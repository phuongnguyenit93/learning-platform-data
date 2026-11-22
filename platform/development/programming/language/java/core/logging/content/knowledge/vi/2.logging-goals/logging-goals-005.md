# Hỗ trợ kiểm toán bằng logging trong Java

## 1. Logging hỗ trợ kiểm toán như thế nào?

**Kiểm toán (audit)** cần trả lời có căn cứ: ai hoặc hệ thống nào đã thực hiện thao tác gì, trên đối tượng nào, khi nào, kết quả ra sao và có thể lần theo giao dịch liên quan hay không. **Audit logging** là việc chủ động tạo các bản ghi sự kiện phục vụ việc truy vết, đối soát, điều tra sự cố và chứng minh quy trình kiểm soát đã được thực thi.

Trong Java, audit logging là một **mục tiêu sử dụng logging**, thường được thiết kế ở tầng nghiệp vụ và bảo mật. Nó bổ sung cho log kỹ thuật của ứng dụng, không đồng nghĩa với việc in mọi câu lệnh hoặc mọi thay đổi biến ra console.

Ví dụ, khi một quản trị viên thay đổi quyền truy cập, hệ thống cần biết:

- **Ai** thực hiện: mã định danh chủ thể đã được xác thực, hoặc mã service account.
- **Làm gì, với ai/cái gì**: `ROLE_UPDATE` trên tài khoản `user-81`.
- **Khi nào**: thời điểm có múi giờ rõ ràng, ưu tiên UTC.
- **Kết quả**: thành công, bị từ chối hoặc thất bại; nguyên nhân ở mức mã nghiệp vụ.
- **Liên hệ với yêu cầu nào**: mã tương quan để nối các bước xử lý.
- **Bằng chứng**: bản ghi được lưu, kiểm soát truy cập, giữ lại và kiểm tra tính toàn vẹn theo chính sách.

Lợi ích thực tế gồm truy xuất lịch sử thay đổi, phát hiện hành vi bất thường, phân định trách nhiệm, đối chiếu quy trình phê duyệt và hỗ trợ kiểm tra nội bộ hoặc bên ngoài. **Có audit log chưa tự động có nghĩa là đã tuân thủ một tiêu chuẩn pháp lý**: yêu cầu cụ thể còn phụ thuộc lĩnh vực, dữ liệu và chính sách kiểm toán.

## 2. Phân biệt audit log và log kỹ thuật

| Loại log | Câu hỏi chính | Ví dụ | Đặc điểm cần ưu tiên |
| --- | --- | --- | --- |
| Application/diagnostic log | Chương trình đang chạy ra sao, lỗi ở đâu? | `Connection timeout while calling service` | Hỗ trợ debug, quan sát vận hành; có thể rất chi tiết và được lấy mẫu. |
| Access/request log | Có yêu cầu nào đi vào hệ thống? | `POST /users/81/roles → 403` | Đường đi HTTP, mã trạng thái, độ trễ; không tự nói rõ quyết định nghiệp vụ. |
| **Audit log** | Ai đã yêu cầu/thực hiện hành động có ý nghĩa, tác động tới đâu, kết quả gì? | `ROLE_UPDATE / user-81 / DENIED / NO_PERMISSION` | Sự kiện có cấu trúc, gắn danh tính đáng tin cậy, lưu giữ và bảo vệ theo yêu cầu kiểm toán. |

Một HTTP 200 không nhất thiết chứng minh dữ liệu đã commit; một HTTP 500 cũng không đủ để xác định có hay không có thay đổi bền vững. Audit event phải phản ánh **sự thật nghiệp vụ tại thời điểm đã xác định**, không suy luận chỉ từ mã HTTP hoặc dòng debug.

**Sự kiện nên ghi:** đăng nhập và đăng nhập thất bại; cấp/thu hồi vai trò; thay đổi cấu hình bảo mật; phê duyệt/từ chối; tạo, sửa, xóa dữ liệu quan trọng; xuất dữ liệu nhạy cảm; sử dụng đặc quyền quản trị; thay đổi chính sách lưu giữ log; truy cập dữ liệu thuộc diện cần kiểm toán. Không cần biến mọi lượt đọc hoặc mọi vòng lặp thành audit event: chọn theo rủi ro và yêu cầu nghiệp vụ.

## 3. Thiết kế một bản ghi có thể kiểm toán

Một mẫu sự kiện dạng JSON Lines (mỗi dòng một đối tượng JSON độc lập):

```json
{
  "schemaVersion": 1,
  "eventId": "evt-001",
  "occurredAt": "2026-11-09T08:00:00Z",
  "actorId": "user-42",
  "action": "ROLE_UPDATE",
  "targetType": "USER",
  "targetId": "user-81",
  "outcome": "SUCCESS",
  "reasonCode": "APPROVED",
  "correlationId": "req-100"
}
```

| Trường | Ý nghĩa và lưu ý |
| --- | --- |
| `schemaVersion` | Phiên bản cấu trúc để đọc được dữ liệu cũ khi schema thay đổi. |
| `eventId` | Định danh duy nhất của sự kiện; dùng nhận biết bản ghi trùng khi giao nhận lại. |
| `occurredAt` | Thời điểm sự kiện theo ISO 8601/UTC; khi cần có thể bổ sung `recordedAt` (lúc hệ thống ghi nhận). |
| `actorId` | Chủ thể thực sự được xác thực (người dùng, service, tác vụ định kỳ). |
| `action` | Tên hành động ổn định, thống nhất quy ước như `ROLE_UPDATE`, `DATA_EXPORT`. |
| `targetType`, `targetId` | Loại và mã định danh đối tượng bị tác động. |
| `outcome` | `SUCCESS`, `DENIED` hoặc `FAILURE` với ý nghĩa được định nghĩa rõ. |
| `reasonCode` | Mã nguyên nhân đã chuẩn hóa, tránh ghi ngoại lệ hoặc thông tin nhạy cảm nguyên văn. |
| `correlationId` | Nối yêu cầu với trace/log nghiệp vụ qua nhiều lớp và dịch vụ. |

Trong hệ thống thực tế, có thể thêm `tenantId`, `sourceService`, mã chính sách/quyền hoặc tập trường thay đổi được **chọn lọc**. Nếu cần before/after, chỉ ghi các thuộc tính được phép kiểm toán (ví dụ mã vai trò trước/sau), tránh sao chép toàn bộ thực thể.

**Nguồn dữ liệu phải đáng tin:** `actorId` lấy từ ngữ cảnh xác thực do server xác lập, không lấy nguyên giá trị `userId` do client tự gửi để tự nhận là người khác. Tương tự, `outcome` phải được suy ra từ kết quả xử lý thực tế. Dùng `eventId` để chống trùng; `correlationId` để tìm các sự kiện liên quan. Hai trường có mục đích khác nhau.

## 4. Ví dụ Java 17+ chạy độc lập, không cần thư viện ngoài

Ví dụ sau ghi hai sự kiện mẫu ra tệp `audit-demo.jsonl` theo UTF-8. Toàn bộ dữ liệu ví dụ đã được cố định để dễ đọc và đối chiếu. Chương trình **chỉ mô phỏng kết quả nghiệp vụ**: nó không thực sự cập nhật quyền hoặc xác thực người dùng.

Tạo tệp `AuditLoggingDemo.java`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.Objects;

public class AuditLoggingDemo {

    record AuditEvent(
            String eventId,
            Instant occurredAt,
            String actorId,
            String action,
            String targetType,
            String targetId,
            String outcome,
            String reasonCode,
            String correlationId) {
    }

    public static void main(String[] args) throws IOException {
        Path file = Path.of("audit-demo.jsonl");

        AuditEvent success = new AuditEvent(
                "evt-001",
                Instant.parse("2026-11-09T08:00:00Z"),
                "user-42",
                "ROLE_UPDATE",
                "USER",
                "user-81",
                "SUCCESS",
                "APPROVED",
                "req-100");

        AuditEvent denied = new AuditEvent(
                "evt-002",
                Instant.parse("2026-11-09T08:01:00Z"),
                "user-99",
                "ROLE_UPDATE",
                "USER",
                "user-81",
                "DENIED",
                "NO_PERMISSION",
                "req-101");

        appendEvent(file, success);
        appendEvent(file, denied);
        System.out.println("Đã ghi 2 sự kiện audit vào " + file);
    }

    private static void appendEvent(Path file, AuditEvent event)
            throws IOException {
        Objects.requireNonNull(event);
        Files.writeString(
                file,
                toJson(event) + "\n",
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE,
                StandardOpenOption.APPEND);
    }

    private static String toJson(AuditEvent event) {
        return "{"
                + "\"eventId\":" + quote(event.eventId()) + ","
                + "\"occurredAt\":" + quote(event.occurredAt().toString()) + ","
                + "\"actorId\":" + quote(event.actorId()) + ","
                + "\"action\":" + quote(event.action()) + ","
                + "\"targetType\":" + quote(event.targetType()) + ","
                + "\"targetId\":" + quote(event.targetId()) + ","
                + "\"outcome\":" + quote(event.outcome()) + ","
                + "\"reasonCode\":" + quote(event.reasonCode()) + ","
                + "\"correlationId\":" + quote(event.correlationId())
                + "}";
    }

    private static String quote(String value) {
        Objects.requireNonNull(value);
        StringBuilder result = new StringBuilder();
        result.append('"');

        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '"' -> result.append("\\\"");
                case '\\' -> result.append("\\\\");
                case '\n' -> result.append("\\n");
                case '\r' -> result.append("\\r");
                case '\t' -> result.append("\\t");
                default -> {
                    if (c < 0x20) {
                        result.append('\\').append('u')
                                .append(String.format("%04x", (int) c));
                    } else {
                        result.append(c);
                    }
                }
            }
        }
        return result.append('"').toString();
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên, ở thư mục chứa tệp nguồn:

```bash
javac -encoding UTF-8 AuditLoggingDemo.java
java AuditLoggingDemo
```

Kết quả stdout **chính xác của mỗi lần chạy thành công**:

```text
Đã ghi 2 sự kiện audit vào audit-demo.jsonl
```

Sau lần chạy đầu tiên, tệp `audit-demo.jsonl` có đúng hai dòng sau (đã trình bày nguyên dòng, không thêm thụt lề):

```jsonl
{"eventId":"evt-001","occurredAt":"2026-11-09T08:00:00Z","actorId":"user-42","action":"ROLE_UPDATE","targetType":"USER","targetId":"user-81","outcome":"SUCCESS","reasonCode":"APPROVED","correlationId":"req-100"}
{"eventId":"evt-002","occurredAt":"2026-11-09T08:01:00Z","actorId":"user-99","action":"ROLE_UPDATE","targetType":"USER","targetId":"user-81","outcome":"DENIED","reasonCode":"NO_PERMISSION","correlationId":"req-101"}
```

Giải thích:

1. `AuditEvent` gom các trường định danh, thao tác, kết quả và liên kết yêu cầu, giúp mã gọi xây dựng cùng một định dạng.
2. `toJson` tạo sự kiện có cấu trúc; `quote` escape dấu ngoặc kép, dấu gạch chéo ngược và ký tự điều khiển để giá trị bất thường không phá định dạng hoặc chèn bản ghi giả qua newline.
3. `appendEvent` dùng `CREATE` và `APPEND` để thêm sự kiện vào tệp mà không xóa nội dung đã có. Nó để lỗi I/O nổi lên qua `IOException`, vì ứng dụng cần biết lúc nào việc ghi thất bại.
4. Timestamps, định danh và kết quả ở đây là **dữ liệu minh họa**, không lấy từ người dùng hoặc đồng hồ thật. Trong ứng dụng, tạo `eventId` riêng cho mỗi sự kiện và lấy thời gian từ `Instant.now()` hoặc một `Clock` được tiêm vào để dễ test.
5. **Chạy lại sẽ thêm hai dòng nữa với cùng ID**, vì demo cố định ID. Hệ thống thật phải có cơ chế đảm bảo ID duy nhất và loại trùng trong kho lưu trữ.

**Giới hạn quan trọng:** `Files.writeString(..., APPEND)` là ví dụ học tập, **không phải kho audit đạt yêu cầu production**. Nó không đảm bảo tính nguyên tử giữa các process ghi đồng thời, không bảo đảm fsync/durability khi mất điện, chưa chống sửa/xóa tệp và chưa có phân quyền, lưu giữ hoặc xác minh tính toàn vẹn. Java SE cũng không cung cấp sẵn bộ mã hóa JSON tổng quát ở đây; hàm `quote` chỉ phục vụ các trường chuỗi của demo. Khi triển khai thật, dùng bộ serializer chuẩn của dự án, cùng nơi nhận audit chuyên dụng.

## 5. Ghi đúng thời điểm để kết quả audit không sai lệch

Sự kiện `SUCCESS` nên có nghĩa **nghiệp vụ đã hoàn tất theo ranh giới được định nghĩa** (ví dụ giao dịch database đã commit). Nếu ghi thành công trước khi commit rồi transaction rollback, nhật ký sẽ khẳng định sai rằng thay đổi đã xảy ra. Ngược lại, nếu commit xong rồi tiến trình chết trước khi gửi audit, thay đổi có thể không có dấu vết.

Một luồng phù hợp cho thao tác cập nhật quan trọng:

```text
Yêu cầu -> Xác thực -> Phân quyền
                     |-- Bị từ chối -> Ghi audit DENIED
                     |
                     +-- Được phép -> Transaction:
                                      +-- Cập nhật dữ liệu
                                      +-- Ghi audit_outbox cùng transaction
                                     Commit
                                       |
                              Worker/dispatcher gửi event
                                       |
                              Kho audit xác nhận lưu
```

- **Transactional outbox:** ghi dữ liệu nghiệp vụ và bản ghi outbox **trong cùng giao dịch của cùng cơ sở dữ liệu**, sau đó chuyển event đến kho audit. Cách này giảm khe hở giữa commit và phát sự kiện; cần giám sát outbox chưa gửi, retry và khả năng phục hồi.
- **Ít nhất một lần (at-least-once):** khi dispatcher gửi lại do mất ACK, kho nhận phải loại trùng theo `eventId`. Không giả định một lần gửi chắc chắn có đúng một bản ghi.
- **DENIED/FAILURE:** hành động bị từ chối hoặc lỗi trước commit có thể không có transaction thành công. Nếu các nỗ lực này phải được kiểm toán, ghi qua đường audit thích hợp, độc lập với transaction nghiệp vụ bị rollback.
- **Audit bắt buộc:** quyết định chính sách khi không thể ghi audit. Với thao tác yêu cầu bằng chứng bắt buộc, có thể phải từ chối thao tác hoặc giữ ở trạng thái chờ có thể khôi phục; tuyệt đối không ngầm báo thành công khi bản ghi audit quan trọng đã thất lạc. Cần thiết kế hành vi nhất quán cho cả timeout, mất mạng, restart và ghi lặp.
- **Nhiều dịch vụ:** truyền `correlationId` qua các bước, đồng bộ thời gian và phân biệt `occurredAt` với `receivedAt`; đừng chỉ suy ra thứ tự tuyệt đối từ timestamp của các máy khác nhau.

Đừng đặt thông điệp audit duy nhất trong `catch` hoặc log debug ở cuối controller: như vậy dễ bỏ qua các đường xử lý thành công, từ chối hoặc rollback. Hãy xác định điểm phát sự kiện theo hành động nghiệp vụ và kiểm tra đầy đủ các nhánh kết quả.

## 6. Giữ bằng chứng đáng tin cậy và an toàn

**Tính toàn vẹn:** kho audit cần cơ chế phát hiện sửa, xóa, chèn hoặc thiếu bản ghi; có thể sử dụng lưu trữ append-only/WORM, phân quyền độc lập, chữ ký số hoặc chuỗi hash có bảo vệ khóa. Chỉ thêm trường checksum hoặc mã hóa tệp **không đủ chứng minh chống sửa đổi** nếu người có quyền chỉnh sửa cũng có thể tạo lại checksum hoặc thay khóa. Cần quy trình kiểm tra định kỳ và lưu kết quả kiểm tra.

**Tính sẵn có:** lưu trữ tập trung, sao lưu/nhân bản, giám sát độ trễ và độ đầy của hàng đợi, cảnh báo mất sự kiện hoặc lỗi gửi; thiết kế để còn dữ liệu khi một instance ứng dụng hỏng. Quy trình khôi phục phải được diễn tập.

**Quyền truy cập:** phân tách người ghi, người đọc và người quản trị chính sách lưu giữ; người bị kiểm toán không nên tự có quyền sửa/xóa dấu vết về chính mình. Kiểm toán cả việc truy vấn hoặc xuất log nhạy cảm khi chính sách yêu cầu.

**Bảo mật và quyền riêng tư:** ưu tiên ID ổn định hơn dữ liệu định danh thô; hạn chế IP/thiết bị/vị trí khi không thật sự cần. Không ghi mật khẩu, OTP, access token, refresh token, private key, session secret, toàn bộ body chứa thông tin nhạy cảm hoặc stack trace chứa bí mật. Áp dụng redaction/allowlist trước khi gửi sự kiện, mã hóa đường truyền và dữ liệu lưu trữ, quy định người được đọc.

**Lưu giữ và xóa:** xác định mục đích, thời hạn giữ, yêu cầu khóa pháp lý khi áp dụng, cơ chế hủy đúng hạn, tính truy xuất được và khả năng cung cấp chuỗi bằng chứng. Không tự mặc định một số ngày áp dụng cho mọi sản phẩm hoặc mọi quy định.

**Truy vấn phục vụ kiểm toán:** có khả năng lọc theo `actorId`, `action`, `targetId`, `eventId`, khoảng UTC và `correlationId`; giữ schema/phiên bản để giải mã bản ghi cũ; ghi lại ai đã xuất bộ kết quả và phạm vi xuất. Một bản ghi nhiều trường nhưng không tìm kiếm hay giải thích được vẫn khó phục vụ kiểm toán.

## 7. Tình huống và cách đối chiếu

**Tình huống: thay đổi vai trò quản trị**

1. Nhân viên kiểm toán tìm `action=ROLE_UPDATE` và `targetId=user-81` trong khoảng thời gian cần điều tra.
2. Hệ thống trả về `evt-001`: `actorId=user-42`, `SUCCESS`, `08:00:00Z`, `correlationId=req-100`; cùng những sự kiện phê duyệt liên quan nếu quy trình có phê duyệt.
3. Truy vấn `req-100` trong log vận hành để hiểu luồng kỹ thuật. Nhật ký kỹ thuật là tài liệu bổ trợ; trạng thái thay đổi phải được kiểm tra với nghiệp vụ/transaction.
4. Có bản ghi `evt-002`: `DENIED / NO_PERMISSION` lúc `08:01:00Z`; nó chứng minh có nỗ lực bị từ chối, **không chứng minh** vai trò đã bị thay đổi bởi nỗ lực đó.
5. Đối chiếu mã định danh, chính sách quyền tại thời điểm thực hiện, bản ghi before/after được cho phép và kiểm tra tính toàn vẹn để hình thành kết luận có cơ sở.

Đây là lý do chỉ log `"update role completed"` hoặc `"403 Forbidden"` không đủ cho yêu cầu kiểm toán: thiếu tác nhân, mục tiêu, thời điểm chuẩn hóa, kết quả nghiệp vụ và đường dẫn đến bằng chứng khác.

## 8. Kiểm thử và lỗi thường gặp

| Trường hợp kiểm thử | Điều cần xác nhận |
| --- | --- |
| Thay đổi hợp lệ commit thành công | Có đúng sự kiện `SUCCESS` gắn đúng actor, target, thời gian và giao dịch. |
| Bị từ chối quyền | Có `DENIED` (nếu thuộc phạm vi kiểm toán); **không** có thay đổi dữ liệu bị từ chối. |
| Transaction rollback | Không sinh bản ghi khẳng định commit thành công; nỗ lực thất bại được ghi theo chính sách. |
| Mất kết nối tới kho audit | Retry/phục hồi hoặc chặn nghiệp vụ đúng hợp đồng; có cảnh báo và không mất event im lặng. |
| Gửi event lặp | Chỉ có một sự kiện logic theo `eventId` ở kho nhận; vẫn truy vết được retry. |
| Input chứa newline, dấu nháy | JSON vẫn hợp lệ; không xuất hiện dòng audit giả mạo do chèn ký tự điều khiển. |
| Thay đổi schema và thời gian | Bản ghi cũ còn đọc được; UTC và ý nghĩa timestamp nhất quán. |
| Truy cập trái phép hoặc sửa log | Bị từ chối, để lại dấu vết phù hợp hoặc bị phát hiện khi kiểm tra toàn vẹn. |

Các lỗi thiết kế phổ biến:

- Ghi một chuỗi log tự do không có schema; đổi câu chữ là hỏng truy vấn lịch sử.
- Tin `actorId` lấy từ request thay vì principal xác thực.
- Ghi `SUCCESS` trước commit hoặc quên audit các lần `DENIED`.
- Dùng `System.out.println`, file cục bộ hay log debug làm nguồn bằng chứng duy nhất.
- Ghi dữ liệu nhạy cảm để “đủ chi tiết”, dẫn tới lộ thông tin và mở rộng rủi ro.
- Không xử lý trùng, mất sự kiện, clock skew, phân quyền đọc hoặc chính sách lưu giữ.
- Đồng nhất “đã mã hóa” với “không thể bị sửa” và đồng nhất “có log” với “đã tuân thủ”.

## 9. Checklist áp dụng trong dự án Java

1. **Liệt kê hành động cần kiểm toán:** xác định sự kiện nào tạo giá trị bằng chứng, bao gồm thao tác quản trị, thay đổi quan trọng và nỗ lực bị từ chối.
2. **Định nghĩa schema/version:** tên action, actor/target, outcome, lý do, event ID, tương quan yêu cầu, timestamp UTC và các thuộc tính được phép ghi.
3. **Gắn vào ranh giới nghiệp vụ:** dùng kết quả xác thực server-side, quyết định rõ thời điểm emit và trạng thái sau commit; có outbox nếu cần phát sự kiện bền vững cùng transaction.
4. **Chọn nơi nhận phù hợp:** lưu tập trung, kiểm soát quyền ghi/đọc/xóa, giữ theo chính sách, giám sát lỗi và kiểm tra tính toàn vẹn.
5. **Kiểm thử khả năng chứng minh:** từ một ID đối tượng hoặc một `correlationId`, có thể tái dựng chuỗi quyết định và phân biệt thay đổi thành công với nỗ lực thất bại; không làm lộ bí mật.

**Điểm cốt lõi:** logging hỗ trợ kiểm toán khi bản ghi phản ánh đúng hành vi nghiệp vụ, có cấu trúc, có thể tìm lại, có đường liên kết đến các bằng chứng khác và được bảo vệ khỏi mất mát hoặc thay đổi trái phép.