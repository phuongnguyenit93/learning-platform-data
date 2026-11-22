# Repair trong một datacenter hoặc giữa các datacenter của Apache Cassandra

## 1. Mục tiêu: đồng bộ đúng bản sao, đúng phạm vi

Apache Cassandra là cơ sở dữ liệu **wide-column phân tán**. Mỗi partition được xác định bằng **partition key**, có thể chứa nhiều clustering row, và được lưu tại nhiều replica theo cấu hình **replication factor (RF)**. Với cụm nhiều datacenter (DC), chiến lược `NetworkTopologyStrategy` cho phép đặt RF riêng cho từng DC.

Một lần ghi CQL có thể được xác nhận theo `LOCAL_QUORUM` tại DC địa phương trước khi mọi replica ở các DC khác xác nhận. Nếu node gặp sự cố, mạng bị phân vùng hoặc replica bỏ lỡ mutation, các bản sao có thể không giống nhau trong một thời gian.

**Anti-entropy repair** là hoạt động Cassandra so sánh và đồng bộ dữ liệu giữa các replica của một phạm vi token. Chủ đề quan trọng ở đây là **chọn repair chỉ trong một datacenter hay repair giữa các datacenter**:

- **Repair trong một DC (intra-DC/local repair):** đối chiếu những replica thuộc cùng DC, hạn chế luồng đồng bộ vượt qua kết nối WAN.
- **Repair giữa các DC (cross-DC/inter-DC repair):** đưa replica thuộc nhiều DC vào quá trình đối chiếu, phát hiện và xử lý chênh lệch mà repair nội bộ từng DC có thể bỏ sót.

Hai cách không tương đương. **Chỉ chạy local repair riêng cho mỗi DC không đủ để chứng minh dữ liệu giữa các DC đã hội tụ**.

Trong ứng dụng Java, việc đặt CL đọc/ghi, thiết kế partition key đúng với truy vấn và có lịch repair thích hợp là các quyết định bổ sung cho nhau; không một quyết định đơn lẻ nào thay thế được các quyết định khác.

## 2. Mô hình hai DC: replica nào đang khác nhau?

Giả sử cluster có hai datacenter, mỗi DC gồm ba replica của partition có khóa `order_id = O1`:

```text
               DATACENTER dc1                       DATACENTER dc2
           +----------------------+             +----------------------+
           | R1       R2       R3 |             | R4       R5       R6 |
           | status = PAID        |             | status = PENDING     |
           | status = PAID        |             | status = PENDING     |
           | status = PAID        |             | status = PENDING     |
           +----------------------+             +----------------------+
                 RF(dc1)=3                               RF(dc2)=3
                            <--- đường mạng liên DC --->
```

Giả sử `PAID` đến từ mutation hợp lệ có timestamp thắng nhưng chưa đến dc2 do gián đoạn mạng. Tại thời điểm này:

- Một lần đọc `LOCAL_QUORUM` ở dc1 có thể trả `PAID`.
- Một lần đọc `LOCAL_QUORUM` ở dc2 có thể trả `PENDING`.
- Repair **chỉ trong dc1** thấy R1, R2, R3 đã giống nhau, nên không có chênh lệch cục bộ cần sửa.
- Repair **chỉ trong dc2** cũng có thể thấy R4, R5, R6 giống nhau, dù chúng vẫn cũ so với dc1.
- Repair có **phạm vi giữa dc1 và dc2** mới có cơ hội so sánh hai tập replica và đưa mutation thắng tới replica còn thiếu.

Đây là ví dụ đơn giản hóa. Khi có ghi đồng thời, tombstone hoặc TTL, Cassandra hòa giải dữ liệu theo **timestamp và quy tắc cell**, không phải chọn “giá trị từ DC nào đông hơn”. Không được suy luận thời gian thực trên đồng hồ của người dùng chính là thứ tự thắng khi timestamp từ các nguồn có thể lệch.

### Vì sao còn có local quorum?

Với RF = 3 trong một DC:

```text
LOCAL_QUORUM = floor(RF_DC / 2) + 1 = 2
```

Mỗi lần đọc hoặc ghi ở `LOCAL_QUORUM` chỉ yêu cầu hai phản hồi trong DC địa phương để đáp ứng CL; coordinator vẫn có thể liên hệ thêm replica hoặc chuyển tiếp dữ liệu ra DC khác tùy đường ghi và trạng thái cụm. **CL địa phương là điều kiện xác nhận**, không phải một lệnh yêu cầu “ngừng sao chép xuyên DC”.

Hai local quorum thuộc hai DC khác nhau **không cần có replica chung**. Vì vậy, không thể dùng phép giao quorum trong một DC để bảo đảm hai DC luôn trả cùng một giá trị ở mọi thời điểm.

## 3. Cơ chế anti-entropy repair và phần dữ liệu được so sánh

Repair không đơn giản sao chép toàn bộ bảng từ một node được cho là “đúng” sang những node khác. Trên các phiên bản Cassandra hỗ trợ, quá trình repair sử dụng cơ chế như **validation** và so sánh cấu trúc tóm tắt dữ liệu (ví dụ Merkle tree) để phát hiện các dải dữ liệu không khớp, sau đó **stream** những phần cần đồng bộ.

```mermaid
sequenceDiagram
    participant Op as Người vận hành
    participant N as Node điều phối repair
    participant A as Replica A
    participant B as Replica B
    Op->>N: nodetool repair (với phạm vi đã chọn)
    N->>A: Validation cho token range
    N->>B: Validation cho cùng token range
    A-->>N: Tóm tắt dữ liệu
    B-->>N: Tóm tắt dữ liệu
    Note over N: So sánh, tìm vùng khác nhau
    N->>A: Phối hợp đồng bộ nếu cần
    N->>B: Phối hợp đồng bộ nếu cần
    A<->>B: Streaming dữ liệu cho vùng cần sửa
    A-->>N: Kết quả session
    B-->>N: Kết quả session
    N-->>Op: Hoàn tất hoặc báo lỗi
```

Đây là sơ đồ khái niệm; bước thực thi, việc chọn source/destination, xử lý SSTable và cách hiển thị session phụ thuộc phiên bản Cassandra cũng như full/incremental repair.

Một thao tác repair có ít nhất **ba lớp phạm vi** cần được xác định:

1. **Token range/partition:** node bắt đầu repair chịu trách nhiệm cho những dải token nào; các tùy chọn range có thể giới hạn hơn nữa.
2. **Keyspace và table:** chỉ những bảng được chọn mới được đưa vào phiên repair.
3. **Participants:** những replica nào được phép tham gia so sánh/stream, theo local DC, DC chỉ định hoặc cấu hình mặc định.

Nếu một lớp phạm vi bị thu hẹp, không được diễn giải kết quả thành “tất cả dữ liệu trên mọi replica đã được đồng bộ”.

## 4. Repair trong cùng datacenter: lợi ích và ranh giới

**Intra-DC repair** so sánh các replica trong một DC. Nó thường được chọn khi:

- Cần giảm băng thông WAN vì các DC ở những vùng địa lý xa nhau.
- Một replica trong dc1 mới phục hồi sau sự cố, trong khi những replica khác của dc1 đã có dữ liệu cập nhật.
- Lịch bảo trì tách việc sửa chênh lệch **nội DC** khỏi một đợt sửa chênh lệch **liên DC**.
- Mạng liên DC đang có giới hạn mà hệ thống không thể chịu tải streaming lớn ngay lập tức.

Ví dụ `dc1` có ba replica:

| Replica trong dc1 | Giá trị tại partition `O1` |
| --- | --- |
| R1 | `PAID` |
| R2 | `PAID` |
| R3 | `PENDING` |

Repair local của các range có chứa `O1` có thể so sánh R1/R2/R3 và đồng bộ R3 theo quy tắc hòa giải. **Điều đó không chứng minh dc2 đã có `PAID`**.

### Lệnh `nodetool repair -local`

Khi chạy trên một node ở **dc1**, ví dụ để sửa bảng `orders_by_id`:

```bash
nodetool repair -full -local repair_lab orders_by_id
```

Ý nghĩa chủ đạo của các tùy chọn:

- `-full`: yêu cầu **full repair** thay vì phụ thuộc chế độ incremental mặc định của phiên bản.
- `-local`: giới hạn participants ở **datacenter của node đang chạy lệnh**.
- `repair_lab orders_by_id`: chỉ định keyspace và bảng.

Lệnh này **không tự repair mọi token range của toàn cluster**. Phạm vi range liên quan tới node mục tiêu; để bao phủ toàn bộ dữ liệu của một DC hoặc cluster, cần kế hoạch chạy trên tập node/range phù hợp. Ngoài ra, nó có thể thất bại khi một participant cần thiết không khả dụng.

> Ghi nhớ: `-local` nghĩa là “chỉ repair với replica thuộc DC địa phương”, **không có nghĩa toàn bộ dữ liệu trên các DC khác đã an toàn**.

### Chạy local repair trên tất cả DC có đủ không?

Không nhất thiết. Xét:

```text
Trước repair:
dc1: PAID, PAID, PAID
dc2: PENDING, PENDING, PENDING

Sau repair local riêng trong dc1:
dc1: PAID, PAID, PAID
dc2: PENDING, PENDING, PENDING

Sau repair local riêng trong dc2:
dc1: PAID, PAID, PAID
dc2: PENDING, PENDING, PENDING
```

Vì mỗi nhóm replica đã nhất quán **nội bộ**, không có cặp so sánh vượt qua ranh giới DC để phát hiện khác biệt giữa hai nhóm. Một lịch chỉ có local repair có thể bảo đảm phạm vi nội bộ mà **không bảo đảm hội tụ giữa DC**.

## 5. Repair giữa các datacenter: khi nào cần?

**Cross-DC repair** đưa replica ở nhiều DC vào cùng phạm vi đối chiếu. Đây là cơ chế quan trọng khi:

- Một DC đã vắng mạng lâu và có thể bỏ lỡ các mutation từ DC khác.
- Hệ thống dùng đọc/ghi theo `LOCAL_QUORUM` ở **nhiều DC**, cần hội tụ bản sao giữa các vùng.
- Các DC đã tự repair nội bộ nhưng vẫn có kết quả đọc khác nhau.
- Cần lập kế hoạch đồng bộ dữ liệu sau phục hồi thảm họa, sau streaming hoặc trước một thay đổi vận hành có yêu cầu nhất quán đặc biệt.

### Lệnh minh họa cho repair không giới hạn ở DC địa phương

Ở phiên bản có semantics tùy chọn tương ứng, một full repair **không thêm `-local` hoặc `-dc`** có thể đưa replica từ tất cả DC liên quan của keyspace vào quá trình repair:

```bash
nodetool repair -full repair_lab orders_by_id
```

**Không chạy lệnh này đồng thời trên mọi node theo phản xạ.** Nó có thể truyền dữ liệu qua WAN, tạo tải validation/streaming trên nhiều replica và chiếm đáng kể băng thông. Thực hiện theo lịch chạy từng phạm vi node/range, có giới hạn concurrency và theo dõi tài nguyên.

Một số phiên bản hỗ trợ tùy chọn giới hạn participants theo DC:

```bash
# Ví dụ tùy chọn phạm vi; xác minh "nodetool help repair" của phiên bản.
nodetool repair -full -dc dc1 repair_lab orders_by_id
```

Trong ví dụ, `-dc dc1` giới hạn participants tới DC được chỉ định; **nó không đồng nghĩa repair xuyên cả dc1 và dc2**. Để thực sự so sánh dữ liệu giữa các DC, tập participants/range của session phải chứa replica thuộc các DC cần đối chiếu.

Các tùy chọn `-dc` có cú pháp và giới hạn phối hợp tùy phiên bản; không giả định có thể lặp một cờ hoặc kết hợp tùy ý với `-local` mà không kiểm tra trợ giúp của phiên bản triển khai.

### Đánh đổi về hiệu năng và độ tin cậy

| Khía cạnh | Local DC repair | Cross-DC repair |
| --- | --- | --- |
| Replica được đối chiếu | Replica trong một DC đã chọn | Replica thuộc nhiều DC liên quan |
| WAN traffic | Thường tránh streaming xuyên DC | Có thể phát sinh streaming qua WAN |
| Network latency | Thường thấp hơn do kết nối nội DC | Bị ảnh hưởng độ trễ, băng thông và độ ổn định liên DC |
| Chênh lệch giữa các DC | Có thể **không phát hiện** | Có thể phát hiện và sửa nếu range và participants bao phủ |
| Tác động vận hành | Tập trung vào tài nguyên DC được sửa | Cần phối hợp tài nguyên ở nhiều DC |
| Ý nghĩa sau khi hoàn tất | Đã repair phạm vi local đã chọn | Đã repair phạm vi cross-DC đã chọn; không tự bảo đảm mọi phạm vi khác |

Vì khác biệt về chi phí, lịch thường cần **phối hợp repair nội DC và liên DC**, thay vì chọn một loại rồi bỏ loại kia. Tần suất phải dựa trên thay đổi dữ liệu, uptime của replica, giới hạn hint, tombstone grace, SLA và năng lực phần cứng.

## 6. Xác định phạm vi repair: tránh “một lệnh sửa toàn cluster”

`nodetool` kết nối vào **một node** của Cassandra và điều khiển repair theo phạm vi của node/range đó. Việc hoàn tất trên một node **không đồng nghĩa** đã quét đủ mọi partition của mọi node.

Các lựa chọn thường gặp:

| Tùy chọn/đầu vào | Điều cần hiểu | Cảnh báo |
| --- | --- | --- |
| `keyspace [table]` | Giới hạn dữ liệu theo keyspace và bảng | Nếu chỉ một bảng, các bảng khác không được repair |
| `-local` | Chỉ làm việc với replica ở DC của node mục tiêu | Không phát hiện chênh lệch chỉ tồn tại giữa các DC |
| `-dc <dc>` | Giới hạn participants theo DC được chỉ định ở phiên bản hỗ trợ | Chọn sai DC có thể bỏ ngoài phạm vi cần đồng bộ |
| `-pr` | Chỉ repair những primary ranges của node theo cách xác định ở phiên bản đó | Phải chạy đủ node/range để có độ phủ; không tự suy ra coverage khi phối hợp DC options |
| `-st`/`-et` | Giới hạn token range bắt đầu/kết thúc trong phiên bản hỗ trợ | Cần hiểu partitioner/token ring và cách khoảng đầu/cuối được diễn giải |
| `-full` | Chạy full repair, không chỉ dựa vào trạng thái incremental | Có thể tốn nhiều I/O/streaming |
| `-hosts` | Giới hạn participants theo host khi được hỗ trợ | Không thích hợp làm lịch repair toàn cluster nếu vô tình bỏ replica cần thiết |

Với các tùy chọn trên, tham số và quy tắc kết hợp có thể khác giữa Cassandra 3.x, 4.x và 5.x. Hãy chạy:

```bash
nodetool help repair
```

trên **đúng phiên bản đang vận hành** trước khi sao chép một command vào quy trình bảo trì.

### Primary ranges và virtual nodes

Một node có thể sở hữu nhiều token range, đặc biệt khi cluster dùng **vnodes**. Khi bật `-pr`, repair chỉ xử lý các primary ranges theo định nghĩa của phiên bản/cấu hình. Mục đích phổ biến là tránh kiểm tra trùng lặp khi thiết lập lịch repair cho toàn cluster.

Tuy nhiên:

- `-pr` chạy trên **một node** không phải lệnh repair toàn ring.
- Cần tính tập node/range phải chạy để bao phủ toàn bộ keyspace.
- Khi muốn phạm vi nội DC hoặc liên DC, phải kiểm tra tác động của `-pr` cùng các lựa chọn participants.
- Nếu bỏ sót một token range, dữ liệu trong range đó có thể chưa từng được đối chiếu.

Một hệ thống scheduler repair cần theo dõi **thành công theo range/participant**, không chỉ “đã gọi lệnh trên vài node”.

## 7. Full repair và incremental repair có thay đổi ý nghĩa DC không?

Hai khái niệm này trả lời **hai câu hỏi độc lập**:

- **Local hay cross-DC:** *những replica nào được phép tham gia*.
- **Full hay incremental:** *những dữ liệu/SSTable nào được xét trong phiên repair theo trạng thái và cơ chế sửa chữa của phiên bản*.

**Full repair** xét dữ liệu thuộc phạm vi được chọn mà không dựa vào việc dữ liệu đã được đánh dấu repaired bởi incremental repair trước đó. **Incremental repair** quản lý thông tin repaired/unrepaired hoặc pending repair theo cơ chế của phiên bản và tập trung vào dữ liệu chưa được repair theo quy tắc tương ứng.

Không nên hiểu “incremental” là “chỉ sửa các dòng vừa được cập nhật từ lần trước” một cách trực tiếp. Nó có semantics về trạng thái SSTable, session và phiên bản, không đơn giản là quét timestamp ứng dụng.

| Lựa chọn | Câu hỏi cần kiểm tra | Lỗi suy luận thường gặp |
| --- | --- | --- |
| Full + local | Có cần kiểm tra toàn bộ dữ liệu trong phạm vi DC này? | Tưởng đã kiểm tra cả DC khác |
| Incremental + local (khi phiên bản hỗ trợ) | Trạng thái repaired/unrepaired và phạm vi DC được quản lý ra sao? | Tưởng kết quả chắc chắn đồng bộ giữa DC |
| Full + cross-DC | Token ranges và mọi DC liên quan đã được bao phủ chưa? | Tưởng một lần chạy là toàn cluster |
| Incremental + cross-DC | Session, tài nguyên và trạng thái repaired giữa các DC có tương thích lịch không? | Tưởng cứ restart command là an toàn và tương đương full |

Cơ chế, trạng thái phiên repair và mặc định của `nodetool repair` đã thay đổi theo lịch sử Cassandra. Để bài học có thể áp dụng cho nhiều phiên bản, ví dụ command sử dụng `-full` tường minh; **đừng trộn full/incremental tùy tiện trong một lịch vận hành mà chưa hiểu chiến lược quản lý repaired SSTable**.

## 8. Vì sao repair có thể tốn nhiều băng thông và đĩa?

Trong khi repair, node cần đọc dữ liệu/SSTable, xây dựng thông tin validation, xử lý khác biệt và **stream** dữ liệu giữa các replica. Chạy nhiều phiên cùng lúc có thể tranh chấp:

- **Disk I/O:** đọc SSTable, ghi dữ liệu được stream, flush và compaction.
- **CPU/memory:** hashing, validation và các cấu trúc metadata.
- **Network:** đặc biệt đường WAN giữa DC có giới hạn throughput hoặc chi phí egress.
- **Storage headroom:** SSTable mới, tệp tạm và hoạt động compaction liên quan có thể làm tăng dung lượng cần thiết.
- **Foreground latency:** ứng dụng Java vẫn gửi `SELECT`, `INSERT` và `UPDATE`; repair quá nặng có thể làm p95/p99 xấu đi.

Ví dụ: một dải token có khoảng **120 GiB dữ liệu cần đối chiếu**. Không được mặc định “120 GiB sẽ phải truyền qua WAN”: validation có thể tìm ra ít khác biệt, hoặc cũng có nhiều dữ liệu cần stream nếu hai bên lệch đáng kể. Lưu lượng thực tế còn phụ thuộc cách chạy, nén và mức chồng lấp.

### Dấu hiệu cần giảm tốc hoặc chia nhỏ lịch

| Tín hiệu | Diễn giải khả dĩ | Hành động |
| --- | --- | --- |
| WAN gần bão hòa trong cross-DC repair | Streaming/validation cạnh tranh đường truyền | Giảm concurrency và đổi lịch repair |
| p99 đọc/ghi tăng khi repair | I/O/CPU/network bị tranh chấp | So sánh với baseline và giới hạn tác vụ |
| Đĩa gần đầy | Thiếu headroom cho dữ liệu streamed/compacted | Ưu tiên dung lượng, không ép repair tiếp |
| Một node liên tục timeout | Replica quá tải, GC, lỗi mạng/đĩa | Khắc phục sức khỏe node trước |
| Repair session thất bại sau nhiều giờ | Participant gián đoạn hoặc thay đổi topology | Xem log/session/range để quyết định chạy lại đúng phạm vi |

Repair giúp dữ liệu hội tụ, **không thay thế replication** và không làm biến mất mọi nguyên nhân gây timeout. Khi một DC đang mất hoàn toàn, cross-DC repair có thể không thể hoàn tất; cần phục hồi kết nối/tính sẵn sàng trước khi tổ chức repair.

## 9. Tombstone, TTL và yêu cầu không bỏ sót repair quá lâu

Cassandra biểu diễn thao tác xóa bằng **tombstone**. Trong khi một replica còn dữ liệu cũ, tombstone ở replica khác cần được giữ đủ lâu để sự vắng mặt của dữ liệu được lan truyền an toàn qua các cơ chế đồng bộ.

Ví dụ:

```text
T0: dc1 nhận DELETE O1 -> lưu tombstone.
T1: dc2 bị cô lập -> vẫn còn hàng O1 cũ.
T2: dc1 compaction và tombstone được phép bị thu gom
    sau những điều kiện an toàn.
T3: dc2 trở lại, streaming/repair nhưng không còn bằng chứng xóa
    ở một số hoàn cảnh -> nguy cơ dữ liệu cũ xuất hiện lại (zombie).
```

Đó là lý do `gc_grace_seconds`, TTL, lịch repair và thời gian replica offline cần được thiết kế **cùng nhau**. Tùy phiên bản/định dạng và chính sách, có thể có ngoại lệ/tối ưu hóa tombstone; nguyên tắc an toàn vẫn là **không để replica bỏ lỡ xóa vượt quá cửa sổ bảo vệ mà không có quy trình phục hồi phù hợp**.

Hệ quả đặc biệt của cluster nhiều DC:

- Repair local ở dc1 có thể bảo vệ việc lan truyền tombstone giữa R1/R2/R3.
- Nhưng nếu dc2 đã cô lập lâu, **local repair tại dc1 không tự đưa tombstone sang dc2**.
- Repair local riêng dc2 cũng không tự học tombstone ở dc1 nếu toàn bộ dc2 vẫn giữ hàng cũ.
- Vì vậy, **cross-DC repair** và chiến lược khôi phục DC cần được tính vào kế hoạch xử lý khoảng vắng mặt kéo dài.

Không tự giảm `gc_grace_seconds` chỉ vì muốn compaction dọn SSTable nhanh; điều này có thể làm tăng nguy cơ dữ liệu đã xóa xuất hiện lại nếu bỏ sót repair.

## 10. Phân biệt repair với read repair, hints, compaction và backup

| Cơ chế | Phạm vi thường tác động | Nó giúp gì? | Không thay thế |
| --- | --- | --- | --- |
| **Read repair** | Dữ liệu được truy vấn và replica tham gia đọc | Hòa giải, có thể sửa sai khác trên đường đọc | Repair dữ liệu không được đọc |
| **Hinted handoff** | Mutation được lưu hint cho replica tạm vắng trong giới hạn cấu hình | Gửi lại một phần mutation đã bỏ lỡ | Repair toàn bộ khi hint hết hạn/mất |
| **Anti-entropy repair** | Token ranges, bảng và replica được chọn | Đối chiếu/sửa chênh lệch giữa các bản sao | Backup, giao dịch hoặc đảm bảo CL tại mọi thời điểm |
| **Compaction** | SSTable trên **một replica** | Hợp nhất dữ liệu cục bộ, xử lý phiên bản/tombstone an toàn | Đồng bộ replica/DC |
| **Backup/snapshot** | Bản lưu dữ liệu để khôi phục | Phục hồi sau mất dữ liệu hoặc sự cố nghiêm trọng | Repair để đối chiếu các bản sao hiện hữu |

Đừng nghĩ `LOCAL_QUORUM` + read repair luôn đủ bù cho repair vận hành. Partition ít khi được đọc có thể không kích hoạt read repair trong nhiều tháng; dữ liệu đó vẫn cần nằm trong lịch anti-entropy repair.

## 11. Ví dụ CQL: keyspace hai DC và truy vấn theo partition

Ví dụ mô tả cụm có DC tên `dc1` và `dc2`, **mỗi DC có đủ ba node**. Nếu lab có một DC hoặc không đủ node, phải sửa tên DC/RF theo topology thực tế trước khi chạy:

```sql
CREATE KEYSPACE IF NOT EXISTS repair_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS repair_lab.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id text,
    status text,
    updated_at timestamp
);
```

Truy vấn dùng đúng partition key:

```sql
INSERT INTO repair_lab.orders_by_id
    (order_id, customer_id, status, updated_at)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'customer-42',
    'PENDING',
    '2026-11-20 09:00:00+0000'
);

UPDATE repair_lab.orders_by_id
SET status = 'PAID',
    updated_at = '2026-11-20 09:05:00+0000'
WHERE order_id = 11111111-1111-4111-8111-111111111111;

SELECT order_id, status, updated_at
FROM repair_lab.orders_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

Trong `cqlsh`, có thể đặt:

```text
CONSISTENCY LOCAL_QUORUM;
```

Khi quan sát ở dc1 và dc2, cần kết nối client tới coordinator của **đúng DC** rồi chạy truy vấn với `LOCAL_QUORUM` để hiểu phạm vi đọc. **Không tạo chênh lệch bằng cách cố tình xóa SSTable/commit log hoặc làm gián đoạn node production.** Mọi thí nghiệm fault injection chỉ nên thực hiện trên cluster lab cô lập.

### Tại sao một câu `SELECT` không thay thế repair?

`SELECT ... WHERE order_id = ?` chỉ yêu cầu partition đó. Nó không đồng bộ những order khác không được đọc. Nếu bảng sử dụng `read_repair = 'BLOCKING'` trên Cassandra 4.x, read repair có thể xảy ra khi phát hiện mismatch; tuy nhiên phạm vi của nó vẫn khác anti-entropy repair theo token range và theo participants đã chọn.

## 12. Playbook vận hành: chọn local hay cross-DC

Trước khi chạy một đợt repair, nên trả lời các câu hỏi và lưu lại kết quả:

### Bước 1 — Xác minh topology

```bash
nodetool status
nodetool describecluster
```

Kiểm tra tên DC thực tế, trạng thái Up/Down/Normal của node, số replica theo keyspace và khả năng kết nối giữa các DC. Đầu ra `nodetool status` không thay thế việc kiểm tra schema replication của keyspace; cần đối chiếu hai nguồn bằng công cụ quản trị thích hợp.

Nếu đang thay đổi topology, rebuild, decommission hoặc có node lỗi nặng, cần tuân theo runbook vận hành tương ứng trước khi đưa repair quy mô lớn vào lịch.

### Bước 2 — Xác định mục tiêu và phạm vi

| Câu hỏi | Quyết định cần ghi lại |
| --- | --- |
| Muốn sửa lệch giữa replica trong DC hay giữa các DC? | `-local`, participants DC được chọn hoặc cross-DC |
| Keyspace/bảng nào có dữ liệu quan trọng? | Danh sách keyspace/table và RF |
| Token ranges nào cần cover? | Danh sách node/range, có hoặc không dùng `-pr` |
| Full hay incremental theo phiên bản? | Chính sách repair và trạng thái repaired SSTable |
| Cửa sổ bảo trì đủ không? | Bandwidth WAN, đĩa, CPU, p99 SLA, thời gian |
| Có tombstone/replica offline lâu không? | Xem lịch repair cuối và `gc_grace_seconds` |

### Bước 3 — Đo baseline

```bash
nodetool tablestats repair_lab.orders_by_id
nodetool compactionstats
nodetool netstats
```

Tùy phiên bản, các lệnh này giúp quan sát kích thước bảng, I/O liên quan và streaming đang diễn ra. Đồng thời đo network throughput, disk latency, CPU/GC, p95/p99 của client và free space bằng giám sát hệ thống.

### Bước 4 — Thực thi trong phạm vi kiểm soát

**Trường hợp A: chỉ cần sửa giữa replica trong dc1.** Từ node thuộc dc1, với full repair minh họa:

```bash
nodetool repair -full -local repair_lab orders_by_id
```

**Trường hợp B: cần so sánh giữa dc1 và dc2.** Từ node phù hợp trong cluster, khi đã chuẩn bị WAN headroom và kiểm tra trợ giúp phiên bản:

```bash
nodetool repair -full repair_lab orders_by_id
```

Hai lệnh trên chỉ là **một bước trên một node**; lập lịch đủ những node/range cần thiết để đạt coverage mong muốn. Không chạy cả hai lệnh liên tiếp một cách máy móc: lựa chọn phải dựa vào mục tiêu và trạng thái dữ liệu.

### Bước 5 — Theo dõi và xác minh

Ghi lại theo từng session: node điều phối, keyspace/table, token ranges, participants/DC, loại full/incremental, thời gian bắt đầu/kết thúc, trạng thái thành công/lỗi và lượng dữ liệu stream nếu có.

Kiểm tra:

- Repair có hoàn tất **toàn bộ phạm vi dự kiến** hay chỉ một phần?
- Có lỗi timeout/streaming, disk full, node down hoặc session thất bại không?
- Có tăng p99 đọc/ghi trong giờ cao điểm không?
- Các node/range còn lại đã được lên lịch, hay mới chỉ có một node hoàn tất?
- Dữ liệu tombstone/TTL có yêu cầu lịch repair sớm hơn không?

Nếu một session thất bại, **đừng đánh dấu toàn bộ keyspace là đã repair**. Xem log, xác định range/participant nào chưa thành công và áp dụng cơ chế retry/phục hồi phù hợp phiên bản. Tránh khởi động hàng loạt phiên repair trùng nhau trên cùng dữ liệu.

## 13. Java Driver: CL địa phương không có nghĩa dữ liệu liên DC đã hội tụ

Ứng dụng Java Driver 4.x thường đặt `local datacenter` khi cấu hình session để chọn coordinator gần ứng dụng. Cài đặt đó và **consistency level** quyết định đường yêu cầu, nhưng không thay thế anti-entropy repair.

Ví dụ repository đọc một order:

```java
import java.util.Optional;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class OrderRepository {
    private final CqlSession session;
    private final PreparedStatement selectStatus;

    public OrderRepository(CqlSession session) {
        this.session = session;
        this.selectStatus = session.prepare(
            "SELECT status FROM repair_lab.orders_by_id WHERE order_id = ?"
        );
    }

    public Optional<String> findStatus(UUID orderId) {
        BoundStatement statement = selectStatus.bind(orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        Row row = session.execute(statement).one();
        return row == null || row.isNull("status")
            ? Optional.empty()
            : Optional.of(row.getString("status"));
    }
}
```

Nếu ứng dụng A ở dc1 và ứng dụng B ở dc2 cùng dùng `LOCAL_QUORUM`, chúng có thể quan sát những trạng thái khác nhau **trong lúc các DC chưa hội tụ**. Đọc và ghi tại từng DC còn phụ thuộc timing, replica đang sẵn sàng, timestamp và chiến lược nhất quán; không được giải quyết vấn đề chỉ bằng việc nâng timeout của driver.

Nếu nghiệp vụ yêu cầu CAS để tránh cập nhật tranh chấp, có thể dùng **LWT** (`INSERT ... IF NOT EXISTS` hoặc `UPDATE ... IF`) với serial consistency phù hợp, nhưng LWT **không thay thế lịch anti-entropy repair** của dữ liệu thông thường và cần phân tích riêng phạm vi `SERIAL`/`LOCAL_SERIAL`.

## 14. Bốn tình huống tự đánh giá

### Tình huống 1 — Mỗi DC tự nhất quán nhưng kết quả khác nhau

dc1 có ba replica `PAID`; dc2 có ba replica `PENDING`. Quản trị viên chạy local full repair thành công trên mọi node/range của từng DC. Có thể kết luận hai DC giống nhau không?

**Đáp án:** Không. Các phiên local không so sánh dữ liệu giữa hai DC. Cần repair với participants và token ranges bao phủ cả hai DC nếu mục tiêu là hội tụ liên DC.

### Tình huống 2 — Lịch repair chỉ chạy trên một node

Cụm dùng vnodes, keyspace lớn. Một node ở dc1 chạy `nodetool repair -full -local repair_lab orders_by_id` rồi trả exit code thành công. Có được báo cáo “toàn bộ keyspace đã repair” không?

**Đáp án:** Không. Cần kiểm tra dải token mà node đó repair và phạm vi participants; lập lịch để toàn bộ range quan trọng được bao phủ. Thêm `-pr` mà không có kế hoạch coverage cũng không giải quyết vấn đề.

### Tình huống 3 — WAN đang bão hòa

Một đợt cross-DC full repair chạy cùng lúc với peak traffic. WAN gần bão hòa, p99 của API tăng cao. Có nên chạy thêm repair song song để hoàn thành nhanh?

**Đáp án:** Không. Cần bảo vệ SLA và headroom, điều chỉnh lịch/concurrency/khối lượng từng phiên sau khi xem throughput và lỗi. Thêm luồng song song lên đường WAN đã bão hòa thường làm tình hình tệ hơn.

### Tình huống 4 — DC offline dài ngày và có nhiều DELETE

dc2 offline qua thời gian bảo vệ tombstone; dc1 tiếp tục xóa dữ liệu. Sau khi dc2 trở lại, chỉ chạy local repair dc2. Rủi ro?

**Đáp án:** dc2 có thể chỉ so sánh các replica còn dữ liệu cũ trong DC của mình, không nhận được tombstone từ dc1. Khi tombstone đã bị thu gom ở các bản sao thích hợp, nguy cơ zombie data có thể xuất hiện. Cần runbook phục hồi DC và chiến lược đối chiếu xuyên DC/thời điểm phục hồi dữ liệu an toàn, không phụ thuộc local repair đơn lẻ.

## 15. Checklist vận hành và ghi nhớ

- [ ] Biết **RF theo từng DC**, tên datacenter và vai trò coordinator trong mỗi lượt đọc/ghi.
- [ ] Hiểu `LOCAL_QUORUM` chỉ quyết định điều kiện phản hồi tại DC địa phương, không xác nhận mọi DC đã hội tụ.
- [ ] Phân biệt **repair nội DC** với **repair liên DC** qua tập replica tham gia.
- [ ] Xác định đầy đủ **keyspace, table, token range, node và participants** cho mỗi đợt repair.
- [ ] Không hiểu một `nodetool repair` trên một node là repair toàn cluster.
- [ ] Kiểm tra `nodetool help repair` ở đúng phiên bản trước khi dùng `-local`, `-dc`, `-pr` hoặc full/incremental.
- [ ] Giám sát **WAN bandwidth, disk I/O, CPU, p95/p99, disk free** khi chạy cross-DC repair.
- [ ] Lập lịch repair để phòng chênh lệch kéo dài, nhất là khi có DELETE/TTL và replica từng offline.
- [ ] Đừng dùng read repair, hinted handoff, compaction hoặc backup như vật thay thế cho anti-entropy repair.
- [ ] Với ứng dụng Java, dùng prepared statement và CL có chủ đích; đánh giá nhất quán giữa DC theo yêu cầu nghiệp vụ.
- [ ] Ghi nhận range/session thành công, xử lý những phạm vi thất bại thay vì công bố “repair xong” theo số lệnh đã gọi.

**Ghi nhớ:** Repair trong **một datacenter** giúp đồng bộ replica trong phạm vi DC được chọn và thường giảm tải WAN. Repair **giữa các datacenter** cần thiết để phát hiện những chênh lệch mà từng DC tự nó không nhìn thấy, nhưng tốn tài nguyên mạng và phải lên lịch cẩn thận. Dù chọn cách nào, phạm vi thực tế vẫn phụ thuộc **token range, bảng, participants và chế độ repair**, nên không thể đánh đồng “một lệnh thành công” với “toàn bộ cluster đã nhất quán”.
