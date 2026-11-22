# TTL, thời gian dữ liệu có thể cũ và chính sách vô hiệu hóa

Một ứng dụng thương mại điện tử dùng MongoDB để lưu giá sản phẩm, số lượng hàng tồn và trạng thái đơn hàng. Để giảm tải truy vấn, nhóm đưa các kết quả đọc thường xuyên vào Redis. Sau khi triển khai, p99 giảm rõ rệt. Nhưng rồi xuất hiện ba sự cố:

1. Giá sản phẩm đã được cập nhật trong nguồn chính, trong khi một số người dùng vẫn thấy giá cũ trong vài phút.
2. Hàng vừa được bán hết, nhưng cache vẫn trả về “còn hàng”, khiến nhiều người tiếp tục đặt mua.
3. Quyền xem một tài liệu đã bị thu hồi, nhưng một cache ở tầng API vẫn cung cấp nội dung cho người không còn quyền.

Về kỹ thuật, cả ba trường hợp đều liên quan đến **dữ liệu trong cache không còn phản ánh trạng thái có thẩm quyền**. Tuy nhiên, chúng **không có cùng yêu cầu nghiệp vụ**. Giá có thể cho phép hiển thị cũ một thời gian ngắn nếu được xác nhận; số lượng tồn kho có thể phải kiểm tra lại tại thao tác giữ hàng; dữ liệu nhạy cảm có thể cần chặn truy cập theo quyền mới ngay lập tức.

**TTL (Time To Live)**, **thời gian chấp nhận dữ liệu cũ (staleness budget)** và **chính sách vô hiệu hóa (invalidation policy)** là ba thành phần cần được thiết kế cùng nhau. Đặt TTL bằng 5 phút không tự chứng minh mọi người dùng chỉ thấy dữ liệu cũ tối đa 5 phút, cũng không làm các thao tác DELETE, đổi quyền hoặc ghi đồng thời trở nên an toàn.

Bài học thuộc chương **Bộ nhớ đệm dữ liệu**, module **Database No SQL**. Ta sẽ học cách định nghĩa độ mới dữ liệu, lựa chọn TTL, xây các mẫu cache-aside/read-through/write-through/write-behind, xử lý đua tranh khi cập nhật và nạp lại cache, ngăn cache stampede, kết hợp Redis và NoSQL làm nguồn chính, đo freshness SLO, kiểm thử lỗi và xây runbook vận hành. Ví dụ tập trung vào các tình huống thực tế thay vì giả định cache luôn chứa dữ liệu chính xác.

## 1. Nguồn dữ liệu và cache có vai trò khác nhau

Kiến trúc đơn giản:

~~~mermaid
flowchart LR
    U["Ứng dụng / API"] --> C["Redis cache"]
    U --> D["MongoDB: nguồn có thẩm quyền"]
    D -. "Đọc khi miss / đồng bộ" .-> C
~~~

Các nguyên tắc:

- **Source of truth** là nơi quyết định trạng thái nghiệp vụ được công nhận.
- **Cache** là bản sao phục vụ truy vấn nhanh hơn, thường có thể xóa và tái tạo.
- **Cache hit** chứng minh key có dữ liệu trong cache, **không chứng minh giá trị vẫn đúng ở nguồn**.
- **Cache miss** không có nghĩa đối tượng không tồn tại; chỉ có nghĩa lớp cache không có dữ liệu hợp lệ theo giao thức của nó.
- **TTL hết hạn** không có nghĩa dữ liệu đã được xóa khỏi tất cả nơi lưu hoặc mọi request in-flight đã dừng sử dụng bản cũ.
- **Một write thành công ở source** không tự bảo đảm các cache nodes đã thấy giá trị mới.

Một bản ghi sản phẩm có thể gồm:

~~~json
{
  "tenantId": "shop-a",
  "productId": "p-101",
  "priceVnd": 149000,
  "availableQuantity": 7,
  "version": 18
}
~~~

Cache thường chỉ nên lưu các trường cần cho read path. Nếu một trường là **đầu vào của quyết định không được sai**, phải xác định cách xác minh ở nguồn tại thời điểm thực hiện quyết định.

## 2. Ba khái niệm dễ bị nhầm

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| **TTL** | Một entry được coi là hợp lệ trong cache bao lâu kể từ mốc đặt TTL? | 60 giây |
| **Freshness / độ mới** | Kết quả đọc phản ánh trạng thái nguồn mới đến đâu? | Đã thấy version 20 |
| **Staleness / độ cũ** | Một thay đổi tại nguồn chưa được phản ánh tới nơi đọc trong bao lâu? | Giá mới đã commit 4 giây, cache còn giá cũ |
| **Invalidation** | Khi nào và bằng cách nào loại bỏ/đánh dấu cache entry không còn tin cậy? | Xóa key sau UPDATE |
| **Refresh** | Lấy lại dữ liệu từ source để thay entry? | Nạp phiên bản 20 |
| **Eviction** | Đẩy entry ra vì thiếu bộ nhớ hoặc chính sách lưu trữ? | Loại key ít truy cập |
| **Retention** | Dữ liệu/tombstone/event được giữ trong hệ thống bao lâu? | Lưu audit 90 ngày |

**TTL và staleness không giống nhau.** Một entry mới được tạo 1 giây trước có thể đã stale nếu source vừa thay đổi; một entry tồn tại 20 phút vẫn có thể chính xác nếu source chưa hề đổi.

## 3. Tuổi của cache entry khác độ cũ so với nguồn

Giả sử:

~~~text
10:00:00 Redis SET price:p-101 = 149000, TTL 300s.
10:00:01 MongoDB commit giá mới 139000.
10:00:02 User đọc Redis -> 149000.
~~~

Tại 10:00:02:

- **Cache age**: khoảng 2 giây.
- **Dữ liệu đã stale**: khoảng 1 giây kể từ commit giá mới.
- **TTL còn lại**: khoảng 298 giây.

Nếu không có invalidation, stale có thể tiếp tục gần hết TTL. Nếu một read miss đúng lúc source vừa commit, entry có thể được nạp mới và không stale. Mối liên hệ phụ thuộc **thời điểm source thay đổi, thời điểm cache fill và cách invalidation hoạt động**.

Vì vậy dashboard có metric **cache entry age thấp** chưa đủ chứng minh dữ liệu đúng.

## 4. Freshness SLO phải được mô tả bằng hành vi quan sát được

Một yêu cầu có thể là:

> 99,9% cập nhật giá sản phẩm đã commit phải trở nên hiển thị tại endpoint đọc trong tối đa 5 giây, khi các thành phần hạ tầng hoạt động theo phạm vi SLO đã định nghĩa.

Để đo:

~~~text
t_commit = thời điểm thay đổi được source công nhận.
t_visible = thời điểm đường đọc bắt đầu trả version mới.

visibilityLag = t_visible - t_commit
~~~

Một số câu hỏi bắt buộc:

- Endpoint nào phải đạt SLO?
- Có tính các cache L1 ở mỗi instance không?
- Có tính ứng dụng mobile, CDN hoặc browser cache không?
- Đo theo **events**, **requests**, hay **resources**?
- Percentile nào, cửa sổ đánh giá nào và điều kiện loại trừ nào?
- Một DELETE hoặc thu hồi quyền có chung SLO với giá hay có yêu cầu nghiêm ngặt hơn?

**p99 cache hit latency** là metric hiệu năng, không phải **p99 visibility lag**.

## 5. TTL tuyệt đối: một mốc hết hạn cố định

Với **absolute TTL**, sau khi đặt entry:

~~~text
SET at 10:00:00
TTL = 60 seconds
Expires at 10:01:00
~~~

Các lần GET không kéo dài thời hạn.

Ưu điểm:

- Dễ dự đoán khoảng thời gian giữ một entry.
- Hạn chế việc dữ liệu cũ sống vô hạn chỉ vì được đọc thường xuyên.
- Phù hợp cache-aside cho nhiều dữ liệu đọc.

Giới hạn:

- Source có thể thay đổi ngay sau khi cache được nạp, khiến entry stale gần toàn bộ TTL.
- Nhiều keys hết hạn đồng loạt có thể gây spike tại source.
- TTL chỉ kiểm soát cache entry, không tự đồng bộ local caches, CDN hoặc client.

Nếu cache **không làm mới TTL bằng giá trị cũ** và mọi miss đọc nguồn đủ mới, TTL 60 giây là một thành phần để ước lượng khoảng hiển thị stale, **không phải bảo đảm end-to-end vô điều kiện**.

## 6. Sliding TTL: mỗi lần truy cập gia hạn

Với **sliding expiration**:

~~~text
10:00 SET key, TTL 60s.
10:00:50 GET -> gia hạn đến 10:01:50.
10:01:40 GET -> gia hạn đến 10:02:40.
...
~~~

Một hot key có thể tồn tại rất lâu khi liên tục được đọc. Nếu không có invalidation hoặc cơ chế kiểm tra nguồn, **giá trị cũ có thể tồn tại không giới hạn theo số lần đọc**.

Sliding TTL có thể hữu ích cho session/cache không cần ràng buộc freshness chặt, nhưng cần:

- Chính sách invalidation khi source đổi.
- Một **absolute maximum lifetime** hoặc max staleness riêng nếu dữ liệu có thể thay đổi.
- Giới hạn số lần gia hạn hoặc version check theo business needs.

**Không dùng sliding TTL như một sự thay thế cho độ mới dữ liệu.**

## 7. Soft TTL, hard TTL và khoảng stale cho phép

Một entry có thể có hai mốc:

~~~json
{
  "value": {"priceVnd": 149000},
  "sourceVersion": 18,
  "freshUntil": "10:00:30Z",
  "serveStaleUntil": "10:01:30Z"
}
~~~

Quy tắc:

| Thời điểm | Hành vi |
|---|---|
| Trước freshUntil | Serve từ cache nếu hợp lệ theo guard |
| Từ freshUntil tới serveStaleUntil | Có thể serve stale **nếu endpoint cho phép**, đồng thời refresh |
| Sau serveStaleUntil | Không serve entry nữa; load source hoặc báo lỗi |

**Soft TTL** đánh dấu cần refresh. **Hard TTL** đánh dấu không được dùng bản cũ sau mốc đó theo contract.

Lưu ý: nếu hard TTL chỉ do application tự kiểm, Redis key có thể còn tồn tại vật lý. Code phải kiểm mốc và **không dùng stale branch sau hạn**. Ngược lại nếu xóa Redis key ngay tại soft TTL, sẽ không còn bản cũ để hỗ trợ stale-while-revalidate.

## 8. Stale-while-revalidate (SWR)

SWR trả cache cũ trong một cửa sổ được cho phép, đồng thời làm mới ở nền hoặc qua một request khác.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant K as Cache
    participant D as Source
    C->>A: GET product
    A->>K: GET cached entry
    K-->>A: value v18, soft TTL expired
    A-->>C: value v18 (allowed stale)
    A->>D: refresh with bounded work
    D-->>A: value v19
    A->>K: store v19 with freshness metadata
~~~

Ưu điểm: giảm latency trên hot paths và giảm tải khi nhiều entries cần refresh.

Điều kiện:

- Product owner chấp nhận khoảng stale.
- Có **hard limit** và chặn refresh vô hạn.
- Refresh được coalesce, bounded và version-aware.
- Có observability về dữ liệu stale được phục vụ.
- Bảo mật/quyền truy cập không phụ thuộc một cache permission stale.

Nếu mỗi GET phục vụ stale và đồng thời tạo một refresh độc lập, SWR có thể gây **stampede** giống cache miss.

## 9. Stale-if-error

Khi source lỗi, một số read-only endpoints có thể chấp nhận trả bản cũ trong giới hạn:

~~~text
Normal:
  cache fresh -> serve.

Source temporarily down:
  cache stale 20s -> serve nếu policy cho phép.

Cache stale 5m:
  không serve nếu hard limit 60s.
~~~

Các cách ứng xử:

- **Fail open có giới hạn:** phục vụ stale để duy trì UX ít nhạy cảm.
- **Fail closed:** trả lỗi/đọc lại nguồn đáng tin, không dùng cache stale.
- **Degraded response:** trả dữ liệu có nhãn độ mới và hạn chế hành động.

Không áp dụng một stale-if-error policy cho **giá thanh toán, quyền truy cập, quyết định cấp hạn mức và số lượng hàng được phép giữ** nếu nghiệp vụ yêu cầu tính đúng mạnh.

Một lỗi source kéo dài không nên khiến hệ âm thầm bỏ giới hạn cũ đi để “giữ availability”.

## 10. Redis TTL: những thao tác cơ bản

Redis hỗ trợ TTL theo giây, mili giây và thời điểm hết hạn.

Ví dụ minh họa trong Redis CLI:

~~~redis
SET product:shop-a:p-101 "{\"priceVnd\":149000,\"version\":18}" EX 60
GET product:shop-a:p-101
TTL product:shop-a:p-101
PTTL product:shop-a:p-101
EXPIRE product:shop-a:p-101 30
DEL product:shop-a:p-101
~~~

Ý nghĩa:

- **SET ... EX 60:** ghi giá trị và TTL 60 giây cùng lệnh.
- **TTL:** thời gian còn lại tính bằng giây, với một số giá trị đặc biệt khi key vắng mặt hoặc không có expiry.
- **PTTL:** độ chính xác mili giây.
- **EXPIRE:** đặt/gia hạn thời hạn.
- **DEL:** xóa key (có thể thay UNLINK cho một số tình huống muốn giải phóng bộ nhớ theo cơ chế khác).

Redis cũng có các biến thể **PX, EXAT, PXAT, PEXPIRE, PERSIST, GETEX**; lựa chọn phụ thuộc API và phiên bản Redis đang dùng. **GETEX** có thể thay TTL khi đọc, nên dùng không đúng sẽ biến absolute TTL thành sliding TTL.

Không nên đặt SET thiếu expiry trong đường cache rồi tưởng TTL cũ vẫn còn: **một số thao tác ghi đè có thể thay đổi hoặc xóa expiry**, cần đọc chính xác semantics của command.

## 11. TTL key đã hết hạn không nhất thiết bị giải phóng tức thì

Redis thường kết hợp:

- **Lazy expiration:** phát hiện key hết hạn khi được truy cập.
- **Active expiration:** chủ động lấy mẫu/dọn một phần keys đã hết hạn.

Hệ thống có thể coi key đã hết hạn là không còn hợp lệ trước khi bộ nhớ vật lý được giải phóng hết.

Vì thế:

- **TTL không phải thời điểm bảo đảm RAM sẽ giảm chính xác từng byte**.
- Đếm physical entries hoặc memory usage không thể dùng một mình để khẳng định nội dung còn hợp lệ.
- Cần theo dõi memory pressure, expired keys và eviction riêng.

TTL của cache còn khác hoàn toàn yêu cầu **xóa dữ liệu cá nhân khỏi mọi bản sao, backup hoặc offline clients**.

## 12. Cache expiration khác cache eviction

| Cơ chế | Trigger | Hệ quả |
|---|---|---|
| Expiration | TTL đã hết theo thời gian | Entry không còn hợp lệ theo expiry |
| Eviction | Bộ nhớ/giới hạn dung lượng và policy | Entry có thể bị loại **trước TTL** |
| Invalidation | Source/event/app nhận biết bản cũ | Xóa/đánh dấu cần tải mới |
| Manual purge | Ops/incident/security | Loại một phạm vi dữ liệu theo runbook |

Với Redis, **maxmemory policy** quyết định cách xử lý khi memory pressure, có thể là loại một số keys hoặc từ chối operations tùy cấu hình. Không giả định Redis chỉ xóa keys khi TTL hết.

Nếu cache bị eviction nhiều:

~~~text
More misses -> more source reads -> higher latency/load
~~~

Do đó cache capacity và eviction rate cũng thuộc bài toán tính hiệu quả của TTL.

## 13. Cache-aside (lazy loading)

Đây là mẫu phổ biến khi ứng dụng tự điều khiển cache:

~~~mermaid
flowchart TD
    A["GET product"] --> B{"Cache hit?"}
    B -->|"Có"| C["Trả cache nếu thỏa freshness policy"]
    B -->|"Không"| D["Read authoritative source"]
    D --> E["Set cache với TTL/version"]
    E --> F["Trả dữ liệu"]
~~~

Pseudo:

~~~text
readProduct(id):
  cached = cache.get(id)
  if cached is permitted and fresh:
      return cached

  value = source.read(id)
  cache.set(id, value, ttl)
  return value
~~~

Ưu điểm:

- Chỉ cache keys thực sự được truy cập.
- Dễ bổ sung cho ứng dụng hiện có.
- Có thể degrade về source khi Redis không khả dụng.

Nhược điểm:

- Miss đầu tiên tốn thêm latency.
- Invalidation cần do ứng dụng hoặc pipeline thực hiện.
- Có race **stale refill** giữa source read và cache set.
- Hot key hết TTL có thể gây stampede.

## 14. Cache-aside write: cập nhật source trước, rồi invalidate

Một thứ tự thường dùng:

~~~text
1. UPDATE authoritative DB.
2. DB commit thành công.
3. DEL cache key (hoặc phát invalidation event).
4. Trả kết quả theo API contract.
~~~

**Không invalidate trước khi source commit rồi coi là xong.** Nếu cache miss trong lúc source còn giá cũ, nó có thể nạp lại giá cũ; sau commit không còn invalidation nào nữa.

Tuy vậy, thứ tự **commit rồi DEL** vẫn **chưa đủ để loại mọi race**, vì một request đọc cũ từ trước có thể ghi cache sau DEL. Ta cần xem xét lịch cụ thể ở phần sau.

Nếu write thành công ở DB nhưng process crash trước DEL, cache vẫn stale. Với yêu cầu freshness đáng tin, dùng **outbox/CDC** hoặc cơ chế recovery để không bỏ mất invalidation intent.

## 15. Read-through cache

Trong read-through, tầng cache hoặc một thư viện/data access layer tự chịu trách nhiệm lấy dữ liệu từ source khi miss.

~~~text
Application -> Cache provider
                  |
                  +-- hit -> value
                  +-- miss -> load from source, store, return
~~~

Lợi ích:

- Có thể dùng chung loading/instrumentation.
- Giảm code cache-aside rải rác.
- Dễ coalesce loads tại một điểm.

Giới hạn:

- Provider phải biết cách load đúng authorization/tenant scope.
- Vẫn có invalidation và stale refill races.
- Không phải mọi NoSQL/cache framework hỗ trợ read-through cùng semantics.
- Không nên đưa toàn bộ business invariant vào một generic cache adapter thiếu quyền kiểm soát.

Read-through không tự tạo **strong consistency** giữa cache và source.

## 16. Write-through cache

Trong write-through, ứng dụng viết qua một tầng điều phối:

~~~text
Application -> Write-through layer
                  -> Authoritative store
                  -> Cache update
~~~

Mục tiêu là cache được cập nhật cùng luồng ghi để giảm stale windows.

Nhưng phải hỏi:

- Nếu source write thành công mà cache update thất bại thì sao?
- Nếu cache thành công trước nhưng source commit thất bại thì sao?
- Có transaction chung không?
- Hai concurrent writes có thể cập nhật cache sai thứ tự không?
- API trả success sau bước nào?

**Write-through chỉ đồng nghĩa consistency mạnh nếu implementation có giao thức bảo đảm**, không phải vì tên pattern.

Thông thường, xác lập **source là authority**, rồi dùng versioned update/invalidation và retry khi cache lỗi.

## 17. Write-behind / write-back

Write-behind ghi vào cache/queue trước, rồi đưa về nguồn sau:

~~~text
Application -> Cache/buffer -> async flush -> Database
~~~

Nó có thể giảm latency ghi, nhưng mở thêm rủi ro:

- Cache/queue mất dữ liệu chưa flush.
- Thứ tự flush sai.
- Restart gây duplicate writes.
- Source từ chối một mutation sau khi client đã được ACK.
- Cần durable log, idempotency và recovery.

Nếu cache là nơi duy nhất biết write chưa flush, **nó không còn là bản sao bỏ được**. Khi ấy phải thiết kế durability, replication, WAL và ownership tương ứng, không dùng assumptions của cache thuần.

**Không dùng write-behind cho nghiệp vụ đòi ACK đồng nghĩa đã commit bền ở nguồn** nếu chưa có protocol đáp ứng yêu cầu đó.

## 18. Invalidation chủ động và TTL nên kết hợp

Có hai đường:

**Chủ động:**

~~~text
Source UPDATE/DELETE
  -> invalidation event
  -> cache delete/update
~~~

**Thụ động:**

~~~text
Cache TTL hết
  -> lần đọc sau nạp từ source
~~~

Khi kết hợp:

- Invalidation giúp dữ liệu mới hiển thị nhanh hơn TTL.
- TTL giới hạn một số lỗi khi event invalidation bị bỏ sót **nếu không có TTL refresh bằng bản cũ và nguồn đọc đủ mới**.
- TTL có thể làm fallback an toàn hơn nhưng không thay source-of-truth validation cho quyết định critical.
- Monitoring phải phát hiện invalidation pipeline hỏng, không để TTL che kín sự cố quá lâu.

**TTL là một safety net có điều kiện, không phải bằng chứng hệ đồng bộ chính xác.**

## 19. Transactional outbox và CDC cho invalidation

Lỗi kinh điển:

~~~text
1. MongoDB commit price version 19.
2. App định DEL cache.
3. App crash trước DEL.
~~~

Cache có thể giữ v18 đến khi TTL hết.

Một thiết kế:

~~~text
DB atomic unit:
  UPDATE product rev19
  SAVE outbox event ProductUpdated(rev19, operationId)
COMMIT

Relay:
  đọc outbox hoặc CDC
  publish invalidation event

Consumers:
  invalidate/update Redis + L1 caches
~~~

Những điểm quan trọng:

- Outbox và mutation nguồn phải có **cùng fate commit** trong phạm vi transaction được hỗ trợ.
- Relay có thể phát lại event; consumer phải idempotent.
- Event có thể đến không đúng thứ tự, nên mang revision/generation.
- DELETE phải có tombstone hoặc version floor để event UPDATE cũ không tái tạo bản đã xóa.
- Pipeline lag trở thành một **freshness metric**.

Một pipeline đáng tin vẫn cần retry, dead-letter handling, reconciliation và monitoring.

## 20. Race khó: stale refill sau khi invalidate

Giả sử cache-aside và UPDATE đều chạy đúng thứ tự tưởng như hợp lý:

~~~text
t1  Reader R cache miss.
t2  R đọc MongoDB price=v18.
t3  Writer W cập nhật MongoDB price=v19, COMMIT.
t4  W DEL cache key.
t5  R SET cache price=v18, TTL=300s.
t6  Các readers khác thấy v18.
~~~

**DEL sau commit đã chạy**, nhưng stale value vẫn quay lại do request cũ **nạp muộn**.

~~~mermaid
sequenceDiagram
    participant R as Reader R
    participant D as Source DB
    participant W as Writer W
    participant C as Cache
    R->>C: GET -> MISS
    R->>D: READ
    D-->>R: version 18
    W->>D: UPDATE version 19, COMMIT
    W->>C: DEL key
    R->>C: SET version 18, TTL 300s
    Note over C: Cache chứa bản cũ trở lại
~~~

Đây là **race giữa read, invalidation và cache fill**. Giảm TTL chỉ rút ngắn một số hậu quả; không sửa nguyên nhân.

## 21. Hướng khắc phục race: version-aware population

Một cách tiếp cận là làm mọi cache entry mang **source version**:

~~~json
{
  "productId": "p-101",
  "priceVnd": 149000,
  "sourceVersion": 18
}
~~~

Khi version 19 được ghi nhận tại cache hoặc một metadata store, request cố ghi version 18 bị từ chối.

Logic khái niệm:

~~~text
cacheWrite(candidate):
  atomically compare candidate.version to cache.highestKnownVersion
  if candidate.version < highestKnownVersion:
      reject stale fill
  else:
      write candidate and update version metadata
~~~

Điều kiện:

- Version phải được **nguồn có thẩm quyền cấp**, không do reader tự đoán.
- So version và ghi payload phải **nguyên tử ở cache/sink**.
- Invalidation event nên mang **minimum accepted version**.
- Khi xóa key hoặc hết TTL, không được làm mất high-watermark theo cách cho phép v18 được chấp nhận lại.
- Nếu cần độ mới chặt, đọc metadata version từ authority hoặc giao thức đồng bộ mạnh hơn.

**Chỉ so phiên bản đang có trong cache chưa đủ** nếu cache key vừa bị DEL và version floor cũng biến mất.

## 22. Versioned keys và generation keys

Một kỹ thuật là gắn version vào cache key:

~~~text
product:shop-a:p-101:v18
product:shop-a:p-101:v19
~~~

Khi reader biết **authoritative currentVersion=19**, nó chỉ đọc key v19. Bản v18 dù còn tồn tại cũng không được chọn.

Ưu điểm:

- Không có in-place overwrite cùng key giữa các versions.
- Có thể cache kết quả immutable của từng version.
- Dễ ngăn stale writer ghi vào key version mới.

Đánh đổi:

- Reader phải lấy **currentVersion** từ nơi đáng tin.
- Nếu currentVersion pointer cũng cache stale, reader vẫn có thể chọn v18.
- Keys cũ tăng dung lượng, cần cleanup/TTL.
- Cần bảo vệ generation khi dữ liệu DELETE rồi RECREATE.

**Versioned key chỉ mạnh khi cách chọn version đủ đúng**. Không tự tuyên bố strong consistency nếu currentVersion lấy từ một cache khác cũng eventual.

## 23. Delayed double delete: mẹo giảm race, không phải bảo đảm

Một số hệ dùng:

~~~text
DB commit.
DEL cache.
Chờ một thời gian ngắn.
DEL cache lần nữa.
~~~

Lần DEL thứ hai có thể xóa bản cũ được reader nạp lại sau DEL đầu.

Nhưng:

- Reader có thể bị pause lâu hơn khoảng chờ.
- Lần DEL thứ hai có thể bị mất khi process crash.
- Không chặn hoàn toàn replay từ cache khác.
- Một delay cố định không chứng minh absence of stale fill trong hệ phân tán.

Có thể dùng như **risk mitigation phụ** cho workload chấp nhận stale, nhưng không thay version guard, outbox hoặc một protocol có consistency phù hợp khi correctness quan trọng.

## 24. Cache stampede / thundering herd

Một hot key có 10.000 requests/giây:

~~~text
t0  Key hết TTL.
t1  Hàng nghìn requests cùng GET -> MISS.
t2  Mỗi request đọc source.
t3  Source quá tải và timeout.
~~~

TTL giảm tải khi hit nhưng có thể tạo spike khi hết hạn đồng loạt.

Biện pháp:

- **Singleflight/request coalescing:** một load cho cùng key, các requests khác chờ kết quả.
- **Distributed lock có thời hạn** cho hot key nếu cần.
- **Jitter TTL:** keys không hết cùng lúc.
- **Refresh-ahead/SWR:** nạp trước khi hard expiry.
- **Rate limit/queue/bulkhead:** bảo vệ source.
- **Stale-if-error có giới hạn** nếu an toàn nghiệp vụ.

Coalescing tránh số loads đồng thời, nhưng phải có timeout và failure recovery; không để một leader bị treo làm mọi readers chờ vô hạn.

## 25. Singleflight trong một process

Ví dụ giả lập:

~~~text
if cache hit:
    return cached

with perKeySingleflight(key):
    recheck cache
    if now hit:
        return cached
    value = source.read(key)
    cache.set(key, value, ttl)
    return value
~~~

**Double-check** bên trong coalescing quan trọng: một request có thể đã nạp cache trong khi request khác đợi lock.

Nhưng singleflight **trong một JVM** chỉ gộp requests ở JVM ấy. Nếu có 100 API instances, vẫn có thể có 100 loads cho cùng hot key. Có thể dùng distributed coordination, nhưng cần tránh biến lock store thành nút thắt và phải xử lý stale owner/lease.

Với dữ liệu critical, singleflight không thay thế version-aware fill.

## 26. Distributed lock cho refresh có giới hạn

Một lock dùng để quyết định **ai được refresh cache**:

~~~text
Acquire refresh-lock for key K.
If acquired:
  read source.
  publish refreshed cache entry.
Else:
  wait briefly, serve allowed stale, or load source with limits.
~~~

Điều kiện:

- Lock có TTL và owner token để tránh xóa lock người khác.
- Worker cũ có thể bị GC pause sau khi lock hết hạn.
- Nếu nhiều refresh writers có thể ghi, cần **version/fencing guard** ở cache.
- Không đặt mọi read vào distributed lock nếu sẽ tạo bottleneck.
- Có metrics lock contention và refresh failure.

**Lock refresh giảm tải source nhưng không tự đảm bảo cache luôn chứa dữ liệu mới nhất**.

## 27. TTL jitter ngăn hết hạn đồng loạt

Giả sử mọi key được set với TTL đúng 300 giây sau một batch import. Đến phút thứ năm, hàng loạt keys cùng miss.

Một chính sách:

\[
\mathrm{TTL}_{\mathrm{effective}}
=\mathrm{TTL}_{\mathrm{base}}\times U(0{,}8,1{,}0)
\]

với \(U\) là biến ngẫu nhiên đều trong khoảng 0,8–1,0.

Ví dụ TTL base 300 giây trở thành ngẫu nhiên 240–300 giây.

**Jitter nên ngắn hơn hoặc bằng hard freshness budget** nếu TTL là lớp giới hạn stale. Nếu chỉ nhân TTL lên 1,2 mà không điều chỉnh SLO, một số entries sẽ tồn tại lâu hơn mức được phép.

Jitter giải quyết **đỉnh miss đồng loạt**, không giải quyết stale source hoặc mất invalidation events.

## 28. Negative caching: “không tìm thấy” cũng là một giá trị

Giả sử product **p-999** chưa tồn tại:

~~~text
GET p-999 -> source NOT_FOUND
Cache "not found" 60 giây.
~~~

Sau 5 giây, product được tạo. Nếu negative cache còn 55 giây, API có thể vẫn báo **404**.

Vì vậy negative caching cần:

- TTL ngắn hơn theo nhu cầu tạo mới.
- Invalidation khi object được CREATE.
- Phân biệt **NOT_FOUND xác định** với **source timeout/permission denied**.
- Tenant scope và authz.
- Không cache các 5xx như “không có bản ghi” nếu outcome chưa rõ.

Negative caching có lợi khi nhiều requests hỏi IDs không tồn tại, nhưng có thể làm new data bị ẩn trong một khoảng thời gian.

## 29. Không cache kết quả authorization cũ như dữ liệu thường

Giả sử user-B có quyền xem document:

~~~text
Cache permission(user-B,doc-42)=ALLOW, TTL 10 phút.
Quản trị viên thu hồi quyền ở t=0.
User-B request ở t=1 phút.
~~~

Nếu API chỉ tin cache ALLOW, quyền bị thu hồi nhưng nội dung vẫn lộ.

Đối với access control:

- Xác định thời điểm quyền mới phải có hiệu lực.
- Có thể cần policy check tại authoritative service hoặc token/permission epoch.
- Invalidation/short TTL hỗ trợ hiệu năng nhưng không đủ cho yêu cầu “revoke ngay”.
- Cache key phải gắn tenant, principal, policy context và version thích hợp.
- Không để dữ liệu của user A được phục vụ cho user B vì cache key chỉ chứa documentId.

**Một security invariant không nên phụ thuộc vào TTL may mắn hết sớm**.

## 30. Giá hiển thị và giá tính tiền khác nhau

Ví dụ:

~~~text
Product page:
  giá hiển thị có thể chấp nhận stale vài giây theo policy.

Checkout:
  giá để tính tiền phải dựa trên snapshot/rule giao dịch được công nhận.
~~~

Nếu cache hiển thị giá cũ:

- UI có thể thông báo giá được cập nhật khi checkout.
- API checkout đọc authoritative pricing source hoặc quote có hiệu lực theo version/expiry.
- Không thu tiền chỉ dựa trên một cache key đã stale.

Tương tự với inventory:

~~~text
UI "còn hàng" có thể là ước lượng.
ReserveStock phải dùng atomic condition ở source.
~~~

Một endpoint **đọc tham khảo** và một operation **ra quyết định** không nên dùng cùng consistency guarantee một cách mù quáng.

## 31. TTL theo loại dữ liệu, không đặt một giá trị toàn hệ

Ví dụ policy matrix (chỉ minh họa):

| Loại dữ liệu | Ví dụ TTL | Điều kiện bổ sung |
|---|---|---|
| Danh mục ít thay đổi | 5–30 phút | Invalidation khi quản trị sửa |
| Thông tin sản phẩm phổ biến | 30–120 giây | Event-driven invalidation |
| Kết quả search | 10–60 giây | Chấp nhận index lag, version/schema |
| Giá hiển thị | 5–30 giây | Giá chốt tại checkout authoritative |
| Inventory hiển thị | Vài giây | Reserve có conditional write tại nguồn |
| Negative lookup | 1–10 giây | CREATE invalidation |
| User profile không nhạy | Tùy tốc độ thay đổi | Tenant/user scope |
| Quyền truy cập | Theo policy bảo mật | Không dựa duy nhất vào TTL |
| Payment/ledger authoritative | Thường không dùng cache cho commit decision | Transaction/strong validation |

Không lấy các khoảng trong bảng làm **chuẩn chung**. TTL đúng phụ thuộc tần suất cập nhật, business impact, mức tải, propagation delay và độ chính xác cần đạt.

## 32. Chọn TTL dựa trên chi phí stale và chi phí miss

TTL ngắn:

- Ít khoảng stale khi không có event invalidation.
- Tăng cache misses và source load.
- Có thể tăng network/CPU.

TTL dài:

- Hit ratio thường cao hơn với dữ liệu ổn định.
- Giảm source reads.
- Tăng thời gian hiển thị bản cũ nếu invalidation bị lỗi.

Một mô hình quyết định:

\[
C_{\text{total}}(T)
=C_{\text{cache}}(T)
+C_{\text{miss}}(T)
+C_{\text{staleness}}(T)
+C_{\text{operations}}(T)
\]

Trong đó \(T\) là TTL; từng thành phần phụ thuộc workload và policy.

Không nhất thiết có một TTL tối ưu bằng công thức đóng. Thường cần **đo hit ratio, write rate, staleness SLO và impact của sai dữ liệu**, rồi thử có kiểm soát.

## 33. Ước lượng staleness khi chỉ dựa vào TTL

Giả sử:

- Cache-aside absolute TTL 60 giây.
- Không refresh old value bằng sliding TTL.
- Không có SWR/stale-if-error.
- Mỗi cache miss đọc source **đủ mới**.
- Cache fill không bị stale refill race.
- Không có cache tầng khác giữ dữ liệu lâu hơn.

Nếu source đổi ngay sau khi một entry được tạo, entry có thể stale **gần 60 giây**.

Nhưng nếu có SWR thêm 30 giây, một entry có thể được phục vụ stale lâu hơn 60 giây theo policy. Nếu hệ dùng sliding TTL, khoảng stale có thể không có bound từ TTL đơn lẻ. Nếu reader cũ ghi lại cache sau invalidate, giới hạn cũng thay đổi theo thời điểm stale fill.

**Một guarantee về staleness luôn đi kèm giả thiết về mọi đường nạp và phục vụ dữ liệu**.

## 34. Freshness budget nhiều tầng

Ví dụ một write phải trở nên hiển thị tại một API trong 5 giây:

~~~text
Source commit
  -> outbox/CDC relay
  -> broker
  -> Redis invalidation
  -> local L1 cache invalidation
  -> next source read
~~~

Mỗi chặng có độ trễ riêng. Một cách bắt đầu là phân bổ budget:

| Chặng | Mục tiêu ví dụ |
|---|---:|
| CDC relay | 1,5 giây |
| Broker/consumer | 1,0 giây |
| Redis invalidation | 0,5 giây |
| L1 cache propagation | 1,0 giây |
| Margin | 1,0 giây |

Đây là **budget thiết kế**, không phải bằng chứng p99 end-to-end đạt 5 giây. **Không thể đơn giản cộng các p99 thành p99 tổng** mà không xét phân bố và tương quan độ trễ. Cần đo end-to-end commit-to-visible trực tiếp.

Với nhiều cache tiers, yếu tố chậm nhất có thể quyết định độ mới được người dùng quan sát.

## 35. Multi-level cache: L1 trong ứng dụng, L2 Redis

Một hệ:

~~~text
API instance A -> local L1 -> Redis L2 -> MongoDB
API instance B -> local L1 -> Redis L2 -> MongoDB
~~~

Khi source UPDATE:

~~~text
DEL Redis L2
~~~

**Không tự xóa L1** trên A/B. Một instance vẫn có thể trả giá cũ từ bộ nhớ JVM trong khi Redis đã mới.

Các lựa chọn:

- L1 TTL rất ngắn.
- Broadcast invalidation event tới mọi instances.
- Epoch/version check tại L1.
- Không dùng L1 cho dữ liệu nhạy nếu không đảm bảo invalidation.
- Sử dụng per-request/per-session cache có lifetime rõ.

Càng nhiều lớp cache, cần càng rõ **mỗi lớp có freshness budget, ownership và failure mode nào**.

## 36. CDN, browser và mobile cũng là cache

Một API có thể đã xóa Redis key nhưng trình duyệt vẫn giữ response theo HTTP cache headers.

Cần kiểm soát:

- Cache-Control và shared/private caches.
- ETag/conditional requests.
- CDN purge hoặc cache key versioning.
- Browser service worker storage.
- Mobile offline store và sync epoch.
- HTTP 304 chỉ có ý nghĩa khi validation phản ánh trạng thái nguồn phù hợp.

Với nội dung private, phải đảm bảo **không đặt response có PII vào shared cache không được phân vùng quyền**.

**Redis invalidation không lan tự động sang CDN, browser và mobile.** Trước khi định nghĩa “freshness 5 giây”, hãy liệt kê tất cả nơi một response có thể được giữ.

## 37. Cache key phải bao trùm ngữ cảnh

Một key sai:

~~~text
product:p-101
~~~

nếu giá sản phẩm thay đổi theo tenant/currency/price list.

Key có thể cần:

~~~text
product:shop-a:p-101:VND:priceList-v3
~~~

Đối với user-specific response:

~~~text
profile:tenant-7:user-11:policy-v4
~~~

Những field nên xét:

- Tenant/account.
- Resource identity.
- Locale/currency.
- Query parameters/filter/sort.
- Permission context nếu response được authorization-filtered.
- Schema/index version.
- Feature flags ảnh hưởng payload.

Key sai dẫn đến **cache collision và data leak**. Key quá chi tiết dẫn đến hit ratio thấp và cardinality cao. Cần thiết kế dựa trên semantics của response, không chỉ ghép tùy ý mọi tham số.

## 38. Cache query results khó vô hiệu hóa hơn cache entity

Cache entity:

~~~text
product:shop-a:p-101
~~~

thường có invalidation scope rõ.

Cache query:

~~~text
products:tenant=shop-a:category=shoes:sort=price:page=2
~~~

có thể bị ảnh hưởng bởi bất kỳ product nào:

- Đổi category.
- Đổi giá làm thay đổi vị trí sort.
- Được CREATE/DELETE.
- Đổi status hide/active.

Một entity UPDATE có thể ảnh hưởng **nhiều query cache keys** mà hệ không dễ liệt kê.

Các hướng:

1. TTL ngắn cho query results.
2. Namespace generation theo tenant/category.
3. Event invalidation theo dependency tags.
4. Cache IDs rồi load/validate details.
5. Không cache truy vấn có cardinality/combination quá lớn.

Đổi một product làm tăng category generation có thể vô hiệu hóa toàn bộ các pages của category; đánh đổi là nhiều misses nhưng dễ đảm bảo logic hơn việc cố xác định mọi query liên quan.

## 39. Namespace generation để vô hiệu hóa cả nhóm

Ví dụ:

~~~text
catalogGeneration:shop-a:shoes = 27
productsQuery:shop-a:shoes:g27:sort-price:p2
~~~

Khi có một thay đổi ảnh hưởng category:

~~~text
Increment catalogGeneration -> 28.
Các readers dùng g28.
Keys g27 sẽ hết TTL/dọn sau.
~~~

Ưu điểm:

- Invalidate logical namespace mà không scan/DEL hàng triệu keys.
- Dữ liệu cũ không được chọn sau khi readers đã biết generation mới.

Giới hạn:

- Reader có thể cache **generation 27 cũ**.
- Generation tăng phải có authority/durability phù hợp.
- Đổi category có thể cần bump **cả category cũ lẫn mới**.
- TTL của keys g27 vẫn tiêu thụ storage đến khi dọn.
- Tăng generation thường xuyên có thể giảm hit ratio.

**Generation invalidation chỉ mạnh bằng tính đúng của bước đọc generation đang hiệu lực.**

## 40. Time-based TTL và đồng hồ

TTL theo duration và expiry theo wall-clock cần phân biệt.

Một entry application-level:

~~~json
{
  "createdAt": "2026-11-14T10:00:00Z",
  "freshUntil": "2026-11-14T10:01:00Z"
}
~~~

Nếu các API nodes có đồng hồ lệch, một node có thể xem entry vẫn fresh trong khi node khác cho rằng đã hết hạn.

Nên:

- Xác định **clock authority** cho việc tạo/kiểm freshness metadata.
- Dùng server-side TTL command khi phù hợp.
- Đo clock skew và giới hạn drift theo hạ tầng.
- Tránh tin timestamp do client tùy ý gửi để khẳng định freshness.
- Tách **business effectiveAt** khỏi **cache createdAt/expiryAt**.

Nếu nguồn có revision/event sequence, version guard thường chắc chắn hơn việc chỉ so updatedAt của các nodes.

## 41. Invalidation event đến trùng hoặc đảo thứ tự

Timeline:

~~~text
Product version 18 -> cache v18.
Product UPDATE v19 -> event E19.
Product UPDATE v20 -> event E20.

Consumer nhận:
  E20 rồi E19.
~~~

Nếu consumer dùng event làm giá trị để overwrite cache:

~~~text
E20 SET cache v20.
E19 SET cache v19.
~~~

Cache bị lùi phiên bản.

Vì vậy:

- Event mang **sourceVersion và operationId**.
- Consumer idempotent theo operationId.
- Các cập nhật tại cache có **compare/version condition** khi dùng event payload để set.
- Với invalidation-only, duplicate DEL thường vô hại nhưng vẫn phải hiểu race stale refill.
- Một high-watermark/version floor sau DELETE ngăn old UPSERT.

Đừng mặc định broker đảm bảo global ordering giữa mọi partitions/consumers.

## 42. TTL và dữ liệu DELETE

Một document bị DELETE ở source:

~~~text
Source:
  doc-42 = DELETED, revision 19.

Cache:
  doc-42 = LIVE, revision 18.
~~~

Nếu cache chỉ có TTL, người dùng vẫn có thể đọc bản live cho đến khi TTL hết. Sau khi DEL, một old reader có thể nạp lại revision 18 nếu không có guard.

Đối với DELETE:

- Tạo tombstone hoặc retained deletion metadata ở nguồn khi cần đồng bộ.
- Gửi invalidation với revision.
- Projection/consumer phải bỏ old events.
- Cache key cũ không được xem là CREATE hợp lệ.
- Bảo vệ quyền truy cập tại nguồn chính sách.
- Có purge process cho bản sao/backup theo policy.

**Cache TTL không phải dữ liệu xóa/tombstone protocol**, nhất là khi client offline hoặc CDC có replay.

## 43. TTL trong NoSQL nguồn khác TTL ở cache

Một số NoSQL có cơ chế TTL cho dữ liệu lưu:

| Nơi | Ý nghĩa thường gặp | Điều cần phân biệt |
|---|---|---|
| **Redis cache** | Entry hết hạn truy cập theo TTL command | Expiration khác eviction và data erasure |
| **MongoDB TTL index** | Dọn documents đủ điều kiện theo thời gian thông qua background TTL process | Xóa có thể trễ; không phải timer tức thời |
| **DynamoDB TTL** | Dịch vụ xóa expired items bất đồng bộ | Không bảo đảm xóa đúng thời điểm expiresAt |
| **Cassandra TTL** | Cells/rows hết hạn logic, dùng tombstone/compaction | Chi phí tombstones, repair/GC semantics |
| **Application soft TTL** | Mốc logic để trigger refresh | Cache bytes có thể còn để SWR |

Không lấy **DynamoDB TTL 60 giây** thay cho **quy tắc không cho đọc data sau đúng 60 giây** nếu dịch vụ không bảo đảm xóa tức thời. Nếu nghiệp vụ yêu cầu cutoff chính xác, ứng dụng phải kiểm trường expiry tại đường đọc/ghi phù hợp.

**Database TTL có thể là lifecycle/retention; cache TTL là freshness/load policy.** Chúng không nên bị coi là một cơ chế duy nhất.

## 44. Redis eviction và policy “không đủ bộ nhớ”

Nếu Redis sử dụng gần hết memory, entry có thể bị loại trước TTL hoặc write bị từ chối tùy **maxmemory policy**.

Các failure modes:

~~~text
High eviction rate
  -> hit ratio giảm
  -> source load tăng
  -> latency spike
~~~

~~~text
Redis OOM / rejects writes
  -> cache fill fail
  -> app phải fallback hoặc degrade
~~~

Cần:

- Dung lượng memory đủ cho working set và overhead.
- TTL/eviction theo workload.
- Throttling khi source chịu không nổi.
- Observability cho cache memory/evictions.
- Không phụ thuộc Redis cache như nơi duy nhất giữ một business write chưa commit.

Tối ưu cache cần **đồng thời** đo hit ratio, eviction, freshness và load của source.

## 45. Multi-region cache và phân vùng mạng

Một service có:

~~~text
Region A: MongoDB primary/source owner
Region A: Redis-A
Region B: Redis-B
~~~

Source commit v20 ở A nhưng invalidation tới B bị chậm do WAN.

Phải biết:

- Có mỗi region một local cache không?
- Invalidation events đi theo đường nào và có durable replay không?
- Region B có thể đọc nguồn authoritative khi WAN đứt không?
- Có được phép serve stale khi không xác minh được quyền không?
- RTO/RPO và policy khi một region bị cô lập là gì?

Không hứa “trong 2 giây tất cả vùng đều mới” nếu hệ có thể mất kết nối 10 phút và vẫn nhận reads ở mỗi vùng; cần chỉ ra trade-off availability/freshness và điều kiện degrade.

Tối ưu latency cross-region bằng cache phải đi kèm **consistency contract theo vùng**.

## 46. Read-your-writes cho người vừa cập nhật

Sau khi user đổi tên sản phẩm:

~~~text
POST /products/p-101 -> update v20 success.
GET /products/p-101 -> Redis vẫn v19.
~~~

Đây là trải nghiệm khó chịu dù hệ eventual có thể được coi là đúng trong hợp đồng chung.

Hướng xử lý:

- Trả resource/version mới trong response write và cập nhật UI từ response.
- Với request cùng session, **bypass cache** cho đến khi cache đạt minimum sourceVersion.
- Gắn requiredVersion/consistency token ở request đọc.
- Invalidate cache và chờ ACK trong giới hạn nếu product contract yêu cầu.
- Đọc authoritative source trong giai đoạn vừa ghi.

Ví dụ:

~~~text
GET product with requiredVersion=20.
Cached version 19 < 20 -> không được phục vụ cache.
~~~

**Read-your-writes là một consistency guarantee có chi phí**, không tự có chỉ vì TTL nhỏ.

## 47. Pseudocode Java: một entry mang version và soft/hard TTL

Một mô hình Java minh họa:

~~~java
public record CachedProduct(
    Product product,
    long sourceVersion,
    long freshUntilEpochMs,
    long serveStaleUntilEpochMs
) {}

public enum CacheDecision {
    SERVE_FRESH,
    SERVE_STALE_AND_REFRESH,
    REQUIRE_SOURCE
}

public CacheDecision decide(CachedProduct entry, long nowEpochMs) {
    if (entry == null) return CacheDecision.REQUIRE_SOURCE;
    if (nowEpochMs < entry.freshUntilEpochMs()) {
        return CacheDecision.SERVE_FRESH;
    }
    if (nowEpochMs < entry.serveStaleUntilEpochMs()) {
        return CacheDecision.SERVE_STALE_AND_REFRESH;
    }
    return CacheDecision.REQUIRE_SOURCE;
}
~~~

Đây chỉ là **logic quyết định freshness theo thời gian**. Production code còn cần:

- Kiểm authorization trước khi serve.
- Minimum required source version cho read-your-writes.
- Refresh singleflight/timeout.
- Kiểm version trước khi ghi lại cache.
- Phân biệt source NOT_FOUND, transient error và business DELETE.
- Time source và clock skew.

Không gán CacheDecision.SERVE_FRESH chỉ vì timestamp còn hạn nếu business contract yêu cầu nhận bản cập nhật mới tức thời.

## 48. Pseudocode Java: cache-aside có fallback

~~~java
public ProductView getProduct(
        String tenantId,
        String productId,
        Long requiredMinVersion) {

    String key = cacheKey(tenantId, productId);
    CachedProduct cached = cache.getSafely(key);

    if (cached != null
            && isFreshForEndpoint(cached)
            && isVersionAllowed(cached, requiredMinVersion)
            && isAuthorizedForCurrentRequest(tenantId, productId)) {
        metrics.cacheHit();
        return toView(cached.product());
    }

    metrics.cacheMiss();
    Product authoritative = source.loadProduct(tenantId, productId);

    if (authoritative == null) {
        negativeCacheIfAllowed(tenantId, productId);
        throw new ProductNotFoundException();
    }

    // Quan trọng: không dùng cache.set mù khi có writer đồng thời.
    cacheWriteUsingVersionGuard(key, authoritative);
    return toView(authoritative);
}
~~~

Đây là **pseudocode kiến trúc**, chưa phải code triển khai đầy đủ. Đặc biệt, hàm cacheWriteUsingVersionGuard phải sử dụng atomic primitive hoặc protocol thực của cache/source; không được chỉ đọc version, kiểm ở Java rồi SET không điều kiện.

Nếu source timeout, đường catch phải thực thi **stale-if-error policy theo loại dữ liệu**, không tự giả định mọi cached value đều đủ an toàn để trả.

## 49. Ví dụ Redis Lua: ghi cache có kiểm tra version đang lưu

Một Lua script có thể giúp so version và đặt entry **nguyên tử trong Redis** khi metadata version cùng nằm tại key được kiểm:

~~~lua
-- KEYS[1] = cache hash chứa version/payload
-- ARGV[1] = incomingVersion (integer string hợp lệ)
-- ARGV[2] = encodedPayload
-- ARGV[3] = ttlSeconds (số nguyên dương)

local current = redis.call("HGET", KEYS[1], "version")
local incoming = tonumber(ARGV[1])
local ttl = tonumber(ARGV[3])

if incoming == nil or ttl == nil or ttl <= 0 then
  return redis.error_reply("INVALID_ARGUMENT")
end

if current and tonumber(current) > incoming then
  return 0
end

redis.call("HSET", KEYS[1],
  "version", ARGV[1],
  "payload", ARGV[2])
redis.call("EXPIRE", KEYS[1], ttl)
return 1
~~~

Giới hạn cần hiểu:

- Script là **minh họa atomic compare/write trong một instance/slot**, không phải toàn bộ cache consistency protocol.
- Script cho phép token bằng version hiện tại; nếu hai payload khác nhau cùng version, phải bổ sung conflict rule/fingerprint.
- Lua number có giới hạn biểu diễn chính xác đối với integer rất lớn; version production cần định dạng/so sánh được hỗ trợ an toàn.
- Nếu key hết TTL hoặc bị DEL, cả version cao nhất đang lưu cũng mất; writer cũ có thể ghi lại version thấp. Cần **version floor/authoritative version hoặc key generation protocol** ở nơi không bị mất cùng entry.
- Invalidation events và nguồn cấp version vẫn phải đáng tin.
- Redis replication/failover có durability contract riêng; script không tạo transaction với MongoDB.

**Không được đọc script trên và kết luận “đã giải quyết mọi stale refill race”.** Nó chỉ bảo vệ một phần cục bộ khi metadata hiện có.

## 50. Cấu hình Redis TTL phải đi với lỗi timeout

Giả sử cache.set thất bại nhưng source.read thành công:

~~~text
GET product -> Redis miss.
MongoDB read v20 -> success.
Redis SET v20 -> timeout.
~~~

Với cache thuần phục vụ tăng tốc, API thường có thể trả **v20** cho người dùng và ghi nhận cache fill failure.

Ngược lại:

~~~text
MongoDB read -> timeout.
Redis contains stale v18.
~~~

Lúc này quyết định phụ thuộc **stale-if-error contract**, không phải việc Redis vẫn có dữ liệu.

Các lỗi cache không nên tự làm nguồn business write rollback nếu cache chỉ là projection; hãy tách critical path khỏi optional caching và bổ sung observability.

## 51. Tiền xử lý cache và version từ nguồn

Một hệ có thể cache data theo:

~~~json
{
  "value": "...",
  "sourceVersion": 20,
  "loadedAt": "2026-11-14T10:00:00Z",
  "freshUntil": "2026-11-14T10:00:20Z",
  "serveStaleUntil": "2026-11-14T10:01:00Z",
  "schemaVersion": 3
}
~~~

Các field khác nhau có chức năng khác nhau:

- **sourceVersion:** so thứ tự các thay đổi có thẩm quyền.
- **loadedAt:** phục vụ quan sát và policy tuổi entry.
- **freshUntil:** mốc serve fresh.
- **serveStaleUntil:** mốc chặn stale theo policy.
- **schemaVersion:** đảm bảo code mới không deserialize payload cũ sai.

Không dùng loadedAt mới để **nâng sourceVersion** nếu nội dung vẫn đến từ bản ghi cũ; làm vậy chỉ khiến cache **trông mới hơn** chứ không đúng hơn.

## 52. Chuyển schema cache không nên làm dữ liệu lỗi thời sống lại

Khi API deploy version mới, payload cache có thể không còn tương thích.

Một cách:

~~~text
product-cache:v3:shop-a:p-101
~~~

Code v3 chỉ đọc schema v3, không tự diễn dịch nhầm dữ liệu v2.

Nhưng:

- Schema version khác **business source version**.
- Bump schema namespace làm tăng misses/cold start.
- Có thể cần warm-up và rate limit.
- Dữ liệu v2 vẫn cần TTL/cleanup.
- Nếu có source version 20, không được để schema v3 ghi lại dữ liệu business v18 và nghĩ nó mới.

Tách **schemaVersion**, **generation** và **sourceVersion** tránh nhiều bug subtle khi rollout.

## 53. Cache invalidation sau deploy và feature flag

Một tính năng bật:

~~~text
Feature flag: showDiscountedPrice = true.
~~~

Nếu cache key không chứa feature context mà payload thay đổi theo flag, người dùng có thể thấy response trộn hai phiên bản.

Giải pháp:

- Đưa feature/schema generation vào key khi nó thực sự ảnh hưởng kết quả.
- Có invalidation theo feature rollout.
- Không đưa mọi ephemeral flag vào key nếu gây cardinality quá lớn.
- Canary cần quan sát cache hit/miss và correctness.
- Rollback có thể cần chuyển namespace hoặc purge.

**Một thay đổi về logic tạo response cũng có thể là lý do invalidate cache**, ngay cả khi database source không đổi.

## 54. Chi phí TTL ngắn đối với source

Giả sử hot key được đọc 10.000 lần/phút nhưng TTL là 1 giây. Nếu singleflight hoạt động tốt, có thể chỉ khoảng 60 source loads/phút trong mô hình đơn giản, thay vì 10.000. Tuy nhiên, nếu có 100 API instances mỗi instance tự giữ L1 và không phối hợp:

~~~text
100 instances × ~60 refresh/phút
  -> có thể tới ~6.000 loads/phút
~~~

Đây là ví dụ xấp xỉ, phụ thuộc pattern requests, cache hierarchy, latency và TTL placement. Nó minh họa:

- Short TTL không nhất thiết gây source QPS bằng request QPS.
- Coalescing và shared cache topology thay đổi tải rất mạnh.
- Local caches làm freshness khó đồng nhất.
- Cache hit ratio và source protection cần đo ở peak.

Không chọn TTL bằng cách tối thiểu hóa số source queries nếu nghiệp vụ cần freshness chặt.

## 55. Observability: không chỉ cache hit ratio

| Metric | Ý nghĩa |
|---|---|
| **cache_hit_ratio** | Tỷ lệ requests đọc trúng cache |
| **cache_miss_rate** | Tải có thể chuyển về source |
| **cache_evictions** | Entry bị đẩy ra do memory policy |
| **cache_expirations** | Entry hết TTL |
| **cache_key_age** | Thời gian từ lần cache fill |
| **commit_to_visible_lag** | Độ trễ thật từ source commit đến reader thấy version mới |
| **stale_response_count** | Số lần phục vụ dữ liệu được biết là stale |
| **stale_response_age** | Độ trễ stale khi quan sát được |
| **invalidation_lag** | Thời gian từ source change tới cache invalidation |
| **invalidation_failures** | DEL/event/consumer lỗi |
| **stale_fill_rejected** | Số cache writes cũ bị chặn theo version |
| **negative_cache_hit** | Tỷ lệ kết quả NOT_FOUND được cache |
| **refresh_inflight/timeout** | Refresh backlog/treo |
| **singleflight_waiters** | Độ tập trung tải vào cùng key |
| **source_reads_caused_by_cache** | Tải source do miss/refresh |
| **fallback_to_source_rate** | Cache unavailable/degraded |
| **L1_L2_version_mismatch** | Tầng cache không hội tụ |

Không tạo metric label cho từng productId/orderId nếu cardinality lớn. Có thể dùng audit/trace với sampling và quyền truy cập phù hợp.

Một dashboard tốt phải cùng lúc hiển thị **latency, cache hit ratio, freshness, source load và sự cố invalidation**.

## 56. Freshness có thể đo bằng watermark/version

Nếu source và cache mang version:

~~~text
Source product p-101: version 20.
Cache product p-101: version 18.
~~~

Có thể phát hiện cache đang thiếu hai revisions. Nhưng:

- Khoảng cách 2 versions **không tương đương 2 giây stale**.
- Một product có thể ít update, product khác update liên tục.
- Nên gắn commit timestamp hoặc event processing timestamp từ nguồn khi cần đo time lag.
- Một sample bằng cách đọc nguồn cho mỗi request có thể làm mất lợi ích cache.

Các cách đo:

- Event-driven telemetry từ source tới cache consumers.
- Sampling một tỷ lệ keys để đối chiếu source.
- Synthetic write-then-read probes.
- Watermark tại CDC pipeline.

**Chọn phép đo đại diện cho end-user visibility**, không chỉ xem relay đã đọc xong event.

## 57. Error budget cho freshness

Một hệ có SLO:

~~~text
99,9% price changes visible within 5 seconds / rolling 30 days.
~~~

Điều đó có nghĩa một tỷ lệ nhỏ changes có thể vượt ngưỡng theo quy tắc SLO, không có nghĩa có thể bỏ qua mọi yêu cầu xóa dữ liệu nhạy.

Cần:

- Đếm events/visibility windows đúng mẫu số.
- Phân biệt source outage, CDC backlog, local cache lag, CDN lag.
- Đặt alert khi freshness budget burn quá nhanh.
- Có hành động: pause rollout, tăng consumer capacity, tạm bypass cache.
- Xác định critical endpoints không được chấp nhận stale dù SLO chung còn budget.

**Freshness SLO là công cụ vận hành; security/business invariants là ràng buộc riêng.**

## 58. Runbook khi cache trả dữ liệu cũ

Một quy trình điều tra:

1. **Xác định scope:** key, tenant, endpoint, cache tiers và người dùng bị ảnh hưởng.
2. **So source version và cached version**, ghi lại thời điểm commit/invalidation.
3. **Kiểm tra TTL:** absolute hay sliding, soft/hard, có retry gia hạn bản cũ không?
4. **Kiểm pipeline:** outbox, broker, consumer, dead-letter, lag và quyền truy cập.
5. **Tìm race:** stale refill sau DEL, out-of-order events, old schema, local L1 còn v18.
6. **Kiểm nguồn lỗi:** source read có lấy stale replica không, version đã rollback vì restore không?
7. **Đánh giá tác động:** UX hay đã ảnh hưởng pricing/authorization/payment?
8. **Mitigate:** tạm bypass cache, purge đúng namespace, hạn chế stale-if-error.
9. **Reconcile:** nạp lại từ authoritative source, kiểm version/deletion.
10. **Khắc phục dài hạn:** version guard, CDC reliability, TTL/refresh logic, fault test.

Không nên flush toàn bộ Redis theo phản xạ nếu hệ không chịu được source stampede sau đó; cần giới hạn blast radius và có kế hoạch warm-up.

## 59. Kiểm thử những lịch lỗi quan trọng

| Kịch bản | Lỗi có thể xảy ra | Kết quả kỳ vọng |
|---|---|---|
| Update source ngay sau cache fill | TTL giữ bản cũ | Stale trong budget hoặc invalidate |
| Reader đọc v18, writer commit v19 + DEL, reader SET v18 | Stale refill | Guard/floor chặn hoặc có bound được công bố |
| UPDATE v20 event đến trước v19 | Cache lùi version | Bỏ event cũ |
| DELETE v21 rồi UPDATE v20 | Resurrection | Không tạo lại bản cũ |
| Source commit nhưng app crash trước DEL | Cache không invalidate | Outbox/recovery/TTL bound |
| Redis down | Read latency/source spike | Bounded fallback, load shedding |
| Hot keys hết TTL cùng lúc | Stampede | Jitter/singleflight |
| Refresh worker GC pause | Lock owner hết hạn | Version-aware publish |
| Source timeout | Serve stale không kiểm tra | Chỉ serve nếu stale-if-error policy cho phép |
| Negative cache còn sau CREATE | 404 sai | CREATE invalidation/short TTL |
| L1 cache chưa nhận invalidation | Instance trả v18 | L1 TTL/epoch/broadcast |
| Browser/CDN giữ response | Redis mới nhưng client cũ | HTTP cache policy/purge |
| User bị revoke quyền | Cache ALLOW cũ | Deny theo authoritative policy |
| Cache entry v18 bị eviction | Tải nguồn tăng | Dự phòng headroom/fallback |
| Restore từ backup cũ | Metadata fence lùi | Recovery/reconciliation |
| Rolling deploy đổi schema | Deserialize sai/old data | Schema namespace/compatibility |

Fault injection nên chạy ở môi trường được phép, đo cả response lẫn business invariants, không chỉ đếm số lỗi Redis.

## 60. Một ví dụ thiết kế hoàn chỉnh cho product catalog

Yêu cầu giả định:

~~~text
Product details:
  p99 < 100 ms.

Price freshness:
  visibility lag p99 <= 5s theo SLO đã định.

Inventory:
  UI có thể eventual.
  Reserve stock phải kiểm authoritative source.

Permission:
  Không phục vụ dữ liệu nếu quyền hiện hành bị revoke.
~~~

Thiết kế:

~~~mermaid
flowchart TD
    U["Product API"] --> L1{"L1 short TTL"}
    L1 -->|"Miss/stale"| L2{"Redis L2"}
    L2 -->|"Miss/stale"| DB["MongoDB authoritative"]
    DB --> O["Outbox/CDC versioned events"]
    O --> I["Invalidation consumers"]
    I --> L2
    I --> L1
    U --> R["Reservation API: conditional source write"]
    R --> DB
~~~

Quy tắc:

1. L1 TTL rất ngắn hoặc bỏ L1 với dữ liệu cần freshness chặt.
2. Redis L2 lưu **price, version, loadedAt, freshness metadata**.
3. Update giá commit tại MongoDB kèm event có source version.
4. Consumer invalidates/bump generation và chặn old updates.
5. Miss/read fill có version-aware policy chống stale refill.
6. API có read-your-writes token khi một user vừa sửa giá.
7. Reserve inventory không ra quyết định từ cache value.
8. Negative cache có TTL ngắn và CREATE invalidation.
9. Có synthetic probes đo **commit-to-visible**, không chỉ cache hit.
10. Có rollback tắt L1/Redis đường đọc theo rate limit nếu inconsistency.

Thiết kế này vẫn phải được chứng minh bằng benchmark/fault tests; sơ đồ không phải bằng chứng guarantee.

## 61. Quy trình lựa chọn policy cho một cache mới

~~~mermaid
flowchart TD
    A["Chọn dữ liệu và endpoint"] --> B{"Sai/stale có gây vi phạm invariant?"}
    B -->|"Có"| C["Source validation / strong guard"]
    B -->|"Không"| D["Định nghĩa staleness SLO"]
    C --> E["Chọn cache pattern và key scope"]
    D --> E
    E --> F["Chọn absolute/soft/hard TTL"]
    F --> G["Chọn invalidation/event/version"]
    G --> H["Chống stale refill, stampede, ordering"]
    H --> I["L1/L2/CDN/region propagation"]
    I --> J["Metrics, fault tests, fallback"]
    J --> K["Review TTL theo workload thật"]
~~~

Thực hiện:

1. Phân loại data: immutable, ít đổi, thường đổi, critical, sensitive.
2. Xác định source of truth và quyền truy cập.
3. Đặt consistency/freshness contract.
4. Chọn cache-aside/read-through/write-through hoặc pattern khác.
5. Chọn TTL, soft/hard boundary và stale-if-error riêng.
6. Xác định key, tenant/permission/schema scope.
7. Xây invalidation sau source commit hoặc qua outbox/CDC.
8. Giải quyết stale refill và out-of-order events.
9. Chống stampede, negative caching và memory pressure.
10. Kiểm các tầng L1/L2/CDN/browser.
11. Đo hit ratio, p99 latency, freshness lag, load và cost.
12. Fault test, lập runbook, review định kỳ.

## 62. Những nhầm lẫn phổ biến

| Nhầm lẫn | Vì sao sai | Cách hiểu đúng |
|---|---|---|
| “TTL 5 phút nghĩa dữ liệu cũ tối đa 5 phút trong mọi trường hợp” | Có SWR, sliding TTL, stale fill, nhiều layers | Guarantee theo toàn bộ đường đọc |
| “Cache age thấp thì dữ liệu mới” | Source có thể đổi ngay sau fill | Đo source version/visibility |
| “Cache hit đồng nghĩa dữ liệu đúng” | Entry có thể stale hoặc thiếu quyền | Freshness/authorization guard |
| “Cache miss là data không tồn tại” | Cache có thể eviction/expired | Đọc authoritative source |
| “Sliding TTL luôn tiết kiệm chi phí” | Hot key giữ dữ liệu cũ mãi | Có max-age/invalidation |
| “DEL cache sau DB commit loại mọi race” | Reader cũ có thể SET sau DEL | Version-aware fill/floor |
| “Double delete đảm bảo không stale” | GC pause/retry có thể dài hơn delay | Chỉ là mitigation |
| “Một Redis Lua script bảo đảm strong consistency xuyên DB” | Không transaction với source | Hiểu atomicity scope |
| “Có version trong payload là đủ” | Không kiểm atomically, floor có thể mất | Atomic compare và durable generation |
| “Versioned key tự luôn mới” | Reader có thể dùng currentVersion stale | Authority của version pointer |
| “SWR luôn tốt cho UX” | Có thể trả data không được phép cũ | Per-endpoint policy |
| “Source outage thì serve stale bao lâu cũng được” | Vi phạm hard freshness/security | Stale-if-error bounded |
| “Negative cache chỉ giúp giảm 404” | Có thể che object mới CREATE | TTL ngắn + invalidation |
| “TTL hết nghĩa Redis đã giải phóng mọi byte” | Active/lazy expiry khác physical reclaim | Monitor memory riêng |
| “Redis eviction nghĩa TTL hết” | Memory pressure có thể đẩy key sớm | Phân biệt eviction/expiration |
| “L1 tự cập nhật khi L2 bị DEL” | JVM cache riêng vẫn có bản cũ | Broadcast/TTL/epoch |
| “Chỉ cần xóa Redis là browser mới” | CDN/HTTP cache cũng giữ response | Kiểm tất cả tiers |
| “Cache quyền truy cập 10 phút là an toàn” | Revoke cần có hiệu lực ngay theo policy | Authz ở nguồn tin cậy |
| “Giá hiển thị có thể stale nên checkout cũng vậy” | Hai bước có business semantics khác | Price quote/authoritative decision |
| “Atomic INCR cache giải quyết duplicate events” | Duplicate event có thể increment hai lần | Idempotency/ledger |
| “Broker luôn giao event theo version” | Cross partitions/retries out-of-order | Version guard |
| “MongoDB/DynamoDB TTL như Redis key expiry” | Cơ chế dọn async và phạm vi khác nhau | Phân biệt source lifecycle/cache |
| “Không có stale errors nghĩa invalidation đã đúng” | Có thể không đo freshness | Synthetic probes và reconciliation |
| “Hit ratio càng cao càng tốt” | Có thể giữ stale lâu | Tối ưu latency, load, freshness |
| “Flush cache toàn bộ chữa mọi sự cố” | Có thể gây source stampede | Targeted purge + warm-up |

## 63. Bài tập thực hành

### Bài tập 1 — Phân biệt age và staleness

Cache fill lúc 10:00:00 với TTL 300 giây; source đổi lúc 10:00:01; user đọc lúc 10:00:05. Hãy tính cache age, thời gian data đã stale và TTL còn lại. Vì sao chỉ nhìn age không đủ?

### Bài tập 2 — Absolute và sliding TTL

Một hot key được đọc cứ 20 giây, sliding TTL 60 giây. Nếu không có invalidation, entry có thể tồn tại bao lâu? Đề xuất absolute max-age riêng.

### Bài tập 3 — Soft/hard TTL

Thiết kế entry với freshUntil=30s và serveStaleUntil=90s. Mô tả hành vi ở t=20, 50 và 100 giây, gồm refresh, stale-if-error và source timeout.

### Bài tập 4 — Redis CLI

Viết các lệnh Redis SET có TTL 45 giây, GET, TTL/PTTL, EXPIRE và DEL cho key product:shop-a:p-101. Giải thích Redis expiration khác eviction.

### Bài tập 5 — Sliding TTL nguy hiểm

Một ứng dụng GETEX liên tục gia hạn cache permission. User bị revoke nhưng cached ALLOW sống lâu. Hãy mô tả thiết kế quyền an toàn hơn.

### Bài tập 6 — Cache-aside

Vẽ đường đọc hit/miss và đường cập nhật source. Nêu những lỗi có thể xảy ra nếu cache set/invalidate thất bại.

### Bài tập 7 — Stale refill race

Dựng lịch Reader R đọc v18, Writer W commit v19 + DEL, rồi R SET v18. Vì sao DEL sau commit không đủ? Đề xuất version guard hoặc versioned key.

### Bài tập 8 — Version floor bị mất

Cache đã nhận rev20, nhưng DEL xóa cả payload và version metadata. Reader cũ SET rev19. Hãy giải thích vấn đề và cách giữ generation/floor ngoài entry dễ mất.

### Bài tập 9 — Double delete

Một nhóm DEL ngay sau commit, đợi 500 ms rồi DEL lần hai. Hãy tạo lịch GC pause 3 giây khiến vẫn stale và đánh giá giới hạn của heuristic.

### Bài tập 10 — Outbox invalidation

MongoDB commit giá mới nhưng application crash trước Redis DEL. Thiết kế transactional outbox/CDC và retry consumer, nêu nơi cần operationId/revision.

### Bài tập 11 — Event đảo thứ tự

Consumer nhận ProductUpdated v20 trước v19. Viết condition ngăn v19 ghi đè v20. Với DELETE v21, làm sao không hồi sinh v20?

### Bài tập 12 — Cache stampede

10.000 requests cùng miss một hot key. Thiết kế singleflight, bounded wait, distributed coordination khi cần, TTL jitter và source load shedding.

### Bài tập 13 — TTL jitter

Base TTL 300 giây, random multiplier từ 0,8 tới 1,0. Tính khoảng TTL có thể tạo. Vì sao random multiplier lên tới 1,2 có thể vi phạm freshness budget?

### Bài tập 14 — Negative caching

Key p-999 được cache NOT_FOUND trong 60 giây, 5 giây sau sản phẩm được CREATE. Thiết kế invalidation và TTL để hạn chế 404 sai.

### Bài tập 15 — Inventory

Cache hiển thị còn 5 sản phẩm nhưng source đã hết. Vì sao thao tác ReserveStock phải dùng conditional write thay vì decrement từ cache?

### Bài tập 16 — Pricing

Giá hiển thị cho phép stale 15 giây, giá checkout phải đúng theo quote authoritative. Thiết kế đường đọc và contract khi giá vừa thay đổi.

### Bài tập 17 — Cache permission

User bị thu hồi quyền trong lúc các API instances còn cached ALLOW. Thiết kế authorization policy và cách xử lý CDN/browser caches để không tiếp tục rò nội dung.

### Bài tập 18 — L1/L2

Redis L2 đã bị invalidate nhưng JVM L1 giữ v18. Đề xuất cơ chế invalidation, TTL và measurement cho từng tầng.

### Bài tập 19 — Query cache dependency

Query list category=shoes sort=price có 20 cached pages. Product đổi giá và category. Hãy thiết kế tag invalidation hoặc namespace generation, xác định keys bị ảnh hưởng.

### Bài tập 20 — Multi-region

Source ở region A commit rev20, WAN tới region B gián đoạn 10 phút. B vẫn serve cache rev19. Hãy mô tả những guarantee không thể hứa nếu vẫn muốn availability và cách degrade an toàn.

### Bài tập 21 — Read-your-writes

User cập nhật product rev20 và GET ngay, cache còn rev19. Hãy thiết kế requiredMinVersion hoặc bypass-cache flow để trả dữ liệu không thấp hơn rev20.

### Bài tập 22 — Source TTL khác cache TTL

So sánh một item DynamoDB có TTL expiresAt với cache entry Redis EX 60 và MongoDB TTL index. Tại sao không thể dùng thời điểm xóa vật lý để hứa “không đọc được sau đúng 60 giây”?

### Bài tập 23 — Java pseudocode

Triển khai cache-aside có cached sourceVersion, freshUntil, serveStaleUntil và conditional fill. Chỉ ra đường nào phải kiểm auth, version và stale-if-error.

### Bài tập 24 — Redis Lua

Đánh giá script compare version/HSET/EXPIRE trong bài. Nó bảo vệ được race nào, không bảo vệ được race nào nếu key đã bị xóa và source nằm ở MongoDB?

### Bài tập 25 — Capacity và hit ratio

Một hệ có 100.000 GET/phút, 90% hits. Tính source reads/phút trong mô hình lý tưởng. Nếu Redis mất và tất cả requests miss, cần rate limiting/bulkhead/fallback ra sao?

### Bài tập 26 — Freshness SLO

Product team đặt SLO “99,9% price updates hiển thị dưới 5 giây”. Định nghĩa t_commit/t_visible, mẫu số, dashboard, synthetic probes và alert khi vượt budget.

### Bài tập 27 — Debug stale dữ liệu

User thấy giá v18 sau khi source đã commit v20. Viết runbook kiểm tra Redis TTL, local caches, browser/CDN, CDC lag, source read consistency, stale refill và event ordering.

### Bài tập 28 — Rollout policy

Một team muốn chuyển TTL từ 60 lên 600 giây để tăng hit ratio. Hãy đề xuất canary, đo freshness/latency/source load và rollback criteria trước khi chấp thuận.

### Bài tập 29 — Sửa cache schema

Ứng dụng chuyển cached payload schema v2 sang v3 nhưng business sourceVersion không đổi. Thiết kế cache key/versioning, warm-up và chống cache stampede khi deploy.

### Bài tập 30 — Thiết kế hoàn chỉnh

Một hệ có MongoDB source, Redis L2, JVM L1, CDN, mobile offline clients; dữ liệu gồm product catalog, giá, inventory và permissions. Hãy xây:

1. Bảng phân loại freshness và TTL theo loại dữ liệu.
2. Absolute/soft/hard TTL, stale-while-revalidate và stale-if-error policies.
3. Cache key scope theo tenant/currency/permission/schema.
4. CDC/outbox, operationId, event version, delete semantics.
5. Chống stale refill sau DEL và out-of-order updates.
6. Stampede prevention, jitter, negative caching.
7. L1/L2/CDN invalidation và client offline handling.
8. Authoritative price/inventory/authorization decisions.
9. Metrics commit-to-visible, hit ratio, source protection.
10. Fault injection, runbook, canary và rollback.

Không được chỉ nói **“đặt TTL 60 giây rồi xóa cache khi cập nhật”**. Cần chứng minh giới hạn stale theo từng endpoint, xác định khi nào có thể phục vụ bản cũ và bảo vệ những thao tác mà dữ liệu cũ sẽ làm sai nghiệp vụ.

---

**Kết luận:** Thiết kế bộ nhớ đệm NoSQL không chỉ là chọn **TTL** để tăng hit ratio. TTL xác định một phần vòng đời entry; **staleness budget** xác định thời gian dữ liệu cũ được phép hiển thị; còn **invalidation** giúp cache theo kịp các thay đổi tại nguồn. Ba yếu tố phải được đặt trong **business contract**, đặc biệt đối với giá, tồn kho, DELETE và quyền truy cập. Cache-aside, read-through, write-through và write-behind có failure modes khác nhau; thứ tự **source commit → invalidate** quan trọng nhưng chưa đủ vì **stale refill** có thể xảy ra sau DEL. Versioned keys, high-watermarks, atomic guards, CDC/outbox và idempotent consumers giúp kiểm soát một phần các race; SWR, jitter, singleflight và negative caching giúp cân bằng latency với tải nguồn. Một thiết kế đáng tin phải xét **mọi tầng cache, giới hạn phục vụ stale, khả năng fallback, security, freshness metrics và fault tests**, rồi chọn TTL dựa trên dữ liệu đo được thay vì dùng một con số chung cho mọi dữ liệu.
