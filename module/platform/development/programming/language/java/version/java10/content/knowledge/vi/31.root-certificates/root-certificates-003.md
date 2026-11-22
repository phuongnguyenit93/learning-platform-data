# Keystore `cacerts` và quá trình lựa chọn truststore của JSSE trong Java

## 1. Mục tiêu bài học

**JSSE (Java Secure Socket Extension)** là nền tảng TLS/SSL trong Java, được các API như `SSLSocket`, `SSLEngine`, `HttpsURLConnection` và nhiều thư viện Java sử dụng trực tiếp hoặc gián tiếp. Khi kết nối TLS tới một máy chủ, phía client thường cần **xác minh chứng thư X.509** của máy chủ thông qua một tập **trust anchors** (chứng thư hoặc khóa công khai được tin cậy).

Tập thông tin tin cậy này có thể nằm trong **truststore**; ở các bản JDK phổ biến, keystore `cacerts` là nguồn CA gốc mặc định thường gặp. **Java 10 — JEP 319: Root Certificates** là một mốc quan trọng: đưa một bộ chứng thư CA gốc mặc định vào các bản dựng OpenJDK, nhằm tránh tình trạng một số bản dựng trước đó có `cacerts` rỗng làm TLS không xác minh được.

**Khái niệm này vẫn hiện hành.** Oracle JSSE Reference Guide của JDK 25 tiếp tục mô tả quá trình ưu tiên truststore:

1. Nếu **`javax.net.ssl.trustStore` được khai báo**, SunJSSE thử sử dụng giá trị đó.
2. Nếu **không khai báo**, tìm `java.home/lib/security/jssecacerts`.
3. Nếu không có `jssecacerts`, tìm `java.home/lib/security/cacerts`.
4. Nếu không có nguồn phù hợp, không có tập trust anchors mặc định hữu ích cho việc xác minh chứng thư máy chủ.

Điểm rất dễ sai: nếu **đã khai báo `javax.net.ssl.trustStore` nhưng file không tồn tại**, SunJSSE dùng một **truststore rỗng**, **không tự quay về `cacerts`**. Một cấu hình sai đường dẫn có thể làm hàng loạt kết nối HTTPS thất bại với lỗi xác thực chứng thư.

Bài học tập trung vào hành vi **SunJSSE/OpenJDK/Oracle HotSpot** được tài liệu hóa. JSSE có cơ chế **security provider**; nhà triển khai khác, thư viện tự tạo `SSLContext`, hoặc cấu hình TLS riêng của framework có thể dùng nguồn trust material khác. Không xem các property của SunJSSE là cam kết không thay đổi cho mọi implementation.

Sau bài này, bạn sẽ:

- Phân biệt **keyStore**, **trustStore**, **`cacerts`** và **`jssecacerts`**.
- Hiểu thứ tự SunJSSE tìm truststore mặc định, gồm trường hợp đường dẫn sai và truststore rỗng.
- Biết tác dụng của `javax.net.ssl.trustStore`, `trustStoreType`, `trustStorePassword`, `trustStoreProvider`.
- Biết tại sao **`KeyStore.getDefaultType()`** và **định dạng vật lý của file `cacerts`** không được tự đánh đồng.
- Dùng `keytool` xem CA gốc, kiểm tra fingerprint, tạo truststore riêng và nhập một CA doanh nghiệp được xác thực.
- Dùng `TrustManagerFactory.init((KeyStore) null)` với truststore mặc định và `init(customKeyStore)` khi điều khiển tường minh.
- Phân biệt lỗi trust chain, hostname, thiếu intermediate, disabled algorithms và sai TLS protocol.
- Chạy chương trình **Java 17+ độc lập**, không cần gọi mạng, để kiểm chứng behavior của `TrustManagerFactory`.
- Thiết kế cách quản lý truststore an toàn trong Docker/Kubernetes, CI và production.

## 2. Bốn thành phần không nên nhầm lẫn

| Thành phần | Chức năng | Ví dụ |
| --- | --- | --- |
| **`KeyStore`** | API/định dạng lưu keys và certificates; có thể chứa private keys, certificate chains hoặc trusted cert entries | File `server-identity.p12`, `truststore.p12` |
| **Truststore** | Vai trò của một keystore: lưu **trust anchors** mà bên xác minh chấp nhận | `cacerts`, `corp-trust.p12` |
| **Identity keystore** | Vai trò khác của keystore: lưu **private key** và certificate chain đại diện cho danh tính của chính bên này | `client-identity.p12` dùng trong mTLS |
| **`cacerts`** | Kho chứng thư CA gốc mặc định mà nhiều bản JDK cung cấp | `$JAVA_HOME/lib/security/cacerts` |

**Keystore** là khái niệm về **vật chứa/format/API**, còn **truststore** là **vai trò** của dữ liệu và cách JSSE sử dụng. Cả hai có thể được quản lý bằng `keytool`; khác nhau ở **nội dung, mục đích, manager và chính sách bảo mật**.

### Ví dụ luồng HTTPS hai chiều

~~~text
                        TLS handshake
Java HTTPS client                               HTTPS server
      |                                              |
      |<------ certificate chain của server --------|
      |                                              |
      |  TrustManager + truststore                    |
      |  → xây/kiểm tra certificate path             |
      |  → kiểm tra endpoint identity/hostname       |
      |                                              |
      |---- (nếu server yêu cầu mTLS) --------------->|
      |  KeyManager + identity keystore              |
      |  → chọn certificate + private key client     |
      |                                              |
      |<---------------- encrypted TLS --------------|
~~~

- **`TrustManager`** quyết định có tin chứng thư của **đối tác** hay không.
- **`KeyManager`** chọn chứng thư và **private key của chính mình** để cung cấp khi giao thức yêu cầu.
- Nếu client chỉ dùng HTTPS thông thường, thường **không cần** client private key.
- Trong **mTLS**, cả hai bên có thể cần **truststore** và **identity keystore** theo vai trò tương ứng.

Không dùng `javax.net.ssl.keyStore` để chữa vấn đề “Java không tin CA của server” khi thực chất cần bổ sung trust anchor. Hai property khác nhau có trách nhiệm khác nhau.

## 3. `cacerts`: chứng thư gốc từ JDK 10 đến hiện nay

**JEP 319 (JDK 10)** nhằm cung cấp tập CA gốc mặc định trong OpenJDK để tăng khả năng kết nối TLS mà không phải tự nhập toàn bộ các CA công khai. Điều này vẫn có ý nghĩa với ứng dụng Java hiện hành: phần lớn kết nối HTTPS công khai mong muốn được kiểm chứng qua một hoặc nhiều trust anchors tin cậy trong JDK.

Ở những bản JDK phổ biến:

~~~text
<java-home>/lib/security/cacerts
~~~

Trong lệnh shell Linux/macOS, thường thấy:

~~~bash
echo "$JAVA_HOME"
keytool -list -cacerts
~~~

**Cẩn thận:** `JAVA_HOME` là biến môi trường của terminal/build tool, **không bảo đảm trùng JVM đang chạy** trong một IDE, Gradle daemon, container hoặc service. Tại runtime, `System.getProperty("java.home")` cho biết Java runtime home mà tiến trình đang sử dụng.

Một số bản phân phối Linux có thể dùng **symlink** tới CA store do OS quản lý hoặc có quy trình tích hợp chứng thư khác. Bộ CA gốc cũng thay đổi theo **vendor, JDK version, security updates và chính sách CA distrust**.

Vì vậy:

- **Không khẳng định một số lượng CA cố định** như “mọi JDK có 100 chứng thư”.
- **Không tin rằng OS truststore và JDK `cacerts` luôn là một**.
- **Không giả định** update JDK sẽ giữ nguyên từng trust anchor.
- **Không sửa file `cacerts` của JDK bằng cách import CA không được xác minh**.
- Không mặc nhiên xem mọi CA trong `cacerts` đều được chấp nhận cho mọi trường hợp: còn có **cert-path policies, key size, signature algorithm, CA distrust, EKU và hostname validation**.

### `jssecacerts`: truststore ưu tiên riêng cho JSSE

JSSE còn nhận một file tên **`jssecacerts`**, thường nằm cùng directory:

~~~text
<java-home>/lib/security/jssecacerts
~~~

Nó có độ ưu tiên **cao hơn `cacerts`** khi **không có `javax.net.ssl.trustStore`**.

Nếu `jssecacerts` tồn tại, SunJSSE chọn **file đó** theo quy tắc mặc định. Đây **không phải một thao tác hợp nhất tự động** với `cacerts`. Nếu `jssecacerts` thiếu các public CAs cần thiết, kết nối tới website công khai có thể thất bại dù `cacerts` vẫn chứa các CA đó.

Trong phần lớn hệ thống hiện đại, **dùng truststore riêng được quản lý minh bạch cho từng ứng dụng** thường dễ kiểm toán hơn việc sửa file hệ thống `jssecacerts` hoặc `cacerts`. Tuy vậy, thứ tự tìm `jssecacerts` vẫn cần biết để chẩn đoán.

## 4. Quy tắc lựa chọn truststore của SunJSSE

Với **SunJSSE `PKIX` hoặc `SunX509` TrustManagerFactory** khi gọi:

~~~java
TrustManagerFactory factory =
        TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
        );
factory.init((KeyStore) null);
~~~

đối số `null` bảo factory tự tìm nguồn trust material theo **cấu hình mặc định của SunJSSE**.

Quá trình chọn có thể diễn đạt:

~~~text
SunJSSE cần default trust material
                  |
                  v
System property javax.net.ssl.trustStore có được khai báo?
         /                                \
       CÓ                                 KHÔNG
        |                                    |
        v                                    v
Kiểm tra đường dẫn hoặc                 Có file jssecacerts?
provider token được chỉ định             /           \
        |                               CÓ          KHÔNG
        |                                |             |
        v                                v             v
File hợp lệ?                       Dùng jssecacerts  Có cacerts?
 /         \                                         /        \
CÓ        KHÔNG                                     CÓ       KHÔNG
 |           |                                       |          |
 v           v                                       v          v
Dùng file  Truststore rỗng                        Dùng cacerts   Truststore
đó        (không fallback)                                     rỗng
~~~

**Điều kiện ở nhánh explicit:** ký hiệu `NONE` là trường hợp đặc biệt dành cho trust material **không nằm trong file** như PKCS#11 token khi được provider hỗ trợ; không nên xử lý nó như đường dẫn tệp bình thường.

Nếu file explicit có tồn tại nhưng **mật khẩu, định dạng hoặc nội dung không hợp lệ**, quá trình tải truststore có thể thất bại bằng ngoại lệ. Không khẳng định JSSE sẽ âm thầm bỏ file lỗi để quay về `cacerts`.

### 4.1. Không có property — ưu tiên `jssecacerts`, rồi `cacerts`

~~~bash
java -jar app.jar
~~~

Trên JVM và thư viện thực sự sử dụng default SunJSSE, thứ tự tìm là:

~~~text
<runtime-home>/lib/security/jssecacerts
<runtime-home>/lib/security/cacerts
~~~

Khi cả hai cùng tồn tại, **`jssecacerts` thắng**. Khi chỉ có `cacerts`, nó được dùng. Không phải JSSE luôn tự hợp nhất mọi nguồn CA của JDK, OS và truststore ứng dụng.

### 4.2. Có property trỏ đúng file

~~~bash
java -Djavax.net.ssl.trustStore=/opt/app/security/truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12 -jar app.jar
~~~

Đây là ví dụ **đường dẫn truststore riêng đã được chuẩn bị hợp lệ**. Nếu keystore được bảo vệ bằng mật khẩu, cần cung cấp/cấu hình `javax.net.ssl.trustStorePassword` theo cơ chế bảo mật thích hợp của runtime và xác minh nó đọc được file. Không đặt mật khẩu production trực tiếp trong một script hoặc command line dễ bị lộ.

**Lưu ý lớn:** property chỉ định truststore riêng **thay thế lựa chọn mặc định**, chứ **không tự nhập thêm CA mới vào `cacerts` và cũng không tự gộp hai tập CA**.

### 4.3. Có property nhưng file sai

~~~bash
java -Djavax.net.ssl.trustStore=/opt/app/security/missing-store.p12 -jar app.jar
~~~

Nếu đường dẫn này không tồn tại, SunJSSE mặc định tạo **trust manager dựa trên empty truststore**, **không fallback tới `jssecacerts` hay `cacerts`**. HTTPS cần xác thực chứng thư thường thất bại.

Đây là lý do lỗi **sai đường dẫn file** có thể xuất hiện giống lỗi **không tin CA**. Đừng vội import một chứng thư bừa bãi; trước hết xác minh file có thật và đúng JVM đã đọc nó.

### 4.4. Không có file mặc định

Nếu `javax.net.ssl.trustStore` **không có**, `jssecacerts` **không có**, `cacerts` **không có**, default SunJSSE cũng không có tập trust anchors từ file đó.

Đối với kết nối HTTPS hiện đại xác thực server, thiếu trust anchors là cấu hình không thể dùng để xác minh chuỗi chứng thư như mong muốn. **Không** tìm cách sử dụng anonymous cipher suites hoặc tắt xác thực như giải pháp; hãy cung cấp truststore hợp lệ.

## 5. Bảng quyết định và các trường hợp thường gặp

| `javax.net.ssl.trustStore` | `jssecacerts` | `cacerts` | Nguồn mặc định của SunJSSE |
| --- | --- | --- | --- |
| Không đặt | Không có | Có | `cacerts` |
| Không đặt | Có | Có | `jssecacerts` |
| Không đặt | Có | Không có | `jssecacerts` |
| Không đặt | Không có | Không có | Không có trust anchors từ file mặc định |
| Trỏ tới file hợp lệ | Bất kỳ | Bất kỳ | **File explicit** |
| Trỏ tới file không tồn tại | Có | Có | **Empty truststore**, không fallback |
| Trỏ tới file có type/password sai | Bất kỳ | Bất kỳ | Có thể **khởi tạo thất bại**, không phải tự quay về `cacerts` |
| `NONE` với provider phù hợp | Bất kỳ | Bất kỳ | Trust material **không dựa trên file** theo provider |

Đây là quy tắc **SunJSSE reference implementation**, không phải bộ quy tắc có thể áp dụng cho mọi TLS client hoặc một `SSLContext` đã được chương trình khởi tạo với custom trust managers.

### Tình huống 1 — container không có CA mong đợi

Ứng dụng chạy trên laptop nhưng fail HTTPS trong container. Những giả thuyết:

- JDK runtime/container image khác phiên bản hoặc khác vendor.
- Image có `jssecacerts` riêng thiếu root cần thiết.
- `javax.net.ssl.trustStore` trỏ tới file chỉ tồn tại ở laptop.
- Corporate root CA chỉ có trong OS trust store, chưa có trong trust material mà Java chọn.
- Cert chain của server khác khi đi qua corporate proxy/TLS inspection.

Cách chẩn đoán: xem **runtime thực tế + truststore file + TLS debug**, không giả định hai image tự có cùng trust anchors.

### Tình huống 2 — app truststore chỉ chứa CA nội bộ

Một service khai báo `corp-trust.p12` chỉ có **CA công ty**. Các kết nối tới service nội bộ có thể hoạt động, nhưng các HTTPS public endpoints trước đây được `cacerts` tin cậy có thể **thất bại**.

Nguyên nhân: explicit truststore **không tự gộp** với `cacerts`. Nếu cần cả hai nguồn, phải xây dựng trust policy/keystore hợp nhất có kiểm soát, hoặc quản lý riêng các `SSLContext`/clients theo truststore thích hợp.

### Tình huống 3 — nhập chứng thư server bất kỳ vào global `cacerts`

Khi thấy handshake fail, một người lấy leaf certificate từ endpoint và nhập toàn cục, rồi gọi đó là “sửa TLS”.

Vấn đề:

- Leaf certificate có thể thay khi rotation; nhập từng leaf không giải quyết quản trị CA bền vững.
- Nếu không kiểm tra fingerprint bằng kênh tin cậy, có thể nhập chứng thư do kẻ tấn công cung cấp.
- Tăng trust scope toàn bộ JDK có thể làm các ứng dụng khác trong cùng runtime tin thêm CA.
- Lỗi thật có thể là hostname mismatch, thiếu intermediate hoặc certificate expired, không chỉ thiếu CA.

Ưu tiên **xác minh PKI chain đúng**, cấp phát một CA nội bộ đáng tin, và cập nhật truststore có scope nhỏ nhất cần thiết.

## 6. Các thuộc tính JSSE và vai trò của chúng

| System property | Vai trò | Lưu ý |
| --- | --- | --- |
| `javax.net.ssl.trustStore` | File hoặc token truststore mặc định | Có giá trị explicit thì không theo nhánh tìm `jssecacerts`/`cacerts` |
| `javax.net.ssl.trustStoreType` | Kiểu `KeyStore` khi đọc truststore | Ví dụ `PKCS12`, `JKS`, hoặc provider-specific |
| `javax.net.ssl.trustStorePassword` | Mật khẩu giúp kiểm tra integrity/mở truststore | Không in hoặc nhúng mật khẩu thật vào script/log |
| `javax.net.ssl.trustStoreProvider` | Chỉ định provider keystore khi cần | Thường không cần ở cấu hình file thông dụng |
| `javax.net.ssl.keyStore` | File chứa danh tính **local** | Dành cho `KeyManager`, không phải remote trust |
| `javax.net.ssl.keyStoreType` | Format identity keystore | Thường là PKCS12 trong ứng dụng mới |
| `javax.net.ssl.keyStorePassword` | Mật khẩu identity keystore | Bảo vệ/private keys; không log |
| `javax.net.ssl.keyStoreProvider` | Provider identity store | Có thể dùng với token/provider riêng |
| `javax.net.debug` | JSSE debug/tracing | `ssl,handshake,trustmanager` khi điều tra |
| `java.security.debug` | Security/cert-path debug | `certpath` để xem quá trình dựng/kiểm tra chuỗi |

Các thuộc tính `javax.net.ssl.*` liệt kê ở trên là **Java system properties** (truyền qua `-D`). Trong khi đó `ssl.TrustManagerFactory.algorithm`, `keystore.type`, `jdk.certpath.disabledAlgorithms` là **security properties** của Java Security subsystem.

Không đánh đồng:

~~~text
-Djavax.net.ssl.trustStore=/path/to/file     Java system property
ssl.TrustManagerFactory.algorithm=PKIX       Java security property
~~~

Security properties thường đặt trong:

~~~text
<java-home>/conf/security/java.security
~~~

Với JDK hiện hành, thuật toán mặc định của `TrustManagerFactory` trong SunJSSE thường là **PKIX**, nhưng đừng hard-code điều đó trong portable code: dùng `TrustManagerFactory.getDefaultAlgorithm()` để xem giá trị của runtime.

## 7. `PKCS12`, `JKS` và định dạng file `cacerts`

Từ **JDK 9 (JEP 229)**, kiểu keystore mặc định cho nhiều thao tác mới là **PKCS12**. Bạn có thể kiểm tra:

~~~java
System.out.println(KeyStore.getDefaultType());
~~~

Tuy nhiên, **không được suy luận**:

~~~text
KeyStore.getDefaultType() == "pkcs12"
    ⇒ mọi file cacerts đều là PKCS12
~~~

Đó là hai câu hỏi khác nhau:

1. **Default type** mà Java dùng khi code/app không chọn rõ format.
2. **Actual format** của một file keystore đã được JDK/vendor phát hành.

File `cacerts` có thể có định dạng khác nhau theo vendor, build hoặc cách đóng gói; một số implementation hỗ trợ **compatibility detection** để đọc JKS/PKCS12. Cách an toàn hơn là dùng `keytool -cacerts` hoặc kiểm tra file cụ thể thay vì suy từ phần mở rộng.

### Xem keystore đang được dùng

~~~bash
keytool -list -cacerts
~~~

Với một CA alias đã biết:

~~~bash
keytool -list -v -cacerts -alias corp-root
~~~

Dòng thứ hai **chỉ hoạt động nếu alias `corp-root` thực sự tồn tại** trong `cacerts` của JDK đang gọi. Tên alias là định danh do người quản trị đặt; không phải CA nào cũng có tên cố định.

Các file truststore dùng riêng có thể được liệt kê như sau:

~~~bash
keytool -list -keystore /opt/app/security/truststore.p12 -storetype PKCS12
~~~

Nếu keystore được bảo vệ, `keytool` có thể hỏi mật khẩu tương ứng. Tránh dùng `-storepass` với mật khẩu thật trong lịch sử shell hoặc CI logs.

### Mật khẩu mặc định `cacerts` có phải một bí mật mạnh?

Một số JDK phát hành `cacerts` với **mật khẩu khởi tạo thông dụng `changeit`**. Mật khẩu này **không phải một bí mật bảo mật private key của server** (thường không có private key trong root-CA truststore). Nó phục vụ chính sách truy cập/integrity của keystore; không thay thế **file ownership, permissions và kiểm soát supply chain**.

Đừng giả định mật khẩu thực tế luôn là `changeit`: nhà phân phối hoặc đội quản trị có thể đã thay đổi. Và đừng public mật khẩu của **truststore riêng chứa tài liệu/chứng thư nội bộ** trong startup flags.

## 8. Cơ chế `TrustManagerFactory` và `SSLContext`

**JSSE chọn trust material khi tạo/khởi tạo trust managers**, rồi dùng các trust managers đó trong `SSLContext` để xác minh chứng thư.

Dạng cơ bản:

~~~java
TrustManagerFactory factory =
        TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
        );

factory.init((KeyStore) null);
TrustManager[] managers = factory.getTrustManagers();

SSLContext context = SSLContext.getInstance("TLS");
context.init(null, managers, null);
~~~

Đây là **đoạn minh họa trong một phương thức**, cần imports tương ứng và xử lý các checked exceptions.

Ở đây:

- `factory.init((KeyStore) null)`: yêu cầu provider lấy **default trust material**.
- `getTrustManagers()`: lấy các manager phù hợp đã được factory tạo.
- `SSLContext.getInstance("TLS")`: chọn họ giao thức TLS được provider hỗ trợ; **không bắt buộc cố định một protocol TLS lỗi thời**.
- `context.init(null, managers, null)`: không cấp identity key managers tường minh; dùng trust managers đã tạo và secure random mặc định.

### Trường hợp dùng truststore riêng trong code

~~~java
KeyStore custom = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(
        Path.of("/opt/app/security/truststore.p12"))) {
    custom.load(in, password);
}

TrustManagerFactory factory =
        TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
        );
factory.init(custom);

SSLContext context = SSLContext.getInstance("TLS");
context.init(null, factory.getTrustManagers(), null);
~~~

Đây cũng là **đoạn minh họa**: `password` cần được cấp từ nơi bảo vệ bí mật, và `Files`/`Path`/`InputStream` cần imports; không phải chương trình độc lập.

**Điểm mấu chốt:** `init(custom)` nhận **KeyStore explicit**. Đó là cách ứng dụng điều khiển riêng trust anchors của context mà không cần lệ thuộc quyết định chọn default truststore.

### Tại sao thay property sau khi ứng dụng chạy có thể không có tác dụng?

Các default context, trust managers, HTTP connection pools và security properties có thể được khởi tạo/cached **trước** khi chương trình cập nhật một system property.

~~~java
System.setProperty(
        "javax.net.ssl.trustStore",
        "/opt/app/security/new-truststore.p12"
);
~~~

Gọi dòng trên **sau khi default `SSLContext`/trust managers đã hình thành** không bảo đảm những đối tượng cũ tự tải lại dữ liệu. Khi triển khai:

- Cấu hình trước khi tạo TLS clients/contexts.
- Với service chạy lâu, **restart hoặc tạo lại context/client có kiểm soát** sau khi rotate trust material.
- Đừng giả định chỉ thay file dưới cùng đường dẫn sẽ tự refresh các TLS pools đang hoạt động.
- Framework có **TLS configuration riêng** có thể không dùng global properties; đọc hướng dẫn framework đó.

## 9. Chương trình Java 17+ độc lập: kiểm tra mặc định và truststore rỗng

Lưu file **JSSETrustStoreDemo.java**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;

import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManager;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.X509TrustManager;

public final class JSSETrustStoreDemo {
    private static X509TrustManager findX509(
            TrustManager[] managers) {

        for (TrustManager manager : managers) {
            if (manager instanceof X509TrustManager) {
                return (X509TrustManager) manager;
            }
        }

        throw new IllegalStateException(
                "No X509TrustManager available"
        );
    }

    private static void fixture() throws Exception {
        KeyStore empty = KeyStore.getInstance("PKCS12");
        empty.load(null, new char[0]);

        TrustManagerFactory factory =
                TrustManagerFactory.getInstance(
                        TrustManagerFactory.getDefaultAlgorithm()
                );
        factory.init(empty);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(
                null,
                factory.getTrustManagers(),
                null
        );

        System.out.println("fixture type: " + empty.getType());
        System.out.println("fixture entries: " + empty.size());
        System.out.println("fixture accepted issuers: "
                + findX509(
                    factory.getTrustManagers()
                ).getAcceptedIssuers().length);
        System.out.println("context protocol: "
                + context.getProtocol());
    }

    private static void inspect() throws Exception {
        String explicit = System.getProperty(
                "javax.net.ssl.trustStore"
        );

        Path security = Path.of(
                System.getProperty("java.home"),
                "lib", "security"
        );

        System.out.println("explicit trustStore set: "
                + (explicit != null));
        System.out.println("jssecacerts exists: "
                + Files.isRegularFile(
                    security.resolve("jssecacerts")
                ));
        System.out.println("cacerts exists: "
                + Files.isRegularFile(
                    security.resolve("cacerts")
                ));

        TrustManagerFactory factory =
                TrustManagerFactory.getInstance(
                        TrustManagerFactory.getDefaultAlgorithm()
                );
        factory.init((KeyStore) null);

        System.out.println("default accepted issuers: "
                + findX509(
                    factory.getTrustManagers()
                ).getAcceptedIssuers().length);
    }

    public static void main(String[] args) throws Exception {
        String mode = args.length == 0
                ? "fixture" : args[0];

        if ("fixture".equals(mode)) {
            fixture();
        } else if ("inspect".equals(mode)) {
            inspect();
        } else {
            throw new IllegalArgumentException(
                    "Use fixture or inspect"
            );
        }
    }
}
~~~

Biên dịch trên JDK 17+:

~~~bash
javac JSSETrustStoreDemo.java
~~~

### 9.1. Chế độ `fixture`: đầu ra xác định, không dùng mạng

~~~bash
java JSSETrustStoreDemo fixture
~~~

Stdout đã được xác minh bằng OpenJDK:

~~~text
fixture type: PKCS12
fixture entries: 0
fixture accepted issuers: 0
context protocol: TLS
~~~

Đây là một **PKCS12 keystore rỗng tạo trong bộ nhớ**, rồi đưa trực tiếp vào `TrustManagerFactory.init(empty)`. Vì không có chứng thư nào làm trust anchor, `getAcceptedIssuers()` của trust manager thu được có độ dài **0**.

**Quan trọng về bảo mật:** đây **chỉ là minh họa cách truststore rỗng hoạt động**, không phải cấu hình TLS dùng trong sản xuất. Một context có 0 trust anchors không thể dùng để xác thực thông thường các server public qua một CA chain mà nó không tin.

Đoạn code **không** mở socket, không gửi request HTTP, không tạo chứng thư CA giả và không disable validation.

### 9.2. Chế độ `inspect`: xem default runtime thực

~~~bash
java JSSETrustStoreDemo inspect
~~~

Chương trình:

1. Xác định có khai báo explicit `javax.net.ssl.trustStore` hay không.
2. Kiểm tra hai vị trí `jssecacerts` và `cacerts` trong **`java.home` của runtime**.
3. Gọi `factory.init((KeyStore) null)` để SunJSSE tìm default trust material.
4. In số chứng thư được trust manager trả về trong `getAcceptedIssuers()`.

**Không có stdout cố định cho chế độ inspect**: file hiện diện, provider và số lượng accepted issuers thay đổi theo JDK/vendor/cấu hình. Số accepted issuers chỉ là một chỉ báo, không thay thế kiểm tra chi tiết các trust anchors và chính sách validation.

### 9.3. Thử explicit truststore path không tồn tại

Trên môi trường test, giả sử đường dẫn này không có:

~~~bash
java -Djavax.net.ssl.trustStore=/tmp/no-such-jsse-truststore.p12 JSSETrustStoreDemo inspect
~~~

Với SunJSSE, factory mặc định không tự quay về `cacerts` khi property explicit chỉ file không tồn tại. Trong các cấu hình điển hình, bạn sẽ thấy:

~~~text
explicit trustStore set: true
~~~

và số accepted issuers có thể bằng 0. Đừng in một stdout đầy đủ được khẳng định bất biến: đường dẫn, JDK/provider và các trường hợp đặc biệt ảnh hưởng kết quả.

**Chỉ thực hiện phép thử này ở môi trường test**. Đừng vô tình áp dụng truststore rỗng lên service production, vì nó có thể khiến tất cả HTTPS outbound connections cần server authentication thất bại.

### 9.4. Hạn chế của phép `Files.isRegularFile`

Phương thức `Files.isRegularFile` cho biết một đường dẫn có biểu hiện là file thông thường tại thời điểm kiểm tra, **không chứng minh JSSE đã đọc hoặc dùng chính file đó**.

Các nguyên nhân:

- `javax.net.ssl.trustStore` explicit có thể chỉ file khác.
- `NONE` với PKCS#11 provider không theo đường đọc file.
- Provider riêng có cách chọn trust material khác.
- `SSLContext` của framework có thể đã được tạo bằng custom trust managers.
- File có thể bị thay/permission thay đổi giữa lúc kiểm tra và lúc init.

Do đó phép kiểm tra trong `inspect` phải được kết hợp **JSSE debug logs** và thông tin kết nối thực tế khi điều tra lỗi TLS.

## 10. Dùng `keytool` xem và xác minh chứng thư CA

### 10.1. Xem hệ thống root CAs của JDK

~~~bash
keytool -list -cacerts
~~~

Với thông tin chi tiết hơn:

~~~bash
keytool -list -v -cacerts
~~~

Danh sách chứng thư có thể dài. `keytool -cacerts` tham chiếu **`cacerts` của JDK sở hữu executable `keytool` đang được gọi**, vì vậy hãy kiểm tra `which keytool` và `java -version` trên Linux/macOS hoặc `where.exe keytool` trên Windows nếu nghi có nhiều JDK.

**Không** công bố toàn bộ aliases/fingerprints giả định, vì mỗi JDK update/vendor có thể dùng danh sách khác nhau.

### 10.2. In chứng thư CA được cấp qua file

~~~bash
keytool -printcert -file /opt/app/certs/corp-root.pem -v
~~~

Lệnh này hiển thị thông tin như **Subject, Issuer, Validity, SHA-256 fingerprint, key algorithm** (tùy file/phiên bản keytool).

Trước khi import root CA nội bộ, xác minh **SHA-256 fingerprint qua kênh tin cậy độc lập** từ đội PKI/cơ quan cấp chứng thư. Không lấy chứng thư chưa được xác minh từ một kết nối TLS đang lỗi rồi tự động nhập vào truststore.

### 10.3. Tạo truststore riêng cho ứng dụng

Khi đã có file CA được kiểm tra fingerprint, dùng ví dụ:

~~~bash
keytool -importcert -alias corp-root -file /opt/app/certs/corp-root.pem -keystore /opt/app/security/truststore.p12 -storetype PKCS12
~~~

`keytool` có thể hỏi mật khẩu keystore và hỏi xác nhận trust certificate. Khi keystore chưa tồn tại, thao tác này có thể tạo file keystore mới theo định dạng đã chỉ rõ.

**Trước khi thực hiện**, đảm bảo thư mục `/opt/app/security` tồn tại, user có quyền ghi phù hợp và chứng thư được đội PKI cho phép tin cậy.

Xác minh alias vừa nhập:

~~~bash
keytool -list -v -keystore /opt/app/security/truststore.p12 -storetype PKCS12 -alias corp-root
~~~

**Không bỏ qua bước kiểm tra SHA-256 fingerprint** và mục đích sử dụng của chứng thư. Nhập một root CA có phạm vi lớn sẽ cho phép các chain dưới CA đó được xét tin cậy trong những ngữ cảnh mà các kiểm tra khác cho phép.

### 10.4. Không sửa `cacerts` của JDK làm cách duy nhất

Sửa trực tiếp `cacerts` hệ thống có các nhược điểm:

- Thay đổi ảnh hưởng **mọi ứng dụng** dùng JDK đó.
- Có thể mất hoặc bị ghi đè khi thay runtime/container image.
- Cần quyền quản trị và dễ gây khó khăn khi rollback.
- Giảm khả năng truy vết CA được một ứng dụng cụ thể tin cậy.

Một **truststore ứng dụng riêng, version hóa và triển khai cùng service** thường dễ kiểm soát hơn. Nếu quy trình bắt buộc chỉnh global `cacerts`, cần quản lý qua hệ thống cấu hình/PKI chính thức, kiểm tra trust anchors và cập nhật phù hợp khi nâng JDK.

## 11. Truststore riêng không tự hợp nhất với bộ CA công khai

Một lỗi thực tế:

~~~bash
java -Djavax.net.ssl.trustStore=/opt/app/security/corp-only.p12 -jar app.jar
~~~

Giả sử `corp-only.p12` chỉ có một CA nội bộ, còn JDK `cacerts` chứa nhiều public CAs. SunJSSE sử dụng **corp-only** làm nguồn trust material explicit; các public CAs **không tự được nhập thêm**.

**Nếu ứng dụng cần tin cả CA nội bộ và CA công khai**, có các thiết kế:

1. **Tạo truststore hợp nhất có kiểm soát**, bắt đầu từ bộ CA gốc đáng tin đúng phiên bản JDK và thêm CA nội bộ đã xác minh.
2. **Dùng các `SSLContext` riêng** cho từng client/đích, mỗi context có trust anchors và endpoint policy phù hợp.
3. Nếu framework hỗ trợ, dùng **truststore composition** được cung cấp rõ ràng bởi framework/provider.
4. Với ứng dụng không cần public CAs, **giới hạn truststore** chỉ chứa CAs cần thiết có thể là chính sách đúng và hẹp hơn.

Không nên tự viết một trust manager kiểu “chấp nhận nếu một trong hai trust manager không ném lỗi” mà không hiểu đầy đủ **PKIX, algorithm constraints, hostname validation, accepted issuers và TLS handshake context**. Thư viện TLS/provider chuẩn và cách thiết kế được review bảo mật là lựa chọn an toàn hơn.

### Khi build keystore hợp nhất

Nếu quyết định hợp nhất `cacerts` và CA công ty, phải bảo đảm:

- Nguồn `cacerts` đúng **JDK build** mà deployment dùng.
- Fingerprints và danh sách CA được phê duyệt.
- Alias không trùng hoặc ghi đè trust entries ngoài ý muốn.
- Có quy trình cập nhật khi root CA bị thu hồi/không còn được tin cậy.
- Có kiểm thử HTTPS public và corporate endpoints trước khi phát hành.

Không được coi việc “copy một lần mãi mãi” là quản lý CA đủ tốt; root certificates và chính sách thuật toán thay đổi theo thời gian.

## 12. Chứng thư hợp lệ còn cần những điều kiện nào?

Truststore giúp chọn **trust anchors**, nhưng TLS certificate validation không phải phép kiểm tra “alias có tồn tại trong `cacerts`”.

Với một kết nối HTTPS, những việc liên quan có thể gồm:

1. **Server gửi certificate chain** phù hợp (leaf và các intermediates cần thiết).
2. Certificate path có thể được xây dựng tới **một trust anchor** chấp nhận được.
3. Chứng thư và chuỗi thỏa **thời hạn hiệu lực**, mục đích sử dụng, basic constraints, key usage/EKU và các quy tắc PKIX liên quan.
4. Thuật toán chữ ký và key sizes thỏa **`jdk.certpath.disabledAlgorithms`** và các chính sách JDK đang áp dụng.
5. Với HTTPS, **hostname/endpoint identity** khớp Subject Alternative Name phù hợp.
6. TLS protocol/cipher suites được hai bên hỗ trợ theo **`jdk.tls.disabledAlgorithms`** và cấu hình thực.
7. Nếu chính sách yêu cầu, có thể có kiểm tra **revocation/CRL/OCSP**, không mặc định rằng tất cả revocation checks luôn bật trong mọi cấu hình.

Vì thế, **có CA gốc trong `cacerts` không bảo đảm mọi chứng thư do CA đó cấp đều được chấp nhận**. Ví dụ hostname không khớp vẫn phải bị từ chối ở HTTPS có endpoint identification.

### Trust chain khác hostname verification

- **Trust validation:** “Chứng thư có dẫn tới một trust anchor phù hợp theo chính sách hay không?”
- **Hostname validation:** “Chứng thư có được cấp cho hostname mà tôi thực sự kết nối hay không?”

Không giải quyết lỗi hostname bằng cách **tắt `HostnameVerifier`** hoặc tạo `X509TrustManager` luôn trả success. Những mẹo này làm mất bảo vệ MITM và không phù hợp với ứng dụng hiện đại.

Với **raw `SSLSocket` hoặc `SSLEngine`** tự điều khiển TLS cho một ứng dụng HTTPS, bạn cần cấu hình endpoint identification đúng bối cảnh; các HTTPS clients chuẩn thường đã thiết lập chính sách hostname theo API của chúng.

## 13. Gỡ lỗi TLS: tìm truststore nào đã được chọn

### 13.1. Bật JSSE debug có kiểm soát

~~~bash
java -Djavax.net.debug=ssl,handshake,trustmanager -jar app.jar
~~~

Trong log, tìm thông tin:

- Truststore được nạp, đường dẫn, loại store và danh sách certificates được tin cậy.
- Certificate chain server gửi.
- Nguyên nhân `CertificateException`, `SSLHandshakeException`.
- Bước kiểm tra của trust manager.

**Không gắn cứng một đoạn debug output** vì format, thread IDs, aliases và nội dung có thể thay đổi giữa phiên bản JDK/provider.

Khi cần xem chi tiết cert-path:

~~~bash
java -Djava.security.debug=certpath -jar app.jar
~~~

Hoặc kết hợp hai tùy chọn trong **môi trường kiểm thử** nếu cần:

~~~bash
java -Djavax.net.debug=ssl,handshake,trustmanager -Djava.security.debug=certpath -jar app.jar
~~~

**Không bật `javax.net.debug=all` hay logging plaintext/packet cho production thường trực**: log có thể rất lớn và chứa thông tin về endpoints, certificate chains, metadata kết nối, hoặc dữ liệu nhạy cảm tùy chế độ.

### 13.2. Kiểm tra JVM thật đang chạy

Trên Linux/macOS:

~~~bash
java -version
which java
which keytool
echo "$JAVA_HOME"
~~~

Với JVM đang chạy và quyền attach phù hợp:

~~~bash
jcmd 1 VM.system_properties
~~~

Trong container, JVM có thể là PID 1, nhưng **không bảo đảm**. Thay `1` bằng PID Java thực tế.

**Cảnh báo:** `VM.system_properties` có thể hiển thị **các property chứa bí mật**, kể cả `javax.net.ssl.trustStorePassword` nếu được cấu hình theo cách không an toàn. Không dán toàn bộ output công khai; chỉ trích các property **không nhạy cảm** cần để chẩn đoán.

### 13.3. Vì sao `keytool` kiểm tra file A nhưng ứng dụng dùng file B?

- Shell `keytool` thuộc một JDK, còn process Java thuộc JDK khác.
- IDE/build tool/Gradle daemon có runtime riêng.
- Explicit `javax.net.ssl.trustStore` chỉ file khác `cacerts`.
- `jssecacerts` có mặt và được ưu tiên.
- Container mount path khác host path.
- Framework tạo custom `SSLContext` hoặc dùng trust settings riêng.
- TLS process đã khởi tạo trust managers trước khi file/property thay đổi.

Hãy so **runtime home, startup system properties, provider và debug** trong **đúng tiến trình gặp lỗi**, không chỉ dựa vào những gì terminal hiện tại in.

## 14. Ma trận lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng chẩn đoán an toàn |
| --- | --- | --- |
| `PKIX path building failed` | Không dựng được chain tới trust anchor theo policy | Kiểm tra path truststore, CA root/intermediate, debug certpath |
| `trustAnchors parameter must be non-empty` | Empty/default truststore hoặc không có trust anchors hợp lệ | Kiểm tra explicit path không tồn tại, file rỗng/không đọc được |
| `No subject alternative DNS name matching` | **Hostname mismatch** | Sửa cert SAN/hostname; **không** tắt verification |
| `certificate expired` | Leaf/intermediate hết hạn hoặc clock sai | Kiểm tra chain validity và system time |
| `Algorithm constraints check failed` | Key/signature/algorithm bị cấm bởi security policy | Cấp lại cert/key hiện đại; không hạ thấp chính sách bừa bãi |
| `Keystore was tampered with, or password was incorrect` | Sai mật khẩu hoặc file/type không đúng; text lỗi tùy JDK | Kiểm tra format/password/integrity, không in secret |
| `Invalid keystore format` | File không đúng loại hoặc bị hỏng | `keytool -list` với `-storetype` đúng |
| HTTPS trong IDE chạy, trong container fail | JDK/truststore/cert chain hoặc corporate proxy khác | Xem runtime home, mount, trustStore property |
| Custom CA hoạt động, public website fail | File explicit chỉ có private CA | Thiết kế truststore phù hợp, không giả định merge `cacerts` |
| HTTPS fail ngay sau đổi cert | Thiếu intermediate, rotation/issuer khác, truststore chưa cập nhật | Xem chain, fingerprints, CA policy, restart clients nếu cần |
| mTLS server từ chối client certificate | Thiếu/sai identity keyStore hoặc cert client | Kiểm tra `KeyManager`, private key, client cert chain |
| Sau JDK update CA bị từ chối | Root removed/distrusted, disabled algorithm hoặc chính sách thay đổi | Đọc release notes/security properties; không restore CAs bị distrust bừa bãi |

**Đừng khắc phục bằng cách vô hiệu hóa TLS certificate checks.** Một số đoạn code trên internet tạo `TrustManager` có `checkServerTrusted` rỗng hoặc `HostnameVerifier` trả true cho mọi hostname. Đó là hành vi **bỏ xác thực danh tính server**, mở đường cho tấn công man-in-the-middle.

## 15. Phân biệt `PKIX path building failed` với thiếu root CA

Ví dụ một website public trình bày:

~~~text
Leaf certificate → Intermediate CA → Root CA
~~~

Phía server trong TLS thông thường gửi leaf và những intermediate cần thiết, còn client có thể đã tin root CA từ truststore. Một số root có thể không cần được server gửi nếu client đã có trust anchor.

Khi thấy `PKIX path building failed`, các tình huống gồm:

1. Root CA **chưa có** trong truststore.
2. Server gửi **thiếu intermediate** hoặc chain không khớp.
3. Truststore được chỉ định sai hoặc rỗng.
4. Certificate path có thể đi tới một root nhưng bị loại bởi **constraints/policies**.
5. TLS interception proxy thay certificate chain bằng CA riêng chưa được phê duyệt.
6. Certificate path khác đi sau một lần rotation/update JDK.

**Không cứ thấy PKIX là nhập leaf certificate vào global `cacerts`.** Kiểm tra chain thật, root CA được tổ chức chấp thuận và nguyên nhân cụ thể. Một public CA bị JDK distrust vì lý do bảo mật không nên được thêm lại chỉ để “chạy được”.

## 16. Truststore, identity keystore và mTLS

Khi HTTPS server yêu cầu **mutual TLS (mTLS)**, client phải:

1. **Tin chứng thư của server** qua **trust managers**.
2. **Chứng minh danh tính của client** bằng certificate/private key từ **key managers**.

Ví dụ cấu hình hai đường dẫn tách biệt:

~~~bash
java -Djavax.net.ssl.trustStore=/opt/app/security/server-trust.p12 -Djavax.net.ssl.trustStoreType=PKCS12 -Djavax.net.ssl.keyStore=/opt/app/security/client-identity.p12 -Djavax.net.ssl.keyStoreType=PKCS12 -jar app.jar
~~~

Các mật khẩu liên quan phải được cung cấp theo **cơ chế bảo vệ của môi trường**, ví dụ config/secret injection được kiểm soát, không để lộ plaintext trong Git, command history hay log. Những property ở lệnh trên mới xác định **đường dẫn/định dạng**, không tự cung cấp private key hoặc mật khẩu cần thiết.

| Bên dùng | Truststore | Identity keystore |
| --- | --- | --- |
| HTTPS client thông thường | Dùng xác minh server | Thường không cần |
| mTLS client | Dùng xác minh server | Cần client certificate + private key |
| HTTPS server | Dùng xác minh client nếu bật client auth | Thường cần server certificate + private key |
| Proxy/gateway TLS | Tùy vai trò client/server ở từng chặng | Tùy nơi terminate TLS và yêu cầu mTLS |

Đừng import **private key** của server vào truststore của client. Truststore thường chỉ cần **public certificates/trust anchors**, còn identity store quản lý private key với quyền truy cập hạn chế hơn.

## 17. Java 10 JEP 319 và root CA lifecycle trong JDK mới

Mốc lịch sử Java 10 đáng nhớ vì **JEP 319** giúp OpenJDK đi kèm root certificates có ích ngay trong `cacerts`. Nhưng trong hệ thống hiện hành:

- Một root CA có thể được **thêm, thay hoặc loại bỏ** theo bản cập nhật bảo mật.
- Một số CA có thể chịu **distrust policy** theo ngày cấp chứng thư hoặc điều kiện khác.
- Có thể có chính sách **disabledAlgorithms** thay đổi theo JDK update.
- Vendor hoặc OS distribution có thể đóng gói danh sách trust anchors khác nhau.
- CA/certificate **không còn hợp lệ** theo chính sách cập nhật thì không nên được phục hồi bằng cách thêm thủ công chỉ vì kết nối cũ cần chạy.

Ví dụ nguyên tắc vận hành:

~~~text
Nâng JDK / thay vendor / thay container image
             |
             v
Kiểm tra cacerts + JSSE default truststore
             |
             v
Chạy TLS integration tests với public & internal endpoints
             |
             v
Đọc release notes/security policies nếu chain khác trước
             |
             v
Điều chỉnh PKI/truststore theo phê duyệt bảo mật
~~~

Vì vậy “`cacerts` đã có CA X từ năm nào” không phải chứng minh rằng mọi JDK hiện tại vẫn chứa và tin nó. Tập tin **`cacerts` thuộc JDK thực đang chạy** và các chính sách `java.security` mới là nguồn cần kiểm tra.

## 18. Container, Kubernetes và nhiều bản JDK

Với Docker/Kubernetes, nên thiết kế truststore như một cấu hình bảo mật có vòng đời riêng:

1. Đảm bảo JVM có **runtime home** và JDK build được biết rõ.
2. Nếu dùng `cacerts` JDK, coi nó là **artifact thuộc image/JDK release**.
3. Nếu dùng truststore riêng, mount/copy file vào **đường dẫn tuyệt đối ổn định** trong container.
4. Quyền file chỉ mở cho user/service cần đọc; hạn chế sửa hoặc thay thế.
5. Với password/secret, dùng cơ chế quản lý bí mật của tổ chức; đừng đưa mật khẩu thật vào argument hiển thị công khai.
6. Kiểm tra lại sau image update, CA rotation, truststore change.
7. Nếu framework caching SSL contexts, có kế hoạch **restart/refresh** để nhận chứng thư mới.
8. Không tin rằng cập nhật root CA trên host tự động cập nhật JDK `cacerts` trong container.
9. Kiểm thử cả public HTTPS và CA nội bộ nếu ứng dụng thật sự cần cả hai.
10. Cẩn thận khi áp dụng property `javax.net.ssl.trustStore` **global**: nó có thể ảnh hưởng nhiều TLS clients cùng JVM.

### Tránh chép một truststore đã lỗi thời vào mọi image

Một image được build năm trước có thể chứa root CA đã bị loại khỏi JDK mới. Nếu cứ sao chép `cacerts` cũ sang image mới, bạn có thể **phục hồi CA đã bị distrust** và bỏ lỡ các root mới.

Một cách tốt hơn là dùng **JDK update đang được duy trì** làm nguồn public trust và quản lý CA nội bộ bằng một quy trình explicit có kiểm soát. Nếu tạo truststore hợp nhất, phải thực hiện kiểm thử tương thích và kiểm toán danh sách CA ở **mỗi release**.

## 19. Phương pháp kiểm thử lựa chọn truststore

Trong staging, kiểm thử ít nhất những trường hợp sau. Không cần kết nối tới website thật khi chỉ xác minh Java API; khi kiểm tra TLS integration thì sử dụng endpoint do tổ chức kiểm soát.

| Kịch bản | Điều phải xác minh |
| --- | --- |
| Không explicit property, chỉ có `cacerts` | SunJSSE nạp `cacerts`, public TLS hợp lệ hoạt động |
| Có `jssecacerts` | Nó có **ưu tiên hơn** `cacerts` |
| Explicit `trustStore` hợp lệ | Chỉ file explicit được chọn theo default factory |
| Explicit path không tồn tại | **Không fallback**; kiểm tra empty truststore |
| Explicit file PKCS12 sai password | Có lỗi tải/integrity, không tự fallback |
| Custom truststore chỉ CA nội bộ | Public HTTPS có thể fail nếu public root không có |
| Đúng root, nhưng hostname sai | Kết nối HTTPS vẫn bị từ chối |
| Server không gửi intermediate cần thiết | Kiểm tra PKIX chain building |
| Upgrade JDK/container image | CA list và security constraints có thể đổi |
| mTLS có truststore nhưng thiếu identity keystore | Client không thể trình chứng thư/private key đúng |
| SSLContext được tạo trước khi đổi property | Context cũ không tự refresh chắc chắn |
| Framework có SSLContext riêng | Global JSSE property có thể không điều khiển client đó |

### Test đúng lớp cấu hình

- **Kiểm thử API:** `TrustManagerFactory.init(empty)` có 0 accepted issuers.
- **Kiểm thử filesystem:** đường dẫn `java.home`, `jssecacerts`, `cacerts` tồn tại/đọc được.
- **Kiểm thử provider:** `TrustManagerFactory.init(null)` và debug SunJSSE chọn nguồn gì.
- **Kiểm thử TLS:** certificate chain, hostname, protocol và algorithm policies đúng.
- **Kiểm thử production:** đúng container image/JDK, proxy, keystore mounts, renewal/rotation.

Một test pass ở lớp API **không tự chứng minh** một TLS endpoint thật hợp lệ. Tương tự, việc file `cacerts` tồn tại không chứng minh root cần thiết có mặt và chấp nhận được.

## 20. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| “Truststore luôn là một loại file khác keystore.” | Truststore là **vai trò** của keystore, không phải một Java type riêng. | Phân biệt KeyManager/TrustManager và nội dung. |
| “`cacerts` luôn được dùng.” | Explicit `trustStore` và `jssecacerts` được ưu tiên. | Xem thứ tự SunJSSE. |
| “File explicit không tồn tại thì tự về `cacerts`.” | SunJSSE dùng **empty truststore**. | Kiểm tra path/permissions trước. |
| “Có `jssecacerts` thì tự hợp nhất với `cacerts`.” | Nó là nguồn ưu tiên riêng. | Quản lý trust anchors đúng tập. |
| “PKCS12 là default nên `cacerts` chắc chắn PKCS12.” | Default type khác actual file format. | Dùng `keytool` và kiểm tra keystore. |
| “Số CA trong mọi JDK cố định.” | Vendor, update, distrust policies thay đổi. | Đọc đúng runtime. |
| “OS đã tin root thì Java tự tin.” | JDK có trust material riêng hoặc vendor integration khác. | Xem JDK/cacerts/properties. |
| “`javax.net.ssl.keyStore` sửa lỗi thiếu CA.” | Property đó quản lý **local identity**. | Dùng trustStore/PKI đúng vai trò. |
| “Import CA nội bộ thì public CAs vẫn tự còn.” | Explicit store không tự merge. | Xây policy/store hợp nhất khi cần. |
| “CA trong truststore thì hostname sai cũng an toàn.” | Hostname là kiểm tra riêng. | Giữ endpoint identification. |
| “Mọi `SSLContext` đều dùng global trustStore.” | App/framework có thể cung cấp custom trust managers. | Xem cấu hình TLS cụ thể. |
| “Gọi `System.setProperty` lúc nào cũng refresh.” | Default contexts có thể đã cached. | Đặt trước init hoặc refresh/restart. |
| “PKIX failed luôn do thiếu root.” | Có thể do intermediate, policy, chain, thời hạn. | Dùng `javax.net.debug` và `certpath`. |
| “`changeit` là secret riêng của ứng dụng.” | Đây là default khởi tạo của nhiều bản `cacerts`. | Quản lý permissions/keystore khác nhau. |
| “Có thể tắt `checkServerTrusted` để sửa mọi TLS lỗi.” | Bỏ bảo vệ chống MITM. | Sửa chain/trust/hostname đúng. |
| “Import root nào cũng không ảnh hưởng bảo mật.” | Một CA được tin có quyền ký nhiều tên miền theo policy. | Chỉ nhập CA được xác minh/phê duyệt. |
| “JDK update chỉ nâng hiệu năng, không ảnh hưởng TLS.” | Root CA và security policies có thể thay đổi. | Chạy TLS integration tests sau update. |

## 21. Bài tập tự kiểm tra

### Bài 1 — thứ tự lựa chọn

**Đề:** `javax.net.ssl.trustStore` không được khai báo. Cả `jssecacerts` và `cacerts` đều có. SunJSSE chọn gì?

**Đáp án:** **`jssecacerts`**. Không tự merge hai file.

### Bài 2 — property trỏ file sai

**Đề:** `javax.net.ssl.trustStore=/opt/app/security/missing.p12`, file không tồn tại, `cacerts` vẫn có. SunJSSE có fallback về `cacerts` không?

**Đáp án:** **Không.** Trường hợp explicit path không tồn tại dẫn tới **truststore rỗng**.

### Bài 3 — identity vs trust

**Đề:** Java HTTPS client không tin certificate chain của server. Bạn chỉ cấu hình `javax.net.ssl.keyStore` chứa private key client. Có tự giải quyết lỗi không?

**Đáp án:** **Không.** KeyManager dùng cho local identity, còn TrustManager cần trust anchors thích hợp để xác minh server.

### Bài 4 — mặc định PKCS12

**Đề:** `KeyStore.getDefaultType()` trả `pkcs12`. Có được kết luận `cacerts` vật lý của mọi vendor đều là PKCS12 không?

**Đáp án:** **Không.** Default type cho keystore mới và format của file đang tồn tại không nhất thiết giống nhau.

### Bài 5 — JEP 319

**Đề:** Mục đích chính của JEP 319 tại Java 10 là gì?

**Đáp án:** Cung cấp **bộ root CA certificates mặc định** trong JDK/OpenJDK, cải thiện khả năng TLS server authentication ở những bản dựng vốn thiếu public trust anchors.

### Bài 6 — custom corp trust

**Đề:** `corp-only.p12` chỉ chứa private root CA. Khi đặt `trustStore` explicit, kết nối tới public endpoint có còn chắc chắn thành công không?

**Đáp án:** **Không.** Public root CAs từ `cacerts` không tự được merge vào custom truststore.

### Bài 7 — JSSE API

**Đề:** Khác biệt giữa `factory.init((KeyStore) null)` và `factory.init(custom)` là gì?

**Đáp án:** Với SunJSSE, **null** yêu cầu tìm trust material mặc định; **custom KeyStore** cung cấp trust anchors tường minh cho factory, không dựa vào quy tắc tìm file mặc định theo cách đó.

### Bài 8 — trust anchors và TLS

**Đề:** Một CA root phù hợp có trong `cacerts` nhưng hostname của HTTPS URL không có trong SAN. Có nên cho kết nối thành công không?

**Đáp án:** **Không.** Hostname/endpoint identity verification vẫn phải đạt.

### Bài 9 — kiểm thử fixture

**Đề:** Chế độ `fixture` của `JSSETrustStoreDemo` tạo empty PKCS12 rồi init TrustManagerFactory. Nó in số accepted issuers bao nhiêu?

**Đáp án:** **0**. Không có trusted certificate entry nào trong fixture.

### Bài 10 — thay truststore sau khi khởi động

**Đề:** Một application server đã tạo default SSLContext, sau đó operator thay nội dung file truststore. TLS clients đang chạy có chắc tự tải lại không?

**Đáp án:** **Không.** Phải xác minh lifecycle của context/pool/framework; thường cần **refresh/reinitialize hoặc restart** có kiểm soát.

### Bài 11 — lỗi PKIX

**Đề:** Có thể import leaf server certificate bất kỳ khi thấy `PKIX path building failed` mà không xem chain và fingerprint không?

**Đáp án:** **Không.** Phải tìm root cause, xác minh trust anchor qua kênh đáng tin cậy và giữ nguyên TLS hostname/cert-path validation.

### Bài 12 — vì sao không dùng trust-all?

**Đề:** Một `X509TrustManager` trả thành công cho mọi chứng thư có sửa được lỗi handshake không?

**Đáp án:** Nó có thể **che lỗi bằng cách vô hiệu hóa xác thực**, làm ứng dụng dễ bị MITM. Đây không phải giải pháp phù hợp.

## 22. Checklist triển khai JSSE truststore an toàn

- [ ] Xác định đúng **JDK vendor, update build, `java.home`** của tiến trình.
- [ ] Kiểm tra có **explicit `javax.net.ssl.trustStore`** không.
- [ ] Nếu không explicit, kiểm tra **`jssecacerts` trước `cacerts`**.
- [ ] Nếu explicit, kiểm tra path **tồn tại, đúng permission, format, password**.
- [ ] Dùng `keytool -list -cacerts` trên **đúng JDK**; không khẳng định CA count cố định.
- [ ] Xác minh **SHA-256 fingerprint** của CA nội bộ qua kênh tin cậy.
- [ ] Chỉ import CA được phê duyệt; không chấp nhận leaf/CA tùy tiện.
- [ ] Nếu cần public + private CAs, xây truststore/clients với **policy hợp nhất rõ ràng**.
- [ ] Không nhầm `trustStore` với identity `keyStore` cho mTLS.
- [ ] Giữ endpoint identification và PKIX/algorithm checks **đang được hỗ trợ**.
- [ ] Dùng JSSE debug/certpath logs có kiểm soát, không làm lộ secrets.
- [ ] Đánh giá framework/provider có tự tạo `SSLContext` hay không.
- [ ] Tái kiểm tra root CA trust, JDK security updates, rotation và distrust policies.
- [ ] Khi thay truststore, refresh TLS contexts/pools hoặc restart theo quy trình.
- [ ] Không thêm `TrustManager` “trust-all” hoặc `HostnameVerifier` “allow-all”.
- [ ] Test HTTPS public, corporate PKI và mTLS theo yêu cầu nghiệp vụ.

## 23. Tóm tắt và nguồn chính thức

**Ghi nhớ ba quy tắc:**

**Thứ nhất — chọn nguồn trust:** SunJSSE ưu tiên **explicit `javax.net.ssl.trustStore` → `jssecacerts` → `cacerts`**. Khi explicit path sai/không tồn tại, **không fallback** về JDK `cacerts`.

**Thứ hai — đúng vai trò:** `TrustManagerFactory` dùng trust anchors để xác minh peer; `KeyManagerFactory` dùng local identity private key/certificate chain. `cacerts` là **truststore mặc định phổ biến**, không phải identity keystore của server.

**Thứ ba — đúng chính sách bảo mật:** Có CA trong store chưa đủ. Certificate path, hostname verification, thời hạn, thuật toán và distrust policies vẫn cần được áp dụng. Không bỏ certificate checks để chữa một TLS handshake failure.

**Tài liệu chuẩn, còn áp dụng:**

1. [OpenJDK JEP 319 — Root Certificates (Java 10)](https://openjdk.org/jeps/319).
2. [Oracle JDK 10 Release Notes — JEP 319 Root Certificates](https://www.oracle.com/java/technologies/javase/10all-relnotes.html).
3. [Oracle JDK 25 — Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html).
4. [Oracle JDK 25 — The keytool Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/keytool.html).
5. [OpenJDK JEP 229 — Create PKCS12 Keystores by Default](https://openjdk.org/jeps/229).
6. [Oracle JDK 25 — Java Cryptography Architecture Reference Guide](https://docs.oracle.com/en/java/javase/25/security/java-cryptography-architecture-jca-reference-guide.html).
7. [Java SE 17 — `TrustManagerFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html).
8. [Java SE 17 — `SSLContext`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html).
9. [Java SE 17 — `KeyStore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html).
10. [Oracle JDK 25 — Java Security Developer’s Guide](https://docs.oracle.com/en/java/javase/25/security/security-developer-guide.pdf).

**Kết luận:** `cacerts` là một nguồn trust anchors mặc định quan trọng mà JDK 10 giúp đưa vào OpenJDK; nhưng **JSSE không phải lúc nào cũng dùng `cacerts`**. Khi kết nối TLS gặp lỗi, cần xác minh **đúng JVM, đúng đường dẫn, thứ tự `trustStore/jssecacerts/cacerts`, nội dung certificate chain và PKIX/hostname policies**. Cấu hình truststore riêng chỉ nên được triển khai với CA đã xác thực, quản lý vòng đời rõ ràng và kiểm thử TLS đầy đủ.
