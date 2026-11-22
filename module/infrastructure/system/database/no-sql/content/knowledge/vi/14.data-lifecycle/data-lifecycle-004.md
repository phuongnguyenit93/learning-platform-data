# Phân biệt hết hạn dữ liệu với loại bỏ khỏi bộ nhớ đệm

Trong các hệ thống NoSQL, đặc biệt khi dùng Redis làm bộ nhớ đệm (*cache*), hai hiện tượng rất dễ bị đánh đồng là **hết hạn dữ liệu** (*expiration*) và **loại bỏ khỏi bộ nhớ đệm** (*eviction*). Cả hai có thể dẫn đến kết quả giống nhau khi ứng dụng đọc một khóa: **không tìm thấy giá trị trong cache**. Nhưng **nguyên nhân, thời điểm, điều kiện kích hoạt và ý nghĩa nghiệp vụ** của chúng khác nhau.

Giả sử một ứng dụng thương mại điện tử lưu thông tin sản phẩm vào cache trong 10 phút:

~~~text
cache:product:P1001
  value = {"name":"Bút mực","priceVnd":25000}
  TTL = 600 giây
~~~

Có hai tình huống:

- Sau 10 phút, khóa **hết hạn** vì thời gian sống đã kết thúc, dù máy chủ cache còn rất nhiều RAM.
- Chỉ 30 giây sau khi ghi, cache **loại bỏ khóa** do thiếu bộ nhớ và chính sách eviction quyết định nhường chỗ cho dữ liệu khác, dù TTL vẫn còn hơn 9 phút.

Ứng dụng đều phải xử lý **cache miss**. Tuy nhiên, nếu hiểu lầm TTL là cam kết “giá trị sẽ nằm trong cache đủ 10 phút”, hoặc coi eviction là cơ chế bảo đảm xóa dữ liệu sau một hạn định, hệ thống có thể gặp lỗi hiệu năng, độ mới dữ liệu, bảo mật và thiết kế vòng đời.

Bài học đặt hai cơ chế vào ngữ cảnh **vòng đời dữ liệu** của NoSQL: phân biệt cache với nguồn dữ liệu chính, mô tả hành vi bằng ví dụ Redis, đánh giá ảnh hưởng tới ứng dụng và giải thích cách đo lường, xử lý các trường hợp biên.

## 1. Bốn khái niệm không nên gộp làm một

Trước khi đi sâu, cần tách bạch ít nhất bốn thao tác:

| Khái niệm | Vì sao giá trị không còn sử dụng được? | Điều kiện kích hoạt chính | Đối tượng quyết định |
| --- | --- | --- | --- |
| **Expiration — hết hạn** | Đã tới thời điểm hết hạn được gắn với dữ liệu | Thời gian/TTL hoặc thời điểm hết hạn | Quy tắc TTL và đồng hồ của hệ thống |
| **Eviction — loại bỏ khỏi cache** | Cache cần giải phóng tài nguyên hoặc áp dụng chính sách thay thế | Áp lực bộ nhớ/dung lượng và chính sách eviction | Cache engine và cấu hình tài nguyên |
| **Invalidation — vô hiệu hóa cache** | Ứng dụng biết dữ liệu cache không còn phù hợp | Dữ liệu nguồn thay đổi, một sự kiện hoặc yêu cầu nghiệp vụ | Ứng dụng hoặc quy trình đồng bộ |
| **Explicit deletion — xóa chủ động** | Có yêu cầu xóa khóa/bản ghi | Lệnh `DEL`, thao tác quản trị, nghiệp vụ | Client/DBMS có quyền |

**Expiration** trả lời câu hỏi: *giá trị này được phép sống trong cache bao lâu theo chính sách thời gian?*

**Eviction** trả lời câu hỏi: *khi dung lượng bị hạn chế, nên giữ giá trị nào và loại giá trị nào để nhường chỗ?*

**Invalidation** trả lời câu hỏi: *khi dữ liệu nguồn đã đổi, bản cache cũ có còn hợp lệ không?*

**Deletion** trả lời câu hỏi: *ai chủ động yêu cầu loại bỏ một mục dữ liệu?*

Một bản ghi có thể được xóa vì bất kỳ nguyên nhân nào trên. Chỉ nhìn vào kết quả `GET` trả về không tồn tại, ứng dụng thường **không biết chắc nguyên nhân** nếu không có thêm số liệu hoặc nhật ký phù hợp.

### “Không tồn tại trong cache” không đồng nghĩa “dữ liệu nghiệp vụ đã bị xóa”

Giả sử:

~~~text
Database chính:
  products/P1001 → {"name":"Bút mực","priceVnd":25000}

Cache:
  cache:product:P1001 → bản sao của products/P1001
~~~

Nếu cache mất khóa `cache:product:P1001` vì expiration hoặc eviction, sản phẩm `P1001` **vẫn có thể tồn tại trong database chính**. Ứng dụng cần đọc lại từ nguồn có thẩm quyền rồi nạp cache nếu phù hợp.

Ngược lại, nếu bản ghi nguồn đã bị xóa mà cache chưa bị invalidation/hết hạn, cache **có thể vẫn chứa bản sao cũ**. Vì thế **TTL và eviction không thay thế chính sách đồng bộ với dữ liệu nguồn**.

## 2. Expiration: thời gian sống của một khóa

**TTL** (*time to live*) là khoảng thời gian một giá trị được phép tồn tại theo một chính sách thời gian. Trong Redis, ứng dụng có thể đặt TTL bằng số giây hoặc mili giây, hoặc đặt thời điểm hết hạn tuyệt đối bằng những lệnh phù hợp.

Ví dụ:

~~~redis
SET cache:product:P1001 '{"name":"Bút mực","priceVnd":25000}' EX 600
GET cache:product:P1001
TTL cache:product:P1001
~~~

Lệnh `SET ... EX 600` ghi một Redis string và gắn hạn sử dụng **600 giây** tính từ thời điểm Redis xử lý lệnh. Nếu không có thao tác thay đổi thời hạn và không có eviction/xóa khác, sau khi tới hạn, giá trị **không còn được xem là tồn tại khi truy cập theo ngữ nghĩa Redis**.

### Đọc TTL trong Redis

~~~redis
TTL cache:product:P1001
PTTL cache:product:P1001
~~~

- `TTL` trả thời gian còn lại tính bằng **giây**.
- `PTTL` trả thời gian còn lại tính bằng **mili giây**.
- Kết quả `-1`: khóa **có tồn tại nhưng không có expiration được đặt**.
- Kết quả `-2`: khóa **không tồn tại** tại thời điểm kiểm tra.

Ví dụ:

| Trạng thái khóa | `TTL key` có thể trả về |
| --- | --- |
| Còn khoảng 120 giây | Một số gần 120 |
| Có tồn tại, không đặt hạn | `-1` |
| Đã hết hạn hoặc đã bị xóa/evict | `-2` |

**Không thể dựa vào `TTL = -2` để khẳng định nguyên nhân là hết hạn.** Khóa cũng có thể chưa từng được tạo, đã bị xóa chủ động, bị eviction hoặc biến mất vì lý do khác.

### Thời hạn tương đối và thời điểm hết hạn tuyệt đối

Redis hỗ trợ các cách đặt hạn:

~~~redis
EXPIRE cache:product:P1001 300
PEXPIRE cache:product:P1001 300000
~~~

Hai lệnh trên đặt thời gian sống tương đối, tương ứng 300 giây hoặc 300.000 mili giây tính tại thời điểm xử lý.

Redis cũng có `EXPIREAT`/`PEXPIREAT` để đặt thời điểm hết hạn theo Unix time. Một hệ thống có thể cần thời hạn tuyệt đối, chẳng hạn **mã xác nhận chỉ hợp lệ đến 10:00 UTC**, không phải “10 phút kể từ lần đọc gần nhất”.

Nếu dùng deadline nghiệp vụ tuyệt đối, cần thống nhất cách tính, timezone và đồng hồ. Không dùng TTL tương đối tùy tiện nếu việc tạo lại khóa có thể vô tình kéo dài quyền sử dụng vượt deadline ban đầu.

## 3. TTL được áp dụng thế nào khi ứng dụng cập nhật?

Một điểm dễ sai là **TTL không nhất thiết được giữ khi giá trị được ghi lại**.

Ví dụ trong Redis:

~~~redis
SET cache:product:P1001 '{"priceVnd":25000}' EX 600
TTL cache:product:P1001

SET cache:product:P1001 '{"priceVnd":26000}'
TTL cache:product:P1001
~~~

Sau lệnh `SET` thứ hai, theo hành vi Redis thông thường, TTL cũ **bị xóa**; `TTL` có thể trả `-1` nếu khóa còn tồn tại. Kết quả là một mục dữ liệu vốn chỉ dự định lưu tạm có thể tồn tại không giới hạn thời gian do ứng dụng quên đặt lại TTL.

Nếu muốn ghi lại giá trị mà **giữ TTL hiện có**, Redis cung cấp tùy chọn:

~~~redis
SET cache:product:P1001 '{"priceVnd":26000}' KEEPTTL
~~~

Nếu muốn **gia hạn từ thời điểm ghi**, đặt thời hạn mới:

~~~redis
SET cache:product:P1001 '{"priceVnd":26000}' EX 600
~~~

Hai hành vi này không tương đương. `KEEPTTL` giữ deadline đang có; `EX 600` thường đặt lại deadline 600 giây từ lần ghi hiện tại.

### Lệnh cập nhật trường có giữ TTL không?

Trong Redis, những lệnh thay đổi giá trị **mà không thay thế toàn bộ key** như `HSET` trên một Redis hash thường **không tự làm mất expiration đang gắn với key**:

~~~redis
HSET cache:user:U42 name "An" city "Da Nang"
EXPIRE cache:user:U42 300

HSET cache:user:U42 city "Ha Noi"
TTL cache:user:U42
~~~

Lệnh `HSET` không tự đặt lại thời gian sống thành 300 giây. TTL còn lại vẫn tiếp tục giảm nếu ứng dụng không chủ động gia hạn.

**Kết luận:** phải đọc đúng ngữ nghĩa của **từng lệnh ghi**. Không thể suy ra rằng “mọi lần sửa đều reset TTL” hoặc “mọi lần sửa đều giữ TTL”.

### Cố ý xóa hạn của khóa

~~~redis
PERSIST cache:product:P1001
~~~

`PERSIST` bỏ thời hạn hết hạn của khóa hiện có, khiến khóa không còn bị expiration do TTL cũ. Nó **không cam kết khóa sẽ luôn tồn tại**, vì key vẫn có thể bị eviction, bị xóa chủ động hoặc mất khi hệ thống gặp sự cố tùy cấu hình.

## 4. Expiration không nhất thiết xóa vật lý đúng một mili giây

Khi TTL kết thúc, hai điều cần phân biệt:

1. **Hết hạn về mặt logic:** DBMS coi khóa đã hết hạn, nên nó không nên được trả về như một giá trị còn hiệu lực qua đường truy cập thông thường.
2. **Thu hồi tài nguyên vật lý:** bộ nhớ liên quan được giải phóng khi DBMS phát hiện và dọn mục hết hạn theo cơ chế của nó.

Redis sử dụng các cơ chế **lazy expiration** và **active expiration**:

- **Lazy expiration:** khi một khóa được truy cập, Redis có thể phát hiện khóa đã hết hạn và xử lý nó.
- **Active expiration:** Redis chủ động kiểm tra và dọn một số khóa hết hạn mà không cần ứng dụng đọc chúng trước.

Vì vậy, **một khóa hết hạn không nhất thiết bị giải phóng vật lý đúng tại thời điểm deadline với độ chính xác tuyệt đối**. Nhưng điều này **không có nghĩa** ứng dụng được đọc giá trị đã quá hạn chỉ vì byte dữ liệu còn nằm trong bộ nhớ một thời gian.

### Minh họa theo dòng thời gian

~~~text
10:00:00  SET key value EX 600
          TTL logic kết thúc lúc khoảng 10:10:00

10:03:00  GET key
          → Có thể thấy value nếu chưa bị xóa/evict

10:10:00  Deadline expiration
          → Key hết hiệu lực theo TTL

10:10:01  GET key
          → Cache miss; Redis xử lý key đã hết hạn nếu cần

Sau đó   Bộ nhớ đã giữ key được thu hồi theo cơ chế dọn
~~~

Trong các DBMS khác, **expiration có thể được thực hiện bất đồng bộ với độ trễ lớn hơn**. Ví dụ một tính năng TTL ở database chính có thể đánh dấu bản ghi đủ điều kiện để xóa, nhưng job xóa vật lý chạy sau đó. Vì thế không suy luận chung rằng tất cả tính năng có tên TTL có cùng độ chính xác hay bảo đảm xóa ngay như cách đọc một khóa Redis.

## 5. Eviction: loại bỏ khi cần giải phóng bộ nhớ

**Eviction** là chính sách quản lý tài nguyên cache. Khi tổng dung lượng các key tiến đến giới hạn được cấu hình, cache có thể cần chọn một số key để loại bỏ và nhường chỗ cho ghi mới.

Ví dụ:

~~~text
Cache maxmemory: giới hạn được cấu hình

Tại 10:00:
  K1: product P1001, TTL còn 20 phút
  K2: product P1002, TTL còn 12 phút
  K3: category books, TTL còn 3 phút

Tại 10:01:
  Lưu thêm nhiều key, bộ nhớ không còn đủ
  → Chính sách eviction chọn một hoặc nhiều key

K1 có thể bị evict lúc 10:01
dù deadline expiration của K1 còn rất xa.
~~~

Một key được gắn TTL 20 phút **không có cam kết sẽ hiện diện đủ 20 phút**. TTL thường tạo **giới hạn thời gian sống logic**, còn eviction có thể kết thúc sự hiện diện **sớm hơn**.

### Eviction không cần biết dữ liệu nguồn đã đổi

Eviction thường dựa vào tài nguyên và chính sách lựa chọn key; nó không biết nghiệp vụ:

- Giá sản phẩm vừa tăng hay giảm.
- Người dùng vừa đăng xuất hay chưa.
- Một giỏ hàng đang trong quá trình thanh toán.
- Sự kiện cập nhật nào chưa đồng bộ.

Vì thế **eviction không phải cơ chế invalidation theo nghiệp vụ**. Nó có thể vô tình loại bỏ một bản cache đã cũ, nhưng không có bảo đảm rằng mọi bản cache cũ sẽ bị loại bỏ đúng lúc.

## 6. Chính sách eviction trong Redis

Redis có `maxmemory` để giới hạn mức sử dụng bộ nhớ theo cơ chế của Redis. Khi cần giải phóng dung lượng để thực hiện thao tác ghi, Redis có thể áp dụng **maxmemory policy** đã cấu hình.

Một số chính sách thường gặp:

| Policy Redis | Nhóm key có thể bị chọn | Tiêu chí lựa chọn khái quát |
| --- | --- | --- |
| `noeviction` | Không chủ động evict để nhường bộ nhớ theo policy | Các thao tác cần thêm bộ nhớ có thể bị từ chối khi vượt giới hạn |
| `allkeys-lru` | Các key nói chung | Ưu tiên loại những key được ước lượng là ít được truy cập gần đây |
| `allkeys-lfu` | Các key nói chung | Ưu tiên loại những key có tần suất truy cập thấp theo cơ chế xấp xỉ |
| `allkeys-random` | Các key nói chung | Chọn ngẫu nhiên |
| `volatile-lru` | Chỉ những key có đặt expiration | Lựa theo mức ít được truy cập gần đây |
| `volatile-lfu` | Chỉ những key có đặt expiration | Lựa theo tần suất truy cập |
| `volatile-random` | Chỉ những key có đặt expiration | Chọn ngẫu nhiên trong tập có TTL |
| `volatile-ttl` | Chỉ những key có đặt expiration | Ưu tiên key có TTL còn lại ngắn hơn |

Tên policy trong bảng là tên của Redis; **không phải mọi NoSQL DBMS đều có các lựa chọn này**. Cơ chế LRU/LFU trong Redis sử dụng những kỹ thuật xấp xỉ và metadata phù hợp với hiệu năng, không nên hiểu là luôn chọn đúng key ít dùng nhất theo thứ tự tuyệt đối toàn cụm.

### Sự khác biệt giữa allkeys và volatile

Giả sử:

~~~text
cache:product:P1001   → TTL = 300 giây
cache:product:P1002   → TTL = 300 giây
cache:config:global   → không có TTL
~~~

- Với policy **`allkeys-lru`**, cả ba key đều có thể là ứng viên eviction nếu chính sách coi chúng là ít được dùng.
- Với policy **`volatile-lru`**, chỉ hai key có TTL mới là ứng viên theo policy; `cache:config:global` không bị chọn bởi chính sách đó chỉ vì thiếu bộ nhớ.
- Với **`volatile-ttl`**, Redis ưu tiên key có thời gian còn lại ngắn hơn **trong số các key có expiration**.

**Cẩn thận:** nếu chọn một policy `volatile-*` nhưng gần như không có key nào đặt TTL, Redis có thể không tìm được đủ ứng viên eviction; các lệnh ghi có thể gặp lỗi khi bộ nhớ chạm giới hạn. Không thể mặc định “volatile-lru sẽ tự giải phóng mọi thứ khi RAM đầy”.

### `noeviction` có nghĩa là gì?

`noeviction` có nghĩa Redis không dùng policy eviction để loại bỏ key nhằm đáp ứng các thao tác cần thêm bộ nhớ. Khi chạm giới hạn, những lệnh có nhu cầu bộ nhớ phù hợp có thể bị từ chối. Điều này **không tắt TTL expiration**: key hết hạn vẫn có thể biến mất.

Chính sách này đôi khi được cân nhắc khi Redis chứa dữ liệu không muốn tự động đẩy ra vì áp lực bộ nhớ. Tuy nhiên, **không bị eviction cũng không đồng nghĩa dữ liệu được lưu bền vững như database có durability đầy đủ**. Persistence, replication, backup, failover và xử lý hết hạn là các chiều bảo đảm khác nhau.

### Xem cấu hình mà không thay đổi production

Có thể kiểm tra trong môi trường được phép:

~~~redis
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
INFO memory
~~~

Các lệnh trả cấu hình và số liệu hiện tại theo quyền của tài khoản. Đừng thử hạ `maxmemory` hoặc đổi policy trên một instance Redis production chỉ để quan sát eviction: việc đó có thể làm mất cache hàng loạt, tăng cache miss và tạo tải lớn lên DB chính.

## 7. So sánh expiration và eviction theo dòng thời gian

Xét khóa `cache:product:P1001` được ghi lúc 09:00 với TTL 30 phút:

~~~text
09:00               09:08                  09:30
  │                   │                      │
  │ SET EX 1800       │ thiếu RAM           │ TTL deadline
  ▼                   ▼                      ▼
┌─────────────────────────────────────────────────┐
│ Giá trị có thể sử dụng khi còn tồn tại          │
└─────────────────────────────────────────────────┘

Kịch bản A — không bị eviction:
  09:00 ────────────────────────── 09:30 [EXPIRED]

Kịch bản B — bị eviction:
  09:00 ─────────── 09:08 [EVICTED]
  TTL gốc chưa tới hạn nhưng giá trị đã biến mất.

Kịch bản C — nguồn dữ liệu đổi và có invalidation:
  09:00 ─── 09:04 [INVALIDATED]
  Key bị xóa/đánh dấu không dùng vì bản sao đã cũ.
~~~

| Câu hỏi | Expiration | Eviction |
| --- | --- | --- |
| Phụ thuộc thời gian? | Có, theo TTL/deadline | Không nhất thiết; chủ yếu theo áp lực tài nguyên |
| Có thể xảy ra khi RAM còn dư? | Có | Thông thường không vì áp lực `maxmemory`, trừ cơ chế cache khác |
| Có thể xảy ra trước TTL? | Không phải expiration của deadline đó | Có |
| Có thể xảy ra khi key không có TTL? | Không theo TTL của key | Có nếu policy như `allkeys-*` cho phép |
| Có đảm bảo cache luôn giữ key tới TTL? | Không | Không |
| Có xóa bản ghi ở DB nguồn? | Không, nếu TTL chỉ của cache | Không, nếu eviction chỉ ở cache |
| Có đồng nghĩa dữ liệu đã thay đổi ở DB nguồn? | Không | Không |
| Có đủ làm cơ chế xóa dữ liệu vì pháp lý/bảo mật? | Thường không | Không |

**Cùng kết quả cache miss không có nghĩa cùng nguyên nhân hay cùng chính sách.**

## 8. Cache-aside: ứng dụng phải hoạt động khi cache miss

Mẫu phổ biến là **cache-aside** (*lazy loading*):

~~~text
                    GET product
                        │
                        ▼
                  ┌───────────┐
                  │ Redis GET │
                  └─────┬─────┘
                        │
                  ┌─────┴─────┐
                  │           │
                HIT          MISS
                  │           │
                  ▼           ▼
              Trả cache   Đọc DB nguồn
                              │
                       ┌──────┴─────┐
                       │            │
                     Có dữ liệu     Không có
                       │            │
                       ▼            ▼
                   SET cache       Trả not-found
                    kèm TTL
                       │
                       ▼
                   Trả kết quả
~~~

Ví dụ pseudocode:

~~~javascript
async function getProduct(productId) {
  const key = "cache:product:" + productId;
  const cached = await redis.get(key);

  if (cached !== null) {
    return JSON.parse(cached);
  }

  const product = await productRepository.findById(productId);
  if (product === null) {
    return null;
  }

  await redis.set(key, JSON.stringify(product), {
    EX: 300
  });
  return product;
}
~~~

Đây là **mẫu minh họa kiểu API của Redis client cho Node.js**, không phải ứng dụng production hoàn chỉnh. Phải xử lý lỗi cache, xác thực quyền truy cập, JSON lỗi, kiểm soát kích thước payload, dữ liệu nguồn bị xóa và chiến lược khi Redis không sẵn sàng.

### Điều quan trọng nhất của cache-aside

Ứng dụng **không được giả định key luôn tồn tại trong 300 giây**. Bất kỳ lần đọc nào cũng có thể gặp miss vì expiration, eviction, invalidation, khởi động lại, xóa thủ công hoặc một lý do khác.

Nếu cache chỉ là lớp tăng tốc, **cache miss là tình huống bình thường, không phải lỗi nghiệp vụ**. Nguồn có thẩm quyền phải có cách được truy cập khi cache không có giá trị.

### Cache miss và source-of-truth

Khi cache miss:

1. Truy vấn DB nguồn theo key hoặc index phù hợp.
2. Áp dụng cùng quy tắc quyền và validation như khi không có cache.
3. Nếu có dữ liệu, nạp lại cache với TTL/phiên bản thích hợp.
4. Nếu không có, trả not-found hoặc dùng **negative caching** có kiểm soát.
5. Không tự kết luận “đã bị xóa khỏi nghiệp vụ” chỉ vì cache miss.

Đây là lý do cần xác định **cache chứa bản sao có thể tái tạo** hay đang bị dùng sai như nơi lưu dữ liệu duy nhất.

## 9. Cache hit không bảo đảm dữ liệu còn mới

TTL giới hạn thời gian tồn tại **tính từ một mốc**, không tự kiểm tra nội dung cache còn khớp với DB nguồn hay không.

Ví dụ:

~~~text
10:00  Cache giá sản phẩm P1001 = 25.000 VND, TTL 600 giây
10:02  Database nguồn đổi giá thành 27.000 VND
10:03  Cache chưa hết TTL, chưa bị invalidation
       GET cache vẫn có thể trả giá 25.000 VND
~~~

Đây là hiện tượng **stale cache**. Nó khác eviction:

- **Eviction:** dữ liệu biến mất dù có thể còn mới.
- **Stale cache:** dữ liệu vẫn tồn tại nhưng có thể đã lỗi thời.

Thiết kế phải trả lời:

- Mức độ cũ tối đa chấp nhận được là bao nhiêu?
- Có cần invalidation ngay khi dữ liệu nguồn thay đổi?
- Nếu cập nhật cache thất bại, hệ thống có được trả dữ liệu cũ tiếp không?
- Truy vấn nào phải đọc nguồn chính thay vì cache?

### TTL không phải bảo đảm nhất quán mạnh

Giả sử `TTL = 60 giây`. Nhiều người kỳ vọng độ trễ đồng bộ tối đa là 60 giây, nhưng điều đó chỉ gần đúng khi **có những giả định bổ sung**: key được tạo đúng sau lần đọc nguồn gần nhất, không có việc gia hạn TTL trên payload cũ, không dùng stale-while-revalidate vượt hạn, và không có bản cache ở nhiều tầng với thời hạn khác.

Ví dụ nếu một service cứ mỗi phút dùng `EXPIRE key 60` để làm mới TTL của giá trị cũ mà **không đọc lại nguồn**, bản cache có thể tồn tại lỗi thời mãi.

Muốn cam kết độ mới, cần phát biểu thành **freshness policy** rõ ràng, chẳng hạn giá trị phải được xác minh hoặc nạp mới ít nhất một lần trong khoảng phù hợp, hoặc phải có invalidation đáng tin cậy khi nguồn cập nhật.

### Invalidation sau ghi

Một mẫu thường gặp:

~~~text
UPDATE product in authoritative database
         │
         ▼
Commit thành công
         │
         ▼
DEL cache:product:P1001
         │
         ▼
Lần đọc kế tiếp → cache miss → nạp mới
~~~

Mẫu này giảm khả năng giữ giá cũ, nhưng vẫn có **cuộc đua** nếu một luồng đang nạp cache từ dữ liệu cũ trong lúc luồng khác cập nhật DB và invalidation. Ví dụ reader đọc DB trước khi writer commit, writer commit rồi xóa cache, sau đó reader ghi bản cũ vào cache. Khi cần bảo đảm mạnh, phải thiết kế phiên bản dữ liệu, điều kiện ghi cache, thứ tự sự kiện hoặc đường đọc nguồn có thẩm quyền phù hợp.

## 10. Cache stampede khi nhiều key hết hạn cùng lúc

Expiration và eviction đều có thể tạo **cache miss**, nhưng một đợt expiration đồng loạt có thể gây **cache stampede**:

~~~text
11:00  20.000 key phổ biến cùng hết TTL
11:00  Nhiều request liên tục truy cập
       → hàng nghìn cache miss
       → hàng nghìn truy vấn DB nguồn
       → DB nguồn quá tải
~~~

Eviction cũng có thể gây ra tình huống tương tự nếu một lượng lớn key nóng bị loại bỏ vì áp lực bộ nhớ hoặc thay đổi cấu hình.

### Những cách giảm stampede

**1. TTL jitter — tạo thời hạn không đồng loạt**

Thay vì mọi key có chính xác 300 giây:

~~~text
TTL = 300 + random(0..60) giây
~~~

Việc phân tán thời hạn có thể giảm số key hết hạn cùng thời điểm. Tuy nhiên, nếu nghiệp vụ có **deadline cứng**, không được cộng jitter khiến giá trị sống quá hạn cho phép; khi đó dùng jitter giảm xuống hoặc quản lý deadline riêng.

**2. Single-flight/request coalescing**

Trong một instance ứng dụng, nhiều request cùng đọc một key bị miss có thể dùng chung một thao tác nạp nguồn thay vì đồng thời gọi DB. Trong hệ nhiều instance, có thể dùng lock/lease phân tán với timeout và token an toàn.

**3. Background refresh**

Với dữ liệu rất nóng, chủ động nạp lại trước khi hết TTL. Cần tránh cứ gia hạn TTL của payload cũ mà không lấy giá trị mới.

**4. Stale-while-revalidate (SWR)**

Trong các trường hợp nghiệp vụ chấp nhận, tạm phục vụ dữ liệu cũ trong một khoảng grace rồi refresh ở nền. Nhưng SWR **cố ý cho phép stale**, vì vậy không nên dùng bừa bãi cho số dư, tồn kho có điều kiện hay xác nhận thanh toán.

**5. Giới hạn tải nguồn và fallback**

Khi cache miss tăng đột biến, cần rate limit, backpressure, circuit breaker hoặc kết quả suy giảm có kiểm soát tùy nghiệp vụ. Đừng để bộ nhớ đệm vốn để giảm tải trở thành nguyên nhân làm sập DB chính khi key bị loại bỏ hàng loạt.

## 11. Negative caching: cache cả kết quả “không có”

Một sản phẩm không tồn tại có thể bị truy vấn lặp lại bởi bot hoặc client gửi sai ID. Nếu mỗi lần đều truy vấn nguồn, hệ thống vẫn chịu tải cao dù key không có giá trị.

**Negative caching** lưu tạm kết quả “không tìm thấy”:

~~~text
GET product P9999
  → DB nguồn: không tồn tại
  → Cache: NOT_FOUND với TTL 15 giây

Lần truy vấn tiếp:
  → cache trả NOT_FOUND mà không hỏi DB
~~~

Ví dụ quy ước key:

~~~redis
SET cache:product:P9999:missing "1" EX 15
~~~

Lúc áp dụng, phải phân biệt:

- **Cache key bị miss**: chưa biết nguồn có tồn tại không.
- **Cache chứa dấu hiệu NOT_FOUND**: lần tra cứu nguồn gần đây không thấy đối tượng.
- **Nguồn thực sự xóa đối tượng**: là trạng thái nghiệp vụ cần xác minh ở nơi có thẩm quyền.

Nếu sản phẩm P9999 vừa được tạo sau lúc negative cache ghi, ứng dụng có thể trả “không tìm thấy” trong một khoảng ngắn. Vì vậy negative TTL thường được chọn thận trọng và cần invalidation khi có sự kiện tạo mới nếu yêu cầu nghiệp vụ cần thấy ngay.

## 12. Expiration và eviction tác động thế nào tới dữ liệu phiên đăng nhập?

Không nên áp dụng cách nghĩ “mọi thứ trong Redis đều chỉ là cache” cho mọi ứng dụng. Redis đôi khi được dùng để lưu **session**, **mã xác minh**, **rate-limit counter** hoặc những trạng thái tạm có ý nghĩa nghiệp vụ.

Ví dụ:

~~~redis
SET session:S-123 '{"userId":"U42"}' EX 1800
~~~

Nếu session bị expiration sau 30 phút, ứng dụng có thể coi phiên không còn hiệu lực. Nhưng nếu session bị evict sau 2 phút vì thiếu RAM, người dùng bị đăng xuất sớm dù không vi phạm chính sách thời hạn.

### Hết hạn session khác mất session do eviction

| Tình huống | Nguyên nhân | Ảnh hưởng người dùng |
| --- | --- | --- |
| Session hết hạn theo thời gian | Deadline/TTL | Đăng nhập lại theo chính sách |
| Session bị evict sớm | Áp lực bộ nhớ và eviction policy | Đăng xuất bất ngờ |
| Session bị revoke | Yêu cầu đăng xuất, khóa tài khoản, thay đổi quyền | Không được tiếp tục sử dụng |
| Redis gặp sự cố và mất dữ liệu | Durability/availability theo cấu hình | Có thể mất session hàng loạt |

Nếu session là trạng thái quan trọng, cần quyết định **có được phép mất sớm hay không**, cơ chế persistence/replication, cách xử lý Redis unavailable và chính sách cache eviction. Không thể chỉ chọn TTL 30 phút rồi tuyên bố người dùng chắc chắn có phiên trong 30 phút.

### TTL không thay thế thu hồi quyền ngay

Ví dụ khóa tài khoản lúc 10:00 nhưng token/session có TTL đến 10:30. Nếu chỉ trông chờ TTL tự hết, người dùng có thể tiếp tục sử dụng quyền cũ trong khoảng đó nếu hệ thống không có bước kiểm tra khác.

Với yêu cầu **revoke ngay**, có thể cần xóa session, kiểm tra trạng thái tài khoản ở nguồn có thẩm quyền, token revocation hoặc phiên bản quyền. Eviction là một sự kiện phụ thuộc tài nguyên, tuyệt đối không dùng làm cơ chế thu hồi quyền có bảo đảm.

## 13. Expiration ở cache khác TTL của database chính

Thuật ngữ TTL có thể xuất hiện ở nhiều nơi nhưng mang những đặc tính vận hành khác nhau.

### TTL của cache

Mục đích thường là giới hạn tuổi của **bản sao dùng để tăng tốc**:

~~~text
Authoritative products collection
       │
       ▼
Redis cache:product:P1001
  TTL 5 phút
~~~

Khi key cache hết hạn, nguồn chính vẫn tồn tại; ứng dụng có thể nạp lại.

### TTL của bản ghi nguồn trong DBMS

Một database có thể hỗ trợ tự xóa dữ liệu theo hạn, ví dụ các sự kiện tạm, log, kết quả trung gian hoặc dữ liệu có vòng đời cố định. Ở đây expiration là một phần của **chính sách tồn tại của bản ghi**, không đơn thuần là cache optimization.

Một số ví dụ về khác biệt sản phẩm:

- Với Redis, key expiration ảnh hưởng trực tiếp đến việc truy cập khóa theo ngữ nghĩa Redis; dọn vật lý có thể dùng lazy/active expiration.
- Với MongoDB TTL index, tác vụ xóa của DBMS chạy theo cơ chế nền, không nên kỳ vọng một bản ghi được xóa đúng từng mili giây ngay tại deadline.
- Với DynamoDB TTL, thuộc tính thời gian xác định mục đủ điều kiện hết hạn, còn việc xóa vật lý là bất đồng bộ; truy vấn ứng dụng cần tính đến bản ghi đủ hạn nhưng chưa bị dọn nếu nghiệp vụ yêu cầu.
- Với Cassandra, TTL khi hết hạn liên quan đến tombstone và compaction; đó không phải cache eviction.

Những mô tả trên nhằm nhấn mạnh rằng **TTL là khái niệm thời gian, nhưng thời điểm và cơ chế thu hồi vật lý tùy DBMS**. Không được suy ra một SLA xóa dữ liệu chung chỉ từ tên tính năng “TTL”.

### Hết hạn dữ liệu nguồn không đồng nghĩa có thể quên backup

Nếu yêu cầu nghiệp vụ là “dữ liệu phải được xóa sau X ngày”, cần xác định rõ:

- Dữ liệu có ở **cache**, DB chính, replica, search index, warehouse, log hay file export không?
- Có backup hoặc snapshot chứa bản sao không, và chính sách xóa/hết hạn chúng là gì?
- Nếu phải chứng minh xóa, hệ thống có audit và đối soát không?
- Một bản ghi đã đủ hạn nhưng vẫn chưa bị dọn vật lý có thể được đọc bởi một API không?

**Eviction của cache hoàn toàn không thay thế retention/compliance**, vì eviction dựa theo áp lực tài nguyên, không theo deadline pháp lý và không xóa mọi bản sao.

## 14. Đo lường expiration và eviction bằng Redis

Khi cache miss tăng, cần biết do **key hết TTL**, **key bị eviction** hay một nguyên nhân khác.

Redis cung cấp thông tin thống kê qua:

~~~redis
INFO stats
INFO memory
CONFIG GET maxmemory-policy
~~~

Một số chỉ số thường hữu ích:

| Chỉ số/thuộc tính | Diễn giải | Câu hỏi đặt ra |
| --- | --- | --- |
| `expired_keys` | Số key đã bị xử lý hết hạn, tính lũy kế theo thống kê Redis | Có nhiều khóa đang hết TTL không? |
| `evicted_keys` | Số key bị eviction theo thống kê Redis | Cache có đang bị loại bỏ do thiếu bộ nhớ không? |
| `keyspace_hits` | Số lần tìm key thành công ở cache theo loại thống kê Redis | Cache có phục vụ nhiều lượt đọc không? |
| `keyspace_misses` | Số lần tìm key không thành công | Miss có tăng đột ngột không? |
| `used_memory` | Bộ nhớ Redis báo cáo đang sử dụng | Dung lượng sử dụng có gần giới hạn không? |
| `maxmemory` | Giới hạn bộ nhớ đã cấu hình | Áp lực bộ nhớ có khả năng gây eviction không? |
| `maxmemory_policy` | Chính sách chọn key hoặc từ chối ghi | Những key nào là ứng viên eviction? |

Các counter như `expired_keys` và `evicted_keys` là **giá trị lũy kế**, không phải tốc độ/giây. Khi giám sát, thường quan tâm **mức tăng trong một khoảng thời gian** (rate) và phải hiểu khả năng reset sau restart.

### Ví dụ đọc số liệu đúng cách

Giả sử lúc 10:00:

~~~text
expired_keys = 100000
evicted_keys = 200
~~~

Lúc 10:05:

~~~text
expired_keys = 105000
evicted_keys = 10200
~~~

Trong 5 phút:

~~~text
Expired: +5.000 key
Evicted: +10.000 key
~~~

Đây là dấu hiệu **eviction đang tăng mạnh** cần điều tra `maxmemory`, chính sách và phân bố key nóng. Tuy nhiên, không thể suy ra chính xác một request cache miss nào do eviction chỉ từ hai số tổng. Cũng cần so với `keyspace_misses`, tải DB nguồn, cache hit rate và những thay đổi cấu hình/deployment.

### Đừng đánh giá cache chỉ bằng hit rate

Nếu cache có 99% hit nhưng 1% miss xảy ra với những yêu cầu rất đắt, DB nguồn vẫn có thể quá tải. Nếu cache có 70% hit với các truy vấn rẻ, hệ thống có thể vận hành ổn.

Nên đo **theo nhóm key hoặc access pattern**:

- Tỷ lệ hit/miss và tần suất request.
- P95/P99 latency của cache hit và cache miss.
- Độ trễ, CPU và I/O của nguồn dữ liệu khi cache miss.
- Mức tăng của expiration/eviction.
- Kích thước bộ nhớ, dung lượng key, TTL phân bố.
- Tần suất tạo lại những key lớn và traffic burst.

Đừng tự coi `expired_keys` nhiều là xấu: nếu ứng dụng chủ động dùng TTL ngắn cho dữ liệu tạm, expiration cao có thể hoàn toàn bình thường. Ngược lại, eviction liên tục của những key nóng có thể làm cache mất hiệu quả.

## 15. Vì sao tăng TTL không chữa được mọi vấn đề cache?

Khi thấy cache miss nhiều, phản xạ thường gặp là **tăng TTL từ 5 phút lên 1 giờ**. Việc này có thể giảm một phần miss do expiration, nhưng:

1. **Không đảm bảo ngăn eviction:** memory pressure vẫn có thể đẩy key ra trước một giờ.
2. **Tăng nguy cơ dữ liệu cũ:** nếu dữ liệu nguồn thay đổi mà không có invalidation, cache có thể phục vụ bản cũ lâu hơn.
3. **Làm tăng working set:** nhiều key tồn tại lâu hơn, có thể khiến bộ nhớ nhanh đầy hơn và eviction lại tăng.
4. **Có thể làm sai vòng đời:** session hoặc mã dùng một lần bị kéo dài không đúng chính sách.

Để chẩn đoán, hãy phân biệt:

~~~text
Cache miss tăng
    │
    ├── expired_keys tăng
    │      → Xem TTL, refresh policy, stampede, request patterns
    │
    ├── evicted_keys tăng
    │      → Xem maxmemory, key size, eviction policy,
    │        working set và phân bố truy cập
    │
    ├── both low
    │      → Xem key naming, invalidation, cold starts,
    │        cache bypass, lỗi kết nối hoặc dữ liệu chưa từng cache
    │
    └── nhiều nguyên nhân cùng lúc
           → Đo theo service và nhóm key thay vì một con số tổng
~~~

Một hệ thống có thể đồng thời gặp expiration nhiều và eviction nhiều. Chẩn đoán bằng dữ liệu đo, không dùng một “công thức tăng TTL” cho mọi tình huống.

## 16. Chọn TTL theo độ mới và chi phí nạp lại

TTL hợp lý phụ thuộc đặc tính dữ liệu và yêu cầu truy cập, không chỉ dung lượng bộ nhớ.

| Loại dữ liệu | Xu hướng chọn TTL | Lý do / câu hỏi cần kiểm tra |
| --- | --- | --- |
| Danh mục ít đổi | Có thể dài hơn, kèm invalidation khi cập nhật | Dữ liệu ít thay đổi, nạp lại có thể tốn kém |
| Giá sản phẩm | Thường cần ngắn hoặc invalidation đáng tin cậy | Sai giá ảnh hưởng trải nghiệm và giao dịch |
| Kết quả tìm kiếm | Có thể chấp nhận hơi cũ theo sản phẩm | Cân bằng tính mới, tốc độ và chi phí index |
| Token/mã xác nhận | Deadline theo yêu cầu bảo mật | Không được gia hạn tùy ý chỉ để giảm miss |
| Session | Theo chính sách bảo mật/vòng đời phiên | Eviction sớm ảnh hưởng đăng nhập; revoke cần cơ chế riêng |
| Kết quả phân tích | Theo chu kỳ làm mới hoặc mốc dữ liệu | Phải hiển thị độ trễ và cut-off nếu cần |
| Dữ liệu tồn kho để quyết định bán | Không được chỉ tin bản cache cũ | Cần thao tác điều kiện ở nguồn có thẩm quyền |

**Không có bảng TTL mặc định đúng cho mọi ứng dụng.** Các lựa chọn phải dựa trên giá trị nghiệp vụ của độ mới, chi phí cache miss, tỷ lệ thay đổi, dung lượng và khả năng invalidation.

### TTL tuyệt đối và thời hạn tính từ hoạt động cuối

Một chính sách:

> “Phiên hết hạn 30 phút sau khi đăng nhập.”

khác với:

> “Phiên hết hạn sau 30 phút không hoạt động.”

Trường hợp thứ hai cần **gia hạn thời hạn** khi có hoạt động hợp lệ, thường gọi là *sliding expiration*. Nếu dùng Redis, ứng dụng phải chủ động cập nhật TTL hoặc dùng API tương ứng; một lệnh `GET` thông thường không tự gia hạn TTL.

Thời hạn tuyệt đối là *absolute expiration*. Với tài nguyên nhạy cảm, đôi khi cần **cả thời hạn không hoạt động và deadline tuyệt đối tối đa**, tránh một phiên sống mãi nhờ hoạt động liên tục.

## 17. Khi dùng Redis vừa làm cache vừa lưu trạng thái quan trọng

Một thiết kế dễ gây rắc rối là dùng chung instance Redis cho:

~~~text
cache:product:*          → có thể tái tạo, chấp nhận eviction
cache:search:*           → có thể tái tạo, chấp nhận eviction
session:*                → mất sớm làm người dùng đăng xuất
rate-limit:*             → ảnh hưởng kiểm soát lưu lượng
job:progress:*           → mất có thể làm hỏng tiến độ xử lý
~~~

Nếu đặt policy `allkeys-lru`, những key không có TTL vẫn có thể là ứng viên eviction theo chính sách. Điều này có thể hoàn toàn phù hợp với **pure cache**, nhưng rủi ro nếu một số key được ứng dụng coi là **nguồn trạng thái duy nhất**.

### Phân loại dữ liệu trước khi chọn eviction policy

| Nhóm | Có thể tái tạo? | Có chấp nhận mất sớm? | Hướng đánh giá |
| --- | --- | --- | --- |
| Bản sao sản phẩm | Có, từ database chính | Thường có | Cache eviction phù hợp |
| Kết quả query | Có, chạy lại truy vấn | Thường có, nhưng cần tránh stampede | Cache eviction và rate limiting |
| Session | Có thể không tái tạo đầy đủ | Theo chính sách | Cân nhắc nơi lưu, persistence, eviction |
| Tiến độ job | Tùy có checkpoint ở DB khác | Có thể không | Không nên coi như cache thuần |
| Event chưa xử lý | Tùy pipeline | Thường không | Cần hệ lưu trữ/delivery có bảo đảm phù hợp |

Nếu nhu cầu khác nhau rõ rệt, có thể cân nhắc **phân tách instance hoặc lớp lưu trữ** để chính sách eviction và bảo đảm độ bền không xung đột. Việc chỉ đặt tiền tố `cache:` và `session:` trong cùng Redis không tự tạo các nhóm eviction policy riêng theo prefix.

### Cache có thể mất do nhiều nguyên nhân hơn TTL và eviction

Ngoài hai cơ chế chính, cache có thể mất dữ liệu khi:

- Ứng dụng gọi `DEL`, `UNLINK` hoặc dọn theo nhóm.
- Instance bị restart và cấu hình persistence không lưu hoặc không phục hồi đủ dữ liệu.
- Có thao tác quản trị xóa dữ liệu.
- Một quá trình failover/replication tạo trạng thái tạm thời khác nhau theo bảo đảm cụ thể.
- Cache được redeploy, chuyển cluster hoặc key namespace thay đổi.

Do đó, thiết kế **không phụ thuộc vào việc cache giữ mọi key** là nguyên tắc quan trọng với dữ liệu chỉ là bản sao.

## 18. Thực hành Redis: quan sát sự khác nhau

Các ví dụ sau chỉ nên chạy trong **Redis thử nghiệm**, không thay đổi cấu hình `maxmemory` trên instance đang phục vụ người dùng.

### 18.1. Quan sát expiration

~~~redis
SET demo:cache:short "value" EX 5
TTL demo:cache:short
GET demo:cache:short
~~~

Khi chạy `GET` sau hơn 5 giây:

~~~redis
GET demo:cache:short
TTL demo:cache:short
~~~

Kỳ vọng: `GET` không tìm thấy key; `TTL` trả `-2`.

Trong trường hợp này, nguyên nhân được chủ động tạo ra trong bài thử là **deadline expiration**, nhưng chỉ từ `TTL = -2` ở một hệ thống thực không thể chứng minh mọi cache miss đều do expiration.

### 18.2. Quan sát khóa không có TTL

~~~redis
SET demo:cache:no-expiry "value"
TTL demo:cache:no-expiry
~~~

Kỳ vọng khi key còn tồn tại và chưa có TTL: `TTL` trả `-1`. Điều này **không có nghĩa key được bảo đảm lưu vĩnh viễn**: eviction theo `allkeys-*`, xóa chủ động hoặc lỗi hạ tầng vẫn có thể làm key biến mất.

### 18.3. Quan sát tác dụng của SET

~~~redis
SET demo:cache:refresh "old" EX 300
TTL demo:cache:refresh

SET demo:cache:refresh "new"
TTL demo:cache:refresh
~~~

Lệnh `SET` thứ hai thông thường bỏ TTL, nên kết quả là `-1`. Có thể thử lại bằng `KEEPTTL` trong một key mới để so sánh:

~~~redis
SET demo:cache:keep "old" EX 300
SET demo:cache:keep "new" KEEPTTL
TTL demo:cache:keep
~~~

Kỳ vọng: key `demo:cache:keep` vẫn có TTL đang giảm.

### 18.4. Quan sát eviction mà không gây rủi ro production

Eviction cần có **giới hạn bộ nhớ và policy thực sự cho phép loại bỏ key**. Nếu chỉ tạo vài key nhỏ trong một Redis còn nhiều bộ nhớ, sẽ không có eviction để quan sát.

Đối với một instance Redis thử nghiệm riêng do người học quản lý, có thể:

1. Khởi động với giới hạn bộ nhớ và policy eviction dành riêng cho thí nghiệm.
2. Ghi nhiều key có giá trị lớn vừa phải đến khi xuất hiện áp lực bộ nhớ.
3. Quan sát `INFO stats`, đặc biệt mức tăng `evicted_keys`.
4. Chọn một key có TTL còn dài nhưng bị mất khi policy chọn.
5. So sánh với `expired_keys` và lượng bộ nhớ hiện tại.

**Không có lệnh cụ thể nào luôn bảo đảm một key xác định sẽ bị chọn**, bởi chính sách có tính xấp xỉ/ngẫu nhiên hoặc dựa vào mẫu truy cập. Quan sát nhiều lần sẽ thấy hành vi khác nhau tùy policy và mức tải.

Nếu muốn nhận biết chính xác những key nào bị xóa, Redis có cơ chế thông báo sự kiện keyspace/keyevent với cấu hình phù hợp, nhưng đó không phải nhật ký bền vững bảo đảm nhận đủ mọi sự kiện. Ứng dụng cần audit đầy đủ không nên dựa vào thông báo best-effort của cache làm nguồn duy nhất.

## 19. Tình huống tổng hợp: cache dữ liệu sản phẩm

Một cửa hàng có database sản phẩm làm nguồn chính. Redis giữ bản sao sản phẩm để phục vụ đọc chi tiết nhanh.

**Yêu cầu:**

- Cập nhật sản phẩm ít hơn nhiều so với đọc.
- Cache giúp giảm tải cho database.
- Sau khi sửa sản phẩm, nội dung cũ không được hiển thị kéo dài quá chính sách đã công bố.
- Redis có thể bị thiếu bộ nhớ và tự loại bỏ key.
- Khi cache miss, hệ thống phải lấy lại được dữ liệu từ nguồn.

Một thiết kế có thể:

~~~text
Database:
  product P1001 {id, price, updatedAt, revision}

Redis:
  cache:product:P1001 → JSON data + revision
  TTL khoảng vài phút theo chính sách

On read:
  GET cache
    hit  → trả theo chính sách độ mới
    miss → đọc nguồn và nạp lại cache

On write:
  cập nhật nguồn có điều kiện/transaction khi cần
  sau commit → invalidation cache hoặc ghi cache phiên bản mới

Observability:
  hit rate, miss rate, expired_keys, evicted_keys,
  source DB QPS và p95/p99 latency
~~~

### Ba diễn biến cần ứng dụng xử lý

**Diễn biến A — expiration bình thường:**

~~~text
09:00  Nạp P1001, TTL 300 giây
09:05  Key đến deadline hết hạn
09:06  Người dùng đọc → cache miss
       → DB nguồn có P1001 → nạp cache
~~~

**Diễn biến B — eviction sớm:**

~~~text
09:00  Nạp P1001, TTL 300 giây
09:01  Bộ nhớ cache chạm giới hạn
       Policy chọn và evict P1001
09:02  Người dùng đọc → cache miss
       → DB nguồn có P1001 → nạp cache
~~~

**Diễn biến C — dữ liệu nguồn thay đổi:**

~~~text
09:00  Nạp giá P1001 = 25.000 VND, TTL 300 giây
09:01  Admin đổi giá nguồn thành 27.000 VND
       → cần invalidation/đồng bộ cache phù hợp
09:02  Người dùng đọc → cần thấy giá theo freshness policy
~~~

Cả ba diễn biến có thể cần một lần đọc DB nguồn, nhưng **chỉ diễn biến C là sự kiện nghiệp vụ đòi hỏi cache cũ không còn được dùng**. TTL chỉ giúp đặt một giới hạn về thời gian; eviction không thể bảo đảm rằng những giá trị cần invalidation sẽ được chọn.

### Điều gì xảy ra nếu DB nguồn không sẵn sàng?

Nếu key vừa evict hoặc expire và DB nguồn đang lỗi, cache-aside **không thể tự tạo lại dữ liệu**. Tùy nghiệp vụ:

- Có thể trả lỗi rõ ràng.
- Có thể phục vụ bản stale đã được giữ riêng nếu chính sách cho phép.
- Có thể dùng fallback được thiết kế trước.
- Có thể từ chối thao tác quan trọng như thanh toán hoặc trừ tồn thay vì tự suy ra dữ liệu.

**Không được coi TTL dài là phương án khôi phục nguồn.** Eviction hoặc restart có thể làm mất cache trước khi nguồn phục hồi.

## 20. Những nhầm lẫn thường gặp

| Nhận định dễ sai | Cách hiểu đúng |
| --- | --- |
| “TTL 10 phút nghĩa là cache chắc chắn giữ key ít nhất 10 phút.” | Eviction, invalidation, xóa hoặc sự cố có thể làm key mất sớm. |
| “Key biến mất nghĩa là TTL đã hết.” | Có thể do nhiều nguyên nhân khác; `TTL = -2` không chỉ ra lý do. |
| “Eviction là một kiểu expiration.” | Eviction do chính sách tài nguyên; expiration do deadline thời gian. |
| “Không đặt TTL thì key không bao giờ mất.” | Policy `allkeys-*` vẫn có thể evict; có thể xóa hoặc mất do sự cố. |
| “`noeviction` khiến key tồn tại mãi.” | Hết hạn và xóa vẫn có hiệu lực; lệnh thêm bộ nhớ có thể bị lỗi. |
| “Đổi policy từ volatile sang allkeys không ảnh hưởng dữ liệu không TTL.” | Dữ liệu không TTL có thể trở thành ứng viên eviction. |
| “Tăng TTL luôn giảm cache miss.” | Miss do eviction có thể không giảm; working set tăng còn có thể làm eviction nhiều hơn. |
| “Key còn TTL thì chắc chắn dữ liệu còn mới.” | Nguồn đã thay đổi có thể làm giá trị cache lỗi thời. |
| “Cache miss nghĩa đối tượng không tồn tại ở database.” | Phải đọc nguồn có thẩm quyền hoặc dùng negative-cache contract rõ. |
| “Eviction tự động giải quyết thu hồi session/token.” | Chính sách bảo mật cần revoke đáng tin cậy, không trông vào áp lực bộ nhớ. |
| “TTL của database nguồn tương đương TTL của Redis cache.” | Ý nghĩa và thời điểm dọn vật lý khác theo DBMS và vai trò dữ liệu. |
| “Keyspace event là audit log đầy đủ.” | Thông báo cache không nên được coi là nguồn log bền vững với bảo đảm đầy đủ. |
| “SET cập nhật giá trị luôn giữ TTL.” | Redis `SET` thông thường bỏ TTL trừ khi chỉ định cách xử lý phù hợp. |

## 21. Bài tập thực hành

### Bài 1 — Hết hạn hay bị eviction?

Một key được ghi lúc 10:00 với TTL 600 giây. Đến 10:02, ứng dụng không đọc được key. Hãy nêu ít nhất bốn nguyên nhân có thể xảy ra và giải thích vì sao chưa thể kết luận key đã hết hạn.

**Gợi ý:** TTL theo lý thuyết còn khoảng 8 phút; cần xét eviction, invalidation, xóa thủ công, restart/mất dữ liệu, namespace sai hoặc key chưa được ghi thành công.

### Bài 2 — Policy volatile và allkeys

Redis có hai key:

~~~text
cache:product:P1 → TTL 300 giây
config:service   → không có TTL
~~~

Nếu bộ nhớ gần đầy:

1. Key nào là ứng viên với `volatile-lru`?
2. Key nào là ứng viên với `allkeys-lru`?
3. Điều gì có thể xảy ra khi chọn `volatile-lru` nhưng không có key nào đặt expiration?

**Gợi ý:** chính sách `volatile-*` chỉ xét các key có TTL; `allkeys-*` xét mọi key. Không có ứng viên phù hợp có thể làm thao tác cần thêm bộ nhớ bị từ chối.

### Bài 3 — Lệnh SET và TTL

Với các lệnh:

~~~redis
SET session:S1 "old" EX 1800
SET session:S1 "new"
TTL session:S1
~~~

Kết quả `TTL` thông thường là gì? Hãy viết lại lệnh thứ hai trong hai trường hợp:

- Giữ deadline đã có.
- Gia hạn từ bây giờ thêm 1.800 giây.

**Gợi ý:** `SET` thường bỏ TTL; dùng `KEEPTTL` để giữ hoặc `EX 1800` để đặt hạn mới.

### Bài 4 — Một đợt cache stampede

Ứng dụng cache 50.000 danh mục sản phẩm, tất cả có TTL đúng 300 giây và được nạp gần như cùng lúc. Sau 300 giây, DB nguồn đột ngột tăng tải mạnh. Hãy mô tả nguyên nhân và đề xuất ba cơ chế giảm rủi ro.

**Gợi ý:** TTL jitter, single-flight, refresh trước hạn, giới hạn concurrency và backpressure. Không áp dụng stale-while-revalidate nếu yêu cầu dữ liệu mới nghiêm ngặt.

### Bài 5 — Dữ liệu cũ nhưng key vẫn tồn tại

Giá sản phẩm thay đổi lúc 09:05, trong khi key cache được nạp lúc 09:00 với TTL 30 phút. Lúc 09:10, giá trị cache vẫn có thể trả giá cũ không? Eviction có phải giải pháp chính xác để cập nhật giá không?

**Gợi ý:** có thể stale; cần invalidation, version hoặc một quy trình đồng bộ đúng, không trông vào eviction.

### Bài 6 — Phân tích số liệu

Trong 10 phút:

~~~text
expired_keys tăng 2.000
evicted_keys tăng 15.000
keyspace_misses tăng 30.000
used_memory thường xuyên gần maxmemory
~~~

Giả thuyết nào đáng kiểm tra trước? Vì sao tăng TTL có thể làm tình trạng xấu hơn?

**Gợi ý:** áp lực bộ nhớ và eviction có dấu hiệu mạnh. TTL tăng khiến nhiều key tồn tại lâu hơn, làm working set lớn hơn.

### Bài 7 — Session với deadline bảo mật

Session có thời hạn tuyệt đối 30 phút. Ứng dụng cứ mỗi request lại gọi `EXPIRE sessionKey 1800`. Điều gì có thể sai? Hãy đề xuất cách biểu diễn để không vô tình vượt deadline.

**Gợi ý:** `EXPIRE` lặp lại có thể tạo sliding expiration thay vì deadline tuyệt đối; cần lưu mốc hết hạn tối đa và không gia hạn vượt nó.

### Bài 8 — TTL của database chính và retention

Một hệ thống xóa log theo TTL trong database nhưng vẫn giữ bản sao trong search index và file export. Có thể tuyên bố dữ liệu đã bị loại bỏ hoàn toàn chỉ vì log nguồn đã hết hạn không?

**Gợi ý:** chưa; cần chính sách retention cho mọi nơi có bản sao, hiểu cơ chế xóa bất đồng bộ và đối soát theo yêu cầu.

## 22. Mẫu đặc tả vòng đời cho một nhóm cache

Khi sử dụng Redis hoặc cache khác, có thể thống nhất một tài liệu ngắn:

~~~yaml
dataset: Product detail cache
keyPattern: "cache:product:<productId>"
owner: Catalog service
sourceOfTruth: "Product database"
cachedValue: "Product read model with revision"
cacheMiss:
  action: "Read authoritative product; repopulate cache"
  negativeCaching: "Short TTL only when allowed"
expiration:
  ttlSeconds: 300
  semantic: "Maximum normal cache age, not guaranteed residency"
  refresh: "Re-fetch source before extending freshness"
eviction:
  allowed: true
  configuredAt: "Cache infrastructure level"
  applicationAssumption: "Any key may be absent at any read"
invalidation:
  trigger: "Product source update/delete"
  design: "Remove/refresh entry after committed change"
freshness:
  policy: "Defined by Catalog product requirements"
  strongReadBypass: "Use source for critical authoritative decisions"
failureHandling:
  redisUnavailable: "Use controlled source fallback or error policy"
  sourceUnavailable: "Do not invent authoritative product data"
security:
  tenantScope: "Apply authorization independent of cache hit/miss"
monitoring:
  - "cache hit/miss rate"
  - "expired_keys rate"
  - "evicted_keys rate"
  - "used_memory / maxmemory"
  - "source DB load and latency"
  - "stale value incidents"
~~~

Đây là **mẫu đặc tả ứng dụng**, không phải cấu hình Redis có thể tự nạp. Nó nhấn mạnh rằng TTL, eviction, invalidation, nguồn dữ liệu và xử lý cache miss là **những phần khác nhau của cùng một chính sách vòng đời**.

## 23. Tổng kết

Để phân biệt **hết hạn dữ liệu** với **loại bỏ khỏi bộ nhớ đệm**, hãy nhớ:

1. **Expiration dựa trên thời gian.** TTL hoặc deadline quyết định khi nào giá trị hết hiệu lực. Hệ thống có thể phát hiện và dọn dữ liệu bằng cơ chế chủ động hoặc khi truy cập, tùy DBMS.
2. **Eviction dựa trên tài nguyên và policy.** Khi thiếu bộ nhớ, cache có thể chọn key để loại bỏ **trước khi TTL hết**. Không có TTL không đồng nghĩa an toàn khỏi eviction nếu policy chọn mọi key.
3. **Cache miss không cho biết nguyên nhân.** Key có thể chưa được tạo, hết hạn, bị evict, invalidated, bị xóa hoặc mất vì sự cố. Ứng dụng nên xử lý miss như một khả năng bình thường đối với dữ liệu cache có thể tái tạo.
4. **TTL không đảm bảo dữ liệu còn mới hoặc còn hiện diện đến deadline.** Cần freshness/invalidation khi nguồn thay đổi, và chiến lược nạp lại khi cache miss.
5. **Cache eviction không thay thế xóa dữ liệu theo nghiệp vụ, retention hay bảo mật.** Nguồn dữ liệu chính, bản sao, index, backup và chính sách quyền có vòng đời riêng.
6. **Phải đo cả expiration lẫn eviction.** `expired_keys`, `evicted_keys`, cache hit/miss và tải DB nguồn giúp phân biệt mất key do chính sách thời gian hay áp lực bộ nhớ.

**Nguyên tắc thiết kế:** *TTL xác định một giới hạn thời gian sử dụng; eviction quản lý tài nguyên; invalidation phản ánh thay đổi của nguồn dữ liệu*. Chỉ khi phân biệt rõ ba cơ chế và thiết kế đúng đường xử lý cache miss, hệ thống NoSQL mới vừa đạt hiệu năng, vừa giữ đúng vòng đời và ngữ nghĩa dữ liệu.
