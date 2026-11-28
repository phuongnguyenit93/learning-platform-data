# Cache kết quả ở tầng ứng dụng và vô hiệu hóa khi đồ thị thay đổi

Một truy vấn graph có thể phải đi qua nhiều relationship, gom nhóm dữ liệu từ nhiều node hoặc tính toán kết quả tổng hợp. Nếu cùng một kết quả được đọc lặp lại trong thời gian ngắn, ứng dụng có thể cache kết quả ở tầng service để giảm số lần truy vấn Neo4j và rút ngắn thời gian phản hồi.

Khó khăn lớn nhất không phải là lưu kết quả vào cache, mà là giữ kết quả đó nhất quán khi graph thay đổi. Cập nhật một node có thể làm thay đổi nhiều projection; thêm hoặc xóa một relationship có thể làm thay đổi kết quả traversal, đường đi và số lượng node tiếp cận được. Vì vậy, cache key cần mô tả đầy đủ truy vấn, còn chính sách invalidation phải gắn với mọi đường ghi dữ liệu trong ứng dụng.

Spring Data Neo4j (SDN) không tự động duy trì application result cache cho repository. Có thể dùng Spring Cache abstraction ở service, kết hợp `@Cacheable`, `@CachePut`, `@CacheEvict`, cache provider có TTL và event sau commit để điều khiển vòng đời kết quả.

## 1. Phân biệt application cache với cache bên trong Neo4j

Có nhiều lớp cache khác nhau và chúng giải quyết các vấn đề khác nhau:

| Cơ chế | Cache gì? | Ai quản lý? |
|---|---|---|
| Application result cache | DTO, projection hoặc kết quả nghiệp vụ đã tính toán | Ứng dụng, Spring Cache, Caffeine, Redis hoặc provider khác |
| Neo4j page cache | Các page dữ liệu graph trên storage được đọc thường xuyên | Neo4j DBMS |
| Cypher query cache | Kế hoạch thực thi (execution plan) của câu Cypher | Neo4j DBMS |
| Driver connection pool | Kết nối Bolt được tái sử dụng | Neo4j Java Driver |

Neo4j query cache không lưu sẵn danh sách kết quả của một câu `MATCH`. Page cache cũng không lưu DTO đã ánh xạ cho service. Application cache lưu chính kết quả mà ứng dụng muốn trả lại, ví dụ `PersonSummary`, danh sách sản phẩm liên quan hoặc số lượng người trong mạng lưới ba bước.

Không dùng application cache để thay thế index, constraint, query tuning hoặc page cache. Trước khi cache, hãy xác nhận truy vấn có kế hoạch thực thi tốt bằng `EXPLAIN`/`PROFILE` và chỉ cache khi có tỷ lệ đọc lặp lại đủ lớn.

## 2. Chọn dữ liệu phù hợp để cache

Những kết quả thường phù hợp:

- DTO tổng hợp từ nhiều node và relationship.
- Danh sách tham chiếu ít thay đổi như danh mục, loại quan hệ hoặc cấu hình.
- Kết quả traversal có chi phí cao và được nhiều request hỏi lại.
- Projection hiển thị hồ sơ, thống kê hoặc thông tin tổng quan.
- Kết quả tính toán có thể chấp nhận độ trễ cập nhật trong một khoảng TTL xác định.

Những dữ liệu cần cân nhắc kỹ:

- Trạng thái giao dịch hoặc quyền truy cập cần nhất quán tức thời.
- Kết quả graph thay đổi thường xuyên theo từng request.
- Query trả về quá nhiều node/relationship khiến cache chiếm nhiều bộ nhớ.
- Kết quả phụ thuộc user, tenant, locale hoặc quyền nhưng cache key không chứa các yếu tố đó.
- Entity graph có quan hệ chưa được nạp đầy đủ hoặc chỉ là kết quả một phần của custom query.

Ưu tiên cache DTO bất biến hoặc projection dành cho read model. Không nên giữ một domain entity SDN đã được nạp trong một trạng thái graph không đầy đủ rồi chia sẻ nó qua nhiều request. DTO cache có schema rõ ràng, kích thước dễ kiểm soát và không vô tình được dùng làm aggregate để ghi ngược trở lại Neo4j.

## 3. Cache-aside với Spring Cache

Cache-aside là cách triển khai phổ biến:

1. Service tra cache theo key.
2. Nếu có dữ liệu, trả kết quả cache.
3. Nếu cache miss, đọc Neo4j.
4. Đưa kết quả vào cache và trả cho caller.
5. Khi graph thay đổi, evict những key bị ảnh hưởng.

Spring Cache cung cấp abstraction thống nhất cho nhiều cache provider. Bật caching bằng `@EnableCaching`:

```java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CachingEnabledConfiguration {
}
```

Service dùng `@Cacheable`:

```java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class PersonQueryService {
    private final PersonRepository repository;

    public PersonQueryService(PersonRepository repository) {
        this.repository = repository;
    }

    @Cacheable(
        cacheNames = "personSummary",
        key = "#tenantId + ':' + #personCode"
    )
    public PersonSummary getSummary(String tenantId, String personCode) {
        return repository.findSummary(personCode)
            .orElseThrow(() -> new PersonNotFoundException(personCode));
    }
}
```

`PersonSummary` là DTO dành cho màn hình đọc, không phải entity cần lưu lại:

```java
public record PersonSummary(
    String code,
    String name,
    String companyName
) {
}
```

Repository có thể khai báo `findSummary(String code)` bằng `@Query` và trả `Optional<PersonSummary>`. Cache service không phụ thuộc cách repository tạo projection, miễn là kết quả có kiểu ổn định và cache key chứa đủ tham số.

Khi key chưa có trong cache, method được gọi và kết quả được lưu. Với lần gọi sau cùng key, Spring trả giá trị cache và bỏ qua method. Ví dụ giả định `tenantId` là tenant đã được xác thực và `PersonSummary` là DTO đọc.

`tenantId` trong key chỉ cô lập entry cache; nó không tự chọn Neo4j database. Database selection vẫn phải được thực hiện bằng cấu hình tĩnh hoặc provider/tenant context tương ứng, và hai ngữ cảnh phải khớp nhau.

Các biểu thức SpEL dùng tên tham số như `#tenantId` và `#personCode` khi tên tham số được giữ trong bytecode (ví dụ biên dịch Java với tùy chọn `-parameters`). Nếu dự án không giữ tên tham số, có thể dùng chỉ số như `#p0` và `#p1`, hoặc cấu hình `KeyGenerator` riêng.

Spring Cache sử dụng proxy/interceptor. Vì vậy, method được cache phải được gọi qua Spring bean proxy; self-invocation như `this.getSummary(...)` trong cùng object không đi qua proxy mặc định và có thể bỏ qua cache annotation. Không gọi trực tiếp method nội bộ rồi kỳ vọng `@Cacheable` luôn được áp dụng.

## 4. Thiết kế cache key cho dữ liệu graph

Cache key phải phân biệt mọi yếu tố có thể làm thay đổi kết quả. Với truy vấn graph, chỉ dùng node ID thường là chưa đủ.

Ví dụ key của `PersonSummary` có thể gồm:

```text
tenantId : personCode : projectionVersion
```

Với truy vấn mạng lưới quan hệ, key có thể gồm:

```text
tenantId : sourceCode : relationshipType : direction : maxDepth : statusFilter
```

Với kết quả tìm kiếm có phân trang:

```text
tenantId : normalizedQuery : sort : page : size : locale : accessScope
```

Các nguyên tắc quan trọng:

1. **Tenant/database:** cùng một mã node có thể tồn tại ở nhiều database. Key phải chứa tenant hoặc database identity.
2. **Tham số truy vấn:** gồm source, target, loại relationship, chiều traversal, giới hạn hop và filter.
3. **Projection:** kết quả DTO khác nhau cần key khác nhau hoặc cache riêng.
4. **Phân trang/sắp xếp:** page, size và sort làm thay đổi danh sách kết quả.
5. **Quyền truy cập:** nếu kết quả bị lọc theo role hoặc access scope, key phải phân biệt các scope đó.
6. **Locale/format:** chỉ thêm nếu nội dung cache phụ thuộc locale hoặc định dạng.
7. **Phiên bản schema:** có thể thêm version vào key khi DTO hoặc cách tính kết quả thay đổi giữa các lần triển khai.

Không dùng chuỗi key ghép từ object tùy ý nếu `toString()` không ổn định. Với key phức tạp, tạo kiểu key bất biến hoặc `KeyGenerator` riêng. Đừng đưa dữ liệu nhạy cảm như access token vào key; dùng một mã tenant hoặc access scope không bí mật.

## 5. Cấu hình cache provider và TTL

`ConcurrentMapCacheManager` hữu ích cho ví dụ hoặc ứng dụng đơn giản, nhưng không cung cấp TTL tự động, giới hạn kích thước hay chia sẻ cache giữa nhiều instance. Với production, thường chọn cache có eviction policy rõ ràng như Caffeine cho một instance hoặc Redis cho nhiều application instance.

Ví dụ Caffeine với giới hạn kích thước và TTL:

Đây là cấu hình thay thế cho ví dụ `ConcurrentMapCacheManager` ở phần transaction-aware cache bên dưới. Trong ứng dụng, chỉ cần một bean `CacheManager` chính được dùng bởi Spring Cache.

```java
import java.time.Duration;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CaffeineCacheConfiguration {

    @Bean
    CacheManager cacheManager() {
        CaffeineCacheManager manager = new CaffeineCacheManager(
            "personSummary",
            "personNeighborhood",
            "companyOverview"
        );
        manager.setCaffeine(Caffeine.newBuilder()
            .maximumSize(20_000)
            .expireAfterWrite(Duration.ofMinutes(5)));
        return manager;
    }
}
```

Ví dụ cần dependency Spring Cache Caffeine và Caffeine tương thích với Spring Boot/Spring Framework của dự án. `maximumSize` giới hạn số entry; `expireAfterWrite` đặt TTL tính từ lần ghi gần nhất. Chọn TTL dựa trên mức chấp nhận dữ liệu cũ và tần suất thay đổi graph.

TTL là lưới an toàn khi invalidation bị bỏ sót, nhưng không thay thế invalidation cho dữ liệu cần cập nhật nhanh. TTL dài giảm tải database nhưng tăng thời gian dữ liệu có thể cũ; TTL ngắn giảm độ cũ nhưng tăng cache miss.

## 6. Evict cache khi cập nhật một node

Khi một hồ sơ thay đổi, có thể evict summary của node đó:

```java
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonCommandService {
    private final PersonRepository repository;

    public PersonCommandService(PersonRepository repository) {
        this.repository = repository;
    }

    @Transactional
    @CacheEvict(
        cacheNames = "personSummary",
        key = "#tenantId + ':' + #personCode"
    )
    public void rename(
            String tenantId,
            String personCode,
            String newName) {
        Person person = repository.findById(personCode)
            .orElseThrow(() -> new PersonNotFoundException(personCode));
        person.setName(newName);
        repository.save(person);
    }
}
```

`@CacheEvict` mặc định evict sau khi method invocation hoàn tất thành công (`beforeInvocation = false`). Nếu method ném exception, thao tác eviction mặc định không được thực hiện. Tuy nhiên, method có thể chạy bên trong một transaction lớn hơn và transaction đó chỉ commit sau khi method trả về. Vì vậy, “sau method” không đồng nghĩa “sau database commit”. Phần transaction-aware cache bên dưới giải quyết ranh giới này.

Nếu dữ liệu summary được cache dưới nhiều cache name hoặc nhiều key, cần evict tất cả entry liên quan. Không nên chỉ evict cache key hồ sơ trong khi vẫn giữ cache `personNeighborhood` hoặc `companyOverview` phụ thuộc vào tên người đó.

## 7. @CachePut và @CacheEvict khác nhau

| Annotation | Hành vi | Khi dùng |
|---|---|---|
| `@Cacheable` | Đọc cache; chỉ gọi method khi cache miss | Query/read model |
| `@CachePut` | Luôn gọi method rồi đưa kết quả vào cache | Ghi mới kết quả đã tính lại, khi chắc chắn key và dữ liệu đầy đủ |
| `@CacheEvict` | Xóa entry khỏi cache | Sau thao tác làm kết quả cũ không còn hợp lệ |
| `@Caching` | Kết hợp nhiều cache operation trên một method | Một mutation ảnh hưởng nhiều cache |

Ví dụ `@CachePut`:

```java
import org.springframework.cache.annotation.CachePut;

@CachePut(
    cacheNames = "personSummary",
    key = "#tenantId + ':' + #result.code"
)
public PersonSummary refreshSummary(String tenantId, String personCode) {
    return repository.findSummary(personCode)
        .orElseThrow(() -> new PersonNotFoundException(personCode));
}
```

`@CachePut` không bỏ qua method khi cache hit. Nó luôn thực thi method rồi thay giá trị cache bằng kết quả trả về. Không gắn `@Cacheable` và `@CachePut` lên cùng một method nếu không có semantics rõ ràng; hai annotation có mục tiêu khác nhau và dễ gây hành vi khó hiểu.

Với lệnh ghi graph, evict thường an toàn hơn put vì một mutation có thể làm thay đổi nhiều projection mà service không tính lại đầy đủ. Dùng `@CachePut` khi method thực sự trả về read model hoàn chỉnh và không còn key phụ thuộc bị bỏ sót.

## 8. Một mutation có thể ảnh hưởng nhiều cache

Trong graph, tác động của thay đổi không chỉ nằm ở node được cập nhật.

Ví dụ:

```text
(Person)-[:WORKS_AT]->(Company)
    |
    +-- [:KNOWS] --> (Person)
```

- Đổi tên `Person` ảnh hưởng `personSummary`, danh sách nhân viên của công ty và kết quả tìm kiếm theo tên.
- Thêm/xóa `WORKS_AT` ảnh hưởng hồ sơ công ty, danh sách nhân viên và thống kê headcount.
- Thêm/xóa `KNOWS` ảnh hưởng neighborhood, số bước tới node khác và kết quả shortest path.
- Đổi trạng thái `Company` có thể ảnh hưởng danh sách công ty hoạt động và mọi query lọc người theo công ty.

Hãy lập bản đồ dependency từ query/read model tới node label, relationship type và property mà nó phụ thuộc. Khi một mutation xảy ra, xác định cache nào cần invalidation.

| Mutation | Cache có thể bị ảnh hưởng |
|---|---|
| Đổi `Person.name` | `personSummary`, search result, person list, company member display |
| Đổi `Person.status` | person summary, active-person traversal, recommendation |
| Tạo/xóa `KNOWS` | neighborhood, reachability, shortest path, mutual connections |
| Tạo/xóa `WORKS_AT` | company overview, employee list, organization graph |
| Xóa `Company` | company detail, employee membership, company search |

Không phải lúc nào cũng có thể tính chính xác tất cả key bị ảnh hưởng. Với truy vấn traversal rộng, một relationship mới có thể làm thay đổi nhiều kết quả ở nhiều source node. Khi invalidation chính xác quá phức tạp, dùng eviction theo vùng/tenant hoặc version namespace kết hợp TTL.

## 9. Evict nhiều cache bằng @Caching

Spring Cache cho phép một mutation evict nhiều cache:

```java
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Caching;
import org.springframework.transaction.annotation.Transactional;

@Transactional
@Caching(evict = {
    @CacheEvict(
        cacheNames = "personSummary",
        key = "#tenantId + ':' + #personCode"
    ),
    @CacheEvict(
        cacheNames = "personNeighborhood",
        key = "#tenantId + ':' + #personCode"
    ),
    @CacheEvict(
        cacheNames = "personSearch",
        allEntries = true
    )
})
public void updatePerson(
        String tenantId,
        String personCode,
        PersonUpdate command) {
    // Load, validate and persist the changed entity.
}
```

Ví dụ evict toàn bộ `personSearch` vì thay đổi tên có thể ảnh hưởng nhiều search key. Cách này đơn giản nhưng có thể làm cache miss tăng mạnh. Chỉ dùng `allEntries = true` khi phạm vi cache đủ nhỏ hoặc invalidation chính xác không đáng tin cậy.

`@CacheEvict(allEntries = true)` xóa toàn bộ entry của cache name đó, không chỉ key của một tenant. Nếu cache dùng chung nhiều tenant, cần thiết kế cache name riêng hoặc dùng key namespace/version theo tenant để tránh xóa dữ liệu của tất cả tenant.

## 10. Invalidation theo tenant hoặc theo generation

Với nhiều tenant, một mutation trong `tenant_acme` không nên làm mất cache của `tenant_globex` trừ khi cache dùng chung và không thể tách vùng. Có thể dùng cache key namespace theo tenant hoặc cache name riêng theo nhóm dữ liệu.

Một chiến lược cho query graph phụ thuộc nhiều node là generation key:

```text
personNeighborhood:
  tenant_acme : generation=17 : source=P-100 : depth=3
  tenant_globex : generation=4 : source=P-100 : depth=3
```

Khi graph của `tenant_acme` thay đổi, tăng generation của tenant đó. Các key mang generation cũ không còn được đọc; chúng tự hết hạn theo TTL. Không cần biết chính xác mọi source node nào có kết quả bị ảnh hưởng.

Generation có thể được lưu trong Redis hoặc một metadata store. Nếu nhiều instance cùng đọc/ghi, thao tác tăng generation phải atomic và được chia sẻ giữa các instance. Không dùng biến `AtomicLong` trong từng JVM như generation toàn hệ thống vì mỗi instance sẽ có giá trị khác nhau.

Nếu generation được lưu trong Neo4j, cần cân nhắc thêm chi phí đọc generation và cách đồng bộ cache. Nếu cập nhật generation cùng transaction với graph, mọi query phải đọc generation từ nguồn có consistency phù hợp trước khi sử dụng cache. Một generation cache riêng có thể bị trễ; hãy chọn mức consistency theo nghiệp vụ.

## 11. Invalidation sau khi transaction commit

Không nên xóa cache trước khi biết transaction Neo4j đã commit thành công. Nếu cache bị evict nhưng database rollback, cache miss tiếp theo có thể nạp lại dữ liệu cũ; điều đó không sai nhưng gây cache churn. Nguy hiểm hơn là ghi giá trị mới vào cache trước commit, rồi database rollback khiến cache chứa dữ liệu chưa từng được commit.

Có hai cách thường dùng để trì hoãn cache operation đến sau commit:

### Transaction-aware CacheManager

Spring cung cấp `TransactionAwareCacheManagerProxy`, bọc một `CacheManager` khác và trì hoãn các thao tác `put`, `evict`, `clear` thông thường tới sau khi transaction hiện hành commit thành công.

Ví dụ này dành cho imperative Spring transaction, vốn sử dụng transaction synchronization gắn với thread hiện tại. Với reactive transaction, hãy nối invalidation vào reactive transaction lifecycle thay vì dựa vào wrapper imperative này.

```java
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.transaction.TransactionAwareCacheManagerProxy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TransactionAwareCacheConfiguration {

    @Bean("nativeCacheManager")
    CacheManager nativeCacheManager() {
        return new ConcurrentMapCacheManager(
            "personSummary",
            "personNeighborhood",
            "companyOverview"
        );
    }

    @Bean
    CacheManager cacheManager(
            @org.springframework.beans.factory.annotation.Qualifier("nativeCacheManager")
            CacheManager nativeCacheManager) {
        return new TransactionAwareCacheManagerProxy(nativeCacheManager);
    }
}
```

Ví dụ dùng `ConcurrentMapCacheManager` để minh họa wrapper; production có thể bọc cache manager Caffeine hoặc Redis. Các thao tác cache thông thường được đăng ký đồng bộ với transaction Spring hiện hành. Nếu transaction rollback, thao tác deferred không được áp dụng.

Wrapper có giới hạn: các API có semantics tức thời như `putIfAbsent` và `evictIfPresent` không thể trì hoãn giống `put`/`evict` thông thường. Cần hiểu API mà cache provider hoặc code đang gọi. Transaction-aware cache cũng không tạo ra distributed atomic transaction giữa Neo4j và Redis; nó chỉ trì hoãn thao tác cache tới sau commit của transaction Spring.

### Application event sau commit

Có thể publish event trong transaction rồi evict cache ở listener chạy sau commit:

```java
public record PersonChangedEvent(
    String tenantId,
    String personCode
) {
}
```

Service:

```java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonChangeEventService {
    private final PersonRepository repository;
    private final ApplicationEventPublisher events;

    public PersonChangeEventService(
            PersonRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public void rename(String tenantId, String personCode, String newName) {
        Person person = repository.findById(personCode)
            .orElseThrow(() -> new PersonNotFoundException(personCode));
        person.setName(newName);
        repository.save(person);
        events.publishEvent(new PersonChangedEvent(tenantId, personCode));
    }
}
```

Listener:

```java
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class PersonCacheInvalidator {
    private final CacheManager cacheManager;

    public PersonCacheInvalidator(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onPersonChanged(PersonChangedEvent event) {
        String key = event.tenantId() + ':' + event.personCode();
        cacheManager.getCache("personSummary").evict(key);
        cacheManager.getCache("personNeighborhood").evict(key);
    }
}
```

`@TransactionalEventListener` mặc định gắn với transaction hiện hành; `AFTER_COMMIT` chỉ chạy sau commit thành công. Nếu không có transaction, listener không chạy theo mặc định trừ khi bật `fallbackExecution`.

Ví dụ listener cần kiểm tra cache tồn tại trước khi evict trong ứng dụng có cache cấu hình động. Event chỉ invalidates cache trong application context hiện tại; nhiều instance cần cơ chế phát event tới các instance khác hoặc cache dùng chung.

## 12. Cache phân tán và nhiều application instance

Cache cục bộ như Caffeine nằm trong bộ nhớ của từng JVM. Nếu ứng dụng chạy ba instance:

```text
             Neo4j
               ^
       +-------+-------+
       |       |       |
     App A   App B   App C
       |       |       |
    Cache A Cache B Cache C
```

Nếu App A cập nhật graph và chỉ evict Cache A, Cache B và Cache C vẫn có thể trả dữ liệu cũ. Có hai hướng chính:

- Dùng distributed cache như Redis để các instance đọc/evict cùng một entry.
- Phát invalidation event qua message broker/pub-sub để mọi instance xóa entry cục bộ tương ứng.

Redis giúp chia sẻ entry nhưng không tự giải quyết mọi vấn đề consistency. Cần cấu hình TTL, serialization, namespace tenant và chính sách xử lý khi cache unavailable. Pub/sub có thể mất thông báo khi consumer offline hoặc subscriber ngắt kết nối; cần TTL làm safety net và cơ chế phát lại nếu yêu cầu nhất quán cao.

## 13. Outbox để không mất invalidation event

Nếu một thay đổi graph phải làm cache ở nhiều instance được invalidation đáng tin cậy, chỉ publish application event trong bộ nhớ có thể chưa đủ. Ứng dụng có thể ghi một outbox node cùng transaction với thay đổi graph:

```cypher
MATCH (p:Person {code: $personCode})
SET p.name = $newName,
    p.updatedAt = datetime()
CREATE (:CacheInvalidationOutbox {
    eventId: $eventId,
    tenantId: $tenantId,
    aggregateType: 'Person',
    aggregateId: $personCode,
    eventType: 'PERSON_CHANGED',
    createdAt: datetime(),
    published: false
});
```

Một worker đọc outbox chưa publish, phát thông báo invalidation tới Redis Pub/Sub hoặc message broker, sau đó đánh dấu đã publish. Worker cần xử lý lặp an toàn bằng `eventId` vì có thể crash sau khi phát message nhưng trước khi đánh dấu hoàn tất.

Outbox bảo đảm thay đổi graph và bản ghi yêu cầu invalidation được commit cùng nhau trong một Neo4j transaction. Việc giao message vẫn thường là at-least-once; consumer phải idempotent. Không nên xóa outbox ngay sau khi phát nếu chưa có chính sách retention và quan sát lỗi phù hợp.

## 14. Invalidation khi graph thay đổi ngoài SDN

Mutation có thể đến từ nhiều nguồn:

- Repository `save`, `saveAll`, `delete`.
- `@Query` có `CREATE`, `SET`, `MERGE`, `DELETE`.
- `Neo4jClient` chạy Cypher tùy chỉnh.
- Neo4j Java Driver được gọi trực tiếp.
- Script migration hoặc job đồng bộ dữ liệu.
- Một service hoặc ứng dụng khác cùng truy cập database.

Cache annotation ở một service chỉ bao phủ những lời gọi đi qua service đó. `BeforeBindCallback`, `AfterConvertCallback` hoặc `@DomainEvents` cũng không phải database trigger cho mọi client. Nếu một script hoặc ứng dụng khác thay đổi graph, cache trong service không tự biết để evict.

Hãy thống nhất đường ghi trong kiến trúc:

1. Nếu mọi mutation đi qua một command service, đặt invalidation tại service đó.
2. Nếu có custom Cypher, gọi cùng invalidation/event logic sau khi query thành công.
3. Nếu có nhiều writer, dùng outbox/event contract chung hoặc cơ chế change-data notification phù hợp.
4. Với migration làm thay đổi cách đọc dữ liệu, evict namespace/cache liên quan khi triển khai hoặc tăng projection version.
5. Dùng TTL để giới hạn thời gian stale nếu một đường ghi không thể phát invalidation ngay lập tức.

## 15. Race condition giữa cache fill và invalidation

Một tình huống dễ bỏ sót:

1. Request A cache miss và bắt đầu đọc graph cũ.
2. Request B cập nhật node, commit và evict cache key.
3. Request A hoàn tất query cũ sau khi B evict, rồi ghi kết quả cũ vào cache.
4. Các request sau tiếp tục nhận dữ liệu cũ cho tới TTL.

Đây là race giữa cache fill và invalidation. Transaction-aware eviction bảo đảm thứ tự sau commit, nhưng không tự ngăn một read cũ ghi lại cache sau eviction.

Các cách giảm rủi ro:

- Dùng TTL ngắn cho cache có nhiều ghi đồng thời.
- Gắn version/generation vào key và tăng version khi graph thay đổi.
- Cache DTO có version/timestamp và chỉ chấp nhận ghi nếu version vẫn hiện hành.
- Dùng write lock hoặc cơ chế single-flight theo key khi tải cache miss tốn kém.
- Với dữ liệu cần consistency mạnh, đọc trực tiếp Neo4j hoặc bỏ cache cho query đó.

Không có một TTL chung phù hợp cho mọi loại kết quả. Hồ sơ ít thay đổi có thể cache lâu hơn; quyền truy cập, trạng thái đơn hàng hoặc kết quả phụ thuộc quan hệ thường cần TTL ngắn hoặc không cache.

## 16. Cache kết quả traversal và shortest path

Kết quả traversal phụ thuộc nhiều hơn một node. Ví dụ key:

```text
tenant : sourceCode : relationshipType : direction : maxDepth : filters
```

Khi một relationship `KNOWS` được thêm giữa hai node, kết quả neighborhood của cả hai endpoint và nhiều source node khác có thể thay đổi. Nếu query trả shortest path, một cạnh mới có thể làm thay đổi path giữa nhiều cặp source/target.

Có ba chiến lược:

| Chiến lược | Ưu điểm | Hạn chế |
|---|---|---|
| Evict chính xác theo key | Ít cache miss | Phải biết đầy đủ query nào phụ thuộc vào node/edge vừa đổi |
| Evict toàn cache/tenant | Dễ bảo đảm kết quả cũ không còn được đọc | Có thể tạo cache stampede và tải Neo4j tăng |
| Generation/version namespace | Invalidation nhanh, không cần liệt kê key cũ | Cần quản lý version atomic và key cũ vẫn chiếm bộ nhớ tới TTL |

Với neighborhood hoặc shortest path có phạm vi rộng, generation theo tenant hoặc theo graph domain thường dễ vận hành hơn cố gắng tìm mọi key bị ảnh hưởng. Nếu graph có partition/domain độc lập, có thể tăng generation theo partition để giảm invalidation blast radius.

## 17. Cache stampede và đồng thời tải lại

Khi một key hết hạn hoặc bị evict, nhiều request cùng lúc có thể cache miss và đồng thời chạy cùng truy vấn graph. Đây là cache stampede.

Giảm rủi ro bằng cách:

- Giới hạn TTL và kích thước cache hợp lý.
- Dùng cơ chế đồng bộ load theo key nếu cache provider hỗ trợ.
- Dùng `@Cacheable(sync = true)` khi provider và cache implementation hỗ trợ semantics đồng bộ phù hợp.
- Làm query miss đủ nhanh và giới hạn số request đồng thời.
- Với dữ liệu phổ biến, refresh chủ động trước khi TTL hết hạn nếu cần.

`sync = true` là gợi ý đồng bộ cho cache provider; không mặc định nó là distributed lock trên mọi provider. Kiểm tra tài liệu provider cụ thể trước khi dùng để bảo vệ workload nhiều instance.

## 18. Reactive service và caching

Reactive repository trả về `Mono`/`Flux`; cần phân biệt cache một publisher trong Reactor với application cache dùng chung giữa request.

`Mono.cache()` lưu tín hiệu của một publisher instance để subscription sau có thể dùng lại kết quả. Nó không tự tạo một cache có key toàn cục, TTL theo tenant hoặc invalidation liên kết với graph. Không tạo một `Mono.cache()` ở field service rồi dùng cho mọi personCode, vì có thể trả cùng một kết quả cho nhiều request.

Với reactive application, chọn một cache provider có hỗ trợ async/reactive phù hợp hoặc dùng một abstraction cache riêng trả về `Mono<T>`. Đưa toàn bộ cache lookup, database fallback và cache write vào Reactor chain; không gọi `.block()` trong WebFlux. Cache key vẫn phải bao gồm tenant, query parameters và projection như imperative application.

Nếu dùng Spring Cache annotation với reactive return type, hãy kiểm tra phiên bản Spring Framework và semantics của provider. Hành vi hỗ trợ `Mono`/`Flux`, việc materialize `Flux` thành collection và cách lưu publisher đã thay đổi theo phiên bản; không giả định mọi cache provider đều xử lý stream theo cùng một cách. Với kết quả lớn, tránh gom toàn bộ `Flux` vào một cache entry nếu chưa giới hạn số phần tử.

Reactive invalidation cũng cần xảy ra sau khi reactive transaction commit. Có thể dùng reactive transaction event phù hợp hoặc nối logic invalidation sau completion của transaction publisher, đồng thời bảo đảm không evict khi transaction rollback. Với cache phân tán, dùng cùng event/outbox strategy như imperative application.

## 19. Chính sách TTL, size và dữ liệu null

Cache cần có giới hạn vận hành:

| Thuộc tính | Câu hỏi cần trả lời |
|---|---|
| TTL | Kết quả có thể cũ tối đa bao lâu? |
| Maximum size | Cache được phép giữ bao nhiêu entry/byte? |
| Serialization | DTO có tương thích schema giữa các phiên bản ứng dụng không? |
| Null caching | Có cache kết quả không tồn tại không, và trong bao lâu? |
| Eviction | Khi đầy bộ nhớ, entry nào bị loại? |
| Tenant namespace | Có thể xóa hoặc giới hạn cache theo tenant không? |
| Failure mode | Nếu Redis/Caffeine lỗi, request có fallback đọc Neo4j được không? |

Negative caching (cache kết quả không tìm thấy) có thể giảm query lặp lại cho ID không tồn tại, nhưng TTL nên ngắn. Nếu node được tạo sau đó, cache negative phải được evict hoặc hết hạn. Tránh cache exception tùy tiện; chỉ cache một kết quả “không tồn tại” có semantics rõ ràng.

## 20. Quan sát hiệu quả cache

Đo hiệu quả bằng metric thay vì chỉ bật cache rồi suy đoán. Các chỉ số hữu ích:

- Hit rate và miss rate theo cache name.
- Số lần evict/expire và số entry hiện tại.
- Thời gian query Neo4j khi cache miss.
- Latency service p50/p95/p99 trước và sau khi cache.
- Tỷ lệ lỗi cache provider và fallback.
- Số lượng invalidation event pending hoặc thất bại.
- Tuổi của dữ liệu cache nếu lưu timestamp/version.

Hit rate cao không luôn có nghĩa cache đúng. Một cache key thiếu tenant hoặc thiếu filter có thể hit rất tốt nhưng trả nhầm dữ liệu. Kết hợp metric với kiểm thử tenant isolation và freshness.

## 21. Kiểm thử cache và invalidation

Một bộ kiểm thử nên bao phủ:

| Tình huống | Thao tác | Kỳ vọng |
|---|---|---|
| Cache miss | Gọi service lần đầu | Query repository chạy, kết quả được cache |
| Cache hit | Gọi lại cùng key | Không chạy lại query |
| Key khác | Gọi với personCode khác | Không dùng nhầm entry |
| Tenant khác | Cùng personCode nhưng tenant khác | Hai tenant nhận dữ liệu riêng |
| Mutation thành công | Update node rồi gọi query | Entry cũ bị evict và kết quả mới được đọc |
| Transaction rollback | Update rồi ném exception | Cache không chứa giá trị chưa commit; deferred eviction không chạy nếu dùng transaction-aware cache |
| Relationship mutation | Thêm/xóa edge | Neighborhood/path cache liên quan bị invalidation |
| Custom Cypher | Ghi bằng `@Query`/`Neo4jClient` | Invalidation vẫn được gọi qua command/event path |
| External writer | Thay đổi graph ngoài service hiện tại | Event/outbox hoặc TTL làm cache được làm mới |
| Multi-instance | Update tại instance A, đọc tại B | Cache shared hoặc invalidation event làm B không dùng entry cũ quá chính sách |
| Race cache fill | Read cũ chạy đồng thời với update | Version/generation hoặc chính sách freshness ngăn stale value tồn tại lâu |

Có thể dùng `@Cacheable` cùng `CacheManager` giả lập trong unit test để kiểm tra interceptor. Với transaction semantics và Neo4j, cần integration test có database thật hoặc test container để xác minh commit/rollback và dữ liệu graph sau mutation.

## 22. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Cache trả dữ liệu của tenant khác | Key không chứa tenant/database identity | Thêm tenant namespace và kiểm thử isolation |
| Update Neo4j nhưng cache vẫn cũ | Mutation đi qua `@Query`, Driver hoặc service không evict | Chuẩn hóa command path và phát invalidation event |
| Cache chứa dữ liệu chưa commit | Put cache trước khi transaction Neo4j commit | Dùng transaction-aware cache hoặc event `AFTER_COMMIT` |
| Rollback nhưng cache vẫn bị evict | Eviction chạy trước khi transaction kết thúc hoặc transaction/cache advice không phối hợp | Dùng transaction-aware cache hoặc listener sau commit |
| Neighborhood vẫn cũ sau khi thêm relationship | Chỉ evict cache của node được cập nhật, bỏ qua endpoint và traversal phụ thuộc | Evict theo tenant/graph domain hoặc generation |
| Redis cập nhật nhưng instance khác vẫn stale | Cache cục bộ của instance không nhận invalidation | Dùng distributed cache hoặc pub/sub invalidation |
| Cache stampede khi key hết hạn | Nhiều request cùng load lại một key | Single-flight/provider sync, TTL jitter hoặc refresh chủ động |
| `@Cacheable` không chạy | Self-invocation hoặc bean không qua proxy | Gọi qua Spring bean proxy và kiểm tra `@EnableCaching` |
| Cache tăng bộ nhớ không giới hạn | Không đặt TTL hoặc maximum size | Cấu hình expiration và capacity |
| `Mono.cache()` trả sai dữ liệu | Dùng chung publisher instance cho nhiều tham số | Cache theo key trong cache provider phù hợp |
| Evict toàn bộ cache làm tăng tải đột biến | `allEntries = true` trên cache lớn | Evict theo key/tenant hoặc generation namespace |

## 23. Quy trình triển khai application cache cho graph

1. Chọn read model có chi phí tính toán đáng kể và được đọc lặp lại.
2. Dùng DTO/projection bất biến thay vì cache domain entity graph không đầy đủ.
3. Thiết kế cache key chứa tenant/database, query parameters, filter và projection.
4. Chọn provider, TTL, maximum size, serialization và chính sách null.
5. Dùng `@Cacheable` cho query path và đo hit/miss.
6. Liệt kê node/relationship/property mà từng cache entry phụ thuộc.
7. Gắn invalidation với mọi đường ghi: repository, `@Query`, `Neo4jClient`, Driver và job bên ngoài.
8. Trì hoãn cache put/evict tới sau commit bằng transaction-aware cache hoặc `AFTER_COMMIT` event.
9. Với nhiều instance hoặc external writer, dùng distributed cache, pub/sub hoặc transactional outbox.
10. Xử lý race cache fill, stampede và generation version khi query phụ thuộc nhiều cạnh.
11. Kiểm thử commit, rollback, relationship mutation, tenant isolation và multi-instance invalidation.
12. Theo dõi freshness cùng hit rate; bỏ cache nếu chi phí invalidation lớn hơn lợi ích.

## 24. Tự kiểm tra

1. Application result cache khác Neo4j page cache và query cache như thế nào?
2. Vì sao DTO projection thường phù hợp hơn entity graph để lưu cache?
3. `@Cacheable`, `@CachePut` và `@CacheEvict` có semantics khác nhau ra sao?
4. Vì sao cache key cần chứa tenant/database identity?
5. Một relationship mới có thể ảnh hưởng những loại cache kết quả nào?
6. Vì sao `@CacheEvict` sau method invocation chưa chắc là sau database commit?
7. `TransactionAwareCacheManagerProxy` trì hoãn những thao tác cache nào và có giới hạn gì?
8. Khi nào nên dùng `@TransactionalEventListener(AFTER_COMMIT)`?
9. Vì sao application event trong một JVM không đủ cho nhiều application instance?
10. Transactional outbox giúp bảo đảm điều gì khi phát invalidation event?
11. Generation key giúp giảm chi phí invalidation graph traversal như thế nào?
12. Cache stampede và race giữa cache fill với invalidation khác nhau ở điểm nào?
13. Vì sao `Mono.cache()` không thay thế distributed application cache theo key?
14. Cần kiểm thử những tình huống nào để chứng minh cache không làm rò dữ liệu tenant?

## Tài liệu tham khảo

- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework — Declarative Cache Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Cache and Transaction Awareness](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Data Neo4j — Reference Documentation](https://docs.spring.io/spring-data/neo4j/reference/)
- [Neo4j Operations Manual — Page Cache](https://neo4j.com/docs/operations-manual/current/performance/memory-configuration/)
- [Neo4j Cypher Manual — Query Caches](https://neo4j.com/docs/cypher-manual/current/query-caches/)
- [Caffeine — User Guide](https://github.com/ben-manes/caffeine/wiki)
