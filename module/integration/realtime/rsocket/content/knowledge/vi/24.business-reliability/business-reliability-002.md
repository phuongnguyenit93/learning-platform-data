# Các tình huống không biết chắc yêu cầu đã được xử lý hay chưa

Trong giao tiếp realtime, client có thể gửi một lệnh qua RSocket nhưng không nhận được kết quả cuối cùng. Kết nối có thể bị ngắt ngay sau khi server đã ghi dữ liệu, request có thể timeout trong lúc server vẫn đang xử lý, hoặc client có thể hủy subscription khi side effect đã xảy ra. Ở phía client, những tình huống này có cùng một biểu hiện: không biết chắc yêu cầu đã được thực hiện hay chưa.

Đây là vấn đề về độ tin cậy nghiệp vụ, không chỉ là lỗi transport. Với `INTEGRATION_REALTIME_RSOCKET`, cần phân biệt trạng thái của frame và kết nối với trạng thái của lệnh nghiệp vụ. Bài viết này trình bày cách nhận diện kết quả không chắc chắn, thiết kế idempotency, lưu dấu yêu cầu, đối soát trạng thái và retry an toàn cho Request-Response, Fire-and-Forget, Request-Stream và Request-Channel.

## 1. Vì sao client có thể không biết yêu cầu đã được xử lý?

Giả sử client gửi lệnh mở khóa thiết bị. Server nhận lệnh, ghi nhận vào database và gửi response. Nếu kết nối bị đứt sau khi transaction commit nhưng trước khi response tới client, client chỉ thấy timeout hoặc connection error. Server đã thực hiện lệnh, nhưng client không nhận được bằng chứng.

```text
Client                         Server                       Database
  |                              |                              |
  |---- REQUEST ---------------->|                              |
  |                              |---- ghi thay đổi ------------>|
  |                              |<--- COMMIT thành công --------|
  |                              |                              |
  X  kết nối đứt                 |                              |
  |                              |---- RESPONSE (không tới)      |
  |                              |                              |
  |  Client thấy timeout         |  Server đã hoàn tất          |
```

Một tình huống khác là kết nối đứt trước khi server nhận request. Client cũng thấy timeout, nhưng lần này lệnh chưa được xử lý. Hai tình huống khác nhau ở phía server nhưng có thể giống hệt nhau ở phía client.

Do đó, **timeout không đồng nghĩa với thất bại nghiệp vụ**. Nó chỉ nói rằng client không nhận được kết quả trong khoảng thời gian cho phép. Khi không có bằng chứng đủ chắc chắn, client phải xem kết quả là *chưa xác định* (unknown outcome), sau đó đối soát hoặc gửi lại theo một quy tắc an toàn.

## 2. Phân biệt trạng thái transport và trạng thái nghiệp vụ

Một request có nhiều mốc khác nhau:

1. Client tạo command và bắt đầu gửi.
2. Transport gửi frame tới peer.
3. Server nhận và giải mã payload.
4. Handler xác thực, kiểm tra và chấp nhận command.
5. Database commit hoặc hệ thống ngoài thực hiện side effect.
6. Server tạo response/receipt.
7. Client nhận và xử lý response.

Thành công ở một mốc không chứng minh các mốc sau đã thành công. Ví dụ, `Mono<Void>` từ `RSocketRequester.send()` hoàn tất không xác nhận Fire-and-Forget đã được lưu bền vững ở server. Tương tự, client gửi Request-Response nhưng bị timeout không chứng minh server chưa commit.

Nên biểu diễn riêng trạng thái ở client và trạng thái xử lý ở server:

| Góc nhìn | Trạng thái ví dụ | Ý nghĩa |
|---|---|---|
| Client | `CREATED` | Đã tạo command và định danh ổn định. |
| Client | `SENT` | Đã bắt đầu gửi request. |
| Client | `OUTCOME_UNKNOWN` | Timeout/disconnect khiến chưa biết kết quả cuối. |
| Client | `CONFIRMED` | Đã nhận receipt hoặc đọc được trạng thái hoàn tất. |
| Server | `ACCEPTED` | Đã ghi nhận trách nhiệm xử lý command. |
| Server | `PROCESSING` | Worker hoặc handler đang xử lý. |
| Server | `SUCCEEDED` | Side effect nghiệp vụ đã hoàn tất. |
| Server | `REJECTED` | Command bị từ chối theo quy tắc nghiệp vụ. |
| Server | `RETRYABLE_FAILED` | Xử lý thất bại tạm thời và có thể thử lại theo chính sách. |

`OUTCOME_UNKNOWN` thường là trạng thái nhận thức của client, không nhất thiết là trạng thái đã lưu ở server. Server có thể đang `PROCESSING`, đã `SUCCEEDED` hoặc chưa từng nhận command. Không tự chuyển unknown thành failed chỉ vì hết timeout.

## 3. Bốn interaction model và mức độ chắc chắn

### 3.1. Request-Response

Request-Response cho phép server trả một response payload. Nếu server chỉ trả thành công sau khi transaction nghiệp vụ đã commit, response là bằng chứng tốt cho client. Tuy nhiên, response vẫn có thể bị mất sau commit. Client timeout không thể tự kết luận command chưa chạy.

### 3.2. Fire-and-Forget

Fire-and-Forget không có response payload nghiệp vụ. `send()` hoàn tất ở client không phải receipt từ server và không chứng minh server đã xử lý hoặc lưu dữ liệu. Mô hình này phù hợp với tín hiệu best-effort như metric hoặc telemetry có thể mất một số mẫu. Với command quan trọng, cần một cơ chế xác nhận riêng hoặc chọn Request-Response.

### 3.3. Request-Stream

Request-Stream thường mở một luồng response từ một request ban đầu. Nếu stream đứt sau một số phần tử, client cần biết đã nhận tới sequence/cursor nào. Khi đăng ký lại, server có thể phát từ đầu hoặc từ cursor tùy hợp đồng ứng dụng. Không mặc định rằng reconnect tự tiếp tục đúng phần tử tiếp theo.

### 3.4. Request-Channel

Request-Channel có dữ liệu theo cả hai hướng. Client có thể đã gửi một số command trước khi nhận được update tương ứng. Khi channel đứt, cần sequence number hoặc command ID để biết lệnh nào đã được nhận/xử lý, lệnh nào cần đối soát và lệnh nào có thể gửi lại.

| Model | Điều client biết khi tương tác hoàn tất bình thường | Điều vẫn có thể không chắc khi mất kết nối |
|---|---|---|
| Request-Response | Đã nhận một response payload. | Server có thể đã commit nhưng response bị mất. |
| Fire-and-Forget | Publisher gửi phía client hoàn tất theo API. | Không có response nghiệp vụ xác nhận server xử lý. |
| Request-Stream | Đã nhận các phần tử trước khi stream kết thúc. | Có thể thiếu phần tử cuối hoặc không biết cursor tiếp theo. |
| Request-Channel | Đã trao đổi một số payload ở hai hướng. | Không chắc command cuối cùng đã được nhận, xử lý hay update đã bị mất. |

## 4. At-most-once, at-least-once và xử lý lặp an toàn

Khi thiết kế retry, cần hiểu ba mục tiêu phổ biến:

| Cách giao nhận | Hành vi | Rủi ro |
|---|---|---|
| At-most-once | Không gửi lại khi kết quả không rõ. | Có thể mất command nếu request chưa tới server. |
| At-least-once | Gửi lại cho tới khi nhận xác nhận hoặc hết chính sách retry. | Server có thể nhận cùng command nhiều lần. |
| Effectively-once bằng idempotency | Cho phép gửi lặp nhưng server bảo đảm cùng command chỉ tạo một hiệu ứng nghiệp vụ. | Cần lưu định danh và kết quả xử lý bền vững, xử lý race và retention. |

Không nên tuyên bố hệ thống có exactly-once end-to-end chỉ vì dùng RSocket, Resume hoặc một broker. Transport có thể giúp phát lại frame theo trạng thái giao thức, nhưng không thể tự đảm bảo side effect ở database hoặc hệ thống ngoài chỉ xảy ra đúng một lần.

Trong thực tế, cách tiếp cận hữu ích là **at-least-once delivery kết hợp idempotent processing**. Client có thể gửi lại cùng command ID; server nhận diện lần lặp và trả lại trạng thái/kết quả đã lưu thay vì thực hiện side effect lần nữa.

## 5. Tạo idempotency key trước lần gửi đầu tiên

Mỗi command có tác động nghiệp vụ nên có một định danh ổn định, ví dụ `commandId` hoặc `idempotencyKey`. Client tạo ID một lần trước lần gửi đầu tiên và dùng lại chính ID đó trong mọi lần retry.

```java
public record DeviceCommand(
    String commandId,
    String deviceId,
    String action,
    Map<String, String> parameters
) {}

String commandId = UUID.randomUUID().toString();

DeviceCommand command = new DeviceCommand(
    commandId,
    deviceId,
    "UNLOCK",
    Map.of()
);
```

Nếu timeout, client gửi lại command có cùng `commandId`. Không tạo UUID mới cho mỗi lần retry, vì server sẽ xem mỗi ID mới là một command khác và có thể thực hiện side effect nhiều lần.

Idempotency key nên được định phạm vi theo principal/tenant và loại thao tác, ví dụ `(tenantId, operation, commandId)`. Không dùng một key toàn cục mà không kiểm tra quyền, vì người dùng khác có thể đoán hoặc vô tình trùng ID.

Server cũng nên tính hash của payload nghiệp vụ. Nếu cùng một key được gửi lại với payload khác, từ chối bằng lỗi conflict thay vì trả kết quả cũ cho một command có nội dung khác.

## 6. Lưu dấu command và side effect trong cùng transaction

Để chống xử lý lặp, server cần một ràng buộc duy nhất ở database. Ví dụ bảng lưu idempotency record:

```sql
CREATE TABLE command_dedup (
    tenant_id        VARCHAR(100) NOT NULL,
    operation        VARCHAR(120) NOT NULL,
    command_id       VARCHAR(80) NOT NULL,
    payload_hash     VARCHAR(128) NOT NULL,
    status           VARCHAR(32) NOT NULL,
    result_json      TEXT,
    created_at       TIMESTAMP NOT NULL,
    updated_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, operation, command_id)
);
```

Khi nhận command, server thực hiện quy trình:

1. Xác thực principal và xác định tenant từ danh tính đã xác thực.
2. Validate payload, operation và command ID.
3. Tính `payload_hash` từ biểu diễn nghiệp vụ đã chuẩn hóa.
4. Thử insert idempotency record với unique key.
5. Nếu record đã tồn tại, so sánh hash. Cùng hash thì trả trạng thái/kết quả đã lưu; khác hash thì trả conflict.
6. Nếu là command mới và side effect chỉ nằm trong cùng database, cập nhật dữ liệu nghiệp vụ và record kết quả trong cùng transaction.
7. Commit rồi mới trả response xác nhận thành công.

Với PostgreSQL, `INSERT ... ON CONFLICT DO NOTHING` có thể hỗ trợ thao tác insert-if-absent. Repository phải xử lý kết quả insert một cách nguyên tử và đọc record hiện có khi insert không thành công. Unique constraint là lớp bảo vệ quan trọng khi hai request cùng command ID đến đồng thời.

### 6.1. Ví dụ service theo hướng reactive

Đoạn code dưới đây minh họa luồng xử lý. `insertIfAbsent` cần được triển khai bằng câu lệnh có unique constraint ở database; không thay bằng thao tác `find` rồi `insert` không có bảo vệ cạnh tranh.

```java
public Mono<CommandReceipt> accept(
        String tenantId,
        DeviceCommand command) {

    String hash = commandHasher.hash(command);

    return transactionalOperator.transactional(
        dedupRepository.insertIfAbsent(
            tenantId,
            "device.command",
            command.commandId(),
            hash,
            "ACCEPTED"
        ).flatMap(inserted -> {
            if (!inserted) {
                return dedupRepository.find(
                    tenantId,
                    "device.command",
                    command.commandId()
                ).flatMap(existing -> {
                    if (!existing.payloadHash().equals(hash)) {
                        return Mono.error(new IdempotencyConflictException());
                    }
                    return Mono.just(existing.toReceipt());
                });
            }

            return deviceRepository.apply(command)
                .flatMap(result -> dedupRepository.markSucceeded(
                    tenantId,
                    command.commandId(),
                    result
                ).thenReturn(CommandReceipt.succeeded(
                    command.commandId(), result
                )));
        })
    );
}
```

Ví dụ giả định side effect `deviceRepository.apply` và idempotency record nằm trong cùng database/transaction. Nếu thao tác thành công rồi commit, nhưng response bị mất, lần retry sau đọc record `SUCCEEDED` và trả lại receipt đã lưu. Nếu transaction rollback, cả thay đổi nghiệp vụ lẫn dedup record mới đều rollback.

Nếu hai request cùng command ID đến đồng thời, unique constraint quyết định một request thắng quyền tạo record. Request còn lại phải đọc record đã được commit và kiểm tra hash. Cần xử lý trường hợp transaction cạnh tranh hoặc lỗi unique constraint theo đúng database/driver đang dùng.

## 7. Side effect bên ngoài database: dùng Transactional Outbox

Không thể bao một transaction database thông thường và một HTTP call tới thiết bị, nhà cung cấp thanh toán hoặc dịch vụ bên ngoài thành một transaction ACID duy nhất. Nếu server gọi dịch vụ ngoài rồi crash trước khi ghi kết quả, hoặc ghi kết quả trước rồi crash trước khi gọi dịch vụ ngoài, trạng thái có thể không nhất quán.

Transactional Outbox giải quyết khoảng trống giữa việc chấp nhận command và việc phát công việc cần xử lý:

```text
RSocket command
      |
      v
Database transaction
  ├─ insert idempotency record (ACCEPTED)
  └─ insert outbox event
      |
      v
     COMMIT
      |
      v
Outbox worker đọc event
      |
      v
Gọi hệ thống ngoài với cùng commandId
      |
      v
Ghi trạng thái SUCCEEDED / RETRYABLE_FAILED
```

Command được xem là đã **được chấp nhận** sau khi record và outbox cùng commit. Worker xử lý ngoài transaction request RSocket. Nếu worker gửi lại event do crash hoặc timeout, downstream cũng cần hỗ trợ idempotency key hoặc có cơ chế đối soát tương ứng.

Outbox thường được xử lý at-least-once. Cần thiết kế worker có thể đọc lại event, đánh dấu trạng thái và retry có giới hạn. Không đánh dấu event đã gửi trước khi có kết quả phù hợp; cũng không giả định timeout HTTP nghĩa là dịch vụ ngoài chưa thực hiện.

Với quy trình nhiều bước không thể rollback, ví dụ đặt hàng rồi thu tiền rồi yêu cầu vận chuyển, hãy dùng saga hoặc thao tác bù trừ. Idempotency ngăn lặp cùng một bước; compensation xử lý tình huống một bước sau thất bại sau khi bước trước đã thành công.

## 8. Trả receipt và cho phép truy vấn trạng thái

Với command quan trọng, nên tách **chấp nhận yêu cầu** khỏi **hoàn tất nghiệp vụ**. Server có thể trả receipt ngay sau khi lưu command/outbox thành công:

```java
public record CommandReceipt(
    String commandId,
    String status,
    Instant acceptedAt,
    String resultCode
) {}
```

Các trạng thái thường dùng:

| Trạng thái | Ý nghĩa |
|---|---|
| `ACCEPTED` | Server đã lưu yêu cầu và nhận trách nhiệm xử lý. |
| `PROCESSING` | Worker đang thực hiện. |
| `SUCCEEDED` | Side effect nghiệp vụ hoàn tất. |
| `REJECTED` | Yêu cầu bị từ chối do validation hoặc quy tắc nghiệp vụ. |
| `RETRYABLE_FAILED` | Lỗi tạm thời; hệ thống sẽ thử lại hoặc chờ xử lý tiếp. |
| `FAILED_FINAL` | Đã kết thúc thất bại và không tự retry nữa. |

Client có thể hỏi trạng thái theo `commandId` bằng một Request-Response riêng:

```java
Mono<CommandReceipt> lookup = requester
    .route("commands.{commandId}.status.get", commandId)
    .retrieveMono(CommandReceipt.class);
```

Handler phía server chỉ trả trạng thái của command thuộc principal/tenant hiện tại. Không cho phép người dùng truy vấn trạng thái command chỉ bằng cách đoán ID của người khác.

Nếu client timeout ở lần gửi đầu, có thể truy vấn status trước khi retry. Nếu chưa tìm thấy record, kết quả vẫn có thể chưa xác định trong một khoảng ngắn do request ban đầu đang trên đường tới server. Client có thể thử lại cùng command ID; unique constraint ở server sẽ chống tạo command trùng.

## 9. Retry an toàn và backoff

Retry chỉ nên được thực hiện khi loại lỗi và tính chất command cho phép. Một chính sách cơ bản:

- Retry lỗi tạm thời như connection reset, timeout hoặc service unavailable khi thao tác có tính idempotent.
- Không retry lỗi validation, authentication, authorization hoặc business rejection.
- Giữ nguyên `commandId` và payload nghiệp vụ qua mọi lần thử.
- Dùng exponential backoff, jitter và giới hạn tổng số lần/thời gian retry.
- Khi outcome không rõ, ưu tiên truy vấn trạng thái hoặc gửi lại cùng idempotency key.
- Ghi nhận attempt count và thời điểm thử cuối; tránh retry đồng thời từ nhiều tầng không phối hợp.

Ví dụ Reactor cho một truy vấn có thể lặp an toàn:

```java
Mono<DeviceStatus> status = requester
    .route("devices.{deviceId}.status.get", deviceId)
    .data(new StatusQuery())
    .retrieveMono(DeviceStatus.class)
    .timeout(Duration.ofSeconds(3))
    .retryWhen(Retry.backoff(3, Duration.ofMillis(250))
        .maxBackoff(Duration.ofSeconds(4))
        .jitter(0.5)
        .filter(this::isTransientFailure));
```

Đây là ví dụ cho truy vấn đọc trạng thái. Với command có side effect, chỉ thêm retry sau khi server có idempotency/dedup phù hợp và client giữ nguyên command ID. Không áp dụng retry vô hạn cho Fire-and-Forget hoặc command không có cơ chế nhận diện lần gửi lặp.

## 10. Sequence number và cursor cho stream/channel

Với Request-Stream hoặc Request-Channel kéo dài, một command ID cho toàn bộ phiên là chưa đủ. Mỗi phần tử cần sequence number hoặc event ID để phát hiện gap, duplicate và xác định điểm tiếp tục.

Ví dụ một channel điều khiển thiết bị:

```java
public record DeviceCommand(
    String sessionId,
    long sequence,
    String commandId,
    String action
) {}

public record DeviceUpdate(
    String sessionId,
    long acknowledgedSequence,
    String commandId,
    String status
) {}
```

Server lưu sequence cuối đã xử lý theo session hoặc theo aggregate. Khi nhận command:

1. Nếu `commandId` đã xử lý, trả trạng thái/kết quả cũ.
2. Nếu sequence nhỏ hơn hoặc bằng watermark đã xác nhận, bỏ qua lần gửi lặp theo quy tắc idempotency.
3. Nếu sequence lớn hơn sequence kế tiếp mong đợi, phát hiện gap và yêu cầu client đồng bộ hoặc gửi lại phần thiếu.
4. Nếu sequence đúng, xử lý và lưu watermark cùng side effect trong transaction.

Không chỉ dựa vào thứ tự frame để suy ra thứ tự nghiệp vụ sau reconnect. RSocket Resume có thể khôi phục việc truyền frame của logical session nếu state còn hợp lệ; nó không thay thế sequence, dedup hoặc checkpoint nghiệp vụ.

## 11. Resume không giải quyết kết quả nghiệp vụ không chắc chắn

RSocket Resume lưu và phát lại frame chưa được xác nhận theo vị trí của giao thức. Nó giúp tiếp tục một logical connection khi transport bị gián đoạn và session/buffer vẫn còn. Tuy nhiên, các tình huống sau vẫn cần idempotency:

- Server đã xử lý command nhưng client chưa nhận response.
- Server đã commit side effect nhưng kết nối đứt trước khi frame response được xác nhận.
- Client tạo một kết nối/session mới sau khi Resume thất bại và gửi lại command.
- Ứng dụng chủ động retry request trên một session còn sống.

Resume xử lý tính liên tục của frame; idempotency xử lý tính đúng đắn của side effect nghiệp vụ. Hai cơ chế bổ trợ nhau và không thay thế nhau.

## 12. Xử lý Fire-and-Forget khi vẫn cần độ tin cậy

Fire-and-Forget thích hợp cho event best-effort. Nếu hệ thống vẫn muốn dùng tương tác một chiều nhưng không được mất command, cần một đường xác nhận khác:

- Ghi command vào durable outbox/queue trước khi gửi.
- Gắn `commandId` duy nhất và giữ ID đó qua retry.
- Server lưu idempotency record và trạng thái xử lý.
- Client truy vấn status theo ID hoặc nhận receipt qua Request-Stream/Channel riêng.
- Có chính sách retention cho dedup record dài hơn cửa sổ retry, replay và đối soát.

Nếu client cần biết ngay server đã chấp nhận yêu cầu, Request-Response thường thể hiện hợp đồng rõ ràng hơn: response là receipt `ACCEPTED`, không nhất thiết là kết quả cuối cùng. Nếu chỉ cần gửi telemetry có thể mất mẫu, Fire-and-Forget vẫn là lựa chọn đơn giản.

## 13. Những tình huống thường gặp và cách phản ứng

| Tình huống | Điều client biết | Hành động an toàn |
|---|---|---|
| Timeout trước khi có response | Không biết server đã nhận hay chưa | Giữ command ID; truy vấn status hoặc gửi lại cùng ID. |
| Connection reset sau khi server commit | Side effect có thể đã hoàn tất | Không tạo command ID mới; lấy receipt/status đã lưu. |
| Fire-and-Forget `send()` hoàn tất | Client publisher hoàn tất gửi | Không xem là business ack; dùng status/receipt riêng nếu cần. |
| Client hủy subscription | Client không còn chờ kết quả | Không suy ra server đã rollback; đối soát command nếu side effect quan trọng. |
| Response tới nhưng client crash trước khi lưu | Server có thể đã hoàn tất, client mất receipt | Khởi động lại và truy vấn bằng command ID bền vững. |
| Worker gọi dịch vụ ngoài rồi timeout | Dịch vụ ngoài có thể đã thực hiện | Retry cùng idempotency key hoặc truy vấn trạng thái downstream. |
| Resume thất bại do session hết hạn | Không thể tiếp tục transport session cũ | Tạo session mới và khôi phục bằng command ID/cursor/checkpoint. |
| Cùng key nhưng payload khác | Có xung đột sử dụng key | Từ chối conflict và ghi nhận sự kiện bất thường. |

## 14. Kiểm thử kết quả không chắc chắn

Các test cần mô phỏng thời điểm mất kết nối ở nhiều vị trí, không chỉ kiểm tra happy path:

1. Ngắt kết nối trước khi server nhận request; xác nhận retry cùng command ID chỉ tạo một record.
2. Cho server commit side effect rồi cố ý làm mất response; client timeout và retry cùng ID; xác nhận side effect chỉ xảy ra một lần.
3. Gửi đồng thời hai request cùng command ID; xác nhận unique constraint chỉ cho phép một lần xử lý mới.
4. Gửi cùng command ID nhưng payload hash khác; xác nhận server trả conflict.
5. Crash worker sau khi gọi downstream nhưng trước khi cập nhật trạng thái; xác nhận retry dùng idempotency key và không tạo side effect trùng nếu downstream hỗ trợ.
6. Kiểm tra outbox được commit cùng idempotency record; rollback transaction thì không có event mồ côi.
7. Timeout Fire-and-Forget; xác nhận client không kết luận server đã xử lý hoặc chưa xử lý chỉ từ `send()`.
8. Với Request-Stream/Channel, ngắt giữa sequence; xác nhận client phát hiện gap/duplicate và resume từ checkpoint đúng.
9. Khởi động lại client sau khi đã gửi command nhưng trước khi lưu receipt; xác nhận command ID được phục hồi từ local durable storage.
10. Hết thời hạn retention của dedup record; xác nhận chính sách từ chối ID cũ hoặc kiểm soát nguy cơ thực hiện lặp.

Trong integration test, có thể dùng proxy/test transport để chủ động cắt kết nối sau khi server đã commit nhưng trước khi response tới client. Đây là ca kiểm thử quan trọng nhất để chứng minh hệ thống xử lý được ambiguous outcome.

## 15. Quan sát và vận hành

Nên theo dõi các chỉ số và log không chứa bí mật:

- Số command ở trạng thái `ACCEPTED`, `PROCESSING`, `SUCCEEDED`, `RETRYABLE_FAILED` và `FAILED_FINAL`.
- Số timeout/disconnect theo interaction model và route.
- Số lần retry, duplicate command, idempotency conflict và số command phải đối soát.
- Độ trễ từ `ACCEPTED` tới `SUCCEEDED`.
- Outbox backlog, tuổi event cũ nhất và số lần worker retry.
- Số stream/channel bị reconnect, gap sequence và duplicate event.
- Tỷ lệ command ở trạng thái chưa xác định phía client sau timeout.

Log nên dùng `commandId`/correlation ID đã được kiểm soát, route template và error code. Không ghi token, payload nhạy cảm hoặc toàn bộ request chỉ để tìm một command. Cần đặt thời hạn lưu idempotency record đủ dài để bao phủ cửa sổ retry, reconnect và đối soát; xóa quá sớm có thể khiến một lần retry muộn thực hiện side effect lần nữa.

## 16. Kết luận

Khi client timeout hoặc mất kết nối, kết quả nghiệp vụ có thể chưa xác định dù server đã xử lý thành công. Không biến timeout thành kết luận thất bại và không retry command bằng một ID mới. Hãy tạo command ID ổn định, lưu dedup record cùng side effect trong transaction, dùng Transactional Outbox cho công việc ngoài database, cung cấp receipt/truy vấn trạng thái và sequence/cursor cho stream/channel. Retry có giới hạn chỉ an toàn khi thao tác idempotent hoặc server có cơ chế nhận diện lần gửi lặp. RSocket Resume giúp phục hồi frame/session; độ tin cậy nghiệp vụ vẫn cần idempotency, trạng thái bền vững và đối soát.
