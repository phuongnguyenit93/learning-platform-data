# TTL, hết hạn dữ liệu và khác biệt với chính sách loại bỏ khỏi bộ nhớ

Trong mô hình **khóa–giá trị (key–value)**, ứng dụng thường lưu một giá trị dưới một khóa như `cache:product:42`, `session:user:7` hoặc `rate-limit:client:15`. Một số giá trị chỉ hữu ích trong một khoảng thời gian: kết quả truy vấn được cache trong 5 phút, mã xác thực có hiệu lực 2 phút hoặc một dấu đánh dấu xử lý trùng chỉ cần tồn tại trong một ngày.

**TTL (time to live)** mô tả thời gian giá trị được phép tồn tại hoặc được coi là còn hiệu lực. **Expiration (hết hạn)** là việc hệ thống coi dữ liệu đã vượt thời hạn đó là không còn sử dụng được. **Eviction (loại bỏ khỏi bộ nhớ)** lại là quyết định thu hồi tài nguyên khi cần chỗ cho dữ liệu khác, kể cả khi khóa chưa hết hạn.

Ba ý này liên quan nhưng không đồng nghĩa. Hiểu rõ sự khác nhau giúp tránh những lỗi như cache biến mất trước dự kiến, phiên đăng nhập còn được chấp nhận quá lâu, hệ thống ngừng ghi do đầy bộ nhớ, hoặc dùng TTL làm cơ chế xóa dữ liệu vĩnh viễn nhưng dữ liệu vẫn còn trong bản sao lưu.

> Ví dụ xuyên suốt: một ứng dụng bán hàng lưu chi tiết sản phẩm có thể tái tạo từ cơ sở dữ liệu chính vào kho key–value như Redis. Mỗi khóa cache được đặt TTL 300 giây. Khi người dùng truy cập, ứng dụng trả giá trị cache nếu còn hiệu lực; nếu không, ứng dụng đọc nguồn chính rồi tạo cache mới.

## 1. TTL quy định vòng đời logic của một khóa

Một mục dữ liệu có TTL thường gắn với **thời điểm hết hạn (expiration deadline)**. Nếu đặt tại thời điểm `t0` với TTL `T`, thời điểm hết hạn dự kiến là:

\[
t_{expire}=t_0+T
\]

Ví dụ lúc 10:00:00, ứng dụng đặt khóa `cache:product:42` với TTL 300 giây:

~~~text
10:00:00    SET cache:product:42 = {...}, TTL = 300 giây
10:01:30    Đọc khóa: còn hiệu lực, còn khoảng 210 giây
10:04:59    Đọc khóa: còn hiệu lực, còn khoảng 1 giây
10:05:00    Khóa đạt thời hạn; đọc sau đó được coi là không còn giá trị
~~~

Trong nhiều hệ key–value, khi khóa đã hết hạn, lệnh đọc sẽ ứng xử như thể khóa **không tồn tại**, mặc dù việc thu hồi bộ nhớ vật lý có thể diễn ra muộn hơn. Chi tiết phụ thuộc vào sản phẩm, cấu hình và kiểu dữ liệu.

Các đặc điểm quan trọng của TTL:

- **Có giới hạn thời gian:** thường đặt bằng giây, mili giây hoặc một timestamp tuyệt đối, tùy API.
- **Gắn với dữ liệu hoặc đối tượng được quản lý:** nhiều hệ thống đặt TTL cho cả key/item; một số hỗ trợ mức trường/cột riêng. Không mặc định mọi kho hỗ trợ TTL theo cùng mức.
- **Có thể thay đổi:** cập nhật TTL, làm mới TTL, bỏ TTL hoặc ghi đè giá trị là thao tác cần được định nghĩa rõ.
- **Không phải cam kết dữ liệu sẽ luôn có mặt cho đến lúc hết hạn:** khóa có thể bị xóa chủ động, bị eviction, bị ghi đè, hoặc không còn sau lỗi vận hành.
- **Không phải cam kết xóa vật lý đúng vào thời điểm hết hạn:** cơ chế dọn dẹp và loại bỏ khỏi bộ nhớ/đĩa có thể trì hoãn.

### 1.1. Phân biệt thời điểm hết hạn với thời điểm bị thu hồi

Hãy nhìn vào hai mốc sau:

~~~text
Tạo key                 Hết hạn về logic            Dọn bộ nhớ vật lý
  |                           |                           |
  v                           v                           v
10:00:00 ----------------- 10:05:00 ------------------- 10:05:06
  Đọc thành công (nếu key chưa bị xóa/evict)     Đọc coi là không tồn tại
~~~

**10:05:00** là thời điểm dữ liệu không còn hợp lệ theo TTL. **10:05:06** chỉ là một ví dụ khi bộ nhớ được thu hồi. Hệ thống có thể dọn sớm hơn hoặc muộn hơn tùy cơ chế và tải.

Nếu đang giữ dữ liệu có yêu cầu chính xác về thời gian hiệu lực, ứng dụng không được chỉ dựa vào suy đoán “đã dọn khỏi RAM hay chưa”. Cần kiểm tra trạng thái hết hạn theo hợp đồng của kho hoặc kiểm tra mốc `expiresAt` tại lớp nghiệp vụ.

## 2. Expiration khác eviction như thế nào?

Giả sử khóa được tạo lúc 10:00 với TTL 5 phút nhưng bộ nhớ Redis đầy lúc 10:02. Nếu chính sách eviction chọn khóa này, nó biến mất **trước 10:05**. Người dùng nhận cache miss tại 10:02, dù TTL ban đầu còn ba phút.

| Thuộc tính | **Expiration / TTL** | **Eviction / loại bỏ khỏi bộ nhớ** |
| --- | --- | --- |
| Mục đích | Kết thúc thời gian hiệu lực hoặc vòng đời theo quy tắc đã đặt | Thu hồi chỗ chứa/tài nguyên khi đạt ngưỡng |
| Nguyên nhân chính | Đã đến deadline | Áp lực bộ nhớ/giới hạn dung lượng và eviction policy |
| Có thể xảy ra trước TTL? | Không, nếu chỉ xét hết hạn theo deadline hiện tại | **Có**, nếu khóa đủ điều kiện để bị evict |
| Khóa không được đặt TTL | Thông thường không tự hết hạn vì TTL | **Có thể** bị evict nếu chính sách cho phép chọn mọi khóa |
| Quyết định chọn khóa | Theo thời hạn mà ứng dụng/hệ thống đã thiết lập | Theo chính sách, ví dụ LRU, LFU, random hoặc TTL gần nhất |
| Đọc sau khi khóa không còn | Thường nhận miss/không tìm thấy | Thường nhận miss/không tìm thấy |
| Có thể dựa vào đó để bảo đảm dữ liệu tồn tại? | **Không**; TTL không ngăn xóa sớm hay lỗi | **Không**; eviction chủ đích làm mất giá trị được lưu tạm |
| Ứng dụng cần làm gì? | Xác định deadline và cách làm mới đúng nghiệp vụ | Có đường xử lý miss, giới hạn tải và theo dõi sức chứa |

Hai hiện tượng có thể cùng xảy ra trên một khóa, nhưng **lý do biến mất khác nhau**. Trong Redis, các chỉ số `expired_keys` và `evicted_keys` giúp phân biệt xu hướng hết hạn với xu hướng bị loại bỏ bởi chính sách bộ nhớ; đây là những bộ đếm, không phải lịch sử chi tiết của từng khóa.

### 2.1. Thêm hai hành động dễ bị nhầm

**Invalidation** là ứng dụng chủ động vô hiệu hóa cache vì dữ liệu gốc thay đổi. Ví dụ sau khi cập nhật giá sản phẩm ở kho chính, ứng dụng xóa `cache:product:42`. Đây là thao tác **do thay đổi nghiệp vụ**, không phải do hết TTL hay do đầy bộ nhớ.

**Explicit deletion** là lệnh xóa trực tiếp, có thể vì người dùng yêu cầu, nghiệp vụ hủy phiên, quản trị viên xóa dữ liệu hoặc một tiến trình dọn dẹp. Dù kết quả đọc có thể đều là “không thấy khóa”, hệ thống phải theo dõi nguyên nhân để xử lý chính xác.

~~~mermaid
flowchart TD
    K["Key tồn tại"] --> T{"Đã đến thời hạn TTL?"}
    T -->|Có| X["Hết hạn về logic: cache miss"]
    T -->|Chưa| M{"Bộ nhớ cần thu hồi?"}
    M -->|Có, policy chọn key| E["Eviction: cache miss trước TTL"]
    M -->|Không| V{"Ứng dụng có invalidation / delete?"}
    V -->|Có| D["Bị xóa chủ động: cache miss"]
    V -->|Không| H["Key tiếp tục phục vụ đọc"]
~~~

Sơ đồ là mô hình khái niệm. Trên thực tế các kiểm tra có thể được thực hiện tại những thời điểm khác nhau và không nhất thiết theo đúng thứ tự như hình.

## 3. Các cách đặt thời gian sống

### 3.1. Fixed TTL: hết hạn sau thời gian cố định

TTL được tính từ lúc ghi hoặc lúc đặt thời hạn. Đọc không làm thay đổi deadline.

~~~text
10:00  Tạo cache, TTL = 10 phút
10:06  Đọc cache, vẫn hết hạn lúc 10:10
10:09  Đọc cache, vẫn hết hạn lúc 10:10
10:10  Cache hết hạn
~~~

Đây là lựa chọn thường gặp khi một kết quả có thể chấp nhận cũ tối đa một khoảng thời gian tính từ lần lấy dữ liệu. Cần nhớ rằng một thao tác ghi đè hay gia hạn TTL sẽ tạo ra deadline mới.

### 3.2. Sliding TTL / idle timeout: làm mới sau hoạt động

Mỗi lần truy cập hợp lệ có thể đẩy thời hạn ra xa:

~~~text
10:00  Tạo session, idle timeout = 30 phút → hạn 10:30
10:20  Hoạt động hợp lệ → hạn mới 10:50
10:45  Hoạt động hợp lệ → hạn mới 11:15
11:15  Không có hoạt động tiếp theo → hết hạn
~~~

Sliding TTL phù hợp khi muốn kết thúc phiên sau một khoảng **không hoạt động**, nhưng cần định nghĩa thế nào là hoạt động: đọc API tự động từ background có tính là tương tác hay không? Có làm mới TTL mỗi request hay chỉ mỗi vài phút để tránh ghi metadata quá thường xuyên?

**Idle timeout không thay thế absolute lifetime.** Một phiên dùng liên tục có thể được kéo dài mãi nếu chỉ có sliding TTL. Với phiên có yêu cầu giới hạn thời gian tối đa, cần kiểm tra thêm `absoluteExpiresAt` do hệ thống có thẩm quyền quyết định.

### 3.3. Deadline tuyệt đối

Thay vì nói “còn 600 giây kể từ bây giờ”, ứng dụng có thể định nghĩa:

~~~text
expiresAt = 2026-11-14T10:30:00Z
~~~

Deadline tuyệt đối hữu ích khi thời hạn gắn với một sự kiện nghiệp vụ: vé khuyến mãi hết hạn lúc 10:30, token phải vô hiệu sau mốc đã phát hành, hoặc một phiên không được tồn tại quá 8 giờ kể từ lúc đăng nhập.

Thời gian hệ thống, vùng giờ và độ lệch đồng hồ cần được xử lý có chủ đích. Nên dùng một chuẩn lưu mốc thời gian, chẳng hạn UTC, và tránh lấy thời gian từ client làm mốc quyết định bảo mật.

### 3.4. TTL theo từng bản ghi, không mặc định theo từng trường

Trong một kho key–value như Redis, TTL thông thường được gắn với **key**. Một hash gồm nhiều field có thể được lưu cùng một key; không nên mặc định mỗi field có TTL độc lập trên mọi phiên bản/cấu hình. Một số phiên bản hoặc sản phẩm có tính năng TTL cấp field/item riêng, nhưng cần kiểm tra API và giới hạn được hỗ trợ.

Ví dụ:

~~~text
Key: session:user:7
Value:
  lastSeen = ...
  device = ...
  permissions = ...
TTL của key: 1800 giây
~~~

Nếu yêu cầu `permissions` phải làm mới sau 1 phút trong khi `device` cần giữ 30 phút, một TTL chung cho cả key có thể không diễn đạt đúng nghiệp vụ. Có thể tách khóa, lưu `expiresAt` theo trường và kiểm tra trong ứng dụng, hoặc chọn cơ chế có hỗ trợ hạn dùng cấp field thật sự.

## 4. Hết hạn logic và cơ chế xóa vật lý trong NoSQL

Việc đặt TTL không nói lên lúc nào bộ nhớ/đĩa sẽ được thu hồi. Các hệ thống có thể thực thi hạn dùng bằng những chiến lược khác nhau.

### 4.1. Passive expiration / lazy expiration

Khi một lệnh truy cập khóa, hệ thống kiểm tra deadline. Nếu khóa đã hết hạn, hệ thống coi đó là miss và có thể dọn khóa ngay tại thời điểm truy cập.

Ưu điểm là không phải quét toàn bộ tập khóa liên tục. Nhược điểm là các khóa không được truy cập có thể còn chiếm tài nguyên cho tới khi một cơ chế dọn dẹp khác xử lý.

### 4.2. Active expiration / background cleanup

Hệ thống chủ động tìm và dọn các khóa hết hạn bằng công việc nền, lấy mẫu hoặc quét dữ liệu. Cách làm này giúp thu hồi bộ nhớ của những khóa không còn ai truy cập, nhưng thường **không phải lịch chạy chính xác tới từng mili giây cho từng khóa**.

Redis kết hợp kiểm tra hết hạn khi truy cập với cơ chế dọn chủ động. Vì thế một khóa đã hết hạn có thể **không được trả về khi đọc** dù dữ liệu vật lý của nó chưa bị thu hồi tại chính thời điểm hết hạn.

### 4.3. TTL ở các kho dữ liệu khác

Không phải hệ NoSQL nào cũng có cơ chế TTL như một cache trong RAM:

- **DynamoDB TTL:** một mục có thể mang thuộc tính thời gian hết hạn dạng Unix epoch tính bằng giây. Việc xóa vật lý là quá trình bất đồng bộ; mục đã qua deadline có thể còn xuất hiện trong truy vấn trước khi bị xóa. Nếu ứng dụng yêu cầu không trả mục hết hạn, phải tự kiểm tra/filter hạn dùng.
- **Cassandra TTL:** dữ liệu có hạn dùng sẽ trở thành dữ liệu hết hiệu lực theo cơ chế lưu trữ của Cassandra; thông tin xóa/tombstone và việc compaction ảnh hưởng đến lúc dung lượng đĩa được thu hồi. TTL và tombstone phải được tính vào thiết kế tải đọc/ghi và vận hành.
- **Redis:** thường phục vụ cache key–value với TTL ở key; việc kiểm tra deadline trên đường đọc và cơ chế dọn trong bộ nhớ khác với xóa bất đồng bộ của các kho lưu trữ bền vững.

Điểm chung cần nhớ là **deadline của dữ liệu, sự hiện diện trong kết quả đọc và thời điểm giải phóng dung lượng** có thể là ba điều khác nhau. Khi dùng TTL của một sản phẩm cụ thể, phải đọc đúng hợp đồng về đơn vị thời gian, tính nhất quán đọc, tác động đến replica, backup và khả năng kiểm tra hạn dùng.

## 5. Thực hành TTL trên Redis

Redis là ví dụ dễ quan sát để học phân biệt TTL với eviction. Các lệnh dưới đây minh họa Redis CLI; thời gian còn lại hiển thị có thể thay đổi giữa những lần chạy.

### 5.1. Tạo key có TTL ngay trong lệnh ghi

~~~redis
SET cache:product:42 "{\"id\":42,\"name\":\"Ban go\"}" EX 300
GET cache:product:42
TTL cache:product:42
PTTL cache:product:42
~~~

- `EX 300`: đặt hạn dùng sau 300 giây.
- `PX 300000`: có thể đặt tương đương bằng mili giây.
- `TTL key`: trả thời gian còn lại theo giây.
- `PTTL key`: trả thời gian còn lại theo mili giây.

Nên đặt giá trị và TTL **trong cùng một thao tác nguyên tử** khi ứng dụng yêu cầu khóa không bao giờ tồn tại mà thiếu hạn dùng. Nếu làm:

~~~redis
SET temp:job:81 "processing"
EXPIRE temp:job:81 60
~~~

thì tiến trình có thể chết giữa hai lệnh và để lại một khóa không có TTL. Với chuỗi Redis, dùng `SET ... EX` hoặc `SET ... PX` tránh khoảng hở này cho trường hợp ghi mới.

### 5.2. Đọc kết quả TTL

| Lệnh | Ý nghĩa kết quả |
| --- | --- |
| `TTL existing-expiring-key` | Số giây còn lại; không nhất thiết đúng chính xác giá trị ban đầu vì thời gian đã trôi |
| `TTL existing-no-expiry-key` | `-1`: khóa tồn tại nhưng không có expiration |
| `TTL missing-key` | `-2`: khóa không tồn tại hoặc đã hết hạn |
| `PTTL key` | Tương tự `TTL`, nhưng thời gian còn lại đo bằng mili giây |

Ví dụ:

~~~redis
SET demo:ttl "value" EX 120
TTL demo:ttl

PERSIST demo:ttl
TTL demo:ttl

DEL demo:ttl
TTL demo:ttl
~~~

Sau `PERSIST`, `TTL` cho `-1` nếu khóa còn tồn tại; sau `DEL`, `TTL` cho `-2`. Các lệnh tự trả giá trị thành công/thất bại theo trạng thái khóa tại lúc thực thi.

### 5.3. Ghi đè giá trị có thể làm thay đổi TTL

Một sai sót phổ biến là cập nhật giá trị cache bằng `SET` thông thường rồi cho rằng TTL cũ vẫn còn. Với Redis, `SET key value` mặc định **xóa TTL hiện có**; nếu cần giữ TTL, phải dùng tùy chọn phù hợp như `KEEPTTL` khi được hỗ trợ.

~~~redis
SET cache:product:42 "version-1" EX 60
SET cache:product:42 "version-2"
TTL cache:product:42
~~~

Ở ví dụ này, TTL được xóa và khóa có thể tồn tại không giới hạn nếu không bị xóa hoặc eviction. Khi muốn vừa cập nhật giá trị vừa đặt thời hạn mới:

~~~redis
SET cache:product:42 "version-3" EX 60
~~~

Khi muốn cập nhật giá trị mà vẫn giữ deadline cũ:

~~~redis
SET cache:product:42 "version-4" KEEPTTL
~~~

Các lệnh thay đổi trường bên trong một cấu trúc dữ liệu có thể có ngữ nghĩa TTL khác thao tác thay hẳn key. Không nên ngoại suy quy tắc của `SET` cho mọi lệnh.

### 5.4. Gia hạn, rút ngắn hoặc bỏ hạn dùng

~~~redis
EXPIRE session:7 1800
PEXPIRE session:7 1800000
PERSIST session:7
DEL session:7
~~~

Các lệnh này có ý nghĩa khác nhau:

- `EXPIRE` / `PEXPIRE` đặt thời hạn tương đối mới cho khóa.
- `PERSIST` bỏ deadline mà giữ giá trị.
- `DEL` xóa khóa.

Không nên gọi `EXPIRE` khi mỗi request đi qua chỉ vì đã có TTL: đó là thay đổi từ fixed TTL sang sliding TTL và có thể khiến khóa sống lâu hơn dự kiến.

Với các giá trị chuỗi, Redis hỗ trợ `GETEX key EX seconds` để đọc đồng thời làm mới TTL trong một thao tác. Dùng cơ chế này khi nghiệp vụ thực sự muốn gia hạn theo hoạt động, đồng thời kiểm tra giới hạn sống tối đa độc lập nếu cần.

### 5.5. Thời gian của Redis và đồng hồ

Redis lưu thời hạn hết hạn theo thời điểm tuyệt đối ở độ phân giải mili giây. Lệnh đặt TTL tương đối được quy đổi thành deadline tại thời điểm xử lý. Đồng hồ hệ thống thay đổi bất thường có thể ảnh hưởng đến việc hết hạn, nhất là khi di chuyển dữ liệu giữa máy có đồng hồ sai. Cần đồng bộ thời gian máy chủ và không mặc định một lệnh dọn dẹp xảy ra đúng mili giây chỉ vì TTL được tính theo mili giây.

## 6. Chính sách eviction khi bộ nhớ đạt giới hạn

Trong Redis, `maxmemory` quy định ngưỡng bộ nhớ dùng cho chính sách giới hạn; `maxmemory-policy` quyết định Redis làm gì khi một thao tác cần thêm bộ nhớ vượt mức giới hạn. Cấu hình được áp dụng trong phạm vi instance/node theo cách Redis triển khai, không phải một “TTL chung cho cả cụm”.

Các nhóm chính sách phổ biến:

| Chính sách Redis | Khóa có thể được chọn | Nguyên tắc lựa chọn |
| --- | --- | --- |
| `noeviction` | Không chủ động evict theo policy này | Các thao tác cần thêm bộ nhớ có thể bị từ chối khi chạm giới hạn |
| `allkeys-lru` | Mọi key | Ưu tiên key được dùng ít gần đây theo cơ chế LRU xấp xỉ |
| `allkeys-lfu` | Mọi key | Ưu tiên key có tần suất dùng thấp theo cơ chế LFU xấp xỉ |
| `allkeys-random` | Mọi key | Chọn ngẫu nhiên |
| `volatile-lru` | Chỉ key **có expiration** | LRU xấp xỉ trong tập key đủ điều kiện |
| `volatile-lfu` | Chỉ key **có expiration** | LFU xấp xỉ trong tập key đủ điều kiện |
| `volatile-random` | Chỉ key **có expiration** | Chọn ngẫu nhiên trong tập key đủ điều kiện |
| `volatile-ttl` | Chỉ key **có expiration** | Ưu tiên những key có thời gian sống còn lại ngắn hơn |

Các chính sách LRU/LFU của Redis dùng cơ chế lấy mẫu/xấp xỉ, không có nghĩa Redis duy trì một bảng xếp hạng tuyệt đối chính xác cho từng key ở mọi thời điểm. Kết quả eviction phụ thuộc tập ứng viên, thời điểm lấy mẫu và cấu hình.

### 6.1. `allkeys-*` khác `volatile-*`

`allkeys-*` có thể evict cả những khóa **không có TTL**. Nếu một key là dữ liệu nghiệp vụ duy nhất, không thể tái tạo, dùng nó chung instance với cache chịu `allkeys-lru` sẽ có nguy cơ mất giá trị không mong muốn.

`volatile-*` chỉ xét những key có expiration. Điều này **không bảo đảm hệ thống không bao giờ thiếu bộ nhớ**: nếu không còn key đủ điều kiện hoặc việc giải phóng không đủ, một thao tác ghi cần thêm bộ nhớ có thể bị từ chối.

Vì thế, “dùng volatile policy để bảo vệ key quan trọng” chưa đủ để biến Redis thành kho lưu trữ bền vững. Phải thiết kế persistence, replication, backup, recovery và tách workload khi có dữ liệu phải giữ lâu dài.

### 6.2. `volatile-ttl` không đồng nghĩa với expiration

Giả sử lúc 10:01, còn ba key:

~~~text
cache:A → còn 15 giây
cache:B → còn 120 giây
cache:C → không đặt TTL
~~~

Khi chịu áp lực bộ nhớ với `volatile-ttl`, Redis thiên về chọn các key có TTL còn ngắn như `cache:A` để **evict sớm**, ngay cả khi A vẫn còn hợp lệ. `cache:C` không nằm trong tập ứng viên của policy này. Đó là **eviction dùng TTL làm tín hiệu ưu tiên**, chứ không phải “chỉ xóa các key đã hết hạn”.

### 6.3. `noeviction` vẫn không có nghĩa khóa không hết hạn

`noeviction` chỉ nói Redis không chủ động thu hồi key theo eviction policy khi cần bộ nhớ. Những key có TTL vẫn **hết hạn theo deadline** và có thể được dọn đi.

Nếu dùng `noeviction` và bộ nhớ đầy, Redis có thể từ chối thao tác ghi cần thêm bộ nhớ, trong khi một số thao tác đọc vẫn hoạt động. Đây là một kiểu lỗi cần được kiểm soát, nhất là với session, counter hoặc dịch vụ ghi có yêu cầu availability cao.

### 6.4. Kiểm tra cấu hình

Các lệnh tham khảo:

~~~redis
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
INFO memory
INFO stats
~~~

Không nên thay cấu hình eviction trên production chỉ để thử nghiệm. Hãy tạo môi trường kiểm chứng có giới hạn và kiểm soát lượng dữ liệu; chọn chính sách dựa vào việc **những giá trị nào có thể tái tạo và hệ thống sẽ xử lý ra sao nếu chúng biến mất**.

## 7. TTL không ngăn được cache miss và mất tính nhất quán

Trong mô hình key–value cache, TTL có hai mục đích thường bị gộp:

- **Giới hạn độ cũ có thể chấp nhận** của một giá trị cache trong khoảng mà chính sách cache cho phép.
- **Cho hệ thống cơ hội dọn giá trị không còn hữu ích** mà không cần xóa thủ công từng khóa.

TTL không cung cấp tính nhất quán với kho dữ liệu gốc. Một giá trị vẫn còn trong TTL nhưng đã sai ngay sau khi nguồn chính được cập nhật.

### 7.1. Cache-aside và invalidation

~~~mermaid
flowchart LR
    A["API đọc sản phẩm"] --> C[("Key–value cache")]
    C -->|"Hit, còn hạn"| A
    C -->|"Miss: hết hạn, evicted hoặc bị xóa"| P[("Primary store")]
    P -->|"Dữ liệu mới nhất theo hợp đồng nguồn"| A
    P -->|"SET ... EX"| C
    W["API cập nhật giá"] --> P
    W -->|"Sau ghi thành công: invalidation"| C
~~~

Pseudocode:

~~~text
getProduct(productId):
    value = cache.get("product:" + productId)
    if value != null:
        return value

    value = primaryStore.getProduct(productId)
    if value != null:
        cache.set("product:" + productId, value, ttl=300s)
    return value

updatePrice(productId, newPrice):
    primaryStore.updatePrice(productId, newPrice)
    cache.delete("product:" + productId)
~~~

Với cache-aside, việc cập nhật kho chính và xóa cache thường **không nằm trong một giao dịch nguyên tử chung**. Có thể xảy ra trường hợp sau:

~~~text
R1: Cache miss, đọc giá cũ từ primary.
W : Ghi giá mới vào primary.
W : Xóa cache thành công.
R1: Ghi lại giá cũ vừa đọc vào cache với TTL 300 giây.
R2: Đọc cache và thấy giá cũ.
~~~

Đây là **race giữa đọc/làm đầy cache và ghi/invalidation**, TTL chỉ giới hạn thời gian giá trị cũ có thể tiếp tục nằm trong cache. Tùy mức nhất quán cần thiết, có thể dùng version trong giá trị, cập nhật cache có điều kiện, sự kiện vô hiệu hóa đáng tin cậy, kiểm tra lại nguồn tại điểm giao dịch hoặc thiết kế khác phù hợp.

Với quyết định nhạy cảm như thanh toán, đặt chỗ hoặc kiểm tra quyền, hãy dùng **nguồn có thẩm quyền** và bảo đảm tính nhất quán cần thiết. TTL 30 giây không làm cache trở thành nguồn quyết định an toàn chỉ vì cửa sổ cũ nhỏ.

### 7.2. Khi tất cả key hết hạn cùng lúc: cache stampede

Giả sử 50.000 khóa cache được tạo lúc bắt đầu chiến dịch với TTL đúng 600 giây. Tới giây thứ 600, nhiều khóa hết hạn gần như đồng thời. Một lượng lớn request miss và cùng truy vấn primary.

Để giảm hiệu ứng này:

1. **TTL jitter:** phân tán deadline, ví dụ `TTL = 600 giây + random(0..120 giây)` cho những cache chịu được khoảng sống đó. Nếu yêu cầu độ mới tối đa là 600 giây, phải phân tán *trong giới hạn 600 giây*, chẳng hạn `480..600`; không được tùy tiện kéo dài vượt SLO.
2. **Single-flight/request coalescing:** nhiều request cùng miss một key chia sẻ một lần fetch; cần giải pháp cho nhiều tiến trình nếu workload trải trên nhiều server.
3. **Làm ấm có chọn lọc:** refresh key hot trước khi hết hạn; tránh refresh toàn bộ key bằng cron đúng một thời điểm.
4. **Giới hạn tải khi miss:** rate limit, queue/bulkhead, timeout và fallback có kiểm soát để cache outage không kéo sập primary.
5. **Stale-while-revalidate:** nếu nghiệp vụ cho phép, tạm phục vụ một bản cũ có giới hạn trong khi refresh nền; cần thiết kế nơi giữ bản cũ còn truy cập được.

Điểm cuối rất quan trọng: khi Redis đã cho key hết hạn và coi key không tồn tại, ứng dụng **không thể mặc nhiên GET lại bản stale từ chính key đã hết hạn**. Muốn phục vụ stale cần lưu dữ liệu và metadata với hai mốc thời gian, hoặc giữ bản stale ở một lớp khác có retention dài hơn.

### 7.3. TTL quá ngắn và quá dài đều có chi phí

| TTL | Mặt được | Chi phí/rủi ro |
| --- | --- | --- |
| Rất ngắn | Dữ liệu bớt cũ; hữu ích với giá trị thay đổi nhanh | Hit ratio thấp, primary bị tải cao, nhiều refresh |
| Trung bình | Cân bằng hit ratio và độ mới với nhiều dữ liệu thông thường | Vẫn phải xử lý invalidation và tăng tải tại thời điểm hết hạn |
| Rất dài | Tiết kiệm đọc từ nguồn nếu dữ liệu ổn định | Giá trị cũ tồn tại lâu, bộ nhớ bị chiếm lâu hơn nếu ít eviction |
| Không TTL | Tránh hết hạn theo thời gian | Có nguy cơ giữ key không còn giá trị vô thời hạn nếu không có chính sách dọn khác |

Không có một TTL cố định đúng cho mọi loại key. Mốc thời gian nên dựa vào **độ mới được phép, tốc độ thay đổi dữ liệu, chi phí cache miss, dung lượng và hành vi truy cập**.

## 8. TTL cho session, rate limit và idempotency: cần hợp đồng khác cache

TTL trong key–value không chỉ dùng cho cache đọc. Có những khóa tạm đóng vai trò **trạng thái điều khiển**, nên việc hết hạn sớm hoặc muộn có hậu quả khác.

### 8.1. Session và mã đăng nhập một lần

Ví dụ:

~~~text
session:abc → userId=42, issuedAt=..., absoluteExpiresAt=...
TTL Redis: 1800 giây
~~~

Nếu TTL là idle timeout, có thể gia hạn khi có hoạt động hợp lệ. Nếu có giới hạn sống tối đa 8 giờ, thì mỗi lần gia hạn chỉ được tới **mốc absolute expiration**, không được kéo dài vô hạn.

Với mã xác thực hoặc token có deadline bảo mật, cần biết chính xác **ai có quyền quyết định thời hạn**. Nếu hệ thống sử dụng token tự chứa có chữ ký, phải kiểm tra hạn trong token theo quy tắc xác thực; TTL của một bản cache không thể thay thế xác minh token. Nếu dùng dữ liệu server-side, những đường đọc dự phòng và cache khác cũng phải tôn trọng trạng thái hết hạn.

Trong những tính năng có yêu cầu thu hồi phiên ngay lập tức, chỉ trông chờ TTL hết hạn có thể không đáp ứng yêu cầu. Cần cơ chế xóa/thu hồi tại nguồn phiên có thẩm quyền và bảo đảm các đường xác thực kiểm tra đúng trạng thái.

### 8.2. Rate limiting

Một bộ đếm theo cửa sổ có thể đặt:

~~~text
rate-limit:user:42:window:202611141030 → 17
TTL: đến khi không cần cửa sổ này nữa
~~~

TTL giúp dọn các bộ đếm của cửa sổ cũ. Nhưng TTL **không phải chính thuật toán rate limiting**: ứng dụng còn cần cách đếm nguyên tử, định nghĩa cửa sổ cố định/trượt hoặc token bucket, và cơ chế xác định ngưỡng.

Nếu tăng bộ đếm bằng `INCR` rồi gọi `EXPIRE` ở lệnh thứ hai, tiến trình chết ở giữa có thể để lại bộ đếm không có TTL. Một giải pháp là dùng **script/transaction thích hợp hoặc cấu trúc hỗ trợ đặt hạn dùng nguyên tử theo logic của thuật toán**. Với mục tiêu chặn lạm dụng, phải xem điều gì xảy ra khi key bị eviction: nếu mỗi eviction làm reset bộ đếm, giới hạn có thể bị vượt.

### 8.3. Idempotency và chống xử lý trùng

Một API tạo thanh toán có thể dùng `idempotencyKey` để ghi nhớ kết quả:

~~~text
idem:payment:req-903 → {status: "completed", resultId: "payment-81"}
TTL: 24 giờ
~~~

Nếu khóa hết hạn sau 24 giờ, cùng một `idempotencyKey` có thể không còn được nhận diện. Thời hạn phải được chọn theo **khoảng thời gian client được phép retry, yêu cầu nghiệp vụ và tính bền vững của kết quả**. Với thanh toán, không nên trông chờ một key cache dễ bị evict để bảo đảm vĩnh viễn “không bao giờ giao dịch trùng”; cần ràng buộc, trạng thái bền vững và xử lý retry ở nguồn có thẩm quyền.

`SET key value NX EX seconds` có thể hỗ trợ bước đặt khóa tạm nguyên tử, nhưng vẫn cần xử lý tiến trình bị treo, timeout, trạng thái đang xử lý, kết quả đã commit và cạnh tranh sau khi key hết hạn. Với một lease/lock có TTL, khóa hết hạn **không tự ngăn worker cũ tiếp tục ghi**. Nếu cần ngăn thao tác cũ, có thể phải dùng fencing token, điều kiện phiên bản hoặc cơ chế nhất quán ở tài nguyên đích.

### 8.4. Presence, telemetry và dữ liệu dễ tái tạo

Trạng thái “thiết bị đang hoạt động” hoặc “người dùng trực tuyến” có thể được lưu với TTL ngắn, làm mới theo heartbeat:

~~~text
presence:device:0091 → online
TTL = 90 giây; heartbeat mỗi 30 giây
~~~

Nếu thiết bị mất mạng, khóa tự hết hạn sau khi không còn heartbeat. Tuy nhiên, không nên diễn giải “còn key” là bằng chứng tuyệt đối thiết bị đang hoạt động **ngay lúc này**. Cần định nghĩa độ trễ tối đa được chấp nhận và xử lý heartbeat đến muộn/trùng.

## 9. TTL có phải chính sách lưu giữ và xóa dữ liệu không?

TTL có thể **hỗ trợ** chính sách lưu giữ dữ liệu (retention), nhưng không tự động đáp ứng toàn bộ yêu cầu xóa vĩnh viễn.

Một key hết hạn có thể còn ảnh hưởng tới:

- **Bản sao, snapshot và backup:** dữ liệu có thể nằm trong bản sao lưu được tạo trước khi key hết hạn.
- **Log, CDC/event stream:** giá trị hoặc thông tin liên quan có thể đã được ghi ở hệ thống khác.
- **Chỉ mục tìm kiếm hoặc read model:** có thể giữ bản dẫn xuất cho đến khi nhận lệnh xóa hoặc đồng bộ.
- **Bộ nhớ/đĩa chưa được dọn:** expiration có thể logic trước khi thu hồi vật lý.
- **Hệ thống phân tích và bên thứ ba:** đã nhận bản sao dữ liệu qua pipeline riêng.

Nếu có yêu cầu pháp lý hoặc nghiệp vụ “xóa hoàn toàn sau thời hạn X”, cần quy trình xác định **mọi bản sao dữ liệu**, thời gian giữ backup, sự kiện xóa và cách kiểm chứng xóa theo hợp đồng từng hệ thống. Không thể chứng minh xóa toàn bộ bằng câu “Redis TTL = 86400”.

Tương tự, TTL không phải công cụ lập lịch đáng tin để “đúng 10:30 phải gửi email hoặc kích hoạt tác vụ”. Keyevent notification của cache, nếu được bật, không nên coi là hàng đợi sự kiện bền vững hoặc bảo đảm phát đúng thời điểm. Với tác vụ theo lịch cần dùng scheduler/queue bền vững cùng deadline nghiệp vụ.

## 10. Quan sát expiration và eviction trong vận hành

Ứng dụng nên đo cả hai nguyên nhân cache miss. Chỉ đo cache hit ratio tổng thể chưa cho biết vấn đề xuất phát từ TTL quá ngắn, bộ nhớ quá ít hay chính sách eviction.

### 10.1. Chỉ số hữu ích

| Chỉ số | Có thể trả lời điều gì? | Điều cần tránh khi suy diễn |
| --- | --- | --- |
| `keyspace_hits`, `keyspace_misses` | Mức độ đọc hit/miss trong Redis | Không mặc nhiên tương đương tỷ lệ cache hit của toàn API; cần phân nhóm workload |
| `expired_keys` | Số key bị dọn do hết hạn tăng ra sao | Giá trị tích lũy không cho biết tất cả key sẽ hết hạn vào giây nào |
| `evicted_keys` | Có eviction do giới hạn bộ nhớ không? | Không chỉ ra ngay key nào hoặc yêu cầu nào bị ảnh hưởng |
| `used_memory`, `maxmemory` | Mức tiêu thụ bộ nhớ và ngưỡng cấu hình | Không phải dự báo chính xác RSS của tiến trình hay toàn cluster |
| Latency p95/p99 của Redis và API | Cache miss/eviction có tạo đuôi trễ không? | Latency thấp không bảo đảm dữ liệu còn đúng |
| Tải primary, QPS và lỗi fallback | Khi miss hoặc cache lỗi, nguồn chính có bị quá tải? | Cần đối chiếu cùng cửa sổ thời gian |
| Phân bố TTL còn lại | Nhiều key sắp hết hạn cùng lúc không? | Lấy mẫu đại diện; không quét toàn keyspace production tùy tiện |
| Kích thước và số lượng key | Key nào quá lớn, gây chiếm bộ nhớ? | Dung lượng trung bình có thể che đuôi kích thước lớn |

Trong Redis:

~~~redis
INFO stats
INFO memory
INFO keyspace
TTL cache:product:42
PTTL cache:product:42
~~~

Các số đếm `expired_keys` và `evicted_keys` có ý nghĩa hơn khi theo dõi **mức tăng theo phút/giờ**, kèm tải đọc, lưu lượng ghi và độ trễ. Ví dụ `evicted_keys` tăng mạnh cùng lúc API p99 tăng và primary QPS tăng có thể gợi ý cache thiếu sức chứa. Cần kiểm chứng thêm vì tăng cache miss cũng có thể do traffic mới hoặc ứng dụng invalidation nhiều.

### 10.2. Đặt cảnh báo theo hậu quả

Không nên dùng duy nhất “cache hit ratio dưới 90%” cho mọi loại key. Các mục tiêu khác nhau:

- Cache danh mục có thể chấp nhận miss nếu primary chịu được tải.
- Cache chống stampede cho hot key cần cảnh báo khi miss đồng thời tăng mạnh.
- Key rate limiting mất trước deadline có thể khiến kiểm soát lưu lượng sai.
- Session eviction không mong muốn có thể làm người dùng bị đăng xuất sớm.
- Dữ liệu tạm nhưng có nhiệm vụ như dedup/idempotency phải được thiết kế để chịu mất key hoặc chuyển sang kho bền vững.

SLO và cảnh báo nên gắn với **độ trễ, tỷ lệ lỗi, giới hạn nhất quán và tác động nghiệp vụ**, không chỉ bộ nhớ của Redis.

## 11. Thử nghiệm TTL và eviction trên workload mẫu

Một kịch bản kiểm chứng có thể dùng kho Redis thử nghiệm riêng, với những nhóm khóa:

- **Nhóm A:** 100.000 khóa chi tiết sản phẩm, TTL 600 giây, key được đọc theo phân bố Zipf/hot key.
- **Nhóm B:** 10.000 khóa phiên, TTL trượt 1.800 giây, có hoạt động không đều.
- **Nhóm C:** 20.000 bộ đếm tạm TTL 60 giây.
- **Nhóm D:** một tập khóa không TTL để kiểm tra chính sách cho phép hoặc không cho phép evict.

Số lượng, kích thước value, TTL và tốc độ request phải được điều chỉnh để đạt ngưỡng bộ nhớ **một cách an toàn trong môi trường thử nghiệm**. Nếu mỗi value là 1 KiB, 100.000 value đã chứa khoảng 97,7 MiB payload thô, **chưa kể** key, metadata, cấu trúc dữ liệu, fragmentation, replication và overhead khác.

### 11.1. Ma trận thử nghiệm

| Kịch bản | Điều giữ/đổi | Cần đo |
| --- | --- | --- |
| **TTL không có áp lực bộ nhớ** | Đủ bộ nhớ, các khóa có TTL khác nhau | Thời gian đọc chuyển thành miss; số key hết hạn |
| **Bộ nhớ đầy + `allkeys-lru`** | Tăng số khóa dưới cùng workload | `evicted_keys`, hit ratio, hot key survival, p99 API |
| **Bộ nhớ đầy + `volatile-ttl`** | Một số khóa có TTL, một số không | Key nào đủ điều kiện eviction, write errors khi thiếu ứng viên |
| **Bộ nhớ đầy + `noeviction`** | Không cho Redis loại key theo policy | Thao tác nào bị lỗi; fallback có làm ứng dụng suy giảm không |
| **Đồng loạt hết hạn** | Nhiều key cùng TTL và thời điểm tạo | Primary QPS spike, stampede, queue và timeout |
| **TTL jitter** | Cùng tổng khóa nhưng deadline phân tán | Mức giảm tải đỉnh so với trường hợp đồng loạt |
| **Cache bị ngắt kết nối** | Không thể đọc/ghi cache tạm thời | Hành vi fallback, rate limit, độ trễ và số lỗi |
| **Ghi đè/renew key** | `SET`, `SET ... EX`, `KEEPTTL`, `GETEX` | Deadline còn như mong muốn hay bị xóa/gia hạn ngoài ý muốn |

Để có kết luận sử dụng được, ghi phiên bản Redis/driver, số node, kiểu máy, bộ nhớ giới hạn, kích thước key/value, phân phối key, số request/s được gửi và xử lý, độ trễ p95/p99, tỷ lệ lỗi và số lần retry. Tránh chỉ báo throughput tối đa mà bỏ qua việc request bị từ chối hoặc timeout.

### 11.2. Ví dụ phân tích kết quả (số liệu minh họa)

| Cấu hình | Hit ratio | Evictions/phút | p99 API đọc | Nhận định |
| --- | ---: | ---: | ---: | --- |
| Đủ bộ nhớ, TTL 600 giây | 94% | 0 | 38 ms | Baseline khi không có áp lực |
| Bộ nhớ giảm, `allkeys-lru` | 78% | 12.000 | 160 ms | Miss tăng do eviction trước TTL |
| Bộ nhớ giữ nguyên, TTL 60 giây | 64% | 0 | 210 ms | Miss chủ yếu do vòng đời TTL quá ngắn |
| TTL 600 giây, đồng loạt hết hạn | 91% trung bình | 0 | 740 ms tại đỉnh | Hit ratio trung bình che tải dồn tại một thời điểm |
| TTL phân tán hợp lệ + single-flight | 92% | 0 | 95 ms tại đỉnh | Có thể giảm stampede nếu cách triển khai đúng |

Đây chỉ là **bảng minh họa để tập suy luận**, không phải benchmark của một sản phẩm. Để xác nhận nguyên nhân phải đối chiếu thời điểm dọn/evict, số request về nguồn chính và điều kiện thực thi.

## 12. Chọn TTL và eviction policy theo mục đích dữ liệu

| Dữ liệu key–value | TTL thường được dùng để làm gì? | Eviction có chấp nhận được không? | Điểm cần thiết kế thêm |
| --- | --- | --- | --- |
| Cache chi tiết sản phẩm | Giới hạn độ cũ và dọn giá trị không còn hữu ích | Thường có, nếu fallback tốt | Invalidation, jitter, chống stampede |
| Cache kết quả truy vấn tốn chi phí | Kiểm soát độ mới | Có thể, nhưng eviction nhiều gây tải lớn | Headroom, warm-up, single-flight |
| Session đăng nhập | Kết thúc phiên khi không hoạt động/quá hạn | Có thể gây đăng xuất sớm; tùy yêu cầu | Giới hạn tuyệt đối, thu hồi, trạng thái có thẩm quyền |
| Mã OTP/secret tạm | Giới hạn thời gian hiệu lực | Mất sớm gây lỗi trải nghiệm, kéo dài gây rủi ro | Kiểm tra deadline bảo mật, thao tác tiêu thụ một lần |
| Rate limit counter | Dọn bộ đếm cửa sổ cũ | Có thể làm reset giới hạn ngoài dự kiến | Tính nguyên tử, chống bypass, xử lý lỗi |
| Idempotency/dedup key | Giữ dấu vết trong khoảng retry | Có thể dẫn tới xử lý trùng | Kho ghi bền vững/ràng buộc nghiệp vụ |
| Trạng thái online/heartbeat | Đánh dấu mất hoạt động | Thường có thể chấp nhận sai lệch tạm | Cửa sổ phát hiện offline, heartbeat đến muộn |
| Dữ liệu giao dịch duy nhất | Không nên dùng TTL như cache thông thường | Thường **không** | Persistence, replica, khôi phục và xóa theo chính sách nghiệp vụ |

Điểm quyết định: **TTL mô tả vòng đời mong muốn, eviction mô tả cách hệ thống đối phó áp lực tài nguyên**. Nếu giá trị có thể bị loại bỏ sớm, ứng dụng phải biết tái tạo hoặc xử lý thiếu dữ liệu. Nếu giá trị không được phép mất trước deadline, cần mô hình lưu trữ và bảo đảm khác, không chỉ cấu hình TTL dài hơn.

## 13. Bài tập tình huống

Một dịch vụ thương mại điện tử có bốn loại key:

~~~text
cache:product:42       TTL = 10 phút, lấy lại từ Product DB
session:user:7         TTL = 30 phút, refresh theo hoạt động
idem:checkout:req-81   TTL = 24 giờ, dùng ngăn checkout trùng
rate-limit:user:7      TTL = 60 giây, giới hạn 100 request/cửa sổ
~~~

Hệ thống chỉ cấp 1 GiB cho instance Redis nhưng lượng khóa tăng mạnh vào giờ sale. Người vận hành cân nhắc `allkeys-lru`, `volatile-ttl` và `noeviction`.

Hãy trả lời:

1. Nếu `cache:product:42` bị evict sau 2 phút, đó có phải lỗi TTL không? Ứng dụng nên làm gì?
2. Nếu `session:user:7` bị xóa do eviction, người dùng có thể bị ảnh hưởng thế nào? Gia hạn TTL có giải quyết được nguyên nhân này không?
3. Nếu `idem:checkout:req-81` bị evict sau 3 phút, điều gì có thể xảy ra khi client retry? Có nên chỉ trông chờ Redis để tránh tạo đơn trùng không?
4. Nếu `rate-limit:user:7` bị xóa trước khi cửa sổ 60 giây kết thúc, vì sao đó có thể là lỗi về an toàn vận hành?
5. Với `volatile-ttl`, nếu phần lớn bộ nhớ là key **không có TTL**, hệ thống có thể gặp vấn đề gì?
6. Với `noeviction`, key có TTL còn hết hạn không, và điều gì xảy ra với yêu cầu ghi mới khi bộ nhớ cạn?

**Gợi ý hướng giải:** Cache sản phẩm có thể chấp nhận eviction nếu nguồn chính và cơ chế chống stampede đủ sức chịu tải. Session, idempotency và rate limit phải được xem xét theo hậu quả nghiệp vụ của việc mất key; không nên đặt dữ liệu quan trọng cùng chính sách eviction mà chưa có biện pháp bảo đảm. `volatile-ttl` không phải “chỉ xóa key đã hết hạn”, còn `noeviction` không phải “không có expiration”.

Khi thiết kế mô hình khóa–giá trị, hãy tự hỏi **ba câu riêng biệt**: “Giá trị này được coi là hết hiệu lực lúc nào?”, “Nếu bộ nhớ thiếu, giá trị này có thể biến mất sớm không?” và “Nếu một lần đọc nhận miss, hệ thống sẽ làm gì?”. Trả lời rõ cả ba mới đủ để lựa chọn TTL, chính sách eviction, cơ chế làm mới và phương án khôi phục phù hợp.
