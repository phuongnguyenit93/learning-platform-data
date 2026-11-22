# Mã hóa ảnh khi lưu trữ và truyền tải

Checkpoint của một ứng dụng Java có thể chứa nhiều dữ liệu nhạy cảm hơn một file cấu hình hoặc một bản build. Trong bộ nhớ tại thời điểm checkpoint có thể có access token, session credential, private key, thông tin người dùng, request đang xử lý, dữ liệu cache, câu lệnh SQL, nội dung message và trạng thái nội bộ của thư viện. Nếu ảnh checkpoint bị đọc trái phép, người có được ảnh có thể thu thập dữ liệu hoặc khôi phục một tiến trình với trạng thái đã được chuẩn bị sẵn.

CRaC (Coordinated Restore at Checkpoint) giúp lưu và khôi phục trạng thái tiến trình, nhưng không nên giả định mọi JDK hoặc nền tảng đều tự mã hóa checkpoint artifact. Cơ chế mã hóa phải được xác định theo runtime, hệ điều hành, storage, pipeline đóng gói và cách vận chuyển ảnh. Một checkpoint có thể gồm nhiều file, metadata và file phụ trợ; tất cả thành phần nhạy cảm cần nằm trong phạm vi bảo vệ.

Bảo vệ ảnh checkpoint cần giải quyết hai thời điểm khác nhau: **mã hóa khi lưu trữ (at rest)** để người không có quyền không đọc được artifact trên disk, object storage hoặc backup; và **mã hóa khi truyền tải (in transit)** để ngăn việc nghe lén hoặc sửa đổi dữ liệu trên đường truyền. Đồng thời, ứng dụng cần quản lý khóa, xác thực tính toàn vẹn, kiểm soát quyền restore và tránh để lại bản plaintext tạm thời.

## 1. Vì sao checkpoint artifact cần được mã hóa?

Checkpoint có thể lưu trạng thái bộ nhớ của một tiến trình đang chạy. Điều này hữu ích để rút ngắn startup, nhưng cũng làm tăng phạm vi dữ liệu cần bảo vệ.

Một ảnh có thể chứa:

- Access token, session token, refresh token hoặc credential tạm thời đã được nạp vào heap.
- Private key, certificate material hoặc dữ liệu phục vụ ký request.
- Thông tin người dùng, session ứng dụng và dữ liệu nghiệp vụ đang được xử lý.
- Nội dung cache, message queue nội bộ, request body hoặc response buffer.
- Connection string, endpoint, tenant ID và metadata hạ tầng.
- Dữ liệu của thư viện native hoặc vùng nhớ ngoài heap mà runtime đưa vào checkpoint.
- Trạng thái của thread, executor, transaction context hoặc resource handle tùy runtime.

Không phải mọi checkpoint đều chứa toàn bộ các dữ liệu trên. Phạm vi cụ thể phụ thuộc ứng dụng, runtime, resource được loại trừ và cơ chế checkpoint. Tuy nhiên, cách đánh giá an toàn nên bắt đầu từ giả định rằng artifact có thể chứa dữ liệu nhạy cảm của tiến trình.

Nếu artifact được lưu trong object storage, registry, shared filesystem, backup repository hoặc CI artifact store, người có quyền đọc nhầm có thể tiếp cận dữ liệu trong ảnh. Nếu artifact đi qua mạng nội bộ không được mã hóa, người có khả năng quan sát traffic có thể thu thập bản sao. Nếu artifact bị thay đổi, tiến trình restore có thể khởi động từ trạng thái không đáng tin cậy.

Mã hóa giúp giảm rủi ro khi dữ liệu bị truy cập ở storage hoặc trên đường truyền. Nó không thay thế quyền truy cập, xác thực, audit, quản lý khóa và kiểm soát máy đích.

## 2. Phạm vi bảo vệ: toàn bộ checkpoint package

Không nên chỉ mã hóa một file mà bỏ quên những thành phần còn lại. Tùy runtime và cách đóng gói, checkpoint có thể là một thư mục gồm nhiều file memory page, metadata, file descriptor state, thông tin mapping hoặc dữ liệu phụ trợ. Một pipeline triển khai có thể tạo thêm archive, manifest, checksum và log.

Các thành phần cần đưa vào inventory:

| Thành phần | Dữ liệu có thể lộ | Cách bảo vệ |
|---|---|---|
| Memory/image files | Heap, native state và dữ liệu ứng dụng | Mã hóa toàn bộ artifact hoặc dùng storage mã hóa |
| Metadata/manifest | Tên file, phiên bản, đường dẫn, cấu hình và identity | Mã hóa hoặc ký/xác thực; hạn chế quyền đọc |
| Archive/package | Nội dung checkpoint sau khi gom file | Mã hóa package hoàn chỉnh |
| Temporary files | Bản giải nén hoặc bản plaintext trung gian | Dùng vùng lưu trữ được bảo vệ và cleanup |
| Backup/version history | Các bản checkpoint cũ | Áp dụng cùng chính sách mã hóa và retention |
| Transfer logs | URL, object key, credential hoặc thông tin môi trường | Không ghi secret; giới hạn quyền và thời gian lưu |
| Checksum/signature files | Metadata xác minh artifact | Bảo vệ tính xác thực, tránh thay thế cùng artifact |

Nếu runtime tạo checkpoint thành một thư mục, cần đợi thao tác checkpoint hoàn tất rồi mới đóng gói hoặc mã hóa. Không đọc, nén, mã hóa hoặc upload các file trong lúc runtime còn đang ghi chúng. Một package được tạo từ tập file chưa hoàn chỉnh có thể restore thất bại hoặc không nhất quán.

Cần giữ đúng cấu trúc và metadata cần thiết cho restore: tên file, quyền truy cập, owner, symbolic link, thứ tự hoặc quan hệ giữa các thành phần theo yêu cầu runtime. Không tự ý thay đổi nội dung hoặc cấu trúc checkpoint để thuận tiện mã hóa nếu chưa hiểu định dạng của runtime.

## 3. Mã hóa khi lưu trữ và mã hóa khi truyền tải

Hai lớp này bảo vệ hai ranh giới khác nhau.

**Mã hóa khi lưu trữ (encryption at rest)** bảo vệ dữ liệu khi artifact nằm trên disk, volume, object storage, backup hoặc media lưu trữ. Các lựa chọn thường gặp gồm mã hóa volume/filesystem, server-side encryption của object storage và client-side encryption trước khi upload.

**Mã hóa khi truyền tải (encryption in transit)** bảo vệ dữ liệu khi artifact di chuyển từ nơi tạo checkpoint đến nơi lưu trữ hoặc từ storage đến máy restore. Các lựa chọn thường gặp gồm TLS/HTTPS, mutual TLS, SSH/SFTP hoặc kênh riêng có mã hóa được cấu hình đúng.

~~~text
Máy tạo checkpoint
  |
  | 1. Checkpoint hoàn tất
  v
Checkpoint package
  |
  | 2. Mã hóa bằng data key
  v
Ciphertext + manifest đã xác thực
  |
  | 3. Truyền qua TLS
  v
Storage / backup repository
  |
  | 4. Đọc ciphertext qua TLS
  v
Máy restore
  |
  | 5. Xác minh manifest, giải mã bằng quyền được cấp
  v
Checkpoint plaintext trong vùng được bảo vệ
  |
  v
CRaC restore
~~~

TLS không thay thế mã hóa at rest vì TLS kết thúc khi dữ liệu được ghi vào storage. Mã hóa volume không thay thế TLS vì dữ liệu vẫn có thể bị đọc trên đường truyền nếu gửi qua kênh không an toàn. Một hệ thống thường cần cả hai.

## 4. Các mô hình mã hóa at rest

### 4.1. Mã hóa disk hoặc volume

Filesystem hoặc block device được mã hóa, ví dụ bằng cơ chế mã hóa volume của hệ điều hành hoặc nền tảng lưu trữ. Khi volume được mount và ứng dụng có quyền truy cập, dữ liệu thường xuất hiện dưới dạng plaintext đối với process được cấp quyền.

Ưu điểm:

- Có thể bảo vệ nhiều file cùng lúc mà không cần thay đổi định dạng checkpoint.
- Tích hợp ở lớp hạ tầng, ít thay đổi mã ứng dụng.
- Có thể áp dụng cho thư mục staging, thư mục checkpoint và volume chứa bản giải mã.

Giới hạn:

- Không bảo vệ trước process hoặc administrator có quyền đọc dữ liệu sau khi volume đã được mở.
- Không tự động bảo vệ bản sao được copy sang storage khác nếu nơi nhận không mã hóa.
- Backup, snapshot volume và replica storage cần có chính sách riêng.
- Cần quản lý khóa mở volume và quyền mount.

Mã hóa volume phù hợp khi đội vận hành kiểm soát hạ tầng lưu trữ và muốn bảo vệ dữ liệu khi thiết bị hoặc volume bị truy cập ngoài dự kiến. Nó không phải mã hóa end-to-end của artifact.

### 4.2. Server-side encryption

Object storage hoặc storage service có thể mã hóa dữ liệu khi ghi xuống media. Nhà cung cấp quản lý encryption operation và có thể dùng khóa do nền tảng quản lý hoặc khóa trong KMS do khách hàng kiểm soát.

Ưu điểm:

- Dễ tích hợp với object storage.
- Có thể mã hóa cả object version và replica nếu cấu hình đúng.
- KMS policy và audit log hỗ trợ kiểm soát quyền.
- Ứng dụng không nhất thiết phải tự xử lý định dạng ciphertext.

Cần xác minh:

- Bucket/container có bắt buộc mã hóa mọi object không?
- Object cũ hoặc bản copy có được mã hóa không?
- Backup, replication và versioning có giữ cùng chính sách không?
- Ai có quyền yêu cầu decrypt khi đọc object?
- Key policy có giới hạn theo workload identity, environment hoặc artifact prefix không?
- Dịch vụ có audit sự kiện sử dụng khóa không?

Server-side encryption bảo vệ media storage theo mô hình tin cậy của nhà cung cấp. Người hoặc service có quyền đọc object và quyền sử dụng khóa vẫn có thể nhận plaintext. Nếu cần bảo vệ trước chính storage service hoặc trước principal có quyền đọc object nhưng không có khóa giải mã, hãy cân nhắc client-side encryption.

### 4.3. Client-side encryption

Client-side encryption mã hóa artifact trước khi gửi đến storage. Storage chỉ nhận ciphertext; khóa giải mã được quản lý tách biệt qua KMS/HSM hoặc hệ thống khóa riêng.

Ưu điểm:

- Ciphertext được tạo trước khi rời khỏi trust boundary của ứng dụng.
- Storage không cần nhìn thấy plaintext.
- Có thể dùng cùng định dạng mã hóa khi lưu trên nhiều loại storage.
- Quyền đọc object không tự động đồng nghĩa với quyền giải mã.

Đổi lại, ứng dụng hoặc pipeline cần quản lý định dạng, data key, nonce, authentication tag, manifest, rotation và restore. Nếu mất khóa, artifact có thể không còn sử dụng được. Cần kiểm thử cả backup của khóa và quy trình khôi phục thảm họa.

### 4.4. Kết hợp nhiều lớp

Một cấu hình thường dùng là client-side encryption cho artifact, TLS khi truyền và server-side encryption hoặc volume encryption ở storage. Các lớp này bảo vệ những ranh giới khác nhau.

Không nên nhầm nhiều lớp mã hóa với nhiều khóa tùy tiện. Hãy xác định threat model và owner của từng khóa. Việc dùng quá nhiều lớp không có chính sách rotation và recovery rõ ràng có thể khiến restore khó vận hành hoặc không thể giải mã khi cần.

## 5. Mã hóa truyền tải bằng TLS

Khi upload hoặc download checkpoint qua HTTP, HTTPS/TLS cung cấp mã hóa và xác thực kênh truyền. Với dịch vụ mới, ưu tiên TLS 1.3 khi các thành phần hỗ trợ; TLS 1.2 có cấu hình cipher suite an toàn vẫn được sử dụng rộng rãi. Tuân thủ policy bảo mật của tổ chức và nền tảng.

Cần bảo đảm:

- Client xác minh certificate chain và hostname của server.
- Không tắt certificate validation để xử lý lỗi môi trường.
- Dùng CA trust store phù hợp và có kế hoạch cập nhật certificate.
- Dùng mutual TLS khi cần xác thực cả client và server ở tầng transport.
- Giữ credential client ở secret manager hoặc identity provider, không nhúng vào checkpoint package.
- Bảo vệ mọi hop nếu TLS kết thúc tại reverse proxy hoặc gateway.
- Không gửi artifact qua HTTP plaintext.
- Không log Authorization header, private key, session token hoặc signed URL đầy đủ.

Nếu upload đi qua proxy, gateway hoặc service mesh, hãy xác định nơi TLS terminate. Kênh từ client đến proxy có thể được mã hóa trong khi hop từ proxy đến storage lại không. Mỗi hop cần nằm trong mô hình bảo vệ.

TLS không xác thực nội dung artifact sau khi lưu. Sau khi object được lưu, attacker có thể thay thế object bằng một file khác nếu họ có quyền ghi storage. Vì vậy, cần xác minh tính toàn vẹn và nguồn gốc artifact bằng authenticated encryption, chữ ký số hoặc MAC trên manifest.

## 6. Xác thực tính toàn vẹn: chỉ mã hóa là chưa đủ

Mã hóa không xác thực có thể để lại khả năng sửa đổi ciphertext hoặc metadata mà hệ thống không phát hiện đúng cách. Với checkpoint, một thay đổi nhỏ trong file memory hoặc metadata cũng có thể làm restore lỗi hoặc khôi phục trạng thái bị thao túng.

Nên dùng authenticated encryption with associated data (AEAD), ví dụ:

- AES-GCM.
- ChaCha20-Poly1305.

AEAD cung cấp confidentiality và authentication cho ciphertext. Nó cũng cho phép xác thực metadata không cần mã hóa bằng Associated Authenticated Data (AAD), ví dụ artifact ID, file path đã chuẩn hóa, phiên bản định dạng hoặc chunk index.

Khi giải mã, nếu ciphertext, tag hoặc AAD không khớp, thao tác phải thất bại. Không được bỏ qua authentication tag hoặc tiếp tục restore bằng dữ liệu chưa xác minh.

Một checksum như SHA-256 có ích để phát hiện lỗi truyền hoặc corruption ngẫu nhiên. Nhưng nếu attacker có thể thay cả file lẫn checksum, checksum không chứng minh nguồn gốc. Để xác thực trước attacker, dùng AEAD, MAC với khóa bí mật hoặc chữ ký số với public key tin cậy.

## 7. Envelope encryption: mã hóa dữ liệu bằng DEK và bảo vệ DEK bằng KMS

Một mô hình phổ biến là envelope encryption:

- **Data Encryption Key (DEK):** Khóa dữ liệu dùng để mã hóa checkpoint.
- **Key Encryption Key (KEK):** Khóa quản lý trong KMS/HSM, dùng để wrap hoặc encrypt DEK.
- **Wrapped DEK:** DEK đã được mã hóa bằng KEK; có thể lưu cùng ciphertext artifact.
- **KMS key reference:** Định danh khóa trong KMS, không phải bí mật giải mã.

~~~text
                 KMS / HSM
              KEK (không export)
                    |
                    | wrap DEK
                    v
Checkpoint --> DEK ngẫu nhiên --> mã hóa artifact bằng AEAD
                    |
                    +---- Wrapped DEK lưu trong manifest
                    |
                    v
             Ciphertext artifact
~~~

Quy trình tạo artifact:

1. Xác thực identity của pipeline tạo checkpoint.
2. Yêu cầu KMS tạo một DEK mới hoặc tạo DEK trong client theo chính sách.
3. Dùng plaintext DEK để mã hóa artifact.
4. Yêu cầu KMS wrap/encrypt DEK bằng KEK.
5. Lưu wrapped DEK, key ID, algorithm, nonce và metadata cần thiết trong manifest đã được xác thực.
6. Hủy reference tới plaintext DEK khi không còn cần; không ghi DEK vào log hoặc file không mã hóa.

Quy trình restore:

1. Xác thực identity của workload được phép restore.
2. Đọc manifest và kiểm tra chữ ký/MAC hoặc metadata đã được xác thực.
3. Yêu cầu KMS unwrap DEK bằng quyền decrypt phù hợp.
4. Xác thực và giải mã từng file/chunk.
5. Chỉ đưa plaintext vào vùng staging được bảo vệ sau khi kiểm tra thành công.

KMS không nhất thiết phải export KEK. KMS giữ KEK và chỉ thực hiện thao tác wrap/unwrap theo policy. Nhờ đó, quyền truy cập storage và quyền sử dụng khóa có thể được tách riêng.

## 8. Chọn thuật toán và quản lý nonce

Dùng thuật toán mã hóa đã được chuẩn hóa và thư viện mật mã được duy trì. Với ứng dụng Java, AES-GCM là một lựa chọn AEAD phổ biến nếu JDK/provider và policy tổ chức hỗ trợ. ChaCha20-Poly1305 cũng là lựa chọn AEAD phù hợp trên các nền tảng được hỗ trợ.

Các điểm cần nhớ:

- Dùng khóa đủ mạnh, thường là AES-256 theo policy.
- Với AES-GCM, nonce thường có độ dài 96 bit và tag authentication thường là 128 bit.
- Không bao giờ tái sử dụng cùng nonce với cùng key trong AES-GCM.
- Mỗi artifact nên có DEK riêng; mỗi lần mã hóa lại artifact cần nonce mới hoặc DEK mới theo thiết kế.
- Với mã hóa chia chunk, mỗi chunk phải có nonce duy nhất dưới cùng DEK.
- Không tự thiết kế thuật toán, mode hoặc cách kết hợp encryption và checksum.
- Không dùng ECB hoặc mã hóa tự chế dựa trên XOR.

Nonce không cần giữ bí mật, nhưng phải được lưu để giải mã. Với một file mã hóa bằng một DEK riêng, có thể tạo nonce ngẫu nhiên 96 bit bằng SecureRandom. Với file rất lớn chia nhiều chunk, cần thiết kế nonce không lặp, ví dụ một prefix duy nhất cho artifact kết hợp với counter chunk tăng đơn điệu. Khi retry hoặc mã hóa lại, phải bảo đảm không dùng lại nonce với cùng DEK cho plaintext khác.

## 9. Ví dụ Java AES-GCM cho một payload nhỏ

Đoạn code sau minh họa API JCA/JCE để mã hóa và giải mã một payload nhỏ bằng AES-GCM. Trong hệ thống thật, DEK phải được cấp hoặc bảo vệ bởi KMS; ví dụ tạo key cục bộ chỉ để minh họa thuật toán và không phải cách lưu khóa production.

~~~java
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Arrays;

public final class AesGcmExample {
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    public record EncryptedPayload(byte[] nonce, byte[] ciphertext) {}

    public static SecretKey newDemoKey() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        return generator.generateKey();
    }

    public static EncryptedPayload encrypt(
            SecretKey key,
            byte[] plaintext,
            byte[] authenticatedMetadata) throws Exception {

        byte[] nonce = new byte[NONCE_BYTES];
        new SecureRandom().nextBytes(nonce);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.ENCRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(authenticatedMetadata);

        byte[] ciphertext = cipher.doFinal(plaintext);
        return new EncryptedPayload(nonce, ciphertext);
    }

    public static byte[] decrypt(
            SecretKey key,
            EncryptedPayload encrypted,
            byte[] authenticatedMetadata) throws Exception {

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(
                Cipher.DECRYPT_MODE,
                key,
                new GCMParameterSpec(TAG_BITS, encrypted.nonce()));
        cipher.updateAAD(authenticatedMetadata);

        try {
            return cipher.doFinal(encrypted.ciphertext());
        } catch (AEADBadTagException ex) {
            throw new SecurityException(
                    "Checkpoint payload authentication failed", ex);
        }
    }

    public static void main(String[] args) throws Exception {
        SecretKey key = newDemoKey();
        byte[] metadata = "artifact=demo;format=1"
                .getBytes(StandardCharsets.UTF_8);
        byte[] plaintext = "sample checkpoint payload"
                .getBytes(StandardCharsets.UTF_8);

        EncryptedPayload encrypted = encrypt(key, plaintext, metadata);
        byte[] restored = decrypt(key, encrypted, metadata);

        if (!Arrays.equals(plaintext, restored)) {
            throw new IllegalStateException("Plaintext mismatch");
        }
    }
}
~~~

Đây chỉ là ví dụ cho một payload nằm trong bộ nhớ. Không dùng cách đọc toàn bộ checkpoint thành byte array vì checkpoint có thể rất lớn. Định dạng thực tế cần hỗ trợ streaming hoặc chunk encryption, lưu nonce/tag, wrapped DEK và manifest. Nếu authentication thất bại, phải dừng restore và coi artifact là không đáng tin cậy.

Trong production, thay hàm tạo demo key bằng quy trình KMS generate-data-key hoặc một key service đã được phê duyệt. Không serialize plaintext SecretKey vào manifest hoặc checkpoint package.

## 10. Mã hóa checkpoint lớn theo chunk

Checkpoint có thể lớn đến hàng trăm MB hoặc nhiều GB. Đọc toàn bộ artifact vào heap để mã hóa sẽ làm tăng memory pressure và có thể tạo một checkpoint lớn hơn hoặc gây OOM. Nên dùng streaming encryption hoặc chia file thành các chunk có kích thước giới hạn.

Một định dạng chunk cần lưu tối thiểu:

- Artifact ID và format version.
- File ID hoặc relative path đã chuẩn hóa.
- Chunk index và tổng số chunk hoặc thông tin final marker.
- Nonce duy nhất cho chunk.
- Ciphertext và authentication tag.
- Plaintext length hoặc ciphertext length.
- Metadata cần thiết để kiểm tra thứ tự và tính đầy đủ.

AAD có thể chứa artifact ID, file path, chunk index và format version. Nhờ đó, một chunk không thể bị tráo giữa hai file hoặc hai artifact mà không làm authentication thất bại.

~~~text
Artifact
  |
  +-- File A
  |     +-- Chunk 0 -> nonce 0 -> AEAD -> ciphertext + tag
  |     +-- Chunk 1 -> nonce 1 -> AEAD -> ciphertext + tag
  |     +-- Chunk 2 -> nonce 2 -> AEAD -> ciphertext + tag
  |
  +-- File B
  |     +-- Chunk 0 -> nonce 3 -> AEAD -> ciphertext + tag
  |     +-- Chunk 1 -> nonce 4 -> AEAD -> ciphertext + tag
  |
  +-- Authenticated manifest
        +-- file list
        +-- chunk counts
        +-- wrapped DEK
        +-- algorithm and format version
~~~

Mỗi chunk cần được xác thực trước khi dữ liệu plaintext của chunk đó được chuyển cho bước tiếp theo. Khi restore, kiểm tra đủ số chunk, đúng thứ tự, đúng kích thước và đúng file list trong manifest. Một manifest có chữ ký/MAC hoặc được xác thực qua AAD giúp phát hiện việc xóa, thêm, đổi tên hoặc tráo thành phần.

Nếu upload multipart, không coi việc upload từng part thành công là artifact đã hoàn chỉnh. Chỉ publish một manifest/commit marker sau khi tất cả file và chunk đã được upload, xác minh và finalize thành công.

## 11. Nén trước khi mã hóa

Checkpoint có thể chứa nhiều vùng bộ nhớ có khả năng nén. Nếu cần nén để giảm dung lượng, thứ tự phổ biến là:

1. Hoàn tất checkpoint.
2. Đóng gói hoặc nén các file theo định dạng cần thiết.
3. Mã hóa package hoặc từng chunk.
4. Upload ciphertext.

Mã hóa làm dữ liệu trông gần như ngẫu nhiên, nên nén sau mã hóa thường không giảm dung lượng đáng kể. Nén trước mã hóa thường hiệu quả hơn.

Tuy nhiên, nén có thể tăng CPU và memory usage, ảnh hưởng thời gian checkpoint pipeline. Hãy đo tỷ lệ nén, thời gian CPU, thời gian I/O và tổng thời gian từ lúc checkpoint hoàn tất đến lúc artifact sẵn sàng.

Nếu threat model có side-channel theo kích thước, cần cân nhắc padding hoặc bucket size. Kích thước ciphertext có thể tiết lộ gần đúng kích thước artifact hoặc thay đổi giữa các phiên bản. Padding tăng storage và bandwidth nên chỉ áp dụng khi cần thiết.

## 12. Bảo vệ manifest và metadata

Manifest thường mô tả cách khôi phục artifact. Nó có thể chứa:

- Artifact ID, build ID và timestamp.
- JDK vendor/version/build và CRaC runtime metadata.
- Danh sách file, kích thước, thứ tự hoặc checksum.
- Algorithm, nonce format, key ID và wrapped DEK.
- OS/architecture hoặc platform profile.
- Phiên bản ứng dụng và cấu hình tương thích.
- Thông tin phục vụ restore hoặc kiểm tra.

Metadata có thể tiết lộ topology, đường dẫn nội bộ, phiên bản runtime hoặc tên service. Hãy mã hóa manifest nếu các trường này nhạy cảm. Nếu manifest cần được đọc trước khi lấy khóa giải mã, giữ phần header tối thiểu và không nhạy cảm ở bên ngoài, còn phần metadata nhạy cảm nằm trong vùng được mã hóa.

Manifest phải được xác thực. Một cách là ký số bằng signing key riêng; cách khác là dùng MAC hoặc đưa các trường quan trọng vào AAD của AEAD. Không dùng cùng một key tùy tiện cho cả encryption và signing. Dùng key purpose riêng và policy riêng.

Manifest cần ràng buộc artifact ID, file list, chunk count, size, algorithm và wrapped DEK. Nếu attacker thay manifest để trỏ đến wrapped key khác hoặc sắp xếp lại chunk, bước xác thực phải phát hiện.

## 13. Hash, MAC và chữ ký số

Các cơ chế này có mục đích khác nhau:

| Cơ chế | Bảo vệ | Dùng khi |
|---|---|---|
| Hash (ví dụ SHA-256) | Phát hiện thay đổi so với digest đã biết | Kiểm tra corruption hoặc so sánh nội dung khi digest được bảo vệ riêng |
| MAC (ví dụ HMAC-SHA-256) | Toàn vẹn và xác thực bằng khóa bí mật chung | Producer và restore service cùng được phép dùng shared secret |
| Chữ ký số | Toàn vẹn và nguồn gốc bằng private/public key | Producer ký; restore service chỉ cần public key để xác minh |
| AEAD tag | Toàn vẹn/xác thực ciphertext và AAD | Xác thực từng file/chunk trong lúc giải mã |

Nếu dùng hash, digest phải được bảo vệ bằng MAC, chữ ký hoặc kênh tin cậy. Một file SHA-256 đặt cạnh ciphertext trong cùng storage không chống được attacker có quyền thay cả hai.

Chữ ký số có ích khi nhiều môi trường được phép restore nhưng không được phép tạo artifact. Chỉ pipeline tạo checkpoint giữ signing private key; restore service chỉ giữ public key tin cậy. Điều này tách quyền phát hành artifact khỏi quyền sử dụng artifact.

## 14. Quản lý khóa với KMS hoặc HSM

KMS/HSM giúp lưu và sử dụng key material trong một ranh giới quản lý riêng. Ứng dụng có thể yêu cầu KMS tạo data key, wrap DEK, unwrap DEK hoặc ký manifest mà không cần export KEK.

Một thiết kế khóa nên xác định:

- Key owner và team chịu trách nhiệm.
- Key purpose: encrypt checkpoint, sign manifest hoặc bảo vệ transport.
- Môi trường: development, staging, production.
- Tenant hoặc application boundary.
- Region và disaster recovery.
- Rotation schedule và retention.
- Principal được phép encrypt, decrypt, wrap, unwrap hoặc sign.
- Audit event và alert khi key usage bất thường.

Không dùng một key duy nhất cho mọi môi trường nếu chính sách yêu cầu cách ly. Tách key theo môi trường hoặc tenant giúp giảm blast radius. Có thể dùng một KEK riêng cho từng môi trường và DEK mới cho từng artifact.

Không đặt KEK hoặc plaintext DEK trong source code, image, biến môi trường lâu dài, manifest hoặc file checkpoint. KMS key ID không phải secret, nhưng quyền sử dụng key là tài sản cần kiểm soát.

## 15. Tách quyền tạo checkpoint và quyền restore

Pipeline tạo checkpoint và workload restore có thể cần quyền khác nhau.

| Principal | Quyền thường cần | Quyền nên hạn chế |
|---|---|---|
| Checkpoint builder | Tạo DEK, encrypt, wrap DEK, upload artifact, ký manifest | Decrypt artifact production nếu không cần |
| Artifact publisher | Publish object đã mã hóa và manifest đã ký | Truy cập plaintext DEK |
| Restore workload | Đọc artifact, xác minh chữ ký, unwrap DEK, decrypt | Tạo hoặc thay thế artifact production |
| Storage operator | Quản lý lifecycle/replication theo policy | Không mặc nhiên có quyền giải mã client-side |
| KMS administrator | Quản lý key policy, rotation và trạng thái key | Không tự động cần quyền đọc checkpoint |
| Auditor | Đọc audit log và metadata được phép | Không cần quyền decrypt |

Tách quyền giúp giảm rủi ro một tài khoản bị chiếm đoạt có thể vừa tạo artifact giả, vừa thay artifact, vừa giải mã mọi checkpoint. Có thể dùng workload identity và short-lived credential để cấp quyền theo từng job.

Restore role nên chỉ decrypt artifact được phép, ví dụ theo key, prefix, environment, application hoặc tag. Tránh policy rộng cho phép bất kỳ service account nào cũng unwrap mọi DEK.

## 16. Rotation và vòng đời khóa

Rotation cần được thiết kế trước khi artifact được lưu dài hạn. Một checkpoint được tạo hôm nay có thể cần restore sau nhiều tháng. Nếu KEK bị xóa hoặc key version không còn khả dụng, artifact có thể không giải mã được.

Với envelope encryption, có thể rotation KEK bằng cách unwrap DEK bằng key version cũ rồi wrap lại bằng key version mới, nếu KMS và policy hỗ trợ. Khi đó không nhất thiết phải giải mã và mã hóa lại toàn bộ checkpoint ciphertext.

Các nguyên tắc:

- Ghi key ID và version cần thiết trong manifest đã xác thực.
- Giữ key version cũ trong thời gian còn artifact cần restore.
- Test quy trình rewrap và restore sau rotation.
- Không xóa key chỉ vì đã chuyển ứng dụng sang version mới.
- Có quy trình revoke khẩn cấp khi key bị lộ.
- Lưu bản backup hoặc cơ chế recovery của key theo chính sách KMS.
- Kiểm tra artifact retention và key retention có cùng vòng đời hay không.

Xóa KEK có thể làm mất khả năng giải mã toàn bộ artifact được bảo vệ bởi key đó. Đây có thể là một cách cryptographic erasure, nhưng chỉ khi mọi bản sao, key version, backup và wrapped DEK không còn đường khôi phục. Hãy hiểu rõ chính sách KMS trước khi dùng xóa khóa như cơ chế xóa dữ liệu.

## 17. Mã hóa trong pipeline upload

Một pipeline upload an toàn có thể thực hiện:

1. Chờ runtime báo checkpoint đã hoàn tất.
2. Kiểm tra danh sách file và kích thước mong đợi.
3. Đóng gói hoặc nén nếu định dạng yêu cầu.
4. Tạo DEK riêng cho artifact.
5. Mã hóa file/chunk bằng AEAD.
6. Tạo manifest ràng buộc file, chunk, nonce, key ID và version.
7. Ký hoặc xác thực manifest.
8. Upload ciphertext qua TLS.
9. Kiểm tra object size, checksum và upload completion.
10. Publish manifest/commit marker sau cùng.
11. Ghi audit event và cleanup staging plaintext.

Dùng staging location riêng cho mỗi lần tạo artifact. Tránh ghi đè trực tiếp lên một object đang được restore hoặc một artifact đã publish. Nếu upload bị gián đoạn, artifact chưa hoàn chỉnh phải được đánh dấu chưa sử dụng và được dọn theo retention policy.

Nếu dùng multipart upload, cần lưu trạng thái upload ở nơi an toàn và có thể tiếp tục theo thiết kế. Tuy nhiên, không được tái sử dụng nonce dưới cùng DEK cho plaintext khác khi retry mã hóa. Cách đơn giản là dùng DEK mới cho lần mã hóa mới; nếu tiếp tục upload ciphertext đã mã hóa, giữ nguyên đúng các chunk ciphertext đã tạo và không mã hóa lại chúng bằng nonce cũ với nội dung khác.

## 18. Mã hóa trong pipeline restore

Một quy trình restore có kiểm soát:

1. Xác thực workload identity của instance restore.
2. Kiểm tra artifact ID, environment, version và policy có cho phép restore không.
3. Tải manifest qua TLS và xác minh chữ ký/MAC.
4. Lấy wrapped DEK và yêu cầu KMS unwrap bằng quyền giới hạn.
5. Tải ciphertext qua TLS.
6. Xác minh từng chunk bằng AEAD tag và AAD.
7. Kiểm tra đủ file, chunk, size và metadata trong manifest.
8. Giải mã vào thư mục staging được bảo vệ.
9. Kiểm tra quyền file, owner, cấu trúc và compatibility metadata.
10. Chỉ chuyển artifact sang vị trí restore sau khi toàn bộ package đã xác minh.
11. Gọi cơ chế restore theo tài liệu JDK/runtime.
12. Giữ readiness ở trạng thái chưa sẵn sàng cho đến khi ứng dụng và dependency phục hồi.

Không giải mã và restore từng phần theo cách khiến tiến trình có thể khởi động từ một package chưa hoàn chỉnh. Nếu runtime yêu cầu cả một checkpoint directory nhất quán, hãy hoàn thành xác minh toàn bộ trước khi đưa directory đó cho runtime.

Nếu AEAD tag không hợp lệ, manifest signature sai, chunk bị thiếu hoặc file list không khớp, dừng restore. Không tự bỏ qua file lỗi hoặc thử giải mã bằng một key tùy tiện.

## 19. Tránh plaintext tạm thời và file còn sót

Một điểm yếu phổ biến là mã hóa object cuối cùng nhưng để lại bản plaintext ở thư mục tạm. Ví dụ, pipeline tạo archive không mã hóa, sau đó mã hóa archive rồi upload. Nếu archive gốc vẫn còn, mục tiêu bảo vệ at-rest chưa đạt.

Cần kiểm tra:

- Thư mục checkpoint gốc có nằm trên encrypted volume không?
- Archive plaintext có bị xóa sau mã hóa không?
- File tạm có được tạo với quyền chỉ owner đọc/ghi không?
- Crash hoặc process kill có để lại file plaintext không?
- Temporary directory có bị backup hoặc đồng bộ tự động không?
- Swap, core dump hoặc diagnostic dump có thể chứa plaintext không?
- Restore có tạo bản giải mã ở volume bảo vệ không?
- Cleanup có chạy khi pipeline lỗi giữa chừng không?

Secure deletion trên SSD, copy-on-write filesystem hoặc object storage versioning không đơn giản là ghi đè file rồi xóa. Nếu cần xóa mạnh, dùng encrypted storage và hủy key theo chính sách cryptographic erasure, đồng thời quản lý mọi bản backup/key version.

Tmpfs tránh ghi file tạm xuống disk trong một số cấu hình nhưng không tự động giải quyết mọi rủi ro. Nội dung vẫn ở memory, có thể bị swap hoặc xuất hiện trong dump tùy cấu hình. Hãy xem xét toàn bộ host policy.

## 20. Kiểm soát quyền trên storage và artifact repository

Mã hóa không thay thế quyền truy cập storage. Hãy giới hạn ai có thể list, read, write, delete, copy hoặc thay đổi retention của checkpoint artifact.

Các biện pháp thường dùng:

- Bucket/container riêng theo environment hoặc application.
- IAM policy giới hạn theo prefix, tag hoặc resource.
- Chỉ pipeline được phép publish artifact chính thức.
- Versioning hoặc immutable retention khi cần chống sửa/xóa.
- Audit log cho read, write, delete và key usage.
- Không dùng public object hoặc ACL rộng.
- Hạn chế quyền tải checkpoint về máy cá nhân.
- Phân quyền riêng cho backup và restore operator.
- Đặt retention theo nhu cầu khôi phục và chính sách dữ liệu.

Nếu dùng pre-signed URL, giới hạn thời gian, method, object và quyền. Không log URL đầy đủ vì query string có thể là bearer credential. TLS vẫn cần được bật và certificate phải được xác minh.

## 21. Truyền tải qua TLS, mTLS và SFTP

Các phương thức thường gặp:

| Kênh | Khi phù hợp | Lưu ý |
|---|---|---|
| HTTPS/TLS | Upload/download qua object storage hoặc artifact API | Xác minh certificate và hostname |
| mTLS | Service-to-service cần xác thực hai phía | Quản lý client certificate và rotation |
| SFTP/SSH | Truyền file qua máy chủ được kiểm soát | Xác minh host key; giới hạn user và thư mục |
| Private network/VPN | Giảm exposure của endpoint | Không thay thế mã hóa ứng dụng hoặc TLS nếu policy yêu cầu |
| Service mesh TLS | Bảo vệ hop giữa workload | Xác định TLS termination và mọi hop còn lại |

Không tự xây dựng protocol mã hóa qua TCP. Dùng TLS hoặc giao thức đã được kiểm chứng. Với SFTP, kiểm tra host key thay vì chấp nhận mọi server key; nếu không, client có thể gửi artifact đến server giả mạo.

## 22. Xác minh nguồn gốc và chống rollback artifact

Mã hóa và chữ ký có thể chứng minh artifact không bị thay đổi sau khi phát hành, nhưng chưa chắc ngăn được việc thay bằng một artifact cũ vẫn hợp lệ.

Ví dụ, attacker có thể thay checkpoint mới bằng checkpoint cũ được ký đúng. Chữ ký vẫn hợp lệ, nhưng ứng dụng có thể khởi động từ trạng thái đã lỗi thời.

Nếu rollback là rủi ro, manifest nên chứa:

- Artifact generation hoặc sequence tăng đơn điệu.
- Build/version và deployment release được phép.
- Environment và application identity.
- Creation timestamp từ nguồn đáng tin cậy.
- Expiration hoặc policy về thời gian sử dụng.
- Checkpoint lineage hoặc parent ID nếu cần.

Restore service cần so sánh generation với policy hoặc metadata bền vững bên ngoài artifact. Không chỉ tin timestamp do artifact tự khai báo. Có thể cần lưu allowlist hoặc minimum generation trong control plane có tính toàn vẹn.

## 23. Hiệu năng và dung lượng

Mã hóa, xác thực, nén và truyền tải đều tiêu thụ CPU hoặc I/O. Với checkpoint lớn, thời gian pipeline có thể trở thành một phần đáng kể của thời gian triển khai.

Các yếu tố cần đo:

- Kích thước checkpoint trước và sau nén.
- Throughput mã hóa/giải mã theo CPU quota thực tế.
- Chunk size và số worker mã hóa song song.
- Thời gian KMS generate/wrap/unwrap.
- Upload/download throughput và retry.
- Storage request count và chi phí.
- Memory usage của buffer trong pipeline.
- Thời gian xác minh manifest/chữ ký.
- Thời gian từ checkpoint complete đến artifact publish.
- Thời gian từ restore request đến khi plaintext sẵn sàng.

Không tạo quá nhiều worker mã hóa dựa trên số CPU host. Trong container, hãy tính CPU quota và cgroup throttling. Chunk quá nhỏ làm tăng overhead metadata và tag; chunk quá lớn làm tăng memory cần thiết và làm retry tốn kém. Chọn kích thước bằng benchmark trên workload thực tế.

Nén trước mã hóa thường giảm storage và network cost, nhưng có thể tăng CPU. Với CPU quota thấp, pipeline nén có thể làm chậm quá trình publish hoặc restore. Hãy đo cả latency lẫn resource usage.

## 24. KMS availability và disaster recovery

Client-side encryption tạo dependency vào KMS hoặc key service khi restore. Nếu KMS ở region không khả dụng, ứng dụng có thể không giải mã được checkpoint dù object storage vẫn hoạt động.

Cần thiết kế:

- KMS key replication hoặc multi-region key nếu nền tảng hỗ trợ.
- Policy restore trong region dự phòng.
- Identity có quyền unwrap tại môi trường disaster recovery.
- Backup và retention của key metadata.
- Quy trình khôi phục khi key bị disable hoặc rotation.
- Kiểm thử restore khi primary region mất.
- Alert khi key sắp hết hạn hoặc bị disable.
- Runbook cho trường hợp KMS quota hoặc throttling.

Không copy plaintext DEK sang một nơi kém bảo vệ chỉ để dự phòng KMS. Hãy dùng cơ chế backup/recovery được KMS/HSM hỗ trợ và kiểm thử bằng một artifact thực.

## 25. Những giới hạn của mã hóa

Mã hóa artifact rất quan trọng nhưng không bảo vệ mọi tình huống.

Mã hóa at rest không bảo vệ plaintext khi volume đã mount và process có quyền đọc. TLS không bảo vệ dữ liệu sau khi TLS terminate. Client-side encryption không bảo vệ trước máy tạo checkpoint đã bị chiếm quyền trước khi mã hóa hoặc máy restore đã bị chiếm quyền sau khi giải mã.

Mã hóa cũng không tự ngăn:

- Người có quyền decrypt hợp lệ truy cập dữ liệu.
- Malware hoặc process độc hại trên máy restore đọc plaintext.
- Credential bị lộ qua log, environment, debugger hoặc core dump.
- Attacker xóa artifact gây denial of service.
- Rollback về checkpoint cũ nếu không có policy chống rollback.
- Metadata hoặc kích thước artifact bị lộ nếu không được mã hóa/padding.
- KMS administrator hoặc key policy sai cấp quyền quá rộng.

Vì vậy, cần kết hợp mã hóa với endpoint security, IAM, audit, secret management, integrity verification, retention và quy trình vận hành.

## 26. Ví dụ manifest cho checkpoint đã mã hóa

Một manifest có thể có cấu trúc logic như sau:

~~~json
{
  "formatVersion": 1,
  "artifactId": "service-a-2026-11-13-build-42",
  "application": "service-a",
  "environment": "production",
  "runtime": {
    "jdkVendor": "approved-vendor",
    "jdkVersion": "approved-build",
    "architecture": "linux-x86_64"
  },
  "encryption": {
    "algorithm": "AES-256-GCM",
    "keyManagement": "envelope",
    "kmsKeyId": "kms-key-reference",
    "wrappedDataKey": "base64-ciphertext",
    "nonceFormat": "artifact-prefix-plus-chunk-counter"
  },
  "files": [
    {
      "id": "memory-0",
      "path": "checkpoint/memory.img",
      "plaintextSize": 123456789,
      "chunkCount": 12
    }
  ],
  "generation": 42
}
~~~

Đây là ví dụ cấu trúc minh họa, không phải schema CRaC chuẩn. Không nên để plaintext key hoặc secret trong manifest. Nếu tên file hoặc runtime metadata nhạy cảm, mã hóa phần manifest đó hoặc chỉ để một header tối thiểu ở ngoài.

Manifest thực tế cần xác thực bằng chữ ký/MAC hoặc được ràng buộc bằng AAD. Các trường artifactId, formatVersion, file path, size, chunk count, generation và key reference phải được bảo vệ để attacker không thể thay metadata mà vẫn vượt qua kiểm tra.

## 27. Kiểm thử mã hóa và restore

Không chỉ kiểm tra rằng upload/download trả về HTTP 200. Cần chứng minh artifact không thể đọc khi không có quyền, thay đổi bị phát hiện và restore hợp lệ vẫn hoạt động.

Các kịch bản:

1. Tạo checkpoint trong môi trường test có dữ liệu giả lập nhạy cảm.
2. Đóng gói và mã hóa artifact.
3. Kiểm tra storage chỉ chứa ciphertext theo thiết kế; không còn archive plaintext trong staging.
4. Tải artifact bằng principal chỉ có quyền đọc object nhưng không có quyền decrypt.
5. Xác nhận principal đó không thể lấy plaintext.
6. Restore bằng principal được phép; xác minh KMS unwrap và AEAD authentication thành công.
7. Sửa một byte ciphertext và xác nhận giải mã thất bại.
8. Sửa manifest, file list, chunk order hoặc wrapped DEK và xác nhận signature/MAC/AAD validation thất bại.
9. Thay artifact bằng một generation cũ và xác nhận rollback policy từ chối nếu policy yêu cầu.
10. Làm gián đoạn upload giữa các chunk và xác nhận artifact chưa được publish.
11. Làm gián đoạn download/restore và xác nhận plaintext staging được cleanup theo chính sách.
12. Rotate KEK, rewrap DEK và restore lại artifact cũ.
13. Thử restore trong region dự phòng hoặc khi KMS primary tạm thời không sẵn sàng.
14. Đo CPU, memory, I/O và thời gian cho artifact lớn dưới resource limit thực tế.

Không dùng dữ liệu production thật để thử mã hóa nếu không có quy trình bảo vệ phù hợp. Dùng secret giả lập và kiểm tra rằng chúng không xuất hiện trong log hoặc artifact plaintext.

## 28. Những lỗi thường gặp

**Chỉ mã hóa khi truyền tải.** Artifact sau khi ghi vào storage có thể vẫn là plaintext. Cần mã hóa at rest.

**Chỉ bật server-side encryption rồi bỏ qua quyền đọc object.** Principal có quyền đọc object và dùng key có thể nhận plaintext. Kiểm soát IAM và cân nhắc client-side encryption theo threat model.

**Chỉ mã hóa một file trong checkpoint directory.** Metadata hoặc file phụ trợ vẫn có thể lộ dữ liệu. Inventory và bảo vệ toàn bộ package.

**Dùng checksum như bằng chứng xác thực.** Attacker có thể thay cả file và checksum. Dùng AEAD, MAC hoặc chữ ký số.

**Tái sử dụng nonce với cùng AES-GCM key.** Điều này có thể phá vỡ tính bảo mật. Bảo đảm nonce duy nhất theo DEK, đặc biệt khi mã hóa chunk và retry.

**Lưu plaintext DEK hoặc KEK cạnh ciphertext.** Người có artifact có thể giải mã. Dùng envelope encryption và KMS/HSM.

**Xóa key cũ quá sớm.** Artifact backup có thể không restore được. Đồng bộ key retention với artifact retention và kiểm thử rotation.

**Để archive plaintext trong thư mục tạm.** Mã hóa object cuối không loại bỏ bản sao plaintext. Bảo vệ staging và cleanup cả khi lỗi.

**Tin TLS bảo vệ nội dung sau khi lưu.** TLS chỉ bảo vệ phiên truyền. Storage cần encryption at rest và integrity.

**Không xác minh certificate hoặc host key.** Artifact có thể bị gửi đến endpoint giả mạo. Bật xác thực server và quản lý trust material.

**Publish artifact trước khi upload hoàn tất.** Restore có thể đọc package thiếu file/chunk. Chỉ publish manifest/commit marker sau khi hoàn tất xác minh.

**Không ràng buộc manifest với artifact.** Attacker có thể tráo file, chunk hoặc metadata. Ký/xác thực manifest và dùng AAD cho từng chunk.

**Đặt quyền decrypt quá rộng.** Một service account có thể giải mã mọi môi trường. Tách key, role và policy theo application/environment.

**Không thử restore sau rotation hoặc DR.** Artifact có thể tồn tại nhưng key không còn khả dụng. Kiểm thử phục hồi bằng artifact thực trong môi trường kiểm soát.

## 29. Checklist bảo vệ checkpoint artifact

- [ ] Đã xác định dữ liệu nhạy cảm có thể xuất hiện trong checkpoint chưa?
- [ ] Đã inventory toàn bộ file, metadata, manifest, backup và temporary file chưa?
- [ ] Checkpoint chỉ được đóng gói/mã hóa sau khi runtime xác nhận hoàn tất chưa?
- [ ] Có mã hóa at rest cho disk, volume, object storage và backup không?
- [ ] Artifact có được mã hóa client-side nếu threat model yêu cầu không?
- [ ] Upload/download có dùng TLS và xác minh certificate/hostname không?
- [ ] Mọi hop sau TLS termination có được bảo vệ không?
- [ ] Đã chọn AEAD và bảo đảm nonce duy nhất theo key chưa?
- [ ] Artifact lớn có được mã hóa theo chunk mà không nạp toàn bộ vào heap không?
- [ ] Manifest, file list, chunk count, size và generation có được xác thực không?
- [ ] Có envelope encryption với DEK riêng và KEK được quản lý trong KMS/HSM không?
- [ ] Quyền encrypt, decrypt, sign, publish và read storage đã được tách chưa?
- [ ] Key rotation, key retention và disaster recovery đã được kiểm thử chưa?
- [ ] Không có plaintext DEK, KEK hoặc credential trong artifact/manifest/log không?
- [ ] Temporary plaintext và staging directory được bảo vệ và cleanup khi lỗi chưa?
- [ ] Storage policy có hạn chế list/read/write/delete và audit không?
- [ ] Có chống rollback nếu cần bảo đảm generation mới nhất không?
- [ ] Restore chỉ chạy sau khi signature/MAC/AEAD và file completeness được xác minh không?
- [ ] Readiness chỉ thành công sau khi decrypt và restore dependency hoàn tất không?
- [ ] Đã thử sửa ciphertext, manifest, chunk, upload interruption và key rotation chưa?

## Kết luận

Checkpoint artifact có thể chứa dữ liệu nhạy cảm của toàn bộ tiến trình, vì vậy cần được bảo vệ như một tài sản bảo mật. Mã hóa at rest bảo vệ dữ liệu trên disk, volume, object storage và backup; TLS bảo vệ dữ liệu khi upload/download. Với yêu cầu bảo vệ mạnh hơn ở ranh giới storage, client-side envelope encryption cho phép mã hóa artifact bằng DEK riêng và bảo vệ DEK bằng KMS/HSM.

Một quy trình an toàn cần xác thực manifest, dùng AEAD với nonce duy nhất, kiểm tra đầy đủ file/chunk, tách quyền tạo và restore, quản lý rotation/retention của khóa và tránh để lại plaintext tạm thời. Sau restore, chỉ giải mã bằng identity được phép, xác minh artifact hoàn chỉnh rồi mới giao cho runtime. Mã hóa không thay thế bảo vệ endpoint hoặc kiểm soát quyền, nhưng khi kết hợp với TLS, IAM, audit và kiểm thử khôi phục, nó giúp giảm đáng kể rủi ro lộ hoặc bị sửa đổi checkpoint trong lưu trữ và truyền tải.
