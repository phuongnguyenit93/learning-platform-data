# Phân biệt cache của ứng dụng với bộ đệm bên trong hệ quản trị

Trong chương **Nhất quán và cache** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, hai cơ chế thường bị gọi chung là “cache” thực chất nằm ở **hai ranh giới khác nhau**: **cache do ứng dụng quản lý** (*application cache*) và **bộ đệm trang dữ liệu do hệ quản trị cơ sở dữ liệu quản lý** (*database buffer pool/page cache*). Cả hai giúp giảm chi phí truy xuất dữ liệu, nhưng khác nhau về nơi lưu, đơn vị dữ liệu, cách làm mới, quan hệ với transaction và rủi ro nhất quán.

Điểm mấu chốt: **cache ứng dụng có thể trả về một giá trị cũ mà không hề truy vấn database**, còn **database buffer pool thường chỉ quyết định trang dữ liệu được lấy từ RAM của database hay phải đọc từ tầng lưu trữ**. Một trang có sẵn trong bộ đệm **không có nghĩa** database bỏ qua MVCC, khóa, quy tắc cô lập hoặc xử lý transaction.

Bài này giúp lập trình viên Java chọn đúng lớp tối ưu, xác định nguồn dữ liệu có thẩm quyền (*source of truth*), thiết kế vô hiệu hóa cache và tránh nhầm độ trễ thấp với bảo đảm nhất quán hay độ bền dữ liệu.

## 1. Hai loại cache giải quyết hai bài toán khác nhau

**Cache của ứng dụng** lưu kết quả có ý nghĩa đối với ứng dụng: một đối tượng `ProductView`, danh sách sản phẩm, cấu hình, kết quả tính toán, token hoặc số liệu tổng hợp. Nó có thể đặt trong RAM của JVM (ví dụ Caffeine), trong một hệ thống dùng chung qua mạng (ví dụ Redis), hoặc ở các lớp trung gian khác. Khi gặp *cache hit*, ứng dụng **có thể không gửi SQL** cho lượt đọc đó.

**Database buffer pool** lưu các trang (*page/block*) dữ liệu hoặc chỉ mục mà database cần để thực thi SQL. Ví dụ PostgreSQL có `shared_buffers`; InnoDB của MySQL có `buffer pool`. Khi có *buffer hit*, database **vẫn đang thực hiện truy vấn** và sử dụng cơ chế transaction, nhưng không cần lấy trang đó từ tầng lưu trữ chậm hơn.

| Tiêu chí | Cache ứng dụng | Bộ đệm bên trong DBMS |
| --- | --- | --- |
| **Ai quản lý?** | Mã ứng dụng, thư viện cache hoặc dịch vụ cache ngoài. | Database engine và cơ chế lưu trữ liên quan. |
| **Đơn vị dữ liệu** | Key-value, DTO, kết quả truy vấn, object, aggregate. | Trang dữ liệu, trang chỉ mục và cấu trúc nội bộ. |
| **Cache hit có gửi SQL?** | Thường **không**, nếu kết quả được trả trực tiếp từ cache. | **Có**: SQL vẫn được thực thi trong DBMS. |
| **Làm mới** | TTL, eviction, invalidation, cập nhật key, event, hoặc logic ứng dụng. | Engine tự nạp, thay thế, đánh dấu dirty và ghi trang theo thuật toán của nó. |
| **Nhất quán** | Do thiết kế ứng dụng quyết định; có thể trả dữ liệu cũ. | Chịu sự quản lý của cơ chế transaction/MVCC/khóa của DBMS. |
| **Nguồn dữ liệu có thẩm quyền?** | Thường không; cần xác định riêng nếu kiến trúc khác thường. | Cache trang không phải nguồn độc lập; dữ liệu bền vững và log thuộc DBMS. |
| **Khi mất cache** | Cache miss, cần đọc lại/tính lại; có thể tăng tải DB. | DB đọc lại trang từ hệ lưu trữ, theo cơ chế recovery nếu cần. |
| **Tối ưu chính** | Giảm request xuống DB, round-trip mạng, CPU truy vấn và xây dựng DTO. | Giảm truy xuất I/O lưu trữ trong lúc DB xử lý SQL. |
| **Chi phí** | RAM thêm, đồng bộ giữa instance, nguy cơ stale, logic vô hiệu hóa. | RAM máy DB, eviction/dirty page, checkpoint và cạnh tranh bộ nhớ. |

Hai lớp cache **không thay thế cho nhau**. Ứng dụng có thể bỏ qua SQL nhờ Redis; khi Redis miss, SQL đi vào DB và DB có thể đọc phần lớn trang dữ liệu từ `shared_buffers`. Một request có thể lần lượt chạm nhiều tầng cache trong cùng đường đi.

## 2. Theo dõi một lượt đọc từ Java đến ổ lưu trữ

Giả sử API lấy thông tin công khai của sản phẩm `BOOK-1`:

```text
HTTP GET /products/BOOK-1
       |
       v
Java ProductService
       |
       +-- Tra application cache theo key product:BOOK-1
       |       |
       |       +-- HIT ----> Trả DTO, không gửi SQL
       |       |
       |       +-- MISS
       |             |
       |             v
       |        JDBC / JPA / SQL
       |             |
       |             v
       |        Database engine
       |             |
       |             +-- Trang ở DB buffer: lấy từ RAM DB
       |             |
       |             +-- Trang không ở buffer:
       |                     đọc qua OS/filesystem/storage
       |             |
       |             v
       |        Thực thi query, ánh xạ DTO
       |             |
       |             +-- Có thể lưu DTO vào app cache
       |             |
       v             v
            Trả HTTP response
```

Trường hợp 1: cache ứng dụng hit, database không nhận lượt đọc đó. Chỉ số DB query count có thể giảm.

Trường hợp 2: cache ứng dụng miss, database vẫn thực thi câu SQL. Nếu DB buffer hit, query tránh một số lượt đọc từ storage nhưng vẫn phải kiểm tra điều kiện truy vấn, quyền, snapshot MVCC, join/sort và đôi khi chờ khóa.

Trường hợp 3: cả hai lớp miss, hệ quản trị phải nạp thêm trang dữ liệu hoặc chỉ mục. **Ngay cả lúc này, I/O từ database tới filesystem có thể được phục vụ từ OS page cache**, không nhất thiết biến thành truy cập vật lý tới SSD/HDD.

Do đó, cần phân biệt **application cache hit ratio**, **database buffer hit ratio**, **OS cache hit** và **physical disk read**. Không có một chỉ số “cache hit 99%” chung đại diện cho tất cả.

## 3. Bên trong database: trang sạch, trang bẩn và vòng đời ghi

Database có thể lưu trang dữ liệu/chỉ mục trong bộ nhớ để sử dụng lại. Về khái niệm, trang trong buffer có thể là:

- **Trang sạch (clean page):** bản trong bộ nhớ không có thay đổi cần ghi thêm xuống vị trí lưu trữ chính theo trạng thái engine đang quản lý.
- **Trang bẩn (dirty page):** nội dung trong bộ nhớ đã được sửa và cần được ghi lại về khu vực lưu trữ phù hợp.
- **Trang đang được sử dụng:** một query đang đọc hoặc cập nhật, nên engine phải phối hợp việc thay thế/khóa trang và trạng thái truy cập.

Một giao dịch ghi thường có đường đi khái quát:

```text
UPDATE inventory ...
       |
       v
DB đọc/tìm các trang (thường qua buffer pool)
       |
       v
Thay đổi trạng thái trang trong bộ nhớ
       |
       +--> Ghi WAL/redo log theo giao thức của DBMS
       |         |
       |         +--> Đồng bộ log tới mốc commit theo chính sách
       |                       |
       |                       +--> Trả COMMIT thành công
       |
       +--> Trang dirty có thể được ghi xuống file dữ liệu SAU ĐÓ
                 (checkpoint/background writer/flush)
```

Điều quan trọng là **durability không đòi database phải ghi đồng bộ mọi trang dữ liệu bẩn trước khi xác nhận từng transaction**. Với engine dùng write-ahead logging (WAL/redo), log phục hồi được ghi theo quy tắc cần thiết; các trang dirty có thể được đẩy ra sau, rồi được phục hồi từ log nếu xảy ra crash. Cơ chế chi tiết tùy DBMS và cấu hình.

Điều này khác xa cache ứng dụng: một đối tượng `ProductView` trong Redis không tự trở thành một phần của cơ chế WAL và recovery của PostgreSQL. Cache ứng dụng có thể mất sạch sau restart mà không nhất thiết làm mất dữ liệu nghiệp vụ đã commit ở database.

**Cảnh báo về độ bền:** không suy diễn “trang đang trong RAM của database” là “dữ liệu đã an toàn”. Và cũng không suy diễn “transaction commit rồi nhưng data page chưa flush” là “transaction chắc chắn sẽ mất”. Cần xem bảo đảm của WAL, sync, filesystem, storage và replication theo cấu hình triển khai.

## 4. DB buffer không phải cache kết quả truy vấn

Một nhầm lẫn phổ biến là: “Nếu PostgreSQL có `shared_buffers` thì lần chạy lại cùng câu `SELECT` sẽ lấy lại kết quả SQL từ RAM mà không tính toán”.

Thông thường **không phải như vậy**. PostgreSQL buffer cache giữ **block dữ liệu/chỉ mục**, không mặc định lưu toàn bộ bảng kết quả của một `SELECT` để bỏ qua thực thi SQL ở lần gọi sau. SQL vẫn phải đi qua những bước cần thiết để tạo kết quả đúng với snapshot và tham số của lần truy vấn hiện tại.

Ví dụ:

```sql
SELECT id, price, updated_at
FROM products
WHERE category_id = 15
  AND status = 'ACTIVE'
ORDER BY updated_at DESC
LIMIT 20;
```

Khi các trang index/table liên quan đã nằm trong buffer, truy vấn có thể nhanh hơn. Nhưng database vẫn cần xác định 20 hàng đáp ứng điều kiện ở thời điểm đọc, sử dụng execution plan, kiểm tra MVCC và sắp xếp hoặc tận dụng index theo kế hoạch phù hợp.

Trong khi đó, cache ứng dụng có thể lưu thẳng **20 dòng kết quả** theo key như `products:category:15:active:sort:updated_desc:page:1:v2`. Một lần hit có thể bỏ qua SQL hoàn toàn nhưng có nguy cơ danh sách bị cũ khi sản phẩm đổi trạng thái hoặc giá.

**Query cache của thư viện ORM** hoặc một lớp cache kết quả riêng lại là cơ chế khác. Không nên lấy đặc tính của “query cache ở ứng dụng” để suy ra behavior của “buffer pool trong database”.

## 5. Các tầng cache trong hệ sinh thái Java và database

Trong một ứng dụng dùng Java/JPA, có thể tồn tại nhiều bộ nhớ trung gian khác nhau:

| Tầng | Ví dụ | Phạm vi điển hình | Nguồn gây cũ dữ liệu |
| --- | --- | --- | --- |
| Cache trong một JVM | Caffeine, map có TTL | Một tiến trình/application instance. | Instance khác ghi DB; không nhận invalidation; TTL chưa hết. |
| Cache phân tán | Redis hoặc dịch vụ cache dùng chung | Nhiều instance truy cập chung cache. | Ghi DB nhưng key chưa xóa/đổi; event chậm/mất. |
| JPA first-level cache | Persistence context của `EntityManager` | Một persistence context/transaction tùy cách quản lý. | Entity đang managed có thể chưa phản ánh cập nhật ngoài context. |
| JPA second-level cache | Cache entity/collection cấu hình trên ORM provider | Có thể chia sẻ giữa nhiều session, phạm vi phụ thuộc provider. | Ghi trực tiếp SQL hoặc các đường không cập nhật cache; cấu hình concurrency strategy. |
| ORM query cache | Kết quả truy vấn được cache khi kích hoạt/tương thích. | Provider/cache region cụ thể. | Khó xác định mọi tập kết quả bị ảnh hưởng khi dữ liệu thay đổi. |
| DB buffer pool | PostgreSQL `shared_buffers`, InnoDB buffer pool | Một database instance/engine. | Không phải kiểu stale do quên invalidation ứng dụng; chịu giao thức đồng thời của engine. |
| OS page cache | Cache tệp của kernel | Hệ điều hành/máy lưu trữ. | Cơ chế nhất quán và flush của OS/filesystem, không phải TTL DTO. |
| Cache ổ hoặc controller | Cache thiết bị/bộ điều khiển | Phần cứng/storage backend. | Liên quan bảo đảm flush/mất điện, không phải quy tắc API. |

Một số lớp thực chất là **cache vật lý**, một số là **identity map/quản lý trạng thái entity**. Chúng khác nhau về API, vòng đời và cam kết. Không nên dùng “cache” như một nhãn để gộp mọi hoạt động bộ nhớ.

### JPA first-level cache có điểm gì đặc biệt?

Trong một persistence context, JPA thường giữ cùng một managed entity cho một định danh, phục vụ identity và dirty checking. Ví dụ:

```java
ProductEntity first = entityManager.find(ProductEntity.class, 42L);
ProductEntity second = entityManager.find(ProductEntity.class, 42L);

// Trong cùng persistence context, thường first == second.
// Không có nghĩa entity đó luôn tự nhìn thấy thay đổi vừa commit
// từ một transaction khác.
```

JPA cung cấp các thao tác như `refresh()`, `clear()` và chế độ lock để quản lý trạng thái theo nhu cầu. Nhưng việc refresh không tự thay đổi mức cô lập giao dịch: một transaction với snapshot cố định có thể vẫn chịu quy tắc thấy dữ liệu của snapshot đó.

Nếu native SQL hoặc batch job sửa DB mà persistence context còn giữ entity cũ, việc đọc lại trong cùng context có thể không phản ánh thay đổi như người viết service mong đợi. Đây là vấn đề **tầng ORM**, không phải “PostgreSQL buffer pool trả sai trang”.

## 6. Nhất quán của DBMS và độ mới của cache ứng dụng là hai trục khác nhau

Trong database, tính nhất quán khi đọc phụ thuộc isolation level, snapshot/MVCC, khóa và trạng thái transaction. Cache ứng dụng lại quyết định **có hỏi database để lấy snapshot mới hay không**.

Giả sử giá của sản phẩm ban đầu là 100.000 đồng:

```text
T0: Database price = 100.000
T1: Request A đọc DB và cache product:42 = 100.000, TTL 60s
T2: Transaction B UPDATE price = 120.000; COMMIT
T3: Request C đọc application cache → 100.000 (stale)
T4: Cache hết hạn; lần đọc tiếp theo lấy DB → 120.000
```

Transaction B commit đúng, DB buffer hoàn toàn có thể chứa trang mới, nhưng request C **không gửi truy vấn xuống DB** nên vẫn nhận giá cũ. Thay đổi `shared_buffers` lớn hơn **không sửa được** vấn đề này.

Ngược lại, nếu request C truy vấn DB trong một transaction `REPEATABLE READ` đã được thiết lập từ trước, DB có thể trả dữ liệu theo snapshot cũ **một cách đúng với isolation level**. Đây không phải lỗi cache ứng dụng. Muốn hiểu kết quả đọc, phải hỏi:

1. Lần đọc được phục vụ từ **cache nào**?
2. Có gửi SQL không?
3. SQL chạy trên primary hay replica?
4. Transaction đang ở mức cô lập nào và snapshot có từ khi nào?
5. Yêu cầu nghiệp vụ đòi độ mới tới mức nào?

**Application stale cache**, **replica lag** và **transaction snapshot cũ** là ba nguyên nhân khác nhau có thể tạo dữ liệu “cũ” giống nhau trên giao diện, nhưng cách khắc phục không giống nhau.

## 7. Khi nào nên thêm cache ứng dụng?

Không nên thêm Redis hoặc cache JVM chỉ vì database có độ trễ đôi lúc cao. Một câu SQL tối ưu, chỉ mục phù hợp và DB buffer được sử dụng hiệu quả có thể đã đủ.

Cache ứng dụng hữu ích nếu:

- Nhiều request đọc **cùng một tập kết quả** và ít thay đổi.
- Chi phí truy vấn, join, tổng hợp, serialization hoặc round-trip lớn hơn chi phí quản lý cache.
- Yêu cầu có thể chấp nhận một độ trễ cập nhật xác định.
- Hệ thống có đủ RAM và ngân sách vận hành cho cache.
- Có khả năng mô tả key, TTL, vô hiệu hóa, phân quyền và xử lý cache miss rõ ràng.

Những dữ liệu thường hợp cache:

| Dữ liệu | Khả năng cache | Điều kiện |
| --- | --- | --- |
| Danh mục, metadata công khai ít đổi | Thường tốt. | TTL hoặc invalidation khi đổi cấu hình. |
| Thông tin sản phẩm phục vụ trang danh sách | Có thể tốt. | Xác định mức stale cho phép; kiểm soát giá/khuyến mại. |
| Báo cáo tổng hợp tốn CPU nhưng không cần real-time | Thường tốt. | Có dấu thời điểm dữ liệu và chính sách làm mới. |
| Tồn kho/giới hạn để **quyết định chấp nhận đơn** | Không nên lấy cache làm thẩm quyền cuối. | Dùng DB transaction/conditional update để quyết định. |
| Số dư tiền hoặc quyền truy cập có tác dụng an toàn | Cần rất thận trọng. | Đảm bảo đọc nguồn có thẩm quyền khi ra quyết định nhạy cảm. |
| Token/quyền người dùng | Có thể cần cache đặc biệt. | TTL ngắn, thu hồi quyền, isolation tenant và an toàn thông tin. |

Đánh giá cache bằng **đúng đắn nghiệp vụ và chi phí tổng**: giảm vài ms không đáng nếu gây đặt hàng quá số lượng hoặc hiển thị quyền truy cập sai sau khi thu hồi.

## 8. Các chiến lược cache ứng dụng phổ biến

### 8.1. Cache-aside (lazy loading)

Ứng dụng đọc cache trước; nếu miss, đọc DB rồi điền cache. Với cập nhật, thường ghi vào DB và **vô hiệu hóa** cache sau khi commit:

```text
READ:
  cache.get(key)
      | hit  -> return cached DTO
      | miss -> SELECT from DB
                cache.put(key, DTO, TTL)
                return DTO

WRITE:
  BEGIN
  UPDATE DB ...
  COMMIT
  cache.evict(affected keys)    (best effort)
```

Ưu điểm: chỉ cache dữ liệu thật sự được đọc, dễ áp dụng. Nhược điểm: phải xác định key bị ảnh hưởng và xử lý tình huống cache còn cũ, event invalidation thất lạc hoặc request đọc đồng thời với write.

### 8.2. Write-through

Ứng dụng đi qua một thành phần chịu trách nhiệm ghi cả nguồn dữ liệu và cache theo một giao thức được định nghĩa. Mục tiêu là cache được cập nhật cùng đường ghi, nhưng **không có transaction phân tán tự động** giữa Redis và PostgreSQL. Nếu cập nhật DB thành công nhưng cập nhật cache thất bại, cần cơ chế phục hồi.

Đừng khẳng định “write-through luôn nhất quán mạnh” chỉ từ tên chiến lược. Mức nhất quán phụ thuộc thứ tự thao tác, retry và khả năng phối hợp atomicity.

### 8.3. Write-behind / write-back

Ứng dụng ghi vào cache hoặc hàng đợi trước; việc ghi DB diễn ra bất đồng bộ sau đó. Có thể giảm độ trễ ghi nhưng làm thay đổi **nguồn có thẩm quyền tạm thời**, độ bền và khả năng mất dữ liệu khi cache/worker lỗi.

Với đơn hàng, thanh toán, giới hạn tồn kho hoặc nghiệp vụ cần cam kết ghi bền ngay, **không dùng write-behind chỉ để nhanh hơn** nếu không có một log/queue bền vững, giao thức khôi phục và mô hình chấp nhận mất dữ liệu rõ ràng.

### 8.4. Read-through và refresh-ahead

Read-through giao trách nhiệm nạp dữ liệu khi miss cho lớp cache/provider; refresh-ahead cố làm mới trước khi TTL hết. Chúng có thể giảm boilerplate hoặc giảm miss, nhưng không tự giải quyết race giữa read và write, eviction event thất lạc hay tranh chấp phiên bản.

| Chiến lược | Điểm thuận lợi | Rủi ro chính |
| --- | --- | --- |
| Cache-aside | Minh bạch, linh hoạt, phổ biến. | Stale key, invalidation, cold miss và race điền cache. |
| Write-through | Cập nhật cache cùng luồng ghi theo giao thức. | Lỗi từng bước, thiếu atomicity DB + cache. |
| Write-behind | Có thể giảm độ trễ ghi. | Mất dữ liệu trước khi DB ghi; thứ tự và retry khó. |
| Read-through | Gọn thao tác đọc của application. | Provider ẩn logic nạp; vẫn cần chính sách consistency. |
| Refresh-ahead | Giảm cache miss trước khi key hết hạn. | Giá trị refresh có thể lỗi thời hoặc gây tải nền. |

## 9. Ví dụ Java: cache-aside cho ProductView

Để tránh lẫn logic cache với quyền quyết định nghiệp vụ, coi repository là nguồn đọc authoritative, còn cache chỉ là tối ưu cho dữ liệu hiển thị.

```java
import java.math.BigDecimal;
import java.util.Optional;
import java.time.Duration;

public record ProductView(
        String sku,
        String name,
        BigDecimal displayPrice,
        long version
) {
}

public interface ProductReadRepository {
    Optional<ProductView> findForDisplay(String sku);
}

public interface ProductCache {
    Optional<ProductView> get(String key);
    void put(String key, ProductView view, Duration ttl);
    void evict(String key);
}

public final class ProductReadService {
    private static final Duration TTL = Duration.ofSeconds(30);
    private final ProductReadRepository repository;
    private final ProductCache cache;

    public ProductReadService(
            ProductReadRepository repository, ProductCache cache) {
        this.repository = repository;
        this.cache = cache;
    }

    public Optional<ProductView> findForDisplay(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("Invalid SKU");
        }

        String key = "product:view:v1:" + sku;
        Optional<ProductView> cached = cache.get(key);
        if (cached.isPresent()) {
            return cached;
        }

        Optional<ProductView> loaded = repository.findForDisplay(sku);
        loaded.ifPresent(view -> cache.put(key, view, TTL));
        return loaded;
    }
}
```

Mã này là **minh họa giao diện**, không yêu cầu sử dụng Caffeine hay Redis cụ thể. Một implementation thật phải chọn:

- **TTL** và cách đặt tên key có version của **schema cache** (`v1` ở đây), không nhầm với `version` nghiệp vụ của sản phẩm.
- Có cache kết quả “không tồn tại” (*negative caching*) hay không và trong bao lâu.
- Lỗi cache có làm fail request hay được bỏ qua để fallback DB.
- Có cho phép một nghìn request cùng miss đổ xuống DB hay cần cơ chế single-flight/load coalescing.
- Cách serializer/schema evolution, key namespace theo tenant và cache eviction.
- Giới hạn dung lượng cache để tránh hết heap JVM hoặc chi phí Redis tăng không kiểm soát.

Ví dụ **không cam kết đọc tuyến tính/linearizable**. TTL 30 giây nghĩa là dữ liệu có thể cũ **ít nhất trong một số tình huống tới gần khoảng này**, và có thể lâu hơn nếu logic refresh, đồng hồ hoặc đường lỗi kéo dài thời gian sống của giá trị sai. TTL không phải một giao thức nhất quán mạnh.

## 10. Khi cập nhật dữ liệu: vì sao phải gắn invalidation với commit?

Giả sử admin đổi giá sản phẩm. Cách sắp xếp thao tác quan trọng:

```text
Sai:
  1. cache.evict(productKey)
  2. DB UPDATE price ...
  3. Transaction rollback
  → cache bị xóa không cần thiết; request khác có thể nạp lại giá cũ.

Phổ biến hơn:
  1. BEGIN
  2. UPDATE price ...
  3. COMMIT
  4. cache.evict(productKey)
  → Không vô hiệu hóa trước khi DB xác nhận commit.
```

Trong Spring, có thể gắn hành động **sau khi commit** để tránh evict trước khi giao dịch hoàn tất:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class ProductWriteService {
    private final ProductWriteRepository writer;
    private final ProductCache cache;

    public ProductWriteService(ProductWriteRepository writer,
                               ProductCache cache) {
        this.writer = writer;
        this.cache = cache;
    }

    @Transactional
    public void changeDisplayPrice(String sku, java.math.BigDecimal price) {
        if (price == null || price.signum() < 0) {
            throw new IllegalArgumentException("Invalid price");
        }
        writer.updateDisplayPrice(sku, price); // Chạy trong transaction này.

        TransactionSynchronizationManager.registerSynchronization(
            new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    cache.evict("product:view:v1:" + sku);
                }
            }
        );
    }
}
```

`ProductWriteRepository` là port minh họa. Đoạn code giả định **transaction được Spring quản lý và synchronization đang hoạt động**; cần đảm bảo invocation đi qua transaction proxy/manager phù hợp. Phải kiểm tra việc `UPDATE` có thật sự tác động hàng mong muốn, ràng buộc quyền và version theo yêu cầu của use case.

**Giới hạn rất quan trọng:** `afterCommit()` chỉ là callback trong tiến trình. Nếu database commit thành công nhưng JVM sập trước khi callback chạy, cache vẫn có thể còn giá cũ. Nếu callback ném lỗi, database cũng **không thể rollback một commit đã hoàn tất**. Vì vậy mẫu này thích hợp khi chấp nhận stale có giới hạn và cache TTL/fallback; nó **không bảo đảm đồng bộ nguyên tử** giữa DB và cache.

Nếu invalidation bắt buộc có đường phục hồi sau crash, có thể ghi một **outbox event** trong cùng DB transaction, rồi để worker gửi invalidation và retry cho đến khi xử lý. Consumer phải idempotent và có cơ chế nhận diện event trùng. Outbox giảm nguy cơ mất sự kiện, nhưng **không loại bỏ độ trễ giữa commit và cache được làm mới**, và vẫn cần xử lý thứ tự sự kiện.

## 11. Race condition: xóa cache sau commit vẫn có thể nạp lại dữ liệu cũ

Xem lịch sau của mẫu cache-aside:

```text
T1: Reader A cache MISS
T2: A SELECT DB → ProductView(price=100, version=7)
T3: Writer B UPDATE price=120, version=8; COMMIT
T4: B EVICT cache key product:42
T5: A PUT kết quả cũ (price=100, version=7) vào cache
T6: Reader C cache HIT → price=100 dù DB là 120
```

Việc “UPDATE rồi DEL Redis” **không đủ ngăn một read miss đang bay** đẩy giá trị cũ vào cache sau bước xóa. Nếu TTL dài, người dùng tiếp tục nhận giá cũ trong một khoảng đáng kể.

Các hướng xử lý tùy yêu cầu nhất quán:

1. **Chấp nhận stale có giới hạn:** TTL ngắn và chính sách làm mới rõ; dùng khi dữ liệu chỉ để hiển thị và không quyết định nghiệp vụ quan trọng.
2. **Bypass cache tại quyết định quan trọng:** đọc/ghi trực tiếp tại nguồn có thẩm quyền trong transaction hoặc dùng thao tác có điều kiện ở DB; không tin giá trị tồn kho cache để chấp nhận đơn hàng.
3. **Version-aware publication:** mỗi giá trị cache gắn với revision/sequence, chỉ chấp nhận ghi cache nếu không ghi đè revision mới hơn; điều kiện so phiên bản phải **nguyên tử tại cache** và mọi đường ghi phải tuân giao thức.
4. **Versioned keys với revision đã xác thực:** key chứa version, nhưng cần biết **phiên bản hiện hành từ nguồn đủ mới** hoặc một cơ chế publish revision đáng tin; key có version tự nó chưa loại bỏ stale nếu client vẫn đọc pointer phiên bản cũ.
5. **Đồng bộ theo event/outbox và xử lý thứ tự:** yêu cầu event có ID/revision, consumer không áp dụng một invalidation hoặc giá trị cũ lên revision mới hơn; có retry và quan sát backlog.
6. **Đặt một giao thức khóa/điều phối chung** nếu cần điều kiện nhất quán nghiêm ngặt; đánh giá chi phí và failure mode. Với bài toán nhiều trường hợp, bỏ cache trên đường ghi quan trọng có thể đơn giản và an toàn hơn.

**Không có một lệnh `DEL key` sau `COMMIT` nào tự cung cấp strong consistency cho hai hệ lưu trữ độc lập.** Thiết kế cần ghi rõ chấp nhận stale tới đâu, trong lỗi nào, và làm sao phát hiện trạng thái bị cũ.

## 12. TTL, eviction và bất biến nghiệp vụ

**TTL (time to live)** là giới hạn thời gian sống của entry theo hợp đồng cache. Nó giúp cache tự phục hồi sau trường hợp không nhận được invalidation, nhưng cần hiểu các giới hạn:

- **TTL không phải một loại transaction isolation.** Hai client có thể thấy hai giá trị khác nhau trong cùng một thời điểm.
- **Eviction không đồng nghĩa invalidation.** Eviction có thể do hết RAM hoặc thuật toán LRU/LFU; invalidation là yêu cầu có chủ đích khi dữ liệu thay đổi.
- **Không nên dựa vào TTL để cưỡng chế bất biến:** nếu chỉ còn 1 sản phẩm, cache nói còn 5 vì chưa hết hạn thì câu SQL giữ hàng vẫn phải kiểm tra `available >= quantity` ngay khi ghi.
- **TTL ngắn tăng miss và tải DB**, TTL dài tăng cửa sổ stale. Cần đo cả chi phí và mức stale mà sản phẩm cho phép.
- **Không tồn tại (negative cache)** cũng có thể cũ: sản phẩm mới thêm nhưng key “không có sản phẩm” vẫn tồn tại tới hết TTL.
- **Khóa dữ liệu nhiều key liên quan** khó hơn một key: ví dụ thay giá phải làm mới cả view chi tiết và nhiều danh sách theo category. Nếu quên một key, các màn hình hiển thị không thống nhất.

Với dữ liệu đòi thời điểm nhìn thấy rõ như tỷ giá áp dụng để thanh toán, thường cần lưu **snapshot giá/quy tắc đã áp dụng vào giao dịch**, không chỉ đọc cache có thể thay đổi giữa lúc xem trang và lúc thanh toán.

## 13. Cache JVM, Redis và quy mô nhiều instance

Một cache trong JVM nhanh vì không có round-trip mạng tới cache server. Nhưng mỗi instance có một bản độc lập:

```text
Pod A: product:42 = version 7
Pod B: product:42 = version 8
Pod C: product:42 = chưa cache
Database: product:42 = version 8
```

Người dùng đổi pod có thể nhận kết quả khác nhau. Một event invalidation phải tới **mọi instance liên quan**, hoặc mỗi instance phải dựa trên TTL đủ ngắn/chính sách nhất quán phù hợp. Autoscaling và rolling deployment có thể làm trạng thái cache của các pod khác biệt.

Redis hoặc một hệ thống cache dùng chung giúp nhiều instance đọc cùng key, nhưng bổ sung **mạng, kết nối, độ trễ, bộ nhớ server và một điểm lỗi vận hành mới**. Khi Redis không sẵn sàng, ứng dụng cần xác định: trả dữ liệu lỗi, dùng cache local dự phòng với nguy cơ cũ, hay fallback DB có giới hạn concurrency?

| Tình huống | Cache JVM | Cache phân tán |
| --- | --- | --- |
| Độ trễ lấy key | Thường rất thấp trong một process. | Có round-trip mạng hoặc IPC. |
| Nhiều pod | Mỗi pod có bản riêng. | Có thể dùng chung trạng thái cache. |
| Invalidation | Cần fan-out/event cho từng pod hoặc TTL. | Có thể evict một key tập trung, vẫn có race/failure. |
| Restart một pod | Mất cache của pod đó, tạo cold start. | Cache dùng chung có thể còn. |
| Mất cache service | Không ảnh hưởng những cache local còn sống. | Có thể gây miss/timeout đồng loạt trên nhiều pod. |
| Phân quyền và dữ liệu nhạy cảm | Rủi ro trong RAM process/log/snapshot. | Thêm quyền mạng, ACL, TLS và isolation key/tenant. |

Một số hệ thống dùng **hai tầng cache**: local L1 và Redis L2. Việc này tăng khả năng hit nhưng cũng tăng yêu cầu về invalidation, thứ tự và quan sát. Nếu dữ liệu yêu cầu nhất quán cao, nhiều tầng cache không tự đem lại bảo đảm tốt hơn.

## 14. Cache stampede và cold start: khi tối ưu làm database quá tải

Cache ứng dụng thường được thêm để giảm số query. Nhưng khi nhiều key hết hạn cùng lúc, lượng truy vấn có thể tăng đột biến:

```text
10.000 request cùng đọc một key HOT
               |
        TTL vừa hết hạn
               |
      10.000 lần cache MISS
               |
        10.000 SQL query?
               |
          DB bị quá tải
```

Đây là **cache stampede/thundering herd**. Các biện pháp:

- **Single-flight/load coalescing:** một request nạp key, các request khác chờ cùng kết quả. Khi nhiều pod, cơ chế trong JVM chỉ hợp nhất tải trong từng pod.
- **Jitter TTL:** phân tán thời điểm hết hạn để tránh nhiều key cùng miss.
- **Refresh-ahead:** chủ động làm mới dữ liệu hot trước expiry, kèm giới hạn và tránh tranh chấp phiên bản.
- **Stale-while-revalidate:** có thể trả dữ liệu cũ trong giới hạn cho phép trong khi nền cập nhật; **không dùng cho quyết định tài chính/tồn kho cần giá trị mới nhất**.
- **Admission control và pool limit:** không để miss đẩy số query vô hạn xuống DB.
- **Pre-warm dữ liệu thật sự cần thiết:** nạp một phần key trước khi mở traffic, tránh làm nóng toàn bộ dữ liệu không ai đọc.

Đặt cache làm phụ thuộc bắt buộc cho mọi request có thể khiến lỗi Redis thành lỗi toàn dịch vụ. Ngược lại, cho mọi request fallback DB không giới hạn có thể gây **cascading failure**. Cần timeout, circuit breaker/backpressure và giới hạn số truy vấn fallback.

## 15. Cấu hình bộ đệm của DBMS: khi nào nên điều chỉnh?

Cache của DBMS không phải một hash map mà ứng dụng trực tiếp đặt TTL. Engine quản lý buffer theo thuật toán và workload riêng. Cần hiểu các tham số trong phạm vi engine đang dùng.

### 15.1. PostgreSQL: `shared_buffers` và OS page cache

Trong PostgreSQL, `shared_buffers` là vùng shared memory chủ yếu dùng để cache block dữ liệu/chỉ mục được truy cập qua buffer manager. PostgreSQL cũng dựa trên OS/filesystem nên dữ liệu có thể nằm trong **OS page cache** bên ngoài vùng này.

Một số điểm:

- Tăng `shared_buffers` có thể cải thiện tỉ lệ hit đối với workload phù hợp, nhưng dùng thêm RAM và thay đổi áp lực checkpoint/ghi trang; không phải cứ càng lớn càng tốt.
- PostgreSQL và OS cùng cần RAM. Cấp gần như toàn bộ RAM cho `shared_buffers` có thể làm các thành phần khác thiếu bộ nhớ.
- `effective_cache_size` là **ước lượng để planner đánh giá lượng cache có thể tận dụng**, không phải lệnh cấp phát một buffer mới cùng kích thước.
- `work_mem` phục vụ những thao tác như sort/hash theo truy vấn/thao tác phù hợp; **không phải cùng một thứ với `shared_buffers`** và tăng nó thiếu kiểm soát có thể khiến nhiều query đồng thời tiêu tốn nhiều RAM.
- Tăng buffer không sửa được index thiếu, query chạy plan kém, lock contention hay dữ liệu stale ở Redis.

Có thể xem cấu hình:

```sql
SHOW shared_buffers;
SHOW effective_cache_size;
SHOW work_mem;
```

Chọn giá trị cuối dựa trên tài nguyên máy, mẫu truy vấn, số kết nối, đặc tính I/O và kết quả đo; tránh dùng một tỷ lệ RAM cố định như chân lý cho mọi hệ thống.

### 15.2. MySQL/InnoDB: buffer pool

InnoDB có **buffer pool** để cache trang dữ liệu và chỉ mục. Nó quản lý các trang trong bộ nhớ và thực hiện flush các trang bẩn theo cơ chế redo/checkpoint của engine. Khi đo, cần phân biệt logical read từ buffer với physical read; xem thêm chi phí redo log, flush, áp lực RAM và câu truy vấn có dùng index tốt hay không.

Các chỉ số/cấu hình thường được kiểm tra gồm:

```sql
SHOW VARIABLES LIKE 'innodb_buffer_pool_size';
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_read_requests';
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_reads';
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_pages_dirty';
```

Tên và cách xuất metric có thể khác theo phiên bản engine hoặc công cụ giám sát. Đừng suy ra một cache hit ratio cao đồng nghĩa mọi query nhanh: câu SQL có thể tiêu tốn CPU, tạo temp file, chờ khóa hoặc đọc lượng trang khổng lồ ngay cả khi phần lớn trang ở RAM.

## 16. Đo đúng: hit ratio nào đang tăng và hệ thống được lợi gì?

Để biết tối ưu ở tầng nào, nên nhìn đồng thời metric ứng dụng, cache service, database và storage.

| Chỉ số | Tầng | Câu hỏi |
| --- | --- | --- |
| Application cache hit/miss ratio | JVM/Redis/ORM cache | Bao nhiêu request được trả từ cache mà không cần hỏi DB? |
| Cache latency p50/p95/p99 | JVM/Redis | Cache có thực sự nhanh hơn đọc DB không? |
| Eviction/expiry/invalidation count | Cache | Key mất vì TTL, thiếu RAM hay sự kiện cập nhật? |
| Cache fill latency và concurrent miss | Cache + repository | Có stampede, stale fill hoặc refresh chậm không? |
| Số SQL/request và thời gian SQL | Ứng dụng + DB | Cache có giảm round-trip và tải truy vấn không? |
| DB buffer hit/read | DBMS | Bao nhiêu truy cập block được phục vụ từ buffer manager? |
| OS/storage read latency, IOPS, throughput | Hệ điều hành/thiết bị | Có thực sự giảm truy cập vật lý và thời gian đợi I/O? |
| CPU, lock waits, temp files, WAL/flush | DBMS | Nút nghẽn có nằm ngoài việc nạp trang không? |
| Connection pool active/pending/wait | Java | Nhu cầu DB có giảm hay chỉ chuyển hàng đợi sang tầng khác? |
| Staleness age, invalidation lag, lỗi consistency | End-to-end | Dữ liệu tới client có đáp ứng SLA độ mới không? |

### PostgreSQL: phân biệt block hit và read

Ví dụ truy vấn thống kê mức database:

```sql
SELECT
    datname,
    blks_hit,
    blks_read,
    ROUND(
        100.0 * blks_hit / NULLIF(blks_hit + blks_read, 0),
        2
    ) AS buffer_hit_pct
FROM pg_stat_database
WHERE datname = current_database();
```

Một góc nhìn theo bảng:

```sql
SELECT
    relname,
    heap_blks_hit,
    heap_blks_read,
    idx_blks_hit,
    idx_blks_read
FROM pg_statio_user_tables
ORDER BY heap_blks_read DESC
LIMIT 20;
```

Đây là **các bộ đếm tích lũy theo phạm vi thống kê**, không phải độ trễ của một truy vấn riêng. Cần đo theo **delta trong cùng khoảng thời gian**, lưu ý thời điểm reset và các thay đổi do restart. Chúng cũng **không đo application cache hit**.

Quan trọng: trong PostgreSQL, `blks_read` là số block được đọc vào buffer manager; một phần có thể được OS page cache phục vụ, **không thể đồng nhất `blks_read` với số I/O vật lý từ ổ đĩa**. Phải kết hợp metric OS/storage khi cần xác định thiết bị có thực sự nghẽn hay không.

Nếu mục tiêu là tối ưu một câu SQL, dùng execution plan và metric truy vấn phù hợp, ví dụ `EXPLAIN (ANALYZE, BUFFERS)` trên môi trường được phép. Lưu ý `ANALYZE` thực thi câu lệnh thật; đối với DML có tác dụng phụ, phải kiểm soát transaction/môi trường trước khi chạy.

### Hit ratio cao vẫn có thể chậm

Giả sử buffer hit ratio đạt 99%, nhưng mỗi request quét hàng triệu block để lọc 10 dòng. Tỷ lệ hit đẹp không làm **số công việc** nhỏ đi. Tối ưu index hoặc query plan có thể hữu ích hơn thêm RAM. Tương tự, Redis có hit ratio 95% nhưng key được đọc nhiều nhất thường trả JSON cực lớn; chi phí truyền và deserialize vẫn cao.

**Thước đo cuối cùng** là độ trễ, thông lượng, error rate, chi phí tài nguyên và **độ đúng/độ mới dữ liệu** theo yêu cầu nghiệp vụ, không chỉ một tỷ lệ hit đơn lẻ.

## 17. Trường hợp thực tế: hiển thị giá và chốt đơn

Giả sử hệ thống thương mại điện tử muốn hiển thị giá nhanh nhưng không được chấp nhận đơn dựa trên tồn kho cũ.

**Đường đọc hiển thị:**

```text
GET /products/BOOK-1
  -> Cache ProductView (tên, mô tả, giá hiển thị)
  -> TTL 30s / evict theo sự kiện đổi nội dung
  -> Trả giá trị và thời điểm cập nhật nếu cần
```

Nếu chính sách cho phép giá hiển thị trễ tối đa khoảng thời gian xác định, cache có thể là lựa chọn hợp lý. Cần ghi rõ điều kiện khi giá thay đổi mà người dùng vừa nhìn thấy giá cũ.

**Đường ghi chốt đơn:**

```sql
BEGIN;

UPDATE inventory
SET available = available - :quantity,
    version = version + 1
WHERE sku = :sku
  AND status = 'ACTIVE'
  AND available >= :quantity;
-- Bắt buộc kiểm tra đã cập nhật đúng 1 hàng.

-- Chốt giá theo chính sách trên dữ liệu authoritative,
-- ghi order và snapshot giá áp dụng trong cùng transaction.
-- Nếu bước nào thất bại: ROLLBACK.

COMMIT;
```

Câu SQL chỉ là **khung minh họa**; `:quantity` và `:sku` là tham số mà code phải bind. Một use case hoàn chỉnh còn cần ngăn trùng `request_id`, quyền truy cập, giao dịch ghi order, xử lý kết quả commit không rõ, và quy định nguồn giá có thẩm quyền.

Đường chốt đơn không dựa vào `available` từ cache để quyết định bán; database kiểm tra trực tiếp khi ghi. Nếu giá đã thay đổi so với giá người dùng thấy, ứng dụng phải áp dụng quy tắc sản phẩm: từ chối và yêu cầu xác nhận giá mới, hoặc giữ giá theo chính sách đã cam kết. Không giải quyết quy tắc giá bằng cách “tăng TTL” hoặc “tăng shared_buffers”.

**Một loại dữ liệu có thể có hai hợp đồng đọc**: hiển thị nhanh và quyết định giao dịch đúng. Điều đó thường hợp lý hơn việc ép toàn bộ hệ thống sử dụng một cache strategy duy nhất.

## 18. Bảo mật và ranh giới tenant trong cache ứng dụng

Database có thể áp dụng quyền người dùng, row-level security hoặc điều kiện `tenant_id` trong SQL. Nhưng nếu ứng dụng trả thẳng DTO từ cache theo một key chỉ gồm `product_id`, nó có thể **bỏ qua hoàn toàn đường kiểm tra quyền của SQL**.

Ví dụ nguy hiểm:

```text
Key cache: invoice:123
Tenant A đọc invoice 123 → cache lưu hóa đơn của A
Tenant B yêu cầu invoice 123 → cache HIT
Nếu không kiểm quyền/tenant ở cache boundary:
  Tenant B có thể nhận dữ liệu của Tenant A
```

Biện pháp:

- Key hoặc namespace phải bao gồm **phạm vi tenant/quyền cần thiết**; không tin dữ liệu tenant từ client mà chưa xác thực.
- Dữ liệu nhạy cảm phải có chính sách cache rõ, thời gian sống phù hợp, kiểm soát truy cập, mã hóa khi truyền/lưu và quy trình xóa theo yêu cầu.
- Không đưa token, mật khẩu, credential hay dữ liệu cá nhân không cần thiết vào key/log/metrics; key có thể xuất hiện trong hệ quan sát.
- Việc đổi quyền hoặc xóa dữ liệu cần được phản ánh trong chính sách vô hiệu hóa; một TTL dài có thể không đáp ứng yêu cầu thu hồi quyền.
- Nếu chỉ dùng cache để tăng tốc một dữ liệu có phân quyền phức tạp, có thể chọn **bypass cache** hoặc cache theo security context với kiểm tra bổ sung trước khi trả dữ liệu.

Một cache hit rất nhanh nhưng vượt qua ranh giới phân quyền là lỗi bảo mật, không phải tối ưu hiệu năng.

## 19. Kiểm thử các loại lỗi của từng tầng cache

Một phép benchmark 1000 lần `GET` cùng key chỉ chứng minh hit nhanh; nó không chứng minh invalidation và recovery an toàn.

| Kịch bản | Kết quả cần quan sát |
| --- | --- |
| Cache lạnh, database có dữ liệu | Cache miss đọc DB, điền key, trả đúng dữ liệu. |
| JVM/Redis cache bị xóa hoặc restart | Có fallback hợp lệ, không mất dữ liệu nghiệp vụ từ database. |
| Thay giá rồi commit | Request mới đáp ứng chính sách độ mới; invalidation hoặc TTL hoạt động. |
| Ghi DB thất bại/rollback | Không công bố giá trị mới như thể đã commit. |
| Reader nạp dữ liệu cũ sau khi writer đã evict | Nhận diện race stale fill và xác nhận cơ chế/giới hạn chấp nhận. |
| Hai event update tới sai thứ tự | Không để revision cũ ghi đè revision mới nếu hợp đồng yêu cầu monotonic. |
| Event invalidation bị mất | TTL hoặc cơ chế reconcile làm dữ liệu hết stale trong giới hạn mục tiêu. |
| Nhiều pod cache các bản khác nhau | Đo mức không nhất quán giữa pod và kiểm tra invalidation fan-out. |
| Hàng nghìn request đồng thời cache miss | Không làm DB sụp vì stampede; có giới hạn concurrency/backpressure. |
| Read replica chậm nhưng cache vừa miss | Không xem dữ liệu replica cũ là dữ liệu mới nhất cho nghiệp vụ nhạy cảm. |
| DB process crash/restart | DB phục hồi dữ liệu đã commit theo policy; cache có thể cold hoặc stale tùy thứ tự sự cố. |
| Đổi quyền tenant trong khi key còn sống | Không tiết lộ dữ liệu sai tenant hoặc tiếp tục cho phép quyền đã bị thu hồi. |

Đối với integration test concurrency, nên dùng **hai kết nối DB độc lập** và các điểm đồng bộ rõ để điều khiển thời điểm read, commit, invalidation, cache put. Test thuần unit với mock có thể xác nhận gọi `evict()`, nhưng **không tái hiện được** lịch xen kẽ tạo stale fill, độ trễ replica hoặc lỗi mất event.

### Kiểm thử độ mới có thể quan sát

Nếu sản phẩm chấp nhận dữ liệu hiển thị cũ tối đa một khoảng thời gian, hãy ghi một **SLO staleness** đo được: ví dụ “95% lần đọc nhìn thấy cập nhật trong 2 giây; mọi key phải được refresh trong một giới hạn tối đa xác định khi hạ tầng ổn định”. Các con số phải do yêu cầu nghiệp vụ quyết định và cần nêu ngoại lệ, không coi giá trị ví dụ là chuẩn hệ thống.

Thu thập `updated_at` hoặc revision từ nguồn dữ liệu, so với revision mà client nhận; tránh dùng clock của hai máy không đồng bộ để kết luận chính xác tuyệt đối nếu chưa có chiến lược đồng bộ thời gian.

## 20. Checklist quyết định tối ưu đúng tầng

Trước khi tăng RAM database hoặc thêm Redis, hãy trả lời:

1. **Điểm nghẽn thực tế ở đâu?** Round-trip tới DB, CPU truy vấn, I/O physical, lock, serialization, mapping hay cache service?
2. **Loại dữ liệu nào?** Dữ liệu hiển thị, tổng hợp, quyền truy cập, tồn kho hay số dư? Có được phép stale không?
3. **Ai là nguồn có thẩm quyền?** Cache ứng dụng hay database, và hành vi khi cache miss/fail là gì?
4. **Khóa cache thể hiện đủ ngữ cảnh không?** Tenant, locale, bộ lọc, quyền, schema version, chính sách giá?
5. **Ai có quyền ghi dữ liệu?** Tất cả API/job/consumer có phát invalidation hoặc cập nhật revision theo cùng giao thức không?
6. **Khi nào coi ghi thành công?** Sau commit DB, sau ghi cache, sau replica ACK hay sau event consumer? Hệ thống hứa gì với client?
7. **Có thể mất invalidation không?** Có TTL, outbox/retry, kiểm tra revision hoặc quy trình reconcile phù hợp?
8. **Race stale fill và thứ tự event đã được thử chưa?** Có test nhiều transaction và nhiều pod không?
9. **Hệ thống sống được khi cache chết không?** Fallback DB được giới hạn để tránh cascading failure?
10. **Đo chỉ số nào?** Cache hit, số SQL/request, DB buffer hit, physical I/O, p95/p99, độ cũ dữ liệu, tài nguyên và lỗi.

Nếu DB có buffer hit cao nhưng SQL vẫn chậm vì quét nhiều hàng, cần xem truy vấn/index. Nếu DB ít tải nhưng mạng tới DB và serialization là điểm nghẽn trên dữ liệu đọc lặp, cache ứng dụng có thể mang lại lợi ích. Nếu dữ liệu stale làm sai giao dịch, cần sửa **hợp đồng nhất quán**, không chỉ thay thuật toán cache.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Một API có cache Redis hit và trả kết quả mà không gửi SQL. PostgreSQL `shared_buffers` có tham gia vào lượt đọc đó không?

**Không trực tiếp.** Redis trả dữ liệu ở tầng ứng dụng; SQL không được gửi xuống PostgreSQL nên bộ đệm DB không cần phục vụ lượt đọc đó.

**Câu 2.** PostgreSQL báo buffer hit 99%. Có nghĩa 99% HTTP request không truy cập database không?

**Không.** Đây là tỷ lệ ở tầng buffer manager của DBMS, không phải application cache hit ratio. Nhiều SQL có thể chạy và đọc hàng triệu block từ RAM DB.

**Câu 3.** Vì sao `blks_read` trong `pg_stat_database` không đồng nghĩa số lần đọc vật lý từ SSD?

Vì block mà PostgreSQL đọc vào buffer có thể được **OS page cache** phục vụ mà không phải truy cập thiết bị vật lý. Muốn đo I/O thực cần thêm metric OS/storage.

**Câu 4.** Transaction B commit đổi giá từ 100 lên 120, nhưng Java vẫn trả 100 trong 20 giây. Có chắc database transaction bị lỗi không?

**Không.** Cache ứng dụng có thể còn giá cũ dù DB đã commit. Cũng cần xét replica lag hoặc snapshot cũ nếu có SQL. Phải xác định tầng phục vụ kết quả trước khi kết luận.

**Câu 5.** Có nên dùng `available` trong Redis để xác nhận đơn mua 4 khi cache nói còn 5?

**Không dùng làm quyết định cuối** nếu database là nguồn quản lý tồn kho. Phép giữ hàng cần `UPDATE ... WHERE available >= 4` hoặc giao thức concurrency tương đương trong transaction DB.

**Câu 6.** Sau khi `COMMIT` rồi `DEL key`, cache có thể lại chứa dữ liệu cũ không?

**Có.** Một request đã đọc giá cũ từ DB trước commit nhưng điền cache sau khi `DEL` có thể tái tạo entry stale. Cần chính sách stale chấp nhận được hoặc giao thức version/invalidation mạnh hơn.

**Câu 7.** JPA `EntityManager.find()` trả lại cùng managed entity đã đọc trước đó, dù transaction khác đã cập nhật DB. Nên lập tức tăng PostgreSQL `shared_buffers` chứ?

**Không.** Đây có thể là hành vi persistence context/first-level cache và transaction snapshot. Cần xét `refresh()`, clear context, lock hoặc isolation phù hợp, không chỉnh RAM DB để chữa dữ liệu managed entity cũ.

**Câu 8.** Dữ liệu bị mất khỏi Redis sau restart nhưng hàng đã commit vẫn có ở PostgreSQL. Đây là mất dữ liệu nghiệp vụ không?

**Không**, nếu PostgreSQL là nguồn có thẩm quyền và Redis chỉ lưu bản sao tính lại được. Đây là cache miss/cold start; cần xem tải DB tăng đột biến và khả năng phục hồi.

## Kết luận

**Cache ứng dụng** chủ yếu giúp **tránh thực hiện lại thao tác đọc ở tầng ứng dụng và database** bằng cách lưu DTO hoặc kết quả theo key. **Bộ đệm của DBMS** giúp **thực thi SQL hiệu quả hơn** bằng cách giữ trang dữ liệu/chỉ mục trong RAM nhưng vẫn tuân theo transaction, MVCC, khóa, WAL và cơ chế phục hồi của database. Hai tầng giải quyết vấn đề khác nhau và có những chỉ số đo khác nhau.

Trong Java, hãy bắt đầu từ **nguồn dữ liệu có thẩm quyền, mức độ mới dữ liệu cần thiết và bất biến nghiệp vụ**, rồi mới quyết định cache JVM, Redis hay tối ưu buffer/index/query của database. Với dữ liệu dùng để chấp nhận giao dịch, phép kiểm tra cuối phải được bảo vệ ở ranh giới ghi có thẩm quyền. Với dữ liệu được phép stale, cần TTL, invalidation, xử lý sự cố, kiểm thử race và metric đủ để chứng minh mức đánh đổi là chấp nhận được.
