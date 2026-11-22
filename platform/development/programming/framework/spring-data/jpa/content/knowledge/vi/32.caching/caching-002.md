# Bộ nhớ đệm cấp hai và cách cấu hình theo nhà cung cấp

Bộ nhớ đệm cấp hai (second-level cache, L2 cache) của JPA lưu trạng thái entity ở phạm vi rộng hơn một `EntityManager`. Nhờ vậy, nhiều persistence context trong cùng một ứng dụng có thể tái sử dụng dữ liệu đã đọc mà không phải truy vấn database mỗi lần.

JPA định nghĩa API và annotation cơ bản để đánh dấu entity có thể được cache, nhưng việc lưu trữ thực tế, chiến lược đồng bộ, thời hạn sống và khả năng chạy trên nhiều node phụ thuộc nhà cung cấp JPA và cache provider. Hibernate và EclipseLink có cách cấu hình khác nhau. Vì thế, cần xác định provider đang dùng trước khi áp dụng cấu hình.

## 1. Phân biệt first-level cache và second-level cache

JPA có persistence context, thường được xem là first-level cache (L1). Đây là nơi theo dõi entity đang được quản lý trong một `EntityManager`.

| Đặc điểm | First-level cache (L1) | Second-level cache (L2) |
|---|---|---|
| Phạm vi | Một persistence context / EntityManager | Dùng chung giữa các persistence context của cùng persistence unit hoặc SessionFactory |
| Vòng đời | Theo persistence context | Theo cache provider và cấu hình ứng dụng |
| Mặc định | Luôn có trong persistence context | Phụ thuộc provider; Hibernate không cache entity nếu chưa được cấu hình/đánh dấu |
| Nội dung | Các entity instance đang managed và trạng thái theo dõi thay đổi | Trạng thái dữ liệu entity/collection theo định dạng cache của provider |
| Mục tiêu | Tránh tải lặp entity trong cùng một đơn vị làm việc | Tái sử dụng dữ liệu giữa các đơn vị làm việc |

Ví dụ, trong một transaction, gọi `find(Product.class, 10L)` hai lần thường trả cùng managed instance từ L1. Khi transaction kết thúc, persistence context đóng. Một request khác tạo EntityManager mới sẽ không dùng L1 cũ; nếu entity Product đủ điều kiện và L2 được bật, provider có thể lấy trạng thái từ L2 thay vì database.

L2 cache không phải một bản sao database có đầy đủ transaction và khóa như database. Nó là lớp tối ưu hiệu năng. Dữ liệu có thể cũ nếu có cập nhật từ một ứng dụng khác hoặc từ SQL không thông báo cho cache provider.

## 2. Khi nào nên dùng L2 cache?

L2 cache hữu ích nhất với dữ liệu:

- Được đọc thường xuyên.
- Ít thay đổi hoặc có quy tắc cập nhật rõ ràng.
- Có thể dùng chung giữa nhiều request và nhiều persistence context.
- Có chi phí đọc database đáng kể so với chi phí truy xuất cache.
- Có giới hạn kích thước và chính sách hết hạn phù hợp.

Ví dụ thường gặp là danh mục sản phẩm, loại tiền tệ, quốc gia, cấu hình nghiệp vụ ít thay đổi, bảng tham chiếu hoặc metadata dùng chung.

Không nên cache mọi entity. Dữ liệu đơn hàng đang thay đổi liên tục, số dư tài khoản, tồn kho hoặc trạng thái có yêu cầu nhất quán cao có thể không phù hợp với cache chia sẻ nếu chưa thiết kế kỹ chiến lược đồng bộ. Cache không thay thế optimistic locking, transaction isolation hay ràng buộc toàn vẹn ở database.

Cũng cần phân biệt L2 entity cache với query cache. L2 entity cache thường tra cứu trạng thái entity theo định danh. Query cache lưu kết quả truy vấn hoặc tập định danh theo cơ chế của provider. Bật L2 không có nghĩa query cache tự động bật.

## 3. Annotation chuẩn JPA và annotation riêng của provider

JPA cung cấp `@Cacheable` để đánh dấu entity có thể tham gia shared cache:

```java
import jakarta.persistence.Cacheable;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
@Cacheable
public class Country {

    @Id
    private String code;

    private String name;
}
```

Annotation này mang tính chuẩn JPA, nhưng không chọn cache provider, không cấu hình TTL, giới hạn dung lượng hay chính sách đồng thời. Cấu hình `shared-cache-mode` của persistence unit quyết định phạm vi entity nào đủ điều kiện cache. Giá trị `ENABLE_SELECTIVE` là lựa chọn rõ ràng, chỉ entity được đánh dấu `@Cacheable` mới đủ điều kiện theo chế độ này.

Hibernate có annotation riêng `org.hibernate.annotations.Cache` để chỉ định region và concurrency strategy. EclipseLink có annotation riêng `org.eclipse.persistence.annotations.Cache` với các tùy chọn như loại cache, dung lượng, thời hạn và isolation. Những annotation riêng này không portable giữa các provider.

Khi viết ứng dụng có thể đổi provider, hãy ưu tiên API chuẩn JPA ở phần chung, rồi đặt cấu hình riêng của provider ở nơi có chủ đích.

## 4. Cấu hình Hibernate với JCache và Ehcache 3

Spring Boot thường dùng Hibernate làm JPA provider mặc định khi ứng dụng có `spring-boot-starter-data-jpa`. Hibernate không tự cung cấp một cache backend có giới hạn dung lượng, expiry và replication; cần tích hợp một provider phù hợp.

Một cách phổ biến là dùng JCache (JSR-107) làm lớp tích hợp và Ehcache 3 làm cache provider.

### 4.1. Thêm dependency

Ví dụ Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.hibernate.orm</groupId>
        <artifactId>hibernate-jcache</artifactId>
        <version>${hibernate.version}</version>
    </dependency>

    <dependency>
        <groupId>org.ehcache</groupId>
        <artifactId>ehcache</artifactId>
        <version>${ehcache.version}</version>
    </dependency>
</dependencies>
```

Các version placeholder cần được khai báo trong dependency management của dự án. `hibernate-jcache` phải cùng version với `hibernate-core` đang được Spring Boot quản lý. Ehcache phải có module JCache tương thích và JCache API trên classpath. Không tự nâng riêng Hibernate lên một version khác với Spring Boot BOM nếu chưa kiểm tra tương thích.

### 4.2. Cấu hình Spring Boot

Trong `application.properties`:

```properties
spring.jpa.properties.hibernate.cache.region.factory_class=jcache
spring.jpa.properties.hibernate.cache.use_second_level_cache=true
spring.jpa.properties.hibernate.javax.cache.provider=org.ehcache.jsr107.EhcacheCachingProvider
spring.jpa.properties.hibernate.javax.cache.uri=/ehcache.xml
spring.jpa.properties.jakarta.persistence.sharedCache.mode=ENABLE_SELECTIVE
spring.jpa.properties.hibernate.javax.cache.missing_cache_strategy=fail
```

Trong ví dụ, file `ehcache.xml` được đặt ở thư mục gốc classpath. `jcache` chọn JCache RegionFactory của Hibernate; thuộc tính provider chỉ rõ Ehcache khi classpath có nhiều JCache implementation. Tên cấu hình `hibernate.javax.cache.*` vẫn được Hibernate sử dụng cho tích hợp JCache, dù entity của ứng dụng dùng Jakarta Persistence.

Chiến lược `missing_cache_strategy=fail` khiến ứng dụng báo lỗi nếu Hibernate yêu cầu một region chưa được cấu hình. Điều này giúp phát hiện region thiếu khi khởi động thay vì âm thầm tạo cache mặc định không có giới hạn phù hợp. Nếu chọn chiến lược khác, hãy kiểm tra cache được tạo tự động có giới hạn và eviction hay không.

### 4.3. Định nghĩa region trong Ehcache

Tên alias của cache phải khớp tên region Hibernate sẽ sử dụng. Ví dụ entity được gán region `catalog-countries`:

```java
import jakarta.persistence.Cacheable;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;

@Entity
@Cacheable
@Cache(
    usage = CacheConcurrencyStrategy.READ_ONLY,
    region = "catalog-countries"
)
public class Country {

    @Id
    private String code;

    private String name;
}
```

Tạo `src/main/resources/ehcache.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<config xmlns="http://www.ehcache.org/v3"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.ehcache.org/v3
        http://www.ehcache.org/schema/ehcache-core.xsd">

    <cache alias="catalog-countries">
        <key-type>java.lang.Object</key-type>
        <value-type>java.lang.Object</value-type>
        <expiry>
            <ttl unit="minutes">30</ttl>
        </expiry>
        <resources>
            <heap unit="entries">5000</heap>
        </resources>
    </cache>
</config>
```

Region `catalog-countries` có giới hạn 5.000 entry trong heap và TTL 30 phút. Đây là ví dụ cấu hình local cache; chọn kích thước, TTL và tier theo kích thước dữ liệu, bộ nhớ và tần suất cập nhật thực tế. Không nên dùng cấu hình mặc định không giới hạn cho production.

Nếu entity dùng region mặc định theo tên lớp thay vì khai báo `region`, alias Ehcache phải khớp tên region mặc định đó. Nếu cache cả collection role, cần định nghĩa region cho collection tương ứng. Hibernate thường cảnh báo khi phải tạo region không được khai báo trước; hãy cấu hình rõ các region được sử dụng.

### 4.4. Chọn concurrency strategy cho Hibernate

`@Cache` yêu cầu chọn chiến lược đồng thời phù hợp:

| Strategy | Trường hợp dùng | Đánh đổi |
|---|---|---|
| `READ_ONLY` | Entity bất biến hoặc dữ liệu tham chiếu không được sửa | Đơn giản, hiệu quả; cập nhật entity cacheable theo chiến lược này không phù hợp |
| `NONSTRICT_READ_WRITE` | Dữ liệu ít cập nhật, cập nhật đồng thời hiếm | Không khóa; có thể có khoảng thời gian đọc dữ liệu cũ |
| `READ_WRITE` | Dữ liệu có cập nhật nhưng không quá thường xuyên | Dùng soft lock để giảm khả năng đọc/ghi entry cũ; không cung cấp mức cô lập serializable |
| `TRANSACTIONAL` | Cache provider hỗ trợ giao dịch và yêu cầu đồng bộ chặt | Cần backend và transaction integration phù hợp; không thể chỉ bật bằng annotation |

Hãy chọn strategy theo cách dữ liệu được đọc và cập nhật. Đối với dữ liệu tham chiếu bất biến, `READ_ONLY` thường phù hợp. Với entity thay đổi thường xuyên, cần xem xét kỹ liệu lợi ích cache có xứng đáng với chi phí đồng bộ hay không.

## 5. Cấu hình provider khác: Infinispan và EclipseLink

### 5.1. Hibernate với Infinispan

Infinispan có thể được dùng làm cache backend, đặc biệt khi cần cache phân tán giữa nhiều node. Hibernate cần module tích hợp Infinispan tương thích với version Hibernate đang dùng.

Cấu hình Hibernate có dạng:

```properties
spring.jpa.properties.hibernate.cache.region.factory_class=infinispan
spring.jpa.properties.hibernate.cache.infinispan.cfg=org/infinispan/hibernate/cache/commons/builder/infinispan-configs.xml
```

Đường dẫn cấu hình trên là cấu hình mẫu được cung cấp bởi module tích hợp tương ứng. Với môi trường thực tế, hãy dùng cấu hình Infinispan đã được thiết kế cho topology, replication/distribution, persistence và bảo mật của hệ thống. Không chỉ đổi `region.factory_class` rồi mặc định rằng các node đã đồng bộ cache đúng cách.

### 5.2. EclipseLink shared cache

EclipseLink có shared cache ở phạm vi persistence unit và cung cấp cấu hình riêng qua `@Cache` hoặc persistence properties. Khác với Hibernate, shared cache của EclipseLink thường được bật mặc định cho entity theo cấu hình provider.

Ví dụ:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

import org.eclipse.persistence.annotations.Cache;
import org.eclipse.persistence.annotations.CacheType;
import org.eclipse.persistence.config.CacheIsolationType;

@Entity
@Cache(
    type = CacheType.SOFT_WEAK,
    size = 1000,
    expiry = 600000,
    isolation = CacheIsolationType.SHARED
)
public class Product {

    @Id
    private Long id;

    private String name;
}
```

Trong ví dụ, EclipseLink dùng loại cache `SOFT_WEAK`, giới hạn mục tiêu 1.000 object và đặt expiry 600.000 mili giây (10 phút). `SHARED` cho phép dữ liệu entity được dùng trong cache chung của persistence unit.

Các mức isolation chính:

- `SHARED`: entity và dữ liệu được lưu trong shared cache của EntityManagerFactory/ServerSession.
- `PROTECTED`: trạng thái được lưu trong shared cache nhưng instance entity không được chia sẻ trực tiếp giữa client.
- `ISOLATED`: entity không nằm trong shared cache; dữ liệu chỉ thuộc persistence context. Đây là cách loại entity khỏi L2 cache.

Các tên annotation và enum ở ví dụ là phần mở rộng của EclipseLink. Không dùng chúng trong entity nếu ứng dụng đang chạy Hibernate.

## 6. Query cache khác với entity L2 cache

Hibernate còn có query cache, nhưng đây là tính năng riêng và mặc định không bật. Query cache lưu kết quả truy vấn theo cơ chế của Hibernate, thường là tập định danh và thông tin liên quan để xác định kết quả còn hợp lệ hay không.

Có thể bật query cache:

```properties
spring.jpa.properties.hibernate.cache.use_query_cache=true
```

Sau đó, truy vấn cần được đánh dấu cacheable bằng hint của Hibernate, ví dụ:

```java
@Query("select c from Country c where c.active = true")
@QueryHints(
    @QueryHint(name = "org.hibernate.cacheable", value = "true")
)
List<Country> findActiveCountriesCached();
```

Query cache không thay thế entity cache. Nếu kết quả truy vấn chứa entity nhưng entity state không có trong L2 cache, Hibernate vẫn có thể cần đọc entity từ database. Cần xem xét cả tần suất truy vấn, số lượng kết quả và cách dữ liệu thay đổi trước khi bật query cache.

Các truy vấn phụ thuộc thời gian hiện tại, người dùng hiện tại hoặc tham số thay đổi liên tục thường không có tỷ lệ cache hit tốt. Không nên bật cache cho mọi repository query.

## 7. Cache invalidation, dữ liệu cũ và cập nhật ngoài Hibernate

L2 cache có thể trở nên cũ trong các tình huống:

- Một ứng dụng khác cập nhật cùng bảng.
- DBA chạy SQL trực tiếp.
- Batch job dùng JDBC/native SQL bỏ qua cơ chế đồng bộ của Hibernate.
- Một node trong cluster cập nhật dữ liệu nhưng cache node khác không nhận được invalidation.
- TTL quá dài so với mức độ thay đổi dữ liệu.

Với Hibernate, có thể evict entity hoặc region qua API cache:

```java
@Autowired
private EntityManagerFactory entityManagerFactory;

public void evictCountry(String code) {
    entityManagerFactory.getCache().evict(Country.class, code);
}
```

JPA cung cấp `Cache.evict()` và các overload để xóa một entity, một định danh hoặc toàn bộ cache. Hibernate còn có API riêng trên `SessionFactory.getCache()` để evict entity, collection hoặc toàn bộ region.

Evict là thao tác xóa cache, không phải rollback database. Khi cập nhật ngoài Hibernate, hãy xác định thời điểm và phạm vi invalidation phù hợp. Nếu cần thực hiện sau một transaction, nên evict sau khi transaction commit để tránh cache bị nạp lại giá trị cũ trong lúc transaction chưa hoàn tất.

Với ứng dụng nhiều node, eviction trên một node chỉ có hiệu lực toàn cluster nếu provider hỗ trợ và được cấu hình coordination/invalidation tương ứng. Ehcache local trong từng JVM không tự chia sẻ cache với JVM khác. Có thể dùng provider phân tán, cơ chế gửi invalidation hoặc TTL ngắn tùy yêu cầu.

Không nên coi TTL là giải pháp duy nhất cho mọi dữ liệu. TTL giới hạn tuổi entry nhưng không bảo đảm dữ liệu luôn mới ngay sau một cập nhật quan trọng. Với dữ liệu cần nhất quán, cân nhắc không cache hoặc dùng cơ chế đồng bộ có bảo đảm.

## 8. Các chế độ cache và API chuẩn JPA

JPA có thể điều khiển việc đọc/ghi shared cache qua cache retrieve/store mode. Ví dụ, có thể yêu cầu một truy vấn bỏ qua cache hoặc không đưa kết quả vào cache:

```java
List<Country> countries = entityManager
        .createQuery(
                "select c from Country c",
                Country.class
        )
        .setHint("jakarta.persistence.cache.retrieveMode", CacheRetrieveMode.BYPASS)
        .setHint("jakarta.persistence.cache.storeMode", CacheStoreMode.BYPASS)
        .getResultList();
```

Các mode phổ biến:

- `USE`: cho phép dùng cache theo cấu hình mặc định.
- `BYPASS`: bỏ qua cache cho thao tác tương ứng.
- `REFRESH`: yêu cầu làm mới dữ liệu cache từ database khi store mode được áp dụng.

API và hint chuẩn JPA có thể giúp code ít phụ thuộc provider hơn, nhưng cách provider thực thi và các giới hạn vẫn cần kiểm tra theo implementation.

## 9. Đo lường hiệu quả và lỗi thường gặp

Bật cache không đồng nghĩa hiệu năng chắc chắn tăng. Hãy theo dõi hit, miss, put, eviction, kích thước region, thời gian truy vấn và bộ nhớ.

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không có cache hit | Entity chưa được đánh dấu cacheable, L2 chưa bật hoặc provider chưa cấu hình | Kiểm tra annotation, shared cache mode, RegionFactory và log khởi động |
| Cache region bị tạo tự động không giới hạn | Region chưa được khai báo trong cấu hình provider | Khai báo region rõ ràng và đặt TTL/size/eviction |
| Dữ liệu cũ sau khi chạy SQL ngoài | Cache không được provider thông báo | Evict region/entry sau commit hoặc dùng cơ chế coordination |
| Cache hit cao nhưng database vẫn bị truy vấn | Entity state không cacheable hoặc query cache chỉ cache danh sách định danh | Đánh dấu đúng entity và đánh giá query cache riêng |
| Bộ nhớ tăng liên tục | Region không giới hạn hoặc cache quá nhiều entity/collection | Đặt giới hạn dung lượng, TTL và chỉ cache dữ liệu phù hợp |
| Cập nhật entity phát sinh lỗi với READ_ONLY | Dữ liệu được cấu hình bất biến nhưng code vẫn sửa | Chọn strategy phù hợp hoặc loại entity khỏi cache |
| Nhiều node thấy dữ liệu khác nhau | Cache local, replication/invalidation chưa cấu hình | Chọn provider phân tán hoặc cơ chế đồng bộ rõ ràng |

Khi profiling, hãy so sánh cùng một workload ở trạng thái cache lạnh và cache nóng. Đo thời gian p95/p99, số lần gọi database, memory footprint và chi phí eviction. Không chỉ dựa vào một lần truy vấn đơn lẻ.

## 10. Kiểm thử cache

Một bài kiểm thử tích hợp nên xác nhận cả hành vi cache và tính nhất quán:

1. Tạo entity cacheable và commit transaction.
2. Mở EntityManager hoặc transaction mới, đọc entity theo ID và quan sát thống kê L2 cache.
3. Đọc lại trong một persistence context khác để kiểm tra khả năng tái sử dụng L2.
4. Cập nhật entity qua JPA và xác nhận cache phản ánh giá trị mới theo concurrency strategy.
5. Thực hiện cập nhật ngoài Hibernate trong môi trường kiểm thử, evict cache theo thiết kế rồi xác nhận lần đọc tiếp theo lấy dữ liệu mới.
6. Kiểm tra TTL, eviction và giới hạn dung lượng của provider.

Không kiểm thử L2 cache chỉ bằng cách đọc entity hai lần trong cùng một EntityManager: lần đọc thứ hai có thể chỉ chứng minh L1 hoạt động. Hãy dùng persistence context mới và bật thống kê provider hoặc kiểm tra SQL để phân biệt L1 hit, L2 hit và database access.

Với cache phân tán, kiểm thử giữa hai application instance để xác minh invalidation/replication. Kiểm thử đơn JVM không chứng minh cache hoạt động đúng trên cluster.

## 11. Checklist chọn và cấu hình provider

- [ ] Đã xác định JPA provider đang chạy thực tế: Hibernate, EclipseLink hay provider khác.
- [ ] Đã phân biệt L1, L2 entity/collection cache và query cache.
- [ ] Chỉ cache entity có tỷ lệ đọc cao và chính sách cập nhật phù hợp.
- [ ] Dùng `@Cacheable` theo chuẩn JPA và annotation/provider configuration khi cần strategy/region cụ thể.
- [ ] Hibernate có RegionFactory và cache provider tương thích; version module tích hợp khớp Hibernate core.
- [ ] Region có giới hạn dung lượng, TTL và eviction phù hợp; không để cache mặc định vô hạn trong production.
- [ ] Chọn concurrency strategy dựa trên tính bất biến và tần suất cập nhật.
- [ ] Xác định cách invalidation khi có native SQL, JDBC, ứng dụng ngoài hoặc nhiều node.
- [ ] Query cache được đánh giá riêng, không bật đại trà.
- [ ] Có số liệu hit/miss/eviction, SQL và memory để chứng minh lợi ích.
- [ ] Có integration test dùng persistence context mới và kiểm tra dữ liệu sau invalidation.

L2 cache có thể giảm số lần đọc database khi nhiều request cùng truy cập dữ liệu ít thay đổi. Tuy nhiên, nó bổ sung một lớp trạng thái nằm ngoài database, nên cấu hình provider, chiến lược đồng thời, giới hạn vùng cache và invalidation đều quan trọng. Hãy bắt đầu với một vài entity tham chiếu có hành vi rõ ràng, đo hiệu quả bằng workload thật, rồi mới mở rộng sang các region khác.

## Tài liệu tham khảo

- [Hibernate ORM 7 – Caching và cấu hình JCache/Ehcache](https://docs.hibernate.org/orm/7.2/introduction/html_single/)
- [Hibernate ORM User Guide – Caching](https://docs.hibernate.org/orm/7.0/userguide/html_single/)
- [EclipseLink 4 – JPA Extensions Reference, @Cache](https://eclipse.dev/eclipselink/documentation/4.0/jpa/extensions/jpa-extensions.html)
- [Ehcache 3 – XML configuration](https://www.ehcache.org/documentation/3.10/xml.html)