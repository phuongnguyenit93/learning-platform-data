# Xác minh dữ liệu trước, trong và sau chuyển đổi

Một migration có thể chạy hết câu lệnh SQL và được công cụ đánh dấu *success* nhưng vẫn làm sai dữ liệu: vài hàng bị bỏ sót trong backfill, một quy tắc chuyển đổi làm tròn tiền sai, bản ghi tạo mới không đi qua đường ghi kép, hoặc ứng dụng chuyển sang đọc cột mới trước khi dữ liệu kịp đồng bộ. Vì vậy, **migration chạy xong không đồng nghĩa dữ liệu đã được chuyển đổi chính xác**.

Bài học thuộc chương **Tiến hóa dữ liệu** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Trong bối cảnh ứng dụng Java sử dụng persistence, kiến thức về mô hình dữ liệu, transaction, cô lập, kết nối, chỉ mục, độ bền và lỗi cần được vận dụng để chứng minh một thay đổi schema/data không phá các bất biến nghiệp vụ. Chủ đề chính là xây dựng **bằng chứng dữ liệu trước, trong và sau chuyển đổi**, thay vì chỉ nhìn exit code của công cụ migration.

> **Nguyên tắc cốt lõi:** mỗi giai đoạn migration phải có câu hỏi kiểm chứng rõ ràng, cách đo lường có thể chạy lại, ngưỡng chấp nhận và hành động cụ thể khi không đạt. Khi chưa đủ bằng chứng, **không cutover chỉ vì migration script trả thành công**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt thay đổi cấu trúc schema, chuyển đổi giá trị dữ liệu, backfill, cutover và contract.
- Xây dựng baseline về chất lượng dữ liệu nguồn, số lượng, phân bố, bất biến và các trường hợp bất thường trước migration.
- Định nghĩa mapping rõ ràng, có thể kiểm tra được, kể cả null, mã không hợp lệ, độ chính xác số và dữ liệu lịch sử.
- Thiết kế validation chạy **trong từng lô** mà không đếm thiếu, đếm lặp hoặc dùng snapshot không tương thích.
- Chứng minh dữ liệu đích đầy đủ và tương đương nguồn theo **khóa định danh, nội dung và bất biến nghiệp vụ**, không chỉ COUNT(*).
- Xử lý ghi đồng thời, dual-write, backfill, retry, idempotency, cursor/checkpoint và khoảng chênh dữ liệu.
- Phân biệt kiểm tra migration metadata với kiểm tra sự thật dữ liệu trong database.
- Lập điều kiện go/no-go, kế hoạch rollback hoặc forward fix và cách quan sát sau cutover.
- Viết SQL PostgreSQL và mã Java kiểm chứng dữ liệu có kiểm soát tài nguyên và độ tải.
- Thiết kế kiểm thử có dữ liệu bẩn, concurrency, crash, failover và thay đổi nhiều phiên bản ứng dụng.

## 2. Phải xác định chính xác “chuyển đổi thành công” nghĩa là gì

Một thay đổi dữ liệu có nhiều tầng kết quả:

| Tầng | Ví dụ chứng cứ | Điều chưa thể kết luận |
|---|---|---|
| **DDL đã áp dụng** | Cột/bảng/index/constraint tồn tại | Dữ liệu trong cột mới đúng |
| **Backfill đã chạy** | Job báo hoàn tất, checkpoint cuối | Không có hàng bị bỏ sót hoặc lỗi diễn giải |
| **Dữ liệu đích đầy đủ** | Không còn record thiếu dữ liệu bắt buộc | Mọi giá trị đúng theo mapping |
| **Dữ liệu đích tương đương** | So sánh từng khóa, quy tắc biến đổi và bất biến | Ứng dụng đã đọc/ghi đúng phiên bản mới |
| **Đường ghi mới đúng** | Test concurrent writer, retry và dual-write | Không còn writer cũ chạy ngoài kiểm soát |
| **Cutover thành công** | API đọc dữ liệu mới, metrics bình thường | Có thể xóa ngay cột cũ |
| **Contract an toàn** | Đã qua cửa sổ rollback, backup/restore kiểm chứng | Có thể phục hồi ngay từ một lệnh DROP |

**Định nghĩa hoàn tất** không chỉ là tỷ lệ hoàn thành 100%. Nó thường gồm: tất cả khóa phải có dữ liệu đích, mismatch bằng 0 đối với invariant cứng, những ngoại lệ được phân loại/giải quyết, không còn writer không tương thích, kết quả ứng dụng phù hợp và có lối thoát khi phát hiện lỗi muộn.

### 2.1. Dùng một ví dụ nhất quán xuyên suốt

Giả sử Order Service đang lưu trạng thái đơn hàng trong PostgreSQL:

~~~sql
CREATE TABLE orders (
    id uuid PRIMARY KEY,
    tenant_id bigint NOT NULL,
    status_code smallint NOT NULL,
    version bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now()
);
~~~

Quy tắc cũ:

| status_code | Ý nghĩa |
|---|---|
| 0 | PENDING |
| 1 | PAID |
| 2 | CANCELLED |

Ứng dụng muốn thêm cột **status_text** rồi chuyển đường đọc sang chuỗi rõ nghĩa, sau cùng loại bỏ status_code ở một đợt riêng.

~~~sql
ALTER TABLE orders
ADD COLUMN status_text text;
~~~

Mục đích là **không thay đổi ý nghĩa nghiệp vụ của đơn hàng**. Với mỗi record có khóa (id), giá trị status_text phải khớp chính xác với status_code theo quy tắc mapping được chốt. Khi hệ thống còn nhận ghi, cả dữ liệu mới phát sinh cũng phải thỏa điều kiện tương thích.

Ví dụ này dùng kiểu text để đơn giản hóa. Production có thể dùng enum, domain type, bảng tham chiếu hoặc CHECK tùy yêu cầu. Việc dùng code/symbol cũng cần hợp đồng tương thích với hệ thống bên ngoài.

### 2.2. Chốt phép biến đổi như một hàm

~~~text
f(0) = "PENDING"
f(1) = "PAID"
f(2) = "CANCELLED"
f(other) = INVALID, không tự suy ra
~~~

Các thuộc tính cần được xác nhận:

- **Tính xác định:** cùng giá trị nguồn hợp lệ luôn cho một giá trị đích tương ứng.
- **Tính toàn phần trên tập dữ liệu được chấp nhận:** mỗi giá trị nguồn đang có phải có quy tắc hoặc được đưa vào danh sách ngoại lệ để xử lý.
- **Không làm mất thông tin bắt buộc:** nếu nhiều giá trị nguồn bị gộp thành một giá trị đích, phải chứng minh nghiệp vụ cho phép mất khả năng phân biệt.
- **Có khả năng kiểm chứng:** có thể tính lại f(source) và đối chiếu trực tiếp target sau backfill.
- **Tương thích với writer và reader:** những phiên bản ứng dụng cùng tồn tại phải xử lý được cả trạng thái đang chuyển đổi.

Nếu có status_code=9 trong production, **không tự map thành PENDING hoặc UNKNOWN chỉ để job chạy qua**. Phải làm rõ vì sao có mã 9, được phép giữ nó hay không, và tác động của quyết định sửa dữ liệu.

## 3. Trước chuyển đổi: kiểm kê, lập baseline và kiểm tra chất lượng nguồn

### 3.1. Chốt phạm vi dữ liệu

Trước hết phải biết migration áp dụng cho:

- Bảng, schema, tenant, partition, shard, môi trường và vùng địa lý nào.
- Dữ liệu đang hoạt động và dữ liệu lịch sử đã archive.
- Bản ghi đã soft delete, trạng thái PENDING lâu ngày, dữ liệu ẩn hoặc dữ liệu được import thủ công.
- Các hệ phụ thuộc: API, report, CDC, Kafka event, BI, search index, cache và batch jobs.
- Các phiên bản ứng dụng, cron jobs và công cụ quản trị nào đang ghi vào cột nguồn.

Nếu truy vấn baseline chỉ đo 1 partition mà cutover dùng toàn bộ dữ liệu, báo cáo “100%” là sai về mẫu số.

### 3.2. Kiểm kê số lượng và phân bố

Truy vấn đếm tổng và mã trạng thái:

~~~sql
SELECT COUNT(*) AS total_orders
FROM orders;

SELECT status_code,
       COUNT(*) AS rows_per_status
FROM orders
GROUP BY status_code
ORDER BY status_code;
~~~

Phát hiện giá trị ngoài miền cho phép:

~~~sql
SELECT COUNT(*) AS unknown_status_count
FROM orders
WHERE status_code NOT IN (0, 1, 2);
~~~

Với schema mẫu, status_code là NOT NULL. Nếu cột nguồn thực tế cho phép NULL, cần kiểm tra riêng:

~~~sql
SELECT COUNT(*) AS null_status_count
FROM orders
WHERE status_code IS NULL;
~~~

Kiểm kê theo tenant và vùng thời gian có thể làm lộ dữ liệu bẩn chỉ xuất hiện ở một nhóm:

~~~sql
SELECT tenant_id, status_code, COUNT(*) AS amount
FROM orders
GROUP BY tenant_id, status_code
ORDER BY tenant_id, status_code;
~~~

COUNT(*) cho biết **khối lượng**, không chứng minh độ đúng của quy tắc mapping. Cần thêm kiểm tra về khóa, quan hệ, bất biến và lịch sử.

### 3.3. Phân loại bản ghi bất thường trước khi sửa

| Phát hiện | Ý nghĩa có thể có | Hành động |
|---|---|---|
| status_code không thuộc 0,1,2 | Dữ liệu legacy hoặc writer không đúng contract | Điều tra nguồn, sửa mapping hoặc dữ liệu theo phê duyệt |
| status_code NULL | Chưa có quy tắc chuyển đổi | Làm rõ trạng thái hợp lệ; không thay bằng giá trị tùy ý |
| tenant_id không hợp lệ | Rủi ro cô lập tenant và phạm vi migration | Kiểm tra logic phân quyền và nguồn import |
| Một đơn có quan hệ bản ghi con bị thiếu | Invariant referential bị phá | Kiểm kê orphan và kiểm tra FK |
| updated_at sai/mất tính tin cậy | Không thể dùng làm watermark tuyệt đối | Chọn khóa/checkpoint hoặc CDC đáng tin hơn |
| Trạng thái không phù hợp dòng sự kiện | Sai logic nghiệp vụ trước migration | Điều tra bằng event/ledger authoritative |
| Dữ liệu trùng business key | Có thể tạo duplicate sau chuyển schema | Định nghĩa chính sách hợp nhất trước backfill |

**Không sửa dữ liệu bẩn bằng câu UPDATE hàng loạt khi chưa biết nguyên nhân**. Migration có thể bộc lộ lỗi đã tồn tại từ lâu; ghi nhận và khoanh vùng chúng tránh biến lỗi cũ thành lỗi mới khó đối soát.

### 3.4. Snapshot và tính đồng nhất của baseline

Một hệ thống vẫn tiếp nhận ghi sẽ thay đổi ngay sau câu COUNT(*). Nếu chạy ba câu kiểm tra ở ba thời điểm, các tổng có thể không cộng khớp dù dữ liệu vẫn đúng.

Khi cần một baseline logic nhất quán, có thể dùng transaction chỉ đọc ở mức isolation giữ cùng snapshot trên PostgreSQL:

~~~sql
BEGIN TRANSACTION
ISOLATION LEVEL REPEATABLE READ
READ ONLY;

SELECT COUNT(*) FROM orders;
SELECT status_code, COUNT(*)
FROM orders GROUP BY status_code;
SELECT COUNT(*) FROM orders
WHERE status_code NOT IN (0, 1, 2);

COMMIT;
~~~

Chạy các câu trong **cùng transaction** mới cho cùng snapshot. Không giữ một transaction REPEATABLE READ rất lâu chỉ để đếm bảng khổng lồ: snapshot kéo dài có thể ảnh hưởng VACUUM/bloat và tài nguyên. Với bảng lớn, có thể dùng các bước scan theo khoảng khóa, snapshot/CDC watermark theo runbook riêng và ghi rõ rằng những phép đếm ở các thời điểm khác nhau **không so trực tiếp được**.

### 3.5. Lưu bằng chứng baseline

Một hồ sơ migration nên có ít nhất:

- Migration/version ID, thời gian bắt đầu và môi trường/cluster/shard.
- Phiên bản mapping f(), schema nguồn và SQL kiểm chứng.
- Phạm vi tenant/partition, số bản ghi từng nhóm và điều kiện lọc.
- Danh sách/đếm lỗi data quality, định danh hàng để điều tra trong phạm vi được phép.
- Snapshot, transaction ID/watermark hoặc khoảng thời gian đo kèm giới hạn.
- Người phê duyệt cách xử lý ngoại lệ, tiêu chí go/no-go và kế hoạch rollback/forward fix.

Không cần sao chép dữ liệu cá nhân nhạy cảm vào file báo cáo để làm bằng chứng. Có thể lưu số lượng, hash được thiết kế cẩn thận, ID đã được kiểm soát quyền và truy vấn có thể tái chạy.

## 4. Thiết kế các bất biến kiểm chứng trước khi chạy

Với migration status_code sang status_text, bất biến cứng là:

~~~text
Đối với mọi order được đưa vào phạm vi:
  status_text = f(status_code)
và status_text không NULL khi đã kết thúc backfill.
~~~

Trong giai đoạn vẫn ghi kép, cần thêm bất biến:

~~~text
Mọi thay đổi mới của order:
  status_code và status_text cùng phản ánh một trạng thái nghiệp vụ,
  trong cùng DB transaction.
~~~

Những bất biến khác có thể gồm:

- Không mất khóa chính, không tạo duplicate business ID.
- Các tham chiếu khóa ngoại vẫn hợp lệ.
- Không biến PAID thành CANCELLED do ánh xạ nhầm.
- Tổng số tiền theo currency và tenant không thay đổi vì migration chỉ đổi trạng thái.
- Những record không nằm trong phạm vi không bị chỉnh sửa.
- Version hoặc trường nghiệp vụ quan trọng không giảm hoặc bị reset ngoài ý muốn.
- Tenant isolation không bị phá bởi job backfill chạy với quyền quản trị.

**Phân biệt invariant cứng và tín hiệu giám sát:**

| Loại | Ví dụ | Nếu không đạt |
|---|---|---|
| Cứng | Không có order sai mapping | Không cutover |
| Cứng | Không có order bị mất hoặc nhân đôi | Dừng, điều tra và phục hồi |
| Cứng | Các giao dịch mới đi qua giao thức ghi tương thích | Không cho reader mới nhận traffic |
| Cứng | Ràng buộc DB quan trọng đã được xác nhận | Không contract schema cũ |
| Giám sát | Throughput backfill gần mục tiêu | Điều chỉnh rate, chưa nhất thiết dừng |
| Giám sát | Query p95 tăng nhẹ trong giới hạn | Cân nhắc giảm batch hoặc chạy off-peak |
| Giám sát | Replica lag tăng trong ngưỡng cho phép | Theo dõi và giới hạn tải |

Trước migration cần nói rõ cách tính pass/fail. Nếu đến lúc mismatch xuất hiện mới quyết định “1% sai vẫn được”, kết quả kiểm thử dễ bị hợp lý hóa sai.

## 5. Phân biệt chuyển đổi schema và chuyển đổi dữ liệu

Hai loại thay đổi liên quan nhưng không thay thế nhau:

1. **Schema migration:** tạo cột, index, constraint, view hoặc thay quan hệ cấu trúc. Công cụ như Flyway/Liquibase thường theo dõi version, lịch sử áp dụng và checksum script.
2. **Data migration/backfill:** chuyển từng record cũ sang representation mới, có thể kéo dài và được chạy theo lô, có checkpoint, retry và quan sát riêng.

Một version migration được đánh dấu applied chỉ chứng minh **bước được công cụ quản lý đã chạy theo định nghĩa của công cụ**. Nó không tự chứng minh mọi record production đã được backfill và các writer trong lúc chuyển đổi vẫn đúng.

### 5.1. Quy trình expand → migrate → contract

~~~mermaid
flowchart LR
    A["Expand schema: thêm cột mới"] --> B["Triển khai writer tương thích"]
    B --> C["Backfill theo lô"]
    C --> D["Đối soát dữ liệu và ghi đồng thời"]
    D --> E["Chuyển reader sang cột mới"]
    E --> F["Quan sát, xác minh sau cutover"]
    F --> G["Contract: loại cột cũ ở đợt riêng"]
~~~

Có thể có nhiều phiên bản ứng dụng cùng tồn tại trong quá trình rollout. Mục đích của expand–contract là **duy trì tương thích giữa schema và ứng dụng** cho tới khi xác nhận không còn đường đọc/ghi dựa vào representation cũ.

### 5.2. Vì sao phải giữ hai representation tạm thời?

Nếu đổi tên/xóa ngay cột status_code và deploy ứng dụng mới bằng rolling update, một số instance cũ vẫn cố truy cập status_code. Dù dữ liệu đã chuyển đúng, ứng dụng cũ có thể lỗi ngay. Ngược lại nếu thêm status_text nhưng application mới đọc trước khi backfill xong, nhiều bản ghi sẽ có NULL.

Giải pháp là các đợt deploy có **mốc tương thích được kiểm chứng**. Không đồng nhất “DB schema sẵn sàng” với “tất cả writer/reader đã sẵn sàng”.

## 6. Những loại dữ liệu cần xử lý cẩn thận khi mapping

Ví dụ đổi trạng thái chỉ có ba mã, nhưng migration thật thường có chuyển đổi phức tạp hơn.

### 6.1. Tiền và độ chính xác số

Đổi price từ numeric(18,2) sang integer minor unit không nên nhân số bằng phép tính floating point Java rồi ép long mà không kiểm tra:

~~~java
public static long toMinorUnits(
        BigDecimal amount,
        int currencyFractionDigits) {

    Objects.requireNonNull(amount);
    if (currencyFractionDigits < 0 || currencyFractionDigits > 9) {
        throw new IllegalArgumentException("Unsupported currency scale");
    }

    return amount
        .movePointRight(currencyFractionDigits)
        .setScale(0, RoundingMode.UNNECESSARY)
        .longValueExact();
}
~~~

Phép tính này chỉ minh họa cách **không âm thầm làm tròn** và phát hiện overflow; số chữ số thập phân phải lấy từ quy tắc currency/business đã định, không suy mọi tiền tệ đều có hai chữ số. Với dữ liệu legacy có phần lẻ không biểu diễn được ở đơn vị mới, phải dừng và phân loại, không lặng lẽ cắt số.

### 6.2. Ngày giờ và múi giờ

Chuyển cột timestamp không có timezone sang instant cần làm rõ timezone gốc. Nếu dữ liệu cũ lưu “2024-11-01 08:00” mà không biết là giờ Việt Nam hay UTC, ép nó vào một múi giờ có thể đổi ý nghĩa lịch sử.

Kiểm tra:

- timezone nguồn, daylight saving khi có và các thời điểm mơ hồ;
- độ chính xác mili/microsecond;
- quy tắc lưu thời điểm tuyệt đối hay giờ địa phương;
- tác động lên truy vấn khoảng ngày, partition key và báo cáo.

### 6.3. Chuỗi và định danh

Khi chuyển varchar sang enum, normalize tên, đổi charset hoặc ghép khóa, cần xử lý khoảng trắng, Unicode normalization, case sensitivity, chuỗi trống và dữ liệu không hợp lệ. Nếu tạo UNIQUE trên giá trị đã normalize, hai bản ghi vốn khác nhau có thể trở thành trùng.

Không tự suy hai customer chỉ vì tên và ngày sinh giống nhau rồi gộp, nếu chưa có chính sách nhận dạng và đối soát chính thức.

### 6.4. NULL và giá trị mặc định

NULL có thể có ý nghĩa “chưa biết”, “không áp dụng” hoặc “chưa xử lý”; gán giá trị mặc định cho mọi NULL có thể bóp méo dữ liệu lịch sử. Một quy tắc mapping phải nói rõ từng trường hợp, kể cả record soft-deleted và dữ liệu tạo bởi phiên bản ứng dụng cũ.

**Tiêu chí:** phép chuyển đổi phải có mô tả business, điều kiện lỗi và test biên; không được chỉ là một hàm cast chạy được SQL.

## 7. Trong chuyển đổi: kiểm tra tương thích writer trước khi backfill

Hệ thống đang chạy có thể có nhiều writer: HTTP API, job import, event consumer, batch cập nhật và công cụ quản trị. Migration chỉ an toàn khi biết **mọi writer còn tồn tại** sẽ làm gì với hai cột cũ/mới trong suốt rollout.

### 7.1. Vì sao “triển khai dual-write rồi backfill” phải có mốc xác nhận?

Giả sử deployment diễn ra theo rolling update:

~~~text
Instance A: version cũ, chỉ UPDATE status_code
Instance B: version mới, UPDATE status_code + status_text
Backfill: đang cập nhật status_text
Reader mới: bắt đầu đọc status_text
~~~

Instance A có thể đổi đơn từ PENDING sang PAID **sau khi backfill đã ghi PENDING vào status_text**. Nếu không có cơ chế đồng bộ, status_code=1 nhưng status_text=PENDING. Việc một số instance mới hỗ trợ dual-write chưa đủ; phải xác định không còn writer cũ gây lệch dữ liệu hoặc dùng bảo vệ tương thích tại database.

### 7.2. Ba chiến lược chuyển tiếp

| Cách làm | Điều kiện | Rủi ro cần kiểm soát |
|---|---|---|
| Deploy đồng loạt mọi writer tương thích, rồi backfill | Kiểm soát được mọi nguồn ghi và các phiên bản triển khai | Job ẩn, instance cũ, rollback ứng dụng |
| Dùng trigger DB đồng bộ cột mới từ cột cũ trong giai đoạn chuyển tiếp | Có thể áp dụng trigger đúng với nhiều loại DML và tác động hiệu năng chấp nhận | Trigger order, bulk update, replication và quy tắc ghi khi cả hai cột được cung cấp |
| Dừng ghi trong maintenance window, chuyển toàn bộ và mở lại | Hệ thống cho phép downtime rõ ràng | SLA, backlog request, kiểm thử thời điểm bật ghi trở lại |

Khi đang chuyển đổi từ status_code sang status_text, **không để hai representation là hai nguồn chuẩn độc lập**. Trong giai đoạn đầu, status_code vẫn là authoritative; status_text là giá trị dẫn xuất. Khi chuyển chiều ghi sang status_text, cần định nghĩa một đợt triển khai mới và quy tắc tương thích/rollback tương ứng.

### 7.3. Ví dụ Spring ghi đồng thời hai cột trong một transaction

~~~java
public enum OrderStatus {
    PENDING, PAID, CANCELLED
}

public static short legacyCode(OrderStatus status) {
    return switch (status) {
        case PENDING -> 0;
        case PAID -> 1;
        case CANCELLED -> 2;
    };
}

@Transactional
public void setStatus(long tenantId, UUID orderId,
                      OrderStatus status, long expectedVersion) {
    int updated = jdbc.update(
        """
        UPDATE orders
        SET status_code = ?,
            status_text = ?,
            version = version + 1,
            updated_at = now()
        WHERE tenant_id = ? AND id = ? AND version = ?
        """,
        legacyCode(status), status.name(),
        tenantId, orderId, expectedVersion
    );

    if (updated != 1) {
        throw new ConcurrentModificationException(
            "Order not found or version mismatch"
        );
    }
}
~~~

Mã là ví dụ minh họa trong một service có transaction manager của cùng DataSource, được gọi qua Spring proxy. SQL cập nhật cả hai giá trị **trong cùng một câu lệnh**, tránh có transaction commit chỉ một cột. Điều kiện version ngăn lost update do hai writer cùng đọc bản cũ.

Không dùng hai connection/transaction độc lập để cập nhật hai cột rồi gọi đó là dual-write nguyên tử. Nếu một column update thành công còn update khác thất bại nhưng đã commit riêng, dữ liệu sẽ lệch.

### 7.4. Kiểm tra writer đã tương thích bằng bằng chứng

Một checklist deployment nên ghi:

- Phiên bản mọi instance/worker và container đang chạy.
- Job theo lịch, script quản trị, ETL và consumer nào còn viết status_code.
- Traces hoặc metrics chứng minh câu UPDATE mới đi qua đường ghi hai cột.
- Test trên môi trường tương tự production có request ghi khi backfill đang chạy.
- Phương án rollback ứng dụng **không quay lại writer cũ** khi schema đã tới trạng thái không tương thích.
- Cơ chế phát hiện mismatch tăng sau bất kỳ đợt deploy nào.

Chỉ nhìn git commit hoặc trạng thái CD “deployed” không chứng minh mọi writer thực sự đã chuyển.

## 8. Backfill theo lô có checkpoint và bảo vệ ghi đồng thời

Một UPDATE duy nhất trên bảng hàng trăm triệu record có thể tạo transaction rất lớn, giữ lock, sinh WAL đột biến, tăng replica lag và khó phục hồi khi lỗi. Để giảm blast radius, thường cần backfill theo batch với giới hạn số hàng, tốc độ và thời gian chạy.

### 8.1. Keyset pagination thay OFFSET

Chọn khóa chính theo thứ tự ổn định:

~~~sql
SELECT id
FROM orders
WHERE (:last_id IS NULL OR id > CAST(:last_id AS uuid))
ORDER BY id
LIMIT :batch_size;
~~~

Sau khi lấy danh sách ID trong một batch, cập nhật **chính những ID đó** theo giá trị nguồn hiện tại, không dựa vào một status_code đã đọc từ rất lâu:

~~~sql
UPDATE orders
SET status_text = CASE status_code
    WHEN 0 THEN 'PENDING'
    WHEN 1 THEN 'PAID'
    WHEN 2 THEN 'CANCELLED'
    ELSE NULL
END
WHERE id = ANY(CAST(:batch_ids AS uuid[]))
  AND status_code IN (0, 1, 2)
  AND status_text IS DISTINCT FROM CASE status_code
    WHEN 0 THEN 'PENDING'
    WHEN 1 THEN 'PAID'
    WHEN 2 THEN 'CANCELLED'
    ELSE NULL
  END;
~~~

Đoạn SQL là mẫu logic, không phải cú pháp bind của mọi JDBC template. Với PostgreSQL, một implementation có thể tạo java.sql.Array kiểu uuid hoặc dùng NamedParameterJdbcTemplate với danh sách placeholder thích hợp; phải bind tham số đúng cách, không nối chuỗi UUID từ input vào SQL.

**Vì sao giá trị phải được tính trong UPDATE?** Nếu ứng dụng SELECT status_code=0, chờ lâu rồi chạy UPDATE status_text='PENDING' trong khi writer khác đã đổi status_code=1, bản đích có thể bị ghi lệch. Khi tính trực tiếp từ row hiện hành tại thời điểm UPDATE và có row lock thích hợp, tránh dùng một giá trị nguồn đã cũ ở tầng Java. Tuy nhiên giải pháp vẫn cần các writer khác tuân thủ cùng giao thức; một writer cũ chạy sau đó có thể làm lệch hai cột.

### 8.2. Checkpoint tính theo *batch được duyệt*, không phải hàng được cập nhật

Một batch có thể đọc 1.000 ID nhưng chỉ 80 hàng cần cập nhật vì số còn lại đã được dual-write hoặc backfill trước đó. Nếu cursor dựa trên ID lớn nhất của **hàng được UPDATE**, job có thể lặp qua nhiều ID không cần thiết hoặc không tiến nếu batch không đổi hàng nào.

Quy trình đúng:

1. SELECT tối đa N ID lớn hơn cursor đã commit trước đó, theo thứ tự khóa.
2. Nếu không có ID, đi tới bước đối soát toàn bảng; **không** suy hoàn tất chỉ từ cursor.
3. UPDATE các ID được chọn theo nguồn hiện hành, có điều kiện tránh ghi thừa.
4. Kiểm tra constraint, mã trạng thái lạ, các lỗi của batch và số bản ghi đã duyệt.
5. COMMIT transaction batch; chỉ sau khi commit thành công mới lưu/đánh dấu checkpoint tiến độ bền vững theo ID cuối **đã duyệt**.
6. Nếu commit outcome không rõ, job có thể replay batch; UPDATE lặp lại phải giữ nguyên kết quả và không sinh side effect khác.

Nếu checkpoint lưu tại database riêng hoặc file ngoài, việc đồng bộ với commit batch cần thiết kế cẩn thận. Khi không thể commit atomically, hãy đảm bảo **replay idempotent** và đối soát cuối cùng phát hiện mọi bản ghi bỏ sót.

### 8.3. Mã Java minh họa batch bằng JdbcTemplate

~~~java
public record BatchResult(UUID lastSeenId, int scanned, int updated) {}

public BatchResult backfillOneBatch(
        JdbcTemplate jdbc, UUID lastSeenId, int requestedSize) {

    int batchSize = Math.min(Math.max(requestedSize, 1), 500);

    List<UUID> ids = jdbc.query(
        """
        SELECT id FROM orders
        WHERE (?::uuid IS NULL OR id > ?::uuid)
        ORDER BY id
        LIMIT ?
        """,
        (rs, rowNum) -> rs.getObject("id", UUID.class),
        lastSeenId, lastSeenId, batchSize
    );

    if (ids.isEmpty()) {
        return new BatchResult(lastSeenId, 0, 0);
    }

    // NamedParameterJdbcTemplate mở rộng tập UUID thành placeholders.
    // Ví dụ phải được chạy bên trong transaction riêng cho mỗi batch.
    String sql = """
        UPDATE orders
        SET status_text = CASE status_code
            WHEN 0 THEN 'PENDING'
            WHEN 1 THEN 'PAID'
            WHEN 2 THEN 'CANCELLED'
            ELSE NULL END
        WHERE id IN (:ids)
          AND status_code IN (0, 1, 2)
          AND status_text IS DISTINCT FROM CASE status_code
            WHEN 0 THEN 'PENDING'
            WHEN 1 THEN 'PAID'
            WHEN 2 THEN 'CANCELLED'
            ELSE NULL END
        """;

    MapSqlParameterSource params =
        new MapSqlParameterSource("ids", ids);
    int updated = namedJdbc.update(sql, params);

    return new BatchResult(ids.get(ids.size() - 1), ids.size(), updated);
}
~~~

Đây là **phác thảo cấu trúc**, không phải file Java compile trực tiếp: namedJdbc là dependency của lớp hoặc tham số cần được khai báo, và cơ chế transaction/checkpoint nằm ngoài method. Đối với PostgreSQL JDBC, cú pháp cast placeholder có thể cần chỉnh khi dùng prepared statement và driver cụ thể. Khi xây implementation thật, tránh SELECT toàn bộ bảng vào bộ nhớ và bảo vệ những lỗi đến từ database/timeouts.

### 8.4. Bảo vệ khỏi ghi đồng thời và insert mới

Keyset theo UUID có thể duyệt toàn bộ các row **đã có** theo một thời điểm. Nhưng UUID mới thường không tăng theo thời gian; một row INSERT sau khi cursor đã đi qua vị trí UUID của nó có thể bị bỏ qua.

Vì vậy **không dùng cursor là chứng cứ đầy đủ** khi vẫn có ghi:

- Trước khi chạy backfill, các writer mới phải ghi dữ liệu đích theo protocol hoặc DB phải tự đảm bảo mapping.
- Chạy kiểm tra toàn bảng/partition cho NULL, mismatch, unknown sau khi quét.
- Nếu còn mismatch, backfill lại tập sai theo điều kiện chứ không chỉ tiếp tục cursor cũ.
- Chỉ cutover khi reconciliation chứng minh mọi row thuộc phạm vi có đích hợp lệ và writer đang hoạt động giữ được invariant.

Một cờ “batch 100%” không bao gồm dữ liệu mới phát sinh phía sau cursor nếu không có điều kiện trên.

### 8.5. Idempotency và retry

Backfill dạng SET status_text=f(status_code) được thiết kế để chạy lại không làm tăng số lượng hay thay đổi ý nghĩa nghiệp vụ. Nhưng nếu job còn **gửi email, phát event, tăng counter hoặc thu tiền** ở mỗi row, chạy lại có thể tạo tác động trùng.

Tách side effect khỏi backfill kỹ thuật. Nếu cần phát event do thay đổi representation, hãy có định danh bền vững và cơ chế phát/consume idempotent, đồng thời chứng minh có cần phát event hay không. Một thay đổi cột dẫn xuất thường **không nên** được hiểu là người dùng đã chuyển trạng thái đơn lần nữa.

## 9. Trong chuyển đổi: đo tiến độ nhưng không bị đánh lừa

### 9.1. Coverage, mismatch và unknown

~~~sql
SELECT COUNT(*) FILTER (WHERE status_text IS NULL) AS missing_target,
       COUNT(*) FILTER (
         WHERE status_code NOT IN (0, 1, 2)
       ) AS unknown_source,
       COUNT(*) FILTER (
         WHERE status_text IS DISTINCT FROM CASE status_code
           WHEN 0 THEN 'PENDING'
           WHEN 1 THEN 'PAID'
           WHEN 2 THEN 'CANCELLED'
           ELSE NULL END
       ) AS mismatched
FROM orders;
~~~

Đặt điều kiện mismatch theo cách **NULL-safe**: PostgreSQL IS DISTINCT FROM xử lý NULL như một giá trị có thể so sánh. Nếu dùng status_text != expression, SQL ba giá trị có thể biến nhiều trường hợp NULL thành UNKNOWN, khiến COUNT bỏ sót.

Kiểm tra nên theo tenant hoặc partition để tìm phân bố lỗi, tránh một tỷ lệ toàn cụm đẹp che vấn đề nghiêm trọng ở một nhóm nhỏ:

~~~sql
SELECT tenant_id,
       COUNT(*) AS total,
       COUNT(*) FILTER (WHERE status_text IS NULL) AS missing,
       COUNT(*) FILTER (
         WHERE status_text IS DISTINCT FROM CASE status_code
           WHEN 0 THEN 'PENDING'
           WHEN 1 THEN 'PAID'
           WHEN 2 THEN 'CANCELLED'
           ELSE NULL END
       ) AS mismatch
FROM orders
GROUP BY tenant_id
ORDER BY tenant_id;
~~~

### 9.2. Tỷ lệ progress có mẫu số thay đổi

Nếu tổng row tăng do INSERT mới, tỷ lệ updated/total có thể giảm dù batch job vẫn xử lý đúng. Nếu job đếm tổng số hàng từ 9 giờ rồi so với số thành công ở 10 giờ, kết quả có thể vượt 100% hoặc che row mới.

Giải pháp:

- Tách **phạm vi baseline** tại snapshot/watermark đã ghi nhận và **ghi mới sau mốc đó**.
- Đo scanned, updated, skipped, failed, remaining ở cùng phạm vi đo hoặc chú thích sai lệch.
- Theo dõi unknown/mismatch cứng thay vì chỉ progress percentage.
- Có checkpoint/restart có thể kiểm chứng, không dựa vào một counter trong RAM.

### 9.3. Query xác minh gây tải

COUNT và so sánh trên bảng lớn có thể quét rất nhiều row. Chạy quá thường xuyên gây I/O, CPU, cache pressure và ảnh hưởng latency transaction của hệ thống.

Có thể:

- Chia các phép đếm theo partition/tenant hoặc cửa sổ khóa.
- Giảm tần suất full scan; metrics batch theo từng lô đủ cho giám sát ngắn hạn.
- Chạy đối soát sâu trên replica **chỉ khi chấp nhận được độ trễ và hiểu snapshot**; không dùng replica trễ làm bằng chứng cutover cho dữ liệu primary mới nhất.
- Giới hạn statement timeout, work_mem và concurrency của job theo cấu hình vận hành.
- Kết hợp các đợt scan với metrics tiến độ để phát hiện lệch trước khi chạy một kiểm tra cuối đắt hơn.

Không cài một dashboard mỗi giây chạy full table COUNT(*), rồi đổ lỗi cho migration khi production chậm đi.

## 10. Đối soát nội dung: COUNT(*) chỉ là phép kiểm tra đầu tiên

Giả sử nguồn có 100.000 hàng và đích cũng có 100.000 hàng. Điều đó **không chứng minh** hai tập có cùng record hoặc cùng giá trị: một ID bị mất và một ID bị nhân đôi có thể khiến tổng không đổi.

### 10.1. So sánh theo khóa, phát hiện row thiếu

Khi chuyển sang một bảng mới orders_v2, có thể dùng anti-join để tìm thiếu:

~~~sql
SELECT o.id
FROM orders o
LEFT JOIN orders_v2 n ON n.id = o.id
WHERE n.id IS NULL
LIMIT 100;
~~~

Tương tự tìm record thừa ở đích:

~~~sql
SELECT n.id
FROM orders_v2 n
LEFT JOIN orders o ON o.id = n.id
WHERE o.id IS NULL
LIMIT 100;
~~~

Nếu dữ liệu đích được thiết kế là tập con hoặc có filter business có chủ ý, hai câu trên phải thêm điều kiện phạm vi tương ứng. Không kết luận missing từ row vốn không thuộc mục tiêu migration.

### 10.2. So sánh giá trị theo mapping

Với cột mới trên cùng bảng:

~~~sql
SELECT id, tenant_id, status_code, status_text
FROM orders
WHERE status_text IS DISTINCT FROM CASE status_code
    WHEN 0 THEN 'PENDING'
    WHEN 1 THEN 'PAID'
    WHEN 2 THEN 'CANCELLED'
    ELSE NULL
END
LIMIT 100;
~~~

Với bảng đích riêng, join theo khóa và so từng thuộc tính nghiệp vụ. Nếu có các cột kỹ thuật như migrated_at hoặc updated_at do batch job cập nhật, **không mặc định so chúng bằng nhau** nếu contract không yêu cầu.

### 10.3. Tổng tiền và các phép tổng hợp cần giữ

Khi chuyển đơn hàng hoặc ledger, có thể kiểm tra tổng theo currency, tenant, thời gian và trạng thái:

~~~sql
SELECT tenant_id, status_code,
       COUNT(*) AS orders_count
FROM orders
GROUP BY tenant_id, status_code;
~~~

Đối chiếu với nhóm theo status_text tương ứng **trong cùng snapshot được thiết kế**. Số lượng tổng chỉ là một invariant bổ trợ; cần so theo khóa để phát hiện tráo đổi giá trị giữa hai đơn.

Với tiền, không cộng giá trị float/double để đối soát exact money; dùng numeric/BigDecimal hoặc đơn vị nguyên đúng currency. Số tiền tổng bằng nhau cũng không chứng minh mọi khoản chuyển đúng người nhận.

### 10.4. Hash và checksum để giảm dữ liệu truyền

Một hệ thống lớn có thể tạo fingerprint trên representation đã chuẩn hóa của từng row và so theo key:

~~~text
canonicalRow = tenantId | orderId | mappedStatus | amount | currency
fingerprint  = HASH(canonicalRow)
~~~

Để hash đáng tin, phải xác định rõ chuẩn hóa:

- Thứ tự các trường và cách tách trường không mơ hồ.
- Cách biểu diễn NULL, chuỗi rỗng và Unicode.
- Định dạng timestamp và timezone.
- Độ chính xác decimal và currency.
- Thứ tự row nếu băm một tập hợp.
- Thuật toán hash và phạm vi collision được chấp nhận.

Hash phù hợp để phát hiện khác biệt nhanh, nhưng **không thay thế** kiểm tra khóa, constraint và các invariant nghiệp vụ. Nếu fingerprint mismatch, phải truy ra field nào khác biệt. Không dùng checksum từ hai snapshot khác thời điểm rồi kết luận mất dữ liệu khi primary vẫn có ghi.

### 10.5. Kiểm tra mẫu có chủ đích

Ngoài full reconciliation, chọn mẫu tăng khả năng phát hiện lỗi:

- Record mới nhất, cũ nhất, từng tenant/partition.
- Record có trạng thái hiếm hoặc biên chuyển trạng thái.
- Record đã bị cập nhật trong lúc backfill.
- Record có NULL, Unicode đặc biệt, số tiền lớn/nhỏ và timezone đặc biệt nếu mapping liên quan.
- Record từ import legacy hoặc nguồn thường phát sinh dữ liệu bất thường.

Sampling hữu ích để tìm lỗi logic ngoài giả định, nhưng **không chứng minh toàn bộ tập đúng** khi yêu cầu là tuyệt đối. Khi invariant cứng kiểm tra được bằng SQL trên toàn bộ tập, ưu tiên xác minh đầy đủ với tải được kiểm soát.

## 11. Cưỡng chế invariant bằng constraint sau khi dữ liệu sẵn sàng

Khi đã chứng minh dữ liệu đích không NULL và khớp mapping, có thể thêm constraint để ngăn writer mới phá invariant.

Ví dụ với PostgreSQL:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT orders_status_text_present
CHECK (status_text IS NOT NULL) NOT VALID;

ALTER TABLE orders
ADD CONSTRAINT orders_status_text_domain
CHECK (status_text IN ('PENDING', 'PAID', 'CANCELLED')) NOT VALID;
~~~

Constraint CHECK NOT VALID được PostgreSQL áp cho các INSERT/UPDATE mới phù hợp, nhưng chưa quét chứng minh mọi hàng cũ. Sau khi không còn hàng vi phạm, chạy:

~~~sql
ALTER TABLE orders
VALIDATE CONSTRAINT orders_status_text_present;

ALTER TABLE orders
VALIDATE CONSTRAINT orders_status_text_domain;
~~~

**Lưu ý thời điểm triển khai:** nếu còn writer chỉ ghi status_code mà không điền status_text, constraint present sẽ khiến các INSERT/UPDATE của writer đó lỗi. Phải có writer tương thích hoặc trigger/chiến lược chuyển tiếp trước khi thêm constraint. Việc thêm/validate constraint cũng có thể cần lock và tiêu thụ I/O trên bảng lớn; đánh giá PostgreSQL phiên bản, lock timeout và tác động production trước khi chạy.

Nếu trong giai đoạn vẫn giữ hai cột và muốn database bảo vệ mapping, có thể dùng CHECK về tính tương đương:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT orders_status_mapping_consistent
CHECK (
    status_code IN (0, 1, 2)
    AND status_text IS NOT NULL
    AND status_text = CASE status_code
        WHEN 0 THEN 'PENDING'
        WHEN 1 THEN 'PAID'
        WHEN 2 THEN 'CANCELLED'
        ELSE NULL
    END
) NOT VALID;
~~~

Sau khi đối soát và bảo đảm mọi writer ghi cả hai giá trị, VALIDATE constraint này. Khi chuyển representation chính sang status_text rồi muốn loại status_code, cần thay đổi constraint tương ứng ở đợt contract; không giữ một CHECK tham chiếu cột chuẩn bị DROP.

**Không hiểu nhầm:** việc validate constraint thành công là bằng chứng mạnh cho đúng **biểu thức constraint trên những row tồn tại tại thời điểm được kiểm tra**, không chứng minh tất cả quy tắc nghiệp vụ nằm ngoài biểu thức ấy.

## 12. Khi nào có thể chuyển đường đọc sang cột mới?

Chỉ chuyển khi các điều kiện đã xác minh thỏa mãn:

1. Schema đích tồn tại tại mọi database/shard cần phục vụ.
2. Mọi writer còn tồn tại đồng bộ representation theo contract.
3. Backfill đã xử lý dữ liệu thuộc phạm vi dự định.
4. Full reconciliation hoặc kiểm tra tương đương có độ bao phủ phù hợp trả mismatch=0 cho invariant cứng.
5. Constraint cần thiết đã được thêm/validate hoặc có cơ chế cưỡng chế khác.
6. Read path mới đã được chạy thử nghiệm/canary với kết quả đúng.
7. Replica, CDC, cache và read model được cập nhật phù hợp, không dùng bản sao stale để xác nhận cutover của primary.
8. Có runbook rollback, tiến độ/phiên bản ứng dụng và người chịu trách nhiệm quyết định.

Không dùng một dashboard hiển thị progress 100% làm điều kiện duy nhất.

### 12.1. Shadow read để so kết quả trước cutover

Trong giai đoạn đọc cũ vẫn authoritative, chạy song song logic đọc mới trên một tỷ lệ nhỏ request hoặc trong job riêng:

~~~text
Authoritative read: status_code=1 -> PAID
Candidate read:     status_text=PAID
Outcome: MATCH
~~~

Nếu khác:

~~~text
Authoritative read: status_code=1 -> PAID
Candidate read:     status_text=PENDING
Outcome: MISMATCH, không chuyển người dùng sang candidate
~~~

Shadow read phải kiểm soát tải DB và bảo mật log, và nếu hai câu đọc xảy ra ở các thời điểm khác nhau dưới ghi đồng thời, cần tránh coi một race đọc bình thường là lỗi data migration. Tốt nhất đọc cả hai representation trong **cùng row/snapshot** khi có thể.

### 12.2. Chuyển bằng feature flag có đường lui

Có thể tổ chức:

~~~text
READ_MODE = LEGACY
  -> CANARY_NEW (1% traffic)
  -> NEW (100%)
  -> OBSERVE
  -> CONTRACT (đợt triển khai khác)
~~~

Nếu phát hiện lỗi trong CANARY_NEW, chuyển về LEGACY khi cột cũ còn được ghi đúng. **Rollback feature flag không thể tự cứu dữ liệu cũ đã ngừng cập nhật**: trong giai đoạn hỗ trợ rollback, phải duy trì cả hai representation nhất quán hoặc có kế hoạch forward fix/rebuild.

Feature flag cho phép thay đổi routing nhanh hơn nhưng không thay thế migration data quality. Đừng xóa nguồn cũ ngay sau khi traffic đọc mới lên 100%.

## 13. Sau cutover: xác minh hành vi ứng dụng và dữ liệu mới

Việc chuyển reader sang status_text chỉ là một mốc. Phải tiếp tục xác minh **những lệnh ghi mới** và **những đường đọc thực tế** sau khi traffic chạy trên representation mới.

### 13.1. Ba nhóm kiểm tra sau cutover

**A. Kiểm tra cấu trúc và dữ liệu**

- status_text không NULL ở những record bắt buộc.
- Không còn status_text ngoài danh sách giá trị hợp lệ.
- status_text tương đương với status_code khi còn duy trì hai cột.
- Không mất/nhân đôi khóa hoặc orphan record.
- Các constraint và index quan trọng còn hiệu lực theo schema thực tế.
- Dữ liệu theo tenant/partition vẫn đúng phạm vi, không rò qua đường query mới.

**B. Kiểm tra đường đọc/ghi nghiệp vụ**

- Order vừa tạo đọc được và có đúng trạng thái.
- Chuyển PENDING → PAID, PENDING → CANCELLED đi theo các điều kiện hợp lệ.
- Hai request cập nhật cạnh tranh không cùng ghi đè trạng thái.
- Rollback transaction trả mọi thay đổi về trạng thái hợp lệ.
- API legacy/event consumer/report không suy diễn status_text sai.
- Search index, cache và read replicas phản ánh representation mới theo mức trễ được phép.

**C. Kiểm tra vận hành**

- Error rate, SQLSTATE, connection pool, deadlock, lock waits và latency p95/p99 so với baseline.
- Query plan và chỉ mục cho những câu WHERE status_text, GROUP BY status_text.
- WAL sinh thêm, replication lag, tải batch và độ lớn bảng/index.
- Tỷ lệ fallback về đọc cũ và số bản ghi bị dual-write lệch.
- Tốc độ tăng dữ liệu đích ở mọi tenant mới, kể cả record có UUID nhỏ hơn cursor trước đó.

### 13.2. Kiểm tra snapshot sau cutover

~~~sql
SELECT
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE status_text IS NULL) AS null_target,
    COUNT(*) FILTER (
        WHERE status_text NOT IN ('PENDING', 'PAID', 'CANCELLED')
    ) AS invalid_target,
    COUNT(*) FILTER (
        WHERE status_text IS DISTINCT FROM CASE status_code
            WHEN 0 THEN 'PENDING'
            WHEN 1 THEN 'PAID'
            WHEN 2 THEN 'CANCELLED'
            ELSE NULL
        END
    ) AS mapping_mismatch
FROM orders;
~~~

Nếu dữ liệu vẫn liên tục được ghi kép, câu SELECT trên primary nhìn thấy một snapshot nhất quán của các hàng tại thời điểm statement bắt đầu. Kết quả mapping_mismatch=0 tại 11:00 không chứng minh writer không thể gây mismatch lúc 11:01; vì vậy cần **cưỡng chế ở database** và giám sát trong một cửa sổ ổn định.

### 13.3. So số liệu trước–sau không có nghĩa so hai COUNT tại hai giờ

Giả sử lúc 9 giờ có 1 triệu order, lúc 12 giờ có 1,02 triệu order. Không được báo migration tạo ra 20.000 record trùng chỉ vì số lượng tăng. Cần biết có bao nhiêu lệnh INSERT/DELETE hợp lệ trong khoảng giữa.

Các cách giảm hiểu nhầm:

- So cùng tập khóa baseline đã chốt hoặc theo một watermark đáng tin.
- Đối chiếu delta hợp lệ do ứng dụng tạo ra sau baseline.
- Dùng snapshot nhất quán khi so hai representation tại một mốc.
- Kiểm tra từng row bằng khóa và phép mapping, thay vì chỉ so tổng.
- Giữ dấu mốc topology/leader nếu đo qua failover; tránh kết luận dựa trên một replica bị lag.

### 13.4. Kiểm tra ảnh hưởng hiệu năng của schema mới

Chuyển WHERE status_code = 1 sang WHERE status_text = 'PAID' có thể thay đổi độ chọn lọc, kích thước index và execution plan. Chuyển đổi đúng giá trị không bảo đảm query mới nhanh như query cũ.

Các phương pháp:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id
FROM orders
WHERE tenant_id = 42
  AND status_text = 'PAID'
ORDER BY updated_at DESC, id DESC
LIMIT 50;
~~~

EXPLAIN ANALYZE **thực sự thực thi câu SELECT**, nên chỉ chạy theo chính sách cho phép và trên workload/dữ liệu phù hợp. Với UPDATE/DELETE, EXPLAIN ANALYZE cũng sẽ thực thi DML nếu không dùng transaction rollback có kiểm soát, vì vậy không chạy tùy tiện trên production.

Nếu cần thêm index, lên kế hoạch về khóa và tài nguyên. Với PostgreSQL, CREATE INDEX CONCURRENTLY có các giới hạn về transaction block và failure handling riêng; không nhét một cách máy móc vào cùng transaction với toàn bộ migration script.

## 14. Lập kế hoạch rollback và forward fix ngay từ đầu

### 14.1. Rollback code khác rollback dữ liệu

Rollback application từ reader mới về reader cũ có thể nhanh **nếu cột cũ vẫn được ghi chính xác**. Nhưng nếu sau cutover writer đã đổi sang chỉ ghi status_text, status_code có thể cũ. Lúc ấy đổi flag về cũ làm ứng dụng nhìn dữ liệu lỗi thời.

Phân biệt:

- **Rollback traffic/reader:** đổi đường đọc nhưng dữ liệu representation cũ còn đúng.
- **Rollback writer:** chạy lại version ứng dụng cũ; có thể không tương thích với schema/logic mới.
- **Rollback schema:** hủy thay đổi DDL; có thể không an toàn nếu dữ liệu mới không biểu diễn được ở cột cũ.
- **Rollback dữ liệu:** phục hồi hoặc biến đổi lại hàng; có thể làm mất các ghi mới phát sinh nếu làm sai.
- **Forward fix:** sửa mapping, backfill lại tập lỗi hoặc deploy code tương thích rồi tiếp tục trên schema mới.

**Không có một lệnh DOWN migration chung có thể hoàn tác mọi biến đổi dữ liệu và toàn bộ giao dịch mới sinh ra**.

### 14.2. Khi nào nên forward fix?

Với lỗi “một nhóm status_code=2 chưa được backfill” nhưng representation gốc vẫn tồn tại, một forward fix có điều kiện có thể sửa lại chỉ các row mismatch rồi đối soát. Nó thường an toàn hơn restore toàn bộ database về snapshot cũ, vì restore có thể làm mất các lệnh tạo đơn/phát sinh thanh toán sau snapshot.

Nhưng nếu mapping nghiệp vụ sai toàn diện hoặc đã xóa dữ liệu gốc không thể khôi phục, cần tạm dừng ghi và chọn phương án phục hồi theo runbook cùng chuyên gia nghiệp vụ. Tránh tự động sửa row khi chưa hiểu nguồn sai lệch.

### 14.3. Contract là bước nguy hiểm nhất

~~~sql
-- Chỉ ở đợt riêng, khi không còn code hay constraint tham chiếu:
ALTER TABLE orders DROP COLUMN status_code;
~~~

Sau khi DROP, phép đối chiếu trực tiếp status_text = f(status_code) không còn thực hiện được trên bảng hiện tại. Nếu bản mới bị lỗi logic, khả năng rollback ứng dụng cũ giảm đáng kể. Cần giữ:

- Bằng chứng đã đối soát toàn bộ dữ liệu và business approval.
- Migration trace, tài liệu mapping và metric sau cutover.
- Backup/restore được kiểm thử trước khi xóa dữ liệu không thể tái tạo.
- Bằng chứng không còn reader/writer/CDC/report dùng cột cũ.
- Thời gian quan sát ổn định trước contract theo tiêu chí đã công bố.

Nếu tạo backup, kiểm tra có thể restore, có WAL hoặc cơ chế point-in-time recovery cần thiết, quyền truy cập và khóa giải mã. **Backup thành công không đồng nghĩa restore thành công**.

## 15. Thử nghiệm migration bằng dữ liệu đại diện và fault injection

### 15.1. Test mapping đơn vị

~~~java
@Test
void statusMappingIsExact() {
    assertEquals("PENDING", mapStatus((short) 0));
    assertEquals("PAID", mapStatus((short) 1));
    assertEquals("CANCELLED", mapStatus((short) 2));
    assertThrows(
        IllegalArgumentException.class,
        () -> mapStatus((short) 9)
    );
}
~~~

Hàm mapStatus cần được định nghĩa trong ứng dụng hoặc test helper. Unit test chứng minh quy tắc mapping ở một nhánh code, **không chứng minh** câu SQL backfill thực hiện tương đương hoặc dữ liệu production không có mã 9.

### 15.2. Test dữ liệu bẩn

Tạo test fixtures có:

- Giá trị status_code hợp lệ và mã ngoài tập cho phép.
- Bản ghi thuộc các tenant khác nhau.
- Dữ liệu lịch sử, row soft-deleted và record tạo sát thời điểm backfill.
- Cùng ID với nhiều thay đổi status theo thời gian qua các transaction.
- Dữ liệu tiền vượt giới hạn BIGINT, decimal có phần lẻ không biểu diễn được khi đổi kiểu.
- Chuỗi Unicode khác dạng chuẩn hóa và timestamp ở biên timezone nếu có các phép chuyển đổi tương ứng.

Test phải xác nhận job **dừng hoặc phân loại dữ liệu không chuyển được** thay vì âm thầm tạo giá trị sai.

### 15.3. Test ghi đồng thời với backfill

Dùng hai connection/transaction riêng trên PostgreSQL staging:

~~~text
T1 (backfill): đọc tập ID có order O7
T2 (writer):   đổi O7 từ PENDING sang PAID
T1:           cập nhật status_text từ giá trị hiện hành
T2:           COMMIT theo giao thức dual-write
Kiểm chứng:   status_code=1 và status_text='PAID'
~~~

Thực tế thứ tự lock/wait có thể khác. Điều phải chứng minh là **mọi lịch được DB cho phép** theo thiết kế không để hai representation lệch tại thời điểm commit. Dùng latch/barrier/fault injection để tái hiện các mốc, tránh Thread.sleep ngẫu nhiên làm test không ổn định.

### 15.4. Test crash và replay batch

~~~text
Batch chọn 1.000 ID
UPDATE 200 row thiếu target
DB COMMIT thành công
JVM chết trước khi lưu checkpoint

Job restart:
  đọc checkpoint cũ
  xử lý lại cùng tập ID
  UPDATE bỏ qua các row đã khớp
  đối soát vẫn PASS
~~~

Nếu checkpoint và transaction không cùng database transaction, đây là tình huống phải chấp nhận khi thiết kế replay idempotent. Ngược lại, checkpoint được cập nhật **trước** COMMIT rồi tiến trình chết có thể khiến job bỏ qua batch chưa được ghi; cần tránh thứ tự đó.

### 15.5. Test rollout nhiều phiên bản

Cho ứng dụng cũ/mới cùng chạy và ghi xen kẽ trên môi trường tương tự production. Nếu không có trigger/compatibility protocol, test phải chứng minh tình trạng mismatch để xác định rủi ro, rồi xác nhận giải pháp đã loại nó.

Sau khi reader mới nhận traffic, thử rollback flag về reader cũ. Nếu dữ liệu cũ đã ngừng cập nhật, test phải từ chối rollback vì không còn an toàn; không coi việc flag đổi thành công là đủ.

### 15.6. Test tính bền vững, replica và failover

Một transaction dual-write có thể commit thành công trên primary nhưng replica phục vụ read validation vẫn chưa replay commit. Nếu dùng replica để so dữ liệu trước cutover mà không ràng buộc watermark/snapshot, có thể kết luận nhầm “backfill chưa xong” hoặc “đã xong”.

Kiểm thử:

- Replica bị lag trong lúc backfill; hệ thống vẫn xác định mốc kiểm chứng đúng.
- Đường đọc authoritative và candidate dùng cùng primary hoặc snapshot phù hợp.
- COMMIT outcome chưa rõ: job không coi timeout là rollback, có thể đối soát và replay idempotent.
- Failover không làm mất checkpoint hoặc làm lẫn timeline giữa các primary.
- Restore từ backup có thể tái lập trạng thái phù hợp với phiên bản schema/ứng dụng.

Không thực hiện pause WAL hoặc cố ý làm mất primary trên production; dùng môi trường fault injection có kiểm soát.

## 16. Điều tra mismatch: đừng sửa hàng loạt trước khi biết nguyên nhân

Khi kiểm chứng phát hiện mismatch, các nguyên nhân thường gặp:

| Triệu chứng | Giả thuyết | Cách kiểm tra |
|---|---|---|
| status_text NULL trên row mới | Writer cũ không ghi cột mới | Kiểm tra phiên bản client/job, thời điểm tạo row |
| status_text cũ sau update status_code | Dual-write thiếu ở một đường | Traces, audit, SQL workload, transaction log phù hợp |
| Mismatch tăng sau mỗi batch | Backfill đang dùng giá trị nguồn stale | So SQL UPDATE và vị trí tính mapping |
| Mismatch rải rác theo tenant | Một tenant/shard chưa được triển khai | So inventory deployment và phạm vi chạy job |
| Count giống nhưng hash khác | Sai mapping hoặc hoán đổi giá trị | So theo khóa và trường |
| Count khác do log archive | Phạm vi dữ liệu không nhất quán | Xác định snapshot và filter |
| Sai tiền ở một vài currency | Giả định số chữ số thập phân chung | Đối chiếu currency policy và round/overflow |
| Row thiếu sau checkpoint cuối | UUID mới nằm trước cursor | Kiểm tra INSERT trong lúc scan và writer compatibility |
| Check ở replica không thấy row | Replica chưa replay | Đối chiếu LSN/progress trên primary/standby |
| App mới lỗi khi cột hợp lệ | Serializer/enum mapping hoặc query chưa tương thích | Integration test với binary/config thật |

Quy trình ứng phó:

1. Dừng hoặc giới hạn rollout/cutover nếu invariant cứng bị vi phạm.
2. Ghi lại migration version, thời gian, phạm vi lỗi, query điều tra và số lượng.
3. Tìm nguồn gây mismatch, không xóa sạch bằng một UPDATE không có điều kiện.
4. Chọn sửa mapping, reprocess tập lỗi, sửa writer hay rollback theo runbook.
5. Chạy lại đối soát trên **toàn phạm vi bị ảnh hưởng**, không chỉ những record đã sửa.
6. Cập nhật test/monitoring để lỗi cùng loại không tái xuất hiện.

## 17. Go/no-go: điều kiện quyết định chuyển đổi

Một bảng quyết định mẫu:

| Điều kiện | Minh chứng | Quyết định khi không đạt |
|---|---|---|
| Scope đã chốt | Inventory bảng/tenant/shard/partition | NO-GO |
| Không có source code ngoài mapping chưa xử lý | Report unknown_status=0 hoặc danh sách ngoại lệ phê duyệt | NO-GO nếu không có rule |
| Mọi writer tương thích | Version inventory, traces, thử concurrent | NO-GO |
| Backfill đã đi hết phạm vi | Checkpoint, số ID scan, remaining scan | NO-GO |
| Dữ liệu đích đầy đủ | null_target=0, anti-join missing=0 | NO-GO |
| Mapping đúng | mismatch=0 theo phép đối soát và constraint | NO-GO |
| Constraint quan trọng hợp lệ | DB metadata, kiểm tra constraint | NO-GO |
| Đường đọc canary đúng | Shadow comparison, API integration tests | NO-GO |
| Hiệu năng trong ngưỡng | p95/p99, lock wait, CPU, WAL/replica lag | Hoãn hoặc giảm tải |
| Có phương án rollback/forward fix | Runbook, backup restore đã thử | NO-GO |
| Theo dõi sau cutover sẵn sàng | Dashboard, alert, owner, thời gian giám sát | NO-GO |

Ngưỡng có thể khác theo loại dữ liệu: report chỉ dùng cho hiển thị có thể chấp nhận một số sai khác được liệt kê, nhưng ledger hay khóa phân quyền có thể yêu cầu **không một mismatch**. Việc chấp nhận ngoại lệ phải được định nghĩa trước, có người phê duyệt và không được ngụy trang thành pass tuyệt đối.

## 18. Bài tập tình huống

### Bài A — Migration tool báo SUCCESS

Flyway đánh dấu phiên bản schema mới đã áp dụng, nhưng 8% đơn hàng vẫn có status_text NULL.

**Câu hỏi:** Migration đã hoàn tất chưa? Kiểm tra tiếp gì?

**Gợi ý:** Chưa. DDL applied không bằng backfill hoàn tất. Cần đo coverage, tìm row thiếu theo tenant/partition, kiểm tra writer tương thích và hoàn tất reconciliation trước cutover.

### Bài B — COUNT trước và sau khác nhau

Baseline 1.000.000 record lúc 08:00, đích có 1.005.000 record lúc 10:00. Trong 2 giờ ứng dụng nhận 5.000 order mới.

**Câu hỏi:** Có thể kết luận đích bị nhân đôi 5.000 record không?

**Gợi ý:** Không. Phải so cùng phạm vi/snapshot và delta hợp lệ. Tổng theo hai thời điểm khác nhau không chứng minh duplicate.

### Bài C — Cập nhật trạng thái khi backfill

Backfill đã ghi status_text=PENDING cho O7. Một worker cũ sau đó UPDATE status_code=1 nhưng không đổi status_text.

**Câu hỏi:** Cần xử lý gì trước khi reader mới đi vào hoạt động?

**Gợi ý:** Phải loại bỏ/điều phối writer cũ hoặc dùng trigger tương thích, sửa mismatch, chạy lại đối soát và cưỡng chế invariant bằng constraint khi sẵn sàng. Không chỉ tăng tốc backfill.

### Bài D — Cursor đã tới cuối bảng

Job duyệt order theo UUID và tới ID lớn nhất, báo 100% scan. Trong lúc job chạy có INSERT mới với UUID nhỏ hơn cursor.

**Câu hỏi:** Dữ liệu đó có được backfill chưa?

**Gợi ý:** Có thể chưa. Cần writer mới ghi target và full scan remaining/mismatch. Cursor không tự chứng minh tất cả row hiện tại đều được xử lý.

### Bài E — Câu WHERE status_text != expected

Một query kiểm tra mismatch bằng !=, nhưng một số status_text NULL không được đếm là mismatch.

**Câu hỏi:** Vì sao và sửa thế nào?

**Gợi ý:** SQL dùng logic ba giá trị. Dùng IS DISTINCT FROM và đếm NULL riêng, kết hợp kiểm tra source code ngoài miền cho phép.

### Bài F — Từ tiền thập phân sang minor unit

Hệ thống đổi 12.345 thành 1235 minor units do làm tròn. Một số record lịch sử được làm tròn khác với quy tắc kế toán.

**Câu hỏi:** Cần những kiểm chứng gì?

**Gợi ý:** Phép chuyển đổi exact theo currency, phát hiện số không biểu diễn được và overflow, so theo khóa và tổng kế toán, không dùng float và không âm thầm làm tròn.

### Bài G — Rollback ứng dụng sau khi ngừng dual-write

Một phiên bản ứng dụng mới chỉ cập nhật status_text. Sau hai ngày, đội vận hành bật feature flag đọc status_code trở lại.

**Câu hỏi:** Vì sao đây không phải rollback an toàn?

**Gợi ý:** status_code đã trở nên stale. Phải bảo đảm tương thích đảo chiều hoặc có phương án forward fix/khôi phục trước khi quay lại reader cũ.

### Bài H — Validation trên read replica

Primary vừa commit 10.000 bản ghi backfill, replica chưa replay đầy đủ. Job validation trên replica báo còn 10.000 record thiếu.

**Câu hỏi:** Có thể tin kết luận đó để rollback không?

**Gợi ý:** Không tự động. Cần kiểm tra replica replay position và snapshot, hoặc đối soát trên primary/source có bảo đảm phù hợp.

### Bài I — Dấu mốc checkpoint bị mất ACK

DB đã commit batch, nhưng job bị timeout khi ghi kết quả checkpoint ra hệ thống khác. Job restart và chạy lại batch.

**Câu hỏi:** Tính chất nào cần bảo đảm?

**Gợi ý:** Replay idempotent; checkpoint không được tiến trước khi commit được biết, cần readback/reconciliation khi outcome chưa rõ. Không có side effect nghiệp vụ lặp.

### Bài J — Hash bằng nhau

Hai bảng có cùng COUNT và cùng một hash tổng hợp yếu, nhưng một order bị thay người nhận và một order khác bị thay ngược lại.

**Câu hỏi:** Vì sao chưa đủ chứng cứ?

**Gợi ý:** Tổng và hash tổng hợp có thể không phát hiện hoán đổi/collision hoặc được tạo từ canonicalization sai. Cần khóa định danh, phép so theo row, invariant nghiệp vụ và chính sách hash rõ.

## 19. Checklist xác minh migration dữ liệu

### Trước chuyển đổi

- [ ] Đã mô tả mapping và những giá trị không thể chuyển đổi.
- [ ] Đã chốt bảng/tenant/partition/shard và snapshot/watermark của baseline.
- [ ] Đã đo số lượng, phân bố, NULL, duplicate, orphan, unknown codes và invariant.
- [ ] Đã kiểm tra số tiền, thời gian, Unicode và các dữ liệu biên khi có liên quan.
- [ ] Đã kiểm kê mọi writer/reader, job và ứng dụng nhiều phiên bản.
- [ ] Đã có tiêu chí go/no-go, xử lý ngoại lệ, backup và runbook phục hồi.

### Trong chuyển đổi

- [ ] Expand schema không phá phiên bản ứng dụng hiện tại.
- [ ] Writer ghi representation đồng bộ hoặc đã có chiến lược chuyển tiếp tương đương.
- [ ] Backfill theo batch nhỏ, có checkpoint bền vững và retry idempotent.
- [ ] Không dùng cursor là bằng chứng mọi row hiện tại đều được xử lý.
- [ ] Có kiểm chứng NULL/mismatch/unknown theo tenant và partition.
- [ ] Quan sát CPU, I/O, WAL, replica lag, lock wait, pool và latency.
- [ ] Khi gặp dữ liệu bẩn, dừng hoặc phân loại thay vì âm thầm gán mặc định.
- [ ] Đã thử concurrency và mất ACK ở các điểm của migration.

### Sau chuyển đổi

- [ ] Dữ liệu đích có coverage và mapping đúng trên toàn phạm vi.
- [ ] Constraint cần thiết được thêm và validate khi writer đã tương thích.
- [ ] Shadow read/canary cho kết quả đúng theo snapshot phù hợp.
- [ ] API với phiên bản mới và cũ hoạt động đúng theo kế hoạch rollout.
- [ ] Invariant nghiệp vụ vẫn đúng với các transaction và cập nhật đồng thời.
- [ ] Query plan, chỉ mục và chỉ số lỗi/độ trễ không vượt ngưỡng.
- [ ] Reconciliation theo dõi tiếp các writer mới và những lag/bản sao liên quan.
- [ ] Rollback/forward fix vẫn khả thi; chưa DROP nguồn trước thời điểm contract.
- [ ] Báo cáo kết quả, bất thường, owner và bằng chứng phục hồi được lưu an toàn.

## 20. Kết luận

Xác minh dữ liệu khi tiến hóa schema là một **quy trình bằng chứng liên tục**. Trước khi chuyển đổi, phải hiểu dữ liệu nguồn, khóa định danh, miền giá trị và các ngoại lệ đã tồn tại. Trong khi chuyển đổi, phải đảm bảo writer tương thích, backfill có thể replay và những bản ghi mới không bị lọt khỏi phạm vi. Sau cutover, phải kiểm tra tính tương đương dữ liệu, invariant, cách ứng dụng đọc/ghi, hiệu năng và khả năng khôi phục.

Ba câu hỏi cần trả lời cho mọi migration là:

1. **Trước:** Dữ liệu nguồn đúng trong phạm vi nào, và ta biết điều đó bằng chứng cứ nào?
2. **Trong:** Các transaction mới và batch backfill có thể làm lệch dữ liệu ở lịch đồng thời nào, và cơ chế nào ngăn được?
3. **Sau:** Đích có đúng theo từng khóa và invariant nghiệp vụ, các reader/writer có dùng đúng representation, và ta làm gì nếu phát hiện sai?

Một migration thành công không chỉ là DDL áp dụng và job kết thúc. Nó là trạng thái mà **dữ liệu đã được chứng minh đúng theo hợp đồng, hệ thống đang giữ được tính đúng đó và vẫn có phương án an toàn khi lỗi xuất hiện muộn**.
