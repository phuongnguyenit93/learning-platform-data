# OWASP Cryptographic Storage Cheat Sheet

OWASP Cryptographic Storage Cheat Sheet là hướng dẫn thực hành về cách bảo vệ dữ liệu nhạy cảm khi lưu trữ bằng mật mã. Tài liệu nhấn mạnh việc xác định dữ liệu thực sự cần bảo vệ, chọn thuật toán và thư viện đã được kiểm chứng, sử dụng chế độ mã hóa có xác thực, quản lý khóa an toàn và tránh tự xây dựng thuật toán mật mã.

Trong quản lý khóa mật mã, mã hóa dữ liệu chỉ là một phần của bài toán. Một hệ thống có thể dùng AES mạnh nhưng vẫn thất bại nếu khóa được hard-code trong source code, nonce bị tái sử dụng, quyền giải mã quá rộng hoặc backup không còn truy cập được khóa. Vì vậy, hướng dẫn về cryptographic storage phải được kết nối với vòng đời khóa, KMS/HSM, envelope encryption, kiểm soát truy cập, backup, rotation và audit.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích mục tiêu và phạm vi của OWASP Cryptographic Storage Cheat Sheet.
- Xác định dữ liệu nào cần mã hóa và chọn đúng biện pháp bảo vệ.
- Phân biệt mã hóa, hashing, MAC và chữ ký số.
- Chọn thuật toán, chế độ mã hóa và thư viện phù hợp.
- Sử dụng AEAD, nonce/IV và associated data đúng cách.
- Thiết kế lưu trữ khóa, phân quyền, rotation và backup.
- Nhận diện các lỗi thường gặp như ECB, hard-coded key, nonce reuse và tự viết crypto.
- Xây dựng quy trình kiểm thử và rà soát cryptographic storage.

## 2. Vai trò của OWASP Cryptographic Storage Cheat Sheet

OWASP Cheat Sheet Series cung cấp hướng dẫn kỹ thuật ngắn gọn để giúp đội phát triển và bảo mật tránh các lỗi triển khai phổ biến. Cryptographic Storage Cheat Sheet tập trung vào việc bảo vệ dữ liệu nhạy cảm được lưu trong ứng dụng, cơ sở dữ liệu, file, object storage hoặc các hệ thống lưu trữ khác.

Đây là hướng dẫn thực hành, không phải một thuật toán mật mã, giao thức chứng nhận hay tiêu chuẩn tuân thủ độc lập. Khi áp dụng, cần kết hợp hướng dẫn của OWASP với threat model, yêu cầu pháp lý, tiêu chuẩn của tổ chức, tài liệu của thư viện và cấu hình KMS/HSM đang sử dụng.

Các nguyên tắc cốt lõi:

1. Không lưu dữ liệu nhạy cảm nếu không có nhu cầu nghiệp vụ.
2. Dùng thuật toán và thư viện mật mã đã được kiểm chứng.
3. Chọn đúng primitive cho mục tiêu: mã hóa để giữ bí mật, MAC/chữ ký để xác thực toàn vẹn, hashing để tạo dấu vết một chiều.
4. Ưu tiên authenticated encryption để phát hiện dữ liệu bị sửa.
5. Tách khóa khỏi dữ liệu và bảo vệ khóa bằng cơ chế quản lý phù hợp.
6. Giới hạn quyền sử dụng khóa, theo dõi hoạt động và có kế hoạch rotation/recovery.

## 3. Bắt đầu bằng phân loại dữ liệu

Không phải mọi dữ liệu đều cần mã hóa ở tầng ứng dụng. Trước khi chọn thuật toán, hãy xác định dữ liệu nào nhạy cảm, ai có thể truy cập, hậu quả khi bị lộ và dữ liệu tồn tại ở đâu.

Ví dụ về dữ liệu có thể cần bảo vệ:

- Thông tin định danh cá nhân và dữ liệu tài chính.
- Token, API credential, client secret và thông tin xác thực.
- Dữ liệu sức khỏe hoặc dữ liệu thuộc hợp đồng.
- Private key, seed, secret và vật liệu mật mã.
- Dữ liệu nghiệp vụ có giá trị cao hoặc có yêu cầu bảo mật theo quy định.

Phân loại dữ liệu cần bao gồm bản chính và các bản sao: cache, log, file tạm, export, backup, snapshot, replica, message queue và môi trường phân tích. Mã hóa một bảng trong database không bảo vệ bản CSV đã xuất ra thư mục dùng chung.

Một bảng phân loại đơn giản:

| Nhóm dữ liệu | Ví dụ | Kiểm soát tham khảo |
|---|---|---|
| Công khai | Nội dung được phép công bố | Kiểm soát toàn vẹn và thay đổi phù hợp |
| Nội bộ | Cấu hình không chứa secret | Access control, bảo vệ lưu trữ theo rủi ro |
| Nhạy cảm | Thông tin khách hàng, giao dịch | Mã hóa khi lưu/truyền, phân quyền và audit |
| Bí mật có quyền truy cập | Password, token, private key | Secret manager/KMS/HSM, hạn dùng, rotation và audit |

Mức phân loại cần phản ánh tác động khi dữ liệu bị lộ hoặc bị sửa. Không dùng một nhãn chung "encrypted" để thay thế việc xác định owner, retention và quyền truy cập.

## 4. Chọn biện pháp phù hợp với mục tiêu

Mật mã có nhiều primitive và mỗi loại giải quyết một vấn đề khác nhau.

| Cơ chế | Mục tiêu | Ví dụ sử dụng |
|---|---|---|
| Encryption | Giữ bí mật, có thể khôi phục plaintext bằng khóa | Mã hóa hồ sơ, file, backup |
| Hash | Tạo giá trị một chiều để so sánh hoặc kiểm tra | Hash nội dung, fingerprint |
| Password hashing | Lưu password theo cách chống dò đoán ngoại tuyến | Argon2id, scrypt, bcrypt, PBKDF2 |
| MAC/HMAC | Xác thực nguồn và toàn vẹn bằng secret dùng chung | Xác thực message nội bộ |
| Digital signature | Xác thực và kiểm tra toàn vẹn bằng cặp khóa bất đối xứng | Ký artifact, token, tài liệu |

Không mã hóa password để có thể giải mã lại khi đăng nhập. Password người dùng cần được lưu bằng password hashing chuyên dụng với salt riêng và cost phù hợp. Không dùng một hàm hash nhanh như SHA-256 đơn thuần để lưu password.

Ngược lại, dữ liệu nghiệp vụ cần đọc lại như số tài khoản hoặc hồ sơ khách hàng có thể cần encryption. Hashing một chiều không đáp ứng yêu cầu khôi phục dữ liệu.

## 5. Không tự xây dựng thuật toán mật mã

Không tự thiết kế cipher, mode, padding, key exchange, MAC construction hoặc protocol riêng. Những thiết kế này rất dễ sai ở các chi tiết khó nhận biết như nonce, padding oracle, xác thực thông điệp, quản lý khóa và xử lý lỗi.

Ưu tiên:

- Thư viện mật mã được sử dụng rộng rãi và được duy trì.
- API cấp cao có cấu hình an toàn mặc định.
- Primitive chuẩn và chế độ hoạt động đã được phân tích công khai.
- Tích hợp KMS/HSM hoặc secret manager cho việc bảo vệ và sử dụng khóa.
- Phiên bản thư viện được vá và có quy trình theo dõi lỗ hổng.

Không tự viết thuật toán vì muốn giảm dependency hoặc tối ưu vài dòng code. Nếu cần một primitive mà thư viện hiện tại không hỗ trợ, hãy đánh giá thư viện khác đã được kiểm chứng thay vì tự cài đặt.

## 6. Thuật toán mã hóa đối xứng

Mã hóa đối xứng sử dụng cùng một khóa bí mật để mã hóa và giải mã. Đây là lựa chọn phổ biến để bảo vệ dữ liệu có kích thước lớn vì hiệu năng tốt.

Các lựa chọn hiện đại thường gồm:

- AES với khóa 128 hoặc 256 bit, dùng chế độ phù hợp.
- ChaCha20-Poly1305 trong môi trường hoặc nền tảng phù hợp.

Độ dài khóa chỉ là một yếu tố. Chọn AES-256 nhưng dùng ECB, tái sử dụng nonce của GCM hoặc lưu khóa cạnh ciphertext vẫn tạo ra thiết kế không an toàn.

Không dùng DES hoặc RC4 cho hệ thống mới. 3DES đã lỗi thời và không nên là lựa chọn cho thiết kế mới. Nếu phải duy trì dữ liệu legacy, cần có kế hoạch chuyển đổi sang thuật toán và chế độ hiện đại.

## 7. Chọn chế độ mã hóa

Chế độ mã hóa quyết định cách block cipher xử lý dữ liệu dài hơn một block và các thuộc tính bảo mật đi kèm.

| Chế độ | Đặc điểm | Khuyến nghị |
|---|---|---|
| AES-GCM | Authenticated encryption, bảo vệ bí mật và toàn vẹn | Lựa chọn phổ biến cho thiết kế mới khi quản lý nonce đúng |
| ChaCha20-Poly1305 | Authenticated encryption dạng stream cipher kết hợp MAC | Lựa chọn hiện đại khi thư viện/nền tảng hỗ trợ |
| AES-CCM | AEAD, thường gặp trong một số giao thức và thiết bị | Dùng theo profile và thư viện đã được kiểm chứng |
| AES-CBC | Chỉ cung cấp confidentiality, không tự xác thực ciphertext | Chỉ dùng khi có yêu cầu tương thích và bổ sung Encrypt-then-MAC đúng cách |
| AES-CTR | Biến block cipher thành stream-like mode, không tự xác thực | Chỉ dùng với MAC độc lập và quản lý counter đúng |
| AES-ECB | Mã hóa từng block độc lập, để lộ mẫu dữ liệu lặp | Không dùng để bảo vệ dữ liệu ứng dụng |

Ưu tiên AEAD (Authenticated Encryption with Associated Data). AEAD vừa mã hóa vừa xác thực ciphertext và associated data, giúp ứng dụng phát hiện dữ liệu bị sửa hoặc bị gắn nhầm metadata.

Nếu buộc dùng CBC hoặc CTR trong hệ thống legacy, phải xây dựng MAC riêng với khóa tách biệt và xác minh MAC trước khi giải mã theo mô hình Encrypt-then-MAC. Tránh tự ghép encryption và MAC theo thứ tự tùy ý. Lỗi padding hoặc phản hồi khác nhau trước khi xác minh MAC có thể tạo padding oracle.

## 8. Nonce, IV và yêu cầu không tái sử dụng

Nonce hoặc IV là tham số đi kèm thao tác mã hóa. Chúng thường không cần giữ bí mật nhưng phải đáp ứng yêu cầu của mode.

Với AES-GCM:

- Nonce 96 bit là kích thước phổ biến.
- Không được tái sử dụng cùng nonce với cùng một khóa.
- Nonce cần được tạo hoặc cấp phát bằng cơ chế bảo đảm tính duy nhất theo thiết kế.
- Ciphertext phải đi kèm nonce để giải mã.
- Tag xác thực phải được giữ nguyên và kiểm tra trước khi sử dụng plaintext.

Nonce reuse trong GCM có thể phá vỡ tính bảo mật và toàn vẹn, cho phép suy ra thông tin hoặc giả mạo tag. Trong hệ thống phân tán, không giả định mỗi process tự sinh nonce là đủ nếu cùng dùng một key và có khối lượng request lớn. Cần thiết kế bộ đếm duy nhất, vùng nonce theo node hoặc cơ chế phân bổ được đồng bộ; đặt giới hạn sử dụng cho mỗi key và rotation trước khi vượt giới hạn an toàn.

Với CBC, IV cần ngẫu nhiên và không đoán trước theo yêu cầu của mode. Không dùng một IV cố định cho mọi bản ghi. Không tái sử dụng IV theo cách làm lộ quan hệ giữa plaintext.

IV/nonce không phải password và không phải key. Có thể lưu cùng ciphertext, nhưng phải giữ nguyên định dạng và không được tự ý thay đổi.

## 9. Authenticated encryption và associated data

AEAD cung cấp confidentiality và integrity/authenticity trong một thao tác. Ví dụ AES-GCM tạo ciphertext và authentication tag. Khi giải mã, tag phải được xác minh thành công trước khi ứng dụng sử dụng plaintext.

Associated data (AAD) là metadata được xác thực nhưng không được mã hóa. Có thể dùng AAD để ràng buộc ciphertext với:

- Tenant ID.
- Record ID.
- Loại dữ liệu.
- Phiên bản schema.
- Mục đích sử dụng hoặc context của bản ghi.

Ví dụ, ciphertext của hóa đơn được tạo với AAD gồm tenant và invoice ID. Khi một attacker sao chép ciphertext sang tenant khác, thao tác giải mã với AAD khác sẽ thất bại.

AAD không bí mật và không thay thế authorization. Không đưa dữ liệu cá nhân hoặc secret vào AAD chỉ vì nó được xác thực. Cần chuẩn hóa encoding, thứ tự trường và phiên bản schema để producer và consumer tạo đúng cùng một byte sequence.

Khi authentication tag không hợp lệ, ứng dụng phải từ chối dữ liệu và không trả plaintext một phần. Không bỏ qua lỗi tag hoặc tự thử chế độ không xác thực như fallback.

## 10. Ví dụ cấu trúc dữ liệu đã mã hóa

Một record có thể lưu các trường sau:

| Trường | Mục đích | Có cần bí mật? |
|---|---|---|
| ciphertext | Dữ liệu đã mã hóa và tag nếu API gộp tag | Có thể công khai nhưng cần kiểm soát truy cập |
| nonce | Tham số để giải mã | Không, nhưng phải giữ nguyên |
| algorithm | Nhận diện thuật toán/chế độ | Không |
| key_id | Định danh khóa dùng để mã hóa | Thường không |
| key_version | Phiên bản khóa | Không |
| aad_schema | Phiên bản cấu trúc AAD | Không |
| context | Metadata cần tái tạo AAD | Tùy trường, tránh dữ liệu nhạy cảm |

Không lưu key material cùng record. key_id và key_version giúp chọn đúng khóa mà không phải thử mọi khóa trong hệ thống. Metadata cần được xác thực hoặc lấy từ nguồn đáng tin cậy để attacker không thể tùy ý điều khiển key reference.

## 11. Ví dụ AES-GCM trong Java

Ví dụ sau minh họa cách mã hóa bằng JCA. Khóa được truyền vào từ một nguồn quản lý khóa an toàn; ví dụ không tạo hoặc lưu key material trong source code.

~~~java
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.nio.ByteBuffer;

final class AesGcmStorage {
    private static final int NONCE_LENGTH = 12;
    private static final int TAG_LENGTH_BITS = 128;
    private static final SecureRandom RANDOM = new SecureRandom();

    static byte[] encrypt(
            SecretKey key, byte[] plaintext, byte[] aad)
            throws GeneralSecurityException {
        byte[] nonce = new byte[NONCE_LENGTH];
        RANDOM.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.ENCRYPT_MODE,
            key,
            new GCMParameterSpec(TAG_LENGTH_BITS, nonce)
        );
        cipher.updateAAD(aad);
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);

        return ByteBuffer.allocate(
            nonce.length + ciphertextAndTag.length
        ).put(nonce).put(ciphertextAndTag).array();
    }

    static byte[] decrypt(
            SecretKey key, byte[] stored, byte[] aad)
            throws GeneralSecurityException {
        ByteBuffer input = ByteBuffer.wrap(stored);
        if (input.remaining() <= NONCE_LENGTH) {
            throw new GeneralSecurityException("Invalid encrypted payload");
        }

        byte[] nonce = new byte[NONCE_LENGTH];
        input.get(nonce);
        byte[] ciphertextAndTag = new byte[input.remaining()];
        input.get(ciphertextAndTag);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
            Cipher.DECRYPT_MODE,
            key,
            new GCMParameterSpec(TAG_LENGTH_BITS, nonce)
        );
        cipher.updateAAD(aad);
        return cipher.doFinal(ciphertextAndTag);
    }
}
~~~

Đây là ví dụ minh họa API JCA. Ứng dụng thực tế cần lấy SecretKey qua KMS/HSM hoặc cơ chế key provider được phê duyệt, lưu key_id/version cùng payload và xử lý lỗi xác thực an toàn. Ví dụ dùng nonce ngẫu nhiên 96 bit; với hệ thống có lưu lượng lớn hoặc nhiều node cùng dùng một key, phải có thiết kế bảo đảm nonce không lặp và giới hạn số lần sử dụng theo hướng dẫn của thư viện/thuật toán. Không dùng đoạn mã này thay cho đánh giá nonce strategy ở quy mô production.

## 12. Mã hóa bất đối xứng và hybrid encryption

Mã hóa bất đối xứng sử dụng public key để mã hóa hoặc thiết lập bí mật và private key để giải mã hoặc hoàn tất quy trình tương ứng. Nó phù hợp cho trao đổi khóa và một số trường hợp xác thực, nhưng thường không phải lựa chọn hiệu quả để mã hóa trực tiếp dữ liệu lớn.

Thiết kế phổ biến là hybrid encryption:

1. Sinh một DEK ngẫu nhiên bằng CSPRNG.
2. Mã hóa dữ liệu bằng AEAD với DEK.
3. Bọc DEK bằng public key hoặc KEK được quản lý.
4. Lưu ciphertext, nonce, tag, encrypted DEK và key reference.
5. Khi đọc, xác thực principal, mở DEK bằng private key/KEK và giải mã ciphertext.

Với RSA, dùng padding scheme hiện đại như OAEP khi phù hợp; không dùng raw RSA hoặc padding cũ cho thiết kế mới. Với hệ thống dùng key agreement, cần protocol và thư viện đã được kiểm chứng, có xác thực danh tính và bảo vệ chống tấn công hạ cấp.

Không dùng public key encryption để thay thế mọi yêu cầu về chữ ký số. Mã hóa và ký số có mục tiêu khác nhau.

## 13. Hashing và lưu password

Hash là hàm một chiều, không được thiết kế để khôi phục dữ liệu gốc. Khi lưu password, dùng password hashing chuyên dụng có salt riêng cho mỗi password và cost đủ cao để làm chậm dò đoán.

Các lựa chọn thường dùng gồm:

- Argon2id khi thư viện và môi trường hỗ trợ.
- scrypt.
- bcrypt.
- PBKDF2 với cấu hình phù hợp yêu cầu và môi trường.

Salt không cần bí mật và phải khác nhau giữa các password. Có thể lưu salt cùng password hash. Pepper là secret bổ sung tùy kiến trúc; nếu dùng, phải lưu tách khỏi database, ví dụ trong secret manager hoặc KMS.

Không dùng AES để mã hóa password rồi lưu khóa giải mã trong cùng hệ thống. Nếu ứng dụng cần xác thực password, so sánh kết quả password hashing theo API an toàn của thư viện.

Đối với dữ liệu cần khôi phục, password hashing không phù hợp; dùng encryption với key management đúng cách.

## 14. Sinh khóa và vật liệu ngẫu nhiên

Khóa phải được sinh bằng cryptographically secure pseudorandom number generator (CSPRNG) hoặc được tạo bên trong KMS/HSM theo cơ chế được phê duyệt.

Không dùng:

- Math.random() hoặc PRNG phục vụ mô phỏng.
- Timestamp, counter đơn giản hoặc tên ứng dụng làm key.
- Hash của password hoặc chuỗi cố định làm khóa trực tiếp.
- Giá trị mặc định được hard-code trong source code.
- Một key pair được chia sẻ rộng giữa các ứng dụng không liên quan.

Kích thước khóa và thuật toán phải theo policy hiện hành, mục đích sử dụng, thư viện và yêu cầu tương thích. Không tự cắt hoặc nối chuỗi để tạo key bytes. Với password-based encryption, dùng KDF phù hợp thay vì dùng password trực tiếp làm AES key.

## 15. Quản lý khóa: tách khóa khỏi dữ liệu

Khóa mã hóa không nên được lưu cùng ciphertext trong cùng một miền truy cập. Nếu attacker lấy được cả hai, encryption có thể không còn bảo vệ dữ liệu.

Các lựa chọn lưu trữ và bảo vệ:

| Cơ chế | Vai trò | Lưu ý |
|---|---|---|
| KMS | Quản lý key resource, policy, version và thao tác mật mã | Giới hạn principal, scope và operation |
| HSM | Bảo vệ key material trong ranh giới phần cứng và thực hiện thao tác mật mã | Quản lý partition, quorum, backup và quyền quản trị |
| Secret manager | Lưu secret/credential và phân phối cho workload | Phân quyền đọc, rotation và audit |
| OS keystore / protected file | Lưu khóa trong môi trường máy chủ có kiểm soát | Bảo vệ file permission, backup và quyền quản trị host |
| Envelope encryption | Dùng DEK mã hóa dữ liệu, KEK bảo vệ DEK | Tách quyền sử dụng DEK khỏi quyền quản trị KEK |

Không coi biến môi trường hoặc file cấu hình là vault. Chúng có thể là phương thức chuyển secret vào process, nhưng cần kiểm soát quyền đọc process, dump, log, image và orchestration platform.

## 16. Envelope encryption

Envelope encryption là mô hình dùng DEK mã hóa dữ liệu và KEK bảo vệ DEK. Ứng dụng có thể mã hóa dữ liệu cục bộ bằng DEK trong khi KMS quản lý KEK và thực hiện thao tác wrap/unwrap.

Lợi ích:

- Giảm số lần phải gọi KMS cho mỗi block dữ liệu.
- Tách khóa dữ liệu khỏi khóa bảo vệ khóa.
- Hỗ trợ rotation KEK bằng rewrap encrypted DEK.
- Giới hạn quyền: workload chỉ cần thao tác phù hợp với chức năng.
- Tạo metadata để truy vết key ID và version.

Envelope encryption không tự giải quyết mọi rủi ro. Plaintext DEK cần được bảo vệ trong bộ nhớ, giới hạn thời gian tồn tại và không được ghi log. Cache DEK cần policy về TTL, số lượng dữ liệu xử lý và xử lý khi key bị compromise.

Khi KEK rotation, có thể rewrap DEK nếu DEK vẫn an toàn. Khi DEK bị lộ, chỉ rewrap không đủ; cần tạo DEK mới và re-encrypt dữ liệu.

## 17. Phân quyền sử dụng khóa

Quyền đọc metadata, encrypt, decrypt, sign, export, rotate, disable và destroy cần được phân biệt. Không cấp quyền quản trị toàn bộ chỉ vì ứng dụng cần một thao tác mật mã.

Áp dụng:

- Mỗi workload có danh tính riêng.
- Cấp quyền ở resource scope nhỏ nhất.
- Chỉ cho phép thao tác cần thiết.
- Tách quyền quản trị policy khỏi quyền sử dụng khóa.
- Dùng quyền tạm thời cho tác vụ migration hoặc recovery.
- Có phê duyệt độc lập cho export, policy change hoặc destroy nếu mức rủi ro yêu cầu.
- Thu hồi role binding khi workload hoặc nhân viên không còn nhu cầu.

Ví dụ, dịch vụ ghi dữ liệu có thể chỉ cần encrypt hoặc wrap; dịch vụ đọc dữ liệu mới cần decrypt hoặc unwrap. Không mặc định mọi consumer cần cả hai quyền.

## 18. Rotation, revocation và hủy khóa

Khóa cần có vòng đời được quản lý:

1. Tạo khóa theo thuật toán và purpose được phê duyệt.
2. Gán owner, metadata, scope và policy.
3. Cấp quyền sử dụng cho consumer.
4. Theo dõi hoạt động và trạng thái.
5. Rotation theo lịch hoặc sự kiện.
6. Disable hoặc revoke khi có sự cố hoặc không còn nhu cầu.
7. Retire và destroy khi đã đáp ứng điều kiện dữ liệu, backup, retention và phê duyệt.

Rotation phải tính đến dữ liệu đã mã hóa bằng version cũ. Không destroy version cũ trước khi xác minh ciphertext, backup và archive không còn phụ thuộc vào nó hoặc đã có phương án khôi phục.

Nếu key material bị lộ, cần xử lý như sự cố bảo mật: giới hạn quyền, tạo khóa mới, đánh giá dữ liệu bị ảnh hưởng và rewrap/re-encrypt theo loại khóa. Chỉ đổi version hiện hành mà không thu hồi credential hoặc quyền bị lộ là chưa đủ.

## 19. Backup và recovery

Backup của dữ liệu mã hóa cần giữ đủ metadata và khả năng truy cập key version liên quan. Backup ciphertext mà không có khóa cần thiết có thể trở thành dữ liệu không thể khôi phục.

Kiểm soát cần có:

- Backup key metadata và cấu hình policy theo quy trình an toàn.
- Bảo vệ backup của key material theo cơ chế KMS/HSM và dual control khi cần.
- Tách quyền quản trị backup khỏi quyền đọc dữ liệu nghiệp vụ.
- Kiểm thử restore trong môi trường cô lập.
- Xác minh dữ liệu khôi phục bằng checksum hoặc kiểm tra nghiệp vụ.
- Giữ version cũ theo retention của backup và archive.
- Ghi audit cho thao tác khôi phục và sử dụng khóa.

Không xuất key material ra file thông thường chỉ để đơn giản hóa backup. Dùng tính năng backup/restore được thiết kế cho KMS/HSM hoặc quy trình bảo vệ khóa tương ứng.

## 20. Lưu trữ dữ liệu và các lớp mã hóa

Mã hóa ở tầng database, disk hoặc cloud storage có thể bảo vệ khi thiết bị hoặc snapshot bị truy cập ngoài môi trường được phép. Tuy nhiên, khi ứng dụng và database đang hoạt động, dữ liệu có thể được giải mã cho principal có quyền.

Mã hóa ở tầng ứng dụng có thể bảo vệ một trường hoặc object trước khi ghi vào database, nhưng làm tăng trách nhiệm quản lý key, nonce, metadata và migration.

Chọn lớp mã hóa dựa trên threat model:

| Lớp | Bảo vệ tốt trước | Giới hạn |
|---|---|---|
| Disk/storage encryption | Mất thiết bị, truy cập raw volume hoặc snapshot ngoài quyền | Không ngăn principal hợp lệ đọc dữ liệu qua ứng dụng |
| Database/TDE | Một số tình huống truy cập file database hoặc backup thô | Database engine vẫn giải mã cho query được phép |
| Application-level encryption | Database operator hoặc dump chỉ thấy ciphertext ở trường được mã hóa | Ứng dụng phải quản lý key, metadata và quyền decrypt |
| Field-level encryption | Bảo vệ trường dữ liệu cụ thể | Tìm kiếm, index và xử lý nghiệp vụ phức tạp hơn |

Các lớp có thể bổ sung cho nhau. Không xem disk encryption là lý do để bỏ qua access control, audit hoặc bảo vệ backup.

## 21. Xử lý lỗi và phản hồi an toàn

Lỗi mật mã cần được xử lý nhất quán:

- Không trả plaintext nếu authentication tag hoặc MAC không hợp lệ.
- Không tiết lộ chi tiết giúp attacker phân biệt padding, key ID hợp lệ hoặc trạng thái secret qua thông báo lỗi.
- Không tự động fallback từ AEAD sang CBC/ECB hoặc chế độ yếu hơn.
- Không thử nhiều key tùy ý nếu metadata key reference bị thiếu hoặc sai.
- Ghi log đủ thông tin điều tra như request ID, key ID không bí mật, operation và error category; không ghi key material hoặc plaintext.
- Tách lỗi authorization, lỗi dữ liệu, lỗi provider và lỗi cấu hình để vận hành xử lý đúng.

Nếu decryption thất bại, ứng dụng nên trả lỗi phù hợp với giao thức và giữ chi tiết kỹ thuật trong log bảo vệ. Không bỏ qua lỗi tag để “cố đọc” dữ liệu.

## 22. Cryptographic agility và tương thích

Cryptographic agility là khả năng thay thuật toán, key size, provider hoặc key version khi yêu cầu bảo mật thay đổi mà không phải viết lại toàn bộ hệ thống.

Thiết kế hỗ trợ agility:

- Lưu algorithm identifier và format version cùng ciphertext.
- Lưu key ID và key version, không suy luận từ tên file hoặc vị trí lưu.
- Dùng abstraction hoặc adapter cho KMS/HSM.
- Có migration path từ thuật toán legacy sang thuật toán hiện đại.
- Kiểm tra allowlist thuật toán khi đọc; từ chối thuật toán không còn được phép.
- Theo dõi dependency và khả năng tương thích giữa phiên bản ứng dụng.

Không cho phép dữ liệu tự chọn thuật toán tùy ý mà không qua policy. Metadata thuật toán là dữ liệu đầu vào cần được xác thực và kiểm tra theo allowlist.

## 23. Các anti-pattern cần tránh

- Dùng AES-ECB để mã hóa dữ liệu ứng dụng.
- Tái sử dụng nonce GCM hoặc IV CBC theo cách không an toàn.
- Dùng CBC/CTR mà không có MAC xác thực ciphertext.
- Dùng MD5 hoặc SHA-1 cho thiết kế bảo mật mới.
- Dùng SHA-256 nhanh đơn thuần để lưu password.
- Hard-code key, password, token hoặc private key trong source code.
- Lưu khóa cạnh ciphertext hoặc đưa khóa vào cùng backup không được bảo vệ.
- Dùng một key cho nhiều mục đích không liên quan.
- Tự thiết kế thuật toán, padding hoặc protocol.
- Ghi plaintext, secret hoặc key material vào log, trace và exception.
- Chỉ mã hóa database nhưng bỏ quên export, cache, log và backup.
- Không lưu key version hoặc nonce cần thiết để giải mã.
- Destroy key cũ trước khi hoàn tất migration và kiểm tra restore.
- Cấp quyền decrypt hoặc export rộng cho mọi workload.

## 24. Kiểm thử cryptographic storage

Kiểm thử cần xác minh cả hành vi đúng và khả năng từ chối dữ liệu không hợp lệ:

1. Dữ liệu hợp lệ mã hóa và giải mã cho kết quả giống plaintext ban đầu.
2. Ciphertext bị sửa, tag sai hoặc AAD sai phải bị từ chối.
3. Nonce được tạo theo cơ chế đã thiết kế và không bị tái sử dụng.
4. Key ID/version được lưu và chọn đúng khi đọc.
5. Principal không có quyền decrypt hoặc export bị từ chối.
6. Rotation không làm mất khả năng đọc dữ liệu lịch sử.
7. Backup/restore hoạt động với version khóa cần thiết.
8. Log không chứa plaintext, key material hoặc credential.
9. Lỗi provider và timeout không làm ứng dụng fallback sang thuật toán yếu.
10. KMS/HSM audit event ghi nhận principal, operation, key ID/version và kết quả.

Kiểm thử tích hợp nên chạy với KMS/HSM test resource và policy gần production. Unit test có thể dùng fake provider cho logic ứng dụng nhưng không thay thế việc kiểm tra semantics thực tế của provider.

## 25. Ví dụ kiến trúc lưu trữ an toàn

Giả sử dịch vụ Customer Profile lưu số định danh cần bảo vệ:

1. Workload xác thực bằng workload identity.
2. Ứng dụng yêu cầu KMS tạo DEK hoặc lấy DEK theo cơ chế envelope encryption.
3. Plaintext DEK được dùng trong bộ nhớ để mã hóa trường dữ liệu bằng AES-GCM.
4. Ứng dụng tạo AAD từ tenant ID, record ID và schema version.
5. Database lưu ciphertext, nonce, key ID/version và metadata AAD cần thiết.
6. Encrypted DEK được lưu cùng record hoặc metadata nhưng không lưu plaintext DEK.
7. Khi đọc, ứng dụng kiểm tra quyền người dùng và quyền workload trước khi yêu cầu unwrap/decrypt.
8. Ứng dụng xác minh GCM tag với đúng AAD rồi mới trả dữ liệu cho tầng nghiệp vụ.
9. KMS ghi audit event; ứng dụng ghi request ID và kết quả nghiệp vụ mà không ghi plaintext.
10. Rotation KEK thực hiện rewrap DEK; rotation DEK thực hiện re-encrypt theo policy.

~~~mermaid
flowchart TD
    A[Application workload] --> B[Authenticate and authorize]
    B --> C[Request DEK operation]
    C --> D[KMS or HSM: protect KEK]
    D --> E[Plaintext DEK in protected process memory]
    E --> F[AEAD encrypt/decrypt with AAD]
    F --> G[(Database: ciphertext, nonce, key reference)]
    D --> H[Audit event]
    B --> H
    F --> H
~~~

Kiến trúc này minh họa cách phối hợp cryptographic storage với key management. Triển khai thực tế cần giới hạn thời gian DEK tồn tại trong bộ nhớ, quản lý cache, phân quyền KMS và bảo vệ metadata.

## 26. Checklist áp dụng OWASP Cryptographic Storage

- [ ] Đã phân loại dữ liệu và xác định nơi lưu mọi bản sao.
- [ ] Chỉ lưu dữ liệu nhạy cảm khi có nhu cầu nghiệp vụ.
- [ ] Chọn primitive đúng mục tiêu: encryption, password hashing, MAC hoặc signature.
- [ ] Dùng thư viện mật mã đã được kiểm chứng và cập nhật.
- [ ] Ưu tiên AEAD như AES-GCM hoặc ChaCha20-Poly1305 khi phù hợp.
- [ ] Không dùng ECB, DES, RC4 hoặc thuật toán lỗi thời cho thiết kế mới.
- [ ] CBC/CTR legacy có Encrypt-then-MAC và xử lý lỗi an toàn.
- [ ] Nonce/IV đáp ứng yêu cầu của mode và không bị tái sử dụng.
- [ ] AAD được chuẩn hóa, không chứa dữ liệu nhạy cảm không cần thiết.
- [ ] Khóa được sinh bằng CSPRNG hoặc KMS/HSM.
- [ ] Key material tách khỏi ciphertext và được bảo vệ bằng KMS/HSM/secret manager phù hợp.
- [ ] Có key ID, version, owner, purpose và policy rõ ràng.
- [ ] Quyền encrypt/decrypt/sign/export/rotate được giới hạn theo least privilege.
- [ ] Có rotation, revocation, backup và recovery đã được kiểm thử.
- [ ] Log không chứa plaintext, secret hoặc key material.
- [ ] Có kiểm thử integrity, authorization, rotation và restore.
- [ ] Có kế hoạch chuyển đổi khỏi thuật toán hoặc định dạng legacy.

## Kết luận

OWASP Cryptographic Storage Cheat Sheet nhấn mạnh rằng bảo vệ dữ liệu bằng mật mã cần bắt đầu từ phân loại dữ liệu và lựa chọn đúng primitive, sau đó mới đến thuật toán, chế độ và cách triển khai. Với dữ liệu cần khôi phục, ưu tiên authenticated encryption và quản lý nonce/IV đúng cách; với password, dùng password hashing chuyên dụng; với tính toàn vẹn và xác thực, chọn MAC hoặc chữ ký phù hợp. Khóa phải được sinh an toàn, tách khỏi dữ liệu, giới hạn quyền và quản lý qua vòng đời gồm rotation, backup, recovery và hủy. KMS/HSM, envelope encryption, audit và kiểm thử giúp biến lựa chọn thuật toán thành một hệ thống lưu trữ an toàn có thể vận hành và kiểm chứng.
