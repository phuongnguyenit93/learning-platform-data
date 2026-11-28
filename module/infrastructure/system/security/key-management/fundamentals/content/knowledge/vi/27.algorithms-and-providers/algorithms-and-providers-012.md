# Crypto policy của JDK

Trong chương **Algorithm và provider** của module SECURITY_KEY_MANAGEMENT_FUNDAMENTALS, bài học này giải thích crypto policy của Java Development Kit (JDK) và cách chính sách đó giới hạn hoặc từ chối các thao tác mật mã. Crypto policy ảnh hưởng tới khả năng dùng thuật toán, độ dài khóa và việc chấp nhận chứng thư trong một số ngữ cảnh. Hiểu đúng các lớp policy giúp vận hành Java nhất quán, tránh nới lỏng bảo mật chỉ để làm ứng dụng chạy được và phân biệt giới hạn của JCE với các quy tắc riêng của TLS, PKI hoặc provider.

## 1. Crypto policy của JDK là gì?

**Crypto policy** là tập hợp các quy tắc bảo mật mà runtime Java áp dụng cho những dịch vụ mật mã. Các quy tắc có thể giới hạn độ dài khóa, vô hiệu hóa thuật toán hoặc tham số yếu, kiểm soát giao thức TLS và ảnh hưởng đến việc xác minh certificate chain.

Trong Java, policy được thể hiện qua các security properties, cấu hình của provider, giới hạn của runtime và chính sách của thiết bị mật mã bên dưới. Một số thuộc tính áp dụng cho toàn bộ dịch vụ JCE; một số chỉ áp dụng cho TLS, certificate path hoặc xác minh chữ ký JAR.

Crypto policy giúp tổ chức thực thi một baseline mật mã thống nhất. Ví dụ, tổ chức có thể không cho phép DES, RC4 hoặc khóa RSA quá ngắn; giới hạn TLS ở các phiên bản và cipher suite được chấp thuận; hoặc từ chối chứng thư có chữ ký dùng hash đã lỗi thời.

Crypto policy không phải một thuật toán và cũng không thay thế chính sách quản lý khóa. Nó không tự tạo khóa, lưu private key, phân quyền người dùng, rotate khóa hay xóa dữ liệu. Những nhiệm vụ đó vẫn cần được thực hiện bởi ứng dụng, KeyStore, KMS, HSM và quy trình quản trị tương ứng.

## 2. Các lớp policy cần phân biệt

Trong JDK có nhiều cơ chế policy cùng ảnh hưởng tới mật mã nhưng kiểm soát các phạm vi khác nhau.

| Lớp policy | Phạm vi | Ví dụ thuộc tính/cơ chế |
|---|---|---|
| JCE jurisdiction policy | Giới hạn độ dài khóa tối đa được phép cho các phép toán JCE | crypto.policy |
| TLS algorithm constraints | Thuật toán, giao thức, cipher suite và kích thước khóa được phép trong TLS | jdk.tls.disabledAlgorithms |
| Certificate path constraints | Thuật toán và thuộc tính chứng thư không được chấp nhận khi xác minh đường dẫn PKI | jdk.certpath.disabledAlgorithms |
| JAR signature constraints | Thuật toán chữ ký bị hạn chế khi xác minh JAR đã ký | jdk.jar.disabledAlgorithms |
| Provider policy | Thuật toán, key size, mode hoặc operation mà provider hỗ trợ | Cấu hình và giới hạn của từng provider |
| HSM/KMS policy | Quyền sử dụng khóa, thuật toán, operation và giới hạn của thiết bị/dịch vụ | Key policy, mechanism policy, role và security domain |

Các lớp này có thể cùng áp dụng cho một thao tác. Ví dụ, ứng dụng có thể tạo được AES key theo giới hạn JCE nhưng provider HSM không hỗ trợ key size đó; hoặc TLS engine có thể từ chối cipher suite vì jdk.tls.disabledAlgorithms dù JCE vẫn cho phép dùng thuật toán tương ứng trong một phép toán khác.

Vì vậy, khi một thao tác bị từ chối, cần xác định policy nào đã chặn nó thay vì chỉ thay đổi một thuộc tính chung.

## 3. crypto.policy và giới hạn độ dài khóa JCE

Security property **crypto.policy** điều khiển chính sách giới hạn mật mã của JCE. Các giá trị thường gặp là:

- **limited:** áp dụng các giới hạn độ dài khóa theo jurisdiction policy.
- **unlimited:** không áp dụng giới hạn độ dài khóa của jurisdiction policy đối với các thuật toán được policy này quản lý.

Ở các JDK hiện đại, unlimited thường là mặc định. Từ JDK 9, unlimited strength jurisdiction policy được bật mặc định. Với JDK 8, hành vi phụ thuộc bản cập nhật và nhà phân phối; Oracle JDK 8u161 trở lên bật unlimited mặc định, trong khi các bản cũ hơn có thể cần policy files hoặc cấu hình riêng. Luôn kiểm tra tài liệu của đúng vendor/build đang triển khai.

Unlimited chỉ loại bỏ giới hạn độ dài khóa của lớp jurisdiction policy. Nó không tự động cho phép mọi thuật toán, mode hoặc protocol. DES, RC4, thuật toán chữ ký yếu hoặc TLS protocol bị vô hiệu hóa vẫn có thể bị từ chối bởi các policy khác.

Ví dụ, một ứng dụng có thể dùng AES-256 khi runtime cho phép độ dài khóa đó. Tuy nhiên, phép toán vẫn có thể thất bại nếu provider không hỗ trợ AES-256, HSM policy không cho phép hoặc transformation không được provider triển khai.

## 4. Limited và unlimited có ý nghĩa gì?

Trong môi trường legacy, ứng dụng có thể gặp lỗi khi dùng khóa dài hơn giới hạn JCE của runtime. Khi đó cần xác định:

1. JDK vendor và phiên bản cập nhật đang chạy.
2. Giá trị crypto.policy đang được áp dụng.
3. Thuật toán và độ dài khóa thực tế.
4. Provider thực hiện phép toán.
5. Có giới hạn bổ sung từ HSM/KMS hoặc policy doanh nghiệp hay không.

Không nên mặc định đổi sang unlimited để sửa mọi lỗi mật mã. Với JDK hiện đại, unlimited thường đã là mặc định; nếu vẫn lỗi, nguyên nhân có thể nằm ở provider, thuật toán, key format hoặc security property khác.

| Thuộc tính | Limited | Unlimited |
|---|---|---|
| Giới hạn độ dài khóa JCE | Có thể giới hạn theo policy được cài | Không áp dụng giới hạn jurisdiction tương ứng |
| Cho phép thuật toán đã bị vô hiệu hóa | Không | Không |
| Bỏ qua TLS disabled algorithms | Không | Không |
| Bỏ qua giới hạn provider/HSM | Không | Không |
| Tự chứng minh tuân thủ FIPS | Không | Không |

Unlimited không có nghĩa là nên chọn khóa dài nhất cho mọi trường hợp. Kích thước khóa cần phù hợp với thuật toán, chuẩn áp dụng, hiệu năng, khả năng tương thích và thời gian bảo vệ dữ liệu.

## 5. Cấu hình crypto.policy

Crypto policy là security property của runtime. Cấu hình chuẩn nằm trong tệp security properties của JDK. Đường dẫn thường gặp:

| Phiên bản Java | Vị trí thường gặp |
|---|---|
| JDK 9 trở lên | JAVA_HOME/conf/security/java.security |
| JDK 8 cài dưới dạng JDK | JAVA_HOME/jre/lib/security/java.security |
| JRE 8 độc lập | JAVA_HOME/lib/security/java.security |

Trong runtime hỗ trợ thuộc tính này, cấu hình có thể có dạng:

~~~properties
crypto.policy=unlimited
~~~

Trên JDK hiện đại, giá trị này thường đã là mặc định. Chỉ thay đổi khi có yêu cầu rõ ràng và đã xác nhận hành vi của đúng JDK vendor.

Có thể nạp thêm security properties từ một tệp cấu hình bằng tùy chọn JVM:

~~~bash
java -Djava.security.properties=/etc/myapp/crypto-overrides.security -jar app.jar
~~~

Tệp bổ sung có thể chứa các thuộc tính cần override. Cách nạp một tệp bằng một dấu bằng thường bổ sung/ghi đè thuộc tính từ security configuration chính. Cú pháp hai dấu bằng có ngữ nghĩa thay thế toàn bộ security properties mặc định và có thể làm mất nhiều cấu hình bảo mật quan trọng; không dùng nếu chưa chủ động xây dựng đầy đủ baseline thay thế.

Không nên sửa trực tiếp tệp trong JDK đang được chia sẻ giữa nhiều ứng dụng mà không có quản lý cấu hình. Với môi trường production, ưu tiên cấu hình có phiên bản, được kiểm thử và phân phối nhất quán qua image hoặc hệ thống quản lý cấu hình.

## 6. Security property và system property

Java có hai loại thuộc tính dễ bị nhầm:

- **Security property:** được quản lý qua lớp java.security.Security và tệp java.security.
- **System property:** được truyền qua JVM argument -D hoặc API System.

Ví dụ:

| Thuộc tính | Loại | Cách đọc |
|---|---|---|
| crypto.policy | Security property | Security.getProperty("crypto.policy") |
| jdk.tls.disabledAlgorithms | Security property | Security.getProperty("jdk.tls.disabledAlgorithms") |
| jdk.certpath.disabledAlgorithms | Security property | Security.getProperty("jdk.certpath.disabledAlgorithms") |
| java.security.properties | System property | System.getProperty("java.security.properties") |

Đặt một system property cùng tên không đồng nghĩa đã thay đổi security property. Cần dùng đúng cơ chế cấu hình. Ngoài ra, một số thành phần có thể đọc và cache policy khi khởi tạo; thay đổi security property giữa lúc ứng dụng đang chạy có thể không cập nhật các engine đã tạo. Nên cấu hình policy trước khi khởi động và trước khi khởi tạo dịch vụ mật mã.

## 7. Kiểm tra crypto policy từ Java

Ứng dụng có thể đọc security properties và hỏi giới hạn độ dài khóa JCE bằng API.

~~~java
import java.security.Security;
import javax.crypto.Cipher;

public final class CryptoPolicyInfo {
    public static void main(String[] args) throws Exception {
        System.out.println("java.version = "
                + System.getProperty("java.version"));
        System.out.println("java.vendor = "
                + System.getProperty("java.vendor"));

        printSecurityProperty("crypto.policy");
        printSecurityProperty("jdk.tls.disabledAlgorithms");
        printSecurityProperty("jdk.certpath.disabledAlgorithms");
        printSecurityProperty("jdk.jar.disabledAlgorithms");

        int maxAesBits =
                Cipher.getMaxAllowedKeyLength("AES/GCM/NoPadding");
        System.out.println("Maximum allowed AES key length = "
                + maxAesBits);
    }

    private static void printSecurityProperty(String name) {
        System.out.println(name + " = " + Security.getProperty(name));
    }
}
~~~

Giá trị Integer.MAX_VALUE từ getMaxAllowedKeyLength thường biểu thị không có giới hạn tối đa từ jurisdiction policy cho transformation được hỏi. Nó không chứng minh provider hoặc thiết bị thực tế hỗ trợ mọi key size.

Kiểm tra runtime là bước chẩn đoán hữu ích, nhưng cần thực hiện trong đúng tiến trình, container và JDK đang gặp lỗi. Chạy một đoạn mã trên máy quản trị với JDK khác không chứng minh ứng dụng production có cùng policy.

## 8. jdk.tls.disabledAlgorithms

Security property **jdk.tls.disabledAlgorithms** quy định thuật toán, giao thức hoặc điều kiện khóa không được phép dùng trong TLS. Nó có thể chặn protocol cũ, cipher suite yếu, thuật toán trao đổi khóa không phù hợp hoặc certificate key có kích thước dưới ngưỡng.

Các nhóm thường gặp trong policy TLS:

- Phiên bản giao thức đã lỗi thời.
- Cipher suite hoặc thuật toán mã hóa yếu.
- Hash hoặc chữ ký không còn đáp ứng baseline.
- Thuật toán trao đổi khóa yếu.
- Kích thước khóa RSA, DSA hoặc EC thấp hơn ngưỡng policy.
- Các điều kiện thời gian hoặc ngữ cảnh được JDK hỗ trợ trong cú pháp constraint.

Giá trị mặc định thay đổi theo phiên bản JDK và bản cập nhật bảo mật. Không nên sao chép một danh sách từ tài liệu cũ hoặc ghi đè toàn bộ giá trị mặc định bằng một danh sách ngắn. Làm vậy có thể vô tình bật lại protocol/algorithm yếu mà vendor đã vô hiệu hóa.

Khi cần thay đổi, hãy lấy giá trị baseline từ đúng JDK, đánh giá từng constraint, thử nghiệm với client/server thực tế và ghi nhận ngoại lệ có thời hạn. Nếu một TLS handshake thất bại, kiểm tra negotiated protocol, cipher suite, certificate chain, key size và log của JSSE trước khi sửa policy.

## 9. jdk.certpath.disabledAlgorithms

Security property **jdk.certpath.disabledAlgorithms** áp dụng cho quá trình xác minh đường dẫn chứng thư. Nó có thể từ chối chứng thư hoặc CA chain sử dụng thuật toán chữ ký, public key hoặc key size không còn được chấp nhận.

Ví dụ, một chứng thư có thể:

- Được CA ký bằng SHA-1 trong khi policy hiện tại không còn chấp nhận SHA-1 cho certificate path.
- Dùng RSA key ngắn hơn ngưỡng được phép.
- Có CA key hoặc chữ ký nằm trong một nhóm thuật toán đã bị loại bỏ.
- Vi phạm constraint theo thời điểm hoặc ngữ cảnh xác minh.

Điều này khác với crypto.policy. Một runtime có thể cho phép tạo AES-256 key nhưng vẫn từ chối một certificate chain vì thuật toán chữ ký hoặc kích thước public key không đạt policy.

Khi lỗi PKIX hoặc CertPathValidator xuất hiện, cần kiểm tra issuer chain, chữ ký từng certificate, key size, validity, trust anchor và disabled algorithm constraints. Không nên thêm CA hoặc tắt certificate validation chỉ để bỏ qua lỗi.

## 10. jdk.jar.disabledAlgorithms và chữ ký JAR

JDK có thể áp dụng security property **jdk.jar.disabledAlgorithms** để giới hạn thuật toán dùng trong chữ ký JAR. Điều này ảnh hưởng tới việc xác minh tính toàn vẹn và nguồn gốc của artifact Java đã ký.

Nếu một JAR được ký bằng thuật toán đã bị policy vô hiệu hóa, runtime hoặc công cụ xác minh có thể cảnh báo hay từ chối chữ ký tùy phiên bản và cấu hình. Artifact cũ cần được ký lại bằng thuật toán được chấp thuận và quy trình phát hành có kiểm soát.

Không giải quyết lỗi bằng cách bỏ qua kiểm tra chữ ký hoặc tắt cơ chế xác minh artifact. Cần xác định thuật toán ký, timestamp, certificate chain, thời điểm ký và policy áp dụng tại thời điểm xác minh.

## 11. Cú pháp constraint và giới hạn key size

Một số security properties dùng danh sách constraint, ví dụ tên thuật toán, giao thức hoặc điều kiện key size. Dạng cú pháp chính xác và tập điều kiện hỗ trợ phụ thuộc JDK.

Các điều kiện có thể gặp gồm:

- Tên thuật toán hoặc giao thức bị cấm.
- keySize với toán tử so sánh và ngưỡng bit.
- Điều kiện thời gian như denyAfter nếu thuộc tính và phiên bản hỗ trợ.
- Ràng buộc theo usage hoặc ngữ cảnh nếu JDK có hỗ trợ.

Ví dụ minh họa cú pháp key size:

~~~properties
# Minh họa cấu trúc constraint, không phải baseline production.
jdk.tls.disabledAlgorithms=..., RSA keySize < 2048
~~~

Dấu ba chấm biểu thị các constraint khác của baseline phải được giữ nguyên; không dùng nguyên dòng minh họa này làm cấu hình thay thế. Khi chỉnh security property, giá trị mới thường thay thế giá trị cũ của thuộc tính đó, không tự động nối thêm các mục bị bỏ sót.

Ngưỡng key size cần dựa trên chuẩn và chính sách hiện hành. Không dùng ví dụ trong tài liệu này như một giá trị bắt buộc cho mọi tổ chức hoặc mọi phiên bản JDK.

## 12. Quan hệ giữa JDK policy và provider

JCA/JCE định tuyến thao tác qua provider. Provider có thể hỗ trợ một transformation nhưng từ chối key size, tham số hoặc operation cụ thể. Ngược lại, runtime policy có thể chặn thao tác trước khi provider thực hiện.

Một phép toán thành công cần đồng thời đáp ứng:

1. JDK cho phép thuật toán và tham số theo security policy.
2. Provider hỗ trợ transformation, key type, key size và parameter spec.
3. KeyStore/KMS/HSM cho phép sử dụng key object đó.
4. Key policy và quyền của principal cho phép operation.
5. Dữ liệu đầu vào và tham số hợp lệ.

Ví dụ, crypto.policy có thể cho phép AES-256 nhưng HSM chỉ cấu hình AES-128; hoặc Cipher tạo được nhưng key object bị policy cấm export. Đây là các lớp kiểm soát khác nhau.

Không nên thay provider hoặc giảm key size một cách tự động khi gặp lỗi. Trước hết cần xác định lớp nào từ chối, rồi điều chỉnh cấu hình hoặc thiết kế trong phạm vi policy đã phê duyệt.

## 13. Crypto policy và FIPS

FIPS 140 là chương trình đánh giá module mật mã theo tiêu chuẩn tương ứng. Bật crypto.policy=unlimited không làm cho ứng dụng hoặc JDK trở thành FIPS compliant.

Một triển khai cần đánh giá:

- Module mật mã đã được xác nhận/chứng nhận và đúng phiên bản.
- Provider đang chạy có đúng chế độ vận hành được chứng nhận hay không.
- Cấu hình, nền tảng, hệ điều hành và ranh giới module có nằm trong phạm vi chứng nhận không.
- Thuật toán và operation được dùng có nằm trong danh sách được module cho phép không.
- Key generation, key storage, zeroization và self-test đáp ứng yêu cầu liên quan.
- Ứng dụng có vô tình dùng provider không nằm trong ranh giới được đánh giá hay không.

Chỉ sử dụng một provider có tên gợi ý FIPS hoặc cấu hình một security property không đủ chứng minh tuân thủ. Cần đối chiếu chứng nhận, security policy của module và hướng dẫn triển khai của nhà cung cấp.

## 14. Triển khai policy nhất quán

Trong hệ thống phân tán, các instance có thể chạy JDK vendor hoặc update level khác nhau. Khi policy không đồng nhất, cùng một ứng dụng có thể kết nối thành công ở một node nhưng thất bại ở node khác.

Quy trình quản lý cấu hình nên:

1. Kiểm kê JDK vendor, version, update và provider trên từng môi trường.
2. Thu thập security properties thực tế từ runtime.
3. Xác định baseline policy theo tiêu chuẩn của tổ chức.
4. Tách cấu hình chung khỏi ngoại lệ dành cho hệ thống legacy.
5. Lưu cấu hình dưới dạng có phiên bản và review.
6. Kiểm thử TLS, certificate path, JAR verification và các phép toán JCE quan trọng.
7. Phân phối qua image hoặc configuration management.
8. Theo dõi lỗi sau triển khai và có quy trình rollback được phê duyệt.
9. Loại bỏ ngoại lệ khi ứng dụng đã được nâng cấp.

Với container, cần kiểm tra JDK thực tế bên trong image. Máy host có thể dùng một JDK khác với runtime trong container. Không chỉ dựa vào biến JAVA_HOME của terminal hoặc phiên bản JDK trên máy phát triển.

## 15. Troubleshooting lỗi do crypto policy

| Triệu chứng | Lớp policy có thể liên quan | Hướng điều tra |
|---|---|---|
| Illegal key size hoặc lỗi key length | JCE jurisdiction policy hoặc provider | Kiểm tra crypto.policy, getMaxAllowedKeyLength, provider và key size |
| TLS handshake failure | TLS algorithm constraints, protocol/cipher support hoặc certificate | Bật chẩn đoán JSSE phù hợp, kiểm tra protocol, cipher suite, key size và chain |
| CertPathValidatorException | Certificate path constraints hoặc chain/trust issue | Kiểm tra chữ ký certificate, key size, issuer, trust anchor và disabled constraints |
| JAR signature bị từ chối/cảnh báo | JAR disabled algorithms hoặc certificate/timestamp | Kiểm tra thuật toán ký, timestamp, chain và JDK version |
| ProviderException/InvalidKeyException | Provider hoặc HSM/KMS policy | Kiểm tra provider, key object, mechanism, quyền operation và thiết bị |
| Chạy khác nhau giữa node | JDK/provider/policy không đồng nhất | So sánh vendor, update, security properties và runtime image |

Các bước chẩn đoán an toàn:

1. Ghi nhận JDK vendor/version và provider thực tế.
2. Đọc các security properties liên quan trong tiến trình gặp lỗi.
3. Tái hiện bằng một phép thử tối thiểu trên đúng runtime.
4. Kiểm tra key size, transformation, certificate chain và tham số.
5. Xác định chính xác constraint hoặc provider đã từ chối.
6. Chọn nâng cấp ứng dụng, cấp lại chứng thư, đổi thuật toán hoặc cập nhật policy theo quy trình.
7. Kiểm thử hồi quy và ghi lại quyết định.

Không tắt toàn bộ kiểm tra algorithm constraints, không chấp nhận mọi certificate và không chuyển sang thuật toán yếu hơn như một fallback. Các cách này có thể che giấu nguyên nhân và làm giảm mức bảo vệ của toàn runtime.

## 16. Những sai lầm thường gặp

- **Đồng nhất unlimited với cho phép mọi thuật toán:** các disabled algorithm properties vẫn có hiệu lực.
- **Chỉ kiểm tra JDK trên máy phát triển:** production container có thể dùng runtime khác.
- **Ghi đè toàn bộ TLS disabled algorithms bằng một danh sách ngắn:** vô tình bật lại thuật toán hoặc protocol yếu.
- **Nhầm system property với security property:** cấu hình không được runtime áp dụng như mong muốn.
- **Thay đổi policy sau khi engine đã khởi tạo:** một số thành phần có thể đã cache cấu hình.
- **Giảm key size để hết lỗi:** làm suy yếu bảo vệ thay vì giải quyết nguyên nhân.
- **Tắt certificate validation:** cho phép kết nối tới peer không đáng tin cậy.
- **Đổi provider không đánh giá:** có thể thay đổi thuật toán, cách xử lý tham số hoặc ranh giới bảo vệ.
- **Cho rằng unlimited đồng nghĩa FIPS:** tuân thủ phụ thuộc module được chứng nhận và cấu hình cụ thể.
- **Không ghi nhận ngoại lệ:** policy bị nới lỏng lâu dài và không có owner hoặc thời hạn.

## 17. Checklist review crypto policy

- [ ] Đã xác định đúng JDK vendor, version và update level.
- [ ] Đã kiểm tra crypto.policy và giới hạn JCE thực tế.
- [ ] Đã phân biệt JCE limit với TLS, CertPath và JAR algorithm constraints.
- [ ] Đã kiểm tra provider và giới hạn của HSM/KMS.
- [ ] Các security properties được lấy từ baseline của đúng JDK.
- [ ] Không ghi đè disabled algorithms bằng danh sách thiếu constraint.
- [ ] Không bật lại protocol, mode hoặc thuật toán đã bị loại bỏ.
- [ ] Cấu hình được áp dụng trước khi khởi tạo dịch vụ mật mã.
- [ ] Đã kiểm thử JCE operation, TLS handshake và certificate path trên runtime thực tế.
- [ ] Các ngoại lệ có owner, lý do, biện pháp bù và ngày hết hạn.
- [ ] Container/image và các node có policy nhất quán.
- [ ] Không tuyên bố FIPS chỉ dựa trên crypto.policy hoặc tên provider.

Crypto policy của JDK là lớp kiểm soát giúp runtime áp dụng baseline mật mã nhất quán. crypto.policy chủ yếu liên quan giới hạn độ dài khóa JCE; TLS, certificate path và JAR signature có các security properties riêng; provider và HSM/KMS còn có giới hạn bổ sung. Khi xác định đúng lớp policy, kiểm tra runtime thực tế và thay đổi có kiểm soát, tổ chức có thể xử lý lỗi tương thích mà vẫn duy trì mức bảo vệ cần thiết cho khóa, chứng thư và dữ liệu.
