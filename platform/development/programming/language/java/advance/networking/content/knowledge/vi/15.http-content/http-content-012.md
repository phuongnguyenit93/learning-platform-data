# Tải file an toàn: tên file, đường dẫn đích và xử lý nội dung tải chưa hoàn tất

## 1. Vấn đề: nhận được HTTP 200 không có nghĩa đã có file an toàn

Một ứng dụng Java tải file từ HTTP/HTTPS thường phải giải quyết **ba nhóm rủi ro độc lập**:

1. **Tên file không đáng tin:** server có thể gửi `Content-Disposition: attachment; filename="../../outside.txt"`, một URL có tên file khó kiểm soát, hoặc người dùng cung cấp tên chứa ký tự đường dẫn, tên thiết bị dành riêng, ký tự Unicode gây nhầm lẫn.
2. **Đường dẫn đích và hệ thống file:** nối tên file vào thư mục bằng chuỗi một cách ngây thơ có thể ghi ra ngoài thư mục dự kiến, ghi đè file tồn tại, theo symlink hoặc cạnh tranh với một tiến trình khác trong lúc lưu.
3. **Nội dung tải chưa hoàn tất:** HTTP body có thể bị cắt giữa chừng do mất mạng, timeout, hết dung lượng đĩa, cancel, server đóng sớm, sai `Content-Length` hoặc checksum. Nếu viết trực tiếp vào file cuối cùng, ứng dụng và người dùng có thể tưởng file dở dang đã sẵn sàng.

Một pipeline phù hợp:

```text
Nguồn HTTPS đã được cho phép
         |
         v
HttpClient với redirect policy rõ ràng
         |
         v
Kiểm tra status, loại nội dung, length/size limit
         |
         v
Chọn tên file theo chính sách CỦA ỨNG DỤNG
         |
         v
Xác minh thư mục đích được quản trị/tin cậy
         |
         v
Tạo file .part ngẫu nhiên TRONG thư mục đích
         |
         v
Stream byte theo từng chunk + đếm bytes + hash
         |
         +--> lỗi HTTP/I/O/quá giới hạn/hash/length? --> xóa .part
         |
         v
Body kết thúc hợp lệ và kiểm tra xong
         |
         v
Xuất bản sang tên cuối (không chủ ý ghi đè)
         |
         v
Chỉ lúc này báo tải thành công
```

**Nguyên tắc chính:** tên file, đường dẫn và nội dung đều đi qua ranh giới tin cậy riêng. `Content-Type`, `Content-Disposition`, URL, `Content-Length` và status code là **metadata do phía bên kia cung cấp**, không phải bằng chứng file an toàn hoặc đầy đủ.

Bài học sử dụng Java 17+ với `java.net.http.HttpClient` và `java.nio.file.Files/Path`. Ví dụ thực thi chạy **loopback HTTP** cho phép kiểm thử không cần Internet; **production phải ưu tiên HTTPS và kiểm soát đích kết nối**.

## 2. Mô hình đe dọa: ta đang bảo vệ điều gì?

| Đầu vào/tình huống | Rủi ro | Biện pháp |
| --- | --- | --- |
| `filename="../../app.properties"` từ HTTP | Path traversal, sửa file ngoài vùng tải | Không dùng trực tiếp; tên do ứng dụng chọn, allowlist |
| `filename="C:\\Windows\\..."` hoặc `/etc/passwd` | Absolute path hoặc phân tách path khác hệ điều hành | Validate tên đơn, từ chối `/`, `\\`, `:` và path segments |
| `filename="CON.txt"` ở Windows | Tên thiết bị dự trữ | Từ chối tên reserved trên nền tảng được hỗ trợ |
| Hai tác vụ cùng lưu `report.pdf` | Ghi đè, tranh chấp khi commit | File tạm duy nhất, publish không `REPLACE_EXISTING`, chiến lược concurrency |
| Final path là symlink | Ghi vào đối tượng khác với dự định | Không follow symlink, giữ thư mục đích tin cậy, phòng race |
| Server trả 404 nhưng body là HTML | Lưu error page với đuôi `.pdf` | Kiểm tra status trước khi tạo file cuối |
| Server ghi 20 MB rồi ngắt dù khai 100 MB | File chưa hoàn chỉnh | Xử lý stream exception, kiểm tra byte count khi phù hợp, checksum |
| Server gửi body gzip nhưng app kỳ vọng raw ZIP/PDF | Sai bytes/hash hoặc lưu dữ liệu không đúng format | Có chính sách `Content-Encoding` và hash trên đúng representation |
| File rất lớn/không có Content-Length | Hết đĩa, memory pressure | Giới hạn tổng bytes **trong lúc stream** |
| Body tải đủ nhưng chứa nội dung độc hại | File tồn tại nhưng không an toàn để mở | Validate format, security scan theo chính sách, không tự thực thi |
| URL do user chỉ định trỏ tới metadata nội bộ | SSRF, lộ tài nguyên nội mạng | Allowlist URL/host, hạn chế egress, kiểm soát redirect/DNS |
| Mạng lỗi sau khi tải một phần | Rác `.part` và trạng thái hiển thị sai | Cleanup, trạng thái thất bại, retry/resume có kiểm soát |

Không nên giải quyết bằng một lời gọi `Path.normalize()` rồi cho rằng toàn bộ bài toán an toàn. Normalization chỉ xử lý thành phần đường dẫn **theo cú pháp**, không giải quyết được symlink, quyền truy cập, tranh chấp, hoặc nội dung độc hại.

## 3. Ưu tiên chọn **tên an toàn do ứng dụng quyết định**

### 3.1. Cách đơn giản và mạnh nhất: không lấy tên lưu từ server

Giả sử ứng dụng đang tải báo cáo do API cung cấp. Thay vì đọc `Content-Disposition.filename` để tạo path, hãy đặt tên có quy tắc từ **ID đã được kiểm soát** hoặc tên do ứng dụng tự sinh:

```text
Trusted download directory: /srv/app/downloads
Application-selected name:  invoice-2026-001.pdf
Server Content-Disposition: attachment; filename="../../config.yml"

Final intended path: /srv/app/downloads/invoice-2026-001.pdf
Untrusted server filename: bỏ qua, có thể ghi log dưới dạng đã escape nếu cần
```

Ví dụ trên minh họa đường dẫn Unix; trên Windows áp dụng cùng nguyên tắc nhưng cú pháp path khác. Nếu cần giữ tên gốc để hiển thị trong UI, lưu **display name** như metadata riêng, không trực tiếp chuyển nó thành tên hệ thống file.

**Không xem header Content-Disposition là mệnh lệnh**. RFC 6266 xem tên được gợi ý qua `filename`/`filename*` là đầu vào cần xử lý an toàn. Nó có thể có percent encoding, Unicode, dấu phân cách đường dẫn, tên ẩn, extension gây hiểu sai và những hình thức tấn công dựa trên khác biệt giữa hệ điều hành.

### 3.2. Nếu người dùng được phép đặt tên, dùng allowlist nghiêm

Một chính sách đơn giản, có tính portable:

```java
private static final Pattern SAFE_NAME =
        Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,79}");

private static final Pattern WINDOWS_DEVICE = Pattern.compile(
        "(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\\..*)?");

static String validateName(String name) {
    if (name == null || !SAFE_NAME.matcher(name).matches()
            || name.endsWith(".")
            || WINDOWS_DEVICE.matcher(name).matches()) {
        throw new IllegalArgumentException("Unsafe filename");
    }
    return name;
}
```

*Mảnh code trong class có import `java.util.regex.Pattern`; cùng hàm được dùng trong chương trình độc lập ở mục 9.*

Nó cố ý chỉ cho phép **tên đơn ASCII** (tối đa 80 ký tự) bắt đầu bằng chữ/số và những ký tự tiếp theo thuộc `[A-Za-z0-9._-]`. Vì vậy reject `../secret`, `..\\secret`, `C:\\...`, `/tmp/x`, khoảng trắng lạ, ký tự điều khiển và dấu `:`; loại thêm tên thiết bị Windows cơ bản như `CON`, `NUL.txt`. Hạn chế dấu chấm cuối tránh một số bất đồng diễn giải tên trên Windows.

Không coi regex này là giải pháp duy nhất cho **mọi** tên file trên mọi filesystem. Đặc biệt nếu hỗ trợ Unicode, cần chính sách normalize NFC, đối phó ký tự nhìn giống nhau, tên Windows đặc biệt, trailing dot/space, phân biệt case trên filesystem và độ dài **theo byte** của path. Nếu cần đuôi file theo media type, nên **chọn extension từ loại file đã được xác thực**, không chỉ sao chép extension do server đề xuất.

### 3.3. Các cách sửa tên tưởng đúng nhưng chưa đủ

- `Paths.get(filename).getFileName()` phụ thuộc hệ điều hành. Trên Unix, ký tự `\\` có thể không được xem là separator; chuỗi Windows path có thể lọt qua nếu chỉ dựa vào hàm này.
- `filename.replace("../","")` chỉ bắt một dạng traversal, không bao phủ `..\\`, biến thể escape, double encoding và separator khác.
- `URLDecoder.decode(...)` không phải bộ xác thực filename; giải mã có thể biến `%2f` thành `/` hoặc gây khác biệt Unicode.
- Dùng basename của URL sau redirect cũng không bảo đảm an toàn; path URL có thể do attacker kiểm soát, không tương đương tên lưu cho ứng dụng.
- Không được lấy dấu mở rộng `.exe` hay `.pdf` làm chứng nhận nội dung: server có thể gửi HTML/error page hoặc executable nhưng khai một tên rất đẹp.

Nếu phải hỗ trợ `Content-Disposition`, hãy dùng parser tuân RFC 6266/5987 và **sau đó vẫn áp chính sách tên riêng**. Ưu tiên `filename*` theo quy tắc của chuẩn khi cả hai cùng xuất hiện, nhưng **không lấy kết quả parse làm quyền chọn đường dẫn**.

## 4. Đường dẫn đích: `Path.resolve`, `normalize` và sự thật về symlink

Không nối chuỗi như:

```java
// PHẢN VÍ DỤ: filename có thể là "../secret.txt".
Path bad = Path.of(downloadDirString + "/" + serverFilename);
```

*Mảnh code cố ý thiếu các biến khai báo; không dùng trong production.*

Khi đã có tên đáng tin, dùng Java NIO:

```java
Path directory = trustedDirectory.toAbsolutePath().normalize();
String safeName = validateName(chosenName);
Path destination = directory.resolve(safeName);
if (!destination.getParent().equals(directory)) {
    throw new IOException("Destination escaped directory");
}
```

*Mảnh code đặt trong phương thức có các biến và import tương ứng; chương trình chạy ở mục 9 dùng cùng logic.* Dấu `/` trong string không nên là cách "tự nối path"; `resolve` dùng semantics path của filesystem.

**Kiểm tra đường dẫn theo từng lớp:**

1. **Directory gốc phải được quản trị:** lấy từ cấu hình dịch vụ tin cậy, không ghép trực tiếp từ request body/HTTP header. Tạo thư mục với quyền phù hợp và không cho user không tin cậy ghi file/symlink vào đó.
2. **Tên con phải là một filename**, không phải relative path có nhiều segment. Kiểm tra `validateName` *trước* `resolve`.
3. **Containment check** bằng các thành phần `Path` (`startsWith`/`getParent`) là phòng tuyến bổ sung; tránh so sánh raw string prefix kiểu `"/data/reports2".startsWith("/data/reports")`.
4. **Symlink/hardlink:** `normalize()` và kiểm tra lexical containment **không** loại bỏ nguy cơ một thư mục thành phần hoặc file đích bị thay thành symlink. `Files.isDirectory(..., LinkOption.NOFOLLOW_LINKS)` là một check có ích cho phần cuối, nhưng không khóa đường đi trong lúc thao tác.
5. **TOCTOU (time-of-check to time-of-use):** giữa `Files.exists` và `Files.move`, một tác nhân khác có thể thay file/path. Cần quyền filesystem phù hợp, thư mục riêng của ứng dụng, thao tác không ghi đè và thiết kế đồng bộ.
6. **Đối thủ có quyền sửa thư mục đích** là bài toán khó hơn nhiều. Cân nhắc `SecureDirectoryStream` khi provider hỗ trợ, thao tác tương đối với directory handle, hoặc API OS cấp thấp với semantics no-follow/atomic phù hợp. Không gán tính năng an toàn tuyệt đối cho một phép `resolve().normalize()`.

Một chính sách thực tế: dịch vụ tự tạo thư mục chứa file tải, chỉ dịch vụ có quyền write, người dùng cuối chỉ đọc/nhận đường dẫn sau khi complete, và không bao giờ cho upload/file user tùy ý tạo symlink trong cùng thư mục.

## 5. Tại sao phải dùng file tạm trong **cùng thư mục**

Nguyên tắc: **không download trực tiếp vào tên cuối**.

Không nên:

```java
// PHẢN VÍ DỤ: nếu luồng chết giữa chừng, report.pdf đã tồn tại
// nhưng có thể chứa 20% nội dung.
Files.copy(response.body(), destination);
```

Thay vào đó:

```java
Path partial = Files.createTempFile(directory, ".download-", ".part");
boolean committed = false;
try {
    // Stream bytes -> partial; kiểm tra length, size limit, digest...
    // Chỉ xuất bản final destination khi mọi kiểm tra đã PASS.
    Files.move(partial, destination); // Không truyền REPLACE_EXISTING.
    committed = true;
} finally {
    if (!committed) {
        Files.deleteIfExists(partial);
    }
}
```

*Đây là skeleton minh họa; không phải chương trình hoàn chỉnh vì thiếu các biến và code ghi bytes.*

Lợi ích:

- Một tên tạm **ngẫu nhiên** tránh va chạm giữa nhiều lượt tải.
- Dùng `createTempFile(directory,...)` ngay **trong thư mục đích** giúp tránh việc vô tình copy qua filesystem khác khi commit và dễ quản lý file còn dang dở.
- File chưa hoàn chỉnh có extension `.part`, không bị xem là tài liệu cuối.
- Khi nhận lỗi, ứng dụng **chỉ xóa file tạm do chính lượt tải tạo ra**; không xóa file cuối hoặc xóa tất cả `*.part` bất kể ai sở hữu.
- Trong `finally`, nếu `move` thất bại, `partial` được xóa; file đã tồn tại vẫn phải giữ nguyên.

**Cảnh báo về tính nguyên tử:** `Files.move(partial, destination)` **không có `ATOMIC_MOVE`** nên Java không cam kết publish là nguyên tử hay crash-safe trong mọi filesystem/provider. Trên nhiều filesystem cục bộ, move/rename trong cùng thư mục có hành vi gần như nguyên tử, nhưng **không thể suy từ đó thành bảo đảm chung của API**.

Nếu hệ thống yêu cầu commit atomic, phải kiểm tra filesystem hỗ trợ `StandardCopyOption.ATOMIC_MOVE` và chiến lược **không ghi đè**. Với `ATOMIC_MOVE`, Java nói hành vi **khi target đã tồn tại là implementation-specific**; không được kết luận chỉ cần thêm `ATOMIC_MOVE` là vừa atomic vừa no-clobber tuyệt đối. Có thể cần cơ chế reserve tên, khóa/điều phối một writer, hard-link no-clobber trên filesystem hỗ trợ hoặc primitive hệ điều hành có semantics mong muốn.

**Độ bền (durability) khi mất điện** cũng khác với tính atomic: nơi cần durability cao có thể cần `FileChannel.force(...)` và fsync thư mục theo hỗ trợ nền tảng. Download hoàn thành ở tầng ứng dụng không tự bảo đảm byte đã được flush vật lý trước power loss.

## 6. Kiểm tra status và header trước khi ghi

Đối với download toàn bộ file bằng `GET`, quy tắc dễ kiểm chứng là chỉ chấp nhận **`200 OK`** (và áp dụng protocol riêng nếu bạn chủ động hỗ trợ status khác):

| HTTP status | Ý nghĩa ở downloader đơn giản |
| --- | --- |
| `200 OK` | Có thể là full representation; vẫn phải stream đủ và kiểm tra |
| `206 Partial Content` | **Không** được coi là full file nếu không có protocol range/resume cụ thể |
| `301/302/307/308` | Redirect; không tự theo nếu đích chưa được policy cho phép |
| `304 Not Modified` | Không có response body tải mới; chỉ dùng khi có cache validator và bản đã xác thực |
| `401/403` | Auth/permission fail; không lưu error page như file đích |
| `404` | Không tồn tại; không lưu nội dung lỗi dưới tên file yêu cầu |
| `416 Range Not Satisfiable` | Range/resume không hợp lệ; không coi là dữ liệu hoàn chỉnh |
| `429/503` | Rate-limit/quá tải; áp dụng retry/backoff có điều kiện, không publish |
| Status thành công khác, ví dụ `204` | Không tự suy có full file; cần hợp đồng API cụ thể |

**Lưu ý:** `HttpClient.Redirect.NEVER` có thể được cấu hình trên Java HttpClient để không tự đi theo redirect. Nếu cho phép redirect, phải kiểm tra **mỗi** location/đích mới theo HTTPS, host allowlist và chính sách chống SSRF. Đừng tin rằng bắt đầu từ HTTPS nghĩa là mọi redirect giữ HTTPS.

### 6.1. `Content-Length` là byte count, không phải chứng cứ integrity

Giá trị `Content-Length` tính số byte của HTTP content theo quy tắc protocol, **không phải ký tự**. Với server trả content gzip, nó thường phản ánh bytes encoded; nếu thư viện giải content coding trước khi đưa body đến app, phải hiểu rõ số bytes mà app đọc còn tương ứng với header hay không.

Một downloader streaming nên:

- Có `MAX_BYTES` từ **chính sách ứng dụng**, không từ `Content-Length` của server.
- Nếu server khai Content-Length lớn hơn max, có thể **reject sớm**.
- Khi đọc, vẫn **đếm bytes thực** và fail ngay trước khi ghi thêm vượt quá giới hạn.
- Khi có declared Content-Length và app nhận đúng những bytes mà header mô tả, có thể so số bytes nhận sau stream EOF.
- Khi không có Content-Length (ví dụ chunked HTTP/1.1 hoặc HTTP/2), vẫn áp max bytes và xử lý completion/error của HTTP stack.
- Nhớ rằng Content-Length khai đúng nhưng server gửi **một file khác có cùng kích thước** thì vẫn không phát hiện được. Dùng checksum tin cậy hoặc chữ ký/manifest khi yêu cầu integrity.

Không nên cấp trước byte array có kích thước bằng untrusted Content-Length. Dùng `InputStream` và buffer 8 KiB/64 KiB với hạn mức đếm byte.

### 6.2. `Content-Encoding` và định dạng bytes

Nếu server trả `Content-Encoding: gzip`, có hai mục tiêu khác nhau:

1. **Lưu nguyên encoded HTTP content:** file sẽ chứa bytes gzip; digest và Content-Length áp cho encoded bytes đó.
2. **Lưu decoded representation:** cần giải gzip, đặt **limit riêng cho bytes sau giải nén**, tính digest phù hợp và có chính sách extension/media type rõ ràng.

Trong ví dụ mục 9, downloader **chỉ chấp nhận không có Content-Encoding hoặc `identity`**, nhằm không biến những bytes nén thành file có extension misleading. Với ứng dụng hỗ trợ gzip, phải thiết kế pipeline và giới hạn tương ứng; không đổi tùy tiện giữa encoded và decoded bytes.

### 6.3. `Content-Disposition` là gợi ý, không phải quyền ghi file

Header có thể là:

```http
Content-Disposition: attachment; filename="../../outside.txt"
Content-Type: text/plain
Content-Length: 22
```

Ví dụ cố ý có tên chứa traversal. Downloader **bỏ qua filename đó** và chỉ dùng tên đáng tin `report.txt`. Đây là hành vi kiểm thử thực tế của chương trình bên dưới.

Không copy raw header vào log không escape nếu nó chứa CR/LF hoặc ký tự điều khiển; nhiều HTTP parser đã lọc header syntax nhưng code log/report vẫn phải tự bảo vệ.

## 7. Thế nào là "tải chưa hoàn tất" và khi nào biết tải đã hoàn tất?

Một luồng tải có thể dừng vì nhiều nguyên nhân:

```text
CONNECTED
    |
    v
HTTP HEADERS RECEIVED
    |
    +--> status không hợp lệ / declared size > limit -> REJECT
    |
    v
TEMP_CREATED
    |
    v
STREAMING BYTES
    |
    +--> timeout / EOF sớm / read IOException -> FAILED + DELETE TEMP
    +--> disk full / write IOException -> FAILED + DELETE TEMP
    +--> actual bytes > max -> FAILED + DELETE TEMP
    |
    v
STREAM ENDED SUCCESSFULLY
    |
    +--> declared size mismatch -> FAILED + DELETE TEMP
    +--> trusted digest mismatch -> FAILED + DELETE TEMP
    +--> media-type/content policy fail -> FAILED + DELETE TEMP
    |
    v
COMMIT TO FINAL PATH
    |
    +--> destination already exists / move fail -> FAILED
    |
    v
COMPLETE
```

**Chỉ báo hoàn tất an toàn tối thiểu** là: HTTP status phù hợp, streaming body không ném exception, giới hạn bytes không bị vượt, kiểm tra expected size/hash theo chính sách vượt qua, và **publish thành công**. Đừng coi HTTP 200, việc file tạm xuất hiện hoặc nhận được N bytes đầu tiên là "đã tải xong".

Cụ thể:

- **HTTP/1.1 Content-Length:** nếu server khai 100 bytes nhưng kết nối chỉ gửi 25 rồi đóng, HTTP client có thể báo lỗi vì body incomplete. Java `HttpClient.BodyHandlers.ofInputStream()` giúp phát hiện qua exception khi đọc, vì việc `send(...)` trả về không có nghĩa InputStream đã được tiêu thụ hết.
- **Chunked HTTP/1.1:** một kết nối có thể đóng trước **terminating zero-size chunk**; HTTP stack tuân chuẩn thường báo framing error, không phải chỉ EOF bình thường.
- **HTTP/2:** stream có frame/end-of-stream signaling riêng; không dựa vào đóng TCP để biết một stream thành công. Thư viện HTTP phải chịu trách nhiệm xử lý và thông báo lỗi.
- **Không có length hoặc trusted digest:** một response được server **đóng hợp lệ nhưng tự tuyên bố payload ngắn hơn nội dung thật** có thể vẫn là HTTP message hợp lệ; downloader không thể đoán phần còn thiếu chỉ từ số bytes thấy. Muốn biết đúng file kỳ vọng, phải có **expected length/checksum từ kênh tin cậy**.
- **Disk write fail:** dù mạng hoàn toàn tốt, ghi ra ổ hết dung lượng hoặc không có quyền là thất bại tải ở tầng ứng dụng. Không publish file dở dang.
- **Process crash/power loss:** `finally` chỉ chạy trong execution bình thường qua stack unwinding, **không bảo đảm chạy khi process bị kill hoặc máy mất điện**. Cần cơ chế kiểm kê/recovery những file `.part` cũ vào lúc khởi động theo owner/session/age, tránh xóa nhầm tệp đang được tác vụ khác dùng.

Việc kiểm tra hash không tự giải quyết nguồn file có đáng tin hay không. **Expected SHA-256 phải đến từ một nguồn độc lập/tin cậy**, ví dụ manifest được ký hoặc metadata đã được bảo vệ và xác thực; nếu lấy digest do chính server bị tấn công gửi cùng payload, attacker có thể thay cả hai.

## 8. Thiết kế downloader streaming trên Java 17

Các lớp Java liên quan:

| API | Vai trò |
| --- | --- |
| `HttpClient.newBuilder()` | Cấu hình kết nối, proxy/redirect, connect timeout |
| `HttpRequest.newBuilder(uri).GET()` | Tạo GET request |
| `HttpResponse.BodyHandlers.ofInputStream()` | Trả response body dưới dạng stream để xử lý từng khối |
| `HttpResponse.statusCode()` | Tách response lỗi khỏi file content |
| `HttpHeaders.firstValueAsLong("Content-Length")` | Tham khảo độ dài khai báo, có thể vắng |
| `Files.createTempFile(directory, ..., ".part")` | Tạo file tạm duy nhất trong thư mục đích |
| `Files.newOutputStream(partial, WRITE)` | Ghi bytes mà không cần giữ toàn bộ trong RAM |
| `MessageDigest.getInstance("SHA-256")` | Tính hash cập nhật khi streaming |
| `Files.move(partial, destination)` | Bước publish theo chính sách không cố ý ghi đè |
| `Files.deleteIfExists(partial)` | Dọn file tạm khi chưa commit |
| `LinkOption.NOFOLLOW_LINKS` | Kiểm tra đối tượng không follow link trong phạm vi hỗ trợ của API |

Thứ tự quan trọng của một hàm download:

1. Kiểm tra **tên file và cấu hình path** trước network request.
2. Chỉ cho phép URI trong policy (chương trình demo hardcode loopback); đặt redirect policy rõ ràng.
3. Gửi request, **đóng response InputStream** trong mọi nhánh, kể cả status lỗi.
4. Chỉ nhận status phù hợp, reject content coding không hỗ trợ, reject Content-Length đã biết vượt ngưỡng.
5. Tạo `.part`, stream body qua một mảng byte nhỏ; cập nhật size và hash **trên chính bytes được ghi**.
6. Sau EOF hợp lệ, validate length và expected digest.
7. Publish thành tên đã được duyệt; nếu không hoàn thành publish, xóa file tạm trong `finally`.
8. Chỉ trả thành công **sau** khi bước publish hoàn tất.

**Java 17 `HttpClient` không phải `AutoCloseable`**, vì vậy không dùng `try (HttpClient client = ...)` trong ví dụ nhắm `--release 17`. Client được tái sử dụng giữa nhiều request.

## 9. Chương trình Java 17 hoàn chỉnh: thành công và sáu lỗi phải bị từ chối

Ví dụ này chạy hoàn toàn trên loopback và tự tạo thư mục tạm để test. Nó có các đặc điểm:

- `HttpServer` trả body bình thường và cố tình gửi `Content-Disposition` có filename `../../outside.txt`. Ứng dụng **không dùng tên file của server**, mà tự chọn `report.txt`.
- `HttpClient` đặt `Redirect.NEVER`, có kết nối và request timeout ở mức demo, body được nhận qua `ofInputStream()`.
- File được stream qua `.part`; có max bytes và hash SHA-256 từ caller.
- Trước khi publish, mã kiểm tra size, hash và trạng thái; không dùng `REPLACE_EXISTING` để tránh chủ ý ghi đè.
- Chương trình kiểm tra traversal, file đã tồn tại, sai checksum, oversized response, stream bị cắt ngang và HTTP 404.
- Cuối bài test, thư mục chỉ còn **một file thành công** (file report). File tạm từ những lượt thất bại đã được xóa.

**Tệp `SafeHttpDownloadDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HexFormat;
import java.util.regex.Pattern;

public final class SafeHttpDownloadDemo {
    private static final Pattern SAFE_NAME =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,79}");
    private static final Pattern WINDOWS_DEVICE = Pattern.compile(
            "(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\\..*)?");

    static String validateName(String name) {
        if (name == null || !SAFE_NAME.matcher(name).matches()
                || name.endsWith(".")
                || WINDOWS_DEVICE.matcher(name).matches()) {
            throw new IllegalArgumentException("Unsafe filename");
        }
        return name;
    }

    static long download(HttpClient client, URI uri, Path trustedDirectory,
            String chosenName, long maxBytes, String expectedSha256)
            throws Exception {
        String filename = validateName(chosenName);
        if (!"http".equalsIgnoreCase(uri.getScheme())
                || !"127.0.0.1".equals(uri.getHost())) {
            throw new IllegalArgumentException("Demo permits loopback only");
        }
        if (maxBytes < 0) {
            throw new IllegalArgumentException("Invalid byte limit");
        }

        Path directory = trustedDirectory.toAbsolutePath().normalize();
        if (!Files.isDirectory(directory, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("Not a trusted physical directory");
        }
        Path destination = directory.resolve(filename);
        if (!destination.getParent().equals(directory)) {
            throw new IOException("Destination escaped directory");
        }
        if (Files.exists(destination, LinkOption.NOFOLLOW_LINKS)) {
            throw new FileAlreadyExistsException(destination.toString());
        }

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
        HttpResponse<InputStream> response = client.send(request,
                HttpResponse.BodyHandlers.ofInputStream());

        try (InputStream stream = response.body()) {
            if (response.statusCode() != 200) {
                throw new IOException("Expected HTTP 200");
            }
            if (response.headers().firstValue("Content-Encoding")
                    .filter(v -> !v.equalsIgnoreCase("identity"))
                    .isPresent()) {
                throw new IOException("Unexpected content coding");
            }
            long declared = response.headers()
                    .firstValueAsLong("Content-Length").orElse(-1L);
            if (declared > maxBytes) {
                throw new IOException("Declared content too large");
            }

            Path partial = Files.createTempFile(directory,
                    ".download-", ".part");
            boolean committed = false;
            try {
                MessageDigest sha = MessageDigest.getInstance("SHA-256");
                long count = 0;
                byte[] buffer = new byte[8192];
                try (OutputStream output = Files.newOutputStream(partial,
                        StandardOpenOption.WRITE)) {
                    int n;
                    while ((n = stream.read(buffer)) != -1) {
                        if (n > maxBytes - count) {
                            throw new IOException("Stream exceeds byte limit");
                        }
                        output.write(buffer, 0, n);
                        sha.update(buffer, 0, n);
                        count += n;
                    }
                }
                if (declared >= 0 && count != declared) {
                    throw new IOException("Content-Length mismatch");
                }
                String actualHash = HexFormat.of()
                        .formatHex(sha.digest());
                if (expectedSha256 != null
                        && !actualHash.equalsIgnoreCase(expectedSha256)) {
                    throw new IOException("SHA-256 mismatch");
                }
                Files.move(partial, destination); // No REPLACE_EXISTING.
                committed = true;
                return count;
            } finally {
                if (!committed) {
                    Files.deleteIfExists(partial);
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = "Hello, safe download!\n".getBytes(
                StandardCharsets.UTF_8);
        Path directory = Files.createTempDirectory("safe-download-example-");
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/good", exchange -> {
            try (exchange) {
                exchange.getResponseHeaders().set("Content-Disposition",
                        "attachment; filename=\"../../outside.txt\"");
                exchange.sendResponseHeaders(200, bytes.length);
                exchange.getResponseBody().write(bytes);
            }
        });
        server.createContext("/truncated", exchange -> {
            try (exchange) {
                exchange.sendResponseHeaders(200, bytes.length + 10);
                exchange.getResponseBody().write(bytes, 0, 3);
            } catch (IOException expectedAbort) {
                // The response was intentionally truncated.
            }
        });
        server.createContext("/too-large", exchange -> {
            try (exchange) {
                exchange.sendResponseHeaders(200, bytes.length);
                exchange.getResponseBody().write(bytes);
            } catch (IOException earlyClose) {
                // Client can close after checking Content-Length.
            }
        });
        server.createContext("/missing", exchange -> {
            try (exchange) {
                byte[] msg = "Missing".getBytes(StandardCharsets.US_ASCII);
                exchange.sendResponseHeaders(404, msg.length);
                exchange.getResponseBody().write(msg);
            }
        });
        server.start();
        try {
            String prefix = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            HttpClient client = HttpClient.newBuilder()
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .connectTimeout(Duration.ofSeconds(3)).build();
            String expectedHash = HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(bytes));
            long saved = download(client, URI.create(prefix + "/good"),
                    directory, "report.txt", 1024, expectedHash);
            System.out.println("saved bytes=" + saved
                    + ", contentMatch=" + MessageDigest.isEqual(
                            bytes, Files.readAllBytes(
                                    directory.resolve("report.txt"))));
            try {
                download(client, URI.create(prefix + "/good"),
                        directory, "../outside.txt", 1024, expectedHash);
                throw new AssertionError("Traversal should be rejected");
            } catch (IllegalArgumentException expected) {
                System.out.println("traversal: rejected");
            }
            try {
                download(client, URI.create(prefix + "/good"),
                        directory, "report.txt", 1024, expectedHash);
                throw new AssertionError("Existing file should be rejected");
            } catch (FileAlreadyExistsException expected) {
                System.out.println("existing file: preserved");
            }
            try {
                download(client, URI.create(prefix + "/good"),
                        directory, "bad-checksum.bin", 1024,
                        "0".repeat(64));
                throw new AssertionError("Checksum should fail");
            } catch (IOException expected) {
                System.out.println("checksum: rejected");
            }
            try {
                download(client, URI.create(prefix + "/too-large"),
                        directory, "too-large.bin", 4, null);
                throw new AssertionError("Oversize should fail");
            } catch (IOException expected) {
                System.out.println("oversize: rejected");
            }
            try {
                download(client, URI.create(prefix + "/truncated"),
                        directory, "truncated.bin", 1024, null);
                throw new AssertionError("Truncation should fail");
            } catch (IOException expected) {
                System.out.println("truncated: rejected");
            }
            try {
                download(client, URI.create(prefix + "/missing"),
                        directory, "missing.bin", 1024, null);
                throw new AssertionError("404 should fail");
            } catch (IOException expected) {
                System.out.println("HTTP 404: rejected");
            }

            try (var paths = Files.list(directory)) {
                System.out.println("remaining files="
                        + paths.count());
            }
        } finally {
            server.stop(0);
            try (var files = Files.list(directory)) {
                files.forEach(p -> {
                    try {
                        Files.delete(p);
                    } catch (IOException ex) {
                        throw new RuntimeException(ex);
                    }
                });
            }
            Files.delete(directory);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 (module `jdk.httpserver` dùng để tạo server nội bộ):

```bash
javac --release 17 --add-modules jdk.httpserver SafeHttpDownloadDemo.java
java --add-modules jdk.httpserver SafeHttpDownloadDemo
```

**Stdout đã xác minh bằng việc biên dịch và chạy thật:**

```text
saved bytes=22, contentMatch=true
traversal: rejected
existing file: preserved
checksum: rejected
oversize: rejected
truncated: rejected
HTTP 404: rejected
remaining files=1
```

### 9.1. Vì sao mỗi kiểm thử có ý nghĩa?

- `saved bytes=22`: payload được viết đủ 22 byte, xác minh bằng SHA-256 tin cậy từ dữ liệu test và đối chiếu bytes file sau khi publish.
- `traversal: rejected`: tên `../outside.txt` không qua được validator; không có đường dẫn ngoài thư mục được tạo.
- `existing file: preserved`: lượt tải thứ hai không được ghi đè `report.txt` đã tồn tại.
- `checksum: rejected`: dữ liệu stream hợp lệ nhưng **khác digest kỳ vọng**, nên chỉ có `.part` tạm trong lúc nhận; file cuối `bad-checksum.bin` không được tạo.
- `oversize: rejected`: declared Content-Length 22 byte lớn hơn limit 4 byte, client đóng body và không xuất bản.
- `truncated: rejected`: server khai lớn hơn nhưng chỉ viết 3 byte rồi đóng; client đọc body phát sinh lỗi hoặc kiểm tra độ dài không đạt, không publish `truncated.bin`.
- `HTTP 404: rejected`: error page không được lưu như download thành công.
- `remaining files=1`: chỉ còn `report.txt` sau tất cả các test; không còn file `.part` bị bỏ dở. Sau khi in kết quả, chương trình xóa dữ liệu test trong thư mục do nó vừa tự tạo.

**Đây là demo, không phải downloader production hoàn chỉnh.** Nó cố ý chỉ cho URL `http://127.0.0.1` để kiểm thử an toàn không cần TLS. Để dùng thật, **không** đơn giản thay điều kiện thành "mọi HTTP/HTTPS URI"; cần HTTPS, allowlist origin và egress policy. Ví dụ cũng giả định `trustedDirectory` do ứng dụng tự kiểm soát, không có attacker thay symlink trong quá trình chạy; check `isDirectory(NOFOLLOW_LINKS)` và `getParent()` không tự giải quyết mọi race. API `Files.move` không có `ATOMIC_MOVE` nên không được quảng cáo là publish atomic trên mọi nền tảng.

### 9.2. Vì sao không dùng `BodyHandlers.ofFile(destination)` ngay?

`BodyHandlers.ofFile(...)` thuận tiện khi tải bình thường, nhưng nếu ứng dụng cần **file tạm, kiểm soát kích thước, checksum, kiểm tra header trước khi publish, cleanup và tên an toàn**, việc ghi thẳng đến destination cuối có thể gây khó khăn:

- File có thể đã được tạo và có bytes chưa đủ khi request thất bại.
- Status 404/500 vẫn có response body; nếu không tách theo status, bạn có thể lưu error page.
- Khó bảo đảm người tiêu thụ khác không đọc file trước khi kết thúc và verify.
- Nếu target đã tồn tại, cần bảo đảm không ghi đè theo policy.

`ofFileDownload(directory, options...)` cũng là convenience API, **không tự thay toàn bộ kiểm soát** về filename, đường dẫn, trusted content và recovery. Khi có yêu cầu bảo mật riêng, `BodyHandlers.ofInputStream()` và một bước commit rõ ràng dễ kiểm toán hơn.

## 10. Phân biệt Content-Length, EOF, checksum và complete response

| Cơ chế | Phát hiện được gì? | Không phát hiện được gì? |
| --- | --- | --- |
| HTTP status 200 | Server tuyên bố request được xử lý thành công | Bytes có đủ, đúng file hay an toàn |
| Content-Length đã khai | Expected byte count của HTTP content trong trường hợp phù hợp | Hai file cùng số byte; server khai sai nhưng framing tự-consistent |
| HTTP stream completion | Body đã được HTTP stack đọc tới điểm kết thúc hợp lệ | Nội dung có đúng manifest của ứng dụng hay không |
| Byte limit tự áp | Không vượt quá ngân sách tải đã định | File dưới limit nhưng độc hại |
| SHA-256 từ manifest tin cậy | Bytes tải giống digest kỳ vọng với xác suất va chạm không đáng kể | Nguồn manifest đáng tin nếu nó cũng bị attacker kiểm soát |
| Phân tích media format/file signature | Không phải mọi bytes đều hợp lệ cho định dạng mong đợi | Malware trong tài liệu hợp lệ, lỗi parser, quyền sử dụng |
| Temp + commit | File cuối không lộ khi còn download/validation chưa pass trong luồng bình thường | Atomic/durability trên mọi filesystem, crash/symlink race không được xử lý |

**Trường hợp tinh vi:** nếu server trả `200 OK` với body 100 byte và `Content-Length: 100`, trong khi file thật đáng lẽ 1 MB, mọi cơ chế framing của HTTP có thể kết thúc hợp lệ. Không có expected digest/size **được tin cậy độc lập**, client không thể biết file này chỉ là một phần bị server cắt *về mặt nội dung logic*. Vì vậy phần "xử lý chưa hoàn tất" cần cả hai tầng:

- **Protocol-level incomplete:** missing bytes theo framing, TCP reset, streaming exception.
- **Application-level incomplete/wrong:** đúng framing nhưng không đúng artifact kỳ vọng. Cần digest, version, manifest hoặc metadata đáng tin.

Nếu checksum bị mismatch, hãy **giữ file cuối cũ và xóa file tạm**, không "phục hồi bằng cách ghi thêm vài byte" ngẫu nhiên vào file được coi là hoàn tất.

## 11. Tải tiếp khi bị ngắt: `Range`, `If-Range`, `ETag`

Một chiến lược **resume** có thể tiết kiệm băng thông khi file rất lớn, nhưng khó hơn retry từ đầu:

```text
Lượt 1:
  GET /large.bin
  200 OK, ETag: "strong-v1", Content-Length: 5000000
  nhận 2000000 byte -> đứt mạng
  giữ .part + metadata kiểm soát: URI, validator, count, hash state

Lượt 2:
  GET /large.bin
  Range: bytes=2000000-
  If-Range: "strong-v1"

Server có thể:
  206 Partial Content + Content-Range: bytes 2000000-4999999/5000000
    -> chỉ append khi range, identity, size, coding và validator hợp lệ
  200 OK
    -> representation thay đổi/Range bị bỏ qua; tải lại TỪ ĐẦU
  416 Range Not Satisfiable
    -> không append mù; kiểm tra metadata và restart theo policy
```

**Đây là sơ đồ, không phải code resume hoàn chỉnh.** Khi triển khai cần:

1. Một tên file `.part` gắn với job và metadata tương ứng; không trộn dữ liệu từ hai tài nguyên hoặc hai version khác nhau.
2. Dùng **strong validator** như strong ETag cho `If-Range` khi có thể; weak ETag không dùng được làm validator If-Range theo cách tương đương.
3. Kiểm tra `206` thực sự có `Content-Range` khớp offset yêu cầu, tổng kích thước, server validator và dữ liệu đã lưu.
4. Khi nhận `200` thay vì `206`, **không append** body mới vào file cũ. Phải restart từ byte 0 với file tạm mới.
5. Nếu response có content coding, đảm bảo byte offsets tương ứng đúng representation; nhiều workflow resume cần dùng `Accept-Encoding: identity` theo hợp đồng server.
6. Khi download hoàn tất, kiểm tra tổng length và **trusted digest** của toàn bộ file, không chỉ các segment mới nhận.
7. Giữ giới hạn TTL, quota đĩa và cleanup cho file tạm còn lại nếu crash; đừng giữ vĩnh viễn hoặc để người dùng đọc như file hoàn chỉnh.

Với file nhỏ/vừa, **retry từ đầu vào file tạm mới** thường đơn giản và ít lỗi hơn resume. Không triển khai Range nếu không có nhu cầu và server không đảm bảo validator đáng tin.

## 12. Redirect, HTTPS và SSRF: file hợp lệ nhưng nguồn sai vẫn nguy hiểm

Một downloader nhận URI do người dùng cung cấp có thể bị lợi dụng truy cập **dịch vụ nội bộ** từ phía server chạy downloader:

```text
User-controlled URL -> http://127.0.0.1:... 
                    -> http://169.254.169.254/...
                    -> http://internal-db/...
                    -> redirect từ host public tới host private
```

Những URL như vậy phải bị policy từ chối trong tình huống untrusted-URL ingestion. Test demo sử dụng `127.0.0.1` **chỉ vì server/client chạy chung JVM**, không phải gợi ý mở loopback/metadata service trên production.

Một hệ thống thực tế nên:

- Chỉ tải từ những **origin/host đã được cho phép** và scheme HTTPS; xác thực certificate/hostname theo chính sách TLS chuẩn.
- Không cho phép redirect mặc định hoặc **revalidate từng hop** cả host, scheme, port và destination IP. Không cho HTTPS → HTTP downgrade.
- Có **egress firewall/network policy** chặn IP nội bộ/metadata/loopback/link-local khi downloader phục vụ URI không đáng tin, kể cả DNS rebinding.
- Không log token/cookie trong URL và không tự forward `Authorization` sang một host ngoài allowlist qua redirect.
- Giới hạn port, DNS lookup, số redirect, response headers/body, download duration và tổng đồng thời.
- Không coi một tên miền nhìn hợp lệ là đủ nếu DNS trả IP private hoặc biến đổi trong quá trình connect.

Lưu file đúng đường dẫn vẫn chưa an toàn nếu **nguồn tải là attacker**. Cũng như vậy, HTTPS chỉ xác thực transport tới endpoint theo certificate/hostname policy; nó **không đảm bảo tài liệu bên trong không có malware**.

## 13. Timeout, cancellation, retries và resource cleanup

### 13.1. Các timeout không giống nhau

`HttpClient.Builder.connectTimeout(Duration)` hạn chế giai đoạn **thiết lập kết nối** theo API. `HttpRequest.Builder.timeout(Duration)` đặt thời gian chờ response request theo cơ chế của `HttpClient`. Nhưng khi dùng `BodyHandlers.ofInputStream()`, **`client.send(...)` có thể trả về khi headers/body stream sẵn sàng trước lúc tải hết file**.

Do đó **không tự suy rằng timeout của request sẽ giới hạn mọi lần `InputStream.read()` cho đến khi hoàn tất file**. Trong hệ thống thật, cần đo và quản lý thêm **deadline toàn download, idle-read timeout, tốc độ tối thiểu, cancellation và giới hạn bytes**; có thể chọn streaming handler bất đồng bộ/đóng stream/chạy job với cơ chế hủy rõ ràng và theo dõi thời hạn.

Mã demo sử dụng timeout 3 giây cho connect, 5 giây cho request nhằm tránh những lỗi cơ bản khi test; nó không mô tả một timeout end-to-end production chắc chắn cho tất cả lần đọc stream.

### 13.2. Khi người dùng hủy

Nếu hủy giữa chừng:

1. Đóng response `InputStream`/hủy subscription theo API để ngừng tiêu thụ bytes.
2. Đóng `OutputStream` và các file handles trước khi xóa `.part`.
3. Trạng thái job chuyển sang `CANCELLED`; không publish.
4. Nếu đã publish thành công trước khi hủy đến, cần quy tắc **race resolution**: không tự xóa file final vừa được job khác hoặc client khác sử dụng.
5. Đừng xóa toàn bộ file tên bắt đầu `.download-` của người khác; cần metadata owner/job ID và TTL cleanup riêng.

### 13.3. Khi retry

- Retry lỗi tạm thời (timeout, connection reset, 429/503 có policy) theo exponential backoff, jitter và hạn mức.
- Mỗi lượt retry từ đầu tạo **file tạm riêng**, không ghi thêm vào file chưa hoàn tất từ lượt trước trừ khi dùng protocol resume có kiểm chứng.
- Không tải lại vô hạn vì sẽ tiêu tốn bandwidth và tài nguyên.
- Trước khi retry, kiểm tra source/URI vẫn được phép; nếu có redirect hoặc URL expired, cập nhật token theo quy trình bảo mật.
- Nếu file đích đã xuất hiện từ lượt khác trong lúc chờ, đừng ghi đè; báo collision hoặc dùng phiên bản filename được quản lý.

## 14. Tính đúng đắn của publish và xử lý file trùng tên

Trên filesystem, còn hai yêu cầu cần nói rõ:

**(A) Không ghi đè file cũ.** Trong demo, có kiểm tra `Files.exists(destination, NOFOLLOW_LINKS)` và gọi `Files.move(partial, destination)` **không truyền `REPLACE_EXISTING`**. Theo semantics mặc định của `Files.move`, target đã tồn tại khiến move thất bại trừ các tình huống được API đặc tả. Với nhiều tác vụ/tiến trình cạnh tranh, kiểm tra `exists` vẫn có **race**; muốn bảo đảm mạnh thì cần cơ chế tạo/exclusive publication ở tầng filesystem và kiểm thử provider thực tế.

**(B) Không lộ file dở dang ở tên cuối.** Viết vào `partial` trước, verify rồi mới publish giảm rủi ro người tiêu thụ đọc nhầm file giữa chừng. Nhưng nếu muốn guarantee atomic visibility/crash consistency trên mọi filesystem, cách `Files.move` thường của demo chưa đủ. Cần thử `ATOMIC_MOVE` theo hỗ trợ **và** xây chiến lược no-clobber riêng, vì hành vi `ATOMIC_MOVE` khi destination đã tồn tại là provider-specific. Không dùng `REPLACE_EXISTING` tùy tiện.

Có thể áp chính sách tên tránh collision bằng server-side ID:

```text
invoice-7f4b8c2d.pdf     // tên dựa trên ID ngẫu nhiên/unique đã cấp
invoice-7f4b8c2d.pdf.part-<random>  // tệp tạm độc lập
```

Tuy nhiên **random tên file không thay thế quyền truy cập**, chống symlink hoặc cơ chế tạo file đích an toàn trong môi trường hostile. Với ứng dụng có nhiều worker, nên lưu metadata job trong database với uniqueness constraint (job ID/destination) để phối hợp publish và retry.

## 15. Validate nội dung tải: đừng chỉ nhìn extension và `Content-Type`

Sau khi tải bytes hoàn tất, còn lớp kiểm tra nội dung:

| Kiểu tài liệu | Kiểm tra hữu ích |
| --- | --- |
| PDF | Magic bytes, cấu trúc tệp, giới hạn page/size, xử lý của PDF reader an toàn |
| ZIP | ZIP magic/container, số entry, path traversal trong archive, giới hạn tổng bytes giải nén/ratio |
| PNG/JPEG | Header format và decoder có giới hạn; tránh tin extension |
| JSON | UTF-8 đúng, parser an toàn, schema/size/depth constraints |
| Executable/script | Chính sách tải/chạy nghiêm ngặt; không tự thực thi file tải |
| Bất kỳ loại nào | Trusted hash/signature nếu có, nguồn hợp lệ, kích thước giới hạn, scanner nếu yêu cầu |

**Zip Slip** là vấn đề khác nhưng liên quan: nếu tải và **giải nén** một ZIP, tên entry như `../../config.yml` cũng cần kiểm soát khi `resolve` vào thư mục giải nén, cộng phòng symlink và quota. Download path safe không tự làm extraction path safe.

Ngoài ra, khi UI gửi file cho trình duyệt tải về, HTTP response cần chính sách Content-Disposition/Content-Type/X-Content-Type-Options phù hợp; không tự render HTML từ một nguồn không đáng tin ngay trên origin chứa phiên đăng nhập.

## 16. Những lỗi phổ biến cần tránh

| Lỗi | Vì sao nguy hiểm | Sửa |
| --- | --- | --- |
| Ghi `response.body()` thẳng vào filename do server cung cấp | Path traversal và tên nguy hiểm | Ứng dụng chọn tên, allowlist và thư mục tin cậy |
| Coi `Path.normalize()` là sandbox chống symlink | Chỉ normalize cú pháp path | Kiểm soát directory ownership, no-follow, race |
| Bỏ qua file đã tồn tại | Có thể ghi đè dữ liệu | No-clobber policy và xử lý collision |
| Ghi thẳng file final trước khi stream kết thúc | Người khác thấy file dở dang | Tạo `.part` và publish sau kiểm tra |
| Chỉ kiểm tra HTTP status 200 | Body vẫn có thể bị cắt hoặc sai file | Stream completion, length, trusted digest |
| Chỉ tin `Content-Length` | Server có thể khai sai hoặc thiếu | Đếm bytes thực, limit và checksum |
| Gọi `readAllBytes()` cho file không giới hạn | Có thể tốn RAM rất lớn | Stream bằng buffer nhỏ với max bytes |
| Dùng `BodyHandlers.ofFile(final)` rồi coi file tồn tại là thành công | Trộn lẫn incomplete/error và published file | Ghi tạm, xác minh, commit |
| Bỏ qua HTTP 206 và append bừa | Hỏng nội dung do sai offset/version | Validate Range, If-Range, Content-Range |
| Retry download và append vào `.part` cũ mà không xác minh | Trộn nhiều phiên bản tài nguyên | Restart hoặc resume có validator mạnh |
| Bỏ qua Content-Encoding gzip | File được lưu khác representation mong muốn | Chọn giữ encoded hay giải nén có giới hạn |
| Checksum lấy từ chính response attacker kiểm soát | Attacker có thể thay cả file lẫn checksum | Digest từ manifest/nguồn được xác thực độc lập |
| Delete file final trong catch khi lỗi retry | Có thể xóa bản hoàn chỉnh đã tồn tại | Chỉ xóa partial do lượt tải sở hữu |
| Dùng redirect unrestricted cho URL untrusted | SSRF và HTTPS downgrade | Allowlist/revalidate mỗi hop hoặc Redirect.NEVER |
| File có đuôi PDF nên mở ngay | Bytes có thể là HTML/executable | Validate magic/format, scan theo policy |
| Quên đóng response InputStream | Leak connection/resource | `try (InputStream stream = response.body())` |
| Gọi `HttpClient` Java 17 trong try-with-resources | Java 17 chưa implements AutoCloseable | Tái sử dụng client; quản lý theo JDK |
| Tưởng Files.move thường là atomic/durable | Java không bảo đảm mọi provider | Thiết kế commit semantics và fsync phù hợp |
| Tin request timeout bao trùm toàn bộ stream body | `ofInputStream()` có vòng đọc riêng | Deadline/idle timeout/cancel ở mức download job |

## 17. Ma trận kiểm thử cho downloader thực tế

| Ca test | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| Tải thành công | 200, bytes đầy đủ, hash đúng | File final có đủ bytes, không còn partial |
| Tên traversal | `../outside.txt`, `..\\outside.txt` | Reject trước request, không tạo file ngoài directory |
| Tên hệ điều hành đặc biệt | `CON.txt`, trailing dot | Reject hoặc áp chính sách rename an toàn |
| Content-Disposition độc hại | `filename="../../outside.txt"` | Không tác động tới final path |
| File final đã tồn tại | `report.txt` cũ | Không ghi đè, file cũ còn nguyên |
| Connection đóng sớm | Khai 32 KB, gửi 4 KB rồi đóng | Incomplete, xóa partial, không publish |
| Truncated chunked/HTTP2 | Stream kết thúc lỗi framing | Không publish, cleanup |
| Body không có Content-Length | Dữ liệu hoàn tất hợp lệ | Đếm bytes, limit, digest nếu có |
| 404 trả HTML | Body có data nhưng status lỗi | Không lưu như tài liệu |
| 206 không do caller yêu cầu | Partial response | Reject, không coi full download |
| Body lớn hơn quota | Header lớn hoặc stream vượt max | Reject; dừng đọc, xóa partial |
| SHA-256 mismatch | Bytes khác manifest | Không publish |
| gzip encoded body | Header Content-Encoding | Decode có limit hoặc reject theo policy |
| Two concurrent downloads | Cùng tên file final | Chỉ một publish theo collision/lock strategy |
| Symlink trong directory | Đường dẫn bị thay trong lúc ghi | Không thoát thư mục; cần test OS-specific |
| Process kill khi đang ghi | `.part` còn lại | Recovery cleanup bằng owner/age sau restart |
| Hết dung lượng đĩa | `OutputStream.write` ném lỗi | Không publish, log & cleanup |
| URL redirect ra private IP | 302 tới internal metadata | Reject/egress deny |
| Resume Range sai offset | 206 Content-Range không khớp | Không append, restart hoặc fail |
| Resume và server trả 200 | Server không cho partial | Tải lại toàn bộ từ đầu |

Nên kiểm tra thêm Windows và Linux vì cách xử lý filename/symlink/collision có khác biệt; thử filesystem thật mà dịch vụ sẽ sử dụng (local, network share, container overlay) trước khi khẳng định atomicity.

## 18. Bài tập thực hành

**Bài 1.** Server trả `Content-Disposition: attachment; filename="../../credentials.txt"`. Vì sao `Path.of(downloadDir).resolve(filename).normalize()` không đủ để coi là an toàn? Làm sao chọn tên lưu?

**Bài 2.** GET trả HTTP 200, `Content-Length: 10000`. Client đọc được 3000 byte rồi `InputStream.read()` ném `IOException`. Trạng thái job/file cuối nên là gì?

**Bài 3.** Server gửi 800 byte, khai `Content-Length: 800`. Trusted manifest nói file phải có SHA-256 khác. Có thể coi download thành công chỉ vì length khớp không?

**Bài 4.** Một download đang ghi `report.pdf.part`. UI phát hiện file đó trên đĩa. UI có nên cung cấp nút mở báo cáo trước khi commit không?

**Bài 5.** Hai worker đồng thời tải vào `report.pdf` và đều thấy `Files.exists(...) == false`. Rủi ro nào còn lại? Có nên coi `ATOMIC_MOVE` mặc định bảo đảm no-overwrite không?

**Bài 6.** Download có `Content-Encoding: gzip`, server khai Content-Length 40 KiB nhưng bytes sau giải nén là 200 MiB. Cần đặt giới hạn ở tầng nào?

**Bài 7.** Download resume đang giữ 5 MB của file phiên bản A. Client gửi `Range: bytes=5000000-` nhưng server trả `200 OK` chứa toàn bộ file phiên bản B. Có được append response B vào file .part A không?

**Bài 8.** URL bắt đầu từ `https://trusted.example.com/file` nhưng redirect tới `http://127.0.0.1/admin`. Downloader có nên follow không?

**Bài 9.** `BodyHandlers.ofInputStream()` trả response chứa stream. Có thể coi `HttpClient.send(...)` thành công là file đã có đủ byte không?

**Bài 10.** Nếu không có Content-Length và nguồn không cung cấp trusted digest, client có phát hiện chắc chắn rằng server gửi một file logic bị cắt nhưng đóng HTTP message hợp lệ không?

### Đáp án gợi ý

1. Normalize không chống hết filename injection, symlink hoặc race. Bỏ tên từ server, dùng tên được ứng dụng quản lý + allowlist + thư mục tin cậy.
2. Đánh dấu FAILED/INCOMPLETE, đóng stream, xóa file `.part` do job tạo, **không** xuất bản final.
3. Không; same-length bytes khác vẫn có thể bị thay. So hash với manifest tin cậy và reject khi mismatch.
4. Không; chỉ publish/trả download link sau khi stream và các kiểm tra thành công.
5. Có TOCTOU; cần no-clobber publication và chiến lược synchronization theo filesystem. `ATOMIC_MOVE` khi target tồn tại có semantics implementation-specific.
6. Limit cả **encoded bytes** tải từ mạng và **decoded bytes**/compression ratio/time nếu giải nén; tránh decompression bomb.
7. Không. `200` không phải continuation của range; bỏ hoặc bảo quản partial cũ theo recovery policy, rồi tải lại từ đầu; validator/ETag phải khớp.
8. Không. Đây là HTTP downgrade/SSRF; phải kiểm tra từng redirect hop, ưu tiên Redirect.NEVER.
9. Không. `send(...)` có thể trả khi mới nhận headers; phải đọc stream hoàn tất và verify trước publish.
10. Không. HTTP framing có thể hợp lệ cho một representation ngắn; cần expected digest/size/manifest từ nguồn đáng tin.

## 19. Tài liệu chính thức

- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): request, redirect policy, version và connection timeout.
- [Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): `GET`, request timeout, URI.
- [Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofInputStream()`, `ofFile()`, download handler.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `createTempFile`, `move`, `exists`, `deleteIfExists` và các semantics filesystem.
- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): `resolve`, `normalize`, `startsWith`, `getParent`.
- [Java SE 17 — SecureDirectoryStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/SecureDirectoryStream.html): xử lý tương đối với directory handle khi provider hỗ trợ, phòng một số race path.
- [Java SE 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html): cập nhật SHA-256 theo khối bytes.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): Content-Length, Range/If-Range, Content-Range, response status.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112.html): message framing và dữ liệu incomplete.
- [RFC 6266 — Content-Disposition in HTTP](https://www.rfc-editor.org/rfc/rfc6266.html): xử lý `filename` và `filename*` như untrusted advice.
