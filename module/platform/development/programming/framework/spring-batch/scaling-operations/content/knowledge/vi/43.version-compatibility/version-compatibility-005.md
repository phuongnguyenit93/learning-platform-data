# ExecutionContext khi nâng cấp Spring Batch

Trong một hệ thống Spring Batch xử lý dữ liệu lớn, tính năng `restart` phụ thuộc vào khả năng đọc lại trạng thái của lần chạy trước. Khi nâng phiên bản framework, thay đổi trong cách lưu hoặc đọc `ExecutionContext` có thể khiến job vốn chạy ổn định không tiếp tục được: `ItemReader` không khôi phục vị trí, partition bị chạy lại, hoặc `JobRepository` không đọc được dữ liệu lịch sử.

Bài học thuộc chương **Tương thích phiên bản** của module **SPRING_BATCH_SCALING_OPERATIONS**. Mục tiêu là hiểu thay đổi của `ExecutionContext` khi nâng Spring Batch, kiểm tra tính tương thích giữa các thành phần xử lý song song/phân tán, và xây dựng quy trình migration có bằng chứng về khả năng **restart, không mất dữ liệu và không xử lý trùng**.

> Phạm vi: trọng tâm là quá trình nâng cấp từ Spring Batch 4.x lên 5.x và từ 5.x lên 6.x; phiên bản phụ thuộc thực tế cần đối chiếu với tài liệu migration của bản đích. Những thay đổi về `JobParameters`, metadata schema và cấu hình `JobRepository` liên quan trực tiếp đến restart dù không thuộc bản thân `ExecutionContext`.

## 1. ExecutionContext lưu cái gì và tại sao nâng cấp ảnh hưởng đến restart?

`ExecutionContext` là tập khóa–giá trị được Spring Batch lưu trong `JobRepository` để giữ trạng thái có thể khôi phục. Không nên hiểu nó là nơi chứa dữ liệu nghiệp vụ lớn hoặc bộ nhớ chia sẻ xuyên worker.

Một batch job thường có hai loại context:

| Loại | Gắn với | Thường chứa | Khi được lưu |
| --- | --- | --- | --- |
| **Step ExecutionContext** | Một `StepExecution` cụ thể | Cursor, vị trí file, ID cuối đã commit, biên dữ liệu partition, trạng thái `ItemStream` | Trong chunk-oriented step, thường được cập nhật tại các điểm commit |
| **Job ExecutionContext** | Một `JobExecution` | Giá trị cần truyền giữa các step, checkpoint cấp job | Thường được lưu giữa các lần thực thi step |

Với `ItemStream`, trình tự điển hình là:

```text
Job khởi chạy / restart
        |
        v
ItemStream.open(stepExecutionContext)
        |
        v
Đọc -> Xử lý -> Ghi một chunk
        |
        v
ItemStream.update(stepExecutionContext)
        |
        v
Lưu context / commit chunk
        |
        +---- lỗi sau đó ----> Restart -> đọc checkpoint đã commit
```

`open` đọc trạng thái của lần thực thi trước, còn `update` đóng góp trạng thái sắp được lưu. Việc khôi phục đến đâu còn tùy cách reader/writer quản lý checkpoint và giao dịch thực tế. Nếu có tác dụng phụ bên ngoài transaction (gọi API, gửi thông báo, ghi hệ thống khác), việc đọc lại context thành công **không tự bảo đảm** đầu ra không bị tạo trùng.

Ví dụ một bước đọc file 2 triệu dòng ghi `position=1250000` vào context. Sau khi job dừng, phiên bản mới phải giải mã đúng `position` và hiểu nó theo cùng ngữ nghĩa trước khi tiếp tục tại dòng tiếp theo. Nếu bản mới đổi key, đổi kiểu dữ liệu, đổi cách đánh số hoặc serializer, job có thể báo lỗi hoặc quay lại từ đầu.

## 2. Hai lớp tương thích cần kiểm tra riêng

Có hai hợp đồng tương thích độc lập:

1. **Hợp đồng dữ liệu (`ExecutionContext`):** serializer cũ và mới có hiểu cùng định dạng không? Giá trị, tên class, kiểu dữ liệu, khóa và logic của reader/partitioner có tương thích không?
2. **Hợp đồng metadata/job instance:** schema `BATCH_*`, `JobParameters`, tên job/step, trạng thái `JobExecution` và khả năng restart giữa phiên bản có còn tương thích không?

Kiểm tra một serializer có thể đọc lại bytes cũ mới chỉ giải quyết hợp đồng thứ nhất. Một job vẫn có thể **không được Spring Batch phép restart** vì metadata hoặc `JobParameters` đã thay đổi.

### Các thay đổi quan trọng theo phiên bản

| Hướng nâng cấp | Thay đổi cần chú ý | Hệ quả vận hành |
| --- | --- | --- |
| **4.x → 5.x** | Spring Batch 5 đổi serializer mặc định từ JSON/Jackson sang `DefaultExecutionContextSerializer` lưu dưới dạng Base64; Jackson trở thành dependency tùy chọn. `JobParameters` và schema liên quan cũng thay đổi. | Không mặc định cho rằng context JSON cũ đọc được bằng serializer mặc định mới; phải thử migration trên bản sao metadata và xử lý vấn đề job lịch sử. |
| **5.x → 6.x** | `JacksonExecutionContextStringSerializer` ở v6 dùng Jackson 3; serializer Jackson 2 có lớp `Jackson2ExecutionContextStringSerializer` nhưng bị deprecated. Spring Batch 6 cũng đổi cách lưu `JobParameters`. | Cần kiểm tra lại cấu hình JSON, type mapping/trusted classes. **Job instance thất bại khởi chạy bằng v5 không thể restart trực tiếp bằng v6** theo migration guide 6.0. |
| **6.0 → 6.1** | Một số builder reader/writer có `saveState=true` có thể dùng tên mặc định từ class/bean nếu không cấu hình `name`. | Cần giữ ổn định tên/key checkpoint của `ItemStream` khi thay đổi cấu hình bean hoặc reader; kiểm thử restart với metadata thực tế. |

Nguồn: [Spring Batch 5.0 Migration Guide](https://github.com/spring-projects/spring-batch/wiki/Spring-Batch-5.0-Migration-Guide), [Spring Batch 6.0 Migration Guide](https://github.com/spring-projects/spring-batch/wiki/Spring-Batch-6.0-Migration-Guide), [What's new in 6.1](https://docs.spring.io/spring-batch/reference/whatsnew.html).

**Không đánh đồng Base64 với JSON hoặc cơ chế mã hóa bảo mật.** Base64 là cách biểu diễn dữ liệu đã được serialize, không phải encryption. Không thể chỉ nhìn tiền tố của một chuỗi rồi chắc chắn biết đầy đủ kiểu object bên trong; cần kiểm tra serializer thực tế và khả năng deserialize trong môi trường kiểm thử.

## 3. Thay đổi serializer: nguyên nhân thường gặp nhất của lỗi đọc context

### 3.1. Dữ liệu lịch sử và serializer hiện hành có thể khác định dạng

Trong Spring Batch 4.x, cấu hình phổ biến dùng Jackson để ghi context dạng JSON. Từ Spring Batch 5, serializer mặc định của cấu hình batch chuẩn là `DefaultExecutionContextSerializer` với biểu diễn Base64. Ở Spring Batch 5.2, serializer Jackson 2 có tên `Jackson2ExecutionContextStringSerializer`. Với Spring Batch 6, `JacksonExecutionContextStringSerializer` chuyển sang Jackson 3; lớp Jackson 2 được giữ tạm nhưng đã deprecated.

Ví dụ dữ liệu **minh họa về ý tưởng**, không phải payload Spring Batch chuẩn:

```text
Một context logic:
  cursor.lastId: 1250000
  partition.rangeEnd: 1500000

Nếu dùng JSON serializer:
  dữ liệu lưu dưới dạng chuỗi JSON (có thể kèm type metadata)

Nếu dùng DefaultExecutionContextSerializer:
  dữ liệu lưu dưới dạng chuỗi Base64 của nội dung đã serialize
```

Đổi serializer chỉ tác động đến cách lưu và tải context; **không tự chuyển đổi** các bản ghi đã tồn tại trong `BATCH_STEP_EXECUTION_CONTEXT` hoặc `BATCH_JOB_EXECUTION_CONTEXT`. Nếu bản ghi cũ cần dùng để restart, phải duy trì đường đọc tương thích hoặc migrate có kiểm chứng.

### 3.2. Serializable và khả năng tồn tại qua thay đổi class

Với serializer mặc định, các giá trị không transient phải serialize được (thường đáp ứng `java.io.Serializable`). Một object lưu nguyên class ứng dụng có thể gặp lỗi sau nâng cấp:

- `ClassNotFoundException`: class từng lưu trong context đã bị xóa/đổi package.
- `InvalidClassException`: dạng Java-serialized object không tương thích, chẳng hạn thay đổi `serialVersionUID` hoặc cấu trúc class.
- `NotSerializableException`: bổ sung field hoặc giá trị không serializable.
- Lỗi Jackson về type ID, loại dữ liệu chưa được trust hoặc không dựng lại được kiểu object.
- `ClassCastException`/\`getLong\`/\`getString\` thất bại khi dữ liệu cũ và code mới dùng kiểu khác nhau cho cùng khóa.

Một thực hành bền vững hơn là **lưu các giá trị nhỏ, ổn định, đơn giản**: `String`, `long`, `int`, token checkpoint bất biến, ID nguồn, ranh giới partition. Nếu buộc lưu object, phải có quy ước version hóa schema, kiểm thử serializer và chính sách migration rõ ràng.

### 3.3. Context nên lưu checkpoint, không lưu dữ liệu xử lý

| Nên lưu | Hạn chế hoặc tránh |
| --- | --- |
| `lastCommittedId=1250000`, `pageIndex=40` | Danh sách hàng trăm nghìn record |
| `fileName` và vị trí đọc phù hợp | Stream, JDBC connection, file handle, thread |
| `rangeStart/rangeEnd` của partition | Entity JPA đang gắn với persistence context |
| `checkpoint.version=2` | Class ứng dụng thay đổi thường xuyên mà không có kế hoạch tương thích |
| Khóa nghiệp vụ phục vụ idempotency | Password, access token, thông tin nhạy cảm trong DB metadata |

Giảm kích thước context cũng hạn chế lỗi tràn cột, tăng chi phí commit và áp lực xử lý CLOB.

## 4. Kiểm tra metadata trước khi thay đổi phiên bản

Với `JdbcJobRepository`, hai bảng quan trọng là:

- `BATCH_STEP_EXECUTION_CONTEXT`: gắn với `STEP_EXECUTION_ID`, chứa `SHORT_CONTEXT` và `SERIALIZED_CONTEXT`.
- `BATCH_JOB_EXECUTION_CONTEXT`: gắn với `JOB_EXECUTION_ID`, cùng các cột context tương ứng.

Tên schema, prefix và kiểu cột có thể khác theo DB và cấu hình; đây là tên mặc định. Các lệnh dưới đây **chỉ đọc**, dùng tham số an toàn thay cho nối chuỗi SQL.

### 4.1. Thống kê job còn dang dở

```sql
SELECT
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.START_TIME,
    je.END_TIME
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
    ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE je.STATUS IN ('STARTING', 'STARTED', 'STOPPING',
                    'STOPPED', 'FAILED', 'UNKNOWN')
ORDER BY je.JOB_EXECUTION_ID DESC;
```

Đối chiếu trạng thái với process/pod và log; `STARTED` tồn đọng không đủ chứng minh worker chết. Không sửa trạng thái batch bằng SQL để “cho phép restart”.

### 4.2. Xác định context cần bảo toàn

```sql
SELECT
    se.JOB_EXECUTION_ID,
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    sec.SHORT_CONTEXT,
    CASE WHEN sec.SERIALIZED_CONTEXT IS NULL
         THEN 'SHORT_ONLY'
         ELSE 'HAS_LONG_CONTEXT'
    END AS CONTEXT_STORAGE
FROM BATCH_STEP_EXECUTION se
LEFT JOIN BATCH_STEP_EXECUTION_CONTEXT sec
    ON sec.STEP_EXECUTION_ID = se.STEP_EXECUTION_ID
WHERE se.JOB_EXECUTION_ID = ?
ORDER BY se.STEP_EXECUTION_ID;
```

`SHORT_CONTEXT` có thể chỉ chứa phần đầu của chuỗi được serialize; với context dài, phần đầy đủ nằm ở `SERIALIZED_CONTEXT`. Không lấy `SHORT_CONTEXT` làm bản sao đầy đủ khi chuyển dữ liệu, và không ghi payload metadata vào log tập trung nếu chứa dữ liệu nhạy cảm.

Với job-level context, truy vấn bảng `BATCH_JOB_EXECUTION_CONTEXT` theo `JOB_EXECUTION_ID` tương ứng. Khi cần xác định serializer thực tế, ưu tiên **cấu hình ứng dụng của phiên bản đã ghi dữ liệu** kết hợp thử deserialize trên bản sao metadata; không quyết định chỉ bằng việc nhìn chuỗi trong DB.

## 5. Cách chọn chiến lược nâng cấp ExecutionContext

Ba chiến lược thường gặp:

| Chiến lược | Khi phù hợp | Điều kiện và hạn chế |
| --- | --- | --- |
| **Drain rồi nâng cấp** | Có thể hoàn tất hoặc xử lý toàn bộ job đang chạy/dang dở trước khi triển khai | Ít rủi ro tương thích checkpoint; vẫn phải kiểm tra schema và các job lịch sử |
| **Giữ serializer cũ trong giai đoạn chuyển tiếp** | Cần đọc các context định dạng cũ và framework đích còn hỗ trợ serializer đó | Phải kiểm tra việc đọc **và ghi**, mapping kiểu, classpath, schema; đây không giải quyết bất tương thích `JobParameters` hoặc `JobInstance` |
| **Migration dữ liệu context có kiểm chứng** | Bắt buộc duy trì checkpoint cũ trong một định dạng mới | Cần công cụ chuyển đổi theo schema ứng dụng, bản sao DB, định nghĩa rollback và đối chiếu từng context; không chuyển chuỗi trực tiếp theo phỏng đoán |

Với đường **5.x → 6.x**, migration guide chính thức nêu rằng do thay đổi serialize `JobParameters`, **không thể restart trực tiếp các failed job instance tạo từ v5 trên v6**. Kế hoạch mặc định phải hoàn tất/restart thành công trên v5 hoặc có quyết định `abandon` hợp lệ **trước** khi chuyển v6. Việc giữ serializer Jackson 2 trong v6 chỉ giúp tương thích với định dạng context trong những trường hợp được hỗ trợ; nó **không vượt qua** giới hạn restart của job instance lịch sử.

Với đường **4.x → 5.x**, còn phải xét thay đổi schema/job parameters được liệt kê trong migration guide 5.0. Khi job lịch sử chưa hoàn tất, không mặc định bản mới có thể khám phá và restart dữ liệu cũ. Nếu không có khả năng hoàn tất trước migration, cần lập phương án nghiệp vụ và thử nghiệm độc lập thay vì đánh dấu `COMPLETED` giả.

## 6. Ví dụ cấu hình serializer khi cần giữ định dạng JSON

Trong Spring Batch 6 dùng JDBC repository và cấu hình bằng annotation, có thể khai báo một serializer Jackson 2 **tạm thời** khi đang chuẩn bị chuyển định dạng:

```java
// Ví dụ cho Spring Batch 6.x: các import bỏ qua để tập trung cấu hình.
// Cần có dependency Jackson 2 tương thích và JDBC infrastructure.

@Configuration
@EnableBatchProcessing
@EnableJdbcJobRepository(
    executionContextSerializerRef = "legacyContextSerializer"
)
class BatchInfrastructureConfig {

    @Bean
    ExecutionContextSerializer legacyContextSerializer() {
        // API deprecated trong v6, chỉ là giải pháp chuyển tiếp.
        return new Jackson2ExecutionContextStringSerializer();
    }
}
```

Đây là cấu hình minh họa cho môi trường dùng `@EnableBatchProcessing` và `@EnableJdbcJobRepository`; cần bổ sung `DataSource`, transaction manager và các bean hạ tầng theo ứng dụng. Nếu dùng `JdbcDefaultBatchConfiguration`, điểm tùy biến tương ứng là `getExecutionContextSerializer()`. Với Spring Batch 5, thuộc tính `executionContextSerializerRef` đặt ở `@EnableBatchProcessing`. Không phối hợp tùy tiện nhiều cơ chế tự cấu hình Spring Boot và cấu hình Batch thủ công.

Khi dùng Jackson 2/3 để deserialize object tùy biến, cần cấu hình rõ **các class được tin cậy** và khả năng khôi phục object; tránh cho phép mọi loại object mà không kiểm soát. Giải pháp Jackson 2 trong Spring Batch 6 đã deprecated và được dự kiến loại bỏ ở phiên bản tương lai, vì vậy phải có kế hoạch thoát khỏi phụ thuộc này.

Nếu context đang là Base64 từ serializer mặc định, bật JSON serializer như trên **không khiến dữ liệu Base64 cũ tự đọc được**. Muốn đổi định dạng phải có migration phù hợp, hoặc bảo toàn serializer tương ứng cho dữ liệu cần sử dụng.

Tài liệu API: [`EnableJdbcJobRepository`](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/configuration/annotation/EnableJdbcJobRepository.html), [`JdbcDefaultBatchConfiguration`](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/configuration/support/JdbcDefaultBatchConfiguration.html), [`ExecutionContextSerializer`](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/repository/ExecutionContextSerializer.html).

## 7. Viết checkpoint dễ nâng cấp và dễ kiểm thử

Giữ tên key, kiểu giá trị và ý nghĩa dữ liệu ổn định qua các phiên bản. Ví dụ cách làm trong reader có `ItemStream`:

```java
// Đoạn minh họa logic: method open/update thuộc ItemStream.
// Spring Batch 5: org.springframework.batch.item.ExecutionContext
// Spring Batch 6: org.springframework.batch.infrastructure.item.ExecutionContext

private static final String LAST_ID = "ordersReader.lastCommittedId";
private long lastCommittedId;

@Override
public void open(ExecutionContext context) {
    lastCommittedId = context.containsKey(LAST_ID)
            ? context.getLong(LAST_ID)
            : 0L;

    // Thiết lập cursor theo lastCommittedId.
}

@Override
public void update(ExecutionContext context) {
    // Giá trị phải đại diện tiến độ có thể replay an toàn.
    context.putLong(LAST_ID, lastCommittedId);
}
```

Đoạn trên giả định logic reader chỉ nâng `lastCommittedId` tới vị trí mà hệ thống được phép checkpoint; code thực tế phải đảm bảo đồng bộ với commit, transactional writer và cách reader phát bản ghi. Nếu đọc lại theo `id > lastCommittedId`, cần bảo đảm ID dùng để resume có thứ tự phù hợp, dữ liệu nguồn không bị thay đổi theo cách gây bỏ sót và truy vấn có thứ tự ổn định.

Các quy tắc đáng áp dụng:

1. **Đặt key có namespace ổn định** theo reader/step, ví dụ `ordersReader.lastCommittedId`; đừng vô tình đổi tên bean hay component có `saveState=true` vì nhiều `ItemStream` tạo key từ tên component.
2. **Giữ kiểu dữ liệu nhất quán**, ví dụ `getLong` cho cùng key trong mọi bản. Nếu đổi `int` sang `long`, xác định cách đọc checkpoint đã lưu.
3. **Bổ sung phiên bản schema khi cần**, ví dụ `ordersReader.checkpointVersion=2`; đọc cả v1 và v2 trong giai đoạn migration bằng logic rõ ràng.
4. **Giữ context nhỏ**, lưu ID và offsets thay vì cả graph object; dùng bảng riêng cho tiến độ nghiệp vụ rất lớn.
5. **Đăng ký đúng `ItemStream`** nếu reader/writer được bọc qua delegate; callback `open/update/close` phải chạy để checkpoint tồn tại.
6. **Không bật `saveState=false` tùy tiện** cho reader cần restart từ vị trí cũ; khi tắt lưu state phải có chiến lược khôi phục khác.

## 8. Tác động trong hệ thống nhiều thread, partition và remote worker

Trong module mở rộng Spring Batch, serializer chỉ là một phần của hợp đồng giữa các thành phần phân tán.

### Multi-threaded step

Nhiều thread có thể chia sẻ một `StepExecution` và context liên quan. Một key cursor duy nhất có thể sai nếu các thread xử lý đầu vào không theo thứ tự; checkpoint “ID lớn nhất đã đọc” không đồng nghĩa tất cả ID nhỏ hơn đã commit. Khi nâng cấp, cần kiểm tra cả **thread safety**, thứ tự commit và logic resume. Không tự biến một reader vốn không thread-safe thành reader dùng chung chỉ vì serializer mới đọc được context.

### Parallel steps và partitioning

Mỗi step/partition có `StepExecution` và context riêng. `Partitioner` thường ghi các giá trị như `rangeStart`, `rangeEnd` hoặc `filePath` vào context; `worker step` đọc những giá trị này để xác định phần dữ liệu được giao. Khi nâng cấp:

- Giữ nguyên tên step/partition khi muốn tiếp tục dựa trên metadata cũ; thay đổi chiến lược chia partition có thể làm phạm vi dữ liệu khác nhau ở lần restart.
- Không đổi đơn vị hoặc cách hiểu `rangeStart/rangeEnd` mà không migration (ví dụ biên trên bao gồm chuyển thành biên trên loại trừ).
- Đảm bảo manager và worker cùng hiểu các khóa và kiểu dữ liệu. Với remote partitioning, xác nhận cấu hình `JobRepository`/serializer tương thích và worker có thể truy cập metadata cần thiết.
- `gridSize` là gợi ý chia việc, không thay thế checkpoint từng partition khi restart; kiểm tra chính sách chia lại theo phiên bản thực tế.

### Remote chunking và worker phân tán

Các chunk/message có thể được gửi lại sau timeout hoặc crash. Việc nâng cấp serializer `ExecutionContext` của `JobRepository` **không đồng nghĩa** với việc đã nâng cấp serializer của message broker. Hai định dạng này có thể có classpath, version và cách cấu hình khác nhau.

Vì vậy cần kiểm thử riêng:

- Context trong DB có đọc lại được không?
- Message producer/consumer có tương thích payload và headers không?
- Worker cũ và mới có xử lý giống nhau đối với cùng ID/chunk không?
- Writer có idempotent theo khóa nghiệp vụ khi message được redeliver không?

**Không triển khai xen kẽ manager/worker khác major version trên cùng một job đang chạy** khi chưa có bằng chứng kiểm thử tính tương thích giao thức, context và dữ liệu commit. Một rolling deployment bình thường của web service chưa đủ để chứng minh rollout an toàn cho batch đang thực thi.

## 9. Runbook nâng cấp trong production

Thực hiện theo các cổng kiểm soát, đặc biệt khi nhiều worker đang dùng chung `JobRepository`:

**Trước khi nâng cấp**

1. Chốt ma trận **Spring Batch – Spring Boot/Framework – JDK – Spring Integration/broker client – database driver** cho đúng phiên bản đích.
2. Ghi nhận serializer đang chạy, custom class trong context, phiên bản schema metadata, prefix bảng và cấu hình repository.
3. Kiểm kê `JobInstance` chưa hoàn tất, `FAILED/STOPPED/UNKNOWN` và `STARTED` đang tồn đọng; xác minh với runtime thay vì chỉ nhìn status.
4. Với nâng v5 → v6, hoàn tất hoặc xử lý `abandon` các failed v5 job instance trước thời điểm chuyển, theo khuyến nghị migration chính thức.
5. Dừng tiếp nhận job mới theo cửa sổ triển khai; chờ worker/partition hoàn tất hoặc dừng kiểm soát, đảm bảo không có worker cũ đang ghi.
6. Sao lưu nhất quán **toàn bộ Batch metadata schema** cùng các bảng nghiệp vụ/changelog liên quan, lưu đường khôi phục DB và artifact phiên bản cũ.

**Trên staging từ bản sao dữ liệu production đã ẩn thông tin nhạy cảm**

1. Áp dụng đúng migration DDL được nhà phát triển cung cấp cho loại DB và đường phiên bản đích. Không chạy lại các script khởi tạo làm mất metadata.
2. Kiểm thử đọc các context đại diện: context nhỏ/dài, checkpoint có custom object, partition, old/new schema.
3. Thử một job thất bại có chủ đích trước nâng cấp và đánh giá lại hành vi restart **theo giới hạn hỗ trợ của từng đường phiên bản**, không giả định cross-major restart luôn được.
4. Kiểm thử chạy mới, stop/restart trong cùng bản đích và khôi phục khi worker chết; đối chiếu dữ liệu nguồn–đích và không tạo trùng.
5. Ghi nhận thời gian serialize/deserialize, kích thước context, thời gian commit và throughput trong cấu hình song song thực tế.

**Sau khi triển khai**

1. Chỉ mở lịch chạy mới khi repository, serializer, worker/manager và DB migration có cùng cấu hình đã được kiểm thử.
2. Theo dõi các lỗi deserialize, class loading, `ItemStream.open/update`, rollback, retry, số step thất bại, queue lag, duplicate output.
3. Kiểm tra báo cáo đối soát nghiệp vụ; khi cần rollback, chỉ quay lại phiên bản/schema theo **kịch bản restore đã thử**, không giả định code cũ đọc được metadata do code mới ghi.
4. Lưu lại dấu vết: phiên bản build, bản migration, thời điểm chuyển, số execution còn dang dở, kết quả kiểm thử và người phê duyệt.

## 10. Bộ test tương thích cần có

| Kịch bản | Cách thực hiện | Kết quả mong đợi |
| --- | --- | --- |
| Round-trip context | Serialize rồi deserialize tập key/value đại diện với cấu hình đích | Giá trị, kiểu, key giữ nguyên |
| Context lịch sử | Đọc bản sao context được ghi bằng phiên bản cũ | Đọc thành công nếu đường migration được hỗ trợ; lỗi được phát hiện trước production nếu không hỗ trợ |
| Checkpoint trong chunk | Cho job xử lý một phần, cố ý fail sau vài lần commit, restart cùng phiên bản đích | Không bỏ sót record, không tạo trùng ngoài chính sách |
| Object thay đổi class | Đọc checkpoint có custom type đã rename/đổi schema | Có migrator rõ ràng hoặc từ chối với thông báo có thể xử lý |
| Parallel/partition | Cố ý fail một partition giữa nhiều partition hoàn tất | Chỉ những phần cần chạy lại được xử lý, dải dữ liệu chính xác |
| Remote message redelivery | Kill worker sau khi ghi output nhưng trước khi ack/nhận kết quả | Retry không tạo tác dụng phụ trùng |
| Tăng kích thước context | Thử payload vượt ngưỡng `SHORT_CONTEXT` | Lưu/đọc phần context đầy đủ từ LOB và không mất dữ liệu |
| Khác major version | Mô phỏng job cũ chưa hoàn tất và chuyển major version | Ghi nhận đúng giới hạn được hỗ trợ; không “pass” giả bằng cách tạo `JobInstance` mới |
| Rollback release | Thử khôi phục bản sao DB/schema và binary trước nâng cấp | Job mới và metadata được khôi phục theo thủ tục dự kiến |

**Tiêu chí đạt:** so sánh cả `readCount/writeCount` và dữ liệu nghiệp vụ đầu ra; tổng số record không đủ khi có duplicate hoặc mất dữ liệu được bù trừ. Với dữ liệu có giao dịch, dùng khóa duy nhất, idempotency key hoặc bảng audit để chứng minh tính đúng đắn.

## 11. Chẩn đoán các lỗi sau khi nâng cấp

| Dấu hiệu | Nguyên nhân có thể | Hành động ưu tiên |
| --- | --- | --- |
| `StreamCorruptedException`, lỗi Base64, Jackson parse | Đang đọc JSON bằng serializer mặc định Base64 hoặc ngược lại; payload hỏng | So sánh serializer của phiên bản ghi/đọc trên bản sao DB; không tự sửa chuỗi |
| `ClassNotFoundException`, `InvalidClassException` | Custom object đổi class/`serialVersionUID`, thiếu jar | Kiểm tra classpath/schema value; dùng migrator hoặc phiên bản đọc tương thích |
| Jackson báo `not trusted`/type ID | Mapping type hoặc allowlist thay đổi, Jackson 2 → 3 | Xác định đúng kiểu được tin cậy; cấu hình chỉ lớp cần thiết |
| Reader bắt đầu từ đầu dù đã checkpoint | Đổi tên key/bean, `saveState`, reader không được đăng ký `ItemStream` hoặc tạo `JobInstance` mới | So sánh context/key và job identifying parameters |
| Không restart được failed job v5 trên v6 | Giới hạn lịch sử `JobParameters` trong migration v6 | Hoàn tất/abandon theo quy trình trước migration; thiết kế phương án nghiệp vụ thay thế |
| `BATCH_*` schema exception | DDL chưa migration đúng hoặc đổi DB/table prefix | Đối chiếu migration script, schema và cấu hình repository |
| V6 không còn lưu context trong DB | V6 dùng `ResourcelessJobRepository` do chỉ bật `@EnableBatchProcessing` | Cấu hình `@EnableJdbcJobRepository` hoặc `JdbcDefaultBatchConfiguration` phù hợp |
| Mất dữ liệu hoặc duplicate sau restart | Checkpoint không khớp commit, thay đổi partition, external side effect không idempotent | Dừng xử lý ảnh hưởng, đối soát dữ liệu, sửa logic resume/idempotency trước chạy lại |

Lỗi serialize/deserialize là dấu hiệu kỹ thuật; nó không cho biết ngay có mất dữ liệu nghiệp vụ hay chưa. Hãy đối chiếu lần commit cuối, output và log trước khi restart hoặc bỏ qua context.

## 12. Checklist quyết định có thể nâng cấp chưa

Trả lời “Có” cho các tiêu chí sau trước khi đưa workload lớn lên bản mới:

- [ ] Đã biết chính xác phiên bản nguồn/đích, JDK và dependency liên quan.
- [ ] Đã xác định serializer hiện tại và định dạng context thực tế trong metadata.
- [ ] Đã liệt kê job execution còn chạy/thất bại và lập phương án drain, complete hoặc abandon đúng quy định.
- [ ] Đã đọc kỹ giới hạn restart của `JobParameters` và metadata khi nâng major version.
- [ ] Đã sao lưu nhất quán repository và dữ liệu cần đối soát.
- [ ] Đã migration schema trên staging bằng script chính thức của phiên bản đích.
- [ ] Đã kiểm thử context lịch sử, checkpoint dài, custom object và tên key của `ItemStream`.
- [ ] Đã kiểm thử multi-thread, partitioning, broker redelivery và restart worker bị kill.
- [ ] Đã xác nhận output không mất/trùng dữ liệu bằng kiểm tra nghiệp vụ.
- [ ] Đã thử thủ tục rollback, gồm cả restore DB và binary tương ứng.

**Nguyên tắc cần nhớ:** `ExecutionContext` là một hợp đồng trạng thái bền vững giữa các lần chạy. Khi nâng Spring Batch, tính tương thích phải được chứng minh ở cả ba lớp: **dữ liệu checkpoint – metadata JobRepository – hành vi thực thi của reader/partition/worker**. Việc nâng dependency thành công hoặc khởi chạy được một job mới chưa chứng minh job lịch sử có thể restart an toàn.

## Tài liệu tham khảo

1. [Spring Batch 5.0 Migration Guide – Execution context serialization updates](https://github.com/spring-projects/spring-batch/wiki/Spring-Batch-5.0-Migration-Guide).
2. [Spring Batch 6.0 Migration Guide – Historical data access implications và Jackson 3](https://github.com/spring-projects/spring-batch/wiki/Spring-Batch-6.0-Migration-Guide).
3. [Spring Batch Reference – The Domain Language of Batch](https://docs.spring.io/spring-batch/reference/6.0/domain.html).
4. [Spring Batch Reference – Metadata Schema](https://docs.spring.io/spring-batch/reference/6.0/schema-appendix.html).
5. [Spring Batch Reference – Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/6.0/scalability.html).
6. [Spring Batch Reference – Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/6.0/job/configuring-repository.html).
7. [Spring Batch 6.1 – What's New](https://docs.spring.io/spring-batch/reference/whatsnew.html).

