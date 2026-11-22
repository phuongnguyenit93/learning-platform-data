# Kiểm tra đầu vào, đích truy cập, chuyển hướng và giới hạn kích thước dữ liệu

## 1. Bốn ranh giới tin cậy của một ứng dụng Java Networking

Một chương trình Java có thể gọi HTTP API, tải tài liệu, nhận webhook, xử lý dữ liệu upload hoặc chuyển tiếp request tới dịch vụ khác. Đường đi từ input đến kết quả **không an toàn chỉ vì URI parse được hoặc HTTP trả status 200**.

```text
Input do người dùng / upstream cung cấp
     |
     v
[1] Kiểm tra kiểu, cú pháp, độ dài, schema, quyền tài nguyên
     |
     v
[2] Kiểm tra destination: scheme, host, port, DNS/IP, proxy, TLS
     |
     v
    HTTP request với giới hạn timeout/concurrency
     |
     +-- 3xx --> [3] Kiểm tra LẠI đích mới + giới hạn redirect
     |
     v
[4] Kiểm tra response status, content type/coding,
    Content-Length, bytes nhận thực tế, decompressed size
     |
     v
Parse/validate nội dung, lưu .part nếu cần
     |
     v
Commit nghiệp vụ / xuất bản file khi đã hoàn tất
```

Nếu thiếu một lớp:

- **SSRF:** user nhập URL tới metadata service, loopback, dịch vụ nội bộ; app Java làm "người đại diện" truy cập ngoài quyền.
- **Redirect chain:** URL ban đầu là host cho phép, nhưng server trả `Location` sang host/port không được phép; client auto-follow nếu chưa kiểm soát.
- **Unbounded stream:** `Content-Length` thiếu, bị khai sai hoặc nén cực mạnh; gọi `readAllBytes()` gây hết RAM/đĩa/CPU.
- **Content confusion:** phản hồi 404 chứa HTML, dữ liệu gzip được parse như JSON, hoặc tệp không đúng format dù header trông hợp lệ.
- **Truncation:** mất kết nối khi đang nhận body nhưng code vẫn dùng file tạm dở dang làm kết quả.
- **Credential leakage:** tự sao chép `Authorization`/cookie từ request ban đầu sang origin do redirect đưa tới.

Mục tiêu của bài là thiết kế **phòng thủ nhiều lớp nhưng dễ kiểm toán**, biết lớp nào xử lý việc gì, viết code Java 17 dùng `java.net.http.HttpClient` và biết giới hạn của những check ở application layer. Demo chạy thật trên loopback ở mục 15, không gọi Internet hoặc tạo file repository.

## 2. Phân biệt validation, authorization và network policy

| Kiểm tra | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Cú pháp/kiểu | Input có đúng dạng dữ liệu không? | ID là chuỗi chữ/số tối đa 64 ký tự |
| Schema/ngữ nghĩa | Các trường có hợp lý với nhau? | `start <= end`, max size > 0 |
| Authorization | User/tenant có quyền truy cập resource này không? | User A không tải report của User B |
| URL destination policy | URI có thuộc origin/route/port cho phép? | Chỉ `https://reports.example.com:443` |
| Network egress policy | Kết nối **thực** có tới địa chỉ được phép? | Chặn IP nội bộ/metadata/loopback khi URL untrusted |
| Redirect policy | Mọi hop có tiếp tục đáp ứng các quy tắc trên? | Không follow HTTPS → HTTP hoặc sang host khác |
| Response policy | Dữ liệu nhận có đúng status/type/byte limit? | 200, JSON UTF-8, tối đa 2 MiB |
| Completion/integrity | Dữ liệu có đầy đủ và đúng artifact? | Đọc stream xong, SHA-256 khớp manifest tin cậy |

**URI hợp cú pháp không có nghĩa URL được phép.** Tương tự, JSON parse được không có nghĩa người dùng được sửa object chứa trong JSON. Authorization phải gắn với user, tenant, resource và thời điểm request, không chỉ một lần kiểm tra request path.

## 3. Kiểm tra input trước khi dựng HTTP request

### 3.1. Càng ít quyền kiểm soát destination, càng tốt

Nếu ứng dụng chỉ cần tải báo cáo theo ID, hãy nhận **report ID** rồi dựng URL từ base URI được cấu hình tin cậy thay vì cho user nhập URL arbitrary:

```java
// Fragment: baseUri là URI HTTPS của dịch vụ đã được cấu hình.
String reportId = "report-2026-001";
if (!reportId.matches("[A-Za-z0-9_-]{1,64}")) {
    throw new IllegalArgumentException("Invalid report ID");
}
URI download = baseUri.resolve("/api/reports/" + reportId);
```

Mã trên là fragment, cần `import java.net.URI;`. Nếu ID cho phép Unicode, ký tự `/`, dấu cách hoặc `?`, phải mã hóa **đúng thành phần URI** theo hợp đồng thay vì nối chuỗi. Trong trường hợp report ID là một path segment, dùng allowlist đơn giản như trên là cách giảm nhiều bề mặt tấn công.

Trước khi dùng thông tin input:

1. Xác định bắt buộc/tùy chọn; từ chối null, rỗng hoặc duplicate field ngoài hợp đồng.
2. Kiểm tra kiểu số, dấu, range, overflow; không cấp phát theo số nguyên chưa kiểm chứng.
3. Giới hạn số lượng field/header/query parameter, chiều dài từng phần và chiều dài tổng.
4. Đặt limit body **theo bytes**; `String.length()` của Java là số **UTF-16 code units**, không phải bytes UTF-8.
5. Với JSON/XML, giới hạn nesting depth, số phần tử, string length, entity expansion và parser CPU; validate schema sau parse.
6. Dùng allowlist giá trị/enum/route; không chỉ blacklist vài chuỗi như `"../"`.
7. Nếu input có Unicode, quy định rõ normalization và kiểm tra spoofing; không áp NFKC tùy tiện lên token, chữ ký, URL hay tên tài nguyên.
8. Escaping khi xuất ra HTML/SQL/URL là trách nhiệm **output context** khác với validation input; dùng SQL parameters và HTML escaping tương ứng.
9. Liên kết với authorization: resource ID thuộc đúng user/tenant, không phải chỉ có format hợp lệ.
10. Giới hạn tốc độ và số job đồng thời: một request nhỏ nhưng tạo nhiều outbound calls cũng có thể gây DoS.

### 3.2. Lỗi do tưởng một string có cùng kích thước mọi nơi

```java
String body = "Xin chào";
System.out.println(body.length()); // 8 UTF-16 code units
System.out.println(body.getBytes(StandardCharsets.UTF_8).length);
// 9 UTF-8 bytes
```

Đoạn fragment cần `import java.nio.charset.StandardCharsets;`. Với wire protocol, `Content-Length`, network quota, file length và stream budget dùng **bytes thực**. Với một số emoji, một Unicode code point có thể chiếm hai code units và bốn UTF-8 bytes.

## 4. Phân tích URI đúng cách, không tin tiền tố chuỗi

Một lỗi phổ biến:

```java
// PHẢN VÍ DỤ: "https://trusted.example.evil.test/" cũng đạt.
if (rawUrl.startsWith("https://trusted.example")) {
    // Không được coi đây là đích hợp lệ!
}
```

Thay vào đó, parse:

```java
URI uri = URI.create(rawUrl);
String scheme = uri.getScheme();
String host = uri.getHost();
int explicitPort = uri.getPort();
String userInfo = uri.getRawUserInfo();
String path = uri.getRawPath();
String query = uri.getRawQuery();
String fragment = uri.getRawFragment();
```

*Fragment, cần import `java.net.URI` và biến `rawUrl`.*

Các bước đánh giá:

- Scheme phải thuộc tập cho phép, thông thường **`https`** với Internet. Từ chối `file:`, `jar:`, `ftp:`, `data:`, `javascript:` và `http:` nếu không có use case cụ thể.
- Host phải tồn tại (`getHost()!=null`), thuộc **allowlist exact host** hoặc quy tắc subdomain thực sự được phê duyệt; không kiểm tra `rawUrl.contains("trusted")`.
- Port phải thuộc danh sách được phép. `getPort()==-1` nghĩa **không ghi port**, hãy suy ra default theo scheme (HTTPS=443, HTTP=80), không kết nối tới port -1.
- Từ chối userinfo khi không cần: `https://trusted.example@evil.example/path` có hostname **`evil.example`**, còn `trusted.example` là userinfo.
- Fragment `#...` không truyền tới HTTP server nhưng có thể gây nhầm lẫn trong validation/log; reject nếu hợp đồng không cho phép.
- Query phải có giới hạn số trường/kích thước, không chứa URL lồng nhau không được kiểm tra; nhiều API tải file có thể không cần query từ người dùng.
- Path phải đúng route; phân biệt encoded slash/dot, path segments, trailing slash và authorization.

**Không bao giờ dùng `URI.normalize()` như phương án chống SSRF.** Nó chỉ chuẩn hóa một số thành phần path ở tầng cú pháp URI; không giải quyết DNS, proxy, network permissions, symlink, URL decoding khác nhau giữa các hệ thống, hay quyền truy cập tài nguyên.

## 5. Hostname, IPv4/IPv6, IDN và cách đánh lừa policy

Các URI dưới đây yêu cầu phân tích khác nhau:

```text
https://EXAMPLE.COM/
https://example.com.:443/
https://example.com.evil.test/
https://user@example.com/
https://example.com/a/../hidden
https://example.com/%2e%2e/hidden
http://127.0.0.1/
http://[::1]/
```

- Hostname DNS không phân biệt hoa/thường, nhưng **không được** chỉ làm `endsWith("example.com")` (có thể khớp `evil-example.com`). Với subdomain policy, kiểm tra ranh giới dấu chấm.
- Trailing dot có thể biểu diễn DNS absolute name. Chỉ chấp nhận cách chuẩn hóa này khi đã thiết kế cụ thể.
- Với internationalized domain names (IDN), xác minh dạng canonical ASCII/IDNA bằng cơ chế phù hợp. Cẩn thận ký tự trông giống nhau (homograph).
- IPv4 loopback/private/link-local, IPv6 loopback/ULA/link-local, mapped IPv4/IPv6, aliases và dạng IP numeric lạ phải được xử lý nhất quán. **Không chặn SSRF chỉ bằng chuỗi `127.0.0.1`**.
- `%2e`, `%2f`, dấu `..` hoặc double encoding có thể gây nhầm lẫn giữa layer Java, proxy và backend. Một bên decode còn bên kia không decode có thể dẫn tới bypass. Hạn chế input path và thiết kế canonicalization nhất quán.
- Redirect có dạng `Location: //other.example/path`: dù **không ghi scheme**, authority đã đổi. Một redirect `Location: ../admin` có thể thay route.
- Không dùng hostname allowlist như một cách thay thế kiểm tra IP kết nối thực tế.

**Lựa chọn bảo mật tốt nhất:** không để user quyết định hostname; nếu thực sự phải tải URL do user cung cấp, kiểm soát thêm network egress và mọi redirect, không chỉ thêm regex.

## 6. SSRF: host allowlist vẫn chưa đủ nếu IP thực đổi

Rủi ro server-side request forgery:

```text
Input URL được attacker kiểm soát
  |
  v
Ứng dụng Java tưởng sẽ tới public website
  |
  +--> DNS trả IP nội mạng/loopback/link-local
  +--> Server public 302 tới metadata endpoint
  +--> DNS rebinding sau lần validation
  +--> Proxy/tunnel kết nối tới dịch vụ cấm
  |
  v
Private/internal service nhận request của chính server Java
```

Các nhóm địa chỉ nhạy cảm cần xem xét (chỉ là ví dụ, không phải danh sách block hoàn chỉnh):

- Loopback: `127.0.0.0/8`, `::1`.
- RFC1918 IPv4 private: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`.
- Link-local: `169.254.0.0/16` và IPv6 link-local; cloud metadata thường nằm trong phạm vi nhạy cảm.
- IPv6 Unique Local Addresses, unspecified, multicast, các địa chỉ reserved hoặc reachable internal.
- Public IP thuộc dịch vụ nội bộ/đối tác không được phép, kể cả khi IP không nằm trong RFC1918.

**DNS rebinding và TOCTOU:**

```text
1. App gọi InetAddress.getAllByName("allowed.example")
   -> nhận 203.0.113.10, vượt qua preflight IP.

2. Sau đó HttpClient.send(request) tự kết nối.
   -> resolver có thể trả IP khác, ví dụ 127.0.0.1.

3. Request thực có thể đi tới nơi bị policy cấm.
```

Do đó **gọi DNS một lần trước khi request không bảo đảm HttpClient sẽ connect đến đúng IP đã kiểm tra**. Java `HttpClient` chuẩn không cho bạn mặc nhiên "pin" DNS lookup vừa thực hiện chỉ bằng `InetAddress.getAllByName`. Nếu hạ tầng cần xử lý URL untrusted, dùng **egress firewall/secure outbound proxy** kiểm soát điểm đích thực của kết nối, cùng allowlist host/port và ràng buộc DNS phù hợp. Với TLS, vẫn phải xác minh certificate theo hostname logic; không sửa hostname thành IP rồi tắt verification.

### Proxy làm chính sách phức tạp hơn

Nếu ứng dụng chỉ kết nối tới IP của proxy, điều đó **không** chứng minh proxy không truy cập internal targets:

```text
Java application -> approved outbound proxy -> internal metadata service
```

Phải có chính sách destination ở proxy/egress layer, kiểm soát CONNECT, DNS resolver và ports. Với TLS interception, người vận hành proxy còn cần quản lý CA và logging an toàn. Không tự copy HTTP credentials/session cookie qua domain khác khi follow redirect.

## 7. HTTPS/TLS là kiểm tra danh tính, không chỉ mã hóa bytes

Đối với outbound API production:

- Mặc định dùng **HTTPS**, kiểm tra certificate chain và hostname/SAN.
- Từ chối HTTPS → HTTP downgrade trong redirect nếu không có lý do được phê duyệt.
- Không dùng trust-all `TrustManager`, bỏ hostname verification hay tắt TLS để "chữa lỗi certificate".
- TLS connection/certificate hợp lệ **không đồng nghĩa nội dung server tin cậy**, cần status/type/size/schema/integrity.
- HTTP/2 và HTTP/1.1 là HTTP protocol versions; fallback HTTP/1.1 **trong HTTPS** không đồng nghĩa bỏ TLS.
- Có thể cần client auth/mTLS hoặc pinning theo chính sách riêng; không triển khai tùy tiện.
- Không lưu token trong URL query nếu có lựa chọn tốt hơn; query/URL có thể lọt vào proxy/access logs.
- Với ứng dụng nhiều tenant, credential/session phải được scope theo đúng origin/user, không dùng client-global headers không kiểm soát.

Nếu một URL đầu bắt đầu bằng HTTPS nhưng qua chuỗi redirect tới HTTP/host khác, request cuối có thể hoàn toàn khác kỳ vọng. Chính sách redirect cần xác minh **từng hop**.

## 8. Chuyển hướng HTTP: xử lý như một request mới

Ví dụ chuyển hướng tương đối bình thường:

```http
HTTP/1.1 302 Found
Location: /download/verified
Content-Length: 0

```

Ví dụ đáng nghi:

```http
HTTP/1.1 302 Found
Location: http://127.0.0.1:9999/admin
Content-Length: 0

```

Chỉ validate URL ban đầu là **không đủ** nếu Java client tự follow redirects.

### 8.1. Ba lựa chọn `HttpClient.Redirect` của Java 17

| Policy | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| `NEVER` | Không auto-follow HTTP redirects | Tốt khi cần kiểm tra mọi Location |
| `NORMAL` | Follow theo implementation nhưng không redirect từ HTTPS sang HTTP | Có thể dùng cho đích đã tin cậy, không thay origin allowlist |
| `ALWAYS` | Follow redirects kể cả scheme downgrade theo policy | Không là mặc định an toàn cho URL không tin cậy |

Đối với URL do user kiểm soát, ưu tiên:

```java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .connectTimeout(Duration.ofSeconds(3))
        .build();
```

*Fragment: cần import `HttpClient` và `Duration`.* Nếu chọn NORMAL, **host mới không tự được kiểm tra bằng allowlist ứng dụng**; policy này chỉ bao gồm những giới hạn do Java HTTP client quy định.

### 8.2. Thuật toán manual redirect cho GET

```text
validateTarget(current)
    |
    v
send GET(current), redirects NEVER
    |
    +-- HTTP 200 --> validate response + bounded body
    |
    +-- HTTP 301/302/303/307/308
           |
           +-- maxRedirects còn budget?
           +-- Location đúng một giá trị parse được?
           +-- next = current.resolve(Location)
           +-- validateTarget(next) trước mọi network request?
           +-- seen URI chưa có? total deadline còn?
           +-- chuyển current=next, tiếp tục
    |
    +-- status khác --> controlled failure
```

Các quy tắc:

1. Giới hạn hop, ví dụ `maxRedirects=3` trong demo. Dù `Set<URI>` phát hiện A→B→A, attacker có thể đổi query liên tục để không lặp; hop budget vẫn bắt buộc.
2. Giải `Location` tương đối dựa trên **URI hiện tại**, không phải URI đầu tiên.
3. **Revalidate mọi đích sau resolve:** scheme, host, port, path, userinfo, IP/egress, TLS, authorization.
4. Không đi theo một Location thiếu, malformed hoặc ambiguous theo cách ngẫu nhiên.
5. Đóng response body không dùng trước hop tiếp theo để tránh giữ resource/connection.
6. Có **total deadline** cho toàn redirect chain, không chỉ timeout cho từng request.
7. Kiểm tra credential scope; không copy raw `Authorization`/`Cookie` sang host khác.

### 8.3. POST/PUT/PATCH không giống GET

Demo chỉ xử lý GET. Với request có side effect:

- `301/302/303` có ngữ nghĩa chuyển hướng và hành vi method/body theo tiêu chuẩn/implementation; một số redirect chuyển POST sang GET.
- `307/308` bảo tồn method và body, nhưng **body không phải lúc nào cũng có thể replay**; gửi lại POST có thể trùng side effect.
- Nếu một lệnh tạo đơn/chuyển tiền đã xử lý ở server nhưng response bị mất, tự gửi lại như lệnh mới rất nguy hiểm.
- Dùng idempotency key ổn định, backend dedup/transaction và policy chuyển hướng rõ ràng.

**Đừng biến HttpClient auto-redirect thành một cơ chế retry nghiệp vụ.** Đây là hai loại điều phối khác nhau.

## 9. Validation response: status, Content-Type, Content-Encoding, Content-Length

Một HTTP request kết nối thành công có thể trả dữ liệu không phù hợp. Trước khi parse hoặc ghi file, kiểm tra:

| Metadata | Cần kiểm tra gì? | Lỗi nếu bỏ qua |
| --- | --- | --- |
| HTTP status | Chỉ nhận status thành công theo contract, ví dụ `200` | Lưu HTML 404 làm JSON |
| `Content-Type` | Media type được chấp nhận, ví dụ `application/json` | Parser nhận binary/text sai |
| `Content-Encoding` | Giải mã hoặc reject content coding chưa hỗ trợ | Parse gzip bytes như UTF-8 |
| `Content-Length` | Nếu tồn tại: hợp lệ, không âm, không vượt limit | Preallocate quá nhiều, parse lỗi |
| Thực tế byte stream | Không vượt max; HTTP stream hoàn tất không lỗi | OOM, download dở dang |
| Charset | Giải text theo charset/media type quy định | Mojibake/chuỗi sai |
| Schema/file signature | Nội dung thực khớp hợp đồng | Lệnh sai, tệp độc hại |
| Integrity | Hash/signature/manifest tin cậy nếu cần | File cùng kích thước nhưng khác nội dung |

**Không dùng `Content-Type` như bằng chứng nội dung an toàn.** Header là metadata do server cung cấp; một tệp khai `image/png` vẫn có thể là bytes không đúng format. Cần decoder/validator có giới hạn và chính sách bảo mật riêng cho file tải.

**Không ép binary qua `new String(bytes, UTF_8)`**. Nếu tải ảnh/zip, giữ bytes và xử lý bằng parser phù hợp. Với JSON trao đổi giữa các hệ thống, UTF-8 là encoding được chuẩn hóa theo RFC 8259.

## 10. Giới hạn Content-Length và bytes đọc thực tế

`Content-Length` được tính bằng **octet (byte)** theo HTTP semantics, không phải số UTF-16 code units:

```java
String s = "Xin chào";
int units = s.length(); // 8
int actualBytes = s.getBytes(StandardCharsets.UTF_8).length; // 9
```

Với response HTTP, cần hai lớp:

1. **Precheck declared size:** nếu Content-Length (khi hợp lệ và áp dụng) là 1 GiB nhưng ứng dụng chỉ cho phép 10 MiB, từ chối ngay để giảm bandwidth.
2. **Hard cap trong lúc đọc:** nếu Content-Length **thiếu, khai sai hoặc response dùng chunked**, vẫn cộng số bytes thực đọc và từ chối trước khi vượt max.

Không tính `String.length()`, không cấp phát `new byte[(int)contentLength]` từ header chưa tin cậy. Dùng `InputStream` và buffer, kiểm tra:

```java
if (n > maxBytes - consumed) {
    throw new IOException("HTTP body exceeds byte budget");
}
consumed += n;
```

*Fragment: `n` là số bytes từ `read`, `maxBytes` và `consumed` là long không âm.* Kiểu check dạng hiệu tránh tràn số khi `consumed + n`.

### 10.1. Helper bounded read cho dữ liệu nhỏ

```java
static byte[] readAtMost(InputStream in, long maxBytes)
        throws IOException {
    if (maxBytes < 0) throw new IllegalArgumentException();
    ByteArrayOutputStream result = new ByteArrayOutputStream();
    byte[] buffer = new byte[8192];
    long total = 0;
    int n;
    while ((n = in.read(buffer)) != -1) {
        if (n > maxBytes - total)
            throw new IOException("Body too large");
        result.write(buffer, 0, n);
        total += n;
    }
    return result.toByteArray();
}
```

*Fragment: cần import `InputStream`, `ByteArrayOutputStream` và `IOException`.* Hàm giữ toàn bộ kết quả trong RAM nên chỉ dùng với một maxBytes **nhỏ và được kiểm soát**. Với file lớn, stream vào file tạm, checksum, verify và commit sau khi hoàn tất.

### 10.2. Content-Length không phải dữ liệu duy nhất xác định ranh giới

- HTTP/1.1 với `Transfer-Encoding: chunked` có framing riêng; ứng dụng nên để HTTP stack xử lý.
- HTTP/2 và HTTP/3 có data stream/frame/end-of-stream riêng, không dùng chunked syntax HTTP/1.1.
- Response của `HEAD` **không có body** dù có thể gửi Content-Length tương ứng với GET.
- `304 Not Modified` **không có response body**; Content-Length, nếu có, mang ngữ nghĩa riêng.
- Response `204` hoặc `1xx` không có body theo quy tắc protocol.
- Duplicate hoặc mâu thuẫn `Content-Length`/`Transfer-Encoding` là vấn đề cần HTTP stack/proxy xử lý đúng chuẩn để tránh request smuggling.

**Header get từ `HttpHeaders.allValues(...)` đã được Java HTTP stack parse**; không xem application code demo như một raw HTTP parser chống mọi loại framing ambiguity. Ở tầng ứng dụng, nếu metadata vượt contract, fail closed; ở tầng giao thức, dùng HTTP implementation cập nhật.

## 11. Compressed content: đặt cả encoded và decoded budgets

Server có thể gửi:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: gzip
Content-Length: 2048

<gzip bytes>
```

2 KiB dữ liệu nén có thể giải ra hàng trăm MiB tùy nội dung. Một limit chỉ đo **compressed wire bytes** không đủ trước decompression bomb:

- **Encoded-byte quota:** số bytes content thực nhận/đọc dưới dạng encoded.
- **Decoded-byte quota:** số bytes sau giải `gzip/br/deflate` theo content coding được hỗ trợ.
- **CPU/time/expansion ratio quota:** tránh payload rất nhỏ nhưng giải nén quá tốn tài nguyên.
- **Parser quota:** JSON depth/array/string count, ZIP entries/unpacked size, XML entity expansion.

Mảnh code minh họa giới hạn hai tầng:

```java
// Fragment, khi Content-Encoding đúng "gzip" và app muốn decode.
byte[] compressed = readAtMost(encodedBody, MAX_ENCODED);
try (GZIPInputStream gzip = new GZIPInputStream(
        new ByteArrayInputStream(compressed))) {
    byte[] decoded = readAtMost(gzip, MAX_DECODED);
    // Chọn parser/charset theo Content-Type đã xác thực.
}
```

*Đây là fragment dùng helper ở mục 10 và import `GZIPInputStream`, `ByteArrayInputStream`.* Với tệp lớn, dùng streaming decoder có quota thay vì tạo hai mảng trong RAM.

Trong ví dụ runnable ở mục 15, client **từ chối mọi `Content-Encoding` ngoài `identity`**, để không vô tình parse bytes đã nén như raw UTF-8. Đây là chính sách phù hợp cho demo, không phải khẳng định HTTP client không thể hỗ trợ gzip.

## 12. Body bị cắt, lỗi transport và artifact chưa hoàn tất

Một body có thể hỏng theo nhiều cách:

```text
HttpResponse 200
    |
    v
Body InputStream
    |
    +--> read IOException / framing fail --> ERROR
    +--> actual bytes > max             --> ERROR
    +--> declared count mismatch        --> ERROR
    +--> expected digest mismatch       --> ERROR
    +--> schema/format invalid          --> ERROR
    |
    v
Complete + validated
    |
    v
Commit/publish
```

Có hai trường hợp khác nhau:

- **Protocol-level incomplete:** server khai N bytes nhưng chỉ gửi ít hơn, mất terminating chunk hoặc HTTP/2 stream đóng bất thường; HttpClient có thể báo lỗi khi đọc.
- **Application-level incomplete:** server gửi HTTP message hợp lệ với Content-Length đúng nhưng artifact logic vốn phải dài hơn hoặc có hash khác. Muốn xác định cần **expected size/hash/signature từ nguồn tin cậy**, không chỉ status/length.

Với download file: ghi tới **file tạm .part** trong thư mục do ứng dụng quản lý; tính hash/byte count khi stream; nếu lỗi thì chỉ xóa file tạm do chính lượt tải tạo; chỉ publish tên cuối sau khi toàn bộ validation đạt. Không dựa vào `Files.exists(destination)` để khẳng định file hoàn chỉnh. Đường dẫn cuối phải tránh path traversal, symlink race, ghi đè và thiếu quyền.

Khi có remote timeout, disk full hoặc user cancel, đóng body stream, đánh dấu job FAILED/CANCELLED và cleanup. `finally` chạy trong xử lý exception bình thường, **không bảo đảm chạy khi process bị kill hoặc mất điện**; cần cleanup file `.part` cũ lúc khởi động theo owner/TTL.

## 13. Deadline và backpressure: bytes nhỏ không có nghĩa request rẻ

Server có thể gửi 1 byte mỗi phút; byte quota không bao giờ bị vượt nhưng request vẫn bị giữ vô hạn. Ngoài giới hạn bytes cần:

- **Connect timeout:** `HttpClient.Builder.connectTimeout(...)` cho pha kết nối.
- **Request timeout:** `HttpRequest.Builder.timeout(...)` theo contract của Java client.
- **Idle-read timeout:** tối đa thời gian chờ byte tiếp theo, cần cơ chế giám sát/cancel tương ứng.
- **Total job deadline:** tổng thời gian của DNS, TLS, redirect hops, đọc stream, decode/parse, lưu file và commit.
- **Redirect limit:** số hops tối đa, độc lập với deadline.
- **Retry budget:** số retries/tổng thời gian cho lỗi tạm, với exponential backoff + jitter.
- **Concurrency/queue limits:** số request in-flight, body bytes đang buffered, worker threads, pending task count.
- **Rate limits:** theo account/IP/API token/tenant để chống flood.

**Chú ý `BodyHandlers.ofInputStream()`:** `client.send(...)` có thể trả khi response headers/stream đã sẵn sàng **trước khi toàn bộ body được đọc**. Không coi `HttpRequest.timeout(...)` tự bảo đảm một deadline tuyệt đối cho mọi thao tác `InputStream.read()` tiếp theo. Trong production cần cancellation/deadline đủ rõ cho toàn job và đóng stream khi hủy.

Không retry POST non-idempotent mù; nếu side effect có thể đã xảy ra, dùng idempotency key và server-side dedup/result lookup.

## 14. Request validation ở phía server và upload

Đối với Java HTTP server, cần áp tương tự cho **request body inbound**:

| Thành phần | Biện pháp |
| --- | --- |
| HTTP request target/path | Route allowlist, URL length, decode nhất quán, authorization |
| Query/headers | Giới hạn số lượng/bytes, reject sai schema hoặc duplicate ngoài hợp đồng |
| `Content-Length` | Có thể reject sớm nếu lớn hơn max, không tin là đủ |
| Request stream | Đếm bytes thực trong mỗi `read`, giới hạn size/time |
| JSON/XML | Giới hạn nesting/độ dài string/array/entity expansion và schema |
| Multipart | Giới hạn số part, size từng file/tổng, filename, content coding |
| Archive/ZIP | Giới hạn bytes sau giải nén, số entry, path traversal khi extract |
| Authorization | Resource thuộc principal/tenant, kiểm tra trước mutation |
| Request concurrency | Bounded threads/queues/rate limits |
| Error handling | Status phù hợp, không lộ stack trace/secret |

Một request sai cú pháp có thể trả `400`; body lớn `413 Content Too Large`; media type không được hỗ trợ `415`; thiếu quyền `401/403` theo ngữ nghĩa; quá tốc độ `429`. Không tự trả 200 với một object sai schema rồi yêu cầu client "tự đoán lỗi".

**Server không được tin user-provided `Content-Length` để cấp `byte[]`** vì có thể sai, âm, cực lớn hoặc overflow. Để HTTP stack xử lý message framing; ứng dụng áp hard cap trong lúc đọc.

## 15. Ví dụ Java 17 hoàn chỉnh: đích, redirect và byte quota

Ví dụ này **chạy cục bộ** với JDK 17, không cần Internet. Server dùng `com.sun.net.httpserver.HttpServer` trên `127.0.0.1` và port do OS chọn. Client tạo với `Redirect.NEVER`, kiểm tra target trước mỗi request và đọc body bằng `ofInputStream()` với limit.

Các thử nghiệm:

1. `/start` → `302 Location: /data` hợp lệ → GET nhận `Xin chào` (9 byte UTF-8).
2. URI có userinfo và path ngoài allowlist bị chặn.
3. Redirect sang `example.invalid`, port khác, vòng lặp bị chặn.
4. `Content-Length` quá lớn và chunked stream vượt quota bị chặn.
5. Content-Type khác `text/plain`, content coding không hỗ trợ, HTTP 404 và body bị cắt đều bị chặn.

**Tệp `GuardedHttpFetchDemo.java`:**

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class GuardedHttpFetchDemo {
    static final Set<String> PATHS = Set.of(
            "/start", "/data", "/oversize", "/stream", "/offhost",
            "/offport", "/loop-a", "/loop-b", "/missing", "/badtype",
            "/encoded", "/truncated");
    static final int MAX_REDIRECTS = 3;

    record Download(URI finalUri, byte[] bytes, int redirects) {}

    static void validateUri(URI uri, int port) {
        if (!"http".equalsIgnoreCase(uri.getScheme())
                || !"127.0.0.1".equals(uri.getHost())
                || uri.getPort() != port
                || uri.getRawUserInfo() != null
                || uri.getRawFragment() != null
                || uri.getRawQuery() != null
                || !PATHS.contains(uri.getRawPath())) {
            throw new IllegalArgumentException("URI is outside demo policy");
        }
    }

    static Download fetch(HttpClient client, URI start, int port, long limit)
            throws Exception {
        if (limit < 0) throw new IllegalArgumentException("Invalid limit");
        URI current = start;
        Set<URI> seen = new HashSet<>();
        int redirects = 0;
        while (true) {
            validateUri(current, port); // Before every network request.
            if (!seen.add(current)) throw new IOException("Redirect loop");
            HttpRequest req = HttpRequest.newBuilder(current)
                    .timeout(Duration.ofSeconds(5)).GET().build();
            HttpResponse<InputStream> response = client.send(
                    req, HttpResponse.BodyHandlers.ofInputStream());
            try (InputStream body = response.body()) {
                int status = response.statusCode();
                if (status == 301 || status == 302 || status == 303
                        || status == 307 || status == 308) {
                    if (redirects >= MAX_REDIRECTS)
                        throw new IOException("Redirect budget exhausted");
                    List<String> locations = response.headers()
                            .allValues("Location");
                    if (locations.size() != 1)
                        throw new IOException("Missing/ambiguous Location");
                    URI location;
                    try {
                        location = URI.create(locations.get(0));
                    } catch (IllegalArgumentException bad) {
                        throw new IOException("Malformed Location", bad);
                    }
                    URI next = current.resolve(location);
                    validateUri(next, port); // Block off-policy redirects.
                    current = next;
                    redirects++;
                    continue;
                }
                if (status != 200) {
                    throw new IOException("Unexpected status " + status);
                }
                List<String> types = response.headers()
                        .allValues("Content-Type");
                if (types.size() != 1 || !types.get(0)
                        .split(";", 2)[0].trim()
                        .equalsIgnoreCase("text/plain")) {
                    throw new IOException("Unexpected Content-Type");
                }
                List<String> coding = response.headers()
                        .allValues("Content-Encoding");
                if (coding.size() > 1 || coding.size() == 1
                        && !coding.get(0).equalsIgnoreCase("identity")) {
                    throw new IOException("Unexpected Content-Encoding");
                }
                List<String> lengths = response.headers()
                        .allValues("Content-Length");
                if (lengths.size() > 1) {
                    throw new IOException("Ambiguous Content-Length");
                }
                long declared = -1;
                if (lengths.size() == 1) {
                    try {
                        String literal = lengths.get(0);
                        if (!literal.matches("[0-9]+"))
                            throw new NumberFormatException();
                        declared = Long.parseLong(literal);
                    } catch (NumberFormatException bad) {
                        throw new IOException("Invalid Content-Length", bad);
                    }
                    if (declared > limit)
                        throw new IOException("Declared body exceeds limit");
                }
                ByteArrayOutputStream received = new ByteArrayOutputStream();
                byte[] chunk = new byte[256];
                long count = 0;
                int n;
                while ((n = body.read(chunk)) != -1) {
                    if (n > limit - count)
                        throw new IOException("Stream exceeds limit");
                    received.write(chunk, 0, n);
                    count += n;
                }
                if (declared >= 0 && count != declared)
                    throw new IOException("Truncated or excessive response");
                return new Download(current, received.toByteArray(),
                        redirects);
            }
        }
    }

    static void send(HttpExchange exchange, int status, String contentType,
            byte[] bytes) throws IOException {
        try (exchange) {
            if (contentType != null)
                exchange.getResponseHeaders().set(
                        "Content-Type", contentType);
            exchange.sendResponseHeaders(status, bytes.length);
            exchange.getResponseBody().write(bytes);
        }
    }

    static void redirect(HttpExchange exchange, String location)
            throws IOException {
        try (exchange) {
            exchange.getResponseHeaders().set("Location", location);
            exchange.sendResponseHeaders(302, -1);
        }
    }

    static void expectFailure(String label, RunnableWithException job)
            throws Exception {
        try {
            job.run();
            throw new AssertionError(label + " should fail");
        } catch (IOException | IllegalArgumentException expected) {
            System.out.println(label + ": blocked");
        }
    }

    @FunctionalInterface
    interface RunnableWithException {
        void run() throws Exception;
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        byte[] hello = "Xin chào".getBytes(StandardCharsets.UTF_8);
        server.createContext("/start", ex -> redirect(ex, "/data"));
        server.createContext("/data", ex ->
                send(ex, 200, "text/plain; charset=UTF-8", hello));
        server.createContext("/oversize", ex ->
                send(ex, 200, "text/plain", "1234567890123456"
                        .getBytes(StandardCharsets.US_ASCII)));
        server.createContext("/stream", ex -> {
            try (ex) {
                ex.getResponseHeaders().set("Content-Type", "text/plain");
                ex.sendResponseHeaders(200, 0); // Chunked HTTP/1.1.
                ex.getResponseBody().write(
                        "0123456789".getBytes(StandardCharsets.US_ASCII));
            } catch (IOException closedByClient) {
                // Client can stop after limit exceeded.
            }
        });
        server.createContext("/offhost", ex ->
                redirect(ex, "http://example.invalid/secret"));
        server.createContext("/offport", ex ->
                redirect(ex, "http://127.0.0.1:9/data"));
        server.createContext("/loop-a", ex ->
                redirect(ex, "/loop-b"));
        server.createContext("/loop-b", ex ->
                redirect(ex, "/loop-a"));
        server.createContext("/missing", ex ->
                send(ex, 404, "text/plain", "missing"
                        .getBytes(StandardCharsets.US_ASCII)));
        server.createContext("/badtype", ex ->
                send(ex, 200, "application/octet-stream", hello));
        server.createContext("/encoded", ex -> {
            ex.getResponseHeaders().set("Content-Encoding", "gzip");
            send(ex, 200, "text/plain", hello);
        });
        server.createContext("/truncated", ex -> {
            try (ex) {
                ex.getResponseHeaders().set("Content-Type", "text/plain");
                ex.sendResponseHeaders(200, hello.length + 6);
                ex.getResponseBody().write(hello, 0, 3);
            } catch (IOException expectedAbort) {
                // Deliberately incomplete response body.
            }
        });
        server.start();
        try {
            int port = server.getAddress().getPort();
            URI origin = URI.create("http://127.0.0.1:" + port);
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            Download ok = fetch(client, origin.resolve("/start"),
                    port, 32);
            System.out.println("success: redirects=" + ok.redirects()
                    + " bytes=" + ok.bytes().length
                    + " text=" + new String(ok.bytes(),
                            StandardCharsets.UTF_8));
            expectFailure("userinfo", () -> fetch(client, URI.create(
                    "http://alice@127.0.0.1:" + port + "/data"), port, 32));
            expectFailure("unlisted-path", () -> fetch(client,
                    origin.resolve("/private"), port, 32));
            expectFailure("foreign-host-redirect", () -> fetch(client,
                    origin.resolve("/offhost"), port, 32));
            expectFailure("wrong-port-redirect", () -> fetch(client,
                    origin.resolve("/offport"), port, 32));
            expectFailure("redirect-loop", () -> fetch(client,
                    origin.resolve("/loop-a"), port, 32));
            expectFailure("oversize-header", () -> fetch(client,
                    origin.resolve("/oversize"), port, 4));
            expectFailure("stream-limit", () -> fetch(client,
                    origin.resolve("/stream"), port, 4));
            expectFailure("wrong-media-type", () -> fetch(client,
                    origin.resolve("/badtype"), port, 32));
            expectFailure("unexpected-coding", () -> fetch(client,
                    origin.resolve("/encoded"), port, 32));
            expectFailure("HTTP-404", () -> fetch(client,
                    origin.resolve("/missing"), port, 32));
            expectFailure("truncated-body", () -> fetch(client,
                    origin.resolve("/truncated"), port, 32));
        } finally {
            server.stop(0);
        }
    }
}
```

**Biên dịch và chạy JDK 17** (server test trong module `jdk.httpserver`):

```bash
javac --release 17 --add-modules jdk.httpserver GuardedHttpFetchDemo.java
java --add-modules jdk.httpserver GuardedHttpFetchDemo
```

**Stdout đã kiểm thử thực tế:**

```text
success: redirects=1 bytes=9 text=Xin chào
userinfo: blocked
unlisted-path: blocked
foreign-host-redirect: blocked
wrong-port-redirect: blocked
redirect-loop: blocked
oversize-header: blocked
stream-limit: blocked
wrong-media-type: blocked
unexpected-coding: blocked
HTTP-404: blocked
truncated-body: blocked
```

### 15.1. Diễn giải phép thử

**Success:** server trả relative redirect `/data` trong cùng origin/path allowlist; client follow đúng một hop, nhận 9 byte UTF-8 của `Xin chào`, dưới max 32 bytes.

**Userinfo/unlisted-path:** reject đầu vào trước network request; việc URI hợp cú pháp không đủ.

**Foreign-host/wrong-port:** reject `Location` trỏ sang hostname khác hoặc port 9 trước khi connect; đây là ranh giới quan trọng của manual redirect.

**Loop:** server A→B→A, seen set nhận ra URI đã gặp; max hop vẫn cần cho redirect không lặp y hệt URI.

**Oversize-header:** server công bố 16 bytes, max 4 → reject ngay không tải body làm artifact.

**Stream-limit:** HTTP/1.1 chunked response không có length cố định → byte loop dừng ở max 4, không phụ thuộc header.

**Wrong media type/unsupported content coding:** reject trước parse, không dùng binary/gzip như text được phép.

**HTTP 404:** network request thành công nhưng business contract chỉ chấp nhận status 200.

**Truncated-body:** server khai body dài hơn bytes thực gửi; HTTP client báo lỗi hoặc length check fail, không trả dữ liệu dở dang.

### 15.2. Đây chỉ là chính sách fixture, không phải SSRF library production

Ví dụ intentionally dùng HTTP loopback `127.0.0.1` chỉ để chạy cùng JVM. Nó **không** giải quyết:

- HTTPS certificate/hostname validation hoặc mutual TLS.
- Domain DNS rebinding, nhiều A/AAAA, custom resolver, outbound proxy, firewall egress.
- URI query động, percent decoding phức tạp, auth header scoping cross-origin.
- JSON schema validation hoặc gzip decompression có limit.
- Upload/download file lớn và durable hash/commit.
- Deadline toàn stream khi peer đọc/ghi rất chậm, tải concurrent nhiều GB.
- HTTP/1.1 framing ambiguity/hardening của reverse proxy hoặc raw parser.

Dùng Java `HttpClient` chuẩn, có egress/network policy và application routing guard hợp nhất khi thiết kế production. Không thay điều kiện `http://127.0.0.1` trong demo bằng "mỗi URL nào cũng được" rồi gọi đó là SSRF protection.

## 16. Triển khai file download lớn một cách bền vững

Với artifact có thể đạt hàng trăm MiB, không dùng `ByteArrayOutputStream`. Một quy trình:

```text
Validated destination (HTTPS, allowlist, egress)
    |
    v
GET with controlled redirects, status & metadata checks
    |
    v
Create unique .part file inside trusted download directory
    |
    v
Bounded InputStream -> OutputStream in chunks
    |
    +--> count bytes, SHA-256, deadline, cancel checks
    +--> fail if max exceeded, EOF error or disk write fails
    |
    v
Validate complete HTTP body and trusted expected digest/schema
    |
    v
No-clobber publish final name (filesystem semantics considered)
    |
    v
Success reported only after publish
```

Những điều không được bỏ qua:

- Tên final file chọn từ **ID/logic của ứng dụng**; không lấy trực tiếp từ `Content-Disposition: filename=../../...`.
- Không cho path escape qua `..`, absolute path, backslash/Unicode và symlink; `Path.normalize` không xử lý mọi symlink/race.
- File tạm do mỗi job tạo và sở hữu; chỉ xóa partial của job khi fail.
- HTTP status 200 và đúng Content-Length **chưa chứng minh** artifact đúng; dùng trusted checksum/manifest/signature khi cần.
- `Files.move(partial, final)` không mặc định bảo đảm atomic/durable cho mọi filesystem/provider; không dùng `REPLACE_EXISTING` nếu muốn giữ bản cũ.
- Nếu muốn resume Range, xác minh `206 Content-Range`, strong ETag/If-Range, offset và checksum; `200` thay vì `206` nghĩa phải tải lại từ đầu, không append mù.

## 17. Quy trình kiểm soát tải lên và request inbound

Nếu bài toán là **HTTP server nhận input**, hãy áp hard cap cả ở gateway lẫn code xử lý request:

```text
HTTP server request
   |
   +-- reject invalid path/method/query/header
   +-- authenticate & authorize principal
   +-- Content-Length precheck (nếu hợp lệ)
   +-- streaming byte limit dù không có header
   +-- decoded-size limit cho gzip/multipart/archive
   +-- schema/format validation
   +-- store in temp/safe path or transaction
   +-- commit and return status
```

Status nên có ngữ nghĩa: 400 sai cú pháp, 401/403 xác thực/quyền, 413 quá body size, 415 media type không được hỗ trợ, 422 payload không hợp nghĩa theo contract, 429 rate-limit. Không đưa stack trace hoặc internal paths vào error response.

Ở server HTTP/1.1, HTTP stack phải xử lý đúng `Transfer-Encoding` và `Content-Length`, không cho raw parser sai ranh giới gây request smuggling. Application vẫn cần quota, vì một request hoàn toàn hợp lệ về HTTP có thể chứa dữ liệu rất lớn hoặc JSON cực sâu.

## 18. Vận hành: đo cả lượt bị từ chối và ngân sách đã tiêu

Các metric/log đáng quan tâm:

| Metric | Ý nghĩa |
| --- | --- |
| `outbound_rejected_target_total` | Input URL ngoài scheme/host/port/IP allowlist |
| `redirect_hops_per_request` | Số lần server đổi đích |
| `redirect_rejected_total` | Redirect tới host/port/scheme/route cấm |
| `ssrf_egress_denied_total` | Firewall/proxy chặn destination |
| `download_declared_bytes` / `received_bytes` | So length và bytes thực |
| `response_oversize_total` | Chặn dữ liệu vượt max ở precheck/stream |
| `decompressed_bytes_total` | Kiểm tra compression ratio/quota |
| `response_truncated_total` | Lỗi EOF/framing/body incomplete |
| `http_errors_by_status` | Phân biệt 4xx/5xx với network errors |
| `outbound_timeout_total` | Connect/idle/total deadline |
| `active_http_jobs` / `queue_depth` | Backpressure, overload |
| `retry_attempts_total` | Ngăn retry storm |

**Redaction:** đừng log nguyên URL nếu query chứa token, cookie, Authorization header, raw response payload, private IP/hostnames ở mức không cần thiết. Có thể log hash/định danh job, scheme, policy outcome, hop count, số bytes và status đã được kiểm soát.

Một dashboard "requests 200 = 99.9%" **không đủ** chứng minh độ tin cậy nếu 200 có wrong media type, incomplete body hoặc app không nhận được artifact đúng.

## 19. Bảng lỗi phổ biến

| Cách viết/hiểu sai | Rủi ro | Khắc phục |
| --- | --- | --- |
| `rawUrl.startsWith("https://trusted.example")` | Prefix spoof | Parse URI, compare exact host |
| `URI.create(url)` xong coi URL an toàn | SSRF tới địa chỉ hợp cú pháp | Validate origin + network egress |
| Chỉ chặn literal `127.0.0.1` | Bỏ qua private/IPv6/link-local/alias | IP/network policy đầy đủ |
| Lookup DNS trước rồi để HttpClient resolve lại | TOCTOU/rebinding | Network restriction tại actual connect |
| Auto-follow redirect sau preflight URL ban đầu | SSRF/credential leakage | NEVER + validate mỗi Location |
| Chỉ giới hạn số redirect bằng Set URI | Chuỗi URI luôn mới có thể vô hạn | Hop budget + total deadline |
| Cho mọi port của host hợp lệ | Đụng admin/debug endpoints | Port allowlist |
| Disable certificate validation để sửa HTTPS | MITM | Fix CA/hostname/trust store |
| Copy Authorization qua mọi redirect | Lộ secret | Origin-scoped credentials |
| Dựa vào Content-Length để cấp phát | OOM/overflow | Bounded stream |
| Chỉ precheck Content-Length | Chunked/no length bypass | Count bytes thực |
| Dùng String.length() tính network quota | Unicode nhiều byte | Byte count UTF-8 |
| Parse gzip raw bytes như JSON | Wrong payload | Decode có quota, đúng MIME |
| Chỉ nhìn 200 rồi lưu file | Error/truncation/integrity failure | Completion + expected digest |
| Dùng readAllBytes trên response untrusted | RAM exhaustion | Buffer & hard cap |
| Không đóng body của redirect/404 | Resource leak | try-with-resources |
| Chỉ đặt request timeout, bỏ idle-read | Stream có thể chờ rất lâu | Total/idle deadline + cancel |
| Retry non-idempotent POST mù | Side effect trùng | Idempotency key/transaction |
| Commit file trước EOF và hash | File dở dang có tên final | .part + validate + publish |
| Log raw URL/query/header | Lộ credential | Redact và audit có phạm vi |

## 20. Ma trận test bảo mật và độ tin cậy

| Ca test | Đầu vào hoặc server behavior | Kết quả cần đạt |
| --- | --- | --- |
| URL hợp đồng | HTTPS đúng origin/path | Request được phép, response hợp đồng |
| Userinfo | `user@host` | Reject |
| Host prefix spoof | `trusted.example.evil.test` | Reject |
| Schemes ngoài policy | `http/file/ftp` | Reject |
| Port cấm | Host hợp lệ trên admin port | Reject |
| Đường dẫn encoded | `%2e%2e`/double decoding | Reject theo router/contract |
| Redirect hợp lệ | Relative `/data` | Bounded follow |
| Redirect off-origin | Location host khác | Reject |
| Redirect HTTPS→HTTP | Downgrade | Reject |
| Redirect loop | A→B→A | Detect hoặc max hops |
| Redirect chain không lặp | URL mới liên tục | Max hops/deadline |
| DNS rebinding | Public DNS đổi private IP | Chặn ở egress/connect |
| IPv6 loopback/private | IPv6 địa chỉ nội bộ | Reject khi policy cấm |
| Proxy forwarding | Proxy tới metadata IP | Proxy/network guard reject |
| Header Content-Length lớn | Declared > max | Reject sớm |
| Chunked body lớn | Không có length cố định | Reject khi stream vượt max |
| Truncated response | Đóng trước bytes đã khai | Fail, không commit |
| Sai MIME | text/html thay JSON | Reject |
| Content-Encoding ngoài policy | gzip khi client chỉ nhận identity | Reject |
| Compression bomb | 1 KiB nén → 100 MiB | Decoded limit/CPU budget |
| JSON nesting quá sâu | Body nhỏ nhưng parser tốn CPU | Depth quota |
| Digest sai | Same byte length, wrong data | Không publish |
| Slow response | 1 byte / phút | Idle & total deadline |
| HTTP 404 có HTML body | App mong JSON | Không parse như success |
| Concurrent downloads | 1000 jobs cùng lúc | Bounded concurrency/queue |
| Redirect chứa Authorization | Target khác domain | Không forward secret |
| Process crash khi tải | .part còn tồn tại | Recovery cleanup theo owner/TTL |

**Phạm vi kiểm thử của demo mục 15 chỉ bao gồm GET/redirect/headers/stream và một số lỗi**, không chứng minh TLS, DNS rebinding, proxy egress, idempotency production hay load safety. Những chủ đề đó cần integration tests với hạ tầng kiểm soát được và fault injection.

## 21. Bài tập tự kiểm tra

**Câu 1.** Vì sao `https://trusted.example@evil.example/path` không được xác thực bằng `startsWith("https://trusted.example")`? Host thật là gì?

**Câu 2.** Client ban đầu GET tới `https://reports.example.com`, server trả `302 Location: http://127.0.0.1/admin`. Policy chỉ cho HTTPS origin A, có nên follow không?

**Câu 3.** Ứng dụng kiểm tra DNS trước `client.send`, sau đó DNS trả IP khác. Đây là loại rủi ro gì, nên enforce policy ở đâu?

**Câu 4.** Body không có Content-Length và server stream 20 MiB. Max ứng dụng 5 MiB. Kiểm tra `Content-Length` thôi có đủ không?

**Câu 5.** `String s = "Xin chào";`. `s.length()` là bao nhiêu, `s.getBytes(StandardCharsets.UTF_8).length` bao nhiêu?

**Câu 6.** Server khai gzip body 4 KiB nhưng sau giải nén thành 500 MiB. Có cần limit riêng cho decoded bytes không?

**Câu 7.** Server trả HTTP 200, có Content-Length 10000 nhưng đóng sau 1000 byte. Client có nên commit file không?

**Câu 8.** Content-Length và stream hoàn tất hợp lệ, nhưng SHA-256 khác trusted manifest. Dữ liệu có được coi đúng không?

**Câu 9.** Redirect A→B→C→D→... luôn đổi query nên không lặp URI chính xác. Cần guard bổ sung nào?

**Câu 10.** Vì sao không copy Authorization header của request A sang B khi redirect nếu B chưa thuộc allowlist?

**Câu 11.** Request upload có declared length nhỏ nhưng body thực quá lớn; ai phải áp quota? Có được cấp array từ header không?

**Câu 12.** `client.send(..., ofInputStream())` trả nhanh nhưng ứng dụng đọc stream rất lâu. Cần loại deadline nào ngoài connect/request timeout?

**Câu 13.** Ứng dụng chỉ xác minh IP proxy của outbound connection. Proxy lại truy cập internal metadata host. Vì sao chưa đủ?

**Câu 14.** Server trả 404 text/html nhưng ứng dụng chờ JSON. Nên làm gì trước khi parse?

**Câu 15.** Java code mẫu chỉ cho localhost, port test và một số path. Có thể copy nó làm SSRF protection cho URL từ Internet không?

### Đáp án gợi ý

1. Vì `trusted.example` là userinfo; host thật `evil.example`. Parse URI và reject userinfo.
2. Không, vi phạm cả HTTPS và origin policy; phải validate từng redirect.
3. DNS rebinding/TOCTOU; enforce ở actual egress/connect layer, kết hợp allowlist và firewall/proxy.
4. Không. Đếm bytes thực trong vòng stream đọc và reject trước khi vượt quota.
5. 8 UTF-16 code units và 9 UTF-8 bytes.
6. Có. Giới hạn compressed, decoded bytes, ratio/time/CPU.
7. Không. Body chưa hoàn tất theo framing; xử lý IOException/length mismatch, không publish.
8. Không. Đây là application-level integrity mismatch; fail closed.
9. Max redirect hops và total time budget; seen URI set chỉ là hỗ trợ.
10. Vì secret có origin scope; forward sang B có nguy cơ credential leakage.
11. Server/framework và application streaming reader đều phải enforce body quota. Không cấp phát theo untrusted header.
12. Total job deadline, idle-read timeout và cancellation/close body stream.
13. Proxy tự quyết định kết nối thật; policy phải áp tới destination ở proxy/egress.
14. Xử lý lỗi status/type, không parse như business data thành công.
15. Không. Demo bỏ qua TLS, DNS, proxy, egress, nhiều policy production; cần kiến trúc phòng thủ nhiều lớp.

## 22. Tài liệu chính thức và nguồn tham khảo

- [Java SE 17 — URI](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URI.html): parsing, `getScheme/getHost/getPort/getRawUserInfo`, `resolve` và `normalize`.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): tạo client và thực hiện request.
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): redirect policy, connect timeout, proxy, SSL.
- [Java SE 17 — HttpClient.Redirect](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html): `NEVER/NORMAL/ALWAYS` và hạn chế downgrade.
- [Java SE 17 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): request URI/method/timeout.
- [Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofInputStream`, `ofByteArray`, streaming behavior.
- [Java SE 17 — HttpHeaders](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpHeaders.html): `allValues` và `firstValue`.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): loopback test server.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): redirects, status, Content-Type, Content-Encoding và Content-Length.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112.html): message framing, truncated body và parsing ambiguity.
- [RFC 8259 — JSON](https://www.rfc-editor.org/rfc/rfc8259.html): JSON UTF-8 và content validation.
- [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): allowlist, IP egress, DNS rebinding, redirects.
- [OWASP — Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html): schema/range/type checks, allowlist và canonicalization.
