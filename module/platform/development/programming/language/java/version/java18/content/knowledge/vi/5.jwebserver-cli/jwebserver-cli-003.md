# Mặc định thư mục hiện tại, cổng 8000 và địa chỉ loopback khi khởi động máy chủ

## 1. Ba giá trị mặc định cần nắm vững

Từ **Java 18**, JDK cung cấp **Simple Web Server** qua lệnh `jwebserver` để phát triển, thử nghiệm và gỡ lỗi **tài nguyên tĩnh** như HTML, CSS, JavaScript, ảnh và JSON. Tính năng này vẫn được hỗ trợ trong JDK hiện đại; tài liệu **Oracle Java SE 27** xác nhận ba giá trị mặc định khi bạn chỉ gõ:

```sh
jwebserver
```

| Thuộc tính | Giá trị mặc định | Tùy chọn thay đổi |
| --- | --- | --- |
| **Thư mục phục vụ** | **Thư mục làm việc hiện tại (current working directory, CWD)** tại thời điểm khởi chạy. | `-d`, `--directory` |
| **Cổng HTTP** | **`8000`**. | `-p`, `--port` |
| **Địa chỉ bind** | **Loopback: `127.0.0.1` hoặc `::1`**, tùy hệ thống. | `-b`, `--bind-address` |

Công cụ còn có hai mặc định liên quan: **chạy foreground** trong terminal và ghi log yêu cầu ở mức **`info`**. Dùng **Ctrl+C** để dừng.

**Phạm vi:** `jwebserver` phục vụ tệp tĩnh qua HTTP/1.1 và xử lý yêu cầu `GET`/`HEAD`. Công cụ không cung cấp HTTPS, HTTP/2, xác thực hoặc backend xử lý dữ liệu động. Không dùng làm máy chủ production.

## 2. “Thư mục hiện tại” chính xác là thư mục nào?

### 2.1. CWD được lấy từ terminal hoặc tiến trình khởi động

**Current working directory** là thư mục mà tiến trình đứng tại thời điểm khởi động. Nó không mặc định là thư mục cài JDK, thư mục chứa executable `jwebserver`, thư mục chứa tệp `.java`, hay thư mục gốc dự án trong IDE.

Ví dụ cấu trúc:

```text
workspace/
├── notes.txt
├── private-config.txt
└── website/
    ├── index.html
    ├── assets/
    │   └── style.css
    └── data/
        └── products.json
```

Nếu terminal đang đứng tại `workspace/website`, lệnh `jwebserver` phục vụ thư mục `website`. Nếu terminal đang đứng tại `workspace`, chính thư mục **`workspace`** được chọn; lúc này các tệp khác trong cây thư mục của nó có nguy cơ bị phục vụ ngoài ý muốn.

Kiểm tra vị trí trên **Windows PowerShell**:

```powershell
Get-Location
Set-Location .\website
Get-Location
jwebserver
```

Kiểm tra vị trí trên **Linux/macOS (sh, bash, zsh)**:

```sh
pwd
cd ./website
pwd
jwebserver
```

Các lệnh trên giả sử bạn bắt đầu tại thư mục `workspace` đã có sẵn `website`. Khi server được chạy từ script, IDE, terminal tích hợp hoặc một công cụ tự động hóa, hãy kiểm tra **working directory của công cụ đó**. Vị trí tệp script không nhất thiết là CWD.

### 2.2. CWD là gốc của đường dẫn URL

Nếu CWD là `workspace/website`, hãy hình dung ánh xạ:

```text
HTTP request URL              Tài nguyên tương ứng dưới document root
-----------------------------------------------------------------------
/                             ./index.html (nếu tồn tại trang index)
/assets/style.css             ./assets/style.css
/data/products.json           ./data/products.json
/khong-co.html                không có tệp tương ứng -> HTTP 404
```

Dấu `/` đầu URL đại diện cho **gốc của cây thư mục đang phục vụ**, không phải ổ đĩa hoặc thư mục gốc của hệ điều hành. Nếu yêu cầu trỏ đến một thư mục có tệp index, server phục vụ trang index. Nếu không có trang index, server có thể trả về một **directory listing** dạng HTML liệt kê tệp và thư mục con.

Tài liệu `jwebserver` nêu rằng tệp ẩn và symbolic link không được liệt kê hay phục vụ. Tuy vậy, đây không phải giải pháp kiểm soát truy cập hoàn chỉnh: nên chọn CWD chỉ chứa tài nguyên công khai cho bài kiểm thử.

## 3. Cổng mặc định 8000

Một URL HTTP thông thường gồm giao thức, địa chỉ, cổng và đường dẫn:

```text
http://127.0.0.1:8000/assets/style.css
       ^^^^^^^^^ ^^^^ ^^^^^^^^^^^^^^^^^
         địa chỉ  cổng     đường dẫn
```

Khi `jwebserver` chạy với mặc định trên IPv4 loopback, bạn truy cập:

```text
http://127.0.0.1:8000/
```

**Cần ghi rõ `:8000`.** Nếu nhập `http://127.0.0.1/` mà không có cổng, trình duyệt sẽ dùng cổng HTTP mặc định `80`; đó là **đích khác** và không xác minh được server đang chạy trên `8000`.

Nếu port `8000` đã có tiến trình lắng nghe trên địa chỉ cần bind, server có thể báo lỗi và không khởi động được. Bạn có thể đổi cổng:

```sh
jwebserver -p 8181
```

Lúc này, nếu các tùy chọn khác vẫn mặc định, server vẫn dùng CWD và loopback nhưng cổng chuyển thành `8181`. Địa chỉ truy cập phải có `:8181`. Trên một máy có nhiều giao diện và họ địa chỉ, việc xác định cổng đang bị chiếm cần xét đúng **địa chỉ bind cùng cổng**, không chỉ nhìn số cổng.

## 4. Loopback mặc định: 127.0.0.1 hoặc ::1

**Loopback** là địa chỉ dùng để một ứng dụng kết nối về chính máy đang chạy. Hai địa chỉ phổ biến:

| Địa chỉ | Họ địa chỉ | Ý nghĩa |
| --- | --- | --- |
| `127.0.0.1` | IPv4 | Kết nối trở về máy hiện tại qua IPv4 loopback. |
| `::1` | IPv6 | Kết nối trở về máy hiện tại qua IPv6 loopback. |
| `localhost` | Tên host | Có thể được phân giải sang loopback IPv4 hoặc IPv6, tùy hệ điều hành. |
| `0.0.0.0` | IPv4 wildcard | Khi dùng làm địa chỉ **bind**, lắng nghe trên các giao diện IPv4; **không phải loopback**. |

Theo tài liệu Oracle, **địa chỉ bind mặc định là `127.0.0.1` hoặc `::1`**. Điều này không có nghĩa server luôn lắng nghe **đồng thời** cả hai họ địa chỉ. Nếu hệ thống phân giải `localhost` thành địa chỉ khác họ với địa chỉ đã bind, `http://localhost:8000/` có thể không kết nối được, trong khi URL chính xác được server in ra vẫn hoạt động.

Với IPv6 loopback, URL dùng **ngoặc vuông** quanh địa chỉ:

```text
http://[::1]:8000/
```

Đừng tự đoán địa chỉ. Hãy **đọc URL được in khi server khởi động** rồi sử dụng đúng URL đó trong trình duyệt hoặc công cụ HTTP.

### Vì sao máy khác không kết nối được theo mặc định?

Nếu bạn chạy server trên máy A, địa chỉ `127.0.0.1` của **máy B** vẫn trỏ về **máy B**. Tương tự với `::1`. Vì vậy, mặc định loopback cho phép kiểm thử HTTP trên cùng máy và **không mở server tới các thiết bị khác trong LAN**.

Đây là cấu hình phù hợp để học và gỡ lỗi tại máy cá nhân. Nếu cố ý mở server cho mạng thử nghiệm, bạn phải chọn địa chỉ bind khác và cân nhắc rủi ro tiết lộ tài nguyên; nội dung này được giải thích ở mục 7.

## 5. Ví dụ thực hành từ thư mục sạch

### 5.1. Chuẩn bị tài nguyên

Tạo thư mục `demo-site` với cấu trúc:

```text
demo-site/
├── index.html
└── assets/
    └── app.css
```

Tệp `demo-site/index.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Thử mặc định jwebserver</title>
  <link rel="stylesheet" href="/assets/app.css">
</head>
<body>
  <h1>Simple Web Server đã khởi động</h1>
  <p>Trang đang được phục vụ từ thư mục làm việc hiện tại.</p>
</body>
</html>
```

Tệp `demo-site/assets/app.css`:

```css
body {
  font-family: system-ui, sans-serif;
  max-width: 44rem;
  margin: 3rem auto;
}
```

### 5.2. Khởi động mà không truyền tùy chọn

Mở terminal, di chuyển tới **thư mục `demo-site`**, kiểm tra bằng `pwd` (Linux/macOS) hoặc `Get-Location` (PowerShell), rồi chạy:

```sh
jwebserver
```

Nếu thành công, server in **đường dẫn tuyệt đối**, **địa chỉ** và **cổng**. Ví dụ dạng output trên hệ thống dùng IPv4:

```text
Binding to loopback by default. For all interfaces use "-b 0.0.0.0" or "-b ::".
Serving /path/to/demo-site and subdirectories on 127.0.0.1 port 8000
URL http://127.0.0.1:8000/
```

Đây là **ví dụ minh họa**, không phải output cố định. Đường dẫn của bạn sẽ khác; trên hệ thống khác URL có thể dùng địa chỉ IPv6 `[::1]`. Kiểm tra rằng **Serving** trỏ đúng thư mục `demo-site`, **port 8000** được hiển thị, và URL sử dụng địa chỉ loopback.

### 5.3. Kiểm tra trong trình duyệt và bằng curl

Mở **URL mà server đã in**. Nếu đó là `http://127.0.0.1:8000/`, mở terminal thứ hai và chạy:

```sh
# Xem status, header và body của trang chủ:
curl -i http://127.0.0.1:8000/

# Chỉ yêu cầu header của CSS:
curl -I http://127.0.0.1:8000/assets/app.css

# Kiểm tra một tệp không tồn tại:
curl -i http://127.0.0.1:8000/khong-co.html
```

Nếu server in IPv6 `::1`, thay phần địa chỉ trong URL; ví dụ:

```sh
curl -i "http://[::1]:8000/"
```

Trên **Windows PowerShell 5.1**, gọi `curl.exe` thay vì `curl` để tránh alias của `Invoke-WebRequest`.

| Phép kiểm tra | Kết quả thường thấy | Ý nghĩa |
| --- | --- | --- |
| `GET /` | `200 OK` và HTML | `index.html` được lấy từ CWD. |
| `HEAD /assets/app.css` | `200 OK`, có header, không có body | File CSS nằm dưới CWD và server hỗ trợ HEAD. |
| `GET /khong-co.html` | `404 Not Found` | URL không tìm được tài nguyên tương ứng. |
| Truy cập đúng URL in ra | Kết nối được từ máy đang chạy server | Dùng đúng địa chỉ bind và cổng. |
| Terminal server xuất hiện log | Có thông tin request HTTP | Mức log mặc định `info` đang hoạt động. |

Sau khi kiểm tra, nhấn **Ctrl+C** để dừng server. Nếu muốn thử lại với tham số mới, dừng tiến trình cũ trước khi dùng cùng địa chỉ và cổng.

## 6. Thay đổi từng mặc định để hiểu tác dụng

Giả sử terminal hiện đứng ở **thư mục cha của `demo-site`**, không đứng bên trong website. Bảng sau chỉ ra kết quả của mỗi lệnh:

| Lệnh | Gốc phục vụ | Cổng | Bind |
| --- | --- | --- | --- |
| `jwebserver` | Thư mục cha hiện tại | `8000` | Loopback mặc định |
| `jwebserver -d ./demo-site` | `demo-site` | `8000` | Loopback mặc định |
| `jwebserver -p 8181` | Thư mục cha hiện tại | `8181` | Loopback mặc định |
| `jwebserver -b 127.0.0.1` | Thư mục cha hiện tại | `8000` | IPv4 loopback cụ thể |
| `jwebserver -d ./demo-site -p 8181 -b 127.0.0.1` | `demo-site` | `8181` | IPv4 loopback cụ thể |

Chạy ví dụ này từ thư mục cha:

```sh
jwebserver -d ./demo-site -p 8181 -b 127.0.0.1
```

Khi thành công, URL là `http://127.0.0.1:8181/`. Đường dẫn `./demo-site` được hiểu **tương đối với CWD tại thời điểm chạy lệnh**. Với một script hoặc tác vụ chạy tự động từ nhiều thư mục, nên sử dụng đường dẫn tuyệt đối để kết quả nhất quán.

### Cách thứ hai vẫn giữ nguyên ba mặc định

Công cụ cũng được cung cấp qua entry point của module **`jdk.httpserver`**:

```sh
java -m jdk.httpserver
```

Khi dùng cùng JDK và CWD, cách này vẫn mặc định dùng **thư mục hiện tại**, **cổng 8000** và **địa chỉ loopback**. Nếu muốn thay đổi, đặt tùy chọn `-d`, `-p`, `-b` **sau tên module**:

```sh
java -m jdk.httpserver -d ./demo-site -p 8181 -b 127.0.0.1
```

Đây là tùy chọn của Simple Web Server; cần phân biệt với tùy chọn launcher, ví dụ `-p` trước `-m` có nghĩa là module path, không phải cổng HTTP.

## 7. Khi nào cần thay đổi bind ra mạng?

Nếu thực sự cần kiểm tra từ thiết bị khác trong **mạng thử nghiệm tin cậy**, có thể chọn địa chỉ IP cụ thể của giao diện mạng hoặc dùng:

```sh
jwebserver -b 0.0.0.0 -p 8000 -d ./demo-site
```

`0.0.0.0` có nghĩa lắng nghe trên **mọi giao diện IPv4**. Máy khách từ xa phải nhập **địa chỉ IP mạng thực của máy chạy server**, chẳng hạn một địa chỉ nội bộ do mạng cấp, chứ không nhập `0.0.0.0` hoặc loopback. Khả năng kết nối còn phụ thuộc firewall và cấu hình mạng.

Cách này mở rộng phạm vi truy cập; phải rà soát nội dung thư mục phục vụ vì **`jwebserver` không có HTTPS hoặc xác thực**, và một thư mục thiếu trang index có thể hiện directory listing. Đối với kiểm thử trên một máy, **giữ nguyên loopback là lựa chọn thích hợp**.

## 8. Khắc phục các nhầm lẫn thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Trang `/` hiện danh sách tệp lạ | CWD sai hoặc không có trang index trong thư mục được phục vụ. | Đọc đường dẫn sau **Serving**, kiểm tra `pwd`/`Get-Location`, hoặc dùng `-d`. |
| `http://127.0.0.1/` không mở trang | URL thiếu `:8000`, thường đi tới cổng 80. | Dùng đúng cổng từ thông báo khởi động. |
| `localhost:8000` không được nhưng URL in ra được | `localhost` có thể được phân giải sang họ địa chỉ khác với địa chỉ bind. | Dùng chính xác `127.0.0.1` hoặc `[::1]` được in. |
| Máy khác không truy cập qua `127.0.0.1:8000` | Loopback trên máy khác trỏ về máy đó. | Hiểu giới hạn loopback; chỉ mở bind ra mạng nếu có nhu cầu và đã kiểm tra an toàn. |
| Server báo cổng không khả dụng | Địa chỉ/cổng được yêu cầu đã có tiến trình sử dụng hoặc không bind được. | Dừng tiến trình liên quan hoặc thử `-p 8181`. |
| Tệp tồn tại trên máy nhưng URL trả `404` | Tệp không nằm dưới document root hoặc đường dẫn URL sai. | So khớp URL với CWD hoặc `-d` và các thư mục con. |
| Mở HTML bằng `file://` vẫn thấy trang | Trình duyệt đọc tệp trực tiếp, không chứng minh server đang chạy. | Kiểm tra bằng `http://...:8000/` và quan sát HTTP status/log. |
| Lệnh `jwebserver` không được nhận diện | Shell chưa tìm được executable trong `PATH`, hoặc JDK không phù hợp. | Kiểm tra `java --version`, `jwebserver --help`; sử dụng JDK 18+ có module `jdk.httpserver`. |

## 9. Bài tập tự kiểm tra

1. Đứng trong thư mục `demo-site`, chạy `jwebserver` không tham số và ghi lại **document root, cổng, địa chỉ bind** từ output.
2. Dừng server, chuyển lên thư mục cha và chạy lại `jwebserver` không tham số. Giải thích vì sao URL gốc có thể hiển thị nội dung khác.
3. Giữ CWD ở thư mục cha, chạy `jwebserver -d ./demo-site`. So sánh kết quả với bước 1.
4. Đổi sang `-p 8181` và thử URL có cổng `8000` lẫn `8181`. Lưu ý cổng 8000 có thể do tiến trình khác sử dụng.
5. Quan sát server bind `127.0.0.1` hay `::1`, viết URL tương ứng, giải thích vì sao loopback không dùng để truy cập máy khác.
6. Chạy `java -m jdk.httpserver` trong cùng CWD, so sánh ba mặc định với `jwebserver`.

**Tiêu chí hoàn thành:** bạn phân biệt được CWD với thư mục cài JDK, nhận ra tác dụng của cổng `8000`, xác định địa chỉ loopback thực tế, đối chiếu thông báo khởi động với HTTP request và chọn đúng `-d`, `-p`, `-b` khi cần.

## 10. Tài liệu tham khảo

- [Oracle Java SE 27 — The jwebserver Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html): bảng mặc định, thông báo khởi động, cách cấu hình và phạm vi HTTP.
- [Oracle Java SE 27 — Module jdk.httpserver](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/module-summary.html): module cung cấp công cụ và mục đích phát triển/thử nghiệm.
- [OpenJDK JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): nguồn gốc tính năng trong Java 18.
