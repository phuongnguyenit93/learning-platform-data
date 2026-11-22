# Kế hoạch cắt chuyển, dữ liệu tăng thêm và quay lui khi kiểm tra thất bại

Di chuyển Oracle Database sang máy chủ, PDB, trung tâm dữ liệu hoặc môi trường mới không kết thúc khi export/import hoàn tất. Trong thời gian chuẩn bị, dữ liệu ở nguồn vẫn có thể thay đổi: người dùng tạo đơn hàng, cập nhật khách hàng, thanh toán được ghi nhận, job chạy nền cập nhật trạng thái và ứng dụng phát sinh giao dịch mới. Nếu chỉ chuyển một bản dữ liệu tại một thời điểm rồi đổi kết nối, các thay đổi sau thời điểm trích xuất có thể bị mất.

Một kế hoạch cắt chuyển (cutover) cần xác định cách tạo bản dữ liệu ban đầu nhất quán, cách thu thập và áp dụng dữ liệu tăng thêm (delta), thời điểm ngừng ghi ở nguồn, điều kiện cho phép chuyển ứng dụng sang đích và phương án quay lui (rollback) nếu kiểm tra thất bại. Đặc biệt, sau khi ứng dụng bắt đầu ghi vào database đích, quay lại nguồn không còn đơn giản là đổi connection string: những giao dịch mới ở đích phải được bảo toàn hoặc được xử lý theo quyết định nghiệp vụ rõ ràng.

## 1. Mục tiêu và thuật ngữ của một đợt cắt chuyển

### 1.1. Các mốc dữ liệu

Trong một đợt migration, cần phân biệt các mốc sau:

- **Nguồn (source):** database đang phục vụ ứng dụng trước khi chuyển.
- **Đích (target):** database mới sẽ nhận ứng dụng và giao dịch sau cutover.
- **Baseline / initial load:** tập dữ liệu ban đầu được trích xuất từ nguồn tại một mốc nhất quán và nạp vào đích.
- **Delta / change data:** các thay đổi phát sinh sau mốc baseline, gồm insert, update và delete.
- **Catch-up:** quá trình áp dụng các delta còn tồn đọng vào đích để đích tiến gần trạng thái nguồn.
- **Write freeze:** thời điểm ngừng giao dịch ghi mới tại nguồn để tạo ranh giới cuối cùng cho cutover.
- **Cutover point:** thời điểm có thẩm quyền chuyển ứng dụng sang đích.
- **Rollback window:** khoảng thời gian sau cutover mà nhóm vận hành còn chuẩn bị và có thể quay về nguồn theo phương án đã định.

Baseline và delta phải có ranh giới rõ ràng. Nếu baseline chứa một giao dịch nhưng delta lại áp dụng giao dịch đó lần nữa, dữ liệu có thể bị nhân đôi. Nếu baseline bỏ sót giao dịch và delta bắt đầu sau giao dịch đó, dữ liệu sẽ mất. Việc xác định mốc đồng bộ là một phần quan trọng của thiết kế.

### 1.2. Các mục tiêu cần thống nhất

Trước khi chọn công cụ, nhóm dự án cần thống nhất:

| Mục tiêu | Câu hỏi cần trả lời |
|---|---|
| Downtime | Ứng dụng được phép ngừng ghi hoặc ngừng phục vụ trong bao lâu? |
| RPO | Có thể chấp nhận mất tối đa bao nhiêu dữ liệu theo thời gian? |
| RTO | Từ lúc quyết định chuyển hoặc quay lui đến khi dịch vụ sẵn sàng cần bao lâu? |
| Consistency | Các bảng và giao dịch liên quan phải cùng phản ánh một mốc dữ liệu nào? |
| Delta mechanism | Dùng redo-based CDC, GoldenGate, cơ chế ứng dụng hay quy trình trích xuất riêng? |
| Rollback | Nếu đích đã nhận giao dịch mới, các giao dịch đó sẽ được bảo toàn như thế nào? |
| Acceptance | Những kiểm tra nào phải đạt trước khi cho phép mở ghi ở đích? |

Không có một công cụ hoặc một lịch cutover phù hợp cho mọi hệ thống. Một database nhỏ có thể chấp nhận downtime để export/import và kiểm tra. Hệ thống giao dịch lớn cần thời gian ngừng ngắn thường phải nạp baseline trước và đồng bộ delta liên tục trong khi nguồn vẫn hoạt động.

## 2. Chọn chiến lược di chuyển

### 2.1. Di chuyển có downtime (offline migration)

Quy trình offline đơn giản nhất là dừng ghi ở nguồn, export dữ liệu, import vào đích, kiểm tra rồi chuyển ứng dụng. Vì nguồn đã được đóng băng trong suốt quá trình, không cần cơ chế delta liên tục.

Phù hợp khi:

- Dữ liệu và số lượng đối tượng đủ nhỏ để export/import trong cửa sổ downtime.
- Nghiệp vụ có thể tạm ngừng giao dịch.
- Cấu trúc đích có thay đổi cần migration theo kế hoạch.
- Tổ chức ưu tiên quy trình ít thành phần hơn và chấp nhận downtime đã thống nhất.

Hạn chế là downtime bao gồm cả export, truyền file, import, compile object, kiểm tra và xử lý lỗi. Cần diễn tập bằng dữ liệu có dung lượng tương đương production để ước lượng thời gian thực tế.

### 2.2. Nạp baseline trước, đồng bộ delta trong khi nguồn còn hoạt động

Với hệ thống cần downtime ngắn, có thể tạo baseline tại mốc SCN nhất quán, nạp vào đích trong khi nguồn vẫn phục vụ giao dịch, rồi liên tục áp dụng các thay đổi phát sinh sau mốc đó. Khi delta lag gần bằng 0, nhóm dự án đóng băng ghi ở nguồn, chờ apply hoàn tất, kiểm tra và chuyển ứng dụng.

Các công cụ/cơ chế thường được cân nhắc:

- Oracle GoldenGate hoặc giải pháp CDC dựa trên redo để capture và apply thay đổi.
- Cơ chế replication đã được thiết kế và hỗ trợ trong kiến trúc hiện tại.
- Outbox/event log ở tầng ứng dụng nếu ứng dụng được xây dựng để phát sự kiện giao dịch đầy đủ và có thể phát lại an toàn.
- Trích xuất delta theo watermark trong trường hợp dữ liệu, schema và yêu cầu nhất quán cho phép.

Data Pump có thể tạo baseline logic nhất quán bằng `FLASHBACK_SCN` hoặc `FLASHBACK_TIME` trong điều kiện phù hợp. Tuy nhiên, Data Pump không tự cung cấp một luồng CDC liên tục để theo dõi mọi insert, update và delete sau baseline. Cần thiết kế cơ chế delta riêng và xác định cách áp dụng delta vào đích.

### 2.3. So sánh các phương án

| Phương án | Downtime | Ưu điểm | Rủi ro/điều kiện |
|---|---|---|---|
| Data Pump offline | Cao hơn, gồm toàn bộ export/import và validation. | Dễ tổ chức, ít thành phần đồng bộ. | Cần đủ cửa sổ dừng dịch vụ; phải kiểm tra thời gian thực tế. |
| Data Pump baseline + CDC | Thường ngắn ở giai đoạn cutover. | Nạp phần lớn dữ liệu trước, chỉ chờ delta cuối. | Cần căn chỉnh SCN, quản lý CDC, thứ tự giao dịch và lỗi apply. |
| Transportable tablespaces + delta | Có thể ngắn với tập dữ liệu lớn. | Di chuyển datafile nhanh khi đáp ứng điều kiện. | Có yêu cầu self-contained, endian, version, read-only và quy trình chuyên biệt. |
| Network migration/replication | Tùy công nghệ và khối lượng dữ liệu. | Có thể giảm dump file trung gian. | Phụ thuộc mạng, quyền, tương thích và tải hai database. |
| Application-level delta | Có thể ngắn nếu thiết kế sẵn. | Có thể giữ logic nghiệp vụ và kiểm soát sự kiện. | Phải xử lý đầy đủ update/delete, retry, ordering và idempotency. |

Chọn phương án dựa trên RPO/RTO, dung lượng, tốc độ thay đổi, phiên bản Oracle, cấu trúc schema, khả năng downtime và năng lực vận hành. Đừng chọn CDC chỉ vì muốn giảm downtime nếu nhóm chưa có khả năng giám sát lag, xử lý lỗi và diễn tập rollback.

## 3. Lập kế hoạch baseline nhất quán

### 3.1. Vì sao cần một mốc nhất quán?

Giả sử export bảng `ORDERS` lúc 10:00, nhưng export bảng `PAYMENTS` lúc 10:15 trong khi giao dịch đang tiếp tục. Một đơn hàng được tạo và thanh toán giữa hai thời điểm có thể khiến hai bảng phản ánh các trạng thái khác nhau nếu export không dùng một snapshot nhất quán. Khi import, dữ liệu có thể không khớp dù từng bảng riêng lẻ có vẻ hợp lệ.

Baseline nên phản ánh một mốc logic thống nhất cho các bảng liên quan. Với Data Pump, có thể chỉ định SCN để các đối tượng được export theo cùng snapshot nếu điều kiện flashback và undo cho phép.

### 3.2. Lấy SCN cho baseline

Có thể lấy SCN hiện tại bằng:

```sql
SELECT current_scn
FROM v$database;
```

Hoặc dùng package:

```sql
SELECT dbms_flashback.get_system_change_number AS baseline_scn
FROM dual;
```

Ghi lại SCN, timestamp, database identity, PDB/container và thời điểm bắt đầu export. SCN là mốc logic của database, không phải timestamp đồng hồ. Không tự quy đổi SCN sang thời gian bằng phép tính tuyến tính.

### 3.3. Export bằng FLASHBACK_SCN

Ví dụ parfile cho Data Pump:

```text
DIRECTORY=DP_DIR
DUMPFILE=app_baseline_%U.dmp
LOGFILE=app_baseline.log
JOB_NAME=APP_BASELINE_EXPORT
SCHEMAS=APP
FLASHBACK_SCN=123456789012
PARALLEL=4
LOGTIME=ALL
METRICS=YES
```

Chạy:

```bash
expdp app_migration@SOURCEPDB PARFILE=app_baseline.par
```

Thay SCN ví dụ bằng mốc thực tế đã ghi nhận. `FLASHBACK_SCN` yêu cầu Oracle đọc dữ liệu nhất quán tại SCN đó. Job có thể gặp lỗi snapshot/undo nếu cần đọc phiên bản block mà undo đã bị ghi đè hoặc không còn khả dụng. Cần đánh giá thời gian export, tốc độ thay đổi và cấu hình undo trước khi chọn baseline SCN.

`FLASHBACK_TIME` cũng có thể dùng để chỉ định mốc thời gian; Oracle chuyển thời gian đó sang SCN phù hợp. Với runbook cần ranh giới chính xác giữa baseline và CDC, ghi lại SCN được sử dụng sẽ rõ ràng hơn.

### 3.4. Căn chỉnh baseline với CDC

Đối với redo-based CDC, nhóm cần xác định chính xác cơ chế capture bắt đầu từ đâu so với SCN baseline. Mục tiêu là:

- Mọi giao dịch đã được phản ánh trong baseline không bị áp dụng lại theo cách gây trùng.
- Mọi giao dịch commit sau ranh giới baseline được capture và apply.
- Giao dịch đang mở tại thời điểm baseline được xử lý đúng theo quy tắc snapshot/commit của công cụ.
- Không có khoảng trống log giữa thời điểm khởi tạo capture và lúc bắt đầu theo dõi liên tục.

GoldenGate và các công cụ CDC có quy trình instantiation/initial load riêng. Dùng đúng quy trình đồng bộ SCN hoặc checkpoint do công cụ hỗ trợ; không tự chọn một SCN gần đúng chỉ dựa trên thời gian đồng hồ. Cần thử trên bản sao để chứng minh không mất hoặc nhân đôi giao dịch ở ranh giới.

## 4. Thiết kế và áp dụng dữ liệu tăng thêm (delta)

### 4.1. Delta gồm những thay đổi nào?

Một delta đầy đủ phải xem xét:

- **INSERT:** bản ghi mới được tạo sau baseline.
- **UPDATE:** giá trị của bản ghi hiện có thay đổi.
- **DELETE:** bản ghi bị xóa khỏi nguồn.
- **DDL:** thay đổi cấu trúc như thêm cột, đổi kiểu, tạo index hoặc thay đổi constraint.
- **Sequence/identity:** giá trị sinh khóa tăng trong khi ứng dụng tiếp tục hoạt động.
- **Dữ liệu phụ thuộc:** bảng con, bảng audit, trạng thái workflow, LOB và dữ liệu được cập nhật bởi job nền.

Chỉ lấy các dòng mới tạo sẽ bỏ sót update và delete. Chỉ dựa vào `updated_at` sẽ không thấy hard delete nếu không có tombstone hoặc cơ chế capture riêng. Một migration có nhiều bảng liên quan còn phải giữ thứ tự và ranh giới transaction phù hợp.

### 4.2. Redo-based CDC

Redo-based CDC đọc thông tin thay đổi từ redo/archive log và chuyển thành các thao tác áp dụng tại đích. Oracle GoldenGate là một giải pháp phổ biến cho kiến trúc này. Tùy phiên bản và cấu hình, CDC có thể capture insert/update/delete, giữ thứ tự commit, theo dõi checkpoint và apply giao dịch.

Những điều kiện cần chuẩn bị:

- Bật supplemental logging phù hợp để capture đủ khóa và dữ liệu cần thiết.
- Xác nhận archive log được giữ đủ lâu để Extract đọc hết khi có lag hoặc gián đoạn.
- Cấp quyền capture/apply theo hướng dẫn của công cụ và phiên bản.
- Xác nhận bảng có khóa định danh phù hợp; bảng thiếu primary key có thể cần unique key hoặc cấu hình bổ sung.
- Xác định cách xử lý DDL, LOB, sequence, partition và các kiểu dữ liệu đặc biệt.
- Theo dõi checkpoint, trail/dữ liệu trung gian, apply lag, lỗi và conflict.
- Bảo đảm target được khởi tạo từ baseline đúng SCN theo cơ chế instantiation của công cụ.

Không nên xem CDC là một bản sao tự động hoàn hảo. Nếu thiếu logging, thiếu archive log, bảng không được hỗ trợ hoặc apply process lỗi, delta có thể bị gián đoạn. Phải có cảnh báo và runbook xử lý lag trước ngày cutover.

### 4.3. Delta theo watermark ở tầng dữ liệu

Với hệ thống nhỏ hoặc tập bảng có quy tắc cập nhật rõ ràng, có thể trích xuất delta theo một cột thời gian hoặc số thứ tự thay đổi. Ví dụ:

```sql
SELECT order_id, customer_id, status, total_amount, updated_at
FROM app.orders
WHERE updated_at > :last_successful_watermark
  AND updated_at <= :high_watermark;
```

Trong đó:

- `last_successful_watermark` là mốc cuối đã áp dụng thành công.
- `high_watermark` là mốc cố định của đợt trích xuất hiện tại.
- Sau khi nạp và xác nhận delta thành công, mới cập nhật watermark.

Không lấy `SYSTIMESTAMP` mới cho từng bảng trong cùng một đợt nếu cần snapshot thống nhất. Chọn một high watermark chung, ghi nhận nó và sử dụng cho tất cả bảng liên quan.

Phương án timestamp có nhiều giới hạn:

- Cột `updated_at` phải được cập nhật cho mọi đường ghi, kể cả batch và tác vụ quản trị.
- Cần thống nhất timezone và độ chính xác timestamp.
- Giao dịch bắt đầu trước watermark nhưng commit sau có thể bị bỏ sót nếu logic chỉ dựa vào thời điểm cập nhật không phản ánh commit.
- Hard delete không xuất hiện trong truy vấn delta thông thường.
- Bản ghi đến muộn hoặc cập nhật lại timestamp có thể làm sai watermark.
- Trích xuất nhiều bảng ở các snapshot khác nhau có thể tạo trạng thái không nhất quán.

Nếu vẫn dùng watermark, nên có overlap window và cơ chế upsert idempotent, nhưng overlap chỉ giảm một số rủi ro chứ không tự giải quyết delete, commit muộn hoặc transaction ordering. Cần có audit/tombstone cho delete và reconciliation sau mỗi lần apply.

### 4.4. Vì sao không nên coi ORA_ROWSCN là CDC hoàn chỉnh?

`ORA_ROWSCN` có thể cung cấp thông tin SCN liên quan đến thay đổi hàng, nhưng không phải lúc nào cũng là timestamp chính xác cho từng row. Nếu bảng không dùng `ROWDEPENDENCIES`, giá trị có thể phản ánh ở mức block. Nó cũng không tự cung cấp đầy đủ bản ghi đã bị xóa hoặc lịch sử các phiên bản cũ.

Do đó, không nên chỉ dựa vào `ORA_ROWSCN` để bảo đảm capture mọi delta cho migration quan trọng. Hãy dùng cơ chế CDC có checkpoint/redo hoặc một change log được thiết kế rõ ràng.

### 4.5. Áp dụng delta theo cách idempotent

Một thao tác delta idempotent có thể được chạy lại mà không tạo thêm tác dụng ngoài ý muốn. Với dữ liệu upsert, có thể dùng `MERGE` theo khóa ổn định:

```sql
MERGE INTO target_orders t
USING staging_orders_delta s
   ON (t.order_id = s.order_id)
WHEN MATCHED THEN
    UPDATE SET
        t.status       = s.status,
        t.total_amount = s.total_amount,
        t.updated_at   = s.updated_at
WHEN NOT MATCHED THEN
    INSERT (order_id, status, total_amount, updated_at)
    VALUES (s.order_id, s.status, s.total_amount, s.updated_at);
```

Ví dụ này chỉ minh họa upsert; phải bổ sung cột và quy tắc nghiệp vụ thực tế. Nếu có delete, cần ghi nhận tombstone hoặc sự kiện xóa và áp dụng delete theo đúng khóa. Không thể khôi phục delete chỉ bằng cách so sánh các dòng còn tồn tại nếu không có baseline hoặc log đầy đủ.

Khi delta được áp dụng nhiều lần, cần có cơ chế chống xử lý trùng như event ID duy nhất, sequence/checkpoint, unique constraint hoặc logic merge có kiểm soát. Không giả định mọi lệnh `INSERT` đều an toàn khi retry.

### 4.6. Giữ thứ tự transaction và phụ thuộc bảng

Một giao dịch nghiệp vụ có thể cập nhật nhiều bảng. Nếu delta được tách thành nhiều file hoặc batch và apply không đúng thứ tự, có thể tạm thời vi phạm khóa ngoại hoặc tạo trạng thái nghiệp vụ không hợp lệ.

- Ưu tiên công cụ CDC giữ thứ tự commit và transaction boundary.
- Nếu xử lý theo batch, xác định quan hệ cha/con và thứ tự nạp.
- Tránh chạy song song nhiều luồng delta trên cùng một khóa nếu thứ tự cập nhật quan trọng.
- Kiểm tra deadlock, conflict và lỗi apply trước khi coi delta đã hoàn tất.
- Không bỏ qua transaction lỗi chỉ để đưa lag về 0; phải có quy trình xử lý và ghi nhận.

## 5. Quản lý DDL và các đối tượng ngoài dữ liệu bảng

Trong thời gian baseline và CDC, thay đổi schema có thể làm target khác cấu trúc nguồn. Ví dụ, nguồn thêm cột mới sau khi baseline đã export; CDC có thể không tự tạo cột ở đích nếu DDL replication không được cấu hình.

Trước và trong migration:

- Thiết lập **DDL freeze** hoặc quy trình phát hành schema đồng bộ giữa nguồn và đích.
- Lập danh sách sequence, identity, trigger, procedure, package, view, synonym, materialized view và scheduler job.
- Xác định cách đồng bộ grant, role, database link, directory, network ACL, credential, wallet và external table.
- Xác định object nào được tạo bởi migration script và object nào được Data Pump tạo.
- Kiểm tra invalid object và dependency sau mỗi lần import.

Sequence và identity cần được xử lý riêng. Nếu ứng dụng tiếp tục sinh khóa ở nguồn trong thời gian baseline, sequence đích có thể thấp hơn giá trị đã dùng ở nguồn. Trước khi mở ghi tại đích, xác nhận next value an toàn và không va chạm với dữ liệu đã nạp. Không tự cập nhật dictionary table; sử dụng DDL/API phù hợp với phiên bản và quy trình ứng dụng.

Các job scheduler hoặc trigger gửi email, gọi API, phát thanh toán, đẩy message hay tạo giao dịch bên ngoài cần được kiểm soát. Trong lúc kiểm thử đích, không để các job production chạy song song và gây tác dụng kép. Chỉ bật chúng theo trình tự cutover đã phê duyệt.

## 6. Chuẩn bị trước ngày cutover

### 6.1. Khảo sát nguồn và đích

Ghi nhận tối thiểu:

- Oracle version, patch level, edition, character set, timezone file và compatibility.
- DBID, DB_NAME, DB_UNIQUE_NAME, CDB/PDB, service name và topology RAC/Data Guard nếu có.
- Schema, tablespace, datafile, LOB, partition, object dependency và dung lượng.
- Database link, directory, external table, ACL, wallet, credential và job nền.
- User, role, system privilege, object privilege, quota và profile.
- Cấu hình ứng dụng, connection pool, secret, DNS/service discovery và firewall.
- Backup, recovery, CDC, archive log retention và khả năng khôi phục.

Không nên chỉ dựa trên số lượng bảng. Những dependency ngoài database như file trên filesystem, message queue, scheduler, API, certificate và secret cũng có thể làm ứng dụng không hoạt động sau chuyển đổi.

### 6.2. Diễn tập đầy đủ

Chạy ít nhất một lần migration rehearsal với dữ liệu và tốc độ thay đổi gần với production. Đo thời gian export/import baseline, thời gian apply delta, độ trễ CDC, validation, cutover và rollback. Ghi nhận các thao tác thủ công để chuyển thành runbook có thể lặp lại.

Nếu chỉ thử trên database nhỏ, kết quả thời gian không đại diện cho production. Cần kiểm tra cả thời điểm cao tải, bảng LOB lớn, partition, transaction dài và job nền.

### 6.3. Thiết lập tiêu chí go/no-go

Tiêu chí phải đo được và có người chịu trách nhiệm xác nhận. Ví dụ:

| Nhóm | Điều kiện cho phép cutover |
|---|---|
| Baseline | Export/import hoàn tất; không thiếu dump piece; log được xử lý. |
| Delta | CDC/apply không có lỗi chưa xử lý; lag dưới ngưỡng đã thống nhất. |
| Data integrity | Khóa chính, foreign key, row count và các đối soát nghiệp vụ đạt ngưỡng. |
| Schema | Object quan trọng tồn tại, compile được; grants và quota đúng. |
| Application | Smoke test, đăng nhập, đọc/ghi giao dịch thử nghiệm và luồng tích hợp đạt. |
| Performance | Các truy vấn và luồng quan trọng nằm trong giới hạn đã chấp thuận. |
| Operations | Backup đích, monitoring, alerting, secret và quyền vận hành sẵn sàng. |
| Rollback | Runbook, thời hạn rollback và cách bảo toàn giao dịch sau cutover đã được phê duyệt. |

Không dùng một con số lag duy nhất để thay thế mọi kiểm tra. Ví dụ lag bằng 0 nhưng có transaction apply error vẫn không đạt. Ngược lại, lag nhỏ nhưng không có lỗi và nằm trong ngưỡng được chấp thuận có thể được xử lý theo kế hoạch, tùy RPO và nghiệp vụ.

## 7. Quy trình cutover có kiểm soát

### 7.1. Giai đoạn chuẩn bị

Trước cửa sổ cutover:

1. Hoàn tất baseline import trên đích.
2. Khởi động CDC/delta apply và theo dõi đến khi ổn định.
3. Hoàn tất schema, grants, sequence, service, wallet, database link và cấu hình ứng dụng.
4. Chạy validation sơ bộ và smoke test đọc trên đích.
5. Xác nhận backup nguồn và đích; bảo đảm có recovery point trước cutover.
6. Thông báo người dùng, nhóm hỗ trợ và các bên tích hợp về thời gian bảo trì.
7. Chuẩn bị lệnh dừng ghi, drain connection, apply delta cuối, đổi service và rollback.

### 7.2. Bắt đầu write freeze ở nguồn

Tại thời điểm đã thống nhất:

- Đưa ứng dụng vào maintenance mode hoặc chặn các chức năng tạo/cập nhật dữ liệu.
- Dừng hoặc tạm vô hiệu hóa batch/job có thể ghi vào schema liên quan.
- Drain connection pool và session ghi đang hoạt động theo quy trình ứng dụng.
- Xác nhận không còn transaction nghiệp vụ chưa kết thúc.
- Nếu có nhiều nguồn ghi, phải khóa tất cả producer; chỉ dừng một web application có thể chưa đủ.

Không tắt database ngay lập tức khi còn transaction đang chạy. Hãy cho giao dịch hoàn tất hoặc xử lý theo chính sách nghiệp vụ, sau đó xác nhận trạng thái ghi đã đóng.

### 7.3. Thu delta cuối cùng

Khi nguồn đã ngừng ghi:

1. Ghi nhận SCN hoặc checkpoint cuối theo cơ chế CDC.
2. Chờ Extract/transport/apply xử lý hết thay đổi đã commit trước write freeze.
3. Kiểm tra không còn lag chưa giải quyết và không có transaction apply error.
4. Nếu dùng watermark, chốt high watermark cuối và trích xuất mọi thay đổi trong phạm vi, gồm cả delete theo cơ chế đã thiết kế.
5. Ghi lại thời điểm, SCN/checkpoint và số lượng sự kiện cuối cùng.

Không mở ghi ở đích khi vẫn còn delta từ nguồn chưa áp dụng. Nếu có giao dịch lỗi, quyết định rõ cách sửa và chạy lại; không bỏ qua để đạt con số lag bằng 0 giả tạo.

### 7.4. Đối soát và kiểm tra đích

Thực hiện các kiểm tra đã định nghĩa ở phần validation. Đối soát dữ liệu nên dùng cùng mốc snapshot và cùng quy tắc lọc ở cả hai database. Nếu nguồn đã freeze, việc so sánh sẽ dễ xác định hơn.

Kiểm tra thêm:

- Sequence/identity có thể tiếp tục sinh khóa mà không va chạm.
- Scheduler job và trigger ngoài nghiệp vụ chưa được bật sớm.
- Service, connection string, wallet và credential trỏ tới đích.
- Network route và quyền tích hợp đã sẵn sàng.
- Monitoring, alerting, backup và vận hành hỗ trợ đích đã hoạt động.

### 7.5. Chuyển ứng dụng sang đích

Sau khi các gate đạt và người có thẩm quyền phê duyệt:

1. Chuyển service name, connection string, DNS hoặc cấu hình service discovery sang target theo phương án đã diễn tập.
2. Khởi động ứng dụng và connection pool mới.
3. Chạy smoke test chỉ định: đăng nhập, đọc dữ liệu, tạo giao dịch thử nghiệm an toàn, cập nhật và truy vấn lại.
4. Xác nhận giao dịch thử nghiệm không gây tác dụng bên ngoài ngoài dự kiến.
5. Mở ghi cho người dùng theo từng nhóm hoặc theo tỷ lệ nếu kiến trúc hỗ trợ.
6. Theo dõi error rate, latency, session, lock, job, CDC và dữ liệu nghiệp vụ.

Đây là thời điểm target bắt đầu có thể trở thành nguồn dữ liệu có thẩm quyền. Ghi rõ timestamp cutover và giao dịch đầu tiên ở đích.

### 7.6. Giữ nguồn trong rollback window

Trong thời gian theo dõi sau cutover:

- Giữ source ở trạng thái không nhận ghi từ ứng dụng.
- Không drop schema, datafile, database link hoặc backup cần cho rollback.
- Giữ bản backup và log đủ để khôi phục cả hai phía.
- Kiểm soát không cho hai database cùng nhận giao dịch nghiệp vụ cho cùng một tập dữ liệu.
- Theo dõi các chỉ số và tiêu chí rollback đã được phê duyệt.

Nếu source tiếp tục nhận ghi song song với target mà không có cơ chế multi-master đã thiết kế, dữ liệu sẽ phân nhánh và việc hợp nhất rất khó. Một nguồn dữ liệu có thẩm quyền phải được xác định tại mọi thời điểm.

## 8. Đối soát dữ liệu và kiểm tra ứng dụng

### 8.1. Row count theo bảng hoặc partition

So sánh số lượng dòng là bước cơ bản. Có thể lấy count ở từng bảng:

```sql
SELECT COUNT(*) AS row_count
FROM app.orders;
```

Với bảng lớn, nên so sánh theo partition, khoảng khóa hoặc nhóm thời gian để dễ xác định vùng chênh lệch. Thống kê optimizer không phải lúc nào cũng là số đếm chính xác; nếu cần bằng chứng chính xác, dùng truy vấn count phù hợp hoặc cơ chế đối soát đã thống nhất.

### 8.2. Đối soát tổng hợp nghiệp vụ

Ví dụ đối chiếu số lượng và tổng giá trị đơn hàng theo trạng thái:

```sql
SELECT status,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM app.orders
GROUP BY status
ORDER BY status;
```

Chạy cùng truy vấn ở nguồn và đích tại cùng recovery point. Có thể bổ sung min/max ngày, số lượng khách hàng duy nhất, tổng số dư, số giao dịch theo ngày và các chỉ số quan trọng khác.

### 8.3. Kiểm tra quan hệ và dữ liệu bất thường

Các kiểm tra hữu ích:

- Bản ghi con không có bản ghi cha tương ứng.
- Trùng khóa chính hoặc khóa nghiệp vụ.
- `NULL` bất thường ở cột bắt buộc.
- Giá trị trạng thái ngoài tập cho phép.
- Sequence/identity có nguy cơ tạo khóa đã tồn tại.
- Tổng tiền, số dư hoặc trạng thái thanh toán không khớp.
- LOB, file tham chiếu hoặc dữ liệu ngoài database không đầy đủ.

Ví dụ tìm đơn hàng có customer không tồn tại:

```sql
SELECT COUNT(*) AS orphan_orders
FROM app.orders o
WHERE NOT EXISTS (
    SELECT 1
    FROM app.customers c
    WHERE c.customer_id = o.customer_id
);
```

Nếu bảng có foreign key đã enable và validate, một số dạng sai lệch đã bị constraint ngăn chặn; tuy vậy, cần xác nhận constraint thực sự được bật/validate sau import. Không giả định mọi constraint đều đã được tạo hoặc kích hoạt.

### 8.4. Hash/checksum và giới hạn

Checksum hoặc hash theo khóa có thể giúp phát hiện chênh lệch ở tập dữ liệu lớn. Tuy nhiên, phải chuẩn hóa cách biểu diễn dữ liệu, xử lý `NULL`, timezone, số thập phân, CLOB/BLOB và thứ tự dòng. Hash không chứng minh tuyệt đối mọi khía cạnh nghiệp vụ; nó là một lớp kiểm tra bổ sung.

Tránh nối toàn bộ bảng thành một chuỗi khổng lồ trong một câu SQL. Nên chia theo partition hoặc khoảng khóa, tạo fingerprint ổn định và so sánh từng phần để xác định vùng sai khác.

### 8.5. Kiểm tra chức năng và hiệu năng

Smoke test tối thiểu cần đi qua các luồng nghiệp vụ quan trọng:

- Đăng nhập và xác thực.
- Tra cứu dữ liệu cũ.
- Tạo một giao dịch thử nghiệm được kiểm soát.
- Cập nhật trạng thái và đọc lại.
- Kiểm tra report, batch và API tích hợp.
- Kiểm tra quyền user/role và dữ liệu nhạy cảm.
- Kiểm tra hiệu năng truy vấn quan trọng, connection pool và lỗi ứng dụng.

Một database có thể mở thành công nhưng ứng dụng vẫn lỗi vì thiếu grant, synonym, database link, wallet, directory, ACL, job hoặc cấu hình service.

## 9. Thiết kế rollback

### 9.1. Rollback trước khi target nhận ghi

Đây là tình huống dễ nhất. Nếu target chưa nhận giao dịch nghiệp vụ và source vẫn được bảo toàn:

1. Giữ target ở maintenance/read-only hoặc chặn ghi.
2. Chuyển service/connection string trở lại source.
3. Mở lại ứng dụng và các job nguồn theo trình tự.
4. Kiểm tra giao dịch và kết nối trên source.
5. Ghi nhận nguyên nhân cutover thất bại và bảo toàn log.

Vì source không bị thay đổi trong giai đoạn target thử nghiệm, không cần hợp nhất dữ liệu mới từ target trong trường hợp này, trừ các giao dịch thử nghiệm đã cố ý ghi.

### 9.2. Rollback sau khi target đã nhận ghi

Khi target đã nhận giao dịch thật, source trở thành bản dữ liệu cũ. Chỉ đổi service quay về source sẽ làm mất giao dịch đã ghi ở target và có thể gây trùng hoặc sai trạng thái nghiệp vụ.

Trước cutover, phải chọn một trong các chiến lược:

- **Reverse replication/CDC:** chuẩn bị khả năng capture thay đổi từ target và apply ngược về source nếu rollback được kích hoạt.
- **Controlled reconciliation:** dừng ghi ở target, trích xuất và đối soát toàn bộ giao dịch mới, sau đó áp dụng vào source theo quy trình đã kiểm thử.
- **No rollback after write gate:** xác định rõ sau một mốc nghiệp vụ nhất định chỉ được forward-fix hoặc phục hồi sang một target khác; không quay về source cũ.
- **Business-approved data loss:** chỉ trong tình huống đặc biệt, người có thẩm quyền chấp thuận mất dữ liệu trong phạm vi được mô tả rõ và ghi nhận đầy đủ.

Không được giả định CDC một chiều từ source sang target có thể tự đảo chiều. Reverse replication cần được cấu hình, kiểm thử xung đột, sequence, DDL và transaction trước khi cutover. Nếu không có reverse path, phải có phương án reconciliation cụ thể hoặc quy định rõ giới hạn rollback.

### 9.3. Bảng quyết định rollback

| Tình trạng | Hành động phù hợp |
|---|---|
| Chưa chuyển service, target chưa nhận ghi | Hủy cutover, tiếp tục phục vụ từ source. |
| Target mở nhưng chỉ chạy smoke test không tạo dữ liệu nghiệp vụ | Xác nhận mọi giao dịch thử nghiệm; chuyển về source nếu không có dữ liệu cần giữ. |
| Target đã nhận giao dịch thật, reverse CDC còn hoạt động và đã xác nhận | Dừng ghi target, drain apply, đồng bộ ngược về source, đối soát rồi mới chuyển service. |
| Target đã nhận ghi nhưng không có reverse path | Dừng ghi, đánh giá reconciliation; không đổi về source trước khi có quyết định bảo toàn dữ liệu. |
| Target lỗi nghiêm trọng nhưng dữ liệu vẫn truy cập được | Cân nhắc forward-fix hoặc dựng target mới từ backup/CDC; quyết định dựa trên RTO và tính toàn vẹn. |
| Cả source và target đều không sẵn sàng | Kích hoạt DR/recovery plan, chọn recovery point theo RPO và runbook đã phê duyệt. |

### 9.4. Các bước rollback có kiểm soát

1. Incident commander hoặc người có thẩm quyền tuyên bố rollback theo tiêu chí đã định.
2. Chặn mọi giao dịch mới vào target và drain session ghi.
3. Ghi nhận thời điểm, SCN/checkpoint cuối và danh sách transaction đã commit trên target.
4. Xác định phương án bảo toàn delta target: reverse CDC, export/reconcile hoặc quyết định nghiệp vụ được phê duyệt.
5. Nếu reverse CDC: xác nhận capture/apply đã xử lý hết, không có conflict hoặc transaction lỗi; kiểm tra dữ liệu trên source.
6. Nếu reconciliation: tạo snapshot/backup target, trích xuất delta, đối chiếu khóa và áp dụng theo thứ tự transaction đã thiết kế.
7. Xác nhận source có dữ liệu cuối cùng đúng kỳ vọng, sequence an toàn, object và job phù hợp.
8. Chuyển service về source và mở ghi theo từng bước.
9. Chạy smoke test, kiểm tra lỗi và đối soát nghiệp vụ.
10. Giữ target cùng log/backup để điều tra; chỉ dọn sau khi kết thúc rollback window và được phê duyệt.

Không xóa target ngay sau khi quay lui. Target chứa bằng chứng về lỗi và các giao dịch đã phát sinh; cần giữ lại đủ lâu để điều tra và bảo toàn dữ liệu.

## 10. Các tình huống dễ làm rollback thất bại

### 10.1. Hai database cùng nhận ghi

Nếu cả source và target cùng nhận giao dịch cho cùng một nghiệp vụ, chúng có thể phát sinh hai phiên bản khác nhau. Khóa chính có thể trùng, số dư có thể sai và thứ tự sự kiện không thể khôi phục bằng một lần export đơn giản.

Hãy chỉ định một write authority duy nhất. Nếu cần dual-write hoặc active-active, đó phải là kiến trúc được thiết kế với conflict resolution, transaction semantics và kiểm thử riêng; không phải giải pháp tạm thời cho cutover.

### 10.2. Không giữ đủ archive log hoặc CDC trail

Nếu archive log bị xóa trước khi Extract đọc xong, CDC có thể mất khả năng tiếp tục từ checkpoint. Nếu trail bị purge hoặc storage đầy, delta có thể bị gián đoạn. Trước migration, xác định retention đủ dài cho tốc độ thay đổi và thời gian xử lý sự cố, đồng thời cảnh báo khi lag tăng.

### 10.3. Thay đổi schema trong lúc đồng bộ

DDL có thể làm source và target khác cấu trúc, khiến apply lỗi hoặc dữ liệu bị bỏ qua. Thiết lập DDL freeze hoặc quy trình triển khai DDL đồng bộ; kiểm tra DDL support của CDC tool và xử lý các thay đổi không được tự động capture.

### 10.4. Sequence và side effect ngoài database

Giao dịch ở target có thể gọi dịch vụ thanh toán, gửi email hoặc phát message. Khi rollback database, các side effect đó không tự đảo ngược. Cần kiểm soát các job và tích hợp trong smoke test; dùng sandbox hoặc cơ chế suppress side effect trong môi trường kiểm thử.

Sequence cũng có thể đã tăng ở target dù giao dịch bị rollback. Khi chuyển về source, phải xác nhận giá trị sequence/identity và bảo đảm không tạo khóa trùng. Với giao dịch đã commit, phải bảo toàn thứ tự và định danh đã cấp.

### 10.5. Không định nghĩa điểm hết hạn rollback

Giữ source cũ quá lâu làm tăng chi phí và nguy cơ nhầm lẫn; xóa source quá sớm làm mất khả năng quay lui. Hãy xác định rollback window, điều kiện kết thúc, người phê duyệt và hành động cuối kỳ. Sau khi hết window, source có thể được lưu trữ hoặc loại bỏ theo quy trình đã phê duyệt.

## 11. Runbook mẫu theo dòng thời gian

Một runbook cutover cần ghi người thực hiện, người xác nhận, lệnh/công cụ, đầu ra mong đợi và thời hạn cho từng bước. Ví dụ:

| Giai đoạn | Công việc | Gate/bằng chứng |
|---|---|---|
| T-14 ngày | Khảo sát, xác định schema, dependency, dung lượng và phương án delta. | Phạm vi và RPO/RTO được phê duyệt. |
| T-7 ngày | Diễn tập baseline, delta, validation và rollback. | Thời gian thực tế và lỗi đã được ghi nhận. |
| T-1 ngày | Xác nhận backup, CDC lag, dung lượng, quyền, lịch job và liên hệ. | Checklist sẵn sàng được ký xác nhận. |
| T-30 phút | Thông báo maintenance, chuẩn bị service và theo dõi nguồn/đích. | Người điều phối xác nhận bắt đầu. |
| T0 | Bật write freeze, dừng job ghi và drain session. | Không còn transaction ghi nguồn. |
| T+ | Chốt SCN/checkpoint và apply delta cuối. | Lag bằng 0 theo công cụ, không còn lỗi apply. |
| T+ | Đối soát dữ liệu, kiểm tra schema và ứng dụng. | Tất cả acceptance gate đạt. |
| T+ | Phê duyệt go/no-go, chuyển service sang target. | Cutover point được ghi nhận. |
| Sau cutover | Smoke test, mở ghi, theo dõi và giữ source. | Target hoạt động trong ngưỡng, rollback window bắt đầu. |
| Kết thúc window | Xác nhận ổn định, chốt backup và xử lý source cũ. | Chủ hệ thống phê duyệt kết thúc rollback. |

Mốc thời gian chỉ là ví dụ. Runbook thực tế cần thời lượng dựa trên diễn tập và quy trình change management của tổ chức.

## 12. Mẫu ghi nhận kết quả cutover và rollback

Mỗi đợt migration nên lưu một bản ghi gồm:

| Trường | Nội dung cần ghi |
|---|---|
| Source/target | DB_NAME, DB_UNIQUE_NAME, DBID, service, PDB và version. |
| Baseline | SCN/time, Data Pump job, dump set, log và thời điểm hoàn tất. |
| Delta | Công cụ, checkpoint bắt đầu/kết thúc, lag, số transaction và lỗi apply. |
| Write freeze | Thời điểm bắt đầu, người xác nhận, session/job đã dừng. |
| Validation | Row count, aggregate, key/constraint, application smoke test và kết quả. |
| Go/no-go | Quyết định, người phê duyệt và lý do. |
| Cutover | Timestamp chuyển service, giao dịch đầu tiên ở target. |
| Rollback | Điều kiện, thời điểm, reverse/reconciliation method và kết quả nếu kích hoạt. |
| RPO/RTO | Recovery point và thời gian dịch vụ trở lại. |
| Follow-up | Lỗi còn lại, owner, deadline và bằng chứng đóng việc. |

Không ghi mật khẩu, key material hoặc dữ liệu cá nhân thật vào báo cáo. Dùng ID tham chiếu secret và lưu tài liệu ở vị trí có kiểm soát.

## 13. Nguyên tắc vận hành cần nhớ

- Xác định một baseline SCN nhất quán và ghi lại rõ ràng.
- Data Pump tạo baseline logic; nó không tự thay thế CDC cho thay đổi phát sinh sau baseline.
- Delta phải bao gồm insert, update, delete và những thay đổi cấu trúc/định danh có liên quan.
- Căn chỉnh checkpoint CDC với baseline theo cơ chế được công cụ hỗ trợ; không tự suy đoán ranh giới.
- Giữ archive log/trail đủ lâu để CDC theo kịp và phục hồi sau gián đoạn.
- Chỉ có một write authority cho cùng tập dữ liệu trong quá trình cutover.
- Đóng băng ghi, drain transaction và apply delta cuối trước khi mở ghi ở target.
- Đặt acceptance gate có thể đo và có người phê duyệt.
- Nếu target đã nhận ghi, không quay về source cũ trước khi bảo toàn giao dịch target.
- Kiểm tra sequence, job, trigger, database link và side effect ngoài database.
- Diễn tập cả cutover lẫn rollback trên môi trường tương đương production.
- Giữ source, backup và log trong rollback window; chỉ dọn sau phê duyệt.

## Kết luận

Một đợt migration an toàn cần phối hợp baseline nhất quán, cơ chế đồng bộ delta, write freeze, validation và cutover có cổng phê duyệt. SCN giúp xác định mốc snapshot; CDC hoặc change log giúp chuyển insert, update và delete phát sinh sau đó. Khi chuyển ứng dụng, cần bảo đảm nguồn đã ngừng ghi, delta đã được áp dụng và các kiểm tra dữ liệu/ứng dụng đạt yêu cầu. Phương án rollback phải được thiết kế trước, đặc biệt cho thời điểm target đã nhận giao dịch thật: cần reverse replication hoặc reconciliation đã kiểm thử để bảo toàn dữ liệu. Diễn tập toàn bộ quy trình và ghi nhận RPO/RTO mới chứng minh được kế hoạch có thể vận hành khi sự cố xảy ra.
