# Đối soát trạng thái giữa hệ thống nguồn và hệ thống đích

## 1. Vì sao cần đối soát khi đã có cơ chế đồng bộ?

Trong một hệ thống Spring Boot tích hợp qua HTTP client, database, cache, broker thông điệp và Spring Integration adapter, dữ liệu thường được sao chép hoặc biến đổi từ **hệ thống nguồn** sang **hệ thống đích**. Ví dụ:

- Dịch vụ đơn hàng ghi đơn vào database giao dịch và phát sự kiện **OrderChanged**.
- Một consumer cập nhật bảng truy vấn **order_projection** ở dịch vụ báo cáo.
- Cache Redis giữ bản tóm tắt trạng thái đơn hàng.
- Một adapter gọi HTTP sang hệ thống vận chuyển để đồng bộ đơn cần giao.

Ngay cả khi từng thành phần hoạt động bình thường, trạng thái hai bên có thể lệch do sự kiện bị giữ trong hàng đợi, retry chưa hoàn tất, consumer lỗi, ghi đè bởi thông điệp cũ, mapper sai, thay đổi schema hoặc xóa dữ liệu không được chuyển thành sự kiện tương ứng.

**Đối soát (reconciliation)** là quá trình thu thập bằng chứng từ nguồn và đích, so sánh theo cùng một hợp đồng dữ liệu và mốc quan sát, phân loại sai lệch, rồi xác minh hoặc thực hiện sửa chữa theo chính sách có kiểm soát.

Đối soát không đơn giản là chạy **COUNT(*)** trên hai bảng. Hai hệ thống có thể có số dòng bằng nhau nhưng sai một đơn hàng, sai số tiền hoặc khác trạng thái. Ngược lại, một bên ít dòng hơn trong vài giây có thể chỉ là độ trễ đồng bộ bình thường.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Xác định hệ thống có thẩm quyền và hợp đồng so sánh cho từng trường dữ liệu.
2. Chọn mốc nhất quán, khóa nghiệp vụ, version/sequence, tombstone và cách xử lý độ trễ.
3. Phát hiện **thiếu, thừa, chậm, xung đột, sai nội dung** bằng SQL hoặc đối soát phân trang.
4. Thiết kế job Spring Boot có thể chạy lại, tiếp tục từ checkpoint và ghi bằng chứng đối soát.
5. Chọn sửa tự động, phát lại sự kiện, bù trừ hoặc chuyển điều tra dựa trên rủi ro nghiệp vụ.
6. Kiểm thử và quan sát để chứng minh dữ liệu sau sửa đúng với nguồn có thẩm quyền.

Chủ đề này thuộc phần **Nhất quán và chống trùng** của module **SPRING_BOOT_INTEGRATION**: nhất quán cuối cùng và idempotency giúp giảm sai lệch, còn đối soát phát hiện và xử lý những sai lệch vẫn tồn tại sau các lần giao dịch, retry và phục hồi.

## 2. Trước khi so sánh: định nghĩa trạng thái nào phải nhất quán

Giả sử hệ thống nguồn lưu đơn hàng:

~~~text
orderId       = 1042
sourceVersion = 18
status        = CONFIRMED
totalMinor    = 125000
deleted       = false
~~~

Hệ thống đích có thể lưu thêm **updated_at**, **last_synced_at**, tên khách hàng đã chuẩn hóa hoặc một trường phục vụ hiển thị. Không phải mọi cột đều phải bằng nhau. Cần định nghĩa **hợp đồng projection**: dữ liệu đích phải tương ứng với nguồn theo những trường nào, ở version nào và qua phép biến đổi nào.

### 2.1. Chọn nguồn có thẩm quyền

**Source of truth** có thể được quyết định theo thực thể hoặc theo trường:

| Dữ liệu | Nguồn có thẩm quyền ví dụ | Vai trò của hệ thống đích |
| --- | --- | --- |
| Trạng thái và tổng tiền đơn hàng | Order service | Lưu read model để báo cáo và tra cứu. |
| Số dư đã ghi sổ | Ledger/payment service | Hiển thị số dư; không tự tính lại theo sự kiện thiếu. |
| Mã vận đơn từ đối tác | Carrier API | Lưu bản sao để theo dõi giao hàng. |
| Nhóm quyền người dùng | Directory/LDAP theo chính sách tổ chức | Cache có TTL, không mặc nhiên là nguồn quyết định quyền cuối cùng. |
| Ghi chú chỉnh sửa trong hệ thống đích | Chính hệ thống đích | Không để quá trình đồng bộ từ nguồn ghi đè trường đích sở hữu. |

Nếu hai bên đều được phép sửa **cùng một trường**, không thể chỉ dùng quy tắc “nguồn thắng” cho mọi trường hợp. Cần cơ chế ownership, quy tắc giải quyết xung đột, phiên bản hoặc một quy trình hòa giải nghiệp vụ rõ ràng.

### 2.2. Khóa định danh phải ổn định

Đối soát cần một khóa duy nhất theo hợp đồng, chẳng hạn **(tenantId, orderId)**. Không dựa vào thứ tự dòng, vị trí trong trang API hoặc tên hiển thị.

Tách ba loại khóa:

- **Business key:** xác định thực thể, ví dụ **(tenantId, orderId)**.
- **Event ID:** xác định một lần phát sự kiện cụ thể để chống xử lý lại, ví dụ **eventId=evt-9120**.
- **Source version/sequence:** thể hiện thứ tự thay đổi của thực thể, ví dụ **sourceVersion=18**.

Hai sự kiện khác eventId vẫn có thể áp dụng lên cùng orderId; eventId không thay thế version. Khi nhiều tenant có cùng orderId, phải giữ tenantId trong khóa của cả nguồn, đích, nhật ký và phép đối soát.

### 2.3. Hợp đồng biểu diễn dữ liệu

Chuẩn hóa trước khi so sánh:

- **Số tiền:** dùng số nguyên đơn vị nhỏ nhất cùng currency, không so sánh số thực dấu phẩy động.
- **Thời gian:** quy ước múi giờ, độ chính xác và ý nghĩa của timestamp. **updated_at** do hai máy khác nhau tạo ra thường không phải thước đo version đáng tin.
- **Chuỗi:** có quy tắc phân biệt hoa/thường, khoảng trắng, Unicode normalization; chỉ chuẩn hóa nếu nghiệp vụ cho phép.
- **Null/absent:** phân biệt trường null, trường không gửi, giá trị rỗng và giá trị mặc định nếu contract có ý nghĩa khác nhau.
- **Collections:** xác định danh sách có cần đúng thứ tự hay là tập không thứ tự; không băm JSON tùy ý khi hai hệ thống serialize khác nhau.
- **Deletion:** dùng sự kiện xóa hoặc **tombstone** với version để đích không tự hồi sinh bản ghi đã xóa vì nhận lại một sự kiện cũ.

Khi so sánh bằng **content hash**, hai phía phải dùng **cùng một phép canonicalization** và cùng tập trường nghiệp vụ. Hash không giải quyết được khác biệt về contract, version hoặc nguồn có thẩm quyền.

## 3. Phân biệt sai lệch thật với độ trễ đồng bộ

Trong hệ thống **eventually consistent**, tại cùng thời điểm đồng hồ, trạng thái đích có thể tạm chậm hơn nguồn:

~~~mermaid
sequenceDiagram
    participant S as Database nguồn
    participant O as Outbox/Broker
    participant D as Database đích
    participant R as Job đối soát
    S->>S: Commit order 1042 version 18
    S->>O: Publish OrderChanged v18
    R->>S: Đọc nguồn v18
    R->>D: Đọc đích v17
    Note over R: Chênh lệch tạm thời, cần xét lag/watermark
    O->>D: Consumer áp dụng v18
    R->>D: Kiểm tra lại -> MATCH
~~~

Nếu job đối soát tức thì phát lệnh sửa cho mọi trường hợp **v17 ≠ v18**, nó có thể tạo tải thừa hoặc tranh chấp với consumer vẫn đang chạy đúng.

Đặt một **consistency window** hoặc **grace period** phù hợp với SLA của luồng và dùng bằng chứng tiến độ:

- **Watermark/offset:** consumer đã xử lý an toàn đến đâu trong stream nguồn.
- **Version theo thực thể:** đích đã áp dụng version mới nhất nào của từng entity.
- **Tuổi sai lệch:** sai lệch đã tồn tại bao lâu kể từ khi nguồn có thay đổi và đến lúc nguồn phát/đích nhận.
- **Backlog/DLQ:** event còn trên broker, đang retry hay đã bị cách ly vì lỗi.

**Không mặc định** timestamp của nguồn và đích so sánh được nếu đồng hồ, timezone hoặc định nghĩa mốc khác nhau. Nên ưu tiên monotonic sequence/offset do hệ thống phát sinh và trace từ event đã commit.

### 3.1. Mốc chụp dữ liệu phải so sánh được

Lấy snapshot nguồn lúc **T1** rồi đọc đích lúc **T2** mà không xét các thay đổi giữa T1–T2 có thể cho kết quả sai. Có ba chiến lược:

| Chiến lược | Cách dùng | Điều kiện/giới hạn |
| --- | --- | --- |
| **Đóng băng hoặc snapshot nhất quán** | Dùng snapshot database/read replica hay export theo một mốc xác định. | Cần biết phạm vi snapshot và hạn chế ảnh hưởng production; hai hệ thống riêng biệt thường không có transaction snapshot chung. |
| **Watermark stream** | Chọn mốc nguồn, chờ consumer áp dụng hết sự kiện đến mốc đó, rồi so sánh dữ liệu tương ứng. | Cần theo dõi offset theo partition và xử lý sự kiện đến trễ; một watermark toàn cục giả tạo có thể che lỗ hổng. |
| **So sánh version theo entity** | Đọc sourceVersion của cả hai, phân biệt đích chậm với cùng version nhưng nội dung khác. | Nếu dữ liệu thay đổi trong lúc quét, cần đọc lại/kiểm chứng hoặc lưu bản chụp; version phải có ý nghĩa rõ. |

Với nhiều partition, **consumer offset đã commit** không tự chứng minh mọi tác động downstream cũng đã được commit; ACK/offset phải gắn đúng với việc xử lý bền vững. Một source sequence không nhất thiết tăng liên tục toàn cục nếu nó chỉ tăng **trong từng entity**.

### 3.2. Ma trận phân loại kết quả

| Trạng thái so sánh | Ý nghĩa có thể có | Quyết định bước đầu |
| --- | --- | --- |
| **MATCH** | Cùng key, cùng version, nội dung theo contract bằng nhau. | Ghi nhận thành công. |
| **SOURCE_ONLY** | Nguồn có entry, đích chưa có. | Kiểm tra backlog, phạm vi snapshot và grace period; có thể cần tạo lại projection. |
| **DEST_ONLY** | Đích có entry nhưng nguồn không có trong phạm vi chụp. | Kiểm tra tombstone, tenant, filter, retention và dữ liệu mới phát sinh; không tự xóa ngay. |
| **DEST_BEHIND** | Đích có sourceVersion thấp hơn nguồn. | Thường là đồng bộ chậm; quá SLA thì điều tra event mất/kẹt. |
| **DEST_AHEAD** | Đích có sourceVersion cao hơn snapshot nguồn. | Có thể là dữ liệu mới hơn hoặc sai nguồn; đọc lại với mốc nhất quán trước khi quyết định. |
| **CONTENT_MISMATCH** | Cùng version nhưng khác giá trị nghiệp vụ. | Khả năng mapping sai, sửa ngoài luồng hoặc dữ liệu hỏng; điều tra/repair có điều kiện. |
| **INCOMPARABLE** | Thiếu version, mapping không tương thích, có nhiều nguồn cùng sửa hoặc snapshot không đủ. | Dừng sửa tự động; thu thập thêm bằng chứng. |

Tình huống **DEST_ONLY** còn có thể xuất hiện do source API đã lọc bản ghi xóa, trong khi đích giữ tombstone. Vì vậy cần định nghĩa chính sách xóa trước khi phân loại là lỗi.

## 4. Các hình thức đối soát

### 4.1. Full reconciliation

Quét toàn bộ tập dữ liệu thuộc phạm vi được quy định, so sánh theo khóa ổn định. Phù hợp với đối soát hàng ngày/tuần, sau sự cố lớn, sau thay đổi mapping hoặc khi kiểm tra không bỏ sót event nào.

Ưu điểm: phát hiện cả trường hợp hệ thống không có event để báo rằng một dòng bị thiếu. Hạn chế: tốn I/O, thời gian và băng thông; cần phân trang, snapshot/watermark, giới hạn tải và cách tiếp tục sau lỗi.

**Đừng dùng OFFSET/LIMIT trên dữ liệu liên tục bị thêm/xóa mà không có snapshot** nếu yêu cầu quét chính xác. Phân trang theo khóa ổn định (keyset pagination) hoặc theo snapshot đã chốt để giảm nguy cơ bỏ qua/lặp hàng:

~~~sql
SELECT order_id, source_version, status, total_minor, deleted
FROM orders
WHERE order_id > :lastOrderId
ORDER BY order_id
LIMIT :batchSize;
~~~

Đây là minh họa cho một tập dữ liệu **đã được cố định theo mốc**; nếu bản ghi đang thay đổi trong lúc quét, keyset chỉ bảo đảm thứ tự phân trang, không tự tạo snapshot nhất quán. Với khóa tổng hợp, dùng so sánh tuple phù hợp database hoặc cursor nhiều thành phần.

### 4.2. Incremental reconciliation

Chỉ xét những bản ghi thay đổi từ một checkpoint đáng tin, ví dụ:

- CDC/transaction log từ nguồn.
- Bảng outbox với sequence và trạng thái phát.
- API cấp danh sách thay đổi theo cursor + version.
- Bản ghi **updated_at** nếu contract có đảm bảo về thời gian và không bỏ mất cập nhật.

Incremental quét nhanh nhưng có thể bỏ lỡ **delete không phát tombstone**, thay đổi ngoài CDC scope, sự kiện mất do retention hoặc sai cursor. Thực tế thường kết hợp **incremental thường xuyên + full reconciliation định kỳ**.

Không chỉ dùng điều kiện **updated_at > lastRunTime** nếu việc commit, precision timestamp và cùng timestamp của nhiều hàng chưa được giải quyết. Có thể bỏ qua hàng cập nhật đúng bằng mốc. Dùng cursor theo **(updated_at, id)** và overlap window có dedup nếu không có sequence mạnh hơn; vẫn phải xét clock skew và thay đổi đến trễ.

### 4.3. Đối soát theo hash, tổng hợp hoặc theo nghiệp vụ

Để tiết kiệm băng thông, có thể trước hết so sánh **COUNT**, tổng số tiền, min/max version hoặc hash của từng partition. Những cách này chỉ giúp phát hiện hoặc khoanh vùng chênh lệch:

- Cùng số lượng không chứng minh cùng key hoặc cùng nội dung.
- Tổng tiền giống nhau có thể do hai sai lệch bù trừ.
- Hash cần canonicalization nhất quán, cùng phạm vi và đúng version.
- Đối soát tài chính cần theo quy tắc ledger/double-entry, không chỉ theo trạng thái bảng projection.

Khi phát hiện partition bất thường, chạy **row-level diff** theo khóa và version. Không dùng hash làm lý do tự động ghi đè khi chưa hiểu khác biệt.

## 5. Ví dụ đối soát một projection đơn hàng

Giả sử nguồn **Order Service** là chủ sở hữu của trạng thái đơn và giá tiền. Đích **Reporting Service** duy trì read model:

~~~text
Source (Order Service)                 Target (Reporting Service)
order_id  version  status  total       order_id  version  status  total
101       5        PAID     50000      101       5        PAID     50000
102       7        SHIPPED 120000      102       6        PAID    120000
103       3        NEW      30000      (missing)
104       9        PAID     90000      104       9        NEW      90000
                                      105       2        PAID     70000
~~~

Với điều kiện hai tập đã chuẩn hóa và cùng mốc:

- **101:** MATCH.
- **102:** DEST_BEHIND; kiểm tra độ trễ/sự kiện version 7.
- **103:** SOURCE_ONLY; kiểm tra sự kiện tạo bản ghi chưa tới.
- **104:** CONTENT_MISMATCH cùng version; có thể do mapping sai hoặc thay đổi ngoài luồng.
- **105:** DEST_ONLY; điều tra vì sao nguồn không có record hoặc tombstone.

### 5.1. Chuẩn hóa dữ liệu thành hai snapshot staging

Nếu hai database độc lập, **không thể JOIN trực tiếp chỉ vì cùng chạy Spring Boot**. Job đối soát cần đọc qua API/connection được phép và đưa dữ liệu về vùng staging có kiểm soát, hoặc so sánh streaming theo key ở tầng ứng dụng.

Ví dụ PostgreSQL staging dùng chung cho một lượt đối soát:

~~~sql
CREATE TABLE recon_source_snapshot (
    run_id         UUID NOT NULL,
    order_id       BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    status         VARCHAR(32) NOT NULL,
    total_minor    BIGINT NOT NULL,
    deleted        BOOLEAN NOT NULL,
    PRIMARY KEY (run_id, order_id)
);

CREATE TABLE recon_target_snapshot (
    run_id         UUID NOT NULL,
    order_id       BIGINT NOT NULL,
    source_version BIGINT NOT NULL,
    status         VARCHAR(32) NOT NULL,
    total_minor    BIGINT NOT NULL,
    deleted        BOOLEAN NOT NULL,
    PRIMARY KEY (run_id, order_id)
);
~~~

**run_id** xác định một lần quét và giúp tái hiện kết quả. Bản ghi đưa vào staging phải có thông tin **source watermark, scope, phiên bản mapping và mốc thời gian capture** ở metadata của run. Đừng dùng một run_id cho hai tập lấy ở các mốc không tương thích rồi xem mọi khác biệt là lỗi.

Sử dụng **tombstone** trong mô hình mẫu để biểu diễn dữ liệu đã xóa (deleted=true, source_version vẫn tăng). Việc nguồn hoàn toàn không có orderId không đủ bằng chứng xóa hợp lệ nếu API ẩn các bản ghi đã xóa.

### 5.2. Truy vấn phân loại sai lệch

Sau khi thu thập **cả hai snapshot nhất quán theo hợp đồng**, dùng:

~~~sql
WITH s AS (
    SELECT order_id, source_version, status, total_minor, deleted
    FROM recon_source_snapshot
    WHERE run_id = :runId
),
d AS (
    SELECT order_id, source_version, status, total_minor, deleted
    FROM recon_target_snapshot
    WHERE run_id = :runId
)
SELECT
    COALESCE(s.order_id, d.order_id) AS order_id,
    s.source_version AS expected_version,
    d.source_version AS actual_version,
    CASE
        WHEN s.order_id IS NULL THEN 'DEST_ONLY'
        WHEN d.order_id IS NULL THEN 'SOURCE_ONLY'
        WHEN d.source_version < s.source_version THEN 'DEST_BEHIND'
        WHEN d.source_version > s.source_version THEN 'DEST_AHEAD'
        WHEN s.status IS DISTINCT FROM d.status
          OR s.total_minor IS DISTINCT FROM d.total_minor
          OR s.deleted IS DISTINCT FROM d.deleted
        THEN 'CONTENT_MISMATCH'
        ELSE 'MATCH'
    END AS outcome
FROM s
FULL OUTER JOIN d
    ON s.order_id = d.order_id
ORDER BY order_id;
~~~

Hai Common Table Expression **s** và **d** lọc **run_id** trước khi JOIN. Nếu đặt điều kiện **s.run_id = :runId AND d.run_id = :runId** trong **WHERE** sau FULL OUTER JOIN, sẽ vô tình loại bỏ các dòng chỉ tồn tại ở một phía.

**IS DISTINCT FROM** trong PostgreSQL so sánh có xét NULL, tránh bỏ sót chênh lệch khi một giá trị thiếu. Với database khác, cần dùng biểu thức tương đương.

Kết quả SQL là **ứng viên sai lệch kỹ thuật**. Trước khi tạo lệnh sửa, cần kiểm tra tuổi, watermark, retention/tombstone, độ trễ consumer và quy tắc nguồn có thẩm quyền.

### 5.3. Ghi lịch sử đối soát để có thể kiểm toán

Mỗi lượt cần lưu ít nhất:

| Trường | Ý nghĩa |
| --- | --- |
| **run_id, job_version** | Định danh lượt chạy và phiên bản thuật toán/hợp đồng. |
| **scope, source_watermark** | Phạm vi tenant/partition/key và mốc dữ liệu nguồn. |
| **started_at, completed_at, status** | Thời gian và kết quả lượt chạy; phân biệt RUNNING/PARTIAL/COMPLETED/FAILED. |
| **last_key, batch_number** | Checkpoint phục hồi khi quét lớn. |
| **counts_by_outcome** | Số MATCH, SOURCE_ONLY, DEST_ONLY, LAGGING, MISMATCH, INCOMPARABLE. |
| **finding_id, order_id, versions** | Bằng chứng từng bản ghi lệch, hash/giá trị đã được giảm thiểu dữ liệu nhạy cảm. |
| **repair_action, result, verified_at** | Quyết định sửa, tác động, lần đọc lại và người/quy trình phê duyệt nếu cần. |

Đừng coi **PARTIAL** là hoàn tất chỉ vì hàng đã quét đều MATCH. Một run chưa quét hết tập đầu vào không thể dùng để kết luận toàn hệ thống nhất quán.

## 6. Thiết kế job Spring Boot và Spring Integration

Một kiến trúc đơn giản có thể gồm:

~~~mermaid
flowchart LR
    A[Scheduler / Spring Integration poller] --> B[Reconciliation coordinator]
    B --> C[Source API / JDBC]
    B --> D[Target API / JDBC]
    C --> E[Normalize + compare by business key]
    D --> E
    E --> F[(Run + finding store)]
    F --> G{Repair policy}
    G -->|An toàn, tự động| H[Idempotent repair / replay]
    G -->|Mơ hồ, rủi ro cao| I[Quarantine + điều tra]
    H --> J[Read-back verification]
    I --> J
~~~

**Scheduler**, **@Scheduled** hoặc Spring Integration poller chỉ kích hoạt công việc. Tính đúng đắn phụ thuộc vào dữ liệu và quy tắc phía sau, không phụ thuộc vào chọn cách kích hoạt nào.

### 6.1. Thu thập phân trang có thể tiếp tục

Job đọc một phạm vi đã cố định:

1. Tạo **run_id** và metadata gồm source watermark, scope, contract version.
2. Lấy một batch nguồn bằng keyset/cursor ổn định. Đọc trạng thái đích cho đúng tập key hoặc lấy snapshot đích độc lập để phát hiện cả **DEST_ONLY**.
3. Chuẩn hóa record; so sánh version và nội dung theo contract.
4. Ghi findings và checkpoint vào kho bền vững; checkpoint chỉ được đánh dấu sau khi kết quả batch đã lưu thành công.
5. Tiếp tục từ cursor; kết thúc chỉ khi quét toàn bộ scope và xác minh không có khoảng trống.
6. Chạy lại các findings sau grace period và xử lý theo chính sách sửa.

Nếu **checkpoint được lưu trước findings** rồi tiến trình chết, có thể bỏ qua hàng chưa đối soát. Nếu findings đã lưu mà checkpoint chưa lưu, batch được chạy lại; cần ràng buộc duy nhất như **(run_id, order_id)** và upsert kết quả để không nhân đôi tác động.

Không mở một transaction JDBC kéo dài xuyên hàng nghìn HTTP request. Mỗi batch có transaction lưu findings/checkpoint ngắn và có retry riêng. Không giả định **@Transactional** trên Spring Boot service quản lý cùng lúc cả database nguồn, HTTP và broker.

### 6.2. Tách phát hiện và sửa chữa

Đối soát có thể chạy ở chế độ **detect-only** trước. Findings có thể được xác minh lại trước khi thực thi vì dữ liệu nguồn/đích đã thay đổi kể từ khi quét:

~~~text
DETECTED -> CONFIRMED -> APPROVED -> APPLYING -> VERIFIED
                          |                |
                          v                v
                       DEFERRED         FAILED/RETRY
~~~

Mỗi finding chứa expected version và actual version đã quan sát. Việc sửa phải đọc lại/kiểm tra điều kiện **compare-and-set** để tránh ghi đè một record đích mới hơn.

### 6.3. Ví dụ upsert đích không ghi đè version mới hơn

Với PostgreSQL, bảng đích giữ version nguồn đã áp dụng:

~~~sql
CREATE TABLE order_projection (
    order_id       BIGINT PRIMARY KEY,
    source_version BIGINT NOT NULL,
    status         VARCHAR(32) NOT NULL,
    total_minor    BIGINT NOT NULL,
    deleted        BOOLEAN NOT NULL DEFAULT FALSE
);
~~~

Áp dụng bản sửa từ nguồn (đã xác nhận hợp lệ):

~~~sql
INSERT INTO order_projection
    (order_id, source_version, status, total_minor, deleted)
VALUES
    (:orderId, :sourceVersion, :status, :totalMinor, :deleted)
ON CONFLICT (order_id) DO UPDATE
SET source_version = EXCLUDED.source_version,
    status = EXCLUDED.status,
    total_minor = EXCLUDED.total_minor,
    deleted = EXCLUDED.deleted
WHERE order_projection.source_version < EXCLUDED.source_version;
~~~

Điều kiện **source_version < EXCLUDED.source_version** cho phép cập nhật bản cũ nhưng không cho sự kiện cũ ghi đè bản mới. Nếu cùng version nhưng nội dung khác, câu lệnh không sửa; hãy phân loại đó là **CONTENT_MISMATCH** cần điều tra, hoặc thực thi một thao tác sửa riêng có kiểm tra expected version và bằng chứng nguồn thật sự có thẩm quyền. Việc dùng **>=** để ghi đè cùng version một cách mù quáng có thể che lỗi mapping.

Tombstone cũng là record có version: khi nhận delete version 20, đặt **deleted=true** và giữ version 20. Bản update version 19 phát lại không thể hồi sinh record.

### 6.4. Ví dụ service phát hiện sai lệch và sửa có điều kiện

Đoạn Java minh họa lõi quyết định, với **SourceGateway** trả về trạng thái ở mốc được yêu cầu và **TargetRepository** có thao tác SQL version-guarded như bên trên:

~~~java
record OrderState(
        long orderId,
        long sourceVersion,
        String status,
        long totalMinor,
        boolean deleted) {}

enum Outcome {
    MATCH, DEST_BEHIND, DEST_AHEAD,
    SOURCE_ONLY, CONTENT_MISMATCH, INCOMPARABLE
}

@Service
class OrderReconciliationService {
    private final SourceGateway source;
    private final TargetRepository target;

    OrderReconciliationService(SourceGateway source,
                               TargetRepository target) {
        this.source = source;
        this.target = target;
    }

    Outcome compare(long orderId, long watermark) {
        // Gateway chỉ trả dữ liệu hợp lệ theo snapshot/watermark
        // và bao gồm tombstone; null phải được phân loại riêng.
        OrderState expected = source.findAt(orderId, watermark);
        OrderState actual = target.find(orderId);

        if (expected == null) {
            return Outcome.INCOMPARABLE;
        }
        if (actual == null) {
            return Outcome.SOURCE_ONLY;
        }
        if (actual.sourceVersion() < expected.sourceVersion()) {
            return Outcome.DEST_BEHIND;
        }
        if (actual.sourceVersion() > expected.sourceVersion()) {
            return Outcome.DEST_AHEAD;
        }

        boolean samePayload =
                actual.deleted() == expected.deleted()
                && actual.totalMinor() == expected.totalMinor()
                && actual.status().equals(expected.status());

        return samePayload
                ? Outcome.MATCH
                : Outcome.CONTENT_MISMATCH;
    }
}
~~~

**SourceGateway** và **TargetRepository** là các abstraction của ứng dụng, không phải class Spring cung cấp sẵn; code cần được triển khai theo HTTP client/JdbcTemplate hoặc adapter thực tế. Đây là ví dụ để diễn đạt **quy tắc đối chiếu**, chưa có lệnh repair và chưa xử lý **DEST_ONLY** trên toàn bộ phạm vi vì muốn phát hiện DEST_ONLY phải quét cả tập đích.

Trong hệ thống thật, cần giữ **tenantId**, phân loại lỗi HTTP/database khác với việc nguồn không có record, quản lý null từ dữ liệu không hợp lệ và lấy nhất quán theo mốc. Một lần so sánh theo orderId không tự chứng minh snapshot ổn định trong khi các sự kiện mới tiếp tục đến.

Với **DEST_BEHIND** đã quá SLA và dữ liệu nguồn được xác nhận, worker có thể dùng upsert có guard version, sau đó **đọc lại** từ đích để xác minh trạng thái. Nếu 0 dòng được cập nhật, có thể một worker khác vừa áp dụng version bằng hoặc mới hơn; phải đọc lại rồi phân loại thay vì báo đã sửa thành công.

## 7. Sửa sai lệch: ưu tiên bằng chứng và tính lặp lại

Không phải mọi finding đều nên sửa bằng cách sao chép record từ nguồn sang đích.

| Kết quả | Phản ứng sau khi đã xác minh | Khi nào cần can thiệp thủ công |
| --- | --- | --- |
| **DEST_BEHIND** còn trong SLA | Chờ consumer, theo dõi backlog và đọc lại. | Lag vượt SLA, DLQ hoặc sự kiện đã hết retention. |
| **DEST_BEHIND** quá SLA | Replay sự kiện theo version hoặc upsert projection bằng dữ liệu nguồn có thẩm quyền. | Đích có sửa đổi riêng, có side effect không thể đảo hoặc thiếu nguồn version. |
| **SOURCE_ONLY** | Kiểm tra event tạo mới và scope; tạo projection bằng idempotent upsert nếu đủ điều kiện. | Không xác định được có phải record đang chờ hay bị ẩn do quyền/filter. |
| **DEST_ONLY** | Tra cứu tombstone, lịch sử xóa, scope và retention; có thể đánh dấu xóa bằng version có thẩm quyền. | Không chứng minh được nguồn đã xóa; tránh xóa vật lý ngay. |
| **CONTENT_MISMATCH** cùng version | So sánh mapper, schema, normalization và bằng chứng commit; sửa có expected-version guard sau khi xác nhận. | Dữ liệu tài chính, thay đổi nhiều nguồn, nghi ngờ sai logic ứng dụng. |
| **DEST_AHEAD/INCOMPARABLE** | Đọc lại với mốc và contract phù hợp; trì hoãn. | Xung đột ownership, metadata thiếu hoặc không thể xác định trạng thái đúng. |

### 7.1. Replay sự kiện hay rebuild projection?

**Replay** phù hợp nếu event log bền vững, đủ retention, có thứ tự/version và consumer idempotent. Nếu cần dựng lại toàn bộ read model, có thể tạo bảng projection mới từ snapshot nguồn rồi bắt kịp event delta trước khi chuyển traffic.

**Rebuild** cần tránh xóa projection đang phục vụ production trước khi có bản thay thế kiểm chứng được. Dùng snapshot + CDC/outbox catch-up, đối soát số lượng/khóa/phiên bản, sau đó chuyển đọc có kiểm soát.

Nếu dữ liệu nguồn hiện tại đã khác trạng thái tại thời điểm event cũ, replay có thể không phù hợp với một event chỉ chứa delta không idempotent. Các event kiểu **“cộng 10 điểm”** cần chống trùng tuyệt đối theo eventId và đảm bảo thứ tự; dùng snapshot trạng thái cuối cùng cho read model khi contract cho phép sẽ dễ sửa hơn.

### 7.2. Tránh race condition trong quá trình repair

Giả sử job thấy đích ở version 6, nguồn ở version 7. Trong lúc job chuẩn bị sửa, consumer cập nhật đích lên version 8. Một lệnh **UPDATE** không có điều kiện có thể ghi đè version 8 bằng version 7.

Vì vậy:

- Guard theo **sourceVersion** hoặc compare-and-set ở database.
- Nếu sửa cùng version do nội dung sai, so sánh cả **expected old state/hash** và lưu audit.
- Không coi việc HTTP trả 200 là bằng chứng dữ liệu đã đúng; đọc lại kết quả hoặc nhận bằng chứng commit.
- Mỗi lệnh sửa có **idempotency key**, finding/run ID và trace/correlation ID.
- Rate limit, chia batch, backoff và có **kill switch** để dừng sửa nếu thấy sai lệch lan rộng.

### 7.3. Khi sửa có tác động bên ngoài

Việc sửa projection hoặc cache có thể làm lại được; nhưng gọi **refund**, tạo shipment, gửi email hoặc ghi ledger có thể tạo tác động thực. Không được “replay tất cả” như thể side effect luôn đảo ngược được. Cần kiểm tra trạng thái bên thứ ba, sử dụng khóa idempotency hoặc quy trình bù trừ được phê duyệt.

Với dữ liệu nhạy cảm và báo cáo tài chính, có thể cần **quarantine + human approval** trước khi sửa. Mọi thao tác sửa cần lưu bằng chứng trước/sau, ai/hệ thống nào thực hiện và cách khôi phục khi sửa sai.

## 8. Liên hệ với retry, deduplication, outbox và transaction

Đối soát có vai trò bổ sung cho các cơ chế nhất quán:

**Idempotent consumer.** Sự kiện có thể bị phát lại sau broker redelivery. Lưu khóa **(consumerName, eventId)** hoặc ràng buộc nghiệp vụ tương đương trong cùng database transaction với tác động nghiệp vụ. Điều này chống xử lý lặp, nhưng không chứng minh không bỏ mất một event chưa từng đến.

**Transactional outbox.** Database nguồn cập nhật nghiệp vụ và lưu ý định phát sự kiện trong cùng giao dịch. Relay phát tới broker theo cơ chế có thể retry, thường mang tính **at-least-once**. Đối soát kiểm tra có event còn mắc ở outbox hoặc projection đã khác nguồn.

**Inbox và checkpoint.** Khi nhận sự kiện, lưu bền payload/dấu đã xử lý trước ACK khi contract yêu cầu. Checkpoint/offset phải phản ánh phần công việc đã commit, không chỉ số event đã đọc. Đối soát có thể kiểm tra những eventId đã accepted nhưng chưa processed.

**JTA/XA.** Có thể điều phối atomic commit của các tài nguyên XA thực sự tham gia, nhưng không bao phủ mọi HTTP/cache/side effect và không loại trừ lỗi nghiệp vụ, mapper sai hoặc dữ liệu thay đổi ngoài luồng. Đối soát vẫn hữu ích.

**Cache.** Cache có thể lệch so với database vì TTL, invalidation hoặc race. Cần quy ước **database authoritative**, cache version/TTL và cách refresh; không cần đối soát mọi cache entry nếu chấp nhận eventual cache invalidation.

**Spring Integration flow.** HTTP inbound adapter, JDBC outbound adapter, message channel, poller hoặc aggregator có thể tạo ranh giới giao dịch và trạng thái chờ khác nhau. Điều phối đối soát phải biết nguồn nào giữ công việc bền vững và chỗ nào có thể retry/duplicate khi restart.

~~~mermaid
flowchart TD
    A[(DB nguồn)] --> B[(Outbox)]
    B --> C[(Broker)]
    C --> D[Consumer idempotent]
    D --> E[(DB đích)]
    A --> F[Reconciliation]
    E --> F
    C --> G[Backlog / DLQ metrics]
    G --> F
    F --> H{Finding}
    H -->|Lag bình thường| I[Theo dõi / đọc lại]
    H -->|Sai lệch xác nhận| J[Repair có điều kiện]
    H -->|Mơ hồ| K[Điều tra]
    J --> E
~~~

Một nguyên tắc vận hành quan trọng là **repair không được tạo một đường cập nhật “bí mật” bỏ qua invariant và audit**. Tốt nhất sửa qua cùng domain service hoặc một cổng dữ liệu có guard/version và logging tương đương.

## 9. Kiểm thử đối soát và phục hồi

Các kiểm thử nên có database/broker hoặc server giả lập đủ trung thực với quy trình thực tế, sử dụng tập eventId và version xác định. Chỉ mock phương thức so sánh sẽ không phát hiện lỗi checkpoint, khóa unique hoặc thứ tự commit.

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Hai bên cùng key/version/payload | MATCH; không thực hiện sửa. |
| Cùng số lượng dòng nhưng hoán đổi một key | Phát hiện SOURCE_ONLY và DEST_ONLY; không bị COUNT đánh lừa. |
| Target v7, source v8, consumer còn backlog | DEST_BEHIND trong grace period, chưa sửa vội. |
| Target v7, source v8, backlog hết và sai lệch vượt SLA | Finding được xác minh; repair/replay có guard version; readback đạt. |
| Target v8 nhưng khác status của source v8 | CONTENT_MISMATCH; không ghi đè thiếu kiểm soát. |
| Job đang sửa v8 thì target lên v9 | Guard chống ghi đè v9; job đọc lại và phân loại. |
| Xóa tại nguồn bằng tombstone v10, event update v9 phát lại | Đích vẫn deleted=true, version 10. |
| Chạy hai job cùng scope hoặc chết giữa findings và checkpoint | Không nhân đôi finding/repair; job tiếp tục được và không bỏ qua batch. |
| Source API trả lỗi/timeout/partial page | Run PARTIAL/FAILED, không tự coi entry thiếu là đã xóa. |
| Lược bỏ event cũ khỏi stream do retention | Incremental có thể hụt; full reconciliation phát hiện sai lệch. |
| Sai mapping currency, timezone, null hoặc field đa trị | Test bắt được trước/sau normalization; không sửa sai theo hash khác contract. |
| Nhiều tenant trùng orderId hoặc nhiều partition | So khớp theo khóa đúng; watermark/offset từng partition không bị gộp sai. |
| Repair ghi DB thành công nhưng phản hồi timeout | Retry cùng idempotency key không gây thay đổi lặp; đọc lại xác nhận. |

### Fault injection cho job

1. Sinh tập nguồn và đích có **MATCH, SOURCE_ONLY, DEST_ONLY, BEHIND, AHEAD, CONTENT_MISMATCH**, kể cả tombstone.
2. Chạy quét một phần, dừng cưỡng bức sau khi lưu findings nhưng trước checkpoint; khởi động lại và kiểm tra không bỏ sót/nhân đôi.
3. Dừng sau khi repair commit nhưng trước khi ghi **VERIFIED**; chạy lại và xác minh idempotency.
4. Cho consumer cập nhật đích đồng thời để phát hiện race và kiểm tra compare-and-set.
5. Tắt broker/nguồn API, kích hoạt timeout và DLQ, sau đó phục hồi; kiểm tra run **PARTIAL** được phân biệt với run thực sự hoàn tất.
6. Đối chiếu lại toàn bộ tập khóa theo cùng watermark sau khi các luồng bắt kịp.

Không chỉ kiểm thử trường hợp happy path khi dữ liệu đứng yên: khó khăn lớn nhất xuất hiện khi nguồn, đích và công việc repair cùng hoạt động.

## 10. Theo dõi đối soát trong production

Những chỉ số nên đo:

| Chỉ số | Ý nghĩa |
| --- | --- |
| **last_successful_full_reconcile_at** | Full scan gần nhất hoàn tất đúng phạm vi và mốc. |
| **reconcile_duration / scanned_keys** | Thời gian, số bản ghi đã quét và tiến độ. |
| **mismatch_count_by_type** | Phân bố missing, extra, behind, ahead, content mismatch. |
| **mismatch_age / stale_version_lag** | Tuổi và mức độ tồn tại sai lệch; phân biệt chậm ngắn hạn với lỗi kéo dài. |
| **repair_attempt / repair_success / repair_failure** | Hiệu quả và rủi ro thao tác sửa. |
| **unverified_repairs** | Những thao tác đã gửi nhưng chưa có readback đúng. |
| **source_api_errors / target_db_errors** | Độ tin cậy của công đoạn thu thập. |
| **broker_backlog / consumer_lag / DLQ** | Bối cảnh nguyên nhân sai lệch. |
| **run_partial / checkpoint_age** | Job bị kẹt, mất khả năng hoàn tất phạm vi. |

Mỗi finding nên gắn **runId, tenantId, businessKey, sourceVersion, targetVersion, source watermark, correlationId và classification**. Hạn chế log đầy đủ payload chứa thông tin cá nhân hoặc bí mật; lưu fingerprint/bằng chứng tối thiểu với quyền truy cập phù hợp.

Đặt cảnh báo theo **độ tuổi sai lệch**, số lượng bất thường, tỷ lệ lỗi trên tổng tập đã quét và giới hạn nghiệp vụ; chỉ cảnh báo khi **COUNT khác nhau tức thời** sẽ gây nhiều nhiễu trong hệ thống eventual consistency.

### Ví dụ SLO và chính sách can thiệp

Một read model có thể đặt mục tiêu **99,9% đơn hàng được đồng bộ trong 5 phút** sau commit nguồn. Đây chỉ là ví dụ để thiết kế ngưỡng; số thật phải dựa vào độ quan trọng nghiệp vụ và khả năng hệ thống.

- Trong 5 phút, có thể ghi nhận **DEST_BEHIND** nhưng chưa tự sửa.
- Sau ngưỡng, kiểm tra consumer lag, outbox, DLQ và xác minh version.
- Nếu vượt ngưỡng kéo dài hoặc số lượng đột biến, tạm dừng auto-repair có rủi ro và điều tra.
- Khi đã sửa, tính **thời gian đến VERIFIED**, không chỉ thời gian gửi lệnh cập nhật.

## 11. Runbook khi hai hệ thống có trạng thái lệch

1. **Khoanh phạm vi:** xác định thực thể, tenant, business key, dữ liệu nào có thẩm quyền, hợp đồng và version hiện hành.
2. **Chụp bằng chứng:** nguồn/đích theo watermark hoặc snapshot, consumer offset, outbox, DLQ, log và thời điểm thay đổi.
3. **Phân loại:** missing, extra, behind, ahead, same-version mismatch, incomparable; xét grace period và độ trễ.
4. **Tìm nguyên nhân:** event mất/kẹt, retry bỏ sót, checkpoint/ACK quá sớm, schema mapper sai, sửa ngoài luồng, dữ liệu xóa thiếu tombstone hoặc lỗi API.
5. **Chọn phục hồi:** chờ bắt kịp, replay có idempotency, backfill/rebuild projection, sửa có CAS hoặc điều tra thủ công khi không xác định nguồn đúng.
6. **Thực thi giới hạn:** chạy theo batch, có rate limit, audit, điều kiện dừng, theo dõi race và checkpoint.
7. **Kiểm chứng:** đọc lại hai phía cùng contract/mốc, đối soát tập key và version; đánh dấu VERIFIED khi bất biến đạt.
8. **Ngăn tái diễn:** sửa logic outbox/consumer/filter/checkpoint, bổ sung kiểm thử fault injection, điều chỉnh SLO/monitoring.

### Những sai lầm cần tránh

- Chỉ so sánh số lượng hoặc tổng tiền rồi kết luận hai hệ thống nhất quán.
- Đọc hai snapshot khác thời điểm mà không xét watermark và độ trễ đồng bộ.
- Dùng **updated_at** của nhiều máy như một sequence tuyệt đối.
- Xóa ngay record DEST_ONLY khi chưa kiểm chứng source deletion, retention, scope và tombstone.
- Sửa version thấp đè lên version cao do không có điều kiện compare-and-set.
- Dùng eventId làm khóa thực thể hoặc coi một eventId là toàn bộ lịch sử của một order.
- Commit checkpoint trước khi lưu kết quả đối soát, rồi bỏ sót dữ liệu sau crash.
- Cho job sửa chạy song song không có khóa/guard và thiếu audit.
- Coi HTTP 200, publish ACK hoặc một transaction commit là bằng chứng trạng thái cuối hai bên đã tương đồng.
- Replay những side effect tài chính/vận chuyển ngoài hệ thống mà không có idempotency hoặc bù trừ.

## 12. Ghi nhớ

**Đối soát trạng thái là một vòng kiểm chứng độc lập cho nhất quán cuối cùng.** Một thiết kế tốt phải biết **ai sở hữu dữ liệu**, **so sánh theo khóa/version/hợp đồng nào**, **mốc nguồn và đích có tương thích không**, và **sai lệch đã vượt khoảng thời gian cho phép chưa**. Từ đó job phát hiện được bản ghi thiếu, dư, chậm hoặc sai nội dung mà không nhầm với đồng bộ đang diễn ra bình thường.

Đối soát chỉ thực sự hoàn tất khi finding được lưu có thể truy vết, sửa bằng thao tác **idempotent và có điều kiện**, rồi **đọc lại chứng minh** trạng thái đích đúng. Kết hợp đối soát định kỳ với outbox/inbox, consumer chống trùng, checkpoint bền vững, DLQ và quan sát luồng tích hợp giúp Spring Boot phục hồi cả những sai lệch mà một lần retry hoặc transaction riêng lẻ không thể tự giải quyết.
