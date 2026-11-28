# Key pair – Cặp khóa công khai và khóa bí mật

**Key pair** (cặp khóa) là hai khóa mật mã liên hệ với nhau về mặt toán học trong một hệ mật mã bất đối xứng:

- **Public key (khóa công khai):** có thể phân phối cho người khác để xác minh chữ ký, mã hóa hoặc tham gia thiết lập bí mật chung, tùy thuật toán.
- **Private key (khóa bí mật):** do chủ sở hữu kiểm soát; được dùng để ký, giải mã hoặc tham gia thiết lập bí mật chung, tùy thuật toán. Đây là thành phần phải bảo vệ nghiêm ngặt.

Một cặp khóa được tạo bằng thuật toán sinh khóa phù hợp. Với thuật toán và tham số an toàn, việc biết public key không cho phép suy ra private key bằng năng lực tính toán thực tế. Hai khóa **không thể hoán đổi vai trò tùy ý**: khả năng sử dụng phụ thuộc vào thuật toán và mục đích sinh khóa.

Trong quản lý khóa mật mã (**SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**), hiểu key pair là nền tảng để thiết kế vòng đời khóa từ **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi đến hủy**. Key pair kết nối các chủ đề mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

## 1. Key pair dùng để làm gì?

### 1.1. Ký số và xác minh chữ ký

Chủ sở hữu dùng **private key để ký** một thông điệp (hoặc dữ liệu đã được xử lý theo thuật toán chữ ký). Người nhận dùng **public key tương ứng để xác minh** chữ ký. Nếu chữ ký hợp lệ và khóa công khai đã được xác thực là thuộc về đúng chủ thể, người nhận có cơ sở tin rằng dữ liệu không bị thay đổi sau khi ký và chữ ký được tạo bởi bên kiểm soát private key.

~~~mermaid
flowchart LR
    A["Thông điệp"] --> B["Ký bằng private key"]
    P["Private key: giữ bí mật"] --> B
    B --> C["Thông điệp + chữ ký"]
    C --> D["Xác minh bằng public key"]
    U["Public key: đã xác thực chủ sở hữu"] --> D
    D --> E{"Chữ ký hợp lệ?"}
    E -->|Có| F["Chấp nhận tính toàn vẹn và nguồn ký theo chính sách"]
    E -->|Không| G["Từ chối"]
~~~

Ví dụ: dịch vụ phát hành token ký JWT bằng private key; các dịch vụ nhận token xác minh chữ ký bằng public key tương ứng. **Chữ ký không mã hóa nội dung**: dữ liệu token vẫn có thể đọc được nếu không có lớp mã hóa riêng. Việc xác minh còn phải kiểm tra thuật toán được cho phép, thời hạn, bên phát hành, đối tượng nhận và các điều kiện nghiệp vụ.

### 1.2. Mã hóa bất đối xứng và giải mã

Với **thuật toán hỗ trợ mã hóa** như RSA-OAEP, bên gửi có thể mã hóa một lượng dữ liệu nhỏ bằng public key của người nhận; chỉ bên giữ private key tương ứng mới giải mã được. Trong hệ thống thực tế, người ta thường **mã hóa dữ liệu lớn bằng khóa đối xứng** (chẳng hạn AES-GCM) rồi dùng cơ chế bất đối xứng thích hợp để bảo vệ khóa đối xứng đó.

Ví dụ quy trình hybrid encryption:

1. Sinh một **data encryption key (DEK)** ngẫu nhiên để mã hóa tệp bằng thuật toán mã hóa xác thực, chẳng hạn AES-GCM.
2. Bảo vệ DEK bằng khóa công khai của người nhận qua một cơ chế chuẩn phù hợp, chẳng hạn RSA-OAEP cho đầu vào đủ nhỏ hoặc một cơ chế mã hóa lai như HPKE.
3. Lưu hoặc truyền bản mã dữ liệu cùng DEK đã được bảo vệ và thông tin cần thiết (thuật toán, nonce, phiên bản khóa).
4. Người nhận dùng private key qua cơ chế tương ứng để khôi phục DEK, sau đó giải mã và kiểm tra tính toàn vẹn của dữ liệu.

**Lưu ý:** envelope encryption dùng KMS trong thực tế cũng thường dựa trên **khóa chủ đối xứng (KEK)** của KMS để bọc DEK; không phải mọi hệ thống envelope encryption đều cần một key pair.

### 1.3. Thỏa thuận khóa

Một số key pair dùng cho **key agreement**, chẳng hạn X25519. Hai bên kết hợp private key của mình với public key của bên kia để tính ra cùng một giá trị bí mật, sau đó dùng hàm dẫn xuất khóa (KDF) để tạo khóa phiên đối xứng. Giá trị tạo ra không nên dùng trực tiếp như khóa AES nếu chưa thực hiện bước dẫn xuất theo giao thức.

Key agreement **không tự xác thực danh tính**: nếu kẻ tấn công thay public key trên đường truyền, họ có thể thực hiện tấn công người đứng giữa (MITM). Giao thức phải xác thực các public key, chứng chỉ hoặc transcript bắt tay theo thiết kế.

## 2. Phân biệt các loại key pair

| Thuật toán/cơ chế | Công dụng chính | Điểm cần nhớ |
| --- | --- | --- |
| **RSA-PSS** | Chữ ký số RSA | Dùng padding/chế độ ký an toàn; không tự thay bằng thao tác RSA thô. |
| **RSA-OAEP** | Mã hóa bất đối xứng RSA | Giới hạn kích thước đầu vào; phù hợp bảo vệ dữ liệu nhỏ hoặc thành phần của giải pháp lai. |
| **ECDSA** (ví dụ P-256) | Chữ ký số dựa trên đường cong elliptic | Chất lượng nonce khi ký rất quan trọng; dùng thư viện chuẩn. |
| **Ed25519** | Chữ ký số | Dùng cho ký và xác minh; **không phải** thuật toán mã hóa hay ECDH. |
| **X25519** | Thỏa thuận khóa ECDH | Dùng để thiết lập bí mật chung; **không phải** thuật toán ký số. |

Tên thuật toán, bộ tham số, độ dài khóa, chế độ mã hóa/chữ ký và các chính sách sử dụng phải được lựa chọn cùng nhau. Không so sánh độ dài khóa RSA và khóa đường cong elliptic chỉ bằng số bit vì mức an toàn được xác định theo các giả định toán học khác nhau.

**Phân biệt với khóa đối xứng:** mã hóa đối xứng dùng cùng một khóa bí mật (hoặc các khóa dẫn xuất liên quan) ở hai phía; key pair chứa một private key và một public key với các vai trò khác nhau. Trong hệ thống lớn, hai cơ chế thường phối hợp thay vì thay thế hoàn toàn cho nhau.

## 3. Sở hữu public key có đồng nghĩa xác thực danh tính không?

**Không.** Public key có thể được chia sẻ rộng rãi nhưng phải xác minh được nó thực sự thuộc về chủ thể mong muốn. Nếu kẻ tấn công lừa ứng dụng dùng public key giả, ứng dụng có thể mã hóa dữ liệu cho sai người hoặc chấp nhận chữ ký giả mạo của kẻ tấn công.

Các cách gắn public key với danh tính hoặc đối tượng tin cậy gồm:

- **Chứng chỉ X.509/TLS:** hệ thống kiểm tra chuỗi chứng chỉ, tên miền, thời hạn và các điều kiện sử dụng theo chính sách tin cậy.
- **SSH host key:** máy khách ghi nhận hoặc kiểm tra fingerprint của khóa máy chủ trước khi tin tưởng.
- **JWKS trong hệ thống xác thực:** dịch vụ phát hành công bố public key kèm mã định danh khóa (**kid**); bên xác minh lấy khóa từ nguồn tin cậy đã cấu hình và ràng buộc thuật toán, issuer, audience, expiry.
- **Fingerprint/out-of-band:** hai bên đối chiếu dấu vân tay khóa qua kênh đáng tin cậy khi phù hợp.

**kid chỉ là mã chọn khóa**, không chứng minh khóa đó đáng tin. Một public key bị thay thế trái phép vẫn nguy hiểm dù bản thân nó không phải bí mật.

## 4. Vòng đời key pair trong quản lý khóa

Quản lý key pair không dừng ở lệnh sinh khóa. Mỗi giai đoạn cần có người chịu trách nhiệm, chính sách sử dụng và bằng chứng kiểm toán.

| Giai đoạn | Hoạt động cần thực hiện | Nguy cơ khi làm sai |
| --- | --- | --- |
| **Tạo (generation)** | Dùng bộ sinh số ngẫu nhiên mật mã an toàn, thuật toán và tham số đã phê duyệt; ưu tiên sinh private key trong KMS/HSM khi yêu cầu bảo mật cao. | Khóa dễ dự đoán, khóa quá yếu hoặc trùng lặp. |
| **Cấp phát/đăng ký** | Gắn key ID, chủ sở hữu, môi trường, mục đích sử dụng, phiên bản và public key/chứng chỉ được xác thực. | Ứng dụng dùng nhầm khóa hoặc chấp nhận public key giả. |
| **Lưu trữ** | Bảo vệ private key bằng HSM/KMS, kho bí mật hoặc vùng lưu trữ đã mã hóa với ACL chặt chẽ; public key được phân phối bảo đảm tính toàn vẹn. | Private key rò rỉ qua tệp, bản sao lưu, biến môi trường, log hoặc repository. |
| **Sử dụng** | Giới hạn quyền ký/giải mã theo dịch vụ và mục đích, ghi log truy cập, không xuất private key nếu không cần. | Lạm dụng chức năng ký hoặc giải mã dù chưa lấy được khóa thô. |
| **Xoay vòng** | Tạo cặp khóa mới, công bố public key mới, chuyển ứng dụng sang key ID mới và lập kế hoạch hỗ trợ dữ liệu/chữ ký cũ. | Mất khả năng giải mã dữ liệu lịch sử hoặc xác minh token/chữ ký còn hiệu lực. |
| **Thu hồi/ngừng dùng** | Ngừng cấp quyền dùng khóa và thực hiện cơ chế thu hồi chứng chỉ, cập nhật khóa tin cậy/JWKS theo loại hệ thống. | Khóa bị lộ vẫn được chấp nhận hoặc tiếp tục sinh chữ ký. |
| **Hủy** | Hủy key material và các bản sao theo chính sách, kiểm tra thời hạn lưu giữ và yêu cầu khôi phục. | Khóa tồn dư bị lộ hoặc dữ liệu bị mất vĩnh viễn vì hủy quá sớm. |

Ví dụ khi xoay khóa ký JWT: phát hành token mới bằng private key phiên bản **K2**, đồng thời tạm giữ public key **K1** trong JWKS để xác minh token K1 chưa hết hạn. Sau khi hết cửa sổ chấp nhận, gỡ K1 theo chính sách. Nếu K1 bị lộ, quy trình ứng phó có thể cần vô hiệu hóa token K1 sớm hơn, chấp nhận đánh đổi về tính sẵn sàng.

Với cặp khóa dùng để **giải mã**, dữ liệu cũ thường vẫn cần private key cũ cho đến khi được giải mã và mã hóa lại hoặc được xử lý theo chính sách lưu giữ. Xóa private key khi vẫn còn bản mã phụ thuộc vào nó có thể khiến dữ liệu không thể khôi phục.

## 5. Vai trò của KMS, HSM và kiểm soát truy cập

**KMS (Key Management Service)** quản lý vòng đời và chính sách sử dụng khóa qua API. **HSM (Hardware Security Module)** là phần cứng chuyên dụng có cơ chế bảo vệ vật liệu khóa và thực hiện phép toán mật mã trong ranh giới bảo mật của thiết bị. Dịch vụ KMS có thể sử dụng HSM ở phía sau, nhưng cần đọc khả năng và cam kết bảo vệ thực tế của nhà cung cấp.

Trong mô hình khóa bất đối xứng được bảo vệ bởi KMS/HSM:

1. Dịch vụ tạo key pair theo thuật toán và mục đích đã chọn.
2. **Private key có thể được đánh dấu không cho xuất (non-exportable)** và chỉ được dùng thông qua API ký hoặc giải mã mà dịch vụ hỗ trợ.
3. Ứng dụng nhận public key hoặc chứng chỉ để phân phối cho hệ thống cần xác minh/mã hóa.
4. Mỗi lệnh ký/giải mã được phân quyền theo danh tính dịch vụ, phạm vi khóa và môi trường; hệ thống theo dõi các lần sử dụng bất thường.

Như vậy, bảo vệ private key không chỉ là giữ kín bytes của khóa. Kẻ tấn công có quyền gọi API ký vẫn có thể tạo chữ ký trái phép. Cần áp dụng **least privilege**, phân tách nhiệm vụ quản trị khóa và sử dụng khóa, chính sách phê duyệt khi cần, giám sát lưu lượng và cảnh báo.

Không phải mọi KMS hỗ trợ cùng thuật toán hay cho phép dùng một khóa cho cả ký và giải mã. Phải kiểm tra khai báo **key usage**, giao diện API và định dạng chữ ký/bản mã của dịch vụ trước khi thiết kế tích hợp.

## 6. Ví dụ Java: sinh cặp khóa và ký/xác minh bằng Ed25519

Ví dụ dưới đây dùng Java 17+ và API **Java Cryptography Architecture (JCA)** để minh họa ba bước: sinh key pair, ký bằng private key, xác minh bằng public key.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.Signature;

public class KeyPairDemo {
    public static void main(String[] args) throws Exception {
        // 1. Sinh cặp khóa Ed25519 cho ví dụ chạy trong bộ nhớ.
        KeyPairGenerator generator = KeyPairGenerator.getInstance("Ed25519");
        KeyPair keyPair = generator.generateKeyPair();

        byte[] message = "Phe duyet don hang #123"
                .getBytes(StandardCharsets.UTF_8);

        // 2. Chủ sở hữu ký với private key.
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(keyPair.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        // 3. Bên nhận xác minh với public key tương ứng.
        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(keyPair.getPublic());
        verifier.update(message);
        boolean valid = verifier.verify(signature);

        // Nếu nội dung bị sửa, chữ ký không còn hợp lệ.
        Signature tamperedVerifier = Signature.getInstance("Ed25519");
        tamperedVerifier.initVerify(keyPair.getPublic());
        tamperedVerifier.update("Phe duyet don hang #999"
                .getBytes(StandardCharsets.UTF_8));
        boolean tamperedValid = tamperedVerifier.verify(signature);

        System.out.println("Original valid: " + valid);        // true
        System.out.println("Modified valid: " + tamperedValid); // false
    }
}
~~~

**Ý nghĩa:** chữ ký phụ thuộc vào đúng thông điệp và private key. Public key đủ để kiểm tra chữ ký mà không cần biết private key. Nhưng ví dụ chưa chứng minh người ký là ai: hệ thống sản xuất vẫn phải xác thực mối liên hệ giữa public key và danh tính người/cơ quan phát hành.

Đây là mã minh họa với private key nằm trong bộ nhớ ứng dụng. Trong hệ thống có yêu cầu quản lý khóa cao, ứng dụng nên gọi KMS/HSM để ký bằng key ID và dùng public key đã xác thực để kiểm tra. Không ghi private key ra console, log, source code hoặc bộ nhớ ngoài không được bảo vệ. Định dạng khóa và chữ ký khi liên thông hệ thống phải tuân thủ chuẩn tương ứng.

## 7. Các lỗi thường gặp và cách phòng tránh

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đưa private key vào Git, image, cấu hình tĩnh hoặc log | Bất kỳ ai đọc được đều có thể mạo danh ký hoặc giải mã tùy mục đích khóa. | Dùng KMS/HSM hoặc kho bí mật; quét rò rỉ, thu hồi/xoay khóa nếu lộ. |
| Tải public key từ nguồn chưa xác thực | Tấn công thay khóa, MITM hoặc tin nhầm chữ ký. | Kiểm tra chứng chỉ, fingerprint, danh tính nhà phát hành và nguồn JWKS tin cậy. |
| Dùng Ed25519 để “mã hóa”, X25519 để “ký” | API không phù hợp, thiết kế sai thuộc tính bảo mật. | Chọn thuật toán theo đúng chức năng và cấu hình key usage riêng. |
| Tự triển khai primitive mật mã hoặc dùng RSA thô | Lỗi padding, giao thức hoặc xử lý dữ liệu khiến cơ chế không an toàn. | Dùng thư viện/giao thức đã được kiểm chứng, ví dụ RSA-OAEP, RSA-PSS, HPKE. |
| Dùng lại một key pair cho nhiều mục đích không liên quan | Khó cô lập sự cố, tăng phạm vi ảnh hưởng khi lộ khóa. | Tách khóa theo mục đích, môi trường, ứng dụng và chính sách sử dụng. |
| Xoay khóa nhưng quên dữ liệu hay token cũ | Hỏng xác minh, mất khả năng giải mã hoặc gián đoạn dịch vụ. | Quản lý phiên bản, giai đoạn chuyển tiếp, thời hạn token và tái mã hóa khi cần. |
| Chỉ bảo vệ bytes của private key, mở quyền gọi API ký cho mọi dịch vụ | Kẻ tấn công có thể lạm dụng khóa dù không xuất được private key. | Giới hạn quyền theo danh tính, khóa, mục đích; audit và cảnh báo bất thường. |
| Không có quy trình khôi phục cho khóa giải mã quan trọng | Mất khóa dẫn tới mất dữ liệu không thể đảo ngược. | Xây dựng backup/khôi phục có kiểm soát theo mức độ nhạy cảm; thử nghiệm định kỳ. |

## 8. Tình huống thiết kế: khóa ký cho dịch vụ thanh toán

Một hệ thống có **Payment Service** phát hành sự kiện thanh toán và **Ledger Service** tiếp nhận:

1. Payment Service sở hữu key pair ký số **P1**; private key đặt trong KMS và chỉ danh tính workload của Payment Service có quyền ký.
2. Public key P1 được phát hành qua kênh tin cậy với **key ID**. Ledger Service lưu hoặc lấy public key từ nguồn đã xác thực.
3. Khi có sự kiện, Payment Service ký dữ liệu đã chuẩn hóa gồm transaction ID, số tiền, loại tiền, thời gian và phiên bản thông điệp. Ledger Service kiểm tra chữ ký, key ID, tuổi thông điệp và cơ chế chống phát lại trước khi ghi sổ.
4. Khi xoay sang **P2**, Ledger Service nhận public key P2 trước khi Payment Service bắt đầu ký bằng private key P2. Khóa P1 chỉ tiếp tục được chấp nhận trong khoảng thời gian chính sách cho phép.
5. Nếu private key P1 bị nghi lộ, quản trị viên vô hiệu hóa quyền ký P1, thông báo và cập nhật chính sách xác minh; đội vận hành đối soát các sự kiện trong thời gian ảnh hưởng.

Cặp khóa giúp xác minh tính toàn vẹn và nguồn ký của sự kiện; **không thay thế** xác thực dịch vụ, phân quyền nghiệp vụ, chống phát lại, kiểm tra số tiền hoặc mã hóa dữ liệu nhạy cảm.

## 9. Ghi nhớ nhanh

- **Private key là bí mật cần kiểm soát; public key được chia sẻ nhưng phải xác thực đúng chủ sở hữu.**
- Key pair của thuật toán **ký**, **mã hóa** và **thỏa thuận khóa** có công dụng khác nhau, không tự dùng thay thế cho nhau.
- KMS/HSM giúp quản lý và cô lập thao tác với private key; quyền gọi API sử dụng khóa cũng phải được bảo vệ và kiểm toán.
- Xoay vòng, thu hồi và hủy khóa phải xét đến token, chữ ký và dữ liệu lịch sử đang phụ thuộc vào từng phiên bản khóa.
- Hệ thống an toàn cần kết hợp bất đối xứng với mã hóa đối xứng, kiểm soát truy cập, quản lý danh tính, ghi log và kế hoạch ứng phó sự cố.
