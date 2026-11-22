# Cache bên ngoài và quy tắc vô hiệu hóa cache

Trong ứng dụng serverless, nhiều Java function instance có thể được tạo ra và chạy đồng thời. Mỗi instance có thể có bộ nhớ riêng, vòng đời riêng và bị thu hồi bất cứ lúc nào. Nếu mỗi instance tự giữ cache trong RAM, các instance có thể nhìn thấy dữ liệu khác nhau và cache biến mất khi môi trường thực thi kết thúc.

**External cache** là dịch vụ cache nằm ngoài vòng đời của function, thường được chia sẻ qua mạng, ví dụ Redis hoặc Memcached được quản lý. Nó giúp nhiều function instance dùng chung dữ liệu đã tính toán hoặc đọc thường xuyên. Tuy nhiên, khi dữ liệu nguồn thay đổi, cache có thể trở nên cũ. Vì vậy, thiết kế cache phải trả lời hai câu hỏi: dữ liệu nào được phép lưu tạm và hệ thống làm sao để loại bỏ hoặc cập nhật bản cache đã lỗi thời.

Bài học này tập trung vào cache bên ngoài trong kiến trúc serverless, các chiến lược ghi và đọc cache, TTL, invalidation, tính nhất quán, lỗi đồng thời và cách triển khai một cache-aside đơn giản bằng Java.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao external cache hữu ích khi function được mở rộng thành nhiều instance.
- Phân biệt cache-aside, read-through, write-through và write-behind.
- Chọn TTL và chính sách invalidation theo yêu cầu độ mới của dữ liệu.
- Nhận diện cache stampede, stale write và các race condition khi cập nhật dữ liệu.
- Thiết kế cache key an toàn cho tenant và người dùng.
- Viết Java service dùng Redis làm cache có thời hạn, fallback khi cache lỗi và invalidation sau khi dữ liệu nguồn commit.
- Theo dõi hiệu quả cache bằng hit ratio, latency, eviction và tuổi dữ liệu.

## 1. External cache trong môi trường serverless

Cache lưu bản sao dữ liệu có thể tái tạo từ một nguồn khác, thường là database hoặc một dịch vụ nghiệp vụ. Mục đích là giảm thời gian đọc, giảm tải cho nguồn dữ liệu và tránh tính toán lặp lại.

Trong FaaS, một function có thể được gọi đồng thời trên nhiều execution environment. Biến static hoặc cache trong RAM chỉ được chia sẻ trong một số lần gọi trên cùng môi trường thực thi; nó không phải bộ nhớ chung của toàn bộ function. Môi trường cũng có thể bị thu hồi mà không báo trước.

External cache giải quyết vấn đề chia sẻ đó:

~~~mermaid
flowchart TD
    A["Function instance A"] --> C["External cache"]
    B["Function instance B"] --> C
    D["Function instance C"] --> C
    C --> E["Cache hit"]
    C --> F["Cache miss"]
    F --> G["Database / Source of truth"]
    G --> C
~~~

Nhiều function instance có thể đọc cùng một cache service. Khi cache miss, ứng dụng đọc nguồn dữ liệu chuẩn rồi có thể lưu kết quả vào cache để lần đọc sau sử dụng.

Một số lợi ích thường gặp:

- Giảm số lần truy vấn database hoặc gọi API phụ thuộc.
- Giảm latency cho dữ liệu được đọc lặp lại.
- Hấp thụ một phần tải đọc tăng đột biến.
- Chia sẻ kết quả tính toán giữa nhiều function instance.
- Giảm chi phí nguồn dữ liệu khi cache hit đủ cao.

External cache cũng thêm một dịch vụ mạng vào đường đi của request. Nó có latency, quota, giới hạn kết nối, chi phí, yêu cầu bảo mật và khả năng gặp sự cố riêng. Nếu cache không khả dụng, ứng dụng cần biết có thể fallback về nguồn dữ liệu hay phải từ chối request.

**Cache không phải nguồn dữ liệu chuẩn.** Database hoặc dịch vụ nghiệp vụ mới là nơi quyết định dữ liệu đúng. Cache có thể bị xóa, hết hạn, eviction hoặc mất dữ liệu; ứng dụng phải có cách dựng lại giá trị từ nguồn chuẩn.

## 2. Khi nào nên dùng external cache?

Cache phù hợp khi dữ liệu được đọc nhiều, việc đọc nguồn có chi phí đáng kể và có thể chấp nhận một mức độ trễ cập nhật đã xác định.

Ví dụ:

- Thông tin sản phẩm hoặc danh mục được nhiều request đọc.
- Cấu hình ứng dụng ít thay đổi.
- Kết quả truy vấn tổng hợp tốn tài nguyên.
- Token hoặc metadata có thời hạn ngắn, nếu chính sách bảo mật cho phép.
- Dữ liệu tham chiếu được dùng bởi nhiều function.

Cache thường không phù hợp cho dữ liệu thay đổi liên tục mà yêu cầu mọi request phải nhìn thấy giá trị mới nhất ngay lập tức, hoặc cho dữ liệu có chi phí cache cao hơn lợi ích đọc lại. Không nên cache dữ liệu nhạy cảm hoặc dữ liệu theo quyền truy cập nếu cache key và phạm vi phân quyền chưa được thiết kế rõ.

| Tình huống | Cách cân nhắc |
|---|---|
| Đọc nhiều, cập nhật ít | Thường là ứng viên tốt cho cache |
| Đọc ít, cập nhật liên tục | Lợi ích có thể thấp; cân nhắc bỏ cache |
| Cần kết quả gần nhất theo yêu cầu nghiệp vụ | TTL ngắn hoặc invalidation đồng bộ; xác định rõ mức stale cho phép |
| Dữ liệu cá nhân hoặc theo tenant | Cần cache key chứa phạm vi truy cập và chính sách xóa phù hợp |
| Cache outage không được làm gián đoạn nghiệp vụ | Thiết kế fallback, giới hạn tải về nguồn và circuit breaker |

Trước khi thêm cache, hãy đo latency và tải ở nguồn dữ liệu. Cache không tự động làm hệ thống nhanh hơn nếu phần lớn request là cache miss, dữ liệu quá lớn, hoặc network hop tới cache đắt hơn truy vấn nguồn.

## 3. Các chiến lược đọc và ghi cache

### Cache-aside (lazy loading)

Ứng dụng chủ động kiểm tra cache. Nếu có dữ liệu, trả về cache. Nếu không có, đọc nguồn dữ liệu, lưu kết quả vào cache rồi trả về.

~~~mermaid
flowchart TD
    A["Request"] --> B["Đọc cache"]
    B --> C{"Có dữ liệu?"}
    C -->|Có| D["Trả cache"]
    C -->|Không| E["Đọc database"]
    E --> F["Ghi cache với TTL"]
    F --> G["Trả dữ liệu"]
~~~

Ưu điểm là chỉ cache dữ liệu thực sự được đọc. Ứng dụng kiểm soát rõ khi nào cache được nạp và khi nào bị xóa. Đổi lại, lần đọc đầu tiên sau khi cache miss sẽ chậm hơn và có thể có race condition nếu dữ liệu thay đổi trong lúc đang nạp cache.

### Read-through

Ứng dụng đọc qua một lớp cache; lớp đó tự tìm dữ liệu ở nguồn khi cache miss. Cách này gom logic nạp dữ liệu vào cache provider hoặc thư viện.

Read-through giúp consumer đơn giản hơn, nhưng cần một lớp cache có khả năng truy cập nguồn dữ liệu và hiểu cách chuyển đổi dữ liệu. Không phải mọi dịch vụ Redis hoặc Memcached đều tự cung cấp read-through; đôi khi đây là hành vi của một thư viện hoặc lớp ứng dụng.

### Write-through

Khi ghi dữ liệu, ứng dụng cập nhật nguồn chuẩn và cache theo một quy trình đồng bộ. Mục tiêu là cache được cập nhật ngay sau thay đổi.

Write-through có thể giảm cache stale, nhưng việc ghi cache và database thường không nằm trong cùng một transaction phân tán. Nếu một thao tác thành công và thao tác còn lại thất bại, hai nơi có thể lệch nhau. Cần quy định thứ tự ghi, retry và cách sửa sai.

### Write-behind (write-back)

Ứng dụng ghi vào cache trước, sau đó một tiến trình bất đồng bộ mới ghi dữ liệu xuống nguồn chuẩn.

Cách này có thể giảm độ trễ ghi và gom nhiều thay đổi, nhưng tạo rủi ro mất dữ liệu nếu cache hoặc tiến trình đồng bộ gặp sự cố trước khi ghi bền vững. Chỉ dùng khi chấp nhận được độ trễ đồng bộ và đã có cơ chế lưu bền, retry, theo dõi backlog và phục hồi. Không nên dùng cache thông thường làm nơi duy nhất giữ dữ liệu nghiệp vụ quan trọng.

| Chiến lược | Đường đọc | Đường ghi | Đặc điểm chính |
|---|---|---|---|
| Cache-aside | Ứng dụng kiểm tra cache, miss thì đọc nguồn | Cập nhật nguồn rồi invalidation hoặc cập nhật cache | Phổ biến, dễ kiểm soát |
| Read-through | Cache tự nạp từ nguồn khi miss | Tùy cơ chế cache | Gom logic nạp dữ liệu |
| Write-through | Đọc cache | Ghi nguồn và cache theo quy trình đồng bộ | Cache thường mới hơn, nhưng cần xử lý lỗi ghi kép |
| Write-behind | Đọc cache | Ghi cache trước, nguồn được cập nhật sau | Ghi nhanh hơn nhưng tăng rủi ro và độ phức tạp |

Với nhiều Java function xử lý request độc lập, cache-aside thường là điểm bắt đầu dễ hiểu: database vẫn là nguồn chuẩn, function chỉ nạp và xóa cache theo quy tắc nghiệp vụ.

## 4. TTL và invalidation

**TTL (time to live)** là thời gian một key được phép tồn tại trong cache. Khi hết TTL, cache service có thể coi giá trị là hết hạn và loại bỏ nó theo cơ chế của sản phẩm.

**Invalidation** là hành động làm cho một giá trị cache không còn được sử dụng, thường bằng cách xóa key hoặc thay đổi version của key.

Hai cơ chế bổ sung cho nhau:

- TTL đặt giới hạn trên cho tuổi của dữ liệu trong trường hợp invalidation bị bỏ lỡ.
- Invalidation loại bỏ dữ liệu cũ sớm hơn khi ứng dụng biết nguồn chuẩn vừa thay đổi.

### Chọn TTL theo mức stale cho phép

TTL không nên được chọn chỉ vì một con số thuận tiện. Hãy xác định dữ liệu có thể cũ tối đa bao lâu và tác động nghiệp vụ nếu người dùng nhìn thấy dữ liệu cũ.

| Loại dữ liệu | Ví dụ TTL ban đầu để thử nghiệm | Lưu ý |
|---|---:|---|
| Cấu hình ít thay đổi | 5–30 phút | Có thể invalidation khi cấu hình được publish |
| Danh mục hoặc thông tin sản phẩm | 1–10 phút | Xóa key sau khi cập nhật giá hoặc trạng thái |
| Kết quả tổng hợp tốn kém | 30 giây–5 phút | Chấp nhận kết quả gần đúng tùy dashboard |
| Metadata tạm thời | Vài giây–vài phút | TTL không được vượt quá thời hạn nghiệp vụ |
| Dữ liệu yêu cầu tính mới rất cao | Không cache hoặc TTL rất ngắn | Cần đánh giá yêu cầu consistency |

Các khoảng trên chỉ là điểm bắt đầu để đo, không phải mặc định phù hợp cho mọi hệ thống.

### Invalidate sau khi commit dữ liệu nguồn

Với cache-aside, một quy tắc phổ biến là:

1. Cập nhật database.
2. Xác nhận transaction đã commit.
3. Xóa cache key tương ứng.
4. Request tiếp theo đọc lại nguồn và nạp giá trị mới.

Không nên xóa cache trước khi transaction commit. Nếu transaction rollback, cache có thể bị nạp lại từ dữ liệu cũ hoặc một request đồng thời có thể đọc trạng thái chưa commit.

Có một race condition tinh vi hơn: request A đọc dữ liệu cũ từ database; request B cập nhật database và xóa cache; sau đó request A ghi dữ liệu cũ vào cache. Cache lại chứa giá trị cũ dù invalidation đã chạy. Có thể giảm rủi ro bằng versioned key, conditional write theo version, khóa nạp cache hoặc TTL ngắn; lựa chọn phụ thuộc yêu cầu consistency và tải.

### Invalidation bằng sự kiện

Khi database commit, ứng dụng có thể phát event ProductUpdated để consumer xóa hoặc cập nhật cache liên quan. Đây là cách hữu ích khi nhiều function hoặc dịch vụ cùng sử dụng cache.

Tuy nhiên, ghi database và publish event là hai thao tác độc lập. Nếu database commit thành công nhưng publish thất bại, cache có thể không được xóa. **Transactional outbox** giúp ghi thay đổi nghiệp vụ và bản ghi cần phát event trong cùng transaction; một publisher riêng gửi outbox event và retry đến khi thành công.

Luồng minh họa:

~~~mermaid
flowchart TD
    A["Cập nhật dữ liệu"] --> B["DB transaction"]
    B --> C["Ghi outbox event"]
    C --> D["Commit"]
    D --> E["Outbox publisher"]
    E --> F["ProductUpdated event"]
    F --> G["Cache invalidation consumer"]
    G --> H["Xóa hoặc version hóa key"]
~~~

Consumer invalidation cũng cần idempotent: xóa một key nhiều lần phải an toàn. Nếu event có thể đến trễ hoặc sai thứ tự, version dữ liệu giúp tránh một event cũ làm ghi đè cache mới.

## 5. Cache key: phạm vi, phiên bản và bảo mật

Cache key quyết định hai request có dùng chung một giá trị hay không. Nếu key thiếu một yếu tố ảnh hưởng đến kết quả, ứng dụng có thể trả dữ liệu sai hoặc lộ dữ liệu giữa người dùng.

Một cache key nên thể hiện:

- Loại dữ liệu và phiên bản schema.
- Tenant hoặc tổ chức nếu dữ liệu được phân tách theo tenant.
- Định danh bản ghi.
- Các tham số làm thay đổi kết quả, ví dụ locale, currency hoặc quyền truy cập.
- Phiên bản dữ liệu nếu cần chống stale write.

Ví dụ:

~~~text
product:v2:tenant-42:product-1042:vi-VN
profile:v1:tenant-42:user-781
catalog:v3:tenant-42:category-18:page-2
~~~

Không đưa access token, mật khẩu, secret hoặc dữ liệu nhạy cảm vào key. Tránh dùng nguyên văn chuỗi do client kiểm soát nếu chuỗi đó có thể quá dài hoặc chứa ký tự gây khó vận hành. Có thể chuẩn hóa hoặc hash các tham số phức tạp.

Đặc biệt, không cache response đã cá nhân hóa bằng một key chỉ chứa URL nếu response phụ thuộc vào người dùng hoặc role. Ví dụ, giá hiển thị theo nhóm khách hàng phải đưa customer segment vào key hoặc cache ở phạm vi an toàn tương đương.

### Version hóa key

Khi cấu trúc dữ liệu thay đổi, cache cũ có thể không deserialize được hoặc thiếu field mới. Thêm version vào key như product:v2 giúp ứng dụng chuyển sang schema mới mà không phải xóa mọi key cũ ngay lập tức. Key version cũ sẽ hết TTL hoặc được dọn theo chính sách.

Version key cũng có thể dùng để invalidation theo nhóm: cập nhật một generation/version cho tenant hoặc danh mục, khiến request mới đọc namespace mới. Cách này tránh phải xóa hàng nghìn key riêng lẻ, nhưng cần quản lý version và tránh race khi thay đổi đồng thời.

## 6. Cache stampede và các race condition

### Cache stampede

Khi một key phổ biến hết hạn, nhiều request đồng thời có thể cùng nhận cache miss và cùng truy vấn database. Một đợt tải lớn có thể dồn xuống nguồn dữ liệu đúng lúc cache không còn giúp ích.

Các biện pháp giảm stampede:

- **TTL jitter:** cộng hoặc trừ một khoảng ngẫu nhiên nhỏ để nhiều key không hết hạn cùng lúc.
- **Single-flight / request coalescing:** chỉ một request nạp một key; các request còn lại chờ kết quả.
- **Distributed lock:** một instance giữ quyền nạp key trong thời gian ngắn; các instance khác chờ hoặc dùng dữ liệu stale nếu chính sách cho phép.
- **Stale-while-revalidate:** trả giá trị cũ trong giới hạn cho phép trong khi một request làm mới cache.
- **Pre-warming:** nạp trước các key quan trọng trước một thời điểm tải cao có thể dự đoán.

Distributed lock cần lease, timeout và cách xử lý khi chủ lock chết. Không nên giữ lock lâu hơn thời gian xử lý dự kiến hoặc để request chờ không giới hạn.

### Cache stale do request chạy đồng thời

Cache-aside có thể gặp thứ tự sau:

1. Request A đọc phiên bản 10 từ database.
2. Request B ghi phiên bản 11 vào database và xóa cache.
3. Request A ghi phiên bản 10 vào cache sau khi B đã xóa.

Kết quả là cache lại cũ. Nếu yêu cầu consistency nghiêm ngặt, có thể dùng version trong value và chỉ cho phép ghi cache khi version không thấp hơn version hiện tại; hoặc dùng key theo version của bản ghi. Một cách đơn giản hơn là TTL ngắn kết hợp invalidation, nhưng vẫn có một khoảng stale có thể quan sát được.

### Cache outage

Nếu external cache mất kết nối, function có thể fallback về database. Nhưng nếu mọi invocation đồng thời đều fallback, database có thể bị quá tải.

Cần cân nhắc:

- Timeout kết nối cache ngắn và có giới hạn.
- Circuit breaker để ngừng gọi cache liên tục khi service lỗi.
- Giới hạn concurrency hoặc rate ở đường fallback.
- Dùng stale value nếu nghiệp vụ cho phép.
- Cảnh báo khi cache error rate tăng và theo dõi tải nguồn dữ liệu.

Không nên để cache outage biến thành một vòng retry vô hạn hoặc làm function giữ kết nối quá lâu.

## 7. Ví dụ Java: cache-aside với Redis

Ví dụ sau dùng Spring Data Redis với StringRedisTemplate và Jackson ObjectMapper. Database là nguồn dữ liệu chuẩn. Cache lỗi thì service vẫn thử đọc database; lỗi ghi cache không làm request đọc thất bại.

Ví dụ dùng Java record (Java 16 trở lên) và giả định ProductRepository trả về một ProductView đã được đọc từ nguồn chuẩn.

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.time.Duration;

public record ProductView(
        String productId,
        String name,
        long price,
        String currency,
        long version) {
}

public interface ProductRepository {
    ProductView findById(String tenantId, String productId);
}

public final class ProductCacheService {
    private static final Duration TTL = Duration.ofMinutes(5);

    private final StringRedisTemplate redis;
    private final ObjectMapper objectMapper;
    private final ProductRepository repository;

    public ProductCacheService(
            StringRedisTemplate redis,
            ObjectMapper objectMapper,
            ProductRepository repository) {
        this.redis = redis;
        this.objectMapper = objectMapper;
        this.repository = repository;
    }

    public ProductView get(String tenantId, String productId) {
        String key = key(tenantId, productId);

        try {
            String cached = redis.opsForValue().get(key);
            if (cached != null) {
                try {
                    return objectMapper.readValue(cached, ProductView.class);
                } catch (JsonProcessingException invalidCacheValue) {
                    redis.delete(key);
                }
            }
        } catch (DataAccessException cacheUnavailable) {
            // Ghi log/metric; tiếp tục đọc nguồn chuẩn.
        }

        ProductView product = repository.findById(tenantId, productId);
        if (product == null) {
            return null;
        }

        try {
            String json = objectMapper.writeValueAsString(product);
            redis.opsForValue().set(key, json, TTL);
        } catch (DataAccessException | JsonProcessingException cacheWriteFailed) {
            // Cache là tối ưu hiệu năng; dữ liệu chuẩn đã được đọc thành công.
        }

        return product;
    }

    // Gọi sau khi transaction cập nhật product đã commit.
    public void invalidateAfterCommit(String tenantId, String productId) {
        redis.delete(key(tenantId, productId));
    }

    private String key(String tenantId, String productId) {
        return "product:v2:" + tenantId + ":" + productId;
    }
}
~~~

Đoạn code minh họa các nguyên tắc sau:

- Key có tenant và schema version.
- Cache hit trả dữ liệu đã deserialize.
- Cache value hỏng được xóa để lần sau nạp lại.
- Cache unavailable hoặc cache write lỗi không làm mất khả năng đọc nguồn chuẩn.
- TTL giới hạn tuổi của cache.
- Invalidation là thao tác riêng và phải được gọi sau khi transaction nguồn commit.

Trong ứng dụng Spring có thể dùng transaction synchronization hoặc event listener chạy ở phase AFTER_COMMIT để gọi invalidation. Nếu không thể chấp nhận trường hợp commit thành công nhưng invalidation thất bại, hãy ghi invalidation event vào transactional outbox và retry đến khi consumer xử lý được.

Ví dụ này chưa bao gồm distributed lock, version-conditional write hoặc negative caching. Hãy bổ sung khi số liệu tải và yêu cầu consistency cho thấy cần thiết.

## 8. Negative caching và dữ liệu không tồn tại

Nếu một ID không tồn tại, cache-aside đơn giản thường không lưu gì. Khi client liên tục hỏi cùng một ID sai, mỗi request lại truy vấn database. **Negative caching** lưu dấu hiệu “không tìm thấy” trong một khoảng TTL ngắn.

Cần phân biệt giá trị không tồn tại với cache miss. Có thể dùng một sentinel hoặc envelope có trường found=false. TTL của negative cache thường ngắn hơn dữ liệu bình thường vì bản ghi có thể vừa được tạo sau lần kiểm tra trước.

Không nên negative-cache lỗi timeout, lỗi quyền truy cập hoặc lỗi hệ thống nguồn như thể dữ liệu không tồn tại. Nếu làm vậy, một sự cố tạm thời có thể biến thành kết quả “không tìm thấy” kéo dài.

Khi tạo mới bản ghi, phải invalidation negative cache tương ứng sau commit để request tiếp theo nhìn thấy bản ghi mới.

## 9. Quan sát và vận hành external cache

Một cache có hit ratio cao chưa chắc đã tốt nếu nó trả dữ liệu quá cũ hoặc chi phí vận hành lớn. Hãy theo dõi cả hiệu quả, độ mới và sức khỏe của dịch vụ.

| Chỉ số | Ý nghĩa | Dấu hiệu cần xem xét |
|---|---|---|
| Cache hit ratio | Tỷ lệ request đọc được cache | Thấp kéo dài có thể do TTL quá ngắn, key phân mảnh hoặc dữ liệu ít được đọc lại |
| Cache miss rate | Tỷ lệ phải đọc nguồn | Tăng đột biến có thể do flush, expiry đồng loạt hoặc lỗi cache |
| Cache latency | Thời gian đọc/ghi cache | Tăng có thể do network, connection pool hoặc tải cache |
| Eviction rate | Số key bị loại do thiếu bộ nhớ/chính sách eviction | Tăng có thể cho thấy dung lượng hoặc TTL chưa phù hợp |
| Key age / stale age | Tuổi của giá trị được trả | Cao có thể vượt mức stale nghiệp vụ cho phép |
| Invalidation lag | Thời gian từ DB commit đến cache invalidation | Cao làm tăng cửa sổ dữ liệu cũ |
| Cache error rate | Tỷ lệ thao tác cache lỗi | Tăng có thể khiến tải dồn về database |
| Cost per useful hit | Chi phí cache so với số lần cache hit hữu ích | Giúp đánh giá cache có đáng duy trì không |

Không ghi toàn bộ cache value, token hoặc thông tin cá nhân vào log. Log nên có key đã rút gọn hoặc hash, tenant ID theo chính sách bảo mật, thao tác, kết quả và correlation ID.

### Cấu hình và bảo mật

External cache là dịch vụ mạng. Cần:

- Đặt cache trong network boundary phù hợp và chỉ cho phép function cần thiết truy cập.
- Dùng TLS và cơ chế xác thực được hỗ trợ.
- Quản lý secret qua secret manager hoặc cơ chế danh tính của nền tảng.
- Tách quyền đọc/ghi nếu sản phẩm hỗ trợ.
- Giới hạn kích thước value, TTL và số kết nối.
- Theo dõi memory usage, eviction, connection count và quota.
- Xác định chính sách backup hoặc persistence nếu có nhu cầu; không nhầm backup cache với backup nguồn dữ liệu chuẩn.

Trong serverless, mỗi function instance có thể mở kết nối riêng đến cache. Khi concurrency tăng đột biến, số kết nối cũng có thể tăng nhanh. Nên dùng client có quản lý connection phù hợp, tái sử dụng client trong vòng đời execution environment khi runtime cho phép và đặt giới hạn concurrency. Kiểm tra giới hạn connection của cache service trước khi tăng quy mô function.

## 10. Checklist thiết kế cache

- [ ] Đã xác định nguồn dữ liệu chuẩn và dữ liệu nào có thể tái tạo.
- [ ] Có lý do đo được để cache: latency, tải đọc hoặc chi phí nguồn.
- [ ] Đã chọn cache-aside, read-through, write-through hoặc write-behind.
- [ ] TTL phản ánh mức stale tối đa nghiệp vụ chấp nhận.
- [ ] Invalidation diễn ra sau commit hoặc qua outbox có retry.
- [ ] Cache key bao gồm tenant, locale, role hoặc tham số ảnh hưởng kết quả khi cần.
- [ ] Có version hóa key khi schema thay đổi.
- [ ] Đã xử lý cache miss đồng thời, stampede và stale write.
- [ ] Cache outage có timeout, fallback và giới hạn tải về nguồn.
- [ ] Negative caching không nhầm dữ liệu vắng mặt với lỗi hệ thống.
- [ ] Có metric hit ratio, latency, eviction, invalidation lag và error rate.
- [ ] Cache được bảo vệ bằng network policy, TLS, authentication và secret management.
- [ ] Đã kiểm thử update, delete, expiry, cache outage, race condition và dữ liệu theo tenant.

## Tự kiểm tra

1. Vì sao cache trong RAM của một Java function instance không thay thế được external cache khi FaaS mở rộng thành nhiều instance?
2. Cache-aside xử lý cache miss theo những bước nào?
3. Vì sao TTL và invalidation cần được dùng bổ sung cho nhau?
4. Mô tả race condition khiến request đọc dữ liệu cũ ghi lại cache sau khi một request khác đã invalidation.
5. Transactional outbox giúp giảm rủi ro gì khi invalidation được phát qua event?
6. Vì sao cache key cần chứa tenant hoặc các tham số phân quyền?
7. Cache stampede xảy ra khi nào và có thể giảm bằng những kỹ thuật nào?
8. Khi cache outage, fallback về database có thể tạo ra rủi ro gì?

External cache giúp nhiều Java function instance chia sẻ dữ liệu đọc thường xuyên và giảm tải cho nguồn chuẩn. Để cache không làm sai nghiệp vụ, đội phát triển cần xác định mức stale cho phép, chọn TTL, invalidation sau commit, thiết kế key đúng phạm vi và xử lý các tình huống đồng thời. Khi cache được xem là bản sao có thể tái tạo, có metric và có đường fallback rõ ràng, nó trở thành một tối ưu hiệu năng có kiểm soát trong kiến trúc serverless.

