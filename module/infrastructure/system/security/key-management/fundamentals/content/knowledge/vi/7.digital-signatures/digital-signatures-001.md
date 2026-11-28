# Digital signature – Chữ ký số và xác minh tính xác thực dữ liệu

**Digital signature (chữ ký số)** là một cơ chế mật mã bất đối xứng cho phép bên nắm giữ **private key (khóa bí mật)** tạo ra chữ ký trên một thông điệp. Bên nhận dùng **public key (khóa công khai)** tương ứng để kiểm tra chữ ký. Khi thuật toán được sử dụng đúng, chữ ký hợp lệ là bằng chứng mật mã rằng dữ liệu được xác minh khớp với dữ liệu đã ký và chữ ký được tạo bằng private key tương ứng với public key đang dùng để xác minh.

Trong chương **Chữ ký số** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chủ đề này liên kết với **cặp khóa bất đối xứng, hàm băm, mật mã đối xứng, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán**. Để chữ ký số có ý nghĩa trong một hệ thống thực, cần quản lý toàn bộ vòng đời khóa: **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy**, đồng thời xác thực nguồn public key và danh tính người hoặc dịch vụ ký.

> **Nhớ ngay:** Chữ ký số bảo vệ **tính toàn vẹn** và cung cấp bằng chứng về **khóa đã ký**. Nó **không tự mã hóa nội dung, không tự chứng minh danh tính ngoài đời thực, không tự cấp quyền nghiệp vụ và không tự chống phát lại (replay)**.

## 1. Chữ ký số hoạt động thế nào?

Một quy trình chữ ký số có hai phía: **signer** (bên ký) và **verifier** (bên xác minh).

1. **Sinh hoặc cấp phát key pair** theo thuật toán đã chọn, chẳng hạn Ed25519, ECDSA hoặc RSA-PSS. Private key được bảo vệ; public key được cung cấp qua nguồn đáng tin cậy.
2. **Chuẩn bị đúng bytes cần ký**: thông điệp, định dạng dữ liệu, phiên bản giao thức và các thông tin ngữ cảnh cần thiết phải có cách biểu diễn nhất quán.
3. **Ký (sign)**: signer sử dụng private key và thuật toán chữ ký đã xác định để tạo **signature**.
4. **Gửi hoặc lưu**: bên nhận có thông điệp, chữ ký, thông tin thuật toán và mã định danh khóa cần thiết.
5. **Xác minh (verify)**: verifier lấy public key từ nguồn đã xác thực, kiểm tra chính sách thuật toán và xác minh chữ ký trên **đúng bytes** của thông điệp.
6. **Kiểm tra nghiệp vụ**: nếu chữ ký hợp lệ, hệ thống vẫn phải kiểm tra quyền của người ký, thời hạn, người nhận, định danh sự kiện và quy tắc chống replay trước khi thực hiện hành động.

~~~mermaid
flowchart LR
    M["Thông điệp và ngữ cảnh đã chuẩn hóa"] --> S["Sign với private key"]
    SK["Private key: chỉ chủ thể ký kiểm soát"] --> S
    S --> ENV["Thông điệp + chữ ký + key ID"]
    ENV --> V["Verify với public key đáng tin"]
    PK["Public key: nguồn đã được xác thực"] --> V
    V --> R{"Chữ ký hợp lệ?"}
    R -->|Không| NO["Từ chối"]
    R -->|Có| POLICY["Kiểm tra thời hạn, quyền và chống replay"]
    POLICY --> ACCEPT["Chấp nhận theo chính sách"]
~~~

**Ví dụ:** Payment Service ký một sự kiện thanh toán; Ledger Service dùng public key của Payment Service để kiểm tra chữ ký trước khi ghi sổ. Nếu số tiền trong sự kiện bị sửa mà chữ ký không được tạo lại bằng private key hợp lệ, việc xác minh phải thất bại.

### 1.1. Ký chính xác thứ gì?

Ở mức khái niệm, có thể hình dung:

~~~text
signature = Sign(privateKey, bytesToSign)
valid     = Verify(publicKey, bytesToSign, signature)
~~~

Tuy nhiên, **không phải mọi thuật toán đều yêu cầu ứng dụng tự băm bytesToSign trước khi gọi Sign**:

- **RSA-PSS** và **ECDSA** phối hợp thuật toán chữ ký với hàm băm theo tham số hoặc giao diện thư viện.
- **Ed25519** theo giao diện thông dụng ký trên thông điệp bytes; thuật toán thực hiện các bước băm cần thiết bên trong.
- **Ed25519ph** là một biến thể prehash riêng, có quy tắc khác với Ed25519 thuần và không được thay thế bằng thao tác băm tùy ý.

Do đó, ứng dụng phải dùng **đúng API và tham số của thuật toán/giao thức**, tránh tự lặp bước băm, dùng nhầm hàm băm hoặc ký một biểu diễn khác với biểu diễn mà bên nhận sẽ xác minh.

## 2. Những thuộc tính mà chữ ký số có thể và không thể cung cấp

| Thuộc tính | Chữ ký số hỗ trợ thế nào? | Điều kiện hoặc giới hạn |
| --- | --- | --- |
| **Toàn vẹn (integrity)** | Phát hiện dữ liệu được xác minh khác dữ liệu đã ký. | Phải ký đủ các trường quan trọng và xác minh đúng bytes. |
| **Xác thực nguồn ký** | Chứng minh chữ ký khớp với public key tương ứng. | Public key phải được gắn với đúng danh tính/chủ thể qua cơ chế tin cậy. |
| **Bằng chứng ký / chống chối bỏ** | Có thể là một thành phần bằng chứng về hành động ký. | Còn phụ thuộc quyền kiểm soát khóa, thời điểm, chứng chỉ, kiểm toán và khuôn khổ pháp lý; không có bảo đảm tuyệt đối chỉ từ thuật toán. |
| **Bảo mật nội dung (confidentiality)** | **Không cung cấp.** | Cần mã hóa riêng, ví dụ AES-GCM hoặc envelope encryption. |
| **Phân quyền (authorization)** | **Không tự cung cấp.** | Verifier phải kiểm tra signer có quyền thực hiện hành động đang yêu cầu. |
| **Chống replay** | **Không tự cung cấp.** | Cần event ID, nonce nghiệp vụ, thời hạn, sequence number hoặc trạng thái chống xử lý trùng. |
| **Bảo đảm thời gian ký** | **Không tự cung cấp.** | Timestamp tự khai báo có thể bị giả; cần nguồn thời gian hoặc cơ chế đóng dấu thời gian đáng tin khi có yêu cầu. |

Chữ ký chỉ xác minh **mối quan hệ giữa dữ liệu, chữ ký và public key**. Nếu kẻ tấn công thay public key đáng tin bằng public key do chính họ tạo, họ có thể ký dữ liệu giả và làm verifier trả về kết quả hợp lệ. Vì vậy việc xác minh **nguồn public key** quan trọng không kém phép toán Verify.

### 2.1. Phân biệt chữ ký số, MAC và mã hóa

| Cơ chế | Khóa sử dụng | Bên xác minh | Tác dụng chính |
| --- | --- | --- | --- |
| **Digital signature** | Private key để ký, public key để xác minh. | Bất kỳ bên nào có public key đã xác thực và quyền kiểm tra. | Toàn vẹn và xác thực theo chủ thể nắm private key. |
| **HMAC/KMAC** | Một khóa đối xứng bí mật được chia sẻ. | Bên cùng biết khóa bí mật. | Toàn vẹn và xác thực giữa các bên cùng biết khóa. |
| **AES-GCM** | Một khóa AES đối xứng. | Bên biết khóa AES để giải mã và kiểm tra tag. | Bảo mật và toàn vẹn bản mã. |
| **Envelope encryption** | DEK mã hóa dữ liệu; KEK/cơ chế khác bảo vệ DEK. | Thành phần có quyền giải bọc và giải mã. | Bảo vệ bí mật dữ liệu và vòng đời khóa dữ liệu. |

MAC không tạo bằng chứng công khai phân biệt được hai bên cùng nắm khóa bí mật: về mặt kỹ thuật, mỗi bên đều có khả năng tạo MAC hợp lệ. Chữ ký số tách **quyền ký** khỏi **khả năng xác minh**, nên phù hợp cho cập nhật phần mềm, tài liệu, sự kiện liên dịch vụ và những hệ thống nhiều bên xác minh.

## 3. Các thuật toán chữ ký số phổ biến

| Thuật toán | Đặc điểm | Lưu ý vận hành |
| --- | --- | --- |
| **RSA-PSS** | Chữ ký dựa trên RSA với xác suất hóa PSS; chuẩn hóa trong các giao thức tương ứng. | Cần chọn hash, MGF1, salt length và kích thước khóa nhất quán; không dùng RSA thô. |
| **RSA PKCS#1 v1.5 signature** | Cơ chế chữ ký RSA cũ, còn gặp trong hệ thống tương thích. | Khi thiết kế mới thường ưu tiên RSA-PSS nếu giao thức hỗ trợ; không lẫn định dạng chữ ký với RSA-PSS. |
| **ECDSA**, ví dụ P-256 | Chữ ký trên đường cong elliptic, thường có chữ ký và public key nhỏ hơn RSA. | Nonce của **mỗi chữ ký** phải được sinh đúng; tái dùng hoặc rò rỉ nonce có thể làm lộ private key. |
| **Ed25519** | Thuật toán chữ ký EdDSA với tham số xác định, giao diện ký đơn giản. | Dùng để **ký/xác minh**, không dùng trực tiếp để mã hóa hoặc thỏa thuận khóa. |
| **Ed448** | Thuật toán EdDSA trên đường cong khác, có các ràng buộc riêng. | Cần kiểm tra khả năng hỗ trợ của thư viện, KMS/HSM và giao thức. |
| **ML-DSA** | Thuật toán chữ ký số hậu lượng tử được NIST chuẩn hóa trong FIPS 204. | Chỉ dùng khi hệ thống hỗ trợ định dạng, tham số và giao thức tương ứng; không mặc định có API Java 17. |

**Thuật toán chữ ký là một lựa chọn khác với thuật toán tạo khóa mã hóa.** X25519 là thuật toán thỏa thuận khóa, **không phải** thuật toán ký. RSA-OAEP dùng để mã hóa bất đối xứng, còn RSA-PSS dùng để ký. Cùng họ toán học không có nghĩa các API hay định dạng chữ ký có thể hoán đổi cho nhau.

### 3.1. Hash trong chữ ký số

Hàm băm như **SHA-256, SHA-384 hoặc SHA-3** thường góp phần vào thuật toán chữ ký. Hash giúp thuật toán xử lý thông điệp có độ dài tùy ý mà không cần đưa mọi byte trực tiếp vào phép toán khóa công khai ở mức toán học.

**Digest công khai không phải chữ ký.** Nếu ứng dụng gửi thông điệp cùng SHA-256(message), kẻ tấn công có thể thay thông điệp rồi tự tính lại digest. Một chữ ký được tạo bằng private key hợp lệ mới cung cấp tính xác thực của phép ký theo public key đã chọn.

Khi chọn hash, cần tuân thủ **cặp thuật toán/hàm băm được phép theo giao thức**. Không tự gán SHA3-256 cho một API Ed25519 thuần hoặc đổi thuật toán mà không thay đổi quy tắc ký/xác minh ở hai đầu.

### 3.2. ECDSA nonce và lỗi nghiêm trọng

ECDSA cần một giá trị bí mật dùng cho **mỗi lần ký**. Nếu hai chữ ký sử dụng nonce không an toàn, đặc biệt là trùng nonce theo điều kiện tấn công, private key có thể bị suy ra. Có thể sử dụng cơ chế sinh nonce xác định theo chuẩn như RFC 6979 khi giao thức/provider hỗ trợ; cách này không có nghĩa dùng seed cố định tùy ý hoặc tự triển khai thuật toán.

Ed25519 dùng cơ chế sinh chữ ký xác định theo thiết kế chuẩn đối với cùng private key và thông điệp, nhưng vẫn cần bảo vệ private key và tránh cách dùng không đúng biến thể hoặc giao thức.

## 4. Chuẩn hóa dữ liệu và ràng buộc ngữ cảnh trước khi ký

Một chữ ký có thể hợp lệ về mật mã nhưng vô nghĩa với nghiệp vụ nếu **bytes được ký không bao gồm đầy đủ điều kiện cần xác nhận**. Ví dụ ký số tiền mà không ký đơn vị tiền tệ, tenant ID hay transaction ID có thể mở đường cho việc chuyển chữ ký sang ngữ cảnh khác.

Một signed message thường cần các trường:

- **Protocol/version:** xác định định dạng và ngữ nghĩa dữ liệu.
- **Purpose/domain:** phân biệt sự kiện thanh toán, xác nhận đăng nhập, yêu cầu cấp quyền hoặc cập nhật phần mềm.
- **Actor/issuer:** chủ thể phát hành đã được xác thực.
- **Audience:** hệ thống/người nhận dự kiến.
- **Object ID/transaction ID:** đối tượng hoặc giao dịch được ký.
- **Issued-at/expiry và event ID:** hỗ trợ kiểm tra thời hạn, chống replay.
- **Payload có ý nghĩa nghiệp vụ:** gồm các trường mà verifier sẽ sử dụng để đưa ra quyết định.

Chữ ký cần được tính trên **một biểu diễn byte rõ ràng, không mơ hồ**. Với JSON, thứ tự trường, encoding chuỗi, số thập phân, Unicode, giá trị null và khoảng trắng có thể khác giữa hai hệ thống dù ý nghĩa nhìn có vẻ giống nhau. Nên dùng một giao thức chuẩn có quy tắc canonicalization/encoding rõ hoặc ký trực tiếp bytes đã truyền theo quy ước nhất quán.

~~~text
signatureInput = canonicalEncode(
    protocolVersion,
    purpose,
    issuer,
    audience,
    issuedAt,
    expiresAt,
    eventId,
    payload
)

signature = Sign(privateKey, signatureInput)
~~~

Đây chỉ là **giả mã mô tả dữ liệu cần ký**; định dạng thật phải được giao thức định nghĩa và thử nghiệm liên thông. Không tự nối chuỗi các trường với dấu phân cách tùy tiện nếu giá trị trường cũng có thể chứa dấu đó.

**Chống tấn công dùng lại chữ ký ở mục đích khác (cross-protocol replay):** thêm thông tin mục đích và phiên bản đã được định nghĩa rõ vào dữ liệu ký; verifier chỉ chấp nhận chữ ký ở đúng giao thức và ngữ cảnh. Tương tự, key ID giúp chọn khóa chứ không tự xác nhận khóa thuộc ai.

## 5. Quy trình xác minh chữ ký ở hệ thống sản xuất

Một verifier an toàn phải thực hiện **nhiều bước hơn phép gọi verify()**:

1. **Xác định giao thức đã cho phép** và cấu hình thuật toán ở phía máy chủ. Không tự động tin giá trị thuật toán do dữ liệu đầu vào tuyên bố, đặc biệt trong JWT/JWS.
2. **Lấy public key từ nguồn tin cậy**: chứng chỉ hợp lệ, JWKS tại địa chỉ đã cấu hình, kho khóa đã đăng ký hoặc fingerprint đã xác minh. Chỉ dùng key ID để chọn trong tập khóa đã tin.
3. **Kiểm tra metadata khóa**: thuật toán, key usage, phiên bản, tenant, issuer, thời hạn hoặc trạng thái thu hồi theo loại hệ thống.
4. **Tái tạo đúng bytes đã ký** theo định dạng đã thống nhất. Sai một byte có thể làm chữ ký không hợp lệ.
5. **Verify cryptographic signature** bằng thuật toán và public key phù hợp. Từ chối lỗi định dạng, chữ ký sai hoặc thuật toán không hỗ trợ.
6. **Kiểm tra quyền nghiệp vụ**: issuer có được ký loại hành động này không, audience có đúng bên nhận không, người gọi có quyền với object/tenant đó không.
7. **Kiểm tra thời hạn và replay**: giới hạn issued-at, expiry, event ID/nonce/sequence number và trạng thái đã xử lý theo mô hình dữ liệu.
8. **Ghi audit và xử lý lỗi an toàn**: ghi key ID, kết quả, nguyên nhân từ chối ở mức phù hợp, không log private key hay dữ liệu nhạy cảm không cần thiết.

### 5.1. Public key, chứng chỉ X.509 và JWKS

**Public key là dữ liệu công khai; quan hệ giữa public key và danh tính không tự được bảo đảm.** Một số cách gắn khóa vào danh tính:

- **Chứng chỉ X.509/PKI:** verifier kiểm tra chuỗi chứng chỉ, chủ thể/tên, thời hạn, key usage, trust anchor và trạng thái thu hồi theo chính sách và ứng dụng.
- **JWKS:** dịch vụ danh tính công bố tập public key cho việc xác minh JWT/JWS; bên nhận phải ghim **issuer, nguồn JWKS tin cậy, thuật toán được phép và audience**.
- **Fingerprint:** đối chiếu giá trị băm của encoding khóa với giá trị nhận qua một kênh độc lập tin cậy.
- **Registry nội bộ:** bản ghi gắn key ID và public key với workload, môi trường và tenant sau một quy trình đăng ký, xác thực và kiểm toán.

**kid chỉ là mã định danh chọn khóa**. Nếu một token tự cung cấp đường dẫn tải khóa, verifier không được tùy tiện làm theo mà bỏ qua ranh giới tin cậy. Một public key bị thay thế trái phép vẫn có thể xác minh được chữ ký do kẻ tấn công tự tạo.

### 5.2. Cửa sổ tin cậy và chữ ký lịch sử

Việc một chứng chỉ đã hết hạn hoặc bị thu hồi có thể ảnh hưởng đến cách một hệ thống đánh giá **thời điểm và hiệu lực** của chữ ký. Đối với quy trình yêu cầu **xác minh lâu dài (long-term validation)**, có thể phải lưu chứng chỉ, trạng thái thu hồi, bằng chứng thời gian và các bằng chứng xác nhận khác theo chuẩn/chính sách áp dụng.

Không suy luận rằng hủy private key sẽ khiến tất cả chữ ký từng tạo từ khóa đó tự trở thành sai về mặt toán học. Chữ ký cũ vẫn có thể xác minh với public key, nhưng **có được chấp nhận về mặt nghiệp vụ/pháp lý hay không** phụ thuộc vào chính sách, tình trạng khóa ở thời điểm ký và bằng chứng kèm theo.

## 6. Ví dụ Java 17+: ký và xác minh bằng Ed25519

Ví dụ dưới đây sử dụng **Java Cryptography Architecture (JCA)** với **Ed25519**, một thuật toán chữ ký số có API tương đối gọn. Đoạn mã minh họa sinh key pair trong bộ nhớ, ký bytes UTF-8, xác minh và phát hiện thông điệp bị sửa. Không in hoặc xuất private key.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;
import java.util.Base64;

public class DigitalSignatureDemo {
    public static void main(String[] args) throws Exception {
        // Demo: sinh cặp khóa ký Ed25519 trong bộ nhớ.
        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair pair = generator.generateKeyPair();

        // Trong sản xuất, dùng format/canonicalization có quy tắc rõ.
        byte[] signedMessage = (
                "v1|payment-event|issuer=payment-service|" +
                "event=evt-123|amount=4200|currency=VND"
        ).getBytes(StandardCharsets.UTF_8);

        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(pair.getPrivate());
        signer.update(signedMessage);
        byte[] signature = signer.sign();

        // Public key phải được đăng ký và phân phối qua nguồn tin cậy.
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(pair.getPublic());
        verifier.update(signedMessage);
        boolean valid = verifier.verify(signature);

        byte[] tamperedMessage = (
                "v1|payment-event|issuer=payment-service|" +
                "event=evt-123|amount=9900|currency=VND"
        ).getBytes(StandardCharsets.UTF_8);

        Signature changedVerifier = Signature.getInstance("Ed25519");
        changedVerifier.initVerify(pair.getPublic());
        changedVerifier.update(tamperedMessage);
        boolean tamperedValid = changedVerifier.verify(signature);

        System.out.println("Signature (Base64): " +
                Base64.getEncoder().encodeToString(signature));
        System.out.println("Original valid: " + valid);        // true
        System.out.println("Modified valid: " + tamperedValid); // false
    }
}
~~~

**Ý nghĩa:** Chữ ký kiểm tra được rằng **đúng bytes đã ký** được xác minh bằng public key tương ứng. Thay số tiền nhưng dùng chữ ký cũ làm xác minh thất bại. Tuy nhiên, ví dụ **chưa xác nhận danh tính payment-service, quyền ký thanh toán, thời hạn sự kiện hay chống replay**: đó là công việc của giao thức và ứng dụng thực tế.

**Lưu ý về định dạng:** chuỗi ký nối bằng dấu phân cách trong demo chỉ phục vụ học thuật vì các giá trị đều được kiểm soát. Không áp dụng cách nối thô đó khi các trường có thể chứa ký tự phân cách; dùng canonical serialization hoặc một định dạng có prefix độ dài và kiểm tra kiểu dữ liệu.

Trong hệ thống production, private key nên nằm trong **KMS/HSM** nếu yêu cầu bảo mật và thuật toán được hỗ trợ; ứng dụng gọi API **Sign** theo key ID và quyền được cấp, sau đó công bố public key đã xác thực. Không log private key, seed tạo khóa hoặc nội dung nhạy cảm.

## 7. KMS/HSM bảo vệ khóa ký như thế nào?

**KMS (Key Management Service)** quản lý việc tạo, định danh, cấp quyền, sử dụng và thay đổi vòng đời khóa. **HSM (Hardware Security Module)** là phần cứng chuyên dụng bảo vệ key material trong ranh giới an toàn và có thể thực hiện thao tác ký; một số dịch vụ KMS sử dụng HSM phía sau.

Một thiết kế thường gặp:

~~~mermaid
flowchart TD
    APP["Payment Service: đã xác thực workload"] --> POLICY["Kiểm tra quyền Sign cho key ID S1"]
    POLICY --> KMS["KMS/HSM ký bằng private key S1"]
    KMS --> SIG["Trả chữ ký, không xuất private key"]
    PUB["Public key S1 được phân phối qua kênh tin cậy"] --> VERIFIER["Ledger Service xác minh chữ ký"]
    SIG --> VERIFIER
    EVENT["Thông điệp đầy đủ đã ký"] --> VERIFIER
    VERIFIER --> GATE["Kiểm tra quyền, thời hạn, replay và nghiệp vụ"]
~~~

Ưu điểm là giảm nhu cầu sao chép private key vào các container, file cấu hình và bộ nhớ ứng dụng. Nếu provider hỗ trợ, private key có thể được đánh dấu **non-exportable**. Nhưng **không xuất được khóa không đồng nghĩa không thể lạm dụng khóa**: dịch vụ bị chiếm quyền gọi Sign có thể tạo chữ ký trái phép dù không nhìn thấy bytes của khóa.

Áp dụng:

- **Least privilege:** mỗi workload chỉ được ký bằng key ID cần thiết, đúng môi trường và chức năng.
- **Separation of duties:** tách quyền tạo/xóa/cấp quyền khóa khỏi quyền gọi Sign nếu chính sách yêu cầu.
- **Key usage:** gắn rõ SIGN/VERIFY; không tự coi khóa chữ ký có thể dùng để giải mã hoặc trao đổi khóa.
- **Kiểm toán:** ghi actor, key ID, phiên bản, thuật toán, số lượt Sign, thời điểm, kết quả và cảnh báo bất thường.
- **Chính sách tần suất và phê duyệt:** với chức năng nhạy cảm, có thể cần rate limit, giới hạn giao dịch và kiểm soát nghiệp vụ trước khi gửi dữ liệu để ký.

Không mặc định mọi KMS/HSM hỗ trợ cùng một thuật toán như Ed25519, ECDSA, RSA-PSS hay ML-DSA. Khả năng API, kiểu key material, định dạng chữ ký và chính sách xuất khóa thay đổi theo sản phẩm.

## 8. Vòng đời khóa ký số

| Giai đoạn | Hoạt động cần thực hiện | Rủi ro khi quản lý sai |
| --- | --- | --- |
| **Tạo (generation)** | Sinh key pair bằng CSPRNG/provider đáng tin; chọn thuật toán, tham số, purpose, chính sách. | Private key yếu hoặc sai mục đích. |
| **Cấp phát / công bố** | Gắn owner, key ID, phiên bản, chứng chỉ hoặc kênh phân phối public key tin cậy. | Verifier dùng nhầm khóa hoặc public key giả. |
| **Lưu trữ** | Bảo vệ private key bằng HSM/KMS/kho bí mật; hạn chế xuất, backup và bản sao. | Lộ private key từ Git, file, log, dump hay backup. |
| **Sử dụng** | Chỉ cho phép actor hợp lệ gọi Sign; bên nhận kiểm tra chữ ký, trust và quyền nghiệp vụ. | Ký trái phép hoặc chấp nhận thông điệp sai. |
| **Xoay vòng (rotation)** | Sinh cặp mới, công bố public key mới, chuyển signer sang phiên bản mới, hỗ trợ xác minh chữ ký lịch sử có thời hạn. | Chữ ký mới không được nhận hoặc khóa cũ còn được tin quá lâu. |
| **Thu hồi / vô hiệu hóa** | Ngừng ký bằng private key rủi ro; cập nhật tập public key tin cậy, trạng thái chứng chỉ và chính sách. | Khóa lộ vẫn dùng để ký/chấp nhận chữ ký giả. |
| **Hủy (destruction)** | Hủy private key và bản sao sau khi kiểm tra nhu cầu lưu giữ, bằng chứng và phương án khôi phục. | Khóa tồn dư hoặc mất khả năng thực hiện nghĩa vụ còn cần private key. |

### 8.1. Xoay cặp khóa S1 sang S2

Một chuỗi chuyển tiếp an toàn có thể gồm:

1. Tạo **S2** trong KMS/HSM, gắn key ID mới và xác nhận quyền Sign.
2. Công bố **public key S2** trước cho mọi verifier qua nguồn tin cậy.
3. Chuyển ứng dụng ký mới bằng **private key S2**; ghi metadata key ID/phiên bản trong signed message.
4. Cho phép xác minh chữ ký **S1** trong cửa sổ cần thiết theo chính sách, ví dụ cho các sự kiện chưa hết hạn hoặc bản ghi lịch sử.
5. Đối soát các consumer, cache JWKS/chứng chỉ, backlog sự kiện và bản sao dự phòng.
6. Ngừng quyền ký mới bằng **S1**, sau đó thu hồi/hủy private key theo điều kiện lưu giữ và phương án ứng phó sự cố.

**Khi private key S1 bị lộ**, phải ưu tiên vô hiệu hóa quyền ký, điều tra chữ ký có khả năng bị giả mạo, cập nhật trạng thái tin cậy và kiểm soát các sự kiện cũ. Cửa sổ chấp nhận khóa cũ có thể cần rút ngắn dù gây gián đoạn; chỉ chuyển signer sang S2 mà vẫn chấp nhận vô hạn S1 là chưa đủ.

**Chữ ký lịch sử:** Với bài toán cần lưu bằng chứng lâu dài, không đơn giản xóa mọi thông tin liên quan đến S1. Có thể cần giữ public key, chứng chỉ, dấu thời gian và chứng cứ thu hồi; **không cần giữ private key để thực hiện phép xác minh chữ ký cũ về mặt toán học**.

### 8.2. Liên hệ với envelope encryption và khóa giải mã

Khóa **ký** và khóa **giải mã** có yêu cầu vòng đời khác nhau. Với envelope encryption, dữ liệu được mã hóa bằng **DEK đối xứng** (ví dụ AES-GCM) và DEK được bảo vệ bởi **KEK**, có thể được quản lý trong KMS/HSM. Chữ ký số có thể ký manifest hay metadata của gói dữ liệu để xác minh người phát hành, nhưng **chữ ký không thay thế mã hóa**.

Nếu một private key dùng giải mã bị hủy quá sớm, bản mã cũ có thể không khôi phục được. Với khóa ký, public key đáng tin thường đủ để xác minh những chữ ký lịch sử. Do đó, **không dùng một chính sách hủy giống nhau cho mọi key pair** mà bỏ qua công dụng và dữ liệu phụ thuộc.

## 9. Thiết kế ví dụ: sự kiện thanh toán có chữ ký

Giả sử Payment Service công bố sự kiện cho Ledger Service, trong đó một sự kiện gồm **transaction ID, tenant ID, amount, currency, timestamp và event ID**.

**Phía phát hành:**

1. Payment Service tạo sự kiện bằng định dạng đã xác định, kiểm tra các trường nghiệp vụ rồi chuẩn hóa bytes.
2. Chọn **key ID S2** đang hoạt động; KMS/HSM kiểm tra workload có quyền Sign.
3. Ký trên cả **payload và ngữ cảnh giao thức** (loại sự kiện, issuer, audience, phiên bản, expiry).
4. Gửi thông điệp, chữ ký, key ID và metadata theo định dạng liên thông đã thống nhất.

**Phía tiếp nhận:**

1. Ledger Service kiểm tra kết nối/định danh người gọi theo chính sách và lấy public key S2 từ nguồn tin cậy.
2. Kiểm tra thuật toán được ghim cho S2, dạng dữ liệu, chữ ký và key usage.
3. Kiểm tra **tenant**, quyền phát hành giao dịch, transaction ID, amount/currency, thời hạn và event ID chưa xử lý.
4. Chỉ sau khi đủ điều kiện mới ghi sổ; event ID giúp xử lý **idempotency/replay** một cách nhất quán.
5. Ghi audit: key ID, issuer, loại sự kiện, thời gian, kết quả xác minh và kết quả nghiệp vụ; không ghi private key.

**Tình huống tấn công A:** Kẻ tấn công lấy được public key S2 nhưng không có private key, rồi thay amount. Chữ ký cũ không còn hợp lệ trên message đã bị sửa.

**Tình huống tấn công B:** Kẻ tấn công gửi lại nguyên một sự kiện hợp lệ đã ký. Verify vẫn có thể trả về true; kiểm tra event ID và quy tắc xử lý trùng mới ngăn ghi sổ lần nữa.

**Tình huống tấn công C:** Kẻ tấn công có quyền gọi API Sign dù không thể xuất private key từ HSM. Họ vẫn có thể ký giao dịch trái phép nếu quy tắc phân quyền trước khi ký không đủ chặt. Cần kiểm soát workload và phê duyệt nghiệp vụ, giám sát hành vi bất thường và phản ứng khi danh tính bị chiếm đoạt.

## 10. Các lỗi thường gặp và cách phòng tránh

| Sai lầm | Hậu quả | Biện pháp |
| --- | --- | --- |
| Chỉ băm thông điệp rồi gọi đó là chữ ký | Kẻ tấn công có thể sửa thông điệp và tính digest mới. | Dùng thuật toán chữ ký số với private/public key đúng chuẩn. |
| Dùng public key từ nguồn tùy ý | Chấp nhận chữ ký do kẻ tấn công tự tạo dưới khóa giả. | Xác thực CA/chứng chỉ, JWKS đã ghim hoặc fingerprint tin cậy. |
| Tin thuật toán trong token mà không áp chính sách | Có thể gặp lỗi nhầm thuật toán hoặc chấp nhận cơ chế không được phép. | Ghim thuật toán theo issuer, key ID và loại token. |
| Chỉ ký một phần payload | Những trường không được ký có thể bị sửa và làm thay đổi nghiệp vụ. | Ký đầy đủ các trường quyết định và ngữ cảnh liên quan. |
| Nối chuỗi dữ liệu không theo canonical format | Hai hệ thống ký và kiểm tra bytes khác nhau hoặc có biểu diễn mơ hồ. | Dùng định dạng chuẩn, version và test vector liên thông. |
| Bỏ qua replay | Sự kiện cũ có chữ ký hợp lệ được xử lý lại. | Kiểm tra thời hạn, nonce/event ID và idempotency. |
| Lưu private key trong mã nguồn, image hoặc log | Mất khả năng kiểm soát ai có thể ký. | KMS/HSM hoặc kho bí mật được phân quyền, theo dõi rò rỉ. |
| Mở quyền Sign rộng dù private key non-exportable | Workload bị chiếm đoạt vẫn có thể tạo chữ ký giả mạo. | Least privilege, phân tách nhiệm vụ, audit và cảnh báo. |
| Tái dùng hoặc để lộ nonce ECDSA | Có thể làm lộ private key. | Dùng provider đúng chuẩn, nonce an toàn hoặc deterministic ECDSA chuẩn. |
| Xoay khóa nhưng gỡ public key cũ quá sớm | Verifier không thể kiểm tra thông điệp còn hiệu lực. | Quản lý phiên bản và cửa sổ chuyển tiếp có kiểm soát. |
| Tiếp tục tin khóa ký đã lộ quá lâu | Có thể chấp nhận chữ ký giả mạo. | Xử lý sự cố, thu hồi/vô hiệu hóa và đánh giá chữ ký trong thời gian bị ảnh hưởng. |
| Coi chữ ký hợp lệ là giấy phép thực hiện mọi hành động | Bỏ qua phân quyền tenant hoặc giới hạn nghiệp vụ. | Tách Verify khỏi Authorization và kiểm tra nghiệp vụ. |
| Coi chữ ký số là mã hóa dữ liệu | Dữ liệu nhạy cảm vẫn bị đọc được. | Kết hợp mã hóa xác thực hoặc envelope encryption khi cần bí mật. |
| Không lưu chứng cứ thời gian/trạng thái chứng chỉ khi cần | Khó đánh giá giá trị chữ ký lịch sử theo chính sách. | Lập kế hoạch lưu bằng chứng, chứng chỉ và kiểm tra thu hồi/timestamp. |

## 11. Câu hỏi tự kiểm tra

1. Khi một chữ ký Ed25519 hợp lệ, điều đó chứng minh gì về **bytes** và **public key**? Điều gì vẫn cần xác minh về danh tính?
2. Vì sao chữ ký số **không che giấu** nội dung message?
3. Chữ ký số khác HMAC như thế nào về khả năng xác minh công khai và chia sẻ secret?
4. Vì sao không được chọn thuật toán Verify trực tiếp theo giá trị không tin cậy trong token?
5. Nếu hai hệ thống tuần tự hóa cùng một JSON khác thứ tự trường, chữ ký có thể thất bại dù giá trị nghiệp vụ giống nhau không?
6. Tại sao **key ID/kid** không đủ để chứng minh public key đáng tin?
7. Một sự kiện ký hợp lệ bị gửi lại sau một giờ có luôn được phép xử lý tiếp không?
8. Vì sao **non-exportable private key** vẫn có thể bị lạm dụng nếu quyền gọi Sign quá rộng?
9. Khi xoay khóa ký S1 sang S2, thứ tự công bố public key và chuyển signer nên như thế nào?
10. Hủy private key ký có làm cho phép xác minh chữ ký lịch sử bằng public key không thể thực hiện nữa không?
11. Chữ ký số và envelope encryption phối hợp với nhau như thế nào nếu cần cả **xác thực nguồn** và **bí mật nội dung**?

**Ghi nhớ:** Digital signature là cơ chế tạo và xác minh chữ ký bằng **private key/public key**, hỗ trợ **toàn vẹn và xác thực nguồn ký** trong điều kiện public key đáng tin và thuật toán được dùng đúng. Để một chữ ký thực sự bảo vệ hệ thống, cần gắn nó với **dữ liệu đã chuẩn hóa, mục đích, danh tính, quyền nghiệp vụ, thời hạn, chống replay, kiểm toán**, đồng thời quản lý khóa ký trong suốt vòng đời bằng **KMS/HSM và chính sách xoay vòng, thu hồi, hủy**.
