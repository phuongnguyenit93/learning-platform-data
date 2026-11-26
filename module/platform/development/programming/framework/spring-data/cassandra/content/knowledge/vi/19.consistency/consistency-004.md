# Kết hợp mức đọc và ghi theo yêu cầu quan sát dữ liệu trong Spring Data Cassandra

## 1. Bắt đầu từ câu hỏi nghiệp vụ, không phải tên consistency level

Giả sử ứng dụng Spring Boot dùng **Spring Data Cassandra** để lưu trạng thái đơn hàng. Sau khi người dùng nhấn **Thanh toán**, API ghi `state = 'PAID'` và thông báo thành công. Ngay sau đó, giao diện gọi API đọc lại đơn hàng.

Câu hỏi quan trọng là: **lần đọc tiếp theo có bắt buộc thấy trạng thái vừa ghi không?**

Hai màn hình có thể có yêu cầu hoàn toàn khác nhau:

- Trang chi tiết đơn hàng vừa cập nhật: người dùng kỳ vọng thấy **giá trị mình vừa lưu**.
- Bảng thống kê lượt xem: có thể chấp nhận giá trị **chậm vài giây** để đổi lấy độ trễ và tính sẵn sàng tốt hơn.

Trong **Apache Cassandra**, ta chọn **consistency level (CL)** cho **từng thao tác đọc hoặc ghi**. CL quyết định **bao nhiêu replica phải phản hồi thành công** trước khi coordinator báo kết quả. Vì vậy, khi thiết kế khả năng quan sát dữ liệu, không nên nói riêng “đọc ở `ONE`” hoặc “ghi ở `QUORUM`” mà cần xem **cặp mức đọc–ghi**, topology và tình huống concurrent writes.

Bài này thuộc chương **Tính nhất quán** của module **SPRING_DATA_CASSANDRA**. Phạm vi là cách kết hợp mức đọc và ghi trong ứng dụng sử dụng entity mapping, repository, `CassandraTemplate` và truy vấn CQL, đồng thời không quên thiết kế bảng theo truy vấn, partition key, paging và kiểm soát hiệu năng.

**Mục tiêu:**

1. Hiểu `replication factor`, replica, coordinator, `read CL`, `write CL` và quorum.
2. Giải thích điều kiện **`R + W > RF`** trong mô hình đơn giản với các replica cùng phạm vi.
3. Chọn cặp CL phù hợp yêu cầu **read-after-write**, dữ liệu có thể trễ, hoặc độ sẵn sàng khi node gặp sự cố.
4. Nhận biết rủi ro khi đọc và ghi ở **hai datacenter khác nhau** với `LOCAL_QUORUM`.
5. Phân biệt **đọc thấy lần ghi đã xác nhận** với **linearizability**, optimistic concurrency và LWT.
6. Cấu hình CL cho statement của Java driver, hiểu phạm vi kiểm soát trong Spring Data Cassandra.
7. Xử lý đúng timeout, kết quả chưa xác định, retry, TTL, tombstone và kiểm thử dưới lỗi replica.

## 2. Ba khái niệm cốt lõi: RF, coordinator và CL

### 2.1. Replication factor (RF)

**RF** cho biết bao nhiêu bản sao dữ liệu của mỗi partition được bố trí theo replication strategy của keyspace. Với một datacenter có `RF = 3`, mỗi partition thường có ba replica theo sơ đồ phân bố của cluster.

~~~mermaid
flowchart LR
    A[Client Spring Boot] --> B[Coordinator Cassandra]
    B --> C[Replica 1]
    B --> D[Replica 2]
    B --> E[Replica 3]
~~~

**RF không phải số node đang khỏe** và không phải số node ứng dụng đang kết nối. Cluster có thể có nhiều node hơn RF, nhưng một partition cụ thể được nhân bản theo chiến lược của keyspace.

### 2.2. Coordinator

Coordinator là node nhận request CQL từ driver và điều phối liên lạc đến các replica liên quan. Nó không nhất thiết là một trong những replica của partition. Việc chọn coordinator/route chịu ảnh hưởng của driver, token metadata và load balancing.

### 2.3. Consistency level

**Write CL** cho biết mức phản hồi cần đạt trước khi một thao tác ghi được coordinator báo thành công.

**Read CL** cho biết yêu cầu phản hồi cần đạt để coordinator hoàn tất một thao tác đọc.

Một ví dụ với RF = 3 trong **một datacenter**:

| CL | Số replica cần phản hồi theo mô hình cơ bản | Nhận xét |
| --- | ---: | --- |
| `ONE` | 1 | Ít replica bắt buộc phản hồi; có thể quan sát dữ liệu chưa cập nhật |
| `TWO` | 2 | Cần hai phản hồi |
| `THREE` | 3 | Cần ba phản hồi |
| `QUORUM` | 2 | Đa số trong RF = 3 |
| `ALL` | 3 | Không chấp nhận thiếu replica phản hồi |

Với **multi-datacenter**, cần phân biệt `QUORUM` toàn cục, `LOCAL_QUORUM` theo datacenter hiện tại, `EACH_QUORUM` cho write và các mức `LOCAL_ONE`, `ONE`. Những tên này không thể hoán đổi chỉ vì số replica tình cờ trùng nhau trong một ví dụ.

**Điểm then chốt:** CL là yêu cầu về **phản hồi của replica cho một request**, không phải mệnh đề “dữ liệu được khóa trong toàn hệ thống” hoặc “mọi request khác sẽ lập tức nhìn thấy cùng giá trị”.

## 3. Công thức quorum và giao nhau giữa tập đọc–ghi

### 3.1. Quorum của một nhóm replica

Với một nhóm có replication factor `RF`, ngưỡng đa số:

\[
Q = \left\lfloor \frac{RF}{2} \right\rfloor + 1
\]

| RF | Quorum Q | Nếu hai thao tác cùng đòi quorum, tổng R + W |
| ---: | ---: | ---: |
| 1 | 1 | 2 |
| 3 | 2 | 4 |
| 5 | 3 | 6 |

Trong **mô hình đơn giản một tập replica cố định**, để mọi tập replica đã xác nhận ghi (kích thước `W`) và mọi tập replica được dùng cho đọc (kích thước `R`) **bắt buộc giao nhau**, cần:

\[
\boxed{R + W > RF}
\]

Ví dụ RF = 3:

- Ghi `W = 2` và đọc `R = 2`: `2 + 2 = 4 > 3`, nên hai tập không thể hoàn toàn rời nhau.
- Ghi `W = 1` và đọc `R = 1`: `1 + 1 = 2 \le 3`, nên lần đọc có thể hỏi replica chưa nhận lần ghi mới.
- Ghi `W = 2` và đọc `R = 1`: `2 + 1 = 3`, **chưa đủ** để đảm bảo giao nhau.
- Ghi `W = 3` và đọc `R = 1`: `3 + 1 = 4 > 3`, có giao nhau nhưng write yêu cầu mọi replica trả lời.

~~~mermaid
flowchart TB
    A[RF = 3: replicas A, B, C] --> B[Write QUORUM: A + B xác nhận]
    A --> C[Read QUORUM: B + C phản hồi]
    B --> D[Replica B nằm trong cả hai tập]
    C --> D
    D --> E[Đọc có cơ hội quan sát lần ghi đã xác nhận]
~~~

### 3.2. Giới hạn của công thức

**`R + W > RF` là cách suy luận về giao nhau giữa các replica, không phải định lý bảo đảm mọi thao tác Cassandra đều linearizable.**

Công thức hữu ích khi:

1. Các thao tác liên quan **cùng partition/dữ liệu** và **cùng nhóm replica xét đến**.
2. Lần ghi đã **trả thành công** theo mức `W`.
3. Lần đọc sau đó hoàn tất theo mức `R` tương ứng.
4. Không có thay đổi bất thường như concurrent writes với timestamp xung đột, thay đổi topology chưa ổn định, hoặc trạng thái chưa rõ từ timeout.

Cassandra dùng timestamp và quy tắc hòa giải phiên bản để chọn giá trị. Một replica nằm trong cả hai tập giúp giao nhau về dữ liệu nhưng không có nghĩa ứng dụng được bảo đảm **một thứ tự thực thi tuyến tính cho mọi phép đọc/ghi**. Muốn bảo vệ điều kiện cạnh tranh kiểu “chỉ update nếu version vẫn là 7”, cần xem **LWT/CAS** ở phần sau.

## 4. Bảng đối chiếu các cặp R/W trong một datacenter RF = 3

Để so sánh, giả sử cả hai thao tác đều trên **một partition**, trong **cùng datacenter có RF = 3**, không có writer cạnh tranh và các replica hoạt động theo mô hình thông thường.

| Write CL | Read CL | W + R | Giao nhau bắt buộc? | Đánh đổi |
| --- | --- | ---: | --- | --- |
| `ONE` | `ONE` | 2 | **Không** | Độ trễ/độ sẵn sàng tốt hơn, có thể đọc phiên bản cũ |
| `ONE` | `QUORUM` | 3 | **Không** | Read tốn hơn nhưng chưa đủ điều kiện giao nhau |
| `QUORUM` | `ONE` | 3 | **Không** | Write đa số, một read vẫn có thể đến replica chậm |
| `QUORUM` | `QUORUM` | 4 | **Có** | Cân bằng phổ biến cho khả năng quan sát read-after-write trong cùng phạm vi |
| `ALL` | `ONE` | 4 | **Có** | Read rẻ hơn, write khó thành công khi thiếu replica |
| `ONE` | `ALL` | 4 | **Có** | Write dễ được xác nhận hơn, read mất tính sẵn sàng khi thiếu replica |
| `ALL` | `ALL` | 6 | **Có** | Yêu cầu nghiêm ngặt về phản hồi, chi phí/khả dụng cao |

Không có cặp mức nào “tốt nhất cho toàn bộ ứng dụng”. Một endpoint thống kê có thể chấp nhận trễ; endpoint “ghi rồi đọc ngay” có thể cần cặp quorum; endpoint ghi chống ghi đè cần **thêm LWT** chứ không chỉ nâng CL.

**Đặc biệt:** hai trường hợp `QUORUM + ONE` hoặc `ONE + QUORUM` có thể tình cờ trả giá trị mới trong thực tế, nhưng **không có bảo đảm giao nhau chỉ từ công thức**. Không thiết kế yêu cầu bắt buộc read-after-write dựa trên sự may mắn đó.

## 5. Yêu cầu thứ nhất: có thể chấp nhận đọc dữ liệu trễ

Ví dụ: bảng tổng hợp số lượt tương tác được cập nhật thường xuyên, UI hiển thị gần đúng và chấp nhận một độ trễ ngắn. Ứng dụng có thể chọn:

~~~text
Write: ONE
Read : ONE
RF   : 3 (cùng một datacenter trong ví dụ)
~~~

**Điều nhận được:**

- Chỉ cần một replica xác nhận cho mỗi thao tác nên thường có ít điều kiện phản hồi hơn so với `QUORUM`.
- Một số thao tác vẫn có thể hoàn tất khi không đủ replica cho quorum, tùy trạng thái cluster.

**Điều phải chấp nhận:**

- Đọc ngay sau ghi có thể thấy dữ liệu cũ.
- Hai lần đọc liên tiếp có thể quan sát trạng thái khác nhau do replica trả lời khác nhau.
- Replication/repair giúp dữ liệu hội tụ theo cơ chế Cassandra, nhưng **không có cam kết mọi replica cập nhật đồng thời ngay tại thời điểm write ONE trả thành công**.
- Việc client thấy một số mới rồi sau đó thấy số cũ có thể xảy ra nếu các lần đọc từ các replica chưa đồng bộ.

Vì vậy, product/API phải diễn đạt “dữ liệu có thể trễ” một cách có chủ đích. Nếu màn hình **bắt buộc** hiển thị chính xác thay đổi vừa lưu, chỉ tăng độ trễ chờ ở UI hoặc retry `ONE` nhiều lần không phải một bảo đảm nhất quán.

### 5.1. Đừng chọn ONE chỉ vì muốn giảm latency

Latency còn phụ thuộc kích thước partition, coordinator, số tombstone, network, số row, page size và tải cluster. Truy vấn `ALLOW FILTERING` quét rộng ở `ONE` vẫn có thể chậm hơn truy vấn theo partition key đúng ở `LOCAL_QUORUM`.

## 6. Yêu cầu thứ hai: đọc lại phải thấy lần ghi đã được xác nhận

Với một datacenter RF = 3, cặp thường được xem xét:

~~~text
Write: LOCAL_QUORUM
Read : LOCAL_QUORUM
RF   : 3 ở datacenter phục vụ cả hai thao tác
~~~

Giả sử người dùng cập nhật một hàng ở `orders_by_id`:

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant W as API ghi
    participant C as Cassandra
    participant R as API đọc
    U->>W: Thanh toán đơn hàng
    W->>C: Ghi state=PAID, LOCAL_QUORUM
    C-->>W: Thành công sau quorum trong DC
    W-->>U: Ghi thành công
    U->>R: GET /orders/{id}
    R->>C: SELECT, LOCAL_QUORUM cùng DC
    C-->>R: Hàng được hòa giải theo replica/timestamp
    R-->>U: Trạng thái quan sát được
~~~

Tại cùng nhóm ba replica của datacenter đó, write quorum có ít nhất hai replica xác nhận và read quorum cần ít nhất hai phản hồi. Vì hai tập **phải có giao nhau**, cách kết hợp này hỗ trợ yêu cầu **read-after-write đối với một lần ghi thành công**, trong những giả định đã nêu.

**Không nâng cách diễn đạt thành “mọi thao tác đều linearizable”:** có thể xuất hiện concurrent writes, timestamp không phản ánh thứ tự thời gian thực, xóa/TTL, ứng dụng ghi và đọc ở hai DC khác nhau hoặc một request ghi gặp timeout. Những tình huống đó cần mô hình và kiểm thử riêng.

### 6.1. Cần kiểm tra cả đường ghi lẫn đường đọc

Đặt `LOCAL_QUORUM` chỉ cho phương thức `save(...)` nhưng để `findById(...)` mặc định `ONE` sẽ tạo cặp `W=2, R=1`. Khi đó điều kiện `R+W>RF` không thỏa. Ngược lại, chỉ tăng read CL mà write vẫn `ONE` cũng chưa đủ.

**Bài học chính:** hãy ghi rõ **cặp read/write CL cho cùng hành trình nghiệp vụ**; không dừng ở một cài đặt riêng lẻ.

### 6.2. Cần định nghĩa “thành công” và “đọc sau” thật rõ

Khi yêu cầu là “sau phản hồi HTTP 200 từ lệnh ghi, request đọc tiếp theo phải thấy dữ liệu mới”, hãy kiểm tra:

- HTTP 200 chỉ được trả **sau khi Cassandra ghi thành công** ở CL yêu cầu.
- Request đọc **thật sự xảy ra sau** và dùng CL đọc tương ứng.
- Cả hai cùng trỏ đến **keyspace/bảng/partition** và cùng phạm vi datacenter.
- Không có tác nhân khác ghi đè trong khoảng đó bằng timestamp mới hơn hoặc timestamp bất thường.
- Không có cache ngoài Cassandra trả dữ liệu cũ (HTTP cache, Redis, cache của service...).

Cassandra CL không thể sửa một cache ứng dụng cũ hoặc lỗi routing sang bảng khác.

## 7. Yêu cầu thứ ba: đọc cực nhanh nhưng ghi phải xác nhận ở mọi replica

Trong một datacenter RF = 3, có thể xét:

~~~text
Write: ALL
Read : ONE
R + W = 1 + 3 = 4 > 3
~~~

Khi ghi **thành công ở `ALL`**, toàn bộ replica liên quan đã phải phản hồi. Một lần đọc `ONE` về sau thường có cơ sở để quan sát dữ liệu đó, giả sử không có mutation cạnh tranh/timestamp gây khác biệt.

**Đánh đổi lớn:** một replica không thể phản hồi có thể làm write `ALL` **không thể hoàn tất thành công**. Nếu nghiệp vụ cần ghi liên tục khi node lỗi, đây thường không phải lựa chọn tốt mặc dù read CL thấp.

Chiều ngược lại:

~~~text
Write: ONE
Read : ALL
~~~

giúp write dễ được xác nhận hơn nhưng làm read **phụ thuộc mọi replica**; nếu một replica không sẵn sàng, read có thể thất bại. Vì vậy, tối ưu hiệu năng chỉ qua công thức mà không xét **availability và lỗi node** sẽ dẫn đến thiết kế sai.

## 8. Yêu cầu thứ tư: multi-datacenter và khả năng quan sát xuyên vùng

Giả sử keyspace dùng `NetworkTopologyStrategy` với hai datacenter:

~~~sql
-- Ví dụ cho cluster có ít nhất đủ node phù hợp mỗi DC.
CREATE KEYSPACE app_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc_a': 3,
    'dc_b': 3
};
~~~

Tên `dc_a`/`dc_b` và RF chỉ là giả định học tập; phải dùng tên DC thật và topology thật. Với mỗi partition, có **ba replica tại DC A** và **ba replica tại DC B**.

### 8.1. LOCAL_QUORUM chỉ bảo vệ tập replica tại DC local

Nếu service ở DC A ghi `LOCAL_QUORUM`, nó đợi quorum **trong DC A**, tức thường là **hai trong ba replica A**.

Nếu request đọc ngay sau được chuyển sang **DC B** và đọc `LOCAL_QUORUM`, nó đợi **hai trong ba replica B**. Hai tập này **không phải cùng nhóm**, nên không thể dùng `2 + 2 > 3` để suy luận có giao nhau. DC B có thể chưa nhận bản cập nhật mới theo kỳ vọng của người dùng.

~~~mermaid
flowchart TB
    W[API ghi ở DC A] --> A1[DC A: A1]
    W --> A2[DC A: A2]
    A1 --> ACK[LOCAL_QUORUM ghi đã đủ]
    A2 --> ACK
    R[API đọc ở DC B] --> B1[DC B: B1]
    R --> B2[DC B: B2]
    B1 --> READ[LOCAL_QUORUM đọc đã đủ]
    B2 --> READ
    ACK -. Không bắt buộc giao nhau .-> READ
~~~

**Kết luận:** `LOCAL_QUORUM` ghi ở một DC + `LOCAL_QUORUM` đọc ở DC **khác** không tự bảo đảm read-after-write tức thì xuyên DC.

### 8.2. Ba cách xử lý yêu cầu xuyên datacenter

**Cách A — Session affinity/read-local:** với những request cần đọc ngay dữ liệu vừa ghi, giữ thao tác đọc ở **cùng DC** mà thao tác ghi đã được xác nhận theo `LOCAL_QUORUM`. Cần chú ý failover routing, session của ứng dụng và hệ thống cache.

**Cách B — Tăng phạm vi xác nhận:** tùy yêu cầu và topology, một write `EACH_QUORUM` (dành cho **ghi**) yêu cầu quorum trong **mỗi datacenter** được cấu hình phù hợp. Sau đó, một read `LOCAL_QUORUM` ở một DC có tập replica được xác nhận quorum trong chính DC đó. Đổi lại, write phụ thuộc khả năng đáp ứng của **từng DC**, tăng độ trễ và giảm availability khi WAN/DC gặp sự cố.

**Cách C — Mức quorum toàn cluster cho cả đọc và ghi:** xét `QUORUM` trên toàn bộ tập replica. Với tổng RF = 6, quorum toàn cục là **4** và `4 + 4 > 6`, nên tồn tại giao nhau theo mô hình toàn cục; đổi lại, có thể yêu cầu phản hồi xuyên DC và chi phí độ trễ cao. **Không được** kết hợp một write global quorum với một read local quorum rồi áp công thức giao nhau toàn cục một cách tùy tiện: read local chỉ hỏi replica của DC đó.

Chọn cách nào phụ thuộc SLA, mức chịu lỗi một DC, topology, mức độ cần quan sát tức thời và đặc tính concurrent writes. Không có giải pháp nào miễn phí.

### 8.3. Khi failover, hợp đồng read-after-write có thể thay đổi

Nếu ghi ở DC A theo `LOCAL_QUORUM` rồi toàn bộ traffic chuyển sang DC B ngay sau sự cố WAN, ứng dụng không được mặc định DC B **đã nhận mọi lần ghi A vừa xác nhận**. Cần mô tả rõ RPO/RTO, chính sách chuyển DC, những gì client nhìn thấy, và khả năng đối soát hoặc chấp nhận dữ liệu trễ sau failover.

## 9. Một số consistency level cần phân biệt

| CL | Áp dụng | Ý nghĩa thực tế cần nhớ |
| --- | --- | --- |
| `ONE` | Đọc/ghi | Một replica phản hồi theo phạm vi quy tắc CL |
| `LOCAL_ONE` | Đọc/ghi | Một replica trong datacenter local |
| `TWO`, `THREE` | Đọc/ghi | Số lượng replica cụ thể; phải phù hợp RF/topology |
| `QUORUM` | Đọc/ghi | Quorum trên tập replica theo phạm vi global |
| `LOCAL_QUORUM` | Đọc/ghi | Quorum của **datacenter local** |
| `EACH_QUORUM` | **Ghi** | Quorum ở từng datacenter theo replication strategy phù hợp |
| `ALL` | Đọc/ghi | Mọi replica liên quan phải phản hồi |
| `ANY` | **Ghi** | Có thể xác nhận khi hint được chấp nhận mà không có replica đích trả lời; không phù hợp cam kết đọc ngay |
| `SERIAL`, `LOCAL_SERIAL` | **Pha serial của LWT** | Dùng cho thao tác có điều kiện; không thay cho read/write CL thông thường |

### 9.1. Vì sao ANY thường bị hiểu sai?

`ANY` là một **write consistency level** và có thể phản hồi thành công dựa trên cơ chế hinted handoff trong tình huống replica đích chưa nhận trực tiếp mutation. Vì vậy không thể hiểu “write ANY thành công” là “đã có một replica bình thường lưu dữ liệu và read ONE sẽ thấy ngay”.

Nếu nghiệp vụ đòi hỏi phản hồi thành công phải tương ứng với dữ liệu đọc được ngay, **không dùng ANY để né yêu cầu quan sát**. Hinted handoff còn có chính sách lưu/khôi phục/giới hạn riêng, không phải cơ chế durability vĩnh viễn thay repair.

### 9.2. LOCAL_ONE khác gì ONE?

`LOCAL_ONE` thể hiện rõ cần phản hồi từ datacenter local. Với multi-DC, điều này hữu ích để giữ việc đọc/ghi ở phạm vi gần client theo chính sách định tuyến. Dù vậy `LOCAL_ONE` vẫn chỉ cần **một replica**, không có quorum overlap khi cả read và write đều `LOCAL_ONE` với RF = 3.

## 10. Linearizability, timestamp và “last-write-wins” không phải cùng thứ

### 10.1. Giao nhau không bảo vệ được lost update kiểu nghiệp vụ

Giả sử hai worker đọc cùng một trạng thái đơn hàng `CREATED`:

~~~text
T0: A đọc CREATED (LOCAL_QUORUM)
T1: B đọc CREATED (LOCAL_QUORUM)
T2: A ghi PAID (LOCAL_QUORUM) và thành công
T3: B ghi CANCELLED (LOCAL_QUORUM) và thành công
~~~

**Cả hai thao tác ghi có thể báo thành công** nếu là CQL `UPDATE` không điều kiện. Quorum giúp mỗi thao tác có số replica phản hồi theo CL, nhưng **không ngăn writer B ghi đè trạng thái nghiệp vụ mà A vừa cập nhật**.

Để bảo vệ yêu cầu “chỉ được chuyển trạng thái nếu state vẫn là CREATED”:

~~~sql
UPDATE app_ks.orders_by_id
SET state = 'PAID'
WHERE order_id = ?
IF state = 'CREATED';
~~~

Đây là **lightweight transaction (LWT)**. Nó trả `[applied]` cho biết điều kiện có được thỏa. LWT giải quyết một bài toán **đồng thuận/compare-and-set** cụ thể; nó không đồng nghĩa mọi thao tác read/write thường đều có linearizability.

### 10.2. Timestamp quyết định cách hòa giải các bản ghi cạnh tranh

Cassandra dùng timestamp của cell/mutation để xác định giá trị thắng khi có nhiều phiên bản xung đột theo quy tắc của hệ thống. Nếu hai client có clock lệch hoặc tự gắn timestamp theo thứ tự không phù hợp, một lần ghi **đến sau về thời gian thực** không nhất thiết được chọn là giá trị mới nhất sau hòa giải.

Vì vậy, không suy từ cặp `LOCAL_QUORUM/LOCAL_QUORUM` rằng “write được gửi sau luôn thắng” khi có concurrent writers hoặc timestamp tùy biến. Các chiến lược cần xem xét:

- Đồng bộ thời gian hệ thống ở các node/client có liên quan.
- Không tự gán timestamp ngẫu nhiên hoặc lùi thời gian khi không thật sự hiểu tác động.
- Dùng `IF version = ?` hoặc `IF state = ?` khi nghiệp vụ cần CAS.
- Phân biệt **state machine nghiệp vụ** với dữ liệu telemetry cho phép giá trị cuối thắng.

### 10.3. TTL, DELETE và read repair

Một giá trị có TTL có thể hết hạn sau thời gian quy định; xóa sinh tombstone. Trong khi các replica chưa hội tụ, các pha đọc/hòa giải và cơ chế repair góp phần quyết định dữ liệu quan sát được. **Read repair không phải cam kết “mọi lần đọc ONE đều mới nhất”** và hành vi chi tiết phụ thuộc phiên bản Cassandra, schema và trạng thái cluster.

Không dùng giả định rằng “cứ có QUORUM là không bao giờ có tombstone, conflict hoặc dữ liệu trễ”. Hãy thiết kế TTL/xóa và repair theo nhu cầu vận hành riêng.

## 11. Chọn cặp CL bằng ma trận yêu cầu

Thay vì bắt đầu từ một con số, hãy mô tả **mức quan sát mong muốn**:

| Yêu cầu | Điểm khởi đầu để đánh giá | Phải kiểm tra thêm |
| --- | --- | --- |
| Dashboard chấp nhận trễ | `ONE/ONE` hoặc `LOCAL_ONE/LOCAL_ONE` | Khả năng stale read, retry, replica repair |
| Người dùng đọc lại ngay sau ghi đã xác nhận trong **cùng DC** | `LOCAL_QUORUM/LOCAL_QUORUM` với RF = 3 tại DC đó | Cache, concurrent writers, timestamps, topology |
| Đọc rẻ, ghi cực kỳ có ràng buộc tất cả replica | `ALL/ONE` trong cùng phạm vi RF | Write availability khi node lỗi |
| Ghi rẻ, đọc bắt buộc đủ mọi replica | `ONE/ALL` trong cùng phạm vi RF | Read availability và latency |
| Đọc ngay sau ghi khi traffic có thể chuyển **DC** | Xem `EACH_QUORUM` write + `LOCAL_QUORUM` read từng DC, hoặc global quorum cho cả hai | WAN, failover SLA, quorum thuộc phạm vi nào |
| Không được ghi đè trạng thái khác writer đã đổi | LWT `IF version = ?` hoặc `IF state = ?` | `SERIAL/LOCAL_SERIAL`, contention, idempotency |
| Tạo duy nhất theo business key | Bảng đúng khóa + `IF NOT EXISTS` | Phạm vi duy nhất, thao tác các bảng phụ |
| Log sự kiện append-only, có thể xử lý chậm | CL thấp hơn có thể phù hợp | Replay/idempotency, mất phản hồi, sức chịu lỗi |

Đây là **điểm khởi đầu để thiết kế và thử nghiệm**, không phải bảng cấu hình mặc định áp dụng cho mọi cluster. Đặc biệt phải phân biệt **write CL nằm trước read CL hay ngược lại** trong tài liệu của đội nhóm; khi trao đổi, nên viết đầy đủ `W=LOCAL_QUORUM, R=LOCAL_QUORUM` thay vì ghi ngắn “Q/Q” dễ nhập nhằng.

## 12. Ví dụ Spring Data Cassandra: model và câu CQL theo khóa

### 12.1. Bảng theo yêu cầu tìm đơn hàng bằng ID

~~~sql
CREATE TABLE app_ks.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    state text,
    total_cents bigint,
    updated_at timestamp
);
~~~

Trong hệ thống thật, `app_ks` và replication strategy phải được tạo trước theo topology vận hành. Bảng này phục vụ truy vấn **theo một `order_id`**, không được hiểu là thích hợp với mọi truy vấn tìm theo `state` hoặc sắp xếp theo `updated_at`.

### 12.2. Entity và repository

~~~java
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_id")
public class OrderRow {
    @PrimaryKey("order_id")
    private UUID orderId;

    @Column("customer_id")
    private UUID customerId;

    @Column("state")
    private String state;

    @Column("total_cents")
    private Long totalCents;

    @Column("updated_at")
    private Instant updatedAt;

    protected OrderRow() {}

    public OrderRow(UUID orderId, UUID customerId, String state,
                    Long totalCents, Instant updatedAt) {
        this.orderId = orderId;
        this.customerId = customerId;
        this.state = state;
        this.totalCents = totalCents;
        this.updatedAt = updatedAt;
    }

    public UUID getOrderId() { return orderId; }
    public UUID getCustomerId() { return customerId; }
    public String getState() { return state; }
    public Long getTotalCents() { return totalCents; }
    public Instant getUpdatedAt() { return updatedAt; }
}
~~~

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface OrderRepository
        extends CassandraRepository<OrderRow, UUID> {
    // Kế thừa save(...) và findById(...).
}
~~~

Repository cung cấp API CRUD theo khóa; **nó không tự biến `findById(...)` thành “đọc dữ liệu mới nhất” trong mọi topology**. Thao tác thực tế dùng consistency được cấu hình ở driver/template/repository theo phiên bản ứng dụng và có thể có tùy chọn override trên từng query.

**Cần xác minh:** những Spring Data Cassandra version khác nhau có cơ chế áp CL mặc định, query options hoặc annotation/method-level settings khác nhau. Đừng tự khẳng định một annotation bất kỳ sẽ override consistency cho tất cả đường gọi `save`/`findById` nếu chưa kiểm tra tài liệu API và CQL/statement được phát ra.

## 13. Cấu hình mức đọc/ghi trên Java driver 4.x

Khi cần biết chắc CL của **từng câu CQL**, Java driver 4.x cho phép đặt ở mức statement. Có thể dùng một `CqlSession` được Spring quản lý và chuẩn bị các query một lần:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

public final class OrderCqlGateway {
    private final CqlSession session;
    private final PreparedStatement upsert;
    private final PreparedStatement select;

    public OrderCqlGateway(CqlSession session) {
        this.session = session;
        this.upsert = session.prepare(
            "INSERT INTO app_ks.orders_by_id " +
            "(order_id, customer_id, state, total_cents, updated_at) " +
            "VALUES (?, ?, ?, ?, ?)"
        );
        this.select = session.prepare(
            "SELECT order_id, customer_id, state, total_cents, updated_at " +
            "FROM app_ks.orders_by_id WHERE order_id = ?"
        );
    }

    public void save(OrderRow order) {
        session.execute(upsert.bind(
                order.getOrderId(),
                order.getCustomerId(),
                order.getState(),
                order.getTotalCents(),
                order.getUpdatedAt()
            ).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM));
    }

    public Optional<OrderRow> find(UUID orderId) {
        Row row = session.execute(
            select.bind(orderId)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        ).one();
        if (row == null) {
            return Optional.empty();
        }
        return Optional.of(new OrderRow(
            row.getUuid("order_id"),
            row.getUuid("customer_id"),
            row.getString("state"),
            row.isNull("total_cents") ? null
                : row.getLong("total_cents"),
            row.getInstant("updated_at")
        ));
    }
}
~~~

Hai phương thức này dùng **cùng CL tại cùng DC** và làm việc với `order_id`. Chúng minh họa lựa chọn CL tường minh chứ không phải giải pháp CAS. `INSERT` bình thường vẫn có thể upsert hoặc chịu last-write-wins khi có writer cạnh tranh.

**Lưu ý để chạy được:**

- Ví dụ dùng **Java driver 4.x**, `OrderRow` từ phần trước và schema đã chuẩn bị.
- `CqlSession` phải trỏ đúng cluster/keyspace; CQL đã dùng tên bảng đầy đủ `app_ks.orders_by_id`.
- Tên datacenter local trong driver phải khớp topology thực tế.
- `PreparedStatement` được tạo **một lần** trong constructor; `BoundStatement` là đối tượng mới cho mỗi thao tác.
- `Row.getInstant(...)` tương ứng với cột CQL `timestamp`. Nếu cần so sánh chính xác khi round-trip, chuẩn hóa độ chính xác thời gian theo mili giây.
- Đừng đóng `CqlSession` sau mỗi call; để Spring hoặc thành phần sở hữu session quản lý vòng đời.

### 13.1. Bean service không sở hữu session dùng chung

Trong một ứng dụng Spring, có thể đăng ký gateway bằng bean:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderCqlGatewayConfig {
    @Bean
    OrderCqlGateway orderCqlGateway(CqlSession session) {
        return new OrderCqlGateway(session);
    }
}
~~~

**Không tạo thêm session** nếu Spring Boot đã có bean `CqlSession` tương ứng. Nếu ứng dụng có nhiều session/keyspace, dùng `@Qualifier` để đảm bảo gateway và repository nhắm đúng cluster/keyspace. Một cặp CL đúng nhưng ghi ở `catalogSession` và đọc ở `billingSession` vẫn là lỗi kiến trúc.

### 13.2. CL mặc định và override theo statement

Driver cho phép cấu hình **default consistency** và override trên statement. Nếu thao tác yêu cầu mức chặt hơn mặc định, đặt `setConsistencyLevel(...)` trên **bound statement được thực thi** là cách dễ quan sát trong ví dụ.

Không nên cố chuyển mọi truy vấn sang tầng driver chỉ vì muốn thay CL. Trên đường dùng `CassandraRepository`/`CassandraTemplate`, hãy ưu tiên cơ chế query options/consistency được **đúng phiên bản Spring Data Cassandra** hỗ trợ, rồi kiểm tra bằng integration test hoặc quan sát statement options. Khi cần kiểm soát cực kỳ cụ thể, có thể viết gateway CQL tường minh.

## 14. Tình huống: write timeout và trạng thái kết quả chưa rõ

Một sai lầm phổ biến là coi `WriteTimeout` như bằng chứng lần ghi **chắc chắn chưa xảy ra**:

~~~text
Client gửi write LOCAL_QUORUM
     |
Coordinator gửi tới replica
     |
Replica có thể đã áp dụng một phần/toàn bộ mutation
     |
Client hết thời gian chờ, không nhận xác nhận đủ
     |
Client KHÔNG biết chắc dữ liệu thực tế đã ghi đến đâu
~~~

**Timeout có thể gây trạng thái không xác định ở phía client.** Write CL chỉ nói **điều kiện để phản hồi thành công**; thiếu phản hồi thành công không tự suy ra mọi replica đều không nhận gì.

### 14.1. Ba nhánh xử lý khác nhau

~~~mermaid
flowchart TD
    A[Thực hiện write ở CL đã chọn] --> B{Kết quả?}
    B -->|Success| C[Đã đạt mức xác nhận W]
    B -->|Timeout/Unavailable| D[Không có bảo đảm thành công]
    D --> E[Điều tra, kiểm tra lại và xử lý retry]
    B -->|Conditional false| F[LWT: điều kiện không thỏa]
    C --> G[Cho phép đọc theo CL phù hợp]
~~~

Nhánh `Conditional false` **chỉ áp dụng cho conditional write/LWT** khi server trả kết quả `[applied] = false`, không phải mọi lệnh `INSERT` thông thường.

### 14.2. Retry phải gắn với idempotency

Ví dụ nghiệp vụ ghi trạng thái đơn hàng:

- Nếu retry một mutation ghi **cùng giá trị và khóa** dưới chính sách timestamp ổn định, có thể dễ kiểm soát hơn.
- Nếu request đầu có thể đã ghi rồi request khác cập nhật, một retry không điều kiện với timestamp mới hơn có thể **ghi đè dữ liệu hợp lệ**.
- Với counter hoặc hành động nghiệp vụ có tác dụng phụ, retry có thể tạo **hai lần hiệu ứng** nếu không có thiết kế idempotency.

Vì vậy, hãy dùng **idempotency key**, version/CAS hoặc trạng thái workflow khi cần; không viết vòng lặp `catch (Exception) { retry }` vô hạn.

**Read sau timeout** cũng phải được diễn giải cẩn thận: nếu chưa biết write đã đạt CL nào, một lần đọc `LOCAL_QUORUM` không thể tự biến timeout trước đó thành một giao dịch thành công đã được chứng minh. Có thể cần đối soát idempotency hoặc kiểm tra state có phiên bản.

## 15. LWT và serial consistency giải quyết bài toán khác

Nếu yêu cầu là:

> “Chỉ được đặt `state = PAID` nếu hàng vẫn có `version = 7`.”

thì đây là bài toán **compare-and-set**, không phải chỉ read-after-write. CQL có điều kiện:

~~~sql
UPDATE app_ks.orders_by_id
SET state = ?, updated_at = ?
WHERE order_id = ?
IF state = 'CREATED';
~~~

Java driver có thể đặt **regular CL** và **serial CL** riêng cho conditional statement:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;

BoundStatement cas = preparedConditionalUpdate
    .bind("PAID", updatedAt, orderId)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

ResultSet result = session.execute(cas);
boolean applied = result.wasApplied();
~~~

Đoạn ví dụ giả định `preparedConditionalUpdate` và `session` có sẵn; cần import `BoundStatement`, `ResultSet` của driver và có schema tương ứng.

Phân biệt:

- `LOCAL_QUORUM` ở đây là **regular consistency** theo topology phù hợp.
- `LOCAL_SERIAL` chi phối **pha đồng thuận LWT trong phạm vi local**; khi yêu cầu đồng thuận xuyên datacenter, lựa chọn khác như `SERIAL` cần được đánh giá.
- `wasApplied()` trả **true/false của điều kiện đã được xử lý thành công**, không phải bằng chứng một lần ghi thông thường “trả 1 row”.
- LWT dùng thêm phối hợp Paxos, có chi phí/contension lớn hơn write thường.

LWT bảo vệ một điều kiện cụ thể trên dữ liệu/partition theo CQL và phiên bản Cassandra. **Không suy rằng LWT tạo transaction ACID nhiều bảng/partition như RDBMS**, hay rằng tất cả read thường từ hệ khác sẽ ngay lập tức quan sát theo cùng một thứ tự toàn cục.

## 16. Projection, paging và consistency liên hệ ra sao?

CL không quyết định **có bao nhiêu hàng** được trả; nó quyết định yêu cầu replica phản hồi của một thao tác. Một query CQL hợp lệ còn cần:

1. **Partition key đầy đủ** để tránh fan-out/quét không cần thiết.
2. **Clustering restriction** phù hợp nếu đọc theo khoảng thời gian.
3. **Projection** để giảm số cột phải truyền qua mạng.
4. **`LIMIT`** nếu chỉ cần N hàng.
5. **Paging state/page size** nếu phải đọc nhiều trang.

Ví dụ:

~~~sql
CREATE TABLE app_ks.events_by_customer_day (
    customer_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((customer_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

~~~sql
SELECT event_id, occurred_at, event_type
FROM app_ks.events_by_customer_day
WHERE customer_id = ? AND event_day = ?
LIMIT 20;
~~~

Thay `ONE` bằng `LOCAL_QUORUM` **không** biến câu `SELECT * FROM ... WHERE event_type = ?` thành truy vấn theo partition key hợp lệ. Nó cũng không làm `LIMIT 20` tương đương với page size 20 hay tạo snapshot bất biến khi có ghi đồng thời.

Với lịch sử sự kiện có thể cần **mức nhất quán thấp hơn** so với đơn hàng thanh toán, nhưng vẫn phải đo latency, tombstone, partition size và tải đọc/ghi theo access pattern.

## 17. Test thực tế: sự khác nhau giữa ONE/ONE và QUORUM/QUORUM

### 17.1. Môi trường thử nghiệm

Sử dụng **cluster thử nghiệm** có một datacenter, ít nhất ba replica phù hợp và keyspace RF = 3. Ví dụ:

~~~sql
-- Dành cho môi trường test có đủ node tại dc1.
CREATE KEYSPACE IF NOT EXISTS consistency_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS consistency_lab.read_after_write (
    id uuid PRIMARY KEY,
    value text,
    version int
);
~~~

**`dc1` là placeholder**, thay bằng tên DC thật. Nếu chỉ có cluster một node, không thể thử đúng mô hình quorum RF = 3 với ba replica thực tế. Không dùng kết quả lab một node làm bằng chứng cho behavior nhiều replica.

### 17.2. Quy trình so sánh

1. Tạo một `id` thử nghiệm duy nhất.
2. Ghi `value = 'A', version = 1` ở `ONE` rồi đọc `ONE` nhiều lần; quan sát kết quả. Một lần nào đó thấy A **không chứng minh ONE/ONE có bảo đảm read-after-write**.
3. Trên một `id` khác, ghi `value = 'B', version = 1` ở `LOCAL_QUORUM` và chờ xác nhận thành công.
4. Đọc `LOCAL_QUORUM` tại **cùng DC**; đối chiếu với kết quả kỳ vọng trong điều kiện không có writer cạnh tranh.
5. Thử cặp `LOCAL_QUORUM` ghi, `LOCAL_ONE` đọc; giải thích vì sao quorum overlap **không bắt buộc**.
6. Dừng một replica bằng công cụ được phép **chỉ trên cluster thử nghiệm**, rồi so sánh availability của `ONE`, `QUORUM`, `ALL`. Khi RF = 3, quorum có thể vẫn đạt nếu còn đủ hai replica phản hồi, `ALL` không thể hoàn tất khi một replica cần thiết không sẵn sàng.
7. Khởi động lại replica và quan sát quá trình dữ liệu hội tụ; không khẳng định một read thử nghiệm có thể thay thế các quy trình repair/giám sát.
8. Thử hai writer cạnh tranh cùng một hàng bằng write thường; quan sát rằng nâng CL không bảo vệ quy tắc state transition.
9. Thử LWT `IF version = ?` và kiểm tra `wasApplied()` của hai writer.
10. Nếu có hai DC, thử write `LOCAL_QUORUM` tại DC A rồi đọc `LOCAL_QUORUM` tại DC B, nhưng **không suy diễn bảo đảm mạnh từ một số ít lần chạy thành công**.

**Không làm thí nghiệm node failure, network partition hoặc stress trên production.** Kiểm thử fault injection có thể ảnh hưởng topology và cần được kiểm soát trong lab.

### 17.3. Unit test chỉ chứng minh điều gì?

Một unit test có thể dùng mock gateway để kiểm tra service chọn **đúng policy CL cho use case**, ví dụ đơn hàng quan trọng dùng quorum. Nhưng mock không thể kiểm chứng:

- Số replica thực sự phản hồi.
- Việc đọc có thấy bản ghi mới khi replica đang trễ hay không.
- Giao nhau giữa các quorum trong topology thật.
- Timeout và tình huống commit một phần.
- Hòa giải timestamp hoặc hiệu ứng repair.

Những thuộc tính đó cần **integration test và quan sát cluster**.

## 18. Đề xuất cách viết hợp đồng API và đo hiệu quả

Một hợp đồng rõ ràng cho đường “thanh toán xong đọc lại” có thể viết:

~~~text
Use case: đọc trạng thái đơn ngay sau khi thanh toán
Partition key: order_id
Topology: cùng datacenter, RF = 3
Write CL: LOCAL_QUORUM
Read CL : LOCAL_QUORUM
Điều kiện: write đã trả success; không có update cạnh tranh;
            clock/timestamp hợp lệ; không dùng cache cũ
Timeout: không khẳng định write thất bại; xử lý trạng thái chưa rõ
Failover sang DC khác: có chính sách quan sát dữ liệu riêng
~~~

Với use case “thống kê gần thời gian thực”:

~~~text
Use case: dashboard chấp nhận dữ liệu trễ
Topology: cùng DC, RF = 3
Write CL: LOCAL_ONE
Read CL : LOCAL_ONE
Điều kiện: UI chấp nhận stale read; dữ liệu có cơ chế hội tụ
Timeout: retry/backoff và hiển thị trạng thái hệ thống theo hợp đồng
~~~

**Metric nên theo dõi** trong vận hành:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| P50/P95/P99 write/read latency theo CL | Độ trễ thực khi đổi mức consistency |
| Timeout, unavailable, retry rate | Tính sẵn sàng và mức chịu lỗi của lựa chọn CL |
| Số replica/node không khỏe | Điều kiện để một CL có thể đạt được |
| Tỷ lệ stale read theo thử nghiệm/kiểm chứng | Đánh giá mức quan sát so với SLA nghiệp vụ |
| Write conflict, CAS not applied | Mức tranh chấp và tính phù hợp của state machine |
| Kích thước partition, tombstone, paging fetch | Chi phí query không phải do CL đơn thuần |
| Cross-DC latency, failover events | Khả năng đảm bảo yêu cầu quan sát sau chuyển DC |

Không nên đo một câu truy vấn đơn lẻ rồi kết luận `ONE` luôn nhanh hơn `QUORUM` theo một tỷ lệ cố định. Chi phí thay đổi theo cluster, coordinator, tải, network và mẫu dữ liệu.

## 19. Những hiểu nhầm cần tránh

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Write QUORUM, read ONE chắc chắn đọc được dữ liệu mới.” | Với RF = 3, `2 + 1 = 3`, **chưa bảo đảm giao nhau** |
| “Read QUORUM là đủ, write ONE không quan trọng.” | Phải xét **cả R và W** |
| “`R + W > RF` có nghĩa mọi thao tác Cassandra linearizable.” | Chỉ là điều kiện giao nhau theo giả định cụ thể, không ngăn concurrent writes/timestamp conflict |
| “LOCAL_QUORUM tại hai DC khác nhau vẫn tự giao nhau.” | Mỗi LOCAL_QUORUM hoạt động trong **DC của nó** |
| “Quorum tương đương ALL về availability.” | Quorum RF = 3 có thể chịu một replica không phản hồi; ALL thì không |
| “Write ANY thành công là read ONE thấy ngay.” | ANY có thể được xác nhận qua hint, không có bảo đảm đọc tức thì |
| “WriteTimeout nghĩa là không replica nào ghi.” | Lần ghi có thể đã áp dụng một phần/toàn bộ |
| “LWT là cách viết khác của QUORUM.” | LWT dùng đồng thuận/conditional CAS và có serial consistency riêng |
| “Đặt consistency mạnh sẽ sửa được truy vấn thiếu partition key.” | CL không thay đổi schema và đường truy cập CQL |
| “LOCAL_QUORUM đảm bảo dữ liệu trong cache ứng dụng được làm mới.” | Cache là một tầng khác, cần chính sách invalidation |
| “Chỉ cần read repair là mọi ONE read đều luôn mới.” | Repair giúp hội tụ, không là lời hứa tức thời cho mọi lượt đọc |
| “Read-after-write có nghĩa đọc một snapshot nguyên tử xuyên nhiều bảng.” | Cassandra không tự cho transaction ACID đa bảng/partition như RDBMS |

## 20. Bài thực hành tổng hợp và câu hỏi tự kiểm tra

**Đề bài:** nhóm phát triển xây API cập nhật trạng thái đơn hàng và dashboard sự kiện. API đơn hàng cần quan sát dữ liệu vừa ghi trong cùng datacenter; dashboard chấp nhận trễ. Hệ thống có kế hoạch chuyển traffic sang datacenter dự phòng khi có sự cố.

**Các bước đề xuất:**

1. Mô tả chính xác hai SLA về khả năng quan sát, latency và availability.
2. Chọn keyspace RF = 3 cho môi trường lab một DC đủ node; tạo bảng `orders_by_id`.
3. So sánh `ONE/ONE`, `QUORUM/ONE`, `ONE/QUORUM`, `QUORUM/QUORUM` bằng công thức `R + W > RF`.
4. Cấu hình statement write và read ở `LOCAL_QUORUM` trên **cùng DC**, xác minh read-after-write khi ghi thành công và không có writer khác.
5. Kiểm thử một replica không phản hồi trong lab, so sánh hoạt động của `ONE`, `QUORUM`, `ALL`.
6. Tạo hai writer update cùng trạng thái để chứng minh CL cao **không** thay thế CAS; thêm `IF version = ?` và quan sát `[applied]`.
7. Mô phỏng write timeout và thiết kế cách trả trạng thái **chưa xác định**, không biến ngoại lệ thành “ghi chắc chắn thất bại”.
8. Bổ sung DC dự phòng trong sơ đồ thiết kế; giải thích vì sao write local quorum ở DC A không bảo đảm read local quorum ở DC B.
9. Đưa ra lựa chọn cho failover: affinity, `EACH_QUORUM` write hoặc global quorum cả hai chiều, kèm chi phí latency/availability.
10. Giữ truy vấn theo partition key, projection và `LIMIT` phù hợp; chứng minh consistency không sửa được query sai.
11. Ghi nhận latency, timeout, phiên bản Cassandra/driver và trạng thái topology trong mỗi lần thử.

**Tự kiểm tra:**

1. RF = 3 nghĩa là điều gì đối với một partition? Nó có bằng số node đang hoạt động không?
2. Khi RF = 5, quorum cần bao nhiêu replica phản hồi?
3. Vì sao `R + W > RF` là điều kiện giao nhau, và nó dựa trên giả định nào?
4. Với RF = 3, tại sao write `QUORUM` và read `ONE` chưa đủ để bảo đảm giao nhau?
5. Khi nào `LOCAL_QUORUM/LOCAL_QUORUM` có thể hỗ trợ yêu cầu read-after-write?
6. Vì sao câu trên không áp dụng tự động khi write ở DC A và read ở DC B?
7. `ALL/ONE` và `ONE/ALL` khác nhau về khả năng chịu lỗi thế nào?
8. `ANY` có gì nguy hiểm nếu ứng dụng đòi hỏi dữ liệu đọc được ngay?
9. Quorum có tự ngăn hai writer cùng update một hàng từ trạng thái cũ không?
10. Khi nào phải dùng LWT `IF version = ?` thay vì chỉ nâng consistency?
11. Regular CL và serial CL có vai trò gì khác nhau?
12. Khi ghi trả `WriteTimeout`, có thể kết luận hàng chưa từng được ghi không?
13. Vì sao cache ở application layer có thể phá yêu cầu đọc thấy dữ liệu mới dù CL Cassandra đã chọn đúng?
14. CL có ảnh hưởng tới việc cho phép lọc theo cột không nằm trong primary key không?
15. `LIMIT` và page size có thay thế cho việc chọn partition key đúng không?
16. Các metrics nào cần thu thập để đánh giá lựa chọn CL khi node không khỏe hoặc sau failover?

**Ghi nhớ:** trong Cassandra, **mức đọc và mức ghi phải được chọn như một cặp theo yêu cầu quan sát dữ liệu**, replication factor và **phạm vi replica thực sự dùng cho cả hai thao tác**. `R + W > RF` giải thích giao nhau trong mô hình đơn giản, nhưng không tự tạo linearizability, không giải quyết concurrent writes, timeout không chắc chắn hoặc việc chuyển datacenter. Với Spring Data Cassandra, hãy làm rõ CL cho từng đường repository/template/CQL, kiểm thử trên cluster thật và kết hợp đúng partition key, paging, LWT và chính sách vận hành của hệ thống phân tán.
