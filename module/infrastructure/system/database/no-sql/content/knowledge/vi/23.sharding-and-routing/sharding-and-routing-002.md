# Phân mảnh theo băm, khoảng giá trị hoặc danh mục định tuyến

## 1. Vì sao một cơ sở dữ liệu NoSQL cần chia dữ liệu thành nhiều mảnh?

Một ứng dụng học trực tuyến ban đầu lưu dữ liệu của mọi học viên trên một node:

~~~text
Node A
  Learner L001 -> courses, progress, events
  Learner L002 -> courses, progress, events
  Learner L003 -> courses, progress, events
  ...
~~~

Khi số học viên tăng lên hàng chục triệu, một node có thể không còn đáp ứng đủ:

- **Dung lượng:** dữ liệu và index vượt giới hạn lưu trữ an toàn.
- **Thông lượng:** lượng đọc và ghi vượt CPU, RAM hoặc I/O của node.
- **Độ trễ:** một nhóm khóa nóng khiến hàng đợi xử lý kéo dài.
- **Vận hành:** bảo trì, phục hồi, backup và rebalance mất quá nhiều thời gian.

**Sharding (phân mảnh ngang)** chia tập bản ghi thành các nhóm nhỏ rồi phân phối chúng trên nhiều tài nguyên lưu trữ.

~~~text
             Application
                  |
             Shard Router
              /   |    \
             v    v     v
          Shard A Shard B Shard C
           L001    L002    L003
           L004    L005    L006
~~~

Nhưng câu hỏi khó không chỉ là “chia thành ba nhóm” mà là:

> Khi nhận một truy vấn có khóa K, hệ thống làm sao biết K thuộc shard nào, và cách chọn nơi lưu ảnh hưởng đến truy vấn, tải, khả năng mở rộng và tính đúng đắn ra sao?

Bài học này tập trung vào ba mô hình định tuyến thường gặp trong NoSQL:

1. **Phân mảnh theo băm (hash-based sharding):** tính một giá trị băm từ shard key rồi ánh xạ vào shard.
2. **Phân mảnh theo khoảng giá trị (range-based sharding):** chia miền khóa có thứ tự thành những khoảng được quản lý.
3. **Phân mảnh theo danh mục định tuyến (directory/lookup-based sharding):** dùng một bảng hoặc dịch vụ metadata để tra khóa/nhóm khóa đang thuộc shard nào.

Chúng có thể được dùng riêng hoặc kết hợp. Ví dụ hệ dùng **băm để chọn bucket logic**, sau đó dùng **directory để ánh xạ bucket sang node vật lý**; hoặc dùng **range chunks** nhưng có **metadata directory** xác định chunk đang nằm ở đâu.

Đây là bài thuộc chương **Phân mảnh và định tuyến** của module **Database No SQL**. Sau bài, bạn sẽ biết lựa chọn và đánh giá mô hình phân mảnh từ **access patterns** thay vì chỉ nghĩ rằng tăng số shard sẽ tự cải thiện mọi truy vấn.

## 2. Các khái niệm nền tảng: partition, shard, replica và routing

### 2.1. Partition và shard

Trong các tài liệu, partition/shard đôi khi được sử dụng gần nghĩa, nhưng chúng có thể chỉ các tầng khác nhau:

- **Logical partition:** tập dữ liệu chia theo partition key, ví dụ tất cả sự kiện của một học viên trong một ngày.
- **Shard:** đơn vị dữ liệu được phân phối và quản lý trên các node/tài nguyên; có thể chứa nhiều logical partition.
- **Physical partition/tablet/chunk:** đơn vị mà storage engine thực sự phân bổ hoặc di chuyển; tên gọi tùy hệ.

Không nên mặc định “một partition key tương ứng đúng một máy” hoặc “mỗi shard chính là một container”. Một shard có thể có nhiều replica và một node có thể lưu nhiều shard/tablet.

### 2.2. Shard key

**Shard key** là field hoặc bộ field quyết định một bản ghi thuộc phạm vi phân mảnh nào.

Ví dụ:

~~~json
{
  "tenantId": "T17",
  "learnerId": "L001",
  "courseId": "C101",
  "progressPercent": 80
}
~~~

Các lựa chọn:

- Shard theo tenantId.
- Shard theo learnerId.
- Shard theo (tenantId, learnerId).
- Shard theo khóa nội bộ được hệ thống tạo.

Mỗi lựa chọn định tuyến khác nhau và làm một số truy vấn dễ hoặc khó hơn.

### 2.3. Partition key khác clustering key

Trong cơ sở dữ liệu wide-column như Cassandra, **partition key** thường quyết định vị trí partition qua hashing/token. **Clustering columns** quyết định thứ tự các hàng bên trong partition.

Ví dụ:

~~~sql
PRIMARY KEY ((tenant_id, learner_id), occurred_at, event_id)
~~~

Ở đây:

- (tenant_id, learner_id) là partition key.
- occurred_at và event_id là clustering columns.
- Khoảng occurred_at được truy vấn **trong một partition đã định vị**, không đồng nghĩa sharding toàn cụm theo occurred_at.

### 2.4. Replication khác sharding

**Sharding** chia dữ liệu khác nhau sang các nhóm; **replication** tạo nhiều bản sao cho cùng dữ liệu.

~~~text
Sharding:
  Shard A giữ khóa 1..100.
  Shard B giữ khóa 101..200.

Replication:
  Shard A có Replica A1, A2, A3.
  Shard B có Replica B1, B2, B3.
~~~

Một hệ có thể dùng cả hai. Tăng replication factor từ 1 lên 3 không tự nhân ba không gian khóa khả dụng, vì mỗi bản sao giữ cùng dữ liệu logic.

### 2.5. Routing

**Routing** là quá trình quyết định thao tác cần gửi tới đâu.

~~~text
Request GET progress(tenant=T17, learner=L001)
    |
    v
Extract routing key (T17,L001)
    |
    v
Find logical partition/bucket
    |
    v
Resolve current shard placement
    |
    v
Contact replica/leader/coordinator phù hợp
~~~

Đường đi thực còn phụ thuộc consistency level, leader placement, failover và cơ chế cân bằng tải.

## 3. Trước khi chọn thuật toán: viết ma trận truy vấn

Giả sử hệ quản lý tiến độ học tập cần:

| Truy vấn | Tần suất | Điều kiện | Đặc điểm |
|---|---:|---|---|
Lấy tiến độ của một học viên | Rất cao | tenantId + learnerId | Point lookup |
Lấy các bài học của một học viên | Cao | tenantId + learnerId | Range/collection trong người học |
Lấy top học viên của một khóa | Trung bình | tenantId + courseId | Nhiều learnerIds |
Thống kê theo ngày | Cao | tenantId + date | Khoảng thời gian |
Tìm học viên theo email | Trung bình | tenantId + email | Secondary access path |
Xuất mọi dữ liệu của một tenant | Thấp nhưng nặng | tenantId | Large scan |

Nếu sharding theo (tenantId, learnerId), hai truy vấn đầu có thể được định tuyến gọn; thống kê theo course/date có thể phải fan-out hoặc dùng read model/index được thiết kế riêng.

Nếu sharding theo tenantId, truy vấn một tenant dễ gom lại nhưng tenant lớn có thể quá nóng hoặc không thể chia nhỏ nếu không thay mô hình.

Nếu sharding theo date, thống kê theo ngày có thể thuận tiện, nhưng mọi ghi mới vào cùng ngày có nguy cơ dồn vào một vùng khóa.

**Không có shard key tốt cho mọi access pattern.** Thiết kế phải chọn workload quan trọng, dự đoán tăng trưởng và các invariant nghiệp vụ.

### 3.1. Những câu hỏi cần trả lời

1. Query có luôn cung cấp shard key không?
2. Query point lookup, range scan hay aggregate?
3. Tải theo key có đồng đều không?
4. Có một tenant, người dùng hay ngày đặc biệt nóng không?
5. Dữ liệu của một owner có thể vượt dung lượng một shard không?
6. Có cần transaction hoặc uniqueness xuyên các mảnh?
7. Có yêu cầu data residency theo quốc gia/Region?
8. Hệ cần tăng số shard mà không sửa code/repartition toàn bộ không?

## 4. Phân mảnh theo băm: ý tưởng

Một **hàm băm ổn định** biến shard key thành giá trị hash:

\[
h = H(\text{shardKey}).
\]

Router ánh xạ h vào một đơn vị phân mảnh:

\[
\text{bucket} = h \bmod N
\]

trong mô hình đơn giản với N bucket.

Ví dụ giả định có bốn shard:

~~~text
H(T17,L001) mod 4 = 0 -> Shard 0
H(T17,L002) mod 4 = 3 -> Shard 3
H(T17,L003) mod 4 = 1 -> Shard 1
H(T17,L004) mod 4 = 0 -> Shard 0
~~~

Các giá trị chỉ để minh họa. Hàm hash thực cần được chọn ổn định, có định dạng encoding rõ, và kết quả trên mọi router phải giống nhau.

### 4.1. Lợi ích

- Phân tán các shard key khác nhau khá đồng đều nếu hash và phân bố keys phù hợp.
- Tránh tập trung các khóa tuần tự vào một shard duy nhất chỉ vì chúng gần nhau về giá trị.
- Với point lookup có đủ shard key, router tính nơi đến nhanh.
- Thuận tiện khi khóa đầu vào có nhiều giá trị phân biệt.

### 4.2. Giới hạn

- Phá vỡ tính liên tục của khóa gốc: range query trên khóa ban đầu có thể phải xem nhiều shard.
- Một **khóa đơn lẻ quá nóng** vẫn có thể làm quá tải shard nhận nó; hash không chia một key thành nhiều nơi.
- Nếu thay số shard trực tiếp từ N thành N+1 trong modulo, rất nhiều khóa có thể bị ánh xạ sang chỗ mới.
- Hash theo tenantId có thể cho phân phối tốt về **số tenant** nhưng không tốt về **lưu lượng** nếu một tenant chiếm phần lớn traffic.

### 4.3. Ví dụ lưu theo userId tuần tự

Khóa:

~~~text
USER#000001
USER#000002
USER#000003
USER#000004
...
~~~

Nếu dùng range theo userId tăng dần, các user mới có thể rơi vào khoảng cuối. Nếu hash userId, các userId mới thường phân tán trên nhiều bucket, giúp giảm hotspot do tăng tuần tự.

Tuy nhiên, nếu mọi request liên tục cập nhật đúng USER#000001, hashing vẫn gửi chúng về **một nơi**.

## 5. Hashing không đồng nghĩa encryption hoặc tính ngẫu nhiên tuyệt đối

### 5.1. Hash không che được khóa nhạy cảm

Hash shard key được dùng để phân phối vị trí. Nó không phải cơ chế encryption hay authorization.

Một email có thể bị đoán và băm lại; không nên cho rằng băm email giúp bảo vệ thông tin cá nhân. Mã định tuyến và log cũng cần xử lý PII đúng chính sách.

### 5.2. Cùng đầu vào phải có cùng đầu ra

Các router phải thống nhất:

- Kiểu dữ liệu: số 7 khác chuỗi "7" không?
- Unicode normalization.
- Quy tắc chữ hoa/chữ thường.
- Thứ tự field của composite key.
- Byte encoding và delimiter.
- Hash algorithm/version.

Nếu một router dùng UTF-8 nhưng router khác chuyển đổi chuỗi khác cách, cùng key có thể bị route sang hai shard khác nhau.

### 5.3. Không tự đổi thuật toán hash khi đã có dữ liệu

Đổi từ H1 sang H2 mà không migrate sẽ khiến:

~~~text
Old router: K -> shard A.
New router: K -> shard B.
~~~

Nếu shard B chưa có dữ liệu, request báo thiếu item; nếu ghi mới vào B, cùng business key có thể tồn tại ở hai nơi.

Việc đổi hash cần một kế hoạch migration với version/routing metadata.

### 5.4. Dùng hash ổn định ở Java

Đoạn mã sau minh họa hash SHA-256 để ánh xạ khóa thành một **bucket logic**, không phải thư viện phân mảnh production:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public final class HashBucketRouter {
    private final int logicalBucketCount;

    public HashBucketRouter(int logicalBucketCount) {
        if (logicalBucketCount <= 0) {
            throw new IllegalArgumentException("bucket count must be positive");
        }
        this.logicalBucketCount = logicalBucketCount;
    }

    public int bucketFor(String canonicalKey) {
        try {
            byte[] digest = MessageDigest
                    .getInstance("SHA-256")
                    .digest(canonicalKey.getBytes(StandardCharsets.UTF_8));

            // Chỉ dùng bốn byte đầu cho ví dụ; cần giữ
            // cùng cách encoding và hash ở mọi router.
            long unsigned = ((long) (digest[0] & 0xff) << 24)
                    | ((long) (digest[1] & 0xff) << 16)
                    | ((long) (digest[2] & 0xff) << 8)
                    | (long) (digest[3] & 0xff);

            return (int) (unsigned % logicalBucketCount);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
~~~

**Giới hạn của ví dụ:**

- Cách tính đang dùng modulo với số bucket **cố định**.
- Đây là mapping khóa→bucket, **chưa có** bucket→node và failover.
- SHA-256 không bắt buộc cho sharding; nhiều engine chọn hash nhanh hơn phù hợp nhu cầu.
- Không tự thay thế partitioner/routing do database đã quản lý sẵn.

## 6. Vấn đề khi thay số shard theo phép modulo

Giả sử:

\[
\text{shard}(K)=H(K)\bmod4.
\]

Sau đó tăng từ 4 lên 5:

\[
\text{shard}'(K)=H(K)\bmod5.
\]

Ngay cả với một khóa không đổi, giá trị \(H(K)\bmod4\) và \(H(K)\bmod5\) thường khác nhau.

Ví dụ:

| Hash giả định | Modulo 4 | Modulo 5 |
|---:|---:|---:|
| 12 | 0 | 2 |
| 17 | 1 | 2 |
| 26 | 2 | 1 |
| 39 | 3 | 4 |
| 44 | 0 | 4 |

Phần lớn key có thể cần chuyển shard. Nếu router mới hoạt động trước khi dữ liệu được di chuyển, ứng dụng có thể đọc thiếu hoặc tạo bản sao dữ liệu sai chỗ.

### 6.1. Không nhất thiết phải chọn physical shard trực tiếp

Một thiết kế tốt hơn trong một số hệ:

~~~text
hash(key) -> logical bucket (0..1023)
logical bucket -> physical shard (lookup table)
~~~

Số bucket logic được thiết kế ổn định, còn bảng gán bucket→shard có thể thay đổi:

~~~text
Bucket 000..299 -> Shard A
Bucket 300..699 -> Shard B
Bucket 700..1023 -> Shard C
~~~

Khi thêm Shard D, di chuyển **một số bucket** từ A/B/C sang D thay vì tính lại hash cho mọi key.

### 6.2. Lưu ý bucket quá ít

Nếu chỉ có bốn bucket logic, khó cân bằng chính xác lên 20 physical shards. Nếu có đủ nhiều buckets/tablets, việc phân bổ mềm dẻo hơn nhưng tăng metadata và độ phức tạp.

### 6.3. Bucket không tự sửa hot key

Nếu một bucket chứa key K cực nóng, chuyển cả bucket sang node khác chỉ **di chuyển hotspot**, chưa chia nhỏ workload của K.

Cần xem xét sharding bổ sung, write aggregation, key salting với điều kiện nghiệp vụ phù hợp, hoặc thay access pattern.

## 7. Consistent hashing và virtual nodes

### 7.1. Ý tưởng vòng hash

**Consistent hashing** đặt keys và nodes/buckets lên một không gian hash dạng vòng:

~~~text
     [Node A] ---- [key x] ---- [Node B]
         \                        /
          [key z] -- [Node C] -- [key y]
~~~

Trong mô hình phổ biến, một key được gán đến node đầu tiên theo một chiều đã định trên vòng, hoặc đến một tập replica theo quy tắc của hệ.

Khi thêm node, lý tưởng chỉ một phần keys ở các đoạn liên quan phải đổi owner, thay vì remap hầu hết keys như modulo N→N+1.

### 7.2. Không phải không di chuyển dữ liệu

Consistent hashing giảm phạm vi thay đổi mapping trong một số cấu hình. Dữ liệu trong vùng đổi owner **vẫn cần được chuyển hoặc stream**; network I/O, CPU, checksum, replication và cleanup vẫn có chi phí.

### 7.3. Virtual nodes

Một physical node có thể sở hữu nhiều **virtual nodes/tokens** phân tán trên vòng.

~~~text
Physical A owns tokens: A1, A2, A3...
Physical B owns tokens: B1, B2, B3...
~~~

Lợi ích có thể gồm:

- Phân phối miền token đều hơn.
- Rebalance linh hoạt khi thêm/bớt node.
- Phân tán tải theo nhiều đoạn hash.

Đổi lại có chi phí quản lý metadata, streaming và topology tùy implementation. Không phải cứ tăng số vnode vô hạn là tốt.

### 7.4. Rendezvous hashing

Một kỹ thuật khác là **rendezvous/highest-random-weight hashing**:

~~~text
For each candidate shard S:
    score = H(key, S)
Choose shard with highest score
~~~

Với hash ổn định, khi thêm hoặc xóa shard, nhiều key vẫn giữ owner cũ. Có thể dùng weighted rendezvous nếu cần xử lý các shard có capacity khác nhau, nhưng thuật toán tính score/weight phải được định nghĩa thống nhất.

### 7.5. Không nhầm hashing logic với sản phẩm cụ thể

Cassandra dùng token/partitioner của mình; Redis Cluster dùng hash slots; DynamoDB quản lý phân phối nội bộ; MongoDB có hashed shard keys với chunk metadata. Không nên áp dụng mã Java tự viết để thay thế router nội bộ của những hệ ấy.

## 8. Phân mảnh theo khoảng giá trị (range-based sharding)

Thay vì băm, router giữ các **khoảng khóa đã sắp thứ tự**:

~~~text
Shard A: customerId [000000, 099999]
Shard B: customerId [100000, 199999]
Shard C: customerId [200000, 299999]
~~~

Một customerId 150123 thuộc Shard B.

### 8.1. Cách định tuyến

Với những khoảng dạng nửa mở:

\[
[L,U)
\]

router chọn khoảng thỏa:

\[
L\le K<U.
\]

Ví dụ:

~~~text
Ranges:
  [-∞, 1000) -> A
  [1000, 5000) -> B
  [5000, +∞) -> C

K=3750 -> Shard B.
~~~

Quy ước nửa mở giúp tránh chồng lắp biên nếu các khoảng được duy trì nhất quán.

### 8.2. Lợi ích chính: locality của truy vấn theo khoảng

Ví dụ muốn lấy tất cả order theo orderId từ 1200 đến 1450; nếu cả dải nằm trong Shard B, hệ có thể đọc **một shard**.

Với truy vấn [900,1500), router chỉ cần chạm những shard có khoảng giao với query, thay vì tất cả shard.

### 8.3. Tính có thứ tự giúp quản lý split

Khi Shard B quá lớn, có thể chia:

~~~text
Trước:
  [1000,5000) -> B

Sau:
  [1000,3000) -> B1
  [3000,5000) -> B2
~~~

Nhưng split là một **quy trình di chuyển dữ liệu và đổi metadata**, không chỉ sửa một dòng config.

### 8.4. Hạn chế: write hotspot ở miền tăng tuần tự

Nếu shard theo timestamp hoặc auto-increment ID:

~~~text
2026-11-12 -> Shard A
2026-11-13 -> Shard B
2026-11-14 -> Shard C
~~~

Tất cả sự kiện mới của ngày 14/11 có thể đổ vào C, tạo **hot tail shard**.

Range sharding thuận lợi cho scan lịch sử, nhưng timestamp tăng liên tục có thể rất khó cân bằng tốc độ ghi nếu không có thêm bucket hoặc phân tán.

### 8.5. Không phải range nào cũng đồng đều

Chia theo chữ cái:

~~~text
A-H -> Shard 1
I-P -> Shard 2
Q-Z -> Shard 3
~~~

không đảm bảo ba shard có cùng số tên, byte hoặc lượng traffic. Tần suất tên và workload có thể lệch nặng.

### 8.6. Split theo số lượng byte khác split theo lưu lượng

Một range 100 GB có thể ít request; một range 1 GB có thể nhận 100.000 reads/giây. Chỉ split khi quá dung lượng sẽ bỏ qua hotspot do request rate.

Cần kết hợp size, QPS, CPU, latency và key distribution.

## 9. Vấn đề khoảng mở, biên và thứ tự sắp xếp

### 9.1. Thiết kế ranh giới không chồng lắp

Nếu khai báo:

~~~text
Shard A: 0 <= K <= 1000
Shard B: 1000 <= K <= 2000
~~~

thì K=1000 thuộc cả hai. Nên dùng cùng quy ước biên như [0,1000) và [1000,2000).

### 9.2. Không để khoảng trống

Nếu:

~~~text
Shard A: [0,1000)
Shard B: [1001,2000)
~~~

thì K=1000 không được định tuyến. Metadata phải bảo đảm các khoảng bao phủ toàn miền đã định, không tạo gap, và không có overlap mơ hồ trừ giai đoạn migration có giao thức rõ.

### 9.3. Thứ tự chuỗi và số khác nhau

Theo thứ tự chuỗi:

~~~text
"10" < "2"
~~~

có thể đúng theo lexicographic order, nhưng theo số:

~~~text
10 > 2.
~~~

Nếu shard theo chuỗi orderId:

~~~text
ORDER#1
ORDER#10
ORDER#2
~~~

thứ tự không trùng với thứ tự số học trừ khi chuẩn hóa độ dài, mã hóa key hoặc sử dụng kiểu số phù hợp.

### 9.4. Collation và Unicode

Việc so sánh chuỗi có thể thay đổi theo collation/locale và normalization. Routing layer phải dùng **cùng quy tắc so sánh** với metadata và storage. Không để router Java so sánh một kiểu, database so sánh một kiểu khác.

### 9.5. Composite range keys

Ví dụ:

~~~text
(tenantId, occurredAt, eventId)
~~~

Khoảng được so theo thứ tự thành phần. Một truy vấn chỉ cung cấp occurredAt mà không có tenantId có thể không được pruning tốt.

Thứ tự field của shard key làm thay đổi access path; không thể coi các tổ hợp field là hoán vị tương đương.

## 10. Range theo thời gian và time-bucketing

### 10.1. Phân mảnh theo ngày/tháng

Với telemetry:

~~~text
2026-11-01..2026-11-07 -> Shard A
2026-11-08..2026-11-14 -> Shard B
2026-11-15..2026-11-21 -> Shard C
~~~

Truy vấn dữ liệu một tuần có thể dễ giới hạn phạm vi shard. Việc dọn lịch sử theo retention cũng có thể thuận lợi nếu dữ liệu được gom theo phạm vi thời gian.

### 10.2. Hot current bucket

Nếu 90% event đang ghi có occurredAt=today, mọi ghi cùng ngày có thể đi vào một shard.

Một phương án kết hợp:

~~~text
Shard key = (dayBucket, hash(deviceId) mod 16)
~~~

Trong một ngày có 16 bucket logic, giúp ghi từ nhiều thiết bị trải rộng.

Đổi lại truy vấn toàn ngày cần đọc cả 16 bucket, sau đó merge. Đây là tradeoff **write parallelism vs read fan-out**.

### 10.3. Late-arriving events

Một event xảy ra ngày 01/11 nhưng đến ngày 14/11 cần được route theo quy tắc đã chọn:

- Theo event time: về shard/bucket cũ.
- Theo ingestion time: về shard hiện tại.

Lựa chọn ảnh hưởng query, retention, repair và rebalancing. Không thể thay đổi quy tắc tùy từng producer mà không ghi rõ định nghĩa thời gian.

### 10.4. Timestamp không tự bằng partition key

Trong Cassandra, occurredAt có thể là clustering column trong một partition theo (deviceId, day). Điều đó cho range scan theo thời gian **bên trong partition**, không có nghĩa cơ sở dữ liệu phân phối toàn bộ cluster theo timestamp.

## 11. Directory-based sharding: định tuyến bằng một danh mục

Thay vì suy toàn bộ vị trí từ hash hoặc khoảng, hệ có một **directory/routing catalog**:

~~~text
Routing directory
---------------------------------
tenant T17   -> Shard A
tenant T18   -> Shard C
tenant T19   -> Shard B
tenant T20   -> Shard B
---------------------------------
~~~

Router tra directory để biết shard đang sở hữu dữ liệu.

~~~mermaid
flowchart TD
    C["Client query T17"] --> R["Router"]
    R --> D["Routing directory"]
    D --> R
    R --> S["Shard A"]
~~~

### 11.1. Lợi ích

- Linh hoạt chuyển tenant hoặc key group sang shard khác mà không phải đổi công thức hash.
- Có thể gán tenant lớn tới một shard riêng.
- Hỗ trợ placement theo khu vực pháp lý, Region hoặc tài nguyên chuyên biệt.
- Có thể hỗ trợ routing theo business owner thay vì một hash duy nhất.
- Giúp tách **identity của logical partition** khỏi **vị trí vật lý hiện tại**.

### 11.2. Chi phí

- Directory phải sẵn sàng và nhất quán ở mức cần thiết.
- Router có thể cache route cũ.
- Thay route trong lúc copy dữ liệu cần giao thức chuyển owner an toàn.
- Directory có thể là bottleneck nếu tra trực tiếp với mọi request.
- Phải xử lý failover, metadata version, split-brain và recovery.

### 11.3. Directory entry không nhất thiết là mỗi bản ghi

Đừng mặc định cần một dòng metadata cho mọi user. Có thể tra theo:

- Tenant ID.
- Logical bucket.
- Range chunk ID.
- Partition group.
- Region affinity.

Ví dụ:

~~~text
bucket 001 -> Shard B
bucket 002 -> Shard D
bucket 003 -> Shard A
~~~

Một entry quản lý hàng nghìn bản ghi, giảm kích thước directory.

### 11.4. Directory cũng có thể bổ trợ range sharding

Range sharding thực tế thường cần metadata:

~~~text
[0000,2500) -> Shard A
[2500,5000) -> Shard C
[5000,7500) -> Shard B
[7500,MAX)  -> Shard D
~~~

Ở đây **range** quyết định đơn vị dữ liệu; **directory** lưu vị trí hiện tại của range. Hai khái niệm không loại trừ nhau.

## 12. Routing directory cần chứa thông tin gì?

Một entry đơn giản chỉ có tenantId và shardId là chưa đủ cho những thao tác di chuyển dữ liệu an toàn.

Ví dụ metadata:

~~~json
{
  "routingKey": "TENANT#T17",
  "logicalPartition": "TENANT#T17",
  "destinationShard": "shard-03",
  "placementEpoch": 42,
  "state": "ACTIVE",
  "region": "ap-southeast-1",
  "updatedAt": "2026-11-14T09:00:00Z"
}
~~~

### 12.1. Các trường quan trọng

| Trường | Mục đích |
|---|---|
| routingKey | Khóa định danh logic để tra route |
| destinationShard | Shard hiện giữ quyền xử lý |
| placementEpoch | Phiên bản đơn điệu cho lần chuyển quyền |
| state | ACTIVE, MIGRATING, READ_ONLY hoặc trạng thái tương ứng |
| region | Khu vực triển khai nếu cần data residency |
| updatedAt | Phục vụ quan sát và điều tra |

Placement epoch đặc biệt hữu ích để **ngăn router/worker cũ ghi vào shard đã mất quyền sở hữu**.

### 12.2. Atomic metadata transition

Nếu hai bộ điều phối cùng sửa:

~~~text
Coordinator A: T17 -> Shard B.
Coordinator B: T17 -> Shard C.
~~~

cần một cơ chế CAS/transaction/consensus phù hợp cho metadata để xác định một phiên bản owner có hiệu lực.

Chỉ lưu file JSON trên mỗi application instance rồi để chúng tự cập nhật không cho một quyết định ownership chung.

### 12.3. Cache route

Router có thể cache kết quả directory để không phải đọc metadata với mọi request:

~~~text
Router cache:
  T17 -> Shard A, epoch=41.

Directory:
  T17 -> Shard B, epoch=42.
~~~

Khi cache cũ, router có thể gửi yêu cầu tới A. Shard A cần có hành vi rõ:

- Từ chối write với epoch cũ.
- Trả redirect/stale-route signal.
- Cho client/router refresh directory.
- Chỉ tiếp tục trên shard B với idempotency/consistency phù hợp.

Không nên để A âm thầm nhận ghi sau khi B đã là owner.

### 12.4. TTL không thay thế epoch

Giảm cache TTL xuống 5 giây có thể giảm thời gian route cũ, nhưng không loại race trong chính 5 giây đó. Với write cần một owner, **epoch/fencing** hoặc giao thức cutover vẫn cần thiết.

### 12.5. Directory sẵn sàng đến đâu?

Nếu directory lỗi và router chưa cache:

~~~text
Request mới -> không biết shard đích.
~~~

Một giải pháp phải quyết định:

- Metadata service có replication/quorum không?
- Router có thể dùng snapshot cached route nào?
- Những route cũ có được phép đọc stale?
- Với write không xác minh owner, có phải fail-closed?
- Có bootstrap metadata từ snapshot không?

Directory là thành phần **control plane**; nếu được xây sai, chính nó có thể thành single point of failure.

## 13. Ví dụ Java: router dùng logical bucket và directory

Đây là thiết kế giả lập dành cho ứng dụng tự quản lý sharding, **không áp dụng để thay internal routing của MongoDB/Cassandra/DynamoDB**.

### 13.1. Định nghĩa dữ liệu định tuyến

~~~java
public record RoutingEntry(
        int bucketId,
        String shardId,
        long placementEpoch,
        String state
) {
}
~~~

Một interface:

~~~java
public interface RoutingDirectory {
    RoutingEntry getByBucket(int bucketId);
    RoutingEntry refreshByBucket(int bucketId);
}
~~~

### 13.2. Tính bucket

Giả sử sử dụng HashBucketRouter ở phần trước để cố định 1024 bucket:

~~~java
HashBucketRouter hashRouter = new HashBucketRouter(1024);

int bucketId = hashRouter.bucketFor("TENANT#T17#USER#U101");
RoutingEntry entry = directory.getByBucket(bucketId);

// Gửi request tới entry.shardId()
// với placementEpoch = entry.placementEpoch()
~~~

### 13.3. Các trường hợp cần xử lý

Một router production sẽ cần:

1. Hash/encoding chuẩn hóa thống nhất.
2. Kiểm soát tính hợp lệ của directory entry.
3. Connection pool tới từng shard.
4. Deadline, timeout và retry có giới hạn.
5. Xử lý stale-route và refresh directory.
6. Bảo vệ side effect khi retry qua idempotency key.
7. Theo dõi route version trong trace.
8. Phân biệt lỗi routing với lỗi bản ghi không tồn tại.

### 13.4. Giả mã chuyển route an toàn

~~~text
routeAndWrite(request):
    bucket = stableHash(request.routingKey) mod BUCKET_COUNT
    entry = directory.read(bucket)

    for attempt in boundedAttempts:
        result = sendToShard(
            entry.shardId,
            request,
            entry.placementEpoch
        )

        if result == SUCCESS:
            return SUCCESS

        if result == STALE_ROUTE:
            entry = directory.refresh(bucket)
            continue

        if result == UNKNOWN_OUTCOME:
            reconcileByRequestId()
            continue only if retry is safe

        return result

    return ROUTING_UNAVAILABLE
~~~

**Không nên tự động retry mọi timeout trên shard mới**: shard cũ có thể đã commit trước khi response mất. Cần operationId bền vững hoặc công cụ đối soát để tránh duplicate write.

## 14. Query routing: single-shard, multi-shard và scatter–gather

### 14.1. Targeted query

Query có đủ shard key:

~~~text
GET learner progress
WHERE tenantId=T17 AND learnerId=L001
~~~

Router có thể tính một bucket/shard đích và gửi request trực tiếp.

Lợi ích:

- Ít network hops.
- Ít shard phải xử lý.
- Dễ dự đoán latency.
- Thuận tiện cho một số thao tác conditional/transaction trong phạm vi shard.

### 14.2. Scatter–gather

Query không có shard key:

~~~text
GET all learners
WHERE courseId=C101
ORDER BY progressPercent DESC
LIMIT 20
~~~

Nếu dữ liệu sharded theo learnerId, router có thể phải:

1. Gửi query tới nhiều shard.
2. Mỗi shard chạy phần truy vấn.
3. Thu thập kết quả.
4. Merge và sắp xếp.
5. Trả top 20 toàn hệ.

~~~mermaid
flowchart TD
    Q["Top 20 learners in course C101"] --> R["Query coordinator"]
    R --> A["Shard A: local top 20"]
    R --> B["Shard B: local top 20"]
    R --> C["Shard C: local top 20"]
    A --> M["Merge and global top 20"]
    B --> M
    C --> M
    M --> U["Client"]
~~~

Điều này có thể tốn nhiều CPU, network và RAM ở coordinator.

### 14.3. Query fan-out ảnh hưởng tail latency

Giả sử một request cần phản hồi từ 16 shard. Chỉ cần một shard xử lý chậm để toàn bộ query bị ảnh hưởng nếu kết quả phải đợi tất cả.

Không được đo latency một shard rồi kết luận global query có cùng p99. Fan-out tăng khả năng gặp một nhánh chậm.

### 14.4. Fan-out có thể nhân tải

Một request tới 16 shard có thể tạo **16 subqueries**. 10.000 requests/giây dạng này có thể sinh tới 160.000 subquery invocations/giây trước khi xét cache hoặc tối ưu.

Con số là mô hình minh họa. Chi phí mỗi subquery và concurrency thực tùy engine, nhưng tác động nhân tải là rủi ro cần đo.

### 14.5. Partial results có được phép không?

Nếu một shard timeout, có những hợp đồng khác nhau:

- Fail cả query để tránh trả tập dữ liệu thiếu.
- Trả partial results với nhãn rõ và thông tin shard lỗi.
- Chỉ bỏ phần không thiết yếu của analytics.

**Không âm thầm trả top 20 sai** nếu người dùng được hứa kết quả chính xác toàn bộ.

## 15. Các kiểu truy vấn hưởng lợi hay chịu thiệt từ từng mô hình

| Access pattern | Hash | Range | Directory |
|---|---|---|---|
Point lookup có shard key | Tốt | Tốt | Tốt nếu tra metadata hiệu quả |
Range scan theo shard key gốc | Có thể fan-out | Thường pruning tốt | Tùy cách nhóm/tra |
Khóa tăng tuần tự | Thường tránh hot tail giữa nhiều key | Dễ hot tail | Tùy placement |
Một key rất nóng | Không giải quyết tự động | Không giải quyết tự động | Có thể cách ly owner nhưng chưa tự chia key |
Đổi số physical shards | Cần ring/buckets/resharding | Split/move ranges | Chuyển owner metadata + dữ liệu |
Data residency theo tenant | Cần ràng buộc mapping bổ sung | Có thể dùng range tenant theo thiết kế | Rất linh hoạt |
Tenant lớn cần shard riêng | Tùy hash và virtual buckets | Có thể split nếu key cho phép | Dễ gán riêng, cần support split nếu tenant quá lớn |
Metadata điều phối | Hàm băm/ring map | Range/chunk map | Lookup directory |
Hotspot do thời gian tăng | Có thể giảm nếu hash trên khóa khác nhau | Rủi ro cao | Tùy nhóm/bucket |
Cross-shard sort/aggregate | Có thể nhiều shard | Pruning nếu query nằm trong range | Phụ thuộc catalog và access pattern |

Đây là **định hướng**, không phải benchmark. Nếu một database hỗ trợ index riêng, query planner và automatic resharding, kết quả thực có thể khác. Luôn dựa trên cardinality và phân bố lưu lượng thực tế.

## 16. Hot shard, hot partition và skew

### 16.1. Skew về số lượng dữ liệu

Giả sử:

~~~text
Shard A: 100 GB
Shard B: 100 GB
Shard C: 100 GB
Shard D: 900 GB
~~~

D có dung lượng lớn gấp chín lần các shard khác. Nếu không rebalance, khả năng lưu trữ bị giới hạn bởi D dù các node còn lại trống.

### 16.2. Skew về request rate

~~~text
Shard A: 2.000 QPS
Shard B: 2.100 QPS
Shard C: 1.900 QPS
Shard D: 40.000 QPS
~~~

Dung lượng các shard có thể bằng nhau, nhưng D vẫn quá tải vì request rate.

### 16.3. Skew về write bytes

Nếu một tenant tạo log lớn với mỗi event 1 MB còn tenant khác ghi 1 KB, phân đều số bản ghi không đảm bảo phân đều write bandwidth.

Nên theo dõi:

- QPS theo shard và top keys.
- Bytes read/write.
- CPU và disk utilization.
- Compaction/flush backlog.
- Network throughput.
- p50/p95/p99 latency.
- Hot partition/tenant.

### 16.4. Hash có thể phân đều keys, không phân đều sức nóng

100.000 users phân bố tốt qua bốn shard, nhưng user U777 tạo 70% tất cả writes. Hash(U777) vẫn tới một shard.

Để cải thiện:

- Gom writes qua aggregation layer.
- Shard dữ liệu con theo (userId, bucket) nếu invariant cho phép.
- Dùng queue và batch để điều tiết.
- Cách ly tenant cực nóng sang tài nguyên riêng qua directory.
- Thay data model để tránh một counter/document thành bottleneck.

### 16.5. Salting

Một số hệ thêm salt/bucket vào shard key:

~~~text
Before: TENANT#T17
After:  TENANT#T17#BUCKET#00..15
~~~

Writes có thể trải ra 16 bucket, nhưng reads/aggregates của T17 giờ phải tra nhiều bucket hoặc dùng projection khác.

**Không salting tùy tiện cho dữ liệu yêu cầu unique hoặc transaction trên một key.** Nếu hai request tạo cùng username được đưa ngẫu nhiên vào hai bucket, uniqueness có thể bị phá.

## 17. Multi-tenant sharding và data residency

### 17.1. Shard theo tenant

~~~text
Tenant T17 -> Shard A.
Tenant T18 -> Shard B.
Tenant T19 -> Shard B.
~~~

Ưu điểm:

- Dễ giới hạn phạm vi query theo tenant.
- Dễ quản lý retention/migration theo tenant.
- Có thể hỗ trợ data residency hoặc tenant isolation.

Nhược điểm:

- Tenant khổng lồ có thể vượt một shard.
- Tải giữa tenant không đồng đều.
- Cần chính sách khi tenant tăng trưởng.

### 17.2. Shard theo (tenantId, userId)

Khóa ghép cho phép dữ liệu một tenant trải qua nhiều shard.

~~~text
(T17,U001) -> shard A
(T17,U002) -> shard C
(T17,U003) -> shard B
~~~

Ưu điểm: phân tán tải giữa users.

Nhược điểm: export mọi dữ liệu tenant có thể fan-out; giao dịch xuyên users trong tenant có thể phức tạp.

### 17.3. Hybrid theo nhóm tenant

Một directory có thể quản lý:

~~~text
SMALL_TENANT_GROUP_1 -> Shard A
SMALL_TENANT_GROUP_2 -> Shard B
LARGE_TENANT_T17    -> Shards C,D,E
~~~

Các tenant nhỏ được đóng gói chung; tenant lớn được phân chia theo khóa phụ.

Thiết kế có thể tối ưu chi phí nhưng cần catalog và quy tắc truy vấn phức tạp hơn.

### 17.4. Data residency

Nếu dữ liệu tenant T17 bắt buộc ở một Region nhất định, một hash global ngẫu nhiên sang mọi Region là không phù hợp.

Một mô hình:

~~~text
tenantId -> allowed Region
       -> logical partition/bucket trong Region
       -> physical shard trong Region
~~~

Routing metadata phải được bảo vệ khỏi lỗi cấp quyền/chuyển vùng. Không được để retry tự gửi dữ liệu sang Region không hợp lệ chỉ vì một node có latency thấp.

### 17.5. Tenant isolation không chỉ nhờ route

Routing theo tenant không thay authorization. Mỗi query vẫn phải kiểm tra tenant identity và quyền truy cập ở boundary phù hợp.

Một client tự gửi header tenantId khác không được phép đọc shard của tenant ấy chỉ vì router biết địa chỉ.

## 18. MongoDB: ranged shard key và hashed shard key

MongoDB cung cấp sharding ở mức database/collection với metadata và thành phần routing do hệ quản lý. Trong những cấu hình phổ biến, metadata chunk/range cho phép router xác định shard liên quan.

### 18.1. Hashed shard key

Ví dụ sử dụng mongosh ở môi trường sharded cluster đã cấu hình phù hợp:

~~~javascript
sh.shardCollection(
  "academy.progress",
  { learnerId: "hashed" }
);
~~~

Đây là ví dụ cơ chế, không bao gồm đầy đủ điều kiện triển khai, quyền, index và cấu hình cluster. Hashed shard key giúp phân tán những giá trị learnerId tuần tự/khác nhau theo miền hash.

**Đánh đổi:** Query theo learnerId được định vị tốt, nhưng query kiểu learnerId nằm giữa hai giá trị gốc có thể không tương ứng một phạm vi hash liền nhau.

### 18.2. Ranged shard key

~~~javascript
sh.shardCollection(
  "academy.orders",
  { tenantId: 1, orderId: 1 }
);
~~~

Điều này mô tả shard key có thứ tự theo các field. Với query có prefix shard key phù hợp, query router có thể pruning phạm vi chunk.

Nếu orderId tăng tuần tự trong cùng tenant và là thành phần quyết định thứ tự ở phần đang ghi, cần đánh giá hot range/chunk.

### 18.3. Không nhầm shard key với một index bất kỳ

Collection có index trên email, courseId hay createdAt **không có nghĩa** dữ liệu được phân phối theo index đó.

Index có thể hỗ trợ query trong shard; để định tuyến tốt vẫn phải xét điều kiện tương ứng shard key hoặc các cơ chế query routing cụ thể.

### 18.4. Unique constraint trong sharded collection

Trong MongoDB, việc enforce unique indexes trên sharded collections có những ràng buộc liên quan shard key/index shape và cấu hình. **Không mặc định** một unique secondary index tùy ý trên email sẽ được bảo vệ toàn cụm khi shard theo learnerId khác.

Nếu invariant là unique (tenantId,emailCanonical), cần kiểm tra khả năng index/thiết kế shard key hoặc dùng một điểm claim đủ mạnh.

### 18.5. Chunk movement và balancer

Khi dữ liệu lệch, hệ có thể di chuyển chunk/range để cân bằng. Nhưng routing metadata phải được cập nhật và request trong lúc migration phải tuân theo cơ chế nội bộ của sản phẩm.

Ứng dụng dùng mongos/driver chuẩn không nên tự thay thế nó bằng hash modulo không tương thích.

### 18.6. Query không có shard key

~~~javascript
db.progress.find({ courseId: "C101" });
~~~

Nếu shard key là learnerId và query không cung cấp điều kiện có thể định tuyến, nó có thể phải scatter–gather. Đây là lý do một index phụ không luôn cứu được chi phí query xuyên shard.

## 19. Cassandra/ScyllaDB: token và partition key

### 19.1. Partition key quyết định token

Trong Cassandra với partitioner phù hợp, partition key được băm thành token rồi ánh xạ tới các token ranges thuộc node/replica.

~~~text
partition key -> token -> token owners -> replicas
~~~

Tên thuật toán thường gặp trong Cassandra là Murmur3Partitioner; token assignment, replication placement và topology do engine quản lý.

### 19.2. Ví dụ thiết kế bảng

~~~sql
CREATE TABLE activity_by_learner_day (
    tenant_id text,
    learner_id text,
    activity_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    PRIMARY KEY (
        (tenant_id, learner_id, activity_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
~~~

Ở đây:

- Partition key là (tenant_id, learner_id, activity_day).
- Các bản ghi của một learner trong một ngày được gom thành một logical partition.
- Clustering columns hỗ trợ truy vấn theo occurred_at trong partition đó.
- Token từ partition key quyết định placement, không phải occurred_at.

### 19.3. Query đúng khóa định tuyến

~~~sql
SELECT occurred_at, event_id, event_type
FROM activity_by_learner_day
WHERE tenant_id = 'T17'
  AND learner_id = 'L001'
  AND activity_day = '2026-11-14'
  AND occurred_at >= '2026-11-14T08:00:00Z';
~~~

Query cung cấp đầy đủ partition key và điều kiện clustering column phù hợp; dữ liệu được giới hạn trong một partition logic theo schema.

### 19.4. Không truy vấn mọi learner chỉ bằng date

Nếu chỉ có:

~~~sql
WHERE activity_day = '2026-11-14'
~~~

thì thiếu phần lớn partition key, không phải một query có thể được phục vụ hiệu quả bằng một token range duy nhất theo thiết kế bảng này.

Có thể cần một query table khác, search/analytics projection hoặc thay access pattern.

### 19.5. Không tạo partition vô hạn

Nếu một learner có hàng triệu event/ngày, logical partition theo ngày vẫn có thể quá lớn.

Có thể chia bucket theo giờ hoặc (day,segment) và fan-out đọc khi cần. Việc chia bucket phải được đánh giá theo kích thước partition, tốc độ ghi, TTL và query.

### 19.6. Replication và vnode

Một token range có thể có nhiều replica; số bản sao không đồng nghĩa số range. Khi rebalance hoặc thêm node, hệ phải stream dữ liệu và xử lý ownership theo protocol riêng.

Không dùng chương trình tự sửa token ownership thay vì công cụ vận hành chính thức.

## 20. DynamoDB: partition key được băm nhưng không phải shard router ứng dụng

### 20.1. DynamoDB quản lý physical partitions

Trong DynamoDB, một bảng có **partition key** và có thể có **sort key**. Dịch vụ sử dụng giá trị partition key và hệ thống quản lý placement nội bộ để phân phối item trên các tài nguyên lưu trữ.

Ứng dụng không được giả định mình có thể tính:

~~~text
hash(PK) mod 8 -> physical DynamoDB node số 3
~~~

rồi truy cập node đó. Đây là một managed service và nội bộ có thể thay đổi partition placement, capacity và topology.

### 20.2. Access pattern theo khóa chính

Ví dụ:

~~~text
PK = TENANT#T17#LEARNER#L001
SK = COURSE#C101
~~~

Một Query theo PK có thể lấy các item liên quan cùng logical partition. Nếu muốn Query theo khoảng SK, có thể dùng sort key condition theo API và kiểu dữ liệu phù hợp.

~~~text
PK = DEVICE#D17#DAY#2026-11-14
SK = EVENT#2026-11-14T09:01:00Z#EVT001
~~~

Đây là cách **thiết kế access path**, không đồng nghĩa physical sharding toàn cluster theo timestamp.

### 20.3. Hot partition key

Nếu mọi request ghi vào:

~~~text
PK = GLOBAL_COUNTER
~~~

thì dù bảng có nhiều physical partitions, một tập truy cập tập trung trên cùng key vẫn có thể gây throttling hoặc giới hạn thông lượng theo cơ chế của dịch vụ.

Một phương án cho counter chấp nhận tổng hợp:

~~~text
PK = GLOBAL_COUNTER#BUCKET#00
PK = GLOBAL_COUNTER#BUCKET#01
...
PK = GLOBAL_COUNTER#BUCKET#15
~~~

Mỗi request ghi vào bucket phù hợp. Đọc tổng phải Query/Get và cộng các bucket; tính nhất quán và giới hạn sai số cần được định nghĩa.

### 20.4. Write sharding có đánh đổi

Với event độc lập, có thể thêm shard suffix vào partition key:

~~~text
PK = EVENT#2026-11-14#B03
~~~

Các bucket có thể giúp phân tán lưu lượng khi có đủ key khác nhau. Nhưng một truy vấn lấy toàn bộ event ngày 14 phải đọc nhiều bucket và merge.

Nếu cần **unique username** theo tenant, đừng phân tán các claim của cùng username sang bucket ngẫu nhiên rồi tin rằng unique vẫn được bảo vệ. Cần một key claim có thẩm quyền và conditional write/transaction.

### 20.5. GSI có cách phân phối riêng

Một GSI là access path riêng với key schema của nó, có thể chịu hotspot và chi phí capacity riêng. Việc bảng cơ sở phân phối tốt không bảo đảm GSI cũng phân phối đều.

Ví dụ GSI partition key:

~~~text
status = "PENDING"
~~~

Nếu hàng triệu item cùng status PENDING, đây là khóa ít phân biệt. Có thể cần chia bucket, đổi key schema hoặc một read model khác.

### 20.6. Adaptive capacity và autoscaling

DynamoDB có các cơ chế quản lý capacity/phân phối nội bộ, nhưng không nên coi chúng là bảo đảm mọi access pattern cực lệch sẽ tự được xử lý không giới hạn.

Thiết kế partition key vẫn cần dựa trên **độ phân biệt, số byte, mức ghi/đọc theo key** và giới hạn API/tài nguyên hiện hành.

## 21. Redis Cluster: hash slots và routing do cluster quản lý

### 21.1. Hash slot

Redis Cluster sử dụng **16.384 hash slots** trong mô hình cluster phổ biến. Một key được ánh xạ đến một hash slot theo quy tắc hashing của Redis, rồi slot thuộc một node.

~~~text
Key -> hash slot [0..16383] -> cluster node
~~~

Khách hàng không nên tự sử dụng SHA-256 modulo số Redis nodes để thay thế quy tắc slot của Redis.

### 21.2. Hash tag

Redis hỗ trợ hash tag qua dấu ngoặc nhọn trong key:

~~~text
user:{T17}:profile
user:{T17}:settings
user:{T17}:preferences
~~~

Phần T17 trong cặp ngoặc có thể khiến các key được ánh xạ tới cùng slot theo quy tắc Redis Cluster. Điều này hữu ích cho một số multi-key commands/scripts cần cùng slot.

**Đánh đổi:** Nếu tất cả dữ liệu của tenant lớn dùng cùng hash tag, có thể tạo hot slot. Không nên gắn cùng tag cho mọi tenant hay mọi item của một hệ chỉ để tiện transaction.

### 21.3. MOVED và ASK

Khi slot được chuyển owner hoặc client gửi request tới node sai, Redis Cluster có cơ chế redirect như **MOVED** và **ASK**.

Một cluster-aware client nên hiểu các response tương ứng, refresh slot map, và tuân thủ quy trình resharding của Redis.

### 21.4. Routing cache cũ

~~~text
Client nghĩ slot 1200 -> Node A.
Cluster đã chuyển slot 1200 -> Node B.
~~~

Nếu client không xử lý redirect, truy cập có thể thất bại. Nếu client xử lý đúng, route được cập nhật mà ứng dụng không phải tự quản lý bảng key→node ở mức business.

### 21.5. Multi-key operations

Trong cluster, các thao tác đa key có thể yêu cầu các key nằm cùng slot theo loại lệnh. Không phải mọi operation giữa hai slot khác nhau đều có thể trở thành một transaction nguyên tử chỉ nhờ gửi qua pipeline.

### 21.6. Hash slots không tự tạo isolation nghiệp vụ

Đặt hai key cùng slot có thể đáp ứng điều kiện định tuyến để chạy một số thao tác nguyên tử trên Redis, nhưng không tự giải quyết durability/replication/failover và không tạo transaction qua một database khác.

## 22. Elasticsearch/OpenSearch: routing tới primary shard

### 22.1. Document routing

Một search engine phân mảnh index thành các primary shards và có thể có replica shards.

Trong Elasticsearch/OpenSearch, document routing thông thường được tính từ document ID hoặc custom routing key, theo thuật toán của engine.

~~~text
_routing key -> primary shard -> primary/replicas
~~~

Đối với các version và cấu hình, số primary shards và quy tắc mapping là đặc tính của index cần quản lý. Không được giả định có thể đổi số primary shards tùy ý mà không có thao tác split/shrink/reindex phù hợp.

### 22.2. Custom routing

Một cách lập kế hoạch:

~~~http
PUT /course-events/_doc/EVT001?routing=T17
Content-Type: application/json

{"tenantId":"T17","courseId":"C101","eventType":"START"}
~~~

Đây là ví dụ minh họa API; khi dùng custom routing, những thao tác GET/UPDATE/DELETE liên quan phải cung cấp routing tương ứng theo semantics của engine.

### 22.3. Search với routing

Nếu query chỉ cần tenant T17, cung cấp routing phù hợp có thể giảm số shard phải tìm kiếm so với tìm mọi shard của index.

Tuy vậy, custom routing theo tenant khổng lồ có thể đưa toàn bộ dữ liệu tenant tới một shard và tạo hotspot. Không nên coi custom routing là giải pháp không có chi phí.

### 22.4. Routing không phải security boundary

Một client biết routing=T17 không đương nhiên được phép đọc dữ liệu tenant T17. Quyền truy cập phải được enforce riêng.

### 22.5. Index rollover và migration

Nếu dữ liệu chuyển giữa index cũ/mới hoặc index alias, một business key có thể tồn tại ở nhiều concrete indices. Đừng lấy uniqueness theo _id trong một index rồi suy thành uniqueness toàn hệ khi có rollover/reindex.

## 23. Bảng so sánh ba chiến lược

| Tiêu chí | Hash-based | Range-based | Directory/lookup-based |
|---|---|---|---|
| Quyết định đơn vị logic | Hash từ shard key | Khoảng khóa có thứ tự | Entry định tuyến |
| Định vị point query | Tính hash + placement | Tìm range | Lookup metadata |
| Range query theo khóa gốc | Thường phải fan-out | Có thể pruning tốt | Tùy cách catalog nhóm dữ liệu |
| Khóa tăng tuần tự | Phân tán tốt giữa nhiều key nếu hash hợp lý | Dễ hot tail | Phụ thuộc chiến lược placement |
| Hot key duy nhất | Không tự chia được | Không tự chia được | Có thể cô lập nhưng cần chia access pattern |
| Thay đổi số physical shards | Ring/virtual buckets giúp giảm remap | Split/move ranges | Reassign owner và migrate |
| Data residency theo tenant | Cần thêm policy | Có thể theo range/tenant | Linh hoạt |
| Điều phối metadata | Hash/ring/token map | Range map | Directory service/table |
| Chi phí điều hành | Hash ổn định, rebalance | Split/merge và hotspot boundary | Metadata availability, epoch, stale routes |
| Tốt cho | Point lookups và phân bố khóa rộng | Range scan, time/order locality | Tenant placement, tùy chỉnh, di chuyển có chủ đích |

**Quan trọng:** Đây là **các nguyên tắc thiết kế**, không phải cam kết hiệu năng của mọi database. Một hệ thực thường kết hợp nhiều kỹ thuật: hash tới logical bucket, range chunks trong index, directory mapping tới physical nodes.

## 24. Resharding: tăng hoặc giảm shard khi dữ liệu đang hoạt động

### 24.1. Resharding là gì?

**Resharding** thay cách phân bổ dữ liệu giữa shards, ví dụ:

~~~text
Trước:
  Bucket 100 -> Shard A.

Sau:
  Bucket 100 -> Shard D.
~~~

Hoặc:

~~~text
Trước:
  Range [1000,5000) -> Shard B.

Sau:
  Range [1000,3000) -> Shard B.
  Range [3000,5000) -> Shard D.
~~~

Nó không chỉ là thay routing table: **dữ liệu, các thay đổi trong lúc copy và quyền nhận write** đều phải được xử lý.

### 24.2. Những nguyên nhân cần reshard

- Một shard gần hết dung lượng.
- CPU/disk throughput lệch.
- Một tenant tăng trưởng nhanh.
- Thay data residency policy.
- Muốn giảm blast radius của một khách hàng lớn.
- Muốn nâng hạ tầng để tăng capacity.
- Một shard bị lỗi cần thay thế/recover.

### 24.3. Dữ liệu tĩnh khác dữ liệu đang được ghi

Copy 100 GB khi không có writes khá đơn giản về mặt mô hình. Copy trong lúc client liên tục ghi tạo race:

~~~text
t1 Copy K=v1 từ A sang B.
t2 Client ghi K=v2 vào A.
t3 B vẫn chỉ có K=v1.
t4 Router đổi sang B.
~~~

Nếu không đồng bộ mutation v2 trước cutover, client đọc B sẽ thấy bản cũ hoặc mất update.

### 24.4. Cần một nguồn thay đổi có thứ tự

Có thể dùng:

- WAL/CDC/change stream.
- Log sequence number hoặc watermark.
- Copy snapshot có điểm mốc.
- Phát lại delta mutations sau snapshot.
- Chặn ghi ngắn hạn khi cutover nếu business cho phép.

Từng cách có hợp đồng riêng, không tự động tương đương transaction xuyên hai shards.

## 25. Quy trình online migration an toàn ở mức khái niệm

Một thiết kế khả dĩ:

~~~mermaid
flowchart TD
    A["Directory: A owns range/bucket"] --> B["Tạo destination B"]
    B --> C["Copy snapshot từ A"]
    C --> D["Replay changes sau watermark"]
    D --> E["Đối soát source và destination"]
    E --> F["Fenced cutover: epoch tăng"]
    F --> G["Router refresh tới B"]
    G --> H["Theo dõi và xử lý stale routes"]
    H --> I["Giữ source cũ trong retention an toàn"]
    I --> J["Cleanup sau xác minh"]
~~~

### 25.1. Giai đoạn 1 — chuẩn bị

- Chọn bucket/range cần chuyển.
- Kiểm tra destination có đủ dung lượng và capacity.
- Chụp metadata, owner epoch hiện tại và các yếu tố backup.
- Xác định đường rollback và thời gian retention.

### 25.2. Giai đoạn 2 — copy snapshot

Copy dữ liệu đến một mốc nhất quán phù hợp:

~~~text
Snapshot watermark = W1000.
~~~

Nếu không có một snapshot nhất quán, cần một protocol thay thế để không bỏ sót mutation trong khi scan.

### 25.3. Giai đoạn 3 — bắt kịp delta

Các mutation sau W1000 phải được áp dụng đúng thứ tự/ngữ nghĩa:

~~~text
W1001 PUT K=v2
W1002 DELETE J
W1003 PUT L=v5
~~~

Không chỉ copy các key hiện tồn tại; **DELETE/tombstone** cũng quan trọng để không hồi sinh bản ghi đã xóa.

### 25.4. Giai đoạn 4 — validation

Có thể đối soát:

- Số lượng bản ghi trong range.
- Last applied change watermark.
- Key/version checksums theo từng phần.
- Những DELETE đã được phản ánh.
- Các ràng buộc unique/ownership.
- Độ trễ source/destination.

### 25.5. Giai đoạn 5 — cutover

Chuyển quyền ghi phải có một điểm quyết định:

~~~text
Before epoch=41: owner A.
After  epoch=42: owner B.
~~~

Shard A không được tiếp tục commit write với epoch 41 sau khi B đã nhận quyền epoch 42 theo hợp đồng mạnh. Có thể sử dụng fencing, lease an toàn, consensus hoặc cơ chế internal của database.

### 25.6. Giai đoạn 6 — giải quyết stale-route

Router cũ gửi tới A:

~~~text
A: STALE_ROUTE owner=B epoch=42.
Router: refresh directory, retry theo operationId.
~~~

Không retry vô hạn hoặc tạo bản ghi ở hai shard nếu timeout khiến kết quả commit trước đó chưa rõ.

### 25.7. Giai đoạn 7 — cleanup

Chỉ xóa dữ liệu ở A khi:

- Cutover đã ổn định.
- Không còn reader/snapshot/rollback dependency cần bản cũ.
- Đường phục hồi được xác minh.
- Các mutation muộn đã được xử lý.

Việc xóa source ngay sau copy có thể khiến rollback trở nên bất khả thi.

### 25.8. Dual write có thể gây lỗi

Một giải pháp ngây thơ:

~~~text
Application PUT tới A.
Application PUT tới B.
~~~

không bảo đảm hai write thành công cùng nhau. Nếu A thành công và B thất bại, hai shard lệch. Nếu retry làm đảo thứ tự mutation, B có thể giữ bản cũ.

**Dual write không phải transaction**; nếu dùng, phải có idempotency, ordering, reconciliation và cutover protocol rõ.

## 26. Route cache, stale metadata và fencing epoch

### 26.1. Race giữa lookup và write

~~~text
t1 Router X đọc directory: K -> A, epoch 41.
t2 Coordinator chuyển K -> B, epoch 42.
t3 Router X gửi write tới A theo epoch 41.
~~~

Nếu A còn nhận write, hệ có thể split ownership.

### 26.2. Fencing

Shard hoặc một lớp có thẩm quyền phải từ chối write với epoch không còn hợp lệ:

~~~text
if request.epoch != currentOwnershipEpoch:
    reject STALE_ROUTE
~~~

Đây là ý tưởng; triển khai production phải bảo vệ việc đọc epoch và commit write theo một thao tác/protocol đúng. Nếu check epoch và write cũng bị race, fencing chỉ là vẻ bề ngoài.

### 26.3. Lease có hạn

Một lease giúp owner giữ quyền trong khoảng thời gian nhất định. Nhưng khi lease hết, worker cũ có thể vẫn đang thực thi.

Muốn an toàn, nguồn nhận ghi cần biết phiên bản chủ sở hữu mới và từ chối yêu cầu cũ. TTL của lock không đủ nếu đích không kiểm tra fencing.

### 26.4. Read trong lúc migration

Có thể:

- Đọc source cho tới cutover, rồi đọc destination.
- Dùng redirect có version.
- Dùng shadow reads đối soát nhưng không trả shadow result trực tiếp.
- Trong một số hệ, đọc từ cả hai và resolve theo version.

Không mặc định “đọc shard nào cũng được” nếu hai bên chưa được hòa giải hoặc snapshot không đồng nhất.

### 26.5. Không báo NOT_FOUND quá sớm

Một router stale hỏi nhầm shard A sau cutover, A không có key và trả 404. Nếu ứng dụng coi 404 là bản ghi chưa tồn tại rồi tạo mới, có thể tạo duplicate.

Phải phân biệt:

- SHARD_NOT_OWNER.
- OBJECT_NOT_FOUND trên đúng owner.
- UNKNOWN_OUTCOME.
- STALE_ROUTE.
- TRANSIENT_UNAVAILABLE.

Mã lỗi định tuyến cần đủ thông tin cho retry an toàn mà không lộ topology nhạy cảm tới client công khai.

## 27. Cross-shard transactions và uniqueness

### 27.1. Một transaction trong một shard dễ hơn

Giả sử một reservation và payment intent đều nằm trên một logical partition phù hợp và engine hỗ trợ atomic updates trong phạm vi đó. Điều này có thể giảm số participant so với transaction trải ba shards.

### 27.2. Nhưng không nên ép mọi quan hệ vào một shard

Nếu cần:

~~~text
Transfer 100 từ Account A ở shard 1
             sang Account B ở shard 9
~~~

và nghiệp vụ yêu cầu atomicity, hệ cần một giao thức transaction phân tán phù hợp hoặc mô hình ledger/workflow được thiết kế để bảo vệ invariant.

Một batch HTTP gồm hai lệnh UPDATE tới hai shards **không tự là một transaction**.

### 27.3. Global unique key

Hai bản ghi:

~~~text
Shard A: user U101, email=an@example.com
Shard B: user U202, email=an@example.com
~~~

Nếu email không thuộc shard key và mỗi shard chỉ kiểm tra unique index cục bộ, cả hai có thể được tạo nếu không có cơ chế unique toàn cluster.

Phương án:

- Chọn shard key có thể cưỡng chế uniqueness phù hợp với engine.
- Dùng claim directory keyed theo (tenantId,emailCanonical) và conditional create.
- Dùng transaction toàn phạm vi nếu được hỗ trợ.
- Dùng một nguồn có thẩm quyền cho quyết định unique.

### 27.4. Quản lý claim trong migration

Nếu claim key chuyển owner từ A sang B, cutover phải ngăn A và B cùng cấp claim cho hai request khác nhau. Fencing epoch và version có vai trò tương tự một kho dữ liệu user: **metadata và business ownership phải di chuyển an toàn**.

### 27.5. Foreign relationships và join

NoSQL thường khuyến khích thiết kế theo access pattern. Nếu cần JOIN learner và course trải nhiều shards, ứng dụng có thể phải fan-out, đưa dữ liệu liên quan cùng partition theo mức hợp lý hoặc tạo read model denormalized.

Không chọn shard key chỉ để tối ưu một join hiếm khi nó tạo hotspot ở đường ghi quan trọng.

## 28. Phân trang và sắp xếp kết quả xuyên shards

### 28.1. Vì sao OFFSET khó mở rộng?

Query:

~~~sql
SELECT *
FROM activities
ORDER BY occurred_at DESC
OFFSET 100000 LIMIT 50;
~~~

Nếu dữ liệu nằm trên nhiều shards, mỗi shard/coordinator có thể phải duyệt lượng lớn dữ liệu trước khi biết 50 dòng cuối. Chi phí tăng khi offset tăng.

### 28.2. Cursor pagination

Một cách là dùng cặp order key ổn định:

~~~text
Cursor = (lastOccurredAt, lastEventId).
~~~

Lần sau yêu cầu các event nhỏ hơn cursor theo thứ tự được định nghĩa.

### 28.3. Tổng sắp thứ tự cần tiebreaker

Chỉ ORDER BY occurred_at nếu hai events cùng timestamp có thể dẫn tới pagination bị trùng/bỏ sót. Nên có thứ tự toàn phần, ví dụ:

~~~text
ORDER BY occurred_at DESC, eventId DESC
~~~

Trên các shard, coordinator cần merge những stream theo cùng comparator.

### 28.4. Cursor không tự là snapshot

Khi người dùng phân trang, dữ liệu có thể được thêm/xóa giữa hai request. Cursor giúp tránh offset scan lớn nhưng không tự cung cấp một **snapshot cố định** của toàn hệ.

Nếu ứng dụng cần danh sách bất biến trong một phiên export, cần snapshot/time boundary/versioning phù hợp.

### 28.5. Cursor đa shard

Một coordinator có thể phải lưu:

~~~text
Cursor:
  shardA.position
  shardB.position
  shardC.position
  sortBoundary
  routingEpoch
~~~

Nếu shard ownership đổi giữa hai trang, cursor cần được dịch/chuyển tiếp hoặc sử dụng một cơ chế snapshot đã định. Không tự xem cursor byte-string là bất biến mãi qua resharding.

## 29. Capacity planning: tính số shard theo dữ liệu và lưu lượng

### 29.1. Không chỉ chia tổng dung lượng

Giả sử một ứng dụng có:

~~~text
Live logical data:       6 TB
Replication factor:      3
Growth:                  150 GB/ngày
Peak write throughput:   50.000 writes/giây
Peak read throughput:   200.000 reads/giây
~~~

Không thể chỉ lấy 6 TB chia 3 shard rồi kết luận mỗi shard 2 TB.

Bạn còn phải xét:

- Bản sao vật lý và index.
- Compression ratio.
- WAL/commit log, SSTable compaction hoặc storage engine overhead.
- Dung lượng tạm trong resharding.
- Phân bố byte và request rate giữa các khóa.
- Dự phòng cho sự cố mất node/AZ.
- Các yêu cầu IO và tail latency của workload.

### 29.2. Mô hình dung lượng minh họa

Giả sử 6 TB live data là dung lượng logic sau chuẩn hóa cách tính, chưa tính replication, và compression/overhead được bỏ qua tạm để minh họa.

Với RF=3:

\[
\text{Replica storage} \approx 6\times3=18\text{ TB}.
\]

Nếu mục tiêu sử dụng trung bình không quá 60%:

\[
\text{Raw capacity needed}
\approx\frac{18}{0,6}=30\text{ TB}.
\]

Số 30 TB là **ước lượng đơn giản để hiểu phép tính**, chưa bao gồm snapshot, index, WAL, temporary resharding headroom, skew và growth. Không được coi là sizing production.

### 29.3. Tốc độ ghi theo shard

Giả sử 50.000 writes/giây được phân đều lên 10 physical shards:

\[
50.000/10=5.000\ \text{writes/giây/shard}.
\]

Nếu một shard nhận 40% lưu lượng vì hot key, nó xử lý:

\[
50.000\times0,4=20.000\ \text{writes/giây}.
\]

Đó là gấp bốn lần mức trung bình dự tính, dù tổng số shards không đổi.

### 29.4. Sizing theo peak, không chỉ average

Ứng dụng có 1.000 writes/giây trung bình nhưng 100.000 writes/giây khi mở bán không thể được sizing chỉ theo mức trung bình nếu peak là business-critical.

Cần hiểu:

- Burst kéo dài bao lâu.
- Buffer/queue có thể hấp thu bao nhiêu.
- Thời gian cần để autoscale hoặc rebalance.
- Có giới hạn per-partition/per-shard không.
- Nếu mất một shard/node, phần còn lại có đủ capacity không.

### 29.5. Shard count có chi phí riêng

Tăng số shards có thể tăng:

- Metadata.
- Connections/file handles.
- Replication traffic.
- Query fan-out.
- Scheduling/compaction overhead.
- Rebalance time.
- Snapshot/monitoring complexity.

Do đó **nhiều shard nhất không phải tốt nhất**. Cần điểm cân bằng giữa kích thước mảnh, khả năng tăng trưởng và chi phí nền.

## 30. Quan sát định tuyến và hiệu quả phân mảnh

### 30.1. Nhóm metric quan trọng

| Metric | Ý nghĩa |
|---|---|
| Per-shard read/write QPS | Phân bố tải giữa shards |
| Bytes read/write per shard | Skew theo kích thước payload |
| Live bytes / storage utilization | Mức gần ngưỡng capacity |
| Hot keys/partitions | Một số key chiếm tài nguyên lớn |
| Query fan-out count | Mỗi query chạm bao nhiêu shard |
| Targeted query ratio | Tỷ lệ query định vị được shard |
| Scatter–gather latency p95/p99 | Chi phí query đa shard |
| Router cache hit/miss | Tải tới directory |
| Directory lookup latency | Bottleneck ở control plane |
| Stale-route/redirect count | Mức metadata không đồng bộ |
| Routing epoch distribution | Router nào còn dùng epoch cũ |
| Rebalance bytes and duration | Chi phí di chuyển dữ liệu |
| Migration lag/watermark | Destination bắt kịp source chưa |
| Dual-owner/fencing rejection | Phát hiện write sai owner |
| Cross-shard transaction abort | Tranh chấp hoặc lỗi phối hợp |
| Replica lag/repair backlog | Hội tụ sau chuyển shard |
| Data residency violations | Rủi ro placement sai Region |

### 30.2. Tỷ lệ targeted queries

Một phép đo hữu ích:

\[
\text{TargetedQueryRatio}
=\frac{\text{queries directed to intended limited shards}}
{\text{total eligible queries}}.
\]

Cần định nghĩa cụ thể thế nào là targeted: một shard duy nhất hay một số shards được prune bởi range. Không đánh đồng một query chạm hai shards có khoảng liên quan với một query scatter tới 200 shards.

### 30.3. Phân phối latency theo fan-out

Một dashboard có thể chia:

~~~text
fanOut=1:      p99 = 15 ms
fanOut=2..4:   p99 = 45 ms
fanOut=5..16:  p99 = 110 ms
fanOut>16:     p99 = 500 ms
~~~

Các số chỉ để minh họa. Nếu nhiều query endpoint chậm nằm ở nhóm fanOut>16, cần xem lại access path hoặc tạo query table/read model.

### 30.4. Không đánh giá bằng số shard cân bằng một mình

Giả sử shard có storage bytes đồng đều, nhưng một shard liên tục có p99 2 giây do một partition khóa nóng. Dashboard chỉ theo dung lượng sẽ bỏ sót sự cố.

Cần đo **bytes, operations, latency, CPU/I/O và access pattern** cùng nhau.

### 30.5. Cardinality metric

Không gắn email/userId thô vào Prometheus labels gây cardinality cao và rò dữ liệu. Có thể lưu top hot key dưới dạng hashed/anonymized identifier ở hệ chẩn đoán có access control, với retention phù hợp.

## 31. Cách chọn chiến lược cho ba workload

### 31.1. Workload A — hồ sơ học viên

~~~text
100 triệu learners.
90% GET theo learnerId.
8% UPDATE progress theo learnerId.
2% analytics theo course/date.
~~~

Một lựa chọn hợp lý là **hash theo learnerId hoặc (tenantId,learnerId)**, giúp point lookup định vị và phân tán khóa tăng trưởng.

Đối với analytics theo course/date, nên cân nhắc projection/query table thay vì buộc mọi query quét tất cả shards của hồ sơ gốc.

Nếu tenant lớn cần data residency, có thể chọn Region theo tenant trước, rồi hash theo learnerId trong Region đó.

### 31.2. Workload B — telemetry theo thời gian

~~~text
500.000 events/giây.
Query thường theo deviceId và time range 1 ngày.
Retention 30 ngày.
~~~

Shard key đơn theo timestamp có nguy cơ hot tail. Một lựa chọn là **hash theo deviceId/bucket**, kết hợp time-bucket/clustering theo ngày trong partition để hỗ trợ query.

Truy vấn “toàn bộ mọi thiết bị trong một giờ” có thể cần analytics store/projection riêng vì đó là access pattern khác.

### 31.3. Workload C — SaaS có tenant lớn nhỏ không đều

~~~text
20.000 tenants nhỏ.
10 tenants rất lớn.
Một số tenant yêu cầu Region riêng.
~~~

Một **directory-based placement** có thể hữu ích:

- Đưa các tenant nhỏ vào shared shard groups.
- Cách ly tenant cực lớn.
- Ánh xạ tenant vào Region được phép.
- Dùng bucket nội bộ cho tenant quá lớn.

Cần theo dõi directory availability, epoch và migration vì đây là thành phần then chốt cho tính đúng đắn.

### 31.4. Khuyến nghị không phải lựa chọn loại trừ

Một kiến trúc hybrid hoàn toàn hợp lệ:

~~~text
tenantId -> Region (directory)
tenantId + userId -> logical bucket (hash)
bucket -> physical shard (directory)
events within partition -> sorted by occurredAt
~~~

Mỗi lớp giải quyết một vấn đề:

1. Residency.
2. Load distribution.
3. Rebalance.
4. Local range scans.

Đánh đổi là độ phức tạp và nhu cầu metadata/observability.

## 32. Các lỗi thiết kế thường gặp

| Lỗi thiết kế | Hệ quả | Cách suy nghĩ đúng |
|---|---|---|
| Chọn shard key theo ID tăng dần trong range mà không đo peak | Hot tail shard | Hash hoặc thêm bucket hợp lý |
| Hash theo tenantId khi một tenant chiếm 80% writes | Một shard quá tải | Hybrid tenant + sub-bucket hoặc cô lập tenant |
| Hash trực tiếp mod số physical shards rồi thêm node | Phải remap phần lớn keys | Virtual buckets/ring và migration |
| Mỗi request đọc directory từ một node đơn | Routing bottleneck/SPOF | Directory HA, cache + epoch |
| Cache route mãi không refresh | Writes tới owner cũ | Stale-route handling và fencing |
| Đổi route trước khi copy delta xong | Mất update/read stale | Snapshot + replay + fenced cutover |
| Dual write A/B không có ordering/idempotency | Hai shard lệch | Giao thức migration có checkpoint |
| Coi router stale 404 là đối tượng chưa tồn tại | Tạo duplicate | Phân biệt NOT_OWNER với NOT_FOUND |
| Dùng shard key ngẫu nhiên cho mọi truy vấn range | Scatter–gather liên tục | Query matrix/read model |
| Range theo string nhưng xử lý như số | Chọn sai biên | Thống nhất key encoding/comparator |
| Range overlap/gap không kiểm soát | Một key có hai owner hoặc không owner | Metadata ranges nửa mở/atomic update |
| Nghĩ replication factor=3 là ba lần số shard logic | Nhầm capacity và placement | Tách shard và replicas |
| Coi hash bảo vệ email khỏi bị lộ | Rủi ro privacy | Encryption/authorization riêng |
| Dùng GSI eventual như unique constraint | Hai claimant có thể cùng thắng | Conditional claim/source of truth |
| Dùng Redis hash tag chung toàn hệ | Hot slot | Đồng vị trí có chọn lọc |
| Query không có shard key nhưng tin có local index là đủ | Fan-out nhiều node | Phân biệt local index với routing |
| Tăng số shards vô hạn để giảm latency | Metadata, fan-out và chi phí nền tăng | Capacity planning theo workload |
| Chỉ cân bằng theo byte, bỏ qua QPS | Hot shard vẫn nghẽn | Quan sát QPS/bytes/p99 |
| Chuyển tenant sang Region khác để giảm latency, quên residency | Sai chính sách dữ liệu | Directory placement policy |
| Coi một shard tương đương một máy | Sai kiến trúc | Phân biệt logical shard, physical units, replicas |
| Tự tính physical shard của managed database | Định tuyến sai hoặc không hỗ trợ | Dùng SDK/driver/router chính thức |
| Xóa source ngay sau cutover | Không thể rollback/repair | Retention + reconciliation |
| Nghĩ eventual migration tự bảo vệ uniqueness | Split ownership | Epoch/fencing/transaction |

## 33. Bài tập 1 — xác định shard key

Một nền tảng học tập có bảng:

~~~text
Progress(
    tenantId,
    learnerId,
    courseId,
    lessonId,
    progressPercent,
    updatedAt
)
~~~

Workload:

- 75% lấy tất cả tiến độ của learnerId.
- 15% cập nhật một lesson của learnerId.
- 8% thống kê theo courseId.
- 2% export toàn bộ tenant.

Yêu cầu:

1. Đề xuất hash shard key.
2. Giải thích các truy vấn nào là targeted.
3. Các truy vấn nào có nguy cơ scatter–gather?
4. Nếu một tenant chiếm 70% traffic, shard theo tenantId đơn thuần có tốt không?
5. Đề xuất read model cho thống kê course.

## 34. Bài tập 2 — modulo và tăng số shard

Router cũ:

\[
\text{shard}(K)=H(K)\bmod4.
\]

Router mới:

\[
\text{shard}'(K)=H(K)\bmod5.
\]

Cho hash của sáu keys:

~~~text
K1=12
K2=17
K3=26
K4=39
K5=44
K6=55
~~~

Hãy:

1. Tính shard cũ/mới.
2. Đếm bao nhiêu key đổi shard.
3. Giải thích vì sao bật router mới trước khi migrate gây lỗi.
4. Đề xuất logical buckets hoặc consistent hashing để giảm phạm vi di chuyển.

## 35. Bài tập 3 — range sharding

Directory:

~~~text
[0, 1000)     -> A
[1000, 5000)  -> B
[5000, 9000)  -> C
[9000, +∞)    -> D
~~~

1. K=1000 thuộc shard nào?
2. K=8999 thuộc shard nào?
3. Query range [800,1400) cần chạm những shard nào?
4. Query [5200,8800) cần chạm shard nào?
5. Nếu B quá lớn, đề xuất split thành hai khoảng không gap/overlap.

## 36. Bài tập 4 — hash vs range trong time-series

Một hệ lưu 10 triệu sensor events mỗi phút với timestamp tăng. Đọc chủ yếu theo (deviceId, time range).

1. Vì sao range sharding toàn cụm theo timestamp có nguy cơ hot tail?
2. Vì sao hash theo deviceId giúp phân phối nhưng không tối ưu query toàn cluster theo giờ?
3. Đề xuất composite partition key và local time ordering.
4. Nếu một thiết bị phát 60% sự kiện, cần làm gì ngoài hash?
5. Nếu thêm bucket theo giờ, hãy giải thích tác động lên range query.

## 37. Bài tập 5 — directory-based placement

Directory:

~~~text
T17 -> Shard A, epoch 41
T18 -> Shard B, epoch 6
~~~

Coordinator muốn chuyển T17 sang Shard C, epoch 42.

1. Directory cần giữ những thông tin gì?
2. Vì sao router có cache epoch 41 vẫn có thể gửi ghi đến A?
3. Làm sao A từ chối stale write?
4. Vì sao TTL route cache không thay thế fencing?
5. Nếu directory không truy cập được, khi nào nên fail-closed?

## 38. Bài tập 6 — online migration

Thời điểm:

~~~text
t1: Copy snapshot K=v1 từ A tới B.
t2: Client PUT K=v2 tới A.
t3: Router đổi K sang B.
~~~

1. Nếu không replay delta, B đang có giá trị nào?
2. Vì sao mô hình này gây lost update?
3. Đề xuất snapshot watermark và CDC replay.
4. Xác định một cutover epoch và điểm chặn ghi tại A.
5. Nếu response của PUT ở t2 bị mất, client retry sang B cần cơ chế gì?

## 39. Bài tập 7 — hot key

Bốn shards có:

~~~text
A: 2.000 writes/s
B: 2.100 writes/s
C: 1.900 writes/s
D: 40.000 writes/s
~~~

1. Average writes/s/shard là bao nhiêu?
2. Vì sao chỉ tăng physical shard count có thể không giảm tải D nếu một key quá nóng?
3. Thiết kế cách đo top keys/partitions.
4. Đề xuất write aggregation hoặc bucket salting phù hợp.
5. Một counter cần chính xác tuyệt đối tại thời điểm ghi có thể gặp vấn đề gì nếu chia ngẫu nhiên?

## 40. Bài tập 8 — Cassandra token và clustering

Cho schema:

~~~sql
CREATE TABLE events_by_device_day (
    device_id text,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, event_day), occurred_at, event_id)
);
~~~

Hãy xác định:

1. Partition key.
2. Clustering columns.
3. Vì sao filter theo device_id và event_day có thể định vị một logical partition?
4. Vì sao chỉ filter event_day không phải một local partition query?
5. Nếu một device ghi 50 triệu events/ngày, thay partition key ra sao?

## 41. Bài tập 9 — DynamoDB và GSI

Bảng Event:

~~~text
PK = DEVICE#D17#DAY#2026-11-14
SK = EVENT#timestamp#eventId
~~~

1. Query theo PK và dải SK có lợi gì?
2. Nếu mọi event đều ghi tới một PK toàn cầu, có rủi ro gì?
3. Đề xuất write sharding nhiều buckets.
4. Việc thêm bucket ảnh hưởng đọc toàn ngày ra sao?
5. Nếu GSI có PK=status=PENDING cho phần lớn item, điểm nóng có thể chuyển sang đâu?

## 42. Bài tập 10 — Redis Cluster

Các keys:

~~~text
user:{T17}:profile
user:{T17}:settings
user:{T18}:profile
~~~

1. Những key nào được thiết kế để vào cùng hash slot?
2. Vì sao điều đó hữu ích cho một số multi-key operations?
3. Nếu T17 cực nóng, việc gom hết vào một slot có thể gây gì?
4. Khi reshard, client phải xử lý MOVED/ASK thế nào?
5. Vì sao Redis slot map khác với một bảng directory theo business tenant?

## 43. Bài tập 11 — scatter–gather và fan-out

Query top 20 learners theo courseId phải chạm 16 shards.

1. Một request tạo tối đa bao nhiêu subqueries nếu mỗi shard nhận một?
2. 10.000 requests/s có thể tạo bao nhiêu subquery invocations/s theo mô hình đơn giản?
3. Vì sao p99 global query có thể tăng nếu chỉ một shard chậm?
4. Nếu một shard timeout, khi nào có thể trả partial results?
5. Đề xuất một read model/query table theo courseId để giảm fan-out.

## 44. Bài tập 12 — cross-shard uniqueness

Hai users U101 và U202 được hash tới hai shards khác nhau nhưng cùng email:

~~~text
U101: T17, an@example.com
U202: T17, an@example.com
~~~

1. Unique index cục bộ trong từng shard có đủ không?
2. Đề xuất business key cho bảng IdentityClaims.
3. Conditional write bảo vệ điều gì?
4. Khi claim chuyển owner từ Shard A sang B, cần fencing như thế nào?
5. Vì sao một query search eventual theo email không thể dùng làm bước xác nhận uniqueness duy nhất?

## 45. Bài tập 13 — capacity planning

Hệ có 6 TB live data, RF=3 và mục tiêu trung bình sử dụng 60% raw capacity, tạm bỏ qua compression/index/snapshot để minh họa.

1. Tính replica storage.
2. Tính raw capacity xấp xỉ.
3. Kể ít nhất năm thành phần phải thêm khi sizing production.
4. Nếu một shard chịu 40% của 50.000 writes/s, nó chịu bao nhiêu writes/s?
5. Vì sao sizing theo average không đủ cho flash sale?

## 46. Bài tập 14 — kiểm thử resharding khi đang ghi

Thiết kế test cho migration một bucket từ A sang B:

- Có 1.000 writes/s tới bucket.
- Có DELETE, UPDATE và INSERT.
- Có client dùng router cache cũ.
- Một số request timeout giữa cutover.
- Một worker nhận event muộn.

Yêu cầu:

1. Xác định snapshot watermark.
2. Thiết kế replay delta.
3. Xác định cutover epoch.
4. Phân loại stale-route/unknown-outcome.
5. Kiểm tra không mất mutation, không duplicate logical object.
6. Kiểm tra tombstone không hồi sinh.
7. Xác định khi nào an toàn cleanup A.

## 47. Bài tập 15 — chọn chiến lược đa tenant

Một nền tảng SaaS có:

~~~text
30.000 tenants nhỏ.
5 tenants lớn chiếm 65% traffic.
Một tenant yêu cầu dữ liệu chỉ nằm ở EU.
80% query là point lookup theo tenantId + userId.
15% query là dashboard theo tenant.
5% query là báo cáo toàn hệ.
~~~

Hãy xây kiến trúc kết hợp hash/range/directory:

1. Tầng chọn Region.
2. Tầng chia bucket logic.
3. Tầng ánh xạ bucket/tenant group tới physical shards.
4. Cách cô lập tenant cực nóng.
5. Read model cho dashboard.
6. Cách quản lý cross-shard report.
7. Cơ chế migration epoch.
8. Các metric theo dõi trong 90 ngày tăng trưởng.

## 48. Tổng kết

**Phân mảnh theo băm, khoảng giá trị hoặc danh mục định tuyến** là ba cách suy nghĩ về việc dữ liệu nằm đâu và query được gửi tới đâu:

1. **Hash-based sharding** phân tán những shard key khác nhau tương đối đồng đều khi hash và phân bố input phù hợp, thích hợp cho point lookup. Nhưng nó không tự giải quyết một hot key và thường làm range query theo khóa gốc fan-out.
2. **Range-based sharding** giữ locality của các giá trị gần nhau, thuận lợi cho range scans và pruning. Nhưng khóa tăng tuần tự có thể tạo hot tail, và range phải được chia/sắp xếp với comparator cùng quy tắc biên nhất quán.
3. **Directory/lookup-based sharding** tách định danh logic khỏi nơi đặt dữ liệu, cho phép di chuyển tenant/bucket có chủ đích và kiểm soát Region. Đổi lại, routing metadata, cache, epoch, HA và migration trở thành phần thiết yếu của tính đúng đắn.

Các ý quan trọng cần nhớ:

- **Shard key không chỉ là một field tiện lấy hash.** Nó là quyết định về access path, locality, tải, giao dịch và khả năng scale.
- **Partition khác replica.** Nhiều bản sao giúp chịu lỗi nhưng không tự chia một hot partition.
- **Một sản phẩm có thể kết hợp các chiến lược.** Hash→bucket, directory→physical shard, clustering/range bên trong một partition là ví dụ phổ biến về nhiều lớp.
- **Không tự viết router vật lý cho managed databases** khi engine đã có token/chunk/slot placement và driver chính thức.
- **Scatter–gather phải được đo.** Một local index tốt không xóa chi phí truy vấn thiếu shard key trên nhiều node.
- **Resharding là migration có trạng thái**, cần snapshot, delta replay, cutover có fencing, xử lý stale routes và reconciliation. Đổi config/dual write đơn giản không đủ.
- **Hotspot là vấn đề lưu lượng, không chỉ byte dữ liệu.** Một key cực nóng có thể làm nghẽn shard dù hàng triệu key khác phân tán hoàn hảo.
- **Global uniqueness và cross-shard transaction** cần cơ chế quyết định riêng; không suy ra từ hash, directory hoặc unique index cục bộ.
- **Security/data residency không tự có từ routing.** Cần authorization, policy và placement được kiểm soát.
- **Chọn theo truy vấn và đo theo thực tế:** request QPS, byte, p99, targeted ratio, fan-out, metadata lag, rebalance backlog và nhu cầu phục hồi.

Câu hỏi thiết kế cuối cùng không phải chỉ là **“Dùng hash, range hay directory?”**, mà là:

> **“Với các truy vấn và invariant quan trọng nhất, làm thế nào mỗi request xác định đúng owner, dữ liệu phân bố được tải, range query có chi phí chấp nhận được, và khi cần chuyển shard thì không mất ghi, không tạo hai chủ sở hữu và không khiến router dùng metadata cũ phục vụ sai?”**



