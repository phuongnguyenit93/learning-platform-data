# Security property trong Java

**Security property** là thuộc tính cấu hình bảo mật được Java lưu trong kho thuộc tính toàn cục do lớp `java.security.Security` quản lý. Các thuộc tính này điều khiển một số hành vi bảo mật của JDK, chẳng hạn thứ tự security provider, thuật toán bị hạn chế trong TLS hoặc certificate path, loại keystore mặc định và cấu hình nguồn ngẫu nhiên mật mã.

Security property thường được khai báo trong tệp `java.security` của JDK. Ứng dụng có thể đọc bằng `Security.getProperty()` và, trong những trường hợp phù hợp, thay đổi trong tiến trình bằng `Security.setProperty()`. Chúng có cơ chế riêng, khác với system property được đọc bằng `System.getProperty()`.

Hiểu đúng security property rất quan trọng khi cấu hình TLS, certificate validation, cryptographic provider, keystore và nâng cấp JDK. Một giá trị cấu hình sai có thể làm kết nối bảo mật thất bại, khiến thuật toán yếu được chấp nhận hoặc làm ứng dụng không tìm thấy provider cần thiết.

## 1. Security property là gì?

Java có nhiều lớp cấu hình. Security property là một phần của cấu hình bảo mật nền tảng, được tập trung trong lớp `java.security.Security`.

Một số security property phổ biến:

| Security property | Vai trò |
|---|---|
| `security.provider.n` | Đăng ký provider và xác định thứ tự ưu tiên |
| `keystore.type` | Loại keystore mặc định |
| `jdk.tls.disabledAlgorithms` | Thuật toán/protocol bị vô hiệu hóa trong TLS |
| `jdk.certpath.disabledAlgorithms` | Thuật toán hoặc kích thước khóa bị hạn chế khi xác thực certificate path |
| `jdk.jar.disabledAlgorithms` | Thuật toán bị hạn chế khi xác minh chữ ký JAR |
| `crypto.policy` | Chính sách giới hạn mật mã của JDK |
| `securerandom.source` | Nguồn seed cho SecureRandom theo cấu hình/provider |
| `ssl.KeyManagerFactory.algorithm` | Thuật toán mặc định cho KeyManagerFactory của JSSE |
| `ssl.TrustManagerFactory.algorithm` | Thuật toán mặc định cho TrustManagerFactory của JSSE |

Các thuộc tính này thường được JDK hoặc security provider đọc để quyết định cách cung cấp dịch vụ mật mã. Không phải mọi key trong file đều được mọi ứng dụng sử dụng; một property chỉ có tác dụng khi thành phần tương ứng hiểu và đọc nó.

Security property có thể chứa danh sách thuật toán, tên provider, tên loại keystore hoặc giá trị cấu hình khác. Tên property phân biệt chữ hoa/chữ thường theo quy tắc của Properties; hãy sao chép đúng tên trong tài liệu của JDK thay vì tự đặt biến thể.

## 2. Phân biệt security property và system property

Đây là điểm dễ nhầm nhất. Hai loại thuộc tính có API đọc khác nhau và được nạp từ những nguồn cấu hình khác nhau.

| Nội dung | Security property | System property |
|---|---|---|
| API đọc | `Security.getProperty(name)` | `System.getProperty(name)` |
| API đặt lúc chạy | `Security.setProperty(name, value)` | `System.setProperty(name, value)` |
| Nguồn cấu hình chính | `java.security` và file security bổ sung | Tham số `-Dname=value`, môi trường launcher hoặc code |
| Phạm vi | Cấu hình bảo mật toàn JVM | Cấu hình hệ thống của tiến trình |
| Ví dụ | `keystore.type`, `jdk.tls.disabledAlgorithms` | `javax.net.ssl.trustStore`, `https.protocols` |

Ví dụ, `keystore.type` là security property, còn `javax.net.ssl.trustStore` là system property dùng để chỉ định truststore cho JSSE.

Một số system property thường gặp khi cấu hình TLS:

- `javax.net.ssl.keyStore`: đường dẫn keystore dùng cho key material của ứng dụng.
- `javax.net.ssl.trustStore`: đường dẫn truststore.
- `javax.net.ssl.keyStoreType` và `javax.net.ssl.trustStoreType`: loại keystore/truststore.
- `javax.net.ssl.keyStorePassword` và `javax.net.ssl.trustStorePassword`: password tương ứng; không nên truyền secret trực tiếp trên command line.
- `https.protocols` và `jdk.tls.client.protocols`: cấu hình protocol TLS trong các ngữ cảnh JSSE tương ứng.
- `java.security.properties`: system property dùng để chỉ định file security properties bổ sung hoặc thay thế.
- `java.security.debug`: system property bật log chẩn đoán bảo mật.

Không thể dùng `System.setProperty("keystore.type", "JKS")` để thay security property `keystore.type`. Tương tự, `Security.setProperty("javax.net.ssl.trustStore", "...")` không thay thế system property mà JSSE dùng để tìm truststore.

## 3. Tệp java.security nằm ở đâu?

Trong JDK 9 trở lên, master security properties file thường nằm tại:

```text
$JAVA_HOME/conf/security/java.security
```

Trên Windows, đường dẫn tương ứng thường là:

```text
%JAVA_HOME%/conf/security/java.security
```

Các JDK cũ có thể dùng vị trí:

```text
$JAVA_HOME/lib/security/java.security
```

Master file chứa cấu hình mặc định của JDK, bao gồm provider, algorithm constraints, default keystore type và một số cấu hình bảo mật khác.

Có thể xác định thư mục Java đang chạy bằng:

```sh
java -XshowSettings:properties -version
```

Tìm giá trị `java.home` trong phần system properties. Lưu ý `java.home` là system property, không phải security property.

Tệp `java.security` thường dùng cú pháp dạng properties:

```properties
# Comment giải thích cấu hình
property.name=value
another.property=another-value
```

- Dòng bắt đầu bằng `#` là comment.
- Mỗi dòng cấu hình có dạng `tên=giá trị`.
- Giá trị có thể là tên thuật toán, danh sách, đường dẫn hoặc chuỗi tùy property.
- Một số property dùng danh sách phân tách bằng dấu phẩy; hãy giữ đúng cú pháp riêng của property đó.

Không sửa trực tiếp master file nếu có thể tránh. Bản cập nhật JDK có thể thay đổi hoặc ghi đè file này. Với cấu hình riêng của ứng dụng, nên quản lý file bổ sung riêng, lưu trong hệ thống quản lý cấu hình và áp dụng theo cách có thể tái lập.

## 4. Security property được nạp khi nào?

JDK đọc master security properties file khi lớp `java.security.Security` được khởi tạo. Các giá trị được đưa vào kho security properties toàn cục của tiến trình.

Điều này có hai hệ quả:

1. Cấu hình file cần được cung cấp trước khi ứng dụng và các security provider khởi tạo những thành phần phụ thuộc vào property.
2. Sửa file khi ứng dụng đang chạy không tự động làm JVM hiện tại nạp lại toàn bộ cấu hình.

Khi thay đổi `java.security` hoặc file bổ sung, hãy khởi động lại ứng dụng để xác nhận cấu hình mới được áp dụng. Trong hệ thống nhiều instance, cần triển khai đồng nhất và kiểm tra từng tiến trình sau restart.

Một số thành phần đọc property rồi cache giá trị khi khởi tạo. Vì vậy, thay đổi property sau khi TLS context, provider hoặc service tương ứng đã được tạo có thể không ảnh hưởng đến đối tượng hiện có.

## 5. Đọc security property bằng Security.getProperty()

API `Security.getProperty(String key)` trả về giá trị security property theo tên. Nếu key không tồn tại, kết quả là `null`.

Ví dụ đọc một số property:

```java
import java.security.Security;

public class ReadSecurityProperties {
    public static void main(String[] args) {
        String[] keys = {
            "keystore.type",
            "jdk.tls.disabledAlgorithms",
            "jdk.certpath.disabledAlgorithms",
            "crypto.policy"
        };

        for (String key : keys) {
            System.out.println(
                key + " = " + Security.getProperty(key));
        }
    }
}
```

Biên dịch và chạy trên JDK 17+:

```sh
javac ReadSecurityProperties.java
java ReadSecurityProperties
```

Kết quả hiển thị phụ thuộc JDK, vendor, phiên bản và file cấu hình được nạp. Một số giá trị như `jdk.tls.disabledAlgorithms` có thể rất dài vì chứa nhiều thuật toán hoặc điều kiện hạn chế.

Không nên chép nguyên một danh sách thuật toán từ JDK này sang JDK khác mà không kiểm tra tài liệu và giá trị mặc định của phiên bản đích.

## 6. Ví dụ phân biệt Security.getProperty và System.getProperty

Tạo file `SecurityPropertyDemo.java`:

```java
import java.security.Security;

public class SecurityPropertyDemo {
    public static void main(String[] args) {
        String key = "example.application.securityProfile";

        Security.setProperty(key, "production");

        System.out.println(
            "Security property: " + Security.getProperty(key));
        System.out.println(
            "System property: " + System.getProperty(key));
    }
}
```

Biên dịch và chạy:

```sh
javac SecurityPropertyDemo.java
java SecurityPropertyDemo
```

Stdout chính xác:

```text
Security property: production
System property: null
```

Ví dụ đặt một security property tùy chỉnh trong tiến trình. Vì chương trình không gọi `System.setProperty()` và không truyền `-Dexample.application.securityProfile=...`, system property cùng tên vẫn là `null`.

Property tùy chỉnh này chỉ có ý nghĩa nếu code của ứng dụng hoặc provider thực sự đọc nó. Việc thêm một key vào security property map không tự động làm JDK thay đổi hành vi.

## 7. Thay đổi security property lúc chạy bằng Security.setProperty()

API:

```java
Security.setProperty("property.name", "property.value");
```

Ví dụ:

```java
Security.setProperty("keystore.type", "PKCS12");
System.out.println(Security.getProperty("keystore.type"));
```

`Security.setProperty()` cập nhật giá trị trong security property map của JVM hiện tại. Nó không ghi ngược thay đổi vào file `java.security` và không thay đổi cấu hình của những tiến trình JVM khác.

Cần đặc biệt chú ý thời điểm gọi. Một số property không thể thay đổi có hiệu lực sau khi đã được đọc và cache trong quá trình khởi tạo lớp `Security` hoặc thành phần liên quan. Trong trường hợp đó, lời gọi `setProperty()` có thể không ném exception nhưng thành phần đã khởi tạo vẫn tiếp tục dùng giá trị cũ.

Nguyên tắc:

- Ưu tiên cấu hình lúc khởi động cho provider, TLS và algorithm constraints.
- Chỉ dùng `Security.setProperty()` khi tài liệu của property xác nhận có thể thay đổi ở thời điểm đó.
- Đặt property trước khi khởi tạo thành phần phụ thuộc.
- Không giả định một thay đổi runtime sẽ cập nhật các object đã được tạo.
- Kiểm tra giá trị qua `Security.getProperty()` và kiểm thử hành vi thực tế.

## 8. Thêm file security properties bằng java.security.properties

Có thể chỉ định file security properties bổ sung khi khởi chạy JVM bằng system property `java.security.properties`.

Ví dụ trên Linux/macOS:

```sh
java -Djava.security.properties=file:/opt/app/security-extra.properties -jar app.jar
```

Ví dụ trên Windows:

```powershell
java -Djava.security.properties=file:/C:/app/config/security-extra.properties -jar app.jar
```

Với cú pháp một dấu bằng trong giá trị property, file bổ sung được nạp thêm sau master file. Nếu cùng một key xuất hiện ở cả hai file, giá trị trong file bổ sung được nạp sau sẽ thay thế giá trị trước đó.

Ví dụ file `security-extra.properties`:

```properties
# Chỉ đặt loại keystore mặc định khi ứng dụng có yêu cầu tương thích rõ ràng.
keystore.type=PKCS12
```

Sau đó khởi chạy:

```sh
java -Djava.security.properties=file:/opt/app/security-extra.properties -jar app.jar
```

Đây là cách bổ sung hoặc override một số property mà không phải sao chép toàn bộ master file. Hãy giữ file bổ sung trong cấu hình triển khai có kiểm soát và bảo đảm JVM có quyền đọc file.

## 9. Phân biệt một dấu bằng và hai dấu bằng

Cú pháp có hai cách hoạt động khác nhau:

| Cú pháp | Hành vi |
|---|---|
| `-Djava.security.properties=file:/path/extra.security` | Nạp thêm file sau master security properties file |
| `-Djava.security.properties==file:/path/complete.security` | Dùng file chỉ định để thay thế hoàn toàn master file |

Hai dấu bằng có thể khiến các property mặc định của JDK không còn được nạp. Nếu file thay thế không đăng ký provider cần thiết hoặc bỏ các algorithm constraints quan trọng, ứng dụng có thể lỗi hoặc làm giảm mức bảo mật.

Chỉ dùng chế độ thay thế toàn bộ khi bạn quản lý đầy đủ nội dung file, hiểu mọi property bắt buộc của JDK/provider và kiểm thử trên đúng phiên bản runtime. Với phần lớn ứng dụng, file bổ sung dùng một dấu bằng là cách ít rủi ro hơn.

Khả năng dùng file bổ sung còn chịu ảnh hưởng của security property `security.overridePropertiesFile`. Trong cấu hình JDK tiêu chuẩn, property này thường là `true`; nếu được đặt `false` trong master file, việc chỉ định file bổ sung từ command line sẽ bị vô hiệu hóa.

## 10. Một số security property quan trọng

### 10.1. Provider order

Các key dạng `security.provider.1`, `security.provider.2`, ... xác định security provider và thứ tự ưu tiên khi JDK tìm implementation của một thuật toán.

Provider cung cấp các dịch vụ như:

- Message digest.
- Signature.
- Cipher.
- Key pair generation.
- KeyStore.
- SecureRandom.

Thứ tự provider ảnh hưởng provider nào được chọn khi ứng dụng yêu cầu một thuật toán mà không chỉ định provider cụ thể.

Có thể xem provider đã cài đặt:

```java
import java.security.Provider;
import java.security.Security;

public class ProviderList {
    public static void main(String[] args) {
        for (Provider provider : Security.getProviders()) {
            System.out.println(
                provider.getName() + " " + provider.getVersionStr());
        }
    }
}
```

Danh sách thực tế phụ thuộc JDK và provider được cài đặt. Không tự ý đổi thứ tự hoặc bỏ provider trong production nếu chưa kiểm tra thuật toán và thành phần đang phụ thuộc vào provider đó.

### 10.2. jdk.tls.disabledAlgorithms

`jdk.tls.disabledAlgorithms` quy định thuật toán hoặc protocol không được sử dụng trong TLS theo algorithm constraints của JDK.

Giá trị có thể bao gồm tên protocol/algorithm và điều kiện như kích thước khóa tối thiểu. Cấu hình mặc định thay đổi theo phiên bản JDK khi tiêu chuẩn bảo mật được cập nhật.

Không nên xóa một thuật toán khỏi danh sách chỉ để kết nối được với máy chủ cũ. Trước tiên hãy nâng TLS server/certificate hoặc cập nhật cấu hình phía đối tác. Nếu buộc phải thay đổi, cần đánh giá rủi ro, giới hạn phạm vi và có thời hạn loại bỏ ngoại lệ.

### 10.3. jdk.certpath.disabledAlgorithms

`jdk.certpath.disabledAlgorithms` áp dụng algorithm constraints trong quá trình xây dựng và xác minh certificate path.

Nó có thể hạn chế thuật toán chữ ký, loại khóa hoặc kích thước khóa của certificate trong chain. Property này khác với `jdk.tls.disabledAlgorithms`: một bên liên quan đến xác thực certificate path, bên kia áp dụng các ràng buộc trong TLS.

Nếu TLS handshake thất bại vì certificate chain dùng thuật toán không còn được chấp nhận, hãy kiểm tra chain, chữ ký và kích thước khóa trước khi xem xét thay đổi policy.

### 10.4. jdk.jar.disabledAlgorithms

`jdk.jar.disabledAlgorithms` quy định thuật toán bị hạn chế khi xác minh chữ ký JAR. Việc thay đổi property này có thể ảnh hưởng khả năng chấp nhận JAR đã ký bằng thuật toán cũ.

Nếu JAR nội bộ không còn được xác minh, kiểm tra chứng thư ký, thuật toán chữ ký và timestamp. Ưu tiên ký lại bằng thuật toán hiện được hỗ trợ thay vì nới lỏng toàn bộ policy.

### 10.5. keystore.type

`keystore.type` xác định loại keystore mặc định khi ứng dụng gọi `KeyStore.getDefaultType()`.

Từ JDK 9, PKCS12 là default type trong cấu hình JDK tiêu chuẩn. Hệ thống cũ hoặc security configuration tùy chỉnh có thể khác.

Nếu ứng dụng cần đọc một file cụ thể, nên chỉ định tường minh:

```java
KeyStore store = KeyStore.getInstance("JKS");
```

Cách này không phụ thuộc default type của runtime và làm rõ định dạng file cần đọc.

### 10.6. crypto.policy

`crypto.policy` điều khiển chính sách giới hạn mật mã của JDK. Từ JDK 9, cấu hình tiêu chuẩn thường dùng chính sách unlimited, nhưng cần kiểm tra runtime/provider thực tế khi nâng cấp hoặc dùng JDK tùy biến.

Không thay đổi property này chỉ để vượt qua lỗi thuật toán. Hãy xác định ứng dụng cần thuật toán nào, provider có hỗ trợ không và chính sách tổ chức cho phép đến đâu.

### 10.7. securerandom.source

`securerandom.source` liên quan nguồn seed được dùng trong cấu hình SecureRandom của JDK. Hành vi cụ thể phụ thuộc provider và nền tảng.

Không tự đặt nguồn entropy theo một đường dẫn giả định cho mọi hệ điều hành. Nếu SecureRandom khởi tạo chậm hoặc gặp lỗi, hãy kiểm tra provider, hệ điều hành, nguồn entropy và tài liệu của JDK đang chạy.

## 11. Kiểm tra security settings bằng java launcher

JDK 17+ hỗ trợ hiển thị cấu hình bảo mật qua:

```sh
java -XshowSettings:security -version
```

Có thể giới hạn phần hiển thị:

```sh
java -XshowSettings:security:properties -version
```

Các nhóm thông tin gồm security properties, security providers và cấu hình liên quan TLS. Lệnh này hữu ích để kiểm tra cấu hình thực tế mà runtime nhận được, thay vì chỉ đọc file trên đĩa.

Để debug việc nạp property:

```sh
java -Djava.security.debug=properties -jar app.jar
```

Log debug có thể in nhiều thông tin về property cuối cùng và quá trình nạp cấu hình. Chỉ bật khi điều tra, kiểm soát nơi lưu log và tránh ghi log nhạy cảm trong môi trường production.

## 12. Kiểm tra property trong JShell

Có thể kiểm tra nhanh giá trị security property mà không cần viết chương trình riêng:

```text
jshell> import java.security.Security;
jshell> Security.getProperty("keystore.type")
```

Kết quả tùy cấu hình JDK đang chạy. Để xem một số key khác:

```text
jshell> Security.getProperty("jdk.tls.disabledAlgorithms")
jshell> Security.getProperty("jdk.certpath.disabledAlgorithms")
jshell> Security.getProperty("security.provider.1")
```

So sánh với system property:

```text
jshell> System.getProperty("keystore.type")
```

Thông thường, lệnh cuối trả về `null` nếu không có system property cùng tên được đặt. Giá trị của security property không tự động xuất hiện trong system property map.

## 13. Security property và TLS configuration

Khi debug TLS, cần phân biệt ít nhất ba lớp cấu hình:

1. **Security properties:** algorithm constraints, provider và mặc định của dịch vụ bảo mật.
2. **System properties:** đường dẫn keystore/truststore, protocol được ứng dụng yêu cầu và một số tùy chọn JSSE.
3. **Certificate/key material:** private key, certificate chain và trusted CA trong keystore/truststore.

| Vấn đề | Cấu hình cần kiểm tra |
|---|---|
| Không tìm thấy truststore | `javax.net.ssl.trustStore` và file thực tế |
| Không đọc được keystore | `javax.net.ssl.keyStore`, type và password |
| Protocol TLS không được hỗ trợ | Cấu hình JSSE/system property và `jdk.tls.disabledAlgorithms` |
| Certificate chain bị từ chối | `jdk.certpath.disabledAlgorithms`, chain, issuer và thời hạn |
| Không tìm thấy thuật toán | Provider order, provider đã cài và thuật toán được hỗ trợ |
| Default keystore type không như mong đợi | `keystore.type` và `KeyStore.getDefaultType()` |

Không sửa `jdk.tls.disabledAlgorithms` khi nguyên nhân thực tế là truststore thiếu CA. Tương tự, import thêm CA không khắc phục được lỗi do protocol TLS hoặc cipher suite không tương thích.

## 14. Quy trình thay đổi security property an toàn

Trước khi thay đổi:

1. Xác định property chính xác và thành phần đọc property đó.
2. Ghi nhận giá trị hiện tại bằng `Security.getProperty()` hoặc `-XshowSettings:security`.
3. Đọc tài liệu JDK/provider cho đúng release.
4. Xác định thay đổi có ảnh hưởng toàn JVM hay chỉ ứng dụng.
5. Tạo file bổ sung riêng thay vì sửa master file nếu phù hợp.
6. Review security impact và tương thích với hệ thống tích hợp.
7. Khởi động tiến trình mới với cấu hình thử nghiệm.
8. Kiểm tra giá trị hiệu lực và provider được nạp.
9. Chạy test TLS, certificate validation, signing hoặc keystore liên quan.
10. Theo dõi log và có kế hoạch rollback.

Không thay đổi nhiều property cùng lúc nếu chưa biết property nào gây ra hành vi mới. Với algorithm constraints, hãy thay đổi từng mục và kiểm tra các loại certificate/protocol mà ứng dụng cần hỗ trợ.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Security.getProperty()` trả về `null` | Key không tồn tại, sai chữ hoa/thường hoặc file không được nạp | Kiểm tra tên property và file cấu hình thực tế |
| `System.getProperty()` trả về null nhưng Security API có giá trị | Đang đọc nhầm map thuộc tính | Dùng `Security.getProperty()` cho security property |
| File bổ sung không có tác dụng | Sai URL/path hoặc `security.overridePropertiesFile=false` | Kiểm tra đường dẫn, quyền đọc và property cho phép override |
| Thay đổi file nhưng ứng dụng vẫn dùng giá trị cũ | JVM đã khởi tạo Security/provider hoặc service cache giá trị | Restart tiến trình và kiểm tra lại |
| `Security.setProperty()` không thay đổi hành vi | Thành phần đã đọc/cached property trước đó | Đặt cấu hình lúc khởi động và tạo lại thành phần trong tiến trình mới |
| Dùng hai dấu bằng gây lỗi provider | File override toàn bộ master file và thiếu cấu hình bắt buộc | Dùng file bổ sung một dấu bằng hoặc quản lý đầy đủ file thay thế |
| TLS handshake thất bại sau nâng JDK | Algorithm/protocol/certificate cũ bị policy mới hạn chế | Kiểm tra TLS debug, certificate chain và disabled algorithms |
| Không tìm thấy KeyStore type | Provider không hỗ trợ type hoặc cấu hình provider sai | Kiểm tra `KeyStore.getInstance(type)` và provider |
| Provider không được chọn như mong muốn | Thứ tự `security.provider.n` hoặc provider runtime khác | Xem `Security.getProviders()` và cấu hình provider |
| Sửa master file bị mất sau cập nhật JDK | Bản cập nhật thay thế file cấu hình | Dùng file bổ sung được quản lý riêng và triển khai lại |

## 16. Phân biệt java.security với java.policy

`java.security` là file cấu hình các security property và provider của JDK. Nó không phải file policy permission.

`java.policy` là một khái niệm khác, gắn với mô hình policy/permission của SecurityManager truyền thống. Hai file có mục đích, cú pháp và cơ chế nạp khác nhau. Không đặt các dòng security property vào policy file hoặc ngược lại.

Khi đọc hướng dẫn cũ về SecurityManager, hãy kiểm tra phiên bản Java được nói đến. SecurityManager đã bị deprecated for removal và hành vi hỗ trợ thay đổi qua các JDK; không suy ra rằng mọi hướng dẫn policy cũ vẫn áp dụng cho mô hình bảo mật hiện đại.

## 17. Checklist

- [ ] Đã xác định key là security property hay system property.
- [ ] Đã đọc đúng master file `$JAVA_HOME/conf/security/java.security`.
- [ ] Đã dùng `Security.getProperty()` để đọc security property.
- [ ] Đã kiểm tra giá trị hiệu lực bằng `-XshowSettings:security` khi cần.
- [ ] Đã hiểu provider và algorithm constraints liên quan.
- [ ] Đã phân biệt TLS algorithm constraints với truststore/certificate configuration.
- [ ] Đã dùng file bổ sung riêng nếu cần override.
- [ ] Đã hiểu khác biệt giữa `java.security.properties` và `java.security.properties==`.
- [ ] Đã kiểm tra `security.overridePropertiesFile` khi file bổ sung không được áp dụng.
- [ ] Đã restart JVM sau thay đổi cấu hình tĩnh.
- [ ] Đã kiểm tra tác động của cache khi dùng `Security.setProperty()`.
- [ ] Đã kiểm thử TLS, certificate path, provider hoặc keystore liên quan.
- [ ] Đã lưu cấu hình, giá trị trước/sau và kế hoạch rollback.

## 18. Tài liệu tham khảo

- Oracle Java Security — The Security Properties File: https://docs.oracle.com/en/java/javase/21/security/security-properties-file.html
- Oracle Java Security — Troubleshooting Security: https://docs.oracle.com/en/java/javase/21/security/troubleshooting-security.html
- Java SE 21 API — `java.security.Security`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/Security.html
- Oracle JDK 21 Tool Reference — The `java` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html

Security property điều khiển những phần quan trọng của cấu hình bảo mật JVM. Hãy phân biệt nó với system property, kiểm tra giá trị hiệu lực bằng API và công cụ của JDK, ưu tiên cấu hình bổ sung có kiểm soát và kiểm thử sau mỗi thay đổi. Đặc biệt, không nới lỏng algorithm constraints chỉ để che một lỗi TLS chưa được xác định nguyên nhân.