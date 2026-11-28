# Correlation giữa các event

## 1. Từ những sự kiện rời rạc tới một giả thuyết cần điều tra

Một hệ thống ghi nhận thay đổi quyền, xác thực thành công và export dữ liệu ở ba dịch vụ khác nhau. Mỗi sự kiện riêng lẻ có thể hợp lệ. Khi cùng liên quan tới một chủ thể, đúng tenant và một khoảng thời gian ngắn, chúng có thể tạo thành một tín hiệu cần xem xét.

**Correlation giữa các event** là quá trình liên kết những sự kiện theo một hợp đồng về định danh, quan hệ, thời gian và ngữ nghĩa để nhận diện mẫu hành vi hoặc dựng lại ngữ cảnh.

Correlation không tự chứng minh quan hệ nhân quả, ý định của người thao tác hoặc một sự cố đã xảy ra. Nó tạo ra một kết quả có bằng chứng và giới hạn mà người hoặc hệ thống có thẩm quyền có thể kiểm chứng tiếp.

Trong chương Monitoring và detection, yêu cầu cần trả lời được: liên kết event nào, theo khóa nào, trong cửa sổ nào, tin nguồn nào, xử lý dữ liệu thiếu ra sao và cảnh báo dựa vào bằng chứng gì.

Sau bài này, người học có thể:

- Phân biệt liên kết định danh, quan hệ thực thể và tương quan theo thời gian.
- Chọn khóa join đúng vai trò chủ thể và phạm vi tenant.
- Đặc tả event time, dedup, dữ liệu muộn và giới hạn state.
- Tránh biến thiếu dữ liệu hoặc một thuộc tính trùng thành kết luận chắc chắn.
- Chuyển mẫu phát hiện thành yêu cầu, kiến trúc và tiêu chí kiểm thử có thể truy vết.

## 2. Những dạng correlation thường gặp

| Dạng liên kết | Ví dụ | Mức kết luận phù hợp |
|---|---|---|
| Cùng đối tượng nghiệp vụ | Các mốc requested, materialized và delivery của một export ID | Những quan sát thuộc cùng vòng đời theo hợp đồng ID |
| Cùng luồng thực thi | Các service span hoặc event có trace ID tin cậy | Cùng luồng được instrument, chưa chắc cùng một quyết định bảo mật |
| Cùng chủ thể đã ánh xạ | Thay đổi quyền và hành động của một principal trong tenant | Liên quan tới cùng thực thể theo mapping đã xác minh |
| Cùng cửa sổ thời gian | Export gần một lần thay đổi quyền | Có quan hệ thời gian theo độ chính xác được biết |
| Tham chiếu nguồn gốc tường minh | Job được tạo từ request hoặc event có parent reference | Có liên kết do nguồn khai báo và được kiểm chứng theo hợp đồng |
| Thuộc tính yếu trùng nhau | Cùng IP, nhóm thiết bị hoặc user agent | Có ngữ cảnh chung, không đủ để đồng nhất danh tính |

Không gán cùng độ tin cậy cho mọi dạng. Hai người dùng chung địa chỉ mạng có thể không liên quan; hai request dùng cùng một token bị đánh cắp cũng không chứng minh cùng một con người đang thao tác.

Tham chiếu tường minh có giá trị khi producer và cách tạo reference được tin cậy. Người gọi tự đặt `correlationId` không làm cho các sự kiện mang giá trị đó trở thành một chuỗi đáng tin.

### 2.1. Correlation ID không phải credential

Correlation ID giúp đối chiếu, không cấp quyền đọc log, tải artifact hoặc thực hiện hành động. Không dùng session cookie, access token hoặc URL có chữ ký làm khóa đối chiếu.

Nếu giữ ID do client gửi, coi đó là dữ liệu không tin cậy, có giới hạn và ngữ nghĩa riêng. Thành phần tin cậy cần tạo hoặc xác lập những ID dùng cho quan hệ bảo mật nội bộ.

## 3. Chuẩn hóa ngữ nghĩa trước khi join

### 3.1. Tên event giống nhau chưa có nghĩa giống nhau

Một service ghi `login_success` khi password đúng, service khác chỉ ghi khi toàn bộ MFA hoàn tất. Join hai loại dưới cùng một nhãn có thể tạo chuỗi xác thực sai.

Tương tự, `export_success` có thể nghĩa là nhận job, tạo file hoặc gửi dữ liệu xong. Rule phải dùng trạng thái thực sự cần, không chỉ chuỗi tên thuận tiện.

Mỗi loại event cần có:

- Sự thật mà nó đại diện và điểm phát sinh.
- Producer hoặc ranh giới có thẩm quyền về sự thật đó.
- Các vai trò chủ thể và đối tượng bị tác động.
- Ý nghĩa outcome, thời gian và phép đo.
- Schema version và cách diễn giải khi schema thay đổi.

### 3.2. Normalization không được phát minh dữ liệu

Có thể ánh xạ nhiều nguồn sang schema chung, nhưng phải giữ provenance để truy về nguồn và ngữ nghĩa gốc. Field không có không nên được điền một giá trị có vẻ hợp lệ chỉ để hoàn thành schema.

Ví dụ, không có tenant không có nghĩa là tenant toàn cục; không biết outcome không có nghĩa là thành công; thiếu subject không có nghĩa là service quản trị mặc định.

Field suy luận nên có nguồn và trạng thái riêng. Không trộn dữ liệu được producer xác nhận với dữ liệu detector dự đoán rồi trình bày tất cả như sự thật ngang nhau.

### 3.3. Ví dụ event thay đổi quyền

```json
{
  "schemaVersion": 1,
  "eventType": "PRIVILEGE_GRANTED",
  "sourceRef": "identity-admin-service",
  "eventId": "02fd8b19-bd5f-4074-bf71-7e99772e77cd",
  "tenantRef": "tenant-fixture-A",
  "actorRef": "administrator-fixture-3",
  "targetSubjectRef": "subject-fixture-17",
  "resourceScopeRef": "customer-data-scope",
  "outcome": "SUCCEEDED",
  "effectiveAt": "2026-11-27T07:00:00Z",
  "occurredAt": "2026-11-27T07:00:00Z",
  "policyRevision": "access-policy-r11"
}
```

Mọi giá trị là dữ liệu tổng hợp. `actorRef` là người cấp quyền; `targetSubjectRef` là người được cấp. Rule tìm hành động sau đó của người nhận quyền phải liên kết target với initiator của hành động, không liên kết actor quản trị với initiator.

## 4. Chọn đúng khóa và đúng vai trò thực thể

### 4.1. Không dùng một field user chung cho mọi nghĩa

| Vai trò | Ý nghĩa | Lỗi join điển hình |
|---|---|---|
| Actor | Chủ thể thực hiện hành động | Nhầm với người bị thay đổi quyền |
| Target subject | Tài khoản được tác động | Không được dùng thay principal thực thi mọi bước |
| Initiator | Chủ thể khởi tạo yêu cầu hoặc job | Bị mất khi worker chạy dưới service account |
| Executor | Principal thực thi kỹ thuật | Gộp mọi người dùng thành một worker |
| Effective subject | Chủ thể mà quyền được áp dụng trong một mô hình ủy quyền | Che khuất người khởi tạo thực trong luồng impersonation |

Rule cần nêu rõ quan hệ field. Câu “join theo user ID” là thiếu nếu mỗi nguồn dùng từ user cho một vai trò khác nhau.

### 4.2. Định danh cần namespace và phạm vi

Một subject ID chỉ duy nhất trong một tenant hoặc issuer không nên được join toàn cục bằng chuỗi thô. Có thể cần tổ hợp tenant, namespace và định danh chuẩn hóa.

Nếu hệ thống đã ánh xạ về principal nội bộ, mapping phải được xác minh và có ngữ nghĩa ổn định. Không coi hai email giống nhau từ các nguồn chưa tin cậy là cùng một tài khoản.

Alias, đổi tên và liên kết tài khoản có thể thay đổi theo thời gian. Correlation lịch sử cần mapping có hiệu lực tại thời điểm liên quan hoặc một reference ổn định phù hợp, không chỉ tra tên hiện tại rồi diễn giải ngược quá khứ.

### 4.3. Các loại ID phục vụ phạm vi khác nhau

| ID | Phạm vi liên kết thích hợp |
|---|---|
| Event ID | Một sự kiện logic trong namespace nguồn đã chốt |
| Request ID | Một request hoặc lần xử lý theo hợp đồng của hệ thống |
| Trace ID | Luồng instrumentation, có thể qua nhiều service |
| Authentication ID | Một lần chấp nhận danh tính theo state machine |
| Session reference | Một phiên theo reference không có khả năng xác thực |
| Job hoặc operation ID | Vòng đời công việc hoặc thao tác nghiệp vụ |
| Export ID | Các giai đoạn của một export logic |

Hai event có cùng request ID không nhất thiết là cùng event và không nên bị dedup thành một. Ngược lại, một job bất đồng bộ có thể liên quan request gốc dù request đã kết thúc từ lâu.

## 5. Viết một mẫu tương quan có thể triển khai

### 5.1. Tình huống minh họa

| Thời điểm theo nguồn | Event | Vai trò liên quan |
|---|---|---|
| 07:00 | Cấp quyền thành công | Actor là quản trị viên, target là U17 trong tenant A |
| 07:03 | Xác thực được ứng dụng chấp nhận | Principal là U17 trong tenant A |
| 07:08 | Artifact export được tạo | Initiator là U17, executor là report worker, tenant A |

Mẫu có thể tạo candidate alert “export gần thời điểm được cấp quyền”. Event xác thực có thể được dùng làm enrichment nếu liên kết đủ căn cứ, nhưng không tự chứng minh lần export dùng đúng phiên đó chỉ vì cùng subject và gần thời gian.

Muốn liên kết tới một phiên hoặc authentication cụ thể, cần reference thích hợp và nguồn truyền context đáng tin. Nếu chỉ có các ứng viên gần nhau, giữ mức kết luận là ứng viên.

### 5.2. Hợp đồng rule minh họa

```text
Mục đích:
  Tìm export dữ liệu nhạy cảm gần một thay đổi quyền liên quan cùng subject.

Event A:
  Quyền đã được cấp và có hiệu lực theo nguồn có thẩm quyền.

Event B:
  Artifact export đã được tạo, không phải chỉ nhận job.

Khóa liên kết:
  A.targetSubject = B.initiator trong cùng tenant và namespace chuẩn hóa.

Phạm vi:
  Nhóm tài nguyên hoặc quyền thuộc tập mà rule quan tâm.

Thời gian fixture:
  B.occurredAt thuộc đoạn từ A.effectiveAt đến A.effectiveAt + 15 phút,
  bao gồm hai biên theo hợp đồng của ví dụ.

Kết quả:
  Candidate alert có reference A, B, revision rule và chất lượng bằng chứng.
```

Khoảng 15 phút là giá trị fixture, không phải ngưỡng chung cho mọi sản phẩm. Cần kiểm tra ca trước biên, đúng biên và ngoài biên theo rule thực tế.

Timestamp bằng nhau nằm trong cửa sổ của ví dụ nhưng không chứng minh thay đổi quyền thực sự xảy ra trước export. Nếu mục tiêu yêu cầu thứ tự chặt, cần độ phân giải, độ chính xác hoặc quan hệ trạng thái đủ căn cứ; không dựa vào việc hai chuỗi thời gian được sắp xếp.

### 5.3. Cùng thời gian không có nghĩa quyền mới đã gây ra export

Chủ thể có thể vốn đã có quyền export từ một nguồn khác. Một thay đổi vừa xảy ra có thể không liên quan tới dữ liệu đã xuất.

Muốn kết luận mạnh hơn, cần bằng chứng về quyết định phân quyền, phạm vi quyền và policy version thực sự được sử dụng. Ngay cả khi liên kết được quyết định đó, ý định lạm dụng vẫn là câu hỏi cần điều tra riêng.

Tên alert phải phản ánh mức bằng chứng, tránh biến “gần nhau theo rule” thành “đã khai thác quyền vừa cấp”.

## 6. Thời gian, dữ liệu đến muộn và đóng cửa sổ

### 6.1. Tách các loại thời gian

- `occurredAt`: thời điểm sự kiện theo hợp đồng nguồn.
- `effectiveAt`: thời điểm thay đổi có hiệu lực nếu khác thời điểm ghi nhận.
- `observedAt` hoặc `ingestedAt`: thời điểm tầng quan sát hoặc collector nhận.

Một event xảy ra trước nhưng đến sau không nên bị loại chỉ vì detector xử lý theo thứ tự mạng. Rule phải xác định đang dùng event time hay ingest time và vì sao.

Nếu producer khác nhau có clock không đủ chính xác cho khoảng so sánh, cần trạng thái không chắc chắn hoặc chính sách dung sai đã chốt. Không tự cộng một khoảng tùy ý rồi coi thứ tự thực tế đã được chứng minh.

### 6.2. Watermark là quy tắc tiến độ, không phải phép biết tương lai

Trong hệ thống xử lý theo event time, watermark có thể biểu diễn mức tiến độ được dùng để quyết định cửa sổ nào được coi là đủ điều kiện đóng theo policy.

Vẫn cần hành vi cho event đến sau giới hạn: cập nhật kết quả, tạo bản bổ sung, đưa vào đường phân tích lịch sử hoặc ghi nhận đã bỏ ngoài cửa sổ theo hợp đồng. Không được im lặng bỏ rồi tuyên bố lịch sử đầy đủ.

Với nhiều nguồn, một nguồn ngừng phát hoặc bị trễ cần được phản ánh trong chất lượng cửa sổ. Nếu chọn tiến tiếp vì timeout nguồn, phải ghi rõ trạng thái suy giảm; không biến nguồn mất kết nối thành bằng chứng không có sự kiện.

### 6.3. Replay và backfill cần chế độ rõ

Replay phải giữ thời điểm và định danh nguồn. Không biến thời điểm ingest mới thành thời điểm hành vi mới.

Chốt việc replay có được cập nhật incident hiện hữu, tạo alert lịch sử hay chỉ dùng đánh giá rule. Không để một đợt backfill tự phát hàng nghìn notification hiện tại như thể mọi hành vi vừa xảy ra.

State phải được giữ đủ cho cửa sổ và chính sách dữ liệu muộn đã xác định. Nếu event cần đối chiếu đã bị dọn, phải có kết quả hoặc giới hạn rõ thay vì khẳng định không tìm thấy quan hệ trong lịch sử hoàn chỉnh.

## 7. Kiến trúc và state của correlation engine

Một pipeline minh họa:

```text
Nguồn đã xác thực
  -> kiểm tra schema, ngữ nghĩa và chất lượng
  -> chuẩn hóa thực thể cùng provenance
  -> nhận diện giao nhận trùng và xung đột định danh
  -> partition theo scope, duy trì state cửa sổ
  -> đánh giá quan hệ và rule
  -> tạo bằng chứng kết quả đã giảm dữ liệu
  -> cập nhật alert hoặc incident
  -> giao notification và lưu phản hồi điều tra
```

### 7.1. Dedup không được xóa các sự kiện khác nhau

Khóa dedup thường cần nguồn hoặc namespace cùng event ID theo hợp đồng. Hai producer có event ID giống nhau không mặc nhiên là cùng sự kiện.

Nếu cùng định danh nguồn nhưng nội dung cốt lõi mâu thuẫn, cần phát hiện xung đột thay vì âm thầm giữ bản đầu hoặc bản cuối. Những thay đổi do normalization version hoặc enrichment hợp lệ phải có provenance riêng để không bị lẫn với thay đổi sự thật nguồn.

Không dùng subject ID, request ID hoặc timestamp đơn lẻ làm khóa dedup cho mọi loại event.

### 7.2. Quan hệ nhiều-nhiều cần chính sách

Một export có thể nằm gần nhiều lần thay đổi quyền; một thay đổi quyền có thể liên quan nhiều export. Nếu join mọi cặp rồi tạo notification cho từng cặp, số kết quả và nhiễu có thể tăng mạnh.

Chốt rule muốn giữ mọi bằng chứng phù hợp, chọn một quan hệ theo tiêu chí cụ thể hay nhóm vào cùng incident. Không tùy tiện lấy “event gần nhất” nếu nó có thể không thuộc phạm vi quyền liên quan.

Giới hạn fan-out, kích thước state và thời hạn lưu phải đi cùng tín hiệu khi giới hạn bị chạm. Cắt bớt ứng viên mà vẫn báo đã đánh giá đầy đủ là kết luận sai.

### 7.3. Context bất đồng bộ và tham chiếu nguồn gốc

Job cần giữ các reference được phép và principal theo mô hình ủy quyền, không chỉ trace ID của worker mới. Không sao chép credential vào message để tiện correlation.

Nếu dùng parent event hoặc causation reference, xác minh source, loại quan hệ và scope. Reference tự trỏ, vòng lặp hoặc liên kết tới tenant khác cần có hành vi kiểm tra phù hợp. Một field tên `causedBy` vẫn là khai báo cần được đánh giá theo nguồn, không phải chứng minh tự thân.

## 8. Ví dụ Java: join đúng target, initiator và tenant

Ví dụ dùng Java 17 trở lên. Hai loại event đã được lọc đúng outcome và chuẩn hóa từ nguồn tin cậy. Helper chỉ kiểm tra một cặp trong cửa sổ, không phải toàn bộ correlation engine.

```java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public final class PrivilegeExportCorrelation {
    private PrivilegeExportCorrelation() {}

    public enum EvidenceQuality {
        COMPARABLE,
        UNCERTAIN
    }

    public enum Decision {
        MATCHED,
        NOT_MATCHED,
        INDETERMINATE
    }

    // Subject reference được chuẩn hóa trong phạm vi tenant của ví dụ.
    public record PrincipalRef(UUID tenantRef, UUID subjectRef) {
        public PrincipalRef {
            Objects.requireNonNull(tenantRef);
            Objects.requireNonNull(subjectRef);
        }
    }

    public record GrantEvent(PrincipalRef targetSubject, Instant effectiveAt) {
        public GrantEvent {
            Objects.requireNonNull(targetSubject);
            Objects.requireNonNull(effectiveAt);
        }
    }

    public record ExportEvent(PrincipalRef initiator, Instant occurredAt) {
        public ExportEvent {
            Objects.requireNonNull(initiator);
            Objects.requireNonNull(occurredAt);
        }
    }

    public static Decision correlate(
        GrantEvent grant,
        ExportEvent export,
        Duration maxGap,
        EvidenceQuality quality
    ) {
        Objects.requireNonNull(grant);
        Objects.requireNonNull(export);
        Objects.requireNonNull(maxGap);
        Objects.requireNonNull(quality);

        if (maxGap.isNegative() || maxGap.isZero()) {
            throw new IllegalArgumentException("INVALID_WINDOW");
        }
        if (!grant.targetSubject().equals(export.initiator())) {
            return Decision.NOT_MATCHED;
        }
        if (quality != EvidenceQuality.COMPARABLE) {
            return Decision.INDETERMINATE;
        }

        Duration gap = Duration.between(
            grant.effectiveAt(), export.occurredAt()
        );
        if (gap.isNegative() || gap.compareTo(maxGap) > 0) {
            return Decision.NOT_MATCHED;
        }
        return Decision.MATCHED;
    }
}
```

Những lựa chọn quan trọng:

- Target của grant được so với initiator của export, không phải actor quản trị.
- Principal reference gồm cả tenant và subject của mô hình chuẩn hóa.
- Cửa sổ có hai biên inclusive theo hợp đồng của ví dụ; gap bằng không được chấp nhận là cùng mốc cửa sổ.
- Không đủ căn cứ so sánh thì trả INDETERMINATE thay vì tự coi là không khớp.
- Không dùng IP hoặc credential làm định danh liên kết.

`EvidenceQuality.COMPARABLE` phải có tiêu chí do pipeline xác lập, bao gồm ngữ nghĩa thời gian và mapping. Không để client gửi cờ này để nâng chất lượng dữ liệu của chính nó.

MATCHED chỉ nói cặp đã thỏa điều kiện của helper. Nó không khẳng định quyền mới đã được sử dụng, dữ liệu đã tải hay có ý định lạm dụng. NOT_MATCHED cũng chỉ nói về cặp và cửa sổ đang kiểm tra, không nói chủ thể an toàn trong mọi ngữ cảnh.

Mẫu chưa xử lý phạm vi quyền chi tiết, event ID, dedup, clock uncertainty, watermark, nhiều ứng viên hoặc notification. Những phần đó phải nằm trong hợp đồng và kiểm thử của engine bên ngoài.

## 9. Dữ liệu thiếu và mẫu dựa trên sự vắng mặt

### 9.1. Không tìm thấy không có nghĩa không tồn tại

Một detector không thấy event MFA không thể tự kết luận người dùng đã bỏ qua MFA. Có thể event không nằm trong phạm vi thu, bị sampling, chưa đến hoặc dùng loại sự kiện khác.

Tương tự, không thấy event thu hồi quyền không chứng minh quyền vẫn còn hiệu lực. Phải xác định nguồn nào là nguồn trạng thái có thẩm quyền và quan hệ giữa nó với event stream.

### 9.2. Điều kiện cho rule kiểm tra không có event

Một rule dựa trên sự vắng mặt cần chốt:

- Event nào được kỳ vọng và vì sao nó phải phát sinh.
- Nguồn, phạm vi và cơ chế giao nhận có đủ bao phủ hay không.
- Khoảng chờ, giới hạn muộn và điều kiện đóng cửa sổ.
- Cách phân biệt mất telemetry với việc nghiệp vụ không xảy ra.
- Phản ứng khi source không khỏe hoặc state đã hết hạn.

Nếu những điều kiện đó chưa đủ, tạo kết quả chưa xác định hoặc cảnh báo chất lượng theo hợp đồng. Không gán sự thiếu dữ liệu thành một kết luận buộc tội hoặc bảo đảm an toàn.

### 9.3. Chất lượng liên kết khác với mức rủi ro

Một liên kết rất chắc theo export ID có thể chỉ mô tả công việc bình thường. Một mẫu rủi ro cao nhưng chỉ join bằng thuộc tính yếu vẫn cần ghi rõ giới hạn bằng chứng.

Tách lý do khớp, mức ưu tiên và chất lượng liên kết. Không trình bày một điểm số nội bộ như xác suất tài khoản bị chiếm nếu chưa có đánh giá phù hợp để diễn giải theo cách đó.

## 10. Kết quả correlation phải có bằng chứng và ngữ nghĩa

### 10.1. Nội dung của một kết quả

| Thành phần | Nội dung cần ghi |
|---|---|
| Rule | ID, revision và mục đích |
| Scope | Tenant, namespace và các principal reference được phép |
| Quan hệ | Các field đã liên kết và loại quan hệ |
| Event reference | Nguồn cùng event ID hoặc reference truy vết phù hợp |
| Thời gian | Cửa sổ, mốc được dùng, dung sai và dữ liệu muộn nếu có |
| Chất lượng | Mapping, nguồn thiếu và điều chưa đủ căn cứ |
| Kết luận | Mẫu nào khớp; điều gì chưa được kết luận |
| Xử lý | Chủ sở hữu, trạng thái và runbook tương ứng |

Giữ reference tới bằng chứng đủ để kiểm tra lại theo quyền. Không đính kèm toàn bộ request, token hoặc file export vào alert chỉ để người nhận không cần mở công cụ điều tra.

### 10.2. Một chuỗi event không nhất thiết là một incident

Nhiều rule có thể dùng cùng event. Cần định nghĩa cách nhóm candidate vào alert hoặc incident, cách bổ sung bằng chứng và điều kiện chuyển cấp.

Đừng dedup mọi kết quả có cùng subject rồi che mất một hành động mới hoặc phạm vi dữ liệu khác. Cũng không gửi lại toàn bộ chuỗi mỗi lần một event lặp được giao tới.

Giữ lịch sử cập nhật, revision rule và lý do suppression. Việc không gửi một notification mới không nên làm biến mất bằng chứng nền.

### 10.3. Notification là một giai đoạn riêng

Correlation matched không đồng nghĩa cảnh báo đã được giao hoặc đã có người xác nhận. Cần trạng thái giao nhận, retry và cơ chế tránh tạo nhiều incident cho cùng kết quả logic.

Replay hoặc đánh giá lại bằng rule revision mới cần policy riêng về cập nhật incident. Không sửa âm thầm lý do của alert cũ khiến người điều tra không biết nó từng được tạo theo điều kiện nào.

## 11. Quyền riêng tư và ranh giới của việc liên kết

### 11.1. Correlation tạo ra thông tin mới về hành vi

Từng event có thể chỉ giữ metadata tối thiểu, nhưng khi nối lại chúng có thể tiết lộ lịch làm việc, quan hệ giữa người dùng và nhiều hệ thống hoặc chuỗi hành động nhạy cảm.

Cần xác định mục đích, đối tượng được xem, thời hạn giữ state và alert. Reference giả danh vẫn có thể liên kết về con người, nhất là khi dùng chung toàn hệ thống.

Không mặc định băm email tạo ra dữ liệu vô danh hoặc mapping đáng tin cậy. Khả năng dò đoán, trùng ngữ nghĩa, normalization và quyền tra ngược vẫn cần xem xét. Ưu tiên reference từ registry phù hợp thay vì tự tạo một khóa toàn cục ngoài kiểm soát.

### 11.2. Chặn liên kết và truy cập sai tenant

Engine cần giữ scope trong partition, key và truy vấn bằng chứng. Một event có cùng subject ID dạng chuỗi không cho phép nối qua tenant nếu hợp đồng không xác lập quan hệ đó.

Nếu một chức năng giám sát tập trung có quyền phân tích nhiều tenant, quyền đó cần được xác định rõ. Không có quyền tập trung thì không được mở scope chỉ để tăng số lượng kết quả.

API đọc alert, đồ thị quan hệ và export điều tra phải kiểm tra quyền riêng. Biết event ID hoặc correlation ID không đủ để tải lịch sử.

### 11.3. Không đưa secret vào khóa join hoặc metric

Không dùng token hoặc session credential như cách “chắc chắn cùng phiên”. Dùng reference không cấp quyền từ ngữ cảnh tin cậy.

Metric vận hành nên dùng rule ID, loại lỗi, mức ưu tiên hoặc trạng thái có tập giá trị được kiểm soát. Subject, event ID và correlation ID không phù hợp làm label tăng không giới hạn cho từng chuỗi thời gian.

## 12. Bộ yêu cầu bảo mật có thể nghiệm thu

Các mã sau là mẫu đặc tả cho dự án, chưa phải kết quả nghiệm thu của một sản phẩm.

| ID | Yêu cầu | Bằng chứng |
|---|---|---|
| COR-01 | Mỗi nguồn và event type có hợp đồng ngữ nghĩa, outcome, thời gian và thẩm quyền | Registry schema và mapping nguồn |
| COR-02 | Rule nêu rõ vai trò entity và namespace cần liên kết | Quan hệ field và fixture actor/target/initiator |
| COR-03 | Scope tenant được giữ trong normalization, state, join và quyền đọc | Thử ID trùng và truy cập chéo tenant |
| COR-04 | Khóa, cửa sổ, biên, phạm vi tài nguyên và kết luận được đặc tả theo revision | Rule registry và ca biên |
| COR-05 | Dữ liệu đến muộn, clock không đủ chính xác, replay và watermark có hành vi rõ | Fixture thời gian và lịch sử xử lý |
| COR-06 | Dedup theo định danh nguồn phù hợp, không gộp các event khác nghĩa | Thử giao nhận lặp và xung đột event ID |
| COR-07 | Join nhiều-nhiều, fan-out và giới hạn state không bị xử lý bằng bỏ dữ liệu im lặng | Ca tải fixture và tín hiệu giới hạn |
| COR-08 | Dữ liệu thiếu và rule dựa trên sự vắng mặt không tự tạo kết luận chắc chắn | Ca mất nguồn, sampling và hết hạn state |
| COR-09 | Kết quả giữ reference bằng chứng, chất lượng và mức kết luận đúng hợp đồng | Kiểm tra nội dung alert và khả năng đối soát |
| COR-10 | Giao nhận notification, suppression và cập nhật incident tách khỏi rule matched | Thử lỗi kênh gửi, retry và diễn biến mới |
| COR-11 | Event, state, alert và export điều tra không phát hành secret hoặc PII ngoài mục đích | Canary, schema allowlist và ma trận quyền |
| COR-12 | Backlog, source health, mapping lỗi và state eviction có tín hiệu vận hành | Fault injection và dữ liệu quan sát |
| COR-13 | Thay rule, mapping hoặc schema có policy cho state cũ và đánh giá lại | Thử chuyển revision và replay |
| COR-14 | Kết quả nghiệm thu gắn với build, rule, mapping, nguồn và giới hạn bao phủ | Hồ sơ fixture cùng phần chưa kiểm chứng |

### 12.1. Đặc tả sâu hơn cho quan hệ grant và export

```text
Phạm vi:
  Các event cấp quyền và materialized export thuộc nguồn được liệt kê.

Ngữ nghĩa:
  Grant là thay đổi đã có hiệu lực, export là artifact đã được tạo.

Join:
  Target subject của grant khớp initiator của export trong cùng scope.
  Phạm vi quyền và dữ liệu đáp ứng điều kiện rule.

Thời gian:
  Mốc, cửa sổ, biên và tiêu chí so sánh theo revision đã chốt.

Kết luận:
  Candidate về export gần thay đổi quyền, không tự khẳng định lạm dụng.

Bằng chứng:
  Reference hai nguồn, mapping revision, thời gian và chất lượng.

Khi chưa đủ căn cứ:
  Giữ trạng thái không xác định hoặc chất lượng suy giảm theo hợp đồng.
```

Nếu cần khẳng định chính quyền vừa cấp đã được sử dụng, phải bổ sung loại bằng chứng và rule tương ứng. Không tăng độ mạnh của câu kết luận bằng cách chỉ đổi tiêu đề alert.

## 13. Kiểm thử bằng chuỗi event tổng hợp

### 13.1. Ma trận kiểm thử minh họa

| Ca | Điều kiện kích hoạt | Điều kiện đạt |
|---|---|---|
| TC-COR-01 | Grant target và export initiator đúng scope, trong cửa sổ | Có kết quả đúng rule cùng reference và mức kết luận |
| TC-COR-02 | Actor quản trị trùng initiator nhưng target khác | Không join nhầm vai trò người được cấp quyền |
| TC-COR-03 | Subject ID giống nhưng tenant hoặc namespace khác | Không tạo liên kết ngoài hợp đồng |
| TC-COR-04 | Event đúng, trước, tại và sau các biên cửa sổ | Điều kiện thời gian đúng, không suy thứ tự chặt từ timestamp bằng nhau |
| TC-COR-05 | Export tới trước grant trên mạng nhưng event time phù hợp | Engine xử lý theo policy thứ tự đến, không bỏ mất quan hệ hợp lệ |
| TC-COR-06 | Event tới sau watermark hoặc replay lịch sử | Hành vi cập nhật, backfill và notification đúng hợp đồng |
| TC-COR-07 | Giao lại event, ID trùng khác nguồn hoặc nội dung xung đột | Dedup đúng và có tín hiệu xung đột, không gộp tùy tiện |
| TC-COR-08 | Clock hoặc mapping không đủ căn cứ | Không khẳng định thứ tự hoặc danh tính quá mức bằng chứng |
| TC-COR-09 | Nhiều request cùng IP hoặc user agent | Không tự đồng nhất thành cùng principal |
| TC-COR-10 | Một export có nhiều grant ứng viên | Giữ chính sách nhiều-nhiều và giới hạn fan-out đã chốt |
| TC-COR-11 | Nguồn bị mất, sampling hoặc state cần thiết đã hết hạn | Không dùng thiếu event làm bằng chứng chắc chắn |
| TC-COR-12 | Client giả correlation ID, subject hoặc source | Không nâng dữ liệu tự khai thành nguồn có thẩm quyền |
| TC-COR-13 | Job qua worker dùng chung principal dịch vụ | Giữ initiator, executor và quan hệ ủy quyền đúng nghĩa |
| TC-COR-14 | Canary trong token, request hoặc evidence URL | Không phát hành ở state, alert, metric và export bị cấm |
| TC-COR-15 | Kênh gửi lỗi, suppression và event mới có rủi ro khác | Retry không tạo trùng giả, suppression không che bằng chứng mới cần xử lý |
| TC-COR-16 | Thay rule, mapping revision hoặc restore state | Kết quả giữ provenance, không âm thầm diễn giải lại lịch sử |

### 13.2. Oracle cần nhìn cả liên kết đúng và liên kết sai

Một bộ thử chỉ có chuỗi mong muốn MATCHED sẽ không phát hiện engine đang join mọi event gần nhau. Cần các ca cùng IP nhưng khác người, cùng actor nhưng khác target và cùng subject ID nhưng khác tenant.

Ngược lại, engine bỏ mọi event có thể không tạo liên kết sai nhưng cũng không thực hiện nhiệm vụ phát hiện. Có ca dương tính với nguồn và quan hệ được biết là đúng.

Fixture nên ghi event ID, source, vai trò thực thể, thời điểm, thứ tự giao, schema và mapping revision. Những dữ liệu đó giúp tái hiện kết quả thay vì chỉ có một ảnh chụp alert.

### 13.3. Chứng minh nhánh lỗi và chất lượng đã được kích hoạt

Nếu cache mapping trả kết quả hợp lệ, việc tắt registry chưa chắc đã thử được nhánh thiếu mapping. Nếu event vẫn nằm trong allowed lateness, chưa kiểm chứng hành vi late event ngoài giới hạn.

Xác nhận cấu hình hiệu lực, state, watermark và source health trong từng ca. Những giới hạn chưa quan sát được phải được ghi riêng, không gộp vào PASS.

Không cần dùng tài khoản hoặc secret thật. Dùng subject, tenant, nguồn và quan hệ tổng hợp; canary chống lộ không có khả năng truy cập thật.

## 14. Vận hành và thay đổi rule

### 14.1. Theo dõi khả năng nhìn thấy của engine

Các tín hiệu có thể gồm backlog, độ trễ theo nguồn, số event không map được, xung đột schema, lượng late event, state bị dọn, fan-out bị giới hạn và notification chưa giao.

Một rule không phát cảnh báo có thể do không có mẫu rủi ro, nhưng cũng có thể do nguồn ngừng phát hoặc join key đã đổi. Cần kiểm tra bằng fixture, replay được kiểm soát hoặc tín hiệu đối soát phù hợp.

Không lấy số alert thấp làm bằng chứng hệ thống an toàn hoặc detector hiệu quả. Đánh giá cần có tập ca, chất lượng nhãn và giới hạn phạm vi.

### 14.2. Chuyển revision cần kế hoạch state

Thay khóa join, cửa sổ hoặc mapping có thể làm state cũ không còn cùng ngữ nghĩa. Chốt việc migrate, tách state theo revision, chạy song song hay reset có ghi nhận khoảng trống.

Không dùng lại state cũ mà không kiểm tra tương thích rồi để alert mới mang ý nghĩa khác. Cũng không replay bằng rule mới và sửa kết quả cũ như thể rule đó luôn tồn tại.

Đánh giá lại có thể tạo kết quả lịch sử mới với provenance rõ. Quy tắc giao notification, giữ incident và thời hạn dữ liệu phải đi cùng lựa chọn đó.

### 14.3. False positive cần dẫn tới thay đổi có căn cứ

Nếu nhiều alert là công việc hợp lệ, xem thiếu scope, vai trò, lịch hoặc ngữ cảnh nào. Không chỉ mở rộng allowlist mọi tài khoản quản trị hoặc tăng cửa sổ tùy ý.

Ngoại lệ cần điều kiện, thời hạn và chủ sở hữu. Kết quả điều tra bổ sung ngữ cảnh, nhưng không tự biến mọi hành vi tương lai của cùng subject thành an toàn.

## 15. Truy vết từ rủi ro tới bằng chứng nghiệm thu

Một chuỗi minh họa:

```text
Rủi ro:
  Rule join actor của event cấp quyền với initiator export,
  nên bỏ sót người được cấp và gán nhầm quản trị viên.
    -> COR-01, COR-02, COR-03, COR-09
    -> schema tách actor, target, initiator và executor
    -> normalization có nguồn cùng namespace
    -> TC-COR-01, TC-COR-02, TC-COR-03, TC-COR-13
    -> event logic, mapping và kết quả correlation có reference
    -> kết luận theo build, rule và mapping đã kiểm tra
```

Hồ sơ nghiệm thu cần có danh mục nguồn, schema, mapping, rule revision, thời gian, cấu hình lateness, giới hạn state, fixture và kết quả từng ca.

Một tiêu chí đo được có thể là:

> Trong nguồn và rule đã liệt kê, các ca dương tính tạo đúng liên kết và bằng chứng; các ca sai vai trò hoặc scope không bị join; dữ liệu thiếu và thời gian không đủ căn cứ có trạng thái đúng hợp đồng; dedup, replay, notification và quyền đọc đạt policy. Phần chưa có bằng chứng được ghi riêng, không tính là PASS.

Tiêu chí này xác nhận hành vi của hệ thống trong phạm vi kiểm thử, không chứng minh mọi chuỗi event tương quan đều có cùng nguyên nhân hoặc mọi hành vi rủi ro đều đã được phát hiện.

## 16. Thực hành đặc tả cho nền tảng đa tenant

Một nền tảng có identity service, dịch vụ quản trị quyền và report worker. Các service dùng field `user` khác nghĩa, event đến không theo thứ tự và worker chạy chung một service account. Detector hiện join theo IP trong 10 phút, rồi gửi alert “tài khoản đã lạm dụng quyền mới” nếu thấy thay đổi quyền gần export.

Hãy xây dựng một đặc tả gồm:

1. Ngữ nghĩa của từng event và nguồn có thẩm quyền về trạng thái đó.
2. Schema tách actor, target, initiator, executor cùng tenant và namespace.
3. Mapping định danh tin cậy và cách xử lý alias hoặc liên kết thay đổi theo thời gian.
4. Rule có khóa join, scope, mốc thời gian, biên và mức kết luận phù hợp.
5. Chính sách late event, clock uncertainty, watermark và replay.
6. Dedup theo nguồn cùng event ID, cùng hành vi khi nội dung cốt lõi xung đột.
7. Giới hạn join nhiều-nhiều, state và tín hiệu khi không còn đủ bao phủ.
8. Alert giữ reference điều tra, không mang token hoặc payload dữ liệu nhạy cảm.
9. Ca thử sai vai trò, trùng ID khác tenant, IP dùng chung và nguồn bị mất.
10. Kế hoạch chuyển rule revision, nghiệm thu và ghi rõ giới hạn của kết luận.

Hồ sơ hoàn thành cần cho người khác thấy vì sao các event được nối, nguồn nào xác nhận quan hệ, thời gian và chất lượng nào được chấp nhận, điều gì vẫn chưa biết và người có quyền sẽ kiểm chứng tiếp ở đâu.
