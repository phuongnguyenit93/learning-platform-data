# Cache with Redis và giảm tải truy cập database

Trong chương **Kiến trúc sẵn sàng cao** của module **Oracle Cloud Infrastructure**, cache giúp giảm số lượt truy vấn database và rút ngắn thời gian phản hồi cho những dữ liệu được đọc lặp lại. Tuy nhiên, một tầng cache chỉ cải thiện tính sẵn sàng khi ứng dụng xử lý được cả dữ liệu cũ, cache miss, lỗi kết nối và quá trình nạp lại dữ liệu.

Nếu database chỉ chịu được tải khi cache đang nóng, một sự cố Redis có thể làm database quá tải ngay sau đó. Vì vậy, thiết kế phải bao gồm **cách đọc**, **cách cập nhật**, **giới hạn tải khi suy giảm** và **cách khôi phục cache**.

Bài học sử dụng **OCI Cache** làm dịch vụ cache được quản lý trên OCI và **Oracle Database** làm nguồn dữ liệu nghiệp vụ. Các ví dụ tập trung vào Redis và những thao tác cơ bản; cần đối chiếu engine, phiên bản và khả năng hỗ trợ của cluster thực tế.

## 1. Cache là bản sao phục vụ đọc, không tự thay thế database

Trong thiết kế của bài học:

- Oracle Database giữ dữ liệu có thẩm quyền và thực hiện giao dịch nghiệp vụ.
- Redis giữ một phần dữ liệu có thể tái tạo để phục vụ các lượt đọc phù hợp.
- Ứng dụng quyết định key, TTL, quyền truy cập, cách nạp và cách vô hiệu hóa dữ liệu.
- OCI cung cấp và vận hành các thành phần hạ tầng theo phạm vi dịch vụ được quản lý.

“Dữ liệu có thể tái tạo” nghĩa là mất cache không làm mất bản ghi nghiệp vụ đã cam kết. Các dữ liệu như trạng thái thanh toán duy nhất, quyền sở hữu cuối cùng hoặc số lượng hàng được giữ chỗ cần được bảo vệ bằng cơ chế nghiệp vụ phù hợp tại nguồn có thẩm quyền.

| Dữ liệu hoặc tác vụ | Khả năng sử dụng cache | Điều cần quyết định |
| --- | --- | --- |
| Mô tả sản phẩm, danh mục ít thay đổi | Thường phù hợp | Thời gian chấp nhận dữ liệu cũ |
| Trang tổng hợp đọc nhiều, tính toán tốn kém | Có thể phù hợp | Phụ thuộc dữ liệu và cách invalidation |
| Hồ sơ người dùng | Có thể phù hợp | Phạm vi quyền, trường nhạy cảm, thay đổi hồ sơ |
| Hiển thị giá hoặc tồn kho tham khảo | Cần hợp đồng độ mới rõ ràng | Kiểm tra lại tại bước ra quyết định nghiệp vụ |
| Xác nhận thanh toán hoặc giữ hàng | Không dựa riêng vào cache đọc | Giao dịch, ràng buộc và kiểm tra tại database |
| Truy vấn hiếm, kết quả gần như không được dùng lại | Có thể không đáng cache | Chi phí bộ nhớ và độ phức tạp bổ sung |

Cache không sửa được truy vấn sai hoặc một database thiếu index cần thiết. Trước khi thêm Redis, cần xác định truy vấn nào gây tải và việc đọc lặp có đủ lớn để cache tạo giá trị hay không.

## 2. OCI Cache trong kiến trúc OCI

### 2.1. Tên dịch vụ và các kiểu cluster

OCI Cache là dịch vụ cache bộ nhớ được quản lý, hỗ trợ các engine Redis và Valkey theo danh sách phiên bản của dịch vụ. Nó có hai kiểu chính:

- **Non-sharded:** một primary và các replica nếu được cấu hình; dữ liệu được sao chép giữa các node.
- **Sharded:** dữ liệu được chia giữa các shard; mỗi shard có primary và các replica theo cấu hình.

Danh sách engine và khả năng hiện hành cần xem trong [About OCI Cache](https://docs.oracle.com/en-us/iaas/Content/ocicache/overview.htm). Không mặc định mọi tính năng của Redis mới nhất hoặc Redis Enterprise đều có trong engine của OCI Cache.

Replica tăng dự phòng và có thể hỗ trợ tải đọc phù hợp. Shard chia dữ liệu và tải giữa nhiều phần. Hai cơ chế giải quyết các nhu cầu khác nhau.

### 2.2. Sơ đồ triển khai minh họa

~~~mermaid
flowchart TD
    U["Client"] --> LB["OCI Load Balancer"]
    LB --> A["Ứng dụng A"]
    LB --> B["Ứng dụng B"]
    A --> C["OCI Cache: private endpoint"]
    B --> C
    C --> P["Primary"]
    P --> R1["Replica 1"]
    P --> R2["Replica 2"]
    A --> D["Oracle Database: nguồn dữ liệu có thẩm quyền"]
    B --> D
    D --> E["Outbox hoặc luồng thay đổi đã triển khai"]
    E --> I["Worker vô hiệu hóa cache"]
    I --> C
~~~

Đây là kiến trúc minh họa, không phải các tích hợp tự hình thành khi tạo cluster. Ứng dụng, database và cache đều cần phương án sẵn sàng cao riêng.

Với non-sharded cluster phục vụ production, Oracle khuyến nghị một primary và hai replica. Dịch vụ cố gắng phân tán node giữa fault domain và availability domain phù hợp với region. Không suy ra mọi region đều có ba availability domain hoặc việc bố trí luôn giống nhau. [Creating an OCI Cache Cluster](https://docs.oracle.com/en-us/iaas/Content/ocicache/createcluster.htm), [About OCI Cache](https://docs.oracle.com/en-us/iaas/Content/ocicache/overview.htm).

### 2.3. Đường kết nối là một phần của kiến trúc

OCI Cache cung cấp private endpoint. Với đường TLS thông thường, client kết nối qua TCP 6379, kiểm tra chứng thư và dùng hostname của dịch vụ. [Connecting to an OCI Cache Cluster](https://docs.oracle.com/en-us/iaas/Content/ocicache/connecttocluster.htm).

Một bố trí thường gặp:

- Ứng dụng ở subnet có quyền kết nối tới cache.
- Cache nằm trong mạng riêng, với NSG hoặc security list giới hạn nguồn.
- Oracle Database có đường kết nối và quyền truy cập riêng.
- Các workload vận hành có đường truy cập tới Monitoring, dịch vụ xác thực và nơi quản lý bí mật khi cần.

Compartment tổ chức tài nguyên và phạm vi IAM; nó không tự tạo ranh giới mạng. Tạo cluster trong cùng compartment với ứng dụng không có nghĩa ứng dụng đã kết nối được.

## 3. Chọn cache-aside cho các lượt đọc lặp

### 3.1. Luồng đọc

Với **cache-aside**, ứng dụng chủ động kiểm tra cache; khi thiếu dữ liệu thì đọc database và có thể ghi lại vào cache.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Ứng dụng
    participant R as Redis
    participant D as Oracle Database
    C->>A: Đọc mô tả sản phẩm
    A->>A: Kiểm tra quyền và tạo cache key
    A->>R: GET key
    alt Cache hit hợp lệ
        R-->>A: Dữ liệu cache
        A-->>C: Kết quả
    else Cache miss
        R-->>A: Không có key
        A->>D: Truy vấn có giới hạn
        D-->>A: Dữ liệu nguồn
        A->>R: SET key value EX ttl
        A-->>C: Kết quả
    end
~~~

Cache-aside chỉ nạp những dữ liệu thực sự được yêu cầu. TTL và invalidation là các phần cần thiết để quản lý độ mới. [Redis cache-aside](https://redis.io/docs/latest/develop/use-cases/cache-aside/).

Luồng trên là trường hợp bình thường. Trước khi đưa vào production cần bổ sung giới hạn thời gian, chống nạp trùng và kiểm soát tải database.

### 3.2. Luồng cập nhật cơ bản

Một cách bắt đầu là:

1. Kiểm tra quyền và điều kiện nghiệp vụ.
2. Cập nhật Oracle Database.
3. Commit giao dịch.
4. Xóa những key bị ảnh hưởng.
5. Lượt đọc sau nạp lại dữ liệu.

Không xóa cache rồi giả định database chắc chắn sẽ cập nhật thành công. Cũng không để callback invalidation chạy trước commit nếu người đọc sau đó có thể nạp lại dữ liệu chưa được cập nhật.

Nếu database đã commit nhưng việc xóa cache thất bại, giao dịch database không tự quay lại trạng thái cũ. Cần cơ chế ghi nhận và thử lại invalidation; tránh trả trạng thái mơ hồ làm client lặp một giao dịch nghiệp vụ không có idempotency.

### 3.3. Phân biệt các mẫu khác

| Mẫu | Cách hoạt động | Đánh đổi |
| --- | --- | --- |
| **Cache-aside** | Ứng dụng đọc cache rồi nạp từ nguồn khi miss | Đơn giản về đường ghi nhưng cần quản lý độ mới |
| **Read-through** | Tầng cache hoặc adapter chịu trách nhiệm tải từ nguồn | Cần thành phần thực hiện loader |
| **Write-through** | Đường ghi phối hợp cập nhật nguồn và cache trước khi hoàn tất theo hợp đồng | Tăng độ trễ và xử lý lỗi giữa hai nơi |
| **Write-behind** | Ghi được nhận ở tầng trung gian, nguồn được cập nhật sau | Có cửa sổ mất hoặc trễ dữ liệu; cần cơ chế bền vững riêng |

Redis không tự biết cách truy vấn Oracle Database chỉ vì ứng dụng gọi GET. Read-through là hành vi cần một thư viện, adapter hoặc dịch vụ thực hiện.

Với bài toán giảm tải đọc của một hệ thống đã có database giao dịch, cache-aside thường là điểm xuất phát dễ kiểm soát hơn. Lựa chọn cuối cùng phụ thuộc hợp đồng dữ liệu và cách xử lý lỗi.

## 4. Ước lượng mức giảm tải và tải khi cache mất tác dụng

Giả sử toàn bộ 10.000 lượt đọc mỗi giây đều có thể cache, mỗi miss tạo một truy vấn database và hit ratio là 95%:

~~~text
DB reads khi cache hoạt động =
    read requests × (1 - hit ratio)
  = 10.000 × 0,05
  = 500 lượt đọc/giây

DB reads khi cache không còn phục vụ =
    10.000 lượt đọc/giây
~~~

Tải đọc vào database có thể tăng **20 lần** so với trạng thái cache nóng. Đây là ví dụ giả lập, chưa tính lượt ghi, truy vấn phụ hoặc tác vụ nền.

Nếu chỉ một phần lưu lượng có thể cache:

~~~text
DB reads ≈
    lượt đọc không thể cache
  + lượt đọc có thể cache × tỷ lệ miss
  + lượt đọc do refresh hoặc xử lý nền
~~~

Phép tính chỉ có ý nghĩa khi đơn vị phù hợp. Một request miss có thể chạy nhiều truy vấn; một miss khác có thể chỉ đọc theo primary key. Cần đo cả số truy vấn, thời gian database và mức tiêu thụ kết nối.

Hit ratio cao chưa chắc giảm được nhiều tải nếu cache chủ yếu giữ những truy vấn rất rẻ, còn các truy vấn nặng vẫn luôn miss.

Một yêu cầu thiết kế quan trọng là xác định **ngân sách tải database khi suy giảm**. Nếu database không chịu được toàn bộ lưu lượng không cache, ứng dụng phải có admission control, mức phục vụ suy giảm hoặc cơ chế từ chối có kiểm soát.

## 5. Thiết kế key, payload và TTL

### 5.1. Key phải phản ánh đúng phạm vi dữ liệu

Ví dụ key do ứng dụng tự quy định:

~~~text
cache:prod:catalog:tenant-demo:v2:product:p-100:locale:vi
~~~

Key thể hiện môi trường, loại dữ liệu, tenant, phiên bản schema, đối tượng và ngôn ngữ. Nếu kết quả còn phụ thuộc vùng, bộ lọc hoặc nhóm quyền thì phải đưa yếu tố tương ứng vào thiết kế key hoặc cách xác thực.

Không đưa email, token hay thông tin cá nhân đầy đủ vào tên key. Những giá trị này có thể xuất hiện trong công cụ vận hành và log.

Với dữ liệu riêng, kiểm tra quyền vẫn cần thực hiện trước khi trả cache. Một cache hit không phải bằng chứng người gọi được phép đọc payload đó.

### 5.2. Payload cần có schema và thông tin truy vết phù hợp

~~~json
{
  "schemaVersion": 2,
  "entityVersion": 42,
  "loadedAt": "2026-11-21T03:00:00Z",
  "data": {
    "productId": "p-100",
    "name": "Sản phẩm minh họa",
    "category": "demo"
  }
}
~~~

Đây là schema minh họa, không phải định dạng bắt buộc của OCI Cache.

Phiên bản schema hỗ trợ rollout mã ứng dụng. Entity version có thể hỗ trợ đối chiếu với nguồn nếu nguồn có cơ chế version phù hợp. LoadedAt chỉ cho biết thời điểm nạp, không tự chứng minh snapshot database đã phản ánh mọi cập nhật trước đó.

Không cache toàn bộ đối tượng ORM nếu nó chứa trường nhạy cảm, lazy proxy hoặc quan hệ không cần thiết. Chọn DTO nhỏ, có schema rõ và giới hạn kích thước.

### 5.3. Ghi giá trị và TTL trong cùng thao tác

Ví dụ các lệnh trong một phiên Redis CLI đã kết nối và xác thực:

~~~text
SET cache:lab:catalog:v1:product:p-100 '{"productId":"p-100","name":"Demo"}' EX 60
GET cache:lab:catalog:v1:product:p-100
TTL cache:lab:catalog:v1:product:p-100
DEL cache:lab:catalog:v1:product:p-100
~~~

SET với EX đặt giá trị và thời gian hết hạn trong một thao tác. Nếu tách SET rồi EXPIRE, ứng dụng có thể dừng giữa hai lệnh và để lại key không có TTL. Một SET thông thường cũng có thể thay thế TTL cũ, nên phải xác định rõ TTL của từng lần ghi. [Redis SET](https://redis.io/docs/latest/commands/set/).

Các key ví dụ thuộc namespace lab. TTL 60 giây chỉ là giá trị minh họa; không phải khuyến nghị chung cho dữ liệu nghiệp vụ.

### 5.4. Chọn TTL từ mức chấp nhận dữ liệu cũ

TTL cần cân bằng:

- Tần suất dữ liệu thay đổi.
- Mức độ nghiêm trọng khi đọc dữ liệu cũ.
- Khả năng invalidation.
- Lưu lượng và chi phí nạp lại.
- Working set và ngân sách bộ nhớ.

Có thể thêm **jitter** để các key không hết hạn cùng lúc. Ví dụ cho phép TTL nằm trong 48–60 giây thay vì tất cả đều là 60 giây. Không thêm jitter vượt quá mức độ cũ mà nghiệp vụ chấp nhận.

TTL tính từ lúc key được ghi vào cache. Nó không tự tạo ra bảo đảm “dữ liệu luôn mới trong vòng X giây kể từ mọi commit database”, nhất là khi có tải chậm, replica lag hoặc cuộc đua giữa đọc và ghi.

TTL cũng không bảo đảm key tồn tại đến thời điểm đó: eviction, xóa chủ động hoặc sự cố có thể làm key biến mất sớm.

## 6. Invalidation và cuộc đua dữ liệu cũ

### 6.1. Commit rồi xóa cache vẫn có cửa sổ cạnh tranh

Xét dòng thời gian:

~~~text
T1: Request A miss cache và đọc dữ liệu version 41 từ database
T2: Request B cập nhật database lên version 42 rồi commit
T3: B xóa key cache
T4: A hoàn tất xử lý chậm và ghi version 41 vào cache
T5: Request C đọc được version 41 từ cache
~~~

Lệnh DEL ở T3 đã chạy thành công nhưng dữ liệu cũ vẫn được nạp lại ở T4. Đây là lý do không nên mô tả cache-aside với delete-on-write là cơ chế nhất quán mạnh.

Nếu chấp nhận dữ liệu cũ trong một khoảng có kiểm soát, TTL ngắn, giới hạn thời gian nạp và invalidation có thể đủ cho một số dữ liệu. Cần mô tả rõ điều kiện thay vì coi TTL là bảo đảm tuyệt đối.

### 6.2. Tăng độ tin cậy của invalidation bằng outbox hoặc CDC

Một thiết kế outbox có thể:

1. Cập nhật bản ghi nghiệp vụ và ghi sự kiện thay đổi trong cùng giao dịch database.
2. Commit cả hai.
3. Worker đọc sự kiện và xóa các key liên quan.
4. Ghi nhận tiến độ và retry khi lỗi.

Sự kiện nên có ID, định danh thực thể và phiên bản khi phù hợp. Consumer phải xử lý được việc nhận lại sự kiện; DEL cho một key đã mất vẫn phù hợp với mục tiêu vô hiệu hóa.

CDC là một lựa chọn khác khi thay đổi có thể đi qua nhiều ứng dụng hoặc tác vụ trực tiếp trên database. Đây là một tích hợp cần cấu hình, giám sát và tính chi phí.

Outbox giúp tránh mất ý định invalidation sau commit, nhưng tự nó chưa loại bỏ cuộc đua nạp dữ liệu cũ đã bắt đầu từ trước. Nếu cần giao thức theo phiên bản, phải thiết kế cả đường đọc, đường ghi và cách xử lý marker bị mất.

### 6.3. Xác định những key phụ thuộc

Cập nhật một sản phẩm có thể ảnh hưởng:

- Key chi tiết sản phẩm.
- Trang danh mục và kết quả lọc.
- Nội dung tổng hợp ở trang chủ.
- Các biến thể ngôn ngữ hoặc tenant liên quan.

Thiết kế danh sách phụ thuộc, nhóm version hoặc namespace generation phù hợp. Không mặc định xóa một key chi tiết sẽ làm mọi kết quả truy vấn tổng hợp trở nên mới.

Không dùng thao tác quét toàn bộ keyspace trên đường xử lý mỗi cập nhật. Nếu một đợt invalidation lớn là cần thiết, phải giới hạn tốc độ và theo dõi lượng miss phát sinh sau đó.

### 6.4. Khi cần dữ liệu nhất quán hơn

Các lựa chọn có thể gồm:

- Trả trực tiếp dữ liệu vừa commit cho người thực hiện cập nhật.
- Bypass cache cho một số lượt đọc cần read-your-writes.
- Đối chiếu version hoặc dùng giao thức nạp có kiểm soát được thiết kế đầy đủ.
- Đọc nguồn có thẩm quyền tại bước quyết định nghiệp vụ.

Một lock chống nạp trùng chỉ bao quanh loader không tự đồng bộ được với writer đang cập nhật database.

Với số dư, quyền truy cập vừa bị thu hồi hoặc quyết định giữ hàng, dùng cơ chế nhất quán tại nguồn phù hợp thay vì dựa riêng vào thời gian sống của cache.

## 7. Chống stampede, avalanche, penetration và hot key

| Hiện tượng | Cơ chế | Cách xử lý cần xem xét |
| --- | --- | --- |
| **Cache stampede** | Nhiều request cùng miss một key nóng | Single-flight, nạp có giới hạn, refresh sớm |
| **Cache avalanche** | Nhiều key hết hạn hoặc cache mất tác dụng cùng lúc | TTL jitter, warm-up có giới hạn, bảo vệ database |
| **Cache penetration** | Liên tục hỏi đối tượng không tồn tại | Kiểm tra đầu vào, rate limit, negative cache |
| **Hot key** | Một key nhận tải lớn hơn khả năng phục vụ | Giảm payload, L1 nếu phù hợp, phân tán lượt đọc theo hợp đồng |
| **Hot shard** | Dữ liệu hoặc truy cập lệch về một shard | Kiểm tra key distribution và thiết kế phân mảnh |

Các thuật ngữ có thể được sử dụng khác nhau giữa tài liệu; điều quan trọng là nhận diện đúng dạng tải.

### 7.1. Single-flight theo key

Single-flight cho phép những request đồng thời của cùng một key dùng chung một lần tải đang diễn ra.

Trong một instance, có thể dùng cấu trúc in-flight map và future. Với nhiều instance, cơ chế cục bộ chỉ gộp được trong từng instance, không bảo đảm toàn hệ thống chỉ có một lượt đọc database.

Nếu dùng khóa ngắn trong Redis để điều phối nạp:

~~~text
SET lock:lab:catalog:product:p-100 TOKEN_DUY_NHAT NX PX 3000
~~~

Token phải khác cho mỗi lần giữ khóa. Khi giải phóng, kiểm tra token và xóa một cách nguyên tử; không DEL mù vì khóa có thể đã hết hạn rồi thuộc về client khác. Trên những phiên bản cũ hơn có thể dùng Lua script phù hợp nếu dịch vụ và quyền cho phép. [Distributed Locks with Redis](https://redis.io/docs/latest/manual/patterns/distributed-locks/).

Đây là kỹ thuật giảm nạp trùng, không phải bảo đảm độc quyền cho giao dịch tiền hoặc tồn kho. Lease có thể hết khi loader vẫn chạy, hoặc khóa có thể mất khi failover.

Request không lấy được khóa chỉ nên chờ có giới hạn, dùng dữ liệu cũ còn được phép hoặc đi qua cơ chế admission control. Nếu hết thời gian chờ rồi tất cả cùng truy vấn database, stampede chỉ bị trì hoãn.

### 7.2. Soft TTL và stale-while-revalidate

Ứng dụng có thể phân biệt:

- **Soft expiry:** bắt đầu cần refresh.
- **Hard expiry hoặc giới hạn độ cũ:** không được phục vụ tiếp theo hợp đồng.

Trong khoảng giữa hai mốc, có thể trả dữ liệu cũ được phép và chỉ cho một tác vụ refresh. Không để mỗi lượt đọc kéo dài thời hạn dữ liệu cũ vô hạn.

Nếu key đã bị Redis xóa hoặc evict thì không còn payload để phục vụ stale. Muốn hỗ trợ hành vi này cần thiết kế lưu payload và metadata phù hợp, không chỉ đặt một TTL rồi giả định dữ liệu vẫn tồn tại.

### 7.3. Negative cache

Có thể giữ một sentinel “không tồn tại” với TTL ngắn cho ID đã được nguồn xác nhận là không có. Cần xóa hoặc làm hết hiệu lực sentinel khi đối tượng được tạo.

Không cache timeout, lỗi quyền hoặc lỗi database như “không tìm thấy”. Cũng không dùng chung kết quả “không có” giữa các phạm vi quyền nếu câu trả lời thực tế phụ thuộc người gọi.

Negative cache không thay thế rate limit: các ID ngẫu nhiên khác nhau liên tục vẫn có thể tạo tải vào database và bộ nhớ.

## 8. Giữ database ổn định khi cache lỗi

### 8.1. Fallback phải có giới hạn

“Redis lỗi thì đọc database” là một đường xử lý, chưa phải một phương án sẵn sàng cao hoàn chỉnh.

Cần phối hợp:

- **Timeout cache:** nằm trong ngân sách thời gian của request.
- **Circuit breaker:** tạm bỏ qua cache khi lỗi kéo dài, tránh chờ lặp ở từng request.
- **Bulkhead:** giới hạn số tác vụ fallback đang dùng database.
- **Rate limit hoặc admission control:** giới hạn lượng công việc nhận vào.
- **Load shedding:** từ chối có kiểm soát khi không đủ công suất.
- **Stale fallback:** chỉ với dữ liệu còn nằm trong mức độ cũ được phép.

Circuit breaker Redis chỉ giảm thời gian chờ Redis. Nó không tự giảm tải database sau khi chuyển toàn bộ lưu lượng sang fallback.

Nếu giới hạn fallback nằm ở từng app instance, phải tính tổng khi ứng dụng autoscale. Mười instance cùng cho phép một mức concurrency nhỏ vẫn có thể vượt ngân sách database tổng thể.

### 8.2. Mã giả cho một luồng đọc được bảo vệ

~~~text
đọc mô tả sản phẩm:
    xác thực và kiểm tra quyền
    tạo key theo môi trường, tenant và schema

    nếu cache circuit cho phép:
        thử đọc Redis trong ngân sách cache
        nếu có payload hợp lệ và còn được phép dùng:
            trả kết quả
        nếu cache lỗi:
            ghi nhận lỗi, không coi là một cache miss bình thường

    gộp các yêu cầu cùng key nếu có thể

    nếu không lấy được suất đọc database trong deadline:
        nếu có dữ liệu stale còn được phép:
            trả dữ liệu stale theo hợp đồng
        nếu không:
            từ chối có kiểm soát hoặc đưa vào luồng chờ phù hợp

    trong suất đọc database:
        đọc nguồn với timeout riêng
        nếu database lỗi:
            trả lỗi có kiểm soát hoặc stale được phép
        nếu nguồn xác nhận không tồn tại:
            cân nhắc negative cache có TTL ngắn
        nếu có dữ liệu:
            thử ghi cache với TTL và giao thức nạp đã chọn
            nếu ghi cache lỗi:
                ghi nhận lỗi; không xóa kết quả đọc thành công
            trả dữ liệu nguồn
~~~

Mã giả không phải SDK OCI hoặc thư viện Redis cụ thể. Nó thể hiện thứ tự trách nhiệm và nơi cần giới hạn.

### 8.3. Phân loại hành vi khi lỗi

| Sự cố | Hành vi mong đợi |
| --- | --- |
| Redis timeout hoặc tạm không kết nối | Fallback có ngân sách, không retry vô hạn |
| Cache miss hoặc key bị evict | Nạp lại có chống trùng và giới hạn database |
| Cache SET thất bại sau khi đọc DB thành công | Trả kết quả nguồn, ghi metric lỗi cache write |
| Database commit thành công, DEL thất bại | Giữ trạng thái giao dịch đã commit và xử lý invalidation bền vững |
| Database lỗi, có stale được phép | Phục vụ suy giảm theo hợp đồng và có giới hạn tuổi |
| Database lỗi, dữ liệu đòi hỏi độ đúng chặt | Báo không thể hoàn tất; không bịa trạng thái |
| Cả cache và database bị quá tải | Admission control, ưu tiên chức năng quan trọng, tránh hàng đợi vô hạn |

Không cấu hình liveness của mọi app instance thất bại chỉ vì tầng cache dùng để tăng tốc đang tạm lỗi. Việc restart hàng loạt có thể làm mất L1, tạo kết nối mới và khiến quá trình phục hồi khó hơn. Health check cần phản ánh vai trò thật của từng dependency.

## 9. Replica, failover và client trên OCI

### 9.1. Replica không bảo đảm dữ liệu mới tức thời

Redis replication thông thường là bất đồng bộ. Replica có thể trễ và một số ghi gần thời điểm lỗi có thể chưa tới node được đưa lên primary. [Redis replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/).

Với cache có thể tái tạo, mất một phần dữ liệu cache có thể được chấp nhận nếu database vẫn là nguồn đúng. Tuy nhiên, mất một lệnh invalidation hoặc đọc từ replica chậm có thể làm dữ liệu cũ xuất hiện lại; TTL và quy trình đồng bộ vẫn cần được xem xét.

Đọc replica chỉ phù hợp với mức nhất quán ứng dụng chấp nhận. Nếu vừa cập nhật dữ liệu rồi cần đọc kết quả mới ngay, không mặc định endpoint replica sẽ đáp ứng.

### 9.2. Dùng đúng endpoint

Với non-sharded cluster:

- **Primary endpoint** hướng tới node đang giữ vai trò primary.
- **Replicas endpoint** hướng tới replica và không nhất thiết luôn cùng một node.
- **Node endpoint** gắn với node cụ thể, nên không dùng thay primary endpoint nếu cần luôn gọi primary.

Với sharded cluster, client cần hỗ trợ cluster mode, hostname và discovery/topology phù hợp. [Connecting to an OCI Cache Cluster](https://docs.oracle.com/en-us/iaas/Content/ocicache/connecttocluster.htm), [OCI Cache Sharded Clusters](https://docs.oracle.com/en-us/iaas/Content/ocicache/shardedclusters.htm).

Không đóng đinh địa chỉ IP của primary hiện tại. Client cần xử lý kết nối cũ, DNS và topology thay đổi theo cách thư viện hỗ trợ.

### 9.3. Tái sử dụng kết nối và retry có giới hạn

Với ứng dụng Java, chọn client tương thích với TLS và chế độ cluster đang dùng; tài liệu OCI đề cập các lựa chọn như Lettuce và Redisson. Cần kiểm tra phiên bản thư viện trước khi triển khai. [OCI Cache Client Best Practices](https://docs.oracle.com/en-us/iaas/Content/ocicache/ocicachebestpractices.htm).

Tái sử dụng client hoặc connection theo hướng dẫn của thư viện, giới hạn pool, command timeout và lượng chờ. Không tạo một client mới cho mỗi HTTP request.

Retry phải nằm trong deadline tổng và phù hợp với thao tác. Lặp SET có thể thay đổi thời điểm hết hạn; retry những thao tác tăng/giảm số không có cùng ý nghĩa với retry GET. Không suy ra mọi lệnh Redis đều có thể lặp an toàn như nhau.

Failover có thể làm đứt các kết nối đang dùng; “managed failover” không có nghĩa mọi request ứng dụng đều hoàn tất mà không bị gián đoạn.

## 10. Bộ nhớ, eviction và phân mảnh dữ liệu

### 10.1. Tính working set thay vì toàn bộ database

Ước lượng ban đầu:

~~~text
Bộ nhớ cache cần xem xét ≈
    số key hoạt động × kích thước key và payload
  + metadata và cấu trúc dữ liệu
  + buffer, kết nối và overhead
  + phần dự phòng cho dao động và vận hành
~~~

Một triệu payload khoảng 1 KiB đã tạo gần 1 GiB dữ liệu giá trị, trước khi cộng key và overhead. Dữ liệu nén ở nguồn hoặc kích thước JSON trên đĩa không tự tương đương dung lượng Redis cần dùng.

Đo trên dữ liệu đại diện: phân bố kích thước, số trường, thời gian sống và tần suất truy cập. Tránh value quá lớn gây tốn băng thông và làm một thao tác chiếm tài nguyên lâu.

### 10.2. Phân biệt expiration với eviction

- **Expiration:** key hết thời hạn theo TTL.
- **Eviction:** key bị loại để đáp ứng chính sách bộ nhớ.
- **Invalidation:** ứng dụng chủ động loại dữ liệu không còn phù hợp.

Redis có các nhóm chính sách như LRU, LFU, chính sách chỉ áp dụng key có TTL hoặc noeviction. Với noeviction, thao tác cần thêm bộ nhớ có thể bị từ chối khi không đủ chỗ. [Redis Key Eviction](https://redis.io/docs/latest/reference/eviction/).

OCI Cache chỉ cho phép điều chỉnh tập cấu hình mà dịch vụ hỗ trợ. Không lấy hướng dẫn CONFIG SET trên một Redis tự quản lý làm giả định rằng có thể áp dụng y hệt trên OCI Cache. [Supported Configurations for OCI Cache](https://docs.oracle.com/en-us/iaas/Content/ocicache/supported-configurations.htm).

Tách workload cache có thể evict khỏi dữ liệu có vòng đời khác như session hoặc cơ chế điều phối quan trọng khi cần. Cùng dùng Redis không có nghĩa chúng phù hợp dùng chung chính sách bộ nhớ và phạm vi lỗi.

### 10.3. Replica không nhân dung lượng dữ liệu duy nhất

Một non-sharded cluster có ba node sao chép cùng dữ liệu không có nghĩa chứa được ba lần working set của một node.

Sharding mới chia dữ liệu giữa các shard. Tuy nhiên, thêm shard không tự chia nhỏ một hot key và không sửa được phân bố truy cập lệch. Các thao tác nhiều key hoặc script còn phải đáp ứng quy tắc slot của chế độ cluster.

Khi dùng hash tag để đặt các key liên quan cùng slot, giới hạn theo thực thể hoặc nhóm phù hợp. Một hash tag chung cho toàn bộ ứng dụng có thể dồn dữ liệu vào một shard.

## 11. IAM, xác thực và bảo vệ dữ liệu cache

### 11.1. Phân biệt quyền quản lý với quyền đọc dữ liệu

| Lớp | Nội dung cần bảo vệ |
| --- | --- |
| **OCI IAM quản lý tài nguyên** | Ai tạo, sửa, thay kích thước hoặc xóa cluster |
| **Mạng** | Workload nào kết nối được tới private endpoint |
| **Xác thực và quyền cache** | Danh tính nào được thực hiện thao tác dữ liệu |
| **Ứng dụng** | Người gọi được phép xem tenant, đối tượng và trường nào |
| **Bí mật và log** | Ai xem token, thông tin kết nối và dữ liệu được ghi nhận |

Có IAM policy tạo cluster không tự đồng nghĩa đã được phép đọc mọi dữ liệu trong Redis. Kết nối TLS thành công cũng không thay thế xác thực hoặc kiểm tra quyền nghiệp vụ.

OCI Cache có cơ chế người dùng cache và IAM authentication bằng token ngắn hạn theo cấu hình. Nếu chọn cơ chế này, client phải tích hợp quy trình cấp và làm mới token phù hợp. [OCI Cache Users](https://docs.oracle.com/en-us/iaas/Content/ocicache/cache-users.htm), [IAM Authentication for OCI Cache](https://docs.oracle.com/en-us/iaas/Content/ocicache/iam-authentication.htm).

### 11.2. Giới hạn đường mạng và thao tác

- Cho phép kết nối từ nguồn ứng dụng cần thiết bằng NSG hoặc security list.
- Bật kiểm tra chứng thư TLS, dùng hostname đúng.
- Không đưa endpoint hoặc thông tin xác thực vào URL công khai, log hoặc repository.
- Giới hạn quyền xóa hàng loạt và thay cấu hình theo khả năng dịch vụ.
- Cấu hình quyền đọc/ghi cần thiết, không mặc định ứng dụng cần mọi lệnh quản trị.

Nếu có L1 trong bộ nhớ ứng dụng, cần xử lý invalidation và TTL của L1 riêng. Xóa key ở Redis chưa chắc đã xóa bản sao mà một app instance đang giữ.

Dữ liệu cache, bản backup và log vận hành vẫn thuộc phạm vi quản trị dữ liệu. TTL của key không tự làm mọi bản sao hoặc log hết hạn cùng lúc.

## 12. Giám sát hiệu quả giảm tải và khả năng phục hồi

OCI Cache phát metric trong namespace **oci_redis**. Các metric chủ yếu theo node, vì vậy cần quan sát đúng tài nguyên và topology. [OCI Cache Metrics](https://docs.oracle.com/en-us/iaas/Content/ocicache/metrics.htm).

| Metric dịch vụ tiêu biểu | Câu hỏi hỗ trợ trả lời |
| --- | --- |
| **KeyspaceHits / KeyspaceMisses** | Key lookup thành công hoặc không tìm thấy |
| **UsedMemory / MemoryUtilization** | Bộ nhớ có gần giới hạn không |
| **EvictedKeys / ExpiredKeys** | Key bị loại vì bộ nhớ hay hết TTL |
| **ConnectedClients** | Kết nối có tăng bất thường không |
| **CPUUtilization** | Node có chịu tải xử lý lớn không |
| **NetworkBytesIn / NetworkBytesOut** | Có áp lực truyền dữ liệu không |
| **ReplicationLag** | Replica có bị chậm hơn primary không |

Không lấy trung bình hit ratio của các node rồi coi đó là tỷ lệ toàn hệ thống nếu lượng truy cập khác nhau. Cần tổng hợp số hit/miss theo cùng khoảng thời gian và đúng cách metric được phát. Nếu sử dụng counter tích lũy từ công cụ khác, phải xử lý chênh lệch và reset.

Metric ứng dụng cần bổ sung:

- Số lookup hợp lệ, hit, miss, lỗi cache và bypass có chủ đích.
- Độ trễ cache và p95/p99 toàn luồng.
- Lượt đọc database theo nguyên nhân: miss, refresh, fallback.
- Lượng request được single-flight gộp, bị chờ hoặc bị từ chối.
- Lỗi ghi cache và độ trễ xử lý invalidation.
- Số lượt phục vụ stale và tuổi dữ liệu theo hợp đồng.
- Tải database, thời gian truy vấn và mức sử dụng connection pool.

Cache timeout phải được tách khỏi cache miss. Trong timeout, ứng dụng không biết key có tồn tại hay không.

Một dashboard hữu ích đặt hit ratio, cache error, DB QPS, DB latency và độ trễ ứng dụng trên cùng trục thời gian. Khi eviction tăng rồi miss và DB latency cùng tăng, có bằng chứng để điều tra working set hoặc chính sách bộ nhớ.

Alarm nên dẫn đến hành động: giới hạn warm-up, kiểm tra node/shard nóng, xác minh client reconnect hoặc giảm tải fallback. Không chỉ cảnh báo bộ nhớ mà bỏ qua database đang gần cạn kết nối.

## 13. Khôi phục, warm-up và chi phí

### 13.1. Warm-up không được trở thành tác vụ gây quá tải

Sau rollout namespace mới, sự cố cache hoặc chuyển region, cache có thể lạnh. Warm-up nên:

1. Ưu tiên một tập key nóng có giá trị.
2. Có giới hạn concurrency và tốc độ đọc database.
3. Giảm hoặc dừng khi database vượt ngưỡng bảo vệ.
4. Tránh nhiều app instance cùng nạp toàn bộ tập dữ liệu.
5. Đo thời gian hit ratio và độ trễ trở lại mức mục tiêu.

Không cần nạp toàn bộ database vào Redis chỉ vì cache đang trống. Dữ liệu ít được dùng có thể làm key nóng bị evict và tăng chi phí mà không giảm tải đáng kể.

### 13.2. Backup cache không thay thế backup database

OCI Cache có các khả năng backup/restore theo cấu hình được hỗ trợ. Với cache có thể tái tạo, backup có thể hỗ trợ khôi phục nhanh hơn nhưng không thay thế tính bền vững và phương án phục hồi của Oracle Database. [OCI Cache Backup and Restore](https://docs.oracle.com/en-us/iaas/Content/ocicache/backup-restore.htm).

Khi phục hồi một bản cache cũ, phải xét những cập nhật và invalidation sau thời điểm backup. Có thể cần đổi namespace, đối chiếu version hoặc xây lại dữ liệu trước khi phục vụ.

Nếu chọn cơ chế sao chép cache giữa region, vẫn cần kế hoạch chuyển ứng dụng, nguồn dữ liệu, quyền và đường mạng. Cache được sao chép không tự hoàn tất disaster recovery của toàn hệ thống.

### 13.3. So sánh chi phí toàn bộ giải pháp

Chi phí cần xem xét gồm bộ nhớ/công suất các node, replica, shard, kết nối mạng, giám sát, lưu trữ backup và quy trình vận hành. Đối chiếu SKU và đơn vị tính hiện hành trong [Oracle Cloud Price List](https://www.oracle.com/cloud/price-list/).

Tính trên cả:

~~~text
Giá trị giảm tải =
    tài nguyên database hoặc độ trễ được tiết kiệm
  - chi phí cache và phần vận hành bổ sung
~~~

Đây là khung đánh giá, không phải công thức quyết toán tiền. Database có thể vẫn cần giữ công suất dự phòng để chịu suy giảm cache, nên giảm DB QPS không tự chuyển thành mức tiết kiệm tiền tương ứng.

Đo chi phí trên một lượng yêu cầu được phục vụ đạt mục tiêu và kiểm tra cả thời điểm phục hồi. Không giảm replica chỉ để tiết kiệm mà bỏ qua yêu cầu sẵn sàng cao đã đặt ra.

## 14. Thực hành thiết kế và kiểm chứng luồng cache

Các bước sau dành cho người học trong môi trường thử riêng, bằng dữ liệu giả lập hoặc đã được cho phép. Không cần thay đổi cấu trúc database nghiệp vụ để bắt đầu bài thực hành.

### 14.1. Xác định hợp đồng

Chọn API đọc mô tả sản phẩm và ghi rõ:

- Dữ liệu nguồn và phạm vi tenant.
- Mức độ cũ được chấp nhận.
- Điều kiện phải đọc lại database.
- Những key bị ảnh hưởng khi cập nhật.
- Tải database được phép khi cache lạnh hoặc lỗi.
- Mục tiêu độ trễ, tỷ lệ thành công và thời gian phục hồi.

### 14.2. Chuẩn bị tài nguyên và kết nối

1. Chọn compartment, region và cấu hình cluster phù hợp mục tiêu.
2. Với cấu hình HA non-sharded, xem xét khuyến nghị primary và hai replica.
3. Cấu hình kết nối private, NSG/security list, TLS và xác thực.
4. Lấy endpoint từ thông tin cluster, không tự suy ra hostname.
5. Chọn client tương thích; kiểm tra reuse connection và timeout.
6. Xác nhận metric cache cùng chỉ số database có thể quan sát được.

### 14.3. Triển khai cache-aside có giới hạn

1. Dùng prefix riêng cho bài thực hành.
2. Tạo key có tenant, phiên bản schema và các tham số ảnh hưởng kết quả.
3. Đọc cache, xử lý miss qua loader có giới hạn.
4. Ghi value cùng TTL trong một thao tác.
5. Chống nạp trùng theo key.
6. Cập nhật database rồi invalidation sau commit.
7. Ghi nhận riêng cache hit, miss, lỗi và bypass.

### 14.4. So sánh các tình huống

| Tình huống thử | Bằng chứng cần thu |
| --- | --- |
| Không dùng cache | DB QPS, thời gian truy vấn, p95/p99 ứng dụng |
| Cache lạnh | Tốc độ nạp, tải database, request bị giới hạn |
| Cache nóng | Hit ratio, mức giảm DB reads, độ trễ |
| Nhiều request vào cùng key hết hạn | Lượng loader thực sự chạy và tải database |
| Nhiều key hết hạn gần nhau | Hiệu quả jitter và giới hạn refresh |
| Đọc cạnh tranh với cập nhật | Phiên bản dữ liệu và cửa sổ stale |
| Không kết nối được cache trong môi trường thử | Circuit breaker, fallback budget, load shedding |
| Failover hoặc đổi topology theo thao tác được hỗ trợ | Reconnect, lỗi tạm thời và thời gian hồi phục |
| Dữ liệu vượt working set dự kiến | Eviction, lỗi ghi cache và tác động lên database |

Không dùng riêng hit ratio làm điều kiện đạt. Quan trọng là database không sụp khi cache mất tác dụng và ứng dụng không phục vụ dữ liệu ngoài hợp đồng.

### 14.5. Điều kiện hoàn tất thiết kế

| Câu hỏi | Bằng chứng mong đợi |
| --- | --- |
| Mất cache có làm mất giao dịch nghiệp vụ không? | Dữ liệu có thẩm quyền vẫn nằm ở database |
| Có biết lúc nào dữ liệu cũ được chấp nhận không? | Hợp đồng TTL, stale và bypass |
| Invalidation có xử lý lỗi sau commit không? | Outbox, CDC hoặc cơ chế retry có kiểm soát |
| Có xử lý nạp lại dữ liệu cũ do race không? | Phân tích timeline và mức nhất quán được chấp nhận |
| Cache lạnh có làm quá tải database không? | Giới hạn loader, fallback và warm-up |
| Client có theo được failover không? | Endpoint, reconnect và cấu hình topology |
| Bộ nhớ và chi phí có phù hợp không? | Đo working set, overhead và replica/shard |
| Có điều tra được sự cố không? | Metric cache, application, database và runbook |

Một tầng Redis được thiết kế tốt giảm phần việc lặp lại cho Oracle Database, đồng thời giữ được đường phục vụ có kiểm soát khi cache trống, cũ hoặc tạm không sẵn sàng. Đó là vai trò của cache trong kiến trúc sẵn sàng cao trên OCI.
