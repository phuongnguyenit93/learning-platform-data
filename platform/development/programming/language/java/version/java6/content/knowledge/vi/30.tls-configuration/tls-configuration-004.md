# SSLContext.getDefault và SSLContext.setDefault trong cấu hình TLS Java

## 1. Bài toán: TLS mặc định đến từ đâu và vì sao thay đổi toàn cục nguy hiểm?

Khi ứng dụng Java kết nối HTTPS/TLS, nhiều API mạng có thể dựa vào một đối tượng `javax.net.ssl.SSLContext`. Đối tượng này quản lý cấu hình và trạng thái dùng chung phục vụ các phiên TLS, gồm nguồn khóa/chứng thư, quyết định tin cậy và secure random; nó có thể tạo `SSLSocketFactory`, `SSLServerSocketFactory` hoặc `SSLEngine`.

Java SE cung cấp hai phương thức static rất dễ dùng sai:

- `SSLContext.getDefault()`: lấy **ngữ cảnh TLS mặc định hiện tại** của JVM.
- `SSLContext.setDefault(SSLContext context)`: **thay đổi ngữ cảnh mặc định** mà các lần gọi `getDefault()` sau đó sẽ trả về.

Chúng **không phải** là API "kiểm tra kết nối HTTPS" hay "bật TLS 1.3" và càng không phải cách để tắt xác minh chứng thư cho nhanh. Thay đổi default có tác động rộng ở **phạm vi tiến trình JVM** đối với code chọn sử dụng nó. Trong ứng dụng đa luồng, web server, SDK nhiều thư viện hoặc môi trường chạy test đồng thời, tác động đó dễ vượt ra ngoài thành phần gọi `setDefault`.

Mục tiêu bài này:

1. Hiểu chính xác vòng đời và kết quả của `getDefault()`/`setDefault()`.
2. Phân biệt default context đã khởi tạo với context tự tạo bằng `getInstance("TLS")` và `init(...)`.
3. Xác định **những đối tượng đã tạo trước đó không tự đổi** khi đổi global default.
4. Dùng `HttpClient.Builder.sslContext(customContext)` để cấu hình **riêng từng client** thay vì thay toàn JVM.
5. Hiểu nguồn `KeyManager`/`TrustManager`, truststore/keystore và thời điểm cấu hình có hiệu lực.
6. Không đánh đồng trust chain verification với hostname verification; tránh trust-all.
7. Kiểm thử đầy đủ bằng Java 17+ mà **không gửi request mạng** và không thay truststore thật.

> Kết luận sớm: **ưu tiên truyền SSLContext cụ thể cho từng client/server component**. `setDefault` chỉ nên được dùng khi thực sự có yêu cầu cấu hình toàn ứng dụng và đã hiểu ảnh hưởng lên tất cả người dùng default trong JVM.

## 2. Phạm vi API và các đối tượng liên quan

`SSLContext` thuộc package `javax.net.ssl` trong module `java.base`, hiện hành trên Java 17+.

| Thành phần | Nhiệm vụ | Điểm cần cẩn trọng |
| --- | --- | --- |
| `SSLContext` | Định nghĩa nguồn TLS/JSSE factory, key/trust/session state | Có default process-wide và các instance riêng |
| `SSLContext.getDefault()` | Lấy context mặc định đã sẵn sàng | Có thể kích hoạt khởi tạo lần đầu |
| `SSLContext.setDefault(...)` | Thay context mặc định cho các lần đọc tiếp | Global mutable state; không retroactive |
| `SSLContext.getInstance("TLS")` | Tạo context mới với provider hỗ trợ thuật toán `TLS` | Cần `init(...)` trước khi dùng |
| `SSLContext.init(km, tm, random)` | Cấu hình key managers, trust managers, secure random | `null` managers chọn default provider managers, không phải trust-all |
| `KeyManager` | Cung cấp identity keys/certificate chains cho local side | Quan trọng với mTLS hoặc TLS server |
| `TrustManager` | Quyết định tin cậy peer certificate chains | Không bỏ validation để "sửa" lỗi PKIX |
| `TrustManagerFactory` | Tạo trust managers từ truststore | Kiểm soát tập trusted root CAs |
| `KeyManagerFactory` | Tạo key managers từ keystore | Private key/certificate cần bảo vệ |
| `SSLSocketFactory` | Tạo TLS sockets từ một SSLContext | Factory đã giữ tham chiếu cũ không tự được đổi |
| `SSLServerSocketFactory` | Tạo TLS server sockets | Server identity và cert vẫn cần cấu hình |
| `SSLEngine` | TLS engine phi socket/blocking | Endpoint identification phải được cấu hình đúng ở low-level client |
| `SSLParameters` | Các TLS parameters như protocols, cipher suites, endpoint ID algorithm | Context không tự làm tất cả HTTP policy |
| `HttpClient.Builder.sslContext(...)` | Gắn context riêng vào Java HTTP client | Cách thường ưu tiên cho integration |
| `HttpClient.sslContext()` | Xem context mà client đã giữ | Kiểm thử việc không đổi sau `setDefault` |

### 2.1. SSLContext không phải trực tiếp một TLS connection

~~~text
                          SSLContext
                    (key / trust / random)
                             |
                +------------+-----------+
                |            |           |
                v            v           v
         SSLSocketFactory  SSLEngine  SSLServerSocketFactory
                |            |           |
                v            v           v
         TLS socket(s)   TLS engine   TLS server socket(s)
                |
                v
            TLS handshake
                |
                +-- certificate path/trust decision
                +-- server name/endpoint verification (client policy)
                +-- protocol/cipher negotiation
                +-- session establishment
~~~

`SSLContext` là **nguồn cấu hình và trạng thái**, không phải một request, một certificate hoặc một kết nối độc lập. Các sockets/engines/client objects được dựng từ context tại một thời điểm có thể giữ tham chiếu riêng, session state và cấu hình đã chọn.

### 2.2. Default và per-component contexts

~~~text
JVM process
    |
    +-- Static SSLContext.getDefault()
    |           |
    |           +-- SSLContext A (ban đầu)
    |           |
    |           +-- SSLContext B (sau setDefault(B))
    |
    +-- HttpClient client1 (đã tạo trước setDefault)
    |           |
    |           +-- Giữ SSLContext A
    |
    +-- HttpClient client2 (tạo sau setDefault)
    |           |
    |           +-- Có thể dùng SSLContext B khi không set riêng
    |
    +-- HttpClient client3 (builder.sslContext(C))
                |
                +-- Giữ SSLContext C do app chọn
~~~

Đối với `java.net.http.HttpClient` của JDK, JavaDoc xác nhận system-wide defaults được lấy **khi instance được xây dựng**; thay `SSLContext.setDefault(...)` sau đó **không ảnh hưởng tới các HttpClient đã tạo**. Những API/thư viện khác có thể có caching hoặc lifecycle riêng: không kết luận một lần gọi `setDefault` sẽ "chuyển tất cả request HTTPS đang chạy" sang context mới.

## 3. `SSLContext.getDefault()`: khởi tạo và cache

Chữ ký:

~~~java
public static SSLContext getDefault()
        throws NoSuchAlgorithmException
~~~

Đây là chữ ký API mô tả từ JavaDoc. Luồng logic được tài liệu hóa:

1. Nếu trước đó có người gọi `SSLContext.setDefault(context)` thành công, trả về **context đã đặt**.
2. Nếu chưa có context mặc định được đặt, lần đầu gọi `getDefault()` yêu cầu `SSLContext.getInstance("Default")`.
3. Nếu thành công, context ấy trở thành default và được trả về.
4. **Default context trả về đã sẵn sàng sử dụng, không cần gọi `init()`**.
5. Những lần gọi tiếp theo sẽ lấy context mặc định hiện tại, trừ khi có thành phần gọi `setDefault`.

Ví dụ đơn giản:

~~~java
SSLContext first = SSLContext.getDefault();
SSLContext second = SSLContext.getDefault();

System.out.println(first == second);
~~~

Nếu **không có thread nào thay default giữa hai lệnh**, kết quả là:

~~~text
true
~~~

Điều được minh họa là **cùng object reference** (toán tử `==`), không phải "hai SSLContexts tình cờ có cùng danh sách TLS protocols".

### 3.1. Vì sao là “Default”, không nhất thiết là “TLS”?

Theo JavaDoc, bước tự tạo default gọi `getInstance("Default")`. Đây là tên algorithm đặc thù trong danh sách `SSLContext` services, không phải mặc định bắt buộc phải hiển thị `"TLS"` khi gọi `getProtocol()`. Một context được tạo thủ công bằng `getInstance("TLS")` là **object mới** với cấu hình/manager initialization riêng; nó không tự thay default.

Nên tránh code:

~~~java
String protocol = SSLContext.getDefault().getProtocol();
if (!"TLS".equals(protocol)) {
    throw new IllegalStateException("Default context is insecure");
}
~~~

Đây là anti-pattern. Context mặc định có thể có protocol name `"Default"` theo provider, trong khi vẫn đàm phán TLS hiện hành. Hãy kiểm policy bằng **enabled protocols, cipher suites, trusted managers và handshake/identity checks**, không bằng chuỗi tên provider/algorithm đơn lẻ.

### 3.2. Ngoại lệ của `getDefault()`

`getDefault()` khai báo `NoSuchAlgorithmException` khi provider không cung cấp algorithm để tạo default context. Với Java phổ biến đã có JSSE provider phù hợp, trường hợp đó hiếm, nhưng vẫn phải xử lý checked exception khi viết code:

~~~java
try {
    SSLContext context = SSLContext.getDefault();
    // Use context.
} catch (NoSuchAlgorithmException error) {
    throw new IllegalStateException(
            "No usable default SSLContext", error);
}
~~~

Đây là snippet; `NoSuchAlgorithmException` import từ `java.security`. Đừng catch rồi quay sang "trust-all" hoặc bỏ TLS nếu default SSLContext không có sẵn.

### 3.3. Không nên thay key/trust config sau khi đã khởi tạo default rồi đòi hiệu lực ngay

Các tham số hệ thống JSSE như `javax.net.ssl.trustStore` và `javax.net.ssl.keyStore` có thể được default provider dùng **khi default context/manager được tạo**. Sau khi `getDefault()` đã làm khởi tạo, việc gọi `System.setProperty(...)` sau đó không có cam kết tái khởi tạo mọi manager/factory/session đã tồn tại.

Nếu muốn thay trust material giữa lúc chạy, hãy **tạo và init một SSLContext mới với managers thích hợp**, rồi áp riêng cho client mới (hoặc thay cấu hình toàn JVM chỉ khi có thiết kế rõ ràng). Không giả định thay một system property sẽ cập nhật TLS connections cũ.

## 4. `SSLContext.setDefault(context)`: thay đổi gì và không thay đổi gì?

Chữ ký:

~~~java
public static void setDefault(SSLContext context)
~~~

JavaDoc hiện hành quy định:

- Đặt context được đưa vào làm ngữ cảnh mặc định.
- Các lần gọi `getDefault()` **sau đó** sẽ trả về object này.
- Context truyền vào phải **đã sẵn sàng sử dụng, không cần khởi tạo tiếp**.
- `setDefault(null)` ném **`NullPointerException`**.

**Chú ý:** `setDefault` không nhận tên algorithm, không tự tạo truststore, không cung cấp certificate và không khởi tạo một `SSLContext` được tạo bằng `getInstance("TLS")`. Phải init trước:

~~~java
SSLContext custom = SSLContext.getInstance("TLS");
custom.init(null, null, new SecureRandom());
SSLContext.setDefault(custom);
~~~

Đây là snippet dùng các managers mặc định từ provider, **không phải** cấu hình mTLS hay truststore tùy biến.

### 4.1. Sau `setDefault`, ai nhìn thấy context mới?

Tùy caller:

| Đối tượng/hoạt động | Sau khi `setDefault(B)` |
| --- | --- |
| `SSLContext.getDefault()` gọi tiếp | **Trả về B** |
| `HttpClient.newBuilder().build()` tạo sau đó, không set context riêng | Dùng default context được lấy lúc xây dựng (B theo JDK example) |
| `HttpClient` tạo từ trước | **Không tự đổi** context |
| `HttpClient.Builder.sslContext(C).build()` | Dùng **C**, không lệ thuộc B |
| `SSLContext A` tham chiếu lưu từ trước | Vẫn là object A |
| `SSLSocketFactory` tạo từ A trước đó | Không tự bị biến thành factory của B |
| `SSLEngine` đã tạo từ A | Không tự khởi tạo lại TLS state với B |
| Thư viện thứ ba/SDK HTTPS | **Phụ thuộc** việc thư viện lấy default lúc nào, có cache không, có context riêng không |
| Session/connection đang hoạt động | Không tự chuyển context giữa một handshake/connection đang chạy |

**Không suy diễn rộng hơn tài liệu.** `SSLContext.getDefault()` là global lookup, nhưng không thể ra lệnh mọi HTTP client, connection pool hay proxy hiện có đổi trust manager ngay lập tức.

### 4.2. Đặt context mới không tự tạo mTLS hoặc tin chứng thư khác

Nếu code chỉ:

~~~java
SSLContext context = SSLContext.getInstance("TLS");
context.init(null, null, null);
SSLContext.setDefault(context);
~~~

Context mới chọn default key/trust manager implementations. Nó **không tự có** một private key/cert hợp lệ cho mutual TLS. Muốn custom trusted CAs hoặc client certificate, phải tạo đúng `TrustManagerFactory`/`KeyManagerFactory` từ material đáng tin rồi truyền vào `init(...)`.

### 4.3. Vì sao global default là shared mutable state?

Giả sử:

~~~text
Thread A                   Thread B
--------                   --------
getDefault() --> Context X
                           setDefault(Context Y)
connect using X
                           getDefault() --> Context Y
~~~

Trong cùng process, hai thành phần có thể sử dụng contexts khác nhau theo thời điểm xây dựng. Nếu thay default cho **một test** trong khi các test khác chạy song song, kết quả có thể khó tái hiện.

Không dùng `setDefault` trong request handler để lựa chọn truststore theo tenant; toàn bộ tenants chia sẻ cùng một default slot. Trường hợp multi-tenant nên dùng **per-tenant SSLContext, explicit client/factory và trust mapping**, không chuyển default qua lại giữa các requests.

## 5. So sánh `getDefault()`, `getInstance("TLS")` và `getInstance("Default")`

| Lệnh | Đối tượng trả về | Cần `init(...)`? | Thay default global? |
| --- | --- | --- | --- |
| `SSLContext.getDefault()` | Context default hiện hành | **Không** | Không |
| `SSLContext.getInstance("TLS")` | Context mới theo TLS algorithm | **Có** trước khi sử dụng làm factory | Không |
| `SSLContext.getInstance("Default")` | Context mới của provider hỗ trợ `Default` | Với JDK SunJSSE, context **được khởi tạo sẵn** | Không |
| `SSLContext.setDefault(custom)` | `void` | `custom` phải sẵn sàng trước | **Có** |
| `HttpClient.newBuilder().sslContext(custom).build()` | Client dùng context cụ thể | `custom` phải sẵn sàng | **Không** |

Chú ý: `getInstance("Default")` là algorithm đặc biệt mà JavaDoc `getDefault()` sử dụng lúc đầu; một provider khác có thể có hành vi/availability riêng. Không tùy tiện dựa vào `getInstance("Default")` trong logic ứng dụng cần **custom keystore/truststore** — dùng `getInstance("TLS")` + `init(...)` hoặc `getDefault()` theo nhu cầu.

### 5.1. `init(KeyManager[], TrustManager[], SecureRandom)` và các tham số null

~~~java
SSLContext custom = SSLContext.getInstance("TLS");
custom.init(null, null, new SecureRandom());
~~~

Ý nghĩa JavaDoc:

- `KeyManager[] km = null`: provider tìm factory mặc định của key managers.
- `TrustManager[] tm = null`: provider tìm factory mặc định của trust managers.
- `SecureRandom random = null`: provider dùng secure random implementation mặc định.
- `new SecureRandom()`: caller chọn object secure random hiện hành. **Không** dùng `java.util.Random` cho TLS.
- Manager arrays nếu không null: caller chịu trách nhiệm cung cấp các managers theo policy của mình.

**`null` trust managers không có nghĩa “chấp nhận mọi chứng thư”!** Đó là một trong những nhầm lẫn nguy hiểm nhất. Trust-all phải là hành vi custom `X509TrustManager` sai được cố tình viết ra, không phải hiệu ứng của `init(null, null, null)`.

### 5.2. SSLContext không phải mật khẩu, không phải certificate

`SSLContext` chứa cấu hình và state để tạo TLS endpoints, nhưng không tự định danh đối tác. Một TLS connection an toàn cần:

- Protocols/cipher suites được policy cho phép.
- Truststore/trust manager phù hợp.
- Hostname/endpoint identity được xác minh đúng.
- Client certificate/key manager khi protocol yêu cầu mTLS.
- Timeout, SNI/ALPN và HTTP client behavior phù hợp.
- Không bỏ xác minh certificate chain hoặc hostname khi gặp lỗi handshake.

## 6. Ví dụ an toàn được khuyến nghị: SSLContext riêng cho HttpClient

Java 17+ có `java.net.http.HttpClient` với builder:

~~~java
SSLContext scoped = SSLContext.getInstance("TLS");
scoped.init(null, null, new SecureRandom());

HttpClient serviceClient = HttpClient.newBuilder()
        .sslContext(scoped)
        .build();
~~~

Điểm quan trọng: **không cần gọi `SSLContext.setDefault(scoped)`**. Chỉ `serviceClient` dùng cấu hình TLS của `scoped`. Một client khác có thể dùng default hoặc context riêng khác.

### 6.1. Vì sao per-client tốt hơn per-JVM?

- Dễ tách integration A (truststore của đối tác A) khỏi integration B (truststore B).
- Tránh ảnh hưởng thư viện khác đang sử dụng default context.
- Test không tranh chấp shared global state.
- Cho phép rollout/rotation bằng cách dựng `HttpClient` mới với context mới.
- Dễ xác định client nào dùng cert/key nào, thay vì dựa vào timing `setDefault`.
- Giảm rủi ro một sửa đổi config của module khác làm request đang chạy thay trust policy ngoài dự kiến.

Một instance `HttpClient` có thể được tái sử dụng để gửi nhiều requests, tránh tạo client mới trên mỗi request mà không có lý do. Khi rotate trust material, hãy tạo context/client thay thế và xử lý lifecycle của client cũ theo JDK hỗ trợ.

### 6.2. Xem context của HttpClient

~~~java
HttpClient client = HttpClient.newBuilder()
        .sslContext(scoped)
        .build();

boolean correct = client.sslContext() == scoped;
~~~

Đây là snippet. `client.sslContext()` là phương thức quan sát context mà client đang dùng. Nó **không thực hiện handshake** hay chứng minh certificate trust/hostname validation đang hoạt động với server thực. Tính hợp lệ cần kiểm thử integration trên HTTPS endpoint được kiểm soát khi triển khai.

### 6.3. Default context khi không gọi `builder.sslContext`

JavaDoc nói nếu không gọi `HttpClient.Builder.sslContext(...)`, client mới dùng **default SSLContext**. Default system-wide values của `HttpClient` được lấy khi instance được tạo; gọi `SSLContext.setDefault` sau khi xây client **không đổi** SSLContext của client trước đó.

~~~java
HttpClient oldClient = HttpClient.newBuilder().build();
SSLContext oldContext = oldClient.sslContext();

SSLContext replacement = SSLContext.getInstance("TLS");
replacement.init(null, null, new SecureRandom());

SSLContext previous = SSLContext.getDefault();
try {
    SSLContext.setDefault(replacement);
    HttpClient newClient = HttpClient.newBuilder().build();

    System.out.println(oldClient.sslContext() == oldContext);
    System.out.println(newClient.sslContext() == replacement);
} finally {
    SSLContext.setDefault(previous);
}
~~~

Đây là **snippet minh họa trong một method `throws Exception`**; nó vẫn có global side effects trong khoảng `try` nên không nên sử dụng tại production server đang có nhiều threads. Source hoàn chỉnh ở mục 10 chạy trong JVM riêng để tránh ảnh hưởng ứng dụng khác.

## 7. TrustManager, KeyManager và nguồn cấu hình mặc định

Một số system properties của JSSE/JDK thường gặp:

| Thuộc tính | Vai trò thông thường khi dùng SunJSSE | Lưu ý |
| --- | --- | --- |
| `javax.net.ssl.trustStore` | Đường dẫn truststore để mặc định chọn trust anchors | Nếu sai path, có thể mất trust anchors; không tự fallback theo mong muốn |
| `javax.net.ssl.trustStoreType` | Định dạng truststore, ví dụ PKCS12 | Phải khớp file thật |
| `javax.net.ssl.trustStorePassword` | Password kiểm tra bảo toàn truststore khi cần | Không đưa vào log/shell history/commit |
| `javax.net.ssl.keyStore` | Keystore chứa local identity material | Không đồng nghĩa server được phép tin tất cả |
| `javax.net.ssl.keyStoreType` | Định dạng keystore | Phù hợp nội dung |
| `javax.net.ssl.keyStorePassword` | Password mở keystore khi cần | Quản lý qua secret store |
| `jdk.tls.disabledAlgorithms` | Chính sách thuật toán bị vô hiệu hóa của JDK | Không gỡ thuật toán yếu chỉ để “fix handshake” |
| `https.protocols` | Property có hiệu lực với một số HTTPS API/provider | Không giả định kiểm soát mọi HttpClient/SSLEngine |
| `javax.net.debug` | Bật JSSE debug diagnostics | Có thể tiết lộ handshake metadata; không bật rộng trên production |

**Cảnh báo:** Các properties có phạm vi khác nhau tùy API/provider/JDK. `javax.net.ssl.trustStore` là đầu vào cho cơ chế default trust managers trong SunJSSE; nó không phải lệnh “cập nhật tất cả SSLContexts”. `SSLContext.setDefault(...)` lại là thay **object default**, không phải sửa trực tiếp trustStore property.

### 7.1. Khởi tạo default chỉ xảy ra khi cần; thời điểm rất quan trọng

~~~text
JVM starts
   |
   +-- JSSE system properties / security properties configured
   |
   +-- first SSLContext.getDefault() or factory using default
   |       |
   |       +-- Provider creates initialized default SSLContext
   |       +-- Default key/trust managers selected
   |
   +-- Existing clients/factories keep their references
   |
   +-- Later System.setProperty("javax.net.ssl.trustStore", ...)
           |
           +-- Does not automatically rebuild existing contexts
~~~

Vì vậy nếu dựa trên default system properties, hãy cấu hình chúng **trước khi JSSE default được tạo** (thường từ startup/deployment), và kiểm thử bằng một JVM mới có chính xác launch settings. Các thư viện khác có thể kích hoạt default SSLContext sớm trong startup mà bạn không nhận ra.

### 7.2. Không đưa truststore password lên command line ở môi trường thật

Ví dụ **cú pháp minh họa** (không chứa password):

~~~sh
java -Djavax.net.ssl.trustStore=/secure/config/truststore.p12 \
     -Djavax.net.ssl.trustStoreType=PKCS12 \
     MyApplication
~~~

`MyApplication` là class/application do bạn cung cấp, không phải demo đầy đủ. Đường dẫn là placeholder. Khi cần password, dùng secret-management facility/deployment configuration được phê duyệt; command-line arguments có thể lộ qua process-list/logs trên một số môi trường. Không commit passwords vào repo.

### 7.3. Nếu truststore path sai thì sao?

Theo hướng dẫn SunJSSE, khi `javax.net.ssl.trustStore` được cấu hình nhưng file không tồn tại, mặc định trust manager có thể được khởi tạo với truststore trống. Hệ quả là certificate chain bình thường có thể không được tin. Không mặc định rằng JDK sẽ tự chuyển sang `cacerts` sau khi gặp truststore path sai.

Khi lỗi TLS kiểu PKIX path building failed, hãy kiểm:

1. Bạn đang dùng default context hay client-scoped context?
2. TrustStore path/type/password có chính xác không?
3. File có mặt, có đúng root/intermediate certs theo trust policy không?
4. Bạn có vô tình tạo truststore chỉ chứa custom CA và làm mất system trust roots dự kiến không?
5. Certificate chain server có đúng host/expiry/signature algorithm không?
6. JVM đã khởi tạo default context trước khi config được đặt chưa?

**Không khắc phục bằng cách chấp nhận mọi chứng thư**; đó là bỏ bảo vệ TLS, không phải sửa nguyên nhân.

## 8. Truststore riêng cho một dịch vụ: hướng hiện đại hơn setDefault

Giả sử một đối tác dùng CA nội bộ. Bạn cần cho **một** HttpClient tin CA đã được xác minh trong file PKCS12, nhưng các clients khác vẫn dùng trust policy riêng.

Đoạn sau minh họa *phần lõi* đọc truststore. Đây là **snippet triển khai**, không phải chương trình độc lập: `path` là `Path` đã được cấu hình an toàn; `storePassword` là `char[]` được cấp qua secret manager; file truststore phải tồn tại.

~~~java
KeyStore trustStore = KeyStore.getInstance("PKCS12");

try (InputStream in = Files.newInputStream(path)) {
    trustStore.load(in, storePassword);
}

TrustManagerFactory trustFactory =
        TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
trustFactory.init(trustStore);

SSLContext partnerContext = SSLContext.getInstance("TLS");
partnerContext.init(
        null,
        trustFactory.getTrustManagers(),
        new SecureRandom());

HttpClient partnerClient = HttpClient.newBuilder()
        .sslContext(partnerContext)
        .build();
~~~

Cần imports `java.security.KeyStore`, `java.security.SecureRandom`, `javax.net.ssl.TrustManagerFactory`, `javax.net.ssl.SSLContext`, `java.net.http.HttpClient`, `java.nio.file.Files`, `java.nio.file.Path`, `java.io.InputStream`.

Những lưu ý quan trọng:

- `trustFactory.init(trustStore)` chọn **trust material từ trustStore cụ thể**. Đừng mặc định nó tự hợp nhất mọi system CA roots với custom CA; nếu muốn phối hợp trust policies, hãy thiết kế rõ ràng và kiểm thử.
- `init(null, trustManagers, ...)` để **key managers** mặc định, nhưng **trust managers** được chỉ định cụ thể từ truststore của đối tác.
- Cần xác nhận certificates/trust anchors trong truststore là những thực thể ứng dụng **đã cho phép** tin, không tải CA tùy ý theo URI trong request.
- Hostname/endpoint verification vẫn phải được áp đúng; trust root đúng **không** tự chứng minh tên host khớp certificate.
- `partnerClient` dùng context scoped; **không gọi `SSLContext.setDefault(partnerContext)`**, tránh thay trust policy cho các clients khác.
- Khi rotate truststore, rebuild/reinitialize một context mới và xây client mới theo kế hoạch. Existing clients không tự cập nhật.
- Nếu password là mutable `char[]`, người sở hữu phải xóa khi không còn dùng và không in ra log, không giữ biến trong object lâu hơn cần thiết.

### 8.1. Nếu cần mTLS thì còn KeyManagerFactory

mTLS yêu cầu client có certificate/private key hợp lệ và server yêu cầu/chấp nhận client authentication. TrustManager chỉ xác minh peer; **không thay nhiệm vụ KeyManager**. Phần lõi:

~~~java
KeyStore identityStore = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(identityPath)) {
    identityStore.load(in, identityStorePassword);
}
KeyManagerFactory keyFactory =
        KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
keyFactory.init(identityStore, privateKeyPassword);

SSLContext mutualTlsContext = SSLContext.getInstance("TLS");
mutualTlsContext.init(
        keyFactory.getKeyManagers(),
        trustFactory.getTrustManagers(),
        new SecureRandom());
~~~

Đây là **snippet** minh họa cách phối hợp managers. Các biến `identityPath`, `identityStorePassword`, `privateKeyPassword` và `trustFactory` phải được ứng dụng khởi tạo từ nguồn an toàn; chưa thể chạy riêng. Sau đó truyền `mutualTlsContext` cho đúng `HttpClient.Builder.sslContext(...)`. Không gọi `setDefault` chỉ để một đối tác sử dụng mTLS.

### 8.2. PKCS12 và providers

`PKCS12` là KeyStore type hiện hành và được hỗ trợ rộng rãi. Nhưng format file cụ thể, trust material/certificate chain, key password, key alias và requirements của đối tác phải được test bằng provider/JDK triển khai thật. Không chuyển tất cả aliases thành trusted bằng một loop nạp certificate chưa xác minh từ request.

## 9. Xác minh hostname và TLS version: những thứ getDefault không tự đảm bảo

### 9.1. Xác minh certificate chain khác xác minh endpoint identity

Một TLS client cần kiểm hai điều độc lập:

1. **Certificate path trust:** chain xác minh tới trust anchor cho phép, còn hiệu lực, phù hợp key usage/algorithm policy.
2. **Endpoint identity:** tên server mà client định kết nối phải khớp identity trong certificate (thường subjectAltName của DNS/IP theo protocol).

Một `SSLContext` có `TrustManager` hợp lệ **không tự động đảm bảo** code low-level đã bật HTTPS endpoint identification. Với `HttpClient` ở mức cao, JSSE/HTTP client xử lý hostname verification theo chính sách HTTPS bình thường; không tắt nó qua internal/nonstandard flags.

Với `SSLEngine` raw cho phía client, cấu hình minh họa:

~~~java
SSLEngine engine = context.createSSLEngine(
        "example.com", 443);
engine.setUseClientMode(true);

SSLParameters params = engine.getSSLParameters();
params.setEndpointIdentificationAlgorithm("HTTPS");
engine.setSSLParameters(params);
~~~

Đây là snippet, không tạo network connection; `context` là một SSLContext đã `init`. Cần imports `SSLEngine` và `SSLParameters`. `createSSLEngine(peerHost, peerPort)` ghi nhận thông tin peer; thiết lập endpoint identification algorithm làm rõ policy kiểm identity trên handshake khi engine hoạt động. Truyền host đúng theo endpoint thực, không dùng hostname giả hoặc bỏ identity check cho “chạy được”.

### 9.2. TLS 1.3, TLS 1.2 và disabled algorithms

Không suy ra protocol version đang đàm phán từ chuỗi `SSLContext.getProtocol()`. Xem danh sách default/supported:

~~~java
SSLParameters defaults =
        context.getDefaultSSLParameters();
String[] enabledByDefault = defaults.getProtocols();

SSLParameters supported =
        context.getSupportedSSLParameters();
String[] supportedProtocols = supported.getProtocols();
~~~

Đây là snippet. **Supported** khác **enabled by default** và khác protocol thực tế được handshake với server. Java SE modern providers thường hỗ trợ TLS 1.3/1.2, nhưng security properties như `jdk.tls.disabledAlgorithms` và negotiation quyết định kết quả thực tế. Không bật SSLv3, TLSv1.0/TLSv1.1 hoặc thuật toán yếu chỉ vì đối tác legacy.

`SSLContext.getDefault()` không phải một công tắc ép protocol version toàn bộ clients; từng socket/engine/client có parameters và provider behavior riêng. Nếu protocol contract cần TLS version cụ thể, cấu hình theo supported API của client/engine và integration-test handshake.

### 9.3. Cipher suites và SNI

`SSLParameters` cho phép quản lý các thông số giao thức và cipher suites, nhưng không nên tự giới hạn vào một danh sách cứng lấy từ blog cũ. TLS 1.3 cipher handling khác những giả định của TLS cũ; thuật toán được phép còn chịu JDK security properties.

SNI/server name giúp TLS server trình bày certificate phù hợp domain, nhưng **SNI không thay hostname verification**. Ngay cả khi server trả chứng thư được trust bởi CA, client vẫn phải kiểm tên host đúng.

## 10. Chương trình Java 17+ hoàn chỉnh: default, override, HttpClient và khôi phục

### 10.1. Bài kiểm chứng thiết kế để không tác động network

File `SslDefaultContextDemo.java` chạy trong một JVM thử nghiệm riêng. Nó:

1. Lấy default context hai lần và kiểm object identity ổn định.
2. Tạo context mới bằng `SSLContext.getInstance("TLS")`, gọi `init(null, null, new SecureRandom())`.
3. Dựng một `HttpClient` mặc định **trước** khi thay global default.
4. Dựng một `HttpClient` có scoped context explicit.
5. Lưu `SSLSocketFactory` từ context cũ.
6. Gọi `SSLContext.setDefault(special)` rồi kiểm `getDefault()` trả đúng `special`.
7. Dựng `HttpClient` mới sau khi thay default và kiểm nó dùng `special`.
8. Kiểm client cũ vẫn giữ context cũ, factory cũ còn dùng được.
9. Kiểm `setDefault(null)` bị từ chối bằng `NullPointerException`.
10. Tạo `SSLEngine` không kết nối mạng và đặt HTTPS endpoint identification.
11. Xem default TLS parameters và kiểm danh sách protocols không rỗng.
12. **Luôn khôi phục** default ban đầu trong `finally`.
13. Kiểm algorithm `"Default"` tạo context có factory sẵn (được test trên JDK SunJSSE đang chạy).
14. Không tạo TLS handshake, không gửi HTTP request, không truy cập server thật.

**Giới hạn kiểm chứng:** Những assertions về identity là JSSE/HttpClient semantics, nhưng không chứng minh certificate/hostname validation thành công với server thật. Không log certificate/private key hoặc system truststore. Demo chạy trong process riêng để giảm rủi ro thay state global của ứng dụng khác.

### 10.2. Source độc lập: `SslDefaultContextDemo.java`

~~~java
import java.net.http.HttpClient;
import java.security.SecureRandom;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLEngine;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocketFactory;

public final class SslDefaultContextDemo {
    private static void check(boolean ok, String what) {
        if (!ok) {
            throw new AssertionError(what);
        }
    }

    public static void main(String[] args) throws Exception {
        SSLContext original = SSLContext.getDefault();
        check(original != null, "original context missing");
        check(SSLContext.getDefault() == original,
                "default is not stable");
        System.out.println(
                "Initial getDefault object reused: true");

        SSLContext special = SSLContext.getInstance("TLS");
        special.init(null, null, new SecureRandom());
        check(special != original, "unexpected context identity");
        System.out.println(
                "Explicit TLS context initialized: true");

        HttpClient before = HttpClient.newBuilder().build();
        check(before.sslContext() == original,
                "preexisting client context");

        HttpClient explicitlyScoped = HttpClient.newBuilder()
                .sslContext(special)
                .build();
        check(explicitlyScoped.sslContext() == special,
                "explicit client context");
        System.out.println(
                "Explicit HttpClient uses selected context: true");

        SSLSocketFactory previouslyCreatedFactory =
                original.getSocketFactory();
        check(previouslyCreatedFactory != null,
                "preexisting factory missing");

        try {
            SSLContext.setDefault(special);
            check(SSLContext.getDefault() == special,
                    "new process default mismatch");
            System.out.println(
                    "setDefault changed future getDefault: true");

            HttpClient after = HttpClient.newBuilder().build();
            check(after.sslContext() == special,
                    "new default HttpClient context mismatch");
            System.out.println(
                    "New HttpClient uses new default: true");

            check(before.sslContext() == original,
                    "old client was changed retroactively");
            System.out.println(
                    "Existing HttpClient keeps old context: true");

            check(explicitlyScoped.sslContext() == special,
                    "explicit client context changed");
            System.out.println(
                    "Explicit client independent of global lookup: true");

            check(previouslyCreatedFactory != null
                    && original.getSocketFactory() != null,
                    "old factory stopped functioning");
            System.out.println(
                    "Old context and factory remain usable: true");

            boolean nullRejected = false;
            try {
                SSLContext.setDefault(null);
            } catch (NullPointerException expected) {
                nullRejected = true;
            }
            check(nullRejected, "null should be rejected");
            System.out.println(
                    "setDefault(null) rejected: true");

            SSLEngine engine =
                    special.createSSLEngine("example.com", 443);
            engine.setUseClientMode(true);
            SSLParameters parameters = engine.getSSLParameters();
            parameters.setEndpointIdentificationAlgorithm("HTTPS");
            engine.setSSLParameters(parameters);
            check("HTTPS".equals(
                    engine.getSSLParameters()
                            .getEndpointIdentificationAlgorithm()),
                    "endpoint identification was not requested");
            System.out.println(
                    "Raw SSLEngine HTTPS identity check configured: true");

            check(special.getDefaultSSLParameters()
                            .getProtocols().length > 0,
                    "context has no enabled TLS protocols");
            System.out.println(
                    "Context provides default TLS parameters: true");
        } finally {
            SSLContext.setDefault(original);
        }

        check(SSLContext.getDefault() == original,
                "global default was not restored");
        System.out.println(
                "Original default restored in finally: true");

        SSLContext separateDefaultAlgorithm =
                SSLContext.getInstance("Default");
        check(separateDefaultAlgorithm.getSocketFactory() != null,
                "Default algorithm must be usable without init");
        System.out.println(
                "Default algorithm factory usable without init: true");

        System.out.println(
                "No TLS handshake or network request performed: true");
    }
}
~~~

### 10.3. Chạy trên Java 17+

Lưu file đúng tên `SslDefaultContextDemo.java` rồi chạy trong một terminal ở thư mục chứa file:

~~~sh
javac --release 17 SslDefaultContextDemo.java
java SslDefaultContextDemo
~~~

Không cần Maven/Gradle, truststore bổ sung hay kết nối Internet. Test được chạy thực tế với **`javac --release 17` trên JDK 24**, tạo file tạm ngoài repository và dọn sau khi kiểm thử.

**Stdout chính xác gồm 14 dòng:**

~~~text
Initial getDefault object reused: true
Explicit TLS context initialized: true
Explicit HttpClient uses selected context: true
setDefault changed future getDefault: true
New HttpClient uses new default: true
Existing HttpClient keeps old context: true
Explicit client independent of global lookup: true
Old context and factory remain usable: true
setDefault(null) rejected: true
Raw SSLEngine HTTPS identity check configured: true
Context provides default TLS parameters: true
Original default restored in finally: true
Default algorithm factory usable without init: true
No TLS handshake or network request performed: true
~~~

### 10.4. Giải thích từng kết quả

**Initial getDefault object reused: true**: hai lần gọi `getDefault()` không có `setDefault` xen giữa trả cùng object.

**Explicit TLS context initialized: true**: `getInstance("TLS")` tạo object mới và `init(null, null, SecureRandom)` đã hoàn tất; không tự thay global default.

**Explicit HttpClient uses selected context: true**: builder explicit `sslContext(special)` gắn context riêng cho client.

**setDefault changed future getDefault: true**: `setDefault(special)` làm lần `getDefault()` kế tiếp trả chính object `special`.

**New HttpClient uses new default: true**: client mới dựng mà không truyền scoped context lấy default đã được thay.

**Existing HttpClient keeps old context: true**: client dựng trước `setDefault` vẫn giữ `original`; không có retroactive rewrite.

**Explicit client independent of global lookup: true**: client dùng explicit context không cần tra cứu default ở bước kiểm tra.

**Old context and factory remain usable: true**: tham chiếu object/factory cũ chưa bị hủy vì default được thay; điều này không bảo đảm mọi connection cũ sẽ vẫn thành công với server thật.

**setDefault(null) rejected: true**: Java API yêu cầu non-null; ném `NullPointerException` khi null.

**Raw SSLEngine HTTPS identity check configured: true**: đặt `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` cho raw engine. Chưa thực hiện handshake, nên đây mới là **configuration assertion**, không phải chứng chỉ server đã được xác nhận.

**Context provides default TLS parameters: true**: object sau `init` cung cấp danh sách default protocols không rỗng; không suy ra protocol/version nào sẽ được negotiated thực tế.

**Original default restored in finally: true**: cleanup để demo tự phục hồi default trước khi kết thúc. Không biến điều này thành lý do dùng global setDefault trong môi trường nhiều threads.

**Default algorithm factory usable without init: true**: trên JDK SunJSSE đã kiểm thử, `getInstance("Default")` tạo context sẵn sàng. Thực hành portable nên ưu tiên `getDefault()` hoặc `getInstance("TLS") + init` theo yêu cầu.

**No TLS handshake or network request performed: true**: chương trình chỉ tạo objects/local clients/engine và kiểm identity/configuration, không gửi traffic.

### 10.5. Vì sao không in provider name và TLS protocol phiên bản cố định?

Provider được JDK lựa chọn theo `Security Provider` configuration. Danh sách default protocols, cipher suites và name có thể khác giữa OS, security policy và JDK. Chương trình chỉ assert những bất biến API có thể kiểm chứng; nó không gán expected stdout như `TLSv1.3` nếu chưa handshake.

Muốn chẩn đoán ở môi trường thật, có thể in `context.getProvider().getName()` và `getProtocol()` (theo permission), nhưng không đưa danh sách cipher/provider của máy phát triển thành “đầu ra bắt buộc” của mọi máy.

## 11. Kiểm thử tác động toàn cục một cách an toàn

Dù source mẫu khôi phục default trong `finally`, **đừng dùng nó làm test unit chạy song song trong cùng JVM** khi các tests khác đang xây HTTP clients. Global context có thể bị quan sát ở bất kỳ thời điểm nào:

~~~text
Test A                     Test B
------                     ------
save original A
setDefault(X)
                           new HttpClient() -> X (unintended)
restore A
                           client from Test B keeps X
~~~

Khôi phục ở cuối không đảo ngược được việc một client khác đã được dựng trong thời gian default bị thay.

### 11.1. Giải pháp kiểm thử tốt hơn

- Chạy bài thử `setDefault` trong **JVM con tách biệt**.
- Nếu cần test TLS trust khác nhau, **dựng riêng HttpClient.sslContext(scoped)`; không thay global**.
- Nếu phải dùng global test ở một JVM, bảo đảm serialization/exclusive execution và cleanup trong `finally`; đừng trông chờ test runner luôn chạy tuần tự.
- Tránh assertions về local truststore/provider mà không có test fixture được kiểm soát.
- Dùng TLS loopback test server có certificate test và truststore test để kiểm handshake thật, **không kết nối endpoint public ngẫu nhiên** để chứng minh default side effects.
- Không để test code disable certificate validation hoặc mutate truststore của máy.

### 11.2. `setDefault` có ý nghĩa gì trong ứng dụng lớn?

Một server chạy nhiều SDK có thể có:

- HTTP client đi tới payment gateway.
- HTTP client gọi identity provider.
- JDBC driver nói TLS tới database.
- Metrics/exporter hoặc messaging client dùng TLS.
- SDK có connection pools/factories riêng.

Nếu code A gọi `setDefault(contextA)` để giải quyết một lỗi truststore với gateway A, code B **có thể bắt đầu dùng contextA** khi khởi tạo đối tượng dựa trên default. Nếu contextA chỉ tin một private CA, những kết nối khác có thể thất bại; nếu contextA quá permissive, phạm vi tin cậy của thành phần khác có thể bị mở rộng nguy hiểm.

Thiết kế phù hợp hơn là **mỗi integration sở hữu TLS client/context của mình**. Chọn global context ở bootstrap chỉ khi cả process thật sự có cùng trust policy và mọi consumer đã được audit.

## 12. Khi nào có thể chấp nhận `SSLContext.setDefault`?

Có những tình huống hợp lý:

1. Một ứng dụng nhỏ, **một chủ sở hữu process**, có chính sách TLS chung rõ ràng.
2. Cấu hình tại startup **trước khi bất kỳ component nào đọc default hoặc tạo client**.
3. Cần thay default vì một integration API không cung cấp phương án injected context, và đã kiểm chứng tương tác với toàn bộ ứng dụng.
4. Chạy trong JVM test riêng để kiểm semantics của JSSE.

Ngay cả khi đó, nên:

- Tạo/khởi tạo context đầy đủ trước khi `setDefault`.
- Không dùng trust-all `X509TrustManager` và không tắt hostname verification.
- Document scope, startup ordering và provider/JDK constraints.
- Test các integrations khác trong cùng process, bao gồm điều kiện truststore thiếu hoặc CA rotate.
- Tránh gọi `setDefault` nhiều lần trong runtime theo request.
- Thiết kế rollback/restart nếu thay trust policy sai.
- Không dựa vào `setDefault` để cập nhật existing HTTP clients/sockets/pools.

**Không nên** gọi `setDefault` để "mỗi tenant dùng certificate riêng" hoặc "tạm chấp nhận chứng thư tự ký" trong request-scoped code.

## 13. HttpsURLConnection, socket factories và những cache cần lưu ý

`HttpsURLConnection` là API HTTPS trong `javax.net.ssl`. Nó có các cơ chế cấu hình `SSLSocketFactory` mặc định và trên từng connection, ví dụ:

~~~java
HttpsURLConnection connection =
        (HttpsURLConnection) url.openConnection();

connection.setSSLSocketFactory(custom.getSocketFactory());
~~~

Đây là snippet với `URL url` và `SSLContext custom` đã init; không mở kết nối mạng cho tới khi request bắt đầu. Nó áp factory cho **connection instance**, tránh đổi `SSLContext.setDefault` toàn JVM. `HttpsURLConnection.setDefaultSSLSocketFactory(...)` lại là một thay đổi default khác cho lớp HTTPS URL connection và cần xem xét cùng rủi ro global state.

Không khẳng định rằng gọi `SSLContext.setDefault` sẽ đổi ngay mọi `HttpsURLConnection` đã tạo. Một số implementation có caching/default factory riêng; hãy áp trực tiếp factory cho connection nếu cần sự nhất quán.

### 13.1. SSLSocketFactory từ context cụ thể

~~~java
SSLSocketFactory factory = custom.getSocketFactory();
~~~

`factory` là kết quả từ **một SSLContext cụ thể**. Gọi `setDefault(otherContext)` không biến `factory` thành factory mới. Để dùng trust material mới cho kết nối về sau, khởi tạo SSLContext mới và cung cấp factory mới vào nơi tiêu thụ.

### 13.2. Raw SSLSocket cần endpoint identification khi làm HTTPS

Với Java HTTP client mức cao, hostname checking là trách nhiệm do client protocol thực hiện. Nếu dùng raw `SSLSocket` và tự viết HTTP/TLS handshake, hãy yêu cầu endpoint identification algorithm phù hợp:

~~~java
try (SSLSocket socket = (SSLSocket)
        custom.getSocketFactory().createSocket(host, port)) {
    SSLParameters params = socket.getSSLParameters();
    params.setEndpointIdentificationAlgorithm("HTTPS");
    socket.setSSLParameters(params);
    socket.startHandshake();
    // Chỉ giao tiếp sau khi handshake/identity checks thành công.
}
~~~

Đây là snippet **có network I/O thực**, không thuộc chương trình kiểm thử độc lập. Các biến `host`, `port` và `custom` phải được chuẩn bị hợp lệ. Socket connect timeout, read timeout, ALPN/SNI và HTTP semantics còn cần cấu hình phù hợp. Đừng copy snippet này để kết nối tùy ý tới host nội bộ không được phép.

## 14. Thực tế với TLS server và mTLS

`SSLContext` phục vụ cả client và server TLS, nhưng `setDefault` không biến một HTTP server thuần TCP thành HTTPS. Server TLS phải dùng TLS-enabled server socket/engine hoặc server framework có TLS configuration, và phải cung cấp private key/server certificate phù hợp qua `KeyManager`.

Một phía client thường kiểm **server certificate + hostname**; phía server trong mTLS còn cần xác minh **client certificate** và cấp quyền cho identity từ certificate. Những trách nhiệm này không được hoàn thành chỉ bằng `SSLContext.getDefault()`.

### 14.1. Đừng trộn keystore với truststore

- **Keystore**: thường giữ local private keys và certificate chains để trình bày identity của chính bạn.
- **Truststore**: thường giữ trust anchors/certificates dùng xác minh đối tác.
- Client chỉ gọi HTTPS thông thường thường cần trust manager; mTLS client còn cần key manager và certificate riêng.
- TLS server thường cần key manager cho server identity, có thể cần trust manager xác minh client certificate nếu bật client auth.

Nếu Java HTTPS client báo không tin certificate, thiếu server CA trong truststore **không được sửa** bằng cách đưa server private key vào keystore hoặc tắt verify.

## 15. Không dùng trust-all TrustManager để bỏ lỗi TLS

Một anti-pattern nổi tiếng là tạo `X509TrustManager` có `checkServerTrusted(...)` luôn trả về mà không kiểm chain, rồi gọi:

~~~java
SSLContext insecure = SSLContext.getInstance("TLS");
insecure.init(null, trustAllManagers, new SecureRandom());
SSLContext.setDefault(insecure);
~~~

Đây là **đoạn minh họa sai**, `trustAllManagers` chỉ đại diện cho hành vi không an toàn và **không được định nghĩa** ở đây. Nó cho thấy hai cấp nguy hiểm: vô hiệu hóa trust checking, và mở rộng hiệu ứng tới nhiều TLS consumers thông qua global default. **Không đưa cách viết/điều kiện vô hiệu hóa validation vào production/test integration trên mạng thật.**

Nếu gặp lỗi certificate:

- Xác minh endpoint HTTPS có certificate chain đúng.
- Xem hostname có khớp SAN không.
- Kiểm truststore/type/path và CA đã được cấp quyền.
- Kiểm truststore có bị init trước khi sửa config không.
- Kiểm thời gian hệ thống và certificate validity.
- Kiểm protocols/ciphers và `jdk.tls.disabledAlgorithms`.
- Với mTLS, xem server có yêu cầu client certificate không và đúng alias/key manager chưa.
- Dùng `javax.net.debug` **chỉ trong môi trường kiểm soát**, giảm thiểu log nhạy cảm.

## 16. Security & deployment checklist

| Câu hỏi | Cách kiểm |
| --- | --- |
| Có dùng `setDefault` không? | Tìm ở bootstrap/config, không dùng theo request |
| Context đưa vào đã `init` chưa? | Khởi tạo managers/secure random trước `setDefault` |
| Ai sở hữu trust policy? | Mỗi integration có trusted CAs/partners rõ ràng |
| Có trust-all manager không? | Cấm hoặc loại khỏi production |
| Có hostname verification không? | High-level HttpClient bật chuẩn, raw JSSE cần explicit endpoint ID |
| Provider/JDK nào? | Record `getProvider`, build version, policy |
| TLS protocols/cipher suites nào? | Kiểm enabled/supported và handshake thật |
| Certificate còn hợp lệ không? | Trust chain, expiry, identity, key usage |
| Truststore có được đọc đúng lúc? | Configure before JSSE default initialization hoặc scoped init |
| Truststore wrong path? | Fail closed, không tự tin sẽ fallback |
| Global default đổi có ảnh hưởng ai? | Audit clients, SDKs, factories, pools |
| Existing clients có được cập nhật không? | Không; thay/new instances theo lifecycle |
| Có test song song không? | Dùng JVM riêng hoặc scoped SSLContext |
| Có cần mTLS không? | Cấu hình `KeyManagerFactory` cùng `TrustManagerFactory` |
| Có hardcode key password không? | Dùng secret management, không log |
| CA rotation/rollout xử lý thế nào? | Build new context/client, kiểm rolling cutover |
| Kết nối đang hoạt động thế nào khi đổi default? | Không kỳ vọng handshake/tls state đổi giữa chừng |
| Có sử dụng self-signed certificate không? | Chỉ tin qua explicit approved trust anchor/pinning policy |
| Có kiểm HTTPS qua integration test không? | Server test kiểm soát và valid test cert, không dùng network public ngẫu nhiên |

## 17. Test matrix: những tình huống cần kiểm chứng

| Test case | Tác động | Expected |
| --- | --- | --- |
| First `getDefault` | JVM chưa set default | Trả context sẵn sàng hoặc ném NoSuchAlgorithmException nếu không có provider |
| Repeated `getDefault` | Không ai `setDefault` ở giữa | Trả cùng object |
| `getInstance("TLS")` + `init` | Tạo context mới | Factory sẵn sàng, default chưa đổi |
| `setDefault(custom)` | Custom đã init | `getDefault() == custom` |
| `setDefault(null)` | Truyền null | Ném NullPointerException |
| New default HttpClient | Build sau `setDefault` | Dùng context hiện là default |
| Existing HttpClient | Build trước `setDefault` | Không retroactively đổi context |
| Scoped HttpClient | `builder.sslContext(custom)` | Giữ explicit context |
| Old socket factory | Tạo từ context cũ | Tham chiếu vẫn gắn context cũ |
| Restore in finally | `setDefault(original)` | Lần getDefault kế tiếp trả original |
| Raw SSLEngine endpoint ID | `setEndpointIdentificationAlgorithm("HTTPS")` | Config được lưu, chưa handshake |
| Default algorithm implementation | SunJSSE `getInstance("Default")` | Context có factory sẵn |
| Truststore absent | `javax.net.ssl.trustStore` sai path | Không lặng lẽ trust-all; handshake phù hợp phải fail |
| Truststore changed after bootstrap | Existing context đã khởi tạo | Không tự reload |
| New custom truststore | Scoped TrustManagerFactory | Chỉ client dùng context đó thay đổi trust policy |
| Custom CA only | TrustManagerFactory init custom store | Không mặc nhiên gộp system CAs |
| Certificate wrong hostname | Có trust chain nhưng SAN khác | HTTPS endpoint verification rejects |
| Expired certificate | Chain không còn hợp lệ | Trust check rejects |
| mTLS missing client key | Server yêu cầu certificate | Handshake có thể fail |
| TLS version blocked | Legacy protocol bị disabled | Không tự bật lại protocol yếu |
| Global mutation in parallel tests | Một test setDefault trong khi test khác build client | Có nguy cơ quan sát context sai |
| JDK/provider upgrade | Thay Java runtime | Regression TLS/identity/security config |
| No network in unit demo | Chạy source ở mục 10 | 14 assertions pass, không gửi request |
| Permission/trust config errors | JSSE factory/context init failure | Fail closed, không fallback insecure |

**Không biến trường hợp “setDefault xong kết nối tới một website thành công” thành test duy nhất**. Một kết nối thành công có thể đang dùng factory/client cache từ trước, hoặc đang hoạt động nhờ trust policy quá rộng. Cần test cả identity/trust failure cases.

## 18. Các lỗi hiểu nhầm phổ biến

### 18.1. “setDefault thay mọi HTTPS request ngay lập tức”

Sai. `HttpClient` đã build giữ các defaults được áp lúc tạo. Connection pool, raw sockets/engines và third-party clients cũng có lifecycle riêng.

### 18.2. “getDefault trả một context chưa init; phải init thêm”

Sai. JavaDoc xác định default context được trả đã sẵn sàng sử dụng. Với một context **tự tạo** bằng `getInstance("TLS")`, bạn mới gọi `init(...)`.

### 18.3. “getInstance("TLS") tự trở thành default”

Sai. Nó tạo object riêng; default chỉ bị thay nếu gọi `setDefault(...)`.

### 18.4. “init(null, null, null) nghĩa là bỏ kiểm certificate”

Sai. `null` trust managers là chỉ định provider tìm default factory/trust managers, không phải trust-all.

### 18.5. “setDefault(null) có nghĩa reset về default cũ”

Sai. `setDefault(null)` ném `NullPointerException`. Muốn khôi phục trong test, phải **lưu object gốc rồi setDefault(original)**.

### 18.6. “Đổi javax.net.ssl.trustStore là đủ để các clients cũ reload”

Sai. SSLContext và HTTP clients có lifecycle/config riêng. Rebuild context/client hoặc restart với startup properties đúng.

### 18.7. “Chọn truststore custom sẽ tự cộng thêm mọi CA của cacerts”

Không được giả định. `TrustManagerFactory.init(customKeyStore)` sử dụng trust material theo factory/store của bạn. Muốn chính sách kết hợp, hãy triển khai một thiết kế explicit, kiểm thử và review bảo mật.

### 18.8. “Một certificate có chain hợp lệ thì không cần check hostname”

Sai. Chain trust không tự kiểm tra server name. Raw `SSLSocket/SSLEngine` cần endpoint verification policy thích hợp cho HTTPS.

### 18.9. “getProtocol() == TLS chứng minh TLS 1.3”

Sai. Đó là algorithm name của context, không phải negotiated protocol. Xem TLS session sau handshake hoặc kiểm outcome bằng integration test.

### 18.10. “setDefault là cách chọn client certificate cho mỗi tenant”

Sai. Shared mutable default không an toàn khi nhiều tenants/threads. Dùng scoped context với `KeyManagerFactory` và `HttpClient.Builder.sslContext` theo từng integration.

### 18.11. “setDefault đồng nghĩa tự bật HTTPS server”

Sai. TLS server cần socket/engine/framework hỗ trợ TLS, server identity keys/certificate và protocol config; không chỉ có default context.

### 18.12. “HttpClient.sslContext()==ctx chứng minh HTTPS an toàn”

Chưa đủ. Nó chứng minh client dùng đúng object; vẫn phải kiểm certificate chain/hostname/protocol/cipher/timeout bằng integration tests.

### 18.13. “Có thể setDefault trong unit test rồi restore mà không ảnh hưởng tests khác”

Không chắc. Một thread khác có thể tạo client khi default tạm thời đã thay và giữ context đó sau khi bạn restore. Dùng JVM con hoặc scoped builder.

### 18.14. “HttpsURLConnection chắc chắn cập nhật mọi factory khi setDefault”

Không thể giả định. HttpsURLConnection có default socket factory/instance factory configuration riêng, implementation có thể cache; truyền explicit `connection.setSSLSocketFactory(custom.getSocketFactory())` khi cần.

## 19. Hướng dẫn chẩn đoán lỗi mà không bỏ bảo mật

### 19.1. Lỗi `PKIX path building failed`

Hãy kiểm truststore/CA/certificate chain, không tạo trust-all manager. Một server certificate đúng có thể thiếu intermediate CA; hoặc client đang dùng `SSLContext` cũ được tạo trước khi truststore được thay.

### 19.2. Lỗi hostname mismatch

Giữ hostname verification; cập nhật server certificate SAN hoặc URI host đúng. Không tắt `EndpointIdentificationAlgorithm` để né lỗi.

### 19.3. TLS handshake protocol failure

Kiểm provider/JDK security algorithms, enabled protocols, cipher suites, SNI/ALPN và server support. Không chủ động bật SSLv3/TLSv1.0/TLSv1.1.

### 19.4. Cùng app nhưng hai service trust khác nhau

Đọc `HttpClient.sslContext()` của mỗi client và cấu hình builder. Một client dựng trước `setDefault` có thể giữ context cũ; đó là hành vi expected. Để có deterministic TLS settings, dùng explicit client-scoped contexts thay vì phụ thuộc global order.

### 19.5. Giá trị `javax.net.ssl.trustStore` có vẻ đúng nhưng kết nối vẫn lỗi

Kiểm nó được đặt trước khi default được khởi tạo chưa. Đừng nghĩ gọi `System.setProperty(...)` sau khi app đã mở nhiều connections sẽ tự reload trust managers.

### 19.6. Debug TLS

SunJSSE cung cấp `javax.net.debug` để quan sát handshake/trust decisions. Chỉ bật khi đang chẩn đoán ở môi trường được kiểm soát; debug logs có thể chứa certificate details, peer names và metadata nhạy cảm. Bảo vệ log retention/access và tắt flag sau khi kiểm.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** `SSLContext.getDefault()` trả object gì khi JVM chưa có custom default?

**Trả lời:** Nó khởi tạo/lấy một context theo algorithm `"Default"` từ provider được chọn và lưu làm default; object được trả đã sẵn sàng sử dụng.

**Câu 2.** `SSLContext.setDefault(newContext)` có thay các `HttpClient` đã tạo trước không?

**Trả lời:** Không. HttpClient lấy default lúc build; existing instances giữ context đã có.

**Câu 3.** `getInstance("TLS")` có tự `init` không?

**Trả lời:** Không nên giả định; thông thường tạo context mới rồi gọi `init(KeyManager[], TrustManager[], SecureRandom)` trước khi dùng.

**Câu 4.** `init(null, null, null)` có tắt xác minh certificate chain không?

**Trả lời:** Không. Provider chọn default managers và secure random, không tương đương trust-all.

**Câu 5.** `setDefault(null)` có reset không?

**Trả lời:** Không. Ném `NullPointerException`. Muốn restore thì lưu old context rồi gọi `setDefault(old)`.

**Câu 6.** Tại sao dùng `HttpClient.Builder.sslContext(custom)` tốt hơn trong tích hợp nhiều đối tác?

**Trả lời:** Nó giới hạn trust/key policy cho đúng client, tránh thay default toàn JVM và tránh race giữa các threads/tenants.

**Câu 7.** Khác biệt giữa KeyManager và TrustManager?

**Trả lời:** KeyManager chọn local identity keys/certificates; TrustManager quyết định tin peer. mTLS thường cần cấu hình cả hai theo từng phía.

**Câu 8.** Đặt `javax.net.ssl.trustStore` sau khi gọi `getDefault()` có tự cập nhật không?

**Trả lời:** Không bảo đảm. Default context/managers có thể đã được khởi tạo; tạo scoped context mới hoặc restart với cấu hình trước startup.

**Câu 9.** `SSLContext.getProtocol()=="Default"` có đồng nghĩa SSLv3 không?

**Trả lời:** Không. `"Default"` là tên algorithm/provider, không phải negotiated TLS version.

**Câu 10.** SSLContext có tự kiểm hostname server không?

**Trả lời:** Không tự thay cho endpoint policy của API caller. Dùng HttpClient HTTPS bình thường hoặc cấu hình endpoint identification khi dùng raw SSLEngine/SSLSocket.

**Câu 11.** Lấy `HttpClient.sslContext()` để làm gì?

**Trả lời:** Để quan sát context instance mà client đang giữ; không phải handshake/security proof.

**Câu 12.** Một client dùng custom truststore có tự tin tất cả public CAs không?

**Trả lời:** Không được giả định. TrustManagerFactory init trên store chỉ định dùng tập trust anchors theo store/provider.

**Câu 13.** Vì sao không dùng `setDefault` cho request-scoped lựa chọn CA?

**Trả lời:** Vì nó là state toàn JVM; nhiều requests/SDKs có thể vô tình dùng trust policy của nhau.

**Câu 14.** Khi nào default SSLContext được tính từ JSSE startup properties?

**Trả lời:** Khi provider tạo/khởi tạo default context/managers theo cơ chế của nó, thường tại lần first use. Không coi property update là hot reload.

**Câu 15.** Có thể dùng `SSLContext.setDefault` để bật mTLS tự động?

**Trả lời:** Không. mTLS còn yêu cầu client/server certificate/private key, KeyManager, TrustManager, policy yêu cầu cert và handshake phù hợp.

**Câu 16.** Nếu có lỗi certificate, có nên tắt trust validation cho test không?

**Trả lời:** Không. Dùng test CA/truststore được cấu hình đúng và tích hợp test server kiểm soát được.

**Câu 17.** Sao một client mới sau setDefault có thể dùng context B trong khi client cũ vẫn dùng A?

**Trả lời:** Vì client lấy giá trị default tại thời điểm build và lưu tham chiếu object, không tra cứu lại global default cho từng request.

**Câu 18.** Nếu dùng raw SSLEngine cho HTTPS, cài identity check thế nào?

**Trả lời:** Cấu hình `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` cùng peer host đúng trước handshake, bên cạnh trust manager kiểm chain.

**Câu 19.** Vì sao demo không gửi HTTPS request?

**Trả lời:** Nó kiểm JSSE default identity/configuration semantics độc lập với mạng, cert và provider của server thật; handshake/identity correctness cần integration tests riêng.

**Câu 20.** Một nguyên tắc thiết kế quan trọng nhất?

**Trả lời:** **Scoped, initialized, trusted SSLContext cho đúng component**; không dùng mutable global default để thay đổi quyền tin cậy theo từng request.

**Ghi nhớ:** `SSLContext.getDefault()` trả context JSSE mặc định **đã được khởi tạo**; `SSLContext.setDefault(context)` thay object được trả về trong các lần lookup sau, **không thay đổi hồi tố** các clients/sockets/factories đã tạo. `SSLContext.getInstance("TLS")` tạo context mới, cần `init(...)`; `null` managers chọn mặc định chứ không phải trust-all. Trong ứng dụng có nhiều HTTP/TLS integrations, hãy dùng `HttpClient.newBuilder().sslContext(custom)`, trusted keystore/truststore và hostname verification, thay vì tác động toàn JVM. Test global default trong JVM riêng; restore trong `finally` chỉ là cleanup, không loại hết race của code đa luồng.

### Tài liệu chính thức và hiện hành

- [Oracle Java SE 26 — SSLContext](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLContext.html): `getDefault`, `setDefault`, `getInstance`, `init`, protocol/provider và TLS factories.
- [Oracle Java SE 26 — HttpClient](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html): mặc định được lấy khi client được tạo; `sslContext()`.
- [Oracle Java SE 26 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `sslContext(SSLContext)` cho từng client.
- [Oracle Java SE 26 — SSLParameters](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLParameters.html): endpoint identification algorithm, protocols và cipher suites.
- [Oracle Java SE 26 — SSLEngine](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLEngine.html): TLS engine và peer-host configuration.
- [Oracle Java SE 26 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): tạo trust managers cho truststore đã chọn.
- [Oracle Java SE 26 — KeyManagerFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html): local key managers/mTLS.
- [Oracle Java SE 26 — HttpsURLConnection](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html): per-connection/default socket factories và hostname verifier.
- [Oracle Java SE 26 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/26/security/java-secure-socket-extension-jsse-reference-guide.html): default key/trust stores, JSSE providers, TLS settings.
- [Oracle Java SE 17 — SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): API tương thích Java 17.
