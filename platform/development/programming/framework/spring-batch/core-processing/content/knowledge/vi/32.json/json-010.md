# Restart JSON reader

Trong Spring Batch, `JsonItemReader` đọc từng object từ một tài liệu JSON có dạng mảng. Reader có thể lưu trạng thái đọc vào `ExecutionContext`, nhờ đó Step có thể tiếp tục ở vị trí đã commit khi Job được restart. Để cơ chế này đáng tin cậy, cần giữ nguyên file đầu vào, tên Reader, thứ tự item và identifying JobParameters giữa các lần chạy.

Restart JSON reader không có nghĩa parser tự sửa được file JSON hỏng. Nếu tài liệu không hợp lệ hoặc file bị thay đổi giữa hai lần chạy, checkpoint cũ có thể không còn trỏ đến đúng item. Vì vậy, cần kết hợp `saveState`, `JobRepository`, transaction boundary theo chunk và dữ liệu nguồn bất biến.

## 1. JsonItemReader đọc dữ liệu như thế nào?

`JsonItemReader<T>` là `ItemReader` dành cho JSON. Reader sử dụng một `JsonObjectReader<T>` để phân tích từng object trong tài liệu và chuyển object đó thành kiểu Java `T`.

Định dạng đầu vào tiêu chuẩn là một JSON array chứa các object cùng kiểu:

```json
[
  {
    "orderId": "ORD-1001",
    "customerId": "CUST-01",
    "amount": 125.50
  },
  {
    "orderId": "ORD-1002",
    "customerId": "CUST-02",
    "amount": 89.90
  },
  {
    "orderId": "ORD-1003",
    "customerId": "CUST-03",
    "amount": 240.00
  }
]
```

Reader trả về từng object qua các lần gọi `read()`:

```text
orders.json
    |
    v
  JSON array
    |
    +--> object 1 -> Order
    +--> object 2 -> Order
    +--> object 3 -> Order
    |
    v
  ItemProcessor
    |
    v
  ItemWriter
```

Reader dùng API đọc JSON theo luồng thay vì phải tạo một collection chứa toàn bộ file trong memory. Điều này phù hợp với file lớn và chunk processing.

## 2. JsonObjectReader và các implementation

`JsonItemReader` tách việc quản lý luồng đọc và checkpoint khỏi thư viện parse JSON. Interface `JsonObjectReader<T>` đảm nhiệm việc mở nguồn, đọc object tiếp theo và đóng parser.

Spring Batch cung cấp các implementation phổ biến:

| Implementation | Thư viện parse | Khi phù hợp |
|---|---|---|
| `JacksonJsonObjectReader<T>` | Jackson | Ứng dụng đã sử dụng Jackson hoặc cần hệ sinh thái Jackson. |
| `GsonJsonObjectReader<T>` | Gson | Ứng dụng sử dụng Gson để ánh xạ JSON sang Java object. |

Ví dụ dùng Jackson:

```java
import org.springframework.batch.item.json.JacksonJsonObjectReader;

JacksonJsonObjectReader<Order> objectReader =
        new JacksonJsonObjectReader<>(Order.class);
```

`Order.class` là kiểu object mà mỗi phần tử trong JSON array sẽ được ánh xạ thành. Cấu trúc JSON và tên property cần tương thích với lớp đích hoặc được cấu hình bằng annotation/module của thư viện JSON.

## 3. Cấu hình JsonItemReader bằng builder

Với Spring Batch 5, có thể dùng `JsonItemReaderBuilder`:

```java
import org.springframework.batch.item.json.JsonItemReader;
import org.springframework.batch.item.json.JacksonJsonObjectReader;
import org.springframework.batch.item.json.builder.JsonItemReaderBuilder;
import org.springframework.core.io.FileSystemResource;

@Bean
public JsonItemReader<Order> orderJsonReader() {
    return new JsonItemReaderBuilder<Order>()
            .name("orderJsonReader")
            .resource(new FileSystemResource("/data/in/orders.json"))
            .jsonObjectReader(new JacksonJsonObjectReader<>(Order.class))
            .saveState(true)
            .build();
}
```

Các cấu hình chính:

- `name(...)`: tên Reader ổn định, được dùng để nhận diện state trong `ExecutionContext`.
- `resource(...)`: JSON resource cần đọc.
- `jsonObjectReader(...)`: strategy chuyển từng JSON object thành Java object.
- `saveState(true)`: cho phép lưu trạng thái đọc để restart.

Tên Reader phải duy trì ổn định giữa các lần chạy/restart của cùng Step. Nếu đổi tên, key state có thể thay đổi và Reader không còn khôi phục checkpoint cũ như dự kiến.

## 4. Đọc file động bằng JobParameters và @StepScope

Trong thực tế, file JSON thường được xác định khi launch Job. Có thể truyền đường dẫn bằng JobParameters rồi inject vào Reader qua SpEL:

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.json.JsonItemReader;
import org.springframework.batch.item.json.JacksonJsonObjectReader;
import org.springframework.batch.item.json.builder.JsonItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
public JsonItemReader<Order> orderJsonReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException("inputFile is required");
    }

    return new JsonItemReaderBuilder<Order>()
            .name("orderJsonReader")
            .resource(new FileSystemResource(inputFile))
            .jsonObjectReader(new JacksonJsonObjectReader<>(Order.class))
            .saveState(true)
            .build();
}
```

`@StepScope` trì hoãn việc tạo target Reader cho đến khi StepExecution bắt đầu. Khi đó, `jobParameters['inputFile']` đã có giá trị của JobExecution hiện tại. Điều này cũng giúp các Job chạy đồng thời với file khác nhau không ghi đè đường dẫn lên một Reader singleton dùng chung.

Khi launch Job:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/in/orders-2026-11-15.json", true)
        .toJobParameters();

jobLauncher.run(importOrdersJob, parameters);
```

Nếu cần restart, hãy dùng lại cùng identifying parameter `inputFile` và bảo đảm file tại đường dẫn đó vẫn là đúng phiên bản ban đầu.

## 5. Kiểu Java nhận từ JSON

Object reader ánh xạ JSON token sang property của lớp Java. Ví dụ:

```java
import java.math.BigDecimal;

public class Order {

    private String orderId;
    private String customerId;
    private BigDecimal amount;

    public String getOrderId() { return orderId; }
    public void setOrderId(String orderId) { this.orderId = orderId; }

    public String getCustomerId() { return customerId; }
    public void setCustomerId(String customerId) { this.customerId = customerId; }

    public BigDecimal getAmount() { return amount; }
    public void setAmount(BigDecimal amount) { this.amount = amount; }
}
```

JSON object có thể ánh xạ trực tiếp vào kiểu này nếu tên property phù hợp. Với identifier như `orderId`, nên giữ kiểu `String` để bảo toàn số 0 ở đầu. Với tiền tệ, dùng `BigDecimal` thay vì `double` để tránh sai số dấu phẩy động.

Nếu tên field trong JSON khác tên property Java, có thể dùng annotation của Jackson như `@JsonProperty`:

```java
@JsonProperty("order_id")
private String orderId;
```

Đối với `LocalDate`, `LocalDateTime` hoặc các kiểu Java Time, cần cấu hình Jackson module phù hợp (thường là `JavaTimeModule`) trong `ObjectMapper` được dùng bởi `JacksonJsonObjectReader`. Hãy thống nhất định dạng ngày giờ và timezone theo hợp đồng dữ liệu.

## 6. JSON array khác NDJSON

`JsonItemReader` được thiết kế để đọc một JSON array gồm các object. Nó không phải reader mặc định cho Newline Delimited JSON (NDJSON), trong đó mỗi dòng là một JSON document riêng.

JSON array:

```json
[
  {"id": "A-1", "amount": 10.5},
  {"id": "A-2", "amount": 20.0}
]
```

NDJSON:

```text
{"id":"A-1","amount":10.5}
{"id":"A-2","amount":20.0}
```

Với NDJSON, có thể dùng `FlatFileItemReader` đọc từng dòng rồi dùng Jackson `ObjectMapper` trong `LineMapper` hoặc `ItemProcessor` để chuyển từng dòng thành object. Không nên đưa NDJSON trực tiếp vào `JsonItemReader` và kỳ vọng nó tự nhận biết ranh giới mỗi dòng.

Nếu file có một root object chứa array lồng bên trong, ví dụ `{ "metadata": ..., "orders": [...] }`, cần một reader/adapter phù hợp để đi đến array `orders`, hoặc chuyển đổi file sang định dạng array mà `JsonItemReader` mong đợi. Không được giả định mọi JSON document đều là root array.

## 7. Checkpoint của JsonItemReader

`JsonItemReader` hỗ trợ `ItemStream` và lưu trạng thái đọc trong `ExecutionContext` khi `saveState(true)`. Reader dựa trên số lượng item đã đọc để khôi phục vị trí trong tài liệu khi restart.

Với chunk-oriented Step, checkpoint được lưu cùng metadata ở các ranh giới commit phù hợp:

```text
JobExecution #1
  JSON item 1..500    -> Chunk 1 COMMIT
  JSON item 501..1000 -> Chunk 2 COMMIT
  JSON item 1001..1500 -> Chunk 3 FAILED / ROLLBACK

ExecutionContext lưu trạng thái tại checkpoint đã commit
```

Khi restart, Reader mở lại resource và bỏ qua phần item đã được ghi nhận trong checkpoint, sau đó tiếp tục trả về item tiếp theo. Cách này cho phép xử lý JSON lớn mà không cần giữ toàn bộ array trong memory.

Các điều kiện để checkpoint có ý nghĩa:

- Reader có tên ổn định.
- `saveState(true)` được bật.
- JobRepository lưu metadata bền vững.
- Cùng JobInstance được restart bằng identifying JobParameters cũ.
- File JSON không bị sửa, thay thế hoặc sắp xếp lại.
- Step dùng Reader trực tiếp hoặc wrapper chuyển tiếp đầy đủ `ItemStream` lifecycle.

## 8. Restart sau khi một chunk thất bại

Giả sử Job đọc 10.000 order với commit interval 500. Hai chunk đầu đã commit, nhưng Writer gặp lỗi ở chunk thứ ba:

```text
Chunk 1: items 1-500       -> COMMIT
Chunk 2: items 501-1000    -> COMMIT
Chunk 3: items 1001-1500   -> ROLLBACK
                              |
                              v
                         Job FAILED
                              |
                              v
                    Restart cùng JobInstance
                              |
                              v
                    Reader khôi phục checkpoint
                              |
                              v
                    Đọc lại từ item 1001
```

Các thay đổi nghiệp vụ trong chunk đã commit được giữ lại. Chunk thất bại có thể được đọc và xử lý lại vì checkpoint chỉ phản ánh trạng thái commit trước đó.

Writer vì vậy cần idempotent. Ví dụ, dùng unique constraint theo `sourceOrderId` và upsert theo quy tắc nghiệp vụ để item được thử lại không tạo bản ghi trùng.

## 9. Restart bằng JobLauncher với cùng JobParameters

Restart đúng JobInstance yêu cầu giữ nguyên identifying JobParameters. Ví dụ:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/in/orders-2026-11-15.json", true)
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();

JobExecution execution = jobLauncher.run(importOrdersJob, parameters);
```

Nếu JobExecution trước đó là `FAILED` hoặc `STOPPED` và Job/Step cho phép restart, lần launch tiếp theo với cùng identifying parameters có thể tạo JobExecution mới cho cùng JobInstance.

Không thêm timestamp hoặc UUID mới làm identifying parameter chỉ để gọi Job lại. Làm như vậy sẽ tạo JobInstance mới và Reader bắt đầu một đơn vị công việc mới thay vì khôi phục checkpoint cũ.

## 10. Reader và Step phải tham gia ItemStream lifecycle

Spring Batch quản lý `open`, `update` và `close` cho các thành phần `ItemStream` được đăng ký trong Step. Khi `JsonItemReader` được khai báo trực tiếp qua `.reader(reader)`, Step có thể quản lý lifecycle của nó.

Nếu Reader được bọc bởi một custom reader/decorator, wrapper phải chuyển tiếp `ItemStream` hoặc delegate cần được đăng ký rõ ràng:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, ProcessedOrder>chunk(500, transactionManager)
        .reader(customReader)
        .writer(orderWriter)
        .stream(delegateJsonReader)
        .build();
```

Ví dụ này giả định `customReader` không tự chuyển tiếp lifecycle tới `delegateJsonReader`. Nếu wrapper đã implement `ItemStream` và chuyển tiếp `open`, `update`, `close`, không đăng ký delegate lần thứ hai. Nếu lifecycle không được gọi, checkpoint của JSON reader có thể không được lưu hoặc khôi phục đúng.

## 11. JSON file phải bất biến qua restart

Checkpoint của JSON reader dựa trên vị trí item trong tài liệu. Nếu file thay đổi giữa hai lần chạy, cùng một vị trí có thể trỏ đến object khác.

Ví dụ:

```text
Lần đầu:
  item 1 = ORD-1001
  item 2 = ORD-1002
  item 3 = ORD-1003
  checkpoint = sau item 2

File bị thay đổi:
  item 1 = ORD-1000 (được chèn thêm)
  item 2 = ORD-1001
  item 3 = ORD-1002
  item 4 = ORD-1003

Restart tại vị trí cũ có thể bỏ qua/đọc lại sai record.
```

Để tránh:

1. Producer ghi file tạm, đóng file rồi publish tên chính thức.
2. Job chỉ đọc file đã hoàn tất.
3. Lưu checksum, kích thước hoặc object version của file khi nhận batch.
4. Không sửa file input trong suốt vòng đời JobInstance.
5. Nếu producer gửi phiên bản mới, dùng file version mới và identifying parameter mới để tạo JobInstance mới.

Giữ nguyên đường dẫn nhưng thay nội dung không đủ để bảo đảm restart đúng. Cần bảo đảm cả bytes của resource ổn định.

## 12. Lỗi JSON giữa chừng và giới hạn của skip

JSON syntax error khác với lỗi nghiệp vụ của một object đã parse thành công.

| Loại lỗi | Ví dụ | Hành vi phù hợp |
|---|---|---|
| JSON không hợp lệ | Thiếu `]`, thiếu `}`, dấu phẩy thừa, string chưa đóng | Dừng xử lý file, cách ly và yêu cầu file đúng. |
| File bị truncate | File kết thúc giữa object hoặc trước dấu đóng array | Xem file chưa hoàn chỉnh; nhận lại file. |
| Object hợp lệ nhưng thiếu dữ liệu nghiệp vụ | `amount` null hoặc `orderId` rỗng | Validate trong Processor; skip/reject nếu cho phép. |
| Giá trị không đúng quy tắc nghiệp vụ | `amount` âm hoặc trạng thái không hỗ trợ | Ném exception nghiệp vụ và áp dụng skip policy phù hợp. |
| Lỗi ghi đích | Deadlock hoặc constraint violation | Retry/fail theo chính sách Writer và transaction. |

Nếu JSON syntax bị hỏng ở giữa array, parser có thể không xác định được ranh giới object tiếp theo. Cấu hình `.skip(...)` cho exception parse không tự khôi phục trạng thái parser để tiếp tục an toàn. Khi restart cùng file hỏng, Reader thường gặp lại lỗi tại vùng chưa commit.

Nếu yêu cầu là tiếp tục sau từng record lỗi, hãy dùng NDJSON hoặc mỗi object một file/message độc lập, nơi có ranh giới record rõ ràng. Với JSON array chuẩn, lỗi cú pháp ở giữa thường nên làm file thất bại toàn bộ.

## 13. JSON array lồng nhau và schema không đồng nhất

`JsonItemReader` đọc các object ở cấp array được cấu hình. Nếu một JSON object có cấu trúc phức tạp, object reader có thể ánh xạ toàn bộ nested structure vào một DTO:

```json
[
  {
    "orderId": "ORD-2001",
    "customer": {
      "id": "CUST-01",
      "name": "An Nguyen"
    },
    "lines": [
      {"sku": "SKU-01", "quantity": 2},
      {"sku": "SKU-02", "quantity": 1}
    ]
  }
]
```

Mỗi item vẫn là một order; `customer` và `lines` được ánh xạ thành nested object/list trong DTO. Nếu các phần tử trong array có schema khác nhau, cần dùng kiểu chung phù hợp, polymorphic mapping có kiểm soát hoặc custom `JsonObjectReader`. Không nên ép mọi object thành một DTO rồi bỏ qua field không hiểu mà không có chính sách schema version.

Nếu chỉ cần đọc một nested array bên trong root object, hãy dùng custom reader hoặc chuyển đổi đầu vào trước. `JsonItemReader` không tự suy luận tên nested property cần được dùng làm danh sách item.

## 14. Skip lỗi nghiệp vụ sau khi JSON object đã được parse

Một object JSON hợp lệ có thể chứa dữ liệu không hợp lệ. Nên để parser chuyển nó thành DTO, sau đó kiểm tra quy tắc nghiệp vụ trong Processor:

```java
import java.math.BigDecimal;

import org.springframework.batch.item.ItemProcessor;

public class OrderProcessor
        implements ItemProcessor<Order, ProcessedOrder> {

    @Override
    public ProcessedOrder process(Order order) {
        if (order.getOrderId() == null || order.getOrderId().isBlank()) {
            throw new InvalidOrderException("orderId is required");
        }

        BigDecimal amount = order.getAmount();
        if (amount == null || amount.signum() < 0) {
            throw new InvalidOrderException("amount must be non-negative");
        }

        return new ProcessedOrder(order.getOrderId(), amount);
    }
}
```

Có thể cấu hình Step fault-tolerant:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, ProcessedOrder>chunk(500, transactionManager)
        .reader(orderJsonReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(100)
        .listener(orderSkipListener)
        .build();
```

Đây là skip lỗi nghiệp vụ sau khi object đã được parse. Nếu lỗi xảy ra trong JSON syntax hoặc parser state đã hỏng, không nên dùng cùng policy này với kỳ vọng Reader tiếp tục đọc phần còn lại.

## 15. Kiểm thử restart JSON reader

Kiểm thử restart nên xác nhận cả metadata và dữ liệu nghiệp vụ. Một test chỉ kiểm tra Job `COMPLETED` chưa đủ để phát hiện record bị thiếu hoặc trùng.

Kịch bản integration test:

1. Tạo JSON array có số lượng object biết trước và lưu thành file bất biến trong thư mục tạm.
2. Launch Job với identifying parameter trỏ tới file đó.
3. Làm Writer thất bại có kiểm soát sau khi một vài chunk đã commit.
4. Xác nhận JobExecution đầu tiên `FAILED` và dữ liệu target chỉ chứa các chunk đã commit.
5. Khắc phục điều kiện Writer rồi restart cùng JobInstance bằng đúng identifying parameters.
6. Xác nhận Reader tiếp tục sau checkpoint, các object chưa commit được xử lý và Job hoàn tất.
7. Kiểm tra mỗi business key chỉ xuất hiện một lần ở target.

Với Spring Batch Test, `JobLauncherTestUtils` hỗ trợ launch Job; `JobExplorer`/`JobRepository` dùng để tra cứu JobInstance, JobExecution và StepExecution. Có thể dùng một Writer/service test double để gây lỗi ở chunk xác định rồi chuyển sang chế độ thành công cho lần restart.

Ví dụ assertion kiểm tra không ghi trùng:

```java
Integer count = jdbcTemplate.queryForObject(
        "select count(*) from imported_order where source_order_id = ?",
        Integer.class,
        "ORD-1001");

assertEquals(1, count);
```

Khi kiểm tra restart, JobInstance ID của lần chạy thứ hai phải giống lần đầu, còn JobExecution ID phải khác. Nếu tạo UUID identifying mới ở lần thứ hai, test đã tạo instance mới và không còn kiểm tra checkpoint của Reader cũ.

## 16. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng JsonItemReader cho NDJSON | Reader kỳ vọng JSON array, không phải một JSON document mỗi dòng. | Dùng FlatFileItemReader và parse từng dòng. |
| File không có root array | Reader không thể đọc theo định dạng mong đợi. | Chuyển đổi file hoặc dùng custom reader cho nested array. |
| Tên Reader thay đổi khi restart | Checkpoint cũ có thể không được tìm thấy. | Giữ `name(...)` ổn định. |
| Tắt `saveState` nhưng kỳ vọng restart | Reader không lưu checkpoint chuẩn. | Bật `saveState(true)` hoặc tự quản lý state. |
| File JSON bị thay đổi sau checkpoint | Item count có thể trỏ đến object khác. | Giữ file immutable, lưu checksum/version. |
| Thêm identifying UUID khi restart | Tạo JobInstance mới và đọc lại từ đầu. | Dùng lại identifying JobParameters cũ. |
| Skip JSON parser exception để tiếp tục | Parser có thể không thể resynchronize sau syntax error. | Cách ly file hoặc đổi format sang record độc lập. |
| Writer không idempotent | Chunk rollback/restart có thể tạo bản ghi trùng. | Unique constraint, upsert và business key. |
| Wrapper không chuyển tiếp ItemStream | Checkpoint không được lưu/khôi phục đúng. | Chuyển tiếp lifecycle hoặc đăng ký `.stream(delegate)`. |

## Kết luận

`JsonItemReader` đọc từng object trong một JSON array thông qua `JsonObjectReader`, chẳng hạn `JacksonJsonObjectReader`. Khi `saveState(true)` và `ItemStream` lifecycle được quản lý đúng, Reader lưu số item đã đọc trong `ExecutionContext` để tiếp tục sau checkpoint đã commit. Để restart an toàn, giữ tên Reader, identifying JobParameters và nội dung file ổn định; Writer cũng cần idempotent vì chunk chưa commit có thể được xử lý lại. Dùng `JsonItemReader` cho JSON array, chọn reader line-oriented cho NDJSON và xem syntax error giữa tài liệu là lỗi file cần sửa/cách ly thay vì một item có thể skip an toàn.
