# NullChannel để loại bỏ lỗi có chủ đích trong Spring Integration Adapters

> **Chương:** Error handling  
> **Chủ đề trực tiếp:** NullChannel để loại bỏ lỗi có chủ đích  
> **Phạm vi module:** Kết nối các hệ thống ngoài vào **Spring Integration** thông qua inbound/outbound adapter, gateway, poller và MessageChannel. Nội dung liên hệ luồng File, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu; chú trọng hợp đồng message, lỗi, xác nhận xử lý, tính bền vững và vòng đời kết nối.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích bản chất **NullChannel** là MessageChannel dạng **black hole** nhận message và chủ động bỏ nội dung, khác với kho lưu lỗi và bộ retry.
2. Phân biệt **discard message**, **ignore expected condition**, **swallow exception**, **acknowledge message**, **dead-letter** và **recover business operation**.
3. Xác định khi nào có thể gửi **ErrorMessage** tới nullChannel sau **phân loại lỗi có chủ đích**, thay vì nuốt mọi lỗi.
4. Cấu hình tuyến tới kênh **nullChannel** từ một IntegrationFlow, **Filter.discardChannel** hoặc một error-handling flow có kiểm soát.
5. Hiểu khác biệt đường lỗi **đồng bộ** và **bất đồng bộ** qua DirectChannel, ExecutorChannel, QueueChannel, poller và các container.
6. Đánh giá tương tác với **errorChannel header, global errorChannel, ErrorMessage, errorChannel resolver, gateway, RequestHandlerRetryAdvice** và recovery.
7. Thiết kế chính sách an toàn cho File/SFTP, HTTP, JMS, AMQP, Kafka và JDBC: **lỗi nào được bỏ, lỗi nào phải DLQ/retry/rollback**.
8. Bảo đảm **observability, audit, idempotency, mã lý do, owner, đo lường và kiểm thử âm tính** trước khi bỏ message.
9. Viết ma trận quyết định và test chứng minh **loại bỏ đúng có chủ đích**, không tạo ra **silent data loss** hoặc chuyển lỗi nghiêm trọng thành “thành công giả”.

## 2. Bài toán: không phải lỗi nào cũng cần cảnh báo, nhưng không phải lỗi nào cũng được bỏ

Một hệ thống nhận file từ SFTP, xử lý hóa đơn và gửi kết quả sang HTTP ERP có thể gặp:

- **Bản ghi trùng hợp lệ**: cùng business event đã được xử lý thành công, việc nhận lại không cần phát sinh side effect.
- **File phụ không liên quan**: đối tác đặt file README hoặc marker trong cùng thư mục nhưng hợp đồng chỉ xử lý *.ready.
- **Một nhánh không cần reply**: handler phát trạng thái thông tin nhưng caller không cần nhận response.
- **HTTP 503**: ERP tạm ngừng; phải thử lại hoặc lưu job.
- **Payload sai schema**: cần quarantine và thông báo để sửa dữ liệu.
- **JMS consumer lỗi DB**: cần rollback/redelivery hoặc lưu lỗi bền.
- **Kafka record không thể xử lý**: cần DLT/parking hoặc chính sách rõ, không tự bỏ và commit offset.
- **SFTP upload thành công nhưng mất response**: không biết outcome; cần đối soát, không tự “ignore”.

Một số message **nên được loại bỏ vì đã đáp ứng hợp đồng nghiệp vụ**. Nhưng gửi toàn bộ lỗi vào một black-hole channel để dashboard “xanh” có thể làm dữ liệu biến mất không thể khôi phục.

### Câu hỏi quan trọng nhất

> “Điều kiện nào đã được kiểm chứng để chứng minh **không cần thực hiện thêm hành động nghiệp vụ**, và nếu bỏ message ngay bây giờ thì có mất khả năng đối soát hay phục hồi không?”

**NullChannel có thể là điểm cuối hợp lệ của một nhánh đã được phân loại**, không phải lời giải cho mọi lỗi.

## 3. NullChannel là gì?

Trong Spring Integration, **NullChannel** là một triển khai MessageChannel nhận message rồi **loại bỏ message** thay vì chuyển tới một subscriber để xử lý nghiệp vụ. Nó thường được gọi là **black-hole channel**.

Spring Integration cung cấp một channel chuẩn có tên **nullChannel** để sử dụng trong các endpoint/flow theo cấu hình phù hợp. Tên này thể hiện **đích hủy message**, không phải **null** của Java và cũng không phải channel nhận message rồi trả về một giá trị null như một response nghiệp vụ.

### Ba khẳng định cần nhớ

1. **Message được gửi tới NullChannel là điểm kết thúc của nhánh xử lý ấy.** Không có consumer downstream nào nhận message để thực thi tác vụ kinh doanh.
2. **NullChannel không phải một DLQ, message store, retry scheduler hay cơ chế chuyển tiếp lỗi.** Không thể giả định có khả năng replay thông điệp đã bỏ.
3. **Một lệnh send thành công tới NullChannel không chứng minh nghiệp vụ thành công.** Nó chỉ chứng minh message đã được chấp nhận để hủy theo ngữ nghĩa channel.

### So sánh với các thành phần dễ nhầm

| Thành phần | Hành vi | Có lưu bền? | Khi dùng |
|---|---|---|---|
| **NullChannel** | Nhận và bỏ message | Không | Nhánh đã được chứng minh có thể bỏ |
| **DirectChannel** | Dispatch tới handler đồng bộ | Không mặc định | Xử lý trực tiếp/cần propagate lỗi |
| **ExecutorChannel** | Dispatch qua executor | Không mặc định | Ranh giới xử lý bất đồng bộ |
| **QueueChannel** | Xếp message chờ nhận | Phụ thuộc MessageStore | Tách producer/consumer |
| **PublishSubscribeChannel** | Phát tới nhiều subscriber | Không mặc định | Fan-out, có thể làm error channel |
| **errorChannel** | Tuyến xử lý ErrorMessage theo cấu hình | Không mặc định | Quan sát/điều phối lỗi |
| **DLQ/DLT/parking** | Giữ message lỗi cùng nguyên nhân | Có khi kho đích được thiết kế bền | Điều tra, manual fix, redrive |
| **Filter discard** | Loại message không đạt predicate; có thể gửi tới discardChannel | Tùy đích | Loại noise/record không thuộc phạm vi |

**Một channel được đặt tên errorChannel không tự là nơi lưu lỗi bền vững**. Ngược lại, NullChannel không có ý định giữ lại bất cứ message nào.

### NullChannel có log lỗi không?

Khi message thuộc loại **ErrorMessage**, hành vi ghi log chi tiết của NullChannel có thể phụ thuộc phiên bản và cấu hình logging của Spring Integration. Không nên khẳng định “mọi ErrorMessage sẽ biến mất không dấu vết”, nhưng cũng **không được dùng log mặc định như một audit trail bền vững**. Nếu cần đếm, lưu lý do và kiểm toán, phải làm việc đó **trước khi đưa vào nullChannel**, qua một cơ chế quan sát được kiểm thử.

## 4. NullChannel không “sửa lỗi”

Cần phân biệt ba hành động:

1. **Discard:** không thực hiện xử lý downstream cho message đó.
2. **Recover:** thực thi phương án bù, fallback hợp lệ hoặc ghi message vào nơi có thể xử lý tiếp.
3. **Retry:** thực hiện lại operation khi lỗi có cơ hội phục hồi.

NullChannel chỉ trực tiếp thực hiện **discard**. Nếu hệ thống gửi một **ErrorMessage** tới nullChannel, luồng error message đó kết thúc. Điều này **không làm transaction trước đó được rollback**, **không xóa side effect đã tạo** và **không tự quyết định broker ack**.

### Một sai lầm thường gặp

~~~text
SFTP inbound -> HTTP POST tạo order
                      |
                      +-- response timeout
                             |
                             v
                         errorChannel
                             |
                             v
                         nullChannel

Quan sát:
    Không có alert nữa.

Thực tế có thể:
    HTTP POST chưa thành công -> mất order.
    Hoặc POST đã thành công -> outcome unknown.
    Hoặc nguồn đã ack -> không còn message để replay.
~~~

Cấu hình trên chỉ hợp lệ khi có một **hợp đồng trước đó** xác định timeout này thực sự có thể bỏ và đã có bằng chứng bảo toàn hoặc xử lý nghiệp vụ. Thông thường timeout tạo order **không đạt điều kiện**.

## 5. Bốn trạng thái phải tách rõ khi quyết định bỏ lỗi

| Trạng thái | Ý nghĩa | Có thể gửi NullChannel? |
|---|---|---|
| **EXPECTED_IGNORE** | Một message không cần xử lý theo hợp đồng, ví dụ loại file không thuộc tập nhận | Có nếu phân loại đã kiểm chứng, có audit nếu cần |
| **ALREADY_PROCESSED** | Business event trùng đã được xác minh xử lý đầy đủ | Có sau dedupe/đối soát hợp lệ |
| **RECOVERED_BY_POLICY** | Đã có fallback/compensation hoặc lưu bền đúng hợp đồng | Có thể bỏ **thông báo lỗi phụ** khi hậu quả đã được xử lý |
| **UNRESOLVED/UNKNOWN** | Chưa rõ outcome hoặc còn tác vụ chưa hoàn tất | **Không** bỏ; cần retry, rollback, parking hoặc điều tra |

Một lỗi đã được ghi log **không nhất thiết** là RECOVERED_BY_POLICY. Một error flow nhận được message **không có nghĩa** tác vụ gốc được bảo toàn.

### Định nghĩa trước một bản “discard decision”

Một quyết định bỏ có thể chứa:

- Business event ID hoặc correlation ID ổn định.
- Nguồn/adapter/endpoint.
- Error category hoặc loại message.
- **Reason code** đã được phê duyệt.
- Bằng chứng đã xử lý/không cần xử lý.
- Thời điểm phân loại.
- Rule/policy version.
- Owner và thời hạn lưu audit.
- Nhánh kết thúc là DISCARDED_EXPECTED.

Không đưa token, mật khẩu, private key hoặc toàn bộ payload khách hàng vào bản ghi audit chỉ để chứng minh đã bỏ đúng.

## 6. Kiến trúc xử lý lỗi: phân loại trước, NullChannel sau

~~~mermaid
flowchart TD
    S["Inbound adapter / gateway / poller"] --> H["Message handler / Integration Flow"]
    H -->|"Thành công"| OK["Business outcome"]
    H -->|"Exception"| E["ErrorMessage / error boundary"]
    E --> C["Classification + correlation + business-state check"]
    C --> Q{"Trạng thái đã xác minh?"}
    Q -->|"EXPECTED_IGNORE"| M["Metric + audit reason"]
    Q -->|"ALREADY_PROCESSED"| M
    Q -->|"RECOVERED_BY_POLICY"| M
    M --> N["nullChannel: bỏ thông báo đã kết thúc"]
    Q -->|"TRANSIENT_RETRYABLE"| R["Retry bounded / delayed retry"]
    Q -->|"PERMANENT_INVALID"| D["Quarantine / DLQ"]
    Q -->|"OUTCOME_UNKNOWN"| P["Reconcile / PARKED"]
    Q -->|"SECURITY / UNCLASSIFIED"| X["Alert + owner investigation"]
    R --> B["Durable state / source protocol"]
    D --> B
    P --> B
    X --> B
~~~

**Không nối trực tiếp toàn bộ errorChannel tới nullChannel** nếu chưa có bước classifier và quyết định an toàn. Mọi nhánh kết thúc đều cần tiêu chí rõ cho việc source ack/commit hoặc hoàn tất request.

### Các tuyến message

- **Business messages:** payload chính, side effect nghiệp vụ.
- **ErrorMessages:** payload biểu diễn exception và metadata lỗi.
- **Audit events:** bằng chứng phân loại và kết quả, không nhất thiết chứa đầy đủ dữ liệu nguồn.
- **Recovery records:** payload hoặc tham chiếu đủ để retry, điều tra và replay.

Không nên lấy ErrorMessage làm kho lưu message gốc vĩnh viễn; nó có thể chứa exception nhạy cảm và không được thiết kế như store bền mặc định.

## 7. Lỗi đồng bộ và bất đồng bộ khác nhau

Spring Integration có đường xử lý **synchronous** và **asynchronous**. Điều này quyết định exception có đi tới caller trực tiếp hay được chuyển thành ErrorMessage trên một channel.

### DirectChannel

**DirectChannel** thường dispatch handler đồng bộ trong thread của sender. Nếu handler ném exception và không có cơ chế catch/error handling ở tầng thích hợp, exception có thể **nổi về caller**.

Việc chỉ định một channel tên nullChannel đâu đó trong context **không tự bắt mọi exception đồng bộ**. Phải có một điểm catch/transform exception thành ErrorMessage hoặc error flow được cấu hình thật.

### ExecutorChannel

**ExecutorChannel** tạo ranh giới xử lý bất đồng bộ bằng executor. Error propagation có thể đi qua **error channel** theo ngữ cảnh của framework thay vì trở về caller ban đầu.

Nếu ErrorMessage được định tuyến tới NullChannel, không được suy rằng request gốc có durable retry hoặc đã ack đúng: cần xem nguồn, transaction và error handler.

### QueueChannel/poller

Một poller lấy message qua QueueChannel hoặc MessageSource rồi thực thi handler. Nếu message đã được remove/claim từ nguồn, việc bỏ error không mặc nhiên trả message về queue. Cần xác minh transaction/rollback, MessageStore và poller error handling.

### Gateway request–reply

Gateway có thể đợi **reply** hoặc **error reply**. Nếu đẩy cả kết quả và lỗi vào nullChannel, caller có thể đợi tới **reply timeout** rồi thất bại theo một hình thức khác. Không dùng NullChannel làm cách giải quyết yêu cầu trả response hợp lệ.

| Ranh giới | Khi có lỗi | Câu hỏi về NullChannel |
|---|---|---|
| Đồng bộ DirectChannel | Có thể propagate exception | Có flow nào thật sự catch rồi gửi ErrorMessage không? |
| Bất đồng bộ ExecutorChannel | ErrorMessage có thể được gửi theo error path | Đã ack/persist nguồn chưa? |
| PollingConsumer | Polling/error flow theo cấu hình | Có thể poll lại cùng message không? |
| Gateway request–reply | Caller cần reply/error | Nếu bỏ reply, caller có timeout không? |
| Broker listener | Container quyết định ack/nack/rollback | Error flow trả bình thường có dẫn tới ack không? |

## 8. errorChannel và nullChannel: hai kênh có ý nghĩa đối lập

**errorChannel** là tuyến mang ErrorMessage; **nullChannel** là đích hủy message. Cả hai là tên quen thuộc trong Spring Integration, nhưng chỉ một trong hai có ý định giúp bạn tiếp tục xử lý lỗi.

Một số cấu hình Spring Integration có **global errorChannel** để các thành phần xử lý bất đồng bộ đưa ErrorMessage vào khi không có destination cụ thể. Có thể có logging handler theo cấu hình mặc định. Tuy nhiên:

- Không phải exception nào cũng tự đi vào global errorChannel.
- Error channel có thể được xác định qua header hoặc cấu hình endpoint.
- Một error channel có subscriber và loại channel cụ thể, không nhất thiết lưu bền.
- Global errorChannel không tự là DLQ.
- Thay đổi nó thành nullChannel có thể làm **mất đường quan sát lỗi toàn hệ thống**.
- Cần xác nhận precedence/resolve error channel theo topology và version sử dụng.

### Header errorChannel

Một message có thể mang header chỉ định kênh xử lý lỗi khi thành phần/framework có hỗ trợ tuyến lỗi đó. Header có thể tham chiếu channel theo dạng được hỗ trợ trong ngữ cảnh.

**Không nên diễn giải:** đặt errorChannel header = nullChannel thì mọi exception Java trong flow đều tự bị bỏ. Điều đó phụ thuộc thành phần phát ErrorMessage, luồng đồng bộ/bất đồng bộ và việc error channel có thực sự được dùng.

### Trường hợp có thể bỏ reply

Trong một số luồng **one-way**, kết quả trả về không cần được xử lý. Có thể dùng nullChannel làm điểm cuối của **reply message** không cần thiết. Đó là **bỏ reply**, khác với **bỏ ErrorMessage**. Không dùng điều này cho gateway mà caller cần dữ liệu trả về.

## 9. Filter discardChannel khác việc bỏ lỗi

**Filter** trong Spring Integration quyết định một message có tiếp tục đi downstream không. Message không đạt predicate có thể bị bỏ hoặc được chuyển tới **discardChannel**.

Ví dụ file chỉ được nhận khi tên hợp đồng kết thúc bằng .ready, các file phụ được đưa tới NullChannel:

~~~java
import java.io.File;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
class FileSelectionFlow {

    @Bean
    IntegrationFlow candidateFileFlow() {
        return IntegrationFlow.from("candidateFileChannel")
            .filter(File.class,
                file -> file.getName().endsWith(".ready"),
                endpoint -> endpoint.discardChannel("nullChannel"))
            .channel("acceptedFileChannel")
            .get();
    }
}
~~~

Điều kiện trong ví dụ phải đúng **hợp đồng nguồn**. Một file hợp lệ nhưng đang dùng đuôi khác không được âm thầm mất chỉ vì predicate viết sai. Cần unit test **tập file được chấp nhận và bị loại**, cùng metrics cho discarded count.

### Đây có phải xử lý exception?

**Không.** Filter loại một message **theo dữ liệu/hợp đồng**, không nhất thiết vì một exception được ném. Nếu lập trình viên bắt exception từ parser và sửa thành predicate false để đưa mọi file lỗi vào nullChannel, lỗi dữ liệu có thể bị che giấu. Phải có nhánh INVALID/quarantine riêng.

### Lỗi khi filter tự ném exception

Nếu predicate ném RuntimeException, đó là lỗi execution cần đi đường error handling tương ứng; **discardChannel không tự xử lý mọi exception của predicate**. Nó dành cho message bị **loại theo kết quả filter**.

## 10. Định tuyến message có kiểm soát tới nullChannel

Một use case khác là phân loại những thông điệp không cần xử lý theo rule hợp lệ trước khi gửi sang channel.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
class ClassifiedMessageFlow {

    @Bean
    IntegrationFlow classifiedFlow() {
        return IntegrationFlow.from("classifiedInput")
            .route(
                String.class,
                payload -> payload.startsWith("INFO:") ?
                        "IGNORE" : "PROCESS",
                router -> router
                    .channelMapping("IGNORE", "ignoredAuditChannel")
                    .channelMapping("PROCESS", "businessChannel")
            )
            .get();
    }

    @Bean
    IntegrationFlow ignoredFlow() {
        return IntegrationFlow.from("ignoredAuditChannel")
            .handle((payload, headers) -> {
                // Ghi counter và audit có reason code trước khi discard.
                // Đây là nơi minh họa; instrumentation cần được cấu hình thật.
                return payload;
            })
            .channel("nullChannel")
            .get();
    }
}
~~~

Ở đây, handler audit **trả lại payload** để message tiếp tục tới NullChannel. Nếu handler audit ném lỗi thì không nên tự biến lỗi audit thành discard thành công khi audit là điều kiện bắt buộc. Chính sách phải xác định audit sync/bền và tác động khi không thể ghi.

**Ví dụ xử lý payload String đơn giản để minh họa routing**, không phải giải pháp đủ cho việc phân loại ErrorMessage. Với lỗi, cần xét exception type, nguồn, operation, business state và metadata thay vì dựa vào prefix của chuỗi.

## 11. Phân loại ErrorMessage: nên bỏ dạng lỗi nào?

Một ErrorMessage đại diện lỗi phát sinh trong quá trình xử lý message. Payload mang Throwable; metadata có thể cung cấp failed message và correlation theo cách framework tạo lỗi.

**Không nên viết classifier chỉ dựa trên exception class.** Ví dụ cùng một IOException có thể là tạm đứt kết nối cần retry, hoặc thao tác đã hoàn tất nhưng response mất cần đối soát.

### Ma trận quyết định

| Phân loại | Dữ kiện cần kiểm | Hành động phù hợp |
|---|---|---|
| Duplicate đã xử lý | Stable event ID đã có kết quả đầy đủ, checksum/version khớp | Audit + NullChannel cho message trùng |
| Thông báo phụ không cần xử lý | Hợp đồng cho phép bỏ, không có side effect bắt buộc | Audit + NullChannel |
| Business no-op hợp lệ | Rule chỉ rõ thao tác không còn cần, ví dụ event cũ hơn version đã commit | Audit + NullChannel nếu nhất quán |
| HTTP 503 | Retryable, còn deadline/budget | Retry ngắn hoặc durable retry |
| HTTP POST timeout | Outcome unknown | Query remote/idempotency/reconcile |
| Invalid JSON/schema | Dữ liệu không thể xử lý | Quarantine/repair |
| Authentication failure | Credential hết hạn/sai | Alert và sửa cấu hình, không bỏ |
| Authorization failure | Role/scope bị từ chối | Security/owner triage |
| SFTP transfer incomplete | File đang dở hoặc mất session | Staging/transfer recovery |
| Broker ack/offset lỗi | Trạng thái message chưa rõ | Đối chiếu container/source |
| DB deadlock | Transaction thất bại có thể khôi phục | Retry toàn transaction phù hợp |
| DLQ write thất bại | Chưa bảo toàn message | Propagate/fail, không NullChannel |
| Exception không phân loại | Không đủ bằng chứng | Alert/parking, không NullChannel |

**Mặc định an toàn:** không biết có thể bỏ hay không → **không bỏ**. Các ngoại lệ phải có rule/owner/hạn review rõ ràng.

## 12. Kiểm toán trước khi NullChannel

Vì message sẽ bị bỏ, thông tin cần để đối soát phải được tạo **trước đó**. Có thể thiết kế một cấu trúc tối thiểu:

~~~json
{
  "eventId": "partner-X:order-312:v2",
  "correlationId": "corr-7001",
  "source": "sftp-inbound",
  "flowId": "order-import",
  "endpointId": "dedupe-filter",
  "decision": "DISCARD_EXPECTED",
  "reasonCode": "ALREADY_PROCESSED",
  "policyVersion": "dedupe-rules-7",
  "evidenceRef": "inbox/order-312-v2",
  "decidedAt": "2026-11-23T09:00:00Z",
  "owner": "integration-operations"
}
~~~

Đây là schema minh họa, không phải format mặc định của NullChannel.

**Nguyên tắc:** nếu doanh nghiệp yêu cầu audit bền để chứng minh tại sao bỏ message, một console log hoặc metric counter đơn lẻ có thể chưa đủ. Cần kho audit phù hợp, kiểm soát truy cập, retention, correlation và cách đối soát với bản ghi xử lý thành công.

### Đơn vị đo không đồng nhất

- **discarded message count:** số message được hủy.
- **business events ignored:** số sự kiện nghiệp vụ xác nhận là no-op hoặc duplicate.
- **exception count:** số lần handler ném lỗi.
- **source redelivery count:** số lần nguồn giao lại.

Một business event có thể sinh nhiều ErrorMessage hoặc retries. **Không tính mỗi lần error retry là một business event bị bỏ**.

## 13. Không được biến lỗi không rõ thành “ignored”

Một exception có thể có bốn dạng:

- **Transient:** có khả năng phục hồi bằng retry.
- **Permanent:** dữ liệu/permission/config chưa phù hợp.
- **Unknown outcome:** không biết remote đã xử lý chưa.
- **Expected benign:** nghiệp vụ xác nhận không cần thêm hành động.

Chỉ dạng cuối hoặc **một lỗi đã recovered có bằng chứng** mới là ứng viên bỏ ErrorMessage. Nếu classifier dựa vào câu trả lời “lỗi này có thể tự hết không?” mà không xem business effect, nó sẽ phân loại sai.

### Ví dụ timeout sau HTTP POST

~~~text
10:00:00  POST /orders
10:00:01  ERP tạo order thành công
10:00:02  Response mất
10:00:03  Spring Integration nhận timeout
10:00:03  ErrorMessage được sinh tại error boundary
~~~

Nếu ErrorMessage chuyển thẳng NullChannel, chương trình có thể không biết order có thành công hay không, đồng thời message nguồn có nguy cơ được ack. **Đúng hơn:** kiểm tra idempotency key hoặc query ERP; chỉ khi chứng minh order đã được xử lý và trạng thái local đã được đồng bộ mới được đánh dấu no-op cho lỗi dư thừa.

## 14. Phân biệt discard thông báo và discard tác vụ nguồn

**ErrorMessage** là một thông báo về lỗi. Bỏ nó không tương đương:

- Bỏ business event (đã được thực thi hay chưa?).
- Rollback transaction.
- Ack JMS/AMQP.
- Commit Kafka offset.
- Xóa file SFTP.
- Giải phóng row JDBC bị CLAIMED.
- Phản hồi HTTP request/reply với kết quả hợp lệ.

Cần theo dõi song song:

1. **Error handling outcome**: message lỗi đã được phân loại, routing đến đâu?
2. **Business operation outcome**: side effect thành công/thất bại/chưa xác định?
3. **Source delivery outcome**: nguồn đã ack/commit/retry hay chưa?

**Một pipeline đã đạt “100% lỗi được chuyển tới NullChannel” có thể chỉ là 100% mất khả năng nhìn thấy lỗi**, không phải 100% độ tin cậy.

## 15. NullChannel và RequestHandlerRetryAdvice

**RequestHandlerRetryAdvice** có thể bọc một handler để retry khi exception xảy ra. Khi RetryPolicy hết attempts, có thể truyền lỗi lên hoặc sử dụng RecoveryCallback.

### RecoveryCallback trả bình thường

~~~java
// Phản ví dụ: có thể khiến caller/container hiểu handler đã xử lý.
advice.setRecoveryCallback(context -> {
    audit("retry_exhausted", context.getLastThrowable());
    return null;
});
~~~

Nếu việc audit không lưu đầy đủ business message, exception được nuốt có thể khiến nguồn ack **trước khi message được bảo toàn**. Đưa thông tin lỗi vào nullChannel sau callback không tự khắc phục nguy cơ.

### RecoveryCallback an toàn hơn khi chưa có parking

~~~java
advice.setRecoveryCallback(context -> {
    // Chưa bảo toàn message ở kho phục hồi => không báo success.
    throw new IllegalStateException(
        "Retry exhausted: delegate to source recovery",
        context.getLastThrowable());
});
~~~

Mẫu này minh họa chủ trương **propagate exception**; cách container xử lý vẫn phải kiểm tra theo từng adapter.

### Khi nào có thể kết thúc ở NullChannel sau recovery?

Nếu một bước recovery đã ghi thông điệp lỗi vào DLQ/parking bền, xác nhận việc ghi thành công, cập nhật business status đúng hợp đồng và quyết định ack nguồn được kiểm soát, thì **bản ErrorMessage chỉ dùng để thông báo phụ** có thể đi tới NullChannel. NullChannel vẫn không phải nơi thực hiện recovery.

## 16. Ví dụ chính sách phân loại: chỉ bỏ khi có bằng chứng

Một chính sách minh họa ở mức nghiệp vụ:

~~~yaml
# Pseudocode policy: các giá trị là minh họa, không phải YAML của Spring.
error_handling:
  default: INVESTIGATE
  rules:
    - id: duplicate-processed
      when:
        category: DUPLICATE_DELIVERY
        completed_business_state_verified: true
        same_business_event_version: true
      action: AUDIT_THEN_DISCARD
      destination: nullChannel
    - id: informational-noop
      when:
        category: OPTIONAL_NOTIFICATION
        required_business_effect: false
        approved_owner: integration-operations
      action: AUDIT_THEN_DISCARD
      destination: nullChannel
    - id: retryable-dependency
      when:
        category: TRANSIENT_REMOTE_FAILURE
      action: RETRY_OR_PARK
    - id: unknown-outcome
      when:
        category: REMOTE_OUTCOME_UNKNOWN
      action: RECONCILE
    - id: invalid-message
      when:
        category: INVALID_PAYLOAD
      action: QUARANTINE
    - id: security-failure
      when:
        category: AUTHORIZATION_FAILURE
      action: ESCALATE
~~~

Các điều kiện **completed_business_state_verified** và **same_business_event_version** đòi hỏi cơ chế kiểm tra trạng thái thực chứ không phải header do phía gửi tự tuyên bố. Nếu bằng chứng thiếu hoặc sai, rơi về INVESTIGATE.

### Thứ tự kiểm tra

1. Xác minh message và xác thực nguồn.
2. Xác định businessEventId, tenant, operation, version.
3. Phân loại lỗi thực tế và trạng thái đã xử lý.
4. Kiểm tra quyền/owner/hợp đồng no-op được phê duyệt.
5. Ghi audit/metric trước discard.
6. Chỉ gửi tới NullChannel nếu không có nghiệp vụ chưa hoàn tất.
7. Nếu không thể ghi audit bắt buộc hoặc tra cứu trạng thái, **không chuyển sang discard**.

## 17. Tại sao cần reason code cụ thể?

Một reason code như **EXPECTED_ERROR** là quá chung. Nó không nói vì sao nghiệp vụ không cần xử lý nữa.

| Reason code | Khi nào hợp lệ | Điều cần chứng minh |
|---|---|---|
| ALREADY_PROCESSED | Redelivery cùng business event đã hoàn tất | Durable inbox/result và event version |
| OUT_OF_SCOPE_FILE | File không thuộc hợp đồng import | Contract cho phép bỏ loại đó |
| OPTIONAL_REPLY | Một reply không được yêu cầu trong one-way flow | Không có caller đang chờ |
| SUPERSEDED_EVENT | Event cũ hơn version nghiệp vụ đã được commit | Ordering/version check đúng |
| NOOP_BUSINESS_RULE | Hành động có thể bỏ theo policy nghiệp vụ | Rule/owner và audit |
| RECOVERY_RECORDED | Lỗi đã được lưu bền ở nơi xử lý khác | Durable storage reference và ack contract |
| IGNORE_BY_DEFAULT | **Không nên dùng** | Không có bằng chứng và dễ che lỗi |

**Một reason code phải có định nghĩa, owner, mẫu số giám sát và test**. Không để đội vận hành thêm exception class vào danh sách ignore mà không có review.

## 18. File inbound/outbound: bỏ file nào, không bỏ file nào?

File adapters thường dùng poller và file filter để chọn message. Cần phân biệt **lọc file không thuộc phạm vi** với **loại bỏ lỗi xử lý file**.

### File inbound — trường hợp có thể bỏ

~~~text
/inbound/orders-20261123.csv.ready
/inbound/README.txt
/inbound/.upload-lock
/inbound/orders-20261123.csv.part
~~~

Nếu hợp đồng của đối tác quy định chỉ file **.ready** là dữ liệu, README và lock marker được xem là **out of scope**, không cần biến thành lỗi. Có thể loại chúng tại filter nguồn hoặc định tuyến message tương ứng tới NullChannel **sau khi xác nhận rule**.

File **.part** không phải “lỗi vô nghĩa”; đó là file chưa hoàn tất. Thay vì đánh dấu đã xử lý và bỏ vĩnh viễn, nên **không chọn nó ở lần poll hiện tại** và cho phép xử lý sau khi được publish ready.

### File inbound — trường hợp không được bỏ

| Sự cố | Vì sao không NullChannel trực tiếp? | Hướng giải quyết |
|---|---|---|
| CSV sai schema | Record chưa xử lý hợp lệ | Quarantine + reason code |
| File bị hỏng checksum | Có nguy cơ mất dữ liệu | Quarantine/cảnh báo đối tác |
| Permission denied | Lỗi hạ tầng vẫn tồn tại | Alert + sửa ACL |
| Không đọc được vì process lock | Có thể phục hồi | Poll lại/retry có giới hạn |
| Downstream ERP lỗi | Dữ liệu file chưa hoàn thành xử lý | Durable message state/retry |
| App restart sau accept-once | Có thể không thấy lại file | Persistent metadata + business idempotency |
| File đã archive trước commit | Replay khó hoặc có thể trùng | Sửa thứ tự archive/transaction |

### File outbound

Nếu ghi file lỗi giữa chừng, có thể tạo file **partial**. Retry cùng tên khi chưa kiểm tra trạng thái có thể ghi đè dữ liệu. Cần temporary output, stable final name, checksum/manifest hoặc quy tắc publish an toàn theo khả năng filesystem.

**NullChannel không làm việc ghi file trở nên nguyên tử**. Đừng bỏ ErrorMessage của outbound write khi chưa biết file đã hoàn tất hay chưa.

## 19. SFTP: bỏ noise có kiểm soát, không bỏ lỗi transfer

SFTP inbound/outbound có nhiều điểm lỗi: mở session, xác thực, list remote files, download/upload, rename, delete và đóng session.

| Tình huống | Có thể ignore? | Giải thích |
|---|---|---|
| Remote file trùng và durable inbox đã DONE cùng event/version | Có thể sau kiểm tra | Duplicate delivery/no-op |
| Marker hoặc file không thuộc hợp đồng | Có thể tại source filter | Không phải business record |
| SFTP tạm mất mạng | Không | Có thể retry/reconnect, phải giữ nguồn |
| Host-key mismatch | Không | Vấn đề bảo mật/trust |
| Permission denied | Không | Cần sửa quyền/đường dẫn |
| Download tạo local partial file | Không | File chưa hoàn chỉnh |
| Upload xong nhưng response bị mất | Không biết outcome | Kiểm tra remote state/checksum |
| Rename timeout | Không | Lệnh có thể đã hoàn tất |
| Xóa remote file thất bại | Không nếu có nghĩa vụ retention/delete | Cần retry/đối soát có kiểm soát |

### Ngữ nghĩa transfer và metadata

Remote accept-once filter có thể đánh dấu file đã thấy hoặc đã xử lý tùy adapter/config; dữ liệu này **không thay thế** bằng chứng nghiệp vụ thành công. Lần poll sau có thể không nhận lại file nếu filter hoặc metadata store đã lưu trạng thái.

~~~text
SFTP remote file ready
   -> local staging
   -> xác minh checksum/manifest
   -> tạo business event ID ổn định
   -> inbox / processing state
   -> downstream operation
   -> mark DONE hoặc PARKED
   -> archive/remove source theo contract
~~~

Nếu lỗi xảy ra **trước khi tạo message**, NullChannel ở downstream không có cơ hội xử lý nó. Nguồn cần reconnect/error handling. Nếu downstream đã nhận message nhưng thất bại, cần message store hoặc cơ chế replay bền.

Host-key mismatch là tín hiệu phải điều tra. Không bắt exception rồi gửi nullChannel để bỏ qua xác thực host; như vậy có thể che cấu hình sai hoặc nguy cơ kết nối tới máy không đáng tin.

## 20. HTTP inbound/outbound: trả lời caller hay bỏ error?

HTTP có hợp đồng request–response. Điều này làm việc “bỏ lỗi cho yên” đặc biệt nguy hiểm.

### HTTP inbound gateway

~~~text
Client -> HTTP inbound gateway -> business flow
                               -> success response / error response
~~~

Nếu downstream exception bị chuyển thành ErrorMessage rồi NullChannel và không có reply hợp lệ, client có thể đợi tới **reply timeout**, nhận lỗi tổng quát hoặc gửi lại request do không biết trạng thái. Nếu operation có side effect, retry từ client có thể tạo duplicate.

**Không sử dụng NullChannel để né việc trả HTTP status đúng hợp đồng.** Nếu request webhook đã xử lý là no-op hợp lệ, trả **response thành công có chủ đích** theo contract và ghi dedupe audit; không làm caller chờ vô định.

### HTTP outbound gateway

| Tình huống | Hướng xử lý | Vì sao |
|---|---|---|
| GET endpoint phụ và contract cho phép mất kết quả | Có thể fallback/no-op được phê duyệt | Không ảnh hưởng tác vụ chính |
| POST tạo payment bị timeout | OUTCOME_UNKNOWN | Remote có thể đã commit |
| HTTP 503 | Retry/delayed retry | Lỗi transient |
| HTTP 429 | Backoff/rate-limit | Không được spam request |
| 400 invalid payload | Quarantine | Cần sửa dữ liệu |
| 401/403 | Security/config handling | Không retry mãi |
| 409 already processed có bằng chứng | Có thể dedupe | Cần kiểm tra business key/payload |
| 404 | Tùy nghiệp vụ | Permanent hoặc eventual consistency |

**Không đồng nhất mã 409 với thành công:** xung đột có thể là một tài nguyên khác đã được tạo. Cần đối chiếu business key, payload/version và kết quả.

### HTTP POST có idempotency key

~~~mermaid
sequenceDiagram
    participant I as Integration Flow
    participant P as Partner ERP
    participant D as ERP Database
    I->>P: POST order + Idempotency-Key
    P->>D: Commit order
    D-->>P: OK
    Note over I,P: Response bị mất
    I->>I: Phân loại OUTCOME_UNKNOWN
    I->>P: Query trạng thái / retry cùng key nếu contract cho phép
    P-->>I: Kết quả order đã xử lý
    I->>I: Đồng bộ state, audit dedupe
    Note over I: Chỉ bỏ ErrorMessage phụ khi nghiệp vụ đã hoàn tất
~~~

Bỏ ErrorMessage **sau khi đã có kết quả xác minh** khác với bỏ ngay khi gặp read timeout.

## 21. JMS: ErrorMessage bị bỏ có thể ảnh hưởng rollback/ack

JMS có session transacted, acknowledgement mode, broker redelivery và DLQ tùy cấu hình listener/container.

### Kịch bản nguy hiểm

~~~text
JMS listener nhận message
    -> DB update thất bại
    -> ErrorMessage routed to nullChannel
    -> error path kết thúc bình thường
    -> container có thể xem delivery đã xử lý
    -> message được ack/commit

Rủi ro: database chưa cập nhật, nguồn không còn message.
~~~

Nếu không có bản lưu DLQ hoặc rollback, message có nguy cơ **biến mất** dù database chưa cập nhật.

### Câu hỏi bắt buộc

1. Listener/session có transacted không?
2. Exception có thật sự propagate tới container không?
3. Container ack/commit/rollback dựa vào tín hiệu nào?
4. ErrorMessage được phát ở tầng nào, ảnh hưởng callback không?
5. Broker redelivery limit/DLQ thế nào?
6. Side effect DB/HTTP trước đó có idempotent không?
7. Poison message được phân loại và đưa tới đâu?

Nếu duplicate delivery đã được **durable inbox** xác minh hoàn tất, handler có thể quyết định no-op và kết thúc thành công theo nghiệp vụ. Lúc đó ack là **có chủ đích**, và ErrorMessage thông tin phụ có thể được bỏ sau audit. Không dùng NullChannel làm shortcut thay cho dedupe.

## 22. AMQP/RabbitMQ: requeue, DLQ và trường hợp đã xử lý

Với AMQP inbound:

- Propagate exception có thể kích hoạt chính sách nguồn.
- RecoveryCallback trả bình thường có thể làm container coi message được xử lý.
- Đẩy ErrorMessage tới NullChannel không tự gây nack hoặc chuyển DLQ.
- Requeue ngay không giới hạn có thể tạo **hot loop**, nên cần delayed retry/TTL/DLX hoặc chiến lược phù hợp.
- Prefetch/concurrency quyết định số delivery đang giữ worker slot.

### Duplicate delivery

~~~text
AMQP message eventId=invoice-882-v3
    -> inbox kiểm tra eventId + version
    -> đã có trạng thái DONE, kết quả khớp
    -> ghi audit ALREADY_PROCESSED
    -> kết thúc message processing
~~~

Đây là **business no-op hợp lệ**. Không cần ném exception chỉ để gửi ErrorMessage tới NullChannel. Một informational event phụ sau đó có thể kết thúc ở NullChannel.

### Outbound AMQP

Nếu publish tới broker đã thành công nhưng client không nhận confirm, retry gửi có thể tạo message trùng. Cần outbox/stable event ID/consumer dedupe. **Publisher confirm không chứng minh consumer đã xử lý nghiệp vụ**.

Không gửi ErrorMessage publish failure vào NullChannel khi trạng thái outbox chưa đúng. Ghi DLQ trên broker khác rồi ack nguồn **không tự là một transaction nguyên tử**.

## 23. Kafka: bỏ ErrorMessage không tự commit/seek offset

Kafka có record, partition, offset và consumer group. Spring Integration Kafka inbound adapter chuyển record thành message; Kafka listener/container error handler quản lý retry, seek, commit hoặc DLT theo cấu hình.

| Thành phần | Trách nhiệm |
|---|---|
| Kafka consumer/client | Poll, heartbeat, consumer group |
| Container/error handler | Ack/commit, retry/seek/DLT theo config |
| Spring Integration adapter/channel | Mang record vào message flow |
| Business handler | Tạo side effects và business outcome |
| ErrorMessage/error flow | Diễn đạt lỗi xảy ra |
| NullChannel | Bỏ message được gửi đến nó |

**NullChannel không tự là Kafka DLT, không tự seek lại offset và không tự điều khiển commit.**

### Ví dụ ordering

~~~text
Partition P:
    offset 100: order-created
    offset 101: order-updated
    offset 102: order-cancelled
~~~

Nếu offset 100 gặp lỗi DB, chỉ bỏ ErrorMessage mà commit offset có thể cho offset 101/102 xử lý trên trạng thái sai. Nếu ghi lỗi vào DLT và xử lý record tiếp, **thứ tự nghiệp vụ** cũng phải được thiết kế.

Một event cũ hơn business version đã commit **có thể** được đánh dấu superseded, nhưng phải kiểm tra theo key/aggregate/version, không chỉ timestamp. Nếu xác minh nó không cần áp dụng, handler có thể ack theo contract; NullChannel chỉ dùng để bỏ thông báo phụ.

Đặc tính exactly-once trong một phạm vi Kafka không tự bảo đảm exactly-once trên HTTP partner và database ở transaction khác. Không dùng NullChannel để che các khoảng hở cần inbox/outbox.

## 24. JDBC inbound/outbound: row state không biến mất cùng ErrorMessage

JDBC polling có thể chọn row trạng thái NEW để xử lý. Nếu row đã được claim và downstream handler lỗi:

- Bỏ ErrorMessage không tự reset lease/trạng thái row.
- Row có thể kẹt PROCESSING.
- Mark DONE quá sớm có thể mất dữ liệu.
- Claim lại sau khi remote đã thành công có thể duplicate.

~~~text
NEW -> CLAIMED -> PROCESSING -> DONE
                  |
                  +-> RETRY_WAIT -> PROCESSING
                  |
                  +-> INVALID / PARKED
~~~

Cần stable event ID, transaction/atomic claim, lease owner/expiry, attempt count và nextAttemptAt bền qua restart.

| Lỗi | Hướng xử lý |
|---|---|
| Connection pool tạm cạn | Backoff/bulkhead/monitor |
| Deadlock/serialization conflict | Rollback, retry transaction mới |
| Constraint violation | Xác minh duplicate hoặc dữ liệu invalid |
| Schema mismatch | Sửa migration/SQL |
| Timeout sau commit không rõ | Query theo business ID, reconcile |
| Transaction rollback-only | Không tiếp tục trong transaction hỏng |

Unique constraint violation **có thể** là duplicate đã xử lý, cũng có thể là conflict thật. Không bắt toàn bộ DataIntegrityViolationException rồi gửi NullChannel.

Nếu database update là tác vụ bắt buộc, lỗi chưa giải quyết phải được propagate hoặc chuyển PARKED/retry. ErrorMessage discarded không chứng minh row đã DONE.

## 25. Gateway và replyChannel: bỏ reply có thể làm caller chờ

Sử dụng NullChannel làm **reply channel** có thể phù hợp với message một chiều không ai cần kết quả. Với gateway request–reply:

- Caller kỳ vọng một reply/error.
- Reply vào NullChannel có thể làm caller timeout.
- Error reply vào NullChannel làm mất thông tin nguyên nhân.
- Caller retry sau timeout có thể làm lặp side effect.
- Không dùng discard reply để ngụy trang lỗi thành success.

| Flow | Reply có cần không? | Khuyến nghị |
|---|---|---|
| Event notification one-way đã ghi outbox | Không | Có thể bỏ reply phụ |
| HTTP GET gateway trả trạng thái | Có | Không discard reply |
| POST gateway tạo order | Có hoặc cần ack theo contract | Không discard nếu outcome unknown |
| Fire-and-forget metric event | Có thể không | Chấp nhận discard theo policy |
| Financial transaction event | Có | Durable state và response rõ |

**Không có response không đồng nghĩa thành công.** Phải định nghĩa rõ fire-and-forget cho từng nghiệp vụ.

## 26. Recovery và NullChannel sau khi retry exhausted

~~~text
A. Handler lỗi
   -> RetryPolicy exhausted
   -> RecoveryCallback rethrows
   -> container/caller xử lý error/rollback

B. Handler lỗi
   -> RetryPolicy exhausted
   -> recovery ghi durable PARKED thành công
   -> source ack theo contract
   -> ErrorMessage phụ được audit rồi NullChannel
~~~

Nếu RecoveryCallback chỉ log và return null **trước khi có recovery record**, trường hợp B không được bảo đảm. NullChannel không sửa điều đó.

Một recoverer gửi ErrorMessage tới error channel có thể hữu ích, nhưng cần xác minh error flow có lưu bền và **giá trị return của recoverer ảnh hưởng handler/container** thế nào. Thành công của recovery được đo bằng **trạng thái nghiệp vụ đã xử lý hoặc bảo toàn bền vững**, không phải một lệnh send tới channel.

## 27. Policy discard có owner, scope và kỳ review

| Thuộc tính | Ví dụ |
|---|---|
| policyId | ignore-duplicate-v7 |
| scope | partner-X, order-import, schema version>=2 |
| reasonCode | ALREADY_PROCESSED |
| predicate | inbox DONE và hash/version khớp |
| allowedSource | service account inbound đã xác thực |
| impact | không phát sinh order mới |
| auditRequired | true |
| owner | Integration Operations |
| approver | Application Owner; Security nếu cần |
| reviewDate | kỳ review được tổ chức quy định |
| expiry | áp dụng khi rule tạm thời |
| metrics | discarded_total, unknown_total, false_discard_incidents |
| fallback | PARKED khi không đủ evidence |

Không tạo wildcard “mọi lỗi từ adapter X đều bỏ”. Quy tắc có scope hẹp giúp lỗi mới thuộc adapter ấy vẫn được điều tra.

### Quy trình thay đổi rule

1. So sánh tập case trước/sau.
2. Test lỗi trước đây phải retry/alert.
3. Đo lượng message mới được discard.
4. Kiểm tra owner và ngày review.
5. Có rollback/feature flag nếu phát hiện silent loss.
6. Lưu policy version trong audit.

## 28. Observability: đã bỏ thì vẫn phải biết vì sao

Khi NullChannel nhận message, nhánh downstream thường không còn tiếp tục. Vì thế cần đo **quyết định discard trước khi gửi vào channel**, không lấy việc không còn ErrorMessage làm bằng chứng hệ thống khỏe.

| Metric | Định nghĩa | Ý nghĩa |
|---|---|---|
| **discard_decisions_total** | Quyết định discard theo reasonCode/flow | Phát hiện tăng bất thường |
| **verified_discard_rate** | Discard có evidence đủ ÷ tổng quyết định discard | Không coi unknown là hợp lệ |
| **error_route_to_null_total** | ErrorMessage thực đi nullChannel theo policy | Phân biệt với Filter discard |
| **unexpected_errors_total** | Lỗi không có policy ignore hợp lệ | Ưu tiên triage |
| **quarantined_messages_total** | Message invalid đã giữ để sửa | Không gộp vào discarded |
| **parked_messages_total** | Message còn nghĩa vụ xử lý đang chờ | Theo tuổi và mức quan trọng |
| **dlq_backlog_age_seconds** | Tuổi lớn nhất/phân vị của lỗi chưa giải quyết | Tránh backlog bị quên |
| **business_events_completed_total** | Tác vụ thật sự DONE | Không tăng chỉ vì NullChannel nhận message |
| **source_redeliveries_total** | Số lần broker/source giao lại | Tách retry và discard |
| **duplicate_effect_total** | Side effect trùng đã xác minh | Đo thiệt hại nghiệp vụ |
| **ack_without_outcome_total** | Ack/commit thiếu DONE/PARKED/no-op hợp lệ | Cảnh báo silent loss |
| **unknown_outcome_total** | Remote outcome chưa biết | Không được default discard |

**Không dùng eventId/orderId/correlationId làm metric label** vì cardinality lớn. Đặt chúng vào log/tracing; metric label theo flow, errorCategory, reasonCode và outcome có số giá trị hữu hạn.

### Dấu hiệu lỗi bị che

Nếu một ngày sau khi global errorChannel được route tới NullChannel, dashboard còn **0 errors** nhưng số order DONE giảm, source input vẫn tăng và DLQ không nhận record nào, đây có thể là **silent data loss**. Hãy đối soát số business events từ nguồn với DONE, PARKED, QUARANTINED, DLQ và các quyết định no-op đã có bằng chứng.

## 29. Audit tối thiểu và bảo mật thông tin

Mỗi quyết định discard quan trọng nên giữ:

- Stable businessEventId/correlationId;
- Source/flow/endpoint và loại thông điệp;
- Error category, reasonCode và policy version;
- Evidence reference (inbox DONE, state/version check, hợp đồng no-op);
- Thời điểm lỗi, thời điểm phân loại, thời điểm discard;
- Quyền của service/owner chịu trách nhiệm;
- Source ack/commit outcome nếu đã xác minh;
- Kết quả cuối: DISCARDED_EXPECTED, NOOP_CONFIRMED hoặc RECOVERY_RECORDED.

~~~json
{
  "auditId": "discard-20261123-0104",
  "businessEventId": "partner-X:order-312:v2",
  "correlationId": "corr-7001",
  "source": "amqp-inbound",
  "flowId": "order-import",
  "reasonCode": "ALREADY_PROCESSED",
  "decision": "DISCARD_EXPECTED",
  "policyVersion": "ignore-duplicate-v7",
  "evidenceRef": "inbox/order-312-v2",
  "sourceOutcome": "ACK_AFTER_NOOP_CONFIRMED",
  "decidedAt": "2026-11-23T10:15:00Z",
  "owner": "integration-operations"
}
~~~

Schema trên chỉ minh họa. **Không ghi** password, bearer token, refresh token, session cookie, private key SFTP, Authorization header hoặc toàn bộ dữ liệu khách hàng vào log. Nếu cần giữ payload để replay, dùng message store có mã hóa/phân quyền/retention và lưu payload reference.

Logging của NullChannel đối với ErrorMessage có thể tùy phiên bản/cấu hình. Không xem việc ghi log mặc định là audit bền. Khi yêu cầu audit bắt buộc, cần **lưu thành công trước discard** và xác định hành vi khi audit store lỗi.

## 30. Java: chốt bảo vệ trước NullChannel

Ví dụ sau thể hiện ý tưởng của **service activator chỉ gửi ErrorMessage đã có bằng chứng hợp lệ**. Các kiểu DiscardPolicy, DiscardDecision và DiscardAuditStore do ứng dụng tự định nghĩa; đây không phải file độc lập có thể biên dịch nguyên trạng.

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ErrorMessage;

public class ExpectedErrorDiscardHandler {
    private final MessageChannel nullChannel;
    private final DiscardPolicy policy;
    private final DiscardAuditStore audit;

    public ExpectedErrorDiscardHandler(
            @Qualifier("nullChannel") MessageChannel nullChannel,
            DiscardPolicy policy,
            DiscardAuditStore audit) {
        this.nullChannel = nullChannel;
        this.policy = policy;
        this.audit = audit;
    }

    @ServiceActivator(inputChannel = "classifiedErrorMessages")
    public void handle(ErrorMessage error) {
        DiscardDecision decision = policy.evaluate(error);

        if (!decision.isVerifiedExpected()) {
            throw new IllegalStateException(
                    "Error is not safe to discard");
        }

        // Giả định persist xác nhận ghi bền theo contract.
        audit.persist(decision);

        boolean accepted = nullChannel.send(error);
        if (!accepted) {
            throw new IllegalStateException(
                    "NullChannel did not accept message");
        }
    }
}
~~~

### Giới hạn và trách nhiệm còn lại

- Policy phải dựa vào **business state**, không chỉ exception class.
- Nếu không có evidence, **không** gọi nullChannel.
- Lỗi classifier/audit cần đi nhánh an toàn, tránh **error loop** quay lại chính classifiedErrorMessages.
- Audit bền trước discard vẫn **không tự chứng minh** nguồn đã ack đúng; phải kiểm tra transaction/container.
- Giá trị true của send không có nghĩa business event đã DONE.
- Nếu error flow là async, cần bảo toàn message **trước ranh giới source ack** khi cần at-least-once.
- Không tự thay global errorChannel bằng handler này; hãy dùng kênh phân loại riêng để không nuốt lỗi khác.

## 31. Runbook khi discard tăng bất thường

Các tín hiệu:

- discard_decisions_total tăng gấp nhiều lần so với baseline;
- business_events_completed_total giảm dù inbound volume ổn định;
- ALREADY_PROCESSED tăng nhưng durable inbox không có DONE khớp;
- DLQ/parking rỗng bất thường;
- nguồn đã ack dù không tìm thấy kết quả nghiệp vụ.

### Các bước ứng phó

1. **Khoanh vùng** theo flow, endpoint, reasonCode, policyVersion và thời điểm thay đổi.
2. **Đánh giá ảnh hưởng** bằng source event IDs và số record quan trọng.
3. **Vô hiệu hóa/rollback rule ignore** đáng ngờ, chuyển unknown sang INVESTIGATE/PARKED.
4. **Bảo toàn nguồn**: broker retention, Kafka offsets, file staging, JDBC leases, inbox/outbox.
5. **Đối soát** inbound IDs với DONE/PARKED/QUARANTINED/DLQ và remote outcomes.
6. **Replay có kiểm soát** bằng stable eventId, idempotency, rate limits và ordering phù hợp.
7. **Kiểm thử lại** duplicate/no-op và các lỗi không được bỏ.
8. **Hậu kiểm** bằng regression tests, review owner/expiry và policy version.

Không nên sửa bằng cách thêm wildcard ignore, xóa DLQ, reset offset mù hoặc log toàn bộ secret để tìm nguyên nhân.

## 32. Ma trận kiểm thử NullChannel và error handling

Mỗi test phải nêu **đầu vào, error category, đích mong đợi, business outcome, source ack/commit và audit evidence**.

| ID | Tình huống | Kết quả cần kiểm chứng |
|---|---|---|
| N1 | Message cố ý đi NullChannel | Nhánh kết thúc, không có downstream side effect |
| N2 | ErrorMessage duplicate có inbox DONE | Audit + discard |
| N3 | Cùng event ID nhưng payload/version khác | Không discard mù |
| N4 | File README ngoài hợp đồng | Filter discard đúng |
| N5 | File .part chưa hoàn tất | Không đánh dấu processed vĩnh viễn |
| N6 | File .ready sai schema | Quarantine |
| N7 | SFTP connection reset | Retry/reconnect có budget |
| N8 | SFTP host-key mismatch | Alert bảo mật, không ignore |
| N9 | SFTP upload ACK mất | Reconcile remote state |
| N10 | HTTP 503 | Retry/delayed retry |
| N11 | HTTP 401/403 | Xử lý auth/config |
| N12 | POST đã commit nhưng response mất | OUTCOME_UNKNOWN, idempotency/query |
| N13 | HTTP gateway cần reply | Không discard gây timeout |
| N14 | One-way informational reply | Được bỏ theo contract |
| N15 | JMS lỗi DB, error flow nuốt lỗi | Test phát hiện ack thiếu outcome |
| N16 | JMS duplicate đã DONE | No-op/ack có evidence |
| N17 | AMQP requeue lặp | Delayed retry/DLQ, không hot loop |
| N18 | AMQP publish confirm mất | Không bỏ unknown |
| N19 | Kafka record lỗi DB | Không commit offset trái policy |
| N20 | Kafka event cũ chưa có version proof | INVESTIGATE, không discard |
| N21 | Kafka event superseded đã xác minh | No-op có audit |
| N22 | JDBC deadlock | Retry transaction mới |
| N23 | JDBC row kẹt PROCESSING | Lease/recovery hoạt động |
| N24 | Async error channel thiếu subscriber | Không coi recovery hoàn tất |
| N25 | Error flow không có durable store | Không báo PARKED thành công |
| N26 | Audit bắt buộc ghi lỗi | Không discard không dấu |
| N27 | RecoveryCallback trả bình thường | Kiểm ack/commit/persistence |
| N28 | RetryAdvice exhausted rồi rethrow | Container/caller xử lý đúng |
| N29 | Restart trước NullChannel | Source/state nhất quán |
| N30 | Restart sau DLQ trước ack | Không mất, duplicate được dedupe |
| N31 | Policy ignore wildcard sai | Regression test fail |
| N32 | Một event redelivery nhiều lần | Chỉ tính một business event DONE |
| N33 | Lỗi chưa phân loại | INVESTIGATE |
| N34 | Error count về 0 đột ngột | Không suy ra mọi việc thành công |
| N35 | ErrorMessage chứa token | Secret được redact |
| N36 | DirectChannel ném exception | Không mặc định đi global errorChannel |
| N37 | ExecutorChannel phát error | Đúng error path và source guarantee |
| N38 | Side effect đã xảy ra trước discard | Discard không được coi là rollback |
| N39 | Event compliance-critical bị đánh dấu optional | Rule bị từ chối |
| N40 | Nhiều lỗi làm nghẽn queue | Dùng backpressure, không xóa lỗi |
| N41 | Evidence store của dedupe không sẵn | Không NullChannel |
| N42 | Reply gateway bị route NullChannel | Test phát hiện timeout |
| N43 | ErrorMessage đã log, payload chưa bền | Không coi là replayable |
| N44 | Message bị bỏ trước khi audit | Test phát hiện thiếu evidence |
| N45 | Policy ignore hết hạn | Không được discard |
| N46 | Global errorChannel có nhiều subscriber | Không vô tình tắt logging/monitoring |

### Crash-point tests

Dừng process:

1. Sau khi nhận message, trước inbox;
2. Sau khi remote commit, trước response;
3. Sau khi classifier xác nhận duplicate, trước audit;
4. Sau khi ghi DLQ, trước ack;
5. Sau khi ack, trước metrics.

Mỗi điểm phải có phương án xác định event **DONE/PARKED/UNKNOWN/cần redelivery**, không chỉ kiểm tra NullChannel không ném exception.

## 33. Bài tập tình huống: giảm noise mà không mất đơn hàng

### Bối cảnh

Doanh nghiệp có flow:

~~~text
SFTP inbound adapter + poller
    -> staging
    -> parse / validate
    -> HTTP outbound gateway ERP
    -> JDBC order status
    -> AMQP notification
~~~

Vì quá nhiều ErrorMessage, đội vận hành muốn đưa **toàn bộ errorChannel tới nullChannel**. Trong ngày xảy ra:

| Mốc | Diễn biến |
|---|---|
| 08:00 | Order A được gửi lại cùng ID/version |
| 08:02 | Durable inbox có A ở DONE, checksum khớp |
| 08:05 | Order B JSON sai schema |
| 08:10 | ERP trả HTTP 503 suốt 15 phút |
| 08:12 | POST order C đã commit, response mất |
| 08:14 | JDBC update D deadlock |
| 08:18 | AMQP broker temporarily down |
| 08:20 | File E bị đứt SFTP transfer |
| 08:30 | Kafka nhận order-updated cũ hơn version đã commit |
| 09:00 | Error dashboard về 0 sau thay đổi routing |

### Nhiệm vụ

1. Phân loại mỗi tình huống thành EXPECTED_IGNORE, INVALID, TRANSIENT, OUTCOME_UNKNOWN hoặc loại khác.
2. Tình huống nào có thể kết thúc tại NullChannel **sau khi có bằng chứng**?
3. Vì sao đưa toàn bộ global errorChannel vào NullChannel nguy hiểm?
4. Thiết kế classifier/recovery cho từng nhóm.
5. Nếu nguồn là JMS/AMQP/Kafka, điều gì cần kiểm chứng trước khi handler trả bình thường?
6. Vì sao HTTP gateway cần reply không được bỏ reply?
7. Chọn 6 metrics phát hiện false discard.
8. Đề xuất 8 negative tests bảo vệ rule.

### Lời giải tham khảo

**A — duplicate DONE:** durable inbox xác minh cùng business ID/version và checksum, có audit ALREADY_PROCESSED. Có thể no-op và kết thúc theo hợp đồng; thông báo phụ có thể tới NullChannel.

**B — invalid:** quarantine với reasonCode, payload reference và đường sửa/replay, không discard.

**ERP 503:** retry ngắn với backoff, sau đó delayed retry nếu lỗi kéo dài; không NullChannel.

**C — remote outcome unknown:** query ERP bằng business ID, dùng idempotency contract hoặc chuyển PARKED/OUTCOME_UNKNOWN; không bỏ chỉ vì timeout.

**D — JDBC deadlock:** rollback và retry transaction mới, không gửi lại HTTP đã thành công.

**AMQP outage:** dùng outbox để bảo toàn notification sau DB commit, retry publish khi broker hồi phục; không bỏ lỗi nếu thông báo là bắt buộc.

**SFTP E:** retry transfer và quản lý local partial/remote metadata; không đánh dấu file hoàn tất.

**Kafka event superseded:** chỉ no-op nếu business state/version check chứng minh event cũ không cần áp dụng và contract cho phép; nếu không, INVESTIGATE.

**Lỗi tổng quát:** global errorChannel chứa nhiều nguồn lỗi; nullChannel không lưu được error, không tự ack đúng hay DLQ, nên không thể thay thế triage.

**Metrics:** discard_decisions_total, verified_discard_rate, unexpected_errors_total, unknown_outcome_total, ack_without_outcome_total và business_events_completed_total; thêm age of parking/DLQ.

**Negative tests:** JSON invalid, auth failure, HTTP POST timeout sau commit, dedupe thiếu evidence, audit store down, HTTP reply cần thiết, restart sau DLQ-before-ack và Kafka thiếu version proof.

### Kiến trúc mục tiêu

~~~mermaid
flowchart TD
    S["Inbound message / ErrorMessage"] --> V["Validate + classify + query business state"]
    V --> C{"Safe outcome?"}
    C -->|"VERIFIED_NOOP / DUPLICATE"| A["Audit reason + metric"]
    A --> N["nullChannel"]
    C -->|"INVALID"| Q["Quarantine"]
    C -->|"TRANSIENT"| R["Retry bounded / delayed retry"]
    C -->|"OUTCOME_UNKNOWN"| P["Reconcile / PARKED"]
    C -->|"SECURITY / UNCLASSIFIED"| X["Alert + investigate"]
    Q --> B["Durable store + owner"]
    R --> B
    P --> B
    X --> B
    B --> F["Replay / close after verified resolution"]
~~~

Nếu error flow chạy async và nguồn đã ack trước phân loại, sơ đồ chưa khép kín độ tin cậy; cần **bảo toàn message trước ranh giới ack** hoặc thay đổi transaction/source recovery theo ngữ nghĩa adapter.

## 34. Anti-pattern thường gặp

| Anti-pattern | Rủi ro | Giải pháp |
|---|---|---|
| Route global errorChannel tới nullChannel | Mất giám sát và error recovery | Classification hẹp, default INVESTIGATE |
| Bỏ mọi ErrorMessage vì đã log | Silent data loss | Evidence nghiệp vụ + durable audit |
| Coi NullChannel là DLQ | Không replay được message | Parking/DLQ thật |
| Catch mọi exception rồi return success | Ack sai | Propagate hoặc durable recovery |
| Filter discard mọi file lỗi | Mất dữ liệu hợp lệ | Tách out-of-scope và invalid |
| Dedupe theo MessageHeaders.ID | Không ổn định qua redelivery | Business event ID |
| Bỏ HTTP timeout sau POST | Side effect không rõ, có thể trùng | Idempotency/reconcile |
| Ignore lỗi auth/host-key | Che vấn đề bảo mật | Security triage |
| Kafka offset được commit khi chưa hoàn tất | Mất record hoặc sai thứ tự | Container error handler + DLT |
| Ack JMS/AMQP trước parking | Không còn nguồn để replay | Đúng transaction/ack boundary |
| Không có reasonCode | Không kiểm toán được | Policy và audit |
| Log secret trong ErrorMessage | Rò rỉ credential | Redaction |
| KPI chỉ đếm số errors | “Xanh giả” | Business DONE, backlog, unknown |
| Ignore rule không owner/review | Danh sách ngoại lệ phình ra | Governance/expiry |
| Ghi audit lỗi vẫn discard | Mất chứng cứ | Fail safe |
| Bỏ reply của request–reply gateway | Caller timeout | Reply/error contract |
| Dùng NullChannel để giảm backlog | Che mất dữ liệu | Backpressure/bulkhead/durable retry |

## 35. Checklist thiết kế NullChannel an toàn

- [ ] Xác định message sẽ bị bỏ là business message, ErrorMessage hay reply phụ.
- [ ] Policy discard có scope, reasonCode, owner, evidence và kỳ review.
- [ ] Lỗi chưa phân loại mặc định INVESTIGATE.
- [ ] Không route toàn bộ global errorChannel sang nullChannel.
- [ ] Lỗi transient, invalid, unknown, security đi đúng retry/quarantine/parking/alert.
- [ ] Durable inbox/state dùng để xác minh duplicate/superseded events.
- [ ] Audit/metric được ghi **trước discard** khi contract yêu cầu.
- [ ] NullChannel không được dùng như DLQ/retry scheduler/message store.
- [ ] Đã test DirectChannel/ExecutorChannel/poller/errorChannel theo topology.
- [ ] HTTP gateway request–reply có response đúng hợp đồng.
- [ ] JMS/AMQP ack/rollback/DLQ đã kiểm thử khi error flow trả bình thường.
- [ ] Kafka offset/seek/DLT và ordering được kiểm soát riêng.
- [ ] File/SFTP có ready marker, transfer state, metadata và replay.
- [ ] JDBC có row lease, transaction rollback và state DONE/PARKED rõ.
- [ ] RecoveryCallback không báo success trước khi recovery được bảo toàn.
- [ ] Có idempotency/reconciliation/outbox cho side effects ngoài DB.
- [ ] Có metric discard, unexpected error, ack_without_outcome và business DONE.
- [ ] Không ghi token/private key/password/PII không cần thiết.
- [ ] Có negative tests invalid/auth/timeout-after-commit/missing evidence/audit failure.
- [ ] Có crash tests cho DLQ-before-ack, restart và duplicate.
- [ ] Có runbook rollback ignore rule và đối soát.

## 36. Thuật ngữ và tài liệu tham khảo

| Thuật ngữ | Ý nghĩa |
|---|---|
| **NullChannel** | MessageChannel nhận rồi chủ động bỏ message |
| **Black-hole channel** | Điểm cuối không truyền message tới xử lý nghiệp vụ |
| **ErrorMessage** | Message mang Throwable/error context |
| **errorChannel** | Kênh định tuyến ErrorMessage theo cấu hình |
| **discardChannel** | Kênh nhận message bị Filter loại |
| **No-op** | Hành động hợp lệ không cần thay đổi trạng thái |
| **Idempotency** | Lặp cùng business event không tạo thêm side effect |
| **Unknown outcome** | Không rõ remote đã commit hay chưa |
| **DLQ/DLT/parking** | Kho giữ thông điệp lỗi để phục hồi |
| **Ack/commit** | Nguồn đánh dấu tiến độ xử lý |
| **Redelivery** | Broker/source giao lại message |
| **Quarantine** | Cách ly message invalid để sửa |
| **RecoveryCallback** | Callback khi retry exhausted |
| **DirectChannel** | Channel dispatch đồng bộ |
| **ExecutorChannel** | Channel dispatch qua executor |
| **Policy version** | Phiên bản quy tắc phân loại có thể kiểm toán |

### Tài liệu đọc sâu

- **Spring Integration Reference — Message Channels:** NullChannel, DirectChannel, ExecutorChannel, QueueChannel và PublishSubscribeChannel.
- **Spring Integration Reference — Error Handling:** ErrorMessage, errorChannel, luồng xử lý lỗi.
- **Spring Integration Reference — Filters / Routers:** filter predicate, discardChannel và router.
- **Spring Integration Reference — Message Handler Advice:** RequestHandlerRetryAdvice và recovery.
- **Spring Integration Reference — File, SFTP, HTTP, JMS, AMQP, Kafka, JDBC adapters/gateways:** ngữ nghĩa từng nguồn/đích.
- **Spring Retry Reference:** RetryTemplate, RetryPolicy, BackOffPolicy, RecoveryCallback.
- **Spring AMQP / Spring for Apache Kafka Reference:** nack/requeue, retry, offset, DLQ/DLT.
- **Enterprise Integration Patterns:** Invalid Message Channel, Dead Letter Channel, Idempotent Receiver, Message Store, Guaranteed Delivery.

### Câu hỏi tự kiểm tra

1. NullChannel khác errorChannel và DLQ thế nào?
2. Filter.discardChannel có tự bắt mọi exception từ filter predicate không?
3. Vì sao ErrorMessage bị bỏ không chứng minh JMS đã rollback?
4. Vì sao HTTP gateway cần reply không nên đưa reply vào NullChannel?
5. Điều kiện nào cho phép discard duplicate?
6. Vì sao POST timeout sau commit cần reconciliation?
7. NullChannel có tự commit Kafka offset không?
8. Một ignore rule hợp lệ phải có thông tin gì?
9. Error dashboard về 0 sau routing có thể báo hiệu gì?
10. Khi audit store bắt buộc down, có nên tiếp tục discard không?

### Đáp án ngắn

1. NullChannel hủy message; errorChannel định tuyến lỗi; DLQ giữ lỗi để điều tra/replay.
2. Không, discardChannel dành cho message bị loại theo predicate, không phải mọi exception thực thi.
3. Ack/rollback do container/transaction và đường exception quyết định.
4. Caller có thể timeout rồi retry, tạo trạng thái mơ hồ.
5. Durable inbox/state chứng minh cùng business event/version đã DONE; có audit.
6. Remote có thể đã tạo side effect; phải dùng idempotency/query trạng thái.
7. Không, offset thuộc consumer/container.
8. Scope, reasonCode, predicate, evidence, owner, review/expiry, audit và fallback.
9. Có thể error bị nuốt; phải đối chiếu business DONE/backlog và source.
10. Không nếu audit bền là điều kiện bắt buộc; phải giữ lỗi để xử lý theo policy.

**Điểm cần nhớ:** **NullChannel không sửa lỗi; nó chỉ là điểm hủy message có chủ đích.** Trong Spring Integration Adapters, chỉ gửi ErrorMessage hoặc message không cần thiết tới NullChannel **sau khi đã phân loại, xác minh kết quả nghiệp vụ và hoàn tất nghĩa vụ audit/recovery**. Khi vẫn còn nghĩa vụ xử lý, thiếu bằng chứng hoặc nguồn có nguy cơ ack/commit sai, hãy **giữ lỗi, retry, rollback, quarantine hoặc DLQ/parking** thay vì tạo ra sự im lặng không thể khôi phục.




