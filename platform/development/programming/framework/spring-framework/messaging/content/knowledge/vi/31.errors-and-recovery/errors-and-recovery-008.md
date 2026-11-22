# Thiết kế xử lý khi một phần trao đổi đã thành công

## Mục tiêu

Trong hệ thống messaging, một thao tác có thể gồm nhiều bước hoặc nhiều mục dữ liệu. Một số bước đã được xử lý thành công trước khi bước tiếp theo thất bại, client mất kết nối hoặc hết thời gian chờ. Bài học này trình bày cách thiết kế hợp đồng request/response, lưu kết quả từng phần, retry an toàn và khôi phục trạng thái trong Spring RSocket.

Sau bài này, bạn có thể:

- Phân biệt lỗi toàn bộ request với kết quả nghiệp vụ thành công một phần.
- Chọn Request-Response, Request-Stream hoặc Channel theo yêu cầu xác nhận.
- Thiết kế kết quả theo từng mục, operation ID và idempotency key.
- Chọn ranh giới transaction phù hợp với chính sách all-or-nothing hoặc partial success.
- Phục hồi sau timeout, mất kết nối, cancellation và lỗi giữa chừng.
- Dùng Reactor và Spring RSocket để trả kết quả từng phần có thể kiểm tra lại.

Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Messaging và RSocket. Các interface repository trong ví dụ là hợp đồng để triển khai bằng JDBC, JPA hoặc R2DBC tùy ứng dụng.

## 1. Vì sao xuất hiện trạng thái thành công một phần?

Giả sử client gửi một lệnh đặt trước 100 sản phẩm. Server xử lý lần lượt:

1. Kiểm tra sản phẩm A và giữ chỗ thành công.
2. Kiểm tra sản phẩm B và giữ chỗ thành công.
3. Sản phẩm C hết hàng.
4. Trong lúc xử lý sản phẩm D, kết nối bị gián đoạn.

Tại thời điểm kết nối mất, hai thao tác đầu có thể đã commit vào database. Client có thể chỉ nhìn thấy timeout hoặc lỗi transport. Nó không thể kết luận rằng toàn bộ batch chưa được xử lý.

Tình huống tương tự xuất hiện khi:

- Một request gọi nhiều dịch vụ hoặc nhiều kho dữ liệu.
- Server phát một luồng kết quả, đã gửi một số payload rồi gặp lỗi.
- Server đã commit nghiệp vụ nhưng response bị mất trên mạng.
- Client hủy subscription hoặc timeout trong khi server vẫn đang xử lý.
- Một workflow gồm nhiều bước có thể thành công hoặc thất bại độc lập.

Cần tách ba khái niệm:

- **Kết quả nghiệp vụ:** một mục dữ liệu đã được chấp nhận, từ chối hoặc xử lý lỗi.
- **Kết quả truyền tải:** client đã nhận được payload, lỗi hoặc tín hiệu kết thúc của stream.
- **Trạng thái bền vững:** kết quả đã được ghi nhận trong nơi lưu trữ đáng tin cậy và có thể truy vấn sau khi mất kết nối.

Một payload đã được server tạo ra chưa chắc client đã nhận. Một response bị mất cũng không chứng minh nghiệp vụ chưa commit. Thiết kế tốt phải cho phép tra cứu trạng thái bền vững sau khi kết nối không còn đủ thông tin.

## 2. Hiểu ngữ nghĩa của từng kiểu trao đổi RSocket

RSocket có bốn kiểu tương tác chính. Lựa chọn kiểu request ảnh hưởng trực tiếp đến cách biểu diễn partial success.

| Kiểu tương tác | Ngữ nghĩa kết quả | Khi phù hợp |
|---|---|---|
| Request-Response | Một request nhận một response payload hoặc lỗi. | Một thao tác có kết quả tổng hợp, kể cả khi từng mục có trạng thái khác nhau. |
| Request-Stream | Một request tạo ra nhiều response payload. | Server phát nhiều kết quả hoặc sự kiện theo thời gian. |
| Channel | Hai phía trao đổi luồng payload theo cả hai chiều. | Client gửi nhiều mục và server trả xác nhận tương ứng trong khi trao đổi vẫn tiếp tục. |
| Fire-and-Forget | Client không nhận response payload nghiệp vụ. | Chỉ dùng khi không cần xác nhận từng mục qua request đó và có cơ chế theo dõi riêng. |

### 2.1. Request-Response không có kết quả từng phần tự động

Request-Response chỉ trả về một payload. Payload đó có thể là một DTO tổng hợp chứa kết quả của nhiều mục:

- Mục A: thành công.
- Mục B: thành công.
- Mục C: bị từ chối do hết hàng.
- Mục D: chưa xử lý.

Đây là một response hợp lệ nếu server đã xử lý xong phần việc có thể quyết định. Lỗi nghiệp vụ dự kiến của từng mục nên được biểu diễn trong DTO. Lỗi hệ thống khiến server không thể tạo kết quả tổng hợp có thể kết thúc request bằng error.

Một điểm quan trọng: nếu server commit A và B rồi gặp lỗi hạ tầng trước khi tạo response, client nhận error nhưng A và B vẫn có thể đã thành công. Vì vậy, với batch có side effect, phải lưu trạng thái theo operation ID để client truy vấn lại.

### 2.2. Stream có thể phát kết quả rồi mới lỗi

Request-Stream và Channel có thể phát nhiều payload. Ví dụ server gửi xác nhận A, B, C rồi stream kết thúc bằng lỗi.

Client đã nhận A, B, C có thể giữ các kết quả đó. Những mục chưa nhận xác nhận vẫn ở trạng thái chưa rõ cho đến khi tra cứu server. Không nên suy luận rằng các mục chưa nhận được payload chắc chắn chưa được xử lý.

Mỗi payload nên chứa định danh ổn định như operation ID, item ID và sequence number. Điều đó giúp client ghép kết quả với yêu cầu ban đầu và phát hiện mục nào còn thiếu.

### 2.3. Fire-and-Forget không thích hợp khi cần xác nhận

Fire-and-Forget không cung cấp response payload để xác nhận nghiệp vụ. Nó không phải lựa chọn phù hợp cho thao tác mà client cần biết chính xác từng mục đã thành công hay chưa.

Nếu vẫn cần gửi lệnh bất đồng bộ, hãy trả operation ID qua một request khác hoặc cung cấp endpoint truy vấn trạng thái, event stream hay notification channel. Client cần biết cách lấy kết quả cuối cùng.

### 2.4. Resume không thay thế xác nhận nghiệp vụ

Session resumption có thể phục hồi một phiên và các stream trong giới hạn giao thức, nếu hai phía hỗ trợ và cấu hình tương thích. Nó không tạo transaction xuyên database, không tự lưu kết quả nghiệp vụ và không đảm bảo side effect chỉ xảy ra một lần.

Vì thế, dù dùng resume, ứng dụng vẫn cần operation ID, idempotency key, lưu trạng thái và cơ chế tra cứu kết quả. Reconnect hoặc resume giải quyết kết nối; idempotency và transaction giải quyết tính đúng đắn của nghiệp vụ.

## 3. Thiết kế hợp đồng kết quả rõ ràng

Trước khi viết handler, xác định đơn vị nào có thể thành công độc lập. Với một batch, kết quả nên chứa trạng thái tổng thể và trạng thái từng mục.

Một hợp đồng tối thiểu:

~~~json
{
  "operationId": "op-2026-00042",
  "state": "PARTIAL_SUCCESS",
  "items": [
    {
      "itemId": "line-1",
      "status": "SUCCEEDED",
      "message": "Reserved"
    },
    {
      "itemId": "line-2",
      "status": "REJECTED",
      "message": "Insufficient stock"
    },
    {
      "itemId": "line-3",
      "status": "RETRYABLE_FAILURE",
      "message": "Inventory service unavailable"
    }
  ]
}
~~~

Các trường nên có:

- **operationId:** định danh duy nhất của toàn bộ lệnh, được giữ nguyên qua các lần truy vấn và retry.
- **itemId:** định danh ổn định của mục trong operation.
- **idempotencyKey:** khóa nhận diện thao tác nghiệp vụ cho mục đó.
- **status:** trạng thái được định nghĩa trong hợp đồng API.
- **message/code:** lý do có thể hiển thị hoặc xử lý bằng máy; tránh đưa stack trace hay dữ liệu bí mật vào response.
- **sequence/version:** số thứ tự hoặc phiên bản nếu kết quả được phát thành stream và có thể cập nhật.
- **updatedAt:** thời điểm trạng thái được ghi nhận nếu client cần hiển thị tiến độ.

Có thể chuẩn hóa trạng thái:

| Trạng thái | Ý nghĩa | Có nên tự retry? |
|---|---|---|
| SUCCEEDED | Nghiệp vụ đã commit thành công. | Không. |
| REJECTED | Nghiệp vụ từ chối theo quy tắc, ví dụ thiếu hàng hoặc dữ liệu không hợp lệ. | Không, trừ khi dữ liệu đầu vào hoặc điều kiện nghiệp vụ thay đổi có chủ đích. |
| RETRYABLE_FAILURE | Chưa hoàn tất do lỗi tạm thời và có thể thử lại. | Có, sau khi kiểm tra idempotency và giới hạn retry. |
| PROCESSING | Server đã nhận và đang xử lý. | Không gửi lại thao tác mới; truy vấn trạng thái hoặc chờ. |
| UNKNOWN | Chưa thể xác định kết quả cuối cùng. | Tra cứu trước khi retry. |

Trạng thái tổng thể có thể là COMPLETED, PARTIAL_SUCCESS, FAILED hoặc PROCESSING. Định nghĩa quy tắc tính trạng thái này trong API. Ví dụ, PARTIAL_SUCCESS nghĩa là có ít nhất một mục SUCCEEDED và ít nhất một mục không thành công; FAILED có thể nghĩa là không có mục nào thành công. Nếu hệ thống cần phân biệt từ chối nghiệp vụ với lỗi kỹ thuật, hãy giữ chúng ở trạng thái từng mục thay vì gộp vào một boolean.

Đừng dùng một trường boolean success cho cả batch nếu nó che giấu kết quả từng mục. Client cần biết chính xác phần nào đã hoàn tất để tránh xử lý lặp.

## 4. Chọn ranh giới transaction

Quyết định quan trọng nhất là các mục trong batch có bắt buộc thành công cùng nhau hay không.

### 4.1. All-or-nothing

Dùng một transaction khi nghiệp vụ yêu cầu toàn bộ thay đổi cùng commit hoặc cùng rollback, ví dụ chuyển tiền giữa hai tài khoản trong cùng database.

Luồng:

1. Validate toàn bộ đầu vào.
2. Mở transaction.
3. Thực hiện mọi thay đổi.
4. Ghi kết quả operation.
5. Commit nếu tất cả thành công.
6. Rollback nếu bất kỳ bước bắt buộc nào thất bại.

Response chỉ được gửi sau khi transaction commit. Nếu client mất response sau commit, client vẫn cần idempotency key hoặc operation status để biết kết quả đã được ghi nhận.

Không mở một transaction database dài trong lúc chờ mạng hoặc gọi nhiều dịch vụ từ xa. Transaction dài làm giữ lock và tăng nguy cơ nghẽn.

### 4.2. Partial success

Cho phép từng mục commit độc lập khi nghiệp vụ chấp nhận một số mục thành công và một số mục thất bại.

Ví dụ: nhập 100 bản ghi, mỗi bản ghi có thể được chấp nhận độc lập. Có thể xử lý từng mục trong transaction riêng:

1. Đọc hoặc tạo bản ghi idempotency cho item.
2. Nếu đã có kết quả cuối cùng, trả lại kết quả đã lưu.
3. Nếu chưa có, thực hiện side effect.
4. Ghi kết quả item và thay đổi nghiệp vụ trong cùng transaction.
5. Commit.
6. Chuyển sang mục tiếp theo.

Nếu mục thứ 50 gặp lỗi hạ tầng, kết quả 1–49 vẫn được lưu. Client truy vấn operation để biết những mục đã hoàn thành và tiếp tục từ các mục chưa hoàn tất.

### 4.3. Nhiều dịch vụ hoặc nhiều hệ thống

Một transaction ACID thường không thể bao phủ nhiều dịch vụ độc lập. Khi workflow gồm nhiều bước như giữ hàng, thu tiền và tạo vận đơn, hãy cân nhắc Saga:

- Mỗi bước thực hiện một transaction cục bộ.
- Ghi lại trạng thái và kết quả của từng bước.
- Nếu bước sau thất bại, chạy hành động bù trừ phù hợp với nghiệp vụ.
- Lưu cả trạng thái của hành động bù trừ; bù trừ cũng có thể thất bại và cần retry.
- Cho phép truy vấn operation để biết workflow đang chạy, hoàn tất, hoàn tất một phần hay cần can thiệp.

Compensation không phải rollback thời gian. Ví dụ, hoàn tiền là một thao tác nghiệp vụ mới, có thể phát sinh phí hoặc cần thời gian xử lý. Hãy thiết kế trạng thái rõ ràng thay vì giả định mọi side effect có thể đảo ngược hoàn toàn.

## 5. Idempotency: nền tảng của retry an toàn

Một request có thể được server xử lý thành công nhưng response bị mất. Nếu client gửi lại, server cần nhận ra đó là cùng một thao tác.

**Idempotency** nghĩa là gửi cùng một lệnh với cùng khóa nhận diện nhiều lần không làm side effect xảy ra nhiều lần. Nó không có nghĩa mọi lần gọi đều phải trả cùng một frame; nó có nghĩa trạng thái nghiệp vụ không bị nhân đôi và server có thể trả lại kết quả đã lưu.

### 5.1. Tạo khóa ổn định

Dùng operation ID cho batch và idempotency key cho từng item. Không tạo khóa mới mỗi lần retry.

Ví dụ:

- operationId: order-8451-reservation
- itemId: line-01
- idempotencyKey: order-8451-line-01-reserve-v1

Nếu cùng khóa được gửi với payload khác, server nên từ chối vì đây là xung đột, không nên coi là retry hợp lệ. Có thể lưu hash của payload đã chuẩn hóa để phát hiện trường hợp này.

### 5.2. Lưu khóa và side effect nguyên tử

Một thiết kế phổ biến có bảng idempotency:

| Cột | Mục đích |
|---|---|
| idempotency_key | Unique key cho thao tác. |
| operation_id | Nhóm các mục trong cùng workflow. |
| request_hash | Phát hiện cùng key nhưng payload khác. |
| status | PROCESSING, SUCCEEDED, REJECTED hoặc RETRYABLE_FAILURE. |
| result_payload | Kết quả có thể trả lại cho client. |
| updated_at | Thời điểm cập nhật để phát hiện tác vụ treo. |

Cập nhật side effect và kết quả idempotency trong cùng transaction database. Nếu chỉ lưu khóa sau khi side effect đã commit, server có thể crash giữa hai bước và xử lý lặp khi retry.

Cần unique constraint hoặc cơ chế khóa để hai request đồng thời dùng cùng key không cùng thực hiện side effect. Nếu request thứ hai gặp bản ghi PROCESSING, nó có thể chờ trong giới hạn, hoặc trả trạng thái PROCESSING để client truy vấn lại.

Với nhiều dịch vụ, dùng inbox/outbox hoặc cơ chế deduplication tương đương ở từng ranh giới dịch vụ. Không giả định một khóa trong database của service A tự bảo vệ side effect ở service B.

## 6. Xây dựng handler Spring RSocket cho batch

Ví dụ dưới đây dùng Request-Response để trả một kết quả tổng hợp. Mỗi item được xử lý idempotently và có kết quả riêng.

### 6.1. DTO

~~~java
package com.example.messaging;

import java.util.List;

public record ItemCommand(
    String itemId,
    String idempotencyKey,
    String sku,
    int quantity
) {}

public record ChannelItemCommand(
    String operationId,
    ItemCommand item
) {}

public record BatchCommand(
    String operationId,
    List<ItemCommand> items
) {}

public enum ItemStatus {
    SUCCEEDED,
    REJECTED,
    RETRYABLE_FAILURE
}

public record ItemOutcome(
    String itemId,
    ItemStatus status,
    String code,
    String message
) {}

public record BatchResult(
    String operationId,
    String state,
    List<ItemOutcome> items
) {}

public record OperationStatusQuery(String operationId) {}

public record BatchStatus(
    String operationId,
    String state,
    List<ItemOutcome> items
) {}
~~~

Trong production, nên validate operationId, itemId, idempotencyKey, SKU và quantity trước khi thực hiện side effect. Giới hạn kích thước batch để tránh một request chiếm quá nhiều bộ nhớ hoặc thời gian xử lý.

### 6.2. Service contract

~~~java
package com.example.messaging;

import reactor.core.publisher.Mono;

public interface BatchReservationService {

    Mono<BatchResult> reserve(BatchCommand command);

    Mono<BatchStatus> findStatus(String operationId);
}
~~~

Contract reserve phải bảo đảm kết quả từng item được lưu bền vững cùng side effect tương ứng. findStatus đọc trạng thái đã lưu theo operation ID. Đây là phần cần triển khai bằng transaction và idempotency store; chỉ giữ kết quả trong bộ nhớ của controller không đủ để phục hồi sau khi process khởi động lại.

### 6.3. RSocket controller

~~~java
package com.example.messaging;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class BatchReservationController {

    private final BatchReservationService service;

    public BatchReservationController(BatchReservationService service) {
        this.service = service;
    }

    @MessageMapping("inventory.reserve-batch")
    public Mono<BatchResult> reserve(
        @Payload BatchCommand command
    ) {
        return service.reserve(command);
    }

    @MessageMapping("inventory.operation-status")
    public Mono<BatchStatus> status(
        @Payload OperationStatusQuery query
    ) {
        return service.findStatus(query.operationId());
    }
}
~~~

Client gọi Request-Response bằng RSocketRequester:

~~~java
Mono<BatchResult> result = requester
    .route("inventory.reserve-batch")
    .data(command)
    .retrieveMono(BatchResult.class);
~~~

Khi request trả về bình thường, client nhận kết quả tổng hợp. Nếu request bị timeout hoặc lỗi transport, client dùng operation ID đã tạo từ trước để truy vấn:

~~~java
Mono<BatchStatus> status = requester
    .route("inventory.operation-status")
    .data(new OperationStatusQuery(command.operationId()))
    .retrieveMono(BatchStatus.class);
~~~

Nếu status vẫn PROCESSING, client có thể chờ và truy vấn lại theo backoff. Nếu status cho thấy một số item chưa hoàn tất, client chỉ gửi lại các item phù hợp với chính sách retry và giữ nguyên idempotency key. Không tạo một operation ID mới cho cùng một nghiệp vụ đang cần phục hồi.

## 7. Điều phối nhiều mục bằng Reactor

Một batch có thể được xử lý tuần tự hoặc đồng thời. Chọn operator dựa trên phụ thuộc nghiệp vụ và giới hạn tài nguyên.

### 7.1. Xử lý tuần tự với concatMap

~~~java
return Flux.fromIterable(command.items())
    .concatMap(item ->
        itemService.processIdempotently(
            command.operationId(),
            item
        )
    )
    .collectList()
    .map(outcomes -> new BatchResult(
        command.operationId(),
        summarize(outcomes),
        outcomes
    ));
~~~

concatMap đợi publisher của mục hiện tại hoàn tất rồi mới xử lý mục kế tiếp. Nó giữ thứ tự kết quả và phù hợp khi các mục phụ thuộc nhau hoặc cần giới hạn tải. Nếu một publisher phát lỗi kỹ thuật không được xử lý bên trong, chuỗi sẽ lỗi và không xử lý tiếp các mục sau.

### 7.2. Xử lý đồng thời có giới hạn với flatMap

~~~java
return Flux.fromIterable(command.items())
    .flatMap(
        item -> itemService.processIdempotently(
            command.operationId(),
            item
        ),
        8
    )
    .collectList()
    .map(outcomes -> new BatchResult(
        command.operationId(),
        summarize(outcomes),
        outcomes
    ));
~~~

Tham số 8 giới hạn số publisher xử lý đồng thời. flatMap có thể phát kết quả không theo thứ tự đầu vào. Nếu cần giữ thứ tự trong khi vẫn xử lý đồng thời, cân nhắc flatMapSequential, đồng thời hiểu rằng nó có thể phải giữ kết quả hoàn thành sớm trong bộ đệm để chờ mục trước đó.

Không đặt concurrency quá cao. Nó có thể làm cạn connection pool, gây quá tải dịch vụ downstream hoặc tăng số transaction tranh chấp.

### 7.3. Chỉ chuyển lỗi nghiệp vụ dự kiến thành kết quả từng mục

Có thể chuyển một lỗi nghiệp vụ đã biết thành ItemOutcome để tiếp tục batch. Phạm vi xử lý lỗi phải nằm bên trong từng item:

~~~java
return itemService.reserve(item)
    .thenReturn(new ItemOutcome(
        item.itemId(),
        ItemStatus.SUCCEEDED,
        "RESERVED",
        "Reservation committed"
    ))
    .onErrorResume(
        InsufficientStockException.class,
        error -> Mono.just(new ItemOutcome(
            item.itemId(),
            ItemStatus.REJECTED,
            "INSUFFICIENT_STOCK",
            "Not enough stock"
        ))
    );
~~~

Đây là mẫu minh họa. Trong hệ thống thật, kết quả REJECTED cũng cần được ghi bền vững theo idempotency key nếu client có thể retry hoặc truy vấn sau đó. Lỗi kết nối database, timeout downstream hoặc lỗi lập trình không nên bị biến thành REJECTED. Những lỗi này cần được phân loại là lỗi kỹ thuật, ghi log và xử lý theo chính sách phục hồi.

Không đặt một onErrorResume bao quanh toàn bộ batch để biến mọi lỗi thành danh sách rỗng hoặc một response thành công giả. Cách đó che giấu những mục đã commit và làm client mất khả năng phục hồi chính xác.

## 8. Dùng Channel khi cần xác nhận theo từng mục

Nếu client gửi một luồng lệnh và muốn nhận kết quả từng mục trong lúc server đang xử lý, Request-Channel là lựa chọn tự nhiên.

Handler Spring có thể nhận một Flux lệnh và trả về Flux kết quả:

~~~java
@MessageMapping("inventory.reserve-channel")
public Flux<ItemOutcome> reserveChannel(
    @Payload Flux<ChannelItemCommand> commands
) {
    return commands.concatMap(command ->
        itemService.processIdempotently(
            command.operationId(),
            command.item()
        )
    );
}
~~~

Trong ví dụ này, mỗi ChannelItemCommand mang operationId của batch và một ItemCommand có itemId cùng idempotencyKey. Server chỉ phát ItemOutcome sau khi đã lưu kết quả tương ứng bền vững. Mỗi outcome đóng vai trò xác nhận ở cấp ứng dụng.

Nếu channel kết thúc sau khi đã phát một số outcome rồi lỗi:

1. Client giữ lại các outcome đã nhận và đối chiếu theo itemId.
2. Client truy vấn trạng thái operation để biết kết quả bền vững của các mục còn lại.
3. Client chỉ gửi lại mục chưa hoàn tất hoặc có trạng thái retryable.
4. Client giữ nguyên idempotency key cho cùng thao tác nghiệp vụ.

Không coi việc đã ghi payload vào socket là xác nhận nghiệp vụ. Điểm xác nhận nên là kết quả đã commit và được lưu trong hệ thống.

Với channel hai chiều, hãy xác định rõ client có thể gửi thêm lệnh khi server đang xử lý hay không, giới hạn số lệnh đang chờ, cách hủy và cách kết thúc stream. Backpressure giúp điều tiết tốc độ, nhưng không thay thế giới hạn batch, giới hạn bộ nhớ hay chính sách lưu kết quả.

## 9. Retry và phục hồi sau lỗi

Retry là một quyết định nghiệp vụ, không chỉ là một operator trong Reactor.

### 9.1. Phân loại lỗi trước khi retry

| Nhóm lỗi | Ví dụ | Hành động |
|---|---|---|
| Validation | Thiếu itemId, quantity âm. | Từ chối; yêu cầu sửa dữ liệu. |
| Business rejection | Hết hàng, không đủ hạn mức. | Ghi REJECTED; không tự retry. |
| Transient infrastructure | Database tạm unavailable, gateway timeout. | Tra cứu trạng thái rồi retry có giới hạn nếu an toàn. |
| Permanent infrastructure/configuration | Sai credentials, route không tồn tại. | Dừng retry tự động; sửa cấu hình hoặc chuyển vận hành xử lý. |
| Unknown outcome | Timeout sau khi server có thể đã commit. | Truy vấn operation trước; không gửi lệnh mới với key mới. |

### 9.2. Quy trình phục hồi

Khi client nhận timeout hoặc mất kết nối:

1. Giữ nguyên operation ID và idempotency key đã gửi.
2. Kết nối lại theo chính sách transport.
3. Gọi route truy vấn trạng thái operation.
4. Đọc trạng thái từng item đã được lưu.
5. Giữ nguyên các mục SUCCEEDED và REJECTED.
6. Thử lại các mục RETRYABLE_FAILURE hoặc chưa có kết quả sau khi xác minh chúng chưa được xử lý.
7. Dùng backoff có giới hạn, jitter và deadline phù hợp.
8. Nếu trạng thái vẫn PROCESSING quá lâu, đưa vào quy trình reconciliation hoặc cảnh báo vận hành.

Không retry toàn bộ batch theo cách tạo operation mới. Nếu server đã commit một phần, thao tác có thể bị lặp.

### 9.3. Retry với Reactor

Ví dụ retry một request chỉ khi lỗi thuộc nhóm tạm thời:

~~~java
return requester
    .route("inventory.operation-status")
    .data(query)
    .retrieveMono(BatchStatus.class)
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(300))
            .maxBackoff(Duration.ofSeconds(5))
            .filter(this::isTransientTransportError)
    );
~~~

Cần import reactor.util.retry.Retry và java.time.Duration. isTransientTransportError là logic phân loại lỗi do ứng dụng định nghĩa. Ví dụ chỉ minh họa retry việc đọc trạng thái; retry một lệnh ghi cần có idempotency và phải tuân thủ cùng nguyên tắc.

Dùng giới hạn retry, backoff, jitter và deadline. Tránh retry liên tục khi server đang quá tải vì điều đó có thể làm tình trạng xấu hơn. Không retry lỗi validation hoặc business rejection.

## 10. Cancellation, timeout và shutdown

Một client hủy subscription không đồng nghĩa server đã rollback. Tùy thời điểm và cách triển khai, server có thể đã commit một hoặc nhiều side effect trước khi nhận tín hiệu cancellation.

Với tác vụ ngắn, có thể liên kết cancellation với việc dừng các bước chưa bắt đầu. Tuy nhiên, các side effect đã commit cần giữ lại kết quả. Với tác vụ dài, nên tách operation khỏi vòng đời connection:

- Client gửi lệnh tạo operation.
- Server lưu operation và trả operation ID.
- Worker xử lý độc lập với connection.
- Client theo dõi qua status request, Request-Stream hoặc notification.
- Client có thể ngắt kết nối và quay lại truy vấn sau.

Đặt timeout cho từng bước và toàn bộ workflow. Khi timeout xảy ra, cập nhật trạng thái phù hợp như UNKNOWN hoặc PROCESSING; không tự đánh dấu FAILED nếu chưa biết các side effect trước đó.

Khi shutdown, ngừng nhận operation mới, hoàn tất hoặc lưu checkpoint cho các bước đang chạy, rồi giải phóng tài nguyên. Với tác vụ phải tiếp tục sau restart, checkpoint và kết quả phải được lưu bền vững; không chỉ nằm trong bộ nhớ của một Flux đang subscribe.

## 11. Quan sát và reconciliation

Để xử lý partial success trong production, cần quan sát được tiến trình và có khả năng sửa trạng thái không nhất quán.

Nên ghi log có cấu trúc với:

- operationId và itemId.
- idempotencyKey hoặc một dạng hash an toàn.
- trạng thái trước và sau.
- số lần thử và thời gian xử lý.
- mã lỗi đã chuẩn hóa.
- correlation ID / trace ID để nối log giữa các dịch vụ.

Không ghi token, mật khẩu, dữ liệu cá nhân hoặc payload nhạy cảm vào log.

Các chỉ số hữu ích:

- Số operation COMPLETED, PARTIAL_SUCCESS, FAILED và PROCESSING.
- Tỷ lệ item thành công, bị từ chối và lỗi tạm thời.
- Số operation PROCESSING quá thời hạn.
- Số lần retry trên mỗi operation.
- Độ trễ từ lúc nhận lệnh đến lúc hoàn tất.
- Số operation cần reconciliation hoặc compensation.

Một tiến trình reconciliation có thể tìm các item ở trạng thái PROCESSING quá lâu, đối chiếu với trạng thái nghiệp vụ thật và cập nhật lại kết quả. Việc sửa trạng thái phải idempotent và có audit trail. Không tự động đánh dấu thành công chỉ vì timeout đã hết.

## 12. Lỗi thiết kế thường gặp

| Cách làm sai | Hậu quả | Cách sửa |
|---|---|---|
| Trả một boolean cho cả batch. | Không biết mục nào đã thành công. | Trả trạng thái từng item và operation ID. |
| Coi timeout là chưa xử lý. | Gửi lại side effect đã commit. | Truy vấn trạng thái và dùng idempotency key. |
| Retry toàn bộ batch với key mới. | Tạo giao dịch trùng lặp. | Giữ key cũ và chỉ retry phần chưa hoàn tất. |
| Biến mọi exception thành REJECTED. | Lỗi hạ tầng bị che giấu như lỗi nghiệp vụ. | Phân loại lỗi và chỉ bắt lỗi dự kiến. |
| Chỉ lưu kết quả trong bộ nhớ. | Mất khả năng phục hồi sau restart. | Lưu operation/item state trong database hoặc store bền vững. |
| Gửi xác nhận trước khi commit. | Client tin một thao tác chưa được lưu bền vững. | Phát outcome sau commit. |
| Dùng Fire-and-Forget khi cần kết quả. | Client không biết trạng thái nghiệp vụ. | Dùng Request-Response/Channel hoặc status API. |
| Dùng resume như đảm bảo exactly-once. | Side effect vẫn có thể lặp. | Kết hợp resume với idempotency và transaction. |
| Mở transaction dài qua nhiều lời gọi mạng. | Giữ lock, tăng timeout và khó phục hồi. | Transaction cục bộ ngắn và Saga nếu cần. |
| Hủy stream rồi xóa trạng thái operation. | Không thể biết phần đã commit. | Lưu checkpoint và trạng thái độc lập với stream. |

## 13. Checklist trước khi triển khai

- [ ] Đã xác định batch là all-or-nothing hay cho phép partial success.
- [ ] Có operation ID ổn định cho toàn bộ workflow.
- [ ] Mỗi item có item ID và idempotency key ổn định.
- [ ] Cùng key nhưng payload khác được phát hiện và từ chối.
- [ ] Side effect và kết quả idempotency được commit nguyên tử.
- [ ] DTO phân biệt SUCCEEDED, REJECTED, RETRYABLE_FAILURE và PROCESSING.
- [ ] Client có route truy vấn trạng thái sau timeout hoặc mất kết nối.
- [ ] Retry có giới hạn và chỉ áp dụng cho lỗi tạm thời.
- [ ] Không retry thao tác có side effect nếu chưa có bảo vệ idempotency.
- [ ] Stream phát xác nhận sau khi kết quả đã bền vững.
- [ ] Cancellation không xóa các kết quả đã commit.
- [ ] Operation dài có checkpoint, reconciliation và chính sách shutdown.
- [ ] Log và metric cho phép truy vết operation/item mà không lộ dữ liệu nhạy cảm.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): các kiểu tương tác, RSocketRequester và annotated responders.
- [Spring Framework Reference — RSocket Messaging](https://docs.spring.io/spring-framework/reference/rsocket.html#rsocket-annotated-responders): ánh xạ route và handler reactive.
- [RSocket Protocol](https://rsocket.io/about/protocol/): request frames, stream termination, error và session resumption.
- [RSocket Java](https://github.com/rsocket/rsocket-java): triển khai connector, transport và lifecycle.
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/): Flux, Mono, backpressure, cancellation và retry.
- [Reactive Streams](https://www.reactive-streams.org/): quy tắc truyền dữ liệu bất đồng bộ có backpressure.
