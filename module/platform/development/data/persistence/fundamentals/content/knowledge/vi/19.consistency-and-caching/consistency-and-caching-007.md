# Vai trò của TTL và giới hạn bảo đảm tính đúng đắn

Một trang thương mại điện tử hiển thị giá sản phẩm từ cache để giảm tải database. Cache được cấu hình hết hạn sau 30 giây, nên nhóm phát triển kết luận: “Giá luôn chính xác, cùng lắm chỉ chậm 30 giây”. Kết luận đó **không tự động đúng**. Một giá trị có thể được nạp từ replica đang trễ, bị ghi lại vào cache sau một lần invalidation, hoặc được gia hạn mỗi khi truy cập. Ở một tình huống khác, dù giá trị chỉ cũ vài mili giây, dùng nó để chốt tiền thanh toán vẫn có thể vi phạm quy tắc nghiệp vụ.

**TTL — Time To Live** — là khoảng thời gian một cache entry còn được xem là hợp lệ theo **chính sách thời gian của cache**. TTL giúp kiểm soát tuổi entry, bộ nhớ và tần suất nạp lại. TTL **không phải** là transaction, ràng buộc toàn vẹn, giao thức đồng bộ với nguồn dữ liệu chính (*source of truth*) hay lời hứa chống đọc dữ liệu cũ trong mọi tình huống.

Bài này thuộc chương **Nhất quán và cache** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Mục tiêu là thiết kế cache trong ứng dụng Java dựa trên yêu cầu dữ liệu bền vững, giao dịch, cô lập và kiểm soát đồng thời: khi nào dữ liệu cache có thể phục vụ đọc, khi nào phải xác minh ở database, cách chọn TTL theo rủi ro, cách tránh ghi đè cache bằng dữ liệu cũ và cách kiểm thử những bảo đảm thực tế.

## 1. TTL thật sự định nghĩa điều gì?

Một entry có thể được mô tả bằng:

~~~text
key          = product:42:price
value        = 250000 VND
cached_at    = 10:00:00
ttl          = 30 seconds
expires_at   = 10:00:30
~~~

Với chính sách **expire-after-write**, nếu không có thao tác làm mới/gia hạn, cache coi entry đó hết hạn sau 30 giây kể từ lúc ghi. Ở lần đọc sau hạn, cache thông thường xử lý như **cache miss** và ứng dụng phải nạp từ nguồn khác.

Điều này chỉ nói về **đồng hồ của cache**. Nó không trả lời:

- Giá trị 250000 VND có đúng với database ngay lúc được nạp không?
- Database có thay đổi lúc 10:00:05 không?
- Sau khi hết hạn, lần nạp tiếp theo có đọc từ replica đã cập nhật chưa?
- Trong lúc một request đang nạp dữ liệu, có request khác commit thay đổi rồi xóa cache không?
- Cache có đang phục vụ dữ liệu stale theo một chính sách *stale-while-revalidate* không?

Do đó, **“chưa hết TTL” không đồng nghĩa với “đúng theo dữ liệu hiện tại”**; “đã hết TTL” cũng không đồng nghĩa với lỗi. Nó chỉ là tín hiệu để hệ thống chọn cách xử lý entry.

### Phân biệt các khái niệm liên quan

| Khái niệm | Ý nghĩa | Có thay thế TTL không? |
| --- | --- | --- |
| **Cache hit/miss** | Tìm được entry có thể dùng theo chính sách cache hay không | Không; hit có thể chứa dữ liệu cũ |
| **Expiration** | Chính sách coi entry không còn hợp lệ theo thời gian | Là nơi TTL thường được áp dụng |
| **Eviction** | Loại entry để tiết kiệm bộ nhớ hoặc theo chính sách dung lượng | Không; entry có thể bị đẩy ra **trước** khi TTL hết |
| **Invalidation** | Chủ động loại bỏ/đánh dấu entry không hợp lệ khi dữ liệu thay đổi | Bổ sung TTL, nhưng có race condition |
| **Refresh** | Nạp lại một entry, có thể nền hoặc đồng bộ | Có thể gia hạn tuổi entry; không chắc đọc được dữ liệu mới |
| **Version/revision** | Dấu mốc thay đổi của dữ liệu tại nguồn | Giúp phát hiện thứ tự phiên bản, không thay việc định nghĩa hết hạn |
| **Consistency** | Quan hệ giữa giá trị quan sát và lịch sử cập nhật | Cần bảo đảm từ toàn bộ đường đọc/ghi, không chỉ TTL |

## 2. Timeline: TTL không làm dữ liệu tự cập nhật

Giả sử ứng dụng cache-aside đọc từ database chính, dùng TTL 30 giây:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant C as Cache
    participant DB as Database chính
    U->>C: 10:00:00 GET price:42
    C-->>U: Miss
    U->>DB: SELECT price
    DB-->>U: 250000, version=7
    U->>C: SET 250000, TTL=30s
    Note over DB: 10:00:05: giá được đổi thành 270000, version=8
    U->>C: 10:00:20 GET price:42
    C-->>U: Hit 250000 (cũ nhưng chưa hết TTL)
    U->>C: 10:00:31 GET price:42
    C-->>U: Miss sau expiration
    U->>DB: SELECT price
    DB-->>U: 270000, version=8
~~~

Giá trị cache trở nên **stale** từ lúc database commit thay đổi vào 10:00:05, không phải đến khi hết TTL. Nếu không có invalidation/refresh, cache vẫn có thể trả 250000 cho các yêu cầu đến trước lúc hết hạn.

Trong mô hình đơn giản này, sự chênh lệch thời gian giữa **một thay đổi DB** và **một entry đã có** có thể gần bằng TTL nếu DB thay đổi ngay sau khi entry được nạp. Nhưng nói “TTL 30 giây nên không bao giờ stale quá 30 giây” chỉ có thể là một giới hạn **có điều kiện**: cache phải thực sự từ chối entry hết hạn, không gia hạn sai, tất cả lần refill phải đọc từ nguồn đủ mới, không có race ghi giá trị cũ trở lại và không có tầng cache khác với chính sách riêng.

Nếu lần nạp sau hết hạn lại đọc **replica đang lag**, cache có thể lưu giá trị cũ với **TTL mới 30 giây**. Vậy tuổi stale tính từ lần DB đổi giá có thể lớn hơn 30 giây. TTL giới hạn **tuổi entry từ lúc được cache ghi**, không tự giới hạn **độ trễ so với thay đổi của nguồn dữ liệu**.

## 3. Bốn phép đo không nên đánh đồng

Khi đánh giá “cache có mới không?”, cần phân biệt:

1. **Entry age**: thời gian kể từ lần cache ghi entry đang dùng.
2. **Source change age**: thời gian kể từ lần dữ liệu nguồn thay đổi mà cache chưa phản ánh.
3. **Replication/indexing lag**: thời gian một thay đổi đã commit tại nguồn trở nên đọc được qua replica/search/read model.
4. **User-visible staleness**: khoảng thời gian người dùng thực sự quan sát giá trị không còn phù hợp với quy tắc sản phẩm.

Ví dụ:

~~~text
09:59:40  Database primary đổi v8.
10:00:00  Cache miss, ứng dụng đọc replica vẫn có v7.
10:00:01  Cache lưu v7 với TTL 30 giây.
10:00:29  Người dùng đọc v7 từ cache.
~~~

Entry chưa đầy 30 giây tuổi, nhưng giá trị đã cũ so với primary **gần 49 giây** tại 10:00:29. Nếu replica tiếp tục trễ và được dùng trong refill tiếp theo, sự chênh lệch còn có thể kéo dài.

Đừng gọi các số đo này cùng một tên “TTL lag”. Muốn cam kết dữ liệu được cập nhật trong một khoảng thời gian, phải xác định **điểm bắt đầu tính** (commit tại primary, cập nhật CDC, publish sự kiện hay ghi cache) và **điểm kết thúc** (cache đã cập nhật hay request quan sát được bản mới).

## 4. Cache-aside: đơn giản nhưng không có coherence miễn phí

Trong kiểu **cache-aside** (lazy loading), ứng dụng chủ động đọc cache trước, miss thì đọc database rồi ghi cache:

~~~mermaid
flowchart TD
    A[Nhận yêu cầu đọc] --> B[GET key trong cache]
    B --> C{Có entry hợp lệ theo cache?}
    C -- Có --> D[Trả giá trị cache]
    C -- Không --> E[Đọc source of truth]
    E --> F[Lưu kết quả với TTL]
    F --> G[Trả kết quả đọc]
~~~

Các bước:

1. Tạo cache key ổn định, bao gồm tenant/locale/currency và những yếu tố ảnh hưởng kết quả khi cần.
2. Đọc cache; nếu hit, trả giá trị **nếu** use case cho phép dùng cache với mức nhất quán đó.
3. Nếu miss, truy vấn nguồn dữ liệu đã chọn và chuyển sang DTO cache có schema rõ.
4. Ghi kết quả với TTL, sau đó trả dữ liệu.

Điểm có lợi: code dễ hiểu, dữ liệu ít được truy cập không cần luôn nằm trong cache, cache có thể mất và nạp lại. Điểm hạn chế: **từ lúc đọc DB đến lúc ghi cache, nguồn dữ liệu có thể đã thay đổi**. TTL không ngăn được race này.

### Cache key cũng là một phần của tính đúng đắn

Ví dụ cache key chỉ là `product:42:price` nhưng API trả giá khác nhau theo tenant, chương trình khuyến mại hoặc đơn vị tiền tệ. Dù TTL chỉ 1 giây, một người dùng vẫn có thể nhận **giá của ngữ cảnh khác**. Key phải thể hiện đầy đủ các tham số làm thay đổi giá trị; dữ liệu cần phân quyền không được truy xuất chỉ theo key do client cung cấp mà bỏ qua kiểm tra quyền.

Không nên dùng TTL như biện pháp khắc phục một cache key được thiết kế sai hoặc dữ liệu bị trộn giữa tenant.

## 5. Race giữa cache miss, DB commit và invalidation

Giả sử hai request chạy đồng thời:

~~~mermaid
sequenceDiagram
    participant A as Reader A
    participant DB as DB
    participant W as Writer B
    participant C as Cache
    A->>C: GET price:42 -> miss
    A->>DB: SELECT price
    DB-->>A: v7 (250000)
    W->>DB: UPDATE price=v8; COMMIT
    W->>C: DEL price:42
    C-->>W: Đã xóa / key không tồn tại
    A->>C: SET price=v7, TTL=30s
    Note over C: Dữ liệu cũ được đưa trở lại sau invalidation
~~~

Đây là lỗi **stale repopulation**: việc xóa cache sau commit **đúng thời điểm theo từng writer** vẫn chưa loại bỏ mọi race với reader đang nạp dữ liệu cũ. Nếu không có hàng rào bổ sung, v7 có thể tồn tại đến hết TTL dù DB đã ở v8.

Hệ quả:

- **Delete cache sau DB commit** là một chiến lược phổ biến, nhưng không đồng nghĩa có linearizability giữa DB và cache.
- **Delete cache trước DB commit** còn nguy hiểm: một reader có thể miss, đọc v7 khi transaction chưa commit, rồi nạp lại v7; sau đó DB commit v8 nhưng không ai xóa entry mới.
- “Xóa lần thứ hai sau một khoảng chờ” (*delayed double delete*) có thể giảm một số cửa sổ race, nhưng nếu không có đồng bộ/giới hạn thời gian được chứng minh thì **không phải bảo đảm đúng đắn chặt chẽ**.

TTL trong ví dụ đóng vai trò **giới hạn thời gian tồn tại của bản cache v7 vừa bị nạp nhầm**, theo điều kiện expiry hoạt động đúng; nó không ngăn việc nạp nhầm xảy ra.

## 6. Ghi DB và vô hiệu hóa cache: thứ tự quan trọng

Với nguồn sự thật là RDBMS, một cập nhật thường cần thứ tự logic:

~~~text
1. BEGIN transaction DB.
2. Kiểm tra bất biến nghiệp vụ, thực hiện UPDATE/INSERT.
3. COMMIT transaction.
4. Invalidate hoặc cập nhật các bản cache liên quan.
~~~

Làm bước 4 **trước khi commit** có thể khiến reader đưa dữ liệu chưa cập nhật vào cache. Tuy nhiên, chỉ gọi `DEL` ở bước 4 **sau commit** lại có một khoảng lỗi: tiến trình có thể crash ngay sau commit mà **chưa kịp invalidation**.

Nếu hậu quả stale có thể chấp nhận trong TTL, ứng dụng có thể chọn mô hình đơn giản và ghi rõ giới hạn đó. Nếu yêu cầu phục hồi được quá trình invalidation, có thể:

- Ghi một **outbox event trong cùng transaction** với thay đổi dữ liệu chính.
- Sau commit, worker đọc outbox và gửi invalidation hoặc sự kiện cập nhật cache.
- Dùng event ID/idempotency để consumer chịu được phát lặp.
- Theo dõi backlog, retry với backoff và có quá trình đối soát khi pipeline lỗi.

~~~mermaid
flowchart LR
    A[DB transaction: UPDATE + INSERT outbox] --> B[COMMIT]
    B --> C[Outbox worker]
    C --> D[Cache DEL hoặc update]
    C --> E[Retry / quan sát lỗi]
    E --> D
~~~

**Outbox không tạo transaction nguyên tử giữa DB và cache.** Nó làm sự kiện invalidation có thể phục hồi sau crash, nhưng giữa commit và lúc worker xử lý vẫn có khoảng stale; event còn có thể đến trễ/khác thứ tự. Cần thêm kiểm tra version hoặc một phương án đọc authoritative nếu nghiệp vụ không chịu được khoảng đó.

### Cẩn trọng với callback sau commit của Spring

`@TransactionalEventListener(phase = AFTER_COMMIT)` hoặc `TransactionSynchronization.afterCommit()` giúp tránh invalidation trước commit. Chúng hữu ích, nhưng nếu tiến trình chết sau DB commit và trước khi callback thực hiện thành công, sự kiện chỉ nằm trong bộ nhớ có thể mất. **Callback sau commit không tự thay thế transactional outbox bền vững.**

## 7. TTL không bảo vệ các bất biến nghiệp vụ

Một **invariant** là điều kiện phải đúng với trạng thái nghiệp vụ, chẳng hạn:

- Số lượng tồn kho không được âm.
- Hai người không đặt cùng một ghế đã được xác nhận.
- Số dư không vượt quá hạn mức được cấp.
- Tài khoản đã bị thu hồi quyền không được tiếp tục thực hiện thao tác nhạy cảm.
- Một idempotency key không tạo hai lần thanh toán/đơn hàng.

Để bảo vệ invariant, **quyết định ghi phải được kiểm tra ở nguồn có thẩm quyền** bằng ràng buộc database, cập nhật có điều kiện, transaction, locking hoặc cơ chế phối hợp đúng với kho dữ liệu. Không thể:

~~~text
GET cache:stock:p42 -> 1
Nếu stock > 0: chấp nhận đặt hàng
UPDATE DB stock = stock - 1
~~~

và coi đó là an toàn chỉ vì TTL = 500 ms. Hai request có thể cùng nhận `1` trong cùng 500 ms, đều xác nhận đặt hàng và trừ kho sai.

Ví dụ PostgreSQL:

~~~sql
UPDATE inventory
SET available = available - :quantity,
    version = version + 1
WHERE product_id = :productId
  AND available >= :quantity;
~~~

Ứng dụng phải kiểm tra số dòng cập nhật. Nếu `1` dòng: yêu cầu đã vượt qua điều kiện tồn kho **tại thời điểm cập nhật**. Nếu `0` dòng: không xác nhận giữ kho; phân loại tiếp xem đã hết hàng hay ID không tồn tại. Nếu còn phải ghi reservation/order, các thao tác thuộc cùng nghiệp vụ cần transaction thích hợp.

Cache có thể dùng để **hiển thị** “còn khoảng một sản phẩm”, nhưng ở điểm **xác nhận** phải kiểm tra nguồn và commit kết quả phù hợp. TTL nhỏ không biến cache thành khóa giao dịch.

## 8. Chọn TTL theo mức độ rủi ro của dữ liệu

Không có TTL đúng cho mọi thứ. Câu hỏi đầu tiên không phải “nên dùng 30 giây hay 5 phút?” mà là: **nếu cache stale, hệ quả xảy ra là gì, và có thể sửa bằng kiểm tra tại điểm quyết định không?**

| Dữ liệu | Mức nhạy cảm khi stale | Chiến lược gợi ý |
| --- | --- | --- |
| Ảnh đại diện hoặc mô tả sản phẩm ít thay đổi | Thường thấp | TTL vừa/dài, invalidation khi có chỉnh sửa nếu cần |
| Danh sách sản phẩm nổi bật | Thấp đến trung bình | TTL và refresh nền; chịu độ trễ đã công bố |
| Giá hiển thị | Trung bình đến cao | TTL ngắn + invalidation/phiên bản; **tính lại giá tại checkout** |
| Tồn kho hiển thị | Trung bình | Cache phục vụ tham khảo; reservation phải kiểm tra DB |
| Số dư hoặc hạn mức để quyết định giao dịch | Rất cao | Nguồn authoritative/transaction cho quyết định; cache chỉ làm projection nếu được phép |
| Quyền truy cập vừa bị thu hồi | Cao về bảo mật | Không dựa chỉ vào TTL để bảo đảm revoke có hiệu lực ngay |
| Cấu hình feature flag không trọng yếu | Thường vừa | TTL/refresh với chính sách drift rõ ràng |
| Dữ liệu phản hồi idempotency | Cao | Lưu bền vững theo cửa sổ retry và business key; TTL dọn dẹp phải có quy tắc |

Một ứng dụng có thể cho phép hiển thị số dư cache trong trang dashboard nhưng **không** dùng số dư đó để duyệt chuyển tiền. Cùng một dữ liệu có thể có hai **hợp đồng đọc** khác nhau: đọc nhanh để tham khảo và đọc có tính nhất quán đủ mạnh để ra quyết định.

## 9. Expire-after-write, expire-after-access và refresh

Các cơ chế hết hạn có ý nghĩa khác nhau:

| Chính sách | Đồng hồ tính từ | Điều quan trọng |
| --- | --- | --- |
| **Expire after write** | Lần tạo/ghi mới entry | Truy cập lặp lại không tự gia hạn tuổi tuyệt đối của cùng bản |
| **Expire after access** | Lần đọc/ghi được tính là access | Entry nóng có thể tồn tại rất lâu nếu liên tục được truy cập |
| **Refresh after write** | Lần ghi gần nhất kích hoạt cơ hội refresh | Có thể tiếp tục phục vụ bản cũ trong lúc refresh tùy cache |
| **Fixed absolute expiration** | Mốc thời gian định trước | Hợp với sự kiện/giá trị hết hiệu lực tại giờ cụ thể |
| **TTL + stale-while-revalidate** | Hạn dùng bản tươi và cửa sổ được phép dùng bản stale | Cần có ngân sách stale tối đa riêng |

Ví dụ: một cấu hình `expireAfterAccess(30s)` cho cache có hàng triệu lượt đọc mỗi phút **không** bảo đảm mọi entry sẽ được làm mới sau tối đa 30 giây. Mỗi lượt truy cập có thể đẩy hạn hết thời gian ra xa, khiến bản cũ được dùng rất lâu.

`refreshAfterWrite(30s)` trong một cache hỗ trợ refresh có thể bắt đầu nạp lại ở lần đọc tiếp theo và trả **giá trị cũ** cho tới khi refresh hoàn tất. Đừng gọi đó là freshness deadline nếu library cho phép stale response.

Cache hỗ trợ nhiều chính sách cùng lúc phải được kiểm thử theo semantics cụ thể; các từ `expire` và `refresh` không có một hợp đồng đa sản phẩm giống hệt nhau.

## 10. Redis TTL: expiration khác eviction và durability

Redis hỗ trợ đặt thời hạn khi ghi key:

~~~redis
SET product:42:price "250000:v7" EX 30
TTL product:42:price
~~~

`SET ... EX 30` ghi giá trị và thời hạn 30 giây trong cùng command. `TTL` thường trả số giây còn lại, có giá trị đặc biệt cho key không tồn tại hoặc không có thời hạn. Redis có cả phiên bản độ phân giải mili giây như `PTTL`.

Các lỗi thiết kế cần tránh:

- Gọi `SET key value` **sau đó** mới `EXPIRE key 30` dưới dạng hai command độc lập: nếu ứng dụng crash giữa hai lệnh, key có thể tồn tại **không có TTL**. Ưu tiên command kết hợp hoặc thao tác nguyên tử phù hợp.
- Gọi `SET` thông thường lên key đã có thời hạn mà không khai báo giữ/gán lại TTL theo chủ đích: hành vi này có thể **xóa thời hạn cũ**; kiểm tra đúng option của phiên bản Redis đang dùng.
- Coi `DEL` sau commit là thao tác đồng bộ nguyên tử với transaction DB: Redis không tham gia transaction DB đó chỉ vì nằm trong cùng method Java.
- Coi `maxmemory` eviction như TTL: Redis có thể loại key sớm vì thiếu bộ nhớ theo policy, hoặc tiếp tục giữ key chưa hết hạn. TTL là chính sách hết hiệu lực, eviction là chính sách tài nguyên.

Redis xử lý hết hạn bằng cơ chế chủ động và khi truy cập; việc thu hồi bộ nhớ vật lý có thể không diễn ra đúng ở mili giây hết hạn, dù một key đã hết hạn bình thường không còn được trả như dữ liệu hợp lệ qua đường đọc thông thường. Không suy rằng việc liệt kê key hoặc quan sát replica luôn khớp tức thì một lịch xóa vật lý chính xác.

**Redis cache không phải backup của database.** Tùy cấu hình persistence, replication và failover, dữ liệu Redis có thể mất khi tiến trình/host gặp sự cố. Dịch vụ dùng cache phải có cách phục hồi từ nguồn sự thật và xử lý cache miss.

## 11. Java/Caffeine: cache trong tiến trình với expire-after-write

Một cache local thích hợp cho dữ liệu đọc thường xuyên và có thể tái nạp. Ví dụ dùng **Caffeine** (một thư viện cache cho Java) để lưu thông tin giá phục vụ hiển thị:

~~~java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.math.BigDecimal;
import java.time.Duration;
import java.util.Objects;

public final class ProductPriceReader {
    public record PriceView(
            String productId, BigDecimal amount, long revision) {}

    public interface PriceRepository {
        // Đọc từ nguồn dữ liệu authoritative cho thao tác hiển thị.
        // Không trả null; sản phẩm không tồn tại phải báo theo hợp đồng.
        PriceView load(String productId);
    }

    private final PriceRepository repository;
    private final Cache<String, PriceView> cache =
            Caffeine.newBuilder()
                    .maximumSize(10_000)
                    .expireAfterWrite(Duration.ofSeconds(30))
                    .build();

    public ProductPriceReader(PriceRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public PriceView readForDisplay(String productId) {
        Objects.requireNonNull(productId);
        PriceView cached = cache.getIfPresent(productId);
        if (cached != null) {
            return cached;
        }

        PriceView loaded = repository.load(productId);
        cache.put(productId, loaded);
        return loaded;
    }

    public void invalidateAfterCommittedChange(String productId) {
        cache.invalidate(productId);
    }
}
~~~

Đây là ví dụ **cho đọc hiển thị**, không bảo đảm giá tại checkout. Cần thêm phân quyền/tenant trong key nếu giá phụ thuộc tenant hoặc người dùng. `readForDisplay()` dùng `getIfPresent` rồi `put` riêng nên có **race stale repopulation** như phần 5. Đổi sang loader atomic theo key (ví dụ `cache.get(key, mappingFunction)` của Caffeine) giúp giới hạn duplicate load trong **một instance** tùy API, nhưng **không tạo atomicity với DB commit và cache invalidation**, cũng không đồng bộ giữa nhiều JVM.

Trong ứng dụng Spring, có thể dùng `@Cacheable` và `@CacheEvict`, nhưng **thời điểm evict so với DB commit**, timeout, serialization và semantics TTL phụ thuộc cache manager/provider và ranh giới transaction. Annotation không tự tạo transaction phân tán giữa DB và cache.

### Caffeine local và nhiều instance

Với ba instance API, mỗi instance có bộ cache riêng:

~~~text
API-A cache: price v7
API-B cache: price v8
API-C cache: cache miss
Database:    price v8
~~~

Gọi `invalidate()` trong API-B không tự xóa entry của API-A. Nếu yêu cầu các node cập nhật gần đồng thời, cần cơ chế invalidation phân tán, shared cache hoặc chấp nhận mỗi node có một khoảng stale. Đối với dữ liệu chính xác tuyệt đối tại điểm ghi, yêu cầu đọc/ghi authoritative vẫn phải tồn tại.

## 12. Cache stampede và TTL jitter

Khi hàng nghìn key phổ biến hết hạn cùng lúc, rất nhiều request có thể đồng thời gặp miss rồi truy vấn DB. Hiện tượng **cache stampede/thundering herd** làm nguồn dữ liệu bị quá tải đúng lúc cache được kỳ vọng giảm tải.

Ví dụ 10.000 key được nạp lúc 12:00 với TTL 60 giây:

~~~text
12:00:00 — 10.000 key được đưa vào cache.
12:01:00 — phần lớn key hết hạn cùng lúc.
12:01:00 — hàng nghìn request miss và đổ vào DB.
~~~

Cách giảm tác động:

1. **TTL jitter:** phân tán thời hạn, ví dụ TTL mỗi key nằm trong khoảng 45–75 giây nếu use case cho phép.
2. **Request coalescing/single-flight:** một loader cho mỗi key trong một instance; request khác chờ kết quả hoặc dùng stale có kiểm soát.
3. **Distributed coordination** cho hot key nếu cần, nhưng khóa phải có TTL/owner/fencing và xử lý khi owner crash; không biến cache lock thành nguồn sự thật nghiệp vụ.
4. **Stale-while-revalidate** với ngân sách stale công khai cho dữ liệu không trọng yếu.
5. **Pre-warm có giới hạn** cho hot key và giới hạn số loader đồng thời.
6. **Rate limit, circuit breaker và backpressure** để database không bị khuếch đại tải do retry.

Jitter **giúp hiệu năng**, không tự tăng tính đúng đắn. Nếu use case yêu cầu “không stale quá 30 giây”, chọn jitter khiến TTL thực tế lên tới 75 giây là sai hợp đồng. Muốn dùng jitter, ngân sách phải được tính theo **TTL tối đa** và các độ trễ liên quan.

## 13. Negative caching: không có dữ liệu cũng có thể trở nên cũ

**Negative caching** là cache kết quả “không tìm thấy”, “không có kết quả” hoặc một phản hồi trống trong thời gian ngắn. Nó hữu ích để tránh truy vấn DB lặp lại cho ID không tồn tại, nhưng có một rủi ro:

~~~text
10:00:00 GET /users/u-99 -> DB không thấy -> cache NOT_FOUND TTL=5 phút
10:00:10 User u-99 được tạo thành công trong DB
10:00:20 GET /users/u-99 -> cache NOT_FOUND -> 404 sai
~~~

Nếu cache negative result, phải:

- Phân biệt **thực sự không tồn tại** với **lỗi timeout/permission/DB unavailable**. Không cache lỗi hạ tầng như `NOT_FOUND`.
- Chọn TTL negative phù hợp với tần suất tài nguyên mới được tạo.
- Invalidate entry âm khi tạo thực thể hoặc dùng version/generation marker nếu có yêu cầu freshness mạnh.
- Không cache một phản hồi `403`/`404` từ ngữ cảnh phân quyền rồi phục vụ cho người dùng khác nếu key và policy không bảo vệ đúng principal.
- Kiểm tra quyền truy cập ở nguồn có thẩm quyền cho tác vụ nhạy cảm thay vì tin vào negative cache cũ.

Negative TTL không chỉ là tối ưu hiệu năng: nó quyết định thời gian ứng dụng có thể **không nhận ra một thực thể vừa xuất hiện**.

## 14. Dùng version để ngăn bản cũ ghi đè bản mới

Gắn `revision` tăng đơn điệu khi dữ liệu thay đổi tại source of truth có thể giúp ứng dụng so sánh các thông điệp cập nhật cache đến khác thứ tự:

~~~text
DB: product 42 ở revision=11
Event A: revision=10, price=250000 (đến trễ)
Event B: revision=11, price=270000 (đến trước)
~~~

Nếu cache đã có v11, event v10 **không được phép** ghi đè giá trị bằng v10. Có thể dùng một thao tác compare-and-set **nguyên tử trong cache**:

~~~text
proposed = {key, revision: 10, value: 250000}
existing = cache.get(key) // v11
if proposed.revision > existing.revision:
    cache.set(proposed)
else:
    ignore
~~~

**Pseudocode trên phải được hiện thực bằng thao tác nguyên tử phù hợp** — không tách đọc và ghi thành hai command độc lập rồi tuyên bố đã an toàn. Với Redis có thể dùng Lua script/transaction hoặc dữ liệu versioned cùng cơ chế kiểm tra và ghi nguyên tử; với local cache cần thao tác update atomic phù hợp.

Tuy nhiên, **chỉ so version trong cache chưa giải quyết mọi race**:

- Nếu invalidation xóa hẳn v11, reader cũ có thể ghi v10 vào một cache đang trống; không có v11 để so sánh.
- Cần **tombstone/generation marker**, fencing token, một hàng rào nguồn có phiên bản hoặc giao thức phối hợp thích hợp khi yêu cầu không cho phép entry cũ trở lại.
- Nếu version bị reset hoặc tái sử dụng khi xóa rồi tạo lại thực thể cùng ID, so sánh version đơn thuần có thể sai; cần namespace/generation ID hoặc tránh tái sử dụng ID.
- Cache chỉ bảo vệ riêng entry của nó. Một transaction cập nhật nhiều bảng/aggregate vẫn phải bảo đảm invariants tại nguồn.

**Revision là công cụ xây dựng giao thức nhất quán**, không phải một cấu hình TTL thay thế transaction.

## 15. Multi-layer cache, replica và giới hạn end-to-end

Một request có thể đi qua nhiều tầng:

~~~mermaid
flowchart LR
    A[Browser/CDN cache] --> B[Local Caffeine]
    B --> C[Redis shared cache]
    C --> D[Read replica]
    D --> E[(Primary DB)]
~~~

Sơ đồ mô tả các nguồn có thể tham gia đường đọc, không có nghĩa mọi lần đọc nhất thiết đi tuần tự qua tất cả. Khi mỗi tầng có TTL và chính sách riêng, muốn đưa ra **cam kết freshness end-to-end** phải xét:

- Browser/CDN có giữ một bản cũ sau khi API cache đã cập nhật không?
- Local cache ở node A có nhận invalidation của node B không?
- Redis đã hết hạn nhưng một ứng dụng đã giữ kết quả trong bộ nhớ riêng chưa?
- Replica có lag hoặc đọc snapshot cũ không?
- Client có dùng stale-while-revalidate hoặc offline cache không?
- Việc cập nhật và việc gửi invalidation có cùng thứ tự nhìn thấy ở mọi node không?

Không đơn giản cộng các TTL thành một con số rồi coi đó là freshness guarantee, vì các tầng có thể **nạp lại từ bản cũ** và tạo một TTL mới. Ngược lại, khi các tầng được thiết kế với invariant và deadline rõ, có thể lập ngân sách độ trễ có điều kiện, đo từng chặng và kiểm thử trong failure mode.

Với trường hợp cần **read-your-writes**, ứng dụng có thể phải đọc từ primary sau ghi, mang version token để chờ replica bắt kịp hoặc bypass cache cho một khoảng thao tác cụ thể. Chỉ đặt TTL ngắn không chứng minh request tiếp theo của chính người ghi thấy bản vừa commit.

## 16. Chọn TTL theo ngân sách và chi phí thực tế

TTL nên là kết quả của **phân loại nghiệp vụ và phép đo**, không chỉ một hằng số được chọn tùy tiện.

Giả sử giá trị không thay đổi quá thường xuyên và business cho phép hiển thị cũ **tối đa khoảng 60 giây trong điều kiện bình thường**. Nhóm có thể dùng TTL 20–30 giây để tạo khoảng đệm cho load latency, invalidation lag và các tầng phụ; nhưng con số này **không phải chứng minh** cho SLO 60 giây nếu không có các giới hạn cho replica, race và failure.

Các bước chọn TTL:

1. **Định nghĩa tác động của stale:** chỉ hiển thị khác vài giây, hay có thể duyệt giao dịch sai?
2. **Định nghĩa điểm đo freshness:** từ primary commit đến lúc API quan sát giá trị tương ứng.
3. **Xác định tối đa thời gian stale chấp nhận:** deadline thật hoặc một mục tiêu thống kê như p99.
4. **Lập bản đồ đường đọc/ghi:** cache local, Redis, replica, CDN, các sự kiện invalidation.
5. **Đo tần suất thay đổi và tải truy cập:** key nóng hay lạnh, churn, kích thước payload, khả năng DB chịu miss.
6. **Chọn chính sách phù hợp:** expire-after-write, event invalidation, refresh, negative TTL và jitter.
7. **Đặt hàng rào tại điểm quyết định:** không dùng cache không đủ mạnh để giữ invariant.
8. **Kiểm thử khi lỗi:** replica lag, worker chết, event mất/thứ tự đảo, cache restart và retry.

Một mô hình chi phí đơn giản (chỉ mang tính định hướng): TTL ngắn hơn thường tăng số cache miss và tải nguồn, trong khi TTL dài hơn giảm tải nhưng kéo dài khả năng dùng entry cũ. Tối ưu là điểm cân bằng **phù hợp use case**, không phải chỉ tối đa hóa cache hit ratio.

### Khi nào nên bỏ cache thay vì chỉnh TTL?

Nếu dữ liệu nhỏ, nguồn truy vấn đã có chỉ mục tốt và yêu cầu nhất quán cao, thêm cache có thể tạo chi phí giải quyết stale cao hơn lợi ích độ trễ. Một truy vấn DB tốt có thể là thiết kế **đơn giản và đúng hơn** so với cache nhiều lớp với TTL cực ngắn.

## 17. Kiểm thử TTL phải kiểm tra cả race và lỗi hạ tầng

Unit test xác nhận entry hết hạn sau một số giây chưa đủ để chứng minh tính đúng đắn. Cần nhiều loại test:

| Kịch bản | Kết quả nên xác minh |
| --- | --- |
| Cache hit trước TTL | Giá trị được trả theo chính sách, không đọc nguồn không cần thiết |
| Cache miss sau TTL | Nạp lại từ nguồn; không trả bản đã hết hạn nếu không có stale policy |
| DB đổi dữ liệu giữa hai lần đọc | Quan sát rõ khoảng stale được phép và cơ chế invalidation |
| Reader đang load, writer commit rồi invalidate | Không tuyên bố đã chặn stale repopulation nếu chưa có hàng rào; test phải tái hiện race |
| Hai event revision khác nhau đến đảo thứ tự | Event cũ không ghi đè revision mới |
| Cache bị mất hoặc Redis restart | Ứng dụng vẫn đọc được từ nguồn, không mất dữ liệu nghiệp vụ chính |
| Cache lỗi kết nối | Ứng dụng fail-open/fail-closed theo loại nghiệp vụ đã định |
| Negative entry rồi thực thể được tạo | Invalidation hoặc hết hạn cho kết quả đúng theo hợp đồng |
| Tầng replica lag sau TTL | Không nhận định sai rằng bản refill chắc chắn mới |
| Key phụ thuộc tenant/currency | Không trả dữ liệu của ngữ cảnh khác |
| 1.000 key đồng loạt hết hạn | Có giới hạn loader, jitter hoặc bảo vệ DB khỏi stampede |
| Thu hồi quyền rồi dùng cache cũ | Quyết định nhạy cảm không được dựa vào quyền đã thu hồi |

### Test thời gian xác định với Caffeine

Caffeine có khả năng dùng **ticker** có thể điều khiển trong test, giúp giả lập thời gian thay vì `Thread.sleep()` nhiều giây. Ý tưởng:

~~~text
clock = testTicker
cache = expireAfterWrite(30 seconds), dùng clock
clock = 0s: PUT (value=v7)
clock = 29s: GET -> v7
clock = 31s: GET -> miss
~~~

Điều này kiểm chứng expiration **của entry**, không chứng minh business freshness. Trong integration test, dùng hai luồng và barrier/latch để ép thứ tự:

~~~text
A: cache miss, đọc DB -> v7, tạm dừng trước PUT
B: cập nhật DB -> v8, COMMIT, DEL cache
A: tiếp tục PUT v7
assert: hệ thống quan sát kết quả theo thiết kế; nếu yêu cầu không stale,
        phải có version/tombstone/fencing chặn v7
~~~

Không chỉ dùng `Thread.sleep()` để hy vọng race sẽ xuất hiện. Với failover và crash recovery, kiểm thử trong môi trường riêng; không phá dữ liệu production.

## 18. Giám sát: đo freshness thay vì chỉ cache hit ratio

Hit ratio cao là chỉ số hiệu năng, **không đo trực tiếp tính đúng đắn**. Một cache phục vụ 99% hit vẫn có thể trả giá cũ cho 99% người dùng nếu invalidation lỗi.

| Chỉ số | Câu hỏi giúp trả lời |
| --- | --- |
| Cache hit/miss/eviction rate | Cache có giảm tải nguồn như kỳ vọng không? |
| Entry age khi được phục vụ | Người dùng nhận giá trị đã được cache bao lâu? |
| Revision mismatch giữa cache và source trong sampling | Bao nhiêu phần trăm kết quả không theo bản mới nhất? |
| Commit-to-invalidation latency | Thay đổi nguồn mất bao lâu để loại cache cũ? |
| Outbox backlog/retry/errors | Invalidation có bị trì hoãn hoặc kẹt không? |
| Replica lag | Miss có thể vẫn nạp bản cũ không? |
| Cache load latency, concurrent loaders | Miss có gây stampede không? |
| Number of stale reads after critical write | Có vi phạm đường đọc quan trọng không? |
| Negative-cache hit sau create | Có đang trả không tìm thấy sai thời điểm không? |
| Redis memory/eviction/expiration metrics | Cache có thiếu bộ nhớ hoặc TTL hiệu lực không? |

Với dữ liệu quan trọng, có thể **lấy mẫu** so sánh revision cache và DB authoritative, hạn chế tải sinh ra từ việc đo. Metric label không nên chứa raw user ID, product ID hoặc cache key có cardinality quá lớn; không log dữ liệu nhạy cảm. Alert nên gắn với **ngân sách freshness của nghiệp vụ**, không chỉ CPU/cache hit.

## 19. Sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| “TTL = 30s nghĩa là dữ liệu sai tối đa 30s” | Refill từ replica cũ, race và các tầng cache có thể kéo dài stale | Xác định điều kiện bảo đảm, đo commit-to-visible và kiểm thử |
| Dùng cache tồn kho để xác nhận đặt hàng | Hai request có thể cùng thấy số lượng cũ | Cập nhật DB có điều kiện trong transaction |
| Invalidate cache trước khi DB commit | Reader có thể nạp lại bản cũ trước commit | Invalidate sau commit; bổ sung hàng rào khi cần |
| Tin rằng after-commit callback không bao giờ mất | Crash có thể xảy ra giữa commit và callback | Transactional outbox và reconciliation nếu cần |
| Nghĩ DEL sau commit là đủ chặn mọi race | Reader cũ có thể PUT lại sau DEL | Version/generation/fencing hoặc mô hình nhất quán khác |
| Dùng expire-after-access để giới hạn tuổi tuyệt đối | Key nóng được gia hạn liên tục | Dùng expire-after-write/deadline phù hợp |
| SET rồi EXPIRE bằng hai Redis command không phối hợp | Crash giữa hai lệnh để lại key không TTL | Dùng SET với EX/PX hoặc thao tác nguyên tử |
| Coi cache miss là lỗi nghiệp vụ | Miss là tình huống bình thường | Nạp nguồn hoặc fail theo chính sách rõ ràng |
| Cache negative result quá lâu | Thực thể vừa tạo vẫn bị trả NOT_FOUND | TTL âm ngắn và invalidation khi tạo |
| Chỉ chọn TTL bằng cache hit ratio | Bỏ qua freshness và rủi ro nghiệp vụ | Đo staleness, nguồn và tác động người dùng |
| Dùng key không có tenant/locale/currency | Trộn kết quả của ngữ cảnh khác | Thiết kế cache key đầy đủ, phân quyền bắt buộc |
| Giả định invalidation một JVM cập nhật mọi node | Node khác vẫn giữ bản cũ | Distributed invalidation/shared cache hoặc chấp nhận stale |
| Gửi event thay đổi đến chậm mà ghi đè tùy ý | Bản cũ ghi đè bản mới | Kiểm tra revision bằng thao tác atomic |
| Dùng TTL để “xóa quyền” ngay lập tức | Quyền đã thu hồi vẫn có thể được dùng | Chính sách auth/revocation authoritative |

## 20. Bài tập thực hành: giá và tồn kho

Một ứng dụng Java có thiết kế:

~~~text
Database primary:
  products(id=42, price=250000, available=2, revision=5)

Redis:
  price:42 = 250000     TTL=60s
  stock:42 = 2          TTL=10s

API:
  GET /products/42       -> đọc Redis
  POST /checkout         -> đọc Redis stock/price, nếu đủ thì xác nhận
  Admin update price     -> UPDATE DB, rồi DEL Redis price:42
~~~

Hãy trả lời:

1. Người quản trị đổi giá thành 270000 vào thời điểm 10:00:05, nhưng một reader đã đọc v5 trước commit và PUT v5 vào Redis sau lệnh DEL. Vì sao kết quả vẫn cũ dù có invalidation?
2. Nếu cache tồn kho có TTL 10 giây, hai checkout đồng thời cùng nhìn thấy `stock=2` có thể bán tổng cộng 4 đơn vị không?
3. Nếu Redis price key hết hạn nhưng service đọc bản v5 từ replica chậm rồi ghi TTL 60 giây mới, có thể nói dữ liệu sai “tối đa 60 giây kể từ commit” không?
4. Với giá hiển thị và giá chốt đơn, nên dùng cùng một hợp đồng đọc không?
5. Để invalidation không mất khi app crash ngay sau DB commit, cần bổ sung cơ chế gì?
6. Hãy đề xuất một phép đo giúp phát hiện việc cache thường xuyên trả phiên bản cũ dù hit ratio cao.

**Gợi ý lời giải:**

- (1) Đây là stale repopulation: reader load cũ trước commit nhưng ghi cache sau invalidation. Muốn chặn cần giao thức version/generation, fence hoặc cách phối hợp khác, không chỉ DEL.
- (2) **Có thể**, nếu chỉ kiểm tra cache. Checkout phải dùng thao tác cập nhật tồn kho có điều kiện ở DB/nguồn thẩm quyền, commit cùng reservation/order theo đúng ranh giới.
- (3) **Không**. Một refill từ replica lag tạo entry mới với TTL mới, trong khi DB đã thay đổi từ trước đó.
- (4) Giá hiển thị có thể được cache theo mức stale được chấp nhận; giá chốt phải tính/kiểm tra từ nguồn được phép quyết định và ghi kết quả giao dịch.
- (5) Lưu outbox event trong cùng transaction với thay đổi giá, worker invalidate sau commit và retry khi lỗi; vẫn cần xử lý thứ tự/version nếu muốn hạn chế stale race.
- (6) Lấy mẫu so sánh `revision` của cache với primary, đồng thời theo dõi độ trễ từ commit đến invalidation hoàn tất.

## 21. Checklist trước khi đưa TTL vào production

1. **Nguồn sự thật:** biết dữ liệu nào authoritative và cache chứa projection của phiên bản nào.
2. **Độ chính xác:** phân loại quyết định nào dùng được cache stale và quyết định nào phải đọc/ghi authoritative.
3. **Cache key:** chứa tenant, quyền, locale, currency và tham số có ảnh hưởng đến kết quả khi cần.
4. **Expiration:** chọn đúng expire-after-write/access, refresh và cửa sổ stale được phép.
5. **Giới hạn:** không suy TTL thành freshness SLO nếu chưa chứng minh các điều kiện về refill, replica, race, tầng cache khác.
6. **Write path:** commit DB trước; invalidation đáng tin cậy theo mức yêu cầu và có chiến lược xử lý crash.
7. **Concurrency:** kiểm thử stale repopulation, event đảo thứ tự, nhiều node, conditional update và version/tombstone.
8. **Resilience:** cache miss, Redis outage, stampede, negative cache và retry phải có hành vi rõ.
9. **Quan sát:** đo hit ratio **cùng với** entry age, revision mismatch, outbox lag và commit-to-visible latency.
10. **Vận hành:** tài liệu hóa TTL, mục tiêu consistency, runbook khi cache/invalidation lỗi và kiểm thử khôi phục.

**Kết luận:** TTL là một cơ chế quản lý **thời gian tồn tại của dữ liệu đã cache**, hữu ích để giảm tải và giới hạn một số dạng stale theo điều kiện cụ thể. TTL không tự bảo vệ bất biến nghiệp vụ hoặc cam kết “mọi đọc đều thấy bản mới nhất”. Muốn persistence Java đúng đắn, hãy xác định **nguồn có thẩm quyền**, đặt transaction và cập nhật có điều kiện tại điểm quyết định, rồi dùng TTL, invalidation, version và đo lường như các công cụ bổ trợ cho hợp đồng nhất quán đã định nghĩa.
