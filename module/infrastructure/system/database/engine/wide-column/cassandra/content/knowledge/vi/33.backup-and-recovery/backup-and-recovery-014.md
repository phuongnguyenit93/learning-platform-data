# Diễn tập khôi phục, đo thời gian và cập nhật sổ tay

> **Chương:** Sao lưu và phục hồi  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Phạm vi:** Apache Cassandra, kiến trúc phân tán wide-column, partition key, thiết kế bảng theo truy vấn, replication, consistency level, CQL, compaction, repair, xử lý lỗi và ứng dụng Java.

## 1. Từ “có backup” đến “phục hồi được”

Một hệ thống Cassandra có thể tạo snapshot hằng ngày, sao chép tệp sang object storage và hiển thị trạng thái backup thành công nhưng vẫn **không khôi phục được dịch vụ** khi sự cố xảy ra. Ví dụ: thiếu snapshot của một số node, thiếu schema, không có quyền giải mã, SSTable không tương thích với cluster đích hoặc không ai biết phải trỏ ứng dụng Java về đâu sau khi nạp dữ liệu.

**Diễn tập khôi phục (recovery drill)** là việc thực hiện có kiểm soát toàn bộ hoặc một phần quy trình ứng phó sự cố trên môi trường thử nghiệm, đo thời gian từng bước, kiểm chứng dữ liệu và ghi lại các thay đổi cần thiết cho **sổ tay vận hành (runbook)**. Mục tiêu không phải chỉ làm cho lệnh restore chạy xong, mà là chứng minh hệ thống và ứng dụng thực sự có thể phục vụ lại theo mục tiêu đã đặt.

Một cuộc diễn tập đủ giá trị cần trả lời:

1. **Khôi phục từ đâu?** Bản backup nào, mốc dữ liệu nào, có đủ tất cả node/token range, schema, SSTable và khóa giải mã không?
2. **Khôi phục về đâu?** Cluster mới, node thay thế hay môi trường tách biệt; có tương thích với Cassandra, JDK và cấu hình đang vận hành không?
3. **Khôi phục được gì?** Dữ liệu của các partition, tính đúng đắn nghiệp vụ, TTL/tombstone, bảng liên quan và các thay đổi sau mốc backup.
4. **Mất bao lâu?** Từ lúc dịch vụ bị ảnh hưởng đến lúc người dùng có thể sử dụng lại, không chỉ thời gian tải tệp.
5. **Mất bao nhiêu dữ liệu?** Các ghi hợp lệ được xác nhận sau mốc phục hồi có còn hay phải xử lý bù không?
6. **Lần sau làm tốt hơn bằng cách nào?** Chỉnh thủ tục, tự động hóa, quyền truy cập, cảnh báo và kế hoạch diễn tập tiếp theo.

> **Nguyên tắc thực hành:** diễn tập trên cluster cô lập hoặc tài nguyên dành riêng cho thử nghiệm; không xóa bảng, ghi đè SSTable hay chuyển lưu lượng production chỉ để thử runbook.

## 2. Phân biệt mục tiêu RPO, RTO và dữ liệu quan sát

### 2.1. Hai chỉ số chính

| Chỉ số | Câu hỏi | Ý nghĩa |
|---|---|---|
| **RPO — Recovery Point Objective** | Chấp nhận mất dữ liệu tới mốc cũ bao xa? | Mức lùi thời gian dữ liệu tối đa có thể chấp nhận; phải dựa vào cutoff dữ liệu có thể khôi phục |
| **RTO — Recovery Time Objective** | Sau sự cố, bao lâu dịch vụ phải dùng được? | Thời gian tối đa từ **thời điểm bắt đầu gián đoạn được quy định** đến **thời điểm dịch vụ phục hồi đạt tiêu chí nghiệm thu** |

Đây là **mục tiêu**, không phải kết quả đo. Trong báo cáo phải có thêm:

- **RPO thực tế/ước lượng sau restore:** mốc ghi hợp lệ mới nhất được chứng minh là nằm trong trạng thái phục hồi, đối chiếu với thời điểm sự cố. Nếu snapshot toàn cluster không có một cutoff nhất quán, cần báo khoảng không chắc chắn thay vì một số chính xác giả tạo.
- **RTO thực đo:** thời điểm bắt đầu gián đoạn đến khi dữ liệu và đường truy cập của ứng dụng được nghiệm thu, tính cả phát hiện, ra quyết định, dựng hạ tầng, tải backup, restore, kiểm tra và chuyển lưu lượng.
- **Số thay đổi nghiệp vụ thiếu hoặc cần tái phát:** các đơn hàng/sự kiện đã được xác nhận nhưng không có trong dữ liệu được phục hồi. Chỉ tiêu thời gian không thay thế đối soát mất dữ liệu.

Công thức minh họa:

~~~text
RPO ước lượng theo cutoff = T_sự_cố - T_cutoff_khôi_phục

RTO thực đo = T_dịch_vụ_được_nghiệm_thu - T_bắt_đầu_gián_đoạn

Độ trễ tạo backup ≠ thời gian khôi phục dịch vụ
Thời gian upload xong ≠ mốc dữ liệu cuối cùng trong backup
~~~

Cần dùng **UTC** thống nhất cho timestamp sự kiện và đồng hồ hệ thống. Để đo thời lượng của từng bước, dùng timer/monotonic clock của hệ thống giám sát khi có thể; tránh sai lệch vì đồng hồ node không đồng bộ hoặc đổi múi giờ.

### 2.2. Tại sao phải ghi rõ điểm bắt đầu và điểm kết thúc?

Nếu chỉ tính từ lúc chạy lệnh tải backup đến lúc nạp xong SSTable, RTO đo được sẽ bỏ qua **phát hiện sự cố, xin quyền giải mã, cấp hạ tầng, xác minh nghiệp vụ và khôi phục ứng dụng**. Nên ghi các mốc:

- **T0 — ảnh hưởng bắt đầu:** theo synthetic incident hoặc một sự cố thật đã xác định.
- **T1 — phát hiện:** alert, dashboard hoặc người trực xác nhận.
- **T2 — quyết định phương án:** chọn backup/recovery point và mở runbook.
- **T3 — môi trường đích sẵn sàng:** node, mạng, thông tin phiên bản và khóa.
- **T4 — dữ liệu đã được chuyển đến đích:** bao gồm checksum/manifest.
- **T5 — cluster đọc được dữ liệu:** load/stream thành công, các node đạt trạng thái hợp lệ.
- **T6 — dữ liệu và ứng dụng được nghiệm thu:** truy vấn, invariant nghiệp vụ, latency, lỗi, consistency đạt ngưỡng.
- **T7 — đường truy cập phục vụ được mở:** điểm kết thúc RTO nếu tiêu chí nghiệm thu yêu cầu người dùng truy cập.

Đối với diễn tập không thực sự chuyển traffic, ghi rõ **T7 là mô phỏng**, đồng thời tách **RTO đã đo** và **thời gian chuyển traffic ước lượng**. Không công bố một RTO production đã được chứng minh nếu chưa diễn tập phần phụ thuộc đó.

## 3. Chọn kịch bản diễn tập theo miền lỗi

Cassandra có replication để chịu lỗi của replica, nhưng replication **không lưu lịch sử dữ liệu trước thao tác xóa hoặc ghi đè sai**. Snapshot giữ tham chiếu SSTable trên từng node và phải chuyển ra miền lỗi độc lập nếu muốn chống mất node/region. Một cuộc diễn tập nên mô tả **loại sự cố** trước khi chọn cách phục hồi.

| Kịch bản | Mục tiêu kiểm tra | Cơ chế chủ yếu | Kết quả chấp nhận |
|---|---|---|---|
| Một node bị mất, các replica khác khỏe | Node thay thế có nhận đủ token/data và cluster tiếp tục phục vụ? | Replace/bootstrap/streaming, replication | Node thay thế hoạt động; CL mục tiêu đạt; không cần khôi phục dữ liệu cũ |
| Xóa nhầm một tập dữ liệu | Có lấy lại được dữ liệu trước thao tác sai? | Snapshot/backup trước lỗi, restore chọn lọc | Có đủ bản ghi sạch, đối soát được thay đổi hợp lệ sau mốc |
| Mất toàn bộ cluster hoặc region | Có dựng cluster mới từ bản ngoài miền lỗi? | Backup độc lập + schema/config + restore | Ứng dụng truy cập được dữ liệu và đạt RPO/RTO mục tiêu |
| Replica lệch nhau sau lỗi | Có nhận diện và sửa khác biệt theo quy trình? | Repair và theo dõi consistency | Replica hội tụ theo khả năng của cơ chế Cassandra |
| Backup không đủ hoặc không giải mã được | Phát hiện lỗi từ trước và chuyển sang phương án tiếp theo? | Kiểm tra manifest, checksum, quyền và backup thay thế | Báo lỗi rõ, biết last known good recovery point, cập nhật runbook |

**Repair không thay thế restore từ backup.** Chạy repair sau một DELETE hợp lệ đã lan truyền không thể tự biết bản ghi đó cần được “undo”. Cũng không nên ép restore khi sự cố chỉ là một node hỏng và các replica còn lại đầy đủ dữ liệu mới nhất; hãy chọn cơ chế sát với loại mất mát.

### 3.1. Chọn mức độ thực tế của diễn tập

Có ba mức thường dùng:

1. **Tabletop:** đi qua quyết định, đầu mối liên lạc, quyền truy cập và lệnh dự kiến; hữu ích để phát hiện thiếu runbook nhưng **không chứng minh RTO thực tế**.
2. **Restore kỹ thuật trên cluster cô lập:** tải backup, dựng schema, load dữ liệu, đo từng giai đoạn và kiểm chứng CQL/Java; có thể chứng minh phần lớn bước phục hồi.
3. **End-to-end ở môi trường gần production:** bao gồm giả lập cảnh báo, cấp hạ tầng, khôi phục dữ liệu, đổi kết nối ứng dụng, kiểm tra độ trễ/error rate và rollback. Đây là cấp có khả năng so sánh tốt hơn với RTO nghiệp vụ.

Trong báo cáo phải ghi rõ mức đã diễn tập. Không dùng thời gian của một restore nhỏ vài MiB để khẳng định đạt RTO cho cluster hàng chục TiB.

## 4. Chuẩn bị và điều kiện an toàn

### 4.1. Danh mục đầu vào bắt buộc

Trước khi bắt đầu, đội diễn tập cần có:

- **Phạm vi:** keyspace, table, môi trường, token ranges, thời gian dữ liệu và dịch vụ Java liên quan.
- **Backup set:** ID/tag, danh sách node, snapshot/incremental SSTable/commitlog liên quan, manifest và checksum, trạng thái **COMPLETE** đã xác minh.
- **Schema và topology:** bản CQL của keyspace/table, UDT, partitioner, replication strategy, RF, DC/rack, Cassandra/JDK/SSTable format, cấu hình bảo mật.
- **Hạ tầng đích:** mạng, storage, dung lượng dự phòng cho nạp dữ liệu và compaction, số node, quyền đọc kho backup.
- **Khóa/secret:** tham chiếu tới KMS/secret manager và quyền giải mã đã được kiểm thử; không chép secret vào báo cáo.
- **Mốc dữ liệu:** cutoff được hỗ trợ bởi quy trình backup, watermark ứng dụng nếu có, danh sách thao tác nghiệp vụ để đối soát.
- **Tiêu chí nghiệm thu:** bảng/partition cần có, số lượng bản ghi mẫu, invariant nghiệp vụ, mức CL đọc/ghi, latency/error threshold.
- **Điểm dừng và rollback:** ai được quyền dừng, khi nào cô lập cluster, phương án chuyển traffic ngược nếu cấu hình ứng dụng bị ảnh hưởng.

Snapshot Cassandra thường giữ hard link tới SSTable trên **từng node**; chỉ tạo snapshot trên một node **không mặc nhiên bao phủ toàn cluster**. Một backup có thể dùng dữ liệu từ một tập replica/token range đã chứng minh đủ, nhưng quy trình đơn giản và dễ kiểm chứng thường điều phối chụp đủ các node thuộc phạm vi cần backup. Snapshot phân tán **không tự mang tính atomic toàn cluster** trong lúc ghi vẫn chạy.

### 4.2. Ranh giới bảo vệ production

- Dùng **cluster restore riêng**, DNS/service account và địa chỉ kết nối khác với production.
- Hạn chế đường mạng từ môi trường diễn tập để job thử nghiệm không gửi ghi sang production.
- Nếu backup chứa dữ liệu nhạy cảm, yêu cầu quyền truy cập đúng mục đích, mã hóa và chính sách masking/retention phù hợp.
- Đặt giới hạn chi phí và thời gian hạ tầng thử nghiệm, nhưng không cắt giảm tài nguyên đến mức làm kết quả thời gian không còn đại diện.
- Với diễn tập **mất region**, xác minh quyền đọc backup và giải mã không phụ thuộc tài nguyên giả định đã bị mất.
- Không xóa snapshot, cluster, bucket hoặc dữ liệu production như một bước mô phỏng; mô phỏng sự cố bằng cô lập, chặn truy cập hoặc môi trường riêng khi có thể.

## 5. Bộ dữ liệu kiểm chứng: gắn với partition key và CQL

Một bộ dữ liệu mẫu nhỏ giúp kiểm tra cả quá trình phục hồi lẫn tính đúng đắn khi dùng Cassandra. Giả sử ứng dụng Java lưu các sự kiện đơn hàng theo khách hàng/ngày. Ta tạo **trên môi trường diễn tập**:

~~~sql
-- Tên dc1 và RF = 3 chỉ dùng được khi môi trường có đủ replica
-- và topology phù hợp. Điều chỉnh khi dựng cluster thử nghiệm.
CREATE KEYSPACE IF NOT EXISTS restore_drill
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS restore_drill.events_by_customer_day (
    customer_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    order_id uuid,
    event_type text,
    amount decimal,
    PRIMARY KEY ((customer_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

Partition key là **(customer_id, event_day)**. Vì Cassandra định tuyến theo token của partition key, việc kiểm chứng phải bao phủ **nhiều partition nằm ở các token range khác nhau**, tránh chỉ đọc một customer rồi kết luận tất cả dữ liệu đã được khôi phục.

Dữ liệu gốc mẫu:

~~~sql
INSERT INTO restore_drill.events_by_customer_day
    (customer_id, event_day, occurred_at, event_id, order_id,
     event_type, amount)
VALUES
    (11111111-1111-4111-8111-111111111111, '2026-11-21',
     '2026-11-21T08:10:00Z',
     22222222-2222-4222-8222-222222222222,
     33333333-3333-4333-8333-333333333333,
     'ORDER_CREATED', 120.50);

INSERT INTO restore_drill.events_by_customer_day
    (customer_id, event_day, occurred_at, event_id, order_id,
     event_type, amount)
VALUES
    (44444444-4444-4444-8444-444444444444, '2026-11-21',
     '2026-11-21T08:20:00Z',
     55555555-5555-4555-8555-555555555555,
     66666666-6666-4666-8666-666666666666,
     'ORDER_PAID', 275.00);
~~~

Ở môi trường thật, tạo thêm nhiều customer/event ID đa dạng và lưu **bảng đối chiếu** gồm (partition key, clustering key, event_type, amount, thời gian ghi đã xác nhận). Dùng ứng dụng kiểm tra **watermark hoặc chuỗi ID nghiệp vụ** để phát hiện các sự kiện mới hơn mốc backup bị thiếu. Một row còn đọc được chưa chứng minh một bảng nhiều partition đã khôi phục đầy đủ.

Kiểm chứng bằng CQL sau restore:

~~~sql
SELECT occurred_at, event_id, order_id, event_type, amount
FROM restore_drill.events_by_customer_day
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 100;
~~~

Không nên dùng **SELECT COUNT(*) trên toàn bộ bảng dữ liệu production** làm kiểm chứng mặc định: truy vấn có thể rất tốn tài nguyên và tổng số hàng bằng nhau vẫn có thể che các hàng bị mất hoặc ghi sai. Với bộ fixture nhỏ có thể đối chiếu số lượng, nhưng quan trọng hơn là **đúng từng khóa và giá trị**.

### 5.1. Bổ sung ca kiểm thử khó

Bộ dữ liệu diễn tập nên có ít nhất:

- Một partition nhỏ và một partition nhiều row, trải nhiều token range.
- Một row đã **UPDATE** trước cutoff, để chứng minh phiên bản giá trị phù hợp.
- Một row đã **DELETE** hợp lệ trước cutoff, để bảo đảm restore không hồi sinh dữ liệu cũ trái ý định.
- TTL có chủ đích, kiểm tra giá trị đã hết hạn không được coi là còn tồn tại.
- Dữ liệu có UDT, collection hoặc TTL/tombstone nếu đó là cấu trúc production đang dùng.
- Một số ghi hợp lệ **sau** cutoff để đo phần dữ liệu cần hòa giải hoặc chấp nhận mất.

Cassandra dùng timestamp/tombstone/TTL để giải quyết dữ liệu, vì vậy **trộn SSTable từ thời điểm khác nhau vào cluster có ghi mới** có thể tạo hiệu ứng bất ngờ. Khôi phục trước vào môi trường cô lập và kiểm tra ngữ nghĩa xóa/hết hạn là bước bắt buộc.

## 6. Quy trình diễn tập khôi phục end-to-end

### 6.1. Chuỗi công việc và điểm kiểm tra

~~~mermaid
flowchart TD
    A["Kích hoạt kịch bản và ghi T0"] --> B["Xác định backup/cutoff, chốt tiêu chí"]
    B --> C["Dựng cluster phục hồi cô lập"]
    C --> D["Tải backup, manifest, schema, khóa"]
    D --> E{"Checksum và phạm vi dữ liệu đầy đủ?"}
    E -->|Không| X["Dừng hoặc chọn backup thay thế; ghi blocker"]
    E -->|Có| F["Dựng schema và nạp SSTable theo runbook phiên bản"]
    F --> G{"Node, schema, token và dữ liệu hợp lệ?"}
    G -->|Không| X
    G -->|Có| H["Chạy kiểm thử CQL, Java và invariant nghiệp vụ"]
    H --> I{"Đạt tiêu chí nghiệm thu?"}
    I -->|Không| X
    I -->|Có| J["Diễn tập kết nối ứng dụng và chuyển traffic giả lập"]
    J --> K["Ghi T7, tính RPO/RTO, cập nhật runbook"]
~~~

### 6.2. Các bước vận hành có thể thực hiện

**Bước 0 — Xác nhận đề bài.** Đặt mã cuộc diễn tập, người điều phối, người vận hành Cassandra, chủ ứng dụng Java và người nghiệm thu. Ghi loại sự cố: **mất toàn bộ cluster**, **xóa logic** hay **mất node**. Chốt thời điểm T0 và mục tiêu RPO/RTO trước khi chạy; nếu chưa chốt, không thể đánh giá pass/fail công bằng.

**Bước 1 — Chọn điểm khôi phục.** Lấy backup set đã đánh dấu COMPLETE và thời gian dữ liệu thực của nó. Kiểm tra mốc snapshot theo node, thời điểm application barrier nếu có, trạng thái upload, checksum, schema và khóa. Không dùng thời gian “upload xong” làm recovery point.

**Bước 2 — Dựng môi trường đích.** Cấp Cassandra/JDK tương thích, replication strategy, partitioner và dung lượng storage đủ lớn. Mỗi node phải dùng đúng DC/rack; kiểm tra network giữa node và client, quyền download, chứng chỉ TLS/cấu hình xác thực. Không nạp system keyspace của cluster cũ vào cluster mới theo cách không có trong runbook đã được chứng minh.

**Bước 3 — Phục hồi dữ liệu.** Chọn một phương án phù hợp phiên bản: restore SSTable vào node/cluster được chuẩn bị theo quy trình tương thích, hoặc tạo schema trên cluster mới rồi **stream SSTable bằng công cụ như sstableloader** khi phù hợp. Chỉ chạy lệnh thực tế sau khi đối chiếu tài liệu của **phiên bản Cassandra đang sử dụng**, cấu trúc thư mục/table ID và danh sách SSTable cần thiết. Với cùng một backup set, phải giữ bảng manifest các tệp đã nạp để tránh thiếu/trùng.

**Bước 4 — Khôi phục và kiểm tra tính nhất quán.** Chờ cluster đạt trạng thái vận hành được, kiểm tra node/token ownership, xác nhận đủ replica theo RF và áp dụng CL mục tiêu cho truy vấn kiểm tra. **Repair** có thể cần ở giai đoạn phù hợp của quy trình để khắc phục khác biệt replica, nhưng không phải bước tự động chữa dữ liệu bị xóa sai; không chạy repair mù trước khi biết dữ liệu cần khôi phục là gì.

**Bước 5 — Kiểm chứng dữ liệu.** Đối chiếu event_id/order_id và các trường, dữ liệu trước/sau cutoff, row bị DELETE/TTL, metadata/schema, đa token range. Nếu có các bảng được denormalize theo truy vấn, kiểm tra invariant giữa các bảng ở tầng nghiệp vụ; Cassandra không tự bảo đảm các bảng truy vấn khác nhau có cùng nội dung nghiệp vụ sau backup không đồng bộ.

**Bước 6 — Kiểm chứng ứng dụng Java.** Trỏ **chỉ bản ứng dụng thử nghiệm** đến cluster restore; kiểm tra authentication, TLS, prepared statement, đọc theo partition key, các thao tác ghi thử mới, paged queries và consistency level. Theo dõi timeout, tỷ lệ lỗi, throughput và latency. Kiểm tra quy trình đổi connection points/DNS có thực sự dùng cấu hình mới hay không.

**Bước 7 — Kết thúc và làm sạch.** Ghi lại mốc nghiệm thu, log và các sự cố gặp phải; đối chiếu mục tiêu. Chỉ dọn môi trường thử nghiệm sau khi bảo toàn bằng chứng và xác nhận người phụ trách đồng ý theo quy trình. Không dọn hoặc làm thay đổi backup gốc chỉ vì cuộc diễn tập đã hoàn thành.

### 6.3. Những lệnh quan sát minh họa

Chỉ chạy trên **cluster diễn tập** theo quyền được cấp, và đối chiếu cú pháp của phiên bản đang vận hành:

~~~bash
# Quan sát topology, trạng thái node và token ownership.
nodetool status

# Kiểm tra snapshot còn ở node nguồn; lệnh có tác dụng cục bộ.
nodetool listsnapshots

# Khi chuẩn bị một snapshot thử nghiệm trên node nguồn:
# (cần điều phối đủ các node để tạo backup set cho toàn cluster)
nodetool snapshot -t drill_20261121T0800Z restore_drill

# Quan sát thông tin node sau restore.
nodetool info

# Kiểm tra việc compaction có chiếm tài nguyên trong giai đoạn nghiệm thu.
nodetool compactionstats

# Thống kê bảng trên phiên bản hỗ trợ.
nodetool tablestats restore_drill.events_by_customer_day
~~~

Lệnh **nodetool snapshot** có thể flush memtable theo hành vi của phiên bản nếu không chọn bỏ flush. Lệnh này **không tải tệp ra object storage** và **không tạo snapshot đồng thời trên tất cả node**. Mỗi lần chạy cần lưu exit code, thời gian bắt đầu/kết thúc, node được thực thi và tag. Với hệ có dữ liệu nằm trong các keyspace khác, phải xác định toàn bộ phạm vi backup.

Việc nạp dữ liệu từ SSTable vào cluster đích có nhiều khác biệt theo phiên bản, table ID, schema và công cụ. Runbook production cần chứa **lệnh restore đã được kiểm chứng riêng cho cluster đó**; một ví dụ chung không nên khuyến khích copy trực tiếp file snapshot vào thư mục data của node đang phục vụ.

## 7. Kiểm chứng bằng ứng dụng Java sau khi restore

CQL kiểm chứng thủ công chỉ trả lời được một phần. Ứng dụng Java cần chứng minh driver kết nối đúng cluster khôi phục, có thể dùng prepared statement và đọc dữ liệu đúng partition với consistency level đã chọn.

~~~java
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public class CassandraRestoreVerification {
    public static void main(String[] args) {
        UUID customerId = UUID.fromString(
                "11111111-1111-4111-8111-111111111111");
        LocalDate eventDay = LocalDate.of(2026, 11, 21);
        UUID expectedEventId = UUID.fromString(
                "22222222-2222-4222-8222-222222222222");

        // Đổi contact point/DC theo CLUSTER PHỤC HỒI, không dùng production.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement query = session.prepare(
                "SELECT event_id, order_id, event_type, amount " +
                "FROM restore_drill.events_by_customer_day " +
                "WHERE customer_id = ? AND event_day = ? LIMIT ?");

            ResultSet result = session.execute(
                query.bind(customerId, eventDay, 100)
                     .setConsistencyLevel(
                         DefaultConsistencyLevel.LOCAL_QUORUM));

            boolean found = false;
            for (Row row : result) {
                if (expectedEventId.equals(row.getUuid("event_id"))
                    && "ORDER_CREATED".equals(row.getString("event_type"))
                    && row.getBigDecimal("amount")
                          .compareTo(new java.math.BigDecimal("120.50")) == 0) {
                    found = true;
                    break;
                }
            }
            if (!found) {
                throw new IllegalStateException(
                    "Không tìm thấy dữ liệu mong đợi sau restore");
            }
            System.out.println("PASS: sự kiện mẫu có đủ khóa và giá trị");
        }
    }
}
~~~

Đoạn trên dùng **Java driver 4.x** và dữ liệu thử ở mục 5. **LOCAL_QUORUM** chỉ phù hợp nếu số replica ở local DC đáp ứng được quorum; nếu cluster diễn tập chỉ có một node, cần thiết kế RF/CL phù hợp và ghi rõ sự khác biệt với production. **LIMIT 100** và một bản ghi mẫu không chứng minh phục hồi toàn bộ; phải kết hợp danh sách nhiều partition và invariant do chủ ứng dụng cung cấp.

Kiểm chứng bổ sung nên gồm:

- **Đọc và ghi thử mới:** chỉ sau khi dữ liệu phục hồi được xác minh, thực hiện ghi lên bảng test; không ghi thử lên dữ liệu cần bảo toàn làm bằng chứng.
- **Timeout/error rate:** connection failures, unavailable exceptions, read/write timeouts, authentication/TLS failures.
- **Metadata driver:** prepared queries, routing key và thay đổi schema; không dùng session cũ vẫn kết nối production.
- **Tính toàn vẹn nghiệp vụ:** số đơn hàng theo khách hàng/ngày, tổng tiền, trạng thái đơn, tham chiếu giữa các bảng denormalized.
- **Đồng bộ replica:** thử đọc theo CL mục tiêu; kiểm tra trạng thái replica và repair khi runbook yêu cầu.

## 8. Đo RTO theo từng giai đoạn: ví dụ có số liệu

**Kịch bản giả định:** mô phỏng mất hoàn toàn cluster lúc **09:00 UTC**, backup sạch có **application cutoff được xác nhận lúc 08:40 UTC**. Backup đã hoàn tất upload lúc 08:50 UTC và đủ thành phần. Mục tiêu đặt trước diễn tập: **RPO ≤ 30 phút, RTO ≤ 120 phút**.

| Mốc | Thời điểm UTC | Diễn giải | Thời lượng giai đoạn |
|---|---|---|---:|
| T0 | 09:00 | Ảnh hưởng dịch vụ bắt đầu | — |
| T1 | 09:06 | Alert phát hiện, người trực xác nhận | 6 phút |
| T2 | 09:18 | Chọn backup 08:40 và khai triển runbook | 12 phút |
| T3 | 09:40 | Cluster khôi phục và quyền truy cập sẵn sàng | 22 phút |
| T4 | 10:12 | Tải tệp + checksum hoàn tất | 32 phút |
| T5 | 11:04 | Nạp SSTable, schema và node sẵn sàng đọc | 52 phút |
| T6 | 11:40 | CQL/Java và đối soát dữ liệu đạt nghiệm thu | 36 phút |
| T7 | 12:00 | Chuyển traffic giả lập hoàn tất, dịch vụ thử hoạt động | 20 phút |

Kết quả:

~~~text
RPO theo cutoff = 09:00 - 08:40 = 20 phút
RTO diễn tập   = 12:00 - 09:00 = 180 phút = 3 giờ

Mục tiêu RPO <= 30 phút   → đạt nếu cutoff/đối soát được chứng minh
Mục tiêu RTO <= 120 phút  → KHÔNG đạt; vượt 60 phút
~~~

**Cách diễn giải:** mốc 08:50 là lúc upload hoàn thành, không phải cutoff. Với bảng ghi sau 08:40, cần đối soát event ID đã được xác nhận trước sự cố để xác định **số sự kiện thiếu thực tế** và nguồn tái phát. Nếu chưa chứng minh snapshot có cutoff đồng nhất, chỉ báo **RPO ước lượng** với độ bất định thích hợp.

Vì T7 là **chuyển traffic giả lập**, báo cáo phải gọi thời gian này là **RTO diễn tập trong điều kiện đã khai báo**. Còn phải xác minh các phụ thuộc chưa thử, ví dụ DNS TTL production, quyền KMS khi region chính mất, thông lượng tải hàng chục TiB và các client Java ở nhiều mạng khác nhau.

### 8.1. Đọc ra nút thắt từ timeline

Trong ví dụ:

- **T4 → T5 = 52 phút**: giai đoạn nạp dữ liệu dài nhất. Có thể do bandwidth, số SSTable, ổ đĩa, streaming, compaction hoặc topology.
- **T5 → T6 = 36 phút**: kiểm chứng mất nhiều thời gian; có thể thiếu bộ fixture tự động, query mẫu hay người duyệt.
- **T2 → T3 = 22 phút**: dựng hạ tầng/quyền; có thể cải thiện bằng IaC, image đã kiểm chứng và quyền giải mã dự phòng.

Không nên kết luận một bước chậm chỉ vì con số thời gian. Đối chiếu CPU, disk throughput/latency, network bandwidth, cluster status, driver metrics, log và sự kiện cgroup/OOM để tìm nguyên nhân. Sau đó chọn **một hoặc vài cải tiến có trách nhiệm và cách xác minh**, không tùy tiện tăng thread/concurrency mà chưa đo tài nguyên.

## 9. Phiếu ghi chép diễn tập và bằng chứng

Mỗi lần diễn tập cần một **hồ sơ duy nhất** có ID, phiên bản runbook và đầy đủ mốc thời gian. Mẫu có thể như sau:

~~~yaml
drill_id: "cassandra-restore-2026-11-21-01"
scenario: "loss-of-primary-cluster"
environment: "isolated-restore-cluster"
runbook_version_used: "v1.4"
owner_role: "database-oncall"
application_owner_role: "orders-service"
scope:
  keyspaces: ["restore_drill"]
  cassandra_version: "<actual-version>"
  local_datacenter: "dc1"
backup:
  backup_id: "<verified-backup-id>"
  status: "COMPLETE"
  cutoff_utc: "2026-11-21T08:40:00Z"
  uploaded_utc: "2026-11-21T08:50:00Z"
  manifest_checksum: "<verified-digest>"
  schema_location: "<reference>"
targets:
  rpo_minutes: 30
  rto_minutes: 120
measured:
  impact_started_utc: "2026-11-21T09:00:00Z"
  detected_utc: "2026-11-21T09:06:00Z"
  decision_utc: "2026-11-21T09:18:00Z"
  environment_ready_utc: "2026-11-21T09:40:00Z"
  download_verified_utc: "2026-11-21T10:12:00Z"
  data_loaded_utc: "2026-11-21T11:04:00Z"
  application_validated_utc: "2026-11-21T11:40:00Z"
  simulated_traffic_ready_utc: "2026-11-21T12:00:00Z"
  rpo_estimate_minutes: 20
  rto_drill_minutes: 180
validation:
  token_coverage: "verified"
  schema_compatible: true
  backup_integrity: "verified"
  business_invariants: "passed-for-defined-fixtures"
  production_cutover_tested: false
result: "PARTIAL_FAIL_RTO"
findings_reference: "<ticket-or-document>"
next_drill_due: "<approved-date>"
~~~

Mẫu YAML này là **bản ghi minh họa do đội vận hành tự xây dựng**, không phải cấu hình Cassandra và không yêu cầu ghi vào bất kỳ tệp đặc biệt nào của cluster. Tên version, ID, mốc, kết quả và quyền đều phải thay bằng số liệu đã quan sát thực tế. Không nhúng access token, password hoặc private key vào hồ sơ.

Một hồ sơ tốt có **bằng chứng đi kèm**: checksum của manifest, log command kèm exit code, ảnh chụp metrics có thời gian, danh sách row/invariant đã đối soát, ticket blocker, thay đổi cấu hình và xác nhận nghiệm thu. Giữ quyền truy cập bằng chứng theo mức độ nhạy cảm; kiểm soát dữ liệu khách hàng trong log.

## 10. Cập nhật runbook sau cuộc diễn tập

**Runbook** phải là các bước đủ cụ thể để một người trực khác có thể thực hiện trong áp lực sự cố, chứ không chỉ là tài liệu mô tả lý thuyết. Sau diễn tập, người phụ trách cập nhật dựa trên lỗi và bằng chứng đã ghi nhận.

### 10.1. Cấu trúc sổ tay đề xuất

| Phần runbook | Nội dung phải có |
|---|---|
| **Mục đích và điều kiện kích hoạt** | Loại sự cố, khi nào dùng restore, khi nào thay node/repair, hệ thống trong phạm vi |
| **Vai trò và quyền quyết định** | Incident commander, Cassandra on-call, Java service owner, security, người nghiệm thu |
| **Thông tin trước khi chạy** | Cluster/version/DC, keyspace, snapshot/backup ID, cutoff, manifest, schema, quyền KMS, RPO/RTO |
| **Điểm dừng an toàn** | Tiêu chí từ chối backup thiếu, sai checksum, schema mismatch, thiếu khóa hoặc thiếu replica |
| **Lệnh và tham số đã kiểm chứng** | Chính xác cho Cassandra/JDK/version, biến thay thế, host nào chạy, exit code kỳ vọng |
| **Bằng chứng theo từng bước** | T0–T7, log, metrics, checksum, kết quả truy vấn/invariant và người xác nhận |
| **Chuyển lưu lượng / rollback** | Cấu hình driver/secret/DNS/TLS, phương án ngừng ghi, rollback và test sau cutover |
| **Khác biệt môi trường** | Dữ liệu nhỏ so với production, RF/CL, storage, network, vùng KMS không mô phỏng được |
| **Hậu kiểm và vòng đời** | Ngày diễn tập, kết quả, issue còn mở, owner, hạn sửa, phiên bản runbook mới |

### 10.2. Ví dụ sửa runbook theo nguyên nhân

**Phát hiện:** lúc T3, đội diễn tập mất 15 phút vì thông tin tài khoản đọc bucket và quyền KMS đã hết hạn.

**Trước khi cập nhật:**

> Tải snapshot từ object storage và khôi phục lên cluster.

**Sau khi cập nhật:**

1. Trước diễn tập và định kỳ trước khi xảy ra sự cố, kiểm thử role phục hồi có thể **list, đọc object, giải mã** một file thử ở miền đích.
2. Ghi **tên role, nơi cấp quyền, điều kiện kích hoạt và kênh liên hệ** vào runbook. Không ghi secret trực tiếp.
3. Trước T4, xác minh manifest cùng khả năng giải mã; nếu thất bại quá ngưỡng đã định, mở đường escalation và chọn bản backup/role dự phòng.
4. Bổ sung mốc **T3a — quyền giải mã sẵn sàng**, có thời gian và bằng chứng.
5. Giao issue cụ thể cho owner IAM/KMS, kiểm thử lại bằng drill ngắn sau sửa.

Thay đổi này trực tiếp xử lý một blocker đã quan sát được. **Một runbook cập nhật nhưng chưa kiểm chứng lại** chỉ là giả thuyết cải tiến.

### 10.3. Version, review và lịch diễn tập lại

Khi phát hành bản runbook mới, ghi:

~~~text
Version: v1.5
Thay đổi: thêm bước kiểm tra quyền bucket/KMS trước khôi phục
Lý do: drill 2026-11-21 phát hiện chậm 15 phút
Owner: database-oncall + security/IAM owner
Kiểm chứng: test giải mã file mẫu và tải manifest ở miền khôi phục
Trạng thái: pending validation / verified
Rollback: dùng quy trình đã xác minh gần nhất nếu bước mới gây lỗi
Ngày review tiếp: theo chính sách đội vận hành
~~~

Tần suất diễn tập cần dựa trên **RPO/RTO cam kết, mức thay đổi của hệ thống và hậu quả nếu phục hồi lỗi**. Ví dụ có thể chạy tabletop thường xuyên, restore chọn lọc mỗi tháng/quý và diễn tập đầy đủ sau thay đổi lớn về Cassandra/JDK, topology, backup service, IAM/KMS hoặc Java driver. Đây là **gợi ý lập lịch**, không phải tần suất bắt buộc cho mọi tổ chức.

## 11. Các lỗi đặc thù Cassandra thường lộ ra khi diễn tập

### 11.1. Backup thiếu phạm vi token hoặc node

RF = 3 không có nghĩa một node chứa 100% dữ liệu của keyspace. Nếu chỉ sao lưu snapshot của node A, nhiều token range có thể hoàn toàn không nằm trong tập tệp của A.

**Phát hiện:** đối chiếu manifest với node/token ownership và kiểm thử các partition phân bố rộng. **Cách khắc phục:** sửa job snapshot/copy để bảo đảm độ phủ dữ liệu đầy đủ theo thiết kế backup, sau đó chạy lại diễn tập.

### 11.2. Schema, table ID hoặc SSTable format không tương thích

SSTable thuộc một table/schema/version cụ thể; khôi phục sang cluster khác mà sai table ID, UDT, kiểu cột hoặc định dạng có thể không nạp được hoặc cho kết quả khó lường.

**Phát hiện:** xem log công cụ restore, thông tin version, schema CQL và tên/table ID trong manifest. **Cách khắc phục:** giữ schema/cấu hình cùng backup, xác định phương án restore/streaming tương thích đúng phiên bản; không tự sửa tên thư mục/SSTable tùy tiện để che lỗi.

### 11.3. Dữ liệu bị xóa trước cutoff lại xuất hiện

Nếu khôi phục snapshot cũ rồi trộn với dữ liệu mới sai quy trình, tombstone của DELETE hợp lệ có thể không còn đầy đủ; hệ thống có thể làm sống lại dữ liệu đã xóa. TTL, **gc_grace_seconds** và thời gian repair ảnh hưởng tình huống này.

**Phát hiện:** dùng fixture có DELETE/TTL và xác minh *sự vắng mặt* của row phải bị xóa. **Cách khắc phục:** phục hồi cô lập ở mốc rõ ràng, áp dụng đúng cơ chế replay/hòa giải dữ liệu, không giảm gc_grace hoặc tự ý chạy compaction để xử lý nhanh.

### 11.4. Snapshot có nhưng backup ngoài miền lỗi chưa hoàn chỉnh

**nodetool snapshot** thường tạo hard link cục bộ; phải copy đủ SSTable components, schema và metadata đến kho an toàn, kiểm tra checksum. Upload thiếu một tệp chỉ bị phát hiện nếu restore thực sự được thử.

**Phát hiện:** đối chiếu manifest, số node/table/tệp, checksum và kiểm tra quyền giải mã ở môi trường đích. **Cách khắc phục:** gắn nhãn COMPLETE chỉ sau khi kiểm tra đủ thành phần, không cho retention xóa bản sạch trước đó khi job mới thất bại.

### 11.5. Dùng repair để “khôi phục” một DELETE sai

Repair đồng bộ trạng thái giữa replica theo cơ chế Cassandra. Nó không hiểu thao tác xóa có hợp lệ về nghiệp vụ hay không, và không thể quay ngược về snapshot cũ nếu backup không tồn tại.

**Phát hiện:** dữ liệu đã xóa đồng loạt trên replica, không còn bản lịch sử. **Cách khắc phục:** lấy bản trước lỗi từ backup độc lập hoặc event log nghiệp vụ, sau đó khôi phục có kiểm soát.

### 11.6. Cluster đích có dữ liệu nhưng Java service vẫn lỗi

Một cluster có thể có đủ SSTable nhưng app Java vẫn dùng contact point cũ, local datacenter sai, schema mới chưa đồng bộ, prepared statements chưa refresh, TLS/ACL không hợp lệ hoặc truy vấn theo partition key trả dữ liệu không đúng cutoff.

**Phát hiện:** chạy test từ chính môi trường ứng dụng, kiểm tra kết nối, consistency, query và latency. **Cách khắc phục:** bổ sung các bước cấu hình driver và kiểm thử end-to-end vào runbook, không kết thúc ở trạng thái node **UN (Up/Normal)**.

## 12. Đo dung lượng và công việc nền khi restore

Cassandra có thể tiếp tục thực hiện **compaction, repair, streaming và đồng bộ replica** sau khi dữ liệu ban đầu được nạp. Những công việc này ảnh hưởng RTO và trạng thái dịch vụ thực tế.

| Hoạt động | Chỉ số nên quan sát | Nguy cơ cho RTO |
|---|---|---|
| Tải tệp từ kho backup | Thông lượng, checksum, latency mạng, retry | Network/KMS/bandwidth giới hạn; thiếu tệp |
| Nạp SSTable/streaming | Tốc độ nạp, số tệp, disk throughput, pending tasks | Data volume lớn, nhiều SSTable, CPU/disk bão hòa |
| Compaction | Backlog, write amplification, disk free, latency | Đọc/ghi cạnh tranh, thiếu dung lượng tạm |
| Repair | Trạng thái tác vụ, tiến độ, network/disk, replica health | Kéo dài giai đoạn hội tụ; không được phép che dữ liệu sai |
| JVM, heap/off-heap và OS | GC pauses, RSS, MemAvailable/page cache, OOM | Node bị restart/OOM, latency cao |
| Client Java | p95/p99, timeout, retry, số kết nối, CL | Dịch vụ chưa sẵn sàng dù cluster đã khởi động |

Kết quả thử nghiệm phải ghi **dung lượng dữ liệu và cấu hình phần cứng tương ứng**. Nếu chỉ khôi phục 1 GiB trên máy thử nhưng production có 30 TiB và topology đa region, không được nhân tuyến tính số liệu để hứa RTO. Có thể dự báo sơ bộ theo throughput đo, nhưng phải cộng overhead và thực hiện diễn tập đại diện để xác nhận.

## 13. Tiêu chí pass/fail và công việc tiếp theo

Một diễn tập **PASS** khi thỏa **tất cả điều kiện trong phạm vi đã tuyên bố**:

- Backup hợp lệ, đầy đủ và giải mã được bằng quy trình độc lập phù hợp kịch bản.
- Schema/table/partition phục hồi đúng; đối soát fixture, TTL/DELETE và invariant nghiệp vụ đạt ngưỡng.
- Cassandra đáp ứng mức replication/consistency cần cho ứng dụng trong môi trường đích.
- Java service đọc và ghi thử đúng cluster, không có tỷ lệ lỗi/latency ngoài mục tiêu nghiệm thu.
- RPO và RTO đo theo định nghĩa đã chốt, **đều trong ngưỡng**.
- Bằng chứng, timeline, bất định và giới hạn thử nghiệm được ghi vào hồ sơ.

**PARTIAL** hoặc **FAIL** khi còn phần chưa được kiểm chứng hoặc bất kỳ tiêu chí bắt buộc nào không đạt. Báo cáo phải tách lỗi dữ liệu, lỗi quy trình, lỗi hiệu năng và lỗ hổng kiểm thử.

Với ví dụ mục 8, **RPO theo cutoff đạt 20 phút**, nhưng **RTO diễn tập 180 phút vượt mục tiêu 120 phút**, nên kết quả là **FAIL theo mục tiêu RTO**. Cần tạo các công việc có owner, hạn xử lý và phép đo xác nhận:

| Phát hiện | Hành động | Xác minh sau sửa |
|---|---|---|
| T4 → T5 mất 52 phút | Đánh giá tốc độ tải/nạp, số SSTable, disk/network, quy trình song song có kiểm soát | Đo lại đúng backup volume/topology |
| T5 → T6 mất 36 phút | Tự động hóa đối chiếu partition mẫu, event ID và invariant Java | Chạy bộ test, đo tỷ lệ false positive và thời gian |
| T2 → T3 mất 22 phút | Chuẩn bị IaC/image, quyền KMS và network đích | Dựng mới từ đầu trong diễn tập kế tiếp |

Đừng đánh dấu việc “cập nhật tài liệu” là đã khắc phục rủi ro. Chỉ đóng issue khi bằng chứng diễn tập sau sửa chứng minh kết quả.

## 14. Bài tập thực hành

### Bài 1 — Phân biệt mốc upload và mốc dữ liệu

Bản snapshot hoàn chỉnh có cutoff được chứng minh lúc **01:00 UTC**, upload sang miền độc lập xong lúc **01:25**. Cluster hỏng lúc **04:10**. Không có incremental/commitlog archive.

**Câu hỏi:** RPO theo cutoff là bao nhiêu? Có thể lấy mốc 01:25 làm recovery point không?

**Gợi ý:** **3 giờ 10 phút (190 phút)**. Upload xong không chứng minh backup chứa dữ liệu đến 01:25. Cần đối soát các ghi hợp lệ sau 01:00 và nguồn tái phát nếu có.

### Bài 2 — Tính RTO đúng phạm vi

Một diễn tập có các mốc:

~~~text
10:00 - sự cố bắt đầu
10:08 - phát hiện
10:24 - quyết định khôi phục
10:50 - môi trường đích sẵn sàng
11:35 - SSTable nạp xong
12:20 - app và dữ liệu nghiệm thu
12:30 - đường truy cập phục vụ đã mở
~~~

**Câu hỏi:** RTO từ đầu sự cố đến lúc sẵn sàng phục vụ là bao nhiêu? Nếu chỉ báo “restore mất 45 phút” từ 10:50 đến 11:35 thì bỏ sót gì?

**Gợi ý:** **150 phút**. Con số 45 phút chỉ là nạp dữ liệu, bỏ qua phát hiện, quyết định, dựng cluster, kiểm thử, chuyển đường truy cập.

### Bài 3 — Cluster UP nhưng chưa đủ bằng chứng

Sau khi restore, **nodetool status** hiển thị mọi node **UN**, nhưng Java service báo timeout khi đọc **LOCAL_QUORUM** và thiếu vài order ID.

**Câu hỏi:** Có được công bố PASS không? Kiểm tra gì tiếp theo?

**Gợi ý:** Không. Cần kiểm tra RF/DC/rack, CL, token coverage, schema, dữ liệu theo partition, backup manifest, disk/network, driver connection và các order ID đã được ghi trước cutoff. Trạng thái UN không bảo đảm dữ liệu đúng.

### Bài 4 — Viết một thay đổi runbook đo được

Cuộc diễn tập không đạt RTO vì mất 25 phút tìm người có quyền giải mã backup.

**Yêu cầu:** Viết một thay đổi cụ thể về bước kiểm tra quyền trước phục hồi, owner, bằng chứng và cách kiểm chứng ở lần diễn tập sau.

**Gợi ý:** Thêm preflight định kỳ cho restore role, KMS, đường dẫn secret và escalation; ghi thời gian xác nhận quyền, chủ sở hữu IAM, link ticket. Thực hành từ một tài khoản khôi phục đã được cấp quyền theo quy trình và đo T3a.

### Bài 5 — Lựa chọn đúng cơ chế

Có hai sự cố:

- **A:** Một node hỏng, RF = 3 và các replica còn lại chứa dữ liệu mới nhất.
- **B:** Một DELETE sai đã được replicate tới cả ba replica.

**Câu hỏi:** Khi nào ưu tiên replace/streaming, khi nào cần backup?

**Gợi ý:** A: thay node rồi đồng bộ từ replica và kiểm tra consistency. B: cần bản backup sạch trước DELETE hoặc nguồn lịch sử độc lập; repair chỉ đồng bộ bản sao, không tự undo thao tác sai.

## 15. Checklist trước khi tuyên bố “sẵn sàng khôi phục”

- [ ] Đã xác định **loại sự cố, miền lỗi, phạm vi keyspace/table** và mức diễn tập.
- [ ] Có một hoặc nhiều backup **COMPLETE**, đủ node/token range, checksum, schema và khóa giải mã.
- [ ] Quyền khôi phục hoạt động khi giả định miền chính không còn, có thử tải/giải mã dữ liệu.
- [ ] Có môi trường cô lập tương thích Cassandra/JDK và đủ storage/network.
- [ ] Có fixture hoặc dữ liệu đối soát theo **partition key**, bao gồm UPDATE, DELETE, TTL và nhiều token range.
- [ ] Runbook có lệnh được kiểm chứng cho đúng version, host, owner, điều kiện dừng và rollback.
- [ ] Đã đo **T0–T7**, tách cutoff dữ liệu khỏi thời điểm upload và ghi rõ mốc mô phỏng.
- [ ] CQL và Java service đã được kiểm thử với **consistency level** phù hợp, có đối soát nghiệp vụ.
- [ ] Đã đánh giá tác động compaction/repair/streaming và giới hạn tài nguyên đến thời gian phục hồi.
- [ ] Có **RPO/RTO đo được**, kết luận PASS/FAIL minh bạch và bằng chứng.
- [ ] Mọi phát hiện có owner, mức ưu tiên, hạn xử lý và lần kiểm thử lại.
- [ ] Runbook đã tăng version/review, lịch diễn tập tiếp theo đã được xác định theo chính sách vận hành.

## 16. Tổng kết

Diễn tập khôi phục Cassandra là phép thử **cả dữ liệu, hạ tầng, ứng dụng và con người**. Replica giúp chịu lỗi node nhưng không quay ngược một DELETE sai; snapshot giữ SSTable ở một mốc nhưng phải được bảo quản ngoài miền lỗi; backup chỉ có giá trị khi dữ liệu, schema, khóa và quy trình nạp lại đều được kiểm chứng.

Một cuộc diễn tập tốt chọn đúng kịch bản, chốt RPO/RTO từ đầu, khôi phục vào môi trường cô lập, xác nhận dữ liệu theo partition key và kiểm thử ứng dụng Java ở consistency level dự kiến. Từng mốc được đo và đối chiếu với mục tiêu; phát hiện được chuyển thành **thay đổi runbook có owner và bằng chứng kiểm chứng lại**. Khi làm được vậy, “có backup” mới tiến gần đến “khôi phục được dịch vụ trong thời gian chấp nhận được”.
