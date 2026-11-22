# Transaction ID, xmin, xmax và trạng thái phiên bản hàng trong PostgreSQL

## 1. Từ một hàng dữ liệu đến nhiều phiên bản MVCC

Giả sử một ứng dụng quản lý tài liệu có hàng:

~~~text
doc_id = 1
title  = "Bản nháp"
status = "draft"
~~~

Nhân viên A bắt đầu sửa thành `title = 'Đã duyệt'` nhưng **chưa COMMIT**. Cùng lúc, nhân viên B mở màn hình xem tài liệu. B có nên nhìn thấy nội dung chưa commit của A không? Nếu B đang chạy một báo cáo dài, có nên đột nhiên nhìn thấy một phần kết quả mới từ A giữa các bước tính toán không?

PostgreSQL sử dụng **MVCC — Multi-Version Concurrency Control**, tức cơ chế quản lý **nhiều phiên bản của hàng**. Thay vì sửa trực tiếp một giá trị duy nhất rồi buộc mọi người nhìn cùng một bản, PostgreSQL có thể giữ các phiên bản tuple khác nhau để mỗi transaction thấy phiên bản phù hợp với **snapshot** của mình.

Khi tìm hiểu MVCC, bạn sẽ thường gặp:

- **Transaction ID (XID):** định danh một transaction có thể được dùng trong cơ chế kiểm soát phiên bản.
- **`xmin`:** trường hệ thống gắn với transaction đã **tạo phiên bản tuple**.
- **`xmax`:** trường hệ thống có thể ghi transaction đã **đánh dấu kết thúc phiên bản** hoặc tham gia **khóa hàng**; không thể diễn giải chỉ bằng "khác 0 tức là đã xóa".
- **`ctid`:** vị trí vật lý của phiên bản tuple, thay đổi khi cập nhật hoặc viết lại bảng.
- **Snapshot:** góc nhìn của một câu lệnh/transaction về các transaction nào đã hoàn tất, đang hoạt động hoặc chưa được nhìn thấy.
- **VACUUM/FREEZE:** cơ chế quản lý các phiên bản cũ và tuổi XID để tránh tích lũy dữ liệu chết và wraparound.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của XID, XID 32-bit và Full Transaction ID (`xid8`).
2. Truy vấn có kiểm soát các system column `xmin`, `xmax`, `ctid`.
3. Mô tả vòng đời tuple qua `INSERT`, `UPDATE`, `DELETE`, `COMMIT` và `ROLLBACK`.
4. Phân biệt **trạng thái transaction** với **khả năng nhìn thấy tuple theo snapshot**.
5. Hiểu vì sao `xmax != 0` **không đủ** để kết luận hàng đã bị xóa.
6. Quan sát hai phiên đọc/ghi đồng thời theo READ COMMITTED và REPEATABLE READ.
7. Biết vai trò của `pg_xact`, tuple header flags, HOT, VACUUM, freezing và wraparound.
8. Tránh dùng `xmin`, `xmax` hoặc `ctid` làm khóa nghiệp vụ/audit log.
9. Thiết kế optimistic locking bằng một cột version riêng và biết cách chẩn đoán transaction dài.

> **Phạm vi:** đây là bài về cơ chế MVCC trong PostgreSQL, không phải tài liệu cho phép đọc/chỉnh sửa trực tiếp các page dữ liệu. Chỉ thực hành trên database lab có quyền phù hợp; không giữ transaction mở lâu hay thực hiện VACUUM FULL trên production để thử nghiệm.

---

## 2. Phân biệt ba khái niệm quan trọng

Trong PostgreSQL có ít nhất ba lớp thông tin khác nhau:

| Lớp | Đối tượng | Câu hỏi được giải đáp |
|---|---|---|
| **Transaction** | XID, trạng thái in-progress/committed/aborted | "Giao dịch tạo/sửa dữ liệu đã hoàn tất chưa?" |
| **Tuple version** | `xmin`, `xmax`, flags, `ctid` | "Phiên bản này do transaction nào tạo, đã bị đánh dấu sửa/xóa hoặc khóa như thế nào?" |
| **Snapshot** | XID horizon, danh sách transaction còn hoạt động, isolation | "Ở thời điểm nhìn của người đọc, phiên bản nào được phép xuất hiện?" |

Một tuple chứa `xmin` và `xmax` **không tự mang toàn bộ câu trả lời "visible hay invisible"**. Cùng một phiên bản có thể:

- Đang hiển thị cho transaction B nhưng không hiển thị cho transaction C vì **snapshot khác nhau**.
- Được nhìn thấy sau khi transaction tạo nó COMMIT, nhưng chưa xuất hiện trong một snapshot cũ.
- Còn nằm trên đĩa sau khi bị DELETE, dù SELECT thông thường không còn trả lại nó.

### 2.1. Một hình dung theo trục thời gian

~~~text
Thời gian ──────────────────────────────────────────────────────>

Transaction A: BEGIN ── UPDATE row ───────────── COMMIT
                    |       |                    |
Version cũ:         |       | vẫn có thể thấy      | không còn thấy
                    |       | từ snapshot cũ       | trong snapshot mới
Version mới:        |  được tạo nhưng chưa      | thấy được từ
                    |  commit, B không thấy      | snapshot phù hợp

Transaction B:  SELECT trước COMMIT       SELECT sau COMMIT
~~~

Đây là mô hình ý tưởng. Chi tiết hàng nào visible phụ thuộc mức cô lập, thời điểm snapshot và tình trạng transaction, không chỉ phụ thuộc việc một COMMIT đã xảy ra.

---

## 3. Transaction ID (XID) là gì?

### 3.1. XID không phải PRIMARY KEY

XID là mã định danh **transaction** trong cơ chế điều phối đồng thời. Nó không phải:

- ID của hàng (`doc_id`).
- ID của người dùng.
- Timestamp tạo hàng.
- Số thứ tự commit có thể dùng làm lịch sử nghiệp vụ.
- Khóa ổn định cho API.

Một transaction chứa nhiều thao tác ghi có thể tạo/sửa **nhiều tuple cùng mang một XID** trong trường `xmin` hoặc `xmax` thích hợp. Ngược lại, một hàng nghiệp vụ qua nhiều lần UPDATE có nhiều phiên bản tuple gắn những XID khác nhau.

### 3.2. Không phải transaction nào cũng lập tức lấy XID thường

PostgreSQL có cơ chế **virtual transaction ID** cho session/transaction và thường chưa cần phân bổ permanent XID ngay khi chỉ thực hiện những tác vụ đọc đơn giản. XID thường được cấp khi transaction cần thực hiện hoạt động yêu cầu XID, chẳng hạn ghi dữ liệu. Không nên nghĩ `BEGIN` luôn lập tức lấy một số XID mới.

Trong phiên bản PostgreSQL có các hàm transaction-ID hiện đại:

~~~sql
BEGIN;

SELECT pg_current_xact_id_if_assigned() AS xid_if_allocated;

-- Hàm sau yêu cầu một XID cho transaction nếu chưa được cấp:
SELECT pg_current_xact_id() AS current_xid8;

ROLLBACK;
~~~

Trên transaction mới chưa cần XID, lời gọi đầu **có thể trả NULL**. `pg_current_xact_id()` bảo đảm trả Full Transaction ID cho transaction và có thể khiến XID được cấp ngay lúc gọi. Không nên gọi nó tràn lan chỉ để "in một con số" trong các báo cáo chỉ đọc.

### 3.3. XID 32-bit và Full Transaction ID

PostgreSQL dùng các XID thông thường có phạm vi **32-bit**, vì vậy số XID về lý thuyết sẽ quay vòng sau nhiều transaction. Để xác định thứ tự tuổi một cách an toàn qua vòng lặp, PostgreSQL sử dụng cơ chế **epoch/full transaction ID** và xử lý freezing/wraparound.

Một số kiểu và biểu diễn:

| Khái niệm | Kiểu/biểu diễn | Lưu ý |
|---|---|---|
| `xmin`/`xmax` của tuple | `xid` (32-bit) | Giá trị hệ thống trong header |
| `pg_current_xact_id()` | `xid8` | Full Transaction ID có thông tin epoch |
| `backend_xid` trong thống kê | XID của backend, nếu đã có | Có thể NULL |
| `backend_xmin` | Horizon snapshot mà backend đang giữ | Không phải `xmin` của một hàng |

**Không so sánh chuỗi** `xmin::text` và `pg_current_xact_id()::text` để xác định "bằng nhau" trong mọi hoàn cảnh. Chúng dùng các biểu diễn/kiểu khác nhau; còn có wraparound, transaction state và phiên bản PostgreSQL.

### 3.4. XID không phải đồng hồ

Hai giao dịch có XID khác nhau chưa đủ để suy ra:

- Giao dịch nào **COMMIT trước**.
- Giao dịch nào có thời điểm kinh doanh trước.
- Giao dịch nào nằm trong cùng một request.

XID thường được cấp theo tiến trình khi cần, nhưng thứ tự cấp **không đồng nghĩa thứ tự COMMIT**. Transaction A có thể được cấp XID trước, chạy lâu, rồi commit **sau** transaction B.

Nếu muốn lưu thời điểm audit, dùng cột rõ nghĩa như `created_at TIMESTAMPTZ` cộng thông tin nghiệp vụ, không suy ra từ XID.

### 3.5. pg_current_snapshot

~~~sql
SELECT
    pg_current_snapshot() AS snapshot_value,
    pg_snapshot_xmin(pg_current_snapshot()) AS low_boundary,
    pg_snapshot_xmax(pg_current_snapshot()) AS high_boundary;
~~~

Các hàm này cho cái nhìn về **ranh giới snapshot** và transaction IDs liên quan, không phải bảng liệt kê mọi phiên bản hàng. Vì snapshot có thể thay đổi giữa các statement ở READ COMMITTED, nếu cần nghiên cứu một snapshot cụ thể thì lấy **một lần** và xem từ đúng giá trị ấy trong cùng truy vấn/CTE.

~~~sql
WITH s AS (
    SELECT pg_current_snapshot() AS snapshot_value
)
SELECT
    snapshot_value,
    pg_snapshot_xmin(snapshot_value) AS snapshot_xmin,
    pg_snapshot_xmax(snapshot_value) AS snapshot_xmax
FROM s;
~~~

Trong bản text của snapshot, bạn có thể thấy một dạng gồm mốc thấp, mốc cao và danh sách XID đang hoạt động. **Giá trị cụ thể thay đổi theo workload**; không có một con số XID cố định để bài học yêu cầu ghi nhớ.

### 3.6. Một ví dụ snapshot mang tính mô hình

Giả sử snapshot có:

~~~text
xmin = 730
xmax = 736
in-progress XIDs = {732, 734}
~~~

Khi xét transaction tạo một tuple:

- XID **từ 736 trở lên** chưa được coi là đã xảy ra trong snapshot này.
- XID **732 hoặc 734** vẫn đang hoạt động ở thời điểm snapshot, nên các ghi của chúng chưa được thấy như dữ liệu committed từ transaction khác.
- Các XID khác **thấp hơn xmax** vẫn cần xét trạng thái committed/aborted và quy tắc hiện hành.

Các mốc snapshot không phải `xmin`/`xmax` của một hàng cụ thể. Đây là **hai bộ tên giống nhau nhưng thuộc hai cấu trúc khác nhau**.

---

## 4. Các system columns của tuple

PostgreSQL cung cấp một số cột hệ thống có thể SELECT trực tiếp dù chúng không thuộc danh sách cột do người dùng CREATE TABLE:

| System column | Ý nghĩa chính | Điều không nên suy ra |
|---|---|---|
| `xmin` | XID tạo phiên bản tuple hiện tại | Không phải thời điểm INSERT nghiệp vụ |
| `xmax` | Trường gắn với kết thúc phiên bản **hoặc trạng thái khóa**, phụ thuộc flags | Khác 0 không chắc bị DELETE/UPDATE đã commit |
| `cmin` | Command ID của lệnh tạo tuple trong transaction | Không phải thời gian tạo |
| `cmax` | Command ID của lệnh đánh dấu kết thúc tuple, khi có ý nghĩa | Không phải timestamp hay trạng thái commit |
| `ctid` | Địa chỉ vật lý của tuple version trong bảng | Không phải khóa chính ổn định |
| `tableoid` | OID của bảng chứa phiên bản (hữu ích khi kế thừa/partition) | Không phải ID nghiệp vụ |

### 4.1. Vì sao SELECT * không hiện xmin?

~~~sql
SELECT *
FROM mvcc_lab.documents;
~~~

Chỉ hiện các cột khai báo thông thường của bảng. Muốn thấy system column, cần **gọi đích danh**:

~~~sql
SELECT
    doc_id,
    title,
    xmin,
    xmax,
    ctid
FROM mvcc_lab.documents;
~~~

Các câu trên chạy sau khi đã tạo bảng lab ở phần kế tiếp.

### 4.2. cmin/cmax không thay thế xmin/xmax

Một transaction có thể chạy nhiều lệnh theo thứ tự; command ID giúp PostgreSQL phân biệt các thay đổi trong cùng transaction theo quy tắc visibility nội bộ. Nhưng `cmin`/`cmax` không được thiết kế như audit "lúc mấy giờ". Người học thường chỉ cần hiểu vai trò, không cần tự sửa/giải mã chúng.

---

## 5. Tạo bảng và dữ liệu để quan sát MVCC

Làm việc trên database lab riêng:

~~~sql
CREATE SCHEMA IF NOT EXISTS mvcc_lab;

CREATE TABLE mvcc_lab.documents (
    doc_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'review', 'published')),
    version_no INTEGER NOT NULL DEFAULT 1
        CHECK (version_no >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Nạp dữ liệu **một lần** vào bảng trống:

~~~sql
INSERT INTO mvcc_lab.documents
    (doc_id, title, status)
VALUES
    (1, 'Bản A', 'draft'),
    (2, 'Bản B', 'draft'),
    (3, 'Bản C', 'draft');
~~~

Quan sát:

~~~sql
SELECT
    doc_id,
    title,
    status,
    version_no,
    xmin::text AS xmin_text,
    xmax::text AS xmax_text,
    ctid,
    tableoid::regclass AS physical_table
FROM mvcc_lab.documents
ORDER BY doc_id;
~~~

Một kết quả **minh họa**, không phải XID/ctid được PostgreSQL bảo đảm:

~~~text
doc_id  title   status  xmin_text  xmax_text  ctid
1       Bản A   draft   741        0          (0,1)
2       Bản B   draft   741        0          (0,2)
3       Bản C   draft   741        0          (0,3)
~~~

Lưu ý:

- XID `741` chỉ là **số ví dụ**; thực tế tùy database và hoạt động đồng thời.
- Nếu cả ba dòng được INSERT trong **một statement/transaction**, chúng thường có cùng `xmin`.
- `xmax=0` thường xuất hiện khi phiên bản chưa bị đánh dấu xóa/sửa/khóa theo cách cần lưu XID, nhưng không nên biến điều này thành rule định nghĩa toàn bộ trạng thái hàng.
- `ctid=(0,1)` là dạng **block/offset vật lý**, không phải ID ổn định.
- Những transaction khác chạy trước/sau sẽ khiến XID trên môi trường của bạn khác kết quả minh họa.

### 5.1. Tách khỏi thứ tự hiển thị

Không phụ thuộc vào thứ tự đọc tự nhiên của table heap. Viết `ORDER BY doc_id` để kết quả nhất quán; `xmin` và `ctid` không thay thế ORDER BY.

### 5.2. Thêm ví dụ không giữ lại

~~~sql
BEGIN;

INSERT INTO mvcc_lab.documents
    (doc_id, title, status)
VALUES
    (99, 'Bản tạm', 'draft');

SELECT doc_id, title, xmin::text AS xmin, xmax::text AS xmax, ctid
FROM mvcc_lab.documents
WHERE doc_id = 99;

ROLLBACK;

SELECT doc_id
FROM mvcc_lab.documents
WHERE doc_id = 99;
~~~

Trong transaction, phiên thực hiện INSERT có thể nhìn thấy hàng vừa thêm với `xmin` của transaction ghi. Sau `ROLLBACK`, SELECT bình thường không còn thấy `doc_id=99`.

Tuy nhiên, điều đó **không chứng minh** bytes của phiên bản tạm bị xóa vật lý khỏi page ngay lúc rollback. Bản ghi vật lý chưa được dọn có thể còn trong storage cho đến khi VACUUM hoặc hoạt động bảo trì xử lý.

---

## 6. xmin: transaction đã tạo phiên bản

### 6.1. INSERT gán xmin cho phiên bản mới

Khi một transaction INSERT thành công một tuple, header của tuple chứa thông tin `xmin` liên quan transaction tạo nó.

~~~sql
BEGIN;

INSERT INTO mvcc_lab.documents
    (doc_id, title, status)
VALUES
    (100, 'Đang kiểm thử', 'review')
RETURNING
    doc_id,
    xmin::text AS creating_xid,
    xmax::text AS xmax_text,
    ctid;

ROLLBACK;
~~~

Ví dụ không giữ thay đổi. Trong transaction ghi, `RETURNING xmin` có thể giúp bạn thấy XID gắn với phiên bản vừa tạo.

### 6.2. UPDATE cũng tạo phiên bản với xmin mới

Điểm dễ ngộ nhận: `xmin` không nhất thiết là XID của lần **INSERT gốc của hàng nghiệp vụ**.

Khi cập nhật:

~~~sql
BEGIN;

UPDATE mvcc_lab.documents
SET title = 'Bản A đã chỉnh',
    version_no = version_no + 1,
    updated_at = now()
WHERE doc_id = 1
RETURNING
    doc_id, title, version_no,
    xmin::text AS version_creator_xid,
    xmax::text AS xmax_text,
    ctid;

ROLLBACK;
~~~

`UPDATE` thường tạo **phiên bản tuple mới** với `xmin` của transaction cập nhật. Phiên bản cũ được đánh dấu để không còn visible sau khi update commit theo snapshot thích hợp.

Sau rollback, phiên bản mới không có hiệu lực; SELECT bình thường vẫn cho hàng như trước khi update.

### 6.3. xmin không phải "ngày tạo"

Giả sử document 1 được tạo từ năm trước nhưng hôm nay UPDATE title. Phiên bản hiện tại sau update commit có `xmin` của transaction **hôm nay**, không phải transaction INSERT ban đầu.

Muốn biết thời điểm tạo thực thể nghiệp vụ, lưu cột riêng:

~~~sql
created_at TIMESTAMPTZ NOT NULL DEFAULT now()
~~~

và đảm bảo ứng dụng không tự sửa created_at khi UPDATE; muốn lịch sử thay đổi chi tiết, dùng audit log/history design phù hợp.

### 6.4. Một transaction nhiều hàng có thể chung xmin

~~~sql
BEGIN;

UPDATE mvcc_lab.documents
SET status = 'review',
    version_no = version_no + 1
WHERE doc_id IN (1, 2)
RETURNING doc_id, xmin::text AS xmin_text;

ROLLBACK;
~~~

Hai phiên bản được tạo trong một transaction có thể chia sẻ XID. Vì vậy **xmin không phải khóa duy nhất cho từng hàng**.

---

## 7. xmax: được ghi khi UPDATE/DELETE hoặc khóa, không đơn giản là "đã xóa"

### 7.1. Ý tưởng cơ bản

Trong mô hình dễ hiểu ban đầu:

~~~text
Phiên bản cũ:
    xmin = transaction tạo ra nó
    xmax = transaction đánh dấu nó hết hiệu lực

Phiên bản mới sau UPDATE:
    xmin = transaction UPDATE
    xmax = chưa đánh dấu kết thúc/khóa tương ứng
~~~

Nhưng đây là **mô hình giáo dục**, không đủ để quyết định visibility chỉ bằng số nguyên trong `xmax`.

### 7.2. DELETE đánh dấu phiên bản cũ

~~~sql
BEGIN;

DELETE FROM mvcc_lab.documents
WHERE doc_id = 3
RETURNING doc_id, title;

ROLLBACK;
~~~

`DELETE` thông thường không tạo một "phiên bản hàng mới với trạng thái deleted" trong bảng. Nó đánh dấu phiên bản hiện tại là bị xóa bởi transaction liên quan. Sau `ROLLBACK`, document 3 vẫn visible.

Nếu DELETE được COMMIT, SELECT thông thường ở snapshot mới sẽ không còn thấy hàng đó, nhưng bản ghi heap cũ có thể vẫn tồn tại vật lý cho đến VACUUM.

### 7.3. xmax khác 0 có thể là UPDATE/DELETE chưa commit

Phiên A đang UPDATE nhưng chưa COMMIT. Phiên B ở READ COMMITTED vẫn có thể thấy **phiên bản cũ**. Header của phiên bản cũ có thể đã ghi `xmax` của transaction A, dù B chưa được nhìn thấy phiên bản mới.

Vì vậy:

~~~sql
-- LƯU Ý: cách suy luận sau là SAI.
SELECT doc_id
FROM mvcc_lab.documents
WHERE xmax::text <> '0';
~~~

Kết quả của câu trên **không phải danh sách tin cậy "hàng đã bị xóa"**. Nó chỉ áp một biểu thức lên trường hệ thống của những phiên bản vốn **đã visible cho SELECT hiện tại**.

### 7.4. xmax khác 0 có thể là khóa hàng

~~~sql
BEGIN;

SELECT doc_id, title
FROM mvcc_lab.documents
WHERE doc_id = 1
FOR UPDATE;

-- Ở phiên khác có thể quan sát system column của
-- phiên bản vẫn visible, nhưng không được suy luận
-- đơn giản từ xmax rằng hàng đã bị xóa.

ROLLBACK;
~~~

Một số row lock được phản ánh vào trường `xmax` và các flag trong tuple header. Trong trường hợp có nhiều locker, PostgreSQL có thể sử dụng **MultiXactId**.

### 7.5. xmax khác 0 có thể trỏ đến transaction đã aborted

Một transaction thử UPDATE/DELETE rồi ROLLBACK. Những dấu vết transaction có thể còn trong tuple header một thời gian; transaction tạo thay đổi đã **aborted** nên không có hiệu lực xóa phiên bản hợp lệ.

Kết luận "xmax khác 0 => deleted" bỏ qua **trạng thái COMMIT/ABORT và flags**, vì vậy sai.

### 7.6. Điều gì cần kiểm tra để xác định tuple visible?

Không chỉ `xmax`:

- `xmin` của tuple có được coi là transaction tạo đã commit và visible với snapshot này không?
- Nếu `xmax` có giá trị, đây là XID xóa/update, locker đơn, hay MultiXact?
- Transaction gắn với `xmax` đã **committed**, **aborted** hay còn **in progress**?
- Snapshot của người đọc có nhìn thấy việc kết thúc phiên bản không?
- Tuple header có flag nói `xmax` không hợp lệ hoặc chỉ liên quan lock không?
- Người đọc có phải **chính transaction tạo/sửa** và đang ở command nào không?

PostgreSQL xử lý các chi tiết này trong engine; ứng dụng thường **không tự tái hiện toàn bộ thuật toán visibility bằng SQL**.

---

## 8. Từ INSERT đến UPDATE đến DELETE: vòng đời phiên bản

### 8.1. INSERT

~~~text
Transaction T10: INSERT document 1
Tuple V1:
    xmin = T10
    xmax = chưa có đánh dấu kết thúc có hiệu lực

T10 COMMIT
=> Snapshot phù hợp về sau có thể thấy V1
~~~

### 8.2. UPDATE

~~~text
Transaction T20: UPDATE document 1

Tuple V1 (cũ):
    xmin = T10
    xmax = T20  [mô hình đánh dấu bị thay]

Tuple V2 (mới):
    xmin = T20
    xmax = chưa có đánh dấu kết thúc có hiệu lực

Trước COMMIT T20:
    Transaction khác có snapshot phù hợp vẫn thấy V1
    Transaction T20 thường thấy thay đổi của chính mình là V2

Sau COMMIT T20:
    Snapshot mới phù hợp thấy V2
    Snapshot cũ có thể vẫn thấy V1
~~~

### 8.3. DELETE

~~~text
Transaction T30: DELETE document 1

Tuple V2:
    xmin = T20
    xmax = T30  [mô hình đánh dấu bị xóa]

Trước COMMIT T30:
    Những reader khác vẫn có thể thấy V2

Sau COMMIT T30:
    Snapshot mới không thấy document 1
    Snapshot đủ cũ vẫn có thể thấy V2
~~~

### 8.4. ROLLBACK

Nếu T20 hoặc T30 **ROLLBACK**, các thay đổi của chúng không được coi là committed. Phiên bản cũ hợp lệ vẫn có thể visible. Đừng nhầm "transaction đã sửa page trước khi rollback" với "database buộc phải hoàn nguyên từng byte ngay lập tức".

### 8.5. Sơ đồ trạng thái theo snapshot

~~~mermaid
flowchart TD
    A["INSERT tạo V1, xmin = T10"] --> B{"T10 kết thúc thế nào?"}
    B -- "ROLLBACK" --> C["V1 không visible cho các snapshot khác"]
    B -- "COMMIT" --> D["V1 có thể visible"]
    D --> E["UPDATE tạo V2; V1 được đánh dấu xmax=T20"]
    E --> F{"T20?"}
    F -- "ROLLBACK" --> D
    F -- "Đang chạy" --> G["Reader cũ có thể thấy V1; T20 thấy V2"]
    F -- "COMMIT" --> H["Snapshot mới thấy V2; snapshot cũ có thể thấy V1"]
    H --> I["DELETE đánh dấu V2 bằng T30"]
    I --> J{"T30?"}
    J -- "ROLLBACK" --> H
    J -- "COMMIT" --> K["Snapshot mới không thấy hàng; phiên bản vật lý chờ dọn"]
~~~

**T10, T20, T30 chỉ là nhãn biểu diễn.** Không phải XID thực trong database lab.

---

## 9. Khi UPDATE, PostgreSQL có tạo phiên bản mới không?

### 9.1. UPDATE thường không sửa tuple cũ thành giá trị mới tại chỗ

Về cơ chế MVCC, `UPDATE` tạo một tuple version mới và đánh dấu phiên bản cũ bằng thông tin transaction cập nhật. Điều này cho phép snapshot cũ tiếp tục đọc dữ liệu phù hợp của nó.

~~~sql
BEGIN;

SELECT doc_id, title, xmin::text AS xmin, ctid
FROM mvcc_lab.documents
WHERE doc_id = 1;

UPDATE mvcc_lab.documents
SET title = 'Tiêu đề cập nhật',
    version_no = version_no + 1
WHERE doc_id = 1
RETURNING
    doc_id,
    title,
    xmin::text AS xmin,
    ctid;

ROLLBACK;
~~~

Trong transaction, tuple version mới có thể có `xmin` khác bản cũ và `ctid` khác vì nằm ở vị trí vật lý khác. Vị trí thực tế phụ thuộc bố trí heap, dữ liệu và tối ưu hóa; không được mã hóa `(block,offset)` cố định vào ứng dụng.

### 9.2. HOT update

PostgreSQL có tối ưu hóa **HOT — Heap-Only Tuple** khi điều kiện phù hợp, chẳng hạn cột được sửa không làm thay đổi giá trị mà index liên quan cần theo dõi, và còn không gian phù hợp trong page. Khi đó các tuple versions có thể nối thành **HOT chain**, giảm nhu cầu tạo một số index entries mới.

Điều này **không phủ định MVCC**: vẫn có phiên bản tuple mới; HOT chỉ là tối ưu hóa đường truy cập/ghi trên heap và index.

Không phải mọi UPDATE của cột không indexed đều được bảo đảm HOT: không gian page, index biểu thức/partial index, phiên bản và trạng thái table đều có thể ảnh hưởng.

### 9.3. Trạng thái "live" không phải chỉ xem xmax

PostgreSQL có thể coi một version:

- Visible với reader này.
- Invisible với reader khác.
- Đã bị thay thế nhưng còn cần cho snapshot cũ.
- Dead với mọi snapshot có khả năng đọc và đủ điều kiện dọn.

Do đó "một version còn nằm trên page" **không có nghĩa** nó sẽ xuất hiện trong SELECT của bất kỳ reader hiện tại nào.

---

## 10. ctid: vị trí phiên bản không phải ID nghiệp vụ

`ctid` biểu diễn vị trí tuple, thường có dạng:

~~~text
(block_number, item_offset)
~~~

Ví dụ:

~~~sql
SELECT doc_id, ctid
FROM mvcc_lab.documents
ORDER BY doc_id;
~~~

Giá trị `ctid` có thể thay đổi khi:

- Hàng được UPDATE (tạo tuple version mới).
- Bảng được viết lại bởi `VACUUM FULL`, `CLUSTER` hoặc những thao tác rewrite.
- Storage được tổ chức lại trong các tình huống quản trị.

### 10.1. Đừng dùng ctid làm primary key

Sai:

~~~text
API trả về "documentId" = "(0,7)" rồi lưu vĩnh viễn.
~~~

TID đó **không bảo đảm trỏ đến cùng một thực thể sau UPDATE/rewrite**. Sử dụng `doc_id` hoặc khóa nghiệp vụ ổn định.

### 10.2. ctid đôi khi hữu ích trong chẩn đoán

Nếu muốn giải thích hai lần UPDATE có thể tạo các version khác nhau, `ctid` có ích như dữ liệu kỹ thuật trong **lab**. Nhưng một câu `SELECT` bình thường chỉ hiện version visible ở thời điểm đó, không cho phép truy cập toàn bộ lịch sử ctid theo cách tự do.

Không dựa vào `ctid` để tìm "bản trước" của một document đã được update và vacuum nhiều lần.

---

## 11. Hai cửa sổ psql: thấy phiên bản cũ khi UPDATE chưa commit

Mở **hai connection độc lập** (A và B) tới cùng database lab. Kịch bản này kết thúc bằng ROLLBACK để không thay đổi dữ liệu lâu dài.

### 11.1. Phiên A: BEGIN và UPDATE

~~~sql
BEGIN;

UPDATE mvcc_lab.documents
SET title = 'A đang sửa nhưng chưa commit',
    version_no = version_no + 1
WHERE doc_id = 1
RETURNING
    doc_id,
    title,
    version_no,
    xmin::text AS xmin,
    xmax::text AS xmax,
    ctid;

-- Dừng ở đây, chưa COMMIT/ROLLBACK.
~~~

Trong phiên A, SELECT của A nhìn thấy thay đổi chưa commit do **chính A thực hiện**.

### 11.2. Phiên B: đọc bình thường

~~~sql
SELECT
    doc_id,
    title,
    version_no,
    xmin::text AS xmin,
    xmax::text AS xmax,
    ctid
FROM mvcc_lab.documents
WHERE doc_id = 1;
~~~

Ở READ COMMITTED thông thường, B **không thấy title chưa commit của A**. B thấy version cũ của document 1 phù hợp snapshot. Nếu kiểm tra `xmax` của version cũ, đôi khi bạn có thể thấy giá trị liên quan transaction update đang diễn ra, nhưng version vẫn **visible với B**. Không lấy một quan sát cụ thể làm quy tắc luôn đúng cho mọi trường hợp.

### 11.3. Phiên A: ROLLBACK

~~~sql
ROLLBACK;
~~~

### 11.4. Phiên B: đọc lại

~~~sql
SELECT doc_id, title, version_no, xmin::text AS xmin, xmax::text AS xmax
FROM mvcc_lab.documents
WHERE doc_id = 1;
~~~

Hàng vẫn là trạng thái đã commit trước thí nghiệm; phần title từ A bị hủy. Các dấu vết trong heap header có thể vẫn còn cho đến khi engine xử lý, nhưng chúng **không biến thay đổi aborted thành visible**.

### 11.5. Nếu A COMMIT thay cho ROLLBACK?

Một SELECT **mới** của B ở READ COMMITTED thường thấy version mới sau commit. Nhưng một transaction B ở REPEATABLE READ đã lấy snapshot cũ có thể tiếp tục thấy version cũ cho đến khi transaction của B kết thúc. Kịch bản đó được trình bày ở phần tiếp theo.

---

## 12. Snapshot và isolation: READ COMMITTED so với REPEATABLE READ

### 12.1. READ COMMITTED: snapshot theo từng statement

Đây là mức cô lập mặc định của PostgreSQL trong nhiều cài đặt. Mỗi statement nhìn một snapshot phù hợp tại thời điểm bắt đầu câu lệnh.

~~~text
Phiên B (READ COMMITTED)                 Phiên A
----------------------------------      ------------------------
SELECT doc 2  → thấy "Bản B"             BEGIN
                                        UPDATE doc 2
                                        COMMIT
SELECT doc 2  → thấy "Bản B mới"
~~~

Hai SELECT của B có thể thấy hai phiên bản khác nhau vì chúng là **hai statement** riêng. Điều này **không phải dirty read**: B chỉ thấy thay đổi sau khi A đã commit.

### 12.2. REPEATABLE READ: snapshot transaction ổn định

Trong PostgreSQL, REPEATABLE READ dùng một snapshot ổn định sau khi snapshot của transaction được thiết lập. Những SELECT bình thường tiếp theo tiếp tục dùng snapshot đó.

**Phiên B — bắt đầu trước:**

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

-- SELECT đầu xác lập góc nhìn snapshot cho transaction B:
SELECT doc_id, title, version_no,
       xmin::text AS xmin, xmax::text AS xmax
FROM mvcc_lab.documents
WHERE doc_id = 2;

-- Giữ transaction B mở, sang phiên A.
~~~

**Phiên A — cập nhật và commit:**

~~~sql
BEGIN;

UPDATE mvcc_lab.documents
SET title = 'Bản B mới',
    version_no = version_no + 1
WHERE doc_id = 2;

COMMIT;
~~~

**Phiên B — vẫn đang trong transaction REPEATABLE READ:**

~~~sql
SELECT doc_id, title, version_no,
       xmin::text AS xmin, xmax::text AS xmax
FROM mvcc_lab.documents
WHERE doc_id = 2;

COMMIT;

-- Một statement mới sau khi kết thúc transaction:
SELECT doc_id, title, version_no,
       xmin::text AS xmin, xmax::text AS xmax
FROM mvcc_lab.documents
WHERE doc_id = 2;
~~~

Kỳ vọng theo ngữ nghĩa:

- SELECT đầu của B: thấy version đã commit trước khi snapshot B được thiết lập.
- SELECT thứ hai **trong cùng transaction B**: vẫn thấy version cũ mặc dù A đã commit.
- SELECT sau khi B COMMIT, ở một transaction/statement mới: có thể thấy title `Bản B mới`.

> Đây là ví dụ **có COMMIT thực** ở phiên A, làm thay đổi document 2 của lab. Nếu muốn giữ nguyên dữ liệu ban đầu, thực hành trên database/schema lab riêng hoặc có quy trình khôi phục dữ liệu theo chủ đích; không tự quay về hàng gốc bằng cách sửa dữ liệu sản xuất.

### 12.3. Snapshot không phải sao chép toàn bộ bảng

Không phải PostgreSQL tạo một bản copy bảng mới cho mỗi transaction. Snapshot là **thông tin logic** giúp engine quyết định những tuple versions có thể thấy được. Việc giữ nhiều version trong heap và đọc qua MVCC tạo trải nghiệm nhất quán mà không phải copy toàn bộ dữ liệu cho mỗi reader.

### 12.4. REPEATABLE READ không bảo đảm mọi thao tác UPDATE luôn thành công

Nếu transaction REPEATABLE READ cố sửa một hàng đã bị transaction khác thay đổi kể từ snapshot phù hợp, PostgreSQL có thể báo **serialization failure** (ví dụ "could not serialize access due to concurrent update"). Một transaction đã nhìn snapshot cũ không thể tùy ý ghi đè mọi dữ liệu mới mà không đối mặt kiểm soát đồng thời.

### 12.5. SERIALIZABLE

Mức SERIALIZABLE của PostgreSQL còn dùng cơ chế phát hiện tương tác không thể coi như lịch transaction tuần tự, bao gồm **SSI — Serializable Snapshot Isolation**. Một transaction có thể bị hủy bằng `SQLSTATE 40001` ngay cả khi chỉ nhìn vào các cặp xmin/xmax không thấy điều gì trực quan.

Ứng dụng cần **retry toàn bộ transaction** khi lỗi đó có thể retry an toàn, không chỉ lặp lại câu UPDATE cuối. Đây là một lý do nữa không tự viết thuật toán kiểm soát đồng thời dựa vào vài system columns.

---

## 13. Quy tắc visibility: vì sao cần cả XID, status và snapshot?

Để biết một tuple version có xuất hiện trong SELECT không, PostgreSQL phải xét nhiều thông tin đồng thời. Với một bản mô hình đơn giản:

### 13.1. XID tạo tuple (`xmin`)

| Trạng thái transaction tạo phiên bản | Với một reader khác |
|---|---|
| **Aborted** | Tuple do transaction đó tạo không trở thành dữ liệu committed visible |
| **In progress** | Thay đổi chưa commit không visible như dữ liệu committed |
| **Committed trước và visible trong snapshot** | Tuple có thể được xem xét là visible, sau đó xét `xmax` |
| **Committed nhưng không thuộc snapshot hiện tại** | Tuple vẫn chưa visible trong snapshot cũ |

Reader là **chính transaction ghi** có các quy tắc nhìn thấy thay đổi của mình theo command ID; bảng trên nói khái quát về **transaction khác**.

### 13.2. XID kết thúc hoặc khóa (`xmax`)

Nếu `xmin` cho biết phiên bản đã được tạo hợp lệ và snapshot có thể thấy, tiếp tục xem `xmax`:

| Tình huống `xmax` | Ý nghĩa khái quát |
|---|---|
| Không có dấu đánh kết thúc có hiệu lực | Tuple có thể tiếp tục visible |
| Transaction UPDATE/DELETE đã **aborted** | Thay đổi không làm tuple cũ biến mất |
| Transaction UPDATE/DELETE vẫn **in progress** | Reader khác thường vẫn có thể thấy tuple cũ |
| Transaction UPDATE/DELETE **committed và visible với snapshot** | Tuple cũ không còn visible với snapshot đó |
| `xmax` phục vụ **row locking** | Không coi là đã xóa tuple |
| Trường chứa **MultiXactId** | Phải xét nhóm locker/updater cùng các flags, không đọc như một XID thông thường |

Quy tắc thực tế của engine còn chứa nhiều chi tiết về command ID, infomask bits, subtransaction, speculative insertion và loại snapshot. Bảng chỉ giúp hình dung **tại sao không thể viết `xmax=0` làm định nghĩa "dòng còn sống"**.

### 13.3. Một tuple có thể visible với A nhưng invisible với B

Giả sử V1 tạo bởi T10 đã commit. T20 cập nhật thành V2, sau đó T20 commit. 

~~~text
Snapshot S_old được tạo trước commit T20:
  V1 → visible
  V2 → invisible

Snapshot S_new được tạo sau commit T20:
  V1 → invisible
  V2 → visible
~~~

Cùng một page có thể chứa **cả hai phiên bản**; snapshot quyết định phiên bản nào thuộc kết quả SELECT.

### 13.4. SELECT bình thường không trả mọi phiên bản vật lý

~~~sql
SELECT doc_id, title, xmin::text, xmax::text, ctid
FROM mvcc_lab.documents
WHERE doc_id = 2;
~~~

Lệnh này chỉ trả phiên bản visible theo snapshot của SELECT. Nó **không phải** câu lệnh "liệt kê tất cả lịch sử update của document 2" dù đã SELECT xmin/xmax.

### 13.5. PostgreSQL phải phối hợp status transaction

Nếu chỉ xét `xmin=741` và `xmax=780` mà không biết 780 **committed, aborted, in progress, lock-only hay MultiXact**, bạn chưa thể xác định chính xác trạng thái phiên bản. Hệ thống có các cơ chế lưu/truy xuất trạng thái commit và header flags để đưa ra kết luận.

---

## 14. pg_xact, tuple header và hint bits

### 14.1. pg_xact lưu trạng thái transaction

PostgreSQL sử dụng cơ sở thông tin trạng thái commit/abort của transaction, thường được nhắc tới với tên **pg_xact** (trong các tài liệu cũ có thể gặp tên `pg_clog`).

Khi cần kiểm tra visibility cho một tuple, engine có thể cần biết transaction XID liên quan đã:

- Commit.
- Abort.
- Còn đang hoạt động.

Không đọc hoặc sửa trực tiếp các file nội bộ dưới data directory để "kiểm tra" trạng thái transaction trong ứng dụng. Đây là chi tiết storage/engine được PostgreSQL quản lý.

### 14.2. Hint bits giúp tránh tra cứu lặp

Sau khi trạng thái một transaction được xác định, PostgreSQL có thể cập nhật **hint bits** trong tuple header để những lần kiểm tra sau biết nhanh hơn rằng transaction đã commit/abort.

Ví dụ conceptual:

~~~text
Tuple header:
  xmin   = T10
  xmax   = T20
  flags  = "xmin đã commit", "xmax lock-only/invalid/..."

Snapshot:
  tập transaction visible ở góc nhìn reader

pg_xact / state metadata:
  trạng thái transaction khi cần tra cứu
~~~

Hint bits là **cơ chế tối ưu hóa nội bộ**, không phải API nghiệp vụ.

### 14.3. Vì sao không đủ chỉ SELECT xmin/xmax?

Lệnh:

~~~sql
SELECT doc_id, xmin::text, xmax::text
FROM mvcc_lab.documents;
~~~

không lộ ra đầy đủ tất cả flags trong tuple header. Bạn có thể quan sát con số của `xmax` nhưng không biết chỉ từ đó nó dùng cho **lock-only** hay một **delete đã commit**. Thậm chí phiên bản đã bị xóa thực sự có thể **không xuất hiện trong kết quả** để bạn SELECT được.

### 14.4. Xem page nội bộ có cần thiết không?

Các extension như `pageinspect` có thể hỗ trợ phân tích tuple header ở mức thấp trong môi trường điều tra phù hợp, thường cần quyền cao và hiểu biết sâu về page format. Bài này **không yêu cầu** cài extension hay truy cập raw page; chỉ dùng SQL và system columns đã có để hiểu cơ chế.

Không chạy các truy vấn page-level trên production chỉ vì muốn "đọc xmax"; cách phân tích đó dễ nhầm tuple offset, HOT chain, vacuum state và quyền truy cập.

---

## 15. Row lock và MultiXactId

### 15.1. Khóa hàng khác với xóa hàng

~~~sql
BEGIN;

SELECT doc_id, title
FROM mvcc_lab.documents
WHERE doc_id = 1
FOR UPDATE;

ROLLBACK;
~~~

`SELECT FOR UPDATE` khóa một hàng để phối hợp với transaction ghi đồng thời. Bản thân nó **không đổi title**, không tạo một lần DELETE nghiệp vụ, cũng không buộc một reader SELECT thông thường thấy "đã xóa".

Một row lock có thể để lại thông tin trong tuple header, liên quan `xmax` và các flag. Vì vậy việc nhìn thấy xmax nonzero từ một tuple visible có thể phản ánh **lock**, không phải một commit làm biến mất row.

### 15.2. Nhiều transaction cùng khóa

Một số loại row lock tương thích nhau (ví dụ các reader yêu cầu khóa chia sẻ phù hợp). PostgreSQL có thể cần ghi nhận **nhiều transaction đang khóa một tuple**.

**MultiXactId** là cơ chế biểu diễn một nhóm transaction tham gia trạng thái khóa/cập nhật tương ứng. Trong những hoàn cảnh đó, giá trị trường `xmax` không thể được diễn giải đơn thuần là "ID của một transaction xóa".

### 15.3. Một cách tưởng tượng sai

~~~text
Nếu xmax = 881:
    "Transaction 881 đã DELETE row"
~~~

Suy luận này có thể sai vì:

- 881 có thể là transaction UPDATE chưa commit.
- 881 có thể đã rollback.
- Giá trị xmax có thể phục vụ row lock.
- Trường có thể chứa MultiXactId theo kiểu diễn giải qua tuple flags.
- Một snapshot cũ vẫn có thể thấy phiên bản cũ sau commit xóa/update.

### 15.4. Row lock ảnh hưởng đồng thời

Hai phiên cùng muốn `UPDATE` một hàng có thể phải chờ nhau. PostgreSQL phối hợp row locks và MVCC:

- **MVCC** quyết định các phiên bản visible.
- **Locking** quyết định khi nào một thao tác ghi/khóa phải chờ hoặc xung đột.

Không coi "PostgreSQL có MVCC" là đồng nghĩa với "không bao giờ có lock wait, deadlock hay serialization failure".

### 15.5. Câu lệnh chờ khóa có timeout

Trong lab:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

SELECT doc_id
FROM mvcc_lab.documents
WHERE doc_id = 1
FOR UPDATE;

ROLLBACK;
~~~

Đây là cách đặt giới hạn chờ khóa cục bộ cho một transaction. Nếu query gặp lỗi lock timeout trong transaction, cần rollback hoặc xử lý theo savepoint; không để kết nối tiếp tục ở trạng thái aborted.

---

## 16. UPDATE không tạo "bản ghi lịch sử" có thể truy vấn mãi mãi

Một ngộ nhận rất phổ biến:

> PostgreSQL lưu nhiều version do MVCC, vậy có thể SELECT những version cũ để xây tính năng xem lịch sử?

**Không thể suy ra điều đó.** Các version cũ tồn tại nhằm phục vụ **snapshot consistency** và có thể được dọn khi không còn cần thiết; chúng **không phải lịch sử kinh doanh có thời hạn lưu trữ được bảo đảm**.

### 16.1. Ví dụ nghiệp vụ

~~~text
09:00  document 1: status=draft
09:10  UPDATE status=review, COMMIT
09:30  UPDATE status=published, COMMIT
~~~

Một SELECT mới lúc 09:31 thường thấy `status=published`. PostgreSQL có thể còn giữ tuple versions cũ trên disk tạm thời, nhưng:

- SELECT thông thường không trả chúng.
- VACUUM có thể dọn khi đủ điều kiện.
- Bạn không có API truy vấn "lấy bản 09:00" chỉ từ `xmin` và `xmax`.
- XID không mã hóa timestamp đủ để khôi phục lịch sử.

### 16.2. Muốn audit, phải thiết kế audit

Một bảng lịch sử minh họa:

~~~sql
CREATE TABLE mvcc_lab.document_history (
    history_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    doc_id BIGINT NOT NULL,
    old_title TEXT,
    old_status TEXT,
    new_title TEXT,
    new_status TEXT,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    changed_by TEXT,
    reason TEXT
);
~~~

Đây mới chỉ là **schema**. Để lịch sử thực sự đầy đủ cần trigger/application logic ghi đúng ở mỗi update, actor, bảo mật, retention, replay và logic transaction. Không mặc định bảng history tự được ghi chỉ vì CREATE TABLE đã tồn tại.

### 16.3. Backup/PITR không phải SELECT version trực tiếp

PostgreSQL có thể phục hồi theo thời điểm khi hệ thống được cấu hình backup/WAL archiving/PITR phù hợp. Đó là cơ chế **recovery**, không phải việc SELECT các phiên bản MVCC cũ ngay trong bảng đang chạy.

---

## 17. VACUUM: khi nào phiên bản chết được thu hồi?

### 17.1. Vì sao cần VACUUM?

`UPDATE` tạo version mới và `DELETE` đánh dấu version cũ. Sau thời gian dài:

- Nhiều tuple versions không còn visible với transaction nào.
- Những phiên bản chết chiếm không gian trong heap/index.
- Nếu không dọn, đọc/ghi có thể chậm hơn, gây **table/index bloat**.

**VACUUM** giúp thu hồi và đánh dấu không gian có thể dùng lại theo trạng thái và horizon của các transaction còn sống.

### 17.2. "Đã COMMIT DELETE" không đồng nghĩa "bytes được xóa khỏi file ngay"

~~~text
T10 INSERT V1, COMMIT
T20 UPDATE V1→V2, COMMIT
T30 DELETE V2, COMMIT

SELECT ở snapshot mới: không thấy hàng
Heap file: có thể vẫn còn phiên bản vật lý cũ
VACUUM: xét có snapshot nào còn cần version không
Nếu đủ điều kiện: có thể thu hồi/đánh dấu tái sử dụng
~~~

Khi tất cả snapshot có khả năng cần một dead tuple đã qua đi, engine có thể xử lý các phiên bản chết. Đây không phải xóa tức thì tất cả byte dữ liệu trong mọi file khi COMMIT.

### 17.3. Dead với một snapshot chưa chắc removable với mọi snapshot

Snapshot mới sau UPDATE COMMIT có thể không thấy V1 nữa, nhưng một transaction REPEATABLE READ bắt đầu trước đó vẫn có thể thấy V1. Vì vậy VACUUM **không được thu hồi V1 quá sớm**.

Phải phân biệt:

1. **Invisible đối với một reader.**
2. **Dead đối với mọi snapshot còn có thể cần tới phiên bản.**
3. **Đã được VACUUM xử lý để tái sử dụng không gian.**

Đây là ba trạng thái/khái niệm khác nhau.

### 17.4. Regular VACUUM và VACUUM FULL

| Lệnh | Mục đích chính | Điểm vận hành |
|---|---|---|
| `VACUUM` | Dọn dead tuples, quản lý visibility/free space và frozen XIDs | Thường có thể hoạt động cùng workload bình thường, nhưng vẫn tốn tài nguyên |
| Autovacuum | Worker nền xử lý bảng đủ điều kiện | Cần giám sát, không nên tắt tùy tiện |
| `VACUUM FULL` | Viết lại bảng để lấy lại nhiều dung lượng vật lý | Cần khóa mạnh, có thể gây downtime, thay đổi vị trí ctid |

Không dùng `VACUUM FULL` trên production chỉ để "reset xmin/xmax" hoặc quan sát ctid. Mục tiêu của nó không phải làm công cụ học trực tiếp về lịch sử MVCC.

### 17.5. Bản ghi đã rollback cũng cần xử lý vật lý

Một INSERT sau đó ROLLBACK có thể để lại tuple trên heap mà engine biết là không visible. Một UPDATE đã rollback có thể để lại version mới không hợp lệ. Các phiên bản/không gian liên quan có thể được VACUUM hoặc cơ chế cleanup xử lý về sau.

**Rollback về ngữ nghĩa** không nhất thiết xóa mọi thay đổi vật lý ngay lập tức.

---

## 18. Freezing và XID wraparound

### 18.1. Vì sao 32-bit XID cần cơ chế chống wraparound?

Transaction ID truyền thống trong tuple header có miền 32-bit hữu hạn. Sau rất nhiều transaction, vòng số lặp lại. Nếu không có cơ chế phân biệt "cũ" và "mới", việc so thứ tự tuổi XID có thể nhầm một transaction rất cũ với một transaction mới.

PostgreSQL sử dụng **tuổi XID, freeze và bảo trì** để bảo đảm những tuple đủ cũ được xem là thuộc về transaction committed trong quá khứ theo cách an toàn, đồng thời tránh các tình huống wraparound nguy hiểm.

### 18.2. Frozen tuple không có nghĩa raw xmin luôn bằng 2

Trong các mô tả/công nghệ cũ, bạn có thể gặp ký hiệu đặc biệt **FrozenTransactionId**. Nhưng trên nhiều phiên bản PostgreSQL hiện đại, freeze có thể được biểu diễn bằng **flags** trong tuple header, còn giá trị raw `xmin` quan sát được không nhất thiết bị ghi lại thành đúng một con số đặc biệt.

Vì vậy không kết luận:

~~~text
xmin::text <> '2'  → tuple chắc chắn chưa frozen
~~~

Đây là một ngộ nhận. Trạng thái frozen là quyết định của cơ chế storage/visibility, không phải quy ước application chỉ dựa trên text của `xmin`.

### 18.3. Một transaction rất cũ không đồng nghĩa một row rất cũ

Thứ tự XID và tính toán tuổi dùng cơ chế nội bộ có wraparound semantics. Không tính:

~~~text
tuổi nghiệp vụ của hàng = current_xid - xmin
~~~

và coi đó là "số giây"/"số ngày". XID không phải timestamp và có thể bị freeze, modulo, khác epoch hoặc không được cấp ngay khi BEGIN.

### 18.4. Quan sát tuổi XID ở mức database

Trong môi trường có quyền đọc thống kê:

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age,
    datfrozenxid
FROM pg_database
ORDER BY age(datfrozenxid) DESC;
~~~

Đây là chỉ báo về khoảng cách tuổi XID liên quan bảo trì database, **không phải** bảng thời gian tạo dữ liệu.

### 18.5. Quan sát tuổi XID của relation

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    age(c.relfrozenxid) AS rel_xid_age
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm')
  AND n.nspname = 'mvcc_lab'
ORDER BY rel_xid_age DESC;
~~~

`relfrozenxid` cho biết horizon freezing liên quan relation. Không sửa trực tiếp giá trị catalog để "làm giảm tuổi XID"; cần dùng autovacuum/VACUUM và các quy trình quản trị được PostgreSQL hỗ trợ.

### 18.6. MultiXact cũng có vòng đời và freezing riêng

Khi nhiều transaction khóa cùng tuple, MultiXact IDs cũng cần quản lý tuổi và wraparound. PostgreSQL có cơ chế autovacuum/freeze để xử lý cả MultiXact. Không cố diễn giải mọi giá trị `xmax` như một XID duy nhất và bỏ qua tuổi MultiXact.

### 18.7. Hậu quả khi bỏ qua autovacuum

Nếu tuổi XID tăng đến các ngưỡng nguy hiểm mà không được freeze kịp, PostgreSQL có cơ chế bảo vệ và cảnh báo, thậm chí có thể từ chối các giao dịch ghi để tránh mất khả năng phân biệt phiên bản. Vì vậy **không tắt autovacuum tùy tiện** trong database nhiều ghi.

---

## 19. Transaction dài và global xmin horizon

### 19.1. Vì sao transaction đọc dài có thể gây bloat?

Một transaction REPEATABLE READ giữ snapshot cũ. Trong khi đó:

~~~text
Reader R: BEGIN REPEATABLE READ ──────────(đọc rất lâu)────── COMMIT
Writer W: UPDATE nhiều hàng → COMMIT
Writer X: UPDATE tiếp     → COMMIT
VACUUM:   không thể dọn những version R còn có thể đọc
~~~

Những phiên bản cũ mà R vẫn có quyền thấy phải được giữ đủ lâu. Nếu R tồn tại quá lâu, dead tuples có thể tích lũy và gây bloat. Một số nguồn giữ horizon khác gồm replication slot, prepared transaction hoặc cơ chế đồng bộ/backup tùy cấu hình.

### 19.2. backend_xmin khác tuple xmin

Trong `pg_stat_activity`:

- `backend_xid` là XID hiện được gắn với backend (nếu có).
- `backend_xmin` biểu thị horizon XID mà backend đang giữ cho snapshot/việc nhìn thấy transaction.

Điều này **không có nghĩa** `backend_xmin` là "xmin nhỏ nhất trong các row mà query của backend đọc".

### 19.3. Quan sát transaction mở

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    backend_xid::text AS backend_xid,
    backend_xmin::text AS backend_xmin,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Một số cột/thông tin chi tiết của session khác cần quyền phù hợp. Không kết luận một backend chậm phải bị terminate chỉ từ số tuổi transaction; phải xác minh owner và ảnh hưởng.

### 19.4. Idle in transaction

Một session:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT * FROM mvcc_lab.documents;
-- Ứng dụng quên COMMIT/ROLLBACK trong nhiều phút.
~~~

có thể trở thành `idle in transaction`. Với snapshot còn giữ, nó có thể hạn chế dọn phiên bản cũ. Kết thúc transaction khi xong việc:

~~~sql
ROLLBACK;
~~~

Với READ COMMITTED, snapshot của một SELECT thông thường không nhất thiết bị giữ nguyên giữa các statement; không áp cùng một kết luận về horizon cho **mọi** session idle in transaction. Dù vậy, transaction mở lâu vẫn có thể giữ khóa/tài nguyên và là vấn đề vận hành.

### 19.5. Các nguồn giữ horizon không chỉ là backend app

Trong điều tra bloat và XID tuổi cao, DBA còn cần xem:

- Replication slots có `xmin` hoặc `catalog_xmin` liên quan.
- Prepared transactions chưa được commit/rollback đầy đủ.
- Standby feedback và việc replica giữ snapshot.
- Autovacuum, freeze progress và retention.

Không xóa replication slot hoặc prepared transaction tùy ý vì đó có thể làm mất khả năng đồng bộ hoặc phá giao dịch nghiệp vụ.

---

## 20. Chẩn đoán bằng SQL mà không can thiệp storage

### 20.1. Xem phiên bản visible và thông tin hệ thống

~~~sql
SELECT
    doc_id,
    title,
    status,
    version_no,
    xmin::text AS xmin_text,
    xmax::text AS xmax_text,
    ctid,
    tableoid::regclass AS source_relation
FROM mvcc_lab.documents
ORDER BY doc_id;
~~~

Cách đọc:

- `doc_id`: khóa nghiệp vụ do schema định nghĩa.
- `xmin`: gợi ý XID tạo **version visible**.
- `xmax`: có thể liên quan update/delete/lock; không dùng để phân loại trực tiếp.
- `ctid`: địa chỉ vật lý của **version visible**.

### 20.2. Xem transaction hiện tại đã có XID chưa

~~~sql
BEGIN;

SELECT
    pg_current_xact_id_if_assigned() AS xid_before_write;

UPDATE mvcc_lab.documents
SET title = title
WHERE doc_id = 1;

SELECT
    pg_current_xact_id_if_assigned() AS xid_after_write;

ROLLBACK;
~~~

Lệnh `UPDATE title = title` có thể vẫn tạo phiên bản mới theo ngữ nghĩa UPDATE ngay cả khi giá trị title không đổi. Nó **không phải** thao tác "chỉ kiểm tra không ghi". Vì có ROLLBACK, thay đổi không được giữ lại trong lab.

Nếu bạn chỉ muốn quan sát mà không tạo XID mới, không gọi `pg_current_xact_id()` trong một giao dịch đọc đơn thuần vì hàm đó có thể cấp XID.

### 20.3. Xem snapshot

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

WITH s AS (
    SELECT pg_current_snapshot() AS snap
)
SELECT
    snap,
    pg_snapshot_xmin(snap) AS snapshot_xmin,
    pg_snapshot_xmax(snap) AS snapshot_xmax
FROM s;

ROLLBACK;
~~~

Đây là **snapshot horizon của transaction**, không phải xmin/xmax tuple. Những hàm này hỗ trợ quan sát cơ chế, không thay thế một engine giải thích hết MVCC internals.

### 20.4. Kiểm tra trạng thái backend khác

~~~sql
SELECT
    pid,
    state,
    xact_start,
    backend_xid,
    backend_xmin,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST, pid;
~~~

Với quyền phù hợp, có thể phát hiện session có transaction dài hoặc đang chờ khóa. Không xem các giá trị này như lịch sử thay đổi từng document.

### 20.5. Các con số không ổn định giữa lần chạy

XID, snapshot bounds, ctid và thông tin khóa phụ thuộc hoạt động của database, transaction khác và quá trình vacuum. Trong bài tập, hãy **giải thích mối quan hệ**, không viết test cứng kỳ vọng `xmin=741` hay `ctid=(0,1)`.

---

## 21. Optimistic locking: nên dùng version_no thay cho xmin

### 21.1. Lost update ở tầng ứng dụng

Giả sử:

~~~text
Client A đọc title hiện tại, version_no=1.
Client B cũng đọc title hiện tại, version_no=1.
Client A lưu "Nội dung A", version_no tăng lên 2.
Client B lưu "Nội dung B" trên dữ liệu cũ mà không kiểm tra version.
~~~

Nếu ứng dụng viết đè mà không kiểm soát, thay đổi của A có thể bị mất từ góc nhìn nghiệp vụ.

### 21.2. Conditional update bằng version_no

~~~sql
UPDATE mvcc_lab.documents
SET
    title = 'Nội dung từ client',
    version_no = version_no + 1,
    updated_at = now()
WHERE doc_id = 1
  AND version_no = 1
RETURNING doc_id, title, version_no;
~~~

**Chỉ chạy trên lab** khi bạn muốn thật sự cập nhật. Ý nghĩa:

- Nếu bản hiện tại có `version_no=1`, update có thể thành công và tăng thành 2.
- Nếu client đã cũ, `UPDATE 0` cho biết version token **không còn khớp**, ứng dụng trả conflict và yêu cầu đọc lại.
- Trong PostgreSQL, UPDATE với điều kiện phiên bản được thực hiện cùng lúc với việc lấy lock thích hợp cho row, tránh kiểu kiểm tra version ở client rồi ghi độc lập.

### 21.3. Version tường minh có nhiều lợi ích

- Phù hợp API/ETag, có thể nằm trong payload giao diện.
- Ổn định về **ý nghĩa ứng dụng**, không cần hiểu modulo XID.
- Không bị người viết code nhầm với header MVCC/row lock.
- Có thể lưu cùng audit/event history theo chính sách nghiệp vụ.

Ứng dụng vẫn cần transaction, kiểm soát UNIQUE/constraints và retry nếu có cạnh tranh; `version_no` không thay thế mọi bảo đảm của SERIALIZABLE hoặc thiết kế lịch sử.

### 21.4. Có thể dùng xmin làm version token không?

Trong một số công cụ và ORM, `xmin` được dùng làm **tín hiệu phát hiện xung đột ngắn hạn** đối với một phiên bản row cụ thể. Nhưng không nên coi nó là API ổn định dài hạn hoặc "version number" cấp nghiệp vụ vì:

- Giá trị `xid` có wraparound/epoch semantics.
- Hàng bị rewrite/freeze và các thay đổi storage có thể ảnh hưởng ngữ cảnh.
- `xmin` không phải timestamp hay counter riêng cho từng entity.
- Sử dụng ngoài PostgreSQL hoặc qua replication/sao chép có thể không giữ đúng semantics bạn mong đợi.

Nếu chọn chiến lược đó, phải dựa vào hợp đồng hỗ trợ của driver/ORM, phạm vi và phiên bản PostgreSQL đã kiểm chứng. Với thiết kế mới cần tính rõ nghĩa lâu dài, **cột version_no riêng thường dễ quản lý hơn**.

---

## 22. Những ngộ nhận về xmin/xmax cần tránh

### 22.1. "xmin là thời gian tạo hàng"

Sai. XID không phải timestamp; sau UPDATE, phiên bản hiện tại có xmin của transaction cập nhật, không phải transaction INSERT gốc.

### 22.2. "xmax = 0 tức là row còn sống, khác 0 tức là đã xóa"

Sai. Xmax còn có thể lưu lock, MultiXact, XID in-progress hoặc aborted. Visibility phụ thuộc commit status, flags và snapshot.

### 22.3. "Mọi version cũ đều có thể SELECT"

Sai. SELECT bình thường chỉ thấy phiên bản hợp lệ theo snapshot. Phiên bản cũ có thể đã được VACUUM dọn.

### 22.4. "ctid là ID tốt hơn primary key"

Sai. CTID là địa chỉ vật lý của tuple version, có thể thay đổi sau UPDATE/rewrite.

### 22.5. "XID lớn hơn chắc chắn commit sau"

Sai. Thứ tự cấp XID không phải thứ tự COMMIT và còn chịu wraparound/epoch.

### 22.6. "Một transaction BEGIN là được cấp ngay permanent XID"

Không nhất thiết. Transaction đọc có thể chưa được gán XID thường; một số hàm như `pg_current_xact_id()` có thể chủ động yêu cầu cấp.

### 22.7. "VACUUM chỉ dọn hàng DELETE"

Sai. Các phiên bản cũ do UPDATE, bản ghi từ transaction abort và việc freeze tuổi XID đều liên quan bảo trì.

### 22.8. "VACUUM FULL an toàn để thử bất kỳ lúc nào"

Sai. VACUUM FULL có thể lấy khóa mạnh, viết lại bảng và ảnh hưởng hoạt động. Không dùng tùy ý trên production.

### 22.9. "PostgreSQL có MVCC nên không có lock waits"

Sai. UPDATE/DELETE/SELECT FOR UPDATE và DDL vẫn có thể chờ lock hoặc deadlock. MVCC và locking bổ sung cho nhau.

### 22.10. "READ COMMITTED giữ một snapshot từ BEGIN đến COMMIT"

Sai trong PostgreSQL. READ COMMITTED thường lấy snapshot theo statement; REPEATABLE READ dùng snapshot ổn định sau khi được thiết lập.

### 22.11. "Một transaction aborted vẫn có thể được commit bằng lệnh COMMIT"

Không. Sau lỗi SQL làm transaction aborted, cần rollback hoặc rollback về savepoint hợp lệ. COMMIT của transaction đã aborted không ép thay đổi lỗi thành dữ liệu committed.

### 22.12. "xmin/xmax có thể thay một audit trail"

Sai. Chúng phục vụ MVCC và có thể không biểu diễn lịch sử nghiệp vụ, actor, lý do, timestamp, phiên bản cũ đã bị vacuum hoặc các thay đổi ngoài DB.

---

## 23. Bảng tra cứu nhanh

| Muốn biết | Công cụ/câu SQL phù hợp | Lưu ý |
|---|---|---|
| Phiên bản visible được tạo bởi transaction nào? | `SELECT xmin FROM table` | XID của **version**, không phải lịch sử tạo entity |
| Phiên bản có trường kết thúc/lock nào? | `SELECT xmax FROM table` | Không tự suy ra deleted |
| Phiên bản đang ở đâu trong heap? | `SELECT ctid FROM table` | Có thể thay đổi |
| Transaction hiện đã được cấp XID chưa? | `pg_current_xact_id_if_assigned()` | Có thể NULL |
| XID đầy đủ của transaction hiện tại? | `pg_current_xact_id()` | Có thể khiến XID được cấp |
| Snapshot hiện tại? | `pg_current_snapshot()` | Không phải danh sách lịch sử row |
| Ranh giới snapshot? | `pg_snapshot_xmin(snap)`, `pg_snapshot_xmax(snap)` | Tên trùng với tuple fields nhưng khác ý nghĩa |
| Backend có horizon nào? | `pg_stat_activity.backend_xmin` | Không phải xmin của một hàng |
| Transaction còn mở bao lâu? | `pg_stat_activity.xact_start` | Cần quyền xem session |
| Khi nào version cũ được dọn? | VACUUM và visibility horizons | Không dọn nếu vẫn cần cho snapshot cũ |
| Tuổi XID database | `age(datfrozenxid)` | Chỉ số bảo trì, không phải tuổi tài liệu |
| Thời điểm tạo tài liệu | `created_at` do ứng dụng quản lý | Không suy từ xmin |
| Lịch sử cập nhật | Bảng audit/history hoặc event log | Không suy từ các dead tuples |
| Phát hiện client sửa dựa trên version cũ | `WHERE version_no = :expected` | Nên dùng token version riêng |

### 23.1. Sơ đồ những tầng tham gia quyết định visibility

~~~mermaid
flowchart TD
    A["Reader gửi SELECT"] --> B["Snapshot của reader"]
    A --> C["Tuple version trong heap"]
    C --> D["xmin: transaction tạo version"]
    C --> E["xmax: kết thúc/lock/MultiXact"]
    C --> F["Tuple header flags, command metadata"]
    D --> G["Trạng thái XID / pg_xact khi cần"]
    E --> G
    B --> H["Bộ quy tắc MVCC của PostgreSQL"]
    F --> H
    G --> H
    H --> I{"Tuple visible cho snapshot này?"}
    I -- "Có" --> J["Có thể tham gia kết quả SELECT"]
    I -- "Không" --> K["Không xuất hiện trong SELECT thường"]
~~~

**Không thay sơ đồ này bằng `WHERE xmax = 0`**. PostgreSQL đã có engine xử lý visibility; tác vụ ứng dụng chỉ cần đọc những rows mà một SQL statement hợp lệ cung cấp theo snapshot của mình.

---

## 24. Bài tập thực hành

Các bài dùng `mvcc_lab.documents` của phần 5, trừ khi nêu rõ hai phiên hoặc tình huống giả định. **Để thí nghiệm tái lập**, ưu tiên các thao tác kết thúc bằng `ROLLBACK`. Bài nào COMMIT sẽ thay đổi dữ liệu lab và có thể làm giá trị version_no về sau không còn bằng 1.

### Bài 1 — Nhận diện các trường hệ thống

Viết SQL hiện `doc_id`, `title`, `xmin`, `xmax`, `ctid` và `tableoid` của ba tài liệu. Vì sao `SELECT *` không tự hiện `xmin`?

### Bài 2 — Một INSERT, nhiều hàng

Nếu cả ba document được INSERT trong một transaction, vì sao chúng có thể mang **cùng xmin** dù có ba doc_id khác nhau?

### Bài 3 — Kiểm tra XID được cấp khi nào

Viết transaction bắt đầu bằng `pg_current_xact_id_if_assigned()`, thực hiện một UPDATE tạm, gọi lại hàm và ROLLBACK. Vì sao không nên luôn dùng `pg_current_xact_id()` ở bước đầu khi chỉ muốn quan sát?

### Bài 4 — INSERT rồi ROLLBACK

INSERT document 99 trong transaction, SELECT `xmin/ctid`, ROLLBACK rồi SELECT lại. Hàng 99 có còn visible không? Dữ liệu vật lý có nhất thiết bị xóa khỏi heap ngay?

### Bài 5 — UPDATE là một phiên bản mới

Viết transaction update title của document 1, trả `xmin` và `ctid` từ `RETURNING`, rồi rollback. Vì sao `xmin` sau update không còn mang nghĩa transaction INSERT gốc?

### Bài 6 — DELETE và xmax

DELETE document 3 nhưng chưa commit. Một phiên B ở READ COMMITTED có thể đọc document 3 không? Điều gì xảy ra nếu A ROLLBACK?

### Bài 7 — Hai phiên đồng thời

Phiên A BEGIN và UPDATE document 1, chưa commit. Phiên B SELECT bình thường. B sẽ thấy bản title nào? Sau A COMMIT, một statement mới của B ở READ COMMITTED thường thấy gì?

### Bài 8 — REPEATABLE READ

Phiên B thiết lập snapshot REPEATABLE READ, sau đó A UPDATE document 2 rồi COMMIT. B SELECT lần hai trong transaction sẽ thấy bản nào? Vì sao?

### Bài 9 — Snapshot xmin và tuple xmin

Phân biệt `pg_snapshot_xmin(pg_current_snapshot())` với `SELECT xmin FROM mvcc_lab.documents`. Chúng dùng chung từ "xmin" nhưng có phải một thông tin không?

### Bài 10 — xmax khác 0

Cho một tuple visible có `xmin=100` và `xmax=101`. Có đủ căn cứ nói "row đã bị DELETE" không? Nêu ít nhất bốn khả năng cần xem xét.

### Bài 11 — SELECT FOR UPDATE

Viết một transaction khóa document 1 bằng `SELECT FOR UPDATE` rồi rollback. Khóa có làm title bị xóa không? Vì sao nó có thể liên quan tới xmax?

### Bài 12 — MultiXact

Một tuple đang có nhiều transaction cùng giữ những row locks tương thích. Vì sao trường xmax không thể luôn đọc như "một transaction xóa hàng"?

### Bài 13 — ctid

Vì sao không dùng `ctid` làm document ID trong URL hoặc API? Nêu ít nhất hai thao tác có thể làm vị trí này thay đổi.

### Bài 14 — HOT

Nếu UPDATE một cột không ảnh hưởng đến index, PostgreSQL **có thể** tạo HOT update. Có phải như vậy là nó không tạo tuple version mới không?

### Bài 15 — Tuple state theo snapshot

V1 được tạo và commit bởi T10. T20 tạo V2 thay V1, rồi commit. Snapshot S_old có trước commit T20; S_new có sau. Mỗi snapshot có thể thấy version nào?

### Bài 16 — Lỗi sau khi COMMIT?

Hai transaction được cấp XID theo thứ tự T30 rồi T31, nhưng T31 COMMIT trước T30. Có thể xác định thứ tự COMMIT chỉ bằng phép so số XID không?

### Bài 17 — pg_xact và hint bits

Vì sao PostgreSQL cần thông tin trạng thái transaction ngoài con số xmin/xmax, và hint bits giúp gì?

### Bài 18 — Transaction bị aborted

Transaction INSERT một tuple rồi ROLLBACK. Vì sao tuple đó không visible cho snapshot mới dù đã có thể được ghi vật lý vào heap?

### Bài 19 — VACUUM

Một phiên REPEATABLE READ giữ snapshot cũ trong 30 phút, trong khi phiên khác UPDATE hàng liên tục và COMMIT. Vì sao VACUUM có thể chưa được thu hồi một số phiên bản cũ?

### Bài 20 — XID wraparound

Vì sao `xmin` không thể dùng như một số tăng mãi mãi? "Raw xmin không bằng FrozenTransactionId" có đủ kết luận row chưa frozen không?

### Bài 21 — Tuổi XID

Viết SQL tìm `age(datfrozenxid)` của các database. Vì sao giá trị đó không phải "số ngày tuổi" của dữ liệu?

### Bài 22 — Idle in transaction

Viết SQL kiểm tra PID, state, xact_start, backend_xmin. Giải thích khác biệt giữa backend_xmin và xmin của một tuple.

### Bài 23 — Chẩn đoán lịch sử

Một team yêu cầu xem mọi bản sửa title trong 90 ngày chỉ bằng `SELECT xmin,xmax,ctid`. Vì sao yêu cầu đó không thể được đảm bảo qua MVCC thông thường? Đề xuất giải pháp lưu lịch sử.

### Bài 24 — Optimistic locking

Client A và B cùng đọc `version_no=1`. A update và tăng version lên 2. Viết câu UPDATE của B chỉ được áp dụng khi version vẫn bằng 1. Nếu UPDATE 0, xử lý ra sao?

### Bài 25 — UPDATE không đổi dữ liệu

Câu `UPDATE ... SET title=title` có phải là câu chỉ đọc, không cấp XID và không tạo phiên bản mới không? Giải thích.

### Bài 26 — Snapshot và SQL mới

Một bảng có tuple V1 bị thay bằng V2 sau COMMIT. Vì sao SELECT thường trên bảng trong transaction mới có thể chỉ trả V2, còn V1 vẫn có thể nằm trong heap cho đến VACUUM?

### Bài 27 — SERIALIZABLE

Vì sao dùng `SERIALIZABLE` không có nghĩa mọi transaction đều COMMIT thành công? Ứng dụng nên làm gì khi nhận `SQLSTATE 40001`?

### Bài 28 — Tổng hợp thiết kế

Một ứng dụng soạn thảo tài liệu muốn: đọc không bẩn, không mất cập nhật client cũ, có audit chỉnh sửa, quan sát transaction dài, không coi xmax nonzero là DELETE. Hãy đề xuất kiến trúc dữ liệu và quy trình xử lý phù hợp.

---

## 25. Gợi ý lời giải

### Bài 1

~~~sql
SELECT
    doc_id, title,
    xmin::text AS xmin_text,
    xmax::text AS xmax_text,
    ctid,
    tableoid::regclass AS relation_name
FROM mvcc_lab.documents
ORDER BY doc_id;
~~~

System columns không được tự mở rộng trong `SELECT *`; phải gọi đích danh. Chúng là metadata của phiên bản tuple, không phải cột ứng dụng tạo.

### Bài 2

`xmin` đánh dấu **transaction tạo tuple version**, không phải ID hàng. Một transaction INSERT nhiều dòng có thể tạo nhiều tuple với cùng XID; `doc_id` mới là định danh riêng từng thực thể.

### Bài 3

~~~sql
BEGIN;

SELECT pg_current_xact_id_if_assigned() AS before_write;

UPDATE mvcc_lab.documents
SET title = title
WHERE doc_id = 1;

SELECT pg_current_xact_id_if_assigned() AS after_write;

ROLLBACK;
~~~

Trước ghi, transaction có thể chưa được cấp XID thường, nên kết quả đầu có thể NULL. Sau UPDATE, thường đã có XID. `pg_current_xact_id()` có thể **chủ động cấp XID**, làm thí nghiệm "đã tự được cấp chưa?" không còn trung lập.

### Bài 4

~~~sql
BEGIN;

INSERT INTO mvcc_lab.documents (doc_id, title, status)
VALUES (99, 'Nháp thử', 'draft')
RETURNING doc_id, xmin::text, xmax::text, ctid;

ROLLBACK;

SELECT * FROM mvcc_lab.documents WHERE doc_id = 99;
~~~

SELECT sau rollback không thấy row 99. Tuple từng được tạo có thể chưa bị xóa vật lý tức thì; PostgreSQL sẽ xử lý phiên bản không hợp lệ trong cleanup/VACUUM thích hợp.

### Bài 5

~~~sql
BEGIN;

UPDATE mvcc_lab.documents
SET title = 'Tiêu đề tạm',
    version_no = version_no + 1
WHERE doc_id = 1
RETURNING doc_id, title, xmin::text AS xmin, ctid;

ROLLBACK;
~~~

UPDATE tạo tuple version mới với `xmin` của transaction UPDATE. Vì thế **xmin của version hiện tại** không được hiểu là transaction đã tạo entity lần đầu.

### Bài 6

**Phiên A:**

~~~sql
BEGIN;
DELETE FROM mvcc_lab.documents WHERE doc_id = 3;
-- Chưa commit.
~~~

**Phiên B:**

~~~sql
SELECT doc_id, title
FROM mvcc_lab.documents
WHERE doc_id = 3;
~~~

B ở READ COMMITTED có thể tiếp tục thấy version đã commit cũ, không đọc bẩn. Khi A ROLLBACK, DELETE không có hiệu lực; B tiếp tục thấy document 3.

**Quay lại phiên A:**

~~~sql
ROLLBACK;
~~~

### Bài 7

Trước COMMIT, B thấy title **cũ đã commit**. Sau COMMIT, một SELECT mới của B ở READ COMMITTED thường thấy **title mới**. Không có dirty read; snapshot thay đổi giữa các statement.

### Bài 8

B giữ snapshot REPEATABLE READ được thiết lập trước commit của A. Những SELECT bình thường của B vẫn thấy **version cũ** trong transaction đó. Khi B kết thúc transaction rồi lấy snapshot mới, nó có thể thấy version A đã commit.

### Bài 9

`pg_snapshot_xmin` là **ranh giới transaction ID trong một snapshot**, hỗ trợ xác định khả năng thấy các transaction. `documents.xmin` là XID **tạo một tuple version**. Tên gần giống nhau nhưng không phải cùng một đối tượng.

### Bài 10

Chưa đủ căn cứ. `xmax=101` có thể liên quan transaction:

1. UPDATE/DELETE còn in progress.
2. UPDATE/DELETE đã aborted.
3. Row lock không có hành vi xóa.
4. MultiXactId với nhóm locker.
5. UPDATE/DELETE đã commit nhưng vẫn visible cho snapshot cũ.

Phải xét snapshot, commit status, flags và semantics của transaction liên quan.

### Bài 11

~~~sql
BEGIN;

SELECT doc_id, title
FROM mvcc_lab.documents
WHERE doc_id = 1
FOR UPDATE;

ROLLBACK;
~~~

Khóa phối hợp các thao tác đồng thời; không xóa title. Row-lock metadata có thể được phản ánh qua `xmax`/tuple flags, nên `xmax nonzero` không tương đương DELETE.

### Bài 12

PostgreSQL có **MultiXactId** để biểu diễn nhóm transaction tham gia row locking trong các tình huống phù hợp. Trường `xmax` phải được giải thích cùng flags, không phải luôn một XID duy nhất.

### Bài 13

`ctid` là **địa chỉ vật lý của tuple version**, có thể đổi sau UPDATE, VACUUM FULL, CLUSTER hoặc rewrite. API cần ID ứng dụng ổn định như `doc_id`.

### Bài 14

Không. HOT là tối ưu hóa của UPDATE trong heap/index; vẫn có tuple version mới theo MVCC. HOT có thể tránh cập nhật một số index entries nếu điều kiện phù hợp, không xóa đi cơ chế versioning.

### Bài 15

Snapshot S_old có từ trước commit T20 thường thấy **V1** và không thấy V2. Snapshot S_new sau commit T20 thường thấy **V2** và không thấy V1. Phiên bản V1 có thể vẫn tồn tại vật lý trong heap để phục vụ S_old.

### Bài 16

Không. XID thường liên quan thời điểm cấp/hoạt động, **không phải commit sequence**; T31 có thể commit trước T30 dù được cấp XID sau.

### Bài 17

PostgreSQL cần biết transaction tạo/kết thúc tuple đã committed, aborted hay còn chạy, đồng thời xét flags và snapshot. `pg_xact` lưu thông tin trạng thái transaction; **hint bits** trong tuple header có thể ghi cache một số kết luận để tránh tra cứu lại.

### Bài 18

INSERT có thể tạo bytes vật lý và xmin cho tuple, nhưng transaction **aborted** không tạo dữ liệu committed visible. MVCC xét trạng thái transaction, không chỉ xem bytes tồn tại.

### Bài 19

Snapshot cũ của reader vẫn có thể cần các tuple versions trước UPDATE. VACUUM không được thu hồi những version còn có thể visible với reader đó; transaction đọc dài có thể làm tăng thời gian retention và bloat.

### Bài 20

XID dạng truyền thống có **32-bit wraparound**. Freezing và cơ chế tuổi XID ngăn nhầm transaction rất cũ với transaction mới. Trên PostgreSQL hiện đại, freeze có thể được biểu diễn qua flags trong tuple header; `raw xmin != FrozenTransactionId` không chứng minh tuple chưa frozen.

### Bài 21

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS xid_age
FROM pg_database
ORDER BY xid_age DESC;
~~~

`age(datfrozenxid)` là thước đo **tuổi transaction ID để bảo trì/freeze**, không đo ngày tháng theo đồng hồ hay thời điểm tạo document.

### Bài 22

~~~sql
SELECT
    pid, state, xact_start,
    backend_xid::text AS backend_xid,
    backend_xmin::text AS backend_xmin
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

`backend_xmin` là horizon XID do backend giữ cho snapshot/khả năng nhìn thấy; `tuple.xmin` là transaction tạo **phiên bản hàng cụ thể**.

### Bài 23

MVCC không phải kho lịch sử có retention 90 ngày. Tuple versions cũ có thể được dọn sau khi không còn snapshot cần; system columns không cung cấp actor, lý do hoặc mốc sửa chính xác. Thiết kế **audit table**, trigger/application event, quyền ghi rõ ràng, retention và cách truy vấn lịch sử.

### Bài 24

Giả sử B có token `expected_version=1`:

~~~sql
UPDATE mvcc_lab.documents
SET title = 'Bản cập nhật từ B',
    version_no = version_no + 1,
    updated_at = now()
WHERE doc_id = 1 AND version_no = 1
RETURNING doc_id, version_no;
~~~

Nếu A đã cập nhật version_no lên 2, UPDATE B sẽ không khớp hàng, trả **0 rows**. B nên báo conflict, đọc lại bản mới, yêu cầu người dùng giải quyết chênh lệch hoặc áp dụng merge có chủ đích; không ghi đè mù quáng.

### Bài 25

Không. `UPDATE SET title=title` vẫn là statement ghi; PostgreSQL thông thường tạo tuple version mới dù giá trị title không đổi, có thể cấp XID và tham gia locking/WAL. Không dùng nó như một SELECT "không tác dụng phụ".

### Bài 26

SELECT thông thường áp dụng MVCC snapshot và chỉ trả các tuple versions visible. V1 có thể đã bị đánh dấu cũ và invisible với snapshot mới nhưng còn cần cho snapshot cũ hoặc chưa được VACUUM thu hồi; do đó **không visible** không đồng nghĩa **không còn bytes vật lý**.

### Bài 27

SERIALIZABLE của PostgreSQL có thể phát hiện xung đột khiến một transaction bị hủy với `SQLSTATE 40001`. Cần rollback/retry **toàn bộ transaction** trên snapshot mới với giới hạn số lần, không chỉ retry câu UPDATE cuối dựa vào các dữ kiện đã cũ.

### Bài 28

Một thiết kế:

1. Dùng `doc_id` làm primary key và các ràng buộc dữ liệu tương ứng.
2. Đọc qua SQL thông thường; PostgreSQL quản lý MVCC, không cho dirty reads từ transaction khác.
3. Gửi `version_no` cho client; khi cập nhật dùng `UPDATE ... WHERE doc_id=? AND version_no=? RETURNING ...`.
4. Nếu UPDATE 0, trả conflict thay vì ghi đè.
5. Dùng transaction để commit thay đổi document **cùng audit event**.
6. Ghi lịch sử ai sửa, sửa gì, lúc nào, request ID nếu cần; không dựa vào xmin/xmax.
7. Kết thúc transaction ngắn gọn và rollback khi lỗi.
8. Theo dõi `pg_stat_activity`, `backend_xmin`, long-running transactions, autovacuum và age XID.
9. Không coi xmax nonzero là deleted, không dùng ctid làm ID.
10. Nếu có tương tác đồng thời phức tạp, kiểm tra isolation, row locking và chính sách retry khi cần.

---

## 26. Tổng kết

**Transaction ID (XID), `xmin`, `xmax` và snapshot là các phần phối hợp của cơ chế MVCC trong PostgreSQL, không phải bốn cột audit đơn giản.**

- **XID:** định danh transaction liên quan đến các version; không phải timestamp, commit order hay primary key. XID truyền thống là 32-bit, còn các API mới có `xid8`/Full Transaction ID.
- **`xmin` của tuple:** gắn với transaction đã tạo **phiên bản tuple hiện tại**. Sau UPDATE, version mới có xmin mới; không được suy ra thời điểm tạo thực thể nghiệp vụ.
- **`xmax` của tuple:** có thể liên quan UPDATE/DELETE, transaction chưa commit/aborted, row locking hoặc MultiXact. **`xmax != 0` không phải phép thử "row đã bị xóa".**
- **`ctid`:** địa chỉ vật lý của phiên bản, không phải ID ổn định.
- **Snapshot:** quyết định một reader nhìn thấy phiên bản nào, cùng với transaction commit status và tuple header flags. READ COMMITTED có snapshot theo statement; REPEATABLE READ giữ snapshot transaction theo quy tắc PostgreSQL.
- **VACUUM và freeze:** giúp dọn phiên bản cũ khi an toàn và ngăn XID wraparound; dead với snapshot mới chưa chắc đủ điều kiện thu hồi nếu snapshot cũ còn dùng.
- **Transaction dài và replication/prepared transaction:** có thể giữ horizon khiến cleanup bị trì hoãn; cần giám sát.
- **Ứng dụng:** dùng PK, cột `version_no`, timestamp nghiệp vụ và audit table khi cần; không biến system columns thành hợp đồng dữ liệu dài hạn.

Tư duy đúng: **xác định transaction tạo/kết thúc tuple → xét trạng thái committed/in-progress/aborted và lock flags → áp dụng snapshot của reader → để PostgreSQL quyết định visibility → dùng VACUUM/freeze cho vòng đời vật lý → lưu audit và khóa nghiệp vụ bằng cấu trúc riêng**.
