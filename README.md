# Анализатор групповых чатов

Ярослав Сергиенко, проектная работа ФКН НИУ ВШЭ, группа БПМИ141-1.

Mockup: https://drive.google.com/file/d/0BxenI4btK8MZelY3RzBJODZDMEU/view?usp=sharing

#### Минимальная функциональность &mdash; бот для Telegram

С точки зрения пользователя: зайти в групповой чат, нажать "добавить участника", найти бота по логину. Бот оставляет сообщение в чате о том, что он начинает вести статистику. Бот будет иметь расширенные привилегии для чтения всех сообщений чата, не только тех, которые адресованы ему. Это будет отражено в статусе бота в списке участников чата.

Пример подобного бота: http://botfamily.com/bot/details/messagestatisticsbot

С момента добавления в групповой чат, бот сохраняет все сообщения в базу данных на сервер, приводит слова к начальной форме при помощи pymorphy и ведет статистику.

С определенной периодичностью (например, каждые 1000 сообщений), бот вставляет изображение с "инфографикой" в чат. Примеры:
* http://www2.sys-con.com/itsg/virtualcd/java/archives/0812/mutton/fig1.jpg
  * Статистика активности чата или пользователей по времени суток.
* https://vk.com/doc12518218_437243244
  * Самые популярные существительные в чате
  * Характерные существительные для каждого пользователя (TF-IDF)
  * Количество и средняя длина сообщений

#### Базовая функциональность &mdash; веб-приложение для анализа групповых чатов ВКонтакте

С точки зрения человека, отправляюего историю сообщений на сервер: зайти на главную страницу, получить токен согласно инструкции, подождать загрузки сообщений на сервер, получить ссылку и передать ее другим участникам чата.

С точки зрения человека, получившего ссылку: перейти по ней, авторизоваться, попасть на страницу со статистикой.

С анализом групповых чатов во ВКонтакте проблема состоит в том, что доступ к сообщениям могут иметь только Standalone-приложения (включая мобильные приложения). Однако имеется возможность сделать это и для веб-приложений. Для этого нужно получить специальный токен, открыв окно с определенным адресом, в котором пользователь подтвердит права на чтение личных сообщений (нет возможности получить права на чтение только групповых чатов или конкретного чата), после чего попросив пользователя скопировать содержимое адресной строки и закрыть окно. Особенностью токена является то, что делать запросы можно только с того же IP, с которого был получен токен. Это означает, что нельзя передать токен от клиента к серверу, чтобы сервер скачивал историю сообщений с сервера ВК напрямую.

В итоге получается, что история сообщений будут посылаться на сервер через веб-приложение:

```
Сервер ВК <-> веб-приложение <-> Сервер GroupChatStats -> страница со статистикой
```

В отличие от бота Telegram, сервер будет выводить выводить статистику при запросе на определенный url, при этом будет требоваться авторизация, чтобы доступ к статистике могли иметь только участники группового чата.

#### Продвинутые функции

* Новые статистики:
  * Популярность слов / число сообщений по дням недели / неделям
  * Граф пользователей:
    * Чьи сообщения находятся рядом чаще, чем если бы они были независимы, то есть, кто с кем общается
    * Кто кого пригласил в чат
    * Кто с кем не дружит
* Поддержка английского языка
