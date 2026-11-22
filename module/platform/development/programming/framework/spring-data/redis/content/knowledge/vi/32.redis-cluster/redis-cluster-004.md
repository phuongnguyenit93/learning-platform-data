# Hash tag để đặt nhiều khóa cùng slot trong Redis Cluster với Spring Data Redis

## 1. Vấn đề cần giải quyết

Khi chuyển từ Redis standalone sang **Redis Cluster**, ứng dụng không còn có thể giả định mọi key đều nằm trên cùng một Redis server. Redis Cluster phân chia không gian khóa thành **16.384 hash slot**; các primary node chịu trách nhiệm phục vụ những slot khác nhau.

Một số lệnh hoạt động trên nhiều key cần tất cả key tham gia **cùng hash slot**. Nếu ứng dụng sử dụng hai tên key không được thiết kế trước:

```text
order:101:status
order:101:updatedAt
```

thì dù hai key cùng thuộc đơn hàng `101`, chúng **không được bảo đảm** nằm cùng slot. Một lời gọi `MGET`, `MSET` hoặc Lua script truy cập cả hai có thể gặp lỗi:

```text
CROSSSLOT Keys in request don't hash to the same slot
```

Redis Cluster cung cấp cơ chế **hash tag**: phần chuỗi không rỗng nằm trong cặp ngoặc nhọn `{...}` hợp lệ của tên key sẽ được dùng để tính slot thay cho toàn bộ tên key.

Ví dụ:

```text
order:{101}:status
order:{101}:updatedAt
order:{101}:items
```

Cả ba key có hash tag `101`, nên Redis tính slot từ cùng một chuỗi `101`. Nhờ vậy, chúng nằm cùng hash slot, bất kể phần tên trước hoặc sau `{101}` khác nhau.

**Hash tag không phải dấu hiệu tạo transaction, không phải kiểu dữ liệu mới, không phải Redis namespace vật lý và không phải công cụ phân tán dữ liệu tự động.** Nó chỉ là quy ước tên key làm thay đổi **đầu vào của phép tính hash slot**.

Bài học này trình bày cơ chế từ cấp Redis tới Spring Data Redis: cú pháp hash tag, kiểm tra slot, lựa chọn ranh giới aggregate, lệnh nhiều key, Lua/transaction, quy tắc key serializer, tải nóng trên một slot và các lỗi vận hành thường gặp.

### Kết quả học tập

Sau khi học, bạn có thể:

1. Giải thích Redis Cluster chia dữ liệu theo 16.384 hash slot và công thức xác định slot.
2. Chỉ ra phần nào của tên key được Redis dùng để hash khi có `{...}`.
3. Thiết kế nhóm key có cùng tag để sử dụng lệnh nhiều key và Lua script.
4. Phân biệt **cùng hash slot** với **cùng primary node**.
5. Dùng `CLUSTER KEYSLOT` để kiểm tra tên key trước khi đưa vào production.
6. Hiểu tại sao multi-key command vẫn lỗi dù client có cơ chế tự redirect `MOVED`/`ASK`.
7. Tổ chức key cho entity, tenant, order, cart, inventory theo đúng ranh giới tính nguyên tử.
8. Dùng `StringRedisTemplate` và `RedisScript` để thao tác các key cùng slot.
9. Nhận ra rủi ro tạo **hot slot** nếu dùng một tag quá rộng.
10. Thiết kế migration khi key cũ chưa có hash tag hoặc có tag không phù hợp.

## 2. Redis Cluster phân vùng theo hash slot thế nào?

Trong Redis Cluster, mỗi key được ánh xạ tới một giá trị nguyên thuộc khoảng:

```text
0 .. 16383
```

Số slot tổng cộng:

```text
16384 = 2^14
```

Về nguyên tắc, Redis sử dụng CRC16 trên byte của tên key hoặc hash tag hợp lệ, rồi lấy phần dư:

```text
HASH_SLOT = CRC16(hash_input_bytes) mod 16384
```

Trong công thức:

- `CRC16` là thuật toán CRC16 được Redis Cluster quy định; khi tự hiện thực cần dùng đúng biến thể tương thích với Redis, không dùng tùy tiện bất kỳ hàm CRC16 nào của thư viện.
- `hash_input_bytes` là toàn bộ tên key nếu không có hash tag hợp lệ, hoặc là phần byte bên trong cặp `{...}` được Redis chọn.
- `mod 16384` khiến kết quả nằm trong không gian 16.384 slot.
- Redis Cluster lưu bảng ánh xạ **slot → primary node** và có thể thay đổi bảng này khi resharding hoặc failover.

Hình dung:

```text
Key bytes
   |
   +--> Có hash tag hợp lệ?
   |        |
   |        +-- Có ---> Chỉ lấy byte trong {...}
   |        |
   |        +-- Không -> Lấy toàn bộ byte tên key
   |
   v
CRC16(...)
   |
   v
mod 16384
   |
   v
Slot 0..16383
   |
   v
Primary đang sở hữu slot
```

Ví dụ Redis Cluster có ba primary:

```text
Primary A: slots     0..5460
Primary B: slots  5461..10922
Primary C: slots 10923..16383
```

Đây là cách chia minh họa. Cấu hình Cluster thực tế có thể phân bố slot khác, có replica và có quá trình di chuyển slot giữa các node.

**Tên key không chọn trực tiếp một server.** Nó chọn một slot; slot được gán cho node hiện tại. Khi một slot chuyển sang node khác, những key thuộc slot ấy chuyển theo cơ chế Cluster, dù tên key và hash tag không đổi.

### 2.1. Không có quy tắc "cùng tiền tố thì cùng slot"

Các tên:

```text
order:101:status
order:101:items
order:101:total
```

đều có tiền tố `order:101:`, nhưng Redis không phân tích tiền tố để xác định aggregate. Nếu không có `{...}` hợp lệ, **toàn bộ tên** được đưa vào CRC16. Chỉ cần khác hậu tố, kết quả có thể khác slot.

Vì vậy:

```text
Giống tiền tố      != chắc chắn cùng slot
Giống tenant ID    != chắc chắn cùng slot
Giống order ID     != chắc chắn cùng slot
Cùng một hash tag  == cùng slot
```

Hai tên key ngẫu nhiên khác nhau vẫn **có thể trùng slot do collision modulo 16384**. Nhưng không nên dựa vào sự trùng hợp ngẫu nhiên: key naming phải làm rõ lý do hai key cần cùng slot.

### 2.2. "Cùng slot" khác "cùng node"

Một primary node thường quản lý nhiều slot. Hai key có slot khác nhau vẫn có thể tình cờ nằm trên cùng một primary tại thời điểm hiện tại.

Ví dụ:

```text
Key A -> slot 1000 -> Primary A
Key B -> slot 1001 -> Primary A
```

Cả hai cùng node, nhưng hai slot khác nhau. Redis Cluster vẫn có thể từ chối lệnh multi-key yêu cầu same-slot vì nó kiểm tra **slot**, không chỉ so sánh địa chỉ node.

Điều này còn quan trọng khi resharding: slot 1001 có thể chuyển sang node khác trong tương lai, trong khi slot 1000 ở lại node cũ. Thiết kế đúng không được dựa vào việc hai slot đang được một node phục vụ hôm nay.

## 3. Cú pháp hash tag `{...}`

Hash tag được nhận diện từ **byte của tên key** theo quy tắc của Redis Cluster.

Ví dụ:

```text
user:{u-42}:profile
user:{u-42}:settings
user:{u-42}:sessions
```

Phần dùng để tính CRC16 của cả ba:

```text
u-42
```

Phần còn lại của tên key vẫn được Redis giữ nguyên để phân biệt dữ liệu:

```text
user:{u-42}:profile   != user:{u-42}:settings
```

Hai key **khác nhau**, nhưng có **cùng slot**.

### 3.1. Quy tắc Redis chọn tag

Redis xử lý theo ý tưởng:

1. Tìm ký tự `{` đầu tiên trong tên key.
2. Tìm ký tự `}` đầu tiên nằm **sau** dấu `{` đó.
3. Nếu không tìm được `}`, hoặc phần nằm giữa hai dấu rỗng, dùng **toàn bộ tên key** để hash.
4. Nếu phần giữa không rỗng, chỉ hash phần đó.
5. Nếu có nhiều cặp ngoặc, các cặp sau **không tự động được dùng** để chọn lại tag.

Quy tắc này không phải parser cấu trúc JSON hoặc ngoặc nhọn lồng nhau. Redis không hiểu tenant, entity, UUID hay loại sự kiện; Redis chỉ xem các byte tên key.

### 3.2. Bảng ví dụ

| Tên key | Đầu vào dùng tính slot | Giải thích |
|---|---|---|
| `order:101:status` | Toàn bộ `order:101:status` | Không có hash tag |
| `order:{101}:status` | `101` | Cặp `{101}` hợp lệ |
| `order:{101}:items` | `101` | Cùng slot với key phía trên |
| `{101}:items` | `101` | Tag ở đầu tên key vẫn hợp lệ |
| `orders:{101}` | `101` | Tag ở cuối tên key vẫn hợp lệ |
| `a{101}b{202}c` | `101` | Chọn tag từ cặp đầu tiên |
| `a{}b` | Toàn bộ `a{}b` | Tag đầu tiên rỗng |
| `a{}b{101}` | Toàn bộ `a{}b{101}` | Không chuyển sang tag thứ hai nếu tag đầu tiên rỗng |
| `a{101` | Toàn bộ `a{101` | Không có dấu `}` đóng |
| `a}b{101}c` | `101` | Dấu `}` trước `{` không tạo tag |
| `a{abc}x` | `abc` | Phần ngoài ngoặc không ảnh hưởng slot |
| `b{abc}y` | `abc` | Cùng slot với `a{abc}x` |
| `a{ABC}x` | `ABC` | Không bảo đảm cùng slot với tag `abc` |

Ví dụ quan trọng:

```text
cart:{c-7}:items
cart:{c-7}:total
```

chắc chắn cùng hash slot.

Trong khi đó:

```text
cart:{c-7}:items
cart:{c-8}:total
```

không được bảo đảm cùng slot, bởi phần dùng để hash lần lượt là `c-7` và `c-8`.

### 3.3. Chỉ một tag được dùng để chọn slot

Giả sử key có cả tenant và order ID:

```text
tenant:{t-7}:order:{o-101}:status
```

Redis sử dụng **`t-7`**, không phải `o-101`, vì `{t-7}` là cặp tag hợp lệ đầu tiên.

Đây là điểm dễ gây lỗi trong thiết kế key:

- Nếu muốn phân vùng theo tenant, ví dụ trên thể hiện mong muốn đó.
- Nếu muốn phân vùng theo **mỗi order**, key trên lại không đúng ý: tất cả order của tenant `t-7` bị đặt vào một slot thay vì chia theo từng order.

Đặt tag theo đúng **ranh giới aggregate cần atomicity**, ví dụ:

```text
tenant:t-7:order:{t-7|o-101}:status
tenant:t-7:order:{t-7|o-101}:items
```

Cả hai dùng tag `t-7|o-101`. Phần `tenant:t-7:` nằm ngoài tag không can thiệp slot.

### 3.4. Tag không phải wildcard

Trong Redis naming:

```text
orders:{o-101}:status
```

dấu ngoặc nhọn làm nhiệm vụ chọn hash input.

Còn:

```text
orders:*
```

ký tự `*` có ý nghĩa glob trong những lệnh nhận pattern như `SCAN MATCH`, nhưng nó **không tự làm các key có tiền tố `orders:` cùng slot**.

Tên key và pattern phục vụ hai mục đích khác nhau:

- Hash tag: quyết định slot của **một key cụ thể**.
- Glob pattern: quyết định một thao tác tìm kiếm/subscribe phù hợp với **nhiều tên** nào đó.

Đừng nhầm `PatternTopic` của Pub/Sub hay `SCAN MATCH` với cơ chế hash tag.

## 4. Kiểm tra slot bằng CLUSTER KEYSLOT

Lệnh chẩn đoán quan trọng nhất:

```redis
CLUSTER KEYSLOT <key>
```

Ví dụ trong Redis CLI kết nối tới Cluster:

```redis
CLUSTER KEYSLOT order:{101}:status
CLUSTER KEYSLOT order:{101}:items
CLUSTER KEYSLOT order:{101}:updatedAt
```

Ba lời gọi phải trả **cùng một số slot**. Con số cụ thể không quan trọng bằng việc chúng giống nhau.

So sánh:

```redis
CLUSTER KEYSLOT order:101:status
CLUSTER KEYSLOT order:101:items
```

Hai tên không dùng hash tag có thể trả hai slot khác nhau.

Dùng CLI từ terminal:

```bash
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'order:{101}:status'
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'order:{101}:items'
```

Các host/port `127.0.0.1:7000` chỉ minh họa một Redis Cluster cục bộ; cần dùng địa chỉ thực trong môi trường triển khai.

**Lưu ý:** `CLUSTER KEYSLOT` đo slot dựa trên **tên key được truyền vào command**, không cần key đã tồn tại. Nó rất hữu ích để kiểm tra thiết kế trước khi ghi dữ liệu.

### 4.1. Xác nhận bằng MGET

Với key cùng tag:

```redis
SET order:{101}:status PENDING
SET order:{101}:updatedAt 2026-11-13T00:00:00Z
MGET order:{101}:status order:{101}:updatedAt
```

Trong Cluster, `MGET` có thể được phục vụ như một multi-key operation hợp lệ khi các key nằm cùng slot và các điều kiện khác của hệ thống được đáp ứng.

Đổi một key thành tên không cùng slot:

```redis
MGET order:{101}:status order:{102}:updatedAt
```

Nếu hai tag khác slot, Redis từ chối với `CROSSSLOT`. Hai tag khác nhau **có thể tình cờ hash về cùng một slot**, nên nếu muốn chứng minh lỗi cho một cặp cụ thể, hãy kiểm tra `CLUSTER KEYSLOT` của chúng trước.

Không nên xem việc một cặp tag khác nhau tình cờ hoạt động là một hợp đồng ổn định về ranh giới dữ liệu.

### 4.2. Không dùng CLUSTER KEYSLOT thay cho kiểm tra dữ liệu

Hai key cùng slot **chưa chắc đã tồn tại**, chưa chắc đúng kiểu Redis, và chưa chắc có giá trị hợp lệ. `CLUSTER KEYSLOT` chỉ giúp trả lời câu hỏi định tuyến.

Một quy trình chẩn đoán hợp lý:

```text
1. Kiểm tra key naming.
2. CLUSTER KEYSLOT từng key.
3. Kiểm tra node đang sở hữu slot.
4. Kiểm tra key có tồn tại và type gì.
5. Kiểm tra lệnh/API multi-key có hỗ trợ ở Cluster không.
6. Kiểm tra lỗi thực tế từ client/driver và topology.
```

## 5. Vì sao lệnh nhiều key gặp CROSSSLOT?

Trong standalone Redis, tất cả key ở cùng một không gian server logic. Lệnh:

```redis
MGET order:101:status order:101:updatedAt
```

thường không có rào cản slot, miễn key và command hợp lệ.

Trong Redis Cluster, mỗi key có slot riêng. Một số lệnh yêu cầu Redis xử lý **nhiều key trong một thao tác** mà không thể chia ra nhiều primary một cách trong suốt, bởi yêu cầu về ngữ nghĩa và tính nguyên tử.

Ví dụ thường cần cùng slot:

```redis
MGET key1 key2
MSET key1 value1 key2 value2
DEL key1 key2
EXISTS key1 key2
RENAME source destination
```

Ngoài ra, multi-key set operations, một số Sorted Set operations, scripting và transaction cũng chịu những ràng buộc riêng.

**Không phải mọi API nhận nhiều key đều bắt buộc luôn gửi một lệnh Redis multi-key.** Một client có thể có tính năng fan-out/split một số thao tác sang nhiều node, tùy implementation và phiên bản. Nhưng điều đó không làm kết quả trở thành một thao tác atomic xuyên slot.

Phân biệt hai trường hợp:

```text
Một lệnh Redis multi-key:
    MGET k1 k2
    -> cần tuân thủ ràng buộc lệnh trên Cluster.

Hai lệnh độc lập:
    GET k1
    GET k2
    -> cluster-aware client có thể gửi tới hai node,
       nhưng không có snapshot atomically consistent.
```

### 5.1. Ví dụ thiết kế không phù hợp

Key ban đầu:

```text
cart:77:items
cart:77:coupon
```

Ứng dụng muốn:

```redis
MGET cart:77:items cart:77:coupon
```

Do không có tag, hai key không được bảo đảm cùng slot. Trên Redis Cluster, lệnh có thể thất bại.

Thiết kế lại:

```text
cart:{77}:items
cart:{77}:coupon
```

Giờ mọi key trong giỏ hàng 77 cùng hash từ `77`.

Tuy nhiên, kết quả này đi kèm một quyết định kiến trúc: các key thuộc cùng một giỏ hàng sẽ không được phân tán giữa nhiều primary. Đó là cái giá có chủ đích để đổi lấy khả năng multi-key atomic operations trong phạm vi giỏ hàng.

### 5.2. Multi-key không đồng nghĩa multi-object toàn hệ thống

Ví dụ cần chuyển tài nguyên giữa hai ví khác nhau:

```text
wallet:{u-1}:balance
wallet:{u-2}:balance
```

Hai key có tag khác nhau, thường thuộc các slot khác nhau. Việc cùng là kiểu `wallet` không làm phép chuyển tiền trở thành một transaction atomic xuyên shard.

Có thể cố tình đặt cả hai dưới một tag chung, nhưng nếu làm vậy cho mọi user, ta tạo một hot slot toàn hệ thống. Khi cần transaction xuyên nhiều entity phân tán, thường phải xem xét database transaction ở nguồn dữ liệu, kiến trúc saga/compensation, hoặc thay đổi ranh giới aggregate.

## 6. Hash tag hỗ trợ atomicity, nhưng không tự cung cấp atomicity

Đây là phân biệt cực kỳ quan trọng:

```text
Cùng hash slot
    -> điều kiện định tuyến cần thiết cho nhiều lệnh atomic/multi-key.

Cùng hash slot
    != mọi chuỗi GET -> kiểm tra -> SET tự nhiên trở thành atomic.
```

Ví dụ hai key cùng slot:

```text
stock:{sku-42}:available
stock:{sku-42}:reserved
```

Java thực hiện:

```text
GET stock:{sku-42}:available
IF available >= 3
    DECRBY stock:{sku-42}:available 3
    INCRBY stock:{sku-42}:reserved 3
```

Dù các key cùng slot, nếu đây là nhiều lời gọi Redis độc lập, hai request có thể xen kẽ:

```text
Request A GET available -> 5
Request B GET available -> 5
Request A giảm 3
Request B giảm 3
```

Điều kiện stock có thể bị vi phạm.

Muốn thao tác kiểm tra và cập nhật là một đơn vị được thực thi không xen lệnh, cần **Lua script, transaction được dùng đúng cách**, hoặc atomic command phù hợp.

Hash tag làm các key liên quan **có thể** tham gia các cơ chế ấy trong Cluster; nó không thực hiện thay logic nghiệp vụ.

### 6.1. Một Redis command riêng lẻ

Các lệnh Redis được xử lý với tính nguyên tử ở mức command theo cơ chế Redis. Ví dụ, nếu một `MSET` hợp lệ trên các key cùng slot, bản thân `MSET` có ngữ nghĩa cập nhật nhiều key trong một command.

Nếu Java chia thành hai `SET` độc lập, không được suy rằng chúng atomic với nhau chỉ vì hai key có cùng tag.

### 6.2. MULTI/EXEC

Trong Cluster, các transaction `MULTI`/`EXEC` tác động nhiều key phải tuân thủ các ràng buộc slot của Redis Cluster. Những key khác slot không thể được gom thành một transaction phân tán bằng cách gọi `MULTI` trên một connection.

Ví dụ dùng các key:

```text
order:{101}:status
order:{101}:updatedAt
```

để thiết kế transaction trong cùng slot.

Các key như:

```text
order:{101}:status
order:{102}:updatedAt
```

không được bảo đảm cùng slot, nên không được coi là tập transaction hợp lệ.

Thêm một chú ý: Redis transaction không có cơ chế rollback SQL-style cho các lệnh đã chạy thành công trước một runtime error sau đó. Nếu phải bảo vệ invariant nghiệp vụ, cần validate đầu vào, trạng thái dữ liệu và xử lý lỗi thật cẩn thận.

### 6.3. WATCH

`WATCH` hỗ trợ optimistic locking dựa trên việc theo dõi thay đổi key trước `MULTI/EXEC`. Nhưng nếu workflow liên quan nhiều key khác slot, hash tag vẫn là điều kiện cần cho một thiết kế transaction đúng trong Cluster.

`WATCH` không tự mang trạng thái quan sát qua nhiều primary thành một transaction toàn cục.

### 6.4. Lua script và Redis Functions

Lua script có thể kiểm tra và cập nhật nhiều key không bị lệnh khác xen vào trong thời gian thực thi. Tuy nhiên, trong Redis Cluster:

- Các Redis key mà script truy cập cần được khai báo rõ qua `KEYS`.
- Các key liên quan phải tương thích với ràng buộc cùng hash slot.
- Đưa một tên key ẩn trong `ARGV` rồi dựng lệnh Redis trong script không phải cách hợp lệ để lách routing.
- Script không tạo transaction phân tán giữa các primary.
- Nếu script thực hiện một số ghi rồi gặp runtime error, những ghi đã xảy ra không mặc nhiên bị rollback.

Redis Functions cũng chịu những ràng buộc phân vùng dữ liệu tương tự đối với key access.

## 7. Thiết kế key theo aggregate, không theo toàn bộ hệ thống

Câu hỏi quan trọng nhất khi chọn hash tag:

> **Những key nào thực sự cần được đọc/cập nhật trong cùng một thao tác atomic hoặc một lệnh multi-key?**

Đó thường là các key thuộc **một aggregate**, **một session**, **một order**, **một shopping cart**, hoặc **một tài nguyên có transaction boundary rõ ràng**.

Ví dụ:

```text
order:{o-101}:status
order:{o-101}:items
order:{o-101}:total
order:{o-101}:version
```

Nhóm này có tag `o-101`; mỗi order khác dùng tag khác:

```text
order:{o-102}:status
order:{o-102}:items
order:{o-102}:total
order:{o-102}:version
```

Redis có thể phân phối các order trên nhiều slot. Nhưng trong mỗi order, các key vẫn được đặt cùng slot.

### 7.1. Cấu trúc khuyến nghị

```text
<domain>:<optional-context>:{<aggregate-id>}:<component>
```

Ví dụ:

```text
order:{o-101}:status
order:{o-101}:items
cart:{c-77}:items
cart:{c-77}:coupon
inventory:{sku-42}:available
inventory:{sku-42}:reserved
```

Tên thực tế cần tuân theo quy ước nhất quán của dự án; Redis chỉ quan tâm bytes và cặp ngoặc nhọn.

### 7.2. Có cần tenant ID trong tag?

Nếu `orderId` là duy nhất toàn hệ thống, chỉ dùng order ID có thể đủ. Nếu order ID chỉ duy nhất **bên trong từng tenant**, cần ghép tenant và order vào định danh tag:

```text
tenant:t-7:order:{t-7|o-101}:status
tenant:t-7:order:{t-7|o-101}:items

tenant:t-8:order:{t-8|o-101}:status
tenant:t-8:order:{t-8|o-101}:items
```

Ở đây:

- `t-7|o-101` và `t-8|o-101` là hai hash tag khác nhau.
- Không xảy ra dùng nhầm tag cho hai order ID giống nhau ở tenant khác.
- Các component của cùng một order/tenant vẫn cùng slot.

**Tag không tự tạo unique constraint**; hai tên key có tag giống nhau vẫn là hai key phân biệt nếu phần còn lại khác. Thiết kế định danh business phải chịu trách nhiệm tránh collision/hợp nhất aggregate sai.

### 7.3. Dùng hash tag theo tenant khi nào?

Một phương án:

```text
tenant:{t-7}:config
tenant:{t-7}:quota
tenant:{t-7}:audit
tenant:{t-7}:order:o-101
tenant:{t-7}:order:o-102
```

Tất cả đều hash từ `t-7`.

Cách này có ích **nếu thật sự cần atomic multi-key operations bao trùm dữ liệu toàn tenant** và kích thước/tải của tenant được kiểm soát. Nhưng nếu tenant có hàng triệu order và QPS rất lớn, nó sẽ dồn toàn bộ workload vào một slot/primary, đi ngược mục đích phân tán Redis Cluster.

Không có nguyên tắc chung “mọi key của một tenant đều nên cùng tag”. Mức hạt tag cần dựa trên **đơn vị cần atomicity**, không chỉ dựa trên mô hình phân quyền/namespace.

## 8. Chọn kích thước nhóm key như thế nào?

Có ba lựa chọn thường gặp:

| Thiết kế tag | Ví dụ | Lợi thế | Rủi ro |
|---|---|---|---|
| Tag theo toàn hệ thống | `app:{global}:...` | Mọi key của app cùng slot | Cực dễ hot slot, gần như mất lợi ích sharding |
| Tag theo tenant | `tenant:{t-7}:...` | Có thể xử lý nhiều key tenant cùng slot | Tenant lớn tạo hotspot |
| Tag theo aggregate | `order:{t-7|o-101}:...` | Atomicity trong một order; phân phối nhiều order | Không atomic xuyên hai order |
| Tag theo entity nhỏ | `sku:{sku-42}:...` | Tốt cho inventory từng SKU | Hot SKU có thể tạo hot slot |
| Không hash tag | `order:o-101:status` | Phân phối tự nhiên theo toàn key | Multi-key cùng order không được đảm bảo |

**Khuyến nghị thiết kế:** bắt đầu từ ranh giới nghiệp vụ cần thao tác đồng thời. Dùng tag đủ nhỏ để tránh gom dữ liệu không liên quan, nhưng đủ rộng để các key cần atomicity chung một slot.

Ví dụ với giỏ hàng:

```text
cart:{c-77}:items      -- Redis Set/Hash
cart:{c-77}:coupon     -- Redis String
cart:{c-77}:totals     -- Redis Hash
cart:{c-77}:version    -- Redis String
```

Nếu yêu cầu chuyển trạng thái giỏ hàng bằng script, thiết kế này cho phép truy cập nhiều component của **cùng cart**.

Nhưng muốn cập nhật cart `c-77` và tồn kho của hàng chục SKU độc lập trong một transaction, các key tồn kho có thể thuộc nhiều slot. Không thể dùng một tag nhỏ cho cả hai mô hình đồng thời mà không đánh đổi phân phối tải hoặc thay đổi kiến trúc.

## 9. Ví dụ Spring Data Redis: đọc nhiều key bằng StringRedisTemplate

Trong Spring Boot, có thể dùng `spring-boot-starter-data-redis` với Lettuce và `StringRedisTemplate`.

Dependency Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

Cấu hình Redis Cluster minh họa:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - 127.0.0.1:7000
          - 127.0.0.1:7001
          - 127.0.0.1:7002
      timeout: 3s
```

Đây là ví dụ topology phát triển; không dùng `127.0.0.1` làm địa chỉ production nếu application không chạy trong cùng môi trường. Các tùy chọn auto-configuration cụ thể phụ thuộc phiên bản Spring Boot và Lettuce.

Service:

```java
package com.example.order;

import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderSnapshotCache {

    private final StringRedisTemplate redis;

    public OrderSnapshotCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void write(String orderId, String status, String updatedAt) {
        String tag = "{" + orderId + "}";

        redis.opsForValue().set(
            "order:" + tag + ":status",
            status
        );

        redis.opsForValue().set(
            "order:" + tag + ":updatedAt",
            updatedAt
        );
    }

    public List<String> read(String orderId) {
        String tag = "{" + orderId + "}";

        return redis.opsForValue().multiGet(
            List.of(
                "order:" + tag + ":status",
                "order:" + tag + ":updatedAt"
            )
        );
    }
}
```

Với tag giống nhau, các key được thiết kế cùng slot. Lệnh `multiGet` thường ánh xạ sang `MGET` ở cấp Redis theo API tương ứng.

**Lưu ý quan trọng:** method `write` trên dùng hai `SET` độc lập, nên **không phải atomic update giữa hai key**. Nếu một lời gọi thành công rồi lời gọi kia thất bại, cache có thể chứa trạng thái không đồng bộ. Chỉ dùng cách này khi chấp nhận sự bất nhất ngắn hoặc có chiến lược khác bảo vệ invariant.

Nếu yêu cầu hai key được cập nhật cùng một cách nhất quán, dùng `MSET` trong cùng slot hoặc script/transaction được thiết kế đúng.

### 9.1. `multiSet` với hai key cùng tag

Ví dụ:

```java
import java.util.LinkedHashMap;
import java.util.Map;

String tag = "{o-101}";

Map<String, String> values = new LinkedHashMap<>();
values.put("order:" + tag + ":status", "PAID");
values.put("order:" + tag + ":updatedAt", "2026-11-13T02:00:00Z");

stringRedisTemplate.opsForValue().multiSet(values);
```

Trong Redis Cluster, các key của multi-key `MSET` cần nằm cùng slot. Cách đặt tag giúp đáp ứng điều kiện đó.

Đừng suy rằng một `Map` Java cùng giữ hai entry thì Redis tự đưa chúng về cùng node/slot. Nếu bỏ `{o-101}`, key naming không còn bảo đảm điều kiện của `MSET`.

### 9.2. Key serializer quyết định slot

`StringRedisTemplate` sử dụng serializer chuỗi cho key và value, nên tên Java như:

```text
order:{o-101}:status
```

được gửi dưới dạng bytes chuỗi phù hợp, và Redis nhìn thấy cặp `{o-101}` như mong muốn.

Với một `RedisTemplate<String, Object>` cấu hình khác, **key serializer có thể không phải String**. Nếu key được đóng gói bằng Java native serialization, byte thực tế của Redis key không giống chuỗi Java hiển thị, và việc Redis tìm dấu `{`/`}` có thể không hoạt động theo ý định.

Hash slot luôn tính từ **wire bytes của Redis key**, không phải từ khái niệm String phía Java.

Để dùng hash tag có thể dự đoán, thường cấu hình `StringRedisSerializer` cho key:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class RedisTemplateConfiguration {

    @Bean
    RedisTemplate<String, Object> appRedisTemplate(
            RedisConnectionFactory factory) {

        RedisTemplate<String, Object> template =
            new RedisTemplate<>();

        template.setConnectionFactory(factory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setHashKeySerializer(new StringRedisSerializer());

        // Chọn value/hashValue serializer theo schema riêng
        // của ứng dụng (JSON, String, binary...).
        // Không trộn định dạng dữ liệu đã tồn tại.
        template.afterPropertiesSet();
        return template;
    }
}
```

Đây là minh họa việc thống nhất **key serializer**; ứng dụng thực cần cấu hình value serializer rõ theo hợp đồng và các bean đang sử dụng. Cấu hình key serializer không tự chuyển đổi các key cũ đã được lưu với encoding khác.

### 9.3. Tên key có `{...}` nhưng vẫn không cùng slot?

Nguyên nhân có thể là:

- Một service dùng key serializer khác.
- Một service chèn thêm cặp `{...}` trước tag mong muốn.
- `orderId` chứa ký tự `{` hoặc `}` chưa được chuẩn hóa.
- Tag có chữ hoa/chữ thường khác.
- Một service dùng `o-101`, service khác dùng `tenant-7|o-101`.
- Một service đổi Unicode normalization hoặc encoding của ID.
- Có key được tạo bởi tooling/CLI khác tên thực tế ứng dụng gửi.
- Một số key không có tag hoặc tag rỗng.

Cần xem **byte key và đầu vào hash** thực tế, không chỉ nhìn log của object Java.

## 10. Tạo key qua một KeyFactory thống nhất

Để tránh mỗi service tự ghép tên key theo một kiểu, nên tạo một component xây dựng tên key.

Ví dụ Java:

```java
package com.example.order;

import java.util.Objects;
import java.util.regex.Pattern;

public final class OrderRedisKeys {

    private static final Pattern SAFE_ID =
        Pattern.compile("[A-Za-z0-9_-]+");

    private OrderRedisKeys() {
    }

    public static String status(
            String tenantId,
            String orderId) {

        return prefix(tenantId, orderId) + ":status";
    }

    public static String updatedAt(
            String tenantId,
            String orderId) {

        return prefix(tenantId, orderId) + ":updatedAt";
    }

    public static String items(
            String tenantId,
            String orderId) {

        return prefix(tenantId, orderId) + ":items";
    }

    private static String prefix(
            String tenantId,
            String orderId) {

        requireSafeId(tenantId);
        requireSafeId(orderId);

        String tag = tenantId + "|" + orderId;

        return "order:{" + tag + "}";
    }

    private static void requireSafeId(String value) {
        Objects.requireNonNull(value, "id");

        if (!SAFE_ID.matcher(value).matches()) {
            throw new IllegalArgumentException(
                "Unsupported identifier characters"
            );
        }
    }
}
```

Cách sử dụng:

```java
String statusKey = OrderRedisKeys.status("t-7", "o-101");
String updatedKey = OrderRedisKeys.updatedAt("t-7", "o-101");
String itemsKey = OrderRedisKeys.items("t-7", "o-101");
```

Kết quả:

```text
order:{t-7|o-101}:status
order:{t-7|o-101}:updatedAt
order:{t-7|o-101}:items
```

Cả ba cùng tag `t-7|o-101`.

Ở đây regex ID chỉ là **quy ước ví dụ**; các ID Unicode hoặc định dạng khác vẫn có thể dùng được nếu ứng dụng có quy tắc encode/canonicalization thống nhất. Điểm chính là **không để input không tin cậy thay đổi cấu trúc ngoặc nhọn của tag**.

### 10.1. Vì sao cần tránh ngoặc nhọn trong dữ liệu đầu vào?

Giả sử ứng dụng định tạo:

```text
order:{tenant|orderId}:status
```

nhưng `tenantId` hoặc `orderId` được ghép từ dữ liệu chưa kiểm soát có ký tự `{` hoặc `}`. Khi đó cặp ngoặc đầu tiên mà Redis nhận diện có thể không phải tag mong muốn.

Ví dụ dạng lỗi:

```text
prefix:{unexpected}:order:{t-7|o-101}:status
```

Redis chọn `unexpected`, không chọn `t-7|o-101`.

Vì vậy, một KeyFactory tốt cần:

1. Chuẩn hóa identifier ở một chỗ.
2. Loại hoặc encode các ký tự làm thay đổi cấu trúc tên, nhất là `{` và `}`.
3. Dùng format nhất quán cho mọi service.
4. Tách data identifier khỏi phần cú pháp `{...}` mà application tạo.
5. Kiểm soát cách ghép nhiều ID để tránh ambiguity.

### 10.2. Dấu phân cách trong tag cũng phải rõ

Nếu dùng:

```text
{tenant|order}
```

mà giá trị tenant có thể chứa `|`, sẽ khó phân biệt các thành phần khi debug hoặc khi tạo canonical ID.

Có thể:

- Cấm `|` trong identifier.
- Encode từng thành phần bằng Base64url hoặc một canonical escaping scheme, loại bỏ khả năng chèn `{`/`}`.
- Dùng UUID/ID kỹ thuật đã chuẩn hóa.
- Dùng length-prefix format nếu cần kết hợp các phần có ký tự tùy ý.

Một giải pháp tốt phải tạo **cùng tag cho cùng aggregate** trên mọi instance và **khác tag khi aggregate thật sự khác**, trừ khả năng collision CRC16 không thể tránh hoàn toàn.

## 11. Lua script nhiều key trong cùng slot

Một trường hợp cần atomicity là chuyển trạng thái order từ `PENDING` sang `PAID` và cập nhật `updatedAt` cùng lúc **chỉ nếu trạng thái hiện tại đúng**.

Hai key:

```text
order:{t-7|o-101}:status
order:{t-7|o-101}:updatedAt
```

Lua script (lưu dưới `src/main/resources/scripts/transition-order.lua`):

```lua
-- KEYS[1]: order status
-- KEYS[2]: order updatedAt
-- ARGV[1]: expected current status
-- ARGV[2]: next status
-- ARGV[3]: new updatedAt text

if #KEYS ~= 2 or #ARGV ~= 3 then
    return redis.error_reply('INVALID_ARGUMENT_COUNT')
end

local current = redis.call('GET', KEYS[1])

if current ~= ARGV[1] then
    return 0
end

redis.call(
    'MSET',
    KEYS[1], ARGV[2],
    KEYS[2], ARGV[3]
)

return 1
```

Hợp đồng trả về:

| Redis result | Ý nghĩa |
|---:|---|
| `1` | Đã chuyển trạng thái và cập nhật timestamp |
| `0` | Trạng thái hiện tại khác `expected`; không cập nhật |
| Error reply | Sai contract, Redis command lỗi hoặc điều kiện vận hành |

Mục đích dùng Lua là gộp **đọc điều kiện** và **cập nhật nhiều key** thành một thao tác không bị lệnh khác xen giữa. `MSET` tự có ngữ nghĩa cập nhật nhiều key trong một command, nhưng không có phần kiểm tra `current == expected`; đó là lý do script hữu ích.

### 11.1. Khai báo script trong Spring Boot

```java
package com.example.order;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class OrderScriptConfiguration {

    @Bean
    RedisScript<Long> transitionOrderScript() {
        return RedisScript.of(
            new ClassPathResource(
                "scripts/transition-order.lua"
            ),
            Long.class
        );
    }
}
```

Khai báo `Long.class` để Spring Data Redis diễn giải Redis integer reply tương ứng với `return 0` hoặc `return 1`.

### 11.2. Gọi bằng StringRedisTemplate

```java
package com.example.order;

import java.time.Instant;
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class OrderTransitionService {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> transitionOrderScript;

    public OrderTransitionService(
            StringRedisTemplate redis,
            RedisScript<Long> transitionOrderScript) {
        this.redis = redis;
        this.transitionOrderScript = transitionOrderScript;
    }

    public boolean markPaid(
            String tenantId,
            String orderId) {

        String statusKey =
            OrderRedisKeys.status(tenantId, orderId);

        String updatedAtKey =
            OrderRedisKeys.updatedAt(tenantId, orderId);

        Long result = redis.execute(
            transitionOrderScript,
            List.of(statusKey, updatedAtKey),
            "PENDING",
            "PAID",
            Instant.now().toString()
        );

        if (result == null) {
            throw new IllegalStateException(
                "Lua did not return an expected status"
            );
        }

        return result == 1L;
    }
}
```

`OrderRedisKeys` là KeyFactory ở phần trước. Hai key truyền qua `List.of(...)` sử dụng **cùng hash tag**. `ARGV` chỉ mang dữ liệu nghiệp vụ, không dùng để giấu key name.

Khi muốn thử:

```redis
SET order:{t-7|o-101}:status PENDING
```

Sau đó gọi `markPaid("t-7", "o-101")`; script có thể chuyển trạng thái thành `PAID` và ghi `updatedAt`.

Nếu đồng thời có hai request `markPaid`, request tới sau có thể thấy trạng thái đã đổi và nhận `0`, thay vì cả hai đều thấy `PENDING` rồi thay đổi độc lập.

### 11.3. Giới hạn vẫn tồn tại

- Hai key cần cùng slot; hash tag giúp đảm bảo điều kiện định tuyến.
- Script không tạo transaction với database SQL, HTTP service hay queue bên ngoài.
- Nếu script gặp runtime error sau những thao tác ghi, Redis không tự rollback những lệnh đã thành công trước đó theo kiểu SQL transaction.
- Nếu client timeout, Redis có thể đã thực thi script nhưng response chưa về; cần thiết kế thao tác có tính idempotent hoặc kiểm tra trạng thái.
- Nếu application bổ sung key thứ ba, key ấy cũng phải được khai báo trong `KEYS` và cùng slot.
- Script chạy lâu có thể ảnh hưởng latency Redis; tránh gọi lệnh phức tạp hoặc vòng lặp không giới hạn trên dữ liệu lớn.

## 12. Cách đặt tên key ảnh hưởng RedisScript KEYS/ARGV

Một lỗi thường gặp là truyền key dưới dạng argument:

```java
redis.execute(script, List.of(statusKey), updatedAtKey);
```

và trong Lua:

```lua
redis.call('SET', ARGV[1], 'NEW')
```

Về mặt thiết kế Cluster, đây không phải cách đúng để khai báo key script truy cập. Redis Cluster cần biết các key của script để áp dụng điều kiện hash slot và định tuyến.

Cách rõ ràng:

```java
redis.execute(
    script,
    List.of(statusKey, updatedAtKey),
    "NEW"
);
```

Lua:

```lua
redis.call('SET', KEYS[1], ARGV[1])
redis.call('SET', KEYS[2], ARGV[1])
return 1
```

Trên Redis Cluster, mọi Redis key mà script thao tác cần được xác định rõ từ đầu, không được tự tính key mới từ dữ liệu chứa trong Redis hoặc giấu trong JSON `ARGV` rồi truy cập key ở slot tùy ý.

### 12.1. Giải tuần tự hóa giá trị khác hash slot

Redis tính slot theo **bytes tên key**. Còn dữ liệu lưu trong value có thể dùng String, JSON hoặc binary serializer.

Đối với script:

```lua
local state = redis.call('GET', KEYS[1])
```

nếu value trước đó được ghi bằng JDK serialization, `state` không phải text `"PENDING"` thuần. Việc `state == ARGV[1]` có thể sai dù Java object logic trông giống nhau.

Vì vậy:

- Thống nhất **key serializer** để hash tag được nhận diện đúng.
- Thống nhất **value/args serialization** để Lua hiểu payload.
- Thống nhất **result serializer/RedisScript result type** để Java nhận đúng response.

Đây là ba yêu cầu khác nhau. Cùng slot không tự giải quyết lỗi serialization.

## 13. Các loại dữ liệu và lệnh khác cũng cần xem slot

Hash tag không chỉ dành cho String value và `MGET`.

Ví dụ một cart:

```text
cart:{c-77}:items        -> Redis Hash hoặc Set
cart:{c-77}:coupon       -> Redis String
cart:{c-77}:discounts    -> Redis Hash
cart:{c-77}:total        -> Redis String
```

Một Lua script có thể truy cập các key đó bằng `HGETALL`, `GET`, `HSET`, `SET` và các command phù hợp để thực hiện một thao tác giỏ hàng.

Với set intersection:

```text
user:{u-42}:follows
user:{u-42}:followers
```

có thể thực hiện những multi-key set operations phù hợp nếu cả hai key cùng slot.

Với Sorted Set:

```text
leaderboard:{season-2026}:points
leaderboard:{season-2026}:bonuses
```

có thể hữu ích khi cần thao tác nhiều Sorted Set của **cùng mùa**. Nhưng nếu mọi season cùng dùng tag `{leaderboard}`, toàn bộ tải của chúng có nguy cơ dồn một slot.

### 13.1. Đừng gom các key không liên quan chỉ để lệnh chạy

Lựa chọn sai:

```text
order:{global}:101:status
order:{global}:102:status
order:{global}:103:status
```

Dù có thể dùng lệnh multi-key trên chúng, bạn đã đặt mọi order vào một slot. Cần hỏi liệu ứng dụng thực sự cần một transaction giữa **mọi order** hay không.

Nếu chỉ cần hiển thị danh sách nhiều order, thường có thể:

- Đọc từng key qua cluster-aware client.
- Dùng một materialized view hoặc index riêng.
- Dùng database/search system phù hợp cho truy vấn.
- Dùng batch/pipeline được driver hỗ trợ, chấp nhận không có snapshot atomic xuyên slot.

Dùng hash tag quá rộng để “tiện MGET” có thể làm Redis Cluster mất khả năng scale.

### 13.2. TTL của các key cùng tag vẫn độc lập

Ví dụ:

```redis
SET session:{s-101}:state ACTIVE EX 60
SET session:{s-101}:lastSeen 2026-11-13T00:00:00Z EX 120
```

Hai key cùng slot nhưng có TTL riêng. Hash tag **không gom TTL, không tạo atomic expiration và không tự dọn tất cả key của aggregate cùng một lúc**.

Nếu nghiệp vụ yêu cầu toàn bộ state một session hết hạn đồng thời, có thể:

- Lưu state vào **một key Hash** với một TTL.
- Cấp cùng deadline cho các key bằng thao tác phù hợp và chấp nhận điều kiện vận hành.
- Để logic đọc kiểm tra deadline trung tâm.
- Dùng Lua/transaction khi cần thay đổi thời hạn của nhiều key trong một bước same-slot.

Tuy vậy, expiration notification không phải một callback chính xác theo thời gian và không bảo đảm mọi key cùng tag bị xóa vật lý tại đúng một mili giây.

## 14. Một key Hash hay nhiều key cùng hash tag?

Giả sử đơn hàng có trạng thái, tổng tiền, timestamp và một số trường phụ:

**Phương án A — một Redis Hash:**

```text
order:o-101
    status = PENDING
    total = 500000
    updatedAt = ...
```

**Phương án B — nhiều Redis key cùng tag:**

```text
order:{o-101}:status
order:{o-101}:total
order:{o-101}:updatedAt
```

So sánh:

| Tiêu chí | Một Redis Hash | Nhiều key cùng hash tag |
|---|---|---|
| Số Redis key | Ít | Nhiều |
| TTL tổng thể | Một TTL trên key Hash | Mỗi key có TTL riêng |
| Nhiều field | Dùng `HGET`, `HSET`, `HMGET` | Có thể dùng `MGET`, Lua hoặc multi-key |
| Cùng slot | Tự nhiên vì là một key | Phải tuân theo hash tag |
| Bộ nhớ metadata | Có thể tiết kiệm hơn tùy dữ liệu/encoding | Nhiều key có overhead |
| Cập nhật một field | `HSET` | `SET` key tương ứng |
| Kiểu dữ liệu khác nhau | Cùng trong Hash field-value | Có thể phối hợp Set, Hash, ZSet, String |
| Khả năng tự do TTL từng thành phần | Hạn chế theo key TTL thông thường | Linh hoạt hơn |
| Transaction nhiều thành phần | Các thao tác trên một key dễ quản lý hơn | Có thể cần script/transaction same-slot |

Nên cân nhắc **một Hash** nếu dữ liệu vốn là một object nhỏ và cần cùng TTL. Chọn **nhiều key cùng tag** khi các thành phần có data type, vòng đời hoặc pattern truy cập khác nhau và cần thao tác multi-key trong một aggregate.

Hash tag là công cụ giúp nhiều key cùng slot, **không phải lý do để tách một object thành nhiều key khi không có lợi ích rõ ràng**.

## 15. Rủi ro hot slot và mất cân bằng tải

Một hash slot thuộc một primary tại một thời điểm. Khi rất nhiều key/công việc được gắn cùng tag, chúng hội tụ vào **một slot** và do đó cùng một primary.

Ví dụ rất rộng:

```text
order:{all-orders}:1
order:{all-orders}:2
order:{all-orders}:3
...
```

Tất cả hash từ `all-orders`.

Dù Redis Cluster có nhiều primary, lượng thao tác cho các key này tập trung tại node sở hữu slot đó. Kết quả có thể là:

- CPU node đó cao hơn các node còn lại.
- Network đến node đó tăng.
- Latency p95/p99 cao cho nhóm key.
- Memory phân bố lệch.
- Resharding một slot quá lớn trở nên tốn kém.
- Scale bằng cách thêm primary không tự phân tán các key đang bị buộc chung tag.

### 15.1. Tag có cardinality thấp

Một tag theo `region` hoặc `tenant` có thể tạo ít nhóm:

```text
{north}
{central}
{south}
```

Nếu toàn hệ thống chỉ có ba tag, dữ liệu chủ yếu sử dụng tối đa ba slot, không tận dụng đầy đủ 16.384 slot.

Tag theo order ID có cardinality lớn hơn:

```text
{t-7|o-101}
{t-7|o-102}
{t-8|o-103}
...
```

sẽ phân tán nhiều aggregate trên không gian slot theo hàm hash.

**Cardinality cao không tự bảo đảm cân bằng QPS.** Một aggregate đơn lẻ cực nóng vẫn tập trung vào một slot. Ví dụ một SKU bán chạy có thể tạo hot slot dù mỗi SKU có tag riêng.

### 15.2. Dữ liệu phân tán không đồng nghĩa workload phân tán đều

Giả sử có 100.000 order với tag theo order ID, nhưng 80% traffic lại tập trung vào `order:{o-hot}:...`. Slot của `o-hot` trở thành hot slot.

Hash tag giúp đặt những key cần atomicity cùng nhau, nhưng không thể chia **một aggregate duy nhất** ra nhiều slot mà vẫn giữ atomicity multi-key kiểu Redis Cluster theo cách cũ.

Các giải pháp khi một aggregate nóng:

- Giảm số Redis commands trên hot path.
- Dùng một key/data type phù hợp thay vì nhiều thao tác.
- Cache ở tầng ứng dụng nếu workload cho phép.
- Partition read-heavy data theo mô hình chấp nhận eventual consistency.
- Thiết kế sharded counters khi nghiệp vụ chấp nhận tổng hợp không atomic tức thì.
- Dùng database/transactional service khác nếu cần tính nhất quán mạnh xuyên partitions.
- Cân nhắc thay đổi aggregate boundary nếu mô hình nghiệp vụ cho phép.

Đừng giải quyết hot slot bằng cách tùy tiện đổi tag cho vài key trong cùng transaction: như vậy sẽ làm mất same-slot invariant.

### 15.3. Kiểm tra tải thay vì chỉ nhìn số key

`CLUSTER COUNTKEYSINSLOT` có thể cho biết số key trong một slot tại node phù hợp, nhưng **số lượng key không trực tiếp phản ánh QPS hay CPU**. Một key nóng có thể gây tải lớn hơn hàng nghìn key ít truy cập.

Cần xem:

- Command rate và latency theo node/slot/key nếu telemetry hỗ trợ.
- Redis CPU, memory, network và evictions.
- Client-side latency, timeout và redirect.
- Phân bố slot giữa primary.
- Các hot key/command và access pattern.
- Số lượng multi-key script, thời gian chạy script và số request đồng thời.

Một ứng dụng đặt hash tag tốt về mặt correctness vẫn có thể cần tối ưu về performance.

## 16. Chọn một ranh giới transaction thực tế

Xét dịch vụ đặt hàng với các nhóm dữ liệu:

```text
Order:
    order:{o-101}:status
    order:{o-101}:total
    order:{o-101}:items

Inventory:
    stock:{sku-42}:available
    stock:{sku-42}:reserved

Customer:
    customer:{u-7}:profile
    customer:{u-7}:loyalty
```

Trong mỗi aggregate, các key cùng tag. Nhưng một quy trình checkout có thể cần thay đổi **order + inventory + customer**.

Bạn có hai hướng thiết kế lớn:

**Hướng 1 — gom tất cả dưới một tag transaction:** thường không khả thi nếu dữ liệu tham gia thuộc nhiều order, SKU và customer; sẽ tạo ghép nối và hot slot rất rộng.

**Hướng 2 — giữ aggregate boundary nhỏ và phối hợp các bước xuyên aggregate:** dùng giao dịch ở nguồn dữ liệu thích hợp, saga, reservation, idempotency, outbox, trạng thái chờ và các thao tác bù.

Ví dụ workflow:

```text
1. Reserve inventory của sku-42 bằng atomic operation ở slot sku-42.
2. Tạo/trạng thái order ở slot o-101.
3. Ghi nhận outcome của bước 1 và 2 bằng eventId/idempotency key.
4. Nếu bước 2 thất bại, có logic hoàn trả reservation.
5. Reconcile để xử lý trường hợp timeout/crash ở giữa.
```

Cách này phức tạp hơn một script Redis, nhưng phản ánh thực tế rằng **Redis Cluster không cung cấp giao dịch phân tán mặc định** giữa nhiều slot.

### 16.1. Dùng tag theo request ID có cứu được transaction xuyên aggregate?

Giả sử đặt:

```text
order:{request-1}:status
stock:{request-1}:reserved
```

Hai key này cùng slot, nhưng đó là **key theo request**, không còn là key tồn kho chung của SKU hoặc order canonical. Nếu cố gắn toàn bộ dữ liệu dùng chung vào tag request, nhiều request khác nhau sẽ không nhìn thấy cùng một state.

Một tag không thể đồng thời biểu diễn nhiều aggregate độc lập theo cách cho phép mỗi aggregate được cập nhật nguyên tử trong mọi tổ hợp giao dịch. Đây là giới hạn của partitioned data model, không phải thiếu cú pháp Redis.

## 17. Hash tag và Redis Streams

Streams cũng là Redis keys. Nếu một workflow cần ghi event vào Stream cùng với cập nhật dữ liệu khác bằng Lua/script, mọi key được dùng trong thao tác atomic cần tương thích slot.

Ví dụ:

```text
order:{o-101}:status
order:{o-101}:events
```

Nếu `events` là một Redis Stream chỉ chứa sự kiện của order `o-101`, hai key cùng slot và có thể tham gia một cơ chế atomic cùng-slot phù hợp.

Ngược lại:

```text
order:{o-101}:status
orders:global:events
```

một Stream tổng hợp toàn hệ thống có thể nằm slot khác. Không thể tự giả định cập nhật status rồi `XADD` vào global Stream là một transaction atomic trên Redis Cluster.

Các lựa chọn:

- Thiết kế Stream theo aggregate/partition.
- Dùng transactional outbox ở hệ thống nguồn rồi đưa event vào Stream.
- Chấp nhận hai bước và triển khai retry/reconcile.
- Nếu muốn cùng-slot, cân nhắc tag theo partition nhỏ, nhưng tránh tạo một Stream duy nhất thành hot slot.

**Redis Stream consumer group không thay đổi hash slot của Stream key.** PEL là metadata của group gắn với Stream, không tạo phép transaction toàn cluster giữa mọi Stream.

## 18. Hash tag và Redis Repository

Spring Data Redis Repository có các cơ chế lưu entity, secondary index, TTL và query. Các thao tác của repository có thể liên quan **nhiều Redis key**, không chỉ key Hash chính của entity.

Ví dụ mô hình logic:

```text
Entity Hash
Secondary index Set
TTL/shadow copy
Index cleanup metadata
```

Dù key Hash của entity có tag riêng, các key chỉ mục tập trung có thể thuộc slot khác. Vì vậy, không nên giả định:

> “Tôi đã thêm `{id}` vào một tên key entity, nên mọi tính năng Redis Repository tự động trở thành một transaction nhiều key hợp lệ trên Cluster.”

Cần xem mapping, serializer, cơ chế index, tập lệnh Redis thực sự và giới hạn Cluster của phiên bản Spring Data Redis đang dùng.

Một hướng thiết kế là giữ **simple key-value hoặc Hash access** trong những workload dễ đặt tag, và dùng hệ thống tìm kiếm/query thích hợp nếu cần truy vấn xuyên nhiều entity/slot. Nếu yêu cầu atomic secondary-index updates, cần đánh giá kỹ thiết kế dữ liệu và khả năng của thư viện.

### 18.1. Hash tag không làm query xuyên slot thành query xuyên toàn Cluster

Giả sử ứng dụng muốn tìm mọi order đang `PENDING`. Nếu mỗi order có tag riêng:

```text
order:{o-101}:status
order:{o-102}:status
order:{o-103}:status
```

thì hash tag không tạo sẵn một index tập trung theo status. Một Redis Set chứa tất cả order pending là một key khác, có thể thuộc slot khác.

Nếu muốn cập nhật Set global cùng lúc với từng order trong một script, bạn phải cân nhắc ranh giới slot. Hệ thống có thể cần eventual index maintenance, background reconciliation hoặc công cụ query khác thay vì ép mọi order vào một slot.

Đây là một trade-off cơ bản:

```text
Atomic per aggregate + phân tán tốt
    vs
Global index/aggregate cập nhật atomically cùng mọi entity
```

Không thể giải quyết cả hai bằng một cặp ngoặc nhọn duy nhất trong mọi thiết kế.

## 19. Transaction, pipeline và batch không phải cùng một thứ

Một API Java có thể gửi nhiều lệnh Redis nhưng cần phân biệt:

| Cơ chế | Mục tiêu | Same-slot và atomicity |
|---|---|---|
| Một command `GET key` | Đọc một key | Không cần nhóm key |
| Một command `MGET k1 k2` | Đọc nhiều key trong một lệnh | Redis Cluster yêu cầu tương thích slot theo lệnh |
| Hai command `GET k1`, `GET k2` | Đọc độc lập | Client cluster-aware có thể route khác node; không atomic |
| Pipeline | Giảm overhead network và gom nhiều request | Không tự biến các command thành một transaction |
| `MULTI`/`EXEC` | Thực thi một nhóm lệnh theo ngữ nghĩa Redis transaction | Không tự hỗ trợ transaction nhiều slot |
| Lua/Redis Function | Thực thi logic trên server không bị lệnh khác xen vào | Key access phải đáp ứng ràng buộc Cluster |
| Distributed workflow | Phối hợp thao tác trên nhiều service/slot | Cần thiết kế consistency/retry riêng |

### 19.1. Vì sao pipeline không sửa CROSSSLOT?

Giả sử client pipeline:

```text
GET order:{o-101}:status
GET order:{o-102}:status
```

Hai lệnh đọc đơn lẻ có thể được gửi riêng tới đúng primary qua cluster-aware client. Đó không phải một `MGET` atomic.

Nếu pipeline chứa một `MGET` với key khác slot, bản thân `MGET` vẫn có thể lỗi `CROSSSLOT`. Pipeline không can thiệp công thức tính slot.

### 19.2. Đọc nhiều slot có tạo snapshot nhất quán không?

Không. Nếu Java thực hiện:

```text
GET keyA ở primary A
GET keyB ở primary B
```

giữa hai lần đọc có thể xảy ra thay đổi dữ liệu. Một cluster-aware client routing đúng không bảo đảm **snapshot chung tại cùng thời điểm** cho các key ở các primary khác nhau.

Nếu chỉ cần hiển thị dashboard với tính nhất quán cuối cùng, cách đọc phân tán có thể ổn. Nếu cần business invariant mạnh, hãy chuyển logic consistency về một transactional boundary thích hợp.

## 20. MOVED, ASK và resharding có liên quan gì?

Khi Cluster thay đổi topology hoặc di chuyển slot:

- `MOVED` là tín hiệu redirect sang node đang sở hữu slot mới.
- `ASK` liên quan đến quá trình di chuyển slot và yêu cầu redirect tạm thời theo cơ chế Cluster.
- Client cluster-aware như Lettuce có thể cập nhật topology và xử lý redirect theo khả năng/configuration.
- Một số thao tác nhiều key hoặc trong giai đoạn migration có thể chịu hạn chế/tạm lỗi, cần retry có kiểm soát.

Điểm cần hiểu:

```text
Hash tag -> xác định slot ổn định từ tên key.
Slot owner -> có thể thay đổi theo topology.
```

Ví dụ:

```text
order:{o-101}:status -> slot S
order:{o-101}:items  -> slot S
```

Sau resharding, cả hai key vẫn thuộc slot `S`, nhưng slot `S` có thể chuyển sang primary khác.

**Hash tag không khóa key mãi trên một node cụ thể.** Nó chỉ đảm bảo hai key luôn ánh xạ tới cùng slot theo thuật toán.

### 20.1. Redirect không vượt qua CROSSSLOT

Một redirect giải quyết việc client đang gửi lệnh tới node không sở hữu slot của key. Nó **không thay đổi** việc hai key trong cùng lệnh thuộc hai slot khác nhau.

Ví dụ:

```text
MGET k1 k2
   |
   +-- k1 thuộc slot S1
   +-- k2 thuộc slot S2
   |
   v
CROSSSLOT
```

Không có node duy nhất nào trở thành nơi hợp lệ cho một `MGET` yêu cầu hai slot khác nhau chỉ vì client biết topology.

### 20.2. Không retry mù mọi thao tác ghi

Khi connection timeout hoặc failover xảy ra, client có thể không biết command đã được Redis thực thi hay chưa. Nếu retry:

```redis
INCR order:{o-101}:counter
```

một cách mù quáng, có thể tăng hai lần khi lần đầu đã thành công nhưng response thất lạc.

Hash tag không giải quyết sự không chắc chắn của kết quả sau timeout. Dùng idempotency token, compare-and-set script hoặc thiết kế state phù hợp khi nghiệp vụ không chấp nhận duplicate.

## 21. Migration từ key không tag sang key có tag

Một ứng dụng đang dùng standalone có thể lưu:

```text
order:o-101:status
order:o-101:items
```

Sau khi chuyển Cluster, muốn dùng:

```text
order:{o-101}:status
order:{o-101}:items
```

**Thêm hash tag làm thay đổi tên key thực tế**, không chỉ thay đổi cấu hình routing. Redis coi đây là các key khác hoàn toàn.

Do đó, chỉ đổi hàm build key trong Java mà không migration dữ liệu có thể khiến ứng dụng đọc `null` và tưởng như toàn bộ cache trống.

### 21.1. Các bước migration có kiểm soát

Một chiến lược tổng quát:

1. Xác định mọi nơi tạo key: HTTP service, background worker, Lua scripts, repository, scheduler, batch tools.
2. Định nghĩa KeyFactory mới và các tag cần dùng.
3. Kiểm kê dữ liệu cũ: tên key, type, TTL, serialization, dung lượng.
4. Quyết định có thể **rebuild cache** từ source-of-truth hay buộc phải migrate state.
5. Nếu có thể rebuild, cho dữ liệu cache cũ hết hạn hoặc xóa theo quy trình, sau đó chuyển reader/writer.
6. Nếu cần giữ state, triển khai cơ chế copy/restore/dual-read có kiểm soát.
7. Dùng version key namespace để tránh reader cũ/reader mới hiểu nhầm.
8. Triển khai theo từng nhóm traffic và đo Redis errors.
9. Khi toàn bộ service chuyển sang format mới, dọn key cũ theo retention policy.
10. Lưu khả năng rollback nếu migration chưa ổn định.

### 21.2. RENAME không phải giải pháp xuyên slot tổng quát

Trong Redis standalone, `RENAME old new` có thể đổi tên key trực tiếp. Trong Redis Cluster, `RENAME` cần các key name phù hợp ràng buộc slot.

Một tên cũ không tag và tên mới có tag thường hash vào hai slot khác nhau. Do đó, **không được mặc định `RENAME` sẽ migrate giữa chúng được**.

Có thể phải dùng copy/move theo cách được driver/tool hỗ trợ, có thể qua hai node và không atomic; hoặc rebuild state từ dữ liệu nguồn. Cần bảo đảm TTL và metadata được chuyển đúng, đồng thời xử lý race khi ứng dụng vẫn ghi key cũ.

### 21.3. TTL cần được bảo toàn nếu state không phải cache thuần

Nếu key cũ có thời hạn còn 30 giây nhưng trong migration bạn tạo key mới với TTL 1 giờ, có thể vô tình kéo dài một token, lock hoặc session đã sắp hết hạn.

Khi migrate:

- Đọc TTL hoặc absolute deadline theo khả năng lệnh.
- Bảo toàn deadline hợp lệ.
- Phân biệt `-1` (không expire) và `-2` (không tồn tại).
- Tránh tạo lại dữ liệu đã hết hạn.
- Kiểm soát race giữa đọc TTL, copy value và ghi key mới.
- Ưu tiên migration tại nơi sở hữu dữ liệu nếu dữ liệu có ý nghĩa bảo mật/nghiệp vụ.

Đối với token/lease nhạy cảm, xây dựng logic migration phải cẩn trọng hơn cache có thể tái tạo.

## 22. Một số lỗi thường gặp và cách chẩn đoán

### 22.1. `CROSSSLOT Keys in request don't hash to the same slot`

**Nguyên nhân:** ít nhất hai key trong lệnh yêu cầu same-slot đang thuộc các slot khác nhau.

**Hướng xử lý:** xem danh sách key thực sự được truyền, chạy `CLUSTER KEYSLOT` trên từng key; sau đó sửa key naming hoặc thay đổi thiết kế thao tác. Không khắc phục bằng retry liên tục.

### 22.2. “Các key cùng order nhưng MGET vẫn lỗi”

Có thể tên đang là:

```text
order:o-101:status
order:o-101:items
```

Chúng giống tiền tố nhưng không có hash tag. Đổi sang:

```text
order:{o-101}:status
order:{o-101}:items
```

và migration dữ liệu theo nhu cầu.

### 22.3. “Tôi đã dùng tag nhưng vẫn có key khác slot”

Xem ký tự `{`/`}` đầu tiên, tag rỗng, tag nằm sai vị trí, một service truyền tag khác hoặc key serializer khác. Redis chỉ sử dụng **tag đầu tiên hợp lệ theo quy tắc parser**, không dùng mọi cặp ngoặc trong tên.

### 22.4. “Hai key cùng node, vì sao không MSET được?”

Vì same-node không tương đương same-slot. Redis Cluster có ràng buộc trên hash slot của multi-key command. Địa chỉ primary hiện tại không phải điều kiện đủ.

### 22.5. “Lettuce cluster-aware có thể GET cả hai, sao MGET lỗi?”

Hai `GET` độc lập được route tới hai slot. Một `MGET` là một command có ràng buộc multi-key. Client có thể hỗ trợ một số cách split trong một số phiên bản, nhưng không nên suy ra semantic atomic giống nhau.

### 22.6. “Lua script thất bại dù hai key được tạo ở cùng server”

Lua trong Cluster cần key access tuân thủ ràng buộc cùng slot và khai báo `KEYS` phù hợp. Cùng server không đủ.

### 22.7. “Sau khi thêm `{tenant}` hệ thống chậm đi”

Nhiều key của một tenant được dồn vào một slot. Nếu tenant nóng, slot/node bị quá tải. Cân nhắc tag theo order, cart, SKU hoặc aggregate nhỏ hơn.

### 22.8. “Sau resharding key bị chuyển node”

Đó là hành vi bình thường của Redis Cluster. Hash tag xác định slot chứ không pin node. Cần client cluster-aware và cơ chế xử lý redirect.

### 22.9. “Đổi format key làm mất dữ liệu”

Tên key mới khác tên cũ; Redis không tự rename/migrate khi ứng dụng thêm `{}`. Cần migration hoặc rebuild.

### 22.10. “Tag dùng đúng nhưng Lua đọc ra dữ liệu lạ”

Slot không quyết định serializer của value. Nếu key được lưu bằng JSON/JDK serialization nhưng Lua mong String, logic so sánh/`tonumber` có thể sai. Kiểm tra wire format.

### 22.11. “Hai key cùng tag nhưng transaction vẫn không nhất quán”

Có thể ứng dụng dùng hai `SET` độc lập hoặc script có lỗi runtime sau khi ghi một phần. Hash tag chỉ thỏa ràng buộc vị trí; thiết kế atomic operation vẫn cần đúng.

### 22.12. “Một tenant có hàng chục triệu key cùng slot”

Tag theo tenant quá rộng. Có thể cần chuyển sang tag theo aggregate và chấp nhận workflow xuyên aggregate thay vì transaction Redis toàn tenant.

### 22.13. “Một key sau khi đổi tag không còn TTL cũ”

Đổi tên hoặc copy dữ liệu không tự duy trì deadline theo cách ứng dụng có thể đã thực hiện. Kiểm tra migration và expiration policy.

### 22.14. “READ có lúc thành công, có lúc MOVED/TRYAGAIN”

Topology có thể đang cập nhật hoặc slot đang di chuyển. Dùng client hỗ trợ Cluster, logging, retry có giới hạn và quan sát node health. Không tự đổi hash tag theo địa chỉ node đang phản hồi.

## 23. Quy trình kiểm tra khi thiết kế một multi-key workflow

Thay vì bắt đầu từ Redis command, hãy mô tả invariant trước:

**Ví dụ:** “Chuyển trạng thái giỏ hàng và cập nhật tổng tiền phải là một thao tác nguyên tử cho đúng một cart”.

Bước 1 — Xác định aggregate:

```text
Aggregate = cartId
```

Bước 2 — Liệt kê keys:

```text
cart:{c-77}:status
cart:{c-77}:total
cart:{c-77}:discount
```

Bước 3 — Chọn một tag chung:

```text
c-77
```

Bước 4 — Kiểm tra:

```redis
CLUSTER KEYSLOT cart:{c-77}:status
CLUSTER KEYSLOT cart:{c-77}:total
CLUSTER KEYSLOT cart:{c-77}:discount
```

Bước 5 — Chọn atomic primitive:

```text
Nếu chỉ ghi nhiều String: MSET có thể đủ.
Nếu cần điều kiện/so sánh: Lua hoặc WATCH/MULTI phù hợp.
```

Bước 6 — Định nghĩa kết quả và lỗi:

```text
SUCCESS
INVALID_STATE
MISSING_CART
RETRYABLE_INFRA_ERROR
UNKNOWN_AFTER_TIMEOUT
```

Bước 7 — Kiểm soát TTL, serialization và idempotency.

Bước 8 — Đo QPS của một cart và phân bố cart giữa slot.

Bước 9 — Thử failover/resharding trong môi trường phù hợp và xác nhận client handling.

Bước 10 — Khi thêm key mới vào workflow, yêu cầu nó dùng cùng KeyFactory và tag.

### 23.1. Bảng quyết định nhanh

| Câu hỏi | Nếu trả lời có | Hệ quả |
|---|---|---|
| Các key này cần cùng một `MGET`/`MSET`? | Có | Đặt cùng slot bằng tag phù hợp |
| Có cần script đọc và cập nhật cả nhóm key? | Có | Các key script truy cập cần cùng slot |
| Chỉ cần đọc từng key độc lập? | Có | Không nhất thiết phải cùng slot |
| Một key được truy cập cực nhiều? | Có | Cẩn trọng hot slot nếu gom thêm nhiều key |
| Workflow bao trùm nhiều order/SKU/customer? | Có | Xem lại transaction boundary, có thể cần phối hợp phân tán |
| Tên key hiện tại chưa có tag? | Có | Dự trù migration hoặc rebuild |
| Có key được tạo bằng nhiều serializer? | Có | Chuẩn hóa wire key trước khi dựa vào hash tag |
| Có nhiều môi trường/tenant cùng ID? | Có | Đưa định danh namespace vào key và tag theo quy tắc |

## 24. Bài thực hành 1 — Trực quan hóa hash slot

Kết nối Redis Cluster thử nghiệm, chạy:

```redis
CLUSTER KEYSLOT profile:{u-7}:name
CLUSTER KEYSLOT profile:{u-7}:avatar
CLUSTER KEYSLOT profile:{u-7}:settings
```

Ghi nhận ba số slot.

So sánh:

```redis
CLUSTER KEYSLOT profile:u-7:name
CLUSTER KEYSLOT profile:u-7:avatar
CLUSTER KEYSLOT profile:u-7:settings
```

Giải thích vì sao cùng `u-7` chưa đủ để bắt buộc mọi key cùng slot khi không có tag.

Mở rộng:

```redis
CLUSTER KEYSLOT profile:{u-8}:name
```

So sánh với `profile:{u-7}:name`. Hai tag khác nhau **không được bảo đảm** trả slot khác, vì CRC16 modulo 16384 có collision; điều quan trọng là không có contract cùng-slot giữa hai aggregate.

## 25. Bài thực hành 2 — Phân tích quy tắc ngoặc nhọn

Không cần tạo key trước. Dự đoán phần Redis dùng hash cho các tên:

```text
a{tenant-7}x
b{tenant-7}y
a{}b{tenant-7}
a{tenant-7
a{tenant-7}{order-101}
a{order-101}
a{Tenant-7}
```

Sau đó dùng `CLUSTER KEYSLOT` để xác nhận các nhóm dự đoán cùng slot.

Các câu hỏi:

1. Vì sao `a{tenant-7}x` và `b{tenant-7}y` cùng slot?
2. Vì sao `a{}b{tenant-7}` không chọn tag thứ hai?
3. Vì sao `{tenant-7}` và `{Tenant-7}` không nên được coi như cùng tag?
4. Với `a{tenant-7}{order-101}`, Redis dùng tenant hay order?
5. Nếu muốn tag theo cả tenant/order, nên ghép định danh ở đâu?

## 26. Bài thực hành 3 — MGET/MSET và CROSSSLOT

Tạo:

```redis
SET cart:{c-77}:status ACTIVE
SET cart:{c-77}:coupon SAVE10
MGET cart:{c-77}:status cart:{c-77}:coupon
```

Tiếp theo dùng:

```redis
CLUSTER KEYSLOT cart:{c-77}:status
CLUSTER KEYSLOT cart:{c-88}:coupon
```

Nếu hai slot khác nhau, thử:

```redis
MGET cart:{c-77}:status cart:{c-88}:coupon
```

Quan sát lỗi. Nếu hai tag tình cờ trùng slot, đổi `c-88` thành một ID khác có slot khác rồi thử lại.

Giải thích: `MGET` không thể tự biến thành một snapshot atomic giữa hai primary chỉ vì CLI dùng tùy chọn `-c` để xử lý redirect.

## 27. Bài thực hành 4 — Java KeyFactory

Viết class `OrderRedisKeys` như ở phần 10.

Yêu cầu:

1. `status("t-7", "o-101")` và `items("t-7", "o-101")` phải có cùng tag.
2. `status("t-7", "o-102")` phải dùng tag khác aggregate `o-101`.
3. Input chứa `{` hoặc `}` phải bị từ chối hoặc được encode an toàn.
4. Các service khác nhau phải tạo cùng chuỗi cho cùng ID.
5. Dùng `CLUSTER KEYSLOT` kiểm tra byte key được tạo ra.
6. Thêm một component `version` mà không đổi format tag.

Thảo luận vì sao KeyFactory dùng chung có giá trị hơn việc mỗi controller tự ghép String tên Redis key.

## 28. Bài thực hành 5 — Lua chuyển trạng thái order

Sử dụng script `transition-order.lua` ở phần 11.

1. Khởi tạo:

   ```redis
   SET order:{t-7|o-101}:status PENDING
   ```

2. Gọi `OrderTransitionService.markPaid("t-7", "o-101")`.
3. Đọc `status` và `updatedAt` để xem kết quả.
4. Gọi `markPaid` lần nữa, quan sát mã trạng thái.
5. Đổi một key sang `{t-7|o-102}`, xem slot và điều kiện thực thi.
6. Giải thích tại sao so sánh trong Lua tránh race `GET -> SET` khi nhiều request đồng thời.
7. Thảo luận timeout của script sau khi Redis đã cập nhật trạng thái: lần retry cần hành xử thế nào?

## 29. Bài thực hành 6 — Hot slot từ tag quá rộng

Giả sử một hệ thống có 1 triệu key:

```text
order:{global}:<id>:status
```

và 10 primary Redis Cluster.

Hãy trả lời:

- Những key này sử dụng bao nhiêu slot khác nhau theo quy tắc hash tag?
- Thêm primary có tự phân chia những key đó không?
- Nếu đổi sang `order:{<orderId>}:status`, số tag khác nhau tăng thế nào?
- Một order cực nóng có vẫn là vấn đề không?
- Nếu nghiệp vụ cần đọc 1000 order độc lập trên một dashboard, có bắt buộc phải dùng một lệnh MGET atomic không?
- Có chiến lược nào tốt hơn ép toàn bộ dữ liệu vào tag global?

Dùng `CLUSTER KEYSLOT` với một số key đại diện để minh họa. Không cần tạo một triệu key thật.

## 30. Bài thực hành 7 — Migration và TTL

Giả sử dữ liệu cũ:

```text
session:s-101:state
session:s-101:lastSeen
```

muốn đổi thành:

```text
session:{s-101}:state
session:{s-101}:lastSeen
```

Yêu cầu:

1. Mô tả vì sao Redis coi đây là key mới.
2. Giải thích hạn chế của `RENAME` trong Cluster nếu tên cũ/mới khác slot.
3. Liệt kê dữ liệu cần bảo toàn: value, type, TTL/deadline, serialization.
4. Phác thảo dual-read/rebuild với kế hoạch chuyển writer.
5. Xác định điều gì xảy ra nếu TTL key cũ hết hạn trong khi migration.
6. Đề xuất metric theo dõi sau khi deploy: cache miss, CROSSSLOT, timeout, read old key và read new key.

## 31. Bài thực hành 8 — Thiết kế ranh giới nghiệp vụ

Bài toán: checkout cần:

```text
order status
cart total
inventory available
customer loyalty balance
```

Các dữ liệu thuộc bốn aggregate khác nhau.

Hãy thiết kế:

- Hash tag cho từng aggregate.
- Những thao tác có thể atomic bằng script trong một aggregate.
- Những thao tác cần phối hợp xuyên aggregate.
- Vị trí của idempotency token.
- Cơ chế xử lý khi bước trừ tồn kho thành công nhưng ghi order thất bại.
- Cách đối soát để khôi phục sau timeout hoặc crash.

Giải thích vì sao gắn tất cả key bằng `{checkout-global}` không phải giải pháp scale tốt.

## 32. Câu hỏi tự đánh giá

1. Redis Cluster có bao nhiêu hash slot?
2. Công thức cơ bản tính slot từ tên key là gì?
3. Hash tag thay đổi phần nào của input CRC16?
4. Vì sao `order:101:status` và `order:101:items` không được bảo đảm cùng slot?
5. Vì sao `order:{101}:status` và `order:{101}:items` chắc chắn cùng slot?
6. Nếu có hai cặp `{...}` trong một key, Redis dùng cặp nào?
7. Điều gì xảy ra khi cặp đầu tiên là `{}` rỗng?
8. Cùng primary node có đủ để một lệnh multi-key chạy không?
9. `CLUSTER KEYSLOT` có yêu cầu key tồn tại không?
10. Một cluster-aware client tự redirect `MOVED` có giải quyết `CROSSSLOT` không?
11. Một key dùng `StringRedisSerializer` và một key dùng Java serialization có thể khác slot dù Java String hiển thị tương tự không?
12. Vì sao `MSET` same-slot và hai lệnh `SET` riêng biệt khác nhau về atomicity?
13. Lua trong Redis Cluster cần khai báo tên key ở đâu?
14. Vì sao giấu key trong `ARGV` không phải cách thiết kế đúng?
15. Hash tag có tự bảo đảm rollback runtime error trong script không?
16. Vì sao dùng tag `{global}` cho mọi key gây rủi ro?
17. Khi nào tag theo tenant có thể phù hợp, khi nào nên theo order?
18. Có thể thiết kế một transaction nguyên tử giữa hai SKU khác slot chỉ bằng `MULTI` không?
19. Tại sao một Redis Hash duy nhất đôi khi tốt hơn nhiều key cùng hash tag?
20. Vì sao thêm hash tag vào tên key cũ cần migration hoặc rebuild?
21. Điều gì xảy ra với slot khi primary owner thay đổi vì resharding?
22. Nếu một SKU quá nóng, tag theo SKU có thể dẫn đến giới hạn nào?
23. Vì sao TTL của các key cùng tag vẫn độc lập?
24. Làm sao kiểm tra hai key khác nhau có cùng slot mà không cần ghi dữ liệu?
25. Khi một workflow chứa nhiều aggregate, nguyên tắc chọn transaction boundary nên là gì?

## 33. Ghi nhớ

- Redis Cluster tính slot theo `CRC16(hash_input_bytes) mod 16384`, với **16.384 slot** cố định.
- Khi tên key có hash tag `{...}` hợp lệ, Redis dùng **phần byte không rỗng bên trong cặp ngoặc đầu tiên được chọn** làm hash input; nếu không, Redis dùng toàn bộ tên key.
- Các key như `order:{o-101}:status` và `order:{o-101}:items` **chắc chắn cùng hash slot** dù khác tên; mỗi key vẫn là một Redis key riêng.
- **Cùng slot khác cùng node**. Redis Cluster kiểm tra slot cho các lệnh multi-key phù hợp, kể cả khi hai slot tình cờ cùng được một primary phục vụ.
- Dùng `CLUSTER KEYSLOT` để xác minh key naming. Cùng tiền tố, cùng tenant hay cùng aggregate ID ở bên ngoài `{}` **không đủ**.
- Hash tag giúp đáp ứng ràng buộc của `MGET`, `MSET`, Lua, transaction và nhiều thao tác nhiều key khác, nhưng **không tự biến nhiều lời gọi độc lập thành atomic**.
- Thiết kế tag theo **aggregate cần atomicity**, tránh đặt mọi key dưới `{global}` hoặc tag tenant quá rộng khiến Redis Cluster bị **hot slot**.
- Trong Spring Data Redis, cần thống nhất **key serializer** (thường dùng `StringRedisSerializer`) để byte key thực sự chứa tag mong muốn; value serializer là một hợp đồng khác.
- Nên có một **KeyFactory tập trung** để chuẩn hóa tenant/order ID, ngăn `{}` từ dữ liệu đầu vào làm đổi tag và tạo tên key nhất quán giữa các service.
- Script cần khai báo key qua `KEYS`; không giấu Redis key trong `ARGV` để lách phân vùng. `MOVED`/`ASK` không biến giao dịch xuyên slot thành hợp lệ.
- Khi đổi key cũ sang format có tag, đó là đổi **tên key thực**, cần migration/rebuild và bảo toàn TTL nếu state quan trọng.
- Khi workflow cần thay đổi nhiều aggregate độc lập, hãy thiết kế idempotency, transaction ở source-of-truth, event/outbox hoặc saga thay vì gom toàn hệ thống vào một slot.
- Hash tag là **công cụ đặt dữ liệu cùng slot có chủ đích**, không phải lời hứa rằng mọi thao tác trên các key cùng tag đều nhất quán, bền vững hay đúng tuyệt đối sau sự cố.

### Tài liệu tham khảo chính thức

- [Redis — Redis Cluster specification: key distribution model](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Redis — Redis Cluster tutorial](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/)
- [Redis — CLUSTER KEYSLOT](https://redis.io/docs/latest/commands/cluster-keyslot/)
- [Redis — MGET](https://redis.io/docs/latest/commands/mget/)
- [Redis — MSET](https://redis.io/docs/latest/commands/mset/)
- [Redis — MULTI](https://redis.io/docs/latest/commands/multi/)
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/)
- [Redis — RENAME](https://redis.io/docs/latest/commands/rename/)
- [Redis — SET](https://redis.io/docs/latest/commands/set/)
- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
