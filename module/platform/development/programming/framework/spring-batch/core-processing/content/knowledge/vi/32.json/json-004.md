# JsonItemWriter

Trong Spring Batch, writer tích hợp để ghi item thành JSON file có tên lớp là `JsonFileItemWriter<T>`. Nhiều ứng dụng gọi ngắn gọn chức năng này là JSON item writer hoặc `JsonItemWriter`. `JsonFileItemWriter` nhận các item từ chunk, dùng một `JsonObjectMarshaller<T>` chuyển từng object thành JSON text rồi ghi kết quả vào resource đích.

Writer này phù hợp khi Job cần xuất dữ liệu thành một tài liệu JSON, ví dụ danh sách đơn hàng, khách hàng, giao dịch hoặc kết quả đồng bộ. Cần phân biệt writer ghi JSON với writer ghi từng dòng JSON độc lập (JSON Lines/NDJSON): định dạng đầu ra và cách consumer đọc file phải thống nhất ngay từ đầu.

## 1. JsonFileItemWriter hoạt động như thế nào?

Trong chunk-oriented Step, reader tạo item, processor có thể biến đổi item, rồi writer ghi các item đầu ra. `JsonFileItemWriter` nhận một chunk và marshal từng item thành JSON.

Luồng xử lý:

```text
ItemReader<Order>
       |
       v
ItemProcessor<Order, OrderExport>
       |
       v
Chunk<OrderExport>
       |
       v
JsonFileItemWriter<OrderExport>
       |
       +--> JsonObjectMarshaller
       |       |
       |       +--> JSON text cho từng object
       |
       v
Output Resource
```

Writer tập trung vào việc chuyển object thành biểu diễn JSON và ghi vào file. Việc chọn item nào được xuất, lọc dữ liệu, chuẩn hóa field hoặc áp dụng quy tắc nghiệp vụ nên nằm ở reader/processor hoặc service phù hợp.

Trong Spring Batch, tên API built-in là `JsonFileItemWriter`; nếu dự án có class tự viết tên `JsonItemWriter`, cần xem hợp đồng của class đó. Các ví dụ dưới đây dùng API chuẩn `JsonFileItemWriter` của Spring Batch.

## 2. JSON array và JSON Lines

Trước khi cấu hình writer, hãy xác định consumer mong đợi định dạng nào.

**JSON document dạng array** chứa một mảng JSON với nhiều object:

```json
[
  {"orderId": 1001, "amount": 250000},
  {"orderId": 1002, "amount": 175000},
  {"orderId": 1003, "amount": 99000}
]
```

Đây là dạng tài liệu JSON thông thường: toàn bộ file là một JSON value, cụ thể là array. `JsonFileItemWriter` được thiết kế để ghi các object item thành một JSON array.

**JSON Lines (NDJSON)** có một JSON value trên mỗi dòng, không có dấu ngoặc array bao ngoài:

```text
{"orderId":1001,"amount":250000}
{"orderId":1002,"amount":175000}
{"orderId":1003,"amount":99000}
```

JSON Lines thường phù hợp với pipeline streaming hoặc hệ thống đọc từng record theo dòng. Không nên đổi một file JSON array thành JSON Lines chỉ bằng cách thay dấu xuống dòng; cần writer và consumer cùng thống nhất format. Nếu đích yêu cầu NDJSON, hãy dùng writer phù hợp hoặc triển khai `ItemWriter` riêng thay vì giả định `JsonFileItemWriter` tự tạo NDJSON.

## 3. JsonObjectMarshaller

`JsonFileItemWriter` không tự quyết định mọi chi tiết serialization của object. Nó sử dụng `JsonObjectMarshaller<T>` để chuyển một item thành chuỗi JSON.

Hợp đồng cơ bản của marshaller:

```java
public interface JsonObjectMarshaller<T> {
    String marshal(T object) throws Exception;
}
```

Marshaller quyết định cách ánh xạ object sang JSON, ví dụ:

- Tên property trong JSON.
- Cách biểu diễn ngày giờ và timezone.
- Cách biểu diễn enum.
- Xử lý `null`.
- Định dạng số thập phân.
- Nested object và collection.
- Các field bị loại khỏi output.
- Custom serializer cho kiểu dữ liệu đặc biệt.

Tách marshalling khỏi file writing giúp ứng dụng thay đổi thư viện JSON hoặc quy tắc serialization mà không phải tự viết lại toàn bộ cơ chế quản lý file/checkpoint của Spring Batch.

## 4. Dùng JacksonJsonObjectMarshaller

Spring Batch cung cấp `JacksonJsonObjectMarshaller<T>` để dùng Jackson chuyển object thành JSON. Ví dụ:

```java
@Bean
JacksonJsonObjectMarshaller<OrderExport> orderJsonMarshaller() {
    return new JacksonJsonObjectMarshaller<>();
}
```

Model đầu ra:

```java
public record OrderExport(
        Long orderId,
        String customerId,
        BigDecimal amount,
        String currency) {
}
```

Khi marshal một `OrderExport`, Jackson tạo object JSON với các property tương ứng, ví dụ:

```json
{
  "orderId": 1001,
  "customerId": "C001",
  "amount": 250000.00,
  "currency": "VND"
}
```

Đầu ra cụ thể phụ thuộc model, Jackson version và cấu hình mapper được sử dụng. Nếu hợp đồng JSON yêu cầu tên field, format ngày giờ hoặc xử lý null chính xác, hãy cấu hình/kiểm thử marshaller theo hợp đồng đó thay vì dựa vào giá trị mặc định.

## 5. Cấu hình JsonFileItemWriterBuilder

Với Spring Batch 5, có thể tạo writer bằng `JsonFileItemWriterBuilder`:

```java
@Bean
@StepScope
JsonFileItemWriter<OrderExport> orderJsonWriter(
        @Value("#{jobParameters['output.file']}") String outputFile,
        JacksonJsonObjectMarshaller<OrderExport> orderJsonMarshaller) {

    return new JsonFileItemWriterBuilder<OrderExport>()
            .name("orderJsonWriter")
            .resource(new FileSystemResource(outputFile))
            .jsonObjectMarshaller(orderJsonMarshaller)
            .saveState(true)
            .build();
}
```

Các cấu hình quan trọng:

- `name`: tên writer ổn định, được dùng trong metadata/checkpoint.
- `resource`: file hoặc resource đích.
- `jsonObjectMarshaller`: thành phần chuyển item thành JSON.
- `saveState(true)`: cho phép lưu state để hỗ trợ restart.

`@StepScope` cho phép resource được lấy từ JobParameters của execution hiện tại. Không tạo một writer singleton với đường dẫn output thay đổi theo từng lần chạy rồi lưu state dùng chung cho nhiều Job.

## 6. Gắn writer vào chunk Step

Writer có thể được dùng như một `ItemWriter` bình thường:

```java
@Bean
Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, OrderExport> orderProcessor,
        JsonFileItemWriter<OrderExport> orderJsonWriter) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<Order, OrderExport>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderJsonWriter)
            .build();
}
```

Với cấu hình này:

1. Reader lấy tối đa các item cần thiết cho chunk.
2. Processor chuyển từng `Order` thành `OrderExport`.
3. Writer marshal các item đầu ra và ghi vào JSON file.
4. Step commit chunk theo transaction manager đã cấu hình.

Chunk size là số item được xử lý trong một transaction; nó không phải số byte hoặc số ký tự JSON. Nếu mỗi object có nested collection lớn, một chunk nhỏ hơn có thể giúp kiểm soát bộ nhớ.

## 7. Tạo DTO dành riêng cho JSON output

Không nhất thiết phải serialize trực tiếp entity database. Một DTO dành cho export giúp kiểm soát hợp đồng JSON và tránh vô tình xuất field nội bộ.

Ví dụ entity nội bộ:

```java
public class Order {
    private Long id;
    private String customerId;
    private BigDecimal amount;
    private String internalStatus;
    private String paymentToken;
    // Other persistence fields
}
```

DTO export:

```java
public record OrderExport(
        Long orderId,
        String customerId,
        BigDecimal amount,
        String currency,
        LocalDate businessDate) {
}
```

Processor:

```java
@Bean
ItemProcessor<Order, OrderExport> orderExportProcessor() {
    return order -> new OrderExport(
            order.getId(),
            order.getCustomerId(),
            order.getAmount(),
            "VND",
            order.getBusinessDate());
}
```

DTO giới hạn rõ các field được xuất. Đây cũng là nơi thích hợp để đổi tên property, chuẩn hóa giá trị và tránh serialize credential, token, audit field hoặc quan hệ ORM không cần thiết.

## 8. Custom JsonObjectMarshaller

Nếu cần format JSON riêng, có thể triển khai `JsonObjectMarshaller<T>` và dùng thư viện JSON mà ứng dụng đã chọn.

Ví dụ với Jackson `ObjectMapper`:

```java
public class CustomOrderMarshaller
        implements JsonObjectMarshaller<OrderExport> {

    private final ObjectMapper objectMapper;

    public CustomOrderMarshaller(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public String marshal(OrderExport item) throws JsonProcessingException {
        return objectMapper.writeValueAsString(item);
    }
}
```

Đăng ký mapper và marshaller:

```java
@Bean
ObjectMapper exportObjectMapper() {
    return JsonMapper.builder()
            .findAndAddModules()
            .build();
}

@Bean
JsonObjectMarshaller<OrderExport> orderJsonMarshaller(
        ObjectMapper exportObjectMapper) {
    return new CustomOrderMarshaller(exportObjectMapper);
}
```

`findAndAddModules()` cho phép Jackson phát hiện module có trên classpath, ví dụ module hỗ trợ Java time nếu dependency tương ứng đã được thêm. Cấu hình thực tế cần khớp version Jackson và dependency của ứng dụng.

Custom marshaller nên stateless hoặc thread-safe nếu bean được dùng bởi nhiều execution. Không giữ mutable buffer dùng chung cho nhiều Job đồng thời.

## 9. Định dạng ngày giờ và timezone

Ngày giờ là phần dễ gây khác biệt giữa producer và consumer. Ví dụ `LocalDate` có thể được serialize thành chuỗi ISO như `2026-11-15`; `Instant` có thể được serialize với ký hiệu UTC `Z`.

Hợp đồng JSON nên quy định rõ:

- Ngày nghiệp vụ dùng `yyyy-MM-dd`.
- Thời điểm tuyệt đối dùng ISO-8601 có offset hoặc UTC.
- Múi giờ được ghi rõ nếu consumer cần diễn giải thời gian địa phương.
- Không serialize `LocalDateTime` rồi để consumer tự đoán timezone.
- Không thay đổi format giữa các lần export nếu consumer phụ thuộc schema cũ.

Ví dụ JSON:

```json
{
  "businessDate": "2026-11-15",
  "createdAt": "2026-11-15T02:30:00Z",
  "businessTimeZone": "Asia/Ho_Chi_Minh"
}
```

Nếu cần format tùy chỉnh, có thể dùng Jackson annotation như `@JsonFormat` hoặc serializer riêng. Kiểm thử bằng JSON thực tế để xác nhận đúng kiểu và timezone.

## 10. Null, enum và số thập phân

Các quy tắc serialization nên được quyết định theo hợp đồng dữ liệu:

| Kiểu Java | Câu hỏi cần xác định |
|---|---|
| `null` | Ghi property với giá trị `null`, bỏ property hay dùng giá trị thay thế? |
| Enum | Ghi tên enum, mã nghiệp vụ hay ordinal? |
| `BigDecimal` | Có giữ scale/precision và định dạng số theo JSON number không? |
| `Boolean` | Dùng `true`/`false` hay có mapping nghiệp vụ khác? |
| Collection rỗng | Ghi `[]`, `null` hay bỏ field? |
| Optional | Chuyển thành value, null hay bỏ field? |

Không nên dùng ordinal của enum làm hợp đồng lâu dài vì thứ tự enum có thể thay đổi khi code được cập nhật. Dùng mã chuỗi ổn định như `PENDING`, `APPROVED`, `REJECTED` hoặc một code được định nghĩa rõ.

Với tiền tệ, giữ `BigDecimal` thay vì `double` để tránh sai số dấu phẩy động. JSON number không mang thông tin currency, nên thường cần field `currency` riêng.

## 11. Nested object và collection

Jackson có thể serialize object graph thành JSON nested object/array. Ví dụ:

```java
public record OrderExport(
        Long orderId,
        CustomerExport customer,
        List<OrderLineExport> lines) {
}

public record CustomerExport(String customerId, String name) {
}

public record OrderLineExport(String sku, Integer quantity) {
}
```

JSON tương ứng:

```json
{
  "orderId": 1001,
  "customer": {
    "customerId": "C001",
    "name": "Lan"
  },
  "lines": [
    {"sku": "A-01", "quantity": 2},
    {"sku": "B-05", "quantity": 1}
  ]
}
```

Hãy kiểm soát kích thước object graph. Nếu mỗi item có hàng chục nghìn nested child, chunk writer có thể giữ nhiều object lớn trong bộ nhớ. Có thể cần tách export thành nhiều record hoặc thay đổi item boundary theo hợp đồng downstream.

Tránh serialize entity có quan hệ hai chiều không được kiểm soát. ORM proxy, lazy loading và vòng tham chiếu có thể gây query ngoài ý muốn, JSON đệ quy hoặc lỗi serialization. DTO export phẳng/nested có chủ đích thường dễ quản lý hơn.

## 12. Resource và thư mục output

`resource` xác định nơi writer ghi file. Trong ứng dụng thật, nên truyền đường dẫn output bằng JobParameters hoặc cấu hình môi trường đã validate.

Ví dụ:

```java
@Bean
@StepScope
JsonFileItemWriter<OrderExport> orderJsonWriter(
        @Value("#{jobParameters['output.file']}") String outputFile,
        JsonObjectMarshaller<OrderExport> marshaller) {

    Path outputPath = Path.of(outputFile).toAbsolutePath().normalize();
    return new JsonFileItemWriterBuilder<OrderExport>()
            .name("orderJsonWriter")
            .resource(new FileSystemResource(outputPath))
            .jsonObjectMarshaller(marshaller)
            .saveState(true)
            .build();
}
```

Trước khi chạy, cần xác định:

- Thư mục cha có tồn tại và process có quyền ghi không.
- Output path có nằm trong vùng được phép không.
- Hai Job đồng thời có thể ghi cùng một file không.
- File có cần giữ lại sau `FAILED`/`STOPPED` để restart không.
- File cuối có được consumer đọc ngay trong lúc đang ghi không.

Không nối chuỗi đường dẫn tùy ý từ input không tin cậy. Chuẩn hóa và kiểm tra path theo output root cấu hình.

## 13. Ghi đè và append

File output phải có chính sách rõ ràng khi đã tồn tại. Các tùy chọn builder liên quan đến file lifecycle có thể gồm `append(...)` và `shouldDeleteIfExists(...)` tùy phiên bản Spring Batch.

Các quyết định thường gặp:

- Tạo file mới cho một JobInstance mới.
- Tiếp tục output cũ khi restart cùng JobInstance và writer hỗ trợ checkpoint.
- Từ chối ghi nếu file đích đã tồn tại ngoài dự kiến.
- Ghi vào staging riêng rồi publish thành file cuối.

Append không đồng nghĩa có thể nối tùy ý hai JSON document hoàn chỉnh. Nếu file hiện tại là JSON array đã đóng bằng `]`, nối thêm một array khác sẽ tạo nội dung không phải một JSON document hợp lệ. Chỉ dùng append khi semantics của writer và trạng thái file được xác định rõ; không tự nối các JSON array bằng thao tác file thông thường.

`shouldDeleteIfExists` và `append` ảnh hưởng cách writer xử lý resource khi mở. Không bật xóa file khi restart nếu mục tiêu là khôi phục output đã ghi ở các chunk trước. Hãy kiểm tra defaults và hành vi chính xác của phiên bản đang dùng, đồng thời kiểm thử cả lần chạy đầu và restart.

## 14. Restart và saveState

`JsonFileItemWriter` là writer có thể lưu state thông qua cơ chế `ItemStream`. Khi `saveState(true)`, writer lưu thông tin cần thiết trong `ExecutionContext` để tiếp tục output sau checkpoint đã commit.

Các yếu tố cần giữ ổn định:

- Tên writer (`name`).
- Resource output path.
- Cấu hình marshaller và JSON schema.
- Cấu hình append/delete khi mở file.
- JobInstance và identifying JobParameters.
- Cách writer quản lý dấu phân cách và trạng thái JSON array.

Ví dụ, Job đã commit hai chunk và process bị kill trong chunk thứ ba. Khi restart, writer cần khôi phục output đến checkpoint cuối đã commit rồi tiếp tục ghi các item chưa hoàn tất. Nếu output file bị xóa hoặc thay thế giữa hai lần chạy, checkpoint có thể không còn khớp với nội dung file.

Không đổi writer name hoặc output path ngẫu nhiên mỗi lần restart. Dùng path ổn định theo JobInstance hoặc lưu path đã chọn trong metadata bền vững.

## 15. Transactional writing và rollback

Writer file không giống writer database. Transaction manager JDBC không tự tạo transaction nguyên tử với filesystem. `JsonFileItemWriter` có cơ chế quản lý ghi theo chunk và transaction-aware buffering để hỗ trợ rollback trong phạm vi writer, nhưng filesystem vẫn không phải XA resource tự động tham gia transaction JDBC.

Các tình huống cần phân biệt:

- Chunk rollback trước khi nội dung được flush/commit theo cơ chế writer: writer có thể bỏ phần dữ liệu chunk chưa commit.
- Chunk đã commit: output tương ứng được giữ.
- Process bị kill sau khi dữ liệu file được ghi nhưng trước khi metadata commit: nội dung file và checkpoint có thể không đồng bộ, tùy thời điểm flush/transaction.
- File được copy/publish sang hệ thống ngoài: database rollback không thu hồi bản copy đó.

Hãy kiểm thử failure/restart với filesystem và cấu hình writer thực tế. Không giả định một transaction JDBC có thể rollback mọi byte đã ghi ra file.

## 16. Staging file và publish output

Một mẫu an toàn là ghi JSON vào file staging, validate JSON sau khi writer hoàn tất, rồi đổi tên thành file chính thức.

```text
order-export.json.part
        |
        +--> JsonFileItemWriter ghi các chunk
        |
        +--> Writer đóng và hoàn tất JSON document
        |
        +--> Validate JSON + checksum
        |
        +--> Atomic move nếu filesystem hỗ trợ
        v
order-export.json
```

Ví dụ publish:

```java
Files.move(
        stagingPath,
        finalPath,
        StandardCopyOption.ATOMIC_MOVE);
```

Atomic move chỉ có thể bảo đảm trong phạm vi filesystem/provider hỗ trợ, thường cần staging và final cùng filesystem. Nó không tạo transaction chung với JobRepository. Process có thể chết sau khi move thành công nhưng trước khi Step ghi nhận hoàn tất; Publish Step nên idempotent bằng cách kiểm tra file cuối, checksum hoặc manifest.

Nếu Job thất bại trước publish, giữ staging khi restart cần tiếp tục writer. Nếu Job đã publish, cleanup staging thừa nhưng giữ file cuối theo retention.

## 17. JSON schema và versioning

JSON là định dạng dữ liệu, nhưng consumer vẫn cần một hợp đồng schema. Hãy quy định:

- Tên property và kiểu dữ liệu.
- Field bắt buộc và field tùy chọn.
- Cách biểu diễn null và collection rỗng.
- Ngày giờ, timezone, currency và precision.
- Giá trị enum/mã nghiệp vụ.
- Nested object và collection cardinality.
- Schema version và quy tắc tương thích.

Có thể đưa version vào mỗi item:

```json
{
  "schemaVersion": 2,
  "orderId": 1001,
  "amount": 250000.00,
  "currency": "VND"
}
```

Hoặc dùng manifest riêng cho toàn file. Nếu schema thay đổi, cần xác định consumer cũ có thể đọc field mới hay không, field bị xóa có phá tương thích không và Job restart của một JobInstance cũ có tiếp tục dùng marshaller/schema cũ không.

Không đổi tên property hoặc format date âm thầm giữa các lần deploy. Một Job restart sau nâng cấp có thể ghi phần đầu bằng schema cũ và phần sau bằng schema mới nếu cấu hình không được version hóa.

## 18. Kiểm tra JSON output

Sau khi Job ghi file, nên kiểm tra output bằng parser JSON hoặc schema validator. Không chỉ kiểm tra file tồn tại và có kích thước lớn hơn 0.

Các kiểm tra hữu ích:

- File là JSON hợp lệ và parse được thành array nếu đó là hợp đồng.
- Số object đúng với số item được xuất, tính đến filter/skip.
- Mỗi object có các field bắt buộc và đúng type.
- Ngày giờ, số thập phân và enum đúng format.
- Không có field nội bộ/secret ngoài ý muốn.
- Nested collection không bị mất hoặc serialize sai.
- File không bị cắt cụt ở cuối sau lỗi/kill.
- Checksum và manifest khớp với output đã publish.

Nếu consumer yêu cầu JSON Schema, có thể validate file bằng schema validator ở một Step riêng trước khi publish. Validation nên diễn ra trên file staging đã đóng hoàn toàn.

## 19. Xử lý lỗi marshalling và ghi file

Exception có thể xảy ra khi:

- Object có kiểu không được serializer hỗ trợ.
- Property getter ném exception.
- Lazy association truy cập database ngoài ý muốn.
- Có vòng tham chiếu trong object graph.
- Không thể ghi file do permission denied hoặc disk full.
- Output path không tồn tại hoặc filesystem mất kết nối.
- JSON value không tuân thủ quy tắc serialization của ứng dụng.

Không nên skip mọi lỗi writer. Lỗi marshalling do một item có thể được xử lý theo chính sách dữ liệu nếu có thể xác định item lỗi và nghiệp vụ cho phép. Lỗi disk full, permission denied hoặc filesystem unavailable thường ảnh hưởng toàn bộ output và cần fail/retry có kiểm soát sau khi khôi phục hạ tầng.

Nếu cần reject item không serialize được, có thể validate/convert trong processor trước writer và ghi reject record riêng. Cách này giúp phân biệt lỗi dữ liệu của một item với lỗi tài nguyên output.

## 20. Bảo mật dữ liệu JSON

JSON output có thể chứa dữ liệu cá nhân, thông tin tài chính hoặc thông tin nội bộ. Cần kiểm soát:

- DTO chỉ xuất field cần thiết.
- Không serialize password, access token, secret hoặc internal credential.
- Thư mục output có permission phù hợp.
- File tạm và file staging có quyền truy cập tương tự file cuối.
- Nếu cần, mã hóa file khi lưu hoặc truyền theo chính sách hệ thống.
- Không log toàn bộ JSON payload của item nhạy cảm.
- Áp dụng retention và xóa an toàn theo yêu cầu lưu trữ.
- Kiểm soát ai có thể đọc file và manifest.

Không dựa vào `@JsonIgnore` duy nhất nếu có nhiều loại export khác nhau; DTO riêng cho từng hợp đồng thường dễ kiểm soát hơn entity dùng chung.

## 21. Kiểm thử JsonFileItemWriter

Nên kiểm thử cả marshaller, writer và tích hợp chunk Step.

### Unit test marshaller

```java
@Test
void marshalsOrderExportToExpectedJson() throws Exception {
    ObjectMapper mapper = JsonMapper.builder()
            .findAndAddModules()
            .build();
    JsonObjectMarshaller<OrderExport> marshaller =
            new CustomOrderMarshaller(mapper);

    String json = marshaller.marshal(new OrderExport(
            1001L, "C001", new BigDecimal("250000.00"),
            "VND", LocalDate.of(2026, 11, 15)));

    JsonNode node = mapper.readTree(json);
    assertThat(node.get("orderId").asLong()).isEqualTo(1001L);
    assertThat(node.get("customerId").asText()).isEqualTo("C001");
    assertThat(node.get("currency").asText()).isEqualTo("VND");
}
```

### Integration test writer

```java
@Test
void writesItemsAsJsonArray() throws Exception {
    Path output = tempDirectory.resolve("orders.json");

    JsonFileItemWriter<OrderExport> writer =
            new JsonFileItemWriterBuilder<OrderExport>()
                    .name("testOrderJsonWriter")
                    .resource(new FileSystemResource(output))
                    .jsonObjectMarshaller(new JacksonJsonObjectMarshaller<>())
                    .saveState(true)
                    .build();

    writer.open(new ExecutionContext());
    try {
        writer.write(new Chunk<>(List.of(
                new OrderExport(1001L, "C001",
                        new BigDecimal("250000.00"), "VND", null),
                new OrderExport(1002L, "C002",
                        new BigDecimal("175000.00"), "VND", null))));
    } finally {
        writer.close();
    }

    JsonNode root = objectMapper.readTree(output.toFile());
    assertThat(root.isArray()).isTrue();
    assertThat(root).hasSize(2);
    assertThat(root.get(0).get("orderId").asLong()).isEqualTo(1001L);
}
```

Test minh họa dùng `tempDirectory` và `objectMapper` đã được tạo trong test fixture. Tùy lifecycle của writer và cách gọi trực tiếp ngoài Step, cần khởi tạo writer theo đúng contract `ItemStream` và bảo đảm resource được đóng trước khi đọc file.

### Kiểm thử restart và transaction

Các tình huống nên kiểm tra:

- Writer ghi nhiều chunk và Job hoàn tất.
- Writer mở lại cùng resource sau restart và tiếp tục từ checkpoint.
- Chunk rollback không để lại item chưa commit theo semantics writer đã cấu hình.
- Process chết ở thời điểm ghi/commit và output được đối soát trước restart.
- Writer không xóa file output đã có ngoài dự kiến.
- Hai Job không ghi chung output path.
- File JSON cuối parse được và đúng schema.
- Publish Step chạy lại không tạo output trùng.

## 22. Những lỗi thường gặp

### Nhầm JsonItemWriter với JSON Lines

`JsonFileItemWriter` tạo JSON array. Nếu consumer cần NDJSON, dùng writer/format phù hợp và test từng dòng.

### Không cấu hình marshaller

Writer cần `JsonObjectMarshaller` để chuyển item thành JSON. Chọn Jackson hoặc custom marshaller theo hợp đồng output.

### Serialize entity database trực tiếp

Entity có thể chứa field nội bộ, lazy proxy hoặc vòng tham chiếu. Dùng DTO export giới hạn schema.

### Không giữ ổn định writer name/resource khi restart

Checkpoint có thể không khớp với file output. Giữ tên writer và path ổn định cho cùng JobInstance.

### Xóa file khi restart

Nếu writer xóa output cũ, dữ liệu của chunk đã commit có thể mất trong khi metadata vẫn giữ checkpoint. Xác nhận `append`/`shouldDeleteIfExists` theo semantics restart.

### Nối hai JSON array như nối text

Kết quả có thể không còn là JSON document hợp lệ. Xác định rõ append semantics hoặc tạo một output mới.

### Tin rằng JDBC rollback luôn rollback file

Filesystem không tự tham gia transaction JDBC. Dùng staging, kiểm tra trạng thái và publish idempotent.

### Không validate file trước publish

File có thể bị cắt cụt hoặc sai schema. Đóng writer, parse/validate JSON và kiểm tra checksum trước khi công bố.

### Bỏ qua lỗi disk full hoặc permission

Job có thể không tạo output hoàn chỉnh. Phân loại lỗi tài nguyên và xử lý retry/fail có kiểm soát.

### Để lộ field nhạy cảm

Jackson có thể serialize property không mong muốn. Dùng DTO và test JSON output để xác nhận field được phép.

## 23. Quy trình triển khai JsonFileItemWriter

Khi tạo một JSON export Job, có thể thực hiện theo trình tự:

1. Xác định consumer cần JSON array hay JSON Lines.
2. Định nghĩa schema JSON: field, type, null, date/time, enum và version.
3. Tạo DTO export chỉ chứa dữ liệu được phép công bố.
4. Chọn JacksonJsonObjectMarshaller hoặc custom `JsonObjectMarshaller`.
5. Cấu hình `JsonFileItemWriterBuilder` với name và resource ổn định.
6. Chọn `saveState` và file lifecycle phù hợp với restart.
7. Gắn writer vào chunk Step và chọn chunk size theo kích thước item.
8. Validate output path, permission và quyền truy cập dữ liệu.
9. Ghi vào staging nếu file chỉ được consumer đọc sau khi hoàn tất.
10. Đóng writer, parse/validate JSON và publish file.
11. Bảo đảm restart không xóa output đã commit hoặc tạo file sai format.
12. Kiểm thử marshaller, file array, rollback, restart, concurrency và lỗi filesystem.

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Ghi object thành JSON array | `JsonFileItemWriter<T>` |
| Chuyển object thành JSON | `JsonObjectMarshaller<T>` |
| Dùng Jackson | `JacksonJsonObjectMarshaller<T>` |
| Kiểm soát schema output | DTO export và custom marshaller/ObjectMapper |
| Output phụ thuộc JobParameters | `@StepScope` và `jobParameters['output.file']` |
| Restart output | `saveState(true)`, writer name/path ổn định |
| Consumer cần NDJSON | Writer JSON Lines riêng hoặc custom `ItemWriter` |
| Chỉ công bố file hoàn chỉnh | Staging, validation và publish idempotent |

## Kết luận

Trong Spring Batch, API writer chuẩn để xuất item thành JSON file là `JsonFileItemWriter<T>`, thường được cấu hình bằng `JsonFileItemWriterBuilder` và một `JsonObjectMarshaller<T>`. Writer marshal từng item thành JSON object và tạo tài liệu JSON dạng array; nếu consumer cần JSON Lines, cần chọn writer/format riêng. Hãy dùng DTO export, định nghĩa schema rõ ràng, cấu hình Jackson hoặc custom marshaller, giữ resource và writer name ổn định khi restart, đồng thời hiểu file lifecycle và giới hạn transaction của filesystem. Với output quan trọng, ghi vào staging, đóng và validate JSON rồi publish idempotent để tránh consumer đọc file dở dang hoặc restart tạo dữ liệu không nhất quán.
