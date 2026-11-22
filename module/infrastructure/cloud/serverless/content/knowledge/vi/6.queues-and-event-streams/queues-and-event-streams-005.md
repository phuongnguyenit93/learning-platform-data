# Xử lý theo batch và xác nhận từng phần thất bại

Trong hệ thống serverless, một queue hoặc event stream thường gom nhiều message thành một batch rồi chuyển cho Java function xử lý trong cùng một lần invocation. Cách làm này giảm số lần gọi function và có thể tăng throughput, nhưng tạo ra một câu hỏi quan trọng: nếu chỉ một message trong batch bị lỗi thì hệ thống có phải gửi lại toàn bộ batch hay có thể chỉ gửi lại message lỗi?

**Partial batch failure** cho phép function báo chính xác những item chưa xử lý thành công, nếu trigger và nền tảng hỗ trợ cơ chế này. Khi thiết kế đúng, các item đã hoàn tất có thể được xác nhận, còn item lỗi được retry theo chính sách của nguồn dữ liệu. Bài học này giải thích cách hoạt động của batch, acknowledgment, retry và partial failure; đồng thời hướng dẫn cách triển khai Java handler an toàn.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao queue và event stream gom nhiều bản ghi thành batch.
- Phân biệt xác nhận toàn batch với xác nhận từng item.
- Mô tả cách partial batch response ảnh hưởng đến retry và khả năng phát lại dữ liệu.
- Viết Java handler thu thập ID của các message thất bại.
- Thiết kế idempotency, DLQ và logging cho xử lý batch.
- Nhận biết khác biệt giữa queue message và stream record khi xác định item cần retry.

## 1. Batch processing là gì?

**Batch processing** là cách xử lý nhiều message hoặc record trong cùng một đơn vị công việc. Nền tảng có thể đợi đủ số lượng item, hoặc đợi hết một khoảng thời gian gom batch, rồi mới gọi function.

Ví dụ, thay vì gọi function 100 lần cho 100 message, queue trigger có thể đưa 10 message vào mỗi batch và gọi function 10 lần. Handler nhận danh sách message, xử lý từng item rồi trả kết quả cho nền tảng.

~~~mermaid
flowchart LR
    A["Producer"] --> B["Queue / Event Stream"]
    B --> C["Gom batch"]
    C --> D["Java Function"]
    D --> E["Xử lý từng item"]
    E --> F["Kết quả / Acknowledgment"]
    F --> B
~~~

Batch có thể giúp:

- Giảm số invocation và chi phí khởi tạo function.
- Tăng throughput khi một lần gọi xử lý được nhiều item.
- Tận dụng kết nối hoặc tài nguyên dùng chung trong một lần xử lý.
- Giảm overhead mạng và serialization khi hệ thống có nhiều message nhỏ.

Tuy nhiên, batch lớn cũng làm tăng lượng dữ liệu một invocation phải giữ trong bộ nhớ, thời gian xử lý và phạm vi ảnh hưởng nếu function timeout. Nếu nền tảng chỉ hỗ trợ xác nhận toàn batch, một item lỗi có thể khiến những item đã xử lý thành công bị giao lại.

### Batch size và batch window

Hai cấu hình thường gặp:

- **Batch size:** số item tối đa trong một batch.
- **Batch window:** khoảng thời gian tối đa nền tảng chờ để gom thêm item trước khi gửi batch.

Batch size lớn có thể tăng hiệu quả khi tải cao, nhưng cũng làm tăng độ trễ khi tải thấp và tăng thời gian xử lý một invocation. Batch window dài giúp gom đủ item trong hệ thống ít traffic, nhưng người dùng phải chờ lâu hơn trước khi function bắt đầu.

| Lựa chọn | Lợi ích | Đánh đổi |
|---|---|---|
| Batch nhỏ | Độ trễ thấp, phạm vi lỗi nhỏ, dễ xử lý timeout | Nhiều invocation và overhead hơn |
| Batch lớn | Throughput cao, giảm số invocation | Tốn bộ nhớ, thời gian xử lý dài, retry có thể tốn kém |
| Batch window ngắn | Bắt đầu xử lý sớm | Có thể thường xuyên nhận batch nhỏ |
| Batch window dài | Có cơ hội gom nhiều item hơn | Tăng thời gian chờ trước xử lý |

Hãy chọn batch size và window dựa trên phân bố tải, giới hạn thời gian function, bộ nhớ, kích thước payload và yêu cầu latency. Không nên chỉ tối đa hóa batch size mà bỏ qua thời gian xử lý p95/p99 hoặc khả năng retry.

## 2. Acknowledgment và retry khi xử lý batch

Sau khi function nhận batch, nền tảng cần biết item nào đã xử lý xong để không tiếp tục giao lại, và item nào cần thử lại.

**Acknowledgment (ack)** là tín hiệu cho biết message hoặc record đã được xử lý theo cơ chế của nguồn. **Negative acknowledgment (nack)** hoặc kết quả thất bại cho biết item cần được giao lại hoặc xử lý theo luồng lỗi. Tên gọi và hành vi cụ thể khác nhau giữa queue, broker và stream service.

Có hai kiểu kết quả tổng quát:

### Xác nhận toàn batch

Function trả thành công thì nền tảng xem toàn bộ batch là thành công. Nếu function báo lỗi hoặc invocation timeout, toàn bộ batch có thể được giao lại.

Ví dụ batch có A, B, C, D:

- A, B và D đã ghi kết quả thành công.
- C gặp lỗi tạm thời.
- Function ném exception.
- Nền tảng giao lại cả A, B, C và D.

A, B và D có thể bị xử lý lặp. Nếu không có idempotency, việc gửi email, trừ tiền hoặc tạo bản ghi có thể xảy ra nhiều lần.

### Xác nhận từng phần (partial batch response)

Function trả danh sách ID của những item thất bại. Nền tảng xác nhận các item còn lại và retry các item được báo lỗi, theo semantics của trigger.

~~~mermaid
flowchart TD
    A["Batch: A, B, C, D"] --> B["Function xử lý từng item"]
    B --> C["A, B, D thành công"]
    B --> D["C thất bại"]
    C --> E["Ack A, B, D"]
    D --> F["Retry C"]
~~~

Với cùng ví dụ, A, B và D không cần bị xử lý lại chỉ vì C lỗi. Đây là lợi ích chính của partial batch failure.

Tuy nhiên, partial response không đảm bảo exactly-once. Function có thể thực hiện side effect rồi timeout trước khi gửi response; nền tảng không biết item đã hoàn tất và có thể giao lại. Consumer vẫn cần idempotency và thao tác ghi nhận kết quả an toàn.

## 3. Partial batch failure hoạt động khác nhau theo nguồn dữ liệu

Không phải mọi trigger đều có cùng hợp đồng acknowledgment. Trước khi viết handler, cần đọc semantics của nguồn sự kiện.

| Nguồn | Đơn vị nhận diện item lỗi | Hành vi retry thường gặp |
|---|---|---|
| Queue message như Amazon SQS | Message ID | Có thể retry riêng message được liệt kê trong partial response khi event source mapping được cấu hình hỗ trợ |
| Ordered queue / FIFO | Message ID cùng quy tắc thứ tự trong message group | Cần dừng hoặc giữ lại các message sau điểm lỗi để không phá vỡ thứ tự |
| Stream có shard/partition như Kinesis hoặc DynamoDB Streams | Sequence number hoặc checkpoint identifier | Checkpoint có thể khiến các record từ vị trí lỗi trở đi được phát lại, không nhất thiết chỉ một record |
| Pub/Sub hoặc broker khác | Message ID, ack token hoặc delivery handle | Cơ chế ack/nack và batch response tùy connector và runtime |

### Queue message

Với queue như Amazon SQS tích hợp AWS Lambda, một invocation có thể nhận nhiều SQS message. Nếu bật response type ReportBatchItemFailures trong event source mapping, handler trả về các message ID thất bại. Lambda có thể xóa những message thành công và chỉ retry các message thất bại.

Nếu không bật cấu hình này, việc trả một cấu trúc partial failure có thể không được nền tảng sử dụng. Khi function ném exception hoặc timeout, cả batch có thể bị retry theo cơ chế queue integration.

### FIFO queue và thứ tự

FIFO queue duy trì thứ tự trong phạm vi message group. Nếu một message trong batch thất bại, tiếp tục xử lý những message phía sau cùng luồng thứ tự có thể khiến nghiệp vụ tiến vượt qua một bước chưa hoàn thành.

Một chính sách an toàn thường là dừng xử lý sau message lỗi đầu tiên và báo thất bại cho message đó cùng những message chưa xử lý phía sau trong batch. Nền tảng sẽ giao lại chúng theo quy tắc FIFO. Điều này có thể làm giảm throughput, nhưng bảo toàn thứ tự cần thiết.

### Event stream và checkpoint

Với stream có shard hoặc partition, vị trí record được biểu diễn bằng sequence number hoặc offset. Khi record ở giữa batch thất bại, nền tảng có thể cần phát lại từ checkpoint thấp nhất chưa hoàn tất. Vì vậy, những record đứng sau record lỗi có thể được xử lý lại dù lần trước đã chạy qua.

Đây là khác biệt quan trọng: **partial batch failure trong queue message không đồng nghĩa với retry độc lập từng record trong mọi stream**. Handler phải dùng đúng định danh mà stream integration yêu cầu và logic xử lý cần chịu được replay.

## 4. Java handler cho SQS: báo ID của message thất bại

Ví dụ dưới đây dùng AWS Lambda Java events library và minh họa queue tiêu chuẩn (standard queue). Handler xử lý từng message độc lập, ghi nhận ID khi có lỗi và trả SQSBatchResponse.

Ví dụ dùng Java 8 trở lên; các lớp event đến từ thư viện aws-lambda-java-events.

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.amazonaws.services.lambda.runtime.events.SQSBatchResponse;

import java.util.ArrayList;
import java.util.List;

public class OrderBatchHandler
        implements RequestHandler<SQSEvent, SQSBatchResponse> {

    @Override
    public SQSBatchResponse handleRequest(
            SQSEvent event, Context context) {

        List<SQSBatchResponse.BatchItemFailure> failures =
                new ArrayList<>();

        for (SQSEvent.SQSMessage message : event.getRecords()) {
            try {
                processMessage(message);
            } catch (Exception ex) {
                context.getLogger().log(
                        "Failed messageId=" + message.getMessageId()
                                + ", reason=" + ex.getMessage());

                failures.add(
                        new SQSBatchResponse.BatchItemFailure(
                                message.getMessageId()));
            }
        }

        return new SQSBatchResponse(failures);
    }

    private void processMessage(SQSEvent.SQSMessage message) {
        // Parse payload, validate and perform an idempotent business operation.
        // Throw an exception when this message has not been processed safely.
    }
}
~~~

Khi không có item thất bại, danh sách failures rỗng. Khi một hoặc nhiều item lỗi, response chứa đúng message ID của các item cần retry.

Để nền tảng dùng response này, event source mapping của Lambda cần bật ReportBatchItemFailures. Ví dụ cấu hình AWS SAM rút gọn:

~~~yaml
Events:
  OrdersQueue:
    Type: SQS
    Properties:
      Queue: !GetAtt OrdersQueue.Arn
      BatchSize: 10
      FunctionResponseTypes:
        - ReportBatchItemFailures
~~~

Tên property và khả năng cấu hình phụ thuộc công cụ triển khai, nhưng nguyên tắc không đổi: phải bật chế độ partial response ở tích hợp event source. Chỉ sửa Java handler là chưa đủ.

### Không nuốt lỗi rồi trả thành công

Nếu catch exception nhưng không thêm message ID vào danh sách failures, function sẽ báo message đó thành công. Nền tảng có thể xóa hoặc xác nhận message và dữ liệu sẽ bị mất khỏi luồng retry.

Ngược lại, nếu thêm ID của message đã xử lý thành công, nền tảng sẽ giao lại message không cần thiết. Vì vậy, chỉ thêm ID khi handler chưa hoàn tất an toàn các tác dụng phụ của item.

## 5. Xử lý FIFO: dừng tại lỗi đầu tiên

Với FIFO queue, nếu thứ tự trong message group có ý nghĩa nghiệp vụ, handler cần tránh xử lý tiếp những message sau item thất bại. Mẫu xử lý đơn giản dưới đây minh họa quy tắc đó; trong hệ thống thực tế cần xem xét message group và semantics của nguồn.

~~~java
List<SQSBatchResponse.BatchItemFailure> failures =
        new ArrayList<>();

boolean stopAfterFailure = false;

for (SQSEvent.SQSMessage message : event.getRecords()) {
    if (stopAfterFailure) {
        failures.add(new SQSBatchResponse.BatchItemFailure(
                message.getMessageId()));
        continue;
    }

    try {
        processMessage(message);
    } catch (Exception ex) {
        failures.add(new SQSBatchResponse.BatchItemFailure(
                message.getMessageId()));
        stopAfterFailure = true;
    }
}

return new SQSBatchResponse(failures);
~~~

Đoạn code trên bảo toàn thứ tự toàn batch bằng cách không xử lý message phía sau điểm lỗi. Nó có thể giữ lại cả message thuộc group khác trong cùng batch nếu nguồn trộn nhiều group; đây là lựa chọn thận trọng, cần cân nhắc với throughput và cách nền tảng phân phối group. Với hệ thống có yêu cầu tối ưu theo group, cần triển khai theo semantics chính xác của broker.

## 6. Quy tắc xác định một item đã thành công

Một item chỉ nên được coi là thành công khi ứng dụng đã hoàn tất phần việc cần thiết và có thể chịu được việc nền tảng không gửi lại item đó.

Ví dụ một function xử lý OrderPlaced:

1. Đọc và kiểm tra schema của event.
2. Kiểm tra eventId hoặc business key đã được xử lý chưa.
3. Thực hiện thao tác nghiệp vụ.
4. Lưu kết quả và dấu mốc idempotency một cách an toàn.
5. Chỉ sau đó mới xem item là thành công trong batch response.

Nếu function gọi dịch vụ thanh toán thành công nhưng không lưu được trạng thái, lần retry có thể gọi thanh toán lần nữa. Dùng idempotency key ổn định ở dịch vụ thanh toán và lưu trạng thái giao dịch giúp giảm rủi ro.

Không nên đánh dấu item thành công chỉ vì function đã bắt đầu xử lý hoặc đã ghi log. Thành công phải được định nghĩa theo kết quả nghiệp vụ đã commit.

### Tránh một transaction lớn cho cả batch khi không cần thiết

Nếu mỗi item là một giao dịch nghiệp vụ độc lập, hãy xử lý và commit từng item riêng. Một transaction bao trùm toàn batch có thể làm mất lợi ích partial failure: chỉ một lỗi có thể rollback tất cả item, hoặc transaction giữ lock quá lâu.

Nếu nghiệp vụ yêu cầu toàn bộ batch phải thành công cùng nhau, đó là một quyết định atomic batch rõ ràng. Khi đó partial acknowledgment không thể tự biến các thao tác thành một giao dịch phân tán nguyên tử.

## 7. Retry, visibility timeout và dead-letter queue

Partial response chỉ xác định item nào thất bại; chính sách retry vẫn do nguồn dữ liệu và cấu hình tích hợp quyết định.

Với queue, cần hiểu:

- **Visibility timeout / message lock:** khoảng thời gian message tạm thời không được giao cho consumer khác trong khi đang xử lý.
- **Retry policy:** khi nào message được giao lại, có backoff hay không và số lần thử tối đa.
- **Receive count / delivery attempt:** số lần message đã được giao.
- **Dead-letter queue (DLQ):** nơi nhận message đã vượt ngưỡng retry hoặc không thể xử lý theo chính sách.
- **Redrive:** quy trình đưa message từ DLQ trở lại queue để thử xử lý sau khi đã sửa nguyên nhân.

Visibility timeout hoặc lock duration phải đủ cho thời gian xử lý dự kiến, bao gồm batch và các bước gọi dịch vụ phụ thuộc. Nếu lock hết trước khi handler hoàn tất, message có thể được giao đồng thời cho consumer khác. Cần theo dõi tuổi message, số lần giao và độ dài queue.

### Poison message

**Poison message** là message liên tục thất bại do dữ liệu sai, schema không hỗ trợ, thiếu dữ liệu bắt buộc hoặc một lỗi không thể tự phục hồi.

Nếu retry vô hạn, một poison message có thể chiếm năng lực xử lý, làm tăng chi phí và trì hoãn message tốt. Cần phân loại:

- Lỗi tạm thời như timeout hoặc throttling: có thể retry với backoff.
- Lỗi dữ liệu vĩnh viễn như schema không hợp lệ: ghi nhận, quarantine hoặc chuyển DLQ theo chính sách.
- Lỗi do bug ứng dụng: giới hạn retry, phát cảnh báo và sửa handler trước khi redrive.

DLQ không phải nơi để quên dữ liệu. Cần có người chịu trách nhiệm xem xét, dashboard, thời hạn lưu, quy trình sửa payload và kiểm soát replay.

## 8. Idempotency và side effect trong batch

Queue và event stream thường cung cấp semantics giao nhận ít nhất một lần trong nhiều cấu hình. Vì vậy, cùng một item có thể được xử lý nhiều hơn một lần, kể cả khi partial response được bật.

Các biện pháp thường dùng:

- Dùng eventId ổn định làm khóa deduplication.
- Tạo unique constraint hoặc conditional write ở database.
- Ghi kết quả nghiệp vụ và trạng thái đã xử lý trong cùng transaction khi có thể.
- Gửi idempotency key đến dịch vụ bên ngoài nếu API hỗ trợ.
- Dùng transactional outbox khi cần phát event sau khi commit dữ liệu.
- Giữ side effect tách biệt với việc parse và validate message.

Một bảng idempotency có thể có các trường:

| Trường | Mục đích |
|---|---|
| event_id | Định danh ổn định của event |
| status | RECEIVED, PROCESSING, SUCCEEDED hoặc FAILED |
| result_reference | Mã tham chiếu kết quả nghiệp vụ |
| first_seen_at | Thời điểm consumer lần đầu tiếp nhận |
| completed_at | Thời điểm xử lý hoàn tất |
| attempt_count | Số lần thử đã ghi nhận |

Việc tạo trạng thái PROCESSING cần có lease hoặc cơ chế phục hồi nếu function chết giữa chừng. Nếu chỉ đánh dấu event đã xử lý trước khi side effect hoàn tất, lần retry sau có thể bị bỏ qua dù nghiệp vụ chưa thành công.

## 9. Batch size, timeout và concurrency

Batch size, thời gian xử lý và concurrency liên quan trực tiếp:

- Batch lớn làm giảm invocation nhưng một batch có thể cần nhiều thời gian hơn.
- Function timeout có thể khiến toàn bộ batch hoặc phần chưa xác nhận bị giao lại.
- Concurrency cao giúp tăng tốc độ tiêu thụ nhưng có thể làm database hoặc API phía sau quá tải.
- Một batch có nhiều item nặng có thể gây lệch thời gian xử lý giữa các invocation.
- Partial failure giảm việc chạy lại item đã thành công, nhưng không làm mất chi phí retry và kiểm tra.

Hãy đo ít nhất:

- Batch size thực tế và tỷ lệ batch đầy.
- Thời gian xử lý từng item và toàn batch.
- Tỷ lệ batch có lỗi, số item thất bại trên mỗi batch.
- Số lần delivery/retry và số message vào DLQ.
- Queue depth, tuổi message lâu nhất và thời gian chờ.
- Throttling, concurrency và lỗi từ dịch vụ phụ thuộc.
- Chi phí trên mỗi item được xử lý thành công.

Có thể bắt đầu với batch nhỏ, đo tải và tăng dần. Khi tăng batch size, cần chạy kiểm thử với payload lớn, item xử lý chậm, lỗi xen kẽ và timeout để tìm giới hạn an toàn.

## 10. Kiểm thử partial batch failure

Một bộ kiểm thử tốt cần xác minh cả danh sách failure trả về và side effect thực tế.

| Tình huống | Kết quả mong đợi |
|---|---|
| Tất cả item thành công | Response có danh sách failure rỗng |
| Một item lỗi tạm thời | Chỉ ID item đó được trả về trong partial response |
| Nhiều item lỗi | Tất cả ID chưa hoàn tất an toàn được trả về |
| Lỗi sau side effect nhưng trước khi commit trạng thái | Retry không tạo tác dụng phụ trùng nhờ idempotency |
| Function timeout | Hành vi redelivery phù hợp với semantics của nguồn; item đã commit chịu được replay |
| Poison message | Có giới hạn retry và đường chuyển DLQ/quarantine |
| FIFO gặp lỗi | Không xử lý vượt qua điểm lỗi theo quy tắc thứ tự |
| Stream record lỗi | Trả đúng sequence number/checkpoint và kiểm tra các record sau có thể replay |
| Partial response chưa bật | Test cấu hình xác nhận nền tảng có thể vẫn xử lý theo chế độ toàn batch |

Unit test có thể mock service nghiệp vụ để kiểm tra message ID được đưa vào response. Integration test cần chạy với event source mapping hoặc broker thật/test environment tương ứng để xác minh ack, retry, lock timeout, ordering và DLQ.

## 11. Checklist trước khi triển khai batch handler

- [ ] Đã xác định nguồn event là queue, FIFO queue hay ordered stream.
- [ ] Đã đọc semantics acknowledgment, retry, ordering và checkpoint của trigger.
- [ ] Đã bật cấu hình partial batch response nếu nền tảng yêu cầu.
- [ ] Handler chỉ báo thất bại cho item chưa hoàn tất an toàn.
- [ ] Message ID hoặc sequence number được trả đúng định dạng nền tảng yêu cầu.
- [ ] FIFO handler dừng hoặc giữ lại item phía sau điểm lỗi theo quy tắc thứ tự.
- [ ] Side effect có idempotency để chịu được redelivery và replay.
- [ ] Batch size, batch window, timeout và concurrency đã được đo kiểm.
- [ ] Visibility timeout hoặc message lock đủ cho thời gian xử lý.
- [ ] Có retry limit, DLQ, cảnh báo và quy trình redrive.
- [ ] Log có event ID, message ID, attempt và kết quả mà không lộ dữ liệu nhạy cảm.
- [ ] Đã kiểm thử lỗi một item, nhiều item, timeout, duplicate, poison message và stream checkpoint.

## Tự kiểm tra

1. Nếu một batch có 10 message và chỉ message thứ 4 lỗi, xác nhận toàn batch có thể gây ra điều gì?
2. Partial batch response cần được bật ở đâu ngoài phần code Java?
3. Vì sao partial batch failure không đảm bảo exactly-once?
4. Với FIFO queue, vì sao cần dừng xử lý các message sau message lỗi?
5. Vì sao stream có sequence number có thể retry từ checkpoint lỗi trở đi thay vì chỉ retry một record?
6. Batch size lớn ảnh hưởng thế nào đến latency, timeout và phạm vi retry?
7. Khi nào một message nên được chuyển vào DLQ thay vì tiếp tục retry?

Batch processing giúp function xử lý hiệu quả nhiều message trong một invocation. Partial batch failure giúp giới hạn retry vào những item chưa hoàn tất theo hợp đồng của trigger. Để cơ chế này an toàn, đội phát triển phải trả đúng định danh lỗi, bật đúng cấu hình tích hợp, giữ thứ tự khi cần, thiết kế idempotency và theo dõi retry cùng DLQ. Khi các quy tắc này được kiểm chứng trên nguồn event thực tế, batch có thể tăng throughput mà vẫn bảo toàn tính đúng đắn của nghiệp vụ.

