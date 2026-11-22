# KEM.getInstance với thuật toán được provider hỗ trợ

Trong Java 21, javax.crypto.KEM cung cấp API Key Encapsulation Mechanism (KEM) theo kiến trúc Java Cryptography Architecture (JCA). Phương thức KEM.getInstance() tạo đối tượng KEM theo tên thuật toán mà một security provider hỗ trợ. Sau đó, ứng dụng tạo Encapsulator bằng public key của bên nhận hoặc Decapsulator bằng private key tương ứng.

Điểm cần hiểu khi dùng getInstance() là tên thuật toán và provider là hai yếu tố riêng. Một thuật toán có thể được nhiều provider triển khai; ngược lại, một provider có thể chỉ hỗ trợ một số thuật toán hoặc một số loại key/curve nhất định. Tạo được đối tượng KEM chưa có nghĩa mọi key đều dùng được với thuật toán đó.

## 1. Vai trò của KEM trong JCA

KEM là cơ chế để hai bên thiết lập cùng một shared secret qua mật mã khóa công khai:

- Bên nhận tạo key pair và công bố public key; private key được giữ bí mật.
- Bên gửi dùng public key để encapsulate, tạo shared secret và một key encapsulation message.
- Bên gửi chuyển encapsulation message cho bên nhận.
- Bên nhận dùng private key và encapsulation message để decapsulate, khôi phục cùng shared secret.

KEM không phải thuật toán mã hóa dữ liệu ứng dụng hoàn chỉnh. Nó tạo shared secret làm đầu vào cho bước dẫn xuất khóa và giao thức bảo vệ dữ liệu tiếp theo. Trong thiết kế thực tế, cần kết hợp KEM với KDF và cơ chế mã hóa xác thực (AEAD) theo một giao thức đã được chuẩn hóa.

Trong Java 21, API nằm trong module java.base, package javax.crypto; không cần thêm module bên ngoài chỉ để truy cập lớp KEM.

## 2. Tên thuật toán và tên provider

Hai thông tin này có ý nghĩa khác nhau:

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Tên KEM algorithm | DHKEM | Chọn loại cơ chế Key Encapsulation Mechanism |
| Provider | SunJCE | Chọn implementation cung cấp thuật toán |
| Key algorithm | X25519, XDH hoặc EC | Mô tả loại key được dùng để tạo encapsulator/decapsulator |

Java Security Standard Algorithm Names của Java 21 quy định tên KEM chuẩn DHKEM, là DH-Based KEM theo RFC 9180. Tên chuẩn không phân biệt chữ hoa và chữ thường, nhưng nên dùng đúng cách viết DHKEM trong mã để dễ đối chiếu tài liệu.

Không nhầm DHKEM với DiffieHellman của KeyAgreement. KEM là một JCA engine riêng với quy trình encapsulate/decapsulate; KeyAgreement có API và hợp đồng khác.

## 3. Ba dạng getInstance()

KEM cung cấp ba overload chính:

~~~java
KEM kem = KEM.getInstance("DHKEM");
~~~

Yêu cầu implementation cho thuật toán từ danh sách provider đã đăng ký mà không khóa trước một provider cụ thể cho các encapsulator/decapsulator. Provider thực tế có thể được chọn khi tạo encapsulator hoặc decapsulator, dựa trên key và tham số. Đây là dạng phù hợp cho ứng dụng thông thường vì không gắn mã nguồn với một provider cụ thể.

~~~java
KEM kem = KEM.getInstance("DHKEM", "SunJCE");
~~~

Chỉ định provider bằng tên. Provider phải được đăng ký trong security provider list. Dạng này ném NoSuchProviderException nếu không tìm thấy provider có tên đó.

~~~java
Provider provider = Security.getProvider("SunJCE");
KEM kem = KEM.getInstance("DHKEM", provider);
~~~

Chỉ định trực tiếp một đối tượng Provider. Dạng này hữu ích khi ứng dụng đã có tham chiếu provider được cấu hình hoặc cung cấp.

Các overload có provider vẫn ném NoSuchAlgorithmException nếu provider được chỉ định không cung cấp dịch vụ KEM cho thuật toán yêu cầu. Nếu truyền null cho provider, API tương đương với getInstance(String); vì vậy, khi provider là cấu hình bắt buộc, hãy kiểm tra null trước khi gọi để tránh vô tình chuyển sang lựa chọn mặc định.

## 4. Provider hỗ trợ thuật toán có nghĩa là gì?

Trong kiến trúc JCA, provider đăng ký các dịch vụ mật mã. Với KEM, dịch vụ có service type là KEM và tên thuật toán tương ứng, ví dụ DHKEM.

Có thể xem provider nào đang công bố dịch vụ DHKEM:

~~~java
import java.security.Provider;
import java.security.Security;

for (Provider provider : Security.getProviders()) {
    Provider.Service service = provider.getService("KEM", "DHKEM");
    if (service != null) {
        System.out.println(
                provider.getName() + " supports " + service.getAlgorithm()
        );
    }
}
~~~

Đoạn mã chỉ kiểm tra service đã được đăng ký. Nó không chứng minh provider hỗ trợ mọi key, curve hoặc tham số. Khả năng dùng thực tế còn phụ thuộc cấu hình mà provider triển khai.

Trong Oracle JDK 21, provider tích hợp SunJCE cung cấp dịch vụ KEM cho thuật toán DHKEM. Implementation này hỗ trợ:

- EC key trên các đường cong secp256r1, secp384r1 và secp521r1.
- XDH key trên X25519 (Curve25519) và X448 (Curve448).

Provider của một bản phân phối Java khác hoặc provider bên thứ ba có thể có danh sách hỗ trợ khác. Hãy kiểm tra tài liệu của đúng JDK/provider được triển khai.

## 5. Dùng getInstance() với provider mặc định

Ví dụ sau tạo key pair X25519, sau đó dùng DHKEM để encapsulate và decapsulate:

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.util.Arrays;
import javax.crypto.KEM;
import javax.crypto.SecretKey;

public class DhKemExample {
    public static void main(String[] args) throws Exception {
        // Bên nhận tạo key pair và giữ private key.
        KeyPairGenerator keyPairGenerator =
                KeyPairGenerator.getInstance("X25519");
        KeyPair recipientKeys = keyPairGenerator.generateKeyPair();

        // Có thể dùng cùng KEM object để tạo hai phía.
        KEM kem = KEM.getInstance("DHKEM");

        // Bên gửi dùng public key để tạo shared secret và encapsulation.
        KEM.Encapsulator encapsulator =
                kem.newEncapsulator(recipientKeys.getPublic());
        KEM.Encapsulated encapsulated = encapsulator.encapsulate();
        SecretKey senderSecret = encapsulated.key();

        // Bên nhận dùng private key và encapsulation để khôi phục secret.
        KEM.Decapsulator decapsulator =
                kem.newDecapsulator(recipientKeys.getPrivate());
        SecretKey receiverSecret =
                decapsulator.decapsulate(encapsulated.encapsulation());

        boolean sameSecret = Arrays.equals(
                senderSecret.getEncoded(),
                receiverSecret.getEncoded()
        );

        System.out.println("Algorithm: " + kem.getAlgorithm());
        System.out.println("Encapsulator provider: "
                + encapsulator.providerName());
        System.out.println("Decapsulator provider: "
                + decapsulator.providerName());
        System.out.println("Same secret: " + sameSecret);
    }
}
~~~

Các bước chính:

1. KeyPairGenerator.getInstance("X25519") tạo key pair cho bên nhận. Đây là API tạo key, độc lập với KEM.getInstance().
2. KEM.getInstance("DHKEM") lấy implementation của KEM algorithm từ provider phù hợp.
3. newEncapsulator(publicKey) kiểm tra public key và tạo đối tượng phía gửi.
4. encapsulate() tạo shared secret cùng encapsulation message.
5. newDecapsulator(privateKey) tạo đối tượng phía nhận.
6. decapsulate(encapsulation) khôi phục shared secret tương ứng.

Ví dụ so sánh hai SecretKey để minh họa hai phía thu được cùng secret. Trong ứng dụng thực tế, không in hoặc ghi log secret; không truyền secret dưới dạng dữ liệu thông thường và cần đưa nó qua quy trình dẫn xuất khóa phù hợp.

## 6. Provider được chọn ở thời điểm nào?

Khi gọi KEM.getInstance("DHKEM") mà không chỉ định provider, ứng dụng yêu cầu một implementation cho thuật toán. Tuy nhiên, provider dùng cho Encapsulator hoặc Decapsulator có thể được quyết định khi gọi newEncapsulator() hoặc newDecapsulator().

Việc chọn provider ở các bước này dựa trên:

- Public key hoặc private key được truyền vào.
- AlgorithmParameterSpec tùy chọn, nếu thuật toán yêu cầu hoặc sử dụng.
- Khả năng hỗ trợ cấu hình tương ứng của provider.

Vì vậy, cùng một đối tượng KEM có thể tạo encapsulator và decapsulator từ hai provider khác nhau nếu không khóa provider. Có thể xem provider thực tế qua:

~~~java
String senderProvider = encapsulator.providerName();
String receiverProvider = decapsulator.providerName();
~~~

Đối tượng KEM là immutable và cho phép gọi đồng thời nhiều lần newEncapsulator()/newDecapsulator(). Các đối tượng Encapsulator và Decapsulator cũng immutable, và API cho phép gọi nhiều lần encapsulate() hoặc decapsulate() đồng thời trên cùng instance theo hợp đồng của lớp.

## 7. Khi cần chỉ định provider cụ thể

Nếu hệ thống có yêu cầu rõ ràng về provider, ví dụ provider được kiểm định hoặc cấu hình vận hành bắt buộc, hãy chỉ định provider nhất quán ở cả hai phía:

~~~java
import java.security.Provider;
import java.security.Security;
import javax.crypto.KEM;

Provider provider = Security.getProvider("SunJCE");
if (provider == null) {
    throw new IllegalStateException("Required provider is unavailable");
}

KEM kem = KEM.getInstance("DHKEM", provider);
~~~

Khi dùng kem để tạo encapsulator và decapsulator, các thao tác sẽ bị ràng buộc vào provider đã chỉ định. Nếu provider không hỗ trợ DHKEM, getInstance() ném NoSuchAlgorithmException.

Cũng có thể chỉ định tên provider:

~~~java
KEM kem = KEM.getInstance("DHKEM", "SunJCE");
~~~

Dạng tên phù hợp khi provider đã được đăng ký. Nếu tên không tồn tại, phương thức ném NoSuchProviderException; nếu provider tồn tại nhưng không hỗ trợ DHKEM, phương thức ném NoSuchAlgorithmException.

Ứng dụng tổng quát thường nên để JCA chọn provider thay vì hard-code tên SunJCE. Việc chỉ định provider cụ thể có thể làm ứng dụng phụ thuộc vào một bản phân phối JDK hoặc cấu hình bảo mật nhất định, đồng thời ngăn provider khác cung cấp implementation tối ưu hơn.

## 8. Phân biệt lỗi khi lấy instance và lỗi khi tạo encapsulator

Hai giai đoạn có thể thất bại vì những lý do khác nhau:

| Giai đoạn | Lỗi thường gặp | Ý nghĩa |
|---|---|---|
| KEM.getInstance("DHKEM") | NoSuchAlgorithmException | Không có provider nào cung cấp KEM algorithm yêu cầu |
| KEM.getInstance(algorithm, providerName) | NoSuchProviderException | Tên provider chưa được đăng ký |
| KEM.getInstance(algorithm, provider) | NoSuchAlgorithmException | Provider đã chọn không hỗ trợ algorithm |
| newEncapsulator(publicKey) | InvalidKeyException | Public key không hợp lệ hoặc không được provider hỗ trợ |
| newDecapsulator(privateKey) | InvalidKeyException | Private key không hợp lệ hoặc không được provider hỗ trợ |
| Tạo encapsulator/decapsulator với spec | InvalidAlgorithmParameterException | Tham số không hợp lệ hoặc cấu hình yêu cầu spec nhưng không được cung cấp |
| Gọi overload không có spec trong khi provider yêu cầu spec | UnsupportedOperationException | Provider không hỗ trợ overload rút gọn đó |

Không nên xử lý mọi lỗi bằng cách đổi sang một thuật toán khác một cách âm thầm. Nếu thuật toán hoặc provider bắt buộc không có, hãy báo lỗi cấu hình rõ ràng để người vận hành chọn provider/algorithm đã được phê duyệt.

## 9. Thuật toán và cấu hình được hỗ trợ trong Java 21

Đối với Java 21, tên KEM chuẩn trong Java Security Standard Algorithm Names là DHKEM. Oracle JDK 21 cung cấp implementation DHKEM trong SunJCE, với các nhóm key/curve nêu ở trên.

Không giả định rằng một thuật toán xuất hiện trong tài liệu của JDK mới hơn sẽ có sẵn trong Java 21. Danh sách thuật toán chuẩn và implementation thay đổi theo phiên bản JDK và provider. Khi nâng cấp runtime hoặc thay provider, cần xác minh lại cả algorithm name lẫn key/parameter configuration.

## 10. Những lưu ý bảo mật khi sử dụng KEM

- Xác thực public key của bên nhận theo giao thức ứng dụng; getInstance() không xác minh danh tính chủ sở hữu key.
- Bảo vệ private key và không gửi private key qua mạng.
- Truyền encapsulation message nguyên vẹn cho bên nhận; giao thức cần xác định cách đóng gói, định danh thuật toán và tham số.
- Không xem KEM là cơ chế mã hóa payload; sử dụng KDF và AEAD theo giao thức đã được thiết kế, đánh giá.
- Không ghi shared secret, private key hoặc dữ liệu nhạy cảm vào log.
- Không chọn provider chỉ vì tên thuật toán giống nhau; kiểm tra nguồn gốc, cấu hình và mức độ tin cậy của provider.
- Xử lý NoSuchAlgorithmException, InvalidKeyException và InvalidAlgorithmParameterException ở ranh giới cấu hình/khởi tạo, không che giấu bằng fallback không được phê duyệt.

## 11. Checklist chọn KEM instance

- [ ] Xác định tên KEM algorithm theo Java Security Standard Algorithm Names.
- [ ] Xác nhận runtime Java 21 và provider thực tế hỗ trợ algorithm đó.
- [ ] Chọn getInstance(String) nếu không có yêu cầu khóa provider.
- [ ] Dùng overload provider khi chính sách triển khai yêu cầu provider cụ thể.
- [ ] Kiểm tra provider có hỗ trợ loại key, curve và tham số sẽ truyền vào.
- [ ] Kiểm tra providerName() của encapsulator/decapsulator khi cần xác minh provider thực tế.
- [ ] Phân biệt lỗi không tìm thấy algorithm/provider với lỗi key hoặc parameter không hợp lệ.
- [ ] Dùng KEM như một phần của giao thức có KDF và AEAD phù hợp.

KEM.getInstance() là điểm bắt đầu để yêu cầu một KEM implementation từ JCA provider. Lựa chọn đúng không chỉ là tên DHKEM, mà còn là provider, loại key và tham số được provider đó hỗ trợ. Khi hiểu rõ các giai đoạn này, ứng dụng có thể khởi tạo KEM tường minh, kiểm tra lỗi đúng chỗ và giữ tính tương thích giữa môi trường phát triển với runtime triển khai.

## Tài liệu tham khảo

- [Oracle Java SE 21 API — KEM](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEM.html)
- [Java SE 21 — Java Security Standard Algorithm Names](https://docs.oracle.com/en/java/javase/21/docs/specs/security/standard-names.html)
- [Oracle JDK 21 — JDK Providers Documentation](https://docs.oracle.com/en/java/javase/21/security/oracle-providers.html)
- [Oracle Java SE 21 API — KEMSpi](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/crypto/KEMSpi.html)
