# Báo lỗi từng phần trong batch và chuyển tệp lỗi sang quarantine

Một pipeline xử lý tệp theo sự kiện thường nhận nhiều thông báo trong một lần gọi function. Mỗi thông báo có thể trỏ tới một tệp trong object storage; bên trong tệp lại có hàng trăm hoặc hàng nghìn record. Chỉ một record sai định dạng cũng không nên làm mất kết quả của các record hợp lệ, nhưng hệ thống phải giữ được bằng chứng của dữ liệu lỗi và có cách xử lý lại khi nguyên nhân được khắc phục.

Bài học này xây dựng một pipeline Java serverless có khả năng:

- Xử lý độc lập từng message trong một batch.
- Tiếp tục xử lý record hợp lệ khi một số record không hợp lệ.
- Trả về đúng các message cần retry.
- Ghi record hoặc tệp không thể xử lý vào quarantine một cách bền vững.
- Chỉ xác nhận message sau khi kết quả và thông tin lỗi đã được lưu an toàn.
- Chống xử lý trùng khi broker giao lại message.
- Replay dữ liệu sau khi sửa lỗi mà không tạo side effect lặp.

Một điểm cần phân biệt xuyên suốt bài học: **partial batch failure ở cấp message** và **partial failure ở cấp record bên trong tệp** là hai cơ chế khác nhau. Với SQS-triggered Lambda, response partial batch báo lỗi theo message ID. Nếu một message đại diện cho cả tệp, function phải tự lưu những record lỗi vào quarantine; nó không thể yêu cầu SQS chỉ gửi lại một vài dòng trong tệp.

## 1. Bối cảnh và mục tiêu của dự án

Giả sử một hệ thống nhận tệp đơn hàng hoặc dữ liệu sản phẩm do đối tác tải lên. Tệp được lưu trong object storage, sau đó một sự kiện tạo object được đưa vào queue. Java function đọc tệp, kiểm tra từng record và ghi dữ liệu hợp lệ vào hệ thống đích.

Ví dụ tệp CSV:

~~~csv
order_id,customer_id,amount,currency
ORD-1001,CUS-01,125.50,VND
ORD-1002,CUS-02,invalid,VND
ORD-1003,CUS-03,89.00,VND
ORD-1004,,42.00,VND
~~~

Trong ví dụ này:

- ORD-1001 hợp lệ và có thể được xử lý.
- ORD-1002 có amount không phải số.
- ORD-1003 hợp lệ và có thể được xử lý.
- ORD-1004 thiếu customer_id.

Nếu toàn bộ batch bị retry chỉ vì hai dòng lỗi, các dòng hợp lệ sẽ bị đọc và xử lý lại nhiều lần. Nếu function bỏ qua lỗi rồi ack message, hai dòng lỗi có thể biến mất khỏi quy trình mà không ai biết.

Thiết kế cần giữ lại kết quả theo từng cấp:

| Cấp | Đơn vị xử lý | Kết quả lỗi |
|---|---|---|
| Message batch | Một SQS message hoặc event message | Trả message ID trong partial batch response để retry |
| File | Một object/file được tham chiếu bởi message | Quarantine file nếu không thể đọc hoặc không thể xử lý ở cấp file |
| Record | Một dòng/entry bên trong file | Ghi record lỗi vào rejected-records artifact |
| Side effect | Một bản ghi được ghi vào database/API | Dùng idempotency key và version để tránh lặp |

Mục tiêu không phải là làm mọi lỗi biến mất khỏi queue. Mục tiêu là phân loại đúng lỗi, giữ lại dữ liệu cần sửa và chỉ retry công việc có khả năng thành công sau khi thử lại.

## 2. Kiến trúc tổng thể

Một kiến trúc tham khảo:

~~~mermaid
flowchart LR
    A["Uploader / partner"] --> B["Object storage: incoming/"]
    B --> C["Object-created event"]
    C --> D["Queue"]
    D --> E["Java serverless file processor"]
    E --> F["Validate file and records"]
    F --> G["Valid records"]
    F --> H["Rejected records"]
    G --> I["Database / downstream service"]
    H --> J["Quarantine storage"]
    E --> K["Durable job manifest"]
    E --> L["Partial batch response"]
    L --> D
    M["Replay / repair workflow"] --> J
    M --> E
~~~

| Thành phần | Trách nhiệm |
|---|---|
| Object storage | Lưu tệp đầu vào bất biến hoặc có version |
| Event notification | Báo có object mới |
| Queue | Buffer, retry và phân phối message |
| Java file processor | Đọc tệp, phân loại lỗi và điều phối batch |
| Validator/parser | Kiểm tra cấu trúc tệp và từng record |
| Database/downstream | Lưu kết quả của record hợp lệ |
| Quarantine storage | Lưu tệp hoặc record không thể xử lý |
| Job manifest | Theo dõi trạng thái, số lượng và tiến độ |
| Replay workflow | Sửa dữ liệu rồi chạy lại có kiểm soát |

Có thể dùng S3 + SQS + AWS Lambda làm ví dụ cụ thể, nhưng mô hình áp dụng được cho object storage, event broker và function service tương đương. Chi tiết response và cấu hình trigger phụ thuộc provider.

### 2.1. Tách event khỏi nội dung tệp

Queue nên mang tham chiếu đến object thay vì đẩy toàn bộ nội dung tệp vào message:

~~~json
{
  "bucket": "partner-ingestion",
  "key": "incoming/partner-17/orders-2026-11-17.csv",
  "versionId": "3Lg...example",
  "eventId": "evt-9c2f",
  "receivedAt": "2026-11-17T10:15:30Z"
}
~~~

Cách này giúp message nhỏ, tránh giới hạn kích thước queue và cho phép function tải tệp theo nhu cầu. Nếu object storage có versioning, dùng versionId để đọc đúng object đã tạo event. Nếu không có version ID, lưu một định danh ổn định khác và tính checksum nội dung khi tải.

Không chỉ dựa vào object key nếu cùng một key có thể bị ghi đè. Một event cũ có thể vô tình đọc nội dung mới và xử lý sai phiên bản tệp.

## 3. Phân loại lỗi trước khi chọn hành động

Không phải lỗi nào cũng cần retry. Cần phân biệt lỗi tạm thời, lỗi dữ liệu, lỗi ở toàn bộ tệp và lỗi hạ tầng.

| Loại lỗi | Ví dụ | Hành động |
|---|---|---|
| Transient infrastructure | Object storage timeout, database throttling, network reset | Retry message |
| Transient downstream | Search/database tạm unavailable, HTTP 503 | Retry với backoff |
| Invalid record | Thiếu field bắt buộc, số tiền sai định dạng, enum không hợp lệ | Ghi record vào quarantine; tiếp tục record khác |
| Invalid file | Encoding hỏng, header không đúng, định dạng không được hỗ trợ | Quarantine toàn bộ file |
| Unsupported schema | Schema version không được consumer hỗ trợ | Quarantine file hoặc đưa vào luồng tương thích thủ công |
| Duplicate delivery | Cùng event/object được gửi lại | Nhận diện idempotency và trả kết quả cũ |
| Configuration/security | Credential sai, quyền đọc object bị thu hồi | Alert; retry có giới hạn hoặc dừng theo policy |

### 3.1. Lỗi tạm thời và lỗi vĩnh viễn

**Lỗi tạm thời** có khả năng biến mất nếu thử lại: timeout, connection reset, throttling hoặc service unavailable. Không đưa những lỗi này vào quarantine ngay lập tức vì dữ liệu có thể hoàn toàn hợp lệ.

**Lỗi vĩnh viễn ở record** thường không thay đổi khi retry cùng dữ liệu: thiếu trường bắt buộc, sai kiểu, mã tham chiếu không tồn tại hoặc giá trị nằm ngoài domain. Ghi lại record và lý do để người gửi sửa.

**Lỗi vĩnh viễn ở file** khiến không thể đọc hoặc hiểu bất kỳ record nào: file bị hỏng, encoding không hợp lệ, header không đúng contract hoặc format không được hỗ trợ. Quarantine bản gốc cùng metadata.

Không phân loại một HTTP 500 từ downstream thành lỗi dữ liệu. Nếu lỗi hạ tầng bị ghi vào quarantine, dữ liệu hợp lệ sẽ bị loại bỏ chỉ vì một dependency tạm thời gặp sự cố.

## 4. State machine của một file job

Theo dõi trạng thái file bằng một manifest bền vững giúp function phục hồi sau timeout hoặc restart.

Các trạng thái tham khảo:

| Trạng thái | Ý nghĩa |
|---|---|
| RECEIVED | Đã nhận event và tạo job identity |
| PROCESSING | Đang đọc và xử lý file |
| RETRY_PENDING | Gặp lỗi tạm thời, chờ broker giao lại |
| COMPLETED | Tất cả record hợp lệ đã được xử lý |
| COMPLETED_WITH_ERRORS | Record hợp lệ đã xử lý, record lỗi đã được lưu quarantine |
| QUARANTINED | Toàn bộ file không thể xử lý và bản gốc đã được lưu an toàn |
| REPLAY_PENDING | File hoặc record đã sửa được đưa vào replay |
| REPLAYING | Replay job đang chạy |
| REPLAYED | Replay hoàn tất |

Chuyển trạng thái minh họa:

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> PROCESSING
    PROCESSING --> COMPLETED
    PROCESSING --> COMPLETED_WITH_ERRORS
    PROCESSING --> QUARANTINED
    PROCESSING --> RETRY_PENDING: transient failure
    RETRY_PENDING --> PROCESSING: redelivery
    QUARANTINED --> REPLAY_PENDING: approved repair
    COMPLETED_WITH_ERRORS --> REPLAY_PENDING: corrected records
    REPLAY_PENDING --> REPLAYING
    REPLAYING --> REPLAYED
    COMPLETED --> [*]
    COMPLETED_WITH_ERRORS --> [*]
    QUARANTINED --> [*]
    REPLAYED --> [*]
~~~

Manifest nên lưu ít nhất:

- Job ID và object identity.
- Source bucket/container, key và version.
- Checksum của nội dung.
- Schema version và processor version.
- Trạng thái hiện tại.
- Tổng số record, số thành công và số bị từ chối.
- Số lần thử và thời điểm xử lý.
- Quarantine object key nếu có.
- Lý do lỗi đã được chuẩn hóa.
- Thời điểm bắt đầu/kết thúc và correlation ID.

Không dùng biến static trong Java function để giữ trạng thái job. Function có thể bị scale-out, restart hoặc chạy lại trên instance khác.

RETRY_PENDING là trạng thái quan sát được của job khi queue đang chờ redelivery. Nếu manifest store cũng đang lỗi, không để việc ghi trạng thái retry trở thành điều kiện để trả message failure; queue delivery metadata vẫn là nguồn sự thật cho lần thử tiếp theo.

## 5. Partial batch response ở cấp SQS message

Một lần gọi Lambda có thể nhận nhiều SQS message. Nếu một message thất bại, cách xử lý mặc định phụ thuộc cấu hình event source mapping. Với partial batch response, function có thể chỉ rõ message nào cần được queue giao lại.

Đối với SQS, identifier trong response là **messageId** của SQS message. Nó không phải object key, event ID của producer hoặc số dòng trong file.

Ví dụ:

~~~json
{
  "batchItemFailures": [
    {
      "itemIdentifier": "sqs-message-id-002"
    }
  ]
}
~~~

Nếu batch có 5 message và chỉ message thứ hai gặp lỗi tạm thời, function trả message ID đó. Những message còn lại được xem là đã xử lý thành công theo giao thức partial batch response.

### 5.1. Cấu hình AWS Lambda event source mapping

Với AWS Lambda + SQS, cần bật response type ReportBatchItemFailures cho event source mapping. Ví dụ CloudFormation:

~~~yaml
FileProcessorMapping:
  Type: AWS::Lambda::EventSourceMapping
  Properties:
    EventSourceArn: !GetAtt InputQueue.Arn
    FunctionName: !Ref FileProcessorFunction
    BatchSize: 10
    FunctionResponseTypes:
      - ReportBatchItemFailures
    Enabled: true
~~~

Nếu không bật tính năng này, response partial failure có thể không được nền tảng sử dụng như mong muốn. Khi triển khai, xác minh cấu hình thực tế của event source mapping, queue visibility timeout, function timeout và retry/DLQ policy.

### 5.2. Java handler trả partial batch response

Ví dụ skeleton với AWS Lambda Java Events:

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import com.amazonaws.services.lambda.runtime.events.SQSEvent;
import com.amazonaws.services.lambda.runtime.events.SQSBatchResponse;

import java.util.ArrayList;
import java.util.List;

public final class FileBatchHandler
        implements RequestHandler<SQSEvent, SQSBatchResponse> {

    private final FileJobService fileJobService =
            ApplicationServices.fileJobService();

    @Override
    public SQSBatchResponse handleRequest(
            SQSEvent event,
            Context context) {

        List<SQSBatchResponse.BatchItemFailure> failures =
                new ArrayList<>();

        for (SQSEvent.SQSMessage message : event.getRecords()) {
            try {
                ObjectReference reference =
                        ObjectReference.fromNotification(message.getBody());

                fileJobService.process(reference);

            } catch (RetryableProcessingException ex) {
                SQSBatchResponse.BatchItemFailure failure =
                        new SQSBatchResponse.BatchItemFailure();
                failure.setItemIdentifier(message.getMessageId());
                failures.add(failure);

                context.getLogger().log(
                        "Retryable file processing failure for message "
                                + message.getMessageId());
            } catch (Exception ex) {
                SQSBatchResponse.BatchItemFailure failure =
                        new SQSBatchResponse.BatchItemFailure();
                failure.setItemIdentifier(message.getMessageId());
                failures.add(failure);

                context.getLogger().log(
                        "Unexpected failure for message "
                                + message.getMessageId());
            }
        }

        return new SQSBatchResponse(failures);
    }
}
~~~

Đây là skeleton minh họa; phần khởi tạo dependency, parser notification và logging cần được nối với ứng dụng thực tế. Handler chỉ trả success khi FileJobService đã hoàn tất hoặc đã lưu quarantine bền vững. Lỗi bất ngờ chưa được phân loại nên được retry và cảnh báo, không được âm thầm bỏ qua.

### 5.3. Queue FIFO

Với SQS FIFO, thứ tự message có ý nghĩa. Khi một message thất bại, dừng xử lý các message tiếp theo trong cùng batch và báo lại message lỗi cùng các message chưa xử lý theo quy tắc partial batch của FIFO. Nếu tiếp tục xử lý message sau lỗi, thứ tự nghiệp vụ có thể bị phá vỡ.

Với standard queue, các message có thể được xử lý độc lập và không có bảo đảm thứ tự toàn cục. Dù queue loại nào, consumer vẫn cần idempotency vì delivery có thể lặp.

## 6. Partial failure bên trong một file

Partial batch response ở SQS chỉ nhận diện message. Nếu một message trỏ đến một CSV gồm 1.000 dòng, SQS không biết dòng 20 và dòng 700 bị lỗi.

Có hai chiến lược:

**Một message cho mỗi file:** function đọc toàn bộ file, xử lý record hợp lệ, ghi record lỗi vào quarantine artifact và chỉ ack message khi tất cả kết quả đã được lưu bền vững.

**Một message cho mỗi record:** producer hoặc bước phân tách file tạo message riêng cho từng record. Queue có thể retry từng record độc lập, nhưng số message tăng và cần cơ chế quản lý file completion.

| Tiêu chí | Một message/file | Một message/record |
|---|---|---|
| Kích thước queue | Thấp hơn | Cao hơn |
| Partial retry | Theo file | Theo record |
| Quản lý tiến độ | Cần manifest/checkpoint trong file | Broker theo dõi từng message |
| Phù hợp | File vừa/nhỏ, batch import | Record độc lập, throughput lớn |
| Rủi ro | Retry file có thể đọc lại nhiều record | Nhiều message và chi phí orchestration |

Với file lớn hoặc thời gian xử lý dài, có thể dùng bước splitter: đọc file, tạo chunk nhỏ, lưu chunk bền vững rồi phát message theo chunk. Khi đó message identity có thể là file identity + chunk number.

### 6.1. Quy tắc xử lý file có record lỗi

Ví dụ file có 1.000 record:

- 970 record hợp lệ.
- 25 record sai dữ liệu.
- 5 record gặp lỗi tạm thời khi ghi database.

Kết quả đúng:

1. Có thể commit 970 record hợp lệ theo idempotency key.
2. Ghi 25 record lỗi dữ liệu vào rejected-records artifact.
3. Không đánh dấu 5 record lỗi hạ tầng là lỗi dữ liệu.
4. Nếu 5 record chưa thể hoàn tất, trả message failure hoặc lưu checkpoint để tiếp tục theo thiết kế.
5. Chỉ chuyển file sang COMPLETED_WITH_ERRORS khi mọi record đã có kết quả cuối cùng và rejected artifact đã được lưu bền vững.

Không đánh dấu file hoàn tất chỉ vì đã ghi được phần lớn record. Cần phân biệt record đang chờ retry với record bị từ chối vĩnh viễn.

Nếu định dạng có thể phát hiện lỗi cấu trúc ở giữa file (ví dụ CSV quote chưa đóng hoặc archive hỏng ở cuối), không ghi business side effect ngay khi vừa đọc được vài dòng. Hãy preflight toàn bộ cấu trúc trước, hoặc stream nội dung đã parse vào vùng staging bền vững rồi mới bắt đầu ghi record. Nếu hợp đồng nghiệp vụ cho phép import một phần ngay cả khi phần cuối file hỏng, phải ghi rõ policy đó và checkpoint chính xác các record đã commit.

## 7. Record-level result trong Java

Tách kết quả của từng record để dễ kiểm thử và thống kê:

~~~java
public record RecordError(
        long rowNumber,
        String errorCode,
        String safeMessage,
        String rawRecord) {
}

public record FileProcessingSummary(
        long totalRecords,
        long succeededRecords,
        long rejectedRecords,
        long retryableFailures) {
}
~~~

Trong hệ thống có dữ liệu nhạy cảm, rawRecord chỉ nên được ghi vào artifact quarantine có quyền truy cập hạn chế. Log chỉ nên chứa row number, error code và correlation ID.

Một enum lỗi giúp phân loại hành động:

~~~java
public enum FailureKind {
    INVALID_RECORD,
    INVALID_FILE,
    TRANSIENT_STORAGE,
    TRANSIENT_DATABASE,
    DOWNSTREAM_UNAVAILABLE,
    UNSUPPORTED_SCHEMA,
    CONFIGURATION
}
~~~

Validator chỉ phát lỗi dữ liệu khi có bằng chứng rằng record không thỏa contract. Timeout từ repository phải được chuyển thành lỗi retryable, không chuyển thành INVALID_RECORD.

## 8. Luồng xử lý file và ghi quarantine

Luồng cho một message/file:

1. Tạo hoặc lấy job manifest bằng object identity.
2. Nếu job đã COMPLETED, COMPLETED_WITH_ERRORS hoặc QUARANTINED, trả kết quả idempotent.
3. Đọc đúng object version và tính checksum.
4. Kiểm tra kích thước, encoding, header và schema.
5. Nếu file không đọc được, ghi bản gốc cùng metadata vào quarantine.
6. Nếu file hợp lệ, đọc từng record.
7. Validate và xử lý record hợp lệ bằng thao tác idempotent.
8. Thu thập lỗi dữ liệu vĩnh viễn ở từng record.
9. Ghi rejected-records artifact nếu có record bị từ chối.
10. Cập nhật manifest và summary sau khi các artifact/kết quả đã bền vững.
11. Trả success cho message khi file đã đạt trạng thái cuối.
12. Nếu có lỗi transient chưa thể tiếp tục, trả message failure để retry.

Điểm quan trọng là **quarantine write phải hoàn tất trước khi ack message**. Nếu function chỉ ghi log lỗi rồi ack, dữ liệu lỗi không còn đường phục hồi.

### 8.1. Phân biệt lỗi toàn file và lỗi từng record

| Tình huống | Xử lý |
|---|---|
| Không mở được object do timeout | Retry message |
| File có encoding không hợp lệ | Quarantine bản gốc |
| Header thiếu cột bắt buộc | Quarantine bản gốc |
| Một dòng có amount sai định dạng | Ghi dòng đó vào rejected artifact, tiếp tục |
| Một dòng tham chiếu ID không tồn tại | Từ chối record theo policy; có thể retry nếu reference có eventual arrival |
| Database timeout khi ghi record hợp lệ | Retry hoặc checkpoint; không quarantine record |
| Ghi rejected artifact thất bại | Retry message; chưa được ack |
| Manifest update thất bại sau khi đã ghi dữ liệu | Retry an toàn bằng idempotency |

Một reference không tồn tại có thể là lỗi dữ liệu hoặc race/eventual consistency tùy nghiệp vụ. Ví dụ customer được tạo sau order event; khi đó cần retry theo thời hạn hoặc kiểm tra reference readiness trước khi quarantine.

## 9. Java FileJobService

Ví dụ interface cho các adapter:

~~~java
public interface ObjectStorage {
    InputStream open(ObjectReference reference);
    void putIfAbsent(String key, byte[] content, Map<String, String> metadata);
}

public interface JobManifestRepository {
    Optional<FileJobManifest> find(String jobKey);
    void markProcessing(String jobKey);
    void markCompleted(
            String jobKey,
            FileProcessingSummary summary,
            String rejectedObjectKey);
    void markQuarantined(
            String jobKey,
            String quarantineObjectKey,
            String reasonCode);
}

public interface RecordRepository {
    void upsertIdempotently(
            String idempotencyKey,
            OrderRecord record);
}
~~~

Repository có thể triển khai markCompleted bằng cách đặt trạng thái COMPLETED khi rejectedRecords bằng 0 và COMPLETED_WITH_ERRORS khi có record bị từ chối. Cả hai chỉ là trạng thái cuối sau khi mọi record đã có kết quả và quarantine artifact đã được ghi thành công.

Một luồng xử lý rút gọn:

~~~java
public final class FileJobService {

    private final ObjectStorage storage;
    private final JobManifestRepository manifests;
    private final RecordRepository records;
    private final OrderFileParser parser;
    private final OrderValidator validator;
    private final QuarantineWriter quarantine;

    public void process(ObjectReference reference) {
        String jobKey = reference.stableIdentity();

        Optional<FileJobManifest> existing = manifests.find(jobKey);
        if (existing.isPresent() && existing.get().isTerminal()) {
            return;
        }

        manifests.markProcessing(jobKey);

        try (InputStream input = storage.open(reference)) {
            ParsedFile file = parser.parseAndValidateHeader(input);

            List<RecordError> rejected = new ArrayList<>();
            long succeeded = 0;

            for (ParsedRecord row : file.records()) {
                OrderRecord order;
                try {
                    order = validator.validate(row);
                } catch (InvalidRecordException ex) {
                    rejected.add(new RecordError(
                            row.rowNumber(),
                            ex.code(),
                            ex.safeMessage(),
                            row.rawValue()));
                    continue;
                }

                String idempotencyKey =
                        jobKey + ":row:" + row.rowNumber();
                records.upsertIdempotently(idempotencyKey, order);
                succeeded++;
            }

            String rejectedKey = null;
            if (!rejected.isEmpty()) {
                rejectedKey = quarantine.writeRejectedRecords(
                        reference,
                        rejected);
            }

            FileProcessingSummary summary =
                    new FileProcessingSummary(
                            file.totalRecords(),
                            succeeded,
                            rejected.size(),
                            0);

            manifests.markCompleted(
                    jobKey,
                    summary,
                    rejectedKey);

        } catch (InvalidFileException ex) {
            String quarantineKey =
                    quarantine.writeOriginalFile(reference, ex.code());

            manifests.markQuarantined(
                    jobKey,
                    quarantineKey,
                    ex.code());

        } catch (TransientProcessingException ex) {
            throw new RetryableProcessingException(ex);
        }
    }
}
~~~

Đây là skeleton minh họa. Cần bổ sung giới hạn bộ nhớ, streaming parser, phân loại exception của storage/database, timeout, metrics và transaction phù hợp. Ví dụ giữ danh sách rejected trong memory chỉ phù hợp file vừa và nhỏ; với file lớn, ghi rejected artifact theo stream hoặc theo chunk.

Trong ví dụ, parser cần hoàn tất preflight cấu trúc file trước khi trả ParsedFile cho vòng ghi business data. Với file lớn, preflight có thể tạo staging object/chunk thay vì giữ toàn bộ nội dung trong RAM. Nếu parser chỉ phát hiện lỗi cấu trúc khi đọc đến cuối, không nên để những record đã ghi trước đó biến một file-level failure thành trạng thái QUARANTINED nhưng vẫn có side effect không được ghi nhận.

### 9.1. Không gom mọi exception vào InvalidRecordException

Một lỗi database hoặc object storage không chứng minh dữ liệu record sai. Cần giữ ranh giới exception:

- Parser/validator ném InvalidRecordException cho lỗi có thể xác định từ payload.
- Parser ném InvalidFileException cho cấu trúc file không thể xử lý.
- Adapter ném TransientProcessingException cho lỗi hạ tầng có khả năng thử lại.
- Lỗi cấu hình/quyền truy cập cần alert và policy xử lý riêng.

Nếu catch Exception rồi thêm tất cả vào rejected list, một outage database có thể biến toàn bộ file hợp lệ thành file lỗi.

## 10. Thiết kế quarantine storage

Quarantine là vùng lưu dữ liệu cần điều tra hoặc sửa. Nó nên tách khỏi vùng input và vùng output bình thường.

Ví dụ cấu trúc object key:

~~~text
quarantine/
  partner-17/
    2026/11/17/
      job-8f2a/
        original-file.csv
        rejected-records.jsonl
        manifest.json
~~~

Có thể lưu:

- Original file nếu file-level failure.
- Các record bị từ chối nếu record-level failure.
- Manifest chứa reason code, số dòng và schema version.
- Processor version, source object version và checksum.
- Correlation ID và thời điểm xử lý.

Không đưa tên file do người dùng cung cấp trực tiếp vào đường dẫn mà không chuẩn hóa. Dùng job ID do hệ thống sinh hoặc hash ổn định để tránh path traversal và va chạm tên.

### 10.1. Ví dụ rejected-records.jsonl

~~~json
{"rowNumber":2,"errorCode":"INVALID_AMOUNT","message":"amount must be a decimal","record":{"order_id":"ORD-1002","customer_id":"CUS-02","amount":"invalid","currency":"VND"}}
{"rowNumber":4,"errorCode":"MISSING_CUSTOMER_ID","message":"customer_id is required","record":{"order_id":"ORD-1004","customer_id":"","amount":"42.00","currency":"VND"}}
~~~

Mỗi dòng JSON độc lập giúp streaming, grep và replay theo record. Cân nhắc lưu raw record nếu cần người vận hành sửa; nếu dữ liệu có PII, phải mã hóa, giới hạn quyền và đặt retention.

### 10.2. Metadata và reason code

Nên dùng reason code ổn định, không dùng toàn bộ exception message làm định danh:

| Reason code | Ý nghĩa |
|---|---|
| FILE_ENCODING_INVALID | Encoding không được hỗ trợ |
| FILE_HEADER_MISMATCH | Header không đúng schema |
| FILE_FORMAT_UNSUPPORTED | Định dạng không được hỗ trợ |
| RECORD_REQUIRED_FIELD_MISSING | Thiếu field bắt buộc |
| RECORD_VALUE_INVALID | Giá trị sai kiểu hoặc ngoài miền |
| RECORD_REFERENCE_NOT_FOUND | Không tìm thấy dữ liệu tham chiếu |
| SCHEMA_VERSION_UNSUPPORTED | Schema version không được hỗ trợ |

Thông điệp chi tiết có thể thay đổi giữa các phiên bản; reason code nên ổn định để dashboard và replay workflow hoạt động lâu dài.

## 11. Quarantine khác DLQ như thế nào?

Quarantine và dead-letter queue đều cô lập lỗi, nhưng phục vụ mục đích khác nhau.

| Tiêu chí | Quarantine | DLQ |
|---|---|---|
| Đối tượng | File hoặc record payload | Message/event delivery |
| Nguyên nhân | Payload không hợp lệ hoặc cần sửa | Message vượt retry policy hoặc không thể xử lý |
| Nội dung | Dữ liệu gốc, rejected records, manifest | Envelope/message gốc và metadata delivery |
| Cách khắc phục | Sửa dữ liệu, chuyển schema hoặc loại bỏ record | Sửa consumer/config/dependency rồi replay |
| Người xử lý | Data operations/business owner | Platform/application operations |
| Replay | Có thể tạo job mới từ artifact đã sửa | Redrive message theo policy |

Một file sai header có thể được lưu vào quarantine và message được ack vì dữ liệu đã được lưu an toàn để xử lý thủ công. Một message gặp database timeout nên được retry; nếu hết retry policy thì chuyển DLQ để điều tra sự cố delivery.

Không dùng DLQ thay cho kho lưu tệp lỗi nghiệp vụ. Queue có retention, giới hạn kích thước message và công cụ duyệt payload khác với object storage.

## 12. Idempotency khi retry file và record

SQS standard queue có at-least-once delivery. Một message có thể xuất hiện nhiều lần, kể cả khi lần xử lý trước đã hoàn thành side effect nhưng function chưa kịp ack.

Tạo job identity từ object identity:

~~~text
jobKey = hash(bucket + key + versionId)
~~~

Nếu không có versionId, có thể kết hợp bucket, key và checksum SHA-256 của nội dung. ETag có thể được lưu như metadata đối chiếu nhưng không nên mặc định là MD5 checksum trong mọi chế độ upload/encryption.

Idempotency key cho record:

~~~text
recordKey = jobKey + rowNumber
~~~

Nếu business operation cần chống trùng giữa các file khác nhau, dùng thêm business key hoặc idempotency key từ producer. Job/row key chỉ ngăn xử lý lặp của cùng một vị trí trong cùng một file.

### 12.1. Ghi database an toàn khi function bị retry

Ví dụ bảng xử lý record có unique key:

~~~sql
CREATE TABLE processed_input_record (
    idempotency_key VARCHAR(300) PRIMARY KEY,
    business_id VARCHAR(150) NOT NULL,
    payload_hash CHAR(64) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL
);
~~~

Trong transaction, ghi idempotency key và business effect sao cho cùng commit hoặc cùng rollback. Nếu key đã tồn tại, kiểm tra payload hash và trả kết quả đã xử lý. Nếu cùng key nhưng payload hash khác, coi đó là conflict cần điều tra thay vì im lặng bỏ qua.

Không ghi marker completed trước khi side effect thực sự commit. Nếu ghi marker trước rồi process chết, retry có thể bỏ qua record chưa được ghi.

### 12.2. Manifest và checkpoint

Với file lớn, lưu checkpoint theo chunk hoặc row range:

- File identity.
- Chunk number/range.
- Trạng thái chunk.
- Số record thành công/từ chối.
- Quarantine artifact key.
- Checksum của chunk.
- Processor version.

Checkpoint chỉ được cập nhật sau khi side effect của chunk đã commit và reject artifact của chunk đã được ghi bền vững. Khi retry, đọc checkpoint và chỉ tiếp tục phần chưa hoàn tất; vẫn giữ idempotency vì checkpoint update cũng có thể bị lặp hoặc lỗi.

## 13. Thứ tự ghi kết quả và ack message

Một nguyên tắc quan trọng:

**Không ack message trước khi mọi kết quả cần giữ đã được ghi bền vững.**

Với file có record lỗi:

1. Ghi các record hợp lệ vào database bằng idempotent write.
2. Ghi rejected-records artifact.
3. Ghi manifest COMPLETED_WITH_ERRORS và summary.
4. Trả success cho SQS message.

Nếu bước 2 hoặc 3 thất bại, trả message failure. Khi message được giao lại, bước 1 chạy lại nhưng idempotency ngăn side effect trùng.

Nếu object/file không hợp lệ:

1. Copy bản gốc sang quarantine.
2. Xác minh object quarantine tồn tại và metadata/checksum phù hợp.
3. Ghi manifest QUARANTINED.
4. Ack message.

Nếu quarantine storage không khả dụng, chưa được ack. Dữ liệu gốc phải còn trong input storage hoặc queue reference để retry.

Không thể tạo transaction ACID duy nhất bao trùm database, object storage và queue ack. Thiết kế cần dùng durable state, idempotency và thứ tự thao tác để phục hồi từ mọi điểm process có thể bị dừng.

## 14. "Move" file trong object storage

Trong filesystem thông thường, rename trong cùng filesystem có thể là thao tác nguyên tử tùy hệ điều hành/filesystem. Với object storage như S3, thao tác move thường là **copy object sang key mới rồi xóa object nguồn**; không nên giả định có atomic rename.

Quy trình an toàn:

1. Đọc đúng source object version.
2. Copy sang quarantine key bất biến.
3. Kiểm tra copy thành công và metadata/checksum.
4. Ghi manifest trỏ đến quarantine object.
5. Chỉ xóa source object nếu retention/policy cho phép và mọi bước trước đã hoàn tất.

Nếu copy thành công nhưng manifest update thất bại, retry có thể copy lại. Dùng quarantine key deterministic và conditional put/copy hoặc kiểm tra object đích để thao tác lặp an toàn.

Trong nhiều hệ thống, giữ source file trong incoming/archive theo retention và xem quarantine là bản sao được phân loại. Chỉ xóa source khi chính sách lưu trữ cho phép.

### 14.1. Tránh trigger vòng lặp

Nếu object-created event được cấu hình cho toàn bộ bucket, việc ghi file vào quarantine có thể kích hoạt chính function xử lý file, tạo vòng lặp vô hạn.

Biện pháp:

- Dùng bucket riêng cho quarantine.
- Hoặc giới hạn notification chỉ với prefix incoming/.
- Không cấu hình trigger cho prefix quarantine/.
- Dùng prefix archive/ riêng.
- Kiểm tra event source và object key trước khi xử lý.
- Có guard trong code, nhưng không dựa vào guard code thay cho cấu hình notification đúng.

Đây là lỗi triển khai phổ biến: function ghi tệp lỗi sang cùng bucket, rồi chính tệp lỗi lại trở thành input mới.

## 15. Batch size, timeout và backpressure

Batch size ảnh hưởng tới throughput, memory và phạm vi retry.

| Batch size | Lợi ích | Rủi ro |
|---|---|---|
| Nhỏ | Cô lập lỗi tốt, thời gian mỗi invocation ngắn | Nhiều invocation và overhead |
| Lớn | Giảm overhead, tăng khả năng gom xử lý | Dễ timeout, tốn memory và có nhiều message phải retry |
| Theo byte/chunk | Kiểm soát tài nguyên tốt hơn | Cần splitter và manifest phức tạp hơn |

Cần đo:

- Thời gian đọc object.
- Kích thước file và số record.
- Parse/validation duration.
- Database write throughput.
- Quarantine write duration.
- Memory peak.
- SQS batch age và queue depth.
- Function timeout/throttling.

Không đặt batch size chỉ dựa vào số message. Mười message trỏ tới mười file 1 MB khác hoàn toàn mười file 500 MB.

### 15.1. Visibility timeout

Với SQS, visibility timeout phải đủ dài để function xử lý batch và hoàn thành side effect. Nếu visibility timeout quá ngắn, message có thể được giao cho invocation khác trong khi invocation trước vẫn đang chạy.

Cần phối hợp:

- Lambda timeout.
- SQS visibility timeout.
- Batch size.
- Maximum concurrency.
- Retry/backoff policy.
- Thời gian downstream có thể chậm.

Nếu file quá lớn để xử lý trong giới hạn function, dùng chunking hoặc workflow orchestration thay vì tăng timeout đến mức không thể vận hành.

### 15.2. Giới hạn concurrency để bảo vệ downstream

Serverless có thể tăng số invocation nhanh hơn khả năng database tiếp nhận write. Giới hạn concurrency, batch size, connection pool và rate limit để tránh biến một đợt import thành outage của hệ thống đích.

Khi queue backlog tăng nhưng database đã bão hòa, giảm concurrency hoặc pause consumer có thể an toàn hơn việc tăng thêm function.

## 16. Bảo mật và retention của quarantine

Quarantine thường chứa dữ liệu chưa được xác thực đầy đủ. Nó có thể chứa PII, dữ liệu sai cấu trúc hoặc nội dung độc hại.

Cần:

- Mã hóa object khi lưu và khi truyền.
- IAM riêng cho writer, reviewer và replay worker.
- Không cấp quyền đọc quarantine rộng như bucket public.
- Quét malware nếu file có thể chứa nội dung thực thi hoặc archive.
- Giới hạn file size, decompression ratio và loại định dạng.
- Không log raw payload hoặc secret.
- Lưu reason code và metadata tối thiểu cần thiết.
- Đặt retention/lifecycle theo chính sách dữ liệu.
- Audit mọi thao tác đọc, sửa, tải xuống và replay.
- Kiểm tra tenant isolation khi nhiều đối tác dùng chung pipeline.

Tên object nên tránh chứa email, số điện thoại hoặc dữ liệu định danh. Dùng opaque job ID và lưu thông tin đối chiếu trong manifest có kiểm soát quyền.

### 16.1. Replay có kiểm soát

Không nên cho phép mọi người tải file quarantine rồi đẩy trực tiếp trở lại incoming. Quy trình replay nên:

1. Xác định owner và lý do lỗi.
2. Sửa payload hoặc triển khai parser/schema mới.
3. Kiểm tra checksum và nội dung đã sửa.
4. Tạo replay job ID mới liên kết với original job.
5. Giữ nguồn gốc và lịch sử lần xử lý trước.
6. Chạy lại qua cùng validation và idempotency mechanism.
7. Đối chiếu số record thành công, bị từ chối và còn chờ.
8. Đóng incident khi kết quả đã được xác minh.

Nếu replay đúng file cũ, job identity có thể giữ nguyên để tiếp tục cùng workflow hoặc tạo generation mới có chủ đích. Quyết định này phải nhất quán với idempotency key; không tự thay key để né conflict và vô tình ghi trùng business data.

Một cách quản lý rõ ràng là giữ job identity gốc bất biến và tạo replayJobId/generation riêng để theo dõi lần sửa. Record không đổi tiếp tục dùng idempotency key gốc; record đã được sửa phải có correction identity/payload hash mới và áp dụng quy tắc cập nhật theo business key. Không ghi đè lịch sử rejected artifact cũ.

## 17. Observability và báo cáo batch

Một dashboard hữu ích cần cho biết batch đang ở đâu và vì sao có lỗi.

| Metric | Ý nghĩa |
|---|---|
| Messages received | Số message nhận từ queue |
| Messages retried | Số message được trả lại để retry |
| Files completed | Số file hoàn tất |
| Files quarantined | Số file-level failure được lưu |
| Records processed | Số record đã xử lý |
| Records rejected | Số record lỗi dữ liệu |
| Quarantine write failures | Số lần không lưu được artifact lỗi |
| Oldest message age | Tuổi message cũ nhất trong queue |
| Processing duration | Thời gian xử lý file/batch |
| Duplicate jobs | Số job đã được nhận diện là trùng |
| DLQ depth | Message vượt retry policy |
| Replay success rate | Tỷ lệ replay hoàn tất |

Log nên có:

- jobId và correlationId.
- Object key đã được chuẩn hóa hoặc hash.
- Object version/checksum.
- SQS messageId.
- Row number.
- Reason code.
- Processor/schema version.
- Attempt number.
- Quarantine object key.

Tránh dùng jobId, object key hoặc tenant ID làm metric label nếu cardinality cao. Dùng log/trace để truy vết chi tiết.

### 17.1. Báo cáo kết quả cho một file

Một manifest summary có thể như sau:

~~~json
{
  "jobId": "job-8f2a",
  "source": {
    "bucket": "partner-ingestion",
    "key": "incoming/partner-17/orders.csv",
    "versionId": "3Lg...example",
    "sha256": "a4f2...example"
  },
  "status": "COMPLETED_WITH_ERRORS",
  "totalRecords": 1000,
  "succeededRecords": 975,
  "rejectedRecords": 25,
  "retryableFailures": 0,
  "rejectedObjectKey": "quarantine/partner-17/2026/11/17/job-8f2a/rejected-records.jsonl"
}
~~~

Trong ví dụ này, 970 record hợp lệ ngay lần đầu và 5 record từng gặp lỗi tạm thời đã được retry thành công, nên tổng succeededRecords là 975. Cùng với 25 record bị từ chối, các nhóm kết quả cộng đúng 1.000 record. Trong manifest thực tế, nếu có header, trailer, dòng trống hoặc record bị bỏ qua theo policy, cần có count riêng để đối soát.

## 18. Kiểm thử partial failure và quarantine

Test cần bao gồm cả message-level và record-level.

| Tình huống | Kết quả mong đợi |
|---|---|
| Mọi message và record hợp lệ | Không có batchItemFailures |
| Một SQS message gặp timeout storage | Chỉ message đó được trả về để retry |
| Một file có record sai định dạng | Record lỗi được lưu quarantine; record tốt vẫn được xử lý |
| File sai header | Bản gốc được quarantine và message được ack sau khi lưu thành công |
| Quarantine storage timeout | Message failure để retry |
| Database timeout sau một số record | Retry/chunk resume; record đã commit không bị ghi trùng |
| Function chết sau khi ghi index/database nhưng trước ack | Redelivery không tạo side effect trùng |
| Duplicate object event | Job manifest/idempotency ngăn xử lý lặp |
| File cùng key nhưng version khác | Xử lý đúng object version |
| Quarantine copy thành công, manifest update thất bại | Retry an toàn, không tạo nhiều bản không kiểm soát |
| Quarantine object tạo event mới | Trigger không xử lý lại prefix quarantine |
| FIFO message giữa batch thất bại | Giữ đúng thứ tự, không xử lý tiếp ngoài policy |
| DLQ replay | Dữ liệu đã sửa được xử lý, lịch sử vẫn truy xuất được |
| Payload có PII | Log không lộ raw data, quarantine có kiểm soát quyền |

### 18.1. Kiểm thử failure injection

Mô phỏng process bị dừng tại các điểm:

- Sau khi đọc file nhưng trước khi ghi record.
- Sau khi ghi một số record nhưng trước khi checkpoint.
- Sau khi ghi rejected artifact nhưng trước khi cập nhật manifest.
- Sau khi cập nhật manifest nhưng trước khi function trả response.
- Sau khi quarantine copy nhưng trước khi xóa source.
- Sau khi downstream commit nhưng trước khi ack message.

Với mỗi điểm, chạy lại cùng event và xác minh dữ liệu không mất, không bị nhân đôi và manifest cuối cùng phản ánh đúng trạng thái.

## 19. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Throw exception cho mọi lỗi trong batch | Message tốt bị retry cùng message lỗi | Partial batch response |
| Ack message dù quarantine chưa ghi xong | Mất dữ liệu lỗi | Chỉ ack sau durable write |
| Quarantine cả file khi một record sai | Loại bỏ dữ liệu hợp lệ | Tách record-level rejection |
| Retry record lỗi dữ liệu vô hạn | Queue backlog và chi phí tăng | Permanent failure vào quarantine |
| Quarantine lỗi timeout database | Dữ liệu hợp lệ bị phân loại sai | Tách transient khỏi permanent |
| Chỉ dùng in-memory dedup | Duplicate sau cold start/restart | Durable manifest và idempotency |
| Dùng object key làm job ID duy nhất | Ghi đè hoặc bỏ sót version mới | Key + version/checksum |
| Move object bằng giả định atomic rename | Có thể mất source hoặc tạo trạng thái nửa chừng | Copy, verify, manifest, rồi mới delete |
| Trigger toàn bộ bucket | Quarantine tự kích hoạt pipeline | Prefix/bucket filter |
| Log raw record | Rò rỉ PII/secret | Log reason code và metadata an toàn |
| Batch quá lớn | Timeout và memory exhaustion | Chunking, streaming, concurrency control |
| Replay không có lịch sử | Không biết nguồn và lần sửa | Replay job ID và lineage |

## 20. Quy trình triển khai dự án

1. **Xác định contract đầu vào.** Định nghĩa file format, encoding, header, schema version, giới hạn size và record.
2. **Chọn event transport.** Object storage phát event qua queue để buffer và retry.
3. **Tạo job identity.** Kết hợp object key với version/checksum.
4. **Thiết kế manifest.** Lưu trạng thái, số record, checkpoint và artifact reference.
5. **Phân loại lỗi.** Tách transient, invalid record, invalid file và configuration failure.
6. **Xây parser/validator Java.** Streaming file, validate record độc lập và tạo reason code ổn định.
7. **Xây idempotent writer.** Mỗi record có idempotency key; business write và marker phải nhất quán.
8. **Xây quarantine writer.** Lưu original file hoặc rejected records với key deterministic và metadata.
9. **Triển khai partial batch response.** Chỉ trả message cần retry; bật cấu hình tương ứng trên event source mapping.
10. **Thiết lập DLQ và retry policy.** Giới hạn retry, backoff và cảnh báo.
11. **Cấu hình storage notification.** Chỉ trigger incoming prefix; loại trừ quarantine/archive.
12. **Kiểm thử crash/replay.** Xác minh side effect, checkpoint, quarantine và ack ở mọi failure point.
13. **Thiết lập observability.** Theo dõi queue age, file status, rejected count và quarantine write failure.
14. **Triển khai replay workflow.** Có owner, approval, lineage và idempotency policy.
15. **Vận hành theo retention.** Lưu file/quarantine theo policy, kiểm soát truy cập và xóa đúng hạn.

## 21. Câu hỏi tự kiểm tra

- Partial batch response ở SQS nhận diện lỗi bằng messageId hay row number?
- Vì sao message-level partial failure không tự giải quyết record-level failure trong file?
- Khi nào nên retry message và khi nào nên quarantine record?
- Điều gì xảy ra nếu ack message trước khi rejected artifact được ghi bền vững?
- Vì sao database timeout không nên bị phân loại là invalid record?
- File sai header nên được xử lý khác một dòng CSV sai amount như thế nào?
- Quarantine khác DLQ ở mục đích và loại dữ liệu ra sao?
- Vì sao job identity cần object version hoặc checksum?
- Làm thế nào để tránh xử lý trùng sau khi function chết trước ack?
- Vì sao object storage move thường phải thực hiện copy rồi delete?
- Cách tránh quarantine object kích hoạt lại chính function xử lý là gì?
- Khi nào nên dùng một message/file và khi nào nên tách message/record?
- Vì sao file lớn cần chunking và checkpoint?
- Quarantine cần kiểm soát quyền, mã hóa và retention như thế nào?
- Cần kiểm thử những điểm crash nào trước khi triển khai production?


