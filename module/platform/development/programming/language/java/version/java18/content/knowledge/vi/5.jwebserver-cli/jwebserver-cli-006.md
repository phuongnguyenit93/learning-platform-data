# Chọn địa chỉ bằng `-b` hoặc `--bind-address` và phân biệt IPv4 với IPv6 loopback

## 1. Địa chỉ bind của Simple Web Server

Từ **Java 18**, JDK cung cấp công cụ dòng lệnh **Simple Web Server** qua `jwebserver` để phục vụ tài nguyên tĩnh trong quá trình phát triển, thử nghiệm và gỡ lỗi. Tính năng này vẫn được hỗ trợ trên các JDK hiện đại, bao gồm JDK 27.

Khi khởi động server, ngoài cổng TCP và thư mục phục vụ, bạn có thể chọn **địa chỉ mạng mà server lắng nghe** bằng tùy chọn:

- `-b`: dạng ngắn của `--bind-address`.
- `--bind-address`: dạng dài, mô tả rõ mục đích.

Ví dụ:

```sh
jwebserver -b 127.0.0.1 -p 8080
```

Tương đương:

```sh
jwebserver --bind-address 127.0.0.1 --port 8080
```

Ở đây, server lắng nghe trên địa chỉ IPv4 loopback và cổng TCP `8080`. Địa chỉ bind quyết định **giao diện/địa chỉ local của máy mà server nhận kết nối**. Nó khác với địa chỉ client nhập trong trình duyệt và khác với thư mục tài nguyên được chọn bằng `-d`.

Theo tài liệu Java SE 27, mặc định của `jwebserver` là địa chỉ **loopback**, có thể là `127.0.0.1` hoặc `::1` tùy môi trường. Điều đó giới hạn truy cập ở chính máy đang chạy server.

> **Phạm vi:** Simple Web Server phục vụ tệp tĩnh qua HTTP/1.1, thích hợp cho phát triển, thử nghiệm và gỡ lỗi. Công cụ không cung cấp HTTPS, HTTP/2, xác thực hoặc xử lý nghiệp vụ web động; không dùng làm máy chủ production.

## 2. Phân biệt địa chỉ IPv4 và IPv6

IPv4 và IPv6 là hai phiên bản giao thức địa chỉ IP. Một máy có thể có địa chỉ thuộc cả hai họ, tùy cấu hình hệ điều hành và mạng.

| Đặc điểm | IPv4 | IPv6 |
| --- | --- | --- |
| Địa chỉ loopback | `127.0.0.1` (thường dùng nhất) | `::1` |
| Địa chỉ wildcard | `0.0.0.0` | `::` |
| Ví dụ địa chỉ LAN | `192.168.1.25` | `2001:db8::25` (địa chỉ ví dụ thuộc dải tài liệu) |
| Cách viết trong URL | `http://127.0.0.1:8080/` | `http://[::1]:8080/` |

**Loopback** là địa chỉ dùng để một ứng dụng kết nối về chính máy đang chạy. Kết nối đến `127.0.0.1` hoặc `::1` không đi tới máy khác trong LAN.

**Wildcard** là địa chỉ không chỉ một giao diện cụ thể. Khi dùng làm địa chỉ bind, `0.0.0.0` biểu thị mọi giao diện IPv4; `::` là địa chỉ không xác định trong IPv6, thường dùng để lắng nghe trên các giao diện IPv6. Hành vi dual-stack của socket IPv6 có thể phụ thuộc hệ điều hành và cấu hình; **không mặc định rằng bind `::` chắc chắn nhận cả kết nối IPv4**. Hãy kiểm tra bằng client IPv4 và IPv6 riêng biệt nếu cần hỗ trợ cả hai.

### 2.1. Loopback IPv4: 127.0.0.1

Để chỉ nhận kết nối IPv4 từ chính máy:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public
```

Truy cập bằng:

```text
http://127.0.0.1:8080/
```

Máy khác không thể dùng địa chỉ `127.0.0.1` để truy cập server trên máy này, vì loopback của máy khách trỏ về chính máy khách.

### 2.2. Loopback IPv6: ::1

Để chỉ nhận kết nối IPv6 từ chính máy:

```sh
jwebserver -b ::1 -p 8080 -d ./public
```

URL IPv6 phải đặt địa chỉ trong **dấu ngoặc vuông**:

```text
http://[::1]:8080/
```

Dấu ngoặc vuông giúp phân biệt phần địa chỉ IPv6 có nhiều dấu hai chấm với dấu hai chấm dùng để ngăn cách cổng. Không viết `http://::1:8080/`.

### 2.3. Vì sao localhost đôi khi gây nhầm lẫn?

`localhost` là tên host, thường được phân giải thành địa chỉ loopback IPv4, IPv6 hoặc cả hai. Kết quả phụ thuộc cấu hình phân giải tên của hệ thống và thứ tự địa chỉ mà client chọn.

Ví dụ, server chỉ bind vào `127.0.0.1`, nhưng client thử kết nối tới `::1`, kết nối có thể thất bại. Tình huống ngược lại cũng có thể xảy ra khi server chỉ bind IPv6 loopback.

Khi chẩn đoán, hãy dùng địa chỉ IP literal cùng họ với địa chỉ bind:

```sh
# Kiểm tra IPv4 loopback:
curl -4 -i http://127.0.0.1:8080/

# Kiểm tra IPv6 loopback:
curl -6 -i "http://[::1]:8080/"
```

Trên Windows PowerShell 5.1, gọi `curl.exe` nếu `curl` đang là alias của `Invoke-WebRequest`.

## 3. Chọn địa chỉ cụ thể bằng -b hoặc --bind-address

Cú pháp liên quan:

```text
jwebserver [-b bind-address] [-p port] [-d directory]
jwebserver [--bind-address bind-address] [các tùy chọn khác]
```

Giá trị theo sau `-b`/`--bind-address` là **địa chỉ local mà server cần bind**. Có thể dùng địa chỉ IP literal để tránh nhầm lẫn do phân giải tên.

| Lệnh | Phạm vi lắng nghe dự kiến | URL kiểm tra từ chính máy |
| --- | --- | --- |
| `jwebserver -b 127.0.0.1 -p 8080` | IPv4 loopback | `http://127.0.0.1:8080/` |
| `jwebserver -b ::1 -p 8080` | IPv6 loopback | `http://[::1]:8080/` |
| `jwebserver -b 192.168.1.25 -p 8080` | IPv4 cụ thể đã gán cho máy | `http://192.168.1.25:8080/` |
| `jwebserver -b 0.0.0.0 -p 8080` | Mọi giao diện IPv4 | Dùng địa chỉ IPv4 phù hợp của máy |
| `jwebserver -b :: -p 8080` | Wildcard IPv6; dual-stack tùy hệ thống | Kiểm tra `curl -6` và nếu cần cả `curl -4` |

### 3.1. Bind vào một địa chỉ IPv4 cụ thể của máy

Giả sử máy có địa chỉ IPv4 LAN `192.168.1.25`. Nếu địa chỉ này thực sự được gán cho một giao diện đang hoạt động, bạn có thể chạy:

```sh
jwebserver -b 192.168.1.25 -p 8080 -d ./public
```

Thiết bị trong cùng mạng có thể truy cập bằng:

```text
http://192.168.1.25:8080/
```

Địa chỉ `192.168.1.25` chỉ là ví dụ. Hãy thay bằng địa chỉ thật của máy đang chạy server. Nếu bind vào địa chỉ không được gán cho máy, hệ điều hành có thể từ chối thao tác bind, ví dụ báo `Cannot assign requested address`.

Bind vào một địa chỉ giao diện cụ thể giúp giới hạn server ở giao diện đó, phù hợp hơn với việc mở mọi giao diện khi bạn biết chính xác mạng cần dùng. Tuy nhiên, firewall vẫn có thể chặn kết nối đến.

### 3.2. Bind vào mọi giao diện IPv4

```sh
jwebserver -b 0.0.0.0 -p 8080 -d ./public
```

`0.0.0.0` là địa chỉ wildcard IPv4. Nó yêu cầu hệ điều hành lắng nghe trên mọi giao diện IPv4 phù hợp, có thể bao gồm loopback, Ethernet, Wi-Fi và các giao diện ảo.

Máy khách từ xa phải dùng **địa chỉ IPv4 thực của máy chạy server**, không dùng `0.0.0.0` làm URL đích. Vì phạm vi truy cập rộng hơn, hãy kiểm tra document root và firewall trước khi chạy.

### 3.3. Bind IPv6 wildcard

```sh
jwebserver -b :: -p 8080 -d ./public
```

`::` là địa chỉ IPv6 unspecified/wildcard. Nó không giống `::1`: địa chỉ đầu dùng để bind wildcard, địa chỉ sau là loopback.

Một số hệ điều hành có thể cấu hình socket IPv6 wildcard theo chế độ dual-stack và chấp nhận cả IPv4-mapped connections; hệ thống khác hoặc cấu hình khác có thể chỉ nhận IPv6. Hành vi này không nên được suy đoán từ riêng dòng lệnh. Nếu yêu cầu hỗ trợ cả hai họ, hãy thử riêng:

```sh
curl -4 -i http://127.0.0.1:8080/
curl -6 -i "http://[::1]:8080/"
```

Nếu một họ địa chỉ không kết nối được, kiểm tra listener thực tế và cân nhắc chạy server với địa chỉ bind cụ thể phù hợp cho từng trường hợp.

## 4. Xác định địa chỉ IP đang có trên máy

Trước khi bind vào địa chỉ cụ thể, hãy xác nhận địa chỉ đó thực sự được gán cho máy.

### 4.1. Windows PowerShell

```powershell
# Liệt kê các địa chỉ IPv4:
Get-NetIPAddress -AddressFamily IPv4 |
  Format-Table IPAddress, InterfaceAlias, PrefixLength

# Liệt kê các địa chỉ IPv6:
Get-NetIPAddress -AddressFamily IPv6 |
  Format-Table IPAddress, InterfaceAlias, PrefixLength
```

Có thể dùng `ipconfig` để xem nhanh cấu hình các giao diện:

```powershell
ipconfig
```

Chú ý chọn địa chỉ của giao diện cần dùng, ví dụ Wi-Fi hoặc Ethernet. Không chọn địa chỉ loopback nếu mục tiêu là cho thiết bị khác truy cập qua LAN.

### 4.2. Linux

```sh
ip -br address
```

Lệnh hiển thị các giao diện và địa chỉ gắn với chúng. Muốn xem chi tiết hơn:

```sh
ip address show
```

### 4.3. macOS

```sh
ifconfig
```

Tìm giao diện đang hoạt động và địa chỉ IPv4/IPv6 của giao diện đó. Tên giao diện có thể khác nhau giữa các máy; không giả định mọi máy đều dùng cùng một tên.

### 4.4. Phân biệt địa chỉ local, loopback và địa chỉ máy khách

| Loại địa chỉ | Ví dụ | Dùng để |
| --- | --- | --- |
| Loopback IPv4 | `127.0.0.1` | Client trên chính máy kết nối tới server bind IPv4 loopback. |
| Loopback IPv6 | `::1` | Client trên chính máy kết nối tới server bind IPv6 loopback. |
| Địa chỉ LAN IPv4 | `192.168.1.25` | Thiết bị khác trong LAN kết nối tới giao diện IPv4 đó, nếu firewall/mạng cho phép. |
| IPv4 wildcard | `0.0.0.0` | Địa chỉ bind để lắng nghe trên các giao diện IPv4; không dùng làm host trong URL. |
| IPv6 wildcard | `::` | Địa chỉ bind IPv6 unspecified; không dùng làm host đích trong URL. |

## 5. Thực hành: kiểm tra IPv4 và IPv6 loopback

### 5.1. Chuẩn bị thư mục tĩnh

Tạo cấu trúc:

```text
demo/
└── public/
    └── index.html
```

Tệp `demo/public/index.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kiểm tra địa chỉ bind</title>
</head>
<body>
  <h1>jwebserver đang phục vụ trang tĩnh</h1>
  <p>Hãy kiểm tra địa chỉ IPv4 và IPv6 theo cấu hình server.</p>
</body>
</html>
```

### 5.2. Chạy với IPv4 loopback

Đứng trong thư mục `demo`:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o info
```

Trong terminal thứ hai:

```sh
curl -4 -i http://127.0.0.1:8080/
```

Kỳ vọng nhận `200 OK` cùng nội dung HTML. Thử IPv6:

```sh
curl -6 -i "http://[::1]:8080/"
```

Nếu server chỉ bind IPv4, yêu cầu IPv6 không kết nối được. Đây là khác biệt họ địa chỉ, không phải lỗi nội dung HTML.

Dừng server bằng Ctrl+C trước khi chuyển cấu hình.

### 5.3. Chạy với IPv6 loopback

```sh
jwebserver -b ::1 -p 8080 -d ./public -o info
```

Kiểm tra:

```sh
curl -6 -i "http://[::1]:8080/"
```

Sau đó thử:

```sh
curl -4 -i http://127.0.0.1:8080/
```

Với cấu hình chỉ bind IPv6 loopback, không giả định yêu cầu IPv4 sẽ hoạt động. Dùng đúng URL cùng họ địa chỉ với server.

### 5.4. So sánh kết quả

| Cấu hình server | Kiểm tra IPv4 loopback | Kiểm tra IPv6 loopback |
| --- | --- | --- |
| `-b 127.0.0.1` | Kỳ vọng kết nối thành công | Không kỳ vọng kết nối nếu không có listener IPv6 riêng |
| `-b ::1` | Không kỳ vọng kết nối nếu không có listener IPv4 riêng | Kỳ vọng kết nối thành công |
| `-b 0.0.0.0` | Kỳ vọng lắng nghe IPv4 loopback và các giao diện IPv4 | Không tự suy ra có listener IPv6 |
| `-b ::` | Tùy chế độ dual-stack của hệ điều hành/socket | Kỳ vọng lắng nghe IPv6 theo cấu hình wildcard |

Bảng thể hiện hành vi bind dự kiến; kết quả thực tế cần được xác minh trên hệ điều hành và cấu hình mạng của bạn.

## 6. Xác minh địa chỉ và cổng đang lắng nghe

Sau khi khởi động server, có thể kiểm tra socket LISTEN trên cổng `8080`.

### Windows PowerShell

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8080 |
  Select-Object LocalAddress, LocalPort, OwningProcess
```

`LocalAddress` cho biết địa chỉ local. Ví dụ `127.0.0.1` cho thấy listener IPv4 loopback; `::1` cho thấy listener IPv6 loopback; wildcard có thể xuất hiện dưới dạng `0.0.0.0` hoặc `::`.

### Linux

```sh
ss -ltnp 'sport = :8080'
```

Quan sát cột Local Address:Port. Tùy chọn `-l` giới hạn socket đang lắng nghe, `-t` chọn TCP, `-n` giữ địa chỉ/cổng ở dạng số và `-p` hiển thị tiến trình nếu quyền cho phép.

### macOS

```sh
lsof -nP -iTCP:8080 -sTCP:LISTEN
```

Lệnh hiển thị tiến trình và địa chỉ/cổng TCP đang lắng nghe. Nếu thông tin tiến trình bị ẩn do quyền, hãy dùng tài khoản có quyền xem phù hợp.

Kiểm tra listener giúp phân biệt hai tình huống: server không bind được địa chỉ mong muốn, hoặc server đã bind nhưng client đang dùng sai họ địa chỉ/URL.

## 7. Lỗi thường gặp khi chọn địa chỉ bind

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Cannot assign requested address` | Địa chỉ bind không được gán cho máy hoặc giao diện tương ứng không còn hoạt động. | Kiểm tra địa chỉ bằng `ipconfig`, `ip address` hoặc `ifconfig`; chọn địa chỉ local hiện có. |
| `Address already in use` | Địa chỉ/cổng đã có tiến trình khác lắng nghe. | Kiểm tra listener bằng `Get-NetTCPConnection`, `ss` hoặc `lsof`; chọn cổng khác hoặc dừng đúng tiến trình do bạn quản lý. |
| Server bind IPv4 nhưng truy cập `localhost` thất bại | Client có thể thử IPv6 `::1` trong khi server chỉ bind IPv4. | Dùng `127.0.0.1` hoặc cấu hình bind IPv6 riêng. |
| Server bind IPv6 nhưng truy cập IPv4 thất bại | Listener IPv6 không nhất thiết nhận IPv4; dual-stack phụ thuộc hệ điều hành. | Dùng `[::1]` hoặc cấu hình/kiểm tra listener IPv4 riêng. |
| Truy cập từ máy khác không được | Server chỉ bind loopback, firewall chặn hoặc dùng sai địa chỉ máy chủ. | Bind vào địa chỉ LAN phù hợp; kiểm tra firewall và dùng IP của máy chạy server. |
| URL IPv6 không phân tích được | Thiếu ngoặc vuông quanh địa chỉ IPv6. | Dùng dạng `http://[::1]:8080/`. |
| Server chạy nhưng trả `404` | Document root hoặc đường dẫn tài nguyên sai. | Kiểm tra `-d`, thư mục làm việc và URL. Đây không phải lỗi bind. |

### 7.1. Bind vào địa chỉ không thuộc máy

Ví dụ máy chỉ có `192.168.1.25`, nhưng bạn chạy:

```sh
jwebserver -b 192.168.1.99 -p 8080
```

Nếu `192.168.1.99` không được gán cho máy, thao tác bind có thể thất bại. Không thể dùng `-b` để yêu cầu server nhận một địa chỉ IP tùy ý trên mạng; địa chỉ cụ thể phải thuộc một giao diện local hoặc là địa chỉ wildcard hợp lệ.

### 7.2. Bind wildcard làm phạm vi truy cập rộng hơn

Ví dụ:

```sh
jwebserver -b 0.0.0.0 -p 8080 -d ./public
```

Lệnh này không chỉ nhận kết nối loopback IPv4 mà có thể nhận kết nối tới các địa chỉ IPv4 khác của máy. Nếu máy có Wi-Fi, Ethernet hoặc giao diện VPN, cần hiểu rằng các giao diện phù hợp có thể nằm trong phạm vi lắng nghe.

Đừng dùng wildcard chỉ để “sửa lỗi localhost” khi chưa xác định nguyên nhân. Với kiểm thử tại máy, loopback là lựa chọn hẹp và dễ kiểm soát hơn.

## 8. Lưu ý bảo mật khi mở server ra mạng

Khi bind vào địa chỉ LAN hoặc wildcard, người khác có thể truy cập tài nguyên dưới document root nếu định tuyến và firewall cho phép. Trước khi làm vậy:

- Chọn thư mục chỉ chứa tệp cần chia sẻ; không phục vụ thư mục gốc dự án nếu có cấu hình, khóa, dữ liệu cá nhân hoặc bản sao lưu.
- Ưu tiên bind vào địa chỉ giao diện cụ thể thay vì wildcard khi chỉ cần một mạng.
- Kiểm tra firewall và giới hạn mạng truy cập.
- Dừng server ngay sau khi kết thúc kiểm thử.
- Không truyền dữ liệu nhạy cảm qua HTTP không mã hóa.

Simple Web Server không có cơ chế xác thực người dùng hoặc HTTPS. Vì thế, bind ra mạng chỉ nên dùng trong môi trường thử nghiệm tin cậy và trong thời gian cần thiết.

## 9. Bài tập tự kiểm tra

1. Chạy `jwebserver -b 127.0.0.1 -p 8080`. Dùng `curl -4` kiểm tra IPv4 loopback và giải thích vì sao loopback không truy cập được từ máy khác.
2. Chạy lại bằng `jwebserver -b ::1 -p 8080`. Dùng URL `http://[::1]:8080/` và `curl -6` để kiểm tra.
3. Giải thích sự khác nhau giữa `127.0.0.1`, `::1`, `0.0.0.0` và `::`.
4. Liệt kê địa chỉ IP của máy bằng công cụ hệ điều hành, chọn một địa chỉ LAN thật rồi thử bind vào nó.
5. Bind vào địa chỉ không tồn tại và quan sát lỗi; giải thích vì sao một địa chỉ IP tùy ý không thể được dùng làm địa chỉ local.
6. Chạy `jwebserver -b ::`, kiểm tra riêng kết nối IPv4 và IPv6. Ghi lại kết quả trên hệ điều hành của bạn và giải thích vì sao không thể giả định mọi nền tảng có cùng hành vi dual-stack.
7. Kiểm tra socket LISTEN và đối chiếu địa chỉ local/cổng với tham số đã truyền.

**Tiêu chí hoàn thành:** bạn chọn được địa chỉ bind bằng `-b`/`--bind-address`, phân biệt IPv4/IPv6 loopback và wildcard, viết đúng URL IPv6 có ngoặc vuông, xác minh địa chỉ local đang có và kiểm tra listener thực tế trước khi mở server ra mạng.

## 10. Tài liệu tham khảo

- [Oracle Java SE 27 — The jwebserver Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html): tùy chọn `-b`/`--bind-address`, loopback mặc định và ví dụ bind wildcard.
- [Oracle Java SE 27 — Module jdk.httpserver](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/module-summary.html): module cung cấp Simple Web Server trong JDK.
- [Java SE 27 API — InetAddress](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/InetAddress.html): khái niệm địa chỉ IP, loopback và địa chỉ wildcard.
- [OpenJDK JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): nguồn gốc tính năng được giới thiệu từ Java 18.
