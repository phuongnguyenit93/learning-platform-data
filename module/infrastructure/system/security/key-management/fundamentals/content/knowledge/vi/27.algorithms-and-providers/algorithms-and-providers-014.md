# Không phụ thuộc behavior không chuẩn

Khi lập trình mật mã với Java, ứng dụng cần dựa trên **hành vi được đặc tả và được tài liệu hóa**, thay vì dựa vào những chi tiết tình cờ quan sát được ở một JDK, Security provider hoặc thiết bị cụ thể. Một đoạn code có thể chạy đúng trên máy phát triển nhưng thất bại sau khi nâng JDK, đổi provider, chuyển từ file keystore sang HSM hoặc triển khai trên hệ điều hành khác nếu nó phụ thuộc vào mặc định, alias riêng, định dạng nội bộ hay cách xử lý chưa được bảo đảm.

Trong Java Cryptography Architecture (JCA), cùng một API có thể được triển khai bởi nhiều provider. API chuẩn tạo khả năng thay thế, nhưng không cam kết mọi provider hỗ trợ cùng thuật toán, tham số, loại key, định dạng hoặc tính năng mở rộng. Vì vậy, ứng dụng phải xác định rõ hợp đồng mật mã cần dùng, kiểm tra khả năng hỗ trợ trên môi trường đích và xử lý trường hợp không tương thích một cách có chủ đích.

Bài học thuộc phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chương **Algorithm và provider**. Nội dung liên kết tính portable của ứng dụng với vòng đời khóa: tạo, cấp phát, lưu trữ, sử dụng, backup, xoay vòng, thu hồi và hủy; đồng thời xét mật mã đối xứng, bất đối xứng, chữ ký số, certificate/PKI, KMS/HSM, kiểm soát truy cập và kiểm toán.

## 1. Behavior chuẩn và behavior phụ thuộc implementation

Khi đọc một API hoặc giao thức, cần phân biệt:

| Loại behavior | Ý nghĩa | Cách sử dụng |
|---|---|---|
| Được đặc tả (specified) | Hợp đồng được định nghĩa trong Java API, JCA specification, chuẩn thuật toán hoặc giao thức | Có thể dựa vào trong phạm vi phiên bản và điều kiện được nêu. |
| Được tài liệu hóa riêng (documented extension) | Tính năng do provider hoặc nhà cung cấp bổ sung và có tài liệu cam kết | Chỉ dùng khi chấp nhận phụ thuộc provider/phiên bản đó. |
| Phụ thuộc implementation (implementation-specific) | Hành vi do một JDK/provider/thiết bị lựa chọn và không được chuẩn chung bảo đảm | Không dùng làm hợp đồng portable; phải cô lập và kiểm tra rõ. |
| Không được đặc tả đầy đủ (unspecified) | Chuẩn không quy định một kết quả duy nhất cho trường hợp đó | Không suy luận một kết quả cụ thể từ thử nghiệm trên một môi trường. |
| Không hợp lệ hoặc không được hỗ trợ | Đầu vào/operation vi phạm hợp đồng hoặc provider không cung cấp chức năng | Xử lý lỗi rõ ràng; không âm thầm đổi sang thuật toán khác. |

"Không chuẩn" không có nghĩa mọi extension của provider đều xấu. Một tính năng HSM riêng có thể cần thiết. Vấn đề xuất hiện khi ứng dụng dựa vào extension đó mà không khai báo ràng buộc, hoặc nhầm hành vi của một implementation với bảo đảm chung của Java.

Ví dụ, nếu một ứng dụng chỉ chạy được vì provider đầu tiên trong danh sách tình cờ hỗ trợ alias nội bộ, ứng dụng đang phụ thuộc vào cấu hình runtime cụ thể. Khi thứ tự provider thay đổi, tên alias không còn được nhận diện và ứng dụng có thể dừng hoạt động.

## 2. Vì sao phụ thuộc behavior không chuẩn nguy hiểm?

Phụ thuộc ngầm có thể tạo ra nhiều loại sự cố:

- **Lỗi sau nâng cấp:** JDK hoặc provider thay đổi mặc định, loại bỏ alias cũ hay siết chặt thuật toán yếu.
- **Sai khác môi trường:** máy phát triển có provider hoặc native library mà production không có.
- **Sai khác kết quả:** hai provider diễn giải tham số mặc định khác nhau hoặc xuất dữ liệu theo encoding khác nhau.
- **Mất khả năng khôi phục:** keystore/backup chỉ đọc được bằng một provider hoặc phiên bản không còn được cài đặt.
- **Fallback ngoài ý muốn:** HSM lỗi nhưng ứng dụng tự chuyển sang software provider, làm private key rời khỏi ranh giới bảo vệ.
- **Giảm mức bảo mật:** ứng dụng dựa vào mode/padding mặc định hoặc thuật toán cũ vẫn được provider hỗ trợ.
- **Khó kiểm toán:** log chỉ ghi tên thuật toán chung mà không ghi provider, phiên bản, key ID và tham số thực tế.

Trong quản lý khóa, một khác biệt nhỏ về cách tạo, serialize hoặc chọn key có thể làm mất khả năng giải mã dữ liệu lịch sử hoặc làm chữ ký không thể xác minh. Vì vậy, tính tương thích cần được thiết kế cùng lúc với bảo mật và vòng đời khóa.

## 3. Đọc hợp đồng trước khi dựa vào hành vi

Nguồn xác định behavior nên được ưu tiên theo đúng phạm vi:

1. Java API Specification của đúng phiên bản JDK.
2. JCA/JCE, JSSE và Java Standard Algorithm Names documentation.
3. Chuẩn mật mã/giao thức được hệ thống sử dụng, ví dụ RFC hoặc tiêu chuẩn tương ứng.
4. Tài liệu provider, HSM/KMS và native library nếu ứng dụng dùng extension riêng.
5. Kiểm thử trên đúng runtime để xác nhận behavior đã được tài liệu hóa.

Một thử nghiệm thành công chỉ chứng minh một tổ hợp JDK/provider/cấu hình đã chạy trong điều kiện thử nghiệm. Nó không tự biến behavior đó thành cam kết của mọi phiên bản.

Khi tài liệu không nói rõ một chi tiết, không tự suy ra từ cách implementation hiện tại hoạt động. Hãy chọn một cách sử dụng được chuẩn định nghĩa, hoặc ghi nhận rõ phụ thuộc và tạo kiểm thử tương thích riêng.

## 4. Không phụ thuộc vào provider mặc định một cách vô thức

JCA cho phép tạo engine object mà không chỉ định provider:

~~~java
Signature signature = Signature.getInstance("SHA256withRSA");
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
~~~

Trong trường hợp này, JCA lựa chọn provider theo danh sách và quy tắc của runtime. Cách gọi này có thể phù hợp nếu ứng dụng chấp nhận provider đã được quản trị tập trung và mọi provider trong runtime đều nằm trong danh sách tin cậy.

Nếu ứng dụng bắt buộc thao tác phải chạy trong HSM, hoặc phải dùng một module đã được phê duyệt, không nên dựa vào provider mặc định. Hãy kiểm tra provider được cấu hình và chỉ định rõ:

~~~java
Provider hsmProvider = Security.getProvider("ApprovedHsmProvider");
if (hsmProvider == null) {
    throw new IllegalStateException("Required HSM provider is unavailable");
}

Signature signer =
        Signature.getInstance("SHA256withRSA", hsmProvider);
~~~

Tên provider trong ví dụ là cấu hình minh họa. Ứng dụng phải dùng đúng provider đã được phê duyệt cho môi trường của mình. Nếu provider bắt buộc không sẵn sàng, xử lý lỗi theo policy; không tự động dùng provider phần mềm để tiếp tục ký.

## 5. Không dựa vào thứ tự provider như một hợp đồng ngầm

Danh sách provider có thể được cấu hình trong java.security hoặc thay đổi bằng Security.addProvider, insertProviderAt và removeProvider. Thứ tự ảnh hưởng đến quá trình tìm implementation khi ứng dụng không chỉ định provider.

Không nên viết logic kiểu:

~~~java
Provider provider = Security.getProviders()[0];
Signature signature =
        Signature.getInstance("SHA256withRSA", provider);
~~~

Provider đứng đầu có thể khác giữa JDK, bản phân phối, container hoặc cấu hình bảo mật. Hãy tìm provider theo tên đã cấu hình, kiểm tra service cần dùng và ghi nhận phiên bản thực tế.

Không thêm hoặc gỡ provider theo từng request. Provider list là cấu hình bảo mật dùng chung trong JVM; thay đổi động có thể khiến các thành phần khác nhau chọn implementation khác nhau. Nên đăng ký provider ở bootstrap và quản lý thay đổi qua quy trình review, kiểm thử và rollback.

## 6. Không dùng alias riêng của provider như tên chuẩn

Một provider có thể công bố canonical name và các alias tương thích. Alias riêng có thể bị đổi hoặc không tồn tại trong provider khác.

Ví dụ, code nên ưu tiên tên chuẩn được Java/provider documentation công bố:

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
Signature signature = Signature.getInstance("SHA256withRSA");
~~~

Không tự suy ra alias chỉ từ cách viết. Một tên được một provider chấp nhận có thể không được provider khác hỗ trợ. Khi buộc phải dùng alias do vendor cung cấp, hãy ghi rõ provider, phiên bản và tài liệu hỗ trợ; kiểm tra alias trong startup health check.

Tên thuật toán cũng phải đi cùng engine class. SHA-256 trong MessageDigest là digest; SHA256withRSA trong Signature là chữ ký; AES/GCM/NoPadding trong Cipher là transformation. Không dùng một chuỗi tên ở sai service type.

## 7. Không phụ thuộc vào transformation mặc định của Cipher

Không nên gọi:

~~~java
Cipher cipher = Cipher.getInstance("AES");
~~~

Tên ngắn có thể để mode và padding phụ thuộc vào provider hoặc quy tắc của implementation. Khi cần mã hóa dữ liệu mới, chỉ định transformation đầy đủ:

~~~java
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
~~~

Ngoài transformation, phải chỉ định tham số cần thiết như nonce/IV và tag length. Với AES-GCM, nonce không được tái sử dụng với cùng key. Nếu nhiều instance cùng mã hóa bằng một key, cần một chiến lược bảo đảm uniqueness xuyên instance và sau khôi phục.

Không giả định provider sẽ tự sinh IV giống nhau hoặc dùng cùng độ dài IV/tag nếu ứng dụng không truyền tham số. Ghi rõ tham số trong format dữ liệu và kiểm thử cả quá trình giải mã ở provider khác.

## 8. Không dựa vào padding hoặc tham số OAEP mặc định

RSA-OAEP có các tham số như hash, MGF, hash cho MGF1 và label. Chỉ chọn tên transformation chưa chắc đã làm rõ mọi tham số cần tương thích giữa các provider.

Ví dụ, truyền tham số tường minh:

~~~java
OAEPParameterSpec oaep = new OAEPParameterSpec(
        "SHA-256",
        "MGF1",
        MGF1ParameterSpec.SHA256,
        PSource.PSpecified.DEFAULT);

Cipher cipher = Cipher.getInstance(
        "RSA/ECB/OAEPWithSHA-256AndMGF1Padding");
cipher.init(Cipher.ENCRYPT_MODE, recipientPublicKey, oaep);
~~~

Tương tự, RSA-PSS cần xác định hash, MGF, MGF digest và salt length. Không dựa vào PSS default của provider vì hai phía có thể chọn tham số khác nhau.

Với CBC, phải quy định IV và padding rõ ràng; CBC không tự cung cấp xác thực dữ liệu. Với GCM, quy định nonce, tag length và cách lưu authentication tag. Các tham số cần trở thành một phần của protocol/data format có version.

## 9. Không dựa vào key size hoặc curve mặc định

Một số API cho phép gọi initialize mà không truyền key size hoặc parameter spec. Khi đó provider có thể dùng mặc định:

~~~java
KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
SecureRandom random = new SecureRandom();
generator.initialize(3072, random);
KeyPair pair = generator.generateKeyPair();
~~~

Ví dụ trên nêu rõ key size. Với EC, nên chỉ định named curve hoặc ECParameterSpec theo profile được phê duyệt:

~~~java
KeyPairGenerator ec = KeyPairGenerator.getInstance("EC");
ec.initialize(new ECGenParameterSpec("secp256r1"), random);
KeyPair ecPair = ec.generateKeyPair();
~~~

Tên curve phải được hỗ trợ bởi provider và phù hợp với policy. Không dựa vào curve mặc định của provider hoặc hệ điều hành.

Key size và curve phải phù hợp với thuật toán, thời hạn sử dụng, tiêu chuẩn nội bộ và khả năng tương thích của hệ thống nhận. Ghi nhận thông tin này trong key inventory cùng key ID/version.

## 10. Không nhầm hỗ trợ thuật toán với bảo đảm được phép sử dụng

Một provider liệt kê thuật toán không có nghĩa thuật toán đó phù hợp cho mọi trường hợp. Provider có thể tiếp tục hỗ trợ thuật toán legacy để đọc dữ liệu cũ, trong khi security policy của tổ chức không cho phép dùng nó để tạo dữ liệu mới.

Ví dụ:

- MD5 hoặc SHA-1 có thể còn xuất hiện trong hệ thống cũ nhưng không nên chọn cho thiết kế mới cần chống va chạm.
- RSA PKCS#1 v1.5 có thể tồn tại vì tương thích; profile mới có thể yêu cầu RSA-PSS.
- DES/3DES có thể được provider hỗ trợ vì dữ liệu legacy nhưng không phù hợp cho mã hóa mới.
- ECB có thể được triển khai nhưng không phù hợp để mã hóa dữ liệu có cấu trúc lặp.

Phải phân biệt "provider hỗ trợ" với "policy cho phép". Kiểm tra cả Java security properties, chính sách TLS/certificate, yêu cầu FIPS nếu có và policy của KMS/HSM.

## 11. Không dựa vào provider-specific key object

Các interface PrivateKey, PublicKey và SecretKey là hợp đồng API. Provider có thể trả về lớp triển khai riêng. Không ép kiểu key object sang class nội bộ của provider nếu ứng dụng không bị ràng buộc rõ ràng với provider đó.

Không nên giả định mọi private key đều có thể export:

~~~java
byte[] encoded = privateKey.getEncoded();
~~~

getEncoded() có thể trả về null nếu khóa không exportable hoặc provider không cung cấp encoding. Với HSM-backed key, object Java có thể chỉ đại diện cho handle đến khóa trong thiết bị.

Ứng dụng nên sử dụng key object trực tiếp qua engine tương ứng:

~~~java
Signature signer = Signature.getInstance("SHA256withRSA", hsmProvider);
signer.initSign(privateKey);
signer.update(message);
byte[] signed = signer.sign();
~~~

Provider của key object và provider thực hiện operation phải tương thích. Nếu key object gắn với HSM, dùng provider có khả năng thao tác với key đó; không export private key sang provider phần mềm để né lỗi tương thích.

## 12. Không dựa vào định dạng nội bộ của key hoặc chữ ký

Không tự phân tích private key bằng cách giả định cấu trúc byte hoặc class triển khai. Khi cần serialize, dùng chuẩn được xác định như PKCS#8 cho private key, X.509 SubjectPublicKeyInfo cho public key hoặc PKCS#12 cho container, và chỉ khi provider cho phép export.

Đối với chữ ký, không giả định mọi thuật toán tạo cùng định dạng:

- RSA signature thường có độ dài liên quan đến modulus.
- ECDSA signature trong nhiều API/format được mã hóa dạng ASN.1 DER, nhưng hệ thống khác có thể yêu cầu dạng fixed-width r || s.
- Ed25519 có độ dài chữ ký xác định theo thuật toán.

Nếu chữ ký được gửi qua API hoặc lưu trữ lâu dài, phải định nghĩa encoding trong protocol. Không dùng toString() của key/certificate/signature object làm định dạng trao đổi.

Với certificate, dùng CertificateFactory hoặc thư viện ASN.1 phù hợp để phân tích X.509; không cắt chuỗi PEM bằng giả định rằng mọi file đều có đúng một certificate hoặc một thứ tự cố định.

## 13. Không dựa vào default charset hoặc cách chuyển byte

Mật mã xử lý byte, còn dữ liệu ứng dụng thường là text. Không dùng charset mặc định của JVM khi chuyển chuỗi sang byte:

~~~java
byte[] message = text.getBytes();
~~~

Hãy chỉ định encoding rõ ràng:

~~~java
byte[] message = text.getBytes(StandardCharsets.UTF_8);
String restored = new String(message, StandardCharsets.UTF_8);
~~~

Hai hệ thống dùng charset khác nhau có thể tạo byte sequence khác nhau từ cùng chuỗi, khiến digest hoặc chữ ký không khớp. Với dữ liệu cấu trúc, cần xác định cả encoding, normalization, thứ tự field, canonicalization và serialization version trước khi băm hoặc ký.

Không giả định thứ tự byte của số nguyên, cách biểu diễn timestamp hoặc thứ tự thuộc tính JSON/XML là giống nhau giữa mọi thư viện. Dữ liệu được ký phải có canonical representation được hai phía thống nhất.

## 14. Không dựa vào default SecureRandom hoặc cách seed thủ công

SecureRandom là API chuẩn cho số ngẫu nhiên mật mã. Không thay bằng java.util.Random, timestamp, UUID tự chế hoặc bộ sinh số ngẫu nhiên của ứng dụng.

Không tự seed SecureRandom bằng giá trị dễ đoán như thời gian hiện tại:

~~~java
SecureRandom random = new SecureRandom();
byte[] nonce = new byte[12];
random.nextBytes(nonce);
~~~

Để provider/JDK quản lý nguồn entropy theo nền tảng thường an toàn hơn việc tự cung cấp seed yếu. Không gọi setSeed với dữ liệu có entropy thấp với niềm tin rằng điều đó làm random mạnh hơn.

Nếu policy yêu cầu DRBG hoặc nguồn ngẫu nhiên cụ thể, chọn algorithm/provider theo tài liệu JDK và module đã phê duyệt, kiểm tra availability ở startup và không fallback âm thầm.

## 15. Không dựa vào thread-safety của engine object

Không nên chia sẻ một instance Cipher, Signature, Mac hoặc MessageDigest giữa nhiều thread nếu tài liệu API/provider không cam kết thread-safe. Nhiều engine object có trạng thái nội bộ thay đổi qua init, update, doFinal, sign hoặc verify.

Một pattern an toàn hơn là tạo instance theo operation hoặc dùng pool có reset/ownership rõ ràng:

~~~java
byte[] encrypt(SecretKey key, byte[] nonce, byte[] plaintext)
        throws GeneralSecurityException {
    Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
    cipher.init(
            Cipher.ENCRYPT_MODE,
            key,
            new GCMParameterSpec(128, nonce));
    return cipher.doFinal(plaintext);
}
~~~

Không giả định engine object có thể được dùng lại sau mọi exception. Nếu tái sử dụng, phải gọi init lại theo hợp đồng và kiểm tra trạng thái; cách đơn giản là tạo object mới cho operation nhạy cảm khi chi phí cho phép.

## 16. Không dựa vào việc engine tự reset giống nhau sau lỗi

Các engine có lifecycle riêng. Ví dụ, MessageDigest.digest() hoàn tất digest và đưa object về trạng thái ban đầu theo hợp đồng API; Cipher.doFinal() kết thúc operation nhưng việc tiếp tục dùng object cần tuân theo quy tắc init và state của Cipher.

Không dựa vào việc provider cụ thể tự reset hoặc giữ state sau một exception. Hãy gọi init với key/parameters đúng cho operation tiếp theo, hoặc tạo engine object mới. Với signature, cần xác định rõ khi nào gọi initSign/initVerify và không trộn dữ liệu giữa hai operation.

Đối với HSM/KMS provider, một lỗi network có thể làm trạng thái session không rõ ràng. Không tự tiếp tục dùng object cũ nếu provider yêu cầu tạo session mới hoặc đăng nhập lại.

## 17. Không suy luận lỗi chỉ từ exception message

Exception message có thể thay đổi theo JDK, provider, locale hoặc native library. Không viết logic dựa vào chuỗi message như "Invalid key" hay "Bad padding".

Hãy xử lý theo loại exception và operation:

| Exception | Ý nghĩa cần xem xét |
|---|---|
| NoSuchAlgorithmException | Runtime/provider không tìm thấy service/algorithm được yêu cầu. |
| NoSuchProviderException | Provider được chỉ định không có hoặc không được đăng ký. |
| InvalidKeyException | Key không hợp lệ hoặc không tương thích với operation/provider. |
| InvalidAlgorithmParameterException | Tham số không hợp lệ hoặc không được hỗ trợ. |
| UnrecoverableKeyException | Không thể lấy key entry, có thể do password hoặc backend. |
| BadPaddingException | Padding/authentication hoặc dữ liệu đầu vào không hợp lệ theo operation; không dùng message để phân biệt chắc chắn nguyên nhân. |
| AEADBadTagException | Xác thực AEAD thất bại, ví dụ tag không khớp. |
| ProviderException | Lỗi từ provider hoặc backend; cần xem cause và tài liệu vendor. |

Không bắt Exception rồi bỏ qua và không fallback sang thuật toán yếu. Log loại exception, operation, provider, key ID đã phân loại và correlation ID; không log password, plaintext hoặc key bytes.

## 18. Không biến lỗi provider thành fallback bảo mật yếu

Một anti-pattern là:

~~~java
try {
    return signWithHsm(data);
} catch (Exception e) {
    return signWithLocalPrivateKey(data);
}
~~~

Nếu policy yêu cầu private key luôn ở HSM, fallback trên làm thay đổi ranh giới bảo vệ và có thể đưa khóa ra ngoài mà không được phê duyệt.

Fallback chỉ hợp lệ khi kiến trúc đã xác định trước nhiều backend tương đương về security properties, quyền, thuật toán và audit. Cần ghi nhận backend được chọn, có health check và quy tắc fail-closed khi không đáp ứng điều kiện.

Đối với thao tác mã hóa, giải mã hoặc ký, retry cũng cần idempotency và kiểm soát trạng thái. Không retry vô hạn một operation có thể tiêu thụ quota hoặc tạo side effect ở KMS/HSM.

## 19. Không dựa vào alias hoặc default KeyStore type

Không nên dùng:

~~~java
KeyStore keyStore = KeyStore.getInstance(KeyStore.getDefaultType());
~~~

nếu ứng dụng cần định dạng hoặc backend cụ thể. Default type có thể phụ thuộc cấu hình JDK và môi trường. Hãy chọn type rõ ràng:

~~~java
KeyStore keyStore = KeyStore.getInstance("PKCS12");
~~~

Alias chỉ có ý nghĩa trong phạm vi một keystore/provider. Không dùng alias như định danh toàn cục cho key material. Inventory cần ghi store/provider, key ID, version, owner, purpose và certificate fingerprint nếu có.

Không giả định setKeyEntry, deleteEntry, load hoặc store có cùng semantics trên file PKCS#12, JKS và HSM/PKCS#11. Kiểm tra tài liệu provider, đặc biệt về mật khẩu entry, exportability, backup và persistence.

## 20. Không dựa vào default TLS configuration

Không coi SSLContext.getInstance("TLS") là cam kết rằng mọi protocol/cipher sẽ giống nhau giữa các JDK. Runtime có thể vô hiệu hóa protocol hoặc thuật toán cũ theo security properties; provider và trust store cũng có thể khác.

Ứng dụng cần:

- Xác định protocol tối thiểu/tối đa theo policy.
- Dùng KeyManager/TrustManager được cấu hình rõ ràng.
- Bật hostname verification cho client.
- Kiểm tra certificate chain, SAN, thời hạn và revocation policy.
- Không dùng trust-all manager hoặc tắt xác minh hostname.
- Kiểm tra cipher suites và signature schemes trên runtime mục tiêu.
- Kiểm thử handshake với các phiên bản client/server cần hỗ trợ.

Không dựa vào cipher suite mặc định hoặc thứ tự thương lượng quan sát được trên máy phát triển làm hợp đồng triển khai. TLS là giao thức có nhiều thành phần; không nhầm tên cipher suite với Cipher transformation của JCA.

## 21. Không dựa vào tên provider để tuyên bố FIPS

Provider có tên chứa "FIPS" hoặc tài liệu quảng bá tuân thủ không tự chứng minh ứng dụng đang hoạt động trong phạm vi chứng nhận.

Nếu có yêu cầu FIPS, phải xác minh:

- Cryptographic module và số chứng nhận cụ thể.
- Phiên bản module, binary, firmware và môi trường vận hành nằm trong phạm vi chứng nhận.
- Security policy và chế độ hoạt động được cấu hình đúng.
- Operation, thuật toán, key size và cách quản lý key nằm trong phạm vi được phép.
- Ứng dụng không fallback sang provider khác ngoài module được phê duyệt.
- Có bằng chứng vận hành và kiểm toán.

FIPS là thuộc tính của module trong cấu hình và môi trường xác định, không phải nhãn chung cho toàn bộ ứng dụng hoặc mọi thuật toán mà provider công bố.

## 22. Không dựa vào hành vi riêng khi serialize hoặc backup key

Không giả định file keystore có thể được di chuyển nguyên trạng giữa mọi JDK/provider/HSM. Một số file có thể phụ thuộc thuật toán PBE, MAC, provider-specific attribute hoặc phiên bản định dạng.

Khi cần portability:

1. Chọn định dạng chuẩn được các hệ thống đích hỗ trợ.
2. Kiểm tra key type, certificate chain, attributes và thuật toán bảo vệ.
3. Chỉ export private key khi policy cho phép.
4. Giữ metadata key ID/version và purpose độc lập với alias.
5. Kiểm thử import/restore trên đúng provider đích.
6. Xác minh bằng operation mật mã thực tế, không chỉ kiểm tra file mở được.

Với HSM non-exportable, dùng cơ chế backup/clone/restore chính thức của nhà cung cấp. Không tìm cách trích xuất vật liệu khóa để tạo bản backup "portable" nếu điều đó phá vỡ policy.

## 23. Ghi nhận contract của thuật toán và provider

Mỗi operation nhạy cảm nên có metadata đủ để tái hiện cấu hình và kiểm toán:

~~~yaml
operation: encrypt
engine: Cipher
transformation: AES/GCM/NoPadding
provider: ApprovedCryptoProvider
keyId: customer-data-kek-v3
keyPurpose: envelope-encryption
parameters:
  nonceLengthBytes: 12
  tagLengthBits: 128
serialization:
  formatVersion: 1
  textEncoding: UTF-8
~~~

Đây là metadata minh họa, không chứa key material hoặc secret. Giá trị thực tế phải được chọn theo provider, policy và protocol của hệ thống.

Audit event nên ghi principal, operation, provider/version, key ID/version, parameters quan trọng, thời điểm, kết quả và request ID. Không ghi password, private key bytes, DEK dạng rõ hoặc plaintext nhạy cảm.

## 24. Kiểm thử tương thích giữa JDK và provider

Một ma trận kiểm thử nên bao gồm các tổ hợp thực sự được hỗ trợ:

| Trục kiểm thử | Câu hỏi |
|---|---|
| JDK vendor/version | Runtime mục tiêu có cùng API và security properties không? |
| Provider/version | Service và alias cần dùng có tồn tại không? |
| Key source | Key tạo bởi provider này có dùng được ở provider kia không? |
| Algorithm/parameters | Transformation, curve, padding, nonce, tag và PSS/OAEP parameters có tương thích không? |
| Encoding | Certificate, key, signature và ciphertext có định dạng trao đổi thống nhất không? |
| Security policy | Thuật toán có bị disabled hoặc bị policy từ chối không? |
| Backend failure | HSM/KMS timeout, mất kết nối hoặc quota được xử lý ra sao? |
| Lifecycle | Rotation, old-key decrypt, backup/restore và destruction có hoạt động không? |

Kiểm thử nên có:

- Known-answer tests cho digest, MAC, cipher và signature.
- Negative tests với key sai, tag sai, padding sai và parameters không hợp lệ.
- Interoperability tests giữa producer và consumer dùng provider khác nhau.
- Regression tests sau khi nâng JDK/provider.
- Recovery tests với bản backup đã tạo ở phiên bản trước.
- Kiểm tra audit để chắc chắn operation đi qua backend được yêu cầu.

Không dùng khóa production hoặc dữ liệu khách hàng thật để chạy test vector. Dùng khóa thử, dữ liệu tổng hợp và môi trường được phê duyệt.

## 25. Quy trình nâng cấp JDK hoặc provider

Trước khi nâng cấp:

1. Lập danh sách engine class, algorithm name, provider, key type và parameters đang dùng.
2. Ghi nhận JDK/provider version và security properties hiện tại.
3. Kiểm tra release notes và thay đổi tương thích của nhà cung cấp.
4. Chạy bộ test trên runtime mới, gồm negative và interoperability cases.
5. Thử đọc keystore/backup cũ và xác minh operation với key version cần giữ.
6. Kiểm tra TLS handshake, certificate path và algorithm constraints.
7. Đánh giá latency/error behavior khi provider kết nối HSM/KMS.
8. Triển khai canary, quan sát audit và có kế hoạch rollback.
9. Chỉ loại bỏ runtime cũ khi đã xác minh dữ liệu và quy trình DR vẫn truy cập được.

Không thay provider hoặc JDK trực tiếp trên production chỉ vì môi trường thử nghiệm không báo lỗi. Cần có bằng chứng cho toàn bộ operation quan trọng và các đường khôi phục.

## 26. Ví dụ thực tế: ứng dụng chuyển từ software provider sang HSM

Một dịch vụ trước đây ký tài liệu bằng private key trong PKCS#12. Tổ chức chuyển sang HSM để private key không còn export được.

Các thay đổi cần xác định:

1. Chọn HSM provider và version được phê duyệt.
2. Tạo key pair mới bên trong HSM nếu yêu cầu bảo đảm khóa chưa từng rời thiết bị.
3. Cấp certificate mới cho public key mới.
4. Cập nhật alias/key ID và inventory.
5. Chỉ định provider HSM cho Signature operation.
6. Kiểm thử signature encoding và xác minh với các consumer hiện có.
7. Xác minh private key cũ chỉ còn được dùng cho dữ liệu/chữ ký lịch sử trong phạm vi được duyệt.
8. Định nghĩa hành vi khi HSM mất kết nối; không fallback sang file private key cũ để ký mới.
9. Diễn tập backup/restore HSM, rotation và destruction theo quy trình vendor.
10. Ghi audit provider, key ID/version, principal và operation.

Nếu ứng dụng trước đây dựa vào getEncoded() để export private key hoặc dựa vào provider mặc định, quá trình chuyển đổi sẽ làm lộ những phụ thuộc đó. Cần sửa contract trước khi chuyển backend.

## 27. Những lỗi thường gặp

- Dùng mặc định của provider mà không biết nó là gì.
- Dựa vào provider đứng đầu danh sách.
- Dùng alias riêng thay cho tên thuật toán chuẩn.
- Không ghi rõ mode, padding, nonce, IV, tag hoặc PSS/OAEP parameters.
- Dựa vào key size, curve hoặc SecureRandom default không được kiểm tra.
- Ép kiểu key object sang implementation class của vendor.
- Giả định mọi key đều export được qua getEncoded().
- Dựa vào định dạng byte nội bộ của chữ ký hoặc certificate.
- Dùng charset mặc định khi băm/ký dữ liệu text.
- Chia sẻ Cipher/Signature/Mac object giữa nhiều thread.
- Dựa vào state sau exception hoặc tự reset engine theo phỏng đoán.
- Phân loại lỗi bằng exception message.
- Fallback từ HSM sang software key khi backend lỗi.
- Coi provider hỗ trợ thuật toán là bằng chứng thuật toán được policy cho phép.
- Coi tên provider có chữ FIPS là bằng chứng tuân thủ.
- Không kiểm thử tương thích sau khi nâng JDK/provider.

## 28. Checklist tránh phụ thuộc behavior không chuẩn

Trước khi phát hành một ứng dụng mật mã, hãy xác nhận:

- [ ] Đã phân biệt behavior được đặc tả, extension được tài liệu hóa và behavior phụ thuộc implementation.
- [ ] Đã chọn tên engine/service và algorithm chuẩn.
- [ ] Provider bắt buộc được chỉ định hoặc danh sách provider cho phép được quản trị rõ.
- [ ] Không phụ thuộc vào thứ tự provider tình cờ hoặc alias riêng không được ghi nhận.
- [ ] Cipher transformation và mọi tham số quan trọng được chỉ định rõ.
- [ ] Key size, curve, PSS/OAEP, nonce, IV và tag length phù hợp policy.
- [ ] Không dựa vào default charset hoặc serialization không canonical.
- [ ] Không giả định key object exportable hoặc dùng được với mọi provider.
- [ ] Engine object được quản lý state và concurrency theo tài liệu.
- [ ] Exception được xử lý theo loại và operation, không theo message.
- [ ] Không có fallback làm thay đổi ranh giới bảo vệ khóa ngoài policy.
- [ ] TLS hostname, chain, protocol và algorithm constraints được xác minh.
- [ ] FIPS/compliance được kiểm tra theo module và cấu hình cụ thể.
- [ ] Keystore, backup và key version được kiểm thử trên runtime đích.
- [ ] Có interoperability, negative, regression và recovery tests.
- [ ] Audit ghi provider/version, key ID/version, principal và operation.

Không phụ thuộc behavior không chuẩn là cách giữ cho ứng dụng Java có hợp đồng mật mã rõ ràng qua các lần nâng cấp và thay đổi backend. Hãy dùng API và tên thuật toán được đặc tả, chỉ rõ tham số quan trọng, quản lý provider có chủ đích và kiểm thử trên đúng môi trường. Khi một extension riêng là bắt buộc, ghi nhận nó như một phụ thuộc được quản trị cùng phiên bản, policy, kiểm thử và kế hoạch phục hồi.
