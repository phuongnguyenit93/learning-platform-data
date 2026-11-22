# Hint backlog, dung lượng hints và replica vắng mặt kéo dài trong Apache Cassandra

## 1. Bối cảnh: ghi thành công không đồng nghĩa mọi replica đã đồng bộ

Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình **wide-column**, phân phối dữ liệu theo **partition key** và nhân bản theo replication strategy. Một bảng thường được thiết kế theo truy vấn, còn consistency level (CL) xác định số replica cần tham gia xác nhận đọc hoặc ghi. Vì vậy, một request ghi có thể thành công dù một replica chưa nhận được mutation.

Giả sử một keyspace có **replication factor (RF) = 3** trong một datacenter:

- Replica A và B hoạt động bình thường.
- Replica C mất kết nối.
- Ứng dụng ghi với `LOCAL_QUORUM`, và A cùng B xác nhận nên lệnh có thể thành công.
- C vẫn chưa có mutation mới. Khi C quay lại, nó cần cách bắt kịp các bản sao còn lại.

Cassandra cung cấp **hinted handoff** để hỗ trợ trường hợp này. Một node đủ điều kiện có thể lưu **hint** cho replica vắng mặt, sau đó phát lại mutation khi replica hồi phục. Cơ chế này hữu ích với outage ngắn nhưng là **best effort**: không bảo đảm toàn bộ dữ liệu đã đồng bộ, không thay thế anti-entropy **repair** và không làm thay đổi yêu cầu ACK của consistency level.

Bài thuộc chương **Đồng bộ bản sao** trong module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Chúng ta sẽ tập trung vào ba vấn đề: **hint backlog tích lũy**, **dung lượng hints tăng trên đĩa**, và **replica vắng mặt lâu hơn khoảng thời gian hệ thống hỗ trợ tạo hint**. Các ví dụ liên hệ với CQL, replication, xử lý lỗi và Java driver.

## 2. Hinted handoff tham gia đường ghi như thế nào?

### 2.1. Một kịch bản write với replica down

Coordinator nhận mutation, xác định replica theo token của partition key, rồi phân phối request. Nếu một replica đang được xem là không sẵn sàng, Cassandra có thể tạo hint mô tả mutation cần gửi cho replica đó, tùy cấu hình, thời gian downtime và khả năng lưu trữ.

~~~mermaid
sequenceDiagram
    participant J as Ứng dụng Java
    participant K as Coordinator
    participant A as Replica A
    participant B as Replica B
    participant C as Replica C (down)
    J->>K: INSERT, CL=LOCAL_QUORUM
    K->>A: Gửi mutation
    K->>B: Gửi mutation
    K--xC: Replica không sẵn sàng
    A-->>K: ACK
    B-->>K: ACK
    K->>K: Lưu hint cho C nếu đủ điều kiện
    K-->>J: Thành công theo LOCAL_QUORUM
    Note over C: C trở lại cluster
    K->>C: Phát lại hints còn hợp lệ
    C-->>K: Xác nhận nhận dữ liệu
~~~

Đây là một luồng **minh họa logic**, không khẳng định mọi bản Cassandra đều làm các bước theo cùng thứ tự hoặc luôn lưu được mọi hint. Mutation có thể được chuyển tới node khác giữ hint; số lượng và vị trí hints thực tế phụ thuộc coordinator, replication, policy và trạng thái cluster.

**Đặc biệt:** một hint **không phải ACK thay cho replica đích**. Nếu CL yêu cầu ba ACK mà chỉ hai replica thực sự xác nhận, coordinator không thể báo thành công chỉ vì đã lưu hint cho replica thứ ba.

### 2.2. Hint là gì, và không phải là gì?

Một hint là thông tin mutation cần phát lại đến replica đích. Các hint thường được ghi vào vùng lưu trữ hints của node giữ hint, qua cơ chế ghi file riêng của Cassandra và đường dẫn cấu hình như `hints_directory`.

Một hint **không phải snapshot cuối cùng** của partition. Nếu một row bị cập nhật nhiều lần trong lúc C offline, có thể tồn tại nhiều mutation cần phát lại; Cassandra vẫn dựa vào timestamp, tombstone và quy tắc hòa giải để xác định dữ liệu cuối cùng.

Hint cũng **không phải biên nhận bảo đảm dữ liệu đã đến replica đích**. Việc hint được lưu, hint được đưa vào hàng đợi phát lại, và replica thực sự nhận mutation là ba trạng thái khác nhau.

### 2.3. Hinted handoff khác repair ở đâu?

| Cơ chế | Mục đích | Giới hạn |
|---|---|---|
| **Hinted handoff** | Phát lại mutation từng bỏ lỡ cho một replica | Chỉ bao phủ những mutation đã có hint; phụ thuộc hint window, disk và replay |
| **Anti-entropy repair** | So sánh bản sao và đồng bộ phần dữ liệu khác biệt | Tốn network/I/O, phải lập lịch và giám sát |
| **Read repair** (tùy bản/cấu hình) | Xử lý một số khác biệt phát hiện trong lúc đọc | Không duyệt hết mọi partition không được truy vấn |
| **Streaming / rebuild / replace** | Chuyển dữ liệu khi phục hồi node hoặc đổi topology | Thực hiện theo quy trình topology riêng |
| **Compaction** | Hợp nhất SSTable trên một replica | Không chứng minh replica khác có đầy đủ mutation |

Hinted handoff giảm thời gian hồi phục khi outage ngắn. Repair vẫn cần để đối soát những khoảng không có hint hoặc hint đã mất.

## 3. Hint window: vì sao replica vắng mặt lâu là vấn đề?

Cassandra có giới hạn khoảng thời gian cho phép **tiếp tục tạo hint** cho replica bị đánh dấu vắng mặt, thường cấu hình qua `max_hint_window_in_ms`. Khi downtime vượt quá cửa sổ này, hệ thống có thể ngừng tạo hint mới cho replica đó.

Ví dụ **giả định** cửa sổ được cấu hình là ba giờ:

| Thời điểm | Diễn biến | Ý nghĩa |
|---|---|---|
| 09:00 | C down | Những write đủ điều kiện có thể sinh hint cho C |
| 10:30 | C vẫn down | Hint backlog tiếp tục tăng |
| 12:00 | Qua ba giờ | Các mutation về sau có thể không còn được lưu hint cho C |
| 14:00 | C vẫn down | Xuất hiện khoảng dữ liệu không có hint để phát lại |
| 15:00 | C hồi phục | Phát lại hints còn hợp lệ, nhưng vẫn có thể thiếu mutation sau cửa sổ |

**Không hiểu nhầm hint window là tuổi thọ cố định của mọi file hint**, hay cam kết rằng outage ngắn hơn cửa sổ sẽ luôn phục hồi đầy đủ. Đây là ngưỡng liên quan đến khả năng tạo hint cho node vắng mặt; việc lưu giữ, bỏ hoặc chuyển hint còn phụ thuộc phiên bản, cấu hình, lỗi hệ thống và năng lực replay.

Mốc ba giờ trong bảng chỉ phục vụ ví dụ, **không phải mặc định bắt buộc của mọi Cassandra cluster**. Cần kiểm tra giá trị thực tại cluster đang chạy.

### Replica UP chưa có nghĩa đã bắt kịp

Một replica trở lại trạng thái `UP` chỉ có nghĩa nó đã đủ điều kiện giao tiếp/nhận traffic theo health của cluster. Lúc đó:

1. Hints có thể còn nằm trên disk của nhiều coordinator.
2. Hệ thống cần replay với tốc độ phù hợp.
3. Trong thời gian replay, node đích vẫn có thể thiếu mutation đã xảy ra trước đó.
4. Mutation ngoài hint window hoặc hint bị mất không được tự động khôi phục nhờ replay.

Vì vậy, sau outage cần xác nhận **backlog giảm**, **replay không lỗi**, và **repair/đối soát được thực hiện nếu cần**, thay vì chỉ kiểm tra `nodetool status`.

## 4. Hint backlog hình thành và phát triển

**Hint backlog** là tổng lượng hints còn phải chuyển tới replica đích. Nó tăng khi có mutation được ghi thành hint nhưng chưa replay thành công. Khi node hồi phục, backlog có thể giảm nếu tốc độ phát lại vượt tốc độ phát sinh hints mới.

Mô hình tư duy:

~~~text
Thay đổi backlog theo thời gian
≈ hint bytes mới tạo
  - hint bytes chuyển thành công
  - hint bytes bị loại bỏ do cơ chế quản lý và điều kiện lưu giữ
~~~

Không nên coi một backlog giảm do file bị bỏ là bằng chứng replica đã đồng bộ. Cần theo dõi riêng **delivered**, **failed/dropped** và các kết quả khôi phục.

### Các yếu tố làm backlog tăng nhanh

- Tốc độ ghi lớn tới token ranges mà replica đang down chịu trách nhiệm.
- Mutation lớn, nhiều cột hoặc payload lớn.
- Nhiều replica cùng vắng mặt, khiến số bản hint cần giữ tăng.
- Outage kéo dài trong khoảng hint window.
- Hệ thống replay chậm do node đích yếu, mạng nghẽn, disk bận hoặc throttle.
- Compaction, streaming và repair cùng tranh I/O trên coordinator và đích.

Tổng write rate của cluster chưa chắc là write rate tạo hint cho **một replica cụ thể**. Khi dự báo, phải lọc theo traffic có replica đích nằm trong tập nhận mutation.

## 5. Ước lượng dung lượng hints trên đĩa

### 5.1. Công thức gần đúng

Với một khoảng downtime chưa replay, có thể ước lượng:

~~~text
Raw hint bytes
≈ số mutation đủ điều kiện / giây
  x số bytes hint trung bình / mutation
  x số giây có thể tạo hint
  x số replica đích cần hint cho cùng mutation
~~~

Đây là **ước lượng thô**, không phải cách Cassandra phân bổ chính xác từng tệp. Kích thước thực tế có metadata, biến động serialisation/compression, nhiều coordinator và hành vi retry. Nếu các mutation không đi tới cùng các replica down, không được nhân mù quáng theo tổng số replica vắng mặt.

### 5.2. Ví dụ tính dung lượng

Một replica C offline và traffic có thể tạo:

- 1.000 mutation/giây cần hint cho C.
- Trung bình 2 KiB cho mỗi hint.
- Ba giờ outage trong khoảng có thể tạo hint.
- Không có replay trong khoảng đó.

~~~text
Số mutation = 1.000 x 3 x 60 x 60 = 10.800.000
Hint bytes   = 10.800.000 x 2 KiB = 21.600.000 KiB
Dung lượng   ≈ 20,6 GiB
~~~

**20,6 GiB chỉ là dữ liệu thô của ví dụ**, chưa tính metadata, tốc độ tăng đột biến, SSTable mới, commit log, snapshots, compaction hoặc streaming. Hints có thể phân tán trên nhiều node giữ hint; mỗi node cần đủ headroom trên filesystem chứa `hints_directory`.

Một cách lập ngân sách thực tế:

~~~text
Free disk cần dự phòng
≥ peak hint backlog trên node
  + tăng trưởng write / flush đang diễn ra
  + các tác vụ nền cùng filesystem
  + biên an toàn theo runbook
~~~

Nếu hints được đặt trên ổ riêng, hãy tính trên ổ đó. Không lấy tổng dung lượng trống của toàn cluster để chứng minh một coordinator có đủ chỗ.

### 5.3. Backlog 12 GiB sẽ phát lại bao lâu?

Giả sử tốc độ replay thực đo là 8 MiB/s, không có hints mới và không có retry:

~~~text
12 GiB = 12 x 1024 MiB = 12.288 MiB
Thời gian lý tưởng = 12.288 / 8
                   = 1.536 giây
                   ≈ 25,6 phút
~~~

Đây chỉ là phép tính lý tưởng. Replay bị ảnh hưởng bởi throttle, băng thông mạng, CPU/đĩa node đích, lỗi/chậm phản hồi và việc các tác vụ khác cạnh tranh tài nguyên. Nếu node vừa UP nhưng vẫn bị quá tải, phát lại có thể kéo dài hơn rất nhiều.

### 5.4. Hints đầy đĩa ảnh hưởng gì?

- Hints tiêu tốn **dung lượng tạm** trong khi mutation vẫn có thể được ghi bình thường vào memtable/SSTable.
- Việc ghi hint tạo **disk write I/O**; replay tạo **disk read và network I/O**.
- Hints có thể cạnh tranh tài nguyên với compaction, flush, streaming và read/write của ứng dụng.
- Nếu hết không gian hoặc lỗi ghi hint, khả năng khôi phục bằng hinted handoff giảm. Hành vi tác động tới write request phụ thuộc phiên bản và CL; không được giả định mọi request lập tức lỗi hoặc chắc chắn thành công.

**Không xóa file hints bằng tay để chữa đầy đĩa.** Xóa có thể loại bỏ mutation mà replica chưa nhận. Việc thay đổi/bỏ hints phải là quyết định vận hành có kế hoạch repair/khôi phục phù hợp.

## 6. Consistency level không thay hinted handoff và ngược lại

Giả sử một DC có RF=3, một mutation cần đến A, B, C:

| Trạng thái | Write CL | Điều kiện thành công | Vai trò của hint |
|---|---|---|---|
| A và B sống; C down | `ONE` | Có thể thành công với ít nhất một ACK | Có thể giữ hint cho C |
| A và B sống; C down | `LOCAL_QUORUM` | Có thể thành công với hai ACK trong DC | Có thể giữ hint cho C |
| A và B sống; C down | `ALL` | Thiếu ACK của C, không thể đáp ứng CL | Hint không thay ACK |
| Chỉ A sống; B và C down | `LOCAL_QUORUM` | Không đủ quorum | Hints không làm write thành công |
| Chỉ A sống; B và C down | `ONE` | Có thể thành công với ACK của A | Nếu đủ điều kiện, có thể tạo hints cho B/C |

Bảng diễn giải điều kiện ACK trong một DC; timeout, nghẽn mạng hoặc node quá tải có thể khiến thao tác thất bại ngay cả khi số node UP trông có vẻ đủ.

Read CL cũng không chứng minh mọi replica đã bắt kịp. Một SELECT với `LOCAL_QUORUM` có thể trả về dữ liệu đúng cho partition được đọc, nhưng không phải bằng chứng toàn bộ dữ liệu trên C đã đồng bộ.

Ở cluster nhiều datacenter, các mức `LOCAL_QUORUM`, `QUORUM`, `EACH_QUORUM` và tùy chọn hinted handoff theo DC cần phân tích theo topology thực tế.

## 7. Replica offline dài ngày và rủi ro dữ liệu sai lệch

### 7.1. Mutation không có hint vẫn cần đồng bộ

Outage vượt hint window có thể tạo khoảng thời gian không còn hint mới. Hints cũng có thể thiếu vì tắt cơ chế, lỗi ghi, disk pressure, thay đổi topology hoặc phát lại thất bại.

Khi replica quay lại, nó có thể thiếu:

- Update mới nhất của một row.
- Một row mới được tạo trong thời gian down.
- DELETE hoặc tombstone đã phát sinh khi offline.
- Các giá trị hết hạn TTL/cập nhật mới so với dữ liệu cũ tại replica đó.

**Repair** so sánh các replica và đồng bộ những khác biệt còn tồn tại. Nó là công cụ cần cân nhắc sau outage dài hoặc khi replay không thể bảo đảm bao phủ mọi mutation.

### 7.2. Vì sao tombstone và `gc_grace_seconds` đặc biệt quan trọng?

DELETE và TTL trong Cassandra có thể tạo tombstone. Những dấu xóa này giúp ngăn giá trị cũ sống lại khi các replica khác chưa nhận mutation xóa.

Giả sử C không nhận DELETE trong lúc down. Trong khi đó A/B đã hoàn tất các compaction và tombstone đủ điều kiện bị loại khỏi dữ liệu lưu. Khi C hoạt động lại, nó có thể vẫn giữ một giá trị cũ mà không còn tombstone tương ứng trên replica khỏe để che giá trị đó. Kết quả có thể là **zombie data**.

Vì vậy:

1. Không giảm `gc_grace_seconds` chỉ vì muốn thu hồi tombstone/hints nhanh.
2. Lịch repair phải được thiết kế phù hợp với khoảng thời gian replica có thể offline và chính sách giữ tombstone.
3. Với outage **dài tới mức có rủi ro tombstone đã bị loại trước khi replica quay lại**, không mặc định “bật lên rồi chạy repair” luôn đủ an toàn. Cần đánh giá rebuild/replace/resync theo runbook và tình trạng dữ liệu trước khi cho node cũ phục vụ.
4. Repair có thể tốn network, CPU, disk, streaming và compaction; cần capacity plan thay vì chạy toàn cluster thiếu kiểm soát.

Hãy xem cả `max_hint_window_in_ms` lẫn `gc_grace_seconds`: hai thông số phục vụ **hai mục đích khác nhau**. Hint window giới hạn cơ hội tạo hint; grace liên quan an toàn giữ dấu xóa. Không nên coi chúng là một giới hạn downtime chung.

### 7.3. Quy tắc quyết định theo mức độ vắng mặt

| Trường hợp | Phương án hợp lý |
|---|---|
| Down ngắn trong hint window | Phục hồi node, giám sát replay và duy trì repair định kỳ |
| Down gần hoặc vượt hint window | Kiểm tra hints, lên repair cho phần dữ liệu chưa chắc được replay |
| Down rất lâu, vượt ngưỡng an toàn dữ liệu/xóa | Đánh giá rủi ro zombie; có thể cần rebuild/replace theo runbook |
| Node mất dữ liệu hoặc đổi danh tính/topology | Dùng quy trình thay node và streaming; không dựa hoàn toàn vào hints gắn với node cũ |

Các hàng trên là hướng dẫn đánh giá. Phải dựa vào phiên bản Cassandra, cấu hình thực tế, downtime đã ghi nhận, trạng thái replica và chính sách repair.

## 8. Chẩn đoán backlog: nên theo dõi những gì?

### 8.1. Nhóm metrics hữu ích

| Nhóm | Theo dõi | Mục đích |
|---|---|---|
| **Dung lượng** | Bytes/file hints và free space filesystem | Phát hiện nguy cơ đầy đĩa |
| **Hint creation** | Tốc độ hints được tạo, chia theo node/đích nếu có | Xác định tốc độ tăng nợ |
| **Hint delivery** | Hints delivered, failed/retried, throughput | Đánh giá khả năng xả backlog |
| **Tuổi backlog** | Thời điểm hint cũ nhất/đợt backlog bắt đầu nếu thu thập được | Phát hiện nợ kéo dài |
| **Node đích** | UP/DOWN, disk I/O, CPU, network, mutation latency | Biết node có đủ sức nhận replay |
| **Tác vụ nền** | Compaction, repair, streaming, flush | Nhận diện tranh chấp I/O |
| **Chất lượng dữ liệu** | Repair result, phạm vi outage, mismatch | Kiểm tra tính đầy đủ sau replay |

Tên metric cụ thể trong JMX, exporter hoặc dashboard phụ thuộc phiên bản Cassandra. Khi cấu hình cảnh báo, hãy xác nhận đơn vị đo và ý nghĩa từng metric, đặc biệt **created**, **delivered**, **failed/dropped** có thể khác nhau.

Chỉ số quan trọng nhất không phải “C hiện UP” mà là **backlog có giảm một cách bền vững hay không**, cộng với việc phần dữ liệu ngoài hint window đã được xử lý chưa.

### 8.2. Các lệnh hỗ trợ điều tra

Ví dụ chạy trên node Cassandra có quyền phù hợp:

~~~bash
# Trạng thái node theo datacenter và token.
nodetool status

# Thông tin node hiện tại.
nodetool info

# Trạng thái các phiên streaming/rebuild/repair streaming.
# Không phải công cụ đo đầy đủ hinted handoff.
nodetool netstats

# Compaction cạnh tranh băng thông đĩa.
nodetool compactionstats

# Kiểm tra lệnh hints hỗ trợ bởi đúng phiên bản.
nodetool help
~~~

Nếu chạy Linux, có thể kiểm tra dung lượng thực của hints directory **sau khi xác nhận đúng đường dẫn**:

~~~bash
du -sh /var/lib/cassandra/hints
df -h /var/lib/cassandra/hints
~~~

`du` đo dung lượng thư mục; `df` đo filesystem free space. Nếu cluster đặt `hints_directory` ở vị trí khác, phải thay đường dẫn. Đừng suy luận backlog phát lại từ `df` một mình.

### 8.3. Đọc log theo dòng thời gian

Một timeline điều tra có thể trông như sau:

~~~text
09:10  C được đánh dấu DOWN
09:12  hint bytes bắt đầu tăng ở các coordinator
11:40  disk free chạm ngưỡng cảnh báo
12:10  C trở lại UP, replay bắt đầu nhưng chậm
13:00  replay throughput tăng, backlog giảm
14:30  backlog nhỏ nhưng vẫn phải xét khoảng vượt hint window
~~~

Đây chỉ là ví dụ mô tả. Cần đối chiếu log node, metrics hints, network, disk và thời điểm restart để phân biệt **không tạo được hint**, **có hint nhưng chưa replay**, **replay thất bại** và **đã replay xong nhưng cần repair**.

## 9. Cấu hình ảnh hưởng tới hints và những đánh đổi

Các tên cấu hình thường gặp, phụ thuộc Cassandra version:

| Cấu hình | Ý nghĩa | Đánh đổi |
|---|---|---|
| `hinted_handoff_enabled` | Cho phép cơ chế hinted handoff | Tắt làm tăng phụ thuộc vào repair để bắt kịp |
| `max_hint_window_in_ms` | Giới hạn thời gian tạo hints cho replica down | Dài hơn có thể tăng lượng hints cần giữ; ngắn hơn tăng khoảng thiếu |
| `hints_directory` | Nơi lưu hints trên node | Cần disk headroom, tránh nghẽn với dữ liệu/commit log |
| `hinted_handoff_throttle_in_kb` hoặc cơ chế điều tiết tương ứng | Giới hạn tốc độ delivery theo phiên bản | Quá thấp: backlog lâu giảm; quá cao: node đích bị quá tải |
| Giới hạn số luồng, kích thước file, thời gian flush hints | Cách viết và gửi hints | Có thể ảnh hưởng I/O, độ trễ và mức tiêu thụ tài nguyên |
| Chính sách theo datacenter nếu được hỗ trợ | Phạm vi tạo hints xuyên DC | Ảnh hưởng network và trách nhiệm sửa sai lệch |

Không thay đổi dựa trên mặc định của một bài hướng dẫn mà chưa xác nhận bản Cassandra. Đặc biệt, tăng hint window không tự tạo thêm dung lượng disk hay khả năng replay. Điều chỉnh throttle cũng phải đo cả **node gửi** lẫn **node nhận**, cùng p95/p99 latency của ứng dụng.

## 10. Ví dụ CQL và Java: viết đúng consistency nhưng vẫn cần repair

### 10.1. Keyspace và bảng minh họa

Giả sử có một datacenter tên `dc1` và ba replica. Tên DC trong thực tế phải lấy từ cấu hình cluster:

~~~cql
CREATE KEYSPACE demo_sync
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE demo_sync.sensor_by_id (
    sensor_id uuid PRIMARY KEY,
    state text,
    updated_at timestamp
);
~~~

Trong `cqlsh`, thiết lập write CL và thực hiện thao tác ghi:

~~~cql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO demo_sync.sensor_by_id (sensor_id, state, updated_at)
VALUES (
    11111111-1111-1111-1111-111111111111,
    'ACTIVE',
    '2026-11-21T08:00:00Z'
);

SELECT sensor_id, state, updated_at
FROM demo_sync.sensor_by_id
WHERE sensor_id = 11111111-1111-1111-1111-111111111111;
~~~

Trong kịch bản A/B sống, C down, INSERT có thể thành công với `LOCAL_QUORUM`. Nhưng SELECT thành công sau đó **không chứng minh** C đã nhận bản ghi. Trạng thái hint/replay phải kiểm tra ở tầng vận hành, và repair vẫn cần khi có khả năng dữ liệu thiếu.

### 10.2. Java Driver 4.x

Với `CqlSession session` đã kết nối đúng keyspace/datacenter, ứng dụng có thể nêu rõ write consistency:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.util.UUID;

// Chuẩn bị một lần, tái sử dụng trong service.
PreparedStatement insert = session.prepare(
    "INSERT INTO demo_sync.sensor_by_id " +
    "(sensor_id, state, updated_at) VALUES (?, ?, ?)"
);

UUID sensorId =
    UUID.fromString("11111111-1111-1111-1111-111111111111");

BoundStatement statement = insert.bind(
        sensorId, "ACTIVE", Instant.parse("2026-11-21T08:00:00Z"))
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

session.execute(statement);
~~~

Nếu lệnh không ném exception, client biết request đã được xử lý thành công theo write consistency và giao thức driver/server. Điều đó **không mang nghĩa mọi replica đã đồng bộ**, và API này không trả trạng thái hint backlog.

Ngược lại, nếu write timeout hoặc mất kết nối, không được kết luận chắc chắn mutation chưa đi vào replica nào. Thiết kế retry với khóa ổn định và side effects có khả năng chống trùng; lưu operation ID khi nghiệp vụ yêu cầu; quan sát lỗi ở cả tầng service và Cassandra.

Ví dụ driver này là **ghi thông thường**, không phải LWT. Mức `LOCAL_QUORUM` giúp xác định ACK, không tạo compare-and-set hoặc sửa các replica đã bỏ lỡ mutation khác.

### 10.3. Thiết kế truy vấn và partition vẫn quan trọng

Bảng phục vụ truy vấn theo `sensor_id` có thể đọc chính xác partition bằng khóa chính. Tuy nhiên một truy vấn như vậy không thể dùng để xác minh toàn bộ token ranges đã được đồng bộ. Nếu node offline lâu, không nên quét toàn bảng từ Java chỉ để kiểm tra: hãy dùng repair và các công cụ giám sát phù hợp.

## 11. Runbook: node down lâu, hint disk đang đầy

**Bước 1 — Xác định phạm vi outage.** Ghi mốc bắt đầu, node/đích bị ảnh hưởng, DC, token ranges, RF và write CL. Đối chiếu `nodetool status` với logs, write timeout và sự cố hạ tầng.

**Bước 2 — Đo backlog và disk headroom.** Tính bytes hints trên từng node giữ hint, free space từng filesystem, tốc độ hints created/delivered và tốc độ write mới. Xem compaction/streaming có chiếm I/O song song không.

**Bước 3 — Khắc phục nguyên nhân replica down.** Kiểm tra mạng, đĩa, process, GC, capacity và health node đích. Một node vừa UP nhưng còn chậm có thể không đủ sức nhận lượng replay lớn.

**Bước 4 — Điều tiết replay theo số đo.** Theo dõi throughput, retry/error, I/O và p95/p99. Nếu thay throttle hoặc concurrency, cân nhắc cả độ dài backlog và khả năng phục vụ ứng dụng; không đẩy thật nhanh vào node đích chưa khỏe.

**Bước 5 — Lập kế hoạch repair hoặc rebuild.** So downtime với hint window và ngưỡng an toàn liên quan tombstone/`gc_grace_seconds`. Nếu có thể thiếu hint, chuẩn bị repair. Nếu node cực kỳ cũ hoặc mất dữ liệu, đánh giá rebuild/replace theo runbook.

**Bước 6 — Kiểm tra phục hồi.** Xác nhận backlog giảm về mức ổn định, replay errors không tăng, disk free đã an toàn, repair cần thiết hoàn tất, read/write latency trở lại bình thường và không còn sai lệch dữ liệu theo phạm vi kiểm tra.

**Không xử lý vội bằng cách:** xóa tệp hints thủ công, giảm `gc_grace_seconds`, ép node cũ phục vụ mà chưa xác minh, hoặc chỉ tăng write CL trong khi hy vọng dữ liệu lịch sử tự khôi phục.

## 12. Tình huống và câu hỏi tự kiểm tra

**Tình huống A.** RF=3, A và B còn sống, C down. Write ở `LOCAL_QUORUM` thành công. Có thể suy ra C đã nhận mutation không?

**Trả lời:** Không. Hai ACK đủ cho CL, còn C vẫn có thể thiếu. Hints chỉ có thể giúp phát lại khi đủ điều kiện.

**Tình huống B.** Replica down 5 giờ, hint window thực tế là 2 giờ. Sau hồi phục, tất cả file hint còn lại đều phát xong. Có bảo đảm replica đồng bộ hoàn toàn không?

**Trả lời:** Không. Mutation ngoài hint window có thể không có hint. Cần repair/đối soát.

**Tình huống C.** 1.000 hints mỗi giây, trung bình 2 KiB, sinh liên tục trong ba giờ. Dung lượng thô là bao nhiêu?

**Trả lời:** 10,8 triệu hints, khoảng **20,6 GiB** trước overhead. Cần đo dung lượng thực tại các node giữ hint.

**Tình huống D.** C đã UP nhưng hints directory vẫn tăng. Những nguyên nhân nào cần kiểm tra?

**Trả lời:** Replay bị throttle, node đích quá tải, network/disk chậm, delivery lỗi/retry, hoặc tốc độ phát sinh hints mới cao hơn tốc độ phát thành công.

**Tình huống E.** C down nhiều ngày, đã bỏ lỡ DELETE và tombstone có thể đã bị thu hồi ở replica khác. Chỉ replay hints còn lại có đủ không?

**Trả lời:** Không. Có rủi ro zombie data; phải đánh giá độ cũ dữ liệu và quy trình repair/rebuild/replace an toàn.

**Tình huống F.** RF=3, C down, CL=`ALL`. Coordinator ghi hint cho C. Lệnh có đáp ứng `ALL` không?

**Trả lời:** Không. Hint không đóng vai trò ACK của replica C.

## 13. Ghi nhớ

Hinted handoff là **cơ chế hỗ trợ phục hồi gần thời điểm sự cố**, không phải bảo đảm mạnh rằng mọi replica đã có dữ liệu mới nhất.

- **Hint backlog** tăng theo mutation đủ điều kiện trong downtime; chỉ giảm khi replay thành công hoặc hint bị loại theo cơ chế quản lý.
- **Dung lượng hints** phải được đo ở từng node và filesystem cụ thể, cùng với lưu lượng ghi và các tác vụ cạnh tranh I/O.
- **Write consistency** xác định điều kiện ACK; hint không thay ACK và không chứng minh replica đích đã cập nhật.
- **Down lâu hơn hint window** có thể tạo khoảng thiếu dữ liệu không có hint, cần repair.
- **Down quá lâu so với an toàn tombstone/repair** có thể dẫn đến zombie data, đòi hỏi quy trình rebuild/replace phù hợp.
- **Java client** phải thiết kế consistency, retry và idempotency rõ ràng, còn tình trạng hints cần theo dõi bằng metrics, logs và công cụ vận hành Cassandra.

Khi xử lý sự cố thực tế, hãy kết hợp **timeline outage, tốc độ tạo/phát hint, bytes backlog, disk headroom, repair và an toàn tombstone**. Một node hiện `UP` là điểm bắt đầu phục hồi; tính đầy đủ của dữ liệu cần được xác minh riêng.
