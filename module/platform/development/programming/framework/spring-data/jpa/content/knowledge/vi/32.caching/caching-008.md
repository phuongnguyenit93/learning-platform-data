# Chọn dữ liệu nên cache, thời hạn và khả năng chấp nhận dữ liệu cũ trong Spring Data JPA

Cache giúp giảm số lần truy vấn database và rút ngắn thời gian phản hồi bằng cách giữ lại dữ liệu đã đọc hoặc kết quả tính toán để tái sử dụng. Tuy nhiên, cache luôn tạo ra một câu hỏi về tính đúng đắn: dữ liệu được giữ trong bao lâu, khi nào phải làm mới và người dùng có thể chấp nhận dữ liệu cũ đến mức nào?

Không nên cache chỉ vì một truy vấn chậm. Trước hết cần xác định dữ liệu có được đọc lặp lại nhiều không, chi phí tải/tính toán có đáng kể không, dữ liệu thay đổi thường xuyên đến mức nào và hậu quả ra sao nếu kết quả cũ được dùng. Một danh mục sản phẩm có thể chấp nhận trễ vài phút; số dư tài khoản hoặc tồn kho dùng để xác nhận giao dịch có thể cần dữ liệu mới hơn nhiều.

Bài học này hướng dẫn chọn đối tượng cache, đặt freshness/staleness budget, chọn TTL, thiết kế key và invalidation, phân biệt Spring Cache với các cache của JPA/Hibernate, kiểm soát cache stampede và theo dõi hiệu quả trong ứng dụng thực tế.

## 1. Cache giải quyết vấn đề gì?

Một lần đọc dữ liệu thường đi qua nhiều tầng:

1. Ứng dụng gọi service.
2. Repository tạo truy vấn.
3. JPA provider tạo SQL và gửi tới database.
4. Database đọc index/data, thực thi truy vấn và trả kết quả.
5. Hibernate ánh xạ kết quả thành entity hoặc projection.
6. Ứng dụng biến đổi dữ liệu thành response.

Cache có thể tránh một phần hoặc toàn bộ các bước đó ở lần đọc tiếp theo. Nếu dữ liệu giống nhau được yêu cầu nhiều lần, cache giảm tải database và có thể giảm latency.

Ví dụ một API lấy thông tin sản phẩm theo SKU được gọi 5.000 lần mỗi phút, trong khi thông tin mô tả sản phẩm chỉ thay đổi vài lần mỗi ngày. Việc đọc cùng một bản ghi lặp lại từ database có thể không cần thiết.

Ngược lại, nếu mỗi request có một filter riêng biệt và gần như không có key nào được lặp lại, cache có thể tiêu tốn bộ nhớ mà tỷ lệ hit rất thấp.

Cache không làm truy vấn gốc nhanh hơn. Cache chỉ giúp những lần đọc tiếp theo có thể bỏ qua truy vấn hoặc tính toán tương ứng. Truy vấn miss vẫn cần đủ hiệu năng để xử lý tải thực tế.

## 2. Các loại cache thường gặp trong ứng dụng Spring Data JPA

Có nhiều tầng cache, mỗi tầng có phạm vi và mục tiêu khác nhau:

| Tầng cache | Phạm vi | Nội dung được giữ | Thời gian sống điển hình |
|---|---|---|---|
| Persistence context / first-level cache | Một EntityManager | Entity đang managed theo identity | Theo vòng đời persistence context |
| JPA second-level cache | Chia sẻ giữa các persistence context trong một ứng dụng/provider | Trạng thái entity hoặc association được cache | Theo cấu hình provider |
| Hibernate query cache | Provider Hibernate | Kết quả truy vấn theo query/parameter | Theo region và chiến lược invalidation |
| Spring Cache | Tầng ứng dụng/service | Kết quả method, thường là DTO hoặc read model | Theo cache manager/provider |
| Cache phân tán | Nhiều instance ứng dụng | Key/value dùng chung qua Redis hoặc hệ thống tương tự | Theo TTL và invalidation |

Không nên gọi tất cả các tầng này là một loại cache. First-level cache là một phần của persistence context; Spring Cache là abstraction ở tầng ứng dụng; second-level/query cache thuộc JPA provider.

Một request có thể đi qua nhiều tầng. Ví dụ service method được Spring Cache hit thì repository không được gọi. Nếu Spring Cache miss, repository có thể chạy; Hibernate lại kiểm tra persistence context và second-level cache theo cấu hình.

## 3. First-level cache của JPA

Mỗi persistence context có một identity map cho entity được quản lý. Trong cùng một EntityManager, một entity có cùng loại và cùng khóa chính được đại diện bởi cùng một managed instance.

Đây là method fragment trong một service có EntityManager được inject bằng @PersistenceContext; Customer là entity của ứng dụng.

~~~java
@Transactional
public void demonstrateFirstLevelCache(Long id) {
    Customer first = entityManager.find(Customer.class, id);
    Customer second = entityManager.find(Customer.class, id);

    System.out.println(first == second);
}
~~~

Trong cùng persistence context, kết quả thường là:

~~~text
true
~~~

Lần gọi thứ hai có thể lấy instance đã được quản lý mà không cần chạy thêm câu SELECT cho cùng khóa chính.

First-level cache:

- Chỉ có hiệu lực trong persistence context hiện tại.
- Không phải cache dùng chung giữa các request hoặc EntityManager.
- Theo dõi thay đổi của entity managed và hỗ trợ dirty checking.
- Có thể bị làm rỗng bằng clear(), hoặc một entity có thể bị detach bằng detach().
- Không phải cơ chế cache kết quả tùy ý của một JPQL query.

Lưu ý: JPQL query vẫn có thể được gửi tới database dù entity tương ứng đã có trong persistence context. Khi kết quả được ánh xạ, provider sẽ dùng managed identity tương ứng. Không nên dựa vào first-level cache để giả định mọi truy vấn tìm kiếm đều được bỏ qua.

## 4. Second-level cache của JPA/Hibernate

Second-level cache được chia sẻ giữa nhiều persistence context trong phạm vi cấu hình của JPA provider. Nó có thể giúp tránh đọc lại trạng thái entity đã được cache ở lần truy cập sau.

JPA cung cấp annotation jakarta.persistence.Cacheable để đánh dấu entity đủ điều kiện tham gia second-level cache:

~~~java
import jakarta.persistence.Cacheable;
import jakarta.persistence.Entity;

@Entity
@Cacheable
public class Country {
    // Entity mapping
}
~~~

Annotation này không tự cung cấp một cache implementation hoặc chính sách TTL. Cần cấu hình provider và cache region factory tương ứng. Với Hibernate, chiến lược cache có thể được cấu hình bằng annotation Hibernate và cache provider phù hợp.

Ví dụ Hibernate-specific:

~~~java
import org.hibernate.annotations.Cache;
import org.hibernate.annotations.CacheConcurrencyStrategy;

@Entity
@jakarta.persistence.Cacheable
@Cache(
    usage = CacheConcurrencyStrategy.READ_ONLY,
    region = "reference-country"
)
public class Country {
    // Entity mapping
}
~~~

READ_ONLY phù hợp với dữ liệu tham chiếu thực sự không thay đổi trong vòng đời cache. Nếu entity có cập nhật, cần chọn concurrency strategy phù hợp; không dùng READ_ONLY cho dữ liệu thường xuyên ghi.

Các chiến lược Hibernate như READ_ONLY, NONSTRICT_READ_WRITE, READ_WRITE và TRANSACTIONAL có ngữ nghĩa nhất quán/chi phí khác nhau. Hãy chọn dựa trên tần suất đọc/ghi, yêu cầu consistency và khả năng của provider/cache backend.

Second-level cache hữu ích khi nhiều persistence context đọc lặp lại cùng entity. Tuy nhiên, nếu database được cập nhật trực tiếp bởi ứng dụng khác hoặc SQL ngoài Hibernate, cache có thể không nhận được invalidation. Cần có cơ chế đồng bộ hoặc không cache loại dữ liệu đó.

## 5. Hibernate query cache khác entity cache

Hibernate query cache giữ kết quả của một query cụ thể theo query key và tham số. Nó không đồng nghĩa với second-level entity cache.

Một query cache hit có thể giúp tránh thực thi lại truy vấn theo cách provider hỗ trợ, nhưng entity được trả về vẫn có thể cần lấy trạng thái từ second-level cache hoặc database.

Query cache thường cần cấu hình rõ ràng và phù hợp nhất với query có kết quả ổn định, lặp lại. Nếu query thay đổi liên tục theo tham số, sort, page hoặc dữ liệu nền, tỷ lệ hit có thể thấp và chi phí invalidation cao.

Không bật query cache toàn cục mà chưa đo workload. Với Hibernate, query cache và region invalidation phụ thuộc cấu hình provider/version. Hãy xem tài liệu Hibernate của phiên bản đang dùng trước khi cấu hình.

## 6. Spring Cache là cache ở tầng ứng dụng

Spring Cache cung cấp abstraction cho các cache provider như Caffeine, Redis hoặc cache manager khác. Annotation thường dùng:

- @Cacheable: kiểm tra cache trước; chỉ chạy method khi key chưa có.
- @CachePut: luôn chạy method rồi cập nhật cache bằng kết quả.
- @CacheEvict: xóa một key hoặc toàn bộ cache region.
- @Caching: kết hợp nhiều thao tác cache trên cùng method.

Spring Cache thường phù hợp để cache kết quả service như ProductView, CustomerSummary hoặc một read model. Cache không cần biết dữ liệu được lấy từ JPA, REST API hay phép tính.

Chú ý phân biệt hai annotation cùng tên:

- org.springframework.cache.annotation.Cacheable: cache kết quả method ở tầng Spring.
- jakarta.persistence.Cacheable: đánh dấu entity có thể tham gia second-level cache theo JPA.

Hai annotation này có mục đích khác nhau và không thể thay thế lẫn nhau.

## 7. Chọn dữ liệu nào nên cache?

Một ứng viên cache tốt thường có nhiều đặc điểm sau:

- Được đọc lặp lại nhiều lần với cùng một bộ tham số.
- Chi phí đọc database hoặc tính toán đáng kể.
- Tần suất cập nhật thấp hơn đáng kể so với tần suất đọc.
- Có thể xác định rõ key và các điều kiện ảnh hưởng tới kết quả.
- Có thể chấp nhận một khoảng thời gian dữ liệu chưa phản ánh thay đổi mới nhất.
- Kích thước dữ liệu và số lượng key có thể giới hạn.
- Có cách invalidation hoặc refresh phù hợp.

Ví dụ:

| Loại dữ liệu | Mức phù hợp thường gặp | Lý do |
|---|---|---|
| Danh mục quốc gia, tỉnh/thành | Cao | Ít thay đổi, nhiều request dùng chung |
| Danh sách loại sản phẩm | Cao | Đọc nhiều, cập nhật ít |
| Cấu hình hiển thị công khai | Cao nếu có version/TTL | Nhiều request dùng cùng cấu hình |
| Chi tiết sản phẩm, mô tả | Trung bình đến cao | Có thể tái sử dụng; cần invalidation khi cập nhật |
| Kết quả tìm kiếm phổ biến | Trung bình | Chỉ hiệu quả nếu query/key được lặp lại |
| Dashboard tổng hợp | Trung bình | Tính toán có thể đắt; phải xác định độ mới chấp nhận được |
| Tồn kho dùng để xác nhận đơn | Thấp nếu cần chính xác tức thời | Giá trị thay đổi liên tục và ảnh hưởng giao dịch |
| Số dư tài khoản | Thấp nếu yêu cầu nhất quán mạnh | Dữ liệu tài chính không nên dựa vào bản cache cũ |
| Quyền truy cập theo user | Cần đánh giá kỹ | Thay đổi quyền có thể tạo rủi ro bảo mật |
| Kết quả cá nhân hóa | Chỉ khi key đầy đủ | Phải tính đến user, tenant, locale và quyền |

Bảng này là hướng dẫn thiết kế, không phải quy tắc tuyệt đối. Một dashboard nội bộ có thể chấp nhận dữ liệu trễ 30 giây; một báo cáo kiểm toán có thể yêu cầu dữ liệu tại thời điểm truy vấn.

## 8. Xác định dữ liệu có đáng cache hay không

Trước khi thêm annotation, hãy trả lời các câu hỏi:

1. Bao nhiêu request đọc cùng dữ liệu trong một khoảng thời gian?
2. Chi phí query hiện tại là bao nhiêu: latency, CPU database, số dòng và số lần gọi?
3. Dữ liệu thay đổi bao lâu một lần?
4. Ai hoặc hệ thống nào có thể thay đổi dữ liệu?
5. Nếu cache trả dữ liệu cũ, tác động nghiệp vụ là gì?
6. Có thể invalidation theo key hay chỉ xóa toàn bộ region?
7. Số lượng key tối đa và kích thước mỗi value là bao nhiêu?
8. Cache hit có thực sự giảm bottleneck đang gặp hay chỉ chuyển chi phí sang serialization/network?

Nếu query vốn rất nhanh và key gần như không lặp, cache có thể làm hệ thống phức tạp hơn mà không đem lại lợi ích đáng kể.

Đo trước khi cache và đo lại sau khi cache. Tối ưu hóa cần dựa trên hit ratio, latency và tải database thực tế.

## 9. Freshness và staleness budget

Freshness mô tả dữ liệu cache gần với trạng thái hiện tại đến mức nào. Staleness là khoảng cách giữa dữ liệu đang được cache và dữ liệu mới nhất ở nguồn.

Staleness budget là mức dữ liệu cũ tối đa mà nghiệp vụ có thể chấp nhận.

Ví dụ:

- Danh sách quốc gia: có thể chấp nhận nhiều giờ hoặc nhiều ngày.
- Nội dung sản phẩm: có thể chấp nhận vài phút nếu thay đổi không ảnh hưởng giao dịch.
- Giá hiển thị: có thể cần làm mới nhanh hơn, tùy cam kết với khách hàng.
- Tồn kho hiển thị: có thể hiển thị gần đúng, nhưng bước xác nhận đơn phải kiểm tra nguồn dữ liệu có thẩm quyền.
- Số dư dùng để chuyển tiền: cần đọc/ghi theo cơ chế nhất quán của hệ thống tài chính, không dựa vào cache ứng dụng thông thường.

Không chọn TTL trước rồi mới hỏi nghiệp vụ có chấp nhận không. Hãy xác định staleness budget trước, sau đó chọn TTL và invalidation để đáp ứng ngân sách đó.

TTL chỉ giới hạn thời gian một entry được giữ theo chính sách cache. Nó không tự bảo đảm mọi thay đổi đều được phản ánh ngay, cũng không bảo đảm dữ liệu không cũ nếu cache được làm mới từ một replica đang trễ.

## 10. Chọn TTL theo hành vi dữ liệu

TTL (time to live) là thời gian một entry được phép tồn tại trong cache trước khi hết hạn.

Một số chiến lược:

| Chiến lược | Cách hoạt động | Phù hợp |
|---|---|---|
| expire-after-write | Hết hạn sau một khoảng kể từ lần ghi gần nhất | Dữ liệu có freshness budget rõ |
| expire-after-access | Hết hạn sau một khoảng không được truy cập | Dữ liệu ít dùng tự được loại bỏ |
| TTL cố định ngắn | Tất cả key cùng một khoảng ngắn | Kết quả biến động vừa phải |
| TTL theo loại dữ liệu | Mỗi cache region có thời hạn riêng | Ứng dụng có nhiều mức freshness |
| Không TTL + invalidation | Chỉ xóa khi có sự kiện cập nhật | Dữ liệu ổn định, có invalidation đáng tin |
| Refresh ahead | Làm mới trước khi entry hết hạn | Key phổ biến, load miss rất đắt |

Expire-after-access có thể khiến một key nóng tồn tại lâu hơn dự kiến vì mỗi lần truy cập lại làm mới thời gian hết hạn. Nếu cần giới hạn tuổi dữ liệu tối đa, expire-after-write thường dễ dự đoán hơn.

TTL nên cân bằng giữa cache hit và độ cũ. TTL quá ngắn làm miss nhiều và tăng tải database; TTL quá dài làm dữ liệu cũ lâu hơn và khiến invalidation trở nên quan trọng hơn.

Có thể thêm jitter ngẫu nhiên nhỏ vào TTL để nhiều key được ghi cùng lúc không đồng loạt hết hạn, tránh tạo đỉnh tải bất thường. Jitter phải nằm trong staleness budget.

## 11. Cache-aside: mẫu phổ biến ở tầng service

Cache-aside (lazy loading) là mẫu đơn giản:

1. Đọc cache theo key.
2. Nếu hit, trả kết quả.
3. Nếu miss, đọc nguồn dữ liệu.
4. Đưa kết quả vào cache.
5. Trả kết quả cho caller.

Spring @Cacheable thực hiện phần lớn luồng này:

~~~java
@Cacheable(cacheNames = "productBySku", key = "#p0")
public ProductView getBySku(String sku) {
    Product product = repository.findBySku(sku)
            .orElseThrow(() -> new ProductNotFoundException(sku));

    return new ProductView(
            product.getSku(),
            product.getName(),
            product.getPrice(),
            product.getUpdatedAt()
    );
}
~~~

Khi key đã có trong cache, method body không được chạy. Khi key chưa có, method thực thi và kết quả được lưu.

Cache-aside dễ triển khai và chỉ cache dữ liệu thực sự được đọc. Nhược điểm là lần đọc đầu tiên sau khi hết hạn/invalidation phải tải dữ liệu từ nguồn; nếu nhiều request đồng thời cùng miss, có thể xảy ra cache stampede.

## 12. Ví dụ domain Product dùng trong các phần tiếp theo

Các ví dụ dùng entity Product trong package com.example.product.

~~~java
package com.example.product;

import java.math.BigDecimal;
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 80)
    private String sku;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(nullable = false, precision = 19, scale = 4)
    private BigDecimal price;

    @Column(nullable = false)
    private Instant updatedAt;

    protected Product() {
    }

    public Product(
            String sku,
            String name,
            BigDecimal price,
            Instant updatedAt) {
        this.sku = sku;
        this.name = name;
        this.price = price;
        this.updatedAt = updatedAt;
    }

    public void changePrice(BigDecimal newPrice, Instant changedAt) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException("price must be non-negative");
        }
        this.price = newPrice;
        this.updatedAt = changedAt;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
~~~

DTO bất biến để cache:

~~~java
package com.example.product;

import java.math.BigDecimal;
import java.time.Instant;

public record ProductView(
        String sku,
        String name,
        BigDecimal price,
        Instant updatedAt
) {
}
~~~

Repository:

~~~java
package com.example.product;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    Optional<Product> findBySku(String sku);
}
~~~

SKU có unique constraint nên findBySku phù hợp với Optional. DTO ProductView chứa các giá trị cần cho API, không giữ proxy hoặc association LAZY.

## 13. Cấu hình Spring Cache với Caffeine

Caffeine là cache local trong bộ nhớ của một JVM. Nó có độ trễ thấp và hỗ trợ giới hạn kích thước, expiration và thống kê.

Dependency cần có:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-cache</artifactId>
</dependency>
<dependency>
    <groupId>com.github.ben-manes.caffeine</groupId>
    <artifactId>caffeine</artifactId>
</dependency>
~~~

Cấu hình cache:

~~~java
package com.example.product;

import java.time.Duration;

import com.github.benmanes.caffeine.cache.Caffeine;

import org.springframework.cache.CacheManager;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfiguration {

    @Bean
    public CacheManager cacheManager() {
        CaffeineCacheManager manager =
                new CaffeineCacheManager("productBySku");

        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(10_000)
                .expireAfterWrite(Duration.ofMinutes(5)));

        return manager;
    }
}
~~~

Trong ví dụ, cache productBySku có tối đa khoảng 10.000 entry và mỗi entry hết hạn sau 5 phút kể từ lần ghi. Đây là thông số minh họa; production cần chọn theo số SKU hoạt động, kích thước DTO, memory budget và staleness budget.

Caffeine local cache không chia sẻ dữ liệu giữa các instance ứng dụng. Nếu chạy nhiều replica, mỗi instance có bản cache riêng. Khi một instance cập nhật sản phẩm, cần cơ chế invalidation tới các instance còn lại hoặc chấp nhận chúng chỉ làm mới khi TTL hết hạn.

## 14. Dùng @Cacheable để cache kết quả service

Service:

~~~java
package com.example.product;

import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCatalogService {

    private final ProductRepository repository;
    private final ApplicationEventPublisher eventPublisher;

    public ProductCatalogService(
            ProductRepository repository,
            ApplicationEventPublisher eventPublisher) {
        this.repository = repository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional(readOnly = true)
    @Cacheable(cacheNames = "productBySku", key = "#p0")
    public ProductView getBySku(String sku) {
        Product product = repository.findBySku(sku)
                .orElseThrow(() -> new ProductNotFoundException(sku));

        return toView(product);
    }

    @Transactional
    public void changePrice(String sku, BigDecimal newPrice) {
        Product product = repository.findBySku(sku)
                .orElseThrow(() -> new ProductNotFoundException(sku));

        product.changePrice(newPrice, Instant.now());
        eventPublisher.publishEvent(new ProductChanged(sku));
    }

    private ProductView toView(Product product) {
        return new ProductView(
                product.getSku(),
                product.getName(),
                product.getPrice(),
                product.getUpdatedAt()
        );
    }
}
~~~

Exception:

~~~java
package com.example.product;

public class ProductNotFoundException extends RuntimeException {

    public ProductNotFoundException(String sku) {
        super("Product not found: " + sku);
    }
}
~~~

Khi getBySku("SKU-100") được gọi lần đầu, repository đọc database và service tạo ProductView. Spring Cache lưu DTO theo key SKU-100. Các lần gọi tiếp theo trong TTL có thể trả DTO từ cache.

Method được cache phải được gọi qua Spring proxy. Nếu một method trong cùng class gọi trực tiếp method @Cacheable khác của chính object đó (self-invocation), interceptor caching mặc định có thể không được áp dụng.

Trong ví dụ, key dùng #p0 để tham chiếu tham số đầu tiên, tránh phụ thuộc vào việc tên parameter có được giữ trong bytecode hay không.

## 15. Vì sao nên cache DTO/read model thay vì JPA entity?

Cache entity ở tầng ứng dụng có thể tạo nhiều vấn đề:

- Entity có thể là proxy hoặc chứa association LAZY chưa được khởi tạo.
- Entity managed gắn với persistence context; sau khi transaction kết thúc nó trở thành detached.
- Cùng entity có thể được load với fetch plan khác nhau.
- Thay đổi entity hoặc association có thể không được phản ánh trong object đã cache.
- Serialization proxy và quan hệ hai chiều có thể gây vòng tham chiếu hoặc lỗi serialization.
- Cache object entity làm lộ nhiều trường hơn mức API cần trả.

DTO/read model bất biến thường dễ cache hơn vì chỉ chứa dữ liệu cần thiết cho use case, không mang persistence context hay lazy proxy.

Second-level cache của Hibernate là một cơ chế khác: nó được thiết kế để cache trạng thái entity theo provider, không đồng nghĩa với việc đặt object entity tùy ý vào Spring Cache.

Nếu cache một DTO phụ thuộc nhiều nguồn dữ liệu, key và invalidation phải phản ánh tất cả nguồn đó. DTO đơn giản không tự làm cho dữ liệu nhất quán.

## 16. Cache key phải đại diện cho toàn bộ đầu vào ảnh hưởng kết quả

Cache key sai có thể trả dữ liệu của request này cho request khác.

Nếu kết quả phụ thuộc các tham số sau, tất cả phải được đưa vào key:

- SKU hoặc entity ID.
- Tenant hoặc organization.
- Ngôn ngữ/locale.
- User hoặc nhóm quyền nếu kết quả được cá nhân hóa.
- Currency hoặc region.
- Filter, sort và page nếu cache kết quả tìm kiếm.
- Version của cấu hình hoặc schema khi có liên quan.

Ví dụ multi-tenant:

~~~java
@Cacheable(
    cacheNames = "productByTenantAndSku",
    key = "#p0 + ':' + #p1"
)
public ProductView getByTenantAndSku(
        String tenantId,
        String sku) {
    // Load product trong phạm vi tenant.
}
~~~

Không dùng SKU làm key duy nhất nếu cùng SKU có thể tồn tại ở nhiều tenant.

Nếu key có nhiều thành phần, dùng format không mơ hồ hoặc một key object/KeyGenerator. Không ghép các chuỗi tùy tiện nếu delimiter có thể xuất hiện trong dữ liệu đầu vào.

Không đưa thông tin nhạy cảm vào key nếu cache backend, metrics hoặc log có thể hiển thị key. Có thể dùng identifier đã chuẩn hóa hoặc hash khi phù hợp.

## 17. Dùng condition và unless

@Cacheable có thể quyết định có cache hay không:

~~~java
@Cacheable(
    cacheNames = "productBySku",
    key = "#p0",
    condition = "#p0 != null && !#p0.isBlank()",
    unless = "#result == null"
)
public ProductView getBySku(String sku) {
    // Đọc dữ liệu.
}
~~~

- condition được đánh giá trước khi method chạy; false nghĩa là không dùng cache cho lần gọi đó.
- unless được đánh giá sau khi method chạy; true nghĩa là không lưu kết quả vừa trả về.

Trong ví dụ service chính, method ném ProductNotFoundException khi không tìm thấy, nên exception không trở thành cache value. Nếu method trả null cho trường hợp không tồn tại, unless có thể ngăn cache null nếu cache provider hỗ trợ chính sách tương ứng.

Không nên cache kết quả lỗi hoặc trạng thái thiếu dữ liệu quá lâu nếu bản ghi có thể vừa được tạo. Nếu muốn negative caching (cache kết quả không tìm thấy), hãy thiết kế một biểu diễn rõ ràng và TTL ngắn hơn dữ liệu tồn tại.

## 18. Cache miss, negative caching và dữ liệu vừa được tạo

Cache-aside thường chỉ lưu kết quả thành công. Nếu key không có dữ liệu, mỗi request có thể tiếp tục truy vấn database. Khi có nhiều request hỏi một SKU không tồn tại, database vẫn chịu tải.

Negative caching lưu trạng thái "không tìm thấy" trong một khoảng ngắn. Nó có ích khi request lặp lại cho key không tồn tại, ví dụ bot hoặc client gọi sai ID liên tục.

Tuy nhiên, negative cache có rủi ro: sản phẩm có thể vừa được tạo nhưng cache vẫn giữ trạng thái không tồn tại. Khi tạo entity mới, cần evict negative entry tương ứng; TTL cũng nên ngắn.

Không dùng null như một trạng thái mơ hồ nếu API cần phân biệt:
- Chưa từng truy vấn.
- Đã truy vấn và không tìm thấy.
- Có dữ liệu nhưng trường cụ thể là null.

Dùng một result type rõ ràng, ví dụ sealed result hoặc DTO trạng thái, nếu nghiệp vụ cần phân biệt các trường hợp đó.

## 19. Invalidation: xóa cache khi dữ liệu thay đổi

Cache-aside thường dùng invalidation: sau khi dữ liệu nguồn thay đổi thành công, xóa key liên quan. Lần đọc tiếp theo sẽ miss và nạp dữ liệu mới.

Spring cung cấp @CacheEvict:

~~~java
@CacheEvict(cacheNames = "productBySku", key = "#p0")
public void evictProduct(String sku) {
}
~~~

Hoặc xóa toàn bộ region:

~~~java
@CacheEvict(cacheNames = "productBySku", allEntries = true)
public void evictAllProducts() {
}
~~~

allEntries = true có thể hữu ích khi thay đổi ảnh hưởng nhiều key nhưng làm giảm cache hit trên toàn region. Chỉ dùng khi không thể xác định tập key bị ảnh hưởng hoặc khi region đủ nhỏ.

Không xóa cache trước khi biết thao tác ghi có thành công hay không, trừ khi chủ đích là invalidation ngay cả khi method thất bại. Với transaction database, cần cân nhắc thời điểm eviction so với commit.

## 20. Evict sau khi transaction commit

Nếu xóa cache trước khi transaction database commit, request khác có thể miss cache rồi đọc dữ liệu cũ từ database trong lúc transaction cập nhật chưa commit. Sau đó dữ liệu cũ lại được ghi vào cache.

Một cách rõ ràng là phát event trong transaction và chỉ evict sau commit:

Event:

~~~java
package com.example.product;

public record ProductChanged(String sku) {
}
~~~

Trong ProductCatalogService, phương thức changePrice() đã cập nhật entity managed rồi publish ProductChanged. Listener:

~~~java
package com.example.product;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class ProductCacheInvalidator {

    @CacheEvict(cacheNames = "productBySku", key = "#p0.sku()")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onProductChanged(ProductChanged event) {
    }
}
~~~

Listener chỉ chạy sau khi transaction commit thành công. Nếu transaction rollback, event listener ở phase AFTER_COMMIT không thực hiện eviction.

Cách này phù hợp với cache trong cùng ứng dụng. Với Redis hoặc nhiều service, cần đảm bảo event invalidation được phát tới mọi instance. Nếu mất event là không chấp nhận được, dùng outbox/retry hoặc cơ chế đồng bộ đáng tin cậy; TTL chỉ là lớp giới hạn độ cũ dự phòng.

Nếu một thao tác thay đổi SKU hoặc key của entity, cần evict cả key cũ và key mới nếu cache có thể chứa cả hai. Khi một thay đổi ảnh hưởng nhiều view, phải xác định tất cả cache region liên quan.

## 21. Invalidation khó hơn TTL

TTL giải quyết việc entry tự hết hạn sau một khoảng. Invalidation giải quyết việc xóa ngay khi có thay đổi được biết đến.

Hai cách có thể kết hợp:

- TTL ngắn để giới hạn độ cũ tối đa theo chính sách.
- Event invalidation để cập nhật nhanh khi ghi.
- Refresh nền để giảm cache miss cho key nóng.
- Version key để tách cache cũ và mới khi dữ liệu thay đổi theo version.

TTL không thay thế invalidation nếu nghiệp vụ cần cập nhật nhanh. Invalidation cũng không thay thế TTL nếu event có thể bị mất hoặc một writer ngoài ứng dụng không phát event.

Một race condition vẫn có thể xảy ra: request A đọc dữ liệu cũ từ database, request B commit dữ liệu mới và evict cache, sau đó A mới ghi kết quả cũ vào cache. Nếu cần tránh tình huống này, cần phối hợp version/fencing token, lock, kiểm tra lại version hoặc chiến lược đồng bộ mạnh hơn. TTL đơn thuần chỉ giới hạn thời gian tồn tại của giá trị cũ, không loại bỏ race.

## 22. @CachePut và @CacheEvict khác @Cacheable thế nào?

~~~java
@Cacheable(cacheNames = "productBySku", key = "#p0")
public ProductView getBySku(String sku) {
    // Chỉ chạy method khi cache miss.
}
~~~

~~~java
@CachePut(cacheNames = "productBySku", key = "#result.sku()")
public ProductView reloadProduct(String sku) {
    // Luôn chạy method rồi ghi kết quả vào cache.
}
~~~

~~~java
@CacheEvict(cacheNames = "productBySku", key = "#p0")
public void removeProductCache(String sku) {
    // Xóa key.
}
~~~

Khác biệt:

| Annotation | Có chạy method? | Hành động cache |
|---|---|---|
| @Cacheable | Chỉ khi miss hoặc condition không dùng cache | Đọc cache, lưu kết quả khi cần |
| @CachePut | Luôn chạy | Ghi đè value bằng kết quả method |
| @CacheEvict | Luôn chạy theo luồng method | Xóa key hoặc region |

Không gắn @Cacheable và @CachePut lên cùng method nếu chưa hiểu rõ thứ tự và mục đích; hai annotation có ý nghĩa khác nhau. Với method ghi database, hãy bảo đảm cache update/eviction không xảy ra trước khi transaction commit theo cách gây dữ liệu cũ.

## 23. Cache stampede và nhiều request cùng miss

Cache stampede xảy ra khi một key phổ biến hết hạn hoặc bị xóa, rồi nhiều request cùng lúc miss và đồng loạt truy vấn database.

Hậu quả:
- Database nhận một đợt tải đột biến.
- Nhiều request cùng thực hiện một phép tính đắt.
- Latency tăng, timeout và retry có thể khuếch đại tải.
- Cache được nạp lại nhiều lần với cùng một dữ liệu.

Các biện pháp:

1. Single-flight/locking: chỉ một request nạp key, các request khác chờ hoặc dùng kết quả sau khi nạp xong.
2. TTL jitter: tránh nhiều key hết hạn cùng thời điểm.
3. Refresh ahead: làm mới key nóng trước khi hết hạn.
4. Stale-while-revalidate: tạm trả dữ liệu cũ trong ngân sách cho phép trong lúc làm mới nền.
5. Rate limit hoặc bulkhead cho đường tải cache miss.
6. Cache warming có chọn lọc cho key phổ biến sau deploy.

Spring @Cacheable có thuộc tính sync=true để yêu cầu đồng bộ việc tải cùng key ở một số cache provider:

~~~java
@Cacheable(
    cacheNames = "productBySku",
    key = "#p0",
    sync = true
)
public ProductView getBySku(String sku) {
    // Một lần tải được đồng bộ theo khả năng cache provider.
}
~~~

Khả năng đồng bộ và giới hạn của sync phụ thuộc Cache implementation. Nó không mặc nhiên là distributed lock giữa mọi JVM cho mọi provider. Kiểm tra tài liệu cache manager đang dùng trước khi dựa vào tính năng này.

## 24. Cache local hay cache phân tán?

| Tiêu chí | Caffeine local | Redis/distributed cache |
|---|---|---|
| Độ trễ | Rất thấp, cùng JVM | Có network round trip |
| Chia sẻ giữa instance | Không | Có |
| Invalidation | Cần xử lý từng instance | Có thể dùng chung key hoặc pub/sub |
| Bộ nhớ | Heap của từng instance | Bộ nhớ ngoài ứng dụng |
| Serialization | Thường giữ object trong JVM | Cần định dạng/serialization phù hợp |
| Vận hành | Đơn giản hơn | Cần vận hành và giám sát hệ thống cache |
| Phù hợp | Cache dữ liệu nóng, phạm vi instance | Cache dùng chung nhiều replica/service |

Caffeine phù hợp với dữ liệu đọc nhiều và có thể chấp nhận mỗi instance tự làm mới. Redis phù hợp khi nhiều instance cần dùng chung cache hoặc cần key tồn tại độc lập với vòng đời JVM.

Distributed cache không tự giải quyết consistency. Nó chỉ chia sẻ nơi lưu key/value; ứng dụng vẫn cần thiết kế TTL, invalidation, key version, retry và xử lý cache backend unavailable.

## 25. Cache page và kết quả tìm kiếm

Có thể cache kết quả tìm kiếm hoặc Page, nhưng key phải bao gồm mọi yếu tố ảnh hưởng kết quả:

- Bộ lọc.
- Page number và page size.
- Sort field và direction.
- Tenant/organization.
- Locale/currency nếu nội dung phụ thuộc.
- Quyền truy cập nếu kết quả đã được lọc theo user/role.

Ví dụ hai request cùng filter nhưng page size khác nhau không được dùng chung cache key. Tương tự, cùng page number nhưng sort khác nhau cũng là hai kết quả khác nhau.

Search result có cardinality lớn, key ít lặp và invalidation khó. Không cache mọi tổ hợp filter một cách mặc định. Chỉ cache các truy vấn phổ biến, có reuse rõ ràng và có thể giới hạn số key.

Với Page, totalElements cũng có thể thay đổi khi dữ liệu được thêm/xóa. Nếu cache content và count cùng nhau, phải chấp nhận độ cũ của cả hai. Nếu tổng số là thông tin cần mới hơn content, cân nhắc cache hai phần riêng hoặc không cache Page.

Không cache entity page chứa lazy association chưa được tải. DTO projection thường dễ serialization và có hợp đồng rõ ràng hơn.

## 26. Cache và bảo mật dữ liệu

Cache key phải bao gồm mọi ngữ cảnh bảo mật ảnh hưởng kết quả. Nếu kết quả khác nhau theo tenant, user, role, locale hoặc quyền, không dùng một key chung.

Ví dụ rủi ro:
- User A có quyền xem trường nội bộ; User B không có quyền.
- Hai tenant có cùng SKU nhưng dữ liệu sản phẩm khác nhau.
- Một response được cá nhân hóa theo currency hoặc region.
- Quyền user bị thu hồi nhưng cache vẫn trả kết quả đã cấp trước đó.

Nếu không thể đưa ngữ cảnh bảo mật vào key và invalidation một cách đáng tin cậy, không cache kết quả đã cá nhân hóa. Có thể cache dữ liệu nền dùng chung rồi áp dụng authorization sau khi đọc.

Không lưu secret, token hoặc thông tin nhạy cảm vào cache key/value nếu không có nhu cầu rõ ràng và biện pháp bảo vệ phù hợp. Cache Redis cũng cần authentication, network policy và kiểm soát truy cập như database.

## 27. Cache và dữ liệu thay đổi ngoài ứng dụng

Spring Cache hoặc Hibernate không tự biết mọi thay đổi trong database. Dữ liệu có thể bị cập nhật bởi:

- Một service khác.
- Job batch hoặc scheduler.
- SQL script vận hành.
- Stored procedure.
- Người quản trị database.
- CDC hoặc pipeline đồng bộ.

Nếu các writer này không phát invalidation event, cache có thể giữ dữ liệu cũ cho tới khi TTL hết hạn hoặc bị xóa thủ công.

Trước khi cache một bảng, liệt kê tất cả writer và cách chúng thông báo thay đổi. Nếu không kiểm soát được writer, chọn TTL phù hợp với staleness budget, dùng CDC/event invalidation hoặc tránh cache dữ liệu yêu cầu mới nhất.

Đặc biệt với second-level cache, cập nhật trực tiếp database ngoài Hibernate có thể khiến provider không biết region nào cần invalidation.

## 28. Theo dõi hiệu quả và vận hành cache

Một cache cần metrics và cảnh báo. Các chỉ số hữu ích:

| Chỉ số | Ý nghĩa |
|---|---|
| Hit ratio | Tỷ lệ request lấy được từ cache |
| Miss rate | Tần suất phải tải nguồn |
| Load latency | Thời gian nạp value khi miss |
| Eviction count | Số entry bị loại do giới hạn/expiration |
| Cache size/weight | Bộ nhớ đang sử dụng |
| Expiration rate | Số entry hết hạn |
| Backend errors | Lỗi kết nối/đọc/ghi cache |
| Hot keys | Key có tần suất truy cập rất cao |
| Stampede/concurrent loads | Nhiều request cùng nạp một key |
| Staleness/age | Tuổi dữ liệu hoặc thời gian từ lần refresh |

Hit ratio cao chưa chắc tốt nếu dữ liệu cũ hoặc cache giữ quá nhiều dữ liệu không cần thiết. Hit ratio thấp cũng chưa chắc xấu nếu cache chỉ phục vụ một vài truy vấn cực đắt.

Theo dõi đồng thời database QPS, query latency, API latency và heap. Mục tiêu là cải thiện trải nghiệm và tải hệ thống mà vẫn đáp ứng freshness budget.

Có thể dùng actuator/cache metrics và metrics của provider. Tên metric cụ thể phụ thuộc Spring Boot, Micrometer và cache backend phiên bản đang dùng.

## 29. Kiểm thử cache

Kiểm thử nên xác nhận cả cache hit và invalidation, không chỉ kiểm tra method trả đúng dữ liệu.

Các tình huống cần kiểm tra:

1. Lần đọc đầu gọi repository và tạo cache entry.
2. Lần đọc tiếp theo cùng key trả kết quả cache.
3. Key khác không dùng nhầm entry.
4. Thay đổi dữ liệu phát invalidation sau commit.
5. Transaction rollback không xóa cache theo event AFTER_COMMIT.
6. Key theo tenant/locale không bị trộn.
7. Entry hết TTL được nạp lại.
8. Cache backend lỗi được xử lý theo chính sách ứng dụng.
9. Nhiều request đồng thời miss không gây tải không kiểm soát.

Ví dụ test kiểm tra entry được lưu:

~~~java
@SpringBootTest
class ProductCacheTest {

    @Autowired
    private ProductCatalogService service;

    @Autowired
    private ProductRepository repository;

    @Autowired
    private CacheManager cacheManager;

    @BeforeEach
    void prepare() {
        cacheManager.getCache("productBySku").clear();
        repository.deleteAll();
        repository.save(new Product(
                "SKU-100",
                "Keyboard",
                new BigDecimal("49.90"),
                Instant.parse("2026-01-01T00:00:00Z")
        ));
    }

    @Test
    void cachesProductViewBySku() {
        ProductView first = service.getBySku("SKU-100");

        Cache.ValueWrapper cached =
                cacheManager.getCache("productBySku").get("SKU-100");

        assertThat(first.name()).isEqualTo("Keyboard");
        assertThat(cached).isNotNull();
        assertThat(cached.get()).isEqualTo(first);
    }
}
~~~

Các import chính cho test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
~~~

Test này giả định ProductCacheTest nằm trong package com.example.product, cùng package với Product, ProductView và service. Ứng dụng phải có CacheConfiguration, database test và Spring Cache được bật.

Để chứng minh repository không bị gọi lần thứ hai, có thể dùng spy/mock repository trong một test slice phù hợp hoặc kiểm tra SQL statement count bằng datasource proxy. Để kiểm tra invalidation AFTER_COMMIT, cần commit transaction thật trong test; một test transaction tự rollback mặc định sẽ không kích hoạt phase AFTER_COMMIT như một transaction commit thành công.

## 30. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dữ liệu cũ quá lâu | TTL quá dài hoặc thiếu invalidation | Xác định staleness budget và evict khi ghi |
| Cache hit thấp | Key quá đa dạng hoặc TTL quá ngắn | Đo phân bố key và điều chỉnh phạm vi cache |
| Database vẫn quá tải khi key hết hạn | Cache stampede | Single-flight, refresh ahead hoặc jitter |
| User nhận dữ liệu của tenant khác | Cache key thiếu tenant | Đưa tenant vào key hoặc không cache kết quả đó |
| API trả entity lỗi sau transaction | Cache JPA entity/proxy có lazy association | Cache DTO/read model |
| Cache bị xóa trước commit | Invalidation chạy sai thời điểm transaction | Evict sau commit |
| Cache không đổi sau SQL trực tiếp | Writer ngoài ứng dụng không phát event | CDC/invalidation hoặc TTL phù hợp |
| Nhiều instance trả dữ liệu khác nhau | Local cache mỗi JVM có trạng thái riêng | Đồng bộ invalidation hoặc dùng distributed cache |
| Cache page sai sort/filter | Key thiếu tham số truy vấn | Bao gồm toàn bộ input ảnh hưởng kết quả |
| Cache chiếm quá nhiều heap | Không giới hạn số entry/value | maximumSize/weight, TTL và metrics |
| Negative cache giữ trạng thái không tồn tại | Entity vừa được tạo nhưng miss entry chưa hết hạn | Evict khi tạo hoặc dùng TTL ngắn |
| @Cacheable không hoạt động | Self-invocation hoặc caching chưa bật | Gọi qua Spring proxy và bật @EnableCaching |
| @CachePut cập nhật value cũ | Cache ghi trước transaction commit | Đồng bộ cache update sau commit |
| Query cache không cải thiện hiệu năng | Query ít lặp hoặc invalidation thường xuyên | Đo workload và chỉ bật cho query phù hợp |

## 31. Quy trình chọn cache cho một use case

Có thể áp dụng quy trình sau:

1. Xác định use case và dữ liệu được trả về.
2. Đo query latency, tần suất đọc, tần suất ghi và số key khác nhau.
3. Xác định ai là writer và mọi đường cập nhật dữ liệu.
4. Đặt staleness budget cùng hậu quả nếu dữ liệu cũ.
5. Chọn cache layer: Spring Cache, JPA second-level, query cache hoặc không cache.
6. Thiết kế DTO/key, gồm tenant và mọi tham số ảnh hưởng kết quả.
7. Chọn TTL, maximum size/weight và chiến lược invalidation.
8. Xử lý cache stampede và cache backend unavailable.
9. Viết test cho hit, miss, invalidation, rollback và isolation giữa key.
10. Theo dõi metrics và điều chỉnh bằng dữ liệu production.

Nếu dữ liệu cần consistency mạnh, cache có thể chỉ phù hợp cho hiển thị hoặc đọc tham khảo. Thao tác quyết định cuối cùng vẫn cần xác nhận trên nguồn dữ liệu có thẩm quyền.

## 32. Checklist tự đánh giá

- [ ] Phân biệt first-level cache, second-level cache, query cache và Spring Cache.
- [ ] Hiểu persistence context chỉ chia sẻ entity trong phạm vi EntityManager.
- [ ] Biết JPA @Cacheable khác Spring @Cacheable.
- [ ] Chọn dữ liệu có read reuse cao và chi phí tải đáng kể.
- [ ] Xác định mọi writer và tần suất cập nhật.
- [ ] Đặt freshness/staleness budget trước khi chọn TTL.
- [ ] Phân biệt expire-after-write và expire-after-access.
- [ ] Giới hạn kích thước cache và bộ nhớ.
- [ ] Dùng DTO/read model khi cache kết quả service.
- [ ] Thiết kế key gồm tenant, locale, quyền và filter khi có ảnh hưởng.
- [ ] Dùng @Cacheable, @CachePut và @CacheEvict đúng mục đích.
- [ ] Evict sau commit khi transaction consistency yêu cầu.
- [ ] Có chiến lược cho negative caching và dữ liệu vừa được tạo.
- [ ] Nhận diện cache stampede và chọn biện pháp giảm tải.
- [ ] Phân biệt cache local và distributed.
- [ ] Kiểm soát invalidation từ batch job hoặc writer ngoài ứng dụng.
- [ ] Theo dõi hit ratio, miss, eviction, latency, size và backend errors.
- [ ] Kiểm thử cache hit, miss, expiry, invalidation và transaction rollback.
- [ ] Không cache dữ liệu có yêu cầu freshness/authorization không thể đáp ứng.

## 33. Kết luận

Chọn cache bắt đầu từ đặc tính dữ liệu và yêu cầu nghiệp vụ. Dữ liệu đọc nhiều, ít thay đổi, tốn chi phí tải và có thể chấp nhận một mức trễ thường là ứng viên tốt. Dữ liệu biến động liên tục, nhạy cảm hoặc quyết định giao dịch cần được xử lý bằng cơ chế nhất quán phù hợp.

Hãy đặt staleness budget trước khi chọn TTL; kết hợp TTL với invalidation khi cần cập nhật nhanh; thiết kế key đầy đủ; cache DTO phù hợp; và kiểm soát cache stampede. Phân biệt Spring Cache với first-level, second-level và query cache của JPA/Hibernate để chọn đúng tầng. Cuối cùng, đo hit/miss, latency, memory và lỗi backend để xác nhận cache thực sự cải thiện hệ thống mà vẫn giữ dữ liệu trong giới hạn cũ mà nghiệp vụ chấp nhận.
