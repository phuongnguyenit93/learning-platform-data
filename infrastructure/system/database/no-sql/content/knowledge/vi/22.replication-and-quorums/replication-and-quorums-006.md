# Quorum đọc/ghi, số bản sao tham gia và khả năng chịu lỗi

Trong một hệ NoSQL phân tán, dữ liệu của một khóa có thể nằm trên nhiều node. Khi một client ghi dữ liệu, database có thể đợi một hoặc nhiều replica xác nhận. Khi client đọc, database có thể tham khảo một hoặc nhiều replica để trả kết quả. **Số bản sao cần tham gia và cách chúng phối hợp** ảnh hưởng trực tiếp đến độ trễ, tính nhất quán và khả năng chịu lỗi.

Giả sử một sản phẩm có số lượng tồn kho là 10 trên ba replica. Một request cập nhật thành 9 đã được hai replica xác nhận, nhưng replica thứ ba vẫn giữ 10. Nếu GET chỉ hỏi replica cũ, ứng dụng có thể hiển thị tồn kho sai. Nếu GET dùng một quorum giao với tập đã nhận write, nó có cơ sở để phát hiện trạng thái mới hơn — **với điều kiện giao thức đọc thật sự xử lý đúng các phiên bản**.

Bài học nằm trong chương **Sao chép và quorum** của **Database No SQL**. Chúng ta sẽ tìm hiểu N/R/W, điều kiện giao nhau, tính toán số node lỗi có thể chịu, quorum đa số và những giới hạn thực tế: network partition, delayed replica, leader election, conflict resolution, sloppy quorum, durability và multi-region.

**Thông điệp cốt lõi:** Quorum không chỉ là “đủ một nửa số máy”. Nó là một **ngưỡng xác nhận/tham gia trong giao thức cụ thể**. Quorum giao nhau về tập hợp là một tính chất toán học hữu ích, nhưng không tự chứng minh mọi lần đọc đều linearizable hoặc mọi giao dịch đều an toàn.

## 1. Vì sao dữ liệu cần nhiều bản sao?

Giữ một bản duy nhất có thể tạo điểm lỗi đơn. Khi node hoặc ổ đĩa hỏng, ứng dụng có thể không đọc/ghi được hoặc mất dữ liệu.

Replication giúp:

- Chịu được một số lỗi node, rack hoặc zone theo topology.
- Tiếp tục phục vụ khi một số replica không phản hồi.
- Mở rộng khả năng đọc trong một số kiến trúc.
- Hỗ trợ failover, backup/rebuild và vận hành phân tán.
- Giảm rủi ro phụ thuộc vào một phần cứng.

~~~mermaid
flowchart TD
    Client["Ứng dụng"] --> Coord["Coordinator"]
    Coord --> A["Replica A"]
    Coord --> B["Replica B"]
    Coord --> C["Replica C"]
~~~

Tuy nhiên, replication có thể bất đồng bộ. Một write được xác nhận ở nơi này nhưng chưa được áp dụng ở nơi khác. Quorum là một cách mô hình hóa **khi nào read/write được coi là đủ điều kiện hoàn thành**.

## 2. N, W và R nghĩa là gì?

| Ký hiệu | Ý nghĩa khái quát |
|---|---|
| `N` | Số bản sao mục tiêu của một key/đơn vị dữ liệu |
| `W` | Số replica cần xác nhận write theo policy |
| `R` | Số replica cần tham gia hợp lệ để read hoàn tất theo policy |

Ví dụ:

~~~text
N = 3
W = 2
R = 2
~~~

Với mô hình ba replica, một write cần hai xác nhận và một read dựa trên hai phản hồi hợp lệ.

Những điều cần làm rõ trước khi áp dụng con số:

- N là replication factor của keyspace hay số voting members?
- W là số ACK đã nhận request, đã ghi log hay đã bền vững trên disk?
- R là số bản sao có trả dữ liệu/digest đủ để hòa giải không?
- Quorum được tính theo toàn cluster, một partition hay một datacenter?
- Node thay thế tạm thời có được đếm không?
- Replica đang unavailable hay chỉ phản hồi chậm?
- Read được thực hiện theo protocol nào khi nhiều bản khác nhau?

Không phải sản phẩm nào cũng cho phép tùy chỉnh trực tiếp R, W, N; nhiều hệ chỉ cung cấp các **consistency levels** định sẵn hoặc quorum phục vụ election/commit.

## 3. Write quorum hoạt động thế nào?

Giả sử `N=3, W=2`:

~~~text
                 Coordinator
                 /    |    \
                v     v     v
              A       B       C
             ACK     ACK     slow
                 |
           Đủ 2 ACK: success
~~~

Một trình tự:

1. Client gửi write `stock=9`.
2. Coordinator chuyển write tới các replica theo giao thức.
3. A xác nhận, B xác nhận.
4. C chưa xác nhận.
5. Theo policy W=2 và khi hai ACK hợp lệ, coordinator có thể trả thành công.

Lợi ích: không nhất thiết phải chờ replica chậm nhất.

Nhưng **ACK không luôn đồng nghĩa durability**. Trong từng engine, ACK có thể liên quan memory, WAL/journal, commit log hoặc durable flush khác nhau. Nếu mục tiêu là chịu mất điện hoặc crash, phải hiểu đúng cơ chế acknowledgment và durability của sản phẩm.

## 4. Read quorum hoạt động thế nào?

Giả sử `N=3, R=2`:

~~~text
              Read coordinator
                  /       \
                 v         v
              Node A     Node C
               v11        v10
                 \       /
                  Reconcile
                      |
                 Read result
~~~

Read có thể cần lấy phiên bản/timestamp hoặc một digest từ đủ replica, rồi trả kết quả theo quy tắc nhất quán của engine.

Điểm quan trọng: **Đợi hai phản hồi rồi lấy phản hồi đến sớm nhất không tự là quorum read an toàn**. Khi hai replica khác nhau, protocol phải biết cách phát hiện, so sánh và quyết định trạng thái đúng, kể cả khi write đồng thời.

Một số sản phẩm dùng read repair, digest, speculative requests hoặc coordinator optimization thay vì trả toàn bộ document từ mọi replica.

## 5. Giao nhau giữa read và write quorum

Trong một tập **N replica cố định**, gọi:

- `Q_W` là tập replica xác nhận write, có ít nhất W thành viên.
- `Q_R` là tập replica mà read dùng làm bằng chứng hợp lệ, có ít nhất R thành viên.

Nếu:

\[
R+W>N
\]

thì mọi cặp tập như vậy **bắt buộc có giao nhau**:

\[
Q_R \cap Q_W \neq \varnothing
\]

### Ví dụ N=3, W=2, R=2

Write quorum:

~~~text
{A, B}
~~~

Những read quorum có thể là:

~~~text
{A, B}
{A, C}
{B, C}
~~~

Mỗi tập read hai node đều chứa ít nhất một node đã ACK write ở {A,B}.

**Trực giác chứng minh:** Nếu hai tập không giao nhau, chúng cần ít nhất R+W vị trí riêng. Khi R+W>N, không đủ N node để chứa cả hai mà không chồng lên nhau.

Điều kiện giao này là **tính chất của các tập**, chưa đủ để chứng minh tất cả read luôn thấy đúng write mới nhất.

## 6. Khi R + W không lớn hơn N

Ví dụ `N=3, W=1, R=1`:

~~~text
Write v11 được A xác nhận
Read chỉ hỏi C
C vẫn còn v10
~~~

Hai tập hoàn toàn có thể không giao:

~~~text
Write set: {A}
Read set:  {C}
~~~

Với `N=4, W=2, R=2`, hai tập cũng có thể tách rời:

~~~text
Write set: {A, B}
Read set:  {C, D}
~~~

Vì `2+2=4`, tức bằng N chứ không vượt N, không có giao nhau bắt buộc.

Do đó điều kiện là **R+W lớn hơn N**, không phải lớn hơn hoặc bằng N.

## 7. Quorum giao nhau có đủ để bảo đảm dữ liệu mới nhất?

**Không tự động.** Tính chất giao nhau chỉ nói có ít nhất một node chung. Để read phản ánh write hợp lệ, còn cần:

- Replica đã ACK phải lưu/áp write theo semantics cần thiết.
- Read phải dùng trạng thái/metadata từ replica chung, không bỏ qua.
- Engine phải nhận diện phiên bản nào được phép thắng.
- Concurrent writes phải có ordering hoặc conflict resolution rõ.
- Write chưa hoàn tất, rollback và retry phải được xử lý đúng.
- Membership, replica placement và leader epoch phải nhất quán.
- Không dùng những node thay thế khiến tập quorum thực tế không còn giao nhau như giả định.

**R+W>N không phải giấy chứng nhận linearizability** cho mọi engine.

Ví dụ last-write-wins theo timestamp có thể bị ảnh hưởng bởi clock skew. Read lấy timestamp lớn nhất từ nhiều replica chưa chắc phản ánh thứ tự thời gian thực mà người dùng hình dung nếu timestamp không có semantics đó.

## 8. Hai write quorum cần giao nhau khi nào?

Khác với giao **read-write**, hai write quorum bất kỳ giao nhau nếu:

\[
2W>N
\]

Tương đương:

\[
W>\frac N2
\]

Với N=3, W=2, hai write quorum luôn giao.

Với N=4, W=2:

~~~text
Write 1: {A, B}
Write 2: {C, D}
~~~

Hai tập có thể tách nhau.

Write-write overlap có thể quan trọng với đồng thuận và cạnh tranh, nhưng **ngay cả khi 2W>N cũng cần protocol về ordering, term/ballot hoặc conflict handling** để bảo đảm một trạng thái cuối phù hợp.

## 9. Tính khả năng chịu lỗi theo mô hình đơn giản

Giả định:

1. Một key có đúng N replica cố định.
2. F replica hỏng hoàn toàn; N-F còn lại khỏe và liên lạc được.
3. Không có hạn chế khác về quorum theo region, leader hoặc placement.
4. Operation thành công nếu nhận đủ W hoặc R phản hồi hợp lệ.

Để ghi:

\[
N-F\ge W
\]

Suy ra số lỗi tối đa mà write còn có thể thành công:

\[
F_W^{\max}=N-W
\]

Để đọc:

\[
N-F\ge R
\]

Suy ra:

\[
F_R^{\max}=N-R
\]

Để **cả đọc lẫn ghi** cùng tiếp tục:

\[
F_{\text{both}}^{\max}=\min(N-W,N-R)
\]

Đây chỉ là mô hình đếm node. Nó **không tự mô tả** network partition, leader failure, quorum theo datacenter, disk durability hoặc một node còn chạy nhưng chậm đến mức timeout.

## 10. Bảng cấu hình N=3

| N | R | W | R+W>N? | Lỗi tối đa cho read | Lỗi tối đa cho write | Lỗi tối đa cả hai |
|---:|---:|---:|---|---:|---:|---:|
| 3 | 1 | 1 | Không | 2 | 2 | 2 |
| 3 | 1 | 2 | Không | 2 | 1 | 1 |
| 3 | 2 | 1 | Không | 1 | 2 | 1 |
| 3 | 2 | 2 | Có | 1 | 1 | 1 |
| 3 | 1 | 3 | Có | 2 | 0 | 0 |
| 3 | 3 | 1 | Có | 0 | 2 | 0 |
| 3 | 2 | 3 | Có | 1 | 0 | 0 |
| 3 | 3 | 2 | Có | 0 | 1 | 0 |
| 3 | 3 | 3 | Có | 0 | 0 | 0 |

Đọc bảng:

- `R=1, W=1` dễ đạt ngưỡng nhưng **không đảm bảo quorum giao nhau**.
- `R=2, W=2` cân bằng khả năng read/write chịu một lỗi theo mô hình.
- `R=1, W=3` có read nhẹ nhưng write không chịu được mất một replica.
- `R=3, W=1` có write nhẹ nhưng read không chịu được mất một replica.
- `R+W=N` không đủ để bảo đảm read quorum và write quorum giao nhau.

Số lỗi “tối đa” ở đây là số node có thể hoàn toàn không tham gia nhưng các node còn lại vẫn reachable, chứ không hứa operation vẫn đạt latency SLO.

## 11. Ba lựa chọn thường được so sánh

### N=3, R=1, W=1

Ưu điểm:

- Có thể giảm tail latency cho từng read/write.
- Có thể hoàn thành operation dù nhiều replica không phản hồi trong mô hình đếm.
- Phù hợp workload chịu được dữ liệu cũ, nếu engine hỗ trợ.

Hạn chế:

- Không có read-write quorum overlap bắt buộc.
- Có thể đọc stale.
- Write chỉ một ACK có thể có durability/failover risk tùy engine.

### N=3, R=2, W=2

Ưu điểm:

- Có read-write overlap trong tập replica cố định.
- Chịu được một replica không phản hồi cho cả read/write.
- Tạo nền cho một số cấu hình consistency cần cân bằng.

Hạn chế:

- Phải đợi đủ hai phản hồi.
- Hai replica mất có thể làm ngưỡng không còn đạt.
- Giao nhau chưa bảo đảm linearizability nếu protocol hoặc topology không đáp ứng thêm.

### N=3, R=1, W=3

Ưu điểm:

- Write đợi cả ba replica xác nhận theo semantics đã chọn.
- Read chỉ cần một replica theo policy.
- Có thể phù hợp workload ưu tiên read nhẹ, ít write và chấp nhận write availability kém.

Hạn chế:

- Một replica không phản hồi có thể ngăn write.
- Write latency phụ thuộc node chậm nhất.
- ACK cả ba không tự đồng nghĩa snapshot/backup hay durable disk của cả ba.

## 12. Quorum N=5

Với năm replica, cấu hình đa số:

~~~text
N = 5
R = 3
W = 3
~~~

Ta có:

\[
R+W=6>5
\]

Và:

\[
F_W^{\max}=5-3=2,\quad
F_R^{\max}=5-3=2
\]

Trong mô hình lý tưởng, mất hai replica vẫn còn ba để đáp ứng read/write. Mất ba, chỉ còn hai, không đủ quorum ba.

Nhưng tăng N không miễn phí:

- Tăng storage và lưu lượng replication.
- Tăng yêu cầu repair/compaction, metadata và monitoring.
- Có thêm điểm chậm/đứt mạng.
- Chi phí cross-zone/cross-region.
- Phức tạp placement và recovery.

Không có lý do mặc định chọn N=7 thay vì N=3 nếu fault model không cần, bởi độ trễ/chi phí có thể tăng đáng kể.

## 13. Majority quorum

Với N thành viên trong cùng một tập bỏ phiếu:

\[
Q_{\text{majority}}=\left\lfloor\frac N2\right\rfloor+1
\]

| N | Số thành viên majority |
|---:|---:|
| 1 | 1 |
| 2 | 2 |
| 3 | 2 |
| 4 | 3 |
| 5 | 3 |
| 6 | 4 |
| 7 | 4 |

Hai majority quorum của **cùng một membership** luôn giao nhau.

Quorum đa số xuất hiện trong nhiều giao thức đồng thuận như Raft/Paxos, nhưng một giao thức đồng thuận còn cần term, log ordering, leader election và commit rules. Đợi majority ACK không tự tạo một consensus protocol nếu thiếu các phần đó.

Cần phân biệt majority của:

- Replica lưu một key.
- Voting members trong replica set.
- Một shard hay partition.
- Một datacenter hoặc region.
- Một configuration membership trước/sau reconfiguration.

Các tập này không phải lúc nào cũng giống nhau.

## 14. Leader-based quorum và leaderless quorum

### Hệ primary–secondary/leader-based

Một leader có thể là nơi sắp thứ tự writes, còn follower áp dụng log. W mô tả ngưỡng xác nhận/commit theo policy. Quorum cũng có thể được dùng cho election.

Nhưng:

- Đọc leader có thể phải xác minh leadership.
- Đọc follower có thể stale.
- Bản ghi được ACK chưa chắc có thể bị rollback hay không nếu policy yếu.
- Commit index/term/epoch có ý nghĩa ngoài số lượng ACK.

### Hệ leaderless/quorum-style

Một coordinator có thể liên hệ nhiều replica, ghi/đọc theo consistency level. Read có thể so sánh phiên bản và repair.

Nhưng:

- Concurrent writes cần conflict resolution.
- Timestamp, version vector hoặc last-write-wins có semantics riêng.
- Node thay thế tạm thời có thể làm overlap suy yếu.
- Read repair và anti-entropy góp phần vào convergence.

Cùng một con số “quorum=2/3” có thể tạo **bảo đảm rất khác nhau** ở hai kiến trúc.

## 15. Consensus không đơn thuần là đếm ACK

**Quorum** là điều kiện về kích thước/tập giao nhau.

**Consensus** là giao thức để các node quyết định thứ tự và trạng thái được chấp nhận khi có trễ/lỗi.

Một giao thức consensus cần thêm:

- Leader/ballot/term hoặc cách quyết định hợp lệ tương đương.
- Thứ tự proposal/log.
- Quy tắc commit và rollback.
- Reconfiguration thành viên an toàn.
- Cách ngăn hai leader mâu thuẫn cùng commit.
- Recovery sau crash.

Vì vậy không thể chỉ tự viết một HTTP service “gửi ghi tới ba node, nhận hai ACK thì commit” rồi coi đó là Raft hoặc Paxos.

## 16. Network partition: còn node nhưng thiếu quorum

Giả sử N=5, majority=3 và mạng chia:

~~~text
Partition A: {A, B, C}
Partition B: {D, E}
~~~

Nhóm A có thể đạt majority; nhóm B chỉ có hai node, không đạt majority. Trong giao thức consensus đúng, nhóm thiểu số không được commit ghi mới như thể vẫn là leader hợp lệ.

Những lưu ý:

- Cả năm process có thể vẫn chạy; lỗi là **không liên lạc được**.
- Nhóm thiếu quorum có thể trả lỗi hoặc chỉ cho đọc stale theo API.
- Election/failover có độ trễ, không tự tức thời.
- Quorum còn phụ thuộc membership và placement.
- Nếu cả hai nhóm có dữ liệu cũ/khác nhau, phục hồi cần cơ chế hội tụ an toàn.

**Quorum availability là đủ node hợp lệ và reachable**, không chỉ đếm node đang bật.

## 17. Mất node khác với mất zone

Một cluster có ba replica:

~~~text
Zone A: Replica A
Zone B: Replica B
Zone C: Replica C
~~~

Với `W=2, R=2`, trong mô hình các zone độc lập, mất một zone vẫn còn hai replica để phục vụ đọc và ghi.

Nhưng nếu cả ba replica ở cùng Zone A:

~~~text
Zone A: Replica A, B, C
Zone B: không có replica
Zone C: không có replica
~~~

mất Zone A có thể làm mất cả ba. Số `N=3` vẫn là 3 nhưng **failure tolerance theo zone bằng 0** trong tình huống này.

Vì thế, topology cần phân tích ít nhất:

- Node/host.
- Rack.
- Availability zone.
- Region.
- Network segment.
- Tài khoản/quyền quản trị nếu rủi ro liên quan.
- Vị trí leader/voting members.
- Vị trí replica của **mỗi partition/key**, không chỉ tổng số node cluster.

Một hệ có mười node nhưng một partition chỉ có hai replica đều đặt cùng fault domain vẫn dễ mất partition đó.

## 18. Replica chưa bắt kịp và stale read

Giả sử write v11 được hai replica A và B xác nhận:

~~~text
A: version 11
B: version 11
C: version 10
~~~

Với `R=1`, read chọn C có thể trả v10.

Với `R=2`, read chọn B và C có ít nhất B thuộc write quorum. Nhưng **còn phụ thuộc protocol xử lý response**:

- Có lấy và so sánh version hay digest?
- Có read repair không?
- Một bản chưa commit/ack có thể được ưu tiên không?
- Metadata dùng để so phiên bản là timestamp, version vector hay log index?
- Có concurrent writes trên cùng key không?

Nếu chỉ lấy response từ C vì nó trả nhanh, việc đã gửi request tới B không tạo ra bảo đảm freshness tương ứng với R=2.

### Đọc không đồng nghĩa đồng bộ mọi bản sao

Một read có thể biết bản mới nhất trong các phản hồi nhưng không bắt buộc sửa xong mọi replica khác trước khi trả. Read repair có thể xảy ra trong nền tùy sản phẩm.

Không dùng thành công một lần đọc quorum để kết luận replication lag của tất cả node đã về 0.

## 19. Trường hợp timeout và kết quả ghi chưa rõ

Một client gửi ghi:

~~~text
Client -> Coordinator -> A, B, C
A: ACK
B: ghi xong nhưng response thất lạc
C: timeout
Client: timeout
~~~

Có những khả năng:

- Hệ đã đạt W nhưng client mất phản hồi.
- Chưa đạt W nhưng một replica đã giữ dữ liệu.
- Operation đang tiếp tục retry sau khi client bỏ cuộc.
- Một write khác cạnh tranh trong khi write này chưa hoàn tất.

**Timeout không chứng minh chắc write thất bại**, và retry vô điều kiện có thể lặp tác dụng phụ.

Với tăng counter hoặc đặt hàng, ứng dụng nên dùng **operation ID/idempotency key** và cơ chế đối soát theo write contract. Với cập nhật state, CAS/version hoặc transaction có điều kiện giúp bảo vệ khỏi stale overwrite.

Cần phân biệt outcome của request mạng với trạng thái commit của write trong engine.

## 20. Quorum không thay thế atomic check-and-write

Ví dụ tồn kho còn một sản phẩm:

~~~text
Client A: read available=1
Client B: read available=1
Client A: write available=0
Client B: write available=0
~~~

Dù đọc/ghi đều sử dụng một consistency level mạnh, hai request đọc ở những thời điểm khác nhau vẫn có thể cùng thấy available=1 rồi ra quyết định sai.

Điều kiện cần được áp **ở lệnh ghi**:

~~~javascript
db.inventory.updateOne(
  {
    _id: "shop-17#sku-A",
    available: { $gte: 1 }
  },
  {
    $inc: {
      available: -1
    }
  }
);
~~~

Mẫu MongoDB này minh họa một atomic conditional update trong phạm vi một document. Nếu nghiệp vụ phải vừa tạo Order vừa giảm tồn kho ở những document khác nhau, còn cần transaction/workflow thích hợp.

**Quorum phục vụ replication/consistency; business invariant cần được bảo vệ tại nguồn dữ liệu và đúng atomic scope.**

## 21. Sloppy quorum có thể phá giả định tập replica cố định

Một số hệ lấy cảm hứng từ Dynamo-style cho phép nhận ghi ở một node thay thế khi replica danh nghĩa bị lỗi. Đây thường được gọi là **sloppy quorum**, kết hợp với **hinted handoff**.

Giả sử replica danh nghĩa của key X:

~~~text
{A, B, C}
~~~

A không truy cập được. Một write có thể được nhận bởi:

~~~text
{B, D}
~~~

trong đó D giữ dữ liệu tạm để chuyển lại A.

Nếu sau đó read chỉ xét các tập thuộc {A,B,C}, công thức giao nhau dựa trên N=3 cố định **không còn mô tả trọn vẹn** tập ACK của write.

Rủi ro cần hiểu:

- ACK có thể tới từ node không phải home replica.
- Read có thể hỏi một tập không chứa bản vừa ghi.
- Handoff có thể chậm khi A chưa phục hồi.
- Hint có retention/giới hạn và có thể bị mất theo fault model.
- Phải có repair/anti-entropy để hội tụ.

Sloppy quorum thường đánh đổi consistency lấy khả dụng theo cơ chế cụ thể. Không áp máy móc `R+W>N` nếu tập replica thực tế không giống giả định.

## 22. Hinted handoff và read repair

### Hinted handoff

Một coordinator có thể lưu thông tin về write cần gửi cho replica đang unavailable. Khi replica đích hoạt động trở lại, hệ chuyển các hint thích hợp.

Cần xem:

- Hint được ghi bền vững tới mức nào?
- Giữ bao lâu?
- Node nào giữ hint?
- Nếu node giữ hint cũng hỏng thì sao?
- Có giới hạn throughput khi replay?
- Có giữ đúng thứ tự/concurrency semantics không?

Hint có ích cho hội tụ, **không phải bằng chứng mọi bản đã được cập nhật khi write trả success**.

### Read repair

Trong một số hệ, đọc từ nhiều replica phát hiện sự lệch nhau rồi thực hiện sửa bản chậm hoặc lên lịch đồng bộ.

Read repair có thể:

- Làm tăng latency trong những tình huống phải chờ.
- Tốn disk/network IO.
- Không sửa được mọi chênh lệch nếu read chỉ chạm một phần dữ liệu.
- Có chế độ blocking hoặc background tùy sản phẩm/phiên bản.
- Không thay thế repair/anti-entropy toàn diện.

Một read thành công không nhất thiết nghĩa mọi replica đã hội tụ.

## 23. Anti-entropy, repair và tombstone

Trong nhiều hệ phân tán, repair/anti-entropy so sánh trạng thái giữa replica rồi đồng bộ dữ liệu còn thiếu hoặc khác nhau.

Với xóa, database có thể dùng **tombstone** đánh dấu một record đã bị xóa. Nếu tombstone hết hạn và bị compact trước khi replica ngắt mạng nhận được nó, một bản cũ có thể xuất hiện trở lại theo failure scenario của engine.

Vì thế cần thiết kế:

- Repair interval phù hợp.
- Thời gian một replica có thể offline.
- Tombstone retention và compaction policy.
- Backup khi cần lấy trạng thái lịch sử.
- Monitoring các replica chậm/hỏng.

**Repair không phải undo**. Khi một lệnh DELETE hợp lệ nhưng sai ý nghiệp vụ đã lan tới các replica, repair thường làm chúng hội tụ theo trạng thái xóa; để lấy trạng thái trước đó cần backup/PITR hoặc nguồn lịch sử phù hợp.

## 24. Concurrent writes và giải quyết xung đột

Hai client cùng ghi:

~~~text
Client A: Order status = CONFIRMED
Client B: Order status = CANCELLED
~~~

Các write có thể chồng lấn theo thời gian, nhất là trong hệ nhiều writer.

Engine cần quy tắc quyết định:

- Leader serialization và commit log.
- Consensus/ballot.
- Last-write-wins theo timestamp.
- Version vector/causal metadata.
- Merge do ứng dụng thực hiện.
- CRDT trong mô hình dữ liệu phù hợp.

**Quorum intersection không định nghĩa tự động giá trị nào thắng**.

Ví dụ last-write-wins dựa trên timestamp có thể chịu tác động clock skew. Write xuất hiện sau theo thời gian thực chưa chắc có timestamp lớn nhất.

Với trạng thái nghiệp vụ có state machine, nên dùng conditional write, version/CAS hoặc transaction theo guarantee của nguồn. Không nên chỉ dựa vào chính sách “timestamp lớn nhất thắng” khi phải bảo toàn bất biến quan trọng.

## 25. Cassandra: replication factor và consistency level

Apache Cassandra cho phép chọn replication factor theo keyspace/datacenter và consistency level cho các operation theo khả năng phiên bản/driver.

Các khái niệm:

| Cấu hình/khái niệm | Ý nghĩa |
|---|---|
| Replication factor (RF) | Số replica dữ liệu được đặt theo chiến lược replication |
| `ONE` | Yêu cầu số xác nhận tối thiểu tương ứng với một replica |
| `TWO`, `THREE` | Yêu cầu số xác nhận tương ứng theo tên |
| `QUORUM` | Quorum đa số theo tập replica và semantics của CL |
| `LOCAL_QUORUM` | Quorum trong datacenter local |
| `EACH_QUORUM` | Trong những write path được hỗ trợ, yêu cầu quorum ở từng datacenter |
| `ALL` | Yêu cầu tất cả replica theo policy |
| `ANY` | Một mức ghi đặc biệt, có thể liên quan hinted handoff |
| `SERIAL`, `LOCAL_SERIAL` | Các mức serial consistency dùng cho LWT theo phạm vi |

Không phải consistency level nào cũng hợp lệ cho cả read và write. Ví dụ `ANY` là một mức **write**, không phải chế độ đọc thông thường. `SERIAL` liên quan giao thức conditional/LWT, không được trộn như thể nó chỉ là R=2.

### Ví dụ RF=3

Giả sử một datacenter có RF=3:

~~~text
RF = 3
Write CL = QUORUM
Read CL = QUORUM
~~~

Thông thường quorum size là 2 trong ba replica theo phạm vi áp dụng. Khi một replica không phản hồi, hai bản còn lại có thể đủ ngưỡng.

Nhưng đừng suy ra:

- Mọi concurrent mutation đều linearizable.
- Một read quorum bất kỳ luôn tạo transaction snapshot đa row.
- Repair không còn cần thiết.
- Một lệnh delete sai có thể rollback bằng quorum.
- CL nào cũng cùng semantics ở mọi topology/phiên bản.

Cassandra có conflict resolution dựa trên cơ chế mutation/timestamp và thiết kế leaderless; cần xét chi tiết khi có ghi đồng thời.

## 26. Cassandra: kết hợp read/write CL

Với RF=3 trong một datacenter, có thể minh họa:

| Write CL | Read CL | Trực giác | Đánh đổi |
|---|---|---|---|
| ONE | ONE | Chờ ít replica | Có thể stale, ưu tiên latency/availability |
| QUORUM | QUORUM | 2/3 cho cả hai | Giao quorum trong mô hình, chịu một lỗi lý tưởng |
| ALL | ONE | Ghi chặt, đọc nhẹ | Write không chịu replica outage |
| ONE | ALL | Ghi nhẹ, đọc chặt | Read không chịu replica outage |
| ALL | ALL | Mọi replica tham gia | Availability thấp khi một node lỗi |

Bảng cho thấy **trade-off về ngưỡng**, không phải lời khẳng định toàn bộ Cassandra triển khai linearizable từ các cặp số đó.

### Vì sao không dùng ALL cho mọi trường hợp?

Ở hệ nhiều replica, một node chậm hoặc rớt mạng có thể khiến CL=ALL không thể hoàn thành. Nếu nghiệp vụ cần chịu một zone outage, cấu hình đòi tất cả node sẽ mâu thuẫn mục tiêu availability.

Cần chọn level theo loại operation, SLA latency và fault model, không chọn mức cao nhất theo cảm tính.

## 27. Cassandra nhiều datacenter: LOCAL_QUORUM khác QUORUM

Giả sử replication strategy:

~~~text
Datacenter A: RF=3
Datacenter B: RF=3
~~~

`LOCAL_QUORUM` tính quorum ở datacenter local: cần hai trong ba replica local theo mô hình này.

`EACH_QUORUM` trên write paths được hỗ trợ đòi quorum tại **mỗi** datacenter, tức hai trong ba tại A và hai trong ba tại B trong ví dụ.

Một global `QUORUM` có thể xét quorum theo tổng replication factor và semantics của Cassandra/configuration. Cần tra đúng kiểu consistency và datacenter policy.

### Điều gì nếu region/datacenter B bị mất?

- Một client ở A với LOCAL_QUORUM có thể tiếp tục hoạt động nếu hai replica A còn sẵn sàng, theo write/read path được hỗ trợ.
- Một write yêu cầu EACH_QUORUM có thể không đạt vì datacenter B không trả quorum.
- Nếu client chuyển region, local quorum sẽ phụ thuộc datacenter của coordinator/driver routing.
- Multi-DC placement, WAN latency và network partition có thể làm tail latency tăng.

**Quorum local giảm phụ thuộc WAN** nhưng không tự tạo một giao dịch linearizable đồng thời giữa các region. Cần thiết kế rõ consistency scope và conflict behavior.

## 28. Cassandra LWT khác read/write quorum thông thường

Một yêu cầu như:

> Chỉ tạo username nếu chưa tồn tại.

không được giải quyết bằng cách ứng dụng đọc QUORUM rồi insert thông thường, vì hai client có thể cùng đọc “chưa có” trước khi cả hai ghi.

Cassandra có **Lightweight Transactions** với các điều kiện như:

~~~sql
INSERT INTO usernames (
    tenant_id, username_key, user_id
)
VALUES (
    'shop-17', 'NOVA', 'user-101'
)
IF NOT EXISTS;
~~~

Trong schema tương ứng, LWT dùng protocol đồng thuận và serial consistency để thực thi điều kiện theo phạm vi hỗ trợ.

Đánh đổi: nhiều vòng trao đổi, latency và contention tăng. Dùng LWT ở những invariant thật sự cần CAS/insert-if-absent, không thay toàn bộ write thường bằng LWT nếu không cần.

## 29. MongoDB: replica set và write concern majority

MongoDB replica set có mô hình primary–secondary và các thành viên có thể tham gia election theo cấu hình.

Ví dụ một write concern:

~~~javascript
db.orders.insertOne(
  {
    _id: "order-101",
    tenantId: "shop-17",
    status: "PENDING"
  },
  {
    writeConcern: {
      w: "majority",
      j: true
    }
  }
);
~~~

Ví dụ mang tính minh họa về yêu cầu acknowledgment/journaling; hỗ trợ và semantics cụ thể phụ thuộc MongoDB version, topology và driver. Không dùng như một bằng chứng rằng mọi replica đã có dữ liệu hoặc dữ liệu đã được backup.

### Majority write khác đọc từ secondary

Một write majority-acknowledged có thể đã được xác nhận theo policy của replica set, nhưng một secondary vẫn có thể lag khi ứng dụng đọc từ nó.

Cần phân biệt:

- `writeConcern: "majority"` liên quan mức ghi được xác nhận.
- `readPreference: "secondary"` là lựa chọn đọc từ node nào.
- `readConcern: "majority"` liên quan trạng thái majority-committed có thể quan sát.
- `readConcern: "linearizable"` có phạm vi/điều kiện mạnh hơn cho những operation được hỗ trợ, thường đọc primary.
- Causal session giúp giữ quan hệ như read-your-writes khi được cấu hình đúng.

**Majority read không tự là latest linearizable read**, và majority write không khiến mọi cache/search projection cập nhật đồng thời.

## 30. MongoDB majority voting không luôn bằng số bản dữ liệu

Trong replica set, việc bầu primary dùng voting membership. Một số cấu hình có thể có thành viên có vai trò khác nhau, ví dụ arbiter tham gia election nhưng không chứa bản dữ liệu như một secondary bình thường.

Do đó:

- Đếm tổng “số member” không luôn bằng số bản chứa dữ liệu.
- Majority để election và requirement acknowledgment của write có semantics riêng.
- Placement của data-bearing members quan trọng với durability.
- Replica lag, journaling, write concern và fault model cùng ảnh hưởng an toàn.
- Không kết luận một arbiter tạo thêm một bản backup hoặc một replica dữ liệu.

Khi thiết kế chịu lỗi, cần vẽ rõ **voting nodes** và **data-bearing nodes**, đồng thời xem yêu cầu majority thực của topology, thay vì chỉ nhìn số thành viên trên dashboard.

## 31. DynamoDB: không phải mọi NoSQL cho chỉnh R/W trực tiếp

Amazon DynamoDB là dịch vụ managed, cung cấp API/consistency modes thay vì cho người dùng chọn tùy ý `N=3, W=2, R=2` cho từng table như một hệ leaderless có tunable CL.

Ví dụ những chế độ đọc:

- Eventually consistent read trên các đường đọc được hỗ trợ.
- Strongly consistent read trên base table và loại index được hỗ trợ trong phạm vi tương ứng.
- Global Secondary Index có cập nhật bất đồng bộ và không có cùng strong-read option như base table.
- Global Tables có replication giữa region và những semantics riêng cho multi-region.

Không nên lấy thông tin “DynamoDB lưu nhiều bản” rồi suy ra chính xác ngưỡng nội bộ W/R hoặc cam kết linearizability toàn cầu mà API không công bố.

**Hợp đồng sản phẩm và phạm vi operation** quan trọng hơn đoán cấu trúc replication bên trong một dịch vụ managed.

## 32. DynamoDB Global Tables: scope của consistency

Một ứng dụng có Global Tables tại region A và B:

~~~text
Write Order v11 được xác nhận tại A
Replication đến B chưa hoàn tất
Read tại B vẫn có thể thấy v10
~~~

Chế độ strong read trong một region không tự bảo đảm nhìn thấy tức thì tất cả write ở region khác trong mọi cấu hình Global Tables.

Cần làm rõ:

- Mô hình global table và conflict resolution.
- Region nào nhận write.
- Client có session affinity hay route chuyển vùng không.
- Khi mất một region, có chấp nhận dữ liệu cũ không.
- Business invariant cần nhất quán global hay region-local.
- Side effect như payment/stock có nằm ngoài table không.

Tăng số region nâng cao khả năng chịu **một số lỗi địa lý**, nhưng không tự giải quyết concurrent writes toàn cầu hoặc xóa nhầm được replicate.

## 33. Redis: replica ACK không tự là consensus commit

Redis có replication và những cơ chế đợi replica acknowledgement trong các triển khai/phiên bản tương ứng, ví dụ lệnh `WAIT`.

Tuy nhiên:

- Chờ replica đã nhận write không tự đồng nghĩa mọi replica đã fsync bền vững.
- Redis replication/failover có semantics riêng, không giống Raft majority commit theo mặc định.
- Có thể vẫn mất một số write gần failover tùy persistence/acknowledgment/fault model.
- Một thao tác được nhiều replica biết đến không tự là transaction với MongoDB hoặc external payment.
- Redis AOF/RDB là cơ chế persistence; backup độc lập cần kế hoạch riêng.

Không nên gọi một lệnh Redis WAIT với hai replica là “linearizable consensus” chỉ vì có hai ACK.

## 34. Quorum, durability và backup là ba khái niệm

| Khái niệm | Câu hỏi |
|---|---|
| Quorum | Đủ bao nhiêu node hợp lệ để operation được coi là đạt ngưỡng? |
| Consistency | Read/write được phép có những lịch sử quan sát nào? |
| Durability | Write đã xác nhận sống sót qua loại crash/lỗi nào? |
| Availability | Khi node/mạng lỗi, operation còn trả được kết quả không? |
| Latency | Operation mất bao lâu? |
| Backup/PITR | Nếu dữ liệu hiện hành sai hoặc mất, có thể quay về trạng thái quá khứ nào? |

Một DELETE sai có thể được majority-acknowledged, durable và replicated hoàn hảo. Điều đó chỉ có nghĩa dữ liệu sai được giữ đáng tin — **không có nghĩa hệ có thể undo**.

Quorum và replication không thay thế backup có retention, cách ly fault domain và restore drill.

## 35. Đánh đổi latency khi tăng R hoặc W

Trong mô hình đơn giản, nếu coordinator gửi request song song tới N replica và cần K phản hồi hợp lệ, thời gian hoàn tất bị ảnh hưởng bởi **thời điểm phản hồi hợp lệ thứ K**.

Giả sử:

~~~text
Replica A: ACK sau 10 ms
Replica B: ACK sau 20 ms
Replica C: ACK sau 300 ms
~~~

Nếu bỏ qua các overhead khác:

- W=1 có thể chỉ cần ACK nhanh nhất.
- W=2 cần tới ACK thứ hai.
- W=3 đợi cả replica chậm nhất.

Đây là trực giác về thời gian chờ quorum, không phải công thức latency chính xác của mọi engine. Trong thực tế còn có coordinator overhead, leader election, WAL/fsync, conflict reconciliation, queue, compression và network.

### Cross-region quorum

Nếu write phải chờ xác nhận ở region khác, độ trễ WAN có thể chi phối:

~~~text
ACK cùng zone: vài ms trong ví dụ
ACK xuyên region: có thể lớn hơn đáng kể
~~~

Một mức write consistency mạnh hơn theo fault model có thể khiến p95/p99 tăng. Cần benchmark trong topology thật, không giả định “quorum nhiều hơn luôn nhanh vì có nhiều bản sao”.

## 36. Chịu lỗi theo node khác chịu lỗi theo thời gian phản hồi

Với `N=3, R=W=2`, công thức đơn giản nói có thể chịu một replica không tham gia. Nhưng operation vẫn có thể timeout dù chỉ một node chết:

- Node còn sống đáp ứng chậm hơn deadline.
- Coordinator không kết nối được đúng hai replica.
- Leader election chưa xong.
- Read preference/placement ngăn chọn node còn khỏe.
- Quorum local không đủ tại datacenter được yêu cầu.
- Hệ đang bootstrap/reconfigure và chưa có đủ bản sao hợp lệ.
- Disk IO hoặc journal bị nghẽn.

Phân biệt:

1. **Node crash tolerance:** số node chết giả định.
2. **Network availability:** các node có thể liên lạc với nhau không.
3. **Latency SLO:** operation có hoàn tất trước deadline không.
4. **Durability:** ACK giữ được qua lỗi gì.
5. **Consistency:** read/write được phép có lịch sử nào.

Không lấy `N-W` làm cam kết đầy đủ về uptime.

## 37. Quorum khi membership thay đổi

Một key ban đầu có replica:

~~~text
Old membership: {A, B, C}
New membership: {B, C, D}
~~~

Nếu các coordinator chưa thống nhất membership, một số node có thể dùng cấu hình cũ, một số dùng cấu hình mới. Khi đó chứng minh overlap trong **một tập cố định** chưa đủ.

Hệ consensus thường có cơ chế reconfiguration hoặc joint consensus an toàn; các hệ phân tán khác có routing metadata, bootstrap/streaming/repair và cách phối hợp placement riêng.

Quy tắc:

- Dùng cơ chế thay đổi topology được sản phẩm hỗ trợ.
- Không tùy tiện cập nhật danh sách replica thủ công.
- Đảm bảo dữ liệu đã stream tới replica mới.
- Theo dõi trạng thái bootstrap, decommission, rebalance và repair.
- Hiểu quorum trong giai đoạn chuyển đổi, không chỉ steady state.

### Tăng RF không có nghĩa dữ liệu cũ đã có thêm bản ngay

Nếu tăng replication factor từ 2 lên 3, node thứ ba có thể cần thời gian nhận dữ liệu. Cấu hình mong muốn khác **replica coverage đã đạt**. Trước khi dựa vào RF mới để chịu lỗi, cần xác minh streaming/repair và placement đã hoàn tất.

## 38. Quorum một key không tạo snapshot nhiều key

Giả sử có hai tài khoản:

~~~text
Account A: balance = 100
Account B: balance = 100
~~~

Một transfer:

~~~text
Step 1: A = 90
Step 2: B = 110
~~~

Nếu báo cáo đọc A sau bước 1, B trước bước 2 thì tổng thành 190. Cả hai read riêng có thể đạt read quorum, nhưng **ảnh chụp liên tài khoản không nhất quán**.

Muốn một snapshot phù hợp cần transaction với isolation thích hợp, snapshot coordinator/checkpoint hoặc reconciliation theo domain. Quorum per-key không tự biến thành serializable transaction nhiều document/partition.

## 39. Cache và Search vẫn có thể stale

Ngay cả khi source DB có write majority và read mạnh, cache/read model vẫn có vòng đời khác.

Ví dụ:

~~~text
Source Service: INACTIVE, version 11
Search Service: ACTIVE, version 10
Cache Service:  ACTIVE, version 10
~~~

Quorum ở source không làm Search/Cache cập nhật tức thời. Khi người dùng bấm booking, source-of-truth phải kiểm tra trạng thái có thẩm quyền trong operation ghi thích hợp.

Cần bảo vệ:

- Read-your-writes/session token khi người dùng vừa cập nhật.
- Versioned event apply để projection không lùi.
- TTL/invalidation có chính sách rõ.
- Authorization theo dữ liệu hiện hành cho thao tác nhạy cảm.
- Điều kiện nghiệp vụ tại write-time, không chỉ một read từ cache.

## 40. Monitoring cho quorum và fault tolerance

### Replica và topology

- Replica health theo shard/partition, không chỉ tổng số node.
- Node unreachable/down, bootstrap, decommission.
- Placement theo rack/AZ/region.
- Applied checkpoint và replication lag.
- Leader election, membership changes.
- Read repair/anti-entropy backlog.
- Tombstone và repair health.

### Read/write operation

- Consistency level thực tế.
- ACK latency theo replica/quorum.
- P50/P95/P99 read/write latency.
- Insufficient-replicas/unavailable errors.
- Timeouts và unknown write outcome.
- Coordinator retry/speculative attempts.
- Hot partition/CPU/disk/network pressure.
- Conflicts, stale read và version divergence nếu có.

### Data correctness

- Read-your-writes/monotonic-read violations.
- Invariant breaches như overselling.
- Idempotency duplicate requests.
- Out-of-order projection events.
- Replica re-sync/recovery duration.
- Backup/PITR restore test results.

Một dashboard latency trung bình đẹp không chứng minh tất cả partitions có quorum. Cần phân tách theo region, partition, CL và failure mode.

## 41. Fault injection để kiểm chứng quorum

| Tình huống | Câu hỏi |
|---|---|
| N=3, R=W=2, tắt một node | Read/write còn đạt ngưỡng trong deadline không? |
| Tắt hai node | Operation có từ chối đúng policy không? |
| Network partition 2–1 | Nhóm nào có thể tiếp tục ghi theo protocol? |
| Một follower rất chậm | P99 quorum latency tăng thế nào? |
| Leader chết | Election, failover và acknowledged writes ra sao? |
| Replica chưa apply write | Read consistency có bị vi phạm không? |
| Concurrent writes | Conflict resolution có đúng contract không? |
| Hinted handoff bị trì hoãn | Stale read kéo dài bao lâu? |
| Read repair dừng | Replica divergence có tăng không? |
| Membership change | Quorum còn an toàn lúc rebalance không? |
| Mất một AZ | Replica placement có đúng fault model không? |
| Mất một region | LOCAL_QUORUM và cross-region semantics ra sao? |
| Timeout sau commit | Retry có nhân đôi effect không? |

Kiểm thử node/network cần thực hiện ở môi trường được cho phép, có kế hoạch rollback và giới hạn tác động. Không gây gián đoạn production ngoài một quy trình diễn tập được phê duyệt.

## 42. Quorum là một lớp của ứng dụng đặt lịch

Một hệ đặt lịch có:

- Booking source-of-truth trong NoSQL.
- Slot availability được cập nhật khi người dùng đặt.
- Search index giúp khám phá dịch vụ.
- Redis cache giúp hiển thị slot trống.
- Ba replica nguồn trải trên ba availability zone.

Giả sử chọn mức write acknowledgment đa số theo khả năng database. Khi một node lỗi, nguồn có thể tiếp tục ghi nếu còn đủ quorum.

Nhưng vẫn chưa tự giải quyết:

- Hai user đọc cùng slot trống rồi cùng đặt.
- Cache cho biết slot còn trống dù source đã hết.
- Request timeout và client retry booking.
- Search index chưa thấy trạng thái khóa.
- Booking và slot reservation ở hai document.
- Một lệnh xóa sai lan tới mọi replica.
- Region outage hoặc backup bị xóa bởi cùng quyền quản trị.

Quy trình đúng hơn:

1. Dùng cache/search để khám phá.
2. Xác thực tenant và quyền.
3. Reserve slot bằng conditional write tại nguồn.
4. Dùng transaction/workflow khi cần tạo Booking cùng reservation.
5. Ghi idempotency key cho retry.
6. Đồng bộ projection bằng event có sourceVersion.
7. Kiểm tra lại source khi xác nhận booking.
8. Có backup/PITR và restore drill.
9. Đo quorum latency, failover và business invariants.

**Quorum giúp lớp lưu trữ chịu lỗi**, còn đúng nghiệp vụ cần thêm atomic conditions, transaction, idempotency và observability.

## 43. Những ngộ nhận phổ biến

**“Có N replica nghĩa là chịu được N node chết.”** Số bản sao không cho phép mất tất cả; ngưỡng read/write và fault domain quyết định giới hạn.

**“W=2 chắc chắn có hai bản durable trên disk.”** ACK có semantics riêng; cần xét journal/fsync và durability policy.

**“R=2 là hỏi hai node rồi lấy kết quả trả nhanh nhất.”** Read protocol phải sử dụng đúng bằng chứng và reconciliation.

**“R+W=N là đủ giao nhau.”** Hai tập có thể không giao. Cần `R+W>N`.

**“R+W>N nghĩa là mọi read linearizable.”** Còn phụ thuộc membership, ACK, concurrent writes và conflict resolution.

**“2W>N tự tạo consensus.”** Consensus cần ordering, ballot/term và commit rules.

**“N-W là số lỗi thật chắc chắn chịu được ở mọi trường hợp.”** Công thức giả định node còn lại reachable, hợp lệ và đúng latency policy.

**“Node healthy thì quorum chắc đạt.”** Network partition, quá tải hoặc read preference có thể làm operation không đạt.

**“Chỉ cần thêm replica là giảm latency.”** Quorum lớn, network và tail latency có thể khiến chậm hơn.

**“Quorum read sửa xong mọi replica trước khi trả.”** Read repair có hành vi khác nhau tùy engine.

**“Sloppy quorum vẫn áp công thức giao theo tập replica cố định.”** Các node thay thế có thể làm giả định không còn đúng.

**“Cassandra QUORUM là serializable transaction nhiều row.”** Consistency level khác LWT và transaction scope.

**“LOCAL_QUORUM là global consistency.”** Phạm vi datacenter local không tự bảo vệ multi-region concurrency.

**“MongoDB majority read luôn latest.”** Majority-committed state và linearizable latest read không đồng nhất.

**“MongoDB arbiter là một bản sao dữ liệu.”** Arbiter có vai trò voting/election, không phải data replica thông thường.

**“DynamoDB có thể tùy chọn R/W như Cassandra.”** Dịch vụ managed cung cấp consistency modes theo API, không nhất thiết cho phép tự đặt N/R/W.

**“Redis WAIT là một majority consensus durable.”** ACK replication không tự là Raft/Paxos commit.

**“Quorum chặn hai request cùng đặt một slot.”** Cần conditional reservation/CAS, idempotency và transaction/workflow thích hợp.

**“Đã đổi RF=3 nghĩa là mọi record đã có ba bản.”** Rebalance/streaming/repair có thể chưa xong.

**“Per-key quorum cho snapshot nhất quán toàn bộ database.”** Invariant đa key cần isolation/transaction riêng.

**“Quorum thay thế backup.”** Delete/bug hợp lệ có thể được replicate rất chính xác; vẫn cần lịch sử phục hồi.

## 44. Bài tập về N/R/W và khả năng chịu lỗi

### Bài A — Có giao nhau không?

Cho `N=5, W=3, R=2`.

**Câu hỏi:** mọi read quorum có giao với write quorum không?

**Hướng giải:** không. `R+W=5`, bằng N. Có thể chọn write {A,B,C}, read {D,E}, hai tập không giao.

### Bài B — Khi nào hai write quorum giao nhau?

Cho `N=5, W=3`.

**Câu hỏi:** hai write quorum bất kỳ có giao nhau không?

**Hướng giải:** có, vì `2W=6>5` trong một membership cố định.

### Bài C — Số node lỗi tối đa

Cho `N=5, R=W=3`.

**Câu hỏi:** tối đa mấy node có thể không phản hồi mà read và write vẫn đạt ngưỡng lý tưởng?

**Hướng giải:** `N-R=N-W=2`. Cả hai cùng chịu tối đa hai lỗi theo giả định các node còn lại reachable.

### Bài D — Đọc nhẹ, ghi chặt

Cho `N=3, R=1, W=3`.

**Câu hỏi:** khi một node chết thì điều gì xảy ra?

**Hướng giải:** read vẫn có thể đạt ngưỡng một node; write không thể đủ ba xác nhận.

### Bài E — Ghi nhẹ, đọc chặt

Cho `N=3, R=3, W=1`.

**Câu hỏi:** khi một node chết?

**Hướng giải:** write có thể đạt ngưỡng, read không đạt yêu cầu cả ba. Có dữ liệu không đồng nghĩa API đọc theo policy vẫn khả dụng.

### Bài F — Placement sai

Một partition có RF=3, ba replica đều thuộc cùng một availability zone.

**Câu hỏi:** có chịu được mất cả zone đó không?

**Hướng giải:** không. Replica placement phải trải đúng fault domain mà kiến trúc muốn bảo vệ.

### Bài G — Mạng chia đôi

N=5, majority=3. Cluster chia thành nhóm ba và hai node.

**Câu hỏi:** nhóm nào có majority?

**Hướng giải:** nhóm ba, với điều kiện cùng membership và các node liên lạc được; nhóm hai không đủ majority.

### Bài H — Read stale

Write v11 được A,B ACK. C còn v10. Với `N=3, W=2, R=1`, GET chỉ hỏi C.

**Câu hỏi:** v10 có thể xuất hiện không?

**Hướng giải:** có. `R+W=3` không lớn hơn N, nên read/write không có overlap bắt buộc.

### Bài I — Giao nhau nhưng protocol sai

Write v11 được A,B ACK. Read hỏi B,C nhưng lấy ngay response C=v10, bỏ qua B=v11.

**Câu hỏi:** có thể viện dẫn `R+W>N` để tuyên bố read đúng không?

**Hướng giải:** không. Giao nhau chỉ hữu ích nếu read protocol thật sự dùng và xử lý đúng bằng chứng từ các replica.

### Bài J — Sloppy quorum

Replica danh nghĩa {A,B,C}; A unavailable; D nhận tạm write cùng B.

**Câu hỏi:** điều kiện giao nhau tính trên {A,B,C} có đủ không?

**Hướng giải:** không; write thực tế được ACK bởi một node ngoài tập danh nghĩa. Phải xét handoff và semantics giao thức cụ thể.

### Bài K — Cassandra hai datacenter

DC A có RF=3, DC B có RF=3. Write yêu cầu EACH_QUORUM nhưng B chỉ còn một replica hoạt động.

**Câu hỏi:** có đạt write quorum theo mô hình mỗi DC phải có majority không?

**Hướng giải:** không; B cần hai replica. Với LOCAL_QUORUM ở A có thể cho kết quả khác nếu A còn đủ quorum.

### Bài L — MongoDB majority

Một write majority thành công; read secondary ngay sau vẫn trả trạng thái cũ.

**Câu hỏi:** write có chắc đã thất bại không?

**Hướng giải:** không. Secondary có thể lag; cần xem read preference, read concern và causal session.

### Bài M — DynamoDB GSI

Item được cập nhật ở base table, Query GSI ngay chưa thấy.

**Câu hỏi:** có thể suy “quorum chưa đạt” không?

**Hướng giải:** không. GSI là read path đồng bộ bất đồng bộ với source và có consistency semantics riêng.

### Bài N — Tồn kho và conditional write

GET mạnh trả `available=1`. Client khác mua trước khi client hiện tại gửi checkout.

**Câu hỏi:** quorum/strong read có ngăn overselling nếu sau đó ghi vô điều kiện không?

**Hướng giải:** không; cần conditional decrement hoặc transaction tại nguồn lúc ghi.

### Bài O — Timeout sau commit

Client gửi lệnh tăng counter; commit có thể đã xảy ra nhưng response bị mất.

**Câu hỏi:** có thể retry `increment` vô điều kiện không?

**Hướng giải:** không an toàn nếu mỗi event chỉ được đếm một lần. Cần operation ID/idempotency hoặc reconciliation.

### Bài P — Thêm replica

Đội vận hành tăng RF từ 2 lên 3 rồi ngay lập tức tắt một node, giả định mọi dữ liệu đã có ba bản.

**Câu hỏi:** thiếu bước gì?

**Hướng giải:** xác minh streaming/repair/bootstrap đã hoàn tất và placement/coverage đủ trước khi dựa vào RF mới.

### Bài Q — N=4 với R=3, W=2

**Câu hỏi:** read-write overlap và write-write overlap có đều được bảo đảm không?

**Hướng giải:** `R+W=5>4` nên read-write giao. Nhưng `2W=4` bằng N, nên hai write quorum không bắt buộc giao. Cần protocol quyết định concurrency riêng.

### Bài R — Partial outage

`N=3, R=W=2`. Một node đã chết và một node còn sống phản hồi sau 10 giây; API timeout ở 2 giây.

**Câu hỏi:** tại sao đọc/ghi có thể timeout dù công thức chịu một lỗi?

**Hướng giải:** công thức đếm node không tính deadline. Trước 2 giây có thể chưa nhận đủ hai phản hồi hợp lệ.

## 45. Checklist chọn cấu hình quorum

Trước khi thay đổi consistency/replication, hãy trả lời:

1. Đơn vị replication là **key, partition, shard hay toàn replica set**?
2. N đếm **data replicas** hay **voting members**?
3. Engine cho phép chỉnh R/W trực tiếp hay chỉ có consistency levels?
4. ACK xác nhận **memory, WAL, journal, durable commit hay applied state**?
5. R/W tính trong **local DC, mỗi DC hay toàn cluster**?
6. Trong cùng membership cố định, `R+W>N` và nếu cần `2W>N` có được thỏa không?
7. Có leader, consensus, sloppy quorum hoặc node thay thế không?
8. Concurrent writes được ordering và reconcile theo quy tắc nào?
9. Có read repair, hinted handoff, anti-entropy và tombstone policy nào?
10. Theo mô hình lý tưởng, `N-W` và `N-R` bằng bao nhiêu?
11. Replica placement có trải đúng **node/rack/AZ/region** mục tiêu không?
12. Khi mất quorum, request **chờ, timeout, từ chối hay trả stale**?
13. Quorum có làm WAN latency/tail latency vượt SLO không?
14. RF mới đã thực sự được **bootstrap/repair** cho dữ liệu cũ chưa?
15. Business invariant có cần CAS, unique constraint hoặc transaction không?
16. Cache/Search có consistency và freshness contract riêng không?
17. Retry sau timeout có idempotency không?
18. Có backup/PITR cho xóa nhầm và corruption không?
19. Có dashboard theo partition, CL, node, region và version lag không?
20. Đã diễn tập node/zone loss, partition, failover và concurrent writes chưa?

### Hợp đồng kiến trúc minh họa

~~~yaml
system: BookingNoSQL
replication:
  targetCopiesPerKey: 3
  placement: threeAvailabilityZones
  membershipChanges: managedByDatabaseProtocol
consistency:
  writePolicy: majorityAcknowledged
  readPolicy: perEndpoint
  ownProfile: readYourWrites
  bookingCommit: conditionalWriteAtSource
failureModel:
  targetUnavailableNodes: 1
  zoneLoss: oneZone
  regionLoss: separateDRPlan
durability:
  acknowledgmentSemantics: verifyWithEngineVersion
  backupPitr: required
correctness:
  idempotencyKey: required
  sourceVersionForProjections: required
  multiDocumentInvariants: transactionOrWorkflow
observability:
  - quorumUnavailableErrors
  - replicaLag
  - readWriteP99Latency
  - repairBacklog
  - failoverDuration
validation:
  - nodeFailureDrill
  - zonePartitionDrill
  - concurrentBookingTest
  - restoreDrill
~~~

YAML là **mẫu tài liệu thiết kế**, không phải cấu hình được một database thực thi tự động. Các thuật ngữ majority, read/write concern, durability và replication phải được ánh xạ sang API/driver của engine thật.

## 46. Kết luận

Trong mô hình quorum đọc/ghi cổ điển:

- `N` là số bản sao mục tiêu của một khóa.
- `W` là số xác nhận ghi cần đạt.
- `R` là số phản hồi đọc hợp lệ cần tham gia.
- `R+W>N` bảo đảm **read quorum và write quorum giao nhau** trong cùng tập replica cố định.
- `2W>N` bảo đảm **hai write quorum** trong cùng tập cố định giao nhau.
- `N-W` và `N-R` là **giới hạn số node lỗi lý tưởng** để write/read còn đạt ngưỡng.
- Quorum đa số có kích thước `floor(N/2)+1`.

Những quan hệ này rất hữu ích để phân tích fault tolerance, nhưng **không tự bảo đảm linearizability, durability, transaction đa document hoặc an toàn nghiệp vụ**. Tính đúng đắn còn phụ thuộc leader/consensus, conflict resolution, ACK semantics, membership, replica placement, network partition và các khả năng được sản phẩm công bố.

> **Đủ bản sao tham gia chưa chắc đã đọc mới nhất; đủ quorum chưa chắc mọi giao dịch đều an toàn; và có nhiều replica chưa chắc phục hồi được dữ liệu bị xóa nhầm.**

Hãy chọn quorum theo fault model và SLO thực tế, giữ những invariant quan trọng bằng conditional write/transaction, kiểm tra quyền và dữ liệu nguồn khi cần, kết hợp backup độc lập và đo lường bằng fault injection. Khi đó các thông số N/R/W trở thành một quyết định kiến trúc có thể giải thích, kiểm chứng và vận hành bền vững trong hệ NoSQL phân tán.
