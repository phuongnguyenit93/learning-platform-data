# Cập nhật context trước commit

Trong Spring Batch, `ExecutionContext` lưu trạng thái cần thiết để theo dõi hoặc khôi phục một lần thực thi Job/Step. Với chunk-oriented processing, một ví dụ quan trọng là vị trí hiện tại của reader: sau khi một chunk được ghi thành công, lần restart tiếp theo cần biết nên đọc tiếp từ đâu.

Spring Batch phối hợp việc cập nhật `ExecutionContext` với transaction của chunk. Các thành phần triển khai `ItemStream` được gọi qua callback `update(ExecutionContext)` để ghi trạng thái nội bộ vào context. Framework lưu context và metadata của Step trước khi transaction chunk commit. Khi metadata và dữ liệu nghiệp vụ tham gia cùng transaction phù hợp, checkpoint và thay đổi dữ liệu của chunk được commit như một đơn vị nhất quán.

Thứ tự này giúp tránh hai tình huống nguy hiểm: dữ liệu đã commit nhưng checkpoint chưa được lưu, khiến restart đọc và ghi trùng; hoặc checkpoint đã được lưu nhưng dữ liệu nghiệp vụ chưa commit, khiến restart bỏ qua dữ liệu chưa được ghi. Vì vậy, cập nhật context trước commit là một phần quan trọng của khả năng restart và tính nhất quán của Spring Batch.

## 1. ExecutionContext dùng để lưu trạng thái nào?

`ExecutionContext` là một vùng lưu trữ dạng key/value gắn với execution. Nó phù hợp với thông tin nhỏ cần tồn tại qua các lần cập nhật metadata, đặc biệt là checkpoint để tiếp tục công việc sau khi Step bị gián đoạn.

Ví dụ trạng thái có thể lưu:

- Dòng hoặc vị trí cuối cùng đã đọc từ một tệp.
- ID cuối cùng đã xử lý khi đọc dữ liệu theo thứ tự.
- Trang tiếp theo cần đọc từ một API phân trang.
- Một khóa hoặc mã batch mà Step sau cần sử dụng.
- Trạng thái nội bộ tối thiểu cần khôi phục khi restart.

Không nên dùng ExecutionContext làm nơi lưu toàn bộ dữ liệu nghiệp vụ hoặc danh sách item của một Job. Hãy lưu khóa, vị trí, offset hay thông tin gọn nhẹ; dữ liệu chính vẫn nằm trong database, file hoặc hệ thống nguồn/đích phù hợp.

### Step ExecutionContext và Job ExecutionContext

Spring Batch có hai phạm vi context thường dùng:

| Context | Phạm vi | Trường hợp sử dụng |
|---|---|---|
| `StepExecution.getExecutionContext()` | Một lần thực thi Step | Checkpoint riêng của reader/writer hoặc Tasklet trong Step đó. |
| `JobExecution.getExecutionContext()` | Một lần thực thi Job | Dữ liệu nhỏ cần chia sẻ giữa các Step trong cùng JobExecution. |

Checkpoint của một reader thường nên nằm trong Step ExecutionContext vì nó gắn với vị trí đọc của Step đó. Nếu một Step chuẩn bị mã batch để Step tiếp theo sử dụng, có thể lưu mã này trong Job ExecutionContext.

Hai context có vòng đời và mục đích khác nhau. Không nên đặt checkpoint reader vào Job context chỉ vì muốn đọc nó ở nhiều nơi; điều đó có thể khiến các lần thực thi Step hoặc các Step khác chia sẻ trạng thái không phù hợp.

## 2. Vì sao phải cập nhật context trước commit?

Giả sử một chunk xử lý 100 đơn hàng. Reader đã đọc các item từ 1 đến 100, writer ghi các đơn hàng đó vào database. Cùng lúc, reader cần lưu checkpoint cho biết phần dữ liệu này đã được xử lý để lần restart tiếp tục từ item 101.

Nếu dữ liệu nghiệp vụ được commit trước nhưng checkpoint được lưu sau bằng một transaction riêng, tiến trình có thể dừng giữa hai thao tác:

```text
Ghi 100 đơn hàng
       |
       v
COMMIT dữ liệu nghiệp vụ
       |
       X  Tiến trình bị dừng
       |
       v
Lưu checkpoint = 100 (chưa xảy ra)
```

Khi restart, metadata vẫn cho biết vị trí cũ. Reader có thể đọc lại các item 1–100 và writer có thể ghi trùng.

Tình huống ngược lại cũng nguy hiểm. Nếu checkpoint được commit trước dữ liệu nghiệp vụ trong một transaction độc lập, tiến trình có thể dừng sau khi checkpoint đã chuyển đến 100 nhưng trước khi các đơn hàng được commit. Lần restart sẽ bắt đầu từ item 101, khiến các item 1–100 bị bỏ qua dù dữ liệu đích chưa được lưu.

Mục tiêu là cập nhật checkpoint và ghi dữ liệu nghiệp vụ trong cùng ranh giới transaction khi có thể:

```text
Bắt đầu transaction của chunk
       |
       v
Reader đọc item 1–100
       |
       v
Processor xử lý item
       |
       v
Writer ghi dữ liệu nghiệp vụ
       |
       v
ItemStream.update(context)
       |
       v
JobRepository lưu Step ExecutionContext
       |
       v
COMMIT transaction
       |
       +--> Dữ liệu và checkpoint cùng được xác nhận
```

Khi dữ liệu nghiệp vụ và metadata repository cùng tham gia một transaction được quản lý phù hợp, commit xác nhận cả hai. Nếu transaction rollback, cả thay đổi nghiệp vụ và cập nhật checkpoint trong transaction đó được hoàn tác. Khi restart, framework dùng checkpoint cuối cùng đã commit.

Đây là lý do callback cập nhật stream được gọi trước khi transaction chunk commit. Nó tạo cơ hội để trạng thái reader được lưu cùng với kết quả ghi của chunk.

## 3. Vòng đời ItemStream và callback update

Các reader/writer cần lưu và khôi phục trạng thái có thể triển khai `ItemStream` hoặc interface mở rộng như `ItemStreamReader` và `ItemStreamWriter`.

Ba callback chính:

| Callback | Khi nào được gọi | Trách nhiệm |
|---|---|---|
| `open(ExecutionContext)` | Khi stream được mở trong vòng đời Step | Khôi phục trạng thái đã lưu hoặc khởi tạo trạng thái mới. |
| `update(ExecutionContext)` | Tại điểm cập nhật trạng thái trước commit | Ghi trạng thái hiện tại của stream vào ExecutionContext. |
| `close()` | Khi stream kết thúc vòng đời | Đóng file, cursor hoặc tài nguyên đang sử dụng. |

Hợp đồng rút gọn:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext)
            throws ItemStreamException;

    void update(ExecutionContext executionContext)
            throws ItemStreamException;

    void close() throws ItemStreamException;
}
```

Trong chunk Step, Spring Batch quản lý vòng đời stream đã được đăng ký. Sau khi chunk xử lý xong và trước khi transaction commit, framework gọi `update` để stream đưa trạng thái cần lưu vào context. Repository sau đó lưu context theo cơ chế của JobRepository.

`update` không có nghĩa là mỗi item đều tạo một lần commit. Callback được gọi tại điểm cập nhật stream của chunk/transaction, không phải để commit riêng từng item. Commit interval và CompletionPolicy vẫn xác định ranh giới chunk.

## 4. Ví dụ reader lưu checkpoint

Giả sử một reader tùy chỉnh đọc danh sách đơn hàng theo vị trí. Reader cần lưu chỉ số item tiếp theo để khi restart có thể tiếp tục từ vị trí đã commit.

```java
public class CheckpointingOrderReader
        implements ItemStreamReader<OrderInput> {

    private static final String INDEX_KEY = "orders.reader.current.index";

    private int currentIndex;

    @Override
    public void open(ExecutionContext context) {
        currentIndex = context.getInt(INDEX_KEY, 0);
        openSourceAt(currentIndex);
    }

    @Override
    public OrderInput read() {
        OrderInput item = readNext();
        if (item != null) {
            currentIndex++;
        }
        return item;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(INDEX_KEY, currentIndex);
    }

    @Override
    public void close() {
        closeSource();
    }

    private void openSourceAt(int index) {
        // Mở nguồn dữ liệu tại vị trí cần khôi phục.
    }

    private OrderInput readNext() {
        // Đọc item tiếp theo từ nguồn dữ liệu.
        return null;
    }

    private void closeSource() {
        // Đóng file, cursor hoặc resource tương ứng.
    }
}
```

Đây là khung minh họa; `readNext()` và các phương thức quản lý nguồn phải được triển khai theo loại dữ liệu thực tế. Điểm quan trọng là:

1. `open` lấy checkpoint đã commit từ ExecutionContext.
2. `read` cập nhật trạng thái trong bộ nhớ khi item được đọc.
3. `update` chép trạng thái hiện tại vào ExecutionContext trước commit.
4. Nếu chunk commit thành công, checkpoint mới được lưu.
5. Nếu chunk rollback, checkpoint của chunk đó không được xem là checkpoint đã commit khi repository và dữ liệu cùng tham gia transaction.

Với reader tùy chỉnh, cần bảo đảm vị trí được lưu có thể khôi phục chính xác. Nếu nguồn dữ liệu thay đổi thứ tự giữa hai lần chạy, một chỉ số dòng đơn thuần có thể không đủ; nên dùng thứ tự ổn định hoặc khóa nghiệp vụ phù hợp.

## 5. Cấu hình reader có trạng thái trong Step

Khi reader triển khai `ItemStream`, Step cần quản lý vòng đời của nó để gọi `open`, `update` và `close`. Các reader chuẩn của Spring Batch thường được đăng ký tự động khi được cấu hình trực tiếp trong Step.

Ví dụ với reader chuẩn đọc tệp:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(inputFile)
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
```

Các reader chuẩn hỗ trợ state thường có tùy chọn `saveState`; cần bật và đặt tên reader ổn định để metadata được lưu đúng. `@StepScope` cho phép reader nhận JobParameters của execution đang chạy và tạo instance trong phạm vi Step.

Khi bọc reader có trạng thái bên trong một delegate hoặc decorator, cần bảo đảm stream bên trong cũng được đăng ký với Step. Nếu framework không tự nhận diện delegate, có thể đăng ký stream tường minh bằng `.stream(...)` trên Step builder phù hợp.

Không nên tự tạo reader mới mỗi lần gọi `read` hoặc giữ trạng thái checkpoint trong field của một singleton dùng chung cho nhiều execution. Trạng thái của một lần chạy cần gắn với đúng StepExecution.

## 6. Cập nhật Step ExecutionContext trong Tasklet

Tasklet cũng có thể ghi trạng thái vào Step ExecutionContext. Ví dụ, một Tasklet thực hiện một lần chuẩn bị có thể lưu mã staging để Step tiếp theo đọc:

```java
.tasklet((contribution, chunkContext) -> {
    StepExecution stepExecution = contribution.getStepExecution();
    ExecutionContext context = stepExecution.getExecutionContext();

    String stagingBatchId = stagingService.prepareBatch();
    context.putString("staging.batch.id", stagingBatchId);

    return RepeatStatus.FINISHED;
}, transactionManager)
```

Với TaskletStep, framework cũng quản lý transaction của lần gọi Tasklet và cập nhật metadata theo vòng đời Step. Nếu Tasklet trả `CONTINUABLE`, các lần gọi tiếp theo có thể cập nhật context nhiều lần. Cần cập nhật checkpoint nhất quán với phần công việc đã hoàn tất.

Nếu Step tiếp theo cần đọc giá trị này, có thể lấy từ Job ExecutionContext hoặc dùng cơ chế promotion từ Step ExecutionContext lên Job ExecutionContext, tùy cách tổ chức Job. Không nên giả định mọi Step đều tự động nhìn thấy Step context của Step trước.

## 7. Step ExecutionContext và Job ExecutionContext được lưu thế nào?

Với JDBC JobRepository, Spring Batch lưu hai context ở các bảng metadata riêng:

| Bảng | Nội dung |
|---|---|
| `BATCH_STEP_EXECUTION_CONTEXT` | ExecutionContext thuộc một StepExecution, thường chứa checkpoint của reader/writer. |
| `BATCH_JOB_EXECUTION_CONTEXT` | ExecutionContext thuộc một JobExecution, dùng cho dữ liệu chia sẻ giữa các Step. |

Khi chunk hoàn tất, JobRepository lưu context của StepExecution cùng metadata liên quan. Với context cấp Job, framework lưu theo các điểm cập nhật tương ứng của JobExecution. Cách serialize phụ thuộc cấu hình serializer và phiên bản Spring Batch.

Các giá trị đưa vào ExecutionContext cần có thể serialize bằng cơ chế đang cấu hình. Nên ưu tiên kiểu dữ liệu đơn giản như `String`, số, ngày được biểu diễn phù hợp hoặc object serializable có cấu trúc ổn định. Tránh lưu đối tượng chứa connection, stream, entity graph lớn hoặc resource không thể serialize.

Tên key nên ổn định và có namespace, ví dụ `orders.reader.current.index`, để tránh va chạm với key của reader khác hoặc thành phần khác. Khi thay đổi cấu trúc checkpoint giữa các phiên bản ứng dụng, cần cân nhắc tương thích với JobExecution cũ còn có thể restart.

## 8. Điều gì xảy ra khi chunk rollback?

Giả sử chunk size là 100. Reader đọc item 1–100, processor xử lý và writer ghi database. Trước commit, stream cập nhật checkpoint thành 100. Nếu transaction commit thành công, dữ liệu và checkpoint mới được xác nhận.

Nếu writer ném exception trước commit:

```text
Chunk bắt đầu
  |
  +--> Reader đọc item 1–100
  +--> Processor xử lý
  +--> Writer ghi dữ liệu
  +--> ItemStream.update: checkpoint = 100
  +--> JobRepository cập nhật context
  +--> Writer/transaction phát sinh lỗi
  +--> ROLLBACK

Checkpoint cuối cùng đã commit vẫn là checkpoint trước chunk này.
```

Khi Job restart, reader khôi phục checkpoint đã commit gần nhất và xử lý lại phần chưa hoàn tất. Đây là hành vi mong muốn: framework không coi chunk rollback là đã hoàn tất chỉ vì reader đã đọc các item đó trong bộ nhớ.

Tuy nhiên, hành vi này chỉ bảo đảm nhất quán khi cập nhật metadata và dữ liệu nghiệp vụ thực sự tham gia cùng transaction phù hợp. Nếu JobRepository và writer dùng hai datasource hoặc hai transaction manager độc lập, một transaction JDBC thông thường không thể tự bảo đảm commit/rollback nguyên tử cho cả hai. Khi đó cần XA/JTA nếu hệ thống yêu cầu transaction phân tán, hoặc thiết kế checkpoint/idempotency và đối soát để xử lý khoảng trống giữa hai tài nguyên.

## 9. Vì sao không cập nhật checkpoint sau commit?

Nếu ứng dụng tự lưu checkpoint sau khi chunk đã commit, có một khoảng thời gian giữa hai thao tác:

```text
Writer ghi dữ liệu
       |
       v
COMMIT dữ liệu
       |
       X  Process crash
       |
       v
Lưu checkpoint
```

Khi process crash tại điểm `X`, dữ liệu đã được ghi nhưng checkpoint chưa thay đổi. Restart có thể đọc lại cùng item. Nếu writer không idempotent, hệ thống có thể tạo bản ghi trùng hoặc lặp tác dụng phụ.

Spring Batch gọi `ItemStream.update` trước commit để checkpoint có thể tham gia cùng transaction với dữ liệu chunk. Không nên tự xây dựng cơ chế “commit dữ liệu trước, cập nhật checkpoint sau” bằng hai thao tác độc lập.

Ngược lại, nếu lưu checkpoint trong transaction riêng trước khi dữ liệu được commit, có thể tạo tình huống checkpoint tiến lên nhưng dữ liệu chưa được ghi. Mục tiêu không phải chỉ là “ghi context sớm hơn”, mà là **ghi context trước commit trong cùng ranh giới transaction phù hợp**.

## 10. Khi metadata và dữ liệu nghiệp vụ dùng transaction manager khác nhau

Trong ứng dụng đơn giản, metadata repository và dữ liệu nghiệp vụ có thể cùng dùng một database và transaction manager. Khi đó, cập nhật context, cập nhật StepExecution và ghi dữ liệu chunk có thể cùng tham gia transaction.

Trong hệ thống lớn, metadata và business data có thể nằm ở hai database khác nhau. Nếu dùng hai transaction manager độc lập, commit của database nghiệp vụ không tự động nguyên tử với commit metadata. Có thể xảy ra:

- Business data commit thành công nhưng metadata rollback hoặc không được cập nhật.
- Metadata checkpoint được lưu nhưng business data rollback.
- Một resource mất kết nối trong lúc resource kia commit.

Các lựa chọn thiết kế:

- Dùng transaction phân tán/XA khi yêu cầu và hạ tầng cho phép.
- Thiết kế writer idempotent để ghi lại cùng business key không tạo dữ liệu sai.
- Dùng trạng thái xử lý và đối soát để phát hiện khoảng trống giữa metadata và business data.
- Lưu checkpoint nghiệp vụ ở cùng database với dữ liệu đích nếu cần một ranh giới commit cục bộ rõ ràng.
- Dùng outbox/inbox cho tác dụng phụ liên hệ thống.

Không nên mặc định một `PlatformTransactionManager` quản lý được nhiều database chỉ vì chúng được gọi trong cùng một Step. Hãy xác định rõ tài nguyên nào thực sự tham gia transaction.

## 11. Checkpoint phải phản ánh phần công việc đã commit

Checkpoint là tuyên bố về tiến độ: “mọi dữ liệu trước vị trí này đã được xử lý theo mức bảo đảm của ứng dụng”. Vì vậy, giá trị checkpoint phải được cập nhật đúng thời điểm.

Ví dụ với reader phân trang:

```java
int pageToRead = context.getInt("next.page", 0);
Page<OrderInput> page = service.fetchPage(pageToRead);

// Đọc và xử lý các item của trang hiện tại.
// Chỉ đặt next.page sau khi phần công việc tương ứng
// được đưa vào transaction commit theo thiết kế.
context.putInt("next.page", pageToRead + 1);
```

Đoạn code minh họa nguyên tắc; trong thực tế, logic cập nhật context nên nằm trong `ItemStream.update` hoặc cơ chế checkpoint phù hợp để framework lưu trước commit. Không nên cập nhật `next.page` ngay khi gửi request nếu trang đó chưa được ghi thành công.

Với dữ liệu database, dùng khóa tăng dần hoặc cursor ổn định thường an toàn hơn offset nếu dữ liệu nguồn có thể thay đổi trong lúc Job chạy. Nếu dùng offset paging và có bản ghi được thêm/xóa giữa hai lần đọc, một số item có thể bị lặp hoặc bỏ sót.

## 12. Trạng thái trong bộ nhớ và checkpoint đã lưu

Trong lúc Step chạy, reader có thể đã tăng chỉ số trong field nội bộ. `update` chép giá trị đó vào ExecutionContext ở điểm cập nhật. Nhưng trạng thái trong bộ nhớ không đồng nghĩa checkpoint đã được commit bền vững.

Phân biệt:

- **State trong reader:** trạng thái hiện tại của object reader trong process đang chạy.
- **ExecutionContext trong bộ nhớ:** các key/value đã được cập nhật trong execution hiện tại.
- **Checkpoint đã commit:** context đã được lưu bền vững cùng transaction thành công và có thể khôi phục khi restart.

Nếu transaction rollback, không nên xem giá trị context đang có trong object là checkpoint cuối cùng. Khi restart, Spring Batch khôi phục context đã lưu trong JobRepository. Reader tùy chỉnh cần có cách phục hồi state trong bộ nhớ phù hợp với rollback/retry trong cùng execution, hoặc dựa vào buffering và cơ chế retry của framework.

## 13. saveState và các reader/writer chuẩn

Nhiều reader/writer chuẩn của Spring Batch có hỗ trợ lưu trạng thái. Ví dụ, `FlatFileItemReader` có thể lưu vị trí đọc để restart. Tùy reader, có thể cấu hình `saveState(true)` hoặc mặc định đã bật.

Khi tắt `saveState`, reader sẽ không lưu checkpoint nội bộ của nó. Điều này có thể phù hợp nếu nguồn dữ liệu không cần restart hoặc reader được thiết kế stateless, nhưng có thể khiến Step phải đọc lại từ đầu sau restart.

Một số lưu ý:

- Đặt tên stream/reader ổn định để key trong ExecutionContext ổn định.
- Đảm bảo reader có thể mở lại nguồn tại vị trí đã lưu.
- Không thay đổi thứ tự dữ liệu nguồn giữa lần chạy và lần restart nếu checkpoint phụ thuộc vị trí.
- Với delegate stream, đăng ký đúng vòng đời để `update` được gọi.
- Nếu reader được dùng trong multi-threaded Step, kiểm tra thread safety và cơ chế checkpoint của nó.

## 14. Lưu nhiều giá trị context và quản lý key

Một Step có thể có nhiều stream hoặc thành phần cùng ghi vào ExecutionContext. Hãy đặt key rõ ràng và tránh trùng:

```java
ExecutionContext context = stepExecution.getExecutionContext();

context.putLong("orders.reader.last.id", lastOrderId);
context.putInt("orders.reader.page", currentPage);
context.putString("orders.batch.status", "PREPARED");
```

Nên dùng namespace theo component hoặc nghiệp vụ. Không ghi đè key do reader khác quản lý. Không lưu thông tin bí mật như password, token hoặc private key trong context vì metadata có thể được truy vấn bởi người có quyền đọc JobRepository.

Khi thay đổi key hoặc kiểu dữ liệu giữa các phiên bản ứng dụng, cần cân nhắc các JobExecution cũ có thể restart. Có thể cần hỗ trợ đọc cả key cũ và mới trong giai đoạn chuyển đổi hoặc đánh dấu những execution cũ không còn restart được theo quy trình vận hành.

## 15. Theo dõi và chẩn đoán checkpoint

Khi Job restart sai vị trí hoặc xử lý trùng dữ liệu, cần kiểm tra:

1. `JobInstance` và `JobExecution` nào đang được restart.
2. `StepExecution` trước đó có trạng thái gì.
3. Step ExecutionContext đã lưu những key checkpoint nào.
4. Reader có thực sự triển khai `ItemStream` và `saveState` được bật không.
5. Callback `update` có được gọi trong vòng đời Step không.
6. Metadata repository và business writer có cùng transaction boundary không.
7. Nguồn dữ liệu có thứ tự ổn định giữa hai lần chạy không.
8. Writer có thể ghi trùng nếu item được đọc lại không.

Có thể đọc context thông qua `JobExplorer` để điều tra metadata đã lưu. Không nên chỉnh sửa trực tiếp chuỗi serialized trong bảng `BATCH_STEP_EXECUTION_CONTEXT` để ép reader đến vị trí khác. Thay đổi checkpoint cần thực hiện qua API hoặc quy trình phục hồi đã thiết kế và phải đối chiếu dữ liệu nghiệp vụ trước.

## 16. Những lỗi thường gặp

### Cập nhật checkpoint sau khi writer commit

Nếu process dừng giữa commit dữ liệu và lưu context, restart có thể đọc lại item đã ghi. Hãy để Spring Batch cập nhật stream trước commit và giữ metadata trong transaction phù hợp.

### Cập nhật checkpoint trước khi dữ liệu được ghi

Nếu checkpoint được lưu độc lập trước business data, crash có thể khiến restart bỏ qua item chưa commit. Checkpoint phải đồng bộ với phần công việc đã commit.

### Reader không triển khai ItemStream

Reader tùy chỉnh không lưu trạng thái sẽ không tự có checkpoint. Hãy triển khai `ItemStreamReader` hoặc đăng ký stream phù hợp và cài đặt `open`, `update`, `close`.

### Không đăng ký delegate stream

Reader bọc bên ngoài có thể che khuất delegate triển khai `ItemStream`. Nếu delegate không được framework quản lý vòng đời, `update` sẽ không được gọi. Đăng ký stream tường minh khi cần.

### Dùng key checkpoint không ổn định

Đổi tên reader hoặc key có thể làm context cũ không còn được đọc. Giữ tên ổn định hoặc có chiến lược tương thích khi nâng cấp.

### Dùng offset trên nguồn dữ liệu thay đổi

Nếu dữ liệu nguồn bị thêm/xóa giữa lần chạy và restart, offset có thể trỏ đến vị trí khác. Dùng thứ tự ổn định, khóa nghiệp vụ hoặc snapshot phù hợp.

### Giả định hai transaction manager commit nguyên tử

Metadata và business data ở hai database độc lập không tự được commit/rollback như một transaction duy nhất. Cần XA hoặc thiết kế idempotency và đối soát.

### Lưu quá nhiều dữ liệu trong context

Context được serialize và lưu metadata. Lưu danh sách lớn hoặc object phức tạp làm metadata phình to, tăng chi phí ghi/đọc và gây khó khăn khi nâng cấp serializer. Chỉ lưu checkpoint và thông tin cần thiết.

## 17. Quy trình triển khai cập nhật context trước commit

Khi xây dựng reader hoặc writer có trạng thái, có thể thực hiện theo trình tự:

1. Xác định state tối thiểu cần khôi phục, ví dụ current index, last processed ID hoặc next page.
2. Chọn Step ExecutionContext cho checkpoint riêng của Step.
3. Triển khai `ItemStream` hoặc dùng reader/writer chuẩn có hỗ trợ state.
4. Trong `open`, khôi phục state từ ExecutionContext đã lưu.
5. Trong `read`/`write`, cập nhật state nội bộ theo tiến độ thực tế.
6. Trong `update`, chép state vào ExecutionContext để Spring Batch lưu trước commit.
7. Bảo đảm metadata repository và dữ liệu nghiệp vụ dùng transaction boundary phù hợp nếu cần commit nguyên tử.
8. Kiểm thử trường hợp commit thành công, rollback, process crash và restart.
9. Kiểm tra writer idempotent hoặc có khóa nghiệp vụ để bảo vệ khi nguồn phải đọc lại.
10. Theo dõi context size và duy trì tính tương thích của key/kiểu dữ liệu qua các lần nâng cấp.

| Tình huống | Kết quả mong muốn |
|---|---|
| Chunk commit thành công | Dữ liệu nghiệp vụ và checkpoint mới được xác nhận. |
| Chunk rollback trước commit | Checkpoint đã commit trước đó vẫn là mốc restart. |
| Process dừng sau commit | Restart dùng checkpoint mới đã lưu cùng chunk. |
| Process dừng trước commit | Restart không xem chunk chưa commit là hoàn tất. |
| Reader không hỗ trợ state | Cần thiết kế lại reader hoặc chấp nhận đọc lại theo chính sách. |
| Metadata và business data khác transaction | Cần XA hoặc cơ chế idempotency/đối soát. |

## Kết luận

Spring Batch gọi `ItemStream.update(ExecutionContext)` trước khi transaction của chunk commit để trạng thái reader/writer có thể được lưu cùng kết quả xử lý của chunk. Khi dữ liệu nghiệp vụ và metadata tham gia cùng transaction phù hợp, checkpoint chỉ được xác nhận khi chunk commit; nếu rollback, checkpoint của chunk đó không trở thành mốc restart đã commit. Hãy lưu checkpoint trong Step ExecutionContext, khôi phục qua `open`, cập nhật qua `update`, giữ key ổn định và bảo đảm writer an toàn khi chạy lại. Nếu metadata và business data nằm ở các transaction manager độc lập, cần thiết kế thêm XA, idempotency hoặc đối soát vì một transaction thông thường không thể bảo đảm tính nguyên tử xuyên nhiều tài nguyên.
