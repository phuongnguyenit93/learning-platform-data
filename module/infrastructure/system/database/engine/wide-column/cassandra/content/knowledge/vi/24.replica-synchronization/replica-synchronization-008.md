# Last-write-wins khi hợp nhất dữ liệu từ nhiều replica trong Apache Cassandra

> **Chương:** Đồng bộ bản sao  
> **Trọng tâm:** Cách Apache Cassandra hòa giải những giá trị khác nhau do nhiều replica trả về, quy tắc **last-write-wins (LWW) theo write timestamp**, ảnh hưởng của mức nhất quán đọc/ghi, xóa bằng tombstone, repair, đồng hồ và ứng dụng Java.

## 1. Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

1. Giải thích chính xác vì sao **“last write” trong Cassandra là mutation có timestamp lớn hơn**, không nhất thiết là request đến node sau hoặc response trả về cuối.
2. Phân biệt trạng thái của **replica**, **partition**, **row**, **cell**, và lý do các cột trong cùng một hàng có thể đến từ những mutation khác nhau.
3. Minh họa read reconciliation khi một số replica có dữ liệu mới, số khác giữ giá trị cũ; đánh giá ý nghĩa của `ONE`, `QUORUM` và `LOCAL_QUORUM`.
4. Giải thích cách DELETE, TTL, tombstone, compaction và repair tương tác với LWW.
5. Tái hiện thứ tự timestamp bằng CQL `USING TIMESTAMP` và quan sát `WRITETIME`; nhận diện lỗi clock skew hoặc timestamp sai đơn vị.
6. Chọn cách xử lý xung đột phù hợp giữa LWW và **lightweight transaction (LWT)**, rồi áp dụng từ Cassandra Java Driver.

Trong cơ sở dữ liệu **wide-column phân tán** như Cassandra, partition key quyết định token và các replica theo replication factor (RF). Ứng dụng thiết kế bảng theo truy vấn và chọn consistency level (CL); những quyết định này xác định **replica nào được ghi/đọc**, còn LWW xác định **giá trị nào thắng khi dữ liệu không giống nhau**.

## 2. LWW giải quyết bài toán nào?

Giả sử keyspace có RF=3; partition `tenant-a` được sao chép trên ba node A, B và C. Một replica có thể tạm mất kết nối, một mutation có thể đến trễ, hoặc hai client ghi gần đồng thời:

~~~text
                   Coordinator
                       |
                WRITE status=PAID
                 ts=1700000000000200
                   /   |    \
                  v    v     x
                  A    B     C (down)
                 PAID PAID  NEW
                 ts=...0200  ts=...0100

           Sau đó C hoạt động trở lại
                  /    |     \
              A: PAID B: PAID C: NEW
                  \    |     /
                  Read / repair
                        |
                Reconcile theo timestamp
                        |
                  PAID thắng NEW
~~~

**LWW là một quy tắc hòa giải dữ liệu khi tồn tại nhiều phiên bản**, giúp các replica có thể hội tụ sau khi nhận đủ mutation. Nó không làm một giao dịch trên các node trở thành giao dịch ACID toàn cục, cũng không làm mọi replica luôn giống nhau ngay sau mỗi write.

### 2.1. Ba khái niệm rất dễ bị trộn lẫn

| Khái niệm | Ý nghĩa trong Cassandra | Ví dụ |
|---|---|---|
| **Thứ tự request đến node** | Thứ tự mạng hoặc thread xử lý; có thể khác nhau giữa replica | A nhận W1 rồi W2, C nhận W2 rồi W1 |
| **Write timestamp** | Giá trị thời gian logic gắn với mutation/cell, thường tính bằng **microsecond từ epoch** trong CQL | W1=1000, W2=2000 |
| **Giá trị sống cuối cùng** | Kết quả hòa giải theo timestamp, tombstone và quy tắc dữ liệu của Cassandra | W2 thắng vì 2000 > 1000 |

Nếu W2 đến **trước** W1 tại replica C, C vẫn phải giữ W2 khi cả hai mutation có cùng phạm vi cell và timestamp của W2 lớn hơn. Cụm “last-write-wins” vì thế nên được hiểu là **highest-timestamp-wins** đối với dữ liệu thông thường.

## 3. Đơn vị hòa giải: phần lớn là từng cell, không phải cả hàng

Đối với các cột thông thường của Cassandra, một mutation mang write timestamp cho từng giá trị được ghi. Khi một hàng nhận UPDATE trên hai cột ở hai lần khác nhau, mỗi cột có thể có timestamp riêng.

Ví dụ một hàng:

~~~text
PRIMARY KEY: (tenant_id='tenant-a', order_id=1111...)

Replica A                         Replica B
--------------------------------  --------------------------------
status='PAID', ts=300              status='NEW', ts=100
amount=150,   ts=120              amount=200, ts=250
note='sent',  ts=180              note='sent', ts=180

Hòa giải hợp lệ:
  status = 'PAID'  (300 của A > 100 của B)
  amount = 200    (250 của B > 120 của A)
  note   = 'sent' (cả hai cùng giá trị/timestamp)
~~~

Kết quả có thể là **một hàng kết hợp giá trị từ nhiều replica**. Không có quy tắc đơn giản “toàn bộ hàng của node A thắng node B” hoặc “replica có nhiều cột mới nhất hơn sẽ thắng”.

Điều này phù hợp với mô hình **CQL wide-column**, nhưng có hệ quả nghiệp vụ: nếu `status` và `amount` phải thay đổi cùng nhau như một trạng thái không thể tách rời, **không nên mặc định hai UPDATE độc lập là một giao dịch bất khả phân**. Cassandra có một số bảo đảm atomicity trong phạm vi partition đối với mutation/batch, nhưng điều đó khác với một giao dịch có isolation và kiểm tra điều kiện như cơ sở dữ liệu quan hệ.

### 3.1. Quy tắc hòa giải cơ bản

Với **cùng cell/định danh**, bỏ qua những biến thể đặc biệt như counter:

1. Mutation có **write timestamp lớn hơn** thường chiếm ưu thế.
2. Một **tombstone** che dữ liệu sống thuộc phạm vi của nó nếu timestamp của tombstone **lớn hơn hoặc bằng** timestamp ghi dữ liệu cần xóa.
3. Với **timestamp bằng nhau**, Cassandra dùng các quy tắc tie-break nội bộ, trong đó tombstone ưu tiên hơn live cell khi cùng phạm vi; các trường hợp hai live cell cùng timestamp không được coi là “request đến sau thắng”.
4. **TTL** và thời gian hết hạn quyết định một giá trị còn sống hay đã chuyển thành trạng thái xóa; không chỉ nhìn giá trị timestamp mà bỏ qua lifetime.
5. Kết quả có thể được ghi lại qua read repair/anti-entropy repair để replica hội tụ, nếu các cơ chế đó thực sự chạy và còn thông tin cần thiết.

Ví dụ thuật toán khái niệm cho một cell:

~~~text
reconcile(cellX ở A, B, C):
    thu thập các phiên bản/tombstone liên quan
    ưu tiên write timestamp lớn hơn
    nếu timestamp hòa: áp dụng tie-break của Cassandra
    xét tombstone theo phạm vi và TTL/liveness
    trả trạng thái cuối hợp lệ
~~~

**Không tự cài thuật toán trên client theo cách so sánh mỗi `WRITETIME(col)`**: tombstone hàng, tombstone partition/range, liveness và các trường hợp cùng timestamp cần được storage engine xử lý đầy đủ.

### 3.2. Ngoại lệ cần hiểu

- **Counter columns** có cách lưu và hợp nhất theo counter context, không áp dụng quy tắc cập nhật LWW đơn giản như một cột text/int; CQL cũng hạn chế `USING TIMESTAMP` trên counter.
- **Collection không frozen** có thể có nhiều phần tử và metadata xóa theo thành phần; **frozen collection** được xử lý khác vì lưu như một giá trị. Không tự suy một collection luôn có đúng một timestamp.
- **Row/partition/range tombstone** che nhiều cell, nên “timestamp lớn nhất của status” chưa mô tả được toàn bộ việc hàng có xuất hiện hay không.
- **Lightweight transaction** là một đường cập nhật có điều kiện dựa trên Paxos; nó giải quyết lớp bài toán khác với write thường và LWW.

## 4. Read reconciliation: ONE có thể cũ, QUORUM có thể hòa giải

Xét ba replica A/B/C chứa cùng một partition:

~~~text
T0:
  A=status NEW, ts=100
  B=status NEW, ts=100
  C=status NEW, ts=100

T1:
  UPDATE status PAID, ts=200, CL=QUORUM
  A=status PAID, ts=200   -> ACK
  B=status PAID, ts=200   -> ACK
  C=status NEW,  ts=100   -> không nhận

T2:
  SELECT status CL=ONE, chọn C
    -> có thể thấy NEW (cũ).

  SELECT status CL=QUORUM, trả lời từ một cặp replica
    -> trong RF=3, cặp hai replica luôn có ít nhất một
       replica đã ACK ts=200 (nếu đúng tập replica và
       không có mutation/failure khác).
    -> reconcile: PAID(ts=200) thắng NEW(ts=100).
~~~

Khi đọc với nhiều replica, Cassandra có thể dùng **full-data response** và **digest response** để phát hiện khác biệt, rồi lấy dữ liệu cần thiết và hòa giải. Cơ chế đọc chính xác phụ thuộc phiên bản, loại truy vấn, speculative retry và chính sách read repair.

### 4.1. Vì sao công thức quorum chỉ là một phần câu trả lời?

Với RF=3 (full replicas) trong một DC:

| CL | Số phản hồi cần | Hệ quả |
|---|---:|---|
| `ONE` | 1 | Đọc/ghi khả dụng hơn khi lỗi node; có thể nhìn dữ liệu cũ |
| `QUORUM` | 2 | Tập phản hồi đọc/ghi theo cùng RF giao nhau |
| `ALL` | 3 | Yêu cầu mọi replica trả lời; dễ unavailable khi node down |

Công thức **R + W > RF** có ích khi phân tích tập replica phản hồi, nhưng cần các giả định quan trọng:

- Đọc và ghi đang xét **cùng tập replica và cùng phạm vi nhất quán**.
- Không có ghi khác mang timestamp cao hơn chen giữa hoặc conflict chưa được tính.
- Coordinator và client không nhầm timeout với một write chắc chắn thất bại.
- Replica được xét còn chứa thông tin đủ để hòa giải; tombstone đã bị GC có thể tạo rủi ro zombie riêng.
- Trên cluster nhiều DC, `LOCAL_QUORUM` chỉ dùng RF của **DC cục bộ**; không thể suy “đã thấy trên mọi DC”.

Quorum **không tạo thứ tự thời gian thực toàn cục** cho các UPDATE thông thường. Một request đến sau với timestamp nhỏ hơn vẫn thua write có timestamp lớn hơn đã hoàn tất trước đó.

### 4.2. Read repair khác periodic repair

Khi phát hiện digest mismatch, Cassandra có thể sửa khác biệt trong phạm vi dữ liệu được đọc. Từ Cassandra 4.0, bảng có tùy chọn `read_repair` với các hành vi như `BLOCKING` hoặc `NONE`, cần kiểm đúng version; `BLOCKING` có thể sửa dữ liệu của read trước khi trả kết quả tùy theo CL.

**Read repair có phạm vi theo truy vấn thực tế được chạm tới**. Nó không thay thế **anti-entropy repair theo toàn bộ token range**, vốn dùng để sửa những partition lâu không được đọc hoặc nằm trên replica vừa phục hồi.

~~~text
Read QUORUM gặp mismatch
     |
     +-> reconcile để trả kết quả
     +-> có thể thực hiện read repair theo phiên bản/config

Nodetool / scheduled repair:
     |
     +-> quét và so sánh các token range
     +-> đồng bộ khác biệt kể cả những partition không được đọc
~~~

## 5. Write path: vì sao cùng một mutation đến replica không cùng lúc?

Cassandra dùng replication strategy chọn các natural replicas của token range. Coordinator chịu trách nhiệm gửi write theo CL yêu cầu. Một request có thể hoàn tất khi đủ phản hồi **mà chưa phải mọi replica đều nhận được**.

~~~text
                      WRITE W1
                        |
                 Coordinator
                 /    |     \
                A     B      C
              ACK   ACK    timeout
                \    /
               QUORUM thành công

Trong lúc C không sẵn sàng:
  A và B giữ phiên bản mới.
  C có thể còn phiên bản cũ.
  Hint/repair cần giúp C bắt kịp.
~~~

Nếu một mutation cũ đến sau mutation mới tại C, **timestamp reconciliation** vẫn bảo vệ giá trị mới. Ví dụ:

~~~text
Timestamps:
  W1: status NEW,  ts=100
  W2: status PAID, ts=200

Thứ tự mạng tại C:
  Nhận W2 trước -> PAID
  Nhận W1 sau   -> vẫn PAID, vì 100 < 200
~~~

**Hinted handoff** có thể lưu mutation cho replica bị gián đoạn ngắn hạn; **anti-entropy repair** đối chiếu các replica khi chạy. Không cơ chế nào là bảo đảm mọi mutation được giao trong mọi tình huống chỉ vì CL ghi trả thành công.

## 6. Timestamp: “mới” theo Cassandra có thể không phải “mới” theo người dùng

### 6.1. Timestamp CQL tính bằng microsecond

`USING TIMESTAMP` của CQL dùng số nguyên biểu diễn **microseconds kể từ Unix epoch**, không phải milliseconds của nhiều API Java/JavaScript.

~~~sql
-- Đúng kiểu đơn vị CQL: epoch microseconds.
UPDATE lww_lab.orders
USING TIMESTAMP 1700000000000200
SET status = 'PAID'
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

`WRITETIME(status)` cho biết timestamp của **cell đang sống** khi cột được phép dùng hàm này:

~~~sql
SELECT status,
       WRITETIME(status) AS status_write_ts,
       amount,
       WRITETIME(amount) AS amount_write_ts
FROM lww_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

Lưu ý `WRITETIME` không phải phép đọc đầy đủ lịch sử mutation. Nếu giá trị đã xóa, hàm không trả cho bạn một lịch sử tombstone hoàn chỉnh; muốn chẩn đoán phải kết hợp logs/tracing, metadata, audit và những công cụ hỗ trợ đúng phiên bản.

### 6.2. Timestamp do ai cấp?

Một request không ghi rõ `USING TIMESTAMP` vẫn nhận timestamp từ cơ chế của **driver và/hoặc coordinator** tùy phiên bản/cấu hình. Java Driver 4.x có hệ thống timestamp generator phía client; khi không tự cấp timestamp, không nên mặc định mọi write đều do đồng hồ coordinator tính. Cần xem cấu hình driver đang dùng trước khi giải thích một conflict.

Những nguồn timestamp khác nhau gây nguy cơ:

| Nguồn | Rủi ro cần xét |
|---|---|
| Đồng hồ hệ điều hành của nhiều node | **Clock skew** giữa các máy |
| Java driver cấp timestamp phía client | Các instance có thời gian lệch nhau hoặc restart |
| `USING TIMESTAMP` từ ứng dụng | Sai đơn vị, số cố định, timestamp tương lai, replay cũ |
| Import, restore, CDC replay | Ghi lại dữ liệu cũ sau thời gian dài với timestamp ban đầu |
| Nhiều service ghi cùng cell | Tranh chấp timestamp không theo thứ tự nghiệp vụ |

**Timestamp tương lai** đặc biệt nguy hiểm. Nếu một client ghi `status='PAID'` với timestamp lớn hơn thời gian hiện tại nhiều giờ, một UPDATE hoặc DELETE hợp lệ từ client khác có thể không thắng cho đến khi timestamp mới thực sự vượt giá trị tương lai đó. Tăng CL không chữa lỗi thứ tự timestamp.

### 6.3. Các tình huống thường bị gọi nhầm là “mất ghi”

| Hiện tượng | Lời giải thích có thể xảy ra |
|---|---|
| UPDATE trả OK nhưng SELECT vẫn thấy giá trị cũ | UPDATE mới đến sau nhưng có timestamp **thấp hơn** cell hiện hành |
| Write từ service B luôn thắng service A | Clock B chạy nhanh; timestamp B luôn lớn hơn |
| DELETE trả thành công nhưng giá trị vẫn tồn tại | Có mutation timestamp lớn hơn tombstone, hoặc đọc replica chưa nhận xóa |
| Một số cột đã đổi, cột khác chưa đổi | Mỗi cell có timestamp và lịch sử mutation riêng |
| Một giá trị xuất hiện sau repair | Replica có write timestamp cao hơn đã được đồng bộ, hoặc tombstone cần thiết đã mất |

Không kết luận mọi vấn đề trên đều do LWW trước khi kiểm tra **write timestamp, tombstone, CL, replica health, thời gian node và lịch sử ghi**.

## 7. DELETE, TTL và tombstone tham gia hòa giải ra sao?

DELETE cũng là một mutation có timestamp, nhưng biểu diễn **dấu xóa** thay vì giá trị sống.

~~~text
Replica A: status='PAID', ts=100
Replica B: tombstone status, ts=200
Replica C: status='PAID', ts=100

Reconciliation:
  tombstone ts=200 che status ts=100
  -> không trả giá trị status.
~~~

Nếu có ghi hợp lệ `status='REFUNDED'` với timestamp `ts=300`, nó thắng tombstone `ts=200` theo LWW và có thể xuất hiện trở lại. Đây là **giá trị mới hợp lệ**, khác với zombie từ replica giữ phiên bản cũ.

### 7.1. DELETE theo phạm vi

- **Cell tombstone** che một cell.
- **Row tombstone** che các cell trong hàng theo timestamp/phạm vi.
- **Range tombstone** che nhiều clustering rows thuộc một khoảng.
- **Partition tombstone** che partition theo timestamp.

Một query có `WRITETIME(status)=300` chưa đủ kết luận status sẽ xuất hiện nếu có tombstone ở phạm vi hàng/partition mang timestamp lớn hơn. Để xác định kết quả chính xác, Cassandra kết hợp **liveness, tombstone và nhiều SSTable**, không chỉ so sánh hai số.

### 7.2. TTL làm giá trị hết hạn

TTL được lưu cùng giá trị. Khi hết hạn, cell không còn là dữ liệu sống; khi đọc phải xét thời hạn/tombstone tương ứng. Vì SSTable bất biến, dữ liệu đã hết hạn có thể vẫn nằm trên đĩa cho tới khi compaction và các điều kiện garbage collection cho phép.

~~~sql
UPDATE lww_lab.orders
USING TTL 300
SET note = 'temporary'
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

SELECT note, TTL(note), WRITETIME(note)
FROM lww_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

`TTL(note)` là **thời gian còn lại tính bằng giây** trong phạm vi hỗ trợ của hàm; nó không phải write timestamp. Không dùng TTL như một công cụ tự động giải quyết mọi xung đột của các trường khác.

### 7.3. Nguy cơ zombie khi tombstone bị thu hồi trước repair

Khi một replica bỏ lỡ DELETE và không được sửa trước khi tombstone ở các replica khỏe bị purge sau `gc_grace_seconds` và compaction thích hợp, dữ liệu cũ có thể **xuất hiện lại**. LWW không thể nhận ra ý định xóa nếu dấu xóa có timestamp lớn hơn đã biến mất ở mọi replica có khả năng chữa lỗi.

~~~text
Ngày 0: A/B nhận DELETE ts=200; C chỉ có status ts=100.
Trong grace: repair có thể đưa tombstone ts=200 tới C.
Sau grace + purge hợp lệ: A/B không còn tombstone.
C trở lại với status ts=100, repair không còn ts=200 để so.
-> Dữ liệu cũ có thể bị xem là còn sống và lan sang A/B.
~~~

Do đó, **lịch repair cần hoàn tất bao phủ dữ liệu trước khi grace hết hạn**, và node offline vượt grace phải được đánh giá/rebuild theo runbook thay vì đưa SSTable cũ trở lại một cách tùy tiện.

## 8. Tie-break khi timestamp trùng nhau

Hai write có cùng timestamp là tình huống đặc biệt:

~~~text
W1: status='NEW',  ts=500
W2: status='PAID', ts=500
~~~

Cassandra có quy tắc hòa giải **deterministic** dành cho trường hợp bằng timestamp để các replica hội tụ. Khi một live cell và tombstone cùng timestamp/phạm vi, **tombstone được ưu tiên**. Với hai live cell cùng timestamp nhưng giá trị khác, storage engine có quy tắc tie-break nội bộ dựa trên giá trị/serialization và metadata liên quan, không có ý nghĩa “request cuối cùng” theo giờ người dùng.

Vì vậy:

- **Không** cố tạo hai write cùng timestamp và dự đoán bên thắng từ thứ tự mạng.
- **Không** dùng timestamp bằng nhau như cách mô phỏng một giao dịch.
- **Không** dựa vào chi tiết tie-break theo bytes như một logic nghiệp vụ, nhất là nếu dữ liệu có nhiều loại cell/collection.
- Nếu cần bảo đảm “chuyển NEW → PAID khi trạng thái hiện tại vẫn NEW”, hãy dùng **conditional update/LWT** hoặc thiết kế tuần tự hóa phù hợp, thay vì trông chờ so sánh timestamp.

## 9. LWW và lightweight transaction (LWT) giải quyết hai bài toán khác nhau

LWW cho phép các mutation **thông thường** hội tụ khi có replica khác nhau hoặc ghi gần đồng thời. Khi nghiệp vụ cần một điều kiện kiểu **compare-and-set**, ví dụ “chỉ chuyển đơn từ NEW sang PAID nếu vẫn là NEW”, LWW không đủ để ngăn hai client cùng tưởng mình là người thắng.

Ví dụ minh họa LWT:

~~~sql
UPDATE lww_lab.orders
SET status = 'PAID'
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111
IF status = 'NEW';
~~~

Lệnh điều kiện dùng cơ chế đồng thuận **Paxos**. Kết quả CQL có cột `[applied]`:

- `[applied] = true`: điều kiện đúng, mutation được chấp nhận.
- `[applied] = false`: điều kiện không còn đúng; ứng dụng cần đọc trạng thái hiện tại và quyết định retry/hiển thị conflict.

Các lựa chọn nhất quán của LWT còn gồm **serial consistency** (`SERIAL`/`LOCAL_SERIAL`) và consistency level thường cho pha commit; chọn theo topology và yêu cầu. LWT tốn nhiều round trip hơn một UPDATE thường, do đó cần benchmark.

| Nhu cầu | Hướng phù hợp | Vì sao |
|---|---|---|
| Ghi log trạng thái có thể chấp nhận hội tụ cuối | UPDATE thường + CL thích hợp, repair | Đơn giản, hiệu năng tốt; timestamp quyết định xung đột |
| Chỉ cho một client đổi trạng thái nếu chưa bị đổi | UPDATE ... IF ... (LWT) | Điều kiện được kiểm tra bằng Paxos |
| Tạo duy nhất một bản ghi theo khóa chính | INSERT ... IF NOT EXISTS (LWT) | Giảm nguy cơ hai client cùng ghi mâu thuẫn tại cùng khóa |
| Duy trì invariant giữa nhiều partition/bảng | Thiết kế transaction/điều phối riêng | LWT không tự biến toàn cluster thành cơ sở dữ liệu ACID đa bảng |
| Thứ tự các sự kiện nghiệp vụ không trùng đồng hồ | Sequence/version có kiểm soát hoặc event sourcing | Timestamp đồng hồ không mô tả quan hệ nhân quả nghiệp vụ |

**Không kết hợp tùy tiện `USING TIMESTAMP` với mutation có `IF`**: Cassandra không hỗ trợ tự gán timestamp theo cùng cách cho các conditional statements. Hãy để cơ chế LWT quyết định tính hợp lệ, rồi thiết kế đọc/ghi theo tài liệu phiên bản.

## 10. Bài thực hành CQL: write đến sau vẫn có thể thua

**Môi trường:** cluster lab Apache Cassandra có ít nhất 3 node ở cùng DC mang tên giả định `dc1`, `cqlsh` và quyền xem `nodetool`; các bước không cần gây lỗi node. Chỉ dùng `dc1` khi đó thực sự là tên DC trong cluster; nếu khác, thay cho đúng topology.

### Bước 1 — Tạo keyspace và bảng theo partition key

~~~sql
CREATE KEYSPACE IF NOT EXISTS lww_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': '3'
};

CREATE TABLE IF NOT EXISTS lww_lab.orders (
    tenant_id text,
    order_id uuid,
    status text,
    amount int,
    note text,
    PRIMARY KEY ((tenant_id), order_id)
);
~~~

Mỗi hàng là cặp (`tenant_id`, `order_id`). Tập replica do hash của **tenant_id** và replication strategy chọn; `order_id` là clustering key. Với dữ liệu lab ít, đây là ví dụ để đọc timestamp, không phải mẫu partition key phù hợp cho mọi hệ thống production.

### Bước 2 — Ghi giá trị ban đầu với timestamp cố định

~~~sql
CONSISTENCY QUORUM;

INSERT INTO lww_lab.orders
    (tenant_id, order_id, status, amount, note)
VALUES (
    'tenant-a',
    11111111-1111-1111-1111-111111111111,
    'NEW',
    100,
    'created'
)
USING TIMESTAMP 1700000000000100;

SELECT status, WRITETIME(status) AS status_ts,
       amount, WRITETIME(amount) AS amount_ts
FROM lww_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

**Kỳ vọng:** `status='NEW'`, `amount=100`, cả hai có write timestamp `1700000000000100`. Đây là timestamp minh họa thuộc quá khứ, không phải hướng dẫn tự đặt timestamp cố định cho ứng dụng thật.

### Bước 3 — Mutation có timestamp lớn hơn tới trước

~~~sql
UPDATE lww_lab.orders
USING TIMESTAMP 1700000000000300
SET status = 'PAID'
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

-- Gửi sau, nhưng write timestamp LẠI NHỎ HƠN.
UPDATE lww_lab.orders
USING TIMESTAMP 1700000000000200
SET status = 'PENDING'
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

SELECT status, WRITETIME(status)
FROM lww_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

**Kỳ vọng:** Vẫn là `PAID` với timestamp `1700000000000300`. Lần UPDATE `PENDING` được gửi **sau** nhưng thua do timestamp cũ hơn. Bài này chứng minh “LWW” là quy tắc **thứ tự timestamp**, không phải thứ tự lệnh trong terminal.

### Bước 4 — Hai cột thắng ở hai thời điểm khác nhau

~~~sql
UPDATE lww_lab.orders
USING TIMESTAMP 1700000000000250
SET amount = 150
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

UPDATE lww_lab.orders
USING TIMESTAMP 1700000000000150
SET note = 'checked'
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

SELECT status, WRITETIME(status),
       amount, WRITETIME(amount),
       note, WRITETIME(note)
FROM lww_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

**Kỳ vọng:** `status=PAID` (`...0300`), `amount=150` (`...0250`), `note=checked` (`...0150`). Các timestamp khác nhau chứng minh hòa giải phần lớn diễn ra theo **cell**.

### Bước 5 — Tombstone thắng dữ liệu cũ

~~~sql
DELETE status
FROM lww_lab.orders
USING TIMESTAMP 1700000000000400
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

-- Ghi cũ sau DELETE, timestamp vẫn nhỏ hơn tombstone.
UPDATE lww_lab.orders
USING TIMESTAMP 1700000000000350
SET status = 'OLD-STATUS'
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

SELECT status, amount, note
FROM lww_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

**Kỳ vọng:** `status=null` (vì tombstone), nhưng `amount=150` và `note=checked` vẫn sống. Đây là DELETE **một cột**, không phải DELETE cả row.

### Bước 6 — Ghi mới hơn tombstone là hành vi hợp lệ

~~~sql
UPDATE lww_lab.orders
USING TIMESTAMP 1700000000000500
SET status = 'REOPENED'
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

SELECT status, WRITETIME(status), amount
FROM lww_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;
~~~

**Kỳ vọng:** `REOPENED` có timestamp `...0500`, lớn hơn tombstone `...0400`. Đây là một **ghi mới hợp lệ** đã thắng xóa, không nhất thiết là zombie data.

### Bước 7 — Quan sát CL và replica

~~~bash
nodetool status
nodetool getendpoints lww_lab orders tenant-a
~~~

`getendpoints` cho biết **tập natural replicas dự kiến**, không chứng minh nội dung thực tế của từng SSTable. Trong lab, khi được phép thao tác node, có thể tạo tình huống replica ngắt kết nối rồi khôi phục để so sánh kết quả CL ONE và QUORUM, nhưng **không cần cố tình gây partition mạng** để xác nhận quy tắc timestamp ở các bước trước.

### Bước 8 — Phân biệt read repair với repair định kỳ

~~~sql
TRACING ON;

SELECT status, WRITETIME(status)
FROM lww_lab.orders
WHERE tenant_id = 'tenant-a'
  AND order_id = 11111111-1111-1111-1111-111111111111;

TRACING OFF;
~~~

Trace có thể cho biết các replica tham gia và hoạt động reconcile/read repair tùy phiên bản; tracing làm tăng tải, chỉ bật tạm trong lab.

Khi vận hành repair trên một cluster thử nghiệm có phân công rõ:

~~~bash
# Chạy theo lịch trên TỪNG node/DC liên quan,
# để bao phủ toàn bộ primary token ranges.
nodetool repair --full -pr lww_lab orders
~~~

Một lệnh trên một node với `-pr` **không tự bao phủ toàn cluster**. Repair có thể khiến replica hội tụ, nhưng nó không thay lại các timestamp nghiệp vụ theo thứ tự mong muốn của người dùng: **giá trị có timestamp cao nhất vẫn thắng**.

## 11. Java Driver: kiểm tra WRITETIME và tránh timestamp xung đột

Trong Cassandra Java Driver 4.x, ứng dụng có thể đọc timestamp cell để điều tra hiện tượng ghi bị che. Ví dụ phương thức nhận `CqlSession` được ứng dụng tạo và dùng lại:

~~~java
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

public final class OrderVersionReader {
    public static Long statusWriteTimeMicros(
            CqlSession session, String tenantId, UUID orderId) {
        SimpleStatement query = SimpleStatement.builder(
                "SELECT status, WRITETIME(status) AS status_ts " +
                "FROM lww_lab.orders WHERE tenant_id = ? AND order_id = ?")
            .addPositionalValues(tenantId, orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .build();

        Row row = session.execute(query).one();
        if (row == null || row.isNull("status_ts")) {
            return null; // Không có cell status đang sống.
        }
        return row.getLong("status_ts"); // CQL trả epoch microseconds.
    }
}
~~~

Trên RF=3 trong một DC, LOCAL_QUORUM cần hai phản hồi. Với nhiều DC, nó chỉ sử dụng replica ở local DC. Giá trị trả về từ `WRITETIME` giúp tìm chứng cứ, **không** thay được việc điều tra tombstone hoặc sự kiện ứng dụng.

### 11.1. Gán timestamp chủ động chỉ khi có cơ chế phối hợp

Nếu cần tái hiện xung đột trong lab từ Java, prepared statement có thể bind CQL timestamp:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import java.util.UUID;

public final class LabTimestampWriter {
    public static void updateWithControlledTimestamp(
            CqlSession session, long epochMicros,
            String tenantId, UUID orderId, String status) {
        PreparedStatement statement = session.prepare(
                "UPDATE lww_lab.orders USING TIMESTAMP ? " +
                "SET status = ? WHERE tenant_id = ? AND order_id = ?");

        BoundStatement bound = statement.bind(
                epochMicros, status, tenantId, orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        session.execute(bound);
    }
}
~~~

**Cảnh báo:** Timestamp phải là **microsecond**, không phải `System.currentTimeMillis()` (millisecond). Ví dụ phương thức trên dành cho test/replay đã kiểm soát; ứng dụng production thường nên để cơ chế timestamp generator được cấu hình đúng đảm trách công việc, đồng thời giữ đồng hồ máy đồng bộ. Nếu chủ động cấp timestamp vì nghiệp vụ, phải thiết kế nguồn phát thứ tự **không xung đột giữa các writer**.

### 11.2. Nếu cần bảo đảm trạng thái có điều kiện

Một Java service có thể dùng prepared conditional statement:

~~~java
PreparedStatement conditional = session.prepare(
    "UPDATE lww_lab.orders SET status = ? " +
    "WHERE tenant_id = ? AND order_id = ? IF status = ?");

Row result = session.execute(
    conditional.bind("PAID", "tenant-a", orderId, "NEW")
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL))
    .one();

boolean applied = result != null && result.getBoolean("[applied]");
~~~

Đây là đoạn mã nằm **bên trong phương thức đã có** các biến `session` và `orderId`, minh họa cách kiểm `[applied]` của LWT. Phải chọn SERIAL/LOCAL_SERIAL đúng topology và hiểu chi phí Paxos. LWT không tự cung cấp transaction toàn cục trên nhiều partition.

## 12. Runbook kiểm tra lệch replica và lỗi LWW

### Bước 1 — Xác định triệu chứng và phạm vi

Ghi rõ keyspace/table, partition key, clustering key, cột bị sai, timestamp nghiệp vụ, thời điểm lệnh WRITE/DELETE, DC và CL. Đừng gọi chung là “replication lag” nếu chưa có dữ kiện về replica hoặc write timestamps.

| Câu hỏi chẩn đoán | Cách thu thập |
|---|---|
| Client thực sự ghi với timestamp nào? | CQL `WRITETIME` cho cell sống, log driver/ứng dụng, audit timestamp |
| Có nhiều writer cạnh tranh một cell không? | Request ID, service instance, event chronology |
| Node/replica nào tham gia? | `nodetool getendpoints`, topology, `nodetool status` |
| Ghi đọc với CL nào? | CQL/statement config, driver config, query tracing có chọn lọc |
| Có tombstone hoặc TTL không? | Schema `gc_grace_seconds`, TTL, lệnh DELETE, compaction/repair log |
| Có clock skew hoặc timestamp tương lai? | NTP/clock monitoring, epoch micros vs millis |
| Node có bị cô lập hoặc repair fail? | Hints, repair job coverage, streaming errors |
| Có batch, counter, collection hay LWT? | Query shape, loại bảng và tính năng cụ thể |

### Bước 2 — Phân loại đúng lớp lỗi

| Dấu hiệu | Khả năng nguyên nhân | Hành động phù hợp |
|---|---|---|
| ONE thấy cũ, QUORUM thấy mới | Replica chưa đồng bộ | Kiểm tra hints/read repair, thực hiện repair có phạm vi |
| Mọi CL thấy giá trị ghi “cũ” dù vừa UPDATE | Timestamp mới thấp hơn cell đã tồn tại | Kiểm timestamp generator, clock skew, import/replay |
| DELETE thành công nhưng cell vẫn tồn tại | Có live write timestamp cao hơn, CL không đủ hoặc replica chưa nhận delete | Phân tích tombstone vs live, timestamp và CL |
| Hàng bị xóa xuất hiện sau downtime/compaction | Có thể zombie do tombstone đã purge | Điều tra grace/repair/restore trước khi ghi lại |
| Hai cột cùng row đến từ hai phiên bản | LWW theo cell và mutations khác nhau | Xem invariant, chuyển sang một mutation thích hợp hoặc LWT |
| Hai client đồng thời đổi trạng thái, một người bị ghi đè | Concurrent regular writes | Dùng conditional write/versioning nếu cần CAS |
| Đọc QUORUM nhưng hai DC khác nhau chưa hội tụ | LOCAL_QUORUM chỉ trong local DC, hoặc lỗi repair liên DC | Xác minh RF/CL của từng DC và lịch repair |

### Bước 3 — Tránh “sửa” bằng timestamp cực lớn

Nếu một cell đang có timestamp tương lai, cách ghi `USING TIMESTAMP 9999999999999999` để ép thắng **có thể làm tình trạng tệ hơn**: các mutation bình thường về sau khó ghi đè được giá trị này. Cần phân tích nguồn timestamp lỗi, xác định dữ liệu đúng và lên kế hoạch sửa có kiểm soát theo thời gian/nguồn sự thật.

Tương tự, **chạy repair khi dữ liệu đã mang timestamp nghiệp vụ sai** thường chỉ lan truyền **phiên bản sai có timestamp cao hơn** tới replica khác. Repair làm replicas **giống nhau**, không có quyền quyết định giá trị nào đúng theo nghiệp vụ.

### Bước 4 — Xác minh sau khi khắc phục

1. Rà soát logs để biết nguồn timestamp sai đã được dừng hoặc sửa.
2. Đọc cùng tập khóa kiểm thử ở các CL/DC liên quan, so sánh `WRITETIME` và giá trị sống.
3. Kiểm tra tombstone/TTL trong tình huống DELETE, và bảo đảm repair bao phủ những replica bị lỗi.
4. Quan sát p95/p99 read/write latency, timeout, hints và repair status trong chu kỳ tiếp theo.
5. Nếu đã phát sinh zombie, đối soát với nhật ký nghiệp vụ để chắc bản ghi cũ không tiếp tục lan rộng.

## 13. Những hiểu lầm phổ biến

| Nhận định sai | Điều đúng cần nhớ |
|---|---|
| “Last-write-wins nghĩa là UPDATE gửi sau luôn thắng.” | Mutation có **write timestamp lớn hơn** thắng theo quy tắc hòa giải. |
| “Mọi cột trong hàng dùng một timestamp.” | Các cell có thể được ghi bởi mutation khác nhau, có timestamp khác nhau. |
| “QUORUM nghĩa là ba replica giống nhau sau mỗi write.” | RF=3, QUORUM cần hai ACK; replica còn lại có thể cũ. |
| “Timestamp do coordinator cấp trong mọi ứng dụng.” | Driver có thể cấp timestamp client-side; phụ thuộc config/phiên bản. |
| “USING TIMESTAMP dùng milliseconds.” | CQL cần **microseconds**. |
| “Read repair thay hoàn toàn periodic repair.” | Read repair chỉ sửa những dữ liệu được truy vấn/detect, không phủ mọi range. |
| “Repair sẽ chọn dữ liệu đúng theo nghiệp vụ.” | Repair hội tụ bằng dữ liệu và timestamp hiện có; timestamp sai vẫn có thể thắng. |
| “DELETE chỉ là xóa hàng trực tiếp khỏi các SSTable.” | DELETE tạo tombstone; read reconciliation phải xét dấu xóa. |
| “Tombstone đã bị GC thì mọi replica đều biết xóa.” | Replica bỏ lỡ DELETE có thể giữ dữ liệu cũ, gây zombie. |
| “Timestamp bằng nhau thì request cuối thắng.” | Tie-break là quy tắc nội bộ xác định; không dựa vào thứ tự mạng. |
| “LWT giống UPDATE thường nhưng có thêm WHERE.” | LWT dùng Paxos cho conditional mutation, khác cơ chế regular write. |
| “Tăng CL sẽ chữa clock skew.” | CL điều khiển số ACK; không đổi timestamp của mutation. |

## 14. Bài tập tư duy

**Câu 1.** A giữ `status=NEW, ts=100` và B giữ `status=PAID, ts=200`. Giá trị nào thắng và tại sao?  
*Định hướng:* PAID thắng vì timestamp lớn hơn, bất kể thứ tự request tới từng node.

**Câu 2.** Với RF=3, WRITE QUORUM thành công ở A/B, C chưa nhận. SELECT ONE từ C có thể trả gì?  
*Định hướng:* Giá trị cũ; QUORUM thành công chưa có nghĩa mọi replica đều được cập nhật.

**Câu 3.** Cùng một row, A có `status ts=300` và B có `amount ts=400`. Một replica có thể trả cả hai không?  
*Định hướng:* Có, hòa giải theo cell; phải xét invariant của dữ liệu nghiệp vụ.

**Câu 4.** UPDATE sau dùng timestamp 1000, UPDATE trước dùng timestamp 2000. UPDATE nào thắng cho cùng cell?  
*Định hướng:* Mutation 2000.

**Câu 5.** DELETE status ts=500 có che status ts=500 không?  
*Định hướng:* Có, tombstone chiếm ưu thế khi cùng timestamp/phạm vi.

**Câu 6.** Tại sao WRITE có timestamp ở tương lai dễ làm DELETE hợp lệ thất bại?  
*Định hướng:* DELETE với timestamp thấp hơn không che được live cell mang timestamp cao hơn.

**Câu 7.** Quorum read có thay periodic repair khi ứng dụng chỉ đọc 10% partition không?  
*Định hướng:* Không; các partition không được đọc có thể tiếp tục lệch.

**Câu 8.** Client muốn chỉ đổi `NEW → PAID` nếu chưa có worker khác đổi trạng thái. Nên dùng gì?  
*Định hướng:* Conditional update/LWT hoặc cơ chế điều phối/versioning được kiểm chứng.

**Câu 9.** Vì sao repair sau khi tombstone bị purge có thể tạo zombie?  
*Định hướng:* Không còn thông tin xóa ts cao; replica với dữ liệu cũ có thể trông hợp lệ.

**Câu 10.** Java service dùng `System.currentTimeMillis()` đưa thẳng vào CQL `USING TIMESTAMP`. Sai ở đâu?  
*Định hướng:* Milliseconds khác microseconds, làm thứ tự timestamp sai và dễ che khuất mutation.

## 15. Ghi nhớ bằng sơ đồ

~~~text
Nhiều replica nhận mutation theo thứ tự khác nhau
                     |
                     v
           Cassandra đọc/repair
                     |
           Reconcile theo từng cell
                     |
          So sánh write timestamp
           /                  \
     Timestamp khác       Timestamp bằng
     -> lớn hơn thắng     -> tie-break nội bộ
           \                  /
            \                /
       Xét tombstone, TTL và liveness
                     |
                     v
             Giá trị hợp lệ
                     |
      Read repair / periodic repair
           giúp replicas hội tụ

Nhưng:
  + CL không sửa đồng hồ hoặc timestamp sai.
  + Repair không quyết định đúng/sai theo nghiệp vụ.
  + Tombstone bị purge quá sớm có thể làm dữ liệu cũ sống lại.
  + LWT/Paxos dùng khi phải có điều kiện cập nhật đồng thời.
~~~

**Nguyên lý cốt lõi:** LWW của Apache Cassandra là **quy tắc hòa giải các mutation dựa trên write timestamp ở mức cell và tombstone**, giúp nhiều replica hội tụ cuối cùng. Nó không đồng nghĩa “request cuối cùng thắng theo thời gian thực”, không thay bảo đảm nhất quán đọc/ghi, và không thay anti-entropy repair. Hiểu điều đó giúp ứng dụng Java chọn timestamp, CL, schema và cơ chế cập nhật phù hợp với bài toán phân tán thực tế.

## Tài liệu tham khảo

- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — coordinator, replication, CL, hinted handoff, read repair và hòa giải.
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html) — `USING TIMESTAMP`, `WRITETIME`, UPDATE/DELETE, TTL và điều kiện IF.
- [Apache Cassandra — Data Definition](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html) — replication strategy, keyspace/table và `read_repair`.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — anti-entropy repair, full/incremental repair và primary ranges.
- [Apache Cassandra — Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html) — `gc_grace_seconds`, zombie data và compaction.
- [Apache Cassandra — Storage engine](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html) — memtable/SSTable, mutation timestamp và compaction.
- [Apache Cassandra — Lightweight transactions](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html#lightweight-transactions) — conditional write, Paxos và serial consistency.
