# Khác biệt giữa lỗi gọi đồng bộ và lỗi xử lý sự kiện bất đồng bộ

> **Chương:** Serverless  
> **Module:** SPRING_CLOUD_FUNCTION  
> **Trọng tâm:** Phân biệt lỗi của request/response với lỗi xử lý event được giao bất đồng bộ; hiểu response, acknowledgement, retry, dead-letter và idempotency khi cùng một bean Supplier, Function hoặc Consumer chạy qua HTTP, AWS Lambda, Azure Functions, Google Cloud Run functions và broker.  
> **Mốc tham khảo:** 24/11/2026. Ví dụ Java dùng Java 21, Spring Boot 4.2.0, Spring Cloud BOM 2026.0.0 và Spring Cloud Function 5.1.0. Chính sách retry/ack phụ thuộc trigger, broker, adapter và cấu hình triển khai.

## 1. Cùng một exception, hai hợp đồng xử lý khác nhau

Giả sử một bean nghiệp vụ chuẩn hóa mã đơn hàng:

~~~java
@Bean
public Function<OrderCommand, OrderResult> normalizeOrder() {
    return command -> {
        if (command.code() == null || command.code().isBlank()) {
            throw new InvalidOrderException("Thiếu mã đơn hàng");
        }
        return new OrderResult(
                command.eventId(),
                command.code().trim().toUpperCase(Locale.ROOT));
    };
}
~~~

Nếu caller gửi HTTP request đồng bộ, exception có thể được chuyển thành **HTTP 400** để caller sửa dữ liệu. Caller đang chờ response và có thể quyết định gửi lại.

Nếu cùng lệnh đến từ queue, handler ném exception có thể khiến runtime/broker **không xác nhận message**, rồi giao lại theo retry policy. Nếu dữ liệu sai vĩnh viễn, retry nhiều lần chỉ lặp lại cùng một lỗi và có thể làm nghẽn queue.

Câu hỏi quan trọng không chỉ là “function ném exception gì?” mà còn là: ai đang chờ kết quả, ai quyết định request/event đã thành công, lỗi được truyền về caller hay được giữ trong hàng đợi, và nếu event chạy lại thì side effect có bị thực hiện hai lần không?

**Spring Cloud Function giữ logic nghiệp vụ có thể tái sử dụng; adapter và nền tảng quyết định cách exception trở thành response, nack, retry hoặc dead-letter.**

### 1.1. Sơ đồ hai đường đi

~~~mermaid
flowchart TB
    subgraph Sync["Gọi đồng bộ"]
        C["Client"] --> H["HTTP handler / adapter"]
        H --> F["FunctionCatalog"]
        F --> B["Business Function"]
        B -->|Thành công| R["HTTP response 2xx"]
        B -->|Exception| E["HTTP error response"]
        E --> C
        R --> C
    end

    subgraph Async["Xử lý event bất đồng bộ"]
        P["Producer"] --> Q["Queue / event broker"]
        Q --> W["Trigger / event adapter"]
        W --> FC["FunctionCatalog"]
        FC --> BB["Business Function / Consumer"]
        BB -->|Hoàn tất| ACK["Ack / checkpoint / complete"]
        BB -->|Exception| NACK["Nack / không ack / batch failure"]
        NACK --> RETRY["Retry / redelivery"]
        RETRY --> W
        RETRY --> DLQ["DLQ / failure destination"]
    end
~~~

Sơ đồ là mô hình khái niệm. Tên thao tác ack/nack và điều kiện retry khác nhau giữa SQS, Kafka, Azure Service Bus, Pub/Sub và từng adapter.

### 1.2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích synchronous invocation và asynchronous event processing.
2. Phân biệt HTTP response, Lambda Invoke API response, event acceptance và broker acknowledgement.
3. Xác định tầng chịu trách nhiệm retry ở AWS, Azure và Google Cloud.
4. Phân loại lỗi permanent, transient và uncertain outcome.
5. Thiết kế idempotency, DLQ, partial batch response và redrive.
6. Hiểu vai trò của FunctionCatalog và vì sao catalog không tự định nghĩa retry policy.
7. Viết test cho cùng một business function qua hai boundary khác nhau.

## 2. Đồng bộ và bất đồng bộ: khác nhau ở hợp đồng hoàn tất

### 2.1. Gọi đồng bộ

Một caller gửi request và chờ kết quả:

1. Client gửi HTTP request hoặc gọi API invocation đồng bộ.
2. Handler xác thực, parse payload và gọi function.
3. Function trả kết quả hoặc ném exception.
4. Adapter ánh xạ kết quả thành response/error.
5. Client nhận response hoặc timeout.

Có một **caller đang chờ**. Kết quả được phản ánh qua response contract; client hoặc service phía trên thường quyết định retry. Timeout ở client/gateway không chứng minh business code chưa chạy hoặc chưa ghi dữ liệu.

### 2.2. Xử lý sự kiện bất đồng bộ

Một producer gửi event, còn consumer xử lý sau:

1. Producer publish event vào queue/broker hoặc yêu cầu provider nhận invocation bất đồng bộ.
2. Producer nhận xác nhận đã tiếp nhận theo contract của nguồn.
3. Trigger/runtime giao event tới function.
4. Function xử lý rồi báo thành công/thất bại theo adapter contract.
5. Nguồn event quyết định ack, retry, giữ lại, chuyển DLQ hoặc bỏ event theo policy.

**Accepted không đồng nghĩa processed successfully.** Producer thường cần API tra trạng thái, callback hoặc event kết quả nếu muốn biết business outcome cuối cùng.

### 2.3. Bảng so sánh

| Tiêu chí | Đồng bộ | Bất đồng bộ |
| --- | --- | --- |
| Ai chờ? | Client/caller chờ response. | Producer thường chỉ chờ broker/provider nhận event. |
| Dấu hiệu thành công | HTTP status/body hoặc response API. | Ack/checkpoint/complete theo contract trigger. |
| Lỗi business | Map thành response/error cho caller. | Báo runtime/broker để retry, quarantine hoặc DLQ. |
| Ai retry? | Caller/SDK/gateway theo policy. | Trigger, broker, provider hoặc event source mapping. |
| Duplicate | Client có thể gửi lại sau timeout. | Redelivery/at-least-once có thể tạo duplicate. |
| Kết quả cuối cùng | Thường trả trong response. | Có thể cần job status/result event riêng. |
| Phù hợp | Validate, query, command nhanh. | Event integration, batch, side effect, công việc có thể chờ. |

## 3. Lỗi có thể xảy ra ở nhiều tầng

~~~mermaid
flowchart TD
    A["Client / producer"] --> B["Gateway / broker"]
    B --> C["Provider runtime + handler"]
    C --> D["Deserialize / convert / route"]
    D --> E["FunctionCatalog"]
    E --> F["Business function"]
    F --> G["Database / API / storage"]
    G --> H["Serialize result / side effect"]
    H --> I["Response / ack"]
~~~

| Tầng | Ví dụ lỗi | Ghi chú |
| --- | --- | --- |
| Client/network | DNS, TLS, client timeout | Client không biết chắc server đã xử lý chưa. |
| Gateway/ingress | 401, 403, 413, rate limit, integration timeout | Function có thể chưa được gọi. |
| Provider runtime | Cold start failure, OOM, invocation timeout | Runtime có thể reset hoặc giao lại event. |
| Conversion | JSON sai, Base64 lỗi, thiếu trường | Business function có thể chưa chạy. |
| FunctionCatalog/routing | Sai definition, không tìm thấy bean | Lỗi cấu hình/integration. |
| Business logic | Validation, trạng thái không hợp lệ | Có thể là lỗi permanent. |
| Downstream | DB unavailable, API 429/503 | Có thể là lỗi transient. |
| Response/ack | Serialization lỗi, mất kết nối, ack không hoàn tất | Side effect có thể đã xảy ra trước lỗi. |

**Không phải cứ thấy exception trong log là business function đã chạy.** Nếu JSON conversion thất bại, function có thể chưa được gọi. Ngược lại, function có thể đã ghi DB thành công rồi response/ack bị mất.

## 4. Đồng bộ: response là hợp đồng với caller

### 4.1. HTTP status và error body

| Loại lỗi | HTTP response gợi ý | Ý nghĩa |
| --- | --- | --- |
| Request sai schema/thiếu trường | 400 Bad Request | Caller cần sửa input. |
| Chưa xác thực/không đủ quyền | 401/403 | Caller cần credentials/quyền hợp lệ. |
| Resource không tồn tại | 404 | Không tìm thấy tài nguyên. |
| Conflict/trạng thái không cho phép | 409 | Request xung đột trạng thái. |
| Rate limit | 429 | Caller giảm tốc độ và tuân thủ retry policy. |
| Downstream tạm thời không sẵn sàng | 503 | Có thể retry sau khoảng thời gian phù hợp. |
| Lỗi không dự kiến | 500 | Không trả stack trace cho caller. |

Ví dụ body lỗi theo phong cách Problem Details:

~~~json
{
  "type": "https://api.example.com/problems/invalid-order",
  "title": "Invalid order",
  "status": 400,
  "code": "INVALID_ORDER_CODE",
  "detail": "Mã đơn hàng phải có dạng AA-999",
  "correlationId": "corr-42"
}
~~~

Không trả tên class nội bộ, SQL statement, access token hoặc stack trace.

### 4.2. Timeout không chứng minh request thất bại

Giả sử client gửi POST /orders. Server đã nhận request, ghi đơn hàng thành công, nhưng kết nối bị đứt trước khi client nhận response. Client thấy timeout, nhưng đơn hàng có thể đã tồn tại. Nếu client gửi lại cùng request mà không có idempotency key, hệ thống có thể tạo đơn trùng.

**Đồng bộ không có nghĩa chắc chắn chỉ chạy một lần.** Hãy thiết kế idempotency cho các command có side effect, kể cả HTTP.

### 4.3. HTTP 202 chỉ xác nhận đã nhận việc

Với tác vụ dài, API có thể trả:

~~~http
HTTP/1.1 202 Accepted
Location: /jobs/job-42
Content-Type: application/json

{"jobId":"job-42","status":"ACCEPTED"}
~~~

202 Accepted có nghĩa request đã được chấp nhận để xử lý; **không khẳng định tác vụ đã hoàn tất**. Client cần polling GET /jobs/job-42, nhận webhook hoặc subscription kết quả. Trạng thái job phải được lưu bền vững, không đặt trong biến singleton của Spring bean.

## 5. AWS Lambda: ba đường gọi không được đánh đồng

### 5.1. RequestResponse — gọi đồng bộ

Khi gọi Lambda Invoke API với:

~~~text
InvocationType = RequestResponse
~~~

caller chờ function xử lý và nhận response. Nếu function ném exception, response invocation có thể vẫn mang **HTTP status 200 ở lớp Lambda Invoke API** nhưng có header X-Amz-Function-Error và payload lỗi. Khi gọi trực tiếp Invoke API, không chỉ nhìn HTTP status; phải kiểm tra header và payload báo function error.

Nếu đi qua API Gateway/Function URL, response HTTP tới client phụ thuộc integration/adapter và mapping response. Không áp dụng máy móc quy tắc X-Amz-Function-Error của Lambda Invoke API cho HTTP proxy response.

AWS không tự retry lỗi function của một lời gọi RequestResponse chỉ vì function ném exception. Caller/service phía trên quyết định có gọi lại hay không.

### 5.2. Event — gọi bất đồng bộ

Khi gọi Lambda với:

~~~text
InvocationType = Event
~~~

Lambda nhận event vào hàng đợi nội bộ và thường trả **202 Accepted** khi đã tiếp nhận invocation. Response đó **không phải kết quả xử lý nghiệp vụ**.

Theo cấu hình mặc định của asynchronous invocation:

- Function error được retry tối đa **hai lần bổ sung** (tổng tối đa ba lần xử lý thông thường).
- Lỗi throttling/system error có cách retry/backoff riêng; event có thể được giữ trong hàng đợi tới giới hạn tuổi event.
- Event có thể bị giao nhiều lần ngay cả khi function không trả lỗi do semantics hàng đợi.
- Có thể cấu hình maximum retry attempts, maximum event age, DLQ hoặc on-failure destination.

Không nhầm retry của asynchronous invocation với retry của SQS event source mapping.

### 5.3. SQS event source mapping: batch được invoke đồng bộ bởi poller

Khi Lambda poll SQS, Lambda nhận batch và gọi function theo event source mapping. Đây là **một mô hình riêng**:

- Function được gọi đồng bộ với một batch event.
- Nếu batch thành công, messages được xóa khỏi queue.
- Nếu invocation thất bại, messages có thể trở lại visible sau visibility timeout.
- Mặc định, lỗi ở một record có thể khiến cả batch được giao lại.
- Nếu bật ReportBatchItemFailures và trả đúng danh sách record lỗi, chỉ các record được báo thất bại cần được xử lý lại theo contract.

Do đó, **SQS → Lambda không đơn giản là InvocationType=Event**. Retry do event source mapping và SQS visibility/redrive quản lý.

### 5.4. Bảng phân biệt AWS

| Cách gọi | Caller nhận gì? | Ai retry? |
| --- | --- | --- |
| Lambda RequestResponse | Response invocation và function error details. | Caller/service gọi lại theo policy của họ. |
| Lambda Event | 202 khi Lambda tiếp nhận event. | Lambda async queue theo retry/age/destination config. |
| SQS → Lambda event source mapping | Poller giao batch; success/failure theo batch response. | SQS/Lambda event source mapping theo visibility timeout, redrive, partial batch. |
| Kinesis/DynamoDB Streams | Batch records theo shard/partition. | Event source mapping; lỗi có thể chặn shard đến khi xử lý/expire hoặc cấu hình bisect/partial response. |

## 6. AWS: chọn đúng nơi xử lý exception và batch failure

### 6.1. Nếu catch rồi trả success, provider có thể xóa message

Ví dụ nguy hiểm:

~~~java
@Bean
public Consumer<OrderCommand> consumeOrder() {
    return command -> {
        try {
            process(command);
        } catch (Exception exception) {
            log.error("Không xử lý được order", exception);
            // Không ném lại lỗi và không ghi DLQ bền vững.
            // Adapter có thể xem invocation là thành công.
        }
    };
}
~~~

Với consumer event, nếu handler hoàn tất bình thường thì adapter/binder có thể coi message đã được xử lý. Log exception **không phải** một cơ chế retry.

Nếu bạn chủ động bắt lỗi để đưa event vào DLQ hoặc lưu failure record, chỉ báo success sau khi thao tác quarantine đã được ghi bền vững và có thể audit.

### 6.2. Partial batch response

Với SQS, response có thể chỉ rõ record thất bại:

~~~json
{
  "batchItemFailures": [
    {"itemIdentifier": "message-id-2"}
  ]
}
~~~

Khi event source mapping bật ReportBatchItemFailures, adapter có thể trả các message ID cần retry. Nếu handler ném exception thay vì trả partial response, toàn bộ batch có thể được xem là thất bại.

**FIFO queue:** phải giữ thứ tự message group. Khi gặp lỗi, không tiếp tục xử lý tùy tiện những record sau trong cùng nhóm; báo các record chưa xử lý theo hướng dẫn AWS.

### 6.3. Lỗi stream khác lỗi queue

Với Kinesis/DynamoDB Streams, event source mapping quản lý checkpoint theo shard. Một batch lỗi có thể được retry và giữ shard ở vị trí đó. Các lựa chọn như bisect-on-error, partial batch response và maximum record age/attempts có semantics riêng. Không áp cấu hình SQS visibility timeout cho Kinesis checkpoint.

## 7. Azure Functions: HTTP response và trigger retry không cùng cơ chế

### 7.1. HTTP trigger

Với HTTP trigger, handler trả response cho caller. Caller nhìn status/body và quyết định retry theo client policy.

- 400/401/403 thường biểu thị request/quyền không hợp lệ.
- 429/503 có thể gợi ý retry có backoff nếu API contract cho phép.
- 500 có thể là lỗi server; caller cần biết request có idempotent hay không.
- Client timeout không cho biết function đã dừng hay side effect đã commit.

Azure Functions không tự áp một retry policy chung cho mọi HTTP request. Nếu cần retry, phải định nghĩa behavior ở client, API gateway hoặc workflow.

### 7.2. Queue Storage trigger

Azure Queue Storage trigger có cơ chế poison message riêng. Theo tài liệu Azure, khi function thất bại, runtime thử lại message tối đa **năm lần bao gồm lần đầu**; nếu vẫn thất bại, message được đưa vào queue có hậu tố -poison.

Đây là behavior của **Queue Storage trigger**, không phải quy tắc áp dụng cho Service Bus, Event Hubs, Kafka hay HTTP.

### 7.3. Service Bus trigger và PeekLock

Với Azure Service Bus trigger, runtime nhận message trong chế độ PeekLock:

- Khi function hoàn tất thành công, runtime mặc định gọi Complete.
- Khi function thất bại, runtime mặc định gọi Abandon, khiến message có thể được giao lại.
- Nếu message vượt quá MaxDeliveryCount của entity, Service Bus có thể chuyển vào dead-letter queue.
- Lock có thể được tự gia hạn trong giới hạn cấu hình maxAutoLockRenewDuration.

Đây là **settlement contract của Service Bus**. Một method Java trả void không có nghĩa mọi message đều được complete; exception và cấu hình trigger quyết định kết quả.

### 7.4. Retry policy của Azure phụ thuộc extension/trigger

Azure có hai nhóm:

1. Retry behavior tích hợp trong từng trigger/binding extension.
2. Retry policy do Azure Functions runtime thực hiện cho các trigger được hỗ trợ.

Tài liệu liệt kê retry policy function-level cho một số trigger như Cosmos DB, Event Hubs, Kafka và Timer; Queue Storage, Blob Storage, Event Grid, Service Bus, RabbitMQ có behavior/extension riêng.

Vì vậy, **không chỉ thêm @Retryable vào Spring bean rồi giả định Azure runtime tự chạy lại mọi event**. Phải cấu hình đúng trigger extension, host settings và broker policy.

## 8. Google Cloud Run functions: HTTP lỗi và Eventarc retry

### 8.1. HTTP function

HTTP caller chờ status/response. Nếu function trả lỗi hoặc client timeout, caller/workflow quyết định có gửi lại hay không. Không có một hàng đợi event tự động retry mọi HTTP request đồng bộ chỉ vì Java function ném exception.

Nếu request đã ghi dữ liệu nhưng response mất, retry của client có thể gây duplicate. Sử dụng idempotency key cho command có side effect.

### 8.2. Event-driven function

Với Pub/Sub/Eventarc, việc retry thuộc **trigger/subscription delivery policy**, không nằm trong bean Java:

- Pub/Sub push có thể redeliver nếu subscriber không xác nhận.
- Eventarc trigger có cấu hình retry riêng.
- Tùy cách tạo trigger, retry có thể được bật hoặc cấu hình single delivery attempt.
- Khi retry bật, exception không được xử lý hoặc response không được xem là success có thể khiến event được giao lại với exponential backoff.
- Có thể cấu hình retry window, min/max backoff, delivery attempts và dead-letter topic qua subscription/trigger phù hợp.

Cloud Run functions docs nêu các HTTP status được coi là success trong một số delivery paths gồm 102, 200, 201, 202 và 204; status khác có thể được xem là negative acknowledgement khi retry được bật. **Phải xác minh trigger cụ thể**, không áp danh sách status này cho mọi API HTTP thông thường.

### 8.3. Acknowledgement deadline

Pub/Sub push/Eventarc delivery có acknowledgment deadline. Nếu function xử lý lâu hơn deadline, event có thể bị giao lại trong khi invocation cũ còn chạy. Điều này tạo hai worker xử lý cùng event đồng thời.

Cần cấu hình deadline phù hợp trong giới hạn provider, giữ xử lý trong budget và dùng idempotency/claim atomic. Tăng deadline không thay thế transaction hoặc duplicate protection.

## 9. Spring Cloud Function: exception đi qua catalog như thế nào?

### 9.1. FunctionCatalog không phải retry engine

Spring Cloud Function biến các functional beans thành biểu diễn chuẩn và cung cấp wrapper cho type conversion, composition, lookup. Khi adapter gọi function:

~~~text
HTTP / Event adapter
        |
        v
FunctionCatalog.lookup("normalizeOrder")
        |
        v
Function.apply(command)
        |
        +-- return result
        |
        +-- throw exception
~~~

Nếu function ném exception, exception đi ngược lên caller của function. **FunctionCatalog không tự quyết định** trả HTTP 400, nack SQS, abandon Service Bus hay retry Pub/Sub. Adapter/binder/provider mới có hợp đồng để diễn giải lỗi.

### 9.2. Function và Consumer

Function<T,R> có thể trả kết quả. Trong HTTP, adapter có thể serialize kết quả thành response. Trong stream, kết quả có thể được publish ra output binding.

Consumer<T> trả void. Khi Consumer ném exception, exception có thể được adapter/binder xem là thất bại; khi Consumer kết thúc bình thường, trigger có thể ack/complete theo contract.

**Không bắt mọi exception trong Consumer rồi log xong** nếu muốn broker retry. Nếu bắt và trả bình thường, hệ thống có thể đánh dấu message thành công.

### 9.3. Exception do conversion khác exception nghiệp vụ

Ví dụ:

- JSON không parse được thành OrderCommand: conversion/adapter error; business function có thể chưa chạy.
- OrderCommand.code sai định dạng: validation error trong business function.
- DB timeout trong lúc ghi: transient downstream error.
- Response serialization lỗi sau khi business side effect đã commit: kết quả không chắc chắn với caller/trigger.

Cần log/correlation theo **từng boundary** để xác định lỗi xảy ra trước hay sau side effect.

### 9.4. Không dùng retry annotation thay thế trigger policy

Một retry annotation ở lớp service có thể thử lại **một thao tác nội bộ**. Nó không thay thế retry của SQS, Lambda asynchronous invocation, Azure Service Bus, Eventarc/Pub/Sub hoặc HTTP caller.

Nếu cả service và broker đều retry, tổng số lần downstream có thể bị gọi là tích của các policy. Phải đặt giới hạn tổng thể, timeout và idempotency.

## 10. Phân loại lỗi: permanent, transient và uncertain

### 10.1. Lỗi vĩnh viễn (permanent)

Ví dụ: payload sai schema, thiếu event ID, mã đơn hàng sai định dạng, user không có quyền, trạng thái nghiệp vụ không cho phép hoặc event schema version không được hỗ trợ.

Retry cùng một payload thường không sửa được lỗi. Nên trả HTTP 400/403/409 ở sync; ở async, quarantine/DLQ hoặc ghi permanent failure theo policy.

### 10.2. Lỗi tạm thời (transient)

Ví dụ: database failover, connection timeout, downstream trả 429/503, network tạm thời mất kết nối, provider throttling hoặc resource tạm thời quá tải.

Có thể retry với backoff và jitter nếu thao tác idempotent và còn thời gian/age budget.

### 10.3. Lỗi không xác định kết quả (uncertain outcome)

Ví dụ: DB đã commit nhưng response connection bị đứt; HTTP client timeout khi server có thể đã xử lý xong; event consumer ghi side effect xong rồi process crash trước ack; provider đã gửi response nhưng broker không ghi nhận settlement.

Không thể suy ra “thất bại nên chạy lại” hoặc “thành công nên bỏ qua” chỉ từ timeout. Cần truy vấn trạng thái theo idempotency key hoặc dùng transaction/outbox/inbox.

### 10.4. Ma trận quyết định

| Lỗi | Đồng bộ | Bất đồng bộ |
| --- | --- | --- |
| Input không hợp lệ | Trả 400/422 theo API contract. | Không retry vô hạn; quarantine/DLQ hoặc ghi permanent failure. |
| Không đủ quyền | Trả 401/403. | Ghi nhận security failure, không retry như lỗi tạm thời. |
| DB tạm thời unavailable | 503/504 hoặc lỗi có mã; caller retry có giới hạn. | Ném lỗi để trigger retry/backoff theo policy. |
| Downstream rate limit | 429/503 + Retry-After nếu phù hợp. | Retry có backoff/jitter; giới hạn concurrency. |
| Function timeout | Caller nhận timeout/5xx tùy gateway; outcome có thể uncertain. | Trigger có thể redeliver; cần idempotency. |
| Serialization/ack thất bại sau side effect | Caller có thể không nhận được kết quả. | Message có thể được giao lại. |
| Lỗi code không dự kiến | 500, log/trace và alert. | Ném lỗi; retry có giới hạn, sau đó DLQ/failure destination. |

## 11. Retry: chỉ thử lại khi có cơ hội thành công

### 11.1. Exponential backoff và jitter

Một lịch retry thường dùng:

\[
d_n = \min(d_{\max}, d_0 \times 2^n) + jitter
\]

Trong đó d_0 là delay ban đầu, d_max là delay tối đa, jitter giúp nhiều clients không retry cùng thời điểm.

Ví dụ: 1 giây → 2 giây → 4 giây → 8 giây, thêm jitter và dừng sau số lần/tuổi event được phép. Đây là **lịch minh họa**, không phải default của mọi provider.

### 11.2. Những điều kiện phải có

Trước khi bật retry, xác định lỗi nào có thể retry, số attempts/event age tối đa, backoff/jitter/deadline tổng, sức chịu tải của downstream, idempotency, nơi lưu event khi hết retry và người chịu trách nhiệm redrive.

### 11.3. Tránh retry storm và retry lồng nhau

Nếu HTTP client retry 3 lần, service retry 3 lần và broker retry 5 lần, downstream có thể nhận tới **45 lần thử** cho một event theo tổ hợp đơn giản. Thực tế số lần còn tùy thời điểm fail, nhưng ví dụ cho thấy retry lồng nhau khuếch đại tải.

Hãy chọn một tầng điều phối retry chính, giới hạn retry nội bộ và đặt tổng deadline/attempt budget. Khi downstream đang quá tải, giảm concurrency/circuit-breaker có thể tốt hơn retry ngay.

## 12. Idempotency: bảo vệ side effect khi request/event bị gửi lại

### 12.1. Vì sao retry tạo duplicate?

Giả sử consumer xử lý event evt-42:

1. Ghi đơn hàng vào database thành công.
2. Process crash trước khi broker nhận ack.
3. Broker giao lại evt-42.
4. Consumer ghi đơn lần nữa nếu không kiểm tra idempotency.

Điều này xảy ra ở queue, stream, webhook và HTTP client retry.

### 12.2. Dùng business event ID làm khóa ổn định

Một cách phổ biến:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    result_reference VARCHAR(300),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Khi nhận event, transaction thử insert khóa consumer/event. Nếu unique conflict, event đã xử lý hoặc đang được xử lý; đọc trạng thái/result theo policy. Nếu insert thành công, thực hiện side effect trong cùng transaction khi khả thi, rồi commit dữ liệu và trạng thái xử lý nhất quán. Chỉ báo ack sau khi transaction hoàn tất.

Đây là mô hình khái niệm; implementation phải xử lý transaction isolation, lock, trạng thái in-progress và lỗi giữa chừng.

### 12.3. Không nhầm các loại ID

| ID | Vai trò | Phù hợp làm business idempotency key? |
| --- | --- | --- |
| Business event ID | Định danh event do producer nghiệp vụ phát hành. | **Thường phù hợp** nếu ổn định và duy nhất đúng scope. |
| SQS message ID / Pub/Sub message ID | Định danh message ở broker. | Có thể dùng cho delivery-level dedup trong scope phù hợp; không thay business operation ID trong mọi hệ thống. |
| Lambda request ID | Định danh một invocation. | Không; retry có thể có request ID mới. |
| HTTP correlation ID | Liên kết trace/call chain. | Không mặc định; có thể dùng chung cho nhiều request. |
| Idempotency key do client gửi | Nhận diện một command logic. | Có thể phù hợp nếu xác thực, lưu bền vững và có TTL/scope. |

### 12.4. Transactional outbox

Nếu một transaction vừa cập nhật DB vừa publish event, hai thao tác độc lập có thể lệch nhau: DB commit nhưng publish thất bại, hoặc publish thành công nhưng DB rollback.

**Transactional outbox** ghi business data và event vào cùng transaction; một publisher riêng đọc outbox rồi gửi event. Consumer vẫn cần idempotency/inbox vì publish/delivery có thể lặp.

## 13. Dead-letter queue và poison message

### 13.1. DLQ dùng để làm gì?

DLQ/failure destination lưu event không thể xử lý sau policy retry. Nó giúp tránh một message lỗi chặn cả pipeline mãi, giữ payload/metadata để điều tra, tách lỗi dữ liệu cố định khỏi outage tạm thời và redrive có kiểm soát sau khi sửa code hoặc dữ liệu.

DLQ không tự sửa lỗi và không nên trở thành nơi lưu vĩnh viễn không người theo dõi.

### 13.2. Những trường cần lưu

Một failure record nên có event ID và source/trigger, function/version, thời điểm thất bại, error category/code, số lần delivery nếu provider cung cấp, correlation/trace ID, payload hoặc pointer được bảo vệ, và trạng thái redrive.

Không lưu access token, raw secrets hoặc toàn bộ payload nhạy cảm vào log/DLQ không được kiểm soát.

### 13.3. Redrive an toàn

Trước khi phát lại DLQ: xác định nguyên nhân lỗi đã được sửa; kiểm tra event schema/version; kiểm tra side effect có xảy ra một phần; dùng idempotency key cũ; giới hạn tốc độ redrive; theo dõi kết quả và giữ audit trail.

## 14. Partial batch failure: một event lỗi không nhất thiết làm hỏng cả batch

### 14.1. SQS

Với SQS event source mapping, mặc định lỗi invocation có thể làm toàn batch được giao lại. Partial batch response cho phép trả ID record thất bại. Khi dùng tính năng này, event source mapping phải bật ReportBatchItemFailures.

Pseudo-code Java:

~~~java
List<BatchItemFailure> failures = new ArrayList<>();

for (SQSEvent.SQSMessage message : event.getRecords()) {
    try {
        processOne(message);
    } catch (PermanentMessageException ex) {
        quarantine(message, ex);
    } catch (TransientProcessingException ex) {
        failures.add(new BatchItemFailure(message.getMessageId()));
    }
}

return new SQSBatchResponse(failures);
~~~

Đây là pseudo-code vì SQSEvent, SQSBatchResponse và BatchItemFailure thuộc AWS event libraries; quarantine và processOne là code ứng dụng. Với FIFO, cần dừng xử lý record tiếp theo khi gặp lỗi theo yêu cầu ordering và báo cả những record chưa xử lý.

### 14.2. Kinesis/DynamoDB Streams

Với stream, record có thứ tự theo shard/partition và checkpoint. Một record lỗi có thể giữ shard ở vị trí đó. Cấu hình partial batch response, bisect-on-error và maximum retry age/attempts có thể giúp cô lập poison record; nhưng phải hiểu checkpoint và thứ tự.

### 14.3. Azure và Google

Azure Service Bus/Queue Storage có cơ chế settlement, delivery count và poison/dead-letter riêng. Google Pub/Sub/Eventarc dùng acknowledgement và delivery retry policy theo subscription/trigger. Không chuyển response SQSBatchResponse sang các nền tảng này.

## 15. HTTP bất đồng bộ: trả 202 và cung cấp trạng thái công việc

Một số công việc nên được tách thành hai API:

~~~http
POST /jobs
Content-Type: application/json
Idempotency-Key: client-request-42

{"orderId":"order-42","operation":"RECONCILE"}
~~~

Response:

~~~http
HTTP/1.1 202 Accepted
Location: /jobs/job-9001
Retry-After: 3
Content-Type: application/json

{"jobId":"job-9001","status":"ACCEPTED"}
~~~

Sau đó worker xử lý event bất đồng bộ. Client truy vấn GET /jobs/job-9001. Kết quả có thể là QUEUED, RUNNING, SUCCEEDED hoặc FAILED. Trạng thái phải được lưu bền vững; không đặt trong biến singleton của Spring bean vì instance có thể bị thay.

**202 chỉ xác nhận đã tiếp nhận job theo contract.** Nếu queue publish thất bại, API không nên trả 202 giả. Có thể dùng transactional outbox để gắn trạng thái job với việc publish event.

## 16. Dự án thực hành: một function, hai cách phản hồi lỗi

Project minh họa có một bean Function<OrderCommand,OrderResult> normalizeOrder, một bean Consumer<OrderCommand> consumeOrder, một facade đồng bộ map exception thành HTTP-like outcome và một facade bất đồng bộ để exception đi ngược về trigger adapter.

Các facade là **lớp mô phỏng boundary**. Chúng chưa phải AWS Lambda handler, Azure trigger hoặc Google Cloud Functions entrypoint.

### 16.1. Cấu trúc project

~~~text
sync-vs-async-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/vn/example/errors/
    │   │   ├── OrderApplication.java
    │   │   ├── SynchronousOrderFacade.java
    │   │   └── AsynchronousOrderFacade.java
    │   └── resources/application.properties
    └── test/java/vn/example/errors/
        └── ErrorBoundaryTest.java
~~~

### 16.2. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.2.0</version>
        <relativePath/>
    </parent>

    <groupId>vn.example</groupId>
    <artifactId>sync-vs-async-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
        <spring-cloud.version>2026.0.0</spring-cloud.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>2026.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-function-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

BOM quản lý version Spring Cloud; spring-cloud-function-context cung cấp catalog và function integration. Project chưa thêm Web starter hay AWS/Azure/GCP adapter vì mục tiêu là kiểm tra hai boundary trong JVM.

### 16.3. Cấu hình

src/main/resources/application.properties:

~~~properties
spring.application.name=sync-vs-async-demo
spring.main.web-application-type=none
~~~

Project không mở HTTP port. SynchronousOrderFacade mô phỏng việc ánh xạ lỗi sang HTTP status; muốn có endpoint thật cần thêm Web controller/adapter.

### 16.4. Business function và exception types

Tạo src/main/java/vn/example/errors/OrderApplication.java:

~~~java
package vn.example.errors;

import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Function;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OrderApplication {

    private static final Logger log =
            LoggerFactory.getLogger(OrderApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }

    public record OrderCommand(String eventId, String code) {}

    public record OrderResult(String eventId, String normalizedCode) {}

    public interface OrderStore {
        void save(OrderResult result);
    }

    public static class InvalidOrderException
            extends RuntimeException {
        public InvalidOrderException(String message) {
            super(message);
        }
    }

    public static class RetryableProcessingException
            extends RuntimeException {
        public RetryableProcessingException(
                String message, Throwable cause) {
            super(message, cause);
        }

        public RetryableProcessingException(String message) {
            super(message);
        }
    }

    @Bean
    public Function<OrderCommand, OrderResult> normalizeOrder() {
        return command -> {
            if (command == null ||
                    command.eventId() == null ||
                    command.eventId().isBlank()) {
                throw new InvalidOrderException("Thiếu event ID");
            }
            if (command.code() == null || command.code().isBlank()) {
                throw new InvalidOrderException("Thiếu mã đơn hàng");
            }

            String code = command.code()
                    .trim()
                    .toUpperCase(Locale.ROOT);

            if (!code.matches("[A-Z]{2}-[0-9]{3}")) {
                throw new InvalidOrderException(
                        "Mã đơn hàng phải có dạng AA-999");
            }
            return new OrderResult(command.eventId(), code);
        };
    }

    @Bean
    public OrderStore orderStore() {
        // Demo sink: chỉ ghi log. Production dùng repository/transaction.
        return result -> log.info(
                "Demo save order eventId={}", result.eventId());
    }

    @Bean
    public Consumer<OrderCommand> consumeOrder(
            Function<OrderCommand, OrderResult> normalizeOrder,
            OrderStore store) {
        return command -> store.save(normalizeOrder.apply(command));
    }
}
~~~

Bean normalizeOrder xử lý validation và chuẩn hóa. consumeOrder gọi cùng logic rồi chuyển kết quả cho OrderStore. Store của demo chỉ ghi log; production cần persistence transaction và idempotency thực tế.

### 16.5. Facade đồng bộ

Tạo src/main/java/vn/example/errors/SynchronousOrderFacade.java:

~~~java
package vn.example.errors;

import java.util.function.Function;

import org.springframework.stereotype.Component;

import vn.example.errors.OrderApplication.InvalidOrderException;
import vn.example.errors.OrderApplication.OrderCommand;
import vn.example.errors.OrderApplication.OrderResult;
import vn.example.errors.OrderApplication.RetryableProcessingException;

@Component
public class SynchronousOrderFacade {

    public record HttpOutcome(
            int status,
            OrderResult result,
            String errorCode,
            String message) {}

    private final Function<OrderCommand, OrderResult> function;

    public SynchronousOrderFacade(
            Function<OrderCommand, OrderResult> function) {
        this.function = function;
    }

    public HttpOutcome handle(OrderCommand command) {
        try {
            return new HttpOutcome(200, function.apply(command), null, null);
        } catch (InvalidOrderException exception) {
            return new HttpOutcome(
                    400, null, "INVALID_ORDER", exception.getMessage());
        } catch (RetryableProcessingException exception) {
            return new HttpOutcome(
                    503, null, "DEPENDENCY_UNAVAILABLE",
                    "Dịch vụ tạm thời không sẵn sàng");
        }
    }
}
~~~

Ở HTTP controller thực, handler có thể chuyển HttpOutcome.status thành ResponseEntity hoặc response type của provider. Ví dụ không trả stack trace hoặc nội dung exception kỹ thuật ra ngoài.

### 16.6. Facade bất đồng bộ

Tạo src/main/java/vn/example/errors/AsynchronousOrderFacade.java:

~~~java
package vn.example.errors;

import java.util.function.Consumer;

import org.springframework.stereotype.Component;

import vn.example.errors.OrderApplication.OrderCommand;

@Component
public class AsynchronousOrderFacade {

    private final Consumer<OrderCommand> consumer;

    public AsynchronousOrderFacade(Consumer<OrderCommand> consumer) {
        this.consumer = consumer;
    }

    public void onMessage(OrderCommand command) {
        // Exception được truyền về trigger/adapter.
        // Adapter ánh xạ nó thành failed invocation hoặc nack
        // theo contract của provider.
        consumer.accept(command);
    }
}
~~~

Facade không catch exception. Khi bean consumeOrder ném lỗi, adapter có thể nhận biết invocation thất bại và áp retry/ack policy. Nếu provider handler bắt exception rồi return bình thường, nó có thể vô tình xác nhận message.

### 16.7. Chuyển lỗi hạ tầng thành lỗi retryable

Ở production, lớp repository có thể chuyển lỗi DB tạm thời thành exception ứng dụng:

~~~java
try {
    repository.save(result);
} catch (TransientDataAccessException exception) {
    throw new RetryableProcessingException(
            "Database tạm thời không sẵn sàng",
            exception);
}
~~~

Đây là snippet bổ sung, cần Spring JDBC/transaction dependency nếu dùng TransientDataAccessException. Chỉ chuyển những lỗi có khả năng hồi phục thành retryable; lỗi constraint/schema vĩnh viễn nên được phân loại riêng.

## 17. JUnit: cùng một lỗi, hai cách biểu diễn

Tạo src/test/java/vn/example/errors/ErrorBoundaryTest.java:

~~~java
package vn.example.errors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.function.Consumer;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

import vn.example.errors.OrderApplication.InvalidOrderException;
import vn.example.errors.OrderApplication.OrderCommand;
import vn.example.errors.OrderApplication.OrderResult;
import vn.example.errors.OrderApplication.RetryableProcessingException;
import vn.example.errors.SynchronousOrderFacade.HttpOutcome;

@SpringBootTest
class ErrorBoundaryTest {

    @Autowired
    FunctionCatalog catalog;

    @Autowired
    SynchronousOrderFacade synchronousFacade;

    @Autowired
    AsynchronousOrderFacade asynchronousFacade;

    @Test
    void catalogFindsBusinessFunction() {
        Function<OrderCommand, OrderResult> function =
                catalog.lookup("normalizeOrder");
        assertNotNull(function);

        OrderResult result = function.apply(
                new OrderCommand("evt-42", "  od-123 "));
        assertEquals("OD-123", result.normalizedCode());
    }

    @Test
    void synchronousValidationErrorBecomes400() {
        HttpOutcome outcome = synchronousFacade.handle(
                new OrderCommand("evt-43", "bad-code"));
        assertEquals(400, outcome.status());
        assertEquals("INVALID_ORDER", outcome.errorCode());
    }

    @Test
    void asynchronousValidationErrorPropagates() {
        assertThrows(InvalidOrderException.class,
                () -> asynchronousFacade.onMessage(
                        new OrderCommand("evt-44", "bad-code")));
    }

    @Test
    void synchronousTransientErrorBecomes503() {
        Function<OrderCommand, OrderResult> failingFunction =
                command -> {
                    throw new RetryableProcessingException(
                            "Simulated downstream timeout");
                };

        var facade = new SynchronousOrderFacade(failingFunction);
        HttpOutcome outcome = facade.handle(
                new OrderCommand("evt-45", "OD-123"));

        assertEquals(503, outcome.status());
        assertEquals("DEPENDENCY_UNAVAILABLE", outcome.errorCode());
    }

    @Test
    void asynchronousTransientErrorPropagatesToAdapter() {
        Consumer<OrderCommand> failingConsumer =
                command -> {
                    throw new RetryableProcessingException(
                            "Simulated database unavailable");
                };

        var facade = new AsynchronousOrderFacade(failingConsumer);
        assertThrows(RetryableProcessingException.class,
                () -> facade.onMessage(
                        new OrderCommand("evt-46", "OD-123")));
    }

    @Test
    void consumerIsRegisteredInCatalog() {
        Consumer<OrderCommand> consumer =
                catalog.lookup("consumeOrder");
        assertNotNull(consumer);
        consumer.accept(new OrderCommand("evt-47", "OD-123"));
    }
}
~~~

Chạy trong thư mục project:

~~~bash
mvn clean test
~~~

Nếu repository có Maven Wrapper, dùng ./mvnw clean test hoặc ./mvnw.cmd clean test trên Windows.

Bộ test minh họa catalog lookup, HTTP-like 400/503 mapping, exception propagation ở async facade và consumer registration. **Test không chứng minh AWS/Azure/GCP đã retry thật.** Muốn kiểm chứng phải thêm provider adapter, trigger, retry config, DLQ và integration test trên runtime tương ứng.

## 18. Kiểm thử và quan sát lỗi trên môi trường thật

### 18.1. Bộ kiểm thử tối thiểu

| Lớp | Kiểm tra |
| --- | --- |
| Unit test | Validation, domain exception, permanent/transient classification. |
| FunctionCatalog test | Function/Consumer lookup, conversion, composition. |
| HTTP contract test | Status, error body, Retry-After, idempotency key. |
| Event contract test | Envelope parsing, event ID, ack/failure response, batch semantics. |
| Provider integration test | Trigger thật, retry, visibility/lock/checkpoint, DLQ. |
| Failure injection | DB timeout, 429/503, connection reset, function timeout. |
| Duplicate test | Cùng event giao hai lần hoặc hai instances xử lý đồng thời. |
| Redrive test | DLQ replay sau khi sửa lỗi và giữ nguyên idempotency. |

### 18.2. Metric cần theo dõi

- Invocation count, success/error/timeout.
- Error rate theo function, trigger và error category.
- Retry attempts, duplicate count, event age.
- Queue depth, oldest message age, dead-letter count.
- Partial batch failures/record failures.
- HTTP 4xx/5xx/429 và client retry rate.
- Downstream dependency latency/availability.
- Idempotency conflict và transaction rollback.
- Trace/correlation ID nối producer → trigger → function → database.

### 18.3. Log có cấu trúc

Ví dụ log ứng dụng:

~~~json
{
  "eventId": "evt-42",
  "correlationId": "corr-7",
  "function": "consumeOrder",
  "trigger": "sqs",
  "attempt": 2,
  "errorCategory": "TRANSIENT_DEPENDENCY",
  "outcome": "RETRY"
}
~~~

Không log raw payload, access token, receipt handle hoặc thông tin cá nhân không cần thiết. Hãy giữ event ID và correlation ID để điều tra mà không lộ dữ liệu.

## 19. Lỗi thường gặp khi thiết kế hai mô hình

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Trả HTTP 200 sau khi catch mọi exception | Caller tưởng xử lý thành công. | Map lỗi đúng status; chỉ trả success khi failure đã được xử lý bền vững theo contract. |
| Coi AWS async 202 là business success | Producer không biết event xử lý thất bại. | Theo dõi destination/DLQ hoặc phát event kết quả. |
| Dùng một retry policy cho mọi trigger | Retry sai semantics, có thể mất/nhân event. | Cấu hình theo Lambda async/SQS, Azure extension hoặc Eventarc subscription. |
| Catch exception trong Consumer rồi chỉ log | Broker có thể ack message; mất cơ hội retry. | Ném lại lỗi retryable hoặc ghi quarantine bền vững trước khi ack. |
| Retry lỗi validation | Queue bị poison message và tốn tài nguyên. | Phân loại permanent/transient, DLQ/quarantine. |
| Retry khi không có idempotency | Duplicate side effects. | Business key, unique constraint, transaction/inbox/outbox. |
| Dùng request ID làm idempotency key | Mỗi lần retry có thể tạo ID khác. | Dùng event/operation ID ổn định. |
| Cho rằng timeout đồng nghĩa chưa commit | Client gửi lại và tạo bản ghi trùng. | Query trạng thái theo idempotency key. |
| Bật retry vô hạn | Chi phí tăng, backlog và retry storm. | Giới hạn attempts/age, backoff, DLQ. |
| Dùng SQS batch response cho Pub/Sub | Sai contract adapter. | Dùng ack/response semantics của trigger thực tế. |
| Gộp lỗi parse và lỗi domain | Khó chẩn đoán, status/retry sai. | Log/metric theo boundary và error category. |
| Dùng retry annotation làm retry của broker | Broker vẫn có thể ack hoặc retry khác mong đợi. | Phối hợp retry nội bộ với trigger policy, kiểm tra integration. |

## 20. Bài tập tình huống

### Bài 1 — Phân biệt response và processing result

Một AWS Lambda được gọi với InvocationType=Event. API trả 202 nhưng sau đó function ném exception.

1. 202 biểu thị điều gì?
2. Ai retry function error theo mặc định?
3. Producer làm sao biết event cuối cùng thất bại?
4. DLQ và on-failure destination khác nhau ở mục đích nào?

**Gợi ý:** 202 là tiếp nhận invocation, không phải kết quả business. Lambda async queue áp retry policy; failure destination/DLQ giúp giữ kết quả thất bại để điều tra.

### Bài 2 — Direct invoke và API Gateway

Một Lambda được gọi trực tiếp bằng RequestResponse; Invoke API trả HTTP 200 nhưng có X-Amz-Function-Error. Một API Gateway route khác gọi cùng function và client nhận 5xx.

Giải thích vì sao hai response không mâu thuẫn. Nêu trường cần kiểm tra ở Lambda Invoke API và mapping response của API Gateway.

### Bài 3 — SQS batch

Một batch gồm ba record m-1, m-2, m-3. m-2 gặp database timeout, hai record còn lại thành công.

1. Nếu không bật partial batch response, điều gì có thể xảy ra?
2. Nếu bật ReportBatchItemFailures, response cần chứa record nào?
3. Nếu handler catch lỗi m-2 rồi return bình thường thì điều gì xảy ra?
4. Vì sao vẫn cần idempotency cho m-1 và m-3?

### Bài 4 — Azure Queue Storage và Service Bus

Một team dùng chung một giả định “Azure retry 5 lần” cho cả Queue Storage và Service Bus.

1. Vì sao giả định đó sai?
2. Queue Storage poison queue hoạt động thế nào?
3. Service Bus PeekLock Complete/Abandon có ý nghĩa gì?
4. MaxDeliveryCount và DLQ thuộc lớp nào?

### Bài 5 — Google Eventarc

Một Cloud Run function nhận Pub/Sub event. Khi DB timeout, handler ném exception. Hãy xác định:

- Retry có được bật trên trigger/subscription không?
- Response status nào được xem là success/negative ack theo delivery path?
- Retry window/backoff/DLQ được cấu hình ở đâu?
- Nếu event được giao lại khi invocation cũ chưa kết thúc, làm sao ngăn duplicate?

### Bài 6 — Cùng function, hai facade

Dùng project mục 16–17:

1. Giữ normalizeOrder stateless.
2. Sync facade trả 400 khi mã sai.
3. Async facade để InvalidOrderException thoát ra.
4. Thêm RetryableProcessingException và test 503 vs propagated exception.
5. Giải thích vì sao JUnit không chứng minh broker đã retry.

### Bài 7 — Side effect đã commit nhưng ack thất bại

Một consumer ghi thanh toán thành công rồi process bị dừng trước khi ack.

1. Broker có thể làm gì?
2. Vì sao retry có thể tạo thanh toán trùng?
3. Thiết kế idempotency key và unique constraint.
4. Cần lưu trạng thái transaction ở đâu?
5. Khi nào dùng outbox/inbox và khi nào chuyển event vào DLQ?

## 21. Checklist triển khai

| Hạng mục | Cần xác nhận |
| --- | --- |
| Invocation mode | HTTP/request-response, Lambda async, SQS mapping, Service Bus, Eventarc hay Kafka binder? |
| Error contract | HTTP status/body, Lambda FunctionError, batch response hay broker settlement? |
| Retry owner | Client, provider async queue, event source mapping, extension hay subscription? |
| Retry budget | Attempts, backoff/jitter, event age, visibility/lock/deadline. |
| Error classification | Permanent, transient, uncertain outcome. |
| Idempotency | Business event/operation key, unique constraint, transaction. |
| Batch semantics | Toàn batch hay partial record failures? FIFO/partition ordering? |
| DLQ/failure destination | Payload, metadata, retention, access và redrive procedure. |
| Observability | Error category, attempt, event age, trace/correlation, queue depth. |
| Test | Unit, catalog, contract, provider integration, duplicate/redrive. |
| Security | Không log secrets/PII; xác thực producer và quyền redrive. |

## 22. Tổng kết và tài liệu chính thức

**Lỗi đồng bộ là một phần của response contract; lỗi bất đồng bộ là một phần của delivery/acknowledgement contract.** Cùng một Java function có thể được dùng ở cả hai nơi, nhưng cách báo lỗi và retry phải theo adapter/provider.

Ghi nhớ:

- Đồng bộ: caller chờ response; lỗi được map thành status/body hoặc error payload; caller/service quyết định retry.
- Bất đồng bộ: producer thường chỉ nhận xác nhận tiếp nhận; consumer phải ack/complete hoặc báo lỗi để trigger/broker xử lý.
- AWS RequestResponse, Lambda Event và SQS event source mapping là ba đường invocation có semantics khác nhau.
- Azure HTTP, Queue Storage, Service Bus và Event Hubs không dùng một retry policy chung.
- Google HTTP và Eventarc/Pub/Sub có retry owner/cấu hình khác nhau; kiểm tra trigger/subscription cụ thể.
- FunctionCatalog hỗ trợ lookup, wrapper và conversion, **không** quyết định retry hay ack.
- Phân loại permanent/transient/uncertain, dùng backoff có giới hạn, DLQ, idempotency và transaction/outbox.
- Timeout/response mất không chứng minh side effect chưa xảy ra; mọi command có side effect cần chống duplicate.

**Tài liệu chính thức:**

1. Spring Cloud Function 5.1.0 — Programming Model, FunctionCatalog và functional beans: https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html
2. Spring Cloud Function — AWS Lambda adapter: https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html
3. AWS Lambda — Synchronous and asynchronous invocation: https://docs.aws.amazon.com/lambda/latest/dg/lambda-invocation.html
4. AWS Lambda — Asynchronous invocation error handling and retries: https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-error-handling.html
5. AWS Lambda — Configure asynchronous invocation destinations/retry age: https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-configuring.html
6. AWS Lambda — SQS event source error handling and partial batch responses: https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html
7. AWS Lambda — SQS event source mapping and at-least-once behavior: https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html
8. Microsoft Azure Functions — Error handling and retries by trigger: https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-error-pages
9. Microsoft Azure Functions — Service Bus trigger, PeekLock and dead-letter: https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-service-bus-trigger
10. Microsoft Azure Functions — Queue Storage trigger and poison messages: https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-storage-queue-trigger
11. Google Cloud Run functions — Configure event-driven function retries: https://docs.cloud.google.com/run/docs/tips/function-retries
12. Google Cloud Run — Troubleshoot redelivery and acknowledgement behavior: https://docs.cloud.google.com/run/docs/troubleshooting
13. Spring Cloud Stream — Error handling and binder reference: https://docs.spring.io/spring-cloud-stream/reference/
14. Spring Cloud — Release train compatibility: https://spring.io/projects/spring-cloud/
