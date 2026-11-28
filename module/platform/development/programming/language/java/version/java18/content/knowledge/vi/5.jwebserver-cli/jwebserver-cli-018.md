# Dừng máy chủ, giải phóng cổng và thực hành xem trước tài liệu HTML hoặc fixture cục bộ

> **Chương:** Lệnh jwebserver  
> **Module:** `JAVA_VERSION_JAVA18`  
> **Mục tiêu:** Chạy `jwebserver` trên loopback để xem trước HTML và fixture tĩnh; dừng máy chủ bằng `Ctrl+C`, xác minh cổng không còn listener, xử lý xung đột cổng và tránh dừng nhầm tiến trình khác. Các hướng dẫn này sử dụng hành vi JDK đã được tài liệu hóa từ Java 18 và vẫn hữu ích trên JDK hiện đại.

## 1. Khi nào nên dùng jwebserver?

Khi cần xem một bộ tài liệu HTML, kiểm tra CSS, JavaScript hoặc file JSON tĩnh, ta có thể cần URL HTTP thay vì mở `file:///...` trực tiếp trong trình duyệt. Một số cơ chế như JavaScript `fetch()`, đường dẫn tương đối và kiểm tra HTTP status cần một server thực sự.

JEP 408 bổ sung Simple Web Server trong Java 18. Công cụ `jwebserver` thuộc module `jdk.httpserver`, phục vụ cây thư mục file tĩnh qua HTTP/1.1 để phát triển, thử nghiệm và gỡ lỗi. Đây là công cụ JDK có tài liệu riêng; nó không phải ứng dụng web production.

Bài này thực hiện một vòng đầy đủ:

1. Tạo thư mục chỉ chứa dữ liệu thử nghiệm.
2. Chạy server foreground với địa chỉ và port xác định.
3. Xem HTML bằng browser, dùng GET/HEAD để kiểm tra fixture.
4. Dừng server với `Ctrl+C`.
5. Kiểm tra listener đã biến mất và sử dụng lại cổng.
6. Xử lý khi cổng đang bị một tiến trình khác sử dụng.

## 2. Vòng đời của tiến trình và cổng

`jwebserver` mặc định chạy ở foreground: terminal khởi chạy giữ tiến trình đang hoạt động cho đến khi bị dừng. Browser chỉ là client; đóng tab browser không dừng tiến trình server.

~~~text
Tạo public/index.html và fixtures/example.json
                    |
                    v
jwebserver -b 127.0.0.1 -p 8765 -d public
                    |
                    v
Server LISTEN ở 127.0.0.1:8765
                    |
                    v
Browser/curl gửi GET hoặc HEAD
                    |
                    v
Ctrl+C trong terminal đang chạy server
                    |
                    v
Tiến trình thoát, socket listener đóng
                    |
                    v
Kiểm tra port rồi khởi động lại nếu cần
~~~

Port `8765` được chọn làm ví dụ để tách khỏi port mặc định `8000`; nó vẫn có thể bị chiếm. Dùng `127.0.0.1` để giới hạn truy cập qua IPv4 loopback của máy thực hành.

## 3. Xác minh JDK và các option

Trước tiên:

~~~shell
java --version
jwebserver --version
jwebserver --help
~~~

Kiểm tra runtime image có `jdk.httpserver` bằng:

~~~shell
java --list-modules
~~~

Tìm dòng `jdk.httpserver@...`. Một custom runtime image có thể thiếu module hoặc launcher dù bản JDK đầy đủ có chúng. Nếu lệnh không tồn tại, kiểm tra PATH/JDK đang dùng trước khi kết luận tính năng bị loại bỏ.

Các option quan trọng:

| Option | Ý nghĩa | Ví dụ |
|---|---|---|
| `-b`, `--bind-address` | Địa chỉ bind | `127.0.0.1` |
| `-p`, `--port` | TCP port | `8765` |
| `-d`, `--directory` | Thư mục gốc | `public` |
| `-o`, `--output` | Log `none`, `info`, `verbose` | `info` |
| `-h`, `--help` | In trợ giúp rồi thoát | `jwebserver --help` |
| `-version`, `--version` | In phiên bản rồi thoát | `jwebserver --version` |

Khi không ghi option, công cụ thường bind loopback và port `8000`, phục vụ working directory. Lệnh trong bài sẽ luôn chỉ rõ địa chỉ, port và thư mục để dễ tái hiện.

## 4. Tạo fixture cục bộ

Chuẩn bị cấu trúc:

~~~text
local-preview/
└── public/
    ├── index.html
    ├── assets/
    │   └── site.css
    └── fixtures/
        └── example.json
~~~

Trên Linux/macOS:

~~~shell
mkdir -p local-preview/public/assets local-preview/public/fixtures
cd local-preview
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path .\local-preview\public\assets, .\local-preview\public\fixtures | Out-Null
Set-Location .\local-preview
~~~

Tiếp theo, dùng editor lưu các file dưới đây bằng UTF-8.

### 4.1. public/index.html

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Xem trước tài liệu</title>
  <link rel="stylesheet" href="./assets/site.css">
</head>
<body>
  <main>
    <h1>Simple Web Server hoạt động</h1>
    <p>Trang HTML được phục vụ qua HTTP cục bộ.</p>
    <p id="result">Đang tải fixture...</p>
    <a href="./fixtures/example.json">Xem JSON gốc</a>
  </main>
  <script>
    fetch("./fixtures/example.json")
      .then(response => {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(data => {
        document.getElementById("result").textContent = data.message;
      })
      .catch(error => {
        document.getElementById("result").textContent =
            "Lỗi fixture: " + error.message;
      });
  </script>
</body>
</html>
~~~

### 4.2. public/assets/site.css

~~~css
body {
  font-family: system-ui, sans-serif;
  line-height: 1.6;
  max-width: 48rem;
  margin: 2rem auto;
  padding: 0 1rem;
}
main {
  border: 1px solid #aaa;
  border-radius: 0.5rem;
  padding: 1.5rem;
}
~~~

### 4.3. public/fixtures/example.json

~~~json
{
  "message": "Fixture JSON đã được tải: Xin chào!",
  "active": true,
  "items": ["java", "html", "json"]
}
~~~

Mã `fetch()` chỉ đọc JSON tĩnh. `jwebserver` không thực thi backend JavaScript, không cập nhật file và không cung cấp API POST.

## 5. Khởi động server foreground

Đứng trong thư mục `local-preview`, chạy:

~~~shell
jwebserver -b 127.0.0.1 -p 8765 -d public -o info
~~~

Khi khởi động thành công, console sẽ cho biết thư mục phục vụ và URL, có thể tương tự:

~~~text
Serving .../local-preview/public and subdirectories on 127.0.0.1 port 8765
URL http://127.0.0.1:8765/
~~~

Output đầy đủ phụ thuộc phiên bản JDK và môi trường; không assert toàn bộ log. Cần xác nhận địa chỉ `127.0.0.1`, cổng `8765` và đường dẫn thư mục gốc.

Terminal sẽ chưa trả về prompt vì tiến trình vẫn chạy. Mở browser hoặc một terminal thứ hai để gửi request.

**Lưu ý về `-d`:** `public` là đường dẫn tương đối từ working directory của process. Nếu chạy từ folder khác, `-d public` có thể trỏ sai. Hãy dùng đúng folder hoặc truyền đường dẫn tuyệt đối.

## 6. Xem trước HTML và fixture

Trong browser mở:

~~~text
http://127.0.0.1:8765/
~~~

Khi `public/index.html` tồn tại, GET `/` sẽ phục vụ trang index. Bạn sẽ thấy tiêu đề, CSS và message từ `example.json` nếu `fetch()` thành công.

Dùng Developer Tools → Network để kiểm tra ba request:

~~~text
GET /
GET /assets/site.css
GET /fixtures/example.json
~~~

Mở riêng URL:

~~~text
http://127.0.0.1:8765/fixtures/example.json
~~~

Nếu JSON không hiện trong trang, kiểm tra response status, đường dẫn `-d` và console của browser. Một request `404` cho fixture thường có nghĩa URL không map tới file trong serve root.

Mở HTML bằng `file://` có thể tạo hành vi khác đối với `fetch()` và origin security policy. Server HTTP loopback giúp kiểm thử trong điều kiện gần với cách browser tải tài nguyên từ một website.

## 7. Kiểm tra GET và HEAD bằng terminal

### 7.1. GET nội dung HTML

Trên Linux/macOS:

~~~shell
curl -i http://127.0.0.1:8765/index.html
~~~

Trên Windows PowerShell, dùng `curl.exe` để tránh nhầm alias của một số bản PowerShell:

~~~powershell
curl.exe -i http://127.0.0.1:8765/index.html
~~~

Kết quả mong đợi khi file đọc được là HTTP status thành công như `200 OK` và HTML body phù hợp với fixture.

### 7.2. HEAD chỉ lấy header

~~~shell
curl -I http://127.0.0.1:8765/fixtures/example.json
~~~

Trên Windows:

~~~powershell
curl.exe -I http://127.0.0.1:8765/fixtures/example.json
~~~

HEAD không trả body nhưng có thể cho biết status và metadata của resource. Không coi response body rỗng của HEAD là lỗi của file JSON.

### 7.3. GET JSON và thử đường dẫn sai

~~~shell
curl -i http://127.0.0.1:8765/fixtures/example.json
curl -i http://127.0.0.1:8765/fixtures/missing.json
~~~

Request đầu mong đợi thành công và body chứa message. Request thứ hai thường nhận `404 Not Found`. Đây vẫn là một **HTTP response do server đang chạy trả về**, khác với trường hợp không kết nối được vì server đã dừng.

`jwebserver` chỉ phục vụ GET và HEAD theo tài liệu. Với các method khác như POST, công cụ có thể trả `405` hoặc `501`; không sử dụng nó để kiểm thử xử lý API động.

Không so khớp nguyên văn tất cả header như `Date`, giá trị thời gian hoặc thứ tự header; chúng có thể thay đổi. Tập trung vào status, method, URL và nội dung fixture đã xác định.

## 8. Dừng server bằng Ctrl+C

Khi hoàn tất xem trước:

1. Quay lại terminal đang chạy `jwebserver`.
2. Nhấn `Ctrl+C`.
3. Quan sát process kết thúc và terminal trở lại prompt.
4. Kiểm tra request mới không còn nhận response từ server cũ.

Theo JDK tool specification, `Ctrl+C` là cách dừng server. Trên Unix, tổ hợp này gửi `SIGINT` đến process foreground. Trên Windows, console hỗ trợ tổ hợp ngắt tiến trình tương ứng.

Sau khi server kết thúc, hệ điều hành đóng listening socket của process. Việc đóng tab browser không tương đương: tab là client, không sở hữu listener.

### 8.1. Kiểm tra bằng curl

Sau khi dừng:

~~~shell
curl --connect-timeout 2 -I http://127.0.0.1:8765/index.html
~~~

Trên PowerShell:

~~~powershell
curl.exe --connect-timeout 2 -I http://127.0.0.1:8765/index.html
~~~

Khi không có listener nào ở endpoint này, `curl` thường báo lỗi kết nối và trả exit code khác 0. Nội dung lỗi chính xác phụ thuộc OS và client.

**Phân biệt ba trường hợp:**

- `404`: một server vẫn trả HTTP response, nhưng URL không map tới file.
- `Connection refused` hoặc lỗi thiết lập kết nối: client chưa nhận được HTTP response từ endpoint đó.
- `200` sau khi đã dừng server: có thể là process khác đã dùng cổng hoặc bạn đã dừng nhầm terminal; kiểm tra listener và PID.

Request lỗi là một dấu hiệu. Muốn xác minh cổng được giải phóng, kiểm tra listening socket bằng công cụ OS.

## 9. Kiểm tra port 8765 trên Windows

Trong PowerShell:

~~~powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
~~~

Nếu không có kết quả, thường không có TCP listener trên port `8765` mà công cụ có thể quan sát. Nếu có, kiểm tra địa chỉ local và PID sở hữu:

~~~powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen |
    Select-Object LocalAddress, LocalPort, OwningProcess
~~~

Để xem chi tiết một PID đã được xác minh:

~~~powershell
Get-Process -Id 12345
~~~

Thay `12345` bằng PID thực tế đọc được. Không dùng một PID minh họa để dừng process.

Một cách khác:

~~~powershell
netstat -ano | findstr :8765
~~~

Ở kết quả này, cần xem trạng thái `LISTENING` và local address. Dòng `TIME_WAIT` của một kết nối cũ không chứng minh server còn lắng nghe trên cổng đó.

## 10. Kiểm tra port trên Linux và macOS

Trên Linux, có thể dùng:

~~~shell
ss -ltnp | grep ':8765'
~~~

Nếu `ss` không có hoặc cần một công cụ khác, thử `lsof` khi có cài:

~~~shell
lsof -nP -iTCP:8765 -sTCP:LISTEN
~~~

Trên macOS, lệnh `lsof` ở trên cũng dùng được. Nó cho biết tên process và PID khi có quyền xem.

Đọc output dựa trên trạng thái `LISTEN`, local address, local port và PID. Thông tin process của user khác có thể bị hạn chế bởi quyền của hệ điều hành.

### 10.1. LISTEN khác TIME_WAIT

Sau khi dừng server, các TCP connection đã đóng có thể còn bản ghi `TIME_WAIT` trong một khoảng thời gian. Điều này không đồng nghĩa một process vẫn có listening socket nhận request mới.

Để xác định port đang bị server khác chiếm, ưu tiên các dòng `LISTEN`/`LISTENING` và PID sở hữu, thay vì chỉ tìm thấy con số port ở bất kỳ dòng `netstat` nào.

## 11. Xử lý khi cổng bị chiếm

Giả sử chạy:

~~~shell
jwebserver -b 127.0.0.1 -p 8765 -d public
~~~

nhưng gặp lỗi bind, ví dụ thông báo tương đương `Address already in use`. Một process khác có thể đã lắng nghe trên cùng địa chỉ/cổng.

Quy trình:

1. Kiểm tra có terminal `jwebserver` cũ nào còn chạy không.
2. Dùng công cụ ở phần 9 hoặc 10 để xem listener.
3. Xác minh PID và tên process, xác định ai sở hữu nó.
4. Nếu đó là server do mình chạy foreground, quay về terminal đó và nhấn `Ctrl+C`.
5. Nếu cần giữ process đang chạy, chọn port khác, ví dụ `8766`.
6. Khởi động lại, kiểm tra URL và serve root.

Chạy trên port khác:

~~~shell
jwebserver -b 127.0.0.1 -p 8766 -d public
~~~

Mở:

~~~text
http://127.0.0.1:8766/
~~~

Không kill hàng loạt process `java` hoặc `jwebserver` bằng tên chương trình. Máy có thể đang chạy nhiều ứng dụng Java khác nhau; chỉ dừng đúng process bạn đã xác định.

### 11.1. Khi server chạy nền và không còn terminal

Nếu IDE hoặc task runner đã khởi chạy server, dùng lệnh Stop của chính công cụ quản lý đó trước.

Trên Linux/macOS, sau khi xác nhận PID thật sự thuộc server của mình, có thể gửi `SIGINT`:

~~~shell
kill -INT 12345
~~~

Trên Windows PowerShell, sau khi xác minh đúng PID do mình sở hữu:

~~~powershell
Stop-Process -Id 12345
~~~

Hai ví dụ dùng PID minh họa `12345`; cần thay bằng PID quan sát được. Dừng process theo PID là bước dự phòng, khác với `Ctrl+C` được dùng cho foreground server. Luôn kiểm tra listener sau đó.

## 12. Thực hành tái sử dụng port sau khi dừng

### Vòng A: xem trước fixture

Ở terminal A:

~~~shell
jwebserver -b 127.0.0.1 -p 8765 -d public -o info
~~~

Ở terminal B:

~~~shell
curl -I http://127.0.0.1:8765/index.html
curl -i http://127.0.0.1:8765/fixtures/example.json
~~~

Sau khi kiểm tra, quay lại terminal A, nhấn `Ctrl+C`. Thử request lại và xác minh không còn listener `8765` thuộc server này.

### Vòng B: dùng lại port cho bộ tài liệu khác

Giả sử đã có thư mục `docs` với `index.html`. Từ thư mục cha của `docs`:

~~~shell
jwebserver -b 127.0.0.1 -p 8765 -d docs -o info
~~~

Mở lại `http://127.0.0.1:8765/`. Nội dung giờ được lấy từ `docs` thay vì `public`, dù endpoint giống nhau.

Nếu chưa có `docs`, có thể tạo thư mục mới chứa trang `index.html` để thử. Sau vòng B, tiếp tục dừng bằng `Ctrl+C` và kiểm tra port.

## 13. Xem trước tài liệu Javadoc đã sinh

Một use case liên quan Java 18 là xem bộ HTML do `javadoc` sinh ra, kể cả trang có snippet `{@snippet}` khi dùng standard doclet phù hợp.

Giả sử project có file `src/Example.java` chứa Javadoc hợp lệ. Tạo tài liệu:

~~~shell
javadoc -encoding UTF-8 -d docs src/Example.java
~~~

Kiểm tra `docs/index.html` tồn tại rồi chạy:

~~~shell
jwebserver -b 127.0.0.1 -p 8765 -d docs
~~~

Mở browser tới `http://127.0.0.1:8765/`. Có thể thử link, stylesheet và script được sinh trong tài liệu qua cùng origin HTTP.

`jwebserver` chỉ phục vụ file HTML đã tạo. Snippet Javadoc được render không có nghĩa code trong snippet đã được compile hoặc thực thi; muốn kiểm chứng hành vi Java, cần source/test riêng.

Sau khi xem xong, nhấn `Ctrl+C` để giải phóng cổng. Nếu cập nhật tài liệu trong lúc server vẫn chạy, hãy refresh browser và kiểm tra browser cache trước khi kết luận file không được cập nhật.

## 14. Bảng chẩn đoán nhanh

| Hiện tượng | Điều cần kiểm tra | Cách xử lý |
|---|---|---|
| Không có lệnh `jwebserver` | PATH/JDK launcher, module `jdk.httpserver` | Dùng JDK có công cụ và module |
| Bind error | Listener khác đã giữ port | Xem PID, dừng server của mình hoặc đổi port |
| Browser không kết nối được | Server chưa chạy, đã dừng hoặc sai URL | Kiểm tra terminal và URL bind |
| `404` với `index.html` | `-d` trỏ sai, file thiếu | Kiểm tra working directory và serve root |
| Trang HTML không có CSS | URL tương đối sai, asset không tồn tại | Dùng Network tab kiểm tra GET CSS |
| `fetch()` báo lỗi | JSON sai/thiếu hoặc status không thành công | Mở fixture URL trực tiếp và kiểm tra body |
| `405`/`501` khi POST | Method không được server hỗ trợ | Chỉ dùng GET/HEAD cho file tĩnh |
| Tiếng Việt hiển thị sai | File encoding, meta charset hoặc renderer | Lưu fixture UTF-8, kiểm tra byte và browser |
| Sau `Ctrl+C` vẫn nhận response | Có process khác đang phục vụ | Kiểm tra listener/PID và terminal dừng |
| Có `TIME_WAIT` sau khi dừng | Connection TCP cũ đang hoàn tất | Kiểm tra `LISTEN` thay vì chỉ tìm port |

`404` là HTTP response do server đưa ra, còn lỗi không kết nối được sau khi dừng thường là kết quả mong đợi. Không gộp chúng thành một loại lỗi.

## 15. Phạm vi sử dụng và các giới hạn

`jwebserver` thích hợp để:

- Xem trước HTML/CSS/JavaScript tĩnh.
- Mở tài liệu Javadoc đã sinh.
- Phục vụ fixture JSON/text local cho browser hoặc client.
- Quan sát request GET/HEAD, status và response header.
- Thử lại một bộ tài nguyên tĩnh nhanh chóng.

Công cụ không cung cấp HTTPS, HTTP/2, authentication, backend POST, upload hoặc dynamic routing. Nó không thay thế server web có cấu hình bảo mật cho production.

Trong bài này, dùng `-b 127.0.0.1`. Nếu chuyển sang `-b 0.0.0.0`, server có thể lắng nghe từ các máy khác trên mạng tùy firewall và routing. Để thực hành cục bộ, không có lý do mở rộng khả năng truy cập.

Vì server có thể phục vụ các file trong cây thư mục `-d` và đưa ra directory listing khi không có index, chỉ dùng một thư mục fixture riêng đã kiểm tra. Không đặt secret, token, khóa riêng, hồ sơ người dùng hoặc file sản xuất trong serve root.

## 16. Bài tập thực hành

### Bài 1 — Xem trước HTML

Tạo `public/index.html` và chạy server tại `127.0.0.1:8765`.

**Tiêu chí đạt:** Trang mở được trong browser; URL và serve root khớp thông báo từ công cụ.

### Bài 2 — Tải fixture bằng fetch

Tạo `fixtures/example.json`, gọi `fetch()` trong HTML và kiểm tra bằng `curl`.

**Tiêu chí đạt:** GET trả JSON đúng, browser hiển thị message từ fixture.

### Bài 3 — Dừng server và kiểm tra listener

Nhấn `Ctrl+C`, thử request mới và kiểm tra socket trên hệ điều hành.

**Tiêu chí đạt:** Server không còn nhận request và listener cũ trên port `8765` đã được đóng.

### Bài 4 — Tạo xung đột cổng

Giữ server thứ nhất chạy ở `8765` rồi thử khởi động server thứ hai cùng endpoint.

**Tiêu chí đạt:** Phân tích bind error, xác định process giữ port và chọn dừng server của mình hoặc dùng `8766`.

### Bài 5 — Dùng lại port

Sau khi dừng server từ `public`, khởi chạy server từ `docs` bằng cùng port.

**Tiêu chí đạt:** Port được tái sử dụng và nội dung thay đổi theo serve root.

### Bài 6 — So sánh 404 với lỗi kết nối

Khi server đang chạy, gọi một file không có thật. Sau khi dừng server, gọi lại URL đó.

**Tiêu chí đạt:** Phân biệt HTTP `404` với việc không nhận được HTTP response vì không có listener.

## 17. Checklist kết thúc buổi thực hành

- [ ] Đã xác minh `jwebserver` và `jdk.httpserver` có trong JDK.
- [ ] Thư mục `-d` chỉ chứa tài liệu và fixture được phép phục vụ.
- [ ] Đã bind `127.0.0.1` và chọn port rõ ràng.
- [ ] Đã xác nhận URL và serve root khi server startup.
- [ ] Đã kiểm tra GET/HEAD và nội dung fixture.
- [ ] Đã phân biệt `404` và connection error.
- [ ] Đã dừng server foreground bằng `Ctrl+C`.
- [ ] Đã kiểm tra listener bằng công cụ OS thích hợp.
- [ ] Đã phân biệt `LISTEN` với `TIME_WAIT`.
- [ ] Không dừng nhầm process Java khác.
- [ ] Đã có thể dùng lại port sau khi server dừng.
- [ ] Không để server test tiếp tục lắng nghe sau giờ thực hành.

## 18. Tài liệu chính thức

1. [The jwebserver Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jwebserver.html): các option, serve root, GET/HEAD, logging, địa chỉ mặc định và cách dừng server.
2. [JEP 408 — Simple Web Server](https://openjdk.org/jeps/408): mục tiêu đưa Simple Web Server vào Java 18.
3. [SimpleFileServer — JDK 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.httpserver/com/sun/net/httpserver/SimpleFileServer.html): API tương ứng với công cụ.
4. [The javadoc Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javadoc.html): cách tạo HTML Javadoc phục vụ cục bộ.
5. [MDN — GET](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Methods/GET) và [HEAD](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Methods/HEAD): ý nghĩa hai HTTP method.
6. [Microsoft Learn — Get-NetTCPConnection](https://learn.microsoft.com/en-us/powershell/module/nettcpip/get-nettcpconnection): kiểm tra TCP listener trên Windows.
7. [Microsoft Learn — Stop-Process](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.management/stop-process): dừng đúng tiến trình đã xác định theo PID.

**Kết quả cần đạt:** Bạn có thể tạo trang HTML và fixture JSON, khởi chạy `jwebserver` trên loopback, thử GET/HEAD, dừng server bằng `Ctrl+C`, xác minh cổng đã được giải phóng và xử lý bind conflict mà không gây ảnh hưởng tới các tiến trình khác. Quy trình này tiếp tục hữu ích trên JDK hiện đại khi xem trước tài liệu và kiểm thử nội dung tĩnh.
