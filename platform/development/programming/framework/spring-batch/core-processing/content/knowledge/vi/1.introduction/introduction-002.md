# Batch processing khác xử lý request trực tuyến ra sao?

Batch processing (xử lý theo lô) và xử lý request trực tuyến đều thực hiện logic nghiệp vụ trên dữ liệu. Điểm khác nhau nằm ở cách công việc được khởi chạy, đơn vị dữ liệu được xử lý, thời gian hoàn thành mà người gọi kỳ vọng và cách hệ thống quản lý lỗi.

Với request trực tuyến, ứng dụng thường xử lý một yêu cầu nhỏ trong lúc người dùng hoặc hệ thống khác đang chờ kết quả. Với batch processing, ứng dụng gom nhiều bản ghi thành một công việc có điểm bắt đầu và kết thúc rõ ràng, xử lý chúng theo từng bước rồi lưu kết quả và trạng thái chạy. Một job batch có thể mất vài phút hoặc vài giờ mà không cần giữ một kết nối HTTP mở trong suốt thời gian đó.

## 1. Xử lý request trực tuyến hoạt động như thế nào?

Trong mô hình trực tuyến (online request processing), client gửi một request đến ứng dụng, thường qua HTTP. Server thực hiện logic cần thiết và trả response cho chính request đó.

Một luồng điển hình có dạng:

```text
Client
  |
  | HTTP request
  v
Controller / API
  |
  v
Business service
  |
  +----> Database / Cache / External service
  |
  v
HTTP response
  |
  v
Client
```

Ví dụ, khi người dùng xem chi tiết một đơn hàng, ứng dụng nhận `GET /orders/123`, tìm đơn hàng trong cơ sở dữ liệu, áp dụng các quy tắc hiển thị và trả dữ liệu về trình duyệt. Khi người dùng tạo một đơn hàng, ứng dụng kiểm tra dữ liệu, ghi nhận đơn hàng và trả kết quả tạo đơn.

Đặc điểm thường gặp của xử lý trực tuyến:

- **Bắt đầu từ một yêu cầu cụ thể:** request của người dùng hoặc một service là nguyên nhân trực tiếp khiến logic được thực thi.
- **Đơn vị công việc nhỏ và có giới hạn:** thường là một truy vấn, một lệnh cập nhật hoặc một thao tác nghiệp vụ.
- **Có người gọi đang chờ:** client kỳ vọng nhận được kết quả trong một khoảng thời gian ngắn, phù hợp với timeout của HTTP hoặc giao thức đang dùng.
- **Độ trễ quan trọng:** thời gian phản hồi của từng request ảnh hưởng trực tiếp đến trải nghiệm người dùng và khả năng đáp ứng của hệ thống.
- **Lỗi được trả về cho caller:** chẳng hạn response `4xx` khi dữ liệu không hợp lệ hoặc `5xx` khi server gặp sự cố. Caller có thể hiển thị lỗi hoặc quyết định thử lại.

Một request trực tuyến không nhất thiết chỉ đọc một bản ghi. Nó có thể thực hiện nhiều truy vấn hoặc cập nhật nhiều bảng. Tuy vậy, phạm vi công việc thường được giới hạn đủ nhỏ để hoàn thành trong thời gian request được phép tồn tại.

## 2. Batch processing hoạt động như thế nào?

Batch processing bắt đầu từ một công việc đã được xác định trước. Công việc có thể được kích hoạt theo lịch, bởi người vận hành, bởi một sự kiện hoặc bởi một request khởi tạo job. Thay vì trả kết quả nghiệp vụ ngay cho một client đang chờ, hệ thống xử lý một tập dữ liệu rồi ghi nhận kết quả của cả lần chạy.

Một luồng batch điển hình:

```text
Scheduler / Operator / Job launcher
                |
                v
             Batch Job
                |
                v
        Step 1: Đọc dữ liệu
                |
                v
        Step 2: Xử lý dữ liệu
                |
                v
        Step 3: Ghi kết quả
                |
                v
       Lưu trạng thái và kết quả
```

Ví dụ, vào cuối ngày, hệ thống cần tính phí cho 800.000 tài khoản. Job có thể đọc danh sách tài khoản thuộc kỳ tính phí, tính số tiền cần thu, ghi các giao dịch phát sinh và tạo báo cáo. Công việc này có thể chạy lâu, cần chia dữ liệu thành nhiều phần và cần biết đã xử lý đến đâu nếu tiến trình bị dừng.

Đặc điểm thường gặp của batch processing:

- **Bắt đầu từ một job:** một lịch chạy, thao tác vận hành hoặc lệnh khởi chạy xác định công việc cần thực hiện.
- **Đơn vị công việc là một tập dữ liệu:** job có thể xử lý hàng nghìn, hàng triệu hoặc nhiều hơn bản ghi.
- **Không cần giữ caller chờ đến khi xử lý xong:** job có thể chạy nền. Hệ thống lưu trạng thái để người vận hành hoặc ứng dụng khác tra cứu sau.
- **Thông lượng quan trọng:** mục tiêu thường là hoàn tất một khối lượng dữ liệu trong một khoảng thời gian xử lý cho phép (batch window).
- **Cần quản lý tiến độ và khả năng chạy lại:** job có thể phải tiếp tục từ checkpoint hoặc xử lý lại một phần sau lỗi.

Batch không đồng nghĩa với việc luôn chạy ban đêm. Một job có thể chạy mỗi phút, mỗi giờ, theo sự kiện hoặc được khởi chạy ngay sau khi có dữ liệu. Tính chất batch đến từ việc xử lý một công việc/tập dữ liệu có phạm vi xác định, chứ không chỉ từ thời điểm chạy.

## 3. So sánh trực tiếp

| Khía cạnh | Request trực tuyến | Batch processing |
|---|---|---|
| Cách khởi chạy | Một client gửi request | Scheduler, operator, event hoặc job launcher khởi chạy job |
| Đơn vị xử lý | Một thao tác nghiệp vụ hoặc một request | Một tập dữ liệu hoặc một công việc gồm nhiều bước |
| Người gọi chờ kết quả | Thường có | Thường không; job chạy độc lập và lưu trạng thái |
| Mục tiêu thời gian | Độ trễ thấp cho từng request | Hoàn thành toàn bộ khối lượng trong batch window |
| Khối lượng | Thường nhỏ và bị giới hạn theo request | Có thể rất lớn, được chia thành các phần |
| Ranh giới giao dịch | Thường gắn với một thao tác nghiệp vụ | Thường chia theo chunk hoặc từng bước |
| Xử lý lỗi | Trả lỗi cho caller; caller có thể thử lại | Có thể retry, skip bản ghi lỗi, dừng job hoặc restart từ trạng thái đã lưu |
| Theo dõi | Request ID, log và metrics theo request | Job/step execution, số bản ghi đọc/ghi, thời gian và trạng thái từng bước |
| Ví dụ | Tra cứu đơn hàng, đăng nhập, tạo đơn | Import dữ liệu, đối soát, tính lương, tạo sao kê |

Đây là khác biệt về mục tiêu vận hành, không phải một ranh giới tuyệt đối. Một API trực tuyến vẫn có thể cập nhật nhiều bản ghi; một batch job vẫn có thể xử lý một tập dữ liệu nhỏ. Thiết kế nên dựa trên yêu cầu về thời gian phản hồi, quy mô dữ liệu, cách khôi phục và cách người dùng nhận kết quả.

## 4. Vì sao không xử lý một batch lớn bên trong HTTP request?

Giả sử một API nhận request để tính lại điểm thưởng cho hai triệu tài khoản. Nếu controller thực hiện toàn bộ công việc trước khi trả response, request có thể kéo dài hàng chục phút. Cách làm này tạo ra một số vấn đề:

1. **Timeout:** trình duyệt, API gateway, load balancer hoặc HTTP client có thể đóng kết nối trước khi server hoàn thành.
2. **Tài nguyên bị giữ lâu:** request chiếm thread xử lý, connection hoặc các tài nguyên khác trong thời gian dài. Nhiều request tương tự có thể làm giảm khả năng phục vụ các thao tác ngắn.
3. **Khó khôi phục:** nếu tiến trình chết sau khi đã xử lý một phần dữ liệu, một request đơn lẻ thường không có cơ chế checkpoint để biết nên tiếp tục từ đâu.
4. **Khó quan sát tiến độ:** caller chỉ thấy request đang chờ hoặc đã timeout, trong khi công việc phía server có thể vẫn đang chạy.
5. **Thử lại có thể gây tác dụng phụ lặp:** caller không biết server đã xử lý đến đâu trước khi kết nối bị ngắt. Gửi lại request có thể tạo giao dịch hoặc cập nhật trùng nếu nghiệp vụ không được thiết kế idempotent.

Batch job giải quyết bài toán này bằng cách tách thời gian sống của công việc khỏi thời gian sống của kết nối request. Hệ thống có thể lưu job ID, trạng thái, tiến độ và kết quả để caller kiểm tra sau.

Ví dụ về API khởi tạo một công việc dài:

```text
POST /recalculations
        |
        v
Kiểm tra request và tạo job
        |
        +----> Lưu job ID: 8f31...
        |
        v
Trả HTTP 202 Accepted
        |
        v
Job chạy nền

GET /jobs/8f31...
        |
        v
Trả trạng thái: STARTED / COMPLETED / FAILED
```

Trong mô hình này, API vẫn xử lý trực tuyến phần tiếp nhận yêu cầu. Phần tính toán lớn được giao cho batch job. Response `202 Accepted` cho biết yêu cầu đã được tiếp nhận để xử lý, không có nghĩa toàn bộ nghiệp vụ đã hoàn thành.

## 5. Spring Batch tổ chức công việc batch ra sao?

Spring Batch cung cấp mô hình để định nghĩa, chạy và theo dõi các job xử lý dữ liệu. Những khái niệm cốt lõi giúp phân biệt cách chạy batch với một request thông thường gồm `Job`, `Step`, `JobInstance`, `JobExecution`, `StepExecution`, `JobRepository` và `ExecutionContext`.

### Job và Step

**Job** đại diện cho một quy trình batch hoàn chỉnh, chẳng hạn `dailyBillingJob` hoặc `customerImportJob`. Job được cấu thành từ một hoặc nhiều **Step**. Mỗi Step thực hiện một phần công việc có thể quản lý riêng, ví dụ đọc file, kiểm tra dữ liệu, ghi vào database hoặc tạo báo cáo.

Với job import khách hàng, các step có thể là:

```text
customerImportJob
  |
  +--> validateInputStep
  |
  +--> importCustomersStep
  |
  +--> generateReportStep
```

Job xác định thứ tự và luồng thực hiện các step. Một step có thể chỉ chạy một tác vụ (tasklet), hoặc xử lý nhiều item theo mô hình chunk.

### Chunk-oriented processing

Với dữ liệu gồm nhiều bản ghi, Spring Batch thường dùng mô hình chunk-oriented processing. Một step đọc từng item, có thể chuyển đổi hoặc kiểm tra item, rồi ghi một nhóm item sau khi đạt kích thước chunk đã cấu hình.

```text
ItemReader
    |
    v
ItemProcessor (tùy chọn)
    |
    v
ItemWriter
    |
    v
Commit transaction cho chunk
```

Ví dụ cấu hình dưới đây dùng API của Spring Batch 5. Các bean `reader`, `processor` và `writer` được cung cấp riêng theo nguồn dữ liệu và nghiệp vụ của ứng dụng:

```java
@Bean
Job customerImportJob(JobRepository jobRepository, Step importStep) {
    return new JobBuilder("customerImportJob", jobRepository)
            .start(importStep)
            .build();
}

@Bean
Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> reader,
        ItemProcessor<CustomerInput, Customer> processor,
        ItemWriter<Customer> writer) {

    return new StepBuilder("importStep", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

Với `chunk(500, transactionManager)`, Spring Batch gom tối đa 500 item đã đọc và xử lý vào một chunk trước khi gọi writer và commit giao dịch. Nếu một lỗi khiến giao dịch của chunk rollback, các thay đổi thuộc giao dịch đó sẽ được hoàn tác. Cấu hình retry hoặc skip có thể quyết định cách xử lý một số loại lỗi; chúng cần được thiết kế theo quy tắc nghiệp vụ và loại lỗi thực tế.

Kích thước chunk là một quyết định vận hành. Chunk nhỏ thường tạo nhiều lần commit hơn nhưng giới hạn lượng công việc trong mỗi giao dịch. Chunk lớn có thể giảm chi phí commit nhưng giữ giao dịch và tài nguyên lâu hơn, đồng thời làm tăng lượng dữ liệu cần xử lý lại khi một chunk thất bại. Không có một kích thước phù hợp cho mọi hệ thống.

### JobInstance, JobExecution và JobParameters

Spring Batch phân biệt một lần chạy logic với một lần thực thi cụ thể:

- **JobInstance:** một lần chạy logic của một job, được nhận diện bởi tên job và các identifying `JobParameters`. Ví dụ, `dailyBillingJob` cho ngày `2026-11-15` là một instance theo kỳ nghiệp vụ đó.
- **JobExecution:** một lần thực thi của JobInstance. Nếu một lần chạy thất bại và được khởi động lại, instance có thể có execution mới.
- **StepExecution:** thông tin thực thi của một step trong một JobExecution, gồm trạng thái và các bộ đếm như số item đọc, ghi, bỏ qua hoặc commit.
- **JobParameters:** dữ liệu đầu vào dùng để xác định job cần chạy, chẳng hạn ngày nghiệp vụ, mã file hoặc phạm vi dữ liệu. Các tham số được đánh dấu identifying góp phần xác định JobInstance.

Sự phân biệt này rất hữu ích khi vận hành. Ví dụ, job tính phí cho ngày 15/11 thất bại có thể được restart với cùng identifying parameters để tiếp tục instance của ngày đó. Job tính phí cho ngày 16/11 là một instance khác vì kỳ nghiệp vụ khác.

### JobRepository và ExecutionContext

`JobRepository` lưu metadata về job, step và các lần thực thi. Nhờ metadata này, ứng dụng có thể tra cứu trạng thái, lịch sử chạy và thông tin cần thiết cho việc restart.

`ExecutionContext` là nơi Spring Batch lưu trạng thái cần giữ lại giữa các lần thực thi, thường bao gồm thông tin checkpoint do reader hoặc thành phần xử lý sử dụng. Chẳng hạn, một reader có thể lưu vị trí đọc để khi job được restart, nó tiếp tục từ vị trí phù hợp thay vì luôn bắt đầu lại từ đầu.

Khả năng restart phụ thuộc vào cách job và các thành phần được cấu hình. Việc có metadata không tự động bảo đảm mọi tác dụng phụ bên ngoài đều có thể hoàn tác hoặc tiếp tục an toàn. Nếu job gọi API bên ngoài, gửi email hoặc ghi sang hệ thống không tham gia cùng giao dịch, những hành động đó có thể đã xảy ra dù chunk database bị rollback. Vì vậy, cần thiết kế thao tác ghi theo hướng idempotent, lưu khóa xử lý duy nhất hoặc có cơ chế đối soát phù hợp.

## 6. Chọn mô hình nào cho từng loại công việc?

Nên ưu tiên xử lý request trực tuyến khi caller cần kết quả ngay và phạm vi công việc đủ nhỏ để hoàn thành trong giới hạn thời gian của request. Ví dụ:

- Lấy thông tin hồ sơ hoặc đơn hàng.
- Kiểm tra quyền truy cập.
- Tạo một đơn hàng và trả mã đơn.
- Cập nhật một thiết lập của người dùng.

Nên cân nhắc batch processing khi công việc có khối lượng lớn, cần chạy theo kỳ, cần xử lý nhiều bước hoặc cần khả năng theo dõi và restart. Ví dụ:

- Import hàng trăm nghìn dòng từ file CSV.
- Đối soát giao dịch giữa hai hệ thống.
- Tính lương hoặc phí cho toàn bộ nhân viên/tài khoản trong một kỳ.
- Tạo sao kê định kỳ.
- Tổng hợp dữ liệu và tạo báo cáo cuối ngày.
- Làm sạch hoặc chuyển đổi dữ liệu quy mô lớn.

Trong thực tế, hai mô hình thường phối hợp. Một request có thể xác thực quyền, kiểm tra tham số, tạo yêu cầu xử lý và khởi chạy batch job. API trả về mã công việc; một endpoint khác cho phép xem trạng thái hoặc tải kết quả sau khi job hoàn tất.

Khi chọn kiến trúc, hãy trả lời các câu hỏi sau:

1. Caller có cần kết quả nghiệp vụ ngay trong cùng request không?
2. Khối lượng dữ liệu lớn đến mức nào và thời gian xử lý dự kiến là bao lâu?
3. Công việc có thể chia thành các bước hoặc các chunk độc lập không?
4. Nếu ứng dụng dừng giữa chừng, cần tiếp tục từ đâu và dữ liệu nào đã được commit?
5. Có thể chạy lại một phần công việc mà không tạo tác dụng phụ trùng lặp không?
6. Ai cần theo dõi trạng thái, tiến độ, lỗi và kết quả của công việc?

## 7. Những điểm cần nhớ khi vận hành batch

Batch job có thể chạy lâu và xử lý nhiều dữ liệu, vì vậy thiết kế cần chú ý một số điểm:

- **Đọc dữ liệu theo luồng hoặc theo trang:** tránh nạp toàn bộ tập dữ liệu lớn vào bộ nhớ nếu không cần thiết.
- **Chọn chunk phù hợp:** cân bằng giữa chi phí commit, thời gian giữ giao dịch và lượng dữ liệu cần xử lý lại.
- **Xác định rõ retry và skip:** chỉ retry lỗi có khả năng tự hết; chỉ skip bản ghi khi nghiệp vụ cho phép và cần lưu lại lý do để xử lý sau.
- **Thiết kế idempotency:** bảo đảm restart hoặc chạy lại không tạo giao dịch, thông báo hay cập nhật trùng ngoài ý muốn.
- **Ngăn các lần chạy xung đột:** xác định liệu hai job cùng kỳ hoặc cùng nguồn dữ liệu có được phép chạy đồng thời hay không.
- **Theo dõi bằng metadata và log:** quan sát trạng thái job/step, thời gian chạy, số bản ghi đọc/ghi/lỗi và nguyên nhân thất bại.
- **Đặt giới hạn vận hành:** tính đến batch window, dung lượng database, tốc độ hệ thống nguồn/đích và ảnh hưởng đến traffic trực tuyến.

Batch job chạy đồng thời với ứng dụng phục vụ request có thể tranh chấp CPU, bộ nhớ, connection pool và tài nguyên database. Vì vậy, một job hoàn thành đúng logic vẫn có thể ảnh hưởng đến độ trễ của API nếu không kiểm soát tốc độ, mức song song hoặc lịch chạy.

## Kết luận

Xử lý request trực tuyến tối ưu cho những thao tác cần phản hồi nhanh theo từng yêu cầu. Batch processing tối ưu cho công việc có phạm vi dữ liệu rõ ràng, khối lượng lớn hoặc cần theo dõi, chia nhỏ và khôi phục qua nhiều bước. Trong Spring Batch, `Job` và `Step` mô tả quy trình; chunk, transaction, `JobRepository` và `ExecutionContext` hỗ trợ xử lý dữ liệu có kiểm soát và quản lý tiến độ. Một hệ thống thực tế thường dùng API để tiếp nhận yêu cầu nhanh, sau đó giao phần xử lý dài cho batch job khi nghiệp vụ phù hợp.
