# Thay đổi tập bản ghi phù hợp điều kiện (phantom read)

## Mục tiêu học tập

Sau bài này, người học có thể:

- Nhận diện **phantom read** khi một giao dịch chạy lại cùng một điều kiện tìm kiếm nhưng nhận được tập bản ghi khác do giao dịch khác đã commit.
- Phân biệt phantom read với **dirty read**, **non-repeatable read** và một thay đổi do chính giao dịch đang đọc tạo ra.
- Tự dựng lịch thực thi hai phiên PostgreSQL để quan sát phantom read ở `READ COMMITTED` và đối chiếu với `REPEATABLE READ`.
- Giải thích vai trò của snapshot, MVCC, predicate, chỉ mục và khóa đối với tính ổn định của tập kết quả.
- Thiết kế ranh giới giao dịch trong Java để đọc nhất quán, đồng thời bảo vệ quy tắc nghiệp vụ khi nhiều giao dịch cùng kiểm tra rồi ghi.

## 1. Phantom read là gì và vì sao xuất hiện?

Giả sử một dịch vụ đăng ký lớp học có bảng `registration`. Nhân viên mở báo cáo các đơn đang chờ duyệt cho một lớp:

```sql
SELECT id, student_id
FROM registration
WHERE class_id = 42 AND status = 'PENDING'
ORDER BY id;
```

Lần đầu, truy vấn trả về hai đơn có `id = 101` và `id = 102`. Trong lúc nhân viên vẫn đang thao tác trong cùng một giao dịch, một request khác thêm đơn `id = 103` thỏa cùng điều kiện rồi `COMMIT`. Nếu nhân viên chạy lại chính câu truy vấn trên và nhận ba hàng, tập kết quả đã có thêm một hàng như “xuất hiện từ hư không” trong góc nhìn ban đầu của người đọc. Hiện tượng đó gọi là **phantom read** (đọc bóng ma).

Điểm cốt lõi không nằm ở giá trị của một hàng riêng lẻ mà ở **tập hàng thỏa một predicate**, tức điều kiện lọc của truy vấn. Trong khoảng giữa hai lần đọc, giao dịch khác có thể:

- `INSERT` một hàng mới phù hợp điều kiện, khiến tập kết quả tăng.
- `DELETE` một hàng đang phù hợp điều kiện, khiến tập kết quả giảm.
- `UPDATE` một hàng để nó **bắt đầu** hoặc **ngừng** thỏa điều kiện, khiến hàng đi vào hoặc ra khỏi tập kết quả.

Một predicate có thể là `status = 'PENDING'`, `price BETWEEN 100 AND 200`, `created_at >= ...`, một tập điều kiện `AND/OR`, hoặc điều kiện qua truy vấn có `JOIN` và `EXISTS`. Phantom read không giới hạn ở các bảng có chỉ mục hoặc ở truy vấn `COUNT(*)`.

Phantom read là một hiện tượng về **tính cô lập giao dịch**. Nó có thể xảy ra dù từng câu SQL hợp lệ, từng giao dịch commit nguyên tử và không có dữ liệu hỏng. Vấn đề là người đọc mong chờ tập kết quả ổn định trong phạm vi giao dịch nhưng cơ chế cô lập đang cho phép mỗi lần đọc thấy một thời điểm khác nhau.

Trong module `DATA_PERSISTENCE_FUNDAMENTALS`, nhận diện phantom read giúp người học hiểu mối liên hệ giữa mô hình dữ liệu, truy vấn, cô lập, kiểm soát đồng thời và ranh giới persistence của Java. Nó cũng giúp phân biệt lựa chọn **đúng đắn về giao dịch** với lựa chọn **tối ưu hiệu năng bằng chỉ mục**.

## 2. Mô hình hai giao dịch: điều kiện giống nhau, tập hàng khác nhau

Ký hiệu:

- **T1**: giao dịch đọc báo cáo đăng ký lớp 42.
- **T2**: giao dịch tạo thêm đăng ký lớp 42.
- **P**: điều kiện `class_id = 42 AND status = 'PENDING'`.
- **R(P, t)**: tập hàng mà một lần đọc theo P nhìn thấy tại thời điểm t, dưới quy tắc cô lập đang áp dụng.

Kịch bản:

| Bước | T1: giao dịch báo cáo | T2: giao dịch tạo đăng ký | Tập hàng P mà T1 thấy |
| --- | --- | --- | --- |
| 1 | `BEGIN` | | |
| 2 | `SELECT ... WHERE P` | | `{101, 102}` |
| 3 | | `BEGIN; INSERT ... id = 103` | |
| 4 | | `COMMIT` | |
| 5 | `SELECT ... WHERE P` lần nữa | | `{101, 102, 103}` |
| 6 | `COMMIT` | | |

Nếu mức cô lập cho phép T1 quan sát commit của T2 ở bước 5, ta có:

\[
R(P, t_1) \neq R(P, t_2)
\]

Trong đó, **P không thay đổi** và cả hai lần đọc đều nằm trong **cùng giao dịch T1**. Phần tử mới trong tập là “phantom”. Để kết luận đúng, phải xác minh hàng 103 đến từ một giao dịch **khác**, đã commit giữa hai lần đọc; việc T1 tự thêm hàng và sau đó đọc thấy hàng mình vừa thêm là hành vi bình thường, không phải ví dụ phantom read do giao dịch khác gây ra.

```mermaid
sequenceDiagram
    participant T1 as T1 - Báo cáo
    participant DB as Cơ sở dữ liệu
    participant T2 as T2 - Đăng ký
    T1->>DB: SELECT các đơn PENDING của lớp 42
    DB-->>T1: 101, 102
    T2->>DB: BEGIN; INSERT đơn 103
    T2->>DB: COMMIT
    T1->>DB: SELECT lại cùng điều kiện
    DB-->>T1: 101, 102, 103 (READ COMMITTED)
```

**Lưu ý:** sơ đồ mô tả kết quả ở `READ COMMITTED` của PostgreSQL; một mức cô lập mạnh hơn có thể giữ nguyên tập nhìn thấy trong T1. Thời điểm mỗi giao dịch bắt đầu và thời điểm snapshot được thiết lập đều quan trọng.

## 3. Thực hành có thể tái hiện trên PostgreSQL

### 3.1. Tạo bảng và dữ liệu ban đầu

Chạy khối sau **một lần** trên cơ sở dữ liệu thử nghiệm. Không chạy các thao tác tạo bảng hoặc xóa dữ liệu trên production.

```sql
CREATE TABLE registration (
    id          BIGINT PRIMARY KEY,
    class_id    BIGINT NOT NULL,
    student_id  BIGINT NOT NULL,
    status      TEXT NOT NULL
                CHECK (status IN ('PENDING', 'APPROVED', 'CANCELLED')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO registration (id, class_id, student_id, status)
VALUES
    (101, 42, 9001, 'PENDING'),
    (102, 42, 9002, 'PENDING'),
    (201, 42, 9003, 'APPROVED'),
    (301, 99, 9004, 'PENDING');
```

Có bốn hàng trong bảng, nhưng chỉ **101 và 102** thỏa predicate P. Hàng 201 khác `status`; hàng 301 khác `class_id`. Hai hàng này giúp minh họa rằng phantom read liên quan đến *điều kiện truy vấn*, chứ không phải cứ tổng số hàng của bảng thay đổi là có phantom trong kết quả đang xét.

Mở **hai phiên/kết nối SQL độc lập**, gọi là phiên A và phiên B. Thực hiện các bước theo đúng thứ tự, đừng chạy toàn bộ hai khối liên tiếp trong cùng một kết nối.

### 3.2. Phiên A — giữ giao dịch đọc mở

```sql
-- Phiên A: bước A1
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT id, student_id
FROM registration
WHERE class_id = 42 AND status = 'PENDING'
ORDER BY id;
-- Kỳ vọng: 101, 102

SELECT COUNT(*) AS pending_count
FROM registration
WHERE class_id = 42 AND status = 'PENDING';
-- Kỳ vọng: 2

-- Tạm dừng tại đây. Chạy toàn bộ bước B1 ở phiên B,
-- rồi quay về phiên A thực hiện bước A2.
```

### 3.3. Phiên B — thêm hàng rồi commit

```sql
-- Phiên B: bước B1, chạy sau A1 và trước A2
BEGIN;

INSERT INTO registration (id, class_id, student_id, status)
VALUES (103, 42, 9005, 'PENDING');

COMMIT;
```

### 3.4. Phiên A — đọc lại cùng điều kiện

```sql
-- Phiên A: bước A2, vẫn trong giao dịch A1
SELECT id, student_id
FROM registration
WHERE class_id = 42 AND status = 'PENDING'
ORDER BY id;
-- Kỳ vọng: 101, 102, 103

SELECT COUNT(*) AS pending_count
FROM registration
WHERE class_id = 42 AND status = 'PENDING';
-- Kỳ vọng: 3

COMMIT;
```

**Kết quả quan sát:** T1 đã chạy lại cùng `WHERE` và `ORDER BY` nhưng nhận thêm hàng 103. Đó là phantom read. Không có dirty read vì T2 đã commit trước khi T1 đọc thấy 103. Một lần chạy truy vấn trong từng bước vẫn là một thao tác hợp lệ; điều không ổn định là **kết quả giữa hai câu lệnh trong cùng transaction**.

### 3.5. Nếu T2 rollback thì sao?

Thử lại trên bộ dữ liệu đã reset, cho T2 `INSERT` hàng 103 rồi `ROLLBACK` thay vì `COMMIT`. Phiên A không đọc thấy 103 trong PostgreSQL `READ COMMITTED`. PostgreSQL không lộ dữ liệu chưa commit cho phiên đọc thông thường; điều này phân biệt phantom read với dirty read.

### 3.6. Biến thể: hàng đi ra hoặc đi vào điều kiện

Với dữ liệu ban đầu, ngoài thao tác `INSERT`, T2 có thể dùng:

```sql
-- Hàng 201 vốn không phù hợp P, nay đi vào tập kết quả.
UPDATE registration
SET status = 'PENDING'
WHERE id = 201;

-- Hoặc hàng 102 vốn phù hợp P, nay rời khỏi tập kết quả.
UPDATE registration
SET status = 'APPROVED'
WHERE id = 102;

-- Hoặc xóa hẳn hàng 102 khỏi tập kết quả.
DELETE FROM registration WHERE id = 102;
```

Đây là **các biến thể độc lập** để thử sau khi reset dữ liệu, không phải các lệnh cần chạy nối tiếp trên cùng một bộ dữ liệu. Trong mỗi biến thể, T2 phải commit giữa hai lần T1 chạy lại cùng điều kiện. Khi có `UPDATE` ảnh hưởng đến hàng đã tồn tại, hiện tượng quan sát có thể đồng thời liên quan đến non-repeatable read; cách gọi phụ thuộc việc ta đang theo dõi một hàng cụ thể hay **toàn bộ tập hàng thỏa predicate**.

## 4. Phân biệt phantom read với những hiện tượng gần giống

| Hiện tượng | Điều T1 quan sát | Tình huống cốt lõi | Khác biệt |
| --- | --- | --- | --- |
| **Dirty read** | Thấy giá trị T2 chưa commit | T2 sửa một hàng, T1 thấy thay đổi rồi T2 rollback | Phụ thuộc vào dữ liệu **chưa commit**; PostgreSQL không cho phép dirty read |
| **Non-repeatable read** | Đọc lại cùng hàng và thấy giá trị khác hoặc hàng biến mất | T1 đọc `registration.id = 101`; T2 cập nhật `status` và commit; T1 đọc lại | Theo dõi **một hàng xác định** |
| **Phantom read** | Chạy lại cùng predicate, thấy tập hàng tăng hoặc giảm | T2 insert/delete/update một hàng vào/ra tập `class_id = 42 AND status = 'PENDING'` | Theo dõi **tập hàng thỏa điều kiện** |
| **Read skew** | Ghép dữ liệu đọc từ các thời điểm khác nhau | T1 đọc số dư A, T2 chuyển tiền rồi commit, T1 đọc B | Tổ hợp dữ liệu từ các snapshot khác nhau có thể không đại diện trạng thái nhất quán |

Ba câu hỏi giúp nhận diện phantom read:

1. Hai lần đọc có diễn ra **trong cùng một giao dịch T1** không?
2. T1 có đọc lại **cùng một điều kiện tìm kiếm**, trong khi T2 thay đổi dữ liệu có liên quan và commit ở giữa không?
3. Sau commit của T2, **tập bản ghi T1 nhận được** có khác lần đầu không?

Nếu chỉ nhìn hai lần tải trang trong **hai HTTP request riêng biệt**, có thể đó chỉ là dữ liệu thay đổi bình thường giữa hai giao dịch. Không nên gọi mọi lần kết quả đổi là lỗi phantom read của một transaction. Phân loại hiện tượng phải gắn với **ranh giới giao dịch** và mức cô lập cụ thể.

## 5. Snapshot, MVCC và các mức cô lập ảnh hưởng thế nào?

PostgreSQL sử dụng **MVCC (Multi-Version Concurrency Control)**: dữ liệu có thể có nhiều phiên bản logic trong một khoảng thời gian, và một **snapshot** quyết định phiên bản nào được phép nhìn thấy. Từ đó, các mức cô lập quyết định liệu hai lần đọc trong T1 có cùng góc nhìn về những commit của T2 hay không.

### 5.1. PostgreSQL `READ COMMITTED`: snapshot theo câu lệnh

Đây là mức mặc định của PostgreSQL. Mỗi câu `SELECT` thông thường bắt đầu với snapshot mới, nên câu lệnh thứ hai có thể thấy các thay đổi mà giao dịch khác đã commit sau câu đầu. Chính vì thế, kịch bản ở mục 3 tạo phantom.

Điều quan trọng: **một câu `SELECT` duy nhất có snapshot nhất quán ở cấp câu lệnh**. Trong ví dụ, `SELECT COUNT(*)` tự nó không “đếm được nửa cũ nửa mới” chỉ vì có ai đó commit khi câu lệnh đang chạy. Bất thường nằm ở **hai câu lệnh đọc kế tiếp**, khi snapshot có thể thay đổi.

### 5.2. PostgreSQL `REPEATABLE READ`: snapshot ổn định trong giao dịch

Ở mức `REPEATABLE READ` của PostgreSQL, snapshot được thiết lập tại câu lệnh đầu tiên cần snapshot của giao dịch và được tái sử dụng cho các lần đọc tiếp theo. T2 có thể insert và commit, nhưng T1 vẫn nhìn tập hàng theo snapshot cũ cho đến khi T1 kết thúc giao dịch. PostgreSQL **ngăn phantom read ở `REPEATABLE READ`** bằng cơ chế này.

Để thử lại, dùng bộ dữ liệu hiện có sau ví dụ trước (đã có 103) và chọn một ID chưa dùng (104). Phiên A:

```sql
-- Phiên A, bước A1
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT id
FROM registration
WHERE class_id = 42 AND status = 'PENDING'
ORDER BY id;
-- Giả sử hiện có: 101, 102, 103

-- Sau khi B đã COMMIT, vẫn trong phiên A:
SELECT id
FROM registration
WHERE class_id = 42 AND status = 'PENDING'
ORDER BY id;
-- Vẫn: 101, 102, 103

COMMIT;

-- Giao dịch mới mới thấy những thay đổi đã commit:
SELECT id
FROM registration
WHERE class_id = 42 AND status = 'PENDING'
ORDER BY id;
-- 101, 102, 103, 104
```

Phiên B, chạy giữa hai lần `SELECT` của A:

```sql
BEGIN;
INSERT INTO registration (id, class_id, student_id, status)
VALUES (104, 42, 9006, 'PENDING');
COMMIT;
```

Trong phép thử này, T1 phải chạy lần đọc đầu **trước** khi T2 commit để snapshot của T1 phản ánh trạng thái cũ. Chỉ `BEGIN` nhưng chưa thực hiện lệnh thiết lập snapshot rồi mới để T2 commit có thể dẫn tới kết quả khác kỳ vọng.

### 5.3. PostgreSQL `SERIALIZABLE`: tính đúng đắn mạnh hơn snapshot ổn định

`SERIALIZABLE` hướng tới việc các giao dịch commit tạo ra kết quả tương đương một thứ tự chạy tuần tự nào đó. PostgreSQL dùng **Serializable Snapshot Isolation (SSI)** để theo dõi những phụ thuộc có thể gây ra lịch không tuần tự hóa được và có thể hủy một giao dịch bằng lỗi `SQLSTATE 40001` (`serialization_failure`). Ứng dụng phải sẵn sàng chạy lại **toàn bộ giao dịch**.

Với giao dịch chỉ đọc lặp lại trong ví dụ, `REPEATABLE READ` đã đủ để giữ tập kết quả ổn định; không cần mặc định dùng `SERIALIZABLE` cho mọi báo cáo. Nhưng khi giao dịch còn **đọc điều kiện rồi ghi dựa trên kết quả**, mức cô lập đọc ổn định chưa chắc bảo vệ được bất biến nghiệp vụ (xem mục 7).

### 5.4. Bảng hành vi theo PostgreSQL

| Mức yêu cầu | Phantom read giữa hai câu `SELECT` thông thường | Cách nhìn dữ liệu | Ghi chú |
| --- | --- | --- | --- |
| `READ UNCOMMITTED` | Có thể | PostgreSQL thực thi như `READ COMMITTED` | PostgreSQL không hỗ trợ dirty read |
| `READ COMMITTED` | **Có thể** | Snapshot theo câu lệnh | Một commit giữa hai lệnh có thể làm tập kết quả đổi |
| `REPEATABLE READ` | **Không** | Snapshot ổn định trong transaction | Vẫn có thể gặp các bất thường ghi như write skew |
| `SERIALIZABLE` | **Không trong các giao dịch commit thành công** | Snapshot và cơ chế kiểm tra phụ thuộc | Có thể phải retry giao dịch do `40001` |

Không áp dụng nguyên bảng này cho mọi DBMS. Tiêu chuẩn SQL mô tả những hiện tượng tối thiểu có thể cho phép theo mức cô lập; các hệ quản trị triển khai bằng cơ chế khác nhau, gồm MVCC, shared/exclusive locks, range hoặc key-range locks. Ví dụ PostgreSQL ngăn phantom ở `REPEATABLE READ` dù tiêu chuẩn vẫn cho phép phantom ở mức này trong một số cách diễn giải tối thiểu. Khi dùng MySQL/InnoDB, SQL Server hay Oracle, phải xem **mức cô lập và kiểu đọc cụ thể của chính hệ quản trị đó**.

## 6. Chỉ mục và khóa có giải quyết được phantom read không?

### Chỉ mục giúp truy vấn nhanh hơn, không tự làm tập kết quả bất biến

Ta có thể thêm chỉ mục hỗ trợ predicate:

```sql
CREATE INDEX idx_registration_class_status
    ON registration (class_id, status);
```

Index có thể giúp tìm nhanh những hàng thỏa `class_id = 42 AND status = 'PENDING'`, tùy độ chọn lọc và kế hoạch thực thi. Tuy nhiên, **index không đổi snapshot hoặc mức cô lập**. T2 vẫn có thể insert một hàng mới phù hợp predicate và commit; T1 ở `READ COMMITTED` vẫn có thể thấy hàng mới khi chạy lại truy vấn. Index là công cụ **hiệu năng**, không phải bảo đảm tránh phantom read.

### `SELECT ... FOR UPDATE` chỉ khóa những hàng phù hợp đã đọc

Một hiểu nhầm phổ biến là thêm `FOR UPDATE` vào truy vấn đầu tiên thì T2 không thể chèn thêm hàng phù hợp điều kiện. Trong PostgreSQL, `SELECT ... FOR UPDATE` lấy khóa hàng trên những hàng được trả về, nhưng **không tự khóa mọi giá trị tương lai của predicate**. Nếu lần đầu không có hàng nào phù hợp, không có hàng kết quả để khóa; một giao dịch khác vẫn có thể insert hàng mới.

Ví dụ:

```sql
BEGIN;
SELECT id FROM registration
WHERE class_id = 42 AND status = 'PENDING'
FOR UPDATE;
-- Khóa những hàng đã trả về; không khóa một "khoảng trống" trừu tượng
-- chứa tất cả id có thể được thêm sau này.
COMMIT;
```

**Không** dùng `SELECT COUNT(*) ... FOR UPDATE` như một công thức khóa predicate: PostgreSQL không cho dùng khóa hàng `FOR UPDATE` trực tiếp với kết quả tổng hợp theo cách đó. Ở các DBMS khác, khóa phạm vi hoặc gap locks có thể hoạt động khác, tùy mức cô lập, index và loại câu SQL.

### Predicate locks trong SSI không giống việc chặn mọi lệnh INSERT

PostgreSQL ở `SERIALIZABLE` sử dụng các khóa/đánh dấu phụ thuộc kiểu **predicate/SIREAD** để phát hiện lịch có nguy cơ không tuần tự hóa được. Những dấu này không hoạt động như khóa ghi làm T2 luôn chờ ngay khi insert vào phạm vi mà T1 đã đọc. Thay vào đó, bộ máy có thể cho các thao tác tiếp diễn rồi hủy một giao dịch khi phát hiện chuỗi phụ thuộc nguy hiểm. Vì thế, việc bắt lỗi và retry ở tầng ứng dụng là phần quan trọng của giải pháp.

## 7. Khi phantom read gây ra sai lệch nghiệp vụ

### 7.1. Lỗi “kiểm tra trước, thêm sau” khi giới hạn số chỗ

Một lớp có tối đa **3** đăng ký được chấp nhận và hiện có **2**. Hai request T1 và T2 cùng xử lý đăng ký mới:

| Thời điểm | T1 | T2 |
| --- | --- | --- |
| 1 | `SELECT COUNT(*) WHERE class_id = 42 AND status = 'APPROVED'` → 2 | |
| 2 | | `SELECT COUNT(*) ...` → 2 |
| 3 | Kiểm tra `2 < 3`, thấy còn chỗ | |
| 4 | | Kiểm tra `2 < 3`, cũng thấy còn chỗ |
| 5 | `INSERT` một đăng ký `APPROVED` | |
| 6 | | `INSERT` một đăng ký `APPROVED` |
| 7 | `COMMIT` | `COMMIT` |

Nếu cả hai giao dịch đều commit được, lớp có **4/3** đăng ký. Đây là một **race condition do đọc rồi ghi**; nó có liên hệ chặt với tập kết quả của predicate, nhưng cần phân biệt: bản thân lỗi overbooking **không đòi hỏi** T1 hoặc T2 phải thực hiện hai lần `SELECT` để quan sát phantom read. Nó có thể tồn tại ngay cả khi mỗi giao dịch ở PostgreSQL `REPEATABLE READ` đọc một snapshot nhất quán, vì cả hai giao dịch có thể cùng đọc 2 rồi thêm **hai hàng khác nhau**. Lỗi đó thuộc nhóm bất thường ghi và kiểm tra bất biến, thường được phân tích dưới góc độ *write skew*.

Do đó, **ngăn phantom read chưa đủ để bảo vệ mọi bất biến có nhiều writer**. Đối với giới hạn số chỗ, ta cần một cơ chế để hai giao dịch nhận chỗ cạnh tranh trên **cùng một tài nguyên được kiểm soát** hoặc một mức cô lập bảo đảm serializability với retry.

### 7.2. Cách 1: cập nhật có điều kiện trên một hàng đại diện cho sức chứa

Một cách thiết kế là lưu số chỗ tối đa và số chỗ đã đặt trên **một hàng của lớp học**:

```sql
CREATE TABLE class_capacity (
    class_id BIGINT PRIMARY KEY,
    capacity INTEGER NOT NULL CHECK (capacity >= 0),
    reserved INTEGER NOT NULL DEFAULT 0,
    CHECK (reserved >= 0 AND reserved <= capacity)
);

INSERT INTO class_capacity (class_id, capacity, reserved)
VALUES (42, 3, 2);
```

Khi duyệt một đăng ký, mọi luồng ghi phải thao tác qua cùng hàng đại diện cho sức chứa:

```sql
BEGIN;

UPDATE class_capacity
SET reserved = reserved + 1
WHERE class_id = 42 AND reserved < capacity
RETURNING reserved;
-- Có một hàng trả về: giữ được 1 chỗ; không có hàng: hết chỗ.

-- Chỉ khi UPDATE đã giữ chỗ thành công mới thêm đăng ký APPROVED:
-- INSERT INTO registration (...) VALUES (...);

COMMIT;
```

`UPDATE` khóa hàng cần sửa; các cập nhật tranh chấp sẽ được PostgreSQL điều phối, và điều kiện `reserved < capacity` được kiểm tra đúng với quy tắc thực thi của mức cô lập. Nếu câu `UPDATE` không trả về hàng nào, ứng dụng phải từ chối đặt chỗ và **không** thực hiện `INSERT`. Nếu insert thất bại, rollback **cả transaction** để hoàn lại số đếm. Các thao tác hủy/chuyển lớp cũng phải cập nhật bộ đếm theo một quy ước duy nhất để tránh lệch dữ liệu.

Đây là một **mô hình dữ liệu và ranh giới ghi** bảo vệ bất biến, khác với việc chỉ cố gắng giữ snapshot báo cáo ổn định. Ngoài ra, vẫn nên dùng `UNIQUE` cho những quy tắc có thể diễn đạt thành duy nhất, như một học viên chỉ có một đăng ký cho một lớp nếu nghiệp vụ yêu cầu.

### 7.3. Cách 2: `SERIALIZABLE` với retry toàn giao dịch

Nếu nhiều giao dịch cùng kiểm tra một điều kiện tổng hợp rồi ghi, `SERIALIZABLE` của PostgreSQL có thể phát hiện lịch không tuần tự hóa được và từ chối một giao dịch bằng `40001`. Mã Java phải retry **toàn bộ transaction**, gồm cả lần đọc điều kiện và quyết định ghi; chỉ chạy lại mỗi `INSERT` là không đủ.

Khi retry, cân nhắc số lần tối đa, backoff và tính idempotent của yêu cầu. Không thực hiện gửi email, gọi API thu tiền hoặc phát sự kiện ra ngoài trong transaction mà có thể retry nếu chưa có cơ chế bảo vệ trùng lặp. Với nghiệp vụ có một quy tắc đơn giản có thể bảo vệ bằng một hàng cập nhật có điều kiện, cách 1 thường dễ quan sát và kiểm thử hơn; nhu cầu thực tế quyết định giải pháp.

## 8. Ranh giới giao dịch trong ứng dụng Java

### 8.1. Đọc nhiều truy vấn với cùng snapshot qua JDBC

Một báo cáo cần vừa đếm vừa liệt kê các đăng ký đang chờ duyệt. Ở `READ COMMITTED`, nếu hai lệnh chạy ở hai snapshot khác nhau, `COUNT(*)` có thể báo 2 trong khi danh sách có 3 phần tử. Nếu yêu cầu báo cáo phải nhất quán tại cùng một thời điểm, có thể đọc cả hai trong **một giao dịch `REPEATABLE READ`**, trên cùng một `Connection`.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

record PendingSnapshot(long count, List<Long> registrationIds) {}

public final class RegistrationReportRepository {
    private final DataSource dataSource;

    public RegistrationReportRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public PendingSnapshot readPendingSnapshot(long classId) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setTransactionIsolation(Connection.TRANSACTION_REPEATABLE_READ);
            connection.setReadOnly(true);
            connection.setAutoCommit(false);
            try {
                long count = countPending(connection, classId);
                List<Long> ids = findPendingIds(connection, classId);
                connection.commit();
                return new PendingSnapshot(count, List.copyOf(ids));
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    error.addSuppressed(rollbackFailure);
                }
                throw error;
            }
        }
    }

    private long countPending(Connection connection, long classId)
            throws SQLException {
        String sql = "SELECT COUNT(*) FROM registration "
                + "WHERE class_id = ? AND status = 'PENDING'";
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, classId);
            try (ResultSet rs = ps.executeQuery()) {
                rs.next();
                return rs.getLong(1);
            }
        }
    }

    private List<Long> findPendingIds(Connection connection, long classId)
            throws SQLException {
        String sql = "SELECT id FROM registration "
                + "WHERE class_id = ? AND status = 'PENDING' ORDER BY id";
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, classId);
            try (ResultSet rs = ps.executeQuery()) {
                List<Long> ids = new ArrayList<>();
                while (rs.next()) {
                    ids.add(rs.getLong(1));
                }
                return ids;
            }
        }
    }
}
```

Các điểm cần quan sát:

- Hai `SELECT` chạy trong **cùng một transaction**. Nếu mỗi lời gọi lấy một kết nối mới hoặc dùng auto-commit riêng, giả định snapshot nhất quán không còn đúng.
- Thiết lập isolation trước khi bắt đầu transaction theo hướng dẫn driver/DBMS. `setReadOnly(true)` là gợi ý hoặc yêu cầu tùy driver và DB, **không** thay thế isolation.
- Việc dùng parameter trong `PreparedStatement` giúp tránh ghép dữ liệu đầu vào vào SQL và hỗ trợ truy vấn an toàn. Nó **không** tự chặn phantom.
- Đoạn mã nhằm minh họa kiểm soát transaction và snapshot; trong hệ thống thực tế, connection pool/transaction manager quản lý việc khôi phục thuộc tính connection, timeout và retry.

### 8.2. Spring: đặt giao dịch ở tầng service

Trong ứng dụng dùng Spring và một transaction manager phù hợp, ranh giới thường nằm ở phương thức service:

```java
@Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
public PendingSnapshot readPendingSnapshot(long classId) {
    long count = repository.countPending(classId);
    List<Long> ids = repository.findPendingIds(classId);
    return new PendingSnapshot(count, ids);
}
```

Các repository phải tham gia **cùng transaction**. Với Spring AOP mặc định, lời gọi phương thức `@Transactional` từ chính đối tượng đó (`this.method()`) có thể không đi qua proxy, khiến annotation không phát huy tác dụng. `readOnly = true` cũng không phải cam kết bảo vệ bất biến cho các thao tác ghi đồng thời.

### 8.3. Một lần truy vấn, nhiều lần truy vấn và nhiều request

Nếu báo cáo có thể được tạo bằng **một câu SQL duy nhất**, PostgreSQL `READ COMMITTED` đã cung cấp snapshot nhất quán ở cấp câu lệnh. Điều này có thể đơn giản và nhẹ hơn mở giao dịch dài qua nhiều `SELECT`. Ngược lại, khi nhiều câu SQL cần cùng góc nhìn dữ liệu, một transaction ở mức cô lập phù hợp là lựa chọn rõ ràng.

Không nên mở một transaction giữ snapshot qua nhiều thao tác UI hoặc qua nhiều HTTP request chỉ để người dùng thấy danh sách bất biến. Giao dịch dài có thể làm chậm việc thu gom phiên bản cũ và tăng áp lực tài nguyên. Đối với danh sách thay đổi liên tục, hãy định nghĩa rõ UI có chấp nhận cập nhật thời gian thực, dùng phân trang theo khóa ổn định, hoặc tạo một ảnh chụp báo cáo có định danh riêng khi yêu cầu nghiệp vụ cần như vậy. **Keyset pagination** có thể hạn chế trùng/mất hàng do thay đổi thứ tự so với offset pagination, nhưng không tự bảo đảm cùng snapshot qua nhiều request.

## 9. Quan sát và kiểm thử phantom read đúng cách

Một bài kiểm thử đồng thời cần **điều khiển thứ tự** của hai giao dịch, không phụ thuộc hoàn toàn vào khả năng hai thread tình cờ chạy đúng thời điểm. Tạo một bộ dữ liệu xác định, dùng hai connection, chủ động dừng T1 giữa hai lần đọc, cho T2 ghi và commit, rồi đọc lại trong T1.

| Kiểm thử | Mức cô lập T1 | Thao tác T2 | Kết quả kỳ vọng |
| --- | --- | --- | --- |
| A | PostgreSQL `READ COMMITTED` | Insert hàng mới thỏa P rồi commit giữa hai lần đọc | T1 nhìn thấy hàng mới ở lần đọc thứ hai |
| B | PostgreSQL `REPEATABLE READ` | Insert hàng mới thỏa P rồi commit giữa hai lần đọc | Hai lần đọc T1 vẫn cùng tập hàng |
| C | PostgreSQL `READ COMMITTED` | Insert nhưng `ROLLBACK` | T1 không nhìn thấy hàng chưa commit |
| D | PostgreSQL `READ COMMITTED` | Insert hàng **không** thỏa P và commit | Tập hàng theo P của T1 không đổi vì thao tác này |
| E | Hai transaction đọc–ghi ở `REPEATABLE READ` | Cùng kiểm tra sức chứa rồi insert hàng khác nhau | Có thể phá bất biến sức chứa dù không có phantom read trong từng transaction |

Khi viết kiểm thử Java, có thể dùng `CountDownLatch` hoặc cơ chế đồng bộ của test harness để giữ T1 sau lần `SELECT` đầu và chỉ cho đọc lần hai khi T2 đã commit. Mỗi luồng phải có **connection riêng**. Cần reset dữ liệu trước mỗi lần thử để kết quả không phụ thuộc lần chạy trước; tránh dùng `Thread.sleep` để giả định thời điểm commit.

Tối ưu SQL bằng index và `EXPLAIN` nhằm đánh giá kế hoạch truy vấn, còn kiểm thử phantom read nhằm xác nhận **lịch thực thi và tính cô lập**. Đừng suy ra không có phantom chỉ vì truy vấn chạy nhanh, có index, hoặc bài test ngẫu nhiên không tái hiện được lỗi.

## 10. Bài tập tình huống

**Tình huống 1 — Thay đổi tập kết quả.** T1 bắt đầu giao dịch ở PostgreSQL `READ COMMITTED`, đọc danh sách các vé `WHERE event_id = 7 AND paid = false`, nhận `{1, 2}`. T2 thêm vé số 3 với `paid = true`, commit. T1 chạy lại cùng truy vấn. Có phantom read trong lần này không?

**Tình huống 2 — Hàng đi vào predicate.** T1 đọc danh sách đơn `WHERE status = 'PENDING'` gồm `{10, 11}`. T2 sửa trạng thái đơn 12 từ `PAID` thành `PENDING`, commit. T1 đọc lại thành `{10, 11, 12}`. Hãy gọi tên hiện tượng và giải thích vì sao không cần `INSERT` để tạo ra nó.

**Tình huống 3 — Chọn mức cô lập.** Báo cáo cần thực hiện ba `SELECT` riêng trong cùng một request và dữ liệu đầu ra phải tương ứng với cùng một trạng thái đã commit. Với PostgreSQL, `READ COMMITTED` có đủ không? Mức nào thường phù hợp cho tình huống chỉ đọc này?

**Tình huống 4 — Giới hạn một người một vé.** Hai giao dịch đồng thời kiểm tra không có vé của cùng một người cho cùng sự kiện rồi cùng insert. `REPEATABLE READ` có luôn bảo đảm không bị trùng không? Hãy đề xuất ít nhất một cơ chế thực thi quy tắc ngay trong database.

**Tình huống 5 — Khóa kết quả rỗng.** T1 dùng `SELECT id FROM registration WHERE class_id = 50 FOR UPDATE` và nhận **không hàng nào**. T2 có bị PostgreSQL chặn mọi thao tác insert đăng ký lớp 50 không? Vì sao?

### Gợi ý đáp án

1. **Không**, nếu T2 chỉ thêm vé `paid = true` thì vé đó không thỏa điều kiện `paid = false`, nên tập kết quả của T1 không đổi vì thao tác ấy. Một thay đổi của bảng không mặc nhiên là phantom theo mọi predicate.
2. **Phantom read**, vì hàng 12 bắt đầu thỏa predicate và xuất hiện trong tập kết quả sau commit của T2. Phantom không bắt buộc phải do `INSERT`; `UPDATE` cũng có thể làm thay đổi tập hàng phù hợp.
3. **Chưa đủ** nếu ba câu `SELECT` phải quan sát cùng snapshot, bởi `READ COMMITTED` lấy snapshot mới cho từng câu. Với PostgreSQL, `REPEATABLE READ` trong một giao dịch chỉ đọc trên một connection là lựa chọn thường phù hợp; có thể cân nhắc gom thành một SQL nếu nghiệp vụ cho phép.
4. **Không**. Hai transaction có thể cùng thấy chưa có vé rồi insert hai hàng khác nhau. Ràng buộc `UNIQUE (event_id, student_id)` là biện pháp bảo vệ trực tiếp khi quy tắc yêu cầu một người chỉ được có một vé cho mỗi sự kiện; xử lý lỗi unique violation ở tầng ứng dụng.
5. **Không**. `FOR UPDATE` trong PostgreSQL khóa những hàng thực sự được chọn, không tự khóa predicate hoặc khoảng trống đại diện cho mọi hàng có thể xuất hiện sau này.

## 11. Checklist áp dụng vào hệ thống thực tế

- [ ] Xác định chính xác **predicate** và lý do nghiệp vụ cần tập hàng ổn định.
- [ ] Xác nhận các lần đọc thuộc **một transaction** hay thuộc nhiều request/transaction khác nhau.
- [ ] Biết DBMS, mức cô lập thực tế và phạm vi snapshot của từng câu lệnh.
- [ ] Kiểm chứng hành vi bằng **hai connection** và một lịch thực thi có kiểm soát.
- [ ] Khi **chỉ đọc**, cân nhắc một SQL hoặc snapshot giao dịch ổn định theo mức nhất quán cần thiết.
- [ ] Khi **đọc rồi ghi**, bảo vệ bất biến bằng constraint, cập nhật có điều kiện, khóa phù hợp hoặc `SERIALIZABLE` và retry.
- [ ] Không coi index hoặc `SELECT ... FOR UPDATE` trên tập rỗng là giải pháp mặc định để chặn phantom.
- [ ] Giới hạn thời gian giao dịch, theo dõi xung đột, retry và tác dụng phụ khi triển khai Java production.

**Ghi nhớ:** Phantom read là việc **tập hàng thỏa cùng một điều kiện thay đổi giữa các lần đọc trong một giao dịch** do thay đổi đã commit từ giao dịch khác. PostgreSQL `READ COMMITTED` có thể cho phép hiện tượng đó; `REPEATABLE READ` giữ tập kết quả theo snapshot ổn định. Nhưng bảo vệ **quy tắc ghi đồng thời** còn cần kiểm soát bất biến ở mức dữ liệu và giao dịch, kể cả khi người đọc không còn thấy phantom.
