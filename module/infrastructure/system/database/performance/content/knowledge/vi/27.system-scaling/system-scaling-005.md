# Chống dồn tải khi bộ đệm hết hạn hoặc khởi động lại

Bộ đệm giúp giảm số lần truy cập database bằng cách giữ kết quả thường dùng trong RAM hoặc một hệ thống cache như Redis. Tuy nhiên, cache cũng có thể tạo ra một điểm rủi ro: khi một khóa phổ biến hết hạn, bị xóa hoặc mất sau khi cache khởi động lại, rất nhiều request cùng phát hiện cache miss và đồng loạt truy vấn database để tái tạo dữ liệu. Hiện tượng này thường được gọi là cache stampede hoặc thundering herd.

Một cache miss đơn lẻ thường không đáng lo. Vấn đề xuất hiện khi nhiều request cùng tải một dữ liệu nóng trong cùng khoảng thời gian, khiến số truy vấn DB tăng đột ngột. Database có thể hết connection, tăng lock wait, CPU và I/O, làm thời gian phản hồi tăng. Khi request timeout rồi retry, tải tiếp tục nhân lên. Một sự kiện cache nhỏ có thể biến thành sự cố dây chuyền.

Trong phạm vi DATABASE_PERFORMANCE, bài học này giải thích nguyên nhân dồn tải khi TTL hết hạn hoặc cache khởi động lại; cách phân tán thời điểm hết hạn, gộp request refresh, phục vụ dữ liệu cũ có kiểm soát, làm nóng cache theo đợt và bảo vệ database bằng giới hạn concurrency/backpressure. Mục tiêu là giữ độ trễ ổn định khi cache lạnh, cache lỗi hoặc nhiều khóa nóng cần làm mới cùng lúc.

## 1. Cache stampede là gì?

Giả sử một trang tổng hợp có khóa cache dashboard:tenant-42. Một nghìn request cùng đọc khóa này. Khi cache còn hiệu lực, phần lớn request nhận kết quả từ cache. Đúng thời điểm TTL hết hạn:

1. Request A đọc cache và nhận miss.
2. Request B cũng đọc cache và nhận miss.
3. Các request C đến Z tiếp tục nhận miss.
4. Mỗi request tự chạy cùng một truy vấn tổng hợp nặng xuống DB.
5. DB phải xử lý hàng trăm hoặc hàng nghìn truy vấn giống nhau để tạo một kết quả có thể dùng chung.
6. Trong lúc DB chậm, request tiếp tục xếp hàng hoặc timeout; retry làm tải tăng thêm.

Đây là cache stampede. Nếu nhiều khóa cùng hết hạn hoặc cache bị xóa toàn bộ, số lượng dữ liệu cần tái tạo có thể tạo ra một đợt tải lớn trên diện rộng.

### Phân biệt các tình huống

| Tình huống | Dấu hiệu | Tác động thường gặp |
|---|---|---|
| Cache miss thông thường | Một số ít khóa không có trong cache | DB nhận thêm một lượng truy vấn nhỏ |
| Cache stampede | Nhiều request đồng thời làm mới cùng một khóa | Truy vấn trùng lặp tập trung vào dữ liệu nóng |
| Cache avalanche | Nhiều khóa hết hạn gần cùng thời điểm | Tải tăng trên nhiều query/table cùng lúc |
| Cold start | Cache trống sau deploy, restart hoặc failover | Nhiều khóa cần nạp lại trong thời gian ngắn |
| Hot-key contention | Một khóa rất phổ biến được đọc/ghi liên tục | Một điểm cache hoặc DB bị tranh chấp |
| Cache outage | Cache không truy cập được | Request có thể dồn thẳng xuống DB nếu fallback không giới hạn |

Các hiện tượng có thể xuất hiện cùng nhau. Ví dụ, Redis restart làm cache lạnh, sau đó nhiều khóa hết hạn cùng lúc khi worker warm-up không được điều tiết.

## 2. Vì sao cache miss có thể làm database quá tải?

Cache thường làm giảm chi phí trung bình bằng cách tránh truy vấn lặp. Nhưng khi cache miss, chi phí tạo dữ liệu có thể cao hơn nhiều so với một lần đọc cache. Nếu mỗi request tự tái tạo cùng một giá trị, số truy vấn DB tỷ lệ với số request đồng thời.

Ví dụ:

- Một truy vấn tổng hợp mất 150 ms và tiêu thụ CPU/IO đáng kể.
- 800 request cùng yêu cầu một khóa vừa hết hạn.
- Nếu mỗi request chạy riêng truy vấn, DB nhận tối đa 800 lượt tính toán giống nhau.
- Nếu chỉ một request refresh và các request khác chờ hoặc nhận dữ liệu cũ, DB chỉ cần một lượt tính toán trong khoảng đó.

### Khuếch đại qua hàng đợi

Khi DB gần bão hòa, một truy vấn vốn mất 150 ms có thể tăng lên vài giây do chờ CPU, I/O hoặc connection. Request giữ worker và connection lâu hơn, làm số công việc đồng thời tăng. Khi timeout, client retry, tạo thêm request mới. Hệ thống rơi vào vòng lặp:

```text
Cache miss đồng loạt
        |
        v
Nhiều truy vấn giống nhau xuống DB
        |
        v
DB bão hòa CPU / I/O / connection
        |
        v
Query và request chậm, timeout
        |
        v
Retry và hàng đợi tăng
        |
        +------ quay lại tải DB
```

Điểm quan trọng là cache stampede không chỉ làm tăng số query. Nó còn kéo dài thời gian giữ connection và worker, làm các request không liên quan cũng chậm theo.

### Ước lượng bằng định luật Little

Định luật Little mô tả quan hệ trung bình:

```text
L = λ × W
```

Trong đó L là số công việc đang tồn tại trong phạm vi đo, λ là tốc độ yêu cầu và W là thời gian trung bình một yêu cầu chiếm hệ thống.

Nếu cache miss tạo 300 truy vấn/giây và mỗi truy vấn mất trung bình 0,4 giây, số truy vấn đang tồn tại trung bình có thể khoảng 120. Khi DB chậm lên 1,5 giây, con số ước tính tăng lên 450 nếu tốc độ đến vẫn giữ nguyên. Đây là mô hình trung bình, không dự báo burst hoặc p99, nhưng cho thấy vì sao truy vấn chậm làm số connection/worker đang bận tăng nhanh.

## 3. Các nguyên nhân thường gây dồn tải

### TTL giống nhau

Một job tạo cache cho hàng nghìn tenant cùng lúc và đặt TTL cố định 10 phút. Các khóa được ghi trong một khoảng ngắn nên cũng hết hạn gần nhau. Nếu traffic tăng đúng thời điểm đó, nhiều khóa đồng loạt miss.

### Deploy hoặc restart làm mất cache cục bộ

Cache L1 trong bộ nhớ của từng application instance mất khi process restart. Nếu rolling deployment khởi động nhiều instance gần như cùng lúc, tất cả đều lạnh. Mỗi instance có thể nạp cùng dữ liệu từ Redis hoặc DB.

### Redis restart, failover hoặc flush

Cache phân tán bị restart, failover, eviction hoặc flush làm mất nhiều khóa. Request tiếp tục đến trong lúc cache chưa được nạp lại, tạo cold-start load.

### Invalidation theo nhóm

Một thao tác quản trị xóa toàn bộ cache của một tenant, catalog hoặc bảng tham chiếu. Nếu các khóa có liên quan bị xóa cùng lúc, các request tiếp theo sẽ cùng tái tạo chúng.

### Một khóa có tần suất truy cập rất cao

Một trang chủ, bảng giá hoặc dashboard có thể nhận phần lớn traffic. Khi khóa đó hết hạn, chỉ một key cũng đủ gây stampede.

### Refresh thất bại lặp lại

Nếu DB đang lỗi, cache miss sẽ kích hoạt refresh. Refresh thất bại, cache vẫn trống, request tiếp theo lại thử. Hệ thống tạo một vòng lặp gọi DB hoặc dịch vụ phụ thuộc đang suy giảm.

## 4. Phân tán TTL bằng jitter

TTL jitter thêm một khoảng ngẫu nhiên vào thời hạn cache để các khóa không hết hạn cùng lúc.

Nếu hard freshness limit là 600 giây, có thể chọn TTL ngẫu nhiên trong khoảng 540 đến 600 giây:

```text
base_ttl = 600 giây
jitter   = số ngẫu nhiên trong [-60, 0]
ttl      = base_ttl + jitter
```

Ví dụ:

| Khóa | TTL được chọn |
|---|---:|
| tenant-A:summary | 548 giây |
| tenant-B:summary | 587 giây |
| tenant-C:summary | 583 giây |
| tenant-D:summary | 594 giây |

Các khóa được làm mới ở những thời điểm khác nhau, giảm khả năng cùng dồn tải vào một phút.

### Chọn biên jitter

Jitter có thể là:

- Cộng ngẫu nhiên một khoảng dương vào TTL.
- Trừ/cộng ngẫu nhiên quanh TTL cơ sở.
- Nhân TTL với một hệ số ngẫu nhiên trong một dải.

Nếu yêu cầu dữ liệu không được cũ quá 10 phút, không được cộng jitter làm TTL thành 12 phút. Hãy xác định freshness SLA trước rồi chọn phân bố chỉ nằm trong giới hạn cho phép. Với dữ liệu nhạy thời gian, có thể dùng jitter âm hoặc đặt hard expiry riêng.

### Ví dụ mã giả

```text
function cacheTtl(baseSeconds, jitterSeconds):
    offset = randomInteger(-jitterSeconds, 0)
    return max(1, baseSeconds + offset)

ttl = cacheTtl(600, 60)
cache.set(key, value, ttl)
```

Jitter nên được sinh cho từng lần ghi hoặc từng khóa, không dùng một giá trị ngẫu nhiên chung cho toàn bộ batch. Nếu mỗi process khởi động lại và dùng cùng seed hoặc cùng lịch ghi, phân tán TTL có thể không đạt như mong muốn.

### Jitter không giải quyết một hot key đơn lẻ

TTL jitter phân tán thời điểm hết hạn giữa nhiều khóa. Nó không ngăn hàng nghìn request cùng truy cập một khóa duy nhất trong thời gian ngắn sau khi khóa đó hết hạn. Với hot key, cần thêm request coalescing, lock/lease hoặc stale-while-revalidate.

## 5. Soft TTL và hard TTL

Một cách giảm stampede là tách thời điểm dữ liệu nên refresh khỏi thời điểm dữ liệu không còn được phép phục vụ.

- **Soft TTL:** thời điểm cache nên được làm mới. Sau mốc này, dữ liệu được xem là stale nhưng có thể vẫn phục vụ trong giới hạn.
- **Hard TTL:** thời điểm dữ liệu không còn được phép phục vụ; request phải lấy dữ liệu mới hoặc trả lỗi phù hợp.

Ví dụ:

| Mốc | Hành vi |
|---|---|
| 0–5 phút | Cache fresh, trả ngay |
| 5–8 phút | Cache stale, trả dữ liệu cũ và kích hoạt refresh |
| Sau 8 phút | Cache vượt hard TTL, cần refresh thành công hoặc fallback theo chính sách |

Khoảng stale chỉ phù hợp nếu nghiệp vụ cho phép dữ liệu cũ. Số dư tài khoản, quyền truy cập hoặc trạng thái giao dịch có thể cần consistency chặt hơn trang thống kê hoặc danh mục sản phẩm.

### Stale-while-revalidate

Khi cache vượt soft TTL:

1. Request đọc được giá trị stale.
2. Một request giành quyền refresh.
3. Request đó nạp dữ liệu mới từ DB và cập nhật cache.
4. Các request còn lại tiếp tục nhận giá trị stale trong giới hạn cho phép.
5. Khi refresh xong, cache chuyển sang giá trị mới.

Cơ chế này giảm số request phải chờ DB. Cần giới hạn tuổi stale tối đa và xác định hành vi nếu refresh thất bại.

### Stale-if-error

Nếu DB hoặc dịch vụ nguồn tạm thời lỗi, hệ thống có thể tiếp tục phục vụ giá trị stale đã xác thực trong một khoảng thời gian bổ sung. Đây là lựa chọn theo nghiệp vụ, không phải fallback mặc định cho mọi dữ liệu.

Không phục vụ stale vô thời hạn. Khi vượt hard TTL hoặc khi có sự kiện invalidation bắt buộc, cần từ chối, trả trạng thái degraded hoặc dùng nguồn dự phòng đáng tin cậy.

## 6. Gộp request refresh trong một process

Singleflight/request coalescing bảo đảm nhiều request cùng cần một khóa chỉ tạo một công việc refresh trong cùng một process. Các request khác dùng chung kết quả hoặc chờ future/promise của request đầu tiên.

Luồng:

```text
Request A ----\
Request B -----+--> Singleflight(key) --> Một lần query DB
Request C ----/                           |
                                          v
                                   Kết quả dùng chung
```

Mã giả:

```text
function getValue(key):
    value = cache.get(key)
    if value exists and isFresh(value):
        return value

    return singleflight.run(key, function():
        secondRead = cache.get(key)
        if secondRead exists and isFresh(secondRead):
            return secondRead

        fresh = loadFromDatabase(key)
        cache.set(key, fresh, ttlWithJitter())
        return fresh
    )
```

Lần đọc cache thứ hai rất quan trọng. Trong lúc request A chờ vào singleflight, một request khác có thể đã refresh xong. Nếu không kiểm tra lại, request B vẫn chạy query DB dù kết quả mới đã có.

### Phạm vi của singleflight

Singleflight trong bộ nhớ chỉ phối hợp request trong cùng process. Nếu có 20 application instance, mỗi instance vẫn có thể chạy một refresh cho cùng khóa, tạo tối đa 20 query. Đây có thể là cải thiện lớn so với hàng nghìn query, nhưng chưa phải một refresh duy nhất trên toàn cụm.

Có thể kết hợp:

- Singleflight trong từng process để gộp request nội bộ.
- Distributed lease/lock để phối hợp giữa các instance.
- Stale-while-revalidate để request không cần chờ refresh.
- Giới hạn concurrency refresh toàn service.

## 7. Distributed lock hoặc lease để phối hợp nhiều instance

Distributed lock cho phép một instance giành quyền refresh khóa cache. Các instance khác thấy lock đang được giữ thì chờ ngắn, đọc stale hoặc trả trạng thái phù hợp.

Với Redis, một dạng acquire cơ bản là:

```text
SET refresh-lock:<cache-key> <random-owner-token> NX PX 5000
```

- NX chỉ đặt nếu khóa chưa tồn tại.
- PX đặt thời hạn lease 5.000 ms.
- owner token là giá trị ngẫu nhiên duy nhất của lần acquire.

Nếu thành công, instance đó được quyền refresh trong thời hạn lease. Nếu không thành công, nó không được tự ý chạy cùng truy vấn nặng.

### Release phải kiểm tra owner token

Không xóa lock bằng DEL đơn giản. Giả sử lease của worker A hết hạn, worker B đã acquire lock mới. Nếu A chạy chậm rồi DEL, A có thể xóa lock của B.

Release phải so sánh token và chỉ xóa nếu token hiện tại vẫn thuộc owner:

```lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
```

Đoạn Lua minh họa thao tác compare-and-delete nguyên tử trên Redis. Cần dùng API/script phù hợp của client và xử lý trường hợp Redis lỗi hoặc timeout.

### Lease hết hạn khi refresh còn chạy

Nếu truy vấn DB mất 8 giây nhưng lease chỉ có 5 giây, worker A có thể vẫn đang chạy khi lease hết hạn. Worker B giành lease mới và cũng bắt đầu refresh. Hai truy vấn trùng lặp lại xuất hiện.

Các cách xử lý:

- Đặt lease lớn hơn thời gian refresh dự kiến nhưng vẫn có giới hạn.
- Gia hạn lease khi worker còn hoạt động, bằng thao tác kiểm tra owner token.
- Dùng timeout truy vấn DB để refresh không chạy vô hạn.
- Có fencing token/version để ngăn worker cũ ghi đè kết quả mới.
- Nếu lease mất, worker phải dừng hoặc không được công bố kết quả nếu không còn quyền.

### Fencing token chống worker cũ

Một lock có thời hạn không đủ để bảo đảm chỉ một worker còn chạy. Worker A có thể bị pause lâu, lease hết hạn, worker B refresh xong và ghi giá trị mới; sau đó A thức dậy và ghi dữ liệu cũ hơn.

Fencing token là số tăng đơn điệu cấp cho mỗi lần acquire. Hệ thống lưu token mới nhất và chỉ chấp nhận ghi nếu token của worker không cũ hơn token đã được chấp nhận. Cách triển khai phải có nơi kiểm tra token một cách nguyên tử; chỉ gắn token vào log mà không kiểm tra khi ghi không bảo vệ được dữ liệu.

Nếu nguồn dữ liệu có version/updated_at đơn điệu đáng tin cậy, có thể dùng điều kiện compare-and-set để từ chối kết quả cũ. Không dùng timestamp máy worker làm fencing token vì đồng hồ có thể lệch.

### Lock không thay thế giới hạn tải

Distributed lock giảm truy vấn trùng cho cùng một key. Nếu một nghìn key khác nhau cùng hết hạn, vẫn có thể có một nghìn refresh đồng thời. Cần thêm semaphore/concurrency limit toàn service hoặc theo nhóm query.

## 8. Mẫu stale-while-revalidate với lease

Một luồng thực tế có thể:

1. Đọc cache entry gồm value, soft_expiry, hard_expiry và source_version.
2. Nếu chưa đến soft expiry, trả value.
3. Nếu đã stale nhưng chưa hard expiry, trả value cũ ngay.
4. Thử acquire lease cho refresh key.
5. Nếu acquire thành công, refresh bất đồng bộ với timeout và concurrency limit.
6. Nếu acquire thất bại, không tạo truy vấn DB trùng; request tiếp tục nhận stale.
7. Khi refresh thành công, ghi value mới nếu version/fencing token hợp lệ.
8. Nếu refresh thất bại, giữ stale trong giới hạn hard expiry và ghi metric/error.

Mã giả:

```text
function readCached(key):
    entry = cache.get(key)

    if entry is null:
        return loadThroughWithCoalescing(key)

    if now() < entry.softExpiry:
        return entry.value

    if now() < entry.hardExpiry:
        triggerRefreshIfOwner(key, entry.sourceVersion)
        return entry.value

    return loadThroughWithCoalescingOrFallback(key)
```

triggerRefreshIfOwner phải trả về nhanh. Không để mọi request stale cùng chờ acquire lock hoặc chờ DB. Nếu không lấy được lease, chỉ một request khác đang refresh; các request còn lại dùng stale hoặc áp dụng chính sách hard-expiry.

## 9. Refresh-ahead và làm mới trước khi hết hạn

Refresh-ahead chủ động làm mới dữ liệu trước khi TTL kết thúc. Có thể lên lịch refresh khi entry còn một phần thời gian sống, ví dụ còn 10% TTL hoặc khi một khóa nóng đạt ngưỡng truy cập.

Ưu điểm:

- Giảm xác suất request người dùng gặp cache miss.
- Phân bố công việc refresh ra trước thời điểm hết hạn.
- Có thể ưu tiên key có tần suất đọc cao.

Rủi ro:

- Làm mới dữ liệu ít được dùng, gây truy vấn DB lãng phí.
- Nếu mọi entry cùng refresh trước TTL cố định, vẫn có thể tạo đợt tải.
- Refresh-ahead có thể cạnh tranh với workload trực tuyến.

Nên kết hợp jitter, giới hạn concurrency, ưu tiên theo độ nóng và chỉ refresh key có xác suất được dùng lại cao.

### Probabilistic early refresh

Với key nóng, hệ thống có thể chọn ngẫu nhiên một request để refresh sớm khi gần hết TTL. Xác suất tăng dần khi entry tiến gần expiry. Cách này tránh tất cả request chờ đúng một mốc thời gian.

Không cần mọi request đều quyết định refresh. Có thể dùng một hàm xác suất dựa trên thời gian còn lại, chi phí refresh và tần suất truy cập. Cần kiểm soát bằng singleflight/lease để nhiều request cùng chọn refresh không tạo nhiều job.

### Negative caching

Nếu truy vấn trả về “không tồn tại”, cache kết quả âm trong một TTL ngắn có thể tránh nhiều request lặp lại cùng truy vấn tìm kiếm. Ví dụ, mã sản phẩm không tồn tại bị client hỏi liên tục.

Negative cache phải có TTL phù hợp và được invalidation khi bản ghi mới được tạo. Không cache lỗi tạm thời của DB như thể đó là “không tồn tại”; phân biệt not found với timeout, permission error và service unavailable.

## 10. Làm nóng cache sau restart hoặc deploy

Cache lạnh sau restart là tình huống đặc biệt vì nhiều key có thể mất cùng lúc. Nếu warm-up quét toàn bộ dữ liệu ngay khi service khởi động, nó có thể tạo một đợt tải lớn lên DB trước khi nhận traffic người dùng.

### Ưu tiên theo độ nóng

Không cần nạp mọi key. Hãy ưu tiên:

- Key có request rate cao.
- Key có chi phí truy vấn lớn.
- Key được dùng trong đường đi quan trọng của request.
- Key có thể dự đoán từ lịch sử hoặc lịch công việc.

Key ít truy cập có thể được nạp theo yêu cầu khi có request đầu tiên.

### Warm-up theo đợt

Một quy trình an toàn:

1. Khởi động một số ít worker warm-up.
2. Lấy danh sách key ưu tiên có giới hạn.
3. Chia key thành batch nhỏ.
4. Giới hạn số query chạy đồng thời.
5. Đặt timeout và retry budget.
6. Nghỉ hoặc giảm tốc khi DB/replica có dấu hiệu bão hòa.
7. Mở traffic dần theo readiness và năng lực hệ thống.
8. Tiếp tục warm-up phần còn lại trong nền.

### Rolling deployment

Khi deploy nhiều instance, không nên để tất cả instance cùng chạy warm-up đầy đủ. Có thể:

- Dùng một worker warm-up chung cho toàn cụm.
- Chia key theo shard/partition để mỗi worker xử lý phần riêng.
- Dùng distributed lease cho từng nhóm key.
- Đặt giới hạn toàn cụm thay vì chỉ giới hạn từng process.
- Giữ cache L2 dùng chung trong khi L1 từng instance khởi động.

Nếu warm-up là điều kiện readiness, tránh chờ toàn bộ cache nạp xong mới nhận traffic. Chỉ chờ phần dữ liệu tối thiểu để phục vụ chức năng cốt lõi; phần còn lại nạp dần.

### Stagger startup

Có thể trì hoãn khởi động worker hoặc mở traffic của từng instance theo khoảng ngẫu nhiên. Điều này giảm việc tất cả process cùng kết nối DB, chạy migration/health query hoặc warm-up tại một thời điểm.

Stagger không thay thế rate limit. Nếu mọi instance vẫn chạy cùng một danh sách key sau vài giây, tải chỉ bị dời sang một thời điểm khác.

## 11. Bảo vệ database bằng concurrency limit

Cache stampede phải được xử lý ở nhiều lớp. Singleflight giảm truy vấn trùng theo key; semaphore giới hạn tổng số refresh; connection pool giới hạn backend connection; backpressure giới hạn request chờ.

Ví dụ:

```text
refreshConcurrency = 20
refreshQueueLimit  = 100
refreshTimeout     = 2 seconds

if refreshSemaphore.acquire(timeout = shortWait):
    try:
        refreshFromDatabase()
    finally:
        refreshSemaphore.release()
else:
    serveStaleOrReject()
```

Giới hạn 20 chỉ là ví dụ. Giá trị thật phải dựa trên năng lực DB, loại truy vấn, pool size và phần capacity dành cho workload trực tuyến.

### Giới hạn theo nhiều chiều

- Toàn service: giới hạn tổng refresh.
- Theo database: tránh một DB nhận quá nhiều công việc.
- Theo tenant: ngăn một tenant lớn chiếm hết capacity.
- Theo query class: giới hạn truy vấn tổng hợp nặng riêng.
- Theo key: chỉ một refresh đồng thời cho cùng khóa.

Giới hạn theo key không ngăn nhiều key khác nhau cùng refresh. Giới hạn toàn service không bảo đảm tenant công bằng. Kết hợp nhiều cấp giúp kiểm soát tốt hơn.

### Dùng connection pool có headroom

Không để refresh background chiếm hết connection pool. Có thể dùng pool riêng hoặc semaphore nhỏ cho tác vụ refresh, để request trực tuyến và tác vụ quản trị vẫn có connection.

Nếu pool có 100 connection, không nên cho phép 100 refresh nặng cùng chạy nếu DB còn phải xử lý request trực tuyến, replication, backup và job khác. Giới hạn refresh phải nằm dưới phần capacity được phân bổ cho nó.

### Bounded queue và load shedding

Queue không giới hạn chỉ chuyển overload thành latency và memory growth. Đặt giới hạn:

- Số refresh đang chạy.
- Số refresh đang chờ.
- Thời gian chờ tối đa.
- Tuổi tối đa của công việc trong queue.

Khi queue đầy, có thể bỏ refresh trùng, trả stale, từ chối request không thiết yếu hoặc trả lỗi retryable có Retry-After. Không tạo một request DB mới cho mọi phần tử bị loại khỏi queue.

## 12. Timeout, retry và circuit breaker

Refresh phải có timeout riêng. Nếu query DB treo lâu, lease có thể hết hạn trong khi worker vẫn chiếm connection. Timeout giúp giải phóng tài nguyên và ngăn một refresh giữ slot vô thời hạn.

### Retry có kiểm soát

Khi refresh thất bại:

- Chỉ retry lỗi tạm thời đã phân loại.
- Dùng exponential backoff và jitter.
- Giới hạn số lần retry và tổng thời gian.
- Không retry đồng thời ở mọi lớp (client, service, proxy, job) mà không có ngân sách chung.
- Ghi lại lần lỗi cuối và thời điểm thử tiếp theo.

Nếu mỗi request tự retry ba lần, 1.000 request miss có thể tạo 3.000 query. Coalescing và retry budget cần được áp dụng trước khi retry.

### Circuit breaker

Khi DB liên tục lỗi hoặc latency vượt ngưỡng, circuit breaker có thể ngừng khởi chạy refresh mới trong một khoảng thời gian. Request đọc có thể nhận stale nếu còn trong hard TTL; request ghi hoặc dữ liệu cần consistency chặt phải dùng chính sách riêng.

Circuit breaker cần:

- Trạng thái CLOSED, OPEN và HALF-OPEN.
- Số probe giới hạn khi thử phục hồi.
- Timeout cho probe.
- Cách chuyển trạng thái dựa trên lỗi/latency có ý nghĩa.
- Metric và log để biết refresh bị chặn do breaker.

Không để mọi request cùng lúc trở thành probe khi breaker chuyển HALF-OPEN. Chỉ một số ít probe được phép kiểm tra DB.

## 13. Cache nhiều tầng và restart

Kiến trúc phổ biến có L1 cache trong process và L2 cache phân tán:

```text
Request
  |
  v
L1: local memory cache
  |
  | miss
  v
L2: shared cache (Redis)
  |
  | miss
  v
Database
```

L1 giảm network hop nhưng mỗi instance có bản sao riêng. Khi một instance restart, L1 lạnh nhưng L2 vẫn có thể còn dữ liệu. Khi Redis restart, cả L2 lạnh và L1 có thể còn dữ liệu với tuổi khác nhau.

### Quy tắc TTL giữa các tầng

L1 không nên sống lâu hơn hard TTL của dữ liệu nguồn. Có thể đặt L1 TTL ngắn hơn L2 TTL và giữ metadata về source version/expiry. Nếu L2 invalidation xảy ra, L1 cần được cập nhật hoặc hết hạn đủ nhanh theo consistency requirement.

### Cache L1 không đồng bộ

Nếu mỗi instance có local cache, một instance refresh không tự động cập nhật các instance khác. Có thể dùng pub/sub invalidation, version key hoặc TTL ngắn. Pub/sub có thể mất message trong lúc subscriber disconnect, nên cần cơ chế đối chiếu version hoặc giới hạn tuổi L1.

### Redis restart và warm-up

Không để toàn bộ application instance cùng đọc DB khi L2 trống. Kết hợp:

- Stale L1 trong giới hạn cho phép.
- Warm-up có giới hạn toàn cụm.
- Singleflight/lease cho key nóng.
- TTL jitter.
- Traffic ramp-up.
- DB concurrency budget.

Nếu Redis hỗ trợ persistence/replication, nó có thể giảm lượng cache mất sau restart, nhưng persistence không thay thế chiến lược cold start. Cache có thể mất do eviction, deploy, failover hoặc flush dù persistence được bật.

## 14. Invalidation và race condition khi refresh

Cache invalidation có thể cạnh tranh với refresh:

1. Worker A đọc dữ liệu version 10 từ DB.
2. Một transaction cập nhật DB lên version 11 và invalidates cache.
3. Worker A ghi kết quả version 10 vào cache sau invalidation.
4. Cache lại chứa dữ liệu cũ dù DB đã có version 11.

Đây là stale write race. Lock refresh không tự giải quyết nếu invalidation không tham gia cùng cơ chế đồng bộ.

### Dùng version hoặc fencing

Một cách là gắn version tăng đơn điệu vào dữ liệu. Cache chỉ chấp nhận ghi nếu version mới hơn version hiện tại. Invalidation có thể ghi tombstone/version tối thiểu, khiến refresh cũ không thể ghi đè.

Ví dụ logic:

```text
if incoming.version >= cached.version:
    write cache
else:
    discard incoming value
```

So sánh và ghi phải nguyên tử. Nếu đọc version rồi ghi bằng hai lệnh riêng mà không có CAS/script/transaction, race vẫn có thể xảy ra.

### Transactional outbox

Nếu cần đồng bộ thay đổi DB với cache invalidation, có thể ghi event invalidation vào outbox trong cùng transaction với cập nhật dữ liệu. Worker đọc outbox rồi phát invalidation. Consumer cần idempotent và xử lý event lặp.

Outbox giúp không mất thông báo khi DB commit nhưng process chết trước khi publish. Tuy nhiên, invalidation có độ trễ; trong khoảng đó cache có thể stale. Cần xác định consistency window và cách xử lý request quan trọng.

### Invalidation theo version key

Thay vì xóa mọi cache key liên quan, có thể tăng version của namespace/tenant. Cache key chứa version hiện tại; dữ liệu cũ trở thành unreachable và hết hạn tự nhiên. Cách này giảm chi phí xóa hàng loạt nhưng cần quản lý version nhất quán và dọn dữ liệu cũ sau TTL.

## 15. Dữ liệu nào được phép stale?

Không phải dữ liệu nào cũng có thể phục vụ từ cache cũ:

| Loại dữ liệu | Chính sách thường phù hợp |
|---|---|
| Danh mục sản phẩm, nội dung tĩnh | Có thể stale trong khoảng ngắn nếu nghiệp vụ chấp nhận |
| Dashboard thống kê | Thường chấp nhận stale có giới hạn |
| Tỷ giá/giá thị trường | Cần freshness SLA rõ, stale có thể gây thiệt hại |
| Số dư, hạn mức, trạng thái thanh toán | Không dùng stale cho quyết định ghi/ủy quyền quan trọng |
| Quyền truy cập, trạng thái thu hồi token | Cần invalidation/freshness chặt, tránh stale cấp quyền |
| Kết quả tìm kiếm | Có thể stale theo SLA tìm kiếm |
| Negative cache cho not found | TTL ngắn và invalidation khi tạo bản ghi |

Một giá trị cache có thể được dùng để hiển thị nhưng không được dùng làm căn cứ ghi. Ví dụ, trang dashboard có thể hiển thị số dư gần nhất với nhãn thời điểm cập nhật, trong khi thao tác chuyển tiền luôn kiểm tra số dư trong transaction DB.

Hãy ghi metadata như generated_at, source_version và stale_until để tầng ứng dụng quyết định có được phục vụ hay phải từ chối.

## 16. Giảm chi phí refresh

Nếu một refresh vẫn tốn nhiều giây và I/O lớn, singleflight chỉ làm nó chạy một lần; nó không làm query nhanh hơn. Cần tối ưu công việc tạo cache:

- Chỉ đọc các cột cần thiết, tránh SELECT *.
- Dùng index hỗ trợ filter/join/order.
- Tổng hợp incremental thay vì quét lại toàn bộ lịch sử.
- Dùng materialized view hoặc bảng summary khi phù hợp.
- Chia refresh theo tenant/partition.
- Tính trước dữ liệu theo lịch thay vì chờ request đầu tiên.
- Dùng snapshot/version nhất quán cho nhiều phần dữ liệu.
- Giới hạn kích thước payload và serialization.

### Incremental refresh

Nếu dữ liệu tổng hợp được xây dựng từ event mới, có thể cập nhật summary theo delta:

```sql
INSERT INTO daily_sales (sales_date, tenant_id, total_amount, order_count)
VALUES (:sales_date, :tenant_id, :amount, 1)
ON CONFLICT (sales_date, tenant_id)
DO UPDATE SET
    total_amount = daily_sales.total_amount + EXCLUDED.total_amount,
    order_count = daily_sales.order_count + 1;
```

Đây là ví dụ khái niệm; cần xử lý event duplicate, cập nhật/hủy đơn, thứ tự sự kiện và idempotency để không cộng hai lần. Incremental refresh giảm quét nhưng chuyển một phần chi phí sang đường ghi và có thể tạo hot key trên summary row.

### Chia nhỏ cache key

Một key khổng lồ có thể yêu cầu truy vấn và serialization nặng. Có thể chia theo tenant, ngày, category hoặc partition để refresh từng phần. Tuy nhiên, quá nhiều key nhỏ làm tăng metadata và số lần truy cập cache. Chọn kích thước theo pattern đọc và cách tổng hợp.

## 17. Quan sát cache stampede

Không chỉ theo dõi cache hit ratio. Hit ratio cao vẫn có thể che giấu một vài hot key gây tải rất lớn khi miss.

### Chỉ số cache

- Hit, miss, stale hit và negative hit.
- Miss rate theo key namespace/tenant.
- Số key hết hạn theo từng khoảng thời gian.
- Số refresh đang chạy và đang chờ.
- Refresh success/failure và duration p50/p95/p99.
- Số request được gộp bởi singleflight.
- Lock/lease acquire success, contention, expiry và renewal failure.
- Số client bị pin/chờ nếu cache proxy hoặc client pool có giới hạn.

### Chỉ số database

- Query rate theo fingerprint.
- Số query refresh trùng nhau.
- Active session, connection pool utilization và acquire wait.
- CPU, I/O latency, buffer/cache hit.
- Lock wait, deadlock và transaction age.
- Replication lag và log generation.

### Chỉ số ứng dụng

- Request rate theo endpoint và key group.
- p50/p95/p99 latency.
- Timeout, retry và circuit breaker state.
- Worker/thread pool queue depth.
- Refresh concurrency và thời gian giữ connection.
- Tỷ lệ request trả stale hoặc degraded response.

### Correlation

Gắn cache key hash hoặc key namespace, refresh_id, trace_id, source query fingerprint và worker instance vào log/trace. Không log payload hoặc khóa chứa thông tin cá nhân nếu không cần. Dùng cùng một refresh_id cho các request được gộp giúp phân biệt một công việc và nhiều waiter.

## 18. Ví dụ tổng hợp: dashboard nhiều tenant

Một hệ thống có 2.000 tenant. Mỗi dashboard đọc một summary được cache 10 phút. Sau deploy, các instance mới khởi động và nhiều cache key đã mất. Nếu mọi tenant cùng truy cập vào đầu giờ, database nhận hàng nghìn truy vấn tổng hợp.

### Thiết kế trước khi sửa

- TTL cố định 600 giây.
- Mỗi request miss tự chạy query.
- Không có stale window.
- Warm-up nạp toàn bộ tenant đồng thời.
- Retry ngay khi query timeout.

### Thiết kế sau khi sửa

1. TTL được jitter trong giới hạn freshness.
2. Cache entry lưu soft expiry, hard expiry và source version.
3. Request stale được trả ngay trong stale window.
4. Singleflight gộp request trong mỗi process.
5. Distributed lease giới hạn một refresh owner theo key trên toàn cụm.
6. Refresh chạy qua semaphore toàn service với queue hữu hạn.
7. Query có statement timeout và retry budget.
8. Warm-up ưu tiên tenant nóng theo batch, có rate limit.
9. Refresh ghi cache chỉ khi version mới hơn.
10. Dashboard hiển thị thời điểm dữ liệu được tổng hợp; các thao tác ghi quan trọng đọc dữ liệu nguồn theo transaction.

### So sánh minh họa

Giả sử có 600 request cùng đọc một dashboard key trong một khoảng ngắn:

| Chỉ số | Trước | Sau |
|---|---:|---:|
| Request đọc cùng key | 600 | 600 |
| Query refresh DB | Có thể gần 600 | Thường 1 cho key đó |
| Request nhận stale | 0 | Có thể gần 599 trong stale window |
| Refresh concurrency toàn service | Không giới hạn rõ | Có semaphore/queue |
| Retry khi DB chậm | Nhiều lớp retry ngay | Retry budget và backoff |

Đây là ví dụ minh họa, không phải cam kết một refresh tuyệt đối trong mọi lỗi mạng hoặc lease expiry. Cần đo thực tế và kiểm tra fencing/version để ngăn refresh cũ ghi đè dữ liệu mới.

## 19. Kiểm thử cache expiry và cold start

Không chờ production tự gặp stampede. Tạo bài kiểm thử có kiểm soát:

1. **Single hot key expiry:** làm hết hạn một key có nhiều request đồng thời.
2. **Mass expiry:** cho một tập key lớn có TTL gần nhau rồi tạo tải.
3. **Cold cache:** xóa cache trong môi trường thử và tăng traffic dần.
4. **Rolling restart:** khởi động nhiều instance theo đợt và quan sát warm-up.
5. **Cache outage:** ngắt cache hoặc làm tăng latency cache để kiểm tra fallback.
6. **DB degraded:** làm query chậm hoặc giới hạn connection để kiểm tra backpressure.
7. **Lease expiry:** cho refresh chạy lâu hơn lease để kiểm tra duplicate refresh và fencing.
8. **Invalidation race:** cập nhật DB trong lúc refresh đang đọc/ghi cache.
9. **Worker crash:** dừng worker sau khi acquire lease hoặc sau khi query xong nhưng trước khi ghi cache.
10. **Retry storm:** tạo lỗi tạm thời và xác minh retry budget không nhân tải.

Theo dõi DB query rate, connection utilization, lock wait, p95/p99, số refresh trùng, stale response và thời gian cache phục hồi.

## 20. Quy trình xử lý sự cố cache stampede

1. **Xác định cache layer.** L1 local, L2 distributed hay cả hai đang miss?
2. **Tìm key/namespace nóng.** Miss tập trung ở một key, một tenant hay toàn bộ cache?
3. **Kiểm tra nguyên nhân.** TTL đồng bộ, deploy, restart, eviction, flush hay invalidation?
4. **Bảo vệ DB ngay.** Giới hạn refresh concurrency, queue và retry; trả stale nếu chính sách cho phép.
5. **Gộp refresh.** Bật singleflight hoặc lease cho hot key; tránh để từng request tự query.
6. **Kiểm tra DB.** Query fingerprint, active session, pool wait, CPU/I/O, lock và replication lag.
7. **Khôi phục cache theo đợt.** Warm-up key ưu tiên với rate limit và stagger.
8. **Kiểm tra dữ liệu.** Xác minh version, tuổi stale, invalidation và không có worker cũ ghi đè.
9. **Điều chỉnh TTL.** Thêm jitter/soft TTL và refresh-ahead nếu phù hợp.
10. **Đo sau xử lý.** So sánh query rate, refresh duration, p95/p99 và DB headroom.

Trong lúc DB đang bão hòa, không chạy một warm-up toàn bộ cache để “làm nóng nhanh”. Việc đó có thể kéo dài sự cố. Hãy phục hồi theo thứ tự ưu tiên và theo năng lực xử lý còn lại.

## 21. Những sai lầm thường gặp

- **Chỉ thêm TTL jitter:** không ngăn hàng nghìn request cùng miss một hot key.
- **Dùng singleflight trong process rồi cho rằng đã phối hợp toàn cụm:** mỗi instance vẫn có thể refresh một lần.
- **Distributed lock không có owner token:** worker cũ có thể xóa lock của worker mới.
- **Lease ngắn hơn thời gian query nhưng không có fencing:** refresh cũ có thể ghi đè kết quả mới.
- **Phục vụ stale vô thời hạn:** dữ liệu có thể vượt freshness SLA hoặc vi phạm nghiệp vụ.
- **Refresh-ahead mọi key:** tạo tải DB cho dữ liệu không được dùng.
- **Warm-up toàn bộ dữ liệu cùng lúc:** tạo cold-start stampede do chính job warm-up.
- **Tăng connection pool để xử lý miss:** có thể làm DB chịu thêm concurrency khi đã bão hòa.
- **Queue không giới hạn:** overload chuyển thành latency và memory growth.
- **Retry ngay lập tức ở nhiều tầng:** nhân số query và tạo retry storm.
- **Fallback cache miss thẳng xuống DB khi cache outage:** biến cache outage thành database outage.
- **Không xử lý invalidation race:** refresh đọc dữ liệu cũ có thể ghi sau khi cache đã bị xóa.
- **Dùng stale cho quyết định ghi quan trọng:** có thể gây sai số dư, quyền hoặc trạng thái giao dịch.
- **Chỉ nhìn hit ratio:** bỏ qua hot key, refresh trùng và p99.

## 22. Checklist thiết kế và vận hành

| Câu hỏi | Điều cần xác nhận |
|---|---|
| Cache key nào có traffic nóng? | Có metric theo namespace/key group |
| TTL có đồng bộ không? | Có jitter trong freshness SLA |
| Có soft TTL và hard TTL không? | Tuổi stale tối đa được xác định |
| Có thể phục vụ stale không? | Đã phân loại dữ liệu theo consistency |
| Nhiều request cùng key có được gộp không? | Singleflight có kiểm tra cache lần hai |
| Nhiều instance có phối hợp refresh không? | Có lease/lock và xử lý owner token |
| Lease có thể hết hạn khi query còn chạy không? | Có timeout, renew và fencing/version |
| Warm-up có giới hạn không? | Có ưu tiên, batch, concurrency và rate limit |
| Cache outage có làm DB nhận toàn bộ traffic không? | Có backpressure, load shedding và fallback |
| Retry có ngân sách không? | Có backoff, jitter và giới hạn tổng |
| Refresh có chiếm hết connection pool không? | Có pool/semaphore dành riêng và headroom |
| Invalidation có race với refresh không? | Có version/CAS hoặc outbox |
| DB có đủ sức chịu cold start không? | Đã kiểm thử mass expiry và restart |
| Theo dõi được hiệu quả không? | Có refresh duration, duplicate query, pool wait, p95/p99 |

## 23. Nguyên tắc ra quyết định

Cache stampede xảy ra khi nhiều request cùng tái tạo dữ liệu sau một cache miss, đặc biệt khi TTL đồng bộ, cache bị restart hoặc một hot key hết hạn. Jitter phân tán thời điểm hết hạn giữa nhiều khóa; singleflight gộp request trong một process; distributed lease phối hợp nhiều instance; stale-while-revalidate giảm số request phải chờ; warm-up theo đợt và concurrency limit bảo vệ database khi cache lạnh.

Không có một kỹ thuật đơn lẻ giải quyết mọi trường hợp. Hãy kết hợp TTL phù hợp freshness SLA, stale window có giới hạn, refresh coalescing, fencing/version cho kết quả cũ, queue hữu hạn, timeout, retry budget và backpressure. Tối ưu truy vấn refresh để mỗi lần nạp dữ liệu có chi phí hợp lý.

Sau cùng, kiểm thử cả hot-key expiry, mass expiry, rolling restart, cache outage và DB degraded. Đo query rate, refresh concurrency, connection pool, lock wait, replication lag và p95/p99 để xác nhận hệ thống phục hồi có kiểm soát mà không chuyển một cache miss thành sự cố database.
