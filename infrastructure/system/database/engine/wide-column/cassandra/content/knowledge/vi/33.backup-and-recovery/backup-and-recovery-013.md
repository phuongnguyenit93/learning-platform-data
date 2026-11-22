# Đối soát dữ liệu, bất biến nghiệp vụ và số liệu sau restore

> **Chương:** Sao lưu và phục hồi  
> **Phạm vi:** Apache Cassandra — cơ sở dữ liệu phân tán theo mô hình *wide-column*, lưu dữ liệu trong SSTable, nhân bản theo token/rack/datacenter và phục vụ CQL qua Java Driver. Bài này tập trung vào **kiểm chứng tính đúng đắn sau khi phục hồi**, không chỉ thao tác đưa tệp trở lại cluster.
>
> **Mục tiêu học tập:** Xác lập mốc khôi phục và dữ liệu kỳ vọng; đối soát độ đầy đủ theo partition/token range; kiểm tra TTL, tombstone, timestamp và quan hệ giữa các bảng denormalized; định nghĩa bất biến nghiệp vụ; đo RPO, RTO, độ trễ và mức sai lệch; đưa ra quyết định *go/no-go* trước khi mở traffic.

## 1. Restore báo thành công nhưng ứng dụng vẫn có thể sai

Giả sử một cluster Cassandra dùng để lưu đơn hàng gặp sự cố mất một số node. Đội vận hành khôi phục từ snapshot SSTable rồi stream dữ liệu vào cluster mới. Các công cụ báo không còn lỗi, `nodetool status` cho thấy node `UN` (*Up/Normal*) và ứng dụng Java kết nối được.

Tuy nhiên, khi mở thử traffic:

- Một số đơn có trạng thái `PAID` nhưng không thấy sự kiện thanh toán tương ứng.
- Bảng `orders_by_id` có đơn hàng, còn bảng `orders_by_customer_day` phục vụ danh sách đơn hàng lại thiếu.
- Một lệnh `DELETE` trước sự cố không được phản ánh đầy đủ, khiến bản ghi đã xóa xuất hiện lại.
- Dữ liệu dùng TTL đã hết hạn nhưng báo cáo đối soát lại xem đó là “mất dữ liệu”.
- Dữ liệu từ ngày sau mốc snapshot không tồn tại; hệ thống không biết đã vượt mục tiêu RPO hay chưa.

**Thành công kỹ thuật của restore khác với tính đúng đắn nghiệp vụ.** Phải chứng minh đồng thời:

1. **Đủ phạm vi:** những partition/token ranges cần thiết thực sự có dữ liệu.
2. **Đúng phiên bản dữ liệu:** giá trị, timestamp, TTL và dấu xóa phản ánh chính sách khôi phục.
3. **Đúng quan hệ nghiệp vụ:** các projection, lịch sử sự kiện và bản ghi trạng thái không mâu thuẫn ngoài phạm vi nhất quán được chấp nhận.
4. **Phục vụ được:** truy vấn Java/CQL đúng access pattern đạt consistency level, độ trễ và khả năng sẵn sàng mong muốn.
5. **Khớp mục tiêu phục hồi:** mất dữ liệu và thời gian gián đoạn được đo minh bạch so với RPO/RTO.

```text
Snapshot / backup / log replay / streaming
                  |
                  v
     File và replica báo phục hồi xong
                  |
                  v
      Đối soát cấp lưu trữ và token range
                  |
                  v
          Đối soát cấp dữ liệu CQL
                  |
                  v
      Kiểm tra bất biến nghiệp vụ, TTL,
      delete, projection và transaction flow
                  |
                  v
        Canary ứng dụng + p95/p99 + RPO/RTO
                  |
                  v
         Quyết định go / no-go / rollback
```

Một kết quả `SELECT` thành công trên một partition **không thay thế** toàn bộ những bước này.

## 2. Trước tiên phải xác định: “khôi phục tới thời điểm nào?”

Cassandra là hệ phân tán với nhiều replica và nhiều bảng phục vụ truy vấn. Snapshot cục bộ trên một node không tự tạo thành một **ảnh chụp nguyên tử của toàn cluster**. Các node có thể chụp ở thời điểm khác nhau, nhận mutation ở CL khác nhau, và một số ghi đang được ứng dụng xử lý khi snapshot bắt đầu.

Do đó, trước khi đối soát cần xác định **hợp đồng khôi phục**:

| Trường | Ý nghĩa | Ví dụ minh họa |
| --- | --- | --- |
| `T_restore_target` | Mốc dữ liệu nghiệp vụ muốn phục hồi đến | 14:00 UTC |
| `T_snapshot` | Mốc/bộ mốc snapshot và trạng thái từng replica | 13:45–13:47 UTC |
| Log/CDC có thể replay | Các mutation sau snapshot đủ để phục hồi tới mốc nào | Có đến 13:58 UTC |
| Quorum/replica condition | Nguồn có bao phủ mutation đã được ACK theo CL không | Cần xác minh theo RF/DC |
| Phạm vi | Keyspace, bảng, token ranges, DC, nghiệp vụ | Đơn hàng và sự kiện thanh toán |
| Ngoại lệ chấp nhận | Những thay đổi ngoài phạm vi mốc phục hồi | Không bao gồm ghi sau 13:58 |
| Chính sách TTL/delete | Dữ liệu đã hết hạn/xóa phải được đánh giá ra sao | Theo thời gian thực tại lúc đọc |
| Nguồn đối chứng | Manifest, ledger, sự kiện ở hệ độc lập, audit log | Event manifest đã đóng dấu mốc |

### Snapshot không phải point-in-time transaction của mọi bảng

Một đơn có thể được ghi vào `orders_by_id` lúc 13:46:30 và projection `orders_by_customer_day` lúc 13:46:31. Nếu snapshot hai bảng/replica xảy ra xen giữa, trạng thái phục hồi có thể chứa một bản ghi nhưng thiếu bản còn lại — **dù từng SSTable đều hợp lệ**.

Nếu cần điểm khôi phục thống nhất xuyên nhiều bảng, phải thiết kế quy trình cấp ứng dụng: kiểm soát writer, tạo checkpoint/watermark có thể kiểm chứng, backup/CDC đầy đủ và đối soát khi phục hồi. Không thể chỉ nói “chụp lúc 13:46” mà bảo đảm một giao dịch đa partition đã được ghi nguyên tử.

### Tách ba mốc thời gian

- **Thời gian sự kiện nghiệp vụ:** `event_time`/`created_at`; có thể do client gửi, đến muộn hoặc bị backfill.
- **Timestamp của Cassandra mutation:** được dùng trong reconciliation khi nhiều phiên bản/tombstone cạnh tranh; có thể khác thời gian sự kiện.
- **Thời gian backup/restore:** thời điểm tạo snapshot, replay hoặc load; **không mặc nhiên** là timestamp mới của dữ liệu nhập.

Chọn một mốc đối soát mà **nguồn dữ liệu có thể chứng minh**. Nếu không có log sau snapshot, không được tự tuyên bố đã phục hồi mọi mutation tới lúc sự cố.

## 3. RPO và RTO phải đo sau khi kiểm chứng, không phải lúc process dừng

**RPO (Recovery Point Objective)** là mức mất dữ liệu theo thời gian mà nghiệp vụ chấp nhận. **RTO (Recovery Time Objective)** là thời gian khôi phục dịch vụ được phép.

Ví dụ:

```text
13:52  Sự kiện nghiệp vụ cuối cùng được xác minh đã phục hồi.
14:00  Sự cố bắt đầu làm mất khả năng phục vụ.
14:20  Bắt đầu dựng cluster từ snapshot.
15:05  Streaming báo hoàn tất.
15:40  Đối soát dữ liệu và bất biến đạt, canary đạt SLO.
15:50  Mở traffic chính thức và xác nhận dịch vụ ổn định.

Độ mất mốc dữ liệu minh họa: 14:00 - 13:52 = 8 phút.
Thời gian khôi phục dịch vụ: 15:50 - 14:00 = 110 phút.
```

Các con số chỉ mang tính minh họa. Trong thực tế, không phải “sự kiện cuối cùng được nhìn thấy” là đủ chứng minh toàn bộ sự kiện trước đó đã phục hồi. Cần **checkpoint liên tục và manifest phủ đầy đủ phạm vi** để kết luận khả năng mất dữ liệu. Nếu không chứng minh được, báo cáo `RPO=unknown` hoặc một **khoảng có điều kiện**, không bịa một con số chính xác.

**Không kết thúc đồng hồ RTO tại 15:05**, vì streaming xong nhưng dữ liệu/canary chưa đạt chưa phải dịch vụ khôi phục được theo SLO.

### Những con số cần công bố riêng

| Thước đo | Không được nhầm với | Bằng chứng |
| --- | --- | --- |
| Backup age | RPO đã thực hiện | Snapshot timeline, log replay, watermark |
| Streaming duration | RTO thực tế | Log loader/rebuild |
| Validated recovery point | Ngày tạo file backup | Manifest và event coverage tới mốc |
| Service recovery time | Giờ node đầu tiên `UN` | Kết quả kiểm tra dữ liệu + API SLO + cutover |
| Restore completeness | Số GiB chuyển thành công | Kiểm chứng range, partition và nguồn đối chứng |

## 4. Thiết kế một “nguồn sự thật” để đối soát

Nếu bảng Cassandra phục hồi được dùng **để tự xác nhận chính nó**, ta chỉ chứng minh một trạng thái nội bộ, không chứng minh nó đúng với dữ liệu đáng lẽ phải có.

Nguồn đối chứng nên được giữ **độc lập với cụm đang phục hồi**, theo quyền riêng tư và chính sách bảo mật:

- Manifest do quy trình backup ghi nhận: schema/version, token ranges, SSTable inventory, checksums và checkpoint.
- Audit/event ledger của ứng dụng (khi có), lưu tách đường failure với Cassandra.
- Log thay đổi có thể replay theo thứ tự xác định, có event ID và mốc watermark.
- Báo cáo kế toán/thanh toán hoặc hệ thống nguồn nghiệp vụ độc lập.
- Tập khóa/case kiểm thử đã định danh trước sự cố: khách hàng nóng, đơn thanh toán, đơn đã xóa, dữ liệu TTL và dữ liệu biên.

**Không phải mọi hệ thống đều có ledger độc lập.** Nếu thiếu, phải nêu mức độ bằng chứng thấp hơn: ví dụ có thể xác nhận tính toàn vẹn file và số partition theo manifest SSTable, nhưng chưa chứng minh “không mất bất kỳ đơn đã được ACK nào”.

### Manifest tốt nên chứa gì?

Ví dụ **định dạng minh họa**, không phải schema Cassandra mặc định:

```json
{
  "restore_id": "restore-lab-2026-11-21-a",
  "target_cluster": "cassandra-dr-lab",
  "source_cluster": "cassandra-primary-lab",
  "checkpoint_utc": "2026-11-21T13:58:00Z",
  "keyspace": "lab",
  "tables": ["orders_by_id", "orders_by_customer_day",
             "payment_events_by_order"],
  "partitioner": "org.apache.cassandra.dht.Murmur3Partitioner",
  "rf_by_dc": {"dc1": 3},
  "expected_token_ranges": "see-signed-range-inventory",
  "sstable_manifest": "see-signed-file-inventory",
  "business_event_watermark": "payment-event-seq-000200",
  "excluded_mutations_after_checkpoint": true
}
```

Thông tin như `expected_token_ranges` và `sstable_manifest` trong ví dụ là **tham chiếu** tới dữ liệu inventory, không khẳng định string đó tự chứa bằng chứng đầy đủ. Manifest cần có kiểm soát sửa đổi, thời điểm tạo và quyền truy cập phù hợp; không lưu dữ liệu khách hàng nhạy cảm không cần thiết.

## 5. Bốn lớp đối soát: file, replica, dữ liệu logic, nghiệp vụ

| Lớp | Câu hỏi trọng tâm | Phép kiểm tra | Giới hạn |
| --- | --- | --- | --- |
| **Tệp và backup** | Có đủ tệp/components, đúng snapshot không? | Inventory, hash/checksum, metadata SSTable | File đúng chưa chứng minh trạng thái nghiệp vụ đúng |
| **Token range và replica** | Dữ liệu đã đến những range/replica cần thiết chưa? | Topology, streaming logs, coverage và repair history | Replica đồng nhất vẫn có thể cùng thiếu mutation |
| **Dữ liệu CQL logic** | Khóa, cột, giá trị, TTL, timestamp và delete có đúng không? | Query theo partition key, so manifest, sample/scan có giới hạn | Sample không chứng minh toàn bộ bảng |
| **Bất biến nghiệp vụ** | Trạng thái đơn, thanh toán, projection, số dư có hợp lệ không? | Đối chiếu nhiều bảng và ledger, kiểm tra quy tắc | Cần hiểu luồng ghi và mốc nhất quán giữa các bảng |

Tối ưu chi phí bằng cách làm **từ rộng tới sâu**: trước tiên xác minh tính toàn vẹn nguồn và coverage, tiếp theo đối soát logic theo range/bucket, cuối cùng kiểm tra bất biến có rủi ro cao.

### Checksums của SSTable không thay thế checksums nghiệp vụ

Một hash SHA-256 khớp cho tệp `Data.db` cho biết những byte trong bản copy có tính toàn vẹn so với nguồn hash. Nó **không** chứng minh:

- File nguồn đã chứa mọi dữ liệu cần thiết.
- Tombstone còn sống đủ để che dữ liệu cũ.
- Schema của cluster đích diễn giải cột chính xác.
- Kết quả join/projection nghiệp vụ không mâu thuẫn.
- Tất cả replica hiện nay có cùng giá trị.

Ngược lại, nếu đối soát giá trị logic sau import, **không nên yêu cầu hash SSTable đích bằng hệt SSTable nguồn**: compaction, format, nén, token placement và cấu trúc SSTable có thể khác trong khi dữ liệu logic tương đương.

## 6. Mô hình bảng minh họa cho bài kiểm chứng

Giả sử nghiệp vụ demo quy định: mỗi đơn có một bản ghi trạng thái chuẩn, một bảng danh sách theo khách hàng và một lịch sử sự kiện thanh toán. Các bảng phục vụ **những truy vấn khác nhau**, không phải một mô hình quan hệ có foreign key tự động.

### Bảng nguồn trạng thái theo mã đơn

```cql
CREATE TABLE IF NOT EXISTS lab.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    order_day date,
    created_at timestamp,
    status text,
    total decimal,
    updated_at timestamp,
    last_event_id uuid
);
```

### Projection danh sách đơn hàng theo khách hàng/ngày

```cql
CREATE TABLE IF NOT EXISTS lab.orders_by_customer_day (
    customer_id uuid,
    order_day date,
    created_at timestamp,
    order_id uuid,
    status text,
    total decimal,
    PRIMARY KEY ((customer_id, order_day), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

### Lịch sử sự kiện thanh toán theo đơn

```cql
CREATE TABLE IF NOT EXISTS lab.payment_events_by_order (
    order_id uuid,
    event_time timestamp,
    payment_event_id uuid,
    outcome text,
    amount decimal,
    PRIMARY KEY ((order_id), event_time, payment_event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, payment_event_id ASC);
```

Các ví dụ chỉ chạy trên **keyspace `lab` đã tồn tại trong môi trường học tập**. Trong production, schema phải được thiết kế theo query/partition size, RF/DC và yêu cầu thanh toán thật. Ví dụ không khẳng định Cassandra tự cung cấp transaction ACID xuyên ba bảng.

### Tạo dữ liệu mẫu trên lab

```cql
INSERT INTO lab.orders_by_id
    (order_id, customer_id, order_day, created_at, status,
     total, updated_at, last_event_id)
VALUES (
    11111111-1111-4111-8111-111111111111,
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-21',
    '2026-11-21T10:00:00Z',
    'PAID',
    250.00,
    '2026-11-21T10:05:00Z',
    33333333-3333-4333-8333-333333333333
);

INSERT INTO lab.orders_by_customer_day
    (customer_id, order_day, created_at, order_id, status, total)
VALUES (
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    '2026-11-21',
    '2026-11-21T10:00:00Z',
    11111111-1111-4111-8111-111111111111,
    'PAID',
    250.00
);

INSERT INTO lab.payment_events_by_order
    (order_id, event_time, payment_event_id, outcome, amount)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21T10:05:00Z',
    33333333-3333-4333-8333-333333333333,
    'CAPTURED',
    250.00
);
```

Trong bài demo, **quy tắc nghiệp vụ được định nghĩa rõ là mỗi đơn thanh toán một lần, không trả góp, không hoàn tiền**; dưới những quy tắc này, `PAID` tương ứng với một sự kiện `CAPTURED` có số tiền bằng tổng đơn. Hệ thống thật có partial capture, refund hoặc multi-currency cần bất biến khác; đừng áp ví dụ này làm chuẩn kế toán chung.

## 7. Đối soát cấp khóa, partition và token range

### Bước A — Xác nhận những khóa nào đáng lẽ tồn tại

Dùng manifest đã chốt tại `T_restore_target` hoặc checkpoint được chứng minh để tạo danh sách **khóa mong đợi**.

Không lấy `SELECT` từ chính bảng đã restore làm danh sách duy nhất — nếu thiếu một partition, nó sẽ không xuất hiện trong danh sách và bị bỏ qua khi kiểm tra.

Các nhóm mẫu nên bao gồm:

- Khóa thường gặp và khóa rất ít đọc.
- Khách hàng có partition nhỏ/lớn, phân bố token khác nhau.
- Đơn được tạo ngay trước mốc checkpoint.
- Bản ghi bị cập nhật nhiều lần.
- Đơn đã hủy/xóa; cả **sự vắng mặt** cũng phải được đối soát.
- Dữ liệu TTL gần hết hạn.
- Dữ liệu từ các node/DC từng gặp lỗi.

### Bước B — Đọc theo đúng partition key

```cql
SELECT order_id, customer_id, order_day, created_at,
       status, total, updated_at, last_event_id
FROM lab.orders_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

Đối chiếu với manifest/ledger: tồn tại hay không, giá trị nào, timestamp nào, trạng thái nào. Một `SELECT` đơn lẻ với `LOCAL_ONE` không chứng minh cả replica đã đồng nhất. Chọn CL phù hợp với RF và mục tiêu đánh giá; khi cần xác nhận trên nhiều DC, thực hiện kiểm tra có ý thức về local DC và replication.

### Bước C — Phạm vi phải được phủ

Cassandra gán token từ partition key. Với nguồn là snapshot từ nhiều node, inventory cần xác định:

- Những token ranges nào được bao phủ bởi snapshot/source.
- Dải nào đã được stream vào replica đích.
- Node/DC nào từng offline hoặc chưa hoàn tất restore.
- Mọi phạm vi dự kiến có **kết quả đối soát đã thành công** hay chưa.

Không lấy số node `UN` làm bằng chứng đầy đủ token range. Cũng không suy ra một snapshot trên một node RF=3 đại diện toàn bộ keyspace.

### Bước D — Đừng lạm dụng toàn bảng `COUNT(*)`

```cql
-- Tránh dùng toàn bảng khổng lồ làm bài kiểm tra phục hồi:
SELECT COUNT(*) FROM lab.orders_by_id;
```

Cassandra không có bộ đếm hàng chính xác toàn bảng được cập nhật tự động để trả một cách rẻ như metadata. Toàn bảng `COUNT(*)` có thể phải đọc rất nhiều dữ liệu, gây I/O và timeout, đặc biệt ngay sau streaming/compaction.

Thay vào đó dùng manifest nguồn, inventory theo token/bucket, job scan có giới hạn và đo tốc độ, hoặc các báo cáo nghiệp vụ riêng đã được xác minh. Nếu dùng `COUNT(*)` trong lab với bảng nhỏ, phải hiểu nó **chỉ là một phép kiểm tra phụ**, không chứng minh đúng mọi giá trị.

## 8. Bất biến nghiệp vụ: điều cần giữ nguyên sau restore

**Bất biến (invariant)** là điều kiện nghiệp vụ phải đúng trong một trạng thái được xem là hợp lệ. Cassandra không tự áp đặt foreign key hoặc unique constraint xuyên tất cả partition; ứng dụng phải thiết kế ghi, đồng bộ projection và đối soát.

Cho hệ thống demo ở trên, có thể định nghĩa:

| Mã | Bất biến | Cách kiểm tra |
| --- | --- | --- |
| INV-01 | Mỗi `order_id` trong manifest phải có một trạng thái chuẩn theo mốc khôi phục | Tra `orders_by_id` và đối chiếu kỳ vọng |
| INV-02 | `total` không âm, `customer_id` và các khóa bắt buộc hợp lệ | Kiểm tra kiểu/giá trị/điều kiện domain |
| INV-03 | Nếu trạng thái `PAID` thì có `CAPTURED` đúng `last_event_id` và `amount = total` theo mô hình demo | Đọc lịch sử thanh toán và đối chiếu |
| INV-04 | Projection danh sách phải khớp `status`, `total`, khóa và mốc tạo của bản chuẩn tại checkpoint | Đọc hai bảng theo primary key tương ứng |
| INV-05 | Khóa đã xóa/hủy theo manifest và chính sách domain không được xuất hiện lại ngoài dự kiến | Đọc khóa âm tính và xem tombstone/replay history |
| INV-06 | Không có event thanh toán đã được xác nhận trước checkpoint bị bỏ sót | So ledger/event manifest độc lập |
| INV-07 | Những phép tổng hợp tài chính đã công bố khớp tập giao dịch hợp lệ | So số liệu từ ledger đã được phê duyệt |

Đây là **hợp đồng minh họa**. Thực tế có thể cho phép trạng thái `PAID` trước khi projection cập nhật trong một cửa sổ eventual consistency; khi ấy cần xác lập **checkpoint/quiescence và thời hạn hội tụ** trước khi đánh dấu vi phạm.

### Đừng biến eventual consistency thành báo lỗi giả

Một ứng dụng có thể ghi bảng chuẩn rồi cập nhật bảng projection bất đồng bộ. Trong lúc bình thường, hai bảng có thể lệch trong vài giây hoặc phút. Để kiểm tra sau restore:

1. Chọn **watermark** thể hiện toàn bộ events đến mốc nào đã được consumer áp dụng.
2. Đợi projection/consumer hoàn tất đến mốc đó, hoặc chạy backfill/reconciliation được thiết kế.
3. So sánh các bản ghi thuộc phạm vi mốc **đã hội tụ**.
4. Ghi riêng “pending theo thiết kế” và “mismatch vượt SLA hội tụ”.

Nếu snapshot lấy giữa hai bước ghi, đối soát giúp khôi phục projection; không nên dùng repair Cassandra làm công cụ duy nhất để tự dựng projection nghiệp vụ chưa từng được ghi.

## 9. Các truy vấn CQL đối soát từng bất biến

### Kiểm tra trạng thái chuẩn và projection

```cql
SELECT order_id, customer_id, order_day, created_at, status, total
FROM lab.orders_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

```cql
SELECT order_id, status, total
FROM lab.orders_by_customer_day
WHERE customer_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  AND order_day = '2026-11-21'
  AND created_at = '2026-11-21T10:00:00Z'
  AND order_id = 11111111-1111-4111-8111-111111111111;
```

Vì bảng projection có partition key kép `(customer_id, order_day)`, truy vấn xác minh dùng đủ hai thành phần và clustering keys tương ứng. **Không dùng `ALLOW FILTERING` để làm phép join tổng quát**; đối chiếu nhiều bảng được điều phối bởi quy trình kiểm thử/ứng dụng.

### Kiểm tra sự kiện thanh toán

```cql
SELECT payment_event_id, event_time, outcome, amount
FROM lab.payment_events_by_order
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

Đối chiếu `last_event_id`, `outcome` và `amount` với điều kiện nghiệp vụ demo. `ORDER BY` theo clustering và `LIMIT` có thể hữu ích nếu query muốn các event mới nhất; nhưng nếu phải chứng minh **mọi event đã ACK trước checkpoint đều có mặt**, chỉ đọc năm event mới nhất là chưa đủ.

### Kiểm tra cell timestamp và TTL

```cql
SELECT status, WRITETIME(status), TTL(status),
       total, WRITETIME(total), TTL(total)
FROM lab.orders_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

`WRITETIME` cho phép quan sát timestamp của cell phù hợp; `TTL` trả thời gian sống còn lại khi cột có TTL. Nếu một cột **không có TTL**, kết quả TTL có thể là `null`, không được hiểu là “dữ liệu đã hết hạn”. Cú pháp/kiểu cột có hỗ trợ các hàm này phải được kiểm tra theo Cassandra version.

**Timestamp thay đổi khi restore?** Nếu dùng SSTable bulk load, metadata timestamp cũ thường được giữ theo định dạng/phương thức nhập. Nếu dùng ETL ghi CQL mới, client/server có thể cấp timestamp mới. Hai phương pháp cho kết quả khác khi merge với giá trị đích; phải biết mình đang dùng phương pháp nào.

## 10. TTL: phải kiểm tra “có nên tồn tại bây giờ không?”

TTL là một lỗi đối soát phổ biến. Giả sử một event được ghi ngày D với TTL 7 ngày và snapshot vào D+2. Khi restore vào D+10, event đã hết TTL logic.

**Không nên đếm event đó là “mất do restore”** chỉ vì không được đọc thấy ở D+10. Ngược lại, nếu chính sách đòi bảo toàn dữ liệu lịch sử ngay cả sau expiry, snapshot SSTable/TTL có thể không đáp ứng yêu cầu lưu trữ; cần một kho lưu trữ khác theo chính sách.

Phân biệt các tình huống:

| Trường hợp | Kỳ vọng sau restore |
| --- | --- |
| Cell không TTL, chưa bị xóa, thuộc checkpoint | Phải còn dữ liệu nếu thuộc phạm vi khôi phục |
| Cell có TTL và chưa hết hạn lúc kiểm tra | Có thể còn; xác minh metadata expiration và replica |
| Cell TTL đã hết hạn trước lúc kiểm tra | Không mong đợi xuất hiện như dữ liệu sống |
| Cell bị DELETE hợp lệ trước checkpoint | Không được hồi sinh từ phiên bản cũ |
| Cell được ghi sau checkpoint nhưng không có log replay | Nằm ngoài phạm vi có thể cam kết phục hồi; tính vào RPO |

### Chú ý `default_time_to_live` và TTL theo cell

Bảng có thể đặt TTL mặc định; một số mutation dùng `USING TTL` riêng. Hạn hết đời của các cell có thể khác nhau ngay trong một row. Khi so sánh giữa nguồn và đích, **không lấy TTL của một cột để suy ra toàn row có thời gian sống giống hệt**.

Khi các cell hết hạn, metadata tombstone/expiry có thể còn nằm trong SSTable đến khi compaction đủ điều kiện; việc còn file trên disk không chứng minh cell phải xuất hiện trong kết quả CQL.

## 11. Tombstone và nguy cơ dữ liệu “sống lại”

Cassandra ghi dấu xóa (**tombstone**) để ngăn các phiên bản dữ liệu cũ xuất hiện. Việc xóa không đồng nghĩa ngay lập tức xóa mọi bản copy trên đĩa và mọi replica.

Hãy hình dung:

```text
T1: R1/R2/R3 giữ order X = 'CANCELLED'.
T2: Ứng dụng DELETE order X; R1/R2 nhận tombstone.
    R3 đang offline nên có thể vẫn giữ phiên bản cũ.
T3: Trải qua grace, tombstone tại R1/R2 được GC khi đủ điều kiện.
T4: Restore/repair trộn R3 cũ với dữ liệu không còn tombstone.
    Order X có nguy cơ xuất hiện trở lại ("zombie data").
```

`gc_grace_seconds` bảo vệ tombstone trong một cửa sổ để replica bỏ lỡ xóa còn có cơ hội được repair. Tombstone chỉ được xét thu hồi khi đủ điều kiện về tuổi và trạng thái SSTable; **quá grace không đồng nghĩa tự động purge ngay**.

Sau restore cần kiểm tra:

- Replica nguồn có offline lâu hơn grace không?
- Snapshot có đầy đủ tombstone/deletion history không?
- Restore có trộn dữ liệu từ các nguồn có trạng thái repair khác nhau không?
- Dữ liệu đã xóa trong manifest có xuất hiện lại không?
- Có kế hoạch repair an toàn và nguồn đáng tin để tái lập replica không?

**Không dùng một lượt `nodetool repair` trễ làm lời bảo đảm tuyệt đối.** Nếu tombstone quan trọng đã bị mất ở nguồn lành, repair không tự suy ra delete nghiệp vụ. Có thể phải rebuild/khôi phục từ nguồn tin cậy, sửa dữ liệu bằng kế hoạch có kiểm soát và ghi lại bằng chứng.

## 12. Timestamp, last-write-wins và mutation sau checkpoint

Cassandra thường hòa giải các phiên bản cell dựa trên timestamp và quy tắc của hệ thống. Một SSTable nhập sau chưa chắc “mới hơn” dữ liệu đích.

```text
SSTable phục hồi:
  order X = PENDING, cell timestamp 100

Cluster đích đang có:
  order X = PAID, cell timestamp 200

Nếu merge hợp lệ:
  phiên bản timestamp 200 có thể thắng trên đường đọc.
```

Số 100 và 200 là timestamp so sánh giả định, không phải mốc Unix CQL thực. Khi timestamp trùng, Cassandra còn quy tắc hòa giải khác; không thiết kế đối soát bằng suy luận “file copy sau luôn thắng”.

### Khác biệt giữa “giữ bản mới” và “khôi phục đúng mốc”

Nếu yêu cầu **point-in-time recovery tại T=13:58**, dữ liệu được ghi sau T **không thuộc trạng thái mong muốn** ngay cả khi timestamp lớn hơn. Nạp snapshot cũ vào bảng đang chứa ghi mới không tự hoàn nguyên bảng về trạng thái tại T.

Cần xác định phương án:

- Restore vào **bảng/cluster mới trống** rồi cutover.
- Khôi phục có kiểm soát các mutation theo mốc, với chính sách xử lý bản ghi cũ/mới.
- Dùng ETL/backfill nếu phải chuyển schema, cùng quy tắc idempotent và đối chiếu.

**Bulk import ≠ rollback toàn bảng** và **repair ≠ phục hồi về quá khứ**.

## 13. Đối soát số lượng: vì sao tổng row count có thể đánh lừa?

Một phép đối chiếu “nguồn có 5 triệu hàng, đích có 4,99 triệu” chưa đủ để tuyên bố mất 10.000 hàng, vì:

- Một phần dữ liệu TTL đã hết hạn ở thời điểm kiểm tra.
- Snapshot nguồn và đích ở mốc khác nhau.
- Dữ liệu đã DELETE đúng chính sách.
- Một bảng là projection, có thể chậm cập nhật ở checkpoint.
- Phép đếm có thể thiếu token range hoặc bị timeout.
- Bảng có nhiều row/cell, tổng row count không phản ánh giá trị cột đúng.

### Các metrics nên có định nghĩa rõ

| Metric | Định nghĩa gợi ý | Phải kèm gì? |
| --- | --- | --- |
| **Expected active keys** | Số khóa phải sống theo checkpoint, TTL/delete rule | Manifest + thời điểm kiểm tra |
| **Missing keys** | Khóa expected nhưng không thấy ở query xác minh | Phạm vi sample/toàn bộ, CL, retries |
| **Unexpected keys** | Khóa không được có nhưng đang đọc được | Deleted/expired/source-of-truth |
| **Value mismatch** | Cùng khóa nhưng cột quan trọng khác giá trị kỳ vọng | Chuẩn canonicalization |
| **Projection mismatch** | Bảng theo truy vấn không nhất quán với bản chuẩn theo checkpoint | Watermark hội tụ |
| **Invariant violations** | Vi phạm điều kiện nghiệp vụ đã định nghĩa | Độ nghiêm trọng và tác động |
| **Verified token coverage** | Tỷ lệ ranges/phạm vi đã có bằng chứng kiểm tra thành công | Denominator, source inventory |
| **Reconciliation lag** | Tuổi backlog cần sửa, hoặc chênh mốc watermark | Clock và SLA hội tụ |
| **Performance degradation** | p95/p99/error vượt baseline/SLO sau restore | Tải, CL, RF, DC |

Nếu đã có một tập expected live keys được xác nhận, có thể tính:

```text
Completeness = verified_expected_keys / total_expected_live_keys

Ví dụ: 9.980 / 10.000 = 99,8%
Missing expected keys = 20
```

Con số trên chỉ đúng **trong tập đã được xác minh**. Nếu 10.000 là một *sample*, không công bố “toàn bảng đạt 99,8%” như một sự thật đo trực tiếp; phải nêu rõ là **sample completeness** và khoảng tin cậy/phương pháp sampling nếu dùng ước lượng thống kê.

### Nhìn vào nhóm quan trọng thay vì chỉ tổng

Hai hệ thống cùng thiếu 20 đơn:

- Hệ A thiếu 20 đơn test đã hủy.
- Hệ B thiếu 20 đơn đã thu tiền nhưng chưa giao hàng.

Tỷ lệ thiếu có thể bằng nhau, **rủi ro kinh doanh khác hoàn toàn**. Báo cáo phải phân nhóm theo giá trị/độ nghiêm trọng và bất biến: tiền, quyền truy cập, đơn hàng đang xử lý, dữ liệu đã xóa theo yêu cầu, sự kiện idempotency.

## 14. Đối soát nội dung bằng hash: cần canonicalization

Có thể tính checksum nội dung logic cho một tập partition/bucket để so sánh nhanh, nhưng chỉ khi **hai bên đồng thuận cách biểu diễn dữ liệu**:

- Thứ tự các row được xác định bằng partition/clustering key.
- Kiểu `decimal` cần chuẩn hóa theo quy tắc nghiệp vụ; `250.0` và `250.00` có thể tương đương về số tiền.
- `timestamp` chuẩn hóa timezone và đơn vị chính xác.
- `uuid` được biểu diễn nhất quán.
- `null` phải phân biệt với chuỗi rỗng.
- Map/set cần sắp xếp theo quy tắc ổn định trước khi băm; list giữ thứ tự có ý nghĩa.
- Các cột không nằm trong hợp đồng đối soát không được lẫn vào hash một cách tùy tiện.
- TTL và timestamp cần được tính trong hash nếu hợp đồng đòi **đúng metadata**, không chỉ đúng giá trị CQL hiển thị.

```text
Một bản ghi canonical minh họa:

order_id=11111111-1111-4111-8111-111111111111
customer_id=aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
status=PAID
total_minor_units=25000
created_at_utc=2026-11-21T10:00:00.000Z

SHA-256(canonical_bytes) -> hash để đối chiếu logic
```

Không đồng nhất “trùng hash” với “đã chứng minh toàn bảng đúng” nếu còn thiếu ranges hoặc tập khóa đầu vào. Hash cũng không cho biết trực tiếp cột nào sai; khi phát hiện mismatch, cần drill down tới key/cell.

**Không dùng hash SSTable nguồn đối chiếu trực tiếp hash SSTable đích như tiêu chí logic bắt buộc**: compaction và phân bố replica làm tệp vật lý khác nhau.

## 15. Đối soát qua Java Driver 4.x theo manifest độc lập

Java Driver phù hợp để kiểm tra **truy vấn nghiệp vụ thực** với consistency level và local datacenter mục tiêu. Ví dụ dưới đây dùng một record expected được lấy từ **manifest ngoài cluster**; không tạo expected bằng chính bảng vừa restore.

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class RestoreOrderVerifier {

    public record ExpectedOrder(
        UUID orderId,
        UUID customerId,
        LocalDate orderDay,
        Instant createdAt,
        String status,
        BigDecimal total
    ) {}

    private final CqlSession session;
    private final PreparedStatement byId;
    private final PreparedStatement projection;

    public RestoreOrderVerifier(CqlSession session) {
        this.session = session;
        this.byId = session.prepare(
            "SELECT customer_id, order_day, created_at, status, total " +
            "FROM lab.orders_by_id WHERE order_id = ?"
        );
        this.projection = session.prepare(
            "SELECT status, total FROM lab.orders_by_customer_day " +
            "WHERE customer_id = ? AND order_day = ? " +
            "AND created_at = ? AND order_id = ?"
        );
    }

    private Row one(PreparedStatement query, Object... values) {
        BoundStatement statement = query.bind(values)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(true);
        return session.execute(statement).one();
    }

    public void verify(ExpectedOrder expected) {
        Row canonical = one(byId, expected.orderId());
        if (canonical == null) {
            throw new IllegalStateException(
                "MISSING_CANONICAL " + expected.orderId());
        }

        if (!expected.customerId().equals(
                canonical.getUuid("customer_id")) ||
            !expected.orderDay().equals(
                canonical.getLocalDate("order_day")) ||
            !expected.createdAt().equals(
                canonical.getInstant("created_at")) ||
            !expected.status().equals(
                canonical.getString("status")) ||
            canonical.isNull("total") ||
            expected.total().compareTo(
                canonical.getBigDecimal("total")) != 0) {
            throw new IllegalStateException(
                "CANONICAL_MISMATCH " + expected.orderId());
        }

        Row listItem = one(
            projection,
            expected.customerId(),
            expected.orderDay(),
            expected.createdAt(),
            expected.orderId()
        );

        if (listItem == null ||
            !expected.status().equals(listItem.getString("status")) ||
            listItem.isNull("total") ||
            expected.total().compareTo(
                listItem.getBigDecimal("total")) != 0) {
            throw new IllegalStateException(
                "PROJECTION_MISMATCH " + expected.orderId());
        }
    }
}
```

Đây là ví dụ dành cho **Java 17 hoặc bản hỗ trợ `record`**. Nếu dùng Java cũ, thay `record` bằng class immutable thông thường. Các bảng phải tồn tại với schema ở trên; `CqlSession` cần cấu hình đúng authentication, contact points, local DC và RF đủ cho `LOCAL_QUORUM`.

Chú ý:

- `BigDecimal.compareTo` so sánh giá trị tiền, tránh coi `250.0` khác `250.00` khi domain không yêu cầu scale bằng nhau.
- `Instant`/`LocalDate` phải được tạo theo timezone và quy tắc bucket thống nhất với writer.
- `setIdempotent(true)` phù hợp với các `SELECT` chỉ đọc; không tự bật speculative execution.
- `LOCAL_QUORUM` chỉ kiểm tra quorum trong DC của coordinator; nếu cần xác nhận nhiều DC, phải chạy từ các session/kiểm tra được cấu hình cho từng DC.
- Một method ném exception tại sai lệch đầu tiên phù hợp demo, nhưng batch production cần thu thập **tổng số, nhóm lỗi, key ẩn danh, retry có giới hạn và báo cáo**.
- Không nên log toàn bộ dữ liệu khách hàng, mã định danh bí mật hoặc giá trị thanh toán nhạy cảm.
- Code không tự kiểm tra `payment_events_by_order`; invariant thanh toán cần một bước đọc/check độc lập theo `order_id` và `last_event_id`.

### Khi cần đối soát khóa đã xóa

Manifest phải lưu **tập khóa không được tồn tại**. Kiểm tra theo khóa:

```cql
SELECT order_id, status
FROM lab.orders_by_id
WHERE order_id = 44444444-4444-4444-8444-444444444444;
```

Nếu không trả row, chỉ mới thấy kết quả ở mức CL hiện dùng tại thời điểm đó; chưa chứng minh mọi replica đã nhận tombstone. Nếu có row bất ngờ, dừng cutover của luồng dữ liệu liên quan và điều tra nguồn snapshot/TTL/delete/repair history trước khi xóa lại tùy tiện.

## 16. Kiểm tra đa datacenter và consistency level

Ví dụ keyspace dùng `NetworkTopologyStrategy` RF=3 ở `dc1` và RF=3 ở `dc2`.

Một ứng dụng Java ở dc1 đọc `LOCAL_QUORUM` nhận hai replica dc1 phản hồi. Ứng dụng ở dc2 cũng đọc `LOCAL_QUORUM` nhưng từ tập replica dc2.

**Hai local quorum thuộc hai DC khác nhau không có giao bắt buộc**. Vì vậy dữ liệu mới trong dc1 chưa chắc đã hiện ngay ở dc2 nếu quá trình replication chưa hoàn tất trước checkpoint/restore.

Kịch bản đối soát nên:

1. Kiểm tra schema, RF và datacenter/rack thực tế.
2. Xác nhận những DC thuộc phạm vi restore và checkpoint nào áp dụng cho chúng.
3. Chạy truy vấn nghiệp vụ từ client đặt **local DC đúng** cho mỗi vùng.
4. So giá trị theo manifest và kiểm tra mức sai lệch chéo DC ở những key quan trọng.
5. Kiểm tra repair/streaming history và ranges chưa hoàn tất trước cutover.
6. Ghi rõ CL đã dùng; không coi một SELECT `ONE` đủ bằng chứng các replica đồng nhất.

### Repair không thay thế đối soát nghiệp vụ

Anti-entropy repair đối soát replica chịu trách nhiệm cho cùng token ranges. Nó **không biết** rằng `PAID` phải có event `CAPTURED` trong một bảng khác. Nếu cả ba replica đều chứa một projection sai giống nhau, repair có thể thành công mà bất biến nghiệp vụ vẫn sai.

Ngược lại, nếu ba replica lệch nhau vì mutation chưa đồng bộ, kiểm tra một partition từ một coordinator duy nhất có thể thấy kết quả phụ thuộc CL và replica được chọn. Phải xử lý **cả replica consistency lẫn business consistency**.

## 17. Số liệu sau restore: dashboard phải trả lời được điều gì?

| Nhóm | Metric và cách đo | Ngưỡng quyết định phụ thuộc |
| --- | --- | --- |
| **Phạm vi** | % token ranges đã khôi phục/đối soát theo inventory | Phải bao phủ 100% phạm vi bắt buộc trước cutover |
| **Độ đầy đủ** | Expected live keys, missing keys theo manifest | Mức chấp nhận của nghiệp vụ; dữ liệu tài chính thường nghiêm ngặt |
| **Dữ liệu thừa** | Unexpected/resurrected deleted keys | Chính sách delete, compliance, mức nghiêm trọng |
| **Đúng giá trị** | Value mismatch theo cột/nhóm partition | Hợp đồng canonicalization |
| **Projection** | Mismatch giữa bảng chuẩn và bảng query-first | Watermark, SLA hội tụ |
| **Bất biến** | Số/rate vi phạm INV-01...INV-07 | Chính sách nghiệp vụ và mức rủi ro |
| **RPO thực tế** | Mốc được chứng minh đã phục hồi so với mốc sự cố | RPO cam kết; nếu thiếu bằng chứng báo unknown |
| **RTO thực tế** | Từ lúc gián đoạn đến khi dữ liệu/traffic đạt điều kiện | RTO cam kết |
| **Tài nguyên** | Disk headroom, SSTable count, compaction backlog, CPU/GC | Phục vụ ổn định sau restore |
| **Ứng dụng** | p95/p99, timeout, error rate, throughput theo DC và query | SLO khi canary/ramp-up |
| **Hậu kiểm** | Repair coverage, streaming errors, reconciliation backlog | Không để sai lệch kéo dài sau cutover |

### Ví dụ báo cáo sau restore

```text
Restore ID: restore-lab-2026-11-21-a
Target checkpoint: 13:58 UTC
Source completeness evidence: 100% expected ranges inventoried
Destination coverage: 100% required ranges validated
Expected live keys checked: 10,000 (phạm vi manifest kiểm chứng)
Missing keys: 0
Unexpected deleted keys: 0
Value mismatch: 0
Projection mismatch after watermark: 0
Critical business invariant violations: 0
Restored watermark: 13:58 UTC (có bằng chứng)
Business p99 at canary load: within approved SLO
RPO/RTO: reported with actual incident and cutover timestamps
Status: eligible for go/no-go review
```

Các giá trị chỉ minh họa **mẫu báo cáo**, không phải kết quả cluster thực. Nếu chỉ kiểm tra 10.000 mẫu ngẫu nhiên từ 10 triệu key, báo cáo phải viết **10.000 sampled keys checked**, không ghi “100% dữ liệu đã xác minh”.

## 18. Hiệu năng sau restore: dữ liệu đúng vẫn có thể chưa sẵn sàng

Sau nạp SSTable hoặc rebuild, các node có thể đang:

- Nhận streaming phần còn lại của dữ liệu.
- Compaction nhiều SSTable.
- Repair để đối soát replica.
- Dần làm nóng OS page cache.
- Xử lý lưu lượng phát sinh từ ứng dụng đồng thời.

Một cluster có dữ liệu đúng nhưng disk chưa đủ headroom, compaction queue lớn hoặc GC pause cao vẫn có thể không đạt SLO.

Kiểm tra tại từng node phù hợp:

```bash
nodetool status
nodetool tablestats lab.orders_by_id
nodetool tablestats lab.orders_by_customer_day
nodetool compactionstats
nodetool tpstats
nodetool netstats
```

Theo dõi thêm CPU, disk read/write await, network saturation, JVM GC pause và lượng ổ trống. Có thể dùng CQL tracing cho **mẫu truy vấn**:

```cql
TRACING ON;

SELECT order_id, status, total
FROM lab.orders_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;

TRACING OFF;
```

Tracing có overhead; không bật 100% trên production chỉ để đối soát. `nodetool status` hiển thị `UN` cũng **không chứng minh p99 hay dữ liệu đúng**.

### Phải so cùng workload

So sánh trước/sau restore với:

- Cùng query shape và phân phối partition nóng/lạnh.
- Cùng consistency level, RF, local DC.
- Tải đọc/ghi đủ đại diện, có các workflow chuyển trạng thái đơn.
- Cùng tiêu chí timeout/error và mốc thu thập p95/p99.
- Theo dõi thêm cache warm-up và compaction backlog.

Không tuyên bố “p99 giảm 50% sau restore” nếu workload test ít dữ liệu hơn hoặc CL đã đổi từ `QUORUM` sang `ONE`.

## 19. Các cách sửa sai lệch sau restore và giới hạn của chúng

| Sai lệch | Không nên làm | Phương án có thể phù hợp |
| --- | --- | --- |
| Thiếu một phần token ranges | Giả định node `UN` là đủ | Xác định source/ranges, stream bổ sung từ nguồn tin cậy, kiểm chứng |
| Replica lệch nhau | Chạy full repair toàn cụm không kế hoạch | Đánh giá repair đúng phạm vi, an toàn tombstone và version |
| Bảng projection thiếu nhưng bảng chuẩn đúng | Mong repair tự tái tạo projection chưa từng ghi | Backfill/rebuild projection **từ nguồn chuẩn** có checkpoint |
| Đơn `PAID` không có event thanh toán | Tự chèn event giả để làm report đẹp | So ledger độc lập, xác định giao dịch thật và xử lý nghiệp vụ |
| Bản ghi đã xóa xuất hiện lại | Xóa ồ ạt không phân tích | Điều tra tombstone/replica/history, sửa có kiểm soát |
| Snapshot thiếu mutation sau checkpoint | Tuyên bố RPO=0 | Dùng log/CDC có thể chứng minh hoặc công bố mức mất dữ liệu |
| Dữ liệu đúng nhưng p99 cao | Chỉ tăng driver timeout | Xem compaction, cache, disk, CPU, query và tải |
| Cột kiểu mới bị decode sai | Rename SSTable file để ép nạp | Chuyển đổi schema/dữ liệu bằng ETL tương thích |

### Không sửa lỗi ở phạm vi sai

- **Replica repair:** đối soát bản sao của cùng partition; không tự phát hiện invariants xuyên bảng.
- **Backfill projection:** xây lại bảng theo truy vấn từ nguồn chuẩn; có thể tốn write và phải dùng idempotency.
- **Replay event/CDC:** tái áp dụng mutation bị thiếu nếu log thực sự đầy đủ và replay an toàn.
- **Khôi phục backup khác:** cần khi nguồn đã thiếu dữ liệu hoặc snapshot bị hỏng; không thể tạo bản ghi từ byte không tồn tại.
- **Sửa nghiệp vụ:** phải theo quy trình có audit trail, không chỉ vì một kết quả test CQL không khớp.

Mỗi thao tác sửa cần lưu **nguồn bằng chứng, key/range ảnh hưởng, mốc thời gian, kiểm tra trước và sau**.

## 20. Rủi ro riêng của counter, LWT, index và CDC

### Counter

Cassandra counter có ngữ nghĩa mutation khác số nguyên thông thường; duplicate/replay hoặc restore không đúng quy trình có thể làm giá trị sai. Không coi “nạp lại cùng counter delta” là idempotent. Nếu hệ thống có số dư/counter nghiệp vụ, đối soát với ledger nguồn và dùng runbook migration/restore theo version được hỗ trợ.

### LWT và trạng thái đồng thuận

Nếu đơn nghiệp vụ dùng `IF` hoặc `INSERT ... IF NOT EXISTS`, dữ liệu bảng và trạng thái liên quan đến giao thức đồng thuận có thể có các điều kiện khôi phục riêng. Không biến một SSTable restore thành bảo đảm rằng mọi giao dịch compare-and-set trước đó đã được tuần tự hóa trên cluster mới. Cần thiết kế cutover, chống hai nơi cùng nhận ghi và khôi phục invariant từ nguồn sự thật.

### Secondary index, SAI và materialized view

Kiểm tra riêng các đường truy vấn dựa trên secondary index, Storage-Attached Index hoặc materialized view nếu hệ dùng chúng. Một SELECT theo primary key trả đúng không chứng minh mọi index/view đã xây và đồng bộ. Hành vi rebuild/index backfill tùy release; phải có bước validation tương ứng.

### CDC và hệ thống bên ngoài

Bulk restore/streaming SSTable không mặc nhiên phát sinh lại mọi **event CDC** như một chuỗi ghi CQL thông thường. Nếu các downstream services cần nhận events đã mất, phải dùng một **kế hoạch replay/backfill có event ID và deduplication**, đảm bảo không trùng tác dụng (ví dụ thu tiền lần thứ hai).

Một sự kiện đã có trong SSTable **không đồng nghĩa** consumer ở hệ khác đã xử lý nó. Đối soát downstream là một phần của hợp đồng phục hồi end-to-end.

## 21. Kiểm soát cutover và chống ghi đồng thời

Một lỗi phổ biến là cluster nguồn và cluster khôi phục **cùng được phép nhận ghi** trước khi đã chọn rõ source of truth. Với Cassandra last-write-wins, việc hòa giải timestamp không phải thuật toán tự động giải quyết xung đột nghiệp vụ.

Trước khi chuyển traffic:

1. Xác định hệ nào được nhận ghi; chặn split-brain hoặc dual-writer ngoài thiết kế.
2. Chốt checkpoint/watermark cần phục hồi.
3. Hoàn tất nhập dữ liệu và xử lý log replay theo thứ tự/định danh hợp lệ.
4. Đối soát invariants quan trọng và các projection đến watermark.
5. Chạy canary đọc/ghi có giới hạn với Java Driver local DC/CL phù hợp.
6. Theo dõi p99, error rate, repair/streaming và dữ liệu mới sau cutover.
7. Có rollback/quay lại nguồn cũ được đánh giá **về dữ liệu ghi sau cutover**, không đơn thuần đổi DNS.

Nếu có ghi mới tại cluster khôi phục sau cutover, rollback về cluster cũ có thể **làm mất ghi mới** nếu không có chiến lược ghi đồng bộ/replay. Đây cũng là vấn đề RPO cần báo cáo minh bạch.

## 22. Runbook đối soát theo từng giai đoạn

### Giai đoạn A — Chốt phạm vi và nguồn

1. Ghi mốc sự cố, checkpoint, mục tiêu RPO/RTO và phạm vi dịch vụ.
2. Thu thập schema/version/partitioner/RF/DC, snapshot và log/CDC inventory.
3. Xác nhận source có đủ token ranges; lưu checksums và nguồn backup bất biến.
4. Đặt hợp đồng expected live/deleted keys cùng TTL/timestamp semantics.
5. Thống nhất các bất biến nghiệp vụ và mức nghiêm trọng được phép/chặn cutover.

### Giai đoạn B — Restore và kiểm tra kỹ thuật

6. Khôi phục schema và dữ liệu theo runbook version-specific; không thay primary key tùy tiện.
7. Xác minh streaming/restore thành công theo từng node/range, không chỉ process exit code.
8. Kiểm tra node health, disk/compaction, RF/DC và dữ liệu có thể truy vấn.
9. Ghi log các phạm vi bị lỗi, retry và những replica chưa có bằng chứng hoàn tất.

### Giai đoạn C — Đối soát dữ liệu và nghiệp vụ

10. Đối chiếu key/partition theo manifest độc lập; kiểm tra mọi range bắt buộc.
11. So giá trị, metadata TTL/WRITETIME và tập deleted keys.
12. Kiểm tra projection theo checkpoint/watermark và SLA hội tụ.
13. Chạy bộ INV-01…INV-07; phân loại critical vs noncritical.
14. Xử lý sai lệch bằng nguồn tin cậy, backfill/replay/repair phù hợp rồi kiểm tra lại.
15. Báo cáo RPO có căn cứ; nếu thiếu nguồn độc lập, công khai giới hạn bằng chứng.

### Giai đoạn D — Go/no-go và hậu kiểm

16. Canary Java/CQL theo local DC/CL dự kiến; đo p95/p99 và timeout với tải thật.
17. Xác minh không còn blocker về dữ liệu tài chính, delete, security và source coverage.
18. Quyết định go/no-go bằng người chịu trách nhiệm nghiệp vụ và vận hành.
19. Mở traffic từng đợt, tiếp tục đo invariant violations và reconciliation backlog.
20. Lưu báo cáo RTO thực tế, bằng chứng, sai lệch còn lại, kế hoạch hậu kiểm và rollback.

### Ví dụ tiêu chí go/no-go

| Hạng mục | Go khi | No-go khi |
| --- | --- | --- |
| Backup/source | Phạm vi token bắt buộc có nguồn tin cậy | Có gap không giải thích được |
| Data correctness | Khóa/giá trị critical đúng theo manifest | Thiếu đơn thanh toán hoặc hồi sinh delete critical |
| Invariants | Không có vi phạm nghiêm trọng chưa giải quyết | `PAID` không có payment evidence theo hợp đồng demo |
| Projection | Hội tụ tới watermark/đạt SLA được duyệt | Mismatch vượt cửa sổ hội tụ |
| RPO | Được đo và nằm trong mức được chấp thuận | RPO vượt cam kết hoặc không biết nhưng vẫn tuyên bố đạt |
| RTO/service | Canary đạt SLO và đường cutover khả dụng | p99/error vượt ngưỡng, compaction/disk mất kiểm soát |
| Recovery plan | Có rollback và quản lý ghi mới rõ ràng | Nguồn/đích cùng ghi không kiểm soát |

Không có ngưỡng universal cho mọi ngành; điều kiện phải được ký duyệt theo rủi ro nghiệp vụ và yêu cầu pháp lý tương ứng.

## 23. Các tình huống chẩn đoán sau restore

### A — Snapshot hợp lệ nhưng thiếu đơn hàng trước checkpoint

**Dấu hiệu:** file hash đúng, nhưng một số `order_id` trong manifest độc lập không đọc thấy.

**Kiểm tra:** token range coverage, node nguồn có snapshot không, CL của ghi gốc, mutation chưa flush/tồn tại trong commit log, và mức replay khả dụng.

**Xử lý:** bổ sung nguồn hoặc replay hợp lệ nếu có; không dùng COUNT(*) tổng để che lỗ hổng ở một số range.

### B — Projection danh sách thiếu dù bảng chuẩn đủ

**Dấu hiệu:** `orders_by_id` có hàng, `orders_by_customer_day` không có.

**Kiểm tra:** luồng update projection, snapshot timing, consumer watermark và lỗi ghi nhiều bảng.

**Xử lý:** backfill projection từ bảng chuẩn theo checkpoint; dùng logic idempotent và xác minh lại. Repair giữa replica của bảng projection không thể tạo mutation chưa từng xảy ra.

### C — Deleted row xuất hiện trở lại

**Dấu hiệu:** đơn trong manifest “đã xóa” nhưng sau restore có giá trị cũ.

**Kiểm tra:** snapshot source stale, tombstone, `gc_grace_seconds`, replica offline và thời điểm xóa.

**Xử lý:** tạm ngừng cutover cho phạm vi affected; xác định nguồn truth rồi tái lập delete/khôi phục với quy trình có audit trail.

### D — TTL record bị báo thiếu sau restore dài ngày

**Dấu hiệu:** một lượng lớn dữ liệu ngắn hạn không xuất hiện; pipeline đối soát báo “missing”.

**Kiểm tra:** expected set có lọc TTL theo thời điểm kiểm tra chưa? Restore có bảo lưu expiry metadata không? Data có thực sự thuộc loại phải lưu trữ lâu dài?

**Xử lý:** sửa phép đo theo mốc TTL; không kéo dài TTL tùy tiện để khiến test xanh.

### E — RPO tính từ thời điểm snapshot nhưng thực tế mất nhiều hơn

**Dấu hiệu:** snapshot chụp 13:50, một số event đã ACK trước đó lại thiếu.

**Kiểm tra:** snapshot chỉ lấy một replica, chưa flush đủ, node offline, CL, log backup và token coverage.

**Xử lý:** đánh giá lại checkpoint có bằng chứng và nguồn bổ sung; không lấy “timestamp snapshot gần sự cố” làm RPO chính xác khi coverage chưa đủ.

### F — Restore xong, dữ liệu đúng nhưng API timeout

**Dấu hiệu:** canary p99 tăng, `tpstats` pending, disk await và compaction backlog cao.

**Kiểm tra:** số SSTable sau load, streaming/repair nền, GC/CPU, CL và route coordinator.

**Xử lý:** điều tiết công việc nền/khả năng lưu trữ, đo lại; không mở traffic toàn bộ chỉ vì dữ liệu đúng.

### G — Hai DC đọc cùng khóa nhưng ra hai trạng thái khác

**Dấu hiệu:** `LOCAL_QUORUM` dc1 đọc `PAID`, dc2 đọc `PENDING`.

**Kiểm tra:** checkpoint riêng từng DC, replication lag, stream/repair coverage và source-of-truth timestamp.

**Xử lý:** xác minh giá trị đúng từ ledger, điều phối repair/khôi phục phù hợp, không chỉ nâng timeout driver.

### H — Hash SSTable khác sau compaction

**Dấu hiệu:** hash file đích khác hash nguồn dù SELECT các key mẫu khớp.

**Giải thích:** compaction, cách đóng gói SSTable, compression và metadata có thể khác. Đừng kết luận mất dữ liệu từ file hash khác trong một pipeline tạo lại cấu trúc vật lý.

**Xử lý:** dùng logical row/cell compare và token coverage, giữ file hash để xác minh bản copy nguồn.

## 24. Những ngộ nhận cần tránh

**“`nodetool status` báo `UN` thì restore hoàn chỉnh.”** Sai. Membership/gossip không chứng minh dữ liệu đúng hoặc đầy đủ.

**“`sstableloader` kết thúc thành công là đã phục hồi toàn bộ hệ thống.”** Sai. Nó chỉ xử lý phạm vi tệp đã cung cấp; source có thể thiếu token ranges hoặc mutation.

**“Snapshot của một node là snapshot nguyên tử toàn cluster.”** Sai. Node chỉ chứa phạm vi replica của nó và thời điểm chụp riêng.

**“RPO bằng khoảng cách giữa sự cố và timestamp file backup.”** Không đủ. Cần xác nhận các mutation đã được ACK và nguồn có đủ dữ liệu tới mốc.

**“RTO kết thúc lúc streaming đạt 100%.”** Sai. Dịch vụ phải đạt các tiêu chí dữ liệu và SLO đã định nghĩa.

**“Dữ liệu TTL không xuất hiện nghĩa là restore bị lỗi.”** Chưa chắc. Có thể đã hết hạn đúng chính sách.

**“Timestamp file import mới nhất sẽ thắng mọi giá trị đích.”** Sai. Cassandra hòa giải theo timestamp mutation/tombstone semantics, không theo giờ copy file.

**“Repair giải quyết mọi mismatch giữa các bảng denormalized.”** Sai. Repair đối soát replica của cùng dữ liệu, không dựng projection nghiệp vụ thiếu mutation.

**“Hai lần đọc `LOCAL_QUORUM` ở hai DC luôn cùng kết quả ngay lập tức.”** Không có giao quorum bắt buộc giữa hai local DC.

**“Đếm đúng tổng số row nghĩa là dữ liệu chính xác.”** Sai. Có thể thiếu khóa A và dư khóa B, hoặc sai giá trị/timestamp/delete.

**“Hash của SSTable nguồn và đích phải giống nhau.”** Sai nếu quá trình tạo lại SSTable/compaction thay đổi biểu diễn vật lý.

**“Hash vài partition mẫu khớp chứng minh 100% dữ liệu đã phục hồi.”** Sai. Sample chỉ chứng minh tập đã kiểm tra; cần coverage riêng.

**“`PAID` nhưng thiếu event thanh toán thì có thể tạo event giả.”** Sai. Phải xác minh ledger và xử lý theo quy trình nghiệp vụ, có audit trail.

**“Rollback chỉ là đổi DNS về cluster cũ.”** Sai. Ghi mới sau cutover có thể mất nếu không có cách replay/đồng bộ.

## 25. Bài tập và câu hỏi phỏng vấn

1. Vì sao restore thành công về file/SSTable chưa chứng minh bất biến nghiệp vụ đúng?
2. Phân biệt `T_snapshot`, `T_restore_target` và thời gian sự kiện nghiệp vụ.
3. Snapshot trên một node RF=3 có bao phủ toàn keyspace không? Phải kiểm tra gì?
4. Trong ví dụ, snapshot lúc 13:45, log replay chứng minh tới 13:58, sự cố 14:00. Có đủ cơ sở công bố RPO=2 phút chưa nếu một token range thiếu backup? Vì sao?
5. Tại sao phải có manifest/ledger độc lập, thay vì sinh expected key từ chính bảng restore?
6. Giải thích vì sao tổng row count bằng nhau không chứng minh giá trị/khóa chính xác.
7. Dữ liệu dùng TTL 7 ngày được restore sau 10 ngày. Có được coi là missing không? Phụ thuộc gì?
8. Vì sao row đã `DELETE` trước checkpoint có thể sống lại khi trộn replica stale?
9. `gc_grace_seconds` và repair giúp gì trong bảo vệ tombstone? Trường hợp nào repair trễ không đủ?
10. Một bảng `orders_by_id` đúng nhưng bảng projection theo customer thiếu. Repair có tự dựng lại không? Hướng sửa?
11. Theo mô hình demo, kiểm tra `PAID` có payment `CAPTURED` như thế nào bằng CQL?
12. Khi hệ có refund/partial capture, bất biến “amount capture = total order” phải thay đổi ra sao?
13. Vì sao `BigDecimal.compareTo` hữu ích khi so giá trị tiền từ hai nguồn?
14. Khi tính hash logic, cần chuẩn hóa timestamp, null, collections và thứ tự row thế nào?
15. `LOCAL_QUORUM` dc1 và `LOCAL_QUORUM` dc2 có giao replica bắt buộc không?
16. Làm thế nào để đặt mục tiêu hội tụ projection mà không báo sai lệch tạm thời thành lỗi restore?
17. Một canary đọc ra đúng dữ liệu nhưng read p99 vượt SLO. Có được mở traffic toàn bộ không?
18. Vì sao `COUNT(*)` toàn bảng vừa tốn tài nguyên vừa không thay thế manifest coverage?
19. Counter, LWT, SAI/materialized view và CDC cần kiểm chứng gì riêng sau restore?
20. Nếu chỉ kiểm tra 10.000 partition mẫu từ 10 triệu partition, báo cáo completeness phải diễn đạt thế nào?
21. Nêu điểm khác nhau giữa *RPO mục tiêu*, *RPO có bằng chứng* và *RTO thực tế*.
22. Trong trường hợp cluster nguồn và đích cùng nhận ghi sau cutover, những rủi ro consistency nào xuất hiện?
23. Nếu thấy đơn đã xóa xuất hiện lại, tại sao không nên tự chạy DELETE cho hàng triệu khóa ngay mà chưa điều tra?
24. Thiết kế bảng metric sau restore: coverage, missing, unexpected, projection mismatch, invariant violation, p99, RPO/RTO.
25. Đưa ra ba điều kiện **no-go** không thể bỏ qua cho một hệ thống thanh toán giả định.

## 26. Sơ đồ quyết định cuối bài

```text
        RESTORE FILE / STREAM / REBUILD BÁO HOÀN TẤT
                           |
                           v
          Source/manifest đủ token ranges không?
                    |               |
                   Không            Có
                    |               |
             Khôi phục bổ sung       v
             hoặc báo gap       Checkpoint và RPO có bằng chứng?
                                    |             |
                                   Không          Có
                                    |             |
                              Nêu giới hạn        v
                              và điều tra     Đối soát keys/values/
                                              TTL/delete/timestamp
                                                  |
                                         +--------+---------+
                                         |                  |
                                       Sai                 Đúng
                                         |                  |
                                    Sửa có kiểm soát        v
                                         |           Check projection +
                                         |           invariants theo mốc
                                         |                  |
                                         +-------+----------+
                                                 |
                                             Đạt không?
                                          +------+------+
                                          |             |
                                         Không          Có
                                          |             |
                                   No-go / repair      Canary Java
                                   / backfill          CL, DC, p99
                                                        |
                                                  SLO đạt không?
                                                    |        |
                                                   Không     Có
                                                    |        |
                                                  No-go      v
                                                      Go/no-go review,
                                                      staged cutover,
                                                      theo dõi sau restore
```

**Ghi nhớ:** **Restore là việc đưa dữ liệu trở lại; recovery chỉ hoàn tất khi dữ liệu đó đúng, đủ, nhất quán theo hợp đồng và phục vụ được nghiệp vụ.** Cassandra cho phép nhiều replica, nhiều SSTable và các bảng thiết kế theo truy vấn, vì vậy phải đối soát **token range, partition key, timestamp, TTL, tombstone, projection và invariant**. Hãy đo **RPO có bằng chứng, RTO tính đến dịch vụ hoạt động trở lại, lỗi dữ liệu nghiêm trọng và p95/p99 sau restore**. Thành công không phải một dòng “stream completed”, mà là quyết định mở traffic dựa trên bằng chứng đầy đủ và có thể kiểm toán.
