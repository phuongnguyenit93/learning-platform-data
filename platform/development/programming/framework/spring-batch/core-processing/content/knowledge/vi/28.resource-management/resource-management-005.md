# Resource từ classpath và filesystem

Trong Spring Framework và Spring Batch, `Resource` là abstraction đại diện cho một nguồn dữ liệu có thể đọc được. Nguồn đó có thể là file nằm trong classpath, file bên ngoài ứng dụng, URL hoặc một dạng resource khác. Nhờ abstraction này, reader có thể nhận một `Resource` mà không cần tự biết cách mở từng loại nguồn.

Hai loại thường gặp khi xây dựng batch job là:

- **`ClassPathResource`:** đọc tài nguyên được đóng gói trong classpath, ví dụ file cấu hình hoặc dữ liệu mẫu nằm trong `src/main/resources`.
- **`FileSystemResource`:** đọc file tồn tại trên filesystem, ví dụ file CSV được scheduler hoặc hệ thống bên ngoài đưa vào thư mục nhập liệu.

Việc chọn đúng loại resource ảnh hưởng đến cách ứng dụng tìm file khi chạy trong IDE, khi đóng gói thành JAR, khi triển khai trên máy chủ và khi Job được restart. Với batch job, resource cần ổn định trong suốt lần chạy để reader có thể đọc đúng dữ liệu và khôi phục checkpoint.

## 1. Resource abstraction trong Spring

`org.springframework.core.io.Resource` là interface mô tả một nguồn dữ liệu. Một số phương thức thường dùng:

| Phương thức | Mục đích |
|---|---|
| `exists()` | Kiểm tra resource có tồn tại hay không |
| `isReadable()` | Kiểm tra resource có thể đọc hay không |
| `getInputStream()` | Mở stream để đọc dữ liệu |
| `getFilename()` | Lấy tên file nếu resource có tên |
| `getDescription()` | Lấy mô tả resource để ghi log hoặc báo lỗi |
| `contentLength()` | Lấy kích thước nội dung nếu resource hỗ trợ |
| `lastModified()` | Lấy thời điểm sửa đổi nếu resource hỗ trợ |
| `getFile()` | Lấy đối tượng `File` khi resource thực sự có biểu diễn file trên filesystem |

Spring cung cấp nhiều implementation của `Resource`, chẳng hạn:

| Implementation | Nguồn |
|---|---|
| `ClassPathResource` | Tài nguyên từ classpath/class loader |
| `FileSystemResource` | File hoặc path trên filesystem |
| `PathResource` | Java NIO `Path` |
| `UrlResource` | Tài nguyên được định địa chỉ bằng URL |
| `ByteArrayResource` | Mảng byte trong bộ nhớ |
| `InputStreamResource` | Một `InputStream` đã được cung cấp |

Trong Spring Batch, các reader như `FlatFileItemReader` nhận `Resource` làm đầu vào. Điều này giúp cùng một reader definition có thể đọc file từ classpath hoặc filesystem mà không phải viết lại logic parse.

## 2. ClassPathResource là gì?

`ClassPathResource` đại diện cho một tài nguyên được tìm thấy thông qua classpath. Trong dự án Maven/Gradle thông thường, các file đặt dưới `src/main/resources` sẽ được copy vào classpath khi build.

Ví dụ cấu trúc dự án:

```text
src/
  main/
    java/
      com/example/batch/
        OrderImportConfiguration.java
    resources/
      data/
        sample-orders.csv
      batch/
        import.properties
```

File `sample-orders.csv` có thể được truy cập bằng:

```java
Resource resource = new ClassPathResource("data/sample-orders.csv");
```

Hoặc inject trực tiếp:

```java
@Bean
public Resource sampleOrdersResource() {
    return new ClassPathResource("data/sample-orders.csv");
}
```

Classpath resource phù hợp với dữ liệu mặc định, file mẫu, schema, template hoặc dữ liệu tham chiếu được đóng gói cùng phiên bản ứng dụng. Nó không phù hợp cho file đầu vào mà hệ thống bên ngoài cần thay thế thường xuyên sau khi ứng dụng đã được build.

## 3. Đường dẫn classpath

Với `ClassPathResource`, đường dẫn được tìm tương đối với classpath, không phải thư mục làm việc hiện tại của process.

Ví dụ:

```java
new ClassPathResource("data/sample-orders.csv");
```

Với `ResourceLoader`, có thể dùng prefix `classpath:`:

```java
@Value("classpath:data/sample-orders.csv")
Resource sampleOrders;
```

Một số điểm cần lưu ý:

- Đường dẫn phải khớp với vị trí resource sau khi build.
- Tên thư mục và file cần đúng chữ hoa/thường; môi trường Linux và JAR thường phân biệt chữ hoa/thường.
- Không thêm `src/main/resources` vào đường dẫn runtime. Phần đó là thư mục nguồn của project; resource runtime thường bắt đầu từ nội dung bên trong nó.
- Có thể dùng dấu `/` làm dấu phân cách trong classpath resource trên các hệ điều hành.
- Nên thống nhất một quy ước đường dẫn trong cấu hình để tránh khác biệt giữa IDE và môi trường triển khai.

Nếu file nằm ở `src/main/resources/data/sample-orders.csv`, đường dẫn runtime là `data/sample-orders.csv`, không phải `src/main/resources/data/sample-orders.csv`.

## 4. FileSystemResource là gì?

`FileSystemResource` đại diện cho file hoặc path tồn tại trên filesystem của máy chạy ứng dụng. Đây là lựa chọn phổ biến cho file được chuyển đến từ hệ thống bên ngoài, thư mục chia sẻ hoặc volume mount.

Ví dụ tạo resource từ path:

```java
Resource input = new FileSystemResource("/var/batch/inbound/orders.csv");
```

Hoặc dùng Java NIO `Path`:

```java
Path inputPath = Path.of("/var/batch/inbound/orders.csv");
Resource input = new FileSystemResource(inputPath);
```

`FileSystemResource` có thể đọc file thay đổi độc lập với việc build ứng dụng. Đây là lựa chọn phù hợp khi scheduler hoặc upstream system đặt file mới vào thư mục đầu vào trước mỗi lần chạy Job.

Trong môi trường Windows, đường dẫn filesystem có thể là `C:\\batch\\inbound\\orders.csv`; trong code Java nên ưu tiên `Path.of(...)` hoặc cấu hình path phù hợp với môi trường thay vì ghép chuỗi bằng dấu phân cách thủ công.

## 5. Đường dẫn tương đối và tuyệt đối của filesystem

Đường dẫn tương đối thường được phân giải dựa trên thư mục làm việc hiện tại (`user.dir`) của process. Thư mục này có thể khác nhau khi chạy từ IDE, command line, service manager, container hoặc scheduler.

Ví dụ:

```java
Resource input = new FileSystemResource("data/orders.csv");
```

Đường dẫn này có thể trỏ đến:

```text
<working-directory>/data/orders.csv
```

Nếu ứng dụng chạy từ thư mục khác, nó có thể không tìm thấy file hoặc đọc nhầm file cùng tên. Với batch job production, nên cấu hình thư mục gốc rõ ràng hoặc truyền path tuyệt đối.

Ví dụ dùng property:

```yaml
batch:
  input-directory: /var/batch/inbound
```

```java
@Bean
@StepScope
public Resource orderInputResource(
        @Value("${batch.input-directory}") String inputDirectory,
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    Path path = Path.of(inputDirectory).resolve(inputFile).normalize();
    return new FileSystemResource(path);
}
```

Trong ví dụ, application property cung cấp thư mục triển khai, còn JobParameter cung cấp tên file theo lần chạy. Nếu `inputFile` đến từ người dùng hoặc hệ thống bên ngoài, cần kiểm tra nó không thoát khỏi thư mục được phép bằng `..`, path tuyệt đối hoặc symbolic link ngoài phạm vi dự kiến.

## 6. Phân biệt classpath và filesystem

Hai loại resource đều triển khai `Resource`, nhưng cách tìm và vòng đời khác nhau:

| Tiêu chí | `ClassPathResource` | `FileSystemResource` |
|---|---|---|
| Nơi tìm | Classpath/class loader | Filesystem của máy chạy |
| Nguồn phổ biến | `src/main/resources` được đóng gói | Thư mục inbound/outbound bên ngoài |
| Thay đổi sau build | Thường cần build/triển khai lại để thay nội dung trong JAR | Có thể thay file mà không build lại ứng dụng |
| Khi chạy từ executable JAR | Có thể đọc trực tiếp từ trong JAR | Đọc file bên ngoài JAR |
| Phù hợp | Template, file mẫu, dữ liệu mặc định | File batch đầu vào/đầu ra thay đổi theo lần chạy |
| Ghi/cập nhật nội dung | Không nên xem là vùng lưu file có thể ghi | Có thể ghi nếu quyền filesystem cho phép |

Chọn resource dựa trên nơi dữ liệu được quản lý. Nếu dữ liệu do ứng dụng phát hành cùng artifact và bất biến, classpath phù hợp. Nếu dữ liệu được gửi đến máy chủ theo lịch, filesystem phù hợp hơn.

## 7. Vì sao ClassPathResource không phải lúc nào cũng trả về File?

Khi chạy ứng dụng trong IDE, classpath resource thường nằm dưới một thư mục như `target/classes` hoặc `build/resources/main`. Khi đó, resource có thể có biểu diễn `File` trên filesystem.

Nhưng khi ứng dụng được đóng gói thành executable JAR, resource có thể nằm bên trong archive:

```text
application.jar
  BOOT-INF/classes/
    data/sample-orders.csv
```

Resource lúc này được đọc thông qua class loader và stream. Nó không phải một file độc lập có đường dẫn filesystem thông thường.

Vì vậy, đoạn code sau không portable:

```java
Resource resource = new ClassPathResource("data/sample-orders.csv");
File file = resource.getFile();
```

`getFile()` có thể hoạt động trong IDE nhưng ném `FileNotFoundException` khi resource nằm trong JAR. Khi cần đọc nội dung, hãy dùng `getInputStream()` hoặc truyền trực tiếp `Resource` cho API hỗ trợ Spring Resource.

```java
try (InputStream inputStream = resource.getInputStream()) {
    // Đọc dữ liệu từ stream.
}
```

Không nên giải quyết vấn đề bằng cách giả định mọi resource đều có thể chuyển thành `File`. Hãy dùng abstraction phù hợp với thao tác cần thực hiện.

## 8. Đọc resource thông qua ResourceLoader

`ResourceLoader` giúp tạo `Resource` từ một location string. Prefix cho biết nguồn cần phân giải:

```java
@Component
public class BatchResourceFactory {

    private final ResourceLoader resourceLoader;

    public BatchResourceFactory(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public Resource classpathTemplate() {
        return resourceLoader.getResource("classpath:templates/orders.csv");
    }

    public Resource filesystemInput(String path) {
        return resourceLoader.getResource("file:" + path);
    }
}
```

Các location phổ biến:

| Location | Cách phân giải |
|---|---|
| `classpath:data/orders.csv` | Resource trong classpath |
| `file:/var/batch/orders.csv` | File trên filesystem |
| `https://example.org/orders.csv` | Resource theo URL |
| `data/orders.csv` | Phụ thuộc implementation/context của ResourceLoader; không nên dựa vào nếu cần rõ ràng |

Với đường dẫn filesystem có khoảng trắng hoặc ký tự đặc biệt, cần xử lý URI/path đúng cách thay vì nối chuỗi `file:` một cách tùy tiện. Nếu đã có `Path`, tạo `FileSystemResource` từ `Path` thường rõ ràng hơn.

## 9. Inject Resource trực tiếp vào ItemReader

`FlatFileItemReader` nhận `Resource`, vì vậy có thể dùng cả classpath và filesystem mà không thay đổi cấu hình parse.

### Đọc file từ classpath

```java
@Bean
public FlatFileItemReader<Order> sampleOrderReader() {
    return new FlatFileItemReaderBuilder<Order>()
            .name("sampleOrderReader")
            .resource(new ClassPathResource("data/sample-orders.csv"))
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(Order.class)
            .build();
}
```

Reader dùng dữ liệu mẫu được đóng gói cùng ứng dụng. Đây là lựa chọn hợp lý cho demo, test hoặc một file tham chiếu bất biến.

### Đọc file từ filesystem

```java
@Bean
@StepScope
public FlatFileItemReader<Order> inboundOrderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    Resource resource = new FileSystemResource(inputFile);

    return new FlatFileItemReaderBuilder<Order>()
            .name("inboundOrderReader")
            .resource(resource)
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

Reader nhận file theo JobParameter của từng lần chạy. `@StepScope` giúp late binding giá trị `inputFile` khi StepExecution đã tồn tại.

Trong cả hai ví dụ, reader nhận cùng một abstraction `Resource`. Khác biệt chỉ nằm ở implementation và cách xác định location.

## 10. Inject Resource bằng @Value

Spring có thể chuyển location string thành `Resource` khi inject qua `@Value`:

```java
@Bean
@StepScope
public FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputLocation']}") Resource inputResource) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(inputResource)
            .delimited()
            .names("orderId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

JobParameter có thể chứa location rõ nguồn:

```text
classpath:data/sample-orders.csv
file:/var/batch/inbound/orders-2026-11-15.csv
```

Với cách này, caller quyết định resource location. Cần kiểm soát các scheme được phép, nhất là khi location đến từ API hoặc người dùng. Không nên cho phép một tham số tùy ý trỏ đến mọi URL hoặc file trên máy chủ nếu ứng dụng chỉ cần đọc một thư mục inbound xác định.

Nếu muốn cố định loại nguồn, inject `String` rồi tự tạo `ClassPathResource` hoặc `FileSystemResource` để tránh caller thay đổi scheme.

## 11. Kiểm tra resource trước khi chạy Step

Một resource có thể được tạo thành công nhưng file không tồn tại hoặc không có quyền đọc. Có thể kiểm tra sớm bằng `exists()` và `isReadable()`:

```java
private void validateResource(Resource resource) {
    if (!resource.exists()) {
        throw new IllegalArgumentException(
                "Input resource does not exist: " + resource.getDescription()
        );
    }

    if (!resource.isReadable()) {
        throw new IllegalArgumentException(
                "Input resource is not readable: " + resource.getDescription()
        );
    }
}
```

Có thể gọi validation trong factory tạo reader hoặc một Tasklet/Step kiểm tra đầu vào. Với file rất lớn hoặc resource remote, một số phép kiểm tra metadata có thể tốn chi phí hoặc không phản ánh chắc chắn khả năng đọc toàn bộ nội dung. Việc mở stream và xử lý lỗi I/O vẫn cần được quản lý.

Với `FlatFileItemReader`, thuộc tính `strict` mặc định thường yêu cầu resource tồn tại khi mở reader. Có thể cấu hình rõ theo yêu cầu, nhưng không nên tắt strict chỉ để Job bỏ qua một file đầu vào bắt buộc bị thiếu.

## 12. Encoding và định dạng file

Khi đọc file text, cần thống nhất encoding giữa hệ thống tạo file và batch reader. Nếu file được mã hóa UTF-8 nhưng reader dùng charset khác, tiếng Việt hoặc ký tự đặc biệt có thể bị lỗi.

Ví dụ cấu hình reader:

```java
return new FlatFileItemReaderBuilder<Order>()
        .name("inboundOrderReader")
        .resource(resource)
        .encoding(StandardCharsets.UTF_8.name())
        .linesToSkip(1)
        .delimited()
        .names("orderId", "customerId", "amount")
        .targetType(Order.class)
        .saveState(true)
        .build();
```

`linesToSkip(1)` thường dùng khi dòng đầu là header. Encoding và định dạng delimiter phải phù hợp với hợp đồng file đầu vào. Resource chỉ xác định nơi lấy nội dung; nó không tự xác định charset hoặc schema dữ liệu.

Nếu file có thể đến từ nhiều nguồn với encoding khác nhau, nên chuẩn hóa upstream hoặc đưa encoding thành tham số được validate thay vì đoán dựa trên môi trường máy chạy.

## 13. Resource và restart của Spring Batch

Reader như `FlatFileItemReader` có thể lưu tiến độ vào Step `ExecutionContext` khi `saveState(true)`. Khi Job restart cùng JobInstance, reader khôi phục checkpoint để tiếp tục đọc.

Ví dụ:

```java
@Bean
@StepScope
public FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

Để restart đáng tin cậy:

- Giữ nguyên identifying JobParameters để restart đúng JobInstance.
- Dùng tên reader ổn định vì tên có thể tham gia tạo key trong ExecutionContext.
- Giữ nguyên resource và nội dung file trong suốt vòng đời của execution.
- Không thay thế file bằng nội dung khác trong khi Job đang dở.
- Đảm bảo reader hỗ trợ `ItemStream` và state được lưu.
- Nếu file có thể bị thay đổi, lưu checksum/version hoặc tạo bản snapshot bất biến trước khi xử lý.

Checkpoint theo số dòng chỉ có ý nghĩa khi nội dung và thứ tự file không đổi. Nếu upstream ghi đè file cũ bằng nội dung mới, reader có thể tiếp tục từ dòng đã lưu nhưng thực tế đang đọc một bản dữ liệu khác.

Classpath resource thường bất biến theo artifact version, nhưng nếu deploy artifact mới giữa lúc Job cũ đang dở, nội dung resource có thể thay đổi. Với Job cần restart qua deployment, nên version hóa artifact hoặc lưu resource đầu vào ở nơi bất biến và có định danh rõ ràng.

## 14. Không dùng getFile() cho mọi Resource

Một số API Java yêu cầu `File` hoặc `Path`, nhưng `Resource` không bảo đảm luôn có file vật lý.

Ví dụ không an toàn:

```java
Resource resource = new ClassPathResource("data/sample-orders.csv");
Path path = resource.getFile().toPath();
```

Đoạn code có thể chạy trong IDE nhưng thất bại khi resource được đóng gói bên trong JAR.

Nếu API chỉ cần đọc, dùng stream:

```java
try (InputStream inputStream = resource.getInputStream()) {
    // Đọc dữ liệu từ stream.
}
```

Nếu API bắt buộc cần `Path`, có thể copy classpath resource sang một file tạm:

```java
Path temporaryFile = Files.createTempFile("sample-orders-", ".csv");

try (InputStream inputStream = resource.getInputStream()) {
    Files.copy(inputStream, temporaryFile, StandardCopyOption.REPLACE_EXISTING);
}
```

Sau khi sử dụng, cần xóa file tạm theo lifecycle phù hợp. Với batch job, việc copy cần được thiết kế để restart có thể dùng lại đúng nội dung; không tạo một file tạm ngẫu nhiên mới ở mỗi lần restart nếu checkpoint phụ thuộc vào file trước.

## 15. Phân biệt FileSystemResource, PathResource và UrlResource

Các implementation có thể phục vụ nhu cầu gần nhau nhưng thể hiện nguồn khác nhau:

- `FileSystemResource` phù hợp khi code đang làm việc với đường dẫn filesystem hoặc file.
- `PathResource` phù hợp khi ứng dụng đã dùng Java NIO `Path` và muốn biểu diễn resource từ path đó.
- `UrlResource` phù hợp khi nguồn được định địa chỉ bằng URL, chẳng hạn HTTP hoặc một URL scheme được hỗ trợ.

Ví dụ:

```java
Path path = Path.of("/var/batch/inbound/orders.csv");
Resource filesystemResource = new FileSystemResource(path);
Resource pathResource = new PathResource(path);
Resource urlResource = new UrlResource(URI.create("https://example.org/orders.csv"));
```

Không nên coi `UrlResource` là lựa chọn mặc định cho file batch lớn qua HTTP. Cần xem xét timeout, retry, tính ổn định nội dung, xác thực, tải lặp khi restart và khả năng snapshot dữ liệu. Trong nhiều hệ thống, tải file về thư mục inbound có kiểm soát trước rồi chạy Job trên file bất biến sẽ dễ vận hành hơn.

## 16. Resource đầu vào và đầu ra

`Resource` thường được dùng để mô tả nguồn đọc. Với file output, Spring Batch có writer riêng và một số writer nhận `Resource` làm đích.

Ví dụ `FlatFileItemWriter` ghi ra filesystem:

```java
@Bean
@StepScope
public FlatFileItemWriter<Order> orderWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderWriter")
            .resource(new FileSystemResource(outputFile))
            .delimited()
            .names("orderId", "amount")
            .shouldDeleteIfExists(false)
            .saveState(true)
            .build();
}
```

Đối với output, cần quyết định rõ append, overwrite, restart và publish file hoàn tất. Không nên ghi vào classpath resource vì resource bên trong JAR thường không phải vùng có thể ghi. Hãy dùng filesystem hoặc storage chuyên dụng cho output.

Nếu output cần được công bố cho hệ thống khác, có thể ghi file tạm rồi đổi tên/publish sau khi Step thành công. Thao tác rename chỉ có thể được xem là atomic trong các điều kiện filesystem phù hợp; với object storage hoặc hai filesystem khác nhau, cần cơ chế publish riêng.

## 17. Bảo vệ đường dẫn filesystem

Nếu JobParameter chứa path do người dùng hoặc upstream truyền vào, cần giới hạn vị trí file được phép đọc. Không nên nối trực tiếp input string vào một thư mục gốc mà không chuẩn hóa và xác thực.

Ví dụ kiểm tra path nằm trong thư mục inbound:

```java
Path baseDirectory = Path.of("/var/batch/inbound").toRealPath();
Path candidate = baseDirectory.resolve(inputFile).normalize();

if (!candidate.startsWith(baseDirectory)) {
    throw new IllegalArgumentException("Input path is outside inbound directory");
}

if (!Files.isRegularFile(candidate) || !Files.isReadable(candidate)) {
    throw new IllegalArgumentException("Input file is missing or unreadable");
}

Resource resource = new FileSystemResource(candidate);
```

Đối với môi trường có symbolic link, cần xem xét `toRealPath()` và chính sách cho phép link. Chỉ kiểm tra chuỗi path bằng `startsWith` trước khi normalize có thể không đủ. Quy tắc bảo vệ phải phù hợp với filesystem và quyền chạy của process.

## 18. Những nhầm lẫn thường gặp

**Cho rằng classpath resource luôn là File.** Khi chạy từ JAR, resource có thể chỉ truy cập được qua stream. Dùng `getInputStream()` hoặc truyền `Resource` cho reader.

**Đưa `src/main/resources` vào đường dẫn runtime.** Runtime classpath bắt đầu từ nội dung được copy bên trong thư mục resources, ví dụ `data/orders.csv`.

**Dùng đường dẫn tương đối mà không biết working directory.** Kết quả có thể khác giữa IDE, service, container và scheduler. Cấu hình base directory hoặc path tuyệt đối.

**Dùng ClassPathResource cho file đầu vào được thay đổi hằng ngày.** File đóng gói trong artifact không phù hợp cho upstream thay nội dung độc lập. Dùng filesystem resource hoặc storage phù hợp.

**Cho rằng Resource tự kiểm tra định dạng nội dung.** Resource chỉ mô tả nguồn. Reader vẫn cần encoding, delimiter, schema và validation.

**Cho rằng `@StepScope` tự bảo đảm restart.** Scope quản lý vòng đời bean; reader cần `ItemStream`/`saveState` và nguồn dữ liệu ổn định để khôi phục checkpoint.

**Gọi `getFile()` trên resource bất kỳ.** Không phải mọi resource có file vật lý. Dùng stream nếu chỉ cần đọc.

**Cho phép JobParameter tùy ý trỏ đến mọi path.** Hãy giới hạn thư mục, scheme và quyền truy cập theo yêu cầu ứng dụng.

## 19. Kiểm thử resource trong các môi trường chạy

Resource có thể hoạt động trong IDE nhưng thất bại sau khi đóng gói. Vì vậy, nên kiểm thử ít nhất các tình huống:

1. Đọc classpath resource từ test/runtime classpath.
2. Đóng gói ứng dụng thành JAR và xác nhận reader đọc được resource nằm trong JAR mà không gọi `getFile()`.
3. Đọc filesystem resource bằng đường dẫn tuyệt đối trong môi trường triển khai tương tự production.
4. Kiểm tra file không tồn tại, không có quyền đọc và thư mục bị cấu hình sai.
5. Kiểm tra path có `..`, path tuyệt đối ngoài thư mục cho phép và symbolic link theo chính sách bảo mật.
6. Kiểm tra encoding, delimiter, header và dữ liệu tiếng Việt/ký tự đặc biệt.
7. Restart Job sau khi một số chunk đã commit và xác nhận file đầu vào không bị thay đổi, reader khôi phục đúng checkpoint.
8. Thay đổi file giữa hai lần chạy thử để xác nhận cơ chế checksum/version hoặc validation phát hiện nội dung không còn giống ban đầu.

Với classpath resource, integration test chạy từ packaged JAR giúp phát hiện lỗi phụ thuộc `getFile()` mà test trong IDE có thể bỏ sót. Với filesystem, test nên dùng thư mục tạm hoặc fixture được tạo rõ ràng để không phụ thuộc working directory của máy developer.

## 20. Cách chọn Resource cho batch job

Hãy chọn `ClassPathResource` cho dữ liệu được phát hành cùng ứng dụng và không cần thay đổi độc lập sau khi build, chẳng hạn file mẫu hoặc template. Chọn `FileSystemResource` cho file đầu vào/đầu ra được quản lý bên ngoài, thay đổi theo từng lần chạy hoặc cần lưu checkpoint/restart trên máy chủ.

Dùng `Resource` abstraction để reader không phụ thuộc trực tiếp vào cách mở file. Dùng `classpath:` và `file:` khi cần phân giải location rõ ràng; tránh dựa vào đường dẫn tương đối không xác định. Không gọi `getFile()` nếu resource có thể nằm trong JAR. Kiểm tra tồn tại, quyền đọc, encoding và path được phép trước khi chạy.

Với Spring Batch, resource còn gắn với khả năng restart: giữ ổn định tên reader, JobParameters và nội dung nguồn; bật lưu state khi cần; không thay file giữa lúc Job đang dở. Khi tách rõ resource đóng gói trong classpath với file bên ngoài filesystem, batch job sẽ chạy nhất quán hơn giữa môi trường phát triển, JAR và production.
