# Chunk size ảnh hưởng throughput và memory

Trong Spring Batch, chunk-oriented processing đọc, xử lý và ghi dữ liệu theo từng nhóm item. Kích thước nhóm được cấu hình bằng **chunk size** hoặc **commit interval**. Giá trị này ảnh hưởng trực tiếp đến số lần commit transaction, lượng dữ liệu được giữ trong bộ nhớ, thời gian xử lý mỗi transaction và khả năng phục hồi khi có lỗi.

Chunk size lớn có thể giúp tăng throughput nhờ giảm chi phí commit lặp lại, nhưng cũng có thể làm transaction dài hơn và tăng bộ nhớ cần thiết. Chunk size nhỏ thường giới hạn lượng dữ liệu đang giữ và giảm phạm vi rollback, nhưng tạo nhiều transaction hơn. Không có một con số tối ưu cho mọi Job; cần chọn dựa trên đặc điểm item, reader, processor, writer, database và mức độ đồng thời của ứng dụng.

## 1. Chunk size là gì?

Một chunk là nhóm item được Spring Batch đọc và xử lý trước khi chuyển nhóm kết quả cho ItemWriter. Trong một chunk-oriented Step, luồng tiêu chuẩn gồm:

- **ItemReader** đọc item từ nguồn dữ liệu.
- **ItemProcessor** xử lý, biến đổi hoặc lọc item; có thể bỏ qua thành phần này nếu không cần.
- **ItemWriter** ghi các item của chunk ra đích.
- Spring Batch quản lý transaction và commit chunk theo kích thước được cấu hình.

Ví dụ, chunk size bằng 100 có nghĩa Step gom tối đa khoảng 100 item đã đọc cho một chunk trước khi gọi writer và hoàn tất transaction. Nếu nguồn dữ liệu chỉ còn 35 item ở cuối, chunk cuối có thể chứa 35 item.

~~~text
Chunk size = 3

Reader          Processor           Writer
  |                 |                  |
  +-- item 1 ------>+                  |
  +-- item 2 ------>+                  |
  +-- item 3 ------>+                  |
                    |                  |
                    +-- chunk [1,2,3] ->+--> ghi dữ liệu
                                       |
                                       +--> commit transaction

  +-- item 4 ------>+
  +-- item 5 ------>+
                    |
                    +-- chunk [4,5] --->+--> ghi dữ liệu
                                       |
                                       +--> commit transaction
~~~

Chunk cuối không nhất thiết có đủ số item như cấu hình. Ngoài ra, số item được writer nhận có thể nhỏ hơn số item reader đã đọc vì ItemProcessor có thể trả về null để lọc item. Vì vậy, cần phân biệt read count, process count, filter count và write count khi quan sát StepExecution.

### Khai báo chunk size

Với API Spring Batch 5 trở lên, chunk size được truyền vào StepBuilder cùng transaction manager:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Trong ví dụ, 100 là commit interval. Spring Batch gom item thành chunk theo giá trị này và quản lý transaction của Step qua transaction manager đã truyền vào.

Có thể đưa giá trị chunk size ra cấu hình để thay đổi giữa các môi trường mà không sửa code. Ví dụ khai báo một lớp cấu hình:

~~~java
@ConfigurationProperties(prefix = "batch.orders")
public class BatchOrderProperties {

    private int chunkSize = 100;

    public int getChunkSize() {
        return chunkSize;
    }

    public void setChunkSize(int chunkSize) {
        this.chunkSize = chunkSize;
    }
}
~~~

Đăng ký lớp cấu hình bằng **@EnableConfigurationProperties(BatchOrderProperties.class)** và inject BatchOrderProperties vào phương thức khai báo Step:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        BatchOrderProperties properties,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(properties.getChunkSize(), transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Giá trị có thể đặt trong application.properties:

~~~properties
batch.orders.chunk-size=100
~~~

Nên kiểm tra giá trị cấu hình ngay khi khởi động để tránh chunk size bằng 0 hoặc giá trị không hợp lệ. Việc đưa chunk size ra cấu hình cũng giúp chạy thử các mức khác nhau trong môi trường kiểm thử hiệu năng.

## 2. Chunk size ảnh hưởng đến throughput như thế nào?

**Throughput** là lượng công việc hoàn thành trong một đơn vị thời gian, ví dụ số bản ghi ghi thành công mỗi giây hoặc mỗi phút. Chunk size ảnh hưởng đến throughput vì nó quyết định tần suất thực hiện các thao tác theo transaction.

Mỗi chunk thường phát sinh một số chi phí cố định hoặc gần cố định:

- Bắt đầu và hoàn tất transaction.
- Ghi metadata và checkpoint của Step.
- Thực hiện round trip đến database.
- Gọi writer và xử lý batch statement.
- Đồng bộ hoặc flush dữ liệu theo cơ chế của resource.

Khi chunk size nhỏ, những chi phí này lặp lại thường xuyên. Nếu database có độ trễ commit đáng kể, thời gian dành cho commit có thể chiếm tỷ lệ lớn trong tổng thời gian xử lý.

Khi tăng chunk size, cùng một lượng item được chia thành ít chunk hơn. Chi phí commit và một số thao tác theo chunk được phân bổ trên nhiều item hơn, nên throughput có thể tăng.

Tuy nhiên, hiệu quả không tăng vô hạn. Khi bottleneck chuyển sang CPU, I/O, truy vấn database, network hoặc tốc độ của hệ thống đích, tăng chunk size có thể không giúp thêm. Nếu chunk quá lớn, transaction dài và lock kéo dài còn có thể làm throughput giảm.

### Mô hình chi phí đơn giản

Giả sử mỗi item cần thời gian xử lý trung bình là t và mỗi chunk có chi phí cố định là c. Với chunk size n, có thể hình dung thời gian một chunk gần đúng:

~~~text
T_chunk = n × t + c

Throughput gần đúng = n / T_chunk
~~~

Khi n tăng, chi phí cố định c được chia cho nhiều item hơn. Nhưng mô hình này chưa tính đến contention, GC, lock, batch write, timeout và các chi phí tăng theo kích thước transaction. Trong hệ thống thật, t và c cũng có thể thay đổi theo tải.

Ví dụ minh họa giả định:

| Chunk size | Thời gian một chunk | Throughput xấp xỉ |
| ---: | ---: | ---: |
| 50 | 1,2 giây | 41,7 item/giây |
| 100 | 1,8 giây | 55,6 item/giây |
| 250 | 3,5 giây | 71,4 item/giây |
| 500 | 8 giây | 62,5 item/giây |

Các con số trên chỉ minh họa cách tính, không phải benchmark của Spring Batch. Ở ví dụ này, tăng từ 50 lên 250 cải thiện throughput vì chi phí commit được phân bổ tốt hơn. Tăng tiếp lên 500 làm transaction và xử lý mỗi chunk kéo dài hơn, khiến throughput giảm.

### Khi nào tăng chunk size có thể cải thiện throughput?

Tăng chunk size thường đáng thử khi:

- Mỗi lần commit có độ trễ đáng kể.
- Writer hỗ trợ ghi theo batch và có thể xử lý nhiều item hiệu quả hơn trong một lần gọi.
- CPU và database còn dư tài nguyên.
- Item có kích thước bộ nhớ nhỏ và thời gian xử lý tương đối ổn định.
- Transaction hiện tại ngắn và chưa gây lock hoặc timeout.

Nếu writer thực hiện một câu INSERT riêng lẻ cho từng item và không tận dụng batch write, tăng chunk size có thể giảm số transaction nhưng chưa chắc giảm số round trip ghi dữ liệu. Cần xem cách writer thực sự tương tác với database.

### Khi nào tăng chunk size không giúp?

Tăng chunk size thường không giải quyết được bottleneck nếu:

- Mỗi item phải gọi một API từ xa với độ trễ cao.
- Một truy vấn database đang chiếm phần lớn thời gian xử lý.
- CPU đã bão hòa vì phép biến đổi dữ liệu.
- Database bị giới hạn IOPS hoặc lock contention.
- Writer đã bị giới hạn bởi tốc độ hệ thống đích.
- GC thường xuyên phải thu gom các object lớn.

Trong những tình huống này, cần tìm đúng bottleneck. Tối ưu truy vấn, giảm số lần gọi dịch vụ từ xa, dùng batch writer, điều chỉnh connection pool hoặc cải thiện thuật toán có thể mang lại hiệu quả lớn hơn việc tăng chunk size.

## 3. Chunk size ảnh hưởng đến memory như thế nào?

Chunk-oriented processing cần giữ các item của chunk trong quá trình đọc và xử lý, sau đó chuyển kết quả cho writer. Vì vậy, chunk size lớn thường làm tăng lượng object có thể tồn tại đồng thời trong heap.

Một cách ước lượng sơ bộ:

~~~text
Memory của chunk
    ≈ số item trong chunk
      × footprint trung bình của mỗi item
      + overhead của collection và framework
~~~

Footprint của item không chỉ là kích thước vài trường dữ liệu. Nó có thể bao gồm object graph được tham chiếu, chuỗi, collection con, dữ liệu nhị phân, object đầu ra do processor tạo và buffer bên trong reader hoặc writer.

Ví dụ giả sử một item cùng object graph chiếm khoảng 20 KB:

| Chunk size | Bộ nhớ thô ước lượng cho item |
| ---: | ---: |
| 100 | Khoảng 2 MB |
| 500 | Khoảng 10 MB |
| 1.000 | Khoảng 20 MB |
| 5.000 | Khoảng 100 MB |

Đây chỉ là phép ước lượng minh họa. Bộ nhớ thực tế có thể cao hơn do object header, reference, collection, dữ liệu trung gian, buffer, reader và writer. Nếu processor tạo object đầu ra mới hoặc giữ tham chiếu đến dữ liệu đầu vào, footprint còn có thể tăng.

### Bộ nhớ của toàn Step không chỉ là chunk

Chunk size là một yếu tố, nhưng tổng bộ nhớ còn phụ thuộc:

- Reader có buffer trước nhiều item hay không.
- Reader dùng paging và giữ một trang kết quả trong bộ nhớ hay không.
- Processor tạo object graph lớn hoặc cache dữ liệu hay không.
- Writer có buffer riêng trước khi ghi hay không.
- ORM có giữ entity trong persistence context hay không.
- ExecutionContext hoặc listener có giữ dữ liệu lớn hay không.
- Có bao nhiêu chunk hoặc worker đang hoạt động đồng thời.

Vì vậy, không nên suy ra rằng chunk size 100 luôn chỉ cần bộ nhớ của 100 object. Một reader paging có thể giữ thêm một trang, writer có thể tạo thêm batch, còn ORM có thể giữ entity đã được quản lý trong persistence context.

### Chunk size và số worker đồng thời

Nếu ứng dụng chạy nhiều partition hoặc nhiều worker song song, mỗi worker có thể có chunk đang xử lý riêng. Bộ nhớ dành cho các chunk có thể tăng theo số worker đồng thời:

~~~text
Memory dành cho item đang xử lý
    ≈ số worker đồng thời
      × chunk size
      × footprint trung bình của item
~~~

Ví dụ, bốn worker cùng xử lý chunk size 500, với footprint trung bình 20 KB mỗi item:

~~~text
4 × 500 × 20 KB ≈ 40 MB
~~~

Khoảng 40 MB chỉ là phần item thô theo giả định. Chưa tính reader/writer buffer, object trung gian, framework, thread stack, connection, ORM và overhead của JVM. Nếu tăng chunk size lên 2.000 trong cùng cấu hình bốn worker, phần item thô có thể lên khoảng 160 MB.

Chunk size không tự quyết định số worker hoặc số chunk chạy đồng thời. Concurrency đến từ cấu hình task executor, partitioning hoặc cơ chế chạy song song khác. Khi tuning, phải đánh giá chunk size cùng mức độ song song.

## 4. Chunk size và thời gian transaction

Trong chunk-oriented Step, một chunk là ranh giới commit thông thường. Transaction bắt đầu cho việc xử lý chunk và được hoàn tất sau khi writer thực hiện xong cùng các cập nhật liên quan.

Chunk size lớn thường kéo dài thời gian transaction vì nhiều item được đọc, xử lý và ghi trước khi commit. Điều này có thể gây:

- Lock trên database được giữ lâu hơn.
- Transaction timeout hoặc query timeout.
- Tăng nguy cơ deadlock khi nhiều Job cùng truy cập dữ liệu.
- Tăng lượng công việc cần rollback khi chunk thất bại.
- Làm các transaction khác phải chờ tài nguyên.

Chunk size nhỏ tạo transaction ngắn hơn, nhưng tăng số lần commit. Với database có chi phí commit cao, điều này có thể làm giảm throughput.

| Khía cạnh | Chunk nhỏ | Chunk lớn |
| --- | --- | --- |
| Số lần commit | Nhiều hơn | Ít hơn |
| Thời gian mỗi transaction | Thường ngắn hơn | Thường dài hơn |
| Bộ nhớ item đang giữ | Thường thấp hơn | Thường cao hơn |
| Phạm vi rollback | Thường nhỏ hơn | Có thể lớn hơn |
| Chi phí metadata theo chunk | Lặp lại nhiều hơn | Được phân bổ trên nhiều item hơn |
| Rủi ro lock/timeout | Có thể thấp hơn | Có thể cao hơn |
| Throughput | Có thể bị giới hạn bởi commit overhead | Có thể cao hơn đến khi gặp bottleneck khác |

Không nên đặt chunk size lớn chỉ để giảm số lần commit mà bỏ qua transaction timeout, lock và khả năng phục hồi.

## 5. Chunk size và phạm vi xử lý lại khi có lỗi

Chunk size cũng ảnh hưởng đến chi phí phục hồi. Nếu writer thất bại trước khi transaction commit, transaction của chunk hiện tại có thể rollback. Những chunk đã commit trước đó vẫn được lưu.

Với chunk lớn, nhiều item có thể nằm trong chunk đang thất bại. Khi retry hoặc restart, một phần công việc có thể phải thực hiện lại tùy loại exception, fault-tolerant configuration, reader, processor và writer.

Ví dụ:

~~~text
Chunk size = 4

Chunk 1: [1, 2, 3, 4] -> ghi thành công -> COMMIT
Chunk 2: [5, 6, 7, 8] -> writer lỗi -> ROLLBACK
Chunk 3: chưa được xử lý

Khi tiếp tục:
  dữ liệu của chunk 1 đã commit
  chunk 2 cần được xử lý theo chính sách retry/restart
~~~

Với chunk size lớn hơn, phạm vi item liên quan đến một transaction thất bại có thể lớn hơn. Điều này có thể làm tăng thời gian xử lý lại, đặc biệt khi processor thực hiện phép biến đổi tốn CPU hoặc reader phải truy cập nguồn dữ liệu chậm.

Tuy nhiên, không phải mọi lỗi đều khiến toàn bộ chunk luôn được xử lý lại theo cùng một cách. Spring Batch có cơ chế retry và skip; hành vi phụ thuộc thời điểm lỗi xảy ra, loại writer, reader có thể reset hay không và cấu hình fault-tolerant. Khi thiết kế, hãy thử nghiệm các lỗi thực tế và bảo đảm side effect có tính idempotent.

Với chunk size nhỏ, lượng item trong một transaction thường ít hơn, nên việc rollback và khôi phục thường có phạm vi hẹp hơn. Đổi lại, nhiều transaction hơn tạo thêm overhead trong trường hợp chạy bình thường.

## 6. Chunk size không giống fetch size hoặc batch size của writer

Một nhầm lẫn phổ biến là cho rằng chunk size điều khiển tất cả kích thước batch của database. Thực tế, đây là các tham số khác nhau:

| Tham số | Điều khiển điều gì? |
| --- | --- |
| **Chunk size / commit interval** | Số item trong một chunk và ranh giới commit của Step |
| **JDBC fetch size** | Gợi ý cho JDBC driver về số dòng lấy từ ResultSet mỗi lần fetch |
| **Paging page size** | Số dòng một truy vấn paging lấy về mỗi trang |
| **JDBC batch size** | Số câu lệnh hoặc parameter set được gửi theo một batch ghi, tùy writer/driver |
| **ORM flush/clear interval** | Tần suất đồng bộ và giải phóng entity trong persistence context |

Các giá trị này có liên quan nhưng không cần luôn bằng nhau. Ví dụ chunk size 500 có thể dùng reader fetch size 100 và writer JDBC batch size 100. Khi đó một chunk có thể được đọc qua nhiều lần fetch và ghi thành nhiều batch nhỏ trong cùng transaction.

### Reader dùng cursor hoặc paging

Với JDBC cursor reader, fetch size là gợi ý cho driver về cách lấy dữ liệu từ database. Chunk size vẫn quyết định số item được gom cho một lần ghi/commit. Tùy driver và cấu hình, fetch size có thể ảnh hưởng đến bộ nhớ ở phía client và số lần round trip.

Với paging reader, page size quyết định số dòng mỗi trang được truy vấn. Nếu page size nhỏ hơn chunk size, một chunk có thể cần đọc qua nhiều trang. Nếu page size lớn hơn chunk size, reader có thể giữ lại các item chưa được dùng trong trang hiện tại.

Không nên tăng fetch size hoặc page size chỉ vì đã tăng chunk size. Hãy đo riêng số lần query, lượng dữ liệu buffer, thời gian đọc và memory footprint.

### Writer dùng JDBC batch

Một writer có thể gom nhiều câu lệnh ghi để gửi xuống database theo batch. JDBC batch size ảnh hưởng số câu lệnh gửi trong mỗi lần thực hiện, còn chunk size ảnh hưởng transaction chứa các thao tác ghi.

Nếu chunk size là 1.000 nhưng writer gửi batch theo nhóm 100, một chunk có thể tạo nhiều lần executeBatch trong cùng transaction. Cấu hình này có thể cân bằng kích thước packet, giới hạn driver và transaction duration.

Với ORM/JPA, cần xem writer có flush hoặc clear persistence context hay không. Nếu entity được giữ lại lâu, persistence context có thể trở thành nguồn tiêu thụ heap đáng kể ngay cả khi chunk size có vẻ hợp lý.

## 7. Cách chọn chunk size ban đầu

Không có công thức chung áp dụng cho mọi ứng dụng. Có thể chọn giá trị khởi đầu dựa trên loại item và chi phí của reader/writer, sau đó đo bằng dữ liệu gần với thực tế.

Một số hướng suy nghĩ:

- Item nhỏ, xử lý nhẹ, writer hỗ trợ batch tốt: có thể thử chunk size trung bình hoặc lớn hơn.
- Item có object graph lớn, processor dùng nhiều bộ nhớ: bắt đầu với chunk nhỏ để giới hạn heap.
- Writer thực hiện thao tác chậm hoặc transaction có nguy cơ timeout: tránh chunk quá lớn.
- Database có commit latency cao: thử tăng chunk size để giảm tần suất commit.
- Có retry/skip phức tạp hoặc lỗi dữ liệu thường xuyên: cân nhắc chi phí xử lý lại của chunk lớn.
- Có nhiều worker song song: bắt đầu thận trọng vì mỗi worker có thể giữ một chunk cùng lúc.

Ví dụ, có thể bắt đầu đo với các mức 50, 100, 250 và 500. Đây chỉ là một dải thử nghiệm minh họa. Với item lớn hoặc heap nhỏ, dải phù hợp có thể thấp hơn nhiều; với item rất nhỏ và writer batch tốt, có thể thử giá trị cao hơn nếu transaction và database cho phép.

## 8. Quy trình tuning dựa trên số liệu

Tuning chunk size nên là một thử nghiệm có kiểm soát. Thay đổi nhiều tham số cùng lúc sẽ khó xác định nguyên nhân khiến kết quả thay đổi.

### Bước 1: Chọn dữ liệu đại diện

Sử dụng tập dữ liệu có kích thước, phân bố và đặc điểm tương tự production. Bao gồm item nhỏ và lớn, trường hợp processor lọc dữ liệu, dữ liệu ghi thực tế và các tình huống có lỗi nếu chúng thường xảy ra.

Không chỉ đo vài chục item nếu Job thực tế xử lý hàng triệu bản ghi. Overhead khởi động, JIT, cache và connection pool có thể làm kết quả của một lần chạy ngắn không đại diện.

### Bước 2: Thiết lập baseline

Chọn một chunk size ban đầu và ghi lại:

- Tổng thời gian Job và Step.
- Read count, write count, filter count, skip count.
- Số chunk hoặc số lần commit có thể quan sát.
- Thời gian trung bình và phân vị cao của một chunk nếu có instrumentation.
- Heap usage, GC pause và số lần GC.
- CPU usage và mức độ chờ I/O.
- Database latency, lock wait, deadlock, connection usage và log transaction.

Các số liệu này giúp phân biệt Job bị giới hạn bởi CPU, memory, database hay chi phí transaction.

### Bước 3: Thay đổi một yếu tố

Giữ nguyên dataset, concurrency, reader, processor, writer và cấu hình database. Thay chunk size theo từng mức, chạy lặp lại đủ số lần để giảm ảnh hưởng của cache, JIT và biến động hệ thống.

Ví dụ bảng ghi kết quả:

| Chunk size | Thời gian Step | Throughput | Heap peak | GC pause | DB commit latency |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 50 | Ghi số đo | Tính từ số item/thời gian | Ghi số đo | Ghi số đo | Ghi số đo |
| 100 | Ghi số đo | Tính từ số item/thời gian | Ghi số đo | Ghi số đo | Ghi số đo |
| 250 | Ghi số đo | Tính từ số item/thời gian | Ghi số đo | Ghi số đo | Ghi số đo |
| 500 | Ghi số đo | Tính từ số item/thời gian | Ghi số đo | Ghi số đo | Ghi số đo |

Throughput nên được tính trên số item thực sự hoàn thành theo cùng một định nghĩa giữa các lần chạy. Nếu một lần chạy skip nhiều item hơn, không nên chỉ so sánh write count mà bỏ qua khác biệt đó.

### Bước 4: Quan sát điểm bão hòa

Nếu throughput tăng khi tăng chunk size nhưng heap peak, GC pause và transaction duration vẫn trong giới hạn, có thể tiếp tục thử tăng có kiểm soát.

Nếu throughput gần như không tăng trong khi heap, GC hoặc lock tăng rõ rệt, đã đến vùng lợi ích giảm dần. Khi đó, chọn chunk size thấp hơn thường hợp lý hơn.

### Bước 5: Thử với concurrency thực tế

Sau khi chọn được một vài giá trị phù hợp cho một worker, hãy kiểm tra lại ở mức concurrency dự kiến. Nhiều worker có thể làm tăng tổng bộ nhớ, connection usage và contention trên database.

Đừng chọn chunk size dựa trên thử nghiệm đơn luồng rồi áp dụng nguyên trạng cho một Job chạy hàng chục partition.

### Bước 6: Kiểm tra tình huống lỗi và restart

Thử writer failure, lỗi tạm thời, skip và restart trong môi trường kiểm thử. Đo lượng công việc phải xử lý lại, thời gian rollback và khả năng khôi phục checkpoint. Một chunk size cho throughput cao trong điều kiện lý tưởng có thể không phù hợp nếu chi phí phục hồi quá lớn.

## 9. Ví dụ thực tế: nhập đơn hàng

Giả sử Job nhập 1.000.000 đơn hàng từ file vào PostgreSQL. Mỗi item được đọc, kiểm tra, chuyển thành entity và ghi vào bảng orders.

~~~text
File CSV
   |
   v
ItemReader
   |
   v
ItemProcessor
   |
   v
Chunk buffer
   |
   v
JDBC batch writer
   |
   v
PostgreSQL
~~~

Một cấu hình ban đầu có thể là:

~~~java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, businessTransactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .build();
~~~

Giả sử mỗi item sau khi parse và chuyển đổi có footprint khoảng 8 KB. Chunk size 100 tạo phần dữ liệu item thô khoảng 800 KB cho một worker, chưa tính overhead. Nếu tăng lên 1.000, phần item thô có thể khoảng 8 MB cho một worker.

Nếu Job chạy song song 8 worker, phần item thô tương ứng có thể khoảng 6,4 MB với chunk 100 hoặc 64 MB với chunk 1.000. Đây vẫn chỉ là ước lượng đơn giản; cần đo heap thực tế.

Nếu database có commit latency cao và writer hỗ trợ JDBC batch tốt, tăng từ 100 lên 250 hoặc 500 có thể giảm số lần commit và cải thiện throughput. Nhưng nếu mỗi đơn hàng có nhiều quan hệ entity, processor tạo object graph lớn hoặc transaction giữ lock trên bảng dùng chung, chunk lớn có thể làm heap và lock tăng mạnh.

Một phương án có thể thử:

| Thành phần | Giá trị thử nghiệm | Vai trò |
| --- | ---: | --- |
| Chunk size | 100, sau đó thử 250 và 500 | Số item trong một transaction chunk |
| JDBC fetch size | 100 | Số dòng gợi ý lấy mỗi lần fetch |
| JDBC batch size | 100 | Số thao tác ghi gom trong một batch |
| Worker concurrency | 1 trước, sau đó kiểm thử mức dự kiến | Số luồng xử lý đồng thời |

Các con số chỉ là điểm bắt đầu cho thử nghiệm. Cần điều chỉnh theo driver, writer, database, kích thước item và giới hạn heap của môi trường.

## 10. Dấu hiệu chunk size quá nhỏ hoặc quá lớn

### Dấu hiệu chunk size quá nhỏ

- Số lần commit rất cao so với số item.
- Transaction ngắn nhưng commit overhead chiếm tỷ lệ lớn.
- Database nhận nhiều thao tác commit nhỏ.
- CPU của ứng dụng không cao nhưng throughput thấp do chờ I/O hoặc commit.
- Writer có khả năng batch nhưng mỗi lần chỉ nhận rất ít item.

Trong trường hợp này, thử tăng chunk size và quan sát throughput, commit latency cùng transaction duration.

### Dấu hiệu chunk size quá lớn

- Heap peak tăng mạnh theo chunk size.
- GC pause kéo dài hoặc xuất hiện nhiều Full GC.
- Transaction duration vượt giới hạn mong muốn.
- Lock wait, deadlock hoặc timeout tăng.
- Khi lỗi xảy ra, thời gian rollback hoặc xử lý lại lớn.
- Throughput không tăng thêm hoặc bắt đầu giảm.

Khi thấy các dấu hiệu này, giảm chunk size và xác định thêm nguyên nhân từ reader, processor, writer hoặc concurrency.

## 11. Các nguyên tắc thực hành

**Đo trước khi tối ưu.** Throughput cần được đo trên dữ liệu đại diện. Không nên chọn chunk size chỉ dựa trên một con số phổ biến trong ví dụ hoặc tài liệu.

**Tính cả bộ nhớ trung gian.** Đừng chỉ nhân số item với kích thước object gốc. Xem xét object graph, output object, buffer của reader/writer và persistence context.

**Tuning cùng concurrency.** Mỗi worker có thể giữ chunk riêng. Tăng chunk size và số worker đồng thời có thể làm bộ nhớ tăng theo tích của hai yếu tố.

**Giữ transaction trong giới hạn.** Kiểm tra timeout, lock và deadlock khi tăng chunk size. Một transaction lớn có thể làm giảm khả năng phối hợp với các luồng ghi dữ liệu khác.

**Phân biệt các loại batch size.** Chunk size, JDBC fetch size, page size và JDBC batch size có mục đích khác nhau. Thay đổi từng giá trị theo bottleneck mà nó giải quyết.

**Thiết kế restart và idempotency.** Chunk lớn có thể làm phạm vi rollback hoặc xử lý lại lớn hơn. Writer và processor cần an toàn khi item được xử lý lại theo cơ chế retry/restart.

**Đưa cấu hình ra ngoài code.** Có thể cấu hình chunk size theo môi trường, nhưng cần validation và giới hạn giá trị hợp lý để tránh một thay đổi cấu hình gây quá tải heap hoặc database.

## 12. Quy trình chọn chunk size cho một Step

Khi thiết kế hoặc tối ưu Step, hãy lần lượt xác định:

1. Kích thước trung bình và trường hợp lớn nhất của item sau khi reader và processor tạo dữ liệu.
2. Số lượng item cần xử lý và throughput mục tiêu.
3. Chi phí đọc, xử lý và ghi cho từng item.
4. Độ trễ commit và giới hạn transaction của database.
5. Khả năng batch của writer và cấu hình fetch/page của reader.
6. Heap khả dụng, GC behavior và số worker đồng thời.
7. Chính sách retry/skip và chi phí xử lý lại khi chunk thất bại.
8. Kết quả benchmark với một vài chunk size trên dữ liệu đại diện.

Chọn giá trị đáp ứng throughput mục tiêu trong giới hạn memory, transaction và khả năng phục hồi. Nếu tăng chunk size không còn cải thiện throughput, hãy dừng ở mức thấp hơn có biên an toàn về tài nguyên.

## Kết luận

Chunk size quyết định số item được gom vào một chunk và ảnh hưởng đến tần suất commit, throughput, bộ nhớ đang sử dụng, thời gian transaction và phạm vi xử lý lại khi lỗi. Chunk lớn có thể giảm commit overhead nhưng thường giữ nhiều dữ liệu hơn và kéo dài transaction. Chunk nhỏ giới hạn memory và phạm vi rollback nhưng có thể tăng chi phí commit. Hãy tuning dựa trên số liệu về throughput, heap, GC, database latency, transaction duration và concurrency trên dữ liệu đại diện của ứng dụng.
