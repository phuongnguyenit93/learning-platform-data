# Thiết lập dữ liệu và phép đo trước khi tối ưu

**Module:** Spring Data JPA  
**Nhóm kiến thức:** Bộ nhớ đệm

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vì sao cần bộ dữ liệu đại diện và đường cơ sở trước khi tối ưu.
- Thiết kế dữ liệu kiểm thử phản ánh quy mô, phân bố và quan hệ của dữ liệu thực tế.
- Xây dựng workload có thể lặp lại và xác định rõ điều kiện đo.
- Thu thập số liệu từ Hibernate, Spring Cache, ứng dụng và cơ sở dữ liệu.
- Phân biệt persistence context, Hibernate second-level cache, query cache, Spring Cache và cache của database.
- Đánh giá cache hit, cache miss, độ trễ, thông lượng, bộ nhớ và tính đúng đắn sau cập nhật.
- So sánh trước và sau tối ưu bằng cùng dữ liệu, workload và môi trường.

## 2. Vì sao phải chuẩn bị dữ liệu và phép đo trước?

Tối ưu hiệu năng là một quá trình thử nghiệm. Nếu không có bộ dữ liệu đại diện và đường cơ sở, bạn khó biết hệ thống thực sự chậm ở đâu, thay đổi nào đã giúp ích và thay đổi nào chỉ làm kết quả của một lần chạy trông tốt hơn.

Trong Spring Data JPA, hiệu năng có thể bị ảnh hưởng bởi nhiều tầng:

- Câu SQL, chỉ mục, kế hoạch thực thi và số hàng cơ sở dữ liệu phải đọc.
- Số lượng entity và association Hibernate phải hydrate.
- N+1 query do truy cập quan hệ lazy.
- Persistence context, second-level cache và query cache.
- Spring Cache ở tầng Service.
- Connection pool, thread pool, CPU, bộ nhớ và garbage collection.
- Cache buffer của hệ điều hành hoặc cơ sở dữ liệu.
- Mạng, độ trễ giữa ứng dụng và database, cũng như tải đồng thời.

Một cache hit cao chưa chắc làm endpoint nhanh hơn. Có thể cache đang trả về một object graph quá lớn, chi phí serialize cao, hoặc truy vấn vốn đã rất nhanh. Ngược lại, một tỷ lệ cache hit vừa phải vẫn có thể giảm đáng kể tải database nếu những truy vấn được tránh có chi phí lớn.

Trước khi thay đổi mapping, query, chỉ mục hoặc cấu hình cache, cần trả lời được ba câu hỏi:

1. **Hệ thống đang chậm ở đâu?** Ứng dụng, Hibernate, database, mạng hay một tầng khác?
2. **Tải thực tế trông như thế nào?** Có bao nhiêu bản ghi, quan hệ, người dùng đồng thời và tỷ lệ đọc/ghi?
3. **Thành công được đo bằng gì?** Ví dụ p95 giảm, thông lượng tăng, số truy vấn giảm hoặc CPU database giảm mà kết quả nghiệp vụ vẫn chính xác.

Không tối ưu chỉ vì một cấu hình nghe có vẻ nhanh. Hãy đặt giả thuyết, đo trước, thay đổi có kiểm soát và đo lại.

## 3. Xác định use case và giả thuyết tối ưu

Bắt đầu từ một luồng nghiệp vụ cụ thể thay vì đo toàn bộ ứng dụng cùng lúc. Ví dụ:

- Mở trang danh sách sản phẩm theo danh mục.
- Xem chi tiết sản phẩm kèm danh mục và ảnh.
- Tải trang lịch sử đơn hàng của một khách hàng.
- Tìm sản phẩm theo mã hoặc tên.
- Đọc cấu hình ít thay đổi nhiều lần.
- Cập nhật giá hoặc tồn kho rồi đọc lại dữ liệu.

Mỗi use case cần mô tả rõ:

| Nội dung | Ví dụ cần ghi nhận |
|---|---|
| Endpoint hoặc phương thức | GET /products?category=... |
| Dữ liệu đầu vào | Danh mục, bộ lọc, số trang, kích thước trang |
| Số bản ghi | Tổng sản phẩm, số kết quả mỗi trang |
| Quan hệ được đọc | Category, images, reviews |
| Kiểu thao tác | Chỉ đọc hay có ghi |
| Tỷ lệ đọc/ghi | 95% đọc, 5% cập nhật |
| Mức đồng thời | 20, 100 hoặc 300 request đồng thời |
| Độ mới dữ liệu | Có thể cũ 30 giây hay phải cập nhật ngay |
| Chỉ số mục tiêu | p95, query count, database CPU, cache hit |

Sau đó viết một giả thuyết có thể kiểm chứng. Ví dụ:

> Trang danh sách đang phát sinh một truy vấn cho mỗi sản phẩm khi đọc tên danh mục. Nếu chuyển sang DTO projection có join cần thiết, số truy vấn trên một request sẽ giảm và p95 sẽ thấp hơn mà kết quả phân trang vẫn giữ nguyên.

Một giả thuyết về cache có thể là:

> Thông tin danh mục ít thay đổi và được nhiều request đọc lặp lại. Nếu cache DTO danh mục trong 60 giây, số lần truy vấn database sẽ giảm. Cần kiểm tra thêm tỷ lệ hit, bộ nhớ, độ trễ sau cache miss và độ trễ khi danh mục được cập nhật.

Giả thuyết phải nêu cả lợi ích dự kiến và rủi ro cần kiểm tra. Với cache, rủi ro thường là dữ liệu cũ, chi phí invalidation, cache stampede hoặc tiêu thụ bộ nhớ quá lớn.

## 4. Chuẩn bị bộ dữ liệu đại diện

### 4.1. Quy mô dữ liệu phải gần với thực tế

Một truy vấn có thể chạy rất nhanh với 100 bản ghi nhưng chậm rõ rệt với hàng triệu bản ghi. Hãy chọn ít nhất một quy mô nhỏ để kiểm tra chức năng và một quy mô gần với tải dự kiến để đo hiệu năng.

Ví dụ với một ứng dụng bán hàng:

- 100.000 sản phẩm.
- 10.000 danh mục.
- 1.000.000 đơn hàng.
- Trung bình 3 dòng hàng mỗi đơn, nhưng có một số đơn chứa hàng chục hoặc hàng trăm dòng.
- Một nhóm nhỏ sản phẩm có lượng truy cập cao, phần còn lại ít được truy cập.

Các con số chỉ là ví dụ. Hãy dựa trên quy mô hiện tại, dự báo tăng trưởng và yêu cầu tải của ứng dụng.

### 4.2. Phân bố dữ liệu quan trọng không kém số lượng

Không nên chỉ tạo dữ liệu phân bố đồng đều nếu hệ thống thật có độ lệch lớn. Dữ liệu thực tế thường có:

- Một số danh mục có rất nhiều sản phẩm.
- Một số khách hàng có lịch sử giao dịch lớn hơn hẳn.
- Một số sản phẩm được đọc liên tục, tạo ra nhóm dữ liệu nóng.
- Nhiều bản ghi cũ ít được truy cập.
- Giá trị null, trạng thái khác nhau và chuỗi có độ dài khác nhau.
- Quan hệ tùy chọn hoặc collection rỗng.

Với cache, cần mô phỏng cả hot key và cold key. Nếu mọi request đều truy cập đúng một sản phẩm, cache hit có thể rất cao nhưng không đại diện cho workload có hàng trăm nghìn khóa khác nhau.

### 4.3. Giữ quan hệ và ràng buộc hợp lệ

Dữ liệu kiểm thử phải tuân theo khóa ngoại, unique constraint, kiểu dữ liệu và trạng thái nghiệp vụ. Ví dụ, một OrderLine phải tham chiếu đến một PurchaseOrder tồn tại; một Product phải có danh mục hợp lệ nếu mapping yêu cầu.

Nếu dữ liệu không phản ánh cấu trúc quan hệ thực, phép đo fetch plan và cache có thể sai lệch. Hãy tạo dữ liệu theo đúng thứ tự phụ thuộc hoặc dùng công cụ migration/seed data của dự án.

### 4.4. Dùng dữ liệu tái lập được

Một lần chạy benchmark phải có thể lặp lại. Nên:

- Dùng seed cố định hoặc quy tắc tạo dữ liệu xác định.
- Ghi lại phiên bản schema, migration và ứng dụng.
- Ghi số bản ghi của từng bảng.
- Ghi cấu hình index, constraint và database.
- Có lệnh reset hoặc tái tạo môi trường kiểm thử.
- Không dùng dữ liệu cá nhân thật nếu không có quy trình cho phép; dữ liệu tổng hợp thường phù hợp hơn.

Có thể dùng Testcontainers để chạy cùng loại database trong kiểm thử tích hợp. Nếu production dùng PostgreSQL, đo trên H2 có thể không phản ánh chính xác index, planner, kiểu dữ liệu, locking hoặc hành vi SQL của PostgreSQL.

### 4.5. Tránh tạo dữ liệu quá đơn giản

Một bộ dữ liệu chỉ có ID tăng tuần tự, tên ngắn và quan hệ một-một thường không thể hiện các vấn đề về selectivity, collection lớn, phân trang hoặc phân bố truy cập. Hãy mô phỏng các trường hợp biên có ảnh hưởng đến query và cache.

## 5. Xác định workload cần đo

Bộ dữ liệu chỉ là một nửa của phép thử. Nửa còn lại là cách ứng dụng truy cập dữ liệu.

Một kịch bản tải nên xác định:

- Tỷ lệ request cho từng endpoint.
- Tỷ lệ đọc, ghi, cập nhật và xóa.
- Số người dùng đồng thời hoặc tốc độ request mỗi giây.
- Kích thước trang và cách sắp xếp.
- Tỷ lệ khóa nóng so với khóa ít truy cập.
- Tỷ lệ dữ liệu mới so với dữ liệu đã tồn tại.
- Tần suất cập nhật làm cache phải invalidation.
- Thời gian chạy đủ dài để thấy hiệu ứng ổn định.

Ví dụ workload giả lập:

| Loại request | Tỷ lệ | Hành vi |
|---|---:|---|
| Danh sách sản phẩm | 50% | Phân trang, lọc theo danh mục |
| Chi tiết sản phẩm | 30% | Đọc sản phẩm và thông tin liên quan |
| Tìm kiếm | 15% | Từ khóa thay đổi, kết quả khác nhau |
| Cập nhật sản phẩm | 5% | Thay đổi giá hoặc trạng thái |

Không phải mọi request đều nên dùng cùng một khóa. Nếu công cụ tải chỉ lặp lại một request với cùng tham số, kết quả sẽ thiên về cache nóng. Hãy phân phối khóa theo tỷ lệ truy cập thực tế.

## 6. Ghi lại môi trường đo

Khi so sánh hai lần chạy, cần biết môi trường có giống nhau không. Ghi lại:

- CPU, RAM, số instance ứng dụng và giới hạn container.
- JDK, Spring Boot, Spring Data JPA và Hibernate version.
- Database version, cấu hình connection pool và số connection.
- Schema, index, statistics của database.
- Cache provider, dung lượng, TTL, eviction policy và topology.
- Cấu hình logging, tracing, metrics và profiler.
- Mạng giữa ứng dụng và database.
- Số request đồng thời, thời gian warm-up và thời gian đo.

Không nên so sánh một lần chạy trên máy nhàn rỗi với một lần chạy khi database đang có tải nền lớn rồi kết luận thay đổi code là nguyên nhân.

Cũng cần phân biệt cache ở các tầng. Database buffer cache có thể đã giữ trang dữ liệu trong RAM ngay cả khi Hibernate second-level cache chưa có entity. Vì thế, "cold application cache" không nhất thiết là "cold database".

## 7. Đo đường cơ sở trước khi tối ưu

Đường cơ sở (baseline) là kết quả của phiên bản hiện tại với bộ dữ liệu và workload đã xác định. Hãy chạy ít nhất vài lần sau warm-up, ghi nhận kết quả từng lần và dùng thống kê phù hợp.

### 7.1. Độ trễ

Ghi nhận:

- p50: một nửa request hoàn thành trong khoảng thời gian này hoặc nhanh hơn.
- p95: 95% request hoàn thành trong khoảng thời gian này hoặc nhanh hơn.
- p99: phản ánh phần đuôi chậm, hữu ích khi hệ thống có request bất thường.
- Trung bình: có thể tham khảo nhưng dễ bị che khuất bởi outlier.

Không chỉ báo cáo thời gian trung bình. Một thay đổi có thể giảm average nhưng làm p99 tăng do lock contention hoặc cache stampede.

### 7.2. Thông lượng và lỗi

Đo request/second hoặc transaction/second cùng với tỷ lệ lỗi, timeout và retry. Thông lượng cao hơn không phải cải thiện nếu hệ thống trả sai dữ liệu hoặc phát sinh nhiều lỗi hơn.

### 7.3. Số lượng truy vấn

Đếm số SQL statement trên mỗi request/use case, đồng thời phân loại:

- SELECT, INSERT, UPDATE, DELETE.
- Truy vấn lặp lại.
- Truy vấn phát sinh do lazy association.
- Truy vấn count dùng cho phân trang.
- Truy vấn tải collection.

Một endpoint chỉ chạy hai câu SQL nhưng mỗi câu trả hàng triệu dòng vẫn có thể rất chậm. Vì vậy, query count phải đi cùng số hàng và thời gian thực thi.

### 7.4. Tài nguyên

Ghi nhận CPU ứng dụng, CPU database, heap, garbage collection, connection pool active/idle, số thread chờ connection và lượng dữ liệu truyền qua mạng. Cache có thể giảm database CPU nhưng tăng heap và GC của ứng dụng.

## 8. Công cụ đo trong Hibernate và Spring

### 8.1. Hibernate Statistics

Hibernate có thống kê về query, entity, collection và second-level cache. Có thể bật trong cấu hình kiểm thử:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Trong một bài kiểm thử cô lập, có thể lấy thống kê qua SessionFactory:

~~~java
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sessionFactory =
        entityManagerFactory.unwrap(SessionFactory.class);

Statistics statistics = sessionFactory.getStatistics();
statistics.setStatisticsEnabled(true);
statistics.clear();

// Thực thi use case cần đo tại đây.

long queryCount = statistics.getQueryExecutionCount();
long entityFetchCount = statistics.getEntityFetchCount();
long collectionFetchCount = statistics.getCollectionFetchCount();
long cacheHits = statistics.getSecondLevelCacheHitCount();
long cacheMisses = statistics.getSecondLevelCacheMissCount();
long cachePuts = statistics.getSecondLevelCachePutCount();
~~~

Đoạn mã trên là phần trích dùng trong test hoặc công cụ benchmark, không phải chương trình độc lập. Statistics thuộc SessionFactory và có thể tổng hợp hoạt động của nhiều session. Không chạy nhiều benchmark song song trên cùng SessionFactory rồi quy toàn bộ số liệu cho một request. Nên cô lập kịch bản, reset thống kê trước khi đo và đọc kết quả sau khi hoàn tất.

Hibernate Statistics có overhead. Chỉ bật trong môi trường đo phù hợp và hiểu tác động của cấu hình thống kê đến kết quả.

### 8.2. SQL log

Có thể bật SQL log trong môi trường phát triển hoặc kiểm thử:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

SQL log giúp nhận ra truy vấn lặp lại và tham số được bind. Tuy nhiên, ghi log quá nhiều có thể làm thay đổi thời gian đo. TRACE có thể ghi dữ liệu nhạy cảm; chỉ bật trong môi trường được kiểm soát và tắt sau khi điều tra.

### 8.3. Spring Boot Actuator và Micrometer

Spring Boot Actuator cùng Micrometer có thể cung cấp metrics cho HTTP request, JVM, connection pool và một số cache được instrument. Có thể theo dõi:

- Request count và thời gian phản hồi theo endpoint.
- JVM heap, GC pause và thread.
- HikariCP active, idle, pending connection.
- Cache hit, miss, put và eviction nếu CacheManager/provider được instrument.
- CPU và tài nguyên container qua hệ thống giám sát triển khai.

Không nên chỉ bật một endpoint metrics rồi kết luận hiệu năng. Cần kết hợp metrics ứng dụng với số liệu database và workload tạo ra request.

## 9. Đo trực tiếp tại cơ sở dữ liệu

### 9.1. Kiểm tra execution plan

Dùng công cụ của database để xem kế hoạch thực thi, index được sử dụng, số hàng ước lượng và số hàng thực tế. Với PostgreSQL, ví dụ:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, name, price
FROM product
WHERE category_id = 42
ORDER BY name
LIMIT 20;
~~~

ANALYZE thực thi câu truy vấn để thu thập thời gian và số hàng thực tế. Chỉ dùng với truy vấn an toàn trong môi trường phù hợp; với câu DML có tác dụng phụ, cần có chiến lược rollback và kiểm soát rõ ràng. BUFFERS giúp quan sát hoạt động đọc buffer.

Đừng thêm index chỉ vì thấy một truy vấn chậm. Hãy xem planner, selectivity, thứ tự cột của index, chi phí sort, số hàng trả về và tác động của index đến INSERT/UPDATE/DELETE.

### 9.2. Phân biệt thời gian ứng dụng và thời gian SQL

Thời gian endpoint gồm nhiều phần: chờ connection, chạy SQL, hydrate entity, ánh xạ DTO, xử lý nghiệp vụ, serialize và truyền phản hồi. Thời gian SQL thấp không đảm bảo endpoint nhanh nếu ứng dụng tạo object graph lớn hoặc serialize quá nhiều dữ liệu.

Dùng tracing hoặc profiler để xác định phần nào chiếm thời gian. So sánh thời gian tổng với thời gian query để tìm phần chi phí ngoài database.

## 10. Phân biệt các tầng cache

Trước khi thử tối ưu cache, phải xác định cache đang đo thuộc tầng nào. Các tầng có phạm vi và cách invalidation khác nhau.

| Tầng cache | Phạm vi | Nội dung thường lưu | Vòng đời |
|---|---|---|---|
| First-level cache | Một persistence context/EntityManager | Entity đang được quản lý | Kết thúc khi persistence context đóng hoặc clear |
| Second-level cache | Nhiều persistence context trong cùng ứng dụng/provider | Trạng thái entity hoặc collection được cấu hình cache | Theo provider, region và chính sách invalidation |
| Query cache | Hibernate SessionFactory/provider | Kết quả truy vấn đã cache, tùy loại query | Theo cấu hình query cache và vùng dữ liệu liên quan |
| Spring Cache | Tầng ứng dụng/service | DTO, kết quả tính toán hoặc object tùy key | Theo CacheManager, TTL và eviction |
| Database buffer cache | Database engine | Trang dữ liệu và index | Theo bộ nhớ và chính sách của database |
| Cache bên ngoài | Nhiều instance ứng dụng nếu dùng chung | Giá trị theo key | Theo hệ thống như Redis hoặc Memcached |

### 10.1. First-level cache

First-level cache là persistence context của EntityManager và có sẵn trong JPA. Khi một entity đã được quản lý trong persistence context, việc tìm lại entity theo cùng identity thường trả về cùng đối tượng đã quản lý.

Nó không phải cache dùng chung giữa mọi request hoặc mọi transaction. Khi EntityManager đóng hoặc gọi clear, các entity không còn nằm trong persistence context đó.

Cũng không nên giả định mọi JPQL query lặp lại đều được bỏ qua hoàn toàn nhờ first-level cache. Query vẫn có thể cần chạy để xác định tập kết quả; provider sau đó hợp nhất entity theo identity trong persistence context.

### 10.2. Second-level cache

Second-level cache nằm ngoài một persistence context và có thể dùng lại dữ liệu giữa các Session/EntityManager nếu provider và cache được cấu hình. Hibernate không tự bật và lưu mọi entity vào second-level cache chỉ vì ứng dụng dùng Spring Data JPA.

Ví dụ mapping entity có thể dùng cache:

~~~java
import jakarta.persistence.Cacheable;
import jakarta.persistence.Entity;
import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;

@Entity
@Cacheable
@Cache(
    usage = CacheConcurrencyStrategy.READ_WRITE,
    region = "products"
)
public class Product {
    // ID và thuộc tính
}
~~~

Cấu hình phải có dependency và region factory/provider tương thích với phiên bản Hibernate đang dùng. Ví dụ các thuộc tính bật second-level cache:

~~~properties
spring.jpa.properties.hibernate.cache.use_second_level_cache=true
~~~

Tên region, dung lượng, TTL và chính sách đồng bộ phụ thuộc cache provider. Không sao chép cấu hình region factory từ một phiên bản Hibernate khác mà chưa xác minh tương thích.

Các chế độ concurrency thường gặp của Hibernate gồm:

- READ_ONLY: dành cho dữ liệu không thay đổi sau khi tạo.
- NONSTRICT_READ_WRITE: chấp nhận một khoảng thời gian dữ liệu cache có thể chưa đồng bộ tuyệt đối.
- READ_WRITE: phối hợp cơ chế khóa mềm/invalidation theo provider để hỗ trợ dữ liệu có cập nhật.
- TRANSACTIONAL: yêu cầu provider hỗ trợ chiến lược giao dịch tương ứng.

Chọn chế độ theo đặc tính cập nhật và khả năng của provider. Không cache entity thường xuyên thay đổi nếu chưa có chiến lược nhất quán rõ ràng.

### 10.3. Query cache

Query cache là tính năng riêng của Hibernate và khác second-level cache. Nó lưu kết quả của query được đánh dấu cacheable. Với query trả entity, kết quả thường liên quan đến ID entity; trạng thái entity vẫn cần được lấy từ persistence context hoặc second-level cache.

Ví dụ query có thể được đánh dấu cacheable bằng hint Hibernate:

~~~java
@QueryHints(value = @QueryHint(
    name = "org.hibernate.cacheable",
    value = "true"
))
@Query("select p from Product p where p.category.id = :categoryId")
List<Product> findByCategoryIdCached(
        @Param("categoryId") Long categoryId);
~~~

Muốn dùng query cache cần bật nó trong Hibernate:

~~~properties
spring.jpa.properties.hibernate.cache.use_query_cache=true
~~~

Query cache không phải giải pháp mặc định cho mọi truy vấn. Với dữ liệu thay đổi thường xuyên, kết quả có thể liên tục bị invalidation. Query cache cũng cần theo dõi region và số hit/miss. Hãy đo cả truy vấn cacheable lẫn chi phí lấy trạng thái entity.

### 10.4. Spring Cache

Spring Cache là abstraction ở tầng ứng dụng. Nó có thể cache DTO hoặc kết quả của phương thức Service mà không yêu cầu kết quả phải là entity JPA.

Ví dụ cache thông tin tóm tắt sản phẩm:

~~~java
@Service
@RequiredArgsConstructor
public class ProductQueryService {

    private final ProductRepository repository;

    @Cacheable(
        cacheNames = "product-summary",
        key = "#id",
        unless = "#result == null"
    )
    @Transactional(readOnly = true)
    public ProductSummary getSummary(Long id) {
        return repository.findSummaryById(id)
                .orElseThrow(() ->
                        new EntityNotFoundException("Không tìm thấy sản phẩm"));
    }
}
~~~

ProductSummary nên là DTO có dữ liệu cần hiển thị, không chứa lazy proxy hoặc collection entity chưa tải. CacheManager quyết định cache thực tế là bộ nhớ cục bộ hay cache phân tán, thời hạn và chính sách eviction.

Khi cập nhật sản phẩm, cần invalidation đúng key:

~~~java
@CacheEvict(cacheNames = "product-summary", key = "#id")
@Transactional
public void updateProduct(Long id, UpdateProductCommand command) {
    // Tải và cập nhật entity Product
}
~~~

Với hệ thống có yêu cầu nhất quán nghiêm ngặt và nhiều request đồng thời, cần thiết kế eviction theo thời điểm commit. Có thể phát sự kiện sau commit bằng @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT), rồi xóa cache trong listener. Điều này tránh xóa cache trước khi thay đổi database được commit và một request khác đọc lại dữ liệu cũ trong khoảng thời gian đó. Cách triển khai cụ thể phải xét đến thứ tự interceptor, transaction và cache provider.

Các annotation cache cũng thường dựa vào proxy của Spring. Tự gọi một phương thức @Cacheable trong cùng bean có thể bỏ qua proxy, tương tự self-invocation với @Transactional. Hãy gọi qua bean Spring khác hoặc tách phương thức thành bean riêng.

## 11. Thiết kế phép đo cache

Một phép đo cache cần tách rõ trạng thái lạnh và nóng.

### 11.1. Cold cache

Cold cache là trạng thái cache ứng dụng chưa có các key của workload đang đo. Bắt đầu bằng cách xóa hoặc tạo mới cache trong môi trường kiểm thử, rồi chạy kịch bản một lần để quan sát:

- Thời gian cache miss.
- Số truy vấn database phát sinh.
- Chi phí đưa dữ liệu vào cache.
- Số lần gọi đồng thời cùng một key.
- Bộ nhớ tăng thêm.

Không được mặc định cold application cache đồng nghĩa với database buffer cache lạnh. Database có thể vẫn giữ dữ liệu và index trong RAM từ lần chạy trước.

### 11.2. Warm cache

Warm cache là trạng thái những key thường dùng đã được đưa vào cache. Chạy workload ổn định và đo:

- Tỷ lệ hit/miss.
- p50, p95 và p99.
- Số truy vấn database còn lại.
- CPU, heap, GC và network.
- Số eviction hoặc put.
- Thời gian xử lý khi key hết hạn hoặc bị invalidation.

Warm-up phải mô phỏng phân bố khóa của workload. Chỉ gọi lặp một key sẽ tạo kết quả quá lạc quan nếu production có nhiều key khác nhau.

### 11.3. Đo cả đường đọc và đường ghi

Nếu chỉ đo GET sau warm-up, bạn chưa biết cache ảnh hưởng thế nào khi dữ liệu cập nhật. Hãy đo:

- Đọc một key đã có cache.
- Đọc một key chưa có cache.
- Cập nhật entity rồi đọc lại.
- Cập nhật nhiều entity cùng lúc.
- Hết TTL và cache được nạp lại.
- Nhiều request cùng lúc yêu cầu một key vừa hết hạn.

Với workload ghi nhiều, chi phí invalidation và đồng bộ có thể lớn hơn lợi ích của hit.

### 11.4. Tỷ lệ hit không phải chỉ số duy nhất

Hit ratio thường được tính:

Hit ratio = Cache hits / (Cache hits + Cache misses)

Ví dụ 9.000 hit và 1.000 miss tạo hit ratio 90%. Nhưng nếu mỗi hit chỉ tránh một query rất nhẹ, còn mỗi miss phải tải graph lớn và chờ database lâu, con số 90% chưa đủ để kết luận hệ thống tốt.

Cần đọc hit ratio cùng latency, query count, memory, eviction, freshness và tỷ lệ lỗi. Hãy phân biệt hit theo cache region hoặc cache name nếu provider cung cấp.

## 12. Quy trình benchmark có thể lặp lại

Một quy trình thực tế:

1. Tạo lại hoặc khôi phục bộ dữ liệu kiểm thử đã xác định.
2. Kiểm tra schema, index, số bản ghi và cấu hình ứng dụng.
3. Tắt những log hoặc profiler gây overhead không cần thiết; giữ các metrics cần đo.
4. Chạy warm-up để JVM, connection pool và database đạt trạng thái ổn định.
5. Reset số liệu thống kê và chuẩn bị trạng thái cache đúng kịch bản.
6. Chạy workload với cùng phân bố request, số người dùng và thời gian.
7. Thu thập latency, throughput, lỗi, SQL count, cache metrics, CPU, heap và database metrics.
8. Lặp lại nhiều lần, lưu từng kết quả và tính phân vị.
9. Thay đổi đúng một yếu tố chính, chẳng hạn bật một cache region hoặc đổi query.
10. Chạy lại cùng kịch bản và so sánh kết quả.
11. Kiểm tra tính đúng đắn, invalidation và hành vi khi dữ liệu thay đổi.
12. Chỉ giữ thay đổi nếu lợi ích đo được lớn hơn chi phí và rủi ro vận hành.

Ghi lại commit/version của code, cấu hình, seed dữ liệu, câu lệnh chạy benchmark và kết quả. Nhờ vậy, người khác có thể lặp lại phép đo và xác nhận kết luận.

## 13. Ví dụ lập bảng baseline

Giả sử endpoint lấy thông tin sản phẩm được đo trước và sau khi thêm Spring Cache. Bảng sau chỉ là minh họa cách ghi nhận, không phải số liệu chuẩn cho mọi hệ thống.

| Chỉ số | Trước cache | Sau warm-up | Nhận xét |
|---|---:|---:|---|
| p50 | 42 ms | 8 ms | Độ trễ điển hình giảm |
| p95 | 110 ms | 18 ms | Phần lớn request nhanh hơn |
| Request/second | 220 | 510 | Thông lượng tăng trong cùng tải |
| DB query/request | 1,0 | 0,08 | Phần lớn request không truy vấn DB |
| Cache hit ratio | — | 92% | Cần đọc cùng latency và freshness |
| Heap sử dụng | 420 MB | 610 MB | Cache tăng mức dùng bộ nhớ |

Khi phân tích, hãy hỏi:

- p95 giảm do cache hit hay do thay đổi khác?
- Cache miss có bị chậm hơn trước không?
- Heap tăng có gây GC pause dài hơn không?
- Sau cập nhật, dữ liệu có được invalidation đúng không?
- Kết quả có giữ nguyên khi tăng số key và số request đồng thời?
- Có endpoint khác bị ảnh hưởng bởi việc chia sẻ CPU hoặc bộ nhớ không?

Nếu chỉ có một lần chạy, kết quả có thể chịu ảnh hưởng của tải nền hoặc cache database. Hãy chạy lặp và giữ cùng điều kiện.

## 14. Kiểm tra tính đúng đắn sau tối ưu

Tối ưu hiệu năng không được thay đổi ngữ nghĩa nghiệp vụ. Với cache và fetch plan, cần kiểm tra:

- Giá trị trả về trước và sau tối ưu giống nhau với cùng trạng thái dữ liệu.
- Quan hệ tùy chọn, collection rỗng và dữ liệu null được xử lý đúng.
- Phân trang không mất hoặc lặp entity.
- Sắp xếp ổn định, có tie-breaker như ID khi cần.
- Cập nhật và xóa làm invalidation đúng các key/region liên quan.
- Request đồng thời không nhận dữ liệu cũ ngoài mức chấp nhận.
- Cache miss, timeout hoặc provider lỗi có fallback phù hợp.
- Cache key bao gồm mọi tham số ảnh hưởng đến kết quả, ví dụ tenant, locale, quyền truy cập, bộ lọc và phiên bản dữ liệu.

Đặc biệt, không cache dữ liệu phụ thuộc người dùng hoặc quyền truy cập bằng một key chỉ chứa ID tài nguyên. Điều này có thể khiến kết quả của người dùng này bị trả cho người dùng khác. Hãy đưa tenant/user/role hoặc các chiều phân quyền cần thiết vào cache key, hoặc không cache kết quả nhạy cảm đó.

## 15. Những sai lầm thường gặp khi đo và tối ưu

### 15.1. Chỉ đo với vài bản ghi

Dữ liệu quá nhỏ không làm lộ N+1, thiếu index, collection lớn hoặc chi phí phân trang. Hãy kiểm tra ở quy mô gần thực tế.

### 15.2. Chỉ đo một lần và dùng average

Một lần chạy dễ bị nhiễu. Average có thể che khuất tail latency. Hãy warm-up, chạy nhiều lần và theo dõi p50/p95/p99.

### 15.3. So sánh hai workload khác nhau

Nếu lần đầu có 10 request đồng thời nhưng lần sau có 100, không thể quy chênh lệch hoàn toàn cho cache. Giữ dữ liệu, tham số, concurrency và thời gian đo tương đương.

### 15.4. Chỉ nhìn cache hit ratio

Hit cao không đảm bảo endpoint nhanh hoặc dữ liệu đúng. Cần đo latency, database load, memory, eviction và invalidation.

### 15.5. Không đo chi phí cache miss

Cache miss có thể tạo truy vấn đồng thời cho cùng key, gây cache stampede. Cần thử khi key hết hạn hoặc cache vừa được xóa.

### 15.6. Cache entity graph quá lớn

Cache một entity cùng collection lớn có thể tiêu thụ nhiều bộ nhớ và làm invalidation phức tạp. Với màn hình chỉ cần vài trường, DTO cache thường dễ kiểm soát hơn.

### 15.7. Không kiểm tra tính nhất quán sau cập nhật

Nếu dữ liệu thay đổi nhưng cache không bị xóa hoặc cập nhật đúng lúc, người dùng có thể thấy giá, tồn kho hoặc trạng thái cũ. Xác định rõ TTL, eviction và mức stale data chấp nhận được trước khi triển khai.

### 15.8. Bật log chi tiết trong benchmark

SQL log và bind TRACE có thể tạo overhead đáng kể. Dùng log để chẩn đoán, sau đó đo lại với cấu hình quan sát ổn định và phù hợp.

### 15.9. Tối ưu trước khi có giả thuyết

Thêm cache, index hoặc fetch join cùng lúc khiến không thể biết yếu tố nào tạo ra thay đổi. Hãy thay một yếu tố chính mỗi lần và giữ kết quả từng thí nghiệm.

## 16. Checklist trước khi kết luận một tối ưu hiệu quả

- [ ] Use case và chỉ số mục tiêu đã được mô tả rõ.
- [ ] Bộ dữ liệu có quy mô, phân bố và quan hệ gần thực tế.
- [ ] Dữ liệu và workload có thể tái tạo.
- [ ] Phiên bản code, database và cấu hình đã được ghi lại.
- [ ] Có baseline trước thay đổi.
- [ ] Đã warm-up và chạy lặp nhiều lần.
- [ ] Đã ghi p50, p95, p99, throughput và tỷ lệ lỗi.
- [ ] Đã đo SQL count, database CPU và execution plan khi cần.
- [ ] Đã phân biệt cold cache, warm cache và database buffer cache.
- [ ] Đã ghi hit, miss, eviction, memory và GC.
- [ ] Đã đo cả đọc, ghi, invalidation và cache miss.
- [ ] Kết quả nghiệp vụ, phân trang và quyền truy cập vẫn chính xác.
- [ ] Lợi ích đo được lớn hơn chi phí bộ nhớ và vận hành.
- [ ] Có thể lặp lại benchmark để xác nhận kết luận.

## 17. Kết luận

Muốn tối ưu bộ nhớ đệm trong Spring Data JPA một cách đáng tin cậy, trước hết phải chuẩn bị dữ liệu và workload đại diện, xác định chỉ số mục tiêu và đo baseline. Cần phân biệt persistence context, second-level cache, query cache, Spring Cache và cache của database vì mỗi tầng có phạm vi, chi phí và cách invalidation riêng. Sau mỗi thay đổi, đo lại trên cùng điều kiện, kiểm tra cả đường đọc lẫn đường ghi và xác nhận dữ liệu vẫn đúng. Chỉ giữ tối ưu khi số liệu lặp lại chứng minh được lợi ích thực tế.
