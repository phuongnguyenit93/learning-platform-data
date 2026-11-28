# Key pair generation – Sinh cặp khóa trong mật mã bất đối xứng

**Key pair generation** (sinh cặp khóa) là quá trình tạo một **private key (khóa bí mật)** và **public key (khóa công khai)** có quan hệ toán học theo thuật toán bất đối xứng được chọn. Private key được giữ kín và bảo vệ chặt chẽ; public key có thể phân phối nhưng cần xác thực nguồn gốc. Sinh khóa phải dùng đúng thuật toán, tham số và nguồn ngẫu nhiên mật mã để việc biết public key không cho phép thực tế suy ra private key.

Trong chương **Mật mã bất đối xứng** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, sinh cặp khóa là **điểm khởi đầu của vòng đời khóa**: tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy. Chất lượng khâu tạo khóa ảnh hưởng trực tiếp đến bảo mật chữ ký số, xác thực danh tính, trao đổi khóa, mã hóa bất đối xứng và các hệ thống có KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán.

> **Nguyên tắc:** Không phải cứ có hai chuỗi byte gọi là private/public key là đã có một cặp khóa an toàn. Chúng phải được tạo theo thuật toán chuẩn, từ nguồn entropy đủ mạnh, có ràng buộc mục đích sử dụng và được quản lý xuyên suốt vòng đời.

## 1. Key pair được tạo ra như thế nào?

Cách tạo phụ thuộc họ thuật toán:

- **RSA:** thuật toán sinh khóa chọn các số nguyên tố đủ lớn theo quy trình an toàn, tính modulus và các tham số khóa công khai/bí mật. Việc chọn, kiểm tra số nguyên tố, bảo đảm các điều kiện toán học và tạo các tham số CRT phải do thư viện được kiểm chứng thực hiện.
- **Mật mã đường cong elliptic (EC):** private key thường là một giá trị vô hướng bí mật hợp lệ trong miền tham số; public key được tính từ phép nhân điểm cơ sở với giá trị đó. Điều này không đồng nghĩa có thể suy private key một cách khả thi từ public key.
- **Ed25519/X25519:** các thuật toán dựa trên Curve25519 dùng cách biểu diễn và xử lý vật liệu bí mật riêng theo đặc tả. Ed25519 phục vụ **chữ ký số**, X25519 phục vụ **thỏa thuận khóa**. Không tự tái sử dụng byte khóa cho hai thuật toán vì tên và kích thước khóa trông tương tự.

Cặp khóa **không nhất thiết** chỉ dùng được cho một công dụng về mặt toán học, nhưng mỗi **đối tượng khóa được vận hành** nên có **mục đích và chính sách rõ ràng**. Việc dùng chung một RSA key pair để vừa ký vừa giải mã thường làm phức tạp phân quyền, xoay vòng và xử lý sự cố; nên tách khóa theo chức năng khi thiết kế hệ thống.

### 1.1. So sánh các lựa chọn thường gặp

| Thuật toán / tham số | Mục đích chính | Ví dụ chọn khi nào | Điểm cần lưu ý lúc sinh |
| --- | --- | --- | --- |
| **RSA-3072** | Chữ ký RSA-PSS hoặc mã hóa RSA-OAEP qua cấu hình thích hợp | Cần tương thích với hệ thống RSA | Sinh bằng CSPRNG và thư viện chuẩn; khóa lớn, sinh chậm hơn EC; tách usage ký/giải mã khi có thể. |
| **ECDSA P-256** | Ký và xác minh chữ ký | Giao thức/hệ sinh thái yêu cầu ECDSA | Chọn **named curve** đúng; cần quản lý nonce khi ký, khác với randomness khi sinh key pair. |
| **Ed25519** | Ký và xác minh chữ ký | API, token, bản ghi cần chữ ký nhỏ và giao thức hỗ trợ | Tham số gần như cố định; không dùng như khóa mã hóa hay ECDH. |
| **X25519** | Thỏa thuận bí mật chung (ECDH) | Thiết lập khóa phiên theo giao thức hỗ trợ | Cần dẫn xuất khóa bằng KDF và xác thực peer; key agreement không tự xác thực danh tính. |
| **Các thuật toán hậu lượng tử theo chuẩn được áp dụng** | Chữ ký hoặc cơ chế đóng gói khóa, tùy thuật toán | Chính sách chuyển đổi mật mã yêu cầu | Cần chọn loại thuật toán và định dạng theo chuẩn/nhà cung cấp, không coi mọi cặp khóa đều có cùng API. |

Các lựa chọn trên là ví dụ, không phải bảng tương đương tuyệt đối về hiệu năng hoặc cấp bảo mật. **RSA-2048, RSA-3072, P-256, Ed25519, X25519** có ràng buộc chính sách và mức bảo mật khác nhau; cần tham chiếu quy định của hệ thống, khả năng hỗ trợ của thư viện/KMS/HSM và thời gian dữ liệu cần bảo vệ. Không so sánh độ an toàn chỉ bằng số bit của khóa giữa các họ thuật toán.

## 2. Entropy, CSPRNG và điểm yếu sinh khóa

**Entropy** mô tả độ khó dự đoán của nguồn ngẫu nhiên. Một **CSPRNG/DRBG** (bộ sinh số ngẫu nhiên mật mã / bộ sinh bit ngẫu nhiên xác định có bảo đảm mật mã) tạo dữ liệu không thể dự đoán thực tế khi được khởi tạo và vận hành đúng. Sinh private key từ nguồn đoán được có thể khiến toàn bộ hệ thống mất an toàn dù thuật toán RSA, ECDSA hay Ed25519 đúng chuẩn.

### 2.1. Những nguồn không phù hợp

- Đồng hồ hệ thống, timestamp, PID, ID của máy, chuỗi tuần tự hoặc tên người dùng.
- Bộ sinh phục vụ mô phỏng như **java.util.Random** hoặc API random không dành cho mục đích mật mã.
- Chuỗi mật khẩu yếu được chuyển trực tiếp thành private key.
- Seed cố định dùng lại ở nhiều môi trường để “tái lập” key pair.
- Tự trộn nguồn ngẫu nhiên thủ công, tự viết RNG hoặc tự phát minh công thức sinh khóa.

**Java:** sử dụng **java.security.SecureRandom** khi API yêu cầu một nguồn ngẫu nhiên từ ứng dụng, hoặc để provider/KMS/HSM thực hiện sinh khóa theo cơ chế được hỗ trợ. Đừng ép một seed cố định để các lần chạy tạo ra cùng khóa; cách quản lý seed và chất lượng entropy phụ thuộc provider, OS và phần cứng.

### 2.2. Vấn đề trong hệ thống phân tán

Môi trường container, VM, autoscaling, clone image hoặc phục hồi snapshot có thể làm tăng nguy cơ lặp trạng thái RNG khi thiết kế hoặc cấu hình sai. Hệ thống phải dùng nguồn entropy do nền tảng và provider mật mã đáng tin cậy quản lý; bảo đảm khóa được tạo riêng cho từng môi trường và từng danh tính cần bảo vệ.

Không suy luận rằng hai instance có cùng cấu hình sẽ sinh cùng khóa. Ngược lại, **không dựa vào giả định “sẽ không trùng”** nếu ứng dụng dùng bộ sinh giả ngẫu nhiên tự phát triển hoặc seed có thể đoán được.

**Khóa không được “làm mạnh hơn” chỉ bằng cách mã hóa private key yếu sau khi sinh.** Bảo vệ lưu trữ giúp giữ bí mật khóa hiện tại, nhưng không khắc phục được việc không gian khóa ban đầu đã nhỏ.

## 3. Quy trình sinh và đăng ký cặp khóa an toàn

~~~mermaid
flowchart TD
    A["Yêu cầu tạo key pair"] --> B["Xác định usage, thuật toán, tham số và owner"]
    B --> C["Kiểm tra chính sách và quyền tạo khóa"]
    C --> D["Chọn CSPRNG hoặc cơ chế tạo trong KMS/HSM"]
    D --> E["Sinh private key và tính public key"]
    E --> F["Provider kiểm tra tham số và tính hợp lệ theo thuật toán"]
    F --> G["Lưu private key trong vùng bảo vệ"]
    G --> H["Gắn key ID, version, thuật toán, usage, owner và audit"]
    H --> I["Công bố public key/chứng chỉ qua kênh tin cậy"]
    I --> J["Sử dụng, xoay vòng, thu hồi và hủy theo vòng đời"]
~~~

### 3.1. Xác định yêu cầu trước khi bấm Generate

Trước khi tạo khóa, cần trả lời:

1. **Khóa dùng để ký, giải mã hay thỏa thuận khóa?** Chọn thuật toán, padding, giao thức và key usage phù hợp. Không dùng Ed25519 cho mã hóa; không dùng X25519 như chữ ký.
2. **Ai sở hữu khóa?** Gắn workload/service identity, người hoặc tổ chức chịu trách nhiệm, môi trường (dev/staging/prod) và tenant khi cần.
3. **Khóa tồn tại bao lâu?** Đặt thời điểm kích hoạt, hết hạn/đánh giá, lịch xoay, thời gian hỗ trợ dữ liệu và chữ ký lịch sử.
4. **Private key có được xuất không?** Với khóa quan trọng, ưu tiên thiết bị KMS/HSM sinh và bảo vệ non-exportable nếu có thể.
5. **Khóa dùng ở đâu và cần khôi phục thế nào?** Làm rõ vùng, HSM cluster, backup, thiết bị, tình huống DR, hoặc đặc tính ephemeral của khóa phiên.
6. **Public key sẽ được ai tin cậy?** Chọn phương án đăng ký, chứng chỉ, fingerprint, JWKS hay kênh truyền tin cậy trước khi đưa khóa vào sử dụng.

### 3.2. Tạo khóa và kiểm tra kết quả

Thư viện mật mã phải kiểm tra tính hợp lệ theo thuật toán, ví dụ độ dài khóa, miền tham số/đường cong và quan hệ toán học giữa public/private key. **Không tự triển khai primality testing, scalar clamping, phép toán đường cong hay mã hóa DER** trừ khi đang xây dựng chính thư viện mật mã chuyên dụng với quy trình đánh giá riêng.

Kết quả sinh key pair cần bao gồm **key ID/phiên bản, thuật toán, key usage, owner và trạng thái** ở lớp quản lý khóa. Public key được công bố qua cơ chế có tính xác thực; private key phải nằm trong ranh giới được bảo vệ.

Đối với khóa xuất ra ngoài provider, có thể thực hiện thao tác thử **ký và xác minh** bằng cặp khóa mới trong môi trường kiểm soát. Với khóa mã hóa, kiểm tra khả năng mã hóa/giải mã theo giao thức cho phép. Nhưng thử nghiệm thành công **không thay thế** xác minh nguồn entropy, key usage, lưu trữ hoặc chủ thể sở hữu.

## 4. Demo Java 17: sinh cặp khóa đúng mục đích

Ví dụ sử dụng **Java Cryptography Architecture (JCA)** với bốn kiểu khóa: Ed25519 ký số, ECDSA P-256, X25519 thỏa thuận khóa và RSA-3072. Ứng dụng chỉ hiển thị **fingerprint public key**, không xuất private key.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;
import java.util.HexFormat;

public class KeyPairGenerationDemo {
    private static String publicFingerprint(KeyPair pair) throws Exception {
        byte[] encoded = pair.getPublic().getEncoded(); // X.509 SPKI dạng DER
        byte[] digest = MessageDigest.getInstance("SHA-256").digest(encoded);
        return HexFormat.of().formatHex(digest);
    }

    public static void main(String[] args) throws Exception {
        // 1. Ed25519: chữ ký số.
        KeyPairGenerator edGen = KeyPairGenerator.getInstance("Ed25519");
        KeyPair signingKey = edGen.generateKeyPair();

        // 2. ECDSA: P-256 là named curve, không tự đặt tham số EC.
        KeyPairGenerator ecGen = KeyPairGenerator.getInstance("EC");
        ecGen.initialize(new ECGenParameterSpec("secp256r1"),
                new SecureRandom());
        KeyPair ecdsaKey = ecGen.generateKeyPair();

        // 3. X25519: key agreement, cần giao thức xác thực/KDF khi sử dụng.
        KeyPairGenerator xGen = KeyPairGenerator.getInstance("X25519");
        KeyPair agreementKey = xGen.generateKeyPair();

        // 4. RSA: chọn 3072 bit cho ví dụ.
        KeyPairGenerator rsaGen = KeyPairGenerator.getInstance("RSA");
        rsaGen.initialize(3072, new SecureRandom());
        KeyPair rsaKey = rsaGen.generateKeyPair();

        // Minh họa kiểm tra chữ ký của cặp Ed25519 vừa sinh.
        byte[] message = "payment-event-123".getBytes(StandardCharsets.UTF_8);
        Signature signer = Signature.getInstance("Ed25519");
        signer.initSign(signingKey.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        Signature verifier = Signature.getInstance("Ed25519");
        verifier.initVerify(signingKey.getPublic());
        verifier.update(message);
        if (!verifier.verify(signature)) {
            throw new IllegalStateException("New key pair failed verification");
        }

        System.out.println("Ed25519 public fingerprint: " +
                publicFingerprint(signingKey));
        System.out.println("P-256 public fingerprint: " +
                publicFingerprint(ecdsaKey));
        System.out.println("X25519 public fingerprint: " +
                publicFingerprint(agreementKey));
        System.out.println("RSA public fingerprint: " +
                publicFingerprint(rsaKey));
    }
}
~~~

**Lưu ý kỹ thuật:**

- Đây là **demo trong bộ nhớ**, minh họa API sinh khóa và kiểm tra cặp ký số. Không ghi khóa bí mật vào console, source, file tạm, log hoặc gửi qua mạng.
- Sử dụng **Java 17+** với provider hỗ trợ Ed25519 và X25519. Nền tảng hoặc cấu hình cryptographic provider khác nhau có thể khác về hỗ trợ thuật toán và định dạng.
- Giá trị fingerprint ở trên là **SHA-256 của encoding SubjectPublicKeyInfo (SPKI)**, không phải chứng chỉ hoặc bằng chứng danh tính. Nếu hệ thống dùng định dạng public key khác, fingerprint có thể khác dù biểu diễn cùng khóa.
- RSA trong ví dụ chỉ **sinh key pair**; khi dùng phải chọn rõ **RSA-PSS** cho ký hoặc **RSA-OAEP** cho mã hóa, không sử dụng RSA thô.
- Đoạn mã không thực hiện X25519 key agreement. Trong ứng dụng thật phải có **peer public key đã được xác thực, KDF và giao thức ngăn MITM**; sinh cặp X25519 là chưa đủ.
- Ví dụ dùng private key trong tiến trình. Với ứng dụng có yêu cầu cao, tạo khóa trong **KMS/HSM**, sử dụng **key ID** qua API và áp dụng cấu hình **non-exportable** khi được hỗ trợ.

### 4.1. Vì sao không sử dụng cùng private key cho mọi thuật toán?

Từng hệ thuật toán có định dạng và cách xử lý khóa riêng. **Ed25519 và X25519** đều liên quan Curve25519 nhưng phục vụ mục đích khác nhau; không coi chúng là hai API có thể tráo đổi trên cùng key pair. Với RSA, mặc dù cùng cấu trúc toán học có thể hỗ trợ nhiều thao tác, tách **RSA signing key** và **RSA decrypt key** giúp thực thi key usage rõ ràng, thu hồi một chức năng mà không phá chức năng khác.

**Entropy của private key** và **nonce của một chữ ký ECDSA** cũng khác nhau. Private key được sinh một lần; ECDSA cần nonce phù hợp cho **mỗi chữ ký** (có thể dùng cơ chế deterministic ECDSA theo chuẩn). Tái sử dụng hoặc làm lộ nonce ECDSA có thể làm lộ private key, ngay cả khi ban đầu key pair được sinh đúng.

## 5. Định dạng, lưu trữ và phân phối sau khi sinh

Sinh khóa chỉ là khởi đầu. Cách biểu diễn và nơi lưu khóa quyết định phần lớn khả năng bảo vệ:

| Đối tượng | Dạng lưu/truyền thường gặp | Bảo vệ cần thiết |
| --- | --- | --- |
| **Public key** | X.509 SubjectPublicKeyInfo (SPKI), PEM public key, JWK/JWKS theo giao thức | Đảm bảo tính toàn vẹn và xác thực nguồn công bố; public key không phải secret. |
| **Private key** | PKCS#8, KeyStore hoặc đối tượng khóa nội bộ của HSM/KMS | Hạn chế xuất, mã hóa khi lưu, ACL chặt, kiểm soát bản sao và thao tác ký/giải mã. |
| **Chứng chỉ X.509** | Chứa public key và thông tin chứng thực | Xác minh chuỗi tin cậy, tên/định danh, thời hạn và điều kiện sử dụng. |
| **Key ID / kid** | Định danh tham chiếu khóa và phiên bản | Phải quản lý duy nhất trong phạm vi áp dụng; không tự chứng minh khóa đáng tin. |
| **Fingerprint** | Giá trị băm của encoding public key/chứng chỉ theo quy ước | Dùng đối chiếu qua kênh đáng tin; bản thân hash không xác nhận chủ sở hữu. |

**PEM là cách đóng gói/biểu diễn**, không phải cơ chế bảo vệ bí mật tự động. Một private key ở dạng PEM không mã hóa vẫn là dữ liệu cực kỳ nhạy cảm. Nếu phải lưu hoặc xuất private key, cần định nghĩa cụ thể cơ chế mã hóa khi lưu, quyền truy cập, backup, luồng cấp phát và kế hoạch hủy; tốt nhất tránh xuất ra khỏi ranh giới HSM/KMS khi nhu cầu không bắt buộc.

**Public key và chứng chỉ khác nhau.** Cặp khóa vừa được tạo chưa có nghĩa đã có chứng chỉ đáng tin: cần đăng ký, xác thực sở hữu và/hoặc qua CA để ràng buộc public key với danh tính theo chính sách. Tương tự, đăng khóa vào **JWKS** hoặc đặt trường **kid** không tự tạo niềm tin nếu nguồn JWKS bị giả mạo.

## 6. Sinh khóa trong KMS/HSM

**KMS (Key Management Service)** cung cấp API quản lý vòng đời khóa, điều phối chính sách và ghi nhật ký. **HSM (Hardware Security Module)** là thiết bị chuyên dụng có cơ chế chống truy cập trái phép vào key material và thực hiện các phép toán mật mã trong ranh giới bảo vệ. Một KMS có thể dùng HSM phía sau, nhưng khả năng thực tế của từng nhà cung cấp khác nhau.

Quy trình điển hình:

1. Quản trị viên hoặc hệ thống điều phối được cấp quyền yêu cầu **create asymmetric key** với thuật toán, key usage, khu vực/môi trường và chính sách thích hợp.
2. KMS/HSM sinh private key trong ranh giới quản lý và, nếu hỗ trợ, bảo đảm **private key không thể xuất** dưới dạng thô.
3. Public key được xuất để phân phối, phát hành chứng chỉ hoặc đăng vào JWKS theo kênh tin cậy.
4. Ứng dụng dùng **key ID/phiên bản** gọi API **Sign**, **Decrypt** hoặc thao tác phù hợp với thuật toán được cho phép; mỗi quyền phải được kiểm soát riêng.
5. Nhật ký ghi danh tính caller, key ID, hành động, thời điểm, kết quả và các thuộc tính không nhạy cảm cần thiết cho kiểm toán.

**Không được mặc định mọi KMS đều hỗ trợ mọi thuật toán, mọi loại key pair hoặc dùng một khóa cho cả ký và giải mã.** Nhiều KMS giới hạn mục đích của khóa ngay lúc tạo. Một số nền tảng có thể cho nhập key material, xuất khóa dưới cơ chế đặc biệt hoặc thực hiện các bước attestation; phải xem chi tiết chính sách nếu muốn dựa vào các khả năng đó.

### 6.1. “Non-exportable” có đủ an toàn?

**Không.** Kẻ tấn công có quyền gọi API ký có thể tạo **chữ ký trái phép** dù private key chưa bao giờ được xuất; kẻ có quyền giải mã có thể khôi phục dữ liệu. Vì vậy, bảo mật private key bao gồm **quyền sử dụng key**, không chỉ nơi lưu bytes:

- Danh tính workload riêng cho từng dịch vụ, xác thực mạnh và phân quyền **least privilege**.
- Tách người **tạo/quản trị/xóa khóa** với dịch vụ **sử dụng khóa** khi cần.
- Hạn chế theo thuật toán, môi trường, tenant, mục đích và key ID.
- Ghi log/alert lệnh ký hoặc giải mã bất thường; không ghi private key hoặc plaintext nhạy cảm vào audit.
- Có kế hoạch vô hiệu hóa, thu hồi, xoay khóa và điều tra khi danh tính caller bị chiếm đoạt.

## 7. Vòng đời cặp khóa sau khi sinh

| Giai đoạn | Hoạt động nên thực hiện | Rủi ro khi làm sai |
| --- | --- | --- |
| **Tạo (generation)** | Dùng provider/CSPRNG tin cậy; thuật toán, tham số, usage được phê duyệt. | Private key đoán được, yếu hoặc dùng sai thuật toán. |
| **Cấp phát/đăng ký** | Gắn key ID, owner, workload, phiên bản, public key/chứng chỉ đáng tin. | Dùng nhầm khóa, kẻ tấn công tráo public key. |
| **Lưu trữ** | Bảo vệ private key trong KMS/HSM hoặc kho bí mật có ACL; kiểm soát bản sao/backup. | Lộ private key qua Git, file, image, dump, hệ thống sao lưu. |
| **Sử dụng** | Chỉ cho phép API đúng key usage; kiểm tra chữ ký, chứng chỉ, phiên bản và quyền truy cập. | Lạm dụng chức năng ký/giải mã; chấp nhận khóa giả. |
| **Xoay vòng** | Sinh cặp mới, cấp phát public key mới, chuyển traffic và hỗ trợ lịch sử có kiểm soát. | Dịch vụ xác minh nhầm hoặc không giải mã được bản mã cũ. |
| **Thu hồi/ngừng dùng** | Vô hiệu hóa quyền dùng private key; cập nhật nguồn khóa tin cậy/chứng chỉ theo giao thức. | Khóa bị lộ vẫn được chấp nhận hoặc tiếp tục ký. |
| **Hủy** | Hủy private key và các bản sao thuộc phạm vi xử lý sau khi kiểm kê phụ thuộc. | Mất khả năng giải mã dữ liệu còn lưu, hoặc khóa tồn dư chưa được loại bỏ. |

**Xoay khóa ký:** tạo cặp **S2**, công bố public key S2 trước khi phát hành chữ ký mới, rồi chuyển sang private key S2. Có thể tạm giữ public key **S1** để xác minh dữ liệu/token cũ trong cửa sổ cho phép. Khi S1 bị lộ cần đánh giá việc dừng tin cậy sớm và xử lý tác động.

**Xoay khóa giải mã:** nếu private key **E1** dùng để giải mã DEK hoặc dữ liệu cũ, sinh **E2** chưa tự chuyển những bản mã đang phụ thuộc E1. Cần **rewrap/re-encrypt** theo cơ chế được hỗ trợ và kiểm tra backup trước khi hủy E1.

**Key agreement với khóa phiên:** một giao thức có thể sinh **key pair tạm thời (ephemeral)** cho mỗi phiên/handshake để giảm phạm vi ảnh hưởng khi khóa lâu dài bị lộ; tuy nhiên các thuộc tính như **forward secrecy** phụ thuộc vào toàn bộ giao thức và việc xóa bí mật phiên, không chỉ việc chọn X25519.

## 8. Liên hệ giữa key pair và envelope encryption

**Envelope encryption** thường dùng **DEK đối xứng** (ví dụ AES-GCM) để mã hóa dữ liệu, còn một **KEK** hoặc cơ chế bảo vệ khóa đảm nhiệm việc lưu/di chuyển DEK an toàn. Key pair có thể tham gia khi cần **bảo vệ/trao đổi khóa giữa hai bên**:

~~~mermaid
flowchart LR
    A["Sinh DEK đối xứng ngẫu nhiên"] --> D["AES-GCM mã hóa dữ liệu"]
    A --> W["Bảo vệ DEK cho người nhận bằng cơ chế bất đối xứng/lai"]
    PUB["Public key đã xác thực của người nhận"] --> W
    W --> WD["DEK được bảo vệ"]
    D --> CT["Ciphertext + nonce + tag"]
    WD --> PKG["Gói dữ liệu lưu/truyền"]
    CT --> PKG
    PKG --> U["Người nhận dùng private key theo giao thức"]
    U --> DEC["Khôi phục DEK rồi giải mã dữ liệu"]
~~~

Với RSA-OAEP, dữ liệu mã hóa trực tiếp bằng RSA bị giới hạn kích thước; thường chỉ bảo vệ khóa đối xứng nhỏ. Với giao thức lai hiện đại, có thể dùng **HPKE** hoặc cơ chế tương ứng để xác lập/bảo vệ vật liệu khóa. Với X25519, việc tạo bí mật chung phải đi cùng **KDF và xác thực bên kia**.

**Không phải mọi hệ thống envelope encryption đều có key pair.** Nhiều KMS dùng **KEK đối xứng** để wrap DEK; key pair là một phương án bổ sung tùy kiến trúc và yêu cầu phân phối khóa.

## 9. Tình huống triển khai: khóa ký cho dịch vụ thanh toán

Một hệ thống có **Payment Service** phát hành sự kiện và **Ledger Service** xác minh:

1. Chủ hệ thống định nghĩa chính sách **Ed25519 signing key**, owner là Payment Service, private key được sinh trong KMS/HSM hỗ trợ thuật toán và usage tương ứng.
2. KMS trả về **key ID S1** và public key S1; hệ thống phân phối public key qua kênh tin cậy, kèm thông tin định danh khóa để Ledger Service chọn đúng phiên bản.
3. Chỉ danh tính của Payment Service có quyền gọi **Sign** cho S1; quyền tạo hoặc hủy khóa do vai trò quản trị riêng đảm nhiệm.
4. Ledger Service kiểm tra chữ ký, nguồn public key, nội dung giao dịch, định danh bên phát hành, tính mới và quy tắc chống phát lại trước khi ghi sổ.
5. Khi chuyển sang S2, hệ thống tạo và công bố public key S2 trước, chuyển ký mới sang S2, giữ public key S1 trong thời gian chính sách cho phép và sau đó thu hồi tín nhiệm theo yêu cầu.
6. Nếu nghi rò rỉ private key hoặc thông tin định danh dùng API Sign, cô lập quyền sử dụng, ghi nhận phạm vi ảnh hưởng và triển khai quy trình xoay/thu hồi.

**Tính toàn vẹn của sự kiện** không thay thế kiểm soát nghiệp vụ như số tiền, mã giao dịch, chống ghi trùng hoặc xác thực người gọi API. Quản lý key pair gắn với danh tính và kiểm toán là điều kiện cần để chữ ký có ý nghĩa trong hệ thống phân tán.

## 10. Lỗi hay gặp khi sinh cặp khóa

| Sai lầm | Nguy cơ | Hướng xử lý |
| --- | --- | --- |
| Dùng RNG thường hoặc seed từ timestamp | Private key có thể dự đoán được. | Dùng CSPRNG/provider đáng tin hoặc sinh trực tiếp trong KMS/HSM. |
| Dùng một key pair trong dev, staging và prod | Lộ khóa ở môi trường yếu ảnh hưởng prod. | Tạo khóa độc lập theo môi trường và mục đích. |
| Tự triển khai RSA, EC hoặc chuyển Ed25519 ↔ X25519 tùy tiện | Sai thuật toán, sai tham số và khó bảo đảm tính an toàn. | Dùng API chuẩn, thư viện được kiểm chứng, key usage rõ ràng. |
| Sinh RSA quá nhỏ/chọn đường cong không được hỗ trợ | Không đạt mức bảo mật hoặc không tương thích. | Áp dụng chính sách thuật toán/tham số được phê duyệt. |
| Xuất private key vào log, biến môi trường hoặc mã nguồn | Dữ liệu bí mật dễ bị sao chép và lạm dụng. | Không xuất nếu không cần; dùng KMS/HSM, ACL, theo dõi sự cố. |
| Tin rằng public key vừa tạo đã chứng thực danh tính | Chấp nhận khóa bị tráo hoặc khóa sai owner. | Đăng ký/publication qua kênh tin cậy, PKI/chứng chỉ hoặc fingerprint xác minh. |
| Không ghi key ID, usage và phiên bản | Không chọn đúng khóa khi rotate, lỗi xác minh/giải mã. | Lưu metadata và quản lý vòng đời theo phiên bản. |
| Dùng chung key pair để ký và giải mã | Quyền rộng, khó cô lập sự cố và bảo đảm chính sách. | Tách key pair theo chức năng khi có thể. |
| Chỉ bảo vệ file private key nhưng mở quyền API Sign | Kẻ tấn công vẫn ký trái phép. | Phân quyền theo workload, kiểm toán, hạn mức và cảnh báo. |
| Hủy private key giải mã ngay sau rotate | Bản mã/backup cũ mất khả năng khôi phục. | Kiểm kê phụ thuộc, rewrap/re-encrypt và thử khôi phục trước hủy. |
| Nhầm kid/fingerprint với chứng chỉ | Không chứng minh được chủ sở hữu public key. | Xác thực nguồn public key và mối liên hệ với danh tính. |

## 11. Câu hỏi tự kiểm tra

1. Vì sao **CSPRNG/entropy** là yêu cầu nền tảng cho key pair generation?
2. Khác nhau thế nào giữa **Ed25519, ECDSA P-256, X25519 và RSA-3072** về mục đích sử dụng?
3. Sinh một key pair trong ứng dụng Java khác gì với sinh khóa **non-exportable** trong KMS/HSM?
4. Vì sao một public key có fingerprint đúng vẫn chưa tự chứng minh danh tính của bên sở hữu?
5. Khi xoay khóa ký, vì sao đôi khi cần giữ **public key cũ** để xác minh chữ ký?
6. Khi xoay khóa giải mã, điều gì xảy ra nếu hủy private key cũ quá sớm?
7. Vì sao key pair X25519 vừa sinh chưa đủ để chống **man-in-the-middle**?
8. Làm thế nào để ghi log/audit việc sinh khóa mà không làm lộ private key?

**Ghi nhớ:** Key pair generation an toàn đòi hỏi **thuật toán đúng mục đích, tham số đã phê duyệt, nguồn ngẫu nhiên mật mã, bảo vệ private key, định danh và xác thực public key, cùng cơ chế kiểm soát quyền sử dụng**. Một cặp khóa được tạo đúng nhưng cấp phát hoặc lưu trữ sai vẫn có thể gây lộ dữ liệu. Vì vậy phải đưa **KMS/HSM, quản lý phiên bản, xoay vòng, thu hồi, hủy khóa và kiểm toán** vào thiết kế ngay từ lúc sinh khóa.
