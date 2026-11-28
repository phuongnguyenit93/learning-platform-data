# Ánh xạ URI đến tệp và thư mục trong cây tài nguyên tĩnh

## 1. Từ URI đến tài nguyên trên đĩa

Từ **Java 18**, JDK cung cấp **Simple Web Server** qua lệnh `jwebserver` để phục vụ tài nguyên tĩnh trong quá trình phát triển, thử nghiệm và gỡ lỗi. Tính năng này vẫn được hỗ trợ trên các JDK hiện đại, bao gồm JDK 27.

Khi trình duyệt gửi một request như:

```http
GET /assets/app.css HTTP/1.1
Host: 127.0.0.1:8080
```

Simple Web Server xác định tài nguyên cần phục vụ bằng cách ánh xạ **đường dẫn trong URI** vào cây thư mục đã chọn làm document root. Nếu document root là `/workspace/site`, đường dẫn `/assets/app.css` tương ứng với tệp:

```text
/workspace/site/assets/app.css
```

Quy trình tổng quát:

```text
HTTP request
GET /assets/app.css
        |
        v
Tách URI path: /assets/app.css
        |
        v
Ghép/giải quyết path trong document root
/workspace/site
        |
        v
/workspace/site/assets/app.css
        |
        v
Kiểm tra tài nguyên
   |            |
   | file       | directory
   v            v
Trả nội dung   Tìm index file
                  |
             +----+----+
             |         |
          Có index   Không có
             |         |
             v         v
        Trả index   Directory listing
```

Đây là mô hình hữu ích để hiểu vì sao URL path không phải đường dẫn tuyệt đối của hệ điều hành, và vì sao chọn đúng document root bằng `-d` rất quan trọng.

> **Phạm vi:** Simple Web Server phục vụ tệp tĩnh qua HTTP/1.1, phù hợp cho phát triển, thử nghiệm và gỡ lỗi. Công cụ không cung cấp HTTPS, HTTP/2, xác thực hoặc xử lý nghiệp vụ web động; không dùng làm máy chủ production.

## 2. Cấu trúc URI và phần được dùng để tìm tệp

Một URI HTTP có thể có dạng:

```text
http://127.0.0.1:8080/products/item.html?lang=vi#details
\___/   \____________/ \__/ \____________/ \______/ \_____/
scheme      authority   port     path        query  fragment
```

Các thành phần cần phân biệt:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Scheme | `http` | Xác định giao thức. |
| Authority/host | `127.0.0.1` | Xác định máy chủ đích. |
| Port | `8080` | Xác định cổng HTTP server. |
| Path | `/products/item.html` | Phần đường dẫn được ánh xạ vào tài nguyên dưới document root. |
| Query | `?lang=vi` | Dữ liệu truy vấn gắn với URI; không phải tên thư mục/tệp. |
| Fragment | `#details` | Phần định vị phía client; trình duyệt không gửi fragment trong HTTP request. |

Đối với Simple Web Server, **URI path** xác định tệp hoặc thư mục được yêu cầu. Query string không trở thành một phần tên tệp. Ví dụ:

```text
http://127.0.0.1:8080/products/item.html?lang=vi
```

vẫn yêu cầu tài nguyên path `/products/item.html`. Phần `lang=vi` không làm server tìm tệp tên `item.html?lang=vi`.

Tương tự, fragment `#details` chỉ có ý nghĩa ở phía client và không được gửi trong request line HTTP. Server không tìm một tệp có tên chứa `#details`.

## 3. Ánh xạ path vào document root

Giả sử cấu trúc thư mục:

```text
web-root/
├── index.html
├── about.html
├── css/
│   └── app.css
├── js/
│   └── app.js
├── images/
│   └── logo.png
└── data/
    └── products.json
```

Chạy server từ thư mục cha của `web-root`:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./web-root
```

Khi đó document root là thư mục `web-root`. Các URL path được ánh xạ như sau:

| Request path | Tài nguyên được tìm dưới document root |
| --- | --- |
| `/` | Thư mục gốc `web-root/`; nếu có index file thì phục vụ index. |
| `/about.html` | `web-root/about.html`. |
| `/css/app.css` | `web-root/css/app.css`. |
| `/js/app.js` | `web-root/js/app.js`. |
| `/images/logo.png` | `web-root/images/logo.png`. |
| `/data/products.json` | `web-root/data/products.json`. |
| `/missing.html` | Không có tài nguyên tương ứng; request thường nhận `404 Not Found`. |

**Dấu `/` ở đầu URL biểu thị gốc của cây tài nguyên được phục vụ**, không phải gốc ổ đĩa như `C:\` hoặc thư mục `/` của hệ điều hành.

Nếu đổi document root, cùng một URI path sẽ ánh xạ tới một vị trí vật lý khác. Ví dụ:

```sh
# Gốc là web-root:
jwebserver -d ./web-root -p 8080

# Gốc là web-root/public:
jwebserver -d ./web-root/public -p 8080
```

Với lệnh thứ hai, URL `/css/app.css` tìm tệp trong `web-root/public/css/app.css`, không phải `web-root/css/app.css`. Hãy luôn đối chiếu URI path với document root thực tế.

## 4. Server xử lý file và directory như thế nào?

Theo tài liệu của công cụ, request `GET` được ánh xạ theo ba trường hợp chính.

### 4.1. URI trỏ tới một file

Nếu tài nguyên được yêu cầu là một tệp, server trả nội dung tệp đó.

Ví dụ:

```text
GET /about.html
       |
       v
web-root/about.html
       |
       v
HTTP response chứa nội dung HTML
```

Kiểm tra bằng:

```sh
curl -i http://127.0.0.1:8080/about.html
```

Nếu tệp tồn tại và có thể được phục vụ, client nhận phản hồi thành công cùng nội dung. Header `Content-Type` cho biết kiểu nội dung mà server suy đoán từ bảng MIME tích hợp.

### 4.2. URI trỏ tới directory có index file

Nếu tài nguyên được yêu cầu là một thư mục và thư mục đó chứa index file, server trả nội dung của index file.

Ví dụ:

```text
web-root/
└── docs/
    ├── index.html
    └── guide.html
```

Request:

```http
GET /docs/ HTTP/1.1
```

được xử lý bằng nội dung index trong thư mục `docs` (ví dụ `docs/index.html`). Người dùng có thể truy cập trang thư mục bằng URL `http://127.0.0.1:8080/docs/`.

Một tệp có tên `index.html` là ví dụ phổ biến. Hãy đặt index file đúng vị trí và kiểm tra hành vi thực tế của JDK đang dùng; đừng giả định mọi tên file bất kỳ đều tự động trở thành trang mặc định.

### 4.3. URI trỏ tới directory không có index file

Nếu thư mục không có index file, Simple Web Server trả về trang HTML liệt kê tên các tệp và thư mục con có thể truy cập trong thư mục đó.

Ví dụ:

```text
web-root/
└── downloads/
    ├── report.pdf
    ├── sample.csv
    └── images/
        └── chart.png
```

Request:

```text
http://127.0.0.1:8080/downloads/
```

có thể hiển thị directory listing gồm `report.pdf`, `sample.csv` và thư mục `images`. Người dùng có thể chọn liên kết để truy cập tài nguyên con.

**Directory listing là hành vi tích hợp của công cụ**, không phải API tìm kiếm hoặc danh mục dữ liệu có phân quyền. Không để tài liệu riêng tư hoặc tệp nhạy cảm trong cây thư mục được phục vụ với giả định rằng người dùng sẽ không tìm thấy chúng.

### 4.4. Bảng tổng hợp hành vi

| Loại tài nguyên | Hành vi với GET |
| --- | --- |
| File tồn tại và có thể phục vụ | Trả nội dung file. |
| Directory có index file | Trả nội dung index file. |
| Directory không có index file | Trả directory listing dạng HTML. |
| Path không tồn tại hoặc không được phục vụ | Thường trả `404 Not Found`. |
| Hidden file hoặc symbolic link | Không được liệt kê hoặc phục vụ. |

## 5. MIME type được xác định tự động

Simple Web Server dùng **bảng MIME tích hợp** để xác định `Content-Type` phù hợp với phần mở rộng tệp. Ví dụ được tài liệu Oracle nêu:

| Phần mở rộng | MIME type ví dụ |
| --- | --- |
| `.html` | `text/html` |
| `.java` | `text/plain` |

Điều này có nghĩa server không thực thi tệp Java hoặc coi mã nguồn Java là ứng dụng web; tệp `.java` được phục vụ như văn bản thuần theo MIME type tương ứng.

Với các loại tệp khác như CSS, JavaScript, SVG, JSON, PNG hoặc PDF, kiểu nội dung được suy đoán từ bảng MIME của JDK. Nếu trình duyệt hiển thị sai hoặc tải xuống thay vì render như mong muốn, hãy kiểm tra header `Content-Type` thay vì đoán từ tên tệp.

Dùng curl:

```sh
curl -I http://127.0.0.1:8080/index.html
curl -I http://127.0.0.1:8080/css/app.css
curl -I http://127.0.0.1:8080/data/products.json
```

Tìm header:

```text
Content-Type: text/html
```

Giá trị thực tế phụ thuộc tệp và bảng MIME của JDK. Không nên tự khẳng định một MIME type khi chưa kiểm tra response header của môi trường đang chạy.

## 6. URI encoding: khoảng trắng và ký tự đặc biệt trong tên file

URL không thể biểu diễn mọi ký tự theo cách gõ trực tiếp trong đường dẫn. Các ký tự cần mã hóa được biểu diễn bằng **percent-encoding**, gồm dấu phần trăm theo sau hai chữ số hex.

Ví dụ, thư mục có khoảng trắng:

```text
web-root/
└── user guides/
    └── getting started.html
```

Trong URL, khoảng trắng được biểu diễn bằng `%20`:

```text
http://127.0.0.1:8080/user%20guides/getting%20started.html
```

Ví dụ kiểm tra:

```sh
curl -i "http://127.0.0.1:8080/user%20guides/getting%20started.html"
```

Các lưu ý:

- URL dùng percent-encoding cho các ký tự không thể hoặc không nên xuất hiện trực tiếp trong URI.
- Không mã hóa dấu phân cách path `/` một cách tùy tiện.
- Dấu `?` mở đầu query string; nếu tên file có ký tự này, phải xử lý encoding đúng để nó không bị hiểu thành query.
- Dấu `#` mở đầu fragment; fragment không được gửi tới server.
- Khi tên tệp chứa ký tự ngoài ASCII, dùng URL encoding phù hợp và kiểm tra URL thực tế trong trình duyệt/curl.

Không nhầm percent-encoding của URI với cách shell xử lý dấu nháy. Dấu nháy trong ví dụ curl giúp shell giữ URL thành một đối số; `%20` là cách biểu diễn khoảng trắng bên trong URI.

## 7. Query string không phải tên file

Xét hai URL:

```text
http://127.0.0.1:8080/products.json
http://127.0.0.1:8080/products.json?category=books
```

Cả hai đều có URI path là `/products.json`. Query `category=books` không làm Simple Web Server tìm một file khác có tên `products.json?category=books`.

Simple Web Server là server tĩnh; nó không tự diễn giải query để lọc nội dung JSON hoặc chạy logic tìm kiếm. Nếu muốn mock các URL khác nhau bằng dữ liệu tĩnh, hãy tổ chức các tệp/thư mục thành path tương ứng, ví dụ:

```text
web-root/
└── products/
    ├── books.json
    ├── electronics.json
    └── all.json
```

Các URL:

```text
/products/books.json
/products/electronics.json
/products/all.json
```

mỗi URL ánh xạ tới một tệp khác nhau. Việc chọn nội dung dựa trên query string cần backend hoặc handler có logic riêng.

## 8. GET và HEAD trong quá trình ánh xạ tài nguyên

Simple Web Server phục vụ các request idempotent `GET` và `HEAD`. Hai method này cho phép kiểm tra tài nguyên theo những cách khác nhau:

- **GET:** yêu cầu nội dung tài nguyên; server trả response body khi tìm thấy tệp hoặc tạo directory listing.
- **HEAD:** yêu cầu metadata/header tương ứng mà không gửi response body.

Ví dụ:

```sh
# Lấy nội dung file:
curl -i http://127.0.0.1:8080/about.html

# Chỉ kiểm tra header:
curl -I http://127.0.0.1:8080/about.html
```

Nếu file không tồn tại, cả GET và HEAD có thể nhận trạng thái lỗi tương ứng, chẳng hạn `404`. HEAD hữu ích để kiểm tra `Content-Type` hoặc metadata mà không cần tải toàn bộ nội dung.

Các method ghi như `POST`, `PUT` hoặc `DELETE` không biến Simple Web Server thành API có thể cập nhật dữ liệu. Request ngoài GET/HEAD nhận `501 Not Implemented` hoặc `405 Method Not Allowed` tùy trường hợp/triển khai.

## 9. Hidden files và symbolic links

Theo tài liệu công cụ, **hidden files và symbolic links không được liệt kê hoặc phục vụ**.

Ví dụ:

```text
web-root/
├── index.html
├── .env
├── .git/
├── public.txt
└── external-link -> /some/other/location
```

Khi directory listing được tạo, các mục ẩn như `.env`, `.git` và symbolic link không được đưa vào danh sách; chúng cũng không được phục vụ theo hành vi được tài liệu mô tả.

Tuy nhiên, đừng dùng quy tắc này như lớp bảo mật duy nhất:

- Không đặt secret, token, khóa riêng hoặc dữ liệu cá nhân trong document root.
- Không dùng symlink để cố tình đưa dữ liệu ngoài cây tài nguyên vào.
- Chỉ chọn thư mục công khai đã được rà soát bằng `-d`.
- Kiểm tra nội dung thư mục trước khi bind vào mạng LAN hoặc wildcard.
- Nhớ rằng directory listing có thể làm lộ tên các tệp và cấu trúc thư mục con.

## 10. Thực hành: ánh xạ URI vào một website nhỏ

### 10.1. Tạo cây thư mục

Tạo cấu trúc:

```text
demo/
└── public/
    ├── index.html
    ├── about.html
    ├── assets/
    │   └── site.css
    ├── docs/
    │   ├── index.html
    │   └── guide.html
    ├── files/
    │   ├── sample.txt
    │   └── user guides/
    │       └── start here.html
    └── data/
        └── products.json
```

Nội dung `demo/public/index.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>URI mapping demo</title>
  <link rel="stylesheet" href="/assets/site.css">
</head>
<body>
  <h1>URI được ánh xạ vào document root</h1>
  <ul>
    <li><a href="/about.html">About</a></li>
    <li><a href="/docs/">Tài liệu</a></li>
    <li><a href="/files/">Tệp mẫu</a></li>
    <li><a href="/data/products.json">JSON</a></li>
  </ul>
</body>
</html>
```

Nội dung `demo/public/assets/site.css`:

```css
body {
  font-family: system-ui, sans-serif;
  max-width: 48rem;
  margin: 2rem auto;
  line-height: 1.6;
}
```

Nội dung `demo/public/docs/index.html`:

```html
<!doctype html>
<html lang="vi">
<head><meta charset="UTF-8"><title>Docs index</title></head>
<body><h1>Trang index của thư mục docs</h1></body>
</html>
```

Nội dung `demo/public/docs/guide.html`:

```html
<!doctype html>
<html lang="vi">
<head><meta charset="UTF-8"><title>Guide</title></head>
<body><h1>Hướng dẫn chi tiết</h1></body>
</html>
```

Nội dung `demo/public/files/sample.txt`:

```text
Đây là tệp văn bản tĩnh.
```

Nội dung `demo/public/data/products.json`:

```json
{
  "products": [
    { "id": 1, "name": "Notebook" },
    { "id": 2, "name": "Pen" }
  ]
}
```

### 10.2. Khởi động server

Từ thư mục `demo`:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o info
```

Mở URL:

```text
http://127.0.0.1:8080/
```

### 10.3. Thử các URI khác nhau

```sh
# File trực tiếp:
curl -i http://127.0.0.1:8080/about.html

# Directory có index:
curl -i http://127.0.0.1:8080/docs/

# Directory không có index:
curl -i http://127.0.0.1:8080/files/

# Tệp trong thư mục con:
curl -i http://127.0.0.1:8080/data/products.json

# Tên tệp chứa khoảng trắng:
curl -i "http://127.0.0.1:8080/files/user%20guides/start%20here.html"

# Tài nguyên không tồn tại:
curl -i http://127.0.0.1:8080/not-found.html
```

Kết quả dự kiến:

| URI | Hành vi |
| --- | --- |
| `/about.html` | Trả nội dung file `about.html`. |
| `/docs/` | Trả nội dung `docs/index.html`. |
| `/files/` | Directory listing vì không có index file. |
| `/data/products.json` | Trả nội dung JSON tĩnh. |
| `/files/user%20guides/start%20here.html` | Trả tệp có khoảng trắng trong tên sau khi URI được xử lý. |
| `/not-found.html` | `404 Not Found`. |

Sau khi thử nghiệm, nhấn Ctrl+C để dừng server.

## 11. Chẩn đoán lỗi ánh xạ URI

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| URL gốc hiển thị directory listing thay vì trang chủ | Document root không có index file. | Kiểm tra đường dẫn sau `-d` và vị trí `index.html`. |
| URL thư mục hiển thị listing dù có trang index ở nơi khác | Index file nằm ngoài chính thư mục đang yêu cầu. | Đặt index file trong đúng directory được ánh xạ. |
| Request file trả `404` | URI path sai, file nằm ngoài document root hoặc tên không khớp. | Đối chiếu URL path với cây thư mục từ gốc `-d`. |
| Đường dẫn có khoảng trắng trả lỗi | URL chưa percent-encode hoặc shell chia URL thành nhiều đối số. | Dùng `%20` trong URI và đặt URL trong dấu nháy khi gọi curl. |
| File tải xuống hoặc hiển thị sai | MIME type được suy đoán khác với mong đợi. | Dùng `curl -I` kiểm tra `Content-Type`. |
| Query string không lọc nội dung JSON | Simple Web Server chỉ phục vụ file tĩnh, không chạy logic query. | Tổ chức tài nguyên thành các URI path riêng hoặc dùng backend. |
| Hidden file không xuất hiện | Công cụ không liệt kê/serving hidden files. | Không dựa vào hành vi này để bảo vệ dữ liệu; chuyển secret ra ngoài document root. |
| Symbolic link không truy cập được | Symbolic link không được liệt kê hoặc phục vụ. | Dùng tệp/thư mục thực nằm dưới document root. |
| Request POST không cập nhật file | CLI chỉ phục vụ GET và HEAD. | Dùng backend/API phù hợp nếu cần xử lý ghi. |

## 12. Bài tập tự kiểm tra

1. Tạo document root có `index.html`, `about.html` và thư mục `docs`. Dự đoán file nào được trả về khi gửi GET tới `/`, `/about.html` và `/docs/`.
2. Xóa hoặc đổi tên index file trong `docs`, gửi lại GET tới `/docs/`. Giải thích vì sao kết quả chuyển thành directory listing.
3. Tạo thư mục `user guides` và tệp `start here.html`. Viết URL đúng dùng percent-encoding.
4. Gửi hai request `/products.json` và `/products.json?category=books`. Giải thích vì sao chúng vẫn ánh xạ tới cùng path.
5. Kiểm tra `Content-Type` của HTML, CSS và JSON bằng `curl -I`. Ghi lại kết quả từ JDK thực tế của bạn.
6. Tạo một tệp ẩn và symbolic link trong document root, quan sát việc không được liệt kê/phục vụ theo hành vi của công cụ.
7. Gửi request HEAD và GET tới cùng một tệp. So sánh headers và response body.
8. Gửi POST tới một tài nguyên tĩnh. Giải thích vì sao Simple Web Server không phải API backend có thể ghi dữ liệu.

**Tiêu chí hoàn thành:** bạn có thể giải thích cách URI path ánh xạ vào document root, dự đoán kết quả cho file/directory/index/listing, hiểu vai trò MIME type và percent-encoding, phân biệt path với query/fragment, đồng thời nhận biết giới hạn GET/HEAD và quy tắc hidden file/symbolic link.

## 13. Tài liệu tham khảo

- [Oracle Java SE 27 — The jwebserver Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html): mô tả cách GET được ánh xạ vào thư mục phục vụ, index file, directory listing, hidden files, symbolic links và MIME type.
- [Oracle Java SE 27 — SimpleFileServer API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): API tạo file handler, ánh xạ request URI vào root directory và phục vụ nội dung tệp/thư mục.
- [Oracle Java SE 27 — Module jdk.httpserver](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/module-summary.html): module cung cấp `jwebserver` và API HTTP server.
- [OpenJDK JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): nguồn gốc tính năng được giới thiệu trong Java 18.
