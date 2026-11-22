# Tệp có dòng lỗi và skip

Khi xử lý file CSV, TSV hoặc fixed-width bằng Spring Batch, không phải dòng nào cũng có dữ liệu hợp lệ. Một dòng có thể thiếu cột, thừa token, sai định dạng ngày, chứa số không chuyển đổi được hoặc vi phạm quy tắc nghiệp vụ. Nếu mọi lỗi đều làm Job dừng, một file lớn có thể không được xử lý chỉ vì vài bản ghi sai.

Spring Batch hỗ trợ **skip** để bỏ qua những item lỗi được cho phép và tiếp tục xử lý các dòng hợp lệ. Với Flat File, lỗi parse thường được biểu diễn bằng **FlatFileParseException**. Step có thể cấu hình exception này là skippable, đặt giới hạn skip và dùng SkipListener để ghi nhận dòng bị loại.

Điều quan trọng là phân biệt lỗi của một dòng dữ liệu với lỗi của toàn bộ resource. Một dòng CSV không đúng định dạng có thể được skip; file không tồn tại, không có quyền đọc hoặc không thể mở thường là lỗi khởi tạo resource và cần làm Step thất bại.

## 1. Các loại lỗi thường gặp trong flat file

Một file đầu vào có thể chứa nhiều dạng lỗi:

| Loại lỗi | Ví dụ | Giai đoạn thường phát hiện |
|---|---|---|
| Thiếu hoặc thừa cột | Dòng CSV có 2 trường trong khi cần 3 | Tokenizer |
| Sai kiểu dữ liệu | Ngày không đúng định dạng, số tiền chứa chữ | FieldSetMapper hoặc conversion |
| Dòng không đúng cấu trúc | Dấu phân cách hoặc dấu quote không hợp lệ | LineTokenizer / RecordSeparatorPolicy |
| Giá trị bắt buộc bị thiếu | customerId rỗng | Mapper hoặc ItemProcessor |
| Vi phạm nghiệp vụ | Mã khách hàng không hợp lệ | ItemProcessor |
| Resource không tồn tại | Đường dẫn file sai | open của reader |
| Không đủ quyền truy cập | Tài khoản ứng dụng không đọc được file | open của reader |
| Lỗi I/O giữa lúc đọc | File system hoặc thiết bị gặp sự cố | read của reader |

Không phải mọi lỗi trên đều nên được xử lý bằng skip. Skip phù hợp nhất với lỗi gắn với một bản ghi cụ thể và có thể loại bản ghi đó mà vẫn tiếp tục xử lý phần còn lại. Lỗi hạ tầng hoặc resource thường ảnh hưởng toàn bộ lần chạy và không nên bị xem như một dòng dữ liệu xấu.

## 2. FlatFileItemReader xử lý từng dòng như thế nào?

FlatFileItemReader đọc resource theo dòng, sau đó chuyển mỗi dòng thành item thông qua LineMapper. LineMapper thường kết hợp một LineTokenizer để tách trường và một FieldSetMapper để ánh xạ trường sang object.

Luồng xử lý cơ bản:

~~~text
File resource
    |
    v
FlatFileItemReader
    |
    v
Đọc physical line
    |
    v
LineMapper
    |
    +--> LineTokenizer
    |       |
    |       v
    |    FieldSet
    |
    +--> FieldSetMapper
            |
            v
       Input object
            |
            v
      ItemProcessor
            |
            v
        ItemWriter
~~~

Nếu tokenizer không thể tách dòng theo cấu trúc mong đợi hoặc mapper không thể chuyển đổi dữ liệu, LineMapper có thể ném exception. FlatFileItemReader thường bọc lỗi ánh xạ dòng thành FlatFileParseException, kèm nội dung input và số dòng để hỗ trợ điều tra.

Ví dụ file CSV:

~~~csv
customerId,fullName,age
C001,An Nguyen,30
C002,Binh Tran,not-a-number
C003,Chi Le,28
C004,Du Pham
C005,Em Vo,35
~~~

Nếu field age được ánh xạ sang kiểu số, dòng C002 có thể gây lỗi chuyển đổi. Dòng C004 thiếu một trường so với schema dự kiến và có thể gây lỗi số lượng token nếu tokenizer được cấu hình strict. Các dòng còn lại có thể được đọc bình thường.

## 3. FlatFileParseException chứa thông tin gì?

FlatFileParseException là exception đặc thù cho lỗi parse một dòng flat file. Nó thường cung cấp:

- Thông báo lỗi và cause gốc.
- Số dòng liên quan thông qua getLineNumber().
- Nội dung dòng đầu vào thông qua getInput().

Thông tin này hữu ích khi ghi nhận dòng bị skip vì callback onSkipInRead không nhận object item. Reader không thể tạo item hợp lệ nên listener chỉ nhận exception.

Ví dụ:

~~~java
if (t instanceof FlatFileParseException ex) {
    log.warn("Cannot parse line {}: {}",
            ex.getLineNumber(), ex.getInput());
}
~~~

Trong production, cần cân nhắc dữ liệu nhạy cảm trước khi log toàn bộ input. Dòng có thể chứa tên, email, số tài khoản hoặc thông tin cá nhân. Có thể lưu raw line vào vùng quarantine được phân quyền, còn log chỉ ghi file ID, line number, business key nếu xác định được và error code.

Không phải mọi lỗi phát sinh khi đọc file đều là FlatFileParseException. Lỗi mở resource, lỗi I/O hoặc lỗi hạ tầng có thể mang exception khác. Vì vậy, không nên cấu hình skip rộng cho mọi exception chỉ để bỏ qua lỗi đọc.

## 4. Cấu hình reader cho CSV

Ví dụ reader đọc file CSV có header:

~~~java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException(
                "Required JobParameter input.file is missing");
    }

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)
            .delimited()
            .names("customerId", "fullName", "age")
            .targetType(CustomerInput.class)
            .strict(true)
            .saveState(true)
            .build();
}
~~~

Trong ví dụ:

- Resource được chọn theo JobParameter input.file.
- Dòng đầu được bỏ qua như header.
- Tokenizer tách dữ liệu theo delimiter mặc định của cấu hình delimited.
- Các tên field được ánh xạ sang CustomerInput.
- strict(true) yêu cầu resource phải tồn tại khi reader mở.
- saveState(true) cho phép reader lưu trạng thái để hỗ trợ restart.

CustomerInput cần tương thích với cơ chế mapping được dùng, ví dụ JavaBean có thuộc tính và setter phù hợp. Nếu cần định dạng delimiter, quote, escape hoặc conversion đặc thù, hãy cấu hình tokenizer/mapper tường minh thay vì dựa vào mặc định.

Đường dẫn file nên được xác thực theo thư mục được phép truy cập. Không ghép trực tiếp đường dẫn tùy ý từ input bên ngoài mà không kiểm tra, đặc biệt nếu Job được launch qua API.

## 5. Cấu hình skip cho dòng parse lỗi

Để bỏ qua dòng lỗi parse, cấu hình Step theo fault tolerance và khai báo FlatFileParseException là skippable:

~~~java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> customerReader,
        ItemProcessor<CustomerInput, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter,
        CustomerSkipListener skipListener) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(100, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skipLimit(25)
            .listener(skipListener)
            .build();
}
~~~

Với cấu hình này, Step cho phép tối đa 25 item bị skip theo skip policy. FlatFileParseException ở giai đoạn đọc có thể được bỏ qua; các dòng tiếp theo tiếp tục được đọc. Nếu số skip vượt giới hạn, Step thất bại.

skipLimit áp dụng tổng số skip ở read, process và write của Step, không phải 25 lỗi riêng cho từng giai đoạn. Nếu chỉ muốn bỏ qua lỗi parse ở reader, hãy chỉ khai báo loại exception phù hợp và không mở rộng thành skip mọi Exception.

Chỉ đăng ký SkipListener mà không cấu hình skip không làm cho dòng lỗi tự động được bỏ qua. Listener ghi nhận quyết định skip đã được Step chấp nhận; nó không phải policy quyết định exception có thể skip hay không.

## 6. Ví dụ dữ liệu trước và sau khi skip

Giả sử file có năm dòng dữ liệu sau header:

~~~csv
customerId,fullName,age
C001,An Nguyen,30
C002,Binh Tran,not-a-number
C003,Chi Le,28
C004,Du Pham
C005,Em Vo,35
~~~

Với schema yêu cầu ba trường và age phải chuyển đổi được sang số:

| Dòng vật lý | Nội dung | Kết quả |
|---:|---|---|
| 1 | Header | Bỏ qua theo linesToSkip |
| 2 | C001,An Nguyen,30 | Đọc thành công |
| 3 | C002,Binh Tran,not-a-number | Lỗi mapping/parse, được skip nếu policy cho phép |
| 4 | C003,Chi Le,28 | Đọc thành công |
| 5 | C004,Du Pham | Lỗi số lượng trường nếu tokenizer strict |
| 6 | C005,Em Vo,35 | Đọc thành công |

Nếu hai lỗi được phân loại skippable và skip limit còn đủ, các item C001, C003 và C005 vẫn được chuyển sang processor/writer. SkipListener nhận thông tin hai dòng lỗi để lưu audit hoặc xử lý lại.

Lưu ý: số dòng trong exception thường là số dòng của resource, không phải số thứ tự item hợp lệ sau khi loại header. Với record nhiều dòng, cần kiểm tra cách reader và RecordSeparatorPolicy xác định vị trí lỗi.

## 7. Ghi nhận dòng lỗi bằng SkipListener

SkipListener có ba callback. Với lỗi parse trong reader, callback phù hợp là onSkipInRead(Throwable t). Callback này không nhận item vì reader chưa tạo được object đầu vào.

~~~java
public class CustomerSkipListener
        implements SkipListener<CustomerInput, Customer> {

    private final SkippedLineService skippedLineService;

    public CustomerSkipListener(SkippedLineService skippedLineService) {
        this.skippedLineService = skippedLineService;
    }

    @Override
    public void onSkipInRead(Throwable t) {
        if (t instanceof FlatFileParseException ex) {
            skippedLineService.record(
                    ex.getLineNumber(),
                    ex.getInput(),
                    ex.getCause() == null
                            ? ex.getMessage()
                            : ex.getCause().getMessage());
        } else {
            skippedLineService.recordUnknownReadFailure(
                    t.getClass().getName(),
                    t.getMessage());
        }
    }

    @Override
    public void onSkipInProcess(CustomerInput item, Throwable t) {
        skippedLineService.recordValidationFailure(
                item.customerId(), t.getClass().getName(), t.getMessage());
    }

    @Override
    public void onSkipInWrite(Customer item, Throwable t) {
        skippedLineService.recordWriteFailure(
                item.customerId(), t.getClass().getName(), t.getMessage());
    }
}
~~~

Các method của SkippedLineService là API minh họa. Trong ứng dụng thực tế, nên lưu thêm:

- JobExecution ID và StepExecution ID.
- File ID hoặc đường dẫn resource đã chuẩn hóa.
- Số dòng và raw line nếu chính sách dữ liệu cho phép.
- Exception type, error code và cause đã làm sạch.
- Thời điểm skip và batch ID.
- Trạng thái xử lý lại như NEW, FIXED hoặc REPLAYED.

SkipListener thường được gọi ngay trước khi transaction chunk commit. Nếu lưu audit vào cùng database và cùng transaction manager, bản ghi skip có thể commit cùng transaction chunk. Nếu ghi sang hệ thống ngoài, thao tác đó không tự động rollback cùng transaction database; cần cân nhắc outbox hoặc idempotency.

## 8. Phân biệt dòng lỗi với header và comment

Không phải dòng nào reader không đưa vào item cũng là một dòng bị skip do lỗi.

### Header bằng linesToSkip

Reader có thể bỏ qua một số dòng đầu file:

~~~java
.linesToSkip(1)
~~~

Đây là cách xử lý header, không phải fault-tolerant skip. Dòng header không làm tăng readSkipCount và không tiêu thụ skipLimit.

Nếu cần kiểm tra header, có thể dùng skippedLinesCallback để nhận nội dung các dòng được bỏ qua ở đầu file và xác thực tên cột. Callback này khác SkipListener.

### Comment lines

FlatFileItemReader có thể được cấu hình prefix comment để không coi các dòng comment là item. Dòng comment được xử lý theo quy tắc reader, không phải item bị skip vì exception.

### Filter trong processor

Nếu processor trả null, item bị filter có chủ đích. filterCount tăng nhưng skip count không tăng và SkipListener không được gọi.

| Trường hợp | Cơ chế | Tăng skip count? |
|---|---|---|
| Header được bỏ qua | linesToSkip | Không |
| Dòng comment | Comment prefix | Không |
| Processor trả null | Filter | Không |
| Tokenizer/mapper ném exception được skip | Read skip | Có |
| Processor ném exception được skip | Process skip | Có |

## 9. Lỗi parse và lỗi mở file không giống nhau

Một dòng dữ liệu lỗi thường xuất hiện sau khi reader đã mở resource thành công. Ngược lại, nếu file không tồn tại hoặc ứng dụng không có quyền đọc, lỗi xảy ra khi reader mở resource.

Ví dụ:

| Tình huống | Thời điểm | Cách xử lý thường phù hợp |
|---|---|---|
| Dòng CSV sai số cột | Khi parse một record | Có thể skip FlatFileParseException |
| Ngày trong một dòng sai format | Khi map field | Có thể skip lỗi parse nếu policy cho phép |
| File không tồn tại | Khi open reader | Step thường thất bại |
| Không có quyền đọc file | Khi open hoặc truy cập resource | Step thường thất bại |
| File system mất kết nối giữa lúc đọc | Khi read | Retry nếu lỗi tạm thời và reader hỗ trợ; nếu không thì fail |
| File bị thay thế giữa lần chạy và restart | Khi khôi phục checkpoint hoặc đọc | Xác minh resource/version; không nên tiếp tục mù quáng |

Không nên khai báo IOException hoặc Exception nói chung là skippable nếu lỗi đó có thể làm reader mất khả năng tiếp tục. Skip chỉ có ý nghĩa khi framework có thể bỏ qua một record cụ thể và chuyển sang record tiếp theo.

strict(true) chủ yếu kiểm soát hành vi khi resource không tồn tại lúc mở. Nó không thay thế skip policy cho các dòng có nội dung sai.

## 10. Cấu hình tokenizer và mapper để phát hiện dòng sai

Độ chính xác của skip phụ thuộc việc reader nhận diện lỗi đúng. Với CSV, DelimitedLineTokenizer tách các trường theo delimiter và xử lý quote theo cấu hình. Với fixed-width, FixedLengthTokenizer dùng các Range để xác định vị trí trường.

Ví dụ tokenizer tùy chỉnh:

~~~java
@Bean
LineMapper<CustomerInput> customerLineMapper() {
    DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
    tokenizer.setNames("customerId", "fullName", "age");
    tokenizer.setStrict(true);

    BeanWrapperFieldSetMapper<CustomerInput> fieldSetMapper =
            new BeanWrapperFieldSetMapper<>();
    fieldSetMapper.setTargetType(CustomerInput.class);

    DefaultLineMapper<CustomerInput> lineMapper = new DefaultLineMapper<>();
    lineMapper.setLineTokenizer(tokenizer);
    lineMapper.setFieldSetMapper(fieldSetMapper);
    return lineMapper;
}
~~~

Sau đó gắn LineMapper vào reader:

~~~java
return new FlatFileItemReaderBuilder<CustomerInput>()
        .name("customerReader")
        .resource(resource)
        .linesToSkip(1)
        .lineMapper(customerLineMapper)
        .saveState(true)
        .build();
~~~

Với strict tokenizer, số token không khớp schema có thể phát sinh lỗi thay vì âm thầm bỏ trường. Điều này giúp nhận diện dữ liệu sai sớm. Tuy nhiên, strictness cần khớp với hợp đồng file; nếu nguồn cho phép cột tùy chọn, mapper nên xử lý trường hợp đó tường minh.

Với fixed-width file, cấu hình các range chính xác và kiểm tra chiều dài dòng. Nếu dòng ngắn hoặc dài hơn schema, cần quyết định đó là lỗi dữ liệu có thể skip hay lỗi cấu trúc file làm toàn bộ batch không đáng tin cậy.

## 11. Dòng CSV có nhiều dòng vật lý

CSV có thể chứa newline bên trong field được quote. Khi đó, một record logic có thể trải qua nhiều physical line. Reader sử dụng RecordSeparatorPolicy để xác định khi nào record hoàn tất.

Ví dụ:

~~~csv
customerId,comment
C001,"First line
second line"
C002,"Normal comment"
~~~

Record C001 là một record logic nhưng chiếm hai dòng vật lý. Nếu quote không được đóng đúng, reader có thể tiếp tục gom các dòng sau vào cùng record hoặc chỉ phát hiện lỗi khi tới cuối resource, tùy RecordSeparatorPolicy.

Vì vậy:

- Không giả định mỗi lần skip luôn tương ứng đúng một physical line.
- Ghi cả line number và input từ exception nếu có.
- Kiểm thử file có quoted newline và quote bị thiếu.
- Dùng RecordSeparatorPolicy phù hợp với định dạng nguồn.
- Nếu nguồn không cho phép multiline field, xác thực quy tắc đó một cách rõ ràng.

Khi vận hành, cần phân biệt số record bị skip với số physical line liên quan. Một record lỗi có thể chiếm nhiều dòng file.

## 12. Dòng lỗi trong processor khác dòng parse lỗi

Một dòng có thể parse thành object hợp lệ nhưng dữ liệu vẫn sai nghiệp vụ. Ví dụ tuổi âm, mã khách hàng không tồn tại hoặc ngày hiệu lực nằm ngoài phạm vi.

Lỗi parse xảy ra trong reader/LineMapper; lỗi nghiệp vụ thường được phát hiện trong ItemProcessor:

~~~java
@Component
public class CustomerProcessor
        implements ItemProcessor<CustomerInput, Customer> {

    @Override
    public Customer process(CustomerInput input) {
        if (input.getAge() < 0) {
            throw new InvalidCustomerException(
                    "Age cannot be negative for " + input.getCustomerId());
        }

        return new Customer(input.getCustomerId(), input.getFullName(),
                input.getAge());
    }
}
~~~

Nếu muốn bỏ qua lỗi nghiệp vụ, phải khai báo exception tương ứng:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidCustomerException.class)
.skipLimit(25)
~~~

Lỗi processor có item đầu vào nên onSkipInProcess nhận CustomerInput. Lỗi reader không có item đã tạo thành công nên onSkipInRead chỉ nhận Throwable. Việc phân biệt này giúp lưu được business key khi có thể và dùng line number/raw input khi chưa thể tạo object.

## 13. Skip limit và xử lý khi vượt ngưỡng

skipLimit đặt tổng số item được phép bỏ qua trong Step. Ví dụ:

~~~java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidCustomerException.class)
.skipLimit(10)
~~~

Step chấp nhận tối đa 10 skip tổng cộng. Lần skip thứ 11 làm Step thất bại. Giới hạn được tính chung cho read, process và write, không phải 10 cho mỗi giai đoạn.

Khi vượt limit:

- Step chuyển sang FAILED nếu không có flow xử lý kết quả khác.
- Chunk hiện tại được xử lý theo transaction/rollback policy.
- Các chunk đã commit trước đó vẫn tồn tại.
- Các item sau lỗi không tiếp tục được xử lý trong execution đó.
- Metadata StepExecution lưu các bộ đếm để điều tra.

Không nên tăng skip limit chỉ để Job luôn kết thúc. Với file quan trọng, tỷ lệ dòng lỗi cao có thể cho thấy file sai version, delimiter không đúng hoặc schema nguồn đã thay đổi. Nên dừng để điều tra thay vì tạo output thiếu dữ liệu.

## 14. Ghi dòng lỗi vào quarantine hoặc dead-letter file

Một quy trình import thực tế thường cần lưu các dòng bị skip để người vận hành sửa và replay. Có thể ghi vào bảng quarantine hoặc file lỗi riêng.

Một record quarantine nên có:

| Trường | Mục đích |
|---|---|
| batchId | Liên kết với lần import |
| sourceFile | Xác định file nguồn |
| lineNumber | Tìm vị trí dòng |
| rawInput | Nội dung dòng nếu được phép lưu |
| exceptionType | Nhóm lỗi |
| errorMessage | Lý do đã làm sạch |
| status | NEW, FIXED, REPLAYED hoặc REJECTED |
| createdAt | Thời điểm ghi nhận |

Với lỗi parse, lấy line number và raw input từ FlatFileParseException. Với lỗi processor, lưu business key và object đầu vào đã parse. Với lỗi writer, lưu business key của object đầu ra.

Nếu ghi dead-letter vào cùng database transaction với Step, cần hiểu rằng bản ghi quarantine có thể rollback cùng chunk. Nếu yêu cầu audit phải tồn tại ngay cả khi chunk rollback, cần thiết kế transaction riêng hoặc outbox có chủ đích; không nên giả định một lời gọi repository luôn độc lập với transaction hiện tại.

Không ghi payload nhạy cảm vào log hoặc file lỗi không được bảo vệ. Có thể lưu reference ID thay vì raw data và giới hạn quyền truy cập/retention.

## 15. Restart khi có dòng lỗi

FlatFileItemReader hỗ trợ lưu trạng thái thông qua ItemStream. Khi saveState được bật, reader có thể ghi checkpoint vào StepExecutionContext để khôi phục khi Job restart.

Ví dụ:

~~~text
Lần chạy đầu:
  open(file A, checkpoint 0)
  đọc các record đầu
  skip một dòng lỗi
  commit chunk và lưu checkpoint
  đọc tiếp
  lỗi nghiêm trọng ở chunk sau
  Job FAILED

Restart cùng JobInstance:
  open(file A, checkpoint đã lưu)
  tiếp tục từ checkpoint
  không đọc lại các chunk đã commit theo trạng thái reader
~~~

Để restart đáng tin cậy:

- Dùng cùng identifying JobParameters cho lần restart.
- Giữ nguyên file nguồn hoặc xác minh checksum/version.
- Giữ tên reader ổn định để checkpoint key không thay đổi.
- Bật saveState nếu cần khôi phục vị trí.
- Không thay đổi schema/tokenizer giữa lần chạy đầu và restart nếu điều đó làm thay đổi cách parse dữ liệu đã đọc.
- Bảo đảm writer idempotent với các tác dụng phụ ngoài transaction.

Nếu file đã bị sửa hoặc thay thế, checkpoint cũ có thể trỏ tới vị trí không còn tương ứng. Khi đó, cần quyết định rõ chạy lại như JobInstance mới với input version mới hay phục hồi file gốc; không tiếp tục với dữ liệu không xác định.

## 16. Kiểm thử file có dòng lỗi và skip

Nên tạo fixture nhỏ có header, dòng hợp lệ, dòng sai số cột, dòng sai kiểu dữ liệu và dòng hợp lệ phía sau. Test cần xác nhận cả dữ liệu output và metadata.

Ví dụ test theo Spring Batch Test:

~~~java
@SpringBatchTest
@SpringJUnitConfig(ImportJobTestConfiguration.class)
class FlatFileSkipTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void skipsMalformedRowsAndWritesValidCustomers() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("input.file", "src/test/resources/customers-with-errors.csv", true)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        StepExecution step = execution.getStepExecutions()
                .stream()
                .filter(s -> s.getStepName().equals("importCustomersStep"))
                .findFirst()
                .orElseThrow();

        assertEquals(2, step.getReadSkipCount());
        assertEquals(expectedCustomerIds, customerRepository.findAllIds());
    }
}
~~~

Đây là khung minh họa; số skip và output cần khớp fixture thực tế. JobRepository và database test phải được làm sạch giữa các test để JobInstance/metadata của lần chạy trước không ảnh hưởng kết quả.

Các trường hợp nên có:

1. Tất cả dòng hợp lệ: không có skip.
2. Một dòng sai số cột: readSkipCount tăng một.
3. Một dòng sai kiểu dữ liệu: parse exception được skip nếu đã cấu hình.
4. Một dòng parse được nhưng sai nghiệp vụ: processSkipCount tăng nếu exception được phép skip.
5. Dòng lỗi vượt skip limit: Step FAILED.
6. Exception không được khai báo skippable: Step FAILED.
7. File không tồn tại: reader open thất bại; không bị coi là một dòng skip.
8. Header sai: kiểm tra bằng skippedLinesCallback hoặc bước xác thực header, không tính vào skip count.
9. CSV có quoted newline: xác nhận record boundary và line number.
10. Restart sau khi đã commit một số chunk: checkpoint và output không bị thiếu/trùng.

## 17. Các lỗi thường gặp

**Skip mọi Exception:** lỗi mở file, lỗi I/O hoặc lỗi hạ tầng có thể bị che giấu. Chỉ skip loại exception gắn với record cụ thể.

**Cho rằng mọi dòng lỗi đều là FlatFileParseException:** lỗi nghiệp vụ trong processor có exception riêng; lỗi mở resource có thể là ItemStreamException hoặc lỗi I/O khác.

**Không bật fault tolerance:** chỉ khai báo listener không khiến reader tự skip dòng lỗi. Cần faultTolerant(), skip policy và skipLimit phù hợp.

**Đặt skip limit quá cao:** Job có thể hoàn tất với output thiếu phần lớn dữ liệu. Chọn ngưỡng theo yêu cầu nghiệp vụ và theo dõi skip rate.

**Nhầm header với skip:** linesToSkip và skippedLinesCallback là cơ chế xử lý dòng đầu file, không tiêu thụ skip limit.

**Không lưu line number và nguồn:** khó tìm lại dòng lỗi trong file lớn hoặc khi nhiều file được xử lý cùng Job.

**Log raw line chứa dữ liệu nhạy cảm:** có thể làm lộ thông tin cá nhân hoặc bí mật nghiệp vụ. Lưu ở quarantine có kiểm soát hoặc log metadata tối thiểu.

**Không kiểm thử fixed-width và multiline CSV:** parser có thể xử lý record boundary khác với giả định mỗi physical line là một item.

**Nhầm lỗi parse với lỗi resource:** file không mở được không có một item cụ thể để skip.

**Thay file trước khi restart:** checkpoint cũ có thể không còn khớp nội dung. Giữ file bất biến hoặc xác minh version/checksum.

**Không xử lý lại dòng lỗi:** skip giúp batch tiếp tục, nhưng dữ liệu bị bỏ qua vẫn cần audit, sửa và replay nếu nghiệp vụ yêu cầu đầy đủ.

## Kết luận

Để xử lý file có dòng lỗi trong Spring Batch, cấu hình FlatFileItemReader với tokenizer và mapper phù hợp, sau đó khai báo exception parse như FlatFileParseException là skippable trong fault-tolerant Step và đặt skipLimit có kiểm soát. SkipListener.onSkipInRead có thể lấy line number, raw input và cause từ exception để lưu dòng lỗi vào quarantine. Phân biệt rõ dòng dữ liệu sai với lỗi mở resource, header, comment và filter; những trường hợp này có cơ chế xử lý khác nhau. Giữ file nguồn ổn định, bật checkpoint khi cần restart, kiểm tra dữ liệu output cùng skip counters và có quy trình replay để các dòng bị bỏ qua không biến mất khỏi khả năng truy vết nghiệp vụ.
