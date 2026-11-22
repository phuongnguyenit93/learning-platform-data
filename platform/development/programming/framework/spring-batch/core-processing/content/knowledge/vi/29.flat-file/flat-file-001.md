# FlatFileItemReader

`FlatFileItemReader<T>` là reader của Spring Batch dùng để đọc dữ liệu từ một file văn bản theo từng record và chuyển mỗi record thành object Java. Nó thường được dùng cho CSV, file phân cách bằng dấu tab hoặc dấu chấm phẩy, và file fixed-width có các trường nằm ở vị trí cố định.

Reader chịu trách nhiệm quản lý resource, đọc record, xử lý header/comment, chuyển dòng qua `LineMapper` và lưu checkpoint để hỗ trợ restart. Việc kiểm tra quy tắc nghiệp vụ của từng bản ghi thường thuộc `ItemProcessor`; reader nên tập trung vào việc đọc và ánh xạ định dạng file một cách xác định.

## 1. Vị trí của FlatFileItemReader trong chunk processing

Trong chunk-oriented step, Spring Batch gọi reader nhiều lần để lấy item. Reader trả về một object cho mỗi lần đọc; khi hết dữ liệu, `read()` trả về `null`. Các item được đưa qua processor rồi chuyển thành chunk cho writer.

```text
Input file
    |
    v
FlatFileItemReader
    |
    +--> đọc logical record
    |
    +--> LineMapper
             |
             +--> LineTokenizer
             |       tách các field
             |
             +--> FieldSetMapper
                     ánh xạ field thành object
    |
    v
ItemProcessor
    |
    v
ItemWriter
    |
    v
Chunk transaction commit
```

`FlatFileItemReader` triển khai `ItemStreamReader`, nên ngoài `read()` nó còn tham gia lifecycle `open()`, `update()` và `close()`. Các callback này cho phép reader mở file, lưu trạng thái đọc vào `ExecutionContext` và giải phóng tài nguyên.

## 2. Cấu hình cơ bản trong Spring Batch 5

Reader thường được tạo bằng `FlatFileItemReaderBuilder`. Một cấu hình cơ bản cần tên reader, resource đầu vào và cách ánh xạ mỗi dòng.

```java
@Bean
@StepScope
FlatFileItemReader<Customer> customerReader(
        @Value("#{jobParameters['input.file']}") String inputFile,
        LineMapper<Customer> customerLineMapper) {

    return new FlatFileItemReaderBuilder<Customer>()
        .name("customerReader")
        .resource(new FileSystemResource(inputFile))
        .encoding(StandardCharsets.UTF_8.name())
        .linesToSkip(1)
        .skippedLinesCallback(line ->
            log.debug("Skipped header: {}", line))
        .lineMapper(customerLineMapper)
        .strict(true)
        .saveState(true)
        .build();
}
```

Trong ví dụ:

- `name` là định danh ổn định của reader, được dùng khi lưu state vào `ExecutionContext`.
- `resource` xác định file cần đọc.
- `encoding` chỉ rõ charset, tránh phụ thuộc encoding mặc định của máy chạy.
- `linesToSkip(1)` bỏ qua dòng đầu, thường là header.
- `skippedLinesCallback` nhận dòng bị bỏ qua ở phần đầu file để có thể ghi log hoặc kiểm tra header.
- `lineMapper` chuyển record thành `Customer`.
- `strict(true)` yêu cầu resource phải tồn tại; cấu hình strict nên được chọn có chủ đích.
- `saveState(true)` cho phép reader lưu trạng thái để restart.

`@StepScope` cho phép lấy `input.file` từ JobParameters tại thời điểm step chạy. Mỗi StepExecution có thể nhận file riêng mà không phải tạo singleton reader chứa đường dẫn mutable.

## 3. Resource đầu vào

`FlatFileItemReader` nhận một Spring `Resource`. Tùy cách triển khai, resource có thể là file trên filesystem, file trong classpath hoặc một resource được cung cấp bởi ứng dụng.

| Resource | Ví dụ | Khi phù hợp |
|---|---|---|
| `FileSystemResource` | `new FileSystemResource("/data/orders.csv")` | File trên máy hoặc volume được mount |
| `ClassPathResource` | `new ClassPathResource("samples/orders.csv")` | File mẫu hoặc dữ liệu đóng gói trong ứng dụng |
| `UrlResource` | `new UrlResource(uri)` | Nguồn URL có thể đọc như resource; cần cân nhắc network/restart |

Ví dụ dùng classpath resource:

```java
@Bean
FlatFileItemReader<Country> countryReader() {
    return new FlatFileItemReaderBuilder<Country>()
        .name("countryReader")
        .resource(new ClassPathResource("data/countries.csv"))
        .encoding(StandardCharsets.UTF_8.name())
        .linesToSkip(1)
        .lineMapper(countryLineMapper())
        .build();
}
```

Trong production, file đầu vào thường được truyền bằng JobParameters để cùng một job có thể xử lý nhiều file. Nên dùng định danh nguồn ổn định như file ID, batch ID hoặc checksum nếu nội dung file có thể bị thay thế tại cùng một đường dẫn.

## 4. LineMapper: chuyển một record thành object

`LineMapper<T>` nhận nội dung của một logical record và số dòng, sau đó trả về object kiểu `T`. `DefaultLineMapper<T>` kết hợp hai thành phần:

1. `LineTokenizer`: tách record thành các field.
2. `FieldSetMapper<T>`: ánh xạ tập field thành object Java.

```text
"C001","An Nguyen","an@example.test"
                  |
                  v
          DelimitedLineTokenizer
                  |
                  v
       FieldSet: customerId, name, email
                  |
                  v
          FieldSetMapper<Customer>
                  |
                  v
          Customer object
```

Ví dụ cấu hình `DefaultLineMapper`:

```java
@Bean
LineMapper<Customer> customerLineMapper() {
    DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
    tokenizer.setDelimiter(",");
    tokenizer.setQuoteCharacter('"');
    tokenizer.setNames("customerId", "name", "email");
    tokenizer.setStrict(true);

    DefaultLineMapper<Customer> mapper = new DefaultLineMapper<>();
    mapper.setLineTokenizer(tokenizer);
    mapper.setFieldSetMapper(fieldSet -> new Customer(
        fieldSet.readString("customerId"),
        fieldSet.readString("name"),
        fieldSet.readString("email")
    ));
    return mapper;
}
```

Ví dụ giả định `Customer` là record hoặc class có constructor tương ứng. `FieldSet` cung cấp các phương thức đọc giá trị theo tên hoặc vị trí, chẳng hạn `readString`, `readInt`, `readLong`, `readBigDecimal` và các phương thức chuyển đổi ngày giờ.

## 5. DelimitedLineTokenizer cho CSV và file phân cách

`DelimitedLineTokenizer` tách record theo delimiter. Delimiter phổ biến gồm dấu phẩy, dấu chấm phẩy, tab hoặc ký tự pipe.

```java
DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
tokenizer.setDelimiter(";");
tokenizer.setQuoteCharacter('"');
tokenizer.setNames("orderId", "customerId", "amount", "currency");
tokenizer.setStrict(true);
```

Với dòng:

```text
1001;C008;125000.50;VND
```

`FieldSet` có thể đọc các trường theo tên:

```java
FieldSetMapper<Order> orderMapper = fieldSet -> new Order(
    fieldSet.readLong("orderId"),
    fieldSet.readString("customerId"),
    fieldSet.readBigDecimal("amount"),
    fieldSet.readString("currency")
);
```

Tokenizer có thể xử lý giá trị được bao bởi quote theo cấu hình. Điều này quan trọng khi field chứa delimiter, ví dụ `"Nguyen, An"` trong CSV. Hãy kiểm tra quy tắc quote/escape của file nguồn; một file CSV tự chế có thể không tuân theo cùng dialect với tokenizer.

`strict(true)` yêu cầu số field khớp với số tên đã khai báo. Nếu file có số cột thay đổi, hãy quyết định rõ có cho phép field thiếu/thừa hay không; đừng tắt strict chỉ để che giấu dữ liệu sai định dạng.

## 6. FixedLengthTokenizer cho file fixed-width

Không phải file văn bản nào cũng phân tách bằng delimiter. Một số hệ thống xuất file có độ rộng cố định cho từng field. `FixedLengthTokenizer` dùng các `Range` để xác định vị trí ký tự của từng cột.

Ví dụ record có:

- Mã khách hàng ở ký tự 1–8.
- Tên ở ký tự 9–38.
- Số dư ở ký tự 39–50.

```java
FixedLengthTokenizer tokenizer = new FixedLengthTokenizer();
tokenizer.setColumns(
    new Range(1, 8),
    new Range(9, 38),
    new Range(39, 50)
);
tokenizer.setNames("customerId", "customerName", "balance");
tokenizer.setStrict(true);

DefaultLineMapper<CustomerBalance> mapper = new DefaultLineMapper<>();
mapper.setLineTokenizer(tokenizer);
mapper.setFieldSetMapper(fieldSet -> new CustomerBalance(
    fieldSet.readString("customerId").trim(),
    fieldSet.readString("customerName").trim(),
    fieldSet.readBigDecimal("balance")
));
```

`Range` dùng vị trí ký tự bắt đầu/kết thúc theo quy ước của Spring Batch. Hãy xác nhận độ rộng record và cách tính vị trí với đặc tả file nguồn; dữ liệu fixed-width có thể chứa khoảng trắng có ý nghĩa ở đầu hoặc cuối field.

## 7. FieldSetMapper và chuyển đổi kiểu dữ liệu

`FieldSetMapper<T>` chịu trách nhiệm chuyển các field đã tokenize thành object domain. Có thể dùng `BeanWrapperFieldSetMapper` khi class có constructor mặc định và setter phù hợp, hoặc viết mapper riêng để kiểm soát chuyển đổi.

Ví dụ mapper tường minh:

```java
FieldSetMapper<Invoice> invoiceMapper = fieldSet -> new Invoice(
    fieldSet.readString("invoiceNumber"),
    LocalDate.parse(fieldSet.readString("invoiceDate")),
    fieldSet.readBigDecimal("totalAmount")
);
```

Mapper riêng hữu ích khi file dùng format ngày, decimal separator hoặc mã enum đặc thù. Chẳng hạn, nếu nguồn dùng ngày `dd/MM/yyyy`, hãy parse bằng formatter rõ ràng thay vì dựa vào locale mặc định:

```java
DateTimeFormatter dateFormat = DateTimeFormatter.ofPattern("dd/MM/uuuu");

FieldSetMapper<Invoice> invoiceMapper = fieldSet -> new Invoice(
    fieldSet.readString("invoiceNumber"),
    LocalDate.parse(fieldSet.readString("invoiceDate"), dateFormat),
    fieldSet.readBigDecimal("totalAmount")
);
```

Không nên đưa quá nhiều quy tắc nghiệp vụ vào mapper. Mapper nên chuyển biểu diễn file thành kiểu Java; processor có thể kiểm tra quan hệ nghiệp vụ giữa các trường, tra cứu dữ liệu tham chiếu hoặc quyết định filter/transform.

## 8. Header và các dòng đầu file

Nhiều file có một hoặc nhiều dòng header trước dữ liệu. `linesToSkip(n)` cho phép reader bỏ qua số dòng vật lý đầu tiên.

```java
return new FlatFileItemReaderBuilder<Customer>()
    .name("customerReader")
    .resource(resource)
    .linesToSkip(2)
    .skippedLinesCallback(line -> log.debug("Header: {}", line))
    .lineMapper(customerLineMapper)
    .build();
```

`skippedLinesCallback` có thể dùng để xác nhận header đúng phiên bản hoặc ghi nhận thông tin nguồn. Nếu cần kiểm tra tên cột trong header, callback nên so sánh nội dung với schema mong đợi và ném lỗi nếu header không hợp lệ.

`linesToSkip` bỏ qua số dòng đầu cố định. Nếu file có header tùy biến, nhiều dòng metadata hoặc schema thay đổi theo phiên bản, hãy dùng callback hoặc một bước kiểm tra file riêng thay vì giả định mọi file đều có cùng số dòng.

## 9. Comments và dòng không phải dữ liệu

`FlatFileItemReader` có thể bỏ qua các dòng comment theo prefix được cấu hình. Điều này hữu ích khi file chứa dòng chú thích như `# generated at ...`.

```java
return new FlatFileItemReaderBuilder<OrderRow>()
    .name("orderReader")
    .resource(resource)
    .comments("#", "//")
    .lineMapper(orderLineMapper)
    .build();
```

Chỉ dùng comment prefix nếu định dạng file quy định những dòng bắt đầu bằng ký tự đó không phải dữ liệu. Nếu giá trị hợp lệ trong cột đầu có thể bắt đầu bằng `#`, cấu hình comment có thể làm mất record. Các dòng trống cũng cần được xử lý theo hợp đồng file; không nên mặc định coi mọi dòng trống là comment hoặc item hợp lệ.

## 10. Encoding và ký tự đặc biệt

Encoding xác định cách byte trong file được chuyển thành ký tự. Nếu không chỉ rõ, ứng dụng có thể phụ thuộc charset mặc định của JVM hoặc cấu hình môi trường, dẫn đến lỗi tiếng Việt, ký tự có dấu hoặc dữ liệu đa ngôn ngữ.

Với file UTF-8, nên cấu hình rõ:

```java
.encoding(StandardCharsets.UTF_8.name())
```

Nếu nguồn sử dụng UTF-16 hoặc một code page cũ, phải chọn đúng charset theo hợp đồng nguồn. Encoding sai có thể tạo ký tự lỗi, làm sai delimiter hoặc khiến mapping thất bại.

Cũng cần xác định file có UTF-8 BOM hay không. BOM ở đầu file có thể xuất hiện như một ký tự trong field đầu tiên tùy cách đọc và xử lý. Nếu nguồn có BOM, hãy chuẩn hóa ở bước đọc/tiền xử lý có kiểm soát và kiểm thử với file thực tế.

## 11. Multi-line record và RecordSeparatorPolicy

Một logical record không phải lúc nào cũng tương ứng với một dòng vật lý. CSV có thể cho phép field được quote chứa ký tự xuống dòng. Khi đó reader cần biết khi nào record kết thúc.

`RecordSeparatorPolicy` quyết định cách ghép các dòng vật lý thành logical record. Spring Batch cung cấp policy mặc định và cho phép cấu hình policy riêng nếu định dạng file có quy tắc đặc biệt.

```java
return new FlatFileItemReaderBuilder<CustomerNote>()
    .name("customerNoteReader")
    .resource(resource)
    .recordSeparatorPolicy(new DefaultRecordSeparatorPolicy())
    .lineMapper(customerNoteLineMapper)
    .build();
```

Tokenizer phải tương thích với quy tắc record separator. Với file có quote mở ở cuối dòng và đóng ở dòng sau, hãy kiểm thử record nhiều dòng để chắc chắn tokenizer nhận được một logical record hoàn chỉnh.

Nếu nguồn dùng continuation marker hoặc record có cấu trúc đặc biệt, có thể cần `RecordSeparatorPolicy` tùy chỉnh. Không nên tự nối các dòng trong processor vì tại thời điểm processor chạy, reader cần đã tạo đúng một item đại diện cho record.

## 12. Xử lý lỗi parse và dữ liệu sai định dạng

Khi `LineMapper` hoặc tokenizer không thể ánh xạ record, reader có thể ném `FlatFileParseException`. Exception này cung cấp thông tin hữu ích như số dòng và nội dung record gây lỗi.

Trong fault-tolerant step, có thể cấu hình skip cho lỗi parse nếu nghiệp vụ cho phép:

```java
return new StepBuilder("importCustomers", jobRepository)
    .<Customer, Customer>chunk(100, transactionManager)
    .reader(customerReader)
    .writer(customerWriter)
    .faultTolerant()
    .skip(FlatFileParseException.class)
    .skipLimit(100)
    .listener(customerSkipListener)
    .build();
```

Chỉ skip lỗi parse khi item lỗi có thể được loại bỏ mà không phá vỡ yêu cầu nghiệp vụ. Nếu header sai, encoding sai hoặc toàn bộ file dùng schema không tương thích, việc skip từng dòng có thể che giấu lỗi nguồn; nên fail sớm.

Đối với lỗi dữ liệu có cấu trúc nhưng cần ghi reject record, dùng `SkipListener` để ghi nhận item hoặc exception thực sự bị skip. `onSkipInRead` không có item Java vì reader chưa tạo được object; có thể lấy line number và input từ `FlatFileParseException` để lưu thông tin điều tra.

## 13. Strict mode và resource không tồn tại

Builder hỗ trợ `strict(boolean)` để quyết định cách xử lý khi resource không tồn tại. Với strict mode bật, thiếu file được coi là lỗi cấu hình/đầu vào và reader không âm thầm coi nguồn là rỗng.

```java
.resource(new FileSystemResource(inputFile))
.strict(true)
```

Đặt `strict(false)` chỉ khi thiếu resource là tình huống hợp lệ theo nghiệp vụ và job được thiết kế để xử lý nguồn rỗng. Ví dụ, một partition có thể không có file tương ứng. Tuy nhiên, nếu file bắt buộc phải được cung cấp, tắt strict sẽ làm lỗi vận hành khó phát hiện.

Không dùng `strict(false)` để né kiểm tra file. Nên xác thực JobParameters, resource path và quyền truy cập trước khi bắt đầu xử lý.

## 14. Restart và ExecutionContext

`FlatFileItemReader` có thể lưu vị trí đọc vào `ExecutionContext` để step tiếp tục sau khi job thất bại. Khi một chunk commit, Spring Batch gọi lifecycle `update()` để reader lưu trạng thái hiện tại. Khi restart, reader khôi phục state trong `open()` và tiếp tục từ vị trí phù hợp.

```text
Execution lần đầu
  đọc record 1..100
  ghi chunk và COMMIT
  reader checkpoint được lưu
  đọc record 101..200
  lỗi trước commit

Restart cùng JobInstance
  reader mở lại file
  khôi phục checkpoint đã commit
  tiếp tục từ record chưa được commit
```

Để restart hoạt động đúng:

- Đặt `.name("customerReader")` ổn định và duy nhất trong step.
- Giữ `.saveState(true)` (mặc định của builder thường bật state; nên cấu hình rõ khi restart là yêu cầu).
- Dùng cùng file đầu vào và cùng identifying JobParameters khi restart cùng JobInstance.
- Không thay nội dung file tại cùng đường dẫn giữa lần chạy và restart.
- Đảm bảo `ExecutionContext` và JobRepository được lưu bền vững.

Nếu file có thể bị thay thế, hãy dùng file ID/checksum/version làm identifying parameter và lưu snapshot hoặc copy bất biến để restart đọc đúng dữ liệu ban đầu.

## 15. Name và saveState

`name` không chỉ là nhãn hiển thị. Reader dùng tên để tạo key lưu state trong `ExecutionContext`. Khi có nhiều reader trong một step, mỗi reader cần tên khác nhau để tránh ghi đè checkpoint.

```java
new FlatFileItemReaderBuilder<OrderRow>()
    .name("ordersInputReader")
    .resource(resource)
    .lineMapper(orderLineMapper)
    .saveState(true)
    .build();
```

Nếu `saveState(false)`, reader không lưu checkpoint. Điều đó có thể phù hợp với một nguồn có thể đọc lại từ đầu hoặc step không cần restart, nhưng restart có thể đọc lại dữ liệu từ đầu hoặc không thể khôi phục tiến độ như mong đợi.

Không tắt state chỉ để xử lý lỗi key trùng. Hãy đặt tên reader ổn định và duy nhất. Nếu dùng reader trong môi trường chạy song song, cần nhớ rằng checkpoint của reader và thread safety là hai vấn đề riêng.

## 16. Reader không thread-safe

`FlatFileItemReader` giữ state nội bộ như reader đang mở, vị trí đọc và line count. Nó không được thiết kế để nhiều thread cùng gọi `read()` trên một instance mà không có đồng bộ phù hợp.

Không chia sẻ một singleton `FlatFileItemReader` cho nhiều worker hoặc nhiều JobExecution. Khi dùng partitioning, hãy khai báo reader với `@StepScope` để mỗi worker StepExecution nhận target reader riêng và phạm vi file/record riêng.

```java
@Bean
@StepScope
FlatFileItemReader<OrderRow> partitionReader(
        @Value("#{stepExecutionContext['file']}") String file) {
    return new FlatFileItemReaderBuilder<OrderRow>()
        .name("partitionOrderReader")
        .resource(new FileSystemResource(file))
        .lineMapper(orderLineMapper())
        .saveState(true)
        .build();
}
```

Với một step cần đọc nhiều file tuần tự, cân nhắc `MultiResourceItemReader`. Với workload cần xử lý song song, partition theo file hoặc theo range dữ liệu để mỗi worker có reader riêng. Không coi `@StepScope` là bảo đảm thread safety nếu nhiều thread vẫn dùng chung một StepExecution và cùng target.

## 17. FlatFileItemReader và MultiResourceItemReader

`FlatFileItemReader` đọc một resource. Nếu đầu vào là một tập nhiều file, `MultiResourceItemReader` có thể điều phối qua danh sách resource và dùng delegate `FlatFileItemReader` để đọc từng file.

```java
@Bean
@StepScope
MultiResourceItemReader<OrderRow> orderFilesReader(
        @Value("#{jobParameters['input.directory']}") String directory,
        FlatFileItemReader<OrderRow> orderFileReader) {

    Resource[] resources = new PathMatchingResourcePatternResolver()
        .getResources("file:" + directory + "/*.csv");
    Arrays.sort(resources, Comparator.comparing(Resource::getFilename));

    return new MultiResourceItemReaderBuilder<OrderRow>()
        .name("orderFilesReader")
        .resources(resources)
        .delegate(orderFileReader)
        .saveState(true)
        .build();
}
```

Ví dụ minh họa ý tưởng; trong cấu hình thực tế, cần bảo đảm delegate reader có scope/lifecycle phù hợp với wrapper và không tạo một delegate target dùng chung sai cách giữa executions. Danh sách resource nên được sắp xếp ổn định để restart tiếp tục đúng file.

`MultiResourceItemReader` quản lý chuyển file; mỗi file vẫn được đọc bằng delegate. Nếu chỉ có một file, dùng trực tiếp `FlatFileItemReader` đơn giản hơn.

## 18. Kiểm tra header và schema file

`linesToSkip` chỉ bỏ qua header; nó không tự xác nhận header đúng. Nếu nhà cung cấp có thể thay đổi tên hoặc thứ tự cột, nên kiểm tra header trước khi đọc dữ liệu.

Ví dụ callback xác nhận header:

```java
.linesToSkip(1)
.skippedLinesCallback(header -> {
    String expected = "customerId,name,email";
    if (!expected.equals(header)) {
        throw new IllegalStateException("Unexpected input header");
    }
})
```

Nếu file có BOM, quote hoặc khoảng trắng chuẩn hóa, phép so sánh header cần xử lý các đặc điểm đó trước khi đối chiếu. Với schema phức tạp hoặc nhiều phiên bản, có thể tạo một bước kiểm tra file riêng để xác định version và cấu hình mapper tương ứng.

## 19. Kiểm thử FlatFileItemReader

Reader nên được kiểm thử với file mẫu đại diện cho cả dữ liệu hợp lệ và các trường hợp biên. Kiểm thử không chỉ xác nhận số item mà còn cần xác nhận mapping và vị trí restart.

Các trường hợp hữu ích:

1. File CSV bình thường: mỗi record được ánh xạ đúng field và kiểu dữ liệu.
2. Header: số dòng được bỏ qua đúng và callback nhận nội dung mong đợi.
3. Comment: các dòng có prefix được cấu hình không trở thành item.
4. Field chứa delimiter trong quote: giá trị được giữ nguyên.
5. File fixed-width: range và field mapping đúng vị trí.
6. Encoding: tiếng Việt, ký tự có dấu và ký tự ngoài ASCII được đọc đúng.
7. Record nhiều dòng: record separator ghép đúng logical record.
8. Dữ liệu sai định dạng: exception chứa line number/input đủ để điều tra.
9. Resource thiếu: strict mode cho kết quả đúng với yêu cầu.
10. Restart: sau một chunk commit, reader tiếp tục từ checkpoint phù hợp.
11. File nguồn bị thay đổi: job phát hiện hoặc quy trình bảo đảm snapshot không bị thay đổi.
12. Chạy song song: mỗi worker có reader target và phạm vi dữ liệu riêng.

Với kiểm thử restart, dùng JobRepository và transaction manager tương thích để xác nhận checkpoint được lưu tại commit boundary. Chỉ gọi `read()` lặp nhiều lần trong unit test không chứng minh restart metadata hoạt động.

## 20. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Không đặt `name` ổn định | Checkpoint khó được lưu/khôi phục đúng | Đặt tên reader duy nhất trong step |
| Dùng encoding mặc định | Ký tự tiếng Việt hoặc dữ liệu đa ngôn ngữ bị lỗi | Chỉ rõ charset theo hợp đồng file |
| Coi `linesToSkip` là kiểm tra header | File sai schema vẫn được đọc | Dùng callback hoặc bước validation header |
| Dùng tokenizer sai delimiter hoặc range | Field bị lệch, dữ liệu mapping sai | Xác định dialect/độ rộng file và kiểm thử |
| Tắt strict cho file bắt buộc | Thiếu file có thể bị hiểu nhầm là nguồn rỗng | Giữ strict và validate resource |
| Skip mọi lỗi parse | File sai schema có thể bị bỏ qua quá nhiều dòng | Chỉ skip lỗi record có thể loại bỏ |
| Chia sẻ reader stateful giữa nhiều thread | Cursor/line count có thể bị sai | Dùng reader riêng theo StepExecution hoặc partition |
| Thay file trước khi restart | Checkpoint cũ áp dụng trên nội dung mới | Dùng input bất biến, checksum/version |
| Tắt saveState nhưng vẫn kỳ vọng restart | Reader không khôi phục checkpoint | Bật state và dùng ExecutionContext bền vững |
| Dùng reader một file cho nhiều resource | Không điều phối chuyển file đúng | Dùng `MultiResourceItemReader` khi cần |

## 21. Quy trình thiết kế reader cho production

Khi xây dựng step đọc file, hãy xác định:

1. File là CSV/delimited, fixed-width hay record có cấu trúc nhiều dòng?
2. Charset, delimiter, quote, escape, comment prefix và header theo hợp đồng nào?
3. Resource có bắt buộc phải tồn tại không?
4. Mỗi record ánh xạ thành kiểu Java nào và lỗi parse nào có thể skip?
5. Reader có cần `@StepScope` để nhận JobParameters hoặc partition context không?
6. Reader có lưu state và có tên ổn định để restart không?
7. File nguồn có bất biến trong suốt lần chạy và restart không?
8. Workload có chạy song song không; mỗi worker có reader riêng không?
9. Skip/reject có audit đủ thông tin mà không làm lộ payload nhạy cảm không?
10. Integration test có xác nhận header, encoding, parse lỗi và restart trên JobRepository thật không?

## Kết luận

`FlatFileItemReader<T>` đọc một resource văn bản theo logical record và chuyển từng record thành object Java. `LineMapper` kết hợp `LineTokenizer` với `FieldSetMapper` để tách field và ánh xạ dữ liệu; `linesToSkip`, comment prefix, encoding và record separator điều khiển cách reader diễn giải file.

Hãy khai báo resource và encoding rõ ràng, dùng `@StepScope` khi cần late binding, đặt tên reader ổn định và bật `saveState` khi cần restart. Kiểm tra header/schema thay vì chỉ bỏ qua header, phân loại lỗi parse cẩn thận và không chia sẻ một reader stateful giữa nhiều thread. Với nhiều file, dùng `MultiResourceItemReader`; với dữ liệu nghiệp vụ, để processor đảm nhiệm validation và transformation.
