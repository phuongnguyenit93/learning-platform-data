# Đọc, ghi lại dữ liệu và nhu cầu dung lượng tạm khi compaction trong Apache Cassandra

## 1. Đặt vấn đề: compaction không phải thao tác “nén tại chỗ”

Trong Apache Cassandra, cơ sở dữ liệu phân tán **wide-column**, các bảng được thiết kế theo truy vấn và dữ liệu được phân phối đến replica dựa trên **partition key**. Mỗi replica ghi mutation vào commit log và memtable, rồi flush memtable thành các **SSTable bất biến** trên đĩa. Một partition có thể xuất hiện trong nhiều SSTable, kèm phiên bản cũ, bản ghi mới và tombstone từ xóa dữ liệu hoặc TTL.

Để giữ cho đường đọc không phải dò quá nhiều SSTable, Cassandra chạy **compaction**: đọc các SSTable được chọn, hòa giải các phiên bản và **ghi ra SSTable mới**. Đây là hoạt động tạo dữ liệu thay thế (*rewrite*), không sửa trực tiếp các SSTable cũ. Trong thời gian compaction chưa hoàn tất, **đầu vào vẫn tồn tại đồng thời với đầu ra đang được tạo**, nên đĩa cần có chỗ cho cả hai.

Ví dụ một node đang lưu 400 GiB dữ liệu; một lần compaction chọn 100 GiB SSTable cũ và dự kiến viết 85 GiB SSTable mới. Không thể kết luận node chỉ cần 315 GiB sau compaction rồi cho chạy ngay khi ổ đĩa gần đầy. **Trong lúc ghi đầu ra, dung lượng đang sử dụng có thể tạm tăng thêm xấp xỉ 85 GiB**, chưa kể flush, compaction khác, streaming, snapshot hay dữ liệu đang ghi mới.

Bài này thuộc chương **SSTable và compaction** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Trọng tâm là ba câu hỏi vận hành: compaction phải **đọc gì**, **ghi lại gì**, và **cần bao nhiêu dung lượng tạm** trước khi có thể thu hồi các SSTable cũ.

## 2. SSTable bất biến dẫn đến read–merge–write như thế nào?

### 2.1. Vì sao không sửa trực tiếp dữ liệu cũ?

Các mutation mới không tìm tới vị trí lưu cell cũ trong SSTable để ghi đè. Thay vào đó, chúng được lưu trong memtable và sau đó tạo SSTable mới. Khi một row bị cập nhật ba lần và một lần bị xóa, replica có thể chứa nhiều phiên bản của cùng khóa ở nhiều tệp.

Giả sử bảng sự kiện theo thiết bị có partition key `device_id`:

| Thời điểm | Hoạt động | Trạng thái lưu trữ có thể xuất hiện |
|---|---|---|
| T0 | Insert `value=25` | SSTable A chứa giá trị 25 |
| T1 | Update `value=26` | SSTable B chứa giá trị 26 |
| T2 | Delete row | SSTable C chứa tombstone |
| T3 | Insert một row khác cùng partition | SSTable D chứa row mới |

Read path phải xét các nguồn liên quan và hòa giải theo **timestamp của mutation**, tombstone, TTL và các quy tắc của Cassandra. Việc “đọc đúng partition key” giảm chi phí định tuyến nhưng không tự loại bỏ nhiều phiên bản trên đĩa.

### 2.2. Các bước logic của một lần compaction

1. **Chọn đầu vào:** compaction strategy quyết định một nhóm SSTable phù hợp; đó có thể là các tệp cùng kích cỡ, các level chồng lấn, hoặc các tệp trong cùng cửa sổ thời gian.
2. **Đọc:** Cassandra mở luồng đọc các SSTable đầu vào, truy cập metadata/index và các đoạn dữ liệu cần thiết. Dữ liệu đã nén cần được giải nén phù hợp để xử lý.
3. **Hợp nhất:** hệ thống đi qua các partition/row được sắp thứ tự, đối chiếu phiên bản của cùng cell, TTL và tombstone. Không phải mọi tombstone hoặc phiên bản cũ đều có thể bị loại bỏ ngay.
4. **Ghi lại:** tạo một hoặc nhiều SSTable đầu ra với data file, index, thông tin kiểm tra, Bloom filter và metadata tương ứng; chi tiết các component thay đổi theo định dạng SSTable/phiên bản.
5. **Hoàn tất và thay thế:** đầu ra chỉ được dùng chính thức sau khi quá trình hoàn thành hợp lệ. Các SSTable đầu vào được đánh dấu loại khỏi tập đang hoạt động và chỉ thu hồi tệp vật lý khi không còn thành phần nào cần giữ chúng.

~~~mermaid
flowchart TD
    A["SSTable A: giá trị cũ"] --> D["Compaction đọc và merge"]
    B["SSTable B: giá trị mới"] --> D
    C["SSTable C: tombstone / TTL"] --> D
    D --> E["Hòa giải timestamp, phiên bản và dấu xóa"]
    E --> F["Ghi SSTable đầu ra mới"]
    F --> G["Hoàn tất, thay thế SSTable đầu vào"]
    G --> H["Thu hồi tệp cũ khi an toàn"]
    I["Mutation mới vẫn được flush trong lúc compaction"] --> J["Các SSTable phát sinh song song"]
~~~

**Ý nghĩa thực tế:** ở giai đoạn ghi đầu ra, ổ đĩa có thể đồng thời giữ **A + B + C + đầu ra**. Tốc độ ghi vào cluster không nhất thiết dừng, nên những SSTable mới do flush còn có thể làm dung lượng tăng thêm.

### 2.3. Kết quả có nhất thiết nhỏ hơn đầu vào?

Không. Đầu ra thường nhỏ hơn nếu hợp nhất nhiều phiên bản trùng hoặc xóa được dữ liệu đã đủ điều kiện, nhưng **không nên coi tỷ lệ nén/giảm dung lượng là bảo đảm**. Khi phần lớn dữ liệu còn sống, kích thước đầu ra có thể gần tổng đầu vào. Kích thước có thể thay đổi theo mức nén, định dạng, metadata và điều kiện xử lý cụ thể.

Vì thế **không dự trù dung lượng dựa trên suy đoán “compaction sẽ tiết kiệm 30%”** nếu chưa có lịch sử số liệu đáng tin cậy cho bảng và loại compaction đó.

## 3. Vì sao compaction vừa tiêu thụ I/O đọc vừa tiêu thụ I/O ghi?

Compaction là công việc nền của storage engine, nhưng cạnh tranh tài nguyên với traffic đọc/ghi của ứng dụng.

| Loại chi phí | Nguồn phát sinh | Điều có thể thấy ở production |
|---|---|---|
| **Read I/O** | Đọc các SSTable nguồn để merge | Tăng băng thông đọc đĩa, độ trễ truy vấn |
| **Write I/O** | Tạo SSTable mới và các component liên quan | Tăng băng thông ghi đĩa, giảm headroom |
| **CPU** | Giải nén, merge, xử lý tombstone, nén lại | CPU tăng, throughput compaction giới hạn |
| **Không gian đĩa tạm** | Giữ SSTable cũ trong lúc ghi SSTable mới | Free space giảm trước khi tăng trở lại |
| **Tài nguyên bộ nhớ/handle** | Buffer, metadata và iterator | Tăng áp lực tài nguyên khi nhiều tác vụ chạy cùng lúc |
| **Write amplification** | Dữ liệu sống có thể được ghi lại qua nhiều vòng compaction | Tổng bytes ghi vào ổ lớn hơn bytes ứng dụng thực ghi |
| **Read amplification nếu chưa compact** | Query phải đọc nhiều SSTable/phiên bản/tombstone | Read latency và SSTables per read tăng |

**Trade-off trung tâm:** compaction ghi lại dữ liệu để đổi lấy chi phí đọc thấp hơn về sau và để thu hồi phiên bản/tombstone đủ điều kiện. Chạy compaction mạnh hơn có thể cải thiện read latency và giảm số SSTable, nhưng cũng tranh I/O với luồng ghi/đọc đang phục vụ. Chạy quá chậm có thể khiến số SSTable và backlog tích lũy.

### Minh họa read và write amplification

Một ứng dụng ghi mới 1 GiB dữ liệu logic. Dữ liệu đó được flush, rồi lần lượt có thể tham gia nhiều lần compaction trong vòng đời. Tổng bytes ổ đĩa phải ghi cho SSTable có thể vượt 1 GiB đáng kể; mức tăng phụ thuộc chiến lược, patterns cập nhật, replication và cấu hình lưu trữ.

Ngược lại, một truy vấn trả 10 row có thể phải đọc nhiều SSTable khi cùng partition phân tán trên nhiều tệp. **Giảm read amplification bằng compaction thường đánh đổi bằng tăng write amplification.** Không thể tối ưu cả hai độc lập hoàn toàn.

## 4. Dung lượng tạm là gì và xuất hiện lúc nào?

### 4.1. “Đầu vào cũ” và “đầu ra mới” cùng tồn tại

Giả sử một compaction chọn 4 SSTable, mỗi SSTable 20 GiB:

~~~text
Trước compaction:
SSTable A 20 GiB
SSTable B 20 GiB
SSTable C 20 GiB
SSTable D 20 GiB
-----------------
Tổng đầu vào = 80 GiB

Trong lúc compaction:
SSTable cũ vẫn giữ: 80 GiB
SSTable đầu ra mới: tăng dần tới khoảng 72 GiB
------------------------------------------------
Dung lượng có thể cùng tồn tại: khoảng 152 GiB

Sau khi hoàn tất và thu hồi đầu vào:
Chỉ giữ đầu ra: khoảng 72 GiB
~~~

Đầu ra giả định là 72 GiB để minh họa. Đây **không phải tỷ lệ giảm dung lượng mặc định**. Nếu các tệp cũ bị giữ bởi snapshot, backup hoặc còn reader cần tới, dung lượng thực tế được thu hồi có thể đến muộn hơn kỳ vọng.

### 4.2. Công thức lập ngân sách dung lượng

Để đánh giá một node ở thời điểm compaction, sử dụng mô hình gần đúng:

~~~text
Free cần dự phòng
≈ Tổng đầu ra mới chưa được giải phóng
  + Tăng trưởng do ghi / flush
  + Streaming, repair hoặc công việc nền khác
  + Biên an toàn
~~~

Ở đây:

- **Output mới:** ước lượng dung lượng SSTable compaction tạo thêm **trước khi đầu vào cũ bị xóa**. Nếu nhiều job chạy đồng thời, phải xét tổng đầu ra còn cùng tồn tại.
- **Tăng trưởng do ghi/flush:** write traffic không biến mất trong khoảng thời gian compaction đang chạy.
- **Tác vụ khác:** streaming, repair, rebuild, bootstrap, snapshot/backup và tệp tạm khác có thể tăng nhu cầu đĩa. Cần phân biệt phần thực sự tăng mới với phần đã tính trong dung lượng đang dùng.
- **Biên an toàn:** dành chỗ cho sai số ước tính, biến động traffic và tình huống compaction chạy lâu hơn dự kiến.

Đây là **mô hình lập kế hoạch**, không phải thuật toán dự đoán chính xác và không là quy tắc “luôn cần 2 lần dữ liệu”. Những SSTable đầu vào có thể được thu hồi ở các thời điểm khác nhau, nhiều tác vụ có thể được giới hạn bởi cấu hình và không phải toàn bộ data directory tham gia cùng một compaction.

**Đo free space trên từng ổ/data directory, không chỉ tổng dung lượng của cluster.** Một node hoặc một ổ trong node đầy vẫn có thể khiến tác vụ thất bại dù các node khác còn rất nhiều đĩa.

### 4.3. Ví dụ tính dung lượng đỉnh

Giả sử một node có ổ dữ liệu 1.000 GiB và đã dùng 760 GiB. Free space hiện tại = 240 GiB.

| Thành phần cần dự trù | Ước lượng |
|---|---:|
| Compaction đang chuẩn bị ghi đầu ra mới | 145 GiB |
| Một tác vụ compaction khác cùng lúc | 20 GiB |
| Ghi mới và flush trong thời gian thực hiện | 30 GiB |
| Biên an toàn mong muốn | 50 GiB |
| **Tổng cần để giữ biên an toàn** | **245 GiB** |
| **Free hiện có** | **240 GiB** |
| **Thiếu so với dự trù** | **5 GiB** |

Nếu chỉ tính lượng có thể tăng thêm trước biên an toàn, mức sử dụng dự đoán là `760 + 145 + 20 + 30 = 955 GiB`, còn `45 GiB` free. Con số này chưa đầy ổ, nhưng đã thấp hơn mức dự phòng 50 GiB đã chọn. Không nên cho rằng “còn 240 GiB free là đủ” mà chưa tính đồng thời nhiều hoạt động.

Trong thực tế phải cập nhật số liệu từ kích thước input, lịch sử output, tốc độ ghi, tốc độ compaction, concurrency và số đo đĩa. Các thông số trong bảng chỉ dùng để **luyện tư duy capacity planning**, không phải ngưỡng vận hành Cassandra khuyến nghị.

## 5. Mối quan hệ với từng chiến lược compaction

Chiến lược compaction quyết định **SSTable nào được chọn và mức độ thường xuyên phải ghi lại dữ liệu**. Vì vậy nó ảnh hưởng đồng thời đến read amplification, write amplification và dung lượng tạm.

| Strategy | Cách chọn và ghi lại dữ liệu (khái quát) | Ý nghĩa về dung lượng tạm |
|---|---|---|
| **SizeTieredCompactionStrategy (STCS)** | Gộp các SSTable có kích cỡ tương tự, tạo tệp lớn hơn | Compaction của nhóm SSTable lớn có thể cần đầu ra đáng kể trong lúc giữ các đầu vào |
| **LeveledCompactionStrategy (LCS)** | Tổ chức SSTable thành các level để giảm chồng lấn khóa; dữ liệu có thể được ghi lại nhiều lần khi chuyển level | Nhiều lần rewrite và compaction với SSTable chồng lấn; cần đo output đồng thời theo level và I/O budget |
| **TimeWindowCompactionStrategy (TWCS)** | Gom SSTable theo cửa sổ thời gian; tập dữ liệu cũ có TTL đồng đều có thể hết hạn theo nhóm | Cửa sổ đang hoạt động vẫn cần rewrite; cửa sổ đã hết hạn toàn bộ có thể giúp thu hồi mà không phải merge lại toàn bộ |
 
Đây là các chiến lược phổ biến để so sánh. Tập strategy và chi tiết thực thi thay đổi theo **phiên bản Cassandra**. Đừng suy ra headroom từ tên strategy; phải dùng metrics của workload cụ thể.

### 5.1. STCS: chú ý compaction ở tier lớn

STCS thường gom một số tệp tương đương kích cỡ. Ví dụ bốn SSTable 50 GiB thành một output xấp xỉ 200 GiB nếu không loại bỏ được nhiều dữ liệu. Tình huống này có thể cần gần 200 GiB chỗ trống để ghi đầu ra **trước khi** đầu vào được thu hồi.

Đó là lý do capacity planning dựa vào mức free trung bình trong ngày có thể bỏ lỡ đỉnh nhu cầu khi một nhóm SSTable lớn vừa đủ điều kiện compaction. STCS phù hợp nhiều workload thiên ghi, nhưng số SSTable chồng lấn và nhu cầu chỗ trống cho merge lớn có thể ảnh hưởng đáng kể tới workload đọc nhạy latency.

### 5.2. LCS: giảm chồng lấn đọc, đổi lại nhiều lần rewrite

LCS giới hạn mức chồng lấn key range của SSTable trong các level đã tổ chức (đặc biệt cần phân biệt level 0). Nó thường giúp đọc point query kiểm tra ít SSTable hơn. Để giữ cấu trúc level, một đoạn dữ liệu có thể phải được **đọc và ghi lại nhiều lần** khi dữ liệu được đẩy qua các level.

Chi phí **write amplification** và I/O tổng thể có thể cao hơn STCS, ngay cả khi mỗi compaction đơn lẻ chỉ xử lý một tập nhỏ hơn so với một merge tier lớn. Với LCS, hãy đánh giá số job đồng thời, kích thước output, backlog, disk throughput và dữ liệu đang tiếp tục được flush.

### 5.3. TWCS: dữ liệu hết hạn theo cửa sổ

TWCS thường hợp với time series được **ghi theo thời gian, ít cập nhật quá khứ và TTL gần đồng đều**. Khi một SSTable trở nên *fully expired* và các điều kiện an toàn được đáp ứng, Cassandra có thể thu hồi tệp mà không cần đọc–ghi lại mọi row còn sống.

Nhưng các tình huống sau làm giảm lợi ích:

- Ghi dữ liệu trễ vào timestamp cũ hoặc cập nhật lại các partition trước đó.
- Trộn dữ liệu có TTL rất khác nhau, hoặc có cả dữ liệu không TTL.
- Dữ liệu cùng partition phân tán nhiều cửa sổ và phát sinh xóa/ghi đè.
- Tốc độ ghi/flush khiến compaction hiện tại chậm hơn traffic mới.

TWCS không miễn phí: cửa sổ đang hoạt động vẫn cần compaction, lưu đầu ra mới và I/O. Không chọn strategy chỉ vì bảng có cột timestamp; hãy xem **mẫu ghi thực** và retention.

## 6. Tombstone và điều kiện thu hồi trong compaction

Tombstone là dấu xóa dữ liệu để các replica và các SSTable cũ không làm sống lại giá trị đã bị xóa. Khi compaction gặp tombstone, nó **không mặc định loại bỏ ngay**.

Vì sao?

1. Một SSTable **ngoài tập input** có thể còn chứa dữ liệu cũ mà tombstone này đang che.
2. Một replica bị mất liên lạc có thể chưa nhận mutation xóa; loại bỏ dấu xóa quá sớm có thể dẫn tới **zombie data** sau khi replica trở lại.
3. Dữ liệu TTL hết hạn cũng phải chịu logic an toàn của việc thu hồi trên đĩa; hết hạn không có nghĩa tệp biến mất ngay.

`gc_grace_seconds` liên quan đến cửa sổ bảo vệ trước rủi ro hồi sinh dữ liệu, nhưng **đủ tuổi grace không phải điều kiện duy nhất trong mọi trường hợp**. Cassandra còn phải xét dữ liệu chồng lấn, dấu xóa và các điều kiện bảo vệ theo strategy/phiên bản. **Repair** hỗ trợ đồng bộ replica; **compaction** xử lý các SSTable trên từng replica. Hai công việc này liên quan nhưng không thay thế nhau.

Ví dụ:

~~~cql
-- Giả sử keyspace demo đã được tạo.
CREATE TABLE demo.measurements_by_device (
    device_id uuid,
    measured_at timestamp,
    temperature double,
    PRIMARY KEY (device_id, measured_at)
) WITH default_time_to_live = 604800
  AND compaction = {
      'class': 'TimeWindowCompactionStrategy',
      'compaction_window_unit': 'DAYS',
      'compaction_window_size': '1'
  };
~~~

Ví dụ này giả định dữ liệu time series lưu 7 ngày và chủ yếu ghi theo thứ tự thời gian. Nó chỉ minh họa cấu hình; chọn `gc_grace_seconds`, lịch repair và retention phải theo topology, replica outage window và nhu cầu nghiệp vụ thực tế.

**Không tự giảm `gc_grace_seconds` về 0 để dọn đĩa khi thiếu chỗ**. Quyết định như vậy cần phân tích bảo đảm về repair, replication và rủi ro data resurrection.

## 7. Những yếu tố khiến dung lượng không được giải phóng như mong đợi

### 7.1. Snapshot và backup vẫn giữ SSTable cũ

Cassandra snapshot thường dựa trên hard link đến SSTable tại thời điểm snapshot. Khi compaction tạo SSTable thay thế, file cũ có thể không còn thuộc bảng đang hoạt động nhưng **dung lượng vật lý vẫn bị snapshot giữ** cho tới khi snapshot được dọn theo chính sách.

Tương tự, các cơ chế backup/retention có thể tiếp tục giữ bản sao hoặc hard link tùy thiết lập. **Dung lượng sử dụng trên filesystem có thể không giảm** tương ứng với “bytes compacted” mà công cụ báo cáo.

### 7.2. Reader và các thành phần đang dùng tệp cũ

Một query đang sử dụng SSTable cũ hoặc một thành phần lưu trữ cần tham chiếu tới chúng có thể trì hoãn việc thu hồi vật lý. Vì vậy, mốc “compaction task đã hoàn thành” và “free space đã tăng hết” không nhất thiết xảy ra trong cùng một thời điểm.

### 7.3. Flush, streaming, repair và bootstrap diễn ra song song

Traffic mới tiếp tục tạo memtable và SSTable. Streaming, bootstrap, rebuild hoặc repair có thể truyền/ghi thêm dữ liệu; cần lập ngân sách **theo node và data directory** cho các tác vụ thực sự dự kiến chạy cùng lúc. Đừng lấy tổng replication factor của cluster rồi chia đều thành một “ổ trống chung”: compaction chạy cục bộ, mỗi replica phải có headroom riêng.

### 7.4. Dung lượng báo cáo khác nhau ở các lớp

- **Logical live data:** dữ liệu còn hiệu lực được ứng dụng quan tâm.
- **SSTable live bytes:** dữ liệu trong các SSTable đang hoạt động, có thể còn phiên bản/tombstone.
- **Total storage used:** các tệp hiện hữu, snapshot/backup, commit log và những thành phần khác trên đĩa.
- **Filesystem free bytes:** chỗ thật sự còn có thể ghi trên data directory liên quan.

Các chỉ số này **không tương đương**. Trong sự cố thiếu đĩa, hãy bắt đầu bằng filesystem free space rồi đối chiếu với thống kê SSTable và các nguồn giữ dung lượng.

## 8. Cách quan sát và ước lượng trên cluster thực tế

Với quyền vận hành ở môi trường phù hợp, có thể bắt đầu từ các lệnh sau. Cú pháp và các trường kết quả cụ thể có thể thay đổi theo phiên bản.

~~~bash
# Công việc compaction đang chạy, tiến độ và pending tasks.
nodetool compactionstats

# Thống kê một bảng: số SSTable, không gian lưu trữ,
# read/write latency và thông tin partition/tombstone nếu phiên bản hỗ trợ.
nodetool tablestats demo.measurements_by_device

# Lịch sử compaction hoàn thành (phụ thuộc phiên bản/cấu hình).
nodetool compactionhistory

# Snapshot đang tồn tại có thể giữ dung lượng của SSTable cũ.
nodetool listsnapshots

# Quan sát sức khỏe node, load chỉ dùng để đối chiếu.
nodetool status
~~~

Cú pháp `tablestats` nhận keyspace/table có thể khác giữa các phiên bản; nếu lệnh trên không được hỗ trợ, xem trợ giúp `nodetool help tablestats` của bản Cassandra đang vận hành. Để đo dung lượng trống thật sự, sử dụng công cụ của hệ điều hành trên **data filesystem** tương ứng, chẳng hạn `df -h` trên Linux. Không suy ra free space chỉ từ cột `Load` của `nodetool status`.

### Chỉ số cần ghép khi điều tra

| Nhóm quan sát | Cần xem | Giải thích |
|---|---|---|
| Dung lượng đĩa | Free bytes, used %, từng data directory | Xác định còn chỗ cho output mới không |
| Compaction | Task active, estimated remaining bytes, pending | Biết bao nhiêu job có thể cùng sinh output |
| SSTable | Count, size distribution, bytes live/total | Phát hiện nhiều tệp, nhóm merge lớn hoặc phân mảnh |
| Workload | Write throughput, flush rate, read latency p95/p99 | Tính tăng trưởng trong thời gian compaction và tác động đọc |
| Hạ tầng | Disk read/write throughput, latency, CPU | Kiểm tra nghẽn I/O và cạnh tranh tài nguyên |
| Giữ tệp | Snapshots, backup retention, long-running read | Giải thích vì sao xóa input xong vẫn không tăng free bytes |
| Replication | Repair/streaming, replica chậm/ngắt | Đánh giá an toàn tombstone và hoạt động đồng thời |

Chỉ đếm số SSTable **chưa đủ**. Một compaction của bốn tệp 100 GiB có thể cần nhiều dung lượng tạm hơn hàng trăm tệp vài MiB. Ngược lại, hàng trăm tệp nhỏ có thể làm read amplification tăng ngay cả khi tổng kích cỡ không lớn.

### Checklist trước một thay đổi vận hành lớn

1. **Xác nhận node/ổ và chiến lược compaction** của bảng bị ảnh hưởng.
2. **Ước lượng kích thước input và output**, lấy từ lịch sử compaction, bảng tương tự và phân bố phiên bản/tombstone; ghi rõ bất định.
3. **Tính nhiều tác vụ đồng thời**, cộng thêm tốc độ flush, streaming/repair nếu có và biên an toàn.
4. **Xem snapshot/backup và dung lượng thực trên filesystem**, nhất là khi đầu vào cũ không thể được giải phóng sớm.
5. **Xem I/O còn dư để compaction hoàn tất**, bởi compaction kéo dài nghĩa là phải giữ vùng dung lượng tạm lâu hơn.
6. **Theo dõi free bytes trong lúc chạy**, đối chiếu kích thước tệp đang sinh và pending backlog; thực hiện thao tác điều chỉnh theo runbook của cluster.

## 9. Ứng dụng Java và luồng ghi ảnh hưởng đến compaction ra sao?

Java driver không điều khiển trực tiếp compaction, nhưng **cách ứng dụng tạo mutation và partition** quyết định số phiên bản và mẫu SSTable về sau.

Ví dụ, một hệ thống telemetry ghi theo một partition không có giới hạn thời gian:

~~~cql
CREATE TABLE demo.telemetry_unbounded (
    device_id uuid,
    event_time timestamp,
    value double,
    PRIMARY KEY (device_id, event_time)
);
~~~

Khi một thiết bị gửi hàng triệu sự kiện qua nhiều tháng, partition có thể lớn dần và xuất hiện ở nhiều SSTable. Ghi thêm các correction tới thời điểm cũ còn gây chồng lấn dữ liệu trong compaction. Một cách tổ chức theo cửa sổ truy vấn có thể dùng bucket:

~~~cql
CREATE TABLE demo.telemetry_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    value double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Java client ghi đủ partition key và clustering key qua prepared statement:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

// CqlSession session được khởi tạo và quản lý trong vòng đời ứng dụng.
PreparedStatement insert = session.prepare(
    "INSERT INTO demo.telemetry_by_device_day " +
    "(device_id, event_day, event_time, value) VALUES (?, ?, ?, ?)"
);

UUID deviceId = UUID.fromString("11111111-1111-1111-1111-111111111111");
Instant eventTime = Instant.parse("2026-11-21T10:00:00Z");
LocalDate bucket = LocalDate.of(2026, 11, 21);

session.execute(insert.bind(deviceId, bucket, eventTime, 26.5));
~~~

Mô hình bucket giúp giới hạn kích thước partition và thu hẹp phạm vi truy vấn, nhưng **không tự bảo đảm compaction rẻ**. Cần cân nhắc kích thước bucket với tốc độ ghi, TTL, thời gian giữ và truy vấn xuyên ngày.

Các thói quen phía ứng dụng giúp hạn chế I/O nền không cần thiết:

- Tránh **update lặp lại cùng row** khi business có thể ghi sự kiện bất biến; mỗi update có thể tạo phiên bản mới chờ hòa giải.
- Tránh **DELETE hàng loạt liên tục** khi một mô hình retention bằng bucket/TTL phù hợp hơn; TTL cũng sinh dấu hết hạn nên phải đo.
- Tránh lạm dụng **large batch** trên nhiều partition: batch không làm compaction miễn phí và có thể tạo áp lực ghi.
- Áp dụng **bounded concurrency/backpressure** cho backfill, import và phục hồi dữ liệu để không tạo đợt flush/compaction vượt sức đĩa.
- Ghi nhận **p95/p99 read/write latency**, request timeout và tốc độ ingest khi điều chỉnh chiến lược compaction.

Các quyết định này liên quan trực tiếp đến cấu trúc wide-column, partition key và thiết kế bảng theo truy vấn của Cassandra. Chúng cũng cho thấy vì sao xử lý compaction phải phối hợp cả **data model, CQL, Java ingestion và vận hành replica**.

## 10. Tình huống thực tế: compaction gần làm đầy một node

Giả sử bảng time series có STCS, node báo:

- Ổ dữ liệu gần đầy, free space giảm từ 150 GiB xuống 65 GiB.
- `nodetool compactionstats` cho thấy compaction đang ghi SSTable mới rất lớn.
- SSTable đầu vào chưa biến mất; song song đó job backfill vẫn đang ghi dữ liệu.
- p99 read latency tăng do I/O bị cạnh tranh.

Quy trình phân tích:

**Bước 1: Xác định dữ liệu đĩa thực sự còn trống.** Đọc filesystem free bytes theo data directory và theo dõi tốc độ giảm. Không căn cứ duy nhất vào kích thước live SSTable hoặc suy đoán rằng compaction sắp xong sẽ lập tức giải phóng đủ chỗ.

**Bước 2: Phân rã mức tăng dung lượng.** Xác định task compaction nào đang sinh output, còn bao nhiêu dữ liệu dự kiến phải ghi, có task đồng thời nào khác, và tốc độ write/flush từ backfill. Kiểm tra snapshot/backup giữ các SSTable đã thay thế.

**Bước 3: Bảo vệ tính sẵn sàng.** Theo runbook, giảm hoặc tạm dừng luồng backfill/import chủ động nếu được phép, và cân nhắc điều chỉnh tốc độ/mức đồng thời compaction theo tình trạng cluster. Cần hiểu trade-off: **làm compaction chậm lại có thể kéo dài thời gian phải giữ cả input và output**.

**Bước 4: Lựa chọn dài hạn bằng workload.** Nếu nhóm STCS lớn thường xuyên cần dung lượng tạm vượt headroom, xem lại strategy, data model, retention, capacity và phân bổ tải; đánh giá LCS/TWCS theo đặc tính thực, không tự chuyển ngay trong sự cố. Nâng capacity hoặc di chuyển tải có thể cần thiết.

**Bước 5: Xác minh phục hồi.** Theo dõi free bytes, pending compactions, số SSTable, I/O latency, read/write p99 và tốc độ ghi. Chỉ kết luận ổn định khi backlog không tiếp tục lớn lên và vẫn có biên an toàn cho đợt compaction tiếp theo.

**Tránh hành động hấp tấp:** không xóa file SSTable trực tiếp khỏi data directory, không tự giảm `gc_grace_seconds` để xóa tombstone, và không ép full compaction khi chưa kiểm tra headroom. Những thao tác này có thể làm mất dữ liệu hoặc khiến tình trạng thiếu đĩa nghiêm trọng hơn.

## 11. Phân biệt compaction, repair và cleanup

Ba hoạt động này dễ bị gom chung thành “dọn dữ liệu”, nhưng khác mục tiêu và chi phí:

| Hoạt động | Mục đích chính | Liên quan dung lượng |
|---|---|---|
| **Compaction** | Hợp nhất SSTable trên replica, giảm phiên bản trùng, tổ chức tệp, thu hồi dữ liệu đủ điều kiện | Đọc đầu vào và ghi SSTable mới, cần dung lượng tạm |
| **Repair** | Đồng bộ khác biệt dữ liệu giữa các replica, tránh thiếu mutation/xóa | Có thể phát sinh I/O, streaming và SSTable/compaction phụ thuộc phiên bản |
| **Cleanup** | Loại bỏ dữ liệu node không còn chịu trách nhiệm theo token range sau thay đổi topology | Cũng có thể phát sinh đọc–ghi dữ liệu và nhu cầu chỗ trống; phải thực hiện đúng quy trình |

Compaction **không tự xác nhận mọi replica đã đồng bộ**. Repair **không tự bảo đảm SSTable cũ được thu hồi tức thì**. Cleanup **không phải giải pháp chung cho bảng đang có nhiều tombstone**. Vì thế nên lập kế hoạch dung lượng cho các công việc này riêng biệt và xem chúng có thể đồng thời tranh I/O hay không.

## 12. Bài tập ứng dụng

### Bài 1 — Tính peak disk

Một node dùng 600 GiB trên tổng 800 GiB. Compaction đang chọn 120 GiB SSTable cũ và ước lượng output 100 GiB. Dự kiến có thêm 35 GiB data/flush và cần giữ biên an toàn 60 GiB. Chưa có job compaction nào khác. Có đủ free space để vẫn đạt biên an toàn không?

**Đáp án:** Free hiện tại là 200 GiB. Nhu cầu dự trù `100 + 35 + 60 = 195 GiB`, còn dư khoảng 5 GiB so với mức dự phòng mong muốn. **Về phép tính minh họa là vừa đủ**, nhưng biên sai số rất nhỏ; chưa nên dùng một ước lượng output đơn lẻ làm quyết định vận hành an toàn.

### Bài 2 — Hiểu nhầm về dung lượng sau compact

Sau compaction, SSTable live giảm 80 GiB nhưng `df` chỉ tăng 10 GiB. Nêu ít nhất hai giả thuyết.

**Đáp án:** Snapshot/backup giữ hard link tới SSTable cũ; reader hoặc thành phần lưu trữ chưa nhả file; những mutation mới/flush hay task khác đã làm dung lượng tăng đồng thời; số liệu “live SSTable” khác phạm vi filesystem.

### Bài 3 — Đánh đổi strategy

Workload A là point reads nhạy p99, thường xuyên update cùng khóa. Workload B là time series append-only, TTL gần đồng đều. Strategy nào đáng thử trước?

**Đáp án:** Với A, **LCS** thường đáng đánh giá vì hạn chế chồng lấn SSTable khi đọc, nhưng cần đo write amplification và I/O. Với B, **TWCS** thường phù hợp đặc tính cửa sổ thời gian và hết hạn, nếu không có nhiều ghi trễ/cập nhật cũ. Không chọn mà không benchmark.

### Bài 4 — Tombstone và repair

Một đội muốn đặt `gc_grace_seconds=0` vì compaction không loại bỏ tombstone ngay, trong khi có replica thỉnh thoảng offline nhiều ngày. Rủi ro là gì?

**Đáp án:** Tombstone có thể bị thu hồi trước khi replica cũ nhận delete, khiến dữ liệu bị xóa **xuất hiện trở lại** khi replica đồng bộ. Cần thiết kế repair và chính sách quản trị replica trước khi thay đổi grace.

### Bài 5 — Vì sao không chạy full compaction tùy tiện?

Một node đang thiếu đĩa; quản trị viên đề nghị `nodetool compact` với hy vọng mọi file cũ được xóa và giải phóng dung lượng. Điều gì cần đánh giá trước?

**Đáp án:** Full compaction có thể tạo đầu ra lớn trong khi đầu vào vẫn tồn tại, khiến nhu cầu free space tạm tăng mạnh. Cần kiểm tra kích thước đầu vào, ước lượng output, các task đồng thời, snapshot và I/O; không coi full compaction là giải pháp chữa đầy đĩa tức thì.

## 13. Ghi nhớ

Compaction là quy trình **đọc SSTable đầu vào → hợp nhất và hòa giải → ghi SSTable đầu ra → thay thế/thu hồi đầu vào khi an toàn**. Quy trình này giải thích ba thực tế quan trọng:

1. **Dữ liệu có thể được ghi lại nhiều lần**: write amplification là chi phí để cải thiện read path và tổ chức lưu trữ.
2. **Dung lượng tạm là điều kiện để compaction hoàn thành**: trong lúc ghi đầu ra, SSTable đầu vào vẫn có thể chiếm đĩa; traffic ghi, streaming, repair và snapshot có thể làm đỉnh dung lượng cao hơn.
3. **Không có một tỷ lệ headroom đúng cho mọi bảng**: STCS, LCS, TWCS, compaction concurrency, TTL, tombstone, dữ liệu chồng lấn và cấu trúc partition quyết định thực tế.

Khi lập kế hoạch vận hành Apache Cassandra, cần tính dung lượng **theo từng node và từng data directory**, đo output lớn nhất có thể đồng thời tồn tại, quan sát backlog/I/O, giữ biên an toàn và xác minh khả năng thu hồi file. Một compaction “giảm dung lượng về cuối” vẫn có thể **làm đầy đĩa trước khi kết thúc** nếu không dự trù giai đoạn ghi lại dữ liệu.
