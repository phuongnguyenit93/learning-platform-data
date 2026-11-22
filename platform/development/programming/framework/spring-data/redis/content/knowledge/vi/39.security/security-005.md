# Giới hạn lệnh quản trị, script và thao tác xóa diện rộng

## 1. Vì sao một kết nối Redis dùng được không có nghĩa được phép làm mọi việc?

Một ứng dụng Spring Boot dùng **Spring Data Redis** để cache sản phẩm, lưu trạng thái phiên và hỗ trợ xử lý nền. Để đơn giản, mọi service cùng dùng một tài khoản Redis có toàn quyền. Một ngày, một phương thức dọn cache nhầm namespace, một script được triển khai sai hoặc một endpoint bảo trì bị gọi ngoài dự kiến.

```text
HTTP request / scheduled job
             |
             v
        Spring service
             |
             v
    RedisTemplate / CacheManager
             |
             v
      Redis connection
       (quá nhiều quyền)
             |
       +-----+------------------+
       |                        |
   GET cache key            FLUSHALL / EVAL
       |                        |
       v                        v
   Đọc hợp lệ             Xóa hoặc sửa rộng
```

Nếu cùng một tài khoản được phép gọi `GET`, `SET`, `CONFIG SET`, `FLUSHDB`, `FLUSHALL`, `EVAL` và `FUNCTION FLUSH`, chỉ một lỗi code hoặc tài khoản bị lộ có thể ảnh hưởng tới **toàn bộ Redis deployment**.

Bài học thuộc chương **Bảo mật** của **Spring Data Redis**, với mục tiêu:

- Giới hạn **lệnh quản trị** và những thao tác thay đổi cấu hình hay trạng thái toàn server.
- Chỉ cho phép **script Lua/Redis Functions** khi thật sự cần và có cơ chế rà soát.
- Chống **xóa diện rộng** ngoài ý muốn bằng ACL, phân tách tài khoản, giới hạn phạm vi và quy trình phê duyệt.
- Hiểu vì sao các API tiện lợi của `RedisTemplate`, `RedisCacheManager` và `@CacheEvict` vẫn cần được kiểm soát.
- Thiết kế kiểm thử quyền hạn, audit, cảnh báo và phương án phục hồi cho sự cố.

**Nguyên tắc cốt lõi:** một HTTP service chỉ được phép làm những thao tác Redis mà chức năng của nó thật sự cần. Lệnh quản trị, script tự do và xóa hàng loạt phải nằm sau **ranh giới quyền và quy trình riêng**.

## 2. Phân biệt ba nhóm rủi ro

### 2.1. Lệnh quản trị

Ví dụ:

```redis
CONFIG GET maxmemory
CONFIG SET maxmemory-policy allkeys-lru
ACL LIST
CLIENT KILL TYPE normal
SHUTDOWN
```

Không phải lệnh nào cũng xóa dữ liệu trực tiếp. Nhưng chúng có thể thay đổi cấu hình bảo mật, giết kết nối, dừng dịch vụ hoặc bộc lộ thông tin nhạy cảm.

### 2.2. Lệnh thao tác tập dữ liệu ở phạm vi lớn

Ví dụ:

```redis
FLUSHDB
FLUSHALL
KEYS *
```

- `FLUSHDB` xóa các key trong logical database hiện tại theo ngữ nghĩa của lệnh.
- `FLUSHALL` xóa các key trong tất cả logical databases trên server đó.
- `KEYS *` không xóa, nhưng có thể duyệt toàn bộ keyspace và tạo áp lực khi dataset lớn; còn có rủi ro làm lộ tên khóa.

Trong Redis Cluster, các lệnh server-local như `FLUSHALL` thực hiện trên **node nhận lệnh**, không tự biến thành một transaction xóa toàn bộ Cluster. Nhưng với quyền quản trị và khả năng gửi tới nhiều node, một tác vụ lỗi vẫn có thể phá hủy dữ liệu diện rộng. **Không được hiểu “chỉ tác động một node” là an toàn**.

### 2.3. Script và programmable operations

Ví dụ:

```redis
EVAL "return redis.call('GET', KEYS[1])" 1 app:cache:product:42
```

Script có thể giúp thực hiện nhiều bước trên Redis một cách nguyên tử đối với các lệnh khác trên cùng server/slot. Nhưng code script cũng có thể:

- Đọc hoặc ghi nhiều khóa.
- Lặp qua tập dữ liệu và tiêu tốn thời gian CPU.
- Thực hiện `DEL`/`UNLINK` trên tập khóa rộng.
- Làm phát sinh lỗi khó xử lý khi schema hoặc tham số sai.
- Tạo vấn đề vận hành khi quá nhiều tài khoản được phép chạy script tùy ý.

Redis Functions cũng mang rủi ro tương tự ở những vai trò có quyền **cài đặt, thay đổi hoặc xóa function libraries**.

## 3. Không chỉ chống tấn công: còn chống lỗi vận hành

Các tình huống gây sự cố phổ biến:

| Tình huống | Tác động có thể xảy ra |
|---|---|
| Web API dùng tài khoản quản trị | Lỗ hổng API có thể dẫn tới thao tác Redis đặc quyền |
| Developer gọi `FLUSHALL` trong script thử nghiệm | Xóa nhiều dữ liệu ngoài phạm vi test |
| Đổi prefix cache nhưng xóa bằng pattern quá rộng | Xóa cả cache của phiên bản khác |
| `@CacheEvict(allEntries = true)` trên cache shared | Xóa toàn bộ region khi chỉ muốn xóa một entry |
| Một `EVAL` dùng key từ user input | Thao tác lên key ngoài phạm vi dự kiến |
| Job chạy `KEYS *` trong giờ cao điểm | Redis latency tăng mạnh |
| Dùng tài khoản có `+@all` | Lỗi ở một service có blast radius lớn |
| Cho mọi instance chạy job cleanup | Nhiều tác vụ xóa đồng thời, khó kiểm soát |
| Quyền `CONFIG`/`ACL` bị lộ | Thay đổi chính sách, tạo tài khoản mới hoặc mở quyền |
| Không có audit/recovery | Khó biết ai xóa gì và khôi phục đến đâu |

Đây là vấn đề **thiết kế ranh giới tin cậy**, không chỉ là tìm một danh sách lệnh “nguy hiểm”.

## 4. Redis ACL là lớp bảo vệ chính ở server

Redis hỗ trợ **Access Control Lists (ACL)** để quản lý tài khoản và quyền thực thi lệnh.

Một chính sách ACL có thể giới hạn:

1. **User:** tài khoản nào được phép kết nối và xác thực.
2. **Commands:** loại lệnh hoặc subcommand nào được chạy.
3. **Keys:** các mẫu key mà tài khoản được phép truy cập đối với những lệnh kiểm tra key permissions.
4. **Pub/Sub channels:** các channel mà tài khoản được phép truy cập.
5. Một số cơ chế phân quyền đọc/ghi cụ thể tùy phiên bản Redis.

Đây là lớp bảo vệ **phía Redis server**, không phụ thuộc việc lập trình viên có vô tình gọi API nguy hiểm hay không.

Ví dụ:

```text
Spring Product API       -> Redis user app_cache_read
Spring Cache Writer      -> Redis user app_cache_write
Migration/Cleanup Job    -> Redis user cache_maintainer
Infrastructure Operator  -> Redis admin role
```

Mỗi nhóm có quyền khác nhau. Không cần cho REST API quyền `FLUSHALL` chỉ vì nhóm vận hành thỉnh thoảng cần dọn Redis.

### 4.1. Default user là nơi dễ vô tình mở rộng quyền

Nếu mọi ứng dụng dùng một tài khoản mặc định có quyền rất rộng, việc thêm service mới làm tăng số nơi giữ credentials đặc quyền.

Mô hình tốt hơn:

- Tạo user riêng cho từng ứng dụng hoặc chức năng cần thiết.
- Chuyển client sang tài khoản ít quyền.
- Hạn chế hoặc vô hiệu hóa cách truy cập mặc định không còn cần thiết, theo quy trình tránh gián đoạn.
- Cấp credentials qua secret manager.
- Không lưu username/password trong repository, log hoặc lệnh shell có thể bị ghi lịch sử.
- Kiểm tra môi trường staging trước khi thay ACL production.

Tài khoản quản trị phải có đường truy cập riêng, quyền cấp phát và giám sát riêng.

### 4.2. ACL dùng ở đâu?

Redis ACL có thể cấu hình qua cơ chế quản trị tương ứng, ví dụ `ACL SETUSER`, file ACL hoặc nền tảng managed Redis nếu provider hỗ trợ giao diện khác.

Các ví dụ `ACL SETUSER` dưới đây là **minh họa trên Redis thử nghiệm có quyền quản trị**. Không copy nguyên mật khẩu hoặc thay ACL trên production mà chưa có kế hoạch xác thực/rollback.

## 5. Ví dụ cấp một tài khoản cache reader ít quyền

Giả sử ứng dụng chỉ được đọc Redis String theo namespace:

```text
app:cache:product:v2:*
```

Trong phiên `redis-cli` tương tác **đã xác thực bằng tài khoản quản trị**:

```redis
ACL SETUSER app_product_reader reset on >demo-change-me ~app:cache:product:v2:* resetchannels -@all +get +mget +exists +ttl +pttl
```

**Lưu ý:** `>demo-change-me` là mật khẩu **giả dùng trong môi trường lab**, không được sử dụng thật. Nếu gửi lệnh qua shell thay vì `redis-cli` tương tác, ký tự `>` có thể bị shell diễn giải thành chuyển hướng output; đồng thời mật khẩu có thể bị ghi vào command history. Trong production, ưu tiên quy trình cấp secrets/ACL phù hợp với hệ thống quản lý bí mật.

Giải thích:

| Thành phần | Ý nghĩa |
|---|---|
| `app_product_reader` | Tên user chuyên dụng |
| `reset` | Đặt lại các quy tắc ACL của user trước khi gán chính sách mới |
| `on` | Bật user |
| `>...` | Đặt mật khẩu |
| `~app:cache:product:v2:*` | Mẫu key được phép theo ACL key checks |
| `resetchannels` | Xóa các quyền channel cũ |
| `-@all` | Thu hồi quyền với toàn bộ nhóm lệnh trước khi cấp lại |
| `+get`, `+mget`, `+exists` | Chỉ cho phép một số lệnh đọc cụ thể |
| `+ttl`, `+pttl` | Cho phép xem TTL khi ứng dụng cần |

Cách cấp quyền theo **allowlist** giúp tránh trường hợp một Redis upgrade bổ sung lệnh mới trong nhóm quyền rộng mà ứng dụng vô tình có thêm khả năng.

### 5.1. Kiểm tra chính sách bằng ACL GETUSER

Quản trị viên có thể kiểm tra:

```redis
ACL GETUSER app_product_reader
```

Kết quả giúp quan sát command rules, key patterns, channel patterns và trạng thái user.

Chú ý rằng output ACL có thể chứa **password hashes hoặc thông tin cấu hình quyền**. Không đưa output này vào log công khai hoặc tài liệu có quyền truy cập rộng.

### 5.2. Test command được phép

Kết nối bằng tài khoản test:

```text
AUTH app_product_reader <password-from-secret-manager>
GET app:cache:product:v2:42
TTL app:cache:product:v2:42
```

Các lệnh này chỉ thành công nếu kết nối, key và ACL phù hợp.

### 5.3. Test command bị cấm

Các yêu cầu sau phải bị từ chối với user reader:

```redis
SET app:cache:product:v2:42 "new"
DEL app:cache:product:v2:42
FLUSHDB
FLUSHALL
CONFIG SET maxmemory 100000000
EVAL "return 1" 0
```

Mục tiêu của bài test là **xác nhận Redis server thực thi chính sách**, không phải chỉ kiểm tra rằng code hiện tại không gọi những lệnh đó.

**Không chạy thử `FLUSHALL` bằng một tài khoản đặc quyền trên Redis chứa dữ liệu thật.** Hãy dùng `ACL DRYRUN` hoặc một Redis cô lập với quyền hạn được kiểm tra trước.

## 6. Những giới hạn của ACL key patterns

Một mẫu:

```text
~app:cache:product:v2:*
```

giới hạn key arguments theo các cơ chế ACL hỗ trợ. Nhưng nó **không có nghĩa Redis tự hiểu mọi ngữ nghĩa nghiệp vụ**.

### 6.1. Prefix không thay thế tenant authorization

Giả sử ứng dụng nhận:

```http
DELETE /cache/products/42
```

Tài khoản Redis được phép xóa:

```text
app:cache:product:v2:*
```

Nếu API không xác thực người gọi và không kiểm tra quyền theo tenant, người dùng vẫn có thể xóa cache của người khác **trong cùng namespace được phép**.

ACL kiểm tra quyền của **Redis user** mà ứng dụng sử dụng; nó không biết ai là người dùng HTTP cuối cùng nếu tất cả request đi qua cùng một tài khoản.

Vì vậy:

```text
HTTP authorization
        +
Business validation
        +
Redis ACL
        =
Các lớp bảo vệ bổ sung
```

Không có lớp nào thay thế hoàn toàn lớp khác.

### 6.2. Một số lệnh duyệt keyspace cần hạn chế riêng

Các lệnh như:

```redis
KEYS *
SCAN 0 MATCH *
```

không tương đương với thao tác `GET <key>` cụ thể. Việc duyệt **tên key** có thể làm lộ metadata của các namespace khác và tạo tải.

**Không giả định** một ACL `~prefix:*` tự làm kết quả `SCAN`/`KEYS` bị lọc chỉ còn prefix đã được cấp quyền. Phân quyền của những lệnh liệt kê cần được đánh giá theo phiên bản Redis và ACL command checks.

Với ứng dụng chỉ cần `GET`/`SET`, cách bảo vệ tốt nhất là **không cấp `KEYS` hoặc `SCAN` ngay từ đầu**.

### 6.3. Multi-key commands phải xét từng key

Một lệnh:

```redis
MGET app:cache:product:v2:42 private:session:abc
```

không được phép vượt giới hạn key permissions chỉ vì key đầu hợp lệ. Redis ACL kiểm tra các key arguments theo ngữ nghĩa của lệnh.

Ở Redis Cluster còn có giới hạn hash slot với một số lệnh nhiều key. Đây là **quy tắc định tuyến**, khác với ACL.

### 6.4. Key pattern không phải parser dữ liệu

Một key name có thể chứa thông tin người dùng. ACL không tự mã hóa/che dữ liệu trả về. Đừng đưa `GET`, `SCAN` hoặc `KEYS` vào một endpoint “debug Redis” không có kiểm soát.

## 7. Cấp quyền tối thiểu theo chức năng

Không nên mở nguyên nhóm lệnh `+@all` cho một ứng dụng chỉ cần `GET` và `SET`.

Một ma trận thiết kế:

| Vai trò | Cần làm | Quyền đáng cân nhắc | Không nên có |
|---|---|---|---|
| Product read API | Tra cứu cache | `GET`, `MGET`, `TTL`, key pattern product | `FLUSH*`, `CONFIG`, `EVAL`, `DEL`, `SCAN` |
| Product cache writer | Ghi/cập nhật đúng key | `GET`, `SET`, `DEL` nếu có invalidation theo ID | `FLUSH*`, `ACL`, `MODULE`, script tự do |
| Session lookup | Đọc session theo key | Các lệnh đọc cần thiết, namespace session | Quyền với namespace khác |
| Stream consumer | Đọc group, ACK/claim đúng Stream | `XREADGROUP`, `XACK`, `XAUTOCLAIM` theo nhu cầu | `XGROUP DESTROY`, `XTRIM`, `FLUSHALL` nếu không dùng |
| Cache maintenance | Dọn một region xác định | `SCAN`/`UNLINK` trong namespace, có quy trình duyệt | Quyền quản trị toàn Redis |
| DB/Redis admin | Cấu hình, backup, incident response | Quyền đặc biệt có kiểm soát | Dùng credentials này trong web service |
| Script deployment | Cài đặt script/function đã duyệt | Quyền deploy script chuyên dụng | Giao credential cho HTTP handler |

Đây là **ma trận thiết kế**, không phải cú pháp ACL đầy đủ. Một chức năng thực tế có thể cần các lệnh bổ sung (`EXISTS`, `PTTL`, `HGET`, `HSET`, `EVALSHA`…) tùy template, serializer và Spring Cache internals.

**Dùng logs của ACL denial và integration tests để điều chỉnh quyền cần thiết**, thay vì mở `+@all` khi gặp một lỗi `NOPERM`.

## 8. Vì sao `+@all` và các command categories rộng dễ rủi ro?

Redis ACL có các command categories như `@read`, `@write`, `@admin`, `@dangerous`, `@scripting` và các nhóm khác. Có thể xem trên Redis được quản trị:

```redis
ACL CAT
ACL CAT dangerous
ACL CAT scripting
```

Chúng là cơ chế phân nhóm tiện dụng, nhưng khi mở cả một category, tập lệnh được cấp có thể rộng hơn nhu cầu ứng dụng.

Ví dụ:

```text
Ứng dụng chỉ cần một GET
        |
        v
Cấp +@read toàn bộ
        |
        v
Có thể mở cả những thao tác đọc/duyệt
mà ứng dụng chưa đánh giá
```

Không nên dùng `+@all` để giải quyết nhanh một lỗi quyền `NOPERM`.

### 8.1. Command allowlist tốt hơn khi tập lệnh nhỏ

Ví dụ app chỉ dùng String cache:

```redis
ACL SETUSER app_cache_writer reset on >demo-change-me ~app:cache:* resetchannels -@all +get +set +del +unlink +exists +pttl
```

Lưu ý:

- Đây là **ví dụ quyền cho toàn namespace cache**, có thể rộng hơn nhu cầu một service.
- `+del` và `+unlink` cho phép xóa các key nằm trong mẫu được phép; Redis không tự phân biệt xóa đúng một key với xóa toàn vùng.
- `+unlink` chỉ cần nếu code thật sự sử dụng `UNLINK`.
- Không cấp `+scan` chỉ vì muốn “sau này tiện dọn”.
- ACL không kiểm tra “đã có ticket phê duyệt hay chưa”. Đó là trách nhiệm hệ thống gọi.

### 8.2. Cú pháp subcommand và phiên bản

Các quyền hẹp theo subcommand có thể được cấu hình bằng cú pháp ACL tương ứng của phiên bản Redis, ví dụ `+config|get` để cho phép riêng một subcommand thay vì toàn bộ `CONFIG`.

Tuy nhiên, không nên đoán rằng mỗi lệnh hay subcommand đều được hỗ trợ theo đúng cách trong mọi phiên bản. Hãy kiểm tra `ACL CAT`, `COMMAND INFO` và tài liệu của Redis đang dùng, rồi kiểm thử bằng `ACL DRYRUN`.

Ngay cả một lệnh “chỉ đọc” như xem cấu hình cũng có thể bộc lộ thông tin hệ thống; không mở chỉ để dễ debugging.

## 9. Những lệnh cần bảo vệ ở cấp quản trị

### 9.1. FLUSHDB và FLUSHALL

```redis
FLUSHDB
FLUSHALL
```

- `FLUSHDB` xóa các key của database hiện tại trên Redis server thực thi lệnh.
- `FLUSHALL` xóa key của các databases trên Redis server đó.
- Các lựa chọn `ASYNC`/`SYNC` ảnh hưởng cách giải phóng tài nguyên, **không làm lệnh trở thành an toàn hoặc có thể hoàn tác**.

Ví dụ:

```redis
FLUSHALL ASYNC
```

có thể làm key biến mất khỏi keyspace ngay trong khi bộ nhớ được giải phóng ở background. Không được hiểu “ASYNC” là có khoảng thời gian để cancel thao tác.

**Không đưa `FLUSHDB`/`FLUSHALL` vào ứng dụng HTTP và không dùng chúng để clear một cache region.**

### 9.2. CONFIG SET, CONFIG REWRITE

```redis
CONFIG SET maxmemory-policy allkeys-lru
CONFIG REWRITE
```

Có thể thay đổi hành vi eviction, notifications hoặc những thuộc tính vận hành khác; thay đổi sai làm dữ liệu cache hay kết nối bị ảnh hưởng.

Ngay cả khi một cấu hình không ảnh hưởng lập tức, nó có thể ảnh hưởng hành vi sau restart.

Cần giới hạn những lệnh này cho vai trò quản trị với quy trình thay đổi cấu hình, audit và rollback.

### 9.3. ACL và user management

```redis
ACL SETUSER
ACL DELUSER
ACL LOAD
ACL SAVE
```

Người có thể quản lý ACL có thể thay đổi quyền truy cập. Đây là một **ranh giới đặc quyền**.

Tài khoản ứng dụng thường không cần quyền thay user hoặc reload ACL. Một lỗi ACL có thể khiến mọi ứng dụng không đăng nhập được.

### 9.4. CLIENT, MONITOR, DEBUG, SHUTDOWN, MODULE

Một số ví dụ:

```redis
CLIENT KILL TYPE normal
MONITOR
SHUTDOWN
```

- `CLIENT KILL`: có thể ngắt kết nối ứng dụng khác.
- `MONITOR`: có thể làm lộ commands/arguments và gây áp lực hiệu năng.
- `DEBUG`: các thao tác debug sâu cần được hạn chế theo chính sách của Redis.
- `SHUTDOWN`: dừng Redis process.
- `MODULE LOAD`: nạp module ảnh hưởng tới tiến trình Redis, ranh giới bảo mật đặc biệt quan trọng.

Không để ứng dụng bình thường có quyền như một operator chỉ vì cùng chạy trong mạng nội bộ.

### 9.5. Topology và replication commands

Các thao tác liên quan vai trò primary/replica, Redis Cluster và failover như `REPLICAOF`, `CLUSTER` subcommands hoặc các lệnh Sentinel quản trị có thể thay đổi khả năng sẵn sàng và dữ liệu.

Một ứng dụng cache thông thường không nên được phép chủ động đổi topology. Quyền và API cụ thể cần được đánh giá theo loại triển khai: standalone, Sentinel, Cluster hoặc managed Redis.

## 10. Script Lua: lợi ích và bề mặt rủi ro

Spring Data Redis có thể thực thi script qua `RedisTemplate.execute(RedisScript, ...)` hoặc Reactive Redis operations.

Ví dụ atomic compare-and-delete cho một lock:

```lua
-- KEYS[1] = lock key
-- ARGV[1] = owner token được kỳ vọng

if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end

return 0
```

Cách thực hiện này tránh lỗi giữa `GET` và `DEL`: chỉ xóa nếu key vẫn thuộc owner cũ.

Nhưng script có nhiều quyền hơn một API `delete(key)` nếu được viết thiếu cẩn trọng.

### 10.1. Không dùng script như đường vòng qua ACL

Một hiểu nhầm:

```text
Tài khoản không có quyền DEL
nhưng có EVAL
=> chạy redis.call('DEL') trong script để xóa
```

Không được mặc định script có thể vượt ACL của người gọi. Redis kiểm tra quyền đối với các lệnh được gọi từ script theo cơ chế và phiên bản Redis liên quan. Chính sách đúng cần thử **cả lệnh ngoài lẫn các lệnh bên trong script**.

Tuy vậy, nếu user được cấp cả `EVAL` lẫn nhiều lệnh ghi/đọc, nó có thể viết **script tùy ý** bằng những quyền đã có. Vì thế `+eval` không phải một quyền nhỏ chỉ vì script “thường dùng để xóa một lock”.

### 10.2. Cấm input tự do trở thành Lua code

Ví dụ **không an toàn**:

```java
String script = "return redis.call('" + operation + "', '"
        + keyFromHttp + "')";
```

Nếu `operation` hoặc nội dung script bị điều khiển bởi client, bạn đã biến input ngoài thành mã lệnh. Ngay cả khi ACL ngăn một số command, đây vẫn là thiết kế nguy hiểm.

Tốt hơn:

- Script là **tài nguyên cố định trong source code**, được review.
- Tham số động được truyền qua `KEYS` và `ARGV`, không nối vào script source.
- Chỉ dùng các lệnh thật sự cần.
- Kiểm tra số lượng khóa, kiểu và giới hạn payload.
- Đặt timeout/điều kiện tải phù hợp.
- Không cho endpoint nhận một chuỗi Lua do người dùng cung cấp rồi gửi vào Redis.

### 10.3. KEYS và ARGV phải đúng vai trò

Với Redis scripting:

```lua
redis.call('GET', KEYS[1])
```

`KEYS` chứa **tên key**; `ARGV` chứa các tham số không phải tên key, như giá trị mong đợi hoặc TTL.

Không giấu tên key trong `ARGV` để cố vượt qua quy tắc định tuyến/khai báo key của Redis. Trong Redis Cluster, các key do script truy cập phải được cung cấp và tuân thủ slot constraints, theo yêu cầu của phiên bản Redis.

### 10.4. Script có tính nguyên tử nhưng không phải rollback toàn bộ

Redis thực thi Lua script với ngữ nghĩa nguyên tử đối với các lệnh khác trên một Redis server trong khi script chạy. Tuy nhiên, **lỗi runtime sau khi script đã thực hiện một số thay đổi không tự rollback những thay đổi đó**.

Ví dụ:

```lua
redis.call('SET', KEYS[1], 'updated')
redis.call('HSET', KEYS[2], 'field', 'value')
```

Nếu `KEYS[2]` có kiểu không phù hợp hoặc lệnh thứ hai thất bại, thay đổi từ `SET` đầu tiên không nhất thiết được hoàn tác.

Script cần:

1. Kiểm tra điều kiện đầu vào và loại dữ liệu khi có thể.
2. Hạn chế tác dụng phụ.
3. Thiết kế idempotency/khả năng chạy lại khi cần.
4. Không xem `EVAL` là transaction xuyên database hay external services.

### 10.5. Script CPU-intensive có thể ảnh hưởng toàn node

Một script thực hiện nhiều thao tác hoặc vòng lặp dài có thể giữ Redis bận, làm request khác bị trễ.

Không dùng Lua để quét toàn bộ keyspace, tạo hàng triệu thao tác xóa hoặc xử lý một payload không giới hạn chỉ vì script “atomic”.

Đặt ngân sách cho:

```text
Số key
Kích thước arguments
Số lệnh nội bộ
Thời gian chạy
Tần suất gọi
```

`lua-time-limit` và những cơ chế Redis liên quan không thay thế review script; việc xử lý script chậm có hạn chế và tác động vận hành riêng.

## 11. Redis scripting permissions và danh tính script

### 11.1. EVAL, EVALSHA, SCRIPT và FUNCTION không giống nhau

| Nhóm | Vai trò | Rủi ro cần quản lý |
|---|---|---|
| `EVAL` | Gửi và chạy script Lua | Cho phép code script động qua Redis |
| `EVALSHA` | Chạy script đã tồn tại trong script cache bằng SHA | SHA là định danh script, không phải bản thân quyền ứng dụng |
| `SCRIPT LOAD` | Nạp script vào cache | Ảnh hưởng tập script có thể chạy |
| `SCRIPT FLUSH` | Xóa cache script | Các lệnh EVALSHA có thể gặp `NOSCRIPT` |
| `SCRIPT KILL` | Can thiệp script đang chạy khi điều kiện cho phép | Tác động vận hành |
| `FUNCTION LOAD`/`RESTORE` | Cài đặt function libraries | Thay đổi code chạy trong Redis |
| `FUNCTION DELETE`/`FLUSH` | Xóa function hoặc libraries | Có thể làm ứng dụng gọi function bị lỗi |
| `FCALL`/`FCALL_RO` | Gọi Redis Function | Vẫn phải quản lý quyền và hành vi của function |

Không nhất thiết một ứng dụng cần quyền `SCRIPT LOAD` chỉ vì nó sử dụng script đã được nạp sẵn. Mặt khác, nếu Spring Data Redis dùng cơ chế fallback sang `EVAL` khi script cache không còn, việc chỉ cấp `EVALSHA` có thể làm ứng dụng lỗi `NOSCRIPT`.

### 11.2. Không dùng script SHA như một access token

Một chuỗi SHA của script dùng để định danh nội dung script. Nó **không phải** một chữ ký cấp quyền và không tự bảo vệ resource khỏi một client đã có đủ quyền để chạy script.

Nếu ứng dụng yêu cầu chỉ được chạy vài script có review:

- Quản lý mã script trong source control.
- Có quy trình build/review/deployment.
- Hạn chế người có thể load hoặc thay đổi script/function.
- Tách Redis user dành cho script-enabled service khỏi reader chỉ cần `GET`.
- Giữ quyền key/command ở phạm vi tối thiểu.
- Test hành vi sau restart, failover và script cache miss.
- Không nghĩ rằng `EVALSHA` tự tạo allowlist từng SHA ở tầng Redis ACL.

### 11.3. Redis Functions cũng cần quản trị vòng đời

Redis Functions cho phép triển khai code phía server để gọi lại bằng tên function. So với script gửi theo từng lời gọi, chúng có vòng đời quản lý khác.

Những thao tác quản trị như thay thế, xóa hoặc flush function libraries phải được bảo vệ tách biệt với người gọi function theo nghiệp vụ.

Một service cần `FCALL` không nhất thiết phải có quyền `FUNCTION LOAD` hoặc `FUNCTION FLUSH`.

## 12. Ví dụ Spring Data Redis chạy script cố định

Spring Data Redis có `DefaultRedisScript`, giúp load script resource và thực thi qua `RedisTemplate`.

Ví dụ một script cố định:

```java
package com.example.redis.security;

import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

@Service
public class SafeLockReleaseService {

    private static final String RELEASE_LUA = """
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                return redis.call('DEL', KEYS[1])
            end
            return 0
            """;

    private final StringRedisTemplate redis;
    private final DefaultRedisScript<Long> releaseScript;

    public SafeLockReleaseService(StringRedisTemplate redis) {
        this.redis = redis;

        releaseScript = new DefaultRedisScript<>();
        releaseScript.setScriptText(RELEASE_LUA);
        releaseScript.setResultType(Long.class);
    }

    public boolean release(String resourceId, String ownerToken) {

        if (resourceId == null
                || !resourceId.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("Invalid resourceId");
        }

        if (ownerToken == null || ownerToken.isBlank()) {
            throw new IllegalArgumentException("Missing owner token");
        }

        String key = "app:locks:{" + resourceId + "}";

        Long result = redis.execute(
                releaseScript,
                List.of(key),
                ownerToken
        );

        return Long.valueOf(1L).equals(result);
    }
}
```

Các điểm bảo vệ:

- Code Lua là **hằng trong source**, không đến từ request.
- Tên key có prefix cố định và ID được validate.
- Script chỉ có một key và một giá trị owner.
- Chỉ `DEL` khi giá trị hiện tại khớp.
- Dùng `StringRedisTemplate` để truyền giá trị theo serializer chuỗi.
- Tên key chứa `{resourceId}` nhằm phục vụ yêu cầu cùng slot nếu sau này mở rộng giao thức khóa trong Redis Cluster.

Giới hạn:

- Owner token phải được sinh bằng cơ chế không dễ trùng và giữ bí mật phù hợp, không lấy tùy ý từ một API công khai.
- Redis ACL của user gọi script phải cho phép những lệnh cần thiết theo chính sách và phiên bản Redis đang dùng.
- Không gọi method này chỉ vì một HTTP user đưa vào một `resourceId` hợp lệ; vẫn cần authorization.
- Script chỉ bảo vệ việc **release đúng lock**; nó không tự ngăn stale worker ghi vào tài nguyên ngoài Redis sau khi TTL hết hạn.
- Nếu script bị mất khỏi cache, Spring Data Redis có thể thử `EVAL` thay `EVALSHA`; hãy kiểm thử quyền và hành vi thực tế.

## 13. Vì sao `@CacheEvict(allEntries = true)` có thể nguy hiểm?

Spring Cache cung cấp:

```java
@CacheEvict(cacheNames = "products", allEntries = true)
public void clearProducts() {
}
```

Nhiều developer dùng annotation này với ý nghĩa “xóa cache sản phẩm”. Nhưng thực chất nó có thể yêu cầu **xóa toàn bộ cache region**, không phải một product key.

Tùy `RedisCacheManager`/`RedisCacheWriter`:

- Redis cache region có key prefix được sinh theo cấu hình.
- Clear có thể quét tìm các key phù hợp.
- RedisCacheWriter mặc định ở những phiên bản Spring Data Redis phổ biến dùng chiến lược dựa trên **`KEYS` và `DEL`** cho thao tác clear.
- Có lựa chọn cấu hình **SCAN batch strategy** để tránh vấn đề quét toàn keyspace bằng `KEYS` theo cách blocking trên dataset lớn.

Vì vậy, `@CacheEvict(allEntries = true)` trong một API public có thể gây hiệu ứng xóa hàng loạt và tăng latency Redis/database.

### 13.1. Xóa một entry khác với clear region

Xóa một sản phẩm:

```java
@CacheEvict(cacheNames = "products", key = "#productId")
public void invalidateProduct(long productId) {
    // Update nguồn dữ liệu hoặc nghiệp vụ tương ứng.
}
```

Xóa cả cache:

```java
@CacheEvict(cacheNames = "products", allEntries = true)
public void clearAllProducts() {
}
```

Hãy xem **clear region là một operation quản trị ứng dụng**, dù nó được biểu diễn bằng annotation.

### 13.2. RedisCacheWriter và chiến lược SCAN

Với phiên bản Spring Data Redis hỗ trợ `BatchStrategies`, có thể cấu hình:

```java
package com.example.redis.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.BatchStrategies;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.cache.RedisCacheWriter;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
public class RedisCacheSecurityConfig {

    @Bean
    public RedisCacheManager cacheManager(
            RedisConnectionFactory factory) {

        RedisCacheWriter writer =
                RedisCacheWriter.nonLockingRedisCacheWriter(
                        factory,
                        BatchStrategies.scan(500)
                );

        return RedisCacheManager.builder(writer).build();
    }
}
```

Cấu hình này minh họa cách dùng SCAN theo batch cho thao tác clear. Nó **không** tự giới hạn người được quyền gọi clear hoặc tổng số key có thể bị xóa.

Các giới hạn cần lưu ý:

- `SCAN` là quét theo cursor, **không phải snapshot nguyên tử**.
- Nhiều batch vẫn có thể tạo áp lực Redis.
- Trong Redis Cluster, hỗ trợ SCAN và cách driver truy cập mọi node phụ thuộc cấu hình/driver. Lettuce có khả năng tốt hơn trong những trường hợp Cluster so với một số triển khai Jedis ở các phiên bản nhất định.
- Nếu ACL cấm `SCAN` hoặc `DEL`, thao tác clear có thể thất bại. Không vì thế mà mở cả lệnh quản trị cho mọi service.
- Với một region chứa hàng triệu key, chuyển từ `KEYS` sang `SCAN` là biện pháp giảm rủi ro, **không phải cấp phép xóa vô hạn**.

Một lựa chọn kiến trúc tốt hơn là **không cho web service thường gọi allEntries**, và cung cấp một maintenance service riêng có ACL, xác thực và giới hạn.

## 14. Thao tác xóa đúng một key bằng Spring Data Redis

Nếu cần vô hiệu hóa cache một sản phẩm, hãy xây API có **phạm vi hẹp** thay vì một helper nhận wildcard.

```java
package com.example.redis.security;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheInvalidator {

    private final StringRedisTemplate redis;

    public ProductCacheInvalidator(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public boolean invalidateOne(long productId) {

        if (productId <= 0) {
            throw new IllegalArgumentException(
                    "productId must be positive"
            );
        }

        String key = "app:cache:product:v2:" + productId;

        return Boolean.TRUE.equals(redis.unlink(key));
    }
}
```

Điểm quan trọng:

1. Key prefix được cố định trong code.
2. API nhận **một ID**, không nhận `*` hay Redis command.
3. `UNLINK` xóa key khỏi keyspace, còn phần giải phóng bộ nhớ có thể diễn ra bất đồng bộ.
4. ACL của service có thể giới hạn key pattern.
5. Phải áp dụng authorization ở controller/service trước khi cho user tác động đến sản phẩm.
6. Có thể ghi audit ở mức `operation=product_cache_invalidate`, không log raw session/token hay payload.

### 14.1. UNLINK không có nghĩa xóa được hoàn tác

```redis
UNLINK app:cache:product:v2:42
```

Khóa được loại khỏi keyspace; việc giải phóng bộ nhớ có thể diễn ra ở background. Tác dụng xóa đối với reader là thực tế và không tự đảo ngược.

Vì vậy **`UNLINK` an toàn hơn `DEL` về chi phí giải phóng một số object lớn**, nhưng không tự an toàn hơn về **phạm vi dữ liệu bị xóa**.

### 14.2. Không nhận raw Redis key từ public API

Không nên:

```java
public void delete(String userProvidedKey) {
    redis.delete(userProvidedKey);
}
```

Nếu tài khoản có quyền với nhiều namespace, một caller có thể xóa nhầm key ngoài chức năng dự kiến.

Tốt hơn:

```text
User input: productId=42
       |
Validate ID + authorization
       |
Build key from fixed prefix
       |
Redis delete/unlink exactly one key
```

Không dùng `"prefix:" + input` khi `input` có thể chứa cú pháp wildcard/phân tách hoặc làm thay đổi miền dữ liệu; xác định rõ domain model và định dạng ID.

## 15. Xóa theo namespace: vì sao cần một quy trình riêng?

Trong một số tình huống vận hành, cần xóa cache của một phiên bản ứng dụng:

```text
app:cache:product:v2:*
```

Một cách nhanh nhưng rủi ro:

```redis
KEYS app:cache:product:v2:*
```

sau đó gửi nhiều `DEL` liên tiếp. Với tập key lớn, cách này có thể tạo tải đáng kể và có thể vượt phạm vi dự kiến nếu pattern sai.

Một phương án quản trị tốt hơn dùng **quét theo lô, giới hạn số key và điều kiện an toàn**.

```text
Maintenance request
         |
         v
Authentication + operator role
         |
         v
Explicit namespace / environment / ticket
         |
         v
Dry-run estimate + blast-radius review
         |
         v
Approval + canary
         |
         v
SCAN bounded
         |
         v
UNLINK small batches
         |
         v
Metrics, audit, abort conditions
```

### 15.1. Các điều kiện bắt buộc trước khi chạy

Một tác vụ xóa diện rộng cần có:

- **Môi trường:** production, staging hoặc local có được xác định chắc chắn?
- **Target:** Redis instance/Cluster và database nào?
- **Namespace:** một prefix cố định từ allowlist, không nhập wildcard tùy ý.
- **Loại dữ liệu:** cache tái tạo được hay dữ liệu không thể mất?
- **Quy mô:** ước lượng số key, dung lượng, DB reload cost.
- **Phê duyệt:** ai được phép yêu cầu/duyệt, với ticket hoặc change record?
- **Ngân sách tải:** batch size, rate limit, thời gian chạy, concurrency.
- **Cách dừng:** abort khi vượt giới hạn, khi latency tăng hoặc khi sai môi trường.
- **Rollback:** có nguồn nạp lại không, hay cần backup/restore?
- **Audit:** ai thực hiện, lúc nào, target, lý do, số lượng đã xóa.

Đặc biệt, một **dry-run SCAN chỉ là ước lượng theo thời điểm chạy**. Keyspace có thể thay đổi; số key ở lúc thực thi có thể khác.

### 15.2. Ví dụ lệnh SCAN

```redis
SCAN 0 MATCH app:cache:product:v2:* COUNT 100
```

`COUNT` là gợi ý mức công việc cho Redis, không đảm bảo mỗi lần trả đúng 100 key.

`SCAN`:

- Có thể trả trùng key.
- Có thể trả danh sách rỗng dù cursor chưa về `0`.
- Không phải snapshot.
- Có thể quan sát key thêm/xóa trong lúc chạy.
- Không có bảo đảm mọi key vừa xuất hiện trong quá trình scan đều được thấy.
- Trong Redis Cluster, cần bao phủ các primary/slot liên quan.

Nếu muốn xóa đúng một vùng cache, sau scan cần **kiểm tra lại key nằm trong prefix được phép** trước khi thực hiện `UNLINK`, không chỉ tin rằng mọi dữ liệu từ scan đã an toàn.

### 15.3. Batch UNLINK

Ví dụ trong môi trường thử nghiệm:

```redis
UNLINK app:cache:product:v2:42 app:cache:product:v2:43
```

`UNLINK` có thể nhận nhiều key. Tuy nhiên, với Redis Cluster, các lệnh nhiều key có giới hạn slot hoặc cần client chia lô phù hợp topology. Không mặc định `UNLINK key1 key2` hoạt động khi hai key ở hai hash slot khác nhau.

Một maintenance job có thể chia theo node/slot hoặc xóa từng key qua client cluster-aware, và cần được kiểm thử thực tế.

### 15.4. Cần giới hạn cứng, không chỉ log cảnh báo

Ví dụ:

```text
Max keys to delete for one run: 10.000
Max operations per second:       100
Max duration:                     15 minutes
Maximum concurrent jobs:          1
```

Đây là **ngưỡng minh họa**, không phải giá trị an toàn phổ quát.

Nếu job vượt số lượng hoặc bắt đầu thấy Redis p99/DB load tăng, nó phải có quyền **dừng**, không chỉ ghi “warning” rồi tiếp tục xóa.

Trong hệ thống có nhiều worker, điều phối để không vô tình chạy cùng cleanup trên nhiều instance. Một distributed lock có thể giúp tránh chạy trùng, nhưng không thay thế authorization và safety limits.

## 16. Tại sao xóa hàng loạt không thể bảo đảm hoàn toàn atomic?

Giả sử cần xóa 500.000 key. Một job SCAN theo batch:

```text
Batch 1 -> UNLINK 100 keys
Batch 2 -> UNLINK 100 keys
...
Batch N -> UNLINK 100 keys
```

Nếu job crash ở batch 120:

- Một số key đã bị xóa.
- Một số key chưa bị xóa.
- Một số key có thể được ứng dụng nạp lại trong lúc job chạy.
- Nếu chạy lại SCAN, key đã xóa có thể không còn, key mới có thể xuất hiện.

Do đó:

- Batch delete là **partial-progress operation**.
- Không tự cam kết “xóa toàn bộ namespace trong một transaction”.
- Cần job có thể chạy lại an toàn và đối soát.
- Nếu mục tiêu là invalidation tức thời với nhiều cache entries, cân nhắc **đổi phiên bản namespace** thay vì quét/xóa trực tiếp, rồi dọn key cũ theo TTL.

### 16.1. Namespace versioning để giảm blast radius

Thay vì:

```text
Delete all app:cache:product:v2:*
```

có thể đổi app sang:

```text
app:cache:product:v3:*
```

Khi đó:

- App mới bỏ qua cache v2.
- Cache v3 được tạo dần.
- Cache v2 còn trong Redis đến khi TTL hết hoặc cleanup sau.
- Không phải xóa hàng trăm nghìn key ngay tại thời điểm chuyển phiên bản.

Đánh đổi:

- Memory có thể tăng tạm thời vì v2 và v3 cùng tồn tại.
- Database có thể bị load cao do v3 lạnh.
- Vẫn cần TTL và dọn dẹp có kiểm soát.
- Nếu dữ liệu không phải cache tái tạo được, đổi namespace không phải giải pháp xóa hoặc migration tùy ý.

### 16.2. Thời điểm cache invalidation và tính nhất quán

Xóa cache region không tự đảm bảo request tiếp theo đọc được dữ liệu mới nhất. Nếu đồng thời có reader/writer nạp lại cache từ database, cần thiết kế cache-aside, transaction boundary và cách chống race phù hợp.

Một job cleanup có thể làm database nhận hàng loạt cache miss. Vì vậy, **công cụ an toàn với Redis vẫn có thể gây outage ở database** nếu xóa quá nhiều key cùng lúc.

## 17. RedisTemplate có những API cần bảo vệ

Spring Data Redis cung cấp quyền truy cập tiện lợi:

```java
redisTemplate.delete(key);
redisTemplate.unlink(key);
redisTemplate.scan(scanOptions);
```

Và ở tầng connection thấp hơn có thể có các lệnh quản trị hoặc thao tác rộng tùy phiên bản:

```java
redisTemplate.getConnectionFactory()
        .getConnection()
        .serverCommands();
```

Một ví dụ về vấn đề thiết kế:

```text
Public controller
       |
       v
Service được inject StringRedisTemplate
       |
       v
Có thể gọi nhiều operations theo Redis user hiện có
```

**Không có Java visibility modifier nào tự thay thế ACL ở server.** Nếu tài khoản Redis có quyền quản trị, code hoặc một dependency bị lỗi có thể phát lệnh không mong muốn.

### 17.1. Tách Redis access layer theo mục đích

Một thiết kế dễ kiểm soát:

```text
ProductQueryService
      |
      v
ProductCacheReader
      |
      v
Read-only Redis credentials

ProductWriteService
      |
      v
ProductCacheWriter
      |
      v
Writer credentials with scoped key permissions

Maintenance job
      |
      v
CacheMaintenanceClient
      |
      v
Dedicated, limited maintenance credentials
```

Các service nghiệp vụ không cần biết chi tiết `RedisConnection` hay `FLUSHDB`.

### 17.2. Không tiêm maintenance template vào public controller

Kể cả khi có annotation phân quyền HTTP, tránh biến template quản trị thành bean mặc định để tất cả service dễ dàng inject.

Có thể:

- Đặt maintenance job ở deployment hoặc module riêng.
- Sử dụng một Redis user riêng.
- Cấp secret maintenance chỉ cho workload được phép.
- Giới hạn network và lịch hoạt động.
- Tạo các method có phạm vi nghiệp vụ rõ ràng.
- Ghi audit và yêu cầu approval khi xóa nhiều.

**Tách bean trong cùng JVM chỉ là ranh giới thiết kế code**, chưa phải bảo mật cứng nếu cả hai credentials đều nằm trong cùng process. Tách deployment và secret scope có thể giảm blast radius mạnh hơn.

## 18. Spring Boot: cấu hình kết nối có username/password

Với Spring Boot 3.x, có thể cấu hình:

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6379}
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
      timeout: 2s
```

Đây là ví dụ cho một Redis endpoint sử dụng TLS. `REDIS_*` phải được cấp bởi cơ chế quản lý cấu hình/secret phù hợp; **không** commit thông tin bí mật vào file cấu hình thực tế.

Lưu ý:

- Host/port, username/password, TLS và ACL phải tương thích với Redis server hoặc managed Redis.
- Spring Boot phiên bản cũ có thể dùng prefix `spring.redis.*`.
- Với Sentinel, có thể cần cấu hình xác thực/TLS riêng cho Sentinel nodes và data nodes theo khả năng của driver/Boot.
- Với Cluster, client phải truy cập được các node được công bố qua topology.
- Không ghi URI chứa credential vào log khi lỗi kết nối.
- Xác nhận ứng dụng thật sự dùng `RedisConnectionFactory` đã cấu hình, nhất là khi dự án tự tạo factory.

### 18.1. Nguyên tắc cấp secrets

Nên sử dụng:

- Secret manager, Kubernetes Secrets được bảo vệ, hoặc cơ chế tương đương.
- Giới hạn workload nào nhận secret nào.
- Quy trình xoay vòng credentials.
- Không ghi plaintext password vào source control/CI logs.
- Không truyền secret trực tiếp như một argument để nó xuất hiện trong process list nếu có phương án an toàn hơn.
- Thu hồi tài khoản cũ khi đã xác minh toàn bộ client chuyển sang user mới.

### 18.2. TLS và network isolation vẫn cần thiết

ACL chỉ có giá trị nếu bên gọi đã được xác thực và kết nối được kiểm soát.

Môi trường production nên xét:

```text
Application network
        |
      TLS
        |
 Redis endpoint protected by ACL
        |
  Private network / firewall / security groups
```

Không expose Redis ra Internet chỉ vì đã đặt password. Tùy topology còn cần bảo vệ Sentinel, Redis Cluster bus, Redis admin endpoints và các replica.

## 19. Redis ACL DRYRUN: thử quyền mà không thực thi lệnh

Redis các phiên bản có hỗ trợ `ACL DRYRUN` (Redis 7+) cho phép quản trị viên **kiểm tra ACL** với một lệnh mô phỏng, không thực sự chạy tác dụng của lệnh đó.

Ví dụ trên Redis test hoặc phiên quản trị có quyền:

```redis
ACL DRYRUN app_product_reader GET app:cache:product:v2:42
```

Kết quả dự kiến: cho phép nếu key pattern và command rules phù hợp.

Thử một lệnh bị cấm:

```redis
ACL DRYRUN app_product_reader FLUSHALL
```

Kết quả dự kiến: bị từ chối.

Thử xóa một key:

```redis
ACL DRYRUN app_product_reader DEL app:cache:product:v2:42
```

Kết quả dự kiến: bị từ chối.

Thử GET namespace khác:

```redis
ACL DRYRUN app_product_reader GET private:session:token
```

Kết quả dự kiến: bị từ chối.

### 19.1. DRYRUN không thay integration test

ACL DRYRUN đánh giá quyền cho lệnh được chỉ định; nó không thay thế kiểm thử ứng dụng thật với pipeline, transaction, scripts, RedisCacheWriter và các API khác.

Đặc biệt, với Lua script:

```text
Outer command: EVAL
Inner calls: GET, DEL, ...
```

Một phép dry run của `EVAL` không chứng minh rằng tất cả lệnh bên trong script đều được chấp thuận hoặc rằng script an toàn về ngữ nghĩa.

Cần kiểm thử cả script trong một Redis **cô lập** với tài khoản quyền tối thiểu.

### 19.2. Điều cần test trước khi áp ACL production

- `@Cacheable` hoạt động khi cache hit/miss.
- Ghi cache với TTL hoạt động.
- `@CacheEvict` theo một key hoạt động nếu được phép.
- Clear cache toàn region **bị từ chối** với user read-only.
- `KEYS`, `SCAN` bị từ chối nếu không nằm trong hợp đồng.
- `FLUSHDB`, `FLUSHALL`, `CONFIG`, `ACL`, `MODULE` bị từ chối.
- Script đã duyệt có đủ quyền nhưng không thể thao tác namespace ngoài dự kiến.
- App có lỗi rõ ràng khi Redis trả `NOPERM`, không nuốt thành miss.
- Connection pool và Lettuce reconnect không tự chuyển sang user đặc quyền.
- Đổi user/password không làm gián đoạn dịch vụ ngoài cửa sổ dự kiến.

## 20. ACL LOG: phát hiện quyền bị từ chối

Redis cung cấp thông tin ACL denials thông qua `ACL LOG` trong phiên bản hỗ trợ.

```redis
ACL LOG
```

Tín hiệu cần quan sát:

- Tên user nào bị từ chối.
- Lệnh hoặc loại quyền nào bị thiếu.
- Thời điểm xảy ra.
- Những thất bại xác thực hoặc access denied.

Ví dụ:

```text
user=app_product_reader
reason=command
object=FLUSHALL
```

Đây là dữ liệu minh họa, không phải định dạng bắt buộc của mọi exporter.

### 20.1. ACL denial là một tín hiệu bảo mật

Nếu một application user bỗng thử `FLUSHALL`, `CONFIG SET` hoặc `EVAL` dù ứng dụng được thiết kế chỉ để đọc cache, cần điều tra:

- Có code deployment mới gọi nhầm không?
- Có dependency hoặc script không mong muốn không?
- Có tài khoản/secret bị lộ không?
- Có người vận hành dùng nhầm credentials không?
- Có nguồn yêu cầu bất thường không?

Không giải quyết bằng cách mở quyền cho mọi command ngay lập tức.

### 20.2. Không đưa toàn bộ ACL LOG vào hệ thống log ít bảo vệ

ACL logs có thể chứa tên key, user, command và thông tin phục vụ kiểm tra truy cập. Một số key có thể chứa ID hoặc token nhạy cảm.

Cần giới hạn quyền đọc, thời gian lưu, dữ liệu xuất ra và cơ chế lọc. Tương tự, full `MONITOR` hoặc raw Redis command traces không phù hợp để bật liên tục trên production.

## 21. Xử lý NOPERM trong Spring Data Redis

Khi Redis ACL từ chối lệnh, Redis trả lỗi dạng `NOPERM`. Spring Data Redis/Lettuce có thể bọc lỗi đó thành exception thuộc nhóm command/data access phù hợp tùy phiên bản.

Ví dụ sai:

```java
try {
    return redis.opsForValue().get(key);
} catch (RuntimeException ignored) {
    return null;
}
```

Hành vi này biến lỗi quyền thành “không có cache”. Nó che sự cố ACL và có thể làm database bị tăng tải do fallback hàng loạt.

Tốt hơn:

```text
GET trả value  -> CACHE HIT
GET trả null   -> CACHE MISS
GET trả NOPERM -> AUTHORIZATION / CONFIG ERROR
GET timeout    -> REDIS DEPENDENCY ERROR
```

### 21.1. Không retry NOPERM liên tục

Khi tài khoản không có quyền với một lệnh, gửi lại đúng lệnh đó 100 lần thường không thay đổi kết quả.

Nên:

1. Ghi metric `redis_acl_denied_total` hoặc một category tương đương tại tầng ứng dụng khi phân loại được lỗi.
2. Giữ original exception làm cause khi wrap.
3. Ghi log an toàn: operation alias, service name, exception class, trace ID.
4. Không log raw credentials, toàn bộ key/value hoặc script arguments.
5. Tạo cảnh báo cho những lệnh không nằm trong quyền dự kiến.
6. Dừng retry vô ích.
7. Sửa ACL hoặc code thông qua quy trình có review, không tự động mở quyền ở runtime.

Không đưa `ex.getMessage()` của Redis trực tiếp ra HTTP response vì nó có thể tiết lộ tên key, command hoặc cấu hình nội bộ.

## 22. Security in depth: ACL không phải bức tường duy nhất

Một hệ thống production nên phối hợp:

```text
User / HTTP client
       |
       v
Authentication + Authorization
       |
       v
Service API with fixed operations
       |
       v
Validation + Rate limit + Audit
       |
       v
Redis client with least-privilege ACL
       |
       v
TLS / private network
       |
       v
Redis data node
```

### 22.1. Bảo vệ ngay tại API

Ví dụ controller chỉ nhận ID:

```text
DELETE /api/products/42/cache
```

Không cung cấp endpoint như:

```text
POST /admin/redis/execute
Body: {"command":"FLUSHALL"}
```

Một endpoint “Redis console từ xa” là bề mặt nguy hiểm, kể cả khi được đặt sau authentication. Nếu thật sự cần console vận hành, nên sử dụng công cụ quản trị riêng với giám sát, phê duyệt và mạng giới hạn.

### 22.2. Defense in depth khi lệnh đã được phép

Giả sử Redis user có quyền `DEL` trong prefix `app:cache:*`. ACL không thể tự biết:

```text
Xóa 1 key do invalidate hợp lệ
hay
Xóa 1.000.000 key do job chạy sai
```

Cả hai đều dùng `DEL` trên key được phép. Vì thế cần thêm:

- Hard cap số key mỗi tác vụ.
- Batch size và rate limit.
- Một job duy nhất tại một thời điểm.
- Danh sách prefix từ allowlist.
- Preview + approval khi là tác vụ diện rộng.
- Phân biệt dry-run và execute.
- Giới hạn môi trường/Redis cluster.
- Metrics và khả năng abort.

## 23. Audit cho thao tác nhạy cảm

Một bản ghi audit nên trả lời:

```text
Ai?
Thao tác gì?
Trên môi trường nào?
Namespace hoặc resource nào?
Vì sao?
Được phê duyệt bởi ai?
Bao nhiêu key?
Bắt đầu và kết thúc lúc nào?
Có lỗi/abort không?
```

Ví dụ:

```json
{
  "event": "redis_cache_purge",
  "actorRole": "cache-maintainer",
  "environment": "staging",
  "namespaceAlias": "product_cache_v2",
  "changeTicket": "CHG-000123",
  "dryRun": false,
  "keysDeleted": 1750,
  "status": "completed"
}
```

Không ghi:

```text
raw Redis password
full token
entire user data
full Lua ARGV
```

Audit phải được lưu trong nơi có retention/access controls phù hợp; không chỉ trong một Redis cache có thể bị chính job xóa.

### 23.1. Phân biệt “yêu cầu xóa” và “đã xóa thành công”

Một tác vụ có thể bắt đầu nhưng chỉ hoàn thành một nửa:

```text
requested=10000
scanned=9500
deleted=7800
failed=100
aborted=true
```

Không ghi `success=true` ngay từ lúc job được chấp nhận. Báo cáo cần phản ánh tác động thực tế và có thể đối soát.

## 24. Mẫu thử nghiệm an toàn về ACL và xóa diện rộng

### 24.1. Môi trường

Dùng Redis riêng cho bài test:

```text
Redis local/test
User admin-test
User app_product_reader
User app_cache_writer
User cache_maintainer
```

Không dùng Redis production để chạy thử các lệnh xóa nguy hiểm.

### 24.2. Chuẩn bị vài khóa test

Trong phiên quản trị của Redis **cô lập**:

```redis
SET app:cache:product:v2:1 "A" EX 120
SET app:cache:product:v2:2 "B" EX 120
SET app:cache:user:v2:1 "C" EX 120
```

### 24.3. Kiểm tra reader chỉ đọc được namespace

Dùng ACL DRYRUN từ tài khoản admin:

```redis
ACL DRYRUN app_product_reader GET app:cache:product:v2:1
ACL DRYRUN app_product_reader GET app:cache:user:v2:1
ACL DRYRUN app_product_reader DEL app:cache:product:v2:1
ACL DRYRUN app_product_reader FLUSHALL
```

Kỳ vọng:

| Lệnh | Quyết định ACL |
|---|---|
| `GET app:cache:product:v2:1` | Allow |
| `GET app:cache:user:v2:1` | Deny |
| `DEL app:cache:product:v2:1` | Deny |
| `FLUSHALL` | Deny |

### 24.4. Kiểm tra chức năng app và service thực

Trong bài integration test, đăng nhập đúng Redis user rồi:

- Thực hiện GET hợp lệ.
- Thử GET namespace không được cấp.
- Thử SET/DEL trái quyền.
- Thử RedisTemplate chạy script đã duyệt nếu service có quyền.
- Thử `@CacheEvict(allEntries = true)` với user không được phép.
- Xác nhận app phân loại NOPERM đúng, không làm thành cache miss.
- Xác nhận audit và metric không chứa secrets.

Mọi thử nghiệm destructive chỉ chạy trên dữ liệu cô lập. Với `ACL DRYRUN`, lệnh được **kiểm tra quyền nhưng không thực thi**.

### 24.5. Thử giới hạn batch

Một maintenance job test với namespace:

```text
app:cache:product:v2:*
```

có thể cấu hình hard cap 2 key/run rồi tạo 5 key test.

Kỳ vọng:

- Dry-run ước lượng vượt cap.
- Job execute bị từ chối hoặc dừng trước khi vượt cap theo chính sách.
- Không xóa namespace user.
- Audit ghi rõ `cap_exceeded` hoặc một trạng thái tương đương.
- Redis vẫn hoạt động bình thường.
- Test không cần `FLUSHALL` để cleanup.

## 25. Quy trình thay đổi ACL mà không gây outage

Thay ACL production quá đột ngột có thể làm mọi request Redis trả `NOPERM`.

Một lộ trình an toàn:

1. **Inventory:** liệt kê các lệnh ứng dụng thật sự dùng; bao gồm Spring Cache, RedisTemplate, scripts, listeners, Redis Streams và jobs.
2. **Define roles:** đọc, ghi, Stream consumer, script executor và maintenance riêng khi cần.
3. **Create restricted accounts:** cấp credentials mới trong môi trường staging.
4. **Integration tests:** chạy các chức năng hợp lệ và negative ACL tests.
5. **Observability:** bật/kiểm tra ACL denial metrics, error rate và latency.
6. **Canary rollout:** cho một phần ứng dụng dùng credentials mới.
7. **Monitor:** xem NOPERM, cache miss/error, script cache failover và business SLO.
8. **Full rollout:** chuyển các instance còn lại.
9. **Revoke excess access:** thu hồi tài khoản cũ/đặc quyền sau khi xác nhận không còn client phụ thuộc.
10. **Periodic review:** đối chiếu quyền đang cấp với code hiện tại, nhất là sau Redis/Spring upgrades.

### 25.1. Những quyền thường bị bỏ sót

- Cache clear có thể dùng `KEYS`/`SCAN` và `DEL` theo chiến lược.
- Spring Data Redis script execution có thể dùng `EVALSHA` rồi fallback `EVAL`.
- Redis repositories có thể dùng Hash, Set và index operations.
- Redis Streams consumer cần lệnh `XREADGROUP`, `XACK`, `XPENDING`, `XAUTOCLAIM` tùy workflow.
- Key expiration có thể yêu cầu `EXPIRE`, `PEXPIRE` hoặc dùng `SET` với TTL.
- Test/application warmup có thể gửi `PING`.
- Health check/monitoring có thể dùng `INFO` hoặc `PING`.
- Redis Pub/Sub có `SUBSCRIBE`/`PSUBSCRIBE` và channel ACL.
- Redis Cluster/Sentinel có topology commands/protocol interactions tùy driver.

Không giải quyết thiếu quyền bằng cách mở `+@all`. Dùng kết quả đo/ACL denial để xác định **lệnh cần thiết chính xác**.

### 25.2. Redis Cluster cần xét nhiều node

Trong Redis Cluster, các Redis nodes khác nhau có ACL state và các điều kiện vận hành cần được đồng bộ theo quy trình quản trị phù hợp. Không mặc định thay quyền trên một node sẽ tự đáp ứng yêu cầu trên toàn Cluster trong mọi triển khai.

Một client cluster-aware có thể được định tuyến tới node khác theo hash slot; nếu user/quyền không nhất quán giữa các node, một key hoạt động còn key khác trả `NOPERM`.

Cần test:

- Kết nối tới nhiều primary.
- Keys ở nhiều hash slots.
- Redirect `MOVED`/`ASK`.
- Replica reads nếu bật `ReadFrom`.
- Failover và quyền của node được promote.
- ACL cho pub/sub và scripts nếu dùng.

### 25.3. Sentinel và tài khoản dữ liệu không nhất thiết là một

Sentinel có endpoint và cơ chế quản trị riêng. Spring Boot dùng Sentinel cần khám phá primary và kết nối đến data nodes.

Không giả định một credential duy nhất hoạt động cho cả Sentinel và Redis data nodes nếu topology/driver/provider yêu cầu tách xác thực. Quản lý secret theo đúng connection path và test failover thực tế.

## 26. Backup và khôi phục trước thao tác xóa quan trọng

ACL và phê duyệt giảm khả năng xảy ra lỗi, nhưng không có biện pháp nào đảm bảo tuyệt đối một thao tác xóa không bao giờ xảy ra.

Khi dữ liệu quan trọng:

- Xác định có RDB/AOF, snapshot hoặc backup theo chính sách hay không.
- Biết bản backup lưu ở đâu và ai có quyền restore.
- Kiểm tra khôi phục trên môi trường test.
- Định nghĩa RPO/RTO cho dữ liệu bị xóa.
- Kiểm tra backup có bao phủ Redis Cluster nodes và topology liên quan không.
- Không xem replica là backup cho một lệnh xóa hợp lệ; xóa có thể được replication.
- Không xem `UNLINK` hay `FLUSHALL ASYNC` là thao tác có thể rollback.

### 26.1. Cache tái tạo được và dữ liệu không thể mất

| Dữ liệu | Sau khi xóa nhầm |
|---|---|
| Product cache từ PostgreSQL | Có thể warm lại từ DB, cần chống cache stampede |
| Search result cache | Có thể tái tạo nhưng có thể làm tăng tải nguồn |
| Session/token | Có thể ảnh hưởng đăng nhập và chính sách bảo mật |
| Redis Streams chứa công việc | Có thể mất work items và consumer metadata |
| Idempotency records | Có thể tạo nguy cơ xử lý nghiệp vụ trùng |
| Fencing sequence | Reset có thể tái sử dụng token, nguy hiểm |
| Counter duy nhất tại Redis | Có thể không khôi phục chính xác nếu không có nguồn khác |

Vì vậy, không nên cho mọi loại dữ liệu nằm chung một Redis user mà web app có thể gọi `FLUSHALL`.

## 27. Monitoring và cảnh báo cho command nguy hiểm

Nên quan sát:

- ACL denials, đặc biệt lệnh quản trị không được phép.
- Redis connection/auth failures.
- Thay đổi ACL/users và thay đổi cấu hình.
- Số lần chạy maintenance jobs.
- Số key bị xóa theo job và namespace.
- Redis commands/s, latency p95/p99.
- Cache hit/miss/error sau khi clear.
- Database fallback/load sau khi xóa cache.
- Redis memory, eviction/expiration và keyspace changes.
- Redis role/topology changes.
- Script execution failures, `NOSCRIPT`, script latency theo cách đo phù hợp.

Lưu ý: `INFO commandstats` có thể cung cấp số liệu về nhiều command theo server, nhưng dữ liệu cụ thể phụ thuộc phiên bản và không nhất thiết cho biết **người dùng nào** thực hiện.

Để có audit chính xác “ai đã xóa”, phải ghi nhận ở ranh giới maintenance job, ACL/authorization logs và các nguồn vận hành đáng tin cậy. Không dùng một bộ đếm tổng `DEL`/`UNLINK` để khẳng định ai là tác giả.

### 27.1. Những cảnh báo có giá trị cao

| Cảnh báo | Tại sao quan trọng |
|---|---|
| App user bị từ chối `FLUSHALL` | Có hành vi ngoài thiết kế hoặc lạm dụng |
| App user bị từ chối `CONFIG`/`ACL` | Có ý định thao tác đặc quyền |
| Số key giảm đột ngột | Có thể là cleanup sai hoặc expiration theo lịch |
| Cache miss tăng đồng loạt | Có thể xóa nhầm hoặc đổi namespace |
| Database QPS tăng sau cleanup | Có thể cache stampede |
| Script chạy lâu/timeout | Có thể chặn Redis hoặc gây retry storm |
| `NOSCRIPT` tăng sau restart | Quy trình script load/fallback chưa đúng |
| Nhiều NOPERM sau deployment | ACL hoặc cấu hình client lệch nhau |

Một sự kiện ACL denial không tự chứng minh có tấn công. Nó là tín hiệu điều tra, cần kết hợp phiên bản deploy, danh tính workload, trace và môi trường.

## 28. Những sai lầm thường gặp

### Sai lầm 1: Dùng cùng một admin credential cho mọi microservice

Nếu một service bị lỗi hoặc bị xâm nhập, nó có blast radius toàn Redis. Tách user và quyền.

### Sai lầm 2: Cấp `+@all` vì Spring Cache báo NOPERM

Có thể cấp quyền nguy hiểm vượt xa lệnh thiếu. Điều tra lệnh thực tế, cấp từng lệnh phù hợp.

### Sai lầm 3: Tin rằng `~prefix:*` tự ngăn mọi cách liệt kê key

`SCAN` và `KEYS` cần được kiểm soát riêng; không giả định ACL key pattern là bộ lọc liệt kê namespace.

### Sai lầm 4: Coi `FLUSHALL ASYNC` là ít nguy hiểm vì chạy nền

Key có thể không còn trong keyspace dù bộ nhớ được giải phóng sau. Xóa vẫn có phạm vi lớn.

### Sai lầm 5: Coi `UNLINK` là thao tác an toàn về mặt dữ liệu

`UNLINK` vẫn xóa key khỏi keyspace; khác biệt chính là cách giải phóng bộ nhớ.

### Sai lầm 6: Dùng `KEYS *` trong một endpoint dọn cache

Có thể gây blocking work trên keyspace lớn và làm lộ tên khóa. Dùng quy trình maintenance giới hạn.

### Sai lầm 7: Cho public API nhận full Redis key

Caller có thể ảnh hưởng tới key ngoài phạm vi nghiệp vụ. Nhận logical ID rồi tự sinh key cố định.

### Sai lầm 8: Cho người dùng gửi Lua script trực tiếp

Biến API thành code execution trên Redis theo quyền tài khoản đó. Chỉ chạy scripts được review.

### Sai lầm 9: Chỉ kiểm tra lệnh EVAL bên ngoài

Script có nhiều `redis.call` nội bộ; phải đánh giá command/key permissions và hành vi script thực.

### Sai lầm 10: Coi script atomic là transaction rollback

Nếu script lỗi sau khi một số lệnh đã thay đổi dữ liệu, những thay đổi trước đó không tự được hoàn tác.

### Sai lầm 11: Dùng SCRIPT FLUSH như thao tác cleanup cache

Nó xóa cache script chứ không phải cache dữ liệu; có thể gây `NOSCRIPT` cho ứng dụng.

### Sai lầm 12: Đặt full admin secrets trong application.yml

Dễ lộ qua source control, logs, backup hoặc artifact. Dùng secrets management và tách workload.

### Sai lầm 13: Coi authenticated Redis là đủ khi expose Internet

Cần network isolation, TLS, ACL và bảo vệ hạ tầng.

### Sai lầm 14: Không kiểm thử RedisCacheWriter clear

Một số cấu hình dùng `KEYS`/`DEL`; đổi ACL có thể làm clear lỗi hoặc tạo tác động lớn. Cần kiểm thử đường clear riêng.

### Sai lầm 15: Chạy SCAN/UNLINK batch không có hard cap

Quét theo lô giúp điều tiết tải nhưng có thể xóa hàng triệu key nếu để chạy vô hạn.

### Sai lầm 16: Dry-run được xem là snapshot chính xác

Keyspace có thể đổi giữa preview và execution. Cần kiểm tra prefix và giới hạn ở thời điểm thực thi.

### Sai lầm 17: Tạo một token/ticket rồi cho thao tác không giới hạn

Approval phải gắn môi trường, namespace, thời gian, phạm vi và ngân sách; không cấp “quyền dọn mọi thứ”.

### Sai lầm 18: Chỉ dùng UI authorization mà Redis user vẫn là admin

Một lỗi server-side hoặc dependency có thể vượt giao diện UI. ACL ở Redis là lớp phòng vệ bổ sung quan trọng.

### Sai lầm 19: Bật raw MONITOR để điều tra mọi sự cố

Có thể gây thêm tải và làm lộ credentials/payload. Sử dụng kênh chẩn đoán giới hạn.

### Sai lầm 20: Không có backup/restore drill

Khi xóa nhầm, không thể biết thực sự khôi phục được hay mất bao lâu.

### Sai lầm 21: Không kiểm tra nhiều node Redis Cluster

Quyền trên một node có thể khác node khác và lỗi chỉ xuất hiện với một số hash slots.

### Sai lầm 22: Retry NOPERM như lỗi mạng

Quyền không tự xuất hiện sau retry. Cần sửa code/config/ACL có kiểm soát.

### Sai lầm 23: Gộp Redis cache với lock, Stream, idempotency trong một thao tác purge

Một keyspace clear có thể phá trạng thái nghiệp vụ. Phân chia workload và bảo vệ bằng ACL/namespace.

### Sai lầm 24: Audit không ghi tác động thực tế

Một job bị lỗi giữa chừng vẫn có thể đã xóa nhiều key. Cần ghi nhận partial progress.

## 29. Thực hành có kiểm soát

### Bài tập A: Tạo user chỉ được đọc cache

Trên Redis test cô lập, tạo `app_product_reader` với `GET`, `TTL` và namespace product.

Kiểm tra:

```redis
ACL DRYRUN app_product_reader GET app:cache:product:v2:1
ACL DRYRUN app_product_reader DEL app:cache:product:v2:1
ACL DRYRUN app_product_reader FLUSHDB
```

Giải thích tại sao hai lệnh sau phải bị từ chối.

### Bài tập B: Phân biệt xóa một key và clear region

Tạo hai phương thức:

```java
invalidateOne(long productId)
clearProducts()
```

Bảo đảm `invalidateOne` chỉ tạo key cụ thể và không cần `SCAN`. Cho `clearProducts` vào maintenance service riêng với quyền và xác nhận phù hợp.

### Bài tập C: Thử RedisCacheManager với ACL

Đặt user read-only, gọi `@Cacheable`, sau đó thử `@CacheEvict(allEntries = true)`.

Quan sát command mà Spring Data Redis thực sự phát, phân loại NOPERM đúng và kiểm tra ứng dụng không tự mở quyền admin.

### Bài tập D: Rà soát Lua script

Với script compare-and-delete:

- Xác định keys và arguments.
- Liệt kê các lệnh nội bộ: `GET`, `DEL`.
- Xác định tài khoản nào được chạy.
- Chứng minh không thể xóa key ngoài namespace dự kiến khi credentials được giới hạn.
- Kiểm tra trường hợp owner token sai hoặc khóa đã hết hạn.

### Bài tập E: Dry-run xóa cache

Tạo 20 key trong namespace demo, đặt hard cap chỉ 5 key.

Chạy chế độ dry-run trước, xác minh job không được phép xóa quá cap, rồi kiểm tra audit về quyết định từ chối.

### Bài tập F: Kiểm tra sự cố credentials

Mô phỏng credential rotation ở staging:

1. Cấp user mới ít quyền.
2. Chuyển một instance sang user mới.
3. Kiểm tra Redis read/write thật.
4. Quan sát ACL denials.
5. Chuyển hết instances.
6. Thu hồi user cũ khi đã xác nhận không còn client phụ thuộc.

### Bài tập G: Lập runbook xóa nhầm

Một nhân viên vô tình gọi clear toàn product cache và database đang tăng tải. Viết runbook:

- Dừng job.
- Xác định scope và số key đã xóa.
- Giới hạn cache warming.
- Bảo vệ database bằng rate limit/bulkhead.
- Kiểm tra Redis/client latency.
- Ghi nhận sự cố.
- Đề xuất phòng ngừa lần sau.

## 30. Câu hỏi tự kiểm tra

**1. Tại sao một tài khoản chỉ phục vụ GET không nên có FLUSHALL?**

Vì `FLUSHALL` có thể xóa dữ liệu trên Redis server ngoài phạm vi chức năng đọc, làm tăng blast radius khi lỗi hoặc credentials bị lộ.

**2. Redis ACL bảo vệ những thành phần nào?**

User, command permissions, key patterns và channel permissions theo khả năng của phiên bản Redis.

**3. `+@all` nguy hiểm ở đâu?**

Nó cấp quyền rất rộng cho tài khoản, bao gồm những lệnh ứng dụng không cần và có thể làm tăng khả năng phá dữ liệu/cấu hình.

**4. `~app:cache:*` có thay thế quyền tenant của HTTP API không?**

Không. Redis ACL kiểm tra Redis user, không tự hiểu tenant hoặc quyền của người gọi HTTP.

**5. `SCAN` có tự bị lọc theo ACL key pattern không?**

Không được giả định như vậy. Cần kiểm soát quyền command và đánh giá hành vi thực tế.

**6. `FLUSHALL ASYNC` có tránh xóa dữ liệu không?**

Không. Nó vẫn xóa key; phần giải phóng bộ nhớ có thể được xử lý bất đồng bộ.

**7. Vì sao UNLINK không tự an toàn hơn DEL về phạm vi xóa?**

Cả hai đều làm key biến mất; UNLINK chủ yếu khác cách giải phóng bộ nhớ.

**8. Script EVAL có thể coi là một transaction rollback không?**

Không. Script nguyên tử đối với các lệnh khác nhưng thay đổi đã chạy trước lỗi runtime không mặc định được hoàn tác.

**9. Vì sao không nên nhận Lua code từ HTTP request?**

Vì như vậy người gọi có thể điều khiển code chạy trong Redis theo quyền của tài khoản ứng dụng.

**10. `EVALSHA` có chứng minh script được phép chạy theo nghiệp vụ không?**

Không. SHA là định danh script, không tự là authorization hay allowlist per-hash.

**11. Vì sao `@CacheEvict(allEntries = true)` cần bảo vệ?**

Vì nó có thể xóa cả cache region và gây tải Redis/database lớn, khác với invalidation một entry.

**12. Đổi RedisCacheWriter từ KEYS sang SCAN đã giải quyết mọi rủi ro chưa?**

Chưa. SCAN giảm một số nguy cơ quét nhưng không giới hạn số key cuối cùng bị xóa hoặc quyền ai được phép gọi.

**13. `ACL DRYRUN` dùng để làm gì?**

Kiểm tra quyết định ACL đối với lệnh mà không thực hiện tác dụng của lệnh đó.

**14. Redis trả NOPERM nên retry vô hạn không?**

Không. Đây thường là lỗi quyền/cấu hình, cần xử lý và thay đổi qua quy trình phù hợp.

**15. Nếu đã bật TLS và đặt password, có cần ACL ít quyền nữa không?**

Có. TLS và xác thực bảo vệ kết nối/danh tính; ACL hạn chế những lệnh mỗi danh tính được phép thực hiện.

**16. Nếu Redis Cluster có nhiều primary, chỉ kiểm tra ACL trên một node đủ không?**

Chưa. Cần xác nhận quyền trên các node mà client có thể kết nối, bao gồm sau failover và redirect.

**17. Vì sao không nên xóa namespace cache cùng với Redis Streams và fencing sequence?**

Vì Streams/fencing có ý nghĩa nghiệp vụ và có thể không tái tạo được như cache, thao tác xóa làm hỏng tiến độ xử lý hoặc tính đúng đắn.

**18. Audit của một purge job nên có gì?**

Danh tính actor, role, environment, namespace, ticket, approval, số key thực tế, trạng thái hoàn tất/abort và thời gian.

**19. Redis replica có phải backup an toàn nếu một admin thực hiện xóa nhầm không?**

Không. Thao tác xóa có thể được replication; cần backup/restore và kiểm thử khôi phục riêng.

**20. Nếu Redis user có quyền DEL trong namespace, ACL có tự ngăn job xóa 1 triệu key không?**

Không. ACL xác định lệnh/key được phép; ngân sách số lượng, thời gian, rate và approval phải được thực hiện ở tầng maintenance.

## 31. Ghi nhớ

- **Phân quyền Redis theo least privilege:** reader, writer, script executor, maintenance và admin không dùng chung credentials có toàn quyền.
- **Redis ACL là lớp bảo vệ phía server**, nhưng không thay thế xác thực/authorization, input validation và rate limits ở ứng dụng.
- **Hạn chế lệnh quản trị** như `FLUSHDB`, `FLUSHALL`, `CONFIG`, `ACL`, `SHUTDOWN`, `MONITOR`, `MODULE` và các thao tác topology.
- **Không mở `KEYS`/`SCAN` cho ứng dụng chỉ cần GET/SET**; ACL key pattern không được coi là bộ lọc duyệt keyspace hoàn chỉnh.
- **Script phải cố định, được review và truyền tham số qua KEYS/ARGV.** Không cung cấp API thực thi Lua tùy ý; ACL và script validation cần kiểm thử cùng nhau.
- **`@CacheEvict(allEntries = true)` là thao tác diện rộng**; `SCAN` batch strategy chỉ giảm một số chi phí, không thay đổi mức độ nguy hiểm của clear region.
- **`UNLINK` xóa key khỏi keyspace và giải phóng bộ nhớ bất đồng bộ**; nó không tạo khả năng undo.
- **Bulk deletion phải có scope, dry-run, phê duyệt, hard caps, audit, rate limit và abort conditions**; không dùng wildcard nhận từ client.
- **`NOPERM` không phải cache miss hay lỗi có thể retry vô hạn.** Giữ cause, phân loại đúng và điều chỉnh quyền qua quy trình.
- **Tách dữ liệu cache tái tạo được với dữ liệu quan trọng** như Streams, idempotency records, locks và fencing sequences; backup/restore vẫn cần thiết.
- **Đánh giá quyền trên toàn topology** nếu dùng Sentinel/Cluster, nhất là sau failover hoặc đổi node.

### Tài liệu tham khảo

- [Redis — Access Control Lists](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/).
- [Redis — ACL SETUSER](https://redis.io/docs/latest/commands/acl-setuser/).
- [Redis — ACL CAT](https://redis.io/docs/latest/commands/acl-cat/).
- [Redis — ACL DRYRUN](https://redis.io/docs/latest/commands/acl-dryrun/).
- [Redis — ACL LOG](https://redis.io/docs/latest/commands/acl-log/).
- [Redis — FLUSHDB](https://redis.io/docs/latest/commands/flushdb/).
- [Redis — FLUSHALL](https://redis.io/docs/latest/commands/flushall/).
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/).
- [Redis — UNLINK](https://redis.io/docs/latest/commands/unlink/).
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/).
- [Redis — Redis Programmability](https://redis.io/docs/latest/develop/programmability/).
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html).
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html).
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
