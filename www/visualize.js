function compareSecondColumn(a, b) {
    if (a[1] === b[1]) {
        return 0;
    }
    else {
        return (a[1] < b[1]) ? -1 : 1;
    }
}

function sort_by_key(dict, key) {
  var list = [];
  for(var outer_key in dict) {
    list.push([outer_key, dict[key]]);
  }
  list.sort(compareSecondColumn);
  return list;
}

function draw_visualization(data) {
  // $("#view-stats").html("Просмотр статистики чата \"" + data.title + "\"");
  var e = $("#stats");
  e.css({width: 800, display: "inline-block"});
  e.find(".chat-title").html("«" + data.title + "»");
  var top_users = sort_by_key(data.users, "messages_count");
  var users_num = top_users.length;
  // $("#users-raiting").css({width: 200, height: 50 * users_num});
  // var s = Snap("#users-raiting");
  // var l1 = s.line(10, 1, 10, 50 * users_num-1);
  // var l2 = s.line()
  // l1.attr({stroke: "red", strokeWidth: 1});
  var html = '<div class="title">По числу сообщений</div>';
  for(var i=0; i<users_num; i++) {
    var user = data.users[top_users[i][0]];
    html += '<div class="row"><img src="' + user.avatar_50 + '">' + user.name + '<br>' + user.messages_count + '</div>';
  }
  e.find(".users-raiting").html(html);
  html = '<div class="title">Типичные слова</div>';
  for(var i=0; i<users_num; i++) {
    var user = data.users[top_users[i][0]];
    html += '<div class="row"><span class="user_name">' + user.name + '</span>: ';
    htmls = [];
    var top_words = sort_by_key(user.words, "count");
    for(var j=0; j<top_words.length; j++) {
      var word = top_words[j][0];
      htmls.push(word);
    }
    html += htmls.join(", ") + '</div>';
  }
  e.find(".top-words").html(html);
  var container = e.find(".messages-by-week .graph").empty()[0];
  var items = [];
  for (var i=0; i<data.periods.weekdays.length; i++) {
    var item = data.periods.weekdays[i];
    items.push({label : {content: item.name, xOffset: -10, yOffset: 25}, x : "2016-01-1" + i, y : item.messages_count});
  }

  var dataset = new vis.DataSet(items);
  var options = {
    start: '2016-01-09',
    end: '2016-01-17',
    moveable: false,
    zoomable: false,
    height: 200,
    showMajorLabels: false,
    showMinorLabels: false
  };
  var graph2d = new vis.Graph2d(container, dataset, options);
  var nodes = [];
  var edges = [];
  for(var i=0; i<top_users.length; i++) {
    var user_id = top_users[i][0];
    var user = data.users[user_id];
    user.id = i;
    nodes.push({id : i, shape : "image", image : user.avatar_50, label: user.name});
  }
  for(var i=0; i<top_users.length; i++) {
    var user = data.users[top_users[i][0]];
    if (user.invited_by) {
      edges.push({from: data.users[user.invited_by].id, to: i, arrows:'to'});
    }
  }
  var container = e.find(".invitation-graph .graph")[0];
  var d = {nodes : new vis.DataSet(nodes), edges : new vis.DataSet(edges)};
  var options = {
        nodes: {
          size:30,
	      color: {
            border: '#406897',
            background: '#6AAFFF'
          },
          font:{color:'#333333'},
        },
        edges: {
          color: 'gray'
        }
      };
  network = new vis.Network(container, d, options);
}
