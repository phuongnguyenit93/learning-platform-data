# Cache trong bộ nhớ và chiến lược làm mới sau restore

Cache trong bộ nhớ giúp ứng dụng Java giảm độ trễ bằng cách giữ dữ liệu thường dùng ngay trong tiến trình. Khi ứng dụng sử dụng CRaC (Coordinated Restore at Checkpoint), trạng thái heap được lưu trong checkpoint có thể mang theo cả những object cache đã được tạo trước đó. Sau restore, các object này có thể vẫn tồn tại, nhưng dữ liệu bên trong không tự động trở nên mới hoặc còn đúng với hệ thống nguồn.

Trong khoảng thời gian tiến trình bị checkpoint, dữ liệu ở database, dịch vụ bên ngoài, cấu hình, quyền truy cập và thời hạn nghiệp vụ vẫn tiếp tục thay đổi. Một cache entry có thể đã hết TTL, một bản ghi đã được cập nhật, một quyền đã bị thu hồi hoặc một endpoint đã thay đổi. Vì vậy, chiến lược cache sau restore cần trả lời hai câu hỏi riêng biệt: dữ liệu nào có thể giữ lại và dữ liệu nào phải kiểm tra, làm mới hoặc loại bỏ trước khi phục vụ request.

## 1. Cache trong bộ nhớ là gì?

Cache là vùng lưu tạm kết quả hoặc dữ liệu đã được tính toán để lần truy cập sau không phải thực hiện lại toàn bộ thao tác tốn kém. Trong Java, cache có thể là một Map, một thư viện cache, một cấu trúc dữ liệu chuyên dụng hoặc một lớp cache trong framework.

Ví dụ đơn giản:

~~~java
Map<String, Product> productCache = new ConcurrentHashMap<>();

public Product findProduct(String id) {
    return productCache.computeIfAbsent(
        id,
        productRepository::findById
    );
}
~~~

Lần đầu truy cập một sản phẩm, ứng dụng đọc từ repository và đưa kết quả vào cache. Những lần sau, ứng dụng có thể trả dữ liệu từ bộ nhớ.

Cache thường được dùng cho:

- Cấu hình ứng dụng ít thay đổi.
- Thông tin sản phẩm, danh mục hoặc dữ liệu tham chiếu.
- Kết quả truy vấn database.
- Metadata và schema.
- Kết quả tính toán tốn CPU.
- Token hoặc thông tin xác thực có thời hạn.
- DNS hoặc service discovery metadata.
- Nội dung được lấy từ API bên ngoài.

Cache giúp tăng tốc nhưng tạo thêm một bản sao dữ liệu. Bản sao này có thể khác dữ liệu gốc nếu không có chính sách cập nhật và invalidation rõ ràng.

### 1.1. Cache không phải nguồn dữ liệu chính

Một cache thông thường chỉ là bản sao phục vụ truy cập nhanh. Database, service hoặc kho dữ liệu gốc mới là nơi xác định trạng thái chính thức.

Nếu cache mất, ứng dụng thường có thể tải lại dữ liệu từ nguồn. Nếu cache chứa dữ liệu cũ, ứng dụng cần biết thời điểm nào được phép sử dụng dữ liệu đó và khi nào phải làm mới.

Không nên dùng cache trong heap làm nơi lưu trạng thái nghiệp vụ duy nhất nếu dữ liệu phải tồn tại qua restart, failover hoặc các lần triển khai. Với trạng thái quan trọng, hãy dùng database, message broker hoặc một kho lưu trữ bền vững phù hợp.

### 1.2. Các loại cache thường gặp

| Loại cache | Ví dụ | Đặc điểm |
|---|---|---|
| Cache dữ liệu tham chiếu | Danh mục, mã quốc gia | Thường ít thay đổi, có thể giữ lâu nếu có version |
| Cache truy vấn | Kết quả đọc database | Có thể stale khi dữ liệu nguồn thay đổi |
| Cache tính toán | Báo cáo, kết quả tổng hợp | Có thể tính lại khi cần |
| Cache cấu hình | Feature flag, endpoint | Có thể thay đổi độc lập với tiến trình |
| Cache xác thực | Access token, key metadata | Có thời hạn và yêu cầu bảo mật |
| Cache discovery | DNS, service registry | Phụ thuộc trạng thái mạng và endpoint |
| Cache phiên | Session, user context | Có thể phụ thuộc thời gian và trạng thái server |

Mỗi loại có thời gian sống và yêu cầu nhất quán khác nhau. Vì vậy, không nên áp dụng một chính sách refresh duy nhất cho toàn bộ cache của ứng dụng.

## 2. Điều gì xảy ra với cache khi checkpoint và restore?

CRaC lưu trạng thái tiến trình để có thể khôi phục ứng dụng từ một checkpoint. Các object trong heap, bao gồm Map, cache entry, timestamp và metadata, có thể nằm trong trạng thái được lưu.

Điều đó có nghĩa sau restore, ứng dụng có thể thấy lại dữ liệu đã được nạp trước checkpoint. Nhưng trong thời gian tiến trình bị checkpoint:

- Database có thể đã được cập nhật.
- Một bản ghi có thể đã bị xóa.
- Quyền truy cập có thể đã bị thu hồi.
- Feature flag có thể đã thay đổi.
- Token có thể hết hạn.
- Cache entry có thể vượt quá TTL.
- Dịch vụ bên ngoài có thể đổi endpoint hoặc version.
- Cache phân tán có thể đã nhận invalidation từ nơi khác trong khi tiến trình không hoạt động.

~~~mermaid
flowchart TD
    A["Ứng dụng đang chạy"] --> B["Nạp dữ liệu vào cache"]
    B --> C["Tạo checkpoint"]
    C --> D["Heap và cache được lưu"]
    D --> E["Thời gian trôi qua"]
    E --> F["Dữ liệu nguồn thay đổi"]
    F --> G["Restore tiến trình"]
    G --> H["Cache cũ xuất hiện trong heap"]
    H --> I{"Entry còn hợp lệ?"}
    I -->|Có| J["Có thể tiếp tục sử dụng"]
    I -->|Không| K["Invalidate hoặc refresh"]
    K --> L["Kiểm tra nguồn dữ liệu"]
    L --> M["Phục vụ request"]
    J --> M
~~~

Checkpoint khôi phục trạng thái bộ nhớ của tiến trình. Nó không đóng băng database, cache server, DNS, hệ thống xác thực hoặc các dịch vụ khác trong suốt thời gian checkpoint.

### 2.1. Object còn tồn tại không đồng nghĩa dữ liệu còn mới

Giả sử cache chứa thông tin giá sản phẩm lúc 09:00. Ứng dụng tạo checkpoint lúc 09:05 và restore lúc 10:00. Trong thời gian đó, giá sản phẩm có thể đã thay đổi.

Sau restore, Map vẫn có thể chứa object Product với giá cũ. Java không tự biết bản ghi ở database đã được cập nhật. Nếu ứng dụng trả ngay object đó cho request, người dùng có thể nhìn thấy giá không còn đúng.

Tương tự, một cache chứa quyền truy cập có thể còn object Permission sau restore dù quyền đã bị thu hồi. Với dữ liệu bảo mật hoặc nghiệp vụ quan trọng, việc kiểm tra lại nguồn là cần thiết.

### 2.2. Cache entry có thể mang theo tham chiếu không còn hợp lệ

Cache không chỉ lưu dữ liệu bất biến. Nó có thể giữ:

- Entity đang được quản lý bởi persistence context.
- JDBC connection hoặc HTTP response.
- Object chứa session hoặc transaction.
- Token và credential.
- Native resource hoặc handle.
- Object phụ thuộc vào clock hoặc service registry.
- Collection mutable được nhiều thread chia sẻ.

Không nên cache những tài nguyên có vòng đời ngắn như transaction hoặc connection chỉ vì chúng là object Java. Cache nên ưu tiên dữ liệu có thể tái sử dụng độc lập với resource runtime.

### 2.3. Heap cache và cache ngoài tiến trình khác nhau

Một local cache nằm trong heap có thể được lưu cùng checkpoint. Một cache ngoài tiến trình, ví dụ Redis hoặc một dịch vụ cache, tiếp tục tồn tại độc lập và có thể được cập nhật trong lúc ứng dụng bị checkpoint.

Sau restore, hai loại cache có thể không đồng bộ:

- Local cache chứa giá trị trước checkpoint.
- Distributed cache chứa giá trị mới hơn.
- Một invalidation event đã được gửi trong lúc consumer của ứng dụng không hoạt động.
- Version của dữ liệu nguồn đã tăng.

Vì vậy, ứng dụng cần xác định nguồn nào có thẩm quyền và cách đồng bộ lại local cache khi restore.

## 3. Vì sao cache có thể stale sau restore?

### 3.1. TTL đã hết hạn

TTL (Time To Live) là thời gian một entry được phép tồn tại trong cache. Nếu entry được tạo trước checkpoint, TTL có thể đã hết trong khoảng tiến trình bị dừng.

Ví dụ:

- Entry được tạo lúc 08:00 với TTL 15 phút.
- Checkpoint lúc 08:05.
- Restore lúc 08:30.
- Entry đã quá hạn từ 08:15.

Nếu cache chỉ xóa entry khi có request truy cập, entry cũ có thể vẫn nằm trong heap. Ứng dụng phải kiểm tra expiry khi đọc hoặc thực hiện cleanup/refresh sau restore.

### 3.2. Dữ liệu nguồn đã thay đổi

Một bản ghi có thể được cập nhật hoặc xóa trong database. Nếu local cache không nhận được invalidation trong thời gian checkpoint, giá trị cũ vẫn tồn tại.

Điều này thường gặp với cache-aside: ứng dụng đọc từ database khi cache miss và giữ kết quả trong local cache. Khi một instance khác cập nhật database, local cache của instance hiện tại cần được invalidation hoặc hết TTL.

### 3.3. Invalidation event bị bỏ lỡ

Một số hệ thống dùng message broker hoặc pub/sub để thông báo cache invalidation. Nếu tiến trình không chạy trong thời gian checkpoint, consumer có thể bỏ lỡ event, mất subscription hoặc cần đọc lại offset sau restore.

Sau restore, không nên giả định local cache đã nhận đủ event. Có thể cần:

- Kiểm tra version hiện tại của dữ liệu.
- Đọc lại offset hoặc cursor của event stream.
- Xóa toàn bộ nhóm cache phụ thuộc vào stream.
- Đồng bộ lại từ một snapshot có version.
- Tạo lại subscription trước khi nhận traffic.

### 3.4. Credential hoặc token hết hạn

Cache xác thực có rủi ro riêng. Một token hợp lệ trước checkpoint có thể hết hạn trước khi restore. Nếu ứng dụng tiếp tục dùng token cũ, các request đến dịch vụ bên ngoài có thể bị từ chối.

Không nên chỉ dựa vào thời gian còn lại được tính trước checkpoint. Sau restore, cần kiểm tra thời hạn theo clock hiện tại và làm mới token theo chính sách của hệ thống xác thực.

### 3.5. Feature flag và cấu hình thay đổi

Một cache chứa cấu hình có thể đã lỗi thời khi feature flag, endpoint, giới hạn nghiệp vụ hoặc chính sách bảo mật thay đổi.

Với cấu hình ảnh hưởng đến quyền truy cập, thanh toán, giới hạn giao dịch hoặc routing, việc giữ giá trị cũ có thể gây sai hành vi. Nên phân loại cấu hình theo mức độ rủi ro và refresh các giá trị cần cập nhật trước khi ứng dụng nhận request.

### 3.6. Clock và deadline không còn phù hợp

Cache entry có thể chứa thời điểm tạo, thời điểm hết hạn hoặc deadline. Sau restore, ứng dụng cần đánh giá các thời điểm đó bằng clock hiện tại.

Không nên giả định mọi deadline được lưu dưới dạng elapsed time hoặc giá trị monotonic đều có ý nghĩa xuyên qua mọi cơ chế checkpoint/restore. Đối với thời hạn cần tồn tại qua tiến trình, thường nên lưu timestamp tuyệt đối theo UTC hoặc thời hạn do nguồn dữ liệu quản lý, rồi tính lại thời gian còn lại sau restore.

## 4. Chính sách TTL và thời hạn cache

TTL giúp giới hạn thời gian dữ liệu có thể được sử dụng mà không kiểm tra lại nguồn. TTL phù hợp phụ thuộc vào mức độ thay đổi và hậu quả nếu dữ liệu stale.

| Dữ liệu | Chính sách gợi ý | Lý do |
|---|---|---|
| Danh mục ít thay đổi | TTL dài, versioned refresh | Thay đổi không thường xuyên |
| Giá sản phẩm | TTL ngắn hoặc invalidation theo event | Giá có thể thay đổi thường xuyên |
| Feature flag | Refresh nhanh, kiểm tra version | Thay đổi ảnh hưởng hành vi |
| Permission | TTL rất ngắn hoặc kiểm tra nguồn | Thu hồi quyền cần có hiệu lực kịp thời |
| Token | Theo expiry thực tế của token | Không được sử dụng token hết hạn |
| DNS/service discovery | Theo TTL và chính sách resolver | Endpoint có thể đổi |
| Kết quả tính toán | TTL theo chi phí tính lại và độ mới | Có thể tái tính khi stale |

TTL chỉ giới hạn khoảng thời gian stale tối đa trong điều kiện cache kiểm tra expiry đúng cách. TTL không tự bảo đảm dữ liệu luôn mới ngay khi nguồn thay đổi.

### 4.1. Kiểm tra expiry khi đọc

Một cache entry có thể lưu thời điểm hết hạn:

~~~java
import java.time.Instant;

public record CacheEntry<V>(
        V value,
        Instant expiresAt
) {
    public boolean isExpired(Instant now) {
        return !now.isBefore(expiresAt);
    }
}
~~~

Khi đọc:

~~~java
public Product getProduct(String id) {
    CacheEntry<Product> entry = cache.get(id);
    Instant now = Instant.now();

    if (entry == null || entry.isExpired(now)) {
        return refreshProduct(id);
    }

    return entry.value();
}
~~~

Trong ví dụ, thời hạn được biểu diễn bằng Instant để so sánh với wall-clock time hiện tại. Nếu đồng hồ hệ thống thay đổi, kết quả expiry cũng có thể thay đổi; hệ thống cần dùng nguồn thời gian đáng tin cậy và chính sách phù hợp.

Với ứng dụng cần xử lý chính xác deadline, có thể kết hợp timestamp nguồn, version hoặc thời hạn do server cấp thay vì chỉ dựa vào clock cục bộ.

### 4.2. Không dùng thời điểm checkpoint làm thời điểm tạo lại TTL

Một lỗi dễ gặp là sau restore, ứng dụng đặt lại TTL đầy đủ cho mọi entry cũ. Ví dụ, entry đã tồn tại 20 phút trước checkpoint nhưng sau restore lại được cấp thêm 30 phút như thể vừa mới được tạo.

Điều đó kéo dài thời gian sử dụng dữ liệu stale. Nếu entry có thời điểm hết hạn tuyệt đối, hãy giữ nguyên expiresAt và kiểm tra theo thời điểm hiện tại. Nếu cache library lưu remaining duration, hãy kiểm tra cách library xử lý thời gian khi restore.

### 4.3. Jitter để tránh refresh đồng loạt

Nếu nhiều instance cùng nạp cache tại một thời điểm, các entry có thể hết TTL gần nhau. Sau deploy hoặc restore hàng loạt, tất cả instance có thể đồng thời truy vấn database.

Có thể thêm jitter vào TTL để phân tán thời điểm refresh:

~~~java
Duration baseTtl = Duration.ofMinutes(10);
long jitterSeconds = ThreadLocalRandom.current().nextLong(0, 61);

Duration effectiveTtl = baseTtl.plusSeconds(jitterSeconds);
~~~

Jitter cần được dùng phù hợp với yêu cầu freshness. Với token hoặc quyền truy cập, không được cộng thêm thời gian vượt quá expiry thực tế của credential.

## 5. Những chiến lược làm mới cache sau restore

Không phải lúc nào cũng cần xóa toàn bộ cache. Có nhiều chiến lược, từ giữ nguyên dữ liệu đến refresh toàn bộ.

### 5.1. Giữ nguyên cache có version hoặc dữ liệu bất biến

Một số dữ liệu ít thay đổi hoặc được định danh bằng version có thể giữ lại.

Ví dụ:

- Bảng mã quốc gia gắn với version.
- Metadata của một schema bất biến.
- Kết quả tính toán dựa trên input hash.
- Tài nguyên tĩnh có checksum.
- Cấu hình được phát hành cùng một phiên bản ứng dụng.

Nếu version của cache khớp với version nguồn sau restore, dữ liệu có thể tiếp tục được dùng. Nếu version khác, ứng dụng phải refresh.

Cách này giảm chi phí warm-up nhưng cần version có ý nghĩa và được cập nhật đáng tin cậy.

### 5.2. Lazy refresh

Lazy refresh không nạp lại toàn bộ cache ngay sau restore. Entry chỉ được refresh khi có request truy cập và phát hiện entry đã hết hạn hoặc version không còn hợp lệ.

Ưu điểm:

- Restore nhanh hơn.
- Không tạo tải lớn lên database ngay khi khởi động.
- Chỉ làm mới dữ liệu thực sự được dùng.

Nhược điểm:

- Request đầu tiên cho mỗi key có thể chậm.
- Một số request có thể gặp lỗi refresh.
- Nếu nhiều request cùng đọc một key stale, có thể tạo nhiều lần truy vấn đồng thời.

Cần cơ chế single-flight hoặc đồng bộ theo key để chỉ một luồng refresh một entry tại một thời điểm.

### 5.3. Eager refresh hoặc warm-up

Eager refresh nạp trước một tập dữ liệu quan trọng sau restore, trước khi ứng dụng nhận traffic.

Ví dụ:

- Cấu hình thiết yếu.
- Danh mục được dùng trong mọi request.
- Public key hoặc metadata xác thực.
- Cache routing hoặc endpoint.
- Dữ liệu tham chiếu có kích thước nhỏ.

Ưu điểm là request đầu tiên không phải chờ nạp dữ liệu. Nhược điểm là thời gian restore kéo dài và có thể tạo tải đột biến lên nguồn dữ liệu.

Không nên warm-up toàn bộ cache lớn nếu phần lớn key không được dùng. Hãy xác định tập dữ liệu tối thiểu cần thiết để ứng dụng sẵn sàng.

### 5.4. Invalidate toàn bộ cache

Nếu không thể xác định entry nào còn hợp lệ, ứng dụng có thể xóa local cache sau restore và nạp lại khi cần.

Chiến lược này đơn giản nhưng có thể làm tăng tải database, tăng latency và gây cache stampede. Chỉ nên dùng khi cache có thể tái tạo với chi phí chấp nhận được và nguồn dữ liệu đủ khả năng phục vụ các instance cùng lúc.

### 5.5. Refresh theo version hoặc generation

Một cách khác là gắn cache với generation hoặc version của dữ liệu nguồn. Sau restore, ứng dụng đọc version hiện tại. Nếu generation trong cache không khớp, entry thuộc generation cũ sẽ không được sử dụng.

Ví dụ:

~~~java
public record VersionedValue<V>(
        long generation,
        V value
) {}

public V get(String key, long currentGeneration) {
    VersionedValue<V> entry = cache.get(key);

    if (entry == null || entry.generation() != currentGeneration) {
        return loadAndCache(key, currentGeneration);
    }

    return entry.value();
}
~~~

Generation có thể lấy từ database, configuration service hoặc một metadata store. Cần bảo đảm việc đọc generation và dữ liệu có tính nhất quán phù hợp; nếu version được đọc quá cũ, ứng dụng vẫn có thể chấp nhận entry stale.

### 5.6. Stale-while-revalidate

Một số dữ liệu cho phép trả giá trị cũ trong một khoảng thời gian ngắn trong khi refresh nền.

Cơ chế thường gồm:

1. Entry còn trong soft TTL: trả dữ liệu ngay.
2. Entry vượt soft TTL nhưng chưa vượt hard TTL: trả dữ liệu cũ và khởi chạy refresh nền.
3. Entry vượt hard TTL: không trả dữ liệu cũ; chờ refresh hoặc báo lỗi.

Cách này giảm latency nhưng chỉ phù hợp khi nghiệp vụ cho phép dữ liệu cũ tạm thời. Không nên dùng cho permission, token, số dư tài khoản hoặc dữ liệu mà stale có thể gây hậu quả nghiêm trọng.

## 6. Chọn dữ liệu nào cần giữ, refresh hoặc xóa?

Nên phân loại cache theo yêu cầu freshness và mức độ rủi ro.

| Nhóm | Ví dụ | Sau restore |
|---|---|---|
| Bất biến hoặc có version | Metadata theo release | Giữ nếu version khớp |
| Ít thay đổi, rủi ro thấp | Danh mục | Giữ trong TTL hoặc refresh nền |
| Dữ liệu nghiệp vụ thường đổi | Giá, tồn kho | Kiểm tra version hoặc refresh |
| Dữ liệu nhạy cảm | Permission, session | Refresh hoặc xác thực lại |
| Credential có hạn | Access token | Kiểm tra expiry và làm mới |
| Phụ thuộc môi trường | DNS, endpoint, route | Resolve lại khi cần |
| Cache tính toán đắt | Báo cáo, aggregate | Giữ nếu input version còn khớp |
| Tham chiếu runtime | Connection, transaction | Không xem là cache dữ liệu; quản lý bằng lifecycle resource |

Một chiến lược thực tế có thể kết hợp:

- Giữ dữ liệu bất biến hoặc versioned.
- Giữ cache ít rủi ro trong TTL còn hiệu lực.
- Invalidate dữ liệu phụ thuộc thời gian.
- Refresh dữ liệu bảo mật và cấu hình thiết yếu.
- Lazy load dữ liệu ít dùng.
- Warm-up một tập key quan trọng trước khi mở readiness.

## 7. Tích hợp cache với CRaC Resource

CRaC cung cấp interface Resource với hai callback chính:

- beforeCheckpoint(): chuẩn bị tài nguyên trước khi lưu trạng thái.
- afterRestore(): phục hồi hoặc làm mới tài nguyên sau khi tiến trình được khôi phục.

Với cache, beforeCheckpoint() có thể dùng để dừng refresh nền, dừng listener nhận invalidation hoặc đưa cache vào trạng thái nhất quán. afterRestore() có thể kiểm tra version, invalidate entry stale, khởi động lại listener và warm-up dữ liệu thiết yếu.

Không phải cache nào cũng cần xóa trong beforeCheckpoint(). Nếu dữ liệu có version rõ ràng và còn hợp lệ, giữ cache có thể tiết kiệm thời gian restore. Quyết định nên dựa trên semantics của từng loại dữ liệu.

### 7.1. Ví dụ Resource quản lý cache

Ví dụ dưới đây sử dụng các abstraction do ứng dụng định nghĩa: ProductCache, VersionProvider và CacheWarmer. Chúng không phải API của CRaC.

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CacheCheckpointResource implements Resource {

    private final ProductCache cache;
    private final VersionProvider versionProvider;
    private final CacheWarmer warmer;

    public CacheCheckpointResource(
            ProductCache cache,
            VersionProvider versionProvider,
            CacheWarmer warmer) {

        this.cache = cache;
        this.versionProvider = versionProvider;
        this.warmer = warmer;

        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {

        // Dừng refresh nền và listener trước khi lưu tiến trình.
        cache.pauseBackgroundRefresh();
        cache.stopInvalidationListener();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {

        // Đối chiếu version của cache với nguồn dữ liệu hiện tại.
        long currentVersion = versionProvider.currentVersion();

        if (cache.version() != currentVersion) {
            cache.invalidateAll();
        } else {
            cache.invalidateExpiredEntries();
        }

        // Khởi động lại các thành phần đồng bộ cache.
        cache.startInvalidationListener();

        // Nạp dữ liệu cần thiết trước khi ứng dụng nhận traffic.
        warmer.warmEssentialEntries();
        cache.resumeBackgroundRefresh();
    }
}
~~~

Ví dụ minh họa một cách tổ chức, không phải implementation dùng trực tiếp với mọi thư viện cache. Cần xác định rõ:

- Listener có thể dừng và đăng ký lại như thế nào.
- Cache version được lưu và cập nhật ra sao.
- Warm-up có timeout hay không.
- Nếu version service không truy cập được thì ứng dụng xử lý thế nào.
- Readiness chỉ mở sau khi cache thiết yếu đã sẵn sàng hay có thể dùng fallback.

Nếu cache library hoặc framework đã có CRaC integration, hãy dùng hướng dẫn của thư viện và tránh đăng ký thêm một resource khác xử lý cùng một cache theo cách trùng lặp.

### 7.2. Thứ tự phục hồi cache và dependency

Cache có thể phụ thuộc vào database, Redis, configuration service hoặc service discovery. Vì vậy, thứ tự restore cần phản ánh dependency:

1. Khởi tạo cấu hình và kết nối mạng.
2. Kết nối nguồn dữ liệu hoặc distributed cache.
3. Đọc version/generation hiện tại.
4. Invalidate hoặc refresh local cache.
5. Khởi động listener và background refresh.
6. Warm-up key thiết yếu.
7. Chuyển readiness sang READY.

Nếu warm-up chạy trước khi database connection sẵn sàng, callback có thể thất bại. Nếu listener khởi động sau khi traffic đã mở, ứng dụng có thể bỏ lỡ invalidation mới.

## 8. Tránh cache stampede sau restore

Cache stampede xảy ra khi nhiều request cùng phát hiện một key đã hết hạn và đồng thời truy vấn nguồn dữ liệu để làm mới.

Sau restore, hiện tượng này có thể xảy ra trên nhiều key hoặc nhiều instance cùng lúc, đặc biệt khi toàn bộ cache bị invalidate.

### 8.1. Single-flight refresh

Single-flight bảo đảm chỉ một lần refresh cho một key đang stale. Các request khác chờ kết quả refresh hoặc sử dụng stale value nếu chính sách cho phép.

Mẫu ý tưởng:

~~~java
ConcurrentHashMap<String, CompletableFuture<Product>> refreshes =
        new ConcurrentHashMap<>();

public CompletableFuture<Product> refreshOnce(String key) {
    return refreshes.computeIfAbsent(key, id ->
        CompletableFuture.supplyAsync(() -> {
            try {
                return repository.loadProduct(id);
            } finally {
                refreshes.remove(id);
            }
        }, refreshExecutor)
    );
}
~~~

Đoạn mã minh họa ý tưởng single-flight; implementation production cần xử lý trường hợp task hoàn tất rất nhanh, exception, executor rejection và việc remove future đúng theo identity để tránh xóa nhầm lần refresh mới.

### 8.2. Jitter và refresh theo lô

Không nên làm mới toàn bộ key theo cùng một thời điểm nếu cache lớn. Có thể:

- Phân tán thời điểm expiry bằng jitter.
- Warm-up theo batch nhỏ.
- Giới hạn số request refresh đồng thời.
- Ưu tiên key được truy cập nhiều.
- Đặt timeout và giới hạn tải lên database.
- Dùng rate limiter cho refresh nền.

### 8.3. Giữ stale value có điều kiện

Nếu nghiệp vụ cho phép, có thể giữ giá trị stale trong thời gian refresh. Tuy nhiên, cần đặt hard limit và phân loại dữ liệu. Không trả stale value khi quyền đã bị thu hồi, token hết hạn hoặc dữ liệu ảnh hưởng trực tiếp đến quyết định tài chính.

### 8.4. Circuit breaker và fallback

Nếu nguồn dữ liệu không sẵn sàng, refresh liên tục có thể làm hệ thống tệ hơn. Circuit breaker có thể tạm ngừng gọi nguồn khi lỗi vượt ngưỡng. Ứng dụng cần xác định fallback:

- Trả stale value nếu nghiệp vụ cho phép.
- Trả lỗi tạm thời.
- Dùng giá trị mặc định an toàn.
- Giữ readiness NOT_READY nếu dependency thiết yếu không thể hoạt động.

Không nên dùng fallback một cách im lặng cho dữ liệu nhạy cảm hoặc quan trọng.

## 9. Cache invalidation và đồng bộ đa instance

Trong hệ thống nhiều instance, mỗi tiến trình có local cache riêng. Khi một instance cập nhật dữ liệu, những instance khác cần biết để xóa hoặc làm mới entry.

Các cơ chế phổ biến:

### 9.1. TTL polling

Mỗi entry hết hạn theo TTL. Cách này đơn giản và không cần event bus, nhưng có độ trễ freshness tối đa theo TTL.

### 9.2. Event-based invalidation

Dịch vụ phát event khi dữ liệu thay đổi. Các instance nhận event và invalidate key tương ứng.

Sau restore, listener có thể cần đăng ký lại và đồng bộ offset/cursor. Nếu không chắc đã nhận đủ event, có thể invalidate cache theo namespace hoặc đối chiếu version hiện tại.

### 9.3. Version-based validation

Mỗi nhóm dữ liệu có version. Cache entry lưu version đã đọc. Khi truy cập, ứng dụng so sánh với version hiện tại.

Cách này giảm phụ thuộc vào việc nhận đủ event, nhưng cần một nguồn version có độ tin cậy và chi phí đọc phù hợp.

### 9.4. Distributed cache

Redis hoặc cache server bên ngoài có thể là nơi giữ dữ liệu dùng chung. Local cache chỉ là L1 cache, còn distributed cache là L2 cache.

Sau restore:

- L1 cache có thể stale.
- L2 cache có thể đã được cập nhật.
- Local cache cần kiểm tra version hoặc invalidation.
- Kết nối đến L2 cache phải được xác nhận trước khi warm-up.

Không nên giả định local cache và distributed cache tự đồng bộ chỉ vì chúng chứa cùng key.

## 10. Cache chứa cấu hình và dữ liệu bảo mật

Một số cache ảnh hưởng trực tiếp đến bảo mật hoặc hành vi của ứng dụng.

### 10.1. Permission và authorization

Nếu quyền truy cập bị thu hồi trong lúc tiến trình bị checkpoint, local cache cũ có thể tiếp tục cho phép request. Với quyền nhạy cảm, cần refresh hoặc kiểm tra nguồn theo yêu cầu của hệ thống.

Không nên dùng stale-while-revalidate cho quyền truy cập quan trọng nếu chính sách yêu cầu thu hồi có hiệu lực nhanh.

### 10.2. Token và credential

Checkpoint có thể chứa token, key hoặc credential trong heap. Cần bảo vệ checkpoint như một artifact có dữ liệu nhạy cảm.

Sau restore:

- Kiểm tra thời hạn token.
- Refresh token khi cần.
- Đọc lại secret nếu nền tảng có thể thay đổi secret.
- Tránh log token hoặc credential.
- Không đưa credential vào cache lâu hơn chính sách cho phép.

### 10.3. Feature flag và cấu hình runtime

Feature flag có thể điều khiển routing, giới hạn hoặc hành vi nghiệp vụ. Sau restore, nên refresh những flag cần phản ánh trạng thái hiện tại trước khi nhận traffic.

Có thể chia cấu hình thành:

- Cấu hình bất biến theo release.
- Cấu hình runtime có version.
- Cấu hình nhạy cảm cần refresh ngay.
- Cấu hình có thể stale trong một khoảng ngắn.

Mỗi nhóm có TTL và fallback khác nhau.

## 11. Thiết kế warm-up sau restore

Warm-up là quá trình nạp trước dữ liệu để giảm cache miss khi bắt đầu nhận traffic.

Không nên nạp tất cả dữ liệu theo một cách cố định. Một warm-up tốt cần xác định:

- Key nào được dùng thường xuyên.
- Dữ liệu nào thiết yếu để xử lý request.
- Dữ liệu nào có thể tải lazy.
- Nguồn nào có giới hạn throughput.
- Có thể nạp theo batch hay không.
- Timeout tối đa trước khi mở readiness.

### 11.1. Warm-up theo mức ưu tiên

Có thể chia thành ba nhóm:

| Mức | Dữ liệu | Hành động |
|---|---|---|
| Critical | Cấu hình, quyền, endpoint thiết yếu | Refresh trước khi nhận traffic |
| High | Danh mục và key phổ biến | Warm-up theo batch |
| Optional | Dữ liệu ít dùng, báo cáo | Lazy load khi có request |

### 11.2. Readiness và cache readiness

Readiness nên phản ánh khả năng phục vụ thực tế. Nếu request nào cũng cần cấu hình hoặc dữ liệu tham chiếu thiết yếu, ứng dụng không nên báo READY trước khi warm-up hoàn tất.

Nếu một cache chỉ tăng hiệu năng và có thể fallback sang database, ứng dụng có thể nhận traffic sớm hơn. Tuy nhiên, cần tính đến tải tăng lên database khi cache chưa nóng.

### 11.3. Warm-up có timeout

Không nên để callback afterRestore chờ vô hạn vì một cache server hoặc database không phản hồi.

Có thể đặt timeout cho từng nhóm dữ liệu. Nếu critical cache không nạp được, giữ readiness NOT_READY hoặc báo lỗi restore theo chính sách. Nếu optional cache thất bại, ứng dụng có thể tiếp tục với lazy loading.

## 12. Ví dụ chiến lược cache có expiry và refresh

Ví dụ sau mô tả cache dữ liệu sản phẩm với thời điểm hết hạn. Cache được invalidate khi version nguồn thay đổi.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;

public final class ProductCache {

    private final ConcurrentHashMap<String, Entry> entries =
            new ConcurrentHashMap<>();

    private final Duration ttl;
    private final ProductRepository repository;

    public ProductCache(
            Duration ttl,
            ProductRepository repository) {
        this.ttl = ttl;
        this.repository = repository;
    }

    public Product get(String id) {
        Instant now = Instant.now();
        Entry entry = entries.get(id);

        if (entry != null
                && now.isBefore(entry.expiresAt())) {
            return entry.product();
        }

        Product fresh = repository.findById(id);
        entries.put(
            id,
            new Entry(fresh, Instant.now().plus(ttl))
        );

        return fresh;
    }

    public void invalidate(String id) {
        entries.remove(id);
    }

    public void invalidateAll() {
        entries.clear();
    }

    public void invalidateExpiredEntries() {
        Instant now = Instant.now();

        entries.entrySet().removeIf(
            item -> !now.isBefore(item.getValue().expiresAt())
        );
    }

    private record Entry(Product product, Instant expiresAt) {}
}
~~~

Đây là ví dụ tối giản. Trong production, cần cân nhắc:

- Đồng bộ khi nhiều thread cùng refresh một key.
- Xử lý lỗi repository.
- Giới hạn kích thước cache.
- Chính sách eviction.
- Jitter cho TTL.
- Version của dữ liệu.
- Metric cache hit, miss và refresh failure.
- Không trả dữ liệu stale vượt quá hard expiry.

### 12.1. Làm mới cache sau restore

Một resource có thể invalidate entry hết hạn và warm-up dữ liệu quan trọng:

~~~java
public final class ProductCacheResource implements Resource {

    private final ProductCache cache;
    private final ProductCacheWarmer warmer;

    public ProductCacheResource(
            ProductCache cache,
            ProductCacheWarmer warmer) {
        this.cache = cache;
        this.warmer = warmer;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) {
        warmer.pause();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        cache.invalidateExpiredEntries();
        warmer.refreshCriticalData();
        warmer.resume();
    }
}
~~~

Ví dụ giả định các lớp đã có dependency và phương thức tương ứng. Trong ứng dụng thực tế, cần xử lý lỗi khi refresh critical data, timeout và trạng thái readiness. Nếu cache không có khả năng xác định expiry chính xác, có thể cần invalidate theo version hoặc xóa một namespace cụ thể.

## 13. Các lỗi thường gặp khi restore cache

| Lỗi | Hậu quả | Hướng xử lý |
|---|---|---|
| Giữ nguyên mọi entry mà không kiểm tra TTL | Trả dữ liệu hết hạn | Kiểm tra expiry sau restore và khi đọc |
| Reset TTL cho cache cũ | Kéo dài thời gian stale | Giữ expiry tuyệt đối hoặc version |
| Refresh toàn bộ cache đồng thời | Database quá tải | Batch, jitter, concurrency limit |
| Mở traffic trước warm-up critical | Request lỗi hoặc dùng fallback không an toàn | Readiness gate |
| Bỏ lỡ invalidation event | Local cache giữ dữ liệu cũ | Resync offset hoặc đối chiếu version |
| Cache token không kiểm tra expiry | Request bị từ chối hoặc dùng credential cũ | Refresh token theo expiry |
| Cache connection hoặc transaction | Tham chiếu đến resource không còn hợp lệ | Quản lý bằng CRaC Resource riêng |
| Dùng stale fallback cho permission | Quyền đã thu hồi vẫn được chấp nhận | Refresh hoặc kiểm tra nguồn |
| Warm-up vô hạn | Restore bị treo | Timeout và chính sách lỗi |
| Không giới hạn cache | Heap tăng và restore chậm | Maximum size và eviction |

## 14. Quan sát cache trong quá trình vận hành

Sau restore, nên theo dõi:

- Cache hit rate và miss rate.
- Số entry được giữ lại.
- Số entry bị invalidate.
- Số entry hết TTL.
- Thời gian warm-up.
- Tỷ lệ refresh thành công/thất bại.
- Số request bị chờ vì refresh.
- Số lần cache stampede hoặc refresh đồng thời.
- Version cache so với version nguồn.
- Thời gian từ restore đến READY.

Metric giúp xác định cache có thực sự giúp tăng tốc sau restore hay đang tạo tải lớn lên hệ thống nguồn.

Nên ghi log theo các giai đoạn:

- Cache restore preparation started.
- Cache invalidation completed.
- Cache version verified.
- Critical cache warm-up started/completed.
- Invalidation listener reconnected.
- Cache readiness changed.
- Cache refresh failed.

Không ghi nội dung nhạy cảm hoặc token vào log. Với cache lớn, nên log số lượng và version thay vì dump toàn bộ key/value.

## 15. Quy trình triển khai đề xuất

### Trước checkpoint

1. Ngừng nhận công việc mới nếu cache refresh đang chạy nền.
2. Dừng scheduler hoặc listener nếu cần quản lý vòng đời riêng.
3. Chờ refresh đang chạy hoàn tất hoặc đưa nó về trạng thái có thể tiếp tục.
4. Xác định cache nào có thể giữ và cache nào cần invalidate.
5. Đóng các resource bên ngoài được cache manager sử dụng nếu chúng cần được tạo lại.
6. Để CRaC tiếp tục checkpoint sau khi trạng thái đã sẵn sàng.

### Sau restore

1. Khởi tạo kết nối đến database, distributed cache và configuration service.
2. Đọc version/generation hiện tại.
3. Kiểm tra TTL và expiry.
4. Invalidate cache stale hoặc không xác định được trạng thái.
5. Khởi động lại invalidation listener và background refresh.
6. Warm-up critical keys theo batch.
7. Chuyển readiness sang READY khi các dữ liệu thiết yếu sẵn sàng.

Thứ tự có thể thay đổi tùy dependency. Ví dụ, nếu cache chỉ phụ thuộc vào Redis, không cần đợi database nếu Redis đã cung cấp dữ liệu có version đáng tin cậy. Hãy xác định nguồn thẩm quyền của từng cache.

## 16. Checklist thiết kế cache cho CRaC

### Dữ liệu và freshness

- [ ] Mỗi nhóm cache có TTL hoặc chính sách version rõ ràng.
- [ ] Dữ liệu nghiệp vụ nhạy cảm có yêu cầu freshness phù hợp.
- [ ] Entry giữ expiry tuyệt đối hoặc thông tin version có thể kiểm tra sau restore.
- [ ] Cache không chứa transaction, connection hoặc resource runtime ngắn hạn.
- [ ] Credential và token được kiểm tra expiry.

### Restore và refresh

- [ ] Cache được phân loại thành giữ lại, refresh hoặc invalidate.
- [ ] Invalidation event được đồng bộ lại sau restore.
- [ ] DNS, endpoint và cấu hình phụ thuộc môi trường được refresh khi cần.
- [ ] Warm-up critical data có timeout.
- [ ] Readiness phản ánh trạng thái cache thiết yếu.

### Hiệu năng và lỗi

- [ ] Refresh được giới hạn concurrency.
- [ ] Có jitter hoặc batch để tránh stampede.
- [ ] Có single-flight hoặc cơ chế tương đương cho cùng một key.
- [ ] Fallback chỉ dùng cho dữ liệu mà nghiệp vụ cho phép stale.
- [ ] Cache có giới hạn kích thước và eviction policy.
- [ ] Có metric hit/miss, expiry, invalidation và refresh.

### Bảo mật và vận hành

- [ ] Checkpoint được bảo vệ vì heap có thể chứa dữ liệu nhạy cảm.
- [ ] Secret không được ghi vào log.
- [ ] Có cách xử lý khi nguồn cache không sẵn sàng.
- [ ] Đã kiểm thử restore sau TTL, version change và invalidation bị bỏ lỡ.
- [ ] Đã kiểm thử nhiều instance restore cùng lúc.

## 17. Câu hỏi thường gặp

### Cache trong heap có được lưu cùng checkpoint không?

Các object cache nằm trong heap có thể được lưu cùng trạng thái tiến trình. Tuy nhiên, dữ liệu được khôi phục có thể đã stale vì nguồn dữ liệu và các dịch vụ bên ngoài tiếp tục thay đổi trong thời gian checkpoint.

### Có nên xóa toàn bộ cache trong beforeCheckpoint() không?

Không nhất thiết. Dữ liệu bất biến hoặc có version đáng tin cậy có thể được giữ lại. Cache phụ thuộc thời gian, quyền truy cập hoặc môi trường có thể cần invalidate hoặc refresh. Hãy quyết định theo từng nhóm dữ liệu.

### Có thể chỉ dựa vào TTL không?

TTL giới hạn thời gian sử dụng entry nhưng không bảo đảm dữ liệu mới ngay khi nguồn thay đổi. Với dữ liệu cần freshness cao, nên kết hợp TTL với version hoặc event-based invalidation.

### Nên dùng lazy refresh hay eager warm-up?

Lazy refresh giúp restore nhanh và chỉ tải key được dùng. Eager warm-up phù hợp với dữ liệu thiết yếu cần sẵn sàng trước request đầu tiên. Nhiều ứng dụng kết hợp hai cách: warm-up nhóm critical và lazy load phần còn lại.

### Nếu invalidation event bị bỏ lỡ trong thời gian checkpoint thì sao?

Sau restore, consumer cần đồng bộ lại offset/cursor hoặc đối chiếu version nguồn. Nếu không thể xác định cache đã nhận đủ event, invalidate nhóm dữ liệu liên quan hoặc refresh theo một snapshot có version.

### Có nên giữ token trong cache qua restore không?

Có thể giữ object nếu thiết kế cho phép, nhưng không được giả định token còn hiệu lực. Sau restore, kiểm tra expiry và refresh theo chính sách xác thực. Checkpoint cũng cần được bảo vệ vì có thể chứa token và secret trong heap.

### Warm-up thất bại có nên mở traffic không?

Phụ thuộc dữ liệu nào thất bại. Nếu đó là cache thiết yếu cho quyền truy cập hoặc nghiệp vụ quan trọng, giữ readiness NOT_READY hoặc báo lỗi theo chính sách. Nếu chỉ là cache tăng hiệu năng và có fallback an toàn, ứng dụng có thể nhận traffic với giới hạn phù hợp.

### Cache ngoài tiến trình có cần xử lý sau restore không?

Có. Redis hoặc distributed cache vẫn có thể hoạt động độc lập, nhưng kết nối, listener, subscription và local L1 cache của ứng dụng có thể stale. Hãy kết nối lại, đồng bộ version và khôi phục invalidation listener.

## Kết luận

Cache trong heap có thể được khôi phục cùng tiến trình CRaC, nhưng object còn tồn tại không chứng minh dữ liệu còn mới. TTL có thể đã hết, database có thể đã đổi dữ liệu, invalidation event có thể bị bỏ lỡ, token có thể hết hạn và cấu hình có thể đã thay đổi trong thời gian checkpoint.

Một chiến lược tốt phân loại cache theo freshness và mức độ rủi ro: giữ dữ liệu bất biến hoặc versioned, kiểm tra expiry, invalidate dữ liệu stale, refresh dữ liệu nhạy cảm và warm-up nhóm key thiết yếu. Kết hợp version, TTL, event resync, single-flight, jitter, timeout và readiness giúp ứng dụng phục hồi cache có kiểm soát mà không tạo tải đột biến hoặc phục vụ dữ liệu lỗi thời.
