# Feature flag safety

## 1. Feature flag thay đổi hành vi vận hành như thế nào?

Feature flag là cơ chế lựa chọn hành vi ứng dụng bằng cấu hình, thường có thể thay đổi khi hệ thống đang chạy. Một flag có thể quyết định tenant nào dùng thuật toán mới, có chạy bước đánh giá thử hay có nhận thêm lệnh thực hiện hoàn tiền. Trong chương **Deployment Operations**, tính an toàn của flag nằm ở việc thay đổi đó không mở đường bỏ qua quy tắc nghiệp vụ, không làm các instance thực hiện hai hợp đồng khác nhau cho cùng một thao tác và không khiến retry tạo tác động trùng.

Ví dụ xuyên suốt là dịch vụ hoàn tiền có các bất biến:

- Actor chỉ được thao tác trên đối tượng và tenant được policy cho phép.
- Người tạo yêu cầu không được tự phê duyệt yêu cầu của mình.
- Chỉ yêu cầu đã được phê duyệt với đúng nội dung mới được đưa đi thực hiện.
- Tổng số tiền đã hoàn và đang giữ chỗ không vượt số tiền được phép hoàn.
- Lệnh gửi lại, worker chạy lại và callback trùng không tạo khoản hoàn thứ hai.

Hai engine `V1` và `V2` có thể khác cách tối ưu xử lý nhưng đều phải giữ các bất biến này. Flag được bật không có nghĩa người gọi có quyền; flag bị tắt cũng không phải lý do tự bỏ qua kiểm tra dữ liệu hoặc xóa một bước bắt buộc.

Một điều kiện thực hiện nên được hiểu là:

```text
được thực hiện lệnh mới
    = được phân quyền trên đối tượng
      AND trạng thái và nội dung phê duyệt hợp lệ
      AND bất biến tiền và idempotency được bảo vệ
      AND cổng vận hành cho phép nhận thêm lệnh
      AND engine được chọn tương thích với dữ liệu hiện tại
```

Đây là mô hình của bài, không phải biểu thức có sẵn của một SDK. Các ví dụ dùng Java 17 và mã giả cho hợp đồng ứng dụng; không phụ thuộc một phiên bản thư viện feature flag cụ thể.

## 2. Phân loại flag theo điều nó được phép thay đổi

| Loại | Ví dụ trong bài | Phạm vi được thay đổi | Điều không được suy ra |
|---|---|---|---|
| Release/rollout | Chọn engine `V1` hoặc `V2` cho tenant | Lựa chọn triển khai đã được kiểm tra | Engine được phép bỏ guard hoặc thay quyền |
| Shadow | Chạy policy mới để so sánh trên snapshot | Tính toán thử và thu số liệu | Được ghi trạng thái, giữ chỗ hoặc gửi tiền lần nữa |
| Operational gate/kill switch | Cho nhận thêm lần thực hiện hoàn tiền | Tạm dừng công việc mới tại ranh giới đã định nghĩa | Mọi request và tác động ngoài đã dừng ngay lập tức |
| Entitlement | Cho một tenant thấy tính năng theo hợp đồng | Một đầu vào của policy truy cập tính năng | Có quyền trên mọi đối tượng của tính năng đó |
| Tham số policy động | Hạn mức theo cấu hình đã kiểm soát | Thay đổi chính sách có phiên bản, kiểm tra miền giá trị và quyền sửa | Chỉ là một thử nghiệm giao diện không cần kiểm soát |

Các sản phẩm có thể dùng tên khác nhau cho cùng khái niệm. Điểm quan trọng là xác định hậu quả nghiệp vụ, thay vì áp dụng một giá trị mặc định cho tất cả flag.

Một entitlement flag có thể tham gia quyết định cấp quyền theo thiết kế, nhưng không thay thế kiểm tra quyền trên đối tượng, tenant hoặc trạng thái. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) nhấn mạnh quyền tối thiểu, từ chối mặc định và kiểm tra quyền tại mỗi request ở vị trí thích hợp.

### 2.1. Các flag nguy hiểm ngay từ cách đặt câu hỏi

Các tên như `skip-refund-approval`, `disable-tenant-check` hoặc `ignore-idempotency` thường biểu thị một khả năng bỏ kiểm soát nghiệp vụ. Nếu dùng chúng để chữa lỗi production, một thay đổi cấu hình có thể trở thành đường vượt quy trình.

Một hợp đồng phù hợp hơn là “engine nào thực hiện cùng một nghiệp vụ an toàn?” hoặc “có nhận thêm lệnh mới không?”. Trong code, đặt các guard bắt buộc ở ranh giới dùng chung hoặc yêu cầu từng nhánh thực thi cùng hợp đồng và được kiểm thử tương đương. Không để một nhánh cũ thiếu kiểm tra tồn tại như phương án fallback được coi là an toàn.

## 3. Xác định ranh giới tin cậy của dữ liệu flag

### 3.1. Quyết định nhạy cảm ở phía máy chủ

Trình duyệt có thể nhận flag để hiển thị nút hoặc trải nghiệm tương ứng. Người dùng vẫn có thể sửa JavaScript, sửa local storage hoặc gọi API trực tiếp. Máy chủ phải tự đánh giá điều kiện vận hành và kiểm tra quyền khi nhận lệnh; không chấp nhận một body như sau làm bằng chứng:

```json
{
  "refundId": "refund-123",
  "useNewEngine": true,
  "approvalRequired": false,
  "tenantId": "tenant-with-special-rollout"
}
```

Flag gửi xuống client không phải bí mật. Không đưa server token, thông tin kết nối, khóa ký hay dữ liệu nhạy cảm vào payload flag. Nếu có lựa chọn trải nghiệm do người dùng cung cấp, chỉ coi đó là một đề nghị trong danh sách cho phép; policy máy chủ vẫn quyết định phần có tác động nghiệp vụ.

### 3.2. Context đánh giá phải có nguồn đáng tin

Context có thể chứa targeting key, tenant, nhóm rollout, khu vực hoặc loại tài khoản. Các trường liên quan tới quyền phải được dựng từ dữ liệu máy chủ đã xác thực, không sao chép nguyên header hoặc JSON của người dùng.

Ví dụ, nếu rollout theo tenant, lấy tenant đã được xác minh từ danh tính và quan hệ thành viên. Không lấy `X-Tenant-Id` chưa kiểm tra rồi cho client tự chọn cohort. Tương tự, trường `isStaff` hoặc `plan=enterprise` do client gửi không được trở thành điều kiện vào nhánh đặc quyền.

[OpenFeature Evaluation Context](https://openfeature.dev/specification/sections/evaluation-context/) định nghĩa targeting key và các cấp context có thứ tự ghi đè, trong đó invocation và before hook có thể ghi đè giá trị ở cấp thấp hơn. SDK gộp context theo quy tắc không có nghĩa dữ liệu sau khi gộp đã được xác thực. Cần kiểm soát các hook và adapter có quyền sửa trường nhạy cảm.

Không thay context global bằng tenant của từng request trên một singleton dùng chung. Khi hai request đồng thời chạy, cách đó có thể làm tenant A được đánh giá bằng context của tenant B. Dùng context theo invocation hoặc cơ chế truyền context đúng vòng đời mà SDK đang dùng hỗ trợ; kiểm tra cả job nền và xử lý bất đồng bộ.

### 3.3. Giữ cohort ổn định ở đúng cấp nghiệp vụ

Nếu quyết định rollout cần nhất quán cho cả quy trình của một tenant, lựa chọn theo mỗi request ngẫu nhiên có thể khiến bước tạo chạy `V1`, bước duyệt chạy `V2` và retry lại sang `V1`. Chọn targeting key ổn định theo phạm vi mong muốn và lưu engine của một lần thực hiện khi đã nhận lệnh có tác động.

Stickiness của hệ thống flag không thay thế việc lưu quyết định nghiệp vụ: rule, trọng số hoặc key có thể đổi. Một workflow dài có thể cần `workflowVersion` hoặc `executionEngine` riêng. Chỉ gửi context tối thiểu cần thiết; không gửi email, dữ liệu thanh toán hoặc toàn bộ principal nếu rollout chỉ cần một định danh tenant giả danh ổn định.

## 4. Giá trị mặc định, lỗi đánh giá và cache cũ

### 4.1. Mặc định an toàn phụ thuộc thao tác

| Trường hợp | Ví dụ cách xử lý trong thiết kế này |
|---|---|
| Thiếu flag rollout engine mới | Dùng `V1` nếu `V1` vẫn đáp ứng đầy đủ bất biến và tương thích dữ liệu; nếu không có nhánh an toàn thì dừng lệnh mới |
| Thiếu cấu hình cho phép thực hiện hoàn tiền | Không nhận thêm lần thực hiện mới; vẫn cho đọc trạng thái theo quyền |
| Thiếu flag shadow | Không chạy shadow; đường xử lý chính tiếp tục theo policy của nó |
| Giá trị engine không nằm trong danh mục | Không tự đoán engine; dừng lệnh mới và phát tín hiệu cấu hình lỗi |
| Provider chưa sẵn sàng hoặc cache quá cũ | Áp dụng chính sách riêng cho thao tác; không dùng một boolean thành công làm bằng chứng cấu hình còn mới |
| Flag chứa hạn mức sai kiểu, âm hoặc vượt trần | Từ chối cấu hình đó; không ép kiểu hoặc mặc định thành “không giới hạn” |

Fail closed trong bài nghĩa là dừng **lệnh mới có tác động nhạy cảm khi không có quyết định vận hành đủ tin cậy**, không phải đóng mọi endpoint và bỏ mặc tác động đã bắt đầu. Một API đọc trạng thái hoặc luồng đối soát có thể cần tiếp tục hoạt động để phục hồi đúng.

### 4.2. Boolean trả về không cho biết nguồn kết quả

Với một SDK, `false` có thể là kết quả rule, giá trị mặc định do flag không tồn tại hoặc giá trị fallback khi provider lỗi. Tương tự, `true` có thể đến từ cache chưa được cập nhật. Chỉ ghi `flag=true/false` là chưa đủ để điều tra.

[OpenFeature Flag Evaluation API](https://openfeature.dev/specification/sections/flag-evaluation/) quy định API đánh giá trả giá trị mặc định khi gặp thực thi bất thường; detailed evaluation cung cấp thêm thông tin như reason và error code. Do đó, `try/catch` quanh một lời gọi chỉ trả boolean không đủ để phát hiện tất cả lỗi đánh giá. Khi dùng OpenFeature, đọc evaluation details theo khả năng của SDK/provider và ánh xạ rõ sang quyết định vận hành.

Metadata không đồng nhất giữa mọi provider. Một provider có thể cho reason hoặc thông tin trạng thái, nhưng không cung cấp revision cấu hình hay bằng chứng độ mới của từng flag. [OpenFeature Provider](https://openfeature.dev/specification/sections/providers/) mô tả resolution details và các lý do như cached hoặc stale; chúng cần được hiểu theo hợp đồng của provider, không được tự coi là một giao thức nhất quán mạnh.

### 4.3. Độ mới phải được đo từ lần xác nhận cấu hình

Thời điểm ứng dụng đánh giá flag không phải thời điểm dữ liệu flag được làm mới. Nếu mỗi lần đọc cache đều cập nhật `lastUpdated=now`, một cấu hình đã mất kết nối hàng giờ vẫn trông như vừa được xác nhận.

Cần phân biệt ít nhất:

```text
evaluatedAt  = lúc ứng dụng tính kết quả cho lệnh hiện tại
verifiedAt   = lúc nguồn tin cậy xác nhận snapshot cấu hình còn hợp lệ
revision     = phiên bản/định danh cấu hình nếu nguồn thực sự cung cấp
```

Đặt giới hạn tuổi cấu hình theo rủi ro, độ trễ truyền và khả năng phục hồi đã đo. Nếu provider không cung cấp dữ liệu đủ để xác nhận yêu cầu đó, phải bổ sung adapter/giao thức phù hợp hoặc chọn cơ chế khác cho cổng thực hiện quan trọng. Không tự tạo một revision có vẻ chính xác từ timestamp của request.

## 5. Chốt một snapshot nhất quán cho một quyết định

Nếu một handler đọc cùng flag ở nhiều nơi, cấu hình có thể đổi giữa bước kiểm tra, tính tiền và ghi dữ liệu. Quyết định nên được chuẩn hóa tại một ranh giới rõ ràng và truyền xuống dưới dưới dạng bất biến.

Việc đọc ba flag lần lượt vào một record không tự tạo snapshot nguyên tử. Nếu ba giá trị cần cùng một revision, dùng một tài liệu cấu hình có phiên bản được nạp nguyên khối hoặc một khả năng snapshot được provider bảo đảm. Với các flag độc lập, phải định nghĩa và kiểm thử mọi tổ hợp hợp lệ; dependency hiển thị trên dashboard chưa chứng minh code đọc được tất cả giá trị cùng lúc.

### 5.1. Ví dụ Java cho cổng nhận lần thực hiện mới

Đoạn mã sau là policy của ứng dụng, không phải API OpenFeature. Adapter phải tạo `VerifiedSnapshot` từ **một tài liệu đã được xác thực, kiểm tra schema và nạp nhất quán**. Trường `verifiedAt` chỉ được cập nhật khi có xác nhận phù hợp từ nguồn cấu hình, không phải mỗi lần đọc cache. Không dựng đối tượng này từ body của người dùng.

```java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class RefundExecutionGate {

    public enum Engine { V1, V2 }

    public record VerifiedSnapshot(
            boolean allowNewExecutions,
            Engine engine,
            String revision,
            Instant verifiedAt) {
        public VerifiedSnapshot {
            Objects.requireNonNull(engine);
            Objects.requireNonNull(revision);
            Objects.requireNonNull(verifiedAt);
            if (revision.isBlank()) {
                throw new IllegalArgumentException("MISSING_REVISION");
            }
        }
    }

    public record ExecutionPlan(Engine engine, String flagRevision) {}

    public static final class ExecutionPaused extends RuntimeException {
        public ExecutionPaused(String reason) {
            super(reason);
        }
    }

    private final Duration maxAge;

    public RefundExecutionGate(Duration maxAge) {
        Objects.requireNonNull(maxAge);
        if (maxAge.isNegative() || maxAge.isZero()) {
            throw new IllegalArgumentException("INVALID_MAX_AGE");
        }
        this.maxAge = maxAge;
    }

    public ExecutionPlan chooseForNewExecution(
            VerifiedSnapshot snapshot, Instant now) {
        Objects.requireNonNull(now);
        if (snapshot == null) {
            throw new ExecutionPaused("FLAGS_UNAVAILABLE");
        }
        if (now.isBefore(snapshot.verifiedAt())) {
            throw new ExecutionPaused("CLOCK_OR_METADATA_INVALID");
        }
        Duration age = Duration.between(snapshot.verifiedAt(), now);
        if (age.compareTo(maxAge) > 0) {
            throw new ExecutionPaused("FLAGS_TOO_OLD");
        }
        if (!snapshot.allowNewExecutions()) {
            throw new ExecutionPaused("NEW_EXECUTIONS_DISABLED");
        }
        return new ExecutionPlan(snapshot.engine(), snapshot.revision());
    }
}
```

`maxAge` là tham số vận hành đã được quyết định và kiểm thử, không có con số an toàn chung cho mọi dịch vụ. Adapter cần ánh xạ sai kiểu, engine không nhận diện được, revision thiếu hoặc nguồn không đáng tin thành trạng thái không sử dụng được; không tự đổi chuỗi lạ thành `V1` để lệnh tiếp tục.

Ví dụ dùng `Instant` để diễn đạt thời gian. Triển khai thực tế cần kiểm soát clock skew và cách đo tuổi dữ liệu; phép đo thời gian trôi qua trong một tiến trình có thể dùng nguồn thời gian đơn điệu phù hợp. Record và tên `VerifiedSnapshot` không tự bảo đảm tính xác thực, độ mới hay nguồn gốc của dữ liệu.

Được trả về `ExecutionPlan` chỉ có nghĩa cổng cục bộ cho phép chọn engine tại thời điểm đánh giá. Nó chưa chứng minh actor có quyền, refund đã được duyệt, hạn mức còn đủ hoặc cấu hình sẽ không đổi trước khi commit. Các kiểm tra đó vẫn cần thực hiện ở ranh giới nghiệp vụ.

## 6. Giữ transaction và idempotency đúng khi flag thay đổi

Một luồng **mã giả** để nhận một lần thực hiện mới có thể là:

```text
authenticate caller and derive trusted actor/tenant

begin transaction
    load scoped refund and required shared resources with concurrency control
    check object access and access to any stored command result
    inspect or claim idempotency record atomically

    if this command already committed:
        return its stored result under current access policy

    read one usable flag snapshot and choose execution plan
    check authoritative admission gate if strong cutoff is required
    check approval, approved content revision, current state and version
    check money reservation and all mandatory business invariants
    check chosen engine can process this workflow/schema version

    persist executionEngine, executionId and decision metadata
    move refund to PROCESSING using conditional update
    write ExecuteRefund intent to outbox
    store idempotent result
commit
```

Thứ tự lấy khóa trong triển khai phải thống nhất giữa mọi đường ghi. Pseudocode tập trung vào các trách nhiệm cần có, không chỉ định một transaction API hoặc cơ sở dữ liệu cụ thể. Tránh gọi chậm ra dịch vụ flag từ bên trong transaction đang giữ khóa; có thể chuẩn bị snapshot cục bộ rồi kiểm tra tuổi và cổng có thẩm quyền tại điểm nhận lệnh.

Các nguyên tắc quan trọng gồm:

- **Quyết định đã nhận lệnh cần được lưu.** Retry của cùng một lần thực hiện phải dùng engine và định danh ngoài đã chốt; không đánh giá rollout mới rồi tự chạy lại bằng engine khác.
- **Idempotency có phạm vi rõ ràng.** Key cần gắn với tenant, tài nguyên và loại lệnh theo hợp đồng; cùng key nhưng payload có ý nghĩa khác phải bị từ chối. Không dùng một flag để bỏ ràng buộc duy nhất hoặc dấu vết chống trùng.
- **Replay kết quả khác nhận lệnh mới.** Khi cổng đang đóng, có thể trả kết quả của lệnh đã commit nếu người gọi còn quyền; việc đó không tạo một lần thực hiện mới.
- **Outbox không cho hiệu quả đúng một lần ở mọi hệ thống.** Nó lưu ý định cùng transaction, còn worker và nhà cung cấp vẫn cần idempotency và xử lý trùng. Xem [AWS Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html).
- **Tiền đã gửi không tự quay về khi tắt flag.** Timeout cần đối soát; không đặt ngay `FAILED` rồi giải phóng giữ chỗ chỉ vì đã đổi cấu hình.

Ví dụ, request đầu chọn `V2`, commit `executionId=E1` nhưng mất response. Sau đó rollout quay về `V1`. Request retry với cùng key phải được nhận diện là E1; worker xử lý hoặc đối soát E1 theo hợp đồng đã lưu, không tạo E2 dưới engine mới.

Nếu API ngoài dùng idempotency key, phải giữ key ổn định cho cùng một lần thực hiện và hiểu thời hạn/phạm vi của nhà cung cấp. [Stripe Idempotent requests](https://docs.stripe.com/api/idempotent_requests) là một ví dụ hợp đồng cụ thể; không suy ra mọi API đều có cùng cách lưu và trả lại kết quả.

## 7. Kill switch có giới hạn nhất quán và thời gian truyền

### 7.1. “Tắt” phải có nghĩa cụ thể

Đối với hoàn tiền, cần phân biệt:

| Phạm vi dừng | Ý nghĩa | Việc vẫn cần được xử lý |
|---|---|---|
| Dừng nhận lệnh mới | Không tạo thêm lần thực hiện sau ranh giới nhận lệnh đã định | Trả kết quả cũ, theo dõi tác động đã bắt đầu |
| Dừng gửi ý định chưa thực hiện | Worker không bắt đầu gửi thêm tác động ngoài thuộc phạm vi dừng | Phân loại công việc đã gửi, chưa gửi hoặc chưa biết |
| Dừng toàn bộ xử lý | Chặn thêm cả các bước đã định nghĩa rõ | Cần đánh giá hậu quả đối với callback, giải phóng giữ chỗ và đối soát |

Một boolean dùng chung để chặn cả gửi tiền lẫn xử lý callback có thể làm tiền đã hoàn nhưng sổ nội bộ không bao giờ được cập nhật. Trong thiết kế này, cổng đóng chặn lần thực hiện mới; luồng xác minh callback, đọc trạng thái và đối soát vẫn chạy theo quyền và hợp đồng riêng. Nếu sự cố nằm chính ở các luồng đó, cần biện pháp cô lập riêng kèm kế hoạch khôi phục.

### 7.2. Cache cục bộ không tạo mốc dừng đồng thời trên mọi instance

Một instance có thể đã nhận revision tắt, instance khác còn dùng revision bật trong cache. Đánh giá một lần cho mỗi lệnh giúp nhất quán cục bộ, nhưng không tạo bảo đảm “không có lệnh mới sau thời điểm người vận hành bấm nút”.

[Unleash Feature flag best practices](https://docs.getunleash.io/guides/feature-flag-best-practices) mô tả cách dùng cache/đánh giá cục bộ để duy trì khả dụng khi hệ thống flag gặp sự cố. Đối với nghiệp vụ cần mốc dừng chặt, phải bổ sung giao thức nhận lệnh phù hợp; không coi tính khả dụng của cache là bằng chứng mọi instance đã nhận cấu hình mới nhất.

Nếu nghiệp vụ chấp nhận độ trễ truyền, cần đặt và đo giới hạn: thời gian cập nhật, tuổi cache, số instance chưa xác nhận revision, số ý định mới sau yêu cầu dừng và lượng công việc đang chạy. Trường hợp mất mạng phải được tính vào chính sách, không chỉ đo trong môi trường kết nối tốt.

### 7.3. Ví dụ cổng nhận lệnh có thẩm quyền trong cơ sở dữ liệu

Khi cần ranh giới mạnh hơn, có thể dùng một dòng `business_execution_gate` trong cùng cơ sở dữ liệu với transaction nhận lệnh. Ví dụ SQL theo PostgreSQL 18, với tham số được driver bind:

```sql
-- Trong mọi transaction nhận lần thực hiện mới:
SELECT enabled, epoch
FROM business_execution_gate
WHERE scope = :scope
FOR SHARE;

-- Chỉ khi enabled = true mới ghi execution/outbox trong cùng transaction.
-- Giữ khóa cho đến khi transaction đó commit hoặc rollback.
```

Thao tác đóng cổng ở transaction quản trị có quyền riêng:

```sql
UPDATE business_execution_gate
SET enabled = false,
    epoch = epoch + 1
WHERE scope = :scope;
```

Theo giao thức này, thao tác đóng chờ các transaction đang giữ khóa chia sẻ trên dòng gate hoàn tất; transaction nhận lệnh sau khi đóng đã commit sẽ thấy gate tắt. Tính chất đó chỉ áp dụng khi mọi đường nhận lệnh đọc đúng dòng từ nguồn có thẩm quyền, kiểm tra `enabled`, giữ khóa và ghi ý định trong cùng transaction. Không đọc gate từ read replica có thể trễ, không bỏ qua khi dòng bị thiếu và không cho đường khác ghi ý định không qua gate. Cơ chế khóa tương ứng được mô tả trong [PostgreSQL Explicit Locking](https://www.postgresql.org/docs/18/explicit-locking.html).

Đặt thứ tự khóa gate và các tài nguyên nghiệp vụ nhất quán, giữ transaction ngắn và không giữ khóa qua lời gọi mạng. Nếu phạm vi có cả gate toàn hệ thống và gate tenant, định nghĩa thứ tự cố định và cách phối hợp rõ ràng. Một dòng gate chung còn có chi phí tranh chấp cần đo trước khi chọn thiết kế.

Mốc được bảo vệ ở ví dụ là **commit nhận ý định mới**, không phải thời điểm nhà cung cấp thực hiện tiền. Ý định đã commit trước lúc đóng vẫn có thể đang ở hàng đợi hoặc đã gửi mạng. Cần kiểm kê và xử lý chúng theo phạm vi dừng đã định nghĩa. Trường `epoch` chỉ giúp ghi dấu phiên bản cổng; nó không tự chặn một lời gọi HTTP bên ngoài nếu bên nhận không thực thi giao thức fencing tương ứng.

Việc đổi flag trên dashboard và commit gate trong cơ sở dữ liệu cũng không tự nguyên tử. Runbook phải chỉ rõ cơ chế nào tạo mốc dừng có thẩm quyền và xác nhận nó đã commit; không suy ra từ trạng thái hiển thị trên dashboard.

## 8. Rollout và rollback phải tương thích với dữ liệu đã tồn tại

### 8.1. Mở dần theo bằng chứng nghiệp vụ

Một kế hoạch minh họa cho engine hoàn tiền mới:

| Giai đoạn | Điều thực hiện | Bằng chứng trước khi mở rộng |
|---|---|---|
| Chuẩn bị | Deploy code hiểu schema/phiên bản workflow cần thiết; vẫn chọn engine an toàn hiện tại | Các nhánh đều giữ quyền, state machine, bất biến và idempotency |
| Shadow | So sánh phần quyết định thuần của `V2` trên dữ liệu được phép đọc | Chênh lệch được giải thích; không tạo tác động nghiệp vụ thứ hai |
| Canary | Chọn một tập tenant có kiểm soát và đủ khả năng quan sát | Quyết định flag đúng cohort, không lệch tiền hoặc lặp execution |
| Mở rộng | Tăng phạm vi theo giai đoạn | Chỉ số nghiệp vụ, lỗi, cache và công việc tồn đọng trong giới hạn đã đặt |
| Hoàn tất | Dùng nhánh mục tiêu, xác nhận không còn công việc cần nhánh cũ | Có kế hoạch dọn flag/code, vẫn giữ cổng vận hành cần thiết |

Phần trăm tenant không bằng phần trăm lưu lượng hoặc số tiền. Một tenant lớn có thể mang phần lớn rủi ro tài chính; cohort cần phản ánh quy mô và đặc điểm nghiệp vụ, không chỉ một con số trên dashboard.

Các điều kiện dừng không nên chỉ là tỷ lệ HTTP 5xx. Phải quan sát số tiền đã hoàn cộng giữ chỗ, số execution cho cùng nghiệp vụ, kết quả quyền theo đối tượng, thời gian đối soát và các transition không hợp lệ. Chênh lệch bảo mật hoặc tiền không nên bị che trong một mức trung bình toàn hệ thống.

### 8.2. Tắt flag không đảo migration hoặc lịch sử

Giả sử `V2` tạo một trạng thái mà `V1` không hiểu hoặc lưu số tiền theo một hợp đồng khác. Chuyển rollout về `V1` không làm dữ liệu trở về định dạng cũ. Một instance cũ đọc trạng thái lạ không được mặc định thành “chưa duyệt” rồi thực hiện lại.

Để rollback có ý nghĩa, cần trả lời:

- Phiên bản cũ có đọc được dữ liệu và message do phiên bản mới tạo không?
- Các workflow đang chạy đã chốt engine hoặc policy nào? Có thể tiếp tục an toàn hay phải tạm dừng và chuyển qua adapter phục hồi?
- Một lần thực hiện đã gửi ra ngoài có giữ nguyên execution ID và idempotency key khi rollback không?
- Công việc trong outbox, hàng đợi và callback đến muộn sẽ do phiên bản nào xử lý?
- Dữ liệu backfill hoặc schema đã đổi có tương thích với cả hai nhánh trong thời gian chuyển tiếp không?

Một cách tổ chức là mở rộng schema theo hướng tương thích trước, triển khai người đọc hiểu cả hai hợp đồng, chuyển dần người ghi rồi mới loại bỏ phần cũ khi không còn phụ thuộc. Đây là chiến lược cần điều chỉnh cho mô hình dữ liệu thực tế; không mặc định việc giữ hai nhánh trong code đã giải quyết tương thích.

Nếu `V1` đang có lỗ hổng đã biết, “tắt `V2`” để quay lại `V1` không phải phương án an toàn. Có thể phải đóng nhận lệnh mới, vá bản an toàn hoặc triển khai một đường phục hồi riêng. Luôn mô tả rollback bằng hành vi và dữ liệu có thể xử lý, không chỉ bằng giá trị flag.

## 9. Shadow và thử nghiệm policy không được tạo đường vượt quyền

Shadow là chạy một phần xử lý mới để quan sát kết quả mà chưa dùng nó làm quyết định chính. Với nghiệp vụ nhạy cảm, chỉ shadow phần có thể đánh giá thuần trên snapshot được phép sử dụng.

Ví dụ **mã giả**:

```text
primaryDecision = approvedPolicy.evaluate(trustedSnapshot)

if shadowEnabled:
    candidateDecision = candidatePolicy.evaluateReadOnly(trustedSnapshot)
    record bounded comparison metadata

enforce primaryDecision
```

Đừng gọi cả `v1.executeRefund()` và `v2.executeRefund()` rồi bỏ response của một bên. Cả hai vẫn có thể gửi tiền, tạo lịch sử, giữ chỗ hoặc tiêu thụ idempotency key. Cũng không dùng một transaction rollback để giả lập shadow nếu code đã gọi hệ thống ngoài; rollback cơ sở dữ liệu không thu hồi tác động mạng.

Snapshot shadow phải được lấy sau các kiểm tra truy cập cần thiết và giới hạn vào dữ liệu được phép sử dụng. Không vì “chỉ chạy thử” mà cho candidate policy truy vấn đối tượng khác tenant hoặc xuất dữ liệu nhạy cảm sang hệ thống phân tích.

Nếu candidate từ chối còn primary cho phép, hoặc ngược lại, ghi loại chênh lệch và điều kiện đủ để điều tra. Không tự chọn quyết định dễ dãi hơn để tối ưu tỷ lệ chuyển đổi. Nếu triển khai chính sách mới siết quyền, cần một quyết định phát hành có kiểm soát về ảnh hưởng và quy trình xử lý; shadow tự nó không phải phê duyệt thay đổi policy.

Giới hạn CPU, thời gian, lượng log và số truy vấn của shadow. Sự cố của một nhánh quan sát không nên âm thầm biến thành lỗi nghiệp vụ chính hoặc làm hệ thống cạn tài nguyên. Nếu yêu cầu audit bắt buộc, điều kiện đó phải được nêu thành hợp đồng riêng thay vì phụ thuộc vào lỗi ngẫu nhiên của shadow.

## 10. Bảo vệ quyền thay đổi flag và cấu hình production

Một người có quyền đổi flag có thể tác động tới phạm vi rollout, hạn mức hoặc khả năng nhận lệnh của nhiều tenant. Vì vậy, cần coi control plane của flag là một ranh giới quản trị quan trọng.

| Bề mặt | Kiểm soát cần thiết theo rủi ro |
|---|---|
| Tài khoản quản trị | SSO/MFA phù hợp, quyền tối thiểu, thu hồi theo vòng đời nhân sự |
| Phạm vi quyền | Tách môi trường, project, đọc cấu hình, sửa targeting và mở rộng production |
| Token SDK | Chỉ quyền đọc cần thiết, đúng môi trường; không dùng token quản trị trong ứng dụng |
| Thay đổi nhạy cảm | Có bản diff cụ thể, người chịu trách nhiệm, kiểm tra tác động và mức phê duyệt phù hợp |
| API thay đổi flag | Xác thực, phân quyền, audit; không lộ override endpoint qua header hay query production |
| Nguồn cấu hình | Xác thực nguồn và bảo vệ truyền/lưu theo kiến trúc; kiểm tra schema, kiểu và miền giá trị |

Tách secret và cấu hình kết nối khỏi flag. Tài liệu [Unleash Feature flag management](https://docs.getunleash.io/guides/best-practices-using-feature-flags-at-scale) bàn về phân quyền thay đổi, audit và việc tránh dùng feature flags làm kho cấu hình nhạy cảm. Những khả năng như workflow phê duyệt, lịch sử hoặc phạm vi token phụ thuộc sản phẩm và gói triển khai; phải xác nhận khả năng thực tế thay vì suy đoán.

Đối với thay đổi hạn mức hoặc quyền động, bản đề xuất phải nêu giá trị cũ/mới, phạm vi tenant, thời điểm hiệu lực, hành vi với lệnh đang chạy và cách khôi phục. Không chỉ phê duyệt “bật flag” khi tên flag che khuất một thay đổi policy.

Break-glass khi có sự cố cũng cần quyền hẹp, thời hạn rõ và dấu vết. Biện pháp khẩn cấp phù hợp có thể là đóng cổng nhận lệnh; không cung cấp một cờ cho phép bỏ tenant check, state machine hoặc audit để “giải quyết nhanh”.

Mỗi flag nên có hồ sơ ngắn: mục đích, owner, môi trường, kiểu giá trị, default/fallback, nguồn context, phụ thuộc, mức rủi ro, cách đo truyền cấu hình, kế hoạch rollback và tiêu chí gỡ bỏ. Với kill switch dài hạn, thay ngày hết hạn bằng lịch kiểm tra chủ động để tránh xóa mất một kiểm soát vẫn còn cần.

## 11. Kiểm thử feature flag theo tình huống lạm dụng và sự cố

### 11.1. Kiểm thử cả quyết định flag lẫn tác động nghiệp vụ

Unit test adapter/gate giúp chứng minh fallback và kiểm tra kiểu đúng; test tích hợp phải chứng minh quyền, transaction, version và idempotency vẫn được thực thi qua từng nhánh. Một test mock SDK trả `true` rồi chỉ kiểm tra handler chạy không đủ để chứng minh an toàn.

| Tình huống | Điều phải chứng minh |
|---|---|
| Flag bật nhưng actor không có quyền | Không thực hiện nghiệp vụ, không ghi ý định gửi tiền |
| Flag bật cho tenant A, request truy cập tài nguyên tenant B | Quyền theo đối tượng vẫn chặn; context rollout không cấp quyền chéo tenant |
| Client sửa header, cookie, local storage hoặc body flag | Máy chủ dùng context tin cậy và không bỏ guard |
| Flag off/on ở mọi nhánh engine | Không tự duyệt, bỏ bước, vượt tiền hoặc bỏ idempotency |
| Flag không tồn tại hoặc bị sai tên | Default đúng mục đích; có tín hiệu cấu hình thiếu, không âm thầm mở thao tác nhạy cảm |
| Provider chưa khởi tạo hoặc chưa được gắn | Không coi giá trị code default là một xác nhận từ nguồn cấu hình |
| Provider lỗi, cache stale, metadata không đủ | Hành vi đúng hợp đồng của từng loại thao tác; không tự làm mới tuổi cache |
| Giá trị boolean/string/object sai kiểu hoặc schema lạ | Không ép thành giá trị cho phép; không tạo kế hoạch thực hiện từ cấu hình không hợp lệ |
| Hai request đồng thời của hai tenant | Không rò context qua global/singleton hoặc thread-local được dọn sai |
| Flag đổi giữa các bước trong cùng lệnh | Quyết định dùng một snapshot theo hợp đồng, không trộn engine và policy |
| Hai instance nhận revision khác nhau | Bất biến vẫn đúng; mốc dừng mạnh chỉ dựa vào cơ chế có thẩm quyền đã thiết kế |
| Kill switch đóng khi đã có outbox chưa gửi | Phân loại và xử lý theo phạm vi dừng; không mặc định tất cả đều chưa thực hiện |
| Kill switch đóng sau khi đã gửi mạng | Callback/đối soát cập nhật được kết quả; không giải phóng tiền chỉ do timeout |
| Retry sau khi rollout đổi từ `V2` sang `V1` | Cùng lệnh giữ execution ID, engine đã chốt và không gửi tiền lần hai |
| Shadow bật | Không tạo giữ chỗ, transition, execution hoặc lời gọi tiền thứ hai |
| Rollback code trong khi còn workflow/schema mới | Phiên bản cũ xử lý theo hợp đồng tương thích hoặc dừng an toàn, không reset trạng thái |
| Flag được xóa nhưng còn instance hoặc job cũ | Missing flag không bật lại đường xử lý sai qua default |
| Token hoặc môi trường flag cấu hình nhầm | Không lấy rule staging làm quyết định production; có tín hiệu lỗi rõ ràng |

Ngoài các ca riêng lẻ, cần kiểm tra tổ hợp hợp lệ của rollout, shadow, gate và phiên bản workflow. Với nhiều flag, số tổ hợp tăng nhanh; giảm số flag phụ thuộc, chuẩn hóa tài liệu cấu hình và dùng kiểm thử theo bất biến. Pairwise có thể hỗ trợ tìm tương tác thông thường nhưng không thay thế các tổ hợp quan trọng đã xác định trong threat model.

### 11.2. Kiểm thử mốc dừng bằng lịch thực thi rõ ràng

Đối với gate trong cơ sở dữ liệu ở mục 7, một kịch bản tích hợp có thể là:

```text
T1: transaction nhận lệnh lấy FOR SHARE trên gate đang bật
T2: yêu cầu đóng gate, phải chờ T1 kết thúc
T1: commit ý định E1 và nhả khóa
T2: ghi gate tắt, tăng epoch và commit
T3: transaction nhận lệnh mới đọc gate đã tắt, không tạo E2

Kiểm tra riêng: E1 có thể còn cần gửi hoặc đối soát theo phạm vi dừng.
```

Chạy bằng các connection/transaction riêng với barrier hoặc latch để kiểm soát điểm cạnh tranh. Không dùng hai lời gọi tuần tự làm bằng chứng cho lịch đồng thời. Có thêm ca transaction rollback, deadlock/timeout và thiếu dòng gate; lỗi hạ tầng không được trở thành đường bỏ qua cổng.

Với thời gian cache, dùng clock có thể điều khiển trong test để kiểm tra ngay trước, đúng và sau giới hạn tuổi, cùng trường hợp thời gian xác nhận ở tương lai. Với pipeline nền, chờ điều kiện có timeout và kiểm tra dữ liệu bền vững; không coi việc ngủ một khoảng cố định là xác nhận đã hội tụ.

Kiểm thử tác động bằng state/version, tổng tiền, số bản ghi idempotency/outbox và định danh thực hiện ở nhà cung cấp giả lập. Đừng chỉ assert HTTP status: response lỗi vẫn có thể đi kèm một khoản tiền đã gửi ngoài dự kiến.

## 12. Quan sát, xử lý sự cố và dọn vòng đời flag

### 12.1. Ghi được quyết định đã thực sự áp dụng

Một bản ghi quyết định vận hành có thể chứa command ID, execution ID nếu có, mã thao tác, app version, engine, revision cấu hình nếu có thật, nguồn kết quả, tuổi dữ liệu, reason/error code đã chuẩn hóa và correlation ID. Liên kết với audit nghiệp vụ để phân biệt:

```text
FLAG_EVALUATION_FALLBACK -> phải dùng giá trị mặc định hoặc không có snapshot đủ tin cậy
NEW_EXECUTION_PAUSED    -> cổng vận hành từ chối nhận lần thực hiện mới
BUSINESS_RULE_REJECTED  -> quyền, trạng thái hoặc bất biến nghiệp vụ không thỏa mãn
EXECUTION_ADMITTED     -> ý định thực hiện đã được commit
REFUND_CONFIRMED       -> đã xác nhận kết quả theo giao thức nghiệp vụ
```

Không suy số tiền đã hoàn từ số lần flag bật hoặc số event đánh giá SDK. Một request có thể đánh giá nhiều flag, và một ý định đã nhận có thể còn chờ kết quả bên ngoài. Dùng dữ liệu nghiệp vụ đã xác minh cho chỉ số tiền và kết quả.

Metric hữu ích gồm tỷ lệ fallback theo flag/loại lỗi, tuổi snapshot, độ trễ truyền cấu hình, số instance chưa xác nhận trạng thái mong muốn, số lệnh mới sau yêu cầu dừng, tuổi outbox và lượng workflow cần đối soát. Không đưa user ID, tenant ID, execution ID hoặc toàn bộ targeting context làm nhãn metric có số lượng giá trị không giới hạn.

Log và trace chỉ giữ dữ liệu cần thiết, chuẩn hóa lỗi từ provider và giới hạn dung lượng. Không log token SDK, body chứa dữ liệu thanh toán hoặc toàn bộ context. Nếu telemetry được sampling, không coi số đếm mẫu là tổng nghiệp vụ thực; audit bắt buộc cần cơ chế lưu phù hợp riêng.

### 12.2. Runbook tạm dừng và khôi phục

Một runbook cho sự cố hoàn tiền có thể gồm:

1. Xác định loại sai lệch, phạm vi tenant/engine và điểm đang tạo tác động; giữ lại bằng chứng cấu hình cùng app version.
2. Đóng nhận lệnh mới bằng cơ chế có thẩm quyền đã chọn; nếu dùng gate chung, xác nhận transaction đóng đã commit. Đồng bộ flag hiển thị/rollout theo quy trình, không chỉ nhìn nút đã chuyển màu.
3. Kiểm kê công việc đã nhận, đang gửi, chờ kết quả và chưa biết kết quả. Dừng gửi mới nếu phạm vi sự cố yêu cầu, đồng thời giữ đường đối soát/tiếp nhận bằng chứng an toàn.
4. Kiểm tra revision và sức khỏe trên các instance, token/môi trường, tuổi cache, outbox và dữ liệu tiền; không giải phóng giữ chỗ hàng loạt khi chưa biết tác động ngoài.
5. Vá nhánh lỗi hoặc chọn nhánh an toàn có khả năng đọc dữ liệu hiện tại. Xác nhận retry vẫn giữ định danh cũ và không tái thực hiện các khoản đã xử lý.
6. Mở lại có giới hạn sau khi kiểm tra bất biến, tồn đọng và tương thích; quan sát kết quả nghiệp vụ trước khi tăng phạm vi. Ghi nhận ai đã đổi gì, phạm vi và thời điểm hiệu lực thực tế.

Đây là khung để cụ thể hóa theo kiến trúc, không phải một bảo đảm rằng mọi sự cố đều được giải quyết bằng bật/tắt. Nếu tác động đã đi ra ngoài, cần giao thức đối soát hoặc bù trừ phù hợp; rollback cấu hình không hoàn tác một giao dịch đã xảy ra.

### 12.3. Gỡ bỏ flag mà không thay đổi hợp đồng an toàn

Sau rollout, flag ngắn hạn trở thành nợ bảo trì nếu vẫn giữ hai nhánh không được kiểm thử. Việc dọn nên loại bỏ nhánh không còn cần, giữ nguyên guard bắt buộc, kiểm tra các job/consumer và bản triển khai cũ, rồi mới archive/xóa cấu hình theo khả năng sản phẩm. Không tái sử dụng key cũ cho một ý nghĩa mới vì code cũ có thể vẫn tham chiếu key đó.

Nếu còn khả năng rollback về bản dùng flag, phải biết default của bản đó khi flag đã bị xóa. Có thể cần giữ cấu hình trong giai đoạn tương thích hoặc thực hiện một kế hoạch loại bỏ nhiều bước. Với kill switch dài hạn, xác nhận nó vẫn được kiểm thử và có owner; đừng xóa chỉ vì một quy tắc chung yêu cầu mọi flag hết hạn.

Feature flag an toàn cho phép thay đổi cách triển khai và phạm vi tiếp nhận công việc, trong khi quyền, bất biến, state machine và idempotency tiếp tục được thực thi. Mọi quyết định cần có nguồn đáng tin, hành vi khi lỗi rõ ràng, giới hạn nhất quán được thừa nhận và bằng chứng về tác động nghiệp vụ thực tế.
