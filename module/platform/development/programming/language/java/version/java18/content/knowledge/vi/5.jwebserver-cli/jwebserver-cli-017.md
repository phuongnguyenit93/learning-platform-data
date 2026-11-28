# Dùng trình duyệt, curl hoặc curl.exe để kiểm tra 200, 404, HEAD và tên tệp có ký tự Unicode

## 1. Mục tiêu của bài thực hành

Từ **Java 18**, JDK cung cấp **Simple Web Server** qua lệnh `jwebserver` để phục vụ một cây thư mục tĩnh trong quá trình phát triển, thử nghiệm và gỡ lỗi. Công cụ vẫn có trên JDK hiện đại, bao gồm JDK 27.

Bài này hướng dẫn kiểm tra một tài nguyên tĩnh bằng ba cách:

- **Trình duyệt:** mở URL và quan sát status trong Network panel.
- **curl trên Linux/macOS:** gửi GET, HEAD và xem response headers.
- **curl.exe trên Windows:** thực hiện các phép thử tương tự trong PowerShell hoặc Command Prompt.

Bạn sẽ kiểm tra bốn tình huống:

1. Tệp tồn tại trả `200 OK`.
2. Tệp không tồn tại trả `404 Not Found`.
3. HEAD trả status và headers nhưng không có response body.
4. Tên tệp có dấu tiếng Việt và khoảng trắng được biểu diễn đúng trong URL bằng percent-encoding UTF-8.

> **Phạm vi:** `jwebserver` chỉ phục vụ tệp tĩnh qua HTTP/1.1 và hỗ trợ GET/HEAD. Công cụ được thiết kế cho phát triển, thử nghiệm và gỡ lỗi; không phải máy chủ production.

## 2. Hiểu các status cần kiểm tra

### 2.1. 200 OK

`200 OK` cho biết server đã xử lý request thành công. Khi GET một tệp tồn tại trong document root, response thường có dạng:

```http
HTTP/1.1 200 OK
Content-type: text/plain
Content-length: 28

Tệp mẫu đang được phục vụ.
```

Header và body thực tế phụ thuộc tệp, MIME mapping và JDK. Điểm cần kiểm tra là status 200 và nội dung có đúng với tệp đã tạo hay không.

### 2.2. 404 Not Found

`404 Not Found` cho biết server không tìm thấy tài nguyên tương ứng với URL hoặc không phục vụ tài nguyên đó.

Ví dụ:

```http
HTTP/1.1 404 Not Found
```

Với GET, response có thể có phần body mô tả lỗi. Không nên phụ thuộc vào nội dung body lỗi vì mục tiêu kiểm tra chính là status code.

Một số nguyên nhân thường gặp:

- Tên tệp bị gõ sai.
- Tệp không nằm dưới document root.
- Sai chữ hoa/chữ thường trên file system phân biệt hoa thường.
- URL chứa khoảng trắng hoặc ký tự Unicode được mã hóa sai.
- Đường dẫn trỏ tới hidden file hoặc symbolic link bị Simple Web Server loại khỏi phạm vi phục vụ.

### 2.3. HEAD

HEAD yêu cầu metadata của tài nguyên tương tự GET nhưng server không gửi response body.

Ví dụ:

```http
HEAD /sample.txt HTTP/1.1
Host: 127.0.0.1:8000
```

Response minh họa:

```http
HTTP/1.1 200 OK
Content-type: text/plain
Content-length: 28
```

Với cùng tài nguyên và điều kiện request, HEAD thường trả status tương ứng với GET. Nếu tệp không tồn tại, HEAD cũng thường trả 404 nhưng không có response body.

**HEAD không phải GET bị ẩn phần body trên terminal.** HEAD là một HTTP method riêng. Client gửi HEAD và server không gửi nội dung response.

## 3. Chuẩn bị document root

Tạo một thư mục thử nghiệm:

```text
jwebserver-demo/
└── public/
    ├── index.html
    ├── sample.txt
    └── tai-lieu.txt
```

Tệp `index.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Kiểm tra jwebserver</title>
</head>
<body>
  <h1>Simple Web Server</h1>
  <p>Trang này dùng để kiểm tra GET, HEAD và status HTTP.</p>
  <a href="/sample.txt">Mở tệp mẫu</a>
</body>
</html>
```

Tệp `sample.txt`:

```text
Tệp mẫu đang được phục vụ.
```

Tệp `tai-lieu.txt`:

```text
Tai lieu khong dau de kiem tra duong dan co ban.
```

Bạn có thể tạo các tệp bằng editor hoặc terminal. Điều quan trọng là giữ đúng tên tệp và lưu chúng dưới thư mục `public`.

### 3.1. Tạo tệp trên Linux/macOS

Từ thư mục `jwebserver-demo`:

```sh
mkdir -p public
printf '%s\n' '<!doctype html><html lang="vi"><head><meta charset="UTF-8"><title>jwebserver</title></head><body><h1>Simple Web Server</h1></body></html>' > public/index.html
printf '%s\n' 'Tệp mẫu đang được phục vụ.' > public/sample.txt
printf '%s\n' 'Tai lieu khong dau de kiem tra duong dan co ban.' > public/tai-lieu.txt
```

### 3.2. Tạo tệp trên Windows PowerShell

Từ thư mục `jwebserver-demo`:

```powershell
New-Item -ItemType Directory -Force -Path '.\public' | Out-Null

$html = @'
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Kiểm tra jwebserver</title>
</head>
<body>
  <h1>Simple Web Server</h1>
</body>
</html>
'@

[System.IO.File]::WriteAllText(
    (Join-Path $PWD 'public\index.html'),
    $html,
    [System.Text.UTF8Encoding]::new($false)
)

[System.IO.File]::WriteAllText(
    (Join-Path $PWD 'public\sample.txt'),
    'Tệp mẫu đang được phục vụ.',
    [System.Text.UTF8Encoding]::new($false)
)
```

Đoạn PowerShell dùng `UTF8Encoding($false)` để ghi UTF-8 không có BOM. Điều này giúp nội dung thử nghiệm dễ dự đoán hơn.

## 4. Khởi động jwebserver

Từ thư mục cha chứa `public`, chạy:

```sh
jwebserver -b 127.0.0.1 -p 8000 -d ./public -o info
```

Ý nghĩa:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `-b 127.0.0.1` | Chỉ lắng nghe trên loopback của máy hiện tại. |
| `-p 8000` | Lắng nghe cổng 8000. |
| `-d ./public` | Chọn document root. |
| `-o info` | Ghi request và status ra terminal. |

Nếu khởi động thành công, server in địa chỉ và thư mục đang phục vụ. URL cơ bản:

```text
http://127.0.0.1:8000/
```

Giữ terminal server mở. Mở terminal thứ hai hoặc trình duyệt để gửi request.

Nếu lệnh `jwebserver` không được nhận diện, kiểm tra JDK đang dùng và PATH:

```sh
java -version
jwebserver -version
```

Không nhầm lỗi không kết nối được với HTTP 404. Nếu server chưa chạy hoặc sai cổng, client không nhận được HTTP response status.

## 5. Kiểm tra bằng trình duyệt

### 5.1. Mở tệp tồn tại

Mở:

```text
http://127.0.0.1:8000/
```

Trang `index.html` được phục vụ. Tiếp theo mở trực tiếp:

```text
http://127.0.0.1:8000/sample.txt
```

Bạn sẽ thấy nội dung của tệp văn bản.

### 5.2. Mở tệp không tồn tại

Mở URL:

```text
http://127.0.0.1:8000/not-found.txt
```

Server trả `404 Not Found`. Trình duyệt có thể hiển thị một trang lỗi hoặc body lỗi do server gửi; giao diện hiển thị không phải cách duy nhất để xác nhận status.

### 5.3. Xem status trong Network panel

Trong Chrome hoặc Edge:

1. Mở Developer Tools bằng `F12` hoặc `Ctrl+Shift+I`.
2. Chọn tab **Network**.
3. Bật **Disable cache** khi DevTools đang mở để tránh dùng response cache cũ.
4. Tải lại trang hoặc nhập URL cần kiểm tra.
5. Chọn request tương ứng trong danh sách.
6. Xem cột **Status** hoặc phần **Headers → General → Status Code**.

Network panel cho biết request URL, method, status code và response headers. Với request GET, chọn tab **Response** để xem nội dung server trả về.

### 5.4. Phân biệt HTTP 404 và lỗi kết nối

Hai tình huống có biểu hiện khác nhau:

| Hiện tượng trong trình duyệt | Ý nghĩa |
| --- | --- |
| Request có status `404` | Đã kết nối tới server và server trả HTTP response 404. |
| Request có status `200` | Server trả response thành công. |
| `(failed)`, `ERR_CONNECTION_REFUSED` | Không thiết lập được kết nối tới server; chưa có HTTP status từ server. |
| Request chuyển hướng rồi thành công | Có response redirect, sau đó trình duyệt gửi request tiếp theo. |

Không kết luận server trả 404 chỉ vì trình duyệt hiện trang “This site can’t be reached”. Lỗi kết nối không phải HTTP response 404.
## 6. Kiểm tra bằng curl trên Linux/macOS

### 6.1. GET tệp tồn tại và xem cả headers/body

```sh
curl -i http://127.0.0.1:8000/sample.txt
```

Tùy chọn `-i` hiển thị response headers cùng response body.

Kết quả mong đợi:

- Status `200 OK`.
- Header `Content-Type` mô tả kiểu dữ liệu.
- Body chứa nội dung `Tệp mẫu đang được phục vụ.`.

### 6.2. GET tệp không tồn tại

```sh
curl -i http://127.0.0.1:8000/not-found.txt
```

Kết quả mong đợi là `404 Not Found`. Nếu có body lỗi, curl sẽ hiển thị sau phần headers.

### 6.3. Gửi HEAD

```sh
curl -I http://127.0.0.1:8000/sample.txt
```

`-I` (hoặc `--head`) khiến curl gửi HTTP HEAD. Kết quả có status và headers nhưng không có response body.

Kiểm tra HEAD tới tệp không tồn tại:

```sh
curl -I http://127.0.0.1:8000/not-found.txt
```

Kết quả mong đợi là status `404`, không có body.

### 6.4. Chỉ in status code

Khi viết script kiểm tra nhiều URL, có thể chỉ lấy status:

```sh
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:8000/sample.txt
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:8000/not-found.txt
```

Trong ví dụ này:

- `-sS` tắt progress meter nhưng vẫn hiển thị thông báo lỗi của curl.
- `-o /dev/null` bỏ body ở phía client.
- `-w` in mã HTTP sau khi request hoàn tất.

Lệnh trên vẫn gửi GET. Việc bỏ body bằng `-o` không biến request thành HEAD.

### 6.5. Dùng verbose để xem request line

```sh
curl -v http://127.0.0.1:8000/sample.txt
```

Trong output verbose:

- Dòng bắt đầu bằng `&gt;` là dữ liệu request curl gửi đi.
- Dòng bắt đầu bằng `&lt;` là status line và headers server gửi về.

Bạn có thể xác nhận request line là GET và response line là `HTTP/1.1 200 OK`.

## 7. Kiểm tra bằng curl.exe trên Windows

### 7.1. Vì sao nên gọi curl.exe?

Windows PowerShell 5.1 có alias tên `curl` trỏ tới `Invoke-WebRequest`. Alias này có cú pháp tham số khác với curl thật.

Để dùng đúng curl, gọi:

```powershell
curl.exe -i http://127.0.0.1:8000/sample.txt
```

Có thể kiểm tra cách PowerShell phân giải tên lệnh:

```powershell
Get-Command curl -All
Get-Command curl.exe
```

PowerShell 7+ không định nghĩa alias `curl` mặc định, nhưng gọi rõ `curl.exe` vẫn giúp ví dụ nhất quán giữa các phiên bản.

### 7.2. GET tệp tồn tại

```powershell
curl.exe -i http://127.0.0.1:8000/sample.txt
```

Xác nhận status `200 OK` và nội dung body.

### 7.3. GET tệp không tồn tại

```powershell
curl.exe -i http://127.0.0.1:8000/not-found.txt
```

Xác nhận status `404 Not Found`.

### 7.4. HEAD tệp tồn tại

```powershell
curl.exe -I http://127.0.0.1:8000/sample.txt
```

Xác nhận status và headers được trả về, không có nội dung tệp.

### 7.5. HEAD tệp không tồn tại

```powershell
curl.exe -I http://127.0.0.1:8000/not-found.txt
```

Xác nhận status `404`. Không có response body.

### 7.6. Chỉ in status code trong PowerShell

```powershell
curl.exe -sS -o NUL -w "HTTP %{http_code}\n" http://127.0.0.1:8000/sample.txt
curl.exe -sS -o NUL -w "HTTP %{http_code}\n" http://127.0.0.1:8000/not-found.txt
```

Trên Windows, `NUL` là thiết bị bỏ dữ liệu tương tự `/dev/null` trên Unix-like systems.

## 8. Hiểu chính xác GET, HEAD và các tùy chọn curl

Các tùy chọn dễ nhầm:

| Lệnh | HTTP method | Kết quả ở phía curl |
| --- | --- | --- |
| `curl -i URL` | GET | In headers và body. |
| `curl -I URL` | HEAD | In headers, không nhận body. |
| `curl -v URL` | GET | In thông tin request/response phục vụ gỡ lỗi; body vẫn được in nếu không chuyển hướng output. |
| `curl -sS -o /dev/null URL` | GET | Gửi GET nhưng bỏ body ở phía client. |
| `curl -X HEAD URL` | Custom method string HEAD | Chỉ thay method string; không tương đương đầy đủ với tùy chọn HEAD chuyên dụng của curl. |

Dùng `-I` khi muốn kiểm tra HEAD. Không cần kết hợp `-X HEAD` với `-I`.

HEAD không gửi body nhưng vẫn có thể có `Content-Length`. Nếu header này xuất hiện, nó mô tả độ dài body mà GET tương ứng sẽ gửi, không phải độ dài body HEAD.
## 9. Kiểm tra tên tệp có dấu tiếng Việt và khoảng trắng

Tên tệp có thể chứa Unicode. Ví dụ:

```text
public/
└── tài liệu.txt
```

Nội dung tệp:

```text
Nội dung tiếng Việt trong tệp có tên Unicode.
```

Khi tạo URL cho tài nguyên này, cần biểu diễn các byte UTF-8 của tên tệp bằng percent-encoding.

### 9.1. Tạo tệp Unicode trên Linux/macOS

Từ thư mục `jwebserver-demo`:

```sh
printf '%s\n' 'Nội dung tiếng Việt trong tệp có tên Unicode.' > 'public/tài liệu.txt'
```

Dấu nháy giúp shell xem toàn bộ tên tệp có khoảng trắng là một đối số duy nhất.

### 9.2. Tạo tệp Unicode trên Windows PowerShell

```powershell
[System.IO.File]::WriteAllText(
    (Join-Path $PWD 'public\tài liệu.txt'),
    'Nội dung tiếng Việt trong tệp có tên Unicode.',
    [System.Text.UTF8Encoding]::new($false)
)
```

Xác nhận tên tệp:

```powershell
Get-ChildItem -LiteralPath '.\public' | Select-Object Name
```

Trên Windows, dùng `-LiteralPath` khi kiểm tra đường dẫn có ký tự đặc biệt để tránh wildcard parsing ngoài ý muốn.

### 9.3. Vì sao URL không giữ nguyên khoảng trắng và Unicode?

URI sử dụng một tập ký tự có quy tắc. Ký tự không được phép xuất hiện trực tiếp trong URI cần được biểu diễn bằng percent-encoding.

Đối với tên Unicode, cách interoperable là:

1. Mã hóa ký tự thành byte UTF-8.
2. Với từng byte cần escape, ghi dấu phần trăm `%` theo sau hai chữ số hexadecimal.

Tên:

```text
tài liệu.txt
```

được biểu diễn trong URL path thành:

```text
t%C3%A0i%20li%E1%BB%87u.txt
```

Trong đó:

- `%C3%A0` biểu diễn ký tự `à` trong UTF-8.
- `%20` biểu diễn khoảng trắng.
- `%E1%BB%87` biểu diễn ký tự `ệ` trong UTF-8.

Vì vậy URL đầy đủ là:

```text
http://127.0.0.1:8000/t%C3%A0i%20li%E1%BB%87u.txt
```

Trình duyệt có thể hiển thị tên Unicode dễ đọc trên thanh địa chỉ, nhưng request URL được gửi qua HTTP dùng biểu diễn đã percent-encode.

### 9.4. Kiểm tra Unicode bằng trình duyệt

Nhập URL sau vào thanh địa chỉ:

```text
http://127.0.0.1:8000/tài%20liệu.txt
```

Trình duyệt chuẩn hóa ký tự Unicode trong URL. Mở Network panel và chọn request để xem Request URL, status và response.

Kết quả mong đợi:

- Status `200 OK`.
- Nội dung response là văn bản trong tệp.
- Request URL biểu diễn các byte Unicode bằng percent-encoding.

Nếu nhận 404, kiểm tra tên tệp trên file system và bảo đảm URL được tạo từ đúng tên đó.

### 9.5. Kiểm tra Unicode bằng curl trên Linux/macOS

Dùng URL đã percent-encode:

```sh
curl -i 'http://127.0.0.1:8000/t%C3%A0i%20li%E1%BB%87u.txt'
```

Kiểm tra HEAD:

```sh
curl -I 'http://127.0.0.1:8000/t%C3%A0i%20li%E1%BB%87u.txt'
```

Kết quả mong đợi lần lượt là GET 200 với body và HEAD 200 không body.

curl có thể tự percent-encode byte ngoài ASCII trong URL được cung cấp. Tuy nhiên, khoảng trắng vẫn phải được URL-encode. Dùng URL percent-encoded tường minh giúp tránh phụ thuộc vào encoding của terminal hoặc shell.

### 9.6. Kiểm tra Unicode bằng curl.exe trong PowerShell

PowerShell có thể tạo path segment đã mã hóa bằng `Uri.EscapeDataString`:

```powershell
$segment = [Uri]::EscapeDataString('tài liệu.txt')
$url = "http://127.0.0.1:8000/$segment"

$segment
curl.exe -i $url
curl.exe -I $url
```

Giá trị của `$segment` mong đợi:

```text
t%C3%A0i%20li%E1%BB%87u.txt
```

`EscapeDataString` phù hợp để mã hóa một path segment. Không dùng `URLEncoder` để mã hóa path segment: `URLEncoder` dành cho HTML form encoding và biểu diễn khoảng trắng bằng dấu `+`, trong khi trong URI path, khoảng trắng được biểu diễn bằng `%20`.

### 9.7. Tránh percent-encode hai lần

Nếu tên đã được mã hóa:

```text
t%C3%A0i%20li%E1%BB%87u.txt
```

không đưa nguyên chuỗi đó vào `EscapeDataString` lần nữa. Ký tự `%` sẽ được mã hóa thành `%25`, dẫn tới URL dạng:

```text
t%25C3%25A0i%2520li%25E1%25BB%2587u.txt
```

Server khi giải mã một lần sẽ nhận chuỗi chứa các ký tự `%C3` thay vì tên Unicode ban đầu, dẫn đến 404.

Quy tắc thực hành:

- Nếu đầu vào là tên tệp Unicode chưa encode, encode đúng một lần.
- Nếu đầu vào đã là URL path percent-encoded, giữ nguyên nó.
- Không trộn lẫn chuỗi đã encode và chuỗi Unicode chưa encode trong cùng một bước.
## 10. Những ký tự đặc biệt khác trong tên tệp

Ngoài dấu tiếng Việt và khoảng trắng, một số ký tự có ý nghĩa đặc biệt trong URI:

| Ký tự | Ý nghĩa trong URI | Cách xử lý khi là dữ liệu của tên tệp |
| --- | --- | --- |
| Khoảng trắng | Không được dùng trực tiếp trong URL curl. | Mã hóa thành `%20`. |
| `#` | Bắt đầu fragment; fragment không được gửi như path tới server. | Mã hóa thành `%23`. |
| `?` | Bắt đầu query string. | Mã hóa thành `%3F`. |
| `%` | Bắt đầu percent-encoding. | Mã hóa thành `%25` nếu là ký tự literal. |
| `+` | Là ký tự hợp lệ trong path; không tự động có nghĩa là khoảng trắng. | Giữ nguyên hoặc percent-encode theo cách tạo URL nhất quán. |

Nếu một tệp có tên `report#1.txt` mà URL được gửi là:

```text
http://127.0.0.1:8000/report#1.txt
```

thì phần `#1.txt` là fragment và không được gửi trong request path. Cần dùng:

```text
http://127.0.0.1:8000/report%231.txt
```

Tương tự, tên có dấu hỏi literal cần mã hóa `?` thành `%3F` để server không hiểu nhầm là query delimiter.

## 11. Unicode filename và khác biệt file system

Một URL Unicode chỉ truy cập thành công khi tên được giải mã khớp với tên trên file system mà server đang dùng.

Những nguyên nhân có thể khiến tên nhìn giống nhau nhưng không khớp:

- Chữ hoa/chữ thường khác nhau trên file system phân biệt case.
- Tên chứa dấu cách thường nhưng URL lại dùng ký tự khoảng trắng khác.
- Dấu tiếng Việt ở dạng Unicode composed hoặc decomposed.
- Shell hoặc terminal truyền chuỗi không đúng encoding.
- Tên tệp có ký tự đặc biệt chưa được percent-encode hoặc đã bị encode hai lần.

Một số file system có quy tắc chuẩn hóa Unicode riêng. Nếu tên hiển thị giống nhau nhưng request vẫn 404, hãy copy đúng tên từ file system hoặc tạo URL bằng cách encode chính chuỗi tên vừa đọc được, thay vì tự gõ lại.

Không nên giả định mọi file system sẽ coi hai chuỗi Unicode tương đương về mặt hiển thị là cùng một tên.

## 12. Kiểm tra nhanh bằng bảng test

Giả sử các tệp `index.html`, `sample.txt` và `tài liệu.txt` đều nằm dưới document root.

| Request | Method | Kết quả mong đợi | Body |
| --- | --- | --- | --- |
| `/` | GET | `200` | Nội dung index. |
| `/sample.txt` | GET | `200` | Nội dung tệp. |
| `/not-found.txt` | GET | `404` | Có thể có body lỗi. |
| `/sample.txt` | HEAD | `200` | Không có body. |
| `/not-found.txt` | HEAD | `404` | Không có body. |
| `/t%C3%A0i%20li%E1%BB%87u.txt` | GET | `200` | Nội dung tệp Unicode. |
| `/t%C3%A0i%20li%E1%BB%87u.txt` | HEAD | `200` | Không có body. |
| `/wrong-name.txt` | GET | `404` | Có thể có body lỗi. |

Status thực tế cần được xác nhận trên server đang chạy. Nếu một URL thư mục thiếu dấu `/` cuối, server có thể trả `301` để chuẩn hóa URL trước khi xử lý index hoặc directory listing.

## 13. Đối chiếu ba cách kiểm thử

| Nhu cầu | Trình duyệt | curl / curl.exe |
| --- | --- | --- |
| Xem nội dung HTML/txt | Mở URL. | GET với `-i`. |
| Kiểm tra 200/404 | Network panel. | `-i` hoặc `-w "%{http_code}"`. |
| Kiểm tra HEAD | Dùng Console fetch cùng origin hoặc công cụ gửi request. | `-I`. |
| Xem response headers | Network → Headers. | `-i`, `-I` hoặc `-v`. |
| Kiểm tra Unicode URL | Nhập tên Unicode vào thanh địa chỉ và xem Request URL. | Percent-encode UTF-8 hoặc tạo segment bằng `Uri.EscapeDataString`. |
| Lặp lại kiểm thử trong script | Khó tự động hóa bằng thao tác tay. | Dễ viết lệnh và kiểm tra status. |

### 13.1. Gửi HEAD bằng Console trong trình duyệt

Nếu trang đang mở từ cùng origin `http://127.0.0.1:8000`, có thể mở DevTools → Console và chạy:

```javascript
fetch("/sample.txt", { method: "HEAD" })
  .then(response => {
    console.log("status:", response.status);
    console.log("content-type:", response.headers.get("content-type"));
    console.log("content-length:", response.headers.get("content-length"));
  });
```

Kết quả cho biết status và một số response headers. HEAD không cung cấp nội dung để đọc trong response body.

Để thử một URL không tồn tại:

```javascript
fetch("/not-found.txt", { method: "HEAD" })
  .then(response => console.log("status:", response.status));
```

Kết quả mong đợi là 404.

## 14. Đọc request log của jwebserver

Với mức log mặc định `info`, terminal server ghi method, request path và status. Ví dụ minh họa:

```text
127.0.0.1 - - [27/Nov/2026:05:00:00 +0000] "GET /sample.txt HTTP/1.1" 200 -
127.0.0.1 - - [27/Nov/2026:05:00:01 +0000] "HEAD /sample.txt HTTP/1.1" 200 -
127.0.0.1 - - [27/Nov/2026:05:00:02 +0000] "GET /not-found.txt HTTP/1.1" 404 -
127.0.0.1 - - [27/Nov/2026:05:00:03 +0000] "GET /t%C3%A0i%20li%E1%BB%87u.txt HTTP/1.1" 200 -
```

Đây là ví dụ minh họa định dạng log; thời gian, path và status phụ thuộc request thực tế. Dùng log để đối chiếu method và status mà trình duyệt hoặc curl quan sát được.

Nếu cần thêm headers và đường dẫn tuyệt đối của tài nguyên, khởi động với:

```sh
jwebserver -b 127.0.0.1 -p 8000 -d ./public -o verbose
```

Mức `verbose` hữu ích khi gỡ lỗi nhưng có thể in thêm thông tin request. Rà soát log trước khi chia sẻ.

## 15. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Trình duyệt báo không kết nối được | Server chưa chạy hoặc sai cổng/bind address. | Kiểm tra startup banner và URL loopback. |
| URL tệp tồn tại nhưng trả 404 | Tệp nằm ngoài document root hoặc tên path sai. | Kiểm tra cây thư mục và request path. |
| GET trả 200 nhưng body không như mong đợi | Đang truy cập nhầm tệp hoặc nội dung tệp chưa được cập nhật. | Xem Response tab hoặc output của `curl -i`. |
| HEAD trả 200 nhưng không có body | Đây là hành vi đúng của HEAD. | Dùng GET nếu cần đọc nội dung. |
| HEAD trả 404 | Tài nguyên không được tìm thấy hoặc không được phục vụ. | Kiểm tra cùng URL bằng GET và xem document root. |
| curl báo URL có khoảng trắng không hợp lệ | Khoảng trắng chưa được percent-encode. | Dùng `%20` hoặc `Uri.EscapeDataString`. |
| Tệp Unicode trả 404 | Tên file hoặc percent-encoding không khớp. | Encode UTF-8 đúng một lần và kiểm tra tên trên file system. |
| URL Unicode bị biến thành chuỗi `%25C3...` | Percent-encoding đã bị thực hiện hai lần. | Dùng chuỗi tên gốc hoặc URL đã encode, không encode lặp. |
| URL có dấu `#` không tìm thấy tệp | Phần sau dấu # là fragment và không được gửi trong path. | Encode ký tự literal thành `%23`. |
| URL có dấu `?` bị xử lý sai | Dấu hỏi mở đầu query string. | Encode ký tự literal thành `%3F`. |
| PowerShell gọi `curl` cho kết quả khác | Windows PowerShell 5.1 có alias `curl`. | Gọi `curl.exe`. |
| DevTools không hiện request mới | Cache hoặc Network panel được mở sau khi request hoàn tất. | Mở DevTools trước, bật Disable cache và reload. |
| Request thư mục trả 301 | URL thư mục thiếu dấu `/` cuối. | Theo redirect hoặc dùng URL có dấu `/`. |
| Log không thấy request | Chọn mức log none hoặc request không tới server này. | Dùng `-o info`, kiểm tra port và URL. |

## 16. Bài tập tự kiểm tra

1. Mở `http://127.0.0.1:8000/` trong trình duyệt. Tìm status của document trong Network panel.
2. Mở một tệp tồn tại và ghi lại status, Content-Type và nội dung body.
3. Mở một URL không tồn tại. Xác nhận Network panel hiển thị 404.
4. Dùng `curl -i` để gửi GET tới tệp tồn tại và tệp không tồn tại. So sánh response.
5. Dùng `curl -I` để gửi HEAD tới cùng hai URL. Xác nhận status và việc không có response body.
6. Dùng `curl -v` để xác định request line và response status line.
7. Tạo tệp `tài liệu.txt` và truy cập từ trình duyệt.
8. Dùng URL `/t%C3%A0i%20li%E1%BB%87u.txt` để GET và HEAD tệp Unicode.
9. Trong PowerShell, dùng `Uri.EscapeDataString` tạo path segment và gửi request bằng `curl.exe`.
10. Tạo tên tệp có ký tự `#`. Truy cập bằng URL đã encode `%23` và giải thích vì sao URL chưa encode không hoạt động.
11. Tạo URL percent-encoded hai lần và quan sát vì sao server không tìm thấy tệp.
12. Đọc request log và đối chiếu method, path, status với kết quả curl.

**Tiêu chí hoàn thành:** bạn dùng được trình duyệt, curl và curl.exe để kiểm tra 200/404; phân biệt GET với HEAD; biết xem status, headers và body; tạo URL đúng cho tên tệp Unicode bằng UTF-8 percent-encoding; xử lý được khoảng trắng và ký tự đặc biệt; và nhận ra lỗi kết nối khác với HTTP 404.

## 17. Tài liệu tham khảo

- [Oracle Java SE 27 — The jwebserver Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html): phạm vi phục vụ tệp tĩnh, HTTP/1.1, GET/HEAD, document root và request logging.
- [RFC 9110 — HTTP Semantics, Section 9.3.2 HEAD](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3.2): semantics của HEAD và quy tắc không gửi response content.
- [RFC 9110 — Section 15.3.1 200 OK](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.3.1): ý nghĩa status 200.
- [RFC 9110 — Section 15.5.5 404 Not Found](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.5): ý nghĩa status 404.
- [RFC 3986 — URI Generic Syntax, Sections 2.1, 2.4 and 2.5](https://www.rfc-editor.org/rfc/rfc3986.html): percent-encoding, thời điểm encode/decode và biểu diễn dữ liệu Unicode bằng UTF-8.
- [curl URL syntax](https://curl.se/docs/url-syntax.html): quy tắc URL của curl, khoảng trắng cần encode và byte ngoài ASCII được percent-encode.
- [curl man page](https://curl.se/docs/manpage.html): các tùy chọn `-i`, `-I`, `-v`, `-o` và `-w`.
- [Microsoft Learn — curl on Windows](https://learn.microsoft.com/en-us/windows/curl/): sử dụng curl trên Windows và lưu ý alias `curl` trong Windows PowerShell 5.1.
- [Chrome DevTools — Network features reference](https://developer.chrome.com/docs/devtools/network/reference): xem status, request URL, method và request/response headers trong Network panel.
- [WHATWG URL Standard](https://url.spec.whatwg.org/): quy tắc percent-encoding và xử lý ký tự đặc biệt trong URL.
