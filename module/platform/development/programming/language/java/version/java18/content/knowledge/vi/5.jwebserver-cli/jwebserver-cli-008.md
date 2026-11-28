# Điều chỉnh mức log none, info và verbose bằng `-o` hoặc `--output`

## 1. Vì sao cần chọn mức log?

Từ **Java 18**, JDK cung cấp **Simple Web Server** qua lệnh `jwebserver` để phục vụ tài nguyên tĩnh trong quá trình phát triển, thử nghiệm và gỡ lỗi. Công cụ này vẫn được hỗ trợ trên các JDK hiện đại, bao gồm JDK 27.

Khi server chạy, log giúp bạn quan sát request mà trình duyệt hoặc công cụ HTTP gửi tới server. `jwebserver` cho phép chọn mức đầu ra bằng tùy chọn:

- `-o`: dạng ngắn.
- `--output`: dạng dài.

Cả hai chấp nhận ba giá trị:

| Giá trị | Ý nghĩa |
| --- | --- |
| `none` | Không ghi log cho từng request HTTP. |
| `info` | Ghi thông tin cơ bản của mỗi request. Đây là mặc định. |
| `verbose` | Ghi chi tiết hơn, bổ sung request headers, response headers và đường dẫn tuyệt đối của tài nguyên được yêu cầu. |

Ví dụ:

```sh
jwebserver -o info
```

Tương đương:

```sh
jwebserver --output info
```

**Lưu ý:** đây là mức đầu ra của **Simple Web Server**, chủ yếu điều khiển log request. Nó không phải tùy chọn bật/tắt toàn bộ output của tiến trình Java hay hệ thống log của JVM.

> **Phạm vi:** Simple Web Server chỉ phục vụ tài nguyên tĩnh qua HTTP/1.1, phù hợp cho phát triển, thử nghiệm và gỡ lỗi. Công cụ không cung cấp HTTPS, HTTP/2, xác thực hay xử lý nghiệp vụ web động; không dùng làm máy chủ production.

## 2. Cú pháp và giá trị mặc định

Cú pháp tùy chọn:

```text
jwebserver [-o none|info|verbose]
jwebserver [--output none|info|verbose]
```

Nếu không chỉ định `-o`, mức mặc định là **`info`**. Do đó hai lệnh sau có cùng mức log:

```sh
# Không ghi -o: mặc định info
jwebserver

# Ghi rõ mức mặc định
jwebserver -o info
```

Bạn có thể kết hợp mức log với các tùy chọn khác:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o verbose
```

Lệnh trên bind vào IPv4 loopback, dùng cổng `8080`, phục vụ thư mục `./public` và ghi log chi tiết cho request.

Dạng dài tương đương:

```sh
jwebserver --bind-address 127.0.0.1 --port 8080 --directory ./public --output verbose
```

Tên tùy chọn dài thường dễ đọc trong script; dạng ngắn tiện khi gõ trực tiếp trong terminal.

## 3. Mức info: theo dõi request ở mức cơ bản

`info` là mức mặc định. Mỗi request được ghi ra console theo dạng log đơn giản, giúp nhận biết:

- Địa chỉ client mà server quan sát được.
- Thời điểm request.
- HTTP method và đường dẫn được yêu cầu.
- Phiên bản HTTP trong request line.
- Mã trạng thái phản hồi.

Ví dụ một dòng log minh họa theo định dạng được tài liệu Oracle mô tả:

```text
127.0.0.1 - - [10/Feb/2021:14:34:11 +0000] "GET /some/subdirectory/ HTTP/1.1" 200 -
```

Đây chỉ là ví dụ về hình thức; địa chỉ, thời gian, URL và mã trạng thái thực tế phụ thuộc request của bạn.

Có thể đọc dòng này như sau:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Client address | `127.0.0.1` | Địa chỉ client mà server ghi nhận. |
| Timestamp | `[10/Feb/2021:14:34:11 +0000]` | Thời điểm request. |
| Request line | `"GET /some/subdirectory/ HTTP/1.1"` | Method, URL path và phiên bản HTTP. |
| Status | `200` | Mã trạng thái phản hồi. |
| Phần cuối | `-` | Trường phụ trong định dạng log ví dụ. |

### Khi nào dùng info?

- Khi cần biết trình duyệt đã gửi request tới server hay chưa.
- Khi trang tải thiếu CSS, JavaScript hoặc ảnh và muốn tìm request bị lỗi.
- Khi muốn quan sát status như `200`, `404` mà không cần xem toàn bộ headers.
- Khi chạy server trong quá trình phát triển thường ngày.

Ví dụ chạy:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o info
```

Mở trang trong trình duyệt hoặc gửi request bằng curl. Terminal server sẽ xuất hiện log tương ứng. Nếu yêu cầu CSS trả `404`, bạn có thể kiểm tra URL và đường dẫn dưới document root.

## 4. Mức verbose: xem headers và đường dẫn tài nguyên

Khi cần chẩn đoán sâu hơn, chọn:

```sh
jwebserver -o verbose -p 8080 -d ./public
```

Mức `verbose` giữ thông tin request cơ bản và **bổ sung**:

- Request headers do client gửi.
- Response headers do server trả về.
- Đường dẫn tuyệt đối của tài nguyên được yêu cầu trên máy server.

Ví dụ, khi trình duyệt tải `/assets/app.css`, log chi tiết giúp kiểm tra các header liên quan đến request và response, đồng thời cho biết tệp tuyệt đối mà server ánh xạ tới. Điều này hữu ích khi nghi ngờ sai document root, MIME type hoặc hành vi header.

### Ví dụ kiểm tra request

Khởi động:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o verbose
```

Từ terminal thứ hai:

```sh
curl -i http://127.0.0.1:8080/assets/app.css
```

Quan sát log tại terminal thứ nhất. So với `info`, `verbose` cho thêm headers và đường dẫn tuyệt đối của tài nguyên. Tùy client, headers có thể gồm `Host`, `User-Agent`, `Accept` và các header khác.

### Khi nào dùng verbose?

- Khi cần biết client gửi header gì.
- Khi kiểm tra response headers như `Content-Type` hoặc các metadata phản hồi.
- Khi cần xác nhận URL được ánh xạ tới đúng tệp trong document root.
- Khi debug request bất thường mà log `info` chưa đủ dữ liệu.

**Không nên bật verbose liên tục nếu không cần thiết.** Log chi tiết nhiều hơn, có thể làm terminal khó theo dõi khi trang tải nhiều tài nguyên. Đường dẫn tuyệt đối có thể tiết lộ tên tài khoản hoặc cấu trúc thư mục máy phát triển. Request headers cũng có thể chứa thông tin nhạy cảm nếu client gửi chúng, chẳng hạn cookie hoặc token. Kiểm tra log trước khi chia sẻ cho người khác.

## 5. Mức none: tắt log từng request

Nếu không cần theo dõi request trên console, dùng:

```sh
jwebserver -o none
```

Hoặc:

```sh
jwebserver --output none
```

Mức `none` tắt **log từng request HTTP**. Điều này hữu ích khi bạn chỉ cần server phục vụ tệp tĩnh và không muốn console bị lấp đầy bởi các request tự động từ trình duyệt, ví dụ favicon, CSS, JavaScript hoặc ảnh.

### none không có nghĩa là tiến trình hoàn toàn im lặng

Khi khởi động thành công, server vẫn in thông báo khởi động ra `System.out`, bao gồm địa chỉ và đường dẫn tuyệt đối của thư mục phục vụ cùng URL truy cập. `none` điều khiển đầu ra log request; không nên hiểu nó là tùy chọn tắt mọi thông báo khởi động hoặc mọi lỗi của tiến trình.

Ví dụ:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o none
```

Bạn vẫn đọc URL được in khi server khởi động, nhưng các request sau đó không được ghi thành log request trên console theo mức `info`/`verbose`.

### Khi nào dùng none?

- Khi log request không còn cần thiết trong một phiên xem giao diện tĩnh.
- Khi trình duyệt tạo nhiều request nền khiến console quá nhiều dòng.
- Khi muốn giảm thông tin request xuất hiện trên terminal.
- Khi đã kiểm tra xong đường dẫn và chỉ cần server tiếp tục phục vụ nội dung thử nghiệm.

Không dùng `none` để thay thế kiểm soát truy cập hoặc bảo vệ dữ liệu. Nó chỉ thay đổi mức log, **không** làm server kín hơn, không thay đổi địa chỉ bind, document root, quyền truy cập hay phản hồi HTTP.

## 6. So sánh ba mức log

| Tiêu chí | `none` | `info` | `verbose` |
| --- | --- | --- | --- |
| Log từng request | Không | Có | Có |
| Request line / status | Không ghi log request | Có | Có |
| Request headers | Không ghi log request | Không bổ sung headers | Có |
| Response headers | Không ghi log request | Không bổ sung headers | Có |
| Đường dẫn tuyệt đối tài nguyên | Không ghi log request | Không bổ sung đường dẫn chi tiết | Có |
| Giá trị mặc định | Không | **Có** | Không |
| Mục đích | Giảm log request | Theo dõi cơ bản | Chẩn đoán chi tiết |

Có thể chọn mức log theo câu hỏi đang cần trả lời:

- **Không biết request có tới server không?** Dùng `info`.
- **Cần xem header hoặc đường dẫn tệp tuyệt đối?** Dùng `verbose`.
- **Đã debug xong, không muốn log từng request?** Dùng `none`.

Ba mức chỉ thay đổi thông tin được ghi ra console. Chúng không thay đổi tài nguyên nào được phục vụ, cổng, địa chỉ bind, HTTP status hay nội dung phản hồi.

## 7. Thực hành: quan sát cùng một request ở ba mức

### 7.1. Chuẩn bị thư mục

Tạo cấu trúc:

```text
demo/
└── public/
    ├── index.html
    └── assets/
        └── app.css
```

Tệp `demo/public/index.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kiểm tra jwebserver logging</title>
  <link rel="stylesheet" href="/assets/app.css">
</head>
<body>
  <h1>Thử ba mức log</h1>
  <p>Hãy tải trang và quan sát terminal server.</p>
</body>
</html>
```

Tệp `demo/public/assets/app.css`:

```css
body {
  font-family: system-ui, sans-serif;
  max-width: 48rem;
  margin: 3rem auto;
}
```

### 7.2. Chạy mức info

Từ thư mục `demo`:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o info
```

Mở terminal thứ hai và gửi:

```sh
curl -i http://127.0.0.1:8080/
curl -I http://127.0.0.1:8080/assets/app.css
curl -i http://127.0.0.1:8080/missing.css
```

Quan sát terminal server. Bạn sẽ thấy log request cơ bản và mã trạng thái tương ứng, chẳng hạn trang tồn tại có thể trả `200`, còn tài nguyên không tồn tại trả `404`.

### 7.3. Chạy mức verbose

Dừng server bằng Ctrl+C, sau đó khởi động lại cùng cấu hình nhưng đổi mức:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o verbose
```

Gửi lại ba request giống mục trước. Quan sát các request headers, response headers và đường dẫn tuyệt đối của tài nguyên trong log chi tiết.

So sánh với phiên `info`: request và phản hồi HTTP không đổi chỉ vì bạn chọn `verbose`; thông tin quan sát trên console nhiều hơn.

### 7.4. Chạy mức none

Dừng server rồi chạy:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o none
```

Gửi lại cùng các request từ terminal thứ hai. Trình duyệt/curl vẫn nhận phản hồi HTTP, nhưng terminal server không ghi log cho từng request. Thông báo khởi động vẫn xuất hiện khi server bắt đầu.

### 7.5. Bảng ghi nhận kết quả

| Nội dung quan sát | none | info | verbose |
| --- | --- | --- | --- |
| Thông báo khởi động | Có | Có | Có |
| Log request `GET /` | Không | Có | Có |
| Log request `HEAD /assets/app.css` | Không | Có | Có |
| Log status của request lỗi | Không | Có | Có |
| Request/response headers | Không ghi log request | Không bổ sung headers | Có |
| Đường dẫn tuyệt đối tài nguyên | Không ghi log request | Không bổ sung đường dẫn chi tiết | Có |
| HTTP response của client | Vẫn được gửi | Vẫn được gửi | Vẫn được gửi |

Kết quả này giúp tách bạch **logging** khỏi **xử lý HTTP**: lựa chọn log chỉ tác động quan sát ở terminal.

## 8. Lưu log ra tệp bằng shell redirection

Tùy chọn `-o` chọn mức thông tin log; nó **không phải** tham số chỉ định tên tệp log. Theo tài liệu công cụ, log mặc định được ghi ra console. Nếu muốn lưu output của tiến trình, có thể dùng chuyển hướng output của shell.

Ví dụ trên Linux/macOS:

```sh
jwebserver -p 8080 -d ./public -o verbose > jwebserver.log 2>&1
```

Ví dụ PowerShell:

```powershell
jwebserver -p 8080 -d .\public -o verbose *> jwebserver.log
```

Ví dụ Command Prompt:

```bat
jwebserver -p 8080 -d .\public -o verbose > jwebserver.log 2>&1
```

Các ví dụ trên chuyển hướng output của tiến trình theo quy tắc shell; chúng không tạo tính năng quản lý log riêng trong `jwebserver`. Khi tiến trình chạy foreground và output được chuyển vào tệp, terminal hiện tại có thể không hiển thị thông báo khởi động/log như trước. Dừng server bằng Ctrl+C trong terminal đang giữ tiến trình.

Lưu ý:

- Chọn `info` nếu chỉ cần request line và status.
- Chọn `verbose` khi cần chẩn đoán sâu, rồi bảo vệ tệp log như dữ liệu có thể chứa thông tin nhạy cảm.
- Dùng `none` nếu không cần log request; redirect khi đó không tạo log request hữu ích.
- Xác định vị trí lưu log và quyền truy cập tệp trước khi chia sẻ.
- Không đưa log verbose chứa token, cookie, thông tin nội bộ hoặc đường dẫn riêng tư lên nơi công khai.

## 9. Phân biệt log của jwebserver với log của JVM

Một nhầm lẫn thường gặp là cho rằng `-o verbose` tương đương tùy chọn `-verbose` của lệnh `java`. Hai thứ này thuộc **hai lớp khác nhau**:

| Tùy chọn | Thuộc về | Mục đích |
| --- | --- | --- |
| `jwebserver -o verbose` | Simple Web Server | Ghi thêm request/response headers và đường dẫn tuyệt đối của tài nguyên. |
| `java -verbose:class` | Java launcher/JVM | Hiển thị thông tin về các lớp được nạp. |
| `java -Xlog:...` | JVM Unified Logging | Cấu hình log nội bộ của JVM theo tag, level và output. |

Nếu chạy server qua module:

```sh
java -m jdk.httpserver -o verbose -p 8080
```

`-o verbose` đặt **sau tên module** để được chuyển cho Simple Web Server. Các tùy chọn JVM như `-Xlog:...` được đặt **trước** `-m`:

```sh
java -Xlog:class+load=info -m jdk.httpserver -o info -p 8080
```

Không cần bật JVM logging chỉ để xem request HTTP; dùng `-o info` hoặc `-o verbose` cho đúng mục tiêu.

## 10. Khắc phục vấn đề thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không thấy log request | Server đang chạy với `-o none` hoặc client chưa gửi request tới đúng server. | Kiểm tra lệnh khởi động, URL, địa chỉ bind và cổng; đổi sang `-o info` để quan sát. |
| Không thấy headers | Mức hiện tại là `info`, không phải `verbose`. | Dừng server và khởi động lại với `-o verbose`. |
| Không thấy đường dẫn tuyệt đối | Đường dẫn chi tiết chỉ được bổ sung ở `verbose`. | Dùng `-o verbose` khi cần kiểm tra ánh xạ URL. |
| Terminal có quá nhiều dòng | `info` ghi mỗi request; trình duyệt có thể gửi nhiều request nền. | Dùng `none` khi không cần log, hoặc lọc output bằng công cụ shell phù hợp. |
| Log verbose có thông tin nhạy cảm | Request headers hoặc đường dẫn tuyệt đối có thể chứa thông tin không nên chia sẻ. | Không gửi log nguyên bản lên nơi công khai; rà soát và che dữ liệu nhạy cảm. |
| Không tìm thấy tệp log sau khi redirect | Đường dẫn redirect được tính từ CWD của shell, hoặc tiến trình chưa ghi output được chuyển hướng. | Kiểm tra CWD, đường dẫn đích và trạng thái tiến trình. |
| Dùng `java -o verbose -m jdk.httpserver` bị lỗi | `-o` là tham số của Simple Web Server, không phải tùy chọn launcher. | Đặt sau module: `java -m jdk.httpserver -o verbose`. |
| HTTP response không thay đổi khi đổi mức log | Logging không điều khiển hành vi xử lý request. | Đây là hành vi đúng; kiểm tra status/body bằng curl thay vì dựa vào lượng log. |

## 11. Bài tập tự kiểm tra

1. Chạy `jwebserver` không truyền `-o`. Xác định mức mặc định và quan sát một request GET.
2. Chạy lại bằng `-o info` rồi `--output info`. Giải thích vì sao hai cách có cùng kết quả.
3. Gửi các request GET, HEAD và một URL không tồn tại trong ba phiên `none`, `info`, `verbose`. So sánh log và HTTP response.
4. Chọn `verbose`, kiểm tra request headers, response headers và đường dẫn tuyệt đối. Giải thích vì sao cần rà soát log trước khi chia sẻ.
5. Chọn `none` và xác nhận thông báo khởi động vẫn có thể xuất hiện trong khi log từng request không được ghi.
6. Dùng shell redirection lưu output vào tệp. Xác định CWD, vị trí tệp và cách dừng tiến trình.
7. Giải thích khác biệt giữa `jwebserver -o verbose` và `java -verbose:class`.

**Tiêu chí hoàn thành:** bạn chọn đúng `none`, `info`, `verbose` theo nhu cầu, hiểu log nào được bổ sung ở mức verbose, biết rằng none chỉ tắt log request, phân biệt log của server với log JVM và bảo vệ tệp log khi có thông tin nhạy cảm.

## 12. Tài liệu tham khảo

- [Oracle Java SE 27 — The jwebserver Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html): tùy chọn `-o`/`--output`, mức mặc định `info`, định dạng log request và thông tin được bổ sung ở mức `verbose`.
- [Oracle Java SE 27 — The java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): tùy chọn launcher và JVM logging, giúp phân biệt log của JVM với log của Simple Web Server.
- [OpenJDK JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): bối cảnh giới thiệu Simple Web Server từ Java 18.
