# Quản lý trạng thái ngoài hàm và giới hạn sử dụng dữ liệu cục bộ

Hàm serverless thường được thiết kế theo mô hình **stateless**: mỗi lần gọi nhận đầu vào, thực hiện công việc rồi trả kết quả hoặc phát sinh sự kiện tiếp theo. Nền tảng có thể tạo thêm execution environment khi tải tăng, tái sử dụng một môi trường trong nhiều lần gọi hoặc thu hồi môi trường khi không còn cần thiết. Vì vậy, bộ nhớ tiến trình và hệ thống tệp cục bộ không phải nơi lưu dữ liệu nghiệp vụ cần tồn tại lâu dài.

Muốn dữ liệu bền vững qua nhiều lần gọi, lần triển khai, mở rộng ngang hoặc sự cố, ứng dụng cần lưu trạng thái ở dịch vụ bên ngoài như cơ sở dữ liệu, object storage, hàng đợi hoặc bộ điều phối workflow. Việc chọn đúng nơi lưu còn phụ thuộc vào kiểu dữ liệu, yêu cầu nhất quán, thời gian truy cập, dung lượng, chi phí và cách khôi phục.

## 1. Vì sao hàm serverless cần quản lý trạng thái bên ngoài?

Một hàm có thể được gọi bởi HTTP request, lịch chạy, thông điệp hàng đợi, sự kiện lưu trữ hoặc một bước trong workflow. Mỗi lần gọi có thể được xử lý bởi một execution environment khác nhau.

Ví dụ, một API serverless xử lý đơn hàng có thể nhận ba request gần như đồng thời. Nền tảng có thể chạy chúng trên ba môi trường khác nhau để đáp ứng tải. Nếu mỗi môi trường giữ danh sách đơn hàng trong biến toàn cục, mỗi bản sao chỉ thấy dữ liệu của chính nó. Không có cơ chế bảo đảm request tiếp theo sẽ quay lại cùng môi trường.

Các đặc điểm quan trọng của mô hình thực thi:

- **Môi trường có vòng đời do nền tảng quản lý:** runtime có thể được khởi tạo, tái sử dụng hoặc thu hồi mà ứng dụng không kiểm soát.
- **Mở rộng ngang:** nhiều bản thực thi có thể chạy đồng thời trên nhiều máy hoặc vùng xử lý.
- **Retry:** nền tảng hoặc dịch vụ phát sự kiện có thể gọi lại hàm khi timeout, lỗi tạm thời hoặc không nhận được xác nhận.
- **Triển khai phiên bản mới:** lần phát hành có thể tạo môi trường mới với mã và cấu hình mới.
- **Thời gian thực thi hữu hạn:** một invocation thường có giới hạn thời gian; công việc dài cần chia nhỏ hoặc chuyển trạng thái cho workflow/queue.
- **Tính đồng thời:** hai invocation có thể cùng cập nhật một bản ghi hoặc xử lý cùng một sự kiện.

Do đó, hàm nên xử lý đầu vào một cách độc lập, đọc trạng thái cần thiết từ hệ thống có lưu trữ bền vững, ghi kết quả rồi kết thúc. Khi invocation tiếp theo diễn ra ở môi trường khác, nó vẫn có thể tiếp tục công việc từ dữ liệu đã lưu.

## 2. Phân biệt trạng thái trong bộ nhớ, dữ liệu cục bộ và dữ liệu bền vững

Có ba nhóm dữ liệu thường gặp trong ứng dụng serverless:

| Nhóm dữ liệu | Ví dụ | Vòng đời và khả năng sử dụng |
|---|---|---|
| Trạng thái trong bộ nhớ | Biến cục bộ, object trong heap, dữ liệu cache trong biến toàn cục | Chỉ tồn tại trong tiến trình hiện tại; có thể mất khi môi trường bị thu hồi hoặc khởi động lại |
| Dữ liệu trên hệ thống tệp tạm | File tải xuống để xử lý, file nén trung gian, kết quả tạm | Có thể tồn tại trong vòng đời execution environment hoặc lâu hơn giữa các lần gọi được tái sử dụng, tùy nền tảng; không có bảo đảm lưu trữ lâu dài |
| Dữ liệu lưu bên ngoài | Bản ghi cơ sở dữ liệu, object trong bucket, thông điệp queue, trạng thái workflow | Được dịch vụ lưu trữ quản lý theo chính sách độ bền, sao lưu, nhân bản và khôi phục đã cấu hình |

Một biến toàn cục có thể hữu ích để tái sử dụng kết nối database, SDK client hoặc cache tham chiếu ít thay đổi giữa các invocation trong cùng môi trường. Tuy nhiên, dữ liệu trong biến toàn cục không được chia sẻ tự động giữa các môi trường và không nên là nguồn sự thật của nghiệp vụ.

Ví dụ, có thể khởi tạo client bên ngoài handler để giảm chi phí khởi tạo:

~~~javascript
// Minh họa Node.js: tái sử dụng client nếu runtime giữ môi trường ấm.
const databaseClient = createDatabaseClient();

export async function handler(event) {
  const order = await databaseClient.getOrder(event.orderId);
  return processOrder(order);
}
~~~

Client được tái sử dụng chỉ là tối ưu hiệu năng. Bản ghi đơn hàng vẫn nằm trong database. Mã xử lý phải hoạt động đúng cả khi nền tảng tạo một môi trường hoàn toàn mới.

Không nên dùng biến toàn cục để lưu giỏ hàng, trạng thái thanh toán, số thứ tự nghiệp vụ hoặc dữ liệu cần chia sẻ giữa người dùng. Việc đó dễ gây mất dữ liệu, trạng thái không nhất quán và rò rỉ dữ liệu giữa các invocation nếu lập trình viên vô tình giữ tham chiếu dùng chung.

## 3. Giới hạn của dữ liệu cục bộ

### 3.1. Bộ nhớ tiến trình

Bộ nhớ trong tiến trình phù hợp cho dữ liệu tạm thời của một lần gọi: biến tính toán, object đã parse, kết quả trung gian hoặc cache nhỏ. Bộ nhớ này có một số giới hạn:

- Không được chia sẻ giữa các execution environment.
- Không được bảo đảm tồn tại sau khi invocation kết thúc hoặc môi trường bị thu hồi.
- Có thể bị giới hạn theo cấu hình memory của hàm; dùng quá mức có thể khiến invocation lỗi hoặc bị chấm dứt.
- Cache trong bộ nhớ có thể cũ khi một môi trường khác đã cập nhật dữ liệu.
- Dữ liệu nhạy cảm còn lưu trong biến hoặc heap cần được xử lý thận trọng, đặc biệt khi tái sử dụng đối tượng qua nhiều invocation.

### 3.2. Hệ thống tệp tạm

Nhiều nền tảng cung cấp một vùng lưu trữ tạm cho execution environment, thường dùng để tải file, giải nén, xử lý ảnh hoặc tạo artifact trước khi đẩy lên kho lưu trữ bền vững.

Ví dụ, AWS Lambda cung cấp thư mục `/tmp` cho dung lượng lưu trữ tạm có thể cấu hình. Dữ liệu trong vùng này có thể còn tồn tại khi execution environment được tái sử dụng, nhưng có thể bị xóa khi môi trường kết thúc. Các nền tảng khác có đường dẫn, giới hạn dung lượng và vòng đời riêng.

Dùng hệ thống tệp tạm cần lưu ý:

- Dung lượng có giới hạn và phải được cấu hình phù hợp với kích thước file trung gian.
- Nhiều invocation đồng thời có thể chạy ở các môi trường riêng; không giả định chúng cùng nhìn thấy một file.
- File còn sót lại từ invocation trước có thể chiếm dung lượng hoặc làm lẫn dữ liệu nếu tên file không duy nhất.
- Môi trường có thể bị thu hồi bất cứ lúc nào theo vòng đời nền tảng.
- File chứa dữ liệu nhạy cảm cần có quyền truy cập phù hợp và được xóa khi hoàn tất nếu chính sách yêu cầu.
- Khi cần chia sẻ file giữa nhiều hàm hoặc nhiều máy, dùng kho lưu trữ dùng chung được quản lý thay vì dựa vào thư mục tạm.

Ví dụ xử lý file đúng cách: tải object về vùng tạm, kiểm tra kích thước và định dạng, xử lý, ghi kết quả lên object storage, sau đó xóa file tạm. Nếu invocation dừng giữa chừng, file gốc vẫn còn trong kho bền vững để có thể chạy lại.

### 3.3. Mount hệ thống tệp dùng chung

Một số nền tảng cho phép hàm mount hệ thống tệp mạng hoặc dịch vụ file được quản lý. Đây là tài nguyên dùng chung và có thể giữ dữ liệu qua vòng đời execution environment, nhưng phải kiểm tra khả năng hỗ trợ của nhà cung cấp, vùng triển khai, quyền truy cập, throughput, giới hạn kết nối và hành vi khi mất kết nối.

Hệ thống tệp dùng chung vẫn là một dependency bên ngoài. Cần thiết kế xử lý lỗi, khóa file, quyền truy cập đồng thời, sao lưu và khôi phục. Việc mount được một volume không tự động bảo đảm mọi thao tác ghi đều an toàn trước lỗi hoặc xung đột.

## 4. Chọn dịch vụ lưu trữ theo loại dữ liệu

Không có một dịch vụ duy nhất phù hợp cho mọi trạng thái. Nên chọn nơi lưu theo cách dữ liệu được truy cập và yêu cầu nghiệp vụ.

| Loại lưu trữ | Dữ liệu phù hợp | Ưu điểm | Đánh đổi cần xem xét |
|---|---|---|---|
| Cơ sở dữ liệu quan hệ | Đơn hàng, thanh toán, tài khoản, dữ liệu cần quan hệ và transaction | Ràng buộc, transaction, truy vấn SQL và tính nhất quán mạnh theo cấu hình | Cần quản lý kết nối, giới hạn connection, chi phí truy vấn và khả năng mở rộng |
| Cơ sở dữ liệu NoSQL | Hồ sơ, trạng thái theo khóa, metadata và workload có mô hình truy cập rõ | Mở rộng theo thiết kế dịch vụ, truy cập nhanh theo khóa, có thể hỗ trợ conditional write | Cần thiết kế partition key, chỉ mục, giới hạn truy vấn và mô hình nhất quán |
| Object storage | Ảnh, video, tài liệu, file đầu vào/đầu ra, bản sao lưu | Phù hợp file lớn, độ bền cao theo dịch vụ, chi phí lưu trữ theo dung lượng | Không thay thế database cho cập nhật từng trường hoặc truy vấn quan hệ |
| Cache phân tán | Kết quả đọc lặp lại, session tạm, rate limit, dữ liệu có TTL | Giảm độ trễ và tải lên database | Dữ liệu có thể hết hạn hoặc bị loại bỏ; cần xử lý cache miss và dữ liệu cũ |
| Queue hoặc stream | Công việc chờ xử lý, sự kiện cần chuyển giữa các bước | Tách rời producer/consumer, hấp thụ burst, hỗ trợ retry và điều tiết tải | Có thể phát lại hoặc giao trùng; cần idempotency và chính sách retention |
| Workflow/state orchestration | Trạng thái của quy trình nhiều bước, chờ callback hoặc retry dài | Lưu tiến trình, điều phối retry, timeout và nhánh xử lý | Tăng phụ thuộc dịch vụ điều phối, chi phí theo bước/thời gian và giới hạn workflow |

Các ví dụ dịch vụ phổ biến gồm Amazon S3, Amazon DynamoDB, Amazon RDS/Aurora, Amazon SQS, Amazon ElastiCache; Google Cloud Storage, Firestore, Cloud SQL, Pub/Sub; Azure Blob Storage, Cosmos DB, Azure SQL và Service Bus. Tên sản phẩm khác nhau nhưng nguyên tắc lựa chọn tương tự: object cho file, database cho trạng thái có cấu trúc, cache cho dữ liệu có thể tái tạo, queue cho công việc bất đồng bộ và workflow engine cho tiến trình nhiều bước.

Không nên lưu toàn bộ nội dung file lớn trong database nếu object storage phù hợp hơn. Thường có thể lưu file trong bucket, còn database giữ metadata như chủ sở hữu, object key, trạng thái xử lý, checksum và thời điểm tạo.

## 5. Thiết kế trạng thái ngoài hàm

Một thiết kế bền vững cần xác định rõ dữ liệu nào là nguồn sự thật, ai có quyền cập nhật và trạng thái chuyển đổi hợp lệ.

Ví dụ một quy trình xử lý tài liệu có thể có các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> PROCESSING
    PROCESSING --> COMPLETED
    PROCESSING --> RETRY_PENDING
    RETRY_PENDING --> PROCESSING
    PROCESSING --> FAILED
    COMPLETED --> [*]
    FAILED --> [*]
~~~

Bản ghi trạng thái có thể lưu các trường:

~~~json
{
  "jobId": "job-2026-00042",
  "objectKey": "incoming/customer-42/document.pdf",
  "status": "PROCESSING",
  "attempt": 2,
  "createdAt": "2026-11-22T08:00:00Z",
  "updatedAt": "2026-11-22T08:02:10Z",
  "lastErrorCode": null
}
~~~

Ví dụ trên chỉ minh họa cấu trúc dữ liệu. Trong hệ thống thật, cần xác định kiểu dữ liệu, múi giờ, định dạng ID và quy tắc bảo vệ trường nhạy cảm.

Các nguyên tắc thiết kế quan trọng:

1. **Nguồn sự thật rõ ràng:** xác định database hoặc kho dữ liệu nào là nơi ghi nhận trạng thái chính thức. Cache chỉ giữ bản sao có thể tái tạo.
2. **Chuyển trạng thái có điều kiện:** chỉ cho phép chuyển từ trạng thái hợp lệ, ví dụ `RECEIVED` sang `PROCESSING`, tránh hai worker cùng nhận một công việc.
3. **Ghi nhận thời gian và phiên bản:** lưu thời điểm cập nhật, số lần thử và version để phát hiện bản ghi cũ hoặc xung đột.
4. **Lưu khóa tham chiếu:** với file lớn, lưu object key và version thay vì nhúng nội dung file vào bản ghi trạng thái.
5. **Xác định retention:** quy định thời gian giữ trạng thái hoàn tất, dữ liệu tạm, log và bản sao lưu.
6. **Có đường khôi phục:** xác định cách tiếp tục từ trạng thái đã lưu khi hàm timeout hoặc workflow bị gián đoạn.

Với tiến trình kéo dài hơn giới hạn một invocation, chia công việc thành các bước ngắn. Sau mỗi bước, ghi checkpoint vào database hoặc để workflow engine quản lý tiến trình. Invocation tiếp theo đọc checkpoint và tiếp tục. Tránh giữ toàn bộ tiến trình trong bộ nhớ một hàm chạy lâu vì timeout hoặc thu hồi môi trường sẽ làm mất phần tiến độ chưa ghi.

## 6. Đồng thời, retry và tính idempotent

Hệ thống serverless thường mở rộng bằng cách xử lý nhiều invocation đồng thời. Sự kiện có thể được gửi lại khi consumer timeout, không xác nhận thành công hoặc gặp lỗi tạm thời. Vì vậy, một sự kiện có thể được xử lý nhiều hơn một lần.

**Idempotency** là khả năng xử lý lặp một yêu cầu mà không tạo thêm tác dụng nghiệp vụ ngoài kết quả dự kiến. Ví dụ, nhận cùng một sự kiện thanh toán hai lần không được tạo hai lần ghi nhận thanh toán.

Một mẫu xử lý phổ biến:

1. Xác định idempotency key ổn định, như event ID do hệ thống phát sự kiện cấp hoặc mã thao tác nghiệp vụ.
2. Tạo bản ghi xử lý với ràng buộc duy nhất hoặc conditional write.
3. Nếu key đã tồn tại và đã hoàn tất, trả lại kết quả đã lưu hoặc bỏ qua tác dụng lặp.
4. Nếu key đang được xử lý, áp dụng quy tắc chờ, retry hoặc kiểm tra lease/timeout.
5. Ghi kết quả và trạng thái hoàn tất theo cách nhất quán.

Ví dụ SQL minh họa:

~~~sql
CREATE TABLE processed_events (
    event_id       VARCHAR(128) PRIMARY KEY,
    status         VARCHAR(24) NOT NULL,
    result_ref     VARCHAR(512),
    created_at     TIMESTAMP NOT NULL,
    completed_at   TIMESTAMP
);
~~~

Khóa chính `event_id` ngăn việc tạo hai bản ghi cho cùng một sự kiện. Tuy nhiên, chỉ có bảng chống trùng chưa đủ: cập nhật dữ liệu nghiệp vụ và đánh dấu sự kiện hoàn tất cần được phối hợp bằng transaction hoặc mẫu thiết kế phù hợp. Nếu gọi một hệ thống thanh toán bên ngoài, cần truyền idempotency key sang hệ thống đó khi API hỗ trợ.

Khi nhiều invocation cập nhật cùng một bản ghi, có thể dùng:

- Transaction để nhóm nhiều thay đổi phải thành công hoặc thất bại cùng nhau.
- Conditional update hoặc compare-and-swap dựa trên version.
- Unique constraint để ngăn bản ghi trùng.
- Lease có thời hạn để worker nhận quyền xử lý tạm thời và có thể thu hồi khi worker chết.
- Distributed lock chỉ khi thật sự cần; khóa phải có timeout, fencing token hoặc cơ chế chống worker cũ tiếp tục ghi sau khi mất lease.

Không dùng mutex trong bộ nhớ của một execution environment để điều phối nhiều invocation trên toàn hệ thống. Mutex đó chỉ có phạm vi của một tiến trình và không bảo vệ dữ liệu trước các môi trường khác.

## 7. Ví dụ thực tế: nhận và xử lý file tải lên

Giả sử khách hàng tải hóa đơn lên một ứng dụng serverless. Hệ thống cần lưu file, kiểm tra nội dung, trích xuất dữ liệu và cập nhật trạng thái xử lý.

~~~mermaid
flowchart TD
    A["Người dùng tải file"] --> B["Object storage: bucket đầu vào"]
    B --> C["Sự kiện tạo object"]
    C --> D["Queue hoặc event bus"]
    D --> E["Hàm xử lý file"]
    E --> F["Đọc file vào vùng tạm"]
    E --> G["Database: trạng thái và metadata"]
    F --> H["Kiểm tra / trích xuất"]
    H --> I["Object storage: kết quả"]
    H --> G
    G --> J["API đọc trạng thái"]
    J --> K["Người dùng xem kết quả"]
~~~

### 7.1. Tiếp nhận file

API xác thực người dùng và tạo một mã công việc duy nhất. File được tải lên bucket bằng object key có thể truy vết, ví dụ:

`incoming/customer-42/job-2026-00042/invoice.pdf`

Database lưu metadata ban đầu:

- `jobId` và chủ sở hữu.
- Object key, version hoặc checksum của file.
- Trạng thái `RECEIVED`.
- Thời điểm tạo và chính sách retention.
- Thông tin tương quan để truy vết request.

Không nên dùng tên file do người dùng gửi làm đường dẫn tùy ý trên hệ thống tệp. Hãy tạo object key theo quy tắc của ứng dụng, kiểm tra quyền sở hữu và xác thực nội dung file.

### 7.2. Xử lý bất đồng bộ

Sự kiện object được đưa vào queue hoặc event bus. Hàm consumer nhận thông điệp, lấy `jobId`, xác nhận trạng thái và dùng idempotency key để tránh xử lý lặp.

Hàm tải file vào vùng tạm, kiểm tra kích thước, loại nội dung và checksum, sau đó thực hiện trích xuất. Kết quả được lưu thành object mới, ví dụ:

`processed/customer-42/job-2026-00042/result.json`

Database cập nhật trạng thái `COMPLETED`, đường dẫn kết quả và thời điểm hoàn tất. API truy vấn database để trả trạng thái cho người dùng; API không cần dựa vào bộ nhớ của hàm xử lý.

### 7.3. Xử lý lỗi và retry

Nếu hàm timeout sau khi đã ghi file kết quả nhưng trước khi cập nhật database, lần retry có thể chạy lại. Cần thiết kế để thao tác lặp không tạo nhiều kết quả hoặc làm trạng thái sai.

Có thể dùng object key kết quả xác định từ `jobId`, ghi có điều kiện hoặc lưu version/checksum để nhận biết kết quả đã tồn tại. Khi cập nhật database, dùng transaction hoặc conditional update để chỉ chuyển trạng thái nếu công việc đang ở trạng thái phù hợp.

Nếu lỗi không thể tự phục hồi, chuyển thông điệp sang dead-letter queue sau số lần thử đã định, lưu mã lỗi và cho phép người vận hành phát lại sau khi sửa nguyên nhân. Không đánh dấu hoàn tất chỉ vì hàm đã nhận được sự kiện.

### 7.4. Kiểm tra kết quả

Người vận hành cần xác minh cả dữ liệu và luồng sự kiện:

- Object đầu vào tồn tại, có version/checksum đúng và quyền truy cập phù hợp.
- Thông điệp đã được xử lý hoặc có lý do rõ ràng trong queue/dead-letter queue.
- Database chuyển trạng thái đúng theo luồng hợp lệ.
- Object kết quả tồn tại, đọc được và gắn với đúng job.
- Retry cùng một event không tạo thêm tác dụng nghiệp vụ.
- Người dùng chỉ truy cập được dữ liệu thuộc quyền của họ.

## 8. Nhất quán giữa database, object storage và queue

Một quy trình có thể ghi vào nhiều dịch vụ: tạo bản ghi database, tải file lên object storage và phát thông điệp vào queue. Những thao tác này thường không nằm trong một transaction phân tán duy nhất. Nếu hàm dừng giữa các bước, hệ thống có thể rơi vào trạng thái một phần.

Ví dụ:

- File đã tải lên nhưng database chưa có metadata.
- Database đã đánh dấu `PROCESSING` nhưng thông điệp chưa được gửi.
- Thông điệp đã được gửi nhưng transaction database bị rollback.
- Kết quả đã được tạo nhưng trạng thái vẫn là `PROCESSING`.

Một số mẫu thiết kế giúp giảm rủi ro:

- **Outbox pattern:** ghi thay đổi nghiệp vụ và bản ghi outbox trong cùng transaction database; một publisher riêng đọc outbox rồi gửi thông điệp. Publisher có thể gửi lặp nên consumer vẫn cần idempotency.
- **Saga:** chia quy trình thành các bước có hành động bù trừ khi bước sau thất bại, thay vì giả định có một transaction bao trùm mọi dịch vụ.
- **Reconciliation job:** định kỳ tìm bản ghi quá hạn hoặc object mồ côi, so sánh trạng thái giữa các dịch vụ và sửa theo quy tắc nghiệp vụ.
- **Checkpoint:** lưu tiến độ sau mỗi bước để retry tiếp tục từ phần chưa hoàn tất.
- **Dead-letter queue:** cô lập thông điệp lỗi kéo dài, hỗ trợ điều tra và phát lại có kiểm soát.

Cần xác định rõ thứ tự ghi, trạng thái trung gian, điều kiện retry và cách bù trừ. Không nên cập nhật trạng thái `COMPLETED` trước khi kết quả bền vững đã được ghi và xác minh.

## 9. Bảo mật và quản trị vòng đời dữ liệu

Dữ liệu được đưa ra ngoài hàm cần có chính sách bảo vệ nhất quán:

- **Quyền tối thiểu:** execution role chỉ được đọc/ghi đúng bucket, bảng, queue hoặc secret mà hàm cần.
- **Mã hóa:** bật mã hóa khi truyền và khi lưu; quản lý khóa theo yêu cầu của tổ chức.
- **Phân tách tenant:** kiểm tra quyền sở hữu ở API và lớp truy cập dữ liệu; không tin một object key do client tự gửi.
- **Secret:** lưu thông tin xác thực trong secret manager hoặc dịch vụ cấu hình an toàn, không nhúng vào image, biến môi trường công khai hoặc log.
- **Retention và xóa:** quy định thời hạn lưu file đầu vào, kết quả, trạng thái, log và bản sao lưu; thực hiện xóa theo yêu cầu nghiệp vụ và pháp lý.
- **Sao lưu và khôi phục:** cấu hình backup, versioning hoặc replication phù hợp; định kỳ thử khôi phục để xác nhận RPO và RTO.
- **Audit:** ghi lại ai hoặc workload nào đã đọc, ghi, xóa dữ liệu và khi nào, theo mức chi tiết cần thiết.
- **Không ghi dữ liệu nhạy cảm vào log:** log ID tương quan và mã lỗi; tránh token, mật khẩu, dữ liệu cá nhân hoặc nội dung file.

Dữ liệu tạm cũng cần được xem là dữ liệu có thể nhạy cảm. File trong `/tmp` không trở thành an toàn chỉ vì nó nằm trong môi trường serverless. Hãy hạn chế quyền, tránh dùng tên file đoán được giữa các invocation và dọn dẹp dữ liệu sau khi xử lý.

## 10. Hiệu năng, khả năng mở rộng và chi phí

Lưu trạng thái bên ngoài giúp nhiều invocation cùng truy cập dữ liệu, nhưng cũng tạo thêm độ trễ và chi phí. Cần thiết kế đường truy cập phù hợp:

- Khởi tạo và tái sử dụng connection/client trong môi trường ấm khi SDK hỗ trợ, nhưng xử lý trường hợp kết nối đã hết hạn hoặc bị đóng.
- Giới hạn số kết nối đồng thời đến database; khi hàm scale out nhanh, tổng connection có thể vượt khả năng database.
- Dùng connection pooler hoặc proxy được quản lý nếu phù hợp với nền tảng và engine.
- Chọn partition key và index theo mẫu truy vấn thực tế để tránh hotspot.
- Dùng cache có TTL cho dữ liệu đọc nhiều và có thể tái tạo; luôn có đường xử lý cache miss.
- Đưa công việc nặng hoặc kéo dài sang queue để điều tiết concurrency và tránh giữ invocation chờ.
- Dùng object storage cho file lớn, chỉ truyền object key hoặc URL có thời hạn giữa các bước.
- Theo dõi số lần gọi database, kích thước object, thời gian lưu, số thông điệp, retry và chi phí egress.

Autoscaling của hàm có thể nhanh hơn khả năng mở rộng của database phía sau. Đặt concurrency hoặc giới hạn số invocation đồng thời, dùng queue để hấp thụ burst và theo dõi connection saturation. Tăng số hàm mà không tăng khả năng phục vụ của dependency có thể làm sự cố lan rộng.

## 11. Xác minh thiết kế và kiểm thử lỗi

Trước khi phát hành, cần kiểm tra cả trường hợp bình thường và tình huống môi trường bị thay thế:

1. Gọi hàm nhiều lần trên các invocation riêng biệt và xác nhận mọi lần đều đọc được cùng trạng thái từ kho bên ngoài.
2. Mô phỏng cold start hoặc môi trường mới; xác nhận logic không phụ thuộc biến toàn cục hoặc file tạm còn sót.
3. Gửi hai sự kiện cùng lúc cho một job; xác nhận chỉ một lần chuyển trạng thái hợp lệ được thực hiện.
4. Gửi lại cùng một event ID; xác nhận idempotency ngăn tác dụng nghiệp vụ trùng.
5. Dừng xử lý giữa hai bước ghi; xác nhận retry hoặc reconciliation đưa quy trình về trạng thái hợp lệ.
6. Làm database chậm hoặc không khả dụng; xác nhận timeout, retry có giới hạn và backoff không tạo vòng lặp vô hạn.
7. Gửi file vượt dung lượng hoặc sai định dạng; xác nhận hàm từ chối an toàn và không để lại trạng thái xử lý mồ côi.
8. Thử khôi phục dữ liệu từ backup hoặc version; xác nhận ứng dụng có thể đọc và tiếp tục xử lý.

Các chỉ số cần theo dõi gồm invocation error, timeout, concurrency, duration, memory used, số lần retry, tuổi thông điệp queue, dead-letter count, database connection, query latency, object storage error và tỷ lệ công việc ở trạng thái quá hạn.

Mỗi log nên có correlation ID hoặc job ID để liên kết request, event, invocation và bản ghi dữ liệu. Không cần ghi toàn bộ payload nếu payload chứa thông tin nhạy cảm.

## 12. Checklist quản lý trạng thái và dữ liệu

- [ ] Trạng thái nghiệp vụ có nguồn sự thật ở database, object storage hoặc workflow service phù hợp.
- [ ] Biến toàn cục chỉ giữ client hoặc cache có thể tái tạo; không lưu dữ liệu nghiệp vụ duy nhất.
- [ ] Bộ nhớ và file cục bộ chỉ phục vụ xử lý tạm thời, có giới hạn dung lượng và quy tắc dọn dẹp.
- [ ] File lớn được lưu ở object storage; database giữ metadata và tham chiếu cần thiết.
- [ ] Đã chọn retention, versioning, backup và quy trình khôi phục cho từng loại dữ liệu.
- [ ] Mỗi sự kiện có idempotency key; thao tác ghi được bảo vệ bằng transaction, conditional write hoặc unique constraint phù hợp.
- [ ] Đã xử lý đồng thời, retry, timeout, thông điệp trùng và dead-letter queue.
- [ ] Các bước ghi qua nhiều dịch vụ có checkpoint, outbox, saga hoặc cơ chế reconciliation phù hợp.
- [ ] Quyền truy cập theo nguyên tắc tối thiểu; dữ liệu được mã hóa và không rò rỉ qua log.
- [ ] Đã giới hạn concurrency và kết nối để bảo vệ database, queue và dịch vụ phụ thuộc.
- [ ] Đã kiểm thử cold start, môi trường mới, lỗi giữa chừng, retry và khôi phục dữ liệu.

Quản lý trạng thái ngoài hàm giúp ứng dụng serverless hoạt động đúng khi invocation chạy trên nhiều môi trường, bị retry hoặc bị thu hồi. Bộ nhớ và hệ thống tệp cục bộ vẫn hữu ích cho tính toán và dữ liệu trung gian, nhưng trạng thái nghiệp vụ cần được ghi vào dịch vụ có vòng đời và cơ chế bảo vệ rõ ràng. Khi kết hợp lưu trữ phù hợp, idempotency, kiểm soát đồng thời và quy trình khôi phục, ứng dụng có thể mở rộng mà vẫn duy trì tính nhất quán và độ bền dữ liệu.
