# Đánh giá thời gian chạy vì script có thể chặn xử lý lệnh khác trong Spring Data Redis

Lua scripting giúp Redis thực hiện nhiều thao tác đọc, kiểm tra điều kiện và ghi dữ liệu **như một đơn vị nguyên tử về mặt thực thi**. Đó là lợi thế lớn khi xây dựng các chức năng như trừ tồn kho có điều kiện, giới hạn số lần truy cập, cấp quyền sở hữu khóa hoặc cập nhật nhiều cấu trúc dữ liệu có liên quan.

Tuy nhiên, chính cơ chế bảo đảm tính nguyên tử ấy tạo ra một giới hạn quan trọng: **trong lúc Redis thực thi một Lua script, những lệnh thông thường khác trên cùng Redis server không được chen vào giữa script**. Một script có vòng lặp dài, duyệt quá nhiều phần tử hoặc gọi các lệnh có chi phí lớn có thể khiến hàng loạt request Redis khác bị tăng độ trễ, dù những request đó chỉ gửi `GET` đơn giản.

Vì vậy, khi dùng Spring Data Redis gọi `EVAL`/`EVALSHA` thông qua `RedisTemplate.execute(...)`, cần đánh giá **thời gian chạy, lượng công việc và ảnh hưởng đến độ trễ của các request khác**, ngoài việc kiểm tra script có trả kết quả đúng hay không.

Bài này tập trung vào mối quan hệ giữa **tính nguyên tử**, **thời gian script chiếm Redis server**, các công cụ quan sát và cách thiết kế Lua script có giới hạn công việc rõ ràng.

## 1. Vì sao script nguyên tử lại có nguy cơ gây nghẽn?

Redis thực thi thao tác trên cấu trúc dữ liệu theo cơ chế tuần tự hóa lệnh. Dù một số phiên bản/cấu hình có I/O threads để hỗ trợ phần mạng, việc thực thi các thao tác dữ liệu thông thường vẫn có đặc tính một script Lua chiếm luồng thực thi lệnh của Redis trong lúc chạy.

Ví dụ, hai client cùng làm việc với một Redis server:

```text
Client A                             Redis server                         Client B
--------                             ------------                         --------
EVAL long-script ------------------> [ script bắt đầu ]
                                     [ đọc các key     ]
GET user:42 --------------------X    [ vòng lặp lớn    ] <---------------- GET user:42
                                     [ ghi nhiều key   ]
                                     [ script kết thúc ]
                                                                        <--- trả lời GET
```

Trong hình, `GET` của client B không thể chen giữa các thao tác của script để quan sát trạng thái mới chỉ được ghi một nửa. Tính chất này giúp script giữ tính nguyên tử, nhưng đồng thời khiến **độ trễ của client B phụ thuộc vào thời gian còn lại của script A**.

Hệ quả có thể xảy ra:

- Một script chạy vài trăm mili giây làm tăng độ trễ của nhiều request bình thường.
- Nhiều script nặng liên tiếp tạo hàng đợi xử lý lệnh và làm p95/p99 latency tăng đột biến.
- Một script chạy lâu có thể khiến client nhận timeout trước khi server hoàn thành xử lý.
- Người vận hành thấy Redis vẫn hoạt động ở cấp tiến trình nhưng các lệnh khác chờ rất lâu hoặc nhận lỗi liên quan đến script đang bận.
- Một script đọc dữ liệu nhưng không ghi gì vẫn có thể gây nghẽn, vì việc giữ tính không xen giữa không phụ thuộc script có lệnh ghi hay không.

Điểm quan trọng: **script không cần gây lỗi mới làm hệ thống chậm**. Chỉ cần chiếm luồng xử lý lệnh đủ lâu là có thể ảnh hưởng tới mọi ứng dụng cùng sử dụng Redis server đó.

## 2. Tính nguyên tử của Lua script thực sự bảo đảm điều gì?

Xét một thao tác trừ tồn kho:

```text
Đọc stock
    |
Kiểm tra stock >= quantity
    |
Trừ quantity
    |
Trả kết quả
```

Nếu Java gửi `GET` rồi `DECRBY` thành hai lệnh độc lập, client khác có thể thay đổi tồn kho ở giữa. Đưa cả kiểm tra và cập nhật vào một Lua script giúp Redis thực thi chúng liên tiếp, không bị thao tác của client khác chen vào.

Ví dụ:

```lua
local current = tonumber(redis.call('GET', KEYS[1]))
local requested = tonumber(ARGV[1])

if not current or not requested or requested <= 0 then
    return -1
end

if current < requested then
    return 0
end

return redis.call('DECRBY', KEYS[1], requested)
```

Với key `stock:sku-42` và số lượng yêu cầu là `2`, script đọc stock, kiểm tra và trừ trên Redis server.

Những bảo đảm cần hiểu đúng:

| Khía cạnh | Tính chất |
|---|---|
| Không xen giữa | Lệnh của client khác không chen vào giữa các lệnh của script trên Redis server thực thi |
| Kiểm tra rồi cập nhật | Điều kiện và phép cập nhật nằm trong cùng một script |
| Kết quả phía client | Client nhận phản hồi sau khi script hoàn thành hoặc phát sinh lỗi |
| Rollback khi lỗi runtime | **Không** có cơ chế rollback tổng quát các ghi đã thực hiện trước lỗi trong script |
| Độ bền sau crash | Phụ thuộc cấu hình persistence/replication Redis |
| Giao dịch với PostgreSQL hoặc dịch vụ khác | **Không** được tạo chỉ vì một script Redis nguyên tử |
| Giới hạn thời gian | Phải chủ động thiết kế; tính nguyên tử không đặt một hạn mức công việc an toàn |

Nếu script ghi một số dữ liệu rồi phát sinh lỗi, Redis không tự khôi phục mọi ghi về trạng thái trước khi chạy script. Do đó, logic nên **kiểm tra đầy đủ điều kiện và khả năng lỗi trước khi bước vào chuỗi ghi**. Đồng thời, một script đúng về nghiệp vụ vẫn có thể gây ảnh hưởng lớn nếu thực thi quá lâu.

## 3. Thời gian chạy script liên quan thế nào đến latency toàn hệ thống?

Giả sử một Redis server nhận request từ ba dịch vụ:

```text
Service A: xác thực phiên           -> GET session:...
Service B: đọc cache sản phẩm       -> MGET cache:...
Service C: cập nhật thống kê lớn    -> EVAL lua-script
```

Nếu Service C chạy một script mất 200 ms, các lệnh đến Redis đúng trong khoảng thời gian đó phải chờ script kết thúc trước khi được thực thi. Với hệ thống cần phản hồi trong vài mili giây, 200 ms có thể vượt xa ngân sách latency.

Một cách nhìn định tính:

```text
Thời gian
0 ms              50 ms             100 ms             200 ms
|------------------|------------------|------------------|
[                 EVAL đang chạy                         ]
   [GET đến].............................................[GET được xử lý]
                       [INCR đến].........................[INCR được xử lý]
```

Script chiếm Redis càng lâu, cửa sổ chờ của những request khác càng dài.

### 3.1. Không chỉ quan tâm thời gian trung bình

Một script có thời gian trung bình 2 ms nghe có vẻ nhanh, nhưng nếu thỉnh thoảng xử lý danh sách cực lớn trong 300 ms thì p99 latency của hệ thống vẫn có thể bị ảnh hưởng nghiêm trọng.

Hãy quan sát tối thiểu:

- **Latency trung bình:** cho biết bức tranh tổng quát.
- **p95 và p99:** phát hiện những lần chạy chậm hiếm gặp, thường quan trọng với request phục vụ người dùng.
- **Thời gian chạy lớn nhất:** hữu ích để phát hiện đầu vào bất thường.
- **Số lần script được gọi mỗi giây:** script ngắn nhưng được gọi liên tục cũng chiếm một phần lớn năng lực server.
- **Độ trễ của các lệnh khác khi script chạy:** giúp xác định tác động lan rộng.
- **Timeout, lỗi `BUSY` và số connection chờ:** biểu hiện quá tải hoặc script kéo dài.

Đánh giá phải gắn với **ngân sách latency của ứng dụng**, số lượng request đồng thời, kích thước dữ liệu và tải thực tế. Không tồn tại một ngưỡng thời gian duy nhất phù hợp cho mọi Redis deployment.

### 3.2. Thời gian phía ứng dụng khác thời gian chạy trên Redis server

Khi Java gọi:

```java
redisTemplate.execute(script, keys, args);
```

thời gian đo từ Java gồm nhiều thành phần:

```text
Thời gian phía client
  = chờ connection / pool (nếu có)
  + serialize key và arguments
  + gửi request qua mạng
  + chờ server có thể xử lý
  + Redis thực thi Lua script
  + gửi response về client
  + deserialize kết quả
  + overhead ứng dụng
```

Do đó, đo `System.nanoTime()` trước và sau lệnh `execute(...)` giúp hiểu **latency mà ứng dụng cảm nhận**, nhưng **không cô lập được thời gian Lua thật sự chiếm server**.

Ngược lại, `SLOWLOG` chủ yếu ghi lại thời gian Redis dùng để **thực thi lệnh**, không bao gồm thời gian truyền request/response qua mạng. Kết hợp quan sát cả hai phía giúp phân biệt:

- Script thực sự xử lý nặng ở server.
- Redis đang phải chờ xử lý vì các lệnh nặng khác.
- Connection pool hoặc mạng khiến request chậm.
- Client parse lượng dữ liệu trả về quá lớn.

## 4. Vì sao Lua script dễ chậm dù chỉ gửi một lệnh `EVAL`?

Từ góc độ client, `EVAL` là một Redis command. Nhưng bên trong có thể chứa nhiều vòng lặp và rất nhiều lời gọi `redis.call(...)`.

Ví dụ chỉ nhằm minh họa **mẫu thiết kế cần tránh**:

```lua
-- Không triển khai script này với tập dữ liệu không giới hạn.
local processed = 0

for i = 1, #KEYS do
    local members = redis.call('SMEMBERS', KEYS[i])

    for _, member in ipairs(members) do
        -- Giả sử có thêm nhiều bước xử lý cho từng member.
        processed = processed + 1
    end
end

return processed
```

Số lượng lệnh Redis bên ngoài chỉ là **một lần `EVAL`**, nhưng công việc bên trong gồm:

1. Duyệt mọi key trong `KEYS`.
2. Với mỗi key, đọc toàn bộ phần tử của Set bằng `SMEMBERS`.
3. Duyệt tất cả phần tử Set trong Lua.
4. Giữ quyền thực thi xuyên suốt các vòng lặp đó.

Nếu đầu vào chứa hàng nghìn key và mỗi Set có rất nhiều phần tử, thời gian chạy có thể tăng đáng kể.

### 4.1. Độ phức tạp là một phần của thời gian chặn

| Dạng thao tác trong script | Nguy cơ |
|---|---|
| Đọc/ghi một Redis String nhỏ | Thường có công việc giới hạn rõ ràng |
| Gọi `HGET` một vài field xác định | Thường nhỏ nếu số lệnh được giới hạn |
| Duyệt `KEYS` do client gửi mà không giới hạn số lượng | Tăng theo lượng key đầu vào |
| Gọi `SMEMBERS`/`LRANGE 0 -1` trên cấu trúc lớn | Đọc toàn bộ dữ liệu, tạo bảng Lua và tốn bộ nhớ |
| `HGETALL` trên hash lớn | Công việc tăng theo số field |
| Vòng lặp lồng nhau qua nhiều tập dữ liệu | Có thể tăng rất nhanh theo kích thước đầu vào |
| Gọi nhiều lệnh ghi trong vòng lặp dài | Kéo dài thời gian server không phục vụ request khác |
| Dùng `KEYS pattern` trong script trên keyspace lớn | Có thể duyệt phạm vi keyspace rộng, gây nghẽn |
| Quét nhiều lượt bằng `SCAN` ngay trong cùng script | Dù từng bước SCAN nhỏ, toàn script vẫn chiếm Redis cho đến khi kết thúc |

Một sai lầm thường gặp là thay `KEYS` bằng `SCAN` **bên trong một script duy nhất** rồi lặp cho đến khi cursor về `0`. `SCAN` giúp chia công việc thành các bước ở mức command, nhưng nếu chạy tất cả những bước ấy trong **cùng một lần `EVAL`**, Redis vẫn không có cơ hội phục vụ các lệnh thông thường khác giữa các vòng lặp Lua.

Giải pháp đúng khi không cần tính nguyên tử trên toàn bộ keyspace thường là **chia công việc thành nhiều lời gọi nhỏ**, mỗi lời gọi được phép kết thúc để Redis xử lý request khác.

## 5. Redis có tự dừng script khi chạy quá lâu không?

Redis có cấu hình `lua-time-limit`, thường có giá trị mặc định **5.000 mili giây**. Có thể xem trên instance đang sử dụng:

```redis
CONFIG GET lua-time-limit
```

Ví dụ minh họa:

```text
lua-time-limit = 5000
```

Phải hiểu đúng giá trị này:

**`lua-time-limit` không phải cơ chế tự động rollback hoặc buộc mọi script kết thúc sau đúng 5 giây.**

Khi script chạy vượt ngưỡng, Redis có thể ghi cảnh báo rằng script chạy quá lâu và cho phép một tập lệnh quản trị đặc biệt được xử lý trong trạng thái bận. Các lệnh Redis thông thường khác có thể nhận lỗi dạng:

```text
BUSY Redis is busy running a script
```

Script vẫn có thể tiếp tục chạy cho đến khi tự kết thúc hoặc người vận hành xử lý theo cơ chế cho phép. Do đó, không thể đặt `lua-time-limit = 5000` rồi mặc định toàn hệ thống chắc chắn không bị chặn quá 5 giây.

### 5.1. `SCRIPT KILL` có những giới hạn nào?

Redis hỗ trợ:

```redis
SCRIPT KILL
```

Lệnh này có thể dừng một script đang chạy quá lâu **nếu script chưa thực hiện thao tác ghi dữ liệu**. Giới hạn này tồn tại để tránh dừng script giữa chừng sau khi nó đã làm thay đổi trạng thái Redis.

Nếu script đã ghi dữ liệu, Redis không cho phép dùng `SCRIPT KILL` như một cách hoàn tác an toàn. Với sự cố nghiêm trọng, Redis có những cơ chế quản trị mạnh hơn như dừng server mà không lưu dữ liệu (`SHUTDOWN NOSAVE`), nhưng đó là biện pháp khẩn cấp có nguy cơ **mất dữ liệu** và phải theo quy trình vận hành nghiêm ngặt, không phải cách xử lý timeout thường ngày của ứng dụng.

Những điều nên nhớ:

- Không viết script với kỳ vọng `SCRIPT KILL` luôn giải cứu được mọi tình huống.
- Không dùng kill như một chiến lược timeout nghiệp vụ.
- Không coi kết quả client timeout là bằng chứng script đã được dừng trên server.
- Khi script bị bận, cần phân biệt lỗi Redis `BUSY` với timeout ở tầng client.
- Nếu dùng Redis Functions, cơ chế quản trị có tên và điều kiện riêng, chẳng hạn `FUNCTION KILL` cho function phù hợp.

### 5.2. Client timeout không chặn được script trên Redis

Giả sử client Java đặt timeout 2 giây:

```text
t = 0s    Java gửi EVAL
t = 2s    Java ngừng chờ và báo Redis command timeout
t = 5s    Script trên Redis vẫn có thể đang chạy
t = 7s    Script mới kết thúc hoặc gặp lỗi
```

Timeout phía ứng dụng chỉ mô tả **thời gian client sẵn sàng đợi**. Nó không bảo đảm Redis đã hủy công việc được gửi trước đó.

Nếu request xử lý thất bại và ứng dụng tự động retry một script có tác dụng ghi, có thể vô tình **thực hiện cùng thay đổi hai lần**. Với nghiệp vụ quan trọng, cần token nhận diện request và cơ chế idempotency được kiểm tra/cập nhật nguyên tử ở server.

## 6. Thiết kế script có số bước và dữ liệu đầu vào được giới hạn

Một script phù hợp với workload latency thấp thường có đặc điểm:

- Số lượng Redis commands bên trong **nhỏ và có giới hạn rõ ràng**.
- Không duyệt toàn bộ Redis keyspace.
- Không đọc toàn bộ các Set/List/Hash lớn nếu chỉ cần một phần dữ liệu.
- Kiểm tra đầu vào hợp lệ trước khi thực hiện thao tác ghi.
- Số vòng lặp được giới hạn ngay tại server, không chỉ nhờ client tự giác.
- Kết quả trả về gọn, tránh gửi cả bộ dữ liệu lớn nếu chỉ cần một trạng thái.
- Không chứa phép tính CPU nặng hoặc vòng lặp không có giới hạn kết thúc.
- Không phụ thuộc vào khả năng dừng script thủ công khi đã chạy quá lâu.

### 6.1. Ví dụ: script tồn kho có phạm vi O(1)

Một script chỉ thao tác trên **một key** có phạm vi công việc dễ kiểm soát hơn script quét nhiều key.

```lua
-- KEYS[1]: stock:sku-42
-- ARGV[1]: số lượng cần trừ, nguyên dương trong giới hạn nghiệp vụ

if #KEYS ~= 1 or #ARGV ~= 1 then
    return redis.error_reply('invalid arguments')
end

local quantity = tonumber(ARGV[1])

if not quantity
   or quantity % 1 ~= 0
   or quantity < 1
   or quantity > 1000 then
    return redis.error_reply('invalid quantity')
end

local rawStock = redis.call('GET', KEYS[1])

if not rawStock then
    return -1 -- Không tồn tại tồn kho
end

local currentStock = tonumber(rawStock)

if not currentStock then
    return redis.error_reply('invalid stock value')
end

if currentStock < quantity then
    return 0 -- Không đủ hàng
end

-- Mọi điều kiện đã được kiểm tra trước bước ghi.
return redis.call('DECRBY', KEYS[1], quantity)
```

Logic chính gồm:

```text
GET một key
  |
Phân tích và kiểm tra số nguyên
  |
Nếu không đủ -> trả 0
Nếu đủ       -> DECRBY một key
```

Tính nguyên tử giúp tránh race condition giữa kiểm tra tồn kho và trừ tồn kho. Giới hạn `quantity <= 1000` là **quy tắc nghiệp vụ minh họa** nhằm tránh đầu vào không hợp lệ; nó không có nghĩa mọi script phải dùng mức này.

Ngoài giới hạn số lượng, phải bảo đảm dữ liệu lưu trong key là số nguyên Redis hỗ trợ và có phạm vi hợp lệ. Khi cần thao tác trên nhiều key, giới hạn số key, kích thước dữ liệu và số bước xử lý tương tự.

### 6.2. Một script ngắn vẫn có thể gặp dữ liệu lớn

Không nên chỉ đếm số dòng Lua để đánh giá hiệu năng. Ví dụ:

```lua
return redis.call('HGETALL', KEYS[1])
```

chỉ có **một dòng**, nhưng một Redis Hash rất lớn có thể khiến lệnh này tốn thời gian và tạo phản hồi lớn.

Tương tự:

```lua
return redis.call('LRANGE', KEYS[1], 0, -1)
```

có thể đọc toàn bộ một List. Khi cần phân trang hoặc giới hạn dữ liệu, hãy đặt phạm vi cụ thể từ yêu cầu nghiệp vụ và đo thời gian chạy theo dữ liệu lớn nhất dự kiến.

## 7. Chia công việc lớn thành nhiều bước nhỏ

Giả sử ứng dụng cần cập nhật hàng trăm nghìn bản ghi Redis. Chạy một Lua script để tìm toàn bộ key rồi xử lý trong một lần `EVAL` sẽ khiến Redis bị chiếm trong thời gian dài.

Thay vào đó, nếu yêu cầu không bắt buộc tất cả bản ghi cùng đổi trạng thái nguyên tử, có thể:

1. Dùng một worker phía ứng dụng để tìm danh sách key theo từng đợt, chẳng hạn dùng cơ chế cursor/`SCAN` thích hợp.
2. Tạo những batch nhỏ với số key đã giới hạn.
3. Gọi script chỉ xử lý **một batch** hoặc một đơn vị dữ liệu cụ thể.
4. Kết thúc mỗi lần script để Redis có cơ hội phục vụ request khác.
5. Theo dõi độ trễ và khả năng thất bại/tái xử lý khi worker bị gián đoạn.

```text
Thay vì:

EVAL [ xử lý 100.000 khóa trong một lần ]
      |----------------------------------- thời gian chặn lớn ----------------------------------|

Thiết kế có giới hạn:

EVAL [batch 1] -> trả kết quả
            Redis có thể phục vụ lệnh khác
EVAL [batch 2] -> trả kết quả
            Redis có thể phục vụ lệnh khác
EVAL [batch 3] -> trả kết quả
...
```

Điều đánh đổi rất quan trọng: **chia batch làm mất tính nguyên tử trên toàn bộ tập dữ liệu**. Nếu nghiệp vụ thực sự đòi hỏi mọi bản ghi được đổi trạng thái cùng lúc, phải cân nhắc lại mô hình lưu trữ, đặt cờ phiên bản, chuyển con trỏ tới bộ dữ liệu mới hoặc sử dụng storage có giao dịch phù hợp. Không thể vừa đòi mọi thao tác trên dữ liệu cực lớn là một script duy nhất vừa kỳ vọng không gây chặn Redis server.

### 7.1. Giới hạn số key ngay trong Lua

Dù client đã chia batch, script cũng nên tự chặn đầu vào quá lớn:

```lua
local MAX_KEYS = 50

if #KEYS < 1 or #KEYS > MAX_KEYS then
    return redis.error_reply('too many keys')
end

for i = 1, #KEYS do
    redis.call('DEL', KEYS[i])
end

return #KEYS
```

Ví dụ này chỉ phù hợp khi từng key có chi phí xóa có thể chấp nhận được. `DEL` của một cấu trúc dữ liệu rất lớn vẫn có thể tốn thời gian vì giải phóng bộ nhớ; giới hạn **50 key** không bảo đảm toàn script nhanh trong mọi hoàn cảnh. Nếu xóa dữ liệu lớn, cần thiết kế cân nhắc `UNLINK`, phạm vi nguyên tử cần thiết và hành vi dọn bộ nhớ.

Giới hạn đầu vào phải bao gồm **khối lượng công việc ẩn trong lệnh Redis**, không chỉ số key được truyền vào.

## 8. Đo thời gian gọi script trong Spring Data Redis

Spring Data Redis hỗ trợ thực thi script thông qua `RedisTemplate.execute(RedisScript<T>, List<K>, Object...)`. Khi dùng `DefaultRedisScript`, ứng dụng có thể lưu Lua trong classpath hoặc cung cấp script text.

Ví dụ Java sử dụng `StringRedisTemplate` và đo độ trễ bằng `System.nanoTime()`:

```java
package com.example.redis;

import java.util.List;
import java.util.concurrent.TimeUnit;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

@Service
public class StockReservationService {

    private static final String DECREASE_STOCK_LUA = """
        if #KEYS ~= 1 or #ARGV ~= 1 then
            return redis.error_reply('invalid arguments')
        end

        local quantity = tonumber(ARGV[1])
        if not quantity
            or quantity % 1 ~= 0
            or quantity < 1
            or quantity > 1000 then
            return redis.error_reply('invalid quantity')
        end

        local current = redis.call('GET', KEYS[1])
        if not current then
            return -1
        end

        local stock = tonumber(current)
        if not stock then
            return redis.error_reply('invalid stock value')
        end

        if stock < quantity then
            return 0
        end

        return redis.call('DECRBY', KEYS[1], quantity)
        """;

    private final StringRedisTemplate redis;
    private final DefaultRedisScript<Long> decreaseScript;

    public StockReservationService(StringRedisTemplate redis) {
        this.redis = redis;
        this.decreaseScript =
                new DefaultRedisScript<>(DECREASE_STOCK_LUA, Long.class);
    }

    public long reserve(String sku, int quantity) {
        String key = "stock:" + sku;
        long startNanos = System.nanoTime();

        try {
            Long result = redis.execute(
                    decreaseScript,
                    List.of(key),
                    Integer.toString(quantity)
            );

            if (result == null) {
                throw new IllegalStateException(
                        "Redis script returned no result"
                );
            }

            return result;
        } finally {
            long elapsedNanos = System.nanoTime() - startNanos;
            long elapsedMillis =
                    TimeUnit.NANOSECONDS.toMillis(elapsedNanos);

            // Minh họa đơn giản. Trong production nên ghi histogram
            // bằng Micrometer/observability thay vì log mỗi request.
            System.out.println(
                    "decrease_stock script call took "
                    + elapsedMillis + " ms"
            );
        }
    }
}
```

Trong ví dụ:

- `DefaultRedisScript<Long>` xác định kiểu kết quả mong muốn; các số nguyên Redis trả về được ánh xạ phù hợp.
- `StringRedisTemplate` xử lý việc serialize key/argument theo cách gọi template.
- `execute(...)` thực thi script trên Redis; cơ chế `EVALSHA`/nạp lại script khi cần do Spring Data Redis xử lý theo khả năng của phiên bản và driver.
- Đồng hồ đo trong `finally` vẫn ghi nhận thời gian khi thao tác thành công hoặc có exception.
- Thời gian đo là **end-to-end call duration**, bao gồm network và client overhead, không phải riêng CPU time của Lua.
- Không gắn nhãn metric theo `sku`, session ID hoặc các giá trị biến thiên không giới hạn; cần giữ cardinality thấp.

Trong triển khai thực tế, có thể ghi `Timer` của Micrometer với tên script ổn định như `decrease_stock`, thêm các nhãn ít biến thể như `result=success|rejected|error`, rồi quan sát p95/p99 và số lần gọi. Nếu request đã bị timeout, hãy cân nhắc tính chất không chắc chắn của kết quả trước khi tự động retry.

### 8.1. Phân biệt tổng thời gian và thời gian thực thi Lua

Ví dụ kết quả quan sát trong môi trường thử nghiệm:

```text
App duration p99 của execute(...):   45 ms
Redis SLOWLOG command EVALSHA:         4 ms
```

Một khả năng là phần lớn độ trễ nằm ở chờ kết nối, mạng, xử lý client hoặc xếp hàng chờ Redis rảnh. Cần xem thêm metric pool, Redis load và các lệnh khác trước khi kết luận.

Trường hợp khác:

```text
App duration p99 của execute(...):  250 ms
Redis SLOWLOG command EVALSHA:      238 ms
```

Khi thời gian server lớn tương đương tổng độ trễ, bản thân Lua hoặc các lệnh Redis được gọi trong script là ứng viên cần tối ưu trước.

Các con số chỉ dùng minh họa; không phải ngưỡng bắt buộc của Spring Data Redis.

## 9. Dùng `SLOWLOG` quan sát script chậm

Redis có **slow query log** ghi những lệnh có thời gian thực thi tại server vượt ngưỡng cấu hình.

Xem cấu hình:

```redis
CONFIG GET slowlog-log-slower-than
CONFIG GET slowlog-max-len
```

Ngưỡng `slowlog-log-slower-than` được tính bằng **microsecond**. Ví dụ `10000` nghĩa là 10 ms; không phải 10.000 ms.

Xem các bản ghi mới nhất:

```redis
SLOWLOG GET 20
```

Xem tổng số bản ghi đã được ghi nhận:

```redis
SLOWLOG LEN
```

Trong môi trường thử nghiệm có quyền cấu hình, có thể đặt ngưỡng thấp hơn để quan sát lệnh chạy hơn 2 ms:

```redis
CONFIG SET slowlog-log-slower-than 2000
```

Giá trị `2000` tương ứng 2.000 microsecond. **Đây là cấu hình minh họa cho môi trường kiểm thử**; không tự giảm ngưỡng trên production mà không đánh giá lượng log và quyền cấu hình của dịch vụ Redis đang dùng.

### 9.1. Đọc kết quả SLOWLOG như thế nào?

Một entry SLOWLOG thường cho biết:

- ID của bản ghi.
- Thời điểm ghi nhận.
- Thời gian thực thi lệnh tính bằng microsecond.
- Thông tin command và các argument được hiển thị/truncated theo cách Redis lưu log.
- Một số thông tin client trong các phiên bản Redis hỗ trợ.

Nếu script được gọi bằng `EVALSHA`, lệnh trong SLOWLOG có thể hiện tên `EVALSHA` cùng script SHA/arguments. Không nhất thiết thấy toàn bộ mã Lua khi script được gọi bằng SHA.

**SLOWLOG ghi các lệnh đã hoàn thành và vượt ngưỡng**, vì vậy một script vẫn đang chạy/bị kẹt chưa chắc đã xuất hiện ngay trong log. Khi điều tra sự cố hiện tại, cần phối hợp SLOWLOG với triệu chứng `BUSY`, độ trễ và thông tin vận hành Redis.

`SLOWLOG` hữu ích để trả lời: “Một lần `EVAL`/`EVALSHA` đã chiếm server bao lâu?”, nhưng chưa đủ để cho biết vòng lặp Lua nào cụ thể gây chậm. Muốn xác định đoạn nặng, cần hiểu thuật toán và kích thước dữ liệu đầu vào; trong môi trường kiểm thử có thể phân tách logic và đo từng biến thể an toàn.

## 10. Đo độ trễ toàn Redis bằng `LATENCY` và các công cụ quan sát

Redis có **latency monitoring** để ghi nhận một số sự kiện độ trễ khi đã được cấu hình phù hợp.

Kiểm tra ngưỡng:

```redis
CONFIG GET latency-monitor-threshold
```

Trong môi trường thử nghiệm, có thể bật theo ngưỡng minh họa 10 ms:

```redis
CONFIG SET latency-monitor-threshold 10
```

Các lệnh quan sát:

```redis
LATENCY LATEST
LATENCY HISTORY command
LATENCY DOCTOR
```

Lưu ý rằng tên event trong `LATENCY HISTORY` phụ thuộc sự kiện thực sự được Redis ghi nhận; `command` chỉ là một loại sự kiện có thể xuất hiện. `LATENCY DOCTOR` cung cấp diễn giải/chẩn đoán dựa trên các sự kiện đã có, không thay thế việc đọc SLOWLOG hay đo end-to-end từ ứng dụng.

Một số lệnh và tiện ích khác:

```redis
INFO commandstats
INFO stats
INFO cpu
INFO memory
```

Có thể dùng công cụ `redis-cli` trong môi trường vận hành:

```bash
redis-cli --latency
redis-cli --latency-history
```

`INFO commandstats` thường cung cấp tổng số lần gọi và các thống kê thời gian theo loại command, hữu ích để xem `eval`/`evalsha` có chiếm tỷ trọng xử lý đáng kể không. Tuy nhiên, đây là số liệu tổng hợp theo command, không thay thế p99 per script.

### 10.1. Kết hợp nhiều nguồn đo

| Nguồn | Quan sát được | Giới hạn cần nhớ |
|---|---|---|
| `System.nanoTime()` quanh `redis.execute(...)` | Thời gian ứng dụng cảm nhận | Gồm network, pool, serialization và chờ Redis |
| Micrometer Timer/histogram | Số lần gọi, p95/p99, lỗi theo tên script | Cần quản lý nhãn và số lượng metric |
| Redis `SLOWLOG` | Thời gian thực thi lệnh chậm tại server | Chỉ ghi lệnh vượt ngưỡng và đã hoàn thành |
| Redis `LATENCY` | Các sự kiện latency tại Redis nếu bật monitor | Phụ thuộc ngưỡng và loại event |
| `INFO commandstats` | Mức sử dụng/tổng thời gian theo loại command | Không nhận diện cụ thể từng script khi cùng dùng EVALSHA |
| `redis-cli --latency` | Latency quan sát từ client Redis | Chịu ảnh hưởng mạng và môi trường đo |
| Error/timeout/BUSY metrics | Mức độ ảnh hưởng đến availability | Không trực tiếp cho biết nguyên nhân hoặc số bước Lua |

Một script nhanh trên máy phát triển có thể chậm khi chạy với dữ liệu thật hoặc tải cao. Vì vậy nên đo cả Redis phía server **và** request phía ứng dụng trên các kịch bản đầu vào lớn, có concurrent traffic.

## 11. Đặt ngân sách thời gian cho Lua script

Không có giá trị duy nhất như “mọi Lua script phải dưới 5 ms”. Ngân sách hợp lý phải dựa trên:

- Yêu cầu p95/p99 của API phục vụ người dùng.
- Tải Redis server từ các ứng dụng khác.
- Tần suất gọi script.
- Thời gian xử lý của các command khác.
- Khả năng tăng kích thước dữ liệu trong tương lai.
- Sự khác biệt giữa Redis standalone, replication và cluster.
- Ngưỡng timeout/connection-pool của phía client.

Ví dụ nếu API yêu cầu phản hồi p99 dưới 100 ms và nhiều thao tác DB/Redis/network khác cũng dùng chung ngân sách, một Lua script chạy 80 ms có thể đã chiếm phần lớn giới hạn cho phép. Nếu script ấy được gọi thường xuyên, nó còn tăng độ trễ của các request không liên quan.

Một cách lập ngân sách mang tính minh họa:

```text
Tổng ngân sách API p99:            100 ms

- Network/application overhead:    25 ms
- Truy vấn hệ thống khác:           40 ms
- Redis call và chờ xử lý:          20 ms
- Dự phòng:                         15 ms
```

Trong ví dụ, không nên cho một script duy nhất tiêu hết 20 ms mà không còn phần chờ Redis hoặc truyền mạng. Đặt mục tiêu script nhỏ hơn đáng kể mức này, rồi xác nhận bằng load test.

### 11.1. Tần suất quan trọng ngang với thời gian từng lần

Một script chiếm server 10 ms nhưng chỉ chạy một lần mỗi giờ có tác động trung bình khác với script cũng chiếm 10 ms nhưng chạy hàng chục lần mỗi giây.

Cần nhìn song song:

```text
Chi phí một lần script x Số lần script mỗi giây
      -> áp lực trên luồng thực thi lệnh Redis
```

Phép ước lượng này chỉ giúp hình dung mức sử dụng năng lực xử lý; không thể dự đoán chính xác latency p99 vì còn phụ thuộc phân bố arrival, loại lệnh, I/O và các yếu tố runtime khác.

## 12. Đo hiệu năng theo kích thước đầu vào, không chỉ theo một ví dụ nhỏ

Khi đánh giá script, cần tạo những kịch bản có **dữ liệu tăng dần** theo trục có nguy cơ ảnh hưởng độ phức tạp:

| Kịch bản | Dữ liệu | Mục tiêu quan sát |
|---|---|---|
| Nhỏ | Một key String, một thao tác kiểm tra | Chi phí tối thiểu của script |
| Trung bình | Vài chục key hoặc vài trăm phần tử nếu nghiệp vụ yêu cầu | Thời gian tăng theo lượng công việc |
| Lớn trong giới hạn hỗ trợ | Batch bằng giới hạn đầu vào đã quy định | p95/p99 và độ trễ của lệnh khác |
| Tranh chấp cao | Nhiều client gọi cùng script/key | Xếp hàng, throughput và retry |
| Cấu trúc dữ liệu lớn | Hash/Set/List gần kích thước tối đa dự kiến | Chi phí ẩn trong lệnh như `HGETALL` hoặc `SMEMBERS` |
| Có lỗi | Key thiếu, sai kiểu, dữ liệu không hợp lệ | Script từ chối nhanh và không ghi dở |
| Redis Cluster | Các key theo hash slot thực tế | Giới hạn routing và thời gian theo node |

### 12.1. Đừng chỉ benchmark Lua trong môi trường không tải

Một script chạy 1 ms khi Redis gần như rảnh có thể khiến hệ thống chịu ảnh hưởng lớn hơn khi có hàng trăm request khác đang chờ.

Một thử nghiệm có ý nghĩa thường gồm:

1. Nạp dữ liệu có kích thước gần thực tế.
2. Tạo lưu lượng `GET`/`SET` nền đại diện cho ứng dụng.
3. Gọi script ở tần suất dự kiến.
4. Đo thời gian script tại client và Redis, đồng thời đo p95/p99 của traffic nền.
5. Thử dữ liệu đầu vào sát giới hạn và tình huống concurrency.
6. Giảm phạm vi xử lý nếu script làm tăng tail latency của traffic nền.

Mục đích không phải ép mọi script có thời gian tương đương nhau, mà xác định **mức công việc an toàn** và tác động khi dữ liệu/tần suất tăng.

## 13. Các chiến lược giảm thời gian script giữ Redis server

### 13.1. Ưu tiên lệnh Redis native nếu đã đủ chức năng

Nếu nhu cầu là tăng bộ đếm, dùng:

```redis
INCR metrics:views:42
```

Không cần Lua chỉ để làm:

```lua
local value = tonumber(redis.call('GET', KEYS[1]) or '0')
redis.call('SET', KEYS[1], value + 1)
return value + 1
```

Lệnh `INCR` đã thực hiện đọc, cộng và ghi nguyên tử với code ngắn hơn. Ngoài hiệu năng, dùng native command còn giảm khả năng mắc lỗi chuyển đổi và xử lý concurrency.

Tương tự, cân nhắc `SET ... NX EX`, `HINCRBY`, `SADD`, `GETDEL` và những lệnh Redis sẵn có khi chúng đã biểu diễn đúng phép toán.

### 13.2. Đưa kiểm tra đơn giản vào server, để xử lý nặng ở ứng dụng

Lua phù hợp cho logic nhỏ như:

```text
Đọc 1-2 giá trị
  |
Kiểm tra điều kiện
  |
Ghi 1-2 giá trị
  |
Trả status
```

Không nên đưa toàn bộ xử lý domain phức tạp, ghép dữ liệu lớn, tính báo cáo hoặc duyệt toàn bộ keyspace vào Lua chỉ để giảm round trip.

Nếu có thể, ứng dụng xử lý dữ liệu lớn ở ngoài Redis, còn Lua chỉ làm bước kiểm tra và cập nhật nguyên tử cuối cùng.

### 13.3. Giới hạn số lượng và kích thước dữ liệu

Đặt giới hạn:

- Số lượng key trong `KEYS`.
- Số phần tử được đọc từ collection.
- Số vòng lặp xử lý.
- Kích thước payload và dữ liệu phản hồi.
- Phạm vi giá trị numeric trong `ARGV`.
- Số thao tác ghi mà một script được phép tạo.

Nên kiểm tra giới hạn **ngay đầu script**, trước khi thực hiện các lệnh tốn công.

### 13.4. Thiết kế dữ liệu để tránh quét toàn bộ

Nếu thường xuyên cần “tìm item có điểm cao nhất”, thay vì quét mọi phần tử Set bên trong Lua, cân nhắc Sorted Set và lệnh truy xuất theo rank/score phù hợp.

Nếu thường xuyên cần “kiểm tra một email đã tồn tại”, cân nhắc key định danh hoặc cấu trúc tra cứu phù hợp thay vì lấy toàn bộ danh sách user rồi lặp.

Nếu thường xuyên cần xóa các key hết hạn, cân nhắc TTL native thay vì script quét mọi key định kỳ.

**Thay đổi mô hình dữ liệu** thường hiệu quả hơn việc tối ưu cú pháp Lua của một thuật toán quét quá rộng.

### 13.5. Chia thành batch và chấp nhận giao dịch theo từng đơn vị

Khi không cần tính nguyên tử trên toàn bộ tập, chia xử lý thành nhiều script ngắn để giảm thời gian chiếm server mỗi lần. Dùng cursor/progress marker và idempotency để worker có thể tiếp tục sau lỗi.

Phải mô tả rõ giới hạn nghiệp vụ: batch 1 có thể hoàn thành trong khi batch 2 chưa chạy. Nếu không chấp nhận trạng thái trung gian đó, hãy chọn mô hình trạng thái theo version hoặc công nghệ giao dịch phù hợp hơn.

### 13.6. `EVALSHA` giúp phần phân phối script, không tự làm thuật toán nhanh

Spring Data Redis có thể tải script và gọi theo SHA khi được driver/framework hỗ trợ. Cách này giúp tránh phải gửi toàn bộ script text cho mỗi lần gọi và có thể giảm overhead truyền/biên dịch trong một số trường hợp.

Nhưng:

```text
EVALSHA <sha> 1 key arg
```

**vẫn thực thi các vòng lặp và `redis.call(...)` của script**. Nếu thuật toán xử lý một triệu phần tử, chuyển từ `EVAL` sang `EVALSHA` không biến việc xử lý ấy thành nhanh hay không chặn server.

## 14. Khi Redis bị chặn bởi script dài: nhìn triệu chứng đúng cách

Những triệu chứng thường gặp:

- Độ trễ của `GET`, `SET`, `PING` và các request khác tăng đột biến.
- Client gặp command timeout dù kết nối mạng vẫn tồn tại.
- Redis log cảnh báo về script chạy quá lâu.
- Lệnh thường nhận phản hồi `BUSY Redis is busy running a script`.
- `SLOWLOG` sau khi script hoàn thành có entry `EVAL`/`EVALSHA` rất chậm nếu vượt ngưỡng.
- CPU trên Redis node tăng cao, nhưng cũng cần phân biệt với CPU từ công việc khác.

Một trình tự xử lý vận hành hợp lý:

1. **Xác định phạm vi ảnh hưởng:** node Redis nào, service nào, loại lệnh nào tăng latency.
2. **Đọc metric ứng dụng và Redis:** latency, lỗi `BUSY`, timeout, Redis SLOWLOG/LATENCY khi có thể.
3. **Xác định script được gọi:** tên nghiệp vụ, SHA/script ID, tần suất, số key và kích thước đầu vào.
4. **Đánh giá script có đang tiếp tục chạy hay đã hoàn thành:** SLOWLOG thường chỉ cho biết lệnh đã hoàn tất.
5. **Nếu script đang chạy quá lâu:** thực hiện xử lý theo runbook Redis và khả năng `SCRIPT KILL` nếu script chưa ghi; không mặc định có thể dừng an toàn sau khi đã ghi.
6. **Khắc phục nguyên nhân:** giới hạn batch, bỏ scan toàn bộ, dùng lệnh native, đặt metric và giới hạn đầu vào.
7. **Rà lại retry và idempotency:** request timeout có thể đã được thực thi; không gửi lại lệnh ghi một cách mù quáng.

Với Redis do nhà cung cấp dịch vụ quản lý, một số lệnh `CONFIG`, `SCRIPT KILL` hoặc công cụ quản trị có thể bị giới hạn theo quyền. Khi đó cần dùng metric, log và cơ chế vận hành được dịch vụ hỗ trợ.

## 15. Redis Cluster có giúp tránh tất cả vấn đề script chặn lệnh không?

Redis Cluster phân phối key qua các hash slot và nhiều node. Lua script thực thi trên node xử lý những key liên quan; **tính chặn lệnh xảy ra trên node đó**, không mặc nhiên chặn mọi node khác trong cluster.

Ví dụ:

```text
Redis Cluster

Node A: cache + stock slot nhóm A
   |
   +--- EVAL dài trên Node A
   |       -> lệnh khác phục vụ bởi Node A có thể bị chậm
   |
Node B: key ở slot nhóm B
   |
   +--- tiếp tục xử lý các lệnh riêng của Node B
```

Tuy vậy:

- Các key script truy cập phải tuân thủ quy tắc định tuyến và hash slot của cluster.
- Nếu workload tập trung ở một node/hot slot, script dài vẫn có thể ảnh hưởng nghiêm trọng tới ứng dụng.
- Thêm node không tự làm script đang duyệt quá nhiều dữ liệu trở thành an toàn.
- Các thao tác đa key nguyên tử không tùy ý vượt qua nhiều shard độc lập.
- Nếu một request ứng dụng chờ nhiều key ở nhiều node, một node bị nghẽn vẫn có thể làm cả request chậm.

Do đó, thiết kế script ngắn và có phạm vi công việc rõ ràng vẫn là yêu cầu quan trọng trong Redis Cluster.

## 16. Lua script so với `MULTI/EXEC` về thời gian chặn

Cả Lua và Redis transaction có thể được dùng để bảo đảm không có lệnh khác chen vào **trong lúc phần công việc nguyên tử được thực thi**. Tuy nhiên, chúng khác nhau về cách định nghĩa logic:

| Tiêu chí | Lua `EVAL`/`EVALSHA` | `MULTI`/`EXEC` |
|---|---|---|
| Logic điều kiện | Có thể `if`, vòng lặp và gọi lệnh dựa trên kết quả ngay trong server | Các lệnh được xếp hàng; ứng dụng chưa có kết quả `GET` để điều kiện hóa trước `EXEC` |
| Thời gian giữ quyền thực thi | Trong toàn bộ thời gian script chạy | Trong giai đoạn Redis thực thi nhóm lệnh ở `EXEC` |
| Rủi ro xử lý dài | Vòng lặp, dữ liệu lớn, command nặng | Nhiều lệnh được queue với khối lượng lớn |
| Rollback sau lỗi runtime | Không có rollback tổng quát | Không có rollback tổng quát |
| Giao dịch với DB ngoài Redis | Không | Không |
| Công cụ xử lý xung đột | Điều kiện nằm trong script | Có thể dùng `WATCH` trước `MULTI` |

Nếu công việc lớn bị gom vào `MULTI/EXEC`, Redis cũng có thể bận khi chạy nhóm lệnh. Vì vậy, chỉ chuyển cùng một khối lượng công việc từ Lua sang `MULTI` không đảm bảo giải quyết được latency.

Mục tiêu là **rút ngắn thời gian Redis phải xử lý liên tiếp không nhường cho lệnh khác**, thông qua thao tác nhỏ và giới hạn khối lượng công việc.

## 17. Những hiểu lầm về thời gian chạy Lua

**“Lua script là một lệnh Redis nên chắc chắn rất nhanh.”** Sai. Một lần `EVAL` có thể gọi hàng chục nghìn lệnh Redis bên trong và duyệt lượng dữ liệu lớn.

**“Tính nguyên tử chỉ liên quan dữ liệu, không ảnh hưởng latency.”** Sai. Script không bị chen giữa đồng thời ngăn các lệnh thông thường khác được thực thi trong lúc nó chạy.

**“Đặt `lua-time-limit = 5000` thì script tự bị dừng sau 5 giây.”** Sai. Ngưỡng này chủ yếu giúp Redis nhận biết script chạy quá lâu và chuyển sang cơ chế xử lý trạng thái bận; không có tự động rollback hay chặn đúng thời điểm.

**“`SCRIPT KILL` luôn dùng được khi script treo.”** Sai. Redis không cho kill script đã thực hiện ghi dữ liệu bằng cơ chế thông thường.

**“Timeout client nghĩa là script không còn chạy.”** Sai. Client có thể ngừng chờ khi server vẫn đang thực thi.

**“Chuyển `KEYS` thành `SCAN` bên trong cùng một script sẽ không chặn.”** Sai. Nếu loop SCAN được thực hiện hoàn toàn trong cùng `EVAL`, script vẫn giữ quyền thực thi cho tới lúc hoàn thành.

**“Một script chỉ có một `HGETALL`, không thể chậm.”** Sai. Một command đọc cấu trúc dữ liệu lớn cũng có thể tốn thời gian.

**“`EVALSHA` làm script nặng nhanh hơn về thuật toán.”** Sai. Nó giúp tối ưu cách gửi/tải script trong một số trường hợp, không thay đổi khối lượng công việc bên trong.

**“Chia script thành nhiều batch vẫn giữ nguyên tử trên toàn bộ công việc.”** Sai. Tính nguyên tử lúc đó chỉ còn ở từng batch; cần thiết kế trạng thái trung gian và khả năng khôi phục.

**“SLOWLOG không có record nghĩa là không có script chậm.”** Không thể kết luận. Ngưỡng có thể quá cao, log bị giới hạn, script đang chạy chưa hoàn thành hoặc vấn đề nằm ở network/pool.

**“Lua có rollback tự động nếu gặp exception.”** Sai. Các lệnh ghi đã hoàn thành bên trong script không được tự hoàn tác toàn bộ khi phát sinh lỗi sau đó.

## 18. Checklist thiết kế cho một Lua script mới

Trước khi dùng script ở lưu lượng thực tế, hãy xác định:

| Câu hỏi | Cách quyết định |
|---|---|
| Script giải quyết bất biến nào? | Viết rõ điều kiện phải được kiểm tra/cập nhật nguyên tử |
| Một Redis command có làm được không? | Nếu có, ưu tiên native command |
| Số key tối đa được xử lý? | Đặt giới hạn rõ ràng trong script |
| Kích thước lớn nhất của dữ liệu bên trong key? | Xem xét độ phức tạp của `HGETALL`, `SMEMBERS`, `LRANGE`... |
| Có vòng lặp phụ thuộc dữ liệu không? | Giới hạn số lần; cân nhắc chia batch |
| Có lệnh nặng trên Redis không? | Chọn cấu trúc dữ liệu/lệnh rẻ hơn nếu có thể |
| Những điều kiện lỗi có được kiểm tra trước khi ghi không? | Đưa validation lên đầu để tránh cập nhật dở dang |
| Client timeout có thể xảy ra không? | Xử lý kết quả không xác định và idempotency |
| Mục tiêu latency của script là bao nhiêu? | Dựa vào ngân sách p99 và tần suất gọi |
| Đã đo cả script và traffic nền chưa? | Dùng metric client, SLOWLOG/LATENCY và load test phù hợp |
| Chạy trên cluster không? | Xác định hash slot, node và giới hạn key |
| Script chạy lâu thì xử lý thế nào? | Có runbook, hiểu giới hạn `SCRIPT KILL` và rủi ro thao tác quản trị |

Đánh giá thời gian chạy phải là một phần của thiết kế bất biến nghiệp vụ, vì lựa chọn “cập nhật tất cả trong một lần nguyên tử” có thể đánh đổi trực tiếp bằng latency của cả Redis node.

## 19. Tình huống tổng hợp: thay script quét bằng script ngắn

Giả sử một hệ thống ghi nhận sự kiện học tập. Ban đầu, một script chạy định kỳ có nhiệm vụ:

```text
1. Tìm tất cả progress:* keys.
2. Đọc từng key.
3. Kiểm tra học viên không còn hoạt động.
4. Xóa hoặc cập nhật trạng thái.
5. Trả tổng số học viên đã xử lý.
```

Nếu script tự quét toàn bộ keyspace, nó có thể xử lý số lượng key ngày càng lớn và khiến những API đang dùng chung Redis bị chậm.

Một hướng thiết kế khác:

```text
Worker phía ứng dụng
    |
    +-- SCAN / đọc ID theo từng đợt ở ngoài script
    |
    +-- EVAL update_one_progress(key1) ----> hoàn thành
    +-- EVAL update_one_progress(key2) ----> hoàn thành
    +-- EVAL update_one_progress(key3) ----> hoàn thành
    |
    +-- Lưu checkpoint/progress
    +-- Tiếp tục batch sau
```

Script cho một học viên chỉ chịu trách nhiệm một phép toán nhỏ, chẳng hạn:

```lua
-- Ví dụ: đánh dấu một progress nếu trạng thái hiện tại còn là ACTIVE.
if redis.call('HGET', KEYS[1], 'status') ~= 'ACTIVE' then
    return 0
end

redis.call('HSET', KEYS[1], 'status', 'INACTIVE')
return 1
```

Giới hạn phạm vi thực thi giúp các lệnh khác có cơ hội được phục vụ giữa các lần `EVAL`. Worker cần xử lý retry, checkpoint và dữ liệu có thể thay đổi trong lúc quét. Nếu yêu cầu “tất cả người dùng đổi trạng thái cùng lúc”, bài toán phải được thiết kế thành phiên bản dữ liệu hoặc một mô hình giao dịch khác, vì chia batch không thể mang lại nguyên tử toàn cục.

## 20. Kết luận

Lua trong Redis là công cụ mạnh để **kiểm tra và cập nhật dữ liệu nguyên tử tại server**, nhưng đổi lại **script giữ quyền thực thi lệnh trong toàn bộ thời gian nó chạy**. Một script dài có thể làm những lệnh nhỏ của các client khác tăng độ trễ, gây timeout hoặc lỗi `BUSY`.

Khi dùng Spring Data Redis, không chỉ hỏi “script có đúng logic không?” mà còn phải trả lời:

1. **Khối lượng công việc lớn nhất của script là bao nhiêu?**
2. **Thời gian thực thi tại Redis và latency mà ứng dụng cảm nhận là bao nhiêu, đặc biệt ở p95/p99?**
3. **Script ảnh hưởng thế nào đến các lệnh của ứng dụng khác dùng chung server?**
4. **Nếu timeout hoặc xử lý dở, ứng dụng có retry và khôi phục an toàn không?**

Thực hành hiệu quả là giữ script ngắn, giới hạn key và dữ liệu đầu vào, ưu tiên lệnh native khi đủ khả năng, chia việc lớn thành nhiều bước nếu nghiệp vụ cho phép, kết hợp đo **client latency** với **SLOWLOG/LATENCY** phía Redis và tránh dựa vào `lua-time-limit` như một cách tự động dừng script.

Khi xem **thời gian chạy** là một phần của thiết kế **tính nguyên tử**, ứng dụng có thể tận dụng Lua để giải quyết race condition mà không làm Redis trở thành nút nghẽn cho toàn hệ thống.
