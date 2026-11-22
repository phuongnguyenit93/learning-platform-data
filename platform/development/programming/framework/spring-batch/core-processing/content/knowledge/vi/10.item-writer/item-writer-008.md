# Writer thứ tự item

Trong Spring Batch, ItemWriter nhận các item đã được đọc và xử lý từ một chunk rồi ghi chúng ra đích. Thứ tự item có thể quan trọng khi tạo file, xuất báo cáo, gửi thông điệp hoặc ghi dữ liệu cần giữ trình tự nghiệp vụ.

Điều cần phân biệt là **thứ tự item trong một chunk**, **thứ tự các chunk được xử lý** và **thứ tự dữ liệu được nhìn thấy ở hệ thống đích**. Trong một Step chạy tuần tự, Spring Batch chuyển các item đến writer theo thứ tự của luồng đọc sau khi processor xử lý và filter. Khi dùng xử lý song song, thứ tự hoàn thành giữa các chunk hoặc partition có thể khác thứ tự đọc ban đầu. Với database, thứ tự insert cũng không bảo đảm thứ tự truy vấn nếu câu SELECT không có ORDER BY.

Vì vậy, nếu nghiệp vụ yêu cầu thứ tự xác định, cần thiết kế thứ tự từ nguồn dữ liệu, lựa chọn mô hình chạy và cách ghi/đọc ở đích. Không nên dựa vào thứ tự vật lý của bản ghi trong database.

## 1. ItemWriter nhận dữ liệu theo chunk

Trong chunk-oriented Step, luồng cơ bản là:

~~~text
ItemReader
    |
    v
Đọc item theo thứ tự nguồn
    |
    v
ItemProcessor
    |
    +---- trả null: item bị filter
    |
    v
Các item còn lại trong chunk
    |
    v
ItemWriter
    |
    v
Ghi dữ liệu ra đích
~~~

ItemWriter không tự động sắp xếp item theo ID, thời gian hoặc một thuộc tính nào. Writer nhận chunk do framework chuyển đến và thực hiện thao tác ghi. Nếu writer cần một thứ tự khác, ứng dụng phải chủ động quy định thứ tự đó.

Trong Spring Batch 5, hợp đồng ItemWriter nhận một Chunk:

~~~java
public interface ItemWriter<T> {
    void write(Chunk<? extends T> chunk) throws Exception;
}
~~~

Các phiên bản cũ hơn dùng List trong phương thức write:

~~~java
void write(List<? extends T> items) throws Exception;
~~~

Sự khác biệt về kiểu tham số không làm thay đổi nguyên tắc thiết kế: writer nhận một nhóm item đã được xử lý, và thứ tự trong nhóm phản ánh thứ tự các item được chuyển qua pipeline. Với Spring Batch 5, có thể duyệt item trong chunk theo thứ tự:

~~~java
public class OrderWriter implements ItemWriter<Order> {

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            writeOne(order);
        }
    }

    private void writeOne(Order order) {
        // Ghi một order theo logic của ứng dụng.
    }
}
~~~

Nếu writer ghi từng item tuần tự như ví dụ, thao tác ghi trong một lần gọi tuân theo thứ tự duyệt chunk. Nếu writer gom lệnh, gọi dịch vụ bất đồng bộ hoặc gửi dữ liệu qua nhiều thread, cần xem xét thứ tự mà chính writer tạo ra.

## 2. Thứ tự trong một Step chạy tuần tự

Với một chunk-oriented Step chạy tuần tự, reader trả item theo thứ tự nào thì các item còn lại sau processor thường đến writer theo thứ tự đó. Processor được gọi trên từng item theo luồng xử lý của chunk. ItemProcessor có thể:

- Trả về một object cùng kiểu hoặc kiểu khác để thay đổi biểu diễn của item.
- Trả về null để filter item khỏi kết quả.
- Ném exception để báo lỗi, từ đó Step áp dụng chính sách fail, retry hoặc skip.

Processor thông thường không làm thay đổi vị trí của item trong chuỗi. Tuy nhiên, một processor tùy chỉnh có thể giữ item, gom nhóm hoặc phát ra dữ liệu theo logic riêng; nếu nó làm vậy, ứng dụng phải tự chịu trách nhiệm về thứ tự đầu ra.

Ví dụ reader trả các mã đơn hàng theo thứ tự 101, 102, 103, 104. Processor filter đơn hàng 102:

~~~text
Reader:       101 -> 102 -> 103 -> 104
Processor:    101 -> null -> 103 -> 104
Writer:       [101, 103, 104]
~~~

Writer nhận các item còn lại theo thứ tự 101, 103, 104. Filter tạo ra khoảng trống trong dãy nhưng không tự đảo thứ tự các item còn lại.

Nếu reader là FlatFileItemReader, thứ tự thường theo thứ tự dòng trong file. Nếu reader đọc từ database, thứ tự phải được quy định trong truy vấn. Không nên giả định database trả bản ghi theo thứ tự ID hoặc thứ tự insert nếu truy vấn không có ORDER BY.

## 3. Xác định thứ tự ngay tại ItemReader

Nếu thứ tự là yêu cầu nghiệp vụ, nên bắt đầu bằng cách xác định một khóa sắp xếp ổn định ở nguồn dữ liệu.

### Với JDBC reader

Truy vấn cần có ORDER BY:

~~~sql
SELECT
    order_id,
    created_at,
    customer_code,
    total_amount
FROM orders
WHERE status = 'READY'
ORDER BY created_at ASC, order_id ASC;
~~~

Ở đây created_at quy định thứ tự thời gian. order_id là khóa phụ để phân biệt các bản ghi có cùng created_at. Nếu chỉ ORDER BY created_at và nhiều bản ghi có timestamp giống nhau, thứ tự giữa các bản ghi đó không được xác định đầy đủ.

Nên chọn khóa sắp xếp:

- Có ý nghĩa rõ đối với nghiệp vụ.
- Ổn định trong suốt lần chạy.
- Có thêm tie-breaker duy nhất nếu khóa chính không duy nhất.
- Có index phù hợp nếu tập dữ liệu lớn và truy vấn cần hiệu năng tốt.

### Với paging reader

JDBC paging reader chia dữ liệu thành các trang. Các sort keys phải xác định thứ tự ổn định giữa các trang. Nếu sort key không duy nhất, bản ghi có cùng giá trị có thể bị trả về ở vị trí không ổn định giữa các truy vấn trang, đặc biệt khi dữ liệu nguồn thay đổi trong lúc Job chạy.

Ví dụ sort key có thể gồm created_at và order_id. Cần bảo đảm cách sắp xếp được dùng nhất quán ở mọi trang. Với dữ liệu thay đổi liên tục, nên xem xét phạm vi dữ liệu cố định, snapshot hoặc điều kiện lọc theo watermark để tránh bản ghi mới chen vào giữa quá trình phân trang.

### Với file reader

FlatFileItemReader thường đọc theo thứ tự dòng trong file. Nếu file được tạo từ nhiều nguồn hoặc được sort trước đó, thứ tự đầu vào phản ánh cách file đã được tạo. Nếu cần thứ tự nghiệp vụ, hãy xác định nó ở bước tạo file hoặc đọc dữ liệu vào một nguồn có thứ tự xác định.

## 4. Chunk boundary và thứ tự giữa các chunk

Chunk size chia luồng item thành các nhóm để xử lý và commit. Với Step chạy tuần tự, Spring Batch xử lý các chunk theo trình tự của luồng đọc:

~~~text
Nguồn: 1 2 3 4 5 6 7 8
Chunk size = 3

Chunk 1: [1, 2, 3] -> Writer -> Commit
Chunk 2: [4, 5, 6] -> Writer -> Commit
Chunk 3: [7, 8]    -> Writer -> Commit
~~~

Trong trường hợp này, writer được gọi theo thứ tự chunk 1, chunk 2, rồi chunk 3. Thứ tự item trong mỗi chunk cũng theo luồng đọc sau khi xử lý.

Chunk size không phải là một chỉ số sắp xếp. Tăng hoặc giảm chunk size làm thay đổi ranh giới commit và số item mỗi lần writer nhận, nhưng không tự thay đổi thứ tự đọc của một Step tuần tự.

Nếu một chunk thất bại, retry hoặc restart có thể làm item trong chunk được thực hiện lại. Side effect ở writer cần được thiết kế phù hợp để ghi lại an toàn. Thứ tự thực thi lại không nên được dùng như một cơ chế tạo số thứ tự nghiệp vụ.

## 5. Thứ tự khi xử lý song song

Khi bật concurrency, không thể mặc định thứ tự hoàn thành giữa các chunk giống thứ tự đọc. Một chunk có thể xử lý nhanh hơn chunk trước và ghi xong trước. Đây là hệ quả tự nhiên của việc nhiều thread cùng làm việc.

~~~text
Thứ tự tạo chunk:

Chunk 1 ----------- xử lý lâu ----------------> ghi xong
Chunk 2 ----- xử lý nhanh ----> ghi xong
Chunk 3 -------- xử lý vừa --------> ghi xong

Thứ tự hoàn thành có thể là:
Chunk 2 -> Chunk 3 -> Chunk 1
~~~

Trong một multi-threaded Step, chunk được xử lý trên các thread khác nhau. Spring Batch không bảo đảm thứ tự hoàn thành toàn cục giữa các chunk. Nếu các chunk ghi vào cùng một file hoặc một resource không thread-safe, cần đồng bộ writer hoặc thiết kế output riêng cho từng worker.

Ngoài ra, ItemReader được chia sẻ giữa các thread phải hỗ trợ truy cập đồng thời hoặc được bảo vệ thích hợp. Nhiều reader không thread-safe. Đồng bộ hóa một reader có thể bảo vệ trạng thái đọc nhưng không tự tạo bảo đảm thứ tự commit của các chunk.

### Partitioning

Với partitioned Step, dữ liệu được chia thành các phạm vi hoặc phân vùng xử lý độc lập:

~~~text
Master Step
    |
    +-- Partition 1: order_id 1-1000
    |
    +-- Partition 2: order_id 1001-2000
    |
    +-- Partition 3: order_id 2001-3000
~~~

Mỗi partition có thể chạy trên một worker khác nhau. Thứ tự bên trong từng partition có thể được giữ theo reader và Step của partition đó, nhưng thứ tự hoàn thành giữa các partition không được bảo đảm. Nếu output chung cần một thứ tự toàn cục, cần có bước hợp nhất hoặc sắp xếp sau khi các partition hoàn tất.

### Chọn concurrency khi thứ tự là yêu cầu bắt buộc

Nếu nghiệp vụ yêu cầu ghi tuần tự theo đúng thứ tự nguồn, lựa chọn đơn giản nhất thường là giữ Step tuần tự. Nếu cần tăng throughput, có thể chia dữ liệu thành partition có phạm vi rõ ràng, ghi output riêng từng partition rồi hợp nhất theo khóa sắp xếp sau đó.

Không nên hy sinh thứ tự nghiệp vụ bằng cách bật nhiều thread mà không có thiết kế output và merge phù hợp.

## 6. AsyncItemProcessor và AsyncItemWriter

Spring Batch cung cấp AsyncItemProcessor và AsyncItemWriter để xử lý processor bất đồng bộ. AsyncItemProcessor gửi công việc xử lý đến executor và trả về Future. AsyncItemWriter chờ các Future rồi chuyển kết quả cho writer delegate.

Trong một chunk, AsyncItemWriter duyệt các Future theo thứ tự chúng xuất hiện trong chunk và thu kết quả tương ứng. Vì vậy, thời điểm một Future hoàn thành không nhất thiết quyết định vị trí kết quả trong chunk đầu ra. Một item xử lý nhanh có thể hoàn tất trước item đứng trước nó nhưng kết quả vẫn được thu theo thứ tự danh sách Future.

~~~text
Chunk đầu vào: [A, B, C]

Async processing:
    A ----------- hoàn tất sau cùng
    B --- hoàn tất đầu tiên
    C ------ hoàn tất thứ hai

AsyncItemWriter thu kết quả theo danh sách Future:
    [result(A), result(B), result(C)]
~~~

Điều này giúp giữ thứ tự trong chunk khi dùng cặp AsyncItemProcessor và AsyncItemWriter theo cách thiết kế của chúng. Tuy nhiên, cần phân biệt với việc chạy nhiều chunk đồng thời: thứ tự giữa các chunk vẫn có thể khác. Ngoài ra, exception trong Future thường được phát hiện khi AsyncItemWriter lấy kết quả, nên cần cấu hình và quan sát lỗi đúng vị trí.

Ví dụ cấu hình rút gọn:

~~~java
@Bean
public AsyncItemProcessor<OrderInput, Order> asyncProcessor(
        ItemProcessor<OrderInput, Order> delegate,
        TaskExecutor taskExecutor) {

    AsyncItemProcessor<OrderInput, Order> processor =
            new AsyncItemProcessor<>();
    processor.setDelegate(delegate);
    processor.setTaskExecutor(taskExecutor);
    return processor;
}

@Bean
public AsyncItemWriter<Order> asyncWriter(
        ItemWriter<Order> delegate) {

    AsyncItemWriter<Order> writer = new AsyncItemWriter<>();
    writer.setDelegate(delegate);
    return writer;
}
~~~

Khi dùng cặp này, kiểu dữ liệu đầu ra của AsyncItemProcessor là Future<Order>, vì vậy writer trong Step phải được khai báo tương ứng với kiểu item mà async writer nhận. Cần đối chiếu API cụ thể của phiên bản Spring Batch đang sử dụng.

Async processing không tự động làm writer thread-safe. AsyncItemWriter thường tập hợp kết quả trước rồi gọi delegate writer; nếu delegate hoặc resource bên dưới có cơ chế concurrency riêng, ứng dụng vẫn phải bảo đảm an toàn.

## 7. Thứ tự trong writer và hệ thống đích

Giữ thứ tự khi gọi writer chưa đồng nghĩa dữ liệu được lưu ở đích sẽ luôn được đọc lại theo thứ tự đó. Điều này đặc biệt quan trọng với database.

### Database không bảo đảm thứ tự hàng nếu không ORDER BY

Ngay cả khi writer insert item 1 trước item 2, câu truy vấn:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders;
~~~

không có bảo đảm trả về theo thứ tự insert, thứ tự khóa chính hoặc thứ tự vật lý trên đĩa. Optimizer có thể chọn execution plan khác, index khác hoặc cách đọc khác.

Nếu cần kết quả có thứ tự, hãy truy vấn:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
ORDER BY created_at ASC, order_id ASC;
~~~

Thứ tự phải được biểu diễn bằng dữ liệu có thể sắp xếp, không dựa vào vị trí vật lý của hàng.

### Lưu sequence hoặc sort key nghiệp vụ

Nếu thứ tự xử lý cần được bảo toàn qua nhiều lần đọc, hãy lưu một trường sequence hoặc sort key:

~~~java
public class Order {
    private String orderId;
    private LocalDateTime createdAt;
    private long sourceSequence;
}
~~~

sourceSequence có thể là số dòng trong file, vị trí trong nguồn hoặc số thứ tự được cấp từ một quy trình tạo dữ liệu. Writer ghi giá trị này cùng bản ghi. Khi đọc lại, truy vấn dùng:

~~~sql
SELECT order_id, created_at, source_sequence
FROM orders
ORDER BY source_sequence ASC;
~~~

Nếu nhiều file hoặc nhiều partition cùng tạo sequence, cần bổ sung file ID, partition ID hoặc một khóa duy nhất để tạo thứ tự toàn cục ổn định. Không dùng bộ đếm trong bộ nhớ của từng worker nếu cần thứ tự duy nhất trên toàn Job.

### File writer

Với FlatFileItemWriter chạy trong Step tuần tự, các item được ghi theo thứ tự writer nhận. Nếu output được ghi đồng thời từ nhiều worker, cần xem xét đồng bộ hóa hoặc ghi ra file riêng theo partition. Sau đó có thể merge các file theo sort key.

Không nên cho nhiều thread cùng ghi vào một file tuần tự nếu writer không hỗ trợ concurrency. Ngay cả khi mỗi lần write nhận một chunk có thứ tự, các lần gọi write có thể xen kẽ hoặc hoàn thành theo thứ tự khác khi có concurrency.

## 8. Sắp xếp trong writer có giải quyết được không?

Writer có thể sắp xếp item trong chunk trước khi ghi:

~~~java
public class SortedOrderWriter implements ItemWriter<Order> {

    private final OrderRepository repository;

    public SortedOrderWriter(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        List<Order> sorted = chunk.getItems().stream()
                .sorted(Comparator.comparing(Order::getCreatedAt)
                        .thenComparing(Order::getOrderId))
                .toList();

        repository.saveAll(sorted);
    }
}
~~~

Ví dụ này chỉ sắp xếp **trong từng chunk**. Nếu chunk 2 chứa createdAt sớm hơn một item ở chunk 1, việc sort riêng mỗi chunk không tạo ra thứ tự toàn cục giữa hai chunk.

Muốn sắp xếp toàn bộ dữ liệu, cần một trong các chiến lược:

- Đọc nguồn đã có thứ tự toàn cục ổn định bằng ORDER BY.
- Ghi dữ liệu vào staging table kèm sort key, rồi xuất hoặc xử lý tiếp bằng truy vấn ORDER BY.
- Ghi output riêng từng partition, sau đó merge bằng một bước sort có kiểm soát.
- Dùng external sort hoặc cơ chế sắp xếp ngoài bộ nhớ nếu dữ liệu quá lớn để nạp toàn bộ vào heap.

Không nên gom toàn bộ dữ liệu vào một List trong writer chỉ để sort nếu tập dữ liệu có thể lớn. Cách đó phá lợi ích giới hạn bộ nhớ của chunk-oriented processing và có thể gây OutOfMemoryError.

## 9. Skip, retry và thứ tự item

Trong Step tuần tự, skip một item thường tạo khoảng trống trong luồng output nhưng không làm đảo thứ tự các item còn lại. Ví dụ item 2 bị skip thì writer có thể nhận [1, 3, 4].

Retry có thể khiến một item được đọc hoặc xử lý lại tùy loại lỗi và cấu hình. Với writer, một lỗi khi ghi chunk có thể làm transaction rollback; lần thử lại cần ghi dữ liệu theo cách an toàn. Nếu writer gửi message hoặc gọi API ngoài transaction database, retry có thể tạo side effect trùng.

Khi thứ tự là yêu cầu nghiệp vụ, cần lưu ý:

- Skip có thể làm thiếu một số sequence; đây không nhất thiết là lỗi nếu bản ghi bị từ chối đã được ghi nhận.
- Retry không nên làm một item được áp dụng hai lần ở hệ thống đích.
- Writer cần idempotent hoặc có khóa nghiệp vụ để chống ghi trùng.
- Không nên đánh số item bằng một biến tăng đơn giản trong writer nếu nhiều chunk chạy song song.
- Khi cần kiểm toán thứ tự, hãy lưu source sequence và trạng thái xử lý thay vì suy ra từ thời điểm commit.

## 10. Ví dụ: xuất file theo thứ tự nghiệp vụ

Giả sử cần xuất các đơn hàng theo thời gian tạo. Reader truy vấn database với sort key ổn định:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = 'READY'
ORDER BY created_at ASC, order_id ASC;
~~~

Step chạy tuần tự với chunk size 100:

~~~java
@Bean
public Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
~~~

Nếu writer là FlatFileItemWriter được cấu hình ghi tuần tự, file output giữ thứ tự item mà reader cung cấp, trừ các item bị filter hoặc skip theo chính sách.

Nếu sau này Step chuyển sang chạy song song, cần đánh giá lại yêu cầu. Có thể ghi mỗi partition ra một file riêng và thêm sort key vào từng dòng, sau đó chạy một Step merge để tạo file cuối cùng theo createdAt và orderId. Đây là cách tách việc tăng throughput khỏi yêu cầu thứ tự toàn cục.

## 11. Những lỗi thường gặp

### Giả định database trả dữ liệu theo thứ tự insert

Thứ tự vật lý không phải hợp đồng của SQL. Hãy dùng ORDER BY với khóa sắp xếp rõ ràng.

### ORDER BY bằng một cột không duy nhất

Nếu nhiều hàng có cùng giá trị sort key, thứ tự giữa chúng có thể thay đổi. Bổ sung tie-breaker duy nhất như primary key.

### Nghĩ rằng chunk size quyết định thứ tự

Chunk size điều khiển kích thước nhóm và ranh giới commit. Nó không sắp xếp item và không tạo thứ tự nghiệp vụ.

### Bật multi-threaded Step rồi vẫn mong thứ tự toàn cục

Chunk có thể hoàn tất khác thứ tự. Nếu thứ tự là bắt buộc, giữ xử lý tuần tự hoặc thiết kế partition và merge có sort key.

### Dùng writer không thread-safe

Nhiều worker cùng ghi vào một resource có thể làm dữ liệu xen kẽ, lỗi hoặc hỏng output. Dùng resource riêng, writer thread-safe hoặc bước hợp nhất sau đó.

### Sort từng chunk nhưng tưởng đã sort toàn bộ

Sort trong writer chỉ tạo thứ tự nội bộ mỗi chunk. Muốn thứ tự toàn cục, cần sort nguồn hoặc merge/sort sau khi tất cả chunk đã hoàn tất.

### Dựa vào thời điểm commit để suy ra thứ tự nghiệp vụ

Thời điểm hoàn tất transaction bị ảnh hưởng bởi concurrency, lock và tải hệ thống. Hãy lưu sequence hoặc business sort key.

### Ghi side effect không idempotent khi retry

Một lần retry có thể gửi trùng message hoặc ghi trùng dữ liệu nếu writer gọi hệ thống ngoài transaction. Dùng idempotency key hoặc outbox phù hợp.

## 12. Cách thiết kế thứ tự item

Khi thứ tự item quan trọng, hãy trả lời các câu hỏi:

1. Thứ tự được xác định bởi nguồn nào: thứ tự dòng file, thời gian, ID hay một sequence nghiệp vụ?
2. Khóa sắp xếp có duy nhất và ổn định không? Nếu không, cần tie-breaker nào?
3. Reader có ORDER BY hoặc cơ chế duy trì thứ tự đầu vào không?
4. Processor có filter, buffer hoặc thay đổi thứ tự item không?
5. Step có chạy tuần tự, multi-threaded hay partitioned không?
6. Writer có ghi tuần tự và thread-safe không?
7. Hệ thống đích có bảo toàn thứ tự hay cần lưu sort key để truy vấn lại?
8. Khi retry/skip/restart, sequence và idempotency được quản lý ra sao?

Với luồng tuần tự, cách thiết kế thường đơn giản: nguồn có thứ tự ổn định, processor không reorder và writer ghi theo thứ tự nhận. Với luồng song song, cần chấp nhận thứ tự hoàn thành không xác định hoặc bổ sung sequence và bước merge để tạo output có thứ tự toàn cục.

## Kết luận

ItemWriter nhận các item theo thứ tự pipeline cung cấp trong từng chunk; trong Step tuần tự, thứ tự này theo luồng reader sau khi processor xử lý và filter. Chunk size không tự sắp xếp item. Khi chạy song song, thứ tự hoàn thành giữa các chunk hoặc partition có thể thay đổi. Database cũng không bảo đảm thứ tự truy vấn nếu thiếu ORDER BY. Muốn giữ thứ tự nghiệp vụ, hãy xác định sort key ổn định ở nguồn, hiểu tác động của concurrency, ghi sequence khi cần và truy vấn hoặc merge dữ liệu theo khóa đó.
