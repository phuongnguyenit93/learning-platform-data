# Không kiểm tra ExecutionContext trong Spring Batch: lỗi checkpoint và restart thường gặp

## 1. Vì sao phải kiểm tra ExecutionContext?

Trong Spring Batch, **`ExecutionContext` là nơi lưu trạng thái cần thiết để một job hoặc step có thể theo dõi tiến độ và tiếp tục sau khi bị dừng/thất bại**. Nó không phải một biến toàn cục tùy ý, cũng không phải bằng chứng rằng công việc nghiệp vụ đã commit thành công.

Giả sử job `importInvoices` đọc một file có 1 triệu dòng. Step đã ghi thành công 400.000 dòng thì tiến trình mất kết nối và dừng. Khi restart, reader cần biết **vị trí an toàn cuối cùng** để không nhập lại cả file hoặc bỏ qua dữ liệu chưa commit. Spring Batch hỗ trợ việc này qua `ItemStream` và `ExecutionContext`, nhưng cơ chế chỉ đáng tin nếu ứng dụng lưu và **kiểm tra** trạng thái đúng cách.

Lỗi “không kiểm tra ExecutionContext” thường thể hiện dưới những hình thức:

- Đọc giá trị bằng `getInt("offset")` mà không biết key có tồn tại và đúng kiểu hay không.
- Coi giá trị mặc định `0` là an toàn kể cả khi job đang restart và checkpoint bị mất.
- Dùng nhầm **JobExecution context** thay cho **StepExecution context**.
- Đổi tên reader/key giữa hai phiên bản ứng dụng rồi tiếp tục job cũ mà không có migration.
- Lưu số dòng đã đọc nhưng không xác nhận file/nguồn dữ liệu còn là cùng một version.
- Cập nhật vị trí đọc quá sớm hoặc tự ghi checkpoint ngoài ranh giới transaction.
- Lưu object lớn hoặc không thể serialize, khiến việc persist/restart thất bại.
- Không kiểm tra checkpoint và dữ liệu đích sau khi step rollback.

Hậu quả có thể nghiêm trọng hơn một exception: **mất bản ghi**, **xử lý trùng**, **ghi dữ liệu sai thứ tự**, **đọc nhầm file** hoặc **báo job COMPLETED khi kết quả không đầy đủ**.

**Mục tiêu của bài:** hiểu đúng vòng đời `ExecutionContext`, phân biệt phạm vi job/step, kiểm tra checkpoint trước khi dùng, triển khai một reader restartable đơn giản và kiểm thử các tình huống failure/restart. Các ví dụ sử dụng Spring Batch **5.2.x**, Spring Boot **3.x** và Java **17+**; khi dùng phiên bản khác, cần đối chiếu package và API tương ứng.

## 2. ExecutionContext không phải một loại duy nhất

Spring Batch có hai phạm vi `ExecutionContext` quan trọng:

| Phạm vi | Lấy từ đâu? | Mục đích chủ yếu |
|---|---|---|
| **StepExecution context** | `stepExecution.getExecutionContext()` | Trạng thái/checkpoint của **một step**: offset reader, trang tiếp theo, cursor, tiến độ xử lý |
| **JobExecution context** | `jobExecution.getExecutionContext()` | Dữ liệu chia sẻ giữa **các step trong cùng job execution**, ví dụ đường dẫn file đầu ra do step trước tạo |

Cả hai đều là bản đồ key–value, nhưng **khác vòng đời và thời điểm lưu**.

### 2.1. Cấu trúc runtime

```text
JobInstance: importInvoices + businessDate=2025-05-12
    |
    +-- JobExecution id=501
            |
            +-- Job ExecutionContext
            |     app.source.fileId = "invoices-20250512-v3"
            |     app.validation.approved = true
            |
            +-- StepExecution id=1001: downloadStep
            |      Step ExecutionContext
            |        app.download.lastPart = 8
            |
            +-- StepExecution id=1002: importStep
                   Step ExecutionContext
                     app.invoiceReader.nextIndex = 400000
                     app.invoiceReader.sourceId = "invoices-20250512-v3"
```

Khi restart, Spring Batch tạo một **`JobExecution` mới** cho cùng `JobInstance`, và dùng metadata đã lưu của execution trước để khôi phục các state phù hợp. Không nên suy diễn rằng tất cả object Java trong memory hoặc mọi map field của bean cũ sẽ sống qua restart.

### 2.2. Hai context lưu ở thời điểm khác nhau

Theo mô hình chunk-oriented processing:

- **StepExecution context** được Spring Batch cập nhật/persist theo các điểm checkpoint, thường là **trước commit của chunk** khi các `ItemStream` được gọi `update(...)`.
- **JobExecution context** thường được persist ở **ranh giới các step**, thích hợp để chuyển dữ liệu giữa step, không phù hợp làm nơi cập nhật cursor sau mỗi item của một chunk.
- Dữ liệu trong `ExecutionContext` cần qua cơ chế **serialize/deserialze** của `JobRepository`; field trong bean Java không tự trở thành state bền vững.

Khi chạy step song song hoặc partitioned, từng `StepExecution` có context riêng. Hai step có thể cùng đặt key `"offset"` nhưng không vì thế có một bộ đếm offset chung.

**Quy tắc chọn phạm vi:** thứ gì cần **restart trong cùng một step** thì thường thuộc step context; thứ gì cần **step sau biết kết quả step trước** thì có thể dùng job context cùng cơ chế chuyển giao rõ ràng.

## 3. Vòng đời ItemStream: open, read, update, close

`ItemReader` chỉ định cách đọc một item. Để lưu và khôi phục state, reader có thể triển khai `ItemStream` hoặc `ItemStreamReader`:

```java
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStreamReader;

public class ExampleReader implements ItemStreamReader<String> {

    @Override
    public void open(ExecutionContext executionContext) {
        // Khôi phục checkpoint khi khởi động/restart step.
    }

    @Override
    public String read() throws Exception {
        // Trả item hoặc null khi hết dữ liệu.
        return null;
    }

    @Override
    public void update(ExecutionContext executionContext) {
        // Lưu trạng thái phù hợp ở mốc framework yêu cầu.
    }

    @Override
    public void close() {
        // Giải phóng resource.
    }
}
```

Luồng thông thường:

```text
Step bắt đầu
    |
    v
ItemStream.open(step ExecutionContext)
    |
    v
read -> process -> write (nhiều item trong chunk)
    |
    v
ItemStream.update(step ExecutionContext)
    |
    v
Persist checkpoint / commit chunk
    |
    v
Lặp chunk tiếp theo
    |
    v
ItemStream.close()
```

Sơ đồ giản lược này mô tả ý tưởng checkpoint, không có nghĩa tất cả listener hoặc thao tác metadata xảy ra theo một thứ tự đơn giản trong mọi lỗi/transaction manager. Điểm cần nhớ: **đọc xong một item chưa đồng nghĩa đã có checkpoint bền vững cho item đó**.

### 3.1. Chỉ chỉnh field trong reader là chưa đủ

Đoạn sau không restartable:

```java
public class VolatileReader implements ItemReader<String> {

    private int nextIndex;

    @Override
    public String read() {
        if (nextIndex >= items.size()) {
            return null;
        }
        return items.get(nextIndex++);
    }
}
```

Giá trị `nextIndex` chỉ nằm trong RAM. JVM restart tạo reader mới với `nextIndex=0`; nếu dữ liệu đích đã commit 400.000 item, job có thể xử lý lại toàn bộ phần đầu.

Thêm `ItemStream`, persist checkpoint và thiết kế writer idempotent mới giải quyết đầy đủ bài toán.

### 3.2. Đừng tự ghi trạng thái bền vững mỗi lần read

Một anti-pattern khác:

```java
public String read() {
    String item = loadNext();
    saveOffsetToSeparateDatabaseImmediately();
    return item;
}
```

Nếu vị trí đã được ghi ở database riêng **trước khi item được writer commit**, rồi writer gặp lỗi, lần restart có thể bỏ qua item chưa từng được ghi thành công.

Cơ chế checkpoint nên gắn với ranh giới giao dịch phù hợp; nếu cần state ở ngoài `JobRepository`, phải thiết kế transaction và recovery đồng bộ giữa state và side effect, không chỉ “ghi offset sớm cho chắc”.

## 4. Đọc ExecutionContext mà không kiểm tra: lỗi rất thường gặp

Ví dụ:

```java
// Mẫu dễ sai:
int nextIndex = stepExecution
        .getExecutionContext()
        .getInt("nextIndex");
```

Các giả định ẩn bên trong:

1. Key `nextIndex` đã tồn tại.
2. Giá trị đã được ghi đúng kiểu `int`.
3. Giá trị không âm.
4. Giá trị không vượt số lượng phần tử nguồn.
5. Key này thuộc đúng reader/step.
6. Giá trị được ghi từ cùng version đầu vào.
7. Nếu key không tồn tại thì mặc định từ đầu là hành vi an toàn.

Bất kỳ giả định nào sai cũng có thể gây lỗi hoặc mất dữ liệu. **Không được xem thao tác `getInt(...)` đơn lẻ là bước validation checkpoint.**

### 4.1. Kiểm tra tồn tại và kiểu dữ liệu

`ExecutionContext` hỗ trợ `containsKey(...)` và các phương thức typed như `putInt/getInt`, `putLong/getLong`, `putString/getString`.

```java
ExecutionContext context = stepExecution.getExecutionContext();

if (!context.containsKey("app.reader.nextIndex")) {
    // Phải phân biệt lần chạy mới và checkpoint thất lạc.
}

Object raw = context.get("app.reader.nextIndex");

if (!(raw instanceof Integer nextIndex)) {
    throw new IllegalStateException(
            "Checkpoint type is invalid");
}

if (nextIndex < 0) {
    throw new IllegalStateException(
            "Checkpoint index cannot be negative");
}
```

Dùng `get(...)` để kiểm tra kiểu thô trước khi gọi typed getter sẽ cho phép thông báo lỗi rõ ràng thay vì tin rằng serializer luôn tạo đúng kiểu. Nếu key có kiểu `Long` do phiên bản cũ ghi nhưng mã mới đòi `Integer`, cần quy tắc migration hoặc từ chối restart, không ép kiểu một cách im lặng.

### 4.2. Phân biệt fresh run và restart

Một context rỗng có thể là bình thường ở **lần chạy đầu tiên**. Nhưng nếu đang **restart** mà checkpoint đáng lẽ phải tồn tại, việc tự mặc định `nextIndex=0` có thể làm job đọc lại.

Không nên viết:

```java
// Nguy hiểm nếu mất checkpoint ở lần restart:
int nextIndex = context.containsKey(KEY)
        ? context.getInt(KEY)
        : 0;
```

trong mọi trường hợp mà không biết ý nghĩa của state thiếu. Cần phân biệt:

- **Lần chạy mới**: context chưa có checkpoint, bắt đầu ở 0 là hợp lệ.
- **Restart mà step trước chưa từng checkpoint**: bắt đầu lại từ 0 có thể hợp lệ nếu writer idempotent và ranh giới transaction rõ ràng.
- **Restart mà step đã commit nhiều chunk**: thiếu checkpoint là tín hiệu bất thường; không nên tự đọc lại hoặc nhảy đến một vị trí tùy tiện.

Một cách triển khai thực tế là lưu đồng thời version state, source ID và cursor sau checkpoint đầu; nếu phát hiện **một số key có mặt nhưng không đủ bộ**, fail fast. Với yêu cầu nghiêm ngặt, có thể kết hợp `JobExplorer`/metadata của execution trước để phân biệt restart thiếu state. Phần tiếp theo trình bày mã kiểm tra nhất quán.

## 5. Đặt tên key rõ ràng và version hóa trạng thái

`ExecutionContext` là map chung trong phạm vi step/job tương ứng. Đặt tên `"count"`, `"page"` hoặc `"offset"` quá chung dễ xung đột khi nhiều `ItemStream` hoặc listener dùng chung context.

Ưu tiên key có namespace:

```text
app.invoiceReader.stateVersion
app.invoiceReader.sourceId
app.invoiceReader.nextIndex

app.paymentReader.stateVersion
app.paymentReader.lastTransactionId

app.report.outputFileId
```

Không cần tự nhét tên `jobExecutionId` vào mỗi key: mỗi execution đã có context riêng. Nhưng cần namespace theo **component** để tránh hai reader vô tình cùng dùng một khóa.

### 5.1. Version hóa schema của checkpoint

Một checkpoint có thể được ghi bởi phiên bản code trước:

```text
Version 1:
  app.invoiceReader.nextIndex = 400000

Version 2:
  app.invoiceReader.lastOrderId = "INV-400000"
  app.invoiceReader.sourceVersion = "etag-123"
```

Nếu ứng dụng v2 cứ gọi `getString("lastOrderId")` mà không xác định version, có thể bắt đầu từ sai vị trí hoặc ném lỗi mơ hồ.

Nên lưu một `stateVersion` và có một trong các chính sách:

- Chỉ chấp nhận version hiện tại.
- Chuyển đổi version cũ sang version mới bằng hàm migration có test.
- Từ chối restart và yêu cầu một quy trình reprocess an toàn.

**Đừng coi thay tên key là refactor vô hại**: nó có thể phá khả năng restart các job đã dừng trước khi deploy.

## 6. Ví dụ: lớp đọc checkpoint có validation đầy đủ

Ta xây một reader xử lý danh sách bất biến. Mỗi phần tử được truy cập bằng index. State lưu gồm:

- `stateVersion=1` để biết cách diễn giải dữ liệu.
- `sourceId` để xác minh input là **cùng nguồn/version**.
- `nextIndex` là vị trí item kế tiếp.

Đầu vào `sourceId` phải được gắn với một định danh **ổn định qua restart**, chẳng hạn object storage version hoặc file checksum. Không nên tự tính source ID bằng `LocalDate.now()` hoặc tên file có thể bị tái sử dụng với nội dung khác.

### 6.1. Lớp quản lý checkpoint

```java
import org.springframework.batch.item.ExecutionContext;

public final class InvoiceCheckpoint {

    public static final String VERSION =
            "app.invoiceReader.stateVersion";

    public static final String SOURCE_ID =
            "app.invoiceReader.sourceId";

    public static final String NEXT_INDEX =
            "app.invoiceReader.nextIndex";

    private static final int CURRENT_VERSION = 1;

    private InvoiceCheckpoint() {
    }

    public static int restore(
            ExecutionContext context,
            String expectedSourceId,
            int inputSize) {

        if (expectedSourceId == null || expectedSourceId.isBlank()) {
            throw new IllegalArgumentException(
                    "Expected source identity is required");
        }

        if (inputSize < 0) {
            throw new IllegalArgumentException(
                    "inputSize must not be negative");
        }

        boolean hasVersion = context.containsKey(VERSION);
        boolean hasSource = context.containsKey(SOURCE_ID);
        boolean hasIndex = context.containsKey(NEXT_INDEX);

        if (!hasVersion && !hasSource && !hasIndex) {
            // Chỉ an toàn khi đây thực sự là state khởi đầu.
            return 0;
        }

        if (!hasVersion || !hasSource || !hasIndex) {
            throw new IllegalStateException(
                    "Checkpoint is incomplete");
        }

        Object versionValue = context.get(VERSION);

        if (!(versionValue instanceof Integer version)
                || version != CURRENT_VERSION) {
            throw new IllegalStateException(
                    "Unsupported checkpoint version");
        }

        Object sourceValue = context.get(SOURCE_ID);

        if (!(sourceValue instanceof String storedSourceId)
                || !expectedSourceId.equals(storedSourceId)) {
            throw new IllegalStateException(
                    "Input source differs from checkpoint");
        }

        Object indexValue = context.get(NEXT_INDEX);

        if (!(indexValue instanceof Integer nextIndex)
                || nextIndex < 0
                || nextIndex > inputSize) {
            throw new IllegalStateException(
                    "Invalid checkpoint nextIndex");
        }

        return nextIndex;
    }

    public static void save(
            ExecutionContext context,
            String sourceId,
            int nextIndex) {

        context.putInt(VERSION, CURRENT_VERSION);
        context.putString(SOURCE_ID, sourceId);
        context.putInt(NEXT_INDEX, nextIndex);
    }
}
```

Kiểm tra đồng thời **tính đầy đủ**, **kiểu**, **version**, **source identity** và **giới hạn cursor** giúp phát hiện sớm metadata không thể khôi phục an toàn.

**Giới hạn cần hiểu:** Nếu ba key hoàn toàn không tồn tại, hàm trên trả `0` để hỗ trợ lần chạy đầu. Hàm **không tự biết** đây có phải restart của một step trước đó đã commit hay không. Với bài toán cần bảo đảm nghiêm ngặt, caller phải thêm một quy tắc kiểm tra lịch sử execution trước khi chấp nhận trạng thái rỗng, hoặc tận dụng reader chuẩn của Spring Batch có cơ chế checkpoint đã được kiểm chứng.

### 6.2. Reader dùng checkpoint đã kiểm tra

```java
import java.util.List;

import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStreamReader;

public final class RestartableInvoiceReader
        implements ItemStreamReader<String> {

    private final List<String> invoices;
    private final String sourceId;

    private int nextIndex;

    public RestartableInvoiceReader(
            List<String> invoices,
            String sourceId) {

        this.invoices = List.copyOf(invoices);
        this.sourceId = sourceId;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        nextIndex = InvoiceCheckpoint.restore(
                executionContext,
                sourceId,
                invoices.size()
        );
    }

    @Override
    public String read() {
        if (nextIndex >= invoices.size()) {
            return null;
        }

        return invoices.get(nextIndex++);
    }

    @Override
    public void update(ExecutionContext executionContext) {
        InvoiceCheckpoint.save(
                executionContext,
                sourceId,
                nextIndex
        );
    }

    @Override
    public void close() {
        // Không giữ file descriptor hoặc connection trong ví dụ.
    }
}
```

Reader này chỉ là **mẫu minh họa state/checkpoint**. Nó giả định:

1. Danh sách đầu vào và thứ tự phần tử **không thay đổi**.
2. `sourceId` thật sự gắn với nội dung/phiên bản đầu vào.
3. Chỉ một execution sử dụng một instance reader tại một thời điểm.
4. `ItemStream.update(...)` được framework gọi trong cơ chế checkpoint của step.
5. Writer và transaction của step được cấu hình đúng.

Không dùng trực tiếp kiểu reader này để đọc nguồn cập nhật liên tục, hoặc chia sẻ một instance trong multi-threaded step, mà không thiết kế thêm cơ chế đồng bộ và snapshot.

### 6.3. Khai báo bean riêng cho mỗi StepExecution

```java
import java.util.List;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemStreamReader;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
ItemStreamReader<String> invoiceReader(
        @Value("#{jobParameters['sourceId']}") String sourceId) {

    List<String> input = List.of(
            "INV-001",
            "INV-002",
            "INV-003",
            "INV-004"
    );

    return new RestartableInvoiceReader(input, sourceId);
}
```

Trong production, `List.of(...)` sẽ được thay bằng một nguồn cố định theo `sourceId`: file immutable, staging snapshot hoặc object storage version. `@StepScope` giúp instance reader thuộc đúng step execution, thay vì dùng chung trạng thái cursor của bean singleton.

Để reader tham gia lifecycle và checkpoint, Spring Batch cần nhận diện nó là `ItemStream`. Khi reader được truyền **trực tiếp** vào `StepBuilder.reader(...)` và kiểu bean thể hiện giao diện `ItemStreamReader`, framework có thể đăng ký lifecycle. Nếu nó bị ẩn sau delegate/composite writer/reader và không được đăng ký, cần thêm `.stream(delegate)` thích hợp.

## 7. Lỗi delegate ItemStream không được đăng ký

Một lỗi khó phát hiện: custom reader ở bên trong một wrapper triển khai `ItemReader`, còn wrapper không triển khai `ItemStream` và không gọi `open/update/close` cho delegate.

Ví dụ:

```java
public final class MaskingReader
        implements ItemReader<String> {

    private final ItemStreamReader<String> delegate;

    public MaskingReader(ItemStreamReader<String> delegate) {
        this.delegate = delegate;
    }

    @Override
    public String read() throws Exception {
        String value = delegate.read();
        return value == null ? null : mask(value);
    }

    private String mask(String value) {
        return value.replaceAll("\\d", "*");
    }
}
```

Nếu `MaskingReader` là reader trực tiếp của step, framework chỉ thấy một `ItemReader`. Delegate có thể không nhận `open(...)` hoặc `update(...)`, khiến trạng thái không được persist.

Một cấu hình giải thích cách đăng ký delegate:

```java
@Bean
Step maskedStep(
        JobRepository repository,
        PlatformTransactionManager tx,
        MaskingReader maskingReader,
        ItemStreamReader<String> checkpointReader,
        ItemWriter<String> writer) {

    return new StepBuilder("maskedStep", repository)
            .<String, String>chunk(100, tx)
            .reader(maskingReader)
            .writer(writer)
            .stream(checkpointReader)
            .build();
}
```

`checkpointReader` phải là **chính instance delegate** mà `maskingReader` gọi; nếu tạo hai instance khác nhau, framework có thể cập nhật state của object không trực tiếp đọc dữ liệu.

Một lựa chọn khác là để wrapper implement `ItemStreamReader` và chuyển tiếp đầy đủ `open/update/close`. Tránh vừa tự forward vừa đăng ký cùng delegate hai lần nếu dẫn đến gọi lifecycle lặp lại.

## 8. Đọc từ Job Context nhưng ghi vào Step Context — hoặc ngược lại

Hai context có thể chứa key giống nhau nhưng hoàn toàn khác nhau:

```java
ExecutionContext stepContext =
        stepExecution.getExecutionContext();

ExecutionContext jobContext =
        stepExecution.getJobExecution().getExecutionContext();

stepContext.putString("app.report.outputPath", "/data/report.csv");

// Lỗi logic: đọc từ jobContext, nơi chưa hề có key.
String output = jobContext.getString("app.report.outputPath");
```

Trong một số phiên bản API, đọc sai key có thể tạo exception; ở code khác, việc dùng default value có thể che lỗi. Điều cần làm là **xác định phạm vi của key**, không tự “thử context còn lại” nếu không thấy dữ liệu.

### 8.1. Truyền giá trị giữa step bằng JobExecutionContext

Giả sử step `generateReport` tạo ra file, step `sendReport` cần đường dẫn file ấy:

```text
generateReport (StepExecutionContext)
    |
    | promote key theo quy tắc
    v
JobExecutionContext
    |
    v
sendReport (đọc key đã promote)
```

Spring Batch cung cấp `ExecutionContextPromotionListener`:

```java
import org.springframework.batch.core.listener.ExecutionContextPromotionListener;
import org.springframework.context.annotation.Bean;

@Bean
ExecutionContextPromotionListener reportPathPromotion() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();

    listener.setKeys(new String[] {
            "app.report.outputPath"
    });

    listener.setStatuses(new String[] {
            "COMPLETED"
    });

    listener.setStrict(true);

    return listener;
}
```

Đăng ký listener vào **step tạo ra dữ liệu**:

```java
@Bean
Step generateReportStep(
        JobRepository repository,
        PlatformTransactionManager tx,
        Tasklet generateReportTasklet,
        ExecutionContextPromotionListener reportPathPromotion) {

    return new StepBuilder("generateReportStep", repository)
            .tasklet(generateReportTasklet, tx)
            .listener(reportPathPromotion)
            .build();
}
```

Ví dụ tasklet đặt giá trị tại step context:

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext context) {

    String output = generateReportAndReturnPath();

    contribution.getStepExecution()
            .getExecutionContext()
            .putString("app.report.outputPath", output);

    return RepeatStatus.FINISHED;
}
```

Ở đây `generateReportAndReturnPath()` là phương thức nghiệp vụ minh họa. Sau khi step thành công, promotion listener chuyển key đã chọn sang job context để step sau đọc:

```java
@Bean
@StepScope
Tasklet sendReportTasklet(
        @Value("#{jobExecutionContext['app.report.outputPath']}")
        String outputPath) {

    return (contribution, context) -> {
        if (outputPath == null || outputPath.isBlank()) {
            throw new IllegalStateException(
                    "Missing report output path in job context");
        }

        sendReport(outputPath);
        return RepeatStatus.FINISHED;
    };
}
```

`sendReport(...)` là một hàm nghiệp vụ được định nghĩa trong ứng dụng, không phải Spring Batch API. Ví dụ này cho thấy **step sau vẫn phải kiểm tra giá trị được promote**, thay vì dùng một đường dẫn default có thể gửi sai báo cáo.

**Lưu ý:** `ExecutionContextPromotionListener` không phải dịch vụ message bus và không bảo đảm tự động đồng bộ state cho các job khác. Nó hoạt động trong vòng đời một job, với điều kiện listener được đăng ký và trạng thái step phù hợp.

## 9. ExecutionContext không thay thế JobParameters

Một lỗi thiết kế khác là bỏ các dữ liệu định danh đầu vào vào context nhưng không ghi vào `JobParameters`.

Ví dụ job nhập file được launch với:

```text
jobName=importInvoices
run.id=123
```

Sau đó trong step:

```java
stepExecution.getExecutionContext()
        .putString("inputFile", "/data/invoices-20250512.csv");
```

Lần restart, job definition hoặc môi trường có thể không còn biết **file nào** là đầu vào chính thức cho job instance. Thậm chí code có thể chọn file “mới nhất” rồi tiếp tục từ offset của file cũ.

Ngược lại, cách thiết kế rõ:

```text
JobParameters (identifying):
  businessDate = 2025-05-12
  sourceId     = invoices-20250512-v3

Step ExecutionContext (checkpoint):
  app.invoiceReader.sourceId   = invoices-20250512-v3
  app.invoiceReader.nextIndex  = 400000
  app.invoiceReader.stateVersion = 1
```

`JobParameters` xác định dữ liệu/ý định của một `JobInstance`. `ExecutionContext` mô tả **tiến độ xử lý** trong ý định đó. Hai loại dữ liệu cần được đối chiếu, không thể thay thế cho nhau.

### 9.1. Identifying parameters và restart

Nếu thêm identifying `run.id` mới mỗi lần retry, Spring Batch có thể tạo **JobInstance khác** thay vì restart instance cũ; checkpoint của instance trước không tự áp dụng cho instance mới.

Khi cần tiếp tục job đã `FAILED` hoặc `STOPPED`, sử dụng cơ chế restart và các identifying parameters của cùng job instance. Đồng thời xem xét writer idempotency vì một chunk có thể đã được commit trước khi lỗi xảy ra.

## 10. Kiểm tra input fingerprint hoặc source version

Chỉ xác minh `nextIndex <= inputSize` vẫn chưa đủ.

Giả sử:

```text
Execution 501:
  file = invoices.csv
  nội dung dòng 1..500.000 = version A
  checkpoint = nextIndex 400.000

Trước restart:
  file invoices.csv được ghi đè bằng version B
  tổng số dòng vẫn là 500.000
```

Kiểm tra kích thước tập dữ liệu sẽ **không phát hiện** thay đổi. Restart có thể bỏ qua 400.000 dòng của version B hoặc kết hợp nửa dữ liệu A với nửa B.

Các cách bảo vệ:

- **Object storage version ID**: đọc đúng phiên bản object đã chốt.
- **Checksum/hash toàn file**: so checksum ở thời điểm launch và restart khi chi phí chấp nhận được.
- **Immutable staging table**: dữ liệu được snapshot theo `importId`; reader chỉ đọc snapshot đó.
- **Database snapshot/cutoff**: cố định phạm vi nghiệp vụ và thứ tự truy vấn.
- **Source sequence/version**: nếu API cung cấp snapshot ID ổn định.

**Không dùng timestamp sửa đổi file như dấu hiệu duy nhất** trong hệ thống yêu cầu bảo đảm cao; timestamp có thể bị thay đổi hoặc không đủ phân giải. `sourceId` nên gắn với một version thực sự của dữ liệu.

### 10.1. Đừng lưu payload lớn vào ExecutionContext

Để tránh re-read file, có người lưu cả danh sách 100.000 bản ghi vào context:

```java
// Không nên:
context.put("allInvoices", hundredThousandInvoices);
```

Điều này làm metadata phình to, serializer có thể không xử lý được custom object, và mỗi checkpoint có thể gây overhead lớn. Thay vào đó:

```text
JobParameters:
  sourceId=invoices-20250512-v3

Step ExecutionContext:
  nextIndex=400000
  cursorVersion=1
```

Dữ liệu gốc nên nằm ở nguồn bền vững phù hợp; context chỉ chứa state nhỏ đủ để tái xác định vị trí xử lý.

## 11. Kiểu dữ liệu và serialization: đừng lưu object tùy ý

`ExecutionContext` có thể chứa key–value, nhưng không phải mọi object Java đều có thể được lưu và khôi phục an toàn qua `JobRepository`.

Ví dụ không phù hợp:

```java
context.put("httpClient", new HttpClient(...));
context.put("jdbcConnection", connection);
context.put("openInputStream", inputStream);
```

Một HTTP client, JDBC connection hoặc stream mở là tài nguyên runtime, không thể khôi phục hợp lệ ở JVM mới. Có thể gặp lỗi serialization hoặc giá trị được khôi phục nhưng không còn ý nghĩa.

Ưu tiên:

- `String` cho source ID, cursor token nhỏ, enum code.
- `int`/`long` cho offset, page index và version.
- `boolean` cho một flag trạng thái có semantics rõ.
- Giá trị thời gian ở dạng chuỗi ISO hoặc một biểu diễn được chính sách serialization của ứng dụng hỗ trợ.
- Các object phức tạp cần serializer tương thích và chính sách migration rõ ràng; thông thường nên tránh.

### 11.1. Không nhầm getInt và getLong

```java
// Writer phiên bản cũ:
context.putLong("app.reader.offset", 400000L);

// Reader phiên bản mới không được giả định kiểu Integer:
Object rawOffset = context.get("app.reader.offset");

if (!(rawOffset instanceof Long offset)) {
    throw new IllegalStateException("Unexpected offset type");
}
```

Nếu cần đổi từ `long` sang `int`, kiểm tra `offset` có nằm trong `Integer.MIN_VALUE..MAX_VALUE` và có ngữ nghĩa hợp lệ trước khi chuyển. Không cast trực tiếp một `Long` thành `Integer`.

### 11.2. Bảo vệ dữ liệu nhạy cảm

Không lưu access token, mật khẩu, secret key hoặc payload nhạy cảm vào `ExecutionContext`. Metadata có thể được ghi xuống database và xuất hiện trong công cụ vận hành, backup hoặc dump.

Nếu step cần gọi API khi restart, lưu **định danh cấu hình/secret reference** không nhạy cảm và lấy credential mới từ secret manager an toàn, thay vì checkpoint token cũ trong context.

### 11.3. Thay đổi serializer và phiên bản thư viện

Cơ chế serialize `ExecutionContext` trong `JobRepository` phụ thuộc Spring Batch và cấu hình serializer. Một lần nâng cấp framework hoặc thay serializer có thể khiến dữ liệu checkpoint cũ không đọc được.

Trước khi đổi serializer:

1. Xác định có job `FAILED`/`STOPPED` đang chờ restart không.
2. Kiểm tra cách đọc dữ liệu context do phiên bản cũ ghi.
3. Chuẩn bị migration hoặc chiến lược xử lý job cũ.
4. Thử nghiệm restart trên bản sao dữ liệu metadata thực tế.
5. Không tự chỉnh chuỗi serialized trực tiếp trong database nếu không có công cụ/phương án kiểm chứng rõ ràng.

## 12. Kiểm tra context theo lifecycle, không chỉ lúc đọc từng item

Validation checkpoint nên đặt tại điểm phù hợp:

| Thời điểm | Kiểm tra gì? | Phản ứng |
|---|---|---|
| **Trước khi job launch** | `JobParameters`, source ID, ngày nghiệp vụ, quyền đọc nguồn | Từ chối yêu cầu không hợp lệ |
| **ItemStream.open** | Key tồn tại/đúng kiểu, state version, source identity, cursor range | Fail fast nếu checkpoint không khôi phục an toàn |
| **Trong read** | Item có hợp đồng dữ liệu hợp lệ không; cursor tiến thế nào | Process/skip/fail theo chính sách |
| **ItemStream.update** | State sắp lưu có hợp lệ và bền vững không | Ghi checkpoint nhỏ, nhất quán |
| **Sau chunk commit** | Writer result, số item, kiểm soát side effect | Đối soát/metrics, tránh giả định state = data commit |
| **Giữa các step** | Key promoted đã tồn tại, output thật đã sẵn sàng | Chặn downstream nếu thiếu |
| **Trước restart** | Execution trước, nguồn, checkpoint, idempotency | Khôi phục có kiểm soát |

**Không ghi điều kiện “nếu key không có thì cứ làm tiếp” khắp nơi**. Cần một policy rõ: key nào optional, key nào bắt buộc và vì sao.

### 12.1. Fail fast tốt hơn âm thầm đọc sai

Nếu reader được yêu cầu resume tại vị trí 400.000 nhưng context chứa `-1`, việc sửa tự động thành `0` sẽ biến một lỗi metadata có thể phát hiện thành một cuộc import lại toàn bộ dữ liệu.

```java
if (checkpointIndex < 0 || checkpointIndex > inputSize) {
    throw new IllegalStateException(
            "Checkpoint is invalid; manual recovery required");
}
```

Sau khi fail, người vận hành có thể điều tra source ID, metadata, output đã commit và quyết định có thể restart hay phải rebuild staging. Với dữ liệu quan trọng, **từ chối một restart không thể xác minh** thường an toàn hơn hoàn tất với dữ liệu sai.

## 13. Restart và transaction: checkpoint phải nhất quán với writer

`ExecutionContext` không bảo đảm **exactly once** cho mọi side effect. Nó là cơ chế state phối hợp với transaction và reader/writer.

Xét hai chunk:

```text
Chunk 1:
  read INV-001 ... INV-100
  write 100 invoices
  ItemStream.update(nextIndex=100)
  commit

Chunk 2:
  read INV-101 ... INV-200
  write gây lỗi
  transaction rollback
  không có commit chunk 2

Restart:
  khôi phục checkpoint đã commit (nextIndex=100)
  đọc lại INV-101...
```

Nếu writer tham gia cùng transaction JDBC được step quản lý, thay đổi chưa commit của chunk 2 rollback cùng transaction. Nhưng nếu writer gọi email, HTTP hoặc ghi file ở nơi **không rollback theo database transaction**, những side effect này có thể đã xảy ra và sẽ bị lặp khi retry/restart.

### 13.1. Không dùng checkpoint làm bằng chứng business commit

Đừng viết:

```java
if (context.getInt("nextIndex") == 200) {
    // Sai: tự kết luận 200 invoice đã commit trên mọi hệ thống.
}
```

Nên kiểm tra dữ liệu đích bằng business key, transaction log hoặc outbox/inbox khi yêu cầu tính nhất quán cao. `writeCount` và `readCount` từ `StepExecution` cũng là counter Batch, không thay thế kiểm chứng số dòng database thực sự commit.

### 13.2. Idempotent writer là lớp bảo vệ bổ sung

Nếu bản ghi có khóa `invoiceId`, bảng database có thể dùng `UNIQUE(invoice_id)` hoặc upsert có điều kiện theo version để tránh chèn trùng khi retry.

```sql
CREATE TABLE invoices (
    invoice_id VARCHAR(80) PRIMARY KEY,
    amount NUMERIC(18, 2) NOT NULL
);
```

Tùy nghiệp vụ, một writer có thể `INSERT ... ON CONFLICT DO NOTHING`, hoặc kiểm tra xung đột payload để từ chối nếu cùng invoice ID nhưng amount khác. **Không dùng `DO NOTHING` để che mọi xung đột dữ liệu**.

### 13.3. Không tự sửa ExecutionContext trong database

Spring Batch có bảng metadata `BATCH_STEP_EXECUTION_CONTEXT` và `BATCH_JOB_EXECUTION_CONTEXT`. Việc chỉnh trực tiếp các cột serialized `SHORT_CONTEXT`/`SERIALIZED_CONTEXT` có thể làm hỏng dữ liệu hoặc khiến các key không còn nhất quán.

Nếu cần khôi phục sau metadata lỗi, nên có quy trình backup, đối chiếu source/output và công cụ migration có kiểm soát. Không copy thủ công context từ execution khác chỉ vì hai job có tên giống nhau.

## 14. Key từ StepExecutionContext không tự xuất hiện ở JobExecutionContext

Đây là lỗi phổ biến khi một step tạo file rồi step sau muốn dùng file đó.

```text
Step A:
  stepContext["reportPath"] = "/data/report.csv"

Step B:
  jobContext["reportPath"]  -> không có key
```

Lý do: hai context là **hai map khác phạm vi**. Spring Batch không tự chuyển mọi key từ step context sang job context. Cần một chiến lược rõ như `ExecutionContextPromotionListener` hoặc ghi job context tại điểm được thiết kế phù hợp.

Ngay cả khi đã promote:

- Key chỉ được copy khi listener chạy và policy status phù hợp.
- Step B phải validate giá trị.
- Đường dẫn file hoặc object ID cần được kiểm tra tồn tại/phiên bản khi đọc.
- Nếu step A đã hoàn tất ở execution trước và step B được restart, cần xác nhận job context đã được khôi phục đúng.

**Không dùng giá trị mặc định như `"/tmp/report.csv"` để che việc promotion bị thiếu**. Có thể gửi nhầm báo cáo của một ngày nghiệp vụ khác.

## 15. Những lỗi thường gặp với key, kiểu và phạm vi

| Lỗi | Biểu hiện | Hậu quả | Cách phòng |
|---|---|---|---|
| Không dùng `containsKey`/type check | Exception hoặc default sai | Restart sai offset | Validation trong `open` |
| Dùng `getInt` cho giá trị `long` | Lỗi kiểu | Job fail khi upgrade | Schema type ổn định/migration |
| Đổi tên key sau deploy | Key “biến mất” | Đọc lại dữ liệu | Version checkpoint và migration |
| Key quá chung như `offset` | Component khác ghi đè | Checkpoint sai | Namespaced keys |
| Dùng Job context thay Step context | Không thấy checkpoint reader | Restart từ đầu | Dùng đúng scope |
| Không promote output giữa step | Step sau không thấy file | Flow lỗi hoặc dùng default | Promotion listener + validation |
| Không đăng ký delegate `ItemStream` | `open/update` không được gọi | Không có checkpoint | `.stream(delegate)` hoặc forward lifecycle |
| Lưu cả List/Stream/Connection | Serializer lỗi, metadata lớn | Không restart được | Lưu chỉ ID và cursor nhỏ |
| Lưu secret/token | Metadata tiết lộ credential | Rủi ro bảo mật | Secret manager, reference không nhạy cảm |
| Không xác minh source version | Offset trỏ file đã thay đổi | Mất/nhầm bản ghi | Immutable source/version/checksum |
| Ghi offset trước khi writer commit | Checkpoint vượt dữ liệu đã ghi | Bỏ sót item | Tuân theo transaction/checkpoint lifecycle |
| Dùng `readCount` làm cursor | Có filter/skip/retry | Sai vị trí nguồn | Reader tự lưu state đúng ngữ nghĩa |
| Share reader singleton nhiều thread | Cursor race condition | Trùng/bỏ sót item | `@StepScope` và thiết kế concurrency |
| Lưu checkpoint ở Job context mỗi item | Không có commit boundary phù hợp | State không nhất quán | Step context + `ItemStream` |
| Không test restart | Production mới phát hiện mất state | Mất dữ liệu | Test failure rồi restart thực |
| Tự sửa metadata DB | Serialized context hỏng | Không restart, khó điều tra | Quy trình khôi phục có kiểm soát |

## 16. Vì sao không dùng StepExecution.readCount làm checkpoint?

Một quan niệm dễ gặp: số item đã đọc chính là vị trí trong file, vậy chỉ cần lưu `readCount` thay vì cursor riêng.

Điều đó có thể sai khi:

- Reader bỏ qua header hoặc comment line.
- Có dòng parse lỗi và `skip in read`.
- Item bị filter ở processor.
- Retry/rollback làm item được đọc lại.
- API paging hoặc partitioning không có quan hệ 1:1 giữa item và offset.
- Reader trả một item từ nhiều dòng hoặc một dòng tạo nhiều item.

Ví dụ:

```text
File:
  line 1 = header
  line 2 = INV-001 hợp lệ
  line 3 = INVALID (skip in read)
  line 4 = INV-002 hợp lệ

readCount=2
readSkipCount=1
actual next file line=5
```

Nếu restart bằng “bỏ qua `readCount=2` dòng”, reader có thể bắt đầu sai vị trí. `FlatFileItemReader` có cơ chế lưu state và xử lý line mapping riêng; với custom reader cần thiết kế cursor theo **vị trí thực của nguồn** chứ không suy ra từ một counter nghiệp vụ.

## 17. Multithreading, partitioning và context

Một `ExecutionContext` là state gắn với **một `StepExecution`**; nó không tự cung cấp khóa phân tán hay cơ chế merge dữ liệu giữa worker.

### 17.1. Multi-threaded step

Nếu nhiều thread gọi cùng một `ItemStreamReader` có field `nextIndex` mutable, có thể xảy ra:

```text
Thread A đọc nextIndex=100
Thread B đọc nextIndex=100
A tăng lên 101
B tăng lên 101
Cùng một item có thể được đọc hai lần
```

Một số reader không thread-safe; nhiều reader trong Spring Batch có tùy chọn state/restart không tương thích hoàn toàn với mô hình đa luồng nếu không thêm đồng bộ. Phải đánh giá thread-safety của reader, cách chia input và khả năng checkpoint nhất quán. Chỉ đặt `@StepScope` không tự biến reader thành thread-safe nếu chính step chạy nhiều thread trên cùng instance.

### 17.2. Partitioned step

Một partition có thể có tham số vùng dữ liệu riêng:

```text
manager StepExecution
    |
    +-- worker partition 0
    |     stepContext: minId=1, maxId=100000, nextId=35000
    |
    +-- worker partition 1
    |     stepContext: minId=100001, maxId=200000, nextId=160000
    |
    +-- worker partition 2
          stepContext: minId=200001, maxId=300000, nextId=240000
```

Mỗi worker cần kiểm tra:

- `minId`, `maxId` và `nextId` có kiểu/giới hạn đúng không.
- Partition range không chồng lấp ngoài chủ đích.
- Một restart sử dụng đúng key và vùng dữ liệu của partition tương ứng.
- Dữ liệu nguồn không thay đổi làm mất ý nghĩa của `nextId`.

Không gom mọi cursor của partition vào một biến `"lastProcessedId"` trong job context rồi kỳ vọng các worker không ghi đè nhau. Kết quả merge/aggregate cần có quy tắc riêng, phù hợp với semantics của partition.

### 17.3. Remote workers

Nếu worker chạy ở JVM khác, object reference trong context của manager không phải cách truyền state. Các khóa cần được serialize và gửi/đọc bằng cơ chế partitioning/remote execution phù hợp. Không cho rằng việc sửa map context trong một JVM sẽ tự làm map ở JVM khác thay đổi ngay lập tức.

## 18. Unit test checkpoint: không cần chạy cả Batch infrastructure

Hàm `InvoiceCheckpoint` ở phần trên có thể được kiểm tra với `ExecutionContext` trong bộ nhớ.

### 18.1. Test fresh state

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;

class InvoiceCheckpointTest {

    @Test
    void emptyContextStartsAtZero() {
        ExecutionContext context = new ExecutionContext();

        assertEquals(
                0,
                InvoiceCheckpoint.restore(context, "file-v1", 100)
        );
    }
}
```

Điều kiện “empty context ⇒ bắt đầu từ zero” chỉ đúng khi **caller bảo đảm đây là lần chạy mới hoặc một trường hợp restart chưa có checkpoint hợp lệ**. Unit test kiểm tra thuật toán, không chứng minh metadata của mọi execution phù hợp giả định ấy.

### 18.2. Test lưu và khôi phục cursor

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;

class InvoiceCheckpointRoundTripTest {

    @Test
    void restoresSavedPosition() {
        ExecutionContext context = new ExecutionContext();

        InvoiceCheckpoint.save(context, "file-v1", 42);

        assertEquals(
                42,
                InvoiceCheckpoint.restore(context, "file-v1", 100)
        );
    }
}
```

### 18.3. Test thiếu key bắt buộc

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;

class InvoiceCheckpointMissingKeyTest {

    @Test
    void partialCheckpointMustFail() {
        ExecutionContext context = new ExecutionContext();

        context.putInt(InvoiceCheckpoint.VERSION, 1);
        context.putInt(InvoiceCheckpoint.NEXT_INDEX, 42);
        // Thiếu SOURCE_ID.

        assertThrows(
                IllegalStateException.class,
                () -> InvoiceCheckpoint.restore(
                        context, "file-v1", 100)
        );
    }
}
```

### 18.4. Test đổi nguồn, version, giá trị âm và cursor vượt giới hạn

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;

class InvoiceCheckpointValidationTest {

    @Test
    void rejectsSourceChange() {
        ExecutionContext context = new ExecutionContext();

        InvoiceCheckpoint.save(context, "file-v1", 10);

        assertThrows(
                IllegalStateException.class,
                () -> InvoiceCheckpoint.restore(
                        context, "file-v2", 100)
        );
    }

    @Test
    void rejectsUnsupportedVersion() {
        ExecutionContext context = new ExecutionContext();

        InvoiceCheckpoint.save(context, "file-v1", 10);
        context.putInt(InvoiceCheckpoint.VERSION, 99);

        assertThrows(
                IllegalStateException.class,
                () -> InvoiceCheckpoint.restore(
                        context, "file-v1", 100)
        );
    }

    @Test
    void rejectsNegativeOffset() {
        ExecutionContext context = new ExecutionContext();

        InvoiceCheckpoint.save(context, "file-v1", -1);

        assertThrows(
                IllegalStateException.class,
                () -> InvoiceCheckpoint.restore(
                        context, "file-v1", 100)
        );
    }

    @Test
    void rejectsOffsetPastEnd() {
        ExecutionContext context = new ExecutionContext();

        InvoiceCheckpoint.save(context, "file-v1", 101);

        assertThrows(
                IllegalStateException.class,
                () -> InvoiceCheckpoint.restore(
                        context, "file-v1", 100)
        );
    }

    @Test
    void rejectsUnexpectedValueType() {
        ExecutionContext context = new ExecutionContext();

        InvoiceCheckpoint.save(context, "file-v1", 10);
        context.putString(InvoiceCheckpoint.NEXT_INDEX, "ten");

        assertThrows(
                IllegalStateException.class,
                () -> InvoiceCheckpoint.restore(
                        context, "file-v1", 100)
        );
    }
}
```

Các test này tập trung đúng vào lỗi **không kiểm tra context**. Chúng nhanh, không cần `Thread.sleep(...)`, không phụ thuộc clock, network hay dữ liệu ngẫu nhiên.

### 18.5. Test lifecycle của reader

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.batch.item.ExecutionContext;

class RestartableInvoiceReaderTest {

    @Test
    void readerResumesFromSavedIndex() throws Exception {
        ExecutionContext context = new ExecutionContext();

        RestartableInvoiceReader first =
                new RestartableInvoiceReader(
                        List.of("A", "B", "C", "D"),
                        "file-v1"
                );

        first.open(context);
        assertEquals("A", first.read());
        assertEquals("B", first.read());

        // Mô phỏng framework gọi update ở checkpoint đã commit.
        first.update(context);
        first.close();

        RestartableInvoiceReader restarted =
                new RestartableInvoiceReader(
                        List.of("A", "B", "C", "D"),
                        "file-v1"
                );

        restarted.open(context);
        assertEquals("C", restarted.read());
        assertEquals("D", restarted.read());
        assertEquals(null, restarted.read());
        restarted.close();
    }
}
```

Test dùng lại `ExecutionContext` trong bộ nhớ để minh họa round-trip của state. **Nó chưa mô phỏng transaction rollback hoặc serialization thực của `JobRepository`.** Những yêu cầu đó cần integration test.

## 19. Integration test: failure giữa chunk và restart thật

Để khẳng định checkpoint có thể dùng trong production, nên viết integration test có:

1. `JobRepository` thật (ví dụ H2 cho test logic; database tương tự production cho kiểm chứng transaction quan trọng).
2. Reader `ItemStreamReader` được đăng ký đúng.
3. Writer JDBC dùng cùng transaction manager với step.
4. Lỗi được kích hoạt có kiểm soát **sau một số chunk đã commit**.
5. Restart cùng `JobInstance`, qua `JobOperator.restart(...)` hoặc `JobLauncher` theo cơ chế phù hợp.
6. Đối soát bảng đích sau restart: đủ dữ liệu, không có duplicate, không thiếu item.

Sơ đồ kịch bản:

```text
Input immutable: A, B, C, D, E, F
chunk size = 2

Execution 501:
  chunk 1: A, B -> commit
  chunk 2: C, D -> commit
  chunk 3: E, F -> writer cố ý lỗi -> rollback
  Step FAILED

Execution 509 (restart):
  khôi phục reader tại checkpoint sau D
  chunk 3: E, F -> commit
  Job COMPLETED

Output cuối:
  A, B, C, D, E, F (mỗi item đúng một lần)
```

Trong test, dùng writer giả lập phát sinh lỗi một lần dựa trên **cờ của test harness nằm ngoài transaction**, sau đó restart và cho writer chạy bình thường. Không nên dùng một biến đếm trong processor và giả định nó rollback cùng database.

### 19.1. Cách tạo tham số run ổn định

```java
JobParameters params = new JobParametersBuilder()
        .addString("sourceId", "file-v1", true)
        .addString("businessDate", "2025-05-12", true)
        .toJobParameters();
```

Khi restart, không thêm identifying `run.id` khác để tạo job instance mới. Nếu cần chạy nhiều test độc lập, tạo `JobRepository`/schema test sạch hoặc dùng source ID khác **giữa các test khác nhau**, chứ không đổi tham số giữa hai execution đang được kiểm tra restart.

### 19.2. Điều gì cần assert?

```java
// Ý tưởng assertions sau khi restart hoàn tất:
assertEquals(BatchStatus.COMPLETED, restarted.getStatus());

List<String> ids = jdbcTemplate.queryForList(
        "SELECT invoice_id FROM invoices ORDER BY invoice_id",
        String.class
);

assertEquals(List.of("A", "B", "C", "D", "E", "F"), ids);
```

Đây là đoạn assertion minh họa, giả định schema và dữ liệu được tạo trong test. Ngoài kết quả cuối, cần xem `StepExecution` của execution cũ/mới và checkpoint đã được persist; nếu không, writer idempotent có thể che lỗi reader đã đọc lại từ đầu. Để kiểm chứng reader thực sự resume, có thể ghi lại **item ID được reader trả về ở execution restart** trong test fixture.

### 19.3. Test mất hoặc sai context

Ngoài happy path, cần kiểm thử:

- Context sau commit chứa thiếu một key checkpoint.
- `stateVersion` không hỗ trợ.
- `sourceId` không trùng với `JobParameters`.
- `nextIndex` vượt độ dài input.
- Key sai kiểu (ví dụ chuỗi thay vì số).
- Reader delegate không được đăng ký `ItemStream`.
- File nguồn thay đổi nội dung nhưng giữ nguyên tên.
- Job context thiếu key được promote từ step trước.
- Hai partition dùng trùng tên key và bị map state sai.
- Serializer thay đổi và không đọc được metadata cũ.

Các trường hợp này phải tạo lỗi **có thể giải thích**, thay vì âm thầm reset checkpoint và làm job `COMPLETED` với dữ liệu thiếu.

## 20. Quan sát ExecutionContext khi vận hành

Khi job `FAILED` hoặc `STOPPED` và không thể restart, người vận hành cần xem:

- `JobInstance`: tên job và identifying parameters.
- `JobExecution`: status, thời điểm bắt đầu/kết thúc, failure exceptions.
- `StepExecution`: status, read/write/skip/rollback/commit counters.
- **Step ExecutionContext**: tên key, phiên bản state, source ID, cursor hoặc page token.
- **Job ExecutionContext**: giá trị được chia sẻ giữa các step, có promotion hay không.
- Nguồn dữ liệu: file/object version, snapshot ID, checksum.
- Đích dữ liệu: bản ghi đã commit và side effect ngoài transaction.

Spring Batch có API `JobExplorer` để đọc metadata:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.item.ExecutionContext;

public final class CheckpointInspector {

    private final JobExplorer explorer;

    public CheckpointInspector(JobExplorer explorer) {
        this.explorer = explorer;
    }

    public void inspect(long jobExecutionId) {
        JobExecution job =
                explorer.getJobExecution(jobExecutionId);

        if (job == null) {
            throw new IllegalArgumentException(
                    "Unknown JobExecution " + jobExecutionId);
        }

        for (StepExecution step : job.getStepExecutions()) {
            ExecutionContext state = step.getExecutionContext();

            System.out.println("stepName=" + step.getStepName());
            System.out.println("status=" + step.getStatus());
            System.out.println("stepExecutionId=" + step.getId());

            // Chỉ đọc whitelist key an toàn, không dump toàn map.
            if (state.containsKey(InvoiceCheckpoint.SOURCE_ID)) {
                System.out.println(
                        "sourceId="
                                + state.getString(
                                        InvoiceCheckpoint.SOURCE_ID));
            }

            if (state.containsKey(InvoiceCheckpoint.NEXT_INDEX)) {
                Object raw = state.get(InvoiceCheckpoint.NEXT_INDEX);
                System.out.println("nextIndex=" + raw);
            }
        }
    }
}
```

**Không log toàn bộ `ExecutionContext` bằng `toString()`** nếu chưa biết nó chứa gì. Context có thể chứa identifier, đường dẫn nội bộ, token do ứng dụng lưu sai và những giá trị cần kiểm soát quyền truy cập. Trang quản trị nên hiển thị whitelist key an toàn và có quyền truy vấn rõ ràng.

### 20.1. Đọc metadata từ database

Schema Spring Batch thường dùng hai bảng:

```text
BATCH_STEP_EXECUTION_CONTEXT
  STEP_EXECUTION_ID
  SHORT_CONTEXT
  SERIALIZED_CONTEXT

BATCH_JOB_EXECUTION_CONTEXT
  JOB_EXECUTION_ID
  SHORT_CONTEXT
  SERIALIZED_CONTEXT
```

Tên bảng, cột và cách mã hóa context phụ thuộc phiên bản/schema/prefix cấu hình. Đọc trực tiếp có thể hữu ích khi điều tra, nhưng **không nên chỉnh sửa serialized context thủ công**. Cách dùng `JobExplorer` giúp ứng dụng tôn trọng lớp serialization của framework.

### 20.2. Metrics nào hữu ích?

Ngoài duration của step, nên theo dõi:

| Chỉ số | Mục đích |
|---|---|
| Số job restart thất bại do invalid checkpoint | Phát hiện thay đổi code hoặc source bất thường |
| Số lần `sourceId` mismatch | Phát hiện file/version bị thay |
| Số context serialization errors | Phát hiện object không phù hợp hoặc nâng cấp serializer |
| Step `FAILED` theo nhóm nguyên nhân | Phân biệt lỗi metadata, input và writer |
| `readCount`, `writeCount`, `rollbackCount` | Đối chiếu tiến độ với transaction |
| Lần checkpoint cuối và thời gian không tiến độ | Phát hiện step đang treo |
| Số lần restart của một `JobInstance` | Đánh giá độ ổn định của pipeline |

Đây là các metric **do ứng dụng/giám sát thiết kế**, không phải tất cả đều được Spring Batch tự tạo. Đừng đưa từng `jobExecutionId`, `sourceId` hoặc nội dung context làm label Prometheus; chúng có thể tạo high cardinality. Dùng log/audit có phân quyền để truy chi tiết.

## 21. Xử lý sự cố: restart báo thiếu ExecutionContext

Một quy trình vận hành an toàn:

1. **Xác nhận đang restart đúng instance.** Đối chiếu tên job, identifying parameters và execution cũ.
2. **Đọc trạng thái execution/step.** `FAILED`, `STOPPED` hay metadata kẹt `STARTED`? Không tự coi mọi state là restartable.
3. **Xác minh reader đã đăng ký ItemStream.** Có `open/update/close` được gọi trong cấu hình hiện tại không?
4. **Kiểm tra key và version.** Có thay tên bean, reader, namespace key hoặc serializer sau deploy không?
5. **Đối chiếu nguồn.** Source ID, checksum và định dạng có còn đúng không?
6. **Đối chiếu dữ liệu đã ghi.** Chunk nào đã commit? Writer có side effect ngoài transaction không?
7. **Chọn recovery có kiểm soát.** Sửa cấu hình/migrate checkpoint khi có bằng chứng; nếu không thể khôi phục, tạo một quá trình reprocess mới có cơ chế dedup/reconciliation.
8. **Bổ sung regression test.** Tái tạo trạng thái context lỗi trong test để tránh lặp lại.

**Không nên:**

```java
try {
    return context.getInt("nextIndex");
} catch (Exception ignored) {
    return 0; // Che mọi lỗi checkpoint bằng việc đọc lại từ đầu.
}
```

Mẫu này biến lỗi schema, type hoặc nguồn bị thay thành kết quả bất ngờ. Nếu nghiệp vụ cho phép reprocess từ đầu, đó phải là **quyết định rõ ràng**, kèm writer idempotency và audit, không phải fallback mặc định của mọi exception.

## 22. Bài tập thực hành

Xây job `syncInvoiceSnapshot` đọc một danh sách hóa đơn bất biến từ snapshot có `sourceId` và ghi vào bảng `invoices`. Step dùng `chunk(100)`.

Yêu cầu:

1. Định nghĩa `JobParameters` gồm `businessDate` và `sourceId`. Phân biệt identifying parameters với cursor lưu trong `StepExecutionContext`.
2. Viết `ItemStreamReader<Invoice>` có `open/read/update/close`, lưu `stateVersion`, `sourceId` và `nextIndex`.
3. Trong `open(...)`, từ chối context thiếu một phần key, version lạ, sai kiểu, index âm hoặc vượt giới hạn input.
4. Thiết kế snapshot source bất biến và checksum/version phù hợp để ngăn restart trên dữ liệu đã đổi.
5. Tạo writer JDBC có ràng buộc unique theo `invoiceId`, bảo đảm idempotency khi retry/restart.
6. Chạy test failure sau 2 chunk đã commit, rồi restart; xác nhận không thiếu hoặc trùng hóa đơn.
7. Cố ý xóa một checkpoint key khi chuẩn bị test recovery, xác nhận reader fail fast thay vì đặt lại cursor.
8. Đổi `sourceId` từ `file-v1` sang `file-v2` nhưng giữ cùng số item; xác nhận mismatch được phát hiện.
9. Tạo wrapper `ItemReader` quanh delegate `ItemStreamReader`; bỏ `.stream(delegate)` để tái hiện lỗi lifecycle, sau đó sửa và kiểm tra.
10. Tạo hai step: step A sinh `reportPath` vào step context và step B đọc job context. Dùng `ExecutionContextPromotionListener`, kiểm tra khi không có key hoặc status không phù hợp.
11. Thử thay `nextIndex` từ `Integer` sang `Long` và viết test cho migration có kiểm tra phạm vi.
12. Thiết kế trang vận hành chỉ hiển thị whitelist checkpoint keys và metadata cần thiết, không dump secret hay payload.

**Câu hỏi ôn tập:** Một step đã ghi 400.000 invoice, khi restart `ExecutionContext` không có key `nextIndex`. Có nên mặc định bắt đầu từ 0 để job “chạy được” không?

**Trả lời:** **Không nên tự động.** Trước hết phải xác định đây là state khởi đầu hợp lệ hay checkpoint bị mất, đối chiếu trạng thái chunk đã commit và writer idempotency. Nếu không chứng minh được reprocess từ đầu là an toàn, hãy fail fast và thực hiện recovery có kiểm soát.

## 23. Tài liệu tham khảo

- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `open`, `update`, `close` và persist state trong `ExecutionContext`.
- [Spring Batch Reference — Registering ItemStream with a Step](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/registering-item-streams.html): đăng ký delegate `ItemStream` thông qua `.stream(...)`.
- [Spring Batch Reference — Common Batch Patterns](https://docs.spring.io/spring-batch/reference/common-patterns.html): các patterns đọc/ghi, restart và xử lý state.
- [Spring Batch Reference — Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `JobExecution`, `StepExecution` và phạm vi `ExecutionContext`.
- [Spring Batch Reference — Configuring a Step](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): chunk, transaction và checkpoint.
- [Spring Batch Reference — Execution Context Promotion](https://docs.spring.io/spring-batch/reference/common-patterns.html): sử dụng `ExecutionContextPromotionListener` giữa các step.
- [Spring Batch 5.2 API — ExecutionContext](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/item/ExecutionContext.html): các phương thức `containsKey`, `get`, `putInt`, `getInt`, `putString`.
- [Spring Batch 5.2 API — ItemStream](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/item/ItemStream.html): hợp đồng vòng đời của reader/writer có state.
- [Spring Batch Reference — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): các bảng lưu job/step execution context.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): kiểm thử step/job và các tình huống restart.
