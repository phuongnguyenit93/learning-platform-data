# Tệp index, chuyển hướng đường dẫn thư mục và danh sách nội dung khi thiếu index

## 1. Tổng quan

Từ **Java 18**, JDK cung cấp **Simple Web Server** qua lệnh `jwebserver` để phục vụ tài nguyên tĩnh trong quá trình phát triển, thử nghiệm và gỡ lỗi. Tính năng này vẫn có trong JDK hiện đại, bao gồm JDK 27.

Khi HTTP request trỏ tới một thư mục bên dưới document root, Simple Web Server xử lý theo ba bước:

1. Nếu URL path trỏ tới thư mục nhưng thiếu dấu `/` cuối, server trả chuyển hướng **301 Moved Permanently** tới URL có thêm dấu `/`.
2. Nếu thư mục có index file, server trả nội dung index file.
3. Nếu thư mục không có index file, server trả trang HTML liệt kê các tệp và thư mục con có thể truy cập (directory listing).

Ví dụ:

```text
public/
├── index.html
├── docs/
│   ├── index.html
│   └── guide.html
└── downloads/
    ├── report.pdf
    └── sample.csv
```

| URL path | Kết quả |
| --- | --- |
| `/docs` | `301` chuyển tới `/docs/`. |
| `/docs/` | Trả nội dung `docs/index.html`. |
| `/downloads` | `301` chuyển tới `/downloads/`. |
| `/downloads/` | Trả directory listing vì không có index file. |
| `/downloads/report.pdf` | Trả trực tiếp nội dung file. |

> **Phạm vi:** Simple Web Server phục vụ tệp tĩnh qua HTTP/1.1, phù hợp cho phát triển, thử nghiệm và gỡ lỗi. Công cụ không cung cấp HTTPS, HTTP/2, xác thực hoặc xử lý nghiệp vụ web động; không dùng làm máy chủ production.

## 2. Chuyển hướng 301 cho đường dẫn thư mục thiếu dấu /

### 2.1. Vì sao server thêm dấu /?

Một URL kết thúc bằng tên thư mục nên có dấu gạch chéo cuối để thể hiện rõ đó là đường dẫn thư mục. Khi client gửi:

```http
GET /docs HTTP/1.1
Host: 127.0.0.1:8080
```

và `/docs` ánh xạ tới một thư mục có thật, server trả:

```http
HTTP/1.1 301 Moved Permanently
Location: /docs/
```

Client dùng header `Location` để gửi request tiếp theo tới `/docs/`. Trình duyệt thường tự theo redirect nên người dùng nhìn thấy trang cuối cùng mà không cần sửa URL thủ công.

Redirect này **chỉ chuẩn hóa URL thư mục**. Nó không chuyển thẳng tới `index.html`. Sau khi client yêu cầu `/docs/`, server mới tìm index file hoặc tạo directory listing.

### 2.2. Dấu / cuối ảnh hưởng tới URL tương đối

Giả sử trang HTML chứa:

```html
<link rel="stylesheet" href="assets/site.css">
<a href="guide.html">Hướng dẫn</a>
```

Nếu trang được mở tại `http://127.0.0.1:8080/docs/`, trình duyệt giải quyết URL tương đối thành:

```text
/docs/assets/site.css
/docs/guide.html
```

Nếu URL không có dấu `/` cuối, chẳng hạn `http://127.0.0.1:8080/docs`, trình duyệt có thể coi `docs` là thành phần cuối của tên tài nguyên và giải quyết URL tương đối thành:

```text
/assets/site.css
/guide.html
```

Điều này có thể làm CSS, JavaScript hoặc liên kết con bị tải sai vị trí. Redirect sang URL có dấu `/` giúp trình duyệt xử lý đường dẫn tương đối theo đúng thư mục.

### 2.3. Query string được giữ khi redirect

Nếu request là:

```text
/docs?lang=vi&version=2
```

URL chuyển hướng sẽ giữ query:

```text
/docs/?lang=vi&version=2
```

Query không trở thành tên thư mục hoặc tên tệp. Nó được giữ trong URL đích để client gửi tiếp sau redirect.

### 2.4. Phân biệt redirect với các trường hợp khác

| Request | Kết quả thường gặp |
| --- | --- |
| `/docs` và docs là thư mục | `301`, Location thêm dấu `/`. |
| `/docs/` và docs là thư mục | Xử lý index hoặc directory listing. |
| `/guide.html` và đây là tệp | Trả nội dung tệp, không redirect chỉ vì thiếu dấu `/`. |
| `/missing` không tồn tại | `404 Not Found`, không phải redirect thư mục. |

## 3. Kiểm tra redirect bằng curl

Giả sử server chạy ở `127.0.0.1:8080`.

### 3.1. Xem phản hồi redirect ban đầu

```sh
curl -i http://127.0.0.1:8080/docs
```

Tùy chọn `-i` hiển thị headers và body. Kết quả dự kiến có dạng:

```http
HTTP/1.1 301 Moved Permanently
Location: /docs/
```

Header `Location` cho biết URL đích mà client cần yêu cầu tiếp.

### 3.2. Cho curl tự động theo redirect

```sh
curl -i -L http://127.0.0.1:8080/docs
```

Tùy chọn `-L` yêu cầu curl theo redirect. Request đầu tiên tới `/docs` nhận 301; request tiếp theo tới `/docs/` nhận nội dung index hoặc directory listing tùy cấu trúc thư mục.

Không có `-L`, curl thường chỉ hiển thị phản hồi redirect ban đầu. Trình duyệt thường tự theo redirect khi điều hướng.

### 3.3. Kiểm tra bằng HEAD

```sh
curl -I http://127.0.0.1:8080/docs
curl -I -L http://127.0.0.1:8080/docs
```

HEAD cho phép xem status và headers mà không tải response body. Có thể dùng để kiểm tra mã 301 và header `Location`, sau đó xem headers của request đã theo redirect.

Trên Windows PowerShell 5.1, gọi `curl.exe` thay cho `curl` nếu tên `curl` đang là alias của `Invoke-WebRequest`.

## 4. Tệp index: phục vụ nội dung trang thay vì danh sách thư mục

### 4.1. Tạo index file trong thư mục

Ví dụ:

```text
public/
└── docs/
    ├── index.html
    ├── guide.html
    └── faq.html
```

Khi client yêu cầu `/docs/`, server tìm tệp index trong thư mục `docs`. Nếu tìm thấy, nội dung index được trả về; directory listing không được tạo cho request đó.

Ví dụ nội dung `public/docs/index.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tài liệu dự án</title>
</head>
<body>
  <h1>Tài liệu dự án</h1>
  <ul>
    <li><a href="guide.html">Hướng dẫn</a></li>
    <li><a href="faq.html">Câu hỏi thường gặp</a></li>
  </ul>
</body>
</html>
```

Trình duyệt hiển thị trang index. Các liên kết tương đối `guide.html` và `faq.html` được giải quyết bên dưới `/docs/`.

### 4.2. Tên index file được hỗ trợ

Tài liệu CLI mô tả khái quát là “index file”. Trong implementation OpenJDK hiện hành, hai tên được kiểm tra là:

1. `index.html`
2. `index.htm`

`index.html` được ưu tiên. Nếu cả hai cùng tồn tại, `index.html` được chọn trước; nếu không có `index.html`, server mới kiểm tra `index.htm`.

| Tệp trong thư mục | Kết quả |
| --- | --- |
| Chỉ có `index.html` | Phục vụ `index.html`. |
| Chỉ có `index.htm` | Phục vụ `index.htm`. |
| Có cả hai | Ưu tiên `index.html`. |
| Không có cả hai | Tạo directory listing. |
| Chỉ có `home.html` | Không được tự nhận là index; directory listing vẫn được tạo. |

Đừng giả định `Index.html`, `INDEX.HTML` hoặc tên tùy chỉnh sẽ được chọn làm trang index.

### 4.3. Index file không cần xuất hiện trong URL

Khi request `/docs/` được xử lý bằng `docs/index.html`, URL trình duyệt vẫn là:

```text
http://127.0.0.1:8080/docs/
```

Server trả nội dung index mà không yêu cầu client chuyển URL sang `/docs/index.html`. Client vẫn có thể truy cập trực tiếp tệp bằng URL:

```text
http://127.0.0.1:8080/docs/index.html
```

Hai URL có thể trả cùng nội dung nhưng thể hiện hai cách truy cập khác nhau: một URL thư mục dùng index mặc định, một URL trỏ thẳng tới tệp.

### 4.4. Mỗi thư mục có index riêng

```text
public/
├── index.html
├── docs/
│   ├── index.html
│   └── guide.html
└── products/
    ├── index.htm
    └── catalog.json
```

| URL | Tệp được phục vụ |
| --- | --- |
| `/` | `public/index.html`. |
| `/docs/` | `public/docs/index.html`. |
| `/products/` | `public/products/index.htm`. |
| `/products/catalog.json` | `public/products/catalog.json`. |

Index file được tìm trong chính thư mục tương ứng với URL, không phải luôn lấy index ở document root.

## 5. Directory listing khi thư mục không có index

### 5.1. Danh sách nội dung được tạo tự động

Nếu thư mục không có `index.html` hoặc `index.htm`, `jwebserver` trả về trang HTML liệt kê các tệp và thư mục con có thể truy cập.

Ví dụ:

```text
public/
└── downloads/
    ├── report.pdf
    ├── sample.csv
    ├── images/
    │   └── chart.png
    └── notes.txt
```

Request:

```http
GET /downloads/ HTTP/1.1
```

có thể trả:

```http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
```

Response body là HTML có tiêu đề thư mục và danh sách liên kết tới các mục được liệt kê. Client có thể bấm liên kết hoặc gửi request trực tiếp tới từng tài nguyên.

### 5.2. Directory listing không phải trang index tùy chỉnh

Directory listing do server sinh tự động. Nó không đọc README hay tệp văn bản bất kỳ để biến nội dung thành trang chủ.

Ví dụ, nếu thư mục chỉ có:

```text
downloads/
├── README.txt
├── report.pdf
└── sample.csv
```

thì `README.txt` không được coi là index. Server vẫn tạo directory listing; người dùng có thể mở README bằng URL trực tiếp nếu tệp được phục vụ.

Muốn có giao diện thư mục riêng, hãy tạo `index.html` hoặc `index.htm` với các liên kết mong muốn.

### 5.3. Những mục không xuất hiện trong listing

Theo tài liệu công cụ, **hidden files và symbolic links không được liệt kê hoặc phục vụ**. Directory listing chỉ bao gồm những mục có thể đọc và được phép hiển thị theo quy tắc của server.

Ví dụ:

```text
downloads/
├── report.pdf
├── sample.csv
├── .private-notes
├── .git/
└── external-link -> /other/location
```

Các mục ẩn như `.private-notes`, `.git` và symbolic link không xuất hiện trong directory listing và không được phục vụ theo hành vi được tài liệu mô tả.

Đây không phải cơ chế phân quyền đầy đủ. Không đặt mật khẩu, token, khóa riêng, bản sao lưu hoặc dữ liệu cá nhân trong document root với giả định rằng tệp ẩn sẽ luôn an toàn.

### 5.4. Directory listing là phản hồi HTTP có nội dung

Directory listing thường trả status thành công và `Content-Type: text/html; charset=UTF-8`. Vì vậy, khi kiểm tra bằng curl, bạn sẽ thấy HTML thay vì JSON hoặc danh sách tệp ở định dạng API.

```sh
curl -i http://127.0.0.1:8080/downloads/
```

Muốn chỉ xem headers:

```sh
curl -I http://127.0.0.1:8080/downloads/
```

## 6. Thực hành: so sánh redirect, index và directory listing

### 6.1. Chuẩn bị cấu trúc thư mục

```text
demo/
└── public/
    ├── index.html
    ├── docs/
    │   ├── index.html
    │   ├── guide.html
    │   └── faq.html
    └── downloads/
        ├── report.txt
        └── sample.csv
```

Nội dung `public/index.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Demo jwebserver</title>
</head>
<body>
  <h1>Trang chủ</h1>
  <a href="/docs/">Tài liệu</a>
  <a href="/downloads/">Tệp tải xuống</a>
</body>
</html>
```

Nội dung `public/docs/index.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Docs</title>
</head>
<body>
  <h1>Trang index của docs</h1>
  <a href="guide.html">Hướng dẫn</a>
  <a href="faq.html">FAQ</a>
</body>
</html>
```

Nội dung `public/docs/guide.html`:

```html
<!doctype html>
<html lang="vi">
<head><meta charset="UTF-8"><title>Guide</title></head>
<body><h1>Hướng dẫn</h1></body>
</html>
```

Nội dung `public/docs/faq.html`:

```html
<!doctype html>
<html lang="vi">
<head><meta charset="UTF-8"><title>FAQ</title></head>
<body><h1>Câu hỏi thường gặp</h1></body>
</html>
```

Nội dung `public/downloads/report.txt`:

```text
Tài liệu mẫu để kiểm tra directory listing.
```

Nội dung `public/downloads/sample.csv`:

```csv
id,name
1,Notebook
2,Pen
```

### 6.2. Khởi động server

Từ thư mục `demo`, chạy:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o info
```

Mở URL:

```text
http://127.0.0.1:8080/
```

### 6.3. Kiểm tra URL thư mục không có dấu /

```sh
curl -i http://127.0.0.1:8080/docs
```

Kết quả dự kiến là `301 Moved Permanently` với `Location: /docs/`.

Tiếp theo:

```sh
curl -i -L http://127.0.0.1:8080/docs
```

Curl theo redirect và nhận nội dung `docs/index.html`.

### 6.4. Kiểm tra index file

```sh
curl -i http://127.0.0.1:8080/docs/
```

Kết quả dự kiến là `200 OK` với nội dung HTML của trang index. URL vẫn là `/docs/`, không cần đổi thành `/docs/index.html`.

### 6.5. Kiểm tra directory listing

```sh
curl -i http://127.0.0.1:8080/downloads/
```

Vì `downloads` không có index file, response body là HTML directory listing chứa liên kết tới `report.txt` và `sample.csv`.

### 6.6. Kiểm tra truy cập trực tiếp một tệp

```sh
curl -i http://127.0.0.1:8080/downloads/report.txt
```

Request này trỏ tới file nên server trả nội dung file, không tạo directory listing.

### 6.7. Bảng kết quả kỳ vọng

| Request | Status thường thấy | Kết quả |
| --- | --- | --- |
| `GET /docs` | `301` | Redirect tới `/docs/`. |
| `GET /docs/` | `200` | Nội dung `docs/index.html`. |
| `GET /docs/guide.html` | `200` | Nội dung file `guide.html`. |
| `GET /downloads` | `301` | Redirect tới `/downloads/`. |
| `GET /downloads/` | `200` | HTML directory listing. |
| `GET /downloads/report.txt` | `200` | Nội dung tệp văn bản. |
| `GET /not-found/` | `404` | Thư mục không tồn tại. |

Sau khi hoàn tất, nhấn **Ctrl+C** tại terminal server để dừng.

## 7. Những giới hạn cần hiểu

### 7.1. Không có tùy chọn CLI để cấu hình tên index tùy ý

Simple Web Server CLI dùng hành vi index tích hợp. Không có tùy chọn dòng lệnh để khai báo tên trang chủ tùy ý như `home.html`, `default.html` hoặc `welcome.html`.

Nếu cần dùng tên khác, bạn có thể:
- tạo `index.html` hoặc `index.htm` làm trang index;
- truy cập trực tiếp tệp tùy chỉnh bằng URL của nó;
- dùng server/framework khác hoặc tự xây dựng handler khi cần quy tắc định tuyến riêng.

### 7.2. Không có tùy chọn CLI để tắt directory listing

Khi thư mục không có index file, công cụ tạo directory listing. CLI không cung cấp một tham số riêng để tắt hành vi đó hoặc thay thế bằng trang lỗi tùy chỉnh.

Nếu không muốn người dùng nhìn thấy danh sách nội dung, hãy đặt index file phù hợp trong thư mục và kiểm tra lại document root. Index file chỉ thay đổi phản hồi khi yêu cầu thư mục; các tệp con vẫn có thể truy cập trực tiếp bằng URL nếu chúng nằm trong cây được phục vụ.

Với yêu cầu phân quyền, giới hạn truy cập hoặc kiểm soát directory listing, hãy dùng một web server/ứng dụng có cấu hình bảo mật phù hợp.

### 7.3. Redirect không phải xác thực hoặc bảo vệ tài nguyên

Redirect `/docs` sang `/docs/` chỉ chuẩn hóa URL. Nó không che giấu tệp, không kiểm tra danh tính người dùng và không giới hạn quyền truy cập.

Tương tự, việc thư mục có index khiến server không hiển thị listing trong phản hồi `/docs/` không có nghĩa các tệp `guide.html` hoặc `faq.html` trở nên riêng tư. Client vẫn có thể yêu cầu trực tiếp các URL đó.

### 7.4. Chỉ hỗ trợ GET và HEAD

Simple Web Server chỉ phục vụ `GET` và `HEAD`. Các method khác có thể nhận `405 Method Not Allowed` hoặc `501 Not Implemented`. Không thể dùng directory listing như một API quản lý tệp có chức năng upload, xóa hoặc sửa dữ liệu.

## 8. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `/docs` trả `301` | Đây là redirect chuẩn hóa URL thư mục thiếu `/` cuối. | Theo `Location` hoặc dùng `/docs/` ngay từ đầu. |
| Curl chỉ hiện `301`, không thấy HTML | Curl chưa được yêu cầu theo redirect. | Dùng `curl -L` để theo redirect. |
| `/docs/` trả listing thay vì index | Không có `index.html` hoặc `index.htm` trong đúng thư mục được phục vụ. | Kiểm tra tên và vị trí index file dưới document root. |
| Có cả `index.html` và `index.htm`, nhưng nội dung không như mong đợi | `index.html` được ưu tiên. | Kiểm tra nội dung `index.html` hoặc chỉ giữ tệp index dự định dùng. |
| `home.html` không được chọn làm trang mặc định | Tên đó không nằm trong các tên index tích hợp. | Tạo `index.html`/`index.htm` hoặc truy cập trực tiếp `home.html`. |
| Directory listing không hiển thị tệp ẩn | Hidden files không được liệt kê/phục vụ. | Không dựa vào điều này để bảo vệ dữ liệu; chuyển dữ liệu nhạy cảm ra ngoài document root. |
| Liên kết CSS/JS sai sau khi mở thư mục | URL thư mục thiếu dấu `/` cuối hoặc đường dẫn tương đối được viết sai. | Dùng URL thư mục có `/` cuối và kiểm tra base path của liên kết. |
| `/docs` trả `404` thay vì `301` | `docs` không tồn tại dưới document root hoặc không được phục vụ. | Kiểm tra `-d`, đường dẫn và tên thư mục. |
| `/docs/` trả `404` | Thư mục hoặc path không tồn tại, không đọc được hoặc bị loại khỏi phạm vi phục vụ. | Kiểm tra document root, quyền đọc và đường dẫn. |

## 9. Bài tập tự kiểm tra

1. Tạo thư mục `docs` có `index.html` và `guide.html`. Gửi GET tới `/docs` rồi `/docs/`; ghi lại status và giải thích vì sao có redirect.
2. Dùng `curl -i` và `curl -i -L` với cùng URL `/docs`. So sánh kết quả khi curl không theo và có theo redirect.
3. Thay `index.html` bằng `index.htm`. Xác minh trang index vẫn được phục vụ.
4. Tạo đồng thời `index.html` và `index.htm` với nội dung khác nhau. Xác định tệp được ưu tiên.
5. Đổi tên index thành `home.html`. Gửi request `/docs/` và `/docs/home.html`; giải thích sự khác nhau.
6. Tạo thư mục `downloads` không có index. Quan sát directory listing và mở một tệp con từ liên kết được tạo.
7. Thêm một tệp ẩn và symbolic link vào thư mục. Kiểm tra chúng không xuất hiện trong listing và không được phục vụ.
8. Tạo một trang index chứa liên kết tương đối `guide.html`. So sánh URL `/docs` với `/docs/` và giải thích vai trò của dấu `/` cuối.
9. Giải thích vì sao có index file không đồng nghĩa các tệp trong thư mục được bảo vệ khỏi truy cập trực tiếp.

**Tiêu chí hoàn thành:** bạn dự đoán được khi nào server trả 301, khi nào phục vụ index file và khi nào tạo directory listing; biết kiểm tra `Location` bằng curl, hiểu thứ tự ưu tiên `index.html`/`index.htm`, và nhận thức rằng index/redirect không phải cơ chế phân quyền.

## 10. Tài liệu tham khảo

- [Oracle Java SE 27 — The jwebserver Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html): mô tả GET được ánh xạ tới file, directory có index file và directory listing khi thiếu index; quy tắc hidden files và symbolic links.
- [Oracle Java SE 27 — SimpleFileServer API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): mô tả file handler và hành vi phục vụ file/directory listing trong API.
- [OpenJDK — FileServerHandler.java](https://github.com/openjdk/jdk/blob/master/src/jdk.httpserver/share/classes/sun/net/httpserver/simpleserver/FileServerHandler.java): implementation hiện hành về redirect 301 cho thư mục thiếu dấu `/`, thứ tự tìm `index.html`/`index.htm` và cách tạo directory listing.
- [OpenJDK JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): bối cảnh giới thiệu Simple Web Server trong Java 18.
