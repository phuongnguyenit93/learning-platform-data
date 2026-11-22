# Thiết kế luồng xử lý tệp dựa trên sự kiện Blob

Trong một hệ thống kinh doanh trên Azure, tệp thường được tải lên liên tục: hóa đơn PDF, ảnh sản phẩm, báo cáo CSV, chứng từ kế toán hay bản sao lưu. Nếu ứng dụng phải định kỳ quét toàn bộ thư mục để tìm tệp mới, việc xử lý dễ bị trễ, tạo nhiều lượt kiểm tra không cần thiết và khó mở rộng khi lượng tệp tăng đột biến. **Kiến trúc dựa trên sự kiện (event-driven architecture)** giúp khởi động luồng xử lý khi Azure Blob Storage phát sinh sự kiện liên quan tới đối tượng dữ liệu.

Ví dụ, khi một người dùng tải hóa đơn lên container **incoming**, Azure Event Grid có thể nhận sự kiện **Microsoft.Storage.BlobCreated** và chuyển thông tin tới Azure Functions hoặc hàng đợi. Worker kiểm tra tệp, trích xuất dữ liệu, lưu kết quả vào **processed** và ghi trạng thái công việc. Ứng dụng tải tệp lên không cần chờ toàn bộ quy trình hoàn tất.

Bài học thuộc chương **Lưu trữ đối tượng với Blob Storage** trong lộ trình Microsoft Azure: tổ chức tài nguyên bằng subscription/resource group, thiết kế mạng ảo và Microsoft Entra ID, triển khai dịch vụ tính toán, lưu trữ, dữ liệu, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Blob Storage**, **Blob event**, **Event Grid**, **Azure Functions** và **queue** trong một pipeline.
2. Thiết kế luồng từ lúc upload tệp đến lúc xử lý, lưu kết quả và thông báo hoàn tất.
3. Lựa chọn giữa xử lý trực tiếp từ Event Grid và kiến trúc Event Grid → Queue → Worker.
4. Hiểu sự kiện có thể trùng lặp, đến không đúng thứ tự, được gửi lại hoặc đến khi blob đã thay đổi.
5. Thiết kế **idempotency**, retry, dead-letter, chống quá tải và trạng thái công việc đáng tin cậy.
6. Thiết lập bộ lọc sự kiện, quyền truy cập, private network, giám sát và các điều kiện nghiệm thu.
7. Đọc ví dụ Azure Functions bằng Python và kiểm tra luồng thực tế trong Azure portal/Azure CLI.

## 1. Vì sao dùng sự kiện thay cho quét định kỳ?

Giả sử một ứng dụng nhận 20.000 tệp ảnh mỗi ngày. Cách quét định kỳ có thể phải liệt kê rất nhiều blob, so sánh thời gian cập nhật rồi đoán xem tệp nào chưa xử lý. Một ứng dụng khác lại quét cùng container có thể tạo thêm tải và khiến dữ liệu bị xử lý nhiều lần.

Với mô hình dựa trên sự kiện:

1. Client upload blob tới Azure Storage.
2. Storage phát sinh sự kiện về hoạt động đối tượng theo khả năng hỗ trợ.
3. Event Grid lọc và chuyển sự kiện tới đích đã cấu hình.
4. Consumer bắt đầu hoặc xếp lịch công việc.
5. Worker đọc blob, kiểm tra an toàn, xử lý rồi ghi kết quả/trạng thái.

| Tiêu chí | Quét định kỳ (polling) | Kích hoạt bằng sự kiện |
|---|---|---|
| Phát hiện tệp mới | Phụ thuộc chu kỳ quét và logic đối chiếu | Dựa trên thông báo sự kiện khi hoạt động được ghi nhận |
| Tài nguyên quét | Có thể liệt kê lặp lại nhiều đối tượng | Xử lý những sự kiện được nhận theo bộ lọc |
| Độ trễ | Phụ thuộc lịch chạy | Thường giảm độ trễ phát hiện, nhưng không phải thời gian thực tuyệt đối |
| Khả năng chịu mất/trùng | Phải tự thiết kế trạng thái và đối chiếu | Vẫn phải thiết kế retry, idempotency và đối chiếu |
| Vận hành | Cần quản lý checkpoint của lần quét | Cần theo dõi delivery, queue, consumer và lỗi xử lý |

**Event-driven không đồng nghĩa “mỗi blob luôn được xử lý đúng một lần”.** Sự kiện có thể bị gửi lại; hệ thống phải đảm bảo tính đúng đắn ở tầng ứng dụng.

## 2. Các thành phần của pipeline

### Azure Blob Storage

Blob Storage giữ nội dung tệp trong **Storage Account**, chia theo **container** và tên blob. Trong ví dụ, nhóm sử dụng:

- **incoming**: tệp mới từ người dùng; xem như dữ liệu chưa được kiểm tra.
- **processed**: tệp đầu ra hoặc kết quả đã xử lý thành công.
- **quarantine**: tệp có rủi ro hoặc không đạt kiểm tra an toàn.
- **failed**: kết quả lỗi được ghi nhận để điều tra, nếu cần lưu bản sao hoặc báo cáo lỗi.

Tách container giúp thiết lập quyền, chính sách vòng đời và bộ lọc sự kiện rõ ràng. Việc tách container **không tự động tách quyền** nếu ứng dụng vẫn dùng account key có quyền quá rộng.

### Azure Event Grid

**Azure Event Grid** là dịch vụ định tuyến sự kiện. Một **Event Grid system topic** đại diện cho nguồn sự kiện của dịch vụ Azure, chẳng hạn Storage Account; **event subscription** xác định loại sự kiện, bộ lọc và điểm nhận.

Điểm đến có thể là Azure Function, webhook, một queue hoặc dịch vụ xử lý tương thích, tùy loại endpoint và tính năng được hỗ trợ. Event Grid chuyển **metadata của hoạt động**, không mang toàn bộ nội dung tệp trong event.

### Azure Functions

**Azure Functions** chạy mã khi có trigger, chẳng hạn Event Grid trigger hoặc trigger từ hàng đợi. Một function có thể làm nhiệm vụ rất ngắn: xác thực sự kiện và đẩy thông tin công việc vào queue. Một worker function khác thực hiện xử lý tệp nặng hơn, có retry và quy mô độc lập.

### Hàng đợi và dịch vụ xử lý

**Azure Storage Queue** hoặc **Azure Service Bus Queue** giúp tách tốc độ upload tệp khỏi tốc độ xử lý. Queue lưu công việc đang chờ, cho phép nhiều worker tiêu thụ và giúp điều tiết tải. Service Bus có các tính năng nâng cao như dead-letter queue và cơ chế xử lý thông điệp phù hợp workflow phức tạp. Storage Queue đơn giản hơn và có cơ chế thông điệp poison kết hợp với Azure Functions queue trigger.

Một pipeline có thể dùng queue **làm đích trực tiếp của Event Grid** khi kiểu endpoint/ủy quyền đáp ứng yêu cầu, hoặc để một Function tiếp nhận Event Grid rồi enqueue công việc.

### Nơi lưu trạng thái

Một **job ledger** bền vững, chẳng hạn Azure Table Storage, Cosmos DB hoặc cơ sở dữ liệu đang dùng, ghi nhận:

~~~text
jobKey | blobName | blobETag | state | attempts | startedAt | completedAt | result
~~~

Trạng thái có thể là **RECEIVED**, **PROCESSING**, **SUCCEEDED**, **FAILED**, **QUARANTINED**. Đây là dữ liệu do ứng dụng thiết kế, **không phải** một thuộc tính trạng thái mặc định của BlobCreated event.

## 3. Chọn kiến trúc theo mức phức tạp

### Phương án A: xử lý trực tiếp qua Event Grid trigger

~~~text
Upload blob vào incoming
           |
           v
     BlobCreated
           |
           v
       Event Grid
           |
           v
 Azure Function (Event Grid trigger)
           |
           v
 Đọc blob, kiểm tra, xử lý
           |
           v
     Ghi kết quả
~~~

Phù hợp khi xử lý ngắn, tải ổn định, thao tác có thể thực hiện an toàn trong giới hạn của Function và retry. Điểm yếu là consumer xử lý lâu, lỗi liên tục hoặc đột biến upload có thể làm việc điều tiết tải và phục hồi khó hơn. Đặc biệt, không nên bắt Event Grid chờ một tác vụ xử lý nhiều phút nếu có thể tách công việc vào queue.

### Phương án B: Event Grid → Queue → Worker

~~~text
Client upload
     |
     v
Blob Storage / incoming
     |
     v
Event Grid: BlobCreated
  | lọc container + loại event
  v
Ingest Function hoặc đích queue hỗ trợ
     |
     v
Storage Queue / Service Bus Queue
     |
     +--------> Worker #1
     +--------> Worker #2
     +--------> Worker #N
                    |
                    v
          Kiểm tra & xử lý tệp
                    |
                    v
       processed / quarantine / failed
                    |
                    v
       Job ledger + metrics + thông báo
~~~

**Đây là phương án tham chiếu của bài học** vì tách rõ các trách nhiệm:

- Event Grid phát hiện và phân phối metadata.
- Ingest layer tiếp nhận, kiểm tra tối thiểu và đưa công việc vào queue.
- Queue đệm đột biến, hỗ trợ retry và điều chỉnh số worker.
- Worker xử lý nội dung, quyết định kết quả và cập nhật ledger.
- Hệ thống vận hành theo dõi backlog, lỗi, chất lượng đầu ra và chi phí.

### Khi nào cần Durable Functions hoặc workflow?

Nếu một tệp phải đi qua nhiều bước phụ thuộc nhau như quét mã độc → OCR → kiểm duyệt thủ công → lưu database → gửi thông báo, hãy cân nhắc **Durable Functions**, Logic Apps hoặc workflow trên Service Bus. Chúng cung cấp cách tổ chức trạng thái và phối hợp từng bước, nhưng không loại bỏ yêu cầu idempotency hay kiểm soát lỗi của những dịch vụ bên ngoài.

## 4. Hiểu sự kiện Azure Blob Storage

Hai event type thường gặp:

| Event type | Ý nghĩa | Cách dùng |
|---|---|---|
| **Microsoft.Storage.BlobCreated** | Blob được tạo mới hoặc có hoạt động ghi/commit thuộc trường hợp phát sinh sự kiện | Kích hoạt luồng tiếp nhận tệp |
| **Microsoft.Storage.BlobDeleted** | Blob bị xóa theo hoạt động được hỗ trợ | Đồng bộ chỉ mục, đánh dấu dữ liệu bị xóa hoặc dọn tài nguyên liên quan |

Không phải mọi lần hệ thống chỉnh metadata, thay đổi tag hoặc thao tác backend đều tạo một BlobCreated event. Nếu cần loại sự kiện khác, hãy kiểm tra tài liệu sự kiện và nguồn tài khoản cụ thể.

### Một bản ghi Event Grid schema minh họa

~~~json
{
  "id": "example-event-123",
  "eventType": "Microsoft.Storage.BlobCreated",
  "subject": "/blobServices/default/containers/incoming/blobs/invoice-001.pdf",
  "eventTime": "2026-11-20T03:00:00Z",
  "topic": "/subscriptions/<SUB_ID>/resourceGroups/<RG>/providers/Microsoft.Storage/storageAccounts/stfilesdemo",
  "data": {
    "api": "PutBlob",
    "url": "https://stfilesdemo.blob.core.windows.net/incoming/invoice-001.pdf",
    "eTag": "0x8EXAMPLE0001",
    "contentLength": 32768,
    "contentType": "application/pdf",
    "sequencer": "00000000000000000001"
  },
  "dataVersion": "",
  "metadataVersion": "1"
}
~~~

Đây là **mẫu minh họa rút gọn**, không phải kết quả lấy từ một Storage Account thật. Các trường chính:

- **id**: định danh của bản ghi sự kiện; hữu ích để truy vết và phát hiện delivery trùng.
- **eventType**: loại hoạt động phát sinh sự kiện.
- **subject**: thường chứa đường dẫn tới container và blob, hữu ích để lọc.
- **eventTime**: thời điểm sự kiện được ghi nhận; không phải cam kết thứ tự nhận.
- **data.url**: URL của blob ở nguồn; worker vẫn phải xác thực địa chỉ và quyền.
- **data.eTag**: dấu phiên bản nội dung/trạng thái blob ở thời điểm sự kiện; có ích cho việc chống xử lý nhầm lần ghi khác.
- **data.contentLength / contentType**: metadata hữu ích để kiểm tra nhanh, nhưng **không được tin tuyệt đối** như kết quả kiểm tra nội dung thực.
- **data.sequencer**: có thể hỗ trợ so sánh tương đối những thay đổi trên **cùng một blob**; không dùng làm thứ tự toàn cục cho mọi blob.

Event Grid cũng hỗ trợ **CloudEvents schema**, với tên trường khác, chẳng hạn **type**, **source**, **subject** và **data**. Phải chọn một schema, xem payload thực tế tại đích và viết parser tương ứng; không mặc định mọi event handler đều nhận JSON giống ví dụ.

### Khi nào blob đã hoàn tất upload?

Với Blob Storage thông thường, sự kiện BlobCreated thường liên quan tới thao tác tạo/commit blob, như **Put Blob** hoặc **Put Block List**. Tuy nhiên, quy trình upload qua **Data Lake Storage Gen2 (hierarchical namespace)**, **SFTP** hoặc công cụ đồng bộ khác có thể có hành vi sự kiện và giai đoạn ghi khác.

Ví dụ, một workflow ADLS Gen2 có thể chỉ nên xử lý khi nhận sự kiện có **data.api = FlushWithClose**; các tình huống SFTP cũng cần phân biệt hoạt động tạo với thao tác commit để tránh đọc tệp chưa hoàn chỉnh. Điều kiện chính xác phụ thuộc giao thức upload và tài liệu sự kiện của Storage.

**Quy tắc thiết kế:** xác định rõ “tệp đã sẵn sàng để xử lý” theo cơ chế upload đang dùng; đừng suy ra mọi BlobCreated luôn đại diện cho cùng một điểm kết thúc upload trên tất cả giao thức.

## 5. Thiết kế bộ lọc event subscription

Nếu muốn chỉ xử lý tệp được tải lên container **incoming**, nên lọc càng sớm càng tốt:

1. Chỉ chọn **Microsoft.Storage.BlobCreated**.
2. Dùng subject filter có tiền tố phù hợp, ví dụ:

~~~text
/blobServices/default/containers/incoming/blobs/
~~~

3. Tùy nhu cầu, có thể lọc hậu tố **.pdf**, **.csv** hoặc **.jpg** bằng subject suffix và/hoặc advanced filter theo các thuộc tính được hỗ trợ.
4. Nếu upload theo ADLS Gen2 hoặc SFTP, cân nhắc lọc **data.api** để chỉ nhận những thao tác đã hoàn tất theo kịch bản.
5. Đặt output ở container **processed** hoặc Storage Account khác để tránh chính kết quả mới tạo lại kích hoạt một vòng lặp xử lý.

Filter là công cụ **giảm sự kiện không liên quan**, không phải lớp xác thực nội dung. Client có thể đặt tên tệp **invoice.pdf** nhưng gửi nội dung không phải PDF. Worker phải kiểm tra thực tế.

### Ví dụ tránh vòng lặp

Nếu Event Grid subscription không có subject filter và worker ghi file mới vào container **processed** thuộc cùng Storage Account, blob kết quả lại có thể tạo BlobCreated. Consumer nhận sự kiện đó và tạo thêm kết quả khác, dẫn tới **vòng lặp sự kiện và chi phí**.

Thiết kế đúng: chỉ nhận sự kiện từ **incoming**, hạn chế quyền ghi đầu ra vào **processed**, đồng thời kiểm tra tên container ở mã nhận sự kiện. Có thể áp thêm metadata trạng thái hoặc tách Storage Account theo nhu cầu, nhưng không phụ thuộc duy nhất vào nhãn metadata để ngăn vòng lặp.

## 6. Delivery semantics: at-least-once và không bảo đảm thứ tự

Đây là phần quan trọng nhất của luồng dựa trên sự kiện.

### Event Grid có thể gửi lại

Một event subscription có cơ chế retry khi giao sự kiện thất bại theo chính sách được cấu hình. Sự kiện có thể đến **hơn một lần**, dù blob không thay đổi. Thời gian lưu/retry và giới hạn số lần thử tùy chính sách; khi vượt điều kiện, Event Grid có thể bỏ sự kiện hoặc đưa vào **dead-letter destination** nếu đã cấu hình và đáp ứng yêu cầu.

### Không bảo đảm thứ tự

Nếu file **orders.csv** được ghi phiên bản A rồi B trong thời gian ngắn, handler có thể xử lý sự kiện B trước A. Tệ hơn, lúc worker nhận sự kiện A, blob ở đường dẫn đó đã chứa dữ liệu B.

Đừng dựa vào thời điểm nhận event hoặc thứ tự trong queue để khẳng định nội dung hiện tại là nội dung sự kiện ban đầu. Cần một **processing contract** rõ ràng.

### Chọn hợp đồng xử lý tệp

| Hợp đồng | Cách thực hiện | Phù hợp khi |
|---|---|---|
| **Chỉ xử lý bản mới nhất** | Khi worker chạy, lấy thuộc tính blob hiện tại và bỏ qua event nếu ETag không còn khớp | Tệp được cập nhật thường xuyên, không cần giữ mọi phiên bản |
| **Xử lý từng phiên bản** | Bật blob versioning khi được hỗ trợ, lưu versionId và đọc đúng phiên bản | Cần audit hoặc xử lý mọi lần ghi |
| **Tên blob bất biến** | Mỗi upload dùng tên duy nhất; không ghi đè đường dẫn trong **incoming** | Upload theo công việc/batch, dễ đơn giản hóa xử lý |

Nếu cần bảo đảm không bỏ sót dữ liệu khi có sự cố vận hành, hãy thiết kế thêm bước **reconciliation**: định kỳ đối chiếu blob trong **incoming** với ledger và tái tạo job còn thiếu. Event-driven vẫn có thể cần một job đối chiếu thưa, khác với việc quét toàn bộ để xử lý ở mỗi chu kỳ.

## 7. Idempotency: không tạo kết quả trùng

**Idempotent processing** nghĩa là dù cùng một công việc được gọi nhiều lần, hệ thống vẫn có kết quả nghiệp vụ tương đương với một lần xử lý thành công.

Chỉ dựa vào **event.id** chưa đủ trong mọi kịch bản: cùng một blob có thể phát sinh những sự kiện hợp lệ khác nhau. Một **job key** khả dụng là:

~~~text
jobKey = hash(storageAccount + container + blobName + eTag)
~~~

Hoặc sử dụng **versionId** khi bật versioning và hệ thống cần xử lý chính xác từng phiên bản. Chỉ hash URL nếu đã chuẩn hóa tên và không chứa SAS token hay secret.

### Job ledger phải hỗ trợ cập nhật có điều kiện

Một thuật toán hợp lý:

~~~text
receive event/queue message
    |
    v
validate account/container/blob and jobKey
    |
    v
try INSERT jobKey with state=PROCESSING (unique key)
    |
    +-- already SUCCEEDED --> ACK duplicate, no new output
    |
    +-- active PROCESSING --> defer/retry according to lease policy
    |
    v
read correct blob version or compare current ETag
    |
    v
validate content + scan according to security policy
    |
    v
write output with deterministic name / conditional create
    |
    v
update ledger to SUCCEEDED with result reference
    |
    v
ACK queue message
~~~

**“Kiểm tra đã tồn tại rồi ghi” không tự bảo đảm atomicity.** Hai worker có thể cùng thấy chưa có bản ghi. Hãy dùng **insert-only/unique key**, ETag-based conditional write, transaction hoặc cơ chế khóa/lease phù hợp với database. Nếu worker chết khi đang PROCESSING, trạng thái cần có **lease timeout** hoặc quy tắc chiếm lại công việc để tránh kẹt vĩnh viễn.

Để tạo blob đầu ra, dùng tên xác định từ job key và upload ở chế độ **không overwrite** hoặc điều kiện thích hợp. Nếu output đã tồn tại, worker phải xác minh đó là kết quả hợp lệ của job trước khi đánh dấu hoàn tất.

### Nguyên tắc “ack sau khi bền vững”

Nếu Event Grid gọi HTTP Function để đưa thông tin vào queue, Function chỉ báo thành công khi đã **ghi thông điệp vào queue bền vững**. Nếu queue gửi lỗi, hãy để delivery retry theo cơ chế hỗ trợ; không trả 2xx rồi làm rơi event.

Tương tự, worker chỉ hoàn tất xử lý thông điệp sau khi dữ liệu đầu ra và trạng thái cần thiết đã lưu thành công. Cơ chế ack cụ thể khác nhau giữa Storage Queue trigger, Service Bus trigger và endpoint tùy chỉnh, nhưng nguyên tắc **không xác nhận sớm** luôn quan trọng.

## 8. Retry, poison message và dead-letter

Lỗi có hai nhóm:

- **Tạm thời (transient):** mạng đứt, Storage trả throttling, service OCR chưa sẵn sàng, worker hết tài nguyên trong chốc lát. Có thể thử lại với backoff.
- **Vĩnh viễn hoặc do dữ liệu (permanent):** tệp sai định dạng, vượt kích thước cho phép, nội dung độc hại, không có quyền truy cập theo chính sách. Thử lại vô hạn không giải quyết được.

### Hai tầng lỗi phải được theo dõi riêng

| Tầng | Ví dụ lỗi | Cách phục hồi |
|---|---|---|
| **Event Grid delivery** | Không gửi được tới Function/queue endpoint | Retry theo event subscription, dùng dead-letter destination nếu cấu hình |
| **Queue → Worker** | Worker crash hoặc xử lý tệp thất bại | Queue redelivery, giới hạn delivery, poison queue/DLQ và quy trình replay |

**Dead-letter của Event Grid không phải DLQ của Service Bus.** Chúng phục vụ những giai đoạn khác nhau. Với Azure Storage Queue, Azure Functions queue trigger có thể đưa thông điệp vào queue dạng **-poison** sau khi vượt ngưỡng xử lý thất bại theo host settings; Service Bus có **dead-letter subqueue** theo cơ chế riêng.

Khi replay, cần giữ job key, kiểm tra trạng thái hiện tại và phân biệt lỗi cũ đã được sửa với dữ liệu còn không hợp lệ. Không replay tất cả thông điệp poison một cách tự động và vô hạn.

### Chống quá tải (backpressure)

Giả sử có 50.000 ảnh được upload trong 10 phút nhưng dịch vụ xử lý ảnh chỉ đủ năng lực 500 ảnh/phút. Nếu gọi trực tiếp đồng bộ cho từng event, số function đang chạy và tài nguyên phụ thuộc có thể bị quá tải.

Với queue, cho phép backlog tăng có kiểm soát rồi mở rộng worker theo chính sách:

- Đo số thông điệp chờ và **tuổi của thông điệp cũ nhất**.
- Giới hạn số worker đồng thời và số luồng đọc blob theo dung lượng CPU, RAM, băng thông.
- Thiết lập rate limit tới OCR, cơ sở dữ liệu hoặc API bên ngoài.
- Dùng exponential backoff và phân biệt 429/5xx với lỗi dữ liệu.
- Đặt giới hạn dung lượng tệp, timeout và khả năng xử lý file quá lớn.
- Có cơ chế cảnh báo khi backlog hoặc thời gian chờ vượt ngưỡng nghiệp vụ.

Queue giúp đệm tải, **không tự tăng vô hạn năng lực xử lý**. Dung lượng storage, throughput của tài khoản, kích thước queue message và quota của dịch vụ cũng cần được thiết kế.

## 9. Thiết kế bảo mật cho pipeline tệp

Upload là điểm tiếp nhận **dữ liệu không đáng tin cậy**. Tệp có thể chứa nội dung độc hại, dữ liệu cá nhân, công thức CSV nguy hiểm hoặc định dạng giả mạo.

### Phân quyền tối thiểu bằng Microsoft Entra ID

Phân chia danh tính ứng dụng:

| Thành phần | Quyền dự kiến | Phạm vi |
|---|---|---|
| Uploader | Chỉ được tạo/ghi trong container incoming theo kịch bản | Tối thiểu cho nghiệp vụ upload |
| Ingest Function | Gửi message vào queue | Vai trò gửi thông điệp ở queue đích |
| Worker | Đọc incoming, ghi processed/quarantine | Role data plane riêng trên container tương ứng |
| Trình xem kết quả | Chỉ đọc processed | Role đọc dữ liệu ở phạm vi cần thiết |
| Nhóm vận hành | Xem metric/log, replay có phê duyệt | RBAC cho các tài nguyên liên quan |

Ưu tiên **managed identity** và SDK dùng Microsoft Entra ID cho Function. Đối với Blob có thể dùng các vai trò như **Storage Blob Data Reader**, **Storage Blob Data Contributor**; với Storage Queue có các vai trò dữ liệu tương ứng cho sender/processor. Nếu sử dụng Service Bus, cấp quyền gửi/nhận phù hợp ở scope queue và kiểm tra cơ chế identity của đích Event Grid.

Không đặt account key hoặc SAS dài hạn trong mã nguồn. Nếu phải cấp SAS cho client upload trực tiếp, giới hạn quyền, container/tệp, thời gian hiệu lực và HTTPS; quản lý thu hồi theo thiết kế.

### Network security

Storage Account có thể dùng **private endpoint** và tắt public network access cho data plane sau khi các client hợp lệ có đường kết nối riêng. Worker dùng Blob private endpoint cần DNS phân giải hostname Storage về private IP và có route mạng hợp lệ.

**Kết nối tới Blob qua private endpoint khác với đường Event Grid giao sự kiện tới Function/queue.** Không suy ra rằng vì Storage đã tắt public network access nên mọi Event Grid destination sẽ hoạt động qua mạng riêng. Cần xác minh hỗ trợ private networking, public endpoint, firewall exception, managed identity và mô hình delivery của **từng đích** trước khi khóa mạng.

### Kiểm tra nội dung

Worker nên:

- Xác định loại tệp thực tế bằng **magic bytes/decoder**, không chỉ đuôi file hoặc contentType do client khai báo.
- Giới hạn dung lượng và số lượng trang/ảnh, chống file nén mở rộng quá mức.
- Dùng quy trình quét malware theo yêu cầu tổ chức; có thể đánh giá dịch vụ bảo vệ Storage phù hợp.
- Xử lý tệp trong môi trường có quyền tối thiểu, không chạy macro hoặc mã từ tệp upload.
- Không ghi dữ liệu nhạy cảm, nội dung tệp hoặc token vào log.
- Chỉ chuyển tệp sang vùng có thể tải xuống sau khi đạt kiểm tra an toàn và chính sách.

Một BlobCreated event **không phải bằng chứng tệp đã an toàn**. Với workload nghiêm ngặt, trạng thái phải đi qua các bước như RECEIVED → SCANNED → PROCESSED → PUBLISHED, và không công bố tệp trước khi hoàn tất kiểm tra.

## 10. Ví dụ Python Azure Functions: nhận event và xếp hàng

Ví dụ dưới đây dùng **Python programming model v2** của Azure Functions: Event Grid trigger nhận BlobCreated và gửi một thông điệp nhỏ vào **Azure Storage Queue**. Đây là phần **ingest**, không đọc toàn bộ nội dung blob ngay trên Event Grid trigger.

### Điều kiện chuẩn bị

- Một Storage Account nguồn và container **incoming**.
- Event Grid subscription gửi BlobCreated tới **Azure Function** đúng endpoint được hỗ trợ.
- Một Azure Storage Queue tên **blob-work**.
- Function có **managed identity** và quyền data plane phù hợp để gửi message tới queue.
- Cấu hình ứng dụng chứa **EXPECTED_BLOB_HOST**, **QUEUE_ACCOUNT_URL**, **QUEUE_NAME** (không chứa key).
- Gói Python tương ứng: **azure-functions**, **azure-identity**, **azure-storage-queue**.
- Functions runtime/hosting và cấu hình networking cho phép function gọi queue.

Đối với Function được triển khai lên Azure, **DefaultAzureCredential** có thể sử dụng managed identity. Khi chạy local, nó có thể chọn thông tin đăng nhập developer, nên phải kiểm soát subscription/tenant và quyền dữ liệu trước khi thử.

### Ví dụ function_app.py

~~~python
import json
import logging
import os
from urllib.parse import unquote, urlsplit

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.storage.queue import QueueClient

app = func.FunctionApp()


@app.event_grid_trigger(arg_name="event")
def receive_blob_created(event: func.EventGridEvent):
    # Bỏ qua sự kiện khác BlobCreated.
    if event.event_type != "Microsoft.Storage.BlobCreated":
        return

    data = event.get_json()
    blob_url = data.get("url", "")
    parsed = urlsplit(blob_url)

    # Không tin URL từ payload một cách mù quáng.
    expected_host = os.environ["EXPECTED_BLOB_HOST"].lower()
    if parsed.scheme != "https" or parsed.hostname != expected_host:
        logging.warning("Ignored event: unexpected blob endpoint")
        return

    path = unquote(parsed.path.lstrip("/"))
    container, separator, blob_name = path.partition("/")

    # Chỉ xử lý container incoming, tránh tạo vòng lặp sự kiện.
    if not separator or container != "incoming" or not blob_name:
        return

    allowed_suffixes = (".pdf", ".png", ".jpg", ".csv")
    if not blob_name.lower().endswith(allowed_suffixes):
        return

    job = {
        "eventId": event.id,
        "accountHost": expected_host,
        "container": container,
        "blobName": blob_name,
        "eTag": data.get("eTag"),
        "eventType": event.event_type,
    }

    queue = QueueClient(
        account_url=os.environ["QUEUE_ACCOUNT_URL"],
        queue_name=os.environ.get("QUEUE_NAME", "blob-work"),
        credential=DefaultAzureCredential(),
    )

    # Nếu lệnh gửi thất bại, không nuốt lỗi: trigger cần được retry.
    queue.send_message(json.dumps(job, ensure_ascii=False))
    logging.info("Enqueued blob work: eventId=%s", event.id)
~~~

**Giới hạn của ví dụ:** đây là khung ingest minh họa, không phải toàn bộ giải pháp production. Đuôi file chỉ dùng để lọc nhanh; worker vẫn phải kiểm tra nội dung thật. Cần triển khai log/telemetry có cấu trúc, xác thực đầy đủ source/topic/subject theo hợp đồng sự kiện, theo dõi quyền và quy tắc delivery của Event Grid.

Với một số tài khoản ADLS Gen2/SFTP, phải bổ sung kiểm tra **data.api** hoặc tiêu chí upload hoàn tất thích hợp trước khi enqueue. Ví dụ hiện giả định phía uploader dùng quy trình tạo BlobCreated khi nội dung đã commit.

### Worker xử lý queue theo hướng idempotent

Worker có thể dùng Azure Functions **Queue trigger** rồi đọc blob bằng Azure Blob SDK và managed identity. Pseudocode dưới đây cố ý tách khâu điều phối/idempotency khỏi việc xử lý nội dung:

~~~text
function processMessage(job):
    validate job fields and expected account/container
    jobKey = stableHash(accountHost, container, blobName, eTag)

    if ledger[jobKey] is SUCCEEDED:
        return success  # duplicate delivery

    atomically reserve jobKey or recover expired lease
    blob = open source blob via managed identity

    if processing_latest_only and blob.currentETag != job.eTag:
        mark job SKIPPED_STALE
        return success

    if processing_each_version:
        open exact blob version from validated versionId

    enforce size / file type / security policy
    if malware_or_rejected:
        record QUARANTINED without exposing file
        return success

    result = transform_or_extract(blob)
    write result with deterministic output name and conditional create
    atomically/fail-safely record SUCCEEDED and result reference
    return success
~~~

Điều phối thật cần giải quyết tình huống **worker ghi output thành công rồi crash trước khi cập nhật ledger**: ở lần chạy lại, worker phải kiểm tra output đã tồn tại và tiếp tục hoàn tất ledger mà không tạo sản phẩm trùng. Tính nhất quán giữa queue, blob output và database không tự có giao dịch phân tán; thiết kế theo kiểu **at-least-once + idempotent side effects**.

### Một số cấu hình cần chú ý

| Thành phần | Điều phải xác nhận |
|---|---|
| Event Grid trigger | Subscription đích đúng Function; endpoint validation/xác thực được platform xử lý theo cấu hình |
| Queue sender | Managed identity có quyền gửi message tới queue |
| Queue trigger | Function host có quyền truy cập queue và cấu hình connection theo cơ chế sử dụng |
| Blob reader | Managed identity có quyền đọc container và DNS/route đúng |
| Job ledger | Unique key/conditional write, lease timeout, trạng thái phục hồi |
| Blob output | Chế độ ghi tránh overwrite ngoài ý muốn, tên kết quả xác định |
| Monitoring | Correlation giữa eventId, queue message ID, jobKey và blob ETag |

## 11. Thiết lập pipeline bằng Azure portal

Vì tạo Event Grid subscription, queue và Function có thể phát sinh chi phí, chỉ thực hiện trong subscription/resource group được phép dùng cho bài lab. Không tự thao tác trên Storage production có dữ liệu khách hàng.

### Bước 1: tạo Storage và các container

Chuẩn bị Storage Account và những container **incoming**, **processed**, **quarantine**. Cấu hình replication, mã hóa, public network access, private endpoint và RBAC theo yêu cầu. Xác nhận người upload chỉ có quyền tối thiểu cần thiết.

### Bước 2: chọn mô hình xử lý

Với ví dụ bài học, tạo **Storage Queue blob-work** và một Function App có Event Grid trigger. Tạo thêm một Function hoặc worker tiêu thụ queue, ghi kết quả ra **processed**. Tài nguyên Function có thể cần các dịch vụ hosting/storage phục vụ runtime tùy plan.

Nếu muốn Event Grid gửi thẳng tới Service Bus queue, kiểm tra hỗ trợ delivery/managed identity, RBAC và hạn chế network trước khi chọn cấu hình đó. Không lẫn các thông số của Storage Queue với Service Bus.

### Bước 3: tạo event subscription

Từ Storage Account nguồn, mở **Events** và tạo Event Grid event subscription. Tùy portal, system topic có thể được tạo/quản lý cùng bước này.

Ví dụ lựa chọn:

~~~text
Name: evt-incoming-created
Event types: Blob Created
Subject begins with:
  /blobServices/default/containers/incoming/blobs/
Endpoint type: Azure Function
Endpoint: receive_blob_created
Event delivery schema: Event Grid schema (theo ví dụ mã)
~~~

Kiểm tra prefix thật của container/đường dẫn và tránh match rộng hơn cần thiết. Nếu xử lý ADLS Gen2, bổ sung điều kiện hoàn tất upload phù hợp. Chọn retry/dead-letter policy theo nhu cầu vận hành và quyền truy cập nơi lưu dead-letter.

### Bước 4: cấu hình quyền và biến môi trường

Cấp managed identity của Function quyền **gửi thông điệp** vào queue. Cấp worker quyền **đọc incoming** và **ghi processed/quarantine**, không dùng chung account key cho tất cả thành phần. Đặt EXPECTED_BLOB_HOST và QUEUE_ACCOUNT_URL theo endpoint thật.

Chỉ khi đã kiểm tra route/DNS tới Blob và queue mới khóa public network access. Đường delivery Event Grid đến Function cần được kiểm tra riêng theo network feature/hosting plan đang sử dụng.

### Bước 5: upload tệp thử nghiệm

Tải một file test lên container **incoming**; ví dụ **invoice-001.pdf**. Quan sát:

1. Blob có tồn tại và dung lượng hợp lý.
2. Event Grid có ghi nhận delivery thành công đến Function.
3. Ingest Function đã gửi message vào **blob-work**.
4. Worker đã nhận message, lưu job ledger và tạo output.
5. Kết quả nằm trong **processed** và không kích hoạt vòng lặp mới.
6. Telemetry có eventId/jobKey để tra cứu toàn bộ hành trình.

### Bước 6: kiểm thử lỗi và retry

Trong môi trường thử nghiệm, mô phỏng lỗi xử lý có kiểm soát như tệp sai định dạng hoặc service backend không sẵn sàng. Xác nhận message được retry theo chính sách, số lần thử có giới hạn và đi vào poison/DLQ/quarantine đúng kỳ vọng.

Sau khi sửa lỗi, chạy lại bằng quy trình replay có kiểm soát và xác nhận **không tạo output trùng**. Không cố tình làm gián đoạn tài nguyên production để thử retry.

### Bước 7: dọn dẹp và theo dõi chi phí

Gỡ các event subscription, Function/queue và tài nguyên lab không còn dùng sau khi đã xác nhận đúng owner và phạm vi. **Xóa cả resource group chỉ khi chắc chắn không chứa tài nguyên cần giữ.** Kiểm tra Azure Cost Management và retention của log, dead-letter blob, output test.

## 12. Kiểm tra read-only bằng Azure CLI

Các lệnh dưới đây phục vụ kiểm tra, không tạo hoặc xóa tài nguyên. Những tên account/container/resource group là ví dụ:

~~~bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

az storage account show \
  --resource-group "rg-file-pipeline" \
  --name "stfilesdemo" \
  --query "{name:name,location:location,kind:kind,publicNetworkAccess:publicNetworkAccess}" \
  --output json
~~~

Liệt kê event subscription theo resource ID của Storage Account:

~~~bash
az eventgrid event-subscription list \
  --source-resource-id "<STORAGE_ACCOUNT_RESOURCE_ID>" \
  --output table
~~~

Với tài khoản có **Microsoft Entra ID** và quyền Blob data-plane phù hợp, có thể xem dữ liệu trong container:

~~~bash
az storage blob list \
  --account-name "stfilesdemo" \
  --container-name "incoming" \
  --auth-mode login \
  --output table
~~~

Khi Storage chỉ cho phép private endpoint, môi trường chạy CLI cũng phải có DNS/route đến endpoint phù hợp; quyền Entra ID không thay thế được đường mạng.

Để xem thiết lập queue hoặc trạng thái consumer, dùng phần tương ứng trong Azure portal hoặc công cụ Azure theo quyền được cấp. Không xóa message, chạy replay hay sửa event subscription chỉ vì muốn kiểm tra.

## 13. Giám sát và vận hành

Một pipeline chạy được ở lần thử đầu chưa chắc đủ an toàn cho production. Cần theo dõi xuyên suốt đường đi.

### Các chỉ số quan trọng

| Chỉ số | Ý nghĩa |
|---|---|
| Event Grid publish/delivery failures | Phát hiện sự kiện không được chuyển tới đích |
| Queue length / oldest message age | Đo backlog và khả năng bị trễ khi upload tăng |
| Worker success/failure/retry counts | Hiểu độ ổn định của xử lý |
| Processing latency | Thời gian từ upload tới kết quả có thể dùng |
| Blob bytes processed | Theo dõi khối lượng và chi phí xử lý |
| DLQ/poison message count | Phát hiện lỗi chưa được xử lý |
| Duplicate/stale event count | Đánh giá idempotency và tệp bị ghi đè |
| Quarantined/rejected files | Theo dõi chất lượng dữ liệu và vấn đề an ninh |
| Storage 403/429/5xx | Phân biệt lỗi quyền, throttling và lỗi dịch vụ |

### Correlation ID

Mỗi log nên có dữ liệu truy vết an toàn:

~~~json
{
  "eventId": "example-event-123",
  "jobKey": "hash-of-account-container-name-etag",
  "sourceContainer": "incoming",
  "blobName": "invoice-001.pdf",
  "state": "SUCCEEDED",
  "durationMs": 820,
  "resultBlob": "processed/invoice-001.json"
}
~~~

Không ghi SAS token, account key, nội dung tệp, dữ liệu cá nhân hoặc toàn bộ URL có query bí mật vào log.

### Các điểm cần cảnh báo

- Event Grid delivery failure tăng hoặc dead-letter phát sinh.
- Queue backlog vượt ngưỡng hoặc tuổi job lớn nhất quá SLA.
- Worker liên tục lỗi/được retry và không có job nào hoàn thành.
- Lượng tệp quarantine tăng bất thường.
- Chi phí Function, queue, dữ liệu lưu trữ và log tăng nhanh.
- Private DNS/network thay đổi làm worker không đọc được blob.

Có thể dùng **Azure Monitor**, **Application Insights**, diagnostic settings và dashboard phù hợp để ghép log/metric. Tên và độ chi tiết của từng metric phụ thuộc dịch vụ, plan và cấu hình thu thập thực tế.

## 14. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Upload thành công nhưng không có job | Event subscription sai resource/event type/filter; delivery lỗi | Kiểm tra Events, subject filter, endpoint và delivery metrics |
| Event đến nhưng queue trống | Ingest Function lỗi hoặc thiếu quyền gửi queue | Xem Function logs, managed identity và quyền Queue Data |
| Queue tăng liên tục | Worker không chạy, concurrency thấp hoặc downstream throttling | Xem Function host, scale, queue age, CPU/memory và API bên ngoài |
| Một tệp được xử lý hai lần | Retry hoặc sự kiện trùng; chưa có idempotency | So sánh eventId, blob ETag, jobKey và unique-key ledger |
| Xử lý phiên bản cũ nhưng đọc nội dung mới | Blob đã overwrite trước khi worker đọc | So sánh ETag; bật versioning nếu phải đọc đúng bản cũ |
| BlobCreated đến trước khi tệp sẵn sàng theo nghiệp vụ | Upload có nhiều bước, ADLS Gen2/SFTP commit khác kỳ vọng | Kiểm tra data.api và quy trình hoàn tất upload |
| Worker lỗi 403 khi đọc Blob | Thiếu quyền RBAC, token lỗi hoặc Storage firewall từ chối | Kiểm tra managed identity, data-plane roles, network rules và DNS |
| Worker timeout tới Blob | Private DNS, route, NSG hoặc Private Endpoint chưa đúng | Phân giải tên từ worker, kiểm tra TCP/443 và trạng thái endpoint |
| Job mãi ở PROCESSING | Worker crash, ledger không có lease timeout | Kiểm tra TTL/lease, retry và cơ chế reclaim |
| Event đầu ra lại tạo job mới | Bộ lọc event quá rộng hoặc output cùng container incoming | Kiểm tra subject prefix và logic validate container |
| DLQ/poison tăng | Lỗi dữ liệu hoặc cấu hình chưa được sửa | Phân loại transient/permanent, xử lý có kiểm soát và replay |
| Xử lý thành công nhưng không thấy kết quả | Ghi blob sai account/container hoặc quyền/ledger sai | Kiểm tra output key, request ID, role và giao dịch cập nhật trạng thái |

### Một tình huống cần suy luận

Người dùng tải **report.csv** lên rồi tải lại cùng tên trong vòng vài giây. Event A có ETag A; event B có ETag B. Worker xử lý event B trước, ghi kết quả cho B. Sau đó event A đến. Nếu worker chỉ đọc blob hiện tại theo path, event A có thể xử lý lại **nội dung B** và tạo output trùng.

Khắc phục bằng cách kiểm tra ETag trước khi đọc, quy ước mỗi upload một tên bất biến, hoặc bật versioning và đọc đúng phiên bản. Đồng thời dùng ledger theo job key để chống xử lý lặp và ghi output với tên xác định.

## 15. Tối ưu hiệu năng và chi phí

Chi phí của pipeline không chỉ là dung lượng Blob Storage. Cần ước tính:

- **Blob Storage**: dung lượng, số thao tác, mức lưu trữ, lifecycle/retention, phiên bản/soft delete khi sử dụng.
- **Event Grid**: số thao tác/sự kiện phân phối và retry theo biểu phí hiện hành.
- **Queue/Service Bus**: số message, thao tác, thời gian lưu, tính năng premium nếu dùng.
- **Azure Functions**: plan hosting, thời gian chạy, bộ nhớ/công suất, số execution và dịch vụ đi kèm.
- **AI/OCR/transform**: phí xử lý trên mỗi tài liệu/trang/transaction nếu tích hợp.
- **Networking**: private endpoint, NAT, băng thông/truyền dữ liệu hoặc dịch vụ mạng bổ sung.
- **Observability**: log/metrics, lưu trữ, truy vấn và thời gian retention.

Một thiết kế hiệu quả thường dùng **message nhỏ chứa metadata và tham chiếu blob**, thay vì đặt toàn bộ bytes của tệp vào queue. Hàng đợi không được dùng thay thế Blob Storage để giữ các tệp lớn; mỗi dịch vụ queue có giới hạn message riêng.

Chọn batch size/concurrency để worker không vượt tài nguyên và không gây throttling tới Storage hoặc hệ thống dữ liệu. Sử dụng lifecycle rule để xóa tệp tạm hoặc chuyển tầng lưu trữ khi đã đáp ứng yêu cầu lưu giữ. Đặt tag chủ sở hữu và ngân sách theo resource group/subscription; theo dõi giá hiện hành thay vì ghi cứng một mức phí trong kiến trúc.

## 16. Bài tập tình huống: xử lý hóa đơn PDF

Một công ty thương mại điện tử cần xử lý khoảng 10.000 hóa đơn PDF mỗi ngày. Người dùng upload vào Blob Storage. Hệ thống cần quét tệp, trích xuất thông tin số hóa đơn và số tiền, lưu kết quả JSON, rồi thông báo cho bộ phận kế toán. Có thể có upload lặp cùng tên; một số tệp lớn; dịch vụ OCR đôi khi trả lỗi tạm thời.

Hãy thiết kế:

1. Container **incoming**, **processed**, **quarantine** và cách cấp quyền cho uploader/worker.
2. Event Grid subscription chỉ nhận BlobCreated từ **incoming**.
3. Queue nào dùng để đệm tải, với lý do lựa chọn Storage Queue hoặc Service Bus.
4. Cách xác định một bản PDF đã upload xong theo giao thức upload đang sử dụng.
5. Job key và ledger ngăn xử lý cùng một phiên bản hai lần.
6. Cách phân biệt OCR timeout với file hỏng/độc hại.
7. Phương án retry, poison/DLQ, replay và reconciliation.
8. Các bước xác minh DNS, private endpoint và quyền data plane.
9. Cách ngăn output JSON mới tạo kích hoạt lại pipeline.
10. Metrics, cảnh báo, SLA và chi phí cần báo cáo.

**Gợi ý lời giải:** dùng Event Grid → Function enqueue → Queue → Worker, đặt job key theo **account/container/blob/ETag**, tạo output JSON với tên xác định, kiểm tra dữ liệu thực và trạng thái antivirus, retry có giới hạn cho lỗi OCR tạm thời, đưa lỗi cố định vào quarantine/DLQ và theo dõi **tuổi message cũ nhất**. Nếu nghiệp vụ yêu cầu xử lý mọi lần ghi thì bật versioning, lưu versionId và đọc đúng phiên bản.

## 17. Checklist trước khi đưa vào production

| Nhóm | Việc cần xác nhận |
|---|---|
| Nguồn | Đúng Storage Account, container, subresource và định nghĩa hoàn tất upload |
| Events | Event type/schema/filter đúng; không tạo vòng lặp |
| Delivery | Endpoint đúng, xác thực/ủy quyền và retry/dead-letter được cấu hình |
| Queue | Có giới hạn kích thước message, retry/poison và khả năng chống backlog |
| Tính đúng đắn | Idempotency key, unique-key ledger, ETag/version và output điều kiện |
| Bảo mật | Managed identity/RBAC, không lưu secret, kiểm tra tệp không tin cậy |
| Mạng | DNS, route, private endpoint và đường delivery tới consumer được xác minh |
| Ứng dụng | Lỗi tạm thời/vĩnh viễn được phân loại; timeout/concurrency hợp lý |
| Vận hành | Correlation ID, metrics, alerts, runbook replay và reconciliation |
| Chi phí | Có ước tính Event Grid, queue, compute, storage, network và log |
| Nghiệm thu | Thử upload, duplicate, overwrite, tệp lỗi, retry, recovery và scale |

## 18. Câu hỏi tự kiểm tra

1. Khi nào nên dùng BlobCreated event thay vì quét toàn bộ container theo lịch?
2. Event Grid event có chứa bytes của tệp PDF không? Worker lấy nội dung tệp từ đâu?
3. Vì sao cần lọc subject theo **incoming** và không đặt output trong cùng luồng đầu vào không kiểm soát?
4. Khác biệt giữa Event Grid trigger trực tiếp và Event Grid → Queue → Worker là gì?
5. “At least once delivery” ảnh hưởng thế nào đến thiết kế output và trạng thái job?
6. Vì sao một eventId duy nhất không luôn đủ để mô tả một phiên bản dữ liệu Blob?
7. ETag và Blob versioning giúp xử lý trường hợp ghi đè tệp như thế nào?
8. Sự khác nhau giữa lỗi delivery của Event Grid và lỗi xử lý thông điệp trong queue là gì?
9. Tại sao phải xác thực tệp PDF thực tế dù filename kết thúc bằng **.pdf**?
10. Managed identity có vai trò gì khi worker đọc Blob và gửi message vào queue?
11. Vì sao Private Endpoint cho Storage không tự bảo đảm Event Grid giao event thành công?
12. Những metric nào giúp phát hiện worker bị tụt lại khi tải upload tăng nhanh?
13. Nếu output đã ghi nhưng worker crash trước khi cập nhật ledger, lần chạy lại cần làm gì?
14. Vì sao một hệ thống dựa trên sự kiện vẫn có thể cần reconciliation job định kỳ?

## Tài liệu tham khảo

- Microsoft Learn — *Azure Blob Storage events with Azure Event Grid*: https://learn.microsoft.com/azure/storage/blobs/storage-blob-event-overview
- Microsoft Learn — *Event schemas for Blob Storage events*: https://learn.microsoft.com/azure/event-grid/event-schema-blob-storage
- Microsoft Learn — *Azure Event Grid overview*: https://learn.microsoft.com/azure/event-grid/overview
- Microsoft Learn — *Azure Event Grid delivery and retry*: https://learn.microsoft.com/azure/event-grid/delivery-and-retry
- Microsoft Learn — *Event Grid trigger for Azure Functions*: https://learn.microsoft.com/azure/azure-functions/functions-bindings-event-grid-trigger
- Microsoft Learn — *Azure Functions Blob storage bindings*: https://learn.microsoft.com/azure/azure-functions/functions-bindings-storage-blob
- Microsoft Learn — *Azure Functions Queue storage trigger*: https://learn.microsoft.com/azure/azure-functions/functions-bindings-storage-queue-trigger
- Microsoft Learn — *Azure Blob Storage versioning*: https://learn.microsoft.com/azure/storage/blobs/versioning-overview
- Microsoft Learn — *Authorize Blob data with Microsoft Entra ID*: https://learn.microsoft.com/azure/storage/blobs/authorize-access-azure-active-directory
