# Khởi chạy bằng `jwebserver` hoặc `java -m jdk.httpserver` và kiểm tra trợ giúp của đúng JDK

## 1. Mục tiêu và phạm vi

Từ **Java 18**, JDK cung cấp **Simple Web Server** để phục vụ nhanh tài nguyên tĩnh trong quá trình phát triển, thử nghiệm và gỡ lỗi. Tính năng được giới thiệu qua **JEP 408** và vẫn được mô tả trong tài liệu Java SE 27. Có **hai cách khởi chạy chính thức**:

```sh
jwebserver
```

hoặc:

```sh
java -m jdk.httpserver
```

Cả hai cách đều dùng Simple Web Server thuộc module **`jdk.httpserver`**. Bài học này tập trung vào việc **chọn đúng JDK, đọc trợ giúp và phiên bản, chạy server bằng hai lệnh, hiểu vị trí tham số và kiểm chứng kết quả**. Các ví dụ ưu tiên bind vào loopback để sử dụng trên máy phát triển.

> **Giới hạn sử dụng:** đây là server dành cho tài nguyên tĩnh, chỉ hỗ trợ HTTP/1.1 qua HTTP với các yêu cầu GET và HEAD. Nó không cung cấp HTTPS, HTTP/2, xác thực, xử lý nghiệp vụ web động hay giải pháp triển khai production.

## 2. Kiểm tra JDK thực sự đang được sử dụng

Điều kiện cần là **JDK 18 trở lên** có module `jdk.httpserver`. Trước khi gõ lệnh khởi động, hãy kiểm tra:

```sh
java --version
java --list-modules
java --describe-module jdk.httpserver
```

- `java --version` in phiên bản của **lệnh java được shell chọn**.
- `java --list-modules` liệt kê các module quan sát được của runtime image; tìm dòng bắt đầu bằng `jdk.httpserver`, ví dụ `jdk.httpserver@27` trên một bản JDK 27 có gắn thông tin phiên bản.
- `java --describe-module jdk.httpserver` mô tả module cụ thể mà không chạy server. Nếu hệ thống báo không tìm thấy module, runtime đang gọi có thể thiếu module hoặc thuộc JDK không phù hợp.

**Lưu ý khi cài nhiều JDK:** biến `JAVA_HOME` có thể trỏ một phiên bản nhưng các executable `java` và `jwebserver` trên `PATH` lại thuộc phiên bản khác. Shell chọn lệnh dựa trên quy tắc tra cứu lệnh, không tự động dùng `JAVA_HOME`.

### 2.1. Windows PowerShell

```powershell
Get-Command java -All
Get-Command jwebserver -All

# Dùng where.exe, không nhầm với alias 'where' của PowerShell.
where.exe java
where.exe jwebserver

java --version
jwebserver --version
```

Hai lệnh tra cứu đầu giúp nhận biết nhiều bản Java xuất hiện trên `PATH`. Để cố định phiên bản, gọi executable dưới đúng thư mục JDK đã xác định:

```powershell
# Dùng khi JAVA_HOME đã trỏ chính xác đến JDK mong muốn.
& "$env:JAVA_HOME\bin\java.exe" --version
& "$env:JAVA_HOME\bin\jwebserver.exe" --version
& "$env:JAVA_HOME\bin\java.exe" -m jdk.httpserver --help
```

Trong PowerShell, ký hiệu `&` gọi chương trình tại đường dẫn nằm trong dấu nháy, kể cả khi đường dẫn có khoảng trắng.

### 2.2. Linux/macOS

```sh
command -v java
command -v jwebserver

java --version
jwebserver --version

# Nếu JAVA_HOME đã được xác định đúng:
"$JAVA_HOME/bin/java" --version
"$JAVA_HOME/bin/jwebserver" --version
"$JAVA_HOME/bin/java" -m jdk.httpserver --help
```

Lệnh `command -v` hiển thị cách shell tìm executable. Khi vừa thay đổi `PATH`, mở terminal mới hoặc làm mới bộ nhớ lệnh của shell để chắc chắn đang dùng bản cài mới.

### 2.3. Nếu runtime không chứa module

Một runtime image được tạo tối giản có thể không mang module `jdk.httpserver` dù `java` chạy bình thường. Khi đó, chạy `java -m jdk.httpserver` sẽ không hoạt động. Hãy kiểm tra `java --list-modules`, sau đó chọn bản JDK có module thay vì giả định mọi runtime Java đều chứa sẵn.

## 3. Trợ giúp của Java launcher và trợ giúp của Simple Web Server là hai thứ khác nhau

Các lệnh sau **chỉ hiển thị thông tin và thoát**, không khởi chạy một HTTP server:

```sh
# Trợ giúp và phiên bản của công cụ jwebserver:
jwebserver --help
jwebserver --version

# Trợ giúp và phiên bản của server được gọi qua module:
java -m jdk.httpserver --help
java -m jdk.httpserver --version

# Trợ giúp và phiên bản của trình khởi chạy Java:
java --help
java --version
```

| Lệnh | Đối tượng được hỏi |
| --- | --- |
| `jwebserver --help` | Cú pháp và tham số của công cụ Simple Web Server tìm được trên `PATH`. |
| `java -m jdk.httpserver --help` | Cú pháp của Simple Web Server trong **JDK được chọn bởi lệnh java**. |
| `java --help` | Cú pháp của **Java launcher**, trong đó có `-m`, `--module` và các tùy chọn JVM. |
| `jwebserver --version` | Thông tin phiên bản của `jwebserver`. |
| `java -m jdk.httpserver --version` | Thông tin phiên bản của Simple Web Server khi gọi qua module. |
| `java --version` | Phiên bản Java launcher/runtime được chọn. |

Nếu hai cách gọi Simple Web Server hiển thị phiên bản hoặc tham số khác nhau, hãy kiểm tra lại đường dẫn thực thi. Nhiều trường hợp bản JDK được chọn qua `jwebserver` khác bản được chọn qua `java`.

### 3.1. Các tham số của `jwebserver` còn áp dụng trên JDK hiện đại

Theo tài liệu Oracle Java SE 27:

```text
jwebserver [-b bind-address] [-p port] [-d directory]
           [-o none|info|verbose] [-h] [-version]
```

| Tùy chọn | Tác dụng | Mặc định |
| --- | --- | --- |
| `-h`, `-?`, `--help` | Hiển thị hướng dẫn rồi thoát. | — |
| `-version`, `--version` | Hiển thị thông tin phiên bản rồi thoát. | — |
| `-b`, `--bind-address` | Chọn địa chỉ để lắng nghe. | Loopback: `127.0.0.1` hoặc `::1`. |
| `-p`, `--port` | Chọn cổng HTTP. | `8000`. |
| `-d`, `--directory` | Chọn thư mục tài nguyên gốc. | Thư mục làm việc hiện tại. |
| `-o`, `--output` | Mức log `none`, `info`, `verbose`. | `info`. |

Cần kiểm tra `--help` của bản JDK đang thực thi vì cú pháp dòng lệnh là hợp đồng của **công cụ và phiên bản thực tế**, không nên áp dụng máy móc ví dụ đọc từ một bản Java khác.

## 4. Cách thứ nhất: chạy trực tiếp bằng `jwebserver`

Tạo một thư mục minh họa:

```text
demo/
└── public/
    ├── index.html
    └── style.css
```

Trong `demo/public/index.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kiểm tra jwebserver</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>
  <h1>Simple Web Server đang hoạt động!</h1>
</body>
</html>
```

Trong `demo/public/style.css`:

```css
body {
  font-family: system-ui, sans-serif;
  margin: 2rem;
}
```

Đứng tại thư mục `demo` trong terminal và chạy:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o info
```

Giải thích:

- `-b 127.0.0.1` chỉ lắng nghe trên địa chỉ IPv4 loopback, phù hợp để học và thử trên một máy.
- `-p 8080` đổi cổng từ giá trị mặc định `8000`.
- `-d ./public` chỉ phục vụ thư mục `public` và thư mục con, tính từ **thư mục làm việc hiện tại của terminal**.
- `-o info` ghi thông tin yêu cầu HTTP lên terminal khi có truy cập.

Sau khi khởi động thành công, công cụ in thông tin về thư mục phục vụ, địa chỉ, cổng và URL. Ví dụ dạng thông báo (đường dẫn thực tế khác trên mỗi máy):

```text
Serving /path/to/demo/public and subdirectories on 127.0.0.1 port 8080
URL http://127.0.0.1:8080/
```

Mở **http://127.0.0.1:8080/** trong trình duyệt. Tệp `index.html` được phục vụ, và đường dẫn `/style.css` được ánh xạ thành `demo/public/style.css`. Server chạy trong terminal ở foreground, nhấn **Ctrl+C** để dừng.

Nếu không truyền tham số nào:

```sh
jwebserver
```

Server dùng **thư mục làm việc hiện tại**, lắng nghe trên **loopback**, cổng **8000**. Lệnh này rất nhanh để thử, nhưng có thể vô tình phục vụ tệp từ thư mục rộng hơn dự kiến; nên xác định rõ `-d` khi thực hành.

## 5. Cách thứ hai: chạy bằng `java -m jdk.httpserver`

Sau khi dừng server ở mục 4, đứng tại cùng thư mục `demo` và chạy:

```sh
java -m jdk.httpserver -b 127.0.0.1 -p 8080 -d ./public -o info
```

Dạng dài tương đương:

```sh
java --module jdk.httpserver -b 127.0.0.1 -p 8080 -d ./public -o info
```

`-m` là tùy chọn **của Java launcher** dùng để khởi chạy main class của một module có điểm vào chương trình. Trong trường hợp này, module `jdk.httpserver` chứa điểm vào Simple Web Server. **Không cần viết, biên dịch class Java hoặc đóng gói JAR riêng**.

### 5.1. Thứ tự đối số quyết định thành phần nào nhận tham số

```text
java [tùy chọn JVM/launcher] -m jdk.httpserver [tùy chọn Simple Web Server]
```

Với Java launcher, `-p` là cách viết ngắn của **`--module-path`**, còn với Simple Web Server, `-p` là **cổng HTTP**. Bởi vậy:

```sh
# ĐÚNG: server nhận cổng 8080:
java -m jdk.httpserver -p 8080

# SAI MỤC ĐÍCH: Java launcher diễn giải -p là module path:
java -p 8080 -m jdk.httpserver

# ĐÚNG: trợ giúp của server:
java -m jdk.httpserver --help

# Trợ giúp của Java launcher, không phải của server:
java --help
```

Tương tự, `java --version -m jdk.httpserver` **không** kiểm tra phiên bản server: launcher sẽ xử lý `--version` rồi thoát. Dùng `java -m jdk.httpserver --version` để hỏi đúng chương trình.

### 5.2. Cố định cùng một JDK cho cả hai cách chạy

Ví dụ Windows PowerShell, khi `JAVA_HOME` đã trỏ JDK mong muốn:

```powershell
& "$env:JAVA_HOME\bin\jwebserver.exe" --help
& "$env:JAVA_HOME\bin\java.exe" -m jdk.httpserver --help

# Chạy riêng từng lệnh, dừng lệnh thứ nhất trước khi chạy lệnh thứ hai:
& "$env:JAVA_HOME\bin\jwebserver.exe" -p 8080 -d "./public"
& "$env:JAVA_HOME\bin\java.exe" -m jdk.httpserver -p 8080 -d "./public"
```

Ví dụ tương tự trên Linux/macOS:

```sh
"$JAVA_HOME/bin/jwebserver" -p 8080 -d "./public"
# Dừng lệnh trước bằng Ctrl+C, sau đó:
"$JAVA_HOME/bin/java" -m jdk.httpserver -p 8080 -d "./public"
```

Hai server cùng bind một địa chỉ và cổng **không thể chạy song song**. Khi kiểm thử, hãy khởi chạy và dừng lần lượt để tránh lỗi cổng đã được sử dụng.

## 6. Xác minh phản hồi HTTP và so sánh hai cách chạy

Giữ một terminal chạy server, mở terminal thứ hai:

```sh
# Xem HTTP status, header và HTML:
curl -i http://127.0.0.1:8080/

# Kiểm tra HEAD không trả phần thân:
curl -I http://127.0.0.1:8080/style.css

# Kiểm tra tài nguyên không có:
curl -i http://127.0.0.1:8080/unknown.html
```

Nếu dùng **Windows PowerShell 5.1**, hãy gõ `curl.exe` thay vì `curl` khi muốn gọi chương trình curl (do `curl` có thể là alias của `Invoke-WebRequest`).

| Thử nghiệm | Kết quả dự kiến |
| --- | --- |
| `GET /` | `200 OK`, phần thân là nội dung trang HTML. |
| `HEAD /style.css` | `200 OK`, trả các header nhưng không trả body. |
| `GET /unknown.html` | `404 Not Found`. |
| Gửi HTTP request khi chọn `-o info` | Terminal server in log yêu cầu. |
| Nhấn `Ctrl+C` | Server dừng; nếu không có tiến trình thay thế, cổng không còn phục vụ HTTP. |

Để so sánh công bằng, sử dụng cùng bản JDK, cùng thư mục làm việc, `-b`, `-p`, `-d`, `-o` và nội dung tệp. Dừng một cách chạy rồi khởi động cách còn lại, gửi lại ba request giống nhau. Kết quả HTML/CSS sẽ tương đương vì hai cách gọi cùng một Simple Web Server.

## 7. Gỡ lỗi khi lệnh không hoạt động như mong đợi

| Hiện tượng | Nguyên nhân và hướng xử lý |
| --- | --- |
| `jwebserver` không tìm thấy | Kiểm tra `PATH`, `Get-Command` hoặc `command -v`; thử executable dưới `bin` của JDK mục tiêu. |
| `java --version` khác JDK dự kiến | Kiểm tra lệnh `java` được chọn từ thư mục nào; sửa `PATH` hoặc dùng đường dẫn tuyệt đối. |
| `java -m jdk.httpserver` báo không tìm thấy module | Xác nhận JDK 18+ và kiểm tra `java --list-modules`; một runtime image tối giản có thể thiếu module. |
| Hai cách gọi báo khác phiên bản | `java` và `jwebserver` có thể trỏ đến hai JDK khác nhau; kiểm tra đường dẫn executable của mỗi lệnh. |
| `java -p 8080 -m jdk.httpserver` lỗi | Đặt `-p` sau module: `java -m jdk.httpserver -p 8080`. |
| `java --help` không có tùy chọn server | Đó là trợ giúp launcher; dùng `java -m jdk.httpserver --help`. |
| Không bind được cổng `8080` | Dừng tiến trình đang chiếm cổng hoặc chọn cổng khác như `8181`. |
| Nhận `404` hoặc thấy danh sách thư mục | Kiểm tra đường dẫn sau `-d`, thư mục terminal hiện tại và tệp `index.html`. |
| Không truy cập được từ máy khác | Mặc định chỉ lắng nghe loopback; xác định xem có thực sự cần bind vào giao diện mạng khác hay không. |

### Lưu ý về phạm vi mạng

Khi phát triển trên một máy, nên dùng `-b 127.0.0.1`. Tùy chọn `-b 0.0.0.0` khiến server lắng nghe trên **mọi giao diện IPv4**, có thể cho máy khác trong mạng truy cập khi firewall cho phép. Chỉ dùng trong mạng thử nghiệm tin cậy, kiểm tra toàn bộ nội dung thư mục `-d`, vì công cụ không cung cấp HTTPS hoặc xác thực. Nếu thư mục không có tệp index, Simple Web Server còn có thể hiển thị danh sách tệp để tiện kiểm thử.

## 8. Bài tập tự kiểm tra

1. Ghi lại kết quả `java --version`, `jwebserver --version` và `java -m jdk.httpserver --version`. Giải thích khi nào chúng có thể khác nhau.
2. Mở `jwebserver --help` rồi `java -m jdk.httpserver --help` và kiểm tra có các tùy chọn `-b`, `-p`, `-d`, `-o`.
3. Tạo trang `public/index.html`, chạy lần lượt bằng hai lệnh với cùng cổng. Dùng `curl -i` so sánh HTTP status và nội dung phản hồi.
4. Chạy `java -m jdk.httpserver -p 8181 -d ./public`, sau đó giải thích vì sao không dùng `java -p 8181 -m jdk.httpserver`.
5. Tìm đường dẫn thực của hai executable trên hệ điều hành. Khi có nhiều JDK, đề xuất cách cố định cả hai lệnh về cùng một bản cài.

**Tiêu chí đạt:** bạn biết gọi đúng executable, kiểm tra sự hiện diện của `jdk.httpserver`, nhận ra sự khác biệt giữa trợ giúp launcher và trợ giúp công cụ, chạy được cả hai cách với cùng tham số và xác minh server bằng HTTP.

## 9. Tài liệu tham khảo

- [Oracle Java SE 27 — The jwebserver Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html): cách chạy CLI và qua module, tham số chính thức, hành vi HTTP.
- [Oracle Java SE 27 — The java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): ý nghĩa `-m`/`--module`, `-p`/`--module-path`, `--list-modules`, `--describe-module`.
- [OpenJDK JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): giới thiệu tính năng từ Java 18.
