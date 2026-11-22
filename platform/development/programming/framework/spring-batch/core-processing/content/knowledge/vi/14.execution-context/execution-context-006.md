# State không serialize được

`ExecutionContext` là vùng lưu trạng thái mà Spring Batch dùng để tiếp tục công việc sau khi một step hoặc job bị dừng hay thất bại. Reader có thể lưu vị trí đọc cuối cùng, tasklet có thể lưu khóa bản ghi đã xử lý, và step có thể khôi phục những giá trị đó khi restart.

Khi dùng `JobRepository` lưu metadata bền vững, trạng thái trong `ExecutionContext` phải được chuyển thành dạng mà serializer đã cấu hình có thể lưu và đọc lại. Nếu đưa vào context một đối tượng không serialize được, việc lưu checkpoint có thể thất bại. Một object có vẻ đơn giản vẫn có thể không hợp lệ nếu bên trong nó giữ một stream, connection, thread hoặc một object khác không serialize được.

Nguyên tắc thực tế là chỉ lưu dữ liệu trạng thái nhỏ, ổn định và có thể khôi phục; không lưu các tài nguyên runtime đang mở. Hãy lưu thông tin đủ để mở lại tài nguyên và tiếp tục từ điểm đã commit.

## 1. Vì sao ExecutionContext cần serialize?

`ExecutionContext` là một map key/value gắn với `JobExecution` hoặc `StepExecution`. Spring Batch lưu context cùng metadata để có thể khôi phục trạng thái khi ứng dụng khởi động lại hoặc khi job được restart.

```text
ItemReader / Tasklet / ItemStream
              |
              v
       ExecutionContext
       { lastId: 4200,
         inputFile: "orders.csv" }
              |
              v
       ExecutionContextSerializer
              |
              v
         JobRepository
              |
              v
      Lưu metadata bền vững
```

Với JDBC `JobRepository`, context cần được serialize trước khi ghi vào các bảng metadata. Khi khôi phục execution, Spring Batch đọc dữ liệu đã lưu và deserialize thành các giá trị trong context.

Serializer cụ thể phụ thuộc phiên bản và cấu hình hạ tầng batch. Cấu hình JDBC tiêu chuẩn thường dùng serializer dựa trên Java serialization; ứng dụng cũng có thể cấu hình serializer khác, chẳng hạn serializer dựa trên JSON. Dù dùng serializer nào, mọi giá trị phải phù hợp với hợp đồng serialize/deserialize của serializer đó.

## 2. Đối tượng không serialize được gây lỗi ở đâu?

Một lỗi phổ biến là đưa thẳng tài nguyên runtime vào context:

```java
ExecutionContext context = stepExecution.getExecutionContext();
context.put("inputStream", new FileInputStream("orders.csv"));
```

`FileInputStream` đại diện cho một file đang mở trong tiến trình hiện tại. Nó chứa trạng thái tài nguyên hệ điều hành và không phải dữ liệu checkpoint phù hợp để serialize. Khi repository cố lưu context, serializer có thể thất bại với lỗi serialization (ví dụ nguyên nhân gốc là `NotSerializableException` nếu dùng Java serialization).

Lỗi không nhất thiết xảy ra ngay tại dòng `put`. `ExecutionContext` có thể nhận object vào map trước; lỗi chỉ xuất hiện khi Spring Batch serialize context để cập nhật metadata, thường ở ranh giới lưu trạng thái của step hoặc chunk. Vì vậy, log có thể cho thấy lỗi xảy ra lúc commit hoặc cập nhật JobRepository dù dòng code đưa object vào context nằm trước đó.

Không nên chỉ bắt exception serialization rồi tiếp tục job. Nếu checkpoint không được lưu, job có thể không khôi phục đúng vị trí sau restart.

## 3. Serializable phải áp dụng cho toàn bộ object graph

Với Java serialization, đánh dấu class ngoài cùng `implements Serializable` là chưa đủ. Mọi object được tham chiếu trong object graph cần serialize được, trừ các field được loại trừ có chủ đích và có thể khởi tạo lại sau khi deserialize.

Ví dụ class sau vẫn có thể lỗi:

```java
public class ImportState implements Serializable {
    private String inputFile;
    private InputStream inputStream; // Không serialize được
}
```

Dù `ImportState` triển khai `Serializable`, field `inputStream` vẫn không thể được serialize theo cách Java serialization thông thường. Một field lồng sâu trong object cũng có thể gây lỗi tương tự.

Các trường hợp thường không phù hợp để lưu trực tiếp:

- `InputStream`, `OutputStream`, `Reader`, `Writer` hoặc file handle đang mở.
- JDBC `Connection`, `Statement`, `ResultSet` hoặc transaction resource.
- JPA `EntityManager`, session hoặc persistence context.
- `Thread`, `ExecutorService`, lock, socket hoặc HTTP client đang hoạt động.
- Spring bean, proxy, repository hoặc service object.
- Đối tượng framework giữ nhiều tài nguyên runtime hoặc tham chiếu vòng phức tạp.
- Object tùy chỉnh có field không serialize được hoặc chứa dữ liệu quá lớn.

Không nên lưu nguyên entity graph lớn chỉ để ghi nhớ một vài thuộc tính. Ngoài nguy cơ serialization, dữ liệu có thể cũ, chứa quan hệ lazy chưa tải hoặc làm metadata phình to.

## 4. Chỉ lưu checkpoint có thể tái tạo

Thay vì lưu resource đang mở, hãy lưu thông tin đủ để mở lại resource sau restart. Ví dụ, với file reader, lưu đường dẫn, số dòng hoặc byte offset, cùng checksum/định danh file nếu cần bảo đảm đúng nguồn.

```java
ExecutionContext context = stepExecution.getExecutionContext();
context.putString("inputFile", inputPath.toString());
context.putLong("lastProcessedLine", lastProcessedLine);
```

Các giá trị như `String`, `long`, `int` và `boolean` phù hợp cho những checkpoint đơn giản. Nếu serializer hỗ trợ các kiểu dữ liệu khác, vẫn nên ưu tiên biểu diễn gọn và ổn định.

Khi mở lại reader, dùng đường dẫn và vị trí đã lưu để tạo stream mới:

```java
public class ResumableFileReader implements ItemStreamReader<OrderRow> {

    private static final String LINE_KEY = "orders.lastProcessedLine";

    private final Path inputPath;
    private BufferedReader reader;
    private long lineNumber;

    public ResumableFileReader(Path inputPath) {
        this.inputPath = inputPath;
    }

    @Override
    public void open(ExecutionContext context) throws ItemStreamException {
        try {
            lineNumber = context.getLong(LINE_KEY, 0L);
            reader = Files.newBufferedReader(inputPath, StandardCharsets.UTF_8);

            for (long i = 0; i < lineNumber; i++) {
                if (reader.readLine() == null) {
                    throw new ItemStreamException("Checkpoint exceeds file length");
                }
            }
        } catch (IOException ex) {
            throw new ItemStreamException("Cannot open input file", ex);
        }
    }

    @Override
    public OrderRow read() throws Exception {
        String line = reader.readLine();
        if (line == null) {
            return null;
        }
        lineNumber++;
        return parse(line);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(LINE_KEY, lineNumber);
    }

    @Override
    public void close() throws ItemStreamException {
        try {
            if (reader != null) {
                reader.close();
            }
        } catch (IOException ex) {
            throw new ItemStreamException("Cannot close input file", ex);
        }
    }
}
```

Ví dụ minh họa ý tưởng của `ItemStream`: `open` khôi phục vị trí và mở resource mới, `update` lưu checkpoint, còn `close` giải phóng resource. Hàm `parse` là logic chuyển dòng thành `OrderRow` của ứng dụng. Với file lớn, có thể dùng byte offset hoặc reader có sẵn hỗ trợ state thay vì đọc bỏ qua từng dòng khi restart.

## 5. Đối tượng Serializable có thể vẫn là lựa chọn không tốt

Một object triển khai `Serializable` không tự động trở thành checkpoint tốt. Ví dụ một DTO lớn có thể serialize thành payload rất lớn; một entity có thể mang theo quan hệ không cần thiết; một class có thể thay đổi cấu trúc giữa hai lần triển khai.

Checkpoint nên chứa trạng thái tối thiểu cần để tiếp tục:

| Không nên lưu | Nên lưu |
|---|---|
| `BufferedReader` đang mở | Đường dẫn file và vị trí đọc |
| JDBC `Connection` | Tên datasource/cấu hình và khóa bản ghi cuối đã commit |
| Một danh sách hàng trăm nghìn entity | ID hoặc khóa phân trang tiếp theo |
| Spring service hoặc repository bean | Dữ liệu đầu vào cần để gọi lại bean sau khi restart |
| HTTP response/client đang hoạt động | Request ID hoặc cursor do dịch vụ cấp |
| Một object chứa cả cache và tài nguyên runtime | DTO checkpoint nhỏ chỉ chứa các giá trị cần khôi phục |

Giá trị trong context nên có kích thước giới hạn. Context được lưu trong metadata; lưu dữ liệu lớn có thể làm tăng kích thước bảng, thời gian serialize/deserialize và chi phí backup.

## 6. Dùng DTO checkpoint nhỏ khi cần nhóm nhiều giá trị

Khi có nhiều thuộc tính liên quan, có thể tạo một DTO checkpoint nhỏ. Với Java serialization, class và toàn bộ field cần tương thích với serializer.

```java
public final class ImportCheckpoint implements Serializable {

    private static final long serialVersionUID = 1L;

    private final String sourceFile;
    private final long lastProcessedId;
    private final String sourceChecksum;

    public ImportCheckpoint(
            String sourceFile,
            long lastProcessedId,
            String sourceChecksum) {
        this.sourceFile = sourceFile;
        this.lastProcessedId = lastProcessedId;
        this.sourceChecksum = sourceChecksum;
    }

    public String sourceFile() { return sourceFile; }
    public long lastProcessedId() { return lastProcessedId; }
    public String sourceChecksum() { return sourceChecksum; }
}
```

Lưu DTO vào context:

```java
context.put("importCheckpoint", checkpoint);
```

DTO trên chỉ chứa chuỗi và số nguyên, nên object graph đơn giản. Nếu dùng Java serialization, `serialVersionUID` giúp kiểm soát tương thích định danh class giữa các phiên bản, nhưng không bảo đảm mọi thay đổi cấu trúc đều tương thích. Khi đổi class, hãy kiểm tra khả năng deserialize metadata được tạo bởi phiên bản trước.

Với checkpoint đơn giản, lưu từng giá trị bằng `putString`, `putLong` hoặc các phương thức kiểu tương ứng thường dễ quan sát và ít phụ thuộc class hơn việc lưu object tùy chỉnh.

## 7. Dùng transient không phải cách lưu checkpoint

Java cho phép đánh dấu field là `transient` để loại field đó khỏi quá trình serialization:

```java
public class ImportState implements Serializable {
    private static final long serialVersionUID = 1L;

    private String inputFile;
    private transient InputStream inputStream;
}
```

Cách này có thể tránh lỗi serialization của field `inputStream`, nhưng stream sẽ không được khôi phục khi deserialize. Sau restart, field đó sẽ là `null` và phải được mở lại từ `inputFile` hoặc cấu hình khác.

Vì vậy, `transient` chỉ phù hợp với tài nguyên có thể tái tạo và có logic khởi tạo lại rõ ràng. Nó không giúp lưu trạng thái nội bộ của stream, vị trí đọc hoặc buffer. Những trạng thái cần phục hồi phải được lưu riêng dưới dạng giá trị checkpoint.

## 8. Phân biệt Job ExecutionContext và Step ExecutionContext

Spring Batch có context ở hai phạm vi:

| Context | Phạm vi | Ví dụ dữ liệu phù hợp |
|---|---|---|
| Job `ExecutionContext` | Chia sẻ ở cấp JobExecution giữa các step trong cùng execution | Ngày xử lý, mã lô, kết quả tổng hợp cần cho step sau |
| Step `ExecutionContext` | Riêng cho một StepExecution | Vị trí reader, trang hiện tại, checkpoint của step |

Reader và `ItemStream` thường lưu trạng thái riêng trong step context. Một tasklet cũng có thể lấy step context từ `StepContribution` để lưu checkpoint:

```java
ExecutionContext context =
    contribution.getStepExecution().getExecutionContext();
context.putLong("lastProcessedId", lastProcessedId);
```

Không nên đưa state nội bộ của một reader vào job context chỉ vì muốn các step khác nhìn thấy nó. Hãy chọn phạm vi nhỏ nhất cần thiết. Dù là job context hay step context, các giá trị được lưu bền vững vẫn phải đáp ứng yêu cầu serialization.

## 9. Thời điểm cập nhật context và transaction

`ItemStream` cung cấp các callback `open`, `update` và `close`. Spring Batch gọi `update` để component ghi trạng thái hiện tại vào `ExecutionContext` trước khi metadata của step được lưu tại checkpoint.

```text
Đọc và xử lý chunk
       |
       v
ItemStream.update(context)
       |
       v
JobRepository lưu ExecutionContext
       |
       v
Transaction commit
```

Khi dữ liệu nghiệp vụ và repository dùng transaction resource phù hợp, checkpoint có thể được đồng bộ với commit chunk. Nếu chúng nằm ở các transaction manager hoặc database khác nhau, cần xem xét khả năng hai phía không commit cùng nhau.

Đừng cập nhật checkpoint lên vị trí mới trước khi phần dữ liệu tương ứng được ghi thành công. Nếu checkpoint đi trước dữ liệu nghiệp vụ, restart có thể bỏ qua item chưa thực sự được lưu. Nếu checkpoint đi sau nhưng dữ liệu đã commit, item có thể được xử lý lại; vì vậy writer nên idempotent hoặc có khóa nghiệp vụ duy nhất.

## 10. Khi dùng serializer tùy chỉnh

Spring Batch cho phép cấu hình `ExecutionContextSerializer` cho JobRepository. Có thể chọn serializer khác khi cần định dạng dễ quan sát, hỗ trợ DTO cụ thể hoặc tương thích với quy ước dữ liệu của hệ thống.

Khi dùng serializer tùy chỉnh, cần bảo đảm:

- Serialize và deserialize đối xứng cho mọi kiểu dữ liệu thực tế được lưu.
- Có chiến lược tương thích khi nâng cấp class hoặc đổi cấu trúc checkpoint.
- Chỉ cho phép các kiểu dữ liệu được ứng dụng kiểm soát; tránh deserialize dữ liệu không tin cậy.
- Payload nhỏ, có schema rõ ràng và không chứa credential hoặc dữ liệu nhạy cảm không cần thiết.
- Có kiểm thử đọc metadata cũ bằng phiên bản code mới trước khi triển khai.

Serializer JSON có thể phù hợp với DTO có schema ổn định, nhưng không phải object Java bất kỳ nào cũng tự động chuyển đổi được sang JSON và ngược lại. Cần cấu hình type mapping, định dạng ngày/số và chính sách tương thích rõ ràng.

Không nên đổi serializer giữa các phiên bản mà không có kế hoạch migration. Metadata cũ được ghi bằng serializer trước có thể không đọc được bằng serializer mới, khiến job cũ không thể restart.

## 11. Class evolution và triển khai phiên bản mới

Ngay cả khi một class implements `Serializable`, việc thay đổi class giữa các lần chạy có thể khiến deserialize thất bại hoặc tạo ra object có ý nghĩa khác với phiên bản cũ.

Các rủi ro thường gặp:

- Đổi tên package hoặc class được lưu trong context.
- Thay đổi `serialVersionUID` hoặc cấu trúc field không tương thích.
- Đổi kiểu dữ liệu của một field checkpoint.
- Xóa field mà logic restart cũ vẫn cần.
- Đổi ý nghĩa một key trong context nhưng vẫn giữ tên key.
- Triển khai class mới không còn chứa class cũ mà metadata đang tham chiếu.

Với job có thể chạy qua nhiều lần deploy, hãy giữ schema checkpoint ổn định hoặc có phiên bản rõ ràng. Có thể dùng key như `checkpoint.version` để chọn cách đọc/di chuyển trạng thái, đồng thời bảo đảm code mới hiểu được các execution cũ còn cần restart.

Ví dụ lưu phiên bản checkpoint:

```java
context.putInt("checkpoint.version", 2);
context.putLong("orders.lastProcessedId", lastProcessedId);
```

Khi đổi cấu trúc, code khôi phục có thể kiểm tra version và chuyển đổi từ định dạng cũ nếu có hỗ trợ. Với thay đổi không thể tương thích, cần để các JobInstance cũ hoàn tất bằng phiên bản cũ hoặc xây dựng quy trình migration được kiểm soát.

## 12. Cách tìm nguyên nhân serialization failure

Khi JobExecution hoặc StepExecution thất bại lúc lưu context, hãy xem exception gốc và xác định key/value nào vừa được thêm hoặc cập nhật.

Quy trình điều tra:

1. Xác định thời điểm lỗi: lúc `put`, lúc `ItemStream.update`, hay khi `JobRepository` cập nhật metadata.
2. Đọc exception gốc và stack trace để nhận diện class không serialize được.
3. Kiểm tra các giá trị mới được thêm vào cả job context và step context.
4. Với DTO tùy chỉnh, kiểm tra toàn bộ field và các object được tham chiếu lồng bên trong.
5. Xác nhận serializer thực tế được cấu hình cho JobRepository.
6. Thay resource runtime bằng checkpoint scalar hoặc DTO nhỏ có thể khôi phục.
7. Kiểm thử lưu và đọc context qua repository, rồi thử restart một execution đại diện.

Có thể ghi log tên key và loại class trước khi lưu context trong môi trường debug, nhưng không log toàn bộ payload nếu chứa dữ liệu cá nhân, bí mật hoặc thông tin nghiệp vụ nhạy cảm.

## 13. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Lưu `InputStream` hoặc `BufferedReader` | Serializer không thể lưu resource đang mở | Lưu đường dẫn và vị trí đọc; mở lại resource trong `open` |
| Lưu JDBC connection hoặc entity manager | Không thể serialize tài nguyên quản lý bởi container | Lưu ID/khóa truy vấn; lấy connection qua datasource khi thực thi |
| Chỉ đánh dấu class ngoài `Serializable` | Field lồng bên trong vẫn có thể gây lỗi | Kiểm tra toàn bộ object graph |
| Đánh dấu resource là `transient` nhưng không khởi tạo lại | Sau restart field bị null | Tái tạo resource từ checkpoint trong lifecycle callback |
| Lưu danh sách entity lớn | Metadata phình to, serialize chậm và dữ liệu dễ cũ | Chỉ lưu khóa hoặc cursor cần thiết |
| Đổi class checkpoint không tương thích | Không deserialize được metadata cũ | Giữ tương thích hoặc version hóa/migrate checkpoint |
| Đổi serializer mà không migrate metadata | Job cũ có thể không restart được | Có kế hoạch chuyển đổi và kiểm thử đọc metadata cũ |
| Đưa secret vào context | Secret có thể tồn tại trong metadata/backup/log | Lưu tham chiếu secret, lấy credential từ secret manager |

## 14. Checklist thiết kế state có thể khôi phục

Khi định nghĩa state cho reader, tasklet hoặc step, hãy xác định:

1. State nào thực sự cần tồn tại sau khi tiến trình kết thúc?
2. Có thể biểu diễn state bằng chuỗi, số, boolean, ID hoặc cursor ổn định không?
3. Nếu dùng DTO, mọi field và object lồng bên trong có tương thích serializer không?
4. Resource runtime có thể được mở lại từ thông tin checkpoint không?
5. Checkpoint được cập nhật tại ranh giới commit phù hợp chưa?
6. Code phiên bản mới có đọc được context của execution cũ không?
7. Context có đang chứa payload lớn, secret hoặc dữ liệu không cần thiết không?
8. Có integration test lưu, đọc và restart qua JobRepository thật không?

## Kết luận

State trong `ExecutionContext` phải tương thích với serializer mà `JobRepository` sử dụng. Một object ngoài cùng implements `Serializable` vẫn có thể thất bại nếu object graph chứa stream, connection, thread hoặc field không serialize được. Lỗi thường chỉ xuất hiện khi Spring Batch lưu context tại checkpoint, chứ không nhất thiết ngay lúc thêm giá trị vào map.

Hãy lưu dữ liệu checkpoint nhỏ và ổn định như ID, offset, tên file hoặc version; mở lại resource trong lifecycle của reader/tasklet thay vì lưu resource đang hoạt động. Nếu dùng DTO hoặc serializer tùy chỉnh, cần quản lý tương thích qua các lần triển khai và kiểm thử khả năng deserialize metadata cũ trước khi dựa vào restart trong production.
