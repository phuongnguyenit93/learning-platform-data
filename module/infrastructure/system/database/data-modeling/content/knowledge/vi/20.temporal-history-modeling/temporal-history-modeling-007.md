# Ảnh chụp định kỳ và truy vấn dữ liệu tại một thời điểm

## 1. Khi một câu hỏi về quá khứ không thể trả lời từ trạng thái mới nhất

Trong module **DATABASE_DATA_MODELING**, thiết kế dữ liệu phải bắt đầu từ câu hỏi nghiệp vụ, rồi mới chuyển thành thực thể, quan hệ, khóa, ràng buộc, chỉ mục và lược đồ vật lý. Với chương **Thời gian và lịch sử**, một câu hỏi thường gặp là:

> “Vào 10:30 ngày 10/06, kho số 1 còn bao nhiêu sản phẩm A?”

Giả sử hệ thống chỉ lưu một hàng tồn kho hiện tại. Đến 17:00, số lượng đã đổi nhiều lần; đọc hàng hiện tại không còn cho biết giá trị lúc 10:30. Để tra cứu quá khứ, có thể lưu **ảnh chụp định kỳ** (*periodic snapshot*) của trạng thái. Nhưng nếu chỉ chụp lúc 00:00 và 12:00, ảnh chụp cũng không tự biết điều gì đã xảy ra giữa hai mốc.

Bài học này phân biệt ba kết quả thường bị đánh đồng:

1. **Giá trị tại mốc chụp:** “Ảnh chụp lúc 12:00 ghi tồn kho bằng bao nhiêu?”
2. **Giá trị quan sát gần nhất trước thời điểm T:** “Nếu chỉ có ảnh chụp, tại T tôi có thể hiển thị giá trị đã ghi gần nhất nào?” Đây thường là **số liệu trễ**, không bảo đảm là trạng thái thật tại T.
3. **Giá trị chính xác tại một thời điểm hoặc phiên bản:** “Tồn kho đã được hệ thống xác nhận tại 10:30 là bao nhiêu?” Muốn trả lời chính xác giữa các mốc chụp, cần **lịch sử thay đổi đầy đủ** hoặc nguồn phiên bản thời gian phù hợp để tái dựng.

Ảnh chụp là một **chiến lược lưu trạng thái để đọc nhanh và giảm chi phí tái dựng**. Nó không mặc nhiên thay thế lịch sử thay đổi, audit log, log giao dịch hay mô hình hai chiều thời gian.

Sau bài học, người học cần thiết kế được lịch chụp dữ liệu, xác định ranh giới nhất quán, kết hợp snapshot với các thay đổi phát sinh, viết truy vấn theo phiên bản hoặc thời điểm và kiểm chứng các giới hạn về độ chính xác, dung lượng, thời gian lưu, công nghệ dữ liệu.

## 2. Ảnh chụp dữ liệu là gì?

**Snapshot** là bản ghi hoặc tập bản ghi thể hiện **trạng thái đã được xác định tại một điểm cắt nhất quán** (*consistent cutoff*). Điểm cắt có thể được định nghĩa bằng:

- **Một phiên bản của thực thể**, ví dụ số thứ tự thay đổi **state_version = 103** cho hàng tồn kho của sản phẩm A tại kho 1.
- **Một vị trí trong luồng sự kiện hoặc log**, ví dụ offset, sequence hay vị trí commit được nguồn dữ liệu bảo đảm.
- **Một lần đọc nhất quán của cơ sở dữ liệu**, chẳng hạn transaction sử dụng cùng một MVCC snapshot cho toàn bộ tập hàng.
- **Một mốc nghiệp vụ được chốt**, ví dụ trạng thái số dư tại thời điểm khóa sổ cuối ngày, sau khi mọi nghiệp vụ của kỳ được xử lý.

Không phải cứ thêm cột **snapshot_at** vào một bảng là đã có snapshot nhất quán. Nếu đọc từng hàng trong nhiều phút mà dữ liệu tiếp tục thay đổi, những hàng khác nhau có thể đến từ các thời điểm nguồn khác nhau. Bản kết quả như vậy chỉ là **một lần quét dữ liệu**, chưa chắc là một ảnh chụp có ý nghĩa “toàn hệ thống tại T”.

### 2.1. Ba loại mốc thời gian phải tách biệt

| Trường/mốc | Trả lời câu hỏi | Có thể khác nhau không? |
|---|---|---|
| **source_cutoff** hoặc **as_of_version** | Bản chụp bao gồm những thay đổi nào của nguồn? | Có, là ranh giới dữ liệu thực sự |
| **capture_started_at** | Công việc chụp bắt đầu lúc nào? | Có, trước thời điểm hoàn thành |
| **capture_finished_at** | Việc lưu bản chụp hoàn thành lúc nào? | Có, sau khi đọc và ghi dữ liệu |

Một nhãn như **snapshot_day = 2026-06-10** mô tả kỳ báo cáo, không nhất thiết chứng minh mọi hàng đều phản ánh đúng trạng thái tại 00:00 ngày ấy. Cần quy định liệu đó là ngày ghi nhãn, ngày nghiệp vụ, thời điểm khóa sổ hay điểm cắt của nguồn.

**Nguyên tắc:** thời điểm ảnh chụp được *tạo ra* khác với thời điểm dữ liệu mà nó *đại diện*. Khi những mốc này khác nhau, truy vấn lịch sử phải dựa vào **điểm cắt nguồn** thay vì chọn bản chụp mới nhất theo thời gian upload.

### 2.2. Snapshot dữ liệu khác backup cơ sở dữ liệu

**Snapshot ứng dụng** thường lưu các thuộc tính hoặc kết quả tổng hợp cần đọc, ví dụ số dư, số lượng tồn, điểm tích lũy, trạng thái quy trình, số khách hoạt động cuối ngày.

**Backup/PITR** phục vụ khôi phục toàn bộ database sau sự cố; có thể kết hợp bản sao nền với transaction log để khôi phục đến thời điểm nhất định nếu cơ sở dữ liệu và cấu hình cho phép. Một bản backup vật lý không tự cung cấp API nghiệp vụ “giá đơn hàng số 42 tại T”; ngược lại, một bảng snapshot tồn kho không thay thế được backup.

**Audit log** ghi ai làm gì, ở đâu, khi nào. Một số audit log đủ dữ liệu để tái dựng, nhưng nhiều log chỉ có thông tin thao tác hoặc thông điệp thiếu ngữ nghĩa; không nên coi mọi loại log là nguồn thay đổi đầy đủ.

## 3. Ví dụ xuyên suốt: tồn kho thay đổi giữa hai lần chụp

Xét **warehouse_id = 1**, **sku_id = 100** trong ngày **10/06/2026**. Đơn vị tính là sản phẩm. Mọi mốc giờ dưới đây tính bằng **UTC**, các thay đổi được xử lý thành công và có thứ tự phiên bản trong cùng một luồng của hàng tồn kho này.

| Mốc | Hoạt động | Thay đổi số lượng | Số lượng sau thay đổi | Phiên bản |
|---|---|---:|---:|---:|
| 00:00 | Chụp trạng thái đầu ngày | — | **30** | 100 |
| 08:00 | Nhập hàng | +5 | **35** | 101 |
| 10:00 | Xuất hàng | -4 | **31** | 102 |
| 11:00 | Ghi nhận hỏng | -2 | **29** | 103 |
| 12:00 | Chụp trạng thái giữa ngày | — | **29** | 103 |
| 14:00 | Nhập hàng | +6 | **35** | 104 |
| 16:00 | Xuất hàng | -3 | **32** | 105 |
| 00:00 ngày 11/06 | Chụp trạng thái cuối kỳ | — | **32** | 105 |

Ảnh chụp đầu ngày lưu **30, version 100**; ảnh chụp giữa ngày lưu **29, version 103**. Nếu có yêu cầu tìm tồn kho tại **10:30**:

- **Chỉ có ảnh chụp:** ta biết bản đã chụp gần nhất trước T có số lượng 30, nhưng **không được khẳng định** tồn kho thực tế tại 10:30 là 30.
- **Có lịch sử thay đổi đầy đủ:** sau version 100 đã có **+5 ở version 101** và **-4 ở version 102**. Khi đó tồn kho ở version 102 là **30 + 5 - 4 = 31**.
- **Có snapshot 12:00 nhưng hỏi lúc 10:30:** bản 12:00 đã chứa thay đổi lúc 11:00, nên không thể dùng trực tiếp làm trạng thái 10:30.

Cùng cách tính, tại phiên bản 104 ta lấy snapshot version 103, rồi áp dụng **+6** để được **35**. Tại phiên bản 105 tiếp tục áp dụng **-3** để được **32**.

### 3.1. Hình dung snapshot và các thay đổi nằm giữa

~~~mermaid
flowchart LR
    S0["Snapshot V100<br/>00:00 = 30"] --> E1["+5<br/>V101"]
    E1 --> E2["-4<br/>V102"]
    E2 --> E3["-2<br/>V103"]
    E3 --> S1["Snapshot V103<br/>12:00 = 29"]
    S1 --> E4["+6<br/>V104"]
    E4 --> E5["-3<br/>V105"]
    E5 --> S2["Snapshot V105<br/>11/06 = 32"]
~~~

Một snapshot sau version 103 đã tích lũy các thay đổi đến version 103. Khi tái dựng từ nó, phải bắt đầu **sau version 103**, không áp dụng lại event 103.

### 3.2. Hai mức chính xác không được đánh đồng

**Truy vấn theo phiên bản:** “Trạng thái sau khi áp dụng tất cả thay đổi đến version 102 là gì?” — trả lời chính xác nếu snapshot và lịch sử thay đổi đầy đủ, đúng thứ tự.

**Truy vấn theo đồng hồ:** “Trạng thái của hệ thống tại 10:30:00 UTC là gì?” — chỉ trả lời chính xác nếu hệ thống có quy tắc đáng tin để ánh xạ **thời điểm T** thành **tập các thay đổi đã có hiệu lực/đã được commit tới T**.

Một cột **event_at** được ứng dụng tự ghi trước khi transaction commit chưa đủ để bảo đảm câu trả lời đúng theo trạng thái đã commit tại T. Với hệ thống có yêu cầu kiểm toán nghiêm ngặt, có thể cần commit position, transaction ordering hoặc cơ chế temporal của database. Nếu sự kiện có hiệu lực hồi tố, còn phải phân biệt thời điểm nghiệp vụ với thời điểm hệ thống biết sự kiện ấy.

## 4. Các kiểu ảnh chụp và mục đích sử dụng

| Kiểu | Nội dung | Lợi ích | Hạn chế hoặc yêu cầu |
|---|---|---|---|
| **Full snapshot** | Toàn bộ tập trạng thái trong phạm vi đã định tại một điểm cắt | Đọc độc lập, đối soát dễ | Tốn dung lượng và chi phí I/O mỗi lần chụp |
| **Snapshot theo từng thực thể** | Trạng thái từng đơn, tài khoản, SKU sau N thay đổi | Replay ngắn, hỗ trợ tải một thực thể | Không bảo đảm nhất quán toàn hệ thống nếu mỗi thực thể được chụp lúc khác nhau |
| **Incremental/delta snapshot** | Chỉ phần dữ liệu thay đổi kể từ mốc nền | Giảm lượng ghi khi ít thay đổi | Cần chuỗi nền + delta đầy đủ để phục hồi; mất một delta có thể làm sai kết quả |
| **Aggregate snapshot** | Số tổng hợp đã chốt theo kỳ: doanh thu, tồn, số dư | Báo cáo nhanh, giảm truy vấn từ nguồn chi tiết | Không thể truy ngược chi tiết không được lưu |
| **Snapshot + event log** | Trạng thái nền và các thay đổi có thứ tự sau nền | Tái dựng đúng từng phiên bản, tránh phát lại từ đầu | Phải duy trì đủ event, ranh giới nguồn và replay deterministic |

**Full snapshot** là đầy đủ trong phạm vi nghiệp vụ được định nghĩa, ví dụ mọi SKU tại một kho, chứ không nhất thiết toàn bộ database. Nếu một snapshot chỉ bao gồm sản phẩm đang bán nhưng không gồm sản phẩm đã ngừng, phải lưu rõ tiêu chí bao phủ để kết quả “không thấy hàng” không bị hiểu nhầm là tồn kho bằng 0.

**Delta snapshot** cũng khác **event log**: delta có thể chỉ nói “cột X đổi từ 10 sang 12” hoặc “hàng 42 được cập nhật”, trong khi event nghiệp vụ nói “nhập kho 2 đơn vị do phiếu nhận Y”. Khả năng replay, kiểm toán và giải thích nguyên nhân của từng cách khác nhau.

## 5. Chọn lịch chụp từ yêu cầu truy vấn và tần suất thay đổi

Không có một chu kỳ “mỗi ngày” đúng cho mọi nghiệp vụ. Nên hỏi:

- Người dùng cần trạng thái **cuối ngày** hay cần trạng thái tại **bất kỳ giây nào**?
- Khoảng trễ chấp nhận được là bao nhiêu? Một dashboard được phép hiện số liệu cách đây 15 phút hay phải phản ánh transaction mới nhất?
- Số thay đổi trung bình và cực đại giữa hai lần chụp là bao nhiêu?
- Replay một thay đổi có tốn CPU/I/O đáng kể không?
- Snapshot phải giữ bao lâu; có yêu cầu giữ số liệu đã công bố, chốt kỳ hay đối soát pháp lý không?
- Phạm vi chụp là một thực thể, một kho, một dịch vụ hay nhiều database?
- Có bản thay đổi đến muộn, điều chỉnh hồi tố hoặc tình trạng nguồn chưa xác nhận không?

Một ước lượng đơn giản cho luồng thay đổi đều:

~~~text
Số event tối đa phải replay xấp xỉ:
tốc độ thay đổi (event / giờ) × số giờ giữa hai snapshot

Số event replay trung bình xấp xỉ một nửa mức tối đa
nếu thời điểm truy vấn phân bố đều trong chu kỳ.
~~~

Ví dụ 2.000 thay đổi/giờ và snapshot 6 giờ/lần dẫn tới tối đa khoảng 12.000 event cần replay cho một luồng nếu không có mốc trung gian. Đây là ước lượng về khối lượng, không phải lời hứa thời gian phản hồi; CPU còn phụ thuộc độ phức tạp của mỗi event và cách lưu chỉ mục.

Chu kỳ chụp cũng ảnh hưởng **độ mất mát thông tin khi chỉ giữ snapshot**. Chụp 5 phút/lần vẫn không tái dựng được một giá trị tại mốc giữa hai lần chụp nếu không lưu thay đổi ở giữa. Chụp thường xuyên làm giảm khoảng không quan sát được, nhưng không biến dữ liệu lấy mẫu thành lịch sử liên tục.

## 6. Mô hình dữ liệu quan hệ: trạng thái hiện tại, event và snapshot

Ví dụ PostgreSQL dưới đây sử dụng **version tuần tự theo từng cặp (warehouse_id, sku_id)**. Phiên bản tăng khi cập nhật tồn kho; snapshot lưu version đã bao gồm. Mục tiêu là có một nguồn thay đổi bền vững để tái dựng **đúng trạng thái tại version N**.

### 6.1. Bảng trạng thái hiện tại

~~~sql
CREATE TABLE inventory_balance (
    warehouse_id bigint NOT NULL,
    sku_id       bigint NOT NULL,
    qty_on_hand  bigint NOT NULL CHECK (qty_on_hand >= 0),
    state_version bigint NOT NULL CHECK (state_version >= 0),
    PRIMARY KEY (warehouse_id, sku_id)
);
~~~

Khóa kép chỉ rõ **một số tồn kho hiện tại cho mỗi SKU tại mỗi kho**. Nếu hệ thống quản lý tồn theo lô hàng, hạn sử dụng hoặc chủ sở hữu, cần thêm chiều phân biệt vào khóa hoặc tạo thực thể tồn riêng. Tránh gộp những lô không được phép thay thế nhau rồi mong snapshot có thể phục hồi chi tiết đã mất.

**qty_on_hand** là số lượng vật lý theo mô hình này. “Khả dụng để bán” có thể bằng on-hand trừ hàng đã đặt trước hoặc bị khóa; phải lưu hoặc tính riêng reservation và các thành phần khác nếu đó mới là câu hỏi nghiệp vụ.

### 6.2. Bảng thay đổi có thứ tự theo thực thể

~~~sql
CREATE TABLE inventory_movement (
    warehouse_id   bigint NOT NULL,
    sku_id         bigint NOT NULL,
    stream_version bigint NOT NULL CHECK (stream_version >= 1),
    qty_delta      bigint NOT NULL CHECK (qty_delta <> 0),
    operation_id   uuid NOT NULL UNIQUE,
    accepted_at    timestamptz NOT NULL,
    reason_code    text NOT NULL,
    PRIMARY KEY (warehouse_id, sku_id, stream_version)
);

CREATE INDEX ix_inventory_movement_time
    ON inventory_movement
       (warehouse_id, sku_id, accepted_at, stream_version);
~~~

**stream_version** xác định thứ tự áp dụng thay đổi của một SKU tại một kho. **operation_id** dùng để nhận diện lệnh nghiệp vụ và chống nhân đôi khi retry. **accepted_at** hữu ích cho điều tra theo thời gian, nhưng không mặc nhiên là thời điểm commit chính xác hoặc thời điểm nghiệp vụ có hiệu lực hồi tố.

Để bảo đảm bảng thay đổi và trạng thái không lệch nhau, tất cả lần cập nhật cùng một SKU phải thực hiện trong **một transaction**. Khi có bootstrap từ hệ thống cũ, phải xác định rõ giá trị đầu và phiên bản nền; không giả định mọi SKU khởi tạo bằng 0 nếu nguồn không bảo đảm.

### 6.3. Một giao thức cập nhật tối thiểu

Giả sử ứng dụng đã xác thực thao tác nhập/xuất kho và có **operation_id** riêng. Với một SKU đã tồn tại:

~~~sql
BEGIN;

UPDATE inventory_balance
SET qty_on_hand = qty_on_hand + :delta,
    state_version = state_version + 1
WHERE warehouse_id = :warehouse_id
  AND sku_id = :sku_id
  AND qty_on_hand + :delta >= 0
RETURNING state_version;

-- Ứng dụng phải xác nhận đúng 1 hàng được cập nhật
-- và lấy version vừa RETURNING làm stream_version.

INSERT INTO inventory_movement (
    warehouse_id, sku_id, stream_version,
    qty_delta, operation_id, accepted_at, reason_code
)
VALUES (
    :warehouse_id, :sku_id, :returned_version,
    :delta, :operation_id, clock_timestamp(), :reason_code
);

COMMIT;
~~~

Các dấu **:parameter** là tham số ứng dụng bind, không phải biến SQL PostgreSQL dùng trực tiếp trong mọi trình chạy lệnh. Ví dụ trên diễn đạt giao thức, không phải stored procedure hoàn chỉnh.

Nếu INSERT thất bại do trùng **operation_id** hoặc version, cả transaction phải rollback, bao gồm phần UPDATE. Retry cần kiểm tra kết quả của operation_id đã tồn tại và trả về trạng thái phù hợp; không tự tăng version lần nữa. Khi hai transaction cùng sửa một hàng, khóa hàng do UPDATE giúp tuần tự hóa việc tăng version, nhưng service vẫn phải xử lý rollback và các điều kiện nghiệp vụ.

Nếu sự kiện có thể đưa số lượng âm hoặc thay đổi theo nhiều chiều tài sản, ràng buộc **qty_on_hand >= 0** cần được xem xét lại theo nghiệp vụ. Không dùng một quy tắc “không âm” cho sổ kế toán hoặc kho cho phép âm dự kiến khi điều đó không đúng.

## 7. Lược đồ lưu các lần chụp

Có hai cấp thông tin:

1. **Snapshot run:** metadata của một đợt chụp, trạng thái hoàn tất, lúc bắt đầu/kết thúc và phạm vi dữ liệu.
2. **Snapshot row:** trạng thái từng SKU tại đúng **state_version** được nguồn thể hiện khi chụp.

~~~sql
CREATE TABLE inventory_snapshot_run (
    run_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at  timestamptz,
    run_status   text NOT NULL
                 CHECK (run_status IN ('BUILDING', 'COMPLETE', 'FAILED')),
    row_count    bigint CHECK (row_count IS NULL OR row_count >= 0)
);

CREATE TABLE inventory_snapshot (
    run_id        bigint NOT NULL
                  REFERENCES inventory_snapshot_run(run_id),
    warehouse_id  bigint NOT NULL,
    sku_id        bigint NOT NULL,
    qty_on_hand   bigint NOT NULL,
    state_version bigint NOT NULL CHECK (state_version >= 0),
    PRIMARY KEY (run_id, warehouse_id, sku_id)
);

CREATE INDEX ix_snapshot_lookup_by_version
    ON inventory_snapshot
       (warehouse_id, sku_id, state_version DESC, run_id DESC);
~~~

**run_id** nhận diện một lần chụp; **state_version** là ranh giới mà snapshot đã bao gồm **trong luồng của từng SKU**. Vì mỗi SKU có phiên bản riêng, không được coi số 103 của SKU A và số 103 của SKU B là cùng một thời điểm toàn cục.

**run_status = COMPLETE** là điều kiện để bản chụp được dùng. Nếu quá trình chụp lỗi hoặc mới lưu được một phần, hệ thống không được coi nó là snapshot đầy đủ.

**row_count** là thông tin kiểm chứng số hàng trong phạm vi đã định. Trong sản phẩm thực tế nên có thêm **scope**, schema/version của định dạng snapshot, checksum, dữ liệu nguồn, mã job và thông tin độ tin cậy. Nếu cần chụp cả dữ liệu mềm bị xóa, phải có quy tắc cho các entity đã bị xóa để bản chụp không làm mất ngữ nghĩa tồn tại/không tồn tại.

### 7.1. Tạo snapshot nhất quán trong một database

Một cách minh họa là chụp toàn bộ **inventory_balance** trong một transaction có mức cô lập **REPEATABLE READ** của PostgreSQL:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

INSERT INTO inventory_snapshot_run (run_status)
VALUES ('BUILDING')
RETURNING run_id;

-- Ứng dụng lấy run_id ở trên rồi truyền lại vào INSERT sau.

INSERT INTO inventory_snapshot (
    run_id, warehouse_id, sku_id, qty_on_hand, state_version
)
SELECT
    :run_id, warehouse_id, sku_id, qty_on_hand, state_version
FROM inventory_balance;

UPDATE inventory_snapshot_run
SET run_status = 'COMPLETE',
    finished_at = clock_timestamp(),
    row_count = (
        SELECT COUNT(*)
        FROM inventory_snapshot
        WHERE run_id = :run_id
    )
WHERE run_id = :run_id;

COMMIT;
~~~

Dưới **REPEATABLE READ**, các câu SELECT trong transaction dùng cùng một ảnh MVCC nhất quán của dữ liệu nguồn. Do đó các hàng được ghi ra từ **inventory_balance** phản ánh một lát cắt nhất quán trong phạm vi database và transaction, với điều kiện mọi đường ghi bảo đảm **inventory_balance** và **inventory_movement** cập nhật nguyên tử.

Lưu ý:

- **started_at** và **finished_at** cho biết thời gian job, **không tự xác định thời điểm commit chính xác của snapshot nguồn**.
- Để chụp nhiều database hoặc các dịch vụ độc lập, một transaction PostgreSQL không tạo ra điểm cắt nhất quán cho toàn hệ thống. Cần cơ chế snapshot/watermark phối hợp hoặc mô hình nhất quán có độ trễ được công bố.
- Bảng run và các hàng snapshot nên được lưu sao cho người đọc chỉ nhìn thấy dữ liệu **COMPLETE** đã commit. Với transaction như trên, thành công hay thất bại được quyết định nguyên tử.
- Chụp tất cả trạng thái trong một transaction dài có thể tốn tài nguyên và kéo dài thời gian giữ ảnh MVCC; cần đo tác động vận hành. Khi chuyển sang snapshot theo lô, phải thiết kế lại ranh giới nhất quán và tiêu chí hoàn tất.

### 7.2. Chụp riêng từng thực thể có bảo đảm khác

Nếu mỗi SKU được chụp độc lập sau mỗi 100 phiên bản, một bản chụp chỉ có thể nói **“SKU này ở version 100”**. Cách đó phù hợp để tăng tốc truy vấn từng SKU.

Nếu báo cáo yêu cầu **“tổng tồn kho của mọi SKU tại đúng thời điểm T”**, việc ghép bản chụp riêng của SKU A tại 09:00 và SKU B tại 09:07 sẽ không tự tạo ra một trạng thái toàn kho ở cùng T. Phải dùng lần chụp nhất quán toàn phạm vi hoặc một checkpoint/watermark toàn cục có nghĩa rõ.

## 8. Tái dựng trạng thái tại một phiên bản bằng snapshot + event

Giả sử API được yêu cầu xác định số lượng tồn sau **target_version = 102** của kho 1, SKU 100. Ta phải:

1. Chọn snapshot **COMPLETE** có version lớn nhất **không vượt 102**.
2. Đọc các movement có version **lớn hơn phiên bản của snapshot** và **nhỏ hơn hoặc bằng 102**.
3. Áp dụng đúng thứ tự và đúng một lần từng thay đổi.
4. Trả giá trị cuối cùng cùng metadata của snapshot nền và version đích.

SQL minh họa với **qty_delta** cộng dồn:

~~~sql
WITH selected_snapshot AS (
    SELECT
        s.run_id,
        s.qty_on_hand AS base_qty,
        s.state_version AS base_version
    FROM inventory_snapshot s
    JOIN inventory_snapshot_run r
      ON r.run_id = s.run_id
    WHERE r.run_status = 'COMPLETE'
      AND s.warehouse_id = 1
      AND s.sku_id = 100
      AND s.state_version <= 102
    ORDER BY s.state_version DESC, s.run_id DESC
    LIMIT 1
)
SELECT
    s.run_id,
    s.base_version,
    102 AS target_version,
    s.base_qty + COALESCE(SUM(m.qty_delta), 0) AS qty_as_of_version
FROM selected_snapshot s
LEFT JOIN inventory_movement m
  ON m.warehouse_id = 1
 AND m.sku_id = 100
 AND m.stream_version > s.base_version
 AND m.stream_version <= 102
GROUP BY s.run_id, s.base_version, s.base_qty;
~~~

Với ví dụ ở phần 3, bản nền version 100 có **30**, replay các movement version 101 (+5) và 102 (-4), nên kết quả **31**.

**Điều kiện biên rất quan trọng:** movement ngay tại **base_version** đã nằm trong snapshot, nên phải lọc **stream_version > base_version** để tránh tính hai lần. Movement tại target_version phải được bao gồm, nên dùng **<= target_version**.

**Nếu không tìm được snapshot đủ sớm**, CTE không có hàng, kết quả truy vấn cũng không có hàng. Ứng dụng phải thông báo thiếu nền phù hợp hoặc dùng một phương án replay từ trạng thái khởi tạo **được xác minh**, thay vì trả về 0 một cách ngầm định.

### 8.1. Phiên bản là ranh giới logic; timestamp là một bài toán khác

Để biết **target_version cho thời điểm T**, nguồn dữ liệu phải cung cấp ánh xạ đáng tin:

~~~text
T = 10:30 UTC
Các thay đổi đã có hiệu lực theo ngữ nghĩa truy vấn tới T:
V101 (+5), V102 (-4)
=> target_version = 102
~~~

Nếu chỉ có **accepted_at** gắn với INSERT trước commit, lựa chọn các event có accepted_at <= T có thể phản ánh **thời gian xử lý** chứ không phản ánh chính xác các transaction đã commit và khả kiến tại T. Một transaction ghi accepted_at lúc 10:29 nhưng commit 10:31 chẳng hạn chưa phải trạng thái đã commit lúc 10:30.

Muốn bảo đảm truy vấn “hệ thống đã commit gì vào T”, phải định nghĩa mốc commit/ordering phù hợp ở tầng nguồn. Với yêu cầu “dữ liệu có **hiệu lực nghiệp vụ** tại T”, cần sử dụng valid time và xử lý thay đổi hồi tố; một luồng chỉ có thứ tự ghi nhận không mặc nhiên trả lời được.

### 8.2. Dùng snapshot sau T để suy ngược có an toàn không?

Có trường hợp dữ liệu chỉ gồm các delta đảo ngược được, nên về mặt số học có thể lấy snapshot sau T rồi trừ các thay đổi sau T. Tuy nhiên cách này chỉ hợp lệ khi **mọi phép biến đổi có thể đảo ngược, lịch sử đầy đủ và thứ tự được bảo đảm**. Với trạng thái quy trình, quy tắc không thuần cộng hoặc tác động từ dịch vụ ngoài, replay ngược có thể không đáng tin.

Thiết kế mặc định nên chọn **snapshot tại hoặc trước điểm cắt đích**, sau đó replay xuôi. Nó giúp giữ ngữ nghĩa rõ, xử lý logic replay và phát hiện thiếu sự kiện dễ hơn.

## 9. Nếu chỉ có snapshot định kỳ thì truy vấn được gì?

Giả sử không lưu movement, chỉ còn snapshot 00:00 = 30 và snapshot 12:00 = 29.

| Câu hỏi | Có thể trả lời chắc chắn? | Giải thích |
|---|---|---|
| Ảnh chụp 00:00 ghi bao nhiêu? | Có: 30 | Là giá trị được chụp tại mốc nguồn đã xác minh |
| Ảnh chụp 12:00 ghi bao nhiêu? | Có: 29 | Là giá trị được chụp tại mốc nguồn đã xác minh |
| 10:30 tồn thực tế bao nhiêu? | **Không** | Có thể đã nhập/xuất hàng giữa hai lần chụp |
| Chỉ số quan sát gần nhất trước 10:30 là bao nhiêu? | Có, nếu xác định được ranh giới nguồn | Giá trị quan sát gần nhất là 30, có độ trễ |
| Số lượng đã tăng giảm qua những bước nào? | **Không** | Snapshot tổng không lưu từng bước trung gian |
| Có thể suy ra tồn lúc 10:30 từ hai đầu 30 và 29 không? | **Không** | Nhiều chuỗi thay đổi khác nhau có cùng hai đầu |
| Sau bản chụp cuối cùng và đến hiện tại có bao nhiêu? | Chỉ khi có dữ liệu phát sinh sau | Bản chụp cũ không tự biết thay đổi mới |

Một API chỉ dựa trên snapshot nên đặt tên rõ: **latest_snapshot_before**, **sampled_value**, **last_observed_at**, **data_freshness**. Không nên đặt tên kết quả là **exact_balance_at(T)** nếu không có cơ chế phục hồi trạng thái tại T.

### 9.1. Không nội suy trạng thái rời rạc

Lấy trung bình 30 và 29 để suy ra 29,5 tại 06:00 là vô nghĩa đối với số lượng hàng nguyên, trạng thái đơn hàng hay quyền truy cập. Nội suy chỉ phù hợp với một số đại lượng liên tục và mô hình thống kê được xác thực, không phải mặc định của lịch sử dữ liệu.

Nếu yêu cầu chỉ cần **báo cáo xu hướng**, có thể chấp nhận giá trị chụp theo giờ/ngày. Nếu yêu cầu đối soát mỗi giao dịch, cần lưu biến động nghiệp vụ chi tiết.

## 10. Độ nhất quán của một lần chụp quan trọng hơn nhãn thời gian

Một snapshot nhiều bảng có thể bị **lệch thời điểm** nếu dữ liệu nguồn tiếp tục thay đổi trong lúc job đọc.

Ví dụ hệ thống chuyển 100 đơn vị từ kho A sang kho B trong một giao dịch:

- Trước giao dịch: A = 500, B = 300, tổng = 800.
- Sau giao dịch: A = 400, B = 400, tổng = 800.

Nếu job đọc A **trước** giao dịch và B **sau** giao dịch, nó có thể chụp A = 500 và B = 400, tổng = 900, dù không có trạng thái nhất quán nào của cả hệ thống có tổng 900.

### 10.1. Phương án cho một cơ sở dữ liệu giao dịch

Đối với các bảng nằm trong **một database** với transaction và MVCC thích hợp, có thể đọc trong cùng một transaction nhất quán (ví dụ REPEATABLE READ trong PostgreSQL). Các hàng trong phạm vi đọc phản ánh cùng một MVCC snapshot nguồn.

Nếu một quy trình phải đọc nhiều trang bằng nhiều transaction khác nhau, **mỗi trang có thể có một điểm cắt khác**. Chỉ bảo đảm “mọi câu SELECT đều đọc dữ liệu đã commit” (READ COMMITTED) chưa đủ để khẳng định cả đợt chụp là một trạng thái đồng nhất.

### 10.2. Phương án cho hệ thống nhiều dịch vụ

Nếu trạng thái nằm ở nhiều microservice hoặc database khác nhau, cần chọn hợp đồng dữ liệu rõ ràng:

- Chấp nhận **eventual consistency** và ghi rõ watermark/độ trễ của từng nguồn.
- Tổ chức một **snapshot barrier**: các nguồn dừng hoặc đánh dấu những thay đổi đã đạt cùng một điểm cắt logic.
- Dùng luồng sự kiện có offset/checkpoint để xây một projection nhất quán theo quy tắc thứ tự đã định.
- Chụp từng nguồn rồi **đối soát** các bất biến liên nguồn; báo cáo biết rõ có thể khác nhau theo mốc.

Một **timestamp chung** được gắn vào nhiều file không tự tạo đồng bộ nhân quả giữa các dịch vụ. Nếu hệ thống không thể chụp nguyên tử toàn cục, cần trình bày tính nhất quán ở mức **cam kết được**, không khẳng định chính xác hơn bằng chứng.

## 11. Dữ liệu đến muộn, sửa hồi tố và ảnh chụp đã xuất bản

Giả sử ngày 12/06 bộ phận kho nhận một phiếu điều chỉnh nói rằng số lượng hao hụt **đã xảy ra ngày 10/06**. Hai câu hỏi khác nhau là:

- “Theo thông tin hiện nay, tồn kho có hiệu lực nghiệp vụ lúc 11:30 ngày 10/06 là bao nhiêu?”
- “Vào 11:30 ngày 10/06, hệ thống lúc đó **đã ghi nhận** tồn kho là bao nhiêu?”

Nếu snapshot 12:00 ngày 10/06 được tạo **trước khi hệ thống biết** hao hụt đó, thay đổi hồi tố có thể làm kết quả đúng theo nghiệp vụ khác với số đã được chụp và công bố.

### 11.1. Không âm thầm viết lại snapshot đã chốt

Một báo cáo tồn kho đã gửi cho bộ phận tài chính có thể cần giữ nguyên **snapshot đã công bố**, ngay cả khi thông tin sau đó bị đính chính. Các phương án thường gặp:

- Giữ bản snapshot cũ bất biến và tạo **snapshot phiên bản điều chỉnh** mới với liên kết tới bản cũ.
- Lưu **decision_ref**, lý do và thời điểm đính chính; cho biết bản nào đang được coi là mới nhất.
- Phát hành báo cáo điều chỉnh nếu nghiệp vụ yêu cầu, không thay số liệu trong báo cáo đã chốt mà không lưu dấu vết.
- Khi cần truy vấn **“ngày đó hệ thống đã biết gì?”**, mô hình hóa known/system time hoặc một event log đủ đầy để tái dựng lịch sử kiến thức.

Một bảng có **snapshot_at** và **updated_at** không tự trở thành bitemporal. Nếu muốn trả lời hai câu hỏi thời gian, phải thiết kế khả năng giữ cả giá trị có hiệu lực tại **B** và những gì hệ thống biết tại **K**.

### 11.2. Hai chiến lược xử lý event đến muộn

**Chiến lược A — ghi bút toán điều chỉnh tại thời điểm được chấp nhận:** giữ sổ biến động đã ghi, thêm một movement bù trừ với lý do. Nó phù hợp với nhiều hệ thống kế toán/kho cần kiểm chứng thay đổi đã ghi nhận.

**Chiến lược B — tính lại lịch sử hiệu lực nghiệp vụ:** đưa dữ liệu mới vào dòng thời gian valid time, tính lại những đoạn bị ảnh hưởng và phát hành snapshot/projection sửa đổi. Phải giữ lịch sử kiến thức cũ nếu yêu cầu điều tra “hệ thống trước đó đã tin gì”.

Không được tự chọn chiến lược chỉ vì đơn giản khi lập trình. Hậu quả với hóa đơn, sổ cái, hoàn tiền và báo cáo pháp lý phải do nghiệp vụ quy định.

## 12. Kiểm soát tính đầy đủ của event sau mỗi snapshot

Snapshot + event chỉ tái dựng đúng khi event **không thiếu, không lặp hiệu lực và có thứ tự áp dụng rõ**.

Với một SKU có snapshot version 100 và target_version 103, các movement cần có **101, 102, 103**. Nếu chỉ có 101 và 103 nhưng event 102 bị thất lạc, phép cộng delta cho ra số có vẻ hợp lệ nhưng sai.

### 12.1. Những bất biến dữ liệu cần kiểm tra

| Bất biến | Ý nghĩa |
|---|---|
| **Mỗi stream_version duy nhất theo thực thể** | Không áp dụng hai movement tại cùng version |
| **Mỗi operation_id được xử lý tối đa một lần** | Retry không nhân đôi thay đổi |
| **Dãy version cần replay không bị thiếu** | Có thể phục hồi đúng từ snapshot nền |
| **Snapshot.version đã bao gồm mọi event tới version đó** | Không bỏ sót hoặc tính hai lần khi replay |
| **Snapshot đã COMPLETE mới được dùng** | Không chọn bản chụp đang ghi một phần |
| **Snapshot và movement cùng ngữ nghĩa số lượng** | Không cộng delta từ đơn vị hoặc quy tắc khác |
| **Phiên bản schema replay tương thích** | Event cũ vẫn được diễn giải đúng sau nâng cấp |
| **Nguồn thay đổi có thẩm quyền được xác định** | Không lẫn CDC trùng, event thử nghiệm và bút toán thật |

Một khóa chính có thể ngăn **version trùng**, nhưng không tự ngăn **version bị thiếu**. Khi phục hồi, cần kiểm tra độ liên tục hoặc đối chiếu tổng số biến động và checkpoint. Tùy mô hình, có thể dùng sequence theo thực thể, checksum lũy kế hoặc cơ chế phát event có thứ tự từ nguồn có thẩm quyền.

### 12.2. Idempotency khi phát lại và khi áp dụng nghiệp vụ

Nếu movement là **delta**:

~~~text
+5, -4, -2
~~~

áp dụng lại event +5 hai lần sẽ khiến kết quả sai. Vì vậy mỗi event phải được áp dụng **đúng một lần về mặt hiệu quả**, ngay cả khi môi trường gửi thông điệp hỗ trợ at-least-once.

Nếu event là một **giá trị tuyệt đối** (“set quantity = 35”), replay cũng cần thứ tự và xử lý idempotency; nhận bản 35 sau bản 31 có thể đưa trạng thái quay ngược. Dạng payload khác nhau dẫn đến logic replay khác nhau.

### 12.3. Replay phải deterministic

Một sự kiện cũ cần cho cùng kết quả dù được replay sau nhiều tháng. Tránh logic replay phụ thuộc vào:

- Bảng giá **hiện tại** thay vì giá có hiệu lực khi sự kiện được chốt.
- Thời gian **now()** hoặc kết quả API ngoài tại lúc replay.
- Cấu hình nghiệp vụ mới mà không có phiên bản schema/quy tắc tương ứng.
- Thứ tự nhận thông điệp không ổn định.

Nếu quy tắc thay đổi, cần version cho sự kiện, snapshot hoặc cách dịch event cũ (*upcaster*), và có kế hoạch kiểm tra kết quả replay so với dữ liệu đã chốt.

## 13. Chỉ mục, phân vùng và chi phí lưu trữ

Cần thiết kế theo hai nhóm truy vấn khác nhau:

- **Tra snapshot gần nhất theo version của một thực thể**, dùng khóa thực thể và version giảm dần.
- **Tra toàn bộ movement trong khoảng version**, dùng khóa chính có thứ tự theo (warehouse_id, sku_id, stream_version).

Ví dụ trong phần 6–7 đã tạo các khóa này. Khi báo cáo cần nhiều SKU tại cùng run, khóa chính **(run_id, warehouse_id, sku_id)** hỗ trợ quét theo run. Khi hỏi lịch sử theo thời gian đồng hồ, chỉ mục **accepted_at** có thể hữu ích nhưng chỉ bảo đảm đúng ngữ nghĩa của cột ấy, không tự biến nó thành commit time.

### 13.1. Ước lượng dung lượng

Với full snapshot:

~~~text
Dung lượng xấp xỉ =
số thực thể được chụp
× kích thước một bản trạng thái
× số lần chụp còn giữ
+ chỉ mục, bản sao và metadata
~~~

Giả sử có **5 triệu SKU-kho**, mỗi trạng thái cần trung bình **100 byte dữ liệu hữu ích**, chụp mỗi giờ. Dung lượng payload lý thuyết mỗi snapshot khoảng **500 MB**, chưa tính index, row overhead, compression, WAL, replication và backup. Trong 30 ngày, 720 lần chụp tạo khoảng **360 GB payload** trước những chi phí cộng thêm. Đây chỉ là phép tính định cỡ sơ bộ; phải đo thực tế trên hệ thống sẽ triển khai.

Tối ưu thường gặp: giảm tần suất snapshot cho các luồng ít thay đổi; chụp theo thực thể khi đủ N event; dùng incremental snapshot với mốc nền; nén dữ liệu; archive snapshot cũ; hoặc chỉ giữ aggregate đã chốt khi nghiệp vụ không cần chi tiết.

### 13.2. Phân vùng và retention

Partitioning theo **run_id**, thời điểm chụp hoặc phạm vi tổ chức có thể làm các truy vấn và xóa theo kỳ dễ hơn, nhưng phải kiểm tra chỉ mục, khóa và cơ chế phân vùng thực tế của hệ quản trị.

Chính sách retention phải xét **cả snapshot và event**. Nếu xóa event 101–103 nhưng chỉ còn snapshot version 100 và snapshot version 105, không thể tái dựng chính xác version 102. Một chính sách hợp lệ có thể giữ một **snapshot nền không muộn hơn mốc PIT sớm nhất cần hỗ trợ**, cộng đủ event liên tiếp từ nền tới các version cần truy vấn.

Xóa snapshot cũ một mình có thể chấp nhận nếu event từ nguồn khởi tạo vẫn còn và khả năng replay phù hợp. Xóa event có thể chấp nhận nếu nhu cầu chỉ giữ các mốc snapshot được xác nhận. Không được đồng thời quảng cáo truy vấn chi tiết bất kỳ thời điểm nào nếu retention đã cắt mất chuỗi cần thiết.

## 14. Khác nhau giữa snapshot vận hành và snapshot phân tích

Trong hệ thống **OLTP**, một snapshot thường tăng tốc đọc hoặc phục hồi trạng thái của một đơn, một tài khoản, một SKU. Dữ liệu phải bảo toàn bất biến giao dịch và khả năng truy vấn theo phiên bản.

Trong hệ thống **OLAP**, snapshot có thể là bảng **fact_snapshot** theo ngày/tháng, chẳng hạn:

~~~text
inventory_daily_snapshot
  business_date
  warehouse_id
  sku_id
  closing_qty
  snapshot_revision
  source_cutoff
  published_at
~~~

Khóa nghiệp vụ không nhất thiết chỉ gồm **business_date + warehouse_id + sku_id** nếu cho phép **nhiều lần phát hành lại** số liệu cho cùng ngày. Khi có revision, phải xác định bản nào là bản được công bố ban đầu và bản nào là bản điều chỉnh.

### 14.1. Fact snapshot khác fact giao dịch

| Dạng dữ liệu phân tích | Hạt dữ liệu | Trả lời tốt |
|---|---|---|
| **Transaction fact** | Một chuyển động/đơn hàng/sự kiện | “Trong kỳ có những giao dịch nào?” |
| **Periodic snapshot fact** | Một thực thể hoặc tổ hợp chiều ở mỗi kỳ | “Cuối mỗi ngày tồn kho bao nhiêu?” |
| **Accumulating snapshot fact** | Một quy trình có các cột mốc hoàn thành được cập nhật | “Đơn mất bao lâu từ đặt đến giao?” |

Một **periodic snapshot fact** có thể hỗ trợ biểu đồ tồn cuối ngày rất tốt nhưng không cho biết từng lần nhập/xuất trong ngày. Một **accumulating snapshot** có thể được cập nhật khi quy trình tiến triển và cần cơ chế lưu lịch sử riêng nếu muốn tái dựng tất cả lần thay đổi trước đó.

### 14.2. Kết hợp với dimension có phiên bản

Nếu SKU được gán vào danh mục A đầu tháng rồi chuyển sang danh mục B giữa tháng, báo cáo “tồn kho cuối ngày theo danh mục có hiệu lực vào ngày đó” cần **temporal join** với lịch sử danh mục.

Ví dụ bảng tồn ngày 10/06 chứa SKU 100, còn dimension danh mục được phiên bản hóa theo **[valid_from, valid_to)**. Báo cáo phải chọn dimension chứa **business_date** của dòng fact hoặc dùng surrogate key phiên bản đã được chốt. JOIN vào danh mục hiện tại có thể viết lại lịch sử phân nhóm và làm sai so sánh theo kỳ.

Nếu dimension bị điều chỉnh hồi tố, cần quyết định liệu báo cáo phải **tái tính theo thông tin mới** hay **giữ đúng số liệu đã công bố**. Snapshot phân tích và lịch sử kiến thức của dimension là hai vấn đề liên quan nhưng không thể thay thế cho nhau.

## 15. Triển khai ý tưởng trên document và graph

### 15.1. Document database

Một snapshot của từng giỏ hàng hoặc tài liệu sản phẩm có thể được lưu thành document:

~~~json
{
  "entityType": "inventory-balance",
  "warehouseId": 1,
  "skuId": 100,
  "snapshotVersion": 103,
  "qtyOnHand": 29,
  "captureRunId": "run-2026-06-10-noon",
  "schemaVersion": 1
}
~~~

Để tra trạng thái tại version 104, chọn document có **snapshotVersion <= 104** lớn nhất rồi replay movement phiên bản sau nó. Các phép cập nhật và phát event phải giữ cùng thứ tự/ngữ nghĩa.

Nếu nhúng toàn bộ snapshot lịch sử vào **một document hiện tại**, kích thước document có thể tăng không giới hạn và làm mỗi lần ghi tốn kém. Collection snapshot riêng thường dễ phân vùng, index và kiểm soát retention hơn.

### 15.2. Graph database

Với đồ thị tổ chức, một snapshot có thể lưu tập node/edge tại một kỳ. Nhưng nếu mục tiêu là trả lời **“ngày 15/03 nhân viên 42 thuộc phòng nào và người quản lý của phòng đó là ai?”**, cần bảo đảm các **quan hệ MEMBER_OF và MANAGED_BY** được đánh giá ở cùng thời điểm.

Chụp node hôm thứ hai và edge hôm thứ tư không tự tạo được một đồ thị lịch sử đúng ngày thứ ba. Có thể lưu cạnh theo khoảng hiệu lực và dựng subgraph as-of; hoặc chụp toàn bộ đồ thị tại một điểm cắt nhất quán nếu khối lượng cho phép.

Với hai chiều thời gian, cần biết cả quan hệ có hiệu lực tại **B** và hệ thống đã biết quan hệ ấy tại **K**. Snapshot đồ thị định kỳ không tự tạo bitemporal nếu không lưu những phiên bản kiến thức trước đó.

## 16. Kiểm chứng bằng ma trận truy vấn và lỗi thường gặp

### 16.1. Ma trận kết quả trên ví dụ tồn kho

| Yêu cầu | Nguồn được dùng | Kết quả kỳ vọng |
|---|---|---|
| Sau version 100 | Snapshot đầu ngày | 30 |
| Sau version 101 | Snapshot V100 + event 101 | 35 |
| Sau version 102 | Snapshot V100 + event 101–102 | 31 |
| Sau version 103 | Snapshot giữa ngày V103 hoặc replay V100 | 29 |
| Sau version 104 | Snapshot V103 + event 104 | 35 |
| Sau version 105 | Snapshot V103 + event 104–105 | 32 |
| Hỏi 10:30 chỉ với snapshot 00:00 và 12:00 | Không đủ lịch sử biến động | Không thể xác định chính xác |
| Hỏi 10:30 với ánh xạ thời gian tin cậy tới version 102 | Snapshot + event 101–102 | 31 |
| Hỏi version 99, không có snapshot trước hoặc đủ log nền | Thiếu dữ liệu | Thông báo không đủ lịch sử |

Phân biệt **truy vấn trả về 0** với **truy vấn không có câu trả lời**. Nếu snapshot nền thiếu, không được mặc định tồn kho bằng 0. Nếu một SKU thực sự chưa tồn tại tại thời điểm đó, phải có dữ liệu về thời gian tạo hoặc quy tắc khởi tạo để chứng minh điều ấy.

### 16.2. Các ca kiểm thử vận hành

1. **Off-by-one:** snapshot version 103 không được replay lại movement 103.
2. **Thiếu event:** có movement 101 và 103 nhưng mất 102; hệ thống phát hiện thiếu chuỗi và không tuyên bố kết quả chính xác.
3. **Retry:** operation_id trùng được nhận diện, không cộng qty_delta thêm lần nữa.
4. **Snapshot chưa hoàn tất:** run đang BUILDING không được sử dụng, kể cả khi đã có một số hàng snapshot.
5. **Snapshot thất bại giữa chừng:** không để hàng đã chụp một phần hiển thị như bản COMPLETE.
6. **Tăng version và ghi event:** nếu một phần INSERT thất bại, cả thay đổi trạng thái và event phải rollback.
7. **Ghi đồng thời:** hai movement của cùng SKU nhận version khác nhau đúng thứ tự, không mất cập nhật.
8. **Ghi nhiều SKU:** một snapshot toàn kho không tạo tổng vô lý do đọc các hàng từ những trạng thái nguồn khác nhau.
9. **Timestamp trước commit:** sự kiện ghi giờ 10:29 nhưng commit 10:31 không được dùng để khẳng định trạng thái đã commit lúc 10:30.
10. **Event đến muộn:** xác định rõ nó là điều chỉnh tại thời gian ghi nhận hay thay đổi có hiệu lực hồi tố.
11. **Migration schema:** replay dữ liệu cũ bằng quy tắc tương thích với schema/version trước đó.
12. **Retention:** xoá snapshot/log không phá hỏng khả năng truy vấn trong kỳ đã cam kết.
13. **Đối soát:** replay đến version hiện tại phải bằng inventory_balance hiện tại; lệch là tín hiệu lỗi.
14. **Timezone:** lịch snapshot cuối ngày theo thị trường phải được tính từ múi giờ nghiệp vụ, không dựa ngầm vào ngày UTC.

### 16.3. Sai lầm cần tránh

| Sai lầm | Vì sao sai | Hướng khắc phục |
|---|---|---|
| Chọn snapshot gần nhất trước T và gọi đó là trạng thái chính xác tại T | Thay đổi có thể xảy ra sau snapshot | Ghi nhãn số liệu lấy mẫu hoặc replay log đầy đủ |
| Dùng snapshot sau T để trả lời T | Đã bao gồm sự kiện tương lai so với T | Chọn cutoff không vượt mục tiêu; replay xuôi |
| Chỉ lưu snapshot_at là đủ | Không chứng minh điểm cắt nguồn, độ trễ capture | Lưu version/watermark và metadata phạm vi |
| Snapshot theo trang ở READ COMMITTED nhưng coi là một thời điểm | Mỗi trang có thể nhìn thấy trạng thái khác nhau | Cùng một MVCC snapshot hoặc barrier |
| Chỉ giữ event delta và không có nền | Không biết số lượng khởi tạo, replay có thể sai | Snapshot nền xác minh hoặc event khởi tạo đầy đủ |
| Snapshot và event không đồng bộ trong một transaction | Snapshot có thể bao gồm thay đổi thiếu trong log | Ghi trạng thái và movement nguyên tử |
| Xóa log ngay sau snapshot mới nhất | Không còn truy vấn được version giữa các snapshot cũ | Retention dựa trên cửa sổ PIT đã cam kết |
| Dùng accepted_at làm commit-time chắc chắn | Timestamp được tạo trước commit, có thể sai tại T | Nguồn commit ordering hoặc giới hạn ngữ nghĩa rõ ràng |
| Sửa snapshot đã chốt mà không lưu revision | Mất bằng chứng về số liệu đã công bố | Snapshot revision, nguồn điều chỉnh, báo cáo bù trừ |

## 17. Bài thực hành: tính trạng thái đơn hàng bằng snapshot và event

Một hệ thống xử lý đơn hàng có chuỗi:

~~~text
Version 1: CREATED
Version 2: PAID
Version 3: PICKING
Version 4: PACKED
Version 5: SHIPPED
Version 6: DELIVERED
~~~

Sau version 3, hệ thống chụp snapshot trạng thái **PICKING**, gắn **order_id = 42, snapshot_version = 3**. Một snapshot tiếp theo được tạo sau version 6.

Yêu cầu nghiệp vụ:

> “Nhân viên chăm sóc khách hàng phải tra được đơn hàng đã ở trạng thái gì sau từng bước xử lý. Việc tra cứu version 5 phải nhanh dù đơn có hàng nghìn sự kiện phụ trợ.”

Hãy giải quyết theo trình tự:

1. **Định nghĩa nguồn sự thật:** các event nghiệp vụ có thứ tự và payload đủ để dựng trạng thái đơn hàng; phân biệt event trạng thái với audit hoặc sự kiện phụ trợ.
2. **Định nghĩa snapshot:** lưu order_id, snapshot_version, trạng thái dựng được, schema_version và mốc chụp; không tự cho rằng bản snapshot version 6 có thể trả lời version 5.
3. **Truy vấn version 5:** chọn snapshot version 3, replay các event version 4 và 5. Kết quả phải là **SHIPPED**.
4. **Kiểm tra tính đầy đủ:** nếu event version 4 thiếu, không được tự nhảy tới version 5 trừ khi event 5 là một bản trạng thái tuyệt đối đã được quy tắc nguồn bảo đảm.
5. **Thiết kế lịch chụp:** ví dụ cứ 100 thay đổi hoặc khi hoàn tất một cột mốc quan trọng; giải thích cách cân bằng số event replay với dung lượng.
6. **Đặt quy tắc đồng thời:** cập nhật trạng thái và lưu event trong một transaction, version tăng đơn điệu theo từng order; retry có operation_id để không nhân đôi chuyển đổi.
7. **Xử lý câu hỏi theo đồng hồ:** nếu khách hỏi “10:15 đơn đang ở đâu?”, xác định hệ thống lưu loại thời gian nào và có đủ bằng chứng ánh xạ thời điểm sang version hay không.
8. **Xử lý điều chỉnh hồi tố:** nếu đối tác vận chuyển gửi muộn một mốc giao hàng, phân biệt “sự kiện thực tế xảy ra lúc nào” và “hệ thống đã ghi nhận lúc nào”; xác định có cần mô hình valid/known time hay không.
9. **Kiểm thử retention:** nếu xóa snapshot version 3 và các event version 1–3, hệ thống có còn trả lời version 5 từ nền khác không?

**Tiêu chí đạt:** xác định được nguồn dữ liệu, phiên bản nền, tập event phải replay, giới hạn truy vấn theo timestamp và kết quả kỳ vọng sau từng version. Không dùng snapshot “gần nhất về thời gian ghi file” khi mục tiêu thực sự là phiên bản của luồng nghiệp vụ.

## 18. Checklist trước khi chọn snapshot định kỳ

Trước khi phê duyệt mô hình, trả lời rõ:

- **Câu hỏi nghiệp vụ:** cần số liệu đã chụp, số liệu quan sát gần nhất hay trạng thái chính xác tại T?
- **Điểm cắt:** snapshot đại diện cho version/offset/MVCC snapshot nào; started_at và finished_at khác source_cutoff ra sao?
- **Phạm vi:** snapshot bao gồm toàn bộ loại thực thể nào, có loại trừ entity đã xóa hoặc chưa kích hoạt không?
- **Cơ chế lấy dữ liệu:** cùng transaction nhất quán hay nhiều nguồn có watermark riêng; có thể bảo đảm bất biến tổng thể không?
- **Nguồn thay đổi:** event/CDC có đầy đủ, có thứ tự, idempotent và đủ thông tin để replay không?
- **Truy vấn:** có chọn nền tại hoặc trước target_version, dùng biên **(base_version, target_version]** và phát hiện thiếu log không?
- **Thời gian:** có phân biệt event time, valid time, accepted time và commit time theo yêu cầu thực tế không?
- **Tần suất:** snapshot bao lâu một lần để cân bằng độ trễ đọc, số event replay và chi phí lưu?
- **Dữ liệu chốt và hồi tố:** snapshot đã công bố có revision; thay đổi hồi tố có để lại bằng chứng và giải pháp điều chỉnh nghiệp vụ không?
- **Ràng buộc và vận hành:** khóa thực thể, transaction, trạng thái run, checksum, monitoring, rollback và retry đã đầy đủ chưa?
- **Lưu trữ:** retention của cả snapshot lẫn event có còn phục vụ mọi mốc lịch sử đã cam kết không?
- **Tiến hóa:** khi thay schema, chuyển từ quan hệ sang document/graph hoặc đẩy sang kho phân tích, các câu trả lời tại version/T có giữ được ý nghĩa không?

**Nguyên tắc cốt lõi:** snapshot định kỳ ghi lại **một trạng thái tại điểm cắt đã được xác định**. Nó giúp đọc nhanh và giảm số bước tái dựng, nhưng một dãy snapshot rời rạc không tự nói được điều gì xảy ra giữa các mốc. Muốn truy vấn chính xác trạng thái quá khứ, hãy kết hợp snapshot với lịch sử thay đổi đầy đủ và thứ tự đáng tin, hoặc dùng một mô hình temporal tương đương. Thiết kế chỉ hoàn chỉnh khi **nguồn sự thật, điểm cắt, độ chính xác và giới hạn truy vấn** đều rõ ràng và có thể kiểm chứng.
