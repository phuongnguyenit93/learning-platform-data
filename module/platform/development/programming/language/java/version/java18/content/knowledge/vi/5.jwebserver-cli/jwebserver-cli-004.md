# Chọn thư mục phục vụ bằng `-d` hoặc `--directory`, xử lý đường dẫn chứa khoảng trắng

## 1. Vì sao cần chỉ định thư mục phục vụ?

Từ **Java 18**, JDK cung cấp lệnh **`jwebserver`** (Simple Web Server) để phục vụ tài nguyên tĩnh trong quá trình phát triển, thử nghiệm và gỡ lỗi. Trên JDK hiện đại, bao gồm JDK 27, bạn có thể chọn thư mục gốc mà server được phép phục vụ bằng hai tên tùy chọn tương đương:

```sh
jwebserver -d ./public
```

hoặc:

```sh
jwebserver --directory ./public
```

Thư mục này thường được gọi là **document root** hoặc thư mục gốc phục vụ. Các đường dẫn URL được ánh xạ vào cây thư mục đó. Chọn đúng thư mục giúp server chỉ phục vụ HTML, CSS, JavaScript, ảnh và dữ liệu mẫu mà bạn định kiểm thử.

Nếu bỏ qua `-d`/`--directory`, server mặc định dùng **thư mục làm việc hiện tại (current working directory, CWD)** của tiến trình tại thời điểm chạy lệnh. CWD không nhất thiết là thư mục dự án hoặc nơi cài JDK. Bài này tập trung vào cách chọn thư mục rõ ràng, hiểu đường dẫn tương đối/tuyệt đối và truyền đúng đường dẫn có dấu cách qua từng loại shell.

> **Phạm vi:** `jwebserver` phục vụ tệp tĩnh qua HTTP/1.1 để phát triển, thử nghiệm và gỡ lỗi. Công cụ không cung cấp HTTPS, xác thực người dùng hoặc xử lý nghiệp vụ web động; không dùng làm máy chủ production.

## 2. Cấu trúc thư mục và cách ánh xạ URL

Giả sử dự án có cấu trúc:

```text
web-project/
├── README.md
├── private-notes.txt
├── build/
└── site/
    ├── index.html
    ├── css/
    │   └── app.css
    ├── js/
    │   └── app.js
    └── data/
        └── products.json
```

Khi chọn `web-project/site` làm document root, các URL được ánh xạ như sau:

| URL | Tệp tương ứng dưới document root |
| --- | --- |
| `/` | `index.html` nếu có trang index |
| `/css/app.css` | `css/app.css` |
| `/js/app.js` | `js/app.js` |
| `/data/products.json` | `data/products.json` |
| `/missing.txt` | Không có tệp tương ứng, thường nhận `404 Not Found` |

Các tệp `README.md`, `private-notes.txt` và thư mục `build` nằm ngoài document root nên không được đưa vào cây tài nguyên của ví dụ này. Đây là một lý do thực tế để chỉ định thư mục `site` thay vì chạy server từ `web-project`.

Nếu URL yêu cầu một thư mục có trang index, server phục vụ trang đó. Nếu không có trang index, Simple Web Server có thể trả về directory listing dạng HTML. Vì vậy, việc chọn document root quyết định cả phạm vi tệp có thể được truy cập lẫn nội dung có thể được liệt kê.

## 3. Dùng tùy chọn -d hoặc --directory

Cú pháp liên quan:

```text
jwebserver [-d directory] [các tùy chọn khác]
jwebserver [--directory directory] [các tùy chọn khác]
```

Hai cách viết ngắn và dài có cùng ý nghĩa:

- `-d`: dạng ngắn, tiện gõ trong terminal.
- `--directory`: dạng dài, dễ đọc khi viết script hoặc tài liệu.
- Giá trị theo sau là đường dẫn thư mục muốn phục vụ.

Ví dụ, nếu terminal đang đứng tại thư mục `web-project`:

```sh
jwebserver -d ./site -p 8080 -b 127.0.0.1
```

Lệnh trên chọn `web-project/site` làm document root, dùng cổng `8080` và chỉ lắng nghe IPv4 loopback. Cách viết dài tương đương:

```sh
jwebserver --directory ./site --port 8080 --bind-address 127.0.0.1
```

Tùy chọn `-d` không đổi CWD của terminal; nó chỉ xác định thư mục mà server phục vụ. Đường dẫn tương đối sau `-d` vẫn được tính từ **CWD lúc khởi động**, không tính từ thư mục chứa executable `jwebserver`.

## 4. Đường dẫn tương đối và tuyệt đối

### 4.1. Đường dẫn tương đối

Đường dẫn tương đối được tính từ CWD của tiến trình. Các dạng thường gặp:

| Đường dẫn | Ý nghĩa nếu CWD là `web-project` |
| --- | --- |
| `site` | Thư mục `web-project/site`. |
| `./site` | Cùng thư mục `web-project/site`; `./` làm rõ đường dẫn tương đối từ CWD. |
| `./site/data` | Thư mục `web-project/site/data`. |
| `../shared-site` | Thư mục `shared-site` nằm cạnh `web-project`, tức đi lên một cấp rồi đi vào thư mục đó. |

Ví dụ:

```sh
# Terminal đang ở web-project:
pwd
jwebserver -d ./site
```

Nếu terminal thực ra đang đứng ở thư mục cha, lệnh `-d ./site` sẽ trỏ tới một vị trí khác. Khi có lỗi, kiểm tra CWD trước khi kết luận server không tìm thấy thư mục.

### 4.2. Đường dẫn tuyệt đối

Đường dẫn tuyệt đối mô tả vị trí từ gốc của hệ thống tệp, không phụ thuộc CWD. Ví dụ:

**Windows:**

```powershell
jwebserver -d 'C:\Projects\web-project\site'
```

**Linux/macOS:**

```sh
jwebserver -d '/home/linh/projects/web-project/site'
```

Đường dẫn tuyệt đối hữu ích khi:

- chạy server từ IDE, script hoặc một thư mục terminal không cố định;
- viết lệnh trong hướng dẫn cho nhóm, nơi mỗi người có CWD khác nhau;
- muốn xác định rõ thư mục được phục vụ khi có nhiều thư mục cùng tên;
- điều tra lỗi do đường dẫn tương đối bị tính từ vị trí khác dự kiến.

Trên Windows, tránh nhầm **`C:\Projects\site`** với **`C:Projects\site`**. Dạng thứ hai là đường dẫn tương đối theo thư mục hiện hành của ổ C, không phải đường dẫn tuyệt đối bắt đầu từ gốc ổ đĩa.

## 5. Xử lý đường dẫn có khoảng trắng

Một đường dẫn như `My Web Project/site files` chứa dấu cách. Nếu không đặt toàn bộ giá trị đường dẫn trong dấu nháy hoặc escape dấu cách đúng cú pháp shell, shell có thể chia nó thành nhiều đối số. Khi đó `jwebserver` không nhận được một giá trị directory duy nhất.

**Nguyên tắc:** đặt toàn bộ đường dẫn trong một cặp dấu nháy. Dấu nháy giúp shell truyền đường dẫn thành **một đối số**; nó không phải một phần tên thư mục.

Giả sử cấu trúc trên Windows là:

```text
C:\
└── Dev Workspace\
    └── My Web Project\
        └── site files\
            └── index.html
```

### 5.1. Windows PowerShell

PowerShell hỗ trợ chuỗi nháy đơn và nháy kép. Với đường dẫn tĩnh, nháy đơn thường dễ đọc vì PowerShell không nội suy biến bên trong:

```powershell
jwebserver -d 'C:\Dev Workspace\My Web Project\site files' -p 8080
```

Nháy kép cũng hợp lệ:

```powershell
jwebserver --directory "C:\Dev Workspace\My Web Project\site files" --port 8080
```

Trong PowerShell, dấu gạch chéo ngược `\` trong đường dẫn Windows không cần nhân đôi như một số ngôn ngữ lập trình. Nháy kép có nội suy biến; ví dụ muốn dùng thư mục người dùng hiện tại:

```powershell
jwebserver -d "$env:USERPROFILE\Dev Workspace\My Web Project\site files"
```

Có thể kiểm tra thư mục trước khi khởi động:

```powershell
$site = 'C:\Dev Workspace\My Web Project\site files'
Test-Path -LiteralPath $site -PathType Container
Get-Item -LiteralPath $site
jwebserver -d $site -p 8080
```

`Test-Path -PathType Container` giúp xác nhận đường dẫn tồn tại và là thư mục. `-LiteralPath` tránh diễn giải các ký tự như `[` hoặc `]` trong tên như wildcard. Trong ví dụ, nếu kết quả kiểm tra là `False`, hãy sửa đường dẫn trước khi chạy server.

### 5.2. Windows Command Prompt (cmd.exe)

Trong Command Prompt, đặt đường dẫn trong dấu nháy kép:

```bat
jwebserver -d "C:\Dev Workspace\My Web Project\site files" -p 8080
```

Nếu muốn dùng biến môi trường:

```bat
jwebserver -d "%USERPROFILE%\Dev Workspace\My Web Project\site files" -p 8080
```

Command Prompt dùng cú pháp `%USERPROFILE%` để mở rộng biến môi trường. Đây là cú pháp của CMD; không dùng nguyên dạng đó trong PowerShell. Nếu đường dẫn chứa khoảng trắng, vẫn phải đặt toàn bộ biểu thức đường dẫn trong một cặp dấu nháy kép.

### 5.3. Linux/macOS (sh, bash, zsh)

Với shell kiểu POSIX, dùng nháy đơn để giữ nguyên đường dẫn:

```sh
jwebserver -d '/home/linh/Dev Workspace/My Web Project/site files' -p 8080
```

Nháy kép cũng dùng được và cho phép shell mở rộng biến:

```sh
jwebserver --directory "$HOME/Dev Workspace/My Web Project/site files" --port 8080
```

Có thể dùng dấu gạch chéo ngược để escape từng khoảng trắng khi không đặt cả đường dẫn trong dấu nháy:

```sh
jwebserver -d /home/linh/Dev\ Workspace/My\ Web\ Project/site\ files
```

Cách này hợp lệ trong shell POSIX nhưng khó đọc hơn khi đường dẫn dài. Dùng nháy đơn hoặc nháy kép quanh toàn bộ đường dẫn thường rõ ràng và ít sai sót hơn.

### 5.4. So sánh cách viết theo shell

| Môi trường | Đường dẫn có khoảng trắng | Ghi chú |
| --- | --- | --- |
| PowerShell | `'C:\Dev Workspace\site files'` | Nháy đơn giữ nguyên chuỗi; nháy kép mở rộng biến. |
| Command Prompt | `"C:\Dev Workspace\site files"` | Biến môi trường dùng dạng `%NAME%`. |
| POSIX shell | `'/home/user/Dev Workspace/site files'` | Nháy đơn giữ nguyên; nháy kép cho phép mở rộng `$VARIABLE`. |

Không lấy cú pháp mở rộng biến của shell này áp dụng sang shell khác. Khi viết tài liệu hoặc script cho nhóm, ghi rõ terminal đang sử dụng và cung cấp ví dụ đúng môi trường.

## 6. Thực hành: phục vụ một thư mục có dấu cách

### 6.1. Tạo dữ liệu mẫu

Tạo thư mục có cấu trúc:

```text
My Web Project/
└── site files/
    ├── index.html
    └── assets/
        └── app.css
```

Nội dung `My Web Project/site files/index.html`:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Thử đường dẫn có khoảng trắng</title>
  <link rel="stylesheet" href="/assets/app.css">
</head>
<body>
  <h1>Đường dẫn có khoảng trắng đã được xử lý đúng</h1>
  <p>Trang này được phục vụ từ thư mục site files.</p>
</body>
</html>
```

Nội dung `My Web Project/site files/assets/app.css`:

```css
body {
  font-family: system-ui, sans-serif;
  margin: 2rem auto;
  max-width: 48rem;
}
```

### 6.2. Chạy từ thư mục cha bằng đường dẫn tương đối

Đứng trong thư mục `My Web Project`, xác nhận CWD rồi chạy:

**PowerShell:**

```powershell
Get-Location
jwebserver -d '.\site files' -p 8080 -b 127.0.0.1
```

**Command Prompt:**

```bat
cd
jwebserver -d ".\site files" -p 8080 -b 127.0.0.1
```

**Linux/macOS:**

```sh
pwd
jwebserver -d './site files' -p 8080 -b 127.0.0.1
```

Cả ba ví dụ đều chọn thư mục con `site files` bên trong CWD. Dấu nháy bảo đảm khoảng trắng không chia đường dẫn thành nhiều đối số.

### 6.3. Chạy từ vị trí khác bằng đường dẫn tuyệt đối

Bạn có thể chạy terminal ở bất kỳ thư mục nào và dùng đường dẫn tuyệt đối đến `site files`. Ví dụ Windows PowerShell:

```powershell
jwebserver --directory 'C:\Dev Workspace\My Web Project\site files' --port 8080 --bind-address 127.0.0.1
```

Ví dụ Linux/macOS:

```sh
jwebserver --directory '/home/linh/Dev Workspace/My Web Project/site files' --port 8080 --bind-address 127.0.0.1
```

Nếu khởi động thành công, thông báo server sẽ hiển thị đường dẫn đã chọn và URL. Đối chiếu đường dẫn tuyệt đối trong thông báo **Serving ...** với thư mục `site files` mà bạn mong muốn.

### 6.4. Xác minh bằng trình duyệt và curl

Với bind IPv4 và cổng `8080`, mở:

```text
http://127.0.0.1:8080/
```

Trong terminal thứ hai:

```sh
# Lấy trang chủ:
curl -i http://127.0.0.1:8080/

# Kiểm tra tệp CSS trong thư mục con:
curl -I http://127.0.0.1:8080/assets/app.css

# Kiểm tra đường dẫn không tồn tại:
curl -i http://127.0.0.1:8080/missing.html
```

Kết quả thường thấy: trang chủ và CSS trả `200 OK`, đường dẫn không tồn tại trả `404 Not Found`. Trên Windows PowerShell 5.1, dùng `curl.exe` thay cho `curl` nếu tên `curl` đang là alias của `Invoke-WebRequest`.

Nhấn **Ctrl+C** trong terminal chạy server để dừng.

## 7. Kiểm tra thư mục và chẩn đoán lỗi

Trước khi chạy server, có thể kiểm tra đường dẫn và quyền đọc bằng công cụ của hệ điều hành.

**PowerShell:**

```powershell
$site = 'C:\Dev Workspace\My Web Project\site files'
Test-Path -LiteralPath $site -PathType Container
Get-ChildItem -LiteralPath $site
```

**Linux/macOS:**

```sh
site='/home/linh/Dev Workspace/My Web Project/site files'
test -d "$site" && ls -la "$site"
```

Nếu đường dẫn không tồn tại hoặc không phải thư mục, hãy kiểm tra tên thư mục, ổ đĩa, dấu phân cách và CWD. Nếu thư mục có tồn tại nhưng tiến trình không có quyền đọc, hãy điều chỉnh quyền phù hợp hoặc chọn thư mục có thể đọc. Không cần cấp quyền rộng cho toàn bộ dự án chỉ để chạy web server.

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Shell báo không tìm thấy đường dẫn hoặc đối số thừa | Đường dẫn chứa khoảng trắng chưa được đặt trong dấu nháy; shell chia thành nhiều đối số. | Đặt toàn bộ giá trị sau `-d`/`--directory` trong một cặp dấu nháy. |
| Server báo thư mục không hợp lệ hoặc không thể khởi động | Đường dẫn sai, không tồn tại, trỏ tới tệp thay vì thư mục hoặc không truy cập được. | Dùng `Test-Path -PathType Container` hoặc `test -d`; kiểm tra quyền đọc. |
| Server phục vụ nhầm cây thư mục | Đường dẫn tương đối được tính từ CWD khác dự kiến. | Kiểm tra `Get-Location`/`pwd` hoặc chuyển sang đường dẫn tuyệt đối. |
| Server chạy nhưng URL trả `404` | Tệp không nằm dưới document root hoặc URL viết sai. | Đọc đường dẫn **Serving ...**, so khớp đường dẫn URL từ gốc thư mục đã chọn. |
| Trang chủ hiển thị directory listing | Thư mục được phục vụ không có tệp index phù hợp. | Chọn đúng thư mục hoặc thêm tệp index cho nội dung thử nghiệm. |
| PowerShell báo lỗi khi dùng cú pháp biến CMD | Đã dùng `%USERPROFILE%` trong PowerShell. | Dùng `$env:USERPROFILE` trong PowerShell. |
| Đường dẫn Windows trỏ sai vị trí | Dùng dạng `C:folder` và nhầm là đường dẫn tuyệt đối. | Dùng `C:\folder` hoặc đường dẫn đầy đủ phù hợp. |
| Server báo cổng đã được dùng | Tiến trình khác đang lắng nghe trên địa chỉ/cổng đó. | Dừng tiến trình cũ hoặc chọn cổng khác bằng `-p`. |

## 8. Những lưu ý khi chọn document root

- Chỉ chọn thư mục chứa tài nguyên cần kiểm thử, ví dụ `public`, `site` hoặc `dist` sau khi đã kiểm tra nội dung.
- Không chọn thư mục cha quá rộng nếu trong đó có tệp cấu hình, bản sao lưu, thông tin xác thực, khóa riêng hoặc dữ liệu cá nhân.
- Không giả định đường dẫn tương đối được tính từ vị trí của lệnh `jwebserver`; nó được tính từ CWD.
- Dùng đường dẫn tuyệt đối trong script chạy từ nhiều working directory khác nhau.
- Với đường dẫn có khoảng trắng, đặt toàn bộ giá trị trong dấu nháy phù hợp với shell; đừng trộn cú pháp biến môi trường giữa PowerShell, CMD và POSIX.
- Nếu chia sẻ server ra mạng, nhớ rằng đây là HTTP không có xác thực; chỉ thực hiện trong môi trường thử nghiệm tin cậy.

## 9. Bài tập tự kiểm tra

1. Tạo dự án có cấu trúc `web-project/site/index.html`. Đứng tại `web-project` và chạy `jwebserver -d ./site`. Giải thích vì sao server không phục vụ `README.md` nằm ngoài `site`.
2. Đổi tên thư mục thành `site files`, sau đó viết lệnh đúng cho PowerShell, CMD và Linux/macOS. Giải thích vì sao cần dấu nháy.
3. Chạy lệnh từ thư mục cha bằng đường dẫn tương đối, rồi chạy từ thư mục khác bằng đường dẫn tuyệt đối. So sánh kết quả.
4. Cố tình bỏ dấu nháy trong đường dẫn có khoảng trắng, quan sát lỗi shell/CLI rồi sửa lại.
5. Dùng `Test-Path -LiteralPath` hoặc `test -d` để kiểm tra thư mục trước khi khởi động. Giải thích khác nhau giữa thư mục tồn tại và tiến trình có quyền đọc thư mục.
6. Xác minh document root qua thông báo `Serving ...`, rồi dùng `curl` để kiểm tra trang chủ và một tài nguyên con.

**Tiêu chí hoàn thành:** bạn biết dùng `-d`/`--directory`, phân biệt đường dẫn tương đối và tuyệt đối, truyền đúng đường dẫn chứa khoảng trắng trong shell đang dùng, xác minh document root thực tế và chỉ công khai cây thư mục có tài nguyên phù hợp.

## 10. Tài liệu tham khảo

- [Oracle Java SE 27 — The jwebserver Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html): cú pháp `-d`/`--directory`, thư mục mặc định, địa chỉ bind, cổng và các giới hạn của Simple Web Server.
- [Oracle Java SE 27 — Module jdk.httpserver](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/module-summary.html): module cung cấp công cụ và mục đích phát triển/thử nghiệm.
- [OpenJDK JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): nguồn gốc tính năng được giới thiệu từ Java 18.
