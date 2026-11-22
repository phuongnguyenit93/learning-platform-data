# Phân biệt thao tác có thể lặp lại với thao tác gây tác dụng phụ

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích tính idempotent (tính lặp an toàn) và phân biệt nó với thao tác không có side effect.
- Nhận diện rủi ro khi retry một request messaging sau timeout hoặc mất kết nối.
- Phân biệt retry ở client, redelivery của message và việc xử lý trùng ở consumer.
- Thiết kế idempotency key, deduplication và lưu kết quả để một thao tác nghiệp vụ chỉ tạo ra hiệu ứng một lần trong phạm vi đã xác định.
- Áp dụng các nguyên tắc này với Spring Messaging và RSocket.
- Chọn retry policy, transaction, inbox/outbox hoặc cơ chế bù trừ phù hợp với loại tác dụng phụ.

Bài này thuộc chủ đề **Spring Framework - messaging**, trong nhánh **Lỗi và phục hồi**. Trọng tâm là làm cho hệ thống xử lý đúng khi cùng một yêu cầu có thể đến nhiều lần, đặc biệt khi client không biết server đã thực hiện thao tác hay chưa.

## 1. Tính idempotent là gì?

Một thao tác là **idempotent** nếu thực hiện nó một lần hay lặp lại nhiều lần với cùng đầu vào và cùng phạm vi nghiệp vụ tạo ra cùng trạng thái cuối cùng.

Có thể biểu diễn bằng:

~~~text
f(f(state, request), request) = f(state, request)
~~~

Nói cách khác, sau lần thực hiện đầu tiên, những lần lặp lại cùng yêu cầu không làm hiệu ứng nghiệp vụ tăng thêm.

Ví dụ:

| Thao tác | Idempotent? | Lý do |
|---|---|---|
| Đặt trạng thái đơn hàng thành SHIPPED | Có, nếu cùng đơn hàng và cùng trạng thái | Lặp lại vẫn giữ trạng thái SHIPPED |
| Đánh dấu thông báo đã đọc | Thường có | Trạng thái cuối vẫn là đã đọc |
| Lấy thông tin đơn hàng | Thường có về trạng thái nghiệp vụ | Đọc lại không tạo thêm thay đổi nghiệp vụ |
| Tăng số lượt xem thêm 1 | Không | Mỗi lần gọi làm bộ đếm tăng tiếp |
| Trừ 100.000 đồng khỏi tài khoản | Không | Lặp lại có thể trừ tiền nhiều lần |
| Tạo một đơn hàng mới | Thường không | Mỗi lần gọi có thể tạo một đơn hàng khác |
| Gửi email xác nhận | Không tự động idempotent | Mỗi lần gửi có thể tạo thêm một email |

Idempotent không đồng nghĩa với **không có tác dụng phụ**. Cập nhật trạng thái đơn hàng, ghi nhận thanh toán hoặc phát hành một hóa đơn đều là thao tác có tác dụng phụ. Chúng vẫn có thể được thiết kế idempotent nếu hệ thống nhận diện được các lần lặp của cùng một thao tác và ngăn hiệu ứng bị nhân đôi.

Ngược lại, một thao tác không làm thay đổi dữ liệu nghiệp vụ vẫn có thể tạo tác dụng phụ kỹ thuật như ghi audit log, tăng metric hoặc tiêu thụ tài nguyên. Vì vậy cần xác định rõ trạng thái và hiệu ứng nào phải được bảo vệ.

## 2. Vì sao messaging cần tính lặp an toàn?

Trong hệ thống phân tán, client gửi request qua mạng và chờ kết quả. Có nhiều thời điểm kết nối có thể thất bại:

1. Client gửi request nhưng request chưa tới server.
2. Request đã tới server, nhưng server chưa bắt đầu xử lý.
3. Server đang xử lý thì kết nối bị ngắt.
4. Server đã commit thay đổi nghiệp vụ, nhưng response bị mất trên đường về.
5. Client nhận timeout trước khi biết kết quả cuối cùng của server.

Trường hợp thứ tư đặc biệt nguy hiểm. Client thấy timeout nên không biết thao tác đã thành công hay chưa. Nếu client gửi lại một lệnh trừ tiền hoặc tạo đơn hàng mà server không có cơ chế nhận diện trùng, hiệu ứng có thể xảy ra hai lần.

**Timeout là trạng thái không chắc chắn, không phải bằng chứng rằng server chưa thực hiện thao tác.**

Do đó, retry an toàn cần trả lời hai câu hỏi:

- Lỗi có khả năng tạm thời và có thể hồi phục không?
- Nếu request đã được xử lý trước khi lỗi xảy ra, gửi lại cùng request có tạo thêm hiệu ứng không?

Chỉ kiểm tra loại exception là chưa đủ. Retry phải xét cả ngữ nghĩa nghiệp vụ của thao tác.

## 3. Idempotent, retryable và side-effect-free không giống nhau

Ba khái niệm thường bị dùng thay thế cho nhau nhưng có ý nghĩa khác nhau:

| Khái niệm | Ý nghĩa |
|---|---|
| Side-effect-free | Không làm thay đổi trạng thái hoặc tạo hiệu ứng bên ngoài trong phạm vi đang xét |
| Idempotent | Lặp lại cùng thao tác không làm hiệu ứng cuối cùng tăng thêm |
| Retryable | Có thể thử lại trong một số điều kiện lỗi mà vẫn giữ được hành vi đúng |

Một thao tác side-effect-free thường có thể retry an toàn nếu dữ liệu đọc không có yêu cầu nhất quán đặc biệt. Một thao tác idempotent có thể có side effect nhưng lặp lại vẫn an toàn. Một thao tác không idempotent có thể chỉ retry an toàn khi hệ thống có thêm cơ chế deduplication hoặc transaction.

Ví dụ, lệnh SET trạng thái tài khoản thành ACTIVE là thao tác có cập nhật dữ liệu nhưng có thể idempotent. Lệnh INCREMENT số dư hoặc tăng số lượng hàng tồn là thao tác không idempotent nếu không có mã nhận diện lần thực hiện.

HTTP cũng dùng khái niệm idempotent cho ngữ nghĩa phương thức: PUT và DELETE được định nghĩa là idempotent về hiệu ứng dự kiến, trong khi POST nói chung không có bảo đảm đó. Đây là quy ước ngữ nghĩa của HTTP; không thể suy ra mọi handler Spring hoặc mọi endpoint POST đều không idempotent. Điều quyết định là hợp đồng nghiệp vụ và cách triển khai thực tế.

## 4. Retry trong Spring Messaging và RSocket

Spring Messaging cung cấp abstraction cho message và handler. Với Spring RSocket, client thường dùng **RSocketRequester** để gửi request; server dùng **@MessageMapping** để nhận và xử lý.

Ví dụ một handler Request-Response:

~~~java
@Controller
class PaymentController {

    private final PaymentService payments;

    PaymentController(PaymentService payments) {
        this.payments = payments;
    }

    @MessageMapping("payments.charge")
    Mono<ChargeResult> charge(ChargeCommand command) {
        return payments.chargeOnce(command);
    }
}
~~~

Đây là skeleton minh họa. ChargeCommand phải mang một mã nhận diện ổn định cho thao tác, còn PaymentService chịu trách nhiệm kiểm tra trùng và thực hiện nghiệp vụ một cách an toàn.

Ở client, một request có thể được retry với Reactor:

~~~java
Mono<ChargeResult> result = requester
    .route("payments.charge")
    .data(command)
    .retrieveMono(ChargeResult.class)
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(3))
            .jitter(0.5)
            .filter(this::isTransient)
    );
~~~

Đoạn code là phần trích cần đặt trong một class đã có requester, command và phương thức isTransient; cần import các kiểu Reactor Retry và Duration tương ứng.

Điểm quan trọng:

- retryWhen resubscribe vào publisher upstream. Mỗi lần subscribe có thể gửi một request mới tới server.
- command và idempotency key phải được tạo ổn định bên ngoài publisher được retry. Không tạo key mới trong defer hoặc trong mỗi lần subscription.
- Chỉ retry lỗi có khả năng tạm thời, ví dụ một số lỗi kết nối hoặc quá tải có thể hồi phục.
- Không retry vô hạn. Số lần thử, khoảng chờ, jitter và thời hạn tổng phải có giới hạn.
- Nếu timeout xảy ra sau khi server commit, lần retry phải được server nhận diện là cùng một thao tác.

RSocket có nhiều interaction model như Request-Response, Request-Stream, Request-Channel và Fire-and-Forget. Những mô hình này mô tả cách trao đổi request, response và stream; bản thân chúng không cung cấp bảo đảm exactly-once cho hiệu ứng nghiệp vụ. Một lần mất kết nối hoặc một lần client retry vẫn có thể tạo ra request trùng ở tầng ứng dụng.

Đặc biệt, Fire-and-Forget không trả về response nghiệp vụ. Việc publisher hoàn tất ở client không nên được diễn giải thành bằng chứng rằng toàn bộ tác dụng phụ nghiệp vụ đã commit và được lưu bền vững. Nếu client cần xác nhận kết quả, hãy chọn interaction model có response hoặc xây dựng acknowledgement riêng.

## 5. Idempotency key: nhận diện một thao tác qua nhiều lần gửi

**Idempotency key** là mã định danh do caller tạo cho một thao tác nghiệp vụ. Mọi lần retry của cùng thao tác phải dùng lại cùng key.

Ví dụ:

~~~text
idempotencyKey = "checkout-2026-000184"
operation      = create payment
amount         = 250000
customer       = customer-42
~~~

Nếu client gửi lại cùng lệnh vì timeout, server tìm thấy key đã xử lý và trả lại kết quả đã lưu thay vì trừ tiền lần nữa.

Một thiết kế tốt cần các thuộc tính:

1. **Ổn định:** key không đổi giữa các lần retry của cùng thao tác.
2. **Duy nhất trong phạm vi:** key phải duy nhất trong tenant, tài khoản hoặc loại nghiệp vụ mà hệ thống quy định.
3. **Gắn với nội dung request:** lưu fingerprint hoặc các trường nghiệp vụ quan trọng để phát hiện việc dùng lại key cho một lệnh khác.
4. **Được lưu bền vững:** nếu thao tác quan trọng, trạng thái deduplication phải sống qua restart và hoạt động trên nhiều instance.
5. **Có thời hạn lưu phù hợp:** thời hạn giữ key phải dài hơn cửa sổ retry/redelivery mà hệ thống cam kết hỗ trợ.

Không nên dùng timestamp hiện tại làm key mới mỗi lần retry. Cũng không nên chỉ dùng một UUID được sinh ở server sau khi request đến, vì client không thể gửi lại đúng UUID đó khi bị timeout trước khi nhận response.

Key có thể nằm trong payload nghiệp vụ hoặc metadata tùy hợp đồng ứng dụng. Nếu dùng metadata, cần bảo đảm client và server thống nhất MIME type, encoder/decoder và chính sách xác thực. Dù đặt ở đâu, key phải được chuyển nguyên vẹn qua các lần retry.

## 6. Deduplication phải kiểm tra cả key và nội dung

Chỉ kiểm tra key đã tồn tại là chưa đủ. Giả sử request đầu tiên dùng key K để thanh toán 100.000 đồng. Một request khác vô tình dùng lại K để thanh toán 500.000 đồng. Nếu server chỉ nhìn thấy key trùng và trả kết quả cũ, lỗi phía client sẽ bị che giấu.

Một bản ghi idempotency nên lưu ít nhất:

| Trường | Mục đích |
|---|---|
| idempotency_key | Khóa nhận diện thao tác |
| request_fingerprint | Phát hiện cùng key nhưng nội dung khác |
| status | IN_PROGRESS, COMPLETED hoặc trạng thái lỗi có thể retry theo hợp đồng |
| result/reference | Kết quả đã tạo hoặc mã tham chiếu tới kết quả |
| created_at / expires_at | Quản lý thời hạn lưu deduplication |

Luồng xử lý thường là:

1. Nhận request và kiểm tra cú pháp, quyền truy cập, dữ liệu đầu vào.
2. Tạo fingerprint chuẩn hóa từ những trường có ảnh hưởng tới nghiệp vụ.
3. Thử tạo bản ghi idempotency với key duy nhất.
4. Nếu key mới, thực hiện nghiệp vụ và lưu kết quả.
5. Nếu key đã tồn tại và fingerprint khác, trả lỗi conflict.
6. Nếu key đã COMPLETED và fingerprint giống, trả lại kết quả đã lưu.
7. Nếu key đang IN_PROGRESS, áp dụng chính sách chờ, trả trạng thái đang xử lý hoặc cho phép caller truy vấn kết quả sau.

Fingerprint phải dựa trên biểu diễn chuẩn hóa. Không nên hash JSON tùy ý nếu thứ tự thuộc tính, định dạng số hoặc giá trị mặc định có thể thay đổi giữa hai request tương đương. Chọn các trường nghiệp vụ có ý nghĩa và chuẩn hóa chúng trước khi hash hoặc so sánh.

## 7. Ví dụ Java 17: chống thực hiện trùng trong một tiến trình

Ví dụ sau dùng ConcurrentHashMap để minh họa một thao tác có side effect được bảo vệ bằng idempotency key. Cùng một key và cùng nội dung lệnh sẽ nhận cùng kết quả; cùng key nhưng nội dung khác sẽ bị từ chối.

Lưu thành **IdempotencyDemo.java**:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class IdempotencyDemo {

    record ChargeCommand(
        String idempotencyKey,
        String customerId,
        long amountInCents
    ) {}

    record ChargeResult(String operationId, long amountInCents) {}

    record StoredResult(ChargeCommand command, ChargeResult result) {}

    static final class PaymentService {
        private final ConcurrentHashMap<String, StoredResult> completed =
            new ConcurrentHashMap<>();

        private final AtomicInteger executions = new AtomicInteger();

        ChargeResult charge(ChargeCommand command) {
            if (command.idempotencyKey() == null
                    || command.idempotencyKey().isBlank()) {
                throw new IllegalArgumentException(
                    "idempotencyKey is required"
                );
            }

            if (command.amountInCents() <= 0) {
                throw new IllegalArgumentException(
                    "amountInCents must be positive"
                );
            }

            StoredResult stored = completed.compute(
                command.idempotencyKey(),
                (key, previous) -> {
                    if (previous != null) {
                        if (!previous.command().equals(command)) {
                            throw new IllegalArgumentException(
                                "Idempotency key reused with different command"
                            );
                        }
                        return previous;
                    }

                    int sequence = executions.incrementAndGet();
                    ChargeResult result = new ChargeResult(
                        "payment-" + sequence,
                        command.amountInCents()
                    );

                    return new StoredResult(command, result);
                }
            );

            return stored.result();
        }

        int executionCount() {
            return executions.get();
        }
    }

    public static void main(String[] args) {
        PaymentService service = new PaymentService();

        ChargeCommand firstCommand = new ChargeCommand(
            "request-123", "customer-7", 2500
        );

        ChargeResult first = service.charge(firstCommand);
        ChargeResult retry = service.charge(firstCommand);

        System.out.println(
            "same-operation=" + first.operationId().equals(retry.operationId())
        );
        System.out.println("executions=" + service.executionCount());

        try {
            service.charge(
                new ChargeCommand("request-123", "customer-7", 3000)
            );
        } catch (IllegalArgumentException ex) {
            System.out.println("same-key-different-command=rejected");
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac IdempotencyDemo.java
java IdempotencyDemo
~~~

Output chính xác:

~~~text
same-operation=true
executions=1
same-key-different-command=rejected
~~~

Trong ví dụ, ConcurrentHashMap.compute thực hiện cập nhật nguyên tử theo key trong phạm vi map của tiến trình hiện tại. AtomicInteger chỉ đếm số lần nhánh tạo kết quả mới được chạy. Lần gọi thứ hai lấy lại kết quả cũ; lần gọi thứ ba dùng cùng key nhưng số tiền khác nên bị từ chối.

**Giới hạn của ví dụ:** map chỉ nằm trong bộ nhớ một tiến trình. Khi restart, dữ liệu mất; khi chạy nhiều instance, mỗi instance có map riêng. Đây không phải cơ chế lưu thanh toán production và không bảo vệ được side effect bên ngoài như gọi ngân hàng. Hệ thống thật cần kho lưu trữ bền vững và ràng buộc duy nhất ở tầng database hoặc dịch vụ nghiệp vụ.

## 8. Transaction và tính nguyên tử

Với side effect nằm trong cùng một cơ sở dữ liệu, có thể lưu bản ghi idempotency và thay đổi nghiệp vụ trong cùng transaction.

Ví dụ logic:

~~~text
BEGIN TRANSACTION

INSERT idempotency_record(key, fingerprint, status)
  -- key có UNIQUE constraint

Nếu insert thành công:
    cập nhật dữ liệu nghiệp vụ
    lưu kết quả và status = COMPLETED
    COMMIT
    trả kết quả

Nếu key đã tồn tại:
    đọc bản ghi hiện có
    so sánh fingerprint
    nếu khác: trả conflict
    nếu COMPLETED: trả kết quả đã lưu
    nếu IN_PROGRESS: áp dụng chính sách chờ/truy vấn

END
~~~

Ràng buộc UNIQUE là lớp bảo vệ quan trọng khi nhiều request đồng thời đến các instance khác nhau. Một thao tác kiểm tra rồi insert bằng hai câu lệnh riêng mà không có transaction/constraint phù hợp có thể tạo race condition: hai request cùng thấy key chưa tồn tại rồi cùng thực hiện side effect.

Trong Spring, có thể dùng transaction quản lý bởi Spring Data/JDBC/JPA hoặc reactive transaction tùy stack. Với code reactive, cần dùng reactive transaction manager và bảo đảm các thao tác tham gia cùng transaction context. Không gọi blocking database API trong event loop chỉ để né các vấn đề về transaction.

Nếu cập nhật database và gửi message ra broker/RSocket là hai side effect riêng, một transaction database thông thường không thể tự động commit nguyên tử cả hai hệ thống. Đây là lúc **Transactional Outbox** hữu ích:

1. Trong cùng transaction, cập nhật dữ liệu nghiệp vụ và ghi một outbox event.
2. Một publisher đọc outbox và gửi event ra ngoài.
3. Khi gửi thành công, đánh dấu hoặc lưu checkpoint để không bỏ sót event.
4. Consumer dùng inbox/deduplication để xử lý event trùng an toàn.

Outbox thường cung cấp khả năng phát event ít nhất một lần. Consumer vẫn cần idempotency vì publisher có thể gửi lại event sau khi mất acknowledgement.

## 9. Inbox, outbox và xử lý message trùng

Trong messaging, cần phân biệt **message delivery** với **business processing**.

- Outbox bảo đảm thay đổi nghiệp vụ và ý định phát message được lưu cùng transaction.
- Inbox ghi nhận message đã được consumer tiếp nhận/xử lý theo một message ID ổn định.
- Deduplication kiểm tra message ID hoặc idempotency key trước khi áp dụng side effect.
- Transaction bao quanh inbox record và thay đổi nghiệp vụ giúp tránh tình huống ghi nhận message đã xử lý nhưng nghiệp vụ chưa commit, hoặc ngược lại.

Một consumer có thể triển khai theo luồng:

~~~text
receive message
    |
validate message ID and payload
    |
begin transaction
    |
insert inbox record with UNIQUE(message_id)
    |
    +-- duplicate --> return prior outcome / ignore safely
    |
apply business state change
    |
commit
    |
acknowledge or complete processing
~~~

Nếu message ID đã tồn tại, consumer phải biết trạng thái xử lý trước đó. Không được đánh dấu message hoàn tất trước khi side effect quan trọng được commit. Nếu message có thể đang được xử lý bởi một worker khác, cần trạng thái IN_PROGRESS, lease/lock hoặc cơ chế claim phù hợp.

Với RSocket request-response, client có thể dùng idempotency key cho command. Với Request-Stream hoặc Request-Channel, từng phần tử trong stream cần định danh riêng nếu consumer có thể nhận lại hoặc khôi phục từ checkpoint. Một key của cả stream có thể xác định transfer, còn sequence/message ID xác định từng chunk.

## 10. Xử lý side effect bên ngoài

Không phải mọi side effect đều nằm trong database của ứng dụng. Ví dụ:

- Gọi cổng thanh toán.
- Gửi email hoặc SMS.
- Tạo tài nguyên ở cloud.
- Gọi một API của hệ thống khác.
- Xuất bản event sang broker.

Nếu ứng dụng commit database rồi gọi dịch vụ bên ngoài, hoặc gọi dịch vụ bên ngoài rồi mới commit database, đều có thể xuất hiện cửa sổ lỗi giữa hai bước.

Các lựa chọn:

1. **Downstream idempotency key:** truyền cùng key tới dịch vụ bên ngoài nếu dịch vụ hỗ trợ. Key phải được giữ ổn định qua mọi lần retry.
2. **Outbox:** lưu ý định thực hiện side effect trong database cùng transaction nghiệp vụ rồi xử lý bất đồng bộ.
3. **State machine:** lưu trạng thái từng bước, ví dụ PENDING, PROCESSING, SUCCEEDED, FAILED và cho phép khôi phục sau restart.
4. **Reconciliation:** đối chiếu trạng thái nội bộ với hệ thống ngoài khi kết quả không rõ ràng.
5. **Compensation/Saga:** nếu không thể rollback một side effect đã xảy ra, thực hiện hành động bù trừ nghiệp vụ theo quy trình đã thiết kế.

Hành động bù trừ không phải lúc nào cũng là phép đảo ngược hoàn hảo. Ví dụ hoàn tiền là một nghiệp vụ mới có audit trail, không phải xóa giao dịch thanh toán đã xảy ra.

Không được tự retry một lệnh bên ngoài chỉ vì client timeout. Trước tiên hãy tra cứu trạng thái bằng operation ID hoặc idempotency key nếu API cung cấp.

## 11. Chính sách retry an toàn

Một retry policy tốt có các thành phần:

- **Phân loại lỗi:** lỗi validation, quyền truy cập hoặc dữ liệu conflict thường không retry; lỗi kết nối tạm thời hoặc quá tải có thể retry có giới hạn.
- **Giới hạn số lần:** tránh vòng lặp vô hạn.
- **Exponential backoff:** tăng thời gian chờ giữa các lần thử để tránh dồn tải vào dịch vụ đang lỗi.
- **Jitter:** thêm độ lệch ngẫu nhiên để nhiều client không retry cùng thời điểm.
- **Deadline:** tổng thời gian retry phải nằm trong thời hạn nghiệp vụ.
- **Retry budget:** giới hạn tổng lượng retry để tránh làm sự cố lan rộng.
- **Idempotency:** giữ nguyên key và nội dung nghiệp vụ giữa các lần thử.
- **Quan sát:** ghi operation ID, idempotency key đã được che/mã hóa phù hợp, số lần thử, loại lỗi và kết quả cuối cùng.

Không nên retry mọi exception. Retry một lỗi nghiệp vụ vĩnh viễn chỉ làm tăng tải và độ trễ. Cũng không nên kết hợp nhiều lớp retry không giới hạn: client, gateway, service và thư viện đều retry có thể tạo ra số lần thực hiện lớn hơn dự kiến.

Nếu có timeout, hãy phân biệt:

- **Timeout trước khi gửi:** có thể chưa có request ở server.
- **Timeout trong khi server xử lý:** kết quả chưa rõ.
- **Timeout sau commit:** side effect có thể đã thành công, chỉ response bị mất.

Từ phía client, các trường hợp sau khi gửi thường không thể phân biệt chắc chắn chỉ bằng exception. Idempotency và tra cứu kết quả là cách giải quyết ở tầng nghiệp vụ.

## 12. Tương tác với các interaction model của RSocket

| Interaction model | Cách dùng thường gặp | Điều cần bảo vệ |
|---|---|---|
| Request-Response | Tạo đơn, cập nhật trạng thái, thanh toán | Idempotency key cho command và lưu kết quả |
| Request-Stream | Truy vấn luồng dữ liệu | Retry có thể phát lại toàn bộ stream; cần cursor/checkpoint nếu stream lớn |
| Request-Channel | Trao đổi hai chiều hoặc upload nhiều chunk | Định danh stream, sequence từng chunk, xử lý resume và duplicate |
| Fire-and-Forget | Gửi thông báo không cần response trực tiếp | Không dựa vào response để xác nhận commit; cần event ID và cơ chế theo dõi nếu quan trọng |

RSocket request(n) và Reactive Streams backpressure điều khiển demand của message/stream. Chúng không làm một side effect trở thành idempotent và không bảo đảm một command chỉ chạy một lần. Backpressure kiểm soát tốc độ; idempotency kiểm soát hiệu ứng trùng. Hai cơ chế giải quyết hai vấn đề khác nhau.

## 13. Kiểm thử tính lặp an toàn

Một bài kiểm thử chỉ gọi service một lần không chứng minh được idempotency. Hãy kiểm thử các tình huống:

1. Gửi cùng command hai lần với cùng key và cùng nội dung; chỉ có một hiệu ứng nghiệp vụ.
2. Gửi đồng thời nhiều request có cùng key; chỉ một request tạo side effect.
3. Dùng lại key với nội dung khác; server trả conflict hoặc lỗi phù hợp.
4. Server commit nhưng response bị làm mất; client retry và nhận lại kết quả đã lưu.
5. Restart service giữa các lần thử; deduplication vẫn còn nếu hệ thống cam kết lưu bền vững.
6. Gửi cùng key tới hai instance khác nhau; database constraint hoặc kho dùng chung vẫn ngăn trùng.
7. Downstream timeout sau khi có thể đã thực hiện side effect; kiểm tra tra cứu trạng thái hoặc downstream key.
8. Message trùng đến consumer; inbox/deduplication ngăn cập nhật lặp.
9. Message lỗi vĩnh viễn; retry policy dừng thay vì lặp vô hạn.
10. Message đang IN_PROGRESS; request trùng được xử lý theo chính sách đã định.

Trong kiểm thử tích hợp, nên mô phỏng mất kết nối sau khi transaction commit nhưng trước khi response đến client. Đây là tình huống dễ bỏ sót nhất khi chỉ kiểm tra lỗi trước khi server bắt đầu xử lý.

## 14. Lỗi thiết kế thường gặp

- **Sinh idempotency key mới trong mỗi lần retry:** server coi mỗi lần thử là một thao tác mới.
- **Chỉ lưu key ở memory:** restart hoặc nhiều instance làm mất tính deduplication.
- **Không so sánh request fingerprint:** cùng key có thể bị dùng nhầm cho nội dung khác.
- **Đánh dấu COMPLETED trước khi commit nghiệp vụ:** có thể bỏ qua thao tác chưa thực sự thành công.
- **Commit nghiệp vụ rồi ghi deduplication ở transaction khác:** crash giữa hai bước có thể làm side effect lặp.
- **Cho rằng Request-Response đồng nghĩa exactly-once:** response có thể mất sau khi server đã commit.
- **Retry mọi lỗi:** làm tăng tải và lặp lại lỗi không thể hồi phục.
- **Retry nhiều tầng không có budget:** số lần gọi downstream có thể tăng theo cấp số nhân.
- **Dùng Fire-and-Forget cho thao tác cần xác nhận:** client không có response nghiệp vụ để biết kết quả.
- **Không có cơ chế xử lý IN_PROGRESS:** hai request trùng có thể cùng thực hiện hoặc request thứ hai trả kết quả không rõ ràng.
- **Coi compensation là rollback:** side effect ngoài hệ thống có thể không thể đảo ngược hoàn toàn.

## 15. Checklist thiết kế

- [ ] Đã xác định side effect nghiệp vụ nào không được phép lặp.
- [ ] Đã xác định thao tác nào idempotent theo trạng thái cuối.
- [ ] Command có idempotency key ổn định qua các lần retry.
- [ ] Key được ràng buộc với fingerprint của request.
- [ ] Deduplication được lưu bền vững và dùng chung giữa các instance nếu cần.
- [ ] Transaction bao trùm bản ghi deduplication và thay đổi nghiệp vụ trong phạm vi database.
- [ ] Side effect ngoài database dùng downstream key, outbox, state machine hoặc reconciliation.
- [ ] Consumer có inbox/deduplication cho message có thể redeliver.
- [ ] Retry có phân loại lỗi, giới hạn, backoff, jitter và deadline.
- [ ] Timeout được xem là kết quả chưa rõ khi request có thể đã tới server.
- [ ] Fire-and-Forget không bị dùng như acknowledgement nghiệp vụ.
- [ ] Có kiểm thử duplicate, concurrent requests, crash, lost response và multi-instance.

## Kết luận

Trong hệ thống messaging, retry là cần thiết để phục hồi sau lỗi mạng và lỗi tạm thời, nhưng retry có thể gửi lại một thao tác mà server đã thực hiện. Tính idempotent bảo đảm các lần lặp của cùng thao tác không nhân đôi hiệu ứng. Với side effect quan trọng, hãy kết hợp idempotency key ổn định, fingerprint, lưu kết quả bền vững, transaction và inbox/outbox. RSocket interaction model và Reactive Streams backpressure hỗ trợ trao đổi dữ liệu, còn tính đúng đắn khi xử lý trùng phải được thiết kế ở tầng nghiệp vụ.

## Tài liệu tham khảo

- [Spring Framework Reference - RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Reference - Messaging](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html)
- [Spring Framework Reference - Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [RSocket Protocol](https://rsocket.io/about/protocol/)
- [Reactive Streams Specification](https://www.reactive-streams.org/)
- [Project Reactor Reference - Error Handling and Retry](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
