# Quorum đọc/ghi và những sai lệch vẫn cần repair

## 1. Một thao tác thành công không có nghĩa mọi bản sao đã giống nhau

Trong **Apache Cassandra**, dữ liệu của một partition được lưu trên nhiều **replica** do token của partition key, replication strategy và topology quyết định. Một node nhận yêu cầu làm **coordinator**, chuyển thao tác tới những replica thích hợp và trả kết quả khi đạt **consistency level (CL)**.

Một tình huống thường gặp:

1. Partition `device-7 / 2026-11-21` có ba replica **N1, N2, N3** (RF = 3).
2. Ghi ở `LOCAL_QUORUM` thành công vì **N1 và N2** đã xác nhận; **N3** đang chậm hoặc mất kết nối.
3. Một lần đọc `LOCAL_QUORUM` sau đó vẫn có thể thấy giá trị mới nhất nhờ **giao nhau giữa tập replica đã ghi và tập replica được đọc**.
4. **N3 vẫn có thể còn dữ liệu cũ**. Nếu những lần đọc tiếp theo không chạm tới N3, không có gì buộc riêng việc quorum read/write phải tự sửa hết lịch sử trên node này.

Đây là khác biệt quan trọng giữa **đạt quorum cho một request** và **đồng bộ đầy đủ các replica theo thời gian**. Bài học giải thích phép tính quorum, cơ chế đối chiếu khi đọc, các nguồn tạo sai lệch, và vì sao vẫn cần **anti-entropy repair**.

**Mục tiêu sau bài:**

- Tính được số phản hồi `ONE`, `LOCAL_QUORUM`, `QUORUM`, `ALL` theo replication factor.
- Giải thích điều kiện giao nhau `R + W > RF` và các giả định của lập luận này.
- Phân biệt **đọc ra dữ liệu đúng** với **tất cả replica đều đã được sửa**.
- Phân tích tác động của hinted handoff, read repair, tombstone, mạng chập chờn và nhiều data center.
- Thực hành CQL, quan sát topology/repair và sử dụng Java Driver 4.x với CL rõ ràng.

Phạm vi ví dụ là **full replica** thông thường; transient replication, LWT/Paxos và khác biệt cấu hình riêng theo phiên bản không được lấy làm mặc định.

## 2. Ba khái niệm thường bị đánh đồng

| Khái niệm | Trả lời câu hỏi | Không bảo đảm điều gì? |
| --- | --- | --- |
| **Replication factor (RF)** | Mỗi partition có bao nhiêu node replica mục tiêu (theo DC với `NetworkTopologyStrategy`)? | Không nói một write phải chờ bao nhiêu node. |
| **Consistency level (CL)** | Một read/write cần bao nhiêu phản hồi phù hợp trước khi coordinator trả kết quả? | Không bảo đảm mọi replica đã nhận, lưu hoặc được repair. |
| **Repair** | Làm sao phát hiện và đồng bộ khác biệt giữa các replica trên những vùng dữ liệu? | Không phải điều kiện ACK thông thường của một request và không thay backup. |

**Ví dụ:** một DC có bốn node, keyspace RF = 3. Mỗi partition chỉ có **ba replica mục tiêu** trong DC đó; node thứ tư có thể làm coordinator nhưng không phải bản sao của mọi partition. `LOCAL_QUORUM` cần **hai phản hồi** từ ba replica, không phải hai trong bốn node của DC.

Partition key quyết định **token và nhóm replica**. Clustering columns chỉ sắp xếp các hàng bên trong partition; một partition chứa hàng nghìn hàng vẫn có **cùng bộ replica** cho các hàng ấy.

## 3. Toán học của quorum: vì sao `R + W > RF`?

Đặt:

- `RF`: số full replica của partition trong **phạm vi đang xét**.
- `W`: số replica được xác nhận khi thao tác ghi thành công.
- `R`: số replica phải tham gia đáp ứng mức nhất quán đọc.

Nếu `R + W > RF`, hai tập con gồm `W` và `R` node trong cùng một tập `RF` node **phải có ít nhất một node giao nhau**. Đó là **quorum overlap**.

Với RF = 3:

| CL trong một DC | Số phản hồi | Ví dụ |
| --- | ---: | --- |
| `LOCAL_ONE` | 1 | Một replica cục bộ xác nhận. |
| `LOCAL_QUORUM` | `floor(3 / 2) + 1 = 2` | Hai replica cục bộ xác nhận. |
| `ALL` | 3 | Cả ba replica của partition xác nhận. |

Khi **write `LOCAL_QUORUM`** và **read `LOCAL_QUORUM`** cùng DC, `W = 2`, `R = 2`, `RF = 3`, nên `2 + 2 > 3`. Hai tập đều có hai phần tử trong ba phần tử thì không thể hoàn toàn rời nhau.

~~~text
Replica của partition: {N1, N2, N3}

Write ACK:  {N1, N2}          -- W = 2
Read ACK:   {N2, N3}          -- R = 2
Giao nhau:  {N2}

Nếu N2 giữ write mới, coordinator có thể hòa giải dữ liệu đọc
với phiên bản cũ từ N3.
~~~

### 3.1. Sơ đồ request và replica chậm

~~~mermaid
sequenceDiagram
    participant A as Ứng dụng
    participant C as Coordinator
    participant N1 as N1 (replica)
    participant N2 as N2 (replica)
    participant N3 as N3 (replica chậm)
    A->>C: INSERT (LOCAL_QUORUM)
    C->>N1: Mutation t2
    C->>N2: Mutation t2
    C->>N3: Mutation t2
    N1-->>C: ACK t2
    N2-->>C: ACK t2
    C-->>A: Success (2/3 ACK)
    Note over N3: Có thể vẫn giữ t1
    A->>C: SELECT (LOCAL_QUORUM)
    C->>N2: Đọc / digest
    C->>N3: Đọc / digest
    N2-->>C: t2
    N3-->>C: t1
    Note over C: Phát hiện khác biệt, đối chiếu
    C-->>A: Giá trị hợp lệ mới hơn theo timestamp
~~~

Hình trên **không** nói rằng read luôn chọn N2 và N3, hoặc N3 chắc chắn được sửa đồng bộ ngay sau request. Việc chọn replica, gửi dữ liệu/digest và cơ chế read repair tùy phiên bản, mức nhất quán và kiểu truy vấn.

### 3.2. Giới hạn của lập luận giao nhau

`R + W > RF` là **một điều kiện giao nhau về tập replica**, không phải một chứng minh rằng Cassandra có transaction isolation hay serializability cho mọi thao tác.

Lập luận muốn hữu ích cần ít nhất các giả định:

1. `R` và `W` thuộc **cùng tập replica** của cùng partition và phạm vi DC tương ứng.
2. Replica đã ACK write thực sự còn khả dụng/còn dữ liệu để tham gia read; không có mất vĩnh viễn cả các bản đã ACK trước khi dữ liệu được đồng bộ.
3. Xét một write đã hoàn tất, **không có ghi cạnh tranh chưa được giải quyết** hoặc timestamp client sai khiến thứ tự phiên bản không như kỳ vọng.
4. Read protocol thực hiện đối chiếu các phiên bản phù hợp; dữ liệu theo semantics last-write-wins/tombstone được áp dụng chính xác.

Vì thế, quorum thường giúp đọc giá trị đã được ghi thành công gần nhất trong **trường hợp không có ghi đồng thời và không có lỗi vượt giả định**, nhưng không phải giao dịch ACID trên nhiều partition, không ngăn lost update của mô hình đọc-sửa-ghi, và không có nghĩa tất cả replica đã hội tụ.

## 4. Thành công ở quorum nhưng dữ liệu vẫn lệch

### 4.1. Quorum write không đợi toàn bộ replica

Với RF = 3, write `LOCAL_QUORUM` thành công khi có đủ hai ACK trong local DC. Coordinator thường cố gắng gửi mutation tới **toàn bộ replica cần nhận**; tuy nhiên thời điểm trả thành công **không cần chờ replica thứ ba**.

N3 có thể lệch do:

- Không liên lạc được đúng thời điểm ghi.
- Đang khởi động lại, mất mạng hoặc bị quá tải.
- Ghi đang được chuyển tiếp nhưng chưa đến/được áp dụng.
- Có mutation khác với timestamp mới hơn hoặc delete/tombstone chưa được đồng bộ.

Đây là **replica divergence**. Một write thành công chỉ xác minh **ngưỡng ACK của request**, không ghi chứng nhận đồng nhất nội dung toàn bộ replica.

### 4.2. Quorum read không quét toàn bộ lịch sử

Quorum read có thể phát hiện khác biệt **trong dữ liệu truy vấn đã đọc**. Ví dụ:

- `SELECT` đọc riêng partition `device-7` có thể kích hoạt quá trình đối chiếu các hàng liên quan ở partition đó.
- Một partition khác `device-8` chưa từng được đọc có thể vẫn lệch.
- Ngay trong partition `device-7`, những clustering ranges **không được truy vấn** có thể chưa được đối chiếu.
- Nếu N1 và N2 (cả hai đã có write mới) được chọn trả lời một read, N3 có thể **không tham gia** và vẫn cũ.

Read repair (nếu được kích hoạt theo đường đọc/phiên bản) có thể giúp khắc phục phần lệch **được phát hiện**, chứ không bảo đảm tự rà soát toàn bộ keyspace.

### 4.3. Những nơi `ONE` vẫn có thể thấy dữ liệu cũ

Vẫn với N1/N2 có `t2`, N3 có `t1`:

| Request | Replica đọc ví dụ | Kết quả có thể quan sát |
| --- | --- | --- |
| `LOCAL_ONE` | Chỉ N3 | Có thể thấy giá trị cũ `t1`. |
| `LOCAL_ONE` | Chỉ N1 | Có thể thấy giá trị mới `t2`. |
| `LOCAL_QUORUM` | N2 và N3 | Có thể hòa giải, trả giá trị hợp lệ `t2`; N3 là ứng viên sửa lệch. |
| `LOCAL_QUORUM` | N1 và N2 | Thấy `t2`; N3 không nhất thiết được sửa. |

Khi dữ liệu chưa hội tụ, **cùng câu SQL** có thể cho kết quả khác nhau tại các CL/replica khác nhau. Quorum cải thiện khả năng quan sát write phù hợp điều kiện giao nhau; repair giải quyết **sự hội tụ trên toàn tập replica**.

## 5. Quorum nhiều data center: phạm vi mới là điều quyết định

Giả sử keyspace dùng `NetworkTopologyStrategy` với **RF = 3 ở `dc1`** và **RF = 3 ở `dc2`**. Mỗi partition có tối đa sáu full replica nếu đủ node.

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3,
  'dc2': 3
};
~~~

| CL | Ngưỡng với RF 3 + 3 | Phạm vi |
| --- | --- | --- |
| `LOCAL_ONE` | 1 | DC cục bộ của coordinator. |
| `LOCAL_QUORUM` | 2 | Chỉ DC cục bộ, chẳng hạn `dc1`. |
| `QUORUM` | `floor(6/2)+1 = 4` | Tổng full replica trên các DC. |
| `EACH_QUORUM` (ghi) | 2 tại `dc1` **và** 2 tại `dc2` | Cần quorum từng DC; không phải chỉ bốn ACK bất kỳ. |
| `ALL` | 6 | Tất cả full replica của partition. |

**Tình huống quan trọng:** ứng dụng ở `dc1` ghi `LOCAL_QUORUM`, nhận ACK từ hai replica ở `dc1`, rồi ứng dụng tại `dc2` đọc `LOCAL_QUORUM`. Hai quorum thuộc **hai tập replica khác nhau**. `W = 2` trong `dc1` và `R = 2` trong `dc2` **không giao nhau**, dù cả hai yêu cầu đều có chữ QUORUM.

Không thể kết luận `dc2` đã thấy write mới ngay khi `dc1` trả success. Dữ liệu có thể được chuyển đến `dc2` sau đó, và repair giúp xử lý các sai lệch kéo dài.

### Chọn CL theo yêu cầu thực tế

| Mục tiêu | Hướng lựa chọn | Đánh đổi |
| --- | --- | --- |
| Read/write thông thường chỉ cần bảo đảm trong local DC | `LOCAL_QUORUM` khi topology phù hợp | Không đợi quorum ở remote DC. |
| Xác nhận write đã đạt quorum ở từng DC | `EACH_QUORUM` cho write khi được hỗ trợ | Độ trễ và tính sẵn sàng phụ thuộc nhiều DC. |
| Cần quorum toàn cluster | `QUORUM` khi phạm vi và latency chấp nhận được | Mất mạng liên DC có thể ảnh hưởng. |
| Ưu tiên độ trễ/tính sẵn sàng, chấp nhận quan sát cũ trong một số trường hợp | `LOCAL_ONE` | Ít giao nhau hơn; cần theo dõi convergence. |

**Lưu ý:** `EACH_QUORUM` ở đây là **consistency level dành cho write**, không phải mức đọc thường dùng. Và CL không thay đổi RF, topology hoặc cơ chế repair.

## 6. Những sai lệch nào mà repair phải xử lý?

| Nguồn sai lệch | Điều gì xảy ra? | Vì sao quorum chưa đủ? |
| --- | --- | --- |
| Replica mất kết nối trong khi write đạt `ONE` hoặc quorum | Một số replica chưa nhận mutation | CL chỉ cần số ACK yêu cầu. |
| Hints hết hạn, bị giới hạn hoặc không được phát lại | Replica vắng mặt lâu có thể bỏ lỡ nhiều mutation | Hinted handoff không phải nhật ký đồng bộ đầy đủ vô hạn. |
| Partition hoặc clustering range ít được đọc | Không có cơ hội để read repair phát hiện mismatch | Read repair chỉ chạm phạm vi read thực sự. |
| `DELETE` hoặc TTL tạo tombstone, replica khác còn dữ liệu cũ | Dữ liệu đã xóa có thể chưa được lan tới mọi replica | Quorum write của delete không bắt tất cả replica ACK. |
| Ghi từ nhiều DC hoặc network partition | Một DC có thể tạm nhìn thấy phiên bản cũ | Local quorum ở DC này không bao hàm DC kia. |
| Bootstrapping, thay node, topology thay đổi | Dữ liệu cần stream và kiểm tra các token ranges mới | Metadata/topology thay đổi không tự chứng minh toàn bộ file đã đồng bộ. |
| Nhiều bản ghi đồng thời/timestamp lệch | Replica có thể tạm giữ các version khác nhau | Quorum không thay thế giải quyết xung đột ứng dụng hoặc transaction isolation. |

### Vì sao một tombstone bị bỏ lỡ có thể thành “zombie”?

Giả sử N3 offline khi N1 và N2 nhận `DELETE` ở `LOCAL_QUORUM`:

~~~mermaid
flowchart LR
    A["N1: tombstone t2"] --> Q["Read quorum có thể trả: đã xóa"]
    B["N2: tombstone t2"] --> Q
    C["N3: dữ liệu cũ t1"] --> D["N3 vẫn chưa nhận delete"]
    D --> E["Offline lâu, không repair kịp"]
    E --> F["Tombstone trên N1/N2 bị purge quá sớm"]
    F --> G["N3 quay lại, dữ liệu t1 có nguy cơ xuất hiện lại"]
~~~

`gc_grace_seconds` của bảng góp phần giữ tombstone đủ lâu để những replica từng vắng mặt có thời gian nhận thông tin xóa. Nhưng **grace không tự chạy repair**. Nếu bỏ lỡ chu kỳ đồng bộ và purge thông tin xóa trong khi replica cũ vẫn tồn tại, dữ liệu đã xóa có thể sống lại.

Điều này giải thích vì sao cần lên lịch **anti-entropy repair**, đặc biệt với bảng có nhiều `DELETE`, TTL và những partition ít được đọc. Giảm `gc_grace_seconds` chỉ để dọn đĩa khi chưa kiểm soát repair là một quyết định rủi ro.

## 7. Hinted handoff, read repair và anti-entropy repair: ba vai trò

### 7.1. Hinted handoff: bù cho replica tạm không nhận write

Khi một replica không khả dụng, Cassandra có thể ghi lại **hint** ở node phù hợp để gửi mutation về sau. Hints hỗ trợ lấp các khoảng trống ngắn hạn, nhưng bị giới hạn bởi **thời gian lưu, cấu hình, dung lượng, sự cố của node giữ hint và điều kiện phát lại**.

Hint **không phải** một replica đầy đủ và **không bảo đảm** đồng bộ sau thời gian offline dài. CL `ANY` với write thậm chí có thể trả success dựa vào hint trong tình huống phù hợp mà chưa có full replica nào phục vụ read dữ liệu mới. Do vậy không dùng `ANY` để kết luận dữ liệu đã có thể đọc ngay.

### 7.2. Read repair: sửa phần dữ liệu đọc thấy khác nhau

Khi coordinator nhận dữ liệu/digest không khớp, nó có thể yêu cầu đủ dữ liệu để hòa giải và sửa những replica bị lệch. Hành vi **blocking** hay **không sửa theo đường đọc** là vấn đề phụ thuộc phiên bản và tùy chọn cấu hình (chẳng hạn `read_repair` của bảng trong các phiên bản hỗ trợ).

Read repair giúp các truy vấn tiếp theo nhất quán hơn ở phạm vi đã đối chiếu, nhưng:

- Không quét tất cả token ranges hoặc toàn bộ lịch sử của keyspace.
- Không đảm bảo sửa một replica không tham gia request đang xét.
- Có thể không chạm những hàng/partition ít đọc.
- Không thay thế anti-entropy repair định kỳ.

### 7.3. Anti-entropy repair: đối chiếu dữ liệu trên các replica

**Anti-entropy repair** đối chiếu các vùng dữ liệu trên những replica chịu trách nhiệm, thường bằng cơ chế so sánh tóm tắt như Merkle tree và truyền những dữ liệu thiếu/khác để đưa các replica tới trạng thái phù hợp.

Nó tập trung vào **phạm vi token của bảng/keyspace**, không phụ thuộc việc ứng dụng có `SELECT` vào các partition đó hay không.

| Cơ chế | Kích hoạt chính | Phạm vi điển hình | Giới hạn |
| --- | --- | --- | --- |
| Hinted handoff | Replica bỏ lỡ write tạm thời | Mutation bị lỡ mà còn hint hợp lệ | Không đầy đủ/vô hạn. |
| Read repair | Đọc phát hiện dữ liệu/digest không khớp | Dữ liệu thực sự được đọc và replica liên quan | Không rà soát toàn bộ dữ liệu. |
| Anti-entropy repair | Tác vụ bảo trì theo kế hoạch | Token ranges và replica của keyspace/bảng | Cần kế hoạch tài nguyên, giám sát và hoàn thành phạm vi. |
| Compaction | Chính sách quản lý SSTable trên từng node | Dữ liệu cục bộ trong các SSTable được chọn | Không tự đồng bộ replica từ node khác. |
| Backup/snapshot | Kế hoạch phục hồi | Điểm khôi phục theo retention | Repair không thể tự hoàn tác xóa nhầm đã được nhân bản. |

**Repair không phải replication factor, không phải consistency level và không phải backup.** Tăng RF hoặc đổi CL không tự làm sạch sai lệch đã tích lũy; compaction cục bộ cũng không làm dữ liệu chưa có trên replica khác tự xuất hiện.

## 8. Thiết kế lịch repair an toàn

### 8.1. Liên hệ với `gc_grace_seconds`

Nếu bảng dùng `gc_grace_seconds = 864000` (10 ngày), đây là mốc cần cân nhắc khi tổ chức bảo trì đối với replica từng bỏ lỡ tombstone. Không được diễn giải là “chạy repair một lần đúng ngày thứ mười là đủ trong mọi trường hợp”.

Một chính sách thực hành cần:

1. Đảm bảo **tất cả token ranges/replica liên quan** được repair đầy đủ trong khoảng an toàn mà tổ chức quy định, với dư địa cho retry/sự cố.
2. Giám sát và xử lý **repair thất bại hoặc chỉ chạy một phần**; khởi chạy lệnh chưa có nghĩa công việc đã hoàn tất.
3. Khi một replica offline **lâu hơn thời hạn an toàn**, đánh giá phương án **rebuild/replace theo runbook** thay vì đưa node dữ liệu quá cũ trở lại mà không kiểm soát.
4. Điều chỉnh lịch theo dung lượng, số bảng, TTL/delete rate, thông lượng mạng, tải ổ đĩa và chính sách compaction.
5. Phân biệt **incremental/full repair**, phạm vi DC và các tùy chọn cụ thể dựa trên **phiên bản Cassandra** đang vận hành; không tự chuyển đổi chế độ khi chưa hiểu trạng thái repaired/unrepaired SSTable.

**Mốc grace không tự bảo vệ khỏi mọi dạng sai lệch.** Write không có delete vẫn có thể bị lỡ trên replica; những phần dữ liệu có thể khác nhau cho tới khi có repair hoặc cơ chế đồng bộ khác hoàn thành.

### 8.2. Khi nào cần khẩn trương điều tra?

- Một hoặc nhiều node ở trạng thái down trong thời gian dài, đặc biệt khi bảng có TTL/delete.
- Repair liên tục fail, pending compaction tăng, network streaming bị nghẽn.
- Đọc `LOCAL_ONE` và `LOCAL_QUORUM` cho kết quả khác nhau trên cùng dữ liệu sau khi write đã ổn định.
- Cross-DC read thấy dữ liệu cũ sau thời gian vượt kỳ vọng replication.
- Tombstone warnings, nghi ngờ zombie data hoặc phát hiện chênh dữ liệu giữa replica.

Tình trạng read khác nhau **không đủ** để kết luận một node hỏng ổ đĩa; cần đối chiếu timestamp, CL, trace, topology, repair history và workload ghi đồng thời.

## 9. Thực hành CQL: quan sát quorum và dữ liệu được trả

### 9.1. Tạo bảng với partition key phục vụ truy vấn

Ví dụ lab trong DC `dc1` có ít nhất ba node. Nếu môi trường khác, thay tên DC/RF cho đúng trước khi chạy:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_lab.readings_by_device_day (
    device_id text,
    event_day date,
    recorded_at timestamp,
    event_id uuid,
    reading decimal,
    PRIMARY KEY ((device_id, event_day), recorded_at, event_id)
) WITH CLUSTERING ORDER BY (recorded_at DESC, event_id ASC)
  AND gc_grace_seconds = 864000;
~~~

Partition key kép `(device_id, event_day)` quyết định token và nhóm replica. `recorded_at` và `event_id` cho phép định danh từng phép đo và đọc theo thời gian **trong partition**. Không cần quét token toàn cluster để lấy dữ liệu của một thiết bị trong một ngày.

### 9.2. Ghi và đọc bằng `LOCAL_QUORUM`

Trong `cqlsh`:

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

INSERT INTO telemetry_lab.readings_by_device_day
    (device_id, event_day, recorded_at, event_id, reading)
VALUES
    ('device-7', '2026-11-21', '2026-11-21T03:00:00Z',
     123e4567-e89b-42d3-a456-426614174001, 21.75);

SELECT recorded_at, event_id, reading
FROM telemetry_lab.readings_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21';

TRACING OFF;
~~~

Với RF = 3 tại `dc1`, write và read `LOCAL_QUORUM` đều yêu cầu **hai phản hồi replica** trong `dc1`. Tracing có thể hiển thị coordinator, endpoint tham gia, request giữa các node và chi phí đọc. **Một trace thành công không chứng minh replica còn lại đã đồng bộ.**

Đổi CL để hiểu ngữ nghĩa (chỉ trong lab kiểm soát):

~~~sql
CONSISTENCY LOCAL_ONE;

SELECT recorded_at, event_id, reading
FROM telemetry_lab.readings_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21';
~~~

Nếu dữ liệu đã hội tụ, kết quả có thể giống nhau. Nếu replica lệch, `LOCAL_ONE` có thể đọc từ bản sao chưa bắt kịp. Không nên cố tạo sai lệch bằng cách dừng node hoặc thay đổi storage trên cluster production.

### 9.3. Thử nghiệm tombstone và trách nhiệm repair

~~~sql
CONSISTENCY LOCAL_QUORUM;

DELETE FROM telemetry_lab.readings_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND recorded_at = '2026-11-21T03:00:00Z'
  AND event_id = 123e4567-e89b-42d3-a456-426614174001;

SELECT recorded_at, event_id, reading
FROM telemetry_lab.readings_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21';
~~~

Kết quả bình thường không còn hàng trên, nhưng **không có hàng trả về không có nghĩa tombstone đã được purge hoặc mọi replica đã nhận delete**. Việc dọn tombstone phải tôn trọng grace, repair và compaction an toàn.

### 9.4. Quan sát cluster và tác vụ repair

Trên môi trường lab hoặc theo runbook được phê duyệt:

~~~bash
nodetool status
nodetool netstats
nodetool compactionstats
~~~

`nodetool status` giúp kiểm tra node/DC/rack up/down; `netstats` hỗ trợ quan sát streaming/hints trong những tình huống phù hợp; `compactionstats` cho biết công việc nền. Chúng **không tự chứng minh** dữ liệu giữa mọi replica giống nhau.

Lệnh repair mẫu **chỉ để tham khảo cho lab**, không chạy tùy tiện trên production:

~~~bash
nodetool repair telemetry_lab readings_by_device_day
~~~

Đối số, chế độ mặc định (incremental/full), phạm vi xử lý, điều kiện tải và cách theo dõi kết quả cần kiểm tra theo phiên bản cùng quy trình vận hành đang áp dụng. **Thành công của một lệnh tại một node chưa đủ để khẳng định mọi range của toàn cluster đã được repair**. Cần kế hoạch bao phủ topology và kiểm tra kết quả hoàn thành.

## 10. Java Driver 4.x: CL là thuộc tính của statement

Ứng dụng Java nên xác định partition key rõ ràng, dùng prepared statement, đặt CL theo yêu cầu nghiệp vụ và xử lý timeout như **kết quả chưa xác định**.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.math.BigDecimal;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class QuorumReadingExample {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            UUID eventId = UUID.fromString(
                    "123e4567-e89b-42d3-a456-426614174001");

            PreparedStatement insert = session.prepare(
                    "INSERT INTO telemetry_lab.readings_by_device_day " +
                    "(device_id, event_day, recorded_at, event_id, reading) " +
                    "VALUES (?, ?, ?, ?, ?)");

            BoundStatement write = insert.bind(
                    "device-7",
                    LocalDate.of(2026, 11, 21),
                    Instant.parse("2026-11-21T03:00:00Z"),
                    eventId,
                    new BigDecimal("21.75"))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);
            session.execute(write);

            PreparedStatement select = session.prepare(
                    "SELECT recorded_at, event_id, reading " +
                    "FROM telemetry_lab.readings_by_device_day " +
                    "WHERE device_id = ? AND event_day = ?");

            BoundStatement read = select.bind(
                    "device-7", LocalDate.of(2026, 11, 21))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            for (Row row : session.execute(read)) {
                System.out.println(row.getInstant("recorded_at")
                        + " -> " + row.getBigDecimal("reading"));
            }
        }
    }
}
~~~

**Giải thích:**

1. Partition key `(device_id, event_day)` cho driver đủ dữ liệu để tính routing key và ưu tiên replica khi token-aware routing được hỗ trợ.
2. `LOCAL_QUORUM` trên write và read tạo điều kiện giao nhau **trong dc1**, khi RF của DC này là 3 và các giả định ở mục 3 thỏa.
3. `withLocalDatacenter("dc1")` phải đúng tên data center thật. `127.0.0.1` chỉ minh họa môi trường lab; production cần TLS/authentication và contact points phù hợp.
4. **Timeout của write không chứng minh write đã thất bại.** Có replica đã áp dụng nhưng client chưa nhận đủ ACK; retry cần dùng event ID ổn định, cân nhắc idempotency và tránh vô tình ghi đè dữ liệu mới.
5. Dù cả hai lệnh có `LOCAL_QUORUM`, code **không tự sửa các partition không được đọc**. Vẫn cần giám sát replication và chạy repair theo kế hoạch.

## 11. Những hiểu lầm thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “RF = 3 nghĩa mọi write phải chờ ba node.” | **Sai** | CL quyết định ngưỡng ACK; `LOCAL_QUORUM` cần hai trong DC có RF 3. |
| “`R + W > RF` nghĩa tất cả replica đã có bản ghi mới.” | **Sai** | Nó bảo đảm giao nhau của tập phản hồi, không bảo đảm đồng bộ toàn bộ. |
| “Hai `LOCAL_QUORUM` tại hai DC chắc chắn giao nhau.” | **Sai** | Hai tập replica ở các DC khác nhau có thể không giao nhau. |
| “Read repair tự động quét toàn keyspace.” | **Sai** | Chỉ xử lý dữ liệu mà đường đọc/chính sách tương ứng thực sự chạm tới. |
| “Hint đủ để thay repair nếu node offline rất lâu.” | **Sai** | Hint có thời hạn/giới hạn; anti-entropy repair vẫn cần thiết. |
| “`gc_grace_seconds` tự chạy repair khi đến hạn.” | **Sai** | Grace là khoảng bảo vệ tombstone, không phải lịch scheduler của repair. |
| “Repair và compaction giống nhau.” | **Sai** | Repair đồng bộ replica, compaction quản lý SSTable cục bộ. |
| “Write `LOCAL_QUORUM` ở dc1 success nghĩa dc2 đã nhận quorum.” | **Sai** | Không cần ACK từ dc2 để success theo `LOCAL_QUORUM` tại dc1. |
| “Chạy repair có thể hoàn tác mọi `DELETE` sai.” | **Sai** | Repair có thể lan truyền tombstone; cần backup để khôi phục lỗi logic. |
| “Quorum đọc/ghi là transaction serializable toàn cluster.” | **Sai** | Cassandra có semantics eventual consistency/timestamp; LWT là cơ chế khác cho điều kiện tuyến tính hóa hạn chế. |

## 12. Bài tập tự kiểm tra có lời giải

**Bài 1.** Một DC có RF = 3. Write `LOCAL_QUORUM` được N1, N2 ACK; N3 chưa có mutation. Read `LOCAL_QUORUM` chọn N2, N3. Tại sao có thể trả dữ liệu mới?

**Đáp án:** Hai tập `{N1,N2}` và `{N2,N3}` giao nhau tại N2. Khi không có write cạnh tranh và semantics timestamp phù hợp, coordinator có thể đối chiếu dữ liệu mới trên N2 với dữ liệu cũ ở N3.

**Bài 2.** Sau request ở bài 1, vì sao vẫn cần repair?

**Đáp án:** N3 có thể chưa được sửa hoàn toàn, các hàng/partition khác không được đọc có thể lệch. Read repair không đồng nghĩa rà soát toàn keyspace; anti-entropy repair đồng bộ các token ranges được chỉ định.

**Bài 3.** RF = 5 trong một DC. `QUORUM` cần bao nhiêu ACK? Nếu write và read đều `QUORUM`, các tập có buộc giao nhau không?

**Đáp án:** `floor(5/2)+1 = 3`. Hai tập ba node trong năm node phải có ít nhất một node chung, vì `3+3>5`.

**Bài 4.** Keyspace có `dc1: RF=3`, `dc2: RF=3`. Write tại dc1 dùng `LOCAL_QUORUM`. Read ngay tại dc2 cũng dùng `LOCAL_QUORUM`. Có thể chắc chắn đọc ra write mới theo phép tính `2+2>3` không?

**Đáp án:** **Không.** Hai quorum tính trong **hai DC khác nhau**, không dùng cùng tập ba replica. Remote DC có thể chưa nhận mutation.

**Bài 5.** Một replica đã offline lâu hơn cả khoảng lưu hint, chưa chạy repair; bảng có nhiều `DELETE`. Vì sao việc hạ `gc_grace_seconds` để dọn tombstone là nguy hiểm?

**Đáp án:** Replica có thể còn dữ liệu đã xóa. Nếu tombstone ở các replica khác bị purge trước khi delete lan tới replica cũ, những dữ liệu đó có nguy cơ sống lại; phải xử lý theo runbook repair/rebuild và xác nhận an toàn.

**Bài 6.** Sau `LOCAL_QUORUM` write thành công, một request `LOCAL_ONE` đọc từ N3 cho giá trị cũ. Có chứng minh quorum write đã sai không?

**Đáp án:** Chưa. `LOCAL_QUORUM` cần hai trong ba ACK; N3 có thể chưa được cập nhật. `LOCAL_ONE` đọc từ một replica bất kỳ phù hợp có thể nhìn thấy giá trị cũ trước khi hội tụ.

**Bài 7.** Một ứng dụng thường xuyên đọc-sửa-ghi số dư trên cùng row, đều dùng `LOCAL_QUORUM`. Điều đó có ngăn lost update khi hai client thao tác đồng thời không?

**Đáp án:** **Không.** CL không biến vòng đọc-sửa-ghi thành transaction cách ly. Cần thiết kế lại luồng cập nhật, kiểm soát đồng thời hoặc dùng cơ chế điều kiện thích hợp (ví dụ LWT khi đúng trường hợp), đồng thời xem xét chi phí và giới hạn của cơ chế đó.

## 13. Quy trình quyết định: quorum đã đủ hay cần repair?

~~~mermaid
flowchart TD
    A["Read/write Cassandra"] --> B["Xác định partition key, RF và topology"]
    B --> C["Chọn CL phù hợp mục tiêu consistency/latency"]
    C --> D{"R và W có giao nhau trong cùng tập replica?"}
    D -->|Có| E["Giúp đọc thấy write đã ACK theo các giả định"]
    D -->|Không| F["Có thể thấy stale data, nhất là xuyên DC"]
    E --> G{"Mọi replica/partition đã được kiểm tra?"}
    F --> G
    G -->|Không| H["Hints/read repair chỉ xử lý phần giới hạn"]
    G -->|Có| I["Vẫn giám sát lỗi, tombstone, repair history"]
    H --> J["Lập lịch anti-entropy repair đầy đủ"]
    J --> K["Kiểm tra kết quả và phạm vi repair"]
    I --> K
    K --> L["Theo dõi replica convergence và an toàn tombstone"]
~~~

**Ghi nhớ cốt lõi:** `R + W > RF` giải thích **vì sao hai quorum của cùng nhóm replica phải giao nhau**; nó **không có nghĩa mọi replica đã giống nhau**. Hinted handoff khắc phục một phần write bị lỡ trong thời gian ngắn, read repair có thể sửa những khác biệt được phát hiện trên đường đọc, còn **anti-entropy repair** là công việc bảo trì để đối chiếu và đồng bộ dữ liệu trên các replica, đặc biệt là những partition ít đọc và các tombstone có nguy cơ gây zombie data. Thiết kế đúng CL theo DC, theo dõi replica và repair hoàn tất là ba việc phải đi cùng nhau.
