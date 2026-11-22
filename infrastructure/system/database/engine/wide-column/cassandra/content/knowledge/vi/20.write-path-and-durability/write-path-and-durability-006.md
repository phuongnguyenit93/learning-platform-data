# Độ bền cục bộ so với độ bền nhờ nhiều bản sao

## 1. Hai lớp độ bền trong Apache Cassandra

Khi một ứng dụng ghi dữ liệu vào **Apache Cassandra**, có hai câu hỏi rất khác nhau:

1. **Trên một node, dữ liệu có thể được khôi phục sau khi tiến trình khởi động lại hay không?** Đây là câu hỏi về **độ bền cục bộ** (*local durability*): commit log, memtable, SSTable, cơ chế đồng bộ xuống thiết bị lưu trữ.
2. **Nếu cả một node hoặc ổ đĩa biến mất, cluster còn bản sao dữ liệu ở nơi khác hay không?** Đây là câu hỏi về **độ bền nhờ sao chép** (*replicated durability*): replica, replication factor (RF), consistency level (CL), fault domain và quá trình đồng bộ giữa các replica.

Cassandra là cơ sở dữ liệu **wide-column phân tán**: partition key xác định token, token cùng replication strategy quyết định những node lưu partition. Một node bất kỳ nhận truy vấn làm **coordinator**, chuyển mutation đến các replica của partition và chờ số xác nhận thích hợp theo consistency level.

Một thông báo ghi thành công không tự động có nghĩa “mọi replica đã ghi SSTable và mọi ổ đĩa đều đã fsync”. Muốn hiểu lời bảo đảm của thao tác ghi, phải hỏi **replica nào đã xác nhận**, và **mỗi replica đã thực hiện mức ghi bền cục bộ nào**.

**Kết quả cần đạt sau bài học:**

- Giải thích đường ghi cục bộ qua **commit log → memtable → SSTable** và vai trò của `fsync`.
- Phân biệt số replica theo **RF** với số xác nhận phải chờ theo **CL**.
- Phân tích điều gì xảy ra khi tiến trình chết, mất điện, hỏng đĩa, mất node hoặc mất data center.
- Nhận diện giới hạn của hinted handoff, repair, compaction, timeout và retry.
- Thực hành CQL và Java Driver với ví dụ ghi theo partition key.

**Giả định:** các ví dụ dùng full replica thông thường, `NetworkTopologyStrategy`, không xét transient replication hay LWT/Paxos trừ khi nêu rõ. Chi tiết cấu hình commit log và hành vi xử lý có thể khác giữa các phiên bản Cassandra.

## 2. Định nghĩa: local durability khác replicated durability thế nào?

| Góc nhìn | Độ bền **cục bộ** | Độ bền **nhờ nhiều bản sao** |
| --- | --- | --- |
| Phạm vi | Một Cassandra node, tiến trình và thiết bị lưu trữ của node đó | Nhiều replica trên những node/rack/DC khác nhau |
| Cơ chế chính | Commit log, memtable, flush thành SSTable, đồng bộ dữ liệu xuống storage | Replication strategy, RF, coordinator phân phối mutation, CL quyết định ngưỡng ACK |
| Chịu được lỗi gì? | Có thể phục hồi từ commit log/SSTable sau crash nếu bản ghi đã bền trên storage | Có thể còn dữ liệu khi một node hoặc ổ đĩa mất vĩnh viễn, nếu replica khác có bản ghi |
| Không tự giải quyết | Mất cả ổ đĩa, mất node, lỗi storage làm mất dữ liệu chưa đồng bộ | Ghi mất trước khi replica nào lưu bền; mất đồng thời nhiều bản sao; xóa nhầm được nhân bản |
| Yếu tố thiết kế | `commitlog_sync`, storage, flush, filesystem và bảo đảm fsync | RF theo DC, rack placement, CL, repair, hints và vận hành |

**Lưu ý về chữ “local”:** *local durability* ở đây nghĩa là độ bền **bên trong một node**. Nó **không đồng nghĩa** `LOCAL_ONE` hay `LOCAL_QUORUM` — hai consistency level dùng chữ “LOCAL” để chỉ **data center cục bộ của coordinator**, không nói trực tiếp bản ghi đã fsync hay chưa.

### Ví dụ trực giác

Giả sử một partition được lưu ở ba node **N1, N2, N3**, và **N4** nhận lệnh ghi từ client:

~~~mermaid
flowchart LR
    C["Ứng dụng Java"] --> K["N4: coordinator"]
    K --> R1["N1: replica"]
    K --> R2["N2: replica"]
    K --> R3["N3: replica"]
    R1 --> L1["Commit log + memtable N1"]
    R2 --> L2["Commit log + memtable N2"]
    R3 --> L3["Commit log + memtable N3"]
~~~

Ở mỗi node replica có **một đường ghi cục bộ**. Tập N1–N3 tạo thành **lớp sao chép**. N4 có thể là coordinator mà **không hề là replica** của partition; nó không được tính như bản sao thứ tư.

## 3. Một replica ghi dữ liệu thế nào?

### 3.1. Các bước chính của write path

Với thao tác `INSERT`, `UPDATE` hay `DELETE` thông thường, replica nhận một **mutation** do coordinator gửi đến. Đường ghi logic được minh họa như sau:

~~~mermaid
flowchart TD
    M["Replica nhận mutation"] --> C["Append vào commit log"]
    M --> P["Cập nhật memtable trong RAM"]
    C --> A["Đủ điều kiện gửi ACK nội bộ"]
    P --> A
    P --> F["Memtable được flush về sau"]
    F --> S["SSTable trên đĩa"]
    S --> X["Compaction có thể hợp nhất SSTable"]
    C -.-> Y["Commit log segment được tái sử dụng khi an toàn"]
    S -.-> Y
~~~

- **Commit log** là nhật ký ghi nối tiếp trên storage, dùng để **replay** các mutation đã ghi nhận sau sự cố. Nó hỗ trợ khôi phục dữ liệu còn ở memtable nhưng chưa flush thành SSTable.
- **Memtable** chứa dữ liệu đang được cập nhật trong bộ nhớ, giúp write path không phải sửa từng SSTable ngẫu nhiên. Chỉ có dữ liệu trong RAM thì chưa đủ bảo đảm phục hồi sau mất điện.
- **SSTable** là file dữ liệu bất biến được tạo khi flush memtable; các SSTable có thể được hợp nhất hoặc loại bỏ phiên bản cũ bằng compaction theo chính sách.
- **ACK của replica** xác nhận việc xử lý mutation theo đường ghi và cấu hình hiện tại. Nó **không có nghĩa memtable đã flush thành SSTable**.

Cassandra có thể ghi commit log vào bộ đệm của hệ điều hành trước khi các byte thật sự được ép xuống thiết bị lưu trữ. Vì vậy, cần phân biệt **đã append/đã được hệ điều hành nhận** với **đã được đồng bộ bền bằng fsync**.

### 3.2. Commit log sync: cửa sổ mất dữ liệu cục bộ

Tham số `commitlog_sync` trong cấu hình Cassandra ảnh hưởng thời điểm hệ thống đồng bộ commit log và trả ACK. Hai chế độ chính thường được nhắc đến:

| Chế độ | Ý tưởng | Ý nghĩa đối với durability cục bộ |
| --- | --- | --- |
| `periodic` | Đồng bộ commit log xuống storage theo chu kỳ cấu hình; thao tác ghi không chờ một lần fsync riêng cho mỗi mutation | ACK có thể đến **trước lần đồng bộ tiếp theo**. Nếu mất điện đột ngột hoặc mất dữ liệu bộ đệm, các write vừa ACK trên node vẫn có nguy cơ mất. |
| `batch` | Gom mutation trong một cửa sổ ngắn rồi đồng bộ commit log trước khi xác nhận batch | Giảm cửa sổ ACK trước fsync ở cấp node nhưng thường tăng chi phí/độ trễ ghi; còn phụ thuộc độ tin cậy của hệ điều hành và phần cứng. |

Tên tham số phụ trợ, mặc định, giới hạn và cách tinh chỉnh có thể thay đổi theo phiên bản Cassandra. Không nên lấy giá trị mặc định của một bản phát hành để kết luận về cluster khác: hãy kiểm tra **cấu hình thực tế** và cách storage đáp ứng yêu cầu đồng bộ.

**Điểm quan trọng:** trong chế độ `periodic`, nhận ACK từ replica không luôn đồng nghĩa commit log của replica đó đã được **fsync**. Trong chế độ `batch`, đồng bộ trước ACK làm cam kết cục bộ mạnh hơn theo cơ chế của Cassandra, nhưng ổ đĩa/controller hỏng hoặc báo sai việc ghi bền vẫn có thể gây mất dữ liệu.

### 3.3. Sau crash, khôi phục dựa vào đâu?

| Tình huống tại **một replica** | Kỳ vọng phục hồi |
| --- | --- |
| Tiến trình Cassandra lỗi; commit log và SSTable trên storage vẫn còn, các mutation đã được sync | Khi khởi động lại, Cassandra có thể replay commit log để phục hồi dữ liệu chưa flush. |
| Tiến trình lỗi, dữ liệu mới chỉ ở memtable nhưng commit log tương ứng đã bền | Memtable cũ mất, nhưng replay log có thể dựng lại mutation. |
| Mất điện trước khi phần commit log mới được sync bền | Replica đó có thể mất một số mutation mới dù đã phát ACK trong cấu hình cho phép ACK sớm. |
| Ổ đĩa chứa dữ liệu/commit log mất không phục hồi | Độ bền cục bộ của node không cứu được dữ liệu đó; phải dựa vào replica khác hoặc backup. |

Flush và compaction quan trọng cho quản lý storage, hiệu năng đọc và giải phóng các segment commit log không còn cần thiết. Chúng **không thay thế** replication và cũng không có nghĩa “mỗi ACK phải đợi compaction”.

## 4. Replication factor và consistency level: lớp bảo vệ thứ hai

Trong keyspace, **replication factor (RF)** xác định số node replica mục tiêu giữ một partition. Với `NetworkTopologyStrategy`, RF được cấu hình **riêng cho mỗi data center**. **Consistency level (CL)** là số phản hồi replica phù hợp mà coordinator phải thu được trước khi trả kết quả cho client.

Ví dụ: một DC tên `dc1`, ít nhất ba node, keyspace RF = 3. Partition của `device_id = 'sensor-9'` được lưu ở N1, N2, N3; N4 làm coordinator.

~~~mermaid
sequenceDiagram
    participant App as Java client
    participant N4 as N4 coordinator
    participant N1 as N1 replica
    participant N2 as N2 replica
    participant N3 as N3 replica
    App->>N4: INSERT (LOCAL_QUORUM)
    N4->>N1: Mutation
    N4->>N2: Mutation
    N4->>N3: Mutation
    N1-->>N4: ACK
    N2-->>N4: ACK
    N4-->>App: Success, đủ 2/3 ACK ở dc1
    Note over N3: Có thể chưa ACK lúc client nhận success
    N3-->>N4: ACK (nếu đến được)
~~~

`LOCAL_QUORUM` cần **2 trong 3** replica của `dc1` xác nhận. Một write thông thường vẫn được **gửi đến toàn bộ tập replica phù hợp**, nhưng coordinator không phải đợi ACK từ mọi replica để đạt CL này.

### Ngưỡng ACK khi RF = 3 trong một data center

| CL ghi | Phản hồi replica cần thiết | Ví dụ điều kiện thành công | Điều không được suy ra |
| --- | ---: | --- | --- |
| `ONE` hoặc `LOCAL_ONE` | 1 | N1 ACK | N2, N3 đã nhận, áp dụng hoặc fsync write. |
| `QUORUM` hoặc `LOCAL_QUORUM` | 2 | N1 và N2 ACK | N3 đã bắt kịp; N1/N2 nhất thiết đã fsync với `periodic`. |
| `ALL` | 3 | N1, N2, N3 đều ACK | Tất cả replica sẽ tồn tại mãi hoặc không thể mất đồng thời. |
| `ANY` (chỉ ghi) | Có thể xác nhận qua hint theo điều kiện Cassandra hỗ trợ | Không có replica trực tiếp ACK nhưng write được lưu dạng hint | Một replica đã có dữ liệu sẵn cho `SELECT` ngay. |

**RF không phải CL.** Đặt RF = 3 không đồng nghĩa mọi write chờ ba ACK. Ngược lại, đặt `ALL` không tạo thêm replica thứ tư. Tăng RF chỉ tăng số bản sao **mục tiêu**, cần đủ node phù hợp và đồng bộ dữ liệu sang replica mới.

**Thành công theo CL là điều kiện để coordinator trả lời**, còn độ bền thực tế của các ACK vẫn dựa vào cơ chế ghi cục bộ ở từng replica. Hai lớp bảo vệ bổ sung cho nhau nhưng không thể thay thế hoàn toàn cho nhau.

## 5. So sánh các lỗi bằng ví dụ cụ thể

Giả sử RF = 3 tại `dc1`, N1–N3 là full replica của partition, N4 là coordinator và các replica đã/đang xử lý một write mới.

| Sự cố | Nếu chỉ **N1** đã ACK ở `LOCAL_ONE` | Nếu **N1 và N2** đã ACK ở `LOCAL_QUORUM` |
| --- | --- | --- |
| Tiến trình N1 khởi động lại; commit log còn và đã sync | N1 có thể khôi phục mutation từ commit log | N1 khôi phục; N2 cũng đã áp dụng mutation |
| Mất ổ đĩa N1 ngay sau ACK, trước khi N2/N3 áp dụng write | **Có thể mất** phiên bản write mới nhất | N2 còn một bản sao đã ACK (nhưng độ bền fsync của N2 vẫn cần xem xét) |
| N3 mất kết nối nhưng N1/N2 khỏe | N1 có thể đáp ứng `LOCAL_ONE` | Hai ACK từ N1/N2 vẫn đủ `LOCAL_QUORUM` |
| N1 và N2 đều mất vĩnh viễn trước khi N3 nhận write | Write mới có nguy cơ mất nếu không còn bản sao/hint/backup hợp lệ | Dù client đã thấy thành công, mất cả các replica giữ write vẫn có thể gây mất dữ liệu |
| Mất điện đồng thời trước khi commit log trên các node đã ACK được sync | Có nguy cơ mất write trên N1 | Có nguy cơ mất write **trên cả N1 và N2** nếu cùng phụ thuộc dữ liệu chưa sync |

Bảng này minh họa **khả năng tồn tại của bản ghi**, không khẳng định tính sẵn sàng để phục vụ ngay một `SELECT`. Ví dụ, RF = 3 với một node lỗi vẫn có thể đáp ứng `LOCAL_QUORUM` nếu còn hai replica phản hồi, nhưng nếu hai node lỗi thì yêu cầu này không đủ quorum dù có bản sao tồn tại.

### Tránh nhầm durability và availability

- **Durability:** write đã xác nhận có còn phục hồi được sau một loại sự cố hay không?
- **Availability:** cluster có tiếp tục trả kết quả đọc/ghi theo CL được yêu cầu khi sự cố đang diễn ra hay không?

Với RF = 3, `ALL` đòi ba ACK trước khi trả thành công, nhưng chỉ cần một replica không khả dụng là những write mới dùng `ALL` có thể thất bại. `LOCAL_QUORUM` thường đánh đổi số phản hồi và khả năng chịu một replica lỗi trong DC. `LOCAL_ONE` có thể duy trì tính sẵn sàng cao hơn nhưng nếu write mới nhất chỉ tồn tại tại một replica, việc mất replica đó gây rủi ro dữ liệu lớn hơn.

### Vì sao câu “RF = 3 bảo đảm không mất dữ liệu” là sai?

RF = 3 không bảo vệ tuyệt đối khỏi:

- Việc ghi bị ACK trước `fsync` ở nhiều node cùng lúc và sau đó **mất điện đồng thời**.
- Việc ghi chỉ đạt `ONE`, trong khi replica đã ACK bị mất vĩnh viễn trước khi các replica khác nhận dữ liệu.
- Lỗi chung của cùng rack, cùng thiết bị storage, cả data center hoặc thao tác vận hành sai.
- Dữ liệu bị `DELETE`, `UPDATE` sai hoặc corruption **được lan truyền** giữa các replica.
- Sự cố lâu ngày không repair khiến những bản sao đã lệch nhau hoặc mất khả năng đồng bộ an toàn.

Độ bền theo nhiều bản sao cải thiện khả năng chịu hỏng **thành viên độc lập**; mức bảo đảm thực tế phụ thuộc cách triển khai và các lỗi tương quan.

## 6. Nhiều data center: RF theo DC và phạm vi của `LOCAL_QUORUM`

Xét keyspace:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3,
  'dc2': 3
};
~~~

Mỗi partition có mục tiêu **3 replica tại `dc1`** và **3 replica tại `dc2`** nếu topology có đủ node. Với coordinator tại `dc1`:

| CL ghi | Điều kiện trả thành công | Ý nghĩa trong sự cố DC |
| --- | --- | --- |
| `LOCAL_ONE` | 1 ACK thuộc `dc1` | Không cần chờ `dc2`. |
| `LOCAL_QUORUM` | 2 ACK thuộc `dc1` | Không bảo đảm các replica `dc2` đã áp dụng write lúc success. |
| `QUORUM` | 4 ACK trong tổng 6 replica | Cần quorum toàn cluster; phản hồi có thể từ cả hai DC. |
| `EACH_QUORUM` (ghi) | 2 ACK ở **mỗi** DC | Đòi hai DC cùng đáp ứng điều kiện ghi. |
| `ALL` | Cả 6 ACK | Mất một replica có thể làm request `ALL` thất bại. |

Trong write thông thường, coordinator có thể gửi mutation tới các replica ở cả `dc1` và `dc2`, nhưng nếu dùng `LOCAL_QUORUM`, nó **không cần chờ ACK từ `dc2`**. Nếu `dc1` mất ngay sau khi client nhận thành công và trước khi write mới tới `dc2`, **không được mặc định rằng dữ liệu đó có thể phục hồi ở `dc2`**.

Chọn CL cần xuất phát từ **mục tiêu chịu lỗi** và chi phí độ trễ qua DC; nếu yêu cầu write đã ACK phải được xác nhận ở hơn một DC, chính sách ghi cần thể hiện điều này và ứng dụng phải chấp nhận việc mất kết nối liên DC có thể khiến write không thành công.

Đặt các replica trên các **rack/fault domain độc lập** theo topology đúng giúp giảm rủi ro lỗi tương quan. Chỉ tăng số node trong cùng miền lỗi hoặc tăng `num_tokens` không mang lại khả năng chống hỏng DC tương đương.

## 7. Hints, repair và backup nằm ở đâu trong bức tranh?

| Cơ chế | Dùng để làm gì? | Có bảo đảm durability cho mọi write không? |
| --- | --- | --- |
| **Hinted handoff** | Tạm ghi nhận mutation chưa chuyển đến một replica không khả dụng để phát lại khi replica trở lại | **Không.** Hints có giới hạn thời gian, cấu hình và điều kiện hoạt động; không phải replica đầy đủ hay thay thế repair. |
| **Read repair** | Khi đọc gặp các replica không thống nhất, có thể đối chiếu và sửa theo cơ chế/phiên bản | **Không.** Chỉ liên quan phạm vi dữ liệu được đọc và hành vi repair cụ thể. |
| **Anti-entropy repair** | So sánh và đồng bộ dữ liệu giữa các replica, đặc biệt các partition ít đọc | **Không thay thế bảo đảm thời điểm ACK**; rất cần cho sự hội tụ và an toàn vận hành lâu dài. |
| **Compaction** | Hợp nhất và dọn SSTable trên **một node**, theo chính sách compaction | **Không.** Không tạo thêm replica hay sửa sai khác giữa các node. |
| **Snapshot/backup** | Giữ điểm khôi phục riêng trước lỗi vận hành, corruption hoặc mất nhiều bản sao | Cung cấp phương án restore, nhưng RPO/RTO phụ thuộc lịch backup và quy trình thử khôi phục. |

### Tại sao `ANY` không giống `ONE`?

`ONE` cần ít nhất một replica thực sự phản hồi. `ANY` chỉ dùng cho write; trong một số tình huống coordinator có thể chấp nhận thành công khi mutation được ghi dưới dạng **hint**, chưa có full replica nào áp dụng nó. Do đó, một `SELECT` ngay sau write `ANY` có thể **chưa đọc thấy dữ liệu**. Đây không phải lựa chọn mặc định cho nghiệp vụ cần xác nhận đã tồn tại ở replica ngay lập tức.

### Replica bảo vệ khỏi mất node, backup bảo vệ khỏi các sự cố khác

Replication có thể nhân rộng cả **lệnh xóa nhầm** hoặc **dữ liệu bị sửa sai** tới các replica. Ngoài replica, hệ thống quan trọng cần backup, kiểm tra khả năng restore, bảo vệ chống hỏng đồng thời và một kế hoạch khôi phục theo mục tiêu RPO/RTO. Khi thay RF hoặc thay topology, cần theo dõi streaming và chạy quy trình repair thích hợp; không giả định việc đổi metadata là tất cả dữ liệu cũ đã được sao chép xong.

## 8. Thực hành CQL: cùng một dữ liệu, các ngưỡng ACK khác nhau

Ví dụ lab có data center thực tế tên `dc1` và **ít nhất ba node Cassandra** trong DC đó. Nếu triển khai khác, thay tên DC/RF cho phù hợp trước khi chạy.

### 8.1. Tạo bảng theo nhu cầu đọc

Giả sử ứng dụng đọc các phép đo trong một ngày của từng cảm biến. Ta dùng **khóa phân vùng kép** `(sensor_id, event_day)` để giới hạn kích thước partition và giữ các điểm đo cùng ngày gần nhau:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry.readings_by_sensor_day (
  sensor_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  reading decimal,
  PRIMARY KEY ((sensor_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Số replica của partition được quyết định bởi token của **toàn bộ partition key** `(sensor_id, event_day)` và replication của `telemetry`. Thay CL không đổi số replica và không đổi token của partition.

### 8.2. Đổi CL trong cqlsh và quan sát

~~~sql
CONSISTENCY LOCAL_ONE;
TRACING ON;

INSERT INTO telemetry.readings_by_sensor_day
  (sensor_id, event_day, event_time, event_id, reading)
VALUES
  ('sensor-9', '2026-11-21', '2026-11-21T03:00:00Z',
   123e4567-e89b-42d3-a456-426614174001, 21.75);

CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry.readings_by_sensor_day
  (sensor_id, event_day, event_time, event_id, reading)
VALUES
  ('sensor-9', '2026-11-21', '2026-11-21T03:01:00Z',
   123e4567-e89b-42d3-a456-426614174002, 21.90);

SELECT event_time, event_id, reading
FROM telemetry.readings_by_sensor_day
WHERE sensor_id = 'sensor-9'
  AND event_day = '2026-11-21'
LIMIT 10;

TRACING OFF;
~~~

`CONSISTENCY` và `TRACING` là **lệnh của cqlsh**, không phải CQL gửi nguyên văn qua Java driver. Trace cho thấy đường điều phối và những endpoint tham gia (chi tiết tùy phiên bản và topology). Trong hai lần `INSERT`, dữ liệu có thể đi tới **cùng tập replica**; khác biệt là **ngưỡng phản hồi mà coordinator phải chờ**.

Để đối chiếu tình trạng node trong một lab riêng, có thể dùng:

~~~bash
nodetool status
~~~

Lệnh này thể hiện node đang `UN`, `DN`, DC/rack và các thông tin topology. Đừng lấy `UN` của coordinator làm bằng chứng đã có đủ ACK; trạng thái node chỉ là một phần để diễn giải kết quả. Không nên dừng node hoặc mô phỏng mất điện trên cluster sản xuất để “thử durability”.

### 8.3. Bài tập suy luận với RF = 3

Giả sử replica của partition là N1, N2, N3; sau khi N1/N2 có ACK nhưng N3 chưa ACK:

- Với `LOCAL_QUORUM`, **write có thể trả success** nhờ đủ 2 ACK ở DC.
- Nếu N3 mất kết nối, dữ liệu mới vẫn có thể tồn tại ở N1/N2.
- Nếu **ổ đĩa N1 mất vĩnh viễn**, N2 còn mutation nếu đã lưu được theo bảo đảm cục bộ tương ứng. Điều này **khác** trường hợp chỉ N1 từng ACK theo `LOCAL_ONE`.
- Nếu N1 và N2 cùng mất dữ liệu chưa sync và N3 chưa nhận write, **success của client không ngăn được việc mất write**.

## 9. Từ ứng dụng Java: đặt CL theo từng lệnh ghi

Đây là ví dụ Java Driver 4.x với table ở trên. Dữ liệu mẫu cố định `event_id` để dễ đối chiếu retry và readback:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.math.BigDecimal;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public class WriteSensorReading {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement prepared = session.prepare(
                    "INSERT INTO telemetry.readings_by_sensor_day " +
                    "(sensor_id, event_day, event_time, event_id, reading) " +
                    "VALUES (?, ?, ?, ?, ?)");

            BoundStatement write = prepared.bind(
                    "sensor-9",
                    LocalDate.of(2026, 11, 21),
                    Instant.parse("2026-11-21T03:02:00Z"),
                    UUID.fromString("123e4567-e89b-42d3-a456-426614174003"),
                    new BigDecimal("22.10"))
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            session.execute(write);
        }
    }
}
~~~

- Driver chọn node nhận request (coordinator) theo policy và metadata; Cassandra quyết định replica bằng partition key, token và replication strategy.
- `setConsistencyLevel(LOCAL_QUORUM)` yêu cầu đủ **ACK replica trong data center cục bộ**. Nó **không** trực tiếp cấu hình `commitlog_sync` hay ép mọi replica `fsync` từng write.
- `withLocalDatacenter("dc1")` phải khớp tên DC thực tế; `127.0.0.1` chỉ minh họa cho lab cục bộ.
- Khi request **timeout**, không thể khẳng định write đã thất bại hoàn toàn: một số replica có thể đã lưu dữ liệu. Trước khi thiết kế retry, cần xem xét **idempotency**, timestamp, việc cấp khóa ổn định và khả năng ghi trùng hoặc đè lên write đồng thời.

Với một phép đo được nhận từ thiết bị, ứng dụng có thể cấp `event_id` ổn định ngay từ nguồn và lưu thông tin idempotency để thử lại có kiểm soát. Không tự động xem mọi `UPDATE`, thao tác counter hoặc list append là an toàn khi lặp lại.

## 10. Chọn chiến lược phù hợp theo mục tiêu lỗi

| Yêu cầu nghiệp vụ | Hướng thiết kế | Đánh đổi |
| --- | --- | --- |
| Giảm độ trễ khi chấp nhận mất một phần write rất mới trong sự cố hiếm | Đánh giá `LOCAL_ONE` cùng chính sách retry, backup và đo hiệu năng | Nguy cơ mất phiên bản mới nhất nếu chỉ một replica đã nhận trước khi nó mất. |
| Cần chịu lỗi một replica trong DC và giảm nguy cơ write chỉ nằm ở một node | RF đủ lớn, `LOCAL_QUORUM` cho write quan trọng | Cần tối thiểu quorum trả lời; thường tăng thời gian chờ hơn `LOCAL_ONE`. |
| Muốn write được xác nhận ở nhiều DC | RF ở từng DC và chính sách xác nhận xuyên DC thích hợp, ví dụ `EACH_QUORUM` với write | Latency và tính sẵn sàng phụ thuộc mạng liên DC. |
| Giảm cửa sổ mất write đã ACK khi mất điện đột ngột trên một node | Đánh giá `commitlog_sync`, đặc tính fsync của storage và chế độ mất điện | Sync chặt hơn có chi phí latency/throughput; không thay RF. |
| Phục hồi xóa nhầm, corruption hoặc mất hàng loạt replica | Backup/snapshot, lưu giữ ngoài fault domain, kiểm tra restore định kỳ | Có chi phí lưu trữ/vận hành và RPO/RTO riêng. |

### Checklist vận hành gắn với đúng lớp

1. **Tại replica:** xem cấu hình commit log, độ trễ đồng bộ storage, dung lượng và lỗi ổ đĩa; theo dõi tình trạng flush/commit log/compaction bằng metrics phiên bản đang chạy.
2. **Trên cluster:** đối chiếu topology, RF, rack/DC placement, các replica đang sống, write timeout/unavailable, hinted handoff và kết quả repair.
3. **Trong ứng dụng:** chọn CL theo từng workload, cấu hình local DC đúng, giám sát latency và retry; khi timeout coi kết quả ghi là **có thể đã áp dụng một phần**.
4. **Khôi phục thảm họa:** thực hành restore từ backup và xác định rõ RPO/RTO; không nhầm replication với lịch sử khôi phục.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Một replica đã gửi ACK khi commit log đang ở chế độ `periodic`. Có thể khẳng định commit log đã được fsync cho write đó không?

**Đáp án:** **Không.** ACK có thể đến trước lần đồng bộ định kỳ tiếp theo. Mất điện trước thời điểm đó có thể làm mất dữ liệu cục bộ.

**Câu 2.** RF = 3 trong một DC. Write `LOCAL_QUORUM` trả success sau hai ACK. Điều đó chứng tỏ replica thứ ba đã nhận write chưa?

**Đáp án:** **Chưa.** Coordinator chỉ cần hai xác nhận local. Replica thứ ba có thể xử lý hoặc bắt kịp sau đó.

**Câu 3.** Một node bị mất ổ đĩa vĩnh viễn; commit log của chính node đó trước sự cố đã được sync đầy đủ. Có thể khôi phục từ commit log trên ổ đã mất không?

**Đáp án:** **Không.** Sync giúp vượt qua lỗi tiến trình hoặc mất điện khi storage còn nguyên; hỏng mất ổ đĩa khiến phải dựa vào replica khác hoặc backup.

**Câu 4.** `dc1` có RF = 3 và `dc2` có RF = 3. Write `LOCAL_QUORUM` ở coordinator `dc1` báo thành công. Liệu lúc ấy dữ liệu chắc chắn tồn tại ở `dc2`?

**Đáp án:** **Không chắc chắn.** `LOCAL_QUORUM` chỉ yêu cầu hai ACK trong `dc1`. Các replica ở `dc2` có thể chưa áp dụng mutation.

**Câu 5.** Một đội vận hành tăng `num_tokens` từ 8 lên 16 để “tăng durability gấp đôi”, giữ RF = 2. Kết luận?

**Đáp án:** Không chính xác. Token count ảnh hưởng việc chia vùng dữ liệu, không làm số replica mỗi partition tăng. RF vẫn là 2; muốn tăng số bản sao cần thay replication và bảo đảm đủ node.

**Câu 6.** Dữ liệu bị xóa nhầm nhưng lệnh `DELETE` đã được replication đầy đủ. Repair có thể tự đưa dữ liệu về trước khi xóa không?

**Đáp án:** Thường **không**. Repair giúp replica hội tụ theo trạng thái dữ liệu/tombstone; muốn quay về dữ liệu trước khi xóa cần chiến lược backup/restore hoặc lịch sử nghiệp vụ thích hợp.

## 12. Mô hình tư duy cuối bài

~~~mermaid
flowchart TD
    A["Client gửi mutation"] --> B["Coordinator tìm replica bằng partition key và RF"]
    B --> C["Mỗi replica: commit log + memtable"]
    C --> D["Độ bền cục bộ: sync/flush, khả năng replay"]
    C --> E["ACK từ các replica"]
    E --> F{"Đủ ngưỡng consistency level?"}
    F -->|Có| G["Coordinator trả success"]
    F -->|Chưa| H["Chờ thêm, timeout hoặc unavailable"]
    D --> I["Bảo vệ khi crash tiến trình nếu log/dữ liệu còn bền"]
    G --> J["Mức sống sót khi mất node phụ thuộc các bản sao thực tế"]
    J --> K["Repair + fault domains + backup hỗ trợ vận hành lâu dài"]
~~~

**Nguyên tắc cần nhớ:** `commit log + memtable/SSTable` giải thích **một replica giữ lại dữ liệu thế nào**; `RF + topology` giải thích **có bao nhiêu node có thể giữ dữ liệu**; `CL` giải thích **cần bao nhiêu ACK để trả success**. Không lớp nào riêng lẻ bảo đảm chống mọi lỗi. Khi đánh giá một write Cassandra, hãy hỏi: **node nào là replica, những replica nào ACK, commit log đã sync ở mức nào, các bản sao có nằm ở các fault domain độc lập không, và có backup để phục hồi lỗi logic không?**
