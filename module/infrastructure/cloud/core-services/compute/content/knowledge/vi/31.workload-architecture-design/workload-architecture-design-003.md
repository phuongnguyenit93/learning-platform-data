# Thiết kế hệ thống xử lý sự kiện bằng hàm serverless

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Giải thích cách hàm serverless tiếp nhận và xử lý sự kiện theo mô hình bất đồng bộ.
- Chọn nguồn sự kiện, bộ định tuyến, hàng đợi và hàm xử lý phù hợp với yêu cầu nghiệp vụ.
- Thiết kế event envelope, schema, định danh và luồng xử lý có khả năng retry an toàn.
- Kết hợp hàm serverless với queue, pub/sub, event bus và workflow orchestration.
- Kiểm soát concurrency, thời gian chạy, cold start, bảo mật và chi phí.
- Thiết lập quan sát và kiểm thử khả năng phục hồi khi sự kiện đến trùng, đến sai thứ tự hoặc xử lý thất bại.

## 1. Kiến trúc hướng sự kiện với hàm serverless

Trong kiến trúc hướng sự kiện (event-driven architecture), một thành phần phát ra sự kiện khi một việc đã xảy ra; các thành phần khác đăng ký nhận và phản ứng với sự kiện đó. Ví dụ, khi khách hàng tải ảnh lên, hệ thống phát sự kiện ObjectCreated. Một hàm serverless nhận sự kiện, tạo ảnh thu nhỏ rồi lưu kết quả. Một hàm khác có thể cập nhật chỉ mục tìm kiếm hoặc gửi thông báo mà không cần sửa trực tiếp dịch vụ tải ảnh.

Hàm serverless là đơn vị thực thi do nền tảng quản lý hạ tầng, khởi chạy khi có yêu cầu hoặc sự kiện và thường được tính phí theo thời gian thực thi, số lần gọi hoặc tài nguyên được cấp. Nhóm phát triển tập trung vào mã xử lý, cấu hình runtime, quyền truy cập và giới hạn vận hành. Nền tảng chịu trách nhiệm cấp môi trường thực thi, mở rộng số instance và thay thế instance lỗi trong phạm vi dịch vụ.

Một kiến trúc điển hình có các thành phần:

- **Event producer:** dịch vụ hoặc người dùng tạo ra sự kiện, ví dụ API, object storage, database hoặc ứng dụng.
- **Event source:** nguồn cung cấp sự kiện, có thể là queue, stream, event bus, webhook hoặc trigger của dịch vụ.
- **Router/broker:** lọc, định tuyến hoặc phân phối sự kiện đến một hay nhiều consumer.
- **Serverless function:** thực thi logic phản ứng với sự kiện.
- **State store:** lưu trạng thái nghiệp vụ, kết quả, checkpoint hoặc khóa idempotency.
- **Dead-letter queue (DLQ):** giữ sự kiện không thể xử lý sau chính sách retry.
- **Observability:** ghi log, metric, trace và cảnh báo để theo dõi toàn bộ luồng.

Luồng xử lý cơ bản:

1. Một hành động nghiệp vụ xảy ra, chẳng hạn đơn hàng được xác nhận.
2. Producer phát sự kiện OrderConfirmed với định danh và dữ liệu cần thiết.
3. Event bus hoặc queue nhận sự kiện và áp dụng chính sách lưu trữ, lọc, retry.
4. Nền tảng gọi hàm serverless tương ứng.
5. Hàm xác thực sự kiện, kiểm tra idempotency và thực hiện tác dụng phụ.
6. Hàm ghi kết quả bền vững rồi xác nhận xử lý theo giao thức của nguồn sự kiện.
7. Nếu lỗi tạm thời, sự kiện được retry; nếu vượt giới hạn, sự kiện được chuyển sang DLQ để điều tra.

Sự kiện mô tả điều đã xảy ra, chẳng hạn OrderPaid. Command mô tả việc cần thực hiện, chẳng hạn CapturePayment. Phân biệt hai khái niệm giúp tránh việc consumer hiểu nhầm một sự kiện thông báo thành yêu cầu phải thực hiện lại hành động. Một sự kiện có thể có nhiều consumer độc lập; một command thường có một bên chịu trách nhiệm thực thi.

## 2. Khi nào nên dùng hàm serverless?

Hàm serverless phù hợp khi công việc có thể chia thành các lần thực thi độc lập, thời gian chạy nằm trong giới hạn nền tảng và nhu cầu tài nguyên biến động. Các trường hợp phổ biến:

- Phản ứng với sự kiện object storage: tạo thumbnail, kiểm tra file, trích xuất metadata.
- Xử lý thông điệp: gửi email, cập nhật trạng thái đơn hàng, đồng bộ dữ liệu.
- Tích hợp hệ thống: nhận webhook, chuyển đổi payload, gọi API bên ngoài.
- Tự động hóa vận hành: xử lý lịch, phản hồi cảnh báo, chạy tác vụ bảo trì ngắn.
- Xử lý dữ liệu theo luồng hoặc theo lô nhỏ: chuẩn hóa bản ghi, lọc sự kiện, ghi vào kho dữ liệu.

Hàm serverless không phải lựa chọn tối ưu cho mọi tác vụ. Cần cân nhắc container hoặc worker chạy liên tục khi:

- Tác vụ kéo dài hơn giới hạn thời gian của hàm.
- Cần tiến trình nền liên tục, kết nối dài hoặc thư viện native nặng.
- Tải ổn định cao khiến chi phí thực thi serverless vượt mô hình container phù hợp.
- Cần kiểm soát sâu hệ điều hành, runtime hoặc tài nguyên GPU.
- Công việc cần phối hợp nhiều bước dài, có trạng thái và bù trừ phức tạp; khi đó nên dùng workflow orchestration hoặc worker chuyên dụng.

Có thể kết hợp serverless và container: hàm nhận sự kiện, xác thực và điều phối; công việc nặng được đẩy vào queue để worker container xử lý. Cách này giữ đường tiếp nhận nhẹ và giới hạn thời gian thực thi của hàm.

## 3. Chọn mô hình tiếp nhận sự kiện

Không phải mọi nguồn sự kiện đều có cùng cơ chế giao nhận. Cần chọn dựa trên tốc độ sự kiện, khả năng lưu, thứ tự, fan-out và cách consumer xác nhận.

| Mô hình | Cách hoạt động | Phù hợp với |
|---|---|---|
| Direct trigger | Dịch vụ gọi hàm khi sự kiện xảy ra | Sự kiện đơn giản, cần phản hồi nhanh và nguồn có tích hợp trực tiếp |
| Queue | Lưu thông điệp; consumer nhận và xác nhận | Xử lý bất đồng bộ, hấp thụ burst, retry và kiểm soát backlog |
| Pub/sub | Một sự kiện được phân phối đến nhiều subscription | Nhiều hệ thống cần phản ứng độc lập với cùng sự kiện |
| Event bus | Nhận sự kiện từ nhiều nguồn, lọc theo rule và định tuyến đến target | Tích hợp nhiều dịch vụ và phân tách producer khỏi consumer |
| Stream | Lưu chuỗi sự kiện có partition và offset | Thông lượng lớn, replay, xử lý theo thứ tự trong partition |
| Webhook | Hệ thống bên ngoài gửi HTTP request đến endpoint | Tích hợp SaaS hoặc đối tác, khi cần xác thực chữ ký và kiểm soát retry |

### 3.1. Direct trigger

Direct trigger có ít thành phần, dễ triển khai và giảm độ trễ. Ví dụ, object storage gọi hàm khi một file mới được tạo. Tuy nhiên, cần hiểu nguồn có retry hay không, sự kiện có thể trùng không, thời gian giữ sự kiện bao lâu và điều gì xảy ra khi hàm không khả dụng.

Nếu nguồn sự kiện không cung cấp hàng đợi bền vững hoặc khả năng replay đủ mạnh, cân nhắc đưa queue hoặc event bus vào giữa để có vùng đệm, kiểm soát retry và cách ly lỗi.

### 3.2. Queue và competing consumers

Queue phù hợp khi mỗi công việc thường chỉ cần một consumer xử lý thành công. Nhiều instance của cùng hàm có thể đọc một queue để tăng thông lượng. Broker giữ thông điệp trong thời gian xử lý và chờ xác nhận. Nếu hàm thất bại hoặc hết thời gian visibility/lease, message có thể được giao lại.

Queue giúp producer không cần biết số lượng hàm đang chạy. Nó cũng tạo khả năng backpressure: khi consumer chậm, backlog tăng và có thể được quan sát, giới hạn hoặc xử lý sau. Queue không tự giải quyết overload; cần giới hạn độ dài, tuổi message, tốc độ producer và concurrency consumer.

### 3.3. Pub/sub và fan-out

Khi một sự kiện cần nhiều phản ứng độc lập, dùng pub/sub hoặc event bus. Ví dụ OrderPaid có thể được gửi đến:

- Hàm cập nhật trạng thái giao hàng.
- Hàm phát hành hóa đơn.
- Hàm cập nhật dữ liệu phân tích.
- Hàm gửi thông báo cho khách hàng.

Mỗi subscription có thể có retry và DLQ riêng. Một consumer lỗi không nên ngăn các consumer khác xử lý nếu nền tảng hỗ trợ tách subscription. Fan-out làm tăng tổng số lần gọi và tác dụng phụ, vì vậy phải kiểm soát chi phí, quyền truy cập và khả năng xử lý trùng ở từng consumer.

### 3.4. Stream và thứ tự

Stream phù hợp khi cần giữ lịch sử sự kiện và xử lý theo offset. Partition key thường quyết định thứ tự trong một partition. Ví dụ, dùng accountId làm key để sự kiện của cùng tài khoản được xử lý tuần tự trong partition tương ứng.

Không nên giả định thứ tự toàn cục nếu nền tảng chỉ bảo đảm thứ tự trong partition. Nếu hai sự kiện liên quan đến cùng thực thể có thể được xử lý đồng thời, cần version, sequence number hoặc optimistic concurrency để phát hiện sự kiện cũ.

## 4. Thiết kế event envelope và schema

Event envelope là lớp metadata chung bao quanh dữ liệu nghiệp vụ. Một định dạng thống nhất giúp router, logger, schema registry và consumer xử lý sự kiện nhất quán.

Ví dụ:

    {
      "specversion": "1.0",
      "id": "evt-8c1f2a",
      "source": "commerce.orders",
      "type": "com.example.order.confirmed.v1",
      "subject": "orders/order-00421",
      "time": "2026-11-22T09:30:00Z",
      "datacontenttype": "application/json",
      "data": {
        "orderId": "order-00421",
        "customerId": "customer-018",
        "total": 1250000,
        "currency": "VND"
      },
      "correlationId": "checkout-req-9d3",
      "traceparent": "00-..."
    }

Các trường quan trọng:

- **id:** định danh duy nhất của sự kiện; consumer dùng để theo dõi và chống xử lý lặp.
- **source:** hệ thống hoặc thành phần phát sự kiện.
- **type:** loại sự kiện và phiên bản schema.
- **subject:** thực thể nghiệp vụ liên quan, chẳng hạn đơn hàng hoặc tài khoản.
- **time:** thời điểm sự kiện được tạo, dùng để phân tích độ trễ và sự kiện cũ.
- **data:** payload nghiệp vụ tối thiểu cần cho consumer.
- **correlationId:** liên kết các sự kiện trong cùng một luồng nghiệp vụ.
- **traceparent:** truyền ngữ cảnh distributed tracing nếu hệ thống hỗ trợ.

CloudEvents là một đặc tả phổ biến cho event envelope. Có thể dùng định dạng tương đương nếu tổ chức đã có chuẩn nội bộ, nhưng cần thống nhất tên trường, cách định danh, timestamp, content type và version.

### 4.1. Versioning và tương thích

Schema sự kiện thay đổi theo thời gian. Nếu producer thêm trường mới, consumer cũ nên bỏ qua trường chưa biết khi có thể. Nếu đổi kiểu dữ liệu hoặc xóa trường, consumer cũ có thể lỗi.

Nguyên tắc thiết kế:

- Thêm trường tùy chọn theo hướng tương thích ngược.
- Không đổi ý nghĩa của trường đã phát hành.
- Dùng version rõ ràng khi có thay đổi phá vỡ tương thích.
- Có schema registry hoặc kiểm tra schema trong CI/CD nếu nhiều nhóm cùng phát triển.
- Duy trì consumer có thể đọc phiên bản đang được phát trong khoảng thời gian rollout.
- Kiểm thử producer mới với consumer cũ và ngược lại.

Không dùng tên sự kiện chung chung như Updated cho nhiều thay đổi nghiệp vụ khác nhau. Tên OrderAddressChanged hoặc PaymentCaptured thể hiện rõ điều đã xảy ra và giúp consumer lọc chính xác.

### 4.2. Payload nhỏ và tham chiếu dữ liệu

Sự kiện nên chứa dữ liệu đủ để consumer xử lý mà không phải gọi quá nhiều dịch vụ. Tuy nhiên, payload lớn làm tăng chi phí truyền, lưu và retry; dữ liệu nhạy cảm cũng dễ bị nhân bản qua nhiều hệ thống.

Với file lớn hoặc dữ liệu nhạy cảm, lưu ở object storage hoặc kho dữ liệu được kiểm soát, rồi phát tham chiếu cùng object key, version, checksum và metadata cần thiết. Consumer xác minh quyền truy cập, tính toàn vẹn và thời hạn tham chiếu trước khi đọc. Tránh gửi URL có quyền truy cập lâu dài trong event bus hoặc log.

## 5. Thiết kế luồng ví dụ: xử lý ảnh tải lên

Một ứng dụng lưu ảnh gốc trong object storage. Khi file được tải lên, hệ thống cần kiểm tra loại file, tạo thumbnail, lưu metadata và phát thông báo hoàn tất.

Kiến trúc tham khảo:

    Client
      |
      v
    API / Upload service
      |
      v
    Object storage (originals)
      |
      v
    Event bus: ObjectCreated
      |
      +------> Queue: image-processing
      |                |
      |                v
      |          Serverless function
      |                |
      |                +----> Validate / decode
      |                |
      |                +----> Create thumbnail
      |                |
      |                v
      |          Object storage (derived)
      |
      +------> Function: audit metadata
                       |
                       v
                 Metadata database

Quy trình:

1. API cấp quyền tải lên hoặc nhận file và lưu file gốc vào bucket originals.
2. Storage phát sự kiện ObjectCreated.
3. Event bus lọc sự kiện theo bucket và prefix, chỉ định tuyến file thuộc vùng originals.
4. Queue image-processing nhận message và gọi hàm xử lý.
5. Hàm xác thực định dạng, kích thước, quyền truy cập và giới hạn tài nguyên.
6. Hàm tạo thumbnail, ghi file dẫn xuất và cập nhật trạng thái xử lý.
7. Hàm phát ImageProcessed hoặc cập nhật trạng thái để frontend hiển thị kết quả.
8. Nếu xử lý lỗi, queue retry theo chính sách; message lỗi kéo dài được chuyển sang DLQ.

Dùng queue giữa event bus và hàm xử lý để tách tốc độ upload khỏi tốc độ xử lý. Nếu một đợt tải lên tạo hàng nghìn file, queue hấp thụ burst và hàm có thể scale theo backlog. Đặt giới hạn concurrency để không làm cạn CPU, memory hoặc connection của kho metadata.

Một điểm cần tránh là tạo vòng lặp sự kiện: hàm ghi thumbnail vào cùng bucket và prefix đã đăng ký trigger ObjectCreated, khiến chính thumbnail lại kích hoạt hàm. Có thể dùng bucket/prefix riêng cho file dẫn xuất, lọc event theo prefix, hoặc kiểm tra loại object trước khi xử lý.

## 6. Idempotency và xử lý sự kiện trùng

Nhiều nền tảng giao sự kiện theo mô hình at-least-once. Sự kiện có thể được gửi lại khi consumer không xác nhận kịp, khi timeout hoặc khi nền tảng không biết chắc lần xử lý trước đã hoàn tất. Do đó, một hàm phải được thiết kế để xử lý cùng một event nhiều lần mà không tạo tác dụng phụ trùng.

Cách tiếp cận:

1. Dùng event id hoặc business key ổn định làm idempotency key.
2. Ghi nhận key trong kho dữ liệu có ràng buộc duy nhất hoặc thao tác conditional write.
3. Nếu key đã được xử lý thành công, bỏ qua tác dụng phụ và trả kết quả thành công.
4. Nếu chưa được xử lý, thực hiện nghiệp vụ và lưu kết quả theo cách nhất quán.
5. Đặt thời hạn lưu idempotency record phù hợp với thời gian retry, retention và khả năng replay.

Ví dụ bảng xử lý:

| event_id | status | processed_at | result_ref |
|---|---|---|---|
| evt-8c1f2a | SUCCEEDED | 2026-11-22T09:31Z | invoice-00421 |
| evt-8c1f2b | RUNNING | 2026-11-22T09:32Z | |
| evt-8c1f2c | FAILED_RETRYABLE | 2026-11-22T09:33Z | |

Chỉ kiểm tra rồi ghi theo hai thao tác tách rời có thể tạo race condition: hai invocation cùng thấy key chưa tồn tại và cùng thực hiện tác dụng phụ. Dùng unique constraint, conditional put, transaction hoặc distributed lock có lease để bảo đảm chỉ một invocation giành quyền xử lý. Lock phải có thời hạn và có cơ chế xử lý khi invocation chết.

Với tác dụng phụ ngoài database, chẳng hạn gửi email hoặc gọi cổng thanh toán, hãy truyền idempotency key đến dịch vụ đích nếu dịch vụ hỗ trợ. Nếu không, dùng outbox/inbox, saga hoặc quy trình đối soát để xử lý trạng thái không chắc chắn. Không thể bảo đảm exactly-once end-to-end chỉ bằng cách cấu hình retry của hàm.

## 7. Retry, timeout và dead-letter queue

Retry giúp phục hồi lỗi tạm thời, nhưng retry không có giới hạn có thể tạo vòng lặp lỗi và tăng tải. Cần phân loại lỗi:

- **Tạm thời:** timeout mạng, throttling, dịch vụ phụ thuộc không sẵn sàng.
- **Không thể retry nếu không sửa dữ liệu:** payload sai, schema không hợp lệ, thiếu quyền hoặc vi phạm quy tắc nghiệp vụ.
- **Không xác định:** invocation hết thời gian sau khi tác dụng phụ có thể đã xảy ra; phải kiểm tra idempotency trước khi thử lại.

Một chính sách retry nên xác định số lần thử tối đa, khoảng chờ, backoff, jitter và tuổi tối đa của sự kiện. Exponential backoff giúp giảm tốc độ retry khi dependency gặp sự cố:

    delay = min(maxDelay, baseDelay * 2^attempt)
    actualDelay = random(0, delay)

Jitter phân tán thời điểm retry để nhiều invocation không cùng thức dậy và tạo tải đột biến. Với HTTP 429 hoặc Retry-After, cần tôn trọng thời gian do dịch vụ đích hướng dẫn.

### 7.1. Retry tùy nguồn sự kiện

Cách retry khác nhau theo trigger:

- Với queue, message thường được giao lại nếu hàm không xác nhận hoặc xử lý lỗi. Visibility timeout/lock duration phải đủ cho thời gian xử lý và có thể cần gia hạn.
- Với event bus, nền tảng có thể retry target trong khoảng thời gian và số lần cấu hình. Sau đó có thể chuyển sự kiện sang DLQ.
- Với stream, consumer có thể bị chặn tại partition hoặc tiếp tục từ offset tùy cơ chế commit và xử lý lỗi. Cần tránh một bản ghi độc hại chặn toàn partition vô thời hạn.
- Với webhook, endpoint nên trả mã HTTP phù hợp; hệ thống gửi cần có retry và backoff. Consumer nên ghi nhận request trước khi trả thành công nếu cần xử lý bất đồng bộ.

Không áp dụng cùng một retry policy cho mọi nguồn. Xác định rõ thành phần nào chịu trách nhiệm retry: broker, nền tảng gọi hàm hay mã ứng dụng. Tránh để nhiều lớp cùng retry không giới hạn, vì tổng số lần thử có thể tăng theo cấp số nhân.

### 7.2. Batch và partial failure

Một số event source mapping gom nhiều message thành một batch để giảm số lần gọi hàm. Nếu một bản ghi lỗi và hàm báo lỗi cho toàn batch, các bản ghi đã xử lý thành công có thể bị giao lại. Consumer phải idempotent hoặc dùng cơ chế partial batch response nếu nền tảng hỗ trợ.

Với queue SQS và AWS Lambda, có thể bật ReportBatchItemFailures để hàm chỉ định message nào cần retry. Ví dụ minh họa:

    def handler(event, context):
        failures = []

        for record in event["Records"]:
            try:
                process_record(record)
            except RetryableError:
                failures.append({
                    "itemIdentifier": record["messageId"]
                })
            except InvalidRecordError:
                quarantine_record(record)
                # Chỉ coi là đã xử lý nếu quarantine ghi thành công.

        return {
            "batchItemFailures": failures
        }

Nếu thao tác quarantine thất bại, không được âm thầm xác nhận message lỗi; hãy để message retry hoặc áp dụng chính sách lỗi phù hợp. Với lỗi không dự kiến, nên để invocation thất bại để broker áp dụng retry theo cấu hình. Kiểm tra đúng response contract và cấu hình event source mapping của runtime đang dùng.

### 7.3. DLQ và redrive

DLQ giữ sự kiện vượt giới hạn retry để hệ thống chính tiếp tục xử lý sự kiện khỏe mạnh. DLQ cần được theo dõi và có quy trình xử lý:

1. Cảnh báo khi DLQ có message hoặc tốc độ tăng vượt ngưỡng.
2. Phân loại theo event type, source, schema version và lỗi.
3. Xác định lỗi do dữ liệu, code, quyền, dependency hay cấu hình.
4. Sửa nguyên nhân và kiểm tra với một message đại diện.
5. Redrive theo đợt nhỏ, giới hạn tốc độ và theo dõi tác dụng phụ trùng.
6. Lưu audit log cho hoạt động phát lại và kết quả.

Không tự động redrive liên tục khi nguyên nhân chưa được sửa. Với sự kiện nhạy cảm, cần quy trình phê duyệt và kiểm tra quyền trước khi phát lại.

## 8. Thứ tự sự kiện và xử lý sự kiện đến muộn

Sự kiện có thể đến trễ hoặc sai thứ tự do retry, phân vùng mạng, xử lý song song hoặc độ trễ giữa các nguồn. Ví dụ, OrderShipped có thể đến trước OrderPacked dù nghiệp vụ xảy ra theo thứ tự ngược lại.

Các cách bảo vệ:

- Đưa version hoặc sequence number tăng dần vào sự kiện.
- Lưu trạng thái hiện tại cùng version đã áp dụng.
- Chỉ áp dụng sự kiện có version mới hơn trạng thái đã lưu.
- Dùng event time và processing time riêng; không nhầm thời điểm phát với thời điểm consumer nhận.
- Dùng partition key ổn định nếu cần thứ tự trong phạm vi một thực thể.
- Thiết kế consumer có thể bỏ qua sự kiện cũ hoặc chờ sự kiện còn thiếu theo quy tắc nghiệp vụ.

Ví dụ cập nhật trạng thái đơn hàng:

    if event.version <= order.lastAppliedVersion:
        ignore_as_duplicate_or_stale(event)
    else:
        apply_transition(event)
        order.lastAppliedVersion = event.version

Đây chỉ là logic minh họa. Khi cập nhật đồng thời, phải dùng optimistic concurrency, transaction hoặc conditional update để hai invocation không cùng ghi đè version. Nếu sự kiện đến thiếu thứ tự, cần quyết định có thể áp dụng trạng thái mới trực tiếp hay phải đợi các chuyển trạng thái trung gian.

## 9. Fan-out, orchestration và saga

Có hai cách phổ biến để phối hợp nhiều hàm:

- **Choreography:** các thành phần phản ứng với sự kiện và phát sự kiện tiếp theo. Mỗi dịch vụ độc lập, nhưng luồng tổng thể có thể khó quan sát khi có nhiều nhánh.
- **Orchestration:** một workflow điều phối thứ tự các bước, timeout, retry, nhánh điều kiện và trạng thái. Phù hợp quy trình dài hoặc cần biết rõ bước nào đã hoàn thành.

Ví dụ quy trình xử lý đơn hàng:

1. OrderCreated kích hoạt hàm kiểm tra tồn kho.
2. InventoryReserved được phát khi giữ hàng thành công.
3. Hàm thanh toán nhận InventoryReserved và gọi cổng thanh toán.
4. PaymentCaptured kích hoạt dịch vụ giao hàng.
5. ShipmentCreated kích hoạt hàm thông báo khách hàng.

Nếu thanh toán thất bại sau khi giữ hàng, hệ thống cần giải phóng tồn kho. Đây là một saga: mỗi bước có hành động bù trừ (compensation) để đưa hệ thống về trạng thái hợp lệ. Không dùng transaction phân tán giả định bao trùm nhiều dịch vụ độc lập.

Khi quy trình có nhiều bước, chờ callback, timeout dài hoặc cần theo dõi trạng thái tổng thể, dùng dịch vụ workflow như AWS Step Functions, Google Workflows hoặc Azure Durable Functions. Hàm serverless thực hiện từng bước; workflow lưu trạng thái và quản lý retry/timeout theo định nghĩa. Với luồng đơn giản, event choreography có thể nhẹ hơn.

## 10. Điều khiển concurrency và bảo vệ dependency

Hàm serverless có thể tự mở rộng nhiều invocation song song. Đây là lợi thế khi tải biến động, nhưng cũng có thể làm quá tải database, API ngoài hoặc hệ thống thanh toán nếu không giới hạn.

Cần quản lý:

- **Concurrency tổng:** giới hạn số invocation đồng thời cho một hàm hoặc tài khoản theo năng lực nền tảng.
- **Reserved concurrency:** dành hoặc giới hạn concurrency cho một hàm trên nền tảng hỗ trợ.
- **Provisioned concurrency:** giữ sẵn môi trường thực thi để giảm cold start, đổi lại có chi phí duy trì.
- **Queue batch size:** số message mỗi invocation; batch lớn giảm overhead nhưng tăng thời gian xử lý và phạm vi retry.
- **Maximum concurrency của event source:** giới hạn số consumer poll queue hoặc stream nếu dịch vụ hỗ trợ.
- **Connection pool:** tái sử dụng kết nối khi runtime được tái sử dụng, nhưng không giả định instance luôn sống lâu.
- **Rate limit:** giới hạn tốc độ gọi dependency theo quota và SLA của dịch vụ đích.

Ví dụ, database chỉ chịu được 300 kết nối và mỗi invocation mở một kết nối. Nếu hàm scale lên 500 invocation, database có thể bị quá tải. Cần dùng connection pooling phù hợp, proxy kết nối, giới hạn concurrency hoặc đưa tác vụ vào queue để điều tiết.

Không tăng concurrency chỉ để giảm queue depth. Theo dõi downstream latency, throttling và lỗi cùng lúc. Nếu dependency đang quá tải, tăng số invocation sẽ làm tình trạng xấu hơn. Có thể giảm concurrency, tăng backoff, dùng circuit breaker hoặc tạm ngừng consumer.

## 11. Cold start, thời gian thực thi và chi phí

Cold start xảy ra khi nền tảng cần tạo môi trường thực thi mới trước khi chạy hàm. Thời gian khởi động phụ thuộc runtime, kích thước package, thư viện, cấu hình mạng và cách nền tảng cấp tài nguyên. Tải tăng đột ngột có thể tạo nhiều cold start cùng lúc.

Các cách giảm tác động:

- Giữ package và dependency gọn, loại bỏ thư viện không cần thiết.
- Khởi tạo client bên ngoài handler để tái sử dụng khi runtime còn sống.
- Tránh tải dữ liệu lớn hoặc chạy migration trong mỗi invocation.
- Dùng provisioned/minimum instances khi yêu cầu latency nghiêm ngặt và ngân sách cho phép.
- Chọn runtime và memory phù hợp; tăng memory có thể đồng thời tăng CPU trên một số nền tảng.
- Đo p95/p99 latency thay vì chỉ nhìn thời gian trung bình.

Tối ưu chi phí cần xét tổng thể:

| Yếu tố | Tác động chi phí |
|---|---|
| Số invocation | Mỗi sự kiện hoặc lần retry có thể phát sinh lượt gọi |
| Thời gian và memory | Invocation chạy lâu hoặc cấp nhiều bộ nhớ có thể tốn hơn |
| Event bus/queue | Request, operation, polling, storage và data transfer |
| Logging/tracing | Log quá chi tiết hoặc retention dài làm tăng chi phí lưu trữ |
| DLQ và replay | Message tồn đọng, redrive và xử lý lại tạo thêm tài nguyên |
| Downstream | Database, API, object storage và network egress có thể chiếm phần lớn tổng chi phí |

Một hàm rẻ trên mỗi invocation vẫn có thể tạo chi phí cao nếu một sự kiện kích hoạt nhiều nhánh, retry liên tục hoặc phát sinh hàng nghìn request đến dependency. Đo cost per business event, chẳng hạn chi phí hoàn tất một đơn hàng hoặc xử lý một file, sẽ hữu ích hơn chỉ nhìn giá của hàm.

## 12. Bảo mật và quản trị sự kiện

Sự kiện có thể mang dữ liệu nghiệp vụ và kích hoạt hành động có tác động lớn. Cần bảo vệ cả nguồn phát, kênh truyền và hàm consumer.

- Xác thực nguồn sự kiện; với webhook, xác minh chữ ký, timestamp và chống replay.
- Dùng IAM/service identity với quyền tối thiểu cho từng hàm.
- Chỉ cho phép hàm đọc đúng queue/topic và ghi đúng tài nguyên cần thiết.
- Mã hóa dữ liệu khi truyền và khi lưu theo khả năng của nền tảng.
- Lưu secret trong secret manager; không nhúng credential vào payload hoặc source code.
- Kiểm tra schema, kích thước và dữ liệu đầu vào trước khi thực hiện tác dụng phụ.
- Phân vùng dữ liệu theo tenant và xác minh quyền truy cập trong consumer.
- Hạn chế quyền purge queue, xóa DLQ, thay đổi rule và redrive.
- Dùng audit log cho thay đổi cấu hình và thao tác vận hành.

Không tin tưởng payload chỉ vì nó đến từ event bus nội bộ. Một producer bị xâm nhập hoặc cấu hình quyền sai có thể phát sự kiện giả. Consumer vẫn cần xác thực source, kiểm tra trạng thái nghiệp vụ và chống lặp.

## 13. Quan sát toàn bộ luồng sự kiện

Một invocation thành công không đồng nghĩa quy trình nghiệp vụ đã hoàn tất. Cần liên kết producer, broker, function và dependency bằng event id, correlation id và trace context.

Các metric quan trọng:

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| Ingress | Số sự kiện đến, tốc độ publish, publish failure | Producer có gửi được sự kiện? |
| Queue | Queue depth, oldest message age, in-flight count | Backlog có tăng hoặc vượt SLA? |
| Function | Invocation count, duration, error, timeout, throttles, concurrency | Hàm có đủ năng lực và ổn định? |
| Reliability | Retry, redelivery, duplicate, DLQ count | Sự kiện có bị lặp hoặc thất lạc? |
| Dependency | Database latency, connection, API 429/5xx | Consumer có làm quá tải hệ thống khác? |
| Business | Thời gian từ event đến trạng thái hoàn tất, tỷ lệ nghiệp vụ thành công | Người dùng có nhận kết quả đúng hạn? |
| Cost | Cost per invocation và cost per business event | Chi phí có tăng bất thường? |

Log nên có eventId, eventType, source, function version, attempt, correlationId và kết quả xử lý. Không ghi toàn bộ payload nếu chứa dữ liệu nhạy cảm. Dùng distributed tracing để xác định thời gian nằm trong queue, thời gian chạy hàm và thời gian chờ dependency.

Cảnh báo nên gắn với SLA: tuổi sự kiện lâu nhất vượt ngưỡng, DLQ tăng, tỷ lệ timeout tăng, function throttling kéo dài hoặc thời gian hoàn tất nghiệp vụ vượt mục tiêu. Cảnh báo queue depth đơn lẻ có thể gây nhiễu nếu tốc độ xử lý vẫn đủ và message còn mới.

## 14. Ví dụ nền tảng: AWS và các lựa chọn tương đương

Một triển khai trên AWS có thể dùng Amazon S3 phát sự kiện, Amazon EventBridge lọc và định tuyến, Amazon SQS làm buffer, AWS Lambda xử lý và DynamoDB lưu idempotency record. SQS DLQ giữ message đã vượt số lần nhận cho phép. CloudWatch thu thập log và metric.

Các dịch vụ tương đương ở nền tảng khác có thể gồm:

| Vai trò | AWS | Google Cloud | Microsoft Azure |
|---|---|---|---|
| Hàm serverless | AWS Lambda | Cloud Run functions | Azure Functions |
| Event routing | Amazon EventBridge | Eventarc | Azure Event Grid |
| Queue/pub-sub | Amazon SQS, SNS | Pub/Sub | Service Bus |
| Workflow | Step Functions | Workflows | Durable Functions |
| Log/metric | CloudWatch | Cloud Logging/Monitoring | Azure Monitor |

Tên gọi và tính năng cụ thể khác nhau. Cần kiểm tra giới hạn payload, timeout, retry, concurrency, retention, vùng và quota của dịch vụ đang dùng. Không giả định một dịch vụ có cùng delivery semantics hoặc giới hạn với dịch vụ cùng vai trò ở nền tảng khác.

Ví dụ cấu hình khái niệm cho queue-triggered function:

    Function:
      Runtime: Python
      Timeout: 30 seconds
      Memory: 1024 MB
      ReservedConcurrency: 40

    EventSourceMapping:
      SourceQueue: image-processing
      BatchSize: 5
      ReportBatchItemFailures: true

    Queue:
      VisibilityTimeout: greater than function timeout with safety margin
      Retention: according to business SLA
      RedrivePolicy:
        MaxReceiveCount: 5
        DeadLetterQueue: image-processing-dlq

Đây là cấu hình minh họa, không phải manifest triển khai hoàn chỉnh. Cần đối chiếu cú pháp IaC và giới hạn dịch vụ. Visibility timeout cần đủ dài để hàm xử lý batch và xác nhận; nếu quá ngắn, message có thể được giao lại khi invocation trước chưa kết thúc.

## 15. Quy trình thiết kế và triển khai

Có thể dùng quy trình sau khi bắt đầu một hệ thống event-driven:

1. **Xác định sự kiện nghiệp vụ:** mô tả điều đã xảy ra, producer và consumer cần phản ứng.
2. **Đặt yêu cầu dịch vụ:** latency, throughput, thứ tự, retention, thời gian phục hồi và SLA.
3. **Chọn nguồn sự kiện:** direct trigger, queue, pub/sub, event bus, stream hoặc webhook.
4. **Thiết kế event envelope:** định danh, source, type, schema version, timestamp, correlation và payload.
5. **Thiết kế đường lỗi:** timeout, retry, backoff, idempotency, DLQ và redrive.
6. **Thiết kế tác dụng phụ:** transaction, outbox/inbox, conditional write hoặc saga.
7. **Đặt giới hạn tài nguyên:** memory, timeout, batch size, concurrency và quota dependency.
8. **Thiết kế bảo mật:** identity, quyền tối thiểu, secret, mã hóa và kiểm tra payload.
9. **Thiết lập quan sát:** log có cấu trúc, metric, trace, dashboard và cảnh báo theo SLA.
10. **Triển khai bằng IaC:** quản lý function, trigger, queue, DLQ, rule, quyền và alarm trong cùng quy trình phát hành.
11. **Kiểm thử lỗi và tải:** duplicate, out-of-order, throttling, timeout, burst và dependency outage.
12. **Triển khai từng bước:** canary hoặc traffic shifting nếu nền tảng hỗ trợ; theo dõi trước khi tăng lưu lượng.

## 16. Kịch bản kiểm chứng trước production

Thực hiện trong môi trường staging:

1. **Sự kiện hợp lệ:** phát một event mẫu và xác nhận đúng function nhận, đúng trạng thái nghiệp vụ được ghi.
2. **Sự kiện trùng:** gửi lại cùng event id; xác nhận tác dụng phụ không lặp.
3. **Sự kiện sai schema:** gửi payload thiếu trường hoặc sai kiểu; xác nhận được từ chối hoặc cách ly có kiểm soát.
4. **Function timeout:** mô phỏng xử lý lâu hơn timeout; xác nhận retry và idempotency bảo vệ kết quả.
5. **Dependency throttling:** làm API đích trả 429 hoặc 503; xác nhận backoff và giới hạn concurrency.
6. **Partial batch failure:** cho một message trong batch lỗi; xác nhận chỉ message lỗi được retry nếu cơ chế partial response đã bật.
7. **DLQ:** tạo message vượt số lần thử; xác nhận DLQ nhận message và cảnh báo được kích hoạt.
8. **Out-of-order:** gửi version mới trước version cũ; xác nhận trạng thái không bị ghi lùi.
9. **Burst:** phát tải tăng nhanh; đo queue age, function concurrency, throttles và downstream capacity.
10. **Replay:** phát lại một nhóm sự kiện đã xử lý; xác nhận consumer idempotent và có audit trail.
11. **Quyền truy cập:** thử gọi function hoặc đọc queue bằng identity không được cấp quyền; xác nhận bị từ chối.
12. **Chi phí:** đo số invocation, thời gian chạy, queue operations, log và downstream requests trên một lượng sự kiện đại diện.

Ghi lại kết quả, thời gian phục hồi và các giới hạn phát hiện được. Chỉ tăng lưu lượng production khi các chỉ số nằm trong SLO và DLQ có người chịu trách nhiệm vận hành.

## 17. Sự cố thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Hàm không được gọi | Trigger sai, quyền thiếu hoặc rule không khớp | Kiểm tra event source, rule filter, permission và metric ingress |
| Hàm được gọi nhiều lần | At-least-once delivery, timeout hoặc ack thất bại | Kiểm tra event id, idempotency store, retry và visibility timeout |
| Queue backlog tăng | Consumer chậm, concurrency thấp hoặc dependency lỗi | So sánh arrival rate, processing rate, duration và downstream latency |
| Function throttling | Concurrency chạm giới hạn hoặc quota tài khoản | Kiểm tra reserved/max concurrency, account quota và event source scaling |
| DLQ tăng nhanh | Payload lỗi, schema không tương thích hoặc dependency lỗi dài | Phân loại lỗi, kiểm tra phiên bản producer và dừng redrive tự động |
| Cold start làm tăng latency | Runtime/package nặng hoặc không có instance sẵn | Đo init duration, tối ưu package và cân nhắc provisioned/min instances |
| Sự kiện xử lý sai thứ tự | Consumer chạy song song hoặc nguồn không bảo đảm thứ tự toàn cục | Kiểm tra partition key, version và conditional update |
| Chi phí tăng bất thường | Fan-out rộng, retry loop, log nhiều hoặc payload lớn | Phân tích cost theo event type, retry, invocation và downstream |
| Trigger lặp vô hạn | Hàm ghi object vào cùng prefix/bucket được trigger | Kiểm tra event filter và tách vùng dữ liệu đầu vào/đầu ra |
| Hàm thành công nhưng nghiệp vụ chưa xong | Ack trước commit hoặc chỉ ghi log mà không lưu trạng thái | Đối chiếu transaction, trạng thái job và thời điểm ack |

## 18. Checklist thiết kế

- [ ] Mỗi event mô tả một sự kiện nghiệp vụ đã xảy ra, có source và type rõ ràng.
- [ ] Event envelope có id, schema version, timestamp và correlation/trace context.
- [ ] Chọn queue, pub/sub, event bus hoặc stream theo yêu cầu delivery và ordering.
- [ ] Xác định delivery semantics và thiết kế idempotency cho consumer.
- [ ] Lưu kết quả bền vững trước khi xác nhận message.
- [ ] Cấu hình timeout, retry, backoff, jitter, DLQ và redrive.
- [ ] Xử lý partial batch failure khi nguồn hỗ trợ batching.
- [ ] Có chiến lược versioning, sự kiện đến muộn và sai thứ tự.
- [ ] Giới hạn concurrency, batch size và tải lên dependency.
- [ ] Dùng outbox/inbox hoặc saga khi có nhiều hệ thống và tác dụng phụ.
- [ ] Quản lý IAM, secret, mã hóa và xác thực nguồn phát.
- [ ] Theo dõi queue age, duration, errors, throttles, DLQ và business latency.
- [ ] Kiểm thử duplicate, timeout, burst, replay, out-of-order và dependency outage.
- [ ] Quản lý cấu hình bằng IaC và có quy trình phát hành/rollback.
- [ ] Đo chi phí trên mỗi sự kiện nghiệp vụ và đặt cảnh báo ngân sách.

## Kết luận

Hệ thống xử lý sự kiện bằng hàm serverless tách producer khỏi consumer, cho phép mở rộng theo nhu cầu và giảm công sức vận hành máy chủ. Độ tin cậy phụ thuộc vào việc chọn đúng event source, thiết kế schema ổn định, xử lý trùng, retry có giới hạn, DLQ và lưu kết quả trước khi xác nhận. Concurrency phải phù hợp với năng lực của database và API phụ thuộc; quan sát phải nối được event id từ lúc phát đến khi nghiệp vụ hoàn tất. Hãy kiểm thử cả sự kiện lỗi, trùng, sai thứ tự và tải đột biến trước khi đưa kiến trúc vào production.
