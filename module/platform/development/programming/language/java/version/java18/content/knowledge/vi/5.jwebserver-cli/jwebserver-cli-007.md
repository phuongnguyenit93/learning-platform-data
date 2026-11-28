# Tác động của bind mọi giao diện đến khả năng truy cập từ mạng và phạm vi dữ liệu được chia sẻ

## 1. Bind quyết định máy nào có thể kết nối tới server

Từ **Java 18**, JDK cung cấp **Simple Web Server** qua lệnh `jwebserver` để phục vụ tài nguyên tĩnh trong quá trình phát triển, thử nghiệm và gỡ lỗi. Công cụ vẫn có trong các JDK hiện đại, bao gồm JDK 27.

Khi khởi động server, tùy chọn `-b` hoặc `--bind-address` quyết định địa chỉ local mà tiến trình lắng nghe. Địa chỉ bind ảnh hưởng trực tiếp đến phạm vi giao diện mạng có thể nhận kết nối.

```sh
# Chỉ nhận kết nối IPv4 loopback từ chính máy:
jwebserver -b 127.0.0.1 -p 8080 -d ./public

# Nhận kết nối qua mọi giao diện IPv4:
jwebserver -b 0.0.0.0 -p 8080 -d ./public
```

Hai lệnh đều phục vụ cùng thư mục `./public` trên cổng `8080`. Khác biệt nằm ở **phạm vi mạng có thể tiếp cận**:

- `127.0.0.1` là IPv4 loopback, chỉ dành cho kết nối quay về chính máy.
- `0.0.0.0` là địa chỉ wildcard IPv4; khi dùng làm địa chỉ bind, server lắng nghe trên các giao diện IPv4 phù hợp của máy.

Bind mọi giao diện **không tự động đồng nghĩa server có thể truy cập từ Internet**. Kết nối thực tế còn phụ thuộc địa chỉ IP, định tuyến, firewall, cấu hình mạng Wi-Fi/LAN, VPN, NAT và các chính sách bảo mật của máy chủ hoặc mạng.

> **Phạm vi sử dụng:** Simple Web Server phục vụ tệp tĩnh qua HTTP/1.1, phù hợp cho phát triển, thử nghiệm và gỡ lỗi. Công cụ không cung cấp HTTPS, xác thực người dùng hay xử lý nghiệp vụ web động; không dùng làm máy chủ production hoặc mở ra mạng công cộng.

## 2. Mô hình kết nối: bind, port, firewall và client

Có thể hình dung đường đi của một request trong mạng nội bộ:

```text
Thiết bị client
192.168.1.40
      |
      | HTTP GET http://192.168.1.25:8080/
      v
Wi-Fi / LAN / router / switch
      |
      | Định tuyến và firewall cho phép?
      v
Máy chạy jwebserver
192.168.1.25
      |
      | Listener 0.0.0.0:8080
      v
Document root: ./public
      |
      +--> index.html
      +--> css/app.css
      +--> images/logo.png
```

Một kết nối thành công cần đồng thời thỏa các điều kiện:

1. **Server đang chạy** và lắng nghe trên cổng dự kiến.
2. **Địa chỉ bind phù hợp** với địa chỉ mà client dùng để truy cập.
3. Máy client có đường mạng tới máy chủ; hai máy có thể liên lạc qua LAN hoặc một mạng được định tuyến.
4. Firewall trên máy chủ, router hoặc thiết bị trung gian không chặn kết nối.
5. Client dùng đúng địa chỉ IP, cổng và đường dẫn HTTP.

Vì vậy, nếu một thiết bị khác không mở được trang, đừng vội kết luận lỗi do `jwebserver`. Hãy kiểm tra listener, địa chỉ IP, đường định tuyến và firewall theo từng bước.

## 3. Phân biệt loopback, địa chỉ cụ thể và wildcard

| Địa chỉ bind | Ý nghĩa | Phạm vi lắng nghe |
| --- | --- | --- |
| `127.0.0.1` | IPv4 loopback | Chỉ kết nối quay về máy hiện tại qua IPv4. |
| `::1` | IPv6 loopback | Chỉ kết nối quay về máy hiện tại qua IPv6. |
| `192.168.1.25` | Một địa chỉ IPv4 cụ thể được gán cho máy | Chỉ giao diện/địa chỉ IPv4 đó. |
| `0.0.0.0` | IPv4 wildcard | Các giao diện IPv4 phù hợp của máy. |
| `::` | IPv6 unspecified/wildcard | Các giao diện IPv6 phù hợp; khả năng nhận IPv4 còn tùy dual-stack của hệ điều hành/socket. |

### 3.1. Loopback: kiểm thử tại máy

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public
```

Truy cập từ chính máy chủ:

```text
http://127.0.0.1:8080/
```

Thiết bị khác không thể dùng `127.0.0.1` để truy cập server trên máy chủ. Địa chỉ loopback trên thiết bị client luôn trỏ về **chính client đó**.

Với IPv6 loopback:

```sh
jwebserver -b ::1 -p 8080 -d ./public
```

URL phải đặt địa chỉ IPv6 trong ngoặc vuông:

```text
http://[::1]:8080/
```

### 3.2. Bind vào một địa chỉ LAN cụ thể

Giả sử máy chủ có địa chỉ IPv4 LAN `192.168.1.25`, được gán cho giao diện Wi-Fi. Có thể giới hạn listener vào địa chỉ này:

```sh
jwebserver -b 192.168.1.25 -p 8080 -d ./public
```

Thiết bị khác trong LAN truy cập:

```text
http://192.168.1.25:8080/
```

Địa chỉ trên chỉ là ví dụ. Phải thay bằng địa chỉ thật được gán cho máy chủ. Nếu địa chỉ không thuộc máy hoặc giao diện không hoạt động, thao tác bind có thể thất bại với lỗi như `Cannot assign requested address`.

Bind vào một địa chỉ cụ thể thường giúp thu hẹp phạm vi so với wildcard. Tuy nhiên, nó không thay thế firewall và không tự xác thực client.

### 3.3. Bind mọi giao diện IPv4

```sh
jwebserver -b 0.0.0.0 -p 8080 -d ./public
```

`0.0.0.0` có nghĩa là lắng nghe trên các giao diện IPv4 phù hợp, có thể gồm:

- Wi-Fi hoặc Ethernet đang kết nối LAN.
- Giao diện loopback IPv4.
- Giao diện VPN hoặc giao diện mạng ảo.
- Giao diện khác có địa chỉ IPv4 mà hệ điều hành cho phép bind.

Client từ xa phải dùng **địa chỉ IPv4 thật của máy chủ**, không dùng `0.0.0.0` làm host trong URL. Ví dụ, nếu máy chủ có địa chỉ LAN `192.168.1.25`, client dùng `http://192.168.1.25:8080/`.

### 3.4. Bind mọi giao diện IPv6

```sh
jwebserver -b :: -p 8080 -d ./public
```

`::` là địa chỉ unspecified/wildcard IPv6, khác với `::1` là loopback. Server lắng nghe trên các giao diện IPv6 phù hợp.

Một số hệ điều hành/cấu hình socket có thể cho phép IPv6 wildcard nhận cả kết nối IPv4-mapped (dual-stack); cấu hình khác chỉ nhận IPv6. **Không giả định bind `::` luôn mở cả IPv4 lẫn IPv6.** Hãy kiểm tra hai họ địa chỉ riêng biệt nếu ứng dụng cần cả hai.

URL IPv6 dùng địa chỉ thực của máy trong dấu ngoặc vuông, ví dụ dạng minh họa:

```text
http://[2001:db8::25]:8080/
```

Dải `2001:db8::/32` dành cho tài liệu, không phải địa chỉ Internet công cộng để dùng thực tế. Hãy thay bằng địa chỉ IPv6 đang được gán cho máy và có thể định tuyến từ client.

## 4. Bind mọi giao diện không đồng nghĩa Internet truy cập được

Khi dùng `0.0.0.0`, server lắng nghe trên các giao diện IPv4 của máy. Điều này tạo khả năng nhận kết nối qua các giao diện đó, nhưng **không tự tạo đường truyền từ mọi mạng tới máy chủ**.

Các yếu tố ảnh hưởng:

| Yếu tố | Ảnh hưởng tới kết nối |
| --- | --- |
| Địa chỉ IP trên giao diện | Client phải dùng địa chỉ gắn với giao diện có thể tiếp cận. |
| Định tuyến | Mạng client phải có đường tới mạng chứa máy chủ. |
| Firewall của hệ điều hành | Có thể chặn kết nối inbound tới cổng `8080`. |
| Firewall/router | Có thể chặn hoặc cô lập các thiết bị trong cùng Wi-Fi/LAN. |
| Guest Wi-Fi / client isolation | Có thể ngăn thiết bị khách kết nối trực tiếp với nhau. |
| VPN và giao diện ảo | Có thể tạo thêm đường truy cập hoặc chính sách lọc riêng. |
| NAT | Có thể ngăn kết nối từ bên ngoài vào nếu không có cấu hình chuyển tiếp phù hợp. |

Ví dụ:

- Hai máy trong cùng LAN, cùng subnet và firewall cho phép: client có thể truy cập địa chỉ LAN của máy chủ.
- Máy client nằm trong guest Wi-Fi có client isolation: có thể không truy cập được máy khác dù cùng router.
- Máy chủ ở sau NAT: client ngoài mạng thường không thể tự kết nối trực tiếp bằng địa chỉ private của máy chủ.
- Máy chủ có firewall chặn cổng: listener vẫn có thể xuất hiện ở trạng thái LISTEN nhưng request từ máy khác không tới được ứng dụng.

**Không mở cổng router hoặc tạo port forwarding ra Internet chỉ để thử Simple Web Server.** Nếu cần kiểm tra từ xa, hãy dùng mạng thử nghiệm có kiểm soát và chính sách firewall do người quản trị cho phép.

## 5. Bind quyết định phạm vi mạng; document root quyết định phạm vi dữ liệu

Hai thiết lập này có vai trò khác nhau:

- **Bind address (`-b`):** quyết định các địa chỉ/giao diện local mà client có thể kết nối tới.
- **Document root (`-d`):** quyết định cây thư mục chứa tài nguyên tĩnh mà server có thể phục vụ.

Ví dụ:

```sh
jwebserver -b 0.0.0.0 -p 8080 -d ./public
```

Lệnh trên mở listener IPv4 trên mọi giao diện phù hợp nhưng chỉ chọn `./public` làm gốc tài nguyên. Nếu thư mục có:

```text
project/
├── .git/
├── .env
├── credentials.txt
├── src/
├── target/
└── public/
    ├── index.html
    ├── css/
    │   └── app.css
    └── images/
        └── logo.png
```

và CWD là `project`, dùng `-d ./public` sẽ phục vụ cây `public`. Các tệp ở cấp cha như `.env`, `credentials.txt`, thư mục `src` không thuộc document root này.

Nếu thay bằng:

```sh
jwebserver -b 0.0.0.0 -p 8080 -d .
```

thì gốc phục vụ trở thành toàn bộ `project`. Điều này làm tăng số lượng tệp có thể được truy cập qua HTTP, có thể bao gồm mã nguồn, tài liệu, tệp cấu hình và dữ liệu thử nghiệm.

**Mở rộng bind không tự mở rộng document root**, và thu hẹp document root không thu hẹp số giao diện mạng đang lắng nghe. Cần cấu hình cả hai đúng với mục đích.

### 5.1. Những tài nguyên có thể bị chia sẻ

Simple Web Server là server tĩnh. Client có thể yêu cầu các tệp mà server phục vụ dưới document root, ví dụ:

- HTML, CSS, JavaScript và hình ảnh.
- JSON hoặc dữ liệu mẫu.
- Tài liệu, tệp văn bản và các tệp tĩnh khác được hỗ trợ.

Nếu thư mục được yêu cầu không có tệp index, server có thể hiển thị directory listing. Người truy cập có thể nhìn thấy tên các tệp và thư mục con được liệt kê, sau đó mở tài nguyên phù hợp.

Tài liệu công cụ nêu rằng **tệp ẩn và symbolic link không được phục vụ/liệt kê**. Đây là hành vi của công cụ, không phải chính sách bảo mật đủ mạnh để dựa vào đó. Không đặt bí mật trong document root với giả định rằng tên tệp bắt đầu bằng dấu chấm sẽ luôn được bảo vệ.

### 5.2. Dữ liệu tĩnh không phải API có xác thực

Nếu `public/data/users.json` nằm trong document root, một client có thể gửi GET tới đường dẫn tương ứng nếu kết nối tới server được phép. Server không tự hiểu rằng dữ liệu đó “chỉ dành cho người đang phát triển”, cũng không cung cấp cơ chế đăng nhập hoặc phân quyền theo người dùng.

Tương tự, `jwebserver` không thực thi mã Java phía server, không chạy JSP/Servlet và không xử lý logic nghiệp vụ. Nó phục vụ nội dung tĩnh để kiểm thử giao diện hoặc tài nguyên.

## 6. Thực hành: kiểm tra khả năng truy cập từ một thiết bị khác

### 6.1. Chuẩn bị document root

Tạo cấu trúc:

```text
demo/
└── public/
    ├── index.html
    └── data/
        └── sample.json
```

Tệp `demo/public/index.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kiểm tra truy cập LAN</title>
</head>
<body>
  <h1>Simple Web Server trên mạng thử nghiệm</h1>
  <p>Trang tĩnh được phục vụ từ thư mục public.</p>
</body>
</html>
```

Tệp `demo/public/data/sample.json`:

```json
{
  "environment": "development",
  "message": "Static sample data"
}
```

Không đưa mật khẩu, token, thông tin cá nhân hoặc dữ liệu nội bộ thật vào ví dụ này.

### 6.2. Xác định địa chỉ LAN của máy chủ

Trên Windows PowerShell:

```powershell
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notlike '127.*' } |
  Format-Table IPAddress, InterfaceAlias
```

Trên Linux:

```sh
ip -br address
```

Trên macOS:

```sh
ifconfig
```

Chọn địa chỉ IPv4 thuộc giao diện LAN đang hoạt động, ví dụ `192.168.1.25`. Không dùng `127.0.0.1` hoặc `0.0.0.0` làm địa chỉ đích cho client khác.

### 6.3. Khởi động server trên loopback trước

Trên máy chủ, chạy:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o info
```

Kiểm tra từ chính máy:

```sh
curl -i http://127.0.0.1:8080/
```

Nếu bước này thất bại, kiểm tra CWD, document root, cổng và trạng thái server trước. Chưa cần thử từ thiết bị khác.

### 6.4. Mở bind LAN có kiểm soát

Dừng phiên trước bằng Ctrl+C. Nếu mục tiêu là thử truy cập từ một máy khác trong LAN, có thể bind vào địa chỉ LAN cụ thể:

```sh
jwebserver -b 192.168.1.25 -p 8080 -d ./public -o info
```

Hoặc dùng wildcard IPv4 nếu bạn thực sự cần listener trên mọi giao diện IPv4:

```sh
jwebserver -b 0.0.0.0 -p 8080 -d ./public -o info
```

Trên thiết bị client cùng mạng, mở:

```text
http://192.168.1.25:8080/
```

Thay `192.168.1.25` bằng địa chỉ thật của máy chủ. Có thể kiểm tra JSON:

```sh
curl -i http://192.168.1.25:8080/data/sample.json
```

Nếu server hoạt động tại máy chủ nhưng client không kết nối được, kiểm tra firewall và chính sách mạng. Không tắt toàn bộ firewall để thử; nếu được phép, chỉ tạo quy tắc inbound giới hạn cổng và profile mạng riêng cần thiết, rồi gỡ bỏ sau khi hoàn thành.

### 6.5. Xác nhận listener trên máy chủ

**Windows PowerShell:**

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8080 |
  Select-Object LocalAddress, LocalPort, OwningProcess
```

**Linux:**

```sh
ss -ltnp 'sport = :8080'
```

**macOS:**

```sh
lsof -nP -iTCP:8080 -sTCP:LISTEN
```

Kết quả giúp xác nhận server bind vào địa chỉ cụ thể hay wildcard. Ví dụ:

| Local address | Cách hiểu |
| --- | --- |
| `127.0.0.1:8080` | Listener IPv4 loopback. |
| `192.168.1.25:8080` | Listener trên địa chỉ IPv4 LAN cụ thể. |
| `0.0.0.0:8080` | Listener IPv4 wildcard. |
| `[::1]:8080` | Listener IPv6 loopback. |
| `[::]:8080` | Listener IPv6 wildcard; khả năng nhận IPv4 phụ thuộc cấu hình dual-stack. |

Dừng server bằng Ctrl+C sau khi kiểm tra.

## 7. Rủi ro khi bind mọi giao diện

Khi dùng wildcard, các client trên những mạng có thể định tuyến tới giao diện tương ứng có cơ hội kết nối nếu firewall cho phép. Điều này có thể gồm cả giao diện mà bạn không nghĩ tới lúc đầu như Ethernet, Wi-Fi, VPN, mạng ảo hoặc giao diện container.

Các rủi ro thường gặp:

1. **Chia sẻ nhầm tài liệu:** document root đặt ở thư mục dự án thay vì thư mục `public`, khiến README, mã nguồn hoặc tệp cấu hình có thể được truy cập.
2. **Lộ dữ liệu thử nghiệm:** JSON, log, bản dump hoặc dữ liệu mẫu chứa thông tin thật vẫn có thể bị đọc nếu nằm trong cây phục vụ.
3. **Directory listing:** thư mục không có index có thể hiển thị tên tệp và thư mục con.
4. **Truy cập từ mạng ngoài dự kiến:** wildcard mở listener trên nhiều giao diện, bao gồm VPN hoặc mạng ảo nếu phù hợp.
5. **Thiếu bảo vệ truyền tải:** HTTP không mã hóa; nội dung không được bảo vệ như khi dùng HTTPS.
6. **Không có xác thực:** bất kỳ client nào có thể kết nối tới listener và được mạng/firewall cho phép đều có thể yêu cầu tài nguyên tĩnh.

### 7.1. Cấu hình theo nguyên tắc phạm vi nhỏ nhất

| Mục đích | Cấu hình nên cân nhắc |
| --- | --- |
| Chỉ xem trên máy phát triển | Bind `127.0.0.1` hoặc `::1`. |
| Chia sẻ với một thiết bị trong LAN qua IPv4 | Bind vào địa chỉ IPv4 LAN cụ thể, nếu địa chỉ đó ổn định và đã xác minh. |
| Kiểm thử trên nhiều giao diện IPv4 trong mạng riêng | Chỉ dùng `0.0.0.0` khi thực sự cần; giới hạn bằng firewall và document root. |
| Kiểm thử IPv6 | Chọn địa chỉ IPv6 cụ thể hoặc `::` khi cần wildcard, rồi kiểm tra dual-stack. |
| Triển khai dịch vụ thật | Dùng web server/ứng dụng được thiết kế cho production, có HTTPS, xác thực, logging và kiểm soát truy cập phù hợp. |

Luôn chọn document root nhỏ nhất có thể, ví dụ `./public`, và chỉ chứa các tệp cần chia sẻ. Không dùng thư mục gốc repository nếu chưa kiểm tra kỹ nội dung.

### 7.2. Checklist trước khi mở listener ra LAN

- [ ] Đã xác định chính xác địa chỉ IP và giao diện mạng sẽ nhận kết nối.
- [ ] Đã chọn đúng thư mục `-d`, chỉ chứa tài nguyên được phép chia sẻ.
- [ ] Đã rà soát tệp cấu hình, token, khóa, log, dữ liệu cá nhân và bản sao lưu.
- [ ] Đã hiểu firewall và mạng nào có thể truy cập cổng.
- [ ] Không cấu hình router port forwarding hoặc mở truy cập Internet ngoài mục tiêu thử nghiệm.
- [ ] Có kế hoạch dừng server ngay sau khi kiểm thử.
- [ ] Đã kiểm tra lại listener và URL từ một client được phép.

## 8. Phân biệt các lỗi truy cập mạng

| Triệu chứng | Khả năng nguyên nhân | Bước kiểm tra |
| --- | --- | --- |
| Máy chủ tự truy cập được, client LAN không truy cập được | Bind loopback, firewall chặn hoặc mạng cô lập client. | Kiểm tra địa chỉ listener; xác nhận bind LAN cụ thể/wildcard và chính sách mạng. |
| Listener là `0.0.0.0:8080` nhưng client không kết nối | Firewall, routing, guest isolation hoặc sai IP client dùng. | Xác nhận IP LAN, kiểm tra firewall và kết nối TCP từ client. |
| Client truy cập được trang chủ nhưng nhận `404` ở file JSON | URL sai hoặc file không nằm trong document root. | Đối chiếu `-d` với đường dẫn tài nguyên. |
| Dùng `0.0.0.0` trong trình duyệt không được | Wildcard là địa chỉ bind, không phải địa chỉ đích thông thường. | Dùng IP thật của máy chủ. |
| IPv4 truy cập được nhưng IPv6 không được | Server không bind IPv6 hoặc listener không dual-stack. | Kiểm tra listener IPv6 và thử riêng `curl -6`. |
| Truy cập từ Internet không được dù bind wildcard | NAT, firewall biên hoặc không có route công cộng. | Đây là giới hạn mạng; không tự mở port forwarding chỉ để thử. |
| Người dùng thấy tệp không mong muốn | Document root quá rộng hoặc directory listing cho thấy nội dung. | Dừng server, thu hẹp `-d` và kiểm tra lại cây thư mục. |

## 9. Bài tập tự kiểm tra

1. Chạy `jwebserver -b 127.0.0.1 -p 8080 -d ./public`. Xác nhận client trên máy chủ truy cập được và client LAN không dùng loopback để truy cập máy chủ.
2. Xác định IP LAN của máy, bind vào địa chỉ cụ thể đó và thử từ một thiết bị khác trong cùng mạng.
3. Dừng server, chạy `jwebserver -b 0.0.0.0 -p 8080 -d ./public`. Quan sát listener và so sánh phạm vi với bind địa chỉ LAN cụ thể.
4. Thử truy cập bằng `http://0.0.0.0:8080/` rồi bằng IP LAN thật. Giải thích vì sao chỉ URL thứ hai là địa chỉ đích phù hợp.
5. Thay `-d ./public` bằng `-d .` trong thư mục dự án mẫu. Liệt kê các tài nguyên mới có thể xuất hiện qua HTTP và giải thích rủi ro.
6. Thử một thư mục không có trang index để quan sát directory listing. Vì sao không nên dựa vào việc tệp ẩn bị bỏ qua như một biện pháp bảo mật?
7. Giải thích vì sao bind wildcard không bảo đảm truy cập Internet và liệt kê các lớp mạng có thể chặn kết nối.
8. Dừng server sau khi thử nghiệm và kiểm tra rằng listener trên cổng đã chọn không còn tồn tại.

**Tiêu chí hoàn thành:** bạn giải thích được quan hệ giữa bind address và khả năng kết nối, phân biệt loopback/địa chỉ LAN/wildcard, dùng đúng IP đích, nhận biết vai trò của firewall và routing, đồng thời giới hạn document root để chỉ chia sẻ dữ liệu cần thiết.

## 10. Tài liệu tham khảo

- [Oracle Java SE 27 — The jwebserver Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html): tùy chọn bind, địa chỉ loopback mặc định, wildcard và cách phục vụ thư mục.
- [Oracle Java SE 27 — Module jdk.httpserver](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/module-summary.html): phạm vi và mục đích của Simple Web Server trong JDK.
- [RFC 1122 — Requirements for Internet Hosts: Communication Layers](https://www.rfc-editor.org/rfc/rfc1122): quy ước địa chỉ loopback IPv4.
- [RFC 4291 — IP Version 6 Addressing Architecture](https://www.rfc-editor.org/rfc/rfc4291): địa chỉ loopback và unspecified của IPv6.
- [OpenJDK JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): giới thiệu Simple Web Server từ Java 18.
