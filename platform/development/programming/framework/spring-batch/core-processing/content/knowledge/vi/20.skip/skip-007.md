# Skip item và rollback chunk trong Spring Batch

Trong một Job Spring Batch, không phải mọi item đều có thể xử lý thành công. Một dòng file có thể sai định dạng, một bản ghi có thể vi phạm quy tắc nghiệp vụ hoặc writer có thể gặp lỗi khi lưu dữ liệu. Với một số lỗi, dừng toàn bộ Step là cần thiết. Với những lỗi khác, nghiệp vụ cho phép bỏ qua item không hợp lệ và tiếp tục xử lý phần còn lại.

Spring Batch cung cấp **skip** để bỏ qua item gặp lỗi theo chính sách đã khai báo. Trong chunk-oriented Step, skip phải được hiểu cùng **transaction rollback**: một lỗi ở writer có thể làm transaction của chunk hiện tại rollback trước khi framework xác định item gây lỗi và tiếp tục với các item hợp lệ. Các chunk đã commit trước đó vẫn được giữ.

Bài học này giải thích cách skip hoạt động ở reader, processor và writer; giới hạn skip; quan hệ giữa skip và rollback; cách dùng SkipListener; tương tác với retry; và cách kiểm thử để bảo đảm dữ liệu hợp lệ không bị mất, ghi trùng hoặc commit dở dang.

## 1. Skip là gì?

Skip là quyết định bỏ qua một item gặp exception mà nghiệp vụ cho phép loại khỏi lần xử lý hiện tại. Step tiếp tục với những item khác thay vì thất bại ngay lập tức.

Ví dụ file nhập có 1.000 dòng, trong đó một dòng sai định dạng. Nếu chính sách cho phép reject tối đa 10 dòng, Job có thể bỏ dòng lỗi, ghi nhận nguyên nhân và tiếp tục xử lý các dòng hợp lệ.

Skip không có nghĩa là bỏ qua mọi exception. Ứng dụng phải xác định loại lỗi nào được phép skip, số lượng tối đa, và cách lưu thông tin item bị bỏ.

Các tình huống thường phù hợp với skip:

- Một dòng file sai định dạng nhưng các dòng còn lại vẫn độc lập và có thể xử lý.
- Một item vi phạm quy tắc dữ liệu có thể được đưa vào reject file hoặc bảng lỗi.
- Một bản ghi gây lỗi ghi riêng lẻ, trong khi các bản ghi khác trong chunk vẫn hợp lệ.
- Nghiệp vụ cho phép hoàn tất lô với một số lượng item bị loại đã được kiểm soát.

Các tình huống thường không nên skip:

- Database hoặc hệ thống đích không khả dụng trên diện rộng.
- Sai cấu hình, thiếu quyền hoặc thiếu schema.
- Mất kết nối khiến không thể bảo đảm dữ liệu đã được ghi.
- Một lỗi làm cho các item tiếp theo không còn đáng tin cậy.
- Vi phạm tính toàn vẹn khiến việc tiếp tục có thể tạo dữ liệu sai.

Skip là quyết định nghiệp vụ có chủ đích. Nếu bỏ qua một item làm mất dữ liệu quan trọng, Step nên thất bại để người vận hành điều tra.

## 2. Chunk và transaction trước khi xét skip

Một chunk-oriented Step gom item theo commit interval. Framework đọc item, gọi processor nếu có, sau đó gọi writer cho nhóm output. Các thao tác của chunk thường nằm trong transaction do transaction manager của Step điều khiển.

Ví dụ:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
~~~

Với commit interval 100, framework xử lý tối đa 100 item đầu vào trong một chunk trước khi hoàn tất transaction đó. Chunk cuối có thể nhỏ hơn nếu reader kết thúc.

~~~mermaid
flowchart TD
    A["Bắt đầu transaction chunk"] --> B["Reader cung cấp item"]
    B --> C["Processor xử lý item"]
    C --> D["Writer ghi các output"]
    D --> E{"Chunk thành công?"}
    E -- "Có" --> F["Commit"]
    E -- "Không" --> G["Rollback theo policy"]
    G --> H["Retry, skip hoặc fail"]
    F --> I["Chunk tiếp theo"]
~~~

Nếu chunk thành công, transaction commit và dữ liệu được lưu bền vững. Nếu lỗi làm transaction rollback, các thay đổi tham gia transaction của chunk hiện tại được hoàn tác. Những chunk trước đã commit không bị rollback chỉ vì chunk sau thất bại.

Skip hoạt động bên trong cơ chế này. Một item bị skip có thể khiến framework phải rollback hoặc phân tích lại chunk tùy giai đoạn xảy ra lỗi và rollback policy. Không nên hiểu skip đơn giản là xóa item khỏi danh sách rồi chắc chắn không có rollback.

## 3. Phân biệt skip, filter, retry và rollback

Các khái niệm này có liên quan nhưng không thay thế nhau.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Filter | Processor trả về null để loại item theo quy tắc nghiệp vụ bình thường | Đơn đã hủy không cần xuất |
| Skip | Bỏ item do exception được chính sách cho phép | Dòng CSV sai định dạng |
| Retry | Thử lại thao tác khi exception có khả năng tạm thời | Database deadlock |
| Rollback | Hoàn tác thay đổi trong transaction hiện tại | Writer ghi lỗi giữa chunk |
| Restart | Tạo JobExecution mới cho JobInstance đã thất bại hoặc dừng | Khởi động lại Job sau khi sửa lỗi hạ tầng |

Ví dụ processor trả null:

~~~java
@Bean
ItemProcessor<OrderInput, Order> orderProcessor() {
    return input -> {
        if ("CANCELLED".equals(input.status())) {
            return null;
        }

        return mapToOrder(input);
    };
}
~~~

Item bị filter không phát sinh exception và không được tính là skip. Spring Batch tăng filterCount thay vì processSkipCount.

Ngược lại, nếu processor ném ValidationException và exception được cấu hình skip, item đó được tính là process skip.

### Khi nào dùng từng cơ chế?

- Dùng filter khi item hợp lệ nhưng không cần đưa vào output.
- Dùng skip khi một exception đã được xác định là có thể bỏ qua.
- Dùng retry khi lỗi có thể tự phục hồi nếu thử lại.
- Dùng rollback để bảo đảm transaction không để lại thay đổi dở dang.
- Dùng restart khi một JobExecution đã kết thúc thất bại hoặc dừng và cần chạy tiếp theo checkpoint.

## 4. Cấu hình skip cơ bản

Trong Spring Batch 5, có thể cấu hình skip trên Step bằng fault-tolerant builder:

~~~java
@Bean
Step importFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> reader,
        ItemProcessor<CustomerInput, Customer> processor,
        ItemWriter<Customer> writer) {

    return new StepBuilder("importFileStep", jobRepository)
        .<CustomerInput, Customer>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skipLimit(10)
        .build();
}
~~~

Trong ví dụ:

- `faultTolerant()` bật cấu hình skip/retry cho chunk Step.
- `skip(FlatFileParseException.class)` cho phép bỏ qua lỗi parse file thuộc loại này.
- `skipLimit(10)` giới hạn tổng số item bị skip trong Step.
- Các exception không được khai báo skipable sẽ làm Step thất bại nếu không có policy khác xử lý.

Nếu số item bị skip vượt quá giới hạn, Spring Batch ném SkipLimitExceededException và Step thất bại.

### Skip limit được tính như thế nào?

Skip limit áp dụng chung cho lỗi đọc, xử lý và ghi, không phải một giới hạn riêng cho mỗi giai đoạn.

Giả sử cấu hình `skipLimit(10)`:

- 4 lỗi đọc được skip.
- 3 lỗi xử lý được skip.
- 3 lỗi ghi được skip.

Tổng cộng 10 item bị skip, vẫn nằm trong giới hạn.

Nếu phát sinh thêm một item lỗi cần skip, tổng số sẽ là 11 và vượt giới hạn; Step thất bại.

| Giai đoạn | Số item skip |
|---|---:|
| Read | 4 |
| Process | 3 |
| Write | 3 |
| Tổng | 10 |
| Giới hạn | 10 |

Giới hạn là tổng cho Step. Không cấu hình ba lần `skipLimit(10)` để kỳ vọng được skip 30 item.

### Không cấu hình skip limit quá rộng

Một giới hạn lớn có thể khiến Job hoàn tất dù tỷ lệ dữ liệu lỗi rất cao. Chọn limit theo chất lượng dữ liệu và yêu cầu nghiệp vụ. Có thể dùng số tuyệt đối, tỷ lệ lỗi hoặc validation Step riêng để kiểm soát lô.

## 5. Skip ở giai đoạn đọc: read skip

Read skip xảy ra khi ItemReader ném exception và exception đó được phép skip.

Ví dụ file CSV có một dòng sai cấu trúc:

~~~text
customer_id,full_name,email
C001,An,an@example.test
C002,Binh
C003,Chi,chi@example.test
~~~

Nếu dòng C002 thiếu cột và FlatFileItemReader ném FlatFileParseException, Step có thể skip dòng đó nếu policy cho phép. Các dòng hợp lệ phía sau vẫn được đọc.

Ví dụ cấu hình:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skipLimit(20)
~~~

Với FlatFileParseException, thông tin lỗi thường có thể truy cập qua input line và line number. Điều này hữu ích để ghi reject record hoặc chỉ ra dòng cần sửa.

### Read skip không có item đầu vào

Trong callback read skip, reader chưa trả về một object item hợp lệ. Vì vậy SkipListener nhận Throwable mà không có tham số item:

~~~java
@Override
public void onSkipInRead(Throwable throwable) {
    if (throwable instanceof FlatFileParseException ex) {
        log.warn(
            "Bỏ qua dòng {}: {}",
            ex.getLineNumber(),
            ex.getInput()
        );
    }
}
~~~

Không nên coi EOF là read skip. ItemReader trả null theo hợp đồng nghĩa là nguồn đã hết bình thường. Read skip chỉ xảy ra khi reader ném exception được policy cho phép bỏ qua.

### Chỉ skip lỗi đọc có thể phục hồi ở mức item

Một lỗi file sai định dạng ở một dòng có thể là lỗi cục bộ. Nhưng lỗi file không tồn tại, mất quyền đọc hoặc thiết bị lưu trữ bị lỗi có thể ảnh hưởng toàn bộ nguồn. Không nên gom tất cả IOException vào skip nếu điều đó có thể khiến Job bỏ qua một sự cố hạ tầng nghiêm trọng.

## 6. Skip ở giai đoạn xử lý: process skip

Process skip xảy ra khi ItemProcessor ném exception và exception được cho phép skip.

Ví dụ:

~~~java
@Bean
ItemProcessor<CustomerInput, Customer> customerProcessor() {
    return input -> {
        if (input.email() == null || input.email().isBlank()) {
            throw new InvalidCustomerException(
                "Email là trường bắt buộc"
            );
        }

        return new Customer(
            input.customerId(),
            input.fullName(),
            input.email()
        );
    };
}
~~~

Cấu hình Step:

~~~java
.faultTolerant()
.skip(InvalidCustomerException.class)
.skipLimit(50)
~~~

Nếu một item có email thiếu, processor ném InvalidCustomerException. Spring Batch có thể skip item đó và tiếp tục xử lý các item khác.

### Không biến filter thành exception

Nếu item bị loại theo quy tắc bình thường, processor nên trả null. Không nên ném exception chỉ để tăng skip count.

Ví dụ:

- Đơn hàng bị hủy và không cần xuất: trả null.
- Khách hàng thiếu email bắt buộc: ném InvalidCustomerException và skip nếu nghiệp vụ cho phép.
- Dịch vụ xác minh khách hàng tạm thời timeout: có thể retry.
- Dữ liệu vi phạm quy tắc không thể bỏ qua: để Step thất bại.

Việc phân biệt rõ giúp filterCount, processSkipCount và retry metrics phản ánh đúng hành vi.

## 7. Skip ở giai đoạn ghi: write skip

Write skip xảy ra khi ItemWriter ném exception và exception được phép skip.

Đây là trường hợp cần hiểu rõ rollback nhất vì writer thường nhận cả chunk thay vì một item đơn lẻ.

Ví dụ writer ghi batch vào database:

~~~java
@Bean
JdbcBatchItemWriter<Customer> customerWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Customer>()
        .dataSource(dataSource)
        .sql("""
            INSERT INTO customer_result(customer_id, full_name, email)
            VALUES (:customerId, :fullName, :email)
            """)
        .beanMapped()
        .build();
}
~~~

Nếu một bản ghi vi phạm unique constraint, batch write có thể ném exception. Khi exception làm transaction rollback, các thay đổi trong chunk hiện tại tham gia transaction bị hoàn tác.

Để xác định item gây lỗi, cơ chế fault-tolerant của Spring Batch có thể rollback chunk rồi thực hiện lại việc ghi theo cách cô lập item lỗi. Các item hợp lệ được ghi lại; item gây lỗi được skip nếu policy cho phép.

~~~mermaid
flowchart TD
    A["Writer nhận chunk A, B, C, D"] --> B["Ghi batch"]
    B --> C{"Có lỗi tại một item?"}
    C -- "Không" --> D["Commit chunk"]
    C -- "Có" --> E["Rollback transaction chunk"]
    E --> F["Framework xác định item lỗi"]
    F --> G["Ghi lại các item hợp lệ"]
    G --> H["Skip item lỗi nếu policy cho phép"]
    H --> I["Commit kết quả hợp lệ"]
~~~

Sơ đồ là mô hình khái niệm. Chi tiết scan và số lần gọi writer phụ thuộc cấu hình fault-tolerant, rollback classifier và implementation của writer.

### Vì sao writer có thể được gọi nhiều lần?

Writer nhận một Chunk gồm nhiều item. Khi một item gây exception, framework cần biết item nào lỗi. Trong quá trình cô lập lỗi, writer có thể được gọi lại với các tập item hoặc từng item riêng.

Vì vậy:

- Một lần gọi write() không nhất thiết tương ứng một lần commit.
- Writer có thể nhận cùng item nhiều lần trong quá trình retry/scan.
- Side effect bên ngoài transaction có thể bị thực hiện lặp.
- Writer cần idempotent hoặc chỉ thực hiện thao tác tham gia transaction.

Không nên thiết kế writer với giả định mỗi item chỉ được gửi đến writer đúng một lần.

## 8. Rollback chunk có nghĩa gì?

Rollback hoàn tác các thay đổi được thực hiện trong transaction hiện tại. Trong chunk Step, điều này thường bao gồm các câu lệnh JDBC/JPA tham gia transaction do Step quản lý.

Giả sử chunk có 4 item A, B, C, D:

1. Writer bắt đầu ghi các item.
2. A và B được insert thành công trong transaction.
3. C gây lỗi constraint.
4. Writer ném exception.
5. Transaction chunk rollback.
6. Các insert A và B trong transaction đó cũng bị hoàn tác.
7. Framework xử lý lỗi theo retry/skip policy.
8. Nếu C được skip và các item còn lại ghi thành công, transaction phù hợp được commit.

Rollback không có nghĩa mọi dữ liệu của Job bị xóa. Các chunk trước đó đã commit vẫn tồn tại.

Ví dụ:

~~~text
Chunk 1: A, B, C -> COMMIT
Chunk 2: D, E, F -> writer error -> ROLLBACK
Chunk 3: chưa chạy

Kết quả:
- A, B, C vẫn được lưu.
- Các thay đổi của D, E, F trong transaction chunk 2 bị hoàn tác.
- Step xử lý chunk 2 theo policy.
~~~

### Transaction chỉ rollback tài nguyên tham gia transaction

Nếu writer ghi qua JdbcTemplate dùng cùng DataSource và transaction manager, thay đổi database có thể rollback cùng chunk.

Nếu writer gửi email, gọi HTTP API, ghi file bằng Files API hoặc gửi message ra broker không tham gia transaction, các side effect đó không tự biến mất khi database rollback.

Do đó, rollback không phải là một cơ chế hoàn tác toàn hệ thống. Nó chỉ bảo vệ các tài nguyên nằm trong ranh giới transaction.

## 9. Mối quan hệ giữa skip và rollback theo từng giai đoạn

Hành vi transaction phụ thuộc vị trí exception, rollback classifier và resource. Không nên giả định mọi skip đều rollback theo cùng một cách.

| Giai đoạn | Exception | Hành vi cần hiểu |
|---|---|---|
| Reader | Lỗi đọc item | Reader không trả item; policy có thể skip lỗi đọc và tiếp tục |
| Processor | Lỗi xử lý item | Item có thể bị skip; transaction behavior phụ thuộc rollback policy và cấu hình |
| Writer | Lỗi ghi chunk | Mặc định lỗi writer thường làm rollback transaction chunk; framework có thể cô lập item lỗi khi skip được cấu hình |
| Listener | Lỗi callback | Có thể làm Step thất bại; không phải item skip tự động |

Một số điểm quan trọng:

- Skip quyết định item lỗi có được bỏ qua hay không.
- Rollback classifier quyết định exception có làm transaction hiện tại rollback hay không.
- Retry policy quyết định exception có được thử lại hay không.
- Skip policy quyết định exception có được phép bỏ qua hay không.

Các chính sách có thể tương tác. Hãy kiểm thử exception thực tế ở đúng giai đoạn, với đúng transaction manager và writer mà ứng dụng sử dụng.

### Vì sao cần phân biệt?

Nếu một exception không rollback transaction nhưng writer đã thực hiện một phần thay đổi, việc tiếp tục có thể để lại dữ liệu không nhất quán. Ngược lại, rollback quá rộng có thể làm mất công việc đã làm trong chunk dù exception chỉ liên quan một item.

Không thay đổi rollback policy chỉ để tăng tốc. Cần hiểu transaction resource, side effect và cách framework khôi phục chunk.

## 10. Dùng noRollback khi thực sự cần

FaultTolerantStepBuilder cung cấp `noRollback(...)` để khai báo exception không làm transaction rollback.

Ví dụ:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<InputRecord, OutputRecord>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .skip(InvalidRecordException.class)
    .skipLimit(20)
    .noRollback(InvalidRecordException.class)
    .build();
~~~

Cấu hình này minh họa việc phân loại InvalidRecordException là lỗi có thể skip và không yêu cầu rollback theo chính sách của Step.

Tuy nhiên, `noRollback` không có nghĩa exception tự động bị skip. Skip policy vẫn phải cho phép exception đó. Nếu exception không được phép skip, Step vẫn có thể thất bại.

### Cẩn thận khi dùng noRollback

Không nên dùng noRollback cho lỗi writer đã có thể ghi một phần dữ liệu mà không hiểu rõ transaction. Nếu transaction không rollback, các thay đổi trước exception có thể vẫn nằm trong transaction và được commit cùng những thao tác tiếp theo.

Chỉ dùng noRollback khi:

- Exception không làm cho trạng thái transaction bị hỏng.
- Thao tác đã thực hiện trước exception vẫn hợp lệ.
- Các tài nguyên liên quan có hành vi đã được hiểu rõ.
- Có kiểm thử chứng minh kết quả cuối nhất quán.

Trong nhiều tình huống, để writer exception rollback chunk rồi cho framework cô lập item lỗi sẽ dễ bảo đảm tính toàn vẹn hơn.

## 11. Skip limit và SkipLimitExceededException

Skip limit là hàng rào bảo vệ để Step không tiếp tục khi dữ liệu lỗi vượt ngưỡng cho phép.

Ví dụ:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidCustomerException.class)
.skipLimit(25)
~~~

Hai loại exception được phép skip nhưng tổng số item bị skip không được vượt quá 25.

Nếu item lỗi thứ 26 cần được skip, Step thất bại với SkipLimitExceededException. Điều này giúp Job không âm thầm hoàn tất khi nguồn dữ liệu có quá nhiều lỗi.

### Skip limit bằng 0

Nếu không cấu hình skip hoặc đặt giới hạn bằng 0, exception không được phép bỏ qua theo policy sẽ làm Step thất bại. Nếu nghiệp vụ yêu cầu không chấp nhận bất kỳ dữ liệu lỗi nào, đây là hành vi phù hợp.

### Giới hạn theo tỷ lệ dữ liệu

Một skip limit tuyệt đối có thể không phù hợp với mọi kích thước lô. Ví dụ, cho phép 20 lỗi trong lô 100 item tương đương 20%, nhưng trong lô 1.000.000 item chỉ là tỷ lệ rất nhỏ.

Có thể kết hợp:

- Skip limit tuyệt đối để chặn số lượng tối đa.
- Validation Step để tính tỷ lệ lỗi.
- ExitStatus tùy chỉnh nếu tỷ lệ lỗi vượt ngưỡng nghiệp vụ.
- Báo cáo reject để vận hành quyết định có publish hay không.

Skip limit của Step vẫn là số lượng item. Nếu cần tỷ lệ, phải tính và kiểm tra riêng.

## 12. Skip nhiều loại exception và loại trừ exception

Có thể cho phép nhiều exception:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidCustomerException.class)
.skip(InvalidOrderAmountException.class)
.skipLimit(50)
~~~

Có thể loại trừ một exception cụ thể bằng `noSkip(...)`:

~~~java
.faultTolerant()
.skip(Exception.class)
.noSkip(FileNotFoundException.class)
.skipLimit(50)
~~~

Ví dụ thứ hai rất rộng và chỉ nên dùng khi có lý do rõ ràng. Cho phép skip mọi Exception có thể làm Job bỏ qua cả lỗi lập trình, lỗi cấu hình và lỗi hạ tầng.

Nên ưu tiên khai báo exception cụ thể. Nếu một superclass được skip nhưng subclass cụ thể không được phép skip, hãy kiểm thử cách phân loại exception và thứ tự ưu tiên trong phiên bản Spring Batch đang dùng.

### Không phân loại theo message

Không nên viết logic skip dựa vào nội dung message như "temporary" hoặc "invalid" nếu có thể dùng loại exception riêng. Message có thể thay đổi theo driver, locale hoặc phiên bản thư viện.

Hãy tạo exception nghiệp vụ có ngữ nghĩa ổn định tại ranh giới ứng dụng.

## 13. Dùng SkipPolicy tùy chỉnh

Khi quy tắc skip phức tạp, có thể triển khai SkipPolicy thay vì khai báo danh sách exception đơn giản.

Interface:

~~~java
public interface SkipPolicy {
    boolean shouldSkip(Throwable t, long skipCount)
        throws SkipLimitExceededException;
}
~~~

Ví dụ policy cho phép skip lỗi parse tối đa 10 lần, nhưng không skip lỗi không tìm thấy file:

~~~java
public class ImportSkipPolicy implements SkipPolicy {

    private final long limit;

    public ImportSkipPolicy(long limit) {
        this.limit = limit;
    }

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount)
            throws SkipLimitExceededException {

        if (throwable instanceof FileNotFoundException) {
            return false;
        }

        if (throwable instanceof FlatFileParseException
                || throwable instanceof InvalidCustomerException) {
            if (skipCount < limit) {
                return true;
            }

            throw new SkipLimitExceededException(
                "Vượt giới hạn skip",
                skipCount,
                throwable
            );
        }

        return false;
    }
}
~~~

Đăng ký policy:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<CustomerInput, Customer>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .skipPolicy(new ImportSkipPolicy(10))
    .build();
~~~

Custom policy hữu ích khi quyết định skip cần dựa trên loại exception, metadata hoặc số lượng lỗi. Policy nên thuần và xác định; tránh gọi API hoặc thực hiện side effect trong `shouldSkip` vì phương thức có thể được gọi trong quá trình phân loại lỗi.

Nếu dùng SkipPolicy tùy chỉnh, hãy kiểm thử riêng giới hạn và các loại exception. Không nên đồng thời cấu hình skip limit theo cách gây nhầm lẫn về policy nào đang quyết định.

## 14. SkipListener ghi nhận item bị bỏ

SkipListener cung cấp callback để ghi nhận item thực sự bị skip:

~~~java
public interface SkipListener<T, S> extends StepListener {

    void onSkipInRead(Throwable t);

    void onSkipInWrite(S item, Throwable t);

    void onSkipInProcess(T item, Throwable t);
}
~~~

Trong đó:

- `onSkipInRead` nhận exception vì reader không tạo được item.
- `onSkipInProcess` nhận item đầu vào và exception từ processor.
- `onSkipInWrite` nhận item output và exception từ writer.

Ví dụ:

~~~java
@Bean
SkipListener<CustomerInput, Customer> customerSkipListener(
        RejectedCustomerService rejectedCustomerService) {

    return new SkipListener<>() {

        @Override
        public void onSkipInRead(Throwable throwable) {
            if (throwable instanceof FlatFileParseException ex) {
                rejectedCustomerService.recordReadError(
                    ex.getLineNumber(),
                    ex.getInput(),
                    ex.getMessage()
                );
            }
        }

        @Override
        public void onSkipInProcess(
                CustomerInput item,
                Throwable throwable) {
            rejectedCustomerService.recordProcessError(
                item.customerId(),
                throwable.getMessage()
            );
        }

        @Override
        public void onSkipInWrite(
                Customer item,
                Throwable throwable) {
            rejectedCustomerService.recordWriteError(
                item.customerId(),
                throwable.getMessage()
            );
        }
    };
}
~~~

Gắn listener vào Step:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<CustomerInput, Customer>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .skip(FlatFileParseException.class)
    .skip(InvalidCustomerException.class)
    .skipLimit(20)
    .listener(customerSkipListener)
    .build();
~~~

### SkipListener khác ItemProcessListener và ItemWriteListener

ItemProcessListener.onProcessError được gọi khi processor ném exception; item có thể được retry và cuối cùng thành công. SkipListener.onSkipInProcess phản ánh quyết định item bị skip.

ItemWriteListener.onWriteError quan sát lỗi của lần gọi writer; nó không khẳng định mọi item trong chunk đều bị skip. SkipListener.onSkipInWrite được gọi cho item thực sự bị bỏ sau khi framework xác định item lỗi.

Vì vậy, hãy dùng SkipListener cho reject record cuối cùng. Dùng listener khác để quan sát mọi lần thử hoặc mọi lần gọi.

### Thời điểm gọi SkipListener

Spring Batch gọi SkipListener gần thời điểm commit của chunk, sau khi đã xác định item bị skip. Cách tổ chức này giúp giảm nguy cơ ghi reject record nhiều lần khi chunk rollback và được xử lý lại.

Nếu SkipListener ghi reject record bằng cùng transaction manager và cùng database, bản ghi reject có thể commit cùng chunk hợp lệ. Nếu listener gọi API hoặc ghi file bên ngoài, side effect đó không tự rollback. Hãy thiết kế idempotency và xử lý lỗi listener phù hợp.

## 15. Writer lỗi và cơ chế cô lập item gây lỗi

Đây là trường hợp thường khiến người mới hiểu nhầm skip và rollback.

Giả sử writer nhận chunk gồm A, B, C, D. Bản ghi C vi phạm unique constraint:

~~~text
write([A, B, C, D])
    -> database báo lỗi do C
    -> transaction rollback
~~~

Nếu exception thuộc loại được phép skip, framework cần xác định item gây lỗi. Với writer có thể được gọi lại an toàn, Spring Batch có thể thực hiện scan để cô lập item lỗi:

~~~text
Ghi thử tập item / từng item
A -> thành công
B -> thành công
C -> lỗi
D -> thành công

C bị skip
A, B, D được ghi lại theo chunk hợp lệ
Transaction cuối cùng commit nếu mọi thao tác cần thiết thành công
~~~

Đây là mô tả khái niệm về quá trình xác định item lỗi. Implementation có thể gọi writer nhiều lần và chia chunk theo cách cụ thể của framework.

### Vì sao cần rollback trước khi scan?

Nếu lần ghi đầu đã insert A và B rồi thất bại ở C, transaction rollback làm A và B không còn được commit một phần. Sau đó framework có thể thực hiện lại các item hợp lệ và bỏ C.

Nếu không rollback, lần scan có thể ghi lại A và B lần nữa, gây duplicate hoặc dữ liệu không nhất quán.

### Writer cần tuân thủ một số nguyên tắc

- Dùng transaction-bound resource khi ghi database.
- Không tự commit connection bên trong writer.
- Không gửi email hoặc API request trong mỗi lần write nếu chưa có idempotency.
- Không giữ trạng thái mutable cho rằng mỗi item chỉ xuất hiện một lần.
- Có thể được gọi lại với cùng item hoặc các tập item khác nhau.
- Nếu writer tổng hợp nhiều delegate, hiểu rõ side effect của từng delegate.

### Khi writer không thể scan an toàn

Một số writer chỉ có thể ghi theo batch và không thể xác định item lỗi bằng cách gọi lại từng item. Một số writer có side effect không thể hoàn tác. Trong các trường hợp đó, cần thiết kế writer hoặc error handling khác, ví dụ pre-validation trước khi ghi, chia chunk nhỏ hơn, ghi reject theo cơ chế riêng hoặc fail Step để điều tra.

Không nên bật write skip với writer có side effect không idempotent mà chưa kiểm thử cách framework gọi lại writer.

## 16. Reader buffering và rollback

Khi chunk rollback, framework có thể cần đọc lại các item đã được reader cung cấp cho chunk. Với reader thông thường, Spring Batch thường buffer item trong chunk để có thể phát lại mà không tiêu thụ nguồn thêm lần nữa.

Điều này quan trọng với nguồn không thể đọc lại dễ dàng, chẳng hạn cursor hoặc file reader.

Với transactional queue, tình huống khác: message có thể được trả lại queue khi transaction rollback. Khi đó, việc buffer thêm trong framework có thể không phù hợp. Có thể cấu hình Step bằng `readerIsTransactionalQueue()` để thông báo reader lấy item từ transactional queue và framework không dùng cơ chế buffering thông thường cho item đó.

Ví dụ cấu hình:

~~~java
return new StepBuilder("queueImportStep", jobRepository)
    .<Message, ProcessedMessage>chunk(50, transactionManager)
    .reader(messageReader)
    .processor(messageProcessor)
    .writer(messageWriter)
    .readerIsTransactionalQueue()
    .faultTolerant()
    .skip(InvalidMessageException.class)
    .skipLimit(10)
    .build();
~~~

API và cách tích hợp queue phụ thuộc transaction manager, broker và phiên bản Spring Batch. Cần xác nhận message được acknowledge hoặc rollback đúng thời điểm.

### Không acknowledge message quá sớm

Nếu reader acknowledge message trước khi chunk commit, database có thể rollback nhưng message đã biến mất khỏi queue. Khi restart, item không còn để xử lý lại.

Với queue, phải phối hợp transaction hoặc acknowledgment mode để bảo đảm message chỉ được xác nhận khi công việc tương ứng đã đạt trạng thái an toàn.

## 17. Kết hợp retry và skip

Một exception có thể vừa retryable vừa skippable nếu nghiệp vụ muốn thử lại trước, sau đó bỏ item khi hết retry.

Ví dụ:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<OrderInput, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientRemoteServiceException.class)
    .retryLimit(3)
    .skip(TransientRemoteServiceException.class)
    .skipLimit(20)
    .build();
~~~

Ý nghĩa mong muốn:

1. Gặp lỗi dịch vụ tạm thời thì retry theo giới hạn.
2. Nếu một lần thử thành công, item tiếp tục xử lý.
3. Nếu hết retry và exception vẫn còn, policy skip có thể bỏ item nếu giới hạn skip còn cho phép.
4. Nếu không thể skip hoặc vượt skip limit, Step thất bại.

Cần kiểm thử đúng thứ tự và số lần thử của phiên bản Spring Batch/Spring Retry đang dùng. Retry limit và skip limit là hai bộ đếm khác nhau.

### Khi nào không nên kết hợp?

Nếu lỗi là database mất kết nối trên diện rộng, skip item sau vài lần retry có thể làm Job hoàn tất với dữ liệu thiếu hàng loạt. Với lỗi hạ tầng diện rộng, thường nên fail Step thay vì skip từng item.

Chỉ kết hợp retry và skip khi lỗi cuối cùng thực sự có thể được xem là lỗi riêng của item và nghiệp vụ cho phép bỏ nó.

## 18. Skip và rollback của transaction ngoài database

Transaction manager của Step chỉ quản lý những resource tham gia transaction đó.

Ví dụ writer thực hiện:

1. Insert dữ liệu vào database.
2. Gửi message đến broker.
3. Sau đó gặp lỗi ở một item khác.
4. Transaction database rollback.

Database có thể rollback insert, nhưng message đã gửi có thể vẫn tồn tại trong broker. Nếu framework retry hoặc scan writer, message có thể được gửi lại.

Các hướng thiết kế an toàn:

- Ghi database và outbox event trong cùng transaction.
- Publish outbox sau khi chunk commit.
- Dùng message ID ổn định và consumer deduplication.
- Dùng idempotency key cho API.
- Tách file output thành file tạm và publish ở Step riêng.
- Ghi reject record vào database cùng transaction khi phù hợp.

Không coi rollback database là rollback toàn bộ hệ thống.

## 19. Restart sau khi skip hoặc rollback

Skip xảy ra trong một JobExecution đang chạy. Restart xảy ra sau khi JobExecution thất bại hoặc dừng.

Giả sử:

~~~text
Chunk 1: 100 item -> commit
Chunk 2: một số item lỗi -> skip trong giới hạn -> commit
Chunk 3: writer gặp lỗi không skipable -> rollback -> Step FAILED
~~~

Khi restart cùng JobInstance:

- Chunk 1 đã commit vẫn được giữ.
- Chunk 2 đã commit cùng kết quả skip vẫn được giữ.
- Chunk 3 được xử lý lại theo checkpoint và reader state.
- Reader phải hỗ trợ restart hoặc có cơ chế khôi phục vị trí.
- Writer cần idempotent để tránh dữ liệu trùng nếu có side effect ngoài transaction.

Nếu một item đã được skip và chunk chứa nó đã commit, restart thông thường không nên tự đưa item đó trở lại luồng xử lý của cùng Step. Muốn xử lý lại reject item, cần một quy trình riêng đọc reject data hoặc một JobInstance mới theo chính sách nghiệp vụ.

### Reject data cần có định danh

Khi ghi item bị skip, nên lưu:

- Batch ID.
- Source identifier hoặc file name.
- Line number nếu có.
- Business key của item nếu đã đọc được.
- Loại exception.
- Thông điệp lỗi đã được làm sạch.
- Thời điểm và StepExecution ID.

Thông tin này giúp xử lý lại reject record mà không cần quét lại toàn bộ nguồn hoặc suy đoán item nào đã bị bỏ.

## 20. Theo dõi skip và rollback qua StepExecution

Spring Batch lưu các bộ đếm trong StepExecution:

| Bộ đếm | Ý nghĩa |
|---|---|
| readCount | Số item đọc thành công |
| writeCount | Số item writer ghi thành công |
| filterCount | Số item processor lọc bằng null |
| readSkipCount | Số lỗi đọc được skip |
| processSkipCount | Số lỗi xử lý được skip |
| writeSkipCount | Số lỗi ghi được skip |
| commitCount | Số lần commit |
| rollbackCount | Số lần rollback |

Tổng skip count có thể xem bằng `stepExecution.getSkipCount()`. Khi điều tra, hãy xem riêng từng giai đoạn để biết lỗi phát sinh ở đâu.

Ví dụ:

~~~text
readCount        = 1000
writeCount       = 970
filterCount      = 10
readSkipCount    = 5
processSkipCount = 10
writeSkipCount   = 5
~~~

Số liệu này cho biết có 20 skip và 10 filter. Tuy nhiên, không nên chỉ cộng các bộ đếm rồi giả định chúng luôn khớp với một công thức đơn giản trong mọi tình huống retry, rollback hoặc writer scan. Hãy đối chiếu cùng dữ liệu nguồn và log thực tế.

### Ghi log và cảnh báo

Có thể ghi thống kê khi Step kết thúc:

~~~java
@Bean
StepExecutionListener skipSummaryListener() {
    return new StepExecutionListener() {

        @Override
        public void beforeStep(StepExecution stepExecution) {
            // Không cần thao tác trước Step trong ví dụ này.
        }

        @Override
        public ExitStatus afterStep(StepExecution stepExecution) {
            log.info(
                "step={}, read={}, write={}, readSkip={}, processSkip={}, writeSkip={}, rollback={}",
                stepExecution.getStepName(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getReadSkipCount(),
                stepExecution.getProcessSkipCount(),
                stepExecution.getWriteSkipCount(),
                stepExecution.getRollbackCount()
            );
            return null;
        }
    };
}
~~~

Có thể cảnh báo nếu tổng skip vượt ngưỡng tỷ lệ nghiệp vụ, ngay cả khi chưa chạm skipLimit. Không log toàn bộ item nếu chứa dữ liệu nhạy cảm.

## 21. Tạo ExitStatus riêng khi có skip

Một Step có thể hoàn tất kỹ thuật với BatchStatus COMPLETED nhưng có item bị skip. Nếu nghiệp vụ không muốn publish output khi có skip, có thể tạo ExitStatus tùy chỉnh trong StepExecutionListener.

Ví dụ:

~~~java
@Bean
StepExecutionListener skipStatusListener() {
    return new StepExecutionListener() {

        @Override
        public void beforeStep(StepExecution stepExecution) {
        }

        @Override
        public ExitStatus afterStep(StepExecution stepExecution) {
            if (stepExecution.getSkipCount() > 0) {
                return new ExitStatus("COMPLETED_WITH_SKIPS");
            }

            return null;
        }
    };
}
~~~

Flow có thể tách nhánh:

~~~java
.start(importStep)
    .on("COMPLETED").to(publishStep)
.from(importStep)
    .on("COMPLETED_WITH_SKIPS").to(reviewStep)
.from(importStep)
    .on("*").fail()
~~~

Cách này cho phép:

- Publish ngay nếu không có skip.
- Chuyển sang review nếu có reject.
- Fail nếu Step trả ExitStatus không được hỗ trợ.

Không nên giả định skip tự động thay đổi ExitStatus thành COMPLETED_WITH_SKIPS. Nếu muốn flow phân biệt, phải chủ động tạo mã kết quả.

## 22. Kiểm thử skip và rollback

Kiểm thử cần xác nhận cả số liệu và trạng thái dữ liệu trong database. Chỉ xác nhận Job COMPLETED là chưa đủ.

### Test process skip

Tạo processor ném InvalidRecordException cho một item:

~~~java
ItemProcessor<InputRecord, OutputRecord> processor = item -> {
    if (item.id().equals("BAD")) {
        throw new InvalidRecordException("Record không hợp lệ");
    }

    return map(item);
};
~~~

Kỳ vọng:

- Item BAD không đến writer.
- processSkipCount tăng 1.
- Các item hợp lệ vẫn được ghi.
- SkipListener nhận item và exception tương ứng.

### Test write skip và rollback chunk

Chuẩn bị chunk gồm A, B, C, D và làm cho writer thất bại khi ghi C.

Xác nhận:

1. Lần ghi chunk ban đầu gây exception.
2. Transaction của chunk rollback.
3. Không còn dữ liệu ghi dở từ lần thử đầu.
4. Framework xác định item C là item lỗi.
5. C bị skip nếu policy cho phép.
6. A, B và D được ghi thành công.
7. writeSkipCount tăng đúng.
8. Không có dữ liệu trùng do writer được gọi lại.

Nên dùng database test có transaction thật để xác nhận rollback. Mock writer có thể kiểm tra số lần gọi nhưng không chứng minh transaction database đã hoàn tác.

### Test vượt skip limit

Với skipLimit là 2, tạo ba item lỗi được phép skip. Xác nhận:

- Hai item đầu được skip.
- Item lỗi tiếp theo làm Step thất bại do vượt giới hạn.
- Các chunk đã commit trước đó vẫn được giữ.
- Chunk hiện tại tuân theo rollback policy.
- JobExecution và StepExecution phản ánh trạng thái lỗi.

### Test noSkip

Khai báo một exception thuộc nhóm rộng được skip nhưng loại trừ exception cụ thể bằng noSkip. Xác nhận exception bị loại làm Step thất bại thay vì skip.

### Test retry rồi skip

Cho một item ném exception retryable và skippable. Xác nhận số lần thử, thời điểm skip, skip count và dữ liệu reject phù hợp policy.

### Test reader buffering và queue

Với reader thường, tạo lỗi writer giữa chunk và xác nhận item được phát lại đúng sau rollback. Với transactional queue, kiểm thử acknowledgment/redelivery để chắc chắn message không bị mất.

## 23. Những lỗi thiết kế thường gặp

### Skip mọi exception

Cấu hình skip(Exception.class) quá rộng có thể che giấu lỗi lập trình, cấu hình hoặc hạ tầng. Chỉ skip exception có ý nghĩa nghiệp vụ rõ ràng.

### Skip limit quá cao

Job có thể hoàn tất với lượng dữ liệu lỗi không thể chấp nhận. Đặt limit và kiểm tra tỷ lệ lỗi theo lô.

### Nhầm filter với skip

Processor trả null là filter, không phải exception skip. Dùng đúng cơ chế để metrics phản ánh đúng.

### Cho rằng skip không rollback

Skip và rollback là hai quyết định riêng. Đặc biệt với writer, transaction chunk thường rollback trước khi framework cô lập item lỗi.

### Writer không an toàn khi được gọi lại

Writer có thể nhận cùng item hoặc nhóm item nhiều lần khi scan, retry hoặc rollback. Side effect ngoài transaction có thể bị lặp.

### Dùng noRollback để né rollback mà không hiểu dữ liệu

Không rollback có thể giữ thay đổi đã thực hiện trước exception. Chỉ cấu hình khi trạng thái transaction vẫn hợp lệ và đã được kiểm thử.

### Ghi reject trong mỗi lần onWriteError

onWriteError quan sát một lần gọi writer thất bại; writer có thể được gọi lại. Dùng SkipListener để ghi nhận item thực sự bị skip.

### Skip lỗi hạ tầng

Bỏ qua lỗi database hoặc API trên diện rộng có thể tạo output thiếu. Lỗi hạ tầng thường nên retry có giới hạn rồi fail nếu không phục hồi.

### Gửi message hoặc gọi API trong writer không idempotent

Rollback database không thu hồi message hoặc request đã được hệ thống khác xử lý. Dùng outbox, idempotency key hoặc publish sau commit.

### Không kiểm thử rollback thật

Test chỉ kiểm tra callback không chứng minh database đã rollback. Dùng transaction integration test và xác nhận dữ liệu trong bảng.

## 24. Quy trình thiết kế skip an toàn

Khi xây dựng một Step có skip, có thể thực hiện theo trình tự:

1. **Phân loại lỗi:** xác định lỗi dữ liệu riêng lẻ, lỗi tạm thời hay lỗi hạ tầng.
2. **Chọn giai đoạn:** xác định lỗi phát sinh ở reader, processor hay writer.
3. **Định nghĩa exception:** dùng loại exception cụ thể và ổn định.
4. **Đặt skip limit:** xác định số lỗi tối đa cho cả Step.
5. **Thiết kế rollback:** kiểm tra exception nào rollback và resource nào tham gia transaction.
6. **Xem xét retry:** retry lỗi tạm thời trước khi skip nếu nghiệp vụ cho phép.
7. **Ghi reject data:** dùng SkipListener để lưu định danh và nguyên nhân item bị bỏ.
8. **Bảo đảm idempotency:** writer và listener phải an toàn khi được gọi lại.
9. **Theo dõi metrics:** đọc riêng read/process/write skip, filter, commit và rollback.
10. **Kiểm thử:** xác nhận skip từng giai đoạn, write scan, rollback, vượt limit, retry và restart.

## 25. Những điểm cần nhớ

- Skip cho phép bỏ qua item gặp exception đã được xác định là có thể bỏ.
- Cấu hình skip bằng faultTolerant(), skip(...) và skipLimit(...).
- Skip limit là tổng số item bị skip trong Step, bao gồm read, process và write.
- Reader skip xảy ra khi reader ném exception; EOF null không phải skip.
- Processor trả null là filter; processor ném exception có thể tạo process skip.
- Writer skip phức tạp hơn vì writer nhận cả chunk và lỗi có thể làm transaction rollback.
- Khi writer thất bại, framework có thể rollback rồi cô lập item gây lỗi; writer có thể được gọi lại nhiều lần.
- Rollback chỉ hoàn tác tài nguyên tham gia transaction; email, API, file và message bên ngoài không tự rollback.
- noRollback thay đổi rollback classification, không tự biến exception thành skip.
- SkipListener ghi nhận item thực sự bị bỏ; ItemProcessListener và ItemWriteListener quan sát các lần xử lý/gọi writer.
- Retry và skip có thể kết hợp; retry limit và skip limit là hai giới hạn khác nhau.
- Dùng reader buffering hoặc transactional queue đúng với cơ chế nguồn.
- Theo dõi readSkipCount, processSkipCount, writeSkipCount, filterCount, commitCount và rollbackCount.
- Kiểm thử rollback bằng database thật trong integration test, không chỉ mock writer.

Skip được thiết kế đúng giúp Spring Batch tiếp tục xử lý những item hợp lệ trong khi vẫn ghi nhận dữ liệu lỗi. Khi hiểu transaction rollback, đặc biệt ở writer, và giới hạn side effect ngoài transaction, ứng dụng có thể bỏ qua lỗi cục bộ mà vẫn bảo vệ tính toàn vẹn của chunk và toàn bộ Job.

