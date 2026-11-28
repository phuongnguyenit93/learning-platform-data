# Chọn cổng bằng `-p` hoặc `--port` và chẩn đoán lỗi cổng đã được sử dụng

## 1. Cổng HTTP của Simple Web Server

Từ **Java 18**, JDK cung cấp công cụ **Simple Web Server** qua lệnh `jwebserver` để phục vụ tài nguyên tĩnh trong quá trình phát triển, thử nghiệm và gỡ lỗi. Tính năng này vẫn được hỗ trợ trên JDK hiện đại, bao gồm JDK 27.

Mỗi HTTP server cần một địa chỉ và một cổng để nhận kết nối. Với `jwebserver`, cổng mặc định là **`8000`**. Bạn có thể thay đổi bằng tùy chọn dạng ngắn **`-p`** hoặc dạng dài **`--port`**:

```sh
jwebserver -p 8080
```

Tương đương:

```sh
jwebserver --port 8080
```

Cả hai lệnh đều yêu cầu Simple Web Server lắng nghe trên cổng TCP `8080`, trong khi các tùy chọn khác giữ giá trị mặc định. Khi server khởi động thành công, terminal in ra địa chỉ và cổng thực tế cùng URL để truy cập.

> **Phạm vi:** `jwebserver` phục vụ tệp tĩnh qua HTTP/1.1, thích hợp cho phát triển, thử nghiệm và gỡ lỗi. Công cụ không cung cấp HTTPS, HTTP/2, xác thực hay xử lý nghiệp vụ web động; không dùng làm máy chủ production.

## 2. Cú pháp và cách chọn cổng

Cú pháp chính của công cụ:

```text
jwebserver [-b bind-address] [-p port] [-d directory]
           [-o none|info|verbose] [-h] [-version]
```

| Tùy chọn | Ý nghĩa | Mặc định |
| --- | --- | --- |
| `-p`, `--port` | Cổng TCP mà HTTP server lắng nghe. | `8000` |
| `-b`, `--bind-address` | Địa chỉ mạng server bind vào. | Loopback: `127.0.0.1` hoặc `::1` |
| `-d`, `--directory` | Thư mục gốc phục vụ tài nguyên tĩnh. | Thư mục làm việc hiện tại |
| `-o`, `--output` | Mức log yêu cầu. | `info` |

Giá trị cổng được truyền ngay sau tùy chọn, thường là một số nguyên thập phân. Ví dụ:

```sh
# Cổng 8080:
jwebserver -p 8080

# Cổng 8181 với tên tùy chọn dài:
jwebserver --port 8181

# Chọn cả địa chỉ bind, cổng và thư mục phục vụ:
jwebserver -b 127.0.0.1 -p 8080 -d ./public
```

Cổng `8000` không phải cổng HTTP mặc định của trình duyệt. Khi URL không ghi cổng, HTTP thường ngầm dùng cổng `80`; do đó phải dùng URL có cổng đã chọn, ví dụ `http://127.0.0.1:8080/`.

### 2.1. Chọn cổng phù hợp

Khi phát triển trên máy cá nhân, các cổng như `8000`, `8080` hoặc `8181` thường dễ dùng và không yêu cầu quyền đặc biệt trên các hệ điều hành phổ biến. Hãy kiểm tra xem ứng dụng khác đã dùng cổng dự kiến hay chưa.

Một số nguyên tắc thực tế:

- Dùng một cổng dễ nhận biết và ghi lại trong lệnh chạy, tài liệu hoặc script phát triển.
- Nếu chạy nhiều server cùng lúc, gán mỗi server một cổng khác nhau.
- Tránh chọn cổng thấp cần quyền đặc biệt trên hệ điều hành, trừ khi bạn hiểu rõ yêu cầu và quyền cần thiết.
- Không giả định một cổng luôn rảnh chỉ vì lần chạy trước đã thành công; ứng dụng khác có thể bắt đầu lắng nghe sau đó.
- Nếu cổng mong muốn đang được sử dụng, chọn cổng khác hoặc dừng đúng tiến trình đang chiếm cổng.

Cổng TCP có miền số từ `0` đến `65535`; giá trị `0` thường được dùng ở tầng socket để yêu cầu hệ điều hành chọn một cổng tạm thời. Với bài thực hành CLI này, hãy chọn một cổng cụ thể như `8000`, `8080` hoặc `8181` để dễ đọc URL và kiểm tra. Không dùng số cổng của một dịch vụ khác theo thói quen mà không kiểm tra xung đột.

### 2.2. Phân biệt cổng server với cổng của client

Khi trình duyệt truy cập `http://127.0.0.1:8080/`:

- `8080` là cổng server đang lắng nghe.
- Trình duyệt thường tự dùng một cổng nguồn tạm thời cho kết nối TCP.
- Cổng nguồn tạm thời đó không phải cổng mà bạn truyền bằng `-p`.

Vì vậy, không cần và không nên cố định cổng client của trình duyệt để cấu hình `jwebserver`. Tùy chọn `-p` điều khiển cổng **phía server**.

## 3. Chạy server với cổng được chọn

### 3.1. Ví dụ với cổng 8080

Giả sử bạn có thư mục:

```text
demo/
└── public/
    ├── index.html
    └── style.css
```

Từ thư mục cha của `public`, chạy:

```sh
jwebserver -b 127.0.0.1 -p 8080 -d ./public -o info
```

Nếu thành công, server hiển thị thông tin tương tự:

```text
Serving /path/to/demo/public and subdirectories on 127.0.0.1 port 8080
URL http://127.0.0.1:8080/
```

Đường dẫn tuyệt đối và nội dung log thực tế có thể khác theo hệ điều hành và phiên bản JDK. Hãy sử dụng URL mà terminal in ra. Mở `http://127.0.0.1:8080/` trong trình duyệt.

Kiểm tra từ terminal thứ hai:

```sh
# Xem HTTP status, header và body:
curl -i http://127.0.0.1:8080/

# Kiểm tra một tài nguyên con:
curl -I http://127.0.0.1:8080/style.css
```

Khi server đang chạy, terminal thứ nhất ghi log yêu cầu theo mức `info`. Nhấn **Ctrl+C** trong terminal đó để dừng server.

### 3.2. Dùng cổng khác khi chạy song song

Nếu một server khác đang dùng cổng `8080`, có thể chọn `8181`:

```sh
jwebserver -b 127.0.0.1 -p 8181 -d ./public
```

Truy cập:

```text
http://127.0.0.1:8181/
```

Hai tiến trình có thể phục vụ các website khác nhau trên cùng máy nếu chúng bind vào các địa chỉ/cổng không xung đột. Khi dùng cùng địa chỉ bind và cùng cổng, thông thường chỉ một tiến trình có thể lắng nghe tại endpoint đó.

### 3.3. Dùng tên tùy chọn dài

Lệnh sau có cùng ý nghĩa với ví dụ đầu tiên:

```sh
jwebserver --bind-address 127.0.0.1 --port 8080 --directory ./public --output info
```

Dạng dài hữu ích khi đọc script vì tên tùy chọn mô tả mục đích rõ hơn. Dạng ngắn thường tiện khi gõ trực tiếp trong terminal.

### 3.4. Nếu chạy qua module Java

Simple Web Server cũng có thể được khởi chạy bằng module `jdk.httpserver`:

```sh
java -m jdk.httpserver -p 8080
```

Đặt tùy chọn `-p 8080` **sau tên module** để đối số được chuyển cho chương trình Simple Web Server. Nếu viết `java -p 8080 -m jdk.httpserver`, Java launcher hiểu `-p` là tùy chọn `--module-path`, không phải cổng HTTP.

## 4. Hiểu lỗi cổng đã được sử dụng

Một tình huống phổ biến là khởi chạy:

```sh
jwebserver -p 8080
```

nhưng server không thể bind cổng. Thông báo lỗi có thể chứa nội dung như:

```text
java.net.BindException: Address already in use
```

Thông điệp chính là **địa chỉ/cổng mà server muốn lắng nghe đã không thể được bind**. Nguyên nhân thường gặp:

1. Một phiên `jwebserver` khác vẫn đang chạy trên cùng địa chỉ và cổng.
2. Một ứng dụng khác như web server, IDE, container hoặc tiến trình phát triển frontend đã chiếm cổng.
3. Một tiến trình khác bind vào địa chỉ wildcard, khiến địa chỉ cụ thể mà server muốn dùng bị xung đột.
4. Bạn khởi chạy lại server trong terminal khác mà quên dừng phiên trước.

### 4.1. Vì sao hai server cùng cổng có thể xung đột?

Một endpoint TCP được xác định bởi địa chỉ IP và cổng. Nếu hai tiến trình cùng cố lắng nghe trên cùng endpoint, hệ điều hành thường từ chối lần bind sau. Trường hợp một tiến trình bind wildcard như `0.0.0.0` có thể ảnh hưởng đến bind trên địa chỉ IPv4 cụ thể của cùng máy.

Ví dụ:

```text
Server A: 127.0.0.1:8080  -> đang lắng nghe
Server B: 127.0.0.1:8080  -> xung đột
```

Nếu Server A đang chạy ở cổng `8080`, có thể để A tiếp tục và chạy B trên cổng `8181`:

```sh
jwebserver -p 8181
```

Việc bind vào một địa chỉ IP khác có thể tạo endpoint riêng trong một số cấu hình, nhưng cần hiểu rõ giao diện mạng và wildcard bind. Với bài thực hành thông thường, chọn cổng khác là cách đơn giản nhất.

## 5. Tìm tiến trình đang chiếm cổng

Trước tiên, xác định chính xác cổng gây lỗi. Ví dụ dưới đây kiểm tra cổng `8080`. Các lệnh chỉ đọc trạng thái socket và thông tin tiến trình; chúng không tự dừng ứng dụng.

### 5.1. Windows PowerShell

Có thể dùng `Get-NetTCPConnection` để tìm kết nối ở trạng thái lắng nghe:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8080 |
  Select-Object LocalAddress, LocalPort, OwningProcess
```

Cột `OwningProcess` là PID của tiến trình sở hữu socket. Tra cứu tên tiến trình bằng PID vừa tìm được:

```powershell
Get-Process -Id 1234
```

Thay `1234` bằng PID thực tế. Nếu cmdlet `Get-NetTCPConnection` không có trong môi trường của bạn, có thể dùng:

```powershell
netstat -ano -p TCP | findstr ":8080" | findstr "LISTENING"
```

Cột cuối của kết quả `netstat -ano` là PID. Kiểm tra PID bằng `Get-Process` trước khi quyết định hành động.

### 5.2. Linux

Dùng `ss` để xem socket TCP đang lắng nghe tại cổng:

```sh
sudo ss -ltnp 'sport = :8080'
```

Các cột cho biết trạng thái, địa chỉ/cổng local và thông tin tiến trình (nếu quyền hiện tại cho phép xem). Có thể bỏ `sudo` khi thông tin tiến trình đã hiển thị đầy đủ cho tài khoản hiện tại:

```sh
ss -ltnp 'sport = :8080'
```

Nếu hệ thống không có `ss`, có thể kiểm tra bằng `lsof` nếu đã cài:

```sh
sudo lsof -nP -iTCP:8080 -sTCP:LISTEN
```

### 5.3. macOS

Trên macOS, `lsof` thường có sẵn:

```sh
lsof -nP -iTCP:8080 -sTCP:LISTEN
```

Nếu không thấy thông tin tiến trình do giới hạn quyền, thử chạy với quyền phù hợp:

```sh
sudo lsof -nP -iTCP:8080 -sTCP:LISTEN
```

Kết quả thường cho biết tên tiến trình, PID và socket đang lắng nghe.

### 5.4. Đọc kết quả trước khi xử lý

| Thông tin | Cần xác định |
| --- | --- |
| Local address | Tiến trình bind vào `127.0.0.1`, `::1`, địa chỉ IP cụ thể hay wildcard? |
| Local port | Có đúng cổng `8080` mà bạn muốn dùng không? |
| PID | Tiến trình nào sở hữu socket? |
| Process name | Đó có phải phiên `jwebserver` cũ, IDE, web server hoặc dịch vụ khác không? |
| Trạng thái | Có đang là `LISTEN`/`LISTENING` không? |

Chỉ từ số cổng không thể kết luận tiến trình nào an toàn để dừng. Hãy xác định PID và tên ứng dụng, sau đó kiểm tra bạn có quyền và có chủ đích dừng ứng dụng đó hay không.

## 6. Khắc phục lỗi cổng đã được sử dụng

Sau khi xác định tiến trình, chọn cách xử lý phù hợp:

### Trường hợp A: phiên jwebserver cũ vẫn đang chạy

Nếu đó là terminal bạn đã mở trước đó, chuyển về terminal này và nhấn **Ctrl+C**. Sau đó chạy lại lệnh mong muốn:

```sh
jwebserver -p 8080
```

Đây là cách dừng phù hợp cho phiên server do chính bạn khởi chạy tương tác.

### Trường hợp B: tiến trình thuộc ứng dụng khác mà bạn cần giữ

Không cần dừng ứng dụng. Chọn một cổng khác cho Simple Web Server:

```sh
jwebserver -p 8181
```

Dùng URL mới, ví dụ `http://127.0.0.1:8181/`. Nếu cổng `8181` cũng bận, kiểm tra nó theo quy trình tương tự hoặc chọn một cổng khác chưa được sử dụng.

### Trường hợp C: tiến trình thuộc dịch vụ bạn quản lý

Dùng cơ chế dừng bình thường của chính ứng dụng/dịch vụ đó, ví dụ nút Stop trong IDE, lệnh dừng server của dự án hoặc trình quản lý dịch vụ của hệ điều hành. Sau khi dừng, kiểm tra lại trạng thái LISTEN trước khi chạy `jwebserver`.

Không nên kết thúc một PID chỉ vì nó đang chiếm cổng. PID có thể thuộc dịch vụ hệ thống, ứng dụng khác của bạn hoặc tiến trình dùng chung. Chỉ dừng tiến trình sau khi xác định đúng chủ sở hữu và hiểu ảnh hưởng của thao tác.

### Trường hợp D: không thể giải phóng cổng

Nếu không có quyền dừng tiến trình, hoặc cổng do một dịch vụ dùng chung quản lý, hãy chọn cổng khác trong phạm vi được phép. Không cần thay đổi cấu hình hệ thống chỉ để hoàn thành một bài thử nghiệm tệp tĩnh.

## 7. Phân biệt các thông báo mạng thường gặp

Không phải mọi lỗi khởi động đều có nghĩa là cổng bị chiếm.

| Thông báo/triệu chứng | Ý nghĩa có thể có | Hướng kiểm tra |
| --- | --- | --- |
| `Address already in use` | Địa chỉ/cổng cần bind đang xung đột. | Tìm socket LISTEN và PID bằng công cụ hệ điều hành. |
| `Cannot assign requested address` | Địa chỉ bind được chỉ định không thuộc giao diện mạng hiện có hoặc hiện không thể gán cho máy. | Kiểm tra địa chỉ IP của máy; thử địa chỉ loopback phù hợp hoặc một địa chỉ đang được gắn trên giao diện mạng. |
| `Permission denied` hoặc `Access is denied` | Tiến trình không có quyền bind địa chỉ/cổng hoặc bị chính sách hệ thống chặn. | Kiểm tra cổng, quyền và chính sách; thử một cổng phát triển thông thường như `8080`. |
| `UnknownHostException` hoặc lỗi phân giải tên | Địa chỉ bind dạng hostname không phân giải được. | Kiểm tra tên/địa chỉ và thử địa chỉ loopback cụ thể. |
| Server khởi động nhưng trình duyệt không kết nối | URL sai host/cổng, server bind vào địa chỉ khác, hoặc server đã dừng. | Đọc URL trong log, kiểm tra LISTEN và dùng đúng địa chỉ. |
| HTTP `404 Not Found` | Kết nối tới server được nhưng tài nguyên không có trong document root. | Kiểm tra `-d` và đường dẫn URL; đây không phải lỗi chiếm cổng. |
| HTTP `405` hoặc `501` với method ghi | Method đó không được Simple Web Server hỗ trợ như API ghi dữ liệu. | Dùng `GET`/`HEAD` hoặc một backend phù hợp cho nghiệp vụ động. |

Phân biệt **lỗi bind lúc khởi động** với **lỗi HTTP sau khi kết nối** giúp thu hẹp nguyên nhân nhanh hơn. `Address already in use` xảy ra trước khi server sẵn sàng phục vụ; `404` là phản hồi từ một server đã nhận được request.

## 8. Kiểm chứng sau khi khắc phục

Sau khi chọn cổng mới hoặc giải phóng cổng cũ, chạy lại:

```sh
jwebserver -b 127.0.0.1 -p 8181 -d ./public -o info
```

Xác nhận terminal hiển thị địa chỉ và cổng `8181`. Trong terminal thứ hai:

```sh
curl -i http://127.0.0.1:8181/
```

Trên Windows PowerShell, có thể kiểm tra khả năng mở kết nối TCP trước khi gửi HTTP:

```powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 8181
```

Khi `TcpTestSucceeded` là `True`, kết nối TCP tới địa chỉ/cổng đó thành công. Điều này chưa chứng minh nội dung HTTP đúng; tiếp tục dùng trình duyệt hoặc `curl -i` để xác minh status và body.

Nếu muốn xác minh cổng cũ đã được giải phóng, chạy lại lệnh liệt kê socket LISTEN của hệ điều hành. Đừng chỉ dựa vào việc terminal cũ đã đóng; tiến trình khác có thể đã bắt đầu sử dụng cổng đó.

## 9. Bài tập tự kiểm tra

1. Chạy `jwebserver` không tham số và ghi lại cổng mặc định. Sau đó chạy với `-p 8080` và so sánh URL.
2. Viết lại cùng một lệnh bằng `--port`. Giải thích vì sao hai cách viết có cùng tác dụng.
3. Khởi chạy một phiên `jwebserver -p 8080`, để phiên đó tiếp tục chạy rồi mở terminal thứ hai và chạy lại cùng lệnh. Quan sát lỗi bind.
4. Dùng công cụ phù hợp hệ điều hành để tìm PID đang LISTEN trên cổng `8080`. Xác định tên tiến trình mà không dừng nó.
5. Giữ server đầu tiên chạy ở `8080`, chạy server thứ hai ở `8181`. Truy cập cả hai URL và giải thích vì sao hai server có thể cùng hoạt động.
6. So sánh thông báo `Address already in use` với phản hồi HTTP `404 Not Found`. Ở giai đoạn nào mỗi lỗi xuất hiện?

**Tiêu chí hoàn thành:** bạn có thể chọn cổng bằng `-p`/`--port`, đọc URL có cổng, nhận diện lỗi bind, tìm tiến trình LISTEN bằng công cụ của hệ điều hành, xác minh PID trước khi xử lý và kiểm tra lại server sau khi đổi cổng.

## 10. Tài liệu tham khảo

- [Oracle Java SE 27 — The jwebserver Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html): cú pháp `-p`/`--port`, giá trị mặc định và cách khởi chạy Simple Web Server.
- [Oracle Java SE 27 — Module jdk.httpserver](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/module-summary.html): module cung cấp công cụ HTTP server đơn giản trong JDK.
- [Java SE 27 API — BindException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/BindException.html): ý nghĩa lỗi khi socket không thể bind vào địa chỉ/cổng do xung đột.
- [OpenJDK JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): nguồn gốc Simple Web Server từ Java 18.
