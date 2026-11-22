# Bộ nhớ đệm kết quả truy vấn và quan hệ với cache Entity

## 1. Vì sao cần phân biệt các loại cache trong JPA?

Khi một ứng dụng Spring Data JPA đọc dữ liệu, Hibernate có thể lấy dữ liệu từ nhiều tầng cache trước khi truy vấn database. Các tầng này có phạm vi, nội dung và mục đích khác nhau. Nếu chỉ gọi chung là “cache JPA”, rất dễ nhầm rằng cache kết quả truy vấn cũng lưu toàn bộ trạng thái entity hoặc rằng bật cache entity sẽ tự động cache mọi câu SELECT.

Ba cơ chế quan trọng cần phân biệt:

1. **First-level cache (L1):** cache nằm trong persistence context của một EntityManager. Đây là cơ chế quản lý entity bắt buộc trong JPA; mỗi persistence context duy trì một đối tượng entity cho một định danh nhất định.
2. **Second-level cache (L2) / entity cache:** cache tùy chọn ở cấp EntityManagerFactory hoặc Hibernate SessionFactory, có thể được chia sẻ giữa nhiều persistence context. Nó lưu trạng thái entity theo định danh.
3. **Query cache:** cache tùy chọn của Hibernate, lưu kết quả của một truy vấn cụ thể cùng thông tin tham số và phân trang. Với truy vấn trả entity, query cache thường lưu định danh entity và dùng entity cache để lấy trạng thái entity.

Spring Data JPA không tự động cache mọi kết quả repository. Query cache là tính năng của Hibernate; còn Spring Cache là một abstraction riêng để cache kết quả phương thức ở tầng ứng dụng.

## 2. First-level cache: cache trong persistence context

Mỗi EntityManager quản lý một persistence context. Khi một entity được tải vào persistence context, Hibernate theo dõi entity đó và duy trì identity map: cùng một entity type và primary key trong cùng persistence context sẽ tương ứng với cùng một instance đang được quản lý.

Ví dụ:

~~~java
Product first = entityManager.find(Product.class, 10L);
Product second = entityManager.find(Product.class, 10L);

System.out.println(first == second); // true trong cùng persistence context
~~~

Sau lần find đầu tiên, Hibernate thường không cần chạy thêm SELECT cho lần find tiếp theo cùng ID trong cùng persistence context. Lần thứ hai có thể lấy chính instance đang được quản lý từ L1 cache.

Đặc điểm của L1:

- Phạm vi là một persistence context, không được chia sẻ tự động giữa các EntityManager.
- Được dùng mặc định; không cần bật bằng thuộc tính cache.
- Giúp duy trì identity và theo dõi thay đổi entity.
- Bị giải phóng khi persistence context đóng; có thể xóa bằng EntityManager.clear().
- Không phải query cache: nó tra cứu entity theo định danh, không lưu một tập kết quả truy vấn tùy ý để dùng giữa các EntityManager.

L1 có thể làm sai lệch phép đo nếu chỉ chạy một truy vấn lặp lại trong cùng EntityManager. Kết quả lần hai có thể đến từ persistence context, không chứng minh query cache hoặc L2 đã hoạt động.

## 3. Second-level cache: cache trạng thái entity

L2 là cache tùy chọn nằm ngoài một persistence context cụ thể. Khi được cấu hình, nhiều EntityManager có thể dùng chung cache này thông qua Hibernate SessionFactory. Mục đích của nó là giảm số lần đọc trạng thái entity từ database khi cùng một entity được truy cập lặp lại qua nhiều transaction hoặc persistence context.

Ví dụ, transaction A tải Product có ID 10. Khi entity được đưa vào L2 cache, transaction B dùng EntityManager khác có thể lấy trạng thái entity từ L2 mà không cần đọc lại hàng tương ứng từ database, nếu cache entry còn hợp lệ và chiến lược cache cho phép.

L2 cache được quản lý theo entity type và identifier. Nó không tự động cache mọi kết quả tìm kiếm như “tất cả sản phẩm thuộc danh mục BOOK”. Đó là nhiệm vụ của query cache hoặc cache tầng ứng dụng.

### 3.1. Khai báo entity có thể cache

JPA có annotation jakarta.persistence.Cacheable để đánh dấu entity đủ điều kiện dùng shared cache. Hibernate cung cấp thêm annotation org.hibernate.annotations.Cache để chỉ định chiến lược và vùng cache.

~~~java
import jakarta.persistence.Cacheable;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;

import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;

@Entity
@Table(name = "products")
@Cacheable
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "product"
)
public class Product {
    @Id
    @SequenceGenerator(
        name = "product_seq_gen",
        sequenceName = "product_seq",
        allocationSize = 50
    )
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "product_seq_gen"
    )
    private Long id;

    private String name;
    private String category;

    protected Product() {
    }

    public Product(String name, String category) {
        this.name = name;
        this.category = category;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }
}
~~~

Ví dụ dùng SEQUENCE cho ID chỉ nhằm minh họa mapping entity; chiến lược sinh ID không phải điều kiện bắt buộc để bật L2 cache.

Một số điểm cần hiểu:

- @Cacheable là annotation chuẩn JPA, đánh dấu entity đủ điều kiện tham gia shared cache theo cấu hình cache mode của persistence unit.
- @Cache là annotation riêng của Hibernate, chỉ định concurrency strategy và region.
- region = "product" đặt entity vào vùng cache có tên product để có thể cấu hình, theo dõi hoặc evict riêng.
- Chỉ thêm annotation chưa đủ nếu ứng dụng chưa cấu hình second-level cache provider và Hibernate chưa bật L2 cache.
- Nếu entity có quan hệ collection, việc cache entity không đồng nghĩa collection membership cũng được cache. Collection có thể cần cấu hình cache riêng.

### 3.2. Các concurrency strategy thường gặp

Hibernate cung cấp các chiến lược cache thể hiện mức độ nhất quán mà ứng dụng chấp nhận:

| Chiến lược | Khi phù hợp | Lưu ý |
|---|---|---|
| READ_ONLY | Dữ liệu bất biến sau khi tạo, ví dụ danh mục cố định | Phù hợp nhất khi entity thực sự không được cập nhật thường xuyên hoặc không được cập nhật. |
| NONSTRICT_READ_WRITE | Dữ liệu ít thay đổi và chấp nhận một khoảng thời gian ngắn có thể đọc giá trị cũ | Không cung cấp bảo đảm nhất quán mạnh trong mọi thời điểm cập nhật. |
| READ_WRITE | Entity có thể thay đổi và cần phối hợp cache với cập nhật transaction | Dùng cơ chế soft lock của Hibernate/provider; vẫn phải hiểu giới hạn của cache provider và môi trường phân tán. |
| TRANSACTIONAL | Cần cache tham gia giao dịch với bảo đảm tương ứng | Phụ thuộc cache provider và tích hợp transaction, thường yêu cầu hạ tầng phức tạp hơn. |

Không nên dùng READ_ONLY cho entity mà ứng dụng vẫn cập nhật. Cũng không nên coi READ_WRITE là thay thế cho constraint, khóa hoặc optimistic locking ở database. Cache strategy là chính sách đồng bộ cache, còn tính đúng đắn dữ liệu vẫn cần được bảo vệ ở tầng transaction và database.

## 4. Query cache của Hibernate lưu gì?

Query cache lưu kết quả của một truy vấn đã được đánh dấu cacheable. Khóa cache phụ thuộc vào nội dung truy vấn, tham số, phân trang và một số ngữ cảnh thực thi. Cùng một câu JPQL nhưng khác giá trị tham số hoặc trang kết quả có thể tạo entry khác nhau.

Cần phân biệt hai loại kết quả:

- **Truy vấn trả scalar hoặc giá trị đơn giản:** query cache có thể lưu các giá trị kết quả, ví dụ tên sản phẩm, số lượng hoặc tổng tiền.
- **Truy vấn trả entity:** Hibernate thường cache định danh entity trong query result, cùng các giá trị kết quả khác nếu có. Trạng thái entity được lấy từ L2 cache nếu có entry phù hợp; nếu L2 không có dữ liệu, Hibernate vẫn phải đọc trạng thái entity từ database theo các ID đó.

Vì vậy, query cache không phải bản sao thứ hai của toàn bộ entity cache. Nó trả lời câu hỏi “truy vấn này cho ra những kết quả nào?”, còn L2 trả lời câu hỏi “trạng thái entity có ID này là gì?”.

### 4.1. Vì sao query cache thường cần đi cùng entity cache?

Giả sử truy vấn:

~~~sql
select p from Product p where p.category = 'BOOK'
~~~

Lần đầu, Hibernate chạy SQL để tìm sản phẩm thuộc BOOK và đưa kết quả truy vấn vào query cache. Với entity result, query cache lưu các ID của Product phù hợp.

Ở lần truy vấn sau, nếu query cache entry còn hợp lệ, Hibernate có thể bỏ qua câu SQL tìm kiếm theo category. Tuy nhiên, Hibernate vẫn cần materialize các Product để trả về cho ứng dụng:

- Nếu Product tương ứng có trong L1, dùng instance đang được quản lý.
- Nếu không có trong L1 nhưng có trong L2, lấy trạng thái entity từ L2.
- Nếu không có trong L2, Hibernate cần truy cập database để lấy trạng thái entity theo ID.

Do đó, **query cache hit không đồng nghĩa với việc không còn truy cập database**. Nếu entity cache không được bật hoặc các entity thường xuyên bị evict, query cache có thể bỏ qua truy vấn tìm danh sách ID nhưng vẫn phát sinh SELECT để tải từng entity hoặc nhóm entity.

Query cache thường có giá trị cao hơn khi kết quả truy vấn lặp lại và các entity tương ứng cũng được giữ trong L2 cache. Với truy vấn chỉ trả scalar hoặc aggregate, query cache có thể hữu ích ngay cả khi không cần cache entity state.

## 5. Bật L2 cache và query cache trong Hibernate

Cả L2 cache và query cache đều là tính năng tùy chọn của Hibernate. Ví dụ cấu hình cơ bản trong application.properties:

~~~properties
spring.jpa.properties.hibernate.cache.use_second_level_cache=true
spring.jpa.properties.hibernate.cache.use_query_cache=true
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Ngoài các thuộc tính trên, ứng dụng cần cấu hình một cache provider tương thích với phiên bản Hibernate đang dùng. Có thể dùng Hibernate JCache integration cùng một JCache implementation như Ehcache, hoặc một provider khác được Hibernate hỗ trợ. Dependency và giá trị region factory phải khớp phiên bản Hibernate; không nên sao chép một class factory từ hướng dẫn của phiên bản khác.

Ví dụ, khi dùng JCache, dự án thường cần module tích hợp tương ứng của Hibernate và thư viện provider. Cache provider chịu trách nhiệm lưu entry, giới hạn dung lượng, expiry, eviction và chia sẻ cache theo cấu hình. Việc chỉ đặt use_second_level_cache=true mà không có provider/region factory phù hợp có thể khiến ứng dụng khởi động lỗi hoặc cache không hoạt động như mong đợi.

Query cache cần được bật riêng bằng use_query_cache. Bật L2 cache không tự động bật query cache; đánh dấu một query cacheable cũng không tự động làm mọi entity trở thành L2-cacheable.

### 5.1. Đánh dấu query trong Spring Data JPA

Spring Data JPA cho phép truyền JPA query hint đến Hibernate thông qua @QueryHints. Hibernate nhận hint org.hibernate.cacheable để đánh dấu truy vấn có thể dùng query cache.

~~~java
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.QueryHints;
import org.springframework.data.repository.query.Param;

import jakarta.persistence.QueryHint;

public interface ProductRepository extends JpaRepository<Product, Long> {
    @Query("""
        select p
        from Product p
        where p.category = :category
        order by p.name
        """)
    @QueryHints(
        value = @QueryHint(
            name = "org.hibernate.cacheable",
            value = "true"
        )
    )
    List<Product> findCachedByCategory(
        @Param("category") String category
    );
}
~~~

Đây là hint riêng của Hibernate, không phải một tính năng cache query bắt buộc của JPA. Nếu đổi JPA provider, hint có thể bị bỏ qua hoặc không có cùng ý nghĩa.

Có thể chỉ định query cache region bằng hint Hibernate tương ứng nếu muốn phân vùng cache theo loại truy vấn. Tên hint và cách cấu hình region cần đối chiếu với phiên bản Hibernate đang chạy. Khi không chỉ định region riêng, Hibernate sử dụng vùng query cache mặc định.

Không nên đánh dấu mọi repository method là cacheable. Hãy ưu tiên truy vấn có kết quả được dùng lặp lại, tham số có số lượng tổ hợp hợp lý và dữ liệu ít thay đổi.

## 6. Quan hệ giữa query cache và entity cache

Hai cơ chế phối hợp với nhau nhưng có vòng đời khác nhau:

| Khía cạnh | Entity cache (L2) | Query cache |
|---|---|---|
| Nội dung chính | Trạng thái entity theo entity type và ID | Kết quả của truy vấn theo query, tham số và phân trang |
| Cách tra cứu | Entity type + primary key | Query key và ngữ cảnh truy vấn |
| Phạm vi dùng | Có thể phục vụ nhiều truy vấn khác nhau khi cùng cần entity đó | Chỉ phục vụ truy vấn tương ứng với cache key |
| Bật cache | Đánh dấu/cấu hình entity và cấu hình L2 provider | Bật query cache và đánh dấu từng query cacheable |
| Truy vấn trả entity | Có thể cung cấp trạng thái entity sau khi đã biết ID | Thường cung cấp ID của các entity phù hợp |
| Truy vấn scalar | Không phải mục đích chính | Có thể lưu trực tiếp các giá trị kết quả |
| Vô hiệu hóa | Theo entity entry và cache strategy | Theo query result entry và thông tin cập nhật các bảng liên quan |

Có thể hình dung luồng đọc entity query như sau:

~~~text
Repository query
      |
      v
Hibernate query cache
      |
      +-- Cache miss --> Execute SELECT query --> Store query result
      |
      +-- Cache hit --> Retrieve entity identifiers
                              |
                              v
                    Persistence context (L1)
                              |
                     L1 miss / entity absent
                              |
                              v
                       Entity cache (L2)
                              |
                    L2 miss / entry absent
                              |
                              v
                         Database
~~~

Sơ đồ là luồng khái quát. Với truy vấn scalar, Hibernate có thể trả trực tiếp các giá trị đã cache mà không cần bước tải entity. Với truy vấn entity có join, projection hoặc collection, số bước thực tế còn tùy kiểu kết quả và mapping.

Một query cache hit có thể giảm chi phí chạy lại điều kiện lọc hoặc join, nhưng nếu L2 không chứa trạng thái entity thì database vẫn phải cung cấp entity data. Ngược lại, L2 cache có thể giúp tải nhanh một entity đã biết ID mà không cần query cache. Vì thế, hai cache giải quyết hai loại công việc khác nhau.

## 7. Query cache được làm mới và vô hiệu hóa như thế nào?

Query result có thể trở nên lỗi thời khi dữ liệu trong các bảng liên quan thay đổi. Hibernate sử dụng thông tin cập nhật (update timestamps) để theo dõi thời điểm các query space/bảng được thay đổi và đánh giá cache entry của truy vấn còn hợp lệ hay không.

Khi transaction thay đổi dữ liệu thông qua Hibernate, Hibernate có thể đánh dấu các query space liên quan đã được cập nhật. Query cache entry phụ thuộc vào bảng có cập nhật mới hơn sẽ không còn được sử dụng như kết quả hợp lệ; Hibernate chạy lại truy vấn và lưu kết quả mới.

Cơ chế này có một số hệ quả:

- Query cache invalidation có thể rộng hơn một hàng cụ thể. Một thay đổi trong bảng có thể làm mất hiệu lực nhiều query cache entry tham chiếu đến bảng đó.
- Bảng thay đổi thường xuyên làm query cache hit ratio thấp và tăng chi phí quản lý cache.
- Query cache phụ thuộc cả vùng lưu kết quả truy vấn và vùng theo dõi timestamps. Cần cấu hình cache provider và chính sách eviction phù hợp cho các vùng này.
- Các cập nhật đi qua ứng dụng khác, JDBC trực tiếp, script quản trị hoặc hệ thống bên ngoài có thể không được Hibernate biết để invalidation cache. Khi đó cần cơ chế đồng bộ, eviction hoặc TTL phù hợp.
- Bulk JPQL/SQL và native query có ngữ nghĩa khác thao tác entity thông thường. Cần kiểm tra việc đồng bộ persistence context và query spaces/cache invalidation theo provider; không mặc định rằng mọi câu SQL ngoài Hibernate đều tự cập nhật mọi cache liên quan.

Nếu hệ thống có nhiều ứng dụng cùng sửa một database, phải thiết kế chính sách cache nhất quán giữa các node và các writer. Không nên bật query cache nếu không có cách xử lý thay đổi dữ liệu bên ngoài.

## 8. Cache collection và quan hệ entity

Entity cache lưu trạng thái của entity theo ID, nhưng không mặc nhiên lưu mọi tập hợp quan hệ. Ví dụ Product có collection reviews: cache Product không tự bảo đảm danh sách review được lưu và khôi phục từ cache.

Hibernate có thể cache collection riêng bằng annotation @Cache trên association nếu loại quan hệ và provider hỗ trợ phù hợp. Khi dùng collection cache, phải xem xét việc thêm/xóa phần tử, thứ tự collection, filter và invalidation. Cache collection membership cũng khác cache trạng thái của từng Review entity.

Query cache có thể lưu kết quả truy vấn join hoặc truy vấn có association, nhưng nó không thay thế fetch strategy. Nếu ứng dụng gặp N+1 query, cần xem lại fetch join, entity graph, batch fetching hoặc projection. Bật query cache không tự sửa một mapping tải dữ liệu kém hiệu quả.

## 9. Phân biệt Hibernate query cache với Spring Cache

Tên annotation @Cacheable xuất hiện trong hai API khác nhau và rất dễ gây nhầm lẫn:

- jakarta.persistence.Cacheable: annotation chuẩn JPA trên entity, liên quan đến khả năng tham gia shared second-level cache.
- org.springframework.cache.annotation.Cacheable: annotation của Spring Cache trên phương thức, cache giá trị trả về của phương thức theo cache name và key.

Ví dụ Spring Cache ở service:

~~~java
import java.util.List;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductCatalogService {
    private final ProductRepository repository;

    public ProductCatalogService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(
        cacheNames = "productsByCategory",
        key = "#category"
    )
    public List<Product> findByCategory(String category) {
        return repository.findByCategory(category);
    }
}
~~~

Để dùng Spring Cache, ứng dụng cần bật caching bằng @EnableCaching và cấu hình CacheManager/provider phù hợp. Ví dụ trên cache kết quả phương thức ở tầng Spring; nó không tự bật Hibernate query cache và không yêu cầu query phải có hint org.hibernate.cacheable.

So sánh:

| Cơ chế | Vị trí đánh dấu | Cache cái gì? | Ai quản lý? |
|---|---|---|---|
| JPA/Hibernate L2 | Annotation/cấu hình entity | Trạng thái entity theo ID | Hibernate và L2 provider |
| Hibernate query cache | Query hint/cấu hình Hibernate | Kết quả truy vấn | Hibernate query cache |
| Spring Cache | Annotation trên service method | Giá trị trả về của phương thức | Spring Cache và CacheManager |

Spring Cache có thể cache DTO hoặc danh sách kết quả ở tầng ứng dụng. Nhưng ứng dụng phải chủ động thiết kế key và invalidation. Ví dụ khi cập nhật Product, cần evict hoặc cập nhật entry productsByCategory liên quan; Hibernate query cache invalidation không tự động xóa cache Spring. Tương tự, @CacheEvict của Spring không tự động evict L2 cache nếu không gọi cơ chế tương ứng.

Không nên dùng nhiều tầng cache cho cùng một dữ liệu mà chưa xác định rõ nguồn sự thật, TTL, eviction và cách xử lý ghi. Cache trùng lặp có thể làm dữ liệu cũ tồn tại ở một tầng dù tầng khác đã được cập nhật.

## 10. Khi nào nên dùng query cache và entity cache?

Query cache thường phù hợp khi:

- Cùng một truy vấn được chạy lặp lại với cùng tham số và phân trang.
- Dữ liệu liên quan ít thay đổi so với tần suất đọc.
- Kết quả có kích thước hợp lý, không tạo quá nhiều cache key khác nhau.
- Ứng dụng có thể quan sát hit/miss và quản lý invalidation.
- Với truy vấn trả entity, L2 cache cũng có khả năng phục vụ các entity đó.

Entity L2 cache thường phù hợp khi:

- Một nhóm entity được nhiều transaction đọc lặp lại theo ID.
- Dữ liệu ít thay đổi hoặc có concurrency strategy phù hợp.
- Có thể cấu hình cache provider ổn định và nhất quán giữa các instance.
- Việc cache giúp giảm đáng kể lượt đọc database.

Tránh cache không chọn lọc đối với:

- Dữ liệu thay đổi liên tục hoặc yêu cầu đọc mới nhất nghiêm ngặt.
- Truy vấn có rất nhiều tổ hợp tham số, sort và page khiến cache key phân mảnh.
- Kết quả lớn, ít được tái sử dụng.
- Entity có quan hệ phức tạp và invalidation khó kiểm soát.
- Dữ liệu được sửa thường xuyên bởi nhiều writer bên ngoài Hibernate mà không có cơ chế đồng bộ cache.

Cache là một đánh đổi giữa hiệu năng, bộ nhớ và độ mới của dữ liệu. Đừng bật cache chỉ vì có thể bật; hãy xác định truy vấn nào tốn kém, có tỷ lệ tái sử dụng đủ cao và có quy tắc invalidation rõ ràng.

## 11. Kiểm tra cache có thực sự hoạt động

Để kiểm chứng, cần phân biệt query cache hit, L2 cache hit và L1 cache hit. Chỉ nhìn vào việc repository trả kết quả nhanh hơn chưa đủ chứng minh cơ chế nào đã hoạt động.

Có thể bật Hibernate statistics trong môi trường kiểm thử:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Sau đó lấy SessionFactory từ EntityManagerFactory và đọc Statistics:

~~~java
import jakarta.persistence.EntityManagerFactory;

import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.springframework.stereotype.Component;

@Component
public class HibernateCacheMetrics {
    private final Statistics statistics;

    public HibernateCacheMetrics(EntityManagerFactory entityManagerFactory) {
        SessionFactory sessionFactory =
                entityManagerFactory.unwrap(SessionFactory.class);
        this.statistics = sessionFactory.getStatistics();
    }

    public void printCacheStatistics() {
        System.out.println(
                "Query cache hits: " + statistics.getQueryCacheHitCount()
        );
        System.out.println(
                "Query cache misses: " + statistics.getQueryCacheMissCount()
        );
        System.out.println(
                "L2 cache hits: " + statistics.getSecondLevelCacheHitCount()
        );
        System.out.println(
                "L2 cache misses: " + statistics.getSecondLevelCacheMissCount()
        );
    }
}
~~~

Đây là ví dụ đọc số liệu thống kê; trong ứng dụng thật nên xuất các metric qua hệ thống monitoring thay vì in trực tiếp ra console. Các API Statistics thuộc Hibernate, không phải JPA portable API.

Quy trình kiểm thử gợi ý:

1. Dùng database engine và JDBC driver gần với production, chẳng hạn Testcontainers.
2. Bật L2 cache, query cache và statistics; cấu hình cache provider thực tế.
3. Tạo dữ liệu đã commit và chạy một query đã đánh dấu cacheable lần đầu để tạo query cache entry.
4. Đóng hoặc clear persistence context rồi chạy lại cùng query với cùng tham số để loại ảnh hưởng của L1 cache.
5. Quan sát query cache hit/miss và L2 hit/miss; kiểm tra log SQL để xác định database có còn chạy câu truy vấn hoặc SELECT tải entity hay không.
6. Cập nhật entity qua Hibernate rồi chạy lại truy vấn để kiểm tra invalidation.
7. Thử cập nhật dữ liệu bằng JDBC hoặc tiến trình bên ngoài để xác minh chính sách đồng bộ/eviction của hệ thống.
8. Đo cả thời gian, số lượt truy cập database, bộ nhớ và độ mới dữ liệu; so sánh với trường hợp không bật cache.

Khi kiểm thử entity query, query cache hit nhưng vẫn có SELECT tải entity có thể là hành vi bình thường nếu L2 cache miss. Đừng kết luận query cache không hoạt động chỉ vì còn SQL đọc entity; hãy phân loại SQL tìm tập kết quả và SQL lấy trạng thái entity.

## 12. Những nhầm lẫn thường gặp

- **L1 không phải L2:** L1 thuộc một persistence context; L2 được chia sẻ ở phạm vi SessionFactory/provider theo cấu hình.
- **L2 không phải query cache:** L2 lưu trạng thái entity theo ID; query cache lưu kết quả của một truy vấn.
- **Query cache hit không đồng nghĩa không truy cập database:** entity result vẫn cần trạng thái entity từ L1, L2 hoặc database.
- **Bật L2 không tự bật query cache:** phải bật query cache và đánh dấu từng query phù hợp.
- **saveAll() không đồng nghĩa batch insert:** nó lưu từng entity qua repository; batching phụ thuộc Hibernate, identifier strategy, flush và JDBC.
- **Spring @Cacheable khác JPA @Cacheable:** một cái cache kết quả phương thức, một cái đánh dấu entity đủ điều kiện shared cache.
- **Cache invalidation cần được thiết kế:** các thay đổi bên ngoài Hibernate có thể không được tự động phản ánh vào cache.
- **Query cache không thay thế fetch optimization:** vẫn cần giải quyết N+1, projection và fetch plan đúng cách.

Khi thiết kế cache trong Spring Data JPA, hãy xác định rõ dữ liệu nào cần cache theo ID, truy vấn nào có kết quả lặp lại, ai là writer của dữ liệu và mức độ cũ có thể chấp nhận. Dùng L2 để tái sử dụng trạng thái entity, query cache để tái sử dụng kết quả truy vấn, và Spring Cache khi cần cache kết quả phương thức ở tầng ứng dụng. Kiểm tra hit/miss và invalidation trên đúng database/provider trước khi đưa cấu hình vào production.