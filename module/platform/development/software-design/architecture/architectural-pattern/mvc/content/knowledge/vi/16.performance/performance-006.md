# Tính đúng đắn và quyền truy cập khi dùng bộ nhớ đệm

Bộ nhớ đệm (cache) lưu tạm dữ liệu đã được đọc hoặc tính toán để request sau có thể nhận kết quả nhanh hơn. Trong ứng dụng MVC, cache có thể nằm ở trình duyệt, reverse proxy, tầng ứng dụng, query service hoặc cơ sở dữ liệu. Cache giảm thời gian truy vấn và tải hệ thống, nhưng cũng tạo thêm một bản sao dữ liệu có vòng đời riêng.

Một cache chỉ hữu ích khi dữ liệu được trả về vẫn đúng với ngữ cảnh request và người gọi được phép xem dữ liệu đó. Nếu khóa cache thiếu tenant hoặc người dùng, hai request có thể nhận dữ liệu của nhau. Nếu cache không được làm mới sau cập nhật, giao diện có thể hiển thị giá, trạng thái hoặc quyền đã cũ. Nếu cache quyết định quyền truy cập thay cho hệ thống có thẩm quyền, việc thu hồi quyền có thể không có hiệu lực đúng lúc.

Vì vậy, thiết kế cache phải trả lời ba câu hỏi: dữ liệu nào được lưu, ai có thể nhận dữ liệu đó, và khi nào bản sao không còn hợp lệ. Hiệu năng chỉ là một phần của hợp đồng.

## 1. Cache nằm ở đâu trong luồng MVC?

Một request thường đi qua Controller, application service/query service, repository rồi đến cơ sở dữ liệu. Cache có thể được đặt giữa service và repository để tái sử dụng kết quả truy vấn:

~~~mermaid
flowchart TD
    R[HTTP Request] --> C[Controller]
    C --> A[Application / Query Service]
    A --> P[Kiểm tra quyền và ngữ cảnh]
    P --> K{Cache hit?}
    K -->|Có| V[Snapshot đã cache]
    K -->|Không| D[Repository / Database]
    D --> W[Lưu snapshot vào cache]
    W --> V
    V --> M[Ánh xạ ViewModel hoặc Response DTO]
    M --> O[HTML / JSON Response]
~~~

Cache hit có nghĩa là ứng dụng tìm thấy bản sao theo khóa đã yêu cầu. Nó không tự chứng minh bản sao còn mới hoặc người gọi hiện tại có quyền nhận nó. Controller vẫn phải điều phối đúng use case; tầng ứng dụng vẫn phải áp dụng quyền và quy tắc nghiệp vụ cần thiết.

Các vị trí cache phổ biến:

| Vị trí | Dữ liệu thường lưu | Phạm vi ảnh hưởng |
|---|---|---|
| Browser cache | Tài nguyên tĩnh, một số response HTTP | Một trình duyệt hoặc người dùng |
| CDN/reverse proxy | Nội dung công khai, có thể cache được | Nhiều người dùng |
| Application cache | Kết quả truy vấn, cấu hình, projection | Một instance hoặc nhiều instance tùy backend |
| Distributed cache | Dữ liệu dùng chung như Redis | Nhiều instance ứng dụng |
| Database buffer/cache | Trang dữ liệu và kết quả nội bộ của DB | Do hệ quản trị dữ liệu quản lý |

Mỗi tầng có quy tắc riêng về khóa, thời hạn, xác thực và vô hiệu hóa. Không nên giả định việc xóa cache trong ứng dụng sẽ xóa bản sao đã lưu ở CDN hoặc trình duyệt.

## 2. Cache key phải mô tả đầy đủ ngữ cảnh dữ liệu

Cache key xác định một mục dữ liệu được lưu và truy xuất. Nếu hai request có thể nhận kết quả khác nhau thì khóa của chúng phải khác nhau, hoặc dữ liệu phải được lọc lại theo từng request sau khi lấy từ cache.

Ví dụ một sản phẩm có thể khác nhau theo tenant:

- Tenant A có tên sản phẩm, giá và trạng thái riêng.
- Tenant B có thể có giá hoặc chính sách hiển thị khác.
- Người dùng trong cùng tenant có thể có phạm vi nhìn thấy khác nhau.

Khóa chỉ gồm productId là không đủ nếu ID không duy nhất toàn hệ thống hoặc dữ liệu phụ thuộc tenant.

Một cache key có thể cần các chiều sau:

| Chiều ngữ cảnh | Khi nào cần đưa vào khóa? |
|---|---|
| Tenant/organization | Dữ liệu được phân vùng theo tenant |
| Người dùng | Kết quả cá nhân hóa hoặc phạm vi dữ liệu riêng từng user |
| Nhóm quyền/visibility scope | Kết quả khác nhau theo quyền hoặc phạm vi chia sẻ |
| Resource ID | Dữ liệu của một sản phẩm, đơn hàng hoặc tài khoản |
| Bộ lọc và sắp xếp | Kết quả danh sách phụ thuộc query parameter |
| Trang và kích thước trang | Cache riêng từng lát dữ liệu phân trang |
| Locale | Nội dung đã dịch hoặc định dạng theo ngôn ngữ |
| Phiên bản dữ liệu | Cần tách bản sao cũ và mới theo version |
| Feature flag hoặc cấu hình | Kết quả phụ thuộc tính năng hoặc cấu hình runtime |

Không phải cache nào cũng cần mọi chiều. Hãy xác định dữ liệu có thể thay đổi theo yếu tố nào rồi chọn khóa tương ứng. Đưa quá ít thông tin gây rò dữ liệu hoặc trả sai kết quả; đưa mọi thứ vào khóa có thể làm giảm tỷ lệ cache hit và tăng số lượng mục.

### 2.1. Phân vùng theo tenant

Với dữ liệu đa tenant, một dạng khóa cơ bản là:

~~~text
product:{tenantId}:{productId}
~~~

Tenant ID phải lấy từ ngữ cảnh đã xác thực hoặc một nguồn tin cậy ở phía máy chủ. Không dùng giá trị tenant do client gửi làm bằng chứng người dùng thuộc tenant đó. Nếu request có tham số tenant, tầng xác thực và phân quyền phải xác minh người gọi được phép thao tác trong tenant này trước khi sử dụng.

### 2.2. Dữ liệu cá nhân hóa

Nếu kết quả phụ thuộc user, khóa có thể chứa user ID hoặc một visibility scope ổn định:

~~~text
dashboard:{tenantId}:{userId}:{period}
~~~

Nếu nhiều người dùng có cùng kết quả theo một nhóm quyền, có thể cache theo nhóm hoặc chính sách chia sẻ đã xác định. Tuy nhiên, quyền của người dùng có thể thay đổi; cache theo role name đơn thuần có thể không đủ nếu hai người cùng role có phạm vi tài nguyên khác nhau.

### 2.3. Cache danh sách và bộ lọc

Hai truy vấn /products?category=book&page=0 và /products?category=tool&page=0 phải có khóa khác nhau. Nếu thứ tự tham số URL thay đổi nhưng ngữ nghĩa giống nhau, ứng dụng nên chuẩn hóa query criteria trước khi tạo key. Cũng cần chuẩn hóa thứ tự các bộ lọc nhiều giá trị, để cùng một tập điều kiện không tạo nhiều key chỉ vì thứ tự truyền khác nhau.

Không tạo key bằng cách nối chuỗi tùy tiện từ dữ liệu không giới hạn. Key nên có cấu trúc rõ, độ dài kiểm soát được và không chứa token, mật khẩu hoặc dữ liệu bí mật.

## 3. Cache key không thay thế kiểm tra quyền truy cập

Một lỗi bảo mật nghiêm trọng là giả định rằng người dùng có thể đọc cache nếu biết ID hoặc tạo đúng key. Cache không phải ranh giới phân quyền.

Có hai cách tổ chức phổ biến:

1. Cache dữ liệu dùng chung trong phạm vi tenant, sau đó áp dụng kiểm tra quyền cho từng request trước khi trả dữ liệu.
2. Cache kết quả đã cá nhân hóa, với key bao gồm đầy đủ user/visibility context và có chính sách làm mới khi quyền thay đổi.

Cách thứ nhất thường dễ kiểm soát hơn nếu có thể cache snapshot dữ liệu không nhạy cảm theo tenant rồi áp dụng policy riêng ở mỗi request. Cách thứ hai có thể giảm chi phí tính toán nhưng đòi hỏi khóa và vô hiệu hóa quyền chính xác hơn.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant A as Application Service
    participant Z as Authorization Policy
    participant C as Cache
    participant D as Database
    U->>A: Yêu cầu xem sản phẩm
    A->>Z: Kiểm tra quyền với user, tenant, resource
    Z-->>A: Cho phép / từ chối
    alt Được phép
        A->>C: Đọc snapshot theo tenant và resource
        alt Cache hit
            C-->>A: Snapshot
        else Cache miss
            A->>D: Đọc dữ liệu
            D-->>A: Snapshot
            A->>C: Lưu snapshot
        end
        A-->>U: ViewModel / Response DTO
    else Bị từ chối
        A-->>U: 403 hoặc 404 theo chính sách
    end
~~~

Ví dụ này kiểm tra quyền trước khi truy xuất cache. Với tài nguyên mà việc kiểm tra quyền cần đọc dữ liệu, có thể cache dữ liệu cơ sở rồi thực hiện policy sau khi lấy snapshot; điều kiện là không được trả nội dung cho đến khi kiểm tra quyền hoàn tất.

### 3.1. Đừng cache một quyết định quyền quá lâu

Quyền có thể thay đổi khi người dùng bị xóa khỏi nhóm, tenant thu hồi quyền, tài liệu chuyển chủ sở hữu hoặc quản trị viên khóa tài khoản. Nếu cache quyết định allowed=true trong thời gian dài, người dùng có thể tiếp tục truy cập sau khi quyền đã bị thu hồi.

Nếu cần cache authorization decision:

- Xác định rõ TTL ngắn phù hợp với mức rủi ro.
- Có cơ chế vô hiệu hóa khi membership hoặc policy thay đổi.
- Đưa policy version hoặc authorization epoch vào key nếu hệ thống quản lý phiên bản quyền.
- Kiểm tra lại quyền ở thao tác nhạy cảm hoặc tại nơi thực hiện command.
- Không dùng cache quyền làm cơ chế duy nhất để bảo vệ dữ liệu có mức độ nhạy cảm cao.

Ẩn nút trên View hoặc trả canEdit=false trong DTO chỉ là hướng dẫn giao diện. Endpoint cập nhật vẫn phải xác thực quyền tại thời điểm thực hiện.

## 4. Ví dụ Spring: cache snapshot theo tenant

Giả sử ứng dụng có một ProductSnapshot bất biến để trình bày thông tin sản phẩm. Cache lưu snapshot đã được query service tạo ra, không lưu entity JPA có lazy relationship hoặc trạng thái mutable.

~~~java
import java.math.BigDecimal;

public record ProductSnapshot(
        long productId,
        long tenantId,
        String name,
        BigDecimal price,
        String currency,
        long version
) {
}
~~~

Bean đọc cache:

~~~java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CachedProductReader {
    private final ProductReadRepository repository;

    public CachedProductReader(ProductReadRepository repository) {
        this.repository = repository;
    }

    @Cacheable(
            cacheNames = "productSnapshot",
            key = "#p0 + ':' + #p1",
            unless = "#result == null"
    )
    public ProductSnapshot find(long tenantId, long productId) {
        return repository.findSnapshot(tenantId, productId).orElse(null);
    }
}
~~~

Key dùng cả tenantId và productId. #p0 và #p1 tham chiếu tham số theo vị trí, tránh phụ thuộc cấu hình giữ tên tham số khi biên dịch. unless được đánh giá sau khi method trả kết quả và ngăn lưu kết quả null theo biểu thức của Spring Cache. Nếu muốn dùng sync=true để phối hợp tải cùng key, cần tuân thủ các giới hạn của thuộc tính này; chẳng hạn không kết hợp nó với unless trên cùng một phương thức theo hợp đồng Spring Cache. Mức phối hợp cụ thể cũng phụ thuộc cache provider.

Facade áp dụng quyền cho mỗi request:

~~~java
@Service
public class ProductQueryFacade {
    private final ProductAccessPolicy accessPolicy;
    private final CachedProductReader cachedProducts;

    public ProductQueryFacade(
            ProductAccessPolicy accessPolicy,
            CachedProductReader cachedProducts
    ) {
        this.accessPolicy = accessPolicy;
        this.cachedProducts = cachedProducts;
    }

    public ProductSnapshot getFor(
            CurrentUser user,
            long tenantId,
            long productId
    ) {
        accessPolicy.requireCanRead(user, tenantId, productId);
        return cachedProducts.find(tenantId, productId);
    }
}
~~~

Trong ví dụ, tenantId cần được xác định từ tenant context đã xác thực và policy phải xác minh user có quyền trong tenant đó. Repository cũng phải truy vấn theo cả tenantId và productId để không thể lấy nhầm bản ghi của tenant khác. Không nhận tenant ID tùy ý từ client rồi bỏ qua xác minh.

Tách CachedProductReader thành bean riêng cũng giúp lời gọi đi qua Spring proxy. Spring Cache dựa vào proxy trong cấu hình thông thường; gọi một method @Cacheable khác trong cùng instance (self-invocation) có thể bỏ qua interceptor và không kích hoạt cache.

### 4.1. Cache dữ liệu hay cache ViewModel?

Cache snapshot nghiệp vụ/query thường tái sử dụng được giữa nhiều màn hình và API. Cache ViewModel có thể chứa nhãn dịch, cờ giao diện hoặc nội dung cá nhân hóa nên cần key bổ sung theo locale và người dùng. Trước khi cache ViewModel, hãy chắc chắn key bao phủ mọi yếu tố ảnh hưởng kết quả và không đưa dữ liệu riêng tư sang người khác.

Với dữ liệu có thể thay đổi quyền xem, thường an toàn hơn khi cache dữ liệu đã được phân vùng đúng, rồi áp dụng policy và tạo ViewModel cho từng request. Không cache trực tiếp HTML/JSON cá nhân hóa ở CDN hoặc cache dùng chung nếu không cấu hình đúng chính sách riêng tư.

## 5. Freshness: bản sao cache còn mới đến đâu?

Cache có thể trả dữ liệu cũ sau khi nguồn dữ liệu đã thay đổi. Độ mới (freshness) là khoảng thời gian hoặc điều kiện mà ứng dụng chấp nhận dữ liệu cache.

Một số chính sách thường gặp:

| Chính sách | Cách hoạt động | Phù hợp khi |
|---|---|---|
| TTL (time to live) | Hết thời gian thì mục cache tự hết hạn | Dữ liệu thay đổi không quá thường xuyên |
| Invalidation | Xóa mục khi dữ liệu nguồn thay đổi | Cần giảm thời gian tồn tại của dữ liệu cũ |
| Write-through | Cập nhật cache cùng luồng ghi | Cần cache phản ánh cập nhật sau khi ghi thành công |
| Refresh-ahead | Làm mới trước khi hết hạn | Dữ liệu nóng và chi phí tải lại cao |
| Stale-while-revalidate | Tạm trả dữ liệu cũ trong khi làm mới | Có thể chấp nhận stale trong một giới hạn |
| Versioned key | Đổi version để đọc một namespace dữ liệu mới | Cần tránh dùng lại cache cũ sau thay đổi |

TTL là giới hạn thời gian, không phải bảo đảm dữ liệu luôn mới. Nếu một sản phẩm đổi giá ngay sau khi cache được tạo với TTL 30 phút, người dùng vẫn có thể thấy giá cũ gần 30 phút nếu không có invalidation.

Hãy chọn mức stale có thể chấp nhận theo dữ liệu:

- Ảnh đại diện hoặc nội dung ít thay đổi có thể chấp nhận TTL dài.
- Danh mục sản phẩm có thể chấp nhận độ trễ ngắn nếu có quy trình invalidation.
- Giá tại thời điểm thanh toán, số dư, tồn kho hoặc trạng thái quyền thường cần đọc/kiểm tra có thẩm quyền ngay trước thao tác nhạy cảm.

Không dùng một TTL chung cho mọi loại dữ liệu chỉ vì cấu hình đơn giản.

## 6. Cache-aside và cập nhật dữ liệu

Cache-aside (lazy loading) là cách triển khai phổ biến:

1. Đọc cache theo key.
2. Nếu có, trả dữ liệu.
3. Nếu không, đọc nguồn dữ liệu.
4. Lưu kết quả vào cache với TTL.
5. Trả dữ liệu.

Khi cập nhật:

1. Ghi thay đổi vào nguồn dữ liệu.
2. Sau khi transaction commit, xóa hoặc làm mới cache liên quan.

~~~mermaid
flowchart TD
    R[Request đọc] --> K{Có cache?}
    K -->|Có| H[Trả cache]
    K -->|Không| DB[Đọc database]
    DB --> SET[Lưu cache có TTL]
    SET --> OUT[Trả kết quả]
    W[Request cập nhật] --> TX[Transaction ghi database]
    TX --> COMMIT{Commit thành công?}
    COMMIT -->|Không| ERR[Trả lỗi, giữ cache cũ]
    COMMIT -->|Có| INV[Phát tín hiệu invalidation]
    INV --> DEL[Xóa key liên quan]
~~~

Nếu xóa cache trước khi transaction commit rồi transaction thất bại, request sau có thể tải dữ liệu cũ và cache lại. Nếu xóa cache sau commit, hệ thống giảm nguy cơ đó. Tuy nhiên, trong môi trường nhiều instance hoặc có request đọc đồng thời, vẫn cần xử lý các race condition giữa tải dữ liệu và invalidation.

### 6.1. Chỉ vô hiệu hóa sau commit

Có thể phát application event trong transaction rồi xử lý invalidation ở pha AFTER_COMMIT:

~~~java
public record ProductChanged(long tenantId, long productId) {
}
~~~

Service cập nhật:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCommandService {
    private final ProductRepository products;
    private final ApplicationEventPublisher events;

    public ProductCommandService(
            ProductRepository products,
            ApplicationEventPublisher events
    ) {
        this.products = products;
        this.events = events;
    }

    @Transactional
    public void rename(long tenantId, long productId, String newName) {
        Product product = products.findForUpdate(tenantId, productId)
                .orElseThrow(ProductNotFoundException::new);
        product.rename(newName);
        events.publishEvent(new ProductChanged(tenantId, productId));
    }
}
~~~

Listener xóa cache sau commit:

~~~java
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class ProductCacheInvalidator {
    private final CacheManager cacheManager;

    public ProductCacheInvalidator(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(ProductChanged event) {
        Cache cache = cacheManager.getCache("productSnapshot");
        if (cache != null) {
            cache.evict(event.tenantId() + ":" + event.productId());
        }
    }
}
~~~

Ví dụ minh họa invalidation trong cùng ứng dụng và cùng cache manager. ProductRepository.findForUpdate cần có cơ chế khóa hoặc concurrency phù hợp với nghiệp vụ; listener không thay thế transaction ghi dữ liệu.

TransactionalEventListener(AFTER_COMMIT) chỉ xử lý event trong tiến trình ứng dụng. Nếu tiến trình dừng ngay sau commit nhưng trước khi listener hoàn tất, hoặc hệ thống có nhiều instance với local cache riêng, một số instance có thể giữ bản sao cũ. Với invalidation cần độ tin cậy cao giữa nhiều dịch vụ/instance, dùng thông điệp bền vững hoặc Transactional Outbox để phát sự kiện sau commit và có thể retry.

### 6.2. Race giữa cache miss và invalidation

Một trường hợp tinh vi:

1. Request A cache miss và bắt đầu đọc bản ghi cũ từ database.
2. Request B cập nhật bản ghi, commit và xóa key cache.
3. Request A hoàn tất truy vấn cũ sau khi B đã xóa key.
4. A ghi bản cũ vào cache sau invalidation.

Cache lại chứa dữ liệu cũ dù invalidation đã chạy. TTL chỉ giới hạn thời gian tồn tại của bản cũ, không ngăn race này.

Các cách giảm rủi ro:

- Dùng version/generation trong key hoặc cache entry để lần đọc cũ không ghi vào namespace hiện tại.
- Phối hợp đọc/ghi qua khóa hoặc cơ chế cache provider phù hợp nếu mức tải cho phép.
- Dùng cập nhật cache có điều kiện theo version.
- Giữ TTL ngắn cho dữ liệu nhạy cảm với freshness.
- Với quyết định quan trọng, đọc nguồn dữ liệu có thẩm quyền thay vì dựa vào cache.

Không có một chiến lược duy nhất phù hợp mọi dữ liệu. Cần xác định rõ hệ thống chấp nhận stale trong bao lâu và hành vi khi invalidation thất bại.

## 7. Nhiều instance và distributed cache

Local cache trong bộ nhớ của một instance không tự đồng bộ với instance khác:

~~~mermaid
flowchart TD
    subgraph A[Instance A]
        CA[Local Cache A]
        SA[Spring MVC A]
    end
    subgraph B[Instance B]
        CB[Local Cache B]
        SB[Spring MVC B]
    end
    SA --> CA
    SB --> CB
    CA -. Không tự đồng bộ .- CB
    CA --> DB[(Database)]
    CB --> DB
~~~

Nếu request cập nhật đi vào instance A và chỉ xóa local cache A, instance B có thể tiếp tục trả dữ liệu cũ. Có ba hướng thường dùng:

1. Dùng distributed cache chung để các instance đọc cùng namespace và chia sẻ invalidation.
2. Phát sự kiện invalidation đến tất cả instance có local cache.
3. Dùng versioned key hoặc TTL để giới hạn việc tái sử dụng bản sao cũ.

Distributed cache giúp chia sẻ dữ liệu, nhưng không tự giải quyết mọi vấn đề nhất quán. Cần cấu hình serializer, timeout, eviction policy, phân vùng key, xác thực kết nối và xử lý khi cache backend không khả dụng.

Nếu cache backend lỗi, ứng dụng cần chính sách rõ:

- Có thể fallback về database cho dữ liệu không quá tải.
- Có thể bỏ qua cache và tiếp tục với nguồn có thẩm quyền.
- Có thể từ chối thao tác nếu không thể xác minh quyền hoặc tính đúng đắn.
- Cần giới hạn fallback để tránh làm database quá tải khi cache outage.

Không để cache outage biến thành sự cố dây chuyền do mọi request cùng truy vấn database không giới hạn.

## 8. Cache dữ liệu nhạy cảm và response HTTP

Cache có thể lưu dữ liệu cá nhân, thông tin thanh toán, hồ sơ hoặc tài liệu riêng tư. Cần xác định nơi lưu, ai có thể truy cập, thời gian lưu và cách xóa.

### 8.1. Browser và shared proxy cache

HTTP caching có các directive như Cache-Control: private, public, no-store, max-age và s-maxage. Chọn directive theo mức độ chia sẻ:

- public cho phép cache dùng chung lưu response nếu các điều kiện HTTP khác cho phép.
- private giới hạn cache vào cache riêng của client, không cho shared cache lưu response đó.
- no-store yêu cầu cache không lưu response.
- no-cache không có nghĩa là không lưu; nó yêu cầu xác thực lại trước khi dùng bản sao.

Response chứa dữ liệu tài khoản, thông tin thanh toán hoặc nội dung theo quyền người dùng thường cần chính sách private hoặc no-store tùy rủi ro. Không đánh dấu response cá nhân hóa là public chỉ để tăng tốc.

### 8.2. Application/distributed cache

Với cache phía máy chủ:

- Chỉ lưu trường thực sự cần thiết.
- Không lưu password, access token hoặc bí mật xác thực trong cache nghiệp vụ.
- Hạn chế TTL và quyền truy cập của cache backend.
- Bảo vệ đường truyền và thông tin xác thực đến Redis hoặc dịch vụ cache.
- Xóa dữ liệu theo user/tenant khi xóa tài khoản hoặc chấm dứt quan hệ lưu trữ.
- Tránh ghi cache key hoặc value nhạy cảm vào log.

Cache là một nơi lưu dữ liệu bổ sung. Xóa dữ liệu khỏi database nhưng quên xóa cache có thể khiến dữ liệu đã xóa tiếp tục được phục vụ.

## 9. Cache stampede, penetration và avalanche

Cache có thể gây áp lực lên hệ thống nếu nhiều request cùng gặp cache miss.

### 9.1. Cache stampede

Một key phổ biến hết hạn. Hàng trăm request cùng miss và cùng truy vấn database để tạo lại dữ liệu. Kết quả là tải tăng đột biến đúng lúc cache đang cần bảo vệ hệ thống.

Giải pháp:

- Single-flight/request coalescing: chỉ một tác vụ tải một key, request khác chờ kết quả.
- Refresh-ahead: làm mới dữ liệu trước khi hết hạn.
- TTL jitter: cộng thêm độ lệch ngẫu nhiên để nhiều key không hết hạn cùng thời điểm.
- Stale-while-revalidate nếu nghiệp vụ cho phép trả dữ liệu cũ trong thời gian làm mới.
- Giới hạn concurrency và timeout cho tác vụ tải dữ liệu.

Thuộc tính sync của Spring @Cacheable có thể giúp phối hợp tải cùng key theo khả năng của cache provider, nhưng có các giới hạn về cách kết hợp thuộc tính cache và không phải provider nào cũng cung cấp distributed lock. Không nên giả định nó ngăn được nhiều JVM cùng tải một key.

### 9.2. Cache penetration

Client liên tục yêu cầu ID không tồn tại. Cache không có entry nên mỗi request đều truy vấn database. Kẻ tấn công có thể tạo lượng lớn key ngẫu nhiên để bỏ qua cache.

Giải pháp:

- Validate ID và phạm vi đầu vào trước khi truy vấn.
- Dùng negative caching có TTL ngắn cho kết quả không tồn tại nếu phù hợp.
- Rate limit và giám sát mẫu request bất thường.
- Dùng Bloom filter khi có tập ID lớn và workload phù hợp.
- Không cache lỗi kỹ thuật hoặc lỗi quyền theo cách có thể làm lộ dữ liệu.

### 9.3. Cache avalanche

Nhiều key hết hạn cùng lúc hoặc cache backend mất dữ liệu khiến lượng request dồn về database.

Giải pháp:

- TTL jitter.
- Warm-up có giới hạn cho dữ liệu nóng.
- Fallback có giới hạn concurrency.
- Circuit breaker và bulkhead khi truy cập cache/database.
- Theo dõi tỷ lệ hit/miss và tải nguồn dữ liệu.

## 10. Negative caching và lỗi

Có thể cache kết quả “không tìm thấy” trong một khoảng thời gian ngắn để giảm truy vấn lặp cho ID không tồn tại. Tuy nhiên, cần phân biệt:

- Tài nguyên thực sự không tồn tại.
- Người dùng không có quyền xem tài nguyên.
- Database hoặc dịch vụ phụ thuộc đang lỗi.
- Request sai định dạng.

Không nên cache mọi exception như thể đó là kết quả rỗng. Nếu database tạm thời lỗi và ứng dụng cache null, request tiếp theo có thể tiếp tục nhận “không tìm thấy” dù dữ liệu tồn tại. Nếu cache quyết định 403 theo user, việc cấp quyền mới có thể không có hiệu lực cho đến khi cache hết hạn.

Negative entry cần TTL ngắn, key có đủ phạm vi và chính sách invalidation khi tài nguyên được tạo hoặc quyền thay đổi. Không tiết lộ sự tồn tại của tài nguyên khác tenant qua cách phân biệt lỗi hoặc thời gian phản hồi.

## 11. Cache trong Spring: cập nhật và xóa

Spring Cache cung cấp các annotation chính:

| Annotation | Ý nghĩa |
|---|---|
| @Cacheable | Đọc cache; nếu miss thì gọi method và lưu kết quả |
| @CachePut | Luôn gọi method rồi cập nhật cache bằng kết quả |
| @CacheEvict | Xóa một key hoặc toàn bộ cache |
| @Caching | Kết hợp nhiều thao tác cache |
| @EnableCaching | Bật cơ chế annotation-driven caching |

Ví dụ @CacheEvict có thể dùng cho thao tác đơn giản:

~~~java
@CacheEvict(
        cacheNames = "productSnapshot",
        key = "#p0 + ':' + #p1"
)
public void evictProduct(long tenantId, long productId) {
    // Method body có thể rỗng; interceptor thực hiện eviction.
}
~~~

Tuy nhiên, không nên đặt eviction một cách tùy tiện trước khi transaction ghi dữ liệu commit. Thứ tự giữa transaction interceptor và cache interceptor, cấu hình cache manager và thời điểm commit đều ảnh hưởng kết quả. Với dữ liệu cần invalidation sau commit, event listener AFTER_COMMIT hoặc transaction-aware cache integration thường dễ diễn đạt rõ hơn.

Một số lưu ý khi dùng annotation:

- Method phải được gọi qua Spring proxy để interceptor hoạt động trong cấu hình proxy thông thường.
- Self-invocation không đi qua proxy nên có thể bỏ qua cache annotation.
- Cache key phải xác định rõ các tham số có ảnh hưởng kết quả.
- unless được đánh giá sau khi method trả kết quả; condition được đánh giá trước khi gọi method.
- Cấu hình cache provider quyết định hỗ trợ TTL, serialization, atomicity và đồng bộ.
- Không cache kết quả phụ thuộc vào SecurityContext nếu key không chứa hoặc không tái kiểm tra ngữ cảnh đó.

## 12. Cache và tính nhất quán nghiệp vụ

Không phải mọi dữ liệu đều cần strong consistency. Có thể phân loại theo hậu quả nếu người dùng nhìn thấy dữ liệu cũ:

| Dữ liệu | Mức chấp nhận stale | Cách tiếp cận |
|---|---|---|
| Ảnh, nội dung tĩnh | Thường cao | TTL dài, versioned URL |
| Danh mục và mô tả sản phẩm | Có thể chấp nhận ngắn | TTL + invalidation |
| Báo cáo tổng hợp | Tùy thời điểm báo cáo | Snapshot có thời điểm tạo rõ ràng |
| Giá hiển thị trong catalog | Có thể stale ngắn nếu được công bố | Refresh/invalidation; kiểm tra lại khi đặt hàng |
| Tồn kho trước thanh toán | Thấp | Đọc/giữ chỗ bằng transaction hoặc cập nhật có điều kiện |
| Số dư và giao dịch | Rất thấp | Nguồn dữ liệu có thẩm quyền và kiểm soát transaction |
| Quyền truy cập | Phụ thuộc rủi ro | Kiểm tra lại tại request/command; invalidation quyền |

Một giao diện có thể hiển thị dữ liệu cache để phản hồi nhanh, nhưng thao tác ghi quan trọng phải xác minh lại tại thời điểm thực hiện. Ví dụ, trang sản phẩm hiển thị tồn kho từ cache không có nghĩa lệnh đặt hàng có thể trừ tồn kho từ con số đó mà không kiểm tra trong database.

Nếu sản phẩm chấp nhận eventual consistency, hãy công bố thời điểm dữ liệu được cập nhật hoặc trạng thái “đang đồng bộ” khi điều đó có ý nghĩa với người dùng. Không trình bày snapshot cũ như một kết quả chắc chắn hiện tại.

## 13. Cache theo phiên bản và xóa dữ liệu có phạm vi

Với dữ liệu thay đổi thường xuyên, có thể gắn version vào key:

~~~text
product:{tenantId}:{productId}:v{version}
~~~

Khi dữ liệu cập nhật từ version 8 lên 9, request mới dùng key version 9 và không đọc entry version 8. Entry cũ có thể tự hết hạn theo TTL. Cách này giảm phụ thuộc vào việc xóa đúng mọi key, nhưng cần nguồn tin cậy để biết version hiện tại và có thể tạo thêm metadata cần đồng bộ.

Với cache danh sách, một thay đổi sản phẩm có thể làm vô hiệu hóa nhiều key khác nhau theo category, filter, sort và page. Các chiến lược thường dùng:

- Evict toàn bộ namespace liên quan đến tenant hoặc category khi số key nhỏ.
- Dùng tag/index để theo dõi các key phụ thuộc một resource.
- Dùng generation/version theo tenant hoặc loại dữ liệu.
- TTL ngắn nếu không thể liệt kê chính xác mọi key phụ thuộc.

Không gọi allEntries=true cho cache lớn sau mọi cập nhật nếu việc xóa toàn bộ gây tải miss đồng loạt. Chọn phạm vi invalidation dựa trên dependency thực tế.

## 14. Kiểm thử tính đúng đắn và quyền truy cập của cache

Cache cần được kiểm thử cả khi hit, miss, hết hạn, invalidation và khi người gọi có quyền khác nhau.

1. **Key isolation:** cùng resource ID ở hai tenant tạo hai entry khác nhau.
2. **User isolation:** người dùng khác nhau không nhận ViewModel cá nhân hóa của nhau.
3. **Authorization on hit:** request bị thu hồi quyền vẫn bị từ chối dù cache có dữ liệu.
4. **Authorization on miss:** request không có quyền không được làm lộ dữ liệu qua response hoặc cache key.
5. **Cache invalidation:** cập nhật thành công làm entry cũ không còn được dùng.
6. **Rollback:** transaction thất bại không để cache phản ánh dữ liệu chưa commit.
7. **Race:** cache miss đồng thời với cập nhật không làm dữ liệu cũ tồn tại ngoài chính sách freshness.
8. **TTL:** entry hết hạn đúng theo cấu hình provider.
9. **Negative caching:** kết quả không tồn tại không che khuất việc tạo mới tài nguyên sau invalidation.
10. **Backend outage:** fallback hoặc lỗi được xử lý có giới hạn, không làm database quá tải.
11. **Multi-instance:** invalidation đến các instance hoặc namespace dùng chung đúng như thiết kế.
12. **Sensitive data:** key, value và log không chứa token hoặc trường bí mật không cần thiết.

Ví dụ kiểm thử facade khi cache đã có dữ liệu:

~~~java
@Test
void authorizationIsCheckedEvenWhenSnapshotMayBeCached() {
    CurrentUser user = new CurrentUser(25L);
    when(accessPolicy.requireCanRead(user, 7L, 42L))
            .thenThrow(new AccessDeniedException("Không được phép"));

    assertThrows(
            AccessDeniedException.class,
            () -> facade.getFor(user, 7L, 42L)
    );

    verify(cachedProducts, never()).find(7L, 42L);
}
~~~

Test này xác nhận facade kiểm tra quyền trước khi gọi bean đọc cache. Kiểm thử tích hợp cần dùng cache provider thực tế hoặc cấu hình tương đương để xác nhận key, TTL, serialization và invalidation.

## 15. Quan sát cache trong môi trường chạy

Chỉ số cache giúp nhận biết cache có thực sự cải thiện hệ thống hay tạo thêm lỗi:

- Hit rate và miss rate theo cache name.
- Số entry, eviction và expiration.
- Thời gian đọc cache và thời gian tải từ nguồn.
- Tỷ lệ lỗi, timeout và reconnect của cache backend.
- Số lần tải cùng key đồng thời.
- Số lượng invalidation, độ trễ phát/nhận event và lỗi xử lý event.
- Kích thước entry và tổng bộ nhớ sử dụng.

Không chỉ tối ưu hit rate. Một cache có hit rate cao nhưng trả dữ liệu sai hoặc rò dữ liệu người dùng là một cache thất bại. Hãy theo dõi freshness, lỗi quyền, sự cố invalidation và chênh lệch version cùng với hiệu năng.

Log key nên được che hoặc chuẩn hóa nếu chứa định danh nhạy cảm. Metric dùng nhãn có cardinality giới hạn; không đưa userId hoặc resourceId tùy ý làm label vì có thể tạo số lượng chuỗi thời gian rất lớn.

## 16. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Key chỉ gồm resource ID trong hệ đa tenant | Có thể trả dữ liệu tenant khác | Đưa tenant vào key và truy vấn |
| Dùng tenant ID do client gửi mà không xác minh | Truy cập chéo tenant | Lấy tenant từ context tin cậy và kiểm tra membership |
| Cache hit bỏ qua authorization | Người dùng vẫn xem được dữ liệu sau khi mất quyền | Kiểm tra quyền theo request hoặc cache decision có version/TTL chặt |
| Cache response cá nhân hóa dưới public | Shared proxy/CDN có thể phục vụ sai người | Dùng private/no-store phù hợp |
| Chỉ dùng TTL dài để đảm bảo freshness | Dữ liệu cũ tồn tại quá lâu | Invalidation hoặc versioned key |
| Evict trước khi transaction commit | Cache có thể được nạp lại từ dữ liệu chưa cập nhật | Invalidate sau commit |
| Cho rằng AFTER_COMMIT event bảo đảm đa instance | Local cache khác vẫn giữ dữ liệu cũ hoặc event bị mất khi process dừng | Distributed invalidation hoặc transactional outbox |
| Cache entity mutable/lazy | Dữ liệu bị sửa ngoài dự kiến, N+1 hoặc lỗi session | Cache immutable snapshot/DTO |
| sync=true được hiểu là distributed lock | Nhiều JVM vẫn có thể cùng tải | Kiểm tra bảo đảm của provider hoặc dùng coordination phù hợp |
| Cache mọi exception và null | Lỗi tạm thời bị biến thành kết quả âm kéo dài | Phân biệt not-found với lỗi hệ thống, TTL riêng |
| Không giới hạn fallback khi cache lỗi | Database quá tải khi cache outage | Bulkhead, rate limit, circuit breaker |
| Cache key chứa token hoặc dữ liệu bí mật | Bí mật xuất hiện trong log/metadata | Dùng định danh không nhạy cảm và bảo vệ backend |

## 17. Checklist thiết kế cache an toàn

Trước khi bật cache cho một use case MVC, hãy xác nhận:

- Dữ liệu nào được cache và nguồn nào vẫn là nguồn có thẩm quyền?
- Kết quả phụ thuộc tenant, user, role, locale, filter hoặc version nào?
- Key có phân biệt đầy đủ các ngữ cảnh tạo ra kết quả khác nhau không?
- Tenant và user context có đến từ nguồn đã xác thực không?
- Quyền được kiểm tra ở mỗi request cache hit hay đang bị cache thay thế?
- Dữ liệu có nhạy cảm với freshness không và stale tối đa bao lâu?
- Cập nhật database có invalidation sau commit không?
- Có race giữa cache miss và invalidation không?
- Nhiều instance có chia sẻ cache hoặc nhận invalidation đầy đủ không?
- Negative caching, stampede và backend outage được xử lý thế nào?
- HTTP response có directive phù hợp với dữ liệu cá nhân hóa không?
- Cache chỉ lưu snapshot bất biến và những trường thực sự cần thiết không?
- Kiểm thử có bao gồm tenant isolation, quyền bị thu hồi, rollback và race không?
- Metric có đo freshness, lỗi invalidation và hit/miss mà không lộ dữ liệu không?

Cache giúp giảm công việc lặp lại, nhưng mọi entry đều là một bản sao có phạm vi truy cập và thời hạn hiệu lực. Trong MVC, hãy xác định ngữ cảnh dữ liệu trước khi tạo key, kiểm tra quyền trước khi trả kết quả, và gắn invalidation với thời điểm dữ liệu nguồn được commit. Với thao tác nhạy cảm như thanh toán, tồn kho hoặc thay đổi quyền, luôn xác minh lại bằng nguồn có thẩm quyền. Thiết kế như vậy giúp cache tăng tốc ứng dụng mà không làm sai dữ liệu hoặc mở rộng quyền truy cập ngoài ý muốn.
