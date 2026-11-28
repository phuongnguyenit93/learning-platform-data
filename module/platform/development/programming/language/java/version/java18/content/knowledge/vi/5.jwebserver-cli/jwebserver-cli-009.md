# Đọc thông báo khởi động để xác nhận địa chỉ, cổng và đường dẫn tuyệt đối được phục vụ

## 1. Vì sao cần đọc thông báo khởi động?

Từ **Java 18**, JDK cung cấp công cụ **Simple Web Server** qua lệnh `jwebserver` để phục vụ tài nguyên tĩnh trong quá trình phát triển, thử nghiệm và gỡ lỗi. Công cụ này vẫn được hỗ trợ trên JDK hiện đại, bao gồm JDK 27.

Khi khởi động thành công, `jwebserver` in thông báo ra **`System.out`**. Thông báo cho biết:

- Địa chỉ local mà server lắng nghe.
- Đường dẫn tuyệt đối của thư mục đang được phục vụ.
- Cổng server sử dụng.
- URL để truy cập server.

Ví dụ khi chạy mặc định:

```sh
jwebserver
```

Thông báo minh họa theo tài liệu Oracle Java SE 27:

```text
Binding to loopback by default. For all interfaces use "-b 0.0.0.0" or "-b ::".
Serving /cwd and subdirectories on 127.0.0.1 port 8000
URL http://127.0.0.1:8000/
```

Đừng xem các dòng này chỉ là thông báo trang trí. Đây là bằng chứng nhanh để kiểm tra server đã khởi động và **đang phục vụ đúng địa chỉ, cổng, thư mục mà bạn dự định**.

> **Phạm vi:** Simple Web Server chỉ phục vụ tệp tĩnh qua HTTP/1.1, thích hợp cho phát triển, thử nghiệm và gỡ lỗi. Công cụ không cung cấp HTTPS, HTTP/2, xác thực hay xử lý nghiệp vụ web động; không dùng làm máy chủ production.

## 2. Đọc từng dòng trong startup banner

Thông báo khởi động thường có ba dòng quan trọng. Mỗi dòng mang ý nghĩa riêng.

### 2.1. Dòng Binding: thông tin về loopback mặc định

```text
Binding to loopback by default. For all interfaces use "-b 0.0.0.0" or "-b ::".
```

Dòng này xuất hiện trong ví dụ khởi động mặc định và giải thích rằng server đang dùng **loopback** nếu bạn không chỉ định địa chỉ bind:

- IPv4 loopback: `127.0.0.1`.
- IPv6 loopback: `::1`.
- `0.0.0.0` và `::` là địa chỉ wildcard, dùng khi muốn lắng nghe trên các giao diện tương ứng.

Đây là lời giải thích về cấu hình mặc định và cách mở rộng bind. Hãy đọc dòng **Serving** tiếp theo để biết địa chỉ thực tế mà tiến trình đã bind. Nếu bạn truyền `-b` rõ ràng, nội dung thông báo có thể khác hoặc không cần in lời nhắc loopback mặc định.

### 2.2. Dòng Serving: thư mục, địa chỉ và cổng thực tế

```text
Serving /cwd and subdirectories on 127.0.0.1 port 8000
```

Dòng này là phần quan trọng nhất để xác minh cấu hình. Có thể tách thành ba thành phần:

| Thành phần | Ví dụ | Cách hiểu |
| --- | --- | --- |
| Đường dẫn tuyệt đối | `/cwd` | Thư mục gốc mà server đang phục vụ. |
| Địa chỉ local | `127.0.0.1` | Địa chỉ bind mà server đang lắng nghe. |
| Cổng | `8000` | Cổng TCP mà server dùng để nhận kết nối. |

Cụm **`and subdirectories`** cho biết server phục vụ cây thư mục đó cùng các thư mục con. Ví dụ, nếu gốc là `/workspace/site`, tệp `/workspace/site/assets/app.css` có thể được yêu cầu bằng URL path `/assets/app.css`.

Đường dẫn trong dòng `Serving` là **đường dẫn tuyệt đối**, không còn phụ thuộc vào cách bạn viết đường dẫn tương đối trên command line. Đây là cách trực tiếp để phát hiện việc server đang đứng nhầm CWD hoặc chọn sai giá trị `-d`.

Trên Windows, đường dẫn có thể có dạng:

```text
Serving C:\Projects\demo\public and subdirectories on 127.0.0.1 port 8080
```

Trên Linux/macOS, đường dẫn thường có dạng:

```text
Serving /home/dev/demo/public and subdirectories on 127.0.0.1 port 8080
```

Đường dẫn ví dụ chỉ minh họa hình thức. Máy của bạn sẽ hiển thị vị trí thực tế.

### 2.3. Dòng URL: địa chỉ gợi ý để mở bằng client

```text
URL http://127.0.0.1:8000/
```

Dòng này cung cấp URL để bạn mở bằng trình duyệt hoặc gửi request HTTP. Cấu trúc gồm:

- `http://`: giao thức HTTP.
- `127.0.0.1`: host/địa chỉ client dùng để kết nối.
- `:8000`: cổng server.
- `/`: đường dẫn gốc của document root.

Nếu bạn đổi cổng bằng `-p 8080`, URL sẽ phản ánh cổng mới. Nếu bind IPv6 loopback, URL có thể dùng dạng `http://[::1]:8000/`; địa chỉ IPv6 trong URL phải được đặt trong ngoặc vuông.

**Dùng URL được in ra làm điểm bắt đầu**, sau đó bổ sung path của tài nguyên nếu cần, ví dụ `/assets/app.css` hoặc `/data/sample.json`.

## 3. Đọc thông báo khi truyền tham số tùy chỉnh

Thông báo không chỉ hữu ích với cấu hình mặc định. Bạn có thể dùng nó để xác minh các tham số đã truyền.

Giả sử cấu trúc dự án:

```text
demo/
└── public/
    ├── index.html
    ├── assets/
    │   └── app.css
    └── data/
        └── sample.json
```

Chạy từ thư mục `demo`:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o info
```

Nếu khởi động thành công, thông báo sẽ có dạng tương tự:

```text
Serving /absolute/path/to/demo/public and subdirectories on 127.0.0.1 port 8080
URL http://127.0.0.1:8080/
```

Đối chiếu từng giá trị:

| Tham số | Điều cần xác nhận trong output |
| --- | --- |
| `-d ./public` | Đường dẫn sau `Serving` phải trỏ tới thư mục `public` mong muốn. |
| `-b 127.0.0.1` | Địa chỉ sau từ `on` phải là `127.0.0.1`. |
| `-p 8080` | Phần `port` phải là `8080`. |
| `-o info` | Điều khiển log request sau khi server chạy; không thay đổi document root, bind address hoặc port. |

Nếu một trong ba giá trị đường dẫn, địa chỉ hoặc cổng khác dự kiến, dừng server bằng Ctrl+C và kiểm tra lại lệnh trước khi tiếp tục thử nghiệm.

## 4. Phân biệt đường dẫn đã nhập với đường dẫn tuyệt đối được in

### 4.1. Đường dẫn tương đối được giải quyết từ CWD

Ví dụ:

```sh
jwebserver -d ./public
```

Nếu terminal đang ở `/workspace/demo`, đường dẫn được giải quyết thành `/workspace/demo/public`. Dòng `Serving` sẽ cho biết đường dẫn tuyệt đối sau khi được giải quyết.

Trên Windows PowerShell, kiểm tra CWD bằng:

```powershell
Get-Location
```

Trên Linux/macOS:

```sh
pwd
```

Đừng giả định `./public` được tính từ thư mục cài JDK, vị trí executable `jwebserver` hoặc thư mục chứa mã nguồn. Nó được tính từ working directory của tiến trình tại thời điểm khởi chạy.

### 4.2. Đường dẫn tuyệt đối giúp loại bỏ sự mơ hồ

Bạn có thể chỉ định trực tiếp:

**Windows PowerShell:**

```powershell
jwebserver -d 'C:\Projects\demo\public' -p 8080
```

**Linux/macOS:**

```sh
jwebserver -d '/workspace/demo/public' -p 8080
```

Sau khi khởi động, so sánh đường dẫn tuyệt đối được in sau `Serving` với thư mục mà bạn dự định chia sẻ. Nếu hai đường dẫn khác nhau, hãy dừng server và sửa lại lệnh.

### 4.3. Đường dẫn chứa khoảng trắng

Ví dụ:

```sh
jwebserver -d "./My Web Project/site files" -p 8080
```

Hoặc trên PowerShell:

```powershell
jwebserver -d 'C:\Dev Workspace\My Web Project\site files' -p 8080
```

Shell cần truyền toàn bộ đường dẫn thành **một đối số**. Khi server khởi động, dòng `Serving` giúp xác nhận tên thư mục có khoảng trắng đã được hiểu đúng và đường dẫn tuyệt đối trỏ đúng vị trí.

## 5. Đọc thông báo khi bind vào mọi giao diện

Nếu chạy:

```sh
jwebserver -b 0.0.0.0 -p 8080 -d ./public
```

Thông báo trong tài liệu có dạng:

```text
Serving /cwd and subdirectories on 0.0.0.0 (all interfaces) port 8080
URL http://123.456.7.891:8080/
```

Cách đọc:

- `/cwd`: đường dẫn tuyệt đối của document root trong ví dụ.
- `0.0.0.0 (all interfaces)`: server bind vào wildcard IPv4, lắng nghe trên các giao diện IPv4 phù hợp.
- `8080`: cổng server.
- Dòng `URL`: URL gợi ý được in trong ví dụ tài liệu.

Địa chỉ `123.456.7.891` trong tài liệu Oracle là **giá trị minh họa**, không phải IP thật để sao chép. Khi bind wildcard, client từ xa phải dùng **địa chỉ IP thực của máy chạy server** có thể định tuyến tới được. Không dùng `0.0.0.0` làm host đích trong trình duyệt.

Nếu bạn cần IPv6, `-b ::` là wildcard IPv6; khả năng nhận cả IPv4 còn tùy chế độ dual-stack của hệ điều hành/socket. Dòng `Serving` cho biết địa chỉ bind, còn khả năng truy cập từ thiết bị khác vẫn phụ thuộc firewall, routing và cấu hình mạng.

**Lưu ý:** bind mọi giao diện có thể làm server tiếp cận được từ nhiều mạng hơn. Chỉ sử dụng khi đã kiểm tra document root và chắc chắn không làm lộ dữ liệu nhạy cảm.

## 6. Kiểm chứng ba thành phần bằng request HTTP

Thông báo khởi động cho biết cấu hình dự kiến của server. Bạn có thể kiểm chứng tiếp bằng cách gửi request tới URL đó.

Giả sử output là:

```text
Serving /workspace/demo/public and subdirectories on 127.0.0.1 port 8080
URL http://127.0.0.1:8080/
```

Mở terminal thứ hai:

```sh
# Kiểm tra trang chủ:
curl -i http://127.0.0.1:8080/

# Kiểm tra tài nguyên trong thư mục con:
curl -I http://127.0.0.1:8080/assets/app.css

# Kiểm tra đường dẫn không tồn tại:
curl -i http://127.0.0.1:8080/missing.html
```

Kết quả thường thấy:

| Request | Kết quả | Kiểm chứng |
| --- | --- | --- |
| `GET /` | `200 OK` nếu có trang index | Server trả tài nguyên từ document root. |
| `HEAD /assets/app.css` | `200 OK` nếu tệp tồn tại, không có body | URL path được ánh xạ vào thư mục con. |
| `GET /missing.html` | `404 Not Found` nếu tệp không tồn tại | Request đã tới server nhưng không tìm thấy tài nguyên. |

Nếu output ghi cổng `8080` mà bạn truy cập `8000`, đó là URL sai cổng. Nếu output ghi `127.0.0.1` nhưng bạn dùng địa chỉ LAN từ thiết bị khác, listener loopback không nhận kết nối từ thiết bị đó.

Trên Windows PowerShell 5.1, gọi `curl.exe` thay cho `curl` nếu `curl` đang là alias của `Invoke-WebRequest`.

## 7. Đối chiếu thông báo với listener của hệ điều hành

Đôi khi cần xác nhận tiến trình thực sự đang lắng nghe ở địa chỉ/cổng nào. Có thể kiểm tra socket LISTEN bằng công cụ của hệ điều hành.

### Windows PowerShell

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8080 |
  Select-Object LocalAddress, LocalPort, OwningProcess
```

### Linux

```sh
ss -ltnp 'sport = :8080'
```

### macOS

```sh
lsof -nP -iTCP:8080 -sTCP:LISTEN
```

Đối chiếu kết quả:

| Startup banner | Listener hệ điều hành | Cách hiểu |
| --- | --- | --- |
| `on 127.0.0.1 port 8080` | `127.0.0.1:8080` | IPv4 loopback trên cổng 8080. |
| `on ::1 port 8080` | `[::1]:8080` | IPv6 loopback trên cổng 8080. |
| `on 192.168.1.25 port 8080` | `192.168.1.25:8080` | Địa chỉ IPv4 local cụ thể. |
| `on 0.0.0.0 (all interfaces) port 8080` | `0.0.0.0:8080` | Wildcard IPv4. |
| `on :: (all interfaces) port 8080` | `[::]:8080` | Wildcard IPv6; dual-stack tùy cấu hình. |

Công cụ của hệ điều hành có thể trình bày IPv6 bằng dấu ngoặc vuông hoặc dạng rút gọn khác. Hãy đối chiếu địa chỉ, cổng và PID; nếu có nhiều listener, xác định đúng tiến trình đang chạy `jwebserver`.

## 8. Khi không thấy thông báo khởi động như mong đợi

Nếu server khởi động thành công, tài liệu Oracle mô tả rằng thông tin địa chỉ local và đường dẫn tuyệt đối được in ra `System.out`. Khi không thấy dòng `Serving` hoặc `URL`, hãy kiểm tra các khả năng sau:

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Lệnh báo `Address already in use` | Địa chỉ/cổng đã có tiến trình khác lắng nghe. | Kiểm tra listener/PID hoặc chọn cổng khác bằng `-p`. |
| Lệnh báo `Cannot assign requested address` | Địa chỉ được truyền bằng `-b` không thuộc máy hoặc giao diện hiện không khả dụng. | Kiểm tra IP local và dùng địa chỉ hợp lệ. |
| Lệnh báo thư mục không hợp lệ | Giá trị `-d` sai, không tồn tại hoặc không phải thư mục có thể truy cập. | Kiểm tra CWD, đường dẫn và quyền đọc. |
| Chỉ thấy log lỗi, không thấy dòng Serving | Server chưa khởi động thành công. | Đọc exception đầu tiên và xử lý nguyên nhân trước khi thử HTTP. |
| Output được chuyển hướng sang tệp | `System.out` không còn hiển thị trực tiếp ở terminal. | Kiểm tra tệp đích của shell redirection. |
| Có banner nhưng request không kết nối | Client dùng sai host/cổng hoặc firewall/mạng chặn. | Dùng URL từ banner, kiểm tra listener và kết nối TCP. |
| Request kết nối nhưng trả `404` | Tệp không nằm dưới document root hoặc URL path sai. | Đọc lại đường dẫn sau Serving và kiểm tra cây tài nguyên. |

### 8.1. Mức log none không tắt startup banner

Tùy chọn `-o none` điều khiển log từng request HTTP. Nó không có nghĩa mọi thông báo khởi động đều bị tắt. Khi khởi động thành công, banner về địa chỉ local, thư mục phục vụ và URL vẫn được in theo mô tả của công cụ.

Ví dụ:

```sh
jwebserver -o none -p 8080 -d ./public
```

Bạn vẫn cần đọc banner để xác nhận cấu hình; sau đó các request sẽ không được ghi log như ở mức `info`/`verbose`.

### 8.2. Output redirection có thể làm banner không hiện ở màn hình

Trên Linux/macOS hoặc Command Prompt:

```sh
jwebserver -p 8080 -d ./public > jwebserver.log 2>&1
```

Trong PowerShell:

```powershell
jwebserver -p 8080 -d .\public *> jwebserver.log
```

Các lệnh trên chuyển output của tiến trình sang tệp. Nếu terminal không hiện banner, hãy đọc đúng tệp log ở CWD của shell. Đây là hành vi chuyển hướng của shell, không phải thay đổi cách `jwebserver` khởi động.

## 9. Checklist đọc banner trước khi tiếp tục

Sau mỗi lần khởi động server, hãy xác nhận:

- [ ] Có thông báo khởi động thành công và dòng `Serving`.
- [ ] Đường dẫn tuyệt đối sau `Serving` đúng thư mục dự định chia sẻ.
- [ ] Địa chỉ sau từ `on` đúng với cấu hình bind mong muốn.
- [ ] Cổng hiển thị trùng với tùy chọn `-p` hoặc mặc định `8000`.
- [ ] URL có đúng host, cổng và định dạng IPv6 nếu cần.
- [ ] Nếu bind wildcard, client dùng IP thật của máy chủ thay vì `0.0.0.0` hoặc `::`.
- [ ] Đã gửi một request HTTP để xác minh trang/tài nguyên thực tế.
- [ ] Đã kiểm tra phạm vi document root và không chia sẻ tệp nhạy cảm ngoài ý muốn.

## 10. Bài tập tự kiểm tra

1. Chạy `jwebserver` không tham số. Chép lại ba dòng thông báo và giải thích vai trò của `Binding`, `Serving` và `URL`.
2. Chạy `jwebserver -d ./public -p 8080 -b 127.0.0.1`. So sánh đường dẫn, địa chỉ và cổng trong banner với các tham số đã truyền.
3. Đổi CWD sang thư mục cha rồi chạy lại với đường dẫn tương đối. Giải thích vì sao đường dẫn tuyệt đối sau `Serving` thay đổi.
4. Dùng đường dẫn có khoảng trắng. Xác minh shell đã truyền đúng đối số bằng cách đọc dòng `Serving`.
5. Bind `0.0.0.0`. Giải thích vì sao địa chỉ trong dòng Serving không phải host nên nhập vào trình duyệt và cần dùng IP thật của máy.
6. Dùng `curl -i` gửi request tới URL in ra. Phân biệt lỗi kết nối với HTTP `404`.
7. Chạy với `-o none` và xác nhận banner khởi động vẫn có thể xuất hiện dù log request bị tắt.
8. Chuyển hướng output vào tệp, sau đó tìm và đọc banner trong tệp đó.

**Tiêu chí hoàn thành:** bạn có thể đọc banner để xác định chính xác thư mục tuyệt đối đang phục vụ, địa chỉ bind, cổng và URL; phân biệt địa chỉ bind wildcard với host client; đồng thời xác minh cấu hình bằng HTTP request và listener của hệ điều hành.

## 11. Tài liệu tham khảo

- [Oracle Java SE 27 — The jwebserver Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html): xác nhận thông báo khởi động, địa chỉ local, đường dẫn tuyệt đối, cổng, URL và ví dụ bind wildcard.
- [Oracle Java SE 27 — Module jdk.httpserver](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/module-summary.html): module cung cấp công cụ `jwebserver` và mục đích phát triển/thử nghiệm.
- [OpenJDK JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): nguồn gốc tính năng được giới thiệu từ Java 18.
