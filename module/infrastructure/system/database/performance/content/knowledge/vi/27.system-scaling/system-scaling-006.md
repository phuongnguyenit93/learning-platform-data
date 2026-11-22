# Chia dữ liệu (sharding): chọn khóa và giới hạn của truy vấn nhiều phân mảnh

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích sharding phân phối dữ liệu theo chiều ngang qua nhiều node và khác gì với partitioning trong một hệ quản trị.
- Chọn shard key dựa trên mẫu truy vấn, độ phân bố, tính ổn định, khả năng định tuyến và tăng trưởng dữ liệu.
- So sánh range sharding, hash sharding và directory-based sharding.
- Thiết kế truy vấn single-shard để tận dụng locality và nhận diện truy vấn phải fan-out.
- Đánh giá giới hạn của JOIN, aggregate, sort, pagination, uniqueness và transaction trên nhiều shard.
- Lập kế hoạch phân phối lại dữ liệu, quan sát skew và benchmark hiệu năng ở cấp toàn cụm.

## 1. Sharding giải quyết bài toán mở rộng nào?

Sharding là kỹ thuật chia dữ liệu theo chiều ngang thành nhiều tập con và đặt các tập đó trên các node cơ sở dữ liệu khác nhau. Mỗi node hoặc nhóm node quản lý một phần dữ liệu, thường gọi là shard. Khi ứng dụng gửi thao tác, lớp định tuyến xác định shard chứa bản ghi cần đọc hoặc ghi.

Ví dụ, một hệ thống có 300 triệu tài khoản có thể chia dữ liệu thành 12 shard. Mỗi shard quản lý một phần account và giao dịch liên quan. Tổng dung lượng và khả năng xử lý có thể tăng khi bổ sung node, nếu workload phân phối tương đối đều và ứng dụng định tuyến hiệu quả.

Trong phạm vi DATABASE_PERFORMANCE, sharding là một lựa chọn mở rộng sau khi đã hiểu workload, access path, I/O, memory, transaction contention và giới hạn tài nguyên. Sharding có thể tăng tổng CPU, RAM, storage và throughput bằng cách phân phối tải, nhưng tạo thêm chi phí định tuyến, fan-out, đồng bộ, vận hành và xử lý truy vấn xuyên shard.

Sharding không tự làm một truy vấn nhanh hơn. Truy vấn có shard key phù hợp có thể đi đến một shard và tận dụng dữ liệu cục bộ. Truy vấn không có shard key có thể phải gửi đến nhiều shard, chờ các kết quả rồi hợp nhất. Với truy vấn loại này, số node tăng có thể làm công việc tổng thể tăng thay vì giảm.

## 2. Partitioning và sharding khác nhau thế nào?

Partitioning thường chia một bảng logic thành các phân vùng được một hệ quản trị hoặc một cụm quản lý. Sharding phân phối các tập dữ liệu qua nhiều node độc lập hoặc nhiều đơn vị lưu trữ có khả năng mở rộng riêng.

| Tiêu chí | Partitioning | Sharding |
| --- | --- | --- |
| Vị trí dữ liệu | Các partition do cùng hệ quản trị/cụm quản lý | Các shard đặt trên nhiều node hoặc nhóm node |
| Định tuyến | Optimizer/partition manager thường xử lý pruning | Ứng dụng, proxy hoặc lớp phân tán định tuyến theo shard key |
| Tài nguyên | Thường vẫn dùng chung tài nguyên của máy/cụm | Có thể cộng thêm CPU, RAM, I/O và dung lượng bằng node mới |
| Truy vấn thiếu khóa | Có thể quét nhiều partition trong cùng hệ quản trị | Có thể fan-out qua nhiều shard và hợp nhất kết quả |
| Giao dịch | Thường nằm trong một miền transaction | Giao dịch nhiều shard có thể cần coordinator hoặc saga |
| Vận hành | Quản lý partition, index, statistics và retention | Thêm shard map, rebalance, routing, cross-shard query và failure handling |

Một shard có thể tiếp tục partition bảng bên trong node đó. Khi ấy hệ thống có hai tầng: shard routing chọn node, còn partition pruning chọn phần dữ liệu bên trong node.

## 3. Mô hình dữ liệu phân mảnh

Giả sử ứng dụng có bảng tài khoản và giao dịch:

```sql
CREATE TABLE accounts (
    account_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    account_name VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (account_id)
);

CREATE TABLE transfers (
    transfer_id BIGINT NOT NULL,
    source_account_id BIGINT NOT NULL,
    target_account_id BIGINT NOT NULL,
    amount DECIMAL(19, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
```

Khi sharding, các hàng của `accounts` và `transfers` được chia cho nhiều node. Một thiết kế có thể đặt mọi tài khoản của cùng tenant vào một shard, hoặc phân phối theo account ID. Lựa chọn này quyết định:

- Truy vấn theo tenant có thể được xử lý tại một shard hay không.
- Chuyển tiền giữa hai tài khoản có thể nằm cùng shard hay phải phối hợp nhiều shard.
- Một tenant lớn có thể tạo shard nóng hay không.
- Báo cáo toàn hệ thống cần fan-out bao nhiêu node.
- Khóa ngoại, uniqueness và transaction có thể được kiểm tra cục bộ hay không.

Shard key vì thế là một quyết định kiến trúc dữ liệu và hợp đồng truy vấn của ứng dụng, không chỉ là một cột dùng để chia đều số hàng.

## 4. Tiêu chí chọn shard key

Một shard key tốt cần cân bằng nhiều mục tiêu:

1. **Query locality:** phần lớn truy vấn quan trọng có thể cung cấp shard key và đi đến một shard hoặc một nhóm shard nhỏ.
2. **Phân bố tải:** giá trị khóa phân phối số hàng, dung lượng, CPU và I/O tương đối đều.
3. **Phân bố ghi:** tránh dồn phần lớn INSERT/UPDATE vào một shard hoặc một vài khóa nóng.
4. **Tính ổn định:** khóa ít thay đổi trong vòng đời bản ghi để tránh di chuyển dữ liệu thường xuyên.
5. **Khả năng tăng trưởng:** dữ liệu và traffic của một giá trị khóa không vượt quá khả năng một shard.
6. **Ràng buộc nghiệp vụ:** các bản ghi thường cần JOIN hoặc cập nhật cùng transaction có thể được đặt gần nhau.
7. **Khả năng định tuyến:** ứng dụng có thể biết shard từ request mà không phải tra cứu tốn kém cho mọi thao tác.
8. **Bảo mật và cô lập:** nếu chia theo tenant hoặc vùng, cần bảo đảm cách phân phối phù hợp ranh giới dữ liệu.

Không có shard key tối ưu cho mọi loại truy vấn. Hãy xếp hạng các query pattern theo tỷ lệ request, độ trễ mục tiêu và chi phí; chọn khóa hỗ trợ phần lớn workload quan trọng, rồi thiết kế đường xử lý riêng cho truy vấn ngoại lệ.

## 5. Chọn theo query pattern, không chỉ theo cardinality

Một cột có nhiều giá trị khác nhau chưa chắc là shard key tốt. Điều quan trọng là ứng dụng có thường biết giá trị đó khi truy vấn hay không.

Ví dụ:

- `tenant_id` có thể có cardinality cao và xuất hiện trong hầu hết API B2B. Nó có thể tạo locality tốt cho truy vấn trong một tenant.
- `created_at` thường có trong truy vấn báo cáo theo thời gian, nhưng nếu ghi dữ liệu mới luôn vào shard chứa khoảng thời gian mới nhất thì shard đó có thể nóng.
- `account_id` có thể phân phối tốt và hỗ trợ lookup tài khoản, nhưng truy vấn tổng hợp theo tenant có thể phải fan-out.
- `status` có ít giá trị và phân bố lệch, nên thường không phù hợp làm shard key duy nhất.

Trước khi chọn, lập bảng query pattern:

| Query pattern | Tỷ trọng | Khóa thường có | Mục tiêu định tuyến |
| --- | ---: | --- | --- |
| Lấy đơn theo ID trong tenant | 45% | tenant_id, order_id | Một shard |
| Danh sách đơn của tenant theo ngày | 30% | tenant_id, created_at | Một shard hoặc partition cục bộ |
| Báo cáo toàn tenant | 15% | tenant_id | Một shard nếu dữ liệu tenant được colocate |
| Báo cáo toàn hệ thống | 8% | khoảng ngày, không có tenant | Nhiều shard, tổng hợp kết quả |
| Tra cứu theo email toàn hệ thống | 2% | email | Cần global lookup/index hoặc định tuyến phụ |

Các tỷ lệ chỉ là ví dụ. Query pattern hiếm nhưng có SLA quan trọng vẫn cần được thiết kế; không nên để một truy vấn vận hành thiết yếu trở thành fan-out không kiểm soát.

## 6. Range sharding

Range sharding chia miền khóa thành các khoảng và ánh xạ mỗi khoảng vào một shard. Ví dụ:

```text
Shard A: customer_id  1 - 1,000,000
Shard B: customer_id  1,000,001 - 2,000,000
Shard C: customer_id  2,000,001 - 3,000,000
Shard D: customer_id  3,000,001 - 4,000,000
```

Ưu điểm:

- Truy vấn theo khoảng khóa có thể chỉ đến một vài shard.
- Dữ liệu liền kề nằm gần nhau, thuận lợi cho range scan và một số báo cáo.
- Có thể chuyển một khoảng dữ liệu sang shard khác theo đơn vị rõ ràng.

Nhược điểm:

- Các khoảng có thể có kích thước hoặc tải không đều.
- Khóa tăng tuần tự có thể dồn ghi mới vào shard cuối.
- Một tenant hoặc nhóm khóa lớn có thể vượt capacity của shard chứa khoảng đó.
- Thay đổi ranh giới cần di chuyển dữ liệu và cập nhật routing metadata.

Range sharding phù hợp khi truy vấn theo khoảng là phổ biến và phân bố dữ liệu có thể quản lý. Cần giám sát kích thước và throughput từng range; không giả định mỗi khoảng chứa số hàng bằng nhau.

## 7. Hash sharding

Hash sharding áp dụng hàm băm lên shard key rồi ánh xạ kết quả vào một số shard hoặc bucket.

Ví dụ khái quát:

```text
bucket = hash(tenant_id) mod 16
shard  = bucket_map[bucket]
```

Ưu điểm:

- Có thể phân phối giá trị khóa tương đối đều khi hàm băm và tập khóa phù hợp.
- Tránh hotspot do khóa tăng tuần tự nếu các giá trị hash được phân bố tốt.
- Equality lookup theo shard key dễ định tuyến.

Nhược điểm:

- Truy vấn theo khoảng giá trị của khóa thường phải fan-out.
- Thay đổi số shard bằng phép modulo trực tiếp có thể làm phần lớn key đổi vị trí.
- Hash không giải quyết hot key nếu một giá trị duy nhất nhận lượng truy cập vượt trội.

Hash sharding phù hợp với workload lookup theo equality và cần phân phối tải. Với dữ liệu theo tenant, hash tenant ID có thể phân phối tenant giữa các shard, nhưng một tenant cực lớn vẫn nằm trên một shard nếu không có tầng chia nhỏ khác.

## 8. Directory-based sharding

Directory-based sharding dùng một bảng hoặc dịch vụ định tuyến để ánh xạ key/tenant/bucket đến shard.

```text
tenant_id -> directory -> shard_id
```

Ưu điểm:

- Có thể di chuyển tenant hoặc nhóm dữ liệu mà không phụ thuộc công thức hash cố định.
- Hỗ trợ phân shard đặc biệt cho tenant lớn hoặc tenant có yêu cầu riêng.
- Cho phép thay đổi mapping theo từng giai đoạn.

Nhược điểm:

- Mỗi lần định tuyến có thể cần lookup directory hoặc cache mapping.
- Directory trở thành thành phần quan trọng cần HA, backup và quan sát.
- Cache shard map có thể stale trong lúc rebalance.
- Cần xử lý phiên bản mapping, chuyển tiếp request và ghi trong giai đoạn di chuyển.

Directory phù hợp khi cần tính linh hoạt, phân phối tenant không đồng đều hoặc có shard placement theo chính sách. Cần thiết kế cache, invalidation và behavior khi directory không truy cập được.

## 9. Virtual shards và consistent hashing

Một hệ thống có thể chia key space thành nhiều virtual shard/bucket hơn số node vật lý. Ví dụ 1.024 bucket được ánh xạ vào 16 node. Khi thêm node, hệ thống chuyển một phần bucket sang node mới thay vì tính lại mapping trực tiếp trên toàn bộ key.

Virtual shard giúp:

- Tách khái niệm đơn vị dữ liệu logic khỏi node vật lý.
- Chuyển từng bucket có kiểm soát.
- Cân bằng lại dung lượng và tải theo nhiều bước.
- Hỗ trợ node có capacity khác nhau bằng cách gán số bucket khác nhau.

Consistent hashing là một họ kỹ thuật ánh xạ key vào vòng hash để giảm số key phải remap khi node thay đổi. Virtual nodes giúp phân bố vị trí node trên vòng tốt hơn.

Consistent hashing không tự cân bằng dữ liệu theo dung lượng hoặc traffic. Nếu một shard có tenant lớn hoặc hot key, chỉ thay đổi vị trí trên vòng không làm tải tự chia đều. Cần đo skew và có chiến lược tách tenant/bucket nóng.

## 10. Shard key, primary key và uniqueness

Khi dữ liệu phân tán, unique constraint cục bộ trên một shard không tự bảo đảm uniqueness toàn hệ thống.

Ví dụ, mỗi shard có thể có `UNIQUE(email)`. Nếu cùng email được ghi đồng thời vào hai shard khác nhau, cả hai shard đều có thể chấp nhận vì mỗi nơi chỉ nhìn thấy dữ liệu cục bộ.

Các cách xử lý:

- Đưa tất cả bản ghi cần duy nhất theo email về cùng shard bằng email-derived key.
- Dùng global unique ID được cấp bởi cơ chế phân tán phù hợp.
- Dùng global directory/unique service để kiểm tra và đặt chỗ khóa trước khi ghi.
- Đưa uniqueness vào một miền dữ liệu trung tâm nếu chi phí và throughput cho phép.

Khóa chính thường nên chứa shard key hoặc có cấu trúc giúp định tuyến và bảo đảm uniqueness trong shard. Nếu dùng ID toàn cục như UUID hoặc ID phân tán, uniqueness xác suất/toàn cục vẫn cần được hiểu đúng; foreign key và local index vẫn cần thiết.

### Global secondary index

Khi cần tìm bản ghi theo một thuộc tính không phải shard key, có thể duy trì global secondary index hoặc directory phụ:

```text
email -> tenant_id, shard_id, customer_id
```

Tra cứu email trước để lấy shard, sau đó đọc customer tại shard đó. Đổi lại, index phụ phải được cập nhật nhất quán với dữ liệu gốc, có thể trở thành bottleneck và cần xử lý stale entry, retry, delete và migration.

Không coi global index là miễn phí. Nó tạo thêm đường ghi, storage, replication và một thành phần cần đảm bảo sẵn sàng.

## 11. Colocation: đặt dữ liệu thường dùng cùng nhau

Colocation là thiết kế để các hàng thường được truy vấn hoặc cập nhật cùng nhau nằm trên cùng shard.

Ví dụ, nếu một tenant có khách hàng, đơn hàng và chi tiết đơn, đặt các bảng này theo cùng `tenant_id` có thể cho phép:

- JOIN customer với order tại cùng shard.
- Đọc đơn và item trong một transaction cục bộ.
- Tạo foreign key cục bộ nếu hệ quản trị hỗ trợ trong phạm vi shard.
- Tính tổng đơn của một tenant mà không fan-out toàn cụm.

Để colocation hoạt động, các bảng cần dùng cùng quy tắc mapping và join predicate chứa shard key tương ứng. Nếu chỉ một bảng được sharding theo tenant còn bảng khác phân phối theo order ID, JOIN có thể trở thành cross-shard.

Colocation có thể làm một shard lớn nếu một tenant phát triển quá mạnh. Cần có phương án cho tenant lớn như sub-shard theo tenant ID cộng với account/order bucket, hoặc tách tenant đó sang shard riêng bằng directory.

## 12. Định tuyến truy vấn đến shard

Lớp routing cần phân tích request/query để xác định shard đích. Có thể đặt ở:

- Thư viện client trong ứng dụng.
- Database proxy hoặc gateway.
- Middleware/data access layer.
- Query coordinator của nền tảng database phân tán.

Một truy vấn có equality predicate trên shard key thường có thể định tuyến đến một shard:

```sql
SELECT order_id, status, total_amount
FROM orders
WHERE tenant_id = ?
  AND order_id = ?;
```

Nếu `tenant_id` là shard key và mọi bảng order được colocate theo tenant, router có thể chọn đúng một shard.

Truy vấn không có shard key:

```sql
SELECT order_id, status, total_amount
FROM orders
WHERE status = 'PENDING';
```

có thể phải gửi đến tất cả shard vì mỗi shard có thể chứa đơn PENDING. Router không thể suy ra vị trí chỉ từ status nếu không có index/directory bổ sung.

### Shard key cần hiện diện ở tầng ứng dụng

Thiết kế API nên truyền tenant/account/shard context rõ ràng thay vì yêu cầu data access layer tìm kiếm toàn cụm mỗi lần.

Ví dụ:

```java
public Order findOrder(long tenantId, long orderId) {
    Shard shard = shardRouter.forTenant(tenantId);
    return orderRepository.findById(shard, tenantId, orderId);
}
```

Đây là pseudocode. Trong hệ thống thật, shard context phải được xác thực từ danh tính và quyền truy cập, không tin trực tiếp tenant ID do client gửi. Nếu router nhận sai tenant context, có thể gây lộ dữ liệu chéo tenant.

## 13. Single-shard query và multi-shard query

**Single-shard query** được định tuyến đến một shard. Nó thường có thể dùng transaction local, index local và latency gần với database node đó cộng chi phí routing/network.

**Multi-shard query** cần truy cập hai hoặc nhiều shard. Có thể là:

- Query có điều kiện khớp một tập shard đã biết.
- Scatter-gather đến tất cả shard rồi hợp nhất.
- Query phân tán có coordinator đẩy một phần phép tính xuống từng shard.
- JOIN hoặc aggregate cần dữ liệu từ nhiều shard.

Single-shard thường dễ tối ưu và dự đoán hơn. Multi-shard tạo thêm network round trip, fan-out, merge, timeout coordination và tail latency.

## 14. Fan-out và chi phí truy vấn nhiều shard

Fan-out là việc một request được gửi đến nhiều shard. Nếu một truy vấn fan-out đến N shard, hệ thống cần quản lý N request con, kết quả trả về và bước tổng hợp.

Chi phí gồm:

- Network request/response tới từng shard.
- CPU và I/O thực thi tại mỗi shard.
- Connection và concurrency trên toàn cụm.
- Bộ nhớ để giữ kết quả trung gian.
- Thời gian chờ shard chậm nhất nếu cần tất cả kết quả.
- Xử lý lỗi khi một số shard timeout hoặc unavailable.

Nếu router gửi song song, thời gian hoàn tất thường bị chi phối bởi shard chậm nhất cộng chi phí merge. Khi số shard tăng, xác suất ít nhất một shard có tail latency cao cũng tăng. Nếu gửi tuần tự, latency có thể gần tổng thời gian các shard.

Fan-out còn nhân tải. Một request 100 lần/giây đến 20 shard có thể tạo khoảng 2.000 query con/giây nếu tất cả shard đều được gọi. Nhiều request fan-out đồng thời có thể làm cả cụm bão hòa.

### Giới hạn fan-out

Thiết kế cần có:

- Giới hạn số shard tối đa cho một request.
- Giới hạn số request con chạy đồng thời.
- Deadline chung và timeout cho từng shard.
- Cancellation khi request gốc đã hết hạn.
- Backpressure và queue giới hạn.
- Chính sách partial result rõ ràng nếu nghiệp vụ cho phép.
- Circuit breaker hoặc cơ chế cô lập shard lỗi.

Không gửi fan-out không giới hạn chỉ vì có thể tạo nhiều future/thread. Cần tính tổng số request con mà một đợt tải có thể tạo ra.

## 15. Truy vấn nhiều shard với ORDER BY và LIMIT

Giả sử cần lấy 20 đơn mới nhất trên toàn hệ thống. Nếu dữ liệu nằm trên 8 shard, mỗi shard có thể chứa một phần đơn.

Một chiến lược là đẩy `ORDER BY created_at DESC LIMIT 20` xuống từng shard, sau đó merge tối đa 160 ứng viên ở coordinator và chọn 20 hàng đầu toàn cục.

```text
Shard 1: top 20 ----\
Shard 2: top 20 -----\
Shard 3: top 20 ------> merge/sort -> global top 20
Shard ... -----------/
Shard 8: top 20 ----/
```

Đẩy LIMIT xuống shard giúp giảm dữ liệu truyền so với lấy toàn bộ hàng, nhưng coordinator vẫn cần hợp nhất kết quả. Cần có thứ tự xác định và tie-breaker ổn định, ví dụ `(created_at, order_id)`.

Nếu chỉ lấy LIMIT 20 trên từng shard mà không áp dụng cùng thứ tự và không merge đúng, kết quả toàn cục có thể sai.

### Pagination bằng OFFSET

Phân trang sâu bằng `OFFSET 100000 LIMIT 20` có thể tốn kém ngay cả trên một shard. Trên nhiều shard, mỗi shard có thể phải bỏ qua một phần dữ liệu, trả thêm ứng viên và coordinator phải merge.

Offset toàn cục không thể đơn giản gửi cùng offset đến từng shard rồi ghép kết quả. Cần tính vị trí toàn cục sau khi hợp nhất các luồng có thứ tự.

### Keyset pagination

Keyset pagination dùng giá trị cuối của trang trước làm cursor. Với nhiều shard, cursor cần chứa khóa sắp xếp và tie-breaker duy nhất, ví dụ:

```text
cursor = (created_at, order_id)
```

Mỗi shard trả các hàng sau cursor theo cùng thứ tự; coordinator merge các luồng và chọn page tiếp theo. Nếu thứ tự không duy nhất, trang có thể bị trùng hoặc bỏ sót hàng.

Cursor cũng cần xác định snapshot/consistency semantics. Nếu dữ liệu mới được chèn trong lúc người dùng chuyển trang, kết quả có thể thay đổi tùy isolation và cách tạo cursor.

## 16. Aggregate trên nhiều shard

Với các phép tổng hợp có thể kết hợp, mỗi shard tính kết quả cục bộ rồi coordinator hợp nhất.

Ví dụ `COUNT` và `SUM`:

```text
Shard 1: count=100, sum=2500
Shard 2: count=80,  sum=1700
Shard 3: count=50,  sum=900
Coordinator: count=230, sum=5100
```

AVG không nên tính bằng cách lấy trung bình các AVG cục bộ nếu mỗi shard có số hàng khác nhau. Cần tổng hợp `SUM` và `COUNT`, sau đó tính:

```text
global_avg = sum(all shard sums) / sum(all shard counts)
```

COUNT DISTINCT, percentile chính xác, median và một số phép aggregate phức tạp cần trao đổi nhiều dữ liệu hoặc cấu trúc tổng hợp chuyên biệt. Có thể dùng approximate sketches nếu nghiệp vụ chấp nhận sai số và hệ thống có hỗ trợ.

### Group by

Khi GROUP BY theo một thuộc tính không phải shard key, cùng một nhóm có thể xuất hiện ở nhiều shard. Mỗi shard trả partial group, coordinator phải gộp lại theo group key.

Nếu số nhóm rất lớn, dữ liệu trung gian có thể lớn hơn kết quả cuối. Hãy đẩy filter xuống shard, giới hạn khoảng dữ liệu và xem xét pre-aggregation hoặc bảng tổng hợp được cập nhật theo luồng.

## 17. JOIN nhiều shard

JOIN hiệu quả nhất khi hai tập dữ liệu cần nối nằm cùng shard theo một khóa colocation. Khi đó database node có thể dùng nested loop, hash join hoặc merge join cục bộ.

Ví dụ `orders` và `order_items` cùng sharding theo `tenant_id`, truy vấn có điều kiện tenant có thể JOIN cục bộ:

```sql
SELECT o.order_id, i.product_id, i.quantity
FROM orders o
JOIN order_items i
  ON i.tenant_id = o.tenant_id
 AND i.order_id = o.order_id
WHERE o.tenant_id = ?
  AND o.order_id = ?;
```

Trong một số schema, `tenant_id` được lặp trong bảng con để định tuyến và bảo đảm colocation; cần constraint và ứng dụng giữ nhất quán.

### Cross-shard JOIN

Nếu bảng A và B nằm ở các shard khác nhau, hệ thống có thể cần:

- Broadcast bảng nhỏ đến các shard chứa bảng lớn.
- Repartition/shuffle dữ liệu theo join key qua network.
- Gửi nhiều query và JOIN ở application service.
- Duy trì bản sao dimension/reference data trên mỗi shard.

Mỗi phương án có chi phí network, memory, consistency và vận hành. Broadcast bảng nhỏ có thể hợp lý nếu bảng ít thay đổi và kích thước giới hạn; shuffle hàng triệu bản ghi có thể rất đắt.

Tránh JOIN xuyên shard không giới hạn trong request tương tác. Với báo cáo lớn, cân nhắc ETL/warehouse hoặc materialized aggregate phù hợp thay vì buộc OLTP cluster thực hiện cross-shard analytics.

## 18. Giao dịch một shard và nhiều shard

Giao dịch chỉ chạm một shard có thể dùng transaction ACID cục bộ của database node. Đây là lý do thiết kế shard key và colocation nên cố gắng giữ các thao tác nghiệp vụ liên quan trong cùng shard.

Giao dịch nhiều shard cần phối hợp commit giữa nhiều node. Một cơ chế phổ biến là two-phase commit (2PC): coordinator yêu cầu các participant prepare, sau đó commit hoặc rollback theo quyết định chung.

2PC có thể bảo đảm atomicity theo giao thức và hỗ trợ của hệ thống, nhưng tạo thêm:

- Round trip giữa coordinator và từng shard.
- Trạng thái prepared transaction có thể tồn tại khi coordinator lỗi.
- Phụ thuộc vào availability và recovery của coordinator/participant.
- Lock hoặc tài nguyên bị giữ lâu hơn.
- Độ trễ commit và độ phức tạp xử lý timeout.

Không phải nền tảng sharding nào cũng hỗ trợ distributed transaction giống nhau. Cần đọc rõ bảo đảm consistency, isolation, failure recovery và giới hạn phiên bản.

### Saga và eventual consistency

Với quy trình nghiệp vụ kéo dài qua nhiều shard hoặc dịch vụ, saga chia quy trình thành các transaction cục bộ và hành động bù khi một bước thất bại.

Ví dụ chuyển đơn hàng:

1. Tạo đơn và giữ tồn kho tại shard hàng hóa.
2. Ghi yêu cầu thanh toán tại shard thanh toán.
3. Nếu thanh toán thành công, xác nhận đơn.
4. Nếu thất bại, phát hành hành động bù để giải phóng tồn kho.

Saga không tương đương một transaction ACID toàn cục. Trong một khoảng thời gian, các shard có thể ở trạng thái trung gian; API và domain phải hiểu trạng thái đó, hỗ trợ retry và idempotency.

Transactional outbox, inbox/deduplication và idempotency key thường được dùng để truyền sự kiện đáng tin cậy giữa các bước.

## 19. Foreign key và ràng buộc toàn cục

Foreign key cục bộ có thể hoạt động khi bảng cha và bảng con cùng shard. Nếu hai bảng phân phối khác nhau, database thường không thể kiểm tra ràng buộc bằng một FK đơn giản xuyên node.

Ứng dụng khi đó phải quản lý tham chiếu, kiểm tra tồn tại hoặc dùng một dịch vụ/metadata trung tâm. Điều này tạo race condition nếu bản ghi cha bị xóa đồng thời với thao tác tạo bản ghi con.

Unique constraint toàn cục cũng gặp vấn đề tương tự. `UNIQUE(email)` trên từng shard chỉ bảo đảm email duy nhất trong shard đó. Nếu yêu cầu duy nhất trên toàn hệ thống, cần global index, directory hoặc chiến lược định tuyến tất cả bản ghi cùng email đến một shard.

Đừng bỏ ràng buộc dữ liệu chỉ để sharding dễ hơn. Hãy liệt kê rõ constraint nào được database bảo đảm cục bộ, constraint nào cần cơ chế toàn cục và hành vi khi dịch vụ kiểm tra không sẵn sàng.

## 20. Hot shard và dữ liệu lệch

Shard skew là tình trạng dung lượng hoặc tải phân bố không đều giữa các shard. Một cụm có 12 shard nhưng một shard dùng 90% CPU trong khi các shard khác rảnh sẽ bị giới hạn bởi shard nóng đó.

Nguyên nhân thường gặp:

- Một tenant lớn hơn nhiều tenant khác.
- Một account hoặc product nhận quá nhiều request.
- Range key tăng tuần tự dồn ghi vào shard cuối.
- Hash key phân phối hàng đều nhưng workload truy cập lệch.
- Một shard nhận nhiều báo cáo hoặc tác vụ bảo trì hơn.
- Một số shard có index, statistics hoặc storage khác trạng thái.

Cần đo cả data skew và workload skew:

- Rows, bytes và index size mỗi shard.
- CPU, memory, IOPS, throughput và latency mỗi shard.
- Request/s, transaction/s và query mix mỗi shard.
- Lock wait, queue depth, connection usage và replication lag.
- Top key/tenant theo traffic, có kiểm soát bảo mật.

Phân phối đều số hàng không bảo đảm phân phối đều CPU hoặc I/O. Một bảng có hàng tương đương giữa các shard nhưng hot key vẫn có thể tạo tải lệch.

## 21. Xử lý tenant hoặc key nóng

Với hệ thống multi-tenant, shard theo tenant tạo locality và cô lập tốt cho tenant thông thường. Tuy nhiên, tenant rất lớn có thể vượt capacity của một shard.

Các lựa chọn:

- Đặt tenant lớn trên shard riêng bằng directory mapping.
- Chia tenant lớn thành sub-shard theo account/order bucket.
- Dùng composite key `(tenant_id, bucket_id)` cho một số bảng lớn.
- Tách read-heavy workload sang replica hoặc read model phù hợp.
- Cache dữ liệu nóng nếu semantics cho phép.
- Giới hạn hoặc điều tiết request của hot key để bảo vệ toàn cụm.

Chia một tenant thành nhiều shard làm truy vấn toàn tenant trở thành fan-out. Vì vậy, chỉ áp dụng cho tenant có quy mô đủ lớn và workload có thể chấp nhận việc phối hợp nhiều shard.

## 22. Rebalancing và resharding

Rebalancing là điều chỉnh phân bố dữ liệu/tải giữa các shard hiện có hoặc khi thêm/bớt node. Resharding có thể thay đổi shard key, số shard, bucket map hoặc cách ánh xạ dữ liệu.

Quá trình thường gồm:

1. Xác định phạm vi dữ liệu cần chuyển.
2. Tạo destination shard và cấu trúc schema/index tương ứng.
3. Copy dữ liệu nền theo batch.
4. Đồng bộ thay đổi phát sinh trong lúc copy bằng CDC, log stream hoặc dual-write có kiểm soát.
5. Kiểm tra số hàng, checksum, constraint và replication position.
6. Chuyển routing map sang đích mới theo quy trình an toàn.
7. Xử lý request đang chạy và mapping cache cũ.
8. Theo dõi lỗi, latency và tải sau cutover.
9. Giữ phương án rollback hoặc forward-fix theo giới hạn consistency.
10. Xóa dữ liệu nguồn khi đã xác nhận không còn request hoặc dependency.

Dual-write có thể tạo dữ liệu lệch nếu một phía thành công và phía kia thất bại. Nếu dùng, cần idempotency, reconciliation và nguồn dữ liệu chuẩn rõ ràng. CDC hoặc log-based replication có thể giảm rủi ro nhưng cần xử lý ordering, duplicate và lag.

Không chuyển routing trước khi destination đã có dữ liệu nhất quán. Không xóa nguồn ngay sau cutover nếu chưa có thời gian xác nhận và kế hoạch phục hồi.

## 23. Versioning shard map và routing cache

Shard map có thể nằm trong directory service, metadata database hoặc cấu hình được cache trong ứng dụng. Khi mapping thay đổi, nhiều instance ứng dụng có thể giữ phiên bản cũ.

Thiết kế nên có:

- Mapping version hoặc epoch.
- Cache TTL và cơ chế invalidation/push update.
- Quy tắc xử lý request đến shard cũ sau cutover.
- Forwarding hoặc redirect tạm thời nếu nền tảng hỗ trợ.
- Khả năng từ chối ghi vào shard cũ khi migration đã hoàn tất.
- Audit log cho thay đổi mapping.

Trong giai đoạn rebalance, cần xác định shard nào là owner ghi chính. Nếu hai node cùng nhận ghi cho một key mà không có giao thức đồng bộ, dữ liệu có thể diverge.

## 24. Replication trong từng shard và consistency

Mỗi shard có thể có primary và replica riêng. Replication tăng khả năng chịu lỗi và có thể mở rộng đọc, nhưng replica lag ảnh hưởng read-after-write và báo cáo.

Cần xác định:

- Read có thể chuyển sang replica hay phải đọc primary?
- Có yêu cầu read-your-writes không?
- Replica lag tối đa chấp nhận được?
- Khi failover, shard routing cập nhật endpoint thế nào?
- Transaction đang chạy bị ảnh hưởng ra sao?
- Một shard lỗi có làm request fan-out thất bại toàn bộ không?

Read routing sang replica không tự giải quyết query fan-out. Một truy vấn nhiều shard có thể đọc replica ở mỗi shard, nhưng cần xác định consistency của kết quả hợp nhất và thời điểm snapshot.

## 25. Giới hạn của truy vấn nhiều phân mảnh

Những giới hạn quan trọng cần đưa vào thiết kế API:

- **Không có shard key:** router có thể phải scatter-gather toàn cụm.
- **JOIN xuyên shard:** cần broadcast, shuffle hoặc xử lý tại ứng dụng.
- **Aggregate toàn cục:** phải tổng hợp partial result; một số phép toán đòi hỏi dữ liệu lớn hoặc thuật toán xấp xỉ.
- **ORDER BY/LIMIT:** cần merge kết quả có thứ tự và bảo đảm tie-breaker.
- **Pagination:** offset sâu và cursor toàn cục phức tạp hơn single-shard.
- **Uniqueness/FK:** constraint cục bộ không tự bảo đảm toàn hệ thống.
- **Transaction nhiều shard:** có thêm coordinator, network và failure modes.
- **Fan-out:** tăng request con, tail latency, memory và áp lực connection.
- **Partial failure:** một shard timeout có thể khiến kết quả không đầy đủ.
- **DDL/schema migration:** cần triển khai đồng bộ hoặc tương thích giữa nhiều shard.

Trước khi cho phép query fan-out trong API tương tác, hãy xác định shard count tối đa, timeout, concurrency, kết quả partial có được chấp nhận không và giới hạn dữ liệu trả về.

## 26. Thiết kế truy vấn để giảm fan-out

Các nguyên tắc:

1. Đưa shard key vào predicate khi nghiệp vụ có thông tin đó.
2. Định tuyến từ tenant/account context đã xác thực thay vì tìm kiếm toàn cụm.
3. Đẩy filter, projection, aggregation và limit xuống shard trước khi truyền dữ liệu về coordinator.
4. Chỉ truy cập các shard cần thiết, không broadcast mặc định.
5. Dùng colocation cho bảng thường JOIN hoặc cập nhật cùng nhau.
6. Tạo global lookup/index có chủ đích cho truy vấn không có shard key.
7. Tách báo cáo toàn cục khỏi đường request trực tuyến nếu cần quét lượng dữ liệu lớn.
8. Cache hoặc materialize kết quả tổng hợp khi freshness cho phép.
9. Giới hạn concurrency fan-out và đặt deadline.
10. Theo dõi tỷ lệ query single-shard so với multi-shard.

Ví dụ API có tenant context:

```http
GET /tenants/42/orders/9001
```

Router có thể ánh xạ tenant 42 đến shard tương ứng rồi truy vấn order. API báo cáo toàn hệ thống:

```http
GET /admin/orders?status=PENDING
```

có thể phải fan-out. Đây là endpoint quản trị riêng, nên có thể dùng timeout dài hơn, giới hạn tần suất, async export hoặc read warehouse thay vì cho phép request tương tác tạo tải không giới hạn.

## 27. Observability cho cụm sharded

Dashboard chỉ hiển thị trung bình toàn cụm có thể che shard nóng. Cần xem cả tổng và từng shard.

| Nhóm | Metric |
| --- | --- |
| Routing | Single-shard ratio, fan-out count, routing lookup latency, stale map errors |
| Load | Requests/s, transactions/s, query mix theo shard |
| Latency | p50/p95/p99 theo shard và end-to-end, slowest shard contribution |
| Data distribution | Rows, bytes, index size, bucket/tenant size |
| Resources | CPU, memory, IOPS, throughput, storage latency, network |
| Contention | Lock wait, deadlock, connection queue, worker saturation |
| Replication | Lag, apply throughput, failover và replica health |
| Reliability | Timeout, partial failure, retry, coordinator error, rebalance progress |

Đặt trace ID xuyên suốt request và các query con. Ghi shard ID, query fingerprint và thời gian từng shard để biết shard nào quyết định tail latency.

Tránh ghi raw tenant ID hoặc dữ liệu cá nhân vào metric label nếu cardinality hoặc chính sách bảo mật không cho phép. Có thể dùng nhóm tenant, shard ID và top-key sampling có kiểm soát.

## 28. Benchmark shard key và multi-shard query

Benchmark cần kiểm tra cả hiệu quả phân phối và giới hạn truy vấn.

### Chuẩn bị workload

- Cùng tổng số hàng, kích thước dữ liệu và index cho các phương án.
- Phân bố tenant/key đều và lệch để mô phỏng hot tenant.
- Tỷ lệ single-shard và multi-shard gần thực tế.
- Query equality, range, aggregate, JOIN, sort và pagination.
- Cùng consistency, replication và failover assumptions.
- Mức concurrency, request rate và network latency đại diện.

### Metric cần so sánh

- Throughput tổng và throughput từng shard.
- p50/p95/p99 end-to-end và thời gian shard chậm nhất.
- Fan-out count và số query con mỗi request.
- Bytes truyền giữa client, coordinator và shard.
- CPU, memory, I/O và connection utilization mỗi shard.
- Skew về số hàng, dung lượng và request rate.
- Error/timeout/partial-result rate.
- Rebalance duration, data movement và write amplification.

### Thử nghiệm có kiểm soát

1. Chạy single-shard workload trước để xác định baseline.
2. Chạy workload có fan-out đến 2, 4, 8 rồi nhiều shard hơn.
3. Tăng concurrency từng bậc và quan sát tail latency.
4. Tạo một hot tenant/key để đo skew.
5. Thử shard key khác nhau trên cùng workload.
6. Thử query không có shard key để định lượng chi phí scatter-gather.
7. Đo aggregate, JOIN và pagination riêng.
8. Thử một kịch bản shard chậm hoặc unavailable để kiểm tra partial failure.
9. Chạy rebalance thử và đo tác động lên foreground.
10. Xác nhận kết quả dữ liệu đúng, không chỉ throughput cao.

## 29. Ví dụ lựa chọn shard key cho hệ thống multi-tenant

Giả sử hệ thống SaaS có 20.000 tenant. 95% tenant nhỏ, 4% tenant vừa và 1% tenant rất lớn. Phần lớn API có `tenant_id`, nhưng báo cáo quản trị cần tổng hợp toàn hệ thống.

### Phương án A: hash tenant_id

- Các tenant được phân phối tương đối đều qua shard.
- Request trong một tenant đi đến một shard.
- Bảng customer/order/item có thể colocate theo tenant.
- Tenant lớn có thể tạo hot shard nếu một shard nhận một hoặc nhiều tenant lớn.
- Báo cáo toàn hệ thống phải fan-out.

### Phương án B: range tenant_id

- Có thể đặt nhóm tenant liền kề trên một shard.
- Truy vấn theo khoảng tenant có thể định tuyến đến một số shard.
- Nếu tenant ID tăng theo thời gian, tenant mới có thể dồn về range cuối.
- Cần split range khi kích thước hoặc tải không đều.

### Phương án C: directory mapping

- Tenant nhỏ được phân phối theo bucket.
- Tenant lớn được gán shard riêng hoặc nhiều bucket.
- Router tra directory/cache để xác định shard.
- Cần xử lý mapping version và rebalance.

Với workload trên, hash tenant hoặc directory thường phù hợp hơn range thuần nếu API chủ yếu truy cập một tenant. Directory linh hoạt hơn khi tenant lệch kích thước mạnh, nhưng thêm thành phần định tuyến. Lựa chọn cuối cần dựa trên phân bố traffic, không chỉ số lượng tenant.

Đối với tenant rất lớn, có thể dùng mô hình hai tầng: `tenant_id` chọn nhóm dữ liệu, `sub_key` như account/order bucket phân chia phần nóng. Khi đó truy vấn toàn tenant có thể fan-out trong phạm vi tenant đó; API cần chấp nhận hoặc tránh chi phí này bằng aggregate/read model.

## 30. Các mẫu kiến trúc hỗ trợ truy vấn toàn cục

Không phải mọi truy vấn toàn hệ thống đều nên fan-out trực tiếp trên OLTP shards. Có thể dùng:

- **Read replica per shard:** giảm tải đọc nhưng vẫn phải hợp nhất kết quả và xử lý lag.
- **Global index/directory:** hỗ trợ lookup theo thuộc tính không phải shard key.
- **Materialized aggregate:** cập nhật summary theo event hoặc batch để báo cáo không quét mọi shard.
- **Search service:** lập chỉ mục các trường tìm kiếm và trả về document ID/shard reference.
- **Data warehouse/lake:** phục vụ phân tích toàn cục, join lớn và lịch sử dài hạn.
- **Event stream:** phát sự kiện từ từng shard để xây read model tổng hợp.

Mỗi read model có freshness, consistency và chi phí cập nhật riêng. Cần xác định độ trễ dữ liệu chấp nhận được và cách xử lý sự kiện trùng, đến muộn hoặc sai thứ tự.

## 31. Quy trình chọn shard key

1. **Thu thập query pattern.** Phân loại truy vấn theo tần suất, latency mục tiêu, dữ liệu đọc và khóa có sẵn.
2. **Xác định ranh giới nghiệp vụ.** Tìm nhóm dữ liệu thường được đọc/ghi cùng nhau như tenant, account hoặc customer.
3. **Đo phân bố key.** Tính số hàng, dung lượng, request rate và write rate theo giá trị khóa.
4. **Đánh giá locality.** Tính tỷ lệ query có thể định tuyến đến một shard.
5. **So sánh range/hash/directory.** Đánh giá skew, hotspot, range scan, mapping và khả năng mở rộng.
6. **Kiểm tra ràng buộc.** Xem PK, unique, FK, transaction và global lookup.
7. **Mô phỏng truy vấn nhiều shard.** Đo fan-out, merge, JOIN, aggregate và pagination.
8. **Thiết kế rebalance.** Xác định bucket/range có thể di chuyển, version shard map và cutover.
9. **Benchmark theo tải thực.** Dùng dữ liệu đều và lệch, concurrency, network và failure scenarios.
10. **Chốt hợp đồng routing.** Bảo đảm API, repository và batch jobs truyền shard context nhất quán.

## 32. Những sai lầm thường gặp

- **Chọn key chỉ để chia đều số hàng.** Query locality và workload skew có thể vẫn rất xấu.
- **Chọn khóa tăng tuần tự cho range shard mà không kiểm soát hotspot.** Ghi mới có thể dồn vào shard cuối.
- **Hash shard key nhưng cần range query thường xuyên.** Truy vấn có thể fan-out đến toàn cụm.
- **Sharding theo tenant mà bỏ qua tenant lớn.** Một tenant có thể làm shard nóng và giới hạn capacity.
- **Không đưa shard key vào API/query.** Router buộc phải scatter-gather.
- **Cho phép fan-out không giới hạn.** Một request tạo quá nhiều query con và làm cụm bão hòa.
- **JOIN hai bảng không colocate trong request OLTP.** Network shuffle hoặc application join có thể rất đắt.
- **Dùng AVG của từng shard rồi lấy trung bình đơn giản.** Kết quả sai khi số hàng mỗi shard khác nhau.
- **Dùng OFFSET sâu cho pagination toàn cục.** Mỗi shard và coordinator phải xử lý nhiều hàng bỏ qua.
- **Tin rằng unique index cục bộ là unique toàn cụm.** Trùng key vẫn có thể tồn tại ở shard khác.
- **Không tính transaction nhiều shard.** 2PC hoặc saga có failure mode và độ trễ khác transaction local.
- **Rebalance mà không version shard map.** Request có thể ghi vào node cũ và node mới cùng lúc.
- **Chỉ xem metric trung bình toàn cụm.** Một shard nóng có thể bị che khuất.
- **Dùng OLTP fan-out cho báo cáo lớn.** Có thể gây tải cạnh tranh với request nghiệp vụ.

## 33. Danh sách kiểm tra trước khi triển khai sharding

- [ ] Query pattern và tỷ lệ single-shard/multi-shard đã được đo.
- [ ] Shard key có mặt trong phần lớn truy vấn quan trọng.
- [ ] Phân bố rows, bytes, CPU và request rate theo key đã được kiểm tra.
- [ ] Đã đánh giá hot tenant, hot key và range hotspot.
- [ ] Đã chọn range, hash, directory hoặc virtual bucket có lý do rõ ràng.
- [ ] Các bảng thường JOIN/transaction cùng nhau được colocate nếu có thể.
- [ ] Có chiến lược uniqueness và foreign key xuyên shard.
- [ ] Có giới hạn fan-out, timeout, concurrency và partial-result policy.
- [ ] ORDER BY, LIMIT, aggregate và pagination toàn cục có cách merge đúng.
- [ ] Cross-shard JOIN không nằm trên đường request tương tác nếu không có ngân sách.
- [ ] Transaction nhiều shard có semantics, recovery và idempotency rõ ràng.
- [ ] Shard map có version, cache invalidation và cutover procedure.
- [ ] Có kế hoạch rebalance, resharding và rollback/reconciliation.
- [ ] Dashboard hiển thị metric từng shard và end-to-end.
- [ ] Benchmark có tải đều, tải lệch, shard chậm và lỗi một phần.

## Kết luận

Sharding phân phối dữ liệu qua nhiều node để mở rộng tổng dung lượng và năng lực xử lý, nhưng hiệu quả phụ thuộc chủ yếu vào shard key và query locality. Chọn khóa dựa trên mẫu truy vấn, phân bố dữ liệu, tải ghi, ranh giới nghiệp vụ và khả năng tăng trưởng; range hỗ trợ truy vấn khoảng nhưng có thể tạo hotspot, hash phân phối equality tốt nhưng thường làm range query fan-out, còn directory linh hoạt nhưng cần quản lý mapping. Truy vấn nhiều shard phải trả chi phí fan-out, merge, JOIN, aggregate, pagination, consistency và partial failure. Hãy colocate dữ liệu thường dùng cùng nhau, giới hạn fan-out, thiết kế uniqueness/transaction rõ ràng và đo từng shard cùng end-to-end latency. Rebalance cần shard map có version và quy trình chuyển dữ liệu an toàn. Chỉ chọn sharding khi workload và giới hạn tài nguyên đã được đo, rồi xác nhận lợi ích bằng benchmark thực tế.
