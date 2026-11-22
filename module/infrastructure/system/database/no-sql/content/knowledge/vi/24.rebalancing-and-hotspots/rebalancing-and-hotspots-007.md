# Rebalance, split, merge và di chuyển vùng dữ liệu theo từng hệ

Trong một hệ NoSQL phân tán, dữ liệu không đứng yên mãi ở những máy ban đầu. Sau vài tháng vận hành, node mới được bổ sung, một khách hàng lớn tạo lưu lượng bất thường, dữ liệu tăng không đều giữa các vùng khóa, một rack gặp sự cố hoặc đội vận hành muốn giảm số node để tiết kiệm chi phí. Khi ấy hệ phải **điều chỉnh nơi lưu trữ và nơi xử lý các vùng dữ liệu** mà vẫn bảo vệ khả năng đọc/ghi.

Bốn khái niệm thường được nhắc cùng nhau là **rebalance**, **split**, **merge** và **move/relocation**:

- **Rebalance (tái cân bằng):** đưa phân bố dữ liệu, lưu lượng hoặc số vùng quản lý về gần mục tiêu mong muốn. Đây là **mục tiêu/quy trình**, không nhất thiết là một thao tác lưu trữ đơn lẻ.
- **Split (tách):** chia một đơn vị phân vùng logic hoặc một khoảng khóa/token thành các đơn vị nhỏ hơn, để chúng có thể được quản lý hay chuyển vị trí độc lập.
- **Merge (gộp):** kết hợp những đơn vị nhỏ phù hợp thành một đơn vị lớn hơn, giảm overhead khi có quá nhiều vùng nhỏ hoặc tải giảm.
- **Move/relocation (di chuyển):** chuyển quyền sở hữu hoặc dữ liệu thực của một đơn vị từ node/shard này sang node/shard khác; trong thời gian chuyển cần bảo vệ các read/write đang diễn ra.

Những khái niệm này được triển khai **khác nhau theo từng DBMS**. MongoDB quản lý các khoảng shard-key dạng *chunks* và di chuyển chúng giữa shards; Apache HBase quản lý *regions* có thể split/merge/move; Redis Cluster phân phối **hash slots**; Cassandra tái phân bố **token ranges và replicas** qua topology/streaming; DynamoDB tự quản phần lớn việc chia và bố trí các partition vật lý; Elasticsearch có **shards** và quy trình relocation, còn split/shrink index chịu ràng buộc riêng.

Bài học thuộc chương **Cân bằng và điểm nóng** của module **Database No SQL**. Mục tiêu là hiểu **khi nào thao tác nào có ích, dữ liệu nào thực sự dịch chuyển, rủi ro khi vừa chuyển vừa ghi, và giới hạn của từng sản phẩm**.

> **Phạm vi an toàn:** ví dụ lệnh quản trị trong bài là để hiểu khái niệm và thực hành trên cụm lab. API, điều kiện cho phép, cú pháp, cơ chế tự động và thuật toán cân bằng có thể thay đổi giữa các phiên bản DBMS. Không chạy split, merge, reshard, move, decommission hoặc thao tác đổi topology trên production chỉ dựa vào đoạn minh họa.

## 1. Bốn thao tác không đồng nghĩa nhau

Hãy tưởng tượng ba node đang phục vụ sáu vùng dữ liệu:

~~~text
Node A: [R1] [R2] [R3] [R4]
Node B: [R5]
Node C: [R6]
~~~

Nếu R1–R6 có tải tương đương, Node A đang giữ nhiều vùng hơn. Một thao tác **rebalance** có thể:

~~~text
Node A: [R1] [R2]
Node B: [R3] [R5]
Node C: [R4] [R6]
~~~

Ở đây chỉ cần **move R3 và R4**, chưa cần split hay merge.

Nhưng nếu R1 quá lớn/nóng so với mọi vùng khác:

~~~text
Node A: [R1 rất lớn] [R2]
Node B: [R3]
Node C: [R4]
~~~

ta có thể muốn:

~~~text
SPLIT R1 → R1a + R1b

Node A: [R1a] [R2]
Node B: [R1b] [R3]
Node C: [R4]
~~~

Lúc này, **split tạo ra đơn vị có thể điều phối nhỏ hơn**, sau đó **move** R1b mới làm dữ liệu phân bố qua node khác.

Nếu trước đó có quá nhiều vùng bé:

~~~text
Node C: [R10 tiny] [R11 tiny] [R12 tiny] [R13 tiny]
~~~

hệ có thể xem xét **merge những vùng kề nhau và thỏa điều kiện** để giảm metadata, số tác vụ nền và overhead quản lý.

### Bảng phân biệt

| Thao tác | Thay đổi số vùng logic? | Thay đổi vị trí vật lý? | Mục tiêu thường gặp |
| --- | --- | --- | --- |
| Rebalance | Có thể có hoặc không | Thường có | Dàn đều dữ liệu/tải |
| Split | Tăng số vùng | Không bắt buộc ngay | Chia đơn vị quá lớn/nóng |
| Merge | Giảm số vùng | Có thể hoặc không | Giảm overhead vùng nhỏ |
| Move/relocation | Thường không | Có | Dời dữ liệu/quyền phục vụ |

**Điều đặc biệt quan trọng:** một split **không tự bảo đảm dữ liệu đã được đưa sang máy khác**. Một merge **không tự làm tổng dữ liệu nhỏ hơn**, và một rebalance hoàn thành về bytes **không tự chứng minh QPS đã cân bằng**.

## 2. Phân biệt logical partition, physical region và replica

Các DBMS có nhiều lớp ánh xạ:

~~~text
Business key / access pattern
             |
             v
Logical partition key
             |
             v
Hash token hoặc ordered shard key
             |
             v
Token range / chunk / slot / region
             |
             v
Physical node hoặc shard
             |
             v
Replica placement, nếu có
~~~

Một **partition key** có thể xác định **một partition logic không nên tách tùy tiện**, trong khi node vật lý chứa nhiều partition hoặc token ranges.

Ví dụ Cassandra:

~~~text
Partition key = (tenant_id="T1", customer_id="C42")
      |
      v
Hash → một token t
      |
      v
Các replica chịu trách nhiệm token t
~~~

Nếu cluster thêm node và tái bố trí token ranges, **cả partition của khách C42** vẫn có một token. Node mới có thể nhận quyền lưu partition đó, nhưng hệ **không tự bẻ đôi partition key C42 thành hai partition**.

Ngược lại, trong HBase, vùng khóa một bảng có thể split thành **hai regions** theo row-key boundary; những hàng có row key nhỏ hơn/lớn hơn boundary trở thành hai nhóm có thể phục vụ ở những RegionServer khác nhau.

**Luôn xác định “split cái gì?” trước khi tính lợi ích.**

## 3. Hai dạng điểm nóng: hot node và hot key

Không phải mọi tình huống chậm cần cùng một giải pháp.

### 3.1. Hot node do có quá nhiều vùng

~~~text
Node A: 70% toàn bộ byte dữ liệu và nhiều partition.
Node B: 15%.
Node C: 15%.
~~~

Nếu node A có nhiều vùng **độc lập**, rebalance/move một số vùng có thể giảm disk I/O và network pressure.

### 3.2. Hot range do một vùng quá lớn

~~~text
Node A:
  Range R1 = 2 TiB, 40.000 request/s

Node B:
  R2 = 100 GiB
~~~

Nếu hệ hỗ trợ split R1 theo một ranh giới hợp lý, ta có thể tạo R1a/R1b rồi move một phần. Nhưng hiệu quả chỉ có nếu workload thực sự phân bố qua hai phần sau split.

### 3.3. Hot key — một định danh duy nhất quá nóng

~~~text
Key: inventory:FLASH-SALE-2026
QPS: 100.000 updates/s
~~~

Nếu split theo khoảng mà **toàn bộ 100.000 updates vẫn nhắm đúng một key**, key vẫn thuộc **một** khoảng sau split. Mỗi bản ghi/key không tự được chia thành nhiều khóa.

Đây là tình huống cần:

- Thiết kế sharded counter/bucket nếu phép toán cho phép.
- Cấp trước quota hoặc phân tán quyền cập nhật.
- Cache/read replicas cho read-heavy workload phù hợp.
- Hàng đợi tuần tự hóa writes theo aggregate.
- Thay mô hình dữ liệu hoặc quy tắc nghiệp vụ.

**Tách range không phải là phép nhân throughput cho một hot key bất khả phân.**

## 4. Ba mục tiêu cân bằng phải đo riêng

Một cụm có thể cân bằng về bytes nhưng không cân bằng về QPS, hoặc cân bằng QPS nhưng một node vẫn bị nghẽn CPU.

| Thước đo | Cần theo dõi | Ví dụ sai lệch |
| --- | --- | --- |
| **Storage balance** | Bytes/node, disk utilization, compaction overhead | Một node 92% disk, node khác 35% |
| **Read balance** | Reads/s, p95/p99, cache hit, scan size | Một vùng sản phẩm nổi bật nhận hầu hết GET |
| **Write balance** | Writes/s, WAL/commit-log throughput, SSTable pressure | Một time bucket hiện tại nhận phần lớn events |
| **CPU/memory balance** | CPU, GC/heap, cache pressure | Query aggregation nặng tập trung |
| **Network balance** | In/out, cross-AZ/DC transfer | Streaming chiếm hết bandwidth |
| **Replica/failure-domain balance** | Replica count theo rack/AZ, quorum resilience | Replica dồn vào cùng rack |

Vì vậy câu “cluster đã rebalance” phải chỉ rõ **theo metric nào, trên thời gian nào và với workload nào**.

## 5. Định nghĩa range và điều kiện split/merge

Với phân vùng theo khoảng giá trị có thứ tự, một vùng có thể được ký hiệu:

\[
R=[a,b)
\]

nghĩa là chứa những khóa `k` thỏa:

\[
a\le k<b
\]

Giả sử:

~~~text
R = [0,100)
~~~

Split tại `s=40`:

~~~text
Trước:
  R = [0,100)

Sau:
  R_left  = [0,40)
  R_right = [40,100)
~~~

Phải bảo đảm:

\[
[0,40)\cup[40,100)=[0,100)
\]

và hai đoạn không chồng nhau.

### Merge hai vùng kề nhau

~~~text
R1 = [0,40)
R2 = [40,100)

MERGE → R = [0,100)
~~~

Không nên merge:

~~~text
R1 = [0,40)
R2 = [60,100)
~~~

thành `[0,100)` mà không xử lý khoảng trống `[40,60)`, vì sẽ vô tình gán quyền sở hữu cho dữ liệu không thuộc hai vùng cũ.

**Quy ước biên có thể khác theo DBMS.** Khi viết thuật toán hoặc kiểm tra metadata, phải sử dụng đúng ngữ nghĩa min/max inclusive/exclusive của hệ.

## 6. Range-based và hash-based splitting khác nhau

Với **range sharding** theo `created_at`:

~~~text
2026-01-01 ────────── 2026-07-01 ─────────── 2027-01-01
       Region A                 Region B
~~~

Ta có thể split ở mốc thời gian để phân phối những khoảng lịch sử. Nhưng **ghi mới nhất vẫn đổ về phần cuối dải thời gian**, tạo một hotspot ở right edge nếu chiến lược ghi không thay đổi.

Với **hash/token partitioning**:

~~~text
partition key → hash → token
       |
       v
Token ranges [a,b)
~~~

Hash thường giúp rải nhiều partition keys lên không gian token, làm giảm lệch khi khóa đầu vào tăng dần. Tuy nhiên, một partition key vẫn hash về một token.

### Cân nhắc khi split

| Tình huống | Split range giúp gì? | Hạn chế |
| --- | --- | --- |
| Một range có nhiều keys độc lập | Có thể tách dữ liệu/tải thành hai vùng | Chọn split point hợp lý |
| Khóa tăng tuần tự liên tục | Chia dữ liệu lịch sử | Hot edge vẫn có thể nóng |
| Một key duy nhất nhận mọi write | Gần như không | Cần đổi key/bucketing |
| Một tenant cực lớn với một partition key | Không tự tách partition logic | Cần thiết kế lại partition key |
| Nhiều range quá nhỏ | Có thể ngược lại: merge | Phải cân nhắc overhead |

## 7. Split point nên được chọn theo gì?

Một cách đơn giản là chọn midpoint theo giá trị:

\[
s=(a+b)/2
\]

Nhưng chọn midpoint **theo giá trị** không nhất thiết chia đôi **bytes hoặc QPS**.

Ví dụ:

~~~text
Range [0,100)
99% dữ liệu ở keys 80..99
1% ở keys 0..79
~~~

Split tại 50 tạo hai range:

~~~text
[0,50)  → dữ liệu rất ít
[50,100) → gần như toàn bộ dữ liệu
~~~

Cân bằng không cải thiện nhiều.

### Các cách chọn split point

- Theo **median của phân phối key** nếu mục tiêu cân bằng số hàng/bytes.
- Theo **byte size** ước tính trên mỗi phía.
- Theo **histogram/quantile** của key hoặc token.
- Theo **QPS/hot range** nếu mục tiêu chia tải.
- Theo **ranh giới nghiệp vụ/thời gian** nếu giúp retention/query.

Một số DBMS có cơ chế tự chọn split point dựa trên metadata/size/heat. Không nên giả định mọi hệ đều cho operator chỉ định trực tiếp mọi mốc.

## 8. Move không phải chỉ đổi tên owner trong metadata

Giả sử vùng `R=[40,80)` chứa 500 GiB dữ liệu và đang ở Node A:

~~~text
Before:
  Node A: owner(R), data(R)
  Node B: no data(R)
~~~

Nếu chỉ đổi bản đồ:

~~~text
Owner(R) = B
~~~

nhưng B chưa nhận 500 GiB dữ liệu, request chuyển tới B có thể **đọc thiếu hoặc trả NOT_FOUND sai**.

Để di chuyển an toàn cần quản lý hai yếu tố:

1. **Physical copy:** dữ liệu cũ thực sự tới B.
2. **Authoritative ownership:** tại từng thời điểm, hệ biết ai được phép nhận write và phục vụ read dưới consistency contract.

Trong quá trình copy, ứng dụng vẫn có thể ghi. Vấn đề khó không chỉ là snapshot cũ, mà là **những thay đổi xảy ra sau snapshot**.

## 9. Vòng đời điển hình của một lần move online

Một mô hình khái niệm:

~~~text
1. PREPARE
   Kiểm tra node đích, capacity, topology, quyền truy cập
           |
           v
2. COPY SNAPSHOT
   Sao phần dữ liệu tại một mốc nhất quán phù hợp
           |
           v
3. CATCH UP
   Áp thay đổi phát sinh sau mốc snapshot
           |
           v
4. FENCE / COMMIT OWNERSHIP
   Chuyển quyền nhận write theo giao thức an toàn
           |
           v
5. REDIRECT / ROUTE UPDATE
   Client/coordinator chuyển dần tới owner mới
           |
           v
6. VERIFY
   Kiểm metadata, phiên bản, dữ liệu, metrics
           |
           v
7. CLEANUP
   Xóa bản tạm cũ khi an toàn
~~~

Đây là **một mô hình chung**, không khẳng định mọi hệ chạy đúng thứ tự hay dùng cùng thuật ngữ. Ví dụ Redis Cluster có trạng thái migrating/importing và chuyển key/slot; Cassandra dùng streaming và topology transitions; MongoDB có giao thức chunk migration; HBase dùng RegionServer/Master và cơ chế lưu trữ riêng.

### Snapshot và delta/catch-up

Giả sử:

~~~text
T0: snapshot của R có version 100
T1: copy snapshot sang B
T2: client ghi version 101 vào A
T3: client ghi version 102 vào A
T4: copy snapshot hoàn tất
~~~

Nếu cắt route sang B ở T4 mà chưa truyền 101/102, B thiếu dữ liệu.

Đường chuyển an toàn cần **theo dõi và áp những thay đổi sau mốc snapshot**, hoặc có một cơ chế storage/replication khiến đích đọc được trạng thái nhất quán khi cutover.

## 10. Quyền sở hữu và fencing token

Một rủi ro lớn là **hai node cùng nghĩ mình có quyền ghi cuối cùng**.

~~~text
Node A: "Tôi vẫn sở hữu R"
Node B: "Tôi đã nhận R"
~~~

Nếu cả hai nhận write độc lập mà không có quy tắc phối hợp, có thể xảy ra split-brain, lost update hoặc inconsistent reads.

Một thiết kế có thể dùng **ownership generation/epoch**:

~~~text
R, generation=17, owner=A
          |
      safe handoff
          v
R, generation=18, owner=B
~~~

Operation từ generation 17 phải bị **fence/reject** ở nơi có thẩm quyền sau khi generation 18 được commit, theo giao thức.

### Version cần được kiểm soát ở đúng nơi

Không đủ nếu B chỉ lưu:

~~~text
isOwner = true
~~~

và A cũng còn biến `isOwner=true` trong RAM. Một node bị mạng cô lập có thể không biết topology đã đổi.

Vì vậy fencing cần được thực thi bởi **storage/consensus/coordinator hoặc cơ chế ownership có thẩm quyền**; không chỉ là biến boolean trong hai tiến trình.

### Không tự dual-write trong application nếu chưa có protocol

Thấy dữ liệu đang move, một developer có thể thử:

~~~text
write(data) → A
write(data) → B
~~~

Nhưng hai lệnh độc lập có thể thất bại một nửa, tới đảo thứ tự, bị retry không đồng nhất, hoặc phá ràng buộc uniqueness. Dual-write chỉ an toàn khi có giao thức đảm bảo commit/replay/idempotency tương ứng.

## 11. Cutover: lúc nào read/write được chuyển sang nơi mới?

Trong giai đoạn move, một số hệ cho phép đọc từ source tới khi target bắt kịp; một số hệ có redirect; một số hệ dùng shared storage nên chuyển quyền phục vụ region không đồng nghĩa copy mọi byte.

Một contract ở cấp khái niệm:

~~~yaml
range: "[40,80)"
oldOwner: "node-A"
newOwner: "node-B"
generationBefore: 17
generationAfter: 18
copyState: "completed"
deltaCatchup: "reached handoff watermark"
writeAuthority: "new owner after committed handoff"
clientRouting: "refresh metadata or follow redirect"
cleanup: "only after safety checks"
~~~

Đây **không phải** metadata của MongoDB/Cassandra/Redis/HBase. Nó minh họa điều một protocol di chuyển cần xác định.

Nếu router cập nhật **quá sớm**, có thể mất read. Nếu cập nhật **quá muộn**, request vẫn tới owner cũ và phải được xử lý/redirect an toàn. Nếu cleanup **quá sớm**, rollback hoặc recovery có thể mất dữ liệu cần thiết.

## 12. Split và merge cũng cần bảo vệ writes đồng thời

Giả sử:

~~~text
R = [0,100), owner=A
~~~

Split tại 50:

~~~text
R1 = [0,50)
R2 = [50,100)
~~~

Trong lúc split, client ghi key=50. Hệ phải quy định key=50 thuộc **R2** theo khoảng `[start,end)`, tránh tình huống hai vùng cùng nhận hoặc cả hai bỏ sót.

Đối với merge:

~~~text
R1=[0,50), R2=[50,100)
MERGE → R=[0,100)
~~~

Nếu một request tới R1 và một request tới R2 đang chạy, hệ phải đồng bộ metadata/ownership sao cho:

- Không mất mutation đang chờ.
- Không trả kết quả đọc từ trạng thái không hợp lệ.
- Không để hai version owner khác nhau ghi đè tùy ý.
- Có thể retry/redirect theo contract.

**Split/merge thường là hoạt động quản lý trạng thái**, không phải chỉ thay hai hàng metadata trong một bảng.

## 13. Rebalance khi nào nên chạy?

Một rebalance tự động hoặc thủ công có thể được kích hoạt bởi:

1. **Storage skew:** mức sử dụng disk khác biệt lớn.
2. **Compute skew:** QPS/CPU/IOPS tập trung ở ít node.
3. **Thêm node:** muốn chuyển bớt dữ liệu sang node mới.
4. **Loại node:** phải chuyển những vùng đang do node cũ sở hữu.
5. **Sự cố node/rack:** cần phục hồi replica redundancy.
6. **Thay đổi replication factor/topology:** tập replica mục tiêu thay đổi.
7. **Vùng lớn hoặc quá nhiều vùng nhỏ:** cần split/merge để điều chỉnh granularity.
8. **Đặt sai failure domain:** cần move replica để tránh tương quan lỗi.

**Không nhất thiết hễ thấy một node 80% CPU là phải move data.** CPU cao có thể do một query scan nặng, compaction, JVM GC hoặc một job nền tạm thời; nếu move sai vùng, overhead chỉ làm tình trạng tệ thêm.

## 14. Cân bằng theo bytes chưa chắc cân bằng theo tải

Giả sử:

~~~text
Node A: 1 TiB, 5.000 QPS
Node B: 1 TiB, 55.000 QPS
Node C: 1 TiB, 4.000 QPS
~~~

Theo disk, ba node rất đều. Nhưng B đang là điểm nóng read/write.

Nếu B giữ một vùng nóng có **nhiều key độc lập**, tách và di chuyển một phần phù hợp có thể hữu ích.

Nếu B giữ một **hot key duy nhất**, split range có thể không chia được lưu lượng thực. Khi ấy cần thay access pattern hoặc mô hình dữ liệu.

### Weighted score cho rebalancing

Một hệ có thể đánh giá chi phí vùng `r` bằng nhiều tín hiệu:

\[
\operatorname{cost}(r)
=w_1\operatorname{bytes}(r)
+w_2\operatorname{QPS}(r)
+w_3\operatorname{CPU}(r)
\]

Đây là **hàm minh họa**, không phải thuật toán chính thức của Cassandra/MongoDB/HBase. Việc chọn trọng số còn cần chuẩn hóa đơn vị; một QPS nặng không tương đương một QPS nhẹ.

Thực tế cần xét:

- Độ biến động trong ngày.
- Loại truy vấn đọc/ghi.
- Cache locality.
- Chi phí chuyển vùng.
- Quorum/failure domains.
- Chống *thrashing* — vừa chuyển đi lại chuyển về.

## 15. Hysteresis và tránh rebalance liên tục

Nếu hệ cứ thấy Node A 51% và B 49% liền move data để cân bằng đúng 50/50, một thay đổi workload nhỏ sau đó có thể lại đảo ngược quyết định:

~~~text
A cao một chút → move R từ A sang B
B cao một chút → move R từ B sang A
A cao một chút → ...
~~~

Đây là *rebalance thrashing*.

Một chính sách hợp lý có thể dùng:

- Ngưỡng khởi động cao và ngưỡng dừng thấp (**hysteresis**).
- Quan sát nhiều cửa sổ thời gian.
- Giới hạn số migration đồng thời.
- Cooldown cho vùng vừa move.
- Dự đoán thời gian tải cao/giờ bảo trì.
- Không move nếu lợi ích dự tính nhỏ hơn chi phí streaming.

**Tự động cân bằng là một vòng điều khiển có chi phí**, không phải lệnh “luôn bằng nhau tuyệt đối”.

## 16. Capacity planning cho move và split

Ví dụ một vùng 600 GiB cần chuyển từ A sang B. Tốc độ truyền trung bình hữu hiệu **80 MiB/s** theo điều kiện lab giả định.

Ước lượng thời gian chỉ cho copy nền:

\[
t_{\text{copy}}
\approx\frac{600\times1024\ \text{MiB}}{80\ \text{MiB/s}}
=7680\ \text{s}
\]

Tức khoảng **128 phút**, chưa tính:

- Kiểm tra snapshot.
- Delta/catch-up của write mới.
- Congestion, nén, encryption.
- Compaction ở source/target.
- Throttling để giữ latency online.
- Retry sau lỗi mạng.
- Final handoff/cleanup.

Nếu trong lúc copy có **write rate cao** và target áp delta chậm hơn tốc độ phát sinh, backlog có thể **không bao giờ về 0**, khiến quá trình cutover kéo dài.

### Dung lượng tạm

Trong nhiều cơ chế copy:

~~~text
Old owner giữ data.
New owner cũng nhận data.
~~~

Trong một khoảng thời gian, hai nơi có thể cùng giữ bản sao. Vì vậy target phải có headroom disk thực tế; chỉ tính mức **sau khi rebalance** có thể đánh giá thiếu.

## 17. Ước lượng chi phí split và merge

Split/merge không có chi phí giống nhau trong mọi storage engine.

### Một hệ dùng shared file/LSM metadata

Split có thể chủ yếu tạo metadata vùng mới và **tham chiếu tạm tới những file hiện có**, rồi dữ liệu vật lý được tách dần qua compaction.

### Một hệ cần sao dữ liệu vật lý

Split hoặc move có thể tạo nhiều I/O đọc/ghi, mạng và CPU đáng kể.

### Merge

Gộp hai vùng nhỏ có thể:

- Giảm số metadata records.
- Giảm overhead scheduling và quản lý vùng.
- Làm vùng lớn hơn, có thể phải di chuyển để đặt cùng một nơi.
- Tăng chi phí của những lần move tiếp theo vì đơn vị đã lớn.

**Không mặc định split = copy toàn bộ dữ liệu ngay và merge = thao tác chỉ sửa metadata.** Tìm đúng mô hình lưu trữ của hệ.

## 18. MongoDB: shard key, chunk và balancer

Trong MongoDB sharded cluster, dữ liệu của collection được phân phối trên **shards** dựa trên **shard key**. Metadata định nghĩa những khoảng shard-key và nơi chúng đang được đặt. Những khoảng này thường được gọi là **chunks**.

Sơ đồ:

~~~text
                        mongos
                          |
                    Shard-key value
                          |
                     Chunk metadata
                   /       |       \
                  v        v        v
               Shard A  Shard B  Shard C
~~~

### Shard key range

Ví dụ minh họa:

~~~text
Chunk C1: customerId values [A, H) → Shard 1
Chunk C2: customerId values [H, R) → Shard 2
Chunk C3: customerId values [R, +∞) → Shard 3
~~~

Với **hashed shard key**, các chunk nằm trong **không gian giá trị đã hash**, không nhất thiết thành những khoảng chữ cái dễ đọc theo raw customerId.

### Balancer

MongoDB có cơ chế balancer để đưa phân bố chunks/data về gần chính sách mong muốn, cùng các ràng buộc phân phối/zone và trạng thái cluster.

**Không nên gán một quy tắc duy nhất kiểu “mỗi khi chunk vượt đúng X MiB sẽ tự split” cho mọi phiên bản.** Cơ chế auto-splitting, điều kiện migration, quản lý chunk size và balancing đã thay đổi giữa các đời MongoDB. Khi vận hành thật, phải đối chiếu tài liệu version cụ thể.

## 19. MongoDB: split chunk và move chunk khác gì?

Một ví dụ khái niệm:

~~~text
Trước:
  Chunk [0,100) trên Shard A

SPLIT tại 40:
  Chunk [0,40)  trên Shard A
  Chunk [40,100) trên Shard A

MOVE chunk [40,100):
  Chunk [0,40)  trên Shard A
  Chunk [40,100) trên Shard B
~~~

Đầu tiên **split** thay ranh giới metadata, nhưng có thể cả hai chunk vẫn thuộc A. Sau đó **move** mới chuyển vùng sang B.

### Minh họa thao tác quản trị

Tùy version và điều kiện cluster, MongoDB shell từng cung cấp các helper như:

~~~javascript
// Cú pháp tham khảo: yêu cầu collection đã sharded,
// shard key và cluster phù hợp.
sh.splitAt(
  "shop.orders",
  { customerId: "C500" }
);

sh.moveChunk(
  "shop.orders",
  { customerId: "C501" },
  "shardB"
);
~~~

**Không chạy trên production theo ví dụ này.** Trong triển khai thực tế, manual split/migration có giới hạn, một số helper có thể thay đổi hoặc bị hạn chế theo MongoDB version, và balancer tự động có thể là lựa chọn vận hành chuẩn hơn.

Mục đích của mã là phân biệt **thay ranh giới chunk** với **thay shard chứa chunk**.

## 20. MongoDB: một chunk lớn hoặc jumbo chunk

Giả sử một chunk rất lớn chứa dữ liệu khó chia:

~~~text
Chunk C: 500 GiB
  - Nhiều document
  - Nhưng cùng một giá trị shard key lớn/khó chia
~~~

Nếu không có **ranh giới shard-key hợp lệ để tách**, việc split chunk có thể không giúp chia tải. Trong các trường hợp/phiên bản nhất định, MongoDB dùng thuật ngữ **jumbo chunk** hoặc có hạn chế migration cho những phạm vi quá lớn.

### Gốc vấn đề có thể là shard-key cardinality

Nếu tất cả document của tenant lớn có cùng shard key:

~~~text
shardKey = tenantId
tenantId = "VIP"
~~~

chúng không tự được phân phối qua nhiều shard chỉ bằng việc tăng số shard. Cần đánh giá:

- Shard key có cardinality đủ không?
- Có đơn vị nào quá lớn và không chia được không?
- Các query có cần co-location theo tenant không?
- Có thể thay/reshard key theo version hỗ trợ không?
- Ràng buộc uniqueness/transaction bị ảnh hưởng ra sao?

**Balancer không sửa được lựa chọn shard key sai một cách thần kỳ.**

## 21. MongoDB: chunk migration là thao tác online có giao thức

Khi một chunk được chuyển từ Shard A sang Shard B, người vận hành cần hiểu ở mức khái niệm:

~~~text
Source shard A
    |
    | dữ liệu chunk và các cập nhật cần thiết
    v
Destination shard B
    |
    v
Placement metadata được commit theo protocol
    |
    v
Router biết owner mới
~~~

MongoDB có cơ chế điều phối metadata, chuyển dữ liệu và xử lý routing/version trong cluster. **Không được thay thế bằng script copy documents rồi sửa cache của mongos**.

### Những nguyên nhân migration thất bại hoặc chậm

- Destination thiếu disk/capacity.
- Source/target bị tải nặng.
- Network chậm.
- Balancer window/zone constraint.
- Dữ liệu chunk khó chia.
- Metadata/DDL activity cạnh tranh.
- Khối lượng cập nhật trong lúc chuyển lớn.

Monitor **migrations, shard size, chunk distribution và query latency** trong quá trình rebalance, không chỉ số chunk.

## 22. MongoDB: merge chunks và resharding không đồng nghĩa

**Merge chunks** (khi API/điều kiện phiên bản hỗ trợ) là kết hợp những khoảng chunk **kề nhau** theo ràng buộc placement thành một đơn vị metadata lớn hơn.

**Resharding** là thay đổi **cách phân phối của toàn collection theo shard key mới**; nó có thể là hoạt động lớn hơn nhiều vì giá trị shard key của các document quyết định mapping mới.

~~~text
Merge chunks:
  [A,H) + [H,R) → [A,R)
  shard key không đổi.

Reshard collection:
  shard key cũ: tenantId
  shard key mới: (tenantId, orderBucket)
  nhiều document cần ánh xạ lại và di chuyển.
~~~

Hợp đồng truy vấn, index, uniqueness, data locality và thời gian migration đều cần phân tích khi reshard. **Không xem merge như cách đổi shard key.**

## 23. MongoDB: zone sharding làm cân bằng có ràng buộc

Một tổ chức có thể yêu cầu dữ liệu của tenant hoặc dải shard key chỉ nằm trên **tập shards trong zone nhất định** vì locality hoặc data residency.

~~~text
Zone VN:
  Shard A, Shard B

Zone EU:
  Shard C, Shard D
~~~

Balancer phải xét các ràng buộc zone. Nếu zone VN quá nóng nhưng không có thêm capacity trong những shards thuộc VN, không thể chỉ chuyển một chunk VN sang EU mà không vi phạm policy.

### Điều cần kiểm tra

1. Shard-key ranges và zone assignment.
2. Shards được phép giữ dữ liệu zone.
3. Capacity còn lại trong zone.
4. Ảnh hưởng đến read locality.
5. Replica placement của từng shard.

**Rebalance là tối ưu dưới ràng buộc**, không phải luôn chuyển tới node ít dữ liệu nhất trên toàn cluster.

## 24. Cassandra: token ranges và vnodes thay vì chunk split thủ công

Apache Cassandra dùng partition key để tính **token**, rồi gán các token ranges tới replica sets theo partitioner, topology và replication strategy.

~~~text
Partition key
   |
   v
Hash → Token
   |
   v
Token range / vnode ownership
   |
   v
Replicas theo RF, rack, DC
~~~

Một node có thể sở hữu **nhiều token ranges** (*virtual nodes/vnodes*). Thêm node hoặc đổi topology làm những khoảng token và tập replica cần được phân phối lại.

### Khác MongoDB chunk split

Không nên coi Cassandra hỗ trợ lệnh tương đương:

~~~text
SPLIT HOT PARTITION KEY "VIP" INTO TWO HALF-ROWS
~~~

chỉ vì nó có vnodes. Trong Cassandra, một **partition key cụ thể** hash về một token, do đó partition của key đó vẫn có một tập replica được xác định bởi topology.

Nếu partition `tenant=VIP` quá nóng, hướng giải quyết thường là **đổi partition-key design/bucketing** hoặc mô hình ghi; thêm vnodes chỉ chia nhỏ **ownership của nhiều token ranges**, không bẻ một partition key thành nhiều khóa.

## 25. Cassandra: thêm node là một dạng rebalance có streaming

Giả sử ba node A/B/C giữ các token ranges; node D tham gia:

~~~text
Before:
  A: ranges A1, A2, A3
  B: ranges B1, B2, B3
  C: ranges C1, C2, C3

Add D:
  D được giao những ranges hoặc replica responsibilities
  theo token allocation/topology mới.
~~~

Tham gia cụm cần **bootstrap/streaming** để D nhận những dữ liệu cần lưu. Những replica khác có thể phải gửi nhiều ranges, tùy RF, vnode layout và phiên bản.

### Các khái niệm vận hành Cassandra

| Khái niệm | Vai trò |
| --- | --- |
| **Bootstrap** | Node mới nhận data/token responsibilities theo quy trình |
| **Decommission** | Loại node có kế hoạch và chuyển data responsibilities |
| **Replace node** | Thay node lỗi theo quy trình supported |
| **Stream** | Truyền dữ liệu/ranges giữa node |
| **Repair/anti-entropy** | Làm replica đồng bộ phù hợp sau thời gian chênh lệch |
| **Cleanup** | Dọn dữ liệu không còn thuộc node sau thay đổi ownership theo quy trình |
| **Snitch/DC/rack** | Thông tin topology cho replica placement |

**Không tự thao tác token map bằng script rồi coi đã di chuyển dữ liệu**. Một vòng token được tính lại chưa có nghĩa streaming, repair và replica redundancy đã hoàn thành.

## 26. Cassandra: vì sao tăng vnode không nhất thiết sửa hot node?

Giả sử:

~~~text
Node A:
  RF=3 replica data
  16 vnodes
  Disk=85%, QPS=10.000

Node B:
  16 vnodes
  Disk=35%, QPS=3.000
~~~

Có thể do token ownership phân phối chưa đều, nhưng cũng có thể:

- Partition sizes lệch.
- Node A chứa replica của nhiều hot partitions.
- Compaction backlog làm CPU cao.
- Một node có hardware yếu hơn.
- Client routing và cache locality lệch.

Tăng cùng một số vnodes cho mọi node **không bảo đảm** A giảm tải. Cần xác định token/replica map thực tế, workload theo partition và các node đích có capacity hay không.

### Một key quá nóng

Nếu 90% writes nhắm `(tenantId="VIP", bucket="current")`, partition key này vẫn hash về một token. Vnode ownership thay đổi chỉ có thể **chuyển hotspot sang một replica set khác**, không phân nhỏ thao tác của đúng key đó.

## 27. Cassandra: việc đổi partition key có tác động dữ liệu

Giả sử lưu event:

~~~sql
CREATE TABLE events_by_tenant (
    tenant_id text,
    event_time timestamp,
    event_id text,
    payload text,
    PRIMARY KEY ((tenant_id), event_time, event_id)
);
~~~

Một tenant lớn tạo một partition quá nóng. Có thể thiết kế bảng mới:

~~~sql
CREATE TABLE events_by_tenant_bucket (
    tenant_id text,
    bucket int,
    event_time timestamp,
    event_id text,
    payload text,
    PRIMARY KEY ((tenant_id, bucket), event_time, event_id)
);
~~~

Chọn `bucket` theo một hàm ổn định phù hợp workload, ví dụ từ event ID. Khi đó một tenant có nhiều partition keys và có thể phân phối qua nhiều token ranges.

Đổi lại:

- Query mọi event của tenant cần fan-out nhiều buckets.
- Việc sắp xếp toàn cục khó hơn.
- Migration bảng cũ sang bảng mới cần backfill và xử lý writes đồng thời.
- Số buckets và chính sách tăng buckets cần versioning.

**Đây là tái thiết kế dữ liệu theo nghiệp vụ, không phải câu lệnh split một token range.**

## 28. Cassandra: thay RF không phải rebalance thông thường

Ví dụ:

~~~sql
ALTER KEYSPACE ecommerce
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc_hcm': 3,
    'dc_hn': 3
};
~~~

Sau khi thay replication metadata, các replica mới có thể **chưa có dữ liệu lịch sử**. Việc sửa/stream dữ liệu theo quy trình đúng phiên bản là cần thiết để đáp ứng RF mong muốn.

Phân biệt:

- **Thêm node:** tăng capacity và thay tập replica/ownership.
- **Đổi RF:** thay số bản sao cho mỗi partition, không tự thêm capacity.
- **Đổi số vnode/token:** thay granularity/ranges ownership, không tự tăng RF.
- **Repair:** làm replica có dữ liệu phù hợp.

Trong cluster đang nóng, làm nhiều thay đổi topology cùng lúc có thể khiến streaming/compaction vượt năng lực của node còn lại. Cần kiểm soát trình tự thay đổi.

## 29. Redis Cluster: hash slot là đơn vị di chuyển

Redis Cluster không dùng cùng mô hình vnode token ring như Cassandra. Nó tổ chức keyspace thành **16.384 hash slots** (0..16383).

\[
\operatorname{slot}(k)=\operatorname{CRC16}(k)\bmod 16384
\]

(Có quy tắc hash tag trong key như `user:{42}:cart`.)

~~~text
Key → hash slot → node primary giữ slot

Node A: slots 0..4999
Node B: slots 5000..10999
Node C: slots 11000..16383
~~~

### Resharding là chuyển slot ownership

Thêm Node D:

~~~text
Before:
  A: slots 0..4999

After reshard:
  A: slots 0..3499
  D: slots 3500..4999
~~~

Đây là minh họa; trong thực tế các slots được chọn có thể rải rác chứ không bắt buộc một dải liên tục.

Khi slot chuyển, **các keys thuộc slot đó** cũng cần được di chuyển theo cơ chế resharding. Không được chỉ sửa mapping slot→node rồi bỏ lại keys.

## 30. Redis Cluster: migrating, importing, MOVED và ASK

Redis Cluster có cơ chế trạng thái **slot migration** để client vẫn có thể xử lý request trong quá trình reshard:

~~~text
Slot s:
  Source A: MIGRATING
  Target D: IMPORTING
~~~

Client đang dùng metadata cũ hoặc tới sai node có thể nhận redirect theo quy tắc của Redis Cluster.

### MOVED

`MOVED` báo cho client biết slot thuộc node khác; client Redis Cluster phù hợp thường **cập nhật mapping slot → node**.

### ASK

`ASK` là chỉ dẫn **tạm thời** trong lúc slot migration. Client theo redirect và thực hiện handshake/chế độ lệnh tương ứng theo giao thức; không được đồng nhất với việc sở hữu vĩnh viễn đã đổi.

### Cần chú ý multi-key operations

Các phép toán nhiều key trong Redis Cluster thường yêu cầu các keys thuộc **cùng hash slot**. Nếu chúng nằm ở nhiều slots, không thể tự coi một lệnh multi-key là transaction phân tán.

Ví dụ:

~~~text
user:{42}:cart
user:{42}:favorites
~~~

chia sẻ hash tag `42` nên cùng slot theo quy tắc Redis. Đổi lại, tag quá rộng có thể tạo một **hot slot**, khó phân nhỏ nếu không thay key design.

## 31. Redis: chuyển slot không tự chia hot key

Giả sử:

~~~text
key = global:likes
slot = 8172
QPS = 100.000/s
~~~

Nếu move slot 8172 từ A sang B:

~~~text
Node A giảm tải.
Node B nhận hotspot.
~~~

Tổng tải của **một key** không bị phân nhỏ. Redis Cluster không có phép “split một hash slot thành hai slots mới” tùy ý bằng cách tăng node; số slots cơ bản là cố định.

Muốn chia workload có thể cân nhắc:

~~~text
likes:shard:00
likes:shard:01
...
likes:shard:15
~~~

và tổng hợp khi đọc, nhưng phải quản lý:

- Số shard logic.
- Duplicate requests/idempotency.
- Consistency của tổng.
- Chi phí đọc nhiều keys.
- Chính sách nâng/đổi số shards.

Đây là thay mô hình dữ liệu, không phải rebalance slot đơn thuần.

## 32. Redis: thao tác quản trị reshard cần kiểm soát

Một công cụ phổ biến là `redis-cli --cluster reshard` với arguments/topology phù hợp. Trong môi trường thực, thao tác chuyển slots có thể kích hoạt:

- Di chuyển keys của từng slot.
- Redirect tạm trong quá trình chuyển.
- Thay mapping ownership.
- Thay đổi latency và tải network.

Không viết script production kiểu:

~~~text
for each key:
  DUMP on source
  RESTORE on target
  DEL on source
~~~

rồi tự tuyên bố slot đã chuyển an toàn. Phải dùng cơ chế resharding được Redis Cluster hỗ trợ và xử lý concurrent writes, TTL, authentication, conflict, redirect.

**Không được tự sửa trực tiếp slot metadata trên các node khi chưa hiểu giao thức.**

## 33. Apache HBase: region là đơn vị split và move

Apache HBase tổ chức bảng theo **row key ranges** thành các **regions**. Region được một **RegionServer** phục vụ theo cơ chế của HBase.

~~~text
HBase table: users

Region R1: rows [A, H) → RegionServer 1
Region R2: rows [H, R) → RegionServer 2
Region R3: rows [R, +∞) → RegionServer 3
~~~

Đây là hệ mà **split, merge, move region** là các khái niệm vận hành rất trực tiếp.

### Region split

Nếu R2 quá lớn:

~~~text
R2: [H,R)
     |
   split at M
     v
R2a: [H,M)
R2b: [M,R)
~~~

Hai daughter regions có thể được server/balancer phân phối theo quy tắc HBase. **Split không nhất thiết ngay lập tức copy toàn bộ StoreFiles**; cơ chế HBase/HDFS và reference/compaction có thể làm thao tác vật lý khác với split của một service lưu dữ liệu tự sở hữu.

### Region move

Một region có thể được **reassign** sang RegionServer khác để phân phối tải. Cơ chế của HBase xử lý quyền phục vụ region; không nên tự copy HFiles rồi cập nhật DNS như một phép move.

## 34. HBase: merge regions và metadata overhead

Nếu bảng có rất nhiều regions nhỏ:

~~~text
R1 [A,C)
R2 [C,E)
R3 [E,G)
R4 [G,I)
...
~~~

thì mỗi region tạo overhead quản lý, scheduling và metadata; nhiều region có thể ảnh hưởng bộ nhớ/tài nguyên RegionServer.

Một merge phù hợp:

~~~text
R1 [A,C)
R2 [C,E)
     |
    merge
     v
R [A,E)
~~~

Điều kiện merge, tính kề nhau, trạng thái regions và công cụ/quyền thao tác phụ thuộc version. HBase có thể có API quản trị split/merge/move, nhưng **không coi pseudocode dưới đây là lệnh production**:

~~~text
splitRegion(region, splitKey)
mergeRegions(regionA, regionB)
moveRegion(region, targetServer)
~~~

### Merge sai có thể tăng điểm nóng

Nếu R1 và R2 đều có workload cao, merge chúng thành một region duy nhất có thể **dồn công việc phục vụ về một RegionServer**, làm hiệu năng giảm. Merge nên nhằm giảm overhead những vùng nhỏ/ít tải, không phải gom mọi vùng cho ít metadata nhất.

## 35. HBase: row-key design có thể gây hotspot ở đầu/cuối range

Một bảng dùng row key là timestamp tăng dần:

~~~text
2026-11-14T00:00:01
2026-11-14T00:00:02
2026-11-14T00:00:03
...
~~~

Write mới thường đến **vùng cuối của keyspace**, gây hotspot ở một region dù các region cũ rất rảnh.

Split vùng đó có thể đẩy dữ liệu lịch sử sang các regions khác, nhưng **các ghi mới vẫn tập trung vào vùng chứa timestamp mới nhất**.

Hướng thiết kế có thể gồm:

- Salt/prefix đủ đa dạng.
- Bucketing theo tenant/device/time phù hợp.
- Thay row-key order để phân bố writes.
- Read model riêng cho truy vấn theo thời gian.

Đổi key cần cân nhắc range scan, sort order, TTL và chi phí đọc nhiều prefixes. **Không áp dụng salt ngẫu nhiên nếu nó phá access pattern chính**.

## 36. DynamoDB: partition split và adaptive capacity là managed behavior

Trong Amazon DynamoDB, người dùng thiết kế **partition key** và truy cập bảng/index theo API dịch vụ. Việc phân chia **physical partitions**, điều phối dung lượng và placement phần lớn do dịch vụ quản lý.

### Những thuật ngữ cần phân biệt

- **Logical partition key:** giá trị partition key trong một item.
- **Physical partition:** đơn vị hạ tầng mà dịch vụ dùng để lưu/phục vụ một phần dữ liệu.
- **Adaptive capacity:** cơ chế dịch vụ phân bổ khả năng xử lý phù hợp hơn với workload trong phạm vi hỗ trợ.
- **Split for heat:** kỹ thuật nội bộ/được tài liệu mô tả ở những tình huống nhất định nhằm chia vật lý để xử lý phân bố tải, **không phải API chung `SPLIT PARTITION` người dùng tự gọi**.

### Hot partition key

Giả sử:

~~~text
PK = "EVENT#GLOBAL"
Mọi ghi trong ngày dùng cùng partition key.
~~~

Tăng provisioned capacity hoặc chuyển sang on-demand không tự bảo đảm **một giá trị partition key duy nhất** có throughput vô hạn. Giới hạn phụ thuộc item size, access pattern, sort key distribution, index và chế độ capacity; không nên hứa dịch vụ tự split được một single-item hotspot.

### Thiết kế để phân phối writes

Ví dụ:

~~~text
PK = "EVENT#GLOBAL#BUCKET#00"
PK = "EVENT#GLOBAL#BUCKET#01"
...
PK = "EVENT#GLOBAL#BUCKET#15"
~~~

Các writers phân tán ra nhiều logical partition keys. Nhưng query tổng phải đọc/gộp nhiều buckets, và idempotency vẫn là trách nhiệm riêng.

**Với managed NoSQL, ưu tiên thiết kế key và đo metrics được dịch vụ công bố**, không giả định mình có quyền điều khiển physical split/move như HBase hoặc Cassandra.

## 37. Elasticsearch/OpenSearch: relocation khác split/shrink index

Những hệ search phân tán như Elasticsearch có khái niệm:

- **Primary shard:** đơn vị logic của index.
- **Replica shard:** bản sao phục vụ redundancy/read theo cơ chế hệ.
- **Shard allocation/rebalancing:** đặt hoặc di chuyển shard copy giữa nodes.
- **Index split/shrink:** các thao tác tạo index với số primary shards mới theo ràng buộc riêng.

Ví dụ:

~~~text
Index logs:
  Shard 0 → Node A
  Shard 1 → Node A
  Shard 2 → Node B
  Shard 3 → Node C
~~~

Nếu A quá tải, allocator có thể chuyển một shard copy tới node khác theo allocation rules.

### Relocation

~~~text
Shard 1: Node A → Node D
~~~

Thường **không thay đổi số primary shards**; chỉ thay vị trí lưu/phục vụ một shard copy.

### Split/shrink index

Tăng/giảm **số primary shards** của một index chịu nhiều điều kiện về index state, số shard tương thích, khả năng đọc-ghi và storage/version. Không nên gọi chúng là “split một shard nóng ngay trong chỗ rồi xong”.

Một workflow có thể phải tạo target index và chuyển alias/cutover theo API được hỗ trợ; không thể merge hai shard bất kỳ thành một shard tùy ý mà bỏ qua ràng buộc.

**Ranh giới:** Elasticsearch là hệ tìm kiếm/phân tích tài liệu, không đại diện chung cho mọi transaction-oriented NoSQL. Ví dụ này giúp phân biệt **shard relocation** với **thay cấu trúc primary-shard của index**.

## 38. So sánh các hệ theo đơn vị di chuyển

| Hệ | Đơn vị phân phối chính | Split/merge theo ý nghĩa nào? | Move/rebalance điển hình |
| --- | --- | --- | --- |
| **Cassandra** | Token ranges, vnodes và replica assignments | Đổi token-range granularity qua topology; không tự split một partition key | Bootstrap/decommission/replace, streaming, repair |
| **MongoDB sharded cluster** | Shard-key ranges/chunks trên shards | Điều chỉnh ranh giới chunks theo version/cơ chế | Balancer/chunk migration; resharding khi đổi shard key |
| **Redis Cluster** | 16.384 hash slots | Không tùy ý split số slots; có thể chuyển các slots | Reshard/slot migration, MOVED/ASK |
| **HBase** | Ordered row-key regions | Region split và region merge | Region assignment/move/balancer |
| **DynamoDB** | Logical keys, physical partitions do dịch vụ quản lý | Auto split/adaptive capacity theo điều kiện dịch vụ | Service-managed placement; khách hàng sửa key/model |
| **Elasticsearch** | Index primary/replica shards | Split/shrink index theo điều kiện | Shard allocation/relocation |

**Bảng giúp định hướng**, không thay thế tài liệu của đúng release. Một số hệ có nhiều cách triển khai, managed variant hoặc storage engine thay đổi chi tiết.

## 39. Đơn vị nhỏ hơn không phải lúc nào tốt hơn

Một chiến lược split quá mạnh có thể tạo ra:

~~~text
10 regions → 100.000 regions
~~~

Điều này không tự cải thiện performance vì có thể làm tăng:

- Metadata.
- Scheduling.
- Background maintenance.
- Open file handles/bộ nhớ.
- Repair/compaction bookkeeping.
- Số request tới coordinator/metadata service.

Ngược lại, quá ít vùng khiến một đơn vị rất lớn, khó cân bằng và tạo blast radius lớn khi move.

### Mục tiêu hợp lý

Chọn độ lớn đơn vị quản lý phù hợp với:

- Kích thước dữ liệu và tốc độ tăng.
- QPS/IOPS mỗi vùng.
- Chi phí metadata và memory.
- Mạng dùng khi relocation.
- Recovery Time Objective.
- Giới hạn/khuyến nghị DBMS.

**Granularity là một điểm cân bằng giữa linh hoạt và overhead.**

## 40. Khi split có thể cải thiện đọc nhưng không cải thiện ghi

Giả sử vùng `R` chứa 10 triệu products, trong đó:

- 90% reads phân bố đều trên products.
- 99% writes chỉ cập nhật `productId=FLASH`.

Split R thành hai vùng, rồi move một vùng:

~~~text
Reads: có thể chia qua hai nodes.
Writes: hot product FLASH vẫn thuộc một vùng.
~~~

Kết quả có thể giảm read latency nhưng write throughput của hot key không tăng.

**Đo riêng read hotspot và write hotspot.** Nếu chỉ nhìn tổng QPS, một rebalance có thể đạt mục tiêu sai.

## 41. Những thay đổi cạnh tranh trong lúc migration

Xét:

~~~text
T0: source A snapshot balance=100
T1: source A nhận +10 → 110
T2: target B đã copy snapshot 100
T3: client retry +10 sau timeout
T4: cutover A→B
~~~

Nếu thiếu cơ chế delta/catch-up và idempotency, target có thể:

- Thiếu lần cộng ở T1.
- Áp hai lần cộng do retry ở T3.
- Áp một mutation cũ sau mutation mới.

### Các cơ chế cần phân biệt

| Cơ chế | Giải quyết vấn đề gì? |
| --- | --- |
| Snapshot/copy | Chuyển trạng thái tại một mốc |
| Change log/CDC/catch-up | Chuyển thay đổi sau snapshot |
| Ownership epoch/fencing | Chỉ owner hợp lệ nhận write |
| Conditional update/CAS | Phát hiện trạng thái cũ khi ghi |
| Idempotency key | Một ý định retry không tạo hiệu ứng lặp |
| Transaction/atomic handoff | Bảo vệ ranh giới commit theo protocol |
| Reconciliation | Phát hiện sai lệch sau migration |

**Move đúng dữ liệu không tự biến mọi API thành exactly-once.** Retry sau timeout và event reprocessing vẫn phải được giải quyết theo nghiệp vụ.

## 42. Consistency model trong lúc rebalance

Một DBMS có thể hứa các mức đọc khác nhau:

- Linearizable reads/writes trong phạm vi phù hợp.
- Quorum-based operations với bảo đảm riêng.
- Read-your-writes theo session.
- Eventual reads từ replica/index/cache.

Rebalance phải bảo vệ **consistency contract đã hứa**, không chỉ tránh mất file.

Ví dụ:

~~~text
Client A: write(x=1) → ACK
Migration cutover
Client B: read(x)    → 0
~~~

Nếu B đọc sau ACK, không có write khác và đường read hứa linearizability, lịch này là sai. Nếu B đọc từ read model eventual, giá trị cũ có thể nằm trong contract. **Không thể kết luận bằng một lần GET mà không biết đường đọc và mức consistency.**

### Cần giữ session token qua reroute

Nếu một client đã thấy version 20, chuyển node trong migration rồi thấy version 18 có thể vi phạm **monotonic reads** nếu phiên được bảo đảm thuộc tính đó. Route/driver có thể cần thông tin version watermark theo protocol.

## 43. Replication không được phá trong khi move

Giả sử RF=3 với ba replica ở ba rack. Một migration cố đưa replica từ rack C sang rack D:

~~~text
Before:
  A/rack-a
  B/rack-b
  C/rack-c

After:
  A/rack-a
  B/rack-b
  D/rack-d
~~~

Trong lúc chuyển, không được tự xóa C quá sớm nếu D chưa có đủ dữ liệu. Cần xem:

- Số replica thực đang có dữ liệu.
- Quorum/commit requirements.
- Topology/rack constraints.
- Trạng thái rebuild/repair.
- Độ mới của D.

Một hệ có thể **tạm giữ nhiều bản sao vật lý hơn RF mục tiêu trong migration** theo cơ chế an toàn. Nhưng không nên tự mặc định điều đó ở mọi engine; phải dùng supported protocol.

## 44. Capacity và chi phí mạng liên vùng

Di chuyển một range giữa hai node cùng rack có thể có chi phí thấp hơn chuyển sang DC khác qua WAN.

~~~text
Intra-node storage:    local I/O
Intra-rack transfer:   local network
Cross-AZ transfer:     có thể có phí/băng thông khác
Cross-region transfer: WAN latency, egress, data residency
~~~

Khi cân bằng cần tính:

1. Tổng bytes cần chuyển.
2. Băng thông khả dụng sau khi trừ traffic online.
3. I/O đọc source và I/O ghi target.
4. Compaction hoặc merge file.
5. Encryption/compression CPU.
6. Chi phí cloud transfer.
7. RTO nếu một node khác hỏng giữa quá trình.

**Chọn đích có ít disk không đủ.** Đích còn phải thuộc failure domain hợp lệ và có CPU/network để phục vụ workload sau move.

## 45. Không gộp khi đang tăng trưởng nhanh

Giả sử hai vùng:

~~~text
R1 size=100 GiB, tăng 20 GiB/ngày
R2 size=100 GiB, tăng 20 GiB/ngày
~~~

Nếu merge:

~~~text
R = 200 GiB, tăng 40 GiB/ngày
~~~

Sau một thời gian, có thể phải split lại. Việc merge chỉ để giảm số vùng **trong một ngày** có thể tạo chu kỳ split–merge tốn kém.

Trước khi merge hãy xét:

- Data growth forecast.
- Read/write growth.
- Mức phân tán của hot keys.
- Chi phí split lại.
- Thời gian nhỏ/vắng thực tế của vùng.
- Thời gian duy trì ổn định.

**Merge phù hợp với vùng nhỏ ổn định, không phải mọi vùng vừa bị split.**

## 46. Kiểm thử trước khi bật rebalance tự động

Một kế hoạch nên có các tình huống:

~~~text
1. Thêm một node rỗng.
2. Một node gần đầy disk.
3. Một hot range nhưng nhiều keys độc lập.
4. Một hot key không thể split.
5. Source crash trong lúc copy.
6. Target crash trước cutover.
7. Target crash sau cutover.
8. Mạng chập chờn, request timeout.
9. Write liên tục khi đang snapshot/catch-up.
10. Client dùng routing metadata cũ.
11. Replica offline rồi hồi phục.
12. Rack/AZ lỗi giữa migration.
~~~

### Điều cần xác minh

- Không có dữ liệu thiếu/nhân trùng trái nghiệp vụ.
- Ranh giới range phủ đầy đủ, không overlap bất hợp lệ.
- Read/write còn đạt consistency đã cam kết.
- Không có hai authoritative owners cùng nhận write trái protocol.
- Backfill/streaming có thể hoàn tất.
- Throttling bảo vệ latency online.
- Có thể resume hoặc rollback an toàn.
- Quorum/replica placement không bị phá.

**Một lần di chuyển thành công khi không có traffic không chứng minh hệ xử lý đúng concurrent writes.**

## 47. Observability: đo trước, trong và sau migration

| Giai đoạn | Metric cần ghi |
| --- | --- |
| **Trước** | Bytes/node, hot ranges, QPS, p95/p99, cache locality |
| **Prepare** | Disk/network capacity target, topology/failure domains |
| **Copy** | Bytes copied, transfer rate, source/target I/O |
| **Catch-up** | Mutation backlog, lag, retries, write rate |
| **Cutover** | Ownership generation, redirects, request failures |
| **Sau** | New QPS/node, latency, data placement, reconciliation |
| **Recovery** | Resume attempts, stale source/target, unfinished cleanup |

Một bảng theo dõi mẫu:

~~~text
rangeId | source | target | bytes | phase     | progress | lag
------- | ------ | ------ | ----- | --------- | -------- | ---
R-42    | A      | D      | 120GB | COPYING   | 74%      | 8s
R-43    | B      | E      |  20GB | CATCH_UP  | 99%      | 1s
R-44    | C      | F      |  50GB | CUTOVER   | 100%     | 0s
~~~

Đây là **minh họa log vận hành**, không phải output chuẩn của một DBMS.

### Không đo chỉ bytes

Hai node có cùng dung lượng sau rebalance nhưng p99 của một node tăng gấp ba có thể là **rebalance không đạt mục tiêu hiệu năng**. Cần đối chiếu trước/sau cả load, latency, skew và khả năng chịu lỗi.

## 48. Một mô hình Java để hiểu split, move và merge

Ví dụ sau mô phỏng metadata về những khoảng khóa **[start,end)** trên miền số nguyên từ 0 đến 99. Nó không thực hiện file copy hoặc mạng, chỉ giúp nhìn rõ **split/merge/move thay đổi ranh giới và owner như thế nào**.

Tạo `RangeRebalanceDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public final class RangeRebalanceDemo {

    static final class Range {
        final int start;
        final int end;          // exclusive
        final String owner;

        Range(int start, int end, String owner) {
            if (start >= end) {
                throw new IllegalArgumentException("Empty range");
            }
            this.start = start;
            this.end = end;
            this.owner = owner;
        }

        boolean contains(int key) {
            return start <= key && key < end;
        }

        @Override
        public String toString() {
            return "[" + start + "," + end + ")@" + owner;
        }
    }

    static List<Range> split(
            List<Range> ranges, int index, int splitPoint) {
        Range old = ranges.get(index);
        if (!(old.start < splitPoint && splitPoint < old.end)) {
            throw new IllegalArgumentException("Split outside range");
        }

        List<Range> next = new ArrayList<>(ranges);
        next.remove(index);
        next.add(new Range(old.start, splitPoint, old.owner));
        next.add(new Range(splitPoint, old.end, old.owner));
        sort(next);
        return next;
    }

    static List<Range> move(
            List<Range> ranges, int index, String newOwner) {
        Range old = ranges.get(index);
        List<Range> next = new ArrayList<>(ranges);
        next.set(index,
                new Range(old.start, old.end, newOwner));
        return next;
    }

    static List<Range> merge(
            List<Range> ranges, int leftIndex) {
        Range left = ranges.get(leftIndex);
        Range right = ranges.get(leftIndex + 1);

        if (left.end != right.start) {
            throw new IllegalArgumentException("Not adjacent");
        }
        if (!left.owner.equals(right.owner)) {
            throw new IllegalArgumentException(
                    "Move to same owner before this toy merge");
        }

        List<Range> next = new ArrayList<>(ranges);
        next.remove(leftIndex + 1);
        next.set(leftIndex,
                new Range(left.start, right.end, left.owner));
        return next;
    }

    static void sort(List<Range> ranges) {
        ranges.sort(Comparator.comparingInt(r -> r.start));
    }

    static void verifyCoverage(
            List<Range> ranges, int min, int maxExclusive) {
        sort(ranges);
        int cursor = min;
        for (Range range : ranges) {
            if (range.start != cursor) {
                throw new IllegalStateException(
                        "Gap or overlap at " + cursor);
            }
            cursor = range.end;
        }
        if (cursor != maxExclusive) {
            throw new IllegalStateException(
                    "Coverage ends at " + cursor);
        }
    }

    static void print(String phase, List<Range> ranges) {
        System.out.println(phase + ":");
        for (Range range : ranges) {
            System.out.println("  " + range);
        }
    }

    public static void main(String[] args) {
        List<Range> ranges = new ArrayList<>();
        ranges.add(new Range(0, 100, "Node-A"));
        verifyCoverage(ranges, 0, 100);
        print("Initial", ranges);

        ranges = split(ranges, 0, 40);
        verifyCoverage(ranges, 0, 100);
        print("After split", ranges);

        // [40,100) là range thứ hai sau sort.
        ranges = move(ranges, 1, "Node-B");
        verifyCoverage(ranges, 0, 100);
        print("After move", ranges);

        // Hồi chuyển về A để mô phỏng merge khi cùng owner.
        ranges = move(ranges, 1, "Node-A");
        ranges = merge(ranges, 0);
        verifyCoverage(ranges, 0, 100);
        print("After merge", ranges);
    }
}
~~~

Chạy:

~~~bash
javac RangeRebalanceDemo.java
java RangeRebalanceDemo
~~~

Kết quả dự kiến:

~~~text
Initial:
  [0,100)@Node-A
After split:
  [0,40)@Node-A
  [40,100)@Node-A
After move:
  [0,40)@Node-A
  [40,100)@Node-B
After merge:
  [0,100)@Node-A
~~~

### Điều chương trình minh họa

- Split làm tăng số ranges nhưng ban đầu **không đổi owner**.
- Move đổi owner trong metadata nhưng **không copy byte dữ liệu**.
- Merge trong mô hình đơn giản yêu cầu hai ranges kề nhau và cùng owner.
- Hàm kiểm coverage phát hiện gap/overlap giữa ranges.

### Điều chương trình không mô phỏng

- Concurrent writes và versioned ownership.
- Snapshot/catch-up.
- Replication/quorum/transaction.
- Node crash hoặc network partition.
- Disk bytes, compaction và routing cache.

**Không dùng chương trình này làm thuật toán migration production**. Nó là công cụ học phân biệt **metadata transformation** với **physical data movement**.

## 49. Mở rộng Java: chọn vùng nên chuyển theo tải

Cho ba node:

~~~text
Node A:
  R1 100 GiB,  2.000 QPS
  R2 200 GiB, 40.000 QPS
  R3 150 GiB,  1.000 QPS

Node B:
  R4 200 GiB,  5.000 QPS

Node C:
  R5 150 GiB,  4.000 QPS
~~~

Nếu mục tiêu là giảm **bytes skew**, chuyển R2 sang node khác có vẻ hợp lý theo kích thước. Nếu mục tiêu là giảm **hot QPS**, cũng có thể nhắm R2. Nhưng nếu R2 chứa **một hot key** chiếm 39.000 trong 40.000 QPS, chuyển R2 chỉ **chuyển hotspot** từ A sang node mới.

### Bài thực hành tự triển khai

1. Thêm trường `sizeGiB` và `qps` vào mô hình range.
2. Tính tổng bytes và QPS theo owner.
3. Chọn vùng mà việc move làm giảm chênh lệch tải giữa node cao nhất và thấp nhất.
4. Thêm điều kiện target phải có đủ disk headroom.
5. Cấm move nếu target nằm trong failure domain không hợp lệ với replica khác.
6. Thêm cooldown để vùng vừa move không được di chuyển tiếp ngay.

Đây là **bài toán tối ưu nhiều ràng buộc**; không có một tiêu chí duy nhất đúng cho mọi workload.

## 50. Bài tập phân tích

### Bài 1 — Phân biệt bốn thao tác

Cho cluster:

~~~text
Node A: R1, R2, R3
Node B: R4
Node C: R5
~~~

Nếu muốn đưa R3 từ A sang C, đó là split, merge hay move? Nếu R2 quá lớn và cần chia làm hai phần độc lập thì cần thao tác gì trước khi move?

**Gợi ý:** chuyển R3 là move; tách R2 là split rồi có thể move.

### Bài 2 — Split không chuyển máy

R=[0,100) ở A, split tại 40. Viết mapping ngay sau split nếu chưa migration. Một người nói “phần [40,100) chắc chắn đã sang B”, người đó sai ở đâu?

**Gợi ý:** hai vùng mới đều có thể vẫn trên A.

### Bài 3 — Merge có khoảng trống

Cho R1=[0,40), R2=[60,100). Có thể merge thành [0,100) mà không bổ sung quyền sở hữu cho [40,60) không?

**Gợi ý:** không; merge liên tục phải xét gap và điều kiện metadata.

### Bài 4 — Chọn split point

Trong range [0,100), 90% bytes nằm ở [80,100). Vì sao split ở 50 không cân bằng disk? Hãy đề xuất cách chọn split point dựa trên dữ liệu.

**Gợi ý:** median theo bytes hoặc histogram key có thể phù hợp hơn midpoint giá trị.

### Bài 5 — Hot key

Một key nhận 100.000 update/s. Khi split range bao quanh nó thành hai khoảng, QPS tự chia 50/50 không?

**Gợi ý:** không; hot key vẫn thuộc một khoảng, cần sharding logic hoặc đổi workflow.

### Bài 6 — Snapshot thiếu delta

Source A snapshot vùng R tại version=10. Sau đó ghi version=11,12; target B mới nhận snapshot 10 nhưng owner được chuyển sang B. Rủi ro gì xảy ra?

**Gợi ý:** target thiếu writes trong thời gian copy; cần catch-up/fencing.

### Bài 7 — Hai owner cùng ghi

Source A và target B cùng tin mình là owner của R sau network partition. Hãy giải thích nguy cơ và vai trò của epoch/fencing token.

**Gợi ý:** chỉ một quyền ghi hợp lệ sau cutover, theo protocol bảo vệ.

### Bài 8 — Tính băng thông

Vùng 600 GiB chuyển qua network hữu hiệu 80 MiB/s. Tính thời gian copy lý tưởng và nêu năm nguyên nhân khiến thời gian thật lâu hơn.

**Gợi ý:** 7680 giây, khoảng 128 phút; bỏ qua delta, compaction, mạng, throttling và retries trong phép chia.

### Bài 9 — MongoDB split vs move

Chunk [A,Z) của collection ở Shard 1 được split tại M. Ngay sau split, nếu không có migration, hai chunks nằm ở đâu? Nếu balancer move [M,Z) sang Shard 2 thì điều gì thay đổi?

**Gợi ý:** split chỉ thay ranh giới chunk; migration thay shard owner.

### Bài 10 — Shard key cardinality

Một MongoDB collection có shard key `tenantId` và một tenant giữ phần lớn dữ liệu. Vì sao balancer có thể không giải quyết tốt hotspot dù thêm shard?

**Gợi ý:** thiếu ranh giới shard-key đủ đa dạng; cân nhắc schema/reshard key.

### Bài 11 — MongoDB merge hay reshard

Phân biệt:

1. Merge hai chunks kề nhau trên cùng shard.
2. Thay shard key từ `tenantId` sang `(tenantId,bucket)`.

**Gợi ý:** thứ hai là thay đổi phân phối toàn collection, không chỉ merge metadata.

### Bài 12 — Cassandra vnode và hot partition

Node A sở hữu nhiều vnodes; một partition key `VIP` nhận 50.000 writes/s. Thêm node và tăng vnodes có tự chia partition VIP thành nhiều partition keys không?

**Gợi ý:** không; cần bucketing/thiết kế key, và xử lý hệ quả fan-out.

### Bài 13 — Cassandra bootstrap

Một node mới đã xuất hiện UP trong dashboard, nhưng chưa hoàn tất streaming. Có thể báo “rebalance xong và dữ liệu đủ” chưa? Vì sao?

**Gợi ý:** cần kiểm token ownership, replica data, streaming/repair và consistency.

### Bài 14 — RF và move

RF=3 được đặt ở rack-a, rack-b, rack-c. Muốn thay replica rack-c bằng rack-d. Khi nào mới có thể dọn bản cũ ở rack-c an toàn?

**Gợi ý:** sau khi bản mới đáp ứng điều kiện dữ liệu/protocol và topology đúng.

### Bài 15 — Redis Cluster

Trong Redis Cluster, một slot đang chuyển từ A sang B. Giải thích vì sao `ASK` không đồng nghĩa `MOVED` và client cần làm gì với routing metadata.

**Gợi ý:** redirect tạm khi importing/migrating so với mapping ownership đã đổi.

### Bài 16 — Redis hash tag

Các key `user:{42}:cart` và `user:{42}:favorites` được đặt cùng slot. Lợi ích là gì? Khi mọi user cùng dùng `{all}`, rủi ro gì?

**Gợi ý:** co-location multi-key nhưng tag quá rộng gây hot slot.

### Bài 17 — HBase

Region [A,Z) được split thành [A,M) và [M,Z). Sau split, vì sao có thể cần thêm region move để phân tán tải? Khi merge hai regions, cần xét điều gì?

**Gợi ý:** split tạo hai đơn vị; move đặt chúng trên RegionServers khác; merge giảm overhead nhưng có thể dồn hotspot.

### Bài 18 — HBase time-series

Row key là timestamp tăng dần, mọi insert vào region cuối. Split region nhiều lần có đảm bảo hết hotspot không?

**Gợi ý:** right-edge hotspot; phải thiết kế prefix/salt/bucket phù hợp.

### Bài 19 — DynamoDB

Một item duy nhất bị cập nhật liên tục. Vì sao không được mặc định rằng “adaptive capacity sẽ tự split item đó thành hai bản ghi độc lập”?

**Gợi ý:** physical partitioning khác thay đổi identity/transaction semantics của một item.

### Bài 20 — Elasticsearch

Shard relocation khác index split/shrink ở đâu? Nếu chỉ muốn giảm node A đang quá tải nhưng không muốn thay số primary shards, thao tác nào phù hợp hơn để xem xét?

**Gợi ý:** relocation/reallocation, không phải nhất thiết split index.

### Bài 21 — Thrashing

Một balancer chuyển R giữa A và B hàng giờ do CPU hai node luân phiên 51/49%. Đề xuất ba điều kiện chống rebalance thrashing.

**Gợi ý:** hysteresis, cooldown, minimum benefit, đo trong nhiều cửa sổ.

### Bài 22 — Các chỉ số

Sau rebalance, dung lượng ba node đều 1 TiB nhưng Node B có p99 2 giây trong khi A/C 100 ms. Có thể kết luận rebalance thành công không?

**Gợi ý:** storage balance không đồng nghĩa compute/read balance.

### Bài 23 — Test mất target

Target node crash sau khi copy snapshot nhưng trước cutover. Hãy mô tả một cơ chế phục hồi an toàn ở mức ý tưởng.

**Gợi ý:** source vẫn là authority hoặc giao thức đảm bảo rollback/retry, không xóa source sớm.

### Bài 24 — Test mất source

Source crash ngay sau khi ownership cutover sang target. Những điều gì phải được xác minh để đọc/ghi tiếp tục đúng?

**Gợi ý:** target đã catch-up, metadata được commit, route mới và replica/quorum đủ.

### Bài 25 — Định tuyến cũ

Driver giữ topology cache và tiếp tục gửi request tới node A sau khi vùng R đã chuyển sang B. Thiết kế an toàn cần xử lý điều gì?

**Gợi ý:** redirect, metadata refresh, fencing/epoch; không trả sai kiểu NOT_FOUND.

### Bài 26 — Di chuyển xuyên vùng

Một chunk 500 GiB được move sang datacenter khác. Ngoài bandwidth và latency, hãy liệt kê rủi ro về failure domain, data residency, RPO/RTO và quyền truy cập.

**Gợi ý:** không chọn node đích chỉ vì disk trống.

### Bài 27 — Mô hình dữ liệu theo truy vấn

Hệ cho thuê lưu hàng triệu listing, cần đọc theo `listingId` và lọc theo `city`. Một city có traffic gấp 100 lần city khác. Hãy đề xuất cách tách đọc/thao tác, tránh biến `city` thành một partition nóng và giải thích vai trò của rebalance vật lý.

**Gợi ý:** primary lookup theo listing ID và read model/search index theo city; fan-out/partitioning theo access patterns.

### Bài 28 — Thiết kế migration hoàn chỉnh

Một vùng dữ liệu R chiếm 1 TiB ở Node A, Node B còn nhiều disk nhưng đang đặt cùng AZ với một replica khác. Hãy viết kế hoạch:

1. Đánh giá cần split hay chỉ move.
2. Chọn target hợp lệ theo rack/AZ.
3. Tính headroom và thời gian streaming.
4. Xác định snapshot/catch-up/cutover.
5. Xử lý retry và request routing cũ.
6. Giám sát consistency/latency.
7. Cleanup và diễn tập rollback.

**Gợi ý:** “Node B còn disk” không phải điều kiện đủ để được chọn làm replica đích.

## 51. Một decision tree chọn split, merge, move hay đổi key

~~~text
Cluster mất cân bằng?
        |
        +-- Không: đừng thay topology nếu không có lý do.
        |
        +-- Có
             |
             v
       Hotspot nằm ở đâu?
             |
       +-----+------------------+
       |                        |
       v                        v
  Nhiều vùng trên          Một key/partition
  một node                 duy nhất rất nóng
       |                        |
       v                        v
  Move/rebalance         Đổi partition key,
  những vùng hợp lệ      bucket, sharded state,
       |                 cache hoặc coordinator
       v
  Có vùng quá lớn?
       |
   +---+---+
   |       |
  Có      Không
   |       |
   v       v
 Split nếu   Move trực tiếp
 DBMS cho     nếu hữu ích
 phép và
 có key boundary
       |
       v
  Quá nhiều vùng rất nhỏ?
       |
   +---+---+
   |       |
  Có      Không
   |       |
   v       v
 Merge có    Duy trì đơn vị
 điều kiện   hiện tại
~~~

Sơ đồ là **phương pháp đặt câu hỏi**, không phải thuật toán tự động. Sau khi chọn hướng cần kiểm tra khả năng của DBMS, replica/failure domains, consistency, migration cost và giám sát.

## 52. Mẫu tài liệu thay đổi vùng dữ liệu

~~~yaml
changeId: "MOVE-RANGE-042"
system: "Specific DBMS and version"
dataset: "orders"
reason: "Storage and QPS imbalance"
logicalUnit:
  type: "chunk / token range / slot / region / shard"
  id: "R-042"
  start: "inclusive lower bound"
  end: "exclusive upper bound"
  currentOwner: "node-A"
  targetOwner: "node-D"
  sizeBytes: "TBD"
  readQps: "TBD"
  writeQps: "TBD"
prerequisites:
  - "Target has sufficient disk/network/CPU"
  - "Replica/failure-domain policy is satisfied"
  - "Metadata is healthy"
  - "Backups and restore procedures are available"
  - "No conflicting schema/topology change"
execution:
  - "Use supported migration protocol"
  - "Track source snapshot and catch-up progress"
  - "Commit ownership cutover safely"
  - "Refresh routing/redirect old clients"
verification:
  - "No missing or duplicate business effects"
  - "Range coverage and ownership are correct"
  - "Quorum/replica placement remains valid"
  - "Read/write consistency guarantees hold"
  - "Latency and balance improve as expected"
rollback:
  beforeCutover: "Abort via supported procedure"
  afterCutover: "Version-specific recovery procedure"
monitoring:
  - "Bytes copied, lag, errors"
  - "Read/write p95 and p99"
  - "Retries and reroutes"
  - "Disk and compaction pressure"
  - "Data reconciliation"
cleanup:
  - "Remove obsolete copies only when safe"
  - "Update operational topology documentation"
~~~

Đây là **mẫu tài liệu thiết kế**, không phải cấu hình thực thi. Các trường `TBD` phải được điền trước khi dùng trong change request thật.

## 53. Những hiểu nhầm thường gặp

| Nhận định sai | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “Rebalance là split.” | Rebalance là mục tiêu; có thể chỉ move | Phân biệt mục tiêu và thao tác |
| “Split xong tự chuyển sang node khác.” | Có thể hai vùng vẫn cùng owner | Split rồi mới move nếu cần |
| “Merge giúp giảm tổng bytes dữ liệu.” | Merge chủ yếu giảm số vùng/metadata | Dữ liệu logic vẫn cần tồn tại |
| “Đổi owner map là chuyển data xong.” | Bytes và delta có thể chưa tới target | Stream/catch-up/cutover |
| “Split range giải quyết mọi hot key.” | Một key vẫn thuộc một range | Đổi partition-key/model |
| “Vùng cân bằng bytes thì cân bằng tải.” | QPS và CPU không tỉ lệ bytes | Theo dõi nhiều metrics |
| “Split midpoint luôn cân bằng.” | Data có thể lệch về một phía | Chọn theo histogram/size/heat |
| “Thêm node tự động giảm ngay hotspot.” | Thay topology cần thời gian và hotspot có thể không chia được | Phân tích đơn vị hotspot |
| “Dual-write A/B là đủ an toàn.” | Có thể lỗi một bên và đảo thứ tự | Dùng supported protocol/fencing |
| “Sau cutover có thể xóa source ngay.” | Target có thể chưa đủ data/replica/quorum | Verify rồi cleanup |
| “Nhiều migrate song song luôn nhanh hơn.” | Dễ nghẽn network, compaction, source I/O | Giới hạn concurrency |
| “MongoDB balancer sửa shard key sai.” | Một key/range khó chia không tự phân phối | Xem cardinality/resharding |
| “MongoDB merge chunk là resharding.” | Merge không đổi shard key | Phân biệt metadata và data mapping |
| “Cassandra vnodes tự tách hot partition key.” | Một partition key hash về một token | Bucketing/schema design |
| “Cassandra node UP tức data migration hoàn tất.” | Có thể đang stream/repair | Theo dõi giai đoạn và consistency |
| “Redis Cluster có thể tăng số hash slots tùy ý.” | Slot universe cơ bản cố định 16.384 | Move slot ownership |
| “Redis MOVED và ASK giống nhau.” | Redirect permanent vs temporary migration semantics | Driver xử lý đúng giao thức |
| “HBase split tức copy toàn bộ data ngay.” | HBase có cơ chế file/reference/compaction riêng | Xem storage engine |
| “DynamoDB physical partition split có lệnh admin chung.” | Hầu hết do dịch vụ quản lý | Thiết kế key và metrics public |
| “Elasticsearch relocation làm tăng primary-shard count.” | Relocation đổi vị trí shard copy | Split/shrink index là hoạt động khác |
| “Đủ disk trên target là đủ.” | Có thể sai rack/AZ, quota, CPU, network | Kiểm ràng buộc đầy đủ |
| “Replication thay thế backup trong migration.” | Delete/corruption có thể sao chép | Backup/restore riêng |

## 54. Tổng kết

**Rebalance, split, merge và move** là những công cụ liên quan nhưng có bản chất khác nhau:

1. **Rebalance là mục tiêu phân phối lại tải hoặc dữ liệu.** Nó có thể đạt được chỉ bằng move, hoặc cần split/merge và thay cấu trúc trước.
2. **Split chia một đơn vị có ranh giới thành các đơn vị nhỏ hơn.** Split giúp tăng độ mịn quản lý, nhưng không tự chuyển vùng sang máy mới và không tự chia một hot key.
3. **Merge gộp những vùng phù hợp**, thường để giảm overhead; cần cân nhắc tăng trưởng, hotspot và điều kiện kề nhau/placement của từng DBMS.
4. **Move chuyển quyền sở hữu/dữ liệu giữa nơi lưu.** Để an toàn khi online phải giải quyết snapshot, writes phát sinh, catch-up, fencing, routing, commit, validation và cleanup.
5. **Mỗi hệ có đơn vị migration riêng.** MongoDB dùng chunk/balancer; Cassandra dùng token ranges/vnodes/streaming; Redis Cluster dùng 16.384 hash slots; HBase dùng regions; DynamoDB quản lý physical partitions; Elasticsearch dùng shard allocation và split/shrink theo ràng buộc.
6. **Hot node, hot range và hot key là ba vấn đề khác nhau.** Chọn sai cấp xử lý có thể chỉ chuyển điểm nóng sang node khác.
7. **Đo nhiều chiều:** storage bytes, QPS, CPU, p95/p99, network, replica placement và repair lag. Cân bằng bytes đơn thuần chưa bảo đảm cân bằng hiệu năng.
8. **Metadata change không đồng nghĩa data migration hoàn tất.** Cần một protocol chuyển/cutover an toàn và khả năng phục hồi khi node lỗi giữa chừng.
9. **Failure domains và consistency contract phải được giữ trong lúc di chuyển.** Không hy sinh replication/quorum hoặc để hai owners cùng ghi chỉ để rebalance nhanh hơn.

**Nguyên tắc thực hành:** khi một cụm NoSQL mất cân bằng, hãy hỏi theo thứ tự **“đơn vị nào đang nóng?”, “nó có thể chia nhỏ theo key không?”, “vùng nào cần move?”, “ai có quyền nhận write trong lúc chuyển?”, và “bằng chứng nào cho thấy rebalance đã hoàn tất?”**. Chỉ sau khi trả lời được các câu đó mới chọn lệnh và quy trình vận hành của DBMS đang sử dụng.
