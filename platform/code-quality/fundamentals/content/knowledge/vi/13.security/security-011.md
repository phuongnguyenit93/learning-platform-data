# Kết hợp rà soát thiết kế, phân tích và kiểm thử theo mô hình đe dọa

Một chức năng tải báo cáo có thể vượt qua tất cả unit test về đường dẫn thành công, dùng truy vấn SQL an toàn và không chứa mật khẩu trong mã nguồn nhưng vẫn làm lộ báo cáo của khách hàng khác. Chỉ cần người dùng thay một mã báo cáo trong yêu cầu, hệ thống có thể trả về tài liệu không thuộc quyền của họ nếu **kiểm tra quyền trên từng tài nguyên** bị bỏ sót.

Vấn đề không được giải quyết bằng cách “chạy thêm thật nhiều test” một cách ngẫu nhiên. Nhóm phải biết **tài sản nào cần bảo vệ, ai có thể tác động lên đầu vào, ranh giới tin cậy nằm ở đâu và điều gì có thể xảy ra khi một giả định bị phá vỡ**. Từ đó mới chọn đúng điểm rà soát thiết kế, loại phân tích và bài kiểm thử.

Trong module **CODE_QUALITY_FUNDAMENTALS**, mục tiêu là hiểu những thuộc tính quyết định mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Ở chương **Bảo mật**, bài này tập trung vào cách phối hợp **mô hình đe dọa (threat modeling)**, **rà soát thiết kế (design review)**, **phân tích mã và phụ thuộc (analysis)** cùng **kiểm thử bảo mật (security testing)** để tạo bằng chứng có ý nghĩa về hành vi bảo vệ hệ thống.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định tài sản, chủ thể, luồng dữ liệu, điểm vào, giả định và **ranh giới tin cậy** của một chức năng.
- Viết kịch bản đe dọa cụ thể dựa trên khả năng của tác nhân, thay vì chỉ ghi chung chung “có rủi ro bảo mật”.
- Sử dụng STRIDE như **bộ gợi ý câu hỏi** và ưu tiên xử lý theo tác động, khả năng xảy ra cùng điều kiện hệ thống thực tế.
- Phân biệt những lỗi có thể được phát hiện qua **design review**, **SAST**, **SCA**, **kiểm thử động**, **kiểm thử quyền truy cập** và quan sát khi vận hành.
- Liên kết **đe dọa → biện pháp kiểm soát → bằng chứng kiểm chứng → rủi ro còn lại**, để không nhầm “test xanh” với “hệ thống đã an toàn”.

## 1. Vì sao cần mô hình đe dọa trước khi chọn công cụ?

Độ an toàn không chỉ là việc mã có ít lỗi cú pháp hay tránh một số mẫu hàm nguy hiểm. Bảo mật là thuộc tính của **hệ thống đang thực thi trong bối cảnh cụ thể**: ai được phép xem dữ liệu, ai có thể sửa dữ liệu, hệ thống nào được tin cậy, những ràng buộc nào phải đúng và hậu quả khi chúng bị vi phạm.

Ví dụ, công cụ phân tích tĩnh có thể phát hiện nguy cơ ghép chuỗi vào SQL, nhưng nó khó tự suy ra rằng người dùng A **không được tải báo cáo do người dùng B sở hữu**, nếu luật sở hữu này chưa được biểu diễn trong mã và chưa có kiểm thử phù hợp.

Ngược lại, một test xác nhận người A không tải được báo cáo B vẫn chưa chứng minh không tồn tại lỗ hổng ở các đường khác, như endpoint tải hàng loạt, bản xem trước, URL tải tạm thời hoặc tác vụ nền.

Một **mô hình đe dọa** có ích nên trả lời:

1. **Đang bảo vệ điều gì?** Dữ liệu cá nhân, thông tin thanh toán, bí mật hệ thống, tính đúng đắn của nghiệp vụ, khả năng phục vụ.
2. **Ai tác động được vào đâu?** Người dùng đã đăng nhập, người dùng chưa đăng nhập, hệ thống đối tác, người vận hành, tác vụ tự động.
3. **Dữ liệu đi qua những thành phần và ranh giới nào?** Thiết bị khách, API, service, database, object storage, queue.
4. **Điều gì có thể bị lợi dụng hoặc sai lệch?** Giả mạo danh tính, vượt quyền, làm lộ dữ liệu, thay đổi nội dung, gây cạn tài nguyên.
5. **Biện pháp nào dự định ngăn chặn, phát hiện hoặc giảm tác hại?** Kiểm tra danh tính/quyền, ràng buộc dữ liệu, giới hạn tài nguyên, ghi nhận sự kiện, phân vùng.
6. **Làm sao chứng minh biện pháp có hiệu quả trong những tình huống quan trọng?** Review, phân tích, test ở ranh giới thích hợp, thử lỗi và giám sát.

Mục đích không phải dự đoán toàn bộ hành vi của mọi tác nhân trong mọi thời điểm, mà là **đưa các giả định bảo mật quan trọng ra ánh sáng** để thiết kế và kiểm chứng có định hướng.

## 2. Phân biệt tài sản, luồng dữ liệu và ranh giới tin cậy

Giả sử hệ thống có API giả định:

~~~http
GET /api/reports/{reportId}/download
Authorization: Bearer <access-token>
~~~

Nghiệp vụ đã xác nhận: một người dùng chỉ được tải báo cáo thuộc quyền của mình; báo cáo không tồn tại hoặc không được phép xem đều không được trả dữ liệu. Báo cáo được lưu ở object storage, còn thông tin sở hữu được quản lý trong cơ sở dữ liệu.

Đây là một tình huống minh họa cho bài học, **không phải một giao thức sản phẩm đang được triển khai**.

### Luồng dữ liệu rút gọn

~~~text
 [Trình duyệt / ứng dụng khách]
       |
       | reportId (không tin cậy), access token
       v
 +--------------------------+
 | API / lớp xác thực       |
 | Xác minh danh tính       |
 +--------------------------+
       | principal đã được xác thực
       | reportId do người gọi chọn
       v
 +--------------------------+
 | ReportService            |
 | Kiểm tra quyền theo      |
 | chủ sở hữu tài nguyên    |
 +--------------------------+
       |                      |
       v                      v
 [Database metadata]    [Object storage]
  ownerId, storageKey     nội dung báo cáo
       |                      |
       +-----------+----------+
                   |
                   v
             Kết quả tải
~~~

**Ranh giới tin cậy (trust boundary)** là nơi dữ liệu hoặc quyền được diễn giải khác đi. Ví dụ:

- `reportId` đến từ URL do người gọi kiểm soát: **không được tin rằng người gửi có quyền với mã đó**.
- Access token là đầu vào do client gửi: chỉ sau khi được xác minh theo cơ chế xác thực, hệ thống mới tạo được **principal đáng tin cậy** cho request.
- Một service nội bộ vẫn phải kiểm tra **quyền theo tài nguyên**, không được suy ra “đã qua lớp API thì tất cả mã báo cáo đều hợp lệ”.
- Object storage có thể sử dụng thông tin định vị nội bộ; không được dùng một khóa lưu trữ do client đưa vào mà không có ràng buộc quyền phù hợp.

### Những tài sản và thuộc tính cần bảo vệ

| Tài sản / hoạt động | Thuộc tính cần bảo vệ | Ví dụ vi phạm |
| --- | --- | --- |
| Nội dung báo cáo | **Bí mật (confidentiality)** | Người A tải được báo cáo của B |
| Thông tin sở hữu báo cáo | **Toàn vẹn (integrity)** | Người dùng thường tự đổi chủ sở hữu |
| Danh tính người yêu cầu | **Tính xác thực (authenticity)** | API nhận `userId` từ query và coi đó là chủ thể đã đăng nhập |
| Sự kiện tải tài liệu | **Khả năng truy vết (accountability)** | Không xác định được thao tác nào dẫn tới truy cập bất thường |
| Dịch vụ tải báo cáo | **Khả dụng (availability)** | Nhiều yêu cầu tải quá lớn khiến dịch vụ cạn tài nguyên |

Xác định tài sản giúp nhóm biết **hậu quả của một lỗi**. Thứ tự ưu tiên của hệ thống báo cáo tài chính có thể khác với ứng dụng chia sẻ tài liệu công khai; không có danh sách rủi ro phù hợp cho mọi sản phẩm.

## 3. Dùng STRIDE để khơi gợi kịch bản

**STRIDE** là một phương pháp phân nhóm đe dọa. Nó hữu ích như một **checklist đặt câu hỏi**, không phải bộ chứng nhận bảo mật hay máy tự động tìm ra tất cả lỗ hổng.

| Nhóm STRIDE | Câu hỏi trong API tải báo cáo | Ví dụ kiểm soát cần xem xét |
| --- | --- | --- |
| **S — Spoofing** (giả mạo danh tính) | Có thể dùng danh tính người khác để gửi yêu cầu không? | Xác minh token, quản lý phiên, chỉ lấy principal từ nguồn đã xác thực |
| **T — Tampering** (can thiệp dữ liệu) | Có thể sửa `reportId` hoặc khóa lưu trữ để đổi tài nguyên được tải không? | Kiểm tra quyền theo tài nguyên, không tin tham số client, bảo vệ metadata |
| **R — Repudiation** (phủ nhận thao tác) | Có truy vết được yêu cầu nhạy cảm và quyết định cho phép/từ chối không? | Audit log đủ ngữ cảnh và bảo vệ log khỏi sửa trái phép |
| **I — Information disclosure** (lộ thông tin) | Có thể tải hoặc suy ra dữ liệu của người khác không? | Kiểm soát quyền từng đối tượng, hạn chế dữ liệu trả về, thông điệp lỗi không tiết lộ dư thừa |
| **D — Denial of service** (từ chối dịch vụ) | Có thể yêu cầu tải lặp lại hoặc kích thước quá lớn làm cạn tài nguyên không? | Giới hạn tải, timeout, kiểm soát số kết nối, giới hạn tài nguyên |
| **E — Elevation of privilege** (leo thang đặc quyền) | Có thể vượt từ người dùng thường lên quyền quản trị hoặc vượt tenant không? | Kiểm tra quyền ở server, giới hạn đặc quyền và phạm vi dữ liệu |

Một đe dọa có thể liên quan nhiều nhóm STRIDE. Ví dụ **truy cập trực tiếp một tài nguyên không thuộc quyền** (thường được gọi là BOLA/IDOR trong ngữ cảnh API) vừa là vấn đề **kiểm soát quyền**, vừa có thể dẫn đến **lộ thông tin**. Không cần cố gán mỗi lỗi vào đúng một nhãn.

### Viết kịch bản đe dọa có thể kiểm tra

Một mô tả mơ hồ:

> “Có nguy cơ lộ dữ liệu.”

Một kịch bản cụ thể hơn:

> **Tác nhân:** Người dùng A đã đăng nhập, không có quyền xem báo cáo B. **Điểm vào:** `GET /api/reports/{reportId}/download`. **Khả năng kiểm soát:** A có thể thay `reportId` trong đường dẫn. **Điều kiện gây lỗi:** Service truy xuất báo cáo theo ID mà không ràng buộc với principal. **Tác động:** Trả bytes của báo cáo B cho A. **Biện pháp kỳ vọng:** Truy vấn báo cáo phải ràng buộc ID với chủ sở hữu được xác thực; không đọc nội dung khi không có quyền.

Kịch bản này đủ cụ thể để viết **tiêu chí review**, **mã phòng vệ** và **bài kiểm thử phủ định**: thử truy cập báo cáo B với principal A và xác minh hệ thống không trả dữ liệu.

## 4. Đánh giá rủi ro để biết cần kiểm chứng điều gì trước

Không phải mọi kịch bản đều có cùng mức ưu tiên. Trước khi xếp hạng, cần xác nhận **giả định và phạm vi**. Một phương pháp thực tế là đánh giá theo:

- **Tác động:** Mức thiệt hại nếu xảy ra, ví dụ dữ liệu nhạy cảm bị lộ, quyền bị chiếm, nghiệp vụ ngừng hoạt động.
- **Khả năng xảy ra / khả năng khai thác:** Điều kiện tiếp cận bề mặt tấn công, độ khó và biện pháp đang tồn tại.
- **Mức phơi lộ:** API công khai hay nội bộ, số người có thể truy cập, dữ liệu nào có mặt.
- **Khả năng phát hiện và khôi phục:** Có giám sát, thu hồi quyền, giới hạn tác động, rollback hay không.

Ví dụ ưu tiên **minh họa**, không phải kết quả đánh giá chính thức:

| Kịch bản | Điều kiện giả định | Ưu tiên tương đối |
| --- | --- | --- |
| Người dùng thường tải dữ liệu nhạy cảm của người khác | Endpoint Internet-facing, dữ liệu riêng tư | **Cao** |
| Một request tải dữ liệu rất lớn làm cạn bộ nhớ | Chưa giới hạn kích thước/đồng thời | **Cao hoặc trung bình**, tùy quy mô/tác động |
| Log thiếu mã tương quan | Đã có các cơ chế giám sát khác | **Trung bình hoặc thấp**, tùy yêu cầu truy vết |
| Thông điệp lỗi tiết lộ tên lớp nội bộ | Không chứa thông tin nhạy cảm khác | **Cần đánh giá**, không mặc định tương đương lộ dữ liệu người dùng |

Điều quan trọng không phải gắn nhãn “cao” cho thật nhiều dòng, mà là ghi được **lý do lựa chọn**, người chịu trách nhiệm và bằng chứng cần có trước khi chấp nhận rủi ro còn lại.

## 5. Rà soát thiết kế: kiểm tra những quyết định mà công cụ khó hiểu

**Design review** xem xét cách các thành phần phối hợp, ai có quyền quyết định và ranh giới nào bảo vệ tài sản. Trong ví dụ API tải báo cáo, những câu hỏi quan trọng gồm:

1. `principalId` được tạo từ quá trình xác thực đáng tin cậy hay lấy từ tham số request?
2. Mọi đường lấy báo cáo (tải, xem trước, xuất hàng loạt, gửi qua email) có dùng cùng một quy tắc sở hữu không?
3. Repository có buộc điều kiện **ID + owner/tenant** không, hay tải đối tượng trước rồi hy vọng nơi gọi kiểm tra?
4. Khóa object storage do database đáng tin cậy cung cấp hay do client tự chọn?
5. Có đường nào trực tiếp lấy tệp bằng URL mà bỏ qua service kiểm tra quyền không?
6. Khi quyền bị thay đổi giữa lúc kiểm tra và lúc đọc, hợp đồng nhất quán được xử lý thế nào?
7. Có giới hạn kích thước, thời gian, số kết nối, số lần tải và cách xử lý thất bại không?
8. Log có đủ thông tin điều tra mà không ghi token hay nội dung riêng tư không?

Những câu hỏi này phát hiện **thiếu ràng buộc nghiệp vụ** mà một công cụ chỉ nhìn mẫu cú pháp có thể không kết luận được.

### Một lựa chọn thiết kế giúp quyền hiển thị trong hợp đồng

Thay vì một repository cung cấp:

~~~java
Optional<ReportMetadata> findById(ReportId id);
~~~

có thể thiết kế một truy vấn dành cho thao tác cần quyền sở hữu:

~~~java
Optional<ReportMetadata> findOwnedById(
    ReportId id,
    UserId authenticatedUser
);
~~~

Ý nghĩa của phương thức thứ hai là **chỉ trả kết quả nếu báo cáo thuộc chủ thể đã được xác thực**. Tên và hợp đồng làm rõ ý định ngay tại vị trí gọi. Tuy nhiên, **đặt tên đúng không bảo đảm implementation đúng**. Adapter thật vẫn phải dùng điều kiện sở hữu/tenant đúng trong truy vấn và được kiểm chứng bằng integration test với nhiều chủ thể.

## 6. Ví dụ Java: đưa kiểm tra quyền vào đường tải báo cáo

Giả sử hệ thống có các kiểu dữ liệu và giao diện sau, viết bằng Java 17. Các khai báo `public` cần được đặt trong tệp Java tương ứng khi triển khai thực tế.

~~~java
public record UserId(String value) {
    public UserId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("userId is required");
        }
    }
}

public record ReportId(String value) {
    public ReportId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("reportId is required");
        }
    }
}
~~~

~~~java
import java.util.Objects;

public record ReportMetadata(
    ReportId id,
    UserId ownerId,
    String storageKey
) {
    public ReportMetadata {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(ownerId, "ownerId");
        if (storageKey == null || storageKey.isBlank()) {
            throw new IllegalArgumentException(
                "storageKey is required"
            );
        }
    }
}
~~~

~~~java
import java.util.Optional;

public interface ReportRepository {
    Optional<ReportMetadata> findOwnedById(
        ReportId reportId,
        UserId authenticatedUser
    );
}

public interface ReportStorage {
    byte[] read(String storageKey);
}
~~~

Service chỉ đọc nội dung sau khi repository trả về metadata thuộc quyền:

~~~java
import java.util.Objects;

public final class ReportService {
    private final ReportRepository repository;
    private final ReportStorage storage;

    public ReportService(
        ReportRepository repository,
        ReportStorage storage
    ) {
        this.repository = Objects.requireNonNull(repository);
        this.storage = Objects.requireNonNull(storage);
    }

    public byte[] download(UserId principalId, ReportId reportId) {
        Objects.requireNonNull(principalId, "principalId");
        Objects.requireNonNull(reportId, "reportId");

        ReportMetadata report = repository
            .findOwnedById(reportId, principalId)
            .orElseThrow(ReportNotFoundException::new);

        return storage.read(report.storageKey());
    }
}

final class ReportNotFoundException extends RuntimeException {
}
~~~

### Các giả định bảo mật bắt buộc hiểu rõ

- `principalId` **phải do lớp xác thực tạo ra sau khi xác minh danh tính**, không lấy trực tiếp từ `?userId=...` hoặc JSON do client gửi. Ở ví dụ này, `ReportService` tin vào lời gọi từ adapter đáng tin cậy; bản thân kiểu `UserId` không chứng minh danh tính.
- `findOwnedById` phải **thực sự ràng buộc tài nguyên với người dùng/tenant được phép xem**. Nếu adapter trả metadata bất kỳ chỉ theo `reportId`, service vẫn có thể làm lộ dữ liệu.
- `storageKey` phải được lấy từ metadata đã qua kiểm tra quyền, không nhận một khóa tùy ý từ request. Object storage cũng cần có quyền truy cập giới hạn phù hợp.
- `ReportNotFoundException` có thể được ánh xạ ra HTTP `404` cho cả “không tồn tại” và “không thuộc quyền” để tránh tiết lộ quá mức. Tuy vậy, chỉ dùng cùng mã trạng thái **không bảo đảm** mọi kênh phụ như độ trễ hoặc log đều không tiết lộ sự tồn tại.
- Đọc toàn bộ tệp vào `byte[]` chỉ phù hợp khi có **giới hạn kích thước phù hợp**. Với báo cáo lớn, cần cân nhắc streaming, kiểm soát timeout và hạn mức tài nguyên; đây là trách nhiệm bảo vệ khả dụng không được thể hiện đầy đủ trong ví dụ.
- Nếu quyền sở hữu có thể thay đổi đồng thời với thao tác tải, cần xác định **mốc hiệu lực của quyền**, transaction hoặc thiết kế bảo đảm nhất quán phù hợp. Một lần kiểm tra trước khi đọc chưa tự giải quyết mọi tình huống thu hồi quyền.

Ví dụ này chủ yếu chứng minh **đường quyết định quyền** và cách biểu diễn phụ thuộc. Nó không phải một server hoàn chỉnh, cũng không thay thế các cơ chế xác thực, TLS, quản lý phiên, cấu hình storage hoặc quy tắc multi-tenant thực tế.

## 7. Kiểm thử theo đe dọa, không chỉ theo đường thành công

Với kịch bản người A cố tải báo cáo của B, bài kiểm thử cần xác minh **không chỉ exception**, mà còn **không có thao tác đọc nội dung từ storage**.

Một bộ test tối giản có thể dùng repository in-memory thực thi hợp đồng sở hữu và storage ghi nhận số lần đọc:

~~~java
import java.nio.charset.StandardCharsets;

final class RecordingReportStorage implements ReportStorage {
    private int reads;

    @Override
    public byte[] read(String storageKey) {
        reads++;
        return "REPORT CONTENT".getBytes(StandardCharsets.UTF_8);
    }

    int reads() {
        return reads;
    }
}
~~~

~~~java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class ReportServiceTest {
    private static final UserId ALICE = new UserId("alice");
    private static final UserId BOB = new UserId("bob");
    private static final ReportId REPORT_B = new ReportId("report-b");

    private ReportRepository repository() {
        Map<ReportId, ReportMetadata> reports = Map.of(
            REPORT_B,
            new ReportMetadata(REPORT_B, BOB, "internal/report-b")
        );

        return (id, principal) -> Optional.ofNullable(reports.get(id))
            .filter(report -> report.ownerId().equals(principal));
    }

    @Test
    void ownerCanDownloadReport() {
        RecordingReportStorage storage = new RecordingReportStorage();
        ReportService service = new ReportService(repository(), storage);

        byte[] result = service.download(BOB, REPORT_B);

        assertArrayEquals(
            "REPORT CONTENT".getBytes(StandardCharsets.UTF_8),
            result
        );
        assertEquals(1, storage.reads());
    }

    @Test
    void anotherUserCannotReadReportContents() {
        RecordingReportStorage storage = new RecordingReportStorage();
        ReportService service = new ReportService(repository(), storage);

        assertThrows(
            ReportNotFoundException.class,
            () -> service.download(ALICE, REPORT_B)
        );
        assertEquals(0, storage.reads());
    }

    @Test
    void missingReportDoesNotAccessStorage() {
        RecordingReportStorage storage = new RecordingReportStorage();
        ReportService service = new ReportService(repository(), storage);

        assertThrows(
            ReportNotFoundException.class,
            () -> service.download(
                BOB, new ReportId("missing-report")
            )
        );
        assertEquals(0, storage.reads());
    }
}
~~~

Các test này chứng minh **cách service xử lý kết quả trả về từ hợp đồng `ReportRepository`**, gồm đường thành công và đường không có quyền. Nhưng chúng **chưa chứng minh repository thật tuân thủ hợp đồng**: fake trong test đã tự lọc quyền, còn adapter database có thể vô tình thiếu điều kiện `ownerId`.

Vì vậy cần thêm **integration test** chạy qua adapter thật với ít nhất hai người dùng và nhiều bản ghi thuộc các chủ sở hữu khác nhau. Cần kiểm tra cả điều kiện tenant nếu hệ thống đa tenant. Test qua HTTP phải xác minh principal thực sự xuất phát từ token/phiên đã được xác thực, không phải từ `userId` do người gọi cung cấp.

### Từ kịch bản sang trường hợp kiểm thử

| Mã | Điều kiện đầu vào | Hành vi kỳ vọng | Ranh giới nên kiểm tra |
| --- | --- | --- | --- |
| AUTH-01 | Không có danh tính hợp lệ | Không truy cập nội dung; lỗi xác thực đúng hợp đồng | HTTP/authentication integration |
| AUTH-02 | B sở hữu báo cáo B | Tải được đúng báo cáo B | Service + storage integration |
| AUTH-03 | A yêu cầu mã báo cáo của B | Không trả nội dung; không đọc nội dung trái quyền | Service, repository, HTTP |
| AUTH-04 | Báo cáo không tồn tại | Không trả nội dung; thông tin lỗi không tiết lộ dư thừa | Service + HTTP |
| AUTH-05 | Client tự truyền `userId=B` khi đang đăng nhập A | Không được dùng tham số đó để đổi principal | HTTP/authentication integration |
| AUTH-06 | Người dùng yêu cầu nhiều báo cáo đồng thời | Không vượt giới hạn tài nguyên đã cam kết | Load/abuse tests + quan sát |
| AUTH-07 | Quyền bị thu hồi trong lúc xử lý | Hành vi theo chính sách hiệu lực quyền đã xác nhận | Integration/concurrency tests |

Điểm quan trọng là test phải xuất phát từ **mô hình đe dọa và hợp đồng bảo vệ**, không chỉ từ từng nhánh `if` được thấy trong mã.

## 8. Phối hợp các hình thức phân tích và kiểm thử

Không có một công cụ nào nhìn thấy đủ mọi khía cạnh. Chúng bổ sung cho nhau nếu được đặt đúng câu hỏi.

| Hoạt động | Điểm mạnh | Giới hạn tiêu biểu | Cách dùng trong ví dụ |
| --- | --- | --- | --- |
| **Rà soát thiết kế** | Phát hiện thiếu ranh giới quyền, luồng dữ liệu và giả định sai | Phụ thuộc chất lượng mô hình và kiến thức người review | Kiểm tra mọi đường tải đều ràng buộc principal–report |
| **Code review có định hướng bảo mật** | Xem cách quy tắc được thực thi ở đoạn mã cụ thể | Khó bao phủ mọi tổ hợp khi hệ thống lớn | Review adapter `findOwnedById` và nơi tạo principal |
| **SAST** (phân tích tĩnh mã nguồn) | Tìm một số mẫu nguy hiểm, luồng dữ liệu và API dễ dùng sai | Có false positive/false negative; không tự hiểu mọi luật sở hữu | Tìm nguồn đầu vào không tin cậy đi đến truy vấn/đọc tệp |
| **SCA** (phân tích thành phần/phụ thuộc) | Nhận diện thư viện, phiên bản và rủi ro đã biết trong chuỗi cung ứng | Không chứng minh ứng dụng không có bug logic; mức ảnh hưởng cần đánh giá | Xem dependency auth, parser, HTTP client |
| **Unit test theo yêu cầu bảo mật** | Nhanh, tái hiện tốt các điều kiện được mô hình hóa | Fake không bảo đảm adapter thật hoạt động đúng | A không đọc được báo cáo B qua service |
| **Integration/contract test** | Kiểm tra kết nối thật giữa các tầng và hợp đồng adapter | Tốn chi phí thiết lập, phụ thuộc môi trường | Truy vấn database phải lọc đúng owner/tenant |
| **Dynamic security testing / DAST** | Quan sát hành vi của ứng dụng đang chạy từ phía giao diện | Có thể không thấy logic bên trong, cần môi trường và dữ liệu phù hợp | Kiểm tra authn/authz và phản hồi HTTP thực |
| **Fuzzing / property-based testing** | Khám phá trường hợp biên, dữ liệu bất thường, tương tác khó dự đoán | Cần oracle/bất biến rõ; không thay thế chính sách quyền | Tạo ID không hợp lệ, kiểm tra không làm lộ dữ liệu/treo |
| **Kiểm thử thủ công chuyên sâu** | Khảo sát luồng nhiều bước và giả định phức tạp | Chất lượng phụ thuộc phạm vi, kỹ năng, thời điểm | Đánh giá thay đổi quyền, luồng download khác nhau |
| **Giám sát khi vận hành** | Phát hiện bất thường sau triển khai và hỗ trợ điều tra | Mang tính quan sát sau thực tế, không thay thế phòng ngừa | Tăng đột biến yêu cầu bị từ chối, tải lớn bất thường |

### Điểm cần nhớ về SAST và SCA

SAST có thể cảnh báo cách xây SQL bằng chuỗi hoặc đường dẫn tệp từ input, nhưng một dòng `repository.findById(id)` **không thể tự chứng minh** đó là truy cập trái quyền nếu công cụ không biết chính sách chủ sở hữu. Cần kiểm tra kịch bản nghiệp vụ bằng review và test.

SCA phát hiện dependency có cảnh báo bảo mật hoặc không còn được hỗ trợ trong các nguồn dữ liệu có sẵn, nhưng kết quả cần được **đánh giá mức ảnh hưởng đối với cấu hình và đường chạy thật**. Một dependency không có cảnh báo tại thời điểm quét không có nghĩa không có lỗi bảo mật.

Tương tự, DAST có thể tìm nhiều vấn đề tại giao diện đang chạy, nhưng kết quả “không phát hiện” chỉ áp dụng cho **phạm vi và tình huống đã thử**, không phải chứng nhận toàn hệ thống.

## 9. Ma trận truy vết: từ đe dọa đến bằng chứng

Để tránh triển khai biện pháp mà không kiểm chứng, có thể quản lý bằng một bảng đơn giản:

| ID đe dọa | Kịch bản | Biện pháp dự kiến | Bằng chứng cần có | Rủi ro cần theo dõi |
| --- | --- | --- | --- | --- |
| TH-01 | Client giả principal của người khác | Principal lấy từ xác thực đã kiểm tra | Review adapter + HTTP test với userId giả | Lỗi cấu hình xác thực, token bị sử dụng sai |
| TH-02 | A tải báo cáo B | Truy vấn có điều kiện quyền theo owner/tenant | Unit test, repository integration, HTTP test nhiều chủ thể | Đường tải khác bỏ qua kiểm tra |
| TH-03 | Client thao túng khóa storage | Khóa nội bộ chỉ lấy từ metadata đã cho phép | Review data flow + negative tests | URL tải trực tiếp hoặc quyền storage quá rộng |
| TH-04 | Ghi log lộ token/dữ liệu riêng tư | Logging giới hạn và che thông tin nhạy cảm | Review log + kiểm thử log giả lập | Đường lỗi chưa bao phủ |
| TH-05 | Yêu cầu tải lớn/lặp nhiều lần | Giới hạn kích thước, tải đồng thời, timeout | Load/abuse tests có giới hạn an toàn | Mẫu tải khác với thực tế, phụ thuộc hạ tầng |
| TH-06 | Quyền thu hồi trong lúc tải | Chính sách mốc quyền rõ và ràng buộc nhất quán | Review transaction + concurrency test | Chênh lệch giữa DB, cache và storage |

**Ma trận truy vết không cần chỉ gồm test tự động.** Một quyết định thiết kế được xác nhận, cấu hình bảo vệ đã kiểm tra, quy trình phát hành dependency và quan sát khi vận hành cũng là bằng chứng. Tuy nhiên, bằng chứng phải ghi rõ **phạm vi**, **người xác minh**, **kết quả** và **thời điểm**. Một ô “đã kiểm tra” thiếu thông tin gần như không giúp điều tra về sau.

### Bằng chứng dương và bằng chứng âm

Đối với chức năng tải báo cáo:

- **Bằng chứng dương:** chủ sở hữu hợp lệ tải được báo cáo đúng.
- **Bằng chứng âm:** người không có quyền **không tải được**, và không có thao tác đọc nội dung trái quyền.
- **Bằng chứng tương tác:** kiểm tra principal, repository, HTTP adapter và storage hoạt động nhất quán theo hợp đồng.
- **Bằng chứng khôi phục/khả dụng:** khi backend lỗi hoặc quá tải, hệ thống không tự chuyển sang bỏ kiểm tra quyền, và báo lỗi theo chính sách.

Một test dương đạt không tự chứng minh test âm. Trong bảo mật, **điều hệ thống phải từ chối** thường quan trọng ngang với điều hệ thống được phép làm.

## 10. Rà soát thay đổi và bảo vệ chống hồi quy

Mô hình đe dọa không nên chỉ được viết một lần lúc khởi tạo dự án. Những thay đổi sau có thể tạo **đường truy cập mới** hoặc làm sai giả định trước đây:

| Thay đổi | Câu hỏi mô hình đe dọa cần cập nhật |
| --- | --- |
| Thêm endpoint xuất nhiều báo cáo | Có kiểm tra quyền cho **từng** báo cáo được xuất không? |
| Thêm cache metadata | Cache có phân biệt người dùng/tenant và xử lý thu hồi quyền đúng không? |
| Đổi storage sang URL tải tạm thời | Ai được cấp URL, giới hạn thời gian/quyền và khả năng chia sẻ lại là gì? |
| Thêm xử lý bất đồng bộ/queue | Worker có giữ đúng principal hoặc ngữ cảnh ủy quyền đã được xác nhận không? |
| Thêm tài khoản quản trị hỗ trợ khách hàng | Có giới hạn đặc quyền, lý do truy cập và audit không? |
| Đổi cơ chế đăng nhập | Principal và quyền được truyền qua các ranh giới theo cách nào? |
| Đổi ORM, framework hoặc dependency | Giả định về truy vấn, lọc tenant, serialization và quyền mặc định có thay đổi không? |

Với thay đổi nhỏ chỉ chỉnh giao diện, có thể rà soát phần liên quan. Với thay đổi ảnh hưởng luồng xác thực, phân quyền hoặc dữ liệu nhạy cảm, cần xem lại mô hình đe dọa rộng hơn và bổ sung test ở những ranh giới mới.

**Chạy lại các security tests sau mỗi lần refactor** giúp bảo vệ quy tắc đã được kiểm tra, nhưng không đủ để phát hiện mối đe dọa mới nếu phạm vi hoặc kiến trúc thay đổi. Vì vậy mô hình đe dọa phải sống cùng mã và quá trình phát hành.

## 11. Quy trình nhóm phát triển có thể áp dụng

Một vòng làm việc thực tế không cần quá nhiều biểu mẫu, nhưng phải có trình tự và đầu ra rõ:

**Bước 1 — Chọn phạm vi và tài sản.** Xác định chức năng, dữ liệu nhạy cảm, người dùng liên quan và những yêu cầu bảo mật đã được xác nhận. Tránh mô hình hóa “cả hệ thống” khi không có phạm vi đủ rõ.

**Bước 2 — Vẽ luồng và ranh giới tin cậy.** Ghi dữ liệu đi từ đâu tới đâu, nơi xác thực và phân quyền, nguồn cấu hình, storage, queue và hệ thống bên ngoài. Đánh dấu dữ liệu do người gọi kiểm soát.

**Bước 3 — Liệt kê kịch bản theo đe dọa.** Dùng STRIDE để đặt câu hỏi, sau đó viết kịch bản với tác nhân, điểm vào, khả năng kiểm soát, điều kiện gây lỗi và tác động. Tránh chỉ ghi tên loại tấn công.

**Bước 4 — Ưu tiên theo rủi ro.** Đánh giá tác động và điều kiện khai thác trong bối cảnh thực, xác định chủ sở hữu và lựa chọn cách xử lý: giảm thiểu, thay đổi thiết kế, tránh rủi ro hoặc chấp nhận có lý do.

**Bước 5 — Rà soát thiết kế trước khi viết test.** Xác định biện pháp ở đúng ranh giới và kiểm tra **mọi đường đi** có thể chạm tài sản. Thiết kế API khó bị dùng sai: principal đáng tin cậy, quyền theo tài nguyên, hạn chế tác dụng phụ.

**Bước 6 — Chọn kỹ thuật kiểm chứng.** Dùng code review/SAST để xem luồng dữ liệu và mẫu sử dụng nguy hiểm; SCA cho dependency; unit test cho logic; integration/contract test cho adapter; dynamic test cho hành vi thực; kiểm thử tải/race khi mô hình đe dọa yêu cầu.

**Bước 7 — Lưu bằng chứng và rủi ro còn lại.** Ghi rõ điều kiện kiểm thử, kết quả, giới hạn công cụ, ngoại lệ và người chấp nhận quyết định. Không nên chỉ lưu ảnh chụp bảng màu xanh.

**Bước 8 — Theo dõi sau triển khai và cập nhật khi thay đổi.** Quan sát hành vi bất thường, xem xét cảnh báo phụ thuộc, cập nhật kịch bản khi xuất hiện đường tải, quyền hoặc thành phần mới.

Một vòng kiểm chứng có giá trị khi nhóm có thể trả lời câu hỏi: **“Đe dọa quan trọng nào được kiểm soát bằng cơ chế nào, và chúng ta có bằng chứng gì rằng cơ chế đó hoạt động đúng trong những trường hợp đã xét?”**

## 12. Những ngộ nhận thường gặp

| Ngộ nhận | Vì sao chưa đúng | Hướng tiếp cận tốt hơn |
| --- | --- | --- |
| “Có đăng nhập rồi thì API an toàn.” | Đăng nhập chứng minh danh tính, không tự chứng minh quyền trên từng tài nguyên | Kiểm tra authorization theo object và hành động |
| “SAST xanh nghĩa là không có lỗ hổng.” | Công cụ không nhìn thấy mọi luật nghiệp vụ và có giới hạn phân tích | Kết hợp design review, test theo threat scenario |
| “Nhiều test nghĩa là bảo mật cao.” | Test có thể bỏ qua những điều hệ thống **phải từ chối** | Truy vết các đe dọa và kiểm thử đường âm |
| “Unit test với fake đã chứng minh database lọc quyền.” | Fake có thể đúng nhưng truy vấn thật sai | Integration test với dữ liệu nhiều người/tenant |
| “Đã trả 404 thì chắc chắn không tiết lộ gì.” | Có thể còn khác biệt ở dữ liệu trả về, thời gian, log hoặc endpoint khác | Review toàn bộ kênh quan sát phù hợp |
| “Đã kiểm tra quyền một lần thì không cần nữa.” | Quyền và trạng thái có thể thay đổi giữa các bước | Xác định mốc hiệu lực và kiểm tra ở ranh giới nhất quán |
| “Không có cảnh báo thư viện thì dependency an toàn.” | Cảnh báo có thể chưa tồn tại hoặc không bao phủ bug logic | Quản lý phiên bản, review và đánh giá mức ảnh hưởng |
| “Threat model xong thì không cần cập nhật.” | Endpoint, data flow và tác nhân thay đổi theo sản phẩm | Xem lại mô hình cùng mỗi thay đổi có ý nghĩa |

## 13. Bài tập tình huống

Đội phát triển bổ sung tính năng **gửi báo cáo qua email**:

~~~text
POST /api/reports/{reportId}/email
Body: { "recipientEmail": "..." }
~~~

Người gọi đã đăng nhập. Hệ thống lấy báo cáo từ object storage và gửi tệp đính kèm tới địa chỉ email được cung cấp.

Giả sử chính sách đã xác nhận: **chỉ chủ sở hữu báo cáo mới được yêu cầu gửi**, và người sở hữu được phép gửi tới địa chỉ mà họ nhập (không có yêu cầu giới hạn trong danh bạ). Hệ thống phải ghi nhận yêu cầu gửi có thể truy vết, không để gửi trùng ngoài ý muốn khi retry.

**Câu hỏi A.** Chỉ ra ít nhất bốn đe dọa cần thêm vào mô hình so với API tải báo cáo cũ.

**Câu hỏi B.** Với mỗi đe dọa, đề xuất một biện pháp kiểm soát và một bằng chứng phù hợp. Không chỉ ghi “thêm unit test”.

**Câu hỏi C.** Vì sao test thành công khi chủ sở hữu gửi một báo cáo tới email của mình **không đủ** chứng minh tính bảo mật của tính năng?

### Gợi ý đáp án

**A.** Có thể xét: người A gửi báo cáo của B; địa chỉ email bị sửa hoặc bị dùng để phát tán nội dung nhạy cảm ngoài ý muốn; lỗi queue/retry làm gửi trùng; dữ liệu đính kèm bị ghi vào log; số lượng hoặc kích thước email gây cạn tài nguyên; tác vụ nền gửi khi quyền đã bị thu hồi nếu chính sách yêu cầu kiểm tra lại.

**B.** Ví dụ ma trận:

| Đe dọa | Kiểm soát | Bằng chứng |
| --- | --- | --- |
| A gửi báo cáo của B | Kiểm tra quyền theo reportId + principal trước khi tạo tác vụ | HTTP integration test giữa hai người dùng; queue không nhận tác vụ trái quyền |
| Gửi trùng khi retry | Idempotency key và cơ chế ghi nhận trạng thái phù hợp | Integration test mô phỏng cùng request được nhận lại |
| Nội dung hoặc token lọt vào log | Quy tắc logging chỉ giữ metadata cần thiết | Review mã + kiểm thử log với dữ liệu giả |
| Cạn tài nguyên | Giới hạn tệp, số lượt gửi và hàng đợi | Test tải an toàn trong môi trường cô lập, quan sát metric |
| Quyền thay đổi trong khi tác vụ chờ | Quy định rõ thời điểm có hiệu lực của ủy quyền | Review luồng queue + test thay đổi quyền trước lúc worker gửi |

**C.** Đường thành công chỉ chứng minh chủ sở hữu có thể yêu cầu gửi trong một điều kiện. Cần kiểm tra **đường bị từ chối, đường lỗi, sự kiện gửi trùng, môi trường thực và những ranh giới mới**. Khi gửi qua email, ranh giới tin cậy được mở rộng tới người nhận và nhà cung cấp gửi thư; cần xem xét dữ liệu có thể rời hệ thống theo chính sách đã xác nhận.

## Ghi nhớ

**Bảo mật cần sự phối hợp giữa thiết kế, phân tích và kiểm thử có định hướng theo đe dọa.** Mô hình đe dọa xác định **tài sản, tác nhân, ranh giới và tình huống sai có thể xảy ra**; rà soát thiết kế kiểm tra **biện pháp bảo vệ nằm đúng chỗ**; phân tích giúp phát hiện một số mẫu lỗi và rủi ro phụ thuộc; kiểm thử xác minh **hành vi được cho phép và bị từ chối** trong những điều kiện có ý nghĩa.

Không có một con số coverage, công cụ quét hay danh sách test xanh nào tự chứng minh hệ thống hoàn toàn an toàn. Bằng chứng có giá trị nhất là sự liên kết rõ ràng **đe dọa → biện pháp kiểm soát → kiểm chứng → rủi ro còn lại**, được duy trì khi mã nguồn, kiến trúc và yêu cầu nghiệp vụ thay đổi.
