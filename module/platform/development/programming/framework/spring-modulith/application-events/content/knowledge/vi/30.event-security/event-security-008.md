# Mã hóa khi lưu

Application events có thể chứa thông tin khách hàng, địa chỉ giao hàng, dữ liệu thanh toán hoặc chi tiết nghiệp vụ. Dù event chỉ tồn tại trong thời gian ngắn ở bộ nhớ, hệ thống thường phải lưu nó để theo dõi publication, retry, chuyển tiếp sang broker, xử lý dead-letter hoặc phục hồi sau sự cố. Mã hóa khi lưu (encryption at rest) bảo vệ payload và dữ liệu liên quan khi chúng nằm trên database, ổ đĩa, broker, bản sao lưu hoặc kho lưu trữ.

Trong Spring Modulith, Event Publication Registry có thể lưu publication để theo dõi listener và phục hồi event chưa xử lý. Vì vậy, bảo mật event cần tính đến cả dữ liệu publication được lưu bền vững và các bản sao khác của payload. Mã hóa ổ đĩa là một lớp bảo vệ quan trọng; với dữ liệu nhạy cảm, có thể cần thêm mã hóa ở tầng ứng dụng và quản lý khóa tập trung.

## 1. Encryption at rest bảo vệ điều gì?

Encryption at rest là mã hóa dữ liệu khi dữ liệu được lưu trên một phương tiện lưu trữ. Khi một hệ thống được cấp quyền đọc hợp lệ và giải mã, dữ liệu mới được sử dụng. Mục tiêu là giảm khả năng đọc nội dung khi ổ đĩa, snapshot, bản backup hoặc thiết bị lưu trữ bị truy cập trái phép.

Phân biệt ba trạng thái:

| Trạng thái | Ví dụ | Biện pháp thường dùng |
| --- | --- | --- |
| Data in transit | Event đi qua HTTP, Kafka hoặc kết nối database | TLS và xác thực hai đầu phù hợp |
| Data at rest | Event payload trong publication registry, outbox, broker log, DLT hoặc backup | Mã hóa storage, database hoặc mã hóa payload ở tầng ứng dụng |
| Data in use | Event được deserialize và xử lý trong bộ nhớ của ứng dụng | Giới hạn quyền truy cập, bảo vệ runtime, tránh log payload và kiểm soát dữ liệu trong heap/dump |

Mã hóa khi lưu không thay thế TLS. TLS bảo vệ dữ liệu trong quá trình truyền; mã hóa at rest bảo vệ dữ liệu đã được ghi xuống storage. Một luồng event đáng tin cậy thường cần cả hai.

## 2. Xác định mọi nơi payload có thể được lưu

Trước khi chọn giải pháp, hãy lập bản đồ vòng đời của event. Một payload có thể xuất hiện ở nhiều nơi:

- **Event Publication Registry:** thông tin publication và event đã serialize để phục hồi listener chưa hoàn tất.
- **Outbox hoặc integration task:** event/task được lưu bền vững trước khi worker gửi tới hệ thống khác.
- **Message broker:** Kafka log, RabbitMQ durable queue hoặc storage tương đương.
- **Retry topic và dead-letter queue/topic:** bản sao message chờ thử lại hoặc chờ điều tra.
- **Database replica, snapshot và backup:** bản sao dữ liệu có thể tồn tại lâu hơn bản ghi gốc.
- **Log, trace và công cụ quan sát:** payload hoặc một phần payload có thể vô tình bị ghi vào log, error report hay tracing attribute.

Không chỉ mã hóa bảng chính rồi xem như đã bảo vệ toàn bộ event. Hãy xác minh từng bản sao, bao gồm bản backup, topic retry/DLT và dữ liệu xuất ra để điều tra.

## 3. Chọn lớp mã hóa phù hợp

Có hai lớp thường được kết hợp:

| Lớp | Cách hoạt động | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| Storage/database encryption | Database, volume hoặc broker mã hóa block/page/file khi ghi xuống storage | Dễ triển khai ở hạ tầng, bảo vệ khi thiết bị hoặc snapshot bị lấy cắp | Dữ liệu thường được giải mã tự động khi database hoặc broker đang hoạt động; người có quyền đọc hợp lệ vẫn có thể đọc payload |
| Application-level encryption | Ứng dụng mã hóa payload hoặc field nhạy cảm trước khi lưu; chỉ thành phần có khóa mới giải mã được | Bảo vệ dữ liệu ngay cả khi bản ghi bị đọc qua một số đường truy cập storage | Cần quản lý khóa, serialization, tìm kiếm, migration và phục hồi phức tạp hơn |

Database TDE, mã hóa volume và mã hóa storage của broker là lớp nền nên có cho dữ liệu phù hợp. Nếu threat model yêu cầu DBA, operator hoặc người có quyền đọc storage cũng không được thấy nội dung event, cần cân nhắc mã hóa ở tầng ứng dụng trước khi dữ liệu được ghi.

Không nên tự triển khai thuật toán mật mã. Dùng thư viện chuẩn và dịch vụ quản lý khóa đã được vận hành, đồng thời xác định rõ ai được quyền giải mã.

## 4. Mã hóa payload trong vòng đời Spring Modulith

Trong ứng dụng Spring Modulith, event object thường được publish trong bộ nhớ. Các listener nội bộ cần nhận được object đã deserialize bình thường để xử lý nghiệp vụ. Mã hóa at rest nên được áp dụng tại ranh giới lưu trữ hoặc truyền message, thay vì biến event nội bộ thành một object ciphertext mà mọi listener phải tự giải mã.

Ví dụ các ranh giới:

~~~mermaid
flowchart TD
    A[Publish application event] --> B[Event Publication Registry]
    B --> C[Serialize event]
    C --> D[Encrypt payload]
    D --> E[(Database / storage)]
    E --> F[Read encrypted publication]
    F --> G[Decrypt payload]
    G --> H[Deserialize event]
    H --> I[Resume listener]
    A --> J[Externalization adapter]
    J --> K[Encrypt integration payload]
    K --> L[(Broker, retry topic, DLT)]
~~~

Event Publication Registry theo dõi publication tới listener. Khi registry cần lưu event để phục hồi sau restart, serializer và persistence path phải được xem xét cùng cơ chế mã hóa. Cách tích hợp cụ thể phụ thuộc phiên bản Spring Modulith và persistence adapter đang dùng; không giả định framework tự động mã hóa payload hoặc có một annotation chung để bật encryption.

Với externalization, mã hóa payload message tại adapter hoặc lớp producer phù hợp với hợp đồng tích hợp. Consumer được cấp quyền mới giải mã trước khi deserialize và xử lý. Nếu broker có mã hóa storage tích hợp, vẫn cần TLS khi producer/consumer kết nối broker.

## 5. Envelope encryption và quản lý khóa

Trong môi trường production, nên dùng envelope encryption thay vì lưu một khóa AES tĩnh trong application configuration. Envelope encryption có hai lớp khóa:

1. **Data Encryption Key (DEK):** khóa dữ liệu dùng để mã hóa payload event bằng thuật toán đối xứng như AES-GCM.
2. **Key Encryption Key (KEK):** khóa gốc được giữ trong KMS hoặc HSM, dùng để mã hóa (wrap) DEK.

Ứng dụng yêu cầu KMS tạo hoặc cấp DEK. Payload được mã hóa bằng DEK; bản DEK dạng rõ chỉ tồn tại trong bộ nhớ trong thời gian cần thiết. Ứng dụng lưu ciphertext cùng DEK đã được wrap, key ID và metadata cần thiết. Khi đọc, ứng dụng yêu cầu KMS unwrap DEK rồi giải mã payload.

~~~mermaid
flowchart LR
    A[Application] -->|Request DEK| B[KMS / HSM]
    B -->|Plain DEK + Wrapped DEK| A
    A -->|AES-GCM with DEK| C[Ciphertext]
    A -->|Store| D[(Encrypted payload + wrapped DEK + key ID)]
    D -->|Read| A
    A -->|Unwrap DEK| B
    B -->|Plain DEK| A
    A -->|Decrypt| E[Event payload]
~~~

Không ghi plaintext DEK, KEK, access token hoặc credential vào database, log, source code hay file cấu hình được commit. Quyền gọi KMS cần được cấp theo workload identity hoặc cơ chế xác thực của nền tảng, với quyền tối thiểu cần thiết.

Metadata của bản ghi mã hóa nên có tối thiểu:

| Trường | Mục đích |
| --- | --- |
| `cipherVersion` | Phiên bản định dạng envelope để hỗ trợ thay đổi trong tương lai |
| `algorithm` | Thuật toán và mode được dùng, ví dụ AES-256-GCM |
| `keyId` | Định danh khóa KEK hoặc key version trong KMS |
| `wrappedDek` | DEK đã được mã hóa bởi KEK |
| `nonce` | Nonce/IV cần thiết để giải mã AEAD |
| `ciphertext` | Nội dung đã mã hóa, thường kèm authentication tag |

Chỉ lưu metadata không bí mật cần cho quá trình giải mã. Không lưu khóa dạng rõ cùng ciphertext.

## 6. Dùng authenticated encryption

Khi mã hóa payload, cần bảo đảm cả tính bí mật và tính toàn vẹn. AES-GCM là một lựa chọn authenticated encryption with associated data (AEAD) phổ biến. Nó tạo ciphertext và authentication tag; nếu ciphertext hoặc metadata xác thực bị sửa, thao tác giải mã sẽ thất bại.

Ví dụ minh họa Java dùng khóa AES được cấp từ một key provider an toàn:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

record EncryptedPayload(
        String keyId,
        String nonce,
        String ciphertext) {
}

final class EventPayloadCrypto {

    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    private final SecureRandom random = new SecureRandom();

    EncryptedPayload encrypt(
            byte[] plaintext,
            SecretKey dataKey,
            String keyId,
            byte[] associatedData) throws Exception {

        byte[] nonce = new byte[NONCE_BYTES];
        random.nextBytes(nonce);

        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(
                Cipher.ENCRYPT_MODE,
                dataKey,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(associatedData);

        byte[] ciphertext = cipher.doFinal(plaintext);

        return new EncryptedPayload(
                keyId,
                Base64.getEncoder().encodeToString(nonce),
                Base64.getEncoder().encodeToString(ciphertext));
    }

    byte[] decrypt(
            EncryptedPayload encrypted,
            SecretKey dataKey,
            byte[] associatedData) throws Exception {

        byte[] nonce = Base64.getDecoder().decode(encrypted.nonce());
        byte[] ciphertext = Base64.getDecoder().decode(encrypted.ciphertext());

        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(
                Cipher.DECRYPT_MODE,
                dataKey,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(associatedData);

        return cipher.doFinal(ciphertext);
    }
}
~~~

Ví dụ chỉ minh họa thao tác mã hóa/giải mã payload; `SecretKey` phải được cấp an toàn, `keyId` phải ánh xạ tới key version phù hợp và DEK cần được wrap bởi KMS trước khi lưu. `associatedData` (AAD) có thể chứa event type, schema version, tenant ID hoặc publication ID theo một định dạng canonical. AAD không được mã hóa nhưng được xác thực, nên thay đổi metadata sẽ làm giải mã thất bại.

Với AES-GCM, không bao giờ tái sử dụng cùng nonce với cùng một khóa. Nonce 96-bit ngẫu nhiên là lựa chọn phổ biến; với hệ thống có lưu lượng rất lớn, hãy chọn chiến lược nonce và vòng đời DEK bảo đảm không trùng. Dùng DEK riêng cho từng event hoặc từng bản ghi giúp giới hạn miền nonce. Không tự cắt bỏ authentication tag hoặc bỏ qua lỗi xác thực khi decrypt.

## 7. Mã hóa toàn payload hay chỉ field nhạy cảm?

Chọn phạm vi dựa trên nhu cầu truy vấn và quyền truy cập:

- **Mã hóa toàn payload:** phù hợp khi consumer cần toàn bộ nội dung và không cần database truy vấn theo từng field. Cách này giảm lộ thông tin qua query/log nhưng làm cho tìm kiếm theo nội dung khó hơn.
- **Mã hóa field nhạy cảm:** phù hợp khi vẫn cần truy vấn metadata không nhạy cảm như event type, event ID, trạng thái publication hoặc thời điểm tạo. Các field như địa chỉ, số tài khoản hoặc thông tin cá nhân được mã hóa riêng.
- **Tokenization:** thay dữ liệu nhạy cảm bằng token tham chiếu tới kho dữ liệu được bảo vệ. Hữu ích khi nhiều event cần tham chiếu cùng một dữ liệu nhưng không cần mang giá trị gốc.

Không đưa dữ liệu nhạy cảm vào event nếu listener không cần. Data minimization giảm lượng dữ liệu cần mã hóa và giảm rủi ro khi payload bị lộ. Những metadata còn để dạng rõ cũng cần được xem xét vì event type, tenant ID, thời điểm và kích thước message có thể tiết lộ thông tin nghiệp vụ.

## 8. Luân chuyển khóa và vòng đời dữ liệu

Khóa cần được luân chuyển theo chính sách bảo mật và khi có dấu hiệu bị lộ. Thiết kế lưu trữ phải cho phép đọc dữ liệu đã mã hóa bằng key version cũ trong thời gian migration.

Quy trình luân chuyển thường gồm:

1. Tạo key version mới trong KMS và cho phép workload dùng khóa mới để mã hóa dữ liệu mới.
2. Giữ quyền decrypt key version cũ trong thời gian dữ liệu cũ còn tồn tại.
3. Re-wrap DEK bằng KEK mới nếu chỉ cần đổi khóa bảo vệ DEK; không cần giải mã và mã hóa lại toàn bộ payload trong trường hợp này.
4. Nếu cần đổi DEK hoặc thuật toán, đọc payload bằng khóa cũ, xác thực, giải mã rồi mã hóa lại bằng khóa mới.
5. Kiểm tra tỷ lệ bản ghi còn dùng key version cũ và xác minh có thể đọc lại trước khi thu hồi khóa cũ.
6. Thu hồi key version cũ chỉ sau khi chắc chắn không còn publication, message, backup hoặc archive cần giải mã bằng khóa đó.

Retention và key lifecycle phải được thiết kế cùng nhau. Nếu xóa khóa quá sớm, event chưa xử lý hoặc backup vẫn còn nhưng không thể decrypt, làm mất khả năng phục hồi. Ngược lại, giữ khóa vô thời hạn làm giảm hiệu quả của chính sách xóa dữ liệu.

Với yêu cầu xóa dữ liệu theo cá nhân hoặc tenant, có thể cân nhắc crypto-shredding: xóa khóa dữ liệu riêng sau khi xác nhận mọi bản sao cần giữ đã được xử lý theo chính sách. Phải hiểu rõ hậu quả: dữ liệu còn lại trở nên không thể giải mã, kể cả khi sau này cần điều tra hoặc phục hồi.

## 9. Retry, replay và dead-letter khi payload đã mã hóa

Listener có thể cần đọc lại publication sau restart; consumer có thể retry message hoặc phát lại DLT. Mọi đường phục hồi đều phải còn quyền decrypt và có key version tương thích.

- Không thay đổi key ID hoặc AAD theo cách khiến ciphertext cũ không thể giải mã.
- Giữ key version cũ trong thời gian tối đa mà publication, retry topic, DLT và backup có thể tồn tại.
- Xác minh decrypt trước khi deserialize và xử lý event; lỗi authentication tag phải được xem là lỗi bảo mật/toàn vẹn, không được bỏ qua.
- Khi chuyển message sang retry topic hoặc DLT, bảo đảm metadata mã hóa và wrapped DEK được giữ nguyên hoặc được mã hóa lại đúng quy trình.
- Nếu KMS tạm thời không sẵn sàng, phân loại đó là lỗi hạ tầng có thể retry có giới hạn; không đánh dấu publication hoàn tất khi chưa thể phục hồi payload.

Event Publication Registry theo dõi trạng thái giao event tới listener, không phải kho khóa hay event store dài hạn. Cần giữ khả năng giải mã cho toàn bộ thời gian registry có thể phục hồi publication chưa hoàn tất. Với lịch sử dài hạn, archive phải lưu kèm metadata mã hóa và quy tắc key retention riêng.

## 10. Bảo vệ backup, log và môi trường vận hành

Mã hóa database chính không tự động bảo vệ mọi bản sao. Hãy xác nhận:

- Backup, snapshot và replica được mã hóa bằng khóa được quản lý và có quyền truy cập riêng.
- Broker log, retry topic và DLT có encryption at rest, ACL và retention phù hợp.
- Log chỉ ghi event ID, event type, correlation ID và trạng thái xử lý; không ghi plaintext payload, DEK hoặc credential.
- APM, tracing, error tracking và dead-letter tooling không tự thu thập body hoặc header nhạy cảm.
- Quyền giải mã được giới hạn theo workload/consumer cần xử lý loại event tương ứng.
- Quy trình khôi phục backup đã được kiểm tra cùng khả năng truy cập KMS và key version cũ.

Không gửi payload đã giải mã vào dashboard vận hành chỉ để tiện tra cứu. Nếu operator cần điều tra, cung cấp công cụ có audit, quyền hạn, mục đích truy cập và che dữ liệu theo vai trò.

## 11. Kiểm thử mã hóa khi lưu

Kiểm thử nên xác minh cả tính bảo mật lẫn khả năng phục hồi:

1. Payload sau khi ghi storage không xuất hiện dưới dạng plaintext ở nơi được yêu cầu mã hóa.
2. Consumer có quyền đọc và key phù hợp giải mã được payload rồi deserialize thành event đúng.
3. Ciphertext, nonce, wrapped DEK hoặc AAD bị thay đổi sẽ khiến authentication/decryption thất bại.
4. Key ID không tồn tại hoặc KMS không truy cập được được xử lý như lỗi rõ ràng, không âm thầm bỏ qua event.
5. Event cũ vẫn giải mã được trong thời gian key rotation và retry/replay.
6. Backup restore thành công khi workload được cấp quyền KMS và key version cần thiết.
7. Log, trace và DLT metadata không làm lộ plaintext hoặc secret.
8. Payload lớn vẫn nằm trong giới hạn database/broker sau khi thêm nonce, tag và wrapped DEK.

Test không nên chỉ gọi một helper AES độc lập. Cần kiểm tra đúng serializer/persistence adapter của registry và đúng producer/consumer converter được ứng dụng sử dụng, để xác nhận mã hóa thực sự nằm trên đường ghi và giải mã nằm trên đường đọc.

## 12. Những sai lầm cần tránh

- Nhầm TLS khi truyền với encryption at rest.
- Cho rằng mã hóa volume bảo vệ khỏi mọi người có quyền đọc database đang chạy.
- Chỉ mã hóa bảng publication nhưng bỏ quên outbox, broker, retry topic, DLT hoặc backup.
- Tự tạo thuật toán hoặc dùng AES mode không có authentication.
- Dùng lại nonce với cùng AES-GCM key.
- Lưu plaintext key hoặc DEK cạnh ciphertext.
- Thu hồi key cũ khi event pending hoặc backup vẫn cần giải mã.
- Ghi plaintext payload vào log, trace hoặc công cụ dead-letter.
- Coi Event Publication Registry là nơi lưu lịch sử nghiệp vụ vô thời hạn.
- Đánh dấu publication hoàn tất khi decrypt thất bại hoặc chưa bàn giao được công việc.

## Kết luận

Mã hóa khi lưu bảo vệ event payload trong publication registry, outbox, broker, retry/DLT và backup. Với Spring Modulith, hãy xác định đúng ranh giới persistence và externalization để mã hóa trước khi ghi, giải mã trước khi deserialize, đồng thời giữ nguyên khả năng phục hồi publication. Kết hợp storage encryption với envelope encryption, AES-GCM, KMS/HSM, key rotation, retention, data minimization và kiểm thử restore sẽ bảo vệ dữ liệu mà vẫn duy trì khả năng retry và replay khi cần.
