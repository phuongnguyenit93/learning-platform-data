# Hinted handoff và giới hạn của cơ chế chuyển tiếp ghi bị bỏ lỡ

## 1. Khi một bản sao vắng mặt đúng lúc có ghi mới

Trong kiến trúc NoSQL phân tán, một bản ghi thường được sao chép tới nhiều **replica** để hệ thống vẫn hoạt động khi một số node gặp sự cố. Tuy nhiên, **một write thành công không nhất thiết đã đến tất cả replica**, nhất là khi ứng dụng chọn consistency level cho phép xác nhận với ít hơn toàn bộ số bản sao.

Giả sử một partition trong Apache Cassandra có **replication factor (RF) = 3**, được lưu trên ba node A, B, C:

~~~text
                        Client
                          |
                          v
                    Coordinator
                    /     |     \
                   v      v      v
                Node A  Node B  Node C
                 K=v1    K=v1    K=v1
~~~

Tại thời điểm T1, C mất kết nối. Client cập nhật `K=v2` với write consistency level `QUORUM`. Trong trường hợp RF=3 đơn giản, hai replica A/B có thể xác nhận và client nhận thành công, dù C vẫn giữ `v1`.

~~~text
T0  A=v1, B=v1, C=v1
T1  C offline
T2  Client WRITE K=v2
T3  A=v2, B=v2, C=v1
T4  Client nhận write success theo QUORUM
T5  C online trở lại nhưng dữ liệu vẫn có thể cũ
~~~

**Hinted handoff** là cơ chế giúp một node đang hoạt động **tạm ghi nhớ mutation mà replica khác bỏ lỡ**, sau đó **chuyển lại mutation** khi replica đích trở nên sẵn sàng.

Về ý tưởng:

~~~text
               Coordinator
               /         \
              v           v
      Replica đang sống   Hint lưu cục bộ
      nhận mutation       (target = C)
                               |
                       C trở lại online
                               |
                               v
                         Giao lại hint
                               |
                               v
                        C áp dụng ghi
~~~

Bài học thuộc chương **Sao chép và quorum** tập trung vào cơ chế này trong Cassandra, cách nó tương tác với consistency level, anti-entropy repair, TTL, tombstone, multi-data-center và xử lý sự cố.

> **Nguyên tắc trọng tâm:** Hinted handoff giúp chuyển lại **những mutation đã được coordinator lưu thành hint**. Nó **không phải bảo đảm rằng mọi mutation từng bị bỏ lỡ đều có hint**, không thay thế repair và không tự bảo vệ các bất biến nghiệp vụ xuyên nhiều bản ghi.

## 2. Các khái niệm trước khi tìm hiểu chi tiết

### 2.1. Replica và replication factor

**Replica** là node giữ một bản sao dữ liệu của partition. **Replication factor** là số bản sao được bố trí theo chiến lược replication. RF=3 không có nghĩa tất cả ba node luôn online hoặc mọi write được lưu tức thời trên ba node.

### 2.2. Coordinator

Trong Cassandra, **coordinator** là node nhận request từ client, xác định replicas cần thao tác, gửi mutation, theo dõi các phản hồi và quyết định khi nào request đạt mức consistency yêu cầu. Một node làm coordinator **không nhất thiết là natural replica** của partition mà request đang truy cập.

### 2.3. Mutation

**Mutation** là thay đổi ở tầng lưu trữ: insert, update, delete hoặc một thay đổi khác theo semantics engine. Một lệnh DELETE có thể tạo **tombstone** thay vì xóa vật lý ngay. Mutation còn có metadata để hệ thống giải quyết phiên bản như write timestamp và TTL khi phù hợp.

### 2.4. Consistency level

**Consistency level (CL)** của Cassandra quyết định yêu cầu số/phạm vi phản hồi cần thiết để một read hoặc write được xác nhận. Các mức quen thuộc: `ONE`, `QUORUM`, `LOCAL_QUORUM`, `ALL` và mức `ANY` đặc biệt cho write; LWT còn có serial consistency.

CL nói về **điều kiện xác nhận một operation**. Nó không có nghĩa tất cả bản sao đã cùng trạng thái, cũng không tự biến nhiều write rời rạc thành một transaction ACID.

### 2.5. Hint và handoff

Một **hint** là bản ghi mutation dành cho replica không sẵn sàng. **Handoff** là quá trình gửi hint đó tới replica đích khi nó có thể nhận.

Một object khái niệm:

~~~json
{
  "destinationReplica": "C",
  "partitionKey": "K",
  "mutation": {
    "value": "v2",
    "writeTimestamp": 200
  },
  "recordedAt": "T2"
}
~~~

Đây là **JSON minh họa**, không phải định dạng file hint Cassandra thực tế. Dạng lưu trữ, serialization, metadata và vòng đời hints phụ thuộc phiên bản sản phẩm.

## 3. Dòng ghi khi một replica bị lỗi

Giả sử client dùng CL=QUORUM:

~~~text
              Client
                |
          WRITE K=v2
                |
                v
           Coordinator
          /      |      \
         v       v       v
       A         B        C
    WRITE v2  WRITE v2  UNREACHABLE
       |        |
      ACK      ACK
        \      /
         \    /
     QUORUM THÀNH CÔNG
            |
       Client success

Coordinator có thể giữ Hint(C, WRITE K=v2)
theo chính sách hinting và tình trạng tài nguyên.
~~~

Ở đây phải tách **bốn mốc**:

| Mốc | Ý nghĩa | Chưa thể kết luận |
|---|---|---|
| Write ACK | Đủ phản hồi theo CL được yêu cầu | Mọi replica đều có mutation |
| Hint stored | Có một bản mutation được giữ để thử giao lại | Replica đích đã áp dụng |
| Hint delivered | Mutation trong hint được chuyển/nhận theo giao thức | Mọi khác biệt lịch sử đã được xử lý |
| Replicas converged | Tập dữ liệu liên quan đã được đối soát/hội tụ | Các hệ phụ như search cũng đã bắt kịp |

**Node C được báo online không chứng minh handoff đã hoàn tất.** Nó có thể vừa trở lại, còn backlog lớn hoặc chưa nhận toàn bộ các mutation cần thiết.

## 4. Timeline đầy đủ của một lần gián đoạn ngắn

### 4.1. T0 — mọi nơi có cùng trạng thái

~~~text
A: Order O100 status=CREATED, timestamp=100
B: Order O100 status=CREATED, timestamp=100
C: Order O100 status=CREATED, timestamp=100
~~~

### 4.2. T1 — C tạm mất kết nối

Failure detection có thể xác định C không sẵn sàng. Trong thực tế, việc một node bị xem là down và thời điểm bắt đầu mất gói tin không nhất thiết trùng tuyệt đối.

### 4.3. T2 — khách ghi trạng thái PAID

~~~text
Client: UPDATE O100 SET status='PAID'
Write CL: QUORUM

A: PAID timestamp=200 -> ACK
B: PAID timestamp=200 -> ACK
C: vẫn CREATED vì offline
~~~

Coordinator có thể lưu một hint cho C nếu điều kiện tạo hint thỏa.

### 4.4. T3 — nhiều thay đổi tiếp tục xảy ra

~~~text
Order O100: PAID -> PACKED
Order O101: CREATED -> CANCELLED
Order O102: INSERT mới
User U42:   DELETE một record
~~~

Những mutation bị C bỏ lỡ **có thể** được ghi dưới dạng hints. Nhưng không được khẳng định toàn bộ chúng đều có hint trước khi kiểm tra cửa sổ thời gian, cấu hình và trạng thái coordinator.

### 4.5. T4 — C trở lại

C có thể nhận lại những hints được giữ cho nó. Replica áp dụng mutation theo quy tắc reconciliation của Cassandra; không đơn giản “mutation đến cuối luôn thắng”.

### 4.6. T5 — C cần được xác minh đã hội tụ

Sau khi handoff hết backlog được ghi nhận, hệ vẫn có thể thiếu mutation không được hint, hoặc những lệch dữ liệu từ trước. Vì vậy cần **anti-entropy repair theo lịch/quy trình phù hợp**, thay vì chỉ nhìn dashboard “pending hints = 0”.

## 5. Lợi ích chính của hinted handoff

**Phục hồi nhanh sau lỗi tạm thời.** Một node restart hoặc mất kết nối ngắn có thể nhận mutation bị bỏ lỡ mà không cần quét lại toàn bộ dữ liệu ngay lập tức.

**Giảm độ lệch giữa replica.** Những bản sao vắng trong một phần write workload có thể bắt kịp các thay đổi đã được lưu hint.

**Không phụ thuộc vào request đọc của người dùng.** Một partition hiếm khi được truy vấn vẫn có thể nhận mutation qua handoff, thay vì chỉ chờ cơ chế read-triggered repair.

**Bổ sung cho quorum-based availability.** Khi CL cho phép write tiếp tục với một số replica đang lỗi, hinted handoff giúp việc hội tụ sau sự cố trở nên thuận lợi hơn.

**Giảm công việc đối soát toàn bộ trong trường hợp thuận lợi.** Nếu replica chỉ vắng vài phút, chuyển lại số mutation cụ thể có thể rẻ hơn sửa toàn bộ một tập dữ liệu rất lớn.

Tuy nhiên, mỗi lợi ích đều có điều kiện: phải có coordinator lưu được hint, node đích quay lại phù hợp, hints chưa bị mất, và không có bất đồng ngoài phạm vi hints.

## 6. Hinted handoff là best effort — giới hạn quan trọng nhất

Hints không phải một nhật ký đầy đủ, bất biến và đảm bảo lưu trữ mọi mutation của cluster. Có những trường hợp khiến replica thiếu dữ liệu dù không còn hint nào đang chờ:

1. Replica đích offline lâu hơn thời gian cho phép tạo hints.
2. Coordinator không tạo hint vì cấu hình hoặc tình huống vận hành.
3. Coordinator bị crash, hỏng đĩa hoặc mất một phần dữ liệu hints.
4. Disk full/I/O lỗi khiến hint không được lưu như mong đợi.
5. Request chưa từng được xử lý thành công tại nơi có thể tạo hint.
6. Những mutation đặc biệt đi qua đường xử lý khác với write thường.
7. Hints bị dừng, không chuyển được, hoặc kết thúc không đầy đủ.
8. Replica có dữ liệu sai từ một sự cố cũ không liên quan downtime mới.
9. Cluster thay topology, node đã replace, hoặc vùng đích thay đổi.
10. Một read model bên ngoài chưa nhận event dù replica Cassandra đã hội tụ.

Do đó, **hinted handoff là cơ chế hỗ trợ phục hồi**, không phải một giải pháp thay thế cho repair, backup/restore và quản trị dữ liệu.

## 7. Giới hạn thời gian: max_hint_window_in_ms

Trong các bản phát hành Apache Cassandra có tham số `max_hint_window_in_ms`, tham số này liên quan đến **khoảng thời gian một node đích được coi là down mà coordinator còn tiếp tục tạo hints dành cho nó**.

Ví dụ cấu hình minh họa:

~~~yaml
hinted_handoff_enabled: true
max_hint_window_in_ms: 10800000
~~~

`10.800.000 ms` tương đương **3 giờ**. Đây là con số minh họa để giải thích, không phải đề xuất cấu hình mặc định cho mọi phiên bản/cluster.

### 7.1. Dòng thời gian

~~~text
T0           T0 + 1 giờ      T0 + 3 giờ          T0 + 8 giờ
|----------------|---------------|-------------------|
 C down          có thể tạo      quá cửa sổ:
                 hints           không mặc định có
                                 hint cho mọi write mới
~~~

Hệ giới hạn hinting để tránh lưu vô hạn mutation cho một node không quay lại.

### 7.2. Không nhầm cửa sổ tạo hint với TTL của hint

Cần tách:

- Đến khi nào coordinator **tạo hint mới** cho target;
- Hint đã tạo được **lưu và quản lý** ra sao;
- Khi nào hint được **chuyển**;
- Khi nào file hint được **thu hồi/cleanup**.

Không nên hiểu máy móc “đủ 3 giờ, tất cả hint cũ đồng loạt biến mất”.

### 7.3. Khi downtime vượt cửa sổ

Nếu node vắng 20 giờ trong khi policy tạo hint chỉ trong vài giờ, một số mutation sau cửa sổ **có thể không có hint**. Khi node quay lại, không nên chỉ đợi handoff: cần đánh giá **repair/rebuild hoặc replacement** theo runbook.

### 7.4. Vì sao không tăng cửa sổ lên 30 ngày?

Một node vắng dài ngày có thể tích lũy nhiều terabyte hints. Tăng cửa sổ quá mức có thể:

- Làm hết đĩa của các node đang khỏe;
- Tăng I/O và latency writes;
- Kéo dài thời gian replay;
- Cạnh tranh băng thông replication;
- Khiến recovery của một node gây lỗi cho nhiều node khác.

Giải pháp cho downtime dài thường là **quy trình phục hồi dữ liệu có kiểm soát**, không phải bảo đảm bằng dung lượng hint vô hạn.

## 8. So sánh CL=ONE, QUORUM, ALL và ANY

### 8.1. ONE

Với RF=3, write có thể thành công khi một replica phù hợp ACK theo semantics CL=ONE. Những replica khác vẫn có thể chưa nhận mutation.

~~~text
A ACK v2
B unreachable
C unreachable

ONE: có thể ACK nếu A là replica phù hợp
~~~

Hints có thể giúp B/C bắt kịp, nhưng không tự làm read CL=ONE ở mọi node mới nhất.

### 8.2. QUORUM

Trong RF=3 đơn giản, cần hai replica theo quy tắc quorum:

~~~text
A ACK
B ACK
C offline

QUORUM: có thể ACK
C vẫn còn dữ liệu cũ
~~~

**QUORUM không có nghĩa cả ba replica đã nhận dữ liệu.**

### 8.3. ALL

CL=ALL yêu cầu phản hồi của toàn bộ các replica thuộc phạm vi. Nếu C offline và không ACK, A/B ACK cùng một hint lưu cho C **không thay thế** ACK của C để đạt ALL.

### 8.4. ANY — trường hợp đặc biệt

Cassandra có `ANY` cho **write**, với semantics cho phép một write được xác nhận khi mutation được giữ dưới dạng **hint** thích hợp, ngay cả trong một tình huống các natural replicas của partition chưa nhận mutation.

~~~text
                    Coordinator H (alive)
                         |
                    write request
                         |
        A unavailable, B unavailable, C unavailable
                         |
                    Hint persisted
                         |
                CL=ANY có thể ACK
~~~

Tình huống này đòi hỏi coordinator còn hoạt động và thật sự lưu hint theo điều kiện hỗ trợ. Không có nghĩa “cluster chết hoàn toàn mà vẫn ghi được”.

**Rủi ro:** mutation được ACK bởi hint có thể **chưa nằm trên natural replica**. Nếu hint holder mất dữ liệu trước handoff, write có thể không phục hồi được.

`ANY` **không dùng cho read**.

### 8.5. Bảng tổng hợp

| Write CL | Ví dụ điều kiện với RF=3 | Hints có thay ACK thiếu? | Điều cần nhớ |
|---|---|---|---|
| ONE | Một replica ACK | Không cần nếu đã đủ | Các replica khác có thể stale |
| QUORUM | Hai replica ACK | Không | Handoff không đồng nghĩa mọi replica đã bắt kịp |
| ALL | Ba replica ACK | Không | Node down có thể khiến write không khả dụng |
| ANY | Một xác nhận đủ theo semantics write; có trường hợp dựa hint | Có trong trường hợp đặc biệt của ANY | Mutation có thể chưa trên natural replica |
| LOCAL_QUORUM | Quorum trong local DC | Không thay local quorum ACK | Remote DC có thể chưa đồng bộ |
| SERIAL/LOCAL_SERIAL | Gắn với LWT/serial agreement | Không phải “hint thay Paxos” | Có giao thức đồng thuận riêng |

Các quy tắc chi tiết phụ thuộc replication strategy, phiên bản và topology. Đừng áp con số quorum đơn giản cho mọi cấu hình multi-DC.

## 9. Quorum không tự làm replica hội tụ

Một heuristic thường gặp:

\[
R + W > RF
\]

Với RF=3, read quorum R=2 và write quorum W=2 sẽ có tập replica giao nhau trong mô hình đơn giản.

~~~text
Write acknowledged by: {A, B}
Read from:             {B, C}
Intersection:          {B}
~~~

Sự giao nhau có ích cho việc tìm thấy mutation mới, nhưng **không tự bảo đảm toàn hệ linearizable trong mọi tình huống**: còn có concurrent writes, timestamp reconciliation, tombstones, read path, failover và semantics sản phẩm.

Ngoài ra, C vẫn có thể giữ v1 trong khi A/B là v2. Quorum xác định điều kiện xác nhận, **không bắt mọi replica lập tức giống nhau**.

## 10. Đọc khi hinted handoff chưa xong

Giả sử:

~~~text
A = v2
B = v2
C = v1
~~~

Một `READ CL=ONE` có thể trả v1 nếu đường đọc tới C trong điều kiện cho phép. Với read quorum, quá trình reconciliation có thể tìm trạng thái mới hơn trong phạm vi các replica tham gia, nhưng không được mặc định mọi trường hợp đều tuyến tính hóa mạnh.

Nếu một UI yêu cầu **read-your-writes**, phải chọn consistency/route/session protocol thích hợp. Không thể dựa vào giả định “hints sẽ giao xong trước lần GET tiếp theo”.

Nếu ứng dụng đọc qua Redis cache hoặc search index, chúng còn có **pipeline và freshness contract riêng**.

## 11. Hinted handoff khác anti-entropy repair như thế nào?

### 11.1. Hint: “Tôi còn nhớ mutation bạn bỏ lỡ”

~~~text
A nhận WRITE K=v2
C down
A lưu Hint(K=v2, target=C)
C up
A chuyển Hint -> C
~~~

Cơ chế biết **mutation cụ thể** đã được lưu.

### 11.2. Repair: “Chúng ta hãy so trạng thái thực”

~~~text
Replica A       Replica B       Replica C
    |                |                |
    +------ so sánh dữ liệu ----------+
                     |
              phát hiện lệch
                     |
             truyền dữ liệu cần
                     |
                 hội tụ
~~~

Anti-entropy repair so sánh và xử lý khác biệt trong phạm vi dữ liệu/replicas được repair, **không cần có một hint cho mỗi mutation**.

### 11.3. Vì sao hints hết vẫn còn khác biệt?

Nếu coordinator đã mất một hint, dashboard có thể hiển thị `pending=0` dù replica đích vẫn thiếu mutation. Repair có thể phát hiện lệch mà hinted handoff không còn nhớ.

### 11.4. Vì sao repair vẫn phải lên lịch?

- Không phải mọi node downtime ngắn.
- Hint creation có thời hạn.
- Node giữ hint có thể chết.
- Có sai lệch lịch sử không được hint.
- Một node mới/replacement có thể cần dữ liệu đầy đủ.
- Không phải mọi partition được đọc để kích hoạt read-triggered repair.

**Hints bổ sung repair, không thay repair.**

## 12. So sánh hints, read repair, anti-entropy và rebuild

| Cơ chế | Kích hoạt | Giải quyết | Không bảo đảm |
|---|---|---|---|
| Hinted handoff | Coordinator ghi nhớ mutation bỏ lỡ; target quay lại | Phát lại những mutation đã lưu hints | Phát hiện mọi khác biệt dữ liệu |
| Read repair | Một đường đọc phát hiện bất đồng theo semantics hỗ trợ | Sửa một số khác biệt trong read path | Quét mọi partition/replica |
| Anti-entropy repair | Quy trình đối chiếu chủ động | Hội tụ những phạm vi được so sánh | Sửa sai nghiệp vụ do timestamp/bất biến |
| Rebuild/replace | Node mất dữ liệu hoặc quá cũ | Tạo lại dữ liệu từ nguồn được chọn | Chọn đúng nguồn nếu cluster đã sai sẵn |
| CDC/outbox replay | Đồng bộ nguồn sang read model khác | Cập nhật search/analytics/cache | Sửa toàn bộ replicas Cassandra |

Một hệ tốt dùng các cơ chế như **những lớp bổ sung nhau**, không coi một cơ chế duy nhất là bảo đảm tuyệt đối.

## 13. Read repair khác repair theo lịch

Trong một số phiên bản/đường đọc Cassandra, read repair giúp xử lý khác biệt mà truy vấn phát hiện. Nhưng nếu người dùng **không bao giờ đọc** partition K, không có lý do để tin K đã được sửa chỉ nhờ read repair.

Anti-entropy repair có thể chủ động bao phủ keyspace/table/token ranges cần thiết. Do đó:

- Chọn phạm vi repair đầy đủ.
- Ghi nhận lần **hoàn tất thành công**.
- Không coi job “đã được schedule” là đã sửa dữ liệu.
- Theo dõi ranges thất bại và sửa bù.
- Xem lại workload nếu repair quá nặng.

Cơ chế read repair và tùy chọn liên quan thay đổi theo Cassandra version; tài liệu production phải bám đúng phiên bản.

## 14. Hinted handoff không phải batchlog

Trong Cassandra, `LOGGED BATCH` có cơ chế **batchlog** riêng cho quá trình phân phối các mutation thuộc batch trong những tình huống lỗi.

Hinted handoff phục vụ **replica bị bỏ lỡ mutation**.

Ví dụ:

- “Một logged batch có nhiều mutation và coordinator lỗi giữa chừng, batch tiếp tục thế nào?” → xem batchlog/batch semantics.
- “Replica C offline 20 phút khi cluster tiếp tục ghi, C bắt kịp thế nào?” → xem hinted handoff và repair.

Một logged batch nhiều partition **không tự tạo ACID transaction có isolation tương đương cơ sở dữ liệu quan hệ**, và batchlog cũng không thay anti-entropy repair.

## 15. Hinted handoff không phải CDC hoặc event streaming

Một kiến trúc NoSQL thường có:

~~~text
                 Cassandra
                   |
          +--------+-----------+
          |                    |
          v                    v
    Replica protocol      CDC / Outbox
    + hinted handoff           |
          |                    +--> Search index
      Other replicas           +--> Analytics
                               +--> Vector store
                               +--> Cache projector
~~~

Hints dành cho replicas Cassandra; CDC/outbox chuyển thay đổi tới **hệ dẫn xuất**.

Nếu Elasticsearch thiếu document nhưng các replica Cassandra đã có, không nên mặc định sửa bằng `nodetool repair`. Cần điều tra event pipeline, projector, version guard, search refresh và reconciliation.

## 16. Dung lượng hints và áp lực vận hành

Một coordinator có thể phải lưu nhiều hints khi replica down. Nếu tốc độ tạo hints trung bình là `r` MiB/s và downtime `t` giây:

\[
backlog_{\text{MiB}} \approx r \times t
\]

Ví dụ:

~~~text
Hint rate:       6 MiB/s
Downtime:        40 phút = 2.400 giây

Backlog thô:     6 * 2400 = 14.400 MiB
                 xấp xỉ 14,1 GiB
~~~

Đây chỉ là ước lượng: serialization, compression, số coordinator, số replica down, policy hinting và thời gian cửa sổ ảnh hưởng dung lượng thực.

### 16.1. Chi phí khi tạo hint

- Ghi disk/buffer trên coordinator;
- CPU serialization;
- Tăng I/O wait;
- Ảnh hưởng write latency;
- Dùng phần dung lượng mà node khỏe cần cho dữ liệu/compaction.

### 16.2. Chi phí khi giao lại

- Dùng network bandwidth;
- Replica đích phải xử lý thêm writes cũ;
- Compaction/flush tăng tải;
- Backlog có thể mất nhiều giờ để hoàn tất;
- New traffic cạnh tranh tài nguyên với replay.

### 16.3. Throttle không phải lỗi

Giới hạn tốc độ handoff có thể cần để tránh node vừa hồi phục bị đánh sập một lần nữa. Nhưng nếu tốc độ quá thấp, replica có thể stale lâu. Cần capacity planning thay vì chỉ tăng hoặc giảm throttle theo cảm tính.

## 17. Coordinator giữ hint cũng có thể chết

Một kịch bản nguy hiểm:

~~~text
T0: C offline
T1: A lưu Hint(K=v2, target=C)
T2: A hỏng disk trước khi chuyển hint
T3: C quay lại nhưng không có hint v2
~~~

Nếu B hoặc replica khác vẫn có v2, repair có thể giúp C hội tụ. Nhưng nếu write chỉ được ACK theo `ANY` nhờ hint trên A, mutation có thể **chưa nằm ở natural replica nào**.

Không được hiểu hinted handoff là một bản sao bền vững tương đương RF đã cấu hình.

Cần quan sát:

- Hints disk free;
- Tình trạng node giữ hints;
- Các lỗi ghi/lưu/replay;
- CL của request quan trọng;
- Tình trạng dữ liệu ở những natural replicas;
- Phương án phục hồi khi coordinator mất hints.

## 18. Tombstone và nguy cơ dữ liệu đã xóa xuất hiện lại

Trong Cassandra, DELETE hoặc TTL hết hạn có thể được biểu diễn bằng **tombstone**, mang thông tin xóa và timestamp để che những giá trị cũ.

### 18.1. Tình huống đúng

~~~text
A: K -> TOMBSTONE timestamp=200
B: K -> TOMBSTONE timestamp=200
C: K -> VALUE=v1 timestamp=100 (offline)
~~~

Nếu C trở lại khi tombstone vẫn tồn tại và repair/handoff được thực hiện đúng, dữ liệu v1 có thể bị tombstone mới hơn che.

### 18.2. Khi bằng chứng xóa đã mất

Giả sử C offline quá lâu. A/B đã thực sự purge tombstone theo điều kiện compaction:

~~~text
A: không có value sống, không còn tombstone 200
B: không có value sống, không còn tombstone 200
C: vẫn có K=v1 timestamp=100
~~~

Khi C tái nhập và tham gia reconciliation, trong một số điều kiện giá trị cũ `v1` có thể được chấp nhận trở lại. Hiện tượng này gọi là **zombie data**.

### 18.3. gc_grace_seconds

`gc_grace_seconds` trong Cassandra là tham số theo table liên quan tới khoảng thời gian tombstone cần được giữ trước khi có thể đủ điều kiện thu gom.

~~~sql
CREATE TABLE orders_by_id (
    order_id text PRIMARY KEY,
    status text
) WITH gc_grace_seconds = 864000;
~~~

`864000` giây là 10 ngày, chỉ dùng để minh họa. Không phải cấu hình tối ưu cho mọi hệ.

**Hết grace không đồng nghĩa tombstone biến mất đúng giờ**, vì còn điều kiện compaction và an toàn khác. Grace cũng không tự chạy repair.

### 18.4. Quan hệ giữa hint window và grace

| Chính sách | Mục đích |
|---|---|
| Hint window | Giới hạn thời gian tạo hints cho replica down |
| Handoff | Giao lại những mutation đã lưu |
| Repair cadence | Đảm bảo dữ liệu được đối soát định kỳ |
| Tombstone grace | Giữ bằng chứng xóa đủ lâu theo policy |
| Rebuild/replace | Xử lý node quá cũ/không đáng tin |

**Không được chọn một trong các cơ chế rồi bỏ qua những cơ chế còn lại.**

## 19. TTL và replay có đúng thời gian hết hạn không?

Ví dụ:

~~~sql
INSERT INTO sessions_by_id (
    session_id, user_id, state
)
VALUES ('S100', 'U42', 'ACTIVE')
USING TTL 3600;
~~~

Nếu session có TTL một giờ tại thời điểm ghi, rồi node C offline ba giờ mới nhận hint, engine phải xử lý mutation theo **metadata và semantics TTL ban đầu**, không được hiểu hint đơn giản như client chạy lại một lệnh INSERT mới với một giờ TTL kể từ khi C hồi phục.

Tuy nhiên, khi ứng dụng tự xây **event replay** ngoài database, nó có thể mắc lỗi:

~~~text
T0: Event INSERT with TTL=3600
T3: Replayer gọi INSERT with TTL=3600 lần mới
~~~

Điều này có thể vô tình kéo dài session nếu TTL tương đối được tính lại.

**Phải phân biệt native hinted handoff của storage engine với replay ở tầng ứng dụng.** Một số loại mutation đặc biệt như counters, LWT hoặc tính năng cụ thể có semantics riêng, cần đối chiếu phiên bản thay vì suy từ insert thường.

## 20. Timestamp và thứ tự mutation

Giả sử:

~~~text
T0: K=v1 timestamp=100
T1: C offline
T2: K=v2 timestamp=200 -> hint
T3: C có K=v3 timestamp=300 từ write khác
T4: Hint cũ K=v2 timestamp=200 được replay
~~~

Không nên kết luận “hint đến sau nên v2 chắc chắn thắng”. Cassandra dùng timestamp và reconciliation rules để quyết định mutation có hiệu lực.

### 20.1. Clock skew

Nếu các writer tự cấp timestamp sai, một mutation cũ có timestamp tương lai có thể che giá trị mới. Hinted handoff chỉ vận chuyển mutation theo metadata, **không tự sửa clock skew**.

### 20.2. Tái tạo dữ liệu khác zombie data

Một business write mới có timestamp lớn hơn tombstone có thể cố tình tạo lại key. Điều đó khác với replica cũ đưa lại dữ liệu đã xóa vì tombstone bị purge.

### 20.3. Replay thành công chưa đủ để khẳng định nghiệp vụ đúng

Nếu hai vùng đã tạo những writes xung đột không được business protocol bảo vệ, việc replay đầy đủ vẫn có thể dẫn tới trạng thái sai về quota, inventory hoặc quyền sở hữu.

## 21. LWT không thể được thay bằng hints

Cassandra có **Lightweight Transactions (LWT)** qua CQL `IF`, sử dụng giao thức đồng thuận để thực hiện conditional mutation.

~~~sql
CREATE TABLE reservation_by_id (
    reservation_id text PRIMARY KEY,
    state text,
    version bigint
);

UPDATE reservation_by_id
SET state = 'CONFIRMED',
    version = 8
WHERE reservation_id = 'R100'
IF state = 'PENDING' AND version = 7;
~~~

Một LWT phải thỏa điều kiện/giao thức serial consistency tương ứng. Một hint nằm ở coordinator **không tự chứng minh phép CAS đã được đồng thuận và commit**.

Tương tự, hai writes thường dùng CL=QUORUM **không thay thế** atomic compare-and-write khi hai khách cùng tranh một tài nguyên.

### 21.1. Ví dụ overselling

Ứng dụng làm:

~~~text
A READ inventory.available=1
B READ inventory.available=1

A WRITE inventory.available=0, QUORUM
B WRITE inventory.available=0, QUORUM
~~~

Cả hai khách có thể được báo “đặt thành công” dù chỉ có một sản phẩm. Hinted handoff đầy đủ cũng không sửa lỗi kiểm tra điều kiện ở ứng dụng.

Cần CAS/transaction/authority để giữ bất biến.

## 22. Multi-data-center: LOCAL_QUORUM không đảm bảo DC xa đã nhận

Giả sử cluster có hai DC:

~~~text
DC East                   DC West
A1 A2 A3                  B1 B2 B3
RF=3                      RF=3
    \                      /
      --- Replication ----
~~~

Một write từ East đạt `LOCAL_QUORUM` có thể được xác nhận bởi quorum trong East ngay cả khi West đang trễ hoặc mất kết nối.

### 22.1. Hints xuyên DC tùy cấu hình

Hinted handoff có thể được bật/tắt hoặc giới hạn cho những data centers cụ thể, tùy phiên bản và cấu hình. Không được mặc định coordinator ở East **luôn giữ hints đầy đủ** cho toàn bộ replica West.

### 22.2. DC bị ngắt kết nối nhiều ngày

- Hints có thể không còn được tạo sau cửa sổ.
- Một số replica West tiếp tục có giá trị cũ.
- Nếu West nhận writes cục bộ, có thể phát sinh xung đột.
- Khi mạng hồi phục, repair/streaming và conflict analysis có thể cần thiết.

### 22.3. Handoff không quyết định winner theo nghiệp vụ

Nếu East xác nhận owner=A và West xác nhận owner=B cho cùng ghế khi bị chia cắt, replay mutation theo timestamp **không thể đảo ngược thực tế hai khách đã được báo thành công**.

Để ngăn vi phạm uniqueness hoặc inventory, cần một authority, một giao thức consensus/transaction phù hợp hoặc phân bổ quyền bán trước theo region.

## 23. Khi đổi topology hoặc replacement node

Hints đã lưu cho một replica đích không phải cơ chế bootstrap hoàn chỉnh cho node mới. Khi thêm/bớt node, đổi RF hoặc thay topology:

- Natural replicas của partition có thể đổi.
- Node mới phải được nhận dữ liệu qua streaming/rebuild/repair theo quy trình.
- Hints cho endpoint cũ không tự đảm bảo node mới có toàn bộ dữ liệu.
- Node cũ quay lại sau khi đã bị replace có thể mang dữ liệu stale/metadata không phù hợp.

Không nên “bật lại node cũ” như một bước vô hại khi node ấy đã bị loại khỏi topology hoặc vắng quá lâu.

## 24. Khi nào repair hoặc rebuild phù hợp hơn handoff?

| Tình huống | Hướng xử lý cần xem xét |
|---|---|
| Node restart vài phút, hints backlog nhỏ | Theo dõi handoff và tình trạng node |
| Node offline thời gian vừa phải | Theo dõi hints, thực hiện repair theo lịch/runbook |
| Downtime vượt hint window | Không tin hints là đủ; repair hoặc rebuild/replace |
| Node offline vượt cửa sổ an toàn tombstone | Cô lập và đánh giá dữ liệu cũ; thường cần quy trình rebuild/replace |
| Node mất data disk | Rebuild/replacement từ nguồn tin cậy |
| DC partition kéo dài | Xem multi-DC topology, conflict, repair, streaming |
| Dữ liệu lệch dù không còn hints | Anti-entropy repair và điều tra |
| Search index thiếu document | CDC/projector/reindex, không dùng Cassandra hints |

Việc chọn repair hoặc rebuild phụ thuộc mức độ tin cậy của các replica nguồn. Nếu cluster đã mang dữ liệu sai, **repair thành công về kỹ thuật có thể lan truyền trạng thái sai**; khi ấy phải xác định nguồn chuẩn theo nghiệp vụ trước.

## 25. Repair cadence và tombstone safety

Một kế hoạch vận hành cần theo dõi ít nhất:

~~~text
Hint window:         thời gian replica được xem là hintable
Repair cadence:      khoảng cách giữa các lần repair hoàn tất
Tombstone grace:     chính sách giữ dấu xóa từng table
Downtime threshold:  khi nào node không được tái nhập theo cách thường
Recovery procedure:  repair / rebuild / replace
~~~

Lịch `repair mỗi tuần` không chứng minh cả cluster đã repair trong tuần nếu job:

- Thất bại;
- Chỉ chạy một số token ranges;
- Bỏ sót data center;
- Có node vắng mặt;
- Chưa hoàn tất;
- Không bao phủ keyspace/table có DELETE.

Cần ghi nhận **last successful completion theo phạm vi cần thiết**. Repair schedule nên có biên an toàn so với grace, không dồn sát mốc rồi hy vọng lần nào cũng xong.

## 26. Đối chiếu chi phí replay và tải mới

Giả sử một node có backlog 24 GiB, replay ổn định 8 MiB/s và tạm bỏ qua traffic mới:

\[
24 \times 1024 = 24576 \ \text{MiB}
\]

\[
replayTime = \frac{24576}{8} = 3072 \ \text{giây}
\]

Tức khoảng **51,2 phút** trong mô hình lý tưởng.

Nhưng thực tế:

- Replay không phải lúc nào cũng đạt tốc độ cố định;
- Node đích còn nhận writes mới;
- Compaction đang chạy;
- Disk/network có giới hạn;
- Retry hoặc backoff làm chậm;
- Có nhiều coordinator cùng giao hints;
- Sau handoff còn có repair.

Vì vậy không dùng phép chia thô để hứa một SLA hoàn tất.

## 27. Monitoring cần gì ngoài “node đã UP”?

| Nhóm | Quan sát | Mục đích |
|---|---|---|
| Node health | Down/up, downtime duration | Xác định replica bỏ lỡ bao lâu |
| Hint generation | Hints created, bytes, target | Biết backlog có đang tăng |
| Hint backlog | Pending hints, tuổi hint cũ nhất | Theo dõi nguy cơ kéo dài |
| Delivery | Hints delivered, failed, retries | Biết handoff có tiến triển |
| Hints storage | Hints directory disk usage/free space | Tránh disk full |
| Network | Throughput, retransmit, WAN loss | Phát hiện nghẽn replay |
| Target capacity | Disk I/O, CPU, read/write p99 | Tránh quá tải node vừa phục hồi |
| Compaction | Pending tasks, duration | Theo dõi hậu quả của replay |
| Repair | Last successful repair, incomplete ranges | Bảo đảm không bỏ sót sai lệch |
| Tombstone | Grace, node downtime, purge/repair risk | Đánh giá zombie data |
| Application | Stale reads, unknown writes, business mismatch | Đo ảnh hưởng thực tế |

Cấu trúc metric qua JMX/Prometheus/logs tùy phiên bản, không nên giả định tên metric giống nhau ở mọi Cassandra hoặc ScyllaDB.

### 27.1. Pending hints = 0 có nhiều cách giải thích

Backlog bằng 0 có thể vì:

- Hints đã được giao hết;
- Không có hint nào được tạo;
- Node vắng quá hint window;
- Hinting bị tắt;
- Có cleanup/lỗi khác;
- Hints bị mất do hỏng disk.

Do vậy phải kết hợp **delivery outcomes, node downtime và repair coverage**.

## 28. Công cụ vận hành Cassandra

Một số lệnh `nodetool` hữu ích để quan sát:

~~~bash
nodetool status
nodetool netstats
nodetool tablestats
nodetool compactionstats
~~~

Để repair một phạm vi dữ liệu, có thể gặp:

~~~bash
nodetool repair app_data orders_by_id
~~~

Những dòng trên chỉ **minh họa tên nhóm công cụ**, không phải runbook chạy production. Tùy phiên bản, command options, loại repair, scope node/DC/token range và output khác nhau. Repair có thể gây tải lớn.

Không chạy lệnh làm thay đổi cluster chỉ để thử nghiệm, và không thay hints window/TTL/grace trên production khi chưa đánh giá tác động.

## 29. Runbook khi replica trở lại sau outage

### Bước 1 — Xác định phạm vi

- Replica nào bị down?
- Từ khi nào?
- Một node hay cả DC?
- RF/CL của những request quan trọng?
- Có request `ANY` liên quan không?
- Những bảng có delete/TTL nào bị ảnh hưởng?

### Bước 2 — Đánh giá thời gian

So downtime với:

- Hint window;
- Lần repair hoàn tất;
- `gc_grace_seconds` từng table;
- Độ tuổi backup/snapshot;
- Thời gian phục hồi dự kiến.

### Bước 3 — Kiểm tra coordinator và resource

- Hints backlog/bytes ở các nơi có thể giữ;
- Disk usage và lỗi I/O;
- Network bandwidth;
- Tải node vừa phục hồi;
- Khả năng chạy repair sau handoff.

### Bước 4 — Quyết định khôi phục

- Downtime ngắn, dữ liệu còn an toàn: cho handoff theo runbook, theo dõi.
- Thiếu hint hoặc vượt cửa sổ: repair có chủ đích.
- Dữ liệu cũ có nguy cơ zombie: cân nhắc cô lập/rebuild/replace trước khi phục vụ.
- DC outage lớn: xem conflict/authority và multi-DC recovery.

### Bước 5 — Xác minh kết quả

- Handoff delivery đã hoàn tất chưa?
- Repair bao phủ đúng tables/ranges chưa?
- Có stale read hoặc mismatch theo nguồn không?
- Các tombstone vẫn bảo vệ dữ liệu xóa không?
- Application invariants còn đúng không?
- p99/disk/compaction đã trở về mức ổn định không?

### Bước 6 — Đóng sự cố

Ghi timeline, hậu quả, nguyên nhân, điều kiện giúp hoặc cản trở handoff, thời gian hồi phục và thay đổi runbook/capacity planning.

**Không đóng sự cố chỉ vì node status đã xanh.**

## 30. Các tình huống cần phân biệt với hinted handoff

### 30.1. Search index stale

Nếu search không thấy đơn mới nhưng Cassandra nguồn đã đúng, cần kiểm tra CDC/outbox, projector và refresh, không dùng hints làm chốt.

### 30.2. Read model nhận sự kiện sai thứ tự

Một projector nhận `DELETE version=12` trước `UPSERT version=11` có thể làm record xuất hiện lại nếu không có version guard. Đây là **application-level resurrection**, không nhất thiết do hint/repair.

### 30.3. Backup restore trước DELETE

Restore từ snapshot cũ có thể đưa dữ liệu đã xóa trở lại nếu không replay các mutation sau snapshot. Hinted handoff không tự đồng bộ mọi bản backup lịch sử.

### 30.4. Hai concurrent writes không có CAS

Hai client cùng tranh một username/slot nhưng chỉ dùng ordinary writes CL=QUORUM. Mutation được giao đầy đủ vẫn không chứng minh chỉ một client được xác nhận thành công. Phải dùng LWT/CAS/authority hoặc workflow thích hợp.

### 30.5. Clock skew

Một mutation có timestamp bất thường được chuyển lại đúng, nhưng kết quả reconciliation vẫn không phù hợp ý định nghiệp vụ. Handoff không sửa đồng hồ hoặc quy tắc conflict.

## 31. Kiểm thử bằng failure injection có kiểm soát

### 31.1. Node offline ngắn hạn

1. Tạo test cluster RF=3.
2. Ghi K=v1 và xác nhận trạng thái ban đầu.
3. Ngắt replica C khỏi write path.
4. Ghi K=v2 với CL=QUORUM.
5. Xác nhận client ACK và trạng thái A/B.
6. Cho C trở lại trong cửa sổ hinting.
7. Quan sát hints delivery.
8. Xác minh dữ liệu C hội tụ theo phương pháp test/repair phù hợp.

### 31.2. Node offline vượt cửa sổ

1. Trong test environment, cấu hình hint window phù hợp mô phỏng.
2. Cho C vắng quá cửa sổ.
3. Ghi mutations trước và sau thời hạn.
4. Khôi phục C.
5. Xác minh handoff không tự đảm bảo mọi mutation.
6. Dùng repair/rebuild test theo runbook.
7. So sánh kết quả dữ liệu.

### 31.3. Coordinator crash

Tạo tình huống coordinator giữ hints gặp lỗi trước delivery. Phân tích write CL nào đã ACK, natural replicas nào có dữ liệu và repair có thể phục hồi không.

### 31.4. DELETE và tombstone

C down trước DELETE, A/B nhận tombstone. Test khi C quay lại trong cửa sổ an toàn; sau đó mô phỏng điều kiện mất bằng chứng xóa chỉ trong môi trường cô lập. Không làm thử nghiệm destructive trên cluster thật.

### 31.5. Multi-DC partition

Ghi LOCAL_QUORUM ở East khi West unreachable; xác nhận West có thể stale, theo dõi repair khi WAN hồi phục, kiểm tra xung đột nếu West cũng nhận writes.

### 31.6. Tải replay

Tích lũy backlog test và đo:

- Read/write p95, p99;
- Disk I/O/CPU;
- Network;
- Compaction backlog;
- Thời gian handoff;
- Phần dữ liệu còn lệch sau handoff.

Một cơ chế khôi phục đúng dữ liệu nhưng đánh sập node vừa quay lại cũng là vấn đề cần xử lý.

## 32. Những ngộ nhận phổ biến

**“RF=3 nghĩa mọi write thành công đã nằm trên ba replica.”** Không. Phụ thuộc CL và tình trạng node.

**“QUORUM thành công nghĩa các bản sao đã đồng bộ.”** Không. Một replica có thể vẫn offline.

**“Hints xuất hiện tức là target đã nhận dữ liệu.”** Không. Hints có thể đang nằm trên coordinator.

**“Node online nghĩa replay hoàn tất.”** Không. Backlog vẫn có thể tồn tại.

**“Pending hints bằng 0 chứng minh data consistent.”** Không. Có thể có mutation không được hint.

**“Hints tồn tại vô hạn cho node down.”** Không. Có cửa sổ và giới hạn nguồn lực.

**“Tăng hint window thật dài thì không cần repair.”** Không. Vẫn có rủi ro mất hints, overload và sai lệch lịch sử.

**“Một hint thay được ACK cho CL=ALL.”** Không.

**“CL=ANY là write đã nằm trên natural replica.”** Không nhất thiết.

**“CL=ANY là durability tuyệt đối.”** Không. Hint holder cũng có thể hỏng.

**“Read repair sửa mọi key.”** Không, những key không được đọc có thể vẫn lệch.

**“Batchlog và hinted handoff là một.”** Không. Hai cơ chế có mục tiêu khác nhau.

**“Hinted handoff là CDC gửi dữ liệu sang Elasticsearch.”** Không.

**“Hết `gc_grace_seconds` tombstone tự biến mất đúng giờ.”** Không. Compaction và điều kiện purge còn quyết định.

**“Replica offline vượt grace cứ bật lên rồi chạy SELECT.”** Nguy hiểm nếu mang dữ liệu cũ và bằng chứng xóa đã bị purge.

**“Hint replay đến cuối thì dữ liệu cũ phải thắng.”** Không. Reconciliation xét metadata/timestamp.

**“LOCAL_QUORUM ở A nghĩa B đã bắt kịp.”** Không. Phạm vi CL là local DC.

**“Replay đầy đủ giải quyết tranh chấp hai region.”** Không. Conflict ở nghiệp vụ cần authority/transaction.

**“Hinted handoff thay thế LWT.”** Không. Hints không thể thay phép so sánh–ghi nguyên tử.

**“Write CL cao biến hai item thành transaction.”** Không. CL không tự bao phủ multi-item invariant.

## 33. Bài tập thực hành

### Bài tập 1 — Quorum và replica vắng

RF=3, A/B ACK một write CL=QUORUM, C offline.

**Câu hỏi:** Client đã được ACK, C đã có write chưa?

**Gợi ý:** Không thể kết luận. C có thể còn cần handoff hoặc repair.

### Bài tập 2 — Read CL=ONE

A/B giữ v2, C giữ v1. Client đọc từ C theo CL=ONE.

**Câu hỏi:** Có thể nhận gì?

**Gợi ý:** v1 trong tình huống phù hợp, vì replica chưa hội tụ.

### Bài tập 3 — CL=ALL

A/B ACK, C offline, coordinator đã giữ hint C.

**Câu hỏi:** Có đạt ALL không?

**Gợi ý:** Không. Hint không thay ACK của C.

### Bài tập 4 — CL=ANY

Natural replicas không sẵn sàng, coordinator còn hoạt động và lưu được hint theo semantics ANY.

**Câu hỏi:** Write có thể được ACK không, và rủi ro là gì?

**Gợi ý:** Có thể; mutation chưa nằm trên natural replica, mất nơi giữ hint có thể làm mất mutation.

### Bài tập 5 — Hint window

Node offline 12 giờ, chính sách chỉ tạo hints khi down ngắn hơn vài giờ.

**Câu hỏi:** Đợi giao hết hints có đủ không?

**Gợi ý:** Không. Có thể có nhiều write không có hint, cần repair/rebuild.

### Bài tập 6 — Pending hints = 0

Dashboard báo không còn hints nhưng một replica vẫn trả giá trị cũ.

**Câu hỏi:** Mâu thuẫn không?

**Gợi ý:** Không. Hints không chứng minh đã bao phủ mọi mutation.

### Bài tập 7 — Hint holder crash

A giữ hint cho C rồi mất dữ liệu trước delivery. B đang giữ mutation mới.

**Câu hỏi:** Có đường phục hồi không?

**Gợi ý:** Có thể qua repair từ B, nếu dữ liệu trên nguồn còn đúng; không mặc định chắc chắn.

### Bài tập 8 — Hints và read repair

Một partition hiếm khi được đọc, replica C mất nhiều mutation.

**Câu hỏi:** Chỉ trông chờ read repair có ổn không?

**Gợi ý:** Không. Cần anti-entropy repair bao phủ phạm vi.

### Bài tập 9 — Hints và CDC

Search thiếu một order dù Cassandra đã thống nhất.

**Câu hỏi:** Điều tra gì?

**Gợi ý:** CDC/outbox, projector, index refresh, event ordering.

### Bài tập 10 — Tombstone

C giữ K=v1, A/B đã DELETE K và sau đó tombstone bị purge. C quay lại.

**Câu hỏi:** Rủi ro?

**Gợi ý:** Zombie data; cần runbook/rebuild/repair với đánh giá nguồn đúng.

### Bài tập 11 — TTL

Mutation session TTL một giờ được replay ba giờ sau.

**Câu hỏi:** Có nên cấp TTL mới một giờ từ lúc replay?

**Gợi ý:** Không nếu đó là replay mutation gốc; phải giữ semantics TTL/timestamp, không tái tạo session.

### Bài tập 12 — Timestamp

C có K=v3 timestamp=300; hint đến muộn chứa K=v2 timestamp=200.

**Câu hỏi:** v2 chắc chắn ghi đè v3 không?

**Gợi ý:** Không. Reconciliation dựa trên metadata/timestamp, không chỉ thứ tự đến.

### Bài tập 13 — LOCAL_QUORUM

East ghi LOCAL_QUORUM thành công khi West mất mạng.

**Câu hỏi:** West đã nhận dữ liệu chưa?

**Gợi ý:** Không thể suy từ quorum của East.

### Bài tập 14 — Backlog

Handoff có backlog 8 GiB và tốc độ replay lý tưởng 8 MiB/s.

**Câu hỏi:** Mất bao lâu?

**Gợi ý:** `8192/8=1024` giây, xấp xỉ 17,1 phút, chưa tính overhead.

### Bài tập 15 — Hints disk

Tốc độ tạo hints 10 MiB/s trong một giờ.

**Câu hỏi:** Dung lượng thô?

**Gợi ý:** `10×3600=36000` MiB, khoảng 35,2 GiB.

### Bài tập 16 — Node quá cũ

Node vắng 20 ngày, một số bảng có grace 10 ngày. Có khả năng tombstone đã bị purge.

**Câu hỏi:** Có nên tự động đưa node cũ vào phục vụ?

**Gợi ý:** Không. Cần đánh giá zombie risk và cân nhắc rebuild/replace.

### Bài tập 17 — LWT

Hai client tranh một reservation bằng `IF NOT EXISTS`.

**Câu hỏi:** Có thể dùng hint thay kết quả LWT không?

**Gợi ý:** Không. Cần serial consistency/consensus phù hợp.

### Bài tập 18 — Hai item

Inventory và Order ở hai partition, mỗi write đạt QUORUM; service chết sau update Inventory.

**Câu hỏi:** Hinted handoff có làm workflow atomic không?

**Gợi ý:** Không. Cần transaction hoặc saga/reservation có recovery.

### Bài tập 19 — Replay quá tải

Node hồi phục bị chậm do nhiều hints, read p99 tăng, compaction backlog kéo dài.

**Câu hỏi:** Điều chỉnh gì?

**Gợi ý:** Giám sát replay throughput, throttle, I/O, network, disk headroom và capacity.

### Bài tập 20 — Runbook

Một node offline qua cuối tuần, cluster có RF3 và nhiều bảng DELETE/TTL.

**Yêu cầu:** Nêu dữ liệu cần kiểm tra trước khi node nhập lại.

**Gợi ý:** Thời gian downtime, hint window, hints delivery, write CL, grace, repair history, topology, disk state, nguồn chuẩn và chiến lược rebuild.

### Bài tập 21 — Mất coordinator giữ hint

Một write CL=ANY được ACK bằng hint trên coordinator H, H mất toàn bộ disk trước khi replica đích phục hồi.

**Câu hỏi:** Bảo đảm nào có thể thất bại?

**Gợi ý:** Mutation có thể chưa tồn tại trên natural replicas; cần đánh giá durability/unknown data loss theo contract.

### Bài tập 22 — Bảo vệ ACL

Admin xóa quyền, replica một region chưa nhận mutation; user còn được phép truy cập do read từ bản cũ.

**Câu hỏi:** Hinted handoff đủ để đáp ứng yêu cầu thu hồi quyền tức thì không?

**Gợi ý:** Không. Cần authoritative permission check/revocation generation hoặc fail closed.

## 34. Checklist vận hành

- [ ] Biết đúng Cassandra/ScyllaDB version và tính năng hints được hỗ trợ.
- [ ] Biết RF, replica placement và topology DC.
- [ ] Biết read/write consistency level theo từng workload.
- [ ] Hiểu CL=ANY khác ONE/QUORUM/ALL và không dùng cho reads.
- [ ] Đã kiểm tra `hinted_handoff_enabled` và hint window thực.
- [ ] Hints storage có disk free và monitoring phù hợp.
- [ ] Có metric hint creation, backlog, delivery, failures.
- [ ] Theo dõi downtime từng replica và data center.
- [ ] Không coi node online là đã caught up.
- [ ] Có throttle/capacity cho hint replay.
- [ ] Có policy khi downtime vượt hint window.
- [ ] Có anti-entropy repair định kỳ, theo dõi hoàn tất thật.
- [ ] Có tombstone grace và quy trình xử lý zombie risk.
- [ ] Không dùng hints thay LWT, transaction hoặc uniqueness authority.
- [ ] Không dùng hints thay CDC/search index replay.
- [ ] Có runbook khi hint holder hỏng disk.
- [ ] Có kế hoạch rebuild/replace node quá cũ.
- [ ] Kiểm soát topology changes và multi-DC partition.
- [ ] Đã kiểm thử read consistency khi replica chưa bắt kịp.
- [ ] Đã kiểm thử node outage ngắn/dài, replay backlog.
- [ ] Có kiểm tra business invariants sau phục hồi.
- [ ] Không tuyên bố cluster hội tụ chỉ vì hints pending về 0.

## 35. Tổng kết

**Hinted handoff** cho phép coordinator ghi nhớ những mutation dành cho replica tạm unavailable và thử chuyển lại khi replica ấy phục hồi. Đây là cơ chế thực dụng giúp một cluster NoSQL phân tán phục hồi nhanh hơn sau các lỗi **ngắn hạn**, đặc biệt khi một số writes được xác nhận bởi quorum dù không phải mọi replica đều phản hồi.

Nhưng hinted handoff có giới hạn rõ ràng:

- Có **cửa sổ và chính sách tạo hints**, không bao phủ mọi downtime.
- Hints phải được lưu, giữ và giao lại; **node giữ hint cũng có thể hỏng**.
- Hints không phải nhật ký đầy đủ của mọi sai lệch; **anti-entropy repair vẫn cần**.
- CL=ONE/QUORUM/ALL/ANY có semantics khác nhau; **ANY** có tình huống ACK dựa trên hint nhưng dữ liệu chưa nằm trên natural replica.
- Hints không thay transaction, LWT, CDC, authority của nghiệp vụ, hoặc policy bảo vệ dữ liệu đã xóa.
- Nếu replica vắng quá lâu và tombstone đã bị purge, **dữ liệu cũ có nguy cơ hồi sinh** khi replica quay lại.

Một vận hành tin cậy phải kết hợp **replication, consistency level, hinted handoff, anti-entropy repair, tombstone grace, rebuild/replace runbook, monitoring và kiểm thử sự cố**.

**Nguyên tắc cuối cùng:** *hinted handoff giúp chuyển lại những gì coordinator còn nhớ; repair giúp kiểm tra và sửa cả những gì cluster có thể đã quên.* Không lấy “hints đã hết” làm bằng chứng “không còn replica nào sai lệch”.

