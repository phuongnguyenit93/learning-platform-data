# Thuộc tính jdk.crypto.disabledAlgorithms của Java 26

*Tình trạng được đối chiếu với JDK 26 tại ngày 27/11/2026.*

Java 26 bổ sung security property `jdk.crypto.disabledAlgorithms` để quản trị viên giới hạn thuật toán ở tầng JCA/JCE. Property này cho phép khai báo cặp **loại dịch vụ mật mã + tên thuật toán** mà JDK không được khởi tạo qua các factory tương ứng.

JDK 26 ban đầu hỗ trợ trực tiếp bốn service:

- `Cipher`
- `KeyStore`
- `MessageDigest`
- `Signature`

Property được định nghĩa trong file `java.security`. Giá trị mặc định ban đầu là không có thuật toán nào bị vô hiệu hóa bởi property mới. Đây là cấu hình bảo mật của JDK, không phải API Java mới, preview feature hay incubator module.

`jdk.crypto.disabledAlgorithms` áp dụng ở tầng JCA/JCE. Nó không thay thế `jdk.tls.disabledAlgorithms` cho giao thức/cipher suite TLS hoặc `jdk.certpath.disabledAlgorithms` cho kiểm tra certification path.

## 1. Mục đích và cách hoạt động

JCA (Java Cryptography Architecture) và JCE (Java Cryptography Extension) cung cấp các factory để ứng dụng yêu cầu dịch vụ mật mã từ provider đã đăng ký. Ví dụ:

- `Cipher.getInstance(...)` tạo bộ mã hóa/giải mã.
- `MessageDigest.getInstance(...)` tạo hàm băm.
- `Signature.getInstance(...)` tạo đối tượng ký hoặc xác minh chữ ký.
- `KeyStore.getInstance(...)` tạo kho khóa theo type được yêu cầu.

Property mới cung cấp một danh sách hạn chế tập trung cho bốn service được hỗ trợ. Trong JDK reference implementation, factory kiểm tra service và tên được yêu cầu trước khi trả về đối tượng. Nếu mục yêu cầu nằm trong danh sách bị chặn, factory từ chối tạo đối tượng.

Ví dụ, nếu chính sách chặn `MessageDigest.SHA-256`, lời gọi `MessageDigest.getInstance("SHA-256")` sẽ thất bại ngay ở bước tạo service. Ứng dụng chưa bắt đầu tính digest.

Cơ chế này giúp áp dụng chính sách nhất quán ngay cả khi lời gọi factory đến từ thư viện phụ thuộc. Nó không thay thế việc chọn thuật toán an toàn, quản lý khóa, xác thực certificate hoặc thiết kế giao thức đúng cách.

## 2. Phạm vi service được hỗ trợ

| Service | Đối tượng được kiểm soát | Ví dụ tên |
|---|---|---|
| `Cipher` | Transformation mã hóa/giải mã | `AES/GCM/NoPadding` |
| `KeyStore` | Loại kho khóa | `PKCS12` |
| `MessageDigest` | Thuật toán băm | `SHA-256` |
| `Signature` | Thuật toán chữ ký | `SHA256withRSA` |

Các tên trong bảng chỉ minh họa cú pháp. Không có nghĩa nên đưa những thuật toán này vào danh sách chặn production. Một chính sách thực tế phải dựa trên danh sách được security architect phê duyệt và nhu cầu tương thích của ứng dụng.

Property không phải bộ lọc tổng quát cho mọi lớp trong `java.security` hoặc `javax.crypto`. Các service như `Mac`, `KeyAgreement`, `KeyFactory`, `KeyPairGenerator`, `SecretKeyFactory`, `AlgorithmParameters` và `KEM` không nằm trong danh sách hỗ trợ ban đầu được công bố cho JDK 26. Không giả định rằng thêm tên service bất kỳ vào property sẽ khiến JDK kiểm soát service đó.

## 3. Cú pháp Service.Algorithm

Giá trị property là danh sách phân tách bằng dấu phẩy. Mỗi phần tử có dạng:

```text
Service.Algorithm
```

Trong đó:

- `Service` là một trong bốn service được hỗ trợ.
- `Algorithm` là tên chuẩn của thuật toán, loại KeyStore hoặc Cipher transformation tương ứng.
- Các mục được phân tách bằng dấu phẩy.
- Với Cipher, nên ghi transformation đầy đủ gồm thuật toán, mode và padding.

Ví dụ minh họa:

```properties
jdk.crypto.disabledAlgorithms=Cipher.AES/GCM/NoPadding, MessageDigest.SHA-256
```

Đây là cấu hình kiểm thử để xác nhận cơ chế từ chối hoạt động. Nó cố ý chặn AES-GCM và SHA-256 vốn là những lựa chọn hiện đại; không sao chép nguyên ví dụ này vào production nếu ứng dụng vẫn cần chúng.

Đối với Cipher, tên transformation đầy đủ giúp chính sách xác định chính xác biến thể cần hạn chế. `AES/GCM/NoPadding` khác `AES/CBC/PKCS5Padding`. Không rút gọn tên theo suy đoán rằng một mục sẽ bao phủ mọi mode và padding.

Đối với MessageDigest và Signature, sử dụng tên theo Java Security Standard Algorithm Names, ví dụ `SHA-256` hoặc `SHA256withRSA`. Với KeyStore, sử dụng tên type mà ứng dụng truyền vào `KeyStore.getInstance()`, ví dụ `PKCS12`.

Không tự đặt alias riêng hoặc tên hiển thị trong giao diện provider. Hãy đối chiếu tên được ứng dụng thực sự truyền vào factory và tên chuẩn được JDK công bố.

## 4. Factory từ chối thuật toán như thế nào?

Trong JDK reference implementation, các factory của bốn service kiểm tra `jdk.crypto.disabledAlgorithms` trước khi trả về đối tượng:

1. Ứng dụng yêu cầu một service và thuật toán/type.
2. Factory kiểm tra service và tên được yêu cầu với danh sách hạn chế.
3. Nếu bị chặn, factory từ chối lời gọi.
4. Nếu không bị chặn, JDK tiếp tục tìm provider phù hợp và tạo đối tượng như thông thường.

Chỉ định provider cụ thể cũng không phải cách vượt qua chính sách. Các overload `getInstance(algorithm, provider)` và `getInstance(algorithm, Provider)` của những factory được hỗ trợ vẫn được JDK reference implementation kiểm tra.

### Ngoại lệ thường gặp

| Service | Factory | Ngoại lệ khi mục bị chặn |
|---|---|---|
| Cipher | `Cipher.getInstance(...)` | `NoSuchAlgorithmException` |
| MessageDigest | `MessageDigest.getInstance(...)` | `NoSuchAlgorithmException` |
| Signature | `Signature.getInstance(...)` | `NoSuchAlgorithmException` |
| KeyStore | `KeyStore.getInstance(...)` | `KeyStoreException` |

Với Cipher, `NoSuchPaddingException` vẫn có thể xuất hiện khi provider không hỗ trợ padding được yêu cầu. Đó là nguyên nhân khác với việc policy chặn transformation. Hãy đọc exception và cấu hình hiệu lực để phân biệt lỗi chính sách với lỗi provider hoặc tên transformation.

## 5. Phân biệt với các property khác

Java đã có các property chuyên biệt cho những ngữ cảnh bảo mật. `jdk.crypto.disabledAlgorithms` bổ sung lớp kiểm soát JCA/JCE, không thay thế các property chuyên biệt.

| Property | Phạm vi chính | Ví dụ nơi áp dụng |
|---|---|---|
| `jdk.crypto.disabledAlgorithms` | Thuật toán/type của bốn JCA/JCE service được hỗ trợ | Tạo Cipher, KeyStore, MessageDigest, Signature |
| `jdk.tls.disabledAlgorithms` | Protocol, cipher suite, key exchange và thành phần liên quan trong TLS/DTLS | JSSE thương lượng kết nối |
| `jdk.certpath.disabledAlgorithms` | Thuật toán và điều kiện bị cấm trong xác minh certification path | PKIX/CertPath validation |
| `jdk.jar.disabledAlgorithms` | Thuật toán và điều kiện liên quan đến xác minh chữ ký JAR | Kiểm tra JAR đã ký |

Ví dụ:

- Muốn giới hạn transformation mà ứng dụng có thể khởi tạo qua `Cipher.getInstance()`, xem `jdk.crypto.disabledAlgorithms`.
- Muốn giới hạn TLS 1.2/1.3, cipher suite hoặc thành phần thương lượng TLS, xem `jdk.tls.disabledAlgorithms`.
- Muốn giới hạn thuật toán được chấp nhận khi xác minh chuỗi certificate, xem `jdk.certpath.disabledAlgorithms`.
- Muốn áp dụng chính sách cho chữ ký JAR, xem property chuyên biệt của JAR.

Một thuật toán có thể được dùng ở nhiều ngữ cảnh. Việc chặn một Cipher transformation tại JCA/JCE không đồng nghĩa đã cấu hình đầy đủ chính sách TLS; ngược lại, giới hạn TLS không tự động trở thành danh sách chặn cho mọi lời gọi Cipher độc lập trong ứng dụng.

Nếu ứng dụng dùng JSSE, một hạn chế ở tầng JCA/JCE có thể khiến service mật mã mà JSSE cần không thể được tạo. Vì vậy, cần kiểm thử cả việc tạo service trực tiếp và các luồng TLS thực tế.

## 6. Giá trị mặc định trong JDK 26

JDK 26 giới thiệu property này với giá trị mặc định ban đầu là không có thuật toán nào bị chặn bởi `jdk.crypto.disabledAlgorithms`.

Điều đó không có nghĩa JDK 26 mặc định cho phép mọi thuật toán trong mọi ngữ cảnh. Các property khác như `jdk.tls.disabledAlgorithms` hoặc `jdk.certpath.disabledAlgorithms` đã có chính sách riêng và có thể chặn thuật toán trong phạm vi của chúng.

Không nên giả định giá trị mặc định sẽ luôn rỗng ở các bản JDK sau. Release notes nói rõ danh sách mặc định có thể thay đổi trong tương lai. Khi nâng JDK, cần kiểm tra file `conf/security/java.security` của bản phân phối đang triển khai và kiểm thử ứng dụng với chính sách mới.

## 7. Cấu hình trong file security properties

Khi khởi chạy JDK, security properties mặc định được đọc từ:

```text
<java-home>/conf/security/java.security
```

Có thể thêm hoặc điều chỉnh property trong file này:

```properties
jdk.crypto.disabledAlgorithms=Cipher.AES/GCM/NoPadding, MessageDigest.SHA-256
```

Không nên sửa trực tiếp file cấu hình đi kèm JDK một cách tùy tiện trong quy trình triển khai. Một cách dễ quản lý hơn là tạo file policy riêng, lưu trong hệ thống cấu hình được kiểm soát và nạp bổ sung khi chạy.

Ví dụ file `crypto-policy.security`:

```properties
# Ví dụ kiểm thử trong môi trường cô lập.
jdk.crypto.disabledAlgorithms=MessageDigest.SHA-256
```

Khởi chạy ứng dụng với file bổ sung:

```bash
java -Djava.security.properties=file:/etc/myapp/crypto-policy.security -cp app.jar com.example.Main
```

Dạng `-Djava.security.properties=<URL>` bổ sung nội dung file được chỉ định vào master security properties file. Các property cùng tên được xử lý theo quy tắc thứ tự của security properties; giá trị được định nghĩa sau có thể thay thế giá trị trước.

Có một dạng khác:

```bash
java -Djava.security.properties==file:/etc/myapp/complete-java.security -cp app.jar com.example.Main
```

Hai dấu bằng sau tên property yêu cầu JVM dùng file được chỉ định để thay thế hoàn toàn master security properties file. Cách này có thể làm mất các thiết lập mặc định về provider và bảo mật nếu file thay thế không khai báo đầy đủ chúng. Chỉ sử dụng khi bạn chủ động quản lý toàn bộ cấu hình JDK và đã kiểm thử tất cả security properties cần thiết.

## 8. Ghi đè bằng system property cùng tên

JDK 26 cho phép system property `jdk.crypto.disabledAlgorithms` ghi đè security property cùng tên.

Ví dụ:

```bash
java -Djdk.crypto.disabledAlgorithms=MessageDigest.SHA-256 -cp app.jar com.example.Main
```

Nếu system property này được đặt, giá trị của nó supersede giá trị trong security properties file. Không nên giả định hai danh sách sẽ tự động được hợp nhất.

Đây là điểm cần kiểm soát chặt trong production: một tham số JVM được thêm bởi script khởi chạy, container manifest hoặc cấu hình deployment có thể thay thế danh sách hạn chế được quản trị viên đặt trong `java.security`.

Một system property rỗng cũng là một giá trị được đặt. Vì vậy, nếu nó thay thế danh sách trong security properties file bằng chuỗi rỗng, các mục chặn trong file đó có thể không còn hiệu lực. Kiểm soát quyền thay đổi JVM arguments và xác minh cấu hình cuối cùng khi khởi động.

Chỉ dùng cơ chế override khi có yêu cầu tương thích được phê duyệt, có phạm vi ứng dụng cụ thể, thời hạn xử lý và kiểm thử bảo mật. Không đưa một system property override rộng vào image/container dùng chung nếu mục tiêu là duy trì chính sách chặn tập trung.

## 9. Thay đổi property bằng code

Java có phương thức:

```java
Security.setProperty("jdk.crypto.disabledAlgorithms",
        "MessageDigest.SHA-256");
```

Tuy nhiên, việc đặt security property bằng code không bảo đảm mọi thành phần sẽ nhận giá trị mới ở bất kỳ thời điểm nào. Tài liệu Oracle lưu ý rằng một số security properties có thể đã được đọc và cache khi lớp `java.security.Security` được khởi tạo. Nếu đặt quá muộn, thay đổi có thể không được áp dụng và không nhất thiết phát sinh exception.

Vì vậy:

- Ưu tiên cấu hình tĩnh trong security properties file hoặc JVM startup options.
- Nếu buộc phải đặt bằng code, thực hiện ở giai đoạn khởi động sớm nhất, trước khi các dịch vụ mật mã liên quan được khởi tạo.
- Không thay đổi danh sách hạn chế giữa lúc ứng dụng đang xử lý request.
- Sau khi cấu hình, kiểm tra lại giá trị hiệu lực và thực hiện bài test tạo service bị chặn.

Không dùng `System.setProperty()` thay cho `Security.setProperty()` khi mục tiêu là thay đổi security property. Đây là hai namespace cấu hình khác nhau, dù property này có cơ chế system-property override được JDK công bố.

## 10. Ví dụ kiểm thử một thuật toán bị chặn

Tạo file policy riêng chỉ dành cho bài test:

```properties
jdk.crypto.disabledAlgorithms=MessageDigest.SHA-256
```

Ví dụ Java:

```java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public class CryptoPolicyCheck {
    public static void main(String[] args) {
        try {
            MessageDigest.getInstance("SHA-256");
            throw new AssertionError(
                    "SHA-256 should have been blocked by the test policy"
            );
        } catch (NoSuchAlgorithmException expected) {
            System.out.println("Policy applied: " + expected.getMessage());
        }
    }
}
```

Biên dịch và chạy trên JDK 26:

```bash
javac --release 26 CryptoPolicyCheck.java
java -Djava.security.properties=file:/etc/myapp/crypto-policy.security CryptoPolicyCheck
```

Kết quả mong đợi là factory từ chối tạo MessageDigest và chương trình in thông báo xác nhận policy đã được áp dụng.

Đây là bài test âm tính: SHA-256 là thuật toán băm được hỗ trợ rộng rãi và thường vẫn cần trong ứng dụng. Chặn nó ở đây chỉ nhằm chứng minh cơ chế hoạt động trong môi trường cô lập. Không sử dụng danh sách kiểm thử này làm cấu hình production.

Nếu chương trình vẫn tạo được MessageDigest, kiểm tra:

1. Ứng dụng có thực sự chạy bằng JDK 26 dự kiến không?
2. URL của file security properties có chính xác và file có đọc được không?
3. Có system property `-Djdk.crypto.disabledAlgorithms` ghi đè danh sách không?
4. Tên service và thuật toán có đúng chính tả, đúng tên chuẩn không?
5. Bản JDK đang dùng có triển khai property này không?
6. File cấu hình bổ sung có bị một khai báo cùng tên ở vị trí xử lý sau ghi đè không?

## 11. Kiểm tra cấu hình đang có hiệu lực

Có thể xem tổng quan security settings bằng:

```bash
java -XshowSettings:security -version
```

Để theo dõi việc đọc security properties và các file include:

```bash
java -Djava.security.debug=properties -Djava.security.properties=file:/etc/myapp/crypto-policy.security -cp app.jar com.example.Main
```

Thông tin debug giúp xác định:

- Security properties nào đã được nạp.
- File master và file bổ sung được xử lý như thế nào.
- Giá trị cuối cùng sau khi xử lý các khai báo và include.
- Có khai báo nào bị ghi đè theo thứ tự hay không.

JDK 26 cũng hỗ trợ sự kiện JFR `jdk.InitialSecurityProperty` để ghi nhận giá trị security property ban đầu trong một tiến trình. Có thể dùng JFR khi cần lưu bằng chứng cấu hình lúc khởi động hoặc đối chiếu giữa các môi trường.

Đừng chỉ nhìn file policy rồi kết luận ứng dụng đã dùng đúng chính sách. Cần xác nhận JVM thực tế nhận file đó, không có system property override ngoài dự kiến và factory của service bị chặn thực sự từ chối lời gọi.

## 12. Ảnh hưởng đến provider và thư viện bên thứ ba

JCA/JCE dùng kiến trúc provider. Ứng dụng thường gọi factory chuẩn và để JDK chọn provider theo thứ tự ưu tiên. Property này được JDK reference implementation kiểm tra ở các factory thuộc bốn service hỗ trợ trước khi tạo đối tượng.

Điều đó có một số hệ quả:

- Gọi provider theo tên không phải cách bỏ qua danh sách chặn.
- Một thư viện bên thứ ba dùng `Cipher.getInstance()` hoặc `MessageDigest.getInstance()` vẫn có thể bị policy ảnh hưởng.
- Khi một thư viện bắt `NoSuchAlgorithmException` rồi đổi sang thuật toán khác, hành vi fallback cần được kiểm tra để bảo đảm không làm yếu chính sách.
- Một thư viện có thể thất bại ngay lúc khởi động nếu nó tạo sẵn một service đã bị chặn.
- Provider riêng hoặc implementation không tuân theo JDK reference behavior có thể có khác biệt; cần kiểm thử đúng JDK vendor và provider đang triển khai.

Tài liệu Oracle nêu rõ các security properties này không được bảo đảm sẽ được mọi implementation JDK khác sử dụng. Vì vậy, nếu hệ thống dùng nhiều vendor JDK, hãy xác minh hỗ trợ của từng vendor thay vì giả định tên property là một hợp đồng Java SE phổ quát.

## 13. Quy trình đưa chính sách vào production

Một thay đổi ở tầng mật mã có thể làm hỏng tính tương thích của ứng dụng, thư viện, định dạng dữ liệu hoặc hệ thống tích hợp. Nên triển khai theo từng bước:

1. **Kiểm kê service:** tìm các lời gọi tạo Cipher, KeyStore, MessageDigest và Signature trong ứng dụng cùng dependency.
2. **Xác định policy:** security architect phê duyệt service/algorithm cần chặn và lý do.
3. **Tạo profile riêng:** lưu danh sách trong file security properties được quản lý phiên bản và quyền truy cập.
4. **Kiểm thử âm tính:** xác nhận các service trong deny-list không thể được tạo.
5. **Kiểm thử dương tính:** xác nhận các service hợp lệ vẫn tạo được và các luồng nghiệp vụ quan trọng hoạt động.
6. **Kiểm thử tích hợp:** chạy TLS, xác minh certificate, ký/xác minh dữ liệu, đọc keystore và các tác vụ mã hóa có liên quan.
7. **Triển khai thử:** áp dụng cho môi trường canary hoặc một nhóm instance trước.
8. **Quan sát lỗi:** theo dõi NoSuchAlgorithmException, KeyStoreException, lỗi khởi động và các fallback trong thư viện.
9. **Mở rộng:** chỉ triển khai toàn bộ sau khi đã xác nhận tương thích.
10. **Rà soát khi nâng JDK:** so sánh security properties mặc định, provider và release notes của JDK mới.

Không thêm thuật toán vào danh sách chỉ vì tên của nó xuất hiện trong một báo cáo. Cần biết service nào yêu cầu thuật toán đó, ứng dụng nào còn phụ thuộc và phương án thay thế đã được kiểm chứng.

## 14. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Property này chặn mọi thuật toán mật mã trong Java | JDK 26 ban đầu chỉ hỗ trợ Cipher, KeyStore, MessageDigest và Signature |
| Nó thay thế `jdk.tls.disabledAlgorithms` | Hai property có phạm vi khác nhau |
| Nó thay thế `jdk.certpath.disabledAlgorithms` | Certificate path validation vẫn có chính sách riêng |
| Mặc định Java 26 đã chặn một danh sách thuật toán bằng property này | Giá trị mặc định ban đầu là không có thuật toán bị chặn bởi property mới |
| Thêm `-Djdk.crypto.disabledAlgorithms` sẽ cộng thêm vào file `java.security` | System property cùng tên ghi đè giá trị security property |
| Chỉ cần sửa file là chắc chắn JVM đã dùng policy | Phải xác minh file được nạp và giá trị hiệu lực |
| Đặt `Security.setProperty()` ở bất kỳ thời điểm nào cũng có hiệu lực | Một số property có thể đã được đọc và cache |
| Chỉ định provider cụ thể sẽ vượt qua danh sách chặn | Factory của JDK reference implementation vẫn kiểm tra property |
| Đây là API Java preview | Đây là security property của JDK 26, không phải preview/incubator |

## 15. Checklist vận hành

- [ ] Đã xác nhận JDK vendor và release hỗ trợ `jdk.crypto.disabledAlgorithms`.
- [ ] Đã xác định đúng bốn service thuộc phạm vi hỗ trợ.
- [ ] Đã dùng tên service và tên thuật toán theo chuẩn JCA/JCE.
- [ ] Với Cipher, đã ghi rõ transformation cần kiểm soát.
- [ ] Danh sách chặn đã được security architect phê duyệt.
- [ ] Đã phân biệt property này với TLS và CertPath restrictions.
- [ ] Đã kiểm soát `java.security.properties` và các file include.
- [ ] Đã kiểm tra system property cùng tên có ghi đè security property hay không.
- [ ] Đã kiểm thử factory bị chặn và factory hợp lệ.
- [ ] Đã kiểm thử các thư viện và provider thực tế.
- [ ] Đã xác minh cấu hình cuối bằng `-XshowSettings:security` hoặc `java.security.debug=properties`.
- [ ] Đã kiểm tra lại policy sau khi nâng JDK.

## Tài liệu tham chiếu

1. [Oracle JDK 26 Release Notes – New Security Property jdk.crypto.disabledAlgorithms (JDK-8244336)](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html)
2. [Oracle Java SE 26 – Java Secure Socket Extension (JSSE) Reference Guide: Disabled and Restricted Cryptographic Algorithms](https://docs.oracle.com/en/java/javase/26/security/java-secure-socket-extension-jsse-reference-guide.html)
3. [Oracle Java SE 26 – The Security Properties File](https://docs.oracle.com/en/java/javase/26/security/security-properties-file.html)
4. [Oracle Java SE 26 API – Cipher](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/Cipher.html)
5. [Oracle Java SE 26 API – MessageDigest](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/MessageDigest.html)
6. [Oracle Java SE 26 API – Signature](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Signature.html)
7. [Oracle Java SE 26 API – KeyStore](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/KeyStore.html)
8. [Oracle Java SE 26 – System Properties](https://docs.oracle.com/en/java/javase/26/docs/api/system-properties.html)

