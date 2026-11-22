# Xử lý Timer trigger, Storage Queue trigger và Blob trigger

Azure Functions có thể chạy một Java function theo lịch, khi một message xuất hiện trong queue hoặc khi một blob được tạo/cập nhật. Ba trigger này giải quyết các kiểu công việc khác nhau: Timer dành cho tác vụ định kỳ; Storage Queue dành cho xử lý bất đồng bộ và tách rời producer/consumer; Blob dành cho xử lý dữ liệu khi file được đưa vào kho lưu trữ.

Khi kết hợp chúng, một ứng dụng có thể tự động thực hiện tác vụ theo lịch, tiêu thụ công việc từ hàng đợi và xử lý file mới mà không cần một tiến trình Java luôn chạy. Tuy nhiên, mỗi trigger có semantics về lịch chạy, retry, thứ tự, concurrency và lưu trạng thái khác nhau. Thiết kế đúng phải tính đến việc một function có thể được gọi lại, chạy đồng thời trên nhiều instance hoặc thất bại sau khi đã tạo side effect.

Trong module **CLOUD_SERVERLESS**, người học xây dựng và triển khai Java function được kích hoạt bởi HTTP, message hoặc event, đồng thời xử lý trạng thái, quyền truy cập, retry, idempotency, mở rộng và chi phí. Bài này tập trung vào ba trigger của Azure Functions và cách vận hành chúng trong một ứng dụng Java.

## 1. Tổng quan ba loại trigger

| Trigger | Sự kiện kích hoạt | Công việc phù hợp | Đặc điểm chính |
|---|---|---|---|
| Timer trigger | Đến thời điểm theo lịch NCRONTAB | Báo cáo định kỳ, cleanup, đồng bộ dữ liệu, tác vụ bảo trì | Host điều phối lịch; cần storage để quản lý lock và schedule status |
| Storage Queue trigger | Có message trong Azure Queue Storage | Xử lý đơn hàng, gửi email, xử lý tác vụ nền, tích hợp hệ thống | Consumer nhận message, xử lý rồi xóa; lỗi có thể dẫn đến giao lại và poison queue |
| Blob trigger | Blob được tạo hoặc cập nhật trong container | Resize ảnh, phân tích file, nhập dữ liệu, tạo thumbnail | Theo dõi thay đổi blob bằng polling hoặc cơ chế event-based tùy cấu hình |

Cần phân biệt trigger với binding:

- **Trigger** quyết định khi nào function được gọi và cung cấp dữ liệu kích hoạt.
- **Input binding** giúp function đọc dữ liệu từ một dịch vụ mà không phải tự viết toàn bộ mã kết nối.
- **Output binding** giúp function ghi dữ liệu ra dịch vụ đích.
- **Azure SDK** cho phép kiểm soát chi tiết hơn về query, streaming, transaction, metadata và retry.

Một function có đúng một trigger. Function có thể có thêm input/output bindings hoặc tự dùng SDK để tương tác với nhiều dịch vụ. Trigger không tự động bảo đảm nghiệp vụ được thực hiện đúng một lần; consumer vẫn cần idempotency và xử lý lỗi.

## 2. Java programming model và cách khai báo trigger

Trong Java, function thường được khai báo bằng annotation như FunctionName, TimerTrigger, QueueTrigger và BlobTrigger. Azure Functions host quản lý trigger, theo dõi nguồn sự kiện và gọi method Java với các tham số đã bind.

Một method function thường nhận:

- Tham số trigger chứa timer information, queue message hoặc blob content.
- Các tham số binding khác nếu function cần thêm dữ liệu.
- ExecutionContext để ghi log và lấy context của invocation.

Ví dụ cấu trúc tổng quát:

~~~java
import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.annotation.FunctionName;

public class ExampleFunction {
    @FunctionName("Example")
    public void run(
            final ExecutionContext context) {
        context.getLogger().info("Function invoked");
    }
}
~~~

Tên function là định danh được host sử dụng. Không nên coi tên method Java là tên trigger hoặc tên queue; các giá trị này được khai báo trong annotation và cấu hình ứng dụng.

Các ví dụ trong bài dùng package annotation của Azure Functions Java library. Dependency, phiên bản Azure Functions Maven plugin, Java runtime và extension bundle cần được đồng bộ theo hướng dẫn của phiên bản Azure Functions đang triển khai.

## 3. Timer trigger: chạy function theo lịch

Timer trigger gọi function theo biểu thức lịch NCRONTAB. Nó phù hợp với tác vụ có thời điểm chạy xác định, ví dụ:

- Tổng hợp số liệu mỗi giờ.
- Tạo báo cáo vào đầu ngày.
- Dọn dữ liệu tạm hoặc bản ghi đã hết hạn.
- Đồng bộ dữ liệu định kỳ từ hệ thống ngoài.
- Kiểm tra một điều kiện nghiệp vụ theo chu kỳ.

Ví dụ Java chạy mỗi năm phút:

~~~java
import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.TimerTrigger;

public class MaintenanceFunction {
    @FunctionName("MaintenanceTimer")
    public void run(
            @TimerTrigger(
                name = "timerInfo",
                schedule = "0 */5 * * * *"
            ) String timerInfo,
            final ExecutionContext context) {

        context.getLogger().info(
                "Maintenance timer fired. Timer info: " + timerInfo);

        performMaintenance();
    }

    private void performMaintenance() {
        // Gọi service nghiệp vụ; thao tác cần an toàn khi được chạy lại.
    }
}
~~~

Biểu thức trên có nghĩa chạy tại giây 0 của mỗi phút chia hết cho 5. Timer schedule trong Azure Functions dùng NCRONTAB sáu trường theo thứ tự:

| Trường | Phạm vi thường gặp | Ví dụ |
|---|---|---|
| Seconds | 0–59 | 0 |
| Minutes | 0–59 | */5 |
| Hours | 0–23 | 8 |
| Day | 1–31 | * |
| Month | 1–12 | * |
| Day of week | 0–6 hoặc tên ngày tùy parser | * |

Ví dụ:

| Biểu thức | Ý nghĩa |
|---|---|
| 0 */5 * * * * | Mỗi 5 phút, tại giây 0 |
| 0 0 * * * * | Mỗi giờ, tại phút 0 |
| 0 30 8 * * * | Mỗi ngày lúc 08:30 |
| 0 0 0 * * 1 | Thứ Hai hàng tuần lúc 00:00 |
| 0 0 9 1 * * | Ngày đầu mỗi tháng lúc 09:00 |

Hãy kiểm tra biểu thức bằng parser NCRONTAB hoặc công cụ phù hợp trước khi deploy. Sáu trường của Azure Functions khác cron năm trường thường gặp trên Linux; sao chép lịch cron năm trường có thể tạo lịch sai.

### Đưa lịch vào application setting

Không nên hardcode lịch production nếu lịch có thể thay đổi giữa môi trường. Có thể tham chiếu application setting bằng dấu phần trăm:

~~~java
@TimerTrigger(
    name = "timerInfo",
    schedule = "%MaintenanceSchedule%"
) String timerInfo
~~~

Trong local.settings.json dùng cho phát triển cục bộ:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "java",
    "MaintenanceSchedule": "0 */5 * * * *"
  }
}
~~~

Local settings chỉ phục vụ môi trường phát triển và không nên commit connection string hoặc secret thật vào repository. Trên Azure, cấu hình tương ứng nằm trong Application Settings hoặc cơ chế cấu hình/secret được tổ chức sử dụng.

### Time zone và lịch chạy

Timer schedule mặc định được diễn giải theo UTC. Điều này giúp lịch không phụ thuộc vào nơi đặt host, nhưng có thể khác giờ địa phương khi triển khai ứng dụng ở nhiều Region.

Nếu nghiệp vụ yêu cầu giờ địa phương, kiểm tra hỗ trợ WEBSITE_TIME_ZONE theo hệ điều hành và hosting plan đang dùng. Khả năng hỗ trợ khác nhau giữa Windows và Linux, đặc biệt ở Consumption plan. Với lịch quan trọng về tài chính hoặc SLA, cách an toàn là lưu và tính thời điểm theo UTC, đồng thời xử lý rõ quy tắc chuyển giờ mùa hè nếu nghiệp vụ có dùng múi giờ đó.

### Singleton lock và schedule monitoring

Timer trigger sử dụng cơ chế lock dựa trên storage để bảo đảm chỉ một instance của function xử lý lịch tại một thời điểm trong ứng dụng được scale out. Host storage cũng được dùng để theo dõi trạng thái lịch, tránh việc mỗi instance tự chạy cùng một lịch.

Vì vậy:

- Cấu hình storage cho host phải sẵn sàng và có quyền truy cập phù hợp.
- Không xóa hoặc thay đổi tùy tiện các dữ liệu nội bộ mà host dùng để quản lý timer.
- Khi scale nhiều instance, không tự tạo một timer riêng trong mỗi instance để thay thế Timer trigger.
- Cần quan sát trạng thái lịch và log của host nếu một lần chạy bị trễ hoặc bỏ lỡ.

Timer trigger không phải durable workflow engine. Nếu tác vụ kéo dài, có nhiều bước, cần chờ callback hoặc cần retry phức tạp, hãy để Timer trigger khởi tạo một workflow hoặc enqueue công việc thay vì giữ một invocation mở quá lâu.

### runOnStartup và useMonitor

TimerTrigger có các tùy chọn như runOnStartup và useMonitor tùy phiên bản binding/runtime. runOnStartup có thể khiến function chạy khi host khởi động hoặc restart, ngoài thời điểm lịch thông thường. Trong production, không nên bật tùy chọn này nếu không có lý do rõ ràng, vì scale, deploy hoặc restart có thể tạo thêm lần chạy ngoài dự kiến.

useMonitor điều khiển việc lưu/giám sát lịch. Với lịch quan trọng, cần hiểu default theo interval và cấu hình cụ thể của runtime. Không tắt schedule monitoring chỉ để giảm storage activity nếu điều đó làm tăng nguy cơ bỏ lỡ hoặc chạy sai lịch.

## 4. Storage Queue trigger: xử lý message bất đồng bộ

Azure Queue Storage là hàng đợi message đơn giản để tách producer khỏi consumer. Producer ghi message vào queue; Azure Functions host theo dõi queue và gọi function khi có message để xử lý.

Queue trigger phù hợp khi:

- API cần phản hồi nhanh nhưng nghiệp vụ có thể hoàn tất sau.
- Nhiều công việc độc lập cần được phân phối cho consumer.
- Muốn hấp thụ burst bằng backlog thay vì đẩy toàn bộ tải trực tiếp vào database.
- Cần retry message khi dịch vụ phụ trợ tạm thời lỗi.
- Muốn tách vòng đời producer và worker.

Ví dụ Java nhận message từ queue:

~~~java
import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.QueueTrigger;

public class OrderQueueFunction {
    @FunctionName("ProcessOrderMessage")
    public void run(
            @QueueTrigger(
                name = "message",
                queueName = "orders-in",
                connection = "AzureWebJobsStorage"
            ) String message,
            final ExecutionContext context) {

        context.getLogger().info("Received order message");
        processOrderMessage(message);
    }

    private void processOrderMessage(String message) {
        // Parse, validate, gọi service nghiệp vụ và commit kết quả.
    }
}
~~~

Thuộc tính connection tham chiếu đến cấu hình kết nối trong ứng dụng, không phải chuỗi connection được viết trực tiếp trong annotation. Tên queue phải tuân thủ quy tắc đặt tên của Azure Queue Storage, thường dùng chữ thường, số và dấu gạch nối.

### Message lifecycle và acknowledgement

Với Azure Queue Storage, host lấy message từ queue và message trở nên tạm thời không hiển thị với consumer khác trong khoảng visibility timeout. Khi function xử lý thành công, host xóa message khỏi queue. Nếu function thất bại hoặc không hoàn tất theo cơ chế host, message có thể xuất hiện lại sau visibility timeout để được giao lại.

Do đó, queue trigger có semantics giao nhận ít nhất một lần trong các tình huống có thể xảy ra. Một message có thể được xử lý lại nếu:

- Function đã commit database nhưng host chưa xóa message.
- Invocation timeout hoặc process bị dừng.
- Mạng lỗi khi host xác nhận xử lý.
- Message visibility hết hạn trong khi lần xử lý trước vẫn còn chạy.

Không dựa vào giả định mỗi message chỉ được gọi một lần. Hãy thiết kế consumer idempotent và lưu event/message ID để nhận biết lần xử lý lặp.

### Dequeue count và poison queue

Mỗi lần message được lấy ra xử lý, dequeue count tăng. Nếu function liên tục thất bại, host sẽ thử lại message theo cơ chế queue trigger. Sau khi vượt maxDequeueCount, message được chuyển sang poison queue để không tiếp tục chặn luồng chính.

Với queue tên orders-in, poison queue mặc định có tên orders-in-poison. Đây là nơi điều tra message không thể xử lý bình thường. Không nên tự động xóa poison message mà chưa lưu thông tin cần thiết và xác định nguyên nhân.

Có thể cấu hình hành vi queue trong host.json:

~~~json
{
  "version": "2.0",
  "extensions": {
    "queues": {
      "batchSize": 16,
      "newBatchThreshold": 8,
      "maxDequeueCount": 5,
      "visibilityTimeout": "00:00:30"
    }
  }
}
~~~

Ý nghĩa:

- batchSize: số message host lấy trong một batch theo cơ chế queue listener.
- newBatchThreshold: ngưỡng để host lấy batch tiếp theo khi số message đang xử lý giảm xuống.
- maxDequeueCount: số lần dequeue tối đa trước khi message được chuyển sang poison queue.
- visibilityTimeout: thời gian chờ trước khi message thất bại được hiển thị lại để retry.

Các giá trị trên là ví dụ cấu hình, không phải con số tối ưu cho mọi workload. Giá trị mặc định và giới hạn có thể phụ thuộc extension version. Hãy xác nhận với Azure Storage Queues extension đang dùng.

### Concurrency và backpressure

batchSize và newBatchThreshold ảnh hưởng số message được xử lý đồng thời trên mỗi host instance. Khi scale out, tổng concurrency có thể tăng theo số instance. Vì vậy, một cấu hình batch nhỏ trên mỗi instance vẫn có thể tạo concurrency lớn ở toàn ứng dụng nếu host scale nhiều instance.

Cần phối hợp:

- Giới hạn concurrency của function hoặc hosting plan nếu có.
- Batch size và số instance tối đa.
- Connection pool và giới hạn database.
- Rate limit của API downstream.
- Thời gian xử lý và visibility timeout.
- Backlog, tuổi message cũ nhất và tỷ lệ retry.

Nếu database chỉ chịu được 30 tác vụ đồng thời, không nên để queue consumer mở hàng trăm invocation cùng lúc. Tăng concurrency chỉ làm backlog giảm nhanh hơn khi dependency chịu được tải đó; nếu không, nó có thể làm tỷ lệ timeout và retry tăng.

## 5. Blob trigger: xử lý blob mới hoặc được cập nhật

Azure Blob Storage lưu object trong container. Blob trigger gọi function khi một blob phù hợp với path được tạo hoặc cập nhật. Đây là lựa chọn tự nhiên cho pipeline xử lý file như:

- Resize ảnh hoặc tạo thumbnail.
- Quét file upload để kiểm tra virus.
- Trích xuất văn bản từ PDF.
- Chuyển đổi CSV/JSON thành dữ liệu chuẩn.
- Tạo preview hoặc metadata cho video/tài liệu.
- Nhập dữ liệu vào database hoặc data lake.

Ví dụ Java nhận nội dung blob dạng binary:

~~~java
import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.annotation.BindingName;
import com.microsoft.azure.functions.annotation.BlobTrigger;
import com.microsoft.azure.functions.annotation.FunctionName;

public class ImageBlobFunction {
    @FunctionName("ProcessUploadedImage")
    public void run(
            @BlobTrigger(
                name = "content",
                path = "incoming-images/{name}",
                dataType = "binary",
                connection = "AzureWebJobsStorage"
            ) byte[] content,
            @BindingName("name") String blobName,
            final ExecutionContext context) {

        context.getLogger().info("Processing blob: " + blobName);
        processImage(blobName, content);
    }

    private void processImage(String name, byte[] content) {
        // Validate type/size, xử lý và ghi kết quả.
    }
}
~~~

Path incoming-images/{name} nghĩa là theo dõi blob trong container incoming-images; phần {name} được bind vào tham số có BindingName tương ứng. Với file binary, byte[] thuận tiện cho file nhỏ nhưng sẽ đọc toàn bộ nội dung vào memory. Với file lớn, không nên mặc định tải toàn bộ blob vào byte array.

### Blob path và binding data

Path có thể chứa tên container và pattern để lấy tên blob hoặc một phần đường dẫn. Ví dụ:

| Path | Ý nghĩa |
|---|---|
| incoming/{name} | Mọi blob trong container incoming |
| incoming/images/{name} | Blob trong thư mục logic images của container incoming |
| incoming/{name}.csv | Blob có tên kết thúc bằng .csv theo pattern được binding hỗ trợ |

Blob Storage dùng tên blob có thể chứa dấu / để mô phỏng thư mục; đó không phải thư mục vật lý như filesystem. Hãy kiểm tra cách pattern binding xử lý đường dẫn lồng nhau và tên có ký tự đặc biệt.

### Polling và event-based detection

Blob trigger có thể phát hiện thay đổi bằng cơ chế scan/polling hoặc dựa trên Event Grid tùy cấu hình, extension và hosting environment.

- **Polling:** host kiểm tra thay đổi trong storage và dùng thông tin theo dõi/receipt để xác định blob cần xử lý. Cách này có thể có độ trễ phát hiện tùy cơ chế scan và tải.
- **Event Grid-based:** Storage phát sự kiện khi blob được tạo hoặc cập nhật; Event Grid chuyển sự kiện đến integration/trigger. Cách này thường giảm độ trễ phát hiện nhưng cần cấu hình event subscription, quyền và endpoint phù hợp.

Không nên giả định mọi Blob trigger mặc định dùng Event Grid. Kiểm tra tài liệu của extension/runtime và cấu hình source đang triển khai. Nếu cần phản ứng gần thời gian thực, xác nhận event subscription hoạt động và kiểm thử cả việc retry/delivery của Event Grid.

### Blob receipts và xử lý lại

Host dùng receipt hoặc metadata theo dõi để biết blob nào đã được xử lý. Khi blob được cập nhật, một phiên bản/ETag mới có thể khiến trigger xem đó là thay đổi cần xử lý lại. Receipt không thay thế idempotency ở tầng nghiệp vụ: function vẫn có thể thực hiện side effect rồi lỗi trước khi host ghi nhận thành công.

Nếu xử lý blob có thể được kích hoạt lại, hãy lưu ETag, version ID hoặc một operation key ổn định cùng trạng thái nghiệp vụ. Trước khi ghi kết quả, kiểm tra liệu version đó đã được xử lý chưa.

### Tránh đọc toàn bộ file lớn vào heap

Ví dụ byte[] ở trên phù hợp file nhỏ. Với file lớn, dùng Azure Storage SDK để mở stream hoặc tải theo cách có kiểm soát. Cách này cho phép giới hạn memory, xử lý từng phần và tránh OutOfMemoryError khi nhiều blob được xử lý đồng thời.

Mô hình tham khảo:

~~~java
try (InputStream input = openBlobStream(blobName)) {
    processInChunks(input);
}
~~~

Các hàm openBlobStream và processInChunks là abstraction của ứng dụng. Khi dùng SDK, cần xác định rõ quyền đọc container, timeout, retry, cách đóng stream và cách xử lý blob bị xóa trong lúc đang chạy.

### Poison blob và lỗi lặp

Blob trigger có thể retry khi function thất bại. Với cơ chế polling của Blob trigger, runtime có thể ghi thông tin blob thất bại vào queue poison chuyên dụng sau ngưỡng retry; tên queue thường gặp là webjobs-blobtrigger-poison. Hành vi chi tiết và cấu hình phụ thuộc trigger source, extension và phiên bản runtime. Khi dùng Event Grid, cần xem thêm retry và dead-letter của Event Grid subscription.

Không coi việc blob xuất hiện trong poison queue là hoàn tất xử lý. Cần giữ thông tin blob path, ETag/version, thời điểm, exception đã lọc và function version để điều tra. Nếu sửa file hoặc code rồi chạy lại, hãy kiểm soát version được replay và tránh tạo kết quả trùng.

## 6. So sánh Timer, Queue và Blob trigger

| Tiêu chí | Timer | Storage Queue | Blob |
|---|---|---|---|
| Nguồn kích hoạt | Lịch thời gian | Message trong queue | Blob được tạo/cập nhật |
| Mô hình tải | Theo lịch | Theo backlog và tốc độ message | Theo tốc độ upload/thay đổi file |
| Dữ liệu đầu vào | Timer information và schedule status | Message body, metadata | Blob content, tên và metadata |
| Retry | Theo chính sách runtime/function; cần thiết kế rõ | Giao lại theo visibility/dequeue count, poison queue | Theo trigger source/runtime; có thể có poison handling |
| Thứ tự | Theo thời điểm lịch, không phải thứ tự event nghiệp vụ | Không nên giả định strict FIFO | Không bảo đảm thứ tự xử lý giữa nhiều blob |
| Idempotency key | Schedule occurrence/business date | Message ID hoặc event ID | Blob URI + ETag/version |
| Lưu trữ trạng thái | Host storage và kho nghiệp vụ | Queue và database nghiệp vụ | Blob storage, receipts và database nghiệp vụ |
| Trường hợp điển hình | Cleanup, báo cáo, reconciliation | Tác vụ nền và decoupling | Xử lý file và data ingestion |

Ba trigger có thể kết hợp trong một pipeline:

1. Người dùng upload file vào container incoming.
2. Blob trigger xác thực metadata và ghi một công việc vào queue.
3. Queue trigger xử lý file, trích xuất dữ liệu và cập nhật database.
4. Timer trigger chạy định kỳ để tìm công việc bị kẹt hoặc đối soát trạng thái.
5. Khi có message không xử lý được, poison queue giữ lại để điều tra và redrive.

Cách kết hợp này tách phát hiện file, điều phối công việc và đối soát định kỳ thành các bước riêng. Mỗi function có thể scale theo đặc tính trigger của nó.

## 7. Idempotency và trạng thái nghiệp vụ

Cả ba trigger đều có thể dẫn đến việc một tác vụ được chạy lại hoặc chạy chồng lấn. Idempotency nghĩa là thực hiện lại cùng một thao tác với cùng định danh không tạo thêm hiệu ứng nghiệp vụ ngoài dự kiến.

### Timer trigger

Dùng một khóa đại diện cho lần chạy nghiệp vụ, chẳng hạn report-date hoặc schedule-occurrence. Trước khi tạo báo cáo, ghi nhận khóa đó trong database với unique constraint. Nếu lần chạy trước đã hoàn tất, invocation sau có thể bỏ qua hoặc cập nhật theo chính sách.

Không chỉ dùng thời gian hiện tại làm key vì hai invocation có thể chạy ở hai giây khác nhau cho cùng một kỳ báo cáo. Hãy chuẩn hóa business period, ví dụ ngày báo cáo theo UTC hoặc timezone nghiệp vụ.

### Queue trigger

Message nên chứa messageId/eventId hoặc business operation ID. Lưu trạng thái đã xử lý trong database và cập nhật trạng thái cùng side effect trong một transaction nếu có thể. Nếu gọi API ngoài, truyền idempotency key đến downstream hoặc dùng outbox/inbox để tránh tạo side effect lặp.

### Blob trigger

Dùng blob URI cùng ETag hoặc version ID để nhận diện nội dung cụ thể. Cùng một tên blob nhưng ETag khác có thể là nội dung mới cần xử lý. Không chỉ dùng tên file làm idempotency key nếu file có thể được ghi đè.

Một bảng processed_operations có thể lưu:

| Field | Mục đích |
|---|---|
| operation_id | Khóa idempotency duy nhất |
| source_type | TIMER, QUEUE hoặc BLOB |
| source_id | Message ID, blob URI/ETag hoặc schedule occurrence |
| status | STARTED, COMPLETED, FAILED |
| started_at / completed_at | Theo dõi vòng đời |
| result_reference | Tham chiếu kết quả đã lưu |
| attempt_count | Số lần thử theo ứng dụng |

Cần thiết kế xử lý trường hợp function crash sau khi side effect đã commit nhưng trước khi trigger host xác nhận thành công. Lần gọi lại phải tra cứu operation ID và trả kết quả cũ thay vì thực hiện lại side effect.

## 8. Retry, timeout và xử lý lỗi

Không phải mọi lỗi đều nên retry giống nhau.

| Loại lỗi | Ví dụ | Hành động |
|---|---|---|
| Transient | Timeout database, HTTP 503, lỗi mạng tạm thời | Retry có giới hạn, backoff và jitter |
| Permanent theo dữ liệu | JSON sai, thiếu field bắt buộc, blob format không hỗ trợ | Đưa vào poison queue/quarantine hoặc ghi lỗi để sửa dữ liệu |
| Configuration | Storage credential sai, thiếu quyền, sai queue name | Cảnh báo và sửa cấu hình; tránh retry vô hạn |
| Business conflict | Đơn hàng đã hủy, trạng thái không cho phép | Áp dụng quy tắc nghiệp vụ, không retry mù quáng |

Với queue, message sẽ được giao lại theo visibility timeout khi invocation thất bại. Nếu xử lý mất nhiều thời gian hơn visibility timeout, message có thể xuất hiện lại trong khi lần đầu vẫn chạy. Hãy đặt timeout phù hợp, giảm thời gian xử lý hoặc chia công việc thành nhiều message nhỏ.

Với Timer, lỗi không đồng nghĩa lịch sẽ tự chạy lại ngay lập tức. Cần xác định chính sách retry của function/runtime, cảnh báo lần chạy thất bại và có quy trình bù hoặc reconciliation nếu kỳ chạy bị bỏ lỡ.

Với Blob, cần xem cơ chế retry của polling trigger hoặc Event Grid. Event Grid có thể retry delivery theo chính sách riêng; cấu hình dead-letter cho subscription nếu yêu cầu không mất event. Function cũng cần idempotent vì một event có thể được giao lại.

Đối với công việc kéo dài, không giữ một invocation vô hạn. Hãy chia nhỏ, enqueue bước tiếp theo hoặc dùng Durable Functions/workflow khi cần orchestration bền vững.

## 9. Cấu hình storage và bảo mật

Timer, Queue và Blob trigger cần truy cập storage account. Với cấu hình phổ biến, thuộc tính connection trong annotation tham chiếu đến application setting như AzureWebJobsStorage hoặc một setting riêng.

Ví dụ local development:

~~~json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "java"
  }
}
~~~

Trong Azure, nên cân nhắc managed identity và identity-based connection nếu extension/runtime hỗ trợ. Khi đó, cấp đúng data-plane role cho function:

- Queue trigger cần quyền đọc message và xóa message sau khi xử lý; output queue cần quyền gửi message.
- Blob trigger cần quyền đọc blob và metadata; function ghi blob cần quyền ghi tương ứng.
- Timer cần quyền storage mà host sử dụng để quản lý lock và schedule monitoring.

Không cấp Owner hoặc Contributor toàn subscription chỉ để function đọc một queue. Dùng least privilege theo account/container/queue và kiểm tra quyền của managed identity trong đúng subscription và storage account.

Connection string chứa account key là bí mật. Không hardcode trong Java source, annotation, log hoặc file cấu hình được commit. Local settings nên được bảo vệ; production secrets nên được quản lý qua Application Settings, Key Vault hoặc identity-based connection theo kiến trúc đã chọn.

## 10. Quan sát và vận hành

Một function có thể chạy thành công về mặt runtime nhưng nghiệp vụ vẫn lỗi, ví dụ message được xóa nhưng database chưa ghi đúng. Vì vậy, cần kết hợp log, metric và trạng thái nghiệp vụ.

### Timer

Theo dõi:

- Thời điểm dự kiến và thời điểm thực tế function chạy.
- Duration, success/failure và số lần chạy trễ.
- Schedule status và lỗi storage lock.
- Kỳ nghiệp vụ nào đã hoàn tất, kỳ nào đang thiếu.

Ghi business period và invocation ID vào log để đối soát. Không chỉ log “Timer fired” mà cần log kết quả của kỳ công việc.

### Queue

Theo dõi:

- Số message còn trong queue và tuổi message cũ nhất.
- Dequeue count, poison queue depth và tốc độ chuyển vào poison queue.
- Function execution count, duration, failure và retry.
- Throughput consumer, batch size và concurrency.
- Downstream latency, throttling và connection pool saturation.

Nếu backlog tăng, xác định consumer chậm, downstream nghẽn hay concurrency bị giới hạn. Tăng số instance không phải lúc nào cũng giải quyết được vấn đề nếu database đã quá tải.

### Blob

Theo dõi:

- Số blob mới và độ trễ từ upload đến invocation.
- Blob trigger failure, retry và poison records.
- Kích thước blob, thời gian đọc/stream và memory peak.
- Số version/ETag đã xử lý và kết quả output.
- Event Grid delivery failure/dead-letter nếu dùng event-based source.

Log nên chứa blob URI đã chuẩn hóa, ETag/version và correlation ID. Tránh log SAS token hoặc query string có chữ ký nếu blob URL chứa credential.

Application Insights và Azure Monitor có thể cung cấp distributed tracing, dependency telemetry và metric. Cần giữ correlation ID xuyên suốt từ HTTP request sang queue message, blob processing và bước đối soát Timer.

## 11. Local development và kiểm thử

Có thể kiểm thử function Java cục bộ bằng Azure Functions Core Tools cùng Azurite cho các dịch vụ Azure Storage được emulator hỗ trợ.

Các bước thường gặp:

1. Cài JDK và Maven phù hợp với Java runtime mục tiêu.
2. Cài Azure Functions Core Tools.
3. Chạy Azurite để giả lập Blob và Queue Storage.
4. Cấu hình local.settings.json với connection string development.
5. Chạy function host ở local và gửi message/upload blob/thay đổi timer schedule để kiểm thử.
6. Kiểm tra log, retry, poison queue và kết quả database.
7. Triển khai vào Azure test environment để xác nhận behavior thực tế, vì emulator không mô phỏng đầy đủ scale, identity, Event Grid và mọi host behavior.

Ma trận kiểm thử tối thiểu:

| Trigger | Ca kiểm thử | Kết quả mong đợi |
|---|---|---|
| Timer | Schedule hợp lệ | Chạy đúng thời điểm theo UTC/timezone đã cấu hình |
| Timer | Hai host instance cùng hoạt động | Chỉ một lần xử lý lịch theo singleton coordination |
| Timer | Function lỗi giữa chừng | Có log/alert; lần chạy sau không tạo side effect trùng |
| Queue | Message hợp lệ | Xử lý thành công và message bị xóa |
| Queue | Message gây lỗi nhiều lần | Dequeue count tăng và cuối cùng chuyển poison queue |
| Queue | Crash sau database commit | Message có thể giao lại nhưng nghiệp vụ không bị lặp |
| Queue | Backlog lớn | Concurrency không vượt khả năng downstream |
| Blob | Upload blob mới | Function nhận đúng blob name và content |
| Blob | Blob bị ghi đè | Phiên bản/ETag mới được xử lý theo chính sách |
| Blob | File lớn | Xử lý stream hoặc giới hạn memory phù hợp |
| Blob | Function lỗi | Retry/dead-letter theo source và runtime configuration |
| Tất cả | Storage credential hết hạn hoặc thiếu quyền | Lỗi được quan sát và cảnh báo rõ ràng |

## 12. Lựa chọn trigger theo yêu cầu

| Nhu cầu | Trigger phù hợp | Lý do |
|---|---|---|
| Chạy báo cáo vào 02:00 mỗi ngày | Timer | Lịch định kỳ là điều kiện kích hoạt chính |
| Gửi email sau khi đơn hàng được tạo | Storage Queue | Tách gửi email khỏi HTTP request và cho phép retry |
| Xử lý ảnh ngay sau khi upload | Blob | Sự kiện gắn với nội dung file |
| Đồng bộ dữ liệu mỗi 15 phút | Timer | Chạy theo chu kỳ, có thể enqueue từng batch |
| Xử lý hàng nghìn công việc độc lập | Storage Queue | Backlog giúp hấp thụ burst và phân phối worker |
| Phân tích file CSV lớn | Blob + Queue | Blob lưu file; Queue điều phối công việc và metadata |
| Đối soát các job bị kẹt | Timer + database | Tìm trạng thái quá hạn và khởi động bước phục hồi |

Đừng dùng Timer để liên tục polling một queue khi Queue trigger đã giải quyết trực tiếp việc đó. Cũng không nên đưa file lớn vào queue message; lưu file ở Blob Storage rồi gửi blob URI, version và metadata cần thiết qua queue.

## 13. Ví dụ kiến trúc kết hợp ba trigger

Giả sử ứng dụng nhận hóa đơn từ người dùng:

1. HTTP API nhận metadata và tạo upload reference.
2. Người dùng upload file PDF vào container incoming.
3. Blob trigger kiểm tra file type, kích thước và metadata; sau đó tạo message chứa blob URI, ETag và invoice ID.
4. Queue trigger đọc message, tải file theo stream, trích xuất dữ liệu và ghi kết quả vào database.
5. Nếu file không hợp lệ, consumer ghi lỗi và để message đi vào poison queue theo chính sách.
6. Timer trigger chạy mỗi giờ để tìm invoice đang ở trạng thái PROCESSING quá lâu, đối soát với queue/poison queue và tạo tác vụ phục hồi.
7. Dashboard hiển thị số file chờ, số file hoàn tất, lỗi và thời gian xử lý.

Ở đây Blob trigger phát hiện dữ liệu mới, Queue trigger thực hiện công việc có thể retry, còn Timer trigger đảm nhiệm đối soát định kỳ. Database là nguồn trạng thái nghiệp vụ chuẩn; queue và trigger là cơ chế điều phối.

## 14. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
|---|---|---|
| Dùng cron năm trường cho Timer trigger | Lịch chạy sai | Dùng NCRONTAB sáu trường của Azure Functions |
| Bật runOnStartup không cần thiết | Function chạy thêm khi host restart/scale | Giữ mặc định và chỉ bật khi hiểu rõ tác động |
| Không cấu hình host storage đúng | Timer lock hoặc trigger không hoạt động | Kiểm tra AzureWebJobsStorage và quyền truy cập |
| Giả định queue chỉ giao một lần | Side effect bị lặp | Idempotency theo message/event ID |
| Đặt visibility timeout quá ngắn | Message bị giao lại khi lần đầu còn chạy | Cấu hình timeout lớn hơn thời gian xử lý có biên an toàn |
| Không theo dõi poison queue | Message lỗi bị bỏ quên | Alert theo poison queue depth và oldest message age |
| Đưa file lớn vào byte[] | Heap tăng mạnh hoặc OOM | Stream blob bằng SDK |
| Dùng tên blob làm idempotency key duy nhất | Không phân biệt nội dung mới khi blob bị ghi đè | Kết hợp URI với ETag/version |
| Cho rằng Blob trigger luôn dùng Event Grid | Độ trễ và retry không như kỳ vọng | Xác nhận source và extension configuration |
| Tăng concurrency mà không kiểm tra database | Downstream quá tải | Giới hạn batch, concurrency và connection pool |
| Log connection string hoặc SAS URL | Lộ credential | Redact secrets và query signature |
| Dùng trigger như workflow engine | Khó quản lý bước dài, callback và compensation | Dùng Durable Functions/workflow cho orchestration phức tạp |

## 15. Checklist trước khi triển khai production

- **Timer:** schedule dùng đúng sáu trường NCRONTAB, timezone được xác định, schedule monitoring và host storage hoạt động.
- **Queue:** queue name và connection đúng; batch size, visibility timeout, maxDequeueCount và poison queue được cấu hình có chủ đích.
- **Blob:** container/path đúng; chọn polling hoặc Event Grid phù hợp; file lớn được stream và có chiến lược version/ETag.
- **Java runtime:** annotation, binding extension và runtime version tương thích; dependency được đóng gói đúng.
- **Idempotency:** mỗi schedule occurrence, message và blob version có operation key ổn định.
- **Retry:** transient/permanent/configuration errors được phân loại; retry có giới hạn và backoff.
- **Concurrency:** tổng số invocation và batch được giới hạn theo năng lực database/API downstream.
- **Security:** managed identity hoặc secret được cấu hình an toàn; role chỉ có quyền cần thiết.
- **Observability:** có log, metric, correlation ID, alert cho timer failure, queue backlog, poison queue và blob failure.
- **Recovery:** có runbook điều tra poison message, redrive, xử lý blob lỗi và đối soát kỳ Timer bị bỏ lỡ.
- **Cost:** ước lượng invocation, storage transaction, Event Grid, logging, network và thời gian chạy function.

## 16. Kết luận

Timer trigger phù hợp với tác vụ định kỳ; Storage Queue trigger phù hợp với công việc bất đồng bộ cần tách rời producer/consumer và retry; Blob trigger phù hợp với pipeline xử lý file khi blob được tạo hoặc cập nhật. Trong Java, các trigger được khai báo bằng annotation và được Azure Functions host quản lý, còn logic nghiệp vụ nên nằm trong service có thể kiểm thử độc lập.

Hãy thiết kế theo semantics thực tế của từng nguồn: Timer cần lịch và host storage coordination; Queue có thể giao lại và chuyển poison message; Blob cần kiểm soát version, kích thước file, polling hoặc Event Grid. Kết hợp idempotency, retry hữu hạn, concurrency phù hợp, least-privilege access và telemetry sẽ giúp các function hoạt động ổn định khi scale, restart hoặc gặp lỗi.
