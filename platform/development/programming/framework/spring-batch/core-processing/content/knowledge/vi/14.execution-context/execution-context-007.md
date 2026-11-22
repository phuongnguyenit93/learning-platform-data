# Context quá lớn và chi phí metadata

Trong Spring Batch, `ExecutionContext` lưu các giá trị trạng thái cần thiết để một job hoặc step có thể tiếp tục sau khi bị dừng hay thất bại. Ví dụ, reader có thể lưu vị trí dòng cuối đã đọc, page tiếp theo, khóa bản ghi cuối đã xử lý hoặc định danh của file đầu vào. Đây là dữ liệu phục vụ checkpoint và restart.

`ExecutionContext` được lưu cùng batch metadata thông qua `JobRepository`. Với JDBC repository, context được serialize và ghi vào các bảng metadata như `BATCH_STEP_EXECUTION_CONTEXT` và `BATCH_JOB_EXECUTION_CONTEXT`. Vì vậy, mỗi giá trị được thêm vào context đều có chi phí lưu trữ, serialize/deserialize và ghi database tại các thời điểm repository lưu context.

Nếu đưa danh sách lớn, toàn bộ payload, entity graph hoặc dữ liệu nghiệp vụ vào context, metadata có thể phình to. Hậu quả là tăng CPU và memory khi serialize, tăng dung lượng database, làm chậm thao tác repository, tăng thời gian backup/restore và khiến restart phụ thuộc vào những object khó tương thích giữa các phiên bản ứng dụng.

Nguyên tắc thiết kế quan trọng là: **chỉ lưu checkpoint nhỏ và những tham chiếu cần thiết để tiếp tục công việc; dữ liệu lớn nên nằm ở kho lưu trữ phù hợp với nghiệp vụ.**

## ExecutionContext được dùng để lưu gì?

`ExecutionContext` là một vùng key-value gắn với `JobExecution` hoặc `StepExecution`. Các thành phần như reader, writer và tasklet có thể lưu trạng thái cần khôi phục vào context.

Ví dụ các giá trị phù hợp:

- `currentLine`: số dòng hoặc vị trí đọc tiếp theo trong file.
- `lastProcessedId`: khóa cuối cùng đã xử lý trong một truy vấn có thứ tự ổn định.
- `nextPage`: số trang cần đọc ở lần gọi tiếp theo.
- `sourceFile`: đường dẫn hoặc tên resource đầu vào.
- `inputVersion`: phiên bản hoặc checksum của nguồn dữ liệu để nhận diện snapshot.
- `stagingBatchId`: định danh của tập dữ liệu staging đã được chuẩn bị ở hệ thống khác.

Các giá trị này nhỏ, có ý nghĩa rõ ràng và giúp thành phần xử lý xác định nơi cần tiếp tục. Context không được thiết kế để thay thế database nghiệp vụ, file storage, object storage hoặc cache ứng dụng.

### Job ExecutionContext và Step ExecutionContext

Spring Batch có hai phạm vi context:

| Phạm vi | Gắn với | Cách sử dụng thường gặp |
| --- | --- | --- |
| Job `ExecutionContext` | `JobExecution` | Lưu một số giá trị nhỏ cần truyền giữa các step trong cùng job execution |
| Step `ExecutionContext` | `StepExecution` | Lưu checkpoint riêng của step, ví dụ vị trí reader hoặc trạng thái xử lý page |

Step context thường được cập nhật tại các điểm commit của step, đặc biệt là mỗi chunk trong chunk-oriented processing. Job context thường được lưu ở các ranh giới cập nhật job/step, chẳng hạn khi step kết thúc. Tần suất lưu cụ thể phụ thuộc loại step và lifecycle của repository.

Do step context có thể được lưu nhiều lần trong một job dài, việc đặt dữ liệu lớn ở đó thường gây chi phí lặp lại. Job context cũng không phải nơi thích hợp để lưu payload lớn chỉ vì nó ít được cập nhật hơn.

## Metadata được lưu ở đâu?

Với JDBC `JobRepository`, Spring Batch lưu context trong các bảng metadata:

| Bảng | Nội dung |
| --- | --- |
| `BATCH_STEP_EXECUTION_CONTEXT` | Context của từng `StepExecution` |
| `BATCH_JOB_EXECUTION_CONTEXT` | Context của từng `JobExecution` |

Schema JDBC chuẩn thường có các cột như `SHORT_CONTEXT` và `SERIALIZED_CONTEXT`; kiểu cột và chi tiết schema phụ thuộc hệ quản trị cơ sở dữ liệu và phiên bản Spring Batch. Context được chuyển thành dạng lưu trữ bằng serializer được cấu hình, sau đó repository ghi vào database.

Khi context được cập nhật tại một checkpoint, repository cần chuẩn bị biểu diễn đã serialize và ghi metadata. Nếu context lớn, thao tác này có thể tốn CPU, tạo object trung gian trong memory, truyền nhiều dữ liệu qua JDBC và ghi lượng dữ liệu lớn hơn vào database.

`ExecutionContext.put...()` không đồng nghĩa lập tức thực hiện một câu SQL cho mỗi lần gọi. Giá trị được giữ trong context trong quá trình xử lý và được repository lưu tại các điểm cập nhật metadata theo lifecycle của step/job. Tuy nhiên, nếu context lớn ở mỗi điểm lưu, chi phí serialize và ghi vẫn tăng theo kích thước context.

## Vì sao context lớn làm tăng chi phí?

### Chi phí serialize và deserialize

Trước khi lưu context, Spring Batch dùng `ExecutionContextSerializer` được cấu hình để chuyển dữ liệu thành dạng có thể lưu trữ. Khi đọc metadata để restart, context được deserialize trở lại.

Context càng lớn thì thường càng cần:

- Nhiều CPU hơn để serialize và deserialize.
- Nhiều object trung gian và memory allocation hơn.
- Nhiều bộ nhớ hơn trong heap khi context được giữ trong execution.
- Nhiều dữ liệu hơn được truyền qua JDBC.
- Nhiều thời gian hơn để lưu hoặc khôi phục checkpoint.

Nếu một step có hàng nghìn chunk và context chứa một danh sách lớn, chi phí có thể lặp lại ở nhiều lần cập nhật. Ngay cả khi danh sách không thay đổi sau mỗi chunk, việc giữ nó trong context vẫn làm tăng kích thước metadata được lưu.

### Dung lượng database và tăng trưởng metadata

Context lớn làm các bảng metadata tăng nhanh. Điều này ảnh hưởng đến:

- Dung lượng database và tốc độ tăng trưởng theo số execution.
- Backup, replication, restore và đồng bộ dữ liệu giữa môi trường.
- Thời gian đọc/ghi các bản ghi context.
- Chính sách retention và cleanup metadata.
- Khả năng truy vết các job cũ khi bảng metadata chứa payload lớn.

Batch metadata thường được giữ lại để phục vụ kiểm toán và điều tra. Nếu mỗi execution lưu hàng megabyte context, dung lượng sẽ tăng đáng kể khi số lần chạy tăng lên, ngay cả khi dữ liệu nghiệp vụ thực tế đã được lưu ở nơi khác.

### Giới hạn schema và serializer

Một số database schema có cột lưu context ngắn và cột lưu bản serialize đầy đủ. Dù database hỗ trợ CLOB/TEXT hoặc kiểu lớn tương đương, kích thước lớn vẫn có chi phí và có thể gặp giới hạn từ driver, serializer, cấu hình hoặc schema tùy chỉnh.

Không nên dựa vào việc database có thể lưu một chuỗi rất lớn để biến `ExecutionContext` thành kho dữ liệu tổng quát. Khả năng lưu được về mặt kỹ thuật không có nghĩa đó là thiết kế phù hợp cho checkpoint.

### Tác động tới restart

Khi restart, Spring Batch phải đọc và khôi phục context. Context lớn khiến thời gian khôi phục tăng, đồng thời làm tăng rủi ro tương thích serializer và class giữa phiên bản ứng dụng cũ với mới.

Nếu context chứa nhiều object domain, thay đổi package, cấu trúc class hoặc serializer có thể khiến job cũ không deserialize được sau khi triển khai phiên bản mới. Những job chưa hoàn thành có thể bị mắc kẹt dù dữ liệu nghiệp vụ vẫn còn nguyên.

## Ví dụ thiết kế không phù hợp

Giả sử reader đọc một triệu đơn hàng và tasklet lưu toàn bộ danh sách vào context để step tiếp theo sử dụng:

```java
ExecutionContext context = stepExecution.getExecutionContext();
context.put("allOrders", orders); // Không nên lưu danh sách lớn
```

Nếu mỗi `Order` chứa nhiều trường, địa chỉ, chi tiết dòng hàng và object lồng nhau, context có thể trở thành một payload rất lớn. Spring Batch phải serialize nó khi lưu metadata và deserialize lại khi restart. Nếu step có nhiều checkpoint, cùng danh sách có thể được serialize lặp lại.

Các biến thể thường gặp của anti-pattern này:

- Lưu toàn bộ `List` hoặc `Map` chứa hàng nghìn/hàng triệu item.
- Lưu `byte[]` của file đầu vào hoặc file kết quả.
- Lưu nội dung response lớn từ API.
- Lưu toàn bộ entity JPA cùng quan hệ lazy/eager.
- Lưu cache, lookup table hoặc dữ liệu tham chiếu lớn.
- Lưu toàn bộ danh sách lỗi hoặc kết quả xử lý để cuối job mới ghi ra.

Các dữ liệu đó nên được lưu trong database nghiệp vụ, staging table, file hoặc object storage. Context chỉ cần giữ một định danh ổn định để tìm lại dữ liệu.

## Lưu tham chiếu thay vì payload

Thay vì lưu toàn bộ object, hãy lưu một khóa hoặc tham chiếu tới nơi chứa dữ liệu. Ví dụ, nạp dữ liệu vào staging table và lưu `stagingBatchId` trong context:

```java
ExecutionContext context = stepExecution.getExecutionContext();
context.putString("stagingBatchId", stagingBatchId);
context.putLong("lastProcessedId", lastProcessedId);
```

Step tiếp theo dùng `stagingBatchId` để truy vấn dữ liệu từ staging table. Context chỉ chứa vài scalar values, còn dữ liệu lớn nằm trong database được thiết kế để lưu và truy vấn dữ liệu nghiệp vụ.

Một ví dụ khác là lưu tham chiếu đến file trong object storage:

```java
context.putString("sourceObjectKey", "imports/2026/11/orders-15.csv");
context.putString("sourceVersion", sourceVersion);
context.putString("sourceChecksum", checksum);
```

Khi restart, reader lấy object theo key và kiểm tra version/checksum để bảo đảm đang đọc đúng nguồn đã dùng trong lần chạy ban đầu.

Một tham chiếu tốt cần:

- Ổn định trong suốt vòng đời job và các lần restart.
- Trỏ tới dữ liệu vẫn còn tồn tại khi job cần tiếp tục.
- Có version hoặc checksum nếu nội dung nguồn có thể thay đổi.
- Được bảo vệ bằng quyền truy cập phù hợp.
- Có chính sách retention phù hợp với thời gian lưu metadata và khả năng restart.

Không lưu URL tạm thời có thời hạn ngắn hoặc đường dẫn chỉ tồn tại trên filesystem của một node nếu job có thể restart ở node khác.

## Thiết kế checkpoint nhỏ và có ý nghĩa

Checkpoint tốt thường mô tả **vị trí hoặc tiến độ**, không chứa dữ liệu cần xử lý.

Ví dụ với reader đọc database theo khóa tăng dần:

```java
public class OrderReader implements ItemStreamReader<OrderInput> {

    private long lastProcessedId;

    @Override
    public void open(ExecutionContext context) {
        lastProcessedId = context.getLong("lastProcessedId", 0L);
    }

    @Override
    public OrderInput read() {
        // Đọc bản ghi tiếp theo có id > lastProcessedId.
        // Sau khi xác định item, cập nhật lastProcessedId trong state của reader.
        return readNextOrder();
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong("lastProcessedId", lastProcessedId);
    }

    @Override
    public void close() {
        // Giải phóng resource nếu có.
    }
}
```

`readNextOrder()` là phần truy vấn do ứng dụng triển khai. Ví dụ tập trung vào cách lưu checkpoint: chỉ lưu khóa cuối cùng, không lưu toàn bộ các `OrderInput` đã đọc.

Với reader tự triển khai, `ItemStream` cung cấp lifecycle `open`, `update` và `close`. Spring Batch gọi `update` tại các điểm lưu state của step. Các reader dựng sẵn như file reader hoặc paging reader thường đã có cơ chế state riêng; nên ưu tiên cấu hình state tích hợp thay vì tự lưu thêm cùng một danh sách dữ liệu.

Checkpoint phải phản ánh đúng dữ liệu đã commit. Nếu reader cập nhật khóa trong memory khi đọc nhưng chunk rollback, framework cần khôi phục state theo checkpoint đã lưu để đọc lại phần chưa commit. Đừng tự ghi checkpoint vào database độc lập trước khi business data hoàn tất.

## Chọn kiểu dữ liệu ổn định cho context

`ExecutionContext` có thể lưu các giá trị mà serializer được cấu hình có thể xử lý. Để giảm rủi ro, nên ưu tiên các kiểu đơn giản, nhỏ và ổn định như:

- `String` cho mã, đường dẫn, tên resource, version hoặc trạng thái.
- `Long` hoặc `Integer` cho ID, offset, số dòng và page number.
- `Boolean` cho cờ tiến trình.
- `Double` hoặc kiểu số phù hợp khi thật sự cần giá trị số.
- Ngày/giờ hoặc kiểu khác nếu serializer của ứng dụng hỗ trợ ổn định và định dạng được thống nhất.

Không nên lưu trực tiếp:

- JPA entity hoặc Hibernate proxy.
- `InputStream`, `Reader`, `Connection`, `EntityManager` hoặc resource đang mở.
- Object có graph quan hệ lớn hoặc vòng tham chiếu phức tạp.
- Cache, collection lớn hoặc object phụ thuộc vào trạng thái của một thread.
- Class tạm thời, anonymous class hoặc object có cấu trúc dễ thay đổi theo lần build.

Giá trị cần được serializer hỗ trợ và có thể khôi phục sau khi ứng dụng restart. Với kiểu dữ liệu tùy chỉnh, phải kiểm soát serialization contract và khả năng tương thích giữa các phiên bản.

## Tương thích serializer và phiên bản ứng dụng

Context được lưu để dùng lại sau khi tiến trình kết thúc, vì vậy dữ liệu serialize có thể tồn tại lâu hơn phiên bản code đã tạo ra nó.

Một số rủi ro khi lưu custom object:

- Class bị đổi package hoặc tên.
- Field bị đổi kiểu hoặc đổi ý nghĩa.
- Class không còn tồn tại trong phiên bản mới.
- `serialVersionUID` hoặc cấu trúc serialize thay đổi.
- Serializer được thay thế hoặc cấu hình khác giữa các node.
- Một node cũ ghi context mà node mới không đọc được, hoặc ngược lại.

Để giảm rủi ro:

1. Ưu tiên scalar values và format ổn định thay vì object domain.
2. Dùng key có tên và ý nghĩa rõ ràng, giữ tương thích khi restart.
3. Nếu cần object tùy chỉnh, thiết kế schema/version rõ ràng và kiểm thử đọc dữ liệu context cũ.
4. Đảm bảo mọi node trong cùng hệ thống dùng serializer tương thích.
5. Khi thay serializer hoặc cấu trúc context, có kế hoạch cho các job đang chạy hoặc đang chờ restart.

Không thay serializer một cách đột ngột khi còn execution cũ cần restart. Nếu không thể đọc context cũ, có thể phải hoàn tất các execution trước khi nâng cấp, cung cấp cơ chế chuyển đổi hoặc xử lý theo quy trình phục hồi được kiểm soát.

## Không dùng ExecutionContext làm cache

`ExecutionContext` là metadata bền vững phục vụ restart, không phải cache cho dữ liệu được dùng lặp lại trong từng item.

Ví dụ không phù hợp:

```java
context.put("customerLookupCache", allCustomers);
context.put("processedOrders", processedOrderObjects);
```

Nếu mục tiêu là giảm truy vấn lặp, hãy cân nhắc cache trong memory có giới hạn, bảng tham chiếu, batch lookup hoặc dịch vụ cache chuyên dụng. Cache trong memory có thể được tạo lại sau restart; nếu tính đúng đắn của job phụ thuộc vào dữ liệu đó, cần có nguồn dữ liệu bền vững và version rõ ràng.

Một số lựa chọn thay thế:

| Nhu cầu | Cách lưu phù hợp |
| --- | --- |
| Tra cứu hàng nghìn mã tham chiếu | Batch query hoặc cache có giới hạn trong memory |
| Giữ dữ liệu trung gian qua nhiều step | Staging table hoặc file trung gian, context lưu ID/URI |
| Lưu payload file lớn | File system hoặc object storage, context lưu key/version |
| Lưu kết quả từng item | Bảng nghiệp vụ hoặc bảng kết quả riêng |
| Theo dõi vị trí xử lý | ID, offset, page hoặc cursor nhỏ trong context |

## Job context và chia sẻ dữ liệu giữa các step

Job `ExecutionContext` thường được dùng để chia sẻ một số giá trị nhỏ giữa các step. Ví dụ step đầu tạo file báo cáo và lưu đường dẫn, step sau gửi file tới hệ thống khác.

```java
ExecutionContext jobContext =
        stepExecution.getJobExecution().getExecutionContext();

jobContext.putString("reportObjectKey", reportObjectKey);
jobContext.putString("reportVersion", reportVersion);
```

Nếu cần đưa một số key từ step context lên job context, có thể dùng `ExecutionContextPromotionListener` với danh sách key cần promote. Chỉ promote giá trị nhỏ và thực sự cần thiết cho step tiếp theo.

Không nên sao chép cả một collection lớn từ step context sang job context. Việc nhân đôi payload làm tăng metadata và khiến nhiều step phụ thuộc vào cùng một cấu trúc object. Hãy lưu dữ liệu ở staging store và chỉ truyền ID hoặc URI.

## Chi phí tăng theo số chunk và số execution

Giả sử một step có 100.000 chunk và context chứa 200 KB dữ liệu. Nếu context được cập nhật tại mỗi chunk, repository có thể phải serialize và ghi một lượng dữ liệu lớn lặp đi lặp lại. Chi phí không chỉ là 200 KB lưu một lần; nó còn bao gồm CPU, memory allocation, JDBC transfer và database write ở các điểm checkpoint.

Tác động tăng theo nhiều chiều:

- **Kích thước context:** mỗi lần lưu cần xử lý nhiều dữ liệu hơn.
- **Số checkpoint:** step càng nhiều chunk thì context có thể được lưu càng thường xuyên.
- **Số execution:** mỗi lần chạy tạo thêm metadata và context tương ứng.
- **Thời gian retention:** metadata tồn tại càng lâu thì tổng dung lượng tích lũy càng lớn.
- **Số node:** nhiều execution đồng thời làm tăng tải ghi metadata lên repository.

Một context nhỏ vài key có thể không đáng kể. Nhưng context lớn được lưu hàng nghìn lần có thể trở thành nút thắt của repository và database, đặc biệt khi nhiều job chạy đồng thời.

## Đo lường chi phí context

Khi nghi ngờ metadata là nút thắt, hãy đo thay vì chỉ dựa vào kích thước file hoặc số item.

Các chỉ số nên theo dõi:

- Kích thước serialized context trung bình và lớn nhất.
- Thời gian repository cập nhật execution context.
- Thời gian commit chunk và tổng chunk duration.
- CPU và allocation trong serialize/deserialize.
- Dung lượng và tốc độ tăng trưởng của hai bảng context.
- Thời gian restart và khôi phục context.
- Số lượng execution đang chạy, thất bại và còn cần restart.

Có thể quan sát dung lượng bảng bằng công cụ quản trị database hoặc thống kê hệ quản trị. Không nên truy vấn và hiển thị toàn bộ payload context trong log vì có thể tạo thêm tải và làm lộ dữ liệu nhạy cảm.

Nếu cần điều tra một execution, dùng `JobExplorer` hoặc API metadata phù hợp để xác định execution và step liên quan. Tránh sửa trực tiếp serialized context trong database bằng SQL thủ công.

## Quản lý retention và cleanup metadata

Context được lưu cùng lịch sử execution. Nếu ứng dụng giữ metadata vô thời hạn, các bảng `BATCH_*` sẽ tiếp tục tăng theo số lần chạy. Một chính sách retention nên phân biệt:

- Job đã `COMPLETED` và không còn cần restart.
- Job `FAILED` hoặc `STOPPED` còn trong thời gian cho phép restart.
- Job đang chạy hoặc đang được điều tra.
- Metadata cần giữ theo yêu cầu kiểm toán hoặc nghiệp vụ.

Chỉ dọn metadata khi đã xác định execution không còn cần restart, không còn phụ thuộc để điều tra và phù hợp chính sách lưu trữ. Việc xóa metadata có thể làm mất checkpoint và lịch sử batch; không nên xóa riêng các dòng context trong khi giữ lại execution liên quan.

Sử dụng cơ chế quản trị/cleanup được thiết kế cho phiên bản Spring Batch và schema của ứng dụng, hoặc quy trình cleanup có kiểm soát tôn trọng quan hệ khóa ngoại. Backup trước khi dọn và kiểm tra retention cùng business data nếu context chứa tham chiếu tới file hoặc staging records.

Nếu context chỉ lưu `stagingBatchId`, thời gian giữ staging data phải dài ít nhất bằng thời gian job còn có thể restart. Nếu xóa staging data trước khi execution được restart, tham chiếu trong context sẽ không còn hữu ích.

## Bảo mật và dữ liệu nhạy cảm

Execution context được lưu trong batch metadata database và có thể xuất hiện trong backup, replication hoặc công cụ quản trị. Vì vậy, không nên lưu:

- Mật khẩu, access token, refresh token hoặc private key.
- Thông tin xác thực database hoặc broker.
- Payload cá nhân/nhạy cảm không cần thiết cho restart.
- Dữ liệu nghiệp vụ đầy đủ chỉ để tránh truy vấn lại.

Nếu job cần truy cập một resource được bảo vệ, lưu một định danh hoặc secret reference rồi lấy secret từ secret manager khi chạy. Phân quyền database metadata theo nguyên tắc tối thiểu và áp dụng encryption at rest nếu chính sách hệ thống yêu cầu.

## Ví dụ chuyển từ context lớn sang context nhỏ

### Cách lưu không nên dùng

```java
ExecutionContext context = stepExecution.getExecutionContext();
context.put("orders", allOrders);
context.put("customerMap", allCustomers);
context.put("rawFileBytes", fileBytes);
```

Các giá trị trên có thể chứa hàng nghìn object hoặc payload lớn. Chúng làm context khó serialize, tăng dung lượng metadata và buộc restart khôi phục dữ liệu mà lẽ ra có thể đọc từ nguồn chính.

### Cách thiết kế phù hợp hơn

```java
ExecutionContext context = stepExecution.getExecutionContext();
context.putString("stagingBatchId", stagingBatchId);
context.putString("sourceObjectKey", sourceObjectKey);
context.putString("sourceVersion", sourceVersion);
context.putLong("lastProcessedId", lastProcessedId);
```

Step sử dụng `stagingBatchId` để truy vấn dữ liệu staging, `sourceObjectKey` và `sourceVersion` để truy cập đúng file nguồn, còn `lastProcessedId` để tiếp tục từ checkpoint. Context nhỏ, dễ lưu và dễ khôi phục.

Nếu cần truyền danh sách ID lớn giữa step, hãy ghi danh sách đó vào staging table với một batch key. Job context chỉ cần giữ batch key để step sau truy vấn lại. Có thể cleanup staging data sau khi job hoàn thành và hết thời hạn phục hồi.

## Các lỗi thường gặp

### Lưu toàn bộ dữ liệu vào context

Điều này biến metadata thành data store, làm tăng serialization, database IO và thời gian restart. Chỉ lưu checkpoint hoặc reference nhỏ.

### Lưu entity JPA hoặc object graph

Entity có thể chứa proxy, lazy relation, vòng tham chiếu và phụ thuộc vào class version. Lưu ID hoặc business key rồi truy vấn lại khi cần.

### Lưu byte array hoặc nội dung file

File lớn nên nằm trong filesystem hoặc object storage. Context lưu đường dẫn/key, version và checksum.

### Dùng context làm cache lookup

Cache lớn làm context phình to và bị serialize lặp lại. Dùng batch query, cache có giới hạn hoặc kho dữ liệu tham chiếu.

### Đổi serializer khi job cũ còn chờ restart

Context đã lưu có thể không đọc được bằng serializer mới. Duy trì tương thích, kiểm thử dữ liệu cũ hoặc có kế hoạch chuyển đổi trước khi triển khai.

### Xóa metadata quá sớm

Xóa context hoặc execution còn cần restart có thể khiến job không thể tiếp tục. Áp dụng retention có kiểm soát và tôn trọng quan hệ metadata.

### Lưu secret trong context

Metadata có thể được backup và đọc bởi công cụ vận hành. Lưu secret reference thay vì credential hoặc token.

## Nguyên tắc thiết kế ExecutionContext

Khi quyết định có nên lưu một giá trị vào context, hãy tự hỏi:

1. Giá trị này có thật sự cần để tiếp tục sau restart không?
2. Có thể lưu một ID, offset, version hoặc URI thay cho toàn bộ object không?
3. Giá trị có nhỏ và có kiểu dữ liệu serializer hỗ trợ không?
4. Nó có được lưu lặp lại tại nhiều checkpoint không?
5. Cấu trúc và kiểu dữ liệu có tương thích qua các lần triển khai không?
6. Giá trị có chứa secret hoặc dữ liệu nhạy cảm không?
7. Resource được tham chiếu có tồn tại đủ lâu cho mọi lần restart được phép không?
8. Có chính sách retention để dọn metadata và dữ liệu staging đúng thời điểm không?

Trong đa số job production, context nên gồm một số key nhỏ mô tả vị trí xử lý, phạm vi dữ liệu, version nguồn và định danh resource trung gian. Dữ liệu nghiệp vụ lớn nên nằm trong database, staging table hoặc object storage được quản lý riêng.

## Ghi nhớ

`ExecutionContext` là nơi lưu checkpoint nhỏ để Spring Batch khôi phục job và step. Context được serialize và lưu vào các bảng metadata ở những điểm repository cập nhật state; với chunk step, step context thường được lưu tại các commit point. Context lớn làm tăng CPU, memory allocation, JDBC traffic, dung lượng database và thời gian restart; object tùy chỉnh còn tạo rủi ro tương thích serializer/class khi triển khai phiên bản mới. Hãy lưu offset, ID, page, version hoặc URI ổn định thay cho danh sách item, entity graph, byte array hay payload lớn. Đặt dữ liệu lớn ở business database, staging table hoặc object storage; quản lý retention của cả metadata lẫn resource được tham chiếu và không lưu secret trong context.
