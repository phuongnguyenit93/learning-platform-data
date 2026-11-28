# Simple Web Server dùng cho phát triển, thử nghiệm và gỡ lỗi tài nguyên tĩnh

## 1. Vì sao cần `jwebserver`?

Khi phát triển một trang HTML, kiểm tra CSS/JavaScript, hoặc thử một tập dữ liệu JSON mẫu, ta thường chỉ cần một HTTP server để trình duyệt tải các tài nguyên qua `http://` thay vì mở từng tệp bằng `file://`. Từ **JDK 18**, Java cung cấp công cụ dòng lệnh **`jwebserver`** theo JEP 408. Công cụ này vẫn có mặt trong các JDK hiện đại, gồm JDK 27, và thuộc module **`jdk.httpserver`**.

`jwebserver` khởi động nhanh một **Simple Web Server** để phục vụ các **tệp tĩnh** trong một thư mục cùng các thư mục con. Người học không cần tạo dự án Maven/Gradle, viết lớp `main`, cài servlet container hay cấu hình framework chỉ để xem một trang web mẫu.

Các tình huống phù hợp:

- Xem và thử giao diện HTML/CSS/JavaScript trên máy phát triển.
- Kiểm tra đường dẫn đến ảnh, stylesheet, module JavaScript và tệp JSON.
- Tạo phản hồi `GET` từ các tệp JSON mẫu để phát triển giao diện khi API thật chưa sẵn sàng.
- Gửi các yêu cầu HTTP thủ công để quan sát mã trạng thái, header và log khi gỡ lỗi.
- Chia sẻ tạm thời một thư mục tài nguyên trong **mạng thử nghiệm tin cậy**, sau khi đã cân nhắc phạm vi truy cập.

**Phạm vi:** đây là HTTP server tối giản phục vụ phát triển, thử nghiệm và gỡ lỗi; không được thiết kế làm server production. Nó **chỉ hỗ trợ HTTP/1.1 qua HTTP**, không cung cấp HTTPS/HTTP/2, xử lý nghiệp vụ động, hệ thống xác thực hay cơ chế triển khai ứng dụng web hoàn chỉnh. Đừng nhầm nó với một Java web framework.

## 2. Mô hình hoạt động

```text
Trình duyệt hoặc curl
       |
       | GET /assets/site.css  (HTTP/1.1)
       v
  jwebserver :8080
       |
       | Đọc từ thư mục gốc được chọn bằng -d
       v
  ./site/assets/site.css
       |
       +----> HTTP response: status + header + nội dung tệp
```

Ví dụ, với thư mục gốc `./site`, URL `http://127.0.0.1:8080/assets/site.css` tương ứng với tệp `./site/assets/site.css`. Đường dẫn URL được ánh xạ vào **thư mục phục vụ**, không phải thư mục chứa mã nguồn Java và cũng không phải một endpoint do ứng dụng tự định nghĩa.

Quy tắc xử lý tài nguyên:

| Yêu cầu | Hành vi cần hiểu |
| --- | --- |
| `GET` một tệp tồn tại | Trả nội dung tệp cùng kiểu nội dung (`Content-Type`) được suy đoán từ bảng MIME tích hợp. |
| `HEAD` một tệp tồn tại | Trả thông tin phản hồi tương ứng, nhưng không gửi phần thân tệp. |
| `GET` một thư mục có tệp index | Phục vụ trang index, ví dụ `index.html`. |
| `GET` một thư mục không có tệp index | Trả trang HTML liệt kê các tệp và thư mục con có thể truy cập. |
| `GET` đường dẫn không tồn tại | Thông thường trả `404 Not Found`. |
| `POST`, `PUT`, `DELETE`, ... | Không được phục vụ bởi CLI này; tùy yêu cầu có thể nhận `405 Method Not Allowed` hoặc `501 Not Implemented`. |

Theo tài liệu công cụ, **tệp ẩn và symbolic link không được liệt kê hay phục vụ**. Tuy nhiên, tính chất này không thay thế việc chọn đúng thư mục công khai và rà soát dữ liệu nhạy cảm trước khi chạy server.

## 3. Điều kiện sử dụng và các tùy chọn CLI

Cần một bản **JDK từ 18 trở lên** có module `jdk.httpserver` và lệnh `jwebserver` trong `bin` của JDK. Kiểm tra ở terminal:

```sh
java --version
jwebserver --help
jwebserver --version
```

Nếu dùng nhiều bản JDK, kiểm tra `java` và `jwebserver` đang trỏ tới bản mong muốn. Một số môi trường chỉ cài runtime tối giản hoặc chưa thêm thư mục `bin` của JDK vào `PATH` sẽ không nhận diện được lệnh.

Cú pháp chính:

```text
jwebserver [-b <address>] [-p <port>] [-d <directory>]
           [-o none|info|verbose] [-h] [-version]
```

| Tùy chọn | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `-b`, `--bind-address` | Địa chỉ loopback (`127.0.0.1` hoặc `::1`) | Chọn địa chỉ mạng để lắng nghe. `-b 127.0.0.1` chỉ nhận kết nối IPv4 trên máy hiện tại. |
| `-p`, `--port` | `8000` | Chọn cổng HTTP, ví dụ `8080`. |
| `-d`, `--directory` | Thư mục làm việc hiện tại | Chọn thư mục gốc chứa các tệp được phục vụ. |
| `-o`, `--output` | `info` | Chọn mức ghi log yêu cầu: `none`, `info` hoặc `verbose`. |
| `-h`, `-?`, `--help` | — | Hiển thị hướng dẫn sử dụng rồi thoát. |
| `-version`, `--version` | — | Hiển thị thông tin phiên bản rồi thoát. |

Hai dạng khởi động đều được tài liệu JDK hỗ trợ:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./site -o info

# Tương đương, qua entry point của module jdk.httpserver:
java -m jdk.httpserver -b 127.0.0.1 -p 8080 -d ./site -o info
```

`-d ./site` được tính từ **thư mục làm việc của terminal lúc chạy lệnh**. Nếu thư mục có khoảng trắng trong tên, đặt đường dẫn trong dấu nháy, chẳng hạn `-d "./my static site"`. Công cụ chạy ở foreground; nhấn **Ctrl+C** tại terminal chạy server để dừng.

## 4. Thực hành: phục vụ HTML, CSS và JSON mẫu

Giả sử ta muốn dựng nhanh một trang đọc danh sách sản phẩm từ tệp JSON mà chưa cần backend. Tạo cấu trúc thư mục sau (có thể dùng file manager hoặc terminal):

```text
site/
├── index.html
├── assets/
│   └── site.css
└── api/
    └── products.json
```

**Tệp `site/index.html`:**

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Thử dữ liệu tĩnh</title>
  <link rel="stylesheet" href="/assets/site.css">
</head>
<body>
  <h1>Danh sách sản phẩm</h1>
  <pre id="result">Đang tải dữ liệu...</pre>

  <script>
    fetch("/api/products.json")
      .then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then(data => {
        document.querySelector("#result").textContent =
          JSON.stringify(data, null, 2);
      })
      .catch(error => {
        document.querySelector("#result").textContent =
          `Không tải được dữ liệu: ${error.message}`;
      });
  </script>
</body>
</html>
```

**Tệp `site/assets/site.css`:**

```css
body {
  font-family: system-ui, sans-serif;
  max-width: 720px;
  margin: 2rem auto;
  padding: 0 1rem;
}
pre {
  padding: 1rem;
  background: #f2f4f7;
  white-space: pre-wrap;
}
```

**Tệp `site/api/products.json`:**

```json
{
  "products": [
    { "id": 101, "name": "Bút bi", "price": 5000 },
    { "id": 102, "name": "Sổ tay", "price": 25000 }
  ]
}
```

Từ thư mục **cha** của `site`, mở terminal thứ nhất:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./site -o info
```

Khi khởi động thành công, terminal sẽ cho biết thư mục đang phục vụ, địa chỉ và cổng. Mở trình duyệt tại **`http://127.0.0.1:8080/`**. Server trả trang `index.html`; trình duyệt tải CSS và JavaScript gọi `GET /api/products.json` để hiển thị JSON. Lưu ý URL phải là `http://127.0.0.1:8080/`, không phải đường dẫn tệp `file://.../index.html`. Trong ví dụ này, HTML và JSON cùng origin nên không phát sinh bài toán truy cập chéo origin.

Thay đổi nội dung `products.json`, lưu tệp rồi tải lại trang để kiểm tra giao diện với dữ liệu khác. Không cần biên dịch Java. Nếu HTML dùng một đường dẫn sai, ví dụ `/api/product.json` thay vì `/api/products.json`, yêu cầu sẽ thất bại; phần `.catch(...)` giúp hiện thông báo lỗi ngay trên trang.

> **Lưu ý về mock API:** đây là tệp JSON tĩnh được đọc bằng `GET`, không phải API REST xử lý nghiệp vụ. `jwebserver` không tự sinh dữ liệu, không lưu thay đổi và không xử lý `POST` để thêm sản phẩm.

## 5. Kiểm tra trực tiếp bằng `curl`

Giữ server ở terminal thứ nhất. Mở terminal thứ hai và lần lượt chạy:

```sh
# Xem HTTP status, header và phần thân trang chủ.
curl -i http://127.0.0.1:8080/

# Chỉ yêu cầu header, kiểm chứng HTTP HEAD.
curl -I http://127.0.0.1:8080/api/products.json

# Xem phản hồi khi tài nguyên không tồn tại.
curl -i http://127.0.0.1:8080/api/missing.json

# Kiểm chứng giới hạn của HTTP method.
curl -i -X POST http://127.0.0.1:8080/api/products.json
```

Trên **Windows PowerShell 5.1**, nếu `curl` được ánh xạ thành `Invoke-WebRequest`, hãy dùng **`curl.exe`** trong các ví dụ trên để gọi đúng chương trình curl.

Kỳ vọng khi quan sát:

| Thao tác | Kết quả điển hình | Điều rút ra |
| --- | --- | --- |
| `GET /` | `200 OK` và HTML | Trang chủ được tìm thấy trong thư mục gốc. |
| `HEAD /api/products.json` | `200 OK`, có header, không có body | `HEAD` giúp kiểm tra metadata mà không tải phần thân. |
| `GET /api/missing.json` | `404 Not Found` | Kiểm tra lại tên tệp và đường dẫn tương đối với `-d`. |
| `POST /api/products.json` | `405` hoặc `501` | Công cụ không nhận yêu cầu ghi hay cung cấp logic API động. |

`jwebserver` tự đoán MIME type từ bảng có sẵn, chẳng hạn HTML dùng `text/html`. Khi chẩn đoán, hãy quan sát `Content-Type` thực tế trong header thay vì mặc định cho rằng mọi tệp đều được phục vụ như HTML.

### Kiểm tra cách phục vụ thư mục

- `GET /`: có `site/index.html`, nên trình duyệt nhận trang chủ.
- `GET /assets/`: thư mục `assets` trong ví dụ không có trang index; server có thể trả **directory listing** dạng HTML.
- `GET /assets/site.css`: nhận trực tiếp nội dung CSS.

Việc tự động liệt kê thư mục rất tiện để kiểm thử, nhưng cũng là lý do cần giới hạn những tệp có mặt dưới thư mục được phục vụ. Đừng đặt file cấu hình, khóa truy cập hoặc dữ liệu riêng tư trong thư mục này.

## 6. Gỡ lỗi bằng địa chỉ lắng nghe và log

### Chỉ cho phép truy cập trên máy phát triển

```sh
jwebserver -b 127.0.0.1 -p 9000 -d ./site -o verbose
```

`127.0.0.1` là IPv4 loopback: chỉ các chương trình trên chính máy đó truy cập được qua địa chỉ này. Đặt rõ `-b` giúp tránh nhầm lẫn khi máy có cả IPv4 và IPv6. Nếu bỏ `-b`, công cụ mặc định bind vào loopback (`127.0.0.1` **hoặc** `::1` tùy môi trường), không tự mở cho toàn mạng.

Nếu thật sự cần để **thiết bị khác trong mạng thử nghiệm** truy cập, có thể bind vào một địa chỉ mạng phù hợp, ví dụ:

```sh
jwebserver -b 0.0.0.0 -p 8080 -d ./site -o info
```

`0.0.0.0` có nghĩa là lắng nghe trên **mọi giao diện IPv4**. Máy khác sẽ dùng **địa chỉ IP thực của máy chạy server**, không dùng `0.0.0.0` hay `127.0.0.1` của máy đó. Khả năng truy cập còn phụ thuộc firewall và cấu hình mạng. Chỉ làm điều này trong môi trường kiểm thử tin cậy với thư mục đã được kiểm tra: đây là HTTP không mã hóa và không có cơ chế xác thực dành cho người dùng.

### Chọn mức log phù hợp

| Mức `-o` | Khi nào dùng |
| --- | --- |
| `info` (mặc định) | Xem tóm tắt mỗi yêu cầu, gồm phương thức, URL và mã phản hồi. |
| `verbose` | Gỡ lỗi sâu: xem thêm request/response headers và đường dẫn tuyệt đối tới tài nguyên. |
| `none` | Giảm hoặc tắt log cho từng yêu cầu khi không cần quan sát chúng. |

Ví dụ một dòng log `info` minh họa (thời điểm và địa chỉ thực tế sẽ khác):

```text
127.0.0.1 - - [10/Feb/2021:14:34:11 +0000] "GET /assets/site.css HTTP/1.1" 200 -
```

Nếu CSS không tải được, hãy kiểm tra ba điểm liên tiếp: **URL trên trình duyệt → đường dẫn dưới `-d` → mã trạng thái trong log**. Dùng `-o verbose` khi cần kiểm tra header, nhưng chú ý log chi tiết có thể hiển thị đường dẫn trên máy và nội dung header của request.

## 7. Những giới hạn thường gây nhầm lẫn

| Hiện tượng | Nguyên nhân hoặc cách xử lý |
| --- | --- |
| Terminal báo không tìm thấy `jwebserver` | Kiểm tra đang dùng JDK 18+ phù hợp, `PATH` trỏ tới `bin`, thử `java --version` và `jwebserver --help`. |
| Server không khởi động vì cổng đang được dùng | Chọn cổng khác bằng `-p`, ví dụ `-p 8181`, hoặc dừng tiến trình đang giữ cổng. |
| Trình duyệt hiển thị directory listing thay vì trang HTML | Kiểm tra tệp index trong thư mục đang truy cập và xác nhận `-d` trỏ đúng thư mục gốc. |
| Một đường dẫn trả `404` | Kiểm tra tên tệp, thư mục con, chữ hoa/chữ thường trên hệ điều hành và URL ánh xạ từ `-d`. |
| `GET` thành công nhưng `POST`/`PUT` không thành công | Đây là giới hạn được thiết kế của Simple Web Server CLI; cần backend/handler phù hợp nếu muốn xử lý ghi. |
| Trang SPA mở ở `/` nhưng tải trực tiếp `/products/101` không được | CLI tìm tệp/thư mục theo URL, không cung cấp quy tắc tự chuyển mọi đường dẫn về `index.html`. Cần dev server có fallback nếu ứng dụng phụ thuộc client-side routing. |
| Truy cập từ thiết bị khác không được | Mặc định chỉ bind loopback. Chỉ cân nhắc `-b` trên giao diện mạng phù hợp khi có nhu cầu chia sẻ và bảo đảm phạm vi truy cập an toàn. |
| Thử `https://` hoặc HTTP/2 không thành công | `jwebserver` phục vụ HTTP/1.1, không hỗ trợ HTTPS hay HTTP/2. |

### Khi nào cần công cụ khác?

Nếu muốn chạy endpoint Java có xử lý logic, kiểm tra xác thực, nhận dữ liệu `POST`, cấu hình HTTPS, CORS phức tạp, proxy, hoặc phục vụ frontend SPA với fallback định tuyến, hãy chọn server/framework có những tính năng đó. Tại mức lập trình Java, module `jdk.httpserver` còn có `SimpleFileServer` và các API `HttpServer`/`HttpHandler` để xây dựng hành vi linh hoạt hơn; **đó là bài toán khác với lệnh CLI phục vụ tệp tĩnh**.

## 8. Tự luyện tập và tiêu chí hoàn thành

1. Chạy ví dụ ở mục 4 trên cổng `8080`, xác nhận HTML và JSON tải được bằng trình duyệt và `curl`.
2. Đổi tên `products.json` thành `items.json` nhưng giữ nguyên URL trong `fetch`. Quan sát `404`, sau đó sửa URL để trang hoạt động trở lại.
3. Thử `-o info`, rồi `-o verbose` và so sánh thông tin trong log khi gọi `GET /api/products.json`.
4. Tạo thư mục `site/docs` không có index, thêm `guide.txt`, rồi truy cập `/docs/` và `/docs/guide.txt` để phân biệt directory listing với phản hồi tệp.
5. Gửi `HEAD` và `POST` tới cùng một đường dẫn, giải thích tại sao chỉ một trong hai phương thức phù hợp với server này.

Bạn đã nắm được chủ đề khi có thể **chọn đúng thư mục phục vụ, giới hạn địa chỉ bind, chủ động kiểm tra request và đọc log**, đồng thời phân biệt rõ mock dữ liệu tĩnh với một API thực sự.

## Tài liệu tham khảo

- [Oracle Java SE 27 — `jwebserver` command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html): cú pháp, hành vi HTTP và các tùy chọn hiện hành.
- [Oracle Java SE 27 — module `jdk.httpserver`](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/module-summary.html): vị trí của CLI và vai trò các API HTTP server trong JDK.
- [dev.java — JWebserver](https://dev.java/learn/jvm/tool/jwebserver/): ví dụ sử dụng và các ngữ cảnh phát triển/thử nghiệm.
- [OpenJDK JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): nguồn gốc tính năng được giới thiệu từ Java 18.
