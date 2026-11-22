# Mô hình khóa–giá trị và các kiểu dữ liệu của Redis

Redis là một hệ quản trị dữ liệu hoạt động chủ yếu trên bộ nhớ, tổ chức dữ liệu theo **khóa–giá trị** (*key–value*). Điểm quan trọng là **giá trị không nhất thiết chỉ là một chuỗi đơn giản**: Redis có nhiều cấu trúc dữ liệu được thiết kế cho những thao tác khác nhau, chẳng hạn đếm số lượt xem, lưu thuộc tính người dùng, quản lý hàng đợi, tập hợp nhãn, bảng xếp hạng hoặc nhật ký sự kiện.

Trong Spring Data Redis, việc hiểu đúng mô hình dữ liệu quyết định cách đặt khóa, chọn `RedisTemplate`/`StringRedisTemplate` và sử dụng các nhóm thao tác như `opsForValue()`, `opsForHash()`, `opsForList()` hay `opsForZSet()`.

## 1. Tư duy khóa–giá trị

### 1.1. Một khóa trỏ đến một giá trị có kiểu xác định

Hãy hình dung Redis như một bảng tra cứu rất lớn:

```text
Redis keyspace
│
├── product:1001:stock  ───────> "25"                       [String]
├── user:1001           ───────> {name: "An", city: "HCM"}  [Hash]
├── queue:emails        ───────> ["mail-1", "mail-2"]       [List]
├── post:42:tags        ───────> {"java", "redis"}          [Set]
└── ranking:week        ───────> {"an": 120, "binh": 90}    [Sorted Set]
```

Một mục dữ liệu gồm hai phần:

- **Key (khóa):** định danh duy nhất của mục dữ liệu trong phạm vi cơ sở dữ liệu Redis đang sử dụng; thường được biểu diễn bằng chuỗi có ý nghĩa nghiệp vụ.
- **Value (giá trị):** dữ liệu gắn với khóa, mang một kiểu Redis cụ thể như String, Hash, List, Set, Sorted Set hoặc Stream.

Không có khái niệm bảng, hàng, khóa ngoại và phép `JOIN` mặc định như trong cơ sở dữ liệu quan hệ. Ứng dụng thường thiết kế khóa và cấu trúc giá trị theo **cách dữ liệu sẽ được truy cập**.

Ví dụ, muốn lấy ngay tồn kho một sản phẩm theo mã, khóa `product:1001:stock` chứa một số là phù hợp. Muốn lấy nhiều thuộc tính của cùng người dùng, Hash `user:1001` thường rõ ràng hơn việc tạo một khóa độc lập cho mỗi thuộc tính.

### 1.2. Tên khóa có cấu trúc, nhưng Redis không tạo thư mục

Một quy ước thường gặp:

```text
<loại-thực-thể>:<định-danh>:<mục-đích>

user:1001
user:1001:sessions
product:SKU-42:stock
ranking:weekly:2026-W46
```

Dấu hai chấm (`:`) chỉ là ký tự trong tên khóa; Redis **không tự tạo quan hệ cha–con** giữa `user:1001` và `user:1001:sessions`. Quy ước đặt tên giúp lập trình viên tránh trùng khóa, phân tách dữ liệu và quản lý thời hạn tồn tại.

Nên giữ tên khóa nhất quán, vừa đủ mô tả, tránh đưa dữ liệu nhạy cảm vào tên khóa và tránh các khóa khổng lồ chứa quá nhiều phần tử mà ứng dụng luôn đọc toàn bộ.

### 1.3. Những thao tác chung trên khóa

Các lệnh dưới đây thao tác ở cấp **key**, không phụ thuộc giá trị là String, Hash hay List:

```redis
EXISTS user:1001                # Khóa có tồn tại hay không?
TYPE user:1001                  # Ví dụ kết quả: hash
EXPIRE user:1001 3600           # Hết hạn sau 3.600 giây
TTL user:1001                   # Số giây còn lại
DEL user:1001                   # Xóa khóa và toàn bộ giá trị
```

Với `TTL`, kết quả `-1` nghĩa là khóa tồn tại nhưng không có thời hạn hết hạn; `-2` nghĩa là khóa không tồn tại. `EXPIRE` thường dùng cho cache, session và dữ liệu tạm. Trong cách sử dụng cơ bản, TTL gắn với **khóa chứa cấu trúc**, chứ không tự động gắn riêng cho từng phần tử của List hoặc Set. Một số phiên bản Redis mới hỗ trợ thêm khả năng hết hạn ở mức trường Hash.

Khi cần duyệt khóa trên hệ thống đang phục vụ lưu lượng thật, dùng `SCAN` theo từng đợt thay vì `KEYS pattern`, vì `KEYS` có thể chặn máy chủ khi không gian khóa lớn:

```redis
SCAN 0 MATCH user:* COUNT 100
```

`SCAN` trả về cursor tiếp theo và một nhóm khóa; phải tiếp tục duyệt đến khi cursor trở về `0`. `COUNT` chỉ là gợi ý số phần tử mỗi lượt, không bảo đảm kích thước trang cố định.

## 2. Bản đồ các kiểu dữ liệu Redis

| Kiểu/cấu trúc | Giá trị biểu diễn | Đặc điểm chính | Tình huống phù hợp |
|---|---|---|---|
| **String** | Chuỗi byte, có thể biểu diễn số | Đọc/ghi nguyên giá trị, tăng giảm số | Cache giá trị, token, bộ đếm |
| **Hash** | Tập các cặp `field → value` | Truy cập từng thuộc tính | Hồ sơ, cấu hình, thông tin đối tượng |
| **List** | Dãy phần tử có thứ tự | Thêm/lấy ở hai đầu; có thể trùng | Hàng đợi đơn giản, danh sách gần nhất |
| **Set** | Tập phần tử duy nhất, không có thứ tự đảm bảo | Kiểm tra thành viên, giao/hợp/hiệu | Tag, tập người tham gia, quan hệ theo tập |
| **Sorted Set (ZSet)** | Phần tử duy nhất đi kèm điểm số | Sắp theo điểm, truy vấn thứ hạng | Bảng xếp hạng, dữ liệu ưu tiên |
| **Stream** | Chuỗi bản ghi có ID, nhiều trường | Đọc theo ID, nhóm consumer, xác nhận xử lý | Nhật ký sự kiện, xử lý sự kiện có lưu lại |
| **Bitmap / Bitfield** | Các bit hoặc nhóm bit trong String | Biểu diễn trạng thái/counter gọn | Điểm danh, cờ trạng thái, số đếm đóng gói |
| **HyperLogLog** | Cấu trúc ước lượng số phần tử phân biệt | Tiết kiệm bộ nhớ, kết quả xấp xỉ | Ước lượng số người dùng duy nhất |
| **Geospatial** | Tọa độ và định danh địa điểm | Tìm theo khoảng cách/vùng lân cận | Cửa hàng, tài xế, điểm giao hàng |

**Phân biệt kiểu logic và kiểu lưu trữ:** Bitmap, Bitfield, HyperLogLog được triển khai trên giá trị dạng String; dữ liệu Geospatial được xây dựng trên Sorted Set. Vì vậy `TYPE` không nhất thiết trả về tên nhóm chức năng ở bảng trên. Một số phiên bản hoặc bản phân phối Redis còn có kiểu/tính năng mở rộng, chẳng hạn dữ liệu JSON hoặc tìm kiếm vector; cần kiểm tra khả năng hỗ trợ trên máy chủ đang dùng.

## 3. String: giá trị đơn và bộ đếm

String là kiểu cơ bản nhất. Dù lưu chữ, JSON đã tuần tự hóa, dữ liệu nhị phân hoặc số, Redis xử lý giá trị String như một chuỗi byte. Với các thao tác số học, nội dung phải biểu diễn số nguyên/hợp lệ theo yêu cầu lệnh.

```redis
SET product:1001:name "Ban phim co"
GET product:1001:name

SET product:1001:stock 25
INCR product:1001:stock
INCRBY product:1001:stock 4
DECR product:1001:stock
GET product:1001:stock
```

Sau các thao tác tăng, cộng 4 và giảm 1, `product:1001:stock` có giá trị `29`. Các lệnh như `INCR` và `INCRBY` là thao tác nguyên tử ở cấp một lệnh, rất tiện cho bộ đếm có nhiều yêu cầu đồng thời.

String còn hỗ trợ đặt thời gian tồn tại ngay khi ghi:

```redis
SET session:token:abc "user:1001" EX 1800
GET session:token:abc
TTL session:token:abc
```

Ở đây `EX 1800` đặt thời hạn 30 phút. Một lần `SET` thông thường thay thế giá trị hiện tại và làm mất TTL cũ của khóa, trừ khi sử dụng tùy chọn giữ TTL được hỗ trợ; cần lưu ý khi làm mới cache hoặc session.

**Khi chọn String:** ứng dụng thường đọc/ghi toàn bộ giá trị, cần một bộ đếm hoặc muốn lưu dữ liệu đã tuần tự hóa. Nếu thường xuyên cập nhật riêng từng trường của một đối tượng, cân nhắc Hash.

## 4. Hash: nhóm thuộc tính của một đối tượng

Hash chứa nhiều cặp `field → value` bên dưới cùng một khóa Redis. Đây là lựa chọn tự nhiên khi mô hình hóa một đối tượng nhỏ với các thuộc tính có thể đọc và sửa độc lập.

```redis
HSET user:1001 name "An" city "Ho Chi Minh" loginCount 0
HGET user:1001 name
HMGET user:1001 name city
HINCRBY user:1001 loginCount 1
HGETALL user:1001
HDEL user:1001 city
```

`HGET` chỉ lấy một trường; `HGETALL` lấy toàn bộ cặp trường–giá trị. Trường chưa tồn tại trả về giá trị rỗng/null theo giao diện client. Tất cả trường thuộc cùng khóa `user:1001`, nên TTL đặt lên khóa đó ảnh hưởng đến toàn bộ Hash.

Điểm cần chú ý:

- Hash là một giá trị Redis; `name` và `city` là **field**, không phải các key độc lập trong keyspace.
- Redis không tự hiểu `loginCount` là thuộc tính Java kiểu `int`: bộ đếm có thể dùng `HINCRBY` khi giá trị biểu diễn số nguyên hợp lệ.
- Không nên dùng `HGETALL` thường xuyên trên Hash có số trường rất lớn; chỉ lấy field cần dùng hoặc duyệt theo đợt với `HSCAN`.
- Hash không có cơ chế quan hệ, truy vấn lọc nhiều đối tượng hay chỉ mục thứ cấp tự động như bảng SQL.

**Ví dụ thiết kế:** `user:1001` là Hash chứa hồ sơ; `user:1001:roles` có thể là một Set khác nếu ứng dụng cần kiểm tra vai trò và thực hiện các phép tập hợp.

## 5. List: dãy có thứ tự và hàng đợi đơn giản

List lưu các phần tử theo thứ tự trong dãy. Phần tử có thể lặp lại; thao tác thêm hoặc lấy phần tử ở hai đầu rất phù hợp với cấu trúc queue/deque.

```redis
RPUSH queue:emails "mail-1" "mail-2" "mail-3"
LRANGE queue:emails 0 -1
LPOP queue:emails
LRANGE queue:emails 0 -1
```

`RPUSH` thêm ở cuối; `LPOP` lấy ở đầu, nên hai lệnh trên tạo hàng đợi FIFO: `mail-1` được lấy trước. Nếu thêm và lấy cùng một đầu, mô hình sẽ giống stack LIFO. `LRANGE key 0 -1` đọc toàn bộ danh sách; chỉ phù hợp khi danh sách đủ nhỏ.

Những lệnh thường gặp:

| Lệnh | Ý nghĩa |
|---|---|
| `LPUSH` / `RPUSH` | Thêm một hay nhiều phần tử vào đầu/cuối |
| `LPOP` / `RPOP` | Lấy và xóa phần tử đầu/cuối |
| `LLEN` | Lấy số phần tử |
| `LRANGE` | Đọc một đoạn theo chỉ số |
| `BLPOP` | Chờ phần tử xuất hiện ở một trong các List được chỉ định |

List phù hợp với hàng đợi đơn giản, nhưng nếu cần lưu các sự kiện có ID, nhiều consumer, trạng thái đã xử lý và khả năng đọc lại, Stream thường phù hợp hơn. Việc `LPOP` xóa phần tử ngay cũng khiến ứng dụng phải tự thiết kế quy trình phục hồi nếu consumer nhận việc rồi gặp lỗi.

## 6. Set: tập hợp duy nhất, không có thứ tự

Set không chứa hai phần tử giống hệt nhau. Kiểu này hữu ích khi câu hỏi chính là “phần tử này có thuộc tập hay không?” hoặc “hai nhóm có phần tử chung nào?”.

```redis
SADD post:42:tags "redis" "spring" "java" "redis"
SCARD post:42:tags
SISMEMBER post:42:tags "redis"
SMEMBERS post:42:tags

SADD post:43:tags "redis" "docker"
SINTER post:42:tags post:43:tags
SUNION post:42:tags post:43:tags
SDIFF post:42:tags post:43:tags
```

`SCARD post:42:tags` trả về `3`, do thêm lại `redis` không tạo phần tử trùng. `SINTER` tìm giao, `SUNION` tìm hợp và `SDIFF` lấy phần tử thuộc tập đầu nhưng không thuộc tập sau.

**Không dựa vào thứ tự hiển thị của `SMEMBERS`:** Set không bảo đảm trình tự. Với tập lớn, không nên kéo toàn bộ tập về ứng dụng nếu chỉ cần kiểm tra một thành viên; dùng `SISMEMBER`. Có thể duyệt theo từng đợt bằng `SSCAN`.

## 7. Sorted Set (ZSet): thứ hạng theo điểm số

Sorted Set kết hợp tính **duy nhất của phần tử** với một **score** dạng số. Redis sắp phần tử theo score; khi bằng điểm, thứ tự giữa các member được xác định theo thứ tự từ điển của member. Phù hợp cho leaderboard, điểm ưu tiên và các danh sách cần truy vấn theo thứ hạng.

```redis
ZADD ranking:week 120 "an" 90 "binh" 110 "chi"
ZRANGE ranking:week 0 -1 WITHSCORES
ZRANGE ranking:week 0 2 REV WITHSCORES
ZINCRBY ranking:week 35 "binh"
ZREVRANK ranking:week "binh"
ZSCORE ranking:week "binh"
```

Sau khi tăng thêm 35 điểm, `binh` có score `125`, đứng đầu bảng nếu không có phần tử điểm cao hơn. `ZREVRANK` trả về thứ hạng tính từ `0`, trong đó `0` là vị trí cao nhất.

So sánh nhanh:

- **List:** ưu tiên thứ tự chèn vào và thao tác hai đầu; có thể trùng phần tử.
- **Set:** kiểm tra thành viên và phép tập hợp; không có thứ hạng.
- **Sorted Set:** cần thứ tự theo điểm/rank; mỗi member chỉ xuất hiện một lần.

Các thao tác thêm hoặc cập nhật phần tử của Sorted Set thường có chi phí theo logarit của số lượng phần tử, đổi lại hỗ trợ truy vấn thứ hạng hiệu quả. Khi bảng xếp hạng rất lớn, nên đọc theo khoảng thay vì lấy toàn bộ.

## 8. Stream: chuỗi sự kiện có ID

Stream chứa nhiều bản ghi (*entry*), mỗi bản ghi có ID và tập trường–giá trị. Khác với List thông thường, Stream thiết kế cho trường hợp ứng dụng cần đọc dữ liệu phát sinh theo thời gian, quản lý vị trí đọc và có thể tổ chức **consumer group**.

```redis
XADD orders:events * orderId "1001" state "CREATED"
XADD orders:events * orderId "1002" state "PAID"
XLEN orders:events
XRANGE orders:events - +
XREAD COUNT 10 STREAMS orders:events 0-0
```

Dấu `*` yêu cầu Redis cấp ID cho sự kiện mới. `XREAD` với ID `0-0` đọc các entry có ID lớn hơn mốc đó. Trong thực tế có thể đọc từ một ID đã ghi nhớ, đọc chặn để đợi sự kiện mới hoặc dùng consumer group.

Luồng consumer group điển hình:

```redis
XGROUP CREATE orders:events processors 0 MKSTREAM
XREADGROUP GROUP processors worker-1 COUNT 10 STREAMS orders:events >
# Sau khi xử lý thành công, dùng ID thực tế trả về bởi XREADGROUP:
XACK orders:events processors <entry-id>
```

`XREADGROUP` đọc thông điệp mới cho một nhóm; thông điệp đã phân phát nhưng chưa `XACK` nằm trong danh sách chờ xác nhận (*pending*). Để xử lý lỗi consumer, ứng dụng cần cơ chế kiểm tra/nhận lại thông điệp pending. `XACK` **không tự xóa bản ghi khỏi Stream**; muốn khống chế dung lượng phải có chính sách cắt tỉa hoặc xóa dữ liệu phù hợp.

Stream giải quyết bài toán khác với Pub/Sub: Pub/Sub phát thông điệp cho subscriber đang kết nối mà không lưu backlog theo cơ chế Stream; Stream lưu entry để có thể đọc lại cho đến khi bị xóa/cắt tỉa theo chính sách.

## 9. Các cấu trúc chuyên biệt

### 9.1. Bitmap và Bitfield

Bitmap cho phép truy cập từng bit trong một giá trị String. Mỗi bit có thể biểu diễn một trạng thái nhị phân, ví dụ người dùng số `42` có hoạt động trong ngày hay không:

```redis
SETBIT active:2026-11-12 42 1
GETBIT active:2026-11-12 42
BITCOUNT active:2026-11-12
```

`BITCOUNT` đếm số bit bằng `1`. Bitmap tiết kiệm bộ nhớ khi ID đủ liên tục và bài toán chủ yếu là trạng thái đúng/sai. Tuy nhiên, đặt bit tại offset cực lớn có thể làm giá trị mở rộng đáng kể; không nên dùng ID rời rạc khổng lồ làm offset mà không tính toán.

Bitfield cũng thao tác trên String, nhưng xem những nhóm bit liên tiếp như số nguyên có dấu/không dấu:

```redis
BITFIELD counters:packed SET u8 0 7 GET u8 0
```

Ví dụ này ghi giá trị `7` vào trường không dấu dài 8 bit ở offset `0`, rồi đọc lại. Chỉ nên dùng khi hiểu rõ giới hạn số, vị trí bit và cách xử lý tràn số.

### 9.2. HyperLogLog

HyperLogLog dùng để **ước lượng số phần tử phân biệt** với chi phí bộ nhớ nhỏ, phù hợp cho thống kê như số người dùng truy cập duy nhất trong ngày:

```redis
PFADD visitors:2026-11-12 "user-1" "user-2" "user-1"
PFCOUNT visitors:2026-11-12
```

`PFCOUNT` cho kết quả **xấp xỉ**, không phải cam kết chính xác tuyệt đối. HyperLogLog cũng không cung cấp danh sách đầy đủ các phần tử đã thêm và không thay thế Set nếu cần kiểm tra “user-1 có thuộc tập này không?”.

### 9.3. Geospatial

Geospatial lưu địa điểm theo kinh độ và vĩ độ, hỗ trợ tìm các địa điểm trong bán kính:

```redis
GEOADD store:locations 106.701 10.777 "store-a"
GEOADD store:locations 106.710 10.780 "store-b"
GEOPOS store:locations "store-a"
GEOSEARCH store:locations FROMLONLAT 106.700 10.775 BYRADIUS 5 km WITHDIST
```

Thứ tự tọa độ trong `GEOADD` là **kinh độ trước, vĩ độ sau**. Geospatial dựa trên Sorted Set, vì vậy lệnh `TYPE store:locations` trả về `zset`. Kết quả truy vấn khoảng cách là phép tính địa lý gần đúng; ứng dụng cần lựa chọn đơn vị và phạm vi hợp lý.

### 9.4. Các kiểu hoặc mô-đun mở rộng

Ngoài các cấu trúc trên, một hệ thống Redis có thể được trang bị tính năng cho tài liệu JSON, tìm kiếm, vector/embedding và các bài toán chuyên biệt khác. Tên lệnh và khả năng sẵn có phụ thuộc vào phiên bản Redis và các mô-đun hoặc bản phân phối được triển khai. Vì thế, khi thiết kế ứng dụng Spring Data Redis, cần phân biệt **kiểu dữ liệu Redis cơ bản** với khả năng mở rộng được cài đặt riêng.

## 10. Chọn kiểu dữ liệu theo truy vấn cần thực hiện

Giả sử xây một ứng dụng bán hàng có giỏ hàng, nhãn sản phẩm, tồn kho và lịch sử sự kiện. Thay vì bắt đầu bằng câu hỏi “nên có bao nhiêu bảng?”, hãy hỏi “mỗi lần ứng dụng truy cập Redis, nó cần thao tác gì?”.

| Nhu cầu | Mô hình khóa minh họa | Lựa chọn hợp lý | Vì sao |
|---|---|---|---|
| Đọc số lượng tồn kho | `product:1001:stock` | String | `GET`, `INCRBY`, `DECRBY` |
| Cập nhật thuộc tính hồ sơ | `user:1001` | Hash | `HGET`, `HSET`, `HINCRBY` từng field |
| Lấy công việc đầu hàng đợi | `queue:emails` | List | `RPUSH` + `LPOP` |
| Kiểm tra một sản phẩm có nhãn nào | `product:1001:tags` | Set | Không trùng, `SISMEMBER` |
| Top người dùng theo điểm | `ranking:weekly` | Sorted Set | Score và rank |
| Ghi sự kiện đơn hàng để xử lý | `orders:events` | Stream | ID, đọc theo tiến độ, consumer group |
| Ghi trạng thái hoạt động từng ngày | `active:yyyy-mm-dd` | Bitmap | Bit biểu diễn trạng thái |
| Ước lượng lượt khách duy nhất | `visitors:yyyy-mm-dd` | HyperLogLog | Cardinality xấp xỉ, tiết kiệm bộ nhớ |
| Tìm cửa hàng gần vị trí hiện tại | `store:locations` | Geospatial | Tìm theo vị trí/bán kính |

Cùng một thực thể có thể xuất hiện trong nhiều khóa để phục vụ các kiểu truy vấn khác nhau. Ví dụ `product:1001` là Hash mô tả sản phẩm, còn `product:1001:stock` là String dùng để tăng giảm nhanh. Thiết kế này cần quy ước rõ dữ liệu nào là nguồn chính và cách đồng bộ khi một thuộc tính xuất hiện ở nhiều nơi.

## 11. Những quy tắc quan trọng khi thao tác Redis

### 11.1. Mỗi key có một kiểu tại một thời điểm

```redis
SET demo:key "hello"
HSET demo:key name "An"
```

Lệnh thứ hai sẽ gặp lỗi `WRONGTYPE` vì `demo:key` đang là String. Không thể dùng nhóm lệnh Hash để thao tác một key String. Lưu ý `SET demo:key ...` có thể **thay thế** giá trị/kiểu dữ liệu đang lưu ở key đó; cần tránh tái sử dụng tên khóa cho hai mục đích.

### 11.2. Thao tác trên một lệnh thường nguyên tử; một chuỗi lệnh thì chưa chắc

`INCR counter` là một lệnh tăng nguyên tử. Ngược lại, trình tự `GET counter`, tính toán trong Java, rồi `SET counter` có thể bị ghi đè khi nhiều luồng cùng chạy. Các bước nghiệp vụ qua nhiều khóa cũng không mặc nhiên tạo thành một giao dịch nguyên tử. Hãy ưu tiên lệnh dữ liệu chuyên dụng và cân nhắc transaction hoặc script khi cần bảo đảm tính nhất quán cho nhiều thao tác.

### 11.3. TTL, dung lượng và truy vấn toàn bộ

- **TTL:** khóa hết hạn có thể biến mất trước lần đọc kế tiếp; ứng dụng cần xử lý trường hợp không tìm thấy. Không đặt TTL cho dữ liệu cần lưu lâu nếu chưa có chính sách hết hạn.
- **Dung lượng:** Redis thường giữ dữ liệu truy cập nhanh trong bộ nhớ; một key chứa List/Hash/Set quá lớn vẫn tiêu thụ tài nguyên đáng kể. Hãy giới hạn độ dài hàng đợi, số entry Stream hoặc phạm vi lịch sử khi bài toán yêu cầu.
- **Truy vấn:** các lệnh trả về toàn bộ như `SMEMBERS`, `HGETALL`, `LRANGE 0 -1` có thể tạo tải lớn. Dùng phạm vi hợp lý hoặc các lệnh quét theo đợt khi dữ liệu tăng trưởng.
- **Tính bền vững:** Redis có cơ chế persistence và replication tùy cấu hình, nhưng chọn kiểu dữ liệu không tự bảo đảm rằng dữ liệu đã được ghi bền vững. Cần có chính sách vận hành tương ứng với mức độ quan trọng của dữ liệu.

## 12. Ánh xạ sang Spring Data Redis

Spring Data Redis cung cấp các API thao tác tương ứng với cấu trúc Redis. Với ứng dụng Spring Boot, `StringRedisTemplate` thuận tiện khi key và giá trị/field đều có thể biểu diễn bằng chuỗi:

```java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisDataExample {

    private final StringRedisTemplate redis;

    public RedisDataExample(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void writeSampleData() {
        // String: giá trị có TTL 30 phút.
        redis.opsForValue().set("product:1001:stock", "25", Duration.ofMinutes(30));
        redis.opsForValue().increment("product:1001:stock", 2);

        // Hash: các thuộc tính cùng một key.
        redis.opsForHash().put("user:1001", "name", "An");
        redis.opsForHash().put("user:1001", "city", "Ho Chi Minh");
        redis.expire("user:1001", Duration.ofHours(1));

        // List: thêm vào đuôi hàng đợi.
        redis.opsForList().rightPush("queue:emails", "mail-1");

        // Set: mỗi tag chỉ tồn tại một lần.
        redis.opsForSet().add("product:1001:tags", "redis", "spring");

        // Sorted Set: lưu điểm cho bảng xếp hạng.
        redis.opsForZSet().add("ranking:weekly", "user:1001", 120.0);
    }
}
```

API thường dùng:

| Kiểu Redis | API Spring Data Redis | Thao tác ví dụ |
|---|---|---|
| String | `opsForValue()` | `get`, `set`, `increment` |
| Hash | `opsForHash()` | `put`, `get`, `entries`, `increment` |
| List | `opsForList()` | `leftPush`, `rightPush`, `leftPop`, `range` |
| Set | `opsForSet()` | `add`, `isMember`, `intersect` |
| Sorted Set | `opsForZSet()` | `add`, `incrementScore`, `reverseRange` |
| Stream | `opsForStream()` | `add`, `read`, `acknowledge` |
| Geospatial | `opsForGeo()` | `add`, `radius`, `search` (tùy API/phiên bản) |
| HyperLogLog | `opsForHyperLogLog()` | `add`, `size` |

Với object Java, `RedisTemplate<K, V>` cho phép tùy chỉnh serializer của khóa, giá trị, hash key và hash value. Dữ liệu quan sát được bằng `redis-cli` phụ thuộc vào serializer: một đối tượng Java không tự động trở thành Redis Hash chỉ vì nó có nhiều trường. Nếu dùng serializer để ghi toàn bộ object dưới một key, dữ liệu có thể đang là **Redis String chứa payload đã mã hóa**; muốn thao tác từng field bằng `HGET`/`HSET` thì phải thực sự lưu bằng cấu trúc Hash.

Ngoài ra, thao tác `get`, `pop`, `isMember` hay đọc một trường có thể trả về `null` trong một số trường hợp (key vắng mặt hoặc ngữ cảnh thực thi đặc biệt). Mã ứng dụng cần tính đến trạng thái này thay vì giả định dữ liệu luôn tồn tại.

## 13. Ví dụ tổng hợp: thiết kế dữ liệu cho một bài toán

Giả sử cần lưu thông tin một chiến dịch gồm: thuộc tính chiến dịch, tập người tham gia, điểm từng người và sự kiện tham gia. Có thể chọn các khóa độc lập sau:

```text
campaign:2026-fall             [Hash]       name, startDate, status
campaign:2026-fall:members     [Set]        user-1, user-2, ...
campaign:2026-fall:ranking     [Sorted Set] user-1→150, user-2→110, ...
campaign:2026-fall:events      [Stream]     các lần tham gia, cộng điểm, ...
```

Một vài thao tác tương ứng:

```redis
HSET campaign:2026-fall name "Autumn Campaign" status "OPEN"
SADD campaign:2026-fall:members "user-1" "user-2"
SISMEMBER campaign:2026-fall:members "user-1"

ZADD campaign:2026-fall:ranking 150 "user-1" 110 "user-2"
ZRANGE campaign:2026-fall:ranking 0 9 REV WITHSCORES

XADD campaign:2026-fall:events * userId "user-1" action "JOIN"
```

Thiết kế này thể hiện rõ một nguyên tắc: **khóa là địa chỉ truy cập, còn kiểu dữ liệu là tập thao tác tối ưu cho nhu cầu của ứng dụng**. Việc chọn Hash, Set, Sorted Set hay Stream dựa trên cách đọc/ghi mong muốn sẽ giúp mô hình Redis dễ hiểu và giúp code Spring Data Redis sử dụng đúng nhóm API.
