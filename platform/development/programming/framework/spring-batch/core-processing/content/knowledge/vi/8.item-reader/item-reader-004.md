# Reader restartable và save state

Trong Spring Batch, một `ItemReader` có thể cần ghi nhớ vị trí đã đọc để tiếp tục đúng chỗ khi Job bị gián đoạn. Cơ chế này được gọi là *restartability* của reader. Spring Batch cung cấp contract `ItemStream` và `ExecutionContext` để reader lưu trạng thái, khôi phục trạng thái và tiếp tục xử lý trong lần restart.

Một reader restartable cần đáp ứng hai việc: lưu checkpoint tại thời điểm phù hợp trong quá trình xử lý và khôi phục checkpoint đó khi Step chạy lại. Nếu reader chỉ giữ vị trí đọc trong field của object Java, trạng thái sẽ mất khi process bị dừng. `saveState` là tùy chọn quan trọng ở nhiều reader tích hợp sẵn, cho phép bật hoặc tắt việc lưu trạng thái vào `ExecutionContext`.

## 1. Restartable reader giải quyết vấn đề gì?

Giả sử một Step đọc file có 10.000 dòng và ghi dữ liệu vào database theo chunk 100 item. Sau khi xử lý và commit 4.000 dòng, ứng dụng bị dừng đột ngột.

Nếu reader không lưu vị trí đã đọc, khi Job được restart, reader có thể bắt đầu lại từ đầu. Khi đó 4.000 dòng đã commit có nguy cơ được đọc và ghi lại. Nếu reader lưu checkpoint, lần restart có thể tiếp tục từ vị trí tương ứng với chunk cuối cùng đã commit.

```text
Lần chạy đầu
  Đọc dòng 1..100   -> commit
  Đọc dòng 101..200 -> commit
  ...
  Đọc dòng 3901..4000 -> commit
  Ứng dụng dừng trước khi chunk tiếp theo hoàn tất

Restart
  Khôi phục checkpoint đã lưu
  Tiếp tục từ phần dữ liệu chưa được commit
```

Restartability giúp giảm việc xử lý lại dữ liệu và giữ tiến độ nhất quán. Nó đặc biệt quan trọng với Job dài, nguồn dữ liệu lớn hoặc quy trình cần tiếp tục sau lỗi hệ thống.

Tuy nhiên, khả năng restart không chỉ phụ thuộc reader. JobRepository phải lưu được metadata, Step phải có thể restart, reader phải khôi phục đúng trạng thái, và nguồn dữ liệu phải đủ ổn định để vị trí đã lưu vẫn có ý nghĩa.

## 2. ItemStream: contract lưu và khôi phục trạng thái

`ItemReader` định nghĩa thao tác đọc item thông qua `read()`. Để tham gia vòng đời lưu trạng thái, reader thường triển khai thêm `ItemStream`, hoặc dùng interface kết hợp `ItemStreamReader`.

`ItemStream` có ba callback chính:

| Phương thức | Vai trò |
|---|---|
| `open(ExecutionContext)` | Mở reader và khôi phục trạng thái đã lưu trước đó |
| `update(ExecutionContext)` | Ghi trạng thái hiện tại của reader vào context để checkpoint |
| `close()` | Đóng reader và giải phóng tài nguyên |

Luồng gọi khái quát trong một Step:

```text
Step bắt đầu
    |
    +--> open(context đã lưu)
    |
    +--> read item -> process -> write
    |          |
    |          +--> update(context) tại các điểm checkpoint
    |          +--> commit transaction của chunk
    |
    +--> ... lặp lại các chunk ...
    |
    +--> close()
```

Khi Step được restart, `open()` nhận `ExecutionContext` đã được lưu từ lần thực thi trước. Reader dùng dữ liệu trong context để khôi phục vị trí, bộ đếm hoặc trạng thái cần thiết. `update()` được framework gọi trong quá trình lưu trạng thái Step, thường gắn với ranh giới commit của chunk. `close()` được gọi khi Step kết thúc để giải phóng tài nguyên.

`ItemStreamReader<T>` kết hợp `ItemReader<T>` và `ItemStream`, vì vậy một reader triển khai interface này có cả `read()` và các callback quản lý trạng thái.

## 3. ExecutionContext lưu checkpoint ở đâu?

Reader chạy trong một `StepExecution`, vì vậy checkpoint của reader thường được lưu trong Step `ExecutionContext`. Đây là metadata gắn với lần thực thi Step, được `JobRepository` lưu để có thể khôi phục khi restart.

Ví dụ, reader lưu số thứ tự item tiếp theo cần đọc:

```java
executionContext.putInt("ordersReader.currentIndex", currentIndex);
```

Khi Step được restart, reader đọc lại key đó:

```java
currentIndex = executionContext.getInt("ordersReader.currentIndex", 0);
```

Giá trị mặc định `0` được dùng khi key chưa tồn tại, tức đây là lần chạy đầu tiên hoặc chưa có checkpoint tương ứng. Khi key đã tồn tại, reader tiếp tục từ vị trí đã lưu.

Không nên nhầm checkpoint của reader với `JobParameters`. JobParameters là dữ liệu đầu vào dùng để xác định JobInstance; ExecutionContext lưu tiến độ phát sinh trong quá trình thực thi. Ví dụ, ngày nghiệp vụ là JobParameter, còn vị trí dòng đã đọc là checkpoint của reader.

## 4. Tự triển khai một reader có thể restart

Ví dụ sau minh họa reader đọc một danh sách có thứ tự ổn định. Reader lưu chỉ số phần tử kế tiếp cần đọc vào Step ExecutionContext:

```java
public class RestartableOrderReader implements ItemStreamReader<Order> {

    private static final String CURRENT_INDEX_KEY =
            "restartableOrderReader.currentIndex";

    private final OrderSource orderSource;
    private int currentIndex;
    private List<Order> orders;

    public RestartableOrderReader(OrderSource orderSource) {
        this.orderSource = orderSource;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        currentIndex = executionContext.getInt(CURRENT_INDEX_KEY, 0);
        orders = orderSource.loadOrdersInStableOrder();

        if (currentIndex > orders.size()) {
            throw new IllegalStateException(
                    "Saved reader position is beyond the available input"
            );
        }
    }

    @Override
    public Order read() {
        if (currentIndex >= orders.size()) {
            return null;
        }

        return orders.get(currentIndex++);
    }

    @Override
    public void update(ExecutionContext executionContext) {
        executionContext.putInt(CURRENT_INDEX_KEY, currentIndex);
    }

    @Override
    public void close() {
        orders = null;
    }
}
```

Các phần quan trọng:

- `open()` đọc checkpoint cũ. Nếu chưa có key, reader bắt đầu từ index `0`.
- `read()` trả item kế tiếp và tăng `currentIndex`. Khi hết dữ liệu, nó trả `null` theo contract của `ItemReader`.
- `update()` ghi vị trí hiện tại vào ExecutionContext để Spring Batch lưu checkpoint.
- `close()` giải phóng tham chiếu đến danh sách trong ví dụ. Reader thực tế cần đóng stream, cursor hoặc tài nguyên mà nó đã mở.

Ví dụ này giả định `loadOrdersInStableOrder()` trả về cùng tập dữ liệu theo cùng thứ tự khi restart. Trong ứng dụng thực tế, không nên tải một danh sách rất lớn vào bộ nhớ chỉ để minh họa checkpoint; hãy dùng reader phù hợp với nguồn dữ liệu như file reader hoặc database paging reader.

### Key trong ExecutionContext phải ổn định và duy nhất

Tên key là một phần của định dạng checkpoint. Khi đổi tên key giữa hai phiên bản ứng dụng, reader mới có thể không tìm thấy trạng thái cũ và bắt đầu lại từ đầu. Hãy giữ key ổn định qua các lần triển khai hoặc có logic chuyển đổi tương thích khi cần.

Nếu một Step có nhiều stream component cùng lưu trạng thái, mỗi component phải có key riêng để tránh ghi đè dữ liệu của nhau. Với reader tích hợp sẵn dựa trên `ItemStreamSupport`, đặt tên reader duy nhất thường giúp framework tạo execution-context key có namespace riêng. Khi tự viết reader, hãy dùng prefix rõ ràng như `ordersReader.` hoặc tên component ổn định.

## 5. Bật saveState trên reader tích hợp sẵn

Nhiều reader của Spring Batch đã triển khai `ItemStream` và tự lưu checkpoint. Với các reader này, cấu hình `saveState` quyết định có ghi trạng thái vào ExecutionContext hay không. Nên đặt tên reader ổn định và bật `saveState(true)` khi cần restart.

Ví dụ với `FlatFileItemReader`:

```java
@Bean
public FlatFileItemReader<Order> ordersFileReader(
        @Value("${batch.orders-file}") Resource resource) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("ordersFileReader")
            .resource(resource)
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

Reader lưu tiến độ đọc vào ExecutionContext và dùng lại tiến độ đó khi mở lại trong lần restart. Để checkpoint có ý nghĩa, file cần giữ nguyên nội dung và thứ tự trong suốt khoảng thời gian từ lần chạy đầu đến lần restart. Nếu file bị thay thế hoặc chèn/xóa dòng, vị trí dòng đã lưu có thể trỏ đến dữ liệu khác.

Với database reader theo kiểu paging, cần cấu hình thứ tự sắp xếp ổn định. Ví dụ, sort key nên xác định duy nhất từng dòng, thường là khóa chính:

```java
@Bean
public JdbcPagingItemReader<Order> ordersPagingReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider,
        RowMapper<Order> orderRowMapper) {

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("ordersPagingReader")
            .dataSource(dataSource)
            .queryProvider(queryProvider)
            .rowMapper(orderRowMapper)
            .pageSize(100)
            .saveState(true)
            .build();
}
```

`queryProvider` cần có sort key ổn định và xác định thứ tự nhất quán giữa các trang. Nếu sắp xếp chỉ theo một cột có giá trị trùng nhau, thứ tự bản ghi giữa các lần truy vấn có thể thay đổi, làm reader bỏ sót hoặc đọc lặp khi restart.

Các builder và API cụ thể có thể khác theo phiên bản Spring Batch. Hãy dùng reader và builder có trong dependency của dự án, đồng thời kiểm tra API `saveState` của implementation đang sử dụng.

## 6. Ý nghĩa của saveState(true) và saveState(false)

| Cấu hình | Hành vi | Hệ quả khi restart |
|---|---|---|
| `saveState(true)` | Reader lưu trạng thái cần thiết vào ExecutionContext | Reader có thể khôi phục checkpoint nếu nguồn dữ liệu và cấu hình vẫn phù hợp |
| `saveState(false)` | Reader không lưu trạng thái riêng vào ExecutionContext | Reader không thể dựa vào checkpoint của chính nó để tiếp tục từ vị trí trước |

`saveState(true)` không tự bảo đảm mọi nguồn dữ liệu đều restart chính xác. Reader cần triển khai đúng contract, checkpoint cần được lưu tại ranh giới phù hợp và dữ liệu đầu vào phải cho phép khôi phục vị trí.

`saveState(false)` có thể phù hợp khi reader không cần checkpoint, hoặc khi ứng dụng chủ động chấp nhận bắt đầu lại từ đầu và writer có cơ chế idempotent để tránh tạo dữ liệu trùng. Nó cũng có thể cần thiết trong một số cấu hình chạy song song mà việc dùng chung state của reader không phù hợp. Tuy nhiên, tắt lưu state đồng nghĩa ứng dụng phải tự xử lý hệ quả khi Step bị restart.

Không nên tắt `saveState` chỉ để tránh lỗi metadata. Nếu cần restart đúng vị trí, hãy tìm nguyên nhân của vấn đề như tên reader không ổn định, key trùng, nguồn dữ liệu thay đổi hoặc component không được đăng ký như một ItemStream.

## 7. Khi nào Spring Batch gọi open, update và close?

Trong một Step, các `ItemStream` được đăng ký sẽ tham gia vòng đời xử lý:

1. Trước khi đọc item, framework gọi `open()` với ExecutionContext của Step. Reader có thể mở file/cursor và khôi phục checkpoint.
2. Trong quá trình chunk processing, reader cung cấp item qua `read()`.
3. Khi đến thời điểm lưu trạng thái, framework gọi `update()` để các stream ghi trạng thái hiện tại vào ExecutionContext.
4. Metadata Step và ExecutionContext được lưu cùng quá trình commit theo cấu hình repository/transaction.
5. Khi Step kết thúc, framework gọi `close()` để đóng tài nguyên.

`update()` là callback lưu trạng thái, không phải nơi thực hiện công việc nghiệp vụ chính. Không nên đặt thao tác ghi dữ liệu đầu ra hoặc gọi API bên ngoài vào callback này. Nó nên cập nhật những giá trị nhỏ cần thiết để khôi phục reader hoặc writer.

Nếu một chunk rollback, checkpoint của chunk đó không được coi là tiến độ đã commit. Khi restart, reader cần tiếp tục từ checkpoint đã lưu ở ranh giới commit trước đó. Điều này giúp dữ liệu đã commit và vị trí reader được khôi phục nhất quán.

## 8. Đảm bảo reader được đăng ký như ItemStream

Khi reader được truyền trực tiếp vào cấu hình Step và chính reader đó triển khai `ItemStream`, Spring Batch có thể quản lý các callback vòng đời của nó. Tuy nhiên, nếu reader bị bọc bên trong một delegate hoặc wrapper, framework có thể chỉ nhìn thấy object ngoài cùng.

Ví dụ, một reader tổng hợp có delegate bên trong. Nếu delegate tự triển khai `ItemStream`, cần bảo đảm delegate cũng được đăng ký với Step để `open`, `update` và `close` được gọi. Trong cấu hình Java có thể dùng `.stream(delegate)` khi phù hợp:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(compositeReader)
        .writer(orderWriter)
        .stream(fileDelegateReader)
        .build();
```

Nếu delegate không nhận được callback `update()`, trạng thái của nó sẽ không được lưu dù bản thân class đã triển khai `ItemStream`. Khi restart, reader có thể bắt đầu sai vị trí hoặc không thể khôi phục đúng trạng thái.

Các reader đa nguồn như `MultiResourceItemReader` còn phải lưu cả resource hiện tại và trạng thái của delegate. Hãy dùng builder hoặc cấu hình chuẩn của framework và đặt tên delegate riêng để tránh xung đột key.

## 9. Điều kiện để restart chính xác

Một reader chỉ restart chính xác khi checkpoint và nguồn dữ liệu vẫn tương thích. Các điều kiện quan trọng gồm:

- Job được khởi chạy lại với cùng Job name và identifying JobParameters để tiếp tục cùng JobInstance.
- JobInstance trước đó ở trạng thái có thể restart và không còn execution đang chạy.
- Step có thể restart theo cấu hình của Job.
- JobRepository còn metadata của JobExecution/StepExecution trước đó.
- Reader hỗ trợ `ItemStream` và lưu state nếu cần tiếp tục từ checkpoint.
- Tên reader và key trong ExecutionContext ổn định giữa các lần chạy.
- File, query hoặc nguồn dữ liệu giữ thứ tự và định danh đủ ổn định để vị trí checkpoint vẫn chỉ đúng dữ liệu mong muốn.
- Writer và các thao tác nghiệp vụ xử lý an toàn trường hợp item được đọc lại do rollback hoặc lỗi ngoài transaction.

Ví dụ, một reader file có thể lưu số dòng đã đọc. Nếu file bị thay thế bằng nội dung mới nhưng vẫn có cùng đường dẫn, số dòng checkpoint không còn chỉ đến cùng bản ghi. Tương tự, database paging reader cần thứ tự sắp xếp ổn định; dữ liệu bị chèn/xóa trong lúc restart có thể làm thay đổi vị trí trang.

Với dữ liệu thay đổi liên tục, cân nhắc snapshot theo thời điểm, khóa nghiệp vụ, watermark hoặc điều kiện truy vấn cố định để bảo đảm lần restart nhìn thấy cùng một tập dữ liệu logic.

## 10. Phân biệt restart, retry và skip

Các cơ chế này có liên quan nhưng giải quyết những vấn đề khác nhau:

| Cơ chế | Phạm vi | Mục đích |
|---|---|---|
| Restart | Một JobInstance sau khi JobExecution thất bại hoặc dừng | Tiếp tục Job/Step ở lần thực thi mới dựa trên metadata đã lưu |
| Retry | Một thao tác item/chunk gặp lỗi có thể thử lại trong cùng quá trình chạy | Xử lý lỗi tạm thời như lỗi kết nối hoặc lock contention |
| Skip | Một item gặp lỗi thuộc loại được phép bỏ qua | Tiếp tục xử lý các item còn lại theo skip policy |

Reader restartable không có nghĩa mọi lỗi đọc đều tự được retry. Cấu hình retry/skip thuộc fault-tolerant Step; `ItemStream` và ExecutionContext phục vụ việc lưu/khôi phục trạng thái khi Step hoặc Job được restart.

## 11. Những nhầm lẫn thường gặp

**Chỉ lưu vị trí đọc trong field của reader.** Field chỉ tồn tại trong bộ nhớ của object. Khi ứng dụng khởi động lại, field không tự khôi phục. Hãy lưu checkpoint trong ExecutionContext qua `ItemStream.update()`.

**Cho rằng mọi ItemReader đều tự động restart được.** `ItemReader` chỉ định nghĩa thao tác đọc. Reader cần hỗ trợ `ItemStream` và lưu trạng thái, hoặc có một cơ chế khôi phục riêng phù hợp.

**Bật saveState nhưng không đặt tên reader ổn định.** Một số reader dùng tên để tạo key trong ExecutionContext. Tên thay đổi có thể khiến reader không tìm thấy checkpoint cũ.

**Đổi tên key hoặc cấu trúc checkpoint mà không hỗ trợ dữ liệu cũ.** ExecutionContext được lưu qua nhiều lần triển khai. Code mới cần có khả năng đọc metadata cũ hoặc có kế hoạch xử lý các execution đang dở.

**Tắt saveState và vẫn kỳ vọng tiếp tục từ vị trí cũ.** Khi không lưu state, reader không có checkpoint riêng để khôi phục. Cần chấp nhận chạy lại từ đầu hoặc tự xây dựng cơ chế an toàn khác.

**Nguồn dữ liệu thay đổi giữa hai lần chạy.** Vị trí dòng hoặc offset cũ có thể trỏ đến bản ghi khác. Cần bảo đảm snapshot, thứ tự và định danh dữ liệu ổn định.

**Reader delegate không được đăng ký stream.** Nếu framework không gọi `open`, `update`, `close` cho delegate, trạng thái của delegate sẽ không được lưu hoặc khôi phục.

## 12. Thiết kế reader restartable trong ứng dụng thực tế

Khi dùng reader tích hợp sẵn, ưu tiên cấu hình tên ổn định và bật `saveState(true)` nếu Job cần restart. Với reader tự viết, triển khai `ItemStreamReader`, đọc checkpoint trong `open()`, cập nhật checkpoint trong `update()` và giải phóng tài nguyên trong `close()`. Chọn key duy nhất, giữ định dạng checkpoint tương thích và bảo đảm nguồn dữ liệu có thứ tự ổn định.

Hãy kiểm tra hành vi khi lỗi xảy ra ở giữa một chunk: transaction của chunk chưa commit phải rollback, reader phải khôi phục từ checkpoint đã lưu gần nhất, và writer phải xử lý an toàn dữ liệu có thể được đọc lại. Kết hợp đúng `ItemStream`, `ExecutionContext`, JobRepository và nguồn dữ liệu ổn định sẽ giúp reader tiếp tục chính xác sau restart thay vì phụ thuộc vào trạng thái tạm thời trong bộ nhớ.
