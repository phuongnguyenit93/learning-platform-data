# Serialize context vào repository

Spring Batch dùng ExecutionContext để lưu trạng thái cần thiết cho việc tiếp tục một Job hoặc Step sau khi bị dừng hay thất bại. Khi trạng thái này được lưu qua JobRepository, framework phải chuyển các cặp key/value trong context thành dạng dữ liệu có thể ghi vào metadata repository. Quá trình chuyển đổi đó được gọi là serialization.

Serialization là một phần của cơ chế lưu metadata, không phải thao tác mà ứng dụng cần tự thực hiện mỗi lần gọi put(). Ứng dụng cập nhật ExecutionContext; Spring Batch quản lý thời điểm persist và dùng một ExecutionContextSerializer để chuyển nội dung context sang dạng lưu trữ. Khi cần khôi phục, repository đọc dữ liệu đã lưu và serializer chuyển nó trở lại thành các giá trị trong context.

Hiểu rõ cơ chế này giúp chọn kiểu dữ liệu phù hợp, cấu hình serializer đúng phiên bản, tránh lỗi khi restart và kiểm soát kích thước cũng như độ nhạy cảm của metadata.

## 1. ExecutionContext được lưu ở đâu?

Spring Batch có hai phạm vi ExecutionContext:

- **Step ExecutionContext** thuộc về một StepExecution. Nó thường lưu trạng thái riêng của reader, writer hoặc logic trong Step, chẳng hạn vị trí đọc tiếp theo hay khóa cuối cùng đã xử lý.
- **Job ExecutionContext** thuộc về một JobExecution. Nó dùng để chia sẻ một lượng metadata nhỏ giữa các Step trong cùng lần thực thi Job.

Với JDBC JobRepository, Spring Batch lưu các context trong các bảng metadata riêng:

| Phạm vi | Bảng JDBC repository thường gặp |
|---|---|
| Job ExecutionContext | BATCH_JOB_EXECUTION_CONTEXT |
| Step ExecutionContext | BATCH_STEP_EXECUTION_CONTEXT |

Tên bảng và schema có thể thay đổi theo cấu hình prefix hoặc phiên bản. Mỗi bảng lưu thông tin liên kết đến execution tương ứng cùng biểu diễn đã serialize của context.

ExecutionContext trong bộ nhớ là một cấu trúc key/value. Ví dụ:

~~~java
ExecutionContext context = stepExecution.getExecutionContext();

context.putLong("customerReader.lastId", 8500L);
context.putString("input.fileVersion", "orders-v4");
context.putInt("page.number", 12);
~~~

Các giá trị trên được cập nhật trong context của Step. Khi Spring Batch lưu context qua JobRepository, serializer chuyển chúng sang dạng lưu trữ. Ở lần restart, framework nạp context tương ứng và reader hoặc writer có thể dùng các giá trị đó để khôi phục trạng thái.

Không nên coi ExecutionContext là một cache tùy ý hoặc kho lưu toàn bộ dữ liệu nghiệp vụ. Nó phục vụ metadata và checkpoint cần thiết cho vòng đời Batch.

## 2. Serialization diễn ra khi nào?

Lệnh put() chỉ cập nhật context đang được giữ trong bộ nhớ. Nó không có nghĩa dữ liệu đã được ghi ngay xuống database tại dòng code đó.

Spring Batch quản lý việc persist context trong vòng đời execution. Với chunk-oriented Step, framework phối hợp cập nhật trạng thái stream và lưu checkpoint ở ranh giới chunk cùng quy trình quản lý transaction. Job context cũng được lưu qua JobRepository trong quá trình cập nhật JobExecution theo vòng đời Job và Step.

Luồng khái quát:

~~~text
Reader / Writer / Step logic
          |
          | put(key, value)
          v
ExecutionContext trong bộ nhớ
          |
          | framework cập nhật execution
          v
JobRepository
          |
          | ExecutionContextSerializer
          v
Dạng dữ liệu đã serialize
          |
          v
Metadata database
~~~

Khi đọc lại:

~~~text
Metadata database
          |
          | dữ liệu đã serialize
          v
ExecutionContextSerializer
          |
          v
ExecutionContext được khôi phục
          |
          v
Reader / Writer tiếp tục từ checkpoint
~~~

Ứng dụng thông thường không cần tự gọi serializer hoặc tự ghi các bảng BATCH_*. Hãy cập nhật context qua API của ExecutionContext và để Spring Batch quản lý việc lưu, khôi phục.

Nếu ứng dụng gọi put() rồi lập tức truy vấn database trong cùng đoạn code, không nên giả định giá trị đã được persist ngay. Thời điểm lưu phụ thuộc lifecycle của JobRepository và transaction hiện tại.

## 3. ExecutionContextSerializer là gì?

ExecutionContextSerializer là abstraction chịu trách nhiệm chuyển dữ liệu context sang dạng có thể ghi và khôi phục lại từ repository.

Về mặt khái niệm, serializer thực hiện hai chiều:

- **Serialize:** nhận các key/value trong context và ghi ra một representation, thường là chuỗi hoặc luồng byte.
- **Deserialize:** đọc representation đó và tạo lại các key/value để khôi phục context.

Spring Batch cung cấp serializer mặc định và cho phép cấu hình serializer khác. Implementation cụ thể và serializer mặc định có thể khác theo phiên bản Spring Batch cũng như cách ứng dụng tạo JobRepository.

Vì vậy, khi thay đổi phiên bản framework hoặc cấu hình repository, cần xác định serializer thực sự đang được dùng. Không nên suy luận serializer chỉ từ việc ứng dụng dùng JDBC hay từ tên cột trong database.

### Java serialization

Một serializer dựa trên Java Object Serialization có thể lưu các object đáp ứng yêu cầu Serializable. Khi deserialize, JVM phải có thể tìm thấy class tương ứng và khôi phục object graph.

Ưu điểm là có thể lưu một số kiểu object Java trực tiếp mà không cần tự chuyển từng trường thành chuỗi. Tuy nhiên, cách này tạo phụ thuộc vào class và cấu trúc object của ứng dụng. Khi class thay đổi giữa hai lần triển khai, dữ liệu cũ có thể không deserialize được.

### Serializer dựa trên JSON

Một serializer dựa trên JSON chuyển context thành representation dạng văn bản. Cách này có thể giúp dữ liệu dễ quan sát và hỗ trợ nhiều kiểu dữ liệu thông dụng, tùy serializer và cấu hình mapping.

JSON không tự động giải quyết mọi vấn đề tương thích. Kiểu dữ liệu phức tạp, polymorphism, ngày giờ, enum và object tùy chỉnh vẫn cần quy tắc serialize/deserialize rõ ràng. Cấu hình type metadata không an toàn có thể mở rộng bề mặt rủi ro khi deserialize dữ liệu không đáng tin cậy.

### Serializer tùy chỉnh

Ứng dụng có thể cung cấp implementation riêng nếu có yêu cầu đặc biệt về format, tương thích hoặc tích hợp. Khi làm vậy, cần bảo đảm serializer có thể đọc lại mọi context đã ghi theo format tương ứng và có kế hoạch tương thích khi triển khai phiên bản mới.

Không chọn serializer chỉ vì format nhìn dễ đọc. Điều quan trọng là khả năng round-trip, tương thích qua restart, an toàn khi deserialize và vận hành metadata lâu dài.

## 4. Cấu hình serializer cho JobRepository

Khi tự cấu hình JDBC repository bằng JobRepositoryFactoryBean, có thể chỉ định serializer thông qua cấu hình repository.

Ví dụ minh họa phần cấu hình liên quan:

~~~java
@Bean
ExecutionContextSerializer executionContextSerializer() {
    return new DefaultExecutionContextSerializer();
}

@Bean
JobRepository jobRepository(
        DataSource dataSource,
        PlatformTransactionManager transactionManager,
        ExecutionContextSerializer executionContextSerializer) throws Exception {

    JobRepositoryFactoryBean factory = new JobRepositoryFactoryBean();
    factory.setDataSource(dataSource);
    factory.setTransactionManager(transactionManager);
    factory.setSerializer(executionContextSerializer);

    // Các thuộc tính repository khác được cấu hình theo ứng dụng.
    factory.afterPropertiesSet();
    return factory.getObject();
}
~~~

Đây là ví dụ theo kiểu cấu hình JDBC repository; cần điều chỉnh theo phiên bản Spring Batch, cách ứng dụng quản lý schema và các thuộc tính repository đang sử dụng. Nếu dùng Spring Boot hoặc DefaultBatchConfiguration, hãy cấu hình serializer qua extension point phù hợp của phiên bản đó thay vì tạo thêm một JobRepository thứ hai.

DefaultExecutionContextSerializer là một implementation có trong các phiên bản Spring Batch hiện đại. Nếu dùng serializer khác, hãy thay bean bằng implementation phù hợp và kiểm tra format dữ liệu tương thích với metadata hiện có.

Không thay serializer trong một môi trường đang có execution cần restart mà chưa đánh giá dữ liệu context đã được lưu bằng serializer cũ. Serializer mới phải đọc được dữ liệu cũ hoặc cần một kế hoạch migration có kiểm soát.

## 5. Chọn kiểu dữ liệu để lưu trong context

Kiểu dữ liệu đưa vào ExecutionContext phải được serializer hiện tại hỗ trợ. Với Java serialization, các object cần đáp ứng yêu cầu Serializable và toàn bộ object graph liên quan cũng phải serialize được. Với JSON serializer, giá trị cần có cách ánh xạ và khôi phục phù hợp.

Các kiểu dữ liệu đơn giản thường dễ quản lý:

- String cho tên file, version hoặc mã trạng thái.
- Long hoặc Integer cho ID, offset và page number.
- Boolean cho cờ trạng thái.
- Các kiểu ngày giờ được serializer hỗ trợ rõ ràng.
- Enum hoặc value object đơn giản khi đã có quy tắc mapping ổn định.

Ví dụ:

~~~java
ExecutionContext context = stepExecution.getExecutionContext();

context.putString("input.file", inputFileName);
context.putLong("reader.lastCustomerId", lastCustomerId);
context.putInt("reader.page", currentPage);
context.putBoolean("validation.completed", true);
~~~

Các kiểu object phức tạp cần cân nhắc kỹ:

~~~java
// Cân nhắc kỹ trước khi lưu một object nghiệp vụ lớn.
context.put("customerAggregate", customerAggregate);
~~~

Object nghiệp vụ có thể chứa collection lớn, proxy JPA, lazy relationship, connection, resource hoặc tham chiếu đến class không phù hợp để serialize. Thay vì lưu cả object, hãy lưu ID hoặc một vài giá trị nhỏ đủ để Step sau truy vấn lại dữ liệu cần thiết.

Ví dụ, thay vì lưu một Customer entity:

~~~java
context.putLong("customerId", customer.getId());
~~~

Step tiếp theo có thể dùng ID để tải entity từ database. Cách này làm context gọn hơn và tránh gắn metadata vào toàn bộ cấu trúc object của domain model.

## 6. Lỗi serialization thường gặp

Nếu serializer không thể chuyển một giá trị trong context thành representation, quá trình lưu metadata có thể thất bại. Với Java serialization, lỗi thường gặp là NotSerializableException khi object hoặc một thành phần trong object graph không triển khai Serializable.

Các nguyên nhân phổ biến:

- Lưu object tùy chỉnh không hỗ trợ serialization.
- Object chứa một field không serialize được.
- Lưu JPA entity có proxy hoặc quan hệ lazy không phù hợp.
- Lưu stream, connection, thread, executor hoặc resource đang mở.
- Dùng serializer JSON nhưng không có mapping cho kiểu dữ liệu.
- Dữ liệu deserialize không còn tương thích với class hiện tại.

Ví dụ không nên làm:

~~~java
// Không lưu resource đang mở vào ExecutionContext.
context.put("jdbcConnection", connection);
context.put("fileReader", bufferedReader);
context.put("executor", executorService);
~~~

Các resource này có lifecycle riêng và không thể khôi phục chỉ bằng cách serialize object reference. Hãy lưu thông tin nhận diện resource hoặc vị trí cần tiếp tục, rồi mở lại resource trong callback open() của ItemStream.

Khi serialization thất bại, lỗi có thể xuất hiện ở thời điểm JobRepository persist context, không nhất thiết tại dòng put() đã thêm object. Vì vậy, một Step có thể xử lý nhiều item rồi mới gặp lỗi khi framework lưu checkpoint.

## 7. Tương thích giữa các lần triển khai

ExecutionContext có thể tồn tại lâu hơn một lần chạy ứng dụng. Một Job thất bại hôm nay có thể được restart sau khi ứng dụng đã triển khai phiên bản mới. Do đó, format context và kiểu dữ liệu đã lưu cần tương thích qua các phiên bản.

Với Java serialization, thay đổi class có thể ảnh hưởng khả năng deserialize. Một số thay đổi cấu trúc hoặc serialVersionUID không tương thích có thể khiến dữ liệu cũ không đọc được.

Với JSON, đổi tên property, thay kiểu trường, đổi enum hoặc thay quy tắc polymorphic mapping cũng có thể khiến context cũ không khôi phục đúng.

Một số nguyên tắc thiết kế:

1. Ưu tiên lưu giá trị đơn giản và ổn định thay vì domain object.
2. Dùng key có namespace theo component, ví dụ customerReader.lastId.
3. Giữ ý nghĩa của key ổn định giữa các phiên bản.
4. Khi cần thay đổi format, hỗ trợ đọc format cũ trong giai đoạn chuyển tiếp hoặc có kế hoạch xử lý execution cũ.
5. Không đổi tên class được lưu trong Java serialization mà không xem xét dữ liệu đang tồn tại.
6. Kiểm thử restart bằng metadata được tạo từ phiên bản ứng dụng trước.

### Version hóa context key

Nếu logic phục hồi thay đổi, có thể dùng key versioned để nhận biết format state:

~~~java
private static final String CONTEXT_VERSION =
        "orderWriter.contextVersion";

private static final String LAST_ORDER_ID =
        "orderWriter.lastOrderId";

void saveState(ExecutionContext context, long lastOrderId) {
    context.putInt(CONTEXT_VERSION, 2);
    context.putLong(LAST_ORDER_ID, lastOrderId);
}
~~~

Khi mở writer, code có thể đọc context version và xử lý các phiên bản mà ứng dụng còn hỗ trợ. Ví dụ này minh họa cách tổ chức key; không thay thế kế hoạch tương thích cho serializer hoặc schema.

Không nên xóa key cũ ngay khi triển khai phiên bản mới nếu vẫn còn JobExecution cũ cần restart. Có thể cần giữ logic đọc cả key cũ và key mới trong một khoảng thời gian.

## 8. Thay đổi serializer khi repository đã có dữ liệu

Serializer là một phần của format lưu trữ. Nếu ứng dụng đã ghi context bằng serializer A rồi chuyển sang serializer B, serializer B có thể không hiểu dữ liệu cũ.

Ví dụ:

~~~text
Các execution cũ
    |
    v
Context được lưu theo format A
    |
    | nâng cấp ứng dụng / đổi serializer
    v
Ứng dụng mới dùng format B
    |
    v
Restart execution cũ
    |
    +--> B đọc được format A: có thể tiếp tục
    |
    +--> B không đọc được format A: lỗi khôi phục context
~~~

Trước khi đổi serializer, cần xác định:

- Còn JobInstance thất bại hoặc stopped cần restart không.
- Còn StepExecution nào cần khôi phục context không.
- Serializer mới có thể đọc dữ liệu cũ không.
- Có cần chuyển đổi dữ liệu metadata hay giữ serializer cũ cho đến khi execution cũ kết thúc không.
- Các node ứng dụng chạy song song có đang dùng cùng format không.

Không sửa trực tiếp chuỗi serialized trong các bảng BATCH_* bằng SQL thủ công. Việc này dễ làm hỏng format hoặc quan hệ metadata. Nếu cần migration, hãy dùng công cụ chuyển đổi có kiểm soát, backup dữ liệu và kiểm thử restore/restart trên bản sao repository.

Một chiến lược thường dễ vận hành hơn là giữ serializer tương thích trong thời gian còn execution cũ, ngừng tạo execution mới dùng format cũ, chờ các execution cũ hoàn tất hoặc được xử lý theo chính sách, rồi mới loại bỏ khả năng đọc format cũ.

## 9. Kích thước context và hiệu năng repository

Mỗi lần context được persist, dữ liệu phải được serialize và ghi vào metadata repository. Context càng lớn thì chi phí CPU, dung lượng database, backup và truy vấn càng tăng.

Không nên lưu:

- Danh sách hàng nghìn hoặc hàng triệu item.
- Toàn bộ payload JSON/XML lớn.
- File content hoặc binary data.
- Entity graph hoặc collection quan hệ lớn.
- Dữ liệu có thể truy vấn lại từ nguồn nghiệp vụ.

Thay vào đó, lưu các giá trị tham chiếu:

~~~java
context.putString("staging.file", "/data/batch/staging/orders-8421.csv");
context.putLong("staging.batchId", 8421L);
context.putLong("reader.lastId", 95000L);
~~~

Dữ liệu lớn nên được lưu trong database nghiệp vụ, file hoặc object storage. ExecutionContext chỉ giữ ID, đường dẫn hoặc watermark đủ để xác định cách tiếp tục.

Kích thước context lớn có thể làm tăng thời gian serialize/deserialize ở mỗi lần lưu hoặc khôi phục, làm phình các bảng metadata và khiến cleanup/backup chậm hơn. Giữ context nhỏ giúp JobRepository tập trung vào nhiệm vụ quản lý execution.

## 10. Bảo mật dữ liệu được serialize

Serialization không phải mã hóa. Nếu context chứa password, API token, private key hoặc credential, serializer có thể ghi giá trị đó vào metadata dưới dạng có thể đọc hoặc giải mã tùy format.

Không lưu secret trong:

- Job ExecutionContext.
- Step ExecutionContext.
- Custom object được đưa vào context.
- Exception message hoặc log phát sinh trong lúc serialize.

Hãy lưu secret trong secret manager và chỉ đưa reference không nhạy cảm vào context nếu Step sau cần tìm lại secret. Quyền truy cập JobRepository cũng cần được giới hạn vì người có thể đọc metadata có thể xem các giá trị context đã persist.

Mã hóa database hoặc disk at rest là lớp bảo vệ bổ sung, không thay thế nguyên tắc không lưu credential vào metadata. Nếu tổ chức yêu cầu mã hóa dữ liệu cụ thể trong context, cần cấu hình và kiểm thử serializer hoặc lớp mã hóa phù hợp, bao gồm cả khả năng đọc lại khi restart và quản lý khóa.

## 11. JobParameters và ExecutionContext không giống nhau

JobParameters và ExecutionContext đều được lưu trong JobRepository nhưng có vai trò khác nhau.

| Thuộc tính | JobParameters | ExecutionContext |
|---|---|---|
| Mục đích | Mô tả đầu vào của JobInstance/JobExecution | Lưu trạng thái runtime và checkpoint |
| Ai thường tạo | Caller, scheduler hoặc JobLauncher | Reader, writer, Step hoặc Job logic |
| Có thể cập nhật trong khi chạy? | Không dùng để cập nhật trạng thái runtime | Có thể cập nhật qua API context |
| Vai trò khi restart | Giữ identifying parameters để nhận diện cùng JobInstance | Khôi phục vị trí và trạng thái đã lưu |
| Cách lưu | Metadata parameter theo kiểu và giá trị | Serialize key/value qua ExecutionContextSerializer |

Không dùng JobParameters như một nơi thay thế ExecutionContext cho checkpoint. Ngược lại, không dùng ExecutionContext để thay đổi danh tính của JobInstance.

Cũng cần nhớ rằng non-identifying JobParameter vẫn có thể được lưu trong metadata. Cờ identifying chỉ quyết định parameter có tham gia xác định JobInstance hay không, không phải cờ bảo mật.

## 12. Serialization trong reader và writer

Reader và writer có thể triển khai ItemStream để lưu trạng thái thông qua ExecutionContext.

Ví dụ reader lưu ID cuối cùng đã đọc:

~~~java
public class CustomerReader implements ItemStreamReader<Customer> {

    private static final String LAST_ID =
            "customerReader.lastId";

    private long lastId;

    @Override
    public void open(ExecutionContext context) {
        lastId = context.containsKey(LAST_ID)
                ? context.getLong(LAST_ID)
                : 0L;
    }

    @Override
    public Customer read() {
        // Đọc bản ghi tiếp theo sau lastId từ nguồn dữ liệu.
        // Cập nhật lastId khi đã lấy được item.
        return loadNextCustomer();
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(LAST_ID, lastId);
    }

    @Override
    public void close() {
        // Đóng resource nếu reader có mở.
    }
}
~~~

Khi Step cần lưu checkpoint, framework gọi update() để reader đưa state vào Step ExecutionContext. JobRepository serialize context theo cấu hình repository.

Writer có thể dùng cách tương tự nếu cần lưu vị trí ghi. Tuy nhiên, state writer phải khớp với dữ liệu đích đã commit. Không chỉ tăng bộ đếm trong memory rồi lưu nó; nếu chunk rollback, bộ đếm có thể đã tiến lên dù dữ liệu đích chưa được xác nhận.

Khi bọc reader hoặc writer có triển khai ItemStream bên trong delegate/composite, hãy bảo đảm stream được đăng ký đúng để callback open, update và close được gọi.

## 13. Kiểm thử serialization và round-trip

Một serializer cần được kiểm thử theo cả hai chiều. Một test round-trip cơ bản có thể kiểm tra rằng các giá trị sau khi serialize rồi deserialize vẫn giữ đúng kiểu và nội dung.

Ví dụ mang tính minh họa:

~~~java
@Test
void executionContextCanBeSerializedAndRestored() throws Exception {
    ExecutionContext original = new ExecutionContext();
    original.putString("source.version", "v4");
    original.putLong("reader.lastId", 8500L);
    original.putBoolean("validation.completed", true);

    ByteArrayOutputStream output = new ByteArrayOutputStream();
    serializer.serialize(original, output);

    ByteArrayInputStream input =
            new ByteArrayInputStream(output.toByteArray());
    Map<String, Object> restoredValues = serializer.deserialize(input);

    assertEquals("v4", restoredValues.get("source.version"));
    assertEquals(8500L, restoredValues.get("reader.lastId"));
    assertEquals(true, restoredValues.get("validation.completed"));
}
~~~

Tên method và kiểu tham số cụ thể của ExecutionContextSerializer có thể khác theo phiên bản; hãy điều chỉnh test theo interface đang dùng. Mục tiêu là kiểm tra round-trip bằng đúng serializer đã cấu hình cho repository.

Ngoài unit test, nên có integration test với JobRepository:

1. Tạo JobExecution hoặc StepExecution.
2. Đưa các giá trị checkpoint vào ExecutionContext.
3. Persist execution qua repository.
4. Đọc lại execution/context bằng repository hoặc API truy vấn phù hợp.
5. Xác nhận key, value và kiểu dữ liệu được khôi phục.
6. Mô phỏng restart bằng context đã lưu và xác nhận reader/writer tiếp tục đúng vị trí.

Nếu ứng dụng nâng cấp phiên bản, hãy giữ fixture metadata được tạo từ phiên bản trước để kiểm tra khả năng deserialize dữ liệu cũ.

## 14. Kiểm tra lỗi serialization khi vận hành

Khi Job thất bại lúc cập nhật metadata, cần xác định lỗi đến từ business logic, transaction hay serializer.

Một số dấu hiệu:

- NotSerializableException khi dùng Java serialization.
- Lỗi mapping hoặc unsupported type với serializer JSON.
- Lỗi deserialize do class hoặc schema đã thay đổi.
- Lỗi đọc dữ liệu serialized bị hỏng hoặc bị cắt.
- Lỗi ghi database do giới hạn kích thước cột hoặc transaction.

Các bước điều tra:

1. Xác định JobExecution và StepExecution gặp lỗi.
2. Xem exception gốc và vị trí framework đang persist ExecutionContext.
3. Xác định key/value mới được thêm vào context trong chunk hoặc Step.
4. Kiểm tra kiểu dữ liệu và object graph của giá trị đó.
5. Xác nhận serializer được cấu hình ở runtime.
6. Kiểm tra schema metadata và giới hạn cột của repository.
7. Thử serialize/deserialize giá trị tương tự bằng đúng serializer trong môi trường test.
8. Nếu lỗi xuất hiện sau deployment, so sánh format và class giữa phiên bản tạo context và phiên bản đang đọc.

Không log toàn bộ context nếu nó có thể chứa dữ liệu nhạy cảm. Khi cần chẩn đoán, log tên key và loại giá trị không nhạy cảm thay vì in toàn bộ nội dung.

## 15. Những lỗi thiết kế thường gặp

**Cho rằng put() ghi ngay xuống database.** Context trong bộ nhớ chỉ được persist khi framework cập nhật repository theo lifecycle.

**Lưu object không serialize được.** Một object có thể chứa resource hoặc field không hỗ trợ serialization. Hãy lưu scalar hoặc ID thay thế.

**Lưu domain entity lớn.** Entity graph gây context phình to, phụ thuộc class và có thể chứa proxy không phù hợp.

**Đổi serializer mà không tính dữ liệu cũ.** Execution cũ có thể không restart được nếu format mới không đọc được representation cũ.

**Thay đổi class đã serialize.** Java serialization có thể không tương thích sau thay đổi class hoặc serialVersionUID.

**Coi JSON là tự tương thích.** JSON vẫn cần mapping, kiểu dữ liệu và chính sách versioning rõ ràng.

**Lưu secret trong context.** Serializer không phải cơ chế bảo mật; metadata có thể được truy vấn hoặc export.

**Dùng context làm kho dữ liệu lớn.** Payload lớn làm tăng chi phí repository và gây khó khăn khi backup/cleanup.

**Sửa trực tiếp bảng metadata.** Thay đổi serialized context bằng SQL có thể phá format hoặc làm hỏng khả năng restart.

## 16. Quy trình lựa chọn và quản lý serializer

Khi thiết kế JobRepository, hãy xác định:

1. Phiên bản Spring Batch và serializer mặc định thực tế đang được dùng.
2. Các kiểu dữ liệu mà reader, writer và Step sẽ đưa vào context.
3. Có cần lưu object tùy chỉnh hay chỉ cần scalar/reference.
4. Serializer có thể round-trip các giá trị đó không.
5. Format có tương thích khi ứng dụng nâng cấp không.
6. Có JobExecution cũ cần restart sau khi thay serializer không.
7. Context có đủ nhỏ và không chứa dữ liệu nhạy cảm không.
8. Database schema và kích thước cột có phù hợp không.
9. Có integration test persist, load và restart bằng repository thật không.
10. Có kế hoạch backup và migration nếu format metadata thay đổi không.

Ưu tiên giữ ExecutionContext nhỏ, ổn định và dễ deserialize. Dùng ExecutionContextSerializer được cấu hình rõ ràng, kiểm thử round-trip và duy trì tương thích với metadata còn cần sử dụng.

Serialization giúp Spring Batch biến trạng thái runtime thành metadata bền vững để JobRepository lưu và khôi phục khi restart. Khi chỉ lưu các giá trị cần thiết, chọn kiểu dữ liệu tương thích, quản lý thay đổi serializer có kế hoạch và bảo vệ context như dữ liệu metadata, Job có thể phục hồi đáng tin cậy qua các lần chạy và triển khai ứng dụng.

