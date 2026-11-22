# Thời hạn lưu, vô hiệu hóa và mức chấp nhận dữ liệu cũ trong microservices

## 1. Vì sao quản lý độ mới của cache là bài toán kiến trúc?

Trong hệ thống microservices, cache giúp giảm thời gian phản hồi và tải lên cơ sở dữ liệu hoặc dịch vụ phụ thuộc. Tuy nhiên, một bản sao dữ liệu được giữ trong bộ nhớ của từng instance, Redis, CDN hoặc gateway có thể **khác trạng thái nguồn sự thật (source of truth)** ngay sau khi dữ liệu thay đổi.

Giả sử catalog-service hiển thị giá sản phẩm từ cache. Bộ phận kinh doanh sửa giá trong database, nhưng ba instance catalog-service và một lớp CDN vẫn giữ giá cũ. Người dùng khác nhau có thể thấy giá khác nhau; một request thanh toán nếu dùng trực tiếp giá cũ có thể tạo sai lệch tài chính. Ngược lại, nếu một bài viết hoặc danh sách danh mục hiển thị chậm vài chục giây, trải nghiệm có thể vẫn chấp nhận được và cache mang lại lợi ích lớn.

Câu hỏi đúng không chỉ là **“đặt TTL bao nhiêu?”**, mà gồm:
- Dữ liệu nào được phép cũ, trong bao lâu, với điều kiện nào?
- Ai là nguồn sự thật và sự kiện nào làm bản sao mất hiệu lực?
- Khi write thành công, những reader nào phải thấy dữ liệu mới ngay?
- Nếu event invalidation bị trễ/mất, lớp bảo vệ cuối cùng là gì?
- Cache nhiều tầng có thể kéo dài độ cũ ngoài dự kiến như thế nào?
- Khi Redis hoặc database lỗi, phục vụ bản cũ hay báo lỗi?
- Làm sao chứng minh chính sách freshness qua metric và kiểm thử?

**TTL (Time to Live)** quyết định thời gian một entry được phép lưu hoặc được xem là còn hiệu lực theo chính sách cache. **Invalidation** là việc vô hiệu hóa một bản sao khi dữ liệu gốc thay đổi hoặc không còn đáng tin. **Staleness tolerance** là giới hạn độ cũ mà nghiệp vụ chấp nhận đối với giá trị trả về.

Ba cơ chế bổ trợ nhau: TTL giới hạn vòng đời; invalidation giảm thời gian bất nhất sau write; chính sách chấp nhận dữ liệu cũ quyết định khi nào được phục vụ một bản stale, khi nào phải fetch mới hoặc từ chối request.

## 2. Mục tiêu học tập

Sau bài này, người học có thể:
1. Phân biệt TTL, expiration, eviction, invalidation, freshness và tuổi dữ liệu.
2. Thiết kế cache-aside, write-through, write-behind và invalidation theo sự kiện trong microservices.
3. Định nghĩa soft TTL, hard TTL, stale-while-revalidate và stale-if-error theo yêu cầu nghiệp vụ.
4. Giải thích race condition khiến entry cũ xuất hiện lại sau khi đã xóa.
5. Thiết kế key/version, outbox, retry và bảo vệ trước sự kiện đến sai thứ tự.
6. Đo hit ratio, stale age, invalidation lag, cache stampede và ảnh hưởng database.
7. Xây dựng phương án khi cache nhiều tầng, nguồn dữ liệu lỗi hoặc có dữ liệu nhạy cảm.
8. Kiểm thử và triển khai chính sách cache có thể quan sát, có cơ chế điều chỉnh an toàn.

## 3. Từ nguồn sự thật đến các bản sao

Ví dụ kiến trúc có nhiều lớp cache:

~~~text
Client / Browser cache
        │
        ▼
CDN / API Gateway cache
        │
        ▼
catalog-service
   ├── Local in-process cache (L1, mỗi instance)
   ├── Redis / distributed cache (L2)
   └── Catalog database (source of truth)

Các dịch vụ khác có thể subscribe ProductUpdated event
và giữ thêm read model hoặc cache riêng.
~~~

Mỗi tầng có chính sách TTL, cách invalidation, quota và rủi ro khác nhau:
- **Browser/CDN** gần người dùng, hiệu quả với nội dung có thể dùng chung; cần chính sách HTTP cache và phân quyền phù hợp.
- **In-process cache** có độ trễ thấp nhưng từng instance giữ bản sao riêng; invalidate một instance không đồng nghĩa các instance còn lại đã sạch.
- **Distributed cache** dùng chung giữa nhiều replica nhưng vẫn là bản sao của database; triển khai multi-region có thể có độ trễ replication.
- **Read model/materialized view** thường đồng bộ bất đồng bộ qua event; có thể phục vụ như một dữ liệu dẫn xuất riêng, cần đo độ trễ cập nhật.
- **Database** là nguồn sự thật của aggregate theo ranh giới sở hữu; không nên coi cache là bản ghi chính duy nhất nếu thiết kế không có cam kết lưu bền tương ứng.

Chính sách freshness phải xét **đường đi thực tế của request**. Một entry ở Redis vừa hết hạn nhưng được nạp lại từ local cache còn cũ, hoặc một CDN có TTL dài hơn tầng trong, vẫn có thể phục vụ giá trị cũ.

## 4. Thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| TTL | Khoảng thời gian sống theo quy tắc cache | Thường đặt khi tạo/cập nhật entry; có thể trượt hoặc cố định |
| Expiration | Entry hết thời gian được coi là hợp lệ | Không nhất thiết được xóa khỏi RAM ngay lúc đó |
| Eviction | Loại entry do dung lượng/thuật toán thay thế | Có thể xảy ra trước TTL |
| Invalidation | Chủ động đánh dấu/xóa bản cache không còn đáng tin | Phải tới đúng tầng và đúng key |
| Freshness | Độ mới theo cam kết dữ liệu | Không đồng nhất với thời gian entry nằm trong cache |
| Stale data | Bản sao không phản ánh cập nhật đã có ở nguồn | Có thể phát hiện hoặc chưa thể phát hiện |
| Entry age | Thời gian kể từ lần tạo/fetch bản cache | Không tự chứng minh chưa có cập nhật nguồn |
| Soft TTL | Mốc bắt đầu cần refresh, có thể tạm dùng bản cũ | Thường dùng với stale-while-revalidate |
| Hard TTL | Giới hạn cuối cùng để không phục vụ bản đã quá tuổi | Phải thực thi nhất quán trên các tầng |
| Invalidation lag | Thời gian từ thay đổi nguồn đến lúc bản sao bị vô hiệu | Có thể đo qua event/version |
| Consistency window | Khoảng chênh dữ liệu giữa nguồn và các reader | Phụ thuộc đồng bộ, lỗi, retry và topology |

**Entry age không chính xác bằng “thời gian stale”.** Một entry được nạp 90 giây trước có thể vẫn hoàn toàn mới nếu nguồn chưa thay đổi. Ngược lại, một entry được nạp 1 giây trước có thể đã lỗi thời nếu write khác vừa commit. Muốn biết staleness thật, cần so với source version, thời điểm thay đổi nguồn hoặc dấu mốc event đủ tin cậy.

Với TTL triển khai ở Redis hoặc một thư viện cache, cần phân biệt TTL **cố định sau write** và **trượt theo mỗi lần truy cập** (time-to-idle). Cơ chế trượt có thể giữ một entry nóng rất lâu; nếu không có hard age hoặc invalidation đúng, nó không bảo đảm giới hạn độ cũ theo thời gian thực.

## 5. Các mức nhất quán và độ cũ nghiệp vụ chấp nhận

Không phải mọi API đều cần consistency giống nhau.

**Strong/linearizable read** yêu cầu read quan sát một thứ tự cập nhật phù hợp cam kết mạnh; cache bất đồng bộ không thể tự hứa điều này. **Read-your-writes** yêu cầu người vừa sửa dữ liệu đọc lại được phiên bản của chính mình. **Monotonic reads** yêu cầu một client không nhìn thấy phiên bản cũ hơn sau khi đã nhìn thấy phiên bản mới. **Eventual consistency** cho phép bản sao chênh lệch tạm thời nhưng sẽ hội tụ khi cập nhật và cơ chế retry hoạt động.

Cần viết chính sách bằng điều kiện có thể kiểm chứng:

| Dữ liệu và hành động | Độ cũ gợi ý để thiết kế | Quyết định khi không bảo đảm |
| --- | --- | --- |
| Nội dung giới thiệu, danh mục ít thay đổi | Có thể chấp nhận vài phút hoặc hơn nếu nghiệp vụ đồng ý | Phục vụ stale theo giới hạn; refresh nền |
| Trang danh sách sản phẩm | Có thể chấp nhận giây/phút tùy chiến dịch | TTL ngắn và invalidation theo ProductUpdated |
| Giá hiển thị cho mục đích tham khảo | Độ cũ ngắn, thông báo khi giá cuối khác | Xác minh giá hiện hành khi chốt giao dịch |
| Tồn kho hiển thị | Có thể gần đúng trong thời gian ngắn | Khi đặt hàng phải reserve/kiểm tra tại nguồn sở hữu |
| Quyền truy cập, trạng thái khóa tài khoản | Thường cần độ mới rất cao và thu hồi hiệu lực nhanh | Từ chối hoặc đọc nguồn đáng tin thay vì dùng stale vô thời hạn |
| Hạn mức giao dịch, thanh toán, chống gian lận | Phụ thuộc yêu cầu nhất quán nghiêm ngặt | Không ra quyết định cuối dựa trên cache cũ |
| Dashboard phân tích và gợi ý | Chấp nhận stale theo nhãn “cập nhật lúc ...” | Có thể trì hoãn refresh hoặc phục vụ last-known-good |

Các thời lượng trong bảng là ví dụ định hướng, không phải SLA mặc định. Chủ sở hữu nghiệp vụ phải xác nhận **độ cũ tối đa**, tác động khi vượt ngưỡng và đường xử lý thay thế.

Một yêu cầu rõ ràng hơn “cache được 5 phút” là: **“Với API xem danh mục, trong điều kiện bình thường 99% request thấy bản không quá 60 giây kể từ thay đổi nguồn; khi nguồn lỗi có thể trả bản tối đa 5 phút tuổi và phải gắn trạng thái degraded; checkout luôn xác minh giá/tồn kho tại dịch vụ sở hữu.”** Cách phát biểu này đưa ra mục tiêu đo lường và hành vi khi hệ thống mất khả năng đồng bộ.

## 6. TTL: chọn giá trị theo rủi ro, tải và tần suất cập nhật

TTL càng dài thường giảm cache miss và tải đọc nguồn, nhưng làm tăng thời gian có thể quan sát dữ liệu cũ khi invalidation không chạy. TTL ngắn cải thiện cơ hội làm mới, đổi lại tăng tải và latency do fetch nguồn.

Không có TTL tối ưu chung cho mọi key. Cần cân nhắc:
1. **Tần suất thay đổi:** giá, cấu hình và quyền truy cập thay đổi khác danh mục tĩnh.
2. **Tác động của stale:** sai giá thanh toán nghiêm trọng hơn số lượt xem dashboard chậm cập nhật.
3. **Độ đắt của cache miss:** query DB, fan-out RPC, chi phí third-party API.
4. **Lưu lượng/độ nóng:** key nóng có khả năng stampede khi đồng loạt expire.
5. **SLO:** cache miss có thể đưa p95/p99 vượt mục tiêu không?
6. **Khả năng invalidation:** sự kiện cập nhật có đủ tin cậy, có xử lý khi mất event?
7. **Nhiều tầng và vùng:** TTL thực tế bị ảnh hưởng bởi local, Redis, CDN, replica và region.

### 6.1. Ví dụ định lượng đơn giản

Nếu cập nhật của một key xấp xỉ quá trình Poisson với tốc độ trung bình lambda lần/giây, xác suất có ít nhất một cập nhật trong khoảng t là:

**P(có thay đổi trong t) = 1 − exp(−lambda × t).**

Ví dụ một cấu hình đổi trung bình mỗi 300 giây, giả sử lambda = 1/300. Trong 60 giây, xác suất có ít nhất một thay đổi là xấp xỉ **18,1%**.

Đây **không phải tỷ lệ request chắc chắn nhận dữ liệu stale**. Công thức chỉ ước lượng khả năng nguồn có thay đổi trong một khoảng thời gian dưới giả định mô hình; nó chưa xét thời điểm refresh, phân bố truy cập, invalidation, sự kiện đến trễ và đường cache nhiều tầng. Có thể dùng làm trực giác đánh đổi TTL, không thay thế đo hành vi thực.

### 6.2. TTL cố định và sliding TTL

- **Fixed TTL:** entry hết hạn sau một thời lượng xác định từ lúc tạo/cập nhật; giúp đặt rào cản tuổi tương đối dễ hơn.
- **Sliding TTL/time-to-idle:** lần đọc có thể làm mới thời điểm hết hạn; phù hợp quản lý tài nguyên ít dùng nhưng có nguy cơ giữ dữ liệu nóng rất lâu.
- **Expire at business boundary:** ví dụ bảng giá hết hiệu lực lúc 00:00 theo timezone đã xác định, hoặc token/đề nghị có thời điểm hết hiệu lực chính thức. Thời điểm nghiệp vụ nên được bảo vệ ở nguồn và trong quyết định cuối, không chỉ dựa vào cache timer.

Đặt TTL nên kết hợp dữ liệu version, epoch hoặc thời điểm hiệu lực khi stale mang rủi ro lớn. Cần thống nhất đồng hồ, monotonic timer và cách xử lý clock skew cho dữ liệu có timestamp.

## 7. Mẫu cache-aside và vai trò của invalidation

Cache-aside (lazy loading) là mẫu phổ biến:

~~~text
READ(key):
    value = cache.get(key)
    if value exists and is fresh:
        return value

    value = authoritativeStore.read(key)
    cache.put(key, value, ttl)
    return value
~~~

Ưu điểm là chỉ cache dữ liệu được đọc, dễ bổ sung vào một dịch vụ. Hạn chế là miss gây truy cập nguồn và cần xử lý đồng bộ thay đổi dữ liệu.

Quy trình write tương ứng:

~~~text
WRITE(key, newValue):
    commit newValue to authoritativeStore
    after successful commit:
        publish change notification / invalidate cache(key)
~~~

**Không invalidate trước khi database commit thành công** rồi coi như việc đồng bộ đã hoàn tất. Reader có thể miss cache, đọc bản cũ từ database và nạp lại bản cũ đúng lúc transaction chưa commit. Tuy nhiên, **invalidate sau commit cũng không tự loại bỏ mọi race condition**; phần tiếp theo giải thích cách dữ liệu cũ có thể xuất hiện lại.

Nếu cache miss mà database lỗi, quyết định dùng stale phải dựa trên chính sách của operation. Với checkout, fail closed hoặc báo lỗi có thể an toàn hơn việc ra quyết định từ dữ liệu chưa xác minh.

## 8. Những chiến lược ghi và cập nhật cache

| Chiến lược | Luồng chính | Điểm mạnh | Rủi ro |
| --- | --- | --- | --- |
| Cache-aside + invalidate | Write DB, sau commit làm mất hiệu lực key | Đơn giản, chỉ cache khi có nhu cầu | Race, miss storm và event lag |
| Write-through | Ghi qua một lớp cập nhật DB và cache | Có thể giảm miss sau write | Phải xử lý atomicity, thứ tự concurrent writes |
| Write-around | Ghi nguồn, không nạp ngay cache | Tránh chiếm cache cho dữ liệu chưa đọc | Lần đọc tiếp theo miss |
| Write-behind / write-back | Ghi cache trước, đẩy xuống DB sau | Latency write có thể thấp | Mất dữ liệu khi cache lỗi, ordering và durability phức tạp |
| Event-driven invalidation | Sau commit phát event để xóa/đánh dấu | Lan tới nhiều cache/consumer | Delivery trễ, duplicate, out-of-order, mất sự kiện |
| Versioned key | Key chứa source version hoặc epoch | Giảm rủi ro stale resurrection | Cần lấy được version mới, garbage collection key cũ |
| Short TTL only | Đợi entry tự hết hạn | Ít hạ tầng đồng bộ | Có cửa sổ stale tối đa gần TTL hoặc hơn nếu nhiều tầng |

Microservices thường chọn **database làm nguồn sự thật + cache-aside + invalidation theo sự kiện + TTL hữu hạn**. Đây là một tổ hợp dễ hiểu và có cơ chế hội tụ khi event không đến, nhưng không tự tạo consistency mạnh.

Write-behind chỉ thích hợp nếu kiến trúc đã có cách bảo đảm durability, idempotency, ordering và phục hồi sau sự cố. Với giao dịch quan trọng, không nên đưa “đã ghi cache” làm bằng chứng dữ liệu nghiệp vụ đã được commit bền vững.

## 9. Vô hiệu hóa chủ động (cache invalidation)

### 9.1. Invalidation theo key

Khi catalog-service cập nhật product 42, ứng dụng xóa hoặc đánh dấu hết hiệu lực entry theo key:
- product:42
- product-summary:42
- search-result có liên quan nếu được cache
- các biến thể theo locale, currency hoặc tenant liên quan

Vấn đề khó là **đồ thị phụ thuộc cache**. Một trường dữ liệu thay đổi có thể xuất hiện trong nhiều key tổng hợp. Nếu chỉ xóa product detail mà quên category listing hoặc search page, người dùng vẫn gặp dữ liệu cũ từ đường đọc khác.

Đừng quản lý phụ thuộc bằng wildcard scan toàn bộ Redis ở mỗi write trong hệ thống tải cao. Có thể dùng key namespace có version, danh sách index được thiết kế, event được route theo aggregate hoặc chấp nhận TTL ngắn cho cache tổng hợp khó invalidate chính xác.

### 9.2. Invalidation theo sự kiện

Một luồng đáng tin cậy hơn phát event có định danh:

~~~text
ProductUpdated {
  eventId: "event-9812",
  productId: "42",
  version: 18,
  committedAt: "timestamp-from-source"
}
~~~

Consumer cache đọc event và loại bỏ/đánh dấu key liên quan. Event cần chứa **aggregate ID**, **version/sequence** và thông tin loại thay đổi phù hợp. Không đưa dữ liệu nhạy cảm vào event khi consumer không cần.

Luồng:

~~~mermaid
sequenceDiagram
    participant API as Catalog API
    participant DB as Catalog DB
    participant OB as Outbox
    participant BUS as Event broker
    participant IC as Invalidation consumer
    participant CACHE as Cache

    API->>DB: Update product, version = 18
    API->>OB: Store ProductUpdated in same DB transaction
    DB-->>API: Commit
    OB->>BUS: Publish committed event
    BUS->>IC: Deliver event (may retry)
    IC->>CACHE: Invalidate key/version
    IC-->>BUS: Acknowledge after handling
~~~

Sơ đồ là ý tưởng: outbox record được lưu **trong cùng transaction với write dữ liệu** khi dùng transactional outbox. Một worker/CDC relay phát event sau commit; cần có retry và deduplication để chịu delivery ít nhất một lần. Nếu DB không hỗ trợ cùng transaction cho hai bản ghi, phải có cơ chế tin cậy khác.

### 9.3. Trường hợp mất sự kiện

Nếu một event bị mất/consumer dừng lâu, cache không được cập nhật ngay. TTL hữu hạn đóng vai trò **cơ chế hội tụ dự phòng**, nhưng không thể hứa một giới hạn stale theo nghiệp vụ nếu có tầng local luôn nạp từ tầng khác còn stale, TTL trượt, hoặc source tiếp tục trả read model chưa đồng bộ.

Cần:
- Durable subscription/offset và retry khi event handling lỗi.
- Dead-letter queue hoặc cơ chế phát hiện backlog, kèm hành động vận hành.
- Metric lag từ thời điểm commit đến khi các tầng liên quan xử lý.
- Idempotent handler cho duplicate event.
- Cơ chế đối soát version hoặc full refresh/rebuild cache.
- TTL và hard age độc lập để chặn phục vụ bản quá cũ.

## 10. Race condition: dữ liệu cũ xuất hiện lại sau invalidation

Một race thường gặp giữa read miss và write:

~~~text
T0  Reader A miss key product:42
T1  Reader A bắt đầu SELECT product -> đọc version 17
T2  Writer B commit product version 18
T3  Writer B delete cache product:42
T4  Reader A kết thúc và SET cache = version 17 với TTL mới
T5  Reader C đọc cache version 17 dù invalidate đã xảy ra
~~~

Nếu chỉ dùng “write DB rồi delete cache”, hệ thống vẫn có thể nạp lại dữ liệu cũ ở T4. TTL khi đó có thể làm bản cũ tồn tại thêm một khoảng đáng kể sau write.

Các cách giải quyết, tùy mức nhất quán cần có:

1. **Versioned cache key:** lưu theo product:42:v18 thay vì đè product:42. Reader lấy authoritative version hoặc một version pointer đáng tin; không được dựa trên pointer cũ mãi mãi.
2. **Compare-and-set theo version:** cache chỉ chấp nhận giá trị mới nếu phiên bản ghi vào không thấp hơn watermark/version hiện có.
3. **Tombstone/fencing token:** invalidation tăng generation hoặc đặt mốc không cho writer đang đọc trước đó ghi lại entry thuộc generation cũ.
4. **Read-after-write từ nguồn:** yêu cầu nhạy cảm về độ mới bỏ qua cache hoặc truyền version tối thiểu để reader chỉ chấp nhận bản đủ mới.
5. **TTL ngắn kết hợp invalidation:** có thể chấp nhận rủi ro stale có giới hạn đối với dữ liệu ít quan trọng, cùng với monitor.

Không phải chỉ thêm trường version vào JSON là giải quyết được race. Cần xác định **ai cấp version**, nơi lưu watermark, thứ tự ghi atomically và cách xử lý khi một request đã lấy bản cũ nhưng chưa ghi cache.

## 11. Event sai thứ tự và xử lý lặp

Giả sử event ProductUpdated(version=19) đến trước ProductUpdated(version=18) do retry, partition hoặc độ trễ xử lý. Nếu consumer cập nhật cache bằng payload của event nhận sau cùng mà không kiểm tra version, nó có thể lùi trạng thái về 18.

Mẫu xử lý:

~~~text
onEvent(event):
    lastSeen = watermarkStore.get(event.aggregateId)
    if event.version <= lastSeen:
        acknowledge / ignore duplicate or older event
        return

    invalidateAssociatedKeys(event.aggregateId)
    watermarkStore.advanceIfGreater(event.aggregateId, event.version)
    acknowledge after reliable handling
~~~

Đây là pseudocode. Trong hệ thống thật, thao tác kiểm tra/tiến version và invalidation cần được thiết kế cho concurrency, crash giữa các bước và eventual retry. Tùy chính sách, có thể tiến watermark sau khi cache đã được invalidate hoặc dùng thao tác nguyên tử/fencing ở kho lưu trữ. **Không ack trước khi ghi nhận đủ bằng chứng xử lý thành công**, nếu điều đó khiến event mất mà cache vẫn còn cũ.

Với event consumer có nhiều partition, cần hiểu thứ tự được bảo đảm **trong phạm vi partition/key** chứ không giả định mọi event toàn hệ thống có tổng thứ tự. Định danh version theo aggregate thường phù hợp hơn một timestamp phân tán dễ sai lệch.

Nếu event payload chỉ là “đã thay đổi”, invalidate thường an toàn hơn overwrite cache bằng dữ liệu event đến trễ. Nếu dùng event để cập nhật trực tiếp read model, version guard và quy trình đối soát càng quan trọng.

## 12. Soft TTL, hard TTL và phục vụ stale có kiểm soát

Một chính sách linh hoạt chia tuổi entry thành các vùng:

~~~text
Thời điểm nạp t0
  |
  |---- Fresh ----------------------|  soft TTL
  |                                 |
  |---- Stale được phép có điều kiện --------------| hard TTL
                                                   |
  |---- Không phục vụ; phải lấy mới hoặc báo lỗi --|
~~~

Giả sử:
- **Soft TTL = 30 giây:** sau 30 giây, trigger refresh.
- **Hard TTL = 120 giây:** từ lúc bản được lấy/khẳng định từ nguồn, không trả entry cũ quá 120 giây.
- **Stale-while-revalidate:** trong khoảng 30–120 giây, có thể phục vụ bản cũ và làm mới nền nếu operation cho phép.
- **Stale-if-error:** khi nguồn lỗi, tiếp tục dùng bản last-known-good chỉ trong giới hạn 120 giây và ghi lại degraded status nếu phù hợp.

Các con số là ví dụ. Quan trọng là **hard age phải dựa trên thời điểm dữ liệu thực sự được xác minh**, không bị reset mỗi lần một instance sao chép cùng bản cũ từ Redis sang local cache.

Pseudo-code:

~~~text
read(key, policy):
    entry = cache.get(key)

    if entry exists and entry.age <= policy.softTtl:
        return entry.value

    if entry exists
       and entry.age <= policy.hardTtl
       and policy.allowStaleForThisOperation:
        scheduleSingleBackgroundRefresh(key)
        return entry.value with freshness metadata

    fresh = source.read(key)
    if fresh succeeds:
        cache.replaceWithSourceVersion(fresh)
        return fresh.value

    if entry exists
       and entry.age <= policy.hardTtl
       and policy.allowStaleOnError:
        recordStaleServed(key)
        return entry.value with degraded freshness metadata

    fail according to operation contract
~~~

Trong triển khai thực, cần khóa refresh theo key, deadline, cancellation, metrics, và tránh đưa thông tin stale nhạy cảm ra header không phù hợp. Nếu action yêu cầu consistency mạnh, nhánh allowStale phải được tắt và route sang authoritative read hoặc trả lỗi.

**Stale-while-revalidate không có nghĩa “vĩnh viễn stale miễn vẫn phản hồi nhanh”.** Khi hard TTL đã vượt, response phải tuân theo chính sách fail closed hoặc lấy nguồn mới.

## 13. Stale-if-error và lựa chọn fail-open/fail-closed

Khi nguồn dữ liệu unavailable, phục vụ stale có thể cải thiện tính sẵn sàng nhưng phải được lựa chọn theo hậu quả nghiệp vụ.

| Tình huống | Có thể phục vụ stale? | Điều kiện |
| --- | --- | --- |
| Danh mục sản phẩm tĩnh | Thường có thể | Gắn thời gian cập nhật hoặc thông báo khi cần |
| Nội dung hướng dẫn, ảnh tĩnh | Có thể | Trong hạn lưu và không vi phạm yêu cầu thu hồi |
| Giá hiển thị | Có giới hạn | Chỉ tham khảo; xác minh khi thanh toán |
| Tồn kho hiển thị | Có giới hạn | Đặt hàng/reservation cần nguồn hiện hành |
| Trạng thái tài khoản bị khóa | Thường không | Bỏ stale hoặc dùng nguồn có tính nhất quán phù hợp |
| Quyền truy cập, auth decision | Rất hạn chế | Chính sách bảo mật xác định; ưu tiên không cấp quyền khi không xác minh |
| Payment authorization, fraud score | Phụ thuộc quy định rủi ro, thường nghiêm ngặt | Không dựa vào dữ liệu đã hết hiệu lực để quyết định |

Phân biệt **availability SLO** với **correctness SLO**. Một API trả bản cũ khi database lỗi có thể tăng tỷ lệ HTTP 200 nhưng làm giảm độ đúng nghiệp vụ. Nếu có phục vụ degraded response, cần metric và hiển thị rõ trong hệ thống vận hành.

Không dùng stale-if-error để che giấu mãi một dependency outage. Cần có ngưỡng tuổi, cảnh báo, retry có backoff và cách quay lại trạng thái fresh sau khi nguồn phục hồi.

## 14. Cache nhiều tầng và bài toán hiệu lực cuối cùng

Giả sử:
- L1 local cache TTL 10 giây.
- L2 Redis TTL 60 giây.
- CDN TTL 120 giây.

Không thể kết luận response luôn mới trong 120 giây chỉ từ TTL lớn nhất. Nếu local lấy dữ liệu từ Redis ở cuối tuổi thọ Redis và tự đặt lại TTL 10 giây, rồi CDN hoặc client lại lưu thêm một khoảng, độ cũ cuối có thể chịu **các lần refetch nối tiếp**. Nếu L2 dùng sliding TTL hoặc refresh từ nguồn còn cũ, khoảng stale có thể lớn hơn dự kiến.

Cách quản lý:
1. Gắn `sourceVersion` và `fetchedAt/verifiedAt` vào cache entry ở nơi có thể.
2. Tính hard age từ thời điểm xác minh nguồn, không đặt lại khi chuyển tầng.
3. Khi invalidation, xác định những tầng nào phải purge hoặc tăng namespace version.
4. TTL trên CDN, gateway, local cache và Redis cùng phục vụ một freshness contract.
5. Khi có nhiều region, xác định policy với replication lag và event propagation.
6. Đối với nội dung chứa user/tenant, không để public CDN cache response dùng chung.
7. Kiểm thử thật với các tầng đang hoạt động; test trực tiếp service có thể bỏ sót stale CDN.

Một thiết kế thường chọn TTL L1 ngắn hơn L2 và invalidation event cho L1; nhưng thời lượng cụ thể phải dựa trên latency/cache miss và cam kết freshness, không đặt theo thói quen.

## 15. HTTP cache headers và CDN

Với HTTP API, header cache là hợp đồng giữa server và client/shared cache. Một số directive phổ biến:

- **Cache-Control: max-age=60**: cho phép cache coi response còn fresh trong 60 giây theo quy tắc HTTP.
- **s-maxage=120**: tuổi fresh dành cho shared cache, có thể khác client.
- **stale-while-revalidate=30**: có thể phục vụ response stale trong khoảng bổ sung khi revalidate theo chính sách áp dụng.
- **stale-if-error=60**: có thể sử dụng stale trong điều kiện lỗi theo hỗ trợ của cache.
- **private**: response chỉ dành cho cache riêng, không cho shared cache.
- **no-store**: không lưu response; thường phù hợp nội dung nhạy cảm có yêu cầu bảo vệ.
- **ETag** kết hợp **If-None-Match**: revalidate có điều kiện, có thể nhận 304 nếu nội dung chưa đổi.
- **Vary**: chỉ ra các request header ảnh hưởng đến representation, giúp shared cache phân biệt biến thể.

Ví dụ response cho danh mục công khai ít thay đổi:

~~~http
HTTP/1.1 200 OK
Cache-Control: public, max-age=30, s-maxage=60, stale-while-revalidate=30
ETag: "catalog-v18"
Content-Type: application/json
~~~

Đây là chính sách minh họa và phụ thuộc khả năng CDN/browser. Nếu có yêu cầu purge ngay khi cập nhật, cần bổ sung CDN invalidation hoặc key version. Với response theo user hoặc tenant, phải thiết kế **Cache-Control, authorization, cookie, Vary và cache key** phù hợp; tránh đặt public chỉ vì endpoint dùng GET.

Cần phân biệt cache HTTP với application cache ở Redis. Header `max-age` chỉ điều khiển các cache HTTP phù hợp, không tự xóa entry Redis trong backend.

## 16. TTL jitter và tránh cache stampede

**Cache stampede** xảy ra khi nhiều request cùng miss một key nóng (hoặc nhiều key hết hạn đồng thời), khiến hàng trăm request đổ vào database trong một khoảng rất ngắn.

Ví dụ 500 request/s đọc cùng product phổ biến. Khi entry hết TTL, nếu 500 request cùng SELECT, pool DB có thể cạn và hệ thống phát sinh timeout.

Các biện pháp:
- **Single-flight/request coalescing:** trong một instance, chỉ một request fetch nguồn cho cùng key, các request khác chờ kết quả có deadline.
- **Distributed lease/lock:** giảm refresh trùng trên nhiều instance; cần TTL lease, fencing và xử lý lock holder chết.
- **Stale-while-revalidate:** trả bản cũ còn trong hard TTL, chỉ một worker refresh nền.
- **TTL jitter:** phân tán thời điểm expire của nhiều key, ví dụ chọn TTL ngẫu nhiên trong dải 90–110% TTL cơ sở theo chính sách.
- **Prewarming:** làm nóng các key trọng yếu sau deploy hoặc trước sự kiện dự báo traffic tăng.
- **Backpressure/rate limiting:** giới hạn request miss tới dependency.
- **Negative caching:** cache kết quả “không tồn tại” trong TTL ngắn nếu hợp đồng cho phép.

Jitter có tác dụng với việc **nhiều key** hết hạn cùng lúc; với một key cực nóng, cần single-flight/lock hoặc cơ chế stale có kiểm soát. Lock không phải giải pháp đầy đủ nếu request đã bắt đầu đọc bản cũ hoặc hệ thống có nhiều lớp cache.

Khi dùng distributed lock, phải tránh kịch bản khóa hết hạn nhưng worker cũ tiếp tục ghi đè kết quả của worker mới. Source version hoặc fencing token giúp kiểm soát thứ tự.

## 17. Negative caching và cache lỗi

Negative caching giữ trạng thái “không tìm thấy” hoặc “không có dữ liệu” để tránh repeated misses. Ví dụ product ID không tồn tại bị truy vấn 100 lần/giây; cache kết quả not-found vài giây giảm tải DB.

Tuy nhiên:
- Một product vừa được tạo có thể vẫn bị trả 404 trong cửa sổ negative TTL.
- 404 có thể là kết quả phân quyền (không được tiết lộ đối tượng), không được dùng chung giữa tenant.
- Lỗi timeout, 503 hoặc dependency outage không nên được cache như một sự thật nghiệp vụ “không tồn tại” nếu không có chủ đích.
- Negative entry phải có key, version và TTL riêng phù hợp rủi ro.
- Không trả lỗi “not found” từ cache nếu operation yêu cầu đọc nguồn sau khi vừa tạo.

Thiết kế key type rõ: `ProductFound(version=18)`, `ProductNotFound(checkedAt=...)` thay vì chỉ dùng null và không phân biệt “chưa query” với “đã query nhưng không tồn tại”.

## 18. Phân biệt xóa cache với thu hồi dữ liệu

Một tình huống đặc biệt: người dùng thay đổi quyền, sản phẩm bị gỡ vì pháp lý, hoặc yêu cầu xóa dữ liệu cá nhân. Cache TTL 24 giờ không phải lý do chính đáng để vẫn phục vụ nội dung bị thu hồi.

Cần một **revocation/invalidation path**:
1. Cập nhật nguồn dữ liệu hoặc quyền sở hữu.
2. Ghi event/outbox về thay đổi có mức ưu tiên cao.
3. Bump version/revocation epoch hoặc purge các tầng liên quan.
4. Khi request đến, xác minh version/quyền nếu bản cache có thể không đáng tin.
5. Quan sát xác nhận tất cả điểm phục vụ đã ngừng trả dữ liệu bị thu hồi.
6. Có quy trình emergency purge và audit.

**TTL không bảo đảm xóa vật lý tức thời**. Entry có thể vẫn nằm trong bộ nhớ, snapshot, backup hoặc replica sau khi hết hạn. Những yêu cầu về retention và xóa dữ liệu cần xử lý theo chính sách lưu trữ, bảo mật và quyền riêng tư riêng, không chỉ chọn TTL nhỏ.

## 19. Cache key, namespace và vấn đề đa tenant

Một key thiếu ngữ cảnh có thể làm sai dữ liệu hoặc lộ thông tin:

~~~text
Không đủ: product:42
Cần khi dữ liệu phụ thuộc: tenant:<tenant>:product:42:currency:VND:locale:vi
~~~

Đây là tên key minh họa; trong hệ thống thực, nên có encoding/canonicalization, giới hạn độ dài và version schema.

Khi xây dựng key, cần xem xét:
- Tenant hoặc access scope nếu response khác giữa các tenant.
- Locale, currency, feature flag và quyền xem giá nếu ảnh hưởng output.
- API/schema version khi cấu trúc dữ liệu thay đổi.
- Query params có ảnh hưởng dữ liệu; chuẩn hóa thứ tự/encoding.
- Không nhúng token/secret hoặc PII thô không cần thiết vào key.
- Namespace cho service và environment để tránh va chạm khi dùng chung cache cluster.

Một thiết kế tốt không để catalog staging dùng trùng key với catalog production. Tách hẳn cache instance/credential theo môi trường khi cần an toàn. Nếu dùng Redis đa tenant, ACL và network isolation phải bảo vệ ngoài naming convention.

## 20. Versioned key và invalidation theo generation

Đối với dữ liệu thay đổi thường xuyên hoặc nguy cơ stale resurrection, có thể dùng key chứa version:

~~~text
product:42:v17 → bản cũ
product:42:v18 → bản mới
current-version:product:42 → 18
~~~

Reader lấy phiên bản hiện hành từ nguồn có độ tin cậy phù hợp, rồi đọc key phiên bản tương ứng. Khi đổi product, writer commit version 18 và cập nhật cơ chế công bố version. Các key cũ có thể tồn tại cho đến TTL nhưng không còn được reader hợp lệ chọn.

**Điểm yếu cần giải quyết:** nếu key `current-version` cũng bị cache stale, reader vẫn chọn v17. Không được xem versioned key là bảo đảm strong consistency tự động. Có thể cần đọc version từ nguồn authoritative cho operation nhạy cảm, giữ watermark đủ tin cậy hoặc đưa version tối thiểu trong session/token.

Versioned key tăng số entry và chi phí lưu trữ. Cần retention/garbage collection hợp lý, tránh mỗi thay đổi tạo vô hạn bản sao. Với multi-region, cần xác định phạm vi version và chính sách khi có concurrent writers.

## 21. Read-your-writes và phiên làm việc của người dùng

Giả sử user đổi tên hiển thị từ “Lan” sang “Lan Anh”; ngay sau write, một read đi qua replica khác và nhận cache cũ. Đây là vi phạm read-your-writes dù eventual consistency của hệ thống vẫn hợp lệ.

Các lựa chọn:
1. Sau write, trả luôn trạng thái mới trong response và UI cập nhật từ kết quả đó.
2. Trong phiên yêu cầu, bypass cache hoặc đọc trực tiếp nguồn authoritative.
3. Truyền **minimumVersion** vừa ghi, reader chỉ chấp nhận cache entry có version đủ mới.
4. Tăng revision/session token để route request đến read model đã catch up hoặc chờ với deadline.
5. Sử dụng cơ chế nhất quán mạnh hơn cho operation cần cam kết.

Nếu không thể đạt minimumVersion trong deadline, cần hành vi rõ ràng: chờ thêm có giới hạn, đọc nguồn hoặc báo trạng thái chưa đồng bộ. Không âm thầm trả bản cũ nếu API đã hứa read-your-writes.

Dữ liệu nhạy cảm về quyền truy cập cần ràng buộc chặt hơn trải nghiệm cập nhật tên hiển thị. Không đưa quy tắc cho UI thông thường thành tiêu chuẩn cho kiểm soát truy cập.

## 22. Mối quan hệ với transaction và transactional outbox

Database commit và publish event tới broker là hai thao tác ở hai hệ thống khác nhau. Nếu commit thành công nhưng publish event thất bại, cache consumer không được báo đổi dữ liệu. Nếu publish event trước commit mà transaction rollback, cache lại bị invalidate theo thay đổi không có thật.

**Transactional outbox** thường giải quyết bằng cách:
1. Transaction ghi dữ liệu nghiệp vụ và outbox record cùng commit trong một database.
2. Relay/CDC đọc các record đã commit và publish event.
3. Broker/consumer xử lý ít nhất một lần, có idempotency và retry.
4. Consumer cập nhật watermark, invalidate cache hoặc làm mới read model.
5. Theo dõi outbox backlog và age để phát hiện chậm hội tụ.

Outbox không tạo distributed atomicity giữa database và cache; nó làm kênh thông báo thay đổi đáng tin cậy hơn. Read model và cache vẫn có eventual consistency, và TTL/hard age cùng source version là các lớp kiểm soát bổ sung.

Nếu event đến trễ nhiều phút, yêu cầu freshness vài giây vẫn không được đáp ứng chỉ nhờ việc dùng outbox. Cần quan sát và giải pháp phục vụ phù hợp, ví dụ bypass cache khi stale quá ngưỡng hoặc tăng độ ưu tiên kênh đồng bộ.

## 23. Chiến lược cache theo loại dữ liệu microservices

| Loại dữ liệu | Phương án gợi ý | Rủi ro và rào chắn |
| --- | --- | --- |
| Danh mục tham khảo | Cache-aside, TTL trung bình, event invalidation | Stale có thể chấp nhận nhưng cần giới hạn |
| Product detail | Cache-aside L1/L2, version và TTL | Cần purge đúng biến thể key khi sửa |
| Giá khuyến mãi | TTL ngắn, invalidation theo thay đổi giá | Quyết định chốt đơn phải đọc/kiểm chứng giá hiện hành |
| Tồn kho hiển thị | TTL rất ngắn hoặc read model có lag được đo | Reservation/commit tồn kho phải authoritative và chống oversell |
| Session metadata không nhạy cảm | TTL theo phiên và chính sách bảo mật | Không để lộ session giữa user/tenant |
| Quyền truy cập | Cơ chế thu hồi và nhất quán phù hợp | Không cấp quyền theo trạng thái đã bị thu hồi |
| Cấu hình feature flag | Push invalidation hoặc polling TTL ngắn | Với kill switch cần đường thu hồi nhanh và độ tin cậy cao |
| Báo cáo/analytics | TTL dài hơn, timestamp “as of” | Hiển thị rõ độ trễ đồng bộ và thời điểm dữ liệu |
| External API quota cao | Cache có giới hạn, backoff và stale-if-error | Rõ nguồn gốc, giới hạn độ cũ, tránh dữ liệu sai nghĩa |
| Rate-limit counters | Cơ chế đếm nguyên tử, TTL theo window | Tránh dùng cache best-effort làm nguồn quyết định chính nếu cần bảo vệ chặt |

Bảng chỉ là điểm xuất phát. Từng API có thể có nhiều mức độ tươi mới, ví dụ giá hiển thị ở trang chủ khác giá cuối được dùng ở payment. Nên tách contract theo tác vụ thay vì áp TTL duy nhất cho toàn bộ product aggregate.

## 24. Mẫu triển khai trong Java/Spring Boot

Với Spring Boot, có thể dùng abstraction cache hoặc client Redis/Caffeine tùy mục đích. Tuy nhiên, annotation cache đơn giản không tự giải quyết ordering, stale-while-revalidate, outbox và consistency đa instance.

### 24.1. Pseudocode Java cho cache-aside với version

~~~java
public ProductView getProduct(String tenantId, String productId) {
    String key = cacheKey(tenantId, productId);
    CacheEntry<ProductView> cached = cache.get(key);

    if (cached != null && freshnessPolicy.isFresh(cached)) {
        return cached.value();
    }

    ProductRecord fromDb = productRepository.findById(tenantId, productId);
    ProductView value = ProductView.from(fromDb);

    // Chỉ ghi vào cache nếu không lùi sourceVersion/watermark.
    cache.putIfVersionNotOlder(
        key,
        CacheEntry.of(value, fromDb.version(), clock.instant()),
        freshnessPolicy.hardTtl()
    );
    return value;
}
~~~

Các interface `CacheEntry`, `putIfVersionNotOlder` và `freshnessPolicy` là abstraction minh họa, không phải API dựng sẵn của Spring Boot. Phần so sánh version cần được hiện thực bằng atomic operation phù hợp với backend cache. Nếu cache lưu version mà không có CAS, hai request concurrent vẫn có thể ghi sai thứ tự.

### 24.2. Gắn invalidation vào commit

~~~java
@Transactional
public void updateProduct(UpdateProduct command) {
    Product product = productRepository.loadForUpdate(command.id());
    product.apply(command);
    product.incrementVersion();

    productRepository.save(product);
    outboxRepository.add(ProductUpdatedEvent.from(product));
    // Event relay sẽ publish sau commit. Không gọi Redis để làm
    // bằng chứng duy nhất của trạng thái transaction thành công.
}
~~~

Đây là skeleton: các kiểu class/method là giả định; không đủ để chạy nếu thiếu repository, transaction boundary và định nghĩa outbox. Nếu nhiều writer concurrent, cần optimistic/pessimistic locking phù hợp để version tăng đúng thứ tự và không mất cập nhật.

### 24.3. Consumer invalidation có idempotency

~~~java
public void onProductUpdated(ProductUpdated event) {
    if (!versionStore.tryAdvance(event.productId(), event.version())) {
        return; // sự kiện trùng hoặc cũ hơn bản đã biết
    }
    cacheInvalidator.invalidateProductAndDependentKeys(event.productId());
}
~~~

Đoạn trên chỉ minh họa. Nếu tiến watermark **trước** khi invalidation rồi process chết, một lần retry có thể bị bỏ qua và cache vẫn stale. Triển khai đúng cần sắp xếp/transaction hoặc trạng thái xử lý bảo đảm retry không bị đánh dấu hoàn tất sớm. Có thể invalidate idempotently trước khi commit watermark, hoặc dùng cơ chế state machine/outbox tương ứng.

Trong production, handler phải xác định ack, retry, timeout và xử lý crash giữa các bước. Code mẫu giúp định vị trách nhiệm, không thay thế một protocol đồng bộ đã được thiết kế.

## 25. Quan sát độ mới của dữ liệu và hiệu quả cache

**Cache hit rate** hữu ích nhưng không đủ: một cache trả sai dữ liệu với tỷ lệ hit 99% không phải hệ thống tốt. Nên đo các nhóm sau:

| Nhóm | Metric gợi ý | Cần trả lời |
| --- | --- | --- |
| Hiệu quả | hit/miss rate theo service/operation | Cache có thực sự giảm tải nguồn? |
| Độ trễ | cache read/write p95, source fetch p95 | Cache giúp giảm latency bao nhiêu? |
| Freshness | tuổi entry khi phục vụ, stale served count | Có trả bản quá hard age không? |
| Đồng bộ | invalidation lag, outbox lag, consumer lag | Từ commit tới bản sao sạch mất bao lâu? |
| Đúng phiên bản | stale-version rejection, version mismatch | Entry cũ có quay lại sau invalidate? |
| Áp lực | cache evictions, memory, connection errors | Cache có bão hòa hay không? |
| Tranh chấp | refresh single-flight waits, lock timeouts | Có stampede hoặc refresh trùng? |
| Nguồn | database QPS, query latency, pool pending | Cache miss có đẩy tải vượt capacity? |
| Tin cậy | timeout, fail-open/fail-closed decisions | Cache outage có ảnh hưởng đúng policy? |

Ví dụ hệ thống sinh event lúc 10:00:00 và consumer xử lý invalidation lúc 10:00:02, invalidation lag là 2 giây trong bối cảnh đo đó. Thời điểm cần đến từ clock/nguồn đáng tin; chênh lệch đồng hồ giữa host có thể gây số liệu âm hoặc lớn sai thực tế. Có thể dùng broker offsets và các phép đo đồng bộ nếu phù hợp.

**Đo stale thực sự** bằng cách lấy mẫu so sánh cache version với source version hoặc track event/commit version, thay vì chỉ xem TTL còn bao nhiêu. Các phép đối chiếu với nguồn có chi phí, nên cần sampling và quota.

### 25.1. Những ngộ nhận từ chỉ số

- Hit rate cao không chứng minh freshness hoặc correctness.
- Invalidation event đã publish không chứng minh mọi cache instance đã xử lý.
- Cache entry đã bị xóa ở Redis không chứng minh browser/CDN/L1 không còn bản cũ.
- TTL 60 giây không chắc chắn dữ liệu source thay đổi sẽ tới mọi reader trong 60 giây nếu có relay, layered recaching và sliding expiration.
- p99 request latency giảm không có nghĩa hành động nghiệp vụ hợp lệ.
- Không có error log không chứng minh hệ thống không phục vụ stale.

Đối với dữ liệu quan trọng, nên có dashboard gắn deployment version, source version, policy revision và freshness status để khi xảy ra lỗi có thể phân biệt release lỗi logic với thay đổi invalidation strategy.

## 26. SLI/SLO cho độ mới và độ đúng

Ví dụ các SLI có thể kiểm chứng:

1. **Fresh read ratio:** tỷ lệ response có sourceVersion không thấp hơn requiredVersion đối với các request có version requirement.
2. **Bounded staleness ratio:** tỷ lệ response có known data age không quá ngưỡng X giây ở operation cụ thể.
3. **Invalidation propagation latency:** p95/p99 thời gian từ commit đến khi các điểm cache mục tiêu đã được vô hiệu.
4. **Stale served on error:** số response degraded do nguồn lỗi và độ tuổi phân phối của chúng.
5. **Unauthorized stale use:** số quyết định quyền truy cập dùng trạng thái đã bị thu hồi.
6. **Correct business outcome:** tỷ lệ checkout dùng giá/tồn kho được authoritative validation.

Cần giải thích denominator: nếu SLI freshness chỉ được đo trên một tập sampled responses, phải ghi rõ phạm vi lấy mẫu và confidence. Nếu không quan sát được mọi tầng CDN/browser, không tuyên bố “99,99% user nhận dữ liệu mới” chỉ từ số liệu Redis.

Ví dụ SLO giả định cho danh mục: 99% truy vấn đã cache được xác minh với source version không quá ngưỡng 60 giây, khi hạ tầng đồng bộ hoạt động bình thường. Thực tế cần viết lại cho nhất quán về điều kiện version, measured age và outage semantics. Tên SLO không thể thay thế định nghĩa chính xác cách đo.

Với payment và auth, các SLI về correctness/authorization quan trọng hơn “cache response time”. Một số quyết định không nên đi qua stale cache trong bất kỳ cửa sổ cho phép nào.

## 27. Failure mode và phương án vận hành

### 27.1. Redis mất kết nối

- Cache client timeout nhanh và có circuit breaker/bulkhead phù hợp.
- Request fallback tới source theo rate limit hoặc giới hạn concurrency.
- Duy trì single-flight để tránh ồ ạt đọc database.
- Nếu nguồn không đủ capacity, trả 503/429 theo contract thay vì tạo retry storm.
- Dữ liệu ít nhạy cảm có thể dùng local last-known-good trong hard TTL.
- Theo dõi database QPS, pool pending và cache reconnect events.

### 27.2. Consumer invalidation tụt hậu

- Quan sát lag theo partition/consumer group, tỷ lệ xử lý lỗi.
- Dừng phục vụ stale nếu hard age vượt ngưỡng.
- Khôi phục consumer/replay từ durable log và đối soát version.
- Nếu không thể đảm bảo phạm vi affected keys, có thể bump namespace epoch để tránh đọc cache cũ, nhưng phải dự báo tải miss sau khi bump.

### 27.3. Một vùng (region) mất đồng bộ

- Xác định nguồn ghi authoritative và topology replication.
- Theo dõi lag trong từng region.
- Tại request cần read-your-writes, dùng minimum version/route tương ứng hoặc fallback theo policy.
- Tránh dựa vào timestamp từ đồng hồ rời rạc để giải quyết concurrent writes; dùng thứ tự/version được xác lập tại nguồn.

### 27.4. Bản dữ liệu bị thu hồi khẩn cấp

- Kích hoạt purge theo version/namespace hoặc đường invalidation ưu tiên.
- Chặn route nhạy cảm ở gateway hoặc source khi cần.
- Đo số điểm phục vụ đã nhận state mới; đối soát thực tế.
- Ghi audit trail của quyết định thu hồi và thời điểm hoàn tất.

### 27.5. Cache stampede sau deploy

- Kiểm tra cache key có thay toàn bộ do version mới không.
- Nếu thay namespace, làm nóng key nóng có kiểm soát.
- Sử dụng single-flight, TTL jitter, quota nguồn và rollout từng phần.
- Không điều chỉnh TTL đồng loạt quá ngắn vào giờ cao điểm.

## 28. Kiểm thử TTL và invalidation

Các test cần chứng minh *hành vi theo thời gian và cạnh tranh*, không chỉ kiểm tra get/set thông thường.

### 28.1. Kiểm thử thời gian

Dùng fake clock hoặc clock inject được:
1. t=0 đọc source version 1, nạp cache.
2. t=soft TTL − 1 ms: response còn fresh.
3. t=soft TTL + 1 ms: trigger refresh đúng policy.
4. t=hard TTL − 1 ms: nếu nguồn lỗi và operation cho phép, có thể stale.
5. t=hard TTL + 1 ms: không trả entry cũ nữa.
6. Entry chuyển từ L2 sang L1 không reset `verifiedAt` nếu chưa xác minh lại nguồn.
7. Eviction xảy ra trước TTL thì read miss và fetch lại; hành vi vẫn đúng.

### 28.2. Kiểm thử race

Tạo race có kiểm soát bằng barrier:
- Reader bắt đầu SELECT version 17 nhưng tạm dừng trước cache.put.
- Writer commit version 18 và invalidate.
- Cho Reader tiếp tục ghi 17.
- Xác nhận version guard/fencing không cho bản 17 trở thành entry hợp lệ.

Tương tự, gửi event version 19 trước version 18, lặp lại cùng event, và crash consumer giữa invalidation và ack. Kết quả mong muốn là cache cuối không lùi version và event chưa xử lý trọn vẹn vẫn có đường retry.

### 28.3. Kiểm thử nhiều tầng

Mô phỏng local cache, Redis và một gateway/CDN giả:
- Invalidate đúng product nhưng các biến thể locale/currency được xử lý phù hợp.
- Dữ liệu mới không bị che bởi một tầng còn sống TTL cũ quá giới hạn.
- Các instance nhận invalidate không đồng thời vẫn hội tụ.
- Session/tenant không thấy dữ liệu của nhau.
- Khi layer outage, fail-open hoặc fail-closed hoạt động đúng theo operation.

### 28.4. Kiểm thử tải và lỗi

- Nhiều request cùng miss một hot key.
- Redis bị delay/time out; database có giới hạn kết nối.
- Broker ngừng vài phút rồi phục hồi; replay nhiều event.
- Đồng thời có hàng nghìn key expire, kiểm tra TTL jitter và prewarm.
- Nguồn trả 404, 500 hoặc timeout; negative cache phân biệt đúng.
- Cache bị eviction do hết memory, không gây cascade vượt capacity DB.

Mỗi bài test nên ghi request rate, hit/miss, source QPS, p95 latency, stale served và nguồn dữ liệu cuối cùng. Thử nghiệm tải không cần dùng production nếu môi trường chuyên biệt đủ phản ánh hệ thống và không gây side effect thật.

## 29. Quy trình thiết kế TTL và invalidation từng bước

**Bước 1 — Liệt kê dữ liệu có thể cache.** Với từng key/operation, xác định source owner, tần suất thay đổi, payload size, hotness và người tiêu dùng.

**Bước 2 — Ghi freshness contract.** Độ cũ tối đa, yêu cầu read-your-writes, quyết định khi nguồn lỗi, các operation không được stale và khả năng hiển thị trạng thái degraded.

**Bước 3 — Chọn topology.** L1/L2/CDN, đường read/write, key namespace, tenant isolation và mức đồng bộ multi-region.

**Bước 4 — Chọn chiến lược.** Cache-aside, event invalidation/outbox, versioned key/CAS cho các race có tác động, soft/hard TTL, negative caching và single-flight.

**Bước 5 — Đặt hạn và failure policy.** TTL cơ sở theo change rate, miss cost, SLO; hard age độc lập; TTL jitter; quy tắc stale-if-error; giữ số connection nguồn trong budget.

**Bước 6 — Cài observability.** Hit/miss, source QPS, stale age, invalidation lag, consumer lag, rejected old version, cache outages và business correctness.

**Bước 7 — Kiểm thử concurrency.** Race giữa fetch/write/invalidate, duplicate/out-of-order event, mất broker, hết hạn các lớp cache, failover, hồi phục nguồn.

**Bước 8 — Rollout có kiểm soát.** Bật policy theo một phần traffic, theo dõi SLO và dữ liệu stale thực tế, điều chỉnh TTL theo evidence; có phương án rollback strategy hoặc bypass cache khi nghi ngờ sai dữ liệu.

**Bước 9 — Bảo trì.** Khi thêm field/consumer/variant key, cập nhật invalidation dependency; audit chính sách dữ liệu nhạy cảm và kiểm tra retention.

## 30. Ví dụ xuyên suốt: catalog, giá và tồn kho

Hệ thống thương mại điện tử có:
- **catalog-service** sở hữu mô tả và metadata sản phẩm.
- **pricing-service** sở hữu bảng giá hiệu lực.
- **inventory-service** sở hữu tồn kho và reservation.
- **checkout-service** điều phối tạo đơn, xác minh giá và giữ hàng.

### 30.1. Trang chi tiết sản phẩm

Catalog detail được truy cập nhiều và thay đổi ít:
- L1 TTL 5 giây, L2 soft TTL 30 giây, hard age 120 giây (giá trị minh họa).
- Khi ProductUpdated commit, outbox phát event để invalidate các key liên quan.
- Reader có thể phục vụ bản trước trong cửa sổ refresh nếu nội dung không nhạy cảm.
- L1/L2 cùng giữ sourceVersion và verifiedAt; chuyển tầng không reset tuổi đã xác minh.
- Một request cập nhật thông tin ngay trong UI có thể dùng response của write hoặc yêu cầu version tối thiểu.

### 30.2. Giá hiển thị

Pricing-service phát PriceChanged với version và thời điểm hiệu lực:
- Trang sản phẩm có thể hiển thị giá đã cache theo chính sách ngắn, kèm ngữ cảnh khi cần.
- Khi đến checkout, checkout-service yêu cầu giá hiện hành hoặc xác minh priceVersion từ pricing-service.
- Nếu giá thay đổi sau khi người dùng thêm vào giỏ, checkout phải giải thích/áp dụng chính sách nghiệp vụ đã định.
- Không coi một HTTP 200 lấy từ cache là đủ để xác nhận số tiền phải thanh toán.

### 30.3. Tồn kho

Inventory-service có thể cung cấp availableQuantity qua cache để hiển thị “còn hàng”:
- TTL rất ngắn hoặc cập nhật theo event.
- Chỉ số hiển thị có thể gần đúng trong thời gian ngắn.
- Khi đặt hàng, inventory-service cần kiểm tra và reserve bằng cơ chế đúng tính nhất quán, ngăn bán vượt quá năng lực.
- Một invalidate bị trễ có thể làm nút “Mua” hiển thị dù đã hết hàng; hệ thống cần phản hồi rõ khi reservation thất bại.

### 30.4. Dòng thời gian thay đổi

~~~text
10:00:00  Catalog cache product 42 version 17
10:00:01  Admin update -> DB commit version 18
10:00:01  Outbox record ProductUpdated version 18
10:00:02  Relay publish; các cache consumer nhận event
10:00:02  L2 Redis và L1 của các instance invalidate/version guard
10:00:03  User đọc -> lấy version 18 từ source, nạp cache
~~~

Thời gian trên chỉ để minh họa. Trường hợp consumer chậm 30 giây, các reader trong thời gian đó có thể nhận v17 nếu chính sách cho phép. Với operation buộc đọc v18, client có thể truyền minimumVersion=18 hoặc bypass cache. Nếu đến hard age mà vẫn không có bản mới, đường đọc phải trả kết quả đúng fail policy.

## 31. Bài tập thực hành

Giả sử microservices gồm catalog, pricing và checkout. Hiện tại:
- Redis cache product detail với TTL 15 phút.
- Mỗi replica có L1 cache time-to-idle 5 phút.
- Admin cập nhật giá, catalog xóa key Redis ngay trước khi transaction DB commit.
- Có một consumer event để xóa cache nhưng không lưu event version.
- Checkout sử dụng trực tiếp giá lấy từ cache để tạo thanh toán.
- Khi Redis lỗi, ứng dụng phục vụ bản trong local cache dù đã nằm ở đó nhiều giờ.

**Yêu cầu A — Phân tích sai lệch:** nêu mọi đường dữ liệu có thể cũ quá giới hạn, bao gồm local TTL trượt, invalidation trước commit, event sai thứ tự và quyết định checkout.

**Yêu cầu B — Thiết kế freshness contract:** tách policy cho mô tả sản phẩm, giá hiển thị, giá chốt thanh toán và tồn kho; chọn hard age và hành vi khi source outage có lý do nghiệp vụ.

**Yêu cầu C — Viết lại đường write/read:** commit DB rồi ghi outbox cùng transaction; event có version; cache-aside có version guard hoặc key thế hệ; reader dùng minimumVersion khi cần read-your-writes.

**Yêu cầu D — Kiểm soát tải:** dùng single-flight, jitter, rate limit và stale-while-revalidate có hard TTL; giải thích kịch bản 1.000 request cùng miss.

**Yêu cầu E — Quan sát:** đề xuất ít nhất 6 metric, trong đó phải có stale served, invalidation lag, source QPS và số lần ghi bị từ chối do version cũ.

**Yêu cầu F — Thử nghiệm:** mô phỏng race SELECT cũ → commit mới → invalidate → SET cũ, duplicate event và Redis timeout; nêu hành vi đúng cần quan sát.

Một giải pháp đạt mục tiêu phải chỉ ra **đâu là nguồn sự thật**, **mức cũ tối đa được chấp nhận**, **thời điểm phải xác minh giá trị hiện hành**, và **cơ chế bảo đảm stale không tồn tại vô hạn khi hệ thống lỗi**.

## 32. Câu hỏi tự kiểm tra

1. TTL, expiration, eviction và invalidation khác nhau như thế nào?
2. Vì sao TTL 60 giây ở Redis không chứng minh mọi client thấy dữ liệu cập nhật trong 60 giây?
3. Trong điều kiện nào soft TTL và hard TTL mang lại ích lợi?
4. Khi nào stale-if-error phù hợp và khi nào phải fail closed?
5. Vì sao xóa cache sau DB commit vẫn có thể bị nạp lại dữ liệu cũ?
6. Versioned key có giải quyết được vấn đề nếu version pointer cũng stale không?
7. Tại sao cần outbox khi phát event invalidation sau write?
8. Làm sao consumer tránh event version thấp ghi lùi trạng thái cache?
9. Khi nào nên xóa key, khi nào nên tăng namespace generation?
10. Vì sao tăng cache hit rate có thể gây hại nếu không đo freshness?
11. Những nhãn nào cần có trong cache key đa tenant?
12. Negative caching có thể biến 404 tạm thời thành lỗi kéo dài như thế nào?
13. Một cache entry hết hạn có chắc đã bị xóa vật lý khỏi bộ nhớ và backup không?
14. Điều gì xảy ra khi Redis lỗi và toàn bộ traffic dồn vào database?
15. Checkout nên lấy giá/tồn kho từ cache hay xác minh nguồn tại thời điểm nào?
16. Nên đo stale age bằng TTL còn lại hay so với source version? Vì sao?

## 33. Ghi nhớ

- **TTL là giới hạn vòng đời entry**, không phải lời hứa rằng mọi bản sao đều trở nên mới ngay sau một write.
- **Invalidation giúp giảm cửa sổ stale**, nhưng cần xử lý commit ordering, race, retry, duplicate event và multi-instance.
- **Staleness tolerance là quyết định nghiệp vụ theo operation**: nội dung tham khảo có thể stale, giao dịch và quyền truy cập đòi hỏi bảo đảm mạnh hơn.
- **Soft TTL + hard TTL + stale-while-revalidate** có thể cân bằng độ trễ và tính sẵn sàng khi dùng với tuổi nguồn đáng tin và giới hạn cuối.
- **Source version, minimumVersion, CAS hoặc fencing** giúp ngăn bản cũ xuất hiện lại sau invalidate và hỗ trợ read-your-writes.
- **Transactional outbox** làm thông báo thay đổi đáng tin cậy hơn; không tự tạo nhất quán mạnh giữa DB và cache.
- **Cache nhiều tầng, TTL trượt và event lag** làm việc bảo đảm độ cũ khó hơn so với một Redis key đơn lẻ.
- **Hit rate không thay cho correctness**; cần đo tuổi dữ liệu, độ trễ invalidate, phiên bản nguồn, tỷ lệ stale và tác động nghiệp vụ.
- Thiết kế tốt xác định rõ khi nào **phục vụ stale**, khi nào **bypass cache**, và khi nào **phải báo lỗi để không đưa ra quyết định sai**.
