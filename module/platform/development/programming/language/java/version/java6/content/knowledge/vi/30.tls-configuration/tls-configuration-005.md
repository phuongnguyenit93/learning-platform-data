# Tác động toàn tiến trình khi đổi SSLContext mặc định trong Java

## 1. Vấn đề cốt lõi: một thay đổi TLS có thể lan tới nhiều thành phần

Trong Java, `javax.net.ssl.SSLContext` giữ cấu hình một cơ chế TLS/SSL: nơi lấy khóa và chứng thư của phía mình, cách kiểm tra chứng thư của bên kia, nguồn số ngẫu nhiên bảo mật và khả năng tạo TLS socket/engine. Ngoài các `SSLContext` được tạo riêng, Java có một **SSLContext mặc định của toàn JVM** thông qua:

```java
SSLContext.getDefault();
SSLContext.setDefault(sslContext);
```

Khi ứng dụng gọi `SSLContext.setDefault(...)`, nó **thay đổi một điểm cấu hình dùng chung trong tiến trình Java**. Điều này có thể gây tác động không mong muốn nếu một thư viện, HTTP client hoặc thành phần khác tạo đối tượng TLS **sau** thời điểm thay đổi và lấy mặc định mới.

Tuy nhiên, phải hiểu chính xác:

> **`SSLContext.setDefault` không phải lệnh “đổi TLS của mọi kết nối hiện tại”.** Nó thay đối tượng mà các lần `SSLContext.getDefault()` tiếp theo nhận được. Những thư viện và client dùng mặc định ở thời điểm khởi tạo có thể lấy bản mới; những client đã tạo, TLS sessions đang chạy và các thành phần dùng `SSLContext`/`SSLSocketFactory` riêng không tự động chuyển sang bản mới.

Đó là bài toán của đề **“Tác động toàn tiến trình khi đổi SSLContext mặc định”**, thuộc chủ đề **Cấu hình TLS**.

Sau bài, bạn có thể:

1. Giải thích khác biệt giữa `SSLContext.getInstance("TLS")`, `init(...)`, `getDefault()` và `setDefault(...)`.
2. Hiểu tại sao thay đổi mặc định có phạm vi **JVM-wide**, không giới hạn một request hay một HTTP client.
3. Phân biệt các đối tượng được tạo **trước/sau** khi đổi default.
4. Hiểu hành vi của `java.net.http.HttpClient`: mặc định được lấy **khi xây client**; client cũ không bị cập nhật.
5. Phân biệt default `SSLContext` với default **`HttpsURLConnection` socket factory**, là một global setting **riêng**.
6. Chọn `HttpClient.Builder.sslContext(...)` hoặc `HttpsURLConnection.setSSLSocketFactory(...)` khi chỉ muốn ảnh hưởng một client/connection.
7. Biết vai trò `KeyManagerFactory`, `TrustManagerFactory` và `KeyStore`.
8. Không nhầm truststore tùy biến với việc tắt xác minh chứng thư hoặc hostname.
9. Nhận diện nguy cơ trust leakage, tenant isolation, races và TLS connection reuse.
10. Có chiến lược triển khai, kiểm thử, rollback, vận hành mà không cần sửa cấu hình toàn JVM khi không thật cần.
11. Chạy một ví dụ **TLS thật trên localhost**, chứng minh các trường hợp bằng **40 assertions PASS** trên OpenJDK 24, source Java 17+.

**Tính hiện hành:** Bài dựa trên Java SE 26 API/Javadoc và Oracle JSSE Security Developer's Guide hiện hành. Chương trình thực hành biên dịch với `javac --release 17` trên OpenJDK 24, dùng TLS thật và truststore riêng, không tắt xác minh certificate/hostname, không kết nối mạng ngoài.

## 2. SSLContext và các đối tượng liên quan

### 2.1. Vai trò của `SSLContext`

`SSLContext` là factory/configuration context của một implementation TLS. Ví dụ:

```java
SSLContext context = SSLContext.getInstance("TLS");
context.init(keyManagers, trustManagers, secureRandom);
```

Đây là **snippet** (cần các biến `keyManagers`, `trustManagers`, `secureRandom` và xử lý checked exceptions), không phải file độc lập. Sau khi khởi tạo, ứng dụng có thể tạo:

- `SSLSocketFactory` thông qua `context.getSocketFactory()`.
- `SSLServerSocketFactory` thông qua `context.getServerSocketFactory()`.
- `SSLEngine` thông qua `context.createSSLEngine(...)`.
- `SSLSessionContext` cho client/server sessions.
- `SSLParameters` mặc định/hỗ trợ của context.

Một `SSLContext` không tự tạo kết nối ngay lúc khởi tạo. Một lần handshake TLS thực sự xảy ra khi socket/client/server được kết nối hoặc sử dụng, tùy API.

### 2.2. KeyManager và TrustManager khác nhau

| Thành phần | Chức năng | Ví dụ |
| --- | --- | --- |
| `KeyManager` | Chọn private key/chứng thư **để phía mình trình bày** | HTTPS server phải đưa chứng thư và private key của server |
| `TrustManager` | Quyết định **có tin chứng thư peer hay không** | HTTPS client kiểm tra chain của server |
| `KeyManagerFactory` | Tạo key managers từ nguồn khóa | PKCS12 chứa private key của server |
| `TrustManagerFactory` | Tạo trust managers từ nguồn trust | PKCS12 truststore chứa certificate đã phê duyệt |
| `KeyStore` | Abstraction lưu khóa/chứng thư | PKCS12 hoặc provider-backed keystore |
| `SecureRandom` | Nguồn số ngẫu nhiên bảo mật | Dùng khi gọi `SSLContext.init(...)` |

Với HTTPS client xác thực server theo TLS thông thường, **TrustManager** đặc biệt quan trọng. Một client có thể không có key managers nếu không tham gia mutual TLS. Với HTTPS server, KeyManager phải có khả năng trình bày certificate và private key phù hợp.

**Không nhầm “thêm trusted certificate” với “chấp nhận mọi certificate”.** Truststore chứa certificate/CA được kiểm soát là khác hoàn toàn việc triển khai một `X509TrustManager` có `checkServerTrusted` rỗng; cách thứ hai là lỗ hổng bảo mật nghiêm trọng.

### 2.3. `SSLContext.getInstance("TLS")` không tự thay default

```java
SSLContext isolated = SSLContext.getInstance("TLS");
isolated.init(null, configuredTrustManagers, new SecureRandom());
```

Đây là một context **riêng**. Chỉ tạo/khởi tạo nó **không thay đổi** `SSLContext.getDefault()`. Nó cũng không buộc `HttpClient` hoặc `HttpsURLConnection` khác dùng context này cho đến khi được cấu hình tường minh hoặc bạn cố tình thay default.

Điểm quan trọng: `getInstance("TLS")` và `getDefault()` là hai hoạt động khác nhau. Cái đầu tạo một context mới của provider đã chọn; cái sau trả reference tới default context dùng chung trong JVM.

### 2.4. Vì sao dùng tên giao thức `"TLS"`?

`SSLContext.getInstance("TLS")` chọn implementation của nhóm giao thức TLS theo cấu hình provider và security policy. Trên Java SE 26, những protocol names chuẩn liên quan như `TLSv1.2` và `TLSv1.3` vẫn tồn tại. Không tự suy rằng tạo context với `"TLS"` đảm bảo kết nối sẽ luôn negotiate đúng một phiên bản TLS cụ thể; protocol enabled set, client/server support, security properties và cipher suites đều ảnh hưởng.

Không dùng cấu hình nhằm bật lại SSLv3/TLS 1.0/1.1 như lựa chọn mới. Khi cần khóa phiên bản giao thức trong production, cấu hình `SSLParameters`/provider policy tương ứng và có test TLS handshake trên đúng JDK.

## 3. Quy tắc của `getDefault()` và `setDefault()`

### 3.1. `getDefault` khi chưa từng có setDefault

Java SE 26 Javadoc quy định:

- Nếu `SSLContext.setDefault(context)` đã được gọi, `getDefault()` trả **context đó**.
- Nếu chưa có default được set tường minh, lần `getDefault()` đầu tiên sẽ gọi `SSLContext.getInstance("Default")`.
- Nếu thành công, object đó được lưu làm default và được trả lại.
- Default SSLContext ban đầu **đã sử dụng được**, không cần gọi `init(...)` thêm.

Hãy nghĩ default context như một **đối tượng được khởi tạo/lưu lại**, không phải một hàm luôn đọc lại truststore từ filesystem trong mọi request.

### 3.2. `setDefault` thay reference dùng chung

```java
SSLContext before = SSLContext.getDefault();
SSLContext approved = createConfiguredContext();

SSLContext.setDefault(approved);
boolean changed = SSLContext.getDefault() == approved;
```

Đây là **snippet**, `createConfiguredContext()` là method do application định nghĩa để tạo context đã init. `changed` sẽ là `true` nếu không có thread khác thay default giữa các lệnh.

Theo Javadoc:
- `setDefault` **không chấp nhận null**; `SSLContext.setDefault(null)` ném `NullPointerException`.
- Đối tượng truyền vào **phải sẵn sàng sử dụng** (đã khởi tạo nếu provider yêu cầu).
- Nó sẽ được các lần `getDefault` sau đó trả về.
- API không “reset về cấu hình JDK ban đầu” bằng cách truyền `null`.
- Việc đổi đối tượng mặc định không chứng minh rằng các đối tượng đã được xây dựng từ default cũ được cập nhật.

Trong ví dụ hoàn chỉnh, phép kiểm tra gọi `SSLContext.setDefault(null)` được xác nhận ném `NullPointerException`, không làm thay đổi context hợp lệ đang dùng.

### 3.3. “Toàn tiến trình” nghĩa là gì?

`SSLContext.setDefault` là **trạng thái static của Java runtime trong cùng JVM**. Nhiều threads hoặc modules bên trong tiến trình có thể đọc cùng default context thông qua `SSLContext.getDefault()`.

Nó **không**:
- Thay cấu hình TLS của một tiến trình Java **khác**.
- Thay truststore của OS hoặc browser bên ngoài JVM.
- Tự ghi lại file `cacerts` hay `jssecacerts`.
- Cấu hình lại tất cả sockets TLS đã tạo.
- Buộc các HTTP client có context riêng đổi theo.
- Cập nhật mọi class-level cache của mọi thư viện.

Nếu một server chạy nhiều tenants chung JVM, phạm vi toàn tiến trình có thể **vượt xa phạm vi tenant/request** mà bạn định thay. Đây là rủi ro quan trọng nhất khi không kiểm soát các thư viện xung quanh.

## 4. Ai chịu ảnh hưởng, ai không?

| Thành phần/đường đi | Ảnh hưởng khi gọi `SSLContext.setDefault` | Giới hạn/điều kiện |
| --- | --- | --- |
| `SSLContext.getDefault()` gọi **sau** | **Có, nhận object mới** | Trừ khi thread khác lại đổi default |
| Thread khác gọi `SSLContext.getDefault()` sau | **Có, cùng JVM** | Không coi đó là cơ chế đồng bộ lifecycle cho client |
| `HttpClient` mới, không set `sslContext` tường minh | **Có, mặc định mới lúc xây client** | Java SE 26 Javadoc ghi nhận defaults tại construction |
| `HttpClient` **đã build** trước khi đổi | **Không tự thay** | Object client immutable, có thể giữ connection pool |
| `HttpClient` dùng `Builder.sslContext(context)` | **Không tự thay** | Dùng object tường minh |
| `HttpsURLConnection` mới | **Không thể suy trực tiếp chỉ từ SSLContext.setDefault** | Có default SSLSocketFactory **static riêng** được thừa kế khi tạo connection |
| `HttpsURLConnection` đã tạo | **Không tự đổi factory đã thừa kế** | Có thể set per-instance trước connect |
| `SSLSocketFactory` đã được lấy và giữ reference | **Không tự thành factory của context mới** | Factory cũ vẫn hoạt động theo lifecycle riêng |
| `SSLSocket`/`SSLEngine` đã tạo | **Không tự được tái cấu hình** | Cần quản lý lifecycle/session rõ |
| `HttpsServer` dùng `HttpsConfigurator(explicitContext)` | **Không tự thay context riêng** | Server sử dụng context đã cung cấp |
| Third-party HTTP/framework client | **Phụ thuộc cách thư viện lấy/cached TLS defaults** | Đọc docs và test đúng version |

Chìa khóa để dự đoán là trả lời:

> **Consumer lấy giá trị mặc định lúc nào, có cache/copy không và có nhận context riêng không?**

Không được dùng câu “mọi HTTPS request sau khi setDefault đều dùng context mới” như một quy tắc chung. Đây là một dự đoán quá rộng và sai với nhiều API.

## 5. `java.net.http.HttpClient`: snapshot tại thời điểm xây client

### 5.1. Default client

```java
HttpClient first = HttpClient.newHttpClient();
// ...
SSLContext.setDefault(newDefaultContext);
HttpClient second = HttpClient.newHttpClient();
```

Theo Java SE 26 `HttpClient` Javadoc, các system-wide defaults được lấy khi **`HttpClient` được tạo**. Thay đổi `SSLContext.setDefault` **sau** khi `first` đã được build không ảnh hưởng `first`.

Nói ngắn gọn:
- `first.sslContext()` vẫn trả context đã chọn lúc tạo `first`.
- `second.sslContext()` có thể trả default mới tại thời điểm tạo `second`.
- `first` có thể tiếp tục sử dụng các TLS sessions/connections trước đó.
- Tạo một builder mới không phải “làm mới” một client đã có; phải build một **HttpClient mới**.

### 5.2. Explicit context là lựa chọn ổn định hơn

```java
SSLContext partnerTls = createPartnerTlsContext();

HttpClient client = HttpClient.newBuilder()
        .sslContext(partnerTls)
        .connectTimeout(Duration.ofSeconds(5))
        .build();
```

Đây là **snippet**, cần method `createPartnerTlsContext()` do ứng dụng triển khai và imports `java.net.http.HttpClient`, `javax.net.ssl.SSLContext`, `java.time.Duration`.

Khi dùng `Builder.sslContext(partnerTls)`:
- Client này dùng cấu hình TLS do ứng dụng cung cấp.
- Không cần gọi `SSLContext.setDefault`.
- Không vô ý làm client của thư viện khác dùng truststore riêng của đối tác.
- Có thể tạo nhiều clients với trust policies khác nhau.

`HttpClient.sslContext()` cho phép xem reference context của client. Ví dụ thực hành so sánh identity bằng toán tử `==` để chứng minh liệu client cũ có nhận context mới hay không.

### 5.3. Connection reuse làm hiệu ứng thay đổi phức tạp hơn

Một `HttpClient` thường quản lý connection pool. Nếu connection HTTPS còn mở, nó có thể được tái sử dụng mà **không bắt đầu một TLS handshake mới**.

Vì vậy:
- Thay global SSLContext không phá connection đã xác thực.
- Cập nhật truststore/certificate pin không tự làm TLS session cũ mất hiệu lực ngay.
- Client đã build vẫn giữ context cũ theo contract.
- Nếu cần thay chính sách bảo mật, cân nhắc **client lifecycle mới**, drain/close old clients khi API/runtime hỗ trợ và kiểm soát sessions đang mở.

Trên **JDK 21+**, `HttpClient` hỗ trợ các phương thức quản lý lifecycle như `close()`/`shutdown()`. **Java 17 không có cùng API lifecycle mới này**, nên chương trình ví dụ target 17 **không** gọi `HttpClient.close()`. Khi mô tả migration giữa các JDK cần ghi rõ version thay vì dùng API mới trong source `--release 17`.

### 5.4. Nhiều clients, nhiều truststore

```text
One JVM
|
+-- HttpClient A -- SSLContext(trust partner A only)
|
+-- HttpClient B -- SSLContext(trust partner B only)
|
+-- HttpClient C -- SSLContext(JDK default)
|
+-- Global SSLContext.setDefault(...)   <-- shared setting
```

Một ứng dụng đa đối tác nên ưu tiên per-client contexts, thay vì `setDefault` khi chuyển giữa tenants. Nếu đổi global theo tenant A trong lúc tenant B đang tạo client, B có thể nhận nhầm trust policy của A. Không có cách bảo đảm an toàn chỉ bằng cách “set rồi revert trong finally” khi requests khác đang chạy đồng thời.

## 6. `HttpsURLConnection`: default SSLSocketFactory là cấu hình global riêng

`javax.net.ssl.HttpsURLConnection` vẫn là API hợp lệ trên Java SE 26. Nó có thể lấy `SSLSocketFactory` và `HostnameVerifier` từ **giá trị static mặc định riêng của class**.

### 6.1. Các method phân biệt rõ ràng

| API | Phạm vi | Vai trò |
| --- | --- | --- |
| `SSLContext.setDefault(ctx)` | JVM | Đổi `SSLContext.getDefault()` |
| `HttpsURLConnection.setDefaultSSLSocketFactory(sf)` | Class-wide/JVM | Đổi default socket factory cho **các HttpsURLConnection mới** |
| `HttpsURLConnection.setDefaultHostnameVerifier(hv)` | Class-wide/JVM | Đổi default hostname verifier cho **các HttpsURLConnection mới** |
| `connection.setSSLSocketFactory(sf)` | Một connection | Thay factory của một instance trước connect |
| `connection.setHostnameVerifier(hv)` | Một connection | Thay hostname verifier của instance trước connect |

Theo Java SE 26 Javadoc, **các `HttpsURLConnection` mới được gán giá trị default static tại thời điểm tạo instance**. Đối tượng đã tạo không tự thay đổi khi class-level static default thay đổi.

**Một thay đổi `SSLContext.setDefault` không phải lời gọi tương đương với `HttpsURLConnection.setDefaultSSLSocketFactory`.** Hai globals phải được xem là hai trạng thái riêng trong vận hành và kiểm thử.

### 6.2. Ví dụ phản trực giác

```java
SSLContext.setDefault(trustedTls);

// KHÔNG được suy rằng dòng này chắc chắn đã đổi default
// static SSLSocketFactory của HttpsURLConnection.
SSLSocketFactory current =
        HttpsURLConnection.getDefaultSSLSocketFactory();
```

`HttpsURLConnection` có thể đã khởi tạo/cached class-default factory trước đó. Trong bài test thực tế OpenJDK 24, factory static **không đổi** khi chỉ thay `SSLContext.setDefault`. Điều này phù hợp với mô hình Javadoc: HttpsURLConnection quản lý default socket factory riêng.

Nếu **thực sự cần** một connection dùng context mới, cách có phạm vi hẹp hơn:

```java
HttpsURLConnection conn =
        (HttpsURLConnection) url.openConnection();
conn.setSSLSocketFactory(trustedTls.getSocketFactory());
// Giữ hostname verification chuẩn, không disable.
```

Snippets cần `url` được cấp dưới dạng `URL` và SSLContext `trustedTls` đã khởi tạo. Phải set trước khi connect; hãy sử dụng `setConnectTimeout`/`setReadTimeout` và đóng stream/`disconnect()`.

### 6.3. Thay static default factory cũng là thay đổi toàn tiến trình

```java
HttpsURLConnection.setDefaultSSLSocketFactory(
        trustedTls.getSocketFactory());
```

Hậu quả:
- Những `HttpsURLConnection` **tạo sau** sẽ được gán factory mới theo Javadoc.
- Những `HttpsURLConnection` **đã tạo** không tự có factory mới.
- Có thể ghi đè factory riêng của **một** instance bằng `setSSLSocketFactory`.
- Đây vẫn là global mutation, không phải đề xuất mặc định cho service đa tenant.

Test dùng certificate chỉ tin bởi trusted context, chứng minh một `HttpsURLConnection` mới với approved static factory kết nối được; một instance dùng factory khác vẫn từ chối.

### 6.4. HostnameVerifier là chính sách khác TrustManager

`SSLContext`/trust manager quyết định certificate chain có đáng tin hay không. Hostname verification kiểm tra certificate có hợp lệ cho hostname/IP mà ứng dụng định kết nối hay không.

Hai điều kiện đều cần thiết:

```text
Certificate chain trusted?
             AND
Endpoint identity (hostname/IP) matches?
             |
             +-- both true -> TLS peer identity may be accepted
```

Đừng sửa:
```java
HttpsURLConnection.setDefaultHostnameVerifier(
        (hostname, session) -> true);
```

Đây là **anti-pattern nguy hiểm, chỉ trình bày để cảnh báo — không dùng**. Nó vô hiệu hóa kiểm tra hostname và có thể ảnh hưởng các HttpsURLConnection tạo về sau trong JVM.

Ví dụ thực hành tạo chứng thư có **Subject Alternative Name `IP:127.0.0.1` và `DNS:localhost`** bằng `keytool`, dùng HTTPS URI `https://127.0.0.1:port` và giữ hostname verifier mặc định. Do đó handshake thành công là nhờ certificate thực sự được trust và endpoint identity khớp, không phải nhờ disable verification.

## 7. `SSLSocketFactory.getDefault()` và các provider khác

`SSLSocketFactory.getDefault()` là API JSSE riêng, có cơ chế provider/default factory, và Javadoc mô tả bước kiểm tra security property `ssl.SocketFactory.provider` khi method được gọi lần đầu. Một factory có thể được khởi tạo/cached theo implementation/provider.

**Không giả định** mọi lần gọi `SSLSocketFactory.getDefault()` phải trực tiếp đọc `SSLContext.getDefault()` mới nhất. Và đừng suy rằng:
- Thay `SSLContext.setDefault` sẽ đổi mọi `SSLSocketFactory` đã tạo.
- Thay factory của `HttpsURLConnection` sẽ thay default `SSLContext`.
- Một provider third-party sẽ có caching giống SunJSSE/JDK reference implementation.

Nếu framework của bạn lấy một factory trong startup rồi giữ nó, thì **thời điểm khởi tạo/cache** có thể quan trọng hơn thời điểm handshake.

Khi điều tra, kiểm tra:
1. Provider và protocol của `SSLContext`.
2. Context/factory được tạo/đọc ở đâu.
3. Có class-level static cache không.
4. Client object được xây khi nào.
5. Có connection pool/TLS sessions tái sử dụng không.
6. Có per-client/per-instance override không.
7. Unit/integration tests trên **đúng JDK và library version**.

## 8. Truststore/keystore system properties có liên hệ gì?

Oracle JSSE Security Developer's Guide mô tả mặc định của JDK reference implementation qua các properties như:

| System property | Ý nghĩa |
| --- | --- |
| `javax.net.ssl.trustStore` | File hoặc provider-backed truststore được dùng cho default trust managers |
| `javax.net.ssl.trustStoreType` | Kiểu truststore, ví dụ PKCS12 |
| `javax.net.ssl.trustStorePassword` | Password truststore nếu cần |
| `javax.net.ssl.keyStore` | Keystore default để cung cấp private key/certificate của phía mình |
| `javax.net.ssl.keyStoreType` | Kiểu keystore |
| `javax.net.ssl.keyStorePassword` | Password mở keystore khi cần |

Nếu không chỉ định truststore, JDK reference implementation tìm nguồn theo chính sách của nó (thường `jssecacerts` rồi `cacerts` trong java-home security directory). Nếu bạn trỏ tới một truststore **không tồn tại**, JDK documentation mô tả rằng có thể **không có truststore được sử dụng** trong default trust manager path — không có nghĩa tự tin mọi certificate.

### 8.1. Thời điểm đọc system properties rất quan trọng

`SSLContext.getDefault()` có thể được tạo lần đầu và giữ reference. Các factories/clients khác có thể cũng được tạo/cached. Vì vậy:

```java
System.setProperty("javax.net.ssl.trustStore", "/config/new-trust.p12");
```

**Không phải** một cách hot-reload đáng tin cậy cho các TLS clients đã khởi tạo. Thay đổi system property sau khi default managers/context đã được tạo có thể không làm các đối tượng cũ tự đọc lại file mới.

Nếu bạn cần truststore riêng:
- Đọc truststore thành `KeyStore`.
- Tạo `TrustManagerFactory` từ store đó.
- Tạo `SSLContext.getInstance("TLS")` và `init(...)`.
- Truyền context tường minh cho đúng `HttpClient`/factory/server.
- Khi rotation, tạo **context/client mới**, quản lý lifecycle và connection draining theo policy.

### 8.2. Không hardcode secrets trong command line production

Chỉ trong fixture chạy tạm, các lệnh `keytool` dùng một mật khẩu **cố định và không phải production secret**. Trong môi trường thật, tránh truyền secrets trên CLI nếu có nguy cơ hiển thị qua process listing/shell history/CI logs; dùng secret manager, bảo vệ file, option files hoặc phương thức nhập tương ứng.

**Không ghi production truststore/password vào source code hay Sheets**. Bài học này chỉ chứa fixtures giả để chứng minh behavior của JDK.

### 8.3. Mỗi runtime/provider có thể khác nhau

JSSE Security Developer's Guide lưu ý các system properties cụ thể là đặc điểm **JDK reference implementation**, không phải lời hứa mọi provider sẽ đọc tên và loại property giống nhau. Khi dùng một security provider khác, kiểm tra tài liệu của provider và tự chạy bài integration TLS tương ứng.

## 9. Tác động vận hành và bảo mật của global TLS mutation

### 9.1. Trust leakage giữa các tenants

Giả sử một JVM gọi ba dịch vụ:
- Partner A chỉ được tin CA/certificate A.
- Partner B chỉ được tin CA/certificate B.
- Internal admin service chỉ được tin CA nội bộ.

Nếu code xử lý request A tạm gọi `SSLContext.setDefault(trustA)`, trong cùng thời gian một thread của B tạo HTTP client mặc định, client B có thể lấy nhầm trust policy A. Có thể dẫn đến handshake fail hoặc hành vi tin cậy vượt quá security boundary.

**Không dùng global default làm context-local setting** cho user, tenant, task, coroutine hoặc request.

### 9.2. Races giữa các threads

`setDefault` không phải giao thức để serialize toàn bộ các bước:

```text
Thread A: setDefault(trust-A)
Thread B: build HttpClient (unexpectedly captures trust-A)
Thread A: setDefault(original)
Thread B: send HTTPS under trust-A for life of that client
```

Ngay cả khi thread A dùng `try/finally` để restore, thread B **đã capture context khác**. Một mutex ở code A không bảo vệ các thư viện không tham gia cùng mutex. Trên service đa luồng, thay global tại thời điểm request là anti-pattern.

### 9.3. Không thay đổi kết nối đã handshake

SSL/TLS connection đã thiết lập không “handshake lại” chỉ vì default context được thay. `HttpClient` có thể giữ connections, sessions và pool riêng.

Khi certificate/trust policy được revoke:
- Thu hồi trust trong config mới là cần thiết.
- Nhưng phải đánh giá **các connections đã thiết lập** và clients cũ.
- Có thể cần đóng old pools/client instances, drain requests hoặc restart tiến trình theo security policy.
- Không coi `SSLContext.setDefault(newTrusted)` là thao tác revoke mọi liên kết cũ.

### 9.4. Không “trust all” để chữa handshake failure

Một cách sửa lỗi phổ biến nhưng nguy hiểm là tạo `X509TrustManager` không thực hiện kiểm tra certificate, rồi set làm default global. Khi đó một lỗi chứng thư vốn chỉ xảy ra với **một** endpoint có thể biến thành lỗ hổng cho **toàn bộ các client mới** trong JVM.

Cách đúng:
1. Kiểm tra certificate chain, SAN và server hostname.
2. Xác định vì sao handshake thất bại: expired, unknown CA, wrong host, revoked, unsupported TLS, client cert.
3. Cấp certificate/CA hợp lệ trong truststore **được quản trị**.
4. Gắn truststore/context vào đúng client có nhu cầu.
5. Giữ hostname verification.
6. Test success và expected failure với endpoint giả.
7. Không bật trust-all trong production, kể cả “tạm để debug”.

## 10. Khuyến nghị thiết kế: truyền SSLContext qua dependency injection

Thay vì:

```java
// Không nên dùng để đổi trust policy theo request:
SSLContext.setDefault(partnerTls);
HttpClient client = HttpClient.newHttpClient();
```

Hãy viết:

```java
public final class PartnerGateway {
    private final HttpClient client;

    public PartnerGateway(SSLContext partnerTls) {
        this.client = HttpClient.newBuilder()
                .sslContext(partnerTls)
                .connectTimeout(Duration.ofSeconds(5))
                .build();
    }
}
```

Đây là **snippet class minh họa**, cần imports `HttpClient`, `SSLContext` và `Duration`, và code nghiệp vụ sử dụng `client`. Design này:
- TLS trust boundary được đưa vào constructor.
- Không thay shared state trong JVM.
- Tests có thể inject một test truststore rõ ràng.
- Có thể tạo client mới khi rotation.
- Không ảnh hưởng khách hàng khác chỉ vì đối tác này yêu cầu CA riêng.

### 10.1. Một client theo expected partner identity

Khi ứng dụng phục vụ nhiều tổ chức, có thể giữ map từ partnerID đã xác thực sang HttpClient cấu hình riêng. Key của map phải dựa trên **trusted routing/business identity**, không từ một URL không kiểm soát.

```java
Map<String, HttpClient> partnerClients = Map.of(
        "partner-A", HttpClient.newBuilder()
                .sslContext(partnerATls).build(),
        "partner-B", HttpClient.newBuilder()
                .sslContext(partnerBTls).build()
);
```

Đây là **snippet**, cần biến contexts và imports. Nó thể hiện per-partner TLS client isolation. Không tự tạo hàng nghìn client/pool vô hạn với mỗi request; dùng lifecycle/quotas có giới hạn.

### 10.2. HttpsURLConnection có per-instance override

```java
HttpsURLConnection c =
        (HttpsURLConnection) targetUrl.openConnection();
c.setSSLSocketFactory(partnerTls.getSocketFactory());
c.setConnectTimeout(5000);
c.setReadTimeout(5000);
try (InputStream in = c.getInputStream()) {
    // Read bounded response; validate protocol/application data.
} finally {
    c.disconnect();
}
```

Đây là snippet có imports `HttpsURLConnection` và `InputStream`; biến `targetUrl`/`partnerTls` cần được tạo trước. **Không gọi** `setDefaultSSLSocketFactory` chỉ để một connection sử dụng truststore riêng.

### 10.3. HTTPS server riêng

Nếu dùng `com.sun.net.httpserver.HttpsServer`, cấu hình explicit context:

```java
HttpsServer server = HttpsServer.create(address, backlog);
server.setHttpsConfigurator(new HttpsConfigurator(serverTls));
```

Đây là snippet cần `address`, `backlog` và `serverTls` được tạo từ keystore server. Nó tách TLS server identity khỏi JVM default client trust configuration. Code đầy đủ trong fixture sử dụng cách này.

## 11. Thử nghiệm TLS có chứng thư thật nhưng hoàn toàn cục bộ

### 11.1. Vì sao cần một integration test thật?

Test chỉ so sánh references `SSLContext.getDefault()==context` chưa đủ chứng minh **client nào sẽ tin chứng thư**. Một test có giá trị hơn cần:
- Một HTTPS server thực.
- Certificate server không thuộc truststore của context bị từ chối.
- Một context khác tin **chính certificate** đã chỉ định.
- Hai clients được build trước/sau khi đổi default.
- Một client gắn context explicit.
- Một `HttpsURLConnection` dùng static/per-instance factory.
- Xác minh cả success lẫn expected TLS handshake failure.
- Dọn globals và server sau khi test.

Fixture này dùng `keytool` của JDK tạo chứng thư **self-signed chỉ cho localhost** và import certificate vào một **truststore riêng**. Nó không tin mọi certificate: client “trusted” chỉ được thiết lập trust anchors từ store explicit. Client “untrusted” lấy trust managers từ keystore rỗng và phải từ chối server.

### 11.2. Mô hình test

```text
Local PKCS12 server.p12 (private key + localhost cert)
                      |
                      v
       HttpsServer 127.0.0.1:ephemeral
       /probe -> HTTPS 200 "tls-ok"
                      |
      +---------------+--------------------+
      |                                    |
      v                                    v
SSLContext trusted                    SSLContext untrusted
PKCS12 trusted.p12                    empty PKCS12 truststore
       |                                    |
       v                                    v
Handshake SUCCEEDS                   Handshake REJECTED
       |
       +-- explicit HttpClient succeeds independent of global
       +-- new default HttpClient succeeds only after setDefault(trusted)
       +-- HttpsURLConnection succeeds after its own factory update
```

Trong Java source, `HttpsServer` nhận `serverTls` **riêng**, không đọc global client SSLContext. Vì vậy thay default client context không làm server đổi certificate.

### 11.3. Các tệp test

Tạo một folder **tạm** không chứa secrets thật. Các tệp:
- `server.p12`: PKCS12 chứa private key và certificate server.
- `server.cer`: certificate công khai được export.
- `trusted.p12`: PKCS12 truststore chứa certificate đã import.
- `SSLContextGlobalImpactDemo.java`: source thực hành.

Chỉ dùng các tệp này trong local test. Chứng thư ngắn hạn và password mẫu **không dành cho production**. Không commit chúng lên Git hoặc copy private key vào nội dung bài Knowledge.

### 11.4. Tạo chứng thư self-signed bằng `keytool`

Chạy các lệnh sau trong thư mục test. Trên Windows PowerShell và shell Linux/macOS, có thể nhập **mỗi lệnh một dòng**, không cần backslash continuation:

```bash
keytool -genkeypair -alias demo -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 2 -dname "CN=localhost,OU=Test,O=Demo,C=US" -ext "SAN=DNS:localhost,IP:127.0.0.1" -keystore server.p12 -storetype PKCS12 -storepass fixture-only-changeit123 -keypass fixture-only-changeit123 -noprompt

keytool -exportcert -alias demo -keystore server.p12 -storetype PKCS12 -storepass fixture-only-changeit123 -file server.cer -rfc

keytool -importcert -alias trusted-demo -file server.cer -keystore trusted.p12 -storetype PKCS12 -storepass fixture-only-changeit123 -noprompt
```

- Chứng thư test được tạo với RSA 2048/SHA256withRSA.
- `SAN=DNS:localhost,IP:127.0.0.1` cho phép hostname/IP endpoint verification hợp lệ đối với localhost/IP test.
- Không có public CA; client chỉ thành công khi truststore explicit nhận certificate đã export.
- `trusted.p12` chứa certificate được trust, không cần chứa private key server.
- Đây là **local ephemeral development fixture**; private key/password phải được bảo vệ, xóa khi test xong.
- Không dùng certificate tự ký này làm chứng thư public Internet thật.

**Lưu ý thực tế:** Dòng lệnh hiển thị password chỉ chấp nhận được cho fixture không có giá trị. Với production secrets hãy dùng secret injection bảo mật hơn theo chính sách tổ chức.

## 12. Chương trình Java 17+ hoàn chỉnh — `SSLContextGlobalImpactDemo.java`

Mã dưới đây:
1. Đọc `server.p12` và `trusted.p12`.
2. Tạo `SSLContext` server với `KeyManagerFactory`.
3. Tạo hai context client: **trusted** từ certificate được import và **untrusted** từ truststore rỗng.
4. Mở `HttpsServer` ở địa chỉ **127.0.0.1**, port động, dùng chứng thư test.
5. Kiểm tra `HttpClient` cũ/new mặc định, context explicit và các TLS handshakes tương ứng.
6. Chứng minh `SSLContext.setDefault` được thread khác trong cùng JVM nhìn thấy.
7. Chứng minh class-default factory của `HttpsURLConnection` là một setting riêng, không tự đổi khi chỉ set default SSLContext trong test JDK24.
8. Chứng minh new `HttpsURLConnection` thừa kế class default, old instance giữ factory trước đó.
9. Chứng minh per-instance `setSSLSocketFactory` thay đổi được đúng một connection.
10. Không thay `HostnameVerifier` mặc định; test TLS chỉ thành công khi certificate SAN khớp IP.
11. Không dùng **trust-all**; các TLS handshakes thất bại là hành vi bảo mật được mong đợi.
12. **Restore cả hai globals** trong `finally`, stop HTTPS server và shutdown worker executor.
13. In 40 kết quả PASS khi chạy trên OpenJDK24.

**Chú ý:** Ví dụ **cố ý thay global state trong JVM của chính nó** để dạy cơ chế này. Chỉ chạy trong một **JVM test riêng**, không gọi chương trình hoặc những thay đổi tương đương trong JVM production đang xử lý traffic. Restore references trong `finally` không thể “undo” những client/connection đã xây dựng trong thời gian giá trị default bị thay.

### 12.1. Lưu file mã nguồn


```java
import com.sun.net.httpserver.HttpsConfigurator;
import com.sun.net.httpserver.HttpsServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URL;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.HostnameVerifier;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManagerFactory;

public final class SSLContextGlobalImpactDemo {
    static int passed;

    static void check(String label, boolean ok) {
        if (!ok) throw new AssertionError("FAIL " + label);
        System.out.println("PASS " + label);
        passed++;
    }

    static KeyStore load(Path file, char[] password) throws Exception {
        KeyStore ks = KeyStore.getInstance("PKCS12");
        try (InputStream in = java.nio.file.Files.newInputStream(file)) {
            ks.load(in, password);
        }
        return ks;
    }

    static SSLContext clientContext(KeyStore trusted) throws Exception {
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trusted);
        SSLContext result = SSLContext.getInstance("TLS");
        result.init(null, tmf.getTrustManagers(), new SecureRandom());
        return result;
    }

    static SSLContext serverContext(KeyStore withPrivateKey,
                                    char[] password) throws Exception {
        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(withPrivateKey, password);
        SSLContext result = SSLContext.getInstance("TLS");
        result.init(kmf.getKeyManagers(), null, new SecureRandom());
        return result;
    }

    static HttpClient httpClient(SSLContext optionalContext) {
        HttpClient.Builder builder = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(4));
        if (optionalContext != null) builder.sslContext(optionalContext);
        return builder.build();
    }

    static boolean getOk(HttpClient client, URI url) throws Exception {
        HttpRequest req = HttpRequest.newBuilder(url)
                .timeout(Duration.ofSeconds(4))
                .GET().build();
        try {
            HttpResponse<String> r = client.send(req,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            return r.statusCode() == 200 && r.body().equals("tls-ok");
        } catch (IOException refused) {
            return false; // Expected for a certificate not in this truststore.
        }
    }

    static HttpsURLConnection urlConnection(URL url) throws Exception {
        HttpsURLConnection c = (HttpsURLConnection) url.openConnection();
        c.setConnectTimeout(4000);
        c.setReadTimeout(4000);
        c.setRequestMethod("GET");
        return c;
    }

    static boolean urlOk(HttpsURLConnection connection) throws Exception {
        try {
            try (InputStream in = connection.getInputStream()) {
                String response = new String(
                        in.readAllBytes(), StandardCharsets.UTF_8);
                return connection.getResponseCode() == 200
                        && response.equals("tls-ok");
            }
        } catch (IOException refused) {
            return false;
        } finally {
            connection.disconnect();
        }
    }

    static void reply(com.sun.net.httpserver.HttpExchange exchange)
            throws IOException {
        try (exchange) {
            byte[] payload = "tls-ok".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, payload.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(payload);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: server.p12 trust.p12 store-password");
        }
        char[] password = args[2].toCharArray();

        SSLContext originalGlobal = SSLContext.getDefault();
        SSLSocketFactory originalHttpsFactory =
                HttpsURLConnection.getDefaultSSLSocketFactory();
        HostnameVerifier originalVerifier =
                HttpsURLConnection.getDefaultHostnameVerifier();

        ExecutorService workers = Executors.newFixedThreadPool(4);
        HttpsServer server = null;
        try {
            KeyStore serverStore = load(Path.of(args[0]), password);
            KeyStore trustedStore = load(Path.of(args[1]), password);
            KeyStore emptyStore = KeyStore.getInstance("PKCS12");
            emptyStore.load(null, password);

            SSLContext trusted = clientContext(trustedStore);
            SSLContext untrusted = clientContext(emptyStore);
            SSLContext serverTls = serverContext(serverStore, password);
            check("separate-sslcontexts-created",
                    trusted != untrusted && serverTls != trusted);
            check("contexts-use-tls-protocol",
                    "TLS".equals(trusted.getProtocol())
                    && "TLS".equals(untrusted.getProtocol()));
            check("truststore-has-imported-certificate",
                    trustedStore.getCertificate("trusted-demo") != null);
            check("empty-truststore-has-no-aliases",
                    !emptyStore.aliases().hasMoreElements());

            server = HttpsServer.create(new InetSocketAddress(
                    InetAddress.getByName("127.0.0.1"), 0), 16);
            server.setHttpsConfigurator(new HttpsConfigurator(serverTls));
            server.createContext("/probe",
                    SSLContextGlobalImpactDemo::reply);
            server.setExecutor(workers);
            server.start();
            int port = server.getAddress().getPort();
            URI target = URI.create(
                    "https://127.0.0.1:" + port + "/probe");
            URL targetUrl = target.toURL();

            check("https-server-loopback-ephemeral",
                    server.getAddress().getAddress().isLoopbackAddress()
                    && port > 0);
            check("https-server-uses-explicit-context",
                    server.getHttpsConfigurator().getSSLContext()
                            == serverTls);

            SSLContext.setDefault(untrusted);
            check("global-default-is-now-untrusted",
                    SSLContext.getDefault() == untrusted);

            HttpClient older = httpClient(null);
            HttpClient fixedTrusted = httpClient(trusted);
            HttpClient fixedUntrusted = httpClient(untrusted);
            check("old-client-captures-initial-global-default",
                    older.sslContext() == untrusted);
            check("explicit-trusted-client-uses-own-context",
                    fixedTrusted.sslContext() == trusted);
            check("explicit-untrusted-client-uses-own-context",
                    fixedUntrusted.sslContext() == untrusted);
            check("old-client-rejects-self-signed-server",
                    !getOk(older, target));
            check("explicit-trusted-client-connects-over-tls",
                    getOk(fixedTrusted, target));
            check("explicit-untrusted-client-rejects",
                    !getOk(fixedUntrusted, target));

            HttpsURLConnection oldConnection =
                    urlConnection(targetUrl);
            check("old-httpsurlconnection-inherits-old-static-factory",
                    oldConnection.getSSLSocketFactory()
                            == originalHttpsFactory);

            SSLContext.setDefault(trusted);
            check("global-default-points-to-trusted",
                    SSLContext.getDefault() == trusted);

            AtomicBoolean seesProcessDefault = new AtomicBoolean(false);
            Thread thread = new Thread(() -> {
                try {
                    seesProcessDefault.set(
                            SSLContext.getDefault() == trusted);
                } catch (Exception error) {
                    throw new AssertionError(error);
                }
            });
            thread.start();
            thread.join();
            check("another-thread-sees-same-global",
                    seesProcessDefault.get());

            HttpClient newer = httpClient(null);
            check("new-client-captures-updated-global-default",
                    newer.sslContext() == trusted);
            check("new-default-client-connects",
                    getOk(newer, target));
            check("old-client-retains-old-context",
                    older.sslContext() == untrusted);
            check("old-client-still-rejects",
                    !getOk(older, target));
            check("explicit-untrusted-not-changed",
                    !getOk(fixedUntrusted, target));
            check("explicit-trusted-not-changed",
                    getOk(fixedTrusted, target));

            check("httpsurlconnection-static-factory-not-overwritten",
                    HttpsURLConnection.getDefaultSSLSocketFactory()
                            == originalHttpsFactory);
            check("existing-connection-still-has-old-factory",
                    oldConnection.getSSLSocketFactory()
                            == originalHttpsFactory);
            check("old-httpsurlconnection-still-rejects",
                    !urlOk(oldConnection));

            SSLSocketFactory approvedFactory =
                    trusted.getSocketFactory();
            HttpsURLConnection.setDefaultSSLSocketFactory(approvedFactory);
            check("httpsurlconnection-global-factory-is-new",
                    HttpsURLConnection.getDefaultSSLSocketFactory()
                            == approvedFactory);
            HttpsURLConnection newConnection =
                    urlConnection(targetUrl);
            check("new-httpsurlconnection-inherits-approved-factory",
                    newConnection.getSSLSocketFactory()
                            == approvedFactory);
            check("new-httpsurlconnection-tls-success",
                    urlOk(newConnection));

            HttpsURLConnection perInstance =
                    urlConnection(targetUrl);
            perInstance.setSSLSocketFactory(
                    untrusted.getSocketFactory());
            check("per-instance-ssl-factory-overrides-static-default",
                    !urlOk(perInstance));

            HttpsURLConnection manualOverride =
                    urlConnection(targetUrl);
            manualOverride.setSSLSocketFactory(approvedFactory);
            check("per-instance-trusted-override-success",
                    urlOk(manualOverride));
            check("hostname-verifier-still-original",
                    HttpsURLConnection.getDefaultHostnameVerifier()
                            == originalVerifier);

            SSLContext.setDefault(untrusted);
            check("global-default-can-be-restored-to-other-context",
                    SSLContext.getDefault() == untrusted);
            check("built-client-still-has-trusted-context",
                    newer.sslContext() == trusted);
            check("built-client-works-after-global-changes-again",
                    getOk(newer, target));
            check("new-client-after-revert-uses-untrusted",
                    httpClient(null).sslContext() == untrusted);
            check("httpsurlconnection-separate-default-persists",
                    HttpsURLConnection.getDefaultSSLSocketFactory()
                            == approvedFactory);
            check("reject-null-sslcontext",
                    rejectsNullDefault());

            System.out.println("passed=" + passed);
        } finally {
            // Restore BOTH independently global defaults.
            HttpsURLConnection.setDefaultSSLSocketFactory(
                    originalHttpsFactory);
            SSLContext.setDefault(originalGlobal);
            if (server != null) server.stop(1);
            workers.shutdownNow();
        }
        check("global-sslcontext-restored",
                SSLContext.getDefault() == originalGlobal);
        check("global-https-factory-restored",
                HttpsURLConnection.getDefaultSSLSocketFactory()
                        == originalHttpsFactory);
        check("global-hostname-verifier-unchanged",
                HttpsURLConnection.getDefaultHostnameVerifier()
                        == originalVerifier);
        System.out.println("totalPassed=" + passed);
    }

    static boolean rejectsNullDefault() {
        try {
            SSLContext.setDefault(null);
            return false;
        } catch (NullPointerException expected) {
            return true;
        }
    }
}
```

### 12.2. Biên dịch và chạy

Trong folder có `SSLContextGlobalImpactDemo.java`, `server.p12` và `trusted.p12`, dùng JDK 17+:

```bash
javac --release 17 --add-modules jdk.httpserver -encoding UTF-8 SSLContextGlobalImpactDemo.java
java --add-modules jdk.httpserver SSLContextGlobalImpactDemo server.p12 trusted.p12 fixture-only-changeit123
```

`jdk.httpserver` phục vụ local `HttpsServer` để test; `java.net.http` dùng cho HTTP client; `javax.net.ssl` nằm trong `java.base`. Với một named module, có thể khai báo:

```java
module example.tls {
    requires jdk.httpserver;
    requires java.net.http;
}
```

Snippet `module-info.java` trên không thể chạy độc lập và source fixture chưa đặt trong named package; nếu chuyển sang JPMS, cần chỉnh package/build layout tương ứng. Chương trình hiện tại chạy qua classpath thuận tiện hơn để thử và không sử dụng thư viện bên ngoài JDK.

**Điều kiện test:** Cần OS cho phép bind localhost TCP port. Nếu môi trường sandbox cấm socket loopback, test có thể không chạy; đó là hạn chế môi trường, không phải chứng cứ phương thức Java TLS không hoạt động.

### 12.3. Stdout đã kiểm tra với OpenJDK 24

```text
PASS separate-sslcontexts-created
PASS contexts-use-tls-protocol
PASS truststore-has-imported-certificate
PASS empty-truststore-has-no-aliases
PASS https-server-loopback-ephemeral
PASS https-server-uses-explicit-context
PASS global-default-is-now-untrusted
PASS old-client-captures-initial-global-default
PASS explicit-trusted-client-uses-own-context
PASS explicit-untrusted-client-uses-own-context
PASS old-client-rejects-self-signed-server
PASS explicit-trusted-client-connects-over-tls
PASS explicit-untrusted-client-rejects
PASS old-httpsurlconnection-inherits-old-static-factory
PASS global-default-points-to-trusted
PASS another-thread-sees-same-global
PASS new-client-captures-updated-global-default
PASS new-default-client-connects
PASS old-client-retains-old-context
PASS old-client-still-rejects
PASS explicit-untrusted-not-changed
PASS explicit-trusted-not-changed
PASS httpsurlconnection-static-factory-not-overwritten
PASS existing-connection-still-has-old-factory
PASS old-httpsurlconnection-still-rejects
PASS httpsurlconnection-global-factory-is-new
PASS new-httpsurlconnection-inherits-approved-factory
PASS new-httpsurlconnection-tls-success
PASS per-instance-ssl-factory-overrides-static-default
PASS per-instance-trusted-override-success
PASS hostname-verifier-still-original
PASS global-default-can-be-restored-to-other-context
PASS built-client-still-has-trusted-context
PASS built-client-works-after-global-changes-again
PASS new-client-after-revert-uses-untrusted
PASS httpsurlconnection-separate-default-persists
PASS reject-null-sslcontext
passed=37
PASS global-sslcontext-restored
PASS global-https-factory-restored
PASS global-hostname-verifier-unchanged
totalPassed=40
```

**Kết quả QA:** `javac --release 17 --add-modules jdk.httpserver` trên OpenJDK24 PASS. Chạy TLS thật với `HttpsServer` và clients trên loopback đạt **40/40 assertions PASS**. Các phép kiểm tra negative xác nhận client không có chứng thư trusted bị từ chối, thay vì gạt bỏ validation. Mọi giá trị global được khôi phục trong `finally` trước khi chương trình kết thúc.

### 12.4. Diễn giải các nhóm kiểm thử

| Nhóm | Assertions tiêu biểu | Kết luận |
| --- | --- | --- |
| Cấu hình riêng | `separate-sslcontexts-created` | Trusted, untrusted và server contexts là các object riêng |
| PKCS12 truststore | `truststore-has-imported-certificate` | Trust được provision tường minh, không trust-all |
| HTTPS thật | `https-server-loopback-ephemeral` | Local TLS server với certificate hợp lệ cho IP localhost |
| Global mặc định ban đầu | `global-default-is-now-untrusted` | `setDefault` thay reference của `getDefault` |
| HttpClient cũ | `old-client-captures-initial-global-default` | Client nhận default tại construction |
| HTTP client explicit | `explicit-trusted-client-uses-own-context` | Builder cho phép isolation |
| Negative handshake | `old-client-rejects-self-signed-server` | Truststore rỗng từ chối certificate test |
| Positive handshake | `explicit-trusted-client-connects-over-tls` | Truststore chứa certificate cho phép TLS handshake |
| Cross-thread | `another-thread-sees-same-global` | Default SSLContext là JVM-wide |
| Client mới | `new-client-captures-updated-global-default` | Mặc định mới ảnh hưởng new client |
| Client cũ sau đổi | `old-client-still-rejects` | Không retroactive |
| URLConnection static | `httpsurlconnection-static-factory-not-overwritten` | `SSLContext.setDefault` không tự set class default factory trên runtime đã test |
| URLConnection snapshot | `existing-connection-still-has-old-factory` | Instance cũ giữ factory từ lúc tạo |
| URLConnection new | `new-httpsurlconnection-inherits-approved-factory` | New instance thừa kế static factory đã set |
| Per-instance override | `per-instance-ssl-factory-overrides-static-default` | Một connection có thể dùng factory riêng |
| Hostname identity | `hostname-verifier-still-original` | Không vô hiệu hóa hostname check |
| Revert global | `built-client-works-after-global-changes-again` | HttpClient đã build vẫn giữ context trước đó |
| Cleanup | `global-sslcontext-restored`, `global-https-factory-restored` | Trả reference global về giá trị ban đầu |

**Giới hạn cần nói rõ:** Test chạy **OpenJDK24**. Nó xác nhận behavior cụ thể của built-in providers ở runtime này và các public contracts được Java SE26 công bố. Không khẳng định mọi third-party JSSE/HTTP library tự động chia sẻ cùng implementation-specific caching. 40/40 PASS cũng không chứng minh hệ thống production sẽ đạt mọi TLS policy/PKI compliance.

## 13. Thay SSLContext mặc định có làm thay đổi certificate validation ngay không?

Đặt câu hỏi cụ thể:

### Trường hợp A: client đã build trước khi đổi

- Client có `SSLContext` cũ.
- SSLContext.setDefault mới không thay reference trong client.
- Khi client mở TLS connection mới, nó tiếp tục dùng context của nó theo contract.
- Test client cũ vẫn từ chối certificate selfsigned ngay cả sau khi global được đổi sang truststore chấp nhận certificate đó.

### Trường hợp B: client mới build sau khi đổi

- Không truyền explicit `SSLContext`.
- Theo Java SE26 `HttpClient` docs, client lấy default tại construction.
- Nếu global lúc đó là context tin certificate test, handshake có thể thành công.
- Nếu global bị đổi lại trước lần build tiếp, client tiếp theo lấy default mới theo thời điểm nó được tạo.

### Trường hợp C: client có context explicit

- Không phụ thuộc vào global default được đổi thế nào.
- Trusted explicit client luôn thành công tới server test (miễn endpoint/server còn chạy).
- Untrusted explicit client luôn từ chối certificate đó.
- Đây là cách đảm bảo tenant/partner isolation.

### Trường hợp D: `HttpsURLConnection`

- Nó dựa trên **default static `SSLSocketFactory` riêng**, được chụp tại instance creation, không đơn giản tương đương SSLContext.getDefault cho mỗi request.
- Dùng `HttpsURLConnection.setDefaultSSLSocketFactory(...)` nếu chủ động thay mặc định class cho new instances; nhưng điều này vẫn là thay đổi global.
- Dùng `connection.setSSLSocketFactory(...)` để chỉ ảnh hưởng một connection cụ thể.
- Giữ hostname verifier chuẩn.

### Trường hợp E: kết nối đã mở

- Không “thay peer certificate trust decision giữa một TLS session” chỉ vì global reference đổi.
- Nếu application cần revoke trust ngay, đóng/drain sessions và lifecycle cũ theo security policy, không chỉ setDefault.

## 14. Những điều cần xác minh trước khi đổi default trong một dự án

### 14.1. Lập bản đồ consumers

Tìm trong **source do bạn sở hữu**:
- `SSLContext.getDefault()` / `setDefault(...)`.
- `SSLContext.getInstance(...)` và `init(...)`.
- `HttpClient.newHttpClient()` / `HttpClient.newBuilder()`.
- `Builder.sslContext(...)`.
- `HttpsURLConnection.setDefaultSSLSocketFactory(...)`.
- `HttpsURLConnection.setSSLSocketFactory(...)`.
- `SSLSocketFactory.getDefault()`.
- `HttpsURLConnection.setDefaultHostnameVerifier(...)`.
- Framework-specific TLS factories/connection pools.

Không tự search hoặc sửa dependency internals ngoài phạm vi thiết kế. Nếu dùng Spring, Apache HttpClient, Netty, gRPC hoặc SDK của đối tác, hãy kiểm tra **tài liệu và version cụ thể** về cách cấp SSLContext/trust manager. Không giả định tất cả đều nghe theo JVM default.

### 14.2. Kiểm tra thời điểm tạo client

Câu hỏi vận hành:
- Client là singleton tạo ở startup?
- Được tạo lazily ở request đầu tiên?
- Có sử dụng dependency injection?
- Có connection pool hoặc cache TLS sessions?
- Có key rotation hay truststore reload không?
- Có nhiều tenants trong cùng JVM không?
- Có thể close/drain old client đúng JDK/runtime không?

Chỉ khi biết thời điểm mỗi consumer lấy cấu hình mới có thể đánh giá blast radius.

### 14.3. Có nhiều nguồn TLS configuration

Mỗi runtime có thể bị ảnh hưởng bởi:
- JVM security properties và system properties.
- Default `SSLContext`.
- Default `SSLSocketFactory` của `HttpsURLConnection`.
- Per-instance/per-client context/factory.
- `SSLParameters`.
- Protocol/cipher allowlist và disabled algorithms.
- Truststore/certificate lifecycle.
- TLS session caches và reuse.
- Server-specific `SSLContext`, key managers, mTLS config.
- Framework-specific configuration.

Một lệnh `setDefault` chỉ thay **một** trong những lớp cấu hình đó.

## 15. Triển khai thay truststore an toàn hơn global mutation

Một kế hoạch cho service có nhiều HTTPS clients:

1. **Provision** chứng thư/CA được duyệt vào truststore riêng của service/partner.
2. **Load** trusted material bằng `KeyStore` từ đường dẫn cấu hình do tổ chức kiểm soát.
3. **Init** `TrustManagerFactory` và `SSLContext` mới.
4. **Test** explicit client với endpoint staging/localhost hoặc môi trường tích hợp được phép.
5. **Build** `HttpClient` mới bằng `Builder.sslContext(newContext)`.
6. **Switch** dependency/reference của đúng service/partner tại một điểm an toàn.
7. **Drain** old requests/connections và đóng client khi API/runtime hỗ trợ; dùng restart nếu cần.
8. **Observe** handshake failures, certificate expiry, wrong hostname và response latency.
9. **Rollback** theo configuration version, không bằng setDefault ngẫu nhiên trong request path.
10. **Audit** ai đổi trust policy, file nào được đọc và phạm vi khách hàng bị ảnh hưởng.

Nếu cả JVM thực sự chỉ có một TLS policy duy nhất và bạn kiểm soát toàn bộ consumers, cấu hình default tại **startup trước khi tạo clients** có thể có lý do sử dụng. Nhưng ngay cả trong trường hợp này, phải kiểm tra HttpsURLConnection static factory/lifecycle và third-party libraries riêng, tránh hiểu default là cơ chế magic đồng nhất mọi thư viện.

### 15.1. Khi nào cần restart?

Với thay đổi nhạy cảm về trust:
- Nhiều clients cũ có thể giữ SSLContext cũ.
- Static factories/class caches có thể giữ references.
- TLS connections đã handshake có thể tiếp tục tồn tại.
- Một framework không hỗ trợ reload an toàn.

Khi không có cách audit và đổi mọi consumers, **rolling restart** với cấu hình startup mới thường dễ chứng minh hơn một “hot swap” default toàn tiến trình. Đây là khuyến nghị kiến trúc, không phải yêu cầu của `SSLContext` API.

### 15.2. Khác nhau giữa rollback reference và rollback tất cả hiệu ứng

```java
SSLContext original = SSLContext.getDefault();
try {
    SSLContext.setDefault(testContext);
    // Code thử nghiệm.
} finally {
    SSLContext.setDefault(original);
}
```

Mẫu này chỉ khôi phục **current global reference**. Nó không:
- Xóa clients đã được build với `testContext`.
- Hủy TLS sessions đã mở trong lúc test.
- Khôi phục state các thư viện đã cache giá trị mặc định mới.
- Ngăn thread khác capture test context trước khi finally chạy.
- Đảm bảo không có third-party code thay default xen vào giữa.

Vì thế **chỉ dùng trong JVM test riêng**, không dùng thay tenant context trên server đang phục vụ traffic. Fixture cũng restore class static default factory của `HttpsURLConnection` riêng.

## 16. Những lỗi phổ biến cần tránh

**1. Gọi `SSLContext.setDefault(custom)` để một HTTP request dùng CA riêng.**  
Đây là global mutation của JVM, không phải per-request configuration.

**2. Nghĩ `setDefault` thay đổi mọi HTTPS client đã tạo.**  
Sai. `HttpClient` lấy default tại construction và giữ context riêng.

**3. Nghĩ đổi global xong sẽ lập tức làm tất cả TLS sessions handshake lại.**  
Sai. Sessions/connections cũ không tự bị thay.

**4. Nghĩ `SSLContext.getInstance("TLS")` tự đổi default.**  
Không; phải init và truyền explicit hoặc cố ý setDefault.

**5. Gọi `SSLContext.setDefault(null)` để reset.**  
Ném `NullPointerException` theo Java SE26 API.

**6. Truyền context chưa `init` cho default.**  
Javadoc yêu cầu context được set phải ngay lập tức sử dụng được.

**7. Coi `HttpsURLConnection` luôn dùng `SSLContext.getDefault()` mới nhất.**  
Nó có static default SSLSocketFactory riêng được thừa kế khi instance được tạo.

**8. Nhầm `SSLContext.setDefault` với `HttpsURLConnection.setDefaultSSLSocketFactory`.**  
Là hai globals khác nhau, không hoán đổi.

**9. Thay `HttpsURLConnection.setDefaultSSLSocketFactory` rồi nghĩ connection đã tạo đổi theo.**  
Không. Existing instance giữ factory đã lấy, trừ khi thay per-instance trước connect.

**10. Disable hostname verification bằng verifier luôn trả true.**  
Đây là lỗ hổng bảo mật nghiêm trọng.

**11. Viết TrustManager có checkServerTrusted rỗng.**  
Không còn xác minh certificate peer, đặc biệt nguy hiểm nếu set làm default toàn JVM.

**12. Đặt truststore password production trực tiếp trên CLI/log.**  
Có thể lộ qua process listing/shell history/CI logs.

**13. Chỉnh `javax.net.ssl.trustStore` bằng `System.setProperty` rồi kỳ vọng client cũ hot-reload.**  
Không đảm bảo; cache/default managers có thể đã được tạo.

**14. Tin một truststore path không tồn tại sẽ fallback an toàn theo ý bạn.**  
JDK reference implementation có quy tắc riêng, có thể không dùng truststore được chỉ định; phải kiểm tra và fail closed.

**15. Dùng một global trust policy cho nhiều tenants có yêu cầu độc lập.**  
Dễ trust leakage/tenant confusion.

**16. SetDefault(trustA), tạo client A, rồi setDefault(trustB) trên requests khác nhau.**  
Race với threads khác tạo clients trong cùng JVM.

**17. Cho rằng `finally` restore default nghĩa không có side effects còn lại.**  
Những clients, sockets và caches đã tạo vẫn còn.

**18. Bỏ qua connection pooling khi cập nhật chính sách.**  
Một client giữ kết nối cũ không cần handshake lại.

**19. Không kiểm thử TLS handshake thật, chỉ so sánh objects.**  
Cần thử cert trusted/untrusted và hostname validation.

**20. Tự ký cert rồi chấp nhận mọi self-signed cert trong production.**  
Sai. Chỉ tin certificate/CA cụ thể từ trust source được kiểm soát.

**21. Dùng certificate test có CN nhưng thiếu SAN cho IP đang kết nối.**  
Có thể handshake fail do endpoint identity mismatch; fixture có SAN IP 127.0.0.1.

**22. Nhầm TrustManagerFactory với KeyManagerFactory.**  
Một bên quyết định peer trust, bên kia chọn identity private key của phía mình.

**23. Nghĩ `SSLContext.getDefault()` mỗi lần đều re-read cacerts.**  
Không. Javadoc mô tả default object được tạo/lưu từ lần đầu.

**24. Không biết các JSSE providers có thể khác nhau.**  
Provider-specific initialization/caching cần được test trên deployment runtime.

**25. Bật TLS protocol yếu để khắc phục một lỗi certificate.**  
Sai layer và gây giảm bảo mật. Kiểm tra trust, SAN và TLS policy có chủ đích.

**26. Không đặt timeout và giới hạn request khi thực hiện TLS integration test.**  
Dễ tạo test treo. Fixture dùng connect/read/request timeouts ngắn.

**27. Dùng fixture sửa globals trong application server đang hoạt động.**  
Chỉ nên chạy test trong JVM riêng, tách biệt traffic thật.

**28. Giả định TLS server luôn bị ảnh hưởng bởi thay default client context.**  
`HttpsServer` có thể được cấp `HttpsConfigurator(explicitContext)` riêng.

**29. Không quản lý old clients khi rotation.**  
Old client giữ trust context cũ và có thể reuse connections.

**30. Không ghi nhận version của Java và provider trong incident.**  
Không thể giải thích caching/protocol differences đầy đủ nếu thiếu runtime metadata.

**31. Coi `SSLSocketFactory.getDefault()` và `SSLContext.getDefault()` là cùng một lời gọi.**  
Factory có provider/default/caching behavior riêng, không giả định tự cập nhật sau global swap.

**32. Dùng công thức “setDefault ở đầu request, restore cuối request” để cô lập tenant.**  
Static global không có request scope; concurrency phá vỡ giả định.

## 17. Checklist review code và vận hành

- [ ] Định nghĩa rõ ai sở hữu truststore, certificate pins và TLS policy.
- [ ] Xác định chính xác các thư viện HTTP/TLS lấy default khi nào.
- [ ] Không đổi global default để phục vụ một request hoặc một tenant.
- [ ] Ưu tiên `HttpClient.Builder.sslContext(context)` cho clients cần trust riêng.
- [ ] Dùng `HttpsURLConnection.setSSLSocketFactory(factory)` per-instance nếu cần.
- [ ] Giữ hostname verification chuẩn; không dùng trust-all.
- [ ] Phân biệt `SSLContext.setDefault` với static `HttpsURLConnection` defaults.
- [ ] Kiểm tra cả default SSLSocketFactory và default HostnameVerifier khi điều tra.
- [ ] Test client xây trước và sau khi global thay đổi.
- [ ] Test context explicit không bị ảnh hưởng bởi global.
- [ ] Test TLS handshake với cert trusted và cert untrusted.
- [ ] Test chứng thư có SAN khớp DNS/IP đích.
- [ ] Kiểm soát connection pools/TLS session cache và old-client lifecycle.
- [ ] Có rollover/revocation/expiry policy cho cert và trust anchors.
- [ ] Không dùng `System.setProperty(...)` như cơ chế reload runtime toàn diện.
- [ ] Không truyền password production trong command lines.
- [ ] Có metrics handshake failures, TLS protocol/cipher allowlists và safe diagnostics.
- [ ] Có rolling restart/rollback strategy nếu hot reload không chứng minh được.
- [ ] Tránh globals cross-tenant, xác minh concurrency races.
- [ ] Tạo/đóng test HTTPS server và executor đúng lifecycle.
- [ ] Chạy thử trong JVM độc lập với production.
- [ ] Kiểm tra Java SE26 docs và target runtime thực tế.
- [ ] Không lưu fixture private key/certificate password thật trong git hoặc telemetry.

## 18. Câu hỏi ôn tập

**1. `SSLContext.setDefault(ctx)` ảnh hưởng ở phạm vi nào?**  
Một JVM/process, đối với các consumers lấy default từ điểm đó về sau.

**2. Nó có thay đổi mọi `HttpClient` đã tạo không?**  
Không. Java SE26 `HttpClient` nhận system defaults tại construction.

**3. Client mới sau `setDefault` có tự nhận context mới không?**  
Nếu không set explicit context, `HttpClient` mới dùng default tại thời điểm build.

**4. Một client dùng `Builder.sslContext(custom)` có bị global swap tác động không?**  
Không tự động; nó giữ context explicit.

**5. Có phải `SSLContext.getInstance("TLS")` cũng đổi default?**  
Không. Nó tạo context mới riêng.

**6. `SSLContext.getDefault()` lần đầu làm gì khi chưa setDefault?**  
Lấy `SSLContext.getInstance("Default")`, lưu và trả default context đã usable.

**7. Có thể gọi `SSLContext.setDefault(null)` để reset không?**  
Không. Ném `NullPointerException`.

**8. Default context mới phải có trạng thái gì?**  
Phải sẵn sàng sử dụng, đã init nếu cần.

**9. `HttpsURLConnection` lấy socket factory khi nào?**  
Thừa kế default static factory tại instance creation, có thể override trước connect.

**10. `HttpsURLConnection.setDefaultSSLSocketFactory` và `SSLContext.setDefault` là một không?**  
Không. Hai global settings độc lập.

**11. Đổi global SSLContext có buộc old HttpsURLConnection dùng factory mới không?**  
Không.

**12. Làm thế nào chỉ đổi TLS của một HttpsURLConnection?**  
Gọi `connection.setSSLSocketFactory(...)` trước connect.

**13. Có nên tắt hostname verification khi selfsigned certificate?**  
Không. Dùng cert có SAN hợp lệ và truststore phê duyệt.

**14. TrustManager và KeyManager khác nhau ở đâu?**  
TrustManager đánh giá peer; KeyManager cung cấp private key/certificate identity của phía mình.

**15. Vì sao `javax.net.ssl.trustStore` không phải runtime hot-reload switch đáng tin?**  
Default contexts/trust managers/clients có thể đã được tạo và cache.

**16. Tại sao một client cũ còn hoạt động sau khi global bị đổi lại?**  
Nó giữ SSLContext và có thể giữ TLS connections/sessions riêng.

**17. Truyền trust-all manager vào global gây rủi ro gì?**  
Có thể làm tất cả consumers mới dựa vào global chấp nhận certificate giả.

**18. Tại sao test trên localhost cần SAN cho `127.0.0.1`?**  
Để endpoint identity check hợp lệ theo IP URI, không cần disable verifier.

**19. Demo có gọi host bên ngoài Internet không?**  
Không. Chỉ mở HTTPS server trên 127.0.0.1 và tạo local truststore tạm.

**20. Tại sao nên chạy test global default trong một JVM riêng?**  
Vì global mutation và caches có thể ảnh hưởng threads/clients khác; restoring references không xóa mọi side effects.

**21. Thay global default có thay server SSLContext explicit không?**  
Không. `HttpsConfigurator(serverContext)` giữ config được cấp.

**22. Khi một trust anchor bị thu hồi, chỉ `setDefault` là đủ không?**  
Không. Cần cập nhật clients, old sessions/connections và có thể rolling restart.

**23. 40/40 PASS chứng minh mọi TLS library hành xử giống nhau không?**  
Không. Nó xác nhận JDK APIs, runtime OpenJDK24 và các tests đã chạy, cần integration tests đúng runtime/provider/framework khác.

## 19. Tài liệu chính thức Java SE 26

- [Java SE 26 — `SSLContext`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLContext.html): `getDefault`/`setDefault`, initialization, socket factories và SSLParameters.
- [Java SE 26 — `HttpClient`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.html): client immutable, system defaults được chụp khi construction, old clients không đổi khi setDefault, lifecycle APIs từ JDK21.
- [Java SE 26 — `HttpClient.Builder`](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): per-client `sslContext` và `sslParameters`.
- [Java SE 26 — `HttpsURLConnection`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html): class default `SSLSocketFactory`/`HostnameVerifier` và per-instance overrides.
- [Java SE 26 — `SSLSocketFactory`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLSocketFactory.html): factory `getDefault`, provider details và TLS socket creation.
- [Java SE 26 — `TrustManagerFactory`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): tạo trust managers từ một truststore.
- [Java SE 26 — `KeyManagerFactory`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html): tạo key managers từ key entries.
- [Java SE 26 — `KeyStore`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/KeyStore.html): lưu và truy cập keys/certificates.
- [Java SE 26 — `HttpsServer`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html): server HTTPS đơn giản của JDK.
- [Java SE 26 — `HttpsConfigurator`](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsConfigurator.html): explicit SSLContext cho HttpsServer.
- [Oracle Security Developer's Guide (2026) — Customizing JSSE](https://docs.oracle.com/en/java/javase/26/security/security-developer-guide.pdf): default key/trust stores, security properties, provider-specific defaults.
- [Java SE 26 — `SSLParameters`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLParameters.html): TLS protocol/cipher/endpoint-identification parameters.

**Kết luận:** `SSLContext.setDefault` là một **thay đổi cấu hình chia sẻ trong JVM**. Nó có thể làm những clients **được tạo mới** nhận trust policy mới, nhưng không tự cập nhật clients/sockets đã tạo và không tự đổi các mặc định static riêng của `HttpsURLConnection`. Để bảo đảm isolation, security, testability và rotation, hãy tạo `SSLContext` đã khởi tạo đúng truststore rồi **truyền explicit vào HTTP client hoặc HTTPS server cụ thể**. Chỉ dùng global default có chủ đích ở startup sau khi đã lập bản đồ consumers; không dùng global mutation như cơ chế đổi TLS trong request path.
