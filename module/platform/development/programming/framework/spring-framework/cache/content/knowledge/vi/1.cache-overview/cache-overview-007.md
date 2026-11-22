# Đánh đổi giữa tốc độ, bộ nhớ và độ mới của dữ liệu

Trong Spring Framework, cache giúp trả lời nhiều lần đọc từ một kết quả đã tính hoặc đã tải trước đó. Đổi lại, ứng dụng phải giữ thêm dữ liệu, có thể trả về bản cũ, và phải quản lý vòng đời của các bản sao. Ba mục tiêu thường xung đột là **tốc độ phản hồi**, **mức sử dụng bộ nhớ** và **độ mới (freshness) của dữ liệu**. Thiết kế cache tốt bắt đầu bằng việc xác định dữ liệu nào được phép cũ bao lâu, sau đó mới chọn kích thước cache và chính sách hết hạn.

## 1. Cache thay đổi luồng đọc như thế nào?

Với mô hình **cache-aside/read-through ở tầng ứng dụng** thường gặp khi dùng Spring Cache:

1. Yêu cầu đọc đi vào phương thức được đánh dấu **@Cacheable**.
2. Spring tạo khóa từ tham số và hỏi cache được cấu hình qua **CacheManager**.
3. Nếu **hit**, Spring trả dữ liệu đã lưu, thường bỏ qua thân phương thức.
4. Nếu **miss**, phương thức đọc cơ sở dữ liệu/dịch vụ nguồn; kết quả đủ điều kiện được đưa vào cache để dùng cho các lần sau.
5. Khi dữ liệu nguồn thay đổi, cache có thể tiếp tục giữ phiên bản cũ cho đến khi bị cập nhật, xóa hoặc hết hạn.

~~~text
Client ──> Spring @Cacheable ──> Cache lookup
                                    ├── HIT  ──> Bản sao trong cache ──> Client
                                    └── MISS ──> Nguồn dữ liệu ──> Lưu cache ──> Client

Write ──> Nguồn dữ liệu thay đổi ──> Cần chiến lược invalidation/update cache
~~~

**Spring Cache là lớp trừu tượng về thao tác cache**, không phải một engine lưu trữ với TTL, dung lượng hay cơ chế đồng bộ cố định. Các chính sách đó do nhà cung cấp như Caffeine, Redis hoặc một giải pháp khác đảm nhận. Vì vậy, cùng một annotation có thể cho đặc tính độ trễ, bộ nhớ và nhất quán khác nhau tùy cấu hình thực tế.

## 2. Ba trục đánh đổi

| Trục | Lợi ích khi tối ưu | Chi phí/rủi ro đi kèm |
| --- | --- | --- |
| **Tốc độ** | Hit nhanh; giảm truy vấn DB, mạng và CPU; giảm tải hệ thống nguồn | Cần thêm RAM/không gian lưu; việc làm mới, đồng bộ và đo lường có chi phí |
| **Bộ nhớ** | Giữ nhiều khóa nóng hơn, thường tăng hit ratio | Tăng heap, GC hoặc chi phí Redis; có thể giữ dữ liệu ít được dùng |
| **Độ mới** | TTL ngắn hoặc invalidation sớm giúp giảm khoảng thời gian dữ liệu cũ tồn tại | Tăng miss, lượt tải lại, áp lực lên DB; invalidation phân tán có thể phức tạp |

Một phép ước lượng cho đường đọc đồng nhất:

~~~text
Độ trễ trung bình ≈ hitRatio × latencyHit + (1 − hitRatio) × latencyMiss
~~~

Giả sử 90% lượt đọc hit với 2 ms và 10% miss với 80 ms: trung bình khoảng **9,8 ms**. Đây là minh họa có giả định, không phải dự đoán hiệu năng. Khi đánh giá thật, còn phải tính thời gian lookup, serialization, network, đuôi phân phối **p95/p99**, số yêu cầu đồng thời, tốc độ thay đổi khóa và độ trễ nguồn khi bị tải tăng.

Bộ nhớ cũng cần được tính theo **khóa + giá trị + metadata/overhead + bộ đệm liên quan**. Ví dụ 100.000 giá trị trung bình 2 KiB tương đương gần 195 MiB *chỉ riêng payload*, chưa gồm đối tượng Java, metadata cache và bản sao giữa nhiều instance. Giới hạn **maximumSize** của Caffeine là số entry, không đồng nghĩa với giới hạn byte. Nếu kích thước các entry chênh nhau lớn, cân nhắc **maximumWeight** với weigher phù hợp và đo heap thực tế.

## 3. Tại sao tăng tốc thường làm dữ liệu kém mới?

Giả sử lúc **10:00:00** API đọc giá sản phẩm từ DB là 100 và đưa vào cache với **expireAfterWrite = 5 phút**. Lúc **10:00:01**, một hệ thống khác đổi giá DB thành 120. Nếu không có invalidation/update cache, các lượt đọc trước khi entry hết hạn vẫn có thể nhận giá 100. TTL không tự theo dõi thời điểm cập nhật DB. Với expiration tính từ lúc ghi cache, lần thay đổi nguồn ngay sau khi nạp có thể khiến bản sao cũ tồn tại gần trọn một chu kỳ TTL.

Giảm TTL xuống 10 giây thu hẹp khoảng stale tiềm năng, nhưng cũng khiến nhiều entry bị tải lại; nếu có hàng nghìn khóa nóng cùng hết hạn, lượng miss có thể tăng đột ngột. Tăng TTL lên 30 phút thường giúp cache giữ dữ liệu lâu hơn và giảm số lần gọi nguồn, nhưng rủi ro trả bản cũ cũng lớn hơn.

Phải phân biệt:

- **Freshness**: kết quả đủ mới theo yêu cầu nghiệp vụ; ví dụ bảng xếp hạng được phép trễ 1 phút.
- **Staleness**: mức lạc hậu so với trạng thái chuẩn ở nguồn; nên đo cả *tuổi entry* lẫn *độ trễ phản ánh cập nhật*.
- **Expiration/TTL**: quy tắc một entry không còn được dùng sau một mốc thời gian tính theo cơ chế provider. Đây không phải bảo đảm nhất quán tức thời.
- **Eviction**: xóa entry vì hết hạn, vượt sức chứa hoặc lệnh chủ động; entry có thể bị đuổi trước TTL.
- **Invalidation**: loại bỏ bản sao không còn đáng tin khi nguồn dữ liệu thay đổi.
- **Refresh**: lấy dữ liệu mới để thay bản cũ; tùy provider, trong lúc refresh có thể vẫn phục vụ giá trị cũ.

Với Caffeine, **expireAfterWrite** tính từ lần tạo/cập nhật entry; **expireAfterAccess** tính từ lần truy cập gần nhất, nên một entry được đọc liên tục có thể còn tồn tại rất lâu nếu chỉ dùng expire-after-access. **refreshAfterWrite** áp dụng cho loading cache có cơ chế nạp lại; entry trở thành đủ điều kiện refresh theo tuổi, việc refresh thường được kích hoạt khi được truy cập và có thể trả bản cũ trong lúc tải mới. Không được hiểu rằng đặt một tham số refresh trên annotation Spring thông thường sẽ tự có cơ chế stale-while-revalidate.

## 4. Những nút điều chỉnh chính

| Quyết định | Thường cải thiện | Điều phải kiểm tra |
| --- | --- | --- |
| Tăng sức chứa/giữ nhiều khóa nóng | Tăng hit ratio, giảm tải nguồn | RAM/heap, GC, chi phí, hiệu quả tăng thêm có đáng không |
| Giảm sức chứa hoặc áp dụng eviction theo dung lượng | Giới hạn chi phí bộ nhớ | Miss do đuổi khóa nóng; nguồn có chịu được không |
| TTL dài | Giảm lượt nạp lại | Khoảng stale sau cập nhật nguồn có chấp nhận được không |
| TTL ngắn | Thu hẹp thời gian dữ liệu cũ được giữ | Hit ratio giảm, nguy cơ cache stampede và tải DB tăng |
| Invalidate khi ghi thành công | Giá trị mới được nhìn thấy sớm hơn | Có bỏ sót đường ghi, race condition hoặc node khác không |
| Chủ động làm nóng/preload | Giảm cold miss sau khởi động | Có làm tăng bộ nhớ và gây tải đầu đợt không |
| Refresh nền / stale-while-revalidate do provider hỗ trợ | Giảm độ trễ đọc khi làm mới | Có chấp nhận trả dữ liệu cũ trong khoảng refresh không |
| Giới hạn key cardinality, tránh lưu entry quá lớn | Tiết kiệm bộ nhớ và serialization | Có làm mất các mẫu truy cập thực sự nóng không |

**Không có một TTL “chuẩn” cho mọi cache.** Một giá trị tốt phụ thuộc tốc độ cập nhật nguồn, mức chấp nhận sai lệch của người dùng, tần suất đọc, kích thước kết quả và cách xử lý khi cache/DB lỗi.

## 5. Local cache, distributed cache và ảnh hưởng đến ba trục

| Tiêu chí | Caffeine trong tiến trình Spring | Redis dùng chung |
| --- | --- | --- |
| Đường đọc hit | Trong bộ nhớ JVM, thường rất nhanh | Qua kết nối mạng và serialization, thường tốn thêm độ trễ |
| Dung lượng | Từ heap/budget của từng instance | Từ bộ nhớ Redis và cấu hình hạ tầng |
| Nhiều instance | Mỗi JVM có bản sao và chính sách eviction riêng | Nhiều instance có thể dùng một tập dữ liệu cache chung |
| Độ mới khi một node cập nhật nguồn | Evict trong node đó không tự evict các node khác | Evict khóa chung giúp thống nhất hơn, nhưng vẫn phải xử lý thứ tự ghi và race |
| Vận hành | Đơn giản, nhưng áp lực GC/heap | Thêm mạng, độ sẵn sàng, giám sát, serializer và bảo mật |

Ví dụ một dịch vụ có **4 replica** và mỗi replica giữ tối đa 10.000 entry Caffeine: con số đó là **10.000 mỗi instance**, không phải 10.000 cho cả cụm. Cùng một khóa có thể tồn tại ở cả 4 nơi. Nếu một replica cập nhật DB và chỉ xóa cache cục bộ, ba replica còn lại vẫn có thể trả bản cũ cho đến lúc TTL hết. Khi cần phản ánh thay đổi trên toàn cụm, xem xét cache dùng chung hoặc thông báo invalidation được xử lý ở mọi replica; cả hai đều cần kiểm thử race, thất lạc thông báo và lỗi mạng.

Cache nhiều tầng (local Caffeine phía trước Redis) có thể giảm latency thêm nhưng tạo thêm bản sao và thêm bài toán invalidation. Chỉ dùng khi lợi ích đo được bù đắp độ phức tạp.

## 6. Minh họa Spring Framework với Caffeine

Ví dụ sau minh họa một **chính sách ban đầu để thử nghiệm**: tối đa 10.000 entry cho cache chi tiết sản phẩm; mỗi entry hết hạn 2 phút sau khi được ghi. Dự án cần các thư viện Spring Cache/Spring Context Support và Caffeine tương thích; với ứng dụng Spring Boot có thể dùng dependency cache starter và Caffeine. Đoạn mã là các thành phần của một ứng dụng Spring đã có cấu hình DI/repository, **không phải một chương trình Java độc lập**.

~~~java
// CacheConfiguration.java
package demo.cache;

import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Duration;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfiguration {
    @Bean
    public CacheManager cacheManager() {
        CaffeineCacheManager manager = new CaffeineCacheManager("productDetails");
        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(10_000)
                .expireAfterWrite(Duration.ofMinutes(2))
                .recordStats());
        return manager;
    }
}
~~~

~~~java
// ProductService.java
package demo.cache;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final ProductGateway gateway;

    public ProductService(ProductGateway gateway) {
        this.gateway = gateway;
    }

    @Cacheable(cacheNames = "productDetails",
               key = "#id", unless = "#result == null")
    public ProductView findById(String id) {
        return gateway.load(id);
    }

    @CacheEvict(cacheNames = "productDetails", key = "#id")
    public void changePrice(String id, long newPriceInCents) {
        gateway.changePrice(id, newPriceInCents);
    }
}

// Các kiểu miền của ứng dụng; gateway cần một implementation thực tế.
interface ProductGateway {
    ProductView load(String id);
    void changePrice(String id, long newPriceInCents);
}
record ProductView(String id, long priceInCents) {}
~~~

Ý nghĩa của từng phần:

1. **@EnableCaching** kích hoạt xử lý annotation thông qua cơ chế Spring; chỉ gắn annotation mà không bật chức năng thì không tạo cache.
2. **@Cacheable** bỏ qua tải từ gateway khi khóa đã có. **unless** giúp tránh lưu kết quả null trong ví dụ. Một khóa phải bao hàm mọi yếu tố ảnh hưởng đến kết quả, như locale/tenant/permission nếu có.
3. **maximumSize(10_000)** đặt giới hạn số entry Caffeine; cần kiểm tra kích thước object thật để suy ra ngân sách RAM.
4. **expireAfterWrite(2 phút)** hạn chế tuổi entry trong cache, nhưng không đảm bảo dữ liệu vẫn đúng trong 2 phút đó.
5. **@CacheEvict** xóa entry tương ứng **sau khi phương thức hoàn thành bình thường** theo mặc định. Khi có transaction DB, thứ tự commit và evict phải được thiết kế riêng để tránh trường hợp cache bị xóa nhưng một luồng khác nạp bản DB chưa commit rồi giữ lại; cân nhắc cơ chế invalidation sau commit.
6. **recordStats()** cho Caffeine thu thập thống kê nội bộ; muốn đưa chúng vào hệ thống quan sát phải nối với công cụ metrics thích hợp. Bản thân lệnh này không tự cung cấp dashboard.

Ví dụ không nhằm bảo đảm rằng mọi cập nhật đều tức thời, nhất là khi có nhiều replica hoặc đường ghi khác bỏ qua ProductService. Nếu việc mua hàng yêu cầu giá tuyệt đối mới, hãy xác nhận giá tại nguồn ở bước chốt giao dịch thay vì tin vào bản cache phục vụ màn hình.

**Lưu ý proxy Spring:** Trong chế độ proxy thường dùng, lời gọi từ một method sang method được gắn **@Cacheable** ngay trong cùng object (**self-invocation**) không qua proxy nên không kích hoạt caching. **@Cacheable(sync = true)** có thể giảm nhiều tải trùng một khóa khi miss đồng thời nếu provider hỗ trợ, nhưng nó có các giới hạn khi kết hợp annotation khác/điều kiện **unless**; không tự coi đó là khóa phân tán toàn hệ thống.

## 7. Chương trình Java 17 tự chạy: bản cũ, TTL và invalidation

Đây là một mô hình nhỏ, **không sử dụng Spring** để tách bạch cơ chế cốt lõi. Đồng hồ ảo cho phép tái hiện chính xác các lượt đọc mà không phải chờ 60 giây. Mã chỉ minh họa một khóa, chưa có giới hạn dung lượng hoặc an toàn đa luồng của cache thực tế.

~~~java
// CacheTradeoffDemo.java
import java.util.HashMap;
import java.util.Map;

public class CacheTradeoffDemo {
    private record Entry(int price, long expiresAtMs) {}

    private static long nowMs = 0;
    private static int databasePrice = 100;
    private static final Map<String, Entry> cache = new HashMap<>();

    private static String readPrice() {
        Entry item = cache.get("product-1");
        if (item != null && nowMs < item.expiresAtMs()) {
            return item.price() + " (hit)";
        }
        cache.put("product-1", new Entry(databasePrice, nowMs + 60_000));
        return databasePrice + " (miss)";
    }

    public static void main(String[] args) {
        System.out.println("1: " + readPrice());
        System.out.println("2: " + readPrice());

        databasePrice = 120;              // Nguồn đổi, cache chưa biết.
        System.out.println("3: " + readPrice());

        nowMs = 61_000;                   // Đã qua TTL 60 giây.
        System.out.println("4: " + readPrice());

        databasePrice = 140;
        cache.remove("product-1");        // Invalidate ngay khi ghi nguồn.
        System.out.println("5: " + readPrice());
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac CacheTradeoffDemo.java
java CacheTradeoffDemo
~~~

Kết quả chuẩn:

~~~text
1: 100 (miss)
2: 100 (hit)
3: 100 (hit)
4: 120 (miss)
5: 140 (miss)
~~~

Lần 3 trả **100 dù DB đã là 120** vì cache chưa hết hạn. Lần 4 nhận 120 vì TTL 60 giây đã hết. Lần 5 nhận 140 ngay sau invalidation, đổi lại phải tải nguồn một lần nữa. Mô hình này thể hiện rõ: dữ liệu càng được tái sử dụng, lượt miss càng ít, nhưng bản sao có thể chậm cập nhật nếu thiếu quy tắc làm mới.

## 8. Chọn chính sách theo tính chất dữ liệu

| Dữ liệu/tình huống | Yêu cầu độ mới | Hướng thiết kế nên thử | Cảnh báo |
| --- | --- | --- | --- |
| Danh mục ít thay đổi, nội dung giới thiệu | Chấp nhận trễ vài phút | TTL vài phút, cache đủ chứa hot keys, evict khi CMS cập nhật | Không chọn TTL chỉ theo cảm tính; kiểm tra tần suất sửa nội dung |
| Bảng xếp hạng/analytics gần thời gian thực | Chấp nhận độ trễ công bố xác định | Làm mới theo chu kỳ, phiên bản snapshot, hoặc TTL phù hợp | Phải ghi rõ mốc cập nhật cho người dùng |
| Trang chi tiết sản phẩm | Có thể chấp nhận bản cũ ngắn | Cache đọc + evict khi sửa giá/thông tin | Đường ghi ngoài ứng dụng cũng phải invalidate |
| Tồn kho, hạn mức, quyền truy cập, giá chốt đơn | Có thể đòi hỏi dữ liệu hiện hành | Bỏ cache ở quyết định quan trọng hoặc kiểm tra lại nguồn | TTL ngắn không biến cache thành cơ chế nhất quán mạnh |
| Dữ liệu lớn, mỗi khóa ít khi lặp lại | Ít cơ hội hit | Không cache hoặc giới hạn chặt và lọc đối tượng được cache | Giữ mọi kết quả làm tốn RAM mà không giảm tải đáng kể |

Một thiết kế có thể dùng **hai đường đọc khác nhau cho cùng dữ liệu**: hiển thị sản phẩm được phép đọc từ cache để nhanh, nhưng thao tác đặt hàng sẽ xác nhận giá và tồn kho từ nguồn giao dịch. Điều này thường tốt hơn việc cố dùng một TTL cho mọi nghiệp vụ.

## 9. Đo lường rồi điều chỉnh: bài toán có ràng buộc

Trước khi thay TTL hoặc dung lượng, xác định bốn thứ:

- **Mục tiêu latency** (ví dụ p95 của endpoint và p95 thời gian truy vấn nguồn), không chỉ thời gian trung bình.
- **Freshness budget**: mức trễ tối đa được chấp nhận theo từng loại dữ liệu và đường đọc. Nếu cần dữ liệu chính xác ngay sau commit, TTL đơn lẻ không đủ.
- **Memory budget**: giới hạn heap mỗi instance hoặc RAM Redis, bao gồm overhead và chi phí nhân bản; đặt cảnh báo trước khi chạm ngưỡng.
- **Traffic/update pattern**: phân bố khóa nóng/lạnh, tần suất viết, tải cao điểm, số replica và hành vi khi DB/cache lỗi.

Các chỉ số nên theo dõi: **hit/miss ratio theo cache**, số và nguyên nhân eviction, dung lượng entry/heap, GC pause, latency hit/miss và p95/p99, request rate đến nguồn, cache reload đồng thời, thời gian dữ liệu trở nên nhìn thấy sau một cập nhật, số lần refresh lỗi, mức sử dụng Redis/network nếu có. Hit ratio cao không tự chứng minh cache tốt nếu hệ thống vẫn trả dữ liệu sai hoặc dùng quá nhiều RAM.

Quy trình thực nghiệm gợi ý:

1. Đo baseline **không cache**: độ trễ, DB QPS, tải CPU và bộ nhớ.
2. Chọn khóa đúng và tập dữ liệu đủ điều kiện cache; loại dữ liệu nhạy với nhất quán khỏi đường đọc stale.
3. Đặt **budget** ban đầu, chẳng hạn tối đa 10.000 entry và TTL 2 phút, sau đó chạy tải đại diện.
4. Thử thay **một biến mỗi lần**: TTL 30 giây → 2 phút → 5 phút, hoặc capacity 2.000 → 10.000, luôn kiểm tra cả độ trễ và mức stale.
5. Mô phỏng cập nhật nguồn ngay sau cache fill, nhiều ghi đồng thời, cache lạnh khi triển khai, nhiều instance và cache provider bị mất kết nối.
6. Chốt cấu hình dựa trên yêu cầu nghiệp vụ và SLO, theo dõi lại sau khi phân bố truy cập thay đổi.

**Ví dụ quyết định có số liệu giả định:** API đọc chi tiết sản phẩm đặt mục tiêu p95 dưới 50 ms, cho phép chậm cập nhật tối đa 2 phút ở màn hình xem, và ngân sách heap cache 256 MiB mỗi replica. Có thể thử Caffeine với **expireAfterWrite = 2 phút**, capacity được giới hạn bởi heap đo thực tế, kèm **@CacheEvict** ở đường ghi chính. Sau đó kiểm tra bằng đo thực nghiệm rằng số khóa nóng nằm trong giới hạn bộ nhớ, p95 đạt yêu cầu và mọi đường sửa sản phẩm đều có cơ chế làm mới. Không suy diễn rằng cấu hình mẫu tự động đáp ứng các con số này.

## 10. Lỗi phổ biến và câu hỏi tự kiểm tra

- **“TTL dài là dữ liệu luôn mới trong TTL.”** Sai: TTL chỉ xác định vòng đời bản cache; nguồn có thể đổi ngay sau cache fill.
- **“maximumSize = 10.000 nghĩa là RAM cố định.”** Sai: giá trị là số entry, còn footprint phụ thuộc loại key/value và overhead.
- **“Đã @CacheEvict ở một replica thì toàn bộ cụm hết stale.”** Sai với local cache độc lập. Cần chiến lược liên node hoặc kho cache dùng chung.
- **“Hit ratio càng cao càng tốt.”** Chưa đủ: phải đồng thời xem p95, nguồn tải, ngân sách bộ nhớ và tính đúng đắn.
- **“Tăng refresh sẽ luôn trả kết quả mới.”** Không chắc: một số refresh trả bản cũ trong lúc tải mới; hành vi phụ thuộc provider và cách tích hợp.
- **“Cache kết quả method bất kỳ đều an toàn.”** Không: method phụ thuộc thời gian, session, tenant, quyền hay trạng thái ngoài tham số dễ tạo key sai và rò rỉ kết quả giữa ngữ cảnh.
- **“Bật cache sẽ giải quyết mọi đợt tăng tải.”** Không: concurrent misses, cold start, hot keys và TTL đồng loạt có thể tạo **cache stampede**; cân nhắc giới hạn đồng thời nạp, làm nóng và phân tán thời điểm hết hạn.

Tự trả lời ba câu hỏi trước khi chọn chính sách: **(1)** Dữ liệu này được phép cũ bao lâu? **(2)** Cache lớn thêm 1 GiB sẽ tăng hit ratio bao nhiêu trên traffic thật? **(3)** Khi nguồn vừa thay đổi, những đường đọc nào phải thấy bản mới ngay, và ai chịu trách nhiệm invalidation? Nếu chưa có câu trả lời đo được, hãy bắt đầu nhỏ, đo và lặp.

### Tài liệu chính thức để đào sâu

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Cache annotations và cơ chế proxy: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — TTL và eviction phụ thuộc cache provider: https://docs.spring.io/spring-framework/reference/integration/cache/specific-config.html
- Caffeine — Eviction/Expiration: https://github.com/ben-manes/caffeine/wiki/Eviction
- Caffeine — Refresh: https://github.com/ben-manes/caffeine/wiki/Refresh
- Spring Data Redis — TTL/TTI cho Redis Cache: https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html
