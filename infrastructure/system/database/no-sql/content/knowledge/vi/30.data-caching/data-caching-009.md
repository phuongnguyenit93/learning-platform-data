# Ghi database rồi xóa/cập nhật cache và các cửa sổ cạnh tranh

Một ứng dụng sử dụng NoSQL thường bổ sung Redis hoặc một bộ nhớ đệm tại ứng dụng để tăng tốc các truy vấn lặp lại. Đường đọc phổ biến là **cache-aside**: thử đọc cache, nếu không có thì đọc database rồi đưa kết quả vào cache. Đường ghi thường được mô tả bằng một công thức ngắn:

~~~text
Ghi database thành công
      ↓
Xóa hoặc cập nhật cache
      ↓
Trả kết quả cho client
~~~

Nghe có vẻ đơn giản, nhưng hai hệ lưu trữ độc lập không cùng một transaction. Trong khoảng thời gian giữa **database commit** và **cache invalidation**, một request có thể thấy bản cũ. Nguy hiểm hơn, một request đọc bản cũ từ trước khi write commit có thể **đưa dữ liệu cũ trở lại cache sau khi cache vừa bị xóa**. Các writes đồng thời cũng có thể cập nhật cache theo thứ tự khác với thứ tự commit ở database.

Trong chương **Bộ nhớ đệm dữ liệu** của module **Database No SQL**, bài học này tập trung vào **ghi database rồi xóa/cập nhật cache và các cửa sổ cạnh tranh**: phân tích từng interleaving, giải thích giới hạn của TTL, delayed double-delete, cache-aside, write-through, version/CAS, outbox/CDC, và cách xây dựng một hệ có tính nhất quán đúng với hợp đồng nghiệp vụ. Ví dụ giả lập bằng Java giúp nhìn thấy lỗi ngay cả khi không có Redis thật; ví dụ Redis Lua cho thấy cách kiểm phiên bản nguyên tử ở **ranh giới cache**, cùng các giới hạn cần hiểu khi triển khai phân tán.

> **Kết luận định hướng:** ghi database rồi xóa cache là một chiến lược thực dụng để đạt **eventual consistency có kiểm soát**, không phải giao dịch nguyên tử trên hai hệ. Nếu một quyết định như “xác nhận chỗ cuối cùng” đòi tính đúng đắn mạnh, hãy kiểm tra invariant tại **database có thẩm quyền**; cache chỉ cung cấp gợi ý hoặc bản đọc theo freshness contract.

## 1. Ba loại trạng thái trong một đường cache

Giả sử một sản phẩm có:

~~~text
Product P42:
  title = "Bàn làm việc"
  priceMinor = 1500000
  version = 18
~~~

Thông tin có thể tồn tại ở:

| Nơi | Vai trò | Có quyền quyết định giá trị mới? |
| --- | --- | --- |
| Database chính | **Authoritative state** | Có, qua write/transaction hợp lệ |
| Redis cache | **Derived copy** | Không, trong mẫu cache-aside |
| Bộ nhớ local của từng Java instance | Cache lớp thứ hai | Không |
| CDN/client cache | Bản hiển thị/truy cập xa hơn | Không |

Đặt tên:

- `D(k)`: giá trị authoritative của key `k` trong database.
- `C(k)`: giá trị đang có trong cache, hoặc `MISS`.
- `V_D(k)`: phiên bản nguồn đã commit.
- `V_C(k)`: phiên bản của giá trị cache, nếu biết.

Một hệ có thể có `D(k)=v19` nhưng `C(k)=v18` trong một khoảng thời gian. Câu hỏi không phải chỉ “cache có đúng không?”, mà còn là **đường đọc nào được phép chấp nhận độ trễ này, trong bao lâu và phải làm gì khi quá ngưỡng**.

## 2. Hai đường cache-aside cơ bản

### Đường đọc

~~~text
Client
  |
  v
Application
  |---- GET cache(k) ------------> Redis
  |<--- HIT(value) / MISS --------|
  |
  +-- HIT → trả value nếu hợp đồng cho phép
  |
  +-- MISS
       |
       +---- SELECT k ----------> Database
       |<--- value, version -----|
       |
       +---- SET cache(k) ------> Redis
       |
       +---- trả value
~~~

### Đường ghi

~~~text
Client
  |
  v
Application
  |
  +---- UPDATE k ----------> Database
  |<--- COMMIT OK ----------|
  |
  +---- DEL cache(k) ------> Redis
  |
  +---- trả kết quả
~~~

Ở đây **database là nơi ghi trước**, cache được xóa sau commit. Khi một read sau đó gặp miss, nó đọc bản mới từ nguồn và điền lại cache.

**Điều kiện quan trọng:** `COMMIT OK` phải thực sự có nghĩa write nguồn đã commit theo consistency contract. Một request được “accepted” nhưng chưa commit hoặc write chỉ được queue bất đồng bộ không tương đương committed state.

## 3. Vì sao thường ghi database trước rồi mới xóa cache?

Nếu xóa cache trước, một reader có thể điền lại giá trị cũ **trong khi database chưa commit write**:

~~~text
T0: Database = A, Cache = A
T1: Writer DEL cache.
T2: Reader cache MISS.
T3: Reader đọc Database = A.
T4: Reader SET Cache = A.
T5: Writer COMMIT Database = B.
T6: Cache vẫn = A.
~~~

Đây là một dạng **stale fill** do thứ tự thao tác sai.

Nếu ghi database trước rồi xóa cache:

~~~text
T0: Database = A, Cache = A
T1: Writer COMMIT Database = B.
T2: Writer DEL cache.
T3: Read tiếp theo MISS → đọc B → SET B.
~~~

thì trong lịch **không có cạnh tranh và không có lỗi**, cache sẽ tự cập nhật đúng sau miss. Tuy nhiên **thứ tự tốt hơn không loại trừ mọi race**. Những phần tiếp theo chính là các lịch mà công thức ngắn bỏ sót.

## 4. Cửa sổ thứ nhất: sau commit, trước invalidation

~~~text
Time ─────────────────────────────────────────────>

Database:   A --------[COMMIT B]---------------- B
Cache:      A --------------------[DEL]------- MISS
                         ▲
                         |
                   Reader thấy A
~~~

Một reader có thể cache HIT `A` sau khi database đã commit `B` nhưng trước khi writer gọi `DEL`.

### Đây có phải bug?

Phụ thuộc hợp đồng:

- Với danh sách sản phẩm có **eventual consistency**, vài chục mili giây stale có thể chấp nhận.
- Với ứng dụng yêu cầu **read-after-write mạnh** cho cùng người vừa cập nhật, trả A có thể vi phạm hợp đồng.
- Với tồn kho/giữ chỗ, **dùng A làm bằng chứng còn hàng** để commit đơn mới là không an toàn.

Trong hệ bất đồng bộ, không thể giả định khoảng này luôn ngắn. Writer có thể bị GC pause, Redis timeout, mất mạng hoặc process crash **ngay sau DB commit**.

## 5. Cửa sổ thứ hai: stale fill sau khi đã invalidation

Đây là race quan trọng nhất của bài.

### Timeline

~~~text
Reader R                          Writer W
--------                          --------
GET cache(k) → MISS
READ database → A
                                  UPDATE database → B
                                  COMMIT B
                                  DEL cache(k) → OK
SET cache(k, A)
                                  (không còn gì để DEL)

Kết quả cuối:
  Database = B
  Cache    = A  ← bản cũ tái xuất hiện!
~~~

Thậm chí lúc writer trả thành công, cache đã bị điền lại bằng A. Nếu TTL dài, nhiều request sau đó có thể tiếp tục đọc A.

### Tại sao “DB trước, cache sau” chưa đủ?

Vì có **hai luồng cạnh tranh**:

1. R bắt đầu đọc nguồn **trước** khi W commit.
2. W commit và xóa cache.
3. R hoàn tất đọc cũ và SET cache **sau** DEL của W.

Thứ tự trong từng request vẫn đúng; **thứ tự giữa các requests** mới tạo lỗi.

### Tên gọi

Lỗi này thường được mô tả là **stale cache resurrection**, **read-fill/invalidation race** hoặc **cache stampede với stale write-back** trong những ngữ cảnh liên quan.

## 6. Cửa sổ thứ ba: hai writers cập nhật cache đảo thứ tự

Thay vì `DEL`, một số ứng dụng muốn **UPDATE cache ngay sau DB commit** để tránh cache miss:

~~~text
T0: DB = v10, Cache = v10.
T1: W1 commit DB = v11.
T2: W2 commit DB = v12.
T3: W2 SET cache = v12.
T4: W1 SET cache = v11 (đến muộn).
~~~

Kết quả:

~~~text
Database = v12
Cache    = v11  ← ghi đè bằng phiên bản cũ
~~~

**Thứ tự commit trong database không ép các writes ở Redis thực hiện cùng thứ tự.** Hai kết nối, hai Java instances, retry, network delay hoặc scheduling có thể đảo thứ tự cache updates.

### Kết luận

- Ghi DB rồi **xóa** cache có thể gây miss hoặc stale fill.
- Ghi DB rồi **cập nhật** cache giúp nóng dữ liệu hơn nhưng cần guard để **không áp phiên bản cũ lên bản mới**.
- Không giải quyết được bằng cách “để Redis xử lý nhanh”: latency nhỏ không phải bảo đảm không có interleaving.

## 7. Cửa sổ thứ tư: hai lần xóa và một lần điền cache

Xóa cache đơn giản thường an toàn hơn blind update đối với thứ tự các writers: một DEL muộn có thể xóa giá trị mới, gây cache miss chứ không trực tiếp ghi giá trị cũ.

Tuy nhiên xét:

~~~text
R1 đọc DB version 10, chưa fill.
W1 COMMIT v11, DEL cache.
R2 đọc DB v11, SET cache v11.
W2 COMMIT v12, DEL cache.
R1 SET cache v10 rất muộn.
~~~

Cache cuối cùng lại v10. **DEL của các writes không chống được reader cũ chạy quá lâu**. Một cache miss/read-fill concurrent chính là “writer” đối với cache, nên nó cũng phải được xem trong protocol.

### Đừng hiểu sai

Một DEL muộn tự nó không làm dữ liệu cũ tái xuất hiện. Lỗi xuất hiện khi có **stale fill hoặc stale upstream read** sau DEL. Phân biệt nguyên nhân này giúp chọn cơ chế khắc phục đúng.

## 8. Cửa sổ thứ năm: invalidation không được thực hiện

Các trường hợp:

~~~text
T1: DB COMMIT B.
T2: Java process crash.

hoặc

T1: DB COMMIT B.
T2: Redis network timeout.

hoặc

T1: DB COMMIT B.
T2: Không có consumer nào nhận được event invalidation.
~~~

Cache `A` có thể tồn tại tới khi TTL hết hoặc một cơ chế khác xóa nó.

### Tại sao không thể “rollback DB vì Redis lỗi”?

Vì DB transaction **đã commit**. Một request riêng tới Redis thất bại sau đó không tự đảo ngược commit. Nếu muốn nguyên tử xuyên DB và Redis, phải có giao thức giao dịch phân tán được cả hai bên hỗ trợ (thường không có cho cache-aside thông thường) hoặc thay đổi kiến trúc.

### Chính sách hợp lý

- Không đổi kết quả business write thành “chưa ghi” chỉ vì invalidation lỗi.
- Ghi nhận trạng thái invalidation chưa hoàn tất và retry có kiểm soát.
- Sử dụng outbox/CDC nếu cần khả năng phát sự kiện sau crash.
- TTL là một lớp giới hạn stale theo giả định về write/fill; không thay thế pipeline đáng tin.
- Với read bắt buộc mới nhất, đi tới authoritative source theo contract.

## 9. Cửa sổ thứ sáu: đọc từ replica chưa bắt kịp

Ngay cả khi một read bắt đầu **sau** DB commit, nó có thể nhận bản cũ:

~~~text
Primary replica:   version 12, committed
Secondary replica: version 11, lagging
~~~

Lịch:

~~~text
W COMMIT v12 tại primary.
W DEL Redis cache.
R cache MISS.
R đọc secondary → v11.
R SET cache v11.
~~~

**Stale fill không chỉ đến từ một query bắt đầu trước write**. Nó còn đến từ consistency level và replication lag ở tầng database.

Các lựa chọn:

- Đọc source với consistency đủ mạnh khi fill cache.
- Dùng session token/causal consistency hoặc version watermark nếu DB hỗ trợ.
- Kiểm `sourceVersion` trước khi chấp nhận cache fill.
- Giữ cache tombstone/fence version từ commit để bác v11.
- Chấp nhận stale theo SLO nếu chỉ là dữ liệu hỗ trợ hiển thị.

Một Redis `DEL` thành công không biến mọi DB replica thành “đã đồng bộ”.

## 10. Định nghĩa mức nhất quán trước khi chọn giải pháp

| Hợp đồng | Diễn giải | Có thể dùng cache thế nào? |
| --- | --- | --- |
| Eventual consistency | Sau khi các writes dừng và pipeline hoạt động, bản sao cuối cùng hội tụ | Cache-aside + invalidation/retry |
| Bounded staleness mục tiêu | Bản đọc cũ không vượt quá ngưỡng SLO/contract đã chỉ rõ | TTL, latency monitoring và degrade |
| Read-your-writes | Người vừa ghi phải nhìn thấy write của chính mình | Version-aware read hoặc bypass cache |
| Monotonic reads | Một session không thấy version giảm khi chuyển replica/cache | Session watermark/version guard |
| Linearizable read | Đọc bắt đầu sau write hoàn tất phải phản ánh write đó hoặc write mới hơn theo lịch | Thường cần authoritative/validated path |
| Invariant tại commit | Không double-book hoặc âm tồn kho | Conditional write/transaction tại authority |

Một UI catalog có thể chấp nhận eventual. Một API xác nhận booking thường **không được lấy quyết định từ cache eventual**.

**Không đánh đồng “cache hiển thị bản mới cuối cùng” với “mọi read là linearizable”.**

## 11. Phân biệt xóa cache và cập nhật cache

| Tiêu chí | DB commit → DEL cache | DB commit → SET cache |
| --- | --- | --- |
| Đường write | Xóa một entry | Đẩy bản mới vào cache |
| Cache sau write | MISS cho tới read tiếp theo | Có thể HIT ngay |
| Lỗi stale write từ writer khác | DEL muộn thường gây miss | SET muộn có thể đẩy cache về v cũ |
| Lỗi stale read fill | Vẫn có | Vẫn có, nếu không guard |
| Tăng read load lên DB | Có thể xảy ra sau invalidation | Thường giảm |
| Chi phí encode payload trên write | Nhỏ hơn | Cao hơn |
| Cache dành cho query aggregate | Cần invalidation nhiều keys | Cần cập nhật nhiều representations |

### Khi nào ưu tiên DEL?

Một cache-aside đơn giản với TTL, dữ liệu cập nhật không quá thường xuyên và chấp nhận cache miss là lựa chọn dễ vận hành.

### Khi nào cân nhắc UPDATE?

Hot keys luôn được đọc, và đã có **authoritative version** cùng atomic cache update guard. Nếu không có guard, cập nhật cache có thể làm giá trị mới bị ghi đè bởi update cũ.

**Không có phép xóa/cập nhật nào tự động biến dual-write thành atomic.**

## 12. Thao tác sai: update cache trước, commit DB sau

Một đoạn code:

~~~java
cache.put(productId, newPrice);
database.updatePrice(productId, newPrice);
~~~

có thể làm cache chứa giá mà DB chưa chấp nhận.

~~~text
T0: Cache = 100, DB = 100.
T1: SET cache = 120.
T2: Reader sees 120.
T3: DB transaction fails validation.
T4: DB remains 100.
~~~

Nếu người dùng được hứa giá hiển thị chỉ từ những writes đã commit, hành vi này không phù hợp.

**Ưu tiên source commit trước, cache mutation sau**, trừ khi sử dụng một protocol/cache product có write-through/write-behind semantics được thiết kế và chứng minh riêng.

## 13. Transaction callback: sau commit mới invalidation

Trong ứng dụng Java/Spring, dễ có bẫy:

~~~java
@Transactional
public void changePrice(String productId, long amount) {
    repository.updatePrice(productId, amount);
    redis.delete("product:" + productId);
}
~~~

Hàm `redis.delete` có thể chạy **trước khi transaction thực sự commit**, vì transaction interceptor thường commit sau khi method trả về.

### Hậu quả

~~~text
T0: DB transaction mở, update chưa commit.
T1: Redis DEL.
T2: Reader MISS, đọc DB old value, SET cache old.
T3: Transaction COMMIT new value.
~~~

Cache vẫn cũ, dù code trông như “DB rồi DEL”.

### Hướng tốt hơn

- Đăng ký thao tác invalidation ở **after-commit hook** của transaction manager.
- Hoặc ghi **outbox row cùng DB transaction**, để relay xử lý cache invalidation sau commit.
- Nếu dùng after-commit callback, vẫn phải xử lý **crash giữa commit và callback**: callback không durable mặc định.

**Thứ tự code trong một method không luôn bằng thứ tự commit của transaction.**

## 14. Sau COMMIT, trả lỗi cho client có thể gây retry sai

Giả sử:

~~~text
DB COMMIT price=120 → OK.
Redis DEL → timeout.
API returns HTTP 500.
Client retries update with new request ID.
~~~

Nếu write là “tăng giá 10%”, retry có thể tăng **hai lần**.

### Điều cần tách

- **Business commit outcome:** database đã commit gì?
- **Cache maintenance outcome:** cache invalidation đã chạy thành công chưa?
- **Client response:** có thể trả kết quả business commit và ghi nhận async repair nếu policy cho phép?

Nếu kết quả commit không rõ vì ACK từ DB mất, phải tra cứu theo idempotency key/version. **Không tự suy rollback từ timeout**.

### Một nguyên tắc thiết kế API

Đừng biến lỗi của **derived cache** thành lời báo sai về kết quả **authoritative write**. Đồng thời đừng che giấu việc cache maintenance hỏng nếu freshness là một cam kết bắt buộc — cần status/degraded mode và vận hành khắc phục.

## 15. TTL giúp gì và không giúp gì?

Một entry:

~~~text
SET product:P42 value EX 60
~~~

có thời gian sống danh nghĩa 60 giây.

TTL có thể giúp hạn chế thời gian một bản cache tồn tại **kể từ lần SET cuối**, nhưng:

- Không ngăn stale read trong 60 giây.
- Không ngăn R cũ điền lại cache **sau invalidation**, bắt đầu TTL mới.
- Không đảm bảo dữ liệu nguồn replica đã bắt kịp.
- Không tạo linearizable reads.
- Một user có thể thực hiện nhiều reads stale trong khoảng TTL.
- Nếu cache refresh sliding TTL mỗi lần HIT, bản cũ có thể tiếp tục sống nếu không có nguồn invalidation/version kiểm soát.

### Khi freshness là cam kết cứng

Phải xác định chính xác **staleness được đo từ lúc commit nào**, TTL và refresh có thể làm gì, và hệ có hành vi fail-closed khi không thể bảo đảm giới hạn hay không. Đừng hứa “không bao giờ cũ quá 60 giây” chỉ vì cấu hình EX 60 nếu có thể SET lại dữ liệu cũ bất cứ lúc nào.

## 16. Delayed double-delete là gì?

Một biện pháp được nhắc tới trong hệ cache-aside:

~~~text
DEL cache(k)
COMMIT database(k)=newValue
wait Δ
DEL cache(k) lần nữa
~~~

Hoặc biến thể:

~~~text
COMMIT database(k)=newValue
DEL cache(k)
wait Δ
DEL cache(k) lần nữa
~~~

Mục đích: nếu reader đã đọc bản cũ và điền vào cache trong một khoảng cạnh tranh ngắn, lần xóa sau sẽ dọn nó.

### Ví dụ

~~~text
T0: R đọc DB cũ.
T1: W COMMIT DB mới.
T2: W DEL lần 1.
T3: R SET cache bản cũ.
T4: W DEL lần 2.
T5: Read mới MISS và đọc DB mới.
~~~

### Nhưng không phải lời chứng minh

Nếu R chậm **lâu hơn Δ**, nó có thể SET bản cũ **sau lần DEL thứ hai**. Nếu W crash trước lần xóa sau hoặc lời hẹn bị mất, không có gì đảm bảo lần xóa này sẽ chạy.

**Delayed double-delete là heuristic thu hẹp xác suất stale, không phải một giao thức bảo đảm không có stale resurrection dưới mọi scheduling/network delay.**

## 17. Chọn khoảng chờ Δ có ý nghĩa gì?

Một số hệ dùng:

~~~text
wait 100 ms
wait 500 ms
wait 1 s
~~~

Các số này chỉ là ví dụ. Độ dài phù hợp còn phụ thuộc:

- P99/P99.9 database read latency.
- Redis/network latency.
- GC pause và thread scheduling.
- Replica lag.
- Read processing/serialization delay.
- Retry và queueing.

Ngay cả khi chọn Δ lớn hơn p99.9, vẫn có 0.1% request nằm ngoài p99.9; percentile **không phải hard upper bound**. Hơn nữa, delayed DEL sẽ làm cache miss/hot key stampede và tăng tải database.

### Vận hành

Nếu thực hiện delayed delete, hãy dùng cơ chế scheduling/retry có khả năng quan sát và recovery phù hợp, không giữ request thread ngủ vô ích hoặc mặc định một lời hẹn in-memory tồn tại qua process crash.

## 18. Một nguồn phiên bản đáng tin phải đến từ database

Để kiểm thứ tự, source có thể giữ:

~~~json
{
  "id": "P42",
  "priceMinor": 1200000,
  "version": 19
}
~~~

Mỗi write hợp lệ tăng version:

~~~text
v17 → v18 → v19
~~~

### Yêu cầu

1. Version tăng **nguyên tử theo aggregate/key** với giá trị mới trong authoritative DB.
2. Không lấy version từ `System.currentTimeMillis()` trên những app instances khác nhau: clock skew, timestamp collision và step làm thứ tự không đáng tin.
3. Không tái sử dụng version thấp sau delete/recreate nếu đó là cùng identity cần so thứ tự; dùng generation hoặc token bao gồm incarnation.
4. Với sharding/multi-region, xác định nguồn authoritative cho version và conflict semantics.

**Version là metadata của trạng thái được commit**, không phải counter tự tăng riêng ở Java process hoặc Redis khi DB còn là authority.

## 19. Conditional write/CAS tại database

Một thiết kế versioned update:

~~~text
Read product P42 version=18.
Attempt update price if version still 18.
On success: store price=newValue and version=19 atomically.
On conflict: retry business command or report conflict.
~~~

Ví dụ MongoDB Java sync driver:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.model.FindOneAndUpdateOptions;
import com.mongodb.client.model.ReturnDocument;
import org.bson.Document;

Document updateWithExpectedVersion(
        MongoCollection<Document> collection,
        String productId, long expectedVersion,
        long newPriceMinor) {

    return collection.findOneAndUpdate(
            Filters.and(
                    Filters.eq("_id", productId),
                    Filters.eq("version", expectedVersion)),
            Updates.combine(
                    Updates.set("priceMinor", newPriceMinor),
                    Updates.inc("version", 1L)),
            new FindOneAndUpdateOptions()
                    .returnDocument(ReturnDocument.AFTER));
}
~~~

Nếu không tìm thấy document phù hợp, kết quả là `null` theo contract method, có thể do key không tồn tại hoặc version conflict. Ứng dụng cần phân biệt theo nghiệp vụ.

### Lưu ý

- Một document update có tính nguyên tử theo phạm vi MongoDB hỗ trợ; điều đó không tự mở rộng sang Redis cache.
- Write concern ảnh hưởng ý nghĩa acknowledged/durable theo deployment.
- Nếu cập nhật nhiều documents và outbox cùng lúc, cần transaction/protocol phù hợp.
- Không lấy `version` tăng được rồi coi cache đã cập nhật; bước invalidation vẫn riêng.

## 20. Version-aware cache update: chặn SET đến muộn

Nếu writer W2 đã đưa v20 vào cache, writer W1 với v19 không được ghi đè:

~~~text
Cache = (version=20, value=B)
SET_IF_NEWER(version=19, value=A) → REJECT
~~~

Một thao tác atomic ở cache có thể:

1. Đọc version hiện có.
2. Nếu incoming version cũ hơn, bỏ qua.
3. Nếu incoming version mới hơn, ghi value/version cùng nhau.

Trong Redis, **đọc version rồi SET qua hai round trips không đủ**:

~~~text
W1 GET version=18
W2 GET version=18
W2 SET version=20
W1 SET version=19
~~~

Cần **Lua script, transaction có điều kiện hoặc primitive atomic phù hợp** để kiểm + ghi trong một điểm serialized.

### Giới hạn

Guard chống **update cũ so với cache đang có**. Nó không tự giải quyết:

- Cache entry bị xóa/evict mất cả version.
- Invalidation v20 chưa tới cache.
- Reader stale từ replica gửi v19 trước khi cache biết v20.
- Multi-region cache stores không cùng thứ tự.

Vì vậy cần một **version fence/high-watermark** nếu muốn chống stale fills sau invalidation.

## 21. Version fence cho cache fill và invalidation

Tách hai keys logic:

~~~text
cache:data:P42  → {version:19, payload:...}
cache:fence:P42 → highest version known committed/invalidation
~~~

Khi DB commit v20, một event invalidation có thẩm quyền tới Redis:

~~~text
fence := max(fence, 20)
if cached data.version < 20:
    delete cached data
~~~

Khi Reader muốn fill v19:

~~~text
if readVersion < fence:
    reject stale fill
else if readVersion < cachedVersion:
    reject stale overwrite
else:
    cache value/version together
~~~

### Vì sao fence có ích?

Lịch:

~~~text
R reads DB v19, pauses.
W commits DB v20.
W emits invalidation(version=20).
Redis records fence=20 and deletes old value.
R resumes, attempts to fill v19.
Redis rejects v19 because v19 < fence 20.
~~~

Reader cũ không thể “hồi sinh” v19 **sau khi fence đã được áp dụng**.

### Giới hạn chính xác

**Trước khi invalidation v20 tới Redis**, fence có thể vẫn ở v19, nên v19 có thể được chấp nhận trong cửa sổ đó. Cache version fence **không biến cross-store writes thành atomic** và không tạo linearizable read tức thì sau DB commit nếu propagation bị trì hoãn.

## 22. Redis Lua: áp invalidation có version fence

Ví dụ sau giả định:

- `KEYS[1]` là fence string.
- `KEYS[2]` là cache data hash, gồm fields `version`, `payload`.
- `ARGV[1]` là committed version từ DB.
- `ARGV[2]` là fence TTL milliseconds (nếu chính sách cho phép).

~~~lua
local incoming = tonumber(ARGV[1])
local fence = tonumber(redis.call('GET', KEYS[1]) or '-1')

if incoming > fence then
    redis.call('PSETEX', KEYS[1], ARGV[2], ARGV[1])
end

local stored = tonumber(
    redis.call('HGET', KEYS[2], 'version') or '-1')

if stored < incoming then
    redis.call('DEL', KEYS[2])
    return 1
end

return 0
~~~

Về logic:

- Event v20 không làm cache v21 bị xóa.
- Event v20 nâng fence lên 20, chặn stale fill v19 sau đó.
- Nếu cache đang v20 hoặc mới hơn, không cần xóa chỉ vì event v20.

### Các điều kiện production

1. Mọi keys script đọc/ghi phải nằm trong phạm vi **một Redis atomic execution**; với Redis Cluster, các keys trong một script phải thuộc cùng hash slot (dùng hash tag key naming hợp lệ).
2. `tonumber` của Redis Lua dùng số dạng double; không dùng để so phiên bản 64-bit vượt mức integer chính xác của double. Với versions lớn, dùng representation/so sánh an toàn hoặc primitive có semantics tương ứng.
3. TTL của fence **không được chọn tùy ý** nếu reader cũ có thể fill sau fence expiry. Cần bound cho stale fetch/retry hay cơ chế giữ fence lâu hơn, hoặc đọc nguồn có version đủ mới.
4. Redis eviction/restart có thể mất fence; cần policy restore và giới hạn consistency claim.
5. Invalidation chỉ có hiệu lực **sau khi script được thực thi**; trước đó vẫn có cửa sổ stale.
6. Script không bảo đảm message delivery; event outbox/CDC/retries đảm nhiệm đường truyền.

## 23. Redis Lua: fill giá trị có kiểm version

Một script minh họa:

~~~lua
local incoming = tonumber(ARGV[1])
local payload = ARGV[2]
local ttlMs = tonumber(ARGV[3])

local fence = tonumber(redis.call('GET', KEYS[1]) or '-1')
if incoming < fence then
    return 0
end

local cached = tonumber(
    redis.call('HGET', KEYS[2], 'version') or '-1')
if incoming < cached then
    return 0
end

redis.call('HSET', KEYS[2],
    'version', ARGV[1], 'payload', payload)
redis.call('PEXPIRE', KEYS[2], ttlMs)
return 1
~~~

Gọi script với:

~~~text
KEYS[1] = cache:fence:{P42}
KEYS[2] = cache:data:{P42}
ARGV[1] = source version
ARGV[2] = serialized payload
ARGV[3] = data TTL ms
~~~

**Hash tag `{P42}`** là cách các keys có thể cùng hash slot trong Redis Cluster, nếu quy tắc routing/cluster phù hợp.

### Thận trọng khi cùng version

Script minh họa chấp nhận phiên bản bằng nhau để idempotent refresh. Điều đó chỉ hợp lý nếu **một version xác định duy nhất một payload authoritative**. Nếu hai payload khác nhau cùng version hoặc cache giữ representation khác nhau theo authorization/locale, phải đưa scope/schema vào key hoặc thay equality policy.

### Giới hạn của Lua

Lua chỉ giữ **nguyên tử khi đọc/ghi một Redis execution domain**. Nó không thể đồng thời khóa hoặc commit database NoSQL bên ngoài. Mọi điều kiện phiên bản và nguồn event phải được thiết kế ở toàn hệ.

## 24. Vấn đề fence bị xóa hoặc hết TTL

Giả sử:

~~~text
T0: Redis fence=20.
T1: Reader R cũ đã giữ DB result v19.
T2: Fence hết TTL hoặc Redis eviction.
T3: R SET v19, vì không còn fence để so.
~~~

Vậy không được nói “có Lua script nên stale cache không bao giờ xảy ra”. Tính an toàn có thể phụ thuộc:

- Thời gian tối đa một read snapshot có thể tồn tại trước fill.
- Thời gian tối đa retry/buffer giữ một stale payload.
- Fence retention so với những giới hạn ấy.
- Chính sách restart/eviction.
- Nguồn đọc mạnh với version watermark.

Nếu không có giới hạn thời gian cứng, một fence hết TTL **không thể chứng minh** bác được mọi reader cũ. Với những trường hợp cần đảm bảo mạnh, xem xét **versioned immutable keys + authoritative pointer**, cache bypass, hoặc kiểm version ở một nguồn đáng tin gần commit path.

## 25. Versioned keys và generation

Một phương án khác:

~~~text
cache:product:P42:v19 → payload version 19
cache:product:P42:v20 → payload version 20
~~~

Nếu client biết **version hiện hành có thẩm quyền**, nó có thể đọc key version tương ứng, tránh lấy nhầm v19.

### Vấn đề chuyển version

Lấy version mới ở đâu?

- Nếu lấy từ một **pointer cache** có thể stale, client vẫn có thể bị dẫn tới v19.
- Nếu lấy từ DB mỗi read, giảm lợi ích cache.
- Nếu mang version từ session vừa commit, có thể bảo đảm read-your-writes cho **session đó**, nhưng không tự biết writes mới của người khác.
- Nếu dùng một cache pointer được cập nhật async, vẫn có propagation window.

### Vòng đời keys

Versioned keys cần TTL/garbage collection để không giữ vô hạn các generations cũ. Tránh tái sử dụng một version sau delete/recreate khi identity có thể đổi, bằng generation/incarnation ID.

**Versioned keys giải quyết stale overwrite ở tầng dữ liệu, nhưng không tự làm “current version pointer” luôn mới.**

## 26. Transactional outbox: tránh mất invalidation sau commit

Một cách tạo đường gửi đáng tin hơn:

~~~text
Java service
  |
  v
Authoritative DB transaction:
   - UPDATE product version=20
   - INSERT outbox event ProductChanged(P42,20)
  |
 COMMIT
  |
  v
Outbox relay / CDC
  |
  v
Message broker / worker
  |
  v
Redis invalidate cache + update fence
~~~

Nếu process crash ngay sau DB commit, outbox event vẫn còn để relay phát.

### Nhưng outbox không xóa cửa sổ stale tức thì

Một event có thể bị delayed bởi:

- Relay backlog.
- Broker unavailable.
- Consumer retry.
- Redis unavailable.
- GC pause hoặc network partition.

Trong thời gian đó cache có thể cũ. Outbox giúp **durability và eventual delivery theo giả định vận hành**, không tạo atomic cross-store read.

### Duplicate events

Relay có thể phát cùng event hai lần; invalidation theo version nên **idempotent**. Với Redis script `max(fence, incoming)`, xử lý lại v20 không hạ fence v21.

## 27. CDC và change streams

Một số NoSQL databases cung cấp **change streams/CDC** từ các writes được commit. Có thể dùng chúng để invalidate:

~~~text
DB change log/stream
     |
     v
CDC consumer
     |
     v
Redis invalidator
~~~

### Những điểm phải hỏi

1. Change stream có bao gồm mọi cập nhật mà cache phụ thuộc không?
2. Có khả năng resume sau restart không?
3. Resume token/offset lưu ở đâu và theo thứ tự nào so với invalidation?
4. Retention change log có đủ khi consumer offline lâu không?
5. Khi stream quá cũ để resume, làm **rebuild/reconciliation** nào?
6. Có duplicate/out-of-order events không?
7. Cache của một aggregate được invalidation theo key hay cần xóa nhiều keys query?

**Đọc change stream không tự đồng nghĩa có event delivery “exactly once”**. Consumer crash sau Redis DEL nhưng trước offset ACK có thể khiến event được gửi lại; vì vậy operation cần idempotent.

## 28. Retry và idempotency của invalidation

Một `DEL k` thông thường idempotent về trạng thái entry tại thời điểm thực hiện:

~~~text
DEL(k)
DEL(k)
→ cache vẫn MISS
~~~

Nhưng lịch có cạnh tranh:

~~~text
DEL(k) lần 1
Reader fill value mới
DEL(k) retry muộn
→ cache MISS
~~~

Retry muộn có thể làm mất **một bản cache mới hợp lệ**, gây miss. Nó không nhất thiết làm dữ liệu sai, nhưng có thể tăng database load.

### Invalidation với version

Thay vì blind DEL mọi event, xử lý:

~~~text
InvalidateIfOlderThan(k, committedVersion)
~~~

Event v19 không xóa cache v20, còn event v21 có thể loại bản v20.

**Idempotent về business correctness không đồng nghĩa miễn phí về hiệu năng**. Retry storm của invalidation vẫn có thể gây cache churn và DB stampede.

## 29. Cache-aside vs write-through vs write-behind

| Mẫu | Đường write | Đánh đổi |
| --- | --- | --- |
| **Cache-aside** | App ghi DB rồi invalidation/cache update | Dễ hiểu; hai hệ không atomic; stale windows |
| **Write-through** | App ghi qua cache layer, layer đồng bộ đến store theo contract | Có thể đơn giản hóa client, vẫn cần atomicity/failure semantics |
| **Write-behind/write-back** | Cache nhận write và đồng bộ DB sau | Latency write thấp, nhưng cache trở thành một phần của durability/authority |
| **Read-through** | Cache layer tự fetch source khi miss | Dễ dùng nhưng vẫn có read-fill races nếu thiếu guard |

### Write-behind đặc biệt cần thận trọng

Nếu cache xác nhận write trước khi DB commit:

~~~text
Client → Cache ACK
          |
          +-- later → Database commit
~~~

Cache crash trước flush có thể làm mất acknowledged writes, trừ khi hệ có durable log/recovery và contract cụ thể.

**Không đánh đồng write-through với dual-write atomic**, và không dùng write-behind cho dữ liệu tài chính/booking cần durability mạnh mà chưa chứng minh được failure behavior.

## 30. Cache stampede sau invalidation

Một hot key có 50.000 reads/s. Khi bị DEL, hàng nghìn requests có thể cùng miss rồi cùng đọc database:

~~~text
Hot key invalidated
      |
      +--> R1 MISS → DB
      +--> R2 MISS → DB
      +--> R3 MISS → DB
      ...
      +--> R1000 MISS → DB
~~~

Ngay cả khi không trả dữ liệu stale, điều này có thể làm DB quá tải.

### Các kỹ thuật

- **Single-flight/request coalescing:** một loader đọc DB, những readers khác chờ kết quả phù hợp.
- **Per-key bounded semaphore:** giới hạn số loaders song song.
- **TTL jitter:** tránh nhiều keys hết hạn đúng lúc.
- **Stale-while-revalidate:** cho đọc bản cũ trong một freshness window được tuyên bố rõ, đồng thời refresh nền.
- **Admission control/backpressure:** bảo vệ DB khi hot key bị miss.

### Cảnh báo

Single-flight có thể giảm stampede nhưng **không tự chữa stale fill**: nếu loader đã đọc DB cũ trước commit, sau đó W invalidate, loader vẫn có thể điền lại bản cũ. Kết hợp với version guard/fence nếu cần.

## 31. Stale-while-revalidate là một hợp đồng chủ động

Thay vì xóa cứng rồi bắt mọi request chờ DB, một số ứng dụng trả bản cache cũ kèm cơ chế refresh:

~~~text
Cache entry:
  value: product v18
  softExpiry: t1
  hardExpiry: t2

Read between t1 and t2:
  May serve stale v18
  Trigger refresh
~~~

Điều này có thể phù hợp cho:

- Catalog không quá nhạy cảm.
- Nội dung trang chủ.
- Dữ liệu hỗ trợ gợi ý.

Không phù hợp để:

- Xác nhận tồn kho cuối cùng.
- Quyết định số dư được phép chi.
- Thay thế permission revocation có yêu cầu cập nhật tức thì.

Phải nói rõ **soft TTL, hard TTL, maximum staleness và behavior khi source down**; không dùng tên kỹ thuật để che việc client được phép đọc dữ liệu cũ.

## 32. Negative caching và dữ liệu “không tồn tại”

Một API tra `user:U42` có thể cache:

~~~text
key: user:U42
value: NOT_FOUND
TTL: 30s
~~~

Điều này giảm load khi request tìm key không tồn tại lặp lại. Nhưng:

~~~text
T0: Reader finds NOT_FOUND; pauses before cache fill.
T1: Writer creates user U42, COMMIT.
T2: Writer invalidates cache.
T3: Reader fills NOT_FOUND.
~~~

User mới có thể bị báo không tồn tại cho tới expiry.

### Hướng bảo vệ

- Negative-cache TTL ngắn và được đánh giá theo freshness.
- Version/generation/tombstone fence cho create/delete.
- Không dùng `NOT_FOUND` cached cho nơi kiểm quyền hoặc quyết định irreversibility nếu contract không cho phép.
- Phân biệt lỗi database (timeout/unavailable) với kết quả not-found; **không cache lỗi hạ tầng thành NOT_FOUND**.

## 33. Delete/recreate và vấn đề version bị đặt lại

Giả sử record bị xóa rồi tạo lại cùng key:

~~~text
Old incarnation:
  user:U42, version=100

DELETE U42

New incarnation:
  user:U42, version=1
~~~

Một cache fence v100 sẽ bác bản v1 mới dù nó hợp lệ nếu **version không bao gồm generation/incarnation**.

### Phương án

- Version tăng xuyên mọi lifecycle của cùng logical identity.
- Dùng `(generation,version)` có thứ tự được source quyết định.
- Dùng immutable IDs mới cho entity tái tạo, ánh xạ alias cũ sang mới qua authority.
- Tách tombstone với retention và quy tắc reset.

Đây là lý do “mỗi document có integer version” **chưa đủ** nếu business cho phép delete/recreate và reuse ID.

## 34. Cache nhiều tầng: local Caffeine và Redis

Một service có thể dùng:

~~~text
Java local cache (L1)
      |
      v
Redis shared cache (L2)
      |
      v
NoSQL DB
~~~

Sau commit, DEL Redis mới chỉ xử lý L2. Một Java instance khác có thể tiếp tục đọc **L1 cũ**.

### Invalidation fan-out

~~~text
DB commit v20
   |
   v
Event ProductChanged(v20)
   |
   +--> Redis fence/DEL
   +--> Instance A local cache invalidation
   +--> Instance B local cache invalidation
   +--> Instance C local cache invalidation
~~~

Một instance mất event thì sao?

- L1 TTL và version guard.
- Pub/sub có đủ durability không? Nếu không, cần recovery/reconcile.
- Có cần kiểm session watermark trước khi trả L1 value không?
- Có thể dùng short-lived L1 caching cho những fields không quan trọng?

**Thêm lớp cache là thêm các cửa sổ lệch phiên bản**, không chỉ thêm một bước GET.

## 35. Cache cho query/list phức tạp

Một write tới product P42 không chỉ ảnh hưởng:

~~~text
product:P42
~~~

mà còn có thể ảnh hưởng:

~~~text
products:category:desk:page1
products:price:under-2m
search:desk:sort-popularity
recommendations:tenant:T42
~~~

Nếu hệ chỉ xóa entry theo ID, các **query result caches** vẫn có dữ liệu sai hoặc thiếu.

### Chiến lược

1. **Direct key invalidation:** biết chính xác keys phụ thuộc entity.
2. **Tag/generation invalidation:** cache keys mang generation của category/query namespace.
3. **Short TTL:** giới hạn độ trễ ở query caches khó xác định dependency.
4. **Event-driven projector:** cập nhật các read models chuyên biệt.
5. **Không cache truy vấn quá động:** nếu maintenance cost cao hơn lợi ích.

### Cẩn thận với category move

Khi P42 chuyển từ category A sang B, phải invalidate **cả danh sách A và B**; nếu chỉ đọc trạng thái mới, có thể quên key của category cũ. Domain event hoặc transaction cần chứa **before/after** hoặc enough context để xác định dependencies.

## 36. Thứ tự invalidation từ nhiều writers

Giả sử source commit:

~~~text
W1: version 20
W2: version 21
~~~

Nhưng events đến cache:

~~~text
E21 arrives
E20 arrives later
~~~

**Blind DEL**:

~~~text
E21 deletes v20.
Reader fills v21.
E20 deletes v21 → unnecessary MISS.
~~~

**Versioned invalidation**:

~~~text
E21 sets fence=21, deletes cache if version <21.
Reader fills v21.
E20 sees fence=21; does not delete v21.
~~~

Lợi ích vừa về safety đối với stale-fill **sau fence**, vừa giảm cache churn. Nhưng cần per-key version monotonic và atomic compare trong cache.

## 37. Các loại retry sau lỗi cache

| Lỗi | Điều có thể xảy ra | Cách xử lý |
| --- | --- | --- |
| Redis DEL timeout | DEL có thể đã xảy ra hoặc chưa | Retry idempotent có backoff |
| Redis SET timeout | Value có thể đã set | Retry với version guard |
| DB write timeout | Write có thể đã commit | Dùng request ID/conditional state lookup |
| Event broker timeout | Event có thể đã publish | Stable event ID/dedupe |
| Consumer crash sau DEL | Offset chưa ACK | Redelivery an toàn |
| Cache miss khi DB down | Không thể fill | Fail/degrade/stale policy |
| Redis eviction fence | Stale fill không còn bị chặn | Revalidate/retention/policy |

**Đừng retry authoritative write chỉ vì Redis lỗi**. Lỗi cache maintenance và lỗi write commit là hai outcome riêng.

## 38. Java demo: stale resurrection và version fence

Chương trình Java sau **cố tình điều khiển thứ tự sự kiện** để chứng minh race. Không cần Redis thật; `NaiveCache` mô phỏng cache-aside không có version guard, còn `FencedCache` mô phỏng cache có high-watermark.

Tạo file `CacheRaceDemo.java`:

~~~java
public final class CacheRaceDemo {

    record Snapshot(long version, String value) {}

    static final class Database {
        private Snapshot state = new Snapshot(1, "OLD");

        synchronized Snapshot read() {
            return state;
        }

        synchronized Snapshot write(String nextValue) {
            state = new Snapshot(
                    state.version() + 1, nextValue);
            return state;
        }
    }

    static final class NaiveCache {
        private Snapshot cached;

        void fill(Snapshot snapshot) {
            cached = snapshot;
        }

        void invalidate() {
            cached = null;
        }

        Snapshot get() {
            return cached;
        }
    }

    static final class FencedCache {
        private long minimumVersion = -1;
        private Snapshot cached;

        synchronized void invalidate(long committedVersion) {
            minimumVersion =
                    Math.max(minimumVersion, committedVersion);

            if (cached != null
                    && cached.version() < minimumVersion) {
                cached = null;
            }
        }

        synchronized boolean fill(Snapshot snapshot) {
            if (snapshot.version() < minimumVersion) {
                return false;
            }
            if (cached != null
                    && snapshot.version() < cached.version()) {
                return false;
            }
            cached = snapshot;
            return true;
        }

        synchronized Snapshot get() {
            return cached;
        }
    }

    public static void main(String[] args) {
        Database db = new Database();
        NaiveCache naive = new NaiveCache();
        FencedCache fenced = new FencedCache();

        // Reader R chụp bản cũ trước khi writer commit.
        Snapshot oldRead = db.read();   // version 1

        // Writer W commit rồi invalidation.
        Snapshot committed = db.write("NEW"); // version 2
        naive.invalidate();
        fenced.invalidate(committed.version());

        // R bị trễ và chỉ bây giờ mới fill cache.
        naive.fill(oldRead);
        boolean allowed = fenced.fill(oldRead);

        System.out.println("DB: " + db.read());
        System.out.println("Naive: " + naive.get());
        System.out.println("Fenced old fill allowed: " + allowed);
        System.out.println("Fenced before fresh read: "
                + fenced.get());

        // Một read mới trả version 2 từ authoritative DB.
        fenced.fill(db.read());
        System.out.println("Fenced after fresh read: "
                + fenced.get());
    }
}
~~~

Chạy với Java 17+:

~~~bash
javac CacheRaceDemo.java
java CacheRaceDemo
~~~

Kết quả kỳ vọng:

~~~text
DB: Snapshot[version=2, value=NEW]
Naive: Snapshot[version=1, value=OLD]
Fenced old fill allowed: false
Fenced before fresh read: null
Fenced after fresh read: Snapshot[version=2, value=NEW]
~~~

### Giới hạn của demo

- Đây là lịch sự kiện dựng sẵn **không có thread/network thực**; race được biểu diễn bằng thứ tự lệnh.
- `FencedCache` giữ fence trong RAM và chưa xử lý restart, eviction, TTL hoặc distributed nodes.
- Writer áp fence ngay sau commit trong demo; production có **commit→invalidation propagation window**.
- Demo chứng minh **stale fill sau fence bị bác**, không chứng minh mọi read sau DB commit đều linearizable.

## 39. Java: một service contract tách commit và cache maintenance

Ví dụ interface ở mức kiến trúc:

~~~java
interface ProductRepository {
    // Commit price and increment version atomically.
    ProductSnapshot changePrice(
            String productId, long newPriceMinor,
            String idempotencyKey);

    ProductSnapshot readAuthoritative(String productId);
}

interface VersionedCache {
    ProductSnapshot get(String productId);
    boolean fillIfNotOlder(ProductSnapshot snapshot);
    void invalidateIfOlder(String productId, long version);
}

record ProductSnapshot(
        String productId, long version, long priceMinor) {}
~~~

Một service:

~~~java
final class ProductService {
    private final ProductRepository repository;
    private final VersionedCache cache;

    ProductService(ProductRepository repository,
                   VersionedCache cache) {
        this.repository = repository;
        this.cache = cache;
    }

    ProductSnapshot changePrice(
            String productId, long amountMinor,
            String requestId) {

        ProductSnapshot committed =
                repository.changePrice(
                        productId, amountMinor, requestId);

        // Trong production, ghi outbox cùng DB commit
        // để invalidation có thể retry sau crash.
        try {
            cache.invalidateIfOlder(
                    productId, committed.version());
        } catch (RuntimeException cacheFailure) {
            // Report/queue repair; không giả vờ DB rollback.
            reportCacheFailure(
                    productId, committed.version(), cacheFailure);
        }
        return committed;
    }
}
~~~

`reportCacheFailure` và implementation repository/cache là **các thành phần ứng dụng giả định**, không phải class biên dịch độc lập. Code trình bày **ranh giới trách nhiệm**, không thay thế transactional outbox hoặc structured recovery.

### Hợp đồng source

`ProductRepository.changePrice` cần:

- Idempotency key ổn định qua retry.
- Phiên bản tăng nguyên tử theo write.
- Trả **state đã commit** (hoặc xử lý unknown outcome đúng).
- Không trả v mới trước khi transaction hoàn tất.

### Hợp đồng cache

`invalidateIfOlder` phải atomic theo version ở cache. Nó không được biết nhiều hơn DB về business authority.

## 40. Read-your-writes với session watermark

User sửa giá và nhận committed version 20:

~~~json
{
  "productId": "P42",
  "newPriceMinor": 1200000,
  "committedVersion": 20
}
~~~

Request read tiếp theo có thể mang `minimumVersion=20` theo một session contract đáng tin.

~~~text
Cache contains version 19:
  reject as too old for this session.

Cache contains version 20:
  acceptable under version semantics.

Cache MISS:
  read source with consistency sufficient
  to see at least version 20, or wait/retry/fail.
~~~

### Lưu ý

- Session watermark bảo vệ user đã ghi, không tự bắt mọi user khác thấy ngay v20.
- Token/version phải được kiểm soát tenant/auth scope và không dùng để bypass authorization.
- Nếu đọc DB replica vẫn chỉ thấy v19, không được ghi v19 vào cache rồi trả cho session yêu cầu v20.
- Version guard cần áp ở **mọi tầng L1/L2** hoặc bypass phù hợp.

**Read-your-writes là một hợp đồng session; cache invalidation đơn lẻ không tự bảo đảm nó.**

## 41. Lock có giải quyết hoàn toàn race không?

Một giải pháp trực giác là đặt distributed lock quanh read/fill và write/invalidation:

~~~text
Acquire lock(k)
  DB read / cache fill / DB write / invalidate
Release lock(k)
~~~

Nhưng:

- Mọi code path đọc/ghi phải tuân cùng lock.
- Lock service tạo thêm latency, contention, availability dependency.
- Lock TTL có thể hết khi holder bị GC pause.
- Một packet write cũ có thể đến sau lock đã được cấp cho holder mới.
- Lock không làm hai database commits thành một transaction.

Nếu cần bảo vệ dữ liệu quan trọng, **conditional write/CAS tại authoritative DB** vẫn là cốt lõi. Cache có thể dùng lock hoặc single-flight để **giảm duplicate loads**, không coi đó là chứng minh không có stale reads trừ khi có protocol đầy đủ với fencing và scope rõ.

## 42. Khi có nhiều regions hoặc active-active writes

Nếu nguồn dữ liệu cho phép multi-region concurrent writes:

~~~text
Region A commits product update A.
Region B commits product update B concurrently.
~~~

Không có **per-key total order** rõ ràng cho cache version nếu chỉ dùng timestamp local hoặc counters độc lập.

Phải xác định:

- Source sử dụng last-write-wins, vector clock, consensus hay conflict resolution nào?
- Có version globally ordered hay causal metadata?
- Event v20/v21 có ý nghĩa so sánh ở mọi region không?
- Cache ở từng region đọc source cục bộ và chịu replication lag ra sao?
- User cần session consistency khi chuyển region không?

**Redis Lua so version dạng số chỉ đúng khi version mang một thứ tự có thẩm quyền**. Nó không thể giải quyết xung đột business state mà source DB chưa giải quyết.

## 43. Cache correctness khi có rollback, delete hoặc transaction abort

Một transaction update product và outbox:

~~~text
BEGIN
  UPDATE product
  INSERT outbox
ROLLBACK
~~~

Không có event committed, cache không nên bị cập nhật bằng giá trị **chưa commit**.

Với delete:

~~~text
DB DELETE product P42 committed, new generation/version.
Invalidate cache P42.
~~~

Nếu reader cũ đã lấy P42 trước delete rồi cache fill sau invalidation, sản phẩm đã xóa có thể “xuất hiện lại” trong cache. Version tombstone/fence hoặc read-source policy cần ngăn lỗi nếu business contract yêu cầu.

### Delete không phải lúc nào là “không còn record”

Trong NoSQL có TTL/tombstone/soft-delete:

- Source có thể dùng marker thay vì xóa vật lý tức thì.
- Query theo consistency khác nhau có thể thấy giá trị cũ trong một thời gian theo DB semantics.
- Cache negative entry cũng có phiên bản/lifecycle.

Thiết kế cần nói rõ **deleted state** và version, không chỉ gọi `DEL key` ở Redis rồi bỏ qua nguồn.

## 44. Cache stampede và stale-fill phải kiểm thử cùng nhau

Nếu cache bị DEL ở hot key:

~~~text
T0: 100 concurrent requests MISS.
T1: 60 readers bắt đầu DB read khi source còn v18.
T2: Writer commit v19, invalidate.
T3: Các readers v18 trả về và fill cache.
~~~

Single-flight có thể giảm 100 reads thành 1, nhưng nếu read duy nhất bắt đầu trước commit, nó **vẫn có thể fill v18 sau invalidation**.

Một kế hoạch đúng cần:

1. Coalesce readers để bảo vệ DB.
2. Gắn version vào source response.
3. Dùng cache fence hoặc write-version watermark.
4. Đặt TTL/bounds phù hợp.
5. Không dùng kết quả cache để commit invariant.

**Giảm tải và giữ consistency là hai mục tiêu cần kiểm riêng.**

## 45. Đo lường cửa sổ stale

Đặt các mốc:

~~~text
t_commit      = lúc source write có hiệu lực
t_invalidate  = lúc cache nhận/áp invalidation
t_visible     = lúc read qua cache thấy version mới
~~~

Các độ trễ:

\[
L_{\text{invalidation}}=t_{\text{invalidate}}-t_{\text{commit}}
\]

\[
L_{\text{visibility}}=t_{\text{visible}}-t_{\text{commit}}
\]

### Hai chỉ tiêu khác nhau

- **Invalidation lag** cho biết mất bao lâu để cache maintenance chạy.
- **Visible freshness lag** cho biết client thấy state mới sau bao lâu.

Sau DEL, cache có thể miss rồi DB reader nhận replica cũ, nên invalidation lag nhỏ **không bảo đảm visible lag cũng nhỏ**.

### Metrics nên có

| Metric | Câu hỏi |
| --- | --- |
| Cache hit/miss rate | Cache có hiệu quả không? |
| Stale read samples | Đọc cache có version nhỏ hơn source không? |
| Invalidation age/backlog | Commit event có đang bị trễ không? |
| Rejected stale fills | Version fence có đang chặn race không? |
| Cache version distribution | Những keys nào còn phiên bản cũ? |
| DB replica lag | Source read có thể stale đến đâu? |
| Redis error rate | DEL/SET có lỗi không? |
| Retry/duplicate events | Cache churn nhiều không? |
| Hot-key DB load after invalidation | Có stampede không? |
| GC pause/timeouts | Cửa sổ chậm do Java runtime không? |

**Không đo freshness chỉ bằng TTL**, vì giá trị cache có thể được fill từ bản nguồn cũ ngay cả khi entry mới tạo.

## 46. Tracing một write xuyên DB và cache

Một trace hữu ích:

~~~text
requestId=price-801
productId=P42
sourceCommitVersion=20
dbCommitAt=10:00:00.100Z
outboxEventId=evt-20
invalidationStartedAt=10:00:00.120Z
invalidationAppliedAt=10:00:00.160Z
cacheFence=20
cacheFillRejectedVersion=19
~~~

Không log toàn payload nhạy cảm. Để điều tra race, cần **request ID, source version, event ID và thứ tự state transitions**; chỉ dựa timestamp giữa những hosts có clock skew có thể làm sai kết luận.

### Correlation

Trace/span context hoặc correlation ID cần được truyền qua:

~~~text
API → DB transaction → outbox → broker → invalidator → Redis
~~~

Nếu broker message tới muộn, sự kiện vẫn truy về commit nguồn ban đầu.

## 47. Ma trận lỗi và hành vi đúng

| Tình huống | Nguy cơ | Bảo vệ phù hợp |
| --- | --- | --- |
| Read trước commit, fill sau DEL | Stale resurrection | Fence/version guard; read contract |
| W1/W2 commit đúng, SET đảo thứ tự | Cache đi lùi | Atomic SET-if-newer |
| DB commit, app crash trước DEL | Cache cũ kéo dài | Outbox/CDC, TTL, repair |
| Redis DEL timeout | Không rõ invalidation đã thực hiện | Retry/dedupe/backoff |
| Source read replica lag | Fill bản cũ sau DEL | Stronger read hoặc min version |
| Invalidation events đảo thứ tự | DEL mới hợp lệ bị xóa vô ích | Versioned invalidation |
| Fence TTL hết quá sớm | Stale fill được nhận | Retention bound/revalidation |
| Local L1 cache bỏ lỡ event | Đọc cũ dù Redis mới | L1 TTL/versions/recovery |
| Query cache chưa được invalidation | Danh sách sai/thiếu | Dependency map/generation/TTL |
| Redis down khi DB commit | Mất cache maintenance tạm thời | Durable retry và degraded mode |
| Cache MISS khi DB down | Không lấy được bản mới | Fail hoặc stale theo contract |
| Client timeout sau DB commit | Retry business write lặp | Idempotency/state lookup |
| Product deleted rồi recreated | Version reset sai | Generation/incarnation |
| Cache stampede | DB quá tải | Single-flight, bounded loaders |
| Admin sửa DB ngoài app | Không phát event | CDC/reconciliation/governance |

## 48. Thiết kế fault injection cho race

Một test chỉ chạy `GET` sau khi `POST` hoàn tất sẽ khó gặp các lịch cạnh tranh.

Hãy tạo **test hooks/barriers** ở:

~~~text
READ_CACHE_MISS
AFTER_DB_READ_BEFORE_CACHE_FILL
AFTER_DB_COMMIT_BEFORE_INVALIDATE
AFTER_INVALIDATE_BEFORE_RESPONSE
AFTER_REDIS_SET_BEFORE_ACK
~~~

### Test A: stale-fill race

1. R miss và đọc v10, **tạm dừng trước SET**.
2. W commit v11 và invalidates.
3. Cho R resume.
4. Kiểm cache không nhận v10 nếu protocol có fence v11.

### Test B: concurrent writers

1. W1 commit v11, tạm dừng cache update.
2. W2 commit v12 và fill cache v12.
3. Cho W1 update v11.
4. Kiểm cache không đi lùi.

### Test C: lost invalidation

1. DB commit v11.
2. Crash app trước Redis DEL.
3. Restart relay.
4. Kiểm outbox/CDC dẫn tới cache repair.

### Test D: stale replica

1. W commit v11 ở authority.
2. DEL cache.
3. Cho cache loader đọc replica lagging v10.
4. Kiểm version fence hoặc min-version rejects v10.

### Test E: TTL/fence eviction

1. W invalidate v11 và tạo fence.
2. Giữ reader cũ v10 bị pause.
3. Cho fence expire/evict.
4. Resume reader cũ.
5. Xác định **giới hạn của guarantee**, không tuyên bố test pass nếu stale v10 được nhận ngoài contract.

## 49. Chọn giải pháp theo yêu cầu sản phẩm

| Bối cảnh | Thiết kế thường đáng cân nhắc |
| --- | --- |
| Catalog ít thay đổi | DB-first DEL + TTL + monitoring |
| Catalog hot keys | DB-first DEL/update + single-flight + version guard |
| Profile người dùng cần read-your-writes | Session version watermark hoặc đọc source sau write |
| Search/list cache phức tạp | Event-driven invalidation theo dependency/generation |
| Booking/tồn kho | Authoritative conditional transaction; cache chỉ hint |
| Nhiều writers đồng thời | Per-key committed version + atomic cache CAS |
| Invalidation không được mất sau crash | Transactional outbox/CDC + retry + reconciliation |
| Multi-region active-active | Conflict/ordering semantics từ source trước, cache theo đó |
| Cache cực nhạy cảm với stale | Bypass cache hoặc cơ chế validated read phù hợp |

**Không có một TTL hoặc một Lua script dùng được cho mọi mức consistency.** Chọn từ invariant/freshness SLO rồi mới chọn cơ chế.

## 50. Những anti-pattern thường gặp

| Anti-pattern | Vì sao sai/thiếu | Hướng thay thế |
| --- | --- | --- |
| “DB rồi DEL thì luôn nhất quán” | Có commit→DEL và stale-fill windows | Nêu consistency contract, version guard |
| DEL trước DB COMMIT | Reader fill nguồn cũ | After-commit/outbox |
| SET cache trước DB | Hiển thị uncommitted write | Source-first |
| Blind SET theo response arrival | Writer cũ ghi đè mới | Atomic versioned SET |
| Đọc DB rồi SET không kiểm version | Stale resurrection | Min version/fence |
| Dựa hoàn toàn TTL | TTL bắt đầu lại sau stale fill | Version/freshness policy |
| Delayed double-delete như bằng chứng tuyệt đối | Reader có thể chậm hơn delay | Xem là heuristic |
| Dùng local timestamp làm version | Clock skew/collision | DB committed revision |
| Redis GET version rồi Redis SET | TOCTOU trong cache | Lua/atomic primitive |
| Fence TTL quá ngắn | Reader cũ fill sau fence expiry | Bound/retention/revalidate |
| Bỏ qua replica lag | Fill bản cũ sau DEL | Source consistency/watermark |
| Quên cache L1 | Một app instance vẫn stale | Multi-tier invalidation |
| Chỉ xóa cache theo entity ID | List/search cache vẫn sai | Dependency invalidation |
| Redis lỗi thì retry write DB | Duplicate business effect | Tách commit và cache outcome |
| Dựa hoàn toàn Redis Pub/Sub không durable | Instance bỏ lỡ event | Recovery/TTL/version |
| Không có outbox/reconciliation | Cache sai kéo dài khi app crash | Durable event/repair |
| Single-flight là giải pháp consistency | Loader vẫn có thể đọc cũ | Kết hợp version guard |
| Redis lock TTL là bảo đảm mạnh | GC/network có thể làm lock hết | Authority CAS/fencing nếu cần |
| Nhận cache HIT làm bằng chứng còn hàng | Cached availability stale | Conditional DB commit |
| Không có cache version trong logs | Khó xác định stale window | Source/cache revisions |

## 51. Bài tập thực hành

### Bài 1 — Mô tả cửa sổ cạnh tranh

Vẽ timeline từ `COMMIT database` tới `DEL cache`. Vì sao trong khoảng này một read có thể trả bản cũ? Với catalog và với booking, hành vi nào được chấp nhận?

**Gợi ý:** phụ thuộc freshness/consistency contract.

### Bài 2 — Stale resurrection

R cache miss, đọc DB v5. W commit v6 và xóa cache. R sau đó SET cache v5. Xác định DB/cache cuối và giải thích vì sao các thứ tự thao tác trong từng thread vẫn “đúng”.

**Gợi ý:** interleaving giữa hai threads.

### Bài 3 — Hai writers

W1 commit v7, W2 commit v8, W2 SET cache v8 trước W1 SET v7. Thiết kế predicate atomic để bác W1.

**Gợi ý:** incomingVersion phải lớn hơn hoặc bằng version đang có theo policy.

### Bài 4 — Delete muộn

E8 tới trước E7. E8 xóa cache v7, reader fill v8, E7 tới sau và DEL. Cache có sai không? Hiệu năng chịu tác động gì?

**Gợi ý:** cache MISS không phải stale; versioned invalidation giảm churn.

### Bài 5 — Transaction callback

Một `@Transactional` method gọi Redis DEL trước khi return. Vì sao Redis DEL có thể chạy trước DB COMMIT? Đề xuất after-commit/outbox.

**Gợi ý:** transaction interceptor commit sau method body.

### Bài 6 — Process crash

DB commit v9, process crash trước invalidation. TTL có thể giúp gì? Outbox giúp gì và không bảo đảm điều gì về thời gian hiển thị ngay lập tức?

**Gợi ý:** durable event không xóa propagation window.

### Bài 7 — Stale replica

Primary v10, secondary v9. W invalidates Redis sau commit v10, R miss và đọc secondary v9. Thiết kế một guard để không cache v9.

**Gợi ý:** min source version/fence, consistency đủ mạnh.

### Bài 8 — TTL

Cache TTL 60s. R cũ điền bản v4 sau khi W commit v5 được 30s. Tại sao “TTL=60s” không chứng minh mọi read cũ tối đa 60s kể từ commit?

**Gợi ý:** TTL tính lại khi SET stale.

### Bài 9 — Delayed double-delete

Chọn delayed delete 500ms. R bị GC pause 3s sau khi đã đọc bản cũ. Hãy tạo history mà lần delete thứ hai không chặn được stale fill.

**Gợi ý:** heuristic không có bound hard.

### Bài 10 — DB version

Vì sao `System.currentTimeMillis()` của hai app instances không phải nguồn phiên bản phù hợp? Hãy đề xuất version tăng nguyên tử ở DB.

**Gợi ý:** clock offset, collision, steps và per-key ordering.

### Bài 11 — Lua CAS

Redis đang cache v20. Update v19 tới muộn. Viết logic so version và giải thích vì sao GET+SET bằng hai network requests không đủ atomic.

**Gợi ý:** TOCTOU.

### Bài 12 — Fence

Redis fence=22, một reader cố fill v21 sau DEL. Điều gì phải xảy ra? Nếu event invalidation v22 chưa tới thì có thể kết luận gì?

**Gợi ý:** bảo đảm chỉ sau khi fence được cài.

### Bài 13 — Fence hết hạn

Reader cũ giữ snapshot v21 trong 2 phút, fence v22 TTL 30s. Điều gì xảy ra nếu reader fill sau 40s và cache data cũng đang MISS?

**Gợi ý:** retention assumptions bị phá.

### Bài 14 — Delete/recreate

Old user ID có version=100, xóa rồi tạo user mới cùng ID với version=1. Vì sao fence v100 có thể bác record mới hợp lệ?

**Gợi ý:** generation/incarnation.

### Bài 15 — Negative caching

R đọc NOT_FOUND, W tạo user, R fill NOT_FOUND sau invalidation. Thiết kế policy negative cache phù hợp.

**Gợi ý:** short TTL và version/tombstone guard.

### Bài 16 — Cache L1/L2

App có local Caffeine L1 và Redis L2. W xóa Redis nhưng App B vẫn HIT L1. Thiết kế propagation/TTL và session version handling.

**Gợi ý:** mỗi tầng đều có thể stale.

### Bài 17 — Query cache

Product P42 đổi category từ A sang B. Những list-cache keys nào có thể bị sai? Tại sao chỉ biết category mới không đủ invalidation?

**Gợi ý:** before/after dependencies.

### Bài 18 — Outbox

Thiết kế transaction source commit v25 cùng outbox event. Relay crash sau publish, trước checkpoint. Event được giao hai lần; làm sao consumer không hạ fence?

**Gợi ý:** `max(fence,incoming)`.

### Bài 19 — Read-your-writes

User vừa sửa giá v30, cache còn v29. Thiết kế request sau đó mang minimumVersion và xử lý trường hợp replica source cũng chỉ trả v29.

**Gợi ý:** bypass/wait/fail, không trả bản cũ như mới.

### Bài 20 — Cache stampede

1000 reads đồng thời MISS một hot key. Single-flight giảm tải nhưng loader đã đọc v4 trước khi write v5. Vì sao vẫn cần version guard?

**Gợi ý:** coalescing không chứng minh freshness.

### Bài 21 — Java demo

Chạy `CacheRaceDemo.java`, thay `FencedCache.fill` để cố tình bỏ qua `minimumVersion`. Giải thích output khác nhau và phạm vi mà demo không mô phỏng.

**Gợi ý:** script/demo không atomic xuyên DB và Redis.

### Bài 22 — MongoDB CAS

Đọc một product v18 rồi hai clients cùng update với `expectedVersion=18`. Bao nhiêu update có thể thắng theo một-document conditional write? Client thua nên xử lý ra sao?

**Gợi ý:** conflict, retry command có kiểm soát.

### Bài 23 — Source read consistency

Với một NoSQL store có read replicas và eventual reads, hãy mô tả cách cache fill ảnh hưởng freshness khi source primary đã commit nhưng replica chưa đồng bộ.

**Gợi ý:** cache không thể mới hơn dữ liệu đọc được nếu không có version gate.

### Bài 24 — Fault injection

Thiết kế ba tests với barriers: stale read before SET; writer commit before DEL; two cache SETs inverted. Nêu invariant, expected trace và cleanup.

**Gợi ý:** deterministic interleavings.

### Bài 25 — Monitoring

Hãy chọn ít nhất tám metrics/log fields giúp điều tra “Redis trả v17 dù database đã commit v19”. Phân biệt invalidation lag, stale fill, replica lag và cache version.

**Gợi ý:** source version, event ID, fence, cache fill rejected count.

### Bài 26 — Strong booking

Search/Redis báo còn một căn hộ, nhưng authoritative DB đã hết. Thiết kế API đặt chỗ để không double-book; cache được dùng ở bước nào?

**Gợi ý:** cache là hint, commit bằng transaction/CAS ở DB.

### Bài 27 — Multi-region

Hai regions cập nhật cùng product, mỗi region tạo version bằng local counter. Vì sao Redis Lua max-version có thể sai? Cần gì ở source?

**Gợi ý:** total order/conflict resolution có thẩm quyền.

### Bài 28 — Reconciliation

Một invalidation event bị mất quá retention, cache vẫn giữ v12 trong khi DB v15. Thiết kế job phát hiện và sửa drift, có giới hạn tải.

**Gợi ý:** compare versions, targeted repair, TTL.

### Bài 29 — Chọn chiến lược

So sánh DB-first DEL, DB-first versioned SET, delayed double-delete, outbox invalidation và bypass cache theo correctness, latency, memory, vận hành.

**Gợi ý:** không có giải pháp duy nhất cho mọi SLO.

### Bài 30 — Thiết kế cuối chương

Thiết kế cache cho API `GET /products/{id}` và `PATCH /products/{id}/price` với yêu cầu:

1. Database là source of truth.
2. Cập nhật giá có conditional version.
3. Retry request không áp dụng write hai lần.
4. Reader cũ không được ghi đè cache version mới **sau khi fence đã áp dụng**.
5. Caching hỗ trợ 10.000 reads/s cho hot keys.
6. Redis down không làm business write bị báo rollback sai.
7. Có outbox/CDC retry sau crash.
8. Có freshness SLO, metrics, degraded mode và reconciliation.

Hãy vẽ sequence diagram cho write, cache miss và event; viết một bảng fault matrix với read-fill race, DB replica lag, Redis unavailable và app restart.

**Gợi ý:** phân biệt **authoritative correctness** với **derived cache freshness** và **độ trễ phục hồi**.

## 52. Checklist review trước khi triển khai

1. Source of truth của field và invariant là nơi nào?
2. Cache entry có gắn nguồn version/generation không?
3. DB write commit xong **thật sự** mới invalidation?
4. Có thể crash giữa commit và DEL không? Recovery bằng gì?
5. Reader đã đọc trước commit có thể fill sau invalidation không?
6. Read từ DB replica có thể stale sau commit không?
7. Two writers có thể gửi cache SET đảo thứ tự không?
8. Cache CAS/check version có atomic không?
9. Fence version được tạo từ source có thẩm quyền không?
10. Fence mất do TTL/eviction/restart thì consistency còn gì?
11. Invalidation event bị duplicate/out-of-order có an toàn không?
12. Query cache và local L1 cache có nằm trong invalidation scope không?
13. Negative caching, delete/recreate và generation được xử lý chưa?
14. Có idempotency key cho authoritative retries không?
15. Cache outage có bị nhầm thành DB commit failure không?
16. TTL có được diễn đạt đúng là thời gian sống từ fill, không phải freshness guarantee tuyệt đối không?
17. Delayed double-delete có được ghi là heuristic, không phải proof không?
18. Có single-flight/backpressure bảo vệ DB hot keys không?
19. Có metrics invalidation lag, stale fill và source/cache versions không?
20. Đã thử deterministic race injection và long GC pause chưa?
21. Có runbook repair/reconciliation khi mất event chưa?
22. Đường booking/payment có quyết định ở authoritative DB không?

**Nếu hệ chỉ có hai dòng “UPDATE database; DEL Redis” nhưng chưa giải thích stale-fill sau DEL, crash trước DEL và read replica lag, thiết kế chưa mô tả đầy đủ cửa sổ cạnh tranh.**

## 53. Tổng kết

Những nguyên tắc cần nhớ:

1. **Ghi database rồi xóa cache** thường hợp lý hơn xóa cache trước commit, nhưng vẫn có **commit→invalidation window** và **stale fill sau invalidation**.
2. **Đọc cũ điền lại cache sau DEL** là một race độc lập với thứ tự thao tác bên writer; cache-aside không thể bỏ qua reader.
3. **DB-first UPDATE cache** cũng có race khi nhiều writers và Redis operations đến lệch thứ tự; dùng atomic version guard để tránh stale overwrite.
4. **Version phải đến từ authoritative commit**, không dùng wall-clock cục bộ làm tổng thứ tự. Delete/recreate cần lifecycle generation phù hợp.
5. **Version fence** có thể bác stale fill **sau khi fence đã được áp dụng**, nhưng chưa loại bỏ khoảng trước khi event tới cache và có giả định về retention/eviction.
6. **TTL và delayed double-delete là biện pháp giới hạn rủi ro**, không phải transaction nguyên tử hay chứng minh linearizability.
7. **Outbox/CDC giúp invalidation được phát lại sau crash**, nhưng vẫn có duplicate, out-of-order và propagation lag; consumer phải idempotent và có reconciliation.
8. **Cache nhiều tầng và query caches làm phạm vi invalidation lớn hơn**; phải xét phụ thuộc, before/after fields và tenant authorization.
9. **Single-flight, backpressure và TTL jitter bảo vệ tải** sau invalidation, nhưng không tự giữ consistency.
10. **Dữ liệu quan trọng phải quyết định tại nguồn có thẩm quyền** bằng conditional write/transaction; cache là representation dẫn xuất theo freshness contract.

**Nguyên tắc thực hành:** khi review một luồng “ghi DB rồi xóa/cập nhật Redis”, hãy dựng ít nhất ba lịch: **reader đọc cũ rồi fill sau DEL; hai writers cập nhật cache đảo thứ tự; và app crash ngay sau DB COMMIT**. Nếu thiết kế giải thích được hành vi của cả ba lịch, nêu rõ giới hạn stale được phép và có đường phục hồi kiểm chứng được, lúc ấy mới có cơ sở để nói cache đang được quản lý đúng theo hợp đồng của hệ NoSQL.
