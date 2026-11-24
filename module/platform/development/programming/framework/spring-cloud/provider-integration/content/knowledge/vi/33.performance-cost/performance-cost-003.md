# Batching, prefetch và điều tiết tốc độ theo tài nguyên xử lý

Một ứng dụng Spring Boot thường gửi hoặc nhận nhiều bản ghi qua mỗi lần gọi cloud service. Gửi từng bản ghi một làm tăng số round-trip, request overhead và chi phí mạng; gom quá nhiều bản ghi lại có thể làm tăng latency, memory, retry cost và áp lực lên dịch vụ. Prefetch giúp message sẵn sàng trước khi worker cần, nhưng nếu lấy trước nhiều hơn khả năng xử lý thì message nằm chờ trong bộ nhớ hoặc hết lock/visibility timeout. Vì vậy, batching và prefetch phải được đặt theo năng lực xử lý thực tế.

Bài học này xây dựng một cách chọn ba giới hạn cho pipeline: **batch size** (số item/byte trong một lần gọi), **prefetch/concurrency** (lượng việc được đưa tới consumer và số việc đang xử lý), và **rate limit** (tốc độ trung bình được phép gửi tới dịch vụ). Mỗi giới hạn giải quyết một vấn đề khác nhau; chúng phải phối hợp với timeout, retry và quota của cloud service.

Bài thuộc chương **Hiệu năng và chi phí** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua thư viện Spring Cloud tương ứng, bao gồm cấu hình danh tính/quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Các ví dụ dưới đây dùng AWS DynamoDB/SQS, Azure Cosmos DB/Service Bus và Google Cloud Pub/Sub.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

- Phân biệt batching, prefetch, concurrency và rate limiting.
- Chọn batch threshold theo số item, tổng byte và thời gian chờ.
- Tính ảnh hưởng của batch size tới request rate, latency và memory.
- Dùng batch API của DynamoDB, SQS, Azure Service Bus và Google Pub/Sub.
- Thiết kế bulk ingestion với Azure Cosmos DB Java SDK v4.
- Cấu hình prefetch và concurrent handlers cho Service Bus/SQS/Pub/Sub.
- Xử lý partial success, unprocessed items, duplicate delivery và idempotency.
- Điều tiết tốc độ theo RU/s, quota, throttling và độ trễ downstream.
- Kiểm thử throughput, batch fill ratio, backlog age và tail latency.

## 2. Bốn khái niệm cần tách biệt

| Cơ chế | Điều khiển | Mục tiêu | Ví dụ |
| --- | --- | --- | --- |
| **Batching** | Số item/byte gửi trong một request | Giảm round-trip và overhead mỗi request | DynamoDB BatchWriteItem, Pub/Sub publisher batching |
| **Prefetch** | Số message lấy trước và giữ cục bộ | Giảm thời gian chờ nhận message | Azure Service Bus `prefetchCount` |
| **Concurrency** | Số operation/handler đang chạy cùng lúc | Tận dụng CPU/network trong giới hạn downstream | `flatMap(..., 16)`, `maxConcurrentCalls(8)` |
| **Rate limiting** | Số operation hoặc đơn vị tài nguyên trong một khoảng thời gian | Không vượt quota/capacity | 100 request/giây hoặc giới hạn RU/s |

Ví dụ, batch 10 message có thể giảm 10 lần số request so với gửi từng message, nhưng nếu ứng dụng gửi 100 batch đồng thời thì vẫn có thể tạo 1.000 message in-flight. Prefetch 100 không có nghĩa xử lý song song 100 message; số handler có thể chỉ là 8. Rate limit 50 request/giây cũng không tương đương 50 item/giây nếu mỗi request chứa 20 item.

## 3. Vì sao batching cải thiện hiệu năng?

Một request tới cloud service thường có chi phí cố định: HTTP/AMQP framing, authentication/signing, network round-trip, scheduling và xử lý request ở server. Nếu mỗi request chỉ mang một item nhỏ, chi phí cố định chiếm tỷ trọng lớn.

Giả sử một request có:

- Chi phí cố định (T_0 = 20) ms.
- Chi phí xử lý mỗi item (T_i = 1) ms.

Nếu gửi từng item:

**T₁ = T₀ + Tᵢ = 21 ms/item**

Nếu batch 20 item và xử lý song song/hiệu quả trong cùng request:

**T₂₀ ≈ T₀ + 20Tᵢ = 40 ms/batch**

Chi phí request cố định phân bổ còn khoảng 1 ms/item. Đây là mô hình minh họa; service có thể xử lý song song, tuần tự hoặc tính capacity theo từng item. Batching không làm giảm RU/operation, write capacity hoặc số message nghiệp vụ được tính phí nếu giá dịch vụ dựa trên từng operation/message.

Lợi ích thường thấy:

- Giảm số request và round-trip.
- Tăng throughput khi network latency hoặc request overhead là bottleneck.
- Giảm CPU và scheduling overhead phía client/server.
- Dễ kiểm soát payload theo byte và gửi theo micro-batch.

Trade-off:

- Item đầu tiên phải chờ batch đủ lớn hoặc tới thời điểm flush.
- Batch lớn có thể chạm giới hạn request size hoặc service quota.
- Một số API trả partial success; retry toàn batch có thể tạo duplicate.
- Batch có thể làm tăng peak memory và thời gian giữ dữ liệu.
- Batch không mặc định có tính atomic như một transaction.

## 4. Chọn batch theo count, bytes và thời gian

Một batch thường được gửi khi **một trong ba điều kiện** xảy ra:

1. Đạt số item tối đa.
2. Đạt tổng payload bytes tối đa.
3. Đạt thời gian chờ tối đa.

~~~mermaid
flowchart TD
    A[Nhận item mới] --> B[Thêm vào batch hữu hạn]
    B --> C{Đạt count limit?}
    C -->|Có| F[Flush batch]
    C -->|Không| D{Đạt byte limit?}
    D -->|Có| F
    D -->|Không| E{Đạt max wait?}
    E -->|Có| F
    E -->|Không| A
    F --> G[Gửi request và xử lý kết quả từng item]
    G --> H[Khởi tạo batch tiếp theo]
    H --> A
~~~

| Threshold | Tác dụng | Nếu đặt quá thấp | Nếu đặt quá cao |
| --- | --- | --- | --- |
| Item count | Giới hạn số phần tử trong request | Batch nhỏ, ít tiết kiệm overhead | Latency và memory tăng |
| Byte size | Giữ request dưới giới hạn payload | Tốn nhiều request | Request quá lớn hoặc bị reject |
| Max wait | Giới hạn latency chờ gom batch | Batch thường không đầy | Item đầu batch chờ quá lâu |

Không chỉ đặt count. Nếu mỗi message có kích thước khác nhau, 100 item có thể chỉ 10 KiB hoặc vài MiB. Theo dõi p50/p95/p99 payload size và đặt byte threshold với headroom cho metadata/protocol overhead.

### 4.1. Batch size và request rate

Nếu producer phát (R_i) item/giây và batch có trung bình (B) item:

**R_request ≈ R_i / B**

Ví dụ 2.000 item/giây, batch trung bình 20 item:

**R_request ≈ 2.000 / 20 = 100 request/giây**

Nhưng service có thể tính quota theo item hoặc byte, nên request rate giảm không đồng nghĩa quota consumption giảm cùng tỷ lệ.

### 4.2. Max wait và latency

Batching theo timer tạo một khoảng chờ gom item. Với traffic đều và batch count (B), thời gian chờ trung bình xấp xỉ ((B-1)/(2R_i)), nếu chưa chạm byte threshold. Với traffic thưa, max wait thường quyết định latency. Đặt max wait theo SLA của use case: event analytics có thể chờ lâu hơn request đồng bộ cần phản hồi nhanh.

### 4.3. Không tạo unbounded batch queue

Khi producer nhanh hơn sender, hàng đợi batch sẽ tăng. Giới hạn số batch/bytes đang chờ; khi đầy, block upstream, trả lỗi overload, drop dữ liệu được phép hoặc ghi vào durable queue. Không gom vô hạn trong heap để chờ service phục hồi.

## 5. Batching không đồng nghĩa transaction

Một batch request có thể chứa nhiều operation nhưng service có thể xử lý từng operation độc lập:

- **All-or-nothing transaction:** tất cả thành công hoặc tất cả rollback trong phạm vi transaction được hỗ trợ.
- **Partial success batch:** một số item thành công, một số item thất bại; response trả trạng thái riêng.
- **Bulk throughput API:** SDK tự gom, phân phối và chạy nhiều operation song song; không bảo đảm atomicity giữa các item.

Phải đọc semantics của từng API. DynamoDB `BatchWriteItem` không atomic cho cả batch; Azure Service Bus `ServiceBusMessageBatch` là một AMQP message có nhiều message con nhưng không tự biến thành transaction nghiệp vụ xuyên dịch vụ; Cosmos bulk execution khác với transactional batch cùng partition key. Nếu nghiệp vụ yêu cầu atomicity, chọn API transaction riêng và hiểu giới hạn partition/transaction.

## 6. AWS: DynamoDB BatchWriteItem

### 6.1. Giới hạn và semantics

`BatchWriteItem` hỗ trợ tối đa **25 put/delete operations** và tổng request tối đa **16 MB**. Mỗi item có thể tối đa 400 KB khi lưu trữ, nhưng biểu diễn JSON trên wire có thể lớn hơn. API không hỗ trợ conditional write hoặc update expression; put lên key đã tồn tại sẽ ghi đè item. Từng put/delete là atomic riêng lẻ, nhưng toàn batch không atomic.

Nếu một số item không xử lý được do throttling hoặc lỗi tạm thời, response trả chúng trong `UnprocessedItems`. Chỉ retry phần chưa xử lý, dùng exponential backoff; không gửi lại toàn batch ngay lập tức. <Link url="https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_BatchWriteItem.html" title="AWS DynamoDB BatchWriteItem API"/>.

### 6.2. Tạo batch trong AWS SDK for Java 2.x

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.BatchWriteItemResponse;
import software.amazon.awssdk.services.dynamodb.model.PutRequest;
import software.amazon.awssdk.services.dynamodb.model.ReturnConsumedCapacity;
import software.amazon.awssdk.services.dynamodb.model.WriteRequest;

public Map<String, List<WriteRequest>> writeBatch(
        DynamoDbClient dynamoDb,
        String tableName,
        List<Product> products) {

    List<WriteRequest> writes = new ArrayList<>();
    for (Product product : products) {
        Map<String, AttributeValue> item = new HashMap<>();
        item.put("pk", AttributeValue.fromS("PRODUCT#" + product.id()));
        item.put("name", AttributeValue.fromS(product.name()));
        item.put("price", AttributeValue.fromN(
            product.price().toPlainString()));

        writes.add(WriteRequest.builder()
            .putRequest(PutRequest.builder().item(item).build())
            .build());
    }

    if (writes.isEmpty() || writes.size() > 25) {
        throw new IllegalArgumentException("Batch phải có 1-25 item");
    }

    BatchWriteItemResponse response = dynamoDb.batchWriteItem(request -> request
        .requestItems(Map.of(tableName, writes))
        .returnConsumedCapacity(ReturnConsumedCapacity.TOTAL));

    return response.unprocessedItems();
}
~~~

Ví dụ minh họa một batch dưới 25 item. Ứng dụng cần kiểm tra cả tổng byte request trước khi gửi; không chỉ dựa vào số lượng item. Kết quả trả về là map các item chưa xử lý.

### 6.3. Retry UnprocessedItems

Pseudo-code:

~~~java
Map<String, List<WriteRequest>> pending = initialRequestItems;
int attempt = 0;

while (!pending.isEmpty() && attempt < maxAttempts) {
    BatchWriteItemResponse response =
        dynamoDb.batchWriteItem(r -> r.requestItems(pending));

    pending = response.unprocessedItems();
    if (!pending.isEmpty()) {
        sleep(exponentialBackoffWithJitter(attempt));
    }
    attempt++;
}

if (!pending.isEmpty()) {
    persistForLaterRetry(pending);
}
~~~

Đoạn này là pseudocode cho worker/batch job; không dùng `Thread.sleep` trên WebFlux event loop. Trong pipeline reactive, dùng scheduler/async delay. Nếu hết retry budget, lưu lại pending items vào durable store hoặc dead-letter workflow để xử lý tiếp.

Không retry những item đã thành công. Nếu retry cả batch, một put có thể ghi đè lần nữa; với side effect khác, duplicate có thể nguy hiểm hơn.

## 7. AWS: SQS SendMessageBatch và ReceiveMessage

### 7.1. SendMessageBatch

SQS `SendMessageBatch` gửi tối đa **10 message** trong một request; tổng payload và từng message tối đa 1 MiB. Response có danh sách `successful()` và `failed()` riêng. HTTP 200 không đồng nghĩa mọi entry đều thành công. <Link url="https://docs.aws.amazon.com/java/api/latest/software/amazon/awssdk/services/sqs/SqsClient.html" title="AWS SDK for Java SQS API"/>.

~~~java
import java.util.ArrayList;
import java.util.List;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageBatchRequest;
import software.amazon.awssdk.services.sqs.model.SendMessageBatchRequestEntry;
import software.amazon.awssdk.services.sqs.model.SendMessageBatchResponse;

public SendMessageBatchResponse sendBatch(
        SqsClient sqs,
        String queueUrl,
        List<String> bodies) {

    if (bodies.isEmpty() || bodies.size() > 10) {
        throw new IllegalArgumentException("SQS batch phải có 1-10 message");
    }

    List<SendMessageBatchRequestEntry> entries = new ArrayList<>();
    for (int i = 0; i < bodies.size(); i++) {
        entries.add(SendMessageBatchRequestEntry.builder()
            .id("entry-" + i)
            .messageBody(bodies.get(i))
            .build());
    }

    SendMessageBatchResponse response = sqs.sendMessageBatch(
        SendMessageBatchRequest.builder()
            .queueUrl(queueUrl)
            .entries(entries)
            .build());

    response.failed().forEach(failure ->
        log.warn("SQS entry {} failed: {}",
            failure.id(), failure.message()));

    return response;
}
~~~

Entry ID dùng để đối chiếu response, không phải message ID của broker. Retry riêng entry thất bại theo loại lỗi; không retry lỗi validation/permanent như message body không hợp lệ.

Trong ví dụ, `log` là logger SLF4J của service. Client `SqsClient` nên được tạo một lần thành Spring bean và inject vào service; không khởi tạo client cho từng batch.

### 7.2. ReceiveMessage lấy trước tối đa 10 message

~~~java
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageResponse;

ReceiveMessageResponse response = sqs.receiveMessage(request -> request
    .queueUrl(queueUrl)
    .maxNumberOfMessages(10)
    .waitTimeSeconds(20)
    .visibilityTimeout(60));
~~~

`maxNumberOfMessages` hợp lệ từ 1 đến 10; service có thể trả ít hơn số lượng yêu cầu. Long polling giảm request rỗng. Visibility timeout bắt đầu khi message được nhận; nếu consumer giữ message trong local queue quá lâu hoặc xử lý lâu hơn thời hạn, message có thể xuất hiện lại và được consumer khác xử lý. Gia hạn visibility khi công việc cần thêm thời gian và đảm bảo delete sau khi xử lý thành công.

### 7.3. Prefetch ở tầng ứng dụng

SDK SQS không có một tham số `prefetchCount` tương đương Service Bus. Ứng dụng thường triển khai receive loop, giới hạn số batch đang được xử lý và số message trong local queue. Không gọi `ReceiveMessage` liên tục rồi tích lũy message không giới hạn.

Nếu mỗi batch lấy 10 message và có 4 batch đang được xử lý, số message nhận về có thể tới 40. Chỉ tăng số receive loop khi downstream handler/database có capacity tương ứng.

Sau khi xử lý thành công, gọi `DeleteMessage` bằng receipt handle của message. Không delete trước khi business operation hoàn tất; nếu cần thời gian dài hơn visibility timeout, dùng `ChangeMessageVisibility` để gia hạn có kiểm soát.

## 8. Azure Service Bus: batch theo kích thước thực tế

### 8.1. Tạo ServiceBusMessageBatch

`ServiceBusMessageBatch` có `getMaxSizeInBytes()`, `getSizeInBytes()`, `getCount()` và `tryAddMessage()`. SDK xác định giới hạn của batch theo service/transport; không nên hard-code một count cố định hoặc giả định mọi message có cùng kích thước. `tryAddMessage` trả false nếu message không thể thêm vào batch hiện tại. Phương thức không thread-safe, nên chỉ một producer thread được mutate batch tại một thời điểm. <Link url="https://learn.microsoft.com/en-us/java/api/com.azure.messaging.servicebus.servicebusmessagebatch?view=azure-java-stable" title="ServiceBusMessageBatch API"/>.

~~~java
import java.util.List;
import com.azure.messaging.servicebus.ServiceBusMessage;
import com.azure.messaging.servicebus.ServiceBusMessageBatch;
import com.azure.messaging.servicebus.ServiceBusSenderClient;

public void sendMessages(
        ServiceBusSenderClient sender,
        List<ServiceBusMessage> messages) {

    ServiceBusMessageBatch batch = sender.createMessageBatch();

    for (ServiceBusMessage message : messages) {
        if (batch.tryAddMessage(message)) {
            continue;
        }

        if (batch.getCount() > 0) {
            sender.sendMessages(batch);
        }

        batch = sender.createMessageBatch();
        if (!batch.tryAddMessage(message)) {
            throw new IllegalArgumentException(
                "Message quá lớn để thêm vào batch rỗng");
        }
    }

    if (batch.getCount() > 0) {
        sender.sendMessages(batch);
    }
}
~~~

Trong production, sender là client sống lâu được Spring quản lý; không tạo sender cho từng batch. Nếu entity partition-enabled hoặc session-enabled, các message trong một lần gửi cần cùng partition key/session ID. Nếu cần gửi các nhóm khác nhau, tạo batch riêng cho mỗi nhóm.

### 8.2. Prefetch và concurrent calls

Java SDK cho phép cấu hình `prefetchCount` và `maxConcurrentCalls` trên processor builder. Prefetch giữ message trong local buffer để handler lấy ngay; maxConcurrentCalls giới hạn số callback đang xử lý song song.

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusProcessorClient;
import com.azure.messaging.servicebus.ServiceBusReceiveMode;

ServiceBusProcessorClient processor = new ServiceBusClientBuilder()
    .credential(namespace, tokenCredential)
    .processor()
    .queueName(queueName)
    .receiveMode(ServiceBusReceiveMode.PEEK_LOCK)
    .disableAutoComplete()
    .prefetchCount(16)
    .maxConcurrentCalls(8)
    .processMessage(context -> {
        try {
            processBusinessMessage(context.getMessage());
            context.complete();
        } catch (RetryableException ex) {
            context.abandon();
        }
    })
    .processError(error -> log.error(
        "Service Bus receive error", error.getException()))
    .buildProcessorClient();

processor.start();
// Khi Spring ApplicationContext shutdown:
// processor.stop();
// processor.close();
~~~

Ví dụ có tối đa 8 handler song song và buffer prefetch 16 message. Java processor builder mặc định `maxConcurrentCalls=1` và `prefetchCount=0`. Trong PEEK_LOCK, lock bắt đầu ngay khi message được prefetch. Nếu buffer quá lớn, message có thể hết lock trước khi handler bắt đầu hoặc hoàn tất; khi đó complete thất bại, message được giao lại và có thể lặp tới dead-letter. Prefetch count cũng là giới hạn cứng số message có thể giữ trong local buffer; nếu đặt thấp hơn maxConcurrentCalls, processor không tận dụng hết handler. <Link url="https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-prefetch" title="Azure Service Bus prefetch guidance"/>.

Khởi đầu với prefetch gần maxConcurrentCalls hoặc lớn hơn một hệ số nhỏ, sau đó đo thời gian chờ trong buffer và thời gian xử lý p95/p99. Không tăng prefetch nếu lock duration không đủ cho cả thời gian đợi lẫn xử lý.

Trong Java SDK, `ServiceBusProcessorClient` dùng các daemon thread của Reactor global `boundedElastic` để gọi handler. Nếu `maxConcurrentCalls` cao hơn thread cap hiện tại, số handler thực tế có thể thấp hơn cấu hình; kiểm tra thread pool cap và thời gian xử lý blocking. Với lỗi không retry được, đưa message vào dead-letter theo chính sách thay vì abandon lặp vô hạn.

## 9. Azure Cosmos DB Java SDK v4: bulk execution

Bulk support của Cosmos Java SDK v4 nhận một reactive stream các `CosmosItemOperation` và thực hiện bulk operations. SDK phân phối công việc theo partition và throughput. Đây là bulk execution, không phải một transactional batch chung cho toàn bộ stream.

~~~java
import com.azure.cosmos.CosmosAsyncContainer;
import com.azure.cosmos.models.CosmosBulkOperations;
import com.azure.cosmos.models.CosmosItemOperation;
import com.azure.cosmos.models.PartitionKey;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public Mono<Void> bulkUpsert(
        CosmosAsyncContainer container,
        Flux<ProductDocument> documents) {

    Flux<CosmosItemOperation> operations = documents.map(document ->
        CosmosBulkOperations.getUpsertItemOperation(
            document,
            new PartitionKey(document.tenantId())));

    return container.executeBulkOperations(operations).then();
}
~~~

Đoạn code trả `Mono<Void>` để caller compose với pipeline WebFlux; tránh `.blockLast()` trong request path. Mỗi document phải có partition key đúng với container.

Bulk support trong Java SDK v4 không tự xử lý retry và timeout cho toàn bộ bulk stream. Ứng dụng cần phân loại kết quả từng operation, áp dụng retry/backoff có giới hạn và đặt deadline. Không bọc toàn bộ stream bằng một retry vô hạn; thao tác đã thành công có thể được gửi lại.

### 9.1. Điều tiết bulk theo throughput

Tài liệu Microsoft khuyến nghị dùng throughput control và retry policy để tránh 429 ở quy mô lớn, không chỉ tăng batch size hoặc concurrency. Bulk executor sample có thể tự điều chỉnh micro-batch 1–100 documents/physical partition, nhưng đó là cấu hình sample, không phải cam kết cho mọi workload. Một bulk call tự tạo nhiều task; tránh chạy nhiều bulk calls lớn song song trong cùng process nếu chưa đo CPU/network.

Throughput control group của Cosmos Java SDK v4 có thể giới hạn RU consumption theo client cục bộ hoặc phối hợp giữa nhiều client. Một số API throughput control được đánh dấu Beta; kiểm tra version và trạng thái API trước khi dùng production. Khi service trả 429, đọc retry-after và theo dõi RU consumption/partition hot spot. <Link url="https://learn.microsoft.com/en-us/azure/cosmos-db/throughput-control-java" title="Cosmos DB Java throughput control"/>; <Link url="https://learn.microsoft.com/en-us/azure/cosmos-db/bulk-executor-java" title="Cosmos DB Java bulk operations"/>.

Ví dụ tạo local throughput control group:

~~~java
import com.azure.cosmos.ThroughputControlGroupConfig;
import com.azure.cosmos.ThroughputControlGroupConfigBuilder;

ThroughputControlGroupConfig bulkGroup =
    new ThroughputControlGroupConfigBuilder()
        .groupName("bulkIngestion")
        .targetThroughputThreshold(0.75)
        .defaultControlGroup(true)
        .build();

container.enableLocalThroughputControlGroup(bulkGroup);
~~~

Ngưỡng 0,75 giới hạn nhóm bulk ở khoảng 75% throughput được provision theo semantics của control group; các request khác vẫn cần capacity. API này được đánh dấu `@Beta` và yêu cầu Java SDK v4 từ version hỗ trợ throughput control (tối thiểu 4.13.0 cho local/global mode).

### 9.2. Bulk và transactional batch khác nhau

Cosmos transactional batch áp dụng cho một logical partition key và bảo đảm atomicity trong phạm vi transaction hỗ trợ. Bulk execution tối ưu throughput cho nhiều operation, có thể phân tán qua nhiều partition và xử lý từng operation độc lập. Chọn transactional batch khi cần atomicity trong một partition; chọn bulk cho ingestion/upsert/delete số lượng lớn khi có thể chấp nhận kết quả từng item.

## 10. Google Cloud Pub/Sub: batching publisher

### 10.1. Ba threshold của publisher

Google Cloud Pub/Sub Java `Publisher` hỗ trợ `BatchingSettings`:

- `setElementCountThreshold`: số message tối đa để kích hoạt batch.
- `setRequestByteThreshold`: ngưỡng tổng bytes.
- `setDelayThreshold`: thời gian tối đa chờ batch.

Khi bất kỳ threshold nào đạt trước, publisher gửi batch. Pub/Sub có giới hạn tối đa 1.000 message hoặc 10 MB cho một batch publish request. <Link url="https://docs.cloud.google.com/pubsub/docs/batch-messaging" title="Pub/Sub batch messaging"/>.

~~~java
import com.google.api.gax.batching.BatchingSettings;
import com.google.api.gax.batching.FlowControlSettings;
import com.google.api.gax.batching.FlowController.LimitExceededBehavior;
import com.google.api.core.ApiFuture;
import com.google.cloud.pubsub.v1.Publisher;
import com.google.protobuf.ByteString;
import com.google.pubsub.v1.PubsubMessage;
import com.google.pubsub.v1.TopicName;
import org.threeten.bp.Duration;

FlowControlSettings flowControl = FlowControlSettings.newBuilder()
    .setLimitExceededBehavior(LimitExceededBehavior.Block)
    .setMaxOutstandingElementCount(500L)
    .setMaxOutstandingRequestBytes(10 * 1024 * 1024L)
    .build();

BatchingSettings batching = BatchingSettings.newBuilder()
    .setElementCountThreshold(100L)
    .setRequestByteThreshold(256 * 1024L)
    .setDelayThreshold(Duration.ofMillis(20))
    .setFlowControlSettings(flowControl)
    .build();

Publisher publisher = Publisher.newBuilder(
        TopicName.of(projectId, topicId))
    .setBatchingSettings(batching)
    .build();

ApiFuture<String> publishFuture = publisher.publish(
    PubsubMessage.newBuilder()
        .setData(ByteString.copyFromUtf8("order-created"))
        .build());
~~~

Ví dụ giới hạn publisher còn tối đa 500 message/10 MiB outstanding và batch flush khi đạt 100 message, 256 KiB hoặc 20 ms. Flow control `Block` làm producer chờ khi vượt budget; có lựa chọn fail bằng exception hoặc ignore limit, nhưng ignore có thể làm memory tăng không giới hạn. Trong ứng dụng Spring Boot, quản lý `Publisher` như bean có lifecycle; lưu/quan sát các publish future để xử lý kết quả. Khi ứng dụng shutdown, ngừng nhận publish mới, đợi future còn pending hoàn tất, sau đó gọi `publisher.shutdown()` và `publisher.awaitTermination(...)`. Không chờ future bằng `.get()` trên WebFlux event-loop thread.

Mẫu shutdown cho worker/job hoặc lifecycle callback:

~~~java
import java.util.concurrent.TimeUnit;

void stopPublisher() throws InterruptedException {
    publisher.shutdown();
    publisher.awaitTermination(1, TimeUnit.MINUTES);
}
~~~

Đoạn chờ chỉ chạy trong shutdown lifecycle hoặc worker thread; không chạy trong controller/request path.

### 10.2. Publish future và partial failure

Mỗi lời gọi `publish()` trả future riêng cho message. Theo dõi kết quả của từng future; không chỉ log rằng batch đã được gửi. Nếu future lỗi, xác định lỗi transient hay permanent trước khi retry. Giữ message ID để truy vết; dùng idempotency/deduplication ở consumer khi publish retry có thể tạo duplicate.

### 10.3. Subscriber flow control

Publisher batching không thay thế subscriber flow control. Subscriber có giới hạn outstanding message count và bytes; khi chạm ngưỡng, client tạm dừng pull tới khi message được ack/nack. Điều chỉnh số message/byte theo memory và năng lực handler; nếu backlog broker tăng dài hạn, scale subscriber hoặc tối ưu xử lý thay vì tăng outstanding limit vô hạn.

## 11. Prefetch: tăng throughput nhưng làm tăng thời gian chờ cục bộ

Prefetch hữu ích khi network round-trip giữa broker và consumer là bottleneck. Consumer lấy trước message, sau đó handler có sẵn dữ liệu để xử lý. Nhưng prefetch có thể giữ lock/visibility deadline trong lúc message còn nằm trong local buffer.

### 11.1. Sizing prefetch

Một điểm bắt đầu thực tế:

- Xác định số handler đồng thời (C).
- Đo thời gian xử lý p95 (T_p).
- Đo thời gian nhận message từ broker (T_n).
- Chọn prefetch vừa đủ che network latency, thường bắt đầu gần (C) hoặc một hệ số nhỏ trên (C).
- Xác minh message cuối trong buffer vẫn còn đủ lock/visibility time để xử lý.

Không có một tỷ lệ prefetch đúng cho mọi hệ thống. Với message lớn hoặc handler chậm, prefetch nhỏ sẽ an toàn hơn.

### 11.2. Ước lượng bộ nhớ prefetch

**M_prefetch ≈ P × S × K**

Trong đó **P** là số message prefetch, **S** là payload size p95 và **K** là hệ số overhead/copy.

Ví dụ prefetch 100 message, payload p95 128 KiB và hệ số overhead 2:

**M_prefetch ≈ 100 × 128 KiB × 2 = 25 MiB**

Chưa tính object header, deserialization, active handlers và các queue khác. Theo dõi cả heap lẫn direct/native memory nếu SDK dùng Netty.

### 11.3. Lock/visibility timeout

| Dịch vụ | Đồng hồ bắt đầu khi | Rủi ro khi prefetch quá cao |
| --- | --- | --- |
| AWS SQS | Message được receive và trở nên invisible | Visibility timeout có thể hết trước khi handler xử lý xong |
| Azure Service Bus PEEK_LOCK | Message được prefetch và lock | Lock hết trong buffer, duplicate delivery hoặc dead-letter sau nhiều lần |
| Google Pub/Sub | Ack deadline bắt đầu khi delivery | Message cần được ack hoặc gia hạn deadline trong khi xử lý |

Luôn xử lý idempotently vì message broker thường bảo đảm at-least-once delivery trong các tình huống lỗi/redelivery.

## 12. Rate limit và concurrency limit

Rate limit giới hạn số operation trong một khoảng thời gian; concurrency limit giới hạn số operation đang chạy đồng thời. Hai giới hạn không thay thế nhau:

- Service latency tăng có thể làm in-flight request tăng dù request/giây không đổi.
- Service latency giảm có thể làm request/giây tăng dù concurrency giữ nguyên.
- Một batch 100 item là một request nhưng có thể tiêu thụ 100 operation hoặc nhiều RU.

### 12.1. Token bucket

Token bucket tích lũy token theo tốc độ (r), có burst capacity (b). Mỗi request/item tiêu thụ token; khi hết token, producer phải chờ hoặc bị từ chối. Đây là cách phù hợp để giới hạn tốc độ trung bình nhưng vẫn cho phép burst ngắn.

### 12.2. Bulkhead/semaphore

Semaphore giới hạn số operation đồng thời. Ví dụ chỉ cho phép 12 bulk writes Cosmos đang in-flight, dù producer phát 5.000 document/giây. Dùng kết hợp với batch size và rate limit để tránh gửi quá nhiều request khi service chậm.

### 12.3. Resilience4j trong Spring Boot

Có thể dùng RateLimiter và Bulkhead để giới hạn application calls:

~~~yaml
resilience4j:
  ratelimiter:
    instances:
      cosmosBulk:
        limitForPeriod: 80
        limitRefreshPeriod: 1s
        timeoutDuration: 0
  bulkhead:
    instances:
      cosmosBulk:
        maxConcurrentCalls: 12
        maxWaitDuration: 0
~~~

Ví dụ giới hạn 80 lời gọi logic/giây và 12 operation đồng thời. Nếu một operation là batch 50 document, giới hạn này không đồng nghĩa 80 document/giây; phải tính batch size và RU/operation. RateLimiter đơn giản theo số call không thay thế Cosmos throughput control khi mỗi item có RU cost khác nhau.

Áp dụng các instance trên service method bằng annotation (cần các starter/aspect Resilience4j tương ứng):

~~~java
import io.github.resilience4j.bulkhead.annotation.Bulkhead;
import io.github.resilience4j.ratelimiter.annotation.RateLimiter;

@RateLimiter(name = "cosmosBulk")
@Bulkhead(name = "cosmosBulk", type = Bulkhead.Type.SEMAPHORE)
public Mono<Void> ingest(Flux<ProductDocument> documents) {
    return bulkUpsert(cosmosContainer, documents);
}
~~~

Nếu phương thức trả `Mono`/`Flux`, dùng cấu hình tích hợp Reactor tương thích với phiên bản Resilience4j đang dùng. Kiểm thử rõ hành vi khi rate limit/bulkhead từ chối; không để exception overload biến thành retry ngay lập tức ở tầng gọi.

## 13. Điều tiết thích ứng theo phản hồi của dịch vụ

Không phải lúc nào quota cũng cố định theo request count. Cosmos DB có RU/s và partition-level throttling; SQS, Pub/Sub và Service Bus có quota theo service/region/entity; network có bandwidth và latency riêng.

Một thuật toán điều chỉnh đơn giản:

1. Bắt đầu với batch size/concurrency nhỏ.
2. Nếu p95 thấp hơn SLO, không có 429/throttling và queue ổn định, tăng concurrency từ từ.
3. Nếu nhận 429, RESOURCE_EXHAUSTED, server busy hoặc pending acquire tăng, giảm concurrency/batch dispatch rate.
4. Tôn trọng Retry-After hoặc retry-after duration từ SDK/service.
5. Dùng exponential backoff + jitter và một retry budget tổng.
6. Giữ giới hạn tối đa theo memory, connection và quota; không tăng vô hạn chỉ vì một vài request thành công.

Với Cosmos DB, ưu tiên throughput control theo RU thay vì chỉ đếm request. Với Pub/Sub, publisher flow control theo outstanding count/bytes giúp giới hạn bộ nhớ client. Với Service Bus, kết hợp maxConcurrentCalls, prefetch và lock duration. Với SQS, kết hợp receive batch size, visibility timeout, số worker và giới hạn in-flight.

## 14. Xử lý partial failure và idempotency

Batch thường có nhiều kết quả:

| API | Kết quả lỗi/partial success | Hành động |
| --- | --- | --- |
| DynamoDB BatchWriteItem | `UnprocessedItems` | Retry đúng phần chưa xử lý với backoff |
| SQS SendMessageBatch | `failed()` và `successful()` | Retry từng entry lỗi, không gửi lại entry thành công |
| Azure Service Bus send batch | Lỗi gửi ở cấp batch | Retry batch theo semantics gửi và idempotency của ứng dụng |
| Pub/Sub Publisher | Future riêng từng message | Kiểm tra future từng message, retry transient failure |
| Cosmos bulk execution | Kết quả từng operation, lỗi/429 theo item | Retry theo chính sách được ứng dụng xây dựng; không giả định bulk API tự retry đầy đủ |

Khi retry:

- Gắn business ID/idempotency key ổn định cho mỗi item.
- Lưu trạng thái thành công/thất bại theo item nếu batch dài.
- Không retry validation, authorization hoặc schema errors.
- Retry transient failure với backoff/jitter và giới hạn tổng thời gian.
- Đưa item thất bại lâu dài vào dead-letter hoặc durable retry store.
- Không coi HTTP 200 là mọi entry đều thành công.

Batch không tạo ra exactly-once processing. Consumer cần chống duplicate bằng unique constraint, inbox/outbox hoặc idempotency record.

## 15. Bảo toàn thứ tự và partition affinity

Batching có thể ảnh hưởng thứ tự:

- SQS FIFO bảo toàn thứ tự theo MessageGroupId; batch entries cần được thiết kế đúng group và sequence.
- Pub/Sub ordering key yêu cầu publish theo key và xử lý lỗi/retry theo semantics ordering; lỗi một message có thể ảnh hưởng các message cùng key.
- Service Bus partition/session yêu cầu message cùng partition key hoặc session trong batch gửi tương ứng.
- Cosmos bulk có thể xử lý song song qua nhiều logical partition; không giả định thứ tự input là thứ tự commit.

Nếu thứ tự chỉ cần trong một aggregate/tenant, group item theo key và giới hạn concurrency theo key. Nếu không cần thứ tự toàn cục, tránh serialize toàn bộ pipeline chỉ để giữ thứ tự không cần thiết.

## 16. Chọn batch và prefetch bằng số đo

### 16.1. Tính throughput consumer

Nếu có **C** handler đồng thời, mỗi handler xử lý trung bình **T** giây/message:

**R_c ≈ C / T**

Ví dụ 16 handler, mỗi message mất 0,2 giây:

**R_c ≈ 16 / 0,2 = 80 message/giây**

Đây là throughput lý thuyết trước khi tính DB/network/retry. Nếu producer phát 200 message/giây, backlog sẽ tăng khoảng 120 message/giây; tăng prefetch chỉ chuyển backlog từ broker vào heap, không làm consumer xử lý nhanh hơn.

### 16.2. Tính batch request rate

Nếu producer phát 1.000 record/giây và batch trung bình 25 record:

**R_request ≈ 1.000 / 25 = 40 request/giây**

Nếu service quota là 30 request/giây, cần giảm tốc, tăng quota hoặc thay đổi cách ghi. Nếu quota tính RU/item, batch 25 item vẫn tiêu thụ RU của từng item.

### 16.3. Theo dõi các metric quan trọng

| Metric | Ý nghĩa |
| --- | --- |
| Batch fill ratio | Số item thực tế / count threshold |
| Batch bytes p95/p99 | Request có gần giới hạn byte không |
| Batch wait time | Thời gian item chờ flush |
| Request rate và item rate | Phân biệt request quota với item throughput |
| In-flight batches/messages | Số việc đang được xử lý |
| Prefetch buffer depth | Số message đang chờ cục bộ |
| Queue/backlog age | Tuổi của item/message cũ nhất |
| Partial failure/unprocessed count | Tỷ lệ item chưa xử lý |
| 429/throttling/RESOURCE_EXHAUSTED | Downstream đang quá tải |
| p50/p95/p99 latency | Tác động tới SLA |
| Heap/direct memory | Chi phí buffer và serialization |

## 17. Kiểm thử batching và prefetch

Thực hiện load test với cùng dữ liệu và cùng service tier:

1. So sánh gửi từng item với batch 5, 10, 25, 50.
2. Giữ payload byte tương đương và đo fill ratio.
3. Thử max wait 5, 20, 100 ms để xem latency.
4. Thử prefetch 0, C, 2C, 4C trong khi giữ maxConcurrentCalls cố định.
5. Tạo downstream chậm/throttled để đo queue, retry và memory.
6. Giả lập partial failure; xác minh chỉ retry item lỗi.
7. Dừng ứng dụng khi còn batch chưa flush hoặc message chưa ack; xác minh không mất dữ liệu ngoài semantics cho phép.

Không chỉ đo throughput trung bình. Quan sát p95/p99, oldest message age, lock expiry, memory peak và tỷ lệ duplicate.

## 18. Lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Batch chỉ theo count | Payload lớn vượt giới hạn request | Giới hạn thêm tổng bytes |
| Batch chỉ theo bytes | Traffic thấp khiến item chờ lâu | Thêm max wait |
| Batch quá lớn | Latency, memory và retry cost tăng | Tăng dần theo benchmark |
| Retry toàn batch | Duplicate operation đã thành công | Retry theo item/entry thất bại |
| Coi batch là transaction | Dữ liệu có thể commit một phần | Dùng transactional API nếu cần atomicity |
| Prefetch quá cao | Message hết lock/visibility trước khi xử lý | Giảm prefetch, kiểm tra lock duration |
| Prefetch thấp hơn concurrency | Handler không được tận dụng hết | Cân bằng prefetch với maxConcurrentCalls |
| Tăng concurrency khi 429 tăng | Throttling và retry storm nặng hơn | Giảm tốc, backoff, throughput control |
| Chỉ rate limit request | Batch lớn vẫn tiêu thụ nhiều RU/item | Giới hạn theo đơn vị tài nguyên/byte |
| Không kiểm tra publish future | Mất message lỗi hoặc không biết kết quả | Theo dõi từng future/entry |
| Không có idempotency | Duplicate delivery tạo side effect lặp | Idempotent consumer và deduplication |
| Dùng unbounded queue | Heap tăng tới OOM | Queue hữu hạn và overflow policy |

## 19. Quy trình triển khai

~~~mermaid
flowchart TD
    A[Đo item rate, payload và downstream latency] --> B[Chọn batch count + byte + max wait]
    B --> C[Chọn prefetch và max concurrent handlers]
    C --> D[Giới hạn queue/in-flight bytes]
    D --> E[Đặt rate limit theo quota/RU]
    E --> F[Thiết kế partial failure và idempotency]
    F --> G[Load test với throttling/slow consumer]
    G --> H{Latency, backlog và memory đạt SLO?}
    H -->|Không| I[Điều chỉnh batch/prefetch/rate]
    I --> G
    H -->|Có| J[Chốt metrics, alert và rollout]
~~~

Checklist trước production:

1. Batch có giới hạn count, bytes và max wait không?
2. API có trả partial success hoặc unprocessed item không?
3. Có retry riêng item lỗi và idempotency key không?
4. Prefetch có phù hợp concurrency và lock/visibility deadline không?
5. Queue/publisher outstanding có giới hạn count và bytes không?
6. Rate limiter có dựa trên đơn vị quota thực tế không?
7. Có theo dõi 429, batch fill ratio, oldest backlog age và p99 không?
8. Khi shutdown, batch chưa flush và message chưa ack được xử lý ra sao?

## 20. Bài tập thực hành

**Bài tập 1 — DynamoDB BatchWriteItem.** Viết worker ghi 10.000 sản phẩm theo batch 25 item. Giả lập unprocessed items, retry theo exponential backoff và ghi nhận số lần retry.

**Bài tập 2 — SQS SendMessageBatch.** Gửi 100 message theo batch 10. Cố ý tạo một entry không hợp lệ; xác minh response có partial failure và chỉ retry entry lỗi.

**Bài tập 3 — Service Bus batching.** Gửi các message có kích thước khác nhau bằng `tryAddMessage`. Đo count/bytes mỗi batch và xử lý trường hợp một message không fit batch rỗng.

**Bài tập 4 — Service Bus prefetch.** Cố định 8 concurrent calls, thay prefetch 8, 16, 64. Quan sát lock expiry, local buffer, throughput và duplicate delivery.

**Bài tập 5 — Cosmos bulk.** Upsert 100.000 document qua `executeBulkOperations`. Theo dõi RU, 429, partition hot spot và so sánh với throughput control group.

**Bài tập 6 — Pub/Sub publisher.** Cấu hình batch threshold count 100, bytes 256 KiB, delay 20 ms và flow control 10 MiB. Đo batch fill ratio và publish latency.

**Bài tập 7 — Rate vs concurrency.** Giữ concurrency 16, thay rate limit 50/100/200 operation/giây. Sau đó giữ rate 100/giây và thay concurrency 4/8/16; giải thích khác biệt.

**Bài tập 8 — Memory budget.** Tính memory của prefetch 200 message với payload p95 64 KiB và overhead factor 2. Thử payload tăng gấp đôi và xem giới hạn bytes nên thay đổi ra sao.

**Bài tập 9 — Partial failure và duplicate.** Làm consumer nhận lại message sau timeout. Dùng idempotency key để bảo đảm side effect chỉ áp dụng một lần.

## 21. Ghi nhớ

- Batching giảm request overhead; prefetch che network latency; concurrency điều khiển số việc đang chạy; rate limiting điều khiển tốc độ trung bình.
- Chọn batch theo **count + bytes + max wait**; không chỉ theo số item.
- DynamoDB BatchWriteItem tối đa 25 operations/16 MB, không atomic toàn batch và trả `UnprocessedItems`.
- SQS SendMessageBatch tối đa 10 entries; kiểm tra từng entry dù HTTP status là 200. ReceiveMessage trả tối đa 10 message.
- Azure Service Bus batch dùng `tryAddMessage` và giới hạn size thực tế từ SDK; prefetch phải tính cùng `maxConcurrentCalls` và lock duration.
- Cosmos bulk execution nhận reactive stream; throughput control/RU và retry cần được thiết kế rõ ràng.
- Pub/Sub publisher batching flush theo count/bytes/time; publisher flow control giới hạn outstanding message và bytes.
- Prefetch quá cao chỉ chuyển backlog từ broker vào memory và có thể làm lock/visibility hết hạn.
- Batch/async không mặc định atomic hoặc exactly-once; xử lý partial failure, retry và idempotency theo từng item.
- Theo dõi batch fill ratio, p95/p99 latency, backlog age, throttling và memory trước khi tăng batch/prefetch.

## 22. Tài liệu tham khảo

- [Amazon DynamoDB — BatchWriteItem API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_BatchWriteItem.html)
- [AWS SDK for Java 2.x — SQS client API](https://docs.aws.amazon.com/java/api/latest/software/amazon/awssdk/services/sqs/SqsClient.html)
- [AWS SDK for Java 2.x — ReceiveMessageRequest.Builder](https://docs.aws.amazon.com/java/api/latest/software/amazon/awssdk/services/sqs/model/ReceiveMessageRequest.Builder.html)
- [Azure Service Bus — Java client library](https://learn.microsoft.com/en-us/java/api/overview/azure/messaging-servicebus-readme)
- [Azure Service Bus — Prefetch messages](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-prefetch)
- [Azure Service Bus — ServiceBusProcessorClientBuilder](https://learn.microsoft.com/en-us/java/api/com.azure.messaging.servicebus.servicebusclientbuilder.servicebusprocessorclientbuilder?view=azure-java-stable)
- [Azure Cosmos DB — Bulk operations with Java SDK v4](https://learn.microsoft.com/en-us/azure/cosmos-db/bulk-executor-java)
- [Azure Cosmos DB — Java SDK throughput control groups](https://learn.microsoft.com/en-us/azure/cosmos-db/throughput-control-java)
- [Azure Cosmos DB — Migrate to Java SDK v4 bulk support](https://learn.microsoft.com/en-us/azure/cosmos-db/how-to-migrate-from-bulk-executor-library-java)
- [Google Cloud Pub/Sub — Batch messaging](https://docs.cloud.google.com/pubsub/docs/batch-messaging)
- [Google Cloud Pub/Sub — Publisher flow control](https://docs.cloud.google.com/pubsub/docs/flow-control-messages)
- [Google Cloud Pub/Sub — Publish best practices](https://docs.cloud.google.com/pubsub/docs/publish-best-practices)
- [Resilience4j — RateLimiter](https://resilience4j.readme.io/docs/ratelimiter)
- [Resilience4j — Bulkhead](https://resilience4j.readme.io/docs/bulkhead)
