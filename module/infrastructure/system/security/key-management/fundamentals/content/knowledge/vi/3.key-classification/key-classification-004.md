# Wrapping key – Khóa dùng để bọc và bảo vệ khóa khác

**Wrapping key** (khóa bọc khóa) là khóa mật mã dùng để **bảo vệ vật liệu của một khóa khác** khi khóa đó được lưu trữ, truyền giữa các thành phần hoặc di chuyển giữa các miền quản lý khóa. Hành động bảo vệ này gọi là **key wrapping**; khôi phục khóa đã bọc gọi là **key unwrapping**. Khóa bọc thường là một **KEK (Key Encryption Key)**; khóa được bọc thường là **DEK (Data Encryption Key)**, nhưng có thể là loại khóa khác nếu cơ chế và chính sách cho phép.

Trong nhóm kiến thức **Phân loại key** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, wrapping key kết nối mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán. Nhận biết đúng vai trò KEK giúp thiết kế vòng đời khóa từ **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi đến hủy**, đồng thời tránh mất dữ liệu hoặc lộ khóa khi vận hành sai.

> **Điểm quan trọng:** Wrapping key bảo vệ **một khóa khác**, không mặc nhiên dùng để mã hóa dữ liệu ứng dụng. Hệ thống có thể giữ KEK trong KMS/HSM và chỉ cho phép ứng dụng wrap/unwrap qua API được cấp quyền.

## 1. Wrapping key dùng để làm gì?

Giả sử ứng dụng cần lưu một tệp nhạy cảm:

1. Sinh **DEK ngẫu nhiên** để mã hóa nội dung bằng thuật toán mã hóa dữ liệu thích hợp, ví dụ AES-GCM.
2. Dùng **KEK** để wrap DEK theo cơ chế bọc khóa chuẩn.
3. Lưu **bản mã dữ liệu**, **DEK đã bọc** và metadata cần thiết (key ID/phiên bản, thuật toán, nonce, ngữ cảnh).
4. Khi đọc tệp, ứng dụng được phân quyền thực hiện **unwrap** để khôi phục DEK, sau đó giải mã và kiểm tra tính toàn vẹn dữ liệu.
5. Hạn chế thời gian DEK tồn tại ở dạng rõ trong bộ nhớ và không đưa DEK/KEK dạng rõ vào log.

~~~mermaid
flowchart TD
    DATA["Dữ liệu rõ"] --> E["Mã hóa bằng DEK"]
    DEK["DEK"] --> E
    E --> C["Bản mã dữ liệu"]
    DEK --> W["Wrap DEK"]
    KEK["Wrapping key / KEK: KMS-HSM"] --> W
    W --> WD["Wrapped DEK"]
    C --> STORE["Lưu ciphertext + wrapped DEK + metadata"]
    WD --> STORE
    STORE --> R["Ứng dụng được cấp quyền đọc"]
    R --> UW["Unwrap DEK"]
    KEK --> UW
    UW --> D["Giải mã và kiểm tra dữ liệu"]
    STORE --> D
~~~

Đây là cơ chế **envelope encryption** phổ biến: dữ liệu lớn được xử lý bằng mã hóa đối xứng hiệu quả, trong khi KEK bảo vệ các DEK. Một KEK có thể bọc nhiều DEK, nhưng phạm vi KEK càng rộng thì phạm vi ảnh hưởng khi khóa bị lộ, lạm dụng hoặc bị hủy nhầm càng lớn.

Key wrapping không nhất thiết dùng khóa bất đối xứng: KEK có thể là **khóa đối xứng**. Trong quy trình trao đổi khóa, public key của người nhận cũng có thể tham gia bảo vệ khóa phiên bằng cơ chế mã hóa bất đối xứng hoặc giao thức lai chuẩn hóa.

## 2. Wrapping key khác gì với DEK, master key và key pair?

| Loại khóa | Nhiệm vụ | Ví dụ |
| --- | --- | --- |
| **DEK** | Mã hóa/giải mã dữ liệu ứng dụng. | Khóa AES-256-GCM riêng cho một tệp hoặc tập bản ghi. |
| **KEK / wrapping key** | Bọc/giải bọc vật liệu khóa khác. | Khóa AES-KW được giữ trong KMS. |
| **Root/master key** | Bảo vệ khóa ở lớp thấp hơn trong hệ phân cấp khóa; vai trò cụ thể tùy kiến trúc. | Khóa gốc do HSM quản lý để bảo vệ KEK. |
| **Private key** | Thành phần bí mật của key pair dùng ký, giải mã hoặc thỏa thuận khóa tùy thuật toán. | Private key RSA-OAEP tham gia giải mã phần khóa được bảo vệ. |
| **Public key** | Thành phần công khai của key pair dùng xác minh, mã hóa hoặc thỏa thuận khóa tùy thuật toán. | Public key của bên nhận để truyền khóa. |

**KEK và wrapping key thường được dùng như từ gần nghĩa**, nhưng tên khóa không quyết định khả năng sử dụng: cần xem **key usage**, thuật toán, quyền API và phạm vi hoạt động. Ví dụ, Ed25519 là thuật toán ký số, không dùng trực tiếp để wrap DEK; X25519 phục vụ thỏa thuận khóa, cần giao thức dẫn xuất và bảo vệ khóa thích hợp mới tạo thành giải pháp vận chuyển khóa.

### Khác biệt giữa key wrapping và mã hóa dữ liệu

| Tiêu chí | Data encryption | Key wrapping |
| --- | --- | --- |
| Đối tượng đầu vào | Tệp, bản ghi hoặc thông điệp. | Vật liệu khóa và metadata theo thiết kế. |
| Mục tiêu | Bảo mật và thường xác thực nội dung. | Bảo mật khóa và phát hiện khóa đã bọc bị sửa đổi. |
| Cơ chế thường gặp | AES-GCM, AEAD thích hợp. | AES-KW, AES-KWP, AEAD được cấu hình đúng hoặc cơ chế bất đối xứng/lai tiêu chuẩn. |
| Kết quả | Bản mã, nonce/tag và metadata. | Wrapped key cùng thông tin cần để unwrap. |
| Quyền nhạy cảm | Truy cập dữ liệu/DEK. | Unwrap, quản trị KEK và quyền xuất khóa. |

Không nên lấy một chế độ mã hóa tùy ý rồi gọi là key wrapping: **AES-ECB, XOR, RSA thô hoặc CBC không xác thực** không đáp ứng đầy đủ yêu cầu bảo vệ key material.

## 3. Các cơ chế key wrapping chuẩn

**AES Key Wrap (AES-KW, RFC 3394)** sử dụng AES để bọc khóa với cơ chế kiểm tra tính toàn vẹn theo định dạng chuẩn. Dạng thông thường áp dụng cho đầu vào theo giới hạn chiều dài, điển hình có chiều dài bội số 64 bit và từ 128 bit trở lên.

**AES Key Wrap with Padding (AES-KWP, RFC 5649)** hỗ trợ đầu vào có chiều dài linh hoạt hơn nhờ cơ chế padding theo chuẩn.

**AEAD, ví dụ AES-GCM**, cũng có thể được dùng để bảo vệ key material trong một giao thức được thiết kế đúng. AES-GCM yêu cầu **nonce không trùng lặp cho cùng khóa**, xác thực ciphertext và có thể dùng **AAD** (additional authenticated data) để ràng buộc ngữ cảnh. Khi unwrap, AAD phải trùng giá trị đã dùng lúc mã hóa.

**Mã hóa bất đối xứng hoặc mã hóa lai**, ví dụ RSA-OAEP hoặc HPKE, hỗ trợ bảo vệ hoặc vận chuyển khóa theo thuật toán và giao thức tương ứng. RSA-OAEP có giới hạn kích thước đầu vào; không mã hóa dữ liệu lớn trực tiếp bằng RSA hay dùng RSA không có padding an toàn.

**Khác biệt quan trọng:** AES-KW không có trường AAD như AES-GCM. Việc lưu tenant ID, key ID hoặc purpose bên cạnh wrapped key **không tự động ràng buộc mật mã** các giá trị đó. Hệ thống phải xác thực metadata và quyền sử dụng, hoặc dùng giao thức/cơ chế hỗ trợ gắn kết ngữ cảnh.

## 4. Wrapping key trong KMS và HSM

**KMS (Key Management Service)** cung cấp API và chính sách để quản lý khóa. **HSM (Hardware Security Module)** cung cấp ranh giới phần cứng để bảo vệ key material và thực hiện một số phép toán mật mã; KMS có thể sử dụng HSM phía sau. Khả năng thực tế phụ thuộc nhà cung cấp và cấu hình.

Với mô hình envelope encryption trên KMS:

1. Quản trị viên sinh KEK và thiết lập thuật toán, phạm vi, owner, môi trường và quyền sử dụng.
2. Ứng dụng gọi cơ chế sinh DEK/bọc DEK mà KMS hỗ trợ. Trong một số dịch vụ, API sinh data key trả về cả DEK dạng rõ và DEK đã được mã hóa; đây là **hành vi API cụ thể của nhà cung cấp**, không phải đặc tính của mọi KMS.
3. Ứng dụng dùng DEK để mã hóa dữ liệu, lưu ciphertext và DEK đã bọc.
4. Ứng dụng có quyền giải mã gọi KMS để unwrap/giải mã DEK; KEK có thể được giữ **non-exportable**.
5. KMS ghi nhận hoạt động theo khả năng kiểm toán được cấu hình; ứng dụng tiếp tục quản lý vòng đời DEK ở bộ nhớ và cache.

Việc KEK không được xuất khỏi KMS/HSM giúp giảm nguy cơ rò rỉ **bytes của KEK**, nhưng **kẻ có quyền gọi API unwrap trái phép** vẫn có thể lấy được DEK dạng rõ nếu API trả về DEK. Vì vậy, kiểm soát quyền **sử dụng khóa** cũng quan trọng như bảo vệ vật liệu khóa.

### Quyền truy cập nên phân tách

- **Wrap:** tạo wrapped key để lưu DEK mới.
- **Unwrap:** khôi phục DEK để đọc dữ liệu; thường cần bảo vệ đặc biệt.
- **Rotate/disable/delete:** quản trị vòng đời wrapping key.
- **Grant/revoke:** thay đổi quyền sử dụng hoặc quản lý khóa.

Áp dụng **least privilege**, danh tính workload, phân tách nhiệm vụ, tách môi trường, hạn chế theo tenant/ứng dụng và giám sát lệnh unwrap bất thường. Không dựa vào một key alias do client nhập để quyết định quyền truy cập dữ liệu.

## 5. Ví dụ Java 17+: AESWrap bảo vệ DEK, AES-GCM bảo vệ dữ liệu

Ví dụ sau sử dụng **Java Cryptography Architecture (JCA)** để minh họa hai lớp: AES-GCM mã hóa dữ liệu bằng DEK, AESWrap bọc DEK bằng KEK. Để đơn giản, cả hai khóa được sinh trong bộ nhớ; triển khai sản xuất có yêu cầu cao nên giữ KEK trong KMS/HSM và gọi API qua key ID.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class WrappingKeyDemo {
    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey kek = generator.generateKey();
        SecretKey dek = generator.generateKey();

        // Mỗi lần AES-GCM mã hóa với cùng DEK cần nonce duy nhất.
        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);
        byte[] context = "tenant-A|invoice-123|v1"
                .getBytes(StandardCharsets.UTF_8);

        Cipher dataEncryptor = Cipher.getInstance("AES/GCM/NoPadding");
        dataEncryptor.init(
                Cipher.ENCRYPT_MODE, dek, new GCMParameterSpec(128, nonce));
        dataEncryptor.updateAAD(context);
        byte[] ciphertext = dataEncryptor.doFinal(
                "Hoa don can bao ve".getBytes(StandardCharsets.UTF_8));

        // KEK bọc DEK, không mã hóa trực tiếp dữ liệu hóa đơn.
        Cipher wrapper = Cipher.getInstance("AESWrap");
        wrapper.init(Cipher.WRAP_MODE, kek);
        byte[] wrappedDek = wrapper.wrap(dek);

        // Lưu ciphertext + wrappedDek + nonce và metadata đã xác thực.
        // Không lưu KEK/DEK dạng rõ cùng bản mã.

        Cipher unwrapper = Cipher.getInstance("AESWrap");
        unwrapper.init(Cipher.UNWRAP_MODE, kek);
        SecretKey recoveredDek = (SecretKey) unwrapper.unwrap(
                wrappedDek, "AES", Cipher.SECRET_KEY);

        Cipher dataDecryptor = Cipher.getInstance("AES/GCM/NoPadding");
        dataDecryptor.init(
                Cipher.DECRYPT_MODE, recoveredDek, new GCMParameterSpec(128, nonce));
        dataDecryptor.updateAAD(context);
        byte[] plaintext = dataDecryptor.doFinal(ciphertext);

        System.out.println(new String(plaintext, StandardCharsets.UTF_8));
        Arrays.fill(plaintext, (byte) 0); // Chỉ xóa bản sao mảng này.
    }
}
~~~

Diễn giải:

- **kek** là wrapping key, **dek** là khóa mã hóa dữ liệu; không nên dùng lẫn mục đích.
- **AESWrap** bảo vệ vật liệu DEK và kiểm tra định dạng/tính toàn vẹn của wrapped DEK khi unwrap.
- **AES/GCM/NoPadding** cung cấp xác thực bản mã với nonce 96 bit và tag 128 bit. **Không dùng lại nonce với cùng DEK** cho các lần mã hóa khác nhau.
- **updateAAD(context)** ràng buộc ciphertext dữ liệu với thông tin ngữ cảnh. AESWrap trong ví dụ **không tự ràng buộc** wrapped DEK với tenant; hệ thống thực tế cần xác minh metadata và quyền ứng dụng tương ứng.
- **Arrays.fill** chỉ xóa nội dung mảng plaintext được chỉ định; không bảo đảm xóa mọi bản sao trên heap, dump hoặc log.
- Tên biến thể AESWrap và khả năng hỗ trợ có thể phụ thuộc provider/JDK. Ví dụ bỏ qua lưu trữ bền vững, quản lý lỗi, phân quyền, kiểm toán và kế hoạch khôi phục.

Không đưa KEK hoặc DEK dạng rõ vào source code, log, hệ thống phân tích lỗi hay bản sao lưu không được bảo vệ. Việc nhận DEK dạng rõ trong ứng dụng luôn đòi hỏi kiểm soát bộ nhớ và quyền truy cập.

## 6. Xoay KEK, rewrap DEK và thay khóa dữ liệu

**Rotate KEK** là chuyển sang wrapping key hoặc phiên bản KEK mới để bọc các khóa khác. **Rewrap** là chuyển một DEK từ lớp bảo vệ KEK cũ sang KEK mới, có thể qua dịch vụ KMS. **Rotate DEK** là tạo DEK mới; để dữ liệu cũ được bảo vệ dưới DEK mới thường cần giải mã và mã hóa lại dữ liệu.

| Thao tác | Thay đổi | Có cần mã hóa lại dữ liệu ứng dụng? |
| --- | --- | --- |
| **Rotate KEK** | KEK mới được dùng cho các thao tác wrap mới. | Không nhất thiết. |
| **Rewrap DEK** | Bản wrapped DEK được bảo vệ bởi KEK mới. | Thường không cần nếu DEK không đổi. |
| **Rotate DEK** | Thay khóa trực tiếp mã hóa dữ liệu. | Thường cần mã hóa lại dữ liệu cũ nếu muốn chuyển toàn bộ dữ liệu sang DEK mới. |
| **Re-encrypt data** | Tạo bản mã dữ liệu mới dưới khóa/chính sách mới. | Có. |

Quy trình thay KEK cũ **K1** bằng KEK mới **K2**:

1. Tạo K2 và thiết lập quyền, thuật toán, key ID/phiên bản; kiểm tra khả năng unwrap.
2. Chuyển các thao tác wrap mới sang K2, ngừng sử dụng K1 cho dữ liệu mới.
3. Rewrap những DEK cũ còn phải dùng; chọn API KMS re-encryption nếu có hỗ trợ để giảm việc đưa DEK ra ứng dụng.
4. Cập nhật metadata **một cách nhất quán** và bảo đảm thao tác lặp không gây sai phiên bản; duy trì khả năng khôi phục khi lỗi giữa chừng.
5. Đối soát các bản ciphertext, wrapped DEK, bản sao vùng khác và backup; kiểm tra đường giải mã.
6. Chỉ vô hiệu hóa/hủy K1 sau khi mọi dữ liệu và bản sao cần giữ có đường giải mã hợp lệ và chính sách lưu giữ cho phép.

**Không đánh đồng rotate KEK với xử lý lộ DEK:** nếu DEK dạng rõ đã bị lộ, chỉ rewrap DEK dưới KEK mới **không làm DEK cũ hết nguy hiểm**. Dữ liệu bị ảnh hưởng có thể cần được mã hóa lại bằng DEK mới và xử lý theo quy trình sự cố.

## 7. Thiết kế theo tenant và giới hạn phạm vi ảnh hưởng

Một nền tảng SaaS có ba tenant A, B, C; mỗi tệp có DEK riêng. Xem hai phương án:

| Phương án | Ưu điểm | Rủi ro/cân nhắc |
| --- | --- | --- |
| **Một KEK chung** bọc DEK cho nhiều tenant | Ít đối tượng KEK, đơn giản quản trị. | Nếu quyền unwrap không ràng buộc tenant hoặc KEK bị hủy nhầm, ảnh hưởng nhiều tenant. |
| **KEK riêng theo tenant** | Phân tách chính sách, hạn chế tác động khi quản trị hoặc hủy khóa riêng từng tenant. | Tăng số khóa, chi phí, quota, nhu cầu theo dõi trạng thái và backup. |

Nếu tenant B yêu cầu xóa dữ liệu, **không thể đơn giản hủy KEK chung** vì dữ liệu A/C cũng có thể không giải mã được. Nếu B có KEK riêng, hủy KEK-B có thể là một phần chiến lược **crypto-shredding**, nhưng chỉ có hiệu lực khi không còn bản sao DEK, bản rõ, KEK, cache hoặc đường khôi phục khác có thể giải mã dữ liệu B.

Một bản wrapped DEK không tự “biết” thuộc tenant nào. Phải xác thực tenant của caller, kiểm tra quyền tại KMS và ứng dụng, đồng thời bảo vệ ngữ cảnh liên quan bằng AAD/encryption context hoặc giao thức phù hợp. Đầu vào key ID do người dùng gửi không được xem là bằng chứng quyền sở hữu khóa.

## 8. Kiểm toán và vòng đời wrapping key

| Giai đoạn | Hoạt động cần kiểm soát | Hậu quả có thể xảy ra nếu sai |
| --- | --- | --- |
| **Sinh/cấp phát** | Sinh KEK bằng CSPRNG/KMS-HSM, đặt ID, thuật toán, usage, owner, môi trường. | Khóa yếu, nhầm mục đích, không rõ phạm vi. |
| **Lưu trữ** | Giới hạn xuất KEK, tách KEK khỏi DEK/bản mã, bảo vệ backup và replica. | Rò rỉ KEK làm lộ nhiều DEK. |
| **Sử dụng** | Phân quyền wrap/unwrap, ràng buộc tenant/ngữ cảnh, ghi audit. | Giải bọc DEK trái phép dù KEK không xuất ra ngoài. |
| **Xoay vòng** | Phiên bản hóa KEK, rewrap DEK, đối soát dữ liệu và backup. | Không thể khôi phục dữ liệu lịch sử. |
| **Thu hồi/vô hiệu hóa** | Ngăn dùng KEK bị nghi lộ, xử lý DEK đã được unwrap và khóa có liên quan. | Khóa cũ tiếp tục bị lạm dụng từ cache hoặc dịch vụ chưa cập nhật. |
| **Hủy** | Kiểm tra mọi wrapped DEK phụ thuộc, bản sao và nhu cầu khôi phục trước khi xóa. | Dữ liệu mất vĩnh viễn hoặc khóa còn khả năng phục hồi ngoài dự kiến. |

Hồ sơ audit nên ghi **ai**, **khi nào**, **key ID/phiên bản**, **thao tác wrap/unwrap**, **mục đích hoặc tenant**, **kết quả phân quyền** và **mã yêu cầu**. Không log KEK/DEK dạng rõ, secret hoặc nội dung dữ liệu nhạy cảm. Đối với hủy hoặc thay quyền khóa quan trọng, áp dụng cơ chế phê duyệt và phân tách nhiệm vụ theo mức rủi ro.

## 9. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Lưu KEK dạng rõ cạnh wrapped DEK | Mất lớp bảo vệ khóa. | Giữ KEK trong KMS/HSM hoặc kho khóa hạn chế truy cập. |
| Cho nhiều workload quyền unwrap mọi KEK | Một dịch vụ bị chiếm quyền có thể mở nhiều DEK. | Least privilege, tách tenant/workload, xác thực ngữ cảnh. |
| Tự triển khai wrap bằng ECB, XOR hoặc RSA thô | Thiếu thuộc tính mật mã cần thiết và dễ sai giao thức. | Dùng AES-KW/KWP, AEAD phù hợp hoặc chuẩn bất đối xứng được kiểm chứng. |
| Dùng AES-GCM để wrap nhưng tái sử dụng nonce | Có thể mất bí mật và tính toàn vẹn của dữ liệu đã bảo vệ. | Bảo đảm nonce duy nhất theo cùng khóa. |
| Chỉ lưu wrapped DEK, quên key ID/phiên bản | Không xác định được KEK khi rotate hoặc khôi phục. | Lưu metadata có phiên bản và bảo vệ tính toàn vẹn. |
| Cho client tự quyết định tenant/key ID | Có thể unwrap chéo tenant hoặc thay đổi ngữ cảnh. | Kiểm tra danh tính caller, ACL và ngữ cảnh mật mã. |
| Rewrap xong hủy KEK cũ ngay, quên backup | Backup cũ mất khả năng giải mã. | Kiểm kê toàn bộ bản sao và thử quy trình khôi phục. |
| Chỉ rotate KEK sau khi DEK lộ | Dữ liệu vẫn mã hóa bằng DEK đã bị lộ. | Rotate DEK và mã hóa lại dữ liệu bị ảnh hưởng. |

## 10. Câu hỏi tự kiểm tra

1. Wrapping key khác DEK như thế nào, và vì sao thường tách hai vai trò này?
2. Một KEK không thể xuất khỏi HSM có còn rủi ro bị lạm dụng hay không?
3. Khi nào rewrap DEK không cần giải mã lại bản mã dữ liệu?
4. Vì sao phải lưu key ID, phiên bản KEK và metadata đã xác thực cùng wrapped DEK?
5. Hủy KEK chung của nhiều tenant có thể gây hậu quả gì?
6. Nếu DEK bị lộ, chỉ rotate KEK có đủ để bảo vệ bản mã cũ không?

**Ghi nhớ:** Wrapping key là nền tảng của mô hình **bảo vệ khóa bằng khóa**. An toàn không chỉ đến từ thuật toán wrap mà còn từ việc tách KEK và DEK, kiểm soát quyền unwrap, quản lý metadata và phiên bản, kiểm toán KMS/HSM, cũng như lập kế hoạch xoay vòng, thu hồi và hủy khóa trên toàn bộ dữ liệu phụ thuộc.
