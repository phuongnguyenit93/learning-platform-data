# Commit theo kích thước dữ liệu

Trong Spring Batch, chunk thường được cấu hình bằng số lượng item, ví dụ 100 item mỗi chunk. Cách này dễ hiểu và phù hợp khi kích thước từng item tương đối đồng đều. Nhưng nếu item có độ lớn rất khác nhau, cùng một commit interval có thể tạo ra chunk nhỏ hoặc rất lớn về dung lượng thực tế.

Ví dụ, 100 dòng CSV ngắn có thể chỉ chiếm vài kilobyte, trong khi 100 object chứa nội dung JSON lớn hoặc dữ liệu nhị phân có thể chiếm hàng chục megabyte. Khi kích thước item không đồng đều, có thể cần kết thúc chunk theo tổng dung lượng ước tính, đồng thời vẫn giới hạn số item tối đa.

Spring Batch hỗ trợ thay đổi điều kiện kết thúc chunk bằng CompletionPolicy. Có thể dùng policy dựng sẵn cho số item hoặc thời gian, hoặc viết policy riêng để theo dõi trọng lượng dữ liệu của từng item. Dù chọn tiêu chí nào, một chunk hoàn tất vẫn là ranh giới transaction mà framework dùng để ghi và commit dữ liệu.

## 1. Commit interval mặc định đếm item

Cấu hình quen thuộc:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
~~~

Giá trị 100 là số item tối đa mà framework gom vào một chunk theo completion policy mặc định. Nó không có nghĩa chunk luôn có đúng 100 item: chunk cuối có thể nhỏ hơn khi reader hết dữ liệu, và filter/skip cũng ảnh hưởng số item cuối cùng writer nhận được.

Với item có kích thước tương tự nhau, đếm số item thường đủ tốt. Nhưng nếu độ lớn item thay đổi mạnh, số item không phản ánh chính xác bộ nhớ hoặc payload mà chunk tạo ra.

Ví dụ:

| Chunk | Số item | Kích thước trung bình mỗi item | Dung lượng ước tính |
|---|---:|---:|---:|
| A | 100 | 1 KB | 100 KB |
| B | 100 | 200 KB | 20 MB |
| C | 100 | 2 MB | 200 MB |

Cả ba chunk đều có 100 item, nhưng chi phí bộ nhớ và ghi dữ liệu rất khác nhau.

## 2. Khi nào cần commit theo kích thước dữ liệu?

Commit theo kích thước hữu ích khi kích thước item biến động đáng kể hoặc đích ghi có giới hạn payload.

Một số tình huống thường gặp:

- Đọc file có các dòng với độ dài rất khác nhau.
- Xử lý JSON/XML mà mỗi document có kích thước khác nhau.
- Ghi các object chứa nội dung văn bản hoặc dữ liệu nhị phân lớn.
- Gửi batch payload đến API có giới hạn dung lượng request.
- Ghi vào database với dữ liệu BLOB/CLOB hoặc nhiều cột văn bản lớn.
- Muốn giới hạn lượng dữ liệu tạm giữ trong bộ nhớ giữa các lần ghi.

Trước khi chọn policy, cần xác định rõ “kích thước dữ liệu” đang nói đến đại lượng nào:

| Đại lượng | Ý nghĩa | Cách ước lượng |
|---|---|---|
| Byte nguồn | Số byte đã đọc từ file hoặc message | Độ dài byte thực tế |
| Kích thước object | Bộ nhớ mà object chiếm trong JVM | Ước lượng theo trường và cấu trúc object |
| Payload đầu ra | Dung lượng sau khi serialize để ghi/gửi | Đo byte sau serialization hoặc dùng estimator |
| Chi phí ghi database | Dữ liệu và overhead mà database xử lý | Ước lượng theo schema, index và driver |

Các đại lượng này không giống nhau. Một JSON 10 KB có thể trở thành object Java lớn hơn nhiều do object header, String, collection và tham chiếu. Ngược lại, một object lớn trong JVM có thể được serialize thành payload nhỏ hơn.

Nếu mục tiêu là tránh vượt giới hạn request của API, nên đo payload sau serialization. Nếu mục tiêu là hạn chế bộ nhớ khi gom chunk, cần dùng ước lượng bộ nhớ hoặc trọng lượng đại diện cho từng item. Đừng gọi một con số byte ước tính là dung lượng chính xác nếu nó chỉ dựa trên kích thước chuỗi đầu vào.

## 3. CompletionPolicy điều khiển thời điểm kết thúc chunk

Spring Batch dùng CompletionPolicy để xác định khi nào một lần lặp xử lý chunk nên hoàn tất. Policy mặc định thường dựa trên số item. Có thể dùng một policy khác để kết thúc chunk theo điều kiện riêng.

Với Spring Batch 5, StepBuilder hỗ trợ truyền CompletionPolicy cùng transaction manager:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        CompletionPolicy orderChunkPolicy,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(orderChunkPolicy, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
~~~

CompletionPolicy quyết định chunk hiện tại đã đủ điều kiện kết thúc hay chưa. Khi policy báo hoàn tất, framework chuyển các item đã đọc qua processor/writer theo cấu hình, sau đó hoàn thành transaction của chunk.

Một số policy có sẵn:

- **SimpleCompletionPolicy:** kết thúc sau một số lần lặp, thường tương ứng số item.
- **TimeoutTerminationPolicy:** kết thúc khi đạt giới hạn thời gian.
- **CompositeCompletionPolicy:** kết hợp nhiều policy, ví dụ giới hạn số item và thời gian.

Không phải policy có sẵn nào cũng đo byte. Nếu muốn commit theo dung lượng dữ liệu, thường cần một CompletionPolicy tùy chỉnh có cách nhận kích thước của item đã đọc.

Với Spring Batch 4, API StepBuilder và cách truyền transaction manager có thể khác. Hãy dùng overload phù hợp với phiên bản đang triển khai.

## 4. Thiết kế size-based completion policy

Một policy theo kích thước cần biết tổng trọng lượng của các item đã được reader cung cấp cho chunk hiện tại. Có thể thiết kế theo mô hình:

1. Reader đọc một item.
2. Một wrapper đo hoặc ước lượng kích thước item đó.
3. Wrapper ghi trọng lượng của item vào một tracker dùng chung với policy.
4. CompletionPolicy cộng trọng lượng vào tổng của chunk.
5. Khi tổng đạt ngưỡng byte hoặc số item đạt giới hạn, policy kết thúc chunk.

Sơ đồ:

~~~text
ItemReader.read()
      |
      v
Size-aware reader wrapper
      |
      +--> trả item cho framework
      |
      +--> ghi estimated size vào tracker
                  |
                  v
          CompletionPolicy.update()
                  |
                  v
          Cộng dồn bytes / item count
                  |
          +-------+-------+
          |               |
       đạt ngưỡng?      chưa đạt
          |               |
          v               v
     kết thúc chunk    đọc item tiếp
          |
          v
     ItemWriter.write(chunk)
          |
          v
       commit
~~~

Ví dụ, có thể đặt ngưỡng 5 MB và giới hạn tối đa 500 item. Chunk kết thúc khi tổng trọng lượng đạt hoặc vượt 5 MB, hoặc khi đã có 500 item. Giới hạn số item vẫn cần thiết vì nhiều item rất nhỏ có thể khiến chunk chứa quá nhiều object dù tổng byte ước tính thấp.

Ngưỡng kích thước thường là mục tiêu gần đúng, không phải hard limit tuyệt đối. Item làm tổng vượt ngưỡng vẫn nằm trong chunk hiện tại; policy chỉ có thể kết thúc sau khi item đó đã được đọc. Nếu một item đơn lẻ lớn hơn ngưỡng, chunk có thể chỉ chứa item đó và vẫn vượt ngưỡng.

## 5. Theo dõi kích thước item trong reader

Một cách tách trách nhiệm là bọc ItemReader bằng một reader đo kích thước. Reader wrapper vẫn trả về từng item theo hợp đồng thông thường; nó chỉ ghi thêm trọng lượng item vào tracker.

Ví dụ abstraction:

~~~java
public class ItemSizeTracker {

    private final ThreadLocal<Long> lastSize = new ThreadLocal<>();

    public void record(long size) {
        if (size < 0) {
            throw new IllegalArgumentException("Item size must not be negative");
        }
        lastSize.set(size);
    }

    public OptionalLong takeLastSize() {
        Long size = lastSize.get();
        lastSize.remove();

        return size == null
                ? OptionalLong.empty()
                : OptionalLong.of(size);
    }

    public void clear() {
        lastSize.remove();
    }
}
~~~

Reader wrapper:

~~~java
public class SizeTrackingItemReader<T> implements ItemReader<T> {

    private final ItemReader<T> delegate;
    private final ToLongFunction<T> sizeEstimator;
    private final ItemSizeTracker tracker;

    public SizeTrackingItemReader(
            ItemReader<T> delegate,
            ToLongFunction<T> sizeEstimator,
            ItemSizeTracker tracker) {
        this.delegate = delegate;
        this.sizeEstimator = sizeEstimator;
        this.tracker = tracker;
    }

    @Override
    public T read() throws Exception {
        T item = delegate.read();

        if (item == null) {
            tracker.clear();
            return null;
        }

        tracker.record(sizeEstimator.applyAsLong(item));
        return item;
    }
}
~~~

Size estimator tùy thuộc loại item. Với một String, có thể đo số byte UTF-8:

~~~java
ToLongFunction<String> utf8Size =
        value -> value.getBytes(StandardCharsets.UTF_8).length;
~~~

Với một object Order, có thể ước lượng theo trường:

~~~java
ToLongFunction<Order> orderSize =
        order -> estimateOrderBytes(order);
~~~

Hàm estimateOrderBytes là logic ứng dụng cần định nghĩa theo cấu trúc dữ liệu thực tế. Nếu writer serialize Order thành JSON, cách chính xác hơn cho payload là đo byte của JSON sau khi serialize. Nếu chỉ dùng độ dài các trường String, hãy xem đó là ước lượng và tính thêm các trường số, delimiter, encoding và overhead phù hợp.

Tracker cần được dùng chung giữa reader wrapper và CompletionPolicy trong cùng execution. Ví dụ trên dùng ThreadLocal để lưu kích thước item vừa đọc trên thread hiện tại; khi triển khai multi-threaded Step hoặc reader bất đồng bộ, cần bảo đảm reader và policy đọc cùng execution context/thread hoặc dùng cơ chế truyền trọng lượng an toàn phù hợp.

## 6. Ví dụ CompletionPolicy theo byte và số item

Ví dụ dưới đây minh họa một CompletionPolicy tùy chỉnh. Policy kết thúc chunk khi đạt ngưỡng byte ước tính hoặc giới hạn item, đồng thời tôn trọng tín hiệu EOF.

~~~java
public class EstimatedBytesCompletionPolicy implements CompletionPolicy {

    private static final String TOTAL_BYTES = "estimatedBytes.total";
    private static final String ITEM_COUNT = "estimatedBytes.items";

    private final long maxBytes;
    private final long maxItems;
    private final ItemSizeTracker tracker;

    public EstimatedBytesCompletionPolicy(
            long maxBytes,
            long maxItems,
            ItemSizeTracker tracker) {
        if (maxBytes <= 0 || maxItems <= 0) {
            throw new IllegalArgumentException("Limits must be positive");
        }

        this.maxBytes = maxBytes;
        this.maxItems = maxItems;
        this.tracker = tracker;
    }

    @Override
    public RepeatContext start(RepeatContext parent) {
        tracker.clear();
        return new RepeatContextSupport(parent);
    }

    @Override
    public void update(RepeatContext context) {
        OptionalLong size = tracker.takeLastSize();

        if (size.isEmpty()) {
            return;
        }

        long bytes = value(context, TOTAL_BYTES) + size.getAsLong();
        long items = value(context, ITEM_COUNT) + 1;

        context.setAttribute(TOTAL_BYTES, bytes);
        context.setAttribute(ITEM_COUNT, items);
    }

    @Override
    public boolean isComplete(RepeatContext context) {
        return value(context, TOTAL_BYTES) >= maxBytes
                || value(context, ITEM_COUNT) >= maxItems;
    }

    @Override
    public boolean isComplete(
            RepeatContext context,
            RepeatStatus result) {
        return result == RepeatStatus.FINISHED || isComplete(context);
    }

    private long value(RepeatContext context, String key) {
        Object value = context.getAttribute(key);
        return value instanceof Number
                ? ((Number) value).longValue()
                : 0L;
    }
}
~~~

Các lớp RepeatContextSupport, RepeatContext, RepeatStatus và CompletionPolicy thuộc Spring Batch Repeat API. Ví dụ thể hiện ý tưởng triển khai cho Spring Batch 5; cần đặt reader wrapper và policy trong cùng phạm vi Step, đồng thời đăng ký đúng các bean theo cấu hình ứng dụng.

Policy giữ hai bộ đếm trong RepeatContext của chunk:

- TOTAL_BYTES là tổng trọng lượng item đã đọc.
- ITEM_COUNT là số item đã đọc.

Mỗi lần update(), policy lấy trọng lượng mới nhất từ tracker và cộng vào context. Khi một trong hai ngưỡng đạt được, isComplete() trả true. Nếu reader trả null và vòng lặp kết thúc, overload nhận RepeatStatus cũng kết thúc chunk để framework xử lý các item còn lại.

Nếu dùng policy này, reader wrapper phải ghi tracker cho mỗi item không-null. Không để tracker giữ lại kích thước của item trước khi EOF hoặc trước khi lần đọc kế tiếp thất bại.

## 7. Gắn reader wrapper và policy vào Step

Khi cấu hình Spring, reader wrapper và policy phải dùng cùng một ItemSizeTracker. Có thể tách reader gốc thành bean riêng rồi bọc nó.

Ví dụ cấu trúc cấu hình:

~~~java
@Bean
ItemSizeTracker orderItemSizeTracker() {
    return new ItemSizeTracker();
}

@Bean
@StepScope
ItemReader<Order> sizeTrackingOrderReader(
        @Qualifier("delegateOrderReader") ItemReader<Order> delegate,
        ItemSizeTracker orderItemSizeTracker) {

    return new SizeTrackingItemReader<>(
            delegate,
            this::estimateOrderBytes,
            orderItemSizeTracker);
}

@Bean
@StepScope
CompletionPolicy orderSizeCompletionPolicy(
        ItemSizeTracker orderItemSizeTracker) {

    return new EstimatedBytesCompletionPolicy(
            5L * 1024 * 1024,
            500L,
            orderItemSizeTracker);
}
~~~

Trong ví dụ, estimateOrderBytes là hàm ước lượng được ứng dụng cung cấp. Bean delegateOrderReader là reader gốc, không phải chính reader wrapper, để tránh phụ thuộc vòng.

Step dùng policy:

~~~java
@Bean
Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        CompletionPolicy orderSizeCompletionPolicy,
        ItemReader<Order> sizeTrackingOrderReader,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<Order, Order>chunk(orderSizeCompletionPolicy, transactionManager)
            .reader(sizeTrackingOrderReader)
            .writer(orderWriter)
            .build();
}
~~~

Đây là cấu trúc minh họa cho cách kết nối các thành phần. Trong cấu hình thật, cần bảo đảm tracker được chia sẻ đúng giữa policy và reader trong cùng StepExecution. Nếu ứng dụng chạy nhiều JobExecution đồng thời, nên dùng bean theo scope phù hợp hoặc tracker có state riêng theo execution thay vì chia sẻ một accumulator mutable toàn cục.

## 8. Kết hợp giới hạn byte, số item và thời gian

Chỉ dùng một ngưỡng byte có thể chưa đủ.

Nếu item rất nhỏ, chunk có thể chứa số lượng item rất lớn trước khi đạt ngưỡng byte. Điều này làm tăng số object, chi phí xử lý và thời gian writer phải duyệt.

Nếu item rất lớn, một item có thể vượt ngưỡng ngay lập tức. Không có policy chunk nào có thể chia một item nghiệp vụ thành nhiều item một cách tự động.

Một cấu hình thực tế thường kết hợp:

- Ngưỡng byte ước tính để giới hạn payload hoặc lượng dữ liệu trong chunk.
- Số item tối đa để giới hạn số object.
- Thời gian tối đa nếu cần tránh giữ transaction quá lâu.

Ví dụ mục tiêu:

| Điều kiện | Ngưỡng minh họa |
|---|---:|
| Tổng kích thước ước tính | 5 MB |
| Số item tối đa | 500 |
| Thời gian tối đa | 10 giây |

Chunk hoàn tất khi một trong các điều kiện kết thúc được thỏa mãn. Có thể dùng CompositeCompletionPolicy để kết hợp policy có sẵn, hoặc viết một policy duy nhất theo nhiều điều kiện. Hãy kiểm tra semantics của composite policy ở phiên bản Spring Batch đang dùng, nhất là việc policy nào kết thúc toàn bộ chunk và cách các policy được reset giữa các chunk.

Không nên đặt ngưỡng quá thấp khiến writer và database phải commit liên tục. Cũng không nên đặt quá cao khiến một chunk giữ quá nhiều dữ liệu hoặc transaction kéo dài.

## 9. Giới hạn cứng và item vượt ngưỡng

Size-based policy thông thường chỉ kiểm tra sau khi một item đã được đọc. Vì thế, nó tạo ra giới hạn mục tiêu với độ vượt tối đa thường phụ thuộc kích thước item lớn nhất.

Ví dụ ngưỡng 5 MB:

~~~text
Chunk hiện tại: 4.7 MB
Item tiếp theo: 0.8 MB
Tổng mới:      5.5 MB
                |
                v
Policy kết thúc chunk sau item này
~~~

Chunk sẽ có khoảng 5.5 MB, không phải 5 MB chính xác.

Nếu cần giới hạn cứng, cần xử lý item quá lớn riêng:

- Kiểm tra kích thước trước khi đưa item vào chunk.
- Từ chối hoặc đưa item quá lớn vào luồng xử lý riêng.
- Chia nhỏ payload thành các đơn vị nghiệp vụ hợp lệ trước khi reader trả item.
- Dùng API hoặc writer hỗ trợ streaming nếu không cần giữ toàn bộ payload trong chunk.
- Giới hạn kích thước tối đa của một bản ghi ở đầu vào.

Không chia một item nghiệp vụ tùy tiện chỉ để đạt ngưỡng chunk nếu điều đó làm mất tính toàn vẹn dữ liệu.

## 10. Ảnh hưởng đến transaction và database

Dù CompletionPolicy kết thúc chunk theo byte, transaction semantics vẫn giống chunk thông thường:

1. Framework bắt đầu transaction.
2. Reader cung cấp các item đến khi policy kết thúc chunk hoặc nguồn hết.
3. Processor xử lý item.
4. Writer ghi các item còn lại.
5. Framework cập nhật stream state và checkpoint.
6. Transaction manager commit hoặc rollback theo kết quả.

Một chunk lớn hơn có thể giữ transaction và lock lâu hơn. Chunk nhỏ hơn có thể tăng số lần commit và chi phí round-trip database.

Kích thước dữ liệu là một yếu tố, nhưng cũng cần quan tâm:

- Số câu SQL được phát ra.
- Số bind parameter của batch update.
- Kích thước packet hoặc request của driver.
- Giới hạn payload của database hoặc API.
- Thời gian processor và writer.
- Lock contention và thời gian giữ connection.
- Dung lượng bộ nhớ tạm mà reader, processor và writer giữ.

Nếu writer dùng JDBC batch, kích thước chunk có thể ảnh hưởng số lệnh trong batch. Nếu driver có giới hạn số parameter hoặc kích thước packet, cần chọn ngưỡng phù hợp với giới hạn đó.

## 11. Ảnh hưởng đến retry, rollback và restart

CompletionPolicy chỉ quyết định khi nào chunk kết thúc. Nó không tự cung cấp khả năng restart cho reader hoặc writer.

Khi chunk rollback:

- Các thay đổi trong database tham gia transaction được hoàn tác.
- Các item của chunk có thể được đọc hoặc xử lý lại tùy reader và cơ chế retry.
- Reader và writer cần hỗ trợ state phù hợp nếu Step được restart.
- Nếu writer có tác động ngoài transaction, cần idempotency hoặc cơ chế đối soát.

Khi restart một JobInstance, checkpoint phải mô tả đúng ranh giới chunk đã commit. Nếu size tracker chỉ giữ dữ liệu tạm trong bộ nhớ, nó không phải checkpoint và không cần được persist. CompletionPolicy sẽ tạo accumulator mới cho chunk mới; trạng thái đọc/ghi bền vững được quản lý qua ExecutionContext của reader/writer nếu các component hỗ trợ.

Với custom reader hoặc writer, không lưu tổng byte của chunk vào một key dùng chung rồi giả định nó đại diện cho toàn bộ tiến độ Job. Tổng byte của chunk chỉ có ý nghĩa trong chunk hiện tại; checkpoint dài hạn cần lưu vị trí nguồn hoặc trạng thái đích phù hợp.

## 12. Những lỗi thường gặp

**Nhầm byte với số item.** chunk(100) là giới hạn theo số lần đọc, không phải 100 KB hay 100 MB.

**Đo sai đại lượng.** Kích thước String UTF-16, số byte UTF-8, kích thước JSON và bộ nhớ object là các con số khác nhau. Chọn metric phù hợp với mục tiêu.

**Chỉ giới hạn byte mà không giới hạn item.** Nhiều item nhỏ vẫn có thể tạo ra chunk chứa quá nhiều object.

**Tin rằng ngưỡng byte là hard limit.** Item cuối cùng có thể làm tổng vượt ngưỡng; một item riêng lẻ có thể lớn hơn toàn bộ ngưỡng.

**Đo payload sau khi chunk đã được tạo.** Nếu cần dùng kích thước để quyết định điểm kết thúc chunk, trọng lượng phải có sẵn trong lúc framework đang gom item. Đo trong writer là quá muộn để quyết định ranh giới chunk hiện tại.

**Tracker không được chia sẻ đúng.** Reader wrapper ghi vào tracker khác với tracker mà CompletionPolicy đọc thì tổng byte luôn sai hoặc bằng không.

**Dùng state toàn cục cho nhiều Job đồng thời.** Các execution có thể cộng dồn hoặc ghi đè trọng lượng của nhau. State cần được cô lập theo StepExecution hoặc thread/execution phù hợp.

**Bỏ qua item quá lớn.** Một record vượt ngưỡng cần được xử lý theo quy tắc nghiệp vụ, không nên âm thầm bỏ qua hoặc cắt dữ liệu.

**Tối ưu chỉ dựa trên dung lượng.** Database có thể bị giới hạn bởi số câu SQL, lock, index hoặc latency hơn là số byte. Hãy đo trên workload thực tế.

## 13. Khi nào không cần custom size-based policy?

Không phải Job nào cũng cần commit theo byte.

Dùng commit interval theo số item thường phù hợp khi:

- Kích thước item khá đồng đều.
- Writer xử lý một item với chi phí tương tự nhau.
- Database batch update hoạt động tốt với một số lượng item cố định.
- Không có giới hạn payload theo byte.
- Số item đã đủ để kiểm soát bộ nhớ và thời gian transaction.

Có thể bắt đầu với SimpleCompletionPolicy hoặc chunk size cố định, đo thời gian xử lý, bộ nhớ và thời gian commit, sau đó mới chuyển sang policy theo trọng lượng nếu có bằng chứng về biến động kích thước gây ra vấn đề.

Custom policy làm tăng độ phức tạp vì phải đo kích thước, truyền thông tin giữa reader và policy, quản lý scope và kiểm thử các trường hợp biên. Chỉ nên dùng khi metric theo byte mang lại lợi ích vận hành rõ ràng.

## 14. Kiểm thử commit theo kích thước dữ liệu

Khi kiểm thử custom CompletionPolicy, cần kiểm tra cả điều kiện kết thúc và transaction behavior của Step.

| Kịch bản | Điều cần xác nhận |
|---|---|
| Tổng byte dưới ngưỡng | Reader tiếp tục cung cấp item |
| Item làm tổng đạt ngưỡng | Chunk kết thúc sau item đó |
| Item làm tổng vượt ngưỡng | Item vẫn được giữ trong chunk; chunk kết thúc sau đó |
| Đạt max item trước max byte | Chunk kết thúc theo giới hạn item |
| Nguồn hết trước ngưỡng | Chunk cuối nhỏ hơn ngưỡng vẫn được ghi |
| Một item lớn hơn ngưỡng | Item được xử lý theo chính sách oversize đã chọn |
| Item có kích thước 0 | Không làm sai bộ đếm item |
| Reader trả null | Tracker không giữ trọng lượng của item trước |
| Hai JobExecution đồng thời | Tracker không trộn state giữa các execution |
| Writer lỗi | Chunk rollback theo transaction manager |
| Restart sau lỗi | Reader/writer tiếp tục theo checkpoint đã commit |

Nên dùng dữ liệu có kích thước phân bố khác nhau, không chỉ các item cùng độ dài. Có thể ghi log số item và tổng byte ước tính của mỗi chunk để quan sát policy hoạt động; tránh log toàn bộ nội dung item hoặc dữ liệu nhạy cảm.

Ngoài unit test cho CompletionPolicy, hãy chạy integration test với JobRepository và database phù hợp để xác nhận transaction thực sự commit theo chunk. Mock policy hoặc mock transaction manager không chứng minh được hành vi rollback của database.

## 15. Quy trình chọn ngưỡng commit

Khi triển khai commit theo kích thước, có thể làm theo trình tự:

1. Đo phân bố kích thước item thực tế, gồm trung vị, percentile cao và item lớn nhất.
2. Xác định metric cần giới hạn: byte nguồn, payload serialize hay ước lượng bộ nhớ.
3. Chọn ngưỡng byte ban đầu dựa trên giới hạn của writer, database hoặc API.
4. Đặt thêm max item để tránh chunk chứa quá nhiều object nhỏ.
5. Nếu cần, đặt timeout để giới hạn thời gian transaction.
6. Kiểm thử item vượt ngưỡng và nguồn hết giữa chunk.
7. Đo thời gian đọc, xử lý, ghi, commit, bộ nhớ và lock contention.
8. Điều chỉnh ngưỡng dựa trên workload thực tế.
9. Kiểm thử rollback, retry và restart với dữ liệu có kích thước biến động.

Ngưỡng commit không nên được chọn chỉ theo dung lượng tối đa mà database cho phép. Một transaction 5 MB nhưng kéo dài vài phút vẫn có thể gây lock và ảnh hưởng hệ thống. Ngược lại, nhiều chunk 50 KB có thể làm tăng overhead commit mà không đem lại lợi ích đáng kể.

Commit theo kích thước dữ liệu là một cách điều chỉnh ranh giới chunk khi kích thước item không đồng đều. CompletionPolicy cung cấp điểm mở rộng để áp dụng tiêu chí đó; reader hoặc thành phần đo lường cung cấp trọng lượng item; transaction manager vẫn quản lý commit/rollback của mỗi chunk. Khi kết hợp thêm giới hạn số item, timeout, xử lý item quá lớn và kiểm thử restart, Job có thể kiểm soát dung lượng mỗi lần ghi tốt hơn mà vẫn giữ được hành vi phục hồi của Spring Batch.

