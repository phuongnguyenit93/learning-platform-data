# Phản hồi lỗi từng phần của lô SQS khi phù hợp

Khi **Amazon SQS** kích hoạt **AWS Lambda**, mỗi invocation có thể mang một **lô (batch)** gồm nhiều message. Mặc định, nếu hàm gặp lỗi ở bất kỳ message nào và invocation thất bại, **toàn bộ lô có thể được giao lại**, kể cả những message đã xử lý thành công. Trong **SPRING_CLOUD_FUNCTION**, ta có thể khai báo bean **Function<SQSEvent, SQSBatchResponse>** và dùng handler **FunctionInvoker** của **spring-cloud-function-adapter-aws** để trả về danh sách chính xác những message cần thử lại. Cơ chế này gọi là **partial batch response** hoặc **reporting batch item failures**.

Bài thuộc chương **AWS Lambda**, đi sâu vào **khi nào nên dùng** phản hồi lỗi từng phần, cấu trúc **batchItemFailures**, điều kiện cấu hình **ReportBatchItemFailures**, sự khác nhau giữa SQS Standard và FIFO, thiết kế idempotency/retry/DLQ, ví dụ Java 17+ với Spring Cloud Function, cấu hình AWS SAM, kiểm thử và các lỗi nguy hiểm. Nội dung phục vụ mục tiêu chung của module: giữ nghiệp vụ có thể tái sử dụng bằng **Supplier**, **Function** và **Consumer**, trong khi tích hợp riêng với SQS được xử lý ở ranh giới adapter serverless.

## 1. Một Lambda invocation có thể chứa nhiều SQS messages

SQS không gọi một Java method trực tiếp. **Lambda event source mapping** poll queue, gom các message thành batch rồi gọi Lambda với một event chứa mảng **Records**.

Ví dụ rút gọn có ba record:

~~~json
{
  "Records": [
    {
      "messageId": "msg-001",
      "receiptHandle": "sample-handle-001",
      "body": "{\"eventId\":\"evt-001\",\"orderId\":\"ORD-101\",\"action\":\"CREATE\"}",
      "attributes": {"ApproximateReceiveCount": "1"},
      "messageAttributes": {},
      "eventSource": "aws:sqs"
    },
    {
      "messageId": "msg-002",
      "receiptHandle": "sample-handle-002",
      "body": "{\"eventId\":\"evt-002\",\"orderId\":\"ORD-102\",\"action\":\"SIMULATE_RETRY\"}",
      "attributes": {"ApproximateReceiveCount": "1"},
      "messageAttributes": {},
      "eventSource": "aws:sqs"
    },
    {
      "messageId": "msg-003",
      "receiptHandle": "sample-handle-003",
      "body": "{\"eventId\":\"evt-003\",\"orderId\":\"ORD-103\",\"action\":\"CREATE\"}",
      "attributes": {"ApproximateReceiveCount": "1"},
      "messageAttributes": {},
      "eventSource": "aws:sqs"
    }
  ]
}
~~~

Đây là **event minh họa đã rút gọn**, không bao gồm toàn bộ thuộc tính thường có như **md5OfBody**, **eventSourceARN**, **awsRegion**. Các giá trị messageId/receiptHandle là giả định phục vụ bài học.

| Trường | Ý nghĩa |
| --- | --- |
| **Records** | Danh sách message được gửi cùng một invocation |
| **messageId** | ID của SQS message; dùng làm **itemIdentifier** khi báo thất bại |
| **body** | Chuỗi nội dung của message; có thể là JSON nghiệp vụ hoặc envelope lồng bên trong |
| **receiptHandle** | Token nhận/xóa message ở API SQS; **không** dùng thay messageId trong partial failure |
| **attributes** | Metadata hệ thống như receive count; với FIFO có thêm thông tin nhóm |
| **messageAttributes** | Thuộc tính do bên gửi thêm, tách biệt body |
| **eventSourceARN** | Queue nguồn; có thể dùng để phân biệt khi một Lambda có nhiều mapping |

**Một SQS invocation không tương đương một đơn hàng hay một business event.** Hợp đồng Function cần duyệt từng **SQSEvent.SQSMessage**, parse từng **body**, rồi quyết định thành công/thất bại ở mức record.

## 2. Điều gì xảy ra khi không sử dụng partial batch response?

Giả sử business processor xử lý:

- **msg-001**: thành công, đã lưu dữ liệu.
- **msg-002**: thất bại do dependency timeout.
- **msg-003**: thành công hoặc chưa xử lý, tùy code dừng ở đâu.

Nếu mã **ném exception ra khỏi Lambda handler** và không dùng cơ chế báo từng record, AWS thường xem **invocation/batch thất bại**. Sau visibility timeout, các message trong batch có thể xuất hiện lại để được giao tiếp. Điều đó có thể dẫn tới xử lý lại **msg-001** dù đã tạo side effect.

~~~mermaid
flowchart LR
    A["Batch: 001, 002, 003"] --> B["Lambda"]
    B --> C["001 thành công"]
    B --> D["002 gặp lỗi"]
    D --> E["Exception toàn invocation"]
    E --> F["Batch có thể được retry"]
    F --> G["001 có thể chạy lại"]
~~~

Đây là lý do người viết Function cần **idempotency** ngay cả khi không bật partial failure: SQS và Lambda có ngữ nghĩa **at-least-once**, không hứa exactly-once thực thi.

Nếu code nuốt exception rồi trả về thành công cho toàn batch, tình huống ngược lại còn nguy hiểm hơn: **msg-002 có thể bị xóa khỏi queue dù chưa xử lý được**. Việc “không throw” không tự đồng nghĩa mọi message thành công.

## 3. Partial batch response thay đổi điều gì?

Khi **event source mapping** bật:

~~~text
FunctionResponseTypes = ReportBatchItemFailures
~~~

Lambda có thể nhận response dạng:

~~~json
{
  "batchItemFailures": [
    {
      "itemIdentifier": "msg-002"
    }
  ]
}
~~~

Ý nghĩa:

- **msg-001** và **msg-003** không nằm trong danh sách thất bại: Lambda có thể xóa chúng sau khi xử lý response hợp lệ.
- **msg-002** được báo là chưa thành công: nó có thể được giao lại sau visibility timeout, theo retry và retention của queue.
- Danh sách được đưa ra **ở cấp messageId của SQS**, không phải business eventId, orderId hay receiptHandle.

~~~mermaid
flowchart TD
    A["SQS batch: 001, 002, 003"] --> B["Function<SQSEvent,SQSBatchResponse>"]
    B --> C["001: thành công"]
    B --> D["002: thất bại"]
    B --> E["003: thành công"]
    C --> F["Response"]
    D --> F
    E --> F
    F --> G["batchItemFailures: [msg-002]"]
    G --> H["AWS xóa các bản ghi thành công"]
    G --> I["msg-002 chờ retry"]
~~~

**Partial response giảm xử lý lại không cần thiết**, nhưng **không loại trừ hoàn toàn duplicate**. Một invocation timeout, network error, concurrent delivery hoặc lỗi lúc phản hồi vẫn có thể dẫn tới xử lý lại record thành công. Side effect như ghi DB, phát sự kiện hoặc thanh toán vẫn cần thiết kế idempotent.

## 4. Hai điều kiện bắt buộc để AWS hiểu response

Cơ chế hoạt động khi **cả cấu hình và mã ứng dụng** đều đúng:

1. Event source mapping SQS có **FunctionResponseTypes: ReportBatchItemFailures**.
2. Function trả response đúng schema **batchItemFailures** và **không ném exception ngoài cùng** cho những lỗi record mà bạn muốn báo từng phần.

Nếu chỉ viết Java trả **SQSBatchResponse** nhưng không bật **ReportBatchItemFailures**, Lambda không sử dụng danh sách để quyết định message nào cần retry. Nguy hiểm là **handler có thể được xem là thành công**, trong khi một số record lỗi đã được liệt kê nhưng không được retry đúng kỳ vọng.

Ngược lại, nếu bật flag nhưng code gặp lỗi rồi **throw ra ngoài**, AWS vẫn xem **toàn bộ batch thất bại**.

| Cấu hình mapping | Kết quả handler | Hành vi cần hiểu |
| --- | --- | --- |
| Chưa bật ReportBatchItemFailures | Trả object chứa failed IDs | AWS không dùng partial report; không được coi đây là retry từng record |
| Đã bật | Trả failed IDs hợp lệ | Những message được liệt kê sẽ được retry; message còn lại có thể được xóa |
| Đã bật | Trả danh sách rỗng | Toàn bộ batch được coi thành công |
| Đã bật | Trả null/response rỗng | AWS coi batch thành công; có thể làm mất thông tin lỗi nếu code quên ghi failed IDs |
| Đã bật | Throw exception ra ngoài | Toàn bộ batch thất bại |
| Đã bật | JSON/IDs phản hồi không hợp lệ | Toàn bộ batch có thể bị coi thất bại |

**Cần test cấu hình AWS và Java response cùng nhau.** Unit test chỉ chứng minh code tạo danh sách IDs, chưa chứng minh Lambda event source mapping đã bật tính năng tương ứng.

## 5. Schema phản hồi: đúng key, đúng identifier

AWS kỳ vọng một JSON object như sau:

~~~json
{
  "batchItemFailures": [
    {"itemIdentifier": "msg-002"},
    {"itemIdentifier": "msg-004"}
  ]
}
~~~

Các trường **camelCase** là một phần của contract:

- **batchItemFailures** là array.
- Mỗi phần tử là object có key **itemIdentifier**.
- Giá trị phải là **messageId tồn tại trong Records của batch đang xử lý**.

### Những cấu trúc sai

Sai tên key:

~~~json
{
  "failedMessages": [
    {"messageId": "msg-002"}
  ]
}
~~~

Sai identifier:

~~~json
{
  "batchItemFailures": [
    {"itemIdentifier": "ORDER-102"}
  ]
}
~~~

Nếu **ORDER-102** là business orderId nhưng không phải SQS messageId có trong batch, response không hợp lệ.

Sai identifier null/rỗng:

~~~json
{
  "batchItemFailures": [
    {"itemIdentifier": ""}
  ]
}
~~~

AWS có thể xem **toàn batch là lỗi** khi identifier rỗng, null, sai tên key hoặc không tồn tại trong batch. Đừng đoán rằng AWS sẽ bỏ qua phần tử sai và chấp nhận những phần tử còn lại.

### Trường hợp thành công toàn bộ

~~~json
{
  "batchItemFailures": []
}
~~~

Đây là response rõ ràng nhất nếu tất cả records đều thành công. AWS cũng có thể xem **null response** hoặc **null list** là thành công, nhưng không nên dùng cách đó để biểu diễn “không chắc đã xử lý hết”.

## 6. Khi nào NÊN bật partial batch response?

Cơ chế phù hợp nhất khi:

- Queue thường gửi **batch size lớn hơn 1**.
- Các message trong **Standard queue** có thể được xử lý và xác nhận **độc lập**.
- Một vài message sai dữ liệu hoặc timeout không nên khiến **toàn batch** chạy lại.
- Side effects đã có chiến lược **idempotency**; việc giảm retry làm giảm chi phí và tải xuống hệ thống.
- Có logging/metrics và DLQ để theo dõi message liên tục lỗi.
- Ứng dụng có thể phân loại lỗi **theo từng record** và tạo response đúng contract.

Ví dụ: trong một batch 10 yêu cầu gửi email, 9 email được ghi nhận thành công và 1 yêu cầu thất bại do lỗi tạm thời. Nếu kết quả từng yêu cầu độc lập, chỉ retry một message có thể hợp lý.

Một lợi ích vận hành khác được AWS mô tả: khi bật **ReportBatchItemFailures**, Lambda **không giảm tốc độ poll do các invocation báo lỗi record theo cơ chế này** như một số trường hợp invocation thất bại hoàn toàn. Điều này giúp throughput không bị một ít poison messages kéo xuống, nhưng có thể **làm tăng áp lực lên downstream** nếu hàng loạt messages liên tục thất bại.

### Khi nào không có nhiều lợi ích hoặc nên cân nhắc khác?

| Tình huống | Cân nhắc |
| --- | --- |
| **BatchSize=1** | Partial vẫn dùng được nhưng không tiết kiệm retry record khác |
| **Batch phải commit nguyên khối** | Không thể xác nhận từng message độc lập nếu một lỗi làm transaction chung rollback |
| **Mất kết nối DB toàn hệ thống** | Nếu mọi record phụ thuộc cùng DB và đều lỗi, report từng ID không có lợi đáng kể; circuit breaker/backoff có thể thích hợp hơn |
| **Lỗi do code bug hoặc cấu hình nghiêm trọng** | Đừng biến mọi exception thành record-level failure và che lỗi hệ thống |
| **FIFO với ordering nghiêm ngặt** | Chỉ dùng khi có quy trình dừng đúng và báo cả record chưa xử lý |
| **Poison message vĩnh viễn** | Partial không thay DLQ/quarantine; nếu không có redrive policy, message có thể retry kéo dài |
| **Cần kết quả HTTP tức thời cho client** | SQS partial report không phải HTTP response cho caller |
| **Không có kiểm thử event mapping** | Không bật production chỉ vì code compile; xác minh mapping thực có flag |

**“Khi phù hợp” nghĩa là business contract cho phép xác nhận thành công ở mức record.** Nếu các message trong batch là một giao dịch bất khả phân, dùng phản hồi từng phần có thể phá hợp đồng nhất quán.

## 7. Standard SQS và FIFO SQS: quy tắc khác nhau

### 7.1. Standard queue — xử lý record độc lập

Giả sử ba records:

| Thứ tự nhận | messageId | Kết quả |
| --- | --- | --- |
| 1 | msg-001 | Thành công |
| 2 | msg-002 | Thất bại |
| 3 | msg-003 | Thành công |

Có thể tiếp tục xử lý **msg-003** sau khi **msg-002** lỗi, nếu các công việc độc lập và được phép thực hiện không theo thứ tự. Trả về:

~~~json
{
  "batchItemFailures": [
    {"itemIdentifier": "msg-002"}
  ]
}
~~~

### 7.2. FIFO queue — dừng tại lỗi đầu tiên

FIFO bảo đảm ordering theo **MessageGroupId** trong các điều kiện được AWS quy định. AWS khuyến nghị với **ReportBatchItemFailures**:

> Dừng xử lý khi gặp lỗi đầu tiên; đưa message lỗi và **mọi message chưa xử lý** vào danh sách thất bại.

Ví dụ:

| Thứ tự nhận | messageId | Hành động |
| --- | --- | --- |
| 1 | msg-001 | Xử lý thành công |
| 2 | msg-002 | Xử lý lỗi |
| 3 | msg-003 | **Không xử lý** |
| 4 | msg-004 | **Không xử lý** |

Phản hồi:

~~~json
{
  "batchItemFailures": [
    {"itemIdentifier": "msg-002"},
    {"itemIdentifier": "msg-003"},
    {"itemIdentifier": "msg-004"}
  ]
}
~~~

~~~mermaid
flowchart TD
    A["FIFO batch 001,002,003,004"] --> B["001 thành công"]
    B --> C["002 thất bại"]
    C --> D["DỪNG: không gọi xử lý 003/004"]
    D --> E["Trả failed: 002,003,004"]
~~~

**Không đánh dấu msg-003/msg-004 thành công nếu chưa thực hiện.** Nếu chúng không nằm trong danh sách, Lambda có thể xóa chúng cùng những records thành công.

Một batch FIFO có thể có các message group khác nhau; nếu cần tối ưu routing theo nhóm mà vẫn bảo toàn thứ tự, phải thiết kế và kiểm thử chính sách per-group rất cẩn thận. **Cách dừng toàn batch ở lỗi đầu tiên** trong ví dụ là cách bảo thủ, dễ xác minh theo hướng dẫn AWS.

## 8. Kiểu Java cần dùng trong Spring Cloud Function

Adapter AWS cung cấp handler:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker
~~~

hoặc ở AWS Console theo cú pháp:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
~~~

Bên trong ứng dụng, ta khai báo:

~~~java
Function<SQSEvent, SQSBatchResponse>
~~~

Các lớp AWS event:

~~~java
import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.amazonaws.services.lambda.runtime.events.SQSBatchResponse;
~~~

và dependency liên quan:

~~~xml
<dependency>
    <groupId>com.amazonaws</groupId>
    <artifactId>aws-lambda-java-events</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-function-adapter-aws</artifactId>
</dependency>
~~~

**Đây là phần khai báo dependency, không phải pom.xml hoàn chỉnh**. Cần BOM/parent quản lý Spring Boot, Spring Cloud/Function và phiên bản thư viện AWS tương thích. Với ví dụ dùng Jackson 2 và Java 17+, thêm dependency JSON phù hợp cho Spring Boot version đang chọn.

Không dùng **Consumer<SQSEvent>** khi cần trả một **SQSBatchResponse** có danh sách item failures: **Consumer** không có giá trị trả về. Bean **Function<SQSEvent,SQSBatchResponse>** mô tả hợp đồng một cách rõ ràng. Cũng không cần viết một Java **RequestHandler<SQSEvent,SQSBatchResponse>** riêng khi FunctionInvoker đáp ứng yêu cầu.

## 9. Ví dụ hoàn chỉnh Java 17+: hai bean Standard và FIFO

Ví dụ chính tạo:

1. **OrderEvent**: DTO đọc từ mỗi **SQSMessage.body**.
2. **OrderEventProcessor**: hợp đồng cho logic nghiệp vụ.
3. **processStandardSqs**: tiếp tục qua các record, báo riêng record lỗi.
4. **processFifoSqs**: dừng sau record đầu tiên lỗi, báo cả record chưa xử lý.
5. **SQSBatchResponse**: kết quả đúng cấu trúc AWS.

Mã minh họa **không ghi DB và không gọi AWS service thật**. Processor mẫu chỉ xác thực dữ liệu và mô phỏng một lỗi retryable có chủ đích, để bài test kiểm tra semantics an toàn.

Tệp **src/main/java/example/sqs/SqsPartialBatchApplication.java**:

~~~java
package example.sqs;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.function.Function;

import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.amazonaws.services.lambda.runtime.events.SQSBatchResponse;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SqsPartialBatchApplication {

    private static final Logger log =
        LoggerFactory.getLogger(SqsPartialBatchApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(
            SqsPartialBatchApplication.class, args);
    }

    public record OrderEvent(
        String eventId,
        String orderId,
        String action
    ) {}

    @FunctionalInterface
    public interface OrderEventProcessor {
        void process(OrderEvent event);
    }

    public static final class InvalidOrderMessage
            extends RuntimeException {
        public InvalidOrderMessage(String reason) {
            super(reason);
        }
    }

    public static final class RetryableOrderFailure
            extends RuntimeException {
        public RetryableOrderFailure(String reason) {
            super(reason);
        }
    }

    @Bean
    OrderEventProcessor demoProcessor() {
        return event -> {
            if (event == null
                    || event.eventId() == null
                    || event.eventId().isBlank()
                    || event.orderId() == null
                    || event.orderId().isBlank()
                    || event.action() == null) {
                throw new InvalidOrderMessage(
                    "Invalid order event");
            }

            if ("SIMULATE_RETRY".equals(event.action())) {
                throw new RetryableOrderFailure(
                    "Simulated temporary error");
            }

            if (!Set.of("CREATE", "CANCEL")
                    .contains(event.action())) {
                throw new InvalidOrderMessage(
                    "Unsupported order action");
            }

            // Demo: validation thành công, CHƯA ghi database.
            // Production: phải xử lý bền vững/idempotent ở đây.
        };
    }

    @Bean("processStandardSqs")
    Function<SQSEvent, SQSBatchResponse> processStandardSqs(
            ObjectMapper mapper,
            OrderEventProcessor processor) {

        return event -> processBatch(
            event, mapper, processor, false);
    }

    @Bean("processFifoSqs")
    Function<SQSEvent, SQSBatchResponse> processFifoSqs(
            ObjectMapper mapper,
            OrderEventProcessor processor) {

        return event -> processBatch(
            event, mapper, processor, true);
    }

    private static SQSBatchResponse processBatch(
            SQSEvent event,
            ObjectMapper mapper,
            OrderEventProcessor processor,
            boolean fifo) {

        if (event == null || event.getRecords() == null) {
            throw new IllegalArgumentException(
                "Missing SQS Records");
        }

        List<SQSEvent.SQSMessage> records =
            event.getRecords();

        List<SQSBatchResponse.BatchItemFailure> failed =
            new ArrayList<>();

        for (int i = 0; i < records.size(); i++) {
            SQSEvent.SQSMessage message = records.get(i);

            // Envelope không hợp lệ: KHÔNG tạo itemIdentifier sai.
            String messageId = requireMessageId(message);

            try {
                if (message.getBody() == null
                        || message.getBody().isBlank()) {
                    throw new InvalidOrderMessage(
                        "Empty message body");
                }

                OrderEvent input = mapper.readValue(
                    message.getBody(),
                    OrderEvent.class);

                processor.process(input);

                // Chỉ coi thành công khi công việc thật hoàn tất.

            } catch (JsonProcessingException
                     | InvalidOrderMessage
                     | RetryableOrderFailure ex) {

                log.warn(
                    "SQS record failed: messageId={}, type={}",
                    messageId,
                    ex.getClass().getSimpleName());

                failed.add(
                    new SQSBatchResponse.BatchItemFailure(
                        messageId));

                if (fifo) {
                    // Không tiếp tục xử lý message sau lỗi.
                    for (int j = i + 1;
                            j < records.size(); j++) {
                        String unprocessedId =
                            requireMessageId(records.get(j));
                        failed.add(
                            new SQSBatchResponse.BatchItemFailure(
                                unprocessedId));
                    }
                    break;
                }
            }
        }

        return new SQSBatchResponse(failed);
    }

    private static String requireMessageId(
            SQSEvent.SQSMessage message) {

        if (message == null
                || message.getMessageId() == null
                || message.getMessageId().isBlank()) {
            throw new IllegalStateException(
                "Invalid SQS envelope: missing messageId");
        }

        return message.getMessageId();
    }
}
~~~

### 9.1. Những điểm đáng chú ý trong mã

- **Bean names** được đặt rõ: **processStandardSqs** và **processFifoSqs**. Lambda chỉ chọn một bằng **spring_cloud_function_definition**.
- Mỗi record được parse từ **message.getBody()**, không parse cả mảng **Records** thành một OrderEvent.
- **JsonProcessingException** là lỗi parse JSON; **InvalidOrderMessage** và **RetryableOrderFailure** là những lỗi có chủ đích mà hệ thống muốn báo theo từng record.
- Mỗi failure dùng đúng **message.getMessageId()** làm **itemIdentifier**.
- Nếu envelope thiếu messageId, code ném lỗi ở cấp invocation thay vì tạo **SQSBatchResponse** không hợp lệ.
- Với **FIFO**, vòng lặp dừng sau lỗi đầu tiên và ghi các IDs chưa xử lý.
- Ví dụ **không catch mọi RuntimeException hoặc Error**. Nếu code bug hoặc hạ tầng xảy ra lỗi ngoài chính sách record-level, invocation có thể thất bại toàn lô; đây là lựa chọn thiết kế có chủ đích, phải có monitoring.

**Cảnh báo:** khi mở rộng code để gọi database, S3, HTTP downstream hoặc publish message, một exception có thể là tạm thời dù không thuộc các class trên. Cần đặt ranh giới exception hợp lý, quyết định fail từng record hay fail batch, và không vô tình “báo success” cho record chỉ vì lỗi bị nuốt.

### 9.2. Processor demo không phải business consumer production

Trong ví dụ, **demoProcessor** không ghi dữ liệu nên một record có action CREATE hợp lệ được coi là “thành công validation”. Đây **không** phải bằng chứng đơn hàng đã được tạo.

Trong production, thay processor bằng implementation idempotent:

~~~java
// Phác thảo thiết kế, KHÔNG phải class đã được khai báo.
processor.process(event);

// Bên trong processor production có thể làm:
// 1. Dùng event.eventId() làm idempotency key.
// 2. Kiểm tra/ghi key bằng transaction hoặc unique constraint.
// 3. Thực hiện side effect, hoặc ghi transactional outbox.
// 4. Chỉ return bình thường khi kết quả đã bền vững.
~~~

Nếu side effect ghi thành công nhưng response bị mất, message có thể được giao lại. Processor phải nhận ra event đã xử lý và trả success/no-op an toàn. Không dùng **HashSet** singleton trong JVM làm kho chống trùng bền vững xuyên các Lambda environments.

## 10. Input/output theo từng tình huống

Xét Standard batch gồm ba message:

~~~text
msg-001 body.action=CREATE
msg-002 body.action=SIMULATE_RETRY
msg-003 body.action=CANCEL
~~~

Kết quả:

~~~json
{
  "batchItemFailures": [
    {"itemIdentifier": "msg-002"}
  ]
}
~~~

Với FIFO batch có cùng thứ tự:

~~~text
msg-001: được xử lý thành công
msg-002: lỗi
msg-003: chưa được xử lý
~~~

Kết quả:

~~~json
{
  "batchItemFailures": [
    {"itemIdentifier": "msg-002"},
    {"itemIdentifier": "msg-003"}
  ]
}
~~~

Nếu cả ba thành công:

~~~json
{
  "batchItemFailures": []
}
~~~

Nếu **messageId bị thiếu trong record**, ví dụ code tạo test event sai hoặc parser không map được envelope, hàm ném **IllegalStateException** ở cấp batch. Không trả:

~~~json
{
  "batchItemFailures": [
    {"itemIdentifier": null}
  ]
}
~~~

vì AWS xem đây là response không hợp lệ. Mô hình xử lý lỗi rõ ràng giúp tránh “thành công giả” khi event shape đã hỏng.

## 11. Không nên biến mọi lỗi thành retry vô hạn

Có ba nhóm lỗi cần phân biệt:

| Nhóm lỗi | Ví dụ | Chiến lược cân nhắc |
| --- | --- | --- |
| **Dữ liệu không hợp lệ vĩnh viễn** | Thiếu eventId, JSON sai schema | Báo failure để DLQ/quarantine theo giới hạn retry; hoặc ghi quyết định từ chối bền vững rồi ack theo contract |
| **Lỗi tạm thời** | Downstream timeout, throttling, DB unavailable | Báo failure để retry/backoff hoặc fail batch nếu sự cố toàn cục |
| **Lỗi chương trình/hạ tầng nghiêm trọng** | Bug serializer, cấu hình Spring sai, thiếu class | Để invocation fail, cảnh báo và sửa triển khai; không giả vờ mọi record đã xử lý |

Không bắt mọi exception rồi trả **batchItemFailures: []**. Cũng không catch mọi exception để lặp retry những bản ghi hỏng dữ liệu vô hạn mà không có DLQ.

Với lỗi xác thực hoặc quyền IAM, việc retry liên tục thường không sửa được nguyên nhân. Cần báo động theo loại lỗi, sửa permission/configuration hoặc di chuyển message tới nơi kiểm tra sau số lần thử hợp lý.

### Quyết định ACK một message sai dữ liệu

Có hệ thống muốn coi message không hợp lệ là **đã xử lý** sau khi ghi nó vào một **quarantine store** bền vững. Khi đó có thể **không đưa message vào batchItemFailures**, vì công việc xử lý đã chuyển thành “lưu lỗi và ngăn retry”. Nhưng chỉ làm vậy khi quarantine operation đã thành công và contract cho phép xóa message gốc. Nếu chưa ghi được vào nơi lưu lỗi, vẫn phải báo failure.

## 12. Cấu hình AWS SAM Standard queue có DLQ

Ví dụ **template.yaml** mô tả một Lambda nhận Standard SQS và trả partial response.

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2016-10-31

Resources:
  OrdersDlq:
    Type: AWS::SQS::Queue

  OrdersQueue:
    Type: AWS::SQS::Queue
    Properties:
      VisibilityTimeout: 180
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt OrdersDlq.Arn
        maxReceiveCount: 5

  ProcessOrdersLambda:
    Type: AWS::Serverless::Function
    Properties:
      Runtime: java21
      Handler: org.springframework.cloud.function.adapter.aws.FunctionInvoker
      CodeUri: target/sqs-partial-1.0.0-aws.jar
      MemorySize: 512
      Timeout: 30
      Environment:
        Variables:
          MAIN_CLASS: example.sqs.SqsPartialBatchApplication
          spring_cloud_function_definition: processStandardSqs
      Policies:
        - SQSPollerPolicy:
            QueueName: !GetAtt OrdersQueue.QueueName
      Events:
        OrdersEvents:
          Type: SQS
          Properties:
            Queue: !GetAtt OrdersQueue.Arn
            BatchSize: 10
            FunctionResponseTypes:
              - ReportBatchItemFailures
~~~

### Giải thích cấu hình

- **FunctionResponseTypes: ReportBatchItemFailures** là thuộc tính quyết định AWS Lambda xem danh sách failed IDs.
- **BatchSize: 10** phù hợp ví dụ Standard queue, không phải giá trị tối ưu cho mọi workload.
- **VisibilityTimeout: 180** so với **Timeout: 30** là ví dụ theo hướng dẫn cơ bản của AWS: nên đặt visibility timeout tối thiểu khoảng **6 lần** Lambda timeout để có khoảng cho retry do throttling. Nếu có batching window, phải cộng thêm cửa sổ đó theo khuyến nghị AWS.
- **RedrivePolicy** chuyển message liên tục không xử lý được sang **OrdersDlq** sau số lần nhận vượt ngưỡng theo cơ chế SQS.
- **SQSPollerPolicy** cấp quyền tối thiểu phục vụ Lambda poll/xóa SQS messages; nếu queue dùng customer-managed KMS key, có thể cần **kms:Decrypt** và queue/key policy đúng.
- **CodeUri** là JAR ví dụ. Dự án phải build một **shaded JAR thực sự** chứa **FunctionInvoker**, application class, dependencies và Spring metadata.
- **MAIN_CLASS** là Spring Boot application class; **spring_cloud_function_definition** chọn bean **processStandardSqs**.
- **IAM**, network, log retention, tags, encryption, alarm và permission khác cần bổ sung theo môi trường thật.

Đây là một **template minh họa cấu trúc**, chưa đại diện cho deployment production đầy đủ. Java runtime phải tương thích bytecode và tổ hợp Spring Boot/Spring Cloud Function.

### Vì sao DLQ quan trọng?

Nếu một message “poison-pill” luôn sai schema, partial response liên tục trả messageId của nó, rồi message được giao lại. Không có DLQ/quarantine, message có thể quay vòng cho tới khi hết retention, tiêu tốn chi phí và tạo backlog. AWS Prescriptive Guidance gọi hiện tượng thất bại tích tụ kéo dài này là **snowball anti-pattern**.

Cần kiểm tra **redrive policy** (ví dụ maxReceiveCount), thời gian lưu DLQ, alarm và quy trình replay có kiểm soát. Không tự động replay dữ liệu chưa sửa vào cùng queue vô hạn.

## 13. Cấu hình FIFO queue: thêm những gì?

Với FIFO, không chỉ thay **definition** sang processFifoSqs. Queue và DLQ còn phải là **FIFO queue** tương ứng, tên queue có hậu tố **.fifo**.

Ví dụ riêng phần resources:

~~~yaml
OrdersFifoDlq:
  Type: AWS::SQS::Queue
  Properties:
    QueueName: orders-dead-letter.fifo
    FifoQueue: true

OrdersFifoQueue:
  Type: AWS::SQS::Queue
  Properties:
    QueueName: orders-source.fifo
    FifoQueue: true
    VisibilityTimeout: 180
    RedrivePolicy:
      deadLetterTargetArn: !GetAtt OrdersFifoDlq.Arn
      maxReceiveCount: 5
~~~

Ở Lambda tương ứng:

~~~yaml
Environment:
  Variables:
    MAIN_CLASS: example.sqs.SqsPartialBatchApplication
    spring_cloud_function_definition: processFifoSqs
Events:
  FifoOrders:
    Type: SQS
    Properties:
      Queue: !GetAtt OrdersFifoQueue.Arn
      BatchSize: 10
      FunctionResponseTypes:
        - ReportBatchItemFailures
~~~

Hai snippet này **chỉ là những phần của template**, không phải một tài nguyên Lambda hoàn chỉnh. Cần thêm Runtime, Handler, CodeUri, IAM, memory/timeout ở resource thật.

**FIFO ordering:** dừng ở failure đầu tiên và trả cả IDs chưa xử lý như code phần 9. Khi publisher gửi message vào FIFO, cần đáp ứng **MessageGroupId** và quy tắc deduplication (MessageDeduplicationId hoặc content-based deduplication tùy cấu hình). Partial batch response không thay FIFO message-group semantics.

Các giới hạn BatchSize/batching window có thể khác giữa Standard và FIFO, đặc biệt khi dùng chế độ provisioned event polling. Nên chọn theo tài liệu Lambda event source mapping ở phiên bản tính năng đang sử dụng thay vì hard-code giả định cho mọi cấu hình.

## 14. AWS CLI: kiểm tra cấu hình event source mapping thật

Để xem mapping đã khai báo cho Lambda:

~~~bash
aws lambda list-event-source-mappings --function-name process-orders-lambda
~~~

Để xem mapping cụ thể:

~~~bash
aws lambda get-event-source-mapping --uuid YOUR_MAPPING_UUID
~~~

Trong output, cần xác minh:

~~~text
EventSourceArn
FunctionArn
BatchSize
FunctionResponseTypes
State
LastProcessingResult
~~~

Khi muốn bật partial failure cho mapping đã có:

~~~bash
aws lambda update-event-source-mapping --uuid YOUR_MAPPING_UUID --function-response-types ReportBatchItemFailures
~~~

**YOUR_MAPPING_UUID** là placeholder do người vận hành thay bằng UUID lấy từ mapping thực. Không chạy các lệnh trên nếu chưa có Lambda/queue và AWS credentials/permissions phù hợp.

### Kiểm tra sau khi cập nhật

1. Mapping có **State** phù hợp, và quá trình update đã hoàn tất.
2. **FunctionResponseTypes** thực sự chứa **ReportBatchItemFailures**.
3. Function code version/alias được mapping gọi là bản đã triển khai logic tạo SQSBatchResponse.
4. Queue ARN, BatchSize, visibility timeout và redrive policy đúng.
5. Một test batch có message lỗi cho kết quả retry đúng message.

**FunctionResponseTypes thuộc event source mapping**, không thuộc environment variable **spring_cloud_function_definition**. Hai cấu hình giải quyết hai chuyện khác nhau.

Nếu project quản lý hạ tầng bằng **SAM/CloudFormation/Terraform**, hãy sửa nguồn IaC và deploy lại thay vì chỉnh CLI thủ công làm cấu hình bị lệch, rồi bị ghi đè lần deploy kế tiếp.

## 15. Kiểm thử Standard batch bằng JUnit 5

Để kiểm thử logic thuần, ta không cần AWS credentials, không cần khởi chạy Lambda runtime, cũng không cần gửi message thật lên SQS.

Tệp **src/test/java/example/sqs/StandardBatchTest.java**:

~~~java
package example.sqs;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Arrays;
import java.util.List;

import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class StandardBatchTest {

    private final SqsPartialBatchApplication app =
        new SqsPartialBatchApplication();

    private static SQSEvent.SQSMessage msg(
            String messageId, String body) {
        var message = new SQSEvent.SQSMessage();
        message.setMessageId(messageId);
        message.setBody(body);
        return message;
    }

    private static SQSEvent batch(
            SQSEvent.SQSMessage... messages) {
        var event = new SQSEvent();
        event.setRecords(Arrays.asList(messages));
        return event;
    }

    @Test
    void reportsOnlyFailedRecordForStandardQueue() {
        var event = batch(
            msg("msg-001",
                "{\"eventId\":\"evt-001\",\"orderId\":\"ORD-101\",\"action\":\"CREATE\"}"),
            msg("msg-002",
                "{\"eventId\":\"evt-002\",\"orderId\":\"ORD-102\",\"action\":\"SIMULATE_RETRY\"}"),
            msg("msg-003",
                "{\"eventId\":\"evt-003\",\"orderId\":\"ORD-103\",\"action\":\"CANCEL\"}")
        );

        var fn = app.processStandardSqs(
            new ObjectMapper(), app.demoProcessor());

        var result = fn.apply(event);

        List<String> failedIds =
            result.getBatchItemFailures().stream()
                .map(item -> item.getItemIdentifier())
                .toList();

        assertEquals(List.of("msg-002"), failedIds);
    }

    @Test
    void reportsEmptyListWhenAllSucceed() {
        var event = batch(
            msg("msg-001",
                "{\"eventId\":\"evt-001\",\"orderId\":\"ORD-101\",\"action\":\"CREATE\"}")
        );

        var result = app.processStandardSqs(
            new ObjectMapper(), app.demoProcessor()
        ).apply(event);

        assertEquals(0,
            result.getBatchItemFailures().size());
    }

    @Test
    void marksMalformedJsonAsFailedRecord() {
        var event = batch(
            msg("msg-bad", "{\"eventId\":")
        );

        var result = app.processStandardSqs(
            new ObjectMapper(), app.demoProcessor()
        ).apply(event);

        assertEquals("msg-bad",
            result.getBatchItemFailures()
                .get(0).getItemIdentifier());
    }
}
~~~

Bài test xác minh Java code chỉ đưa **msg-002** vào danh sách failure, xử lý thành công batch khi mọi record hợp lệ, và báo message sai JSON.

**Chưa đủ để kết luận AWS sẽ retry đúng record**: integration test phải xác nhận event source mapping đã bật ReportBatchItemFailures và FunctionInvoker serialize kết quả đúng schema.

## 16. Kiểm thử FIFO: không xử lý record sau lỗi

Test FIFO nên xác minh **hai việc**: danh sách failed IDs chứa record lỗi và record sau đó; processor **không được gọi** với những record chưa xử lý.

Tệp **src/test/java/example/sqs/FifoBatchTest.java**:

~~~java
package example.sqs;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;

import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class FifoBatchTest {

    @Test
    void stopsAfterFirstFailureAndReportsRemaining() {
        var app = new SqsPartialBatchApplication();

        List<String> processedEventIds =
            new ArrayList<>();

        SqsPartialBatchApplication.OrderEventProcessor processor =
            event -> {
                processedEventIds.add(event.eventId());

                if ("evt-002".equals(event.eventId())) {
                    throw new SqsPartialBatchApplication.RetryableOrderFailure(
                        "Temporary error");
                }
            };

        SQSEvent input = new SQSEvent();
        input.setRecords(List.of(
            msg("msg-001", "evt-001"),
            msg("msg-002", "evt-002"),
            msg("msg-003", "evt-003"),
            msg("msg-004", "evt-004")
        ));

        var fn = app.processFifoSqs(
            new ObjectMapper(), processor);

        var response = fn.apply(input);

        List<String> failedIds =
            response.getBatchItemFailures().stream()
                .map(item -> item.getItemIdentifier())
                .toList();

        assertEquals(
            List.of("msg-002", "msg-003", "msg-004"),
            failedIds);

        assertEquals(
            List.of("evt-001", "evt-002"),
            processedEventIds);
    }

    private static SQSEvent.SQSMessage msg(
            String messageId, String eventId) {
        var message = new SQSEvent.SQSMessage();
        message.setMessageId(messageId);

        message.setBody(
            "{\"eventId\":\"" + eventId
                + "\",\"orderId\":\"ORD-101\",\"action\":\"CREATE\"}");

        return message;
    }
}
~~~

Nếu test thấy **evt-003** xuất hiện trong **processedEventIds** sau khi evt-002 thất bại, vòng lặp không giữ đúng policy đã cam kết. Chỉ kiểm tra danh sách IDs mà không kiểm tra những side effects đã chạy có thể bỏ sót lỗi ordering.

Bài test dùng một processor giả để ghi nhận những record được gọi; trong production cần kiểm tra ordering ở cấp **MessageGroupId**, event source mapping và idempotency.

## 17. Kiểm thử response JSON và FunctionCatalog

Bên cạnh test xử lý batch, cần kiểm tra serialization để phát hiện lỗi key hoặc output wrapper.

### 17.1. JSON serialization của SQSBatchResponse

~~~java
package example.sqs;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import com.amazonaws.services.lambda.runtime.events.SQSBatchResponse;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class SqsBatchResponseJsonTest {

    @Test
    void emitsAwsExpectedJsonKeys() throws Exception {
        var response = new SQSBatchResponse(
            List.of(
                new SQSBatchResponse.BatchItemFailure(
                    "msg-002")
            )
        );

        var mapper = new ObjectMapper();
        var json = mapper.readTree(
            mapper.writeValueAsString(response));

        assertEquals(
            "msg-002",
            json.path("batchItemFailures")
                .get(0).path("itemIdentifier").asText());
    }
}
~~~

Test này phát hiện lỗi serializer trong Java context đang dùng. Vẫn cần thực hiện invocation trên Lambda **với đúng shaded JAR** nếu muốn xác minh FunctionInvoker và event source mapping phối hợp hoàn chỉnh.

### 17.2. FunctionCatalog integration test

~~~java
package example.sqs;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;

@SpringBootTest(classes = SqsPartialBatchApplication.class)
class SqsCatalogTest {

    @Autowired
    FunctionCatalog catalog;

    @Test
    void findsBothBatchFunctions() {
        assertNotNull(
            catalog.lookup("processStandardSqs"));
        assertNotNull(
            catalog.lookup("processFifoSqs"));
    }
}
~~~

Spring context phải đăng ký ObjectMapper phù hợp với dependency JSON của dự án và các bean AWS event types. Test catalog chỉ chứng minh tên bean có mặt, chưa chứng minh Lambda trigger và response format đã đúng.

### 17.3. Kiểm thử trên Lambda staging

Một kế hoạch integration test tối thiểu:

1. Tạo Standard queue staging, Lambda và DLQ.
2. Bật **ReportBatchItemFailures**.
3. Gửi ba messages, trong đó một message được mô phỏng thất bại có kiểm soát.
4. Kiểm tra những message thành công không xuất hiện lại do **cùng batch thất bại** trong điều kiện test, còn message lỗi được giao lại.
5. Kiểm tra ApproximateReceiveCount và DLQ sau ngưỡng redrive.
6. Lặp test cho FIFO với cùng message group, xác minh không xử lý các records sau lỗi.
7. Kiểm tra logs/metrics và dừng/tắt consumer staging sau khi test.

**Không cam kết tuyệt đối messages thành công không bao giờ được giao lại**: SQS là at-least-once, có thể có duplicate dù partial response đúng.

## 18. Những điểm khác biệt giữa SQS, Kinesis và DynamoDB Streams

**ReportBatchItemFailures** xuất hiện ở nhiều loại event source, nhưng **identifier và retry semantics khác nhau**.

| Nguồn | Identifier trong partial failure | Đặc điểm |
| --- | --- | --- |
| **SQS** | **messageId** | Trả những SQS messages chưa xử lý để retry |
| **Kinesis Data Streams** | **sequenceNumber** | Dùng checkpoint theo sequence; có thể retry records từ checkpoint |
| **DynamoDB Streams** | **sequenceNumber** | Tương tự stream checkpoint; không phải SQS messageId |

**Đừng sao chép code SQSBatchResponse và messageId sang Kinesis/DynamoDB Streams**. Những nguồn đó dùng kiểu event/response và quy tắc chia/retry batch khác. Bài này chỉ giải quyết **SQS trigger qua Lambda event source mapping**.

Tương tự, **API Gateway** và **S3 asynchronous notifications** không đọc **SQSBatchResponse** để quyết định HTTP response hoặc retry object notification. Nếu kiến trúc là **S3 → SQS → Lambda**, lớp ngoài của invocation vẫn là **SQSEvent**; trong từng SQS body có thể là JSON thông báo S3. Khi báo thất bại, **itemIdentifier vẫn là SQS messageId**.

## 19. Idempotency: phần không thể bỏ qua

Giả sử processor xử lý **CREATE** bằng cách ghi database. Kịch bản khó:

1. Lambda nhận message có eventId **evt-101**.
2. DB commit thành công.
3. Lambda hết thời gian hoặc response bị mất trước khi AWS xác nhận.
4. SQS giao lại cùng message hoặc producer gửi lại cùng business event.
5. Processor chạy lần nữa và có nguy cơ tạo record trùng.

Partial batch response không giải quyết khoảng trống giữa **side effect commit** và **xác nhận batch outcome**. Cần idempotency ở storage:

~~~mermaid
flowchart TD
    A["OrderEvent eventId"] --> B{"Đã xử lý eventId?"}
    B -- "Có" --> C["Return success/no-op"]
    B -- "Chưa" --> D["Transaction"]
    D --> E["Áp dụng thay đổi nghiệp vụ"]
    E --> F["Ghi dấu eventId đã xử lý"]
    F --> G["Commit"]
    G --> H["Record success"]
~~~

Những chiến lược thường dùng:

- **Unique constraint** cho eventId hoặc business operation key.
- **Transactional inbox** hoặc bảng dedup cùng giao dịch nghiệp vụ.
- **Outbox** khi phải cập nhật DB và phát message.
- **Idempotency token** cho API ngoài nếu downstream hỗ trợ.
- **Conditional write** trong database như DynamoDB khi phù hợp.

**Không mặc định SQS messageId luôn là business idempotency key tối ưu**. Một producer có thể gửi lại cùng business event thành một SQS message mới với messageId khác. Nếu contract có **eventId** ổn định do producer kiểm soát, thường nên dùng eventId/business key cho dedup.

Một record đã được xử lý từ trước có thể được coi là **success** nếu trạng thái bền vững chứng minh side effect đã hoàn tất. Không báo nó là failure vô hạn chỉ vì phát hiện duplicate.

## 20. Monitoring: invocation success không nói hết sự thật

Khi code bắt lỗi từng record và trả **SQSBatchResponse** hợp lệ, invocation của Lambda có thể **được tính là thành công ở cấp function** dù trong đó có nhiều item failures.

Vì thế, nếu chỉ xem metric **Errors** của Lambda, bạn có thể bỏ lỡ hàng nghìn message đang retry. Cần thêm metrics theo record:

| Metric / tín hiệu | Điều muốn phát hiện |
| --- | --- |
| **RecordsReceived** | Số records đã nhận từ batch |
| **RecordsSucceeded** | Số records hoàn thành công việc |
| **RecordsFailed** | Số records được báo trong batchItemFailures |
| **FailureByReason** | Validation, transient, dependency, unknown |
| **SQS ApproximateAgeOfOldestMessage** | Backlog bị tồn đọng |
| **SQS ApproximateNumberOfMessagesVisible** | Khối lượng chưa xử lý |
| **DLQ message count** | Poison messages vượt ngưỡng retry |
| **Lambda Duration/Throttles** | Tốc độ xử lý hoặc capacity bất thường |
| **EventSourceMapping state** | Poller hoạt động và cấu hình đúng |

Các tên **RecordsReceived/RecordsFailed** ở đây là **custom metrics gợi ý**, không phải metric AWS tự tạo sẵn với đúng tên đó.

**Không log toàn bộ message body** vì có thể chứa dữ liệu cá nhân, token hoặc chi tiết đơn hàng. Log các trường tối thiểu như **messageId**, loại lỗi, số lần nhận ước lượng, correlation ID đã được kiểm soát và kết quả xử lý.

AWS cũng khuyến nghị theo dõi những metric SQS như **NumberOfMessagesDeleted** và **ApproximateAgeOfOldestMessage** để phát hiện xử lý bất thường sau khi bật partial responses.

## 21. AWS Powertools Batch Processing có vai trò gì?

Nếu ứng dụng production xử lý batch lớn và có nhiều chiến lược lỗi, không nhất thiết phải tự viết toàn bộ vòng lặp. **Powertools for AWS Lambda (Java)** có tiện ích **Batch Processing** hỗ trợ logic xử lý từng record và tạo partial batch response theo contract AWS.

Lợi ích tiềm năng:

- Giảm mã lặp thu thập failures.
- Chuẩn hóa một phần cấu trúc xử lý Standard/FIFO.
- Kết hợp logging, metrics/tracing và idempotency utility ở những nơi phù hợp.
- Dễ kiểm thử policy retry/record errors khi dùng API được hỗ trợ.

Tuy nhiên, tiện ích không tự quyết định **một business operation có thể retry hay không**, không tự cấp IAM và không biến một side effect không idempotent thành exactly-once.

Khi sử dụng, **khóa version Powertools phù hợp với Java/Build của dự án** và đọc tài liệu API đúng version. Bài này viết một implementation Java nguyên thủy để người học thấy rõ từng thành phần của contract trước khi sử dụng utility.

## 22. Những lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Message lỗi biến mất dù đã đưa vào failures | Mapping chưa bật **ReportBatchItemFailures** | Xem FunctionResponseTypes |
| Toàn lô bị retry | Handler ném exception hoặc response sai schema | Kiểm tra log, itemIdentifier, JSON |
| AWS coi phản hồi không hợp lệ | itemIdentifier rỗng/null/sai ID | Dùng đúng messageId trong batch |
| FIFO phá thứ tự | Vẫn xử lý các records sau khi gặp lỗi | Dừng, trả cả unprocessed IDs |
| Mọi record được ack dù chưa xử lý | Catch exception rồi trả failures rỗng/null | Rà lỗi theo từng record |
| Poison message retry không ngừng | Thiếu DLQ/RedrivePolicy | Kiểm tra maxReceiveCount, retention |
| Message đã xử lý vẫn lặp | At-least-once, timeout/response lost | Thiết kế storage-level idempotency |
| Lỗi SQS body JSON parse | Nhầm Records với body nghiệp vụ | Parse từng message.getBody() |
| Lambda bị lỗi ClassNotFound | Thiếu adapter hoặc shaded JAR không đúng | Kiểm tra FunctionInvoker.class |
| Spring không chọn Function | Sai definition hoặc bean name | FunctionCatalog.lookup và env |
| EventSourceMapping không poll queue | Thiếu IAM/KMS policy hoặc sai ARN/region | Xem mapping state/LastProcessingResult |
| Nhiều failure nhưng Lambda Errors vẫn thấp | Partial response ở cấp function vẫn success | Custom record metrics + SQS/DLQ metrics |
| Sai chính sách FIFO | Standard processing dùng lại cho FIFO | Chọn processFifoSqs và test ordering |
| Lỗi hạ tầng kéo dài mà poll vẫn cao | ReportBatchItemFailures không tự giảm tốc độ poll | Giới hạn concurrency/backoff, cảnh báo downstream |
| Ghi side effect thành công rồi thất bại response | Không có atomic commit cùng ack | Idempotency key và transaction/outbox |
| Consumer không trả được failed IDs | Dùng Consumer<SQSEvent> | Chuyển sang Function<SQSEvent,SQSBatchResponse> |
| Lambda retry nhầm S3 eventId | S3 message lồng trong SQS body | ItemIdentifier vẫn là SQS messageId |

## 23. Bài tập thực hành

**Bài tập 1 — Mặc định và partial response.** Một Standard batch có message IDs **a**, **b**, **c**; b lỗi sau khi a hoàn thành. Giải thích kết quả nếu handler throw exception, nếu catch lỗi rồi trả response rỗng, và nếu trả đúng failure list.

**Bài tập 2 — JSON contract.** Tạo response chỉ báo thất bại **b** và **d** trong batch **a,b,c,d,e**. Viết test chứng minh dùng **messageId**, không dùng business eventId hoặc receiptHandle.

**Bài tập 3 — FIFO.** Với batch **a,b,c,d** trong cùng message group, a thành công và b lỗi. Viết output và một test kiểm tra c/d chưa được gọi processor.

**Bài tập 4 — Chọn đúng policy.** Trong hệ thống có batch được xử lý bằng một database transaction nguyên khối, việc ack riêng record có làm sai contract không? Phân tích lựa chọn toàn batch fail so với thiết kế transaction per-record.

**Bài tập 5 — Kết nối AWS.** Triển khai SAM Standard SQS có DLQ, Lambda timeout 30 giây, visibility timeout phù hợp, BatchSize 10 và FunctionResponseTypes. Đọc lại event source mapping bằng CLI sau deploy.

**Bài tập 6 — Poison pill.** Một message luôn có JSON hỏng. Đề xuất maxReceiveCount, DLQ retention, alarm, quy trình inspect/replay và cách tránh snowball effect.

**Bài tập 7 — Idempotency.** Sau khi commit database, Lambda bị timeout nên message được giao lại. Hãy thiết kế unique constraint/transaction hoặc conditional write theo eventId để đảm bảo side effect không lặp.

**Bài tập 8 — Tổng hợp lỗi.** Một batch gồm một message lỗi validation vĩnh viễn và một message lỗi API timeout tạm thời. Thiết kế policy xử lý theo từng loại, logging và hành động sau khi message vào DLQ.

**Bài tập 9 — Lỗi do cấu hình.** Java unit test trả batchItemFailures đúng nhưng Lambda xóa mọi message. Nêu thứ tự kiểm tra Handler, FunctionCatalog, event source mapping, FunctionResponseTypes, output serialization và version/alias.

**Bài tập 10 — Observability.** Lambda Errors gần bằng 0 nhưng DLQ tăng liên tục. Đề xuất custom record metrics, SQS queue metrics và cảnh báo theo tỷ lệ failed records thay vì chỉ dựa vào invocation-level errors.

### Ghi nhớ

- **SQS event source mapping gửi batch Records**. Nếu một invocation thất bại, mặc định cả lô có thể được giao lại, kể cả các record đã xử lý thành công.
- **Partial batch response chỉ hoạt động đúng khi bật ReportBatchItemFailures và trả đúng batchItemFailures**. Không bật flag mà vẫn trả failed IDs là một lỗi triển khai nguy hiểm.
- **itemIdentifier phải là SQS messageId trong batch**. ID rỗng, sai key hoặc không tồn tại có thể khiến toàn batch bị coi thất bại.
- **Standard** có thể báo record lỗi độc lập. **FIFO** cần dừng khi gặp lỗi và báo cả record lỗi lẫn những record chưa xử lý để giữ ordering.
- **Function<SQSEvent,SQSBatchResponse>** là hợp đồng phù hợp khi dùng Spring Cloud Function + FunctionInvoker. Consumer không tự trả response từng phần.
- **DLQ, idempotency, retry, visibility timeout, IAM và record-level metrics** vẫn cần thiết. Partial response giảm retry không cần thiết nhưng không hứa exactly-once.
- **Không phải workload nào cũng nên bật**: batch atomic, lỗi hệ thống toàn cục hoặc FIFO ordering phức tạp đòi một chiến lược khác hoặc kiểm thử bổ sung.

### Tài liệu tham khảo

- [Spring Cloud Function — AWS Lambda adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html): FunctionInvoker và kiểu Function<SQSEvent,SQSBatchResponse>.
- [AWS Lambda — Handling errors for an SQS event source](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html): ReportBatchItemFailures, success/failure conditions, FIFO và scaling behavior.
- [AWS Lambda — SQS event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html): visibility timeout, IAM, batch window và DLQ.
- [AWS Lambda — Using Lambda with SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html): at-least-once, polling, visibility timeout, Standard/FIFO.
- [AWS Lambda — Java partial batch example](https://docs.aws.amazon.com/lambda/latest/dg/example_serverless_SQS_Lambda_batch_item_failures_section.html): SQSBatchResponse Java API và BatchItemFailure.
- [AWS SAM — SQS event source](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-property-function-sqs.html): FunctionResponseTypes, BatchSize và các thuộc tính nguồn.
- [AWS Prescriptive Guidance — Partial batch response best practices](https://docs.aws.amazon.com/prescriptive-guidance/latest/lambda-event-filtering-partial-batch-responses-for-sqs/best-practices-partial-batch-responses.html): DLQ, idempotency, monitoring và tránh snowball pattern.
