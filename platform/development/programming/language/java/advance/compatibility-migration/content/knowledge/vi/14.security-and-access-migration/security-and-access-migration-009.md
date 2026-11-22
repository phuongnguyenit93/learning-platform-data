# Phân biệt sửa tương thích với việc khôi phục cấu hình bảo mật đã lỗi thời

Khi nâng cấp Java, ứng dụng có thể không khởi động, không kết nối được tới một dịch vụ cũ hoặc không còn truy cập được một thành phần nội bộ. Một cách xử lý nhanh thường được đề xuất là “bật lại cấu hình cũ”: mở mọi package cho reflection, chấp nhận mọi chứng chỉ TLS, kích hoạt giao thức mật mã đã bị vô hiệu hóa hoặc khôi phục cơ chế phân quyền đã không còn được hỗ trợ. Cách này có thể làm một bài kiểm thử ngắn vượt qua, nhưng cũng có thể **làm mất chính những cải tiến bảo mật mà việc nâng JDK mang lại**.

Trong **Java Advance Compatibility Migration**, cần phân biệt rõ hai mục tiêu:

1. **Sửa tương thích (compatibility remediation):** đưa ứng dụng trở lại hành vi và giao tiếp mong muốn bằng API, giao thức, quyền truy cập và cấu hình còn được hỗ trợ, trong khi duy trì mức bảo vệ phù hợp.
2. **Khôi phục cấu hình bảo mật đã lỗi thời (legacy security rollback):** nới lỏng hoặc vô hiệu hóa một kiểm soát bảo mật để giữ cách hoạt động cũ, ví dụ bỏ xác minh danh tính máy chủ, cho phép giao thức đã bị tắt hoặc mở rộng quyền truy cập nội bộ quá mức.

Hai thao tác này không đồng nghĩa. Có những biện pháp chuyển tiếp bị giới hạn phạm vi và được quản lý có thể cần thiết trong quá trình migration, nhưng không được mặc định coi việc “hết lỗi” là bằng chứng giải pháp an toàn hoặc bền vững.

Bài học tập trung vào cách phân loại sự cố, xác định nguyên nhân gốc, chọn cách sửa phù hợp và lưu bằng chứng để không đánh đổi bảo mật lấy khả năng tương thích ngắn hạn.

## 1. Tương thích và bảo mật là hai yêu cầu cùng phải thỏa mãn

Một hệ thống tương thích nghĩa là những consumer được hỗ trợ tiếp tục thực hiện đúng hợp đồng đã công bố: ứng dụng khởi động, API hoạt động, dữ liệu được xử lý đúng và những giao tiếp bên ngoài đáp ứng yêu cầu.

Một hệ thống an toàn còn phải duy trì các kiểm soát như:

- Xác minh danh tính máy chủ và chuỗi tin cậy khi kết nối TLS.
- Sử dụng protocol, cipher và thuật toán được chính sách bảo mật cho phép.
- Hạn chế quyền truy cập của process, module và tài khoản dịch vụ.
- Bảo vệ dữ liệu bí mật, credential, khóa và certificate.
- Kiểm soát việc nạp class, xử lý dữ liệu không tin cậy và thực thi mã từ bên ngoài.
- Ghi log, phân quyền và giám sát mà không làm lộ dữ liệu nhạy cảm.

Một thay đổi có thể giải quyết khía cạnh tương thích nhưng làm xấu bảo mật. Ví dụ, bỏ toàn bộ kiểm tra certificate sẽ giúp client kết nối tới cả máy chủ có chứng chỉ sai; điều đó không chứng minh kết nối đúng đích.

Cũng có trường hợp việc áp dụng cấu hình bảo mật mới làm bộc lộ lỗi tồn tại từ lâu của hệ thống cũ. Khi JDK từ chối cipher yếu hoặc reflection vào private field, “sửa lỗi” không nhất thiết là trả runtime về hành vi trước kia. Thường cần sửa phía hệ thống phụ thuộc hoặc thay cách tích hợp.

## 2. Phân biệt ba loại kết quả khi xử lý lỗi

| Kết quả | Mô tả | Ví dụ |
|---|---|---|
| Sửa tương thích đúng nguyên nhân | Thay API, dependency hoặc cấu hình để đáp ứng yêu cầu trên JDK mới, vẫn giữ kiểm soát bảo mật | Nâng thư viện HTTP và sửa certificate chain để TLS handshake thành công |
| Biện pháp chuyển tiếp có kiểm soát | Nới một quyền có phạm vi hẹp trong thời gian xác định, có owner và phương án loại bỏ | Mở đúng một package cho một named module trong khi nâng framework |
| Khôi phục hành vi không an toàn | Tắt hoặc mở rộng vô hạn các kiểm soát chỉ để bỏ lỗi | Trust-all TLS, bỏ hostname verification, chấp nhận giao thức đã bị chính sách cấm |

Không phải mọi workaround đều có mức rủi ro giống nhau. Để quyết định chấp nhận một biện pháp tạm thời, phải nêu rõ ranh giới, dữ liệu bị ảnh hưởng, điều kiện áp dụng, mức kiểm soát bù đắp và kế hoạch thay thế. Nếu không chứng minh được rằng rủi ro còn lại phù hợp với chính sách tổ chức, cần sửa thiết kế thay vì khôi phục mặc định cũ.

## 3. Tại sao nâng JDK có thể làm lộ vấn đề bảo mật?

Thay đổi không chỉ đến từ Java language hoặc bytecode. Những lớp khác nhau có thể bị tác động:

1. **JSSE/TLS:** protocol, thuật toán, certificate validation, hostname verification và truststore.
2. **Security providers:** lựa chọn provider, khả năng hỗ trợ algorithm, key format và cipher mode.
3. **Certificate path validation:** thuật toán chữ ký, key size, CA chain, hạn sử dụng và chính sách kiểm tra đường dẫn.
4. **JPMS strong encapsulation:** module nào được phép truy cập public API, package nào mở cho deep reflection.
5. **JDK API lifecycle:** những cơ chế cũ bị deprecated, disabled hoặc removed.
6. **Java deserialization:** bộ lọc lớp được deserialize và giới hạn tài nguyên.
7. **JVM options:** flag bị đổi tên, trở nên obsolete hoặc không còn được hỗ trợ.
8. **Runtime packaging:** custom image thiếu provider, certificate, module hay thành phần cần thiết.
9. **Operating system và container:** truststore, quyền file, DNS, proxy, native library và hệ thống tài khoản dịch vụ.

Một cập nhật bảo mật của JDK trong **cùng feature release** cũng có thể thay đổi các giới hạn hoặc chính sách được áp dụng. Vì vậy, không nên ghi “Java 17 bị lỗi TLS” mà thiếu update/build, vendor, hệ điều hành và endpoint thực tế.

## 4. Bắt đầu bằng phân loại lỗi thay vì thử tắt bảo mật

Thông báo lỗi thường là điểm khởi đầu, không phải kết luận duy nhất.

| Triệu chứng | Các nguyên nhân cần điều tra | Điều không nên làm ngay |
|---|---|---|
| `SSLHandshakeException: PKIX path building failed` | Trust chain, CA, chứng chỉ trung gian, truststore được nạp | Cài TrustManager chấp nhận mọi certificate |
| `No subject alternative names matching` | Hostname và chứng chỉ máy chủ không khớp | Tắt hostname verification |
| `handshake_failure` hoặc `protocol_version` | Protocol/cipher, key exchange, proxy, thiết bị TLS, certificate | Bật lại toàn bộ TLS yếu |
| `InaccessibleObjectException` | Reflection vào package chưa mở của một module | Mở hàng loạt package JDK |
| `IllegalAccessError` | Quyền module export hoặc binary access | Dùng cờ mở quyền không xác định |
| `AccessControlException` trên JDK cũ | SecurityManager/policy và operation đang bị chặn | Cấp `AllPermission` cho mọi code |
| `InvalidKeyException`, `NoSuchAlgorithmException` | Key format/size, algorithm, provider, policy | Chọn lại thuật toán yếu hơn để “chạy được” |
| `ClassNotFoundException` khi deserialize | Missing class, version mismatch, allowlist/filter, class loader | Tắt mọi deserialization filter |
| Không đọc được secret/certificate file | File path, ownership, POSIX/Windows ACL, mount và container UID | Cho quyền đọc rộng rãi hoặc sao chép secret vào image |

Nên thu thập stack trace, root cause, JVM version và cấu hình liên quan trước khi thay đổi. Một lỗi “handshake_failure” có thể do nhiều yếu tố; không nên suy ra thiếu protocol chỉ từ một chuỗi thông báo.

## 5. Ví dụ điển hình: TLS không kết nối được sau khi nâng JDK

Giả sử một ứng dụng chuyển từ JDK cũ lên JDK mới, sau đó kết nối HTTPS tới dịch vụ nội bộ thất bại. Nhóm phát hiện một hướng dẫn cũ đề xuất tạo `X509TrustManager` không kiểm tra certificate để “sửa SSL”.

Nếu thực hiện cách đó, kết nối có thể vượt qua lỗi xác minh, nhưng client không còn xác nhận được máy chủ có đúng danh tính hay không. Điều này có thể tạo điều kiện cho kết nối đến máy chủ giả mạo hoặc kẻ trung gian, đặc biệt nếu hostname verification cũng bị bỏ.

Hướng xử lý phù hợp là xác định **vì sao xác minh thất bại**:

- Certificate máy chủ đã hết hạn hay chưa có hiệu lực?
- Tên DNS mà client dùng có nằm trong Subject Alternative Name (SAN) của certificate?
- Máy chủ có gửi đủ intermediate certificates không?
- CA phát hành có được truststore đúng môi trường tin cậy không?
- Client đang dùng truststore nào: mặc định JDK, cấu hình riêng, hay từ container?
- Proxy/gateway có terminate TLS và cung cấp certificate khác không?
- Có sự khác biệt về đồng hồ hệ thống, SNI hoặc tên host không?
- Thuật toán ký certificate, kích thước khóa hoặc giao thức đã bị hạn chế bởi chính sách mới không?

Sau khi xác định nguyên nhân, sửa trust chain, certificate, tên endpoint hoặc cấu hình client tương ứng. Nếu phải bổ sung CA nội bộ vào truststore, cần xác minh nguồn gốc và thẩm quyền của CA, không import một certificate chưa được kiểm tra chỉ để bỏ lỗi.

### 5.1. Dùng HTTP client được hỗ trợ và giữ xác minh TLS

Ví dụ Java 11+ sử dụng Java HTTP Client:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class HealthClient {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.example.org/health"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString());

        System.out.println("HTTP status = " + response.statusCode());
    }
}
~~~

Đây là ví dụ về việc dùng API chuẩn, không tùy chỉnh để bỏ xác minh certificate hay hostname. Domain là placeholder. Với hệ thống thực tế, client còn cần xử lý lỗi mạng, xác thực, giới hạn kích thước dữ liệu và timeout theo yêu cầu dịch vụ.

Không nên viết một custom trust manager kiểu “chấp nhận tất cả” hay một hostname verifier luôn trả true. Những đoạn code đó giải quyết triệu chứng bằng cách bỏ kiểm tra danh tính.

### 5.2. Các thao tác kiểm tra phù hợp

Xem cấu hình Java Security của runtime:

~~~java
import java.security.Security;

public final class SecurityDiagnostics {
    public static void main(String[] args) {
        System.out.println(
                "TLS disabled algorithms: " +
                Security.getProperty("jdk.tls.disabledAlgorithms"));

        System.out.println(
                "Cert path disabled algorithms: " +
                Security.getProperty("jdk.certpath.disabledAlgorithms"));
    }
}
~~~

Các property này là một phần thông tin để điều tra; giá trị cụ thể phụ thuộc JDK và chính sách. Không nên ghi đè chúng nhằm bật lại thuật toán bị cấm khi chưa có đánh giá bảo mật.

Có thể bật debug TLS tạm thời trên một môi trường được kiểm soát:

~~~bash
java -Djavax.net.debug=ssl:handshake -jar application.jar
~~~

Log handshake có thể chứa thông tin certificate, tên host và chi tiết hạ tầng. Hạn chế quyền truy cập log và không giữ debug verbose lâu dài trong production nếu không có quy trình phù hợp.

### 5.3. Sửa truststore khác với bỏ xác minh

Một truststore được quản trị đúng lưu những CA hoặc certificate được tổ chức quyết định tin cậy. Khi bổ sung một CA nội bộ, cần kiểm tra certificate chain, tên hệ thống, vòng đời, quy trình thay thế và phạm vi trust.

Java thường hỗ trợ chỉ định truststore qua các system property phù hợp, ví dụ:

~~~text
-Djavax.net.ssl.trustStore=/secure/path/truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
~~~

Đây là cấu hình mẫu, không phải chỉ dẫn tự import bất kỳ certificate nào. Không đặt password trực tiếp trong source hoặc script có thể bị đọc; quản lý secret qua cơ chế phù hợp. Việc đặt truststore riêng có thể thay thế tập CA mặc định theo cấu hình, nên cần xác nhận các endpoint khác vẫn hoạt động.

## 6. TLS protocol và cipher: nâng cấp peer thay vì bật lại chế độ yếu

Một JDK mới có thể vô hiệu hóa giao thức hoặc thuật toán yếu theo chính sách bảo mật. Khi hệ thống cũ chỉ hỗ trợ protocol/cipher không còn được cho phép, ứng dụng có thể không bắt tay TLS thành công.

Một cách “sửa” sai hướng là giảm mức bảo vệ của client cho mọi kết nối. Điều này mở rộng rủi ro sang cả những endpoint không cần thay đổi.

Thay vào đó:

1. Kiểm tra phiên bản TLS và cipher suite thực sự được hai bên hỗ trợ.
2. Xác định vị trí chặn: JDK client, server, reverse proxy hay load balancer.
3. Ưu tiên nâng cấp server hoặc thiết bị trung gian để hỗ trợ giao thức và cipher hiện đại.
4. Xác định cấu hình TLS theo tiêu chuẩn an toàn của tổ chức và môi trường.
5. Kiểm thử với client/runtime đích, bao gồm tính tương thích của các consumer khác.
6. Nếu cần thiết kế giai đoạn chuyển tiếp, giới hạn phạm vi, thời hạn, network segment và biện pháp giảm thiểu, rồi xin phê duyệt theo quy trình bảo mật.

Việc TLS 1.2 hoặc TLS 1.3 có khả dụng còn tùy JDK, provider và cấu hình hai bên. Không nên áp một danh sách protocol mà chưa kiểm tra hệ thống thực tế.

Một cấu hình bảo mật bị siết chặt không phải regression chỉ vì ứng dụng từng kết nối được ở JDK cũ. Mục tiêu migration là giữ được nghiệp vụ mà không quay về mức bảo vệ bị chính sách loại bỏ.

## 7. Certificate validation không giống application authorization

Kết nối TLS thành công chỉ chứng minh những thuộc tính được cơ chế TLS xác minh, như certificate chain và danh tính endpoint theo cấu hình. Nó không tự cấp quyền truy cập một API nghiệp vụ.

Cần phân biệt:

- **Authentication:** ai đang giao tiếp?
- **Authorization:** danh tính đó được phép thực hiện hành động nào?
- **Confidentiality/integrity:** dữ liệu truyền có được bảo vệ theo cơ chế đã chọn không?
- **Trust configuration:** client tin cậy CA/endpoint nào, theo chính sách nào?

Ví dụ, sửa một lỗi certificate chain không được kéo theo việc cấp mọi API permission cho tài khoản dịch vụ. Một hệ thống có thể cần cập nhật role/permission do thay đổi service account, nhưng đó là quyết định bảo mật riêng, không phải một hệ quả tất yếu của việc nâng JDK.

## 8. Ví dụ JPMS: mở quyền reflection hay sửa cách sử dụng API?

Từ Java 9, JPMS đưa vào các ranh giới module. Trong JDK hiện đại, strong encapsulation làm nhiều thư viện cũ gặp lỗi khi reflection vào private member của JDK.

Ví dụ:

~~~java
import java.lang.reflect.Field;

Field field = String.class.getDeclaredField("value");
field.setAccessible(true);
~~~

Trên JDK đích, lời gọi trên có thể ném:

~~~text
java.lang.reflect.InaccessibleObjectException:
module java.base does not "opens java.lang" to unnamed module
~~~

Thông báo thường cho biết source module, package và target module. Đây là vấn đề **deep reflection qua ranh giới module**, không có nghĩa API `String` đã bị xóa.

### 8.1. `exports` và `opens`

| Cơ chế | Mục tiêu |
|---|---|
| `exports some.package` | Công bố các public type và member theo quy tắc module |
| `opens some.package` | Cho phép deep reflection vào package đó ở runtime |
| `opens some.package to target.module` | Chỉ mở package cho module cụ thể |
| `--add-exports` | Bổ sung quyền truy cập public API của package chưa export |
| `--add-opens` | Bổ sung quyền deep reflection vào package tại runtime |

Nếu package thuộc **module ứng dụng do nhóm sở hữu**, một khai báo có phạm vi hẹp có thể phù hợp:

~~~java
module com.example.customer {
    exports com.example.customer.api;
    opens com.example.customer.dto to com.example.serializer;
}
~~~

Tên module serializer chỉ là ví dụ. Trong dự án thật, cần dùng tên module chính xác của framework; không mặc định tên artifact Maven là tên module JPMS.

Nếu reflection nhắm vào **private field nội bộ của JDK**, hướng lâu dài nên là dùng public API hoặc nâng thư viện/framework để không phụ thuộc chi tiết triển khai.

### 8.2. `--add-opens` có thể là biện pháp chuyển tiếp, không phải hợp đồng mới

Ví dụ cú pháp:

~~~bash
java --add-opens=java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

Tùy chọn này có thể giúp kiểm chứng một ứng dụng classpath đang bị chặn reflective access tới package cụ thể. Nhưng nó mở rộng khả năng truy cập cho các thành phần trong phạm vi target và vẫn phụ thuộc vào private implementation của JDK.

Nếu phải dùng tạm, cần ghi rõ:

- Source module và package đã được xác minh từ lỗi.
- Target module hoặc nhóm unnamed modules cần quyền.
- Framework/dependency nào gây ra yêu cầu reflection.
- Lý do chưa thể nâng cấp hoặc thay API.
- JVM cụ thể mà cờ được áp dụng: test worker, service, agent hoặc container.
- Owner, thời hạn đánh giá lại và tiêu chí loại bỏ.
- Bằng chứng rằng các kiểm soát khác vẫn được duy trì.

Không nên sao chép một chuỗi dài `--add-opens` từ một dự án khác hay mở tất cả package không có căn cứ. JPMS encapsulation không phải cơ chế sandbox bảo mật toàn diện, nhưng việc bỏ kiểm soát truy cập nội bộ vẫn tạo phụ thuộc và làm rộng khả năng tương tác với implementation detail.

## 9. SecurityManager cũ: khác biệt giữa sửa ứng dụng và phục hồi sandbox lỗi thời

Trong các phiên bản Java trước đây, `SecurityManager` và policy file từng được dùng để kiểm soát một số quyền trong cùng tiến trình JVM. Cơ chế này đã được đưa vào lộ trình ngừng hỗ trợ và thay đổi đáng kể trong các JDK hiện đại.

JEP 411 đánh dấu SecurityManager là deprecated for removal từ Java 17. JEP 486 tiếp tục làm SecurityManager không còn được hỗ trợ để bật lại như cơ chế sandbox cũ trong JDK 24. Khi lập kế hoạch nâng JDK, cần kiểm tra trạng thái của đúng target release và những API cũ mà dự án đang dùng.

Một dự án từng cấu hình:

~~~text
grant {
    permission java.security.AllPermission;
};
~~~

có thể đã cấp quyền rộng trong SecurityManager policy để tránh lỗi quyền. Việc sao chép thiết lập kiểu này vào kiến trúc mới hoặc tìm cách khôi phục sandbox đã lỗi thời không phải hướng migration bền vững.

### 9.1. Vì sao không nên “cấp mọi permission”?

`AllPermission` về bản chất xóa đi nhiều ranh giới quyền trong mô hình SecurityManager cũ. Nó không giúp xác định quyền nào thực sự cần thiết và không giải quyết kiến trúc bảo mật trên JDK mới.

Nếu ứng dụng trước đây dựa vào SecurityManager để cô lập plugin hoặc mã không tin cậy, không nên thay nó bằng một cờ hoặc policy cho phép tất cả. Cần xem xét lại **ranh giới tin cậy** của hệ thống:

- Process và container isolation.
- OS filesystem permission và tài khoản dịch vụ riêng.
- Network policy hoặc firewall.
- Quyền truy cập secret và credential.
- Phân quyền theo identity, API token, OAuth/RBAC tùy kiến trúc.
- Phân tách thành dịch vụ/process riêng cho plugin không tin cậy.
- Giới hạn tài nguyên và cơ chế quan sát.

Một class loader riêng hoặc JPMS module riêng không tự tạo ra sandbox bảo mật đủ để thực thi mã không tin cậy. Nếu nhu cầu là cô lập mã độc lập, phải chọn mô hình isolation thực sự phù hợp với mức rủi ro.

### 9.2. Dấu hiệu cần tái thiết kế

Nếu ứng dụng đang dùng `System.setSecurityManager`, `AccessController.doPrivileged`, custom policy hoặc kiểm tra permission kiểu cũ, hãy kiểm kê code path và vai trò thực sự của nó. Đừng chỉ xóa đoạn code để vượt qua compile error nếu nó từng là một tầng bảo vệ có chủ đích.

Kế hoạch migration phải trả lời:

1. SecurityManager cũ bảo vệ tài nguyên nào?
2. Ai là nguồn dữ liệu/mã không tin cậy?
3. Ranh giới mới là process, container, service hay identity?
4. Ai quản lý policy và kiểm tra quyền mới?
5. Test nào chứng minh trường hợp bị cấm vẫn bị từ chối?
6. Điều gì xảy ra khi một plugin hoặc dependency bị compromise?

Tương thích chức năng và bảo vệ tài nguyên phải được xử lý đồng thời.

## 10. Crypto provider và thuật toán cũ

Một ứng dụng có thể yêu cầu thuật toán theo tên hoặc phụ thuộc provider cụ thể:

~~~java
import javax.crypto.Cipher;

Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
~~~

Ví dụ trên chọn một transformation chuẩn, nhưng code mã hóa thật còn phải quản lý key, nonce/IV, tag, dữ liệu đã mã hóa và chính sách tái sử dụng nonce đúng cách. Không nên coi một lời gọi `getInstance` là đủ cho thiết kế mật mã hoàn chỉnh.

Trong migration, lỗi `NoSuchAlgorithmException` hoặc `NoSuchPaddingException` có thể xảy ra khi:

- Thuật toán hoặc transformation không có trong provider đang được chọn.
- Tên thuật toán riêng của vendor không còn được cung cấp.
- Provider bị thiếu trong custom runtime image.
- Cấu hình provider order hoặc security policy đã đổi.
- Key/certificate không đáp ứng giới hạn của JDK mục tiêu.

Hướng sửa là xác định thuật toán được hệ thống yêu cầu, định dạng dữ liệu lịch sử và provider có thể hỗ trợ an toàn. Không nên chuyển sang thuật toán yếu hơn để “lấy lại tương thích”, hoặc bỏ qua lỗi chữ ký/xác thực.

### 10.1. Không nhầm khả năng đọc dữ liệu cũ với khả năng tạo dữ liệu mới

Một hệ thống có thể cần **đọc tài liệu lịch sử** được bảo vệ bằng một thuật toán cũ, đồng thời không còn cho phép dùng thuật toán đó tạo dữ liệu mới. Hai yêu cầu này có thể cần quy trình xử lý riêng:

- Đánh giá chính sách và quyền truy cập dữ liệu lịch sử.
- Nếu được cho phép, cô lập bước chuyển đổi theo môi trường có kiểm soát.
- Chuyển dữ liệu sang định dạng và thuật toán được chấp thuận.
- Xác minh tính toàn vẹn và khả năng khôi phục.
- Ngừng tạo dữ liệu mới bằng cơ chế cũ.
- Ghi lại phạm vi, owner và thời gian loại bỏ thành phần chuyển đổi.

Không phải thuật toán cũ nào cũng được phép dùng để giải mã, xác minh hay di chuyển dữ liệu. Cần tuân theo chính sách bảo mật và quy định áp dụng, thay vì mặc định “chỉ đọc thì luôn an toàn”.

## 11. Deserialization và dữ liệu không tin cậy

Một số ứng dụng cũ sử dụng Java native serialization. Khi chuyển sang JDK mới hoặc cập nhật thư viện, hệ thống có thể bắt đầu áp dụng bộ lọc hoặc hạn chế đối với class được deserialize. Nếu dữ liệu hoặc class không khớp kỳ vọng, quá trình giải tuần tự có thể thất bại.

Bật cho phép mọi class một cách vô điều kiện không phải giải pháp tương thích an toàn. Deserialization của dữ liệu không tin cậy có thể tạo rủi ro nghiêm trọng khi kết hợp với các class và behavior không phù hợp.

Thay vào đó:

- Xác định dữ liệu đến từ nguồn nào và có đáng tin cậy hay không.
- Ghi danh sách kiểu hợp lệ và giới hạn kích thước, độ sâu, số reference theo nhu cầu.
- Dùng `ObjectInputFilter` hoặc cơ chế phù hợp của runtime/framework để giới hạn lớp được giải tuần tự.
- Cân nhắc chuyển sang định dạng dữ liệu có schema, version và validation rõ.
- Thử cả dữ liệu lịch sử hợp lệ lẫn dữ liệu sai định dạng/bị từ chối.
- Không bỏ tất cả filter chỉ vì một object cũ không được nhận diện.

Ví dụ khái niệm với filter:

~~~java
import java.io.ObjectInputFilter;

ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=10;maxrefs=1000;java.base/*;com.example.dto.*;!*");
~~~

Đây chỉ là ví dụ về việc áp dụng giới hạn; pattern thực tế phải được thiết kế theo tập class và graph dữ liệu thực, đồng thời kiểm tra đúng API/runtime mục tiêu. Không nên lấy pattern này làm allowlist mặc định cho mọi ứng dụng. Cần gắn filter vào luồng ObjectInputStream theo thiết kế và kiểm tra behavior thật.

Mục tiêu migration là cho **dữ liệu hợp lệ được hỗ trợ** tiếp tục hoạt động mà không mở cửa cho object graph bất kỳ.

## 12. Kiểm soát quyền file, secret và runtime image

Một số lỗi được gọi chung là “security compatibility” thực ra đến từ container hoặc hệ điều hành:

- Ứng dụng chạy với UID không có quyền đọc private key.
- Truststore/certificate không được mount vào container mới.
- Docker image tối giản thiếu module hoặc provider cần dùng.
- File path trước đây dựa vào cấu trúc cài đặt JDK 8.
- Container mới có filesystem read-only, không cho ghi thư mục tạm.
- Service account hoặc role thay đổi khi nâng nền tảng.

Hướng sửa là định nghĩa **quyền tối thiểu thực sự cần**, chứ không gán quyền toàn hệ thống.

Ví dụ, nếu ứng dụng phải đọc một file certificate, kiểm tra owner/group/ACL, mount và permission ở đúng thư mục. Không nên dùng `chmod 777` hoặc copy private key vào một vị trí dễ đọc để bỏ lỗi. Nếu ứng dụng cần ghi tạm, tạo vùng ghi riêng có quyền phù hợp thay vì biến toàn bộ filesystem thành writable.

Cần phân biệt JVM permission với OS/container permission. Một cờ Java không thể thay thế kiểm soát truy cập của hệ điều hành, và thay đổi OS ACL không tự giải quyết JPMS encapsulation.

## 13. Bảng lựa chọn: sửa tương thích hay mở lại cấu hình cũ?

| Tình huống | Sửa theo hướng được hỗ trợ | Workaround cần cân nhắc | Không nên coi là kết quả cuối |
|---|---|---|---|
| Certificate chain thiếu | Sửa chain, truststore, CA được phê duyệt | Truststore riêng được quản trị | Trust-all certificate |
| Hostname/SAN sai | Sửa DNS, endpoint hoặc cấp lại certificate đúng SAN | Chuyển endpoint có chứng chỉ hợp lệ | Bỏ hostname verification |
| Server chỉ hỗ trợ TLS yếu | Nâng server/proxy và client tương thích | Giai đoạn chuyển đổi bị giới hạn có phê duyệt | Bật giao thức yếu toàn cục |
| Framework reflection vào private JDK | Nâng framework, dùng public API | `--add-opens` hẹp, có owner và thời hạn | Mở hàng loạt JDK packages lâu dài |
| Named module DTO chưa mở | Qualified `opens` cho framework cần thiết | Runtime open có phạm vi trong giai đoạn triển khai | Dùng `open module` tràn lan không phân tích |
| App dựa vào SecurityManager sandbox | Thiết kế lại ranh giới process/container/identity | Giai đoạn vận hành song song có kiểm soát | Khôi phục `AllPermission` hay sandbox lỗi thời |
| Provider/algorithm cũ thiếu | Chọn provider/algorithm được hỗ trợ, di chuyển dữ liệu | Công cụ chuyển đổi dữ liệu lịch sử đã duyệt | Hạ toàn bộ chính sách crypto |
| Deserialize bị từ chối | Sửa schema/class mapping và filter đúng | Tập ngoại lệ allowlist hẹp, có kiểm soát | Bỏ toàn bộ filter |
| Không đọc được file secret | Sửa mount, owner, ACL và quyền tiến trình | Quyền cụ thể ở path cần thiết | Cấp toàn quyền filesystem |

Bảng này là công cụ ra quyết định, không thay thế security review. Một workaround chỉ hợp lệ khi chính sách tổ chức cho phép và rủi ro đã được xác định.

## 14. Quy trình xử lý sự cố security-related compatibility

### Bước 1: Xác định phiên bản và trạng thái thật

Thu thập Java version, JDK distribution, update/build, Gradle/Maven runtime, OS, container, classpath/module path và các cấu hình bảo mật có liên quan. Đừng chỉ ghi “nâng từ Java 8 lên Java 17”.

Ví dụ:

~~~bash
java -version
javac -version
~~~

Với build Gradle, JVM chạy daemon, toolchain biên dịch và JVM chạy test có thể khác nhau. Nếu lỗi xảy ra trong test worker, cấu hình JVM của Gradle daemon không tự là cấu hình của worker.

### Bước 2: Chụp lại lỗi gốc

Lưu stack trace đầy đủ, nguyên nhân sâu nhất, thao tác kích hoạt, endpoint hoặc member liên quan. Với TLS có thể thu thập handshake debug tạm thời; với JPMS cần giữ nguyên thông báo `does not "opens"`; với crypto cần lưu algorithm và provider.

Khi thu thập log bảo mật, che secret, token, private key và dữ liệu cá nhân. Chỉ chia sẻ log cho các nhóm có quyền truy cập.

### Bước 3: So sánh cấu hình cũ và mới

So sánh chính sách hiệu lực, không chỉ so sánh file cấu hình:

- JVM system properties và security properties.
- Truststore/certificate thực sự được nạp.
- TLS protocol/cipher được client/server hỗ trợ.
- Module exports/opens và vị trí classpath/module path.
- Security provider và algorithm constraints.
- Quyền của service account và container.
- Bộ lọc deserialize và thư viện framework.

Một file `java.security` ở môi trường cũ và mới có thể khác, nhưng thay đổi runtime còn đến từ security update, provider và cấu hình OS. Không áp chênh lệch bằng cách chép toàn bộ file cũ sang JDK mới.

### Bước 4: Phân loại giải pháp

Đối với mỗi đề xuất, ghi:

- Vấn đề gốc được xử lý là gì?
- Có phụ thuộc API hoặc configuration không còn được hỗ trợ không?
- Phạm vi nới quyền/bảo mật là bao nhiêu?
- Có phương án sửa phía peer hoặc nâng dependency không?
- Ai sở hữu rủi ro và chịu trách nhiệm loại bỏ workaround?
- Test nào sẽ chứng minh chức năng vẫn đúng và kiểm soát bảo mật vẫn hoạt động?

Không nên chọn giải pháp chỉ dựa vào việc startup hoặc một request thành công.

### Bước 5: Thử sửa bền vững trước

Ưu tiên nâng dependency, dùng API chính thức, cấp lại certificate đúng, cấu hình truststore có kiểm soát, nâng TLS endpoint và điều chỉnh quyền truy cập thực tế.

Với plugin hoặc thư viện chưa được nâng cấp, cân nhắc bản sửa được hỗ trợ. Nếu vendor chưa cung cấp, cần quản lý ngoại lệ và kế hoạch thay thế.

### Bước 6: Kiểm chứng chức năng và bảo mật

Chạy cả positive test lẫn negative test: hệ thống phải xử lý yêu cầu hợp lệ **và tiếp tục từ chối yêu cầu không được phép**.

### Bước 7: Thực hiện rollout có kiểm soát

Dùng staging/canary theo môi trường mục tiêu, có tiêu chí rollback rõ. Theo dõi TLS failures, authorization denials, reflection errors, exception types, latency và các chỉ số nghiệp vụ liên quan.

### Bước 8: Lưu bằng chứng và ngoại lệ

Ghi version, command line, log, test report, quyết định và owner. Nếu giữ cấu hình tạm thời, phải có điều kiện chấm dứt; không để một workaround trở thành baseline mặc định cho các JDK sau.

## 15. Kiểm thử hai chiều: hoạt động hợp lệ và từ chối đúng

Một kết luận “compatibility fixed” không đủ nếu chỉ chạy happy path.

| Kiểm tra | Trường hợp phải hoạt động | Trường hợp phải bị từ chối |
|---|---|---|
| HTTPS/TLS | Endpoint đúng hostname, chuỗi chứng chỉ hợp lệ | Certificate sai tên, hết hạn hoặc không tin cậy |
| Authentication | Credential/token hợp lệ | Credential không hợp lệ hoặc token hết hạn |
| Authorization | User/role có quyền hợp lệ | Role không được cấp quyền |
| Reflection | Framework truy cập DTO được mở theo hợp đồng | Không tùy ý truy cập JDK internal/private member ngoài phạm vi |
| Deserialization | Object thuộc schema/allowlist hợp lệ | Class không được phép hoặc object graph vượt giới hạn |
| Filesystem | Process đọc file cấu hình và secret cần thiết | Process khác/role khác không được đọc secret |
| Crypto | Dữ liệu hợp lệ được tạo/đọc theo chính sách | Thuật toán/key không được chấp thuận bị từ chối |
| Deployment | Container chạy trên JDK mục tiêu | Không tự động mở quyền toàn bộ hệ thống để vượt lỗi |

Các negative test nên được thiết kế và vận hành an toàn, không phải cố khai thác lỗ hổng trên môi trường production. Mục đích là chứng minh kiểm soát vẫn có hiệu lực trong phạm vi được phép kiểm thử.

### 15.1. Ví dụ kiểm thử logic quyền truy cập

Giả sử một API nghiệp vụ có interface:

~~~java
public interface ReportService {
    Report readReport(UserContext user, String reportId);
}
~~~

Một bộ test contract có thể kiểm tra:

~~~java
@Test
void authorizedUserCanReadReport() {
    Report result = service.readReport(
            userWithReportReadPermission(),
            "R-42");

    assertNotNull(result);
}

@Test
void unauthorizedUserIsRejected() {
    assertThrows(
            AccessDeniedException.class,
            () -> service.readReport(
                    userWithoutReportReadPermission(),
                    "R-42"));
}
~~~

Đây là mã minh họa kiểu JUnit; `UserContext`, `AccessDeniedException` và fixtures là kiểu của ứng dụng giả định. Một migration chỉ đạt phần tương thích chức năng nếu test thứ nhất pass nhưng test thứ hai fail là chưa an toàn.

## 16. Cấu hình an toàn không nên bị trộn lẫn giữa các môi trường

Có những nhóm cờ và cấu hình khác vai trò:

- JVM system properties và security properties.
- `module-info.java`, `--add-opens`, `--add-exports`.
- Truststore, keystore, certificate chain.
- Container permissions, secret mount, network policy.
- Build tool daemon args, test JVM args và application JVM args.
- Framework security config, authentication và authorization rules.

Chúng có thể nằm trong những tiến trình hoặc tầng hạ tầng khác nhau.

Ví dụ, cấu hình `--add-opens` cho Gradle test task:

~~~kotlin
tasks.withType<Test>().configureEach {
    jvmArgs(
        "--add-opens=java.base/java.lang=ALL-UNNAMED"
    )
}
~~~

chỉ có tác dụng với JVM của test task được cấu hình, không có nghĩa Docker container production đã nhận cùng argument. Ngược lại, bổ sung truststore cho server production không tự sửa test worker ở CI.

Cần gắn từng thay đổi cấu hình với tiến trình phát sinh lỗi. Trong migration, ưu tiên giữ môi trường nhất quán bằng cấu hình và tài liệu rõ ràng, không bằng cách sao chép quyền rộng sang mọi nơi.

## 17. Những lưu ý khi xử lý bản cập nhật bảo mật trong cùng JDK

Không phải vấn đề tương thích bảo mật chỉ xuất hiện khi đổi feature release từ Java 11 sang 17 hoặc từ 17 sang 21. Một bản cập nhật JDK cùng nhánh có thể đưa vào bản vá, thay đổi thuật toán bị hạn chế, CA, dữ liệu thời gian hoặc hành vi liên quan tới bảo mật.

Vì vậy, hồ sơ nên ghi:

| Thông tin | Ví dụ cần lưu |
|---|---|
| Feature release | Java 17 |
| Update/build | Chuỗi version đầy đủ từ `java -version` |
| Vendor/distribution | JDK provider thực tế |
| OS/architecture | Linux x64, Windows x64 hoặc môi trường tương ứng |
| TLS endpoint | Hostname và cổng, không ghi secret |
| Trust configuration | Truststore/CA được chọn, đường dẫn quản trị |
| Dependency | HTTP client, provider, framework version |
| Runtime arguments | Chỉ các cờ liên quan, bảo mật thông tin nhạy cảm |
| Evidence | Log, test report, certificate chain validation |
| Decision | Secure fix, temporary exception hoặc blocked |

Nếu tổ chức sử dụng nhiều JDK distribution, mỗi bản build mục tiêu nên được kiểm chứng trong phạm vi cần thiết. Không suy ra bản vá và truststore của các distribution giống hệt nhau chỉ vì cùng Java feature version.

## 18. Phân biệt workaround chấp nhận được với cấu hình không được duy trì

Một biện pháp tạm thời có thể được cân nhắc nếu đáp ứng các điều kiện:

1. Chẩn đoán đã xác định nguyên nhân gốc và giới hạn tác động.
2. Không có sửa gốc khả thi ngay trong thời gian triển khai.
3. Phạm vi mở quyền được giới hạn chặt chẽ.
4. Rủi ro được đánh giá và phê duyệt bởi người có thẩm quyền.
5. Có kiểm soát bù đắp, giám sát và cơ chế rollback.
6. Có owner và thời hạn để nâng dependency/sửa kiến trúc.
7. Có negative tests chứng minh các kiểm soát quan trọng vẫn hoạt động.
8. Workaround được đưa vào danh sách nợ kỹ thuật và không trở thành cấu hình mặc định không kiểm soát.

Một quyết định ví dụ:

~~~yaml
migrationException:
  id: "REFLECTION-01"
  affectedComponent: "legacy-serializer"
  targetJdk: "17"
  cause: "deep reflection to a JDK package"
  temporaryMeasure: "narrowly scoped --add-opens"
  status: "APPROVAL_REQUIRED"
  owner: "platform-team"
  exitCriteria:
    - "upgrade serializer to a supported version"
    - "remove JVM argument"
    - "pass integration tests without the exception"
~~~

Đây là mẫu quản lý ngoại lệ, không phải một phê duyệt thực tế. Trường hợp liên quan tới TLS yếu, trust-all hoặc bỏ kiểm tra authorization có thể không chấp nhận được ngay cả khi có thời hạn; phải tuân theo chính sách bảo mật chứ không tự cho phép vì có ticket.

## 19. Những hiểu lầm thường gặp

**“Ứng dụng chạy được sau khi tắt certificate validation nghĩa là đã sửa TLS.”** Không. Chỉ là bỏ một phép xác minh danh tính. Cần sửa certificate, chain, trust hoặc endpoint thực sự.

**“Bật lại mọi cipher cũ là cách duy nhất để giữ tương thích.”** Thường cần đánh giá và nâng peer/proxy. Nới chính sách trên toàn runtime có thể ảnh hưởng những kết nối khác.

**“Dùng `--add-opens` là sửa bảo mật.”** Đây là thay đổi quyền deep reflection theo JPMS, có thể hữu ích có giới hạn nhưng không thay thế việc loại bỏ phụ thuộc vào private internals.

**“Thấy `InaccessibleObjectException` là Java đã xóa class.”** Class/member có thể vẫn tồn tại; vấn đề thường là package không được mở cho module gọi.

**“Chỉ cần cấp `AllPermission` như SecurityManager cũ.”** Cấp quyền không giới hạn không tạo ra mô hình cô lập phù hợp với JDK mới.

**“Thay Java SecurityManager bằng class loader riêng là sandbox tương đương.”** Class loader không tự cung cấp cách ly bảo mật cần thiết cho mã không tin cậy.

**“Cho phép deserialize mọi class sẽ khôi phục tương thích.”** Nó loại bỏ giới hạn với dữ liệu đầu vào nguy hiểm. Phải xử lý schema, class và filter theo hợp đồng.

**“SSL handshake fail chắc chắn do một protocol cũ bị tắt.”** Handshake có thể fail vì certificate, hostname, CA, key, cipher, proxy hoặc cấu hình khác.

**“Cấu hình test đã sửa thì production tự sửa.”** Test runner, build daemon và production service là các JVM/process có thể khác nhau.

**“Bản patch JDK không thay đổi tương thích.”** Một bản cập nhật bảo mật có thể thay đổi chính sách thuật toán, certificate hoặc behavior đáng kể đối với hệ thống cũ.

**“Không còn warning đồng nghĩa hệ thống an toàn.”** Không có warning không phải bằng chứng mọi phép xác minh, phân quyền và chính sách vẫn được áp dụng.

## 20. Checklist trước khi chốt phương án migration

- [ ] Đã xác định chính xác JDK nguồn, JDK đích, update/build và vendor.
- [ ] Đã ghi lại stack trace/log gốc và code path gây lỗi.
- [ ] Đã phân biệt compile/linkage/runtime/configuration/security failure.
- [ ] Đã xác định kiểm soát bảo mật nào liên quan và vì sao nó từ chối thao tác.
- [ ] Đã ưu tiên sửa API, dependency, certificate, truststore hoặc peer.
- [ ] Không dùng trust-all, bỏ hostname verification hoặc mở quyền vô hạn làm giải pháp mặc định.
- [ ] Đã phân biệt `--add-opens` và `--add-exports` khi xử lý module.
- [ ] Đã kiểm kê phụ thuộc SecurityManager, policy hoặc sandbox kiểu cũ nếu có.
- [ ] Đã kiểm tra crypto provider, algorithm constraints và dữ liệu lịch sử liên quan.
- [ ] Đã kiểm tra deserialization filter và quyền truy cập filesystem/secret khi có tác động.
- [ ] Đã chạy positive tests chứng minh chức năng hợp lệ hoạt động.
- [ ] Đã chạy negative tests chứng minh truy cập không hợp lệ vẫn bị từ chối.
- [ ] Đã kiểm tra test worker, production JVM, container và những môi trường cần hỗ trợ.
- [ ] Workaround tạm thời có owner, phạm vi, phê duyệt, giám sát và exit criteria.
- [ ] Đã lưu bằng chứng, giới hạn kiểm thử, quyết định và kế hoạch rollback.

## Kết luận

**Sửa tương thích không đồng nghĩa khôi phục cấu hình bảo mật đã lỗi thời.** Việc nâng JDK có thể khiến những phụ thuộc cũ vào TLS yếu, certificate không hợp lệ, private JDK internals, SecurityManager hoặc quyền truy cập rộng không còn hoạt động. Thay vì tắt các kiểm soát để qua lỗi, cần xác định nguyên nhân, dùng API và cấu hình được hỗ trợ, nâng dependency/endpoint khi cần và kiểm thử cả trường hợp hợp lệ lẫn trường hợp phải bị từ chối.

Một migration thành công không chỉ chứng minh ứng dụng khởi động và phục vụ request, mà còn chứng minh những ranh giới bảo mật quan trọng vẫn được duy trì. Nếu phải dùng workaround, chỉ chấp nhận trong phạm vi đã đánh giá, có owner và kế hoạch loại bỏ. Cách tiếp cận này giữ được **tương thích có kiểm chứng** mà không biến một sự cố nâng cấp Java thành một điểm yếu bảo mật kéo dài.
