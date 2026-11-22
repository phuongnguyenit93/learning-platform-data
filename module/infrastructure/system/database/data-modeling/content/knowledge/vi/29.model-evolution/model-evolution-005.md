# Điền bổ sung dữ liệu lịch sử với khả năng tiếp tục và đối soát

Khi tiến hóa một mô hình dữ liệu, thêm bảng hoặc cột mới thường chỉ là bước đầu. Hệ thống đã có hàng triệu bản ghi được tạo theo cấu trúc cũ: muốn sử dụng mô hình mới, ta cần **điền bổ sung dữ liệu lịch sử (backfill)**. Nếu chạy một lệnh cập nhật khổng lồ rồi mất kết nối ở giữa, làm sao biết phần nào đã hoàn thành, có thể tiếp tục từ đâu và những hàng nào bị bỏ sót? Nếu dữ liệu nguồn thay đổi trong lúc chạy, làm sao chắc rằng bảng mới phản ánh đúng sự thật? Nếu đếm hàng bằng nhau nhưng giá trị bị ánh xạ sai, làm sao phát hiện?

**Backfill có khả năng tiếp tục và đối soát** là một quy trình chuyển hoặc bổ sung dữ liệu trong đó:

1. **Đầu vào và quy tắc biến đổi có định danh rõ**: nguồn, phạm vi, grain, phiên bản logic, thời điểm chốt.
2. **Công việc được chia thành các lô (batch/chunk) có thể kiểm soát**: không cần một transaction bao toàn bộ lịch sử.
3. **Checkpoint phản ánh phần đã commit**, không chỉ phần đã đọc hoặc đã gửi yêu cầu xử lý.
4. **Chạy lại không gây sai lệch**: cơ chế idempotency, khóa duy nhất và xử lý xung đột được thiết kế trước.
5. **Đối soát nguồn–đích được thực thi** theo khóa và giá trị, không chỉ bằng số hàng tổng.
6. **Chuyển luồng đọc/ghi chỉ sau khi đạt tiêu chí nghiệm thu**, với phương án dừng, khôi phục và rollback.

Bài thuộc chương **Tiến hóa mô hình** của mô-đun **DATABASE_DATA_MODELING**. Nội dung kết nối mô hình nghiệp vụ với khóa, ràng buộc, mô hình quan hệ, lược đồ vật lý, lịch sử và giao dịch; triển khai ví dụ **PostgreSQL** có thể theo dõi từng batch; sau đó mở rộng tới CDC, dữ liệu đến trễ và hệ thống đang hoạt động.

## 1. Backfill là gì và khác các thao tác gần giống ra sao?

**Backfill** là việc điền dữ liệu cho một khoảng quá khứ vào **cột, bảng, chỉ mục hoặc mô hình dẫn xuất mới**, dựa trên những nguồn đã tồn tại. Mục đích có thể là hoàn thiện dữ liệu thiếu, chuyển schema, chuẩn hóa lại các giá trị, xây bảng fact/snapshot hoặc tái dựng một read model.

| Hoạt động | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Backfill** | Điền dữ liệu lịch sử vào cấu trúc mới hoặc phần dữ liệu còn thiếu | Thêm **order_local_date** cho các đơn cũ |
| **Data migration** | Chuyển dữ liệu và hợp đồng đọc/ghi sang mô hình khác | Tách bảng orders thành orders và order_addresses |
| **Replay** | Xử lý lại sự kiện/đầu vào đã ghi theo quy tắc xác định | Chạy lại các sự kiện bán để tạo fact |
| **Reconciliation** | Đối chiếu hai tập dữ liệu theo định nghĩa chung | Tìm đơn thiếu, sai ngày, sai tổng tiền |
| **Repair/correction** | Sửa dữ liệu bị ghi sai hoặc lệch với nguồn chuẩn | Sửa nhầm đơn giá tại thời điểm đặt |
| **Catch-up** | Bắt kịp các thay đổi mới xuất hiện trong lúc backfill | Nạp CDC từ vị trí snapshot tới hiện tại |
| **Cutover** | Chuyển người đọc/ghi sang dữ liệu và đường xử lý mới | Cho dashboard đọc **order_facts_v2** |

Các hoạt động thường diễn ra cùng một dự án nhưng **không đồng nghĩa**. Backfill xong một snapshot lịch sử không có nghĩa các thay đổi phát sinh trong lúc xử lý đã được nạp. Đếm hàng đối chiếu xong không có nghĩa ứng dụng có thể chuyển toàn bộ lưu lượng ngay.

### 1.1. Những ví dụ backfill thường gặp

- Thêm cột **normalized_phone** để tra cứu theo số điện thoại đã chuẩn hóa.
- Chuyển giá tiền từ **DECIMAL** sang **Money + currency** có quy tắc làm tròn rõ.
- Tạo **customer_id** bền vững thay cho phụ thuộc vào email có thể đổi.
- Điền **dimension surrogate key** cho các fact cũ, có xử lý lịch sử SCD Type 2.
- Tách địa chỉ hiện hành và **địa chỉ snapshot lúc giao dịch**.
- Dựng **daily_sales_v2** từ các dòng bán đã ghi trước khi có kho phân tích.
- Tạo **tenant_id** hoặc khóa phân vùng mới cho các bảng cũ trước khi shard.

Mỗi ví dụ có **grain, nguồn chuẩn và mức rủi ro khác nhau**. Không nên lấy một script UPDATE dùng được cho cột đơn giản rồi mặc định nó đủ cho đổi danh tính hoặc phân rã quan hệ nhiều bảng.

### 1.2. Bất biến cần giữ

Backfill nên viết thành những điều kiện có thể kiểm thử:

~~~text
Với mỗi record nguồn đủ điều kiện theo snapshot S:
  -> tồn tại đúng một record đích tương ứng,
  -> có khóa đúng,
  -> các trường được biến đổi đúng theo transform_version V.

Với mỗi record đích thuộc backfill:
  -> truy được nguồn/phiên bản và quy tắc tạo record.

Một batch chỉ được xem là hoàn tất nếu:
  -> các bản ghi đích của batch đã commit,
  -> checkpoint tương ứng được commit cùng một transaction.
~~~

Khi có lọc nghiệp vụ (ví dụ **CANCELLED** không thuộc fact đơn đã đặt), số hàng đích không bằng tổng số hàng nguồn là **đúng theo thiết kế**. Phải đối soát với **tập nguồn đủ điều kiện**, không so mọi hàng của bảng cũ.

## 2. Những quyết định phải chốt trước khi bắt đầu

### 2.1. Grain, khóa và phạm vi duy nhất

Trả lời lần lượt:

- **Một hàng nguồn là gì?** Một đơn, một dòng đơn, một phiên bản sửa, một sự kiện nguồn?
- **Một hàng đích là gì?** Cùng một đơn, một bản tổng hợp tenant–ngày, hay một quan hệ mới?
- **Khóa nào ổn định qua thời gian?** ID có thể được cấp lại hoặc thay đổi không?
- **Khóa duy nhất thuộc phạm vi nào?** Toàn hệ thống, tenant, kỳ, nguồn dịch vụ hay phiên bản snapshot?
- **Một nguồn ánh xạ sang bao nhiêu đích?** Một–một, một–nhiều, nhiều–một?
- **Trạng thái bị xóa/hủy và dữ liệu không hợp lệ được xử lý thế nào?**

Với chuyển đổi **một–một**, khóa **source_record_id** có thể là định danh tự nhiên của record đích. Với chuyển đổi **nhiều–một**, cần khóa group và cơ chế lưu nguồn đóng góp. Với chuyển đổi **một–nhiều**, phải có khóa phần tử dẫn xuất ổn định để retry không sinh nhiều bản sao.

### 2.2. Dữ liệu nguồn có thể thay đổi hay không?

Có hai trường hợp lớn:

**Nguồn đã chốt/immutable:** ví dụ export đã hoàn tất, manifest được đóng băng, không có thêm hoặc sửa hàng. Có thể scan theo khóa ổn định, checkpoint tiến dần, tái chạy cùng snapshot.

**Nguồn đang hoạt động/mutable:** trong lúc quét, record có thể được thêm, cập nhật, xóa. Dùng **MAX(id)** làm mốc trên một bảng đang ghi **không tự tạo snapshot**. Một transaction có thể cấp ID rồi commit muộn, khiến một hàng có ID nhỏ hơn checkpoint xuất hiện sau khi phần khóa đó đã được quét. Ngoài ra, UPDATE vào hàng đã quét còn có thể làm bảng đích cũ đi.

Với nguồn sống, cần **snapshot nhất quán + change capture/CDC**, hoặc quy trình đồng bộ có hàng đợi, version và đối soát tương đương. Backfill ví dụ trong bài trước tiên dùng **snapshot bất biến** để tập trung vào checkpoint; sau đó mục 11 bàn cách đưa vào hệ thống vẫn có ghi mới.

### 2.3. Thời gian và phiên bản biến đổi

Một dự án phải nêu rõ:

| Thành phần | Ví dụ |
| --- | --- |
| **Snapshot ID** | 501 |
| **Transform version** | order-fact-v2.1 |
| **Grain đích** | Một đơn PLACED trong snapshot |
| **Ngày báo cáo** | Ngày địa phương **Asia/Ho_Chi_Minh** từ placed_at |
| **Mốc nguồn** | Export đã chốt, không đổi trong quá trình nạp |
| **Chính sách lọc** | Chỉ trạng thái PLACED, không nạp CANCELLED |
| **Chính sách ghi trùng** | Không tạo thêm hàng nếu đã có đúng source ID |
| **Chính sách sửa nguồn** | Tạo phiên bản/correction hoặc chạy lại có đối soát |
| **Điều kiện nghiệm thu** | Tập khóa bằng nhau, giá trị bằng nhau, tổng theo nhóm khớp |

**Transform version** không chỉ là một chuỗi tùy ý: cần biết công thức tính, timezone, chính sách NULL/rounding, phiên bản mã và dữ liệu tham chiếu nếu có. Chạy lại hai lần cùng một tên version nhưng với logic khác nhau có thể cho kết quả khác mà không giải thích được.

## 3. Triển khai an toàn theo Expand → Backfill → Cutover → Contract

Một cách tiếp cận phổ biến trong tiến hóa hệ thống đang hoạt động:

~~~mermaid
flowchart LR
    OLD["Hệ thống hiện tại"]
    EXPAND["Expand: schema mới, nullable/đích mới"]
    SNAP["Chốt nguồn / snapshot + checkpoint"]
    FILL["Backfill theo batch + resume"]
    CATCH["Catch-up thay đổi mới"]
    VERIFY["Đối soát + shadow read"]
    CUT["Cutover: đổi nguồn đọc"]
    CONTRACT["Contract: bỏ đường cũ khi an toàn"]
    OLD --> EXPAND --> SNAP --> FILL --> CATCH --> VERIFY --> CUT --> CONTRACT
    FILL -- "lỗi có thể khôi phục" --> FILL
    VERIFY -- "sai lệch: sửa + chạy lại" --> FILL
~~~

Các bước cần lưu ý:

1. **Expand:** thêm schema mới theo cách ứng dụng cũ vẫn chạy được. Với cột mới, thường thêm nullable hoặc default an toàn trước; tránh đặt NOT NULL khi lịch sử chưa được điền.
2. **Nguồn đầu vào:** xác định snapshot/cutoff và cơ chế theo dõi thay đổi phát sinh, không đọc dữ liệu tùy thời điểm giữa các batch.
3. **Backfill:** quét khóa ổn định, ghi đích có thể lặp lại và checkpoint nguyên tử.
4. **Catch-up:** áp dụng những ghi mới/sửa/xóa phát sinh trong giai đoạn backfill theo quy tắc thứ tự/version.
5. **Đối soát:** so tập khóa, giá trị, tổng hợp và kết quả truy vấn ứng dụng mới.
6. **Cutover:** chuyển qua feature flag/route/pointer có giám sát, không xóa ngay đường cũ.
7. **Contract:** chỉ bỏ cột, bảng hoặc luồng ghi cũ khi chắc chắn không còn consumer và rollback window đã kết thúc.

**Không phải dự án nào cũng cần dual-write.** Một schema migration đơn giản trên bảng nhỏ có thể thực hiện ngay trong cửa sổ bảo trì. Nhưng với dữ liệu lớn, nhiều dịch vụ hoặc SLA liên tục, kế hoạch tách pha thường dễ kiểm soát hơn một transaction khổng lồ.

## 4. Vì sao checkpoint và idempotency phải đi cùng nhau?

Giả sử batch xử lý những order ID 101, 103, 105:

~~~text
Đã ghi hàng 101, 103 vào đích.
Ứng dụng crash trước khi ghi hàng 105.
Checkpoint đã ghi "last_id = 105".
Sau khi restart, job chỉ đọc id > 105.
=> Hàng 105 có thể bị bỏ sót vĩnh viễn.
~~~

Sai lầm là **đánh dấu đã hoàn tất trước khi việc ghi đích được bảo đảm commit**.

Chiều ngược lại:

~~~text
Đã commit hàng 101, 103, 105.
Ứng dụng crash trước khi ghi checkpoint.
Restart đọc lại id > 100.
=> Hàng 101, 103, 105 được xử lý lần nữa.
~~~

Nếu đích không có khóa duy nhất hoặc thao tác chỉ là **balance = balance + amount**, retry có thể nhân đôi kết quả.

Phương án tin cậy với nguồn snapshot và đích cùng PostgreSQL:

> **Ghi các hàng của batch và cập nhật checkpoint trong cùng một transaction**, cộng với khóa duy nhất và logic ghi có thể chạy lại.

Nếu source/target/checkpoint ở **nhiều hệ thống không chia sẻ transaction**, cần kết hợp idempotency, checkpoint sau xác nhận ghi, outbox/commit protocol hoặc cơ chế chuyên biệt; không thể giả định một transaction SQL bao phủ mọi hệ thống.

## 5. Bài toán thực hành: dựng bảng fact mới từ snapshot đơn hàng cũ

Giả sử hệ thống có bản xuất lịch sử **legacy_order_snapshot** đã được chốt, mỗi hàng là một đơn ở trạng thái cuối của phiên bản dữ liệu được xuất. Mô hình phân tích mới chỉ muốn lấy **đơn trạng thái PLACED** để tạo **reporting_order_fact_v2** phục vụ báo cáo số đơn và giá trị hàng hóa theo tenant/ngày.

**Giới hạn ví dụ:**

- **order_id** là ID dương, duy nhất toàn hệ thống trong dữ liệu nguồn; không sử dụng lại cho tenant khác.
- Snapshot ID **501** chỉ gồm dữ liệu cố định; việc không được sửa/xóa/nạp bổ sung sau khi chốt phải được **quy trình lưu trữ và quyền ghi** bảo vệ. DDL dưới đây không tự chứng minh snapshot bất biến.
- Mỗi đơn được ghi một lần vào đích. Chỉ **PLACED** được đưa vào fact; **CANCELLED** không tạo hàng đích.
- Giá trị **total_vnd** là số tiền hàng đã chốt trong nguồn; chưa mô hình hóa hoàn tiền, đổi trả, thuế, phí giao hàng hoặc ngoại tệ.
- **local_placed_date** là ngày theo múi giờ **Asia/Ho_Chi_Minh**, không phải ngày UTC hoặc ngày được nhập dữ liệu.
- Một job có quyền ghi đích trong ví dụ; nếu nhiều job cùng cập nhật một đơn, cần thêm chính sách phiên bản và quyền sở hữu.

### 5.1. Grain nguồn, grain đích và phép biến đổi

| Dataset | Một hàng là gì? | Khóa | Chú ý |
| --- | --- | --- | --- |
| **legacy_order_snapshot** | Một đơn trong một snapshot xác định | (snapshot_id, order_id) | Một snapshot chứa cả PLACED/CANCELLED |
| **reporting_order_fact_v2** | Một đơn PLACED đã được chuyển sang mô hình báo cáo | source_order_id | Một đơn chỉ có một hàng |
| **backfill_jobs** | Một lần backfill trên một snapshot và transform cụ thể | job_id | Giữ checkpoint đã commit |

Phép biến đổi:

~~~text
SOURCE: legacy_order_snapshot(snapshot_id = 501)

Nếu status = PLACED:
  source_order_id  = order_id
  tenant_id        = tenant_id
  local_placed_date =
      DATE(placed_at theo timezone Asia/Ho_Chi_Minh)
  amount_vnd       = total_vnd
  source_snapshot_id = 501
  transform_version  = order-fact-v2.1

Nếu status = CANCELLED:
  Không tạo fact hàng đích.
  Nhưng vẫn phải đánh dấu khóa nguồn đã được QUÉT trong checkpoint.
~~~

**Điểm dễ sai:** checkpoint theo **các hàng nguồn đã quét**, không theo **hàng đích đã ghi**. Nếu một batch chỉ gồm ba đơn CANCELLED, không có INSERT nào; job **vẫn phải tiến checkpoint** qua ba khóa ấy. Nếu chỉ lấy MAX(source_order_id) từ kết quả INSERT, job có thể lặp vô hạn ở vùng toàn đơn bị loại.

### 5.2. DDL của snapshot và bảng đích

~~~sql
CREATE TABLE legacy_order_snapshot (
    snapshot_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL CHECK (order_id > 0),
    tenant_id TEXT NOT NULL,
    placed_at TIMESTAMPTZ NOT NULL,
    order_status TEXT NOT NULL
        CHECK (order_status IN ('PLACED', 'CANCELLED')),
    total_vnd NUMERIC(20, 0) NOT NULL
        CHECK (total_vnd >= 0),
    PRIMARY KEY (snapshot_id, order_id)
);

CREATE TABLE reporting_order_fact_v2 (
    source_order_id BIGINT PRIMARY KEY,
    source_snapshot_id BIGINT NOT NULL,
    tenant_id TEXT NOT NULL,
    local_placed_date DATE NOT NULL,
    amount_vnd NUMERIC(20, 0) NOT NULL
        CHECK (amount_vnd >= 0),
    transform_version TEXT NOT NULL
);
~~~

Trong môi trường production, có thể thêm các khóa ngoại/quan hệ tới dimension, bảng snapshot manifest và chính sách lineage phù hợp. **Không** bắt buộc mọi fact phải dùng order_id làm khóa chính; ở bài này chọn như vậy vì grain đích là **một hàng cho mỗi đơn**, và order_id được giả định toàn cục.

Nếu nguồn chỉ đảm bảo order_id duy nhất **trong tenant**, khóa đích phải gồm **(tenant_id, source_order_id)** hoặc định danh nguồn tương ứng. Đặt một PRIMARY KEY không đúng phạm vi có thể khiến hai đơn hợp lệ của hai tenant tranh cùng khóa.

### 5.3. Bảng trạng thái công việc

~~~sql
CREATE TABLE backfill_jobs (
    job_id BIGINT PRIMARY KEY,
    snapshot_id BIGINT NOT NULL,
    transform_version TEXT NOT NULL,
    last_order_id BIGINT NOT NULL DEFAULT 0,
    max_order_id BIGINT NOT NULL,
    batch_count INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL
        CHECK (state IN (
            'RUNNING', 'VERIFYING', 'COMPLETED', 'FAILED'
        )),
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (last_order_id >= 0),
    CHECK (max_order_id >= 0),
    CHECK (last_order_id <= max_order_id),
    CHECK (batch_count >= 0)
);
~~~

Ý nghĩa các trường:

- **snapshot_id:** tập nguồn bất biến mà job được giao.
- **transform_version:** quy tắc tính dữ liệu đích.
- **max_order_id:** giới hạn ID lớn nhất của snapshot lúc tạo job.
- **last_order_id:** **khóa nguồn lớn nhất đã quét và commit**, không nhất thiết là khóa của một hàng đã được INSERT.
- **batch_count:** số batch có ít nhất một hàng nguồn được quét và đã commit.
- **state:** trạng thái vận hành; **COMPLETED** chỉ được đặt sau khi đối soát đạt.

Giá trị khởi tạo **last_order_id = 0** dựa trên giả định mọi order_id dương. Với khóa UUID hay chuỗi, dùng checkpoint là khóa composite hoặc trạng thái riêng thay vì tự phát minh “UUID nhỏ nhất”.

### 5.4. Dữ liệu lịch sử mẫu có lỗ hổng ID và hàng bị loại

~~~sql
INSERT INTO legacy_order_snapshot (
    snapshot_id, order_id, tenant_id,
    placed_at, order_status, total_vnd
) VALUES
    (501, 101, 'T01',
     TIMESTAMPTZ '2026-11-19 23:50:00+07', 'PLACED', 300000),
    (501, 103, 'T01',
     TIMESTAMPTZ '2026-11-20 00:10:00+07', 'PLACED', 200000),
    (501, 105, 'T01',
     TIMESTAMPTZ '2026-11-20 10:00:00+07', 'CANCELLED', 500000),
    (501, 106, 'T02',
     TIMESTAMPTZ '2026-11-20 11:00:00+07', 'PLACED', 400000),
    (501, 110, 'T01',
     TIMESTAMPTZ '2026-11-20 14:00:00+07', 'PLACED', 100000),
    (501, 111, 'T02',
     TIMESTAMPTZ '2026-11-21 09:00:00+07', 'CANCELLED', 800000),
    (501, 114, 'T02',
     TIMESTAMPTZ '2026-11-21 12:00:00+07', 'PLACED', 700000),
    (501, 120, 'T01',
     TIMESTAMPTZ '2026-11-21 15:00:00+07', 'PLACED', 50000),
    (501, 125, 'T02',
     TIMESTAMPTZ '2026-11-21 16:00:00+07', 'PLACED', 150000);
~~~

Snapshot có **9 hàng** với khóa không liên tiếp (101, 103, 105, 106, 110, 111, 114, 120, 125). Chỉ **7 đơn PLACED** thuộc fact mới, tổng giá trị hàng là **1.900.000 VND**.

### 5.5. Chốt phạm vi một lần và khởi tạo job

~~~sql
INSERT INTO backfill_jobs (
    job_id, snapshot_id, transform_version,
    last_order_id, max_order_id, state
)
SELECT
    9001,
    501,
    'order-fact-v2.1',
    0,
    COALESCE(MAX(order_id), 0),
    'RUNNING'
FROM legacy_order_snapshot
WHERE snapshot_id = 501;
~~~

Sau lệnh, **max_order_id = 125**. Số 125 là **high-watermark theo ID trong snapshot đã chốt**, không phải watermark của một stream đang sống. Nếu ngày mai có dữ liệu source ID 130 thì nó không được tự đưa vào job 9001; cần snapshot/job hoặc cơ chế catch-up mới theo quy tắc xác nhận.

## 6. Xử lý một batch bằng keyset pagination và checkpoint nguyên tử

### 6.1. Vì sao không dùng OFFSET trên nguồn sống?

Một cách phân trang thường gặp:

~~~sql
-- Không phù hợp làm checkpoint tin cậy khi nguồn đang thay đổi.
SELECT *
FROM legacy_order_snapshot
WHERE snapshot_id = 501
ORDER BY order_id
LIMIT 3 OFFSET 300000;
~~~

**OFFSET** lớn có thể tốn công duyệt bỏ nhiều hàng. Nếu nguồn bị thêm/xóa trong lúc job đang chạy, vị trí thứ 300.000 có thể dịch chuyển, khiến hàng bị lặp hoặc bị bỏ. Với nguồn snapshot không đổi, OFFSET vẫn có thể dùng về mặt ngữ nghĩa, nhưng **keyset theo khóa ổn định** thường phù hợp hơn để resume và tránh chi phí bỏ qua hàng.

Mẫu keyset:

~~~sql
SELECT *
FROM legacy_order_snapshot
WHERE snapshot_id = 501
  AND order_id > 105
  AND order_id <= 125
ORDER BY order_id
LIMIT 3;
~~~

Kết quả là 106, 110, 111 — không phụ thuộc khoảng trống giữa các ID.

### 6.2. Một transaction cho một batch

Chạy **nguyên khối sau cho mỗi batch**, tổng cộng ba lần trên dữ liệu ví dụ. **Không** chạy câu INSERT riêng rồi commit checkpoint ở transaction khác.

~~~sql
BEGIN;

-- Khóa checkpoint: những worker dùng cùng job_id sẽ chờ nhau.
SELECT
    job_id,
    snapshot_id,
    last_order_id,
    max_order_id,
    state
FROM backfill_jobs
WHERE job_id = 9001
FOR UPDATE;

-- Nếu state không phải RUNNING, application phải dừng batch.
WITH batch AS MATERIALIZED (
    SELECT
        s.snapshot_id,
        s.order_id,
        s.tenant_id,
        s.placed_at,
        s.order_status,
        s.total_vnd
    FROM legacy_order_snapshot AS s
    JOIN backfill_jobs AS j
      ON j.snapshot_id = s.snapshot_id
    WHERE j.job_id = 9001
      AND j.state = 'RUNNING'
      AND s.order_id > j.last_order_id
      AND s.order_id <= j.max_order_id
    ORDER BY s.order_id
    LIMIT 3
),
written AS (
    INSERT INTO reporting_order_fact_v2 (
        source_order_id,
        source_snapshot_id,
        tenant_id,
        local_placed_date,
        amount_vnd,
        transform_version
    )
    SELECT
        order_id,
        snapshot_id,
        tenant_id,
        (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE,
        total_vnd,
        'order-fact-v2.1'
    FROM batch
    WHERE order_status = 'PLACED'
    ON CONFLICT (source_order_id) DO NOTHING
    RETURNING source_order_id
),
batch_stats AS (
    SELECT
        (SELECT COUNT(*) FROM batch) AS source_rows_scanned,
        (SELECT MAX(order_id) FROM batch) AS max_source_id,
        (SELECT COUNT(*) FROM written) AS target_rows_inserted
)
UPDATE backfill_jobs AS j
SET
    last_order_id = COALESCE(
        batch_stats.max_source_id, j.last_order_id
    ),
    batch_count = j.batch_count + CASE
        WHEN batch_stats.source_rows_scanned > 0 THEN 1 ELSE 0
    END,
    updated_at = clock_timestamp()
FROM batch_stats
WHERE j.job_id = 9001
  AND j.state = 'RUNNING'
RETURNING
    j.job_id,
    j.last_order_id,
    j.batch_count,
    batch_stats.source_rows_scanned,
    batch_stats.target_rows_inserted;

COMMIT;
~~~

Trong PostgreSQL, **written** là data-modifying CTE; nó và cập nhật checkpoint thuộc **cùng transaction**. Nếu một thao tác lỗi và transaction bị rollback, **không có tiến độ nào được commit**. Tham chiếu **written** trong **batch_stats** buộc tính số hàng đã ghi trước khi trả trạng thái batch. Thao tác ghi chỉ tạo fact của đơn PLACED, còn **MAX(order_id) lấy từ batch nguồn đầy đủ**.

Lệnh **ON CONFLICT DO NOTHING** chỉ giúp retry không tạo thêm hàng khi khóa đã có. Nó **không xác nhận** hàng đích cũ có giá trị đúng; vì vậy phải có đối soát trường–trường ở mục 9. Trong quy trình production nếu tìm hàng đích sai, cần dừng, ghi lỗi và quyết định sửa/ghi đè có kiểm toán, không dùng DO NOTHING để bỏ qua mọi xung đột.

### 6.3. Tiến độ dự kiến

| Batch đã commit | Khóa nguồn được quét | Đơn PLACED mới ghi | last_order_id | batch_count |
| --- | --- | ---: | ---: | ---: |
| 1 | 101, 103, 105 | 2 | 105 | 1 |
| 2 | 106, 110, 111 | 2 | 111 | 2 |
| 3 | 114, 120, 125 | 3 | 125 | 3 |

Tổng đã quét **9 hàng nguồn**, đã ghi **7 hàng đích**. Hai đơn **105 và 111** bị loại theo quy tắc. Khi **last_order_id = max_order_id = 125**, toàn bộ hàng của snapshot đã được quét; bước tiếp theo là **VERIFYING**, chưa phải COMPLETED.

Đối với snapshot rỗng (max_order_id = 0, last_order_id = 0), job có thể đi thẳng sang VERIFYING nhưng vẫn phải kiểm tra rằng tập nguồn và tập đích tương ứng đều rỗng. Với bộ ID có lỗ hổng, điều kiện đạt max vẫn hợp lệ vì job đã quét theo thứ tự và nguồn không đổi.

### 6.4. Vì sao không ghi checkpoint trước khi commit?

Nếu gọi một API để lưu tiến độ ở hệ thống ngoài rồi DB ghi đích thất bại, checkpoint có thể vượt xa dữ liệu thực tế. Nếu DB đích và checkpoint cùng PostgreSQL, đặt cả hai trong một transaction là cách đơn giản nhất tránh trạng thái lệch. Với engine hỗ trợ transactional batches khác, cần áp dụng tính chất tương đương đã được kiểm chứng.

## 7. Tiếp tục sau khi dừng, crash hoặc đổi worker

Một job có khả năng resume không phải chỉ có cột **last_id**. Nó cần quy định **khi nào checkpoint hợp lệ, khi nào được retry, tiến độ có phụ thuộc phiên bản logic nào và ai được xử lý job**.

### 7.1. Kịch bản crash trước COMMIT

Giả sử batch 2 đang xử lý các khóa 106, 110, 111. Database đã nhận một số câu INSERT, nhưng tiến trình bị dừng trước COMMIT:

~~~text
Checkpoint trước batch: last_order_id = 105.
BEGIN;
  INSERT fact cho 106, 110;
  UPDATE backfill_jobs last_order_id = 111;
  ... ứng dụng crash trước COMMIT.

PostgreSQL rollback transaction chưa commit.

Khi restart:
  last_order_id vẫn = 105;
  dữ liệu batch 2 chưa được commit;
  job chạy lại batch 2 an toàn.
~~~

Đây là lợi ích của **atomic commit** giữa hàng đích và checkpoint. Không cần đoán từ log ứng dụng xem câu lệnh nào đã gửi tới database trước khi mất kết nối.

### 7.2. Kịch bản mất phản hồi sau COMMIT

Ứng dụng gửi COMMIT nhưng mạng bị đứt trước khi nhận kết quả. Nó **không biết chắc** transaction đã commit hay chưa:

~~~text
Nếu COMMIT thành công:
  checkpoint đã tiến và target rows đã ghi.

Nếu COMMIT thất bại/rollback:
  checkpoint chưa tiến và target rows chưa ghi.
~~~

Khi nối lại, worker **đọc checkpoint từ database**, không tiếp tục từ biến last_id còn giữ trong RAM. Nếu checkpoint chưa tiến, chạy lại batch; khóa duy nhất và chính sách idempotent giúp ngăn dữ liệu trùng.

Một nguyên tắc hữu ích:

> Trạng thái chạy thật nằm ở hệ lưu trữ checkpoint đã được commit; log hoặc bộ nhớ của worker chỉ là thông tin hỗ trợ.

### 7.3. Khởi động lại đúng phiên bản nguồn và biến đổi

Worker mới phải kiểm tra:

- **job_id = 9001** và **state = RUNNING**.
- **snapshot_id = 501** vẫn tồn tại, chưa đổi và còn đủ dữ liệu.
- **transform_version = order-fact-v2.1** trùng logic đã dùng các batch trước.
- **max_order_id = 125** vẫn mô tả phạm vi nguồn chốt.
- **last_order_id** lấy từ database, không lấy từ cache.

Nếu một worker mới dùng logic **v2.2** cho phần còn lại trong khi nửa đầu được tạo bởi **v2.1**, cùng một bảng fact có thể chứa **hai cách tính khác nhau** mà báo cáo không hay biết. Phải dừng và lập **job/chính sách migration mới**, hoặc xóa/tái xây toàn bộ tập thuộc quyền sở hữu một cách an toàn sau khi đối soát. Không tự thay transform_version trên job đang chạy.

### 7.4. Tạm dừng và tiếp tục không tương đương hủy

Trong hệ thực tế, có thể cần trạng thái **PAUSED**:

~~~text
PENDING -> RUNNING -> VERIFYING -> COMPLETED
              |
              +-> PAUSED -> RUNNING
              |
              +-> FAILED -> RUNNING sau khi xử lý lỗi
~~~

Lược đồ ví dụ mục 5 cố ý tối giản các trạng thái RUNNING/VERIFYING/COMPLETED/FAILED; muốn hỗ trợ pause nghiệp vụ đầy đủ cần mở rộng CHECK và quy tắc chuyển trạng thái. Đừng tự đặt **state = COMPLETED** chỉ vì job được người vận hành dừng thủ công.

## 8. Idempotency, ghi đồng thời và khóa sở hữu

### 8.1. Idempotency cần đúng theo loại phép biến đổi

| Kiểu ghi | Retry có an toàn không? | Cách bảo vệ |
| --- | --- | --- |
| **INSERT theo source ID duy nhất** | Có thể an toàn | PRIMARY KEY/UNIQUE + đối soát payload khi xung đột |
| **UPSERT giá trị xác định từ snapshot** | Có thể an toàn | Cùng source/version/rule, cập nhật thành cùng giá trị |
| **UPDATE SET normalized_col = f(source_col)** | Có thể an toàn | Hàm f xác định, không phụ thuộc thời gian hiện hành |
| **UPDATE SET balance = balance + x** | **Không tự idempotent** | Event ID/ledger riêng, khử trùng hoặc snapshot-derived set |
| **Gửi email/phát sự kiện ra ngoài** | Không tự an toàn | Outbox, idempotency key, xử lý lặp phía consumer |
| **Cấp lại sequence hoặc random ID mỗi lần retry** | Có thể tạo bản ghi khác | Khóa nguồn–đích ổn định, ràng buộc duy nhất |

Ví dụ không nên làm khi backfill tổng cộng:

~~~sql
-- Phản mẫu: retry có thể cộng thêm một lần nữa.
UPDATE tenant_totals
SET total_vnd = total_vnd + 300000
WHERE tenant_id = 'T01';
~~~

Nếu muốn tái tính tổng từ dữ liệu chuẩn:

~~~sql
-- Mẫu an toàn hơn khi đã xác nhận tập nguồn và cutoff.
UPDATE tenant_totals AS t
SET total_vnd = x.new_total_vnd
FROM (
    SELECT tenant_id, SUM(amount_vnd) AS new_total_vnd
    FROM reporting_order_fact_v2
    GROUP BY tenant_id
) AS x
WHERE t.tenant_id = x.tenant_id;
~~~

Đoạn này **chỉ cập nhật tenant đã có trong cả hai tập** và chưa tạo hàng cho tenant mới hay đặt về 0 khi không còn fact. Production cần định nghĩa đủ các trường hợp thiếu group, source version và quyền sở hữu bảng tổng. Điểm chính là **SET bằng giá trị xác định**, không cộng dồn mỗi lần retry.

### 8.2. ON CONFLICT DO NOTHING không phải giấy phép bỏ qua sai lệch

Giả sử **source_order_id = 103** đã tồn tại ở đích, nhưng amount_vnd bị ghi nhầm 250000 thay vì 200000. Lệnh INSERT ... ON CONFLICT DO NOTHING sẽ không tạo lỗi và không sửa giá trị. Nếu chỉ đếm số hàng, báo cáo vẫn thấy đủ 7 đơn và có thể tưởng job thành công.

Vì vậy cần:

- Khóa duy nhất chặn tạo hai hàng đích cho cùng source ID.
- Chính sách **conflict != silent success**: ghi metric/log số conflict và kiểm tra sự tương đương.
- Đối soát **tập khóa và giá trị** trước khi publish.
- Quy trình xử lý dữ liệu sai có kiểm toán, thay vì âm thầm ghi đè dữ liệu người khác đã sửa.

Với source immutable và transform deterministic, một UPSERT có điều kiện **IS DISTINCT FROM** có thể dùng để sửa dữ liệu đích, nhưng phải xác nhận job **sở hữu quyền ghi** toàn bộ các hàng ấy và mọi thay đổi được ghi log. Ví dụ này dùng DO NOTHING để minh họa retry đơn giản và dùng đối soát phát hiện sai.

### 8.3. Nhiều worker cùng một job

Đoạn SQL mục 6 dùng:

~~~sql
SELECT ...
FROM backfill_jobs
WHERE job_id = 9001
FOR UPDATE;
~~~

Khóa hàng checkpoint làm hai worker cùng job **tuần tự hóa việc lấy và nâng last_order_id**, miễn là **mọi worker tuân thủ cùng giao thức transaction**. Đây không phải cách mở rộng thông lượng bằng 10 worker chạy cùng một checkpoint, vì các worker sẽ chờ nhau.

Nếu muốn xử lý song song, có thể phân công **những dải khóa không chồng lấn** hoặc đơn vị công việc độc lập:

~~~text
job_id 9001, shard A: order_id 1..100000
job_id 9002, shard B: order_id 100001..200000
job_id 9003, shard C: order_id 200001..300000
~~~

Mỗi dải có checkpoint riêng; thiết kế phải đảm bảo các dải **bao phủ đủ và không chồng nhau**, cùng snapshot và cùng transform version, đồng thời không để các job phá vỡ invariant dùng chung. Với bảng nguồn partitioned theo tenant, có thể chia theo tenant/range nhưng phải đánh giá whale tenant và chi phí truy vấn.

### 8.4. Lease/fencing khi worker chạy ngoài transaction

Trong hệ phân tán, một worker có thể giữ job nhiều phút và lỗi mạng khiến hệ điều phối gán lại cho worker khác. Chỉ có **lease hết hạn** không đủ để ngăn worker cũ còn chạy tiếp. Có thể dùng:

- **owner_id** và **lease_until** cho việc nhận job.
- **fencing_token/epoch tăng đơn điệu** mỗi lần đổi chủ, để phía ghi từ chối worker dùng phiên bản cũ.
- **Checkpoint và trạng thái batch** được lưu ở database với điều kiện cập nhật theo epoch/version.
- **Idempotency ở đích** như tuyến bảo vệ cuối.

Đây là cơ chế phù hợp khi cần nhiều worker hoặc đích ở hệ khác. Ví dụ PostgreSQL một job trong bài không cần tự thêm lease vì một transaction và khóa hàng là đủ cho kịch bản đơn giản; không nên tạo nhiều thành phần phân tán khi chưa có nhu cầu.

### 8.5. Các ranh giới transaction khi backfill nhiều bảng

Nếu một bản ghi source tạo ra cả **order_v2**, **order_lines_v2** và **order_address_snapshot_v2**, phải xác định:

- Những hàng nào cần xuất hiện **nguyên tử cùng nhau**?
- Khóa ngoại cần được duy trì thế nào trong quá trình batch?
- Nếu lỗi khi ghi bảng con, checkpoint được rollback cùng các bảng khác không?
- Nếu các bảng ở hai database khác nhau, phương án idempotent/compensation ra sao?

Không tự xem việc ghi một bảng thành công là hoàn tất một source ID nếu các bảng còn lại bắt buộc phải đúng cùng thời điểm. Có thể cần staging, batch manifest và transaction trên từng đơn/aggregate hoặc trên một nhóm hàng có liên quan.

## 9. Đối soát (reconciliation): đủ hàng, đúng khóa, đúng giá trị

Checkpoint **đã tới cuối** chỉ cho biết job đã quét phạm vi nguồn theo giả định snapshot cố định. Nó **không chứng minh** kết quả đúng. Cần đối soát **ít nhất ba tầng**:

1. **Tập khóa:** mọi hàng nguồn đủ điều kiện có đích, không có hàng đích thừa.
2. **Giá trị:** thuộc tính đã biến đổi đúng với từng record nguồn.
3. **Tổng hợp:** số hàng/số tiền theo tenant, ngày, trạng thái và trên toàn phạm vi khớp.

### 9.1. Đưa job sang VERIFYING, chưa đánh dấu hoàn tất

Sau khi chạy ba batch mục 6 và thấy checkpoint đạt 125:

~~~sql
UPDATE backfill_jobs
SET state = 'VERIFYING',
    updated_at = clock_timestamp()
WHERE job_id = 9001
  AND state = 'RUNNING'
  AND last_order_id = max_order_id
RETURNING job_id, snapshot_id, last_order_id, state;
~~~

Nếu không có hàng trả về, điều kiện chuyển trạng thái chưa đạt. Không suy đoán “không còn gì cần làm” từ một log batch rỗng khi source vẫn có thể có hàng bị bỏ qua do bộ lọc hoặc checkpoint sai.

### 9.2. Đối soát từng khóa và giá trị bằng FULL OUTER JOIN

Truy vấn dưới đây tính **tập nguồn kỳ vọng** bằng đúng phiên bản quy tắc v2.1, so với các hàng đích thuộc snapshot 501:

~~~sql
WITH expected AS (
    SELECT
        order_id,
        tenant_id,
        (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
            AS local_placed_date,
        total_vnd AS amount_vnd
    FROM legacy_order_snapshot
    WHERE snapshot_id = 501
      AND order_status = 'PLACED'
),
actual AS (
    SELECT
        source_order_id,
        tenant_id,
        local_placed_date,
        amount_vnd,
        transform_version
    FROM reporting_order_fact_v2
    WHERE source_snapshot_id = 501
)
SELECT
    COALESCE(e.order_id, a.source_order_id) AS order_id,
    CASE
        WHEN e.order_id IS NULL THEN 'EXTRA_TARGET'
        WHEN a.source_order_id IS NULL THEN 'MISSING_TARGET'
        ELSE 'VALUE_MISMATCH'
    END AS discrepancy_type,
    e.tenant_id AS expected_tenant,
    a.tenant_id AS actual_tenant,
    e.local_placed_date AS expected_date,
    a.local_placed_date AS actual_date,
    e.amount_vnd AS expected_amount,
    a.amount_vnd AS actual_amount,
    a.transform_version
FROM expected AS e
FULL OUTER JOIN actual AS a
  ON a.source_order_id = e.order_id
WHERE e.order_id IS NULL
   OR a.source_order_id IS NULL
   OR e.tenant_id IS DISTINCT FROM a.tenant_id
   OR e.local_placed_date IS DISTINCT FROM a.local_placed_date
   OR e.amount_vnd IS DISTINCT FROM a.amount_vnd
   OR a.transform_version IS DISTINCT FROM 'order-fact-v2.1'
ORDER BY order_id;
~~~

**Kết quả mong đợi: không có hàng nào.**

Lợi ích của **FULL OUTER JOIN**:

- **MISSING_TARGET:** đơn PLACED có ở nguồn nhưng không có fact tương ứng.
- **EXTRA_TARGET:** fact không thuộc tập đơn PLACED của snapshot 501, ví dụ đơn CANCELLED bị nạp nhầm.
- **VALUE_MISMATCH:** khóa có ở hai nơi nhưng sai tenant, ngày, tiền hoặc version.

Dùng **IS DISTINCT FROM** thay cho so sánh khác bằng dấu **<>** để xử lý NULL một cách tường minh. Các trường quan trọng của ví dụ đều NOT NULL; trong hệ rộng hơn, cách này giúp không để NULL che lỗi so sánh.

**Một giới hạn cần nói rõ:** nếu bảng đích chứa dữ liệu hợp lệ của những snapshot/job khác, phải cô lập đúng phạm vi bằng **source_snapshot_id/job scope**. Không so mọi hàng của một bảng dùng chung với một snapshot nhỏ rồi kết luận các hàng của tenant khác là “thừa”.

### 9.3. Đối soát tổng hợp theo tenant và ngày

Một lỗi có thể bị bỏ sót nếu chỉ xem tổng tiền toàn hệ thống: đơn T01 bị gán nhầm sang T02 nhưng tổng chung vẫn bằng nhau. Vì vậy cần đối soát **theo grain báo cáo**.

~~~sql
WITH expected AS (
    SELECT
        tenant_id,
        (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
            AS report_date,
        COUNT(*) AS order_count,
        SUM(total_vnd) AS amount_vnd
    FROM legacy_order_snapshot
    WHERE snapshot_id = 501
      AND order_status = 'PLACED'
    GROUP BY
        tenant_id,
        (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
),
actual AS (
    SELECT
        tenant_id,
        local_placed_date AS report_date,
        COUNT(*) AS order_count,
        SUM(amount_vnd) AS amount_vnd
    FROM reporting_order_fact_v2
    WHERE source_snapshot_id = 501
    GROUP BY tenant_id, local_placed_date
)
SELECT
    COALESCE(e.tenant_id, a.tenant_id) AS tenant_id,
    COALESCE(e.report_date, a.report_date) AS report_date,
    e.order_count AS expected_count,
    a.order_count AS actual_count,
    e.amount_vnd AS expected_amount,
    a.amount_vnd AS actual_amount
FROM expected AS e
FULL OUTER JOIN actual AS a
  ON a.tenant_id = e.tenant_id
 AND a.report_date = e.report_date
WHERE e.tenant_id IS NULL
   OR a.tenant_id IS NULL
   OR e.order_count IS DISTINCT FROM a.order_count
   OR e.amount_vnd IS DISTINCT FROM a.amount_vnd
ORDER BY tenant_id, report_date;
~~~

Truy vấn cũng **phải rỗng** trên dữ liệu mẫu.

Kết quả tổng hợp dự kiến:

| tenant | Ngày địa phương | Số đơn PLACED | Tổng tiền hàng (VND) |
| --- | --- | ---: | ---: |
| T01 | 2026-11-19 | 1 | 300.000 |
| T01 | 2026-11-20 | 2 | 300.000 |
| T01 | 2026-11-21 | 1 | 50.000 |
| T02 | 2026-11-20 | 1 | 400.000 |
| T02 | 2026-11-21 | 2 | 850.000 |
| **Tổng** | | **7** | **1.900.000** |

Một phép cộng toàn cục dễ kiểm tra:

~~~sql
SELECT
    COUNT(*) AS fact_rows,
    SUM(amount_vnd) AS total_vnd
FROM reporting_order_fact_v2
WHERE source_snapshot_id = 501;
-- 7 hàng, 1900000 VND.
~~~

**Số hàng bằng và tổng tiền bằng vẫn chưa đủ.** Hai hàng có thể bị tráo giá trị hoặc một sai lệch dương được bù bởi sai lệch âm. Đối soát từng khóa/trường ở mục 9.2 là bước không thể bỏ chỉ vì tổng khớp.

### 9.4. Checksum, hash và sampling có vai trò nào?

Với hàng tỷ record, full comparison có thể tốn kém. Có thể sử dụng:

- **Count và sum** theo partition/tenant/ngày làm tín hiệu ban đầu.
- **Min/max ID và mốc ngày** phát hiện phạm vi bị thiếu.
- **Hash/checksum theo bucket** hỗ trợ khoanh vùng nơi có khác biệt.
- **Sampling có chủ đích** để kiểm tra timezone, NULL, encoding, định danh đặc biệt.
- **Anti-join theo khóa** và so sánh trường khi phát hiện bucket nghi vấn.

Nhưng checksum có thể va chạm, khác biệt canonicalization hoặc bỏ qua metadata quan trọng. **Sampling không chứng minh không có lỗi**, còn count/sum có thể bằng nhau dù các hàng sai. Với báo cáo đòi hỏi độ đúng cao, cần quy trình đối soát mạnh hơn hoặc bằng chứng đầu vào bất biến được kiểm chứng.

### 9.5. Chỉ đánh dấu COMPLETED sau khi đối soát đạt

Sau khi chạy các kiểm tra và xác nhận không có sai lệch, job có thể chuyển sang **COMPLETED**. Để không chỉ dựa vào lời xác nhận thủ công, có thể dùng một câu lệnh kiểm tra tính tương đương của tập hàng theo quy tắc mẫu trước khi chuyển trạng thái:

~~~sql
BEGIN;

WITH expected AS (
    SELECT
        order_id,
        tenant_id,
        (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
            AS local_placed_date,
        total_vnd AS amount_vnd
    FROM legacy_order_snapshot
    WHERE snapshot_id = 501
      AND order_status = 'PLACED'
),
actual AS (
    SELECT
        source_order_id,
        tenant_id,
        local_placed_date,
        amount_vnd,
        transform_version
    FROM reporting_order_fact_v2
    WHERE source_snapshot_id = 501
),
discrepancies AS (
    SELECT 1 AS problem
    FROM expected AS e
    FULL OUTER JOIN actual AS a
      ON a.source_order_id = e.order_id
    WHERE e.order_id IS NULL
       OR a.source_order_id IS NULL
       OR e.tenant_id IS DISTINCT FROM a.tenant_id
       OR e.local_placed_date IS DISTINCT FROM a.local_placed_date
       OR e.amount_vnd IS DISTINCT FROM a.amount_vnd
       OR a.transform_version IS DISTINCT FROM 'order-fact-v2.1'
)
UPDATE backfill_jobs
SET state = 'COMPLETED',
    updated_at = clock_timestamp()
WHERE job_id = 9001
  AND state = 'VERIFYING'
  AND last_order_id = max_order_id
  AND NOT EXISTS (SELECT 1 FROM discrepancies)
RETURNING job_id, state, last_order_id, max_order_id;

COMMIT;
~~~

**Nếu trả về 0 hàng thì chưa được công bố hoàn thành.** Câu lệnh này kiểm tra dữ liệu bảng mẫu trong một transaction; nó **không** kiểm tra nguồn đã thực sự immutable, không chứng minh code nghiệp vụ đúng, không xác minh những downstream consumer khác, và không thay thế quy trình phê duyệt cutover. Trong hệ thật cần lưu kết quả đối soát theo **job_id, phiên bản rule, thời điểm chạy và bộ metric** để kiểm toán.

### 9.6. Đừng nhầm COMPLETED với đã chuyển ứng dụng sang dữ liệu mới

Trạng thái **COMPLETED** ở ví dụ nghĩa là phần backfill snapshot được quét và đối soát. Nếu nguồn vận hành còn ghi mới, vẫn cần **catch-up**. Nếu người dùng còn đọc bảng cũ, vẫn cần **cutover và giám sát**. Nếu các consumer cũ chưa được nâng cấp, vẫn chưa thể xóa schema cũ.

Trong hệ lớn, trạng thái backfill và trạng thái triển khai có thể là **hai state machine khác nhau**, tránh dùng một cột status cho mọi giai đoạn.

## 10. Khi dữ liệu nguồn bị sửa: phân biệt hiệu chỉnh và replay

### 10.1. Từ snapshot bất biến sang nguồn có revision

Snapshot 501 được giả định không đổi. Nhưng khi đọc trực tiếp từ bảng **orders** đang hoạt động, có thể xảy ra:

~~~text
10:00  Backfill đọc order 103: total = 200000.
10:01  Ứng dụng sửa order 103: total = 250000.
10:02  Backfill đã tiến checkpoint qua order 103.
10:03  Đọc bảng đích thấy total = 200000, nguồn hiện hành = 250000.
~~~

**Chạy tiếp từ ID > 103 không bao giờ tự sửa hàng 103.** Vì vậy checkpoint theo ID chỉ là **tiến độ quét**, không phải cơ chế theo dõi cập nhật của nguồn mutable.

Ba hướng thiết kế:

1. **Nguồn được snapshot/đóng băng:** mọi batch đọc cùng phiên bản, ghi nhận đây là dữ liệu **as-of snapshot**; sau đó có catch-up riêng.
2. **Nguồn có lịch sử revision:** chọn đúng revision theo cutoff, sau đó xử lý revision mới như correction được ghi rõ.
3. **Change stream/CDC:** bắt đầu thu thay đổi trước hoặc cùng thời điểm snapshot, sau khi backfill bắt kịp tới một checkpoint nguồn được xác nhận.

Không đủ chỉ thêm **updated_at** rồi quét những hàng có updated_at lớn: đồng hồ ứng dụng có thể lệch, nhiều sửa trùng timestamp, việc xóa cứng không còn hàng để quét, và bản ghi có thể thay đổi nhiều lần giữa hai vòng. Một cơ chế version/commit position ổn định thường đáng tin hơn.

### 10.2. Một row hiện hành khác một sự kiện tài chính

Nếu bảng nguồn hiện hành có **order_status** thay từ PLACED thành CANCELLED, cần trả lời:

- Fact đích biểu diễn **“đơn từng được đặt”** (sự kiện bất biến), hay **“các đơn hiện đang PLACED”** (snapshot trạng thái)?
- Việc CANCELLED tạo **sự kiện điều chỉnh** hay xóa hàng đích khỏi tập?
- Có cần bảo toàn lịch sử tại thời điểm đơn đã đặt không?
- Chỉ số báo cáo dùng ngày đặt, ngày hủy hay ngày cập nhật?

Không thể chỉ đổi từ INSERT sang UPSERT rồi cho rằng đúng nghiệp vụ. Với sự kiện “đơn đã được đặt”, lịch sử có thể cần giữ cả sự kiện hủy riêng. Với snapshot “đơn đang PLACED”, revision mới có thể yêu cầu **xóa/đánh dấu inactive** trong bảng dẫn xuất. **Grain và ngữ nghĩa thời gian quyết định hành vi correction.**

### 10.3. Áp dụng sửa đổi theo đúng thứ tự

Giả sử hai thông điệp về order 103 tới consumer theo thứ tự đảo:

~~~text
order 103 @ version 8 -> total = 250000 (đến trước)
order 103 @ version 7 -> total = 200000 (đến sau do retry)
~~~

Nếu consumer luôn ghi đè bằng thông điệp đến sau, bản mới bị thay bằng bản cũ. Nên lưu **source_version/sequence** và chỉ chấp nhận thay đổi khi phiên bản mới hơn phiên bản đang giữ, hoặc xử lý theo giao thức nguồn bảo đảm thứ tự.

Ví dụ pattern điều kiện:

~~~sql
-- Ví dụ giản lược khi bảng đích có source_version.
INSERT INTO order_projection (order_id, source_version, amount_vnd)
VALUES (103, 8, 250000)
ON CONFLICT (order_id)
DO UPDATE SET
    source_version = EXCLUDED.source_version,
    amount_vnd = EXCLUDED.amount_vnd
WHERE order_projection.source_version < EXCLUDED.source_version;
~~~

**Đoạn này giả định** bảng **order_projection** đã được tạo với ba cột tương ứng, và nguồn cam kết version tăng trong phạm vi order. Đây là pattern riêng cho nguồn mutable, **không phải phần DDL thực thi liền mạch** của ví dụ snapshot ở mục 5–9.

Nếu có cùng source_version nhưng payload khác nhau, cần coi là **xung đột dữ liệu nguồn** và điều tra; không tùy ý lấy bản cuối cùng. Với tombstone/delete, cần bảo vệ thứ tự và chính sách xóa tương đương.

## 11. Nguồn vẫn ghi mới: snapshot + CDC + catch-up trước cutover

Backfill lịch sử trên một snapshot đã chốt giải quyết **phần quá khứ**. Với ứng dụng không thể ngừng ghi, cần thêm cơ chế đưa **những thay đổi xảy ra trong lúc backfill** vào mô hình mới.

### 11.1. Hai vấn đề khác nhau cần giải đồng thời

**Vấn đề A — phạm vi dữ liệu cũ:** backfill có tái tạo đúng toàn bộ dữ liệu ở một mốc snapshot không?

**Vấn đề B — biến động sau mốc:** trong lúc chạy backfill, ứng dụng liên tục INSERT/UPDATE/DELETE; mô hình mới có nhận và áp dụng đúng các biến động ấy không?

Chỉ hoàn thành A không đủ để chuyển API sang đọc bảng mới như nguồn hiện hành. Ngược lại, chỉ subscribe CDC từ bây giờ không bổ sung các hàng đã tồn tại từ trước.

### 11.2. Dòng thời gian chuẩn tắc

~~~mermaid
sequenceDiagram
    participant S as Source DB
    participant C as CDC / change stream
    participant B as Backfill worker
    participant T as Target V2
    participant R as Read routing
    S->>C: Đặt checkpoint/khởi động capture
    S-->>B: Snapshot nhất quán ở mốc S0
    B->>T: Backfill các hàng trong S0 theo batch
    S->>C: Các thay đổi sau S0
    B->>T: Hoàn tất backfill, đối soát snapshot
    C->>T: Catch-up thay đổi theo source version
    T-->>R: Báo đã đối soát và đạt checkpoint S1
    R->>T: Cutover reads sang V2
    C->>T: Tiếp tục đồng bộ thay đổi mới
~~~

Sơ đồ là **một kiến trúc logic**, không phải câu lệnh cấu hình CDC cụ thể. Tùy database và công cụ, cách kết hợp snapshot với log position khác nhau. Tính đúng nằm ở việc **không có khoảng trống giữa snapshot S0 và change stream**, không có nguồn sự thật kép vô thời hạn, và thứ tự/version được áp dụng đúng.

### 11.3. Bất biến cho giai đoạn bắt kịp

Đặt:

~~~text
S0 = snapshot nguồn tại thời điểm/vị trí log đã xác định
L0 = vị trí log tương ứng với S0
L1 = vị trí log đã xử lý và xác nhận ở target

Target V2 sau catch-up đến L1 phải tương đương
với trạng thái nguồn sau khi áp dụng mọi thay đổi
từ snapshot S0 tới vị trí L1,
theo hợp đồng dữ liệu đã chọn.
~~~

Với nhiều nguồn độc lập, một **L1 duy nhất** có thể không tồn tại; phải giữ checkpoint/watermark **cho từng nguồn** và quy tắc khi nào có thể coi kết quả phân tích đủ điều kiện công bố.

### 11.4. Vì sao MAX(id) trên nguồn đang sống không đủ?

Một lỗi đặc biệt khó phát hiện:

~~~text
T1: Transaction A lấy nextval() = 100.
T2: Transaction B lấy nextval() = 101, commit.
T3: Backfill thấy MAX(id) = 101, quét đến 101.
T4: Transaction A mới commit bản ghi id = 100.
T5: Job đã checkpoint last_id = 101, không quét lại <=101.
=> id=100 bị bỏ sót.
~~~

**ID tăng không bảo đảm commit theo ID tăng.** Điều này đúng ngay cả khi sequence của một database tạo số tăng. Nếu muốn dùng watermark theo ID, cần các tiền điều kiện mạnh hơn (nguồn thực sự đóng băng, snapshot nhất quán kết hợp capture, hoặc thuật toán đặc biệt đã được chứng minh), không chỉ nhìn MAX(id).

### 11.5. Dual-write không phải giải pháp tự động nhất quán

Đôi khi ứng dụng được sửa để ghi cả bảng cũ và bảng mới:

~~~text
write old -> write new
~~~

Nếu hai ghi ở cùng database và cùng transaction, tính nguyên tử có thể bảo vệ được một số bất biến. Nếu chúng thuộc hai database hoặc hai service độc lập, **ghi cũ thành công nhưng ghi mới thất bại** có thể gây lệch; retry còn có thể nhân bản event.

Giải pháp có thể là **transactional outbox, CDC, change log có thứ tự và consumer idempotent**, hoặc cơ chế migration được thiết kế riêng. Không gọi thao tác hai lần là **exactly-once** chỉ vì nó dùng cùng một request ID.

### 11.6. Điều kiện cutover thực tế

Một chiến lược an toàn thường yêu cầu:

- Backfill snapshot S0 hoàn tất và đối soát đúng.
- Consumer thay đổi từ S0 đã bắt kịp tới checkpoint/mốc nguồn S1 được chấp nhận.
- Nợ xử lý **quarantine**, retry và bản ghi lỗi đã được giải quyết hoặc có phê duyệt rõ.
- Kết quả truy vấn mẫu/shadow read giữa nguồn cũ và V2 tương đương theo định nghĩa.
- Các ràng buộc, chỉ mục và SLO của đường đọc mới đã được đo.
- Routing/feature flag có cách rollback, không xóa nguồn cũ ngay.
- Có cách phát hiện và sửa sai lệch tiếp tục xuất hiện sau cutover.

**Lag bằng 0 tại một thời điểm** chưa chắc đủ nếu consumer có thể mất sự kiện hoặc checkpoint lưu sai. Cần đối soát khóa/version và giám sát lâu dài.

## 12. Backfill khi dữ liệu đích không còn một–một

Ví dụ chính dùng một hàng source PLACED → một fact. Nhưng nhiều migration quan trọng có grain khác:

### 12.1. Một nguồn tạo nhiều hàng đích

Từ một order chứa nhiều địa chỉ lịch sử, ta có thể chuyển thành:

~~~text
legacy_orders(order_id, shipping_address_json)
    ->
order_addresses(order_id, address_kind, version, ...)
~~~

Checkpoint phải tiến theo **order_id đã xử lý đầy đủ**. Nếu order 103 tạo ra ba hàng địa chỉ mà mới ghi hai hàng thì không được checkpoint 103 là hoàn tất. Khóa đích như **(order_id, address_kind, version)** phải xác định, không cấp lại ngẫu nhiên khi retry.

### 12.2. Nhiều nguồn tạo một hàng tổng hợp

Ví dụ bảng doanh số ngày có grain **(tenant_id, day)**. Một batch quét đơn 101–103 và cộng vào tổng, batch sau quét 105–106 rồi cộng tiếp. Nếu retry batch đầu bằng phép **total = total + batch_sum**, bảng tổng sẽ bị cộng đúp trừ khi có **ledger batch đóng góp** và idempotency key.

Cách thường dễ đối soát hơn:

1. Backfill vào **bảng fact chi tiết** theo source ID duy nhất.
2. Tính bảng tổng hợp bằng **GROUP BY từ tập fact đã xác minh**, hoặc ghi contribution per batch có khóa chống trùng.
3. Chỉ publish tổng hợp khi tập nguồn đủ điều kiện đã hoàn tất hoặc ghi rõ phiên bản tạm thời.

### 12.3. Dimension SCD Type 2 và khoảng hiệu lực

Nếu phải gán các giao dịch lịch sử cho đúng phiên bản **customer dimension** có hiệu lực khi giao dịch xảy ra, không được JOIN chỉ bằng customer_id với mọi phiên bản dimension. Cần xác định:

~~~text
customer_id = business key của khách hàng
placed_at = thời điểm cần ánh xạ
dim_customer.valid_from <= placed_at < valid_to
~~~

trong đó dấu kết thúc không bao gồm **valid_to** là một quy ước phải được thống nhất. Khi cần, dimension phải ngăn **khoảng hiệu lực chồng nhau** cho cùng khóa nghiệp vụ; nếu không một fact có thể JOIN ra hai phiên bản và bị nhân hàng.

Ngoài việc thêm cột surrogate key, backfill còn có thể cần **quy tắc xử lý late-arriving dimension** và snapshot của bảng tham chiếu. Dữ liệu dimension hiện hành không tự thể hiện sự thật lịch sử của ngày đặt.

### 12.4. Chuyển định dạng nhưng giữ nguyên ý nghĩa miền

Các thao tác như:

- Đổi timezone.
- Chuẩn hóa số điện thoại.
- Tách tên/địa chỉ.
- Chuyển tiền từ đơn vị đồng sang đơn vị nhỏ hơn.
- Chuyển JSON thuộc tính sang bảng quan hệ.

cần một **hợp đồng biến đổi**, nhất là với giá trị thiếu, nhập sai, encoding, khoảng thời gian và các ngoại lệ. Không ép dữ liệu lịch sử vào định dạng mới bằng một giá trị giả làm sai ý nghĩa. Ví dụ không biến **địa chỉ cũ không biết quận** thành **quận mặc định** rồi coi như đã xác nhận.

## 13. Chia batch và kiểm soát tài nguyên của cơ sở dữ liệu

Một lệnh UPDATE/INSERT trên hàng trăm triệu record trong một transaction có thể gây **WAL lớn, replication lag, thời gian giữ khóa dài, bloat và khó rollback**. Chia batch giúp kiểm soát, nhưng batch quá nhỏ cũng tăng chi phí commit và vòng lặp.

### 13.1. Chọn batch size theo số đo

Trong ví dụ dùng **LIMIT 3** để dễ quan sát. Production có thể dùng hàng nghìn hoặc nhiều hơn, nhưng không có “con số batch size chuẩn” áp dụng mọi schema.

Đo ít nhất:

| Chỉ số | Mục đích |
| --- | --- |
| **Batch duration** (p50/p95/p99) | Tìm lô bất thường, cân đối thời gian giữ khóa |
| **Source rows scanned/second** | Tốc độ thực quét lịch sử |
| **Target rows written/second** | Tốc độ điền dữ liệu thật, khác số quét nếu có lọc |
| **WAL bytes / replication lag** | Tránh làm chậm replica và tăng chi phí lưu log |
| **CPU, IOPS, network, disk free** | Bảo đảm backfill không làm nghẽn hệ thống phục vụ |
| **Lock wait, deadlock, timeout** | Phát hiện xung đột với ứng dụng |
| **Index maintenance, vacuum pressure** | Đánh giá tác động của ghi lớn lên lược đồ vật lý |
| **Backlog và estimated remaining** | Lập kế hoạch cutover, không dùng estimate như cam kết tuyệt đối |

Kỹ thuật phổ biến là điều chỉnh batch size hoặc số worker **theo áp lực hệ thống**, chứ không cố chạy hết tốc độ vào giờ cao điểm. Nếu p99 của ứng dụng tăng hoặc replica lag vượt ngưỡng đã thống nhất, cần giảm tốc hoặc tạm dừng có kiểm soát.

### 13.2. Mỗi batch ngắn, commit thường xuyên, nhưng không bỏ tính nguyên tử

Một batch transaction thường làm:

~~~text
BEGIN
  lock/read checkpoint
  read limited source rows
  transform + write target rows
  advance checkpoint to max scanned source key
COMMIT
~~~

**Transaction chỉ bao một batch**, không bao toàn bộ nhiều ngày chạy. Điều này giảm lượng thay đổi cần rollback nếu một batch lỗi. Nhưng đối với một record tạo ra nhiều hàng cần xuất hiện nguyên tử, batch phải đảm bảo **mọi hàng liên quan và checkpoint cùng commit**.

Trong PostgreSQL, có thể đặt giới hạn an toàn **lock_timeout/statement_timeout** và retry với backoff ở lớp điều phối. Đừng retry vô hạn cùng một dữ liệu lỗi: cần phân biệt deadlock/timeout có thể retry với lỗi dữ liệu bất biến cần quarantine hoặc sửa quy tắc.

### 13.3. Chỉ mục theo đường đọc của backfill

Source mẫu có:

~~~sql
PRIMARY KEY (snapshot_id, order_id)
~~~

thường hỗ trợ tốt truy vấn:

~~~sql
WHERE snapshot_id = 501
  AND order_id > :last_order_id
ORDER BY order_id
LIMIT :batch_size
~~~

vì khóa chỉ mục bắt đầu bằng snapshot_id rồi tới order_id. Nếu bảng thực tế khác, hãy xem **EXPLAIN**, thống kê và tình trạng index để tránh mỗi batch phải full scan.

Khi thiết kế chỉ mục mới cho bảng rất lớn:

- Cân nhắc chi phí tạo index, dung lượng và tải ghi tăng trong thời gian backfill.
- Một số hệ cho phép xây index **concurrently/online** với ràng buộc riêng; ví dụ PostgreSQL **CREATE INDEX CONCURRENTLY không chạy trong transaction block thông thường**.
- Các ràng buộc **UNIQUE/FK/NOT NULL** cần thứ tự triển khai phù hợp để không khóa ứng dụng quá lâu.
- Không loại bỏ chỉ mục cần cho truy vấn sản xuất chỉ để batch chạy nhanh hơn mà thiếu kế hoạch thay thế.

### 13.4. Partition và phạm vi xử lý

Nếu dữ liệu trải theo tháng, tenant hoặc shard, có thể chia job theo **partition hoặc dải khóa riêng**:

~~~text
run snapshot 501:
  partition 2025-01 -> own checkpoint
  partition 2025-02 -> own checkpoint
  ...
  partition 2026-11 -> own checkpoint
~~~

Mỗi partition cần đối soát riêng và báo cáo tổng bao phủ; không nên chỉ đánh dấu job toàn cục hoàn tất khi mới có một partition thành công. Với dữ liệu có **whale tenant**, chia đều theo số tenant không đảm bảo thời gian chạy đều — cần đo số hàng và mức nặng của từng phần.

Khi backfill trên **nhiều shard**, ràng buộc duy nhất và FK có thể không được kiểm tra toàn cục theo cùng cách một PostgreSQL instance. Mỗi shard có checkpoint riêng, nhưng tổng toàn hệ thống vẫn phải có **manifest phạm vi và đối soát dữ liệu không chồng/không thiếu**.

### 13.5. Thời gian tính toán có thể làm sai kết quả hơn vấn đề tốc độ

Nếu mỗi batch gọi **CURRENT_DATE** để suy “ngày hiện tại” hoặc tra bảng giá **hiện hành** mà không cố định version, cùng một bản ghi có thể cho kết quả khác sau khi job restart. Với backfill lịch sử, các biến đổi quan trọng phải dựa vào:

- Timestamp nghiệp vụ **của record**.
- Timezone và chính sách làm tròn đã chốt.
- Snapshot/version của dimension, tỷ giá và dữ liệu tham chiếu.
- Phiên bản thuật toán, cấu hình và hợp đồng đầu vào.

**Tăng tốc job không thể bù cho việc tính sai ngữ nghĩa thời gian.**

## 14. Quan sát và xử lý lỗi theo từng trạng thái

### 14.1. Những trường nên hiển thị trên dashboard backfill

~~~text
job_id
snapshot_id / source_manifest_id
transform_version / code digest
state
last_committed_source_key / high_watermark
source_rows_scanned
target_rows_inserted
target_rows_skipped_on_conflict
batch_count
failed_batch_count
batch_duration_p95
source/target errors + quarantine count
last_commit_at
reconciliation_status / diff_count
change_stream_lag (nếu có CDC)
published_version (nếu đã cutover)
~~~

**Đừng coi estimated percentage = last_id / max_id** là tỷ lệ chính xác nếu ID có nhiều lỗ hổng hoặc phân bố dồn. Trong mẫu, last_id 111 không nói đã xử lý 111/125 số đơn; thực tế mới quét 6/9 hàng. Muốn tỷ lệ theo số hàng, cần **source count manifest** hoặc số hàng đã quét tích lũy đáng tin cậy.

Một phần trăm tiến độ 100% cũng chỉ chứng minh **quét tới cuối**, không chứng minh **đối soát thành công**.

### 14.2. Ma trận lỗi và hành động

| Tình huống | Tác động | Hành động phù hợp |
| --- | --- | --- |
| Worker crash trước COMMIT | Batch chưa được commit | Đọc checkpoint từ DB, chạy lại |
| Mất mạng sau khi gửi COMMIT | Không biết commit thành công chưa | Reconnect, đọc checkpoint/target; không đoán |
| Duplicate source ID với payload khác | Nguồn không nhất quán | Quarantine, báo source owner, không chọn ngẫu nhiên |
| Target đã có khóa nhưng giá trị khác | Idempotency key đúng, payload sai | Dừng/đối soát, xác định quyền sở hữu và cách sửa |
| Batch chỉ có hàng bị filter | Không INSERT hàng đích | Vẫn tiến checkpoint theo hàng nguồn đã quét |
| Một hàng có giá trị không thể chuyển đổi | Batch lỗi hoặc hàng bị loại | Quy tắc từ chối/quarantine có lý do; không âm thầm NULL hóa |
| Source snapshot bị thay đổi | Checkpoint không còn phản ánh tập chốt | Dừng, tạo snapshot/manifest mới, đối soát ảnh hưởng |
| CDC lag tăng | Mô hình mới chưa theo kịp nguồn | Chưa cutover, điều chỉnh năng lực và xử lý backlog |
| Số hàng nguồn/đích khớp nhưng tiền sai | Mapping hoặc transform lỗi | So từng record và aggregate theo group |
| Đã cutover nhưng SLO tệ | Ảnh hưởng người dùng | Rollback read routing nếu an toàn, điều tra chỉ mục/query |
| Retention xóa raw quá sớm | Không thể tái tạo | Dừng xóa, khôi phục từ archive/backup nếu có và đánh giá chứng cứ |

### 14.3. Đánh dấu FAILED khác xóa checkpoint

Khi job lỗi nghiệp vụ, **giữ checkpoint và các batch đã commit** để điều tra. Nếu muốn đổi từ FAILED về RUNNING, phải xác minh:

- Snapshot và transform version không đổi.
- Sai lệch đã được xử lý.
- Những hàng đích đã commit còn hợp lệ.
- Trạng thái job/lease bảo đảm không có worker cũ vẫn ghi.

Nếu logic transform thay đổi, việc tiếp tục từ checkpoint cũ có thể trộn quy tắc; thường cần job phiên bản mới hoặc kế hoạch rebuild phạm vi bị ảnh hưởng, không chỉ đổi state sang RUNNING.

### 14.4. Cách báo cáo hoàn tất rõ ràng

Một báo cáo nghiệm thu có thể có dạng:

~~~text
BACKFILL: order-fact-v2.1
SNAPSHOT: 501, immutable, manifest verified
JOB: 9001, state COMPLETED
SOURCE SCANNED: 9 records
SOURCE ELIGIBLE: 7 PLACED records
TARGET: 7 rows
ROW-LEVEL DIFF: 0
TENANT-DATE DIFF: 0
TARGET AMOUNT: 1,900,000 VND
TRANSFORM TIMEZONE: Asia/Ho_Chi_Minh
CDC CATCH-UP: Not applicable to frozen snapshot example
CUTOVER: Not yet executed
QA: structural/readback only until professional QA phase
~~~

**Chú ý:** đây là **mẫu kết quả kỳ vọng từ dữ liệu minh họa**, không phải kết quả đã thực thi trên database trong bài viết. Khi nghiệm thu thật, phải đính kèm output truy vấn, run ID, version mã và người/phạm vi phê duyệt. Tránh đồng nhất “đã viết script” với “đã chạy và xác minh script”.

## 15. Thiết kế cho khả năng rollback và khả năng tái lập

### 15.1. Giữ đường đọc cũ trong một cửa sổ có kiểm soát

Sau khi đối soát và catch-up, ứng dụng có thể dùng **feature flag** hoặc routing để chuyển:

~~~text
Trước:
  GET /reports/orders -> legacy query

Trong cutover:
  GET /reports/orders -> v2 query
  shadow comparison được ghi riêng (không trả dữ liệu bóng)

Nếu lỗi:
  quay lại legacy query theo chính sách rollback
~~~

Việc rollback đường đọc chỉ an toàn nếu **đường dữ liệu cũ vẫn còn được cập nhật/đáp ứng hợp đồng**. Nếu đã ngừng ghi nguồn cũ rồi, chỉ đổi feature flag không tự đưa dữ liệu mới trở lại mô hình cũ. Cần xác định **rollback dữ liệu**, không chỉ rollback mã ứng dụng.

### 15.2. Không xóa nguồn ngay sau khi báo cáo bằng nhau

Đối soát tại một thời điểm là điều kiện cần, chưa phải lý do đủ để xóa bảng cũ. Những consumer khác có thể vẫn đọc nó; bản ghi lịch sử có thể cần cho kiểm toán; một lỗi chỉ xuất hiện sau vài ngày tải thật.

Kế hoạch contract nên liệt kê:

- Consumer nào đã nâng cấp và xác nhận?
- Các batch/job/export cũ có còn tham chiếu schema không?
- Thời hạn rollback và retention phù hợp là bao lâu?
- Có backup/immutable snapshot và hướng khôi phục không?
- Có quy trình xử lý late event/correction sau cutover không?

### 15.3. Tái lập cùng đầu vào chưa chắc ra cùng kết quả nếu thiếu version

Để chạy lại đáng tin cậy, không chỉ giữ SQL text. Cần lưu:

~~~text
source snapshot / manifest / checksum
source schema và phạm vi khóa
transform code + config version
timezone, currency, rounding policy
reference data / dimension snapshots
job ID và những batch đã commit
trạng thái quarantine và quyết định xử lý dữ liệu lỗi
~~~

Nếu một bước tra cứu bảng **country_codes hiện hành** nhưng bảng ấy đã đổi giá trị, replay có thể tạo kết quả khác dù snapshot đơn hàng không đổi. Những dữ liệu tham chiếu ảnh hưởng transform cần được version hóa hoặc cố định theo mốc phù hợp.

### 15.4. Giữ chứng cứ nhưng không nhân đôi dữ liệu nhạy cảm vô hạn

Một bảng progress không cần sao chép toàn bộ payload khách hàng. Nó cần các định danh nguồn, snapshot/version và kết quả đối soát. Raw backup có thể đặt trong kho riêng có phân quyền/retention; lineage metadata dẫn tới đúng nguồn khi cần.

Khi backfill dữ liệu cá nhân, quy trình cần giữ tenant isolation, quyền đọc nguồn/ghi đích và bảo vệ log khỏi lộ email, số điện thoại, token hoặc nội dung nhạy cảm. Việc có checkpoint giúp resume **không cho phép** mỗi worker đọc toàn bộ tenant khác ngoài phạm vi được cấp.

## 16. Runbook từ chuẩn bị đến nghiệm thu

Một runbook cần đủ rõ để người khác tiếp nhận khi worker ban đầu không còn hoạt động. Ví dụ quy trình cho một đợt backfill có thể gồm:

### Giai đoạn A — Phê duyệt mô hình và phạm vi

1. Viết rõ **grain, khóa nguồn, khóa đích, tập hàng đủ điều kiện** và quy tắc đối chiếu.
2. Xác nhận nguồn chuẩn, **snapshot/version**, định nghĩa thời gian, timezone và chính sách dữ liệu lỗi.
3. Kiểm tra DDL, ràng buộc, chỉ mục, dung lượng đích, WAL, replication lag và backup/khôi phục.
4. Chọn batch size ban đầu, concurrency, tốc độ mục tiêu và ngưỡng dừng.
5. Xác nhận khả năng rollback/read routing và thời gian giữ dữ liệu cũ.

### Giai đoạn B — Tạo đầu vào cố định và canh giữ tiến độ

1. Tạo/chốt snapshot hoặc thiết lập snapshot nhất quán có liên hệ tới checkpoint nguồn.
2. Lưu manifest: số hàng, khoảng khóa, nguồn, version, checksum nếu dùng và thời điểm chốt.
3. Tạo job với **snapshot_id, transform_version, high-watermark**, last_id bắt đầu và state RUNNING.
4. Giới hạn quyền ghi job/target, ngăn hai bộ điều phối độc lập tự nhận cùng một job.

### Giai đoạn C — Chạy có kiểm soát

1. Worker đọc checkpoint **từ database**.
2. Khóa quyền cập nhật checkpoint của job.
3. Chọn batch bằng **keyset pagination** từ snapshot.
4. Ghi các hàng đích đủ điều kiện bằng khóa/idempotency đúng.
5. Cập nhật checkpoint theo **source keys đã quét**.
6. Commit **cùng transaction**.
7. Ghi metric của batch và tiếp tục cho đến khi đã quét hết phạm vi.
8. Khi lỗi, giữ nguyên trạng thái đã commit, xác định nguyên nhân trước khi retry.

### Giai đoạn D — Verify và catch-up

1. Chuyển job sang VERIFYING, **chưa công bố**.
2. So sánh **expected vs actual** theo ID, từng cột bắt buộc, tập group và tổng số tiền.
3. Giải quyết chênh lệch; khi sửa quy tắc tạo job/version mới hoặc tái xây theo chính sách.
4. Nếu nguồn sống, áp dụng CDC/change stream sau snapshot và đối soát checkpoint mới.
5. Chạy shadow query, kiểm tra performance và quyền truy cập dữ liệu ở đường đọc mới.

### Giai đoạn E — Publish và contract

1. Ghi bằng chứng nghiệm thu, phạm vi, số liệu đối soát và sự phê duyệt.
2. Chuyển read routing dần theo kế hoạch, giám sát p95/p99 và tính đúng.
3. Có quy trình rollback nếu số liệu/độ trễ không đáp ứng.
4. Chỉ xóa mô hình cũ sau khi tất cả consumer đã được xác nhận và hết cửa sổ rollback.
5. Giữ checkpoint, manifest và kết quả đối soát theo retention đã phê duyệt.

### 16.1. Tiêu chí hoàn tất không nên chỉ là một số phần trăm

Một tập điều kiện nghiệm thu có thể ghi:

~~~text
SOURCE:
  snapshot/manifest immutable = verified
  expected eligible keys = 7
  source scope and transform_version = fixed

PROCESSING:
  last_committed_key = high_watermark = 125
  failed/unresolved batches = 0
  retry duplicates with conflicting payload = 0

DATA:
  target keys = expected keys
  row-level diff = 0
  group-level diff = 0
  total amount = 1,900,000 VND

INTEGRATION:
  source changes caught up (or not applicable)
  application shadow reads = pass
  latency and resource thresholds = pass

RELEASE:
  publication approved
  rollback procedure exercised
  legacy retention and consumers checked
~~~

Các điều kiện trên dùng số mẫu của bài. Với hệ thống thật, cần định nghĩa rõ ngưỡng chấp nhận, cả trường hợp **có quarantine được phê duyệt**; không nên tùy tiện dùng một tỷ lệ “99,9% hàng đúng” nếu 0,1% còn lại có thể chứa giao dịch trọng yếu.

## 17. Bài tập thực hành

### Bài 1 — Tiếp tục sau crash ở một batch

Snapshot có các ID **101, 103, 105, 106, 110, 111, 114, 120, 125**. Job có **last_order_id = 105**. Worker xử lý batch tiếp theo **106, 110, 111**, ghi được hàng 106 và 110, rồi mất kết nối trước khi biết COMMIT thành công hay không.

**Yêu cầu:**

1. Có thể cập nhật checkpoint trong bộ nhớ thành 111 rồi bỏ qua batch không?
2. Khi worker khởi động lại cần làm gì đầu tiên?
3. Nếu transaction đã commit thì các hàng và checkpoint có trạng thái nào?
4. Nếu transaction rollback thì trạng thái nào?
5. Cần thuộc tính gì để retry không nhân đôi dữ liệu?

<details>
<summary>Gợi ý lời giải bài 1</summary>

Không được đoán kết quả từ biến trong RAM. Worker phải kết nối lại và **đọc checkpoint đã commit**. Nếu transaction COMMIT thành công, dữ liệu đích của batch và **last_order_id = 111** cùng tồn tại. Nếu rollback, **checkpoint vẫn 105**, và batch chưa được commit vào đích.

Khi cần chạy lại, **source_order_id là khóa duy nhất** của fact; thao tác INSERT/UPSERT phải có chính sách idempotent và đối soát payload. Việc ghi target và checkpoint trong **cùng transaction** là điều kiện chủ chốt ngăn tiến độ vượt dữ liệu.

</details>

### Bài 2 — Đơn bị lọc và checkpoint sai

Giả sử một batch chỉ có hai đơn:

~~~text
order_id = 205, status = CANCELLED
order_id = 209, status = CANCELLED
~~~

Job lưu checkpoint bằng cách lấy **MAX(source_order_id)** từ các dòng được INSERT vào fact.

**Yêu cầu:** giải thích lỗi, cho biết checkpoint sau batch nên là bao nhiêu và mô tả cách lấy đúng.

<details>
<summary>Gợi ý lời giải bài 2</summary>

Hai đơn bị loại theo quy tắc fact PLACED nên **không có hàng INSERT**. Lấy MAX từ hàng đích cho kết quả **NULL**, checkpoint không tiến và job có thể đọc lặp vô hạn batch này.

Checkpoint phải dựa trên **MAX(order_id) của tập nguồn đã quét trong batch**, bằng **209**, dù số hàng ghi đích là **0**. Việc lấy khóa từ nguồn phải đi cùng transaction ghi đích.

</details>

### Bài 3 — Đối soát đủ số hàng nhưng sai giá trị

Nguồn có ba đơn PLACED:

| order_id | tenant_id | total_vnd |
| ---: | --- | ---: |
| 1 | T01 | 100000 |
| 2 | T01 | 200000 |
| 3 | T02 | 300000 |

Đích có ba hàng, nhưng **order 1 mang 150000, order 2 mang 150000, order 3 giữ 300000**.

**Yêu cầu:**

1. COUNT(*) và SUM(amount_vnd) toàn hệ thống có phát hiện lỗi không?
2. Tổng theo tenant có phát hiện không?
3. Cần phép đối soát nào phát hiện chắc hai giá trị sai?
4. Nếu bảng đích có thêm một đơn thừa và thiếu một đơn nguồn nhưng cùng số tiền, phép kiểm tra nào quan trọng?

<details>
<summary>Gợi ý lời giải bài 3</summary>

COUNT vẫn bằng **3**, SUM vẫn **600000**; tổng T01 vẫn **300000** và T02 vẫn **300000** nên cả tổng theo tenant cũng **không phát hiện** hai giá trị bị đổi.

Cần đối chiếu **theo source_order_id và từng trường** bằng FULL OUTER JOIN/EXCEPT có phạm vi đúng. Với một đơn thừa và một đơn thiếu có tiền bằng nhau, phải so **tập khóa** bằng anti-join hai chiều; chỉ số hàng và tổng tiền vẫn có thể khớp.

</details>

### Bài 4 — High-watermark trên bảng đang ghi

Transaction A lấy order_id **300**, chưa commit. Transaction B lấy **301** và commit. Backfill đọc MAX(order_id) = 301, quét tới 301 rồi đặt last_id = 301. Sau đó A mới commit order 300.

**Yêu cầu:**

1. Vì sao order 300 có thể bị bỏ sót?
2. Việc tăng số batch hoặc giảm LIMIT có chữa được nguyên nhân gốc không?
3. Nêu hai phương án an toàn để backfill trong hệ thống vẫn hoạt động.
4. Nếu có CDC, cần lưu mốc nào để không có khoảng trống giữa snapshot và change stream?

<details>
<summary>Gợi ý lời giải bài 4</summary>

ID được cấp trước commit; khi backfill đã vượt 301, nó sẽ không đọc lại 300. Tăng/giảm LIMIT không giải quyết thứ tự **commit khác thứ tự cấp ID**.

Hai hướng: (a) **chốt nguồn hoặc snapshot bất biến** rồi backfill phạm vi đó; (b) **snapshot nhất quán kết hợp CDC/outbox có checkpoint nguồn**, bắt kịp các thay đổi phát sinh sau snapshot. Cần lưu **source log position/checkpoint liên hệ với snapshot**, không chỉ MAX(id), để không bỏ sót các transaction commit sau mốc.

</details>

### Bài 5 — Chọn cách ghi tổng hợp có thể retry

Pipeline cần tạo **tenant_daily_sales(tenant_id, report_date, amount_vnd)** từ hàng triệu dòng giao dịch. Developer đề xuất chia sự kiện thành batch và với mỗi batch:

~~~sql
UPDATE tenant_daily_sales
SET amount_vnd = amount_vnd + :batch_total
WHERE tenant_id = :tenant_id
  AND report_date = :report_date;
~~~

**Yêu cầu:**

1. Vì sao chạy lại batch có thể làm sai số?
2. Đề xuất một mô hình chi tiết hoặc ledger để ghi có idempotency.
3. Cần lưu gì nếu một giao dịch bị hiệu chỉnh sau khi bảng tổng đã được công bố?

<details>
<summary>Gợi ý lời giải bài 5</summary>

Phép cộng **không idempotent**: chạy lại cùng batch cộng tiền lần nữa. Hướng dễ kiểm chứng là ghi **fact sự kiện/đơn** bằng khóa nguồn duy nhất, rồi **recompute SUM** cho group cần cập nhật; hoặc lưu **batch_contributions(batch_id, tenant_id, report_date, amount_vnd)** với UNIQUE trên batch identity rồi cộng từ ledger đã deduplicate.

Khi một nguồn bị correction, cần giữ source ID/version, mapping nhóm bị ảnh hưởng, transform version và run đã công bố; có thể tính lại group và ghi lịch sử thay đổi, thay vì âm thầm tăng hoặc giảm tổng mà không có chứng cứ.

</details>

### Bài 6 — Vấn đề mốc thời gian và lịch sử

Một đơn được đặt lúc **2026-11-20 00:10:00+07**, nhưng pipeline cũ ghi ngày từ **UTC date**. Một ứng dụng báo cáo mới muốn dùng ngày địa phương Việt Nam.

**Yêu cầu:**

1. Ngày địa phương của đơn này là gì?
2. Ngày UTC tương ứng là gì?
3. Vì sao đổi ngày trong fact có thể làm dịch tổng giữa hai ngày dù tổng toàn kỳ không đổi?
4. Những metadata nào giúp replay cùng một kết quả?

<details>
<summary>Gợi ý lời giải bài 6</summary>

Ngày địa phương Việt Nam là **2026-11-20**, nhưng thời điểm tương ứng ở UTC là **2026-11-19 17:10:00Z**, nên ngày UTC là **2026-11-19**. Nếu pipeline cũ nhóm theo ngày UTC, đơn này thuộc 19/11; pipeline mới nhóm theo ngày Việt Nam, đơn thuộc 20/11. Do đó tổng tiền có thể dịch giữa hai ngày, dù tổng toàn khoảng không đổi nếu phạm vi chọn ngày được đối soát nhất quán.

Cần lưu timestamp nguồn với timezone đúng, **transform_version**, timezone/cấu hình thời gian, snapshot/cutoff và phiên bản dữ liệu tham chiếu (nếu có), không dùng timezone của máy chạy ngầm định.

</details>

### Bài 7 — Cutover hay chưa?

Backfill snapshot lịch sử đã đối soát không có khác biệt. Tuy nhiên, Order Service vẫn tạo đơn mới; consumer CDC đang trễ **25 phút**, và không có bằng chứng đã xử lý hết các bản ghi bị quarantine.

**Yêu cầu:** có nên chuyển toàn bộ dashboard sang V2 không? Nêu tối thiểu bốn điều kiện cần kiểm tra trước khi công bố.

**Hướng giải:** chưa thể kết luận V2 đủ mới và đầy đủ. Cần kiểm tra checkpoint/watermark CDC và chấp nhận lag theo SLO, xử lý quarantine, đối soát các thay đổi từ snapshot đến thời điểm cutover, shadow-read kết quả mới/cũ, kiểm tra độ trễ truy vấn và quyền truy cập, có rollback, ghi nhận phiên bản/manifest dữ liệu sẽ công bố.

## 18. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Backfill chạy một câu UPDATE là đủ.” | Với dữ liệu lớn cần batch, checkpoint, giám sát, đối soát và rollback. |
| “Đã đọc một hàng thì có thể ghi checkpoint qua hàng ấy.” | Chỉ checkpoint khi **các ghi đích liên quan đã commit**. |
| “Checkpoint phải lấy MAX ID của hàng đã INSERT.” | Phải lấy **MAX khóa nguồn đã quét**, kể cả hàng bị filter. |
| “ID tăng luôn theo thứ tự commit.” | Sequence/ID allocation và commit order có thể khác nhau. |
| “Tăng số shard làm backfill tự đúng và tự nhanh.” | Phải phân chia phạm vi, bảo vệ toàn vẹn và đo tải thực. |
| “ON CONFLICT DO NOTHING chứng minh dữ liệu đích đúng.” | Nó chỉ tránh insert trùng; row cũ có thể sai. |
| “Số hàng bằng nhau là đã đối soát.” | Có thể thiếu/thừa bù nhau; cần so tập khóa và giá trị. |
| “Tổng tiền khớp là đủ.” | Sai lệch có thể triệt tiêu; cần đối soát từng record và group. |
| “Nguồn đã có MAX(id) nên không cần snapshot.” | Bản ghi có ID nhỏ hơn max có thể commit muộn, hoặc hàng cũ bị UPDATE. |
| “Có checkpoint là tự động exactly-once.” | Cần transaction hoặc idempotency, khóa duy nhất và bảo vệ thứ tự. |
| “Backfill snapshot xong tức là dữ liệu mới nhất.” | Phải catch-up thay đổi sau snapshot khi nguồn còn sống. |
| “Batch lỗi thì luôn retry vô hạn.” | Lỗi dữ liệu không hợp lệ có thể cần quarantine và can thiệp. |
| “Có thể thay transform version khi job đang chạy.” | Dễ trộn hai công thức trong cùng dataset; phải version/rebuild có kiểm soát. |
| “Đã COMPLETED thì xóa bảng cũ ngay.” | Còn consumer, cửa sổ rollback, retention và cutover. |
| “Rollback chỉ cần đổi feature flag.” | Nếu đường cũ không còn dữ liệu mới, phải có kế hoạch rollback dữ liệu. |
| “NULL hoặc giá trị thiếu cứ điền mặc định cho đủ hàng.” | Có thể làm sai sự thật lịch sử; cần định nghĩa UNKNOWN/N/A hoặc quarantine. |

## 19. Checklist trước khi đánh dấu hoàn tất

| Nhóm | Điều kiện có thể kiểm chứng |
| --- | --- |
| **Nghiệp vụ** | Grain, tập nguồn đủ điều kiện, khóa và chính sách thời gian được xác nhận |
| **Nguồn** | Snapshot/manifest hoặc CDC checkpoint đáng tin, không đổi trong phạm vi run |
| **Mã biến đổi** | Transform version, code/config, timezone, reference snapshot được lưu |
| **Ghi đích** | PK/UNIQUE/FK/CHECK đúng, insert/upsert có idempotency |
| **Checkpoint** | Đã commit cùng các ghi của batch; trỏ tới khóa **đã quét**, không chỉ khóa đã ghi |
| **Resume** | Đã thử crash trước commit, sau commit và retry không tạo sai lệch |
| **Đồng thời** | Worker ownership, khóa/lease/fencing và phạm vi batch không chồng lấn |
| **Lỗi dữ liệu** | Quarantine, rule xử lý và số hàng bị loại có lý do |
| **Đối soát record** | Không thiếu/thừa khóa, các trường trọng yếu tương đương |
| **Đối soát aggregate** | Số lượng và tổng số đo theo tenant/ngày/partition bằng nhau |
| **Nguồn sống** | Đã catch-up CDC/change stream và xác nhận độ mới |
| **Hiệu năng** | Batch duration, p95/p99 ứng dụng, WAL, replica lag trong ngưỡng |
| **Cutover** | Shadow read, quyền truy cập, canary/feature flag và rollback được chuẩn bị |
| **Hậu triển khai** | Giám sát sai lệch tiếp diễn, retention và tiêu chí bỏ schema cũ |

## 20. Ghi nhớ

**Điền bổ sung dữ liệu lịch sử an toàn** là một quy trình có thể **dừng, tiếp tục, chạy lại và chứng minh kết quả**, không chỉ là thao tác INSERT/UPDATE chạy cho hết số hàng. Cần bắt đầu từ **ngữ nghĩa dữ liệu và grain**, chốt snapshot hoặc mốc nguồn đáng tin, xác định khóa và phiên bản biến đổi, sau đó nạp theo **keyset batch** với **checkpoint commit nguyên tử** và ghi đích idempotent.

Trong ví dụ 9 đơn lịch sử, job quét ba batch để tạo **7 fact đơn PLACED** với tổng **1.900.000 VND**. Đơn CANCELLED không được ghi vào fact nhưng vẫn làm checkpoint tiến. Khi job crash, checkpoint đã commit cho biết phần cần chạy lại; khi job quét xong, **FULL OUTER JOIN theo khóa và giá trị** cùng đối soát theo tenant–ngày giúp phát hiện hàng thiếu, thừa hoặc sai tiền mà count/sum tổng có thể che giấu.

Với hệ thống vẫn có ghi mới, **MAX(id) không thay snapshot nhất quán và change capture**; phải bắt kịp cập nhật, sửa, xóa và dữ liệu đến trễ trước khi cutover. Một thiết kế đáng tin cậy đi theo chuỗi: **định nghĩa nguồn và mô hình đích → snapshot/version → batch có checkpoint → idempotent replay → đối soát hai chiều → catch-up → publish có rollback → giám sát và giữ chứng cứ**. Khả năng **resume** bảo vệ tiến độ; khả năng **reconcile** bảo vệ ý nghĩa và độ đúng của dữ liệu.
