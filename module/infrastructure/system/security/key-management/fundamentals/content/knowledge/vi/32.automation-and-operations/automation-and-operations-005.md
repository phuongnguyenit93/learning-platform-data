# Key version rollout

**Key version rollout** là quá trình đưa một phiên bản khóa mới vào hệ thống, chuyển các ứng dụng và workload sang sử dụng phiên bản đó theo từng giai đoạn, đồng thời duy trì khả năng xử lý dữ liệu đã được bảo vệ bằng các phiên bản trước. Quy trình này thường diễn ra khi xoay vòng khóa, thay đổi thuật toán, khắc phục sự cố lộ khóa hoặc đáp ứng chính sách bảo mật.

Một lần tạo key version mới chưa có nghĩa mọi dữ liệu đã được chuyển sang khóa mới. Ciphertext cũ vẫn phụ thuộc vào khóa đã mã hóa nó. Ứng dụng phải biết phiên bản nào cần dùng cho thao tác mã hóa mới và phiên bản nào cần dùng để giải mã dữ liệu hiện có.

Một chiến lược rollout phổ biến là **single-write, multi-read**: sau khi chuyển đổi, hệ thống chỉ mã hóa dữ liệu mới bằng phiên bản khóa đang hoạt động, nhưng vẫn có thể đọc dữ liệu được mã hóa bằng các phiên bản cũ còn được phép sử dụng. Sau đó, tổ chức có thể re-encrypt dữ liệu cũ theo kế hoạch trước khi vô hiệu hóa hoặc hủy khóa cũ.

Rollout an toàn cần phối hợp key management, ứng dụng, metadata dữ liệu, KMS/HSM, cache, bản sao lưu, monitoring và quy trình rollback. Nếu chỉ thay alias hoặc cấu hình ở một nơi, các consumer còn lại có thể tiếp tục dùng phiên bản cũ hoặc mất khả năng giải mã dữ liệu.

## 1. Key version là gì?

Key version là một phiên bản cụ thể của vật liệu khóa hoặc một khóa được quản lý trong một vòng đời có version. Mỗi version có định danh riêng và các metadata như thuật toán, trạng thái, thời điểm tạo, mục đích sử dụng và chính sách truy cập.

Ví dụ, một khóa mã hóa dữ liệu có thể có các phiên bản:

| Key version | Trạng thái | Vai trò |
|---|---|---|
| v1 | Decrypt-only | Giải mã dữ liệu đã mã hóa trước đây |
| v2 | Active | Mã hóa dữ liệu mới và giải mã dữ liệu v2 |
| v3 | Pending rollout | Đã tạo, đang kiểm thử trước khi đưa vào sử dụng |

Tên trạng thái và khả năng quản lý version phụ thuộc KMS/HSM hoặc nền tảng. Một số dịch vụ có key object và các version bên dưới; một số hệ thống biểu diễn mỗi version như một key resource riêng; một số dùng alias hoặc primary version để chọn khóa hiện hành.

Cần phân biệt:

- **Key identity:** định danh ổn định của đối tượng khóa hoặc logical key.
- **Key version ID:** định danh của một phiên bản cụ thể.
- **Alias:** tên tham chiếu có thể trỏ tới key hoặc version hiện hành.
- **Key material:** vật liệu mật mã thực tế của phiên bản.
- **Key metadata:** thuật toán, trạng thái, usage, thời điểm tạo và các thuộc tính quản lý.

Alias giúp ứng dụng không phải thay đổi cấu hình mỗi khi có version mới, nhưng dữ liệu đã mã hóa vẫn cần lưu đủ thông tin để xác định đúng version khi giải mã. Không nên dựa vào alias hiện tại để giải mã ciphertext cũ vì alias có thể đã được chuyển sang version khác.

## 2. Vì sao cần rollout theo giai đoạn?

Key version rollout thường liên quan đến nhiều consumer và dữ liệu được tạo ở các thời điểm khác nhau. Chuyển đổi tức thời có thể làm gián đoạn dịch vụ hoặc khiến dữ liệu cũ không thể đọc.

Các nguyên nhân phổ biến cần rollout:

- **Scheduled rotation:** thay khóa theo chu kỳ để giới hạn thời gian sử dụng một phiên bản.
- **Key compromise:** thay phiên bản bị nghi ngờ hoặc xác nhận đã lộ.
- **Algorithm migration:** chuyển từ thuật toán hoặc tham số cũ sang cấu hình mới.
- **Policy change:** đáp ứng yêu cầu về độ dài khóa, thuật toán, vùng lưu trữ hoặc HSM.
- **Operational recovery:** thay khóa sau khi khôi phục hệ thống hoặc thay đổi ranh giới tin cậy.

Rollout theo giai đoạn giúp kiểm tra tính tương thích, giới hạn phạm vi lỗi và quan sát hành vi của từng consumer. Tuy nhiên, nếu khóa cũ bị xâm phạm, thời gian chuyển tiếp phải được rút ngắn theo kế hoạch ứng phó sự cố. Không giữ khóa bị lộ chỉ vì quy trình rollout thông thường cần thời gian dài; cần đánh giá riêng việc chấp nhận rủi ro, re-encrypt dữ liệu và thu hồi.

## 3. Single-write, multi-read

Mô hình single-write, multi-read tách biệt hai quyết định:

- **Write version:** phiên bản được dùng để mã hóa hoặc bảo vệ dữ liệu mới.
- **Read versions:** các phiên bản còn được phép dùng để giải mã hoặc xử lý dữ liệu cũ.

Ví dụ, khi v2 được kích hoạt:

- Tất cả thao tác mã hóa mới chọn v2.
- Dữ liệu cũ có key version v1 tiếp tục được giải mã bằng v1.
- Dữ liệu tạo sau thời điểm rollout mang key version v2.
- Khi dữ liệu v1 được đọc và ghi lại, hệ thống có thể mã hóa lại bằng v2.

Mô hình này tránh việc phải chuyển toàn bộ dữ liệu trong cùng một thời điểm. Nó cũng giúp triển khai ứng dụng theo từng nhóm: phiên bản ứng dụng mới hiểu cả v1 và v2, trong khi phiên bản cũ có thể được giữ lại trong thời gian kiểm soát trước khi bị loại bỏ.

Không nên để ứng dụng thử lần lượt mọi khóa cho đến khi giải mã thành công. Cách đó làm tăng chi phí, tạo hành vi khó kiểm toán và có thể che giấu lỗi metadata. Ciphertext cần mang key version ID hoặc một định danh có thể phân giải chính xác.

## 4. Metadata cần gắn với ciphertext

Mỗi bản ghi được mã hóa nên mang metadata đủ để giải mã trong tương lai. Tùy định dạng, metadata có thể gồm:

- Format version của bản ghi.
- Key ID hoặc key version ID.
- Thuật toán và profile tham số nếu giao thức cho phép nhiều lựa chọn.
- Nonce hoặc IV.
- Ciphertext và authentication tag.
- Encrypted data key nếu sử dụng envelope encryption.
- Context hoặc metadata cần thiết để tái tạo AAD.

Key version ID cần được lưu cùng dữ liệu đã mã hóa. Nếu chỉ lưu alias, sau khi alias chuyển sang version mới, ứng dụng có thể không biết ciphertext cũ cần khóa nào.

Với AEAD như AES-GCM, metadata ảnh hưởng đến việc giải mã cần được xác thực. Có thể đưa format version, key ID, tenant ID hoặc record ID vào Additional Authenticated Data (AAD) theo một encoding chuẩn hóa. Nếu metadata bị thay đổi, xác thực tag phải thất bại thay vì giải mã dữ liệu trong ngữ cảnh sai.

Không lưu key material bí mật trong metadata. Key ID, version và nonce thường có thể công khai; encrypted data key có thể được lưu cùng ciphertext trong envelope encryption. Quyền đọc metadata và ciphertext vẫn phải tuân theo chính sách dữ liệu của hệ thống.

## 5. Rollout state machine

Một phiên bản khóa có thể đi qua các trạng thái quản lý như sau:

1. **Created:** version mới đã được tạo nhưng chưa dùng cho dữ liệu sản xuất.
2. **Validated:** thuật toán, policy, quyền, backup/recovery và khả năng tương thích đã được kiểm tra.
3. **Canary:** một nhóm nhỏ workload hoặc một tỷ lệ traffic dùng version mới.
4. **Active for write:** version mới trở thành lựa chọn mã hóa mặc định.
5. **Read-compatible:** các phiên bản cũ còn được phép giải mã trong giai đoạn chuyển tiếp.
6. **Decrypt-only:** version cũ không còn được dùng để mã hóa mới nhưng vẫn được giữ để đọc dữ liệu cũ.
7. **Retired:** version không còn được dùng trong hoạt động thường ngày; việc giải mã có thể bị giới hạn theo quy trình riêng.
8. **Destroyed:** vật liệu khóa được hủy theo chính sách sau khi đã xử lý mọi dependency và yêu cầu lưu giữ.

Tên và số lượng trạng thái thực tế tùy hệ thống. Không phải mọi KMS đều có trạng thái canary hoặc decrypt-only ở cấp key version; có thể cần triển khai trạng thái ở control plane của ứng dụng.

~~~text
Created -> Validated -> Canary -> Active for write
                                  |
                                  v
                         Old version: Decrypt-only
                                  |
                                  v
                         Dependency verification
                                  |
                                  v
                              Retired
                                  |
                                  v
                             Destroyed
~~~

Không được chuyển version cũ sang trạng thái không thể giải mã chỉ vì rollout mới đã thành công ở một vài instance. Phải xác minh toàn bộ dữ liệu, backup, replica, consumer offline và yêu cầu lưu trữ trước khi loại bỏ khả năng giải mã.

## 6. Chuẩn bị trước rollout

Trước khi tạo và kích hoạt version mới, cần lập danh mục những thành phần phụ thuộc vào khóa:

- Ứng dụng và workload đang mã hóa hoặc giải mã.
- Dịch vụ dùng alias, key ID hoặc version cụ thể.
- Cơ sở dữ liệu, object storage, message queue và file archive chứa ciphertext.
- Envelope encryption metadata và encrypted data key.
- Backup, snapshot, bản sao ở region khác và dữ liệu lưu trữ dài hạn.
- Batch job, worker ít chạy, consumer offline và hệ thống khôi phục thảm họa.
- Chứng chỉ, chữ ký hoặc token có quan hệ với cặp khóa bất đối xứng nếu phạm vi rollout liên quan.

Ghi lại version hiện tại, policy, key usage, số lượng dữ liệu phụ thuộc và baseline của thao tác mã hóa/giải mã. Xác định rõ chủ sở hữu, người phê duyệt, thời gian triển khai, tiêu chí thành công và điều kiện dừng.

Cần kiểm tra version mới có tương thích với mọi provider và runtime cần dùng hay không. Nếu KMS/HSM có quota, giới hạn request hoặc độ trễ khác nhau giữa các region, phải đánh giá trước khi đưa traffic lớn vào.

## 7. Các giai đoạn rollout

Một quy trình rollout có kiểm soát có thể chia thành các giai đoạn:

| Giai đoạn | Hoạt động | Tiêu chí đi tiếp |
|---|---|---|
| Prepare | Tạo version mới, policy, backup và metadata | Version tồn tại, policy đúng |
| Validate | Kiểm tra encrypt/decrypt, provider, quyền và tương thích | Kiểm thử thành công, audit đầy đủ |
| Deploy reader | Triển khai ứng dụng hiểu version mới nhưng vẫn đọc version cũ | Các consumer đã hỗ trợ format/version |
| Canary writer | Chuyển một nhóm nhỏ thao tác ghi sang version mới | Error rate và latency trong ngưỡng |
| Expand | Tăng dần workload hoặc traffic dùng version mới | Không có lỗi nghiêm trọng, consumer ổn định |
| Promote | Chuyển version mới thành write version mặc định | Tất cả writer đã cập nhật |
| Migrate | Re-encrypt dữ liệu cũ nếu chính sách yêu cầu | Dependency cũ đã giảm hoặc bằng 0 |
| Retire old | Chặn encrypt mới bằng version cũ, giữ decrypt theo policy | Không còn writer và dữ liệu phụ thuộc đã được xử lý |
| Destroy | Hủy vật liệu khóa theo quy trình được phê duyệt | Recovery, retention và audit đã xác nhận |

Không nhất thiết phải re-encrypt toàn bộ dữ liệu ngay sau khi promote. Với một số hệ thống, dữ liệu cũ có thể tiếp tục được giải mã bằng version cũ cho đến khi hết retention hoặc được đọc và ghi lại. Quyết định này phụ thuộc vào chính sách bảo mật, tình trạng khóa và chi phí vận hành.

## 8. Canary và progressive rollout

Canary rollout đưa version mới vào một phạm vi nhỏ trước khi áp dụng toàn hệ thống. Có thể chọn theo:

- Một nhóm workload hoặc service instance.
- Một tenant hoặc phân vùng dữ liệu.
- Một region hoặc availability zone.
- Một tỷ lệ request được kiểm soát.
- Một nhóm dữ liệu thử nghiệm có thể xác minh độc lập.

Theo dõi ít nhất:

- Tỷ lệ encrypt thành công bằng version mới.
- Tỷ lệ decrypt theo từng version.
- Lỗi policy, provider, invalid parameter và authentication tag.
- Latency và số request KMS/HSM.
- Số lượng consumer vẫn ghi bằng version cũ.
- Số bản ghi không có key version ID hoặc metadata không hợp lệ.

Không chỉ quan sát việc ứng dụng nhận được response thành công. Cần xác minh dữ liệu tạo ra thực sự có version mới trong metadata và có thể giải mã bằng đúng version đó ở các consumer khác.

Nếu canary phát sinh lỗi, dừng tăng traffic và giữ lại khả năng đọc cả hai version. Chỉ tiếp tục sau khi xác định nguyên nhân và có bằng chứng kiểm thử.

## 9. Chuyển write version và duy trì read compatibility

Khi version mới đủ điều kiện, control plane hoặc cấu hình ứng dụng có thể chuyển write version. Cần có một nguồn sự thật rõ ràng để mọi writer đọc cùng quyết định, ví dụ cấu hình có version, key alias được quản lý hoặc API của KMS.

Một số lưu ý:

- Ghi lại version được chọn tại thời điểm bắt đầu operation.
- Không thay đổi version giữa một transaction hoặc batch đang thực hiện.
- Cập nhật cache theo version và có thời hạn phù hợp.
- Xử lý các instance chưa nhận cấu hình mới.
- Dùng optimistic concurrency hoặc version check để tránh hai rollout đồng thời ghi đè nhau.
- Đảm bảo read path có thể phân giải version cũ trong toàn bộ giai đoạn chuyển tiếp.

Một instance có thể tiếp tục dùng write version cũ nếu nó giữ cache quá lâu. Vì vậy, cần kiểm soát thời gian cache, cơ chế invalidation và khả năng quan sát version thực tế được dùng trong từng request.

Sau khi chuyển write version, vẫn phải giữ read compatibility cho các dữ liệu cũ. Đừng xóa key cũ khỏi key resolver chỉ vì alias đã trỏ sang version mới.

## 10. Re-encryption và migration dữ liệu

Re-encryption là quá trình giải mã dữ liệu bằng version cũ rồi mã hóa lại bằng version mới. Nó có thể được thực hiện theo hai cách:

- **Bulk migration:** quét và chuyển đổi dữ liệu theo batch.
- **Lazy migration:** chuyển đổi một bản ghi khi nó được đọc hoặc cập nhật trong luồng nghiệp vụ.

Bulk migration giúp đo được tiến độ và giảm thời gian dữ liệu phụ thuộc khóa cũ, nhưng có thể tạo tải lớn cho KMS/HSM và storage. Lazy migration giảm tải tức thời nhưng có thể để lại dữ liệu ít truy cập phụ thuộc version cũ trong thời gian dài.

Khi migration:

1. Đọc metadata và xác định key version chính xác.
2. Xác minh quyền và trạng thái version cũ.
3. Giải mã dữ liệu, chỉ giữ plaintext trong bộ nhớ cần thiết.
4. Mã hóa bằng write version mới.
5. Ghi ciphertext và metadata mới theo transaction hoặc cơ chế atomic update.
6. Xác minh dữ liệu mới có thể giải mã.
7. Ghi nhận kết quả migration và version cũ/mới mà không ghi plaintext hoặc khóa.
8. Chỉ đánh dấu bản ghi hoàn tất khi bước ghi và xác minh thành công.

Nếu ứng dụng dùng envelope encryption, có thể chỉ cần re-wrap data encryption key (DEK) bằng key-encryption key (KEK) mới thay vì giải mã và mã hóa lại toàn bộ dữ liệu. Điều này giảm chi phí nhưng phụ thuộc định dạng envelope và khả năng quản lý encrypted DEK.

## 11. Envelope encryption trong key version rollout

Trong envelope encryption, dữ liệu được mã hóa bằng DEK; DEK được bảo vệ bằng KEK do KMS/HSM quản lý. Khi rollout KEK version mới, hệ thống có thể re-wrap DEK:

- Đọc encrypted DEK hiện tại và metadata version của KEK cũ.
- Yêu cầu KMS/HSM unwrap DEK bằng KEK cũ.
- Yêu cầu bảo vệ lại DEK bằng KEK version mới.
- Lưu encrypted DEK mới cùng key version ID mới.
- Giữ nguyên ciphertext dữ liệu nếu thuật toán và DEK không thay đổi.

Re-wrap không thay đổi plaintext hoặc ciphertext dữ liệu chính, nhưng vẫn là thao tác nhạy cảm vì DEK được xử lý trong quá trình chuyển đổi. Nếu KMS hỗ trợ thao tác re-encrypt hoặc re-wrap nội bộ, ưu tiên thực hiện trong dịch vụ để hạn chế đưa DEK ra ứng dụng.

Không được xóa KEK cũ ngay sau khi re-wrap một phần. Phải xác minh tất cả encrypted DEK, backup, snapshot, archive và replica đã được chuyển đổi hoặc có kế hoạch giữ version cũ.

## 12. Rollback khi rollout gặp lỗi

Rollback cần được thiết kế trước khi rollout. Có thể cần đưa write pointer về version trước, dừng batch migration hoặc triển khai lại phiên bản ứng dụng tương thích.

Một quy tắc quan trọng: **rollback write version không làm cho ciphertext đã tạo bằng version mới tự giải mã được bằng version cũ**. Nếu dữ liệu mới đã được mã hóa bằng v2, hệ thống vẫn phải giữ khả năng giải mã v2 ngay cả khi quay write version về v1.

Rollback an toàn thường gồm:

- Dừng mở rộng canary hoặc rollout.
- Chuyển writer về version đã được xác nhận ổn định nếu policy cho phép.
- Giữ cả v1 và v2 trong read resolver.
- Không xóa ciphertext hoặc metadata đã được tạo trong giai đoạn rollout.
- Xác định dữ liệu đã migrate và chưa migrate.
- Khôi phục cấu hình ứng dụng và cache theo version có kiểm soát.
- Điều tra lỗi và chỉ retry migration sau khi có kế hoạch khắc phục.

Nếu nguyên nhân là key compromise, không được rollback về khóa bị lộ chỉ để khôi phục dịch vụ. Khi đó cần quy trình incident response riêng: thu hồi quyền, cô lập principal, thay khóa, đánh giá dữ liệu bị ảnh hưởng và phục hồi bằng khóa an toàn.

## 13. Retirement và destruction của version cũ

Retirement là ngừng dùng version cũ trong hoạt động bình thường. Destruction là hủy vật liệu khóa theo quy trình không thể đảo ngược hoặc theo khả năng của KMS/HSM.

Trước khi retire hoặc destroy, cần xác minh:

- Không còn writer nào mã hóa bằng version cũ.
- Không còn ciphertext cần đọc bằng version đó, hoặc đã có kế hoạch xử lý.
- Backup, snapshot, archive và replica đã được chuyển đổi hoặc có khả năng khôi phục khác.
- Các consumer offline hoặc batch job dài hạn đã được cập nhật.
- Audit và retention không yêu cầu giữ khả năng xác minh hoặc giải mã.
- Quy trình khôi phục thảm họa đã được kiểm thử với version còn lại.
- Các phê duyệt và bằng chứng cần thiết đã được lưu.

Đối với khóa ký, public key và chứng chỉ có thể vẫn cần giữ để xác minh chữ ký được tạo trước đó, ngay cả khi private key đã ngừng ký. Đối với khóa mã hóa, hủy vật liệu khóa trước khi hết thời hạn lưu trữ có thể làm dữ liệu backup không thể giải mã. Phải phân biệt ngừng sử dụng, disable, revoke, schedule deletion và destruction.

## 14. Java: lưu key version trong envelope metadata

Ứng dụng nên lưu key version ID cùng ciphertext. Ví dụ sau mô tả một abstraction cho KMS/HSM; adapter có thể thực hiện AES-GCM trực tiếp bằng provider hoặc dùng envelope encryption với DEK.

~~~java
import java.security.SecureRandom;

public final class VersionedEncryption {
    private static final int FORMAT_VERSION = 1;
    private static final int NONCE_BYTES = 12;

    private static final SecureRandom RANDOM = new SecureRandom();

    private VersionedEncryption() {
    }

    public interface KeyVersionClient {
        String currentWriteVersion();

        byte[] encrypt(
                String keyVersionId,
                byte[] plaintext,
                byte[] nonce,
                byte[] aad) throws Exception;

        byte[] decrypt(
                String keyVersionId,
                byte[] ciphertextAndTag,
                byte[] nonce,
                byte[] aad) throws Exception;
    }

    public static final class EncryptedPayload {
        private final int formatVersion;
        private final String keyVersionId;
        private final byte[] nonce;
        private final byte[] ciphertext;

        public EncryptedPayload(
                int formatVersion,
                String keyVersionId,
                byte[] nonce,
                byte[] ciphertext) {
            this.formatVersion = formatVersion;
            this.keyVersionId = keyVersionId;
            this.nonce = nonce.clone();
            this.ciphertext = ciphertext.clone();
        }

        public int formatVersion() {
            return formatVersion;
        }

        public String keyVersionId() {
            return keyVersionId;
        }

        public byte[] nonce() {
            return nonce.clone();
        }

        public byte[] ciphertext() {
            return ciphertext.clone();
        }
    }

    public static EncryptedPayload encrypt(
            KeyVersionClient keys,
            byte[] plaintext,
            byte[] context) throws Exception {

        String versionId = keys.currentWriteVersion();

        byte[] nonce = new byte[NONCE_BYTES];
        RANDOM.nextBytes(nonce);

        byte[] aad = buildAad(FORMAT_VERSION, versionId, context);
        byte[] ciphertext = keys.encrypt(
            versionId,
            plaintext,
            nonce,
            aad
        );

        return new EncryptedPayload(
            FORMAT_VERSION,
            versionId,
            nonce,
            ciphertext
        );
    }

    public static byte[] decrypt(
            KeyVersionClient keys,
            EncryptedPayload payload,
            byte[] context) throws Exception {

        if (payload.formatVersion() != FORMAT_VERSION) {
            throw new IllegalArgumentException("Unsupported payload format");
        }

        byte[] aad = buildAad(
            payload.formatVersion(),
            payload.keyVersionId(),
            context
        );

        return keys.decrypt(
            payload.keyVersionId(),
            payload.ciphertext(),
            payload.nonce(),
            aad
        );
    }

    private static byte[] buildAad(
            int formatVersion,
            String keyVersionId,
            byte[] context) throws Exception {

        java.io.ByteArrayOutputStream buffer =
            new java.io.ByteArrayOutputStream();

        java.io.DataOutputStream output =
            new java.io.DataOutputStream(buffer);

        output.writeInt(formatVersion);
        output.writeUTF(keyVersionId);
        output.writeInt(context.length);
        output.write(context);
        output.flush();

        return buffer.toByteArray();
    }
}
~~~

Ví dụ có các điểm chính:

- Encrypt luôn hỏi client phiên bản write hiện tại.
- EncryptedPayload lưu key version ID, nonce, format version và ciphertext.
- Decrypt chọn key version theo metadata của payload thay vì alias hiện hành.
- Format version và key version ID được đưa vào AAD để metadata không thể bị thay đổi mà vẫn vượt qua xác thực AEAD.
- KeyVersionClient là ranh giới với KMS/HSM; ứng dụng không cần nhận vật liệu khóa thô.

Ví dụ giả định adapter thực hiện xác thực AEAD đúng cách và bảo đảm nonce không lặp với cùng khóa. Trong môi trường phân tán, nonce cần có chiến lược cấp phát phù hợp với lưu lượng và số instance. Nếu dùng envelope encryption, payload thường cần lưu thêm encrypted DEK và metadata của KEK version.

## 15. Java: migration theo batch có kiểm soát

Migration cần idempotent để có thể tiếp tục sau lỗi hoặc restart. Mỗi bản ghi nên có version hiện tại và trạng thái migration. Một thao tác cập nhật cần dùng optimistic locking hoặc compare-and-set để tránh ghi đè thay đổi mới hơn.

~~~java
import java.security.MessageDigest;

public final class KeyMigration {
    private KeyMigration() {
    }

    public interface PayloadStore {
        EncryptedRecord load(String recordId);

        boolean replaceIfVersionMatches(
                String recordId,
                String expectedKeyVersion,
                EncryptedRecord replacement);
    }

    public interface VersionedCrypto {
        byte[] decrypt(EncryptedRecord record) throws Exception;

        EncryptedRecord encryptWithCurrentVersion(
                String recordId,
                byte[] plaintext) throws Exception;
    }

    public static final class EncryptedRecord {
        private final String keyVersion;
        private final byte[] payload;

        public EncryptedRecord(String keyVersion, byte[] payload) {
            this.keyVersion = keyVersion;
            this.payload = payload.clone();
        }

        public String keyVersion() {
            return keyVersion;
        }

        public byte[] payload() {
            return payload.clone();
        }
    }

    public static boolean migrate(
            String recordId,
            String targetVersion,
            PayloadStore store,
            VersionedCrypto crypto) throws Exception {

        EncryptedRecord current = store.load(recordId);

        if (targetVersion.equals(current.keyVersion())) {
            return true;
        }

        byte[] plaintext = crypto.decrypt(current);

        try {
            EncryptedRecord replacement =
                crypto.encryptWithCurrentVersion(recordId, plaintext);

            if (!targetVersion.equals(replacement.keyVersion())) {
                throw new IllegalStateException(
                    "Write version changed during migration"
                );
            }

            byte[] verified = crypto.decrypt(replacement);
            try {
                if (!MessageDigest.isEqual(plaintext, verified)) {
                    throw new IllegalStateException(
                        "Migration verification failed"
                    );
                }
            } finally {
                java.util.Arrays.fill(verified, (byte) 0);
            }

            return store.replaceIfVersionMatches(
                recordId,
                current.keyVersion(),
                replacement
            );
        } finally {
            java.util.Arrays.fill(plaintext, (byte) 0);
        }
    }
}
~~~

Đây là hợp đồng migration minh họa. Trong triển khai thật, cần xử lý record không tồn tại, retry conflict, audit, giới hạn tốc độ và lỗi KMS/HSM. Nếu compare-and-set thất bại, bản ghi có thể đã được một request khác cập nhật; worker migration cần đọc lại và quyết định có cần tiếp tục hay không.

Không nên đánh dấu migration thành công chỉ vì lệnh encrypt trả về dữ liệu. Cần xác minh metadata version, tính toàn vẹn và khả năng đọc lại theo quy trình kiểm thử. Với dữ liệu quan trọng, có thể cần ghi bản mới vào vùng staging, xác minh rồi mới atomically thay con trỏ bản ghi.

## 16. Monitoring và tiêu chí hoàn tất rollout

Rollout phải có số liệu để xác nhận hệ thống thực sự chuyển đổi. Các chỉ số hữu ích:

- Số request encrypt theo key version.
- Số request decrypt theo key version.
- Tỷ lệ lỗi theo operation và version.
- Latency và throttling của KMS/HSM.
- Số lượng bản ghi còn phụ thuộc version cũ.
- Số lượng encrypted DEK đã re-wrap.
- Số consumer còn dùng alias hoặc cấu hình cũ.
- Số migration thành công, thất bại, retry và conflict.
- Số request bị từ chối do key state hoặc policy.
- Tình trạng backup và khôi phục với các version còn hiệu lực.

Tiêu chí promote có thể yêu cầu canary không có lỗi nghiêm trọng, latency trong ngưỡng, mọi writer đã hỗ trợ format mới và audit ghi nhận đúng version. Tiêu chí retire cần nghiêm ngặt hơn: không còn writer cũ, dữ liệu phụ thuộc đã xử lý, backup đã được đánh giá và khôi phục đã được kiểm thử.

Không dùng một metric duy nhất như “100% writer đã chuyển” để kết luận version cũ có thể bị hủy. Một archive ít truy cập hoặc backup nhiều tháng tuổi vẫn có thể cần khóa cũ.

## 17. Xử lý sự cố trong rollout

| Sự cố | Nguyên nhân có thể | Hành động |
|---|---|---|
| Decrypt thất bại sau promote | Reader chưa hỗ trợ version mới hoặc resolver sai | Giữ version mới và cũ, kiểm tra metadata và adapter |
| Một số instance vẫn encrypt bằng version cũ | Cache hoặc cấu hình chưa cập nhật | Dừng promote, cập nhật cache/invalidation và xác minh writer |
| KMS/HSM throttling | Canary hoặc migration tạo quá nhiều request | Giảm tốc độ, backoff, giới hạn concurrency |
| Migration ghi đè dữ liệu mới | Thiếu optimistic locking | Dùng compare-and-set và đọc lại khi conflict |
| Alias trỏ nhầm version | Cập nhật control plane sai hoặc race condition | Khôi phục pointer có kiểm soát, kiểm tra key ID thực tế |
| Backup không giải mã được | Backup phụ thuộc version cũ đã bị retire | Khôi phục quyền đọc version cũ theo quy trình được phê duyệt |
| Key version mới bị nghi lộ | Credential, policy hoặc key material bị xâm phạm | Dừng rollout, revoke quyền và kích hoạt incident response |
| Re-wrap DEK thất bại một phần | KMS lỗi hoặc dữ liệu envelope không đồng nhất | Lưu trạng thái từng record, retry idempotent và giữ KEK cũ |

Trong sự cố, phải bảo toàn khả năng giải mã dữ liệu hợp lệ và giữ bằng chứng audit. Không xóa key version cũ, encrypted DEK hoặc metadata chỉ để làm sạch trạng thái rollout.

## 18. Lỗi thường gặp và cách phòng tránh

| Lỗi | Hệ quả | Cách phòng tránh |
|---|---|---|
| Chuyển alias rồi coi rollout đã hoàn tất | Consumer cache hoặc ciphertext cũ không được xử lý | Theo dõi writer, reader và metadata version |
| Không lưu key version ID trong ciphertext | Không thể chọn đúng khóa để giải mã | Lưu version ID hoặc định danh bất biến trong envelope |
| Chỉ hỗ trợ version mới trên reader | Dữ liệu cũ không giải mã được | Duy trì multi-read trong thời gian chuyển tiếp |
| Giữ writer dùng version cũ quá lâu | Dữ liệu mới tiếp tục phụ thuộc khóa cũ | Theo dõi encrypt theo version và chặn writer cũ |
| Hủy key cũ ngay sau promote | Backup hoặc archive có thể mất khả năng giải mã | Kiểm kê dependency và retention trước destruction |
| Rollback writer nhưng bỏ reader version mới | Dữ liệu tạo trong canary không đọc được | Giữ reader cho mọi version đã phát sinh ciphertext |
| Re-encrypt không atomic | Dữ liệu có thể mất hoặc metadata không khớp | Transaction, staging hoặc compare-and-set |
| Migration không idempotent | Retry tạo trạng thái khó xác định | Lưu version và trạng thái từng record |
| Chuyển quá nhiều traffic cùng lúc | Quota, latency và lỗi tăng diện rộng | Canary và progressive rollout |
| Không kiểm thử restore | Backup không thể giải mã sau khi retire | Diễn tập khôi phục với version thực tế |

## 19. Nguyên tắc triển khai an toàn

- Tạo version mới và xác minh policy, key usage, provider, backup trước khi dùng production.
- Dùng key version ID bất biến trong metadata của ciphertext hoặc envelope.
- Áp dụng single-write, multi-read để chuyển đổi có kiểm soát.
- Triển khai reader tương thích trước khi chuyển writer.
- Dùng canary và progressive rollout, theo dõi metric theo từng version.
- Không thử mọi khóa để tìm khóa giải mã; chọn version từ metadata đã xác thực.
- Re-encrypt hoặc re-wrap theo batch có giới hạn, idempotency và atomic update.
- Khi rollback, có thể đổi write version nhưng vẫn phải đọc được dữ liệu tạo bằng version mới.
- Chỉ retire hoặc destroy version cũ sau khi kiểm kê ciphertext, backup, archive, replica và consumer offline.
- Giữ audit cho việc tạo, promote, rotate, migrate, disable và destroy version.
- Tách quyền tạo version, promote, thay policy và hủy khóa theo nguyên tắc separation of duties.
- Kiểm thử sự cố KMS/HSM, cache stale, migration conflict, rollback và disaster recovery trước rollout lớn.

Key version rollout là một thay đổi có ảnh hưởng xuyên suốt dữ liệu và ứng dụng. Một quy trình tốt xác định rõ version dùng để ghi, các version được phép đọc, metadata gắn với ciphertext, tiến độ migration và điều kiện retire. Khi triển khai theo giai đoạn, có khả năng rollback và giữ bằng chứng audit, tổ chức có thể thay khóa mà vẫn duy trì tính sẵn sàng và khả năng truy cập dữ liệu trong suốt vòng đời khóa.
