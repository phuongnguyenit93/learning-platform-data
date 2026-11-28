# Transport key: Khóa dùng để bảo vệ việc vận chuyển khóa mật mã

Giả sử dịch vụ A vừa tạo một khóa AES để mã hóa dữ liệu. Dịch vụ B cũng cần sử dụng khóa đó, nhưng A không thể gửi trực tiếp 32 byte khóa qua API rồi coi như đã an toàn. Ngoài nguy cơ bị nghe lén, hệ thống còn phải bảo đảm **đúng bên nhận**, **đúng khóa**, **đúng mục đích**, **không bị thay thế hoặc phát lại trái phép**, đồng thời có thể kiểm toán việc cấp phát.

Trong nhóm **Phân loại key**, **transport key** thường chỉ **khóa được dùng để bảo vệ một khóa khác trong quá trình chuyển giao giữa các bên hoặc các miền bảo mật**. Nó là một vai trò của khóa trong quản lý khóa, không phải tên riêng của một thuật toán. Tùy kiến trúc, transport key có thể là **key-encryption key (KEK) đối xứng** dùng để wrap khóa, hoặc **khóa công khai của bên nhận** trong cơ chế vận chuyển khóa bất đối xứng. Khóa cần vận chuyển được gọi là *transported key*; hai khái niệm này phải phân biệt rõ.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, transport key liên kết việc tạo và cấp phát khóa với lưu trữ, sử dụng, xoay vòng, thu hồi, hủy, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán. Đây là mắt xích quan trọng khi một hệ thống cần đưa key material qua ranh giới tin cậy mà vẫn giảm thiểu khả năng lộ khóa bản rõ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích transport key, transported key và key transport mechanism.
2. Phân biệt transport key với DEK, KEK, root/master key, session key và key-agreement key.
3. Mô tả các cách vận chuyển khóa qua **symmetric key wrapping**, **public-key encryption** hoặc quy trình KMS/HSM.
4. Phân tích những yêu cầu về **tính bí mật, tính toàn vẹn, xác thực nguồn và đích, mục đích sử dụng, chống phát lại**.
5. Thiết kế quy trình cấp phát, xoay vòng, nhập/xuất có kiểm soát và xử lý sự cố đối với khóa vận chuyển.

## 2. Transport key là gì?

Một **transport key** là khóa được dùng để bảo vệ vật liệu khóa khác khi vật liệu ấy được chuyển từ một thực thể hay miền tin cậy sang thực thể hoặc miền khác. Trong nhiều tài liệu quản lý khóa, đó là một loại **key-wrapping key** hoặc **key-encryption key** có mục đích cụ thể là vận chuyển khóa. Cụ thể:

- **Transport key:** khóa bảo vệ việc chuyển giao. Ví dụ: KEK AES dùng bọc DEK trước khi gửi, hoặc public key RSA của người nhận dùng mã hóa DEK.
- **Transported key:** khóa được chuyển giao. Ví dụ: một AES DEK dùng mã hóa dữ liệu ở ứng dụng đích.
- **Wrapped/encrypted key:** bản mã của transported key sau khi được bảo vệ bằng cơ chế thích hợp; đây vẫn là **key material đã mã hóa**, không phải metadata thông thường.
- **Key transport:** quy trình một bên tạo/chọn một bí mật khóa rồi chuyển cho bên kia dưới cơ chế bảo vệ thích hợp.

Ví dụ minh họa:

~~~text
Khoá A tạo một DEK:          DEK = [32 byte bí mật]
Đã có transport KEK:        KEK = [khóa AES được chia sẻ an toàn]

wrappedDEK = KeyWrap(KEK, DEK)

Bên gửi  ------------------ wrappedDEK ------------------> Bên nhận
                                                        |
                                                 KeyUnwrap(KEK, wrappedDEK)
                                                        |
                                                       DEK
~~~

Ở ví dụ này, **KEK là transport key**, **DEK là transported key**, còn **wrappedDEK** là vật liệu khóa ở dạng được bảo vệ. Giả định lớn nhất là bên gửi và nhận đã sở hữu đúng KEK theo một quy trình an toàn từ trước. Việc tạo một KEK rồi gửi nó qua email hoặc API dạng bản rõ chỉ đẩy bài toán bảo mật sang một khóa khác.

### 2.1. Tên gọi có thể thay đổi theo hệ thống

Một số hệ thống dùng thuật ngữ *transport key* cho khóa công khai phục vụ nhập khóa, trong khi hệ thống khác dùng cho KEK chia sẻ giữa hai HSM, khóa bảo vệ giao tiếp với thiết bị, hoặc khóa chỉ dùng trong một phiên cấp phát. Do đó, trước khi tích hợp cần đọc contract để trả lời: **khóa được bảo vệ là gì, thuật toán wrapping nào được dùng, bên nào sở hữu khóa bí mật, thao tác nào được phép, cách xác thực peer ra sao**. Không thể suy ra cơ chế an toàn chỉ từ một trường có tên **transportKey**.

## 3. So sánh transport key với các loại khóa khác

| Loại khóa | Vai trò chính | Dạng điển hình | Liên hệ với transport key |
|---|---|---|---|
| **DEK (Data Encryption Key)** | Mã hóa payload thực tế | AES-256 | Thường là **khóa được vận chuyển**, không phải khóa bảo vệ vận chuyển |
| **KEK (Key Encryption Key)** | Wrap/unwrap khóa khác | AES key-wrapping key | Có thể **đóng vai transport key** khi được dùng để chuyển khóa giữa các thực thể |
| **Transport key** | Bảo vệ khóa khi cấp phát/chuyển giao qua ranh giới tin cậy | KEK đối xứng hoặc khóa công khai người nhận | Vai trò theo **mục đích và quy trình sử dụng** |
| **Root/master key** | Bảo vệ tầng khóa cấp dưới hoặc dẫn xuất khóa theo kiến trúc | Key material trong HSM/KMS | Có thể bảo vệ KEK nhưng không nên tự động dùng trực tiếp để transport mọi khóa |
| **Session key** | Bảo vệ lưu lượng trong một phiên | Khóa AEAD đối xứng | Có thể được vận chuyển hoặc được thỏa thuận; không mặc nhiên là transport key |
| **Signing private key** | Tạo chữ ký số | Ed25519, ECDSA, RSA-PSS | Có thể ký gói chuyển giao để xác thực nguồn, nhưng **không phải** khóa wrap |
| **Key-agreement private key** | Tham gia tạo bí mật chung | X25519/ECDH | Thường dùng trong **key agreement**, khác cơ chế một bên chọn khóa rồi vận chuyển |

Một khóa có thể mang nhiều tên kỹ thuật theo ngữ cảnh, nhưng **quyền sử dụng** phải giới hạn theo mục đích. Không nên dùng chung một AES key để mã hóa dữ liệu khách hàng, wrap khóa, rồi xác thực thông điệp chỉ vì tất cả đều là khóa đối xứng.

### 3.1. Key transport khác key agreement

Sự phân biệt này rất quan trọng khi đọc thiết kế giao thức:

| Tiêu chí | Key transport | Key agreement |
|---|---|---|
| Cách có được bí mật chung | Một phía tạo/chọn khóa rồi chuyển cho phía nhận trong dạng được bảo vệ | Hai hoặc nhiều phía tham gia tạo ra bí mật chung |
| Ví dụ điển hình | DEK được wrap bằng KEK; RSA-OAEP bảo vệ một khóa đối xứng do người gửi sinh | ECDH/X25519 rồi dẫn xuất khóa bằng KDF |
| Dữ liệu truyền | Khóa đã mã hóa/wrapped key cùng thông tin cần thiết | Thường truyền public key tạm thời và ngữ cảnh |
| Câu hỏi an ninh chính | Có đúng người nhận, đúng wrapping key và đúng khóa cần chuyển? | Có xác thực đúng peer, xử lý public key và KDF đúng? |
| Forward secrecy | **Không tự có**; phụ thuộc giao thức và tuổi thọ khóa bảo vệ | Có thể đạt khi dùng khóa thỏa thuận tạm thời và xóa bí mật tạm thời theo giao thức |

Không đồng nhất **vận chuyển khóa** với **bắt tay TLS**. TLS 1.3 thông thường dùng thỏa thuận khóa (ECDHE hoặc cơ chế được giao thức hỗ trợ) để thiết lập bí mật phiên; không dùng cơ chế RSA key transport kiểu cũ để truyền trực tiếp premaster secret. Một kênh TLS bảo vệ giao tiếp ở tầng vận chuyển, nhưng chưa thay thế chính sách quản lý **key material được xuất/nhập** ở tầng ứng dụng.

## 4. Ba mô hình transport key thường gặp

### 4.1. Symmetric key wrapping qua KEK chung

Bên gửi và bên nhận đã có KEK giống nhau, được cấp phát an toàn trước đó. Bên gửi wrap DEK bằng **AES Key Wrap (AES-KW)** hoặc **AES Key Wrap with Padding (AES-KWP)**; bên nhận unwrap bằng cùng KEK.

~~~mermaid
sequenceDiagram
    participant A as HSM/KMS bên A
    participant C as Kênh chuyển giao
    participant B as HSM/KMS bên B
    Note over A,B: Hai miền đã thiết lập KEK chung theo quy trình an toàn
    A->>A: Tạo/chọn DEK và kiểm tra quyền ExportWrapped
    A->>A: wrappedDEK = Wrap(KEK, DEK)
    A->>C: wrappedDEK + key reference + metadata
    C->>B: Gói chuyển giao
    B->>B: Xác thực người gửi, chính sách và metadata
    B->>B: Unwrap(KEK, wrappedDEK) trong miền được bảo vệ
    B-->>B: Lưu DEK với policy mới và ghi audit
~~~

**AES-KW** theo RFC 3394 có cơ chế kiểm tra tính toàn vẹn của giá trị khóa đã bọc. **AES-KWP** theo RFC 5649 hỗ trợ dữ liệu đầu vào với độ dài không phải bội thích hợp của AES-KW. Tuy nhiên, AES-KW **không tự xác thực danh tính người gửi, người nhận, tenant hay metadata ngoài ciphertext**, và không tự ngăn phát lại một wrapped key cũ. Hệ thống cần các kiểm soát giao thức bổ sung cho những yêu cầu này.

Nếu DEK dài 32 byte và KEK là AES-256, đó là hai khóa **riêng biệt với mục đích khác nhau** dù có cùng độ dài.

### 4.2. Asymmetric key transport tới public key của người nhận

Nếu không thể hoặc không muốn dùng KEK chung, bên nhận có thể cung cấp một public key được xác thực. Bên gửi mã hóa khóa cần chuyển bằng cơ chế mã hóa khóa công khai được hỗ trợ, ví dụ **RSA-OAEP** với tham số và độ dài khóa an toàn:

~~~text
                  ĐƯỜNG GỬI                        ĐƯỜNG NHẬN
         Tạo DEK ngẫu nhiên  ------------------------+
                 |                                  |
         Xác thực public key B                       |
                 |                                  |
         RSA-OAEP Encrypt(DEK, public_B)              |
                 |                                  |
            encryptedDEK -----------------------> RSA-OAEP Decrypt
                                                  bằng private_B
                                                        |
                                                       DEK
~~~

Bên nhận giữ **private key** bí mật, ưu tiên giải mã trong KMS/HSM phù hợp. Public key không cần giữ kín nhưng bắt buộc phải có **nguồn tin cậy và ràng buộc đúng bên nhận**; nếu kẻ tấn công tráo public key, người gửi có thể mã hóa DEK cho kẻ tấn công.

RSA-OAEP chỉ phù hợp cho payload nhỏ theo giới hạn của độ dài khóa và tham số OAEP; thường nó được dùng để vận chuyển **DEK**, không mã hóa dữ liệu ứng dụng lớn. **RSA-OAEP tự nó không chứng minh bên gửi là ai**. Nếu cần tính xác thực bên gửi, phải thiết kế chứng thực nguồn, chữ ký hoặc cơ chế xác thực giao thức tương ứng.

Một số hệ thống sử dụng **KEM (Key Encapsulation Mechanism)** để tạo và đóng gói một bí mật rồi dẫn xuất keying material bằng KDF; đây là họ cơ chế có ngữ nghĩa khác việc trực tiếp mã hóa một DEK chọn sẵn. Không dùng các tên gọi interchangeably nếu API có yêu cầu cụ thể.

### 4.3. Import/export khóa được bảo vệ trong KMS/HSM

Trong môi trường nhiều miền quản trị, một HSM có thể wrap khóa bằng **transport KEK** được thiết lập giữa hai miền, hoặc một KMS cung cấp public key/tài liệu import để người gửi wrap khóa trước khi nhập.

Quy trình khái niệm:

1. Bên nhận công bố **thông số import, wrapping algorithm, key reference và thời hạn/giới hạn sử dụng** từ kênh xác thực.
2. Bên gửi kiểm tra đúng bên nhận, đúng thuật toán và chính sách **cho phép xuất dưới dạng được bảo vệ**.
3. Bên gửi wrap key material hoặc dùng cơ chế transport đúng API; tuyệt đối không dùng đường export plaintext nếu quy trình yêu cầu bảo vệ.
4. Bên nhận unwrap/import trong KMS/HSM, đặt **purpose, state, owner, tenant, export policy** theo chính sách đích.
5. Hai phía xác nhận kết quả, ghi audit và xóa bản rõ trung gian nếu có thể thực hiện an toàn.

Chữ **non-exportable** phải được hiểu theo chính sách của từng dịch vụ: có loại khóa không xuất được dưới bất kỳ hình thức nào, có loại cho phép **wrapped export** nhưng cấm plaintext export. Không suy luận khả năng import/export từ tên gọi “KMS” hay “HSM”.

## 5. Transport key có phải luôn khác với envelope encryption?

**Envelope encryption** thường dùng **DEK** mã hóa dữ liệu, còn **KEK** bảo vệ DEK. Khi wrapped DEK được chuyển giữa những bên hoặc miền tin cậy, KEK đang thực hiện **vai trò transport key**. Tuy nhiên, nếu wrapped DEK chỉ được lưu cạnh ciphertext trong cùng một hệ thống, người ta có thể gọi KEK là **wrapping key** mà không dùng tên “transport key”.

~~~mermaid
flowchart LR
    P["Dữ liệu gốc"] --> E["AES-GCM với DEK"]
    D["DEK bí mật"] --> E
    E --> C["Ciphertext + nonce + tag"]
    D --> W["Wrap DEK bằng transport KEK"]
    K["Transport KEK trong KMS/HSM"] --> W
    W --> WK["Wrapped DEK"]
    WK --> T["Chuyển giao tới miền đích"]
    C --> T
    T --> R["Kiểm tra quyền, unwrap, giải mã"]
~~~

| Thành phần trong gói | Vai trò | Lưu ý |
|---|---|---|
| **DEK bản rõ** | Key material cần vận chuyển | Không được gửi bản rõ qua giao diện không được bảo vệ; giảm tối đa thời gian tồn tại trong bộ nhớ |
| **Transport KEK / private key nhận** | Key material dùng bảo vệ hoặc nhận khóa | Giữ trong ranh giới tin cậy, giới hạn quyền Wrap/Unwrap hoặc Encrypt/Decrypt |
| **Wrapped DEK** | Key material được mã hóa | Không phải “metadata công khai” chỉ vì có thể lưu cùng ciphertext |
| **Key ID, version, wrapping algorithm** | Metadata chọn đúng khóa bảo vệ và thuật toán | Không tin giá trị do request không xác thực tự khai |
| **Recipient/tenant/purpose/message ID** | Ngữ cảnh chuyển giao và chính sách | Phải được ràng buộc/xác thực theo container hoặc giao thức |
| **Nonce/IV/tag** | Tham số/cấu phần của phép mã hóa dữ liệu hoặc AEAD | Không phải transport key; nonce phải tuân thủ quy tắc thuật toán, đặc biệt tránh trùng dưới cùng khóa GCM |

Nếu đóng gói metadata thành JSON bên cạnh wrapped DEK, việc sửa JSON không nhất thiết làm **AES-KW unwrap thất bại**. Phải thiết kế cách **ràng buộc metadata với key material được bảo vệ**: chẳng hạn container có chữ ký/MAC xác thực toàn gói, giao thức key block được xác thực, hoặc dùng AEAD với AAD được xác định rõ. Việc chỉ dùng HTTPS cho đường truyền không tự xác thực dữ liệu sau khi gói được lưu, chuyển tiếp hay đọc lại ở hệ thống khác.

## 6. Ví dụ Java 17: AES Key Wrap để bảo vệ DEK khi chuyển giao

Ví dụ dùng **AESWrap** của Java Cryptography Architecture (JCA), có trên provider thông dụng như SunJCE của OpenJDK/Oracle JDK 17. Chương trình mô phỏng hai bên đã được cấp **cùng một transport KEK**. Trong triển khai thật, KEK nên được cấp phát và giữ trong KMS/HSM hoặc cơ chế quản lý khóa phù hợp; không truyền KEK bằng phương thức trao đổi wrapped DEK.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class TransportKeyDemo {
    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);

        // Mô phỏng KEK đã được phân phối an toàn cho hai miền.
        SecretKey transportKek = generator.generateKey();

        // DEK này là key material được vận chuyển.
        SecretKey originalDek = generator.generateKey();

        // Bên gửi: AES Key Wrap dùng KEK để bảo vệ DEK.
        Cipher wrapper = Cipher.getInstance("AESWrap");
        wrapper.init(Cipher.WRAP_MODE, transportKek);
        byte[] wrappedDek = wrapper.wrap(originalDek);

        // Chỉ trao đổi wrappedDek cùng metadata đã được xác thực.
        System.out.println("Wrapped DEK (Base64): "
                + Base64.getEncoder().encodeToString(wrappedDek));

        // Bên nhận: đã sở hữu cùng transport KEK theo kênh an toàn.
        Cipher unwrapper = Cipher.getInstance("AESWrap");
        unwrapper.init(Cipher.UNWRAP_MODE, transportKek);
        SecretKey receivedDek = (SecretKey) unwrapper.unwrap(
                wrappedDek, "AES", Cipher.SECRET_KEY);

        // Chứng minh nhận đúng DEK: mã hóa bằng khóa gốc,
        // giải mã bằng khóa đã unwrap ở phía nhận.
        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);
        byte[] plaintext = "demo data".getBytes(StandardCharsets.UTF_8);

        Cipher encryptor = Cipher.getInstance("AES/GCM/NoPadding");
        encryptor.init(Cipher.ENCRYPT_MODE, originalDek,
                new GCMParameterSpec(128, nonce));
        byte[] ciphertextAndTag = encryptor.doFinal(plaintext);

        Cipher decryptor = Cipher.getInstance("AES/GCM/NoPadding");
        decryptor.init(Cipher.DECRYPT_MODE, receivedDek,
                new GCMParameterSpec(128, nonce));
        byte[] restored = decryptor.doFinal(ciphertextAndTag);

        System.out.println("Restored: "
                + new String(restored, StandardCharsets.UTF_8));

        // Không log transportKek.getEncoded() hay originalDek.getEncoded().
    }
}
~~~

Lưu thành **TransportKeyDemo.java** và chạy với JDK 17+:

~~~bash
javac TransportKeyDemo.java
java TransportKeyDemo
~~~

Kết quả sẽ in **Wrapped DEK (Base64): ...** và **Restored: demo data**. Giá trị wrapped DEK thay đổi giữa các lần chạy vì chương trình tạo KEK và DEK ngẫu nhiên mới. Đây là chứng minh cơ chế **wrap → chuyển giao bản mã khóa → unwrap → sử dụng khóa**, không phải mã triển khai một protocol cấp phát khóa hoàn chỉnh.

**Bốn giới hạn an ninh của demo cần hiểu rõ:**

1. **Khởi tạo KEK chung là vấn đề riêng.** Hai thực thể trong chương trình dùng chung một đối tượng SecretKey vì chúng nằm trong cùng tiến trình. Khi triển khai trên hai máy/HSM khác nhau, phải có cơ chế thiết lập KEK ban đầu và định danh khóa an toàn.
2. **AESWrap không bảo vệ toàn bộ metadata của gói.** Demo chưa có chữ ký/MAC cho key ID, owner, tenant, mục đích, phiên bản, message ID hoặc anti-replay; hệ thống production phải bổ sung theo threat model.
3. **DEK được tạo trong bộ nhớ Java để minh họa.** Với khóa không xuất được trong HSM, gọi API **Wrap/Unwrap** nội bộ thay vì đọc byte khóa ra ứng dụng; khả năng này phụ thuộc provider.
4. **AES-GCM dùng nonce mới trên mỗi lần mã hóa với cùng DEK.** Ví dụ chỉ mã hóa một lần. Hệ thống có nhiều instance/lưu lượng lớn phải thiết kế nonce duy nhất và giới hạn sử dụng khóa cho phù hợp.

Nếu provider báo không hỗ trợ **AESWrap**, cần chọn provider và cơ chế wrapping đã được kiểm chứng, đúng yêu cầu tương thích giữa hai bên. Không tự thay bằng việc dùng AES-ECB hay tự mã hóa raw key thiếu bảo vệ tính toàn vẹn.

## 7. Metadata và hợp đồng trao đổi khóa

Mỗi lần chuyển khóa nên có một *contract* rõ ràng để tránh thành công về mặt mật mã nhưng sai chính sách:

| Trường minh họa | Tại sao cần |
|---|---|
| **transferId / messageId** | Phân biệt lần chuyển giao, hỗ trợ idempotency và xử lý chống replay |
| **senderId / recipientId** | Xác định đúng chủ thể gửi và bên nhận được cấp khóa |
| **transportKeyId / transportKeyVersion** | Chọn đúng KEK hoặc private key dùng unwrap |
| **wrappedKey / wrappedKeyAlgorithm** | Vật liệu khóa được bảo vệ và cơ chế wrapping tương ứng |
| **importedKeyType / purpose** | Ràng buộc khóa đích dùng AES, HMAC, ký, hay mục đích khác |
| **tenant / application / environment** | Giới hạn phạm vi người dùng và bối cảnh sử dụng |
| **issuedAt / expiresAt / policyRef** | Điều phối hiệu lực gói và chính sách import |
| **integrity / authentication proof** | Chữ ký/MAC hoặc cơ chế container xác thực gắn nội dung với nguồn tin cậy |

Các tên trường là **schema minh họa**, không phải chuẩn bắt buộc. Một đối tượng JSON chứa các trường này **chưa tự an toàn** nếu không được xác thực, kiểm soát quyền và ràng buộc vào ngữ cảnh bảo vệ.

Ví dụ JSON chỉ để hình dung gói chuyển giao (**tất cả giá trị đều là placeholder**):

~~~json
{
  "formatVersion": 1,
  "transferId": "transfer-2026-001",
  "senderId": "kms-domain-a",
  "recipientId": "kms-domain-b",
  "transportKeyId": "transport-kek",
  "transportKeyVersion": "v7",
  "wrappedKeyAlgorithm": "AES-KW",
  "wrappedKey": "<BASE64_WRAPPED_KEY>",
  "importedKeyType": "AES-256",
  "purpose": "DATA_ENCRYPTION",
  "tenant": "tenant-42",
  "expiresAt": "<POLICY_DEFINED_TIME>",
  "authenticationProof": "<SIGNATURE_OR_MAC_OVER_CANONICAL_PACKAGE>"
}
~~~

Cần thống nhất **quy tắc canonicalization**, encoding và trường nào được xác thực. Nếu có một chữ ký trên gói thì bên nhận còn phải biết public key xác minh của người gửi từ **nguồn tin cậy**. Một client được quyền xem wrappedKey không đương nhiên có quyền unwrap hoặc đổi mục đích sử dụng khóa.

## 8. Kiểm soát truy cập, kiểm toán và vòng đời transport key

### 8.1. Ai được phép làm gì?

| Vai trò | Quyền gợi ý | Quyền cần hạn chế |
|---|---|---|
| **Key administrator** | Cấu hình policy, vòng đời, định danh và phân quyền | Không tự động có quyền xem/export raw key hoặc dùng mọi khóa |
| **Exporting service** | Wrap/export **dưới dạng được bảo vệ** đúng key/recipient | Không được tự chuyển raw private key/DEK sang nơi tùy ý |
| **Importing service** | Kiểm tra gói, unwrap/import vào miền đích và gắn purpose phù hợp | Không được dùng key transport của tenant khác |
| **Data processing service** | Sử dụng DEK đã cấp để mã hóa/giải mã theo ứng dụng | Không cần quyền quản trị transport KEK |
| **Auditor** | Xem metadata, kết quả và nhật ký nghiệp vụ | Không cần quyền đọc private key, KEK hoặc DEK |

Tách **Wrap**, **Unwrap**, **ImportKey**, **ExportWrappedKey**, **ManagePolicy** và **DestroyKey** khi KMS/HSM hỗ trợ. Một quyền **Decrypt/Unwrap** quá rộng có thể khiến người bị chiếm tài khoản lấy được DEK mà không cần biết raw KEK.

### 8.2. Quản lý vòng đời

~~~mermaid
flowchart TD
    A["Sinh/nhập transport key phù hợp"] --> B["Xác thực các bên và gắn owner/purpose"]
    B --> C["Phân phối/đăng ký an toàn"]
    C --> D["Kích hoạt quyền wrap/unwrap"]
    D --> E["Ghi audit từng lần chuyển khóa"]
    E --> F["Đến hạn xoay hoặc xảy ra sự cố"]
    F --> G["Cấp transport key phiên bản mới"]
    G --> H["Chuyển gói mới sang phiên bản mới"]
    H --> I["Xử lý khóa/gói cũ còn phụ thuộc"]
    I --> J["Vô hiệu hóa và hủy khi đủ điều kiện"]
~~~

**Xoay transport key không đồng nghĩa tự xoay mọi DEK được transport.** Khi đổi KEK từ **v7** sang **v8**, các wrapped DEK cũ có thể vẫn cần **v7** để unwrap. Có thể phải **rewrap** DEK bằng KEK mới, cập nhật key ID/version và kiểm tra khả năng phục hồi trước khi hủy v7. Rewrap giúp thay khóa bảo vệ DEK, nhưng **không đổi bản thân DEK**; nếu DEK đã bị lộ, phải tạo DEK mới và xem xét mã hóa lại dữ liệu theo kế hoạch phù hợp.

**Thu hồi/vô hiệu hóa** ngăn hoặc giới hạn sử dụng transport key theo chính sách, nhưng bản sao KEK còn tồn tại ở miền khác hoặc bản ghi đã giải mã có thể tiếp tục là rủi ro. **Hủy** phải xét dữ liệu lịch sử, backup, bản sao phân phối và quy trình khôi phục. Với công cụ KMS cụ thể, hành vi xóa, thời gian chờ và khả năng hoàn tác tùy dịch vụ.

### 8.3. Audit nên ghi và không nên ghi gì?

Nên ghi: **actor/service identity**, thời gian, **key ID/version**, action **Wrap/Unwrap/Import/Export**, tenant, recipient, transfer ID, nguồn yêu cầu, kết quả và mã lỗi an toàn. Không ghi **KEK, plaintext DEK, private key, passphrase, thông tin bí mật trong context hoặc raw payload nhạy cảm**. Log phải được bảo vệ và có cơ chế tương quan yêu cầu để điều tra sự cố.

## 9. Threat model: vận chuyển khóa có thể thất bại như thế nào?

| Sai sót | Hậu quả | Phòng vệ |
|---|---|---|
| Gửi DEK bản rõ qua API, email, log hoặc file tạm | Rò rỉ khóa dù dữ liệu ứng dụng vẫn được mã hóa | Wrap/encrypt key theo cơ chế chuẩn; hạn chế plaintext export và bản sao trung gian |
| Thiết lập KEK chung bằng kênh không an toàn | Kẻ nghe lén có thể unwrap mọi khóa đi qua | Bootstrap KEK qua KMS/HSM, quy trình cấp phát xác thực, hoặc chọn cơ chế public-key phù hợp |
| Không xác thực public key người nhận | DEK bị mã hóa cho kẻ tấn công | PKI/pinning/kênh tin cậy; xác minh recipient và key reference |
| Chỉ AES-KW wrappedKey mà không ràng buộc metadata | Gói có thể bị thay recipient, purpose, tenant, key ID | Xác thực toàn bộ container/context bằng MAC/chữ ký hoặc giao thức hỗ trợ |
| Import gói cũ nhiều lần | Replay, trạng thái khóa cũ bị khôi phục trái phép, vượt chính sách | Transfer ID, nonce giao thức, hạn hiệu lực, idempotency và nhật ký chống replay |
| Dùng cùng transport key cho nhiều miền mà không phân quyền | Một tài khoản bị chiếm ảnh hưởng nhiều tenant/hệ thống | Tách miền, purpose, môi trường và vai trò theo rủi ro |
| Không ghi phiên bản transport KEK | Sau rotation không biết khóa nào unwrap bản ghi cũ | Lưu key ID/version chính xác theo hợp đồng của KMS |
| Hủy KEK trước khi rewrap gói cũ | Không phục hồi được transported key, mất khả năng giải mã dữ liệu | Rewrap, thử restore/rollback, quy trình xóa có kiểm soát |
| Cho phép unwrap không giới hạn | Người có quyền API có thể lấy DEK dù raw KEK vẫn an toàn | IAM tối thiểu, workload identity, quota, approval nếu phù hợp, audit và cảnh báo |
| Tự xây giao thức wrapping bằng AES-ECB hoặc AES-CBC không kiểm tra toàn vẹn | Khóa bị sửa/tráo, lỗi giải mã hoặc kênh tấn công | Dùng AES-KW/AES-KWP, AEAD hoặc chuẩn key block phù hợp; kiểm tra toàn bộ contract |

Một **kết nối TLS hợp lệ** vẫn cần chính sách cấp phát và xác thực ở tầng ứng dụng: nếu một dịch vụ nội bộ đã bị chiếm, nó có thể gửi yêu cầu unwrap qua HTTPS hoàn toàn hợp lệ. Bảo vệ đường truyền và kiểm soát quyền **sử dụng khóa** là hai lớp bổ sung cho nhau.

## 10. Ví dụ tình huống: chuyển DEK giữa hai miền KMS

Một doanh nghiệp vận hành **KMS-A** phục vụ hệ thống lưu trữ và **KMS-B** phục vụ hệ thống phân tích. Cần chuyển một DEK từ miền A sang miền B để xử lý dữ liệu đã được cho phép, nhưng chính sách cấm truyền raw DEK.

**Quy trình đề xuất:**

1. Chủ sở hữu dữ liệu phê duyệt phạm vi tenant, loại dữ liệu, thời hạn và mục đích **ANALYTICS_DECRYPT**.
2. Hai miền xác thực lẫn nhau; bên B cung cấp **wrapping/import parameters** từ nguồn xác thực hoặc hai miền đã thiết lập KEK dùng chung qua cơ chế an toàn.
3. KMS-A kiểm tra chính sách export, tạo **wrapped DEK** đúng thuật toán và ghi transfer ID, source key ID/version, đích nhận, thời gian.
4. Dịch vụ chuyển giao gửi gói **đã xác thực toàn bộ metadata**, có kiểm soát replay và thời hạn.
5. KMS-B kiểm tra chữ ký/MAC, recipient, tenant, allowed purpose, version, duplicate transfer ID, sau đó unwrap/import trong ranh giới bảo vệ; gán key ID và policy đích.
6. Cả hai bên đối soát audit theo transfer ID. Khi chuyển sang transport key mới, dữ liệu/gói cũ được rewrap hoặc giữ khả năng unwrap có giới hạn cho đến khi hết phụ thuộc.

Nếu KMS-A **không hỗ trợ wrapped export** của khóa nguồn, quy trình này phải thay đổi theo khả năng được phép của nền tảng; không tìm cách lấy raw key qua debug, backup hoặc thao tác vượt chính sách. Khi mô hình tin cậy không cho phép chuyển khóa, cần cân nhắc cho hệ thống B gọi phép toán được ủy quyền tại A thay vì xuất material.

## 11. Checklist thiết kế transport key

1. **Phân loại:** đâu là transport key, đâu là transported key và đâu chỉ là metadata?
2. **Chọn thuật toán:** AES-KW/KWP, public-key encryption/KEM hay API import/export của KMS/HSM có phù hợp với loại khóa và threat model?
3. **Bootstrap:** hai phía có được khóa/cặp khóa bảo vệ từ kênh đáng tin cậy và xác thực đúng bên nhận?
4. **Giới hạn quyền:** ai có quyền tạo, wrap, unwrap, export, import, quản trị policy và hủy? Có tách tenant/môi trường/mục đích?
5. **Bảo vệ gói:** có bảo vệ tính toàn vẹn, xác thực nguồn, recipient, key version và thuộc tính purpose, chống replay?
6. **Lưu tham chiếu:** có lưu đủ wrapping algorithm, transport key ID/version và thông tin cần cho giải mã/khôi phục?
7. **Hạn chế lộ khóa:** có tránh raw key trong log, code, CI/CD, file tạm và response API không?
8. **Rotation:** wrapped key cũ sẽ được rewrap hoặc sử dụng thế nào sau khi KEK thay đổi?
9. **Thu hồi/hủy:** đã đánh giá tất cả gói, dữ liệu cũ và backup còn phụ thuộc chưa?
10. **Kiểm toán:** mỗi lần chuyển giao có transfer ID, actor, target, kết quả và khả năng truy vết?

### Câu hỏi tự kiểm tra

**Câu 1.** Bên A wrap DEK bằng KEK-1 rồi gửi wrapped DEK cho B. Khóa nào là transport key?

**Trả lời:** **KEK-1** là transport key; **DEK** là transported key; **wrapped DEK** là biểu diễn DEK đã được bảo vệ.

**Câu 2.** Đã dùng AES-KW, vậy có thể tin toàn bộ trường **tenant** và **recipientId** trong JSON đi kèm không?

**Trả lời:** **Không.** AES-KW bảo vệ giá trị khóa được wrap nhưng không tự ràng buộc metadata JSON ở ngoài. Cần xác thực gói và kiểm tra chính sách nguồn/đích.

**Câu 3.** KMS đổi KEK v2 sang v3. Những wrapped DEK tạo bằng v2 có tự giải mã bằng v3 được không?

**Trả lời:** **Không.** Phải còn quyền dùng KEK v2 để unwrap hoặc thực hiện quy trình **rewrap** có kiểm soát bằng v3.

**Câu 4.** Vì sao ECDH không đơn giản được gọi là “gửi transport key”?

**Trả lời:** ECDH là **key agreement**: các bên cùng tính một bí mật chung từ private key của mình và public key phía kia, sau đó dẫn xuất khóa; không có bước một bên chọn sẵn DEK rồi mã hóa để gửi theo định nghĩa key transport truyền thống.

**Điểm cốt lõi:** Transport key bảo vệ **việc chuyển giao key material**, còn thiết kế giao thức bảo đảm **đúng bên, đúng mục đích, đúng phiên bản và đúng quyền**. Một wrapped key chỉ là một phần của quy trình quản lý khóa an toàn; hệ thống còn cần xác thực, metadata được ràng buộc, phân quyền, audit và kế hoạch rotation/recovery đầy đủ.
