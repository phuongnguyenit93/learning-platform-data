# Memory của item trong một chunk

Trong Spring Batch, một **chunk** là nhóm item được đọc, xử lý và ghi như một đơn vị công việc. Khi Step xử lý chunk, các item và kết quả trung gian được giữ trong bộ nhớ cho tới khi framework hoàn tất việc ghi và kết thúc transaction của chunk. Vì vậy, kích thước chunk ảnh hưởng trực tiếp tới lượng heap mà Step có thể cần tại một thời điểm.

Chunk size càng lớn thì thường có càng nhiều item được giữ cùng lúc. Tuy nhiên, bộ nhớ thực tế không chỉ phụ thuộc vào số item. Kích thước object graph, việc processor tạo object mới, reader prefetch theo trang, writer buffer, retry và số chunk chạy đồng thời đều có thể làm tăng mức sử dụng bộ nhớ.

Hiểu vòng đời của item trong chunk giúp bạn chọn commit policy phù hợp, tránh giữ dữ liệu quá lâu và xử lý các tập dữ liệu lớn ổn định hơn.

## 1. Item đi qua một chunk như thế nào?

Với chunk-oriented Step, Spring Batch điều phối ba thành phần chính:

- **ItemReader** đọc một item từ nguồn.
- **ItemProcessor** kiểm tra, lọc hoặc chuyển đổi item.
- **ItemWriter** ghi các item đầu ra của chunk.

Luồng cơ bản:

~~~text
Nguồn dữ liệu
     |
     v
 ItemReader
     |
     v
 Các item đầu vào được gom
 trong chunk hiện tại
     |
     v
 ItemProcessor
     |
     v
 Các item đầu ra hợp lệ
     |
     v
 ItemWriter
     |
     v
 Commit transaction
     |
     v
 Chunk tiếp theo
~~~

Giả sử Step được cấu hình chunk size bằng 100:

~~~java
@Bean
public Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawCustomer> reader,
        ItemProcessor<RawCustomer, Customer> processor,
        ItemWriter<Customer> writer) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<RawCustomer, Customer>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Spring Batch đọc tối đa 100 item cho một chunk thông thường, xử lý chúng rồi chuyển kết quả sang writer. Khi chunk hoàn tất thành công, transaction được commit và Step chuyển sang chunk tiếp theo.

Chunk size là số item đầu vào tối đa được gom cho một lần xử lý theo cấu hình này. Nó không phải số lượng item chắc chắn được ghi, vì processor có thể lọc item và chính sách skip có thể loại bỏ item lỗi.

## 2. Những object nào có thể nằm trong bộ nhớ?

Trong lúc một chunk đang được xử lý, heap có thể chứa nhiều loại object:

| Thành phần | Dữ liệu có thể được giữ |
|---|---|
| Reader | Item vừa đọc, trang dữ liệu prefetch, buffer ký tự hoặc trạng thái cursor |
| Chunk đầu vào | Các item được đọc cho chunk hiện tại |
| Processor | Object trung gian, DTO, entity mới hoặc dữ liệu phụ trợ |
| Chunk đầu ra | Các item đã được chuyển đổi và sẽ được writer nhận |
| Writer | Batch parameter, buffer ghi file hoặc danh sách chờ ghi |
| Framework | Metadata thực thi, context, exception và trạng thái chunk |
| Ứng dụng | Cache, collection hoặc tham chiếu được giữ bởi service/listener |

Ví dụ processor chuyển RawCustomer thành Customer mới:

~~~java
public Customer process(RawCustomer input) {
    return new Customer(
            input.id(),
            input.name().trim(),
            normalizeEmail(input.email())
    );
}
~~~

Trong quá trình chuyển đổi, item đầu vào và object đầu ra có thể cùng tồn tại trong bộ nhớ. Nếu mỗi Customer giữ thêm một object graph lớn, mức sử dụng heap có thể cao hơn nhiều so với kích thước chuỗi dữ liệu nhìn thấy trong file.

Nếu processor chỉ sửa object đầu vào rồi trả lại chính object đó, có thể tránh tạo thêm một object đầu ra lớn. Tuy nhiên, cách này chỉ phù hợp khi việc thay đổi object là an toàn và không làm ảnh hưởng dữ liệu nguồn hoặc các thành phần khác.

Không nên giả định mỗi item chỉ chiếm đúng kích thước các trường dữ liệu của nó. Một object có thể tham chiếu tới list, map, entity liên quan, byte array hoặc các object khác. Khi 100 item cùng giữ những object graph lớn, tổng heap có thể tăng nhanh.

## 3. Chunk giữ item trong bao lâu?

Một cách hình dung đơn giản:

~~~text
Bắt đầu chunk
     |
     v
Đọc item 1
Đọc item 2
...
Đọc item N
     |
     v
Xử lý các item
     |
     v
Writer nhận kết quả
     |
     v
Cập nhật checkpoint/metadata
     |
     v
Transaction commit
     |
     v
Chunk hoàn tất
     |
     v
Các tham chiếu của chunk
được giải phóng khi không còn dùng
~~~

Trong quá trình xử lý, framework cần giữ các item đủ lâu để processor và writer có thể sử dụng chúng. Sau khi chunk hoàn tất, các tham chiếu nội bộ của chunk có thể được bỏ đi khi framework chuyển sang phần việc tiếp theo.

Tuy nhiên, **chunk commit không có nghĩa JVM lập tức thu hồi toàn bộ bộ nhớ của item**. Garbage Collector chỉ có thể thu hồi object khi không còn tham chiếu sống tới object đó. Nếu ứng dụng lưu item vào một collection toàn cục, cache, field của singleton service hoặc listener, object vẫn còn được giữ lại sau khi chunk kết thúc.

Ví dụ một processor vô tình tích lũy dữ liệu:

~~~java
@Component
public class CustomerProcessor
        implements ItemProcessor<RawCustomer, Customer> {

    private final List<Customer> allCustomers = new ArrayList<>();

    @Override
    public Customer process(RawCustomer input) {
        Customer customer = convert(input);
        allCustomers.add(customer);
        return customer;
    }
}
~~~

Dù mỗi chunk đã commit, list allCustomers vẫn giữ mọi Customer đã xử lý. Khi dữ liệu đầu vào tăng lên, bộ nhớ tăng theo tổng số item của toàn Job thay vì chỉ theo chunk hiện tại.

Với batch lớn, tránh giữ toàn bộ item đã xử lý trong field hoặc collection tồn tại lâu. Nếu cần tổng hợp kết quả, hãy dùng bộ đếm, accumulator có giới hạn, bảng staging hoặc cơ chế ghi kết quả theo lô.

## 4. Chunk size ảnh hưởng đến heap như thế nào?

Chunk size là một trong những yếu tố quan trọng nhất quyết định số item được giữ trong một lần xử lý.

Giả sử mỗi item có kích thước thực tế trung bình tương đương 20 KB sau khi tính object graph liên quan. Nếu chunk giữ 500 item, riêng phần dữ liệu item có thể chiếm khoảng 10 MB. Đây chỉ là ước lượng minh họa; heap thực tế còn có object header, tham chiếu, collection, output object và buffer của các thành phần khác.

| Chunk size | Số item tối đa được gom | Xu hướng bộ nhớ |
|---:|---:|---|
| 10 | 10 | Working set nhỏ |
| 100 | 100 | Working set lớn hơn |
| 500 | 500 | Có thể tăng đáng kể nếu item nặng |
| 2.000 | 2.000 | Rủi ro heap cao hơn với object graph lớn |

Một chunk nhỏ hơn thường giảm lượng item được giữ đồng thời, nhưng làm tăng số transaction và commit. Chunk lớn hơn có thể tận dụng batch write hiệu quả hơn, nhưng tăng working set, thời gian transaction và lượng dữ liệu có thể phải xử lý lại khi rollback.

Không có một chunk size tốt cho mọi Job. Hãy đo với dữ liệu đại diện, đặc biệt là item lớn nhất hoặc có object graph phức tạp nhất, thay vì chỉ dùng kích thước trung bình.

## 5. Ước lượng bộ nhớ cho một chunk

Có thể dùng mô hình khái niệm sau để suy nghĩ về peak memory:

\[
M_{peak} \approx
C \times (S_{in} + S_{out} + S_{temp})
+ M_{reader}
+ M_{writer}
+ M_{framework}
\]

Trong đó:

- \(C\): số item đầu vào trong chunk.
- \(S_{in}\): kích thước trung bình của object đầu vào cùng object graph đang được giữ.
- \(S_{out}\): kích thước trung bình của object đầu ra.
- \(S_{temp}\): object trung gian do processor hoặc mapper tạo ra.
- \(M_{reader}\): bộ nhớ reader dùng cho page, prefetch hoặc buffer.
- \(M_{writer}\): bộ nhớ writer dùng cho batch và output buffer.
- \(M_{framework}\): các object và metadata khác.

Đây không phải công thức đo chính xác heap. Một số object có thể được dùng chung giữa nhiều item; một số object tạm đã trở thành unreachable trước khi chunk kết thúc; processor có thể trả lại chính input object. Mục đích của công thức là nhắc rằng chunk size chỉ là một phần của tổng working set.

Ví dụ:

- Chunk size: 500.
- Mỗi input item và object graph được giữ: khoảng 20 KB.
- Mỗi output item mới: khoảng 12 KB.
- Object trung gian: khoảng 4 KB mỗi item.

Ước lượng thô cho phần item:

\[
500 \times (20 + 12 + 4)\text{ KB}
= 18\text{ MB}
\]

Con số thực tế có thể cao hơn do collection, string, buffer, page prefetch, writer và các object khác. Nếu có 4 partition chạy đồng thời với working set tương tự, tổng bộ nhớ cho các chunk đang hoạt động có thể tăng gần theo số worker, ngoài các phần dùng chung.

## 6. Processor trả về null có giảm bộ nhớ không?

Trong Spring Batch, processor trả về null có nghĩa item bị filter và không được chuyển tới writer:

~~~java
@Bean
public ItemProcessor<RawCustomer, Customer> processor() {
    return raw -> {
        if (!raw.isActive()) {
            return null;
        }

        return convert(raw);
    };
}
~~~

Nếu chunk đọc 100 item nhưng 30 item bị filter, writer có thể chỉ nhận 70 item:

~~~text
Input chunk:       100 item
                       |
                       v
Processor:
  70 item hợp lệ
  30 item trả về null
                       |
                       v
Output chunk:       70 item
                       |
                       v
Writer ghi 70 item
~~~

Filter làm giảm số object đầu ra cần ghi, nhưng không có nghĩa bộ nhớ đầu vào được giải phóng ngay khi processor trả null. Framework vẫn cần hoàn tất việc xử lý chunk và quản lý trạng thái, skip, retry theo chính sách.

Nếu item đầu vào rất lớn, việc filter sớm có thể giảm lượng output và công việc writer, nhưng không nên dựa vào filter để thay thế việc kiểm soát kích thước chunk hoặc tránh tải object graph không cần thiết.

Nếu có thể xác định bản ghi không cần xử lý ngay từ truy vấn nguồn, đôi khi lọc ở query sẽ giảm cả số item được đọc và giữ trong chunk. Hãy bảo đảm điều kiện truy vấn phản ánh đúng nghiệp vụ và không loại nhầm dữ liệu.

## 7. Reader prefetch có thể làm bộ nhớ lớn hơn chunk size

Chunk size không giới hạn toàn bộ dữ liệu mà reader giữ. Một số reader đọc trước theo trang hoặc buffer để giảm số lần truy cập nguồn.

Ví dụ:

- **FlatFileItemReader** đọc file theo dòng và dùng buffer ký tự bên dưới.
- **JdbcPagingItemReader** lấy dữ liệu theo trang.
- **JdbcCursorItemReader** đọc qua cursor; JDBC driver có thể fetch theo nhóm tùy cấu hình.
- Reader tự viết có thể prefetch một số lượng item vào collection trước khi trả từng item.

Với reader paging, có thể tồn tại đồng thời:

1. Các item trong trang mà reader đã lấy về.
2. Các item đã được chuyển vào chunk hiện tại.
3. Các object đầu ra do processor tạo.
4. Các buffer của writer.

Vì vậy, page size và chunk size là hai khái niệm riêng:

| Cấu hình | Điều khiển |
|---|---|
| Chunk size / commit interval | Số item được gom cho một đơn vị xử lý và transaction |
| Page size | Số item reader lấy trong một lần truy vấn trang |
| JDBC fetch size | Gợi ý cho driver về số hàng nên fetch mỗi lần; hiệu quả tùy driver |
| Writer batch size | Số bản ghi writer gửi xuống hệ thống đích mỗi batch, nếu writer có cấu hình riêng |

Không bắt buộc page size phải bằng chunk size. Tuy nhiên, chênh lệch quá lớn có thể làm reader giữ nhiều item hơn mức cần thiết. Hãy đo và chọn cấu hình phù hợp với nguồn dữ liệu.

### Ví dụ reader tự prefetch toàn bộ dữ liệu

Một custom reader có thể gây lỗi bộ nhớ nếu làm như sau:

~~~java
public class InMemoryCustomerReader
        implements ItemReader<Customer> {

    private final Iterator<Customer> iterator;

    public InMemoryCustomerReader(CustomerRepository repository) {
        List<Customer> all = repository.findAll();
        this.iterator = all.iterator();
    }

    @Override
    public Customer read() {
        return iterator.hasNext() ? iterator.next() : null;
    }
}
~~~

Dù Step dùng chunk size bằng 100, constructor đã tải toàn bộ customer vào heap. Chunk không thể giới hạn bộ nhớ của một reader tự giữ toàn bộ nguồn.

Với dữ liệu lớn, hãy dùng cursor, paging, keyset pagination hoặc reader streaming phù hợp. Tránh gọi findAll() cho tập dữ liệu không có giới hạn.

## 8. Reader theo cursor và reader theo page

Hai chiến lược đọc thường có đặc tính bộ nhớ khác nhau.

### Cursor reader

Cursor reader thường duy trì một cursor hoặc result set mở và đọc item dần. Driver có thể dùng fetch size để lấy dữ liệu theo lô, nhưng không nhất thiết tải toàn bộ kết quả vào heap.

Cần chú ý:

- Cursor và connection có thể tồn tại trong thời gian Step chạy.
- Fetch size là gợi ý cho driver, không phải cam kết bộ nhớ tuyệt đối.
- Transaction và isolation ảnh hưởng thời gian giữ connection/cursor.
- Một số database hoặc driver có hành vi buffering riêng.

### Paging reader

Paging reader truy vấn dữ liệu theo từng trang. Page size ảnh hưởng số item reader lấy về trong một lần.

Cần chú ý:

- Page size quá lớn có thể giữ nhiều item cùng lúc.
- Thứ tự truy vấn phải ổn định để tránh mất hoặc lặp item giữa các trang.
- Dữ liệu nguồn thay đổi giữa các trang có thể ảnh hưởng tính nhất quán.
- Khi restart, reader cần lưu trạng thái trang hoặc khóa tiếp tục phù hợp.

Với cả hai loại, hãy kiểm tra tài liệu của reader và JDBC driver cụ thể. Không nên suy luận chỉ từ tên cursor hoặc paging rằng bộ nhớ luôn bị giới hạn theo một con số cố định.

## 9. Writer cũng tiêu thụ bộ nhớ

Sau khi processor tạo output, writer có thể cần thêm bộ nhớ để ghi theo batch hoặc buffer dữ liệu.

Ví dụ:

- JDBC batch writer có thể giữ tham số của batch cho tới khi gửi câu lệnh.
- File writer có buffer ký tự hoặc buffer giao dịch.
- Composite writer có thể chuyển cùng item tới nhiều delegate.
- Custom writer có thể tích lũy item trong collection trước khi ghi.

Nếu writer sao chép toàn bộ chunk sang một list khác, tại một thời điểm có thể có cả chunk gốc và bản sao. Nếu writer giữ tham chiếu tới các item đã ghi trong một field, bộ nhớ có thể tăng theo tổng số chunk.

Ví dụ writer tích lũy dữ liệu không giới hạn:

~~~java
public class UnsafeWriter implements ItemWriter<Customer> {

    private final List<Customer> written = new ArrayList<>();

    @Override
    public void write(Chunk<? extends Customer> chunk) {
        written.addAll(chunk.getItems());
    }
}
~~~

Writer này không ghi dữ liệu ra đích mà giữ toàn bộ item đã nhận trong list. Sau nhiều chunk, list tăng không giới hạn.

Nếu cần thống kê, chỉ giữ các giá trị nhỏ như counter hoặc tổng hợp theo nhóm. Nếu cần lưu chi tiết, ghi ra database/file hoặc hệ thống lưu trữ phù hợp thay vì giữ tất cả object trong heap.

## 10. Retry và rollback có thể giữ item lâu hơn

Khi chunk gặp lỗi và được retry, framework có thể cần giữ hoặc khôi phục các item đã đọc để thử lại. Hành vi cụ thể phụ thuộc loại reader, vị trí exception và cấu hình fault-tolerant.

Một số tình huống:

- Reader đã đọc item nhưng writer gặp lỗi.
- Processor gặp exception và item được retry.
- Skip policy yêu cầu xác định item gây lỗi.
- Chunk rollback khiến reader phải cung cấp lại dữ liệu.
- Reader có buffering hoặc transactional resource riêng.

Trong các trường hợp này, item có thể tồn tại lâu hơn một lần gọi processor thông thường. Nếu item chứa dữ liệu lớn, retry nhiều lần có thể làm tăng áp lực heap và thời gian giữ object.

Hãy giữ retry policy có giới hạn, chỉ retry lỗi tạm thời và tránh lưu thêm bản sao của item trong listener hoặc exception handler.

## 11. Nhiều chunk hoặc partition chạy song song

Khi Job xử lý song song, bộ nhớ không chỉ phụ thuộc một chunk. Mỗi worker hoặc partition đang hoạt động có thể có reader, chunk, processor và writer riêng.

Ví dụ có 4 partition, mỗi partition dùng chunk size 500:

~~~text
Worker 1: chunk 500 + reader/writer buffers
Worker 2: chunk 500 + reader/writer buffers
Worker 3: chunk 500 + reader/writer buffers
Worker 4: chunk 500 + reader/writer buffers
                  |
                  v
       Tổng working set đồng thời
       tăng theo số worker
~~~

Nếu mỗi chunk cần khoảng 18 MB cho item và object trung gian theo ước lượng trước, 4 chunk đồng thời có thể cần khoảng 72 MB chỉ cho phần đó, chưa tính buffer, framework, thread stack và các object dùng chung.

Vì vậy, tăng số partition hoặc thread có thể làm tăng thông lượng nhưng cũng làm tăng peak heap. Không nên nhân chunk size và concurrency lên cùng lúc mà chưa đo memory headroom.

Với partitioning, mỗi worker có StepExecution và ExecutionContext riêng. Cần tránh chia sẻ mutable object giữa các worker nếu không có đồng bộ phù hợp. Reader và writer của từng partition nên có resource và phạm vi dữ liệu độc lập.

## 12. CompletionPolicy và commit interval

Trong cấu hình thông thường, chunk size cố định quyết định khi nào chunk đủ số item để hoàn tất. Spring Batch cũng hỗ trợ CompletionPolicy để quyết định chunk kết thúc theo điều kiện khác.

Ví dụ, một policy có thể hoàn tất chunk theo số item hoặc thời gian. Khi dùng policy dựa trên thời gian, số item trong chunk có thể thay đổi theo tốc độ đọc và xử lý.

Điều này ảnh hưởng tới bộ nhớ:

- Fixed chunk size tạo giới hạn số item rõ ràng hơn.
- Time-based policy có thể gom nhiều item nếu nguồn đọc nhanh trong khoảng thời gian đó.
- Custom policy cần có giới hạn số item nếu muốn kiểm soát heap.
- Nếu policy chỉ dựa vào thời gian mà không giới hạn số item, tốc độ nguồn cao có thể làm chunk lớn hơn dự kiến.

Vì vậy, khi dùng CompletionPolicy, hãy xác định cả giới hạn thời gian và giới hạn số lượng. Đừng giả định một chunk có kích thước cố định nếu policy cho phép kết thúc theo điều kiện động.

## 13. Chunk size nhỏ hay lớn?

Lựa chọn chunk size là cân bằng giữa bộ nhớ, hiệu năng và transaction.

| Chunk size | Ưu điểm | Đánh đổi |
|---|---|---|
| Nhỏ | Working set thấp hơn; transaction ngắn; rollback ít item hơn | Nhiều lần commit; tăng overhead |
| Lớn | Có thể tận dụng batch write; ít lần commit hơn | Heap cao hơn; transaction dài; rollback tốn hơn |
| Quá lớn | Có thể giảm một số overhead trong workload phù hợp | Dễ tăng GC, giữ lock lâu và gặp OutOfMemoryError |

Ví dụ:

- Item chỉ gồm vài trường primitive/string ngắn: chunk lớn hơn có thể phù hợp.
- Item chứa ảnh, JSON lớn hoặc entity graph sâu: cần chunk nhỏ hơn.
- Writer ghi batch hiệu quả: có thể cần chunk vừa đủ lớn để tận dụng batch.
- Reader paging: cần phối hợp page size và chunk size.
- Nhiều partition: phải tính working set tổng của các worker.

Không có con số mặc định như 100, 500 hay 1.000 đúng cho mọi hệ thống. Hãy bắt đầu ở mức vừa phải, đo heap và thời gian xử lý, sau đó điều chỉnh.

## 14. Cách giảm memory footprint của item

### Chỉ đọc các trường cần thiết

Nếu processor chỉ cần ID, tên và trạng thái, đừng đọc toàn bộ entity với nhiều quan hệ hoặc blob.

Với JDBC, chọn rõ các cột cần thiết:

~~~sql
SELECT customer_id, customer_name, status
FROM customer
WHERE status = 'ACTIVE'
ORDER BY customer_id
~~~

Với JPA, cân nhắc projection hoặc DTO thay vì tải cả entity graph nếu không cần.

### Tránh eager loading dữ liệu lớn

Một item có thể kéo theo nhiều quan hệ eager hoặc collection. Hàng trăm item có thể làm tải hàng chục nghìn object liên quan.

Chỉ tải quan hệ cần dùng. Tránh để processor vô tình truy cập lazy relation khiến nhiều truy vấn và object graph được tạo thêm.

### Không giữ item trong collection toàn cục

Processor, writer và listener không nên tích lũy tất cả item trong field của singleton bean. Dùng counter, thống kê tổng hợp hoặc lưu kết quả ra ngoài heap.

### Xử lý theo streaming

Với file hoặc nguồn lớn, đọc từng dòng hoặc từng page. Tránh load toàn bộ file hoặc kết quả query vào List trước khi tạo chunk.

### Giảm object trung gian

Nếu chuyển đổi item tạo nhiều DTO/list/map lớn, xem xét chỉ tạo object cần thiết cho writer. Tránh copy nhiều lần cùng một payload.

### Chỉ giữ trạng thái cần thiết

ExecutionContext nên chứa checkpoint nhỏ như số dòng, page, ID cuối cùng hoặc vị trí reader. Không lưu toàn bộ item của chunk vào ExecutionContext.

## 15. Theo dõi bộ nhớ khi Job chạy

Các counter của StepExecution như readCount, writeCount, filterCount, commitCount và rollbackCount giúp hiểu tiến độ, nhưng không trực tiếp đo heap của item.

Để theo dõi memory, có thể dùng:

- JVM heap metrics qua Micrometer hoặc Spring Boot Actuator.
- Garbage collection metrics và GC logs.
- Java Flight Recorder (JFR) để quan sát allocation và object retention.
- Heap dump khi xảy ra OutOfMemoryError hoặc mức heap tăng bất thường.
- Profiling để tìm object giữ tham chiếu lâu.
- Dashboard theo JobExecution ID, StepExecution ID và partition.

Một số dấu hiệu thường gặp:

| Dấu hiệu | Khả năng cần kiểm tra |
|---|---|
| Heap tăng đều sau mỗi chunk | Processor/writer/listener đang giữ reference |
| Heap tăng mạnh khi bắt đầu Step | Reader tải toàn bộ nguồn hoặc prefetch quá lớn |
| Heap tăng theo số partition | Mỗi worker có working set riêng |
| GC chạy dày nhưng heap vẫn cao | Allocation rate lớn hoặc live set quá lớn |
| OutOfMemoryError trong writer | Batch buffer hoặc collection tích lũy |
| Heap không giảm sau khi Job hoàn tất | Có tham chiếu sống từ cache, singleton hoặc static collection |

Sau khi chunk kết thúc, heap đã dùng không nhất thiết giảm ngay trên biểu đồ. JVM có thể giữ vùng heap đã cấp phát để tái sử dụng. Điều cần quan sát là **live set** sau GC và xu hướng tăng qua nhiều chunk, không chỉ nhìn tổng heap đã committed.

## 16. Ước lượng và đo chunk trong môi trường thật

Một quy trình thực tế:

1. Chọn một tập dữ liệu đại diện, gồm cả item nhỏ và item lớn.
2. Chạy với chunk size nhỏ, chẳng hạn 50 hoặc 100.
3. Quan sát heap trước, trong và sau một số chunk.
4. Ghi nhận allocation rate, GC pause và thời gian commit.
5. Tăng chunk size từng bước và đo lại.
6. Thử với số partition/thread dự kiến trong production.
7. Thử trường hợp processor tạo output object mới và writer buffer batch.
8. Kiểm tra memory sau nhiều chunk để phát hiện collection tích lũy.

Không chỉ đo một chunk đầu tiên. Một số lỗi retention chỉ xuất hiện sau hàng nghìn chunk, khi ứng dụng tích lũy reference hoặc cache không giới hạn.

## 17. Ví dụ chọn chunk size theo loại dữ liệu

Giả sử có hai Job:

**Job A — nhập mã sản phẩm**

- Item nhỏ: ID, mã, tên ngắn.
- Processor chuẩn hóa vài chuỗi.
- Writer ghi JDBC batch.
- Reader paging theo ID.

Job này có thể thử chunk lớn hơn để tận dụng batch insert, miễn heap và transaction vẫn nằm trong giới hạn.

**Job B — xử lý hồ sơ khách hàng**

- Item chứa JSON lớn và nhiều quan hệ.
- Processor tạo DTO mới cùng các collection.
- Writer gọi service ngoài.
- Có nhiều partition chạy song song.

Job này nên bắt đầu với chunk nhỏ hơn và giới hạn số worker. Nếu cần xử lý payload lớn, có thể chỉ giữ ID trong chunk rồi tải chi tiết đúng lúc cần, hoặc xử lý payload theo streaming.

Không nên dùng cùng chunk size cho hai Job chỉ vì chúng chạy trên cùng một ứng dụng.

## 18. Những nhầm lẫn thường gặp

### Nghĩ rằng chunk size giới hạn toàn bộ heap

Chunk size chỉ giới hạn số item của một đơn vị xử lý theo policy. Reader có thể prefetch, writer có thể buffer và ứng dụng có thể giữ object ngoài chunk.

### Nghĩ rằng commit giải phóng bộ nhớ ngay

Commit kết thúc transaction, không ép JVM thu hồi object. Object chỉ có thể được GC khi không còn tham chiếu sống.

### Nghĩ rằng item bị filter không dùng bộ nhớ

Item đầu vào vẫn đã được đọc và có thể được giữ trong lúc chunk xử lý. Filter chủ yếu giảm output gửi tới writer.

### Nghĩ rằng page size và chunk size là một

Page size thuộc reader; chunk size thuộc commit policy của Step. Hai giá trị có thể khác nhau và cùng ảnh hưởng working set.

### Nghĩ rằng reader streaming chắc chắn dùng rất ít bộ nhớ

Driver, cursor, page buffer hoặc custom reader có thể prefetch dữ liệu. Cần đo và kiểm tra cấu hình thực tế.

### Nghĩ rằng tăng chunk size luôn tăng hiệu năng

Chunk lớn có thể giảm commit overhead nhưng làm tăng GC, transaction duration và rủi ro rollback. Hiệu năng cần được đo tổng thể.

### Nghĩ rằng garbage collection sẽ sửa được memory leak

GC chỉ thu hồi object không còn được tham chiếu. Collection toàn cục hoặc cache không giới hạn vẫn giữ object sống.

## 19. Quy trình kiểm soát memory cho một chunk

Khi thiết kế một chunk-oriented Step, hãy lần lượt xem:

1. Chunk size hoặc CompletionPolicy đang giới hạn số item ra sao?
2. Kích thước trung bình và lớn nhất của input item là bao nhiêu?
3. Processor có tạo output object hoặc object graph mới không?
4. Reader có prefetch theo page hoặc buffer toàn bộ nguồn không?
5. Writer có giữ batch hoặc collection riêng không?
6. Có retry/skip khiến item được giữ lâu hơn không?
7. Có bao nhiêu chunk/partition có thể hoạt động đồng thời?
8. Service, listener hoặc singleton có giữ reference qua nhiều chunk không?
9. ExecutionContext có chỉ lưu checkpoint nhỏ hay đang chứa payload?
10. Heap, allocation rate và live set thay đổi như thế nào qua thời gian?

Bộ nhớ của một chunk không chỉ là phép nhân chunk size với kích thước một object. Nó là tổng working set của reader, input, output, processor, writer và các worker đồng thời. Khi giữ object trong phạm vi chunk, tránh prefetch quá mức và không tích lũy reference qua nhiều chunk, Spring Batch có thể xử lý tập dữ liệu lớn với mức sử dụng heap ổn định hơn.
