# Đọc nhiều file theo thứ tự resource

Trong Spring Batch, một batch job thường nhận dữ liệu được chia thành nhiều file thay vì một file duy nhất. Ví dụ, hệ thống nguồn xuất mỗi giờ một file, mỗi chi nhánh tạo một file riêng hoặc một lô dữ liệu lớn được chia thành các phần `orders-0001.csv`, `orders-0002.csv`, `orders-0003.csv`. Job cần đọc lần lượt các file này như một luồng item thống nhất.

`MultiResourceItemReader<T>` là reader của Spring Batch dùng để đọc nhiều `Resource` theo thứ tự. Nó bao bọc một reader delegate, thường là `FlatFileItemReader<T>`, và lần lượt gán từng resource cho delegate. Khi delegate đọc hết một file, `MultiResourceItemReader` chuyển sang resource tiếp theo; item được trả về cho step tạo thành một luồng liên tục.

Điểm quan trọng của chủ đề này là **thứ tự resource phải được xác định rõ ràng**. Thứ tự file mà filesystem, wildcard resolver hoặc object storage trả về không nên được xem là thứ tự nghiệp vụ. Nếu thứ tự xử lý ảnh hưởng tới kết quả, hãy cấu hình comparator hoặc cung cấp danh sách resource đã được sắp xếp theo manifest có kiểm soát.

## MultiResourceItemReader hoạt động như thế nào?

`MultiResourceItemReader<T>` nằm trong package `org.springframework.batch.item.file`. Nó không tự parse CSV hay fixed-width. Nó quản lý danh sách resource và ủy quyền việc đọc từng resource cho một `ResourceAwareItemReaderItemStream`.

Các thành phần chính:

- `resources`: danh sách file/resource cần đọc.
- `delegate`: reader thực sự đọc một resource, ví dụ `FlatFileItemReader`.
- `comparator`: quy tắc sắp xếp resource trước khi đọc.
- `strict`: quy định hành vi khi không tìm thấy resource.
- `saveState`: bật lưu vị trí resource hiện tại và state của delegate để hỗ trợ restart.

Luồng đọc khái quát:

```text
Resource[]
   |
   v
Sắp xếp theo comparator
   |
   v
MultiResourceItemReader
   |
   +--> file-0001.csv --> delegate đọc hết file
   |
   +--> file-0002.csv --> delegate đọc hết file
   |
   +--> file-0003.csv --> delegate đọc hết file
   |
   v
Một luồng item liên tục
   |
   v
Processor --> Writer
```

Ví dụ, file đầu có 100 item, file thứ hai có 250 item và file thứ ba có 50 item. Reader trả tổng cộng 400 item theo thứ tự resource đã chọn, trừ những item bị filter hoặc skip theo cấu hình step.

`MultiResourceItemReader` đọc tuần tự. Nó không tự chia các file cho nhiều thread và không tự tạo partition. Nếu cần xử lý song song từng file, cần một thiết kế partitioning riêng.

## Resource là gì?

Spring dùng abstraction `Resource` để biểu diễn nguồn dữ liệu. Một resource có thể là file local, classpath resource hoặc resource được cung cấp bởi một implementation khác.

Ví dụ:

```java
Resource first = new FileSystemResource("/batch/in/orders-0001.csv");
Resource second = new FileSystemResource("/batch/in/orders-0002.csv");
Resource template = new ClassPathResource("templates/order-header.csv");
```

Với batch đọc file từ thư mục, thường dùng `FileSystemResource` hoặc `ResourcePatternResolver` để tìm nhiều file theo pattern. `MultiResourceItemReader` nhận một mảng `Resource[]`.

Không nên đưa một resource không thể đọc hoặc không còn tồn tại vào danh sách rồi mong reader tự bỏ qua trong mọi trường hợp. Hãy xác định rõ file nào bắt buộc, file nào tùy chọn và cách xử lý khi resource biến mất giữa lúc discovery và lúc mở file.

## Cấu hình cơ bản với FlatFileItemReader

Một cấu hình phổ biến là dùng `FlatFileItemReader` làm delegate để đọc từng file CSV. Ví dụ model:

```java
public record OrderInput(
        String orderId,
        String customerId,
        BigDecimal amount) {
}
```

Khai báo `LineMapper` cho một file:

```java
@Bean
LineMapper<OrderInput> orderLineMapper() {
    DefaultLineMapper<OrderInput> mapper = new DefaultLineMapper<>();

    DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
    tokenizer.setNames("orderId", "customerId", "amount");

    mapper.setLineTokenizer(tokenizer);
    mapper.setFieldSetMapper(fields -> new OrderInput(
            fields.readString("orderId"),
            fields.readString("customerId"),
            fields.readBigDecimal("amount")));

    return mapper;
}
```

`FlatFileItemReader` delegate được tạo mà chưa gắn một file cố định. `MultiResourceItemReader` sẽ đặt resource hiện tại vào delegate trước khi mở nó:

```java
@Bean
FlatFileItemReader<OrderInput> orderFileDelegate(
        LineMapper<OrderInput> orderLineMapper) throws Exception {

    FlatFileItemReader<OrderInput> delegate = new FlatFileItemReader<>();
    delegate.setName("orderFileDelegate");
    delegate.setLineMapper(orderLineMapper);
    delegate.setEncoding(StandardCharsets.UTF_8.name());
    delegate.setLinesToSkip(1);
    delegate.setSaveState(true);
    delegate.setStrict(true);
    delegate.afterPropertiesSet();
    return delegate;
}
```

Trong ví dụ, mỗi file có một dòng header nên `linesToSkip(1)` được áp dụng khi delegate mở từng resource. Nếu chỉ file đầu tiên có header, không dùng cấu hình này một cách máy móc; cần một delegate/policy phù hợp với format thực tế.

## Tìm resource bằng pattern

`PathMatchingResourcePatternResolver` có thể tìm các file theo wildcard:

```java
ResourcePatternResolver resolver = new PathMatchingResourcePatternResolver();
Resource[] resources = resolver.getResources("file:/batch/in/orders-*.csv");
```

Pattern `file:/batch/in/orders-*.csv` tìm các resource phù hợp trong thư mục. Kết quả là danh sách resource; không nên dựa vào thứ tự trả về của resolver để quyết định thứ tự nghiệp vụ.

Nếu đường dẫn đến từ `JobParameters`, có thể tạo reader trong step scope để lấy danh sách tại thời điểm step bắt đầu:

```java
@Bean
@StepScope
MultiResourceItemReader<OrderInput> orderMultiReader(
        @Value("#{jobParameters['inputPattern']}") String inputPattern,
        LineMapper<OrderInput> orderLineMapper) throws Exception {

    ResourcePatternResolver resolver = new PathMatchingResourcePatternResolver();
    Resource[] resources = resolver.getResources(inputPattern);

    FlatFileItemReader<OrderInput> delegate = new FlatFileItemReader<>();
    delegate.setName("orderFileDelegate");
    delegate.setLineMapper(orderLineMapper);
    delegate.setEncoding(StandardCharsets.UTF_8.name());
    delegate.setLinesToSkip(1);
    delegate.setSaveState(true);
    delegate.setStrict(true);
    delegate.afterPropertiesSet();

    Comparator<String> filenameOrder =
            Comparator.nullsLast(Comparator.naturalOrder());
    Comparator<Resource> resourceOrder =
            Comparator.comparing(Resource::getFilename, filenameOrder);

    return new MultiResourceItemReaderBuilder<OrderInput>()
            .name("orderMultiReader")
            .resources(resources)
            .delegate(delegate)
            .comparator(resourceOrder)
            .strict(true)
            .saveState(true)
            .build();
}
```

`@StepScope` giúp pattern được resolve khi step chạy, phù hợp khi danh sách file thay đổi theo lần launch. `jobParameters['inputPattern']` là identifying hoặc non-identifying parameter tùy thiết kế job; nếu nó quyết định tập input của một logical job, nên đưa nó vào danh tính execution hoặc lưu một manifest bất biến để restart luôn dùng đúng tập file.

Builder và API cụ thể cần khớp phiên bản Spring Batch đang dùng. Trong một số cấu hình, có thể tạo `MultiResourceItemReader` rồi gọi `setResources`, `setDelegate`, `setComparator`, `setStrict` và `setSaveState` trực tiếp; ý nghĩa các thuộc tính vẫn giống nhau.

## Xác định thứ tự resource

`MultiResourceItemReader` hỗ trợ comparator để sắp xếp resource. Đây là điểm quan trọng khi tên file biểu diễn thời gian, sequence hoặc thứ tự nghiệp vụ.

### Sắp xếp theo tên file

Ví dụ các file:

```text
orders-0001.csv
orders-0002.csv
orders-0003.csv
```

Comparator theo filename:

```java
Comparator<Resource> byFilename =
        Comparator.comparing(Resource::getFilename);
```

Tên có sequence được zero-pad giúp thứ tự từ điển trùng với thứ tự số. Nếu tên là `orders-1.csv`, `orders-10.csv`, `orders-2.csv`, sắp xếp từ điển sẽ cho thứ tự `1`, `10`, `2`, khác thứ tự số mong muốn.

Với sequence không zero-pad, hãy parse số trong tên file hoặc lấy thứ tự từ manifest. Không dùng comparator chỉ dựa trên `toString()`/description nếu chuỗi đó không phải contract ổn định.

### Sắp xếp theo ngày hoặc sequence

Nếu tên file có dạng `orders-20261115-001.csv`, có thể trích xuất ngày và sequence để so sánh. Ví dụ:

```java
Comparator<Resource> byBusinessSequence = Comparator.comparing(
        resource -> parseSequence(resource.getFilename()));
```

`parseSequence` là method ứng dụng kiểm tra format tên file và trả về một kiểu có thể so sánh, chẳng hạn record chứa `LocalDate` và số sequence. Nếu filename không đúng format, nên báo lỗi rõ ràng thay vì trả về giá trị mặc định khiến file bị xếp sai.

Nếu business order nằm trong metadata của file hoặc manifest, dùng metadata đó làm nguồn sự thật. Tên file chỉ nên được dùng làm thứ tự khi producer bảo đảm quy tắc đặt tên tương ứng.

### Sắp xếp theo manifest

Với pipeline production, manifest thường đáng tin cậy hơn wildcard. Manifest có thể chứa:

| Sequence | Resource | Checksum | Record count |
| ---: | --- | --- | ---: |
| 1 | `orders-a.csv` | `sha256:...` | 1200 |
| 2 | `orders-b.csv` | `sha256:...` | 950 |
| 3 | `orders-c.csv` | `sha256:...` | 1400 |

Ứng dụng đọc manifest, xác nhận từng resource và tạo `Resource[]` theo đúng thứ tự sequence. Cách này giúp job biết rõ tập file thuộc một batch và phát hiện file thiếu, file thay đổi hoặc file bị lặp.

Không nên tạo manifest mới với thứ tự khác ở lần restart của cùng `JobInstance`. Hãy giữ manifest ID/version ổn định và bảo đảm nội dung manifest không thay đổi trong thời gian execution có thể restart.

## Thứ tự resource và thứ tự item

`MultiResourceItemReader` đọc hết resource hiện tại trước khi chuyển sang resource tiếp theo. Vì vậy, thứ tự item được trả ra là:

1. Tất cả item của resource đầu tiên theo thứ tự dòng trong file.
2. Tất cả item của resource thứ hai.
3. Tiếp tục cho tới resource cuối.

Ví dụ:

```text
orders-0001.csv: A-01, A-02, A-03
orders-0002.csv: B-01, B-02
orders-0003.csv: C-01, C-02, C-03

Reader emits:
A-01, A-02, A-03, B-01, B-02, C-01, C-02, C-03
```

Reader không tự merge các dòng theo timestamp, sort toàn bộ item theo một field hoặc xen kẽ các file. Nếu cần sort toàn bộ dữ liệu sau khi đọc, có thể cần staging database, external sort hoặc một bước xử lý riêng. Đừng nhầm thứ tự resource với thứ tự toàn cục của dữ liệu.

## Một delegate cho nhiều file

`MultiResourceItemReader` tái sử dụng một delegate để đọc từng resource. Vì vậy, các file thường phải có cùng cấu trúc record hoặc ít nhất tương thích với cùng `LineMapper`/parser.

Ví dụ, nếu tất cả file đều có header:

```csv
orderId,customerId,amount
O-1,C-1,100.00
O-2,C-2,250.00
```

delegate có thể dùng một tokenizer và mapper chung. Khi chuyển sang file tiếp theo, reader mở lại delegate với resource mới.

Nếu các file có schema khác nhau, ví dụ file A có ba cột còn file B có năm cột với ý nghĩa khác, không nên ép cùng một mapper đọc tất cả. Có thể phân nhóm resource theo format, dùng các step riêng hoặc triển khai reader tùy chỉnh chọn parser theo metadata của từng resource.

## Header trong từng file

Một điểm cần chú ý là delegate được mở lại cho từng resource. Nếu `FlatFileItemReader` được cấu hình `linesToSkip(1)`, header sẽ được bỏ qua ở mỗi file, không chỉ file đầu tiên.

Ví dụ:

```text
orders-0001.csv:
  orderId,amount       <- bỏ qua
  O-1,100
  O-2,200

orders-0002.csv:
  orderId,amount       <- bỏ qua khi mở delegate cho resource tiếp theo
  O-3,300
```

Điều này phù hợp khi mỗi file có header riêng. Nếu chỉ file đầu tiên có header hoặc header thay đổi giữa file, cần thiết kế rõ cách xử lý. Có thể dùng delegate tùy chỉnh, reader biết resource hiện tại hoặc bước chuẩn hóa file trước khi đọc.

`skippedLinesCallback` có thể được dùng để nhận nội dung dòng header bị bỏ qua. Nếu cần xác nhận header của mọi file giống nhau, callback có thể kiểm tra schema và báo lỗi khi header khác mong đợi.

## File rỗng và không tìm thấy resource

Phân biệt các tình huống:

- **Không tìm thấy resource nào:** wildcard không khớp file hoặc manifest rỗng.
- **Resource tồn tại nhưng file rỗng:** file có kích thước 0 byte.
- **File chỉ có header:** có resource nhưng không có data record.
- **Resource biến mất sau discovery:** file bị xóa/di chuyển trước khi reader mở.
- **Resource không đọc được:** quyền truy cập hoặc I/O lỗi.

`strict` của `MultiResourceItemReader` điều khiển hành vi khi không có resource. Với job bắt buộc phải có input, bật strict để lỗi sớm. Nếu không có file là một trường hợp hợp lệ, có thể chọn strict false và ghi nhận rõ job đã xử lý 0 item; không nên để job hoàn tất âm thầm nếu nghiệp vụ yêu cầu dữ liệu.

File rỗng hoặc chỉ có header không nhất thiết giống trường hợp không có resource. Reader có thể mở file, đọc tới EOF và chuyển sang resource tiếp theo. Nếu file rỗng là lỗi nghiệp vụ, cần validation riêng.

## MultiResourceItemReader và chunk processing

`MultiResourceItemReader` là reader ở đầu pipeline. Nó trả từng item cho chunk step như reader thông thường:

```java
@Bean
Step importManyFilesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderMultiReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importManyFilesStep", jobRepository)
            .<OrderInput, Order>chunk(200, transactionManager)
            .reader(orderMultiReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

Chunk có thể bắt đầu ở cuối một file và tiếp tục ở đầu file kế tiếp. Ví dụ file thứ nhất còn 50 item trong khi chunk size là 200; reader có thể lấy thêm 150 item từ file thứ hai để hoàn thành chunk. Ranh giới file không nhất thiết là ranh giới transaction/chunk.

Nếu nghiệp vụ yêu cầu commit riêng sau mỗi file, `MultiResourceItemReader` trong một step chunk không tự bảo đảm điều đó. Có thể cần partition/step theo file hoặc custom orchestration để tạo transaction boundary theo resource.

## Restart và ExecutionContext

`MultiResourceItemReader` hỗ trợ restart thông qua `ItemStream`. Khi `saveState(true)`, reader lưu thông tin resource đang được đọc và state của delegate trong `ExecutionContext` của step. Khi restart, nó khôi phục resource index hiện tại và mở delegate ở vị trí đã checkpoint.

Để restart đúng, cần giữ ổn định:

- Tên reader của `MultiResourceItemReader`.
- Tên delegate reader.
- Thứ tự và số lượng resource.
- Nội dung của resource đã được xử lý/chưa xử lý.
- Cấu hình parser, encoding và header policy.
- Identifying `JobParameters` của cùng `JobInstance`.

Ví dụ, lần chạy đầu có danh sách:

```text
index 0 -> orders-0001.csv
index 1 -> orders-0002.csv
index 2 -> orders-0003.csv
```

Step đã đọc một phần `orders-0002.csv` và checkpoint resource index 1 cùng delegate position. Khi restart, reader cần nhận lại đúng danh sách và thứ tự đó. Nếu một file mới được thêm ở đầu danh sách, index 1 có thể trỏ tới resource khác, khiến reader đọc nhầm hoặc bỏ sót dữ liệu.

### Danh sách resource phải ổn định

Đây là quy tắc quan trọng nhất khi restart với nhiều file. Wildcard có thể trả về tập file khác ở lần chạy sau vì:

- Producer thêm file mới.
- File đã xử lý bị archive hoặc xóa.
- Tên file thay đổi.
- Một file bị thay thế bằng nội dung mới.
- Comparator hoặc quy tắc parse sequence thay đổi.

Vì checkpoint thường dựa vào resource index, cùng một index chỉ có ý nghĩa khi resource list không đổi. Có thể giải quyết bằng cách:

1. Tạo manifest bất biến cho từng batch và dùng lại manifest ID khi restart.
2. Claim/move file vào thư mục riêng của execution trước khi launch.
3. Lưu danh sách resource đã resolve vào metadata bền vững và khôi phục đúng danh sách.
4. Dùng checksum/version để xác nhận file không bị thay đổi.
5. Chỉ archive/xóa file sau khi job hoàn tất và không còn cần restart.

Không chạy lại wildcard trên thư mục `incoming` rồi dùng kết quả mới cho một execution đang restart nếu tập file có thể thay đổi.

### Tên reader và delegate phải ổn định

`ItemStreamSupport` dùng tên component để tạo key trong `ExecutionContext`. Giữ tên reader và delegate ổn định giữa các lần deploy khi execution cũ còn có thể restart. Đổi tên có thể khiến component không tìm được state đã lưu.

`saveState(true)` nên được bật ở wrapper và delegate khi cần khôi phục cả resource index lẫn vị trí trong file. Nếu tắt state của delegate, wrapper có thể biết đang ở file nào nhưng delegate không biết vị trí record trong file đó.

Không lưu `Resource`, `InputStream` hoặc file handle đang mở vào context. State nên chứa thông tin nhỏ có thể serialize; resource thực tế được resolve lại theo manifest/path ổn định khi mở step.

## Thay đổi file giữa các lần chạy

Giả sử file `orders-0002.csv` đã được đọc một phần và job thất bại. Nếu producer ghi thêm dòng vào file trước khi restart, delegate có thể tiếp tục trên nội dung đã thay đổi. Kết quả có thể không phản ánh một snapshot nhất quán.

Vì vậy, input file của batch nên immutable sau khi được công bố. Producer có thể ghi vào tên tạm rồi rename sang tên hoàn chỉnh; consumer claim file và không cho producer sửa lại. Nếu file nằm trong object storage, lưu object version ID hoặc checksum.

Nếu bắt buộc nguồn có thể thay đổi, cần snapshot dữ liệu hoặc copy file vào staging riêng trước khi batch bắt đầu. Không chỉ dựa vào path để nhận diện cùng một nội dung.

## Xử lý lỗi trong một resource

Khi delegate đọc một file gặp lỗi, step thường xử lý exception theo reader/skip/retry policy. `MultiResourceItemReader` không tự động biến mọi lỗi thành việc bỏ file và chuyển tiếp.

Phân biệt:

- Lỗi tạm thời khi mở resource: có thể retry có giới hạn nếu nguyên nhân có khả năng phục hồi.
- File không tồn tại hoặc quyền sai: thường là lỗi cấu hình/ingestion cần điều tra.
- Record sai format: xử lý theo validation/skip policy nếu có thể xác định ranh giới record an toàn.
- File bị truncate hoặc encoding sai: thường nên fail/quarantine file thay vì bỏ qua không kiểm soát.

Nếu một file lỗi ở giữa, việc tiếp tục đọc các file sau có thể làm batch hoàn tất với dữ liệu thiếu. Chỉ thiết kế skip-file behavior khi nghiệp vụ chấp nhận partial success và có audit rõ ràng về file bị bỏ qua.

## Theo dõi resource hiện tại

Khi vận hành job nhiều file, log nên cho biết resource nào đang được xử lý. `MultiResourceItemReader` có resource index nội bộ; nếu cần tên file trong log/audit, có thể dùng một delegate/listener/wrapper được thiết kế để quan sát resource hiện tại hoặc bổ sung metadata từ manifest.

Các thông tin nên ghi nhận:

- Job name và `JobExecution` ID.
- Step name và `StepExecution` ID.
- Manifest/batch ID.
- Resource path hoặc resource ID.
- Sequence/resource index.
- Record count theo file nếu có thể đo.
- Thời điểm bắt đầu/kết thúc từng resource.
- Checksum/version và lỗi mở/đọc.

Không nên phụ thuộc vào field private của `MultiResourceItemReader` để lấy resource hiện tại. Nếu cần API quan sát ổn định, hãy dùng wrapper hoặc metadata store của ứng dụng.

## Đọc nhiều file có schema khác nhau

Một `MultiResourceItemReader` thường dùng một delegate cho mọi resource. Do đó, nó phù hợp khi các file có cùng cấu trúc, encoding, header và quy tắc record.

Nếu mỗi loại file cần mapper khác nhau, có một số lựa chọn:

- Phân loại file trước và chạy một step riêng cho từng format.
- Tạo nhiều `MultiResourceItemReader` cho từng nhóm resource.
- Dùng reader tùy chỉnh chọn parser dựa trên manifest/file metadata.
- Chuẩn hóa các file về một schema staging trước khi đọc chính.

Không nên kiểm tra tên file rồi thay `LineMapper` tùy tiện giữa lúc reader đang mở nếu không kiểm soát lifecycle và restart. Metadata format nên được xác định trước khi step bắt đầu.

## Đọc song song từng file

`MultiResourceItemReader` xử lý resource theo thứ tự trong một luồng đọc. Nếu cần tăng throughput bằng cách đọc nhiều file song song, có thể dùng partitioning: mỗi partition nhận một resource và chạy một reader riêng.

```text
                 Master step
                      |
             Partition resources
             /        |        \
            v         v         v
        Worker 1   Worker 2   Worker 3
        file A     file B     file C
```

Spring Batch cung cấp `MultiResourcePartitioner` trong các phiên bản hỗ trợ để tạo execution context theo resource. Worker step dùng `@StepScope` reader lấy resource của partition từ `stepExecutionContext`.

Partitioning khác với `MultiResourceItemReader`:

| Cách đọc | Đặc điểm |
| --- | --- |
| `MultiResourceItemReader` | Một step đọc tuần tự nhiều resource, một luồng item liên tục |
| Partition theo resource | Mỗi partition xử lý resource riêng; có thể chạy song song |

Khi partition, cần bảo đảm writer có thể nhận dữ liệu đồng thời, output không tranh chấp và thứ tự kết quả được tổng hợp nếu nghiệp vụ yêu cầu. Không chia sẻ một reader mutable duy nhất giữa các worker.

## Hiệu năng và bộ nhớ

`MultiResourceItemReader` đọc tuần tự và thường chỉ giữ resource hiện tại cùng state cần thiết; nó không cần nạp toàn bộ nội dung của mọi file vào memory. Tuy nhiên, việc resolve wildcard có thể tạo danh sách resource lớn và metadata/checkpoint cần quản lý.

Để giữ hiệu năng:

- Dùng pattern hẹp để không quét file không liên quan.
- Sắp xếp resource bằng comparator đơn giản và xác định.
- Tránh đọc toàn bộ file vào `List` trước khi đưa vào reader.
- Dùng chunk size phù hợp với database, transaction duration và kích thước item.
- Theo dõi thời gian mở từng file và thời gian xử lý mỗi resource.
- Nếu số file rất lớn, cân nhắc manifest/partitioning thay vì wildcard rộng.
- Đừng tạo nhiều reader instance cùng đọc một resource nếu không có claim/partition rõ ràng.

Thời gian xử lý tổng thường phụ thuộc vào tổng số record, chi phí mở file, parser, processor, writer và I/O. Tăng số file nhỏ có thể làm tăng overhead mở/đóng resource; ghép file quá lớn có thể làm khó restart và retry. Chọn cách chia file theo đặc điểm vận hành thực tế.

## Kiểm thử MultiResourceItemReader

Nên kiểm thử cả thứ tự resource, ranh giới file, header, empty resource và restart. Unit test comparator không đủ để chứng minh reader chuyển resource đúng; cần test reader thực tế với file tạm.

### Kiểm thử thứ tự resource

Tạo ba file có tên không theo thứ tự tạo file:

```text
orders-0003.csv
orders-0001.csv
orders-0002.csv
```

Đưa chúng vào reader với comparator theo filename và xác nhận item được trả theo thứ tự `0001`, `0002`, `0003`. Không dùng thứ tự tạo file hoặc thứ tự list từ filesystem làm expected value.

### Kiểm thử header mỗi file

Tạo hai file có header và data. Cấu hình delegate `linesToSkip(1)`. Xác nhận header của cả hai file không được trả thành item và mọi data record đều xuất hiện.

### Kiểm thử file rỗng và chỉ có header

Đưa một file rỗng và một file chỉ có header vào danh sách. Xác nhận reader chuyển sang resource tiếp theo và trả đúng item. Nếu nghiệp vụ cấm file rỗng, kiểm tra validation riêng.

### Kiểm thử không có resource

Cho pattern không khớp file. Với strict mode, xác nhận step báo lỗi rõ ràng. Với strict false, xác nhận hành vi 0 item được ghi nhận theo yêu cầu nghiệp vụ.

### Kiểm thử restart giữa một resource

Tạo nhiều file với nhiều item. Chạy step qua một số chunk rồi gây lỗi khi reader đang ở giữa file thứ hai. Restart cùng identifying parameters và cùng danh sách resource. Xác nhận:

- Reader mở lại đúng resource thứ hai.
- Delegate tiếp tục ở đúng vị trí record.
- File thứ nhất không bị đọc lại từ đầu nếu checkpoint đã commit qua nó.
- Các file còn lại được đọc đúng thứ tự.
- Output không thiếu hoặc trùng item.

### Kiểm thử restart khi danh sách resource thay đổi

Mô phỏng lần chạy đầu có `A`, `B`, `C`, checkpoint ở index 1; trước restart thêm `A0` hoặc xóa `A`. Xác nhận test phát hiện tập resource không còn giống manifest/version đã lưu và job không tiếp tục trên danh sách thay đổi. Không coi việc chạy thành công là đủ; cần xác minh đúng resource identity.

### Kiểm thử malformed resource

Đặt một file có record lỗi ở giữa danh sách. Xác nhận job fail/skip theo policy và audit xác định đúng file gây lỗi. Không để job âm thầm bỏ file mà không có metadata.

## Ví dụ integration test đơn giản

Một test có thể trực tiếp mở reader với `ExecutionContext` để xác nhận luồng item:

```java
@Test
void readsResourcesInConfiguredOrder() throws Exception {
    Resource[] resources = {
            new FileSystemResource(file3),
            new FileSystemResource(file1),
            new FileSystemResource(file2)
    };

    MultiResourceItemReader<String> reader =
            new MultiResourceItemReaderBuilder<String>()
                    .name("testMultiReader")
                    .resources(resources)
                    .delegate(testDelegate())
                    .comparator(Comparator.comparing(Resource::getFilename))
                    .saveState(true)
                    .build();

    reader.open(new ExecutionContext());
    try {
        assertEquals("A-1", reader.read());
        assertEquals("A-2", reader.read());
        assertEquals("B-1", reader.read());
        assertEquals("C-1", reader.read());
        assertNull(reader.read());
    } finally {
        reader.close();
    }
}
```

`testDelegate()` là helper trả về reader phù hợp với fixture; expected value giả định file được sắp xếp theo tên `file1`, `file2`, `file3`. Trong test production, nên dùng file tạm và `FlatFileItemReader` thật để kiểm tra cả line mapping, encoding và header.

## Những lỗi thường gặp

### Dựa vào thứ tự wildcard trả về

Thứ tự có thể khác giữa filesystem, OS hoặc lần chạy. Cấu hình comparator rõ ràng hoặc dùng manifest.

### Sắp xếp tên số theo từ điển

`file-10` có thể đứng trước `file-2`. Dùng zero-padding hoặc comparator parse sequence.

### Không giữ danh sách resource ổn định khi restart

Checkpoint resource index có thể trỏ tới file khác nếu list thay đổi. Dùng manifest/snapshot bất biến và giữ resource trong thời gian restart.

### Dùng một delegate cho file có schema khác nhau

Mapper có thể parse sai hoặc fail. Phân nhóm format, dùng step riêng hoặc reader tùy chỉnh.

### Quên header được skip ở từng file

Delegate mở lại cho mỗi resource nên `linesToSkip(1)` áp dụng ở mỗi file. Xác định file nào có header.

### Nghĩ chunk phải kết thúc ở ranh giới file

Chunk có thể chứa item từ cuối file này và đầu file kế tiếp. Nếu cần transaction theo file, thiết kế step/partition riêng.

### Nghĩ MultiResourceItemReader chạy song song

Reader mặc định đọc tuần tự. Dùng partitioning nếu cần xử lý song song từng resource.

### Không phân biệt không có file với file rỗng

Strict mode xử lý danh sách resource rỗng; file rỗng vẫn là một resource hợp lệ. Validation nghiệp vụ cần phân biệt hai trường hợp.

### Bật saveState ở wrapper nhưng tắt ở delegate

Wrapper có thể khôi phục file index nhưng delegate không khôi phục vị trí trong file. Bật state phù hợp cho cả hai khi cần restart.

### Archive file trước khi job hoàn tất

Restart có thể không tìm thấy resource đã checkpoint. Chỉ archive sau khi execution hoàn tất và theo retention phù hợp.

### Chia sẻ reader giữa nhiều thread

Reader giữ state resource/index nên không được giả định thread-safe. Dùng một reader riêng cho từng partition hoặc execution.

## Nguyên tắc thiết kế

Khi đọc nhiều file theo thứ tự resource, hãy xác định:

1. Tập file được chọn từ wildcard, danh sách tường minh hay manifest?
2. Thứ tự nghiệp vụ dựa trên filename, sequence, timestamp hay metadata nào?
3. Comparator có xác định, ổn định và xử lý filename không hợp lệ không?
4. Tất cả file có cùng encoding, schema, header và record format không?
5. Delegate có được mở lại đúng cho từng resource và skip header đúng không?
6. Không tìm thấy resource, file rỗng và file không đọc được được xử lý khác nhau ra sao?
7. Danh sách và nội dung resource có bất biến trong thời gian restart không?
8. Wrapper và delegate có `saveState`/name ổn định không?
9. Chunk có thể đi qua ranh giới file hay nghiệp vụ yêu cầu commit theo file?
10. Có cần đọc tuần tự hay nên partition từng resource để chạy song song?
11. Log/metrics có xác định được file hiện tại, sequence và lỗi không?
12. Integration test đã bao gồm ordering, header, empty file, missing resource, restart và list mutation chưa?

Với các file có cùng cấu trúc và cần xử lý tuần tự, `MultiResourceItemReader` kết hợp delegate `FlatFileItemReader` là lựa chọn đơn giản. Đặt comparator tường minh, dùng manifest hoặc snapshot để giữ thứ tự ổn định, và bật state cho cả wrapper lẫn delegate khi cần restart. Nếu cần transaction theo file hoặc xử lý song song, cân nhắc partitioning. Luôn giữ input immutable và chỉ archive sau khi job hoàn tất để checkpoint tiếp tục đúng resource.

## Ghi nhớ

`MultiResourceItemReader<T>` đọc lần lượt nhiều `Resource` bằng một delegate reader, thường là `FlatFileItemReader`. Nó tạo một luồng item liên tục: đọc hết file hiện tại rồi chuyển sang file tiếp theo. Dùng `resources`, `delegate`, `comparator`, `strict` và `saveState` để cấu hình. Không dựa vào thứ tự wildcard/filesystem; sắp xếp rõ ràng theo filename, sequence hoặc manifest. Delegate được mở lại cho từng file, nên `linesToSkip(1)` áp dụng ở mỗi file. Reader hoạt động tuần tự, không tự partition hoặc commit riêng theo file; chunk có thể đi qua ranh giới resource. Khi restart, giữ ổn định tên reader/delegate, thứ tự và nội dung resource vì checkpoint có thể dựa trên resource index cùng state delegate. Dùng manifest bất biến, input immutable, kiểm thử restart và chỉ archive file sau khi job hoàn tất.
