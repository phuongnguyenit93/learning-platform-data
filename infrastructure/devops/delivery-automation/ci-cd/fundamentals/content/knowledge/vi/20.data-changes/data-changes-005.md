# Tách đổi lược đồ với chuyển đổi dữ liệu tốn nhiều thời gian

## 1. Vì sao cần tách schema migration và data migration?

Một thay đổi ứng dụng có thể yêu cầu thay đổi cả cấu trúc database lẫn dữ liệu đang được lưu. Ví dụ, hệ thống cần đổi cột trạng thái đơn hàng từ chuỗi tự do sang mã trạng thái chuẩn, chuyển dữ liệu từ một cột cũ sang cấu trúc mới, hoặc tách một bảng lớn thành nhiều bảng chuyên biệt.

Hai công việc này có đặc tính vận hành khác nhau:

- **Schema migration** thay đổi cấu trúc database: thêm cột, bảng, index, constraint hoặc đổi kiểu dữ liệu.
- **Data migration** chuyển đổi những bản ghi hiện có sang cách biểu diễn mới, thường phải đọc và ghi một lượng dữ liệu lớn.

Nếu gộp cả hai vào một giao dịch triển khai duy nhất, thời gian phát hành có thể kéo dài, khóa bảng, tăng tải database và làm cho rollback ứng dụng trở nên khó khăn. Một migration kéo dài cũng có thể khiến pipeline chờ hàng giờ, trong khi ứng dụng cũ và mới cần cùng hoạt động trong thời gian chuyển tiếp.

Giải pháp là tách việc mở rộng cấu trúc, chuyển đổi dữ liệu và loại bỏ cấu trúc cũ thành các giai đoạn độc lập. Ứng dụng cần tương thích với schema trong suốt quá trình chuyển đổi. Data migration chạy theo lô, có thể tạm dừng và tiếp tục, đồng thời tạo đủ bằng chứng để quyết định khi nào chuyển luồng đọc/ghi sang cấu trúc mới.

Trong phạm vi **DEVOPS_CI_CD_FUNDAMENTALS**, cách làm này giúp pipeline phát hành có thể truy vết, kiểm soát thời gian triển khai, xác minh dữ liệu, bảo vệ tính sẵn sàng và chuẩn bị phương án khôi phục. Mục tiêu không chỉ là cập nhật database thành công, mà là giữ cho ứng dụng hoạt động đúng trong suốt quá trình thay đổi.

## 2. Phân biệt schema migration và data migration

| Khía cạnh | Schema migration | Data migration |
|---|---|---|
| Đối tượng | Cấu trúc database | Nội dung các bản ghi |
| Thao tác | CREATE, ALTER, ADD INDEX, ADD CONSTRAINT | Đọc, ánh xạ, chuẩn hóa, cập nhật hoặc sao chép dữ liệu |
| Thời gian | Có thể ngắn, nhưng phụ thuộc engine và loại DDL | Có thể kéo dài từ phút đến nhiều giờ hoặc nhiều ngày |
| Tác động | Lock, metadata change, rewrite bảng hoặc index | CPU, I/O, WAL/redo log, replication lag, row lock |
| Cách triển khai | Migration versioned, kiểm tra lock và tương thích | Job có batch, checkpoint, retry, throttle và validation |
| Khôi phục | Có thể cần migration mới để đảo cấu trúc | Thường cần forward-fix, dữ liệu bù trừ hoặc backup/PITR |
| Điều kiện hoàn tất | Cấu trúc mới tồn tại và được kiểm tra | Dữ liệu đã chuyển đủ, đúng và được xác minh |

Ví dụ, thêm cột **normalized_status** là thay đổi schema. Điền giá trị mới cho hàng chục triệu đơn hàng từ cột **legacy_status** là data migration. Hai việc liên quan nhưng không nên mặc định thực hiện cùng một thời điểm.

Một lệnh ALTER TABLE có thể nhanh ở một database version nhưng gây khóa hoặc rewrite bảng ở version khác. Tương tự, một câu UPDATE đơn giản có thể tạo lượng WAL rất lớn nếu chạy trên toàn bộ bảng. Vì vậy, cần đánh giá riêng chi phí DDL và chi phí chuyển dữ liệu.

## 3. Nguyên tắc tương thích trong suốt quá trình chuyển đổi

Trong một đợt phát hành, có thể đồng thời tồn tại:

- Ứng dụng phiên bản cũ đang xử lý request.
- Ứng dụng phiên bản mới vừa được triển khai.
- Worker chạy data migration.
- Consumer hoặc job nền vẫn đọc schema cũ.
- Replica database đang đồng bộ dữ liệu.

Do đó, schema mới cần được thiết kế để phiên bản cũ không bị lỗi ngay khi cấu trúc được mở rộng. Tương tự, phiên bản mới cần hoạt động được trong lúc một phần dữ liệu chưa được chuyển đổi.

Một nguyên tắc hữu ích là **expand-contract**:

- **Expand:** mở rộng schema để hỗ trợ cả cách cũ và cách mới.
- **Migrate:** chuyển dữ liệu dần dần trong khi hệ thống vẫn hoạt động.
- **Switch:** chuyển ứng dụng sang đọc hoặc ghi theo cấu trúc mới.
- **Contract:** chỉ loại bỏ cấu trúc cũ khi không còn thành phần nào cần nó.

~~~mermaid
flowchart TD
    A["Schema cũ và ứng dụng cũ"] --> B["EXPAND: thêm cấu trúc mới tương thích"]
    B --> C["Deploy ứng dụng tương thích cả hai schema"]
    C --> D["BACKFILL: chuyển dữ liệu theo lô"]
    D --> E["VALIDATE: đối chiếu và kiểm tra invariant"]
    E --> F{"Dữ liệu đã đạt điều kiện?"}
    F -- "Chưa" --> D
    F -- "Đạt" --> G["SWITCH: chuyển đọc/ghi sang cấu trúc mới"]
    G --> H["Theo dõi và giữ thời gian an toàn"]
    H --> I["CONTRACT: bỏ cấu trúc cũ"]
    I --> J["Hoàn tất"]
~~~

Không phải dự án nào cũng cần dual-write hoặc backfill. Nếu bảng nhỏ và có thể chuyển đổi trong một giao dịch ngắn với lock được kiểm soát, một migration đơn giản có thể phù hợp. Expand-contract đặc biệt hữu ích khi dữ liệu lớn, ứng dụng cần hoạt động liên tục hoặc nhiều phiên bản cùng tồn tại.

## 4. Ma trận tương thích ứng dụng và schema

Trước khi triển khai, cần lập ma trận xác định phiên bản ứng dụng nào có thể hoạt động với từng trạng thái schema.

Ví dụ khi đổi từ cột **legacy_status** sang **normalized_status**:

| Trạng thái database | Ứng dụng cũ | Ứng dụng mới | Ghi chú |
|---|---|---|---|
| Chỉ có cột cũ | Hoạt động | Chưa triển khai được | Trạng thái ban đầu |
| Đã thêm cột mới, chưa backfill | Hoạt động | Hoạt động nếu xử lý NULL | Giai đoạn expand |
| Hai cột được đồng bộ, backfill đang chạy | Hoạt động | Hoạt động | Giai đoạn chuyển tiếp |
| Dữ liệu mới đã đầy đủ, ứng dụng đọc cột mới | Có thể hoạt động nếu cột cũ còn được duy trì | Hoạt động | Giai đoạn switch |
| Cột cũ đã bị loại bỏ | Không hoạt động | Hoạt động | Chỉ thực hiện sau khi mọi consumer cũ đã dừng |

Ma trận này giúp xác định thứ tự phát hành. Nếu phiên bản ứng dụng mới đọc cột mới nhưng schema chưa có cột đó, deploy sẽ thất bại. Nếu schema loại bỏ cột cũ trước khi các instance cũ được thay thế, request đang chạy có thể lỗi.

Cần tính cả worker nền, batch job, báo cáo, công cụ quản trị, consumer message và các ứng dụng khác cùng truy cập database. Không chỉ web service mới là consumer của schema.

## 5. Giai đoạn Expand: thêm cấu trúc mới mà chưa phá cấu trúc cũ

Giai đoạn expand tạo ra cấu trúc mới theo cách tương thích ngược.

Ví dụ:

~~~sql
ALTER TABLE orders
ADD COLUMN normalized_status VARCHAR(32);
~~~

Sau bước này, cột cũ vẫn tồn tại và ứng dụng cũ tiếp tục đọc/ghi như trước. Cột mới có thể chứa NULL trong thời gian đầu.

Các việc thường làm trong giai đoạn expand:

- Thêm cột mới nullable.
- Tạo bảng mới hoặc bảng ánh xạ.
- Thêm index theo cách phù hợp với database engine.
- Thêm constraint ở chế độ chưa gây gián đoạn nếu engine hỗ trợ.
- Thêm metadata hoặc version field cần thiết.
- Triển khai cấu trúc mà ứng dụng cũ có thể bỏ qua.

Không nên vội thêm NOT NULL hoặc xóa cột cũ khi dữ liệu chưa được chuyển đổi và mọi phiên bản ứng dụng chưa tương thích. Constraint có thể được thêm sau khi backfill và validation đạt.

### 5.1. Đánh giá DDL có khóa hay không

Một câu ALTER TABLE không mặc nhiên là thao tác tức thời. Tác động phụ thuộc database engine, phiên bản, kiểu thay đổi, kích thước bảng và transaction đang chạy.

Trước khi áp dụng production cần xem:

- Loại lock mà DDL yêu cầu.
- DDL có rewrite toàn bộ bảng hoặc index không.
- Thời gian giữ lock và ảnh hưởng tới query đang chạy.
- Có thể dùng thao tác online/concurrent không.
- Có timeout để tránh chờ lock vô hạn không.
- Replica có theo kịp lượng log phát sinh không.

Ví dụ PostgreSQL hỗ trợ CREATE INDEX CONCURRENTLY để giảm chặn ghi trong nhiều trường hợp, nhưng lệnh này có giới hạn và không được chạy bên trong transaction block thông thường. Nếu thất bại, index có thể còn ở trạng thái invalid và cần được xử lý trước khi thử lại. Cần kiểm tra tài liệu và hành vi theo phiên bản database thực tế.

### 5.2. Tạo constraint theo từng bước

Với bảng lớn, việc thêm constraint có thể cần quét dữ liệu. Nếu database hỗ trợ kiểm tra constraint chưa xác thực, nhóm có thể tạo constraint trước, xác minh dữ liệu riêng rồi validate sau.

Ví dụ trong PostgreSQL:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT orders_normalized_status_check
CHECK (
  normalized_status IS NULL
  OR normalized_status IN ('PENDING', 'PAID', 'CANCELLED')
) NOT VALID;

ALTER TABLE orders
VALIDATE CONSTRAINT orders_normalized_status_check;
~~~

Cú pháp và mức độ khóa cần được kiểm tra theo phiên bản. Cách tiếp cận nhiều bước giúp tách thời điểm tạo quy tắc khỏi thời điểm xác minh toàn bộ dữ liệu hiện có.

## 6. Triển khai ứng dụng tương thích trước khi chuyển dữ liệu

Sau khi schema mới tồn tại, triển khai phiên bản ứng dụng có thể làm việc với cả dữ liệu cũ và mới.

Một phiên bản chuyển tiếp có thể:

- Đọc cột cũ khi cột mới chưa có giá trị.
- Ghi cột cũ và cột mới trong cùng transaction.
- Xử lý NULL hoặc giá trị chưa được chuyển đổi.
- Có metric cho số bản ghi còn thiếu dữ liệu mới.
- Chưa yêu cầu cột mới phải NOT NULL.
- Không giả định toàn bộ worker hoặc instance khác đã được nâng cấp.

Ví dụ logic đọc chuyển tiếp:

~~~sql
SELECT
  CASE
    WHEN normalized_status IS NOT NULL THEN normalized_status
    ELSE map_legacy_status(legacy_status)
  END AS effective_status
FROM orders
WHERE id = :order_id;
~~~

Hàm map trong ví dụ đại diện cho quy tắc chuyển đổi được ứng dụng định nghĩa. Cần bảo đảm cùng một quy tắc được dùng trong backfill và trong đường đọc tạm thời, tránh trường hợp hai nơi ánh xạ một giá trị cũ thành hai kết quả khác nhau.

Nếu ứng dụng ghi cả hai cột, nên thực hiện trong cùng transaction của database khi cả hai thuộc cùng một database. Nếu ghi sang hai hệ thống độc lập, dual-write trực tiếp có thể tạo trạng thái một bên thành công, bên còn lại thất bại. Khi đó cần cân nhắc transactional outbox, CDC, retry có idempotency hoặc quy trình đối soát.

## 7. Data backfill: chuyển đổi dữ liệu theo lô

Backfill là quá trình đọc dữ liệu hiện có và điền hoặc chuyển đổi sang cấu trúc mới. Với bảng lớn, không nên mặc định chạy một UPDATE duy nhất trên toàn bảng.

Một backfill theo lô có thể:

1. Chọn một khoảng khóa chính hoặc một nhóm bản ghi.
2. Đọc dữ liệu nguồn.
3. Áp dụng quy tắc chuyển đổi.
4. Ghi giá trị đích cho nhóm đó.
5. Commit transaction.
6. Lưu checkpoint.
7. Tiếp tục lô tiếp theo.

Lợi ích:

- Giới hạn thời gian giữ lock.
- Giảm kích thước transaction.
- Hạn chế WAL/redo log tăng đột biến.
- Có thể điều chỉnh tốc độ theo tải.
- Dễ retry và tiếp tục sau khi worker dừng.
- Có thể theo dõi tiến độ và ước tính thời gian còn lại.

Kích thước batch không nên cố định cho mọi database. Lô 1.000 bản ghi có thể phù hợp ở hệ thống này nhưng quá nhỏ hoặc quá lớn ở hệ thống khác. Cần đo thời gian transaction, lock wait, replication lag, I/O và độ trễ request để điều chỉnh.

## 8. Idempotency và khả năng tiếp tục

Một data migration chạy nhiều giờ có thể bị dừng do deploy, mất kết nối, hết thời gian chạy hoặc cần tạm ngưng để giảm tải. Vì vậy, job phải có khả năng chạy lại mà không làm hỏng dữ liệu.

**Idempotent migration** có nghĩa là chạy lại cùng một bước trên dữ liệu đã xử lý không tạo ra kết quả sai hoặc thay đổi ngoài dự kiến.

Ví dụ cập nhật chỉ những bản ghi chưa có giá trị mới:

~~~sql
UPDATE orders
SET normalized_status =
  CASE legacy_status
    WHEN 'new' THEN 'PENDING'
    WHEN 'settled' THEN 'PAID'
    WHEN 'void' THEN 'CANCELLED'
    ELSE 'UNKNOWN'
  END
WHERE id >= :start_id
  AND id < :end_id
  AND normalized_status IS NULL;
~~~

Điều kiện NULL giúp tránh ghi đè giá trị mới do ứng dụng đã tạo trong lúc backfill chạy. Tuy nhiên, cần xác định rõ trường hợp UNKNOWN có được chấp nhận hay phải đưa vào hàng chờ xử lý thủ công.

Một checkpoint có thể lưu:

- Migration ID và version.
- Phạm vi khóa đã hoàn thành.
- Batch cuối cùng đã commit.
- Số bản ghi đọc, cập nhật, bỏ qua và lỗi.
- Thời điểm bắt đầu, lần tiếp tục gần nhất.
- Phiên bản quy tắc chuyển đổi.

Checkpoint chỉ được cập nhật sau khi batch dữ liệu đã commit thành công. Nếu checkpoint được ghi trước dữ liệu, job có thể bỏ qua một lô chưa được xử lý. Nếu dữ liệu commit nhưng checkpoint chưa cập nhật, batch có thể chạy lại; vì vậy logic vẫn cần idempotent.

### 8.1. Chọn checkpoint ổn định

Có thể dùng khóa chính tăng dần, khóa phân vùng hoặc một tập hợp ID. Không nên chỉ dùng OFFSET lớn trên bảng thay đổi liên tục vì việc quét có thể chậm và thứ tự bản ghi có thể dịch chuyển.

Với dữ liệu phát sinh mới trong lúc backfill, cần có chiến lược bao phủ:

- Ghi kép từ ứng dụng mới.
- CDC hoặc event stream.
- Quét lại các bản ghi được cập nhật sau mốc bắt đầu.
- Một lần reconciliation cuối trước cutover.

Nếu chỉ backfill các ID đã tồn tại tại thời điểm bắt đầu, bản ghi mới được tạo sau đó có thể bị bỏ sót nếu ứng dụng chưa ghi vào cột mới.

## 9. Giới hạn tải và tránh ảnh hưởng database

Data migration cạnh tranh tài nguyên với request của ứng dụng. Một job backfill chạy quá nhanh có thể làm tăng latency, replication lag, lock wait hoặc dung lượng log.

Các biện pháp kiểm soát:

- Giới hạn số batch chạy đồng thời.
- Commit mỗi batch thay vì giữ transaction lớn.
- Đặt timeout và retry có backoff.
- Điều chỉnh batch size theo tải thực tế.
- Tạm dừng khi latency, lock wait hoặc replication lag vượt ngưỡng.
- Chạy vào thời điểm tải thấp nếu nghiệp vụ cho phép.
- Tránh full table scan lặp lại không cần thiết.
- Theo dõi dung lượng WAL/redo log và storage.
- Có giới hạn tốc độ đọc/ghi.
- Chọn index hỗ trợ điều kiện lọc của backfill.

Một migration có thể tự điều chỉnh tốc độ. Ví dụ, nếu replica lag tăng hoặc latency của request vượt ngưỡng, worker giảm batch size hoặc chờ một khoảng thời gian trước khi tiếp tục.

Không nên dùng sleep cố định như cơ chế kiểm soát duy nhất. Tốt hơn là đọc tín hiệu thực tế và điều chỉnh theo policy.

## 10. Dual-write, CDC và transactional outbox

Trong giai đoạn chuyển tiếp, hệ thống có thể cần giữ hai biểu diễn dữ liệu đồng bộ.

### 10.1. Dual-write trong cùng database

Nếu cả hai cột nằm trong cùng một database và cùng transaction, ứng dụng có thể ghi cả hai:

~~~sql
UPDATE orders
SET legacy_status = :legacy_value,
    normalized_status = :normalized_value
WHERE id = :order_id;
~~~

Cách này đơn giản nhưng mọi đường ghi đều phải được cập nhật: API, worker, batch, admin tool và script vận hành. Nếu một consumer chỉ ghi cột cũ, cột mới sẽ bị thiếu hoặc stale.

Có thể bổ sung metric hoặc constraint để phát hiện hai cột không đồng nhất. Không nên duy trì dual-write lâu hơn cần thiết vì nó tăng độ phức tạp và tạo thêm cơ hội sai lệch.

### 10.2. CDC khi dữ liệu cần đồng bộ giữa hệ thống

Change Data Capture (CDC) đọc các thay đổi từ log database hoặc cơ chế tương đương rồi chuyển chúng sang nơi khác. CDC hữu ích khi dữ liệu cần được sao chép hoặc biến đổi sang một kho mới mà không phải chặn mọi request.

Cần chú ý:

- Thứ tự sự kiện và khả năng phát lại.
- Event có thể được gửi nhiều lần.
- Consumer phải idempotent.
- Schema của event cần tương thích.
- Có cơ chế phát hiện lag và dead-letter.
- Đối soát số bản ghi và nội dung sau đồng bộ.

### 10.3. Transactional outbox

Khi ứng dụng cần cập nhật database và phát sự kiện, ghi trực tiếp database rồi publish message riêng có thể tạo lỗi một nửa. Transactional outbox ghi thay đổi nghiệp vụ và bản ghi sự kiện vào cùng transaction; một worker sau đó phát sự kiện từ outbox.

Outbox giúp tránh mất sự kiện giữa hai thao tác độc lập, nhưng consumer vẫn cần xử lý duplicate và retry. Nó không tự đảm bảo mọi hệ thống downstream đã được cập nhật ngay lập tức.

## 11. Validate dữ liệu trước khi chuyển luồng đọc

Không nên chuyển ứng dụng sang đọc cấu trúc mới chỉ vì backfill báo đã xử lý hết batch. Cần xác minh dữ liệu.

Một số kiểm tra:

- Số lượng bản ghi nguồn và đích.
- Số bản ghi còn NULL ở cột mới.
- Số giá trị không nằm trong tập cho phép.
- Số bản ghi không ánh xạ được.
- Tỷ lệ bản ghi được chuyển đổi thành công.
- Tổng hoặc checksum trên các trường phù hợp.
- Các invariant nghiệp vụ, ví dụ tổng tiền, số lượng item hoặc quan hệ khóa ngoại.
- So sánh kết quả đọc cũ và mới trên một mẫu đủ đại diện.

Ví dụ truy vấn kiểm tra:

~~~sql
SELECT COUNT(*) AS missing_new_status
FROM orders
WHERE normalized_status IS NULL;

SELECT normalized_status, COUNT(*)
FROM orders
GROUP BY normalized_status
ORDER BY normalized_status;
~~~

Với bảng lớn, COUNT hoặc phép so sánh toàn bộ có thể tốn tài nguyên. Có thể dùng phân vùng, khoảng khóa, thống kê theo batch hoặc job đối soát riêng. Cần hiểu giới hạn của phép kiểm tra: số lượng bằng nhau không chứng minh nội dung từng bản ghi giống nhau.

### 11.1. Shadow read và so sánh kết quả

Trước khi chuyển hoàn toàn, ứng dụng có thể đọc cả cách cũ và cách mới nhưng chỉ trả kết quả từ nguồn cũ. Kết quả mới được so sánh ở chế độ shadow.

Cần:

- Không để shadow read tạo side effect.
- Không nhân đôi thao tác ghi hoặc giao dịch.
- So sánh dữ liệu đã chuẩn hóa.
- Ghi mismatch mà không lộ thông tin nhạy cảm.
- Đặt giới hạn sampling để không làm tăng tải quá mức.
- Phân loại mismatch theo nguyên nhân.

Khi mismatch đã về mức chấp nhận được và các kiểm tra dữ liệu đạt, nhóm mới chuyển read path sang cấu trúc mới.

## 12. Switch: chuyển ứng dụng sang cấu trúc mới

Switch là thời điểm ứng dụng bắt đầu coi cấu trúc mới là nguồn đọc chính hoặc chuyển luồng ghi sang mô hình mới.

Có thể sử dụng feature flag hoặc cấu hình có version để:

- Chuyển một nhóm request sang read path mới.
- Bật theo tenant hoặc cohort.
- Tăng dần phạm vi.
- Tạm dừng nếu mismatch hoặc latency tăng.
- Quay lại read path cũ khi vẫn còn dữ liệu tương thích.

Trước switch cần xác nhận:

- Backfill đã đạt điều kiện hoàn tất.
- Dữ liệu mới phát sinh trong thời gian backfill đã được đồng bộ.
- Các writer đều duy trì đúng invariant.
- Shadow read hoặc reconciliation không còn mismatch vượt ngưỡng.
- Phiên bản ứng dụng cũ không còn được phép ghi theo cách làm mất đồng bộ.
- Có kế hoạch rollback hoặc forward-fix.

Sau switch, vẫn nên giữ cột cũ trong một khoảng an toàn nếu nó còn cần cho rollback hoặc consumer cũ. Không nên xóa cấu trúc cũ ngay trong cùng release chuyển đọc.

## 13. Contract: loại bỏ cấu trúc cũ ở giai đoạn riêng

Contract là bước loại bỏ những cấu trúc không còn được sử dụng: cột cũ, bảng cũ, index dư thừa, compatibility code hoặc luồng dual-write.

Chỉ thực hiện khi:

- Mọi instance ứng dụng đã chuyển sang phiên bản mới.
- Worker, batch job, report và consumer không còn đọc/ghi cấu trúc cũ.
- Không còn query hoặc dashboard phụ thuộc cột cũ.
- Dữ liệu mới đã được xác minh.
- Thời gian rollback trực tiếp đã kết thúc hoặc có kế hoạch thay thế.
- Có backup và phương án khôi phục phù hợp.
- DDL đã được đánh giá lock và thời gian thực thi.

Contract thường nên nằm trong một release riêng. Điều này giữ khoảng thời gian đủ dài để quan sát và phát hiện consumer bị bỏ sót.

Một thay đổi phá hủy như DROP COLUMN không nên được xem là bước rollback đơn giản. Sau khi xóa, việc khôi phục dữ liệu có thể cần backup hoặc phục hồi điểm thời gian.

## 14. Tách migration dài khỏi thời gian deploy ứng dụng

Không nên để mỗi replica ứng dụng tự chạy cùng một data migration dài trong lúc khởi động. Điều đó có thể gây:

- Nhiều instance cùng chạy backfill.
- Startup timeout hoặc readiness thất bại.
- Lock contention.
- Khó kiểm soát retry và tiến độ.
- Triển khai không ổn định khi rolling update tạo thêm instance.

Nên tách thành các loại job:

1. **Schema migration job:** thực hiện DDL cần thiết, thường ngắn và có kiểm soát.
2. **Backfill job:** chuyển dữ liệu theo lô, chạy độc lập và có thể pause/resume.
3. **Application deployment:** triển khai phiên bản tương thích.
4. **Validation job:** đối soát và kiểm tra invariant.
5. **Cutover job:** bật read/write path mới sau khi được phê duyệt.
6. **Contract job:** loại bỏ cấu trúc cũ trong một đợt riêng.

Job migration cần cơ chế chỉ một worker điều phối cho mỗi migration hoặc partition. Có thể dùng advisory lock, lease hoặc lock record trong database. Lock cần có timeout và cơ chế xử lý worker chết để tránh khóa vĩnh viễn.

## 15. Version hóa và quản lý migration script

Migration script cần được quản lý như mã nguồn:

- Mỗi migration có ID hoặc version duy nhất.
- Lưu trong repository cùng ứng dụng hoặc repository database được quản lý.
- Review thay đổi và kiểm thử trước khi chạy production.
- Script đã áp dụng không bị sửa lại tùy tiện.
- Ghi checksum hoặc metadata để phát hiện file migration bị thay đổi.
- Lưu trạng thái đã chạy, thời điểm và kết quả.
- Tách migration schema khỏi data backfill dài nếu khác vòng đời.
- Có owner và runbook cho migration quan trọng.

Các công cụ như Flyway hoặc Liquibase cung cấp lịch sử migration và cơ chế quản lý version. Tuy nhiên, công cụ không tự làm cho một câu SQL an toàn. Nhóm vẫn phải đánh giá lock, transaction, tính tương thích và khả năng tiếp tục.

Nếu migration đã chạy ở một môi trường, không nên chỉnh sửa file cũ rồi mong các môi trường khác tự có cùng lịch sử. Hãy tạo migration mới để sửa sai hoặc bổ sung thay đổi. Điều này giữ audit trail và tránh checksum mismatch.

## 16. Kiểm thử migration trước production

Migration cần được kiểm tra trên dữ liệu có cấu trúc và quy mô gần thực tế.

Các lớp kiểm thử:

- **Unit test cho mapping:** mỗi giá trị cũ ánh xạ đúng sang giá trị mới.
- **Schema test:** DDL tạo cấu trúc đúng và có thể chạy trên database version mục tiêu.
- **Compatibility test:** phiên bản ứng dụng cũ và mới hoạt động với schema trong giai đoạn chuyển tiếp.
- **Backfill test:** batch có thể chạy lại, resume và xử lý bản ghi mới đồng thời.
- **Load test:** đo lock, latency, I/O, log growth và replication lag.
- **Data validation test:** kiểm tra count, null, uniqueness, foreign key và invariant nghiệp vụ.
- **Failure test:** worker bị kill giữa batch, mất kết nối, retry và tiếp tục từ checkpoint.
- **Rollback/forward test:** xác minh phương án khôi phục trong điều kiện dữ liệu thực tế.

Một bộ dữ liệu nhỏ có thể không bộc lộ vấn đề hiệu năng của bảng hàng chục triệu dòng. Cần thử trên dữ liệu đại diện hoặc môi trường staging đã được làm sạch và bảo vệ.

## 17. Tích hợp vào pipeline CI/CD

Pipeline nên biểu diễn rõ các giai đoạn và dependency giữa chúng.

~~~mermaid
flowchart TD
    A["Pull request"] --> B["Review migration script"]
    B --> C["Schema compatibility test"]
    B --> D["Mapping và backfill test"]
    C --> E["Build release artifact"]
    D --> E
    E --> F["Expand schema"]
    F --> G["Deploy ứng dụng tương thích"]
    G --> H["Backfill job có checkpoint"]
    H --> I["Data validation"]
    I --> J{"Gate đạt?"}
    J -- "Chưa" --> K["Hold, điều tra và tiếp tục"]
    J -- "Đạt" --> L["Phê duyệt cutover"]
    L --> M["Switch read/write"]
    M --> N["Theo dõi"]
    N --> O["Contract ở release riêng"]
~~~

Thứ tự cụ thể có thể thay đổi tùy cách triển khai và mức tương thích. Với nhiều hệ thống, schema expand cần chạy trước khi deploy ứng dụng mới. Backfill có thể chạy song song sau khi writer tương thích đã được triển khai. Contract luôn chờ đến khi mọi consumer cũ được loại bỏ.

### 17.1. Ví dụ pipeline dạng mã giả

~~~yaml
pipeline:
  validate:
    steps:
      - check_migration_version
      - test_schema_compatibility
      - test_mapping_rules
      - test_backfill_idempotency

  release:
    steps:
      - build_once
      - publish_immutable_artifact

  expand:
    requires:
      - release
    steps:
      - acquire_migration_lock
      - apply_expand_schema
      - verify_schema
      - release_migration_lock

  deploy_compatible_application:
    requires:
      - release
      - expand
    steps:
      - deploy_compatible_artifact
      - verify_application_health

  backfill:
    requires:
      - expand
      - deploy_compatible_application
    execution:
      mode: resumable_job
      checkpoint: database_migration_progress
      batch_size: configured_and_tunable
      max_concurrency: bounded
      pause_when:
        - database_latency_high
        - replication_lag_high
        - lock_wait_exceeded

  validate_data:
    requires:
      - backfill
    steps:
      - compare_counts
      - check_nulls_and_constraints
      - verify_business_invariants

  cutover:
    requires:
      - validate_data
      - approval
    steps:
      - switch_read_path
      - verify_shadow_or_canary
      - monitor

  contract:
    requires:
      - cutover
      - compatibility_window_completed
      - approval
    steps:
      - verify_no_legacy_consumers
      - remove_old_schema
~~~

Đây là mã giả, không phải schema của một nền tảng CI cụ thể. Trong triển khai thực tế, cần bảo đảm backfill job có thể được khởi chạy lại mà không chạy trùng, có lock, quyền database tối thiểu và không để một lần retry của pipeline khởi tạo migration thứ hai ngoài ý muốn.

## 18. Quan sát tiến độ và điều kiện dừng backfill

Một backfill dài cần telemetry riêng, không chỉ dựa vào trạng thái job Running hoặc Success.

Nên theo dõi:

- Số bản ghi đã xử lý, cập nhật, bỏ qua và lỗi.
- Tốc độ xử lý theo batch.
- Thời gian mỗi batch và transaction.
- Số bản ghi còn lại hoặc ước lượng tiến độ.
- Lock wait và deadlock.
- Database CPU, I/O và connection usage.
- WAL/redo log growth.
- Replication lag.
- Latency và error rate của ứng dụng.
- Số mismatch trong quá trình validation.

Điều kiện pause có thể gồm database latency vượt ngưỡng, replication lag tăng, lock wait kéo dài hoặc ứng dụng bắt đầu vi phạm SLO. Điều kiện abort có thể gồm mapping sai gây hỏng dữ liệu, vi phạm invariant nghiêm trọng hoặc phát hiện thao tác không an toàn.

Không nên dùng phần trăm tiến độ làm tín hiệu duy nhất. Backfill có thể đã xử lý 99% nhưng 1% còn lại là dữ liệu cũ khó ánh xạ nhất. Cần xác minh số lượng và chất lượng dữ liệu còn lại trước khi cutover.

## 19. Rollback và phục hồi dữ liệu

Rollback schema và rollback dữ liệu có mức độ khó khác nhau.

- Thêm một cột nullable thường có thể để nguyên nếu cần quay lại ứng dụng cũ.
- Xóa cột mới trước khi xác minh có thể làm mất dữ liệu mới.
- Ghi kép có thể tạo hai biểu diễn không đồng nhất nếu một đường ghi bị lỗi.
- Backfill sai mapping có thể làm thay đổi hàng triệu bản ghi.
- DROP COLUMN hoặc chuyển đổi mất thông tin có thể không đảo ngược.

Với migration dài, nên ưu tiên **roll-forward** khi dữ liệu đã thay đổi theo cách không thể đảo ngược an toàn. Roll-forward nghĩa là sửa quy tắc hoặc chạy migration bù để đưa dữ liệu về trạng thái hợp lệ, thay vì cố khôi phục bằng một lệnh down đơn giản.

Trước khi chạy cần chuẩn bị:

- Backup và kiểm tra khả năng restore.
- Point-in-time recovery nếu database hỗ trợ.
- Bảng lưu checkpoint và trạng thái job.
- Bản ghi lỗi hoặc dead-letter cho dữ liệu không ánh xạ được.
- Runbook pause, resume, abort và forward-fix.
- Quy tắc giữ dữ liệu nguồn cho đến khi xác minh xong.
- Kế hoạch xử lý ứng dụng cũ và mới trong thời gian phục hồi.

Một bản backup chỉ hữu ích khi đã kiểm tra có thể phục hồi trong thời gian đáp ứng yêu cầu dịch vụ. Không nên coi việc có snapshot là bằng chứng đủ cho rollback.

## 20. Bảo mật và quyền trong migration

Data migration thường cần quyền đọc/ghi trên lượng dữ liệu lớn. Không nên dùng credential quản trị toàn database nếu job chỉ cần cập nhật một số bảng và cột.

Các nguyên tắc:

- Cấp quyền theo bảng, schema và thao tác cần thiết.
- Tách credential DDL khỏi credential backfill nếu phù hợp.
- Dùng secret manager hoặc workload identity.
- Không ghi dữ liệu nhạy cảm ra log hoặc report.
- Mask hoặc token hóa dữ liệu trong staging.
- Giới hạn quyền đọc dữ liệu production.
- Audit người hoặc job đã chạy migration.
- Có timeout, lock và giới hạn concurrency.
- Bảo vệ checkpoint và bảng migration state.
- Thu hồi credential tạm sau khi job kết thúc.

Nếu migration cần xử lý dữ liệu cá nhân, cần xác định mục đích, phạm vi, thời gian lưu và nơi dữ liệu được sao chép. Không dùng bản dump production chưa được bảo vệ làm dữ liệu thử nghiệm thông thường.

## 21. Ví dụ đầy đủ: đổi trạng thái đơn hàng

Giả sử hệ thống cũ lưu trạng thái đơn hàng trong cột **legacy_status** với các giá trị tự do như new, settled, void. Thiết kế mới cần cột **normalized_status** chỉ nhận PENDING, PAID hoặc CANCELLED.

### Giai đoạn A: Expand

Thêm cột mới nullable:

~~~sql
ALTER TABLE orders
ADD COLUMN normalized_status VARCHAR(32);
~~~

Ứng dụng cũ vẫn đọc và ghi cột cũ. Chưa đặt NOT NULL vì dữ liệu hiện tại chưa được chuyển.

### Giai đoạn B: Deploy phiên bản tương thích

Phiên bản mới:

- Có thể đọc cột mới nếu đã có giá trị.
- Tạm fallback sang mapping từ cột cũ.
- Khi ghi trạng thái, cập nhật cả hai cột trong cùng transaction.
- Ghi metric cho các bản ghi thiếu trạng thái chuẩn.

### Giai đoạn C: Backfill theo batch

Ví dụ một batch theo khoảng ID:

~~~sql
UPDATE orders
SET normalized_status =
  CASE legacy_status
    WHEN 'new' THEN 'PENDING'
    WHEN 'settled' THEN 'PAID'
    WHEN 'void' THEN 'CANCELLED'
    ELSE NULL
  END
WHERE id >= :start_id
  AND id < :end_id
  AND normalized_status IS NULL;
~~~

Những giá trị không ánh xạ được được giữ NULL để báo cáo và xử lý riêng. Không nên tự động gán một trạng thái mặc định nếu điều đó làm thay đổi ý nghĩa nghiệp vụ.

### Giai đoạn D: Validate

- Kiểm tra số bản ghi còn NULL.
- Kiểm tra giá trị ngoài danh sách cho phép.
- Đối chiếu số lượng theo từng trạng thái.
- So sánh kết quả mapping trên mẫu dữ liệu.
- Kiểm tra các request mới vẫn ghi đồng bộ hai cột.

### Giai đoạn E: Switch

Bật feature flag để đọc cột mới trên một nhóm request hoặc toàn bộ dịch vụ sau khi gate đạt. Theo dõi mismatch, latency và lỗi nghiệp vụ. Giữ cột cũ trong thời gian an toàn.

### Giai đoạn F: Contract

Sau khi xác nhận không còn instance, worker hoặc report nào dùng cột cũ, tạo migration riêng để loại bỏ cột cũ. Đánh giá lock và backup trước khi thực hiện.

## 22. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Gộp DDL và backfill hàng triệu dòng vào một transaction | Lock lâu, log lớn, rollback tốn kém | Tách expand và backfill theo batch |
| Mỗi replica ứng dụng tự chạy data migration | Chạy trùng và tranh lock | Dùng migration job riêng có lock |
| Xóa cột cũ ngay sau khi thêm cột mới | Phiên bản cũ hoặc consumer nền bị lỗi | Dùng expand-contract và compatibility window |
| Backfill không idempotent | Retry có thể ghi sai hoặc nhân đôi dữ liệu | Thiết kế điều kiện cập nhật và checkpoint |
| Checkpoint ghi trước khi commit dữ liệu | Có thể bỏ qua batch chưa hoàn tất | Cập nhật checkpoint sau commit |
| Chạy backfill không giới hạn tốc độ | Ảnh hưởng request và replication | Throttle theo telemetry |
| Chỉ so số lượng bản ghi | Bỏ sót sai mapping hoặc dữ liệu sai | Kiểm tra invariant và nội dung |
| Dual-write sang hai hệ thống không có cơ chế đồng bộ | Một bên thành công, bên kia thất bại | Dùng outbox/CDC và reconciliation |
| Sửa migration đã chạy | Môi trường có lịch sử khác nhau | Tạo migration mới |
| Coi rollback ứng dụng là rollback dữ liệu | Dữ liệu mới có thể không tương thích | Chuẩn bị forward-fix, backup và PITR |

## 23. Checklist trước khi tách schema và data migration

**Thiết kế và tương thích**

- [ ] Đã phân biệt thay đổi schema với chuyển đổi dữ liệu.
- [ ] Có ma trận tương thích giữa ứng dụng cũ, mới và từng trạng thái schema.
- [ ] Expand không làm phiên bản cũ lỗi ngay lập tức.
- [ ] Writer, worker, report và consumer đều được xem xét.
- [ ] Mapping có quy tắc rõ ràng và xử lý dữ liệu không hợp lệ.

**Backfill**

- [ ] Có batch size và concurrency giới hạn.
- [ ] Job idempotent và có checkpoint.
- [ ] Có thể pause, resume và retry.
- [ ] Bản ghi mới phát sinh trong lúc backfill được bao phủ.
- [ ] Có throttle theo latency, lock wait và replication lag.
- [ ] Có log tiến độ mà không lộ dữ liệu nhạy cảm.

**Validation và cutover**

- [ ] Có kiểm tra NULL, uniqueness, foreign key và invariant.
- [ ] Có đối soát dữ liệu nguồn/đích.
- [ ] Có shadow read hoặc kiểm tra tương đương khi cần.
- [ ] Có minimum completeness trước khi switch.
- [ ] Cutover có approval và khả năng quan sát.
- [ ] Cấu trúc cũ chỉ được contract sau compatibility window.

**Vận hành và khôi phục**

- [ ] Migration script được version hóa và review.
- [ ] Chỉ một worker điều phối mỗi migration hoặc partition.
- [ ] Có backup và đã kiểm tra restore.
- [ ] Có runbook pause, resume, abort và forward-fix.
- [ ] Có điều kiện dừng khi database hoặc ứng dụng bị ảnh hưởng.
- [ ] Credential có quyền tối thiểu và được thu hồi sau khi dùng.

## 24. Kết luận

Tách đổi lược đồ khỏi chuyển đổi dữ liệu dài giúp giảm rủi ro khóa database, tránh kéo dài thời gian deploy và giữ cho nhiều phiên bản ứng dụng cùng hoạt động trong giai đoạn chuyển tiếp. Expand-contract tạo cấu trúc mới mà chưa phá cấu trúc cũ; backfill chuyển dữ liệu theo lô với checkpoint và idempotency; validation cung cấp bằng chứng trước khi switch; contract chỉ loại bỏ phần cũ sau khi mọi consumer đã chuyển đổi.

Pipeline cần quản lý các giai đoạn này như những công việc có vòng đời riêng, có quyền hạn, telemetry và điều kiện dừng rõ ràng. Khi có thể pause/resume, đối soát dữ liệu, theo dõi tác động và chuẩn bị forward-fix hoặc phục hồi, thay đổi database trở thành một phần có kiểm soát của CI/CD thay vì một thao tác rủi ro gắn chặt với thời điểm phát hành.
