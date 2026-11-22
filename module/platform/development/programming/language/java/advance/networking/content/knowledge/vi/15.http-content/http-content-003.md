# Body có thể phát lại và điều kiện để gửi lại sau xác thực hoặc chuyển hướng

## Mục tiêu bài học

Trong HTTP, **gửi một request lần đầu** và **phát lại request body** là hai công việc khác nhau. Một request `POST` có thể đã truyền một phần hoặc toàn bộ nội dung khi server/proxy trả `401 Unauthorized`, `407 Proxy Authentication Required` hoặc `307 Temporary Redirect`. Nếu client cần gửi request thêm lần nữa, nguồn body phải tạo ra **cùng chuỗi byte từ đầu**. Một `InputStream` đã đọc tới cuối không tự quay lại đầu; một luồng sự kiện thời gian thực cũng không tự phát lại đúng bytes.

Trong Java 17, `java.net.http.HttpRequest.BodyPublisher` là cơ chế cung cấp body cho `HttpClient`. Client sử dụng mô hình `Flow.Publisher<ByteBuffer>`: mỗi lần HTTP request cần được gửi, có một subscription. **Nếu phải phát lại request, sẽ có subscription mới và publisher được kỳ vọng cung cấp cùng dữ liệu.** Với `BodyPublishers.ofInputStream(Supplier<InputStream>)`, supplier được dùng để cung cấp **stream mới** mỗi khi cần, vì Java không tự buffer toàn bộ nguồn stream. Nếu supplier không còn dữ liệu hoặc trả `null` ở lần sau, việc phát lại có thể thất bại.

Sau bài này, bạn có thể:

1. Phân biệt **replayable body** với **idempotent business operation** và với việc TCP tự retransmit byte.
2. Hiểu ngữ nghĩa của `BodyPublisher.subscribe(...)`, `contentLength()` và các factory `ofString`, `ofByteArray`, `ofFile`, `ofInputStream`, `ofByteArrays`, `fromPublisher`.
3. Biết khi nào `401`/`407` authentication challenge hoặc `301`/`302`/`303`/`307`/`308` redirect dẫn tới request mới **có hoặc không có body cũ**.
4. Tạo supplier trả về **một InputStream mới ở mỗi lần gọi**, không dùng lại một stream đã consumed hoặc mutable data bị thay đổi.
5. Quyết định có cho phép tự theo redirect/authentication retry hay cần dừng, hỏi lại người dùng, đối chiếu business outcome hoặc dùng idempotency key.
6. Chạy ba ví dụ Java 17+ độc lập trên **loopback**: redirect `307` và `303`; authentication `401`; và thất bại có chủ đích khi body chỉ đọc một lần.

## 1. Định nghĩa chính xác “phát lại”

Xét một client gửi:

```http
POST /orders HTTP/1.1
Host: api.example.test
Content-Type: application/json
Content-Length: 21

{"sku":"A1","qty":2}
```

Đây là định dạng dễ đọc; trên wire của HTTP/1.1, mỗi dòng header kết thúc bằng CRLF. Các byte body được truyền theo framing HTTP, không phải theo ranh giới gọi `OutputStream.write`.

Giả sử request gặp một trong hai tình huống:

- Server gửi `307 Location: /new-orders`, yêu cầu client tiếp tục **cùng method và body** ở URI khác.
- Server gửi `401 WWW-Authenticate`, client có quyền lấy credentials rồi gửi lại request với `Authorization` phù hợp.

Nếu tiếp tục, client phải đảm bảo request lần thứ hai có body **giống về mặt yêu cầu của giao thức và ứng dụng** với lần đầu. Đó là **replayability**. Việc phải gửi lại có thể xảy ra dù lần đầu body đã được đọc đến EOF, nên nguồn dữ liệu của body phải hỗ trợ **khởi tạo một lần đọc mới**.

### Ba tính chất dễ bị nhầm

| Thuộc tính | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| **Replayable body** | Có tạo lại được cùng sequence bytes khi HTTP client cần gửi lần nữa? | `byte[]` bất biến hoặc supplier mở mới stream từ dữ liệu cố định |
| **Idempotent operation** | Thực thi cùng một ý định nhiều lần có gây tác dụng nghiệp vụ khác một lần? | “Đặt status=PAID” có thể idempotent nếu thiết kế đúng, còn “tăng số dư 10” thì không |
| **Safe HTTP method** | Ngữ nghĩa method là chỉ đọc, không yêu cầu thay đổi trạng thái do client? | `GET` và `HEAD` theo semantics; vẫn có thể có logging/metrics phía server |

**Replayable không có nghĩa retry an toàn.** Một body có thể phát lại 100 lần nhưng server có thể tạo 100 đơn hàng nếu không có cơ chế idempotency. Ngược lại, một thao tác nghiệp vụ vốn idempotent vẫn có thể không phát lại được body nếu client phát một stream live chỉ dùng một lần.

### TCP retransmission cũng khác application replay

TCP có cơ chế truyền lại segment bị mất bên trong một connection. Nó không cần ứng dụng tự mở lại `InputStream` để “gửi lại một HTTP request mới”. Còn `HttpClient` khi thực sự gửi **một request HTTP khác** sau challenge/redirect có thể cần gọi lại body publisher. Giữ hai tầng này tách biệt khi debug.

## 2. Vì sao Java `HttpClient` có thể cần subscribe lại body?

Java 17 định nghĩa `HttpRequest.BodyPublisher` là một `Flow.Publisher<ByteBuffer>`. `HttpClient` subscribe vào publisher để nhận luồng các `ByteBuffer` chứa bytes body của **một lần gửi**. Khi cần resubmit request, client tạo **subscription mới** và mong publisher tạo lại cùng bytes; đây là hợp đồng quan trọng nhất của `BodyPublisher`.

```text
HttpRequest (POST, bodyPublisher)
          │
          ├── Lần gửi 1
          │      BodyPublisher.subscribe(subscriber#1)
          │           -> ByteBuffer A1, A2, ... -> onComplete
          │
          ├── HTTP response: 307/308 hoặc 401/407
          │
          └── Có chính sách cho phép tiếp tục?
                 │
                 ├── Không -> trả response/lỗi cho caller
                 │
                 └── Có, phải giữ method + body
                       BodyPublisher.subscribe(subscriber#2)
                            -> A1, A2, ... GIỐNG LẦN 1
```

**Không phải mọi HTTP response đều dẫn tới resubscribe**: `303` thường chuyển POST thành GET, không cần gửi lại POST body; policy `Redirect.NEVER` không theo redirect; xác thực có thể thất bại hoặc chưa được cấu hình; client có thể dừng theo giới hạn retry/redirect.

Ngoài ra, ở lần đầu server có thể trả response **trước khi đọc hết body**. Subscription ban đầu có thể đã gửi hết, mới gửi một phần, hoặc bị cancel. Publisher vẫn phải chuẩn bị cho trường hợp request được phát lại nếu hợp đồng yêu cầu.

### 2.1. `contentLength()` không tạo khả năng phát lại

`BodyPublisher.contentLength()`:

- Trả `>0` nếu độ dài body đã biết và dương.
- Trả `0` khi không có body bytes; implementation có thể không subscribe publisher body rỗng.
- Trả số âm (thường `-1`) khi không biết trước độ dài.
- Theo Javadoc, `contentLength()` có thể được gọi nhiều lần và **phải trả cùng một giá trị bất biến**.

Một publisher biết độ dài 5 bytes vẫn có thể là **one-shot**: nó phát được 5 bytes ở subscription đầu nhưng không còn nguồn ở subscription sau. Ngược lại, một publisher có `contentLength()==-1` vẫn có thể phát lại đầy đủ nếu mỗi subscription tạo được cùng bytes từ đầu.

Với HTTP/1.1, body length không biết trước có thể được client mã hóa `Transfer-Encoding: chunked` theo giao thức; với HTTP/2 framing là cơ chế khác. **Không tự gán `Content-Length` thủ công** để “ép” client phát lại; hãy để `BodyPublisher` khai báo đúng kích thước hoặc để HTTP client chọn framing.

### 2.2. Ownership của `ByteBuffer`

Javadoc `BodyPublisher` yêu cầu publisher cấp phát các `ByteBuffer` được phát ra và **không tiếp tục truy cập** buffer sau khi đưa cho HTTP client. Custom publisher không nên tái sử dụng cùng mutable `ByteBuffer` cho hai concurrent subscriptions hoặc sửa `position/limit` sau `onNext`. Vi phạm có thể làm body sai, race hoặc lỗi khi redirect/authentication.

Để hỗ trợ retry từ nguồn lớn, publisher nên sở hữu cơ chế tạo **dòng dữ liệu mới**, có cleanup và backpressure phù hợp; không cần giữ toàn bộ body trên heap nếu có thể phát lại từ file/snapshot ổn định.

## 3. Các `BodyPublishers` trong Java 17: chọn loại nào?

| Factory | Nguồn dữ liệu | Khả năng phát lại và điều kiện | Rủi ro |
|---|---|---|---|
| `noBody()` | Không có body | Không cần tái tạo bytes | Không đại diện cho một POST body bị mất |
| `ofString(String)` | Nội dung chuỗi được mã hóa, mặc định UTF-8 | Phù hợp body nhỏ, ổn định | Không nên nhầm `String.length()` với số bytes |
| `ofByteArray(byte[])` | Mảng bytes | Có thể tạo lại bytes nếu dữ liệu không bị thay đổi trong lúc gửi | Mảng mutable từ bên ngoài, lỗi khi sửa nội dung |
| `ofByteArray(buf,offset,length)` | Một vùng trong mảng bytes | Tương tự, nhưng giới hạn vào vùng được chỉ định | Dữ liệu vùng đó thay đổi giữa attempts |
| `ofFile(Path)` | File theo đường dẫn | Cho phép đọc từ file; cần đảm bảo file còn tồn tại và nội dung giữ nguyên | File bị sửa/xóa, quyền đọc, data race, TOCTOU |
| `ofInputStream(Supplier<InputStream>)` | Stream do supplier cấp | **Mỗi lần cần phải có stream mới** đọc được từ đầu với cùng bytes | Reuse stream đã đọc/đã đóng, supplier trả null, nguồn live thay đổi |
| `ofByteArrays(Iterable<byte[]>)` | Iterable tạo các byte arrays | Java gọi iterable/iterator cho mỗi attempt; phải có dữ liệu tương đương ở lần sau | One-shot iterator, mutation, mất snapshot |
| `fromPublisher(Flow.Publisher)` | Publisher tự định nghĩa | Chỉ replayable nếu publisher hỗ trợ nhiều subscriptions tái tạo cùng dữ liệu | “Hot” publisher, single-subscriber publisher, state đã hết |
| `concat(publishers...)` | Nối nhiều publishers | Toàn chuỗi chỉ replayable khi **mọi** thành phần có thể tạo lại bytes | Một thành phần one-shot làm cả body khó phát lại |

**Không có cờ `isReplayable()` phổ quát trên interface `BodyPublisher` của Java 17.** Caller phải hiểu contract của nguồn và sẵn sàng cho lỗi khi client thử resubscribe. Với custom publisher, phải đảm bảo tuân thủ `Flow.Subscription.request(n)`, `cancel()`, `onError/onComplete` và chính sách giới hạn tài nguyên.

### 3.1. Body chuỗi/byte nhỏ

```java
// Trích đoạn minh họa, chưa có URI/client/main đầy đủ.
byte[] canonicalPayload = "{\"count\":2}"
        .getBytes(java.nio.charset.StandardCharsets.UTF_8);

byte[] stableCopy = canonicalPayload.clone();
var publisher = java.net.http.HttpRequest.BodyPublishers
        .ofByteArray(stableCopy);
```

Nên xem bytes gốc là **bất biến về mặt ứng dụng** cho mọi attempt. Dùng `clone()` trước khi đưa vào publisher nếu nơi khác có thể sửa mảng. Bản thân `clone()` không tự bảo vệ bạn khỏi việc code khác giữ reference tới `stableCopy` và sửa nó sau đó.

### 3.2. Body từ file

```java
// Trích đoạn minh họa: path là java.nio.file.Path đã có sẵn.
var publisher = java.net.http.HttpRequest.BodyPublishers.ofFile(path);
```

Chỉ tạo publisher từ `Path` không chứng minh nội dung file bất biến qua redirect/authentication. Với file upload quan trọng, có thể tạo **snapshot file riêng** hoặc ghi checksum/size và xác minh trước mỗi attempt. Nếu file bị thay đổi giữa hai lần đọc, hai HTTP requests có thể mang **hai bodies khác nhau** dù cùng file path.

### 3.3. Body từ stream: sai và đúng

**Sai — cùng một InputStream đóng/mất position sau lần đọc đầu:**

```java
// Chỉ là minh họa anti-pattern; không dùng làm request production.
java.io.InputStream oneShot = new java.io.ByteArrayInputStream(
        "HELLO".getBytes(java.nio.charset.StandardCharsets.UTF_8));

var wrong = java.net.http.HttpRequest.BodyPublishers.ofInputStream(
        () -> oneShot); // Mọi attempt dùng chung stream đã consumed.
```

Một stream thông thường **không tự rewind** khi client subscribe lại. Trả cùng stream đã đọc có thể khiến lần sau đọc 0 bytes, sai body hoặc ném exception.

**Đúng — tạo stream mới từ nguồn bytes ổn định:**

```java
// Đoạn minh họa, "snapshot" không được thay đổi giữa các attempts.
byte[] snapshot = "HELLO".getBytes(
        java.nio.charset.StandardCharsets.UTF_8);

var replayable = java.net.http.HttpRequest.BodyPublishers.ofInputStream(
        () -> new java.io.ByteArrayInputStream(snapshot));
```

Nếu body lớn, supplier có thể mở **một InputStream mới** cho file snapshot, nhưng phải có lifecycle và xử lý lỗi mở file. Một `Supplier` trả `null` ở lần tiếp theo là trường hợp được Javadoc mô tả: request sẽ thất bại khi không lấy được stream mới, không được HTTP client tự tạo bytes cũ từ không khí.

## 4. Tại sao `401` và `407` có thể cần gửi lại request?

### 4.1. `401 Unauthorized`: origin server thách thức xác thực

Một vòng điển hình:

```text
Client                           Origin server
  │ POST /upload, body bytes        │
  ├────────────────────────────────►│
  │ 401 Unauthorized                │
  │ WWW-Authenticate: Basic ...     │
  │◄────────────────────────────────┤
  │                                 │
  │ [Client xác định có credentials hợp lệ]
  │ POST /upload với Authorization  │
  │ + body bytes phát lại           │
  ├────────────────────────────────►│
  │ 200 OK hoặc lỗi khác            │
  │◄────────────────────────────────┤
```

`401` chỉ ra server cần xác thực cho tài nguyên, thường kèm `WWW-Authenticate` để mô tả challenge. Client **không buộc phải retry**: còn tùy credentials, policy, scheme, giới hạn attempts, độ tin cậy của server và body có thể phát lại không. Nếu retry giữ nguyên method + body, client phải phát lại body một cách tương thích.

Một request có thể bị server/proxy đọc đầy đủ trước khi trả challenge, hoặc có thể bị thách thức sớm trước body. Không có bảo đảm chung rằng mọi `401` luôn xảy ra trước khi bất kỳ body byte nào được truyền.

### 4.2. `407 Proxy Authentication Required`

`407` là challenge từ **proxy**, với `Proxy-Authenticate` và thông tin đáp ứng tương ứng `Proxy-Authorization`. Không được nhầm `407` với một `401` do origin server phát. Với proxy, challenge có thể nằm ở bước kết nối proxy, bước `CONNECT` tunnel hoặc bước chuyển tiếp request, tùy proxy/protocol.

- `Authorization` dành cho **origin**; `Proxy-Authorization` dành cho **proxy**.
- Credentials ở các hop **không được lẫn với nhau**.
- Một vòng proxy auth có thể làm client phải thực hiện lại request, nhưng số lần truyền body thực tế còn tùy thời điểm challenge và client implementation.
- Không đưa proxy credentials trực tiếp vào header của request origin hoặc ghi lộ vào log. Java `HttpClient` có thể cấu hình `Authenticator` theo proxy/origin, nhưng phải xem đúng policy và ngữ cảnh hệ thống.

### 4.3. `Expect: 100-continue` có giải quyết hết không?

`Expect: 100-continue` cho phép client gửi headers trước, chờ tín hiệu interim `100 Continue` trong một số trường hợp, rồi mới gửi body; server có thể trả response lỗi/auth sớm. Java `HttpRequest.Builder.expectContinue(true)` hỗ trợ yêu cầu này.

Nhưng **đừng coi đó là bảo đảm body chưa bao giờ được gửi**:

- Server/proxy có thể không hỗ trợ hoặc xử lý khác, client có timeout/implementation policy.
- Response có thể đến sau khi một phần body đã bắt đầu truyền.
- Nếu một challenge khác xảy ra hoặc request được redirect preserving method, vẫn có thể cần body replayable.
- `100 Continue` chỉ là interim response cho việc **tiếp tục truyền**, không có nghĩa request đã được xác thực hay side effect chưa xảy ra.

Vì vậy `Expect: 100-continue` hữu ích để **tránh gửi body lớn không cần thiết**, nhưng không thay thế supplier tái tạo bytes hoặc chính sách idempotency.

## 5. Redirect: status nào giữ body, status nào đổi method?

Các status redirect không giống nhau. Theo RFC 9110, đặc biệt `15.4`:

| Status | Ý nghĩa | Đối với POST khi theo redirect | Cần phát lại POST body? |
|---|---|---|---|
| `301 Moved Permanently` | URI mới lâu dài | User agent **được phép** chuyển POST thành GET; JDK HttpClient có quy tắc chuyển POST→GET | Nếu chuyển GET thì **không**; nếu giữ POST theo policy khác thì **có** |
| `302 Found` | URI thay thế tạm thời | Tương tự 301, có thể chuyển POST thành GET; JDK HttpClient chuyển POST→GET | Phụ thuộc method được chọn |
| `303 See Other` | Xem kết quả ở URI khác | Thông thường gửi **GET** (hoặc HEAD thích hợp), bỏ POST body | **Không** mang lại POST body |
| `307 Temporary Redirect` | Chuyển tạm **không đổi method** | Phải giữ method, và thông thường giữ body | **Có**, nếu POST có body |
| `308 Permanent Redirect` | Chuyển lâu dài **không đổi method** | Phải giữ method, và thông thường giữ body | **Có**, nếu POST có body |

Một redirect hợp lệ thường mang `Location`. Chỉ nhìn mã 3xx chưa đủ; cần biết có `Location`, URI mục tiêu hợp lệ, protocol scheme, host/origin thay đổi hay không, giới hạn redirect và app có quyền gửi body/credentials tới nơi mới không.

### 5.1. `307` và `308`: bắt buộc giữ method nếu redirect

`307` và `308` được tạo để tránh nhập nhằng lịch sử 301/302. Nếu user agent quyết định tự động follow, **không được biến POST thành GET** chỉ để khỏi cần phát lại body. Nếu body đã consumed và nguồn không thể tạo lại, lựa chọn đúng là **không follow hoặc báo lỗi**, chứ không gửi request GET âm thầm thay thế một POST có side effect.

### 5.2. `303`: xem kết quả bằng request khác

Một server có thể dùng pattern POST→303→GET:

```text
POST /orders                -> 303 See Other
                               Location: /orders/123

GET  /orders/123            -> 200 OK (xem trạng thái đơn)
```

GET sau redirect **không phải việc phát lại POST body**. Nó là một request mới có method khác được chuẩn hóa theo redirect semantics. Đừng hiểu `303` là bảo đảm POST ban đầu chưa thực hiện; thường POST đã tạo tài nguyên rồi server mới chỉ URI kết quả.

### 5.3. Java 17 `HttpClient.Redirect`

`HttpClient.Redirect` có các policy:

- `NEVER`: không follow tự động; caller nhận response 3xx và tự quyết định.
- `NORMAL`: follow tự động, **ngoại trừ redirect từ HTTPS xuống HTTP**.
- `ALWAYS`: cho phép follow theo chính sách client cả trường hợp downgrade; **không nên tùy tiện dùng** với token/body nhạy cảm.

**Policy mặc định của Java 17 `HttpClient` là `NEVER`.** Để tự follow, phải cấu hình:

```java
// Đoạn minh họa, cần import HttpClient.
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
```

Javadoc Java 17 ghi rõ Java HTTP client có hành vi **chuyển POST thành GET khi theo `301` hoặc `302`**. Với `307`/`308` giữ method; với `303` thường chuyển sang GET. Khi không tự follow, response 3xx và `Location` được caller xử lý, không mặc nhiên tạo một request tiếp theo.

**Chính sách follow không tự bảo đảm body replayable**: redirect chỉ nói *nên gửi request nào tiếp*, còn publisher phải tạo lại bytes nếu request tiếp theo cần giữ body.

## 6. Redirect khác origin: kiểm tra dữ liệu và credentials trước khi resend

Một `Location` có thể trỏ tới đường dẫn tương đối trong cùng origin, hoặc URI tuyệt đối tới **host khác**. Khi thay đổi origin, việc tự động gửi lại body có thể **tiết lộ thông tin** ngay cả khi client xử lý `Authorization` hợp lý:

```text
POST https://api.company.example/upload
Body = tài liệu nội bộ
   |
   | 307 Location: https://external.example/collect
   v
POST body nội bộ sang một origin khác?   <-- CẦN policy cho phép!
```

Đây là sơ đồ cảnh báo, không phải địa chỉ thật được khuyến nghị. Những nguyên tắc cần có:

1. **Chỉ follow tới origin tin cậy**, đặc biệt khi body chứa PII, file nội bộ, secrets hoặc giao dịch có side effect.
2. Kiểm tra **scheme**: tránh chuyển HTTPS→HTTP; `Redirect.NORMAL` từ chối downgrade này, nhưng vẫn phải đánh giá redirects khác.
3. Xác minh domain/port/đường dẫn mục tiêu, giới hạn số lần redirect và chu trình lặp; không tin tuyệt đối một `Location` do server trả nếu server đó có thể bị tấn công.
4. Xử lý **Authorization, Cookie, Proxy-Authorization** theo đúng scope và policy; không copy nguyên các header nhạy cảm sang origin khác trong client tự viết.
5. Với `307`/`308`, ngoài method còn có body gốc, nên rủi ro lộ dữ liệu có thể cao hơn `303` chuyển sang GET. **Ngay cả GET** vẫn có thể có secrets trong URI/query, nên không mặc định an toàn.
6. Với workflow thay đổi trạng thái quan trọng, cân nhắc `Redirect.NEVER` rồi **kiểm tra thủ công** `Location`, target allowlist và consent trước khi gửi lại.

**Không chỉ dựa vào publisher tạo được body.** Một publisher replayable là điều kiện kỹ thuật, còn **được phép gửi tới đâu** là điều kiện bảo mật/nghiệp vụ độc lập.

## 7. Java 17+: `307` phát lại body, `303` đổi sang GET

Ví dụ này chạy một `HttpServer` tại loopback trên port động; cả hai redirect là **same-origin**. Nó không yêu cầu Internet hoặc tài khoản. Server đọc body của request đầu trước khi phát redirect, nên ta quan sát rõ rằng body source phải được mở lại.

- `/redirect307` đọc POST body và trả `307 Location: /final307`.
- `/final307` kiểm tra method và body khi HTTP client follow.
- `/redirect303` trả `303 Location: /final303`.
- `/final303` kiểm tra method sau khi follow.
- `BodyPublishers.ofInputStream` tăng counter mỗi khi supplier mở một stream mới.

**Tệp `RedirectReplayDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayInputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class RedirectReplayDemo {
    private static void reply(com.sun.net.httpserver.HttpExchange exchange,
                              int code, String text) throws java.io.IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(code, bytes.length);
        try (var out = exchange.getResponseBody()) { out.write(bytes); }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        AtomicInteger opens307 = new AtomicInteger();
        AtomicInteger opens303 = new AtomicInteger();
        AtomicReference<String> target307 = new AtomicReference<>("");
        AtomicReference<String> target303 = new AtomicReference<>("");
        try {
            server.createContext("/redirect307", ex -> {
                try (ex) {
                    ex.getRequestBody().readAllBytes();
                    ex.getResponseHeaders().set("Location", "/final307");
                    ex.sendResponseHeaders(307, -1);
                }
            });
            server.createContext("/final307", ex -> {
                try (ex) {
                    target307.set(ex.getRequestMethod() + ":" + new String(
                            ex.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
                    reply(ex, 200, "OK307");
                }
            });
            server.createContext("/redirect303", ex -> {
                try (ex) {
                    ex.getRequestBody().readAllBytes();
                    ex.getResponseHeaders().set("Location", "/final303");
                    ex.sendResponseHeaders(303, -1);
                }
            });
            server.createContext("/final303", ex -> {
                try (ex) {
                    target303.set(ex.getRequestMethod() + ":" +
                            ex.getRequestBody().readAllBytes().length);
                    reply(ex, 200, "OK303");
                }
            });
            server.start();

            URI base = URI.create("http://localhost:" + server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .followRedirects(HttpClient.Redirect.NORMAL)
                    .connectTimeout(Duration.ofSeconds(3)).build();

            HttpRequest p307 = HttpRequest.newBuilder(base.resolve("/redirect307"))
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.ofInputStream(() -> {
                        opens307.incrementAndGet();
                        return new ByteArrayInputStream(
                                "PAYLOAD".getBytes(StandardCharsets.UTF_8));
                    })).build();
            var r307 = client.send(p307, HttpResponse.BodyHandlers.ofString());

            HttpRequest p303 = HttpRequest.newBuilder(base.resolve("/redirect303"))
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.ofInputStream(() -> {
                        opens303.incrementAndGet();
                        return new ByteArrayInputStream(
                                "PAYLOAD".getBytes(StandardCharsets.UTF_8));
                    })).build();
            var r303 = client.send(p303, HttpResponse.BodyHandlers.ofString());

            System.out.println("307 status: " + r307.statusCode());
            System.out.println("307 destination: " + target307.get());
            System.out.println("307 stream openings: " + opens307.get());
            System.out.println("303 status: " + r303.statusCode());
            System.out.println("303 destination: " + target303.get());
            System.out.println("303 stream openings: " + opens303.get());
        } finally { server.stop(0); }
    }
}
```

Chạy trong thư mục chứa tệp trên bằng **JDK 17 trở lên**:

```bash
javac --release 17 -encoding UTF-8 RedirectReplayDemo.java
java RedirectReplayDemo
```

**Stdout đã được biên dịch và chạy kiểm chứng trên loopback:**

```text
307 status: 200
307 destination: POST:PAYLOAD
307 stream openings: 2
303 status: 200
303 destination: GET:0
303 stream openings: 1
```

**Phân tích:**

- `307 status: 200` là **status cuối cùng sau khi tự follow**, không phải server đầu trả 200. Server đầu trả `307`; response mà caller nhận sau redirect có status `200`.
- `307 destination: POST:PAYLOAD` xác nhận request tiếp theo giữ **POST** và mang chính payload đầu.
- `307 stream openings: 2` xác nhận supplier đã tạo một `ByteArrayInputStream` cho mỗi lần gửi. Đây là ví dụ cụ thể vì sao không trả cùng một `InputStream` đã consumed.
- Với `303`, client chuyển sang **GET**; `GET:0` cho thấy body của request mới dài 0. Supplier chỉ mở một lần cho POST ban đầu.
- Server dùng port ngẫu nhiên trên `InetAddress.getLoopbackAddress()`, không gửi body ra Internet. Không có cơ chế idempotency trong demo; hai endpoints chỉ quan sát requests.
- `HttpClient.Redirect.NORMAL` được bật rõ; nếu bỏ `followRedirects`, policy mặc định `NEVER` nên ví dụ không tự follow.
- Mặc dù demo cho thấy số lần mở stream là 2/1, số subscription thực tế trong một app lớn còn có thể phụ thuộc cancellation, retry nội bộ, lỗi kết nối hoặc policy. **Không dùng con số cứng 2** để viết logic nghiệp vụ; supplier phải có khả năng cung cấp đúng dữ liệu cho mọi attempt hợp lệ.

Ví dụ này minh họa cả **method preservation** và **body replay**, không phải bảo đảm một thao tác POST thật chỉ được thực hiện một lần.

## 8. Java 17+: authentication `401` làm body được đọc lại

Ví dụ thứ hai tạo một `HttpServer` loopback yêu cầu **Basic authentication**. Request đầu được server đọc body nhưng không có credentials phù hợp, nên trả `401` cùng `WWW-Authenticate`. Java `HttpClient` có `Authenticator` cung cấp credentials, sau đó tạo request mới kèm authentication và **phát lại POST body**.

**Chỉ sử dụng thông tin đăng nhập giả trên loopback**. Basic authentication gửi mật khẩu dưới dạng Base64, **không phải mã hóa bảo mật**; ngoài môi trường local test, cần HTTPS/TLS và chính sách quản lý secrets. Không hard-code mật khẩu thật vào source.

**Tệp `AuthenticationReplayDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayInputStream;
import java.net.Authenticator;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.PasswordAuthentication;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;
import java.util.concurrent.atomic.AtomicInteger;

public class AuthenticationReplayDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        AtomicInteger attempts = new AtomicInteger();
        AtomicInteger streams = new AtomicInteger();
        String expectedHeader = "Basic " + Base64.getEncoder().encodeToString(
                "demo:secret".getBytes(StandardCharsets.ISO_8859_1));
        try {
            server.createContext("/secure", exchange -> {
                try (exchange) {
                    attempts.incrementAndGet();
                    byte[] body = exchange.getRequestBody().readAllBytes();
                    boolean authorized = expectedHeader.equals(
                            exchange.getRequestHeaders().getFirst("Authorization"));
                    if (!authorized) {
                        exchange.getResponseHeaders().add(
                                "WWW-Authenticate", "Basic realm=\"local-demo\"");
                        exchange.sendResponseHeaders(401, -1);
                    } else {
                        String text = new String(body, StandardCharsets.UTF_8);
                        byte[] response = ("accepted:" + text)
                                .getBytes(StandardCharsets.UTF_8);
                        exchange.sendResponseHeaders(200, response.length);
                        try (var out = exchange.getResponseBody()) {
                            out.write(response);
                        }
                    }
                }
            });
            server.start();

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .authenticator(new Authenticator() {
                        @Override
                        protected PasswordAuthentication getPasswordAuthentication() {
                            return new PasswordAuthentication(
                                    "demo", "secret".toCharArray());
                        }
                    }).build();
            URI url = URI.create(
                    "http://localhost:" + server.getAddress().getPort() + "/secure");
            HttpRequest request = HttpRequest.newBuilder(url)
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.ofInputStream(() -> {
                        streams.incrementAndGet();
                        return new ByteArrayInputStream(
                                "HELLO".getBytes(StandardCharsets.UTF_8));
                    })).build();
            var response = client.send(request, HttpResponse.BodyHandlers.ofString());
            System.out.println("Final status: " + response.statusCode());
            System.out.println("Final body: " + response.body());
            System.out.println("Server attempts: " + attempts.get());
            System.out.println("Supplier openings: " + streams.get());
        } finally { server.stop(0); }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 AuthenticationReplayDemo.java
java AuthenticationReplayDemo
```

**Stdout đã kiểm chứng:**

```text
Final status: 200
Final body: accepted:HELLO
Server attempts: 2
Supplier openings: 2
```

Diễn giải:

1. Request đầu vào `/secure` chưa có `Authorization` hợp lệ. Server **đọc body trước khi trả 401** để nhấn mạnh không thể dựa vào “401 chắc xảy ra trước khi body được tiêu thụ”.
2. `WWW-Authenticate: Basic realm="local-demo"` là challenge gửi về từ origin.
3. `HttpClient` hỏi `Authenticator`; ở lần tiếp theo client cung cấp credentials và request **vẫn là POST với body HELLO**.
4. `Supplier openings: 2` nghĩa là supplier đã tạo hai `ByteArrayInputStream` khác nhau có bytes giống nhau. Sử dụng stream cũ sau khi bị đọc hết sẽ không thỏa hợp đồng.
5. `Server attempts: 2` là số lần handler thấy HTTP request trong demo, **không nên suy ra luôn có đúng hai attempts** với mọi authentication scheme, proxy hay network.
6. `Final status: 200` là response cuối; caller không nhìn thấy intermediate 401 theo cách `client.send` tự xử lý challenge trong thí nghiệm này.
7. Mục tiêu demo là **khả năng phát lại**, không phải hướng dẫn authentication production. Trong ứng dụng thật, kiểm tra host/origin, scheme TLS, challenge realm, giới hạn thử và secret handling; không in credentials/Authorization vào logs.

**Proxy `407` có nguyên tắc tương tự về nhu cầu có lại body**, nhưng thông điệp dùng `Proxy-Authenticate`/`Proxy-Authorization` và còn tùy proxy configuration. Thí nghiệm không giả lập một proxy thật, nên không khẳng định đã kiểm thử `407`.

## 9. Java 17+: one-shot stream thất bại khi redirect cần resend

Ví dụ thứ ba cố ý tạo **body không replayable**. Supplier chỉ cấp một `ByteArrayInputStream` ở lần gọi thứ nhất; ở lần gọi thứ hai nó trả `null`. Server trả `307`, khiến Java HTTP client phải tái tạo POST body ở URI mới. Theo Javadoc của `BodyPublishers.ofInputStream`, nếu supplier trả `null` trong attempt tiếp theo thì request sẽ thất bại.

**Tệp `OneShotReplayFailureDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayInputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

public class OneShotReplayFailureDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        AtomicInteger supplierCalls = new AtomicInteger();
        AtomicInteger redirectedHits = new AtomicInteger();
        try {
            server.createContext("/first", ex -> {
                try (ex) {
                    ex.getRequestBody().readAllBytes();
                    ex.getResponseHeaders().add("Location", "/second");
                    ex.sendResponseHeaders(307, -1);
                }
            });
            server.createContext("/second", ex -> {
                try (ex) {
                    redirectedHits.incrementAndGet();
                    ex.getRequestBody().readAllBytes();
                    ex.sendResponseHeaders(200, -1);
                }
            });
            server.start();
            URI uri = URI.create(
                    "http://localhost:" + server.getAddress().getPort() + "/first");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .followRedirects(HttpClient.Redirect.NORMAL)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.ofInputStream(() -> {
                        if (supplierCalls.incrementAndGet() != 1) return null;
                        return new ByteArrayInputStream(
                                "ONCE".getBytes(StandardCharsets.UTF_8));
                    })).build();
            boolean failed = false;
            try {
                client.send(request, HttpResponse.BodyHandlers.discarding());
            } catch (java.io.IOException expected) {
                failed = true;
            }
            System.out.println("Resend failed: " + failed);
            System.out.println("Supplier calls: " + supplierCalls.get());
        } finally { server.stop(0); }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 OneShotReplayFailureDemo.java
java OneShotReplayFailureDemo
```

**Stdout đã kiểm chứng:**

```text
Resend failed: true
Supplier calls: 2
```

Điều cần hiểu:

- Ở lần đầu supplier trả `ByteArrayInputStream("ONCE")`; server `/first` đọc body và trả 307.
- Follow 307 giữ POST và cần body, nên client gọi supplier thêm lần nữa.
- Supplier **trả `null` theo chủ đích**: không có stream mới. Java HTTP client không tự lưu nội dung trước để tái tạo body, và việc resend báo lỗi I/O.
- `Resend failed: true` là cách in có kiểm soát cho kết quả kiểm thử, không khuyến nghị dùng catch-all rồi nuốt IOException trong ứng dụng thật. Production phải log/ngữ cảnh hóa lỗi, đảm bảo cleanup và đưa ra hành vi phục hồi phù hợp.
- Cảnh báo quan trọng: server đầu **đã nhận và đọc body**. Việc follow thất bại **không chứng minh request đầu chưa tác động lên nghiệp vụ**. Với thao tác như đặt hàng, người gọi không nên tự tạo request ID mới để “gửi lại cho chắc” nếu không có cơ chế dedup.
- `redirectedHits` trong demo là một counter quan sát phía server đích, không được dùng để tự quyết định giao dịch thành công. Demo cố tình chỉ in hai dòng ổn định để minh họa lần gọi supplier.

Nếu body thực là camera stream hoặc socket stream chỉ đọc một lần, giải pháp thường là **không tự follow các redirect giữ body**, hoặc tạo snapshot/seekable source phù hợp trước khi bắt đầu. Không thể “sửa” bằng `InputStream.mark/reset` khi loại stream không hỗ trợ hoặc dữ liệu đã đổi.

## 10. Giữ body ổn định giữa các attempts

Việc trả stream mới mỗi lần **chưa đủ** nếu nó tạo ra **nội dung khác nhau**. Ví dụ:

```java
// Anti-pattern minh họa: timestamp thay đổi ở từng attempt.
var publisher = java.net.http.HttpRequest.BodyPublishers.ofInputStream(
        () -> new java.io.ByteArrayInputStream(
                ("sentAt=" + System.nanoTime())
                        .getBytes(java.nio.charset.StandardCharsets.UTF_8)));
```

Mỗi subscription đọc được dữ liệu nhưng body khác nhau. Nếu server dùng chữ ký HMAC, request ID, checksum hoặc business idempotency key, sự khác biệt ấy có thể làm xác thực hoặc dedup thất bại. Một body có thể được **kỹ thuật phát lại** nhưng không thỏa điều kiện **cùng ý định/cùng payload**.

### 10.1. Snapshot trước khi gửi

Phù hợp cho body nhỏ:

```java
// Đoạn minh họa: serialize một lần trước khi xây HttpRequest.
byte[] snapshot = "{\"amount\":100}"
        .getBytes(java.nio.charset.StandardCharsets.UTF_8);
byte[] stable = snapshot.clone();

var body = java.net.http.HttpRequest.BodyPublishers.ofInputStream(
        () -> new java.io.ByteArrayInputStream(stable));
```

Với body lớn, không nên luôn load vào heap; có thể dùng immutable temporary file, object storage snapshot theo version hoặc nhà cung cấp luồng đọc lại từ offset 0. Cần kiểm soát thời gian lưu, cleanup, quyền truy cập, hash/size và tránh file bị ghi trong lúc resend.

### 10.2. Dữ liệu không thể phát lại

Các nguồn **không tự replayable**:

- Camera/audio live stream chưa được ghi lại.
- `InputStream` của file/socket đã đọc đến cuối mà không có cách reopen.
- Reactive `Flow.Publisher` “hot” chỉ phát sự kiện hiện tại và không hỗ trợ replay.
- Một iterable gắn với một `Iterator` đã consumed thay vì sinh iterator mới.
- Stream dùng một token chỉ hiệu lực một lần hoặc phụ thuộc trạng thái thay đổi sau lần đọc đầu.

Với các nguồn này, thường cần **bắt đầu lại từ nguồn được phép**, lưu snapshot trước khi gửi hoặc tắt automatic replay. Nếu server vẫn cần cho phép upload lớn với auth, có thể **xác thực trước bằng request nhỏ**, upload theo chunks có checksum/offset/commit protocol, hoặc dùng một URI/credential đã xác minh. Thiết kế upload resumable thường tốt hơn “retry nguyên một stream không thể tái tạo”.

### 10.3. Content-Length biết trước không đồng nghĩa snapshot

Ngay cả khi publisher báo `contentLength()==N`, bạn vẫn phải đảm bảo mỗi attempt gửi **đúng N bytes**. Một source file bị cắt hoặc supplier trả stream ngắn hơn có thể khiến request lỗi. Ngược lại, một publisher streaming báo unknown length có thể hợp lệ nếu giao thức và library hỗ trợ; điều quan trọng với replay là **nội dung sinh lại được**, không phải chỉ con số N.

## 11. Phát lại và an toàn nghiệp vụ: hai lớp bảo vệ

Một vòng retry có thể làm server nhận **hai HTTP requests độc lập**. Ví dụ:

```text
POST /charge, requestId=pay-001
    → server commit thanh toán
    → response 200 bị mất hoặc client chưa nhận

Client retry vì timeout / auth flow / redirect
    POST /charge, requestId=pay-001
    → nếu server không dedup, có thể charge thêm lần nữa
```

Ngay cả một body ổn định 100% vẫn có thể tạo side effect lặp. Với nghiệp vụ không idempotent cần:

1. **Mã ý định nghiệp vụ ổn định** cho mọi attempts của cùng thao tác, ví dụ `Idempotency-Key` theo hợp đồng API. Không tạo ID mới trong mỗi retry.
2. **Server lưu kết quả theo khóa + scope + fingerprint payload** và đảm bảo xử lý đồng thời/crash theo transaction hoặc cơ chế idempotent phù hợp.
3. **Phân biệt response cuối** với response trung gian; trạng thái timeout chưa chứng minh request chưa commit.
4. **Giới hạn thời gian và số attempts**, retry có backoff/jitter khi phù hợp; không cho phép vòng redirect/auth vô hạn.
5. Với redirect giữ method, xác minh **location đích thực sự được quyền xử lý cùng ý định**; không tự gửi lệnh thanh toán tới origin ngẫu nhiên.
6. Nếu không thể xác định outcome, **truy vấn trạng thái nghiệp vụ** theo transaction ID thay vì tùy tiện phát lại với ID mới.

### Các tình huống không nên retry tự động

| Tình huống | Vì sao cần dừng/kiểm tra |
|---|---|
| `POST /charge` không có idempotency contract | Có thể bị charge trùng |
| Stream live không replayable nhưng `307` đòi body cũ | Không thể tạo lại cùng dữ liệu |
| `Location` chuyển sang origin không được phép | Nguy cơ lộ body/credentials |
| `401` lặp nhiều lần dù credentials đúng | Có thể sai realm/permission/secret, không nên thử vô hạn |
| `407` từ proxy chưa được cấu hình tin cậy | Tránh đưa credential origin cho proxy |
| Body là file mutable đang được process khác ghi | Attempts có thể khác nhau về bytes |
| Client timeout khi server đã nhận một phần/đầy đủ request | Outcome nghiệp vụ chưa biết |
| Payload có signature theo timestamp mới mỗi lần | Hash/chữ ký/dedup không còn cùng ý định |

**Không lẫn `retry` và `redirect`:** redirect là hướng dẫn của server về URI tiếp theo, còn retry có thể do timeout/lỗi. Cả hai có thể gây resubscribe; nhưng quyền và semantics khác nhau. `401/407` là authentication challenge, không phải 3xx redirect.

## 12. HTTP client policy và quản lý quyền tự gửi lại

### 12.1. `NEVER`: người gọi tự quyết định redirect

Với body nhạy cảm hoặc thao tác không idempotent, cân nhắc:

```java
// Đoạn minh họa, chưa có URI/client/request đầy đủ.
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
```

Sau khi `client.send(...)` trả response 3xx, application đọc `Location`, giải quyết URI tương đối, kiểm tra target allowlist, scheme, method/status, quyền gửi body, số hops và trạng thái nghiệp vụ trước khi quyết định tạo request tiếp theo. Đừng tự copy thẳng `Authorization`/`Cookie` sang origin mới.

### 12.2. `NORMAL` không phải policy bảo mật toàn diện

`Redirect.NORMAL` chặn HTTPS→HTTP tự động theo Javadoc, nhưng **không tự biết** body nào nhạy cảm, host nào được tổ chức chấp thuận, hoặc redirect có được phép thực hiện một lệnh tài chính hay không. Không coi “NORMAL” đồng nghĩa “an toàn cho mọi POST”. `ALWAYS` còn cần cẩn trọng hơn vì không áp đặt ràng buộc chống downgrade tương tự.

### 12.3. Authenticator phải kiểm soát phạm vi

`Authenticator` nên cấp credentials **đúng origin/proxy và realm** theo policy. Java có API ngữ cảnh requestor type/host/port/scheme; demo ở trên cấp credentials giả cho bất kỳ challenge trong cùng localhost test để đơn giản, nhưng production cần chọn lọc. Không ghi secrets hoặc raw Authorization header vào logs.

### 12.4. Send bất đồng bộ không xóa vấn đề replay

`HttpClient.sendAsync(...)` trả `CompletableFuture<HttpResponse<T>>`, nhưng request body vẫn được cung cấp qua `BodyPublisher`. Nếu redirect/authentication làm client cần gửi lại, publisher vẫn phải đáp ứng subscription mới. Nếu cancel future hoặc request timeout, đừng mặc định server chưa đọc body. Kết quả I/O được thông báo bất đồng bộ không thay đổi semantics nghiệp vụ.

## 13. Debug: nhận diện lần phát lại bằng bằng chứng nào?

Log nên phân biệt **logical request** và **network attempt**:

```text
timestamp | logicalRequestId | attemptNo | currentUri | method
          | bodyFingerprint | bodyBytes | bodyPublisherSubscriptionId
          | authChallenge=401/407 | redirectStatus=3xx
          | redirectTarget | finalStatus | exceptionClass
          | idempotencyKey | businessRecordId
```

Không ghi payload nhạy cảm, mật khẩu, token hoặc toàn bộ header `Authorization`. Nếu cần fingerprint, dùng hash phù hợp với chính sách bảo mật, không coi hash là credential. Trong Java demo ta đếm **số lần supplier được gọi**, đó là tín hiệu rất cụ thể về việc client phải có source mới; nhưng trong production, mọi retry/cancel có thể làm số đếm thay đổi.

### Ma trận lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Điều cần kiểm tra |
|---|---|---|
| `307` rồi client throw `IOException` | Không replayable, supplier null, source lỗi | Supplier có tạo stream mới và bytes giống nhau không? |
| Lần sau gửi body rỗng | Tái sử dụng cùng InputStream đã consumed | Fresh stream mỗi attempt |
| Sau `401` phải login lại nhưng POST không gửi được | Publisher one-shot hoặc credentials policy không khớp | Authenticator/challenge, body source và status cuối |
| Sau `303` POST biến thành GET | Đúng redirect semantics | Đừng mong POST body ở GET |
| Sau `301/302` POST biến thành GET trên JDK | Hành vi Java HttpClient theo Javadoc | Dùng 307/308 nếu server cần giữ method và client có quyền follow |
| `307/308` nhận method giữ nguyên nhưng payload khác | Supplier đọc dữ liệu biến đổi mỗi lần | Snapshot/canonicalization/hash |
| File upload retry thất bại | File bị xóa, thiếu quyền, nội dung thay đổi | File lifetime, snapshot, reopen, cleanup |
| Upload lớn tiêu thụ nhiều RAM | Buffer toàn body vào heap để retry | Streaming từ immutable file hoặc resumable protocol |
| HTTPS redirect sang HTTP không chạy | `Redirect.NORMAL` không cho downgrade | Không nâng lên ALWAYS vô điều kiện; kiểm tra đích |
| Body gửi tới host khác ngoài dự kiến | Tự follow redirect không có allowlist | Giới hạn origin/URI, kiểm soát sensitive headers |
| Request bị thực thi hai lần | Body replayable nhưng business effect không idempotent | Stable requestId, server dedup, transaction/reconciliation |
| `401/407` lặp không dừng | Credentials không đúng, proxy/realm mismatch | Retry cap, kiểm soát Authenticator và báo lỗi |
| Không thấy supplier gọi lần hai | Redirect không follow, method đã chuyển GET, source không cần lại | Xem policy và response/method tiếp theo |

**Không bao giờ suy ra “nếu Java client đã trả IOException thì server chưa xử lý”.** Bytes có thể đã tới và tác dụng nghiệp vụ có thể đã xảy ra trước khi client quan sát lỗi.

### Trình tự điều tra

1. Ghi lại **status/headers của response trung gian**: 401 hay 407? 303 hay 307? Có Location/challenge hợp lệ không?
2. Kiểm tra client policy: `Redirect.NEVER/NORMAL/ALWAYS`, `Authenticator`, proxy selector, request timeout và số attempts.
3. Xác định **method của request tiếp theo**. Nếu chuyển GET, không cần POST body; nếu giữ POST, yêu cầu publisher phát lại bytes.
4. Instrument supplier/subscription theo cách không lộ dữ liệu. Xem lần thứ hai có tạo stream mới đọc từ đầu không.
5. Nếu body có thể tạo lại, so checksum và size hai attempts (trong môi trường kiểm thử được phép).
6. Kiểm tra URI, TLS downgrade, realm, Authorization scope và allowlist trước khi gửi body tới nơi khác.
7. Nếu thao tác có side effect, kiểm tra transaction ID/idempotency outcome ở server, không đoán từ lỗi I/O phía client.

## 14. Thiết kế một producer replayable cho body lớn

Một chiến lược thực tế cho upload file lớn là **tách vòng đời chuẩn bị dữ liệu** khỏi **vòng đời HTTP attempts**:

```text
Prepare:
  serialize đúng payload một lần
  lưu vào immutable snapshot (file tạm có quyền hạn chế)
  tính kích thước, hash, requestId
  đánh dấu snapshot READY

Attempt #1:
  mở stream mới từ snapshot, gửi
  nếu response cuối thành công -> đánh dấu DONE

Challenge/Redirect theo policy:
  kiểm tra status, credentials, URI, method và an toàn nghiệp vụ
  nếu cần phát lại:
     mở stream mới từ cùng snapshot
     gửi cùng requestId và body bytes

Finalize:
  sau khi mọi attempt/future kết thúc, đóng streams còn lại
  xóa snapshot theo chính sách cleanup
```

**Điều kiện kỹ thuật:** snapshot đủ ổn định để nhiều lần đọc; số nguồn phát lại được giới hạn; không tạo thêm side effect không mong muốn khi gọi supplier; không trả stream đã đóng; không chuyển dữ liệu nhạy cảm sang host lạ. Nếu một lần thử bị cancel giữa chừng, phải làm rõ lifecycle trước khi xóa snapshot.

**Điều kiện nghiệp vụ:** server chấp nhận cùng idempotency key trong cửa sổ thích hợp và không áp dụng hiệu ứng hai lần. Nếu server chỉ chấp nhận một lần upload/chunk có offset, thiết kế cần biết resume position thay vì gửi lại toàn bộ body.

### Tại sao không đơn giản gọi `mark/reset`?

Nhiều `InputStream` không hỗ trợ `mark/reset`, hoặc giới hạn read limit không đủ để reset sau khi body lớn đã được đọc. Hơn nữa, subscriber có thể được dùng đồng thời/đã cancel, và body gốc có thể đã thay đổi. **Fresh stream từ snapshot ổn định** rõ ràng hơn về ownership, exception và khả năng phát lại.

### Nếu nguồn chỉ đọc một lần?

Đừng giả vờ nó replayable. Khi server yêu cầu 307/308 hoặc authentication resend, lựa chọn đúng có thể là:

- Trả lỗi rõ “request body cannot be replayed” và giữ nguyên trạng thái chưa biết outcome.
- Tắt redirect tự động rồi xử lý theo contract khác.
- Đăng nhập/lấy token trước khi bắt đầu stream.
- Dùng upload resumable/chunked protocol riêng, transaction/checkpoint và xác minh trạng thái.
- Nếu được phép, snapshot trước khi gửi lần đầu và giới hạn dung lượng/lifetime.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Client POST bằng `BodyPublishers.ofInputStream(() -> existingStream)`, server trả 307. Vì sao request tiếp theo có thể hỏng?  
**Đáp án:** Lần subscribe mới sẽ nhận lại **cùng InputStream đã đọc/đã đóng**, không có bytes từ đầu. Phải cấp stream mới cùng nội dung hoặc không follow.

**Câu 2.** `BodyPublisher.contentLength()==1000` có đủ chứng minh body replayable không?  
**Đáp án:** Không. Chỉ mô tả số bytes kỳ vọng, không chứng minh nguồn còn tạo lại 1.000 bytes ở subscription sau.

**Câu 3.** Server trả 303 sau POST tạo đơn, client follow thành GET. Có đang phát lại POST body không?  
**Đáp án:** Không. Method được chuyển sang GET để lấy kết quả tại URI đích; POST ban đầu có thể đã tạo đơn.

**Câu 4.** 307 và 308 có cho phép client tự chuyển POST sang GET khi follow không?  
**Đáp án:** Không. Đây là redirect **giữ method**; nếu cần body phải tái tạo body.

**Câu 5.** Java `HttpClient` không cấu hình `followRedirects`. Có tự follow 307 không?  
**Đáp án:** Không theo policy mặc định `Redirect.NEVER` của Java 17.

**Câu 6.** Một POST body có thể phát lại 10 lần. Có chắc việc POST không tạo 10 giao dịch không?  
**Đáp án:** Không. Replayability chỉ liên quan bytes; side effect cần idempotency/business transaction protection riêng.

**Câu 7.** `ofFile(path)` được tạo trước khi file bị sửa. Có chắc lần replay giống lần đầu không?  
**Đáp án:** Không nên giả định. Cần snapshot immutable, quyền truy cập ổn định và integrity policy.

**Câu 8.** `401` từ origin và `407` từ proxy khác nhau ở đâu?  
**Đáp án:** `401/WWW-Authenticate/Authorization` liên quan origin; `407/Proxy-Authenticate/Proxy-Authorization` liên quan proxy.

**Câu 9.** `Expect: 100-continue` có làm body one-shot trở thành replayable không?  
**Đáp án:** Không. Nó có thể giúp tránh gửi body trước khi server cho phép tiếp tục, nhưng không bảo đảm body chưa được gửi ở mọi tình huống.

**Câu 10.** Redirect `Location` từ HTTPS tới HTTP, `Redirect.NORMAL` sẽ làm gì?  
**Đáp án:** Java 17 `HttpClient.Redirect.NORMAL` không tự follow HTTPS→HTTP. Không vì thế mà xem mọi redirect còn lại là an toàn.

**Câu 11.** Publisher custom từ hot `Flow.Publisher` chỉ phát sự kiện một lần, rồi HTTP client resubscribe. Có bảo đảm cùng bytes không?  
**Đáp án:** Không. Custom source phải hỗ trợ multiple subscriptions tạo cùng data, hoặc caller phải tắt resend/snapshot từ trước.

**Câu 12.** `ofInputStream` supplier trả `null` ở attempt thứ hai, nhưng server đầu đã đọc body. Có thể tạo request ID mới gửi lại từ đầu để sửa không?  
**Đáp án:** Không nên. Server đầu có thể đã xử lý side effect; phải xác minh outcome và giữ ID ổn định nếu có idempotency contract.

**Câu 13.** `301/302` với POST trong Java `HttpClient` khi tự follow thường xử lý thế nào?  
**Đáp án:** Javadoc Java 17 nêu POST được chuyển sang GET. Muốn bắt buộc giữ POST, API phía server nên dùng 307/308 và client có chính sách phù hợp.

**Câu 14.** Tại sao supplier tạo stream mới có nội dung `System.nanoTime()` chưa đáp ứng replayability đúng?  
**Đáp án:** Mỗi attempt có bytes khác. Replay đúng cần data ổn định theo logical request.

**Câu 15.** Response final 200 sau automatic 401/307 flow có nghĩa chỉ có một request HTTP được gửi?  
**Đáp án:** Không. Caller thường chỉ nhận final response; log server và counter supplier cho thấy các attempts trung gian.

**Câu 16.** 307 chuyển upload file tới host không tin cậy, nhưng publisher mở file lại rất tốt. Có nên follow?  
**Đáp án:** Không chỉ vì “làm được về kỹ thuật”. Phải kiểm tra origin, TLS, quyền gửi body và chính sách bảo mật.

## 16. Ghi nhớ và checklist

- **Body replayable** = một subscription/attempt mới có thể tạo lại **cùng bytes**; không phải idempotency hay network retransmission.
- Java `BodyPublisher` là `Flow.Publisher<ByteBuffer>`; resend tạo subscription mới, dữ liệu phải tương đương.
- `ofInputStream` **không buffer body cho bạn**; supplier phải tạo **InputStream mới** mỗi lần, nếu trả `null` ở attempt sau request có thể thất bại.
- `ofString`/`ofByteArray` thuận tiện với nội dung nhỏ ổn định; `ofFile` và custom publisher cần quản lý dữ liệu biến đổi, lifetime và multiple subscriptions.
- `401`/`407` có thể yêu cầu gửi lại body sau challenge; `Expect: 100-continue` không loại bỏ hoàn toàn nhu cầu replay.
- `307`/`308` giữ method + body, `303` thường chuyển POST thành GET, `301`/`302` cho phép chuyển POST→GET và Java HttpClient làm như vậy khi follow.
- `HttpClient.Redirect.NEVER` là mặc định; `NORMAL` không follow HTTPS→HTTP; `ALWAYS` cần thận trọng hơn về downgrade.
- Mọi automatic resend phải xét **authorization scope, redirect target, giới hạn attempts và business idempotency**.
- Nếu không thể phát lại, **báo lỗi hoặc thay protocol**, không âm thầm thay đổi method/body hoặc phát lại giao dịch mới với ID mới.
- Dùng request/body hash, logical request ID và attempt counter khi debug; không log secrets.

### Nguồn tham khảo

- [Java 17 `HttpRequest.BodyPublisher` — subscription mới khi cần resend](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html)
- [Java 17 `HttpRequest.BodyPublishers` — `ofInputStream`, `ofFile`, `ofByteArray`, `fromPublisher`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html)
- [Java 17 `HttpClient` — builder, default redirects, authenticator](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java 17 `HttpClient.Redirect` — `NEVER`, `NORMAL`, `ALWAYS`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html)
- [Java 17 `HttpRequest.Builder` — `expectContinue`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [RFC 9110 — HTTP Semantics: `401`, `407`, `15.4 Redirection](https://www.rfc-editor.org/rfc/rfc9110.html)
- [RFC 9205 — Building Protocols with HTTP: redirect semantics](https://www.rfc-editor.org/rfc/rfc9205.html)
