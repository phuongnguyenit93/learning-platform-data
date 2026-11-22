# Giới hạn thời gian, bộ nhớ, payload và tài nguyên tạm

Ứng dụng serverless thường được triển khai dưới dạng một hoặc nhiều function chạy khi có HTTP request, thông điệp trong hàng đợi hoặc sự kiện từ dịch vụ khác. Mỗi lần chạy được cấp một ngân sách tài nguyên hữu hạn. Function có thể chạy đúng trên máy phát triển nhưng thất bại khi lên cloud nếu xử lý quá lâu, dùng quá nhiều bộ nhớ, nhận payload quá lớn hoặc làm đầy vùng lưu trữ tạm.

Hiểu các giới hạn này giúp người phát triển Java chọn đúng cách chia nhỏ công việc, đặt timeout, xử lý dữ liệu theo luồng và quyết định khi nào FaaS phù hợp. Các con số cụ thể phụ thuộc nhà cung cấp, dịch vụ kích hoạt, vùng triển khai, cấu hình và thời điểm. Vì vậy, cần tra quota hiện hành của từng dịch vụ trước khi thiết kế; không có một giới hạn chung áp dụng cho mọi nền tảng serverless.

## 1. Bốn nhóm giới hạn cần phân biệt

| Nhóm | Giới hạn kiểm soát điều gì? | Khi vượt giới hạn, điều gì có thể xảy ra? |
|---|---|---|
| Thời gian (execution timeout) | Thời lượng tối đa cho một lần thực thi | Nền tảng dừng function; request có thể timeout; message hoặc event có thể được retry tùy trigger |
| Bộ nhớ (memory) | RAM mà runtime và mã ứng dụng được phép sử dụng | Function có thể bị kết thúc, bị runtime đánh dấu lỗi hoặc gặp OutOfMemoryError |
| Payload | Kích thước request, event, message, batch hoặc response được truyền qua từng dịch vụ | Dịch vụ có thể từ chối request, không đưa message vào queue, không gọi được function hoặc không trả được response |
| Tài nguyên tạm | Dung lượng đĩa tạm, file descriptor, thread, socket và các tài nguyên có vòng đời ngắn | Ghi file thất bại, hết tài nguyên hệ điều hành, cạn connection hoặc function chậm và lỗi |

Các giới hạn có liên quan nhưng không thay thế cho nhau. Tăng bộ nhớ không tự động tăng kích thước payload. Tăng timeout không giúp một request vượt giới hạn của API gateway. Thêm dung lượng đĩa tạm cũng không làm cho dữ liệu trên đĩa trở thành dữ liệu bền vững.

Một request HTTP có thể đi qua nhiều lớp: client, load balancer hoặc API gateway, function, rồi dịch vụ phía sau. Mỗi lớp có timeout và giới hạn kích thước riêng. Với message hoặc event, giới hạn có thể nằm ở producer, queue, event bus, kích thước batch và function. Khi phân tích lỗi, cần xác định chính xác lớp nào từ chối hoặc dừng xử lý.

## 2. Giới hạn thời gian thực thi

### 2.1. Timeout của function và timeout của dịch vụ gọi nó

Execution timeout là thời gian tối đa nền tảng cho phép một invocation chạy. Thời gian này có thể bao gồm khởi tạo runtime, nạp thư viện, xử lý đầu vào, gọi dịch vụ ngoài và tạo kết quả; cách tính cụ thể tùy nền tảng.

Với HTTP đồng bộ, client hoặc API gateway có thể hết thời gian chờ trước khi function đạt execution timeout. Ví dụ, function được cấu hình chạy tối đa lâu hơn gateway, nhưng gateway đã đóng kết nối thì người gọi vẫn không nhận được kết quả. Function thậm chí có thể tiếp tục chạy trong một khoảng thời gian nếu nền tảng cho phép. Vì vậy, cần kiểm tra cả timeout của function lẫn timeout của mọi thành phần trên đường đi.

Với xử lý bất đồng bộ, người gửi thường nhận xác nhận đã tiếp nhận sự kiện trước khi function hoàn thành. Nếu invocation timeout hoặc lỗi, nền tảng có thể thử lại, đưa sự kiện vào dead-letter queue hoặc lưu vào nơi đích xử lý lỗi. Chính sách retry, thời hạn lưu event và số lần thử khác nhau theo dịch vụ. Không nên suy luận rằng timeout đồng nghĩa với sự kiện chắc chắn bị mất hoặc chắc chắn được chạy lại.

### 2.2. Chia ngân sách thời gian

Không nên dùng toàn bộ thời gian cho phần xử lý chính. Một invocation còn cần thời gian đọc và giải mã đầu vào, gọi dịch vụ bên ngoài, ghi kết quả, đóng tài nguyên và hoàn tất response. Hãy chia ngân sách theo từng công đoạn:

~~~text
Ngân sách invocation
  = khởi tạo và đọc đầu vào
  + xử lý nghiệp vụ
  + gọi dịch vụ bên ngoài
  + ghi kết quả và tạo response
  + khoảng dự phòng
~~~

Khoảng dự phòng cho phép ứng dụng hoàn tất thao tác quan trọng và trả lỗi có kiểm soát trước khi nền tảng dừng function. Giá trị dự phòng nên được xác định bằng đo đạc trên workload thực tế, không chọn một tỷ lệ cố định cho mọi ứng dụng.

Khi gọi HTTP, cơ sở dữ liệu hoặc dịch vụ khác, đặt connect timeout và read/request timeout nhỏ hơn thời gian còn lại của invocation. Nếu một lời gọi có thể mất nhiều thời gian hơn ngân sách còn lại, hãy dừng sớm hoặc chuyển công việc sang hàng đợi. Retry phải có giới hạn, có backoff và jitter; không lặp vô hạn trong một invocation ngắn.

Đối với Java, dùng đồng hồ đơn điệu như System.nanoTime() để đo thời lượng. Đồng hồ lịch như System.currentTimeMillis() có thể thay đổi khi hệ thống đồng bộ thời gian. Nếu nền tảng cung cấp API cho biết thời gian còn lại của invocation, nên dùng API đó làm nguồn chính vì nó phản ánh deadline thực tế của runtime.

### 2.3. Xử lý công việc dài

Nếu một tác vụ có thể vượt timeout, hãy chia nó thành các bước có thể tiếp tục:

- Chia dữ liệu thành các phần nhỏ và xử lý từng phần.
- Lưu checkpoint hoặc trạng thái tiến độ ở cơ sở dữ liệu hay object storage.
- Đưa phần việc tiếp theo vào queue hoặc workflow orchestration.
- Thiết kế mỗi bước có thể chạy lại an toàn bằng idempotency key.
- Giới hạn số lần retry và đưa tác vụ lỗi kéo dài sang dead-letter queue để điều tra.

Không nên giả định một invocation sẽ hoàn thành đúng một lần. Timeout có thể xảy ra sau khi dịch vụ phía sau đã nhận lệnh nhưng trước khi function nhận được phản hồi. Khi retry, lệnh có thể được gửi lại. Với thao tác tạo đơn hàng, trừ tiền hoặc gửi thông báo, hãy dùng khóa idempotency, ràng buộc duy nhất hoặc cơ chế ghi nhận trạng thái để tránh tạo hiệu ứng trùng lặp.

## 3. Giới hạn bộ nhớ

### 3.1. Bộ nhớ của function không chỉ là Java heap

Giới hạn RAM cấu hình cho function phải chứa toàn bộ tiến trình, không chỉ các object Java. Các phần sử dụng bộ nhớ có thể gồm:

- Java heap: object, collection, chuỗi và dữ liệu được giải mã.
- Metaspace và dữ liệu lớp: thông tin class, proxy và thư viện đã nạp.
- Thread stack: mỗi thread có vùng stack riêng.
- Bộ nhớ native và direct buffer: TLS, NIO, compression, thư viện JNI và các thành phần của JVM.
- Runtime, JIT compiler, agent và thư viện của nền tảng.

Do đó, đặt Xmx bằng toàn bộ giới hạn RAM là rủi ro. Khi heap chiếm gần hết ngân sách, JVM vẫn cần bộ nhớ ngoài heap để hoạt động. Hãy để lại khoảng trống dựa trên số liệu đo được trong môi trường triển khai.

Trong Java, Runtime.getRuntime().maxMemory() cho biết giới hạn heap tối đa mà JVM nhìn thấy; nó không phải tổng RAM mà function đang dùng. Runtime.getRuntime().freeMemory() cũng không cho biết lượng RAM còn trống của container. Hãy kết hợp số liệu JVM với metric bộ nhớ của nền tảng.

### 3.2. Những nguyên nhân thường làm tăng bộ nhớ đỉnh

Một số mẫu code có thể khiến bộ nhớ tăng nhanh:

- Đọc toàn bộ file hoặc request vào byte[] rồi tạo thêm String và object tree.
- Parse JSON lớn thành nhiều object lồng nhau trong khi chỉ cần vài trường.
- Giữ kết quả của tất cả bản ghi trong List trước khi ghi ra đích.
- Tạo nhiều bản sao dữ liệu khi chuyển đổi encoding, serialize hoặc nén.
- Nạp thư viện lớn hoặc khởi tạo nhiều client cho mỗi invocation.
- Tạo thread, future hoặc task không có giới hạn.
- Giữ dữ liệu invocation trong biến static lâu hơn cần thiết.

Ví dụ, đọc một payload có kích thước P vào byte[], chuyển thành String và parse thành object có thể tạo ra mức sử dụng bộ nhớ lớn hơn nhiều lần P. Hệ số tăng phụ thuộc encoding, cấu trúc JSON và cách thư viện biểu diễn object. Vì vậy, kích thước request không thể được dùng trực tiếp làm dự báo RAM.

### 3.3. Cách kiểm soát bộ nhớ trong Java

Ưu tiên xử lý theo luồng (streaming) khi dữ liệu lớn. Đọc theo buffer có kích thước cố định, xử lý xong từng phần rồi giải phóng tham chiếu. Với JSON lớn, dùng parser dạng streaming thay vì luôn parse toàn bộ thành cây object. Khi ghi kết quả, cân nhắc ghi từng batch nhỏ.

Giới hạn kích thước collection và số tác vụ chạy đồng thời. Dùng thread pool có số thread và hàng đợi hữu hạn. Nếu hàng đợi đầy, từ chối hoặc áp dụng backpressure thay vì âm thầm tích lũy công việc trong heap. Tái sử dụng client thread-safe ở phạm vi execution environment nếu thư viện cho phép, nhưng không giữ dữ liệu riêng của một người dùng trong biến static.

Tăng memory allocation có thể giúp một số nền tảng cấp thêm CPU hoặc cải thiện tốc độ xử lý, nhưng điều này phụ thuộc nhà cung cấp. Cần benchmark nhiều cấu hình với cùng workload và so sánh cả duration, memory peak, số lần throttling và chi phí. Chọn cấu hình theo độ trễ và chi phí mục tiêu, không chỉ theo mức RAM lớn nhất.

## 4. Giới hạn payload và cách truyền dữ liệu lớn

### 4.1. Kích thước bị giới hạn ở nhiều điểm

Payload là dữ liệu đi qua ranh giới giữa các dịch vụ: HTTP body, message, event, từng record trong batch hoặc response. Các điểm giới hạn có thể gồm:

- Client, proxy, load balancer và API gateway.
- Dịch vụ nhận request hoặc dịch vụ tích hợp với function.
- Queue, topic hoặc event bus.
- Kích thước một message, tổng kích thước batch và số record mỗi batch.
- Giới hạn event mà nền tảng chuyển vào function.
- Kích thước response đồng bộ hoặc dữ liệu trả về từ function.

Giới hạn request và response có thể khác nhau. Giới hạn của function cũng có thể khác giới hạn của gateway hoặc queue. Một request có thể được gateway chấp nhận nhưng không thể chuyển tiếp đến function. Vì vậy, hãy xác minh giới hạn trên toàn tuyến và kiểm tra cả payload sau serialize.

Khi mã hóa nhị phân thành Base64, dữ liệu thường tăng kích thước khoảng một phần ba, chưa tính phần bao JSON và metadata. Nén có thể giảm kích thước truyền nhưng cần CPU và RAM để nén/giải nén; không nên xem nén là cách bảo đảm vượt qua mọi quota.

### 4.2. Khi payload nhỏ

Với request nhỏ và có giới hạn rõ ràng, function có thể xác thực, giải mã và xử lý trực tiếp. Dù vậy, nên:

- Kiểm tra kích thước trước khi parse sâu.
- Kiểm tra kiểu dữ liệu, số trường, độ dài chuỗi và độ sâu cấu trúc.
- Trả lỗi đầu vào quá lớn một cách rõ ràng.
- Tránh ghi toàn bộ payload vào log.
- Không tin rằng client luôn gửi đúng Content-Length hoặc metadata kích thước.

Nếu nền tảng đã chuyển toàn bộ event vào bộ nhớ trước khi gọi handler, kiểm tra trong handler chỉ ngăn ứng dụng cấp phát thêm quá nhiều RAM; nó không thể đảo ngược chi phí tiếp nhận payload đã xảy ra ở lớp runtime.

### 4.3. Khi payload lớn

Không nên nhét nội dung file lớn vào HTTP body hoặc message nếu dịch vụ có giới hạn thấp hơn. Một mẫu phổ biến là lưu nội dung ở object storage rồi truyền tham chiếu:

1. Client tải file trực tiếp lên object storage bằng URL được cấp quyền và có thời hạn.
2. Sau khi tải xong, client gửi một event nhỏ chứa object key, bucket/container, mã nghiệp vụ và metadata cần thiết.
3. Function đọc file theo luồng hoặc theo từng phần.
4. Function ghi kết quả ra object storage hoặc cơ sở dữ liệu.
5. Hệ thống lưu trạng thái xử lý và phát event hoàn tất nếu cần.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Object Storage
    participant Q as Queue hoặc Event Bus
    participant F as Java Function
    C->>S: Tải file trực tiếp
    S-->>C: Xác nhận object key
    C->>Q: Gửi event nhỏ chứa object key
    Q->>F: Kích hoạt function
    F->>S: Đọc file theo luồng
    F->>S: Ghi kết quả hoặc checkpoint
    F-->>Q: Hoàn tất hoặc báo lỗi
~~~

Cách này giảm payload đi qua queue và function, đồng thời cho phép retry bằng tham chiếu đến cùng một object. Cần kiểm tra quyền truy cập, thời hạn URL, vòng đời object, kích thước file, checksum và việc object có bị thay đổi trong lúc xử lý hay không.

Với queue, cân nhắc chia message lớn thành các phần nhỏ có sequence number và mã định danh chung. Người tiêu thụ cần phát hiện phần thiếu, phần trùng và thứ tự không mong muốn. Nếu nghiệp vụ cần xử lý cả file như một đơn vị, hãy lưu manifest để theo dõi trạng thái các phần.

## 5. Tài nguyên tạm trong môi trường serverless

### 5.1. Đĩa tạm và thư mục /tmp

Nhiều nền tảng cung cấp một vùng lưu trữ tạm cục bộ cho mỗi execution environment, thường được gắn tại một thư mục như /tmp. Ứng dụng có thể dùng vùng này để tải file, giải nén, tạo báo cáo hoặc trao đổi dữ liệu với thư viện chỉ hỗ trợ file.

Vùng đĩa tạm có quota riêng. Dung lượng còn trống có thể giảm qua nhiều invocation nếu file không được dọn. Một số nền tảng giữ execution environment sống qua nhiều invocation, nên file còn sót có thể xuất hiện ở lần chạy sau. Tuy nhiên, môi trường có thể bị thay thế bất kỳ lúc nào; file tạm không phải nơi lưu dữ liệu bền vững và không được dùng làm nguồn sự thật.

Khi dùng file tạm:

- Tạo tên file duy nhất, tránh ghi đè giữa các invocation.
- Đóng stream trong try-with-resources.
- Xóa file trong khối finally, kể cả khi xử lý lỗi.
- Kiểm tra dung lượng trước khi tải hoặc giải nén.
- Giới hạn số file và kích thước file được xử lý đồng thời.
- Không dựa vào file còn tồn tại ở lần invocation tiếp theo.
- Không ghi dữ liệu nhạy cảm nếu không có biện pháp bảo vệ phù hợp.

Ví dụ Java:

~~~java
Path tempFile = Files.createTempFile("serverless-", ".bin");

try {
    try (InputStream input = source;
         OutputStream output = Files.newOutputStream(tempFile)) {
        input.transferTo(output);
    }

    processFile(tempFile);
} finally {
    Files.deleteIfExists(tempFile);
}
~~~

Đoạn mã giả định function sở hữu InputStream và có trách nhiệm đóng stream. Nếu stream do framework quản lý, cần tuân theo hợp đồng của framework thay vì đóng tài nguyên mà ứng dụng không sở hữu.

Nếu xử lý file nén, hãy giới hạn cả kích thước file nén lẫn tổng kích thước sau giải nén, số lượng entry và độ sâu thư mục. Một file nén nhỏ có thể bung ra thành dữ liệu rất lớn, làm cạn đĩa hoặc bộ nhớ.

### 5.2. File descriptor, thread và connection

Ngoài đĩa, function còn sử dụng các tài nguyên hệ điều hành:

- File descriptor cho file, socket và pipe.
- Thread và thread stack.
- Kết nối HTTP, cơ sở dữ liệu và message broker.
- Bộ đệm trực tiếp và tài nguyên native.

Nếu mỗi invocation tạo một HTTP client hoặc connection pool mới rồi không đóng, số socket có thể tăng qua các lần chạy. Nếu tạo thread mới cho từng record, function có thể cạn thread hoặc bộ nhớ stack. Hãy tái sử dụng client phù hợp, đóng tài nguyên đúng cách, đặt giới hạn pool và dùng timeout cho kết nối.

Mức đồng thời của một execution environment phụ thuộc runtime và nền tảng. Không nên mặc định mọi function chỉ có một invocation tại một thời điểm hoặc mọi biến static đều an toàn. Nếu ứng dụng có thể xử lý song song trong cùng process, trạng thái dùng chung phải thread-safe và dữ liệu của invocation phải được cô lập.

## 6. Thiết kế theo loại trigger

| Trigger | Rủi ro nổi bật | Cách thiết kế phù hợp |
|---|---|---|
| HTTP đồng bộ | Gateway hoặc client timeout trước function; response vượt giới hạn | Xác thực nhanh, giới hạn body, đặt timeout theo ngân sách đầu-cuối; tác vụ dài trả mã tiếp nhận và xử lý nền |
| Queue/message | Message hoặc batch vượt quota; retry tạo xử lý trùng; một record lỗi ảnh hưởng batch | Giới hạn kích thước và batch; xử lý idempotent; dùng partial batch response nếu dịch vụ hỗ trợ; cấu hình retry và DLQ |
| Event bất đồng bộ | Event có thể đến trễ, lặp hoặc sai thứ tự; function timeout | Xử lý event độc lập, lưu trạng thái, chống trùng, đặt chính sách retry và nơi nhận lỗi |
| Event từ object storage | File lớn hoặc object bị thay đổi/xóa trước khi xử lý | Truyền object key và version/checksum; đọc theo luồng; quản lý quyền và vòng đời object |

HTTP phù hợp khi người gọi cần kết quả nhanh và công việc có giới hạn rõ ràng. Nếu thời gian xử lý không dự đoán được, có thể trả về mã tiếp nhận cùng job ID, sau đó xử lý qua queue hoặc workflow. Người gọi truy vấn trạng thái bằng một endpoint khác.

Với queue, kích thước batch ảnh hưởng cả thời gian và bộ nhớ. Batch lớn giảm overhead gọi function nhưng tăng bộ nhớ đỉnh và nguy cơ một record lỗi khiến nhiều record phải chạy lại. Chọn batch size dựa trên thời gian xử lý mỗi record, kích thước dữ liệu và cơ chế retry của dịch vụ. Khi nền tảng hỗ trợ báo lỗi từng record, sử dụng nó để tránh phát lại toàn bộ batch không cần thiết.

## 7. Ví dụ Java: đọc dữ liệu có giới hạn

Đoạn mã sau đọc một InputStream theo buffer cố định và từ chối dữ liệu vượt quá ngưỡng do ứng dụng đặt. Đây là giới hạn ở tầng ứng dụng; nó không thay thế quota của gateway, queue hoặc nền tảng.

~~~java
static void copyWithLimit(
        InputStream input,
        OutputStream output,
        long maxBytes) throws IOException {

    if (maxBytes < 0) {
        throw new IllegalArgumentException("maxBytes must be non-negative");
    }

    byte[] buffer = new byte[64 * 1024];
    long total = 0;
    int count;

    while ((count = input.read(buffer)) != -1) {
        total += count;

        if (total > maxBytes) {
            throw new IOException("Payload exceeds the application limit");
        }

        output.write(buffer, 0, count);
    }
}
~~~

Trong ví dụ này, bộ nhớ cho buffer không tăng theo kích thước file. Dữ liệu được ghi ra đích sau từng lần đọc. Nếu đích là file tạm, cần đóng stream và xóa file khi thất bại. Nếu đích là object storage hoặc dịch vụ mạng, cần đặt timeout và xử lý lỗi ghi giữa chừng.

## 8. Đo lường và kiểm thử giới hạn

Không thể chọn cấu hình đáng tin cậy chỉ từ kích thước trung bình của request. Hãy kiểm thử bằng dữ liệu đại diện và trường hợp xấu:

1. Đo thời gian cold start và warm invocation riêng nếu nền tảng cung cấp metric.
2. Thử payload nhỏ, payload gần giới hạn ứng dụng và payload vượt giới hạn.
3. Thử file có nhiều record, record lớn bất thường và dữ liệu nén có tỷ lệ bung cao.
4. Thử dịch vụ phía sau phản hồi chậm, mất kết nối hoặc trả lỗi tạm thời.
5. Thử nhiều invocation đồng thời để phát hiện cạn connection, thread hoặc bộ nhớ.
6. Thử function timeout ở các thời điểm khác nhau để xác minh retry và idempotency.
7. Theo dõi dung lượng đĩa tạm qua nhiều invocation trong cùng execution environment nếu nền tảng giữ môi trường sống.

Các metric hữu ích gồm duration, timeout count, error count, throttling, memory used/peak, kích thước payload, số record mỗi batch, retry count, tuổi của message, số kết nối đang mở và dung lượng đĩa tạm. Gắn request ID, correlation ID hoặc job ID vào log để nối các bước xử lý. Log kích thước và metadata cần thiết; tránh ghi toàn bộ nội dung request hoặc dữ liệu nhạy cảm.

Nên quan sát percentile như p95 và p99, không chỉ trung bình. Một function có thời gian trung bình thấp vẫn có thể thường xuyên timeout khi gặp file lớn hoặc dịch vụ phía sau chậm. Đặt cảnh báo trước khi chạm quota để còn thời gian điều chỉnh batch size, memory, timeout hoặc cách chia tác vụ.

## 9. Quy trình chọn cấu hình

Có thể áp dụng quy trình sau cho mỗi function:

1. **Xác định đường đi của dữ liệu.** Liệt kê client, gateway, trigger, function và dịch vụ phía sau; ghi lại timeout và quota của từng lớp.
2. **Đặt giới hạn nghiệp vụ.** Xác định kích thước tối đa, số record, thời gian xử lý mục tiêu và mức đồng thời dự kiến.
3. **Chọn cách truyền dữ liệu.** Dữ liệu nhỏ có thể nằm trong request hoặc event; dữ liệu lớn nên được lưu ở object storage và truyền tham chiếu.
4. **Đo mức dùng tài nguyên.** Kiểm tra thời gian, heap, native memory, đĩa tạm, thread và connection với dữ liệu đại diện.
5. **Đặt ngân sách và khoảng dự phòng.** Timeout của lời gọi con phải nằm trong deadline còn lại; heap phải chừa chỗ cho phần native và runtime.
6. **Kiểm tra retry và tính idempotent.** Mô phỏng timeout sau khi một thao tác bên ngoài đã hoàn thành nhưng function chưa nhận được phản hồi.
7. **Theo dõi sau triển khai.** Dùng metric và log để phát hiện workload thay đổi, sau đó điều chỉnh cấu hình hoặc chia nhỏ tác vụ.

Khi một function thường xuyên cần thời gian rất dài, lượng RAM lớn, xử lý dữ liệu liên tục hoặc giữ trạng thái cục bộ lâu dài, hãy đánh giá worker/container hoặc dịch vụ xử lý chuyên dụng. FaaS phù hợp nhất khi công việc có thể chia thành invocation hữu hạn, mở rộng theo sự kiện và không phụ thuộc vào trạng thái cục bộ bền vững.

## 10. Những câu hỏi cần tự kiểm tra

- Timeout của function và timeout của gateway có quan hệ thế nào?
- Vì sao giới hạn heap không bằng giới hạn RAM của function?
- Vì sao đọc toàn bộ payload vào byte[] có thể dùng RAM lớn hơn kích thước payload?
- Khi nào nên truyền object key thay vì đưa file vào message?
- Vì sao file trong /tmp không được dùng làm trạng thái bền vững?
- Một invocation timeout sau khi đã ghi dữ liệu ra hệ thống khác có thể gây vấn đề gì khi retry?
- Những metric nào giúp phát hiện function sắp chạm giới hạn bộ nhớ hoặc thời gian?

Trả lời được các câu hỏi này giúp người phát triển đánh giá function theo toàn bộ vòng đời dữ liệu: dữ liệu được tiếp nhận ở đâu, tiêu thụ bao nhiêu tài nguyên, được lưu ở đâu, và điều gì xảy ra khi invocation kết thúc hoặc được chạy lại.

