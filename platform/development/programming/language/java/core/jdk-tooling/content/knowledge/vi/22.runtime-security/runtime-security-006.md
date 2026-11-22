# Disabled algorithm trong Java Security

**Disabled algorithm** là cơ chế chính sách bảo mật của JDK dùng để từ chối một thuật toán, giao thức, cipher suite hoặc khóa không còn đáp ứng yêu cầu an toàn. Các hạn chế này được áp dụng tại những điểm xử lý cụ thể như thương lượng TLS, xác thực certificate chain và xác minh chữ ký JAR.

Trong Java không có một danh sách duy nhất áp dụng giống nhau cho mọi thao tác mật mã. JDK chia chính sách theo mục đích sử dụng. Vì vậy, khi một kết nối TLS, certificate hoặc JAR bị từ chối do thuật toán, cần xác định đúng security property đang chi phối hoạt động đó trước khi điều chỉnh.

## 1. Vì sao cần disabled algorithms?

Một thuật toán từng được chấp nhận có thể trở nên yếu do tiến bộ phân tích mật mã, sức mạnh phần cứng tăng lên hoặc phát hiện lỗ hổng. Ví dụ, MD2, MD5, RC4 và các phiên bản giao thức SSL/TLS cũ không còn phù hợp với nhiều môi trường hiện đại.

JDK dùng danh sách disabled algorithms để ngăn ứng dụng vô tình sử dụng những lựa chọn đã bị loại khỏi chính sách bảo mật. Chính sách có thể hạn chế:

- Tên thuật toán, ví dụ MD5 hoặc RC4.
- Thuật toán chữ ký, ví dụ MD5withRSA.
- Độ dài khóa, ví dụ RSA key nhỏ hơn một ngưỡng bit.
- Phiên bản giao thức, ví dụ TLSv1 hoặc SSLv3.
- Cipher suite hoặc nhóm elliptic curve.
- Việc sử dụng thuật toán trong một ngữ cảnh cụ thể, ví dụ certificate chain dùng cho TLS server hoặc chữ ký JAR.

Disabled algorithm là một quyết định chính sách ở thời điểm một thành phần bảo mật kiểm tra thuật toán. Nó không xóa thuật toán khỏi mọi provider và không nhất thiết ngăn lập trình viên tạo đối tượng thuật toán ở mọi API. Một thao tác có thể tạo được chữ ký hoặc khóa nhưng bị từ chối khi certificate path được xác thực, khi JAR được xác minh hoặc khi TLS thương lượng kết nối.

## 2. Các security property quan trọng

JDK dùng các security property khác nhau cho từng miền:

| Security property | Phạm vi chính |
|---|---|
| `jdk.tls.disabledAlgorithms` | SSL/TLS/DTLS: phiên bản giao thức, cipher suite, named group, signature scheme, key exchange và peer authentication. |
| `jdk.certpath.disabledAlgorithms` | Xây dựng và xác thực certificate path, gồm thuật toán trong certificate, CRL và chữ ký OCSP. |
| `jdk.jar.disabledAlgorithms` | Thuật toán và độ dài khóa được phép khi xác minh chữ ký JAR. |
| `jdk.security.legacyAlgorithms` | Thuật toán yếu hoặc cũ mà công cụ như keytool và jarsigner có thể cảnh báo khi sử dụng. |
| `jdk.tls.legacyAlgorithms` | Thuật toán TLS còn được hỗ trợ nhưng có mức ưu tiên thấp hơn các lựa chọn tốt hơn. |
| `jdk.disabled.namedCurves` | Danh sách named curve có thể được đưa vào các danh sách disabled algorithms bằng cú pháp include. |

Các property trên không thay thế lẫn nhau. Ví dụ, thêm RC4 vào `jdk.tls.disabledAlgorithms` ảnh hưởng thương lượng TLS; thêm MD5 vào `jdk.jar.disabledAlgorithms` ảnh hưởng xác minh chữ ký JAR.

`jdk.security.legacyAlgorithms` và `jdk.tls.legacyAlgorithms` không đồng nghĩa với disabled. Legacy algorithm có thể vẫn được dùng trong những tình huống nhất định; disabled algorithm bị từ chối trong phạm vi chính sách áp dụng.

Không nên giả định mọi provider bên thứ ba đều đọc các property này. Tài liệu của JDK 24.0.2 ghi rõ một số chính sách được dùng bởi JDK Reference Implementation và không bảo đảm provider/implementation khác phải áp dụng cùng cách.

## 3. TLS disabled algorithms

`jdk.tls.disabledAlgorithms` kiểm soát các lựa chọn trong SSL, TLS và DTLS. Nó được dùng trong quá trình thương lượng:

- Phiên bản giao thức.
- Cipher suite.
- Named group và elliptic curve.
- Signature scheme.
- Xác thực peer.
- Cơ chế trao đổi khóa.

Ví dụ cấu hình của JDK 24.0.2 đang cài đặt:

~~~properties
jdk.tls.disabledAlgorithms=SSLv3, TLSv1, TLSv1.1, DTLSv1.0, RC4, DES, MD5withRSA, DH keySize < 1024, EC keySize < 224, 3DES_EDE_CBC, anon, NULL, ECDH, TLS_RSA_*
~~~

Giá trị thực tế có thể khác theo vendor, bản cập nhật JDK và chính sách của tổ chức.

Một số mục có ý nghĩa:

- `SSLv3`, `TLSv1` và `TLSv1.1`: không cho thương lượng các giao thức cũ này.
- `RC4`, `DES` và `3DES_EDE_CBC`: loại bỏ các thuật toán mã hóa không còn được khuyến nghị.
- `MD5withRSA`: hạn chế chữ ký dùng tổ hợp MD5 và RSA.
- `DH keySize < 1024`: từ chối khóa Diffie-Hellman nhỏ hơn 1024 bit.
- `EC keySize < 224`: từ chối khóa elliptic curve nhỏ hơn 224 bit.
- `TLS_RSA_*`: wildcard loại bỏ các cipher suite có tên bắt đầu bằng `TLS_RSA_`.

JDK kiểm tra các hạn chế này ngay cả khi ứng dụng chủ động bật giao thức hoặc cipher suite trong cấu hình. Vì vậy, gọi `SSLParameters.setProtocols` hoặc `setCipherSuites` không thể làm một thuật toán bị disabled trở lại thành lựa chọn hợp lệ.

Với xác thực peer và key exchange dựa trên PKI, các hạn chế TLS còn được kiểm tra trong quá trình xây dựng/xác thực certificate path và đối với thuật toán trong certificate, CRL hoặc chữ ký OCSP. Chúng được áp dụng bổ sung cùng `jdk.certpath.disabledAlgorithms`.

## 4. Certificate path disabled algorithms

`jdk.certpath.disabledAlgorithms` áp dụng khi JDK xây dựng và xác thực chuỗi certificate. Nó có thể hạn chế:

- Thuật toán chữ ký trong certificate.
- Độ dài khóa public key.
- Thuật toán dùng để ký CRL.
- Chữ ký của OCSP response.
- Thuật toán bị giới hạn trong một ngữ cảnh sử dụng cụ thể.

Ví dụ cấu hình JDK 24.0.2:

~~~properties
jdk.certpath.disabledAlgorithms=MD2, MD5, SHA1 jdkCA & usage TLSServer, RSA keySize < 1024, DSA keySize < 1024, EC keySize < 224, SHA1 usage SignedJAR & denyAfter 2019-01-01
~~~

Một certificate chain có thể bị từ chối dù certificate vẫn còn trong thời hạn hiệu lực. Nguyên nhân có thể là chữ ký dùng thuật toán bị cấm, khóa quá ngắn hoặc certificate được dùng trong ngữ cảnh bị hạn chế.

Theo cấu hình và implementation được kiểm tra, các hạn chế này không áp dụng cho trust anchor hoặc self-signed certificate. Cần phân biệt certificate đầu cuối với trust anchor: một certificate được dùng làm điểm tin cậy không nhất thiết chịu cùng phép kiểm tra như certificate trung gian trong đường dẫn.

Chính sách CertPath cũng phụ thuộc provider thực hiện PKIX. Không nên suy rộng kết quả của JDK Reference Implementation sang mọi provider tùy chỉnh.

## 5. Disabled algorithms cho chữ ký JAR

`jdk.jar.disabledAlgorithms` kiểm soát thuật toán và độ dài khóa dùng để xác minh signed JAR.

Ví dụ trên JDK 24.0.2:

~~~properties
jdk.jar.disabledAlgorithms=MD2, MD5, RSA keySize < 1024, DSA keySize < 1024, SHA1 denyAfter 2019-01-01
~~~

JAR được ký bằng thuật toán hoặc độ dài khóa bị cấm có thể bị xử lý như JAR chưa ký. Điều này ảnh hưởng trực tiếp tới ứng dụng dựa vào code signing để xác định nguồn gốc và tính toàn vẹn của thư viện.

Tùy chọn `denyAfter` cho phép giới hạn theo ngày. Với chính sách JAR, JAR được ký và timestamp trước ngày giới hạn có thể không bị áp dụng hạn chế đó. Timestamp cần được xác minh và được xử lý theo quy tắc của JDK; không thể chỉ dựa vào ngày sửa file hoặc thời gian trên máy người dùng.

Khi một JAR bị xem như chưa ký, ứng dụng có thể không còn nhận được các bảo đảm hoặc quyền truy cập vốn dựa trên signer. Hãy kiểm tra manifest, certificate chain, timestamp và chính sách chữ ký trước khi kết luận file JAR bị hỏng.

## 6. Legacy algorithms khác disabled algorithms

JDK có hai khái niệm cần phân biệt:

**Disabled:** thuật toán không được phép dùng trong phạm vi chính sách. Việc ứng dụng bật nó trong cấu hình không vượt qua được hạn chế đó.

**Legacy:** thuật toán vẫn được hỗ trợ nhưng không được ưu tiên. Trong TLS, thuật toán legacy thường chỉ được thương lượng khi không có lựa chọn phù hợp khác. Nếu một thuật toán đồng thời bị liệt kê trong `jdk.tls.disabledAlgorithms` hoặc bị chặn bởi `AlgorithmConstraints`, nó bị vô hiệu hóa hoàn toàn.

Ví dụ:

~~~properties
jdk.tls.legacyAlgorithms=NULL, anon, RC4, DES, 3DES_EDE_CBC
~~~

Các mục này là lựa chọn legacy trong JSSE. Chúng không có cùng ý nghĩa với danh sách disabled; tuy nhiên, một thuật toán như RC4 cũng xuất hiện trong danh sách TLS disabled của cấu hình JDK 24.0.2, nên nó bị loại bỏ.

Một property khác:

~~~properties
jdk.security.legacyAlgorithms=SHA1, RSA keySize < 2048, DSA keySize < 2048, DES, DESede, MD5, RC2, ARCFOUR
~~~

Các công cụ như `keytool` và `jarsigner` có thể phát cảnh báo khi dùng thuật toán legacy. Cảnh báo này không tự động có nghĩa mọi API sử dụng thuật toán đó sẽ thất bại. Hãy đọc đúng property và thông báo của công cụ.

## 7. Cú pháp danh sách disabled algorithms

Các property disabled algorithms thường nhận danh sách các mục phân tách bằng dấu phẩy. Mỗi mục gồm tên thuật toán và có thể có một hoặc nhiều constraint.

Cấu trúc khái quát:

~~~text
DisabledAlgorithms:
    AlgorithmName [Constraint] { '&' Constraint }
    hoặc IncludeProperty
~~~

Các dạng constraint thường gặp:

| Constraint | Ý nghĩa |
|---|---|
| `keySize < 2048` | Hạn chế khóa có độ dài nhỏ hơn 2048 bit. |
| `jdkCA` | Áp dụng trong trường hợp certificate chain kết thúc tại trust anchor được JDK đánh dấu. |
| `denyAfter 2028-01-01` | Từ chối sau ngày chỉ định, theo quy tắc của property. |
| `usage TLSServer` | Chỉ áp dụng trong ngữ cảnh TLS server. |
| `usage TLSClient` | Chỉ áp dụng trong ngữ cảnh TLS client. |
| `usage SignedJAR` | Chỉ áp dụng trong ngữ cảnh signed JAR. |
| `include jdk.disabled.namedCurves` | Đưa danh sách named curve của property được chỉ định vào chính sách. |

### keySize

`keySize` so sánh độ dài khóa theo bit và hỗ trợ các toán tử:

~~~text
<  <=  ==  !=  >=  >
~~~

Ví dụ:

~~~properties
RSA keySize < 2048
EC keySize <= 224
DSA keySize < 2048
~~~

Các biểu thức trên hạn chế khóa RSA, EC hoặc DSA có kích thước thỏa điều kiện. Chỉ dùng ngưỡng phù hợp với chuẩn mật mã và khả năng tương thích của hệ thống.

Thứ tự biểu thức có thể ảnh hưởng kết quả. Với nhiều ngưỡng cho cùng thuật toán, constraint có key size nhỏ hơn cần được đặt trước ngưỡng lớn hơn. Ví dụ:

~~~properties
RSA keySize < 1024 & jdkCA, RSA keySize < 2048
~~~

### jdkCA

`jdkCA` giới hạn một quy tắc vào certificate chain kết thúc tại trust anchor được JDK đánh dấu trong kho CA mặc định. Nếu bỏ constraint này, thuật toán có thể bị hạn chế trên mọi chain thuộc phạm vi property.

Ví dụ:

~~~properties
SHA1 jdkCA & usage TLSServer
~~~

Biểu thức yêu cầu đồng thời điều kiện trust anchor và ngữ cảnh TLS server.

### usage

`usage` giới hạn quy tắc theo mục đích sử dụng:

~~~properties
SHA1 usage TLSServer TLSClient
SHA1 usage SignedJAR
~~~

Nhiều usage sau từ khóa có thể được ghi cách nhau bằng khoảng trắng. Đây là cách áp dụng chính sách theo ngữ cảnh khi cấm thuật toán ở mọi trường hợp sẽ gây ảnh hưởng không cần thiết.

### denyAfter

`denyAfter` dùng ngày theo định dạng `YYYY-MM-DD`:

~~~properties
SHA1 denyAfter 2028-01-01
~~~

Ngày được xử lý theo UTC. Quy tắc này cho phép một chính sách thay đổi theo thời gian mà không cần chờ certificate hết hạn. Với JAR có timestamp, cần tuân thủ ngoại lệ và quy tắc timestamp mà JDK quy định cho signed JAR.

### Kết hợp constraint bằng dấu &

Dấu `&` yêu cầu các constraint trong cùng biểu thức cùng được thỏa mãn trước khi mục đó bị áp dụng.

Ví dụ:

~~~properties
RSA keySize < 2048 & jdkCA
SHA1 jdkCA & usage TLSServer
~~~

Đọc biểu thức như một điều kiện kết hợp. Các mục phân tách bằng dấu phẩy là các mục chính sách riêng.

## 8. Tên thuật toán và cách khớp

Tên thuật toán được đối chiếu không phân biệt chữ hoa/chữ thường và theo các thành phần con của tên thuật toán.

Ví dụ, mục `SHA1` có thể khớp với tên chữ ký `SHA1withRSA` vì SHA1 là thành phần của tên đó. Mục `DSA` có thể hạn chế thuật toán chữ ký dựa trên DSA nhưng không đồng nghĩa với ECDSA.

Không nên tự suy luận tên thuật toán chỉ từ tên class Java hoặc tên provider. Dùng tên chuẩn trong Java Security Standard Algorithm Names Specification và kiểm tra cách thành phần cụ thể diễn giải tên đó.

Đối với TLS cipher suite, `jdk.tls.disabledAlgorithms` còn cho phép wildcard `*` trong tên cipher suite bắt đầu bằng `TLS_`. Ví dụ:

~~~properties
TLS_RSA_*
~~~

Quy tắc này hạn chế tất cả cipher suite khớp tiền tố đó. Wildcard không phải cách viết chung cho mọi tên thuật toán ở các property khác.

## 9. Named curves và include property

`jdk.disabled.namedCurves` là property chứa danh sách named elliptic curve bị vô hiệu hóa. Các property như TLS, CertPath hoặc JAR có thể đưa danh sách đó vào bằng cú pháp include:

~~~properties
jdk.tls.disabledAlgorithms=..., include jdk.disabled.namedCurves
~~~

Từ khóa `include` tham chiếu một security property khác. Nó giúp dùng chung một danh sách hạn chế ở nhiều miền, tránh phải sao chép tên từng curve vào nhiều chỗ.

Trong JDK 24.0.2 được dùng để kiểm chứng bài này, dòng định nghĩa `jdk.disabled.namedCurves` trong file cấu hình mặc định đang được comment, vì vậy `Security.getProperty("jdk.disabled.namedCurves")` trả về `null`. Một bản JDK khác hoặc chính sách triển khai riêng có thể định nghĩa giá trị này.

Không thêm include tới property chưa được định nghĩa rồi giả định danh sách curve đã được áp dụng. Hãy kiểm tra giá trị hiệu lực trong đúng JVM đang chạy.

## 10. File cấu hình java.security

Security properties mặc định thường nằm tại:

~~~text
JAVA_HOME/conf/security/java.security
~~~

File này khác với file `application.properties` hoặc system properties thông thường. Các mục trong đó được nạp bởi Java Security infrastructure.

Ví dụ một số property trong JDK 24.0.2:

~~~properties
jdk.certpath.disabledAlgorithms=...
jdk.tls.disabledAlgorithms=...
jdk.jar.disabledAlgorithms=...
jdk.security.legacyAlgorithms=...
jdk.tls.legacyAlgorithms=...
~~~

Không nên sửa file mặc định của JDK một cách tùy tiện. Thay đổi tại đó có thể ảnh hưởng tất cả ứng dụng sử dụng cùng JDK, bị ghi đè khi cập nhật JDK hoặc tạo ra khác biệt khó tái lập giữa máy developer và production.

Với triển khai riêng của ứng dụng, có thể sử dụng file security properties bổ sung qua tùy chọn JVM `-Djava.security.properties`. Nên lưu file bổ sung trong cấu hình được quản lý và version control, không sửa JDK đang cài trên máy.

## 11. Nạp security properties bổ sung

Có thể khởi chạy JVM với một file security properties bổ sung:

~~~bash
java -Djava.security.properties=file:/opt/app/security/extra.security -jar app.jar
~~~

Với một dấu bằng trong `-Djava.security.properties=`, file bổ sung được nạp cùng file master. Các property không được khai báo trong file bổ sung vẫn lấy từ file master.

**Điểm rất quan trọng:** nếu file bổ sung khai báo lại một property đã có, giá trị mới thay thế toàn bộ giá trị cũ của property đó. Danh sách thuật toán phân tách bằng dấu phẩy không được tự động nối thêm.

Ví dụ file bổ sung:

~~~properties
jdk.certpath.disabledAlgorithms=MD2
~~~

Sau khi nạp, giá trị hiệu lực của property này chỉ là `MD2`. Những mục mặc định như MD5, SHA1 theo usage, RSA key size và EC key size đã bị thay khỏi property đó. Đây có thể vô tình làm yếu chính sách bảo mật.

Khi muốn bổ sung một constraint, hãy giữ lại toàn bộ các mục mặc định mà tổ chức muốn tiếp tục áp dụng, sau đó thêm constraint mới vào cùng giá trị. Kiểm tra giá trị hiệu lực trước khi triển khai.

Tùy chọn dùng hai dấu bằng:

~~~bash
java -Djava.security.properties==file:/opt/app/security/complete.security -jar app.jar
~~~

có ý nghĩa khác: file được chỉ định thay thế hoàn toàn file security properties master. Không dùng cách này trừ khi đã cung cấp đầy đủ mọi property cần thiết và hiểu rõ tác động tới toàn bộ Java Security configuration.

## 12. Ví dụ bổ sung một hạn chế mà vẫn giữ mặc định

Giả sử chính sách của tổ chức muốn từ chối RSA key nhỏ hơn 2048 bit trong TLS. File bổ sung phải giữ các mục TLS mặc định đang dùng, rồi mới thêm constraint:

~~~properties
jdk.tls.disabledAlgorithms=SSLv3, TLSv1, TLSv1.1, DTLSv1.0, RC4, DES, MD5withRSA, DH keySize < 1024, EC keySize < 224, 3DES_EDE_CBC, anon, NULL, ECDH, TLS_RSA_*, RSA keySize < 2048
~~~

Nạp file khi khởi chạy:

~~~bash
java -Djava.security.properties=file:/opt/app/security/extra.security -jar app.jar
~~~

Ví dụ này minh họa cách giữ các mục cũ và thêm một constraint. Ngưỡng RSA 2048 bit có thể ảnh hưởng certificate, server cũ và các dependency; cần kiểm thử trên môi trường staging trước khi áp dụng production.

Không sao chép nguyên giá trị mặc định từ một JDK khác mà chưa so sánh. Vendor hoặc bản cập nhật có thể thay đổi danh sách, vì vậy hãy lấy giá trị master từ chính JDK mục tiêu.

## 13. Đọc property hiệu lực bằng Java

Dùng `java.security.Security.getProperty` để đọc security property:

~~~java
import java.security.Security;
import java.util.List;

public class DisabledAlgorithmsDemo {
    public static void main(String[] args) {
        List<String> names = List.of(
                "jdk.certpath.disabledAlgorithms",
                "jdk.tls.disabledAlgorithms",
                "jdk.jar.disabledAlgorithms",
                "jdk.security.legacyAlgorithms",
                "jdk.tls.legacyAlgorithms",
                "jdk.disabled.namedCurves"
        );

        for (String name : names) {
            String value = Security.getProperty(name);
            System.out.println(
                    name + "=" + (value == null ? "<not set>" : value)
            );
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac DisabledAlgorithmsDemo.java
java DisabledAlgorithmsDemo
~~~

Với Azul OpenJDK 24.0.2 đã dùng để kiểm tra, output là:

~~~text
jdk.certpath.disabledAlgorithms=MD2, MD5, SHA1 jdkCA & usage TLSServer, RSA keySize < 1024, DSA keySize < 1024, EC keySize < 224, SHA1 usage SignedJAR & denyAfter 2019-01-01
jdk.tls.disabledAlgorithms=SSLv3, TLSv1, TLSv1.1, DTLSv1.0, RC4, DES, MD5withRSA, DH keySize < 1024, EC keySize < 224, 3DES_EDE_CBC, anon, NULL, ECDH, TLS_RSA_*
jdk.jar.disabledAlgorithms=MD2, MD5, RSA keySize < 1024, DSA keySize < 1024, SHA1 denyAfter 2019-01-01
jdk.security.legacyAlgorithms=SHA1, RSA keySize < 2048, DSA keySize < 2048, DES, DESede, MD5, RC2, ARCFOUR
jdk.tls.legacyAlgorithms=NULL, anon, RC4, DES, 3DES_EDE_CBC
jdk.disabled.namedCurves=<not set>
~~~

Giá trị output trên là mẫu của một bản JDK cụ thể, không phải giá trị cố định cho mọi máy. Dùng `Security.getProperty` để kiểm tra JVM thật đang chạy ứng dụng.

Không dùng `System.getProperty("jdk.tls.disabledAlgorithms")` để đọc các security properties. `System.getProperty` đọc system properties; `Security.getProperty` đọc Java security properties.

## 14. AlgorithmConstraints ở cấp ứng dụng

Ngoài chính sách toàn JVM, Java cung cấp interface `java.security.AlgorithmConstraints` để một ứng dụng hoặc provider kiểm tra thuật toán theo nhu cầu.

Với TLS, `javax.net.ssl.SSLParameters` có phương thức `setAlgorithmConstraints`:

~~~java
SSLParameters parameters = new SSLParameters();
parameters.setAlgorithmConstraints(applicationConstraints);
~~~

`applicationConstraints` là implementation do ứng dụng cung cấp. Nó có thể giới hạn thuật toán được phép trong một kết nối hoặc một cấu hình TLS cụ thể.

Đây là lớp kiểm soát bổ sung ở cấp ứng dụng. Nó không phải cách bỏ qua `jdk.tls.disabledAlgorithms`. Thuật toán bị JDK đánh dấu disabled vẫn không được thương lượng chỉ vì ứng dụng cung cấp một AlgorithmConstraints cho phép nó.

Khi tự viết `AlgorithmConstraints`, cần đánh giá đủ tên thuật toán, khóa, tham số và `CryptoPrimitive`. Một implementation quá rộng hoặc luôn trả về true có thể làm mất mục tiêu của chính sách bổ sung.

## 15. Ảnh hưởng tới ứng dụng và lỗi thường gặp

Khi disabled algorithm được áp dụng, thông báo có thể xuất hiện ở nhiều giai đoạn:

| Hiện tượng | Khu vực cần kiểm tra |
|---|---|
| TLS handshake thất bại hoặc không tìm được protocol/cipher phù hợp | `jdk.tls.disabledAlgorithms`, cấu hình TLS và khả năng của peer. |
| Certificate path validation thất bại | `jdk.certpath.disabledAlgorithms`, `jdk.tls.disabledAlgorithms`, certificate chain, CRL và OCSP. |
| Signed JAR bị xem như chưa ký | `jdk.jar.disabledAlgorithms`, thuật toán ký, certificate và timestamp. |
| keytool hoặc jarsigner phát cảnh báo thuật toán yếu | `jdk.security.legacyAlgorithms` và cấu hình công cụ. |
| Thuật toán vẫn được liệt kê trong provider nhưng không dùng được trong một ngữ cảnh | Kiểm tra security property áp dụng cho ngữ cảnh đó và provider thực hiện. |

Một số thông báo có thể chứa cụm từ như `Algorithm constraints check failed`, `No appropriate protocol` hoặc lỗi PKIX. Nội dung chính xác thay đổi theo provider, JDK và giai đoạn thất bại.

### TLS handshake không còn lựa chọn chung

Nếu client và server chỉ hỗ trợ protocol/cipher đã bị disabled, không còn lựa chọn chung để thương lượng. Kiểm tra cả hai đầu kết nối, không chỉ cấu hình client.

### Certificate còn hạn nhưng vẫn bị từ chối

Thời hạn certificate hợp lệ không đảm bảo thuật toán ký và key size còn được chấp nhận. Kiểm tra từng certificate trong chain, CA, mục đích sử dụng và chữ ký CRL/OCSP.

### JAR báo thiếu chữ ký

Nếu thuật toán ký bị cấm, JDK có thể xử lý JAR như chưa ký. Xác minh signer, certificate chain, timestamp và chính sách JAR trước khi thay đổi property.

### Legacy warning bị hiểu nhầm là lỗi

Cảnh báo legacy từ keytool hoặc jarsigner không đồng nghĩa với disabled. Xác định property nguồn và kiểm tra thao tác thực tế trước khi quyết định thay đổi.

## 16. Quy trình chẩn đoán và thay đổi an toàn

Khi một ứng dụng gặp lỗi liên quan thuật toán:

1. Ghi lại JDK vendor, phiên bản và provider mật mã đang được sử dụng.
2. Xác định thao tác thất bại: TLS handshake, CertPath, JAR verification hay lệnh công cụ.
3. Đọc thông báo lỗi đầy đủ và xác định tên thuật toán, key size, protocol hoặc cipher suite.
4. Dùng `Security.getProperty` để xem property hiệu lực trong đúng JVM.
5. Kiểm tra file `JAVA_HOME/conf/security/java.security` và file bổ sung nếu JVM được khởi chạy với `-Djava.security.properties`.
6. Kiểm tra constraint theo ngữ cảnh như `jdkCA`, `usage` và `denyAfter`.
7. Ưu tiên nâng cấp certificate, key, server, thư viện hoặc thuật toán sang lựa chọn an toàn.
8. Nếu cần thay đổi chính sách, giữ các hạn chế mặc định và chỉ thêm constraint đã được đánh giá.
9. Kiểm thử TLS, xác thực certificate và xác minh JAR trên staging.
10. Triển khai có theo dõi, ghi lại cấu hình và chuẩn bị phương án rollback.

Không nên gỡ một thuật toán khỏi danh sách chỉ để làm lỗi biến mất. Trước hết cần tìm nguyên nhân gốc và xác định có thể thay certificate, cấu hình server hoặc dependency hay không.

## 17. Kiểm thử và triển khai trong CI

Chính sách disabled algorithms nên được kiểm thử trên đúng JDK dùng ở production.

Một pipeline có thể thực hiện:

- In vendor và phiên bản JDK.
- In các security properties quan trọng bằng một chương trình kiểm tra nhỏ.
- Chạy test TLS client/server với certificate thực tế.
- Xác minh signed JAR và timestamp.
- Chạy kiểm thử CertPath với chain đại diện cho môi trường.
- Lưu file security properties bổ sung cùng cấu hình triển khai.
- So sánh property hiệu lực với baseline đã được phê duyệt.

Không chỉ kiểm tra file cấu hình. Một file bổ sung có thể không được nạp do sai đường dẫn, hoặc giá trị property có thể đã bị thay toàn bộ thay vì nối thêm. Hãy xác minh từ bên trong đúng JVM của ứng dụng.

Khi nâng cấp JDK, so sánh danh sách mặc định giữa các bản. JDK update có thể bổ sung thuật toán bị cấm hoặc thay đổi ngưỡng; đó là thay đổi bảo mật có thể ảnh hưởng tương thích.

## 18. Checklist quản lý disabled algorithms

- Đã xác định đúng security property theo TLS, CertPath, JAR hay công cụ.
- Đã phân biệt disabled với legacy.
- Đã kiểm tra vendor, phiên bản JDK và provider.
- Đã hiểu constraint keySize, jdkCA, usage, denyAfter và include.
- Đã đọc giá trị hiệu lực bằng `Security.getProperty`.
- File bổ sung không vô tình thay thế mất các hạn chế mặc định cần giữ.
- Không dùng hai dấu bằng `==` nếu không chủ ý thay toàn bộ master security properties.
- Đã kiểm tra TLS, certificate chain và signed JAR trên staging.
- Đã ưu tiên thay certificate/key/algorithm yếu thay vì gỡ hạn chế.
- Có cấu hình được quản lý phiên bản, giám sát và kế hoạch rollback.

Disabled algorithms giúp JDK áp dụng chính sách mật mã nhất quán trong những hoạt động bảo mật quan trọng. Muốn điều chỉnh đúng, cần biết property nào kiểm soát thao tác đang lỗi, hiểu cách constraint được diễn giải và xác minh giá trị thực tế trong JVM. Giữ nguyên các hạn chế mặc định, kiểm thử thay đổi trên môi trường tương đương production và ưu tiên nâng cấp thành phần yếu là cách quản lý chính sách an toàn hơn.
