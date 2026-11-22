# MultiResourceItemReader

Trong Spring Batch, `MultiResourceItemReader<T>` dùng để đọc dữ liệu từ nhiều resource theo cùng một hợp đồng item. Thay vì tạo một step cho từng file, reader quản lý một danh sách file, lần lượt chuyển từng file cho một reader delegate và trả item như thể chúng đến từ một luồng dữ liệu duy nhất.

Ví dụ, mỗi ngày hệ thống nhận được nhiều file `customers-*.csv`. Tất cả file có cùng cấu trúc cột và cần được import theo một job. `MultiResourceItemReader` có thể duyệt danh sách resource, dùng cùng một `FlatFileItemReader` để đọc từng file, rồi chuyển các item liên tục tới processor và writer của step.

Điểm quan trọng là reader phải giữ thứ tự resource ổn định và quản lý đúng lifecycle của delegate. Khi job restart, Spring Batch cần biết đang ở file nào và delegate đã đọc đến đâu trong file đó. Nếu danh sách file thay đổi hoặc nội dung file bị thay thế, checkpoint có thể trỏ đến dữ liệu khác với lần chạy ban đầu.

## 1. MultiResourceItemReader giải quyết vấn đề gì?

Giả sử input được chia thành nhiều file:

```text
input/
  customers-001.csv
  customers-002.csv
  customers-003.csv
```

Mỗi file chứa một phần dữ liệu customer và có cùng định dạng:

```text
customer_id,name,email
C001,Nguyen An,an@example.com
C002,Tran Binh,binh@example.com
```

Nếu không dùng multi-resource reader, ứng dụng có thể phải tự mở từng file, tạo reader riêng và điều phối việc chuyển file. Điều đó làm tăng code quản lý resource, checkpoint và lỗi khi file kết thúc.

`MultiResourceItemReader` thực hiện việc điều phối này:

```text
              Resource[]
                  |
                  v
        MultiResourceItemReader
                  |
          +-------+-------+
          |               |
          v               v
     Resource 1       Delegate reader
          |               |
          +--------------> đọc items
                          |
                    EOF của file 1
                          |
                          v
                    Resource 2
                          |
                          v
                    Delegate reader
                          |
                         ...
                          |
                          v
                 EOF của mọi resource
                          |
                          v
                    return null
```

Với step phía sau, item từ file thứ nhất và file thứ hai đều được đọc qua cùng một `ItemReader<T>`. Processor và writer không cần biết item đến từ resource nào, trừ khi ứng dụng cần giữ lại thông tin nguồn để audit.

## 2. Các thành phần chính

`MultiResourceItemReader<T>` phối hợp một danh sách `Resource` với một delegate có khả năng đọc từng resource.

| Thành phần | Vai trò |
|---|---|
| `Resource[]` | Danh sách file hoặc resource cần đọc. |
| `MultiResourceItemReader<T>` | Điều phối thứ tự resource và chuyển từ resource này sang resource kế tiếp. |
| Delegate reader | Đọc item từ resource hiện tại, ví dụ `FlatFileItemReader<T>`. |
| `ResourceAwareItemReaderItemStream<T>` | Contract cho delegate nhận resource qua `setResource(...)` và hỗ trợ lifecycle stream. |
| `ExecutionContext` | Lưu vị trí resource hiện tại và trạng thái đọc của delegate để restart. |

Delegate thường là `FlatFileItemReader`, nhưng có thể là reader khác miễn đáp ứng contract resource-aware phù hợp. Ví dụ, một reader XML hoặc reader custom có thể được dùng nếu nó có thể mở resource được giao và lưu trạng thái cần thiết.

`MultiResourceItemReader` không tự phân tích CSV, XML hoặc JSON. Nó chỉ điều phối danh sách resource; việc parse record thuộc delegate.

## 3. Cấu hình bằng MultiResourceItemReaderBuilder

Builder giúp khai báo reader rõ ràng:

```java
@Bean
MultiResourceItemReader<Customer> customerMultiReader(
        Resource[] customerResources,
        FlatFileItemReader<Customer> customerFileDelegate) {

    return new MultiResourceItemReaderBuilder<Customer>()
            .name("customerMultiReader")
            .resources(customerResources)
            .delegate(customerFileDelegate)
            .saveState(true)
            .strict(true)
            .build();
}
```

Các cấu hình quan trọng:

- `name(...)`: tên ổn định của multi-resource reader, được dùng để tạo key trong `ExecutionContext`.
- `resources(...)`: danh sách resource cần đọc.
- `delegate(...)`: reader thực hiện đọc một resource tại một thời điểm.
- `saveState(true)`: lưu state của reader để hỗ trợ restart.
- `strict(true)`: báo lỗi khi không tìm thấy resource nào theo cấu hình strict.

API builder có thể khác đôi chút giữa các phiên bản Spring Batch. Với các phiên bản cung cấp `MultiResourceItemReaderBuilder`, hãy dùng builder của đúng dependency version đang chạy.

## 4. Cấu hình delegate FlatFileItemReader

Delegate cần biết cách parse một file. Nó không cần biết danh sách tất cả file vì `MultiResourceItemReader` sẽ cung cấp resource hiện tại.

```java
@Bean
FlatFileItemReader<Customer> customerFileDelegate(
        LineMapper<Customer> customerLineMapper) {

    return new FlatFileItemReaderBuilder<Customer>()
            .name("customerFileDelegate")
            .lineMapper(customerLineMapper)
            .linesToSkip(1)
            .saveState(true)
            .build();
}
```

Delegate không khai báo `.resource(...)` trong ví dụ này vì resource được đặt động qua `setResource(...)` khi multi-resource reader chuyển sang file tiếp theo. Delegate vẫn cần tên ổn định và state riêng để có thể khôi phục vị trí đọc trong resource hiện tại.

Nếu mỗi file đều có một dòng header giống nhau, `linesToSkip(1)` được áp dụng mỗi lần delegate được mở cho một resource. Nếu chỉ file đầu tiên có header còn các file sau không có, cần một chiến lược khác để xử lý header theo resource; không thể mặc định dùng một cấu hình `linesToSkip` duy nhất cho cả hai định dạng.

## 5. Tạo danh sách Resource từ file pattern

Spring `ResourcePatternResolver` có thể tìm các file theo wildcard:

```java
@Bean
Resource[] customerResources(
        ResourcePatternResolver resourcePatternResolver) throws IOException {

    return resourcePatternResolver.getResources(
            "file:./input/customers-*.csv");
}
```

Pattern `file:./input/customers-*.csv` tìm các file phù hợp trong thư mục input theo working directory của ứng dụng. Có thể dùng `classpath*:` khi resource nằm trong classpath, nhưng với file đầu vào thay đổi theo từng batch, filesystem hoặc object storage thường phù hợp hơn.

Nếu đường dẫn đến từ JobParameters, có thể tạo danh sách resource khi step bắt đầu:

```java
@Bean
@StepScope
MultiResourceItemReader<Customer> customerMultiReader(
        @Value("#{jobParameters['inputPattern']}") String inputPattern,
        ResourcePatternResolver resolver,
        FlatFileItemReader<Customer> customerFileDelegate) throws IOException {

    Resource[] resources = resolver.getResources(inputPattern);

    return new MultiResourceItemReaderBuilder<Customer>()
            .name("customerMultiReader")
            .resources(resources)
            .delegate(customerFileDelegate)
            .saveState(true)
            .strict(true)
            .build();
}
```

`@StepScope` cho phép lấy pattern từ JobParameters. Cần validate pattern và giới hạn thư mục mà ứng dụng được phép đọc. Không nhận một pattern tùy ý từ nguồn không tin cậy rồi cho phép nó truy cập mọi đường dẫn trên máy chủ.

## 6. Resource order phải xác định

Thứ tự đọc file có thể ảnh hưởng kết quả nếu dữ liệu có thứ tự nghiệp vụ, nếu cùng một entity xuất hiện ở nhiều file hoặc nếu restart cần quay lại đúng resource.

Không nên dựa vào thứ tự ngẫu nhiên do filesystem hoặc resource resolver trả về. Hãy sắp xếp rõ ràng bằng comparator:

```java
Comparator<Resource> resourceComparator = Comparator.comparing(
        resource -> resource.getFilename() == null
                ? ""
                : resource.getFilename());

return new MultiResourceItemReaderBuilder<Customer>()
        .name("customerMultiReader")
        .resources(resources)
        .delegate(customerFileDelegate)
        .comparator(resourceComparator)
        .saveState(true)
        .build();
```

Comparator theo tên file có thể phù hợp nếu tên file có số thứ tự được padding:

```text
customers-0001.csv
customers-0002.csv
customers-0010.csv
```

Nếu tên file là `customers-1.csv`, `customers-2.csv`, `customers-10.csv`, thứ tự từ điển có thể đặt `10` trước `2`. Khi thứ tự số là yêu cầu, hãy parse sequence trong tên file hoặc dùng naming convention có zero padding.

Ví dụ comparator theo ngày hoặc sequence cần xử lý tên file không đúng format bằng lỗi rõ ràng. Không nên âm thầm xếp file không parse được vào một vị trí tùy ý.

## 7. Ví dụ comparator theo sequence

Giả sử tên file theo format `customers-<number>.csv`:

```java
private int sequenceOf(Resource resource) {
    String filename = Objects.requireNonNull(resource.getFilename());
    Matcher matcher = Pattern.compile("customers-(\\d+)\\.csv")
            .matcher(filename);

    if (!matcher.matches()) {
        throw new IllegalArgumentException(
                "Unexpected customer file name: " + filename);
    }

    return Integer.parseInt(matcher.group(1));
}

Comparator<Resource> bySequence = Comparator.comparingInt(this::sequenceOf);
```

Sau đó truyền `bySequence` vào `.comparator(bySequence)`. Comparator phải cho kết quả nhất quán giữa lần chạy đầu và lần restart. Nếu file được đổi tên hoặc sequence thay đổi, danh sách resource có thể bị sắp xếp khác và checkpoint không còn trỏ đến cùng file logic.

## 8. Resource không tồn tại và strict mode

`strict` của `MultiResourceItemReader` kiểm soát hành vi khi danh sách resource rỗng. Khi strict bật, reader báo lỗi nếu không có resource để đọc. Khi strict tắt, reader có thể kết thúc mà không có item nếu danh sách resource rỗng.

Ví dụ:

```java
return new MultiResourceItemReaderBuilder<Customer>()
        .name("customerMultiReader")
        .resources(resources)
        .delegate(customerFileDelegate)
        .strict(true)
        .build();
```

Nên dùng strict mode khi job được khởi chạy với giả định phải có file đầu vào. Nếu không có file, đó có thể là lỗi upstream hoặc scheduler chạy sai thời điểm.

Nếu không có file là trường hợp hợp lệ, có thể đặt `strict(false)` và bổ sung logic nghiệp vụ để phân biệt “không có file” với “file có nhưng không có record”. Cả hai trường hợp đều có thể tạo `readCount == 0`, nhưng nguyên nhân và cách báo cáo có thể khác nhau.

Đừng nhầm strict của multi-resource reader với strict của `FlatFileItemReader`. Một cái kiểm tra danh sách resource; cái còn lại kiểm tra resource được delegate mở. Cũng cần phân biệt lỗi không có file với lỗi file tồn tại nhưng không đọc được do permission hoặc I/O.

## 9. Delegate được mở lại cho từng resource

Khi chuyển sang resource tiếp theo, multi-resource reader giao resource mới cho delegate và quản lý lifecycle đọc resource đó. Delegate vì thế phải được thiết kế để mở, đọc, đóng và mở lại nhiều lần trong cùng một step execution.

Với `FlatFileItemReader`, mỗi lần mở resource mới:

- Resource hiện tại được thay bằng file tiếp theo.
- Header được bỏ qua theo cấu hình delegate nếu mỗi file có header.
- Line number và state của file mới bắt đầu theo resource đó.
- Khi delegate đạt EOF, multi-resource reader chuyển sang resource kế tiếp.

Không nên cấu hình delegate giữ state toàn cục không liên quan tới resource hiện tại, chẳng hạn một bộ đếm record không reset khi mở file mới, trừ khi đó là hành vi có chủ đích. Nếu cần tổng số record toàn batch, hãy dùng counter ở step/listener thay vì nhúng vào state nội bộ của delegate.

## 10. Đọc nhiều CSV file với cùng cấu trúc

Ví dụ cấu hình đầy đủ hơn:

```java
@Bean
LineMapper<Customer> customerLineMapper() {
    DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
    tokenizer.setDelimiter(",");
    tokenizer.setNames("customerId", "name", "email");

    DefaultLineMapper<Customer> mapper = new DefaultLineMapper<>();
    mapper.setLineTokenizer(tokenizer);
    mapper.setFieldSetMapper(fields -> new Customer(
            fields.readString("customerId"),
            fields.readString("name"),
            fields.readString("email")));
    return mapper;
}

@Bean
FlatFileItemReader<Customer> customerFileDelegate(
        LineMapper<Customer> customerLineMapper) {
    return new FlatFileItemReaderBuilder<Customer>()
            .name("customerFileDelegate")
            .encoding("UTF-8")
            .linesToSkip(1)
            .lineMapper(customerLineMapper)
            .saveState(true)
            .build();
}

@Bean
MultiResourceItemReader<Customer> customerMultiReader(
        ResourcePatternResolver resolver,
        FlatFileItemReader<Customer> customerFileDelegate) throws IOException {

    Resource[] resources = resolver.getResources("file:./input/customers-*.csv");

    return new MultiResourceItemReaderBuilder<Customer>()
            .name("customerMultiReader")
            .resources(resources)
            .delegate(customerFileDelegate)
            .comparator(Comparator.comparing(Resource::getFilename))
            .strict(true)
            .saveState(true)
            .build();
}
```

Ví dụ giả định mọi file có cùng delimiter, column order, encoding và header. Nếu một file có cấu trúc khác, không nên đưa nó vào cùng delegate chỉ vì tên file khớp wildcard. Hãy tách resource pattern hoặc tạo reader/step riêng theo định dạng.

## 11. Tích hợp MultiResourceItemReader vào chunk step

Sau khi có multi-resource reader, step sử dụng nó như một `ItemReader` thông thường:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        MultiResourceItemReader<Customer> customerMultiReader,
        ItemProcessor<Customer, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<Customer, Customer>chunk(500, transactionManager)
            .reader(customerMultiReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
```

Chunk có thể bắt đầu ở cuối một file và tiếp tục ở đầu file kế tiếp. Ví dụ file thứ nhất còn 100 item nhưng chunk size là 500; chunk có thể chứa 100 item cuối của file thứ nhất cùng 400 item đầu của file thứ hai.

Processor và writer không cần biết ranh giới file. Nếu nghiệp vụ cần source file name cho từng item, hãy đưa metadata đó vào item hoặc tạo wrapper chứa cả payload và nguồn.

## 12. Giữ lại tên file nguồn trong item

`MultiResourceItemReader` trả về item do delegate tạo. Nếu cần audit record thuộc file nào, có thể dùng một wrapper hoặc field nguồn trong model.

Ví dụ:

```java
public record ImportedCustomer(
        Customer customer,
        String sourceFile) {
}
```

Một cách triển khai là dùng custom delegate/mapper nhận biết resource hiện tại và thêm tên file vào item. Với `FlatFileItemReader`, có thể dùng `ResourceAware` ở mapper hoặc một component được cấu hình resource-aware, nhưng cần bảo đảm resource được cập nhật mỗi khi delegate chuyển file.

Ví dụ một mapper resource-aware minh họa:

```java
public class CustomerLineMapper
        implements LineMapper<ImportedCustomer>, ResourceAware {

    private Resource resource;

    @Override
    public void setResource(Resource resource) {
        this.resource = resource;
    }

    @Override
    public ImportedCustomer mapLine(String line, int lineNumber) throws Exception {
        String[] fields = line.split(",", -1);
        Customer customer = new Customer(fields[0], fields[1], fields[2]);
        return new ImportedCustomer(customer, resource.getFilename());
    }
}
```

Ví dụ cần được điều chỉnh theo cách cấu hình cụ thể để mapper nhận resource từ delegate. Nếu không thể đảm bảo mapper được cập nhật mỗi lần đổi resource, hãy viết delegate resource-aware hoặc dùng `ResourceAware` ở thành phần được framework gọi trực tiếp.

Một cách khác là log source file khi bắt đầu mỗi resource hoặc ghi batch manifest riêng. Không nên suy ra tên file từ item ID nếu không có quy tắc nghiệp vụ bảo đảm.

## 13. File có header và header khác nhau

Nếu mọi file có một header giống nhau, delegate có thể dùng:

```java
.linesToSkip(1)
```

Do delegate được mở lại cho từng resource, dòng đầu tiên của mỗi file được bỏ qua.

Nếu chỉ file đầu tiên có header hoặc header khác nhau giữa file, cần xử lý theo resource. Một số lựa chọn:

- Dùng `skippedLinesCallback` để kiểm tra header của từng file.
- Tạo delegate custom đọc header và xác thực trước khi parse record.
- Chia file theo loại header và dùng reader/step riêng.
- Dùng một step chuẩn hóa các file về cùng schema trước khi import.

Ví dụ callback:

```java
reader.setSkippedLinesCallback(header -> {
    if (!header.equals("customer_id,name,email")) {
        throw new IllegalStateException("Unexpected CSV header: " + header);
    }
});
```

Callback cần được cấu hình trên `FlatFileItemReader` delegate. Nếu header không hợp lệ, step nên thất bại hoặc đưa file vào rejected path theo quy trình. Không nên bỏ qua header bất kỳ mà không xác minh vì các cột có thể bị đảo thứ tự.

## 14. Resource ordering và dữ liệu phụ thuộc thứ tự

Nếu file chứa các phần dữ liệu có quan hệ thứ tự, ví dụ file delta được tạo theo sequence, cần đảm bảo comparator phản ánh thứ tự nghiệp vụ.

Ví dụ:

```text
delta-0001.csv  -> tạo customer
delta-0002.csv  -> cập nhật customer
delta-0003.csv  -> hủy customer
```

Đọc sai thứ tự có thể khiến trạng thái cuối cùng không đúng. Comparator nên được kiểm thử bằng một tập tên file đại diện, gồm số một chữ số, nhiều chữ số, ngày và file có tên không hợp lệ.

Nếu không có quan hệ thứ tự, vẫn nên dùng thứ tự xác định để restart, log và audit có thể tái lập. Thứ tự không nhất thiết phải là thứ tự thời gian; nó cần nhất quán với quy tắc dữ liệu.

## 15. Restart và checkpoint của MultiResourceItemReader

`MultiResourceItemReader` là một `ItemStreamReader`. Khi `saveState(true)`, nó lưu thông tin cần thiết để tiếp tục ở resource hiện tại. Delegate cũng cần hỗ trợ `ItemStream` và lưu state nếu muốn khôi phục vị trí trong file.

Ví dụ:

```text
Resources theo thứ tự:
  0: customers-001.csv
  1: customers-002.csv
  2: customers-003.csv

Lần chạy đầu:
  file 0 -> đọc hết
  file 1 -> đọc đến record 350
  chunk commit
  file 1 -> lỗi ở chunk tiếp theo

Restart:
  khôi phục resource index = 1
  delegate mở customers-002.csv
  khôi phục vị trí đọc phù hợp
  tiếp tục phần chưa commit
```

Để restart hoạt động đúng:

- `MultiResourceItemReader` có tên ổn định.
- Delegate có tên ổn định và `saveState(true)`.
- Cùng một danh sách resource được tạo ra với cùng thứ tự.
- Các file không bị đổi tên, xóa hoặc thay nội dung giữa các lần chạy.
- JobParameters identifying trỏ đến cùng JobInstance.
- Không có execution khác đang xử lý cùng JobInstance.

Nếu `saveState(false)` được dùng, reader không lưu checkpoint mặc định; restart có thể đọc lại từ đầu hoặc cần một cơ chế tự quản lý khác. Chỉ tắt save state khi job không cần restart hoặc ứng dụng đã có giải pháp thay thế được kiểm thử.

## 16. Vì sao resource list phải bất biến khi restart?

Checkpoint của multi-resource reader phụ thuộc vị trí trong danh sách resource. Giả sử lần chạy đầu có:

```text
index 0 -> A.csv
index 1 -> B.csv
index 2 -> C.csv
```

Sau khi lỗi, nếu file A bị xóa và danh sách mới thành:

```text
index 0 -> B.csv
index 1 -> C.csv
```

checkpoint `index 1` trước đó từng chỉ tới B nhưng bây giờ chỉ tới C. Reader có thể tiếp tục trên resource sai hoặc không khôi phục được state như mong muốn.

Tương tự, nếu một file mới được thêm vào đầu danh sách, index cũ có thể trỏ sang file khác. Vì vậy, với cùng JobInstance:

- Tạo một manifest đầu vào cố định.
- Lưu danh sách file hoặc batch reference khi job bắt đầu.
- Không thêm/xóa/đổi tên file trong lúc job còn có thể restart.
- Có thể lưu checksum/size/last modified để phát hiện file bị thay đổi.
- Nếu input set thay đổi, tạo JobInstance mới theo quy tắc nghiệp vụ.

Một pattern tốt là scheduler chuyển file vào thư mục batch bất biến, tạo manifest, rồi mới launch job. Các file mới đến sau được đưa vào batch khác.

## 17. Tên reader và ExecutionContext key

Spring Batch dùng tên stream để tạo key lưu state trong `ExecutionContext`. Vì vậy, tên `MultiResourceItemReader` và delegate phải ổn định qua lần chạy đầu và restart.

Ví dụ:

```java
new MultiResourceItemReaderBuilder<Customer>()
        .name("customerMultiReader")
        .resources(resources)
        .delegate(customerFileDelegate)
        .saveState(true)
        .build();
```

Delegate:

```java
new FlatFileItemReaderBuilder<Customer>()
        .name("customerFileDelegate")
        .lineMapper(customerLineMapper)
        .saveState(true)
        .build();
```

Không đổi các tên này trong khi JobInstance cũ còn có thể restart. Nếu đổi tên, key cũ có thể không còn được tìm thấy và reader có thể bắt đầu từ vị trí khác.

Nếu có nhiều reader/delegate trong cùng step, mỗi stream cần tên riêng để tránh key trùng. Không dùng cùng một delegate instance cho hai multi-resource reader đồng thời.

## 18. Nhiều loại file và nhiều delegate

`MultiResourceItemReader` thường giả định các resource có cùng định dạng vì nó dùng một delegate reader cho tất cả file. Nếu file CSV, XML và JSON cùng nằm trong một thư mục, không nên đưa tất cả vào một reader rồi hy vọng delegate tự nhận diện format.

Các cách xử lý:

- Dùng pattern riêng cho mỗi loại file và một step tương ứng.
- Tách file theo loại trước khi launch job.
- Dùng custom resource-aware delegate có thể xác định format theo metadata và route parser phù hợp.
- Chuẩn hóa mọi file về một định dạng chung ở bước upstream.

Nếu format khác nhau theo file, custom delegate phải quản lý lifecycle và checkpoint riêng cho từng resource. Độ phức tạp cao hơn đáng kể so với dùng một delegate thống nhất.

## 19. MultiResourceItemReader với XML hoặc JSON

Multi-resource reader không chỉ dành cho CSV. Có thể dùng reader delegate resource-aware phù hợp với XML/JSON nếu delegate nhận resource động và quản lý state đúng.

Ví dụ về ý tưởng:

```text
MultiResourceItemReader<Order>
       |
       +--> XML delegate đọc orders-001.xml
       |
       +--> XML delegate đọc orders-002.xml
       |
       +--> XML delegate đọc orders-003.xml
```

Delegate XML có thể dùng `StaxEventItemReader` nếu API/phiên bản cho phép cấu hình resource động qua contract cần thiết. Tương tự, JSON delegate cần hỗ trợ đọc từng item từ resource hiện tại và lưu state.

Không phải mọi reader đều triển khai `ResourceAwareItemReaderItemStream`. Nếu delegate không nhận được resource mới qua `setResource`, nó không thể được dùng trực tiếp theo cách thông thường. Hãy kiểm tra interface và lifecycle của reader cụ thể trước khi cấu hình.

## 20. Xử lý lỗi ở một resource

Nếu một file lỗi khi đang đọc, delegate có thể ném exception. Khi đó step áp dụng retry/skip policy được cấu hình.

Một số tình huống:

| Lỗi | Hành vi thường phù hợp |
|---|---|
| File không tồn tại sau khi manifest được tạo | Step thất bại; input set đã thay đổi. |
| Không có quyền đọc file | Step thất bại hoặc retry lỗi I/O tạm thời nếu có căn cứ. |
| Header không đúng | Reject file hoặc fail step; không nên parse tiếp theo mapping cũ. |
| Một dòng CSV sai định dạng | Có thể skip record nếu parser tiếp tục an toàn và nghiệp vụ cho phép. |
| File hỏng encoding/cấu trúc toàn bộ | Thường fail step và xử lý file ở upstream. |
| File rỗng | Có thể chấp nhận hoặc reject theo hợp đồng đầu vào. |

Không nên cấu hình skip quá rộng để job bỏ qua cả file lỗi rồi vẫn báo hoàn tất. Nếu một file bị loại, cần ghi nhận rõ tên file, nguyên nhân và số record dự kiến bị ảnh hưởng.

## 21. File rỗng và resource không có item

Một resource có thể tồn tại nhưng không có record. Delegate sẽ trả `null` ngay lần đọc đầu tiên của resource đó; multi-resource reader có thể đóng delegate và chuyển sang resource tiếp theo.

Điều này khác với trường hợp danh sách resource rỗng:

- Resource list rỗng: không có file nào được chọn; `strict` của multi-resource reader quyết định có báo lỗi hay không.
- Resource list có file rỗng: file tồn tại nhưng không có item; delegate đạt EOF ngay.
- Tất cả file đều rỗng: step có thể kết thúc với `readCount == 0`.

Nếu mỗi file phải có ít nhất một record, cần validation theo resource. Chỉ kiểm tra `StepExecution.readCount` tổng không thể xác định file nào rỗng nếu nhiều file được xử lý chung. Có thể ghi số item theo từng resource hoặc có bước kiểm tra manifest/metadata trước khi đọc.

## 22. MultiResourceItemReader và header/footer

Header/footer thường thuộc từng file, không phải toàn bộ stream tổng hợp. Nếu mỗi file có header, delegate `FlatFileItemReader` với `linesToSkip(1)` sẽ bỏ header khi mở từng resource.

Nếu output là một file tổng hợp duy nhất, writer thường chỉ tạo một header cho output đó. Không nhầm header của từng input file với header của output file.

Nếu mỗi input file có header riêng chứa business date hoặc source system, có thể cần đọc và lưu metadata đó. `skippedLinesCallback` có thể kiểm tra header nhưng không tự đưa header thành item. Nếu metadata header cần gắn vào mọi item, hãy dùng delegate/custom reader giữ metadata của resource hiện tại và thêm nó vào wrapper item.

## 23. Nhiều file và thứ tự chunk

Chunk boundary không nhất thiết trùng với ranh giới file. Ví dụ:

```text
File A: 120 records
File B: 180 records
File C: 90 records
Chunk size: 200

Chunk 1: 120 records từ A + 80 records đầu của B
Chunk 2: 100 records còn lại của B + 90 records từ C
```

Điều này có ý nghĩa khi processor/writer cần biết file nguồn hoặc khi cần xử lý toàn bộ file như một đơn vị atomic. `MultiResourceItemReader` không tự tạo một transaction riêng cho từng file. Transaction boundary vẫn theo chunk của step.

Nếu yêu cầu nghiệp vụ là “mỗi file phải commit hoặc rollback toàn bộ”, hãy cân nhắc chạy từng file như một partition/step riêng hoặc tạo job con cho từng resource. Không thể giả định chunk processing sẽ tự rollback tất cả record của một file khi một chunk ở cuối file thất bại.

## 24. Phân biệt MultiResourceItemReader với partitioning

Hai cách tiếp cận đều xử lý nhiều file nhưng có mục đích khác nhau:

| Tiêu chí | `MultiResourceItemReader` | Partitioning theo resource |
|---|---|---|
| Cách đọc | Một step đọc tuần tự các file qua một delegate. | Nhiều worker step, mỗi worker nhận một resource hoặc nhóm resource. |
| Concurrency | Thông thường tuần tự trong một reader instance. | Có thể chạy nhiều partition đồng thời. |
| Checkpoint | Theo resource hiện tại và delegate state. | State riêng theo từng worker/partition. |
| Ordering | Một thứ tự resource được áp dụng. | Thứ tự hoàn thành giữa partition có thể khác nhau. |
| Phù hợp | Nhiều file cùng format, xử lý tuần tự. | File độc lập, có thể xử lý song song và cần scale. |
| Độ phức tạp | Thấp hơn, cấu hình đơn giản. | Cần partitioner, worker step, concurrency và output coordination. |

Nếu file có thể xử lý độc lập và thời gian xử lý dài, partitioning có thể tăng throughput. Nếu thứ tự xử lý quan trọng hoặc file có phụ thuộc lẫn nhau, đọc tuần tự bằng `MultiResourceItemReader` thường dễ kiểm soát hơn.

## 25. MultiResourceItemReader không tự thread-safe

Một `MultiResourceItemReader` có state về resource index và delegate hiện tại. Không nên để nhiều thread gọi đồng thời cùng một instance reader trừ khi có thiết kế/đảm bảo thread-safety cụ thể.

Nếu cần xử lý song song:

- Dùng partitioning với một reader instance riêng cho mỗi worker.
- Chia resource list thành các nhóm độc lập.
- Đảm bảo mỗi worker có `ExecutionContext` và output riêng.
- Không chia sẻ một delegate có mutable state giữa nhiều worker.
- Xác định thứ tự output và cách tổng hợp kết quả.

Đồng bộ hóa method `read()` không tự giải quyết mọi vấn đề. Delegate cũng phải thread-safe, resource không bị nhiều worker đọc/ghi xung đột và checkpoint phải tách biệt.

## 26. Kiểm thử thứ tự resource

Nên kiểm thử comparator độc lập với các tên file đại diện:

```java
@Test
void sortsResourcesByNumericSequence() {
    Resource file10 = new FileSystemResource("customers-10.csv");
    Resource file2 = new FileSystemResource("customers-2.csv");
    Resource file1 = new FileSystemResource("customers-1.csv");

    List<Resource> resources = new ArrayList<>(
            List.of(file10, file2, file1));
    resources.sort(bySequence);

    assertThat(resources)
            .extracting(Resource::getFilename)
            .containsExactly(
                    "customers-1.csv",
                    "customers-2.csv",
                    "customers-10.csv");
}
```

Test nên có tên file không hợp lệ, sequence trùng và trường hợp resource không có filename nếu ứng dụng có thể gặp. Comparator cần có chính sách rõ ràng khi dữ liệu đầu vào không đúng convention.

## 27. Kiểm thử MultiResourceItemReader cơ bản

Một integration/unit test có thể tạo hai file tạm, cấu hình delegate và xác nhận item được trả theo thứ tự resource:

```java
@Test
void readsItemsFromAllResourcesInConfiguredOrder() throws Exception {
    Resource first = new ByteArrayResource(
            "C001,Nguyen An\nC002,Tran Binh\n".getBytes(UTF_8)) {
        @Override
        public String getFilename() {
            return "customers-001.csv";
        }
    };

    Resource second = new ByteArrayResource(
            "C003,Le Chi\n".getBytes(UTF_8)) {
        @Override
        public String getFilename() {
            return "customers-002.csv";
        }
    };

    FlatFileItemReader<Customer> delegate = new FlatFileItemReaderBuilder<Customer>()
            .name("customerDelegate")
            .lineMapper(customerLineMapper)
            .saveState(true)
            .build();

    MultiResourceItemReader<Customer> reader =
            new MultiResourceItemReaderBuilder<Customer>()
                    .name("customerMultiReader")
                    .resources(second, first)
                    .delegate(delegate)
                    .comparator(Comparator.comparing(Resource::getFilename))
                    .saveState(true)
                    .build();

    reader.open(new ExecutionContext());
    try {
        assertThat(reader.read().customerId()).isEqualTo("C001");
        assertThat(reader.read().customerId()).isEqualTo("C002");
        assertThat(reader.read().customerId()).isEqualTo("C003");
        assertThat(reader.read()).isNull();
    } finally {
        reader.close();
    }
}
```

Đoạn test minh họa resource ordering và việc đọc qua ranh giới file. Cần điều chỉnh constructor/encoding và `LineMapper` theo phiên bản Spring Batch cụ thể. Nếu delegate có header, hãy tạo fixture có header và cấu hình `linesToSkip` tương ứng.

## 28. Kiểm thử strict mode và resource list rỗng

Nên có hai test khác nhau:

- Khi resource list rỗng và strict bật, reader báo lỗi theo contract của phiên bản đang dùng.
- Khi resource list rỗng và strict tắt, reader kết thúc mà không có item.

Ngoài ra cần test resource không tồn tại, resource không thể mở và resource tồn tại nhưng rỗng. Những trường hợp này không giống nhau và có thể phát sinh exception ở thời điểm khác nhau.

Trong integration test, kiểm tra cả status và exit description của step/job để biết lỗi xảy ra do không tìm thấy file, không có quyền đọc hay do parser.

## 29. Kiểm thử restart qua nhiều resource

Restart là phần quan trọng nhất của multi-resource reader. Test nên tạo nhiều file với đủ record để chunk boundary nằm giữa file:

1. Tạo danh sách file A, B, C theo thứ tự xác định.
2. Launch job với identifying parameters cố định.
3. Cho reader đọc hết A và một phần B.
4. Làm step thất bại sau khi một số chunk đã commit.
5. Xác nhận ExecutionContext lưu resource index và delegate state.
6. Restart cùng JobInstance với cùng resource list, comparator, reader name và delegate name.
7. Xác nhận reader tiếp tục đúng vị trí trong B.
8. Xác nhận không bỏ sót hoặc lặp các item đã commit.
9. Xác nhận C được đọc sau khi B hoàn tất.

Không chỉ kiểm tra job `COMPLETED`. Hãy so sánh tập business key output với tập input kỳ vọng và kiểm tra số lần mỗi key được ghi.

## 30. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Không tìm thấy file nào | Pattern sai hoặc thư mục làm việc khác dự kiến. | Log pattern, validate resource count và dùng strict mode phù hợp. |
| File được đọc sai thứ tự | Resource resolver/filesystem trả thứ tự khác hoặc comparator không đúng. | Cấu hình comparator xác định và test với tên file thực tế. |
| Restart bắt đầu ở file khác | Resource list thay đổi thứ tự, thêm/xóa/đổi tên file. | Giữ manifest/resource set bất biến cho JobInstance. |
| Restart đọc lại nhiều item | Delegate không lưu state hoặc `saveState` bị tắt. | Bật state cho cả outer reader và delegate, giữ tên ổn định. |
| Header bị đọc thành dữ liệu | Delegate không bỏ header hoặc header chỉ có ở một số file. | Cấu hình `linesToSkip`/header callback theo định dạng từng resource. |
| Một file sai format làm lỗi cả step | Delegate dùng chung mapping nhưng file có cấu trúc khác. | Tách resource theo format hoặc dùng delegate chuyên biệt. |
| Một file rỗng làm step dừng sớm | Custom delegate trả null đúng EOF nhưng wrapper tự viết coi đó là EOF toàn bộ. | Dùng `MultiResourceItemReader` hoặc xử lý chuyển resource đúng contract. |
| Step thành công nhưng thiếu file | Strict mode tắt hoặc pattern không chọn đủ resource. | Kiểm tra manifest và số resource mong đợi trước khi launch. |
| File bị đọc hai lần | Resource trùng trong danh sách hoặc JobInstance mới dùng lại input. | Deduplicate manifest và xác định identity batch. |
| Delegate không mở lại được | Delegate giữ state/resource cũ hoặc không resource-aware. | Dùng delegate hỗ trợ `ResourceAwareItemReaderItemStream` và lifecycle mở/đóng đúng. |
| Ghi trùng khi restart | Writer không idempotent hoặc state writer không được lưu. | Lưu checkpoint writer và thiết kế output theo batch/resource. |
| Hiệu năng kém | Quá nhiều file nhỏ, mở/đóng file thường xuyên hoặc I/O chậm. | Đo từng resource, gộp file nhỏ nếu phù hợp hoặc partition độc lập. |

## 31. Quy trình thiết kế job đọc nhiều resource

Khi xây dựng job đọc nhiều file, hãy xác định:

1. **Resource pattern:** file nào thuộc batch hiện tại và pattern có thể chọn nhầm file không?
2. **Manifest:** có lưu danh sách resource cố định cho JobInstance không?
3. **Format:** mọi file có cùng schema, encoding, header và delimiter không?
4. **Ordering:** thứ tự đọc theo tên, sequence hay business date?
5. **Delegate:** reader nào parse một resource và có hỗ trợ resource-aware/ItemStream không?
6. **Strictness:** không có file là lỗi hay trường hợp hợp lệ?
7. **Checkpoint:** outer reader và delegate có tên/state ổn định không?
8. **Restart:** file có bất biến và resource list có giống lần chạy đầu không?
9. **Chunk boundary:** có chấp nhận chunk đi qua ranh giới hai file không?
10. **Metadata nguồn:** item có cần lưu source file, line number hoặc batch reference không?
11. **Concurrency:** đọc tuần tự bằng một reader hay partition theo file?
12. **Error handling:** file lỗi, header sai hoặc record lỗi được fail/reject/skip thế nào?
13. **Output:** writer có thể ghi dữ liệu từ nhiều resource vào cùng output không và có cần giữ thứ tự không?
14. **Testing:** kiểm tra resource list, ordering, empty file, header, restart và dữ liệu trùng/thiếu.

Một manifest bất biến, comparator xác định và delegate có checkpoint là ba nền tảng quan trọng để multi-resource job có thể restart đáng tin cậy.

## 32. Những điểm cần ghi nhớ

- `MultiResourceItemReader<T>` đọc nhiều `Resource` tuần tự bằng một delegate reader và trả item như một luồng duy nhất.
- Delegate thường là `FlatFileItemReader<T>` và phải nhận được resource hiện tại qua contract resource-aware.
- `MultiResourceItemReader` điều phối file; delegate chịu trách nhiệm parse nội dung.
- Dùng `ResourcePatternResolver` để tìm file theo pattern và validate resource set trước khi chạy.
- Cấu hình comparator rõ ràng để resource order ổn định; thứ tự từ điển không luôn giống thứ tự số/ngày.
- `strict` của multi-resource reader kiểm soát danh sách resource rỗng; strict của delegate kiểm tra resource được mở.
- Delegate được mở/đóng theo resource; header skip của `FlatFileItemReader` được áp dụng cho mỗi file khi delegate mở lại.
- Chunk có thể đi qua ranh giới file; `MultiResourceItemReader` không tự tạo transaction theo từng file.
- Outer reader và delegate cần tên ổn định, save state phù hợp và resource list bất biến để restart.
- Không thêm/xóa/đổi tên/thay nội dung file trong khi JobInstance còn có thể restart; dùng manifest hoặc batch folder cố định.
- Nếu cần source filename trong output, hãy đưa metadata nguồn vào item hoặc log/audit riêng.
- Một delegate dùng chung giả định các resource có cùng format; file khác schema nên dùng reader/step riêng hoặc custom routing rõ ràng.
- `MultiResourceItemReader` không tự thread-safe; dùng partitioning với reader instance/state riêng nếu cần xử lý song song.
- Kiểm thử ordering, resource rỗng/thiếu, header, delegate lifecycle, checkpoint/restart và không mất/trùng item.

`MultiResourceItemReader` giúp xử lý nhiều file như một nguồn dữ liệu thống nhất mà không phải tự điều phối việc chuyển file. Để job vận hành ổn định, hãy dùng delegate phù hợp, xác định thứ tự resource, giữ input set bất biến, bật checkpoint cho reader và delegate, đồng thời quyết định rõ việc xử lý header, file rỗng và lỗi từng resource. Khi số file có thể xử lý độc lập và cần throughput cao, hãy cân nhắc partitioning với một reader riêng cho từng worker.
