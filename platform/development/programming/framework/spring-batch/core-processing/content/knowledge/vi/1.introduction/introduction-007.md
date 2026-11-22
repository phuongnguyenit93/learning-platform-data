# Transaction, checkpoint và trạng thái tiến độ

Trong Spring Batch, transaction, checkpoint và trạng thái tiến độ phối hợp để một Step xử lý dữ liệu theo từng phần, phục hồi sau lỗi và cho phép theo dõi một lần chạy. Ba khái niệm này liên quan với nhau nhưng giải quyết ba vấn đề riêng:

- **Transaction** xác định phần công việc nào được commit hoặc rollback cùng nhau.
- **Checkpoint** lưu vị trí và trạng thái cần thiết để tiếp tục từ điểm đã commit gần nhất.
- **Execution status và counters** ghi nhận lần chạy đang ở trạng thái nào và đã xử lý được bao nhiêu dữ liệu.

Hiểu rõ ranh giới của từng phần giúp thiết kế batch job có thể restart, tránh ghi dữ liệu trùng và giải thích chính xác điều gì đã xảy ra khi một job thất bại.

## 1. Vòng đời xử lý theo chunk

Một Step thường dùng chunk-oriented processing để đọc, xử lý và ghi dữ liệu theo nhóm. Ví dụ, với commit interval là 100, Spring Batch gom tối đa 100 item cho một chunk rồi chuyển nhóm đó cho ItemWriter.

Luồng khái quát:

1. Bắt đầu transaction cho chunk.
2. Gọi ItemReader để đọc item.
3. Gọi ItemProcessor cho từng item nếu Step có processor.
4. ItemProcessor có thể trả về item đã biến đổi hoặc trả về null để lọc item đó.
5. Gọi ItemWriter một lần với các item còn lại trong chunk.
6. Cập nhật trạng thái và checkpoint của Step.
7. Commit transaction. Nếu có lỗi thuộc diện rollback, transaction được rollback theo cấu hình.

Ví dụ với commit interval bằng 3:

~~~text
Chunk 1: read A, B, C -> process -> write -> commit
Chunk 2: read D, E, F -> process -> write -> commit
Chunk 3: read G, H, I -> process -> write -> commit
...
~~~

Mỗi chunk là một đơn vị transaction. Nếu việc ghi chunk 2 thất bại và lỗi làm transaction rollback, các thay đổi thuộc transaction đó được hoàn tác. Các chunk đã commit trước đó vẫn được giữ lại.

Commit interval là số item mà framework gom vào một chunk, không nhất thiết bằng số dòng cuối cùng được ghi. Nếu processor lọc một item bằng cách trả về null, item đó không được chuyển cho writer, nhưng vẫn đã được đọc và xử lý.

### Cấu hình chunk và transaction manager

Ví dụ dưới đây dùng API theo phong cách Spring Batch 5:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Tham số 100 là commit interval. Transaction manager điều khiển transaction cho từng chunk. Trong ứng dụng thực tế, transaction manager phải phù hợp với tài nguyên mà writer sử dụng, chẳng hạn transaction manager cho database đích.

Tên và chữ ký API có thể khác ở Spring Batch 4 hoặc các bản cũ hơn; ví dụ trên theo cách cấu hình StepBuilder phổ biến ở Spring Batch 5.

## 2. Transaction bảo vệ dữ liệu như thế nào?

Transaction cung cấp ranh giới commit/rollback cho những tài nguyên được transaction manager quản lý.

Giả sử một chunk cập nhật ba đơn hàng:

~~~text
BEGIN
  UPDATE order A
  UPDATE order B
  UPDATE order C
COMMIT
~~~

Nếu câu lệnh cập nhật order C thất bại và lỗi làm transaction rollback, các cập nhật A và B trong cùng transaction cũng được hoàn tác. Database không giữ trạng thái chỉ cập nhật được một phần của chunk.

Điều này hữu ích khi writer thực hiện nhiều thao tác database. Writer có thể ghi từng item trong chunk, nhưng các thao tác đó vẫn thuộc cùng transaction nếu chúng dùng cùng transaction manager và cùng tài nguyên transaction.

### Chọn commit interval

Commit interval ảnh hưởng trực tiếp đến hiệu năng và chi phí phục hồi.

| Commit interval nhỏ | Commit interval lớn |
|---|---|
| Transaction ngắn hơn | Transaction kéo dài hơn |
| Ít item phải xử lý lại sau rollback | Có thể phải xử lý lại nhiều item hơn |
| Commit thường xuyên, tăng chi phí commit | Ít lần commit hơn |
| Thường giữ ít dữ liệu trong bộ nhớ hơn | Có thể cần nhiều bộ nhớ hơn |
| Lock thường được giữ trong thời gian ngắn hơn | Lock có thể được giữ lâu hơn |

Không có một con số phù hợp cho mọi job. Hãy cân nhắc kích thước dữ liệu, thời gian xử lý mỗi item, khả năng chịu tải của database, mức độ tranh chấp lock và yêu cầu phục hồi. Có thể bắt đầu với một chunk vừa phải, đo thời gian chạy và tài nguyên sử dụng, sau đó điều chỉnh.

### Những gì transaction không tự bảo vệ

Transaction database không tự động hoàn tác các tác động bên ngoài database, ví dụ:

- Gửi email hoặc gọi API của hệ thống khác.
- Ghi file vào filesystem.
- Đẩy message vào một broker không tham gia cùng transaction.
- Gọi một dịch vụ thanh toán hoặc dịch vụ vận chuyển.

Nếu writer gọi API bên ngoài rồi transaction database rollback, API bên ngoài vẫn có thể đã thực hiện hành động. Khi job chạy lại, hành động đó có thể bị lặp.

Với các tác động như vậy, cần thiết kế thêm cơ chế phù hợp, chẳng hạn:

- **Idempotency key** để hệ thống nhận biết một yêu cầu đã được xử lý.
- **Transactional outbox** để ghi ý định gửi message vào cùng transaction database, sau đó một tiến trình riêng phát message.
- Bảng ghi nhận kết quả hoặc khóa nghiệp vụ để phát hiện thao tác đã hoàn tất.
- Cơ chế bù trừ khi không thể rollback một hành động bên ngoài.

Đừng giả định rằng rollback chunk sẽ hoàn tác mọi thứ mà code trong writer đã thực hiện.

## 3. Checkpoint và ExecutionContext

Checkpoint là trạng thái đã lưu tại một điểm commit, đủ để reader hoặc writer tiếp tục công việc khi Step được restart.

Spring Batch lưu dữ liệu trạng thái trong **ExecutionContext**, một cấu trúc key/value gắn với execution. Có hai phạm vi chính:

- **Step ExecutionContext** gắn với StepExecution. Đây là nơi thường lưu vị trí đọc hoặc trạng thái cần thiết để restart một Step.
- **Job ExecutionContext** gắn với JobExecution. Đây là nơi phù hợp để chia sẻ một lượng trạng thái giữa các Step trong cùng lần thực thi job.

Với chunk-oriented Step, trạng thái của Step thường được cập nhật và lưu tại ranh giới commit. Job ExecutionContext thường được cập nhật khi Step hoàn thành hoặc khi ứng dụng chủ động cập nhật nó. Chi tiết thời điểm lưu phụ thuộc vào vòng đời Step và cách cấu hình repository.

**JobRepository** lưu metadata của Spring Batch, bao gồm execution, step execution và execution context. Checkpoint không phải là bản sao toàn bộ dữ liệu nghiệp vụ; nó chỉ nên chứa thông tin cần thiết để xác định cách tiếp tục xử lý.

### Vai trò của ItemStream

Các component cần lưu và phục hồi trạng thái có thể triển khai **ItemStream**. Vòng đời cơ bản gồm:

- **open(ExecutionContext)**: khôi phục trạng thái khi Step bắt đầu hoặc restart.
- **update(ExecutionContext)**: ghi trạng thái hiện tại vào ExecutionContext tại điểm framework chuẩn bị lưu checkpoint.
- **close()**: giải phóng tài nguyên khi Step kết thúc.

Nhiều reader và writer có sẵn của Spring Batch đã triển khai cơ chế này. Khi dùng các component đó, hãy đặt tên component ổn định và bật lưu trạng thái nếu cần restart. Ví dụ, một FlatFileItemReader có thể được cấu hình như sau:

~~~java
@Bean
@StepScope
FlatFileItemReader<Customer> customerReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        LineMapper<Customer> customerLineMapper) {

    return new FlatFileItemReaderBuilder<Customer>()
            .name("customerReader")
            .resource(new FileSystemResource(inputFile))
            .lineMapper(customerLineMapper)
            .saveState(true)
            .build();
}
~~~

**@StepScope** cho phép tạo reader khi Step chạy, lúc job parameter inputFile đã có giá trị. **saveState(true)** cho phép reader lưu thông tin cần thiết để khôi phục vị trí đọc. Cần giữ tên reader ổn định giữa các lần chạy lại để Spring Batch nhận diện đúng trạng thái của component.

Nếu đặt **saveState(false)**, component không lưu checkpoint của chính nó. Điều đó có thể phù hợp với một reader không cần restart hoặc một thiết kế mà vị trí đọc được quản lý ở nơi khác, nhưng Step sẽ không thể dựa vào trạng thái nội bộ của reader đó để tiếp tục chính xác.

### Ví dụ về reader tự quản lý checkpoint

Một reader tùy chỉnh có thể lưu chỉ số item tiếp theo cần đọc. Ví dụ đơn giản sau minh họa hợp đồng ItemStreamReader; danh sách trong ví dụ chỉ nhằm làm rõ cơ chế:

~~~java
public class IndexedItemReader<T> implements ItemStreamReader<T> {

    private static final String NEXT_INDEX = "indexedReader.nextIndex";

    private final List<T> items;
    private int nextIndex;

    public IndexedItemReader(List<T> items) {
        this.items = items;
    }

    @Override
    public void open(ExecutionContext context) {
        nextIndex = context.containsKey(NEXT_INDEX)
                ? context.getInt(NEXT_INDEX)
                : 0;
    }

    @Override
    public T read() {
        if (nextIndex >= items.size()) {
            return null;
        }

        return items.get(nextIndex++);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(NEXT_INDEX, nextIndex);
    }

    @Override
    public void close() {
        // Giải phóng tài nguyên nếu reader có sử dụng tài nguyên bên ngoài.
    }
}
~~~

Giả sử chunk đầu tiên đọc và commit 100 item. Khi update được gọi, reader lưu **nextIndex = 100**. Nếu chunk tiếp theo thất bại và Step được restart, open đọc lại giá trị 100 từ ExecutionContext và bắt đầu từ item thứ 101.

Đây là ví dụ minh họa checkpoint khi restart. Reader sản xuất cần xử lý thêm các yêu cầu thực tế như nguồn dữ liệu có thể thay đổi, rollback trong cùng một lần chạy, truy cập đồng thời và giải phóng tài nguyên. Việc tăng biến chỉ số trong bộ nhớ không tự động đưa reader về vị trí cũ khi một chunk rollback rồi được thử lại ngay trong cùng execution.

### Chọn dữ liệu lưu trong ExecutionContext

Chỉ lưu những giá trị cần thiết để phục hồi hoặc chuyển trạng thái giữa các Step, ví dụ:

- Số thứ tự bản ghi tiếp theo.
- ID cuối cùng đã xử lý trong một luồng dữ liệu có thứ tự ổn định.
- Tên hoặc phiên bản của file đầu vào.
- Một mốc thời gian hoặc khóa phân trang đã được xác nhận.

Dùng key có tiền tố theo tên component, chẳng hạn **customerReader.nextIndex**, để tránh trùng key giữa nhiều reader hoặc writer. Giá trị lưu phải tương thích với cơ chế serialize của ExecutionContext đang được cấu hình. Không nên đưa toàn bộ danh sách item, object lớn hoặc dữ liệu nghiệp vụ nhạy cảm vào checkpoint.

Nếu một reader hoặc writer được bọc bên trong component khác, hãy bảo đảm component bên trong được đăng ký như một stream khi cần. Nếu không, các callback open, update và close của nó có thể không được gọi như mong đợi.

## 4. Restart một Job và vai trò của JobParameters

Spring Batch phân biệt JobInstance và JobExecution:

- **JobInstance** đại diện cho một lần chạy logic của job, được xác định bởi tên job và các identifying JobParameters.
- **JobExecution** đại diện cho một lần thực thi cụ thể của JobInstance.
- Một JobInstance có thể có nhiều JobExecution nếu lần chạy trước thất bại hoặc bị dừng và được restart.

Ví dụ:

~~~text
JobInstance: importOrders + businessDate=2026-11-15
  JobExecution 101: FAILED
  JobExecution 108: STARTED
  JobExecution 108: COMPLETED
~~~

Nếu chạy lại cùng tên job với cùng identifying parameters, Spring Batch nhận diện đó là cùng JobInstance. Khi JobInstance có execution thất bại hoặc bị dừng, job có thể được restart và sử dụng checkpoint đã lưu.

Nếu thay đổi một identifying parameter, ví dụ businessDate, Spring Batch tạo JobInstance mới. Lần chạy mới bắt đầu theo trạng thái mới, không phải restart checkpoint của JobInstance cũ.

Điều này dẫn đến một số nguyên tắc:

- Dùng JobParameters để xác định rõ tập dữ liệu hoặc kỳ nghiệp vụ mà job xử lý.
- Khi restart, giữ nguyên các identifying parameters của lần chạy cần tiếp tục.
- Chỉ tạo parameter mới khi chủ đích là chạy một JobInstance mới.
- Đảm bảo dữ liệu đầu vào và thứ tự đọc vẫn tương thích với checkpoint đã lưu.

Một file đầu vào bị thay thế nhưng vẫn dùng cùng parameter có thể khiến checkpoint trỏ đến vị trí không còn đúng. Có thể lưu thêm tên file, kích thước, checksum hoặc phiên bản nguồn dữ liệu để phát hiện tình huống đầu vào đã thay đổi.

Mặc định, Step đã hoàn thành trong một JobInstance thường được bỏ qua khi job được restart. Nếu nghiệp vụ yêu cầu chạy lại Step đã hoàn thành, có thể xem xét cấu hình **allowStartIfComplete(true)** cho Step đó. Cần đánh giá tác động lặp dữ liệu trước khi bật tùy chọn này.

## 5. Trạng thái tiến độ và các execution

Spring Batch lưu trạng thái ở nhiều cấp. Cần biết đối tượng nào đang được quan sát để tránh nhầm trạng thái của một lần chạy với trạng thái của job nói chung.

| Đối tượng | Ý nghĩa |
|---|---|
| JobInstance | Định danh logic của job theo tên job và identifying parameters |
| JobExecution | Một lần chạy cụ thể của JobInstance |
| StepExecution | Một lần thực thi cụ thể của một Step trong JobExecution |
| ExecutionContext | Dữ liệu trạng thái dùng để restart hoặc trao đổi thông tin |
| ExitStatus | Mã kết quả dùng để mô tả kết quả và điều hướng flow |

### BatchStatus

**BatchStatus** mô tả trạng thái thực thi của JobExecution hoặc StepExecution. Các trạng thái thường gặp gồm:

| BatchStatus | Ý nghĩa khái quát |
|---|---|
| STARTING | Execution đang được khởi tạo |
| STARTED | Execution đang chạy |
| STOPPING | Đang xử lý yêu cầu dừng |
| STOPPED | Execution đã dừng theo yêu cầu |
| FAILED | Execution kết thúc do lỗi |
| COMPLETED | Execution hoàn tất |
| ABANDONED | Execution được đánh dấu không tiếp tục restart |
| UNKNOWN | Không thể xác định trạng thái đáng tin cậy |

**STOPPED** và **FAILED** có ý nghĩa khác nhau. Một job bị dừng có kiểm soát có thể được restart tùy trạng thái và cấu hình; một job thất bại thường cần xử lý nguyên nhân lỗi trước khi restart. **ABANDONED** biểu thị execution không được tiếp tục theo cơ chế restart thông thường.

### ExitStatus

**ExitStatus** mô tả kết quả theo mã thoát. Nó thường được dùng trong job flow để quyết định Step tiếp theo. Ví dụ, một Step có thể hoàn thành về mặt thực thi nhưng trả về mã nghiệp vụ riêng để flow chuyển sang nhánh xử lý khác.

Vì vậy, không nên đồng nhất BatchStatus với ExitStatus. BatchStatus cho biết execution có hoàn tất, thất bại hay bị dừng; ExitStatus mô tả kết quả mà flow hoặc hệ thống giám sát sử dụng.

### Các bộ đếm tiến độ trong StepExecution

**StepExecution** chứa nhiều bộ đếm giúp quan sát tiến độ:

| Trường | Diễn giải |
|---|---|
| readCount | Số item đã đọc thành công |
| writeCount | Số item đã được ghi |
| filterCount | Số item bị processor lọc bằng cách trả về null |
| readSkipCount | Số lỗi đọc được xử lý theo skip policy |
| processSkipCount | Số lỗi xử lý được bỏ qua |
| writeSkipCount | Số lỗi ghi được bỏ qua |
| commitCount | Số lần commit được ghi nhận |
| rollbackCount | Số lần rollback được ghi nhận |
| startTime, endTime | Thời điểm bắt đầu và kết thúc execution |
| status, exitStatus | Trạng thái và mã kết quả của Step |

Các bộ đếm giúp trả lời câu hỏi job đã đọc, lọc, ghi hoặc bỏ qua bao nhiêu item. Chúng không thay thế checkpoint. Không nên suy ra vị trí cần đọc tiếp chỉ từ readCount, vì filter, skip, rollback và cách reader phân trang có thể khiến số item đã đọc không tương đương với vị trí trong nguồn dữ liệu.

Ví dụ, readCount có thể là 1.000 trong khi writeCount là 970 và filterCount là 30. Điều này có thể hoàn toàn bình thường nếu processor chủ động lọc 30 item.

### Quan sát tiến độ bằng metadata

Có thể quan sát trạng thái qua các đối tượng execution trong code hoặc qua **JobExplorer** khi cần truy vấn execution đã được lưu trong repository. Ví dụ, từ một StepExecution:

~~~java
void logStepProgress(StepExecution stepExecution) {
    log.info(
            "step={}, status={}, read={}, written={}, filtered={}, commits={}, rollbacks={}",
            stepExecution.getStepName(),
            stepExecution.getStatus(),
            stepExecution.getReadCount(),
            stepExecution.getWriteCount(),
            stepExecution.getFilterCount(),
            stepExecution.getCommitCount(),
            stepExecution.getRollbackCount()
    );
}
~~~

Đối với hệ thống giám sát, nên hiển thị ít nhất tên job, JobExecution ID, tên Step, BatchStatus, thời gian bắt đầu, thời gian kết thúc và các bộ đếm quan trọng. JobExecution ID giúp phân biệt các lần restart thuộc cùng JobInstance.

Metadata trong JobRepository là nguồn theo dõi execution của Spring Batch. Không nên cập nhật trực tiếp các bảng metadata để “sửa” tiến độ. Hãy để framework quản lý trạng thái qua JobRepository và các API tương ứng.

## 6. Điều gì xảy ra khi một chunk thất bại?

Giả sử một Step đọc 1.000 đơn hàng, với commit interval bằng 100:

~~~text
Chunk 1: items 1-100       -> commit
Chunk 2: items 101-200    -> commit
Chunk 3: items 201-300    -> commit
Chunk 4: items 301-400    -> writer gặp lỗi -> rollback
~~~

Sau khi chunk 4 rollback:

- Các thay đổi database thuộc chunk 4 được rollback nếu chúng tham gia cùng transaction.
- Ba chunk đã commit trước đó vẫn được giữ.
- Checkpoint bền vững gần nhất vẫn là sau chunk 3, nếu repository và business data được commit đồng bộ.
- Job hoặc Step có thể kết thúc với trạng thái FAILED, tùy loại lỗi và cấu hình.
- Khi restart cùng JobInstance, reader restartable có thể tiếp tục từ checkpoint sau item 300.

Các bộ đếm trong execution phản ánh diễn biến thực tế của lần chạy và có thể bao gồm thông tin về rollback, skip hoặc retry. Khi phân tích sự cố, hãy xem cả trạng thái execution, bộ đếm và checkpoint thay vì chỉ nhìn một con số.

### Skip và retry ảnh hưởng đến tiến độ

Spring Batch có thể được cấu hình để retry một thao tác tạm thời hoặc skip một item lỗi theo chính sách đã định.

- **Retry** thử lại thao tác khi lỗi được xem là có khả năng tạm thời, chẳng hạn một lỗi truy cập dịch vụ có thể phục hồi.
- **Skip** cho phép job tiếp tục sau một loại lỗi được chấp nhận, đồng thời tăng bộ đếm skip tương ứng.
- **Rollback** hoàn tác các thay đổi trong transaction hiện tại khi lỗi yêu cầu rollback.

Retry và skip cần được thiết kế dựa trên tính chất lỗi. Không nên skip lỗi dữ liệu quan trọng chỉ để job đạt trạng thái COMPLETED, vì kết quả cuối có thể thiếu dữ liệu mà không được phát hiện. Với writer không idempotent hoặc có tác động ngoài transaction, retry cũng có thể tạo ra thao tác trùng.

## 7. Giữ checkpoint nhất quán với dữ liệu nghiệp vụ

Checkpoint chỉ hữu ích khi nó mô tả đúng phần dữ liệu đã được xử lý bền vững.

Nếu business data và metadata của Spring Batch dùng chung transaction manager và cùng transaction resource phù hợp, việc ghi dữ liệu nghiệp vụ và cập nhật checkpoint có thể được commit cùng nhau. Khi đó, sau restart, checkpoint tương ứng với phần dữ liệu đã commit.

Nếu business data và JobRepository dùng các database hoặc transaction manager khác nhau, không nên mặc định rằng hai nơi luôn commit hoặc rollback nguyên tử. Có thể xảy ra tình huống dữ liệu nghiệp vụ đã commit nhưng checkpoint chưa được lưu, hoặc checkpoint đã được lưu nhưng dữ liệu nghiệp vụ chưa được commit. Cần hiểu rõ cách cấu hình transaction của ứng dụng và lựa chọn cơ chế đồng bộ phù hợp.

Với nguồn hoặc đích không hỗ trợ transaction chung, hãy thiết kế khả năng chạy lặp an toàn:

- Dùng khóa nghiệp vụ duy nhất hoặc upsert khi phù hợp.
- Lưu dấu mốc xử lý ở nơi có thể kiểm tra lại.
- Làm cho writer idempotent nếu có thể.
- Kiểm tra dữ liệu đầu vào có thay đổi giữa hai lần chạy hay không.
- Dùng outbox hoặc cơ chế bù trừ cho tác động liên hệ thống.

Một checkpoint đúng không thể tự sửa một writer tạo dữ liệu trùng khi chạy lại.

## 8. Các tình huống cần lưu ý khi vận hành

**Reader không lưu trạng thái.** Nếu reader tắt saveState hoặc không triển khai ItemStream khi cần, Spring Batch không có đủ thông tin nội bộ để khôi phục vị trí đọc. Cần bổ sung cơ chế checkpoint hoặc chấp nhận chạy lại từ đầu với thiết kế idempotent.

**Nguồn dữ liệu thay đổi.** Checkpoint theo số dòng hoặc vị trí có thể không còn đúng nếu file bị thay thế, bản ghi bị chèn hoặc thứ tự dữ liệu thay đổi. Dùng nguồn dữ liệu ổn định hoặc lưu thêm định danh phiên bản nguồn.

**Một Step có nhiều stream.** Mỗi stream cần key riêng và phải được đăng ký đúng để các callback vòng đời được gọi. Trùng key trong ExecutionContext có thể làm trạng thái của component này ghi đè component khác.

**Chạy song song hoặc partitioning.** Mỗi partition thường có StepExecution và ExecutionContext riêng. Reader dùng chung giữa nhiều thread phải an toàn khi truy cập đồng thời; checkpoint dùng chung không có đồng bộ có thể gây bỏ sót hoặc xử lý trùng. Ưu tiên trạng thái riêng theo partition và phân chia dữ liệu rõ ràng.

**Step hoàn thành nhưng job thất bại ở Step sau.** Khi restart cùng JobInstance, Step đã hoàn thành thường được bỏ qua. Nếu Step cần chạy lại, phải cấu hình có chủ đích và bảo đảm thao tác của Step an toàn khi lặp.

**Dùng JobParameters mới khi muốn restart.** Thay identifying parameter tạo JobInstance mới. Job mới không tiếp tục checkpoint của instance cũ, dù tên job giống nhau.

## 9. Cách đọc một lần chạy để tìm nguyên nhân lỗi

Khi một batch job không hoàn tất, có thể lần lượt kiểm tra:

1. Xác định JobInstance và JobExecution ID để chắc chắn đang xem đúng lần chạy.
2. Đọc BatchStatus, ExitStatus, thời gian bắt đầu/kết thúc và thông tin lỗi.
3. Xác định StepExecution bị lỗi; xem read, write, filter, skip, commit và rollback counts.
4. Xác định checkpoint gần nhất đã được lưu trong Step ExecutionContext.
5. Kiểm tra reader có hỗ trợ restart và nguồn dữ liệu có còn đúng phiên bản hay không.
6. Kiểm tra writer có tạo tác động ngoài transaction hoặc có thể ghi trùng khi restart hay không.
7. Sau khi xử lý nguyên nhân, restart cùng JobInstance nếu mục tiêu là tiếp tục từ checkpoint đã lưu.

Khi vận hành, cần phân biệt rõ ba câu hỏi: transaction cho biết phần dữ liệu nào đã commit; checkpoint cho biết Step có thể tiếp tục từ đâu; execution status và counters cho biết lần chạy đã diễn ra như thế nào. Kết hợp cả ba mới cho phép đánh giá chính xác tiến độ và độ an toàn của một lần restart.

