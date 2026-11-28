# Phạm vi dịch vụ JCA, JCE và ảnh hưởng của provider

Java Cryptography Architecture (JCA) là kiến trúc bảo mật mật mã của Java. Nó cung cấp các API chuẩn để ứng dụng yêu cầu dịch vụ như tạo hash, ký số, mã hóa, sinh khóa, thỏa thuận khóa, quản lý chứng thư và tạo số ngẫu nhiên an toàn. Các API này không tự chứa mọi thuật toán; chúng gọi đến implementation do một hoặc nhiều Security Provider cung cấp.

Java Cryptography Extension (JCE) hiện là một phần của JCA, dùng cùng kiến trúc provider. JCE tập trung vào các dịch vụ mã hóa và quản lý khóa, chẳng hạn Cipher, Mac, KeyAgreement và KeyGenerator. JCE đã được tích hợp vào JDK từ lâu; ứng dụng Java hiện đại không cần tải một gói JCE riêng để sử dụng mật mã.

Provider quyết định implementation cụ thể mà ứng dụng nhận được: thuật toán nào có sẵn, cách xử lý transformation, kiểu khóa được hỗ trợ, hiệu năng, khả năng dùng HSM hoặc native crypto và mức độ tương thích với môi trường triển khai. Vì vậy, cần hiểu rõ phạm vi JCA/JCE, quy tắc chọn provider và các chính sách mật mã đang áp dụng trước khi cấu hình runtime.

Bài học tập trung vào API và cấu hình còn dùng trong JDK 26. JCA/JCE và provider architecture là API chính thức, không phải preview feature. Không cần --enable-preview.

## 1. JCA là gì và giải quyết vấn đề nào?

JCA là framework và tập API chuẩn để ứng dụng sử dụng dịch vụ bảo mật mà không phải tự triển khai thuật toán mật mã. Ứng dụng chọn loại dịch vụ và tên thuật toán, sau đó framework tìm provider phù hợp để tạo implementation.

Các mục tiêu chính:

- **Độc lập implementation:** code ứng dụng không phải phụ thuộc trực tiếp vào lớp triển khai nội bộ của một nhà cung cấp.
- **Khả năng thay thế implementation:** có thể chuyển sang provider khác khi môi trường cần HSM, phần cứng tăng tốc, implementation được chứng nhận hoặc một tập thuật toán khác.
- **Mở rộng thuật toán:** provider bổ sung implementation cho dịch vụ đã có hoặc cho một dịch vụ mở rộng theo kiến trúc JCA.
- **Chuẩn hóa giao diện:** ứng dụng gọi engine API thống nhất; provider triển khai phần SPI tương ứng.

Ví dụ, ứng dụng cần SHA-256 có thể viết:

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
~~~

Ứng dụng chỉ yêu cầu dịch vụ MessageDigest với thuật toán SHA-256. JCA tìm provider phù hợp trong môi trường hiện tại và trả về một MessageDigest được nối với implementation của provider đó.

Cách gọi này giúp ứng dụng ít phụ thuộc vào một runtime cụ thể. Cùng một API có thể chọn implementation phần mềm, implementation sử dụng native OS hoặc provider nối tới thiết bị mật mã, tùy cấu hình và khả năng thực tế.

## 2. JCA, JCE và JSSE có phạm vi khác nhau

Các tên JCA, JCE và JSSE có liên quan nhưng không phải ba cách gọi cho cùng một thành phần.

| Thành phần | Phạm vi | Ví dụ API |
|---|---|---|
| JCA | Kiến trúc tổng thể cho dịch vụ mật mã và các dịch vụ bảo mật dựa trên provider | MessageDigest, Signature, KeyPairGenerator, KeyStore, CertificateFactory |
| JCE | Phần mở rộng mật mã nằm trong JCA, tập trung vào mã hóa, MAC, thỏa thuận khóa và thao tác khóa bí mật | Cipher, Mac, KeyAgreement, KeyGenerator, SecretKeyFactory |
| JSSE | Framework và implementation cho TLS/DTLS, xác thực peer, mã hóa và bảo vệ kết nối | SSLContext, SSLEngine, TrustManagerFactory, KeyManagerFactory |

JCE sử dụng cùng provider architecture với JCA và đã là một phần của Java platform. Ứng dụng Java hiện đại không cần cài một gói JCE riêng để gọi các API trong javax.crypto.

JSSE có API và nhiệm vụ riêng để xây dựng kết nối TLS. Tuy nhiên, JSSE sử dụng các dịch vụ mật mã từ JCA/JCE, ví dụ chữ ký, cipher, key agreement và certificate path validation. Khi điều tra một kết nối TLS, có thể phải xem đồng thời cấu hình JSSE, provider và các thuật toán bị hạn chế.

Một điểm cần phân biệt: việc một provider hỗ trợ Cipher hoặc Signature không có nghĩa provider đó tự quản lý toàn bộ chính sách TLS, chứng thư, hostname verification hoặc giao thức ứng dụng. Các lớp và chính sách ở tầng cao hơn vẫn phải được cấu hình đúng.

## 3. Những loại dịch vụ JCA/JCE thường gặp

JCA định nghĩa các engine class. Mỗi engine class cung cấp API cấp cao cho một loại dịch vụ; provider triển khai SPI tương ứng.

| Dịch vụ | Engine class | Công việc |
|---|---|---|
| Hash/message digest | MessageDigest | Tạo digest cố định từ dữ liệu đầu vào |
| Chữ ký số | Signature | Ký bằng private key và xác minh bằng public key |
| Mã hóa/giải mã | Cipher | Thực hiện cipher transformation |
| Message authentication code | Mac | Tạo và kiểm tra mã xác thực thông điệp |
| Sinh khóa bí mật | KeyGenerator | Sinh khóa cho thuật toán đối xứng |
| Sinh cặp khóa | KeyPairGenerator | Sinh public/private key pair |
| Thỏa thuận khóa | KeyAgreement | Tạo material khóa chung giữa các bên |
| Chuyển đổi khóa | KeyFactory, SecretKeyFactory | Tạo hoặc chuyển đổi biểu diễn khóa |
| Tham số thuật toán | AlgorithmParameters, AlgorithmParameterGenerator | Tạo, lưu và đọc tham số thuật toán |
| Số ngẫu nhiên an toàn | SecureRandom | Cung cấp dữ liệu ngẫu nhiên dùng cho bảo mật |
| Lưu trữ khóa | KeyStore | Quản lý khóa và chứng thư |
| Chứng thư | CertificateFactory | Tạo certificate và CRL từ dữ liệu mã hóa |
| Dẫn xuất khóa | KDF | Dẫn xuất khóa từ secret và tham số |
| Đóng gói khóa | KEM | Thực hiện cơ chế key encapsulation |

Danh sách này không có nghĩa mọi provider đều triển khai tất cả dịch vụ. Mỗi provider chỉ công bố những service và algorithm mà implementation của nó hỗ trợ. Một JDK có thể cung cấp cùng một thuật toán thông qua nhiều provider, hoặc chỉ một provider có implementation phù hợp với một dịch vụ cụ thể.

Khi cần kiểm tra tên thuật toán chuẩn, hãy dùng Java Security Standard Algorithm Names. Không dựa vào alias riêng của một provider nếu ứng dụng cần chạy trên nhiều JDK hoặc nhiều nhà cung cấp.

## 4. Provider là gì?

Security Provider là một package hoặc tập package cung cấp implementation cụ thể cho một phần Java Security API. Trong Java, lớp java.security.Provider đại diện cho provider và mô tả các service mà nó hỗ trợ.

Một provider thường công bố:

- Tên và phiên bản provider.
- Các service type, ví dụ Cipher, Signature, MessageDigest, KeyStore hoặc SecureRandom.
- Tên thuật toán và alias được hỗ trợ.
- Lớp SPI triển khai từng service.
- Một số thuộc tính mô tả khả năng hoặc giới hạn của implementation.

Provider có thể triển khai bằng Java thuần, gọi native library, sử dụng phần cứng hoặc kết nối với thiết bị quản lý khóa. Một provider không nhất thiết cung cấp toàn bộ chức năng mật mã của JDK.

Ví dụ trong Oracle JDK:

| Provider | Vai trò thường gặp |
|---|---|
| SUN | Một số dịch vụ nền tảng như digest, SecureRandom và certificate |
| SunRsaSign | Các implementation chữ ký RSA |
| SunEC | Các dịch vụ mật mã đường cong elliptic |
| SunJCE | Nhiều dịch vụ Cipher, Mac, key generation và các dịch vụ JCE |
| SunJSSE | Provider của implementation JSSE/TLS |
| SunPKCS11 | Cầu nối tới thiết bị hoặc thư viện mật mã hỗ trợ PKCS#11 |
| SunMSCAPI | Tích hợp với Windows native cryptographic API |

Danh sách và chức năng cụ thể phụ thuộc JDK distribution, module được cài đặt, hệ điều hành và cấu hình. Không viết code giả định mọi runtime đều có provider mang tên SunJCE, SunEC hoặc SunMSCAPI.

## 5. Engine class và SPI kết nối với nhau thế nào?

Ứng dụng làm việc với engine class. Provider triển khai SPI (Service Provider Interface) để cung cấp phần xử lý thực tế.

Ví dụ:

~~~text
Application code
      |
      v
Cipher.getInstance("AES/GCM/NoPadding")
      |
      v
JCA provider selection
      |
      v
Provider.Service
      |
      v
CipherSpi implementation
      |
      v
Software / native library / HSM
~~~

Một số cặp engine/SPI:

| Engine class | SPI class |
|---|---|
| Cipher | CipherSpi |
| MessageDigest | MessageDigestSpi |
| Signature | SignatureSpi |
| KeyAgreement | KeyAgreementSpi |
| KeyPairGenerator | KeyPairGeneratorSpi |
| SecureRandom | SecureRandomSpi |

Ứng dụng không gọi trực tiếp CipherSpi hoặc MessageDigestSpi trong luồng sử dụng thông thường. JCA tạo engine object và chuyển lời gọi API đến SPI object mà provider cung cấp.

Khi gọi getInstance(), framework chọn implementation và tạo engine object gắn với provider đã chọn. Các lần gọi init(), update() hoặc doFinal() trên engine đó được chuyển tới cùng implementation. Nếu provider được chọn không chấp nhận key hoặc tham số, ứng dụng nhận lỗi từ implementation đó; JCA không mặc định chạy lại thao tác với provider tiếp theo.

Vì vậy, việc tìm được một provider có thuật toán không bảo đảm mọi key, mode, padding, parameter spec hoặc loại thiết bị đều tương thích.

## 6. JCA chọn provider như thế nào?

Khi không chỉ định provider, các phương thức getInstance() tìm provider phù hợp theo thứ tự ưu tiên đã cấu hình. Framework xét service type và thuật toán được yêu cầu, rồi chọn implementation phù hợp đầu tiên.

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
System.out.println(digest.getProvider().getName());
~~~

Có thể kết quả provider khác nhau giữa các JDK hoặc cấu hình máy. Điều này là một phần của thiết kế provider architecture.

Ba cách gọi phổ biến:

~~~java
// 1. Để JCA chọn provider theo cấu hình runtime.
MessageDigest automatic =
        MessageDigest.getInstance("SHA-256");

// 2. Chỉ định tên provider đã đăng ký.
MessageDigest byName =
        MessageDigest.getInstance("SHA-256", providerName);

// 3. Chỉ định trực tiếp đối tượng Provider.
MessageDigest byObject =
        MessageDigest.getInstance("SHA-256", provider);
~~~

Khác biệt:

| Cách gọi | Cách chọn | Hệ quả |
|---|---|---|
| getInstance(algorithm) | JCA tự tìm provider phù hợp | Linh hoạt và thường phù hợp ứng dụng phổ thông |
| getInstance(algorithm, providerName) | Chỉ dùng provider có tên được chỉ định | Provider phải được đăng ký; nếu không có sẽ lỗi |
| getInstance(algorithm, providerObject) | Dùng đối tượng provider được truyền vào | Không bắt buộc provider object phải nằm trong danh sách đăng ký |

Nếu chỉ định provider nhưng provider không hỗ trợ service hoặc algorithm, API có thể ném NoSuchAlgorithmException. Nếu chỉ định tên provider không tồn tại trong danh sách đăng ký, API có thể ném NoSuchProviderException.

### Khuyến nghị chọn provider

Ứng dụng thông thường nên yêu cầu thuật toán chuẩn mà không hard-code tên provider. Điều này cho phép runtime chọn implementation phù hợp, bao gồm provider có tăng tốc phần cứng hoặc tích hợp native.

Chỉ chỉ định provider khi có yêu cầu cụ thể đã được xác định, ví dụ:

- Khóa phải nằm trong HSM hoặc smart card.
- Tổ chức yêu cầu một provider và cấu hình đã được đánh giá/chứng nhận cụ thể.
- Ứng dụng phải dùng implementation có khả năng tương thích đặc biệt.
- Kiểm thử cần cố định implementation để so sánh hoặc tái hiện lỗi.

Không chọn provider chỉ vì thấy tên provider trong một ví dụ trên Internet. Tên provider, phiên bản, module, native library và cấu hình vận hành đều có thể ảnh hưởng đến kết quả.

## 7. Thứ tự provider và cấu hình runtime

Provider có thể được đăng ký tĩnh hoặc động.

**Đăng ký tĩnh** thường được cấu hình trong file:

~~~text
<java-home>/conf/security/java.security
~~~

Các dòng có dạng:

~~~properties
security.provider.1=ProviderA
security.provider.2=ProviderB
security.provider.3=ProviderC
~~~

Số thứ tự biểu thị mức ưu tiên. Giá trị thực tế phải theo tài liệu của provider; provider bên thứ ba có thể yêu cầu tên lớp, module hoặc cấu hình riêng.

**Đăng ký động** có thể thực hiện qua Security API:

~~~java
Provider provider = loadApprovedProvider();
int position = Security.addProvider(provider);

if (position == -1) {
    System.out.println("Provider đã được đăng ký");
} else {
    System.out.println("Provider được thêm ở vị trí " + position);
}
~~~

Security.insertProviderAt() có thể chèn provider vào vị trí ưu tiên cụ thể. Security.removeProvider() loại provider khỏi danh sách. Các thao tác này ảnh hưởng danh sách provider ở cấp JVM, vì vậy không nên thay đổi tùy tiện giữa lúc ứng dụng đang xử lý request.

Provider list được thiết lập khi JVM khởi động, nhưng API Security cho phép thay đổi danh sách trong runtime. Hãy hoàn tất cấu hình provider sớm trước khi khởi tạo các engine object quan trọng. Không coi việc thay đổi provider list là cơ chế tự động chuyển các object đã tạo sang implementation mới.

### Preferred provider theo thuật toán

Trong Oracle JDK, thuộc tính bảo mật jdk.security.provider.preferred có thể xác định provider được ưu tiên cho một thuật toán cụ thể. Vì vậy, thứ tự mà Security.getProviders() trả về không nhất thiết mô tả đầy đủ lựa chọn cuối cùng cho mọi algorithm.

Thuộc tính này không được thiết lập mặc định trong cấu hình thông thường và được dùng cho mục đích điều chỉnh hiệu năng. Khi chẩn đoán provider selection, hãy kiểm tra cấu hình thực tế và provider của engine object đã được tạo, thay vì chỉ nhìn vào số thứ tự trong danh sách.

Không sao chép cấu hình preferred provider từ một máy sang máy khác mà không kiểm tra module, provider, phần cứng và mục tiêu triển khai.

## 8. Kiểm tra provider và service có sẵn

Security.getProviders() trả về danh sách provider đã đăng ký. Provider.getServices() liệt kê service mà provider công bố; getService(type, algorithm) tra cứu một service cụ thể.

~~~java
import java.security.Provider;
import java.security.Security;

public class ProviderInventory {

    public static void main(String[] args) {
        for (Provider provider : Security.getProviders()) {
            System.out.printf(
                    "%s version=%s%n",
                    provider.getName(),
                    provider.getVersionStr());

            Provider.Service service =
                    provider.getService("Cipher", "AES");

            if (service != null) {
                System.out.printf(
                        "  %s.%s -> %s%n",
                        service.getType(),
                        service.getAlgorithm(),
                        service.getClassName());
            }
        }
    }
}
~~~

Ví dụ kiểm tra một engine object thực tế:

~~~java
import javax.crypto.Cipher;

Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");

System.out.println("Algorithm: " + cipher.getAlgorithm());
System.out.println("Provider: " + cipher.getProvider().getName());
~~~

Đây là cách kiểm tra provider đã thực sự được chọn cho transformation. Nó có giá trị hơn việc chỉ xem provider có xuất hiện trong danh sách hay không.

Có thể dùng Security.getProviders(filter) để tìm provider đáp ứng tiêu chí service. Kết quả kiểm tra khả năng cung cấp service không thay thế việc thử khởi tạo engine với transformation, key và tham số mà ứng dụng thực tế sử dụng.

## 9. Provider ảnh hưởng đến thuật toán và transformation

Với Cipher, transformation thường có dạng:

~~~text
algorithm/mode/padding
~~~

Ví dụ:

~~~java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
~~~

Nên chỉ định đầy đủ algorithm, mode và padding. Nếu chỉ truyền tên algorithm, provider có thể chọn mode hoặc padding mặc định riêng. Mặc định có thể khác giữa các provider và không nhất thiết phù hợp với yêu cầu bảo mật của ứng dụng.

Một provider có thể hỗ trợ AES nhưng không hỗ trợ mọi mode, padding hoặc tổ hợp tham số. Vì thế, các tình huống sau có thể khác nhau:

- Cipher.getInstance() tìm được service AES nhưng không hỗ trợ transformation đầy đủ.
- Provider hỗ trợ transformation nhưng không hỗ trợ loại key được truyền vào.
- Provider hỗ trợ key nhưng không hỗ trợ tham số hoặc độ dài cụ thể.
- Provider dùng native/HSM key và không cho phép xuất key material ra Java heap.

Khi sử dụng AES-GCM, ngoài việc chọn transformation còn phải quản lý nonce/IV đúng cách và bảo đảm không tái sử dụng nonce với cùng khóa. Việc chọn provider không tự giải quyết yêu cầu này.

Không dựa vào việc một provider chấp nhận transformation để kết luận thiết kế mật mã của ứng dụng là an toàn. Hãy đánh giá thuật toán, mode, key lifecycle, nonce, authentication tag và protocol ở cấp ứng dụng.

## 10. Provider ảnh hưởng đến key và khả năng tương thích

Các đối tượng Key trong JCA có thể là dạng opaque: ứng dụng chỉ biết interface và metadata cần thiết, còn cách lưu trữ key material phụ thuộc provider.

Ví dụ:

- Khóa phần mềm có thể được lưu trong bộ nhớ và có thể hỗ trợ export qua getEncoded().
- Khóa trong HSM có thể không cho phép export private key material.
- Một key được tạo bởi provider phần cứng có thể chỉ sử dụng được qua provider hoặc thiết bị tương ứng.
- KeyFactory của hai provider có thể tạo các object nội bộ khác nhau dù nhận cùng KeySpec.

Điều này đặc biệt quan trọng khi di chuyển giữa provider, HSM hoặc môi trường triển khai.

Không giả định mọi Key đều có getEncoded() khác null. Không ghi private key hoặc secret key vào log. Không chuyển key material ra khỏi HSM chỉ để làm cho một provider khác có thể sử dụng nếu yêu cầu bảo mật là giữ khóa trong phần cứng.

Nếu cần trao đổi key giữa provider, hãy xác định định dạng chuẩn, loại key, thuật toán, encoding và khả năng hỗ trợ của cả hai phía. Khả năng tương thích thuật toán không đồng nghĩa mọi key object đều có thể chuyển trực tiếp giữa các provider.

## 11. Provider ảnh hưởng đến SecureRandom

SecureRandom là engine class trong JCA. Khi tạo bằng constructor mặc định, Java tìm implementation từ provider đã đăng ký theo thứ tự ưu tiên. Vì vậy, nguồn entropy, thuật toán PRNG/DRBG, hiệu năng và đặc điểm vận hành có thể khác giữa các nền tảng.

Ví dụ:

~~~java
import java.security.SecureRandom;

SecureRandom random = new SecureRandom();

byte[] nonce = new byte[12];
random.nextBytes(nonce);

System.out.println(random.getProvider().getName());
~~~

Nếu cần implementation mạnh được định nghĩa trong cấu hình runtime, API có SecureRandom.getInstanceStrong(). Lựa chọn của API này phụ thuộc security property securerandom.strongAlgorithms.

Không tự seed SecureRandom bằng timestamp, process ID hoặc một giá trị dễ đoán. Gọi setSeed() với dữ liệu yếu không làm cho nguồn ngẫu nhiên trở nên mạnh hơn. Hãy để implementation thu thập entropy theo cơ chế của nó, trừ khi có quy trình seed được thiết kế và đánh giá rõ ràng.

Trong môi trường có HSM hoặc yêu cầu compliance, xác nhận SecureRandom thực sự được tạo từ provider và nguồn ngẫu nhiên được phê duyệt. Không suy luận từ tên provider mà bỏ qua cấu hình thiết bị.

## 12. Provider phần cứng, PKCS#11 và HSM

Provider không chỉ là implementation phần mềm. Một số provider đóng vai trò cầu nối tới thư viện native, hệ điều hành, smart card hoặc HSM.

SunPKCS11 là provider trong JDK dùng giao diện PKCS#11 để kết nối tới native cryptographic token library. Thiết bị có thể thực hiện các thao tác ký, giải mã, sinh khóa hoặc lưu private key trong vùng phần cứng được bảo vệ.

Mô hình khái quát:

~~~text
Java application
       |
       v
JCA engine API
       |
       v
SunPKCS11 / vendor provider
       |
       v
PKCS#11 native library
       |
       v
HSM / smart card / cryptographic token
~~~

Lợi ích có thể gồm:

- Private key không cần xuất ra Java process.
- Thiết bị thực hiện thao tác mật mã trong phần cứng.
- Tổ chức có thể quản lý quyền, audit và vòng đời key tập trung.
- Có thể đáp ứng yêu cầu triển khai hoặc compliance cụ thể.

Các giới hạn cần đánh giá:

- Cần cài và cấu hình native library phù hợp.
- Tên slot, token, login, quyền và session ảnh hưởng đến hoạt động.
- Một số thuật toán hoặc parameter spec có thể không được thiết bị hỗ trợ.
- Key object có thể không tương thích với provider phần mềm.
- Lỗi kết nối thiết bị có thể xuất hiện dưới dạng ProviderException hoặc lỗi đặc thù provider.
- Hiệu năng phụ thuộc thiết bị, network, session và kích thước thao tác.

Không kết luận một hệ thống đạt FIPS chỉ vì đã dùng SunPKCS11 hoặc một provider có chữ “FIPS” trong tên. Phải xác nhận module mật mã, phiên bản, cấu hình vận hành, chứng nhận còn hiệu lực và đúng chế độ được chứng nhận theo yêu cầu tổ chức.

## 13. Khi nào nên chỉ định provider cụ thể?

Ứng dụng phổ thông nên để JCA lựa chọn provider. Chỉ định provider cụ thể khi yêu cầu đó là một phần của kiến trúc hoặc chính sách triển khai.

Ví dụ, tên provider được lấy từ cấu hình môi trường đã được phê duyệt:

~~~java
import java.security.Provider;
import java.security.Security;
import javax.crypto.Cipher;

static Cipher createCipher(String providerName)
        throws Exception {

    Provider provider = Security.getProvider(providerName);

    if (provider == null) {
        throw new IllegalStateException(
                "Provider chưa được đăng ký: " + providerName);
    }

    return Cipher.getInstance(
            "AES/GCM/NoPadding",
            provider);
}
~~~

Không hard-code provider name trong thư viện dùng chung nếu thư viện cần chạy trên nhiều JDK. Hãy đưa provider name vào cấu hình deployment, xác thực provider đã được cài và fail rõ ràng khi môi trường không đáp ứng yêu cầu.

Nếu cần pin provider vì chứng nhận hoặc HSM, hãy ghi lại:

- Tên provider và phiên bản.
- JDK distribution và phiên bản.
- Native library hoặc HSM firmware liên quan.
- Danh sách algorithm/transformation đã kiểm thử.
- Kiểu key và parameter spec được hỗ trợ.
- Chế độ vận hành và chứng nhận có liên quan.
- Cách xử lý khi provider hoặc thiết bị không khả dụng.

Không tự động fallback sang provider phần mềm khi yêu cầu là khóa phải nằm trong HSM hoặc thao tác phải thực hiện trong module đã được chứng nhận. Fallback như vậy có thể làm mất yêu cầu bảo mật mà ứng dụng cần bảo đảm.

## 14. Provider và các chính sách mật mã là hai lớp khác nhau

Provider quyết định implementation nào cung cấp dịch vụ. Chính sách mật mã quyết định thuật toán hoặc độ mạnh nào được phép trong môi trường.

Một thuật toán có thể được provider hỗ trợ nhưng vẫn bị chính sách của runtime từ chối. Ngược lại, thuật toán không bị cấm vẫn có thể không sử dụng được nếu không provider nào hỗ trợ service hoặc transformation đó.

Các cấu hình quan trọng trong JDK 26:

| Cấu hình | Phạm vi |
|---|---|
| crypto.policy | Giới hạn độ mạnh mật mã và key size theo jurisdiction policy files |
| jdk.crypto.disabledAlgorithms | Tắt các thuật toán/service ở tầng JCA/JCE trong Oracle JDK 26 |
| jdk.tls.disabledAlgorithms | Giới hạn thuật toán và protocol trong TLS/DTLS |
| jdk.certpath.disabledAlgorithms | Giới hạn thuật toán khi kiểm tra certificate path |
| security.provider.n | Đăng ký provider và thứ tự ưu tiên chung |
| jdk.security.provider.preferred | Ưu tiên provider theo thuật toán trong Oracle JDK implementation |

Không dùng thay thế các thuộc tính này cho nhau. Ví dụ, crypto.policy không phải danh sách thuật toán TLS được phép; jdk.tls.disabledAlgorithms không phải danh sách service provider; security.provider.n không làm một thuật toán bị cấm trở nên hợp lệ.

## 15. Chính sách độ mạnh JCE và unlimited strength

Trong JDK hiện đại, cấu hình crypto.policy mặc định là unlimited. JDK đã đóng gói sẵn các policy files trong:

~~~text
<java-home>/conf/security/policy
~~~

Hai cấu hình có sẵn là limited và unlimited. Cấu hình được chọn bằng security property crypto.policy trong file:

~~~text
<java-home>/conf/security/java.security
~~~

Ví dụ giá trị mặc định:

~~~properties
crypto.policy=unlimited
~~~

Ở chế độ unlimited, giới hạn key size do jurisdiction policy files không hạn chế độ mạnh theo cấu hình đó. Điều này không có nghĩa mọi thuật toán đều an toàn hoặc mọi service đều được phép: algorithm restrictions, provider support, TLS constraints và quy định pháp luật vẫn phải được xem xét.

Có thể kiểm tra giới hạn key size mà JCE policy cho phép:

~~~java
import javax.crypto.Cipher;

int maximumBits =
        Cipher.getMaxAllowedKeyLength("AES/GCM/NoPadding");

if (maximumBits == Integer.MAX_VALUE) {
    System.out.println("JCE jurisdiction policy: unlimited");
} else {
    System.out.println("Maximum key size: " + maximumBits);
}
~~~

API này báo giới hạn theo jurisdiction policy files. Nó không thay thế kiểm tra provider hỗ trợ transformation, key thực tế, thuật toán có bị disabled hay không và yêu cầu bảo mật của hệ thống.

Không làm theo hướng dẫn cũ yêu cầu tải riêng gói JCE Unlimited Strength Jurisdiction Policy Files cho JDK hiện đại. Những gói tải riêng đó chỉ liên quan các bản JDK cũ; JDK 9 trở lên đã tích hợp policy files và mặc định unlimited.

Nếu môi trường cần giới hạn độ mạnh theo quy định địa phương hoặc chính sách tổ chức, quản trị viên phải chọn cấu hình phù hợp và kiểm tra ảnh hưởng tới mọi ứng dụng chạy trên JVM đó. Thay đổi file security properties thường chỉ có hiệu lực khi khởi động lại JVM.

## 16. Thuộc tính jdk.crypto.disabledAlgorithms trong JDK 26

JDK 26 bổ sung security property jdk.crypto.disabledAlgorithms để giới hạn thuật toán ở tầng JCA/JCE. Thuộc tính này cho phép cấu hình các service và algorithm cần bị chặn, ví dụ theo dạng service name và algorithm name.

Một số engine API trong Oracle JDK 26 kiểm tra thuộc tính này khi tạo instance. Do đó, việc chỉ định provider trực tiếp không phải cách vượt qua một thuật toán đã bị policy chặn.

Cần phân biệt:

- crypto.policy: giới hạn độ mạnh/key size theo jurisdiction policy.
- jdk.crypto.disabledAlgorithms: chặn service/algorithm tại tầng JCA/JCE.
- jdk.tls.disabledAlgorithms: giới hạn TLS/DTLS negotiation và các thành phần liên quan.
- jdk.certpath.disabledAlgorithms: giới hạn thuật toán khi kiểm tra đường dẫn chứng thư.

Trong Oracle JDK 26, system property cùng tên jdk.crypto.disabledAlgorithms có thể ghi đè giá trị security property để đáp ứng trường hợp triển khai cụ thể. Đây là cấu hình nhạy cảm: không bật lại thuật toán bị cấm chỉ để làm cho ứng dụng cũ chạy được. Hãy đánh giá rủi ro, thay dependency hoặc thay thuật toán trước khi xem xét ngoại lệ.

JDK implementation khác có thể không hỗ trợ hoặc không diễn giải các security properties giống Oracle JDK. Khi ứng dụng chạy trên nhiều nhà cung cấp JDK, phải kiểm tra tài liệu của từng runtime.

## 17. Security properties được nạp và chẩn đoán thế nào?

File cấu hình bảo mật chính của JDK là:

~~~text
<java-home>/conf/security/java.security
~~~

Có thể bổ sung một security properties file khác bằng system property:

~~~powershell
java -Djava.security.properties=file:/path/to/extra.security MyApp
~~~

Cách dùng một dấu bằng bổ sung các thuộc tính từ file mới vào file master. Cách dùng hai dấu bằng sẽ thay thế hoàn toàn file master; chỉ dùng khi bạn cung cấp đầy đủ cấu hình cần thiết và hiểu hệ quả.

Security properties có thể được đọc khi JVM khởi động hoặc khi service được khởi tạo. Sau khi chỉnh cấu hình, hãy khởi động lại ứng dụng để kết quả không phụ thuộc trạng thái đã được cache trong process.

Có thể kiểm tra cấu hình bảo mật đang hoạt động:

~~~powershell
java -XshowSettings:security -version
~~~

Để xem log lựa chọn JCA engine và provider trong một môi trường kiểm thử:

~~~powershell
java -Djava.security.debug=jca,provider MyApp
~~~

Nếu chỉ cần xem provider selection cho một số engine, tùy chọn provider có thể kết hợp với engine filter theo tài liệu của JDK. Log debug có thể rất nhiều; không bật rộng trên production nếu chưa đánh giá tác động và thông tin nhạy cảm trong log.

## 18. Đoạn kiểm tra tổng hợp provider, policy và engine

Ví dụ sau ghi nhận provider list, kiểm tra service AES và tạo một Cipher transformation đầy đủ. Nó không thực hiện mã hóa dữ liệu; mục đích là quan sát cấu hình runtime.

~~~java
import java.security.Provider;
import java.security.Security;
import javax.crypto.Cipher;

public class JcaRuntimeCheck {

    public static void main(String[] args) throws Exception {
        System.out.println("Registered providers:");

        for (Provider provider : Security.getProviders()) {
            Provider.Service aes =
                    provider.getService("Cipher", "AES");

            System.out.printf(
                    "%s %s AES=%s%n",
                    provider.getName(),
                    provider.getVersionStr(),
                    aes != null);
        }

        Cipher cipher =
                Cipher.getInstance("AES/GCM/NoPadding");

        System.out.println(
                "Selected transformation: " + cipher.getAlgorithm());

        System.out.println(
                "Selected provider: " +
                cipher.getProvider().getName());

        int maxKeyBits =
                Cipher.getMaxAllowedKeyLength("AES/GCM/NoPadding");

        System.out.println(
                "JCE max key bits: " +
                (maxKeyBits == Integer.MAX_VALUE
                        ? "unlimited"
                        : maxKeyBits));
    }
}
~~~

Kết quả phụ thuộc JDK, provider đã cài và security properties. Không so sánh tên provider với một output cố định rồi coi mọi khác biệt là lỗi. Hãy xác định provider được chọn có đáp ứng yêu cầu môi trường hay không.

Nếu ứng dụng cần provider cố định, hãy thêm một kiểm tra rõ ràng sau khi tạo engine object:

~~~java
String expectedProvider = configuration.getRequiredProviderName();

if (!cipher.getProvider().getName().equals(expectedProvider)) {
    throw new IllegalStateException(
            "Provider không đúng với cấu hình triển khai");
}
~~~

Kiểm tra này giúp phát hiện sớm cấu hình sai. Nó không thay thế việc xác thực provider, phiên bản, HSM, key type và chế độ compliance.

## 19. Những lỗi thường gặp khi làm việc với provider

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| NoSuchAlgorithmException | Không provider nào hỗ trợ service/algorithm hoặc policy không cho phép | Kiểm tra tên chuẩn, provider inventory và security properties |
| NoSuchProviderException | Tên provider được chỉ định chưa được đăng ký | Kiểm tra cấu hình cài đặt và đăng ký provider |
| NoSuchPaddingException | Provider có cipher nhưng không hỗ trợ padding trong transformation | Chọn transformation được provider hỗ trợ và kiểm tra tài liệu |
| InvalidKeyException | Key type, key size, parameter hoặc provider không tương thích | Kiểm tra nguồn key, định dạng và khả năng của provider |
| ProviderException | Provider gặp lỗi nội bộ hoặc không giao tiếp được với token/HSM | Kiểm tra log provider, native library, token và thiết bị |
| Engine chọn provider khác dự kiến | Provider order hoặc preferred-provider config khác môi trường | Kiểm tra getProvider(), security properties và JCA debug |
| Ứng dụng chạy ở máy dev nhưng lỗi ở production | Provider, module, native library hoặc HSM không được cài giống nhau | Chuẩn hóa môi trường và kiểm thử trên đúng image triển khai |
| Key từ HSM không dùng được với provider phần mềm | Key opaque hoặc không export được | Thực hiện thao tác qua provider/thiết bị sở hữu key |
| Transformation được tạo nhưng init thất bại | Provider không hỗ trợ key hoặc tham số thực tế | Kiểm thử đầy đủ init(), không chỉ getInstance() |
| Thay provider order làm ứng dụng đổi hành vi | Provider list là cấu hình dùng chung ở cấp JVM | Cố định cấu hình triển khai, kiểm tra regression và quan sát provider đã chọn |
| AES key dài bị từ chối | Jurisdiction policy hoặc provider giới hạn key size | Kiểm tra Cipher.getMaxAllowedKeyLength() và giới hạn của provider |
| Thuật toán có trong provider nhưng không dùng được | Thuật toán bị security property chặn | Xem jdk.crypto.disabledAlgorithms, TLS hoặc CertPath constraints theo tầng |

## 20. Quy trình chọn và triển khai provider

Khi tích hợp provider mới, thực hiện theo thứ tự:

1. Xác định service và algorithm ứng dụng cần dùng.
2. Xác định yêu cầu về hiệu năng, native OS, HSM, smart card hoặc compliance.
3. Chọn provider có tài liệu và phiên bản phù hợp với JDK mục tiêu.
4. Xác minh nguồn phân phối, chữ ký artifact, module và native dependency.
5. Cấu hình provider theo hướng dẫn của nhà cung cấp.
6. Đăng ký tĩnh hoặc động theo chính sách vận hành.
7. Kiểm tra provider inventory và service list.
8. Tạo engine object bằng standard algorithm name.
9. Kiểm tra provider thực tế qua getProvider().
10. Kiểm thử init, thao tác mật mã, key compatibility, error handling và khả năng khôi phục khi thiết bị mất kết nối.
11. Kiểm tra security properties và các algorithm constraints.
12. Chạy regression trên đúng JDK distribution, OS, container image và môi trường triển khai.

Với provider HSM/FIPS, bổ sung kiểm tra phiên bản module, trạng thái chứng nhận, cấu hình thiết bị và việc private key không bị xuất ra ngoài. Không xem một bài test thành công là bằng chứng đầy đủ cho compliance.

## 21. Bài thực hành tổng hợp

Thực hiện bằng JDK 26:

1. Liệt kê provider bằng Security.getProviders() và ghi nhận tên, version string.
2. Với từng provider, kiểm tra service Cipher/AES bằng Provider.getService().
3. Tạo MessageDigest SHA-256 không chỉ định provider và ghi nhận provider được chọn.
4. Tạo Cipher AES/GCM/NoPadding và xác nhận transformation cùng provider.
5. So sánh getInstance(algorithm) với getInstance(algorithm, providerObject) trên provider đã được đăng ký.
6. Thử truyền tên provider không tồn tại và ghi nhận lỗi.
7. Dùng Cipher.getMaxAllowedKeyLength() để kiểm tra giới hạn theo JCE jurisdiction policy.
8. Dùng -XshowSettings:security để xem security properties của JDK.
9. Chạy với java.security.debug=jca,provider trong môi trường kiểm thử để quan sát lựa chọn engine/provider.
10. Kiểm tra riêng crypto.policy, jdk.crypto.disabledAlgorithms, jdk.tls.disabledAlgorithms và jdk.certpath.disabledAlgorithms.
11. Nếu có môi trường HSM, kiểm tra provider PKCS#11 và xác nhận key không thể export theo chính sách thiết bị.
12. Chạy cùng bộ kiểm thử trên các JDK distribution mà ứng dụng hỗ trợ và ghi nhận khác biệt provider.

**Tiêu chí hoàn thành:** giải thích được JCA và JCE; phân biệt JCE với JSSE; mô tả engine class/SPI/provider; hiểu cách getInstance() chọn implementation; biết khi nào nên hoặc không nên pin provider; kiểm tra provider và service; hiểu ảnh hưởng của provider lên transformation, key, SecureRandom và HSM; phân biệt provider selection với cryptographic policy; kiểm tra crypto.policy và các disabledAlgorithms property; chẩn đoán lỗi bằng JCA/provider debug.

## 22. Tài liệu tham khảo chính thức

- [Java Cryptography Architecture (JCA) Reference Guide – JDK 26](https://docs.oracle.com/en/java/javase/26/security/java-cryptography-architecture-jca-reference-guide.html) — phạm vi JCA/JCE, engine class, SPI, provider selection và cryptographic strength.
- [JDK Providers Documentation – JDK 26](https://docs.oracle.com/en/java/javase/26/security/oracle-providers.html) — provider có trong JDK, service hỗ trợ và ảnh hưởng của provider tới Cipher transformation.
- [java.security.Provider API – Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Provider.html) — mô hình provider, service, registration và ServiceLoader.
- [java.security.Security API – Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/Security.html) — truy vấn, thêm, chèn và gỡ provider; quản lý security properties.
- [javax.crypto.Cipher API – Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/crypto/Cipher.html) — transformation, getProvider và giới hạn key size theo JCE policy.
- [The Security Properties File – JDK 26](https://docs.oracle.com/en/java/javase/26/security/security-properties-file.html) — cấu hình provider, algorithm restrictions và JSSE properties.
- [Security Updates – JDK 26](https://docs.oracle.com/en/java/javase/26/migrate/security-updates.html) — thuộc tính mới jdk.crypto.disabledAlgorithms ở JCE layer.
- [Troubleshooting Security – JDK 26](https://docs.oracle.com/en/java/javase/26/security/troubleshooting-security.html) — -XshowSettings:security và java.security.debug.
- [Java Security Standard Algorithm Names – JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/security/standard-names.html) — tên chuẩn cho service, algorithm, transformation và keystore type.

JCA/JCE tách API sử dụng mật mã khỏi implementation cụ thể của provider. Hãy yêu cầu algorithm name chuẩn, để runtime chọn provider khi không có yêu cầu pinning, xác minh provider thực tế khi triển khai và kiểm tra riêng các chính sách độ mạnh cùng algorithm constraints. Một provider có hỗ trợ thuật toán không tự chứng minh thuật toán đó được phép, an toàn cho use case hoặc đáp ứng yêu cầu compliance của hệ thống.

