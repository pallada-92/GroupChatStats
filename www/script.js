var token;
var user_id;
var analyze_mode;

function get_addr_error(addr) {
  var s1 = "https://oauth.vk.com/blank.html#access_token=";
  var s2 = "&expires_in=";
  var s3 = "&user_id=";
  var p1 = addr.indexOf(s1);
  if (p1 == -1) return "Адрес должен начинаться с \"https://oauth.vk.com/blank.html#access_token=\"";
  var p2 = p1 + s1.length;
  var p3 = addr.indexOf(s2);
  if (p3 == -1) return "В адресе должно быть поле \"&expires_in=\"";
  var cur_token = addr.slice(p2, p3);
  var p4 = p3 + s2.length;
  var p5 = addr.indexOf(s3);
  if (p5 == -1) return "В адресе должно быть поле \"&user_id=\"";
  var cur_expires = addr.slice(p4, p5);
  var p6 = p5 + s3.length;
  var p7 = addr.length;
  var cur_user_id = addr.slice(p6, p7);
  if (!(/^[0-9a-f]*$/.test(cur_token))) return "Некорректный токен \"" + cur_token+ "\"";
  if (!(/^[0-9]*$/.test(cur_user_id))) return "Некорректный user_id \"" + cur_user_id + "\"";
  paste_url = addr;
  token = cur_token;
  user_id = cur_user_id;
  return false;
}

// https://oauth.vk.com/blank.html#access_token=0e777963c51d8eaaa1c605f97e3bba28858b69484f9f3f59122a4e8bda5fd1b8eeaf4201d5581dc885a76&expires_in=86400&user_id=12518218
// https://oauth.vk.com/blank.html#access_token=0e777963c51d8eaaa1c605f97e3bba28858b69484f9f3f59122a4e8bda5fd1b8eeaf4201d5581dc885a7&expires_in=86400&user_id=12518218

function verify_token() {
  var addr = $("#paste-url").val();
  var error = get_addr_error(addr);
  if (error) {
    render_analyze(0, error);
    return;
  }
  render_analyze(0, "Идет проверка<span class=\"loading-dots\">....</span>");
  $.getJSON('https://api.vk.com/method/messages.getHistory?callback=?', {
    "access_token" : token,
    "count" : 1,
    "peer_id" : 2000000001,
    "v" : "5.38"
  }, function(data) {
    if ("error" in data || !("response" in data)) {
      render_analyze(0, "Не удается воспользваться токеном. Повторите процедуру или напишите нам на pallada-92@ya.ru");
    } else {
      $("#paste-url").blur();
      get_chat_names();
    }
  });
};

var chat_ids_invalid_run;
var checking_chat_id;
var chat_ids_invalid_limit = 10;
var chats_meta = {};
var loading_chat;

var upl_chat_meta;

function finished_uploading() {
  // get_chat_names();
  location.reload();
}

function upload_chunk(offset) {
  var total_mes = upl_chat_meta.count;
  var uploaded = Math.min(offset, total_mes);
  $("#uploading-progress .bar").css("width", 100 * (uploaded / total_mes) + "%");
  $("#uploading-progress .status").html(uploaded + " / " + total_mes);
  if (offset > total_mes) {
    finished_uploading();
    return;
  }
  $.getJSON('https://api.vk.com/method/messages.getHistory?callback=?', {
      "access_token" : token,
      "count" : 200,
      "peer_id" : 2000000000 + upl_chat_meta.id,
      "start_message_id" : upl_chat_meta.items[0].id,
      "offset" : offset,
      "v" : "5.38"
    }, function(data) {
      if ("response" in data) {
        data.chunk_type = "messages";
        $.get('/upload_chunk', {
          "data" : "{}"
        }, function(data) {
          setTimeout("upload_chunk(" + (offset + 200) + ")", 333);
        });
      }
    });
}

function start_loading_chat(chat_id) {
  render_analyze(3);
  loading_chat = chat_id;
  upl_chat_meta = chats_meta[chat_id];
  upl_chat_meta.chunk_type = "vk_chat_meta";
  $("#uploading-chat h1").html("<h1>Идет отправка сообщений из чата &laquo;" + upl_chat_meta.title + "&raquo; на сервер</h1>");
  $.get("/upload_chunk", "{}"/*JSON.stringify(upl_chat_meta)*/, function(data) {});
  upload_chunk(0);
}

// TODO обработка токена с истекшим сроком действия
function check_next_chat_id() {
  if (analyze_mode != 1) return;
  var cur_chat_id = checking_chat_id++;
  // $("#loading-chat-names .count").html(cur_chat_id);
  $.getJSON('https://api.vk.com/method/messages.getHistory?callback=?', {
    "access_token" : token,
    "count" : 1,
    "peer_id" : 2000000000 + cur_chat_id,
    "v" : "5.38"
  }, function(data) {
    if ("error" in data || !("response" in data) || !("count" in data.response) || data.response.count == 0) {
      chat_ids_invalid_run++;
      if (chat_ids_invalid_run > chat_ids_invalid_limit) {
        render_analyze(2);
      } else {
        setTimeout(check_next_chat_id, 333);
      }
      return;
    }
    chat_ids_invalid_run = 0;
    if (data.response.count < 1000) {
      setTimeout(check_next_chat_id, 333);
      return;
    }
    chats_meta[cur_chat_id] = data.response;
    $.getJSON('https://api.vk.com/method/messages.getChat?callback=?', {
      "chat_id" : cur_chat_id,
      "count" : 1,
      "access_token" : token,
      "fields" : "name, photo_50, photo_100, photo_200_orig",
      "v" : "5.38"
    }, function(data) {
      if ("response" in data) {
        for (var fieldname in data.response) {
          chats_meta[cur_chat_id][fieldname] = data.response[fieldname];
        }
        $("#select-chat-items").append("<div class=\"select-chat-item\" onClick=\"start_loading_chat(" + cur_chat_id + ")\">" + chats_meta[cur_chat_id].title + "</div>");
      }
    }).always(function() {
      setTimeout(check_next_chat_id, 333);
    });
  }).fail(function() {
    chat_ids_invalid_run++;
    if (chat_ids_invalid_run > chat_ids_invalid_limit) {
      render_analyze(2);
    } else {
      setTimeout(check_next_chat_id, 333);
    }
  });
}

// TODO: Запрашивать чаты пачками,
// обрабатывать ошибки в ответах сервера
function get_chat_names() {
  render_analyze(1);
  cur_chat_id = 0;
  $("#select-chat-items").empty();
  checking_chat_id = 0;
  chat_ids_invalid_run = 0;
  check_next_chat_id();
}

function render_analyze(mode, error) { // 0 = enter_token, 1 = loading_chat_names, 2 = select_chat, 3 = analyzing_chat
  analyze_mode = mode;
  $("#get-token").toggle(mode == 0);
  $("#paste-url-error").html(error || "&nbsp;");
  $("#select-chat").toggle(mode == 1 || mode == 2);
  $("#loading-chat-names").toggleClass('white', mode != 1);
  $("#uploading-chat").toggle(mode == 3);
}

var dots_num = 1;
function update_dots() {
  dots_num++;
  if (dots_num >= 4) {dots_num = 1}
  var dots = ["", ".", "..", "..."];
  var html = dots[dots_num] + "<span style=\"color:white\">" + dots[4 - dots_num] + "</span>";
  $(".loading-dots").html(html);
}

var my_chats;
var selected_menu = "analyze";
 
function select_menu(menu) {
  selected_menu = menu;
  $("#analyze").toggle(selected_menu == "analyze");
  $("#stats").toggle(selected_menu != "analyze");
  if (selected_menu != "analyze") {
    draw_visualization(my_chats.chats[selected_menu]);
  }
  $("#chats-menu").empty();
  if (my_chats) {
    for (var id in my_chats.chats) {
      if (id == selected_menu) {
        $("#chats-menu").append("<span class=\"chats-menu-item selected\">" + my_chats.chats[id].title.replace(" ", "&nbsp;") + "</span>");
      } else {
        $("#chats-menu").append("<span class=\"chats-menu-item\" onClick=\"select_menu('" + id + "')\">" + my_chats.chats[id].title.replace(" ", "&nbsp;") + "</span>");
      }
    }
  }
  if (selected_menu == "analyze") {
    $("#chats-menu").append("<span class=\"chats-menu-item selected\">Проанализировать&nbsp;еще...</span>");
  } else {
    $("#chats-menu").append("<span class=\"chats-menu-item\" onClick=\"select_menu('analyze')\">Проанализировать&nbsp;еще...</span>");    
  }
}

$(function(){
  select_menu("analyze");
  $.getJSON("/my_chats", function(data){
    my_chats = data;
    select_menu("417892:3");
  });
  render_analyze(0);
  verify_token();
  setInterval(update_dots, 500);
  $("#paste-url").on("change keyup paste", verify_token);
})
