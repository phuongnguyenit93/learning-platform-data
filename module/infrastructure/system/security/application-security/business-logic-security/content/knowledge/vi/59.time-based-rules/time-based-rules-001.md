# Business time source: Nguồn thời gian cho quyết định nghiệp vụ

## 1. Vì sao nguồn thời gian là một phần của bảo mật logic?

Nhiều quy tắc nghiệp vụ phụ thuộc vào thời gian:

- Mã giảm giá chỉ dùng trong thời gian chương trình.
- Đơn hàng chỉ được hủy trước thời điểm kho bắt đầu xử lý.
- Lượt giữ chỗ chỉ được xác nhận trước hạn.
- Người dùng chỉ được nhận ưu đãi một lần trong một ngày theo lịch kinh doanh.
- Thao tác nhạy cảm phải cách lần thực hiện trước ít nhất một khoảng thời gian.
- Phê duyệt chỉ có giá trị trong thời gian chính sách hoặc ủy quyền còn hiệu lực.

Trong những trường hợp này, timestamp không chỉ để hiển thị. Nó là **đầu vào của quyết định cho phép hoặc từ chối một chuyển trạng thái nghiệp vụ**.

Nếu mỗi thành phần tự hiểu “bây giờ” theo một cách, người dùng có thể gặp quyết định khác nhau khi retry hoặc chuyển máy chủ. Người lạm dụng cũng có thể gửi thời gian giả, phát lại yêu cầu cũ hoặc chọn thời điểm cạnh tranh để vượt qua quy tắc.

**Business time source** là nguồn thời gian được hệ thống chỉ định làm căn cứ cho một loại quyết định nghiệp vụ, kèm quy tắc lấy, diễn giải và sử dụng thời gian đó.

Một thiết kế đầy đủ cần trả lời bốn câu hỏi:

1. Thời gian đến từ đâu, và ai có thể tác động đến nó?
2. Quy tắc sử dụng mốc nào: lúc tiếp nhận, lúc quyết định, lúc sự kiện xảy ra hay lúc hoàn tất?
3. Việc đọc thời gian có nằm trong ranh giới kiểm tra và cập nhật trạng thái hay không?
4. Khi nguồn thời gian sai lệch hoặc không khả dụng, thao tác nào được tiếp tục và theo chính sách nào?

Không có một nguồn thời gian duy nhất phù hợp cho mọi mục đích. Quan trọng là mỗi quyết định có một hợp đồng rõ ràng và các đường thực thi cùng tuân thủ hợp đồng đó.

## 2. Bắt đầu từ hợp đồng thời gian của quy tắc

Xét chương trình giảm giá có khoảng hiệu lực:

~~~text
starts_at <= decision_at < ends_at
~~~

Đây là khoảng có đầu trái đóng, đầu phải mở:

- Đúng thời điểm bắt đầu: được xét áp dụng.
- Trước thời điểm kết thúc: còn hiệu lực.
- Đúng thời điểm kết thúc: hết hiệu lực.

Điều kiện thời gian chỉ là một phần của điều kiện tổng:

~~~text
được áp dụng =
  đúng quyền trên đơn hàng
  AND đơn hàng ở trạng thái cho phép
  AND chương trình còn hiệu lực tại decision_at
  AND khách đủ điều kiện
  AND chưa vượt quota
  AND chưa sử dụng quyền lợi theo quy tắc
~~~

Một request còn trong giờ khuyến mại vẫn có thể bị từ chối do trạng thái hoặc quota. Ngược lại, kiểm tra quyền đúng không bù được việc dùng thời gian sai.

Nên mô tả hợp đồng trước khi chọn API thời gian:

| Thành phần hợp đồng | Ví dụ |
| --- | --- |
| Nguồn có thẩm quyền | Thời gian của cơ sở dữ liệu đang quyết định giao dịch |
| Mốc quyết định | Sau khi khóa đơn hàng và chương trình, trước khi ghi |
| Khoảng hiệu lực | Bắt đầu được tính, kết thúc không được tính |
| Độ chính xác | Dùng cùng độ chính xác với dữ liệu đã lưu |
| Quy tắc lịch | “Ngày” tính theo múi giờ kinh doanh đã cấu hình |
| Cách xử lý retry | Trả kết quả đã commit nếu cùng ý định |
| Chính sách khi nguồn lỗi | Không cấp ưu đãi mới nếu chưa xác minh được thời gian |
| Phiên bản chính sách | Ghi lại phiên bản được dùng khi quyết định |

Một hợp đồng khác có thể cho phép yêu cầu **được tiếp nhận trước hạn** hoàn tất sau hạn. Khi đó cần cơ chế ghi nhận tiếp nhận tin cậy và kiểm soát phát lại; không thể chỉ đổi tên một trường client gửi thành `received_at`.

## 3. Phân biệt các mốc thời gian

| Mốc | Ý nghĩa | Có tự quyết định quyền nghiệp vụ không? |
| --- | --- | --- |
| `client_sent_at` | Thời gian do thiết bị khách khai báo lúc gửi | Không; khách có thể chỉnh đồng hồ hoặc sửa request |
| `received_at` | Thời gian một thành phần máy chủ nhận yêu cầu | Chỉ khi hợp đồng chọn thành phần và cách ghi nhận đó |
| `decision_at` | Thời gian dùng để đánh giá quy tắc | Có, trong phạm vi quy tắc đã định nghĩa |
| `event_occurred_at` | Thời gian sự kiện thực sự xảy ra theo nguồn phát | Chỉ khi nguồn và ý nghĩa sự kiện được tin cậy theo hợp đồng |
| `recorded_at` | Thời gian hệ thống lưu sự kiện hoặc bản ghi | Không mặc nhiên bằng thời điểm sự kiện xảy ra |
| `effective_at` | Mốc bắt đầu hiệu lực do quy tắc xác định | Là dữ liệu chính sách; không nhất thiết là “bây giờ” |
| Thời điểm commit | Mốc transaction được cam kết ở hệ thống lưu trữ | Không mặc nhiên bằng thời gian đọc trước câu lệnh commit |

Ví dụ: khách gửi lúc 09:59:58, gateway nhận lúc 09:59:59, transaction chờ khóa đến 10:00:02, trong khi ưu đãi kết thúc lúc 10:00:00.

- Nếu hợp đồng dùng thời gian quyết định sau khóa, yêu cầu không đủ điều kiện.
- Nếu hợp đồng bảo vệ yêu cầu đã được tiếp nhận trước hạn, hệ thống cần chứng cứ tiếp nhận hợp lệ và các điều kiện bổ sung.
- Nếu chỉ tin `client_sent_at`, khách có thể gửi lúc 10:30 nhưng khai 09:59.

Không chọn timestamp có lợi nhất sau khi biết kết quả. Đó là thay đổi chính sách ngầm, khó audit và dễ bị lạm dụng.

Trong bài này, các ví dụ ghi đồng thời trên cơ sở dữ liệu sử dụng `decision_at` sau khi đã lấy đủ khóa. Một quyết định trước hạn có thể commit sau hạn trong lúc transaction vẫn giữ khóa. Yêu cầu “commit trước hạn” là một hợp đồng khác, cần thiết kế riêng.

## 4. Phân loại nguồn thời gian và ranh giới tin cậy

### 4.1. Thiết bị khách

Đồng hồ trình duyệt hoặc điện thoại phù hợp để dựng bộ đếm ngược, ghi nhận thao tác phục vụ trải nghiệm và gửi dữ liệu ngày tháng do người dùng khai báo.

Không dùng nó trực tiếp để:

- Gia hạn một quyền lợi.
- Chứng minh đơn hàng được gửi trước hạn.
- Reset quota.
- Bỏ qua thời gian chờ.
- Cho phép thực hiện hành động bằng một quyền đã hết hiệu lực.

Ngày sinh, ngày mong muốn nhận hàng hoặc ngày của chứng từ là dữ liệu nghiệp vụ hợp lệ để nhập. Nhưng đó không phải bằng chứng cho “thời gian hiện tại” của hệ thống.

### 4.2. Máy chủ ứng dụng

Máy chủ ứng dụng có thể là nguồn phù hợp khi quyết định được xử lý tại đó và chính sách chấp nhận sai lệch của hệ thống đồng hồ.

Rủi ro cần tính đến:

- Các máy có độ lệch khác nhau.
- Đồng hồ bị điều chỉnh khi vận hành.
- Request chờ lâu sau lần đọc thời gian.
- Máy mới khởi động hoặc cấu hình sai.
- Cấu hình giả lập thời gian vô tình được bật trong môi trường thật.

Nhiều máy cùng dùng một thư viện thời gian không có nghĩa chúng đọc cùng một “bây giờ”.

### 4.3. Cơ sở dữ liệu có thẩm quyền

Khi trạng thái và quota được bảo vệ trong một cơ sở dữ liệu, lấy thời gian tại cơ sở dữ liệu đó giúp gắn quyết định với dữ liệu đang được khóa và cập nhật.

Đây là lựa chọn kiến trúc, không phải bảo đảm rằng đồng hồ cơ sở dữ liệu luôn chính xác. Vẫn cần vận hành đồng hồ đúng, hiểu API thời gian và tránh dùng thời gian cũ sau khi chờ khóa.

Đọc giờ từ một replica rồi ghi sang nơi quyết định khác không tự tạo ra một ranh giới nguyên tử. Với mô hình nhiều nơi ghi, cần chỉ định nơi quyết định cho từng dữ liệu hoặc cơ chế phối hợp phù hợp.

### 4.4. Nguồn sự kiện bên ngoài

Nhà cung cấp thanh toán có thể gửi thời gian thanh toán; hệ thống vận chuyển có thể gửi thời gian bàn giao hàng.

Chữ ký hoặc cơ chế xác thực nguồn giúp xác minh thông điệp theo hợp đồng tích hợp. Nó chưa trả lời toàn bộ các câu hỏi:

- Timestamp biểu thị sự kiện gì?
- Sự kiện có thể bị gửi lại hoặc đến sai thứ tự không?
- Độ trễ tối đa và cách sửa sự kiện là gì?
- Thời gian đó có được dùng để giữ quyền lợi sau hạn không?
- Cần chống phát lại và đối soát bằng ID sự kiện như thế nào?

Chỉ nguồn đã được quy định mới có quyền cung cấp mốc thời gian cho quyết định tương ứng.

## 5. Thời gian lịch và đồng hồ đo khoảng thời gian

Cần phân biệt hai loại công cụ:

| Công cụ | Phù hợp cho | Hạn chế |
| --- | --- | --- |
| Đồng hồ thời gian lịch, như `Instant` từ nguồn hệ thống | So sánh với hạn tuyệt đối, lịch chương trình, audit | Có thể bị điều chỉnh; nhiều máy có thể lệch nhau |
| Đồng hồ đơn điệu để đo khoảng thời gian | Đo thời gian chạy, timeout nội bộ trong một tiến trình | Không biểu diễn một ngày giờ chung giữa các máy |

Trong Java:

~~~java
long startedNanos = System.nanoTime();

performLocalWork();

long elapsedNanos = System.nanoTime() - startedNanos;
~~~

Hiệu hai lần đọc `System.nanoTime()` dùng để đo khoảng thời gian trong cùng JVM. Không lưu giá trị tuyệt đối đó làm hạn nghiệp vụ và không so sánh nó với giá trị từ JVM khác.

Với hạn giữ chỗ cần tồn tại qua restart:

~~~text
expires_at = một thời điểm tuyệt đối được lưu bền vững
valid      = decision_at < expires_at
~~~

Với timeout của lời gọi nội bộ trong một tiến trình, đồng hồ đo khoảng thời gian thường phù hợp hơn lấy hiệu hai timestamp lịch.

Đồng hồ đơn điệu không thay thế được lịch khuyến mại; đồng hồ lịch cũng không bảo đảm đo chính xác một khoảng thực thi khi hệ thống điều chỉnh giờ.

## 6. Thời gian, khóa và transaction phải đi cùng nhau

Mẫu dễ sai:

~~~java
Instant now = applicationClock.instant();

return transaction.execute(() -> {
    Order order = orders.lockForUpdate(orderId); // Có thể chờ lâu.

    if (now.isBefore(order.cancelDeadline())) {
        return cancel(order);
    }

    return CancelResult.expired();
});
~~~

Nếu request lấy `now` trước hạn nhưng chờ khóa đến sau hạn, nó vẫn được hủy theo giá trị cũ.

Mẫu phù hợp với hợp đồng “quyết định sau khóa”:

~~~text
BEGIN
  khóa các hàng theo thứ tự đã quy định
  đọc lại trạng thái và quyền trên đối tượng
  decision_at = đọc thời gian có thẩm quyền
  kiểm tra quy tắc bằng decision_at
  ghi trạng thái, quota, kết quả idempotency và outbox
COMMIT
~~~

Điều kiện thời gian và trạng thái cần được quyết định trên cùng dữ liệu được bảo vệ. Hai request cùng đúng hạn vẫn có thể cùng tiêu thụ quyền lợi một lần nếu chỉ kiểm tra thời gian mà thiếu khóa, ràng buộc duy nhất hoặc cập nhật có điều kiện.

Các tác vụ khác cũng phải theo cùng giao thức. Một endpoint quản trị bỏ qua kiểm tra hạn hoặc một worker cập nhật trạng thái không có khóa có thể phá vỡ bất biến của API chính.

Thời gian cũng là dữ liệu có phiên bản gián tiếp: nếu quản trị viên đổi `ends_at` hoặc đổi chính sách trong lúc có request, cơ chế đồng thời phải xác định request dùng cấu hình nào. Có thể khóa chính sách hoặc lưu tham chiếu đến phiên bản chính sách bất biến phù hợp với mô hình nghiệp vụ.

## 7. Hiểu đúng API thời gian của cơ sở dữ liệu

Không phải mọi hàm có chữ “now” đều biểu diễn thời gian tại cùng một mốc.

Ví dụ trong PostgreSQL:

| Hàm hoặc biểu thức | Mốc thời gian |
| --- | --- |
| `CURRENT_TIMESTAMP`, `now()`, `transaction_timestamp()` | Thời điểm bắt đầu transaction |
| `statement_timestamp()` | Thời điểm bắt đầu câu lệnh hiện tại |
| `clock_timestamp()` | Thời gian thực tại lúc hàm được gọi |

Nếu transaction bắt đầu lúc 09:59:58 nhưng chờ khóa đến 10:00:02, đọc `CURRENT_TIMESTAMP` sau khi lấy khóa vẫn cho mốc bắt đầu transaction. Điều đó có thể sai với hợp đồng “xét hạn sau khóa”.

Một chuỗi câu lệnh minh họa:

~~~sql
BEGIN;

-- Các truy vấn phải kiểm tra đúng tenant và đúng quan hệ đối tượng.
SELECT id, state, promotion_id
FROM orders
WHERE tenant_id = :tenant_id
  AND id = :order_id
FOR UPDATE;

SELECT id, starts_at, ends_at, policy_version
FROM promotions
WHERE tenant_id = :tenant_id
  AND id = :promotion_id
FOR UPDATE;

-- Chỉ chạy truy vấn này sau khi đã lấy đủ các khóa cần thiết.
SELECT clock_timestamp() AS decision_at;

-- Ứng dụng dùng decision_at vừa đọc để kiểm tra và ghi cùng transaction.

COMMIT;
~~~

Thứ tự khóa trên chỉ minh họa. Hệ thống thực phải chọn một thứ tự chung cho mọi đường ghi; nếu một đường khóa promotion trước còn đường khác khóa order trước, có thể tạo deadlock.

Không gộp một biểu thức thời gian vào câu SQL phức tạp rồi tự giả định nó luôn được đánh giá sau mọi lần chờ khóa. Cách dễ kiểm chứng là lấy đủ khóa bằng các câu lệnh trước, sau đó đọc thời gian bằng câu lệnh riêng.

Cũng không gọi `clock_timestamp()` nhiều lần để kiểm tra từng vế của cùng quyết định nếu hợp đồng yêu cầu một mốc chung. Đọc một lần, gán thành `decision_at`, dùng nó cho điều kiện, dữ liệu quyết định và audit.

Nếu cần retry transaction do deadlock hoặc lỗi đồng thời, lần thử mới phải đọc lại trạng thái, chính sách và thời gian sau khi lấy khóa. Không tái sử dụng `decision_at` từ transaction đã rollback.

Không suy diễn hành vi PostgreSQL sang mọi hệ quản trị khác. Khi triển khai, phải xác minh ý nghĩa hàm thời gian, độ chính xác và cách đánh giá trong hệ thống đang dùng.

## 8. Đưa nguồn thời gian vào thiết kế Java

### 8.1. Tách chính sách thuần khỏi việc đọc đồng hồ

Một chính sách thuần có thể nhận thời gian làm tham số:

~~~java
public final class PromotionWindow {
    private final Instant startsAt;
    private final Instant endsAt;

    public PromotionWindow(Instant startsAt, Instant endsAt) {
        if (!startsAt.isBefore(endsAt)) {
            throw new IllegalArgumentException("Invalid time window");
        }
        this.startsAt = startsAt;
        this.endsAt = endsAt;
    }

    public boolean allows(Instant decisionAt) {
        return !decisionAt.isBefore(startsAt)
            && decisionAt.isBefore(endsAt);
    }
}
~~~

Lớp này không tự gọi đồng hồ nên dễ kiểm thử biên. Nhưng nó cũng không biết timestamp có đáng tin hay không. Ranh giới ứng dụng phải chịu trách nhiệm cung cấp `decisionAt` từ đúng nguồn.

Không để controller ánh xạ `request.now` vào tham số này. Đặt tên kiểu rõ ràng và giới hạn nơi khởi tạo thời gian quyết định giúp giảm nhầm lẫn.

### 8.2. Sử dụng Clock khi ứng dụng là nguồn có thẩm quyền

~~~java
public final class EligibilityService {
    private final Clock clock;

    public EligibilityService(Clock clock) {
        this.clock = clock;
    }

    public boolean isWithinWindow(PromotionWindow window) {
        Instant decisionAt = clock.instant();
        return window.allows(decisionAt);
    }
}
~~~

Trong kiểm thử có thể dùng `Clock.fixed(...)`. Trong môi trường thật có thể cấu hình `Clock.systemUTC()` nếu hợp đồng chọn đồng hồ máy chủ ứng dụng.

`Clock.systemUTC()` không đồng bộ giờ giữa các máy. UTC xác định cách biểu diễn múi giờ của clock, không chứng nhận độ chính xác của đồng hồ hệ điều hành.

Dependency injection cũng không tự bảo đảm quyền kiểm soát thời gian. Không cung cấp một header, query parameter hoặc endpoint công khai cho phép đổi clock của môi trường thật.

### 8.3. Nếu cơ sở dữ liệu là nguồn quyết định

Khi hợp đồng chọn cơ sở dữ liệu, không thay bằng `Clock.systemUTC()` chỉ vì dễ gọi hơn.

Có thể định nghĩa một cổng riêng:

~~~java
public interface TransactionTimeSource {
    Instant readDecisionTime();
}
~~~

Implementation phải thực thi truy vấn thời gian bằng **chính kết nối của transaction hiện tại**, sau khi các khóa cần thiết đã được lấy. Interface chỉ diễn tả ý định; không tự bảo đảm những điều kiện đó.

Giả mã luồng áp dụng ưu đãi một lần cho mỗi khách trong một chương trình:

~~~java
return transaction.execute(() -> {
    // Các hàm lock tuân thủ cùng thứ tự khóa trên toàn hệ thống.
    LockedContext context = repository.lockOrderAndPromotion(
        principal.tenantId(), orderId, promotionId
    );

    authorization.requireApplyPromotion(principal, context.order());

    Optional<ApplyResult> previous = idempotency.findSameIntent(
        principal, operationKey, requestFingerprint
    );
    if (previous.isPresent()) {
        return previous.get();
    }

    Instant decisionAt = transactionTimeSource.readDecisionTime();

    if (!context.window().allows(decisionAt)) {
        return ApplyResult.outsideWindow();
    }

    context.requireOrderCanAcceptPromotion();
    context.requireCustomerEligible(principal);
    context.requireQuotaAvailable();

    // Cần ràng buộc duy nhất hoặc cơ chế đồng thời tương đương
    // để bảo vệ quyền dùng một lần.
    repository.recordRedemption(context, principal, decisionAt);
    repository.applyDiscountAndConsumeQuota(context);

    ApplyResult result = ApplyResult.applied(context.order().id());
    idempotency.save(operationKey, requestFingerprint, result);
    outbox.addPromotionApplied(context, decisionAt);

    return result;
});
~~~

Các lớp và hàm trên là giả mã. Khi hiện thực cần giữ nguyên tính nguyên tử giữa ghi nhận sử dụng, cập nhật đơn hàng, quota, idempotency và outbox.

Nếu chính sách cho phép mỗi khách dùng một lần trong cả chương trình, một khóa duy nhất có thể dựa trên `(tenant_id, promotion_id, customer_id)`. Nếu cho phép một lần mỗi ngày, khóa còn cần kỳ nghiệp vụ được tính theo lịch đã quy định.

Kiểm tra thời gian không thay thế kiểm tra đối tượng hoặc chống sử dụng trùng. Một request vẫn có thể sửa `orderId` sang đơn của người khác hoặc chạy hai lần đồng thời.

## 9. UTC, múi giờ và ngày nghiệp vụ

### 9.1. Một thời điểm tuyệt đối khác một ngày trên lịch

`Instant` biểu diễn một thời điểm trên dòng thời gian. “Ngày 22 tháng 11” là một giá trị lịch, phải có múi giờ hoặc quy tắc bổ sung mới xác định được khoảng thời điểm.

Ví dụ chính sách “mỗi khách một ưu đãi trong mỗi ngày theo giờ Việt Nam”:

~~~java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate businessDate =
    decisionAt.atZone(businessZone).toLocalDate();
~~~

`businessDate` phải được tính từ `decisionAt` có thẩm quyền. Không nhận ngày hoặc múi giờ tùy ý từ request rồi dùng làm khóa quota.

Nếu chính sách theo múi giờ của chi nhánh, lấy cấu hình chi nhánh mà đối tượng thực sự thuộc về. Nếu cho phép người dùng đổi múi giờ hồ sơ, cần quy tắc tránh nhận lại quyền lợi bằng cách đổi cấu hình đó.

### 9.2. “Một ngày” không luôn là 24 giờ

Ở vùng có chuyển giờ mùa hè, ngày theo lịch có thể dài hoặc ngắn hơn 24 giờ. Các phép tính sau thể hiện hai ý định khác nhau:

~~~text
decision_at + 24 giờ
ngày mai tại đầu ngày theo múi giờ kinh doanh
~~~

Ví dụ tính khoảng của một ngày nghiệp vụ bằng Java:

~~~java
ZonedDateTime dayStart = businessDate.atStartOfDay(businessZone);
ZonedDateTime nextDayStart =
    businessDate.plusDays(1).atStartOfDay(businessZone);

Instant fromInclusive = dayStart.toInstant();
Instant toExclusive = nextDayStart.toInstant();
~~~

Cách này phù hợp nếu chính sách chọn cách diễn giải đầu ngày của thư viện. Nếu nghiệp vụ có giờ mở ngày riêng hoặc yêu cầu khác khi lịch có thời điểm không tồn tại/trùng lặp, phải quy định rõ cách xử lý và kiểm thử.

### 9.3. Không reset quyền lợi bằng một cờ dễ đảo ngược

Mẫu yếu:

~~~text
is_claimed = false vào lúc nửa đêm
nếu is_claimed == false thì cho nhận
~~~

Nếu job chạy lại, chạy sai múi giờ hoặc đồng hồ quay lùi, khách có thể nhận thêm.

Mẫu dễ bảo vệ hơn là ghi sự kiện nhận với kỳ nghiệp vụ:

~~~text
UNIQUE(tenant_id, benefit_id, customer_id, business_date)
~~~

Kỳ được tính trên server theo chính sách. Job tổng hợp có thể chạy lại mà không tạo quyền nhận mới trong cùng kỳ.

Nếu thay đổi múi giờ hoặc định nghĩa kỳ, phải có chính sách chuyển tiếp. Đưa phiên bản vào khóa duy nhất một cách máy móc có thể vô tình cho nhận lại trong cùng quyền lợi; cần xác định quy tắc chống trùng xuyên phiên bản.

## 10. Lệch đồng hồ, độ chính xác và khoảng bất định

### 10.1. Đồng bộ giờ là điều kiện vận hành, chưa phải chứng minh nghiệp vụ

Cơ chế đồng bộ đồng hồ giúp giảm sai lệch, nhưng không có nghĩa mọi máy luôn đọc chính xác cùng thời gian. Cần giám sát độ lệch, mất đồng bộ và thay đổi giờ bất thường.

Nếu ứng dụng A cho rằng hiện tại là 09:59:59 còn ứng dụng B cho rằng là 10:00:01, hai request cho cùng một hạn 10:00:00 có thể nhận kết quả khác nhau.

Với quyết định cần nhất quán, nên đưa các lần quyết định về cùng nơi có thẩm quyền hoặc sử dụng giao thức có cách xử lý độ bất định rõ ràng. Không giải quyết bằng cách cho phép client tự chọn timestamp của máy có lợi nhất.

### 10.2. Không biến dung sai thành gia hạn ngầm

Thêm `ends_at + 30 giây` để “bù lệch đồng hồ” thực chất mở rộng cửa sổ chấp nhận. Nếu đó là chính sách kinh doanh được phê duyệt, hãy biểu diễn rõ. Nếu chỉ là bản vá kỹ thuật ở một API, các đường khác sẽ quyết định không nhất quán.

Khi hệ thống có một **giới hạn sai số đáng tin cậy**, có thể mô hình hóa thời gian thực nằm trong `[lower_bound, upper_bound]`. Với khoảng hiệu lực `[starts_at, ends_at)`, chỉ chắc chắn còn trong khoảng nếu:

~~~text
lower_bound >= starts_at
AND upper_bound < ends_at
~~~

Nếu khoảng bất định chạm ranh giới, cần từ chối, yêu cầu thử lại hoặc đi vào quy trình đã định nghĩa. Không tự chọn nửa thuận lợi của khoảng.

Đây là mô hình lập luận. Không tự gán một con số sai số rồi coi nó là bảo đảm khi hệ thống vận hành chưa chứng minh được giới hạn đó.

### 10.3. Độ chính xác phải nhất quán

Một thành phần lưu mili giây, thành phần khác giữ nano giây; một API làm tròn lên trong khi worker cắt phần lẻ. Gần hạn, kết quả có thể khác nhau.

Hãy:

- Chọn độ chính xác của thời điểm chính sách khi lưu.
- Dùng thời điểm đã được chuẩn hóa và lưu làm căn cứ.
- Xác định cách xử lý dữ liệu có độ chính xác cao hơn.
- Kiểm thử ngay trước, đúng tại và ngay sau ranh giới theo độ chính xác được hỗ trợ.

Không cắt thời gian hiện tại xuống giây ở một đường kiểm tra nhưng giữ nguyên ở đường khác. Việc đó có thể tạo thêm một khoảng chấp nhận ngoài hợp đồng.

### 10.4. Đồng hồ quay lùi không được hồi sinh trạng thái đã kết thúc

Nếu một lượt giữ đã chuyển thành `EXPIRED`, đồng hồ bị chỉnh lùi không được làm nó quay về `HELD`. State machine phải chặn chuyển đổi đó độc lập với phép so sánh thời gian.

Tương tự, nếu đồng hồ nhảy tiến và hệ thống đã thu hồi hoặc chốt quyền lợi, việc chỉnh lại đồng hồ chưa tự hoàn tác các quyết định đã commit. Cần quy trình đối soát và bù trừ theo nghiệp vụ.

Không âm thầm ép mọi giá trị “bây giờ” thành giá trị lớn nhất từng thấy rồi giả định đã giải quyết mọi vấn đề. Cách làm đó có thể giữ hệ thống ở tương lai sau một lần nhảy giờ lớn và làm sai lịch kinh doanh.

## 11. Hàng đợi và sự kiện đến muộn

Một yêu cầu được tạo trước hạn có thể chờ trong hàng đợi đến sau hạn. Worker cần biết hợp đồng chọn mốc nào.

### 11.1. Hợp đồng dùng thời điểm xử lý

Worker đọc thời gian tại lúc quyết định, sau khi lấy khóa, rồi kiểm tra cửa sổ. Một thông điệp cũ không có quyền bỏ qua hạn chỉ vì trường `createdAt` ghi trước đó.

Cách này phù hợp khi quyền lợi chỉ được cấp nếu tài nguyên còn hợp lệ tại lúc xử lý.

### 11.2. Hợp đồng bảo vệ tiếp nhận trước hạn

Nếu khách phải được bảo vệ khi hệ thống đã nhận yêu cầu đúng hạn, cần:

1. Thành phần tiếp nhận có thẩm quyền, ghi thời gian theo nguồn đã chọn.
2. Bản ghi bền vững gắn với danh tính, đối tượng, ý định và ID yêu cầu.
3. Cơ chế chống sửa, giả mạo, dùng lại hoặc đổi ý định sau tiếp nhận.
4. Thời gian tối đa được xử lý muộn và chính sách khi quá giới hạn đó.
5. Quy tắc giữ quota hoặc tài nguyên trong lúc chờ.
6. Kiểm tra trạng thái, quyền và các điều kiện còn lại tại lúc xử lý.

Ghi `received_at` trước hạn không tự bảo đảm tài nguyên còn đủ sau hạn. Nếu tài nguyên đã cấp cho người khác, cần cơ chế giữ trước hoặc xử lý bù trừ; không thể xác nhận chồng bằng một timestamp cũ.

Một header do gateway nội bộ thêm chỉ có ý nghĩa nếu đường đi tin cậy loại bỏ giá trị giả từ bên ngoài và dịch vụ không thể bị gọi vòng để bỏ qua gateway. Với luồng có độ bền hoặc yêu cầu chống phát lại cao, cần bản ghi hoặc chứng cứ tiếp nhận phù hợp, không chỉ một header.

### 11.3. Webhook thanh toán

Webhook đến lúc 10:05 có thể báo giao dịch xảy ra lúc 09:59. Có dùng 09:59 để xét ưu đãi hay không là quyết định nghiệp vụ phụ thuộc hợp đồng tích hợp.

Phải xác thực nguồn, đối chiếu ID sự kiện và giao dịch, xử lý trùng, đồng thời kiểm tra trạng thái hiện tại. Một timestamp hợp lệ từ nhà cung cấp không tự cho phép đổi giá đơn đã chốt, phục hồi lượt giữ đã thu hồi hoặc bỏ qua phê duyệt.

## 12. Idempotency và thời gian: quyết định đã commit có hiệu lực riêng

Giả sử ưu đãi kết thúc lúc 10:00:

1. Lúc 09:59:59, request được quyết định hợp lệ và commit.
2. Phản hồi bị mất.
3. Lúc 10:00:02, khách retry cùng key và tham số.

Nếu hệ thống đã ghi nhận kết quả thành công, retry nên trả lại kết quả đó theo hợp đồng idempotency. Không chạy lại phép cấp quyền và từ chối chỉ vì lần đọc giờ mới đã qua hạn.

Ngược lại, nếu lần đầu rollback và chưa có kết quả commit, lần thử mới phải kiểm tra trạng thái và thời gian hiện tại theo hợp đồng. “Đã từng gửi trước hạn” chưa đủ để chứng minh đã được chấp nhận.

Các nguyên tắc:

- Key idempotency có phạm vi rõ theo tenant, chủ thể và thao tác.
- Cùng key nhưng thay đổi ý định phải bị từ chối.
- Kết quả và tác động nghiệp vụ được lưu nguyên tử.
- Việc trả kết quả cũ vẫn phải kiểm tra quyền truy cập.
- Không dùng key như một giấy phép miễn kiểm tra hạn cho thao tác mới.
- Chính sách lưu key phải bao phủ khoảng retry được hỗ trợ.

Một kết quả từ chối có được lưu idempotent hay không cũng cần rõ. Ví dụ một request được gửi trước khi chương trình bắt đầu có thể được xét lại sau đó, hoặc bị coi là cùng một quyết định đã hoàn tất. Hai hành vi đều cần hợp đồng cụ thể; không để cache lỗi tùy ý quyết định.

Đặc biệt, không triển khai gia hạn theo kiểu “mỗi lần nhận lại request, đặt hạn bằng now cộng năm phút” nếu không có idempotency. Khách có thể dùng retry để kéo dài quyền ngoài chính sách.

## 13. Audit phải lưu thời gian đã dùng để quyết định

Để giải thích một quyết định sau này, nên lưu:

~~~text
decision_id
operation_id / idempotency_reference
tenant_id, actor_id, object_id
operation
previous_state, next_state
decision_at
time_source_identifier
policy_id, policy_version
starts_at / ends_at hoặc tham chiếu chính sách bất biến
business_zone, business_period nếu áp dụng
outcome, reason_code
recorded_at
correlation_id
~~~

Không nhất thiết mọi trường đều nằm trong một bảng. Điều quan trọng là có thể liên kết và truy xuất mà không phụ thuộc dữ liệu chính sách hiện tại đã bị chỉnh sửa.

`decision_at` phải là chính giá trị đã dùng trong điều kiện. Nếu kiểm tra bằng đồng hồ ứng dụng rồi audit bằng giá trị mặc định `CURRENT_TIMESTAMP` của cơ sở dữ liệu, hai trường có thể khác mốc và gây hiểu nhầm.

`recorded_at` thể hiện thời điểm lưu hoặc ghi log; nó không tự là bằng chứng về thời điểm quyết định. Timestamp của công cụ quan sát cũng có thể là lúc thu nhận log.

Để tái hiện kết quả lịch sử:

~~~text
đánh giá lại =
  chính sách/phiên bản lịch sử
  + dữ liệu đầu vào lịch sử cần thiết
  + decision_at đã ghi nhận
~~~

Không dùng thời gian hiện tại để “phát lại” một quyết định cũ. Cũng không dùng ngày kết thúc hiện tại của chương trình nếu ngày đó đã được sửa sau giao dịch.

Log và audit cần quyền truy cập phù hợp; tránh ghi bí mật xác thực hoặc toàn bộ dữ liệu nhạy cảm của request. Thông tin nguồn thời gian và phiên bản chính sách thường hữu ích hơn việc sao chép mọi header.

## 14. Khi nguồn thời gian lỗi hoặc không đáng tin

Không fallback một cách im lặng từ thời gian cơ sở dữ liệu sang thời gian client hoặc một máy bất kỳ. Fallback có thể thay đổi chính sách mà không để lại dấu vết.

Cần xác định hành vi theo thao tác:

| Loại thao tác | Hướng xử lý cần cân nhắc |
| --- | --- |
| Cấp ưu đãi, quyền hoặc quota có hạn | Tạm từ chối hoặc đưa vào hàng đợi nếu chưa xác minh được điều kiện |
| Xác nhận sử dụng tài nguyên sắp hết hạn | Không xác nhận bằng nguồn thời gian không được hợp đồng chấp nhận |
| Đọc thông tin hiển thị | Có thể trả dữ liệu đã lưu cùng thông tin độ mới phù hợp |
| Thu hồi dựa trên việc đã qua hạn | Trì hoãn thu hồi nếu không xác định được hạn đã đến, theo chính sách an toàn tài nguyên |
| Hủy hoặc hoàn tác theo ý định chủ thể | Quyết định theo chính sách riêng; không mặc nhiên coi mọi thao tác hủy đều vô hại |

Chẳng hạn hủy một lệnh chuyển tiền hoặc hủy đơn sau thời điểm kho xử lý cũng có quy tắc thời gian và tác động kinh tế. Không nên có một quy tắc chung “nguồn thời gian lỗi thì cứ cho hủy”.

Nếu dùng một nguồn dự phòng, cần chỉ rõ:

- Điều kiện kích hoạt và người/cơ chế được phép chuyển.
- Giới hạn sai lệch được chấp nhận.
- Phạm vi thao tác được dùng nguồn dự phòng.
- Dấu vết audit của việc đổi nguồn.
- Cách đối soát khi nguồn chính phục hồi.

Nếu phát hiện đồng hồ nhảy bất thường, có thể tạm dừng các quyết định nhạy cảm theo chính sách đã chuẩn bị, cảnh báo và xử lý sự cố. Việc sửa giờ không tự sửa được những quyết định nghiệp vụ đã commit.

## 15. Kiểm thử chính sách và ranh giới tin cậy

### 15.1. Kiểm thử biên với đồng hồ cố định

Ví dụ theo phong cách JUnit cho chính sách khoảng thời gian ở phần trên:

~~~java
@Test
void endIsExclusive() {
    Instant start = Instant.parse("2026-11-22T02:00:00Z");
    Instant end = Instant.parse("2026-11-22T03:00:00Z");
    PromotionWindow window = new PromotionWindow(start, end);

    assertFalse(window.allows(start.minusMillis(1)));
    assertTrue(window.allows(start));
    assertTrue(window.allows(end.minusMillis(1)));
    assertFalse(window.allows(end));
    assertFalse(window.allows(end.plusMillis(1)));
}

@Test
void serviceUsesInjectedClock() {
    Instant start = Instant.parse("2026-11-22T02:00:00Z");
    Instant end = Instant.parse("2026-11-22T03:00:00Z");
    Clock fixed = Clock.fixed(end, ZoneOffset.UTC);

    EligibilityService service = new EligibilityService(fixed);

    assertFalse(service.isWithinWindow(
        new PromotionWindow(start, end)
    ));
}
~~~

Các ví dụ cần import Java Time và JUnit thích hợp khi đưa vào dự án. Chúng kiểm tra quy tắc thuần, chưa chứng minh adapter đọc thời gian cơ sở dữ liệu đúng kết nối hoặc transaction được khóa đúng.

Với dữ liệu lưu độ chính xác khác mili giây, chọn các điểm biên theo độ chính xác thực tế. Cũng cần kiểm tra đầu vào không hợp lệ như khoảng rỗng hoặc thời điểm kết thúc trước bắt đầu.

### 15.2. Ma trận tình huống tấn công logic

| Tình huống | Bất biến hoặc hành vi cần chứng minh |
| --- | --- |
| Client gửi `now` trước hạn nhưng server đã qua hạn | Không dùng thời gian client để cấp quyền |
| Client chỉnh đồng hồ hoặc đổi múi giờ | Không làm đổi thời điểm quyết định có thẩm quyền |
| Request bắt đầu trước hạn, lấy đủ khóa sau hạn | Tuân thủ hợp đồng mốc quyết định đã chọn |
| Transaction đã chạy lâu trước khi lấy giờ | Không nhầm thời gian bắt đầu transaction với giờ hiện tại |
| Hai request cùng đúng hạn cho quyền lợi dùng một lần | Tối đa một quyền lợi được cấp |
| Retry transaction sau deadlock | Đọc lại giờ và trạng thái, không dùng decision_at đã rollback |
| Retry cùng key sau hạn, lần đầu đã commit | Trả kết quả cũ, không cấp thêm |
| Retry sau hạn, lần đầu chưa commit | Xét lần mới theo hợp đồng, không dựa vào lần gửi cũ |
| Cùng key nhưng đổi đơn hoặc khách | Bị từ chối |
| Client đổi ngày nghiệp vụ hoặc múi giờ để nhận lại | Không vượt giới hạn theo kỳ |
| Ngày có thay đổi giờ mùa hè | Khoảng ngày đúng lịch kinh doanh |
| Độ chính xác bị cắt hoặc làm tròn ở một đường xử lý | API và worker quyết định theo cùng hợp đồng |
| Event đến muộn nhưng mang timestamp cũ | Không tự bỏ qua trạng thái, quyền hoặc dung lượng hiện tại |
| Đồng hồ quay lùi sau khi lượt giữ đã hết hạn | Không hồi sinh trạng thái cuối |
| Đồng hồ nhảy tiến rồi được sửa lại | Không tự hoàn tác quyết định đã commit |
| Nguồn thời gian chính không khả dụng | Thực hiện chính sách đã xác định, không fallback sang client |
| Endpoint quản trị hoặc callback ghi trạng thái | Không đi vòng quy tắc thời gian và quyền |
| Chính sách bị thay đổi đồng thời | Có thể xác định phiên bản thực sự đã dùng |

### 15.3. Kiểm thử transaction thực

Dùng ít nhất hai kết nối khi kiểm tra tranh chấp khóa:

~~~text
T1 lấy khóa dữ liệu liên quan
T2 bắt đầu yêu cầu cạnh tranh và chờ

T1 ghi dữ liệu rồi commit
T2 lấy được khóa
T2 đọc lại trạng thái, chính sách và thời gian
T2 quyết định và commit hoặc rollback

Kiểm tra dữ liệu cuối, quota, idempotency và outbox
~~~

Dùng hàng rào đồng bộ để điều khiển thứ tự, thay vì trông chờ một khoảng sleep sẽ luôn đủ dài. Với kiểm thử adapter thời gian thực của cơ sở dữ liệu, cần quan sát các mốc do cơ sở dữ liệu trả về và bố trí kịch bản có biên đủ rõ; không dùng chênh lệch đồng hồ máy chạy test làm bằng chứng.

Các kiểm thử giả lập clock cần được giới hạn trong môi trường kiểm thử. Không mở khả năng khách hàng tùy ý thay đổi `decision_at` của hệ thống thật để thuận tiện cho test.

Kiểm tra không chỉ mã phản hồi mà cả tác động: trạng thái, số lần nhận quyền lợi, quota, số bản ghi audit và sự kiện được phát. Một request trả lỗi đúng vẫn có thể đã tiêu hao quota sai nếu transaction bị chia cắt.

## 16. Những mẫu triển khai dễ tạo lỗ hổng

| Mẫu sai | Hậu quả | Hướng sửa |
| --- | --- | --- |
| `request.now < expiresAt` | Client tự chọn điều kiện có lợi | Đọc nguồn thời gian có thẩm quyền |
| Đọc giờ trước khi chờ khóa | Dùng quyết định đã lỗi thời | Lấy đủ khóa rồi đọc mốc quyết định |
| Dùng thời gian bắt đầu transaction cho quy tắc cần giờ sau khóa | Vô tình kéo dài cửa sổ | Chọn API thời gian đúng nghĩa |
| Gọi clock ở nhiều nơi cho cùng quyết định | Điều kiện và audit có thể khác mốc | Đọc một lần và truyền cùng giá trị |
| Mỗi service tự tính ngày theo múi giờ máy | Reset quota không thống nhất | Tính kỳ theo cấu hình kinh doanh |
| Chỉ chạy cron để đóng chương trình | Khoảng trống trước lần chạy cho phép vượt hạn | Kiểm tra hạn ở mỗi đường ghi |
| Cộng thêm dung sai riêng ở webhook | Quy tắc bị mở rộng không nhất quán | Mô hình hóa chính sách chung |
| Tin timestamp của sự kiện nhưng không chống phát lại | Tái sử dụng chứng cứ cũ | Đối chiếu ID, ý định, trạng thái và idempotency |
| Đánh giá lại retry thành công bằng thời gian mới | Mất tính ổn định của kết quả đã commit | Trả kết quả idempotent đã ghi |
| Reset cờ theo giờ máy để cấp quyền mỗi ngày | Nhận trùng khi job lặp hoặc giờ quay lùi | Ghi quyền lợi theo kỳ với ràng buộc chống trùng |
| Dùng `nanoTime` làm hạn lưu trong DB | Không so sánh đúng giữa máy hoặc qua restart | Lưu hạn tuyệt đối, dùng nanoTime để đo khoảng cục bộ |
| Tự phục hồi trạng thái cuối khi giờ quay lùi | Hồi sinh quyền đã thu hồi | Chặn bằng state machine |

## 17. Kiểm tra thiết kế trước khi triển khai

Một bản thiết kế có thể được xem xét qua các câu hỏi:

1. Quy tắc này dùng thời điểm tiếp nhận, quyết định hay sự kiện bên ngoài?
2. Ai có thẩm quyền cung cấp thời điểm đó, và dữ liệu có đi qua ranh giới không tin cậy nào?
3. Mọi API, worker, callback và thao tác quản trị có dùng cùng hợp đồng không?
4. Thời gian được lấy trước hay sau khi lấy đủ khóa?
5. Khoảng hiệu lực có tính đúng thời điểm kết thúc không?
6. Độ chính xác và múi giờ được định nghĩa ở đâu?
7. Ngày nghiệp vụ có thể bị đổi bằng dữ liệu người dùng kiểm soát không?
8. Retry sau commit và retry sau rollback được phân biệt như thế nào?
9. Nếu timestamp hợp lệ nhưng trạng thái hoặc tài nguyên đã thay đổi, hệ thống xử lý ra sao?
10. Audit có đủ dữ liệu để giải thích và tái hiện quyết định lịch sử không?
11. Khi đồng hồ sai hoặc nguồn thời gian lỗi, hành vi nào đã được quy định?
12. Kiểm thử nào chứng minh người dùng không thể vượt quyền hoặc nhận trùng bằng cách thao túng thời gian?

Nguồn thời gian cho quyết định nghiệp vụ cần được thiết kế cùng quyền theo đối tượng, state machine, transaction và idempotency. Chọn đúng đồng hồ là bước đầu; bảo vệ được quy tắc đòi hỏi lấy đúng mốc, dùng đúng ranh giới và lưu lại đúng căn cứ của quyết định.
