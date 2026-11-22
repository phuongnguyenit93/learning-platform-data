# Ví dụ Redis, DynamoDB hoặc hệ khác với phạm vi bảo đảm được nêu rõ

## 1. Từ ý tưởng khóa–giá trị đến hệ thống thực tế

**Mô hình khóa–giá trị (key–value)** lưu dữ liệu theo ánh xạ từ một **khóa duy nhất trong phạm vi xác định** tới một **giá trị**. Tư duy sử dụng cơ bản là: biết khóa thì có thể lấy, tạo, cập nhật hoặc xóa giá trị tương ứng.

~~~text
key                             value
----------------------------------------------------------------
session:user-17:token-8f2       {"userId":"17","role":"student"}
cart:user-17                    {"lines":[{"sku":"B01","qty":2}]}
stock:sku-B01                   42
feature:course-recommendation   "enabled"
~~~

Tuy nhiên, mô tả “đọc và ghi theo khóa” chưa đủ để vận hành hệ thống đáng tin cậy. Cần trả lời thêm:

- **Phạm vi duy nhất:** Khóa có duy nhất trong một bảng, một cơ sở dữ liệu, một tenant hay trên toàn bộ ứng dụng?
- **Nguyên tử:** Khi hai yêu cầu cùng cập nhật một khóa, có thể bị mất cập nhật không?
- **Nhất quán khi đọc:** Sau khi ghi thành công, một lần đọc khác có chắc nhìn thấy giá trị mới không?
- **Bền vững:** Sau khi nhận phản hồi thành công, dữ liệu có thể mất khi tiến trình hoặc máy chủ gặp sự cố không?
- **Nhiều khóa:** Hai thao tác trên hai khóa khác nhau có thể cùng thành công hoặc cùng thất bại không?
- **Phân vùng và nhiều vùng:** Bảo đảm trên một máy hoặc một vùng có tiếp tục đúng khi dữ liệu được sao chép sang nơi khác không?
- **Hết hạn:** TTL giúp dọn dữ liệu, nhưng liệu có bảo đảm xóa đúng thời điểm?

Trong nhóm NoSQL, **Redis** và **Amazon DynamoDB** đều cung cấp những thao tác có hình thức key–value, nhưng chúng có kiến trúc và bảo đảm khác nhau. Redis thường được dùng làm cache, phiên, bộ đếm và cấu trúc dữ liệu có độ trễ thấp. DynamoDB là cơ sở dữ liệu NoSQL được quản lý, tổ chức dữ liệu trong bảng với khóa chính và các thuộc tính của item.

Mục tiêu của bài học là thực hành những thao tác tiêu biểu trên cả hai hệ, đồng thời **ghi rõ phạm vi mà mỗi kết luận về tính đúng đắn áp dụng**. Không nên gán những đặc tính của một sản phẩm cho tất cả cơ sở dữ liệu khóa–giá trị.

## 2. Một số khái niệm bắt buộc phân biệt

### 2.1. Key, value, item và partition

Trong Redis, mỗi khóa trỏ tới một giá trị thuộc kiểu dữ liệu Redis hỗ trợ như string, hash, list, set, sorted set. Vì vậy “value” không nhất thiết chỉ là một chuỗi văn bản: nó cũng có thể là một tập hợp các phần tử mà Redis cung cấp lệnh xử lý riêng.

Trong DynamoDB, mỗi **item** là tập thuộc tính; **primary key** được định nghĩa theo một trong hai dạng:

1. **Partition key**: chỉ một thuộc tính khóa phân vùng.
2. **Partition key + sort key**: kết hợp hai thuộc tính tạo thành khóa chính của item.

Hai item trong một bảng có thể có cùng partition key khi bảng có sort key, nhưng không được có cùng **cặp partition key và sort key**. Việc một trường không thuộc khóa chính bị trùng không mặc nhiên bị từ chối.

Ví dụ bảng có khóa chính (PK, SK):

| PK | SK | Thuộc tính khác |
|---|---|---|
| USER#17 | PROFILE | name = An |
| USER#17 | CART | totalItems = 2 |
| USER#17 | ORDER#1001 | status = PAID |
| USER#17 | ORDER#1002 | status = PENDING |

Việc lưu nhiều loại item dưới một partition key chung là **một cách thiết kế**, không phải quy định bắt buộc. Khóa phải được chọn theo đường truy cập và tải thực tế.

### 2.2. Atomicity, consistency, isolation và durability

Những từ này dễ bị dùng lẫn nhau:

| Thuộc tính | Câu hỏi chính | Ví dụ |
|---|---|---|
| **Atomicity** | Một thao tác có thể thành công một phần không? | Giảm một bộ đếm có bị chen giữa các bước nội bộ không? |
| **Read consistency** | Một lần đọc được thấy phiên bản nào? | Đọc ngay sau khi ghi có thấy giá trị mới không? |
| **Isolation** | Các thao tác đồng thời có nhìn thấy trạng thái trung gian hay ảnh hưởng lẫn nhau ra sao? | Hai giao dịch chuyển tiền có giữ được bất biến không? |
| **Durability** | Dữ liệu đã xác nhận ghi được bảo vệ trước sự cố như thế nào? | Restart hoặc failover có thể làm mất ghi mới nhất không? |
| **Availability** | Dịch vụ còn phục vụ yêu cầu khi có lỗi hoặc phân hoạch mạng không? | Một phân vùng dữ liệu không sẵn sàng có làm đọc/ghi thất bại không? |

Một thao tác **nguyên tử trên một khóa** không đồng nghĩa với **giao dịch nguyên tử trên nhiều khóa**. Tương tự, đọc nhất quán mạnh không có nghĩa mọi cập nhật ở nhiều vùng được phối hợp tức thời.

### 2.3. Bảng đối chiếu bảo đảm ở mức khái niệm

| Khía cạnh | Redis thông thường | DynamoDB thông thường |
|---|---|---|
| Địa chỉ dữ liệu | Key trong logical database hoặc không gian khóa theo cấu hình | Primary key trong một bảng |
| Thao tác một đối tượng | Lệnh đơn được thực thi nguyên tử tại máy chủ Redis xử lý khóa | Ghi một item có thể kết hợp điều kiện nguyên tử |
| Nhiều đối tượng | MULTI/EXEC hoặc Lua/Functions có phạm vi và hạn chế cụ thể; Redis Cluster có ràng buộc hash slot | Hỗ trợ giao dịch nhiều item qua API transaction, trong giới hạn sản phẩm |
| Đọc sau ghi | Phụ thuộc nơi đọc: primary, replica, failover và cấu hình | Có lựa chọn eventually consistent hoặc strongly consistent cho một số thao tác đọc |
| Bền vững | Phụ thuộc RDB/AOF, fsync, replication và failover được cấu hình | Dịch vụ quản lý lưu trữ bền vững trong phạm vi hệ thống cung cấp; tính nhìn thấy giữa vùng là vấn đề riêng |
| TTL | Lệnh đặt thời gian hết hạn trên khóa; có thể bị eviction do chính sách bộ nhớ | Thuộc tính TTL cho xóa nền bất đồng bộ, không phải thời điểm xóa chính xác |
| Quy tắc duy nhất ngoài khóa chính | Thường thiết kế bằng khóa đặt chỗ và thao tác có điều kiện | Cần mô hình hóa theo primary key hoặc cơ chế điều kiện/giao dịch; không có unique index tổng quát như SQL |

**Giới hạn của bảng:** Đây là mô tả định hướng. Những bảo đảm cụ thể phải được đánh giá theo phiên bản, loại triển khai, topology, cấu hình replication, chế độ vùng và API đang sử dụng.

## 3. Ví dụ Redis: lưu phiên người dùng có TTL

### 3.1. Tình huống

Một ứng dụng học tập cần lưu trạng thái phiên ngắn hạn. Client giữ một token ngẫu nhiên; server dùng token đã được xác thực để tra cứu dữ liệu phiên. Ví dụ dùng Redis CLI:

~~~redis
SET session:token-8f2 "{\"userId\":\"17\",\"role\":\"student\"}" EX 1800 NX
GET session:token-8f2
TTL session:token-8f2
DEL session:token-8f2
~~~

Ý nghĩa từng thành phần:

- **SET key value**: đặt giá trị dạng string.
- **EX 1800**: yêu cầu khóa hết hạn sau 1.800 giây.
- **NX**: chỉ tạo nếu khóa chưa tồn tại ở thời điểm Redis xử lý lệnh.
- **GET**: lấy giá trị nếu khóa vẫn tồn tại.
- **TTL**: xem thời gian sống còn lại bằng giây. Giá trị trả về có trường hợp đặc biệt cho khóa không tồn tại hoặc không có thời hạn hết hạn.
- **DEL**: xóa khóa.

Kết hợp **SET ... EX ... NX** trong **một lệnh** cho phép vừa yêu cầu tạo có điều kiện vừa gắn thời hạn sống mà không tạo khoảng trống giữa hai lệnh riêng biệt.

### 3.2. Phạm vi bảo đảm

**Bảo đảm:** Với một Redis primary thực thi lệnh, thao tác SET kèm NX và EX được xử lý như một lệnh nguyên tử. Hai yêu cầu cùng đặt **cùng khóa** trên cùng đường thực thi không thể đều được chấp nhận nếu khóa vẫn tồn tại và chưa bị xóa hoặc hết hạn giữa hai lệnh.

**Không tự được bảo đảm:**

- Redis không mặc định biến một khóa phiên thành dữ liệu bền vững qua mọi loại sự cố. Khả năng phục hồi phụ thuộc chế độ persistence, sao chép, failover.
- Lệnh đã trả thành công trên primary không mặc nhiên có nghĩa replica đã nhận và lưu bền vững ghi đó.
- Nếu khóa đã hết hạn, NX có thể tạo giá trị mới cho cùng tên khóa theo chính sách phiên.
- TTL không phải lịch thực thi công việc chính xác đến mili giây; ứng dụng không nên dùng “xóa khóa đúng thời điểm X” như một sự kiện nghiệp vụ cần bảo đảm.
- Token phiên cần đủ ngẫu nhiên và bí mật; ví dụ token ngắn chỉ để minh họa. Redis không tự xác thực chủ sở hữu chỉ dựa vào việc tồn tại của một khóa.

Với phiên đăng nhập thật, thường không nên chứa thông tin quá nhạy cảm ở dạng dễ bị lộ; cần triển khai ACL, TLS, bảo vệ token, chính sách hết hạn và thu hồi phiên phù hợp.

### 3.3. Khi cập nhật phiên cần chú ý TTL

Ví dụ:

~~~redis
SET session:token-8f2 "{\"userId\":\"17\",\"role\":\"teacher\"}"
TTL session:token-8f2
~~~

Một lệnh SET ghi đè thông thường có thể loại bỏ thời hạn hết hạn đang gắn với khóa. Nếu muốn giữ TTL, phải dùng tùy chọn hoặc thiết kế phù hợp (chẳng hạn KEEPTTL ở những phiên bản Redis hỗ trợ), hoặc đặt lại EX theo chính sách ứng dụng.

Điều này có ý nghĩa bảo mật: cập nhật vai trò hoặc dữ liệu phiên bằng lệnh không giữ TTL có thể vô tình biến phiên ngắn hạn thành phiên không tự hết hạn.

## 4. Redis: bộ đếm nguyên tử và điều kiện cập nhật

### 4.1. Vì sao GET rồi SET có thể làm mất cập nhật?

Giả sử có bộ đếm lượt xem:

~~~redis
SET views:course-17 10
~~~

Hai worker cùng thực hiện:

~~~text
Worker A: GET views:course-17 -> 10
Worker B: GET views:course-17 -> 10
Worker A: SET views:course-17 11
Worker B: SET views:course-17 11
~~~

Sau hai lượt tăng, bộ đếm vẫn là 11, dù giá trị mong muốn là 12. Đây là **lost update** do ứng dụng tự thực hiện đọc–tính–ghi ngoài một thao tác nguyên tử.

Redis cung cấp lệnh:

~~~redis
INCR views:course-17
INCRBY views:course-17 5
DECR views:course-17
~~~

**Bảo đảm trong phạm vi:** INCR và các biến thể là những lệnh đơn nguyên tử tại Redis xử lý khóa đó. Khi nhiều client tăng cùng khóa, các phép tăng không chen vào bên trong nhau như mẫu GET rồi SET ở ứng dụng.

**Giới hạn:** Nếu một client gửi INCR, Redis đã tăng nhưng phản hồi bị mất, rồi client **retry** lệnh INCR, giá trị có thể tăng lần thứ hai. **Atomicity không đồng nghĩa idempotency**. Nếu cần đếm một sự kiện đúng một lần, phải có định danh sự kiện và cơ chế chống xử lý lặp.

### 4.2. INCR và EXPIRE: hai lệnh không tự thành một thao tác

Giả sử muốn đếm số request trong một cửa sổ thời gian:

~~~redis
INCR rate:client-17:minute-1200
EXPIRE rate:client-17:minute-1200 60
~~~

Nếu client hoặc kết nối gặp lỗi sau INCR và trước EXPIRE, khóa có thể chưa có TTL. Ngoài ra, EXPIRE mỗi lần request cũng có thể **kéo dài hạn liên tục**, khiến ngữ nghĩa “cửa sổ cố định” bị thay đổi.

Một ví dụ minh họa dùng Lua để đặt TTL **chỉ khi bộ đếm vừa đạt 1**:

~~~lua
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end
return count
~~~

Gọi bằng EVAL theo giao diện Redis CLI:

~~~redis
EVAL "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],tonumber(ARGV[1])) end; return n" 1 rate:client-17:window-1200 60
~~~

**Bảo đảm:** Các lệnh bên trong script được Redis thực thi mà không xen một lệnh client khác vào giữa trong cùng phạm vi thực thi của máy chủ. Điều này phù hợp cho logic cần kết hợp INCR và EXPIRE.

**Giới hạn:**

- Lua script dài hoặc tính toán nặng có thể chiếm thời gian xử lý của Redis; tránh thực hiện công việc chậm trong script.
- Trong Redis Cluster, các khóa được thao tác bởi script phải tuân thủ quy tắc phân bố hash slot và giới hạn của lệnh/phiên bản.
- Nếu script gặp lỗi khi đã thực hiện một số ghi, không được mặc định có cơ chế **rollback toàn bộ như transaction của cơ sở dữ liệu quan hệ**.
- Bộ đếm cửa sổ chỉ là **cách minh họa** rate limiting; thuật toán giới hạn thực tế cần xác định chính xác fixed window, sliding window hay token bucket, cùng cách xử lý biên cửa sổ và retry.

### 4.3. MULTI/EXEC và WATCH giải quyết chuyện gì?

Redis có cơ chế nhóm lệnh:

~~~redis
MULTI
INCR balance:wallet-1
INCR balance:wallet-2
EXEC
~~~

Các lệnh được xếp vào transaction và thực thi tuần tự mà các lệnh client khác không chen vào giữa khi EXEC được xử lý. Tuy nhiên, **Redis MULTI/EXEC không có cơ chế rollback tự động toàn bộ những lệnh đã thực thi thành công khi một lệnh bị lỗi thời gian chạy**. Không nên dùng nó như bằng chứng cho mọi tính chất ACID nhiều bản ghi trong SQL.

**WATCH** hỗ trợ kiểm soát đồng thời lạc quan: client theo dõi khóa, đọc giá trị, rồi MULTI/EXEC. Nếu khóa bị thay đổi trước EXEC, transaction theo WATCH có thể không được áp dụng và client phải thử lại theo quy tắc.

~~~text
WATCH wallet:A
GET wallet:A
// Ứng dụng tính giá trị mới và xác định điều kiện
MULTI
SET wallet:A <newValue>
EXEC
~~~

Đây là **mẫu tư duy**, không phải file script có thể chạy nguyên văn vì còn bước tính giá trị của ứng dụng. Việc đọc trước bằng GET một mình không an toàn; cơ chế WATCH và kết quả EXEC là phần quyết định thao tác có thành công theo phiên bản đã quan sát hay không.

## 5. Redis: cache-aside và những gì cache không bảo đảm

### 5.1. Tình huống

Hệ thống có bảng khóa học lưu trong kho chính. Thông tin khóa học được đọc rất nhiều lần nhưng cập nhật không thường xuyên. Redis được dùng làm cache.

~~~mermaid
flowchart TD
    A["Client hỏi khóa C17"] --> B["Ứng dụng GET course:C17"]
    B --> C{"Cache hit?"}
    C -->|Có| D["Trả giá trị cache"]
    C -->|Không| E["Đọc từ kho dữ liệu chính"]
    E --> F["SET cache với TTL"]
    F --> G["Trả dữ liệu"]
~~~

Ví dụ:

~~~redis
GET course:C17
SET course:C17 "{\"title\":\"NoSQL căn bản\",\"version\":12}" EX 300
~~~

TTL 300 giây chỉ là **giá trị minh họa**. Thời gian phù hợp phải được chọn theo nhu cầu độ mới, tần suất thay đổi và khả năng chấp nhận dữ liệu cũ.

### 5.2. Phạm vi bảo đảm

**Bảo đảm:** Nếu Redis trả một giá trị đang tồn tại, ứng dụng có thể sử dụng nó theo chính sách cache. Nếu khóa đã hết hạn, Redis xử lý theo ngữ nghĩa hết hạn của khóa và lần đọc có thể trả về không tìm thấy.

**Không tự được bảo đảm:**

- Giá trị cache **không chắc là phiên bản mới nhất** của kho nguồn. Nếu dữ liệu nguồn đổi nhưng cache chưa được làm mới hoặc xóa, client có thể thấy dữ liệu cũ.
- TTL giới hạn thời gian lưu theo một chính sách, không tự tạo tính nhất quán giữa hai kho.
- Cache có thể bị mất do restart, failover hoặc **eviction** khi chính sách bộ nhớ cho phép; ứng dụng phải xử lý cache miss.
- Hai client có thể cùng cache miss và cùng truy cập kho nguồn (cache stampede).
- Một quá trình tải chậm có thể ghi dữ liệu cũ đè lên cache vừa được làm mới nếu không có cơ chế phiên bản hoặc điều kiện phù hợp.

Một chiến lược phổ biến là **cache-aside**: khi miss, đọc kho chính và đưa vào cache; khi có cập nhật, ứng dụng chủ động invalidation hoặc cập nhật cache theo quy trình. Với dữ liệu cần đúng tức thời như số dư hay quyền truy cập nhạy cảm, phải đánh giá kỹ liệu cache có phù hợp làm nguồn ra quyết định hay không.

## 6. Redis Cluster, replica và phạm vi “nguyên tử”

Redis chạy trên một primary đơn lẻ khác với Redis có replica hoặc Redis Cluster.

### 6.1. Một máy chủ đang xử lý lệnh

Một lệnh SET NX hoặc INCR có bảo đảm nguyên tử tại máy chủ thực thi. Đây là điều đã dùng trong các ví dụ trước.

### 6.2. Primary và replica

Redis thường sao chép dữ liệu từ primary sang replica theo cơ chế **bất đồng bộ**. Vì vậy:

- Replica có thể chưa thấy cập nhật vừa thành công trên primary.
- Khi xảy ra failover, các ghi mới nhất chưa được sao chép đầy đủ có thể có nguy cơ mất tùy tình huống và cấu hình.
- Một lệnh thành công trên primary chưa phải lời cam kết rằng mọi replica đều đã ghi bền vững dữ liệu.

Redis có những cơ chế như WAIT hoặc WAITAOF trong các môi trường hỗ trợ để chờ các điều kiện nhất định liên quan tới replica hoặc persistence. Nhưng cần xem chính xác **điều kiện đã được xác nhận là gì**; đó không phải lời bảo đảm tổng quát rằng sẽ không bao giờ mất ghi dưới mọi lỗi.

### 6.3. Redis Cluster và nhiều khóa

Redis Cluster chia khóa vào các hash slot. Nhiều thao tác đa khóa hoặc script không thể tùy ý truy cập các khóa nằm ở nhiều slot khác nhau.

Ví dụ tên khóa sử dụng hash tag:

~~~text
cart:{user17}:items
cart:{user17}:summary
cart:{user18}:items
~~~

Hai khóa đầu có cùng phần trong dấu ngoặc nhọn, nên được gán vào cùng hash slot theo cách tính của Redis Cluster; khóa thứ ba không bắt buộc cùng slot.

**Lợi ích:** Có thể thiết kế để những khóa cần thao tác cùng nhau nằm trên cùng slot và dùng các lệnh đa khóa được hỗ trợ.

**Giới hạn:** Đặt quá nhiều khóa chung một slot có thể gây lệch tải. Cùng slot giúp thỏa điều kiện định tuyến của một số lệnh, nhưng không tạo giao dịch toàn cụm hoặc bảo đảm xuyên mọi kiểu failover.

### 6.4. Lưu ý về khóa phân tán

Một mẫu giữ khóa tạm thời là:

~~~redis
SET lock:job-17 random-owner-token NX PX 10000
~~~

Lệnh này có thể giành quyền trên **một khóa của một Redis instance đang thực thi** trong thời hạn được chỉ định, nhưng không đủ để kết luận “chỉ duy nhất một tác nhân có thể tác động vào tài nguyên bên ngoài” trong mọi tình huống mạng chậm, lease hết hạn hoặc failover.

Nếu worker A giữ lease, bị treo lâu; lease hết hạn rồi worker B giành được khóa; sau đó A tiếp tục làm việc, cả hai có thể cùng thao tác trên hệ thống đích. Với nghiệp vụ nghiêm ngặt, cần cơ chế như **fencing token** được hệ thống đích kiểm tra, điều kiện ghi phiên bản, hoặc cách phối hợp có bảo đảm thích hợp. Redis SET NX có TTL tự nó không cung cấp những bảo đảm đó.

## 7. Ví dụ DynamoDB: bảng key–value cho giỏ hàng

### 7.1. Thiết kế khóa

Giả sử ứng dụng lưu giỏ hàng hiện tại của mỗi người dùng vào một bảng DynamoDB tên LearningStore:

| PK | SK | items | updatedAt |
|---|---|---|---|
| USER#17 | CART#CURRENT | Danh sách SKU và số lượng | Thời điểm cập nhật |
| USER#18 | CART#CURRENT | Danh sách SKU và số lượng | Thời điểm cập nhật |

Để truy cập giỏ của user 17, ta biết cả PK và SK. Đây là một **mô hình theo khóa truy cập**. Nếu cần truy vấn giỏ theo trạng thái, giá trị hoặc ngày cập nhật của mọi user, phải thiết kế thêm đường truy cập, chỉ mục hoặc cấu trúc phù hợp; không nên giả định GET theo khóa chính tự giải quyết mọi bộ lọc.

### 7.2. Đọc một item theo khóa chính

Ví dụ JavaScript sử dụng AWS SDK for JavaScript v3 với Document Client:

~~~javascript
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import {
  DynamoDBDocumentClient,
  GetCommand
} from "@aws-sdk/lib-dynamodb";

const client = DynamoDBDocumentClient.from(
  new DynamoDBClient({ region: "ap-southeast-1" })
);

const result = await client.send(new GetCommand({
  TableName: "LearningStore",
  Key: {
    PK: "USER#17",
    SK: "CART#CURRENT"
  },
  ConsistentRead: true
}));

console.log(result.Item);
~~~

Điểm chính:

- **GetItem/GetCommand** truy cập item theo đủ thành phần của primary key.
- **ConsistentRead: true** yêu cầu strongly consistent read khi dùng với thao tác/đối tượng được DynamoDB hỗ trợ, chẳng hạn đọc từ bảng trong cùng Region.
- Đọc strongly consistent **không phải transaction khóa trước**. Ngay sau lần đọc, một yêu cầu khác vẫn có thể sửa item.

**Phạm vi bảo đảm khi đọc DynamoDB:**

| Nguồn/kiểu đọc | Mức nhất quán cần hiểu |
|---|---|
| Đọc item từ bảng trong một Region | Mặc định eventually consistent; có thể yêu cầu strongly consistent trên thao tác hỗ trợ |
| Local secondary index (LSI) | Có thể hỗ trợ strongly consistent read |
| Global secondary index (GSI) | Đọc eventually consistent; không hỗ trợ ConsistentRead: true |
| Bản sao ở Region khác | Phụ thuộc chế độ global tables/cấu hình sao chép; không suy từ strong read ở Region này ra strong read toàn thế giới |

Từ “strongly consistent” cần luôn gắn với **đối tượng được đọc, Region và chế độ triển khai**. Nó không ngăn ứng dụng tạo lỗi lost update khi thực hiện GET rồi PUT không điều kiện.

### 7.3. Tạo mới giỏ hàng mà không ghi đè

~~~javascript
import { PutCommand } from "@aws-sdk/lib-dynamodb";

await client.send(new PutCommand({
  TableName: "LearningStore",
  Item: {
    PK: "USER#17",
    SK: "CART#CURRENT",
    items: [],
    updatedAt: new Date().toISOString()
  },
  ConditionExpression: "attribute_not_exists(PK)"
}));
~~~

Khi mục với cặp PK/SK đang được ghi đã tồn tại, điều kiện tạo mới không thỏa và yêu cầu thất bại. Hai yêu cầu cùng tạo **một item có cùng khóa chính** được điều phối ở điểm ghi điều kiện; không nên thay thế bằng “Get rồi Put”.

**Phạm vi:** Điều kiện được đánh giá đối với item đích trong bảng ở Region nhận yêu cầu. Nó không phải một ràng buộc duy nhất tổng quát đối với mọi thuộc tính khác, và không tự thay đổi quy tắc sao chép đa vùng.

Nếu yêu cầu tạo mới thất bại, ứng dụng cần phân biệt lỗi điều kiện không thỏa với lỗi quyền truy cập, throttling hoặc lỗi dịch vụ. Không nên retry vô hạn một yêu cầu chắc chắn đang tranh chấp cùng khóa.

## 8. DynamoDB: cập nhật nguyên tử có điều kiện

### 8.1. Ví dụ tồn kho không được âm

Giả sử item:

~~~json
{
  "PK": "STOCK#SKU-42",
  "SK": "WAREHOUSE#HCM",
  "available": 1,
  "version": 7
}
~~~

Hai khách cùng muốn mua một đơn vị. Cách sai:

~~~text
A đọc available = 1
B đọc available = 1
A ghi available = 0
B ghi available = 0
~~~

Hai lệnh ghi không điều kiện có thể đều thành công, khiến ứng dụng tạo hai đơn dù chỉ có một sản phẩm.

Thay vào đó, dùng **UpdateItem có ConditionExpression**, kết hợp kiểm tra và trừ trong cùng thao tác:

~~~javascript
import { UpdateCommand } from "@aws-sdk/lib-dynamodb";

await client.send(new UpdateCommand({
  TableName: "LearningStore",
  Key: {
    PK: "STOCK#SKU-42",
    SK: "WAREHOUSE#HCM"
  },
  UpdateExpression: "SET available = available - :one",
  ConditionExpression:
    "attribute_exists(PK) AND available >= :one",
  ExpressionAttributeValues: {
    ":one": 1
  },
  ReturnValues: "ALL_NEW"
}));
~~~

**Bảo đảm:** Trên item đích trong phạm vi thao tác DynamoDB này, nếu available không còn ít nhất 1 tại lúc đánh giá điều kiện, lệnh giảm thất bại; không có khoảng trống “đọc trước rồi ghi sau” của ứng dụng.

**Không tự được bảo đảm:** Việc giảm kho và **tạo đơn ở item khác** chưa tự cùng thành công. Nếu một thao tác được commit còn thao tác kia thất bại, phải dùng transaction nhiều item hoặc quy trình có trạng thái/đối soát phù hợp.

### 8.2. Phiên bản để ngăn ghi đè

Với một item giỏ hàng có version = 7, ứng dụng có thể yêu cầu:

~~~javascript
await client.send(new UpdateCommand({
  TableName: "LearningStore",
  Key: {
    PK: "USER#17",
    SK: "CART#CURRENT"
  },
  UpdateExpression:
    "SET items = :items, version = version + :one",
  ConditionExpression: "version = :expected",
  ExpressionAttributeValues: {
    ":items": [{ sku: "B01", qty: 2 }],
    ":one": 1,
    ":expected": 7
  }
}));
~~~

Nếu người khác đã cập nhật version từ 7 lên 8, thao tác của client dùng phiên bản cũ sẽ nhận lỗi điều kiện không thỏa. Khi đó client có thể đọc lại, áp dụng logic hợp nhất hoặc trả xung đột.

**Lưu ý:** Ví dụ giả sử thuộc tính version đã tồn tại dưới dạng số. Với item mới, cần khởi tạo version và quy tắc cập nhật rõ ràng. Một thao tác CAS trên một item không giải quyết bất biến trải qua nhiều item.

### 8.3. Atomicity khác với idempotency

Giả sử điều kiện trừ tồn kho đã được xử lý thành công nhưng response bị mất. Client retry cùng lệnh giảm thêm một đơn vị; nếu vẫn còn kho, lệnh thứ hai **cũng có thể thành công**.

Điều này không phải lỗi nguyên tử: mỗi lần trừ đã được áp dụng đúng. Lỗi là hai lần trừ cùng **một ý định mua**. Cần idempotency key hoặc trạng thái đặt hàng bảo đảm một sự kiện nghiệp vụ chỉ được áp dụng một lần theo thiết kế.

## 9. DynamoDB: giao dịch nhiều item

### 9.1. Đặt một ghế và tạo đơn đặt chỗ

Giả sử một ghế cho suất chiếu S1 có khóa:

~~~text
PK = SHOW#S1
SK = SEAT#A10
~~~

Một đặt chỗ dùng khóa:

~~~text
PK = BOOKING#B9001
SK = META
~~~

Để tránh ghi ghế đã có người giữ và đồng thời tạo bản ghi đặt chỗ, có thể dùng **TransactWriteItems**. Ví dụ:

~~~javascript
import { TransactWriteCommand } from "@aws-sdk/lib-dynamodb";

await client.send(new TransactWriteCommand({
  TransactItems: [
    {
      Put: {
        TableName: "LearningStore",
        Item: {
          PK: "SHOW#S1",
          SK: "SEAT#A10",
          bookingId: "B9001",
          state: "HELD"
        },
        ConditionExpression: "attribute_not_exists(PK)"
      }
    },
    {
      Put: {
        TableName: "LearningStore",
        Item: {
          PK: "BOOKING#B9001",
          SK: "META",
          seat: "A10",
          showId: "S1",
          state: "HELD"
        },
        ConditionExpression: "attribute_not_exists(PK)"
      }
    }
  ]
}));
~~~

**Bảo đảm theo phạm vi:** DynamoDB transaction cung cấp nhóm thao tác ghi theo tính chất nguyên tử trong phạm vi API, bảng, tài khoản/Region và giới hạn được hỗ trợ. Nếu điều kiện đặt ghế không thỏa, transaction không nên tạo riêng bản ghi booking từ lệnh Put thứ hai.

**Giới hạn cần nhớ:**

- Transaction có giới hạn về số thao tác, kích thước dữ liệu và cách truy cập item; không dùng để cập nhật vô hạn bản ghi.
- Không được mặc định transaction có thể bao trùm tài nguyên ở nhiều Region hay dịch vụ ngoài như cổng thanh toán.
- Khi dùng global tables, cách thay đổi được sao chép qua vùng và mức nhất quán liên vùng phụ thuộc chế độ global tables. Transaction trong một Region không tự biến một thao tác nhiều item thành snapshot nguyên tử có thể quan sát ngay ở mọi Region theo mọi chế độ.
- Nếu timeout, client phải xử lý khả năng transaction đã commit. API transaction có hỗ trợ các cơ chế client token/idempotency trong phạm vi thời gian và quy tắc của dịch vụ; cần hiểu giới hạn đó khi xây ứng dụng.

Ví dụ trên dùng hai mục đặt chỗ vĩnh viễn để tập trung vào bất biến “một ghế, một booking”. Trong ứng dụng thật cần thiết kế **hết hạn giữ chỗ**, thanh toán, hủy, hoàn tiền và chuyển trạng thái bằng điều kiện. Không chỉ thêm TTL rồi coi ghế sẽ tự được mở đúng lúc.

### 9.2. Tình huống cần thiết kế ngoài transaction

Giả sử ứng dụng cần:

1. Tạo booking.
2. Trừ tồn kho.
3. Gửi yêu cầu thanh toán tới nhà cung cấp bên ngoài.
4. Phát email xác nhận.

Transaction DynamoDB có thể phối hợp các thao tác item nằm trong phạm vi API nhưng không thể ép **cổng thanh toán và hệ thống email** cùng commit theo transaction đó.

Một giải pháp thực tế thường có:

- Trạng thái PENDING / RESERVED / PAID / FAILED / EXPIRED.
- Idempotency key cho lần yêu cầu thanh toán.
- Hàng đợi hoặc outbox cho sự kiện phát sinh sau commit.
- Cơ chế retry có giới hạn và đối soát trạng thái không rõ kết quả.
- Logic bù trừ khi không hoàn tất được toàn bộ quy trình.

Đây là thiết kế **quy trình nhiều bước**, không phải một thao tác key–value đơn lẻ.

## 10. DynamoDB: TTL không tương đương xóa đúng giờ

DynamoDB có tính năng TTL dựa trên thuộc tính thời gian hết hạn lưu dưới dạng số giây Unix epoch.

Ví dụ item:

~~~json
{
  "PK": "SESSION#T100",
  "SK": "META",
  "userId": "17",
  "expiresAt": 1795000000
}
~~~

Trong ví dụ, **expiresAt** là thuộc tính cấu hình làm TTL cho bảng. Giá trị chỉ minh họa một thời điểm; ứng dụng thực tế phải tính Unix epoch seconds từ thời gian hết hạn đã định.

**Bảo đảm:** Dịch vụ có thể nhận diện item đã hết hạn và xóa chúng **bất đồng bộ** theo cơ chế TTL nếu tính năng được bật và giá trị hợp lệ.

**Không được bảo đảm:**

- DynamoDB không cam kết xóa item chính xác tại thời điểm expiresAt. Item hết hạn có thể vẫn tồn tại và vẫn xuất hiện trong kết quả truy vấn/đọc trước khi tiến trình nền xóa.
- TTL không tự từ chối truy cập tới phiên đã hết hạn.
- TTL không phải hàng đợi tác vụ để kích hoạt xử lý nghiệp vụ đúng thời gian.

Vì thế, khi đọc phiên, ứng dụng cần kiểm tra expiresAt với thời gian hiện tại và **từ chối sử dụng khi đã quá hạn**, kể cả khi item vẫn còn trong bảng. Một lệnh update/đặt chỗ cũng cần điều kiện dựa trên trạng thái và thời gian nếu muốn bảo đảm không sử dụng item hết hiệu lực.

Sự khác biệt cốt lõi:

| Tính năng | Redis EX/PEXPIRE | DynamoDB TTL |
|---|---|---|
| Ý nghĩa thời hạn | Khóa hết hiệu lực để lệnh đọc xử lý như không tồn tại sau thời hạn | Đánh dấu item đủ điều kiện bị xóa nền |
| Việc thu dọn vật lý | Có thể thực hiện chủ động/thụ động; không phải đồng hồ callback chính xác | Xóa bất đồng bộ, không đúng hạn tức thời |
| Có thể dùng làm “lịch chạy tác vụ” không? | Không nên | Không nên |
| Phải kiểm tra quyền/trạng thái nghiệp vụ riêng? | Có | Có, đặc biệt với item hết hạn chưa bị xóa |

## 11. Ranh giới nhất quán và durability của DynamoDB

### 11.1. Read consistency trong một Region

DynamoDB hỗ trợ **eventually consistent read** và trong các trường hợp phù hợp **strongly consistent read**. Chọn chế độ đọc ảnh hưởng tới chi phí/tải và giá trị có thể quan sát.

Ví dụ:

~~~text
T1: Writer cập nhật CART của U17.
T2: Reader đọc bảng trong cùng Region.
~~~

Nếu đọc eventually consistent, một lần đọc ngay sau ghi có thể thấy giá trị cũ. Nếu dùng strongly consistent read trên đối tượng được hỗ trợ, DynamoDB cung cấp bảo đảm đọc mới nhất đã được xác nhận theo ngữ nghĩa dịch vụ **trong phạm vi đó**.

Tuy nhiên, hai client cùng đọc “giỏ trống”, rồi cùng ghi lại toàn bộ giỏ từ trạng thái cũ vẫn có thể gây lost update nếu các lệnh ghi không có điều kiện. Strong read **không thay thế** điều kiện cập nhật.

### 11.2. GSI là mô hình đọc khác

Giả sử ứng dụng tạo GSI để tìm đơn theo trạng thái và thời điểm:

~~~text
GSI-PK = ORDER_STATUS#PENDING
GSI-SK = createdAt
~~~

GSI giúp truy vấn theo một bộ khóa khác với primary key của bảng. Nhưng GSI được cập nhật bất đồng bộ và chỉ hỗ trợ đọc eventually consistent. Một item vừa đổi trạng thái có thể chưa xuất hiện hoặc chưa biến mất đúng lúc trong truy vấn GSI.

Nếu “một ghế không được đặt hai lần” là bất biến nghiêm ngặt, không nên thực hiện Query GSI để kiểm tra “không thấy ghế đang giữ” rồi ghi. Bảo vệ phải đặt vào item/khóa có điều kiện nguyên tử hoặc transaction phù hợp.

### 11.3. Global tables: không thể suy từ một Region ra mọi Region

DynamoDB có chức năng global tables để làm việc qua nhiều Region. Phạm vi bảo đảm khác nhau theo **chế độ triển khai và mức consistency** được hỗ trợ:

- Với cấu hình sao chép đa vùng **eventual consistency**, cập nhật không xuất hiện tức thì ở mọi Region; có thể xảy ra ghi cạnh tranh và cần quy tắc giải quyết xung đột.
- Những chế độ **multi-Region strong consistency** (nơi được hỗ trợ và cấu hình) có các hạn chế và đặc tính riêng về cách ghi/đọc, Region và tính sẵn sàng; không được coi mọi bảng toàn cầu là mạnh hoặc yếu như nhau.
- Transaction trong một Region và sao chép qua Region là **hai phạm vi bảo đảm khác nhau**. Cần đối chiếu yêu cầu nghiệp vụ với tài liệu của chế độ đang sử dụng.

Ví dụ, một username bắt buộc duy nhất toàn cầu không nên dựa vào điều kiện tạo **chỉ tại từng Region riêng lẻ** nếu cấu hình cho phép hai Region ghi độc lập mà không phối hợp mạnh trên cùng định danh.

### 11.4. Durability, backup và khôi phục

DynamoDB là dịch vụ lưu trữ được quản lý với cơ chế bền vững theo thiết kế sản phẩm. Nhưng **durability không đồng nghĩa có thể khôi phục mọi lỗi nghiệp vụ**:

- Lệnh xóa nhầm hợp lệ vẫn là một thay đổi hợp lệ.
- Bản ghi bị ứng dụng ghi sai có thể được sao chép giống như bản ghi đúng.
- Backup/PITR, nếu được sử dụng, có phạm vi và cửa sổ khôi phục riêng.
- Việc khôi phục một bảng không tự phối hợp trạng thái với cổng thanh toán hay dịch vụ bên ngoài.

Vì vậy cần chính sách sao lưu, phục hồi, kiểm toán và bảo vệ thao tác xóa tùy yêu cầu dữ liệu.

## 12. So sánh trực tiếp các tình huống nghiệp vụ

### 12.1. Phiên đăng nhập

| Yêu cầu | Redis | DynamoDB |
|---|---|---|
| Lấy phiên theo token | GET theo key | GetItem theo primary key |
| Hết hạn | EX/PEXPIRE; khóa hết hạn theo ngữ nghĩa Redis | expiresAt + TTL; ứng dụng phải kiểm tra thời hạn |
| Tạo chỉ khi chưa có | SET ... NX ... EX | PutItem + attribute_not_exists |
| Đọc mới nhất | Đọc primary trong phạm vi thích hợp; replica có thể trễ | Strong read khi API/đối tượng/Region hỗ trợ |
| Lưu bền vững | Phụ thuộc persistence/replication/failover | Lưu trữ bền vững theo dịch vụ; vẫn cần backup/quản lý vòng đời |

Không thể chọn Redis chỉ vì “nhanh”, hoặc DynamoDB chỉ vì “bền”, mà bỏ qua yêu cầu quyền truy cập, chi phí, độ mới, khối lượng dữ liệu và khả năng chấp nhận mất phiên.

### 12.2. Giữ username duy nhất

| Yêu cầu | Redis | DynamoDB |
|---|---|---|
| Khóa đại diện username | username:T1:alice | PK = USERNAME#T1#alice, SK = META |
| Tạo nguyên tử nếu chưa có | SET ... NX | PutItem ConditionExpression |
| Ghi hồ sơ người dùng riêng | Cần tự thiết kế tính nhất quán giữa hai khóa; một số lựa chọn phụ thuộc slot và phạm vi Redis | Có thể dùng TransactWriteItems cho nhiều item được hỗ trợ |
| Trên nhiều máy/vùng | Phải xét topology, replication, failover; SET NX một primary không tự bảo đảm toàn cầu | Phải xét bảng, Region và chế độ global tables |

### 12.3. Tồn kho và thanh toán

Đối với tồn kho, sự quan trọng không chỉ là tra cứu theo khóa SKU mà còn là:

1. Không bán âm tồn kho.
2. Không trừ hai lần do retry.
3. Gắn lần trừ với đúng đơn hàng.
4. Hoàn lại hoặc điều chỉnh theo quy trình hủy/hoàn tiền.

Redis có thể làm bộ đếm hoặc reservation tốc độ cao; DynamoDB có thể giữ trạng thái tồn kho bằng cập nhật có điều kiện và giao dịch nhiều item trong phạm vi hỗ trợ. Hệ thống thật cần chọn **nguồn dữ liệu có thẩm quyền**. Không nên đặt một bản Redis cache và một bản DynamoDB làm hai nguồn độc lập đều có quyền quyết định số lượng mà thiếu cơ chế đồng bộ/đối soát.

## 13. Mẫu thao tác an toàn theo vấn đề

| Vấn đề | Mẫu phù hợp | Phạm vi phải kiểm tra |
|---|---|---|
| Tạo một khóa duy nhất | Redis SET NX; DynamoDB conditional Put | Chính khóa đó, nơi thực thi, topology |
| Tăng/giảm một bộ đếm | Redis INCR/DECR; DynamoDB UpdateItem/ADD hoặc SET có điều kiện | Một khóa/item; xử lý retry riêng |
| Chống ghi đè phiên bản cũ | Redis WATCH hoặc script; DynamoDB condition trên version | Khóa/item và quy tắc thử lại |
| Ghi nhiều giá trị trong một tác vụ | Redis MULTI/EXEC hoặc script trong phạm vi hỗ trợ; DynamoDB transaction | Các khóa cùng slot nếu cần, hoặc tập item được giao dịch hỗ trợ |
| Xóa dữ liệu tạm thời | TTL theo sản phẩm | Ngữ nghĩa hết hạn, thu dọn vật lý, yêu cầu ứng dụng |
| Đếm sự kiện đúng một lần theo ID | Khóa idempotency kết hợp cập nhật nguyên tử | Cả ID sự kiện và tác dụng phụ phải có cùng phạm vi bảo vệ |
| Truy vấn bằng điều kiện khác khóa | Thiết kế tập khóa/index bổ sung hoặc dùng kho khác | Tính đồng bộ chỉ mục, chi phí ghi, độ mới |
| Đa vùng hoạt động | Chọn topology/chế độ consistency có chủ đích | Phạm vi phối hợp toàn vùng và xử lý xung đột |

## 14. Lỗi thường gặp khi áp dụng mô hình khóa–giá trị

### 14.1. “Một lệnh nguyên tử nên toàn bộ quy trình cũng nguyên tử”

Sai khi quy trình có nhiều lệnh hoặc nhiều dịch vụ. Ví dụ Redis INCR nguyên tử, nhưng INCR + ghi đơn vào SQL/DynamoDB không tạo transaction chung.

**Cách xử lý:** Xác định bất biến nào cần nằm trong một phạm vi giao dịch; dùng cơ chế nguyên tử thích hợp hoặc thiết kế quy trình bù trừ và đối soát.

### 14.2. “Đọc strongly consistent rồi ghi thì không còn race”

Hai client vẫn có thể đọc cùng giá trị trước khi bất kỳ client nào ghi. Lỗi **check-then-write** không biến mất.

**Cách xử lý:** Đưa điều kiện vào chính thao tác ghi, ví dụ DynamoDB ConditionExpression hoặc Redis WATCH/Lua theo phạm vi thích hợp.

### 14.3. “Có TTL nghĩa là hệ thống xóa đúng lúc và thực hiện công việc”

TTL không phải công cụ lập lịch bảo đảm thời điểm. DynamoDB còn có thể giữ item đã hết hạn trước khi xóa nền. Redis hết hạn theo ngữ nghĩa khóa, nhưng không gọi callback nghiệp vụ đúng hạn cho mọi sự cố.

**Cách xử lý:** Kiểm tra thời gian hiệu lực trong nghiệp vụ; dùng scheduler/queue phù hợp nếu cần phát hành công việc đúng quy trình.

### 14.4. “Cache có giá trị nên đây là nguồn sự thật”

Cache có thể giữ dữ liệu cũ hoặc mất dữ liệu. Khi cache miss, ứng dụng phải biết đọc ở đâu.

**Cách xử lý:** Xác định rõ nguồn có thẩm quyền, TTL, invalidation, đọc sau cập nhật và cách khôi phục khi cache mất.

### 14.5. “Thêm retry sẽ làm hệ thống chắc chắn hơn”

Retry vô điều kiện trên INCR hoặc trừ kho có thể nhân đôi tác dụng của một yêu cầu đã thành công nhưng mất response.

**Cách xử lý:** Sử dụng idempotency key, giao dịch/ghi điều kiện và cơ chế tra cứu kết quả theo ID ổn định.

### 14.6. “Một unique key trong một Region nghĩa là duy nhất toàn cầu”

Khi hai vùng ghi độc lập, chúng có thể cùng chấp nhận cùng một tên trong một cấu hình chỉ nhất quán cuối cùng.

**Cách xử lý:** Chỉ hứa tính duy nhất trong phạm vi có cơ chế phối hợp thực tế; chọn Region chủ, dịch vụ phân quyền cấp ID hoặc chế độ nhất quán đa vùng đáp ứng yêu cầu.

### 14.7. “Mọi truy vấn đều nhanh nếu lưu key–value”

Lấy item khi biết khóa có thể phù hợp, nhưng truy vấn “tìm mọi đơn trên 10 triệu đồng trong tháng trước” không tự được hỗ trợ hiệu quả bởi một ánh xạ key → value.

**Cách xử lý:** Liệt kê access pattern trước khi thiết kế khóa; bổ sung chỉ mục/tập khóa/materialized view hoặc kho phân tích thích hợp, với kế hoạch đồng bộ.

## 15. Bài tập thực hành

### Bài 1. Thiết kế phiên cho ứng dụng học tập

Yêu cầu:

- Mỗi token chỉ ánh xạ tới tối đa một phiên đang hiệu lực.
- Một phiên hết hạn sau 30 phút không hoạt động.
- Đăng xuất phải thu hồi phiên.
- Dữ liệu phiên không cần giữ mãi nếu Redis mất cache, nhưng không được cấp quyền cho phiên đã quá hạn.

Hãy:

1. Đề xuất cách đặt khóa và các lệnh Redis để tạo, đọc, cập nhật hoạt động và xóa phiên.
2. Giải thích SET NX EX bảo vệ điều gì và không bảo vệ điều gì.
3. Nếu cập nhật giá trị phiên bằng SET, phải làm gì để không vô tình bỏ TTL?
4. Cho biết có nên đọc phiên từ Redis replica khi yêu cầu thu hồi phiên cần có hiệu lực ngay không.

**Gợi ý:** Dùng token ngẫu nhiên làm một phần khóa, SET NX EX khi tạo, lệnh cập nhật TTL được định nghĩa rõ cho sliding expiration. Tránh phụ thuộc replica có thể trễ nếu yêu cầu thu hồi có độ mới nghiêm ngặt.

### Bài 2. Đếm lượt xem trong Redis

Ban đầu:

~~~redis
SET views:course-C1 5
~~~

Hai worker cùng ghi nhận một lượt xem mới. Hãy so sánh:

~~~text
Phương án A:
  GET views:course-C1
  SET views:course-C1 <oldValue + 1>

Phương án B:
  INCR views:course-C1
~~~

1. Vì sao phương án A có nguy cơ lost update?
2. Phương án B bảo đảm gì?
3. Nếu worker retry sau timeout, phương án B có bảo đảm mỗi sự kiện chỉ được đếm một lần không?
4. Đề xuất cách thêm eventId để chống xử lý lặp, chỉ rõ cần đặt điều kiện và cập nhật đếm trong cùng phạm vi nguyên tử.

### Bài 3. Chọn DynamoDB key cho giỏ hàng

Một ứng dụng muốn lấy:

- Giỏ hiện tại của user U17.
- Mười đơn gần nhất của U17.
- Chi tiết đơn O1001 khi đã biết orderId.

Hãy đề xuất một hoặc nhiều bảng/item type cùng PK/SK, nêu rõ truy vấn nào dùng GetItem, truy vấn nào dùng Query, và có cần thêm chỉ mục hoặc ánh xạ truy cập theo orderId hay không. Giải thích vì sao dữ liệu “đơn gần nhất” cần một thành phần khóa sắp xếp phù hợp và phân trang ổn định.

**Gợi ý một cách thiết kế:**

~~~text
PK = USER#U17, SK = CART#CURRENT
PK = USER#U17, SK = ORDER#<time>#<orderId>
~~~

Lấy chi tiết khi **chỉ biết orderId** có thể cần một mục tra cứu riêng hoặc một bảng theo orderId, tùy access pattern. Không mặc định Query theo một trường không thuộc key sẽ hiệu quả.

### Bài 4. Giữ ghế trong DynamoDB

Chỉ có một ghế A10 cho suất S1, hai khách muốn giữ cùng lúc:

1. Đề xuất một khóa chính biểu diễn ghế.
2. Viết ý tưởng conditional Put để chỉ một người giữ được ghế.
3. Nếu cần tạo booking item đồng thời, chọn API nào?
4. Nếu ghế giữ trong năm phút, vì sao chỉ dựa vào DynamoDB TTL là chưa đủ để quyết định có cho khách khác đặt?
5. Nếu client timeout sau khi booking thành công, làm sao tránh tạo booking thứ hai khi retry?

**Gợi ý:** Điều kiện tại điểm ghi bảo vệ ghế; transaction bảo vệ hai item trong phạm vi hỗ trợ; trạng thái giữ chỗ và expiresAt phải được kiểm tra ở thao tác ghi; idempotency key giúp nhận diện cùng một yêu cầu.

### Bài 5. Xác định phạm vi bảo đảm

Xét bốn khẳng định:

1. “Redis INCR nguyên tử, nên request retry không thể đếm trùng.”
2. “DynamoDB GetItem với ConsistentRead true trên bảng ở Region A có thể dùng để khẳng định dữ liệu ngay ở GSI và Region B cũng đã cập nhật.”
3. “DynamoDB TTL đến hạn nên item chắc chắn đã bị xóa khỏi bảng.”
4. “Redis SET NX PX giúp cạnh tranh một khóa trên primary đang xử lý, nhưng cần thêm phân tích về lease, failover và tác động bên ngoài nếu dùng làm distributed lock.”

Hãy đánh giá từng khẳng định, xác định **đối tượng, thời điểm và phạm vi triển khai** mà nó nói đến.

**Gợi ý:** Các câu 1–3 kết luận vượt quá phạm vi bảo đảm được nêu trong bài. Câu 4 phân biệt đúng tính nguyên tử của một lệnh với tính an toàn của cả hệ thống phân tán.

## 16. Bộ câu hỏi để chọn Redis hay DynamoDB trong thực tế

Trước khi quyết định công nghệ, nhóm nên ghi thành bảng:

| Câu hỏi | Ý nghĩa quyết định |
|---|---|
| Dữ liệu có phải nguồn thẩm quyền không? | Cache và dữ liệu nghiệp vụ cốt lõi cần chính sách durability khác nhau |
| Mẫu truy vấn bắt đầu từ khóa nào? | Cần xác định khả năng truy cập theo PK/SK và những đường đọc bổ sung |
| Tần suất đọc/ghi và kích thước value/item? | Ảnh hưởng thông lượng, chi phí, giới hạn kỹ thuật và phân vùng |
| Có nhiều tác nhân cập nhật cùng một khóa không? | Cần INCR, CAS, conditional update hoặc transaction |
| Có bất biến trên nhiều khóa không? | Phải xác định phạm vi giao dịch và phương án phục hồi |
| Độ mới chấp nhận được bao nhiêu? | Ảnh hưởng việc chọn primary/replica, eventual/strong read và cache |
| Cần hết hạn logic hay xóa vật lý đúng giờ? | TTL thường không thay thế kiểm tra thời gian hoặc scheduler |
| Có nhiều Region ghi cùng lúc không? | Cần xác định chế độ consistency và cơ chế xử lý conflict |
| Có retry hoặc xử lý sự kiện lặp không? | Idempotency phải được thiết kế riêng với atomicity |
| Dữ liệu tồn tại bao lâu và khôi phục thế nào? | Cần persistence, backup, retention, kiểm toán và khôi phục |

**Ví dụ ra quyết định:** Với phiên ứng dụng có thể tái tạo và mất cache chỉ khiến người dùng đăng nhập lại, Redis có thể phù hợp nếu đã chấp nhận rõ các rủi ro về persistence/failover. Với hồ sơ đơn hàng cần lưu lâu dài, truy cập theo khóa, bảo đảm điều kiện ghi và khả năng khôi phục theo chính sách, DynamoDB có thể phù hợp. Nếu cần các truy vấn phân tích phức tạp qua nhiều trường, phải cân nhắc mô hình đọc bổ sung hoặc hệ dữ liệu khác.

## 17. Tóm tắt kiến thức

Mô hình khóa–giá trị giúp định địa chỉ dữ liệu bằng khóa và thực hiện những thao tác đơn giản, hiệu quả. Khi chuyển từ ví dụ nhỏ sang ứng dụng thật, **bảo đảm không nằm ở tên mô hình mà ở thao tác, phạm vi dữ liệu và cấu hình triển khai cụ thể**.

Các điểm cần ghi nhớ:

1. **Redis SET NX EX** tạo có điều kiện và gắn TTL nguyên tử tại Redis xử lý lệnh; không tự bảo đảm durable replication hoặc distributed lock an toàn dưới mọi sự cố.
2. **Redis INCR** cập nhật một bộ đếm nguyên tử; nếu cùng yêu cầu bị retry, bộ đếm vẫn có thể tăng trùng nếu không có idempotency.
3. **Redis MULTI/EXEC, WATCH và Lua** giải quyết những dạng phối hợp nhất định nhưng có giới hạn thực thi, phân vùng và rollback.
4. **DynamoDB conditional Put/Update** bảo vệ điều kiện tại thời điểm ghi đối với item đích; Get rồi Put không thay thế được.
5. **DynamoDB TransactWriteItems** hỗ trợ giao dịch nhiều item trong phạm vi dịch vụ quy định, không bao gồm tự động các tác dụng phụ ở dịch vụ ngoài hoặc mọi Region.
6. **DynamoDB read consistency** phụ thuộc bảng, LSI/GSI, Region và chế độ global tables; strong read trên một đối tượng không có nghĩa toàn hệ thống luôn mạnh.
7. **TTL của hai hệ không có cùng ngữ nghĩa**, và không thể thay thế quy tắc kiểm tra thời gian hiệu lực của nghiệp vụ.

Với mọi câu khẳng định như “nguyên tử”, “duy nhất”, “nhất quán” hay “bền vững”, hãy luôn hỏi tiếp: **trên khóa nào, qua thao tác nào, tại máy chủ/Region nào, với cấu hình nào, và trong tình huống sự cố nào?**
