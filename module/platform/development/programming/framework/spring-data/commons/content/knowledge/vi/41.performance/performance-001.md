# Phân biệt chi phí abstraction với chi phí truy vấn của store

## 1. Repository chậm chưa cho biết tầng nào chậm

Một API gọi repository và mất 500 ms không có nghĩa Spring Data Commons tiêu tốn 500 ms để xử lý abstraction. Trong khoảng đó, request có thể đang chờ connection, datastore đang quét nhiều dữ liệu, một truy vấn đếm đang chạy, hoặc ứng dụng đang đọc thêm quan hệ khi chuyển entity thành JSON.

Ngược lại, abstraction cũng không miễn phí. Proxy, metadata, chuyển đổi tham số, tạo đối tượng, projection và mapping đều sử dụng CPU hoặc bộ nhớ. Khi thao tác store rất nhanh, kết quả lớn hoặc tần suất gọi cao, phần chi phí phía ứng dụng có thể đáng kể.

Mục tiêu của phân tích hiệu năng là xác định **chi phí thuộc tầng nào, được trả bao nhiêu lần và có thể giảm mà vẫn giữ đúng hợp đồng nào**. Không nên bắt đầu bằng kết luận “repository luôn chậm” hoặc “database luôn là nút thắt”.

Spring Data Commons cung cấp các abstraction dùng chung như Repository, CRUD, derived queries, phân trang, sắp xếp, projection và auditing. Query creator, mapping, driver và datastore thực tế vẫn thuộc các module cùng thành phần tích hợp tương ứng. Việc dùng chung API không làm các store có cùng kế hoạch thực thi hay cùng chi phí.

## 2. Vẽ đường đi của một thao tác trước khi đo

Một lời gọi đọc dữ liệu có thể đi qua:

```text
Controller hoặc tác vụ ứng dụng
    -> service và transaction interceptor nếu có
    -> repository proxy
    -> chọn implementation hoặc query method
    -> module tạo/bind truy vấn
    -> chờ tài nguyên từ pool
    -> driver và truyền dữ liệu
    -> datastore thực thi
    -> đọc kết quả, convert và materialize đối tượng
    -> xử lý nghiệp vụ, projection hoặc chuyển DTO
    -> serialize response
```

Đây là mô hình khái quát. Thứ tự mở transaction, lấy connection, thực thi và đọc kết quả phụ thuộc module, provider và kiểu API. Một số giai đoạn còn có thể xen kẽ hoặc chồng lấp, đặc biệt với streaming và reactive.

### Phân loại chi phí theo trách nhiệm

| Nhóm chi phí | Ví dụ | Không nên quy hết cho |
| --- | --- | --- |
| Composition và dispatch | Repository proxy, chọn fragment, interceptor | Datastore |
| Metadata và chuẩn bị truy vấn | Phân tích method, mapping metadata, bind tham số | Thời gian thực thi SQL hoặc query phía server |
| Chuyển đổi và tạo đối tượng | Converter, entity, DTO, projection | Chỉ riêng repository proxy |
| Chờ tài nguyên | Hàng đợi connection pool, thread hoặc giới hạn đồng thời | Parser tên method |
| Driver và truyền dữ liệu | Giao thức, round trip, decode kết quả | Chỉ thời gian server xử lý |
| Thực thi ở store | Scan, join, sort, khóa, index, shard fan-out | Spring Data Commons |
| Công việc phát sinh | Count query, lazy loading, lookup trong callback | Một truy vấn nội dung duy nhất |
| Xử lý sau repository | Ghép dữ liệu, serialize, gọi dịch vụ khác | Method repository đã trả về |

Một số công việc nằm ở ranh giới giữa các nhóm. Điều quan trọng là đặt phạm vi đo nhất quán và tránh đếm hai lần. Chẳng hạn, timer quanh driver có thể đã bao gồm thời gian server cùng truyền kết quả; không cộng nguyên timer đó thêm một lần với thời gian server để tính tổng.

## 3. Chi phí khởi tạo khác chi phí mỗi lần gọi

### 3.1. Công việc thường xuất hiện khi tạo repository

Tùy module và cấu hình, việc phát hiện repository, xây dựng metadata, phân tích derived query và tạo đối tượng query có thể diễn ra trong quá trình khởi tạo hoặc ở lần sử dụng đầu tiên.

Do đó, không nên mặc định mỗi lần gọi `findByStatus()` đều phân tích lại toàn bộ tên phương thức từ đầu. Phần metadata hoặc cấu trúc query có thể được tái sử dụng, trong khi bind giá trị tham số và thực thi vẫn xảy ra cho từng lần gọi.

Cũng không nên giả định mọi chi phí này luôn đã được trả ở startup. Cơ chế lazy, deferred initialization hoặc đường truy vấn đặc thù có thể chuyển một phần sang lần gọi đầu tiên.

### 3.2. Lần gọi đầu còn chịu nhiều yếu tố khác

Một request đầu tiên có thể chậm vì:

- Class loading, JIT và khởi tạo các thành phần Java.
- Tạo connection, xác thực hoặc thiết lập kết nối mạng.
- Khởi tạo provider, codec, converter hoặc mapping metadata.
- Cache dữ liệu, cache kế hoạch hoặc các lớp cache khác còn lạnh.
- Datastore cần đọc trang dữ liệu chưa có trong bộ nhớ.

Nếu lấy duy nhất lần gọi đầu để so repository với native query, kết quả rất dễ phản ánh khác biệt warm-up. Cần báo riêng độ trễ khởi động/lần đầu và độ trễ khi hệ thống đã vận hành ổn định.

Warm-up cũng không có nghĩa được bỏ qua các yêu cầu cold-start của sản phẩm. Nếu ứng dụng thường được scale từ 0 hoặc mở kết nối mới, chi phí đó vẫn là một mục tiêu riêng cần đo.

## 4. Số lượt truy cập thường quan trọng hơn số lời gọi Java

### 4.1. Một repository method có thể tạo nhiều thao tác store

Ví dụ một API trả `Page<Course>` có thể cần truy vấn nội dung và truy vấn đếm tổng. Sau đó, việc đọc quan hệ của từng entity có thể tạo thêm truy vấn trong một số mô hình mapping.

```text
1 lần gọi repository ở mã ứng dụng
    -> query lấy trang dữ liệu
    -> có thể có query đếm
    -> có thể có query bổ sung khi đọc quan hệ
```

Số lần gọi repository không phải số round trip. Ngược lại, một thao tác có thể không cần truy cập store trong một số trường hợp cache hoặc persistence context đáp ứng được yêu cầu. Cần quan sát đường chạy thực tế.

### 4.2. `Page`, `Slice` và `List` có hợp đồng khác nhau

| Kiểu kết quả | Thông tin chính | Hệ quả hiệu năng cần xem |
| --- | --- | --- |
| `Page<T>` | Nội dung trang và metadata tổng số phần tử/trang | Có thể cần count query; một số trường hợp module có thể suy ra tổng hoặc tối ưu tránh đếm |
| `Slice<T>` | Nội dung lát dữ liệu và khả năng còn lát tiếp theo | Thường kiểm tra thêm dữ liệu để xác định có phần tiếp; không cam kết tổng số phần tử |
| `List<T>` với cơ chế giới hạn được hỗ trợ | Danh sách kết quả đã lấy | Không tự cung cấp tổng hoặc thông tin còn trang tiếp |

Không khẳng định mọi lần gọi trả `Page` luôn chạy đúng hai query. Cũng không coi `Slice` là miễn phí: nó vẫn phải lấy dữ liệu và có thể cần thêm một phần tử theo cách module triển khai.

Nếu giao diện chỉ cần nút “Tải thêm”, `Slice` có thể khớp yêu cầu hơn. Nếu nghiệp vụ bắt buộc biết tổng chính xác, bỏ count để đạt số đo đẹp hơn là thay đổi hợp đồng, không phải một phép so sánh tương đương.

### 4.3. N+1 là thay đổi hình dạng truy cập

Trong JPA, một danh sách entity có quan hệ lazy có thể phát sinh thêm truy vấn khi truy cập từng quan hệ. Số query cụ thể còn phụ thuộc cache, fetch plan, batch fetching và số đối tượng liên quan khác nhau.

Đây là chi phí truy cập phát sinh từ cách dùng mapping và dữ liệu. Nó không phải chi phí cố định của việc repository đi qua proxy. Thay proxy mà vẫn giữ nguyên cách duyệt quan hệ có thể không loại bỏ được các round trip đó.

Không áp nguyên khái niệm persistence context hoặc quan hệ lazy của JPA lên mọi module. Với document store hoặc API khác, việc ghép dữ liệu ở ứng dụng cũng có thể tạo nhiều lời gọi, nhưng cơ chế cần được phân tích riêng.

## 5. Cùng tên method không có nghĩa cùng chi phí truy vấn

Xét các method:

```java
List<Customer> findByTenantIdAndStatus(String tenantId, String status);

List<Customer> findByEmailContainingIgnoreCase(String text);

long countByTenantIdAndStatus(String tenantId, String status);
```

Cả ba đều là derived queries, nhưng công việc của store có thể rất khác:

- Equality trên khóa lọc phù hợp có thể dùng index hiệu quả.
- Tìm chuỗi con bỏ qua hoa thường có thể cần biểu thức hoặc chiến lược tìm kiếm khác, tùy store và collation.
- Đếm chính xác một tập lớn vẫn có thể phải xử lý nhiều entry hoặc bản ghi, ngay cả khi không trả entity.

Parser xử lý tên method không đủ để giải thích những khác biệt này. Cần xem query thật, tham số, kích thước dữ liệu, phân bố giá trị và kế hoạch thực thi.

Không nên khẳng định `ContainingIgnoreCase` luôn quét toàn bộ dữ liệu hoặc luôn không dùng được index. Store có thể có collation, expression index, text/search index hoặc primitive khác. Điều cần xác nhận là query mà module tạo có sử dụng được cơ chế đó theo semantics mong muốn hay không.

### Derived query và `@Query` không có thứ hạng tốc độ cố định

Nếu derived query và truy vấn khai báo tường minh tạo cùng query, cùng tham số, cùng dữ liệu trả về và cùng điều kiện chạy, phần thực thi phía store có thể tương đương. Đổi cách khai báo không tự làm query nhanh hơn.

Một `@Query` nhanh hơn có thể vì nó chọn ít field, thêm điều kiện, dùng join khác hoặc thay đổi chiến lược truy cập. Khi đó, cải thiện đến từ hình dạng truy vấn hoặc dữ liệu, không thể quy toàn bộ cho việc “bỏ parser”.

Với custom fragment, cũng cần xác định fragment thay đổi điều gì. Gọi thẳng template hoặc driver có thể thay đổi mapping, lifecycle, transaction và semantics cùng lúc; chênh lệch đo được không còn là phép đo riêng chi phí repository proxy.

## 6. Khối lượng dữ liệu và mapping có thể lấn át dispatch

### 6.1. Trả ít phần tử chưa chắc đọc ít dữ liệu

Một trang 20 entity có thể chứa nhiều cột lớn, document nhiều field hoặc dữ liệu quan hệ được tải bổ sung. Cần quan sát cả:

- Số dòng/document được store đọc để tìm kết quả.
- Số dòng/document trả về.
- Số byte truyền qua mạng.
- Số đối tượng và lượng bộ nhớ được cấp phát.
- Công việc serialize response cuối cùng.

Một query trả 20 phần tử sau khi quét hàng triệu bản ghi vẫn có thể đắt. Ngược lại, một query được index hỗ trợ tốt nhưng trả rất nhiều byte có thể bị giới hạn bởi truyền dữ liệu và materialization.

### 6.2. Projection có thể giảm chi phí nhưng cần xem query sinh ra

Ví dụ riêng cho một repository JPA có mapping phù hợp:

```java
interface CourseListView {
    Long getId();
    String getTitle();
    Instant getCreatedAt();
}
```

```java
interface CourseRepository extends Repository<Course, Long> {

    Slice<CourseListView> findByTenantIdAndStatus(
        String tenantId,
        String status,
        Pageable pageable
    );
}
```

```java
Pageable request = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")
    )
);
```

Các đoạn mã lược bỏ import và mapping của `Course`. Ví dụ thể hiện nhu cầu chỉ lấy các trường của danh sách và không cần tổng chính xác. Khả năng projection và tối ưu select phải được xác nhận cho module cùng dạng query cụ thể.

Không mặc định mọi projection đều khiến store chỉ đọc đúng vài field. Projection mở, biểu thức tính toán, đường dẫn lồng nhau hoặc join có thể làm giới hạn tối ưu khác nhau. Ngay cả khi query chỉ chọn ít cột, store vẫn có thể đọc thêm dữ liệu để lọc và sắp xếp.

Nếu response cần dữ liệu liên quan như tên giảng viên, phải đưa nhu cầu đó vào thiết kế query/projection đúng cách. Bỏ trường bắt buộc khỏi response để giảm thời gian không phải tối ưu giữ nguyên hành vi.

### 6.3. Streaming và reactive không xóa chi phí dữ liệu

`Stream<T>` có thể giúp xử lý dần, nhưng vẫn cần đóng tài nguyên và giữ phạm vi truy cập phù hợp. Trong JPA, persistence context cũng có thể giữ các entity đã đọc, nên streaming không tự bảo đảm bộ nhớ luôn thấp.

`Flux<T>` hoặc `Mono<T>` thay đổi mô hình thực thi và quản lý chờ. Chúng không làm query thiếu index chạy nhanh hơn một cách tự động. Cần đo cả thời gian subscription, phần tử đầu tiên, hoàn tất toàn bộ và khả năng hủy/giải phóng tài nguyên theo yêu cầu.

Nếu chỉ đo thời gian tạo publisher mà chưa subscribe, số đo chưa phản ánh truy vấn. Tương tự, đo thời gian trả stream mà không tiêu thụ có thể bỏ qua phần lớn công việc đọc kết quả.

## 7. Query plan và index thuộc store, không thuộc tên abstraction

Giả sử API lọc theo tenant, trạng thái và sắp xếp theo thời gian cùng ID. Với một cơ sở dữ liệu quan hệ hỗ trợ cú pháp tương ứng, index ứng viên có thể được minh họa:

```sql
CREATE INDEX idx_course_tenant_status_created_id
ON course (tenant_id, status, created_at DESC, id DESC);
```

Đây là ví dụ để phân tích, không phải công thức áp dụng cho mọi bảng hoặc mọi store. Tính hiệu quả phụ thuộc phân bố dữ liệu, độ chọn lọc, điều kiện khác, thứ tự sắp xếp và quyết định của optimizer. Index cũng tăng chi phí lưu trữ và ghi.

Các câu hỏi cần trả lời khi xem kế hoạch:

1. Store dùng index nào hoặc vì sao chọn scan?
2. Bao nhiêu bản ghi/entry được đọc so với số trả về?
3. Có sort lớn, spill, join tốn kém hoặc fan-out không?
4. Thời gian chủ yếu là CPU, I/O, chờ khóa hay chờ tài nguyên?
5. Count query có kế hoạch khác content query không?

Index hỗ trợ filter không tự biến mọi phép đếm chính xác thành thao tác hằng số. Phân trang offset sâu cũng có thể vẫn yêu cầu bỏ qua nhiều dữ liệu dù đã có index.

Nếu cần đọc tuần tự tập lớn, keyset/cursor pagination hoặc scrolling có thể phù hợp khi module và query hỗ trợ. Nó cần thứ tự ổn định, khóa phân định và hợp đồng điều hướng phù hợp; không thay thế trực tiếp mọi yêu cầu nhảy tới trang bất kỳ.

## 8. Chi phí ghi cũng cần phân rã

Một lời gọi `save()` có thể gồm nhận diện entity mới, chuyển đổi, callback, auditing, thao tác ghi và chờ transaction hoàn tất. Trong JPA, SQL có thể được thực hiện ở flush hoặc commit sau lời gọi `save()` tùy trạng thái và provider.

Do đó, benchmark chỉ bọc thời gian quanh `save()` có thể bỏ sót công việc ghi được trì hoãn. Để đo một đơn vị nghiệp vụ đã hoàn tất, cần xác định ranh giới transaction và mốc xác nhận của store.

### Không suy ra batching từ `saveAll()`

`saveAll()` là API lưu nhiều đối tượng. Hợp đồng abstraction không cam kết mọi module thực hiện nó thành một bulk operation hoặc một round trip.

Hiệu năng phụ thuộc:

- Entity mới hay cập nhật và cơ chế phát hiện trạng thái.
- Cách module/provider triển khai lưu nhiều đối tượng.
- Cấu hình batching, giới hạn kích thước và loại khóa sinh.
- Transaction, write concern hoặc mức xác nhận tương ứng.
- Callback, auditing và các truy vấn phụ trong logic ứng dụng.

Ví dụ, `AuditorAware` hoặc callback có thể truy vấn thêm dữ liệu nếu người viết cài đặt như vậy. Khi lưu nhiều entity, các lookup này có thể nhân lên. Phần chậm đó là công việc phát sinh trong đường ghi; không thể chỉ nhìn số lần gọi `saveAll()` rồi kết luận driver chậm.

Nếu chuyển sang bulk API để tăng tốc, cần kiểm tra lại version, callback, audit field và semantics lỗi. Bỏ qua một cơ chế bảo vệ dữ liệu để có số đo thấp hơn phải được nhận diện là thay đổi hành vi.

## 9. Thiết kế phép đo để phân biệt nguyên nhân

### 9.1. Bắt đầu từ một workload có ý nghĩa

Trước khi so sánh, cần cố định hoặc ghi nhận:

- Query và tập tham số đại diện, gồm trường hợp phổ biến và trường hợp nặng.
- Kích thước, phân bố dữ liệu và index.
- Kết quả cần trả, thứ tự, giới hạn và độ nhất quán yêu cầu.
- Transaction, mức xác nhận ghi, cache và connection pool.
- Mức đồng thời, thời gian warm-up và thời gian quan sát.

Một request đơn lẻ trên laptop không mô tả được hành vi khi nhiều request cạnh tranh pool hoặc cùng một bản ghi. Ngược lại, test tải quá cao có thể chủ yếu đo hàng đợi do hệ thống đã quá tải.

### 9.2. Đo theo các lớp quan sát

| Lớp quan sát | Dữ liệu hữu ích |
| --- | --- |
| API hoặc đơn vị nghiệp vụ | Latency, throughput, tỷ lệ lỗi, kích thước response |
| Service/repository | Số lời gọi, kiểu kết quả, phạm vi transaction |
| Driver/pool | Số thao tác thực tế, thời gian chờ pool, thời gian dùng connection |
| Store | Query plan, số bản ghi đọc, thời gian xử lý, khóa và tài nguyên |
| JVM | CPU profile, allocation, GC, số đối tượng materialize |

Cần liên kết các quan sát theo cùng request hoặc cùng workload. Query log có thể chứng minh số thao tác và hình dạng query, nhưng log đầy đủ cũng có chi phí và có thể chứa tham số nhạy cảm. Chọn mức ghi nhận vừa đủ cho mục tiêu đo.

Độ trễ trung bình có thể che các request chậm. Nên xem percentile như p50, p95, p99 khi có đủ dữ liệu, cùng throughput và tỷ lệ lỗi. Không cộng p95 của từng thành phần để suy ra p95 toàn request; chúng không nhất thiết thuộc cùng một lần thực thi.

### 9.3. Đo phần công việc thực sự hoàn tất

Đối với luồng đồng bộ, xác định timer kết thúc sau repository, sau mapping hay sau serialize. Với stream/reactive, cần tiêu thụ theo cùng khối lượng dữ liệu mà sản phẩm sử dụng. Với ghi có transaction, cần quan sát lỗi và thời gian ở commit.

Một số truy vấn có thể chỉ được thực hiện khi truy cập thuộc tính hoặc khi flush trước query khác. Nếu đặt timer sai vị trí, phần chi phí bị chuyển sang bước sau có thể bị hiểu nhầm là đã được loại bỏ.

## 10. So sánh abstraction với truy cập thấp hơn một cách công bằng

Có thể so sánh nhiều đường truy cập, nhưng phải ghi rõ khác biệt:

| So sánh | Có thể giúp hiểu | Không được kết luận ngay |
| --- | --- | --- |
| Repository và template dùng cùng query/mapping | Chi phí của một số lớp tổ chức phía trên | Mọi chênh lệch đều do proxy |
| Entity đầy đủ và DTO/projection | Chi phí dữ liệu cùng materialization | Native query luôn nhanh hơn derived query |
| Repository mock và implementation Java thuần | Chi phí gọi trong bộ nhớ của fixture | Chi phí truy vấn production |
| Driver trực tiếp và repository | Chênh lệch tổng của hai đường truy cập đã chọn | Đây là phép đo riêng Spring Data Commons |

Một phép so sánh hợp lý cần giữ tương đương query, tham số, dữ liệu trả về, transaction và mức bảo đảm. Nếu đường driver bỏ qua chuyển đổi, auditing hoặc kiểm tra version, cần tách những khác biệt đó trước khi diễn giải kết quả.

Microbenchmark có thể giúp đo dispatch hoặc allocation trong bộ nhớ khi được thiết kế với công cụ phù hợp như JMH. Nó không thay thế integration benchmark cho mạng và store. Trong microbenchmark, JIT, dead-code elimination và fixture không đại diện có thể làm kết quả gây hiểu nhầm nếu chỉ dùng vòng lặp cùng đồng hồ thủ công.

Không nên trừ hai số p95 của hai workload rồi gọi phần chênh lệch là “overhead proxy”. Nhiễu, cache, query plan và hàng đợi có thể thay đổi giữa hai lần chạy. Cần nhiều mẫu, điều kiện so sánh rõ và profile hỗ trợ kết luận.

## 11. Dùng tỷ trọng chi phí để chọn việc ưu tiên

Giả sử trong một mô hình đơn giản, các giai đoạn chạy tuần tự và abstraction chỉ chiếm một tỷ lệ `f` của tổng thời gian. Nếu tăng tốc phần đó `s` lần, tốc độ tổng thể được ước lượng:

```text
Speedup = 1 / ((1 - f) + f / s)
```

Nếu abstraction chiếm 5%, kể cả giả định loại bỏ hoàn toàn phần đó, mức tăng tốc tối đa của mô hình chỉ khoảng `1 / 0,95`, tức khoảng 1,053 lần. Đây là ví dụ toán học, không phải tỷ lệ đo sẵn của Spring Data.

Ngược lại, nếu mapping và allocation chiếm phần lớn CPU khi trả tập dữ liệu lớn, tối ưu projection hoặc giảm số đối tượng có thể tạo khác biệt rõ. Không có tỷ trọng cố định dùng cho mọi ứng dụng.

Ở hệ thống có hàng đợi hoặc mức sử dụng tài nguyên gần giới hạn, quan hệ không còn đơn giản tuyến tính. Giảm một phần CPU hoặc thời gian giữ connection có thể giảm chờ cho nhiều request. Vì vậy, cần kiểm chứng lại dưới workload thực tế sau thay đổi.

## 12. Phân tích một API danh sách khóa học

### Hiện trạng

API chỉ hiển thị ID, tiêu đề và thời gian tạo, nhưng đang:

1. Lấy `Page<Course>` với entity đầy đủ.
2. Đếm tổng dù giao diện chỉ có nút “Tải thêm”.
3. Để quá trình serialize truy cập thêm dữ liệu liên quan.
4. Lọc tenant, status rồi sort trên tập lớn mà chưa xác nhận index phù hợp.

Báo cáo “một lần gọi repository chậm” chưa chỉ ra được phần nào trong bốn điểm trên chiếm thời gian.

### Cách phân tích

- Đếm thao tác store của một request, tách content query, count query và truy vấn bổ sung.
- Xem query plan, số dữ liệu đọc và thời gian sort của content query.
- Đo byte trả về, allocation và thời gian serialize.
- Theo dõi pool wait khi tăng mức đồng thời.
- Xác nhận hợp đồng giao diện có thực sự cần tổng số phần tử không.

### Các thay đổi có thể xem xét theo bằng chứng

Nếu không cần tổng, chọn `Slice` phù hợp. Nếu chỉ cần ba field, dùng projection/query tương ứng. Nếu serialization gây truy vấn phụ ngoài ý định, chuyển dữ liệu cần thiết thành response rõ ràng trong phạm vi thích hợp. Nếu query plan cho thấy scan/sort tốn kém, đánh giá index hoặc hình dạng query.

Sau từng thay đổi, giữ kiểm tra kết quả, cách ly tenant, thứ tự và giới hạn. Nếu nhiều thay đổi được áp dụng cùng lúc, kết quả cuối có thể tốt nhưng khó quy tác động cho riêng từng nguyên nhân.

Nếu sau các bước đó phần lớn CPU vẫn nằm ở mapping/conversion, mới có bằng chứng để tối ưu phía ứng dụng sâu hơn. Không cần bỏ repository chỉ vì API ban đầu trả quá nhiều dữ liệu.

## 13. Những kết luận dễ sai

| Kết luận | Vấn đề trong suy luận |
| --- | --- |
| “Tên method dài nên query chậm” | Độ dài tên không mô tả số bản ghi đọc hoặc round trip |
| “Một method tương ứng một query” | Count, lazy loading, callback và flush có thể tạo thêm thao tác |
| “Trả ít phần tử nên store xử lý ít dữ liệu” | Filter/sort có thể đọc nhiều hơn số trả về |
| “Có index thì count và offset sâu đều rẻ” | Vẫn cần xem số entry xử lý và query plan |
| “Projection luôn chỉ đọc đúng các field khai báo” | Tối ưu phụ thuộc dạng projection và module |
| “Reactive làm database nhanh hơn” | Mô hình chờ thay đổi, công việc store vẫn phải thực hiện |
| “`saveAll` chắc chắn là một bulk write” | Hợp đồng CRUD không bảo đảm cùng một chiến lược cho mọi module |
| “Native nhanh hơn nên proxy gây toàn bộ chênh lệch” | Query, mapping hoặc transaction có thể đã thay đổi |
| “Đo quanh `save` là đã đo commit” | Một số đường ghi trì hoãn công việc tới flush/commit |

## 14. Bài tập vận dụng

Một API mất nhiều thời gian dù chỉ trả 30 khách hàng. Nhóm phát triển đề xuất thay toàn bộ derived queries bằng truy vấn driver trực tiếp. Quan sát ban đầu cho thấy method trả `Page`, response truy cập quan hệ liên quan và một phần request chờ connection pool.

Hãy xây dựng kế hoạch phân tích:

1. Phân loại chi phí có thể thuộc abstraction, mapping, hàng đợi và store.
2. Xác định các mốc timer và thao tác cần quan sát để không bỏ sót lazy loading hoặc count.
3. Đặt điều kiện so sánh công bằng giữa repository và đường driver.
4. Đề xuất một thay đổi nhỏ có thể kiểm chứng dựa trên nhu cầu response thực tế.
5. Nêu các bảo đảm phải giữ, gồm tenant, thứ tự, tổng số phần tử nếu cần và transaction.

Một lời giải tốt phải chỉ ra bằng chứng nào có thể bác bỏ giả thuyết “proxy là nguyên nhân chính”, đồng thời vẫn cho phép kết luận chi phí phía ứng dụng đáng tối ưu nếu profile thực sự cho thấy như vậy.

## 15. Điểm cần nhớ

Chi phí abstraction là một phần của đường truy cập dữ liệu, không đồng nhất với tổng thời gian một repository method. Số thao tác, hình dạng query, dữ liệu đọc/trả về, mapping và chờ tài nguyên thường cần được quan sát riêng.

Tối ưu hiệu quả bắt đầu từ một workload có hợp đồng rõ, đo đúng phần công việc đã hoàn tất và chọn thay đổi theo tỷ trọng chi phí thực tế. Các API chung của Spring Data giúp tổ chức truy cập; bảo đảm và hiệu năng cuối cùng vẫn phụ thuộc module cùng datastore đang sử dụng.
