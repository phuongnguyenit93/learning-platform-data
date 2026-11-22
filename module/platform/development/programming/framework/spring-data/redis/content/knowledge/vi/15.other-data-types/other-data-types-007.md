# Chọn kiểu dữ liệu theo độ chính xác, bộ nhớ và mẫu truy cập trong Spring Data Redis

Redis không chỉ là nơi lưu một chuỗi theo key. Redis cung cấp nhiều **kiểu dữ liệu với đặc tính khác nhau**: String, Hash, List, Set, Sorted Set, Bitmap, HyperLogLog, Geospatial index, Stream, cùng những cấu trúc xác suất hoặc kiểu dữ liệu nâng cao tùy bản phân phối và module được cài đặt. Chọn đúng cấu trúc có thể biến một truy vấn phức tạp ở Java thành một lệnh Redis hiệu quả; chọn sai có thể làm tăng RAM, khó đảm bảo tính đúng đắn hoặc khiến ứng dụng không lấy được dữ liệu theo cách nghiệp vụ cần.

Ví dụ, câu hỏi “Có bao nhiêu người dùng khác nhau truy cập trang hôm nay?” có ít nhất ba cách tiếp cận:

- **Set:** lưu từng user ID duy nhất, đếm **chính xác** và truy xuất lại từng ID, nhưng tốn RAM theo số lượng user.
- **Bitmap:** đánh dấu các ID nguyên ở từng vị trí bit, đếm **chính xác** với chi phí thấp nếu ID thuộc miền số nguyên đủ đặc và được ánh xạ ổn định.
- **HyperLogLog:** ước lượng số user duy nhất với dung lượng nhỏ, thích hợp dashboard quy mô lớn nhưng **không đếm chính xác tuyệt đối** và không trả lại danh sách user.

Không có một cấu trúc “nhanh nhất” trong mọi tình huống. Bài này hướng dẫn một phương pháp lựa chọn dựa trên **ba trục chính: độ chính xác, chi phí bộ nhớ và mẫu truy cập**, đồng thời tính đến dữ liệu bị cập nhật đồng thời, TTL, tính bền vững và mức hỗ trợ của Spring Data Redis.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt các mức **chính xác tuyệt đối**, **xấp xỉ có sai số**, **chính xác trong một miền ID**, và **độ chính xác số học của score**.
2. Chọn cấu trúc từ câu hỏi truy vấn: đọc theo key, kiểm tra membership, đếm unique, top N, range theo thời gian, phát sự kiện, vị trí địa lý hay lọc “có thể tồn tại”.
3. Giải thích vì sao Set, Bitmap và HyperLogLog không thay thế nhau dù đều có thể phục vụ bài toán đếm.
4. So sánh chi phí bộ nhớ của nhiều key String, một Hash nhiều field, Set chứa ID và Bitmap theo ID.
5. Biết khi nào Sorted Set với score kiểu double có rủi ro về độ chính xác số nguyên; phân biệt với String counter nguyên 64-bit.
6. Hiểu Bloom filter có **false positive** và không thể dùng như một bảng kiểm chứng chắc chắn “đã tồn tại”.
7. Sử dụng những API Spring Data Redis thích hợp như `StringRedisTemplate`, `HashOperations`, `SetOperations`, `ZSetOperations`, `GeoOperations` và `HyperLogLogOperations`.
8. Tạo một ma trận quyết định cho dữ liệu nghiệp vụ thực tế, rồi kiểm tra bằng số liệu thay vì đoán theo tên cấu trúc.

**Ngữ cảnh:** Java 17+, Spring Boot, Spring Data Redis và Redis server. Ví dụ cấu hình hướng đến Spring Boot 3.x; API và khả năng của Redis/module cần đối chiếu theo phiên bản đang triển khai. Bài này là hướng dẫn lựa chọn cấu trúc dữ liệu, không phải một benchmark có số đo thực tế.

## 2. Ba câu hỏi phải trả lời trước khi chọn kiểu dữ liệu

### 2.1. Cần chính xác đến mức nào?

“Chính xác” có nhiều ý nghĩa:

| Khía cạnh | Ví dụ | Yêu cầu |
| --- | --- | --- |
| **Chính xác số lượng** | Có đúng 150.000 user duy nhất không? | Set/Bitmap có thể đếm chính xác; HyperLogLog chỉ ước lượng |
| **Chính xác membership** | User này có thuộc nhóm bị chặn không? | Không chấp nhận Bloom false positive làm kết luận cuối |
| **Chính xác số học** | Số lượng tồn kho còn đúng bao nhiêu? | Redis String integer/logic nghiệp vụ phù hợp, tránh double nếu vượt miền chính xác |
| **Chính xác thứ tự** | Hai đơn có cùng điểm, đơn nào ưu tiên trước? | Cần quy tắc tie-break tường minh |
| **Chính xác vị trí** | Khoảng cách đến cửa hàng là bao nhiêu mét? | GEO phù hợp gợi ý/tra cứu gần đúng, không thay thế đo đạc địa chính |
| **Chính xác lịch sử** | Có thể đọc lại mọi sự kiện đã xử lý không? | Cần retention/ack/durability rõ ràng; một counter hoặc List có trim không đủ |

Nếu một yêu cầu nói “phải đúng tuyệt đối”, cần hỏi **đúng cái gì**. Ví dụ `SCARD` đếm chính xác các member **đang có trong Set**, nhưng nếu một sự kiện không được ghi do lỗi mạng hoặc key bị eviction, kết quả tổng thể vẫn có thể sai so với thực tế nghiệp vụ.

### 2.2. Cần đọc hoặc cập nhật theo mẫu nào?

Hãy diễn đạt thành những câu lệnh mà hệ thống cần thực hiện nhiều nhất:

- “Lấy object theo ID” → point lookup.
- “Tăng số lần xem” → atomic increment.
- “Đổi một field của hồ sơ” → field update.
- “Có user này trong nhóm không?” → exact membership.
- “Có bao nhiêu user unique?” → exact hoặc approximate cardinality.
- “10 người đứng đầu” → ordered top N.
- “Các job có deadline trước 14:00” → score/time range.
- “Lấy sự kiện tiếp theo và xác nhận đã xử lý” → stream/queue consumption.
- “Các cửa hàng trong bán kính 3 km” → geospatial query.
- “ID này chắc chắn chưa tồn tại hay có thể tồn tại?” → probabilistic filter.

Một cấu trúc đọc tốt theo score chưa chắc hỗ trợ hiệu quả truy vấn theo text hoặc lọc nhiều field. Redis không tự tạo SQL query planner cho mọi kiểu dữ liệu.

### 2.3. Dữ liệu có hình dạng và vòng đời ra sao?

Các yếu tố cần biết:

1. Số lượng key dự kiến.
2. Số phần tử trong mỗi key.
3. Kích thước trung bình và tối đa của mỗi value/member.
4. ID nguyên có nằm trong khoảng nhỏ, liên tục, hay rất thưa?
5. Tỷ lệ đọc/ghi, số lần cập nhật mỗi giây, mức đồng thời.
6. Có cần truy xuất lại member hay chỉ cần số đếm?
7. TTL, retention, chính sách eviction và yêu cầu lưu bền vững.
8. Có nhiều client/ngôn ngữ cùng truy cập không, serializer có thống nhất không?

Chi phí RAM không chỉ là bytes nội dung. Redis còn có overhead của key, object, cấu trúc dữ liệu bên trong, allocator, expiration metadata, replication/AOF và đôi khi cả dữ liệu tạm trong lúc xử lý.

## 3. Bản đồ các kiểu dữ liệu nên cân nhắc

| Kiểu dữ liệu | Mức chính xác | Mẫu truy cập nổi bật | Chi phí/giới hạn đáng chú ý | Hỗ trợ trong Spring Data Redis |
| --- | --- | --- | --- | --- |
| **String** | Chính xác với bytes; lệnh integer hỗ trợ số nguyên có giới hạn | GET/SET, INCR/DECR, TTL, JSON blob | Cập nhật một phần JSON blob thường phải ghi lại cả value | `opsForValue()` |
| **Hash** | Chính xác theo field | HGET/HSET/HINCRBY, nhiều thuộc tính của một entity | Field và value vẫn tốn RAM; không phải document query tổng quát | `opsForHash()` |
| **List** | Chính xác theo vị trí/thứ tự lưu | LPUSH/RPUSH/LPOP/RPOP/LRANGE | Range offset sâu, List lớn hoặc trim sai có thể tốn kém/mất dữ liệu | `opsForList()` |
| **Set** | Membership/cardinality chính xác của dữ liệu đã lưu | SADD/SISMEMBER/SCARD, giao/hợp/hiệu | Lưu từng member; RAM tăng theo số lượng và chiều dài ID | `opsForSet()` |
| **Sorted Set (ZSET)** | Member duy nhất; score là double | ZADD, ZRANK, ZRANGE, range theo score, top N | Tốn metadata thứ tự; số nguyên score lớn có thể mất chính xác | `opsForZSet()` |
| **Bitmap** (trên String) | Bit/membership và bit count chính xác | SETBIT/GETBIT/BITCOUNT/BITOP | Kích thước theo **offset bit lớn nhất**, không theo số bit bật | `opsForValue().setBit/getBit()` và bit commands |
| **HyperLogLog** | **Ước lượng** số phần tử phân biệt | PFADD/PFCOUNT/PFMERGE | Sai số thống kê; không liệt kê phần tử hoặc kiểm tra membership | `opsForHyperLogLog()` |
| **Geospatial** | Chỉ mục tọa độ/khoảng cách có sai số thực tế | GEOADD/GEOSEARCH/GEODIST | Tối ưu truy vấn vị trí; không phải GIS độ chính xác pháp lý | `opsForGeo()` |
| **Stream** | Lưu entry/ID theo log; xử lý phụ thuộc retention và ack | XADD/XREAD/XREADGROUP/XACK | Pending entries, trim, consumer lag cần quản trị | `opsForStream()` |
| **Bloom filter** (phụ thuộc module/distribution) | Có **false positive**; không false negative trong điều kiện chuẩn | “Chắc chắn không có / có thể có” | Không liệt kê đầy đủ; cần dự tính capacity/FPR; không luôn hỗ trợ delete | Thường qua module command/client tương ứng |
| **RedisJSON / TimeSeries / Search** (phụ thuộc bản Redis/module) | Theo mô hình của từng tính năng | Cập nhật JSON path, time-series range, tìm kiếm/index | Yêu cầu hỗ trợ server và client thích hợp | Không suy luận chúng là `RedisTemplate` core operation mặc định |

**Lưu ý về “kiểu dữ liệu khác”:** Bitmap và HyperLogLog sử dụng biểu diễn được Redis xử lý trên nền String hoặc một cấu trúc nội bộ chuyên biệt; không nên kỳ vọng tất cả xuất hiện như một tên `TYPE` riêng. Ví dụ một key Bitmap thường báo `TYPE string`. RedisJSON, Bloom hoặc TimeSeries cần kiểm tra khả năng của bản phân phối Redis; lệnh module có thể không tồn tại trên Redis server chỉ hỗ trợ các lệnh lõi.

## 4. Redis String: lựa chọn đơn giản khi truy cập theo một key

String là lựa chọn mạnh khi ứng dụng cần **một giá trị theo một key**, hoặc thao tác số nguyên nguyên tử.

~~~redis
SET shop:product:42:status "active" EX 600
GET shop:product:42:status

SET shop:article:42:views 0
INCR shop:article:42:views
INCRBY shop:article:42:views 5
GET shop:article:42:views
~~~

**Điểm mạnh:**

- GET/SET dễ sử dụng và có độ phức tạp phù hợp với point lookup.
- TTL trên từng key giúp lưu dữ liệu tạm.
- Lệnh `INCR`/`INCRBY` cho số nguyên chạy nguyên tử ở Redis, tránh mô hình GET–cộng ở Java–SET.
- Có thể lưu chuỗi UTF-8, JSON hoặc binary bytes theo serializer đã chọn.

**Giới hạn:**

- Nếu value là một JSON object, Redis String không tự hiểu từng field. Muốn thay một trường nhỏ có thể phải đọc–deserialize–sửa–serialize–ghi lại toàn object.
- GET/SET với payload rất lớn làm tăng network, CPU và memory.
- Một key per attribute tạo nhiều key nhỏ, tăng overhead tổng thể so với gom thuộc tính bằng Hash khi phù hợp.

### 4.1. Độ chính xác của bộ đếm String

Các lệnh tăng/giảm integer của Redis làm việc với **signed 64-bit integer**. Đó là lựa chọn phù hợp nếu miền số nguyên và quy tắc nghiệp vụ nằm trong khoảng:

\[
-2^{63} \leq n \leq 2^{63}-1
\]

Nhưng **nguyên tử của một lệnh không đảm bảo tổng nghiệp vụ exactly-once**: nếu client timeout sau khi Redis đã tăng nhưng chưa nhận phản hồi, retry có thể tăng lần nữa. Với số liệu tài chính hoặc tồn kho cần đối soát, không nên coi một counter Redis là sổ cái duy nhất.

### 4.2. Khi nào nên dùng Hash thay String JSON?

Nếu entity có nhiều field nhỏ thường được cập nhật độc lập:

~~~redis
HSET shop:cart:42 productCount 3 status active lastUpdated 1730000000
HGET shop:cart:42 status
HINCRBY shop:cart:42 productCount 1
~~~

Hash cho phép cập nhật field mà không ghi lại toàn bộ JSON String. Tuy nhiên, Redis Hash không cung cấp truy vấn tổng quát kiểu “tìm mọi giỏ hàng có status = active” nếu bạn không xây thêm chỉ mục; việc chọn kiểu lưu phải bám theo mẫu truy cập thực tế.

## 5. Hash: gom các field nhỏ, giảm overhead của nhiều key

Giả sử có một triệu user, mỗi user có vài field ngắn như `displayName`, `level`, `lastSeen`.

Phương án nhiều key:

~~~text
user:42:displayName -> "Lan"
user:42:level       -> "4"
user:42:lastSeen    -> "..."
~~~

Phương án Hash:

~~~text
user:42 -> Hash {
  displayName: "Lan",
  level: "4",
  lastSeen: "..."
}
~~~

Redis Hash thường tiết kiệm overhead **khi gom những field nhỏ trong một key**, nhất là khi các ngưỡng encoding tối ưu được đáp ứng. Với Redis hiện đại, cách mã hóa nội bộ cho Hash nhỏ có thể sử dụng cấu trúc compact như listpack; khi Hash vượt ngưỡng số field hoặc kích thước value, Redis có thể chuyển encoding, khiến mức sử dụng RAM thay đổi đáng kể.

**Không có bảo đảm “Hash luôn ít RAM hơn”.** Với một object rất lớn, hàng chục nghìn field, hoặc cần nhiều TTL khác nhau cho từng thuộc tính, kết quả có thể khác. Phải đo bằng dữ liệu mẫu.

### 5.1. Mẫu truy cập phù hợp

~~~redis
HSET shop:product:42 name "Bàn phím" stock 20 active 1
HGET shop:product:42 stock
HINCRBY shop:product:42 stock -1
HMGET shop:product:42 name active
HGETALL shop:product:42
~~~

Nếu chỉ cần field `stock`, dùng `HGET`/`HINCRBY` thay vì lấy cả entity. Nếu chỉ đọc vài field, `HMGET` có thể giảm lượng dữ liệu so với `HGETALL`.

### 5.2. Hạn chế của Hash

- Key-level TTL không có nghĩa mọi phiên bản Redis đều có semantics field-level TTL giống nhau; nếu muốn thời hạn riêng cho từng field, phải kiểm tra các lệnh/tính năng theo **phiên bản Redis đang triển khai** và hỗ trợ client.
- `HGETALL` trên Hash lớn có thể trả rất nhiều dữ liệu, không thích hợp gọi trong mỗi HTTP request.
- Serializer cho key, hash-key và hash-value phải được chọn nhất quán.
- Nếu cần query/sort toàn bộ entity theo nhiều điều kiện, Hash thuần không thay thế index/search/database.

## 6. Set: membership và distinct count chính xác

Set phù hợp khi **mỗi phần tử chỉ xuất hiện một lần** và cần kiểm tra nó có nằm trong nhóm hay không.

~~~redis
SADD campaign:42:participants user:1 user:2 user:3
SADD campaign:42:participants user:2
SCARD campaign:42:participants
SISMEMBER campaign:42:participants user:2
SISMEMBER campaign:42:participants user:99
~~~

Kết quả:

- `user:2` vẫn chỉ có **một** bản ghi trong Set.
- `SCARD` trả chính xác **số member hiện có**.
- `SISMEMBER` trả có/không theo member.
- Có thể liệt kê member bằng `SSCAN`, hoặc `SMEMBERS` nếu tập nhỏ; tránh tải tập rất lớn trong một lệnh.

### 6.1. Vì sao Set tốn RAM hơn số đếm?

Set phải giữ **từng member** để hỗ trợ kiểm tra membership, xóa member, hợp/giao/hiệu tập hợp. Nếu lưu hàng triệu ID dạng String, tổng RAM tăng theo số lượng và kích thước ID, không chỉ theo con số distinct.

Khi yêu cầu chỉ là “số lượng unique hôm nay”, không cần lấy danh sách ID hoặc trả lời user cụ thể có tồn tại hay không, HyperLogLog có thể phù hợp hơn.

### 6.2. Set khác Bitmap

Set lưu member như `"user:abc"`, `"user:xyz"` hoặc ID bất kỳ. Bitmap coi mỗi **vị trí bit** như một mã số nguyên không âm. Nếu user ID là UUID hoặc số lớn thưa, Bitmap không còn trực tiếp thuận tiện; cần ánh xạ ID sang index và quản lý ánh xạ đó, đôi khi tổng chi phí còn lớn hơn Set.

## 7. Bitmap: exact membership với miền ID nguyên phù hợp

Bitmap trong Redis là kỹ thuật sử dụng các **bit của một Redis String**. Mỗi offset bit có giá trị 0 hoặc 1.

~~~redis
SETBIT attendance:2026-11-12 10 1
SETBIT attendance:2026-11-12 11 1
SETBIT attendance:2026-11-12 15 1
GETBIT attendance:2026-11-12 10
GETBIT attendance:2026-11-12 12
BITCOUNT attendance:2026-11-12
~~~

Ở đây ba offset 10, 11 và 15 được bật. `BITCOUNT` trả **3**, tức số bit bằng 1, không phải số lần SETBIT đã được gọi. Nếu offset 10 được bật lần nữa, kết quả vẫn là 3.

### 7.1. Khi Bitmap rất tiết kiệm RAM

Nếu ID được ánh xạ liên tục từ 0 đến 99.999.999 và chỉ cần một bit/ID:

\[
\frac{100\,000\,000\ \text{bit}}{8}=12\,500\,000\ \text{byte}
\]

Tức khoảng **12,5 MB dạng thập phân** cho phần bit thô, chưa kể overhead của Redis, allocator hoặc các cấu trúc xung quanh. Đây là khả năng rất hấp dẫn so với lưu 100 triệu member String trong Set nếu bài toán chỉ cần membership nhị phân.

### 7.2. Vì sao ID thưa là vấn đề lớn?

Giả sử bạn chỉ có user ID:

~~~text
7
15
100000000
~~~

Một bitmap dùng trực tiếp ID làm offset phải có đủ không gian đến **offset cao nhất**, dù chỉ bật ba bit. Nó không cấp phát chỉ ba bit vì chỉ có ba user. Khi ID là số lớn rất thưa, Set có thể tiết kiệm hơn.

Nếu ánh xạ UUID → chỉ số nhỏ liên tục, bạn cần lưu và đồng bộ bảng ánh xạ. Phần RAM và độ phức tạp của mapping cũng phải được tính vào bài toán.

### 7.3. Mẫu truy cập phù hợp

- Điểm danh theo ngày với user ID số nguyên thuộc miền đã biết.
- Đánh dấu một tính năng đã bật/tắt cho từng ID.
- Tính số member thuộc hai nhóm bằng toán tử bit (`BITOP`) khi các bitmap dùng **cùng ánh xạ offset**.
- Theo dõi hoạt động trong nhiều cửa sổ, một key mỗi ngày/tuần.

### 7.4. Giới hạn

- Một bit không lưu được số lần hoạt động; nó chỉ biểu thị có/không.
- Không có member String tùy ý nếu không ánh xạ.
- Không có rank, score, metadata của từng user.
- Không tự có TTL theo từng bit; TTL gắn vào toàn key.
- Phải giới hạn offset hợp lệ; input xấu có offset rất lớn có thể gây mở rộng String và tốn bộ nhớ bất ngờ.

Bitmap **đếm chính xác số bit bật** của những ID được biểu diễn đúng. Nó không tự bảo đảm sự kiện thực tế đều được ghi thành công.

## 8. HyperLogLog: đếm distinct gần đúng với chi phí bộ nhớ nhỏ

**HyperLogLog (HLL)** là cấu trúc xác suất dùng để **ước lượng số lượng phần tử phân biệt**. Mỗi phần tử được băm thành thông tin thống kê; Redis không giữ nguyên toàn bộ member để có thể liệt kê chúng về sau.

~~~redis
PFADD analytics:visitors:today user:1 user:2 user:3
PFADD analytics:visitors:today user:2
PFCOUNT analytics:visitors:today
~~~

`PFCOUNT` trả **ước lượng số user duy nhất**, không phải số lượt truy cập. Thêm `user:2` nhiều lần không làm mục tiêu đếm distinct trở thành đếm page views, dù thuật toán có sai số.

### 8.1. Độ chính xác và bộ nhớ

Redis HyperLogLog có sai số chuẩn khoảng **0,81%** và có thể dùng khoảng **12 KB** khi ở dạng dense; với số lượng nhỏ, biểu diễn sparse có thể chiếm ít hơn. Đây là đặc điểm thuật toán/cấu trúc, không phải bảo đảm rằng mọi kết quả luôn sai không quá 0,81%.

Ví dụ nếu số người dùng thực là 1.000.000, một phép đo có thể trả con số quanh một triệu, nhưng **không nên lấy 0,81% làm giới hạn sai số tuyệt đối cho từng lần đo**. Khi cần đếm để thu phí theo từng user chính xác tuyệt đối hoặc đối soát pháp lý, HLL không phải nguồn quyết định cuối cùng.

### 8.2. HLL làm được và không làm được gì?

| Nhu cầu | HLL đáp ứng? | Lý do |
| --- | --- | --- |
| Ước lượng unique user/ngày | **Có** | Đây là mục tiêu chính |
| Ước lượng unique của hai ngày gộp | **Có**, qua merge/count hợp phù hợp | Gộp thông tin thống kê |
| Biết user A có thuộc nhóm không | **Không** | Không giữ danh sách member để kiểm tra |
| Liệt kê 100 user đầu tiên | **Không** | Không lưu danh sách user |
| Xóa riêng một user | **Không** theo mô hình HLL thông thường | Không có member storage để remove |
| Đếm chính xác để tính tiền | **Không** | Có sai số xác suất |

### 8.3. Thiết kế key theo cửa sổ

~~~text
analytics:unique:2026-11-12
analytics:unique:2026-11-13
analytics:unique:2026-11-14
~~~

Mỗi key là một HLL của một ngày. Có thể ước lượng unique của nhiều ngày bằng `PFMERGE` sang key kết quả rồi `PFCOUNT`, hoặc dùng những API hỗ trợ tính gộp tùy phiên bản.

**Không cộng thẳng PFCOUNT từng ngày để ra unique ba ngày.** Một user truy cập nhiều ngày sẽ bị đếm trùng nếu chỉ cộng các kết quả ngày. Cần dùng phép hợp HLL phù hợp.

### 8.4. Khi nào kết hợp Set và HLL?

Một hệ thống có thể dùng Set cho tập người dùng cần membership chính xác trong phiên làm việc ngắn, đồng thời dùng HLL cho dashboard tổng distinct theo ngày/tháng.

Đây là ví dụ **tối ưu cho hai truy vấn khác nhau** chứ không phải lưu dữ liệu vô ích: Set cho “ai”, HLL cho “ước lượng bao nhiêu”. Không ép một cấu trúc giải quyết cả hai khi nó không hỗ trợ.

## 9. Bloom filter: trả lời “chắc chắn không” hoặc “có thể có”

**Bloom filter** là cấu trúc xác suất hỗ trợ kiểm tra membership với chi phí bộ nhớ thấp. Khác với Set:

- Nếu filter trả **không có**, phần tử **chắc chắn chưa được thêm vào filter** trong điều kiện cấu trúc được dùng và duy trì đúng.
- Nếu filter trả **có**, phần tử **có thể có**, vì có **false positive**.

False positive nghĩa là filter báo có đối với phần tử thực tế chưa được thêm. Bloom filter chuẩn không cho phép xóa phần tử đơn giản; việc tự tắt bit có thể khiến những phần tử khác bị ảnh hưởng.

### 9.1. Bộ nhớ và xác suất false positive

Với Bloom filter tối ưu cho `n` phần tử và false-positive probability `p`, số bit xấp xỉ:

\[
m \approx -\frac{n\ln(p)}{(\ln 2)^2}
\]

Nếu dự kiến **1.000.000 phần tử** và **p = 1%**, phần bit thô xấp xỉ **9,6 triệu bit**, khoảng **1,2 MB** (chưa tính overhead). Filter nhỏ hơn thường tăng xác suất false positive; vượt capacity dự kiến cũng có thể làm false-positive rate tăng.

Đây là ước lượng lý thuyết, không phải cam kết chính xác dung lượng của từng triển khai/module.

### 9.2. Use case phù hợp

Giả sử ứng dụng cần kiểm tra rất nhiều product ID trước khi hỏi database:

~~~text
Client hỏi product ID
       |
       v
Bloom: chắc chắn không?
       |
       +-- Có -> trả kết luận không tồn tại theo hợp đồng dữ liệu phù hợp
       |
       +-- Không chắc (có thể có) -> kiểm tra database/cache thật
~~~

Nếu filter trả “có thể có”, **phải truy vấn nguồn chính** trước khi hành động yêu cầu độ chính xác tuyệt đối. Bloom filter hữu ích để giảm một số lần truy cập vô ích, không nên dùng kết quả dương để cho phép truy cập hay xác nhận thanh toán.

### 9.3. Những điều cần cảnh giác

- Redis lõi không bảo đảm có các lệnh `BF.ADD`/`BF.EXISTS` trên mọi server. Cần RedisBloom/Redis Stack hoặc bản phân phối có khả năng tương ứng, cùng client/connector hỗ trợ.
- Tính đúng đắn của kết luận âm phụ thuộc việc **mọi phần tử hiện tồn tại đều đã được thêm đúng**. Nếu pipeline bổ sung filter bị thiếu sự kiện, ứng dụng có thể có false negative **ở mức hệ thống**, dù thuật toán Bloom chuẩn không tạo false negative khi cập nhật đúng.
- Dữ liệu thay đổi liên tục, xóa thành viên, capacity tăng trưởng và rebuild filter cần thiết kế.
- Trong các tình huống cần xóa, có thể khảo sát Cuckoo filter hoặc cấu trúc khác **nếu server/module hỗ trợ**, đồng thời hiểu rủi ro và điều kiện xóa.

## 10. Sorted Set: khi cần top N, rank hoặc khoảng score

Sorted Set gồm **member duy nhất + score**:

~~~redis
ZADD game:rank:2026 120 player:42
ZADD game:rank:2026 180 player:99
ZADD game:rank:2026 150 player:17
ZRANGE game:rank:2026 0 1 REV WITHSCORES
ZREVRANK game:rank:2026 player:42
ZINCRBY game:rank:2026 10 player:42
~~~

Đây là lựa chọn tốt khi:

- Cần top 10/top 100 theo điểm.
- Cần xếp hạng hiện tại của từng member.
- Cần tìm task có thời điểm đến hạn trước một mốc.
- Cần lọc phần tử có score trong một khoảng.

### 10.1. Score là double, không phải long tùy ý

Redis lưu Sorted Set score dưới dạng **IEEE-754 double**. Các số nguyên trong khoảng:

\[
-2^{53}\le n\le 2^{53}
\]

có thể biểu diễn chính xác; ngoài khoảng đó, không phải mọi số nguyên kề nhau đều phân biệt được. Nếu bạn dùng nanosecond timestamp hoặc sequence ID rất lớn làm score, có thể mất thông tin thứ tự.

Một Redis String counter với `INCR` hỗ trợ miền signed 64-bit integer; **không thể thay thế trực tiếp bằng ZSET score** rồi kỳ vọng cùng độ chính xác. Nếu cần vừa đếm chính xác, vừa xếp hạng, hãy chọn thiết kế phù hợp hoặc lưu dữ liệu bổ trợ có kiểm soát.

### 10.2. Thứ tự khi bằng score

Hai member bằng score được Redis phân định bằng **thứ tự lexicographic theo bytes của member**. Đây không phải “người đến trước được ưu tiên trước” hay collation tiếng Việt. Nếu sản phẩm cần tie-break theo thời gian đạt điểm, cần thiết kế rule riêng.

### 10.3. Chi phí bộ nhớ

Sorted Set lưu member, score và cấu trúc phục vụ sắp xếp. Nó thường dùng nhiều metadata hơn Set đơn giản để đáp ứng các truy vấn theo thứ tự. Với ZSET nhỏ, Redis có thể dùng compact encoding, còn ZSET lớn chuyển sang cấu trúc khác; dung lượng thực phụ thuộc phiên bản, encoding, số member và độ dài mỗi member.

Đừng tạo một ZSET rất lớn khi hệ thống chỉ cần kiểm tra membership. Set thường đơn giản hơn cho truy vấn đó.

## 11. List và Stream: khác biệt giữa thứ tự danh sách và nhật ký sự kiện

### 11.1. Redis List

~~~redis
LPUSH shop:user:42:recent event-1
LPUSH shop:user:42:recent event-2
LRANGE shop:user:42:recent 0 9
LTRIM shop:user:42:recent 0 99
~~~

List phù hợp lịch sử gần đây, vùng dữ liệu có thứ tự từ đầu trái/đầu phải, thao tác push/pop nhanh. Nhưng nó không tự có ID sự kiện, consumer group hay trạng thái đã xác nhận xử lý.

Nếu `LTRIM` giữ tối đa 100 phần tử, phần tử cũ có thể bị xóa dù một consumer chưa kịp xử lý. Đây có thể chấp nhận được cho UI recent activity, nhưng nguy hiểm đối với job phải được thực thi.

### 11.2. Redis Stream

~~~redis
XADD order:events * type created orderId 42
XADD order:events * type paid orderId 42
XRANGE order:events - +
~~~

Redis Stream lưu các entry có **ID** và field-value pairs. Có thể đọc theo range ID, dùng `XREAD` hoặc consumer group để xử lý sự kiện.

Ví dụ consumer group về mặt khái niệm:

~~~text
Producer -> XADD -> Stream
                      |
                      +--> Consumer group
                              |
                              +--> Consumer A
                              +--> Consumer B
                              |
                              +--> Pending / XACK
~~~

Stream có cơ chế hỗ trợ pending entries, acknowledgement và consumer group, nhưng **không tự đảm bảo exactly-once end-to-end**. Worker vẫn cần retry, idempotency và cách xử lý lỗi sau khi side effect xảy ra.

### 11.3. Stream retention phải được thiết kế

Có thể dùng retention/trimming cho Stream:

~~~redis
XADD order:events MAXLEN ~ 10000 * type created orderId 43
XLEN order:events
~~~

Ký hiệu `~` yêu cầu giới hạn **xấp xỉ** để Redis tối ưu việc cắt dữ liệu; số entry thực tế có thể lớn hơn 10.000. Nếu cần giới hạn chính xác, phải dùng chế độ/trimming phù hợp và chấp nhận chi phí, đồng thời cân nhắc tác động tới consumer chậm.

**Đừng giả định XTRIM sẽ bảo vệ mọi pending message.** Trimming/deletion có thể khiến stream entry không còn trong dữ liệu dù consumer group còn pending state; cần chính sách retention dựa trên consumer lag, xử lý lại và mức độ tin cậy yêu cầu.

### 11.4. Khi nào chọn List, khi nào chọn Stream?

| Nhu cầu | List | Stream |
| --- | --- | --- |
| UI chỉ cần 20 sự kiện mới nhất | Phù hợp, đơn giản | Có thể dùng nhưng thường phức tạp hơn |
| Đẩy/lấy công việc đơn giản | Có thể dùng pop/blocking | Phù hợp nếu cần lịch sử/consumer group |
| Mỗi sự kiện cần ID và đọc lại theo ID | Không có sẵn | Có |
| Nhiều consumer cùng nhóm, cần ack | Phải tự thiết kế | Có primitives hỗ trợ |
| Cần giữ đúng N item cuối, không quan tâm item cũ | Dùng push + trim | Có stream trimming nhưng semantics khác |
| Cần replay lịch sử event | Phải tự xây | Phù hợp hơn khi retention đủ |

Không nên chọn Stream chỉ vì nó “mới hơn”. Nếu bài toán chỉ là cache 10 giá trị cuối, List thường gọn hơn.

## 12. Geospatial index: tìm kiếm vị trí gần đúng

Redis hỗ trợ các lệnh geospatial như:

~~~redis
GEOADD shop:stores 106.7000 10.8000 store:1
GEOADD shop:stores 106.7050 10.8050 store:2
GEOSEARCH shop:stores FROMLONLAT 106.7000 10.8000 BYRADIUS 3 km WITHDIST
~~~

Thứ tự tham số `GEOADD` là **longitude rồi latitude**, không phải latitude/longitude. Đây là lỗi phổ biến khi chuyển dữ liệu từ API bản đồ hoặc form.

### 12.1. Tại sao GEO tiết kiệm và tiện cho tìm gần?

Redis lưu chỉ mục vị trí địa lý dựa trên Sorted Set/geohash encoding, cho phép tìm các member gần một tọa độ mà không cần tải mọi cửa hàng về Java rồi tính khoảng cách. Một member địa lý mang tọa độ/score phù hợp với cơ chế GEO.

Với Spring Data Redis, có `GeoOperations` và các phương thức thêm điểm/tìm bán kính:

~~~java
redis.opsForGeo().add(
        "shop:stores",
        new org.springframework.data.geo.Point(106.7000, 10.8000),
        "store:1"
);
~~~

Đối với yêu cầu lọc/tìm gần, các API `GeoReference`, `Distance`, `GeoSearchCommandArgs` hoặc các method phù hợp phụ thuộc phiên bản Spring Data Redis. Không nên dùng `ZRANGE` tùy tiện để thay thế `GEOSEARCH` chỉ vì dữ liệu GEO được lưu trên Sorted Set.

### 12.2. Giới hạn độ chính xác

- Tọa độ được mã hóa với độ phân giải hữu hạn; khoảng cách trong Redis mang ý nghĩa tính toán địa lý thực dụng.
- Tính khoảng cách từ tọa độ không tính mọi yếu tố như đường đi, giao thông, độ cao hay ranh giới pháp lý.
- GEO phù hợp “tìm cửa hàng trong bán kính”, “địa điểm gần”, không thay thế hệ GIS đòi hỏi độ chính xác địa chính hoặc routing thực địa.
- Nếu muốn tìm theo địa chỉ/text/rating cùng lúc, có thể cần index/search hoặc một database hỗ trợ truy vấn phức tạp hơn.

## 13. RedisJSON, TimeSeries và các cấu trúc mở rộng

Một số hệ thống Redis cung cấp các khả năng nâng cao:

| Khả năng | Mẫu truy cập | Cần cân nhắc |
| --- | --- | --- |
| **RedisJSON** | Đọc/cập nhật field/path bên trong JSON object | Phải có lệnh/tính năng JSON trên server và client tương ứng |
| **TimeSeries** | Ghi mẫu đo theo timestamp, range/aggregation thời gian | Dữ liệu có mật độ theo thời gian, retention và cơ chế duplicate |
| **Search / indexing** | Query theo nhiều field, text, filter | Chi phí bộ nhớ cho index và cập nhật |
| **Bloom/Cuckoo/TopK** | Cấu trúc xác suất/thống kê | Sai số, khả năng delete, memory sizing, hỗ trợ server |

Các tính năng này không được bảo đảm có mặt trên mọi Redis server. Tên package, cách phân phối module và mức tích hợp có thể khác giữa Redis OSS, Redis Stack, dịch vụ managed Redis hoặc các phiên bản Redis mới.

**Quy tắc triển khai:** kiểm tra lệnh server có hỗ trợ, phiên bản client và mức tích hợp Spring trước khi chọn. Không giả định cứ thêm `spring-boot-starter-data-redis` là có `JSON.SET`, `TS.ADD` hay `BF.ADD`.

### 13.1. JSON String khác RedisJSON

Lưu một object JSON bằng:

~~~redis
SET shop:product:42 "{\"name\":\"Bàn phím\",\"price\":590000}"
~~~

chỉ tạo một **String chứa JSON**. Redis không tự hiểu `name` hay `price` dưới dạng field có thể cập nhật riêng bằng lệnh Hash. Muốn cập nhật JSON path ở server, cần RedisJSON hoặc cơ chế hỗ trợ thích hợp; nếu không, ứng dụng thường đọc/sửa/ghi lại cả blob.

### 13.2. TimeSeries không đồng nghĩa Sorted Set timestamp

Một ZSET có score là timestamp hỗ trợ “tìm member trong khoảng thời gian”, nhưng không tự có aggregation chuyên dụng, downsampling hoặc chính sách xử lý sample trùng như một hệ time-series. Nếu workload là hàng triệu metric samples có query theo khoảng và thống kê, hãy so sánh với TimeSeries hoặc cơ sở dữ liệu time-series phù hợp.

## 14. Ma trận quyết định theo use case

| Bài toán | Cần chính xác? | Cấu trúc nên xét đầu tiên | Vì sao | Khi nào phải đổi lựa chọn |
| --- | --- | --- | --- | --- |
| Số lượt xem một bài viết | Số nguyên đếm | String + `INCR` | Atomic increment, ít metadata | Nếu cần chống trùng từng event, thêm idempotency |
| Hồ sơ user có 8 field ngắn | Field chính xác | Hash | HGET/HSET theo field, có thể gom key overhead | Nếu cần query đa điều kiện, bổ sung index |
| User thuộc nhóm VIP không? | **Có**, quyết định quyền | Set | `SISMEMBER` exact | Không dùng Bloom dương làm kết luận |
| Số user unique trong ngày (dashboard) | Sai số nhỏ chấp nhận | HyperLogLog | Bộ nhớ nhỏ, ước lượng distinct | Dùng Set/Bitmap nếu cần chính xác |
| Điểm danh triệu user có ID số đặc | **Có** | Bitmap | 1 bit/ID, BITCOUNT | ID thưa hoặc UUID khiến Bitmap tốn kém |
| Có thể bỏ qua lookup ID chắc chắn vắng | Có thể chịu false positive | Bloom filter nếu server hỗ trợ | Tiết kiệm query âm | Dữ liệu thay đổi/rebuild, cần xác nhận dương từ nguồn chính |
| Top 100 người có điểm cao | Thứ tự theo score | Sorted Set | Score/rank/top N | Nếu cần lịch sử thay đổi, lưu riêng |
| Danh sách 20 thông báo gần nhất | Có thứ tự đầu/cuối | List | Push + trim + range | Nếu cần ack/replay, chọn Stream |
| Event log cần consumer group | Đảm bảo theo cơ chế xử lý | Stream | ID, pending, XACK | Nếu cần exactly-once end-to-end, bổ sung idempotency/durability |
| Tìm cửa hàng trong bán kính | Khoảng cách thực dụng | GEO | Truy vấn theo tọa độ | Nếu cần routing/địa chính, GIS chuyên dụng |
| Theo dõi sensor theo timestamp | Tùy độ chính xác mẫu | TimeSeries hoặc cấu trúc theo time | Range/aggregation/retention | Kiểm tra module và tính năng server |
| Đọc/sửa một trường JSON lớn | Dữ liệu trường chính xác | Hash hoặc RedisJSON | Field/path update | Nếu không có module, String JSON phù hợp khi ghi ít |
| Đếm số order để đối soát tài chính | Chính xác end-to-end | Database chính + Redis hỗ trợ tùy nhu cầu | Cần transaction/ledger/reconciliation | Không lấy HLL làm nguồn quyết định |

**Đọc ma trận như điểm xuất phát, không phải luật bất biến.** Một use case có thể cần nhiều cấu trúc cho nhiều truy vấn. Ví dụ leaderboard có Sorted Set để sắp hạng và Hash/DB để lấy tên hiển thị; dùng một ZSET lưu JSON cả hồ sơ làm member thường khó bảo trì hơn.

## 15. Bộ nhớ: từ công thức lý thuyết đến kiểm chứng thực tế

### 15.1. Đừng so sánh chỉ theo payload

Giả sử có 100.000 record, mỗi record gồm ID 20 bytes và một trạng thái 1 byte.

Phương án 100.000 String keys có:

~~~text
100.000 key Redis
  + 100.000 value
  + metadata, object overhead, allocator...
~~~

Phương án gom vào một Hash có:

~~~text
1 key Redis
  + 100.000 field/value
  + Hash encoding, metadata...
~~~

Hash **có thể** tiết kiệm overhead key, nhưng ở kích thước lớn nó không nhất thiết vẫn dùng compact encoding như một Hash nhỏ. Không thể kết luận chênh lệch RAM từ payload thuần.

### 15.2. Cùng là “unique users”, memory khác nhau

Giả sử có một triệu user ID phân biệt:

| Cấu trúc | Lưu gì? | Khả năng kiểm tra user cụ thể | Cách dung lượng tăng |
| --- | --- | --- | --- |
| Set | Toàn bộ ID | Có, chính xác | Tỷ lệ với số ID và kích thước từng member |
| Bitmap | Một bit tại offset ID | Có nếu ID ánh xạ đúng | Tỷ lệ với offset lớn nhất |
| HyperLogLog | Thống kê băm | Không | Giới hạn cấu trúc nhỏ, xấp xỉ distinct |
| Bloom filter | Nhiều bit theo hash | Chỉ có thể/không thể | Theo capacity và false-positive rate đã chọn |

Nếu ID là các số liên tục từ 0 đến 999.999, Bitmap dùng khoảng **125.000 bytes bit thô**, rất tiết kiệm. Nếu ID cao nhất là hàng tỷ tỷ với rất ít user, cách dùng offset trực tiếp không phù hợp.

### 15.3. Công thức giúp đặt giả thuyết, không thay số đo

Với Bloom filter:

\[
m\approx-\frac{n\ln p}{(\ln 2)^2}
\]

Với Bitmap có index từ 0 đến offset lớn nhất `M`:

\[
\text{bytes thô}\approx\left\lceil\frac{M+1}{8}\right\rceil
\]

Với các kiểu Set/Hash/ZSET, overhead phụ thuộc encoding, kích thước member và phiên bản Redis, vì vậy **không có một con số bytes/member cố định áp dụng mọi hệ thống**.

### 15.4. TTL và số lượng key có thể quan trọng hơn size từng key

Nếu mỗi user có một List tối đa 20 phần tử, điều đó không có nghĩa tổng dữ liệu chỉ gồm 20 phần tử:

~~~text
500.000 users × 20 events / user
  = tối đa 10.000.000 events
~~~

Chưa kể overhead 500.000 key, TTL metadata và payload thực. Với dữ liệu tạm, phải có chính sách dọn key không còn hoạt động, không chỉ giới hạn số phần tử của mỗi key.

## 16. Cách đo bộ nhớ và xác định encoding trong Redis

Redis CLI cung cấp công cụ quan sát:

~~~redis
TYPE sample:key
OBJECT ENCODING sample:key
MEMORY USAGE sample:key
MEMORY USAGE sample:key SAMPLES 0
INFO memory
INFO keyspace
DBSIZE
~~~

Ý nghĩa:

- `TYPE`: kiểm tra kiểu dữ liệu Redis thấy ở cấp lệnh (String, Hash, Set, ZSET, Stream...).
- `OBJECT ENCODING`: cho biết encoding nội bộ hiện tại của key, khi Redis hỗ trợ; nó có thể thay đổi theo kích thước/phiên bản.
- `MEMORY USAGE`: ước lượng memory Redis dùng cho key; tham số `SAMPLES` ảnh hưởng cách ước lượng đối với cấu trúc lồng/aggregate.
- `INFO memory`: bức tranh memory tổng thể, fragmentation, eviction và một số thông số vận hành.
- `DBSIZE`: số key trong logical database, **không phải số member trong các Set/ZSET**.

Đối với mỗi phương án, hãy tạo dữ liệu mẫu có **cùng distribution thật**: số lượng record, độ dài ID, số field, độ dài JSON, tỷ lệ trùng, TTL và loại thao tác. Sau đó đo `MEMORY USAGE`, RSS, latency và throughput dưới tải. Không dùng một Hash 3 field để suy luận cho Hash 3 triệu field.

### 16.1. Chú ý OBJECT ENCODING

Redis có thể chọn encoding compact cho một cấu trúc nhỏ và chuyển sang dạng khác sau khi vượt ngưỡng. Ví dụ Hash/Sorted Set/Set có những tối ưu khác nhau theo phiên bản. Do vậy:

1. Đo dữ liệu **trước và sau ngưỡng kích thước dự kiến**.
2. Đo khi value lớn nhất xuất hiện, không chỉ average.
3. Đo sau nhiều lần cập nhật/xóa, không chỉ ngay sau insert.
4. Ghi lại Redis version và cấu hình server khi so sánh.

Không cố ép một encoding nội bộ bằng mẹo dữ liệu nếu làm phức tạp correctness; Redis có quyền thay đổi triển khai giữa các phiên bản.

## 17. Spring Data Redis: API cho các cấu trúc thường dùng

Trong Spring Boot, `spring-boot-starter-data-redis` cung cấp API thao tác qua template. Với key/member là String, `StringRedisTemplate` thường là lựa chọn rõ ràng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
~~~

Ví dụ cấu hình local (Spring Boot 3.x):

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Chạy Redis thử nghiệm:

~~~bash
docker run --name redis-type-lab -p 127.0.0.1:6379:6379 -d redis:7
docker exec -it redis-type-lab redis-cli PING
~~~

Redis trả `PONG` khi có kết nối. Nếu container khác hoặc port đã bận, điều chỉnh host/port. Ở production, cần ACL/TLS, giới hạn mạng, secret và chính sách timeouts phù hợp.

### 17.1. String, Hash, Set, ZSET

~~~java
package com.example.redis;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisDataTypeExamples {

    private final StringRedisTemplate redis;

    public RedisDataTypeExamples(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long incrementViews(String articleId) {
        String key = "demo:article:" + articleId + ":views";
        return redis.opsForValue().increment(key);
    }

    public Long incrementHashField(String productId) {
        String key = "demo:product:" + productId + ":metrics";
        return redis.opsForHash()
                .increment(key, "views", 1L);
    }

    public Boolean hasJoined(String campaignId, String userId) {
        String key = "demo:campaign:" + campaignId + ":users";
        return redis.opsForSet().isMember(key, userId);
    }

    public Double addLeaderboardPoints(String userId, double points) {
        return redis.opsForZSet()
                .incrementScore("demo:leaderboard", userId, points);
    }

    public Boolean markVisited(long numericUserId) {
        if (numericUserId < 0 || numericUserId > 1_000_000) {
            throw new IllegalArgumentException("Invalid user ID");
        }
        return redis.opsForValue()
                .setBit("demo:visited:today", numericUserId, true);
    }
}
~~~

**Chú ý:**

- `incrementViews(...)` gửi lệnh số nguyên trên String.
- `incrementHashField(...)` tăng field nguyên trong Hash, không phải String key đơn.
- `hasJoined(...)` trả exact membership đối với Set hiện có.
- `addLeaderboardPoints(...)` tăng score `double` trong Sorted Set.
- `setBit(...)` đánh dấu một offset của Bitmap. Giá trị `Boolean` thường biểu thị bit **trước khi đặt**, không phải xác nhận user đã được đếm mới. Không dùng nó thay cho bit count hay số request.
- Các API trả kiểu boxed như `Long`/`Double`/`Boolean` có thể là `null` trong những ngữ cảnh như pipeline/transaction. Phần code trên là minh họa trực tiếp, chưa bao gồm xử lý lỗi/cấu hình sản xuất.
- Việc tạo key từ input phải có validation và scope/tenant phù hợp; không cho người dùng chọn key tùy ý để chạm vào dữ liệu của người khác.

### 17.2. HyperLogLog

Spring Data Redis có API:

~~~java
Long added = redis.opsForHyperLogLog()
        .add("demo:unique:2026-11-12", "user:42");

Long estimate = redis.opsForHyperLogLog()
        .size("demo:unique:2026-11-12");
~~~

`estimate` là **ước lượng distinct**. Giá trị trả từ `add(...)` không phải số distinct sau khi thêm, và không nên được sử dụng như một Boolean membership chính xác. `PFADD` chỉ cập nhật thống kê bên trong cấu trúc; thêm lại cùng user không biến nó thành một Set.

### 17.3. GeoOperations

~~~java
redis.opsForGeo().add(
        "demo:stores",
        new org.springframework.data.geo.Point(106.7000, 10.8000),
        "store:42"
);
~~~

Điểm đầu tiên trong `Point(x, y)` là **longitude**, điểm thứ hai là **latitude**. Khi truy vấn gần, dùng các method radius/search phù hợp version Spring Data Redis; xác định đơn vị km/m và cách giới hạn số kết quả rõ ràng.

### 17.4. List và Stream

~~~java
redis.opsForList()
        .leftPush("demo:user:42:recent", "event-1");

redis.opsForList()
        .trim("demo:user:42:recent", 0, 19);
~~~

Ở đây `leftPush` rồi `trim` là **hai lệnh** nếu gọi trực tiếp, có khoảng thời gian List vượt giới hạn. Nếu cần bất biến mạnh, kết hợp bằng script/transaction phù hợp.

Với Stream, Spring Data Redis cung cấp `StreamOperations`, `Record`/`MapRecord`, consumer và listener container. Cách tạo consumer group, đọc, acknowledge và retention cần được thiết kế như một luồng xử lý sự kiện; không nên cố dùng List API để thay thế.

## 18. Serializer: sai định dạng có thể làm sai cả mô hình dữ liệu

Redis lưu key/member/value theo **bytes**. Generic Java trong `RedisTemplate<K, V>` không tự đảm bảo String, JSON hay binary.

| Dữ liệu | Serializer nên xem xét | Rủi ro khi không thống nhất |
| --- | --- | --- |
| Redis key | `StringRedisSerializer` | CLI không tìm thấy key như tên mong đợi |
| Set member là user ID | String | Cùng user có hai biểu diễn bytes khác nhau |
| Sorted Set member là product ID | String | Đổi JSON/schema member có thể tạo member mới |
| Hash field name | String | Không đọc được field theo tên |
| Hash/String value là DTO | JSON typed phù hợp version | Reader khác class/schema không giải mã được |
| Bitmap | Offset bit, không dùng object serializer cho từng bit | ID mapping không nhất quán giữa service |
| HyperLogLog element | Cùng biểu diễn ID giữa các writer | Một identity có thể bị băm từ các bytes khác nhau |

Ví dụ hai service cùng đại diện user 42 nhưng một service gửi member UTF-8 `"user:42"`, service kia gửi JSON `{"userId":"42"}`. Với Set, đó là **hai member khác nhau**; với HLL, đó là **hai input băm khác nhau**, có thể làm kết quả distinct tăng ngoài ý định.

### 18.1. Không ép DTO vào mọi cấu trúc

Một lựa chọn phổ biến là lưu ID ngắn trong Set/ZSET/Geo/Stream, còn dữ liệu mô tả object nằm ở Hash, JSON key hoặc database riêng.

~~~text
ZSET:  productId -> score
Hash:  productId -> thông tin ngắn
DB:    productId -> dữ liệu đầy đủ, nguồn chính
~~~

Cách này tách **chỉ mục truy cập** khỏi **payload nghiệp vụ**, giúp đổi tên sản phẩm không thay member trong Sorted Set.

## 19. Độ chính xác số học, xác suất và hệ thống là ba tầng khác nhau

Một sai lầm là chỉ nhìn mô tả “exact” hoặc “approximate” rồi kết luận kết quả đúng ở toàn hệ thống.

### 19.1. Chính xác thuật toán

- Set cardinality là chính xác trên **những member thực có trong Set**.
- Bitmap bit count là chính xác trên **bit đã bật**.
- String integer increment là chính xác trong miền số nguyên hỗ trợ đối với mỗi lệnh đã thực thi.
- HyperLogLog có sai số thống kê theo thuật toán.
- Bloom filter có false positive theo thiết kế.
- ZSET score có giới hạn double và tie-break theo member bytes.

### 19.2. Chính xác dữ liệu đầu vào

Nếu event bị ghi trùng hoặc bị bỏ sót trước khi vào Redis, Set có thể loại trùng theo member nhưng không khôi phục được sự kiện chưa được ghi. Bitmap và HLL cũng phụ thuộc input và identity mapping.

Ví dụ nhiều thiết bị gửi cùng một user ID dưới dạng chữ hoa/chữ thường khác nhau:

~~~text
USER:42
user:42
~~~

Redis coi là hai bytes strings khác nhau. Một Set hoặc HLL không tự hiểu rằng chúng chỉ cùng một user nếu ứng dụng không chuẩn hóa ID.

### 19.3. Chính xác khi vận hành

Ngay cả cấu trúc exact cũng cần:

- Retry/idempotency với thao tác không idempotent.
- Persistence/replication/backup phù hợp với mức quan trọng của dữ liệu.
- Chính sách eviction và TTL không làm mất dữ liệu ngoài ý muốn.
- Đồng bộ giữa Redis và nguồn chính khi dữ liệu có thể thay đổi ở nhiều nơi.
- Phân quyền key để writer không ghi nhầm cấu trúc hoặc tenant.

**Không dùng HLL cho số liệu cần chính xác tuyệt đối**, nhưng cũng **không hứa Set/Bitmap đủ để bảo đảm exactly-once kinh doanh** nếu kiến trúc chưa xử lý lỗi nguồn vào.

## 20. Phương pháp lựa chọn theo từng bước

Có thể dùng một cây quyết định:

~~~text
Bạn cần làm gì với dữ liệu?
    |
    +-- Lấy một giá trị theo key?
    |       +-- Có -> String
    |       +-- Nhiều field cập nhật riêng -> Hash
    |
    +-- Kiểm tra phần tử có trong nhóm?
    |       +-- Cần chính xác -> Set
    |       +-- ID nguyên đặc -> Cân nhắc Bitmap
    |       +-- Chỉ cần lọc âm sớm, chịu false positive
    |              -> Bloom filter (nếu hỗ trợ)
    |
    +-- Đếm số lượng phần tử phân biệt?
    |       +-- Phải exact -> Set hoặc Bitmap nếu mapping phù hợp
    |       +-- Sai số nhỏ được phép -> HyperLogLog
    |
    +-- Sắp xếp theo score / top N / deadline?
    |       +-- Có -> Sorted Set
    |
    +-- Thứ tự chèn/push-pop ở hai đầu?
    |       +-- Có -> List
    |       +-- Cần entry ID/ack/replay -> Stream
    |
    +-- Tìm theo tọa độ/bán kính?
    |       +-- Có -> GeoOperations / GEO
    |
    +-- Cập nhật JSON path hoặc query nhiều field?
            +-- Kiểm tra RedisJSON/Search hoặc DB có index
~~~

Sau khi chọn ứng viên, thực hiện:

1. Chốt **hợp đồng dữ liệu**: key, member, kiểu score, serializer, TTL và quy tắc version.
2. Tính **miền giá trị**: offset lớn nhất, score precision, cardinality, số member.
3. Tính **chi phí bộ nhớ sơ bộ** theo bytes và overhead.
4. Tạo dữ liệu mẫu đại diện, đo `MEMORY USAGE`, `OBJECT ENCODING` và latency.
5. Thử các **trường hợp xấu**: ID thưa, value lớn, key hot, TTL hết hàng loạt, concurrency.
6. Đánh giá khả năng mất dữ liệu khi Redis restart/failover và phương án khôi phục.
7. Chọn cấu trúc đơn giản nhất đáp ứng mục tiêu thay vì kết hợp nhiều cấu trúc không cần thiết.

## 21. Các ví dụ ra quyết định hoàn chỉnh

### 21.1. Unique visitors cho dashboard

**Yêu cầu:** hiển thị xấp xỉ số user duy nhất trong ngày, lượng truy cập lớn, không cần biết chính xác những user nào.

**Lựa chọn:** HyperLogLog.

~~~redis
PFADD analytics:uv:2026-11-12 user:1 user:2 user:3
PFCOUNT analytics:uv:2026-11-12
EXPIRE analytics:uv:2026-11-12 2592000
~~~

TTL 30 ngày ở đây chỉ là ví dụ; cần chọn theo retention. Tính unique theo nhiều ngày bằng hợp HLL, không cộng số từng ngày. Nếu sản phẩm về sau yêu cầu biết user nào đã truy cập, cấu trúc hiện tại không đáp ứng truy vấn đó; phải lưu nguồn sự kiện hoặc một Set/DB khác.

### 21.2. Danh sách user tham gia chương trình có quyền lợi

**Yêu cầu:** biết chắc user có tham gia hay không; cần liệt kê, xóa user và đối soát.

**Lựa chọn:** Set (hoặc database là nguồn chính + Redis Set hỗ trợ).

~~~redis
SADD campaign:42:participants user:1 user:2
SISMEMBER campaign:42:participants user:2
SCARD campaign:42:participants
SREM campaign:42:participants user:2
~~~

HyperLogLog không thể xóa riêng user hoặc trả membership exact. Bloom filter có false positive, nên không được dùng để quyết định quyền lợi chỉ bằng kết quả dương.

### 21.3. Điểm danh theo ID nguyên liên tục

**Yêu cầu:** 500.000 user đã được ánh xạ thành ID từ 0 đến 499.999; mỗi ngày cần biết ai đã truy cập và bao nhiêu người khác nhau.

**Lựa chọn:** Bitmap theo ngày, nếu mapping ID bền vững.

~~~redis
SETBIT attendance:2026-11-12 42 1
GETBIT attendance:2026-11-12 42
BITCOUNT attendance:2026-11-12
EXPIRE attendance:2026-11-12 7776000
~~~

Một key Bitmap theo ngày có chi phí bit thô nhỏ. Nhưng nếu ID chuyển sang UUID hoặc số ID nhảy rất lớn, cần đánh giá Set hoặc một mapping layer khác.

### 21.4. Leaderboard mùa giải

**Yêu cầu:** lấy top 20 điểm cao, tra vị trí một player và tăng điểm khi có sự kiện.

**Lựa chọn:** Sorted Set.

~~~redis
ZADD game:2026:rank 120 user:42
ZINCRBY game:2026:rank 10 user:42
ZRANGE game:2026:rank 0 19 REV WITHSCORES
ZREVRANK game:2026:rank user:42
~~~

Member là user ID ổn định. Nếu điểm có quy tắc tài chính chính xác hoặc cần lịch sử cộng điểm để kiểm toán, lưu events và nguồn điểm chính ở hệ thống phù hợp; ZSET phục vụ thứ hạng hiện tại.

### 21.5. Lịch chạy task theo deadline

**Yêu cầu:** tìm các task có deadline trước một mốc.

**Lựa chọn:** Sorted Set với score = epoch milliseconds, member = task ID.

~~~redis
ZADD scheduler:pending 1730000000000 task:42
ZADD scheduler:pending 1730000010000 task:43
ZRANGE scheduler:pending -inf 1730000005000 BYSCORE WITHSCORES
~~~

Lấy được task đến hạn chưa đủ để triển khai một scheduler đáng tin cậy. Nhiều worker đọc cùng lúc có thể thấy cùng task; cần claim/remove nguyên tử, retry, lease và idempotency. Không tự hiểu score thời gian là TTL; Redis không xóa member chỉ vì timestamp nằm trong quá khứ.

### 21.6. Event stream xử lý đơn hàng

**Yêu cầu:** nhiều worker xử lý sự kiện có ID, cần theo dõi pending và ack.

**Lựa chọn:** Redis Stream nếu retention/durability phù hợp.

~~~redis
XADD orders:events * event created orderId 42
XLEN orders:events
XRANGE orders:events - +
~~~

Trong hệ thống thật, bổ sung consumer group, XREADGROUP, XACK, cơ chế retry/pending reconciliation và chính sách trim. Nếu event phải lưu nhiều năm và đối soát tài chính, database hoặc event log bền vững có thể là nguồn chính, Redis chỉ hỗ trợ xử lý gần thời gian thực.

## 22. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng HLL vì “ít RAM” nhưng cần kiểm tra user cụ thể | Không có membership query | Dùng Set hoặc Bitmap exact |
| Dùng Bloom để xác nhận user chắc chắn tồn tại | False positive dẫn đến quyết định sai | Kết quả dương phải được xác minh ở nguồn chính |
| Dùng Bitmap trực tiếp với ID rất thưa | Bộ nhớ tăng theo offset lớn nhất | Xét Set hoặc ánh xạ ID phù hợp |
| Dùng Set cho unique dashboard hàng trăm triệu ID dù không cần danh sách | RAM lớn | Đánh giá HLL nếu sai số chấp nhận |
| Dùng ZSET score cho sequence 64-bit rất lớn | Mất chính xác ở miền double | Xem lại định dạng/sơ đồ lưu |
| Dùng List để xử lý job cần ack/replay | Có nguy cơ mất job/khó recover | Xét Stream/message broker |
| Dùng Stream nhưng trim trước khi consumer xử lý | Entry có thể không còn để replay | Retention theo lag/pending và chính sách xử lý |
| Dùng Hash lớn rồi luôn gọi HGETALL | Response và latency lớn | HGET/HMGET/HSCAN theo nhu cầu |
| Dùng JSON String để cập nhật một field liên tục | Đọc/ghi cả object nhiều lần | Xem Hash hoặc RedisJSON nếu hỗ trợ |
| Coi Redis GEO là độ chính xác địa chính | Sai kết luận khoảng cách/đường đi | Chọn GIS/routing chuyên dụng cho yêu cầu đó |
| Dùng cùng một key cho String rồi Set | WRONGTYPE | Quy ước key namespace và owner |
| Lưu DTO JSON làm ZSET member rồi đổi schema | Member mới/đúp logic | Lưu ID ổn định |
| Quên serializer member giữa nhiều service | Bytes khác nhau, đếm trùng | Chuẩn hóa format/charset |
| Không đặt TTL cho key tạm | Tổng key tăng theo user/time | Thiết kế retention, giám sát memory |
| Chỉ nhìn `MEMORY USAGE` của một key nhỏ | Dự báo RAM sai | Đo ở quy mô và phân bố thực |
| Tăng connection pool khi Redis server chậm | Không xử lý bottleneck dữ liệu/lệnh | Đo CPU, command latency, round trips |
| Coi atomic Redis command là exactly-once nghiệp vụ | Retry có thể ghi trùng | Idempotency, event ID, reconciliation |

## 23. Bài thực hành: so sánh exact, approximate và bộ nhớ

**Bài toán:** với một tập ID user truy cập trong ngày, xây ba cách thống kê distinct: Set, Bitmap (nếu ID là số trong miền nhỏ), HyperLogLog; đồng thời bổ sung Sorted Set để xếp hạng số điểm.

### 23.1. Chuẩn bị

Chạy Redis local và Spring Boot app có starter phù hợp. Sử dụng key theo namespace thử nghiệm:

~~~text
lab:users:set
lab:users:bitmap
lab:users:hll
lab:users:rank
~~~

Chọn 100.000 user ID liên tiếp và tạo event có trùng lặp. **Không dùng kết quả của bài thực hành làm số liệu production**: đây là môi trường học tập, phụ thuộc Redis version, dữ liệu và bộ nhớ máy.

### 23.2. Nhánh Set

1. Với mỗi user ID, chạy `SADD lab:users:set user:<id>`.
2. Tạo một số event trùng để xác nhận Set không tạo member trùng.
3. Dùng `SCARD` lấy số distinct chính xác.
4. Dùng `SISMEMBER` kiểm tra một vài ID có/không.
5. Ghi `MEMORY USAGE` và xem `OBJECT ENCODING`.

### 23.3. Nhánh Bitmap

1. Với mỗi ID nguyên không âm, chạy `SETBIT lab:users:bitmap <id> 1`.
2. Đặt lại bit đã bật để xác nhận `BITCOUNT` không tăng.
3. Dùng `GETBIT` kiểm tra một ID.
4. Dùng `BITCOUNT` lấy số distinct chính xác theo mapping này.
5. Đo memory; thử thêm một ID cực lớn **trên key test tách biệt** để quan sát tác động của sparse offset, không làm ảnh hưởng key dùng chung.

### 23.4. Nhánh HyperLogLog

1. Với mỗi ID, chạy `PFADD lab:users:hll user:<id>`.
2. Thêm lại các ID trùng và gọi `PFCOUNT`.
3. So sánh ước lượng với `SCARD`/`BITCOUNT`.
4. Ghi sai số tuyệt đối và sai số tương đối:

\[
\text{sai số tương đối} =
\frac{|\text{ước lượng}-\text{giá trị thật}|}{\text{giá trị thật}}
\]

5. Đo memory. Không kết luận thuật toán luôn có sai số dưới một ngưỡng cố định chỉ từ một lần chạy.

### 23.5. Nhánh Sorted Set

1. Tạo 1000 player ID và score trong miền nhỏ.
2. Dùng `ZADD` thêm member/score.
3. Dùng `ZRANGE 0 9 REV WITHSCORES` lấy top 10.
4. Dùng `ZREVRANK` để xem vị trí một player.
5. Cập nhật score một player bằng `ZINCRBY` và quan sát rank thay đổi.
6. Thử hai member cùng score để thấy tie-break theo bytes.

### 23.6. Bảng ghi kết quả

| Cấu trúc | Số ID đầu vào | Distinct thực | Kết quả đếm | Sai số tương đối | Memory usage | Có truy vấn membership? |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Set | Tự đo | Tự đo | `SCARD` | 0 nếu dữ liệu được ghi đúng | Tự đo | Có |
| Bitmap | Tự đo | Tự đo | `BITCOUNT` | 0 nếu mapping đúng | Tự đo | Có theo offset |
| HyperLogLog | Tự đo | Tự đo | `PFCOUNT` | Tự đo | Tự đo | Không |

Không điền giá trị memory giả định làm kết quả benchmark. Ngoài RAM, nên đo thời gian ghi, thời gian đọc, CPU và tổng số key. Đọc mỗi key thử nghiệm nhiều lần không thay thế benchmark dưới traffic thực.

## 24. Câu hỏi tự ôn

1. Ba trục chính để chọn kiểu Redis trong bài này là gì?
2. “Đếm chính xác” khác “đếm đúng sự kiện nghiệp vụ” ở điểm nào?
3. Vì sao Set có thể kiểm tra membership exact nhưng HLL không thể?
4. Khi nào Bitmap dùng ít RAM hơn Set? Khi nào lại dùng quá nhiều RAM?
5. Tại sao kích thước Bitmap phụ thuộc offset lớn nhất?
6. HLL có thể trả danh sách user đã được thêm không? Có thể xóa riêng một user không?
7. Sai số chuẩn khoảng 0,81% của HLL có nghĩa mọi kết quả luôn lệch dưới 0,81% không?
8. Bloom filter có false positive hay false negative trong điều kiện hoạt động chuẩn?
9. Vì sao Bloom filter không nên tự quyết định cấp quyền dựa trên kết quả dương?
10. Một Set chứa một triệu user ID có thể tốn RAM khác Bitmap hay HLL ra sao?
11. Hash có lợi thế nào so với nhiều key String cho các field nhỏ?
12. Vì sao Hash nhỏ có thể dùng encoding compact nhưng Hash lớn tốn nhiều RAM hơn dự tính?
13. Redis String counter và ZSET score khác nhau về độ chính xác nguyên như thế nào?
14. Khi member trong ZSET bằng score, Redis dùng quy tắc tie-break gì?
15. Vì sao không nên lưu toàn bộ JSON của user làm Sorted Set member?
16. List và Stream khác nhau ở tính năng consumer group/ack/replay thế nào?
17. Stream có đảm bảo exactly-once end-to-end chỉ nhờ XACK không?
18. Vì sao việc trim Stream cần tính đến pending entries và consumer lag?
19. GEO phù hợp yêu cầu tìm gần nào, và khi nào cần GIS chuyên dụng?
20. Vì sao score timestamp không tự biến ZSET thành danh sách có TTL từng member?
21. RedisJSON và một String chứa JSON khác nhau ở khả năng cập nhật field ra sao?
22. `MEMORY USAGE`, `OBJECT ENCODING` và `INFO memory` giúp bạn đo ba khía cạnh gì?
23. Nếu nhiều service dùng serializer khác nhau cho cùng user ID, chuyện gì xảy ra với Set và HLL?
24. Tại sao phải kiểm tra phiên bản Redis trước khi gọi `BF.ADD` hoặc `JSON.SET`?
25. Nếu dự án cần cả top 10 và hồ sơ sản phẩm, bạn sẽ kết hợp những cấu trúc nào và vì sao?

## 25. Tài liệu tham khảo

- [Redis — Data types](https://redis.io/docs/latest/develop/data-types/): tổng quan String, Hash, List, Set, Sorted Set, Stream, Bitmap, HLL và những lựa chọn có sẵn.
- [Redis — HyperLogLog](https://redis.io/docs/latest/develop/data-types/probabilistic/hyperloglogs/): distinct estimation, sai số và chi phí bộ nhớ.
- [Redis — Bitmaps](https://redis.io/docs/latest/develop/data-types/bitmaps/): cách ánh xạ bit trong String và thao tác bit.
- [Redis — Sorted sets](https://redis.io/docs/latest/develop/data-types/sorted-sets/): member, score, rank và range.
- [Redis — Streams](https://redis.io/docs/latest/develop/data-types/streams/): entry ID, đọc sự kiện và consumer groups.
- [Redis — Geospatial](https://redis.io/docs/latest/develop/data-types/geospatial/): index tọa độ và truy vấn khoảng cách.
- [Redis — MEMORY USAGE](https://redis.io/docs/latest/commands/memory-usage/): đo memory cho từng key.
- [Redis — OBJECT ENCODING](https://redis.io/docs/latest/commands/object-encoding/): xem biểu diễn nội bộ theo Redis version.
- [Redis — Bloom filter](https://redis.io/docs/latest/develop/data-types/probabilistic/bloom-filter/): membership gần đúng và false positive, khi tính năng được hỗ trợ.
- [Spring Data Redis Reference](https://docs.spring.io/spring-data/redis/reference/): template, data types, Redis operations và cấu hình tích hợp Spring.
- [Spring Data Redis — RedisTemplate JavaDoc](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/RedisTemplate.html): các nhóm operations như Value, Hash, Set, ZSet, Geo, HyperLogLog và Stream.

**Ghi nhớ:** Chọn Redis data type từ **câu hỏi truy cập và yêu cầu chính xác**, không chọn chỉ vì tên cấu trúc nghe quen thuộc. **Set/Bitmap** phục vụ membership chính xác trong điều kiện dữ liệu và mapping phù hợp; **HyperLogLog** phục vụ distinct count xấp xỉ; **Bloom** phục vụ lọc membership có false positive; **Sorted Set** phục vụ score/rank; **List/Stream** phục vụ hai cấp nhu cầu khác nhau về thứ tự và xử lý sự kiện; **Hash/String** phù hợp point lookup hoặc field update; **GEO** phục vụ truy vấn không gian thực dụng. Sau lựa chọn lý thuyết, luôn kiểm tra **dữ liệu mẫu, serializer, TTL, memory thực tế và failure semantics** trước khi dùng ở quy mô production.
