# Cấu hình memory, timeout, ephemeral storage và kiến trúc CPU

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích mối quan hệ giữa memory, CPU, thời gian thực thi và chi phí của AWS Lambda.
- Ước lượng bộ nhớ cần thiết cho Java function, phân biệt Java heap với tổng bộ nhớ của execution environment.
- Đặt timeout theo đặc tính công việc, deadline của caller và thời gian của các dịch vụ phụ thuộc.
- Sử dụng `/tmp` và cấu hình ephemeral storage phù hợp với kích thước dữ liệu tạm.
- Chọn `x86_64` hoặc `arm64` dựa trên hiệu năng, chi phí và khả năng tương thích của dependency.
- Đo lường, benchmark và điều chỉnh cấu hình bằng số liệu thay vì chỉ dựa vào cảm giác.
- Quản lý các cấu hình này bằng AWS SAM, CloudFormation hoặc AWS CLI.

## 1. Vì sao cấu hình tài nguyên Lambda quan trọng?

AWS Lambda chạy function trong execution environment do nền tảng quản lý. Người phát triển không quản lý máy chủ vật lý, nhưng vẫn phải chọn các giới hạn tài nguyên và thời gian cho mỗi function. Những lựa chọn này ảnh hưởng trực tiếp đến khả năng xử lý, độ trễ, độ ổn định và chi phí.

Một Java function xử lý ảnh có thể cần nhiều bộ nhớ và dung lượng tạm để giải nén, resize rồi ghi kết quả. Một HTTP function chỉ xác thực token và đọc một bản ghi có thể cần ít tài nguyên hơn. Một function chạy thuật toán CPU-intensive có thể hoàn thành nhanh hơn đáng kể khi được cấp thêm memory vì Lambda đồng thời cấp thêm năng lực CPU.

Bốn nhóm cấu hình cần hiểu:

1. **Memory:** giới hạn bộ nhớ cấp cho mỗi execution environment và ảnh hưởng đến năng lực CPU, network của function.
2. **Timeout:** thời gian tối đa một invocation được phép chạy.
3. **Ephemeral storage:** dung lượng lưu trữ tạm thời tại thư mục `/tmp`.
4. **CPU architecture:** kiến trúc bộ xử lý mà function chạy trên, thường là `x86_64` hoặc `arm64`.

Các cấu hình này liên quan với nhau nhưng không thay thế nhau. Tăng memory không làm tăng dung lượng `/tmp` đã cấu hình; tăng ephemeral storage không làm Java heap lớn hơn; tăng timeout không làm function có thêm CPU. Chọn đúng từng giới hạn giúp function xử lý đủ công việc mà không tiêu thụ tài nguyên không cần thiết.

## 2. Mô hình tài nguyên của AWS Lambda

Một invocation chạy trong execution environment có các tài nguyên và giới hạn riêng. Lambda có thể tạo nhiều environment để đáp ứng concurrency. Vì vậy, cấu hình của một function cần được xem ở cả hai cấp:

- **Mỗi environment:** memory, CPU tương ứng, `/tmp`, timeout và các giới hạn runtime.
- **Toàn bộ function:** số invocation đồng thời, tổng lượng tài nguyên tiêu thụ, kết nối database và tải lên các dịch vụ phụ thuộc.

~~~mermaid
flowchart TD
    A[Lambda function configuration] --> B[Execution environment]
    B --> C[Memory allocation]
    B --> D[CPU capacity follows memory]
    B --> E[Ephemeral storage /tmp]
    B --> F[Invocation timeout]
    A --> G[CPU architecture]
    G --> H[x86_64 hoặc arm64]
    I[Concurrency] --> J[Nhiều execution environments]
    J --> B
~~~

Ví dụ, một function được cấu hình memory 2 GB và concurrency 100 có thể có khoảng 100 execution environment hoạt động đồng thời khi tải và quota cho phép. Mỗi environment có giới hạn memory và `/tmp` theo cấu hình của function. Tổng tác động lên database, API ngoài và các dịch vụ dùng chung có thể lớn hơn nhiều so với một invocation đơn lẻ.

Lambda có thể tái sử dụng execution environment cho các invocation tiếp theo. Điều này giúp tận dụng runtime, class đã load và connection được khởi tạo phù hợp. Tuy nhiên, không được giả định một invocation tiếp theo chắc chắn chạy trên cùng environment, cũng không được xem bộ nhớ hoặc `/tmp` của environment là kho dữ liệu dùng chung.

### 2.1. Các giới hạn cấu hình thường gặp

Các giới hạn Lambda phổ biến cần nhớ:

| Cấu hình | Phạm vi cấu hình phổ biến | Mặc định và bước thay đổi | Ý nghĩa |
|---|---:|---|---|
| Memory | 128 MB đến 10.240 MB | 128 MB; bước 1 MB | Bộ nhớ cấp cho execution environment |
| Timeout | 1 giây đến 900 giây | 3 giây; bước 1 giây | Thời gian tối đa của một invocation |
| Ephemeral storage | 512 MB đến 10.240 MB | 512 MB; bước 1 MB | Dung lượng tạm tại `/tmp` |
| CPU architecture | `x86_64` hoặc `arm64` | Mặc định `x86_64` | Kiến trúc CPU của environment |

Các giới hạn, runtime được hỗ trợ và quota có thể thay đổi theo thời gian hoặc theo dịch vụ tích hợp. Hãy kiểm tra tài liệu AWS và quota của region khi triển khai thực tế. Những giá trị trong bảng là phạm vi cấu hình phổ biến để giải thích cách thiết kế, không thay thế việc xác minh giới hạn hiện hành.

Memory và ephemeral storage thường được cấu hình theo MB. Timeout được cấu hình theo giây. Architecture là lựa chọn cho function, không phải một tham số có thể thay đổi trong từng invocation.

## 3. Cấu hình memory và tác động đến CPU

Memory là một trong những cấu hình quan trọng nhất của Lambda. Giá trị memory không chỉ quyết định lượng RAM function có thể sử dụng. Lambda còn phân bổ năng lực CPU tăng theo memory. Vì vậy, tăng memory có thể làm một tác vụ CPU-intensive chạy nhanh hơn dù code không thay đổi.

### 3.1. Memory không chỉ là Java heap

Tổng memory mà process Java sử dụng có thể bao gồm:

- Java heap chứa object, collection, buffer và dữ liệu ứng dụng.
- Metaspace chứa metadata của class.
- Thread stack cho các thread đang hoạt động.
- Direct byte buffer và các vùng native memory.
- JIT compiler, code cache và cấu trúc runtime JVM.
- Thư viện native, JNI và thành phần hệ điều hành/runtime liên quan.
- Bộ nhớ dùng cho TLS, compression, serialization, driver và client SDK.

Do đó, không thể đặt Java heap bằng toàn bộ memory của Lambda. Nếu heap chiếm gần hết giới hạn, process vẫn có thể bị thiếu bộ nhớ khi runtime cần cấp phát native memory, tạo thread hoặc xử lý buffer ngoài heap.

Ví dụ, một function được cấp 1.024 MB không có nghĩa Java heap an toàn khi đặt `-Xmx1024m`. Heap tối đa cần chừa không gian cho metaspace, thread stack, direct buffer và các vùng native khác. Mức chừa cụ thể phụ thuộc framework, số thread, thư viện và đặc điểm tải; hãy đo trong môi trường gần production.

### 3.2. Lambda cấp CPU theo memory

Lambda phân bổ CPU tăng theo mức memory được chọn; network throughput cũng có thể tăng theo mức memory. Mốc thường được dùng để tham chiếu là khoảng 1.769 MB memory tương ứng với một vCPU theo mô hình phân bổ của Lambda. Đây là mốc tham khảo để hiểu quan hệ tỷ lệ, không phải cam kết rằng mọi tác vụ sẽ dùng được đúng một core liên tục hoặc đạt một mức băng thông cố định.

Tăng memory có thể cải thiện:

- Tác vụ nén/giải nén, mã hóa và hashing.
- Resize ảnh, chuyển mã media và xử lý dữ liệu.
- Serialization/deserialization payload lớn.
- Tác vụ tính toán hoặc phân tích CPU-intensive.
- Thời gian khởi tạo một số framework Java khi CPU là nút thắt.

Với workload chủ yếu chờ I/O, tăng memory có thể không làm latency giảm nhiều nếu database, network hoặc dịch vụ ngoài mới là giới hạn. Tuy nhiên, thêm CPU vẫn có thể giúp các giai đoạn xử lý trước/sau I/O.

### 3.3. Memory lớn hơn có thể giảm tổng chi phí

Chi phí compute của Lambda chịu ảnh hưởng bởi memory được cấp và thời gian thực thi. Tăng memory làm đơn giá theo thời gian cao hơn, nhưng nếu function hoàn thành nhanh hơn đủ nhiều thì chi phí cho một request có thể giảm.

Ví dụ minh họa, giả sử cùng một tác vụ:

| Cấu hình | Memory | Thời gian | Memory × thời gian |
|---|---:|---:|---:|
| A | 1.024 MB | 1,0 giây | 1.024 MB-giây |
| B | 2.048 MB | 0,45 giây | 921,6 MB-giây |
| C | 3.072 MB | 0,35 giây | 1.075,2 MB-giây |

Trong ví dụ, cấu hình B hoàn thành nhanh hơn và có tích memory-time thấp hơn A. C nhanh hơn B nhưng tích memory-time cao hơn. Đây chỉ là phép so sánh định tính; chi phí thực tế còn phụ thuộc architecture, số request, thời lượng tính phí, ephemeral storage, free tier và biểu giá hiện hành.

Không nên chọn memory thấp nhất chỉ vì muốn giảm đơn giá. Với một số workload, thêm memory giúp giảm thời gian, tăng throughput và giảm thời gian chiếm giữ kết nối database. Hãy so sánh chi phí trên mỗi tác vụ thành công cùng với latency và error rate.

### 3.4. Dấu hiệu memory đang quá thấp

Một số dấu hiệu thường gặp:

- Log xuất hiện `java.lang.OutOfMemoryError: Java heap space`.
- Runtime báo thiếu native memory hoặc không thể tạo thread.
- Execution environment bị dừng bất thường khi memory sử dụng chạm giới hạn.
- `Max Memory Used` thường xuyên tiến sát mức memory đã cấp.
- Payload lớn hoặc batch lớn làm function lỗi dù dữ liệu nhỏ vẫn chạy bình thường.
- Garbage collection diễn ra dày, thời gian pause tăng và duration xấu đi.

`OutOfMemoryError` không phải lúc nào cũng có nghĩa heap quá nhỏ. Nó có thể xuất hiện do direct buffer, metaspace, thread hoặc native allocation. Ngược lại, process có thể bị hệ thống dừng vì tổng memory vượt giới hạn mà không có stack trace Java rõ ràng.

Hãy phân biệt lỗi memory với lỗi timeout. Một function có thể bị timeout khi memory vẫn còn dư; tăng memory có thể giúp nếu CPU là nút thắt, nhưng không giải quyết được một truy vấn database bị treo hoặc một vòng lặp chờ vô hạn.

### 3.5. Ước lượng memory cho Java function

Không có một giá trị memory tối ưu cho mọi Java function. Có thể bắt đầu bằng cách xác định thành phần tiêu thụ:

1. Đo footprint khi runtime và framework đã khởi tạo.
2. Đo heap trong lúc xử lý payload đại diện.
3. Đo số thread và kích thước stack.
4. Đo direct buffer/native memory nếu ứng dụng dùng NIO, Netty, compression hoặc thư viện native.
5. Đo peak memory khi xử lý batch lớn nhất được phép.
6. Chừa headroom cho biến động tải, class loading và các nhánh lỗi/retry.

Một function Spring/Quarkus/Micronaut có footprint khác một function Java thuần. Một handler đọc một JSON nhỏ khác với handler giải nén file hoặc xử lý ảnh. Cần benchmark với đúng artifact, runtime, framework, dependency và kích thước payload dự kiến triển khai.

## 4. Cấu hình timeout và ngân sách thời gian

Timeout giới hạn thời gian một invocation được phép chạy. Khi vượt quá giới hạn, Lambda chấm dứt invocation. Timeout bảo vệ hệ thống khỏi function bị treo và giúp kiểm soát thời gian xử lý, nhưng đặt quá thấp có thể làm tác vụ hợp lệ thất bại; đặt quá cao có thể giữ tài nguyên lâu và làm client chờ quá lâu.

### 4.1. Chọn timeout theo công việc

Timeout mặc định của Lambda thường là 3 giây và có thể cấu hình tối đa 900 giây (15 phút). Mỗi function nên có timeout dựa trên phân bố thời gian thực thi thực tế:

- Function xác thực HTTP và đọc dữ liệu nhỏ thường cần timeout ngắn.
- Function xử lý ảnh hoặc file có thể cần nhiều thời gian hơn, phụ thuộc kích thước đầu vào.
- Function gọi API bên ngoài cần tính cả thời gian kết nối, phản hồi và retry.
- Function xử lý batch cần tính trường hợp batch lớn nhất được phép, không chỉ trường hợp trung bình.
- Function thực hiện export hoặc workflow kéo dài nên chuyển sang mô hình bất đồng bộ thay vì giữ một invocation HTTP mở trong thời gian dài.

Không lấy timeout tối đa làm giá trị mặc định cho mọi function. Timeout dài không làm function chạy nhanh hơn; nó chỉ cho phép invocation giữ tài nguyên lâu hơn trước khi bị dừng.

### 4.2. Ngân sách thời gian end-to-end

Một request có thể đi qua nhiều tầng:

~~~mermaid
flowchart LR
    A[Client deadline] --> B[API Gateway]
    B --> C[Lambda timeout]
    C --> D[HTTP client timeout]
    D --> E[Database hoặc API ngoài]
~~~

Deadline của các tầng cần nhất quán. Nếu client chỉ chờ 10 giây nhưng Lambda được cấu hình 60 giây, client có thể bỏ request trong khi function vẫn đang xử lý. Function tiếp tục ghi dữ liệu hoặc gọi dịch vụ ngoài dù client đã nhận timeout.

Một nguyên tắc hữu ích là:

`function deadline < caller deadline - response margin`

Timeout của lời gọi phụ thuộc nên ngắn hơn thời gian còn lại của invocation. Cần chừa thời gian để ghi log, đóng tài nguyên, lưu trạng thái và trả response. Không để một HTTP client có timeout dài hơn thời gian Lambda còn được phép chạy.

Với chuỗi nhiều dịch vụ, hãy phân bổ ngân sách cho từng bước. Ví dụ, nếu request có deadline 8 giây, không nên để database timeout 8 giây rồi mới bắt đầu serialize response. Cần dành một phần thời gian cho xác thực, truy vấn, xử lý và phản hồi.

### 4.3. Đọc thời gian còn lại trong Java

AWS Lambda Java runtime cung cấp `Context`, trong đó có `getRemainingTimeInMillis()`. Handler có thể dùng giá trị này để tránh bắt đầu một bước mới khi không còn đủ thời gian:

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;

public final class ReportHandler
        implements RequestHandler<ReportRequest, ReportResponse> {

    @Override
    public ReportResponse handleRequest(
            ReportRequest request,
            Context context) {

        int remaining = context.getRemainingTimeInMillis();

        if (remaining < 2_000) {
            throw new IllegalStateException(
                    "Not enough invocation time to start report generation");
        }

        return generateReport(request, remaining, context);
    }

    private ReportResponse generateReport(
            ReportRequest request,
            int remainingMillis,
            Context context) {
        // Truyền deadline xuống repository và HTTP client.
        return new ReportResponse("accepted");
    }
}
~~~

Đây là ví dụ minh họa; trong ứng dụng thực tế, nên dùng exception và error mapping phù hợp với contract của trigger. `getRemainingTimeInMillis()` là thời gian còn lại của invocation, không phải deadline của client. Nếu có deadline từ caller, hãy so sánh cả hai và dùng giới hạn ngắn hơn.

Không chỉ kiểm tra thời gian ở đầu handler. Một bước có thể mất nhiều thời gian hơn dự kiến; hãy kiểm tra trước các thao tác dài, truyền timeout còn lại xuống HTTP/database client và tránh retry nếu không còn đủ ngân sách.

### 4.4. Timeout không tự hủy tác động bên ngoài

Khi Lambda timeout, invocation bị chấm dứt, nhưng một hệ thống bên ngoài có thể đã nhận request và vẫn tiếp tục xử lý. Ví dụ, function gửi lệnh tạo vận đơn, dịch vụ vận chuyển xử lý thành công nhưng response không về kịp. Nếu function được retry, một vận đơn thứ hai có thể được tạo.

Đối với thao tác có side effect:

- Dùng idempotency key ổn định cho mỗi nghiệp vụ.
- Đặt connect timeout và read timeout riêng cho HTTP client.
- Kiểm tra trạng thái thao tác trước khi retry khi kết quả lần trước không xác định.
- Ghi nhận operation ID để có thể tra cứu sau timeout.
- Tránh xem timeout như bằng chứng rằng thao tác đã thất bại.

Timeout của function cũng không thay thế timeout của database statement, socket hoặc SDK. Mỗi dependency cần có timeout riêng để invocation có thể kết thúc có kiểm soát.

### 4.5. Timeout và loại trigger

Cách xử lý khi function timeout phụ thuộc nguồn invocation:

- **Synchronous HTTP:** caller thường nhận lỗi hoặc timeout; caller có thể thử lại. Cần idempotency để tránh tác động trùng.
- **Asynchronous invocation:** Lambda có cơ chế retry theo cấu hình và loại lỗi; event có thể được gửi lại.
- **Queue/event source mapping:** message có thể được giao lại nếu batch không được xác nhận thành công. Một message lỗi có thể ảnh hưởng các message khác trong batch tùy cấu hình partial batch response.
- **Workflow engine:** timeout của task có thể làm state chuyển sang retry/catch/failure theo định nghĩa workflow.

Với Amazon SQS, visibility timeout phải được đặt đủ dài để message không bị giao lại trong lúc lần xử lý trước vẫn đang chạy. Hướng dẫn AWS thường khuyến nghị visibility timeout tối thiểu bằng sáu lần function timeout, cộng thêm batch window nếu có. Hãy xác minh hướng dẫn hiện hành cho event source mapping và cấu hình retry đang sử dụng.

### 4.6. Khi nào cần xử lý bất đồng bộ?

Nếu một request cần xử lý hàng chục nghìn bản ghi, export file lớn, gọi nhiều child workflow hoặc chờ hệ thống ngoài trong nhiều phút, nên tách bước nhận yêu cầu khỏi bước thực thi:

1. HTTP handler xác thực và tạo job.
2. Handler ghi job state và khởi chạy workflow/queue.
3. Handler trả `202 Accepted` cùng `jobId` hoặc URL tra cứu.
4. Worker xử lý theo batch với concurrency giới hạn.
5. Client đọc trạng thái hoặc nhận thông báo khi job hoàn tất.

Cách này giúp HTTP invocation ngắn và cho phép workflow có timeout, retry, checkpoint riêng. Timeout tối đa của Lambda không nên được xem là cơ chế điều phối công việc dài hạn.

## 5. Ephemeral storage và thư mục /tmp

Lambda cung cấp vùng lưu trữ tạm thời cho mỗi execution environment tại thư mục `/tmp`. Đây là scratch space dành cho file trung gian mà function cần trong lúc xử lý.

### 5.1. Dung lượng và đặc tính

Ephemeral storage mặc định là 512 MB và có thể cấu hình tăng đến 10.240 MB. Dung lượng này được cấp cho từng execution environment. Các environment khác nhau không dùng chung thư mục `/tmp`.

Một số đặc điểm cần nhớ:

- File trong `/tmp` có thể còn tồn tại khi environment được tái sử dụng cho invocation ấm tiếp theo.
- Environment có thể bị thu hồi bất kỳ lúc nào; không có cam kết dữ liệu tạm sẽ tồn tại qua lần khởi tạo sau.
- Nội dung `/tmp` không được chia sẻ giữa các environment chạy đồng thời.
- Đây không phải kho dữ liệu bền vững và không thay thế S3, EFS hoặc database.
- Dữ liệu cũ cần được dọn dẹp; không giả định mỗi invocation bắt đầu với thư mục trống.

Lambda mã hóa dữ liệu ephemeral storage khi lưu trữ. Dù vậy, ứng dụng vẫn nên giới hạn quyền truy cập, tránh ghi secret hoặc dữ liệu nhạy cảm không cần thiết, và xóa file tạm sau khi hoàn tất.

### 5.2. Khi nào cần tăng ephemeral storage?

Các tình huống thường cần dung lượng `/tmp` lớn hơn:

- Tải file nén từ S3 rồi giải nén trước khi xử lý.
- Tạo file CSV, PDF, ZIP hoặc report trung gian.
- Chuyển mã audio/video bằng công cụ như FFmpeg.
- Resize hoặc ghép nhiều ảnh có kích thước lớn.
- Tải model hoặc dữ liệu tham chiếu để xử lý trong invocation.
- Dùng thư viện chỉ hỗ trợ làm việc với file thay vì stream.

Nếu có thể xử lý bằng stream, không nhất thiết phải ghi toàn bộ dữ liệu xuống disk. Ví dụ, đọc object theo stream và ghi kết quả theo stream có thể giảm dung lượng tạm và bộ nhớ. Tuy nhiên, streaming có thể phức tạp hơn nếu thư viện cần seek hoặc cần toàn bộ file đầu vào.

### 5.3. Phân biệt memory và ephemeral storage

| Nhu cầu | Cấu hình/tài nguyên |
|---|---|
| Object, collection và buffer trong JVM | Memory, đặc biệt là Java heap |
| Metaspace, thread stack và native allocation | Tổng memory của process |
| File trung gian trên disk | Ephemeral storage tại `/tmp` |
| Dữ liệu phải tồn tại sau invocation | S3, EFS hoặc database |
| Dữ liệu cần chia sẻ giữa nhiều environment | Dịch vụ lưu trữ dùng chung như S3/EFS/database |

Tăng `/tmp` không làm Java heap tăng. Tăng memory không tự tăng giới hạn dung lượng `/tmp`. Một function có thể có đủ heap nhưng hết disk, hoặc còn nhiều disk nhưng bị `OutOfMemoryError`.

### 5.4. Quản lý file tạm bằng Java

Ví dụ sau kiểm tra dung lượng khả dụng, tạo file tạm và xóa file sau khi xử lý:

~~~java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;

public final class TemporaryFileService {

    public Path createTemporaryFile() throws IOException {
        Path tempDirectory = Path.of("/tmp");
        FileStore fileStore = Files.getFileStore(tempDirectory);

        long usableBytes = fileStore.getUsableSpace();
        long requiredBytes = 100L * 1024 * 1024;

        if (usableBytes < requiredBytes) {
            throw new IOException("Insufficient ephemeral storage");
        }

        return Files.createTempFile(
                tempDirectory, "lambda-work-", ".bin");
    }

    public void process() throws IOException {
        Path tempFile = createTemporaryFile();

        try {
            // Ghi hoặc tải dữ liệu vào tempFile.
            // Xử lý file và lưu kết quả bền vững vào S3/database.
        } finally {
            Files.deleteIfExists(tempFile);
        }
    }
}
~~~

Đây là ví dụ khung. Với luồng đọc/ghi thực tế, hãy dùng try-with-resources để đóng stream và luôn xóa file trong `finally`. Nếu file phải được giữ lại giữa các bước trong cùng invocation, chỉ xóa sau khi bước cuối đã sử dụng xong.

Không tạo tên file dựa hoàn toàn trên input client vì hai invocation có thể chạy đồng thời và ghi đè nhau. Dùng `Files.createTempFile` hoặc tên duy nhất theo invocation/task ID. Không dựa vào việc xóa file ở cuối invocation để bảo đảm an toàn: process có thể bị dừng trước khi chạy `finally`, nên cũng cần cơ chế dọn file cũ khi environment được tái sử dụng.

### 5.5. Kiểm soát dung lượng và vòng đời file

Khi dùng `/tmp`:

- Ước lượng kích thước file đầu vào, file giải nén và file đầu ra; chúng có thể cùng tồn tại trong một thời điểm.
- Tính cả file tạm của thư viện, cache và nhiều tác vụ chạy song song trong cùng environment.
- Kiểm tra `getUsableSpace()` trước khi bắt đầu thao tác lớn.
- Xóa file khi không còn cần thiết và dọn file cũ theo quy tắc an toàn.
- Tránh đọc toàn bộ file vào heap nếu có thể stream.
- Đặt giới hạn kích thước file đầu vào để ngăn request bất thường làm đầy disk.
- Theo dõi dung lượng `/tmp` bằng custom metric hoặc log; Lambda không tự cung cấp đầy đủ metric ứng dụng về mức sử dụng từng file.

Nếu nhiều tác vụ chạy song song trong cùng invocation, cần tính tổng dung lượng tạm mà tất cả tác vụ có thể dùng. Giới hạn concurrency cục bộ cũng là một cách ngăn các tác vụ cùng lúc chiếm hết `/tmp`.

## 6. Chọn CPU architecture: x86_64 hay arm64?

AWS Lambda hỗ trợ hai kiến trúc CPU phổ biến là `x86_64` và `arm64`. Kiến trúc được chọn cho function và quyết định loại execution environment mà Lambda cấp. Với Java, bytecode chạy trên JVM thường có tính di động giữa hai kiến trúc, nhưng không phải mọi dependency và artifact đều tự động tương thích.

### 6.1. So sánh hai kiến trúc

| Tiêu chí | `x86_64` | `arm64` |
|---|---|---|
| Nền tảng CPU | Bộ xử lý x86-64 | Bộ xử lý AWS Graviton2 |
| Hệ sinh thái native | Rất rộng, thường là mặc định của thư viện cũ | Cần dependency hoặc binary có bản ARM64 |
| Java bytecode thuần | Thường chạy được | Thường chạy được |
| JNI/native library | Phải có binary x86-64 tương thích | Phải có binary ARM64 tương thích |
| Giá/hiệu năng | Phụ thuộc workload và biểu giá | Có thể có lợi thế giá/hiệu năng |
| Quyết định | Chọn khi dependency hoặc benchmark yêu cầu | Nên benchmark khi muốn tối ưu chi phí/hiệu năng |

`arm64` trên Lambda dựa trên bộ xử lý AWS Graviton2. Nhiều workload có thể đạt hiệu năng và chi phí tốt trên ARM64, nhưng không nên mặc định ARM64 luôn nhanh hơn. Kết quả phụ thuộc instruction mix, thư viện native, mức độ tối ưu của runtime, memory, I/O và đặc điểm dữ liệu.

### 6.2. Java bytecode và thư viện native

Java bytecode trong JAR thường không gắn với kiến trúc CPU. Nếu function chỉ dùng Java standard library và dependency thuần Java, việc chuyển kiến trúc thường đơn giản.

Các thành phần sau cần kiểm tra kỹ:

- JNI library đóng gói trong JAR hoặc layer.
- Thư viện nén, xử lý ảnh, media hoặc cryptography có native binary.
- Driver hoặc SDK sử dụng native acceleration.
- Java agent hoặc profiler có thành phần native.
- Executable được gọi từ Java bằng `ProcessBuilder`.
- GraalVM native executable hoặc artifact đã biên dịch AOT.
- Container image và Lambda layer có binary phụ thuộc kiến trúc.

Ví dụ, một JAR có thể chứa thư viện `.so` cho x86-64. JAR vẫn build thành công trên máy phát triển nhưng function `arm64` lỗi khi nạp thư viện với thông báo không tương thích kiến trúc. Cần xác minh binary được đóng gói đúng định dạng, đúng ABI và đúng kiến trúc đích.

### 6.3. Container image và Lambda layer

Nếu function dùng container image, image phải hỗ trợ kiến trúc đã cấu hình cho Lambda. Không giả định image được build trên máy x86 có thể chạy nguyên trạng trên ARM64 nếu bên trong có binary native.

Khi build image cho ARM64, có thể cần chỉ định platform tương ứng trong Docker build pipeline và xác minh manifest/image architecture. Với Lambda layer, kiểm tra nội dung layer và metadata tương thích kiến trúc; layer chứa binary native phải được build cho cùng kiến trúc với function.

Một package Java thuần có thể dùng chung giữa hai kiến trúc, nhưng pipeline build/release vẫn nên kiểm tra dependency và artifact thực tế. Nếu tạo hai biến thể image hoặc layer, hãy gắn nhãn rõ ràng để tránh deploy nhầm.

### 6.4. Phát hiện kiến trúc trong Java

Có thể ghi nhận một số thông tin runtime khi khởi tạo:

~~~java
public final class RuntimeDiagnostics {

    public static void logRuntime() {
        Runtime runtime = Runtime.getRuntime();

        System.out.println("os.arch=" + System.getProperty("os.arch"));
        System.out.println("availableProcessors="
                + runtime.availableProcessors());
        System.out.println("maxHeapBytes=" + runtime.maxMemory());
        System.out.println("totalHeapBytes=" + runtime.totalMemory());
        System.out.println("freeHeapBytes=" + runtime.freeMemory());
    }
}
~~~

Trên ARM64, `os.arch` thường hiển thị giá trị như `aarch64`; trên x86-64 có thể hiển thị `amd64`. Giá trị cụ thể phụ thuộc JVM. `availableProcessors()` phản ánh CPU mà JVM nhìn thấy, nhưng không nên dùng nó như một cam kết về số core vật lý hay khả năng chạy song song liên tục.

Không ghi các thông tin chẩn đoán nhạy cảm hoặc environment variable chứa secret vào log. Các giá trị trên hữu ích để xác nhận môi trường khi benchmark và điều tra sự cố.

### 6.5. Quy trình chọn architecture

Một quy trình an toàn:

1. Liệt kê dependency, layer, container và executable native.
2. Kiểm tra artifact có bản build tương thích với architecture mục tiêu.
3. Deploy một phiên bản thử nghiệm dùng cùng memory, timeout và dữ liệu đại diện.
4. Đo cold start, warm duration, memory, error rate và throughput.
5. Chạy cả workload CPU-intensive lẫn workload I/O nếu function phục vụ nhiều kiểu request.
6. So sánh chi phí trên mỗi request thành công theo biểu giá hiện hành.
7. Chuyển traffic dần qua alias hoặc môi trường thử nghiệm, theo dõi lỗi trước khi chuyển toàn bộ.

Không so sánh ARM64 với x86-64 bằng hai lần chạy có memory khác nhau, payload khác nhau hoặc mức concurrency khác nhau. Khi đó không thể biết khác biệt đến từ architecture hay từ cấu hình còn lại.

## 7. Cấu hình bằng AWS SAM và AWS CLI

Memory, timeout, ephemeral storage và architecture nên được quản lý như cấu hình triển khai có thể review và version control. Không nên chỉ chỉnh thủ công trên Console rồi để template IaC khác với cấu hình đang chạy.

### 7.1. Ví dụ AWS SAM

Ví dụ sau cấu hình một Java function dùng ARM64, memory 2 GB, timeout 45 giây và ephemeral storage 2 GB:

~~~yaml
Resources:
  ImageProcessorFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: target/function.zip
      Handler: com.example.ImageHandler
      Runtime: java21
      Architectures:
        - arm64
      MemorySize: 2048
      Timeout: 45
      EphemeralStorage:
        Size: 2048
      ReservedConcurrentExecutions: 20
~~~

Ý nghĩa:

- `MemorySize: 2048`: cấp 2.048 MB memory cho mỗi execution environment.
- `Timeout: 45`: giới hạn một invocation trong 45 giây.
- `EphemeralStorage.Size: 2048`: cấp 2.048 MB cho `/tmp` của mỗi environment.
- `Architectures: [arm64]`: chọn kiến trúc ARM64.
- `ReservedConcurrentExecutions: 20`: giới hạn concurrency dành riêng cho function, giúp kiểm soát tải lên dependency trong ví dụ này.

Các giá trị chỉ minh họa. Không sao chép chúng vào production nếu chưa đo memory peak, thời gian xử lý, dung lượng file và capacity của downstream. Nếu function không cần `/tmp` lớn, giữ mặc định sẽ đơn giản và tiết kiệm hơn.

### 7.2. Cập nhật cấu hình bằng AWS CLI

Ví dụ chạy trong shell Bash:

~~~bash
aws lambda update-function-configuration \
  --function-name image-processor \
  --memory-size 2048 \
  --timeout 45 \
  --ephemeral-storage '{"Size":2048}' \
  --architectures arm64
~~~

Đọc lại cấu hình sau khi cập nhật:

~~~bash
aws lambda get-function-configuration \
  --function-name image-processor \
  --query '{Memory:MemorySize,Timeout:Timeout,Storage:EphemeralStorage.Size,Architectures:Architectures}'
~~~

Lệnh cập nhật có thể trả về trạng thái cấu hình đang được áp dụng. Hãy đợi trạng thái function sẵn sàng trước khi chạy benchmark hoặc chuyển traffic. Khi đổi architecture, cần chắc chắn code package, layer và container image tương thích với kiến trúc mới.

### 7.3. Cấu hình trong Console

Trong AWS Lambda Console:

1. Mở function cần cấu hình.
2. Vào **Configuration**.
3. Chọn **General configuration** để chỉnh memory và timeout.
4. Chọn phần **Ephemeral storage** để thay đổi dung lượng `/tmp`.
5. Chọn phần **Architecture** để xem hoặc thay đổi `x86_64`/`arm64`.
6. Lưu cấu hình, đợi update hoàn tất rồi kiểm tra bằng một invocation thử.

Tên và vị trí một số mục có thể thay đổi theo phiên bản giao diện. Khi quản lý function bằng IaC, hãy cập nhật template tương ứng để lần deploy sau không ghi đè thay đổi thủ công.

### 7.4. Published version và alias

Cấu hình Lambda thuộc về phiên bản function. Khi dùng published version, phiên bản đã publish giữ cấu hình tại thời điểm phát hành. Nếu thay đổi memory, timeout, ephemeral storage hoặc architecture trên `$LATEST`, cần publish version mới và cập nhật alias để traffic sử dụng cấu hình mới.

Một quy trình phát hành có kiểm soát:

1. Cập nhật template và build artifact tương thích.
2. Deploy vào `$LATEST` hoặc môi trường thử nghiệm.
3. Chạy smoke test và benchmark với payload đại diện.
4. Publish version mới.
5. Chuyển alias sang version mới hoặc dùng weighted alias để chuyển traffic từng phần.
6. Theo dõi error, duration, memory và dependency load.
7. Roll back alias nếu phát hiện regression.

Alias giúp tách client khỏi số version cụ thể và hỗ trợ chuyển traffic/rollback có kiểm soát. Đổi cấu hình mà không xác nhận version và alias đang phục vụ traffic là nguyên nhân thường gặp khiến benchmark một cấu hình nhưng production lại chạy cấu hình khác.

## 8. Đo memory, timeout và /tmp trong Java

Cấu hình tốt phải được xác nhận bằng số liệu của function thực tế. Lambda cung cấp metric về duration, errors, throttles và concurrency; log invocation có thể hiển thị memory size và mức memory sử dụng cao nhất. Với ephemeral storage, ứng dụng nên tự đo dung lượng còn lại nếu cần quan sát chi tiết.

### 8.1. Metric và log cần theo dõi

| Chỉ số | Nguồn quan sát | Cách dùng |
|---|---|---|
| `Duration` | CloudWatch Metrics | Theo dõi latency và percentile |
| `Errors` | CloudWatch Metrics | Phát hiện invocation lỗi |
| `Throttles` | CloudWatch Metrics | Phát hiện vượt concurrency/quota |
| `ConcurrentExecutions` | CloudWatch Metrics | Theo dõi mức chạy đồng thời |
| `Init Duration` | Lambda REPORT log | Theo dõi thời gian khởi tạo |
| `Max Memory Used` | Lambda REPORT log | So sánh peak memory với mức cấp |
| `/tmp` usable space | Custom log/metric | Phát hiện nguy cơ hết ephemeral storage |
| Timeout count | Log/metric ứng dụng | Phát hiện function chạm deadline |
| Downstream latency | Trace/metric của dependency | Phân biệt CPU bottleneck với I/O bottleneck |

CloudWatch Metrics mặc định không cung cấp mọi chi tiết về mức sử dụng `/tmp` của từng file. Nếu cần, hãy ghi nhận `FileStore.getUsableSpace()` và phát custom metric theo cách có kiểm soát. Tránh tạo metric dimension có cardinality cao như `requestId` hoặc `itemId`.

### 8.2. Ghi nhận heap và dung lượng tạm

Ví dụ Java:

~~~java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ResourceSnapshot {

    public static void log() throws IOException {
        Runtime runtime = Runtime.getRuntime();
        FileStore tempStore = Files.getFileStore(Path.of("/tmp"));

        System.out.println("heap.max.bytes=" + runtime.maxMemory());
        System.out.println("heap.total.bytes=" + runtime.totalMemory());
        System.out.println("heap.free.bytes=" + runtime.freeMemory());
        System.out.println("tmp.usable.bytes=" + tempStore.getUsableSpace());
        System.out.println("cpu.visible="
                + runtime.availableProcessors());
        System.out.println("architecture="
                + System.getProperty("os.arch"));
    }
}
~~~

`Runtime.maxMemory()` là giới hạn heap mà JVM có thể sử dụng, không phải tổng memory của Lambda. `freeMemory()` cũng không phải số memory còn trống của execution environment; nó chỉ mô tả phần heap hiện chưa được sử dụng trong vùng heap đã cấp. Muốn quan sát tổng memory, cần kết hợp REPORT log, Lambda Insights hoặc công cụ giám sát phù hợp.

Ghi snapshot ở các điểm có ý nghĩa như sau khi khởi tạo, trước/sau batch lớn hoặc khi xử lý file lớn. Không nhất thiết log mỗi vòng lặp vì log quá nhiều làm tăng chi phí và gây nhiễu.

### 8.3. Đọc REPORT log

Một dòng REPORT có thể hiển thị các trường như `Duration`, `Billed Duration`, `Memory Size` và `Max Memory Used`. Khi phân tích:

- Nếu `Max Memory Used` gần `Memory Size`, thử tăng memory hoặc giảm peak allocation/batch.
- Nếu memory còn dư nhưng `Duration` cao, kiểm tra CPU, I/O, lock, retry và dependency latency.
- Nếu `Init Duration` cao, xem framework, class loading, dependency initialization và cold start.
- Nếu function timeout, xem bước cuối cùng đã hoàn tất, deadline caller và timeout của dependency.
- Nếu log có lỗi không đủ disk, kiểm tra file tồn tại, dung lượng `/tmp` và file được giữ lại từ invocation trước.

Không chỉ nhìn một invocation. Hãy xem phân bố theo thời gian và theo payload: p50, p95, p99, trường hợp lớn nhất, cold start và warm invocation.

## 9. Quy trình tuning cấu hình

Tuning là quá trình tìm cấu hình đáp ứng latency, độ ổn định và chi phí của workload. Thay đổi một tham số có thể ảnh hưởng đến nhiều tham số khác. Ví dụ, tăng memory vừa tăng giới hạn RAM vừa tăng CPU; nếu function chạy nhanh hơn, timeout có thể được giảm, nhưng phải đo lại ở payload lớn và lúc dependency chậm.

### 9.1. Xác định workload đại diện

Trước khi thay đổi cấu hình, hãy mô tả workload:

- Loại trigger: HTTP, SQS, EventBridge, S3 hoặc workflow.
- Kích thước payload thường gặp, p95 và giới hạn lớn nhất.
- Tỷ lệ CPU, I/O, disk và thời gian chờ dependency.
- Số lượng item trong batch và concurrency trong một invocation.
- Tần suất invocation, concurrency toàn function và theo tenant.
- Yêu cầu latency, deadline và tỷ lệ lỗi chấp nhận được.
- Các tác động nghiệp vụ có thể xảy ra khi retry hoặc timeout.

Không benchmark chỉ bằng một payload nhỏ. Một function xử lý tốt file 1 MB có thể hết memory hoặc `/tmp` khi nhận file 200 MB. Dùng dữ liệu đại diện và dữ liệu biên theo giới hạn sản phẩm.

### 9.2. Tuning memory

Một quy trình thực tế:

1. Chọn memory ban đầu đủ để function khởi động và xử lý payload thử nghiệm.
2. Chạy cùng một bộ dữ liệu ở một số mức memory khác nhau.
3. Giữ nguyên architecture, runtime, artifact, concurrency và cấu hình dependency trong mỗi lần so sánh.
4. Ghi nhận `Duration`, `Billed Duration`, `Max Memory Used`, error rate và chi phí ước tính.
5. Lặp lại với cold start, warm invocation và concurrency gần production.
6. Chọn cấu hình đáp ứng latency và có headroom memory, không chỉ chọn cấu hình có duration thấp nhất.
7. Kiểm tra lại sau khi thay đổi dependency, framework, payload hoặc số thread.

Có thể dùng AWS Lambda Power Tuning để chạy thử nhiều mức memory và so sánh thời gian/chi phí. Công cụ này hỗ trợ ra quyết định, nhưng kết quả chỉ có ý nghĩa khi input, concurrency và môi trường thử nghiệm đại diện cho production.

### 9.3. Tuning timeout

Đặt timeout dựa trên thời gian xử lý ở percentile cao và giới hạn nghiệp vụ. Ví dụ, nếu p99 của function là 4 giây, không có nghĩa timeout 4 giây là an toàn; cần thêm thời gian cho biến động, cold start liên quan, retry nội bộ và phản hồi.

Một số nguyên tắc:

- Timeout phải nhỏ hơn deadline của caller nếu caller cần nhận kết quả đồng bộ.
- Timeout dependency phải nhỏ hơn thời gian còn lại của Lambda.
- Retry phải nằm trong tổng ngân sách thời gian.
- Batch lớn nhất được phép phải hoàn thành trước timeout hoặc được chia nhỏ hơn.
- Nếu thời gian xử lý có thể kéo dài không dự đoán được, chuyển sang job bất đồng bộ.
- Theo dõi timeout thực tế thay vì chỉ tăng timeout khi thấy lỗi.

Không dùng timeout để kiểm soát tốc độ hệ thống. Nếu dependency quá tải, timeout dài hơn có thể làm request giữ connection và tài nguyên lâu hơn, khiến tình trạng nghẽn nặng hơn.

### 9.4. Tuning ephemeral storage

Ước lượng peak disk space, không chỉ kích thước file đầu vào:

`peak temporary space ≈ input files + extracted files + intermediate files + output files + concurrent workspaces`

Ví dụ, một file ZIP 300 MB có thể giải nén thành 1,2 GB. Nếu function đồng thời giữ file ZIP, thư mục đã giải nén và file đầu ra 500 MB, nhu cầu có thể vượt xa 300 MB. Nếu có hai tác vụ xử lý song song trong cùng environment, cần tính cả workspace của cả hai.

Bắt đầu với 512 MB nếu workload nhỏ. Tăng dần khi phép đo cho thấy peak usage cần thêm dung lượng. Dành headroom cho file tạm do thư viện tạo và các thay đổi kích thước dữ liệu. Đồng thời xem xét streaming, xử lý theo batch hoặc lưu trung gian lên S3 nếu `/tmp` không phù hợp.

### 9.5. Benchmark architecture

Để so sánh `x86_64` và `arm64`, dùng cùng:

- Memory và ephemeral storage.
- Runtime version và framework.
- Phiên bản code, dependency và cấu hình.
- Bộ input, số lần chạy và mức concurrency.
- Khu vực triển khai và điều kiện của dịch vụ phụ thuộc.

Đo cold start riêng với warm duration. Đo cả latency và cost per successful invocation. Nếu dependency có native library, kiểm tra cả compatibility lẫn hành vi lỗi ở tải cao. Một lần chạy nhanh hơn không đủ chứng minh kiến trúc đó tốt hơn nếu error rate hoặc memory usage tăng.

### 9.6. Ma trận benchmark mẫu

| Lần thử | Architecture | Memory | Timeout | `/tmp` | Mục tiêu |
|---|---|---:|---:|---:|---|
| A | `x86_64` | 1.024 MB | 30 giây | 512 MB | Baseline |
| B | `x86_64` | 2.048 MB | 30 giây | 512 MB | Đo ảnh hưởng memory/CPU |
| C | `arm64` | 2.048 MB | 30 giây | 512 MB | So sánh architecture |
| D | `arm64` | 2.048 MB | 60 giây | 2.048 MB | Kiểm tra workload file lớn |

Đây là ma trận minh họa, không phải khuyến nghị cấu hình cho mọi function. Khi so sánh memory, chỉ đổi memory; khi so sánh architecture, giữ các tham số khác như nhau. Lần thử D thay đổi cả timeout và storage để kiểm tra một workload khác, không dùng kết quả D để kết luận riêng tác động của architecture.

## 10. Cấu hình tham khảo theo loại workload

Các profile dưới đây là điểm bắt đầu để thiết kế thử nghiệm. Giá trị cuối cùng phải dựa trên đo lường và giới hạn của ứng dụng.

| Loại function | Memory | Timeout | Ephemeral storage | Architecture |
|---|---|---|---|---|
| HTTP handler nhỏ, chủ yếu I/O | Bắt đầu thấp rồi đo | Ngắn theo deadline API | Mặc định nếu không dùng file | Cả hai, benchmark dependency |
| Xử lý JSON/batch nhỏ | Theo peak heap và CPU | Theo kích thước batch | Mặc định hoặc thấp | Cả hai |
| Resize ảnh/giải nén file | Thường cần memory cao hơn | Theo kích thước file | Tính theo input + output + intermediate | Benchmark cả hai |
| CPU-intensive | Đo nhiều mức memory vì memory ảnh hưởng CPU | Theo thời gian xử lý p99 | Chỉ tăng nếu có file tạm | Benchmark cả hai |
| Worker đọc queue | Theo payload và số message trong batch | Đủ xử lý batch, không vượt visibility budget | Theo cách xử lý file | Theo native dependency |
| Export/report lớn | Chia batch hoặc chạy bất đồng bộ | Ngắn cho bước nhận job; worker có giới hạn phù hợp | Theo file trung gian hoặc dùng S3 | Benchmark theo workload |

Một function HTTP nhỏ có thể chạy tốt ở memory thấp nhưng vẫn cần kiểm tra cold start của Java runtime và framework. Một worker ảnh có thể cần memory cao vì CPU và buffer, đồng thời cần `/tmp` lớn vì file giải nén. Hai nhu cầu phải được đo riêng.

## 11. Các lỗi cấu hình thường gặp

- **Coi memory là Java heap:** đặt heap gần bằng toàn bộ memory Lambda có thể khiến native memory hoặc thread stack vượt giới hạn.
- **Tăng memory để sửa mọi lỗi chậm:** nếu bottleneck nằm ở database hoặc API ngoài, tăng memory có thể không giải quyết nguyên nhân.
- **Đặt timeout theo thời gian trung bình:** request p99 hoặc batch lớn có thể timeout dù trường hợp trung bình chạy tốt.
- **Đặt timeout dài để che lỗi dependency:** function giữ tài nguyên lâu hơn trong khi dịch vụ phụ thuộc vẫn không phản hồi.
- **Nhầm `/tmp` với bộ nhớ hoặc kho bền vững:** file tạm có giới hạn riêng, có thể mất khi environment bị thu hồi và không chia sẻ giữa environment.
- **Không dọn file tạm:** invocation ấm tiếp theo có thể gặp disk đầy do file cũ.
- **Chọn ARM64 mà không kiểm tra JNI/layer:** function có thể deploy được nhưng lỗi khi load native library.
- **Benchmark khác cấu hình:** đổi memory, architecture và batch cùng lúc khiến không xác định được nguyên nhân hiệu năng thay đổi.
- **Bỏ qua concurrency toàn function:** nhiều invocation có thể làm database hoặc API ngoài quá tải dù một invocation riêng lẻ chạy tốt.
- **Quên cập nhật IaC:** thay đổi trên Console bị template ghi đè trong lần deploy tiếp theo.
- **Quên published version/alias:** traffic có thể vẫn chạy version cũ dù `$LATEST` đã có cấu hình mới.

## 12. Checklist trước khi đưa cấu hình vào production

- [ ] Memory đủ cho peak heap và native memory với headroom phù hợp.
- [ ] Timeout đáp ứng deadline của caller và workload p99.
- [ ] Timeout của HTTP/database client nhỏ hơn thời gian Lambda còn lại.
- [ ] Retry và idempotency đã được thiết kế cho thao tác có side effect.
- [ ] Dung lượng `/tmp` đủ cho input, extracted data, intermediate và output đồng thời.
- [ ] File tạm được tạo bằng tên an toàn, đóng stream và dọn dẹp.
- [ ] Dữ liệu cần lưu lâu dài được đưa vào S3/EFS/database.
- [ ] Architecture tương thích với JAR, layer, container image, JNI và executable native.
- [ ] Concurrency phù hợp với quota và capacity của downstream.
- [ ] Đã benchmark cold start, warm duration, memory, disk và error rate.
- [ ] Template IaC phản ánh đúng cấu hình đã kiểm chứng.
- [ ] Published version và alias trỏ đến cấu hình đã xác nhận.
- [ ] Có dashboard/cảnh báo cho duration, errors, throttles, concurrency và memory.
- [ ] Có custom log/metric về `/tmp` nếu workload phụ thuộc dung lượng file tạm.

## 13. Tự kiểm tra

**Câu 1.** Vì sao tăng memory của Lambda có thể làm function chạy nhanh hơn dù Java heap không phải nút thắt?

**Gợi ý trả lời:** Lambda phân bổ CPU tăng theo memory. Tác vụ CPU-intensive hoặc các giai đoạn serialize, nén và xử lý dữ liệu có thể hoàn thành nhanh hơn khi function được cấp thêm CPU.

**Câu 2.** Vì sao không nên đặt `-Xmx` bằng toàn bộ memory Lambda?

**Gợi ý trả lời:** Tổng memory còn gồm metaspace, thread stack, direct buffer, JIT/code cache và native library. Heap chiếm hết giới hạn có thể khiến process thiếu memory ngoài heap.

**Câu 3.** Ephemeral storage khác memory thế nào?

**Gợi ý trả lời:** Memory chứa dữ liệu process/JVM đang sử dụng; ephemeral storage là vùng disk tạm tại `/tmp`. Tăng một loại tài nguyên không tự tăng loại còn lại. `/tmp` không phải nơi lưu dữ liệu bền vững hoặc chia sẻ giữa các environment.

**Câu 4.** Khi nào nên tăng timeout và khi nào nên chuyển sang xử lý bất đồng bộ?

**Gợi ý trả lời:** Tăng timeout khi công việc có thời gian xử lý hữu hạn, đo được và vẫn nằm trong deadline của caller. Chuyển sang bất đồng bộ khi công việc dài, biến động lớn hoặc cần nhiều child/batch và không phù hợp với HTTP invocation đồng bộ.

**Câu 5.** Java bytecode có chạy được trên cả `x86_64` và `arm64` không?

**Gợi ý trả lời:** Bytecode thuần Java thường di động giữa hai kiến trúc, nhưng JNI, native library, executable, layer và container image có thể phụ thuộc kiến trúc. Phải kiểm tra artifact và benchmark thực tế.

**Bài tập tình huống:** Một Java Lambda tải file ZIP 250 MB từ S3, giải nén thành khoảng 900 MB, xử lý các CSV và ghi một file kết quả 300 MB. Function hiện có memory 1.024 MB, timeout 30 giây và `/tmp` 512 MB. Một số invocation lỗi `No space left on device`, một số invocation timeout, nhưng heap chưa chạm giới hạn. Hãy đề xuất cách điều chỉnh memory, timeout và ephemeral storage; xác định khi nào nên stream hoặc chia batch; nêu cách kiểm tra architecture và các metric cần theo dõi.

**Gợi ý:** Dung lượng `/tmp` hiện tại chắc chắn không đủ nếu ZIP, dữ liệu giải nén và file kết quả cùng tồn tại. Ước lượng peak disk space từ toàn bộ file đồng thời, tăng ephemeral storage phù hợp và dọn file sau xử lý; cân nhắc stream CSV hoặc ghi kết quả theo multipart để giảm scratch space. Timeout cần dựa trên thời gian xử lý p95/p99 của file lớn và deadline của trigger/caller; nếu thời gian vượt giới hạn phù hợp, chuyển thành job bất đồng bộ. Memory chưa chạm giới hạn không có nghĩa CPU đủ; benchmark nhiều mức memory để xem CPU allocation có giảm duration không. Kiểm tra dependency native và layer trước khi thử ARM64. Theo dõi `Duration`, `Max Memory Used`, `Errors`, timeout, `/tmp` usable space, concurrency và latency của S3.

## Kết luận

Memory của Lambda vừa giới hạn RAM vừa ảnh hưởng đến năng lực CPU; với Java, cần chừa bộ nhớ cho heap và các vùng native của JVM. Timeout phải phù hợp với deadline end-to-end và timeout của dependency. Ephemeral storage tại `/tmp` phục vụ file tạm, có vòng đời theo execution environment và không thay thế kho dữ liệu bền vững. `x86_64` và `arm64` cần được chọn dựa trên compatibility và benchmark cùng điều kiện. Quản lý cấu hình bằng IaC, đo cold/warm invocation và theo dõi peak memory, duration, concurrency cùng dung lượng tạm giúp function đạt hiệu năng và chi phí phù hợp.
