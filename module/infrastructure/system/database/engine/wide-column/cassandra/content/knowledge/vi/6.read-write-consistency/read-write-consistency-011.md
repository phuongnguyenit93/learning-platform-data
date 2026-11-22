# Ảnh hưởng của lỗi nút, mạng chậm và unavailable đến từng lựa chọn

Trong Apache Cassandra, một request thành công hay thất bại không chỉ phụ thuộc **bao nhiêu node của cluster còn chạy**. Điều quan trọng hơn là: **còn bao nhiêu replica của đúng partition, trong đúng phạm vi datacenter, có thể phản hồi kịp để thỏa consistency level (CL)?** Một replica bị tắt, một đường mạng chậm và một datacenter bị cô lập có thể tạo ra các kết quả rất khác nhau dù ứng dụng gửi cùng câu CQL.

Bài này nằm trong chương **Nhất quán đọc/ghi** của mô-đun `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Bên cạnh kiến trúc phân tán và mô hình wide-column, partition key, thiết kế bảng theo truy vấn, CQL, replication, compaction, repair, xử lý lỗi và kết nối từ ứng dụng Java, nội dung tập trung vào **tác động của lỗi nút, độ trễ mạng và trạng thái unavailable đối với từng lựa chọn CL**.

> **Phân biệt quan trọng:** **`Unavailable`** thường chỉ việc coordinator xác định không có đủ replica *được coi là đang hoạt động* để đáp ứng CL. **`Timeout`** thường chỉ việc thao tác không thu đủ phản hồi hoặc không hoàn tất đúng hạn. **Cả hai không chứng minh dữ liệu đã mất, cũng không chứng minh mutation chắc chắn chưa được áp dụng.**

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Tính ngưỡng replica phải phản hồi cho `ONE`, `TWO`, `THREE`, `QUORUM`, `ALL`, `LOCAL_ONE`, `LOCAL_QUORUM` và `EACH_QUORUM`.
2. Phân biệt sự cố **node down**, **network partition**, **mạng chậm**, **replica quá tải** và **coordinator mất kết nối**.
3. Dự đoán CL nào có khả năng thành công với những phân bố replica còn hoạt động cụ thể.
4. Phân biệt `UnavailableException`, `ReadTimeoutException`, `WriteTimeoutException`, lỗi replica và timeout phía driver.
5. Giải thích vì sao một yêu cầu ghi thất bại theo CL vẫn có thể được một số replica áp dụng.
6. Hiểu vai trò của hinted handoff, read repair, anti-entropy repair và khả năng đọc dữ liệu cũ sau sự cố.
7. Thực hành chọn CL ở `cqlsh` và xử lý lỗi đúng hướng với Java Driver 4.x.

## 2. Điều kiện tiên quyết: RF, coordinator và replica của partition

Đầu tiên cần phân biệt **node của cluster** với **replica đích của partition**:

- **Partition key** quyết định partition; cơ chế phân bố token và replication strategy xác định các replica lưu partition đó.
- **Replication factor (RF)** quy định số bản sao của mỗi partition trong một DC hoặc trong tập replica được cấu hình.
- **Coordinator** là node nhận và điều phối request. Nó có thể là một replica đích, nhưng **không bắt buộc**.
- **Consistency level** quy định *số lượng và phạm vi* những phản hồi cần có trước khi coordinator báo thành công.

Giả sử một keyspace có `NetworkTopologyStrategy`:

```text
                    Cassandra cluster

dc1 — RF = 3                    dc2 — RF = 3
  A1  A2  A3                      B1  B2  B3
  |   |   |                       |   |   |
  +---+---+---- partition P ------+---+---+

Một partition P có 6 replica đích.
Coordinator C ở dc1 nhận request từ ứng dụng.
```

Nếu `A3` bị tắt, không nên chỉ hỏi “cluster có còn năm node không?” mà phải hỏi **năm replica đích còn lại thuộc DC nào, CL đang đòi ACK từ đâu và request đi qua coordinator nào**.

**Giả định dùng trong các bảng:** các replica là bản sao đầy đủ thông thường, topology/RF ổn định, request nhắm cùng partition và coordinator còn hoạt động. Các phép đếm thể hiện **khả năng đạt ngưỡng về mặt số lượng**; một thao tác vẫn có thể lỗi do timeout, tải, phân bố mạng, permission hoặc sự cố khác.

## 3. Công thức đếm và các mức nhất quán cần phân biệt

Đa số tuyệt đối của `N` replica là:

\[
Q(N)=\left\lfloor \frac{N}{2} \right\rfloor+1
\]

Với topology `dc1: RF=3`, `dc2: RF=3`:

| CL | Replica phải phản hồi | Phạm vi | Dùng cho |
| --- | --- | --- | --- |
| `ONE` | **1** replica đích | Bất kỳ replica phù hợp trong tập toàn cục | Đọc và ghi |
| `TWO` | **2** replica đích | Tập replica toàn cục | Đọc và ghi |
| `THREE` | **3** replica đích | Tập replica toàn cục | Đọc và ghi |
| `QUORUM` | **`Q(6)=4`** | Đa số của tổng sáu replica | Đọc và ghi |
| `ALL` | **6** replica đích | Mọi replica của partition | Đọc và ghi |
| `LOCAL_ONE` | **1** replica ở DC coordinator | Chỉ local DC | Đọc và ghi |
| `LOCAL_QUORUM` | **`Q(3)=2`** ở DC coordinator | Chỉ local DC | Đọc và ghi |
| `EACH_QUORUM` | **2 ACK ở dc1 và 2 ACK ở dc2** | Quorum riêng trong từng DC | **Ghi thông thường**; không dùng cho đọc thông thường trong Cassandra OSS |
| `SERIAL` / `LOCAL_SERIAL` | Quorum Paxos toàn cục / local | Phạm vi đồng thuận của LWT | **Pha serial/LWT**, không phải CL ghi thường thay cho các hàng trên |

`ONE`, `TWO` và `THREE` yêu cầu *số lượng ACK cố định*; chúng **không tự tăng** khi RF tăng. `QUORUM` và `LOCAL_QUORUM` thì được tính lại theo RF của đúng phạm vi.

`LOCAL_ONE` không phải đồng nghĩa `ONE`: với coordinator ở `dc1`, một phản hồi duy nhất từ `dc2` có thể thỏa `ONE`, nhưng **không** thỏa `LOCAL_ONE`. Tương tự, `QUORUM` toàn cục **không yêu cầu** quorum riêng ở từng DC, còn `EACH_QUORUM` thì có.

## 4. Các dạng sự cố và phản ứng của Cassandra

### 4.1. Node down hoặc replica bị xem là down

Replica có thể ngừng chạy, reboot, lỗi disk hoặc không còn giao tiếp được. Các node Cassandra sử dụng cơ chế theo dõi liveness/failure detector để đánh giá trạng thái của node khác. Coordinator có thể biết **không đủ replica được coi là đang hoạt động** cho CL ngay từ đầu và trả về lỗi unavailable.

Ví dụ một DC RF=3, chỉ còn một replica được coi là sống:

```text
R1: UP
R2: DOWN
R3: DOWN

Ghi/đọc ONE:      có thể đạt 1 ACK
Ghi/đọc QUORUM:   cần 2 ACK -> không đủ replica
Ghi/đọc ALL:      cần 3 ACK -> không đủ replica
```

Đây là bài toán **khả dụng theo ngưỡng**. Không được suy rằng hai replica down đồng nghĩa dữ liệu trên đĩa của chúng đã mất.

### 4.2. Node còn sống nhưng phản hồi chậm

Replica vẫn được coordinator xem là sống nhưng đang:

- bận với compaction, flush, GC, CPU hoặc đĩa;
- bị nghẽn request queue;
- gặp độ trễ mạng cao hoặc mất gói;
- đang xử lý read repair/reconciliation cần thêm thời gian.

Coordinator có thể gửi request thành công tới các replica, nhưng **không thu đủ phản hồi kịp server timeout**. Khi đó client có thể nhận `ReadTimeoutException` hoặc `WriteTimeoutException` thay vì `UnavailableException`.

**Điểm mấu chốt:** `Unavailable` liên quan đến đánh giá **không có đủ replica sẵn sàng**; `Timeout` liên quan đến **không hoàn tất đủ phản hồi đúng hạn**, kể cả khi replica vẫn được đánh dấu UP.

### 4.3. Network partition hoặc DC xa không liên lạc được

Một nhóm node vẫn chạy khỏe mạnh nhưng không thể liên lạc với nhóm khác. Hai nhóm có thể có đánh giá liveness không giống nhau do vị trí mạng; cùng một CL có thể được thực hiện thành công ở vùng này nhưng thất bại ở vùng kia.

Ví dụ `dc1` RF=3 vẫn khỏe, `dc2` RF=3 bị cô lập:

- `LOCAL_ONE` / `LOCAL_QUORUM` từ coordinator `dc1`: **vẫn có thể thành công** nếu các replica `dc1` phản hồi.
- `QUORUM` toàn cluster: cần **4/6**, trong khi `dc1` tối đa có **3** phản hồi; **không thể đạt** nếu không nhận được phản hồi từ `dc2`.
- Ghi `EACH_QUORUM`: cần **hai ACK từ dc2**, nên không đạt khi DC này không liên lạc được.
- `ALL`: cần đủ cả sáu replica, nên không đạt.

Mạng chia cắt không đồng nghĩa toàn cụm mất dữ liệu; nó thay đổi **những replica có thể cùng tham gia xác nhận request tại thời điểm đó**.

### 4.4. Coordinator lỗi hoặc client không kết nối được

Nếu coordinator chết trước khi phản hồi, client có thể nhận lỗi kết nối hoặc timeout **dù các replica vẫn đủ số lượng**. Đây là vấn đề đường đi request/coordinator, không nhất thiết là “CL quá mạnh”.

Driver có thể thử host khác theo chính sách routing/retry; nhưng với ghi, coordinator cũ có thể đã chuyển mutation cho một số replica trước khi mất kết nối. Vì vậy lần thử lại phải xem xét **tính idempotent**.

## 5. Ma trận một datacenter: RF=3 và số replica khả dụng

Giả sử có ba replica của partition trong một DC; các replica được liệt kê là **đang phản hồi đúng hạn** và coordinator vẫn phục vụ request.

| Replica phản hồi | `ONE` / `LOCAL_ONE` | `TWO` | `THREE` | `QUORUM` | `LOCAL_QUORUM` | `ALL` |
| ---: | --- | --- | --- | --- | --- | --- |
| 3/3 | Có thể đạt | Có thể đạt | Có thể đạt | Có thể đạt | Có thể đạt | Có thể đạt |
| 2/3 | Có thể đạt | Có thể đạt | **Không đủ** | Có thể đạt | Có thể đạt | **Không đủ** |
| 1/3 | Có thể đạt | **Không đủ** | **Không đủ** | **Không đủ** | **Không đủ** | **Không đủ** |
| 0/3 | **Không đủ** | **Không đủ** | **Không đủ** | **Không đủ** | **Không đủ** | **Không đủ** |

Với RF=3, quorum cần `floor(3/2)+1=2`. Cặp đọc và ghi `QUORUM` có ngưỡng đủ nếu còn hai replica hoạt động, nhưng không phải cứ hai node UP là request chắc chắn thành công: **một trong hai phản hồi chậm quá hạn vẫn có thể gây timeout**.

Khi có 0 replica đích khả dụng nhưng **một coordinator không thuộc tập replica vẫn chạy và lưu được hint**, ghi `ANY` **có thể** thành công nhờ hint. Điều này **không** đúng cho đọc và không bảo đảm dữ liệu đã tồn tại trên replica để đọc lại.

### Đánh đổi độ trễ và khả dụng

- `ONE` cần ít phản hồi nhất, thường có **khả năng duy trì phục vụ** tốt khi chỉ một replica đích còn khỏe. Nhưng đọc có thể thấy bản cũ nếu replica được hỏi chưa nhận mutation.
- `TWO` ở RF=3 vẫn có thể chịu một replica không phản hồi; đổi lại, phải đợi hai phản hồi.
- `THREE` và `ALL` ở RF=3 cùng cần cả ba phản hồi; một replica down/chậm đủ để khiến thao tác không đạt ngưỡng đúng hạn.
- `QUORUM` ở RF=3 tương đương ngưỡng hai ACK, tạo một điểm cân bằng thường dùng giữa xác nhận đọc/ghi và số replica chịu lỗi.

**Không suy độ trễ tuyệt đối chỉ từ CL:** `ONE` vẫn có thể chậm khi replica được chọn quá tải; `QUORUM` có thể hoàn tất nhanh khi hai replica trả lời sớm. Các cơ chế chọn replica, speculative read, batching, coordinator và thời gian reconciliation đều ảnh hưởng thực tế.

## 6. Ma trận hai datacenter: RF=3+3, coordinator ở dc1

Giả sử **số trong bảng là số replica của partition có thể phản hồi kịp thời** ở từng DC. Coordinator đang chạy trong `dc1` và đường mạng phù hợp với những phản hồi được đếm.

| Replica dc1 | Replica dc2 | `LOCAL_ONE` | `LOCAL_QUORUM` | `QUORUM` toàn cục | Ghi `EACH_QUORUM` | `ALL` |
| ---: | ---: | --- | --- | --- | --- | --- |
| 3 | 3 | Có | Có | Có (6≥4) | Có (3≥2 và 3≥2) | Có |
| 2 | 3 | Có | Có | Có (5≥4) | Có (2+3) | **Không** |
| 1 | 3 | Có | **Không** | Có (4≥4) | **Không** | **Không** |
| 3 | 0 | Có | Có | **Không** (3<4) | **Không** | **Không** |
| 2 | 1 | Có | Có | **Không** (3<4) | **Không** | **Không** |
| 1 | 0 | Có | **Không** | **Không** | **Không** | **Không** |

**Đọc bảng:** “Có” nghĩa là **đủ số lượng và phạm vi replica để có thể thành công**, không phải kết quả chắc chắn. Nếu mạng chậm, server lỗi hoặc coordinator mất kết nối, một request ở ô “Có” vẫn có thể timeout.

### Vì sao `QUORUM` đôi lúc đạt mà `LOCAL_QUORUM` không đạt?

Ở hàng `dc1=1, dc2=3`:

- `LOCAL_QUORUM` với coordinator `dc1` cần **hai ACK ở dc1**, nhưng chỉ có một → không đạt.
- `QUORUM` toàn cục cần **bốn ACK bất kỳ trên sáu replica**, có thể lấy 1 ở `dc1` và 3 ở `dc2` → đủ ngưỡng.

Do đó `QUORUM` không thể được mô tả đơn giản là “lúc nào cũng mạnh hơn và khó đạt hơn `LOCAL_QUORUM`”. Hai mức có **phạm vi khác nhau**.

### Ghi `EACH_QUORUM` có thể khó hơn `QUORUM`

Ở cùng trường hợp `dc1=1, dc2=3`, tổng bốn ACK thỏa `QUORUM` nhưng **không** thỏa `EACH_QUORUM`: `dc1` bắt buộc có **hai ACK**. Ghi `EACH_QUORUM` luôn phải xét **từng DC riêng**, không chỉ cộng số node toàn cụm.

### Mất hoàn toàn dc2

Nếu `dc1` còn ba replica và `dc2` không liên lạc được, ứng dụng điều phối ở `dc1` thường còn lựa chọn **`LOCAL_ONE` hoặc `LOCAL_QUORUM`**. Chuyển từ `QUORUM` sang `LOCAL_QUORUM` để xử lý sự cố, tuy nhiên, **thay đổi phạm vi nhất quán mà ứng dụng nhận được**: các ghi được xác nhận local không bảo đảm một client ở `dc2` lập tức đọc thấy mutation sau khi DC đó phục hồi.

**Không tự động hạ CL khi gặp lỗi** nếu nghiệp vụ đòi bảo đảm chéo DC. Giảm CL có thể giúp tăng availability nhưng làm thay đổi kỳ vọng về độ mới và số replica đã xác nhận.

## 7. RF không cân bằng và tác động khác thường khi mất WAN

Xét hai topology khác nhau, coordinator ở `dc1`.

### 7.1. RF = 3+2

`N_total=5` nên `QUORUM=3`; `LOCAL_QUORUM(dc1)=2`; `LOCAL_QUORUM(dc2)=2`; ghi `EACH_QUORUM` cần `2 ở dc1 và 2 ở dc2`.

Nếu `dc2` bị cô lập nhưng ba replica `dc1` vẫn hoạt động:

- `QUORUM` toàn cụm **có thể đạt 3/5 hoàn toàn từ dc1**.
- `LOCAL_QUORUM` ở `dc1` **có thể đạt 2/3**.
- `EACH_QUORUM` **không đạt**, vì dc2 cần 2 ACK.
- `ALL` **không đạt**, vì cần cả năm.

Như vậy **không phải mọi `QUORUM` nhiều DC đều bắt buộc có ACK WAN**; còn tùy RF của mỗi DC.

### 7.2. RF = 5+1

`N_total=6`, `QUORUM=4`, `LOCAL_QUORUM(dc1)=3`, còn `EACH_QUORUM` ghi cần `3 ở dc1 và 1 ở dc2`.

Nếu toàn bộ `dc2` mất kết nối nhưng `dc1` còn năm replica:

- `QUORUM` **có thể đạt** bằng bốn ACK trong dc1.
- `LOCAL_QUORUM` **có thể đạt** bằng ba ACK trong dc1.
- `EACH_QUORUM` **không đạt** do dc2 có 0 ACK.

Điểm cần rút ra là **tổng RF và phân bố RF quyết định khả năng chịu lỗi**, không chỉ số lượng DC.

## 8. Mạng chậm: Unavailable, Timeout và Failure khác nhau thế nào?

### 8.1. `UnavailableException`

Coordinator dựa trên trạng thái replica mà nó biết để xác định **không đủ replica sống cho CL yêu cầu**. Ví dụ RF=3, CL=`QUORUM` cần hai replica, nhưng chỉ một replica đích được xem là sống. Khi đó request có thể bị từ chối với `UnavailableException` **trước khi hoàn tất đường đọc/ghi**.

Lỗi này nói về **ngưỡng sẵn sàng theo đánh giá của coordinator**, không phải kết luận dữ liệu chưa từng tồn tại.

### 8.2. `ReadTimeoutException`

Đủ replica có thể được xem là sống khi request bắt đầu, nhưng coordinator **không thu đủ phản hồi đọc cần thiết hoặc chưa nhận được dữ liệu cần để trả kết quả đúng hạn**.

Ví dụ RF=3, đọc `QUORUM`, coordinator gửi request tới hai replica UP; một phản hồi chậm hoặc bước lấy dữ liệu sau digest mismatch vượt quá thời gian cho phép.

Một số phiên bản/protocol cho biết số phản hồi đã nhận, số cần có và liệu đã nhận được data response hay chưa. **Không nên đồng nhất “đã nhận đủ digest/phản hồi” với “đã có dữ liệu để trả client”**.

### 8.3. `WriteTimeoutException`

Coordinator **không xác nhận được đủ phản hồi ghi theo CL trước deadline**. Ví dụ RF=3, ghi `QUORUM`:

```text
Replica A: đã ghi mutation và ACK
Replica B: có thể đã ghi nhưng ACK tới muộn
Replica C: không phản hồi

Coordinator không đủ 2 ACK đúng hạn -> WriteTimeout
```

**Tuyệt đối không suy “WriteTimeout tức là không có replica nào ghi”.** Mutation có thể đã được một phần hoặc nhiều replica áp dụng. Retry phải được cân nhắc trên cơ sở tính idempotent và trạng thái nghiệp vụ.

### 8.4. `ReadFailureException` và `WriteFailureException`

Ngoài việc phản hồi chậm, replica còn có thể **báo lỗi khi xử lý** request, khiến yêu cầu không đáp ứng được CL. Các nguyên nhân có thể bao gồm vấn đề tài nguyên, đĩa hoặc lỗi xử lý dữ liệu; cần quan sát lỗi cụ thể trên node và metrics thay vì suy đoán chung.

### 8.5. Timeout phía driver và lỗi kết nối

Driver còn có deadline/request timeout riêng. Nếu **driver hết thời gian chờ**, client có thể nhận `DriverTimeoutException` hoặc lỗi tổng hợp không kết nối/không sử dụng được các host như `AllNodesFailedException` (tùy đường lỗi và driver). Đây **không đồng nghĩa** với một server-side `UnavailableException`.

| Lỗi quan sát | Vấn đề chủ yếu | Điều không được khẳng định |
| --- | --- | --- |
| `UnavailableException` | Coordinator thấy không đủ replica sống theo CL. | “Dữ liệu đã mất.” |
| `ReadTimeoutException` | Đọc không hoàn tất điều kiện phản hồi/dữ liệu đúng hạn. | “Tất cả replica đều down.” |
| `WriteTimeoutException` | Ghi không được xác nhận đủ CL trước deadline. | “Mutation chắc chắn chưa ghi.” |
| `ReadFailureException` / `WriteFailureException` | Replica báo lỗi xử lý; yêu cầu không đạt CL. | “Chỉ cần tăng timeout là hết lỗi.” |
| Driver/request timeout | Client chưa nhận kết quả trước giới hạn của nó. | “Server không áp dụng mutation.” |
| Mất coordinator/kết nối host | Đường gửi/nhận request bị lỗi. | “Các replica của partition đều không sẵn sàng.” |

**Thứ tự chẩn đoán:** trước tiên xác định **lỗi do ai phát ra** (server/coordinator hay driver), tiếp theo kiểm tra **CL + RF + local DC**, rồi mới đánh giá thời gian chờ, mạng và node.

## 9. Đọc và ghi khi replica lệch dữ liệu sau sự cố

Đủ ngưỡng ACK không đồng nghĩa tất cả replica có cùng phiên bản ngay tại thời điểm đó.

### 9.1. Đọc `ONE` có thể cũ

RF=3: ghi `QUORUM` đã thành công trên `A,B`, replica `C` đang chậm và chưa nhận mutation. Một lần đọc `ONE` lấy dữ liệu từ `C` có thể trả giá trị cũ:

```text
Ghi PAID:  A=PAID   B=PAID   C=CREATED
             ACK      ACK       chưa cập nhật

Đọc ONE từ C -> có thể thấy CREATED
```

Đây là **đánh đổi về độ mới**. Không phải lỗi toàn vẹn dữ liệu chỉ vì mọi request đều trả thành công ở CL thấp.

### 9.2. Quorum đọc và ghi cùng phạm vi

Nếu RF=3, ghi `QUORUM` thành công từ hai replica, đọc `QUORUM` sau đó cũng cần hai replica. Vì:

\[
R+W=2+2=4>3
\]

nên tập xác nhận ghi và phản hồi đọc phải giao nhau. Khi không có ghi cạnh tranh và các điều kiện về timestamp/reconciliation được đáp ứng, đây là cơ sở để kỳ vọng lần đọc thấy mutation đã xác nhận.

**Ngoại lệ quan trọng:** công thức này chỉ áp dụng trực tiếp trên **cùng tập replica**. Ghi `LOCAL_QUORUM` trong `dc1` rồi đọc `LOCAL_QUORUM` trong `dc2` không bảo đảm giao nhau, dù cả hai bên đều dùng quorum local.

### 9.3. `ANY` và hinted handoff

`ANY` chỉ dành cho **ghi**. Khi không replica đích nào đáp ứng nhưng coordinator **lưu được hint**, request ghi vẫn **có thể thành công**. Một hint không phải replica đích đã xác nhận ghi; dữ liệu có thể **chưa đọc được** cho tới khi mutation được phát lại.

Hinted handoff hỗ trợ chuyển mutation bị bỏ lỡ khi replica phục hồi, nhưng chỉ là cơ chế **best effort**. Các trường hợp node down lâu, hint bị mất hoặc thay topology cần có **anti-entropy repair** và quy trình vận hành phù hợp. Compaction quản lý SSTable/tombstone, **không thay thế repair**.

## 10. SERIAL/LOCAL_SERIAL: lỗi ảnh hưởng thế nào đến LWT?

Các CL `SERIAL` và `LOCAL_SERIAL` điều khiển phạm vi **đồng thuận Paxos** của lightweight transaction (LWT), chẳng hạn `INSERT ... IF NOT EXISTS` hoặc `UPDATE ... IF ...`. Chúng **không** thay thế các mức phản hồi ghi thường.

Với RF=`3+3`:

- `SERIAL` dùng phạm vi quorum Paxos **toàn cluster**, tương ứng quorum của sáu replica là **4**.
- `LOCAL_SERIAL` dùng phạm vi quorum Paxos **DC của coordinator**, tương ứng quorum của ba replica là **2**.
- Normal CL của LWT, ví dụ `QUORUM` hoặc `LOCAL_QUORUM`, là một lựa chọn **riêng** với serial CL.

Nếu DC xa bị cô lập, LWT dùng `SERIAL` toàn cục có thể không đủ quorum Paxos, còn `LOCAL_SERIAL` trong DC còn khỏe có thể đạt quorum local. Nhưng **không được tự coi hai local serial quorum trong hai DC khác nhau là một quyết định thống nhất toàn cụm**.

### Một timeout LWT không có nghĩa điều kiện không được áp dụng

Paxos có nhiều pha trao đổi. Nếu client bị timeout ở pha serial hoặc sau khi commit đã bắt đầu, trạng thái cuối cùng có thể **chưa rõ** đối với client. Retry `INSERT ... IF NOT EXISTS` có thể nhận `[applied]=false` vì **lần trước đã tạo hàng** nhưng phản hồi bị mất. Cần giữ định danh request và đối soát trạng thái, không chỉ retry vô điều kiện.

**Lưu ý:** `EACH_QUORUM` là CL **ghi thông thường**, không phải mức serial Paxos. Không thay thế `SERIAL`/`LOCAL_SERIAL` bằng `EACH_QUORUM` khi bài toán cần compare-and-set.

## 11. Thực hành CQL: quan sát tác động của CL

Chỉ dùng một **cluster kiểm thử** với datacenter thực sự tên `dc1`, ít nhất ba node cho RF=3. Ví dụ tạo bảng theo truy vấn bằng partition key `shipment_id`:

```sql
CREATE KEYSPACE IF NOT EXISTS failure_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS failure_lab.shipment_by_id (
  shipment_id uuid PRIMARY KEY,
  status text,
  updated_at timestamp
);
```

Trong `cqlsh`, `CONSISTENCY` là **lệnh shell** áp dụng cho các statement **chạy sau nó**:

```sql
-- Cần ít nhất 2 replica trong DC này.
CONSISTENCY QUORUM;

INSERT INTO failure_lab.shipment_by_id
    (shipment_id, status, updated_at)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'CREATED',
    '2026-11-21 10:00:00+0000'
);

-- Đọc ở quorum, cũng cần 2 phản hồi.
SELECT shipment_id, status
FROM failure_lab.shipment_by_id
WHERE shipment_id = 11111111-1111-4111-8111-111111111111;

-- Chỉ cần một replica, đổi độ mới lấy khả dụng/độ trễ.
CONSISTENCY ONE;

SELECT status
FROM failure_lab.shipment_by_id
WHERE shipment_id = 11111111-1111-4111-8111-111111111111;

-- ALL đòi cả ba replica; tránh thử khi cluster production không ổn định.
CONSISTENCY ALL;

SELECT status
FROM failure_lab.shipment_by_id
WHERE shipment_id = 11111111-1111-4111-8111-111111111111;
```

Nếu cả ba replica đều khỏe, các lệnh có thể trả cùng giá trị. **Một lần chạy thành công không chứng minh mọi CL đều có cùng bảo đảm khi sự cố xảy ra.**

### Một bài thí nghiệm an toàn về tính sẵn sàng

Trong một lab có dữ liệu giả, topology đã biết:

1. Xác nhận RF của keyspace, local DC của coordinator và replica đích của partition.
2. Đo kết quả và latency cơ bản ở `ONE`, `QUORUM` và `ALL` khi cluster khỏe.
3. Dùng **cơ chế mô phỏng lỗi được quản lý trong lab** để quan sát khi **một replica đích** không thể phản hồi. Không tắt node production.
4. Dự đoán trước: RF=3 còn 2 replica thì `ONE`/`QUORUM` **có thể thành công**, `ALL` **không đủ ngưỡng**.
5. Phân biệt **lỗi unavailable** với **lỗi timeout** theo log và trạng thái node; không chỉ so thời gian response.
6. Khôi phục node, theo dõi hinted handoff/repair theo quy trình vận hành và xác nhận dữ liệu hội tụ.

Các lệnh đọc trạng thái thường hữu ích trên node quản trị:

```bash
nodetool status
nodetool describecluster
```

Chúng hỗ trợ quan sát node và topology, **không phải bằng chứng trực tiếp mọi replica của partition cụ thể đều đã đồng bộ**. Muốn điều tra sâu cần đối chiếu token/replica placement, logs, metrics và kết quả request.

### Mở rộng sang hai DC

Trong lab thực sự có hai DC đủ node, thay replication strategy:

```sql
CREATE KEYSPACE IF NOT EXISTS failure_multi_dc_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3,
  'dc2': 3
};

CREATE TABLE IF NOT EXISTS failure_multi_dc_lab.shipment_by_id (
  shipment_id uuid PRIMARY KEY,
  status text
);
```

Khi coordinator ở `dc1`, các ngưỡng là:

```text
ONE            = 1 ACK bất kỳ
LOCAL_ONE      = 1 ACK từ dc1
LOCAL_QUORUM   = 2 ACK từ dc1
QUORUM         = 4 ACK tổng cộng từ dc1+dc2
EACH_QUORUM    = 2 ACK dc1 VÀ 2 ACK dc2 (chỉ ghi)
ALL            = 6 ACK
```

**Không chạy `SELECT` với `EACH_QUORUM` trên Cassandra OSS**: đây không phải CL hợp lệ cho đọc thông thường.

## 12. Java Driver 4.x: phân loại lỗi trước khi quyết định retry

Ví dụ sau minh họa cách đặt normal CL trên từng statement. Session cần được khởi tạo với contact points, xác thực và `local datacenter` phù hợp với môi trường:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.DriverTimeoutException;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.UnavailableException;
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;

import java.time.Instant;
import java.util.UUID;

public final class ShipmentRepository {
    private final CqlSession session;
    private final PreparedStatement write;
    private final PreparedStatement read;

    public ShipmentRepository(CqlSession session) {
        this.session = session;
        this.write = session.prepare(
            "UPDATE failure_lab.shipment_by_id " +
            "SET status = ?, updated_at = ? WHERE shipment_id = ?");
        this.read = session.prepare(
            "SELECT status FROM failure_lab.shipment_by_id " +
            "WHERE shipment_id = ?");
    }

    public void updateStatus(
            UUID shipmentId, String status, Instant eventTime) {
        BoundStatement request = write
            .bind(status, eventTime, shipmentId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        try {
            session.execute(request);
        } catch (UnavailableException e) {
            // Không đủ replica được coi là sống theo CL.
            // Không tự động hạ CL nếu nghiệp vụ không chấp nhận.
            throw e;
        } catch (WriteTimeoutException e) {
            // Một hoặc nhiều replica có thể đã áp dụng mutation.
            // Không mặc định retry như một ghi hoàn toàn mới.
            throw e;
        } catch (DriverTimeoutException e) {
            // Hết hạn chờ từ phía client; kết quả ghi có thể chưa rõ.
            throw e;
        }
    }

    public String findStatus(UUID shipmentId) {
        BoundStatement request = read.bind(shipmentId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        try {
            Row row = session.execute(request).one();
            return row == null ? null : row.getString("status");
        } catch (UnavailableException | ReadTimeoutException e) {
            // Phân loại và ghi metrics/log phù hợp tại tầng service.
            // Không coi lỗi đọc là "không có shipment".
            throw e;
        }
    }
}
```

**Điểm thiết kế:** Ví dụ truyền `eventTime` từ tầng gọi vào thay vì sinh một giá trị mới ở mỗi lần retry. Nếu retry cùng một mutation, có thể giữ nguyên khóa và payload để dễ đối soát. Tuy nhiên, ngay cả khi payload giống nhau, timestamp của cell trong Cassandra và các side effect nghiệp vụ vẫn cần được kiểm soát; **đừng tự đánh dấu mọi update là idempotent mà chưa đánh giá ngữ nghĩa cụ thể**.

Tùy driver, các lỗi từ nhiều coordinator có thể được trình bày dưới một lỗi tổng hợp. Tầng vận hành nên ghi nhận **loại lỗi, CL, DC, số replica cần/có, request timeout, node/coordinator và correlation ID**, nhưng không ghi dữ liệu nhạy cảm của khách hàng vào log.

### Có nên tự động retry?

| Tình huống | Hướng xử lý thận trọng |
| --- | --- |
| Đọc `ONE` timeout do một replica chậm | Driver có thể thử replica phù hợp khác theo policy; giới hạn retry, quan sát tải. |
| Đọc `QUORUM` unavailable | Không đủ replica theo CL; retry ngay liên tục thường không giúp nếu topology chưa hồi phục. |
| Ghi `QUORUM` timeout | Kết quả **chưa xác định**; retry chỉ khi mutation/side effect được thiết kế an toàn. |
| Ghi `ANY` trả thành công nhờ hint | Không tuyên bố dữ liệu đã có sẵn để đọc ngay; cần giám sát hội tụ. |
| LWT timeout | Kiểm tra/đối soát kết quả, giữ operation ID; không coi `[applied]=false`. |
| Mạng liên DC chậm làm `EACH_QUORUM` timeout | Xem mục tiêu nhất quán chéo DC trước khi chọn CL khác; không hạ mức âm thầm. |

**Tự động giảm CL** để “chữa timeout” có thể phá hợp đồng nhất quán của API, nhất là khi một endpoint hứa ghi đã được xác nhận ở nhiều DC. Việc thay đổi đó phải là **quyết định nghiệp vụ rõ ràng**, không phải phản xạ kỹ thuật.

## 13. Điều tra sản xuất: tối ưu điều gì trước?

Khi lỗi tăng lên trong hệ thống Cassandra, đừng chỉ tăng timeout. Hãy phân loại theo lớp:

| Lớp | Câu hỏi chẩn đoán | Công cụ/chỉ số phù hợp |
| --- | --- | --- |
| **CL / RF** | Ngưỡng đúng của request là bao nhiêu? CL có hợp lệ cho đọc/ghi không? | Cấu hình keyspace, CL theo statement, tên DC. |
| **Placement / liveness** | Replica của partition nào down hay không liên lạc được? | `nodetool status`, placement, failure detector và log node. |
| **Coordinator** | Có đủ coordinator gần ứng dụng? Route local DC có đúng? | Driver load balancing, connection metrics, host errors. |
| **Mạng** | RTT, packet loss, timeout WAN có tăng? | Network telemetry, latency per DC, tracing được bật có kiểm soát. |
| **Replica latency** | CPU, GC, disk, queue, compaction hay SSTable quá tải? | Cassandra/JVM metrics, read/write latency, pending tasks. |
| **Dữ liệu lệch** | Có backlog hints, read repair, repair chưa hoàn tất? | Hints metrics, repair status, log. |
| **Ứng dụng** | Có retry storm, hot partition, truy vấn sai partition key? | Request rate, coordinator latency, phân bố partition, driver metrics. |

### Tại sao thiết kế partition key vẫn quan trọng?

Nếu partition quá nóng, tất cả request tới partition đó tập trung vào một tập replica hạn chế. Ngay cả khi cluster có hàng trăm node, **những replica cụ thể phục vụ partition nóng vẫn có thể quá tải**, làm `QUORUM` hay `ONE` timeout.

Thiết kế bảng **theo truy vấn** và chọn partition key phân bố tải phù hợp là một phần trực tiếp của khả năng đáp ứng CL. Việc tăng RF hoặc hạ CL không thay thế việc khắc phục hot partition, truy vấn quét rộng hay mô hình dữ liệu sai.

### Chú ý hints, repair và tombstone

Sau khi replica quay lại, hinted handoff có thể giúp cập nhật mutation đã bỏ lỡ, nhưng chỉ trong giới hạn cấu hình và là **best effort**. Anti-entropy repair cần được vận hành theo chính sách phù hợp; với delete/tombstone, việc replica bỏ lỡ xóa trong thời gian dài và các quy tắc `gc_grace_seconds` còn tạo nguy cơ dữ liệu bị xóa xuất hiện lại.

Không coi **compaction đã chạy** là bằng chứng repair hoàn tất hoặc các replica đã hội tụ.

## 14. Bài tập tình huống và đáp án

### Bài 1 — Một replica down

RF=3 trong một DC. Replica `R3` down, `R1` và `R2` phản hồi đúng hạn. Đọc `ONE`, `QUORUM` và `ALL` có khả năng đạt ngưỡng không?

**Đáp án:** `ONE` cần 1 nên **có thể** đạt; `QUORUM` cần 2 nên **có thể** đạt; `ALL` cần 3 nên **không đủ ngưỡng**.

### Bài 2 — Hai replica down

RF=3, chỉ một replica đích còn khỏe. Ghi `ONE`, `TWO` và `QUORUM` có thể thành công theo số phản hồi không?

**Đáp án:** `ONE` có thể đạt 1; `TWO` và `QUORUM` đều cần 2 nên không đạt.

### Bài 3 — Node UP nhưng mạng chậm

RF=3, cả ba replica được coi là UP. Ghi `QUORUM` bị `WriteTimeout`. Có mâu thuẫn với việc số node sống đã đủ quorum không?

**Đáp án:** Không. Hai replica cần **ACK đúng hạn**, không chỉ được đánh dấu UP. Bị trễ vì network/disk/load vẫn có thể timeout.

### Bài 4 — Mất DC xa

RF=3+3, coordinator ở `dc1` có ba replica khỏe; `dc2` bị cô lập. CL nào giữa `LOCAL_QUORUM`, `QUORUM` và ghi `EACH_QUORUM` có thể đạt?

**Đáp án:** `LOCAL_QUORUM` có thể đạt 2/3 tại `dc1`. `QUORUM` cần 4/6, `dc1` tối đa có 3 nên không đạt. Ghi `EACH_QUORUM` thiếu hai ACK ở `dc2` nên không đạt.

### Bài 5 — Quorum toàn cục đạt, local quorum không

RF=3+3, coordinator ở `dc1`. Còn 1 replica `dc1` và 3 replica `dc2` phản hồi được. `QUORUM` và `LOCAL_QUORUM` ở `dc1` có thể đạt không?

**Đáp án:** `QUORUM` cần 4/6, tổng có 4 nên có thể đạt. `LOCAL_QUORUM` ở `dc1` cần 2/3 local, nhưng chỉ có 1 nên không đạt.

### Bài 6 — RF bất đối xứng

RF=5+1, coordinator ở DC có RF=5; DC còn lại bị cô lập hoàn toàn. `QUORUM`, `LOCAL_QUORUM` và `EACH_QUORUM` ghi có thể thành công không?

**Đáp án:** `QUORUM` cần 4/6, có thể đạt trong DC lớn; `LOCAL_QUORUM` cần 3/5, có thể đạt; `EACH_QUORUM` cần ít nhất một ACK từ DC nhỏ nên không đạt.

### Bài 7 — Unavailable hay timeout?

Một request `QUORUM` RF=3 bị từ chối vì coordinator thấy chỉ một replica UP. Request khác thấy hai replica UP nhưng một replica phản hồi quá chậm. Lỗi điển hình khác nhau thế nào?

**Đáp án:** Trường hợp thứ nhất có thể nhận `UnavailableException`; trường hợp thứ hai có thể nhận `ReadTimeoutException` hoặc `WriteTimeoutException` tùy loại thao tác. Trạng thái liveness và việc trả phản hồi kịp deadline là hai vấn đề khác nhau.

### Bài 8 — Retry ghi bị timeout

Ghi `QUORUM` timeout khi một replica có thể đã áp dụng mutation. Có nên tạo `shipment_id` mới rồi retry ngay?

**Đáp án:** Thường không. Việc tạo khóa mới có thể sinh bản ghi trùng nghiệp vụ. Cần giữ identity ổn định, xem tính idempotent và đối soát kết quả.

### Bài 9 — Đọc sau ghi ở CL thấp

RF=3, ghi `QUORUM` thành công trên `R1,R2`; đọc `ONE` từ `R3` chưa cập nhật trả dữ liệu cũ. Có vi phạm CL không?

**Đáp án:** Không. `W=2`, `R=1`, `W+R=3≤3`, hai tập có thể rời nhau. Đây là đánh đổi về độ mới của đọc `ONE`.

### Bài 10 — ANY và hint

Không replica đích nào nhận mutation nhưng coordinator có thể giữ hint. Ghi `ANY` thành công có chứng minh `SELECT QUORUM` ngay sau đó sẽ thấy dữ liệu mới không?

**Đáp án:** Không. Hint không phải replica đích đã ghi; trước khi phát lại, dữ liệu có thể chưa đọc được. `ANY` cũng không hợp lệ cho `SELECT`.

### Bài 11 — LWT khi chia cắt mạng

RF=3+3, client ở hai DC cùng muốn tạo một khóa duy nhất. Mỗi client dùng `LOCAL_SERIAL` tại DC riêng. Có thể lấy việc local quorum thành công để chứng minh đồng thuận toàn cục không?

**Đáp án:** Không. Hai tập Paxos local có thể rời nhau. Nếu yêu cầu quyết định duy nhất xuyên DC, cần cân nhắc phạm vi `SERIAL` và giao thức ứng dụng được áp dụng thống nhất.

### Bài 12 — Vì sao không tự động hạ CL?

Một API công bố “ghi thành công nghĩa là quorum mỗi DC đã xác nhận”. Khi mất WAN, ứng dụng đổi từ `EACH_QUORUM` sang `LOCAL_ONE` mà không thông báo. Sai ở đâu?

**Đáp án:** `LOCAL_ONE` chỉ cần một replica local; nó **không** xác nhận quorum tại mỗi DC. Hạ CL âm thầm phá bảo đảm nghiệp vụ đã công bố, dù giúp một số request được chấp nhận.

## 15. Checklist trước khi lựa chọn CL hoặc thay đổi retry policy

Trước mỗi thay đổi, trả lời:

1. **Partition key nào?** Các replica đích của partition thực tế nằm ở đâu?
2. **RF từng DC là bao nhiêu?** Đừng chỉ dùng số node tổng cluster.
3. **Coordinator ở DC nào?** Các CL `LOCAL_*` phụ thuộc DC coordinator.
4. **Request là đọc, ghi thường hay LWT?** `EACH_QUORUM` không dùng cho đọc thường; `SERIAL`/`LOCAL_SERIAL` là pha Paxos.
5. **CL đòi bao nhiêu ACK ở đâu?** Viết ngưỡng số cụ thể trước khi suy đoán khả dụng.
6. **Replica đang down hay chỉ chậm?** Phân biệt unavailable với timeout/failure.
7. **Ghi có thể đã áp dụng một phần không?** Nếu có, retry phải idempotent và được kiểm soát.
8. **Hạ CL có thay đổi hợp đồng nghiệp vụ không?** Không giảm mức nhất quán tùy tiện khi xảy ra sự cố.
9. **Có hot partition, quá tải, compaction, backlog hints hay repair chưa hoàn tất không?** Đừng chỉ tăng timeout.
10. **Đã đo và kiểm thử trên đúng topology chưa?** Kết quả một DC RF=3 không đại diện cho hai DC RF=3+3.

## 16. Kết luận

Ảnh hưởng của sự cố Cassandra đến mỗi consistency level là một bài toán về **số replica có thể phản hồi**, **phạm vi datacenter** và **thời gian hoàn tất request**. `ONE`/`LOCAL_ONE` cần ít phản hồi, thường ưu tiên khả dụng và độ trễ, nhưng không bảo đảm đọc luôn thấy bản cập nhật mới. `QUORUM` và `LOCAL_QUORUM` tạo giao nhau cho các cặp đọc/ghi phù hợp, đổi lại phải có đủ replica của phạm vi tương ứng. `ALL` dễ mất khả dụng khi một replica lỗi; `EACH_QUORUM` yêu cầu ghi được xác nhận tại **từng DC**, nên đặc biệt nhạy với sự cố liên DC.

**`Unavailable` không giống `Timeout`:** một bên thường là thiếu replica sống theo đánh giá coordinator, bên còn lại là không hoàn tất đủ phản hồi đúng hạn. Với bất kỳ lỗi ghi chưa rõ kết quả nào, tuyệt đối không suy rằng mutation chắc chắn chưa được áp dụng. Ứng dụng Java cần phân loại lỗi, chọn retry idempotent, theo dõi metrics và vận hành repair phù hợp. Khi phải bảo vệ cập nhật có điều kiện trước cạnh tranh, cần xem LWT/serial consistency thay vì chỉ tăng CL.

### Tài liệu tham khảo

- [Apache Cassandra — Dynamo, consistency và replication](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): quorum, replica, đường đọc/ghi và điều kiện thỏa CL.
- [Apache Cassandra — CQL và cqlsh](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/cqlsh.html): lệnh `CONSISTENCY` khi thử nghiệm.
- [Apache Cassandra — Hints](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/hints.html): hinted handoff, giới hạn vận hành và replica bỏ lỡ ghi.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): vai trò anti-entropy repair sau sự cố.
- [Apache Cassandra — Architecture: Failure Detection](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): cơ chế liveness và tính khả dụng của replica trong kiến trúc phân tán.
