# Constraint trigger và kiểm tra trì hoãn trong PostgreSQL

Giả sử một ứng dụng quản lý ngân sách lưu **tổng ngân sách được phê duyệt** trong bảng `batches` và **các khoản phân bổ** trong bảng `allocations`. Khi một đợt ngân sách ở trạng thái đã chốt (`sealed`), nghiệp vụ yêu cầu:

**Tổng số tiền của tất cả dòng phân bổ thuộc đợt đó phải bằng chính xác số tiền được phê duyệt.**

Vấn đề là ứng dụng có thể phải thực hiện nhiều câu SQL trong một transaction:

```sql
BEGIN;

-- Bước 1: tăng khoản phân bổ thứ nhất từ 60 lên 70.
UPDATE ... SET amount = 70 WHERE line_id = 1001;

-- Ở giữa transaction: tổng phân bổ tạm thời là 110,
-- trong khi ngân sách đã chốt vẫn là 100.

-- Bước 2: giảm khoản phân bổ thứ hai từ 40 xuống 30.
UPDATE ... SET amount = 30 WHERE line_id = 1002;

-- Trước COMMIT: tổng đã trở lại 100.
COMMIT;
```

Nếu kiểm tra “tổng phải bằng ngân sách” **ngay sau mỗi statement**, câu UPDATE thứ nhất sẽ bị từ chối. Nhưng nếu kiểm tra **khi transaction kết thúc**, cả hai bước có thể được thực hiện và transaction vẫn bảo đảm trạng thái cuối cùng hợp lệ.

PostgreSQL có cơ chế đáp ứng nhu cầu này: **constraint trigger có thể trì hoãn** (*deferrable constraint trigger*), kết hợp với `SET CONSTRAINTS`.

```text
        BEGIN TRANSACTION
               |
               v
        UPDATE allocation A
        Tổng tạm thời = 110
               |
               +---- Kiểm tra IMMEDIATE ---> LỖI ở cuối statement
               |
               +---- Kiểm tra DEFERRED ----> Ghi nhận sự kiện chờ
                                                |
                                                v
                                       UPDATE allocation B
                                       Tổng trở về 100
                                                |
                                                v
                                              COMMIT
                                                |
                                                v
                                     Chạy kiểm tra đã hoãn
                                                |
                                      +---------+---------+
                                      |                   |
                                   Hợp lệ              Không hợp lệ
                                      |                   |
                                      v                   v
                                   COMMIT             ROLLBACK
```

Bài thuộc chương **Trigger và luật** trong module *Database Engine Relational PostgreSQL*. Bạn sẽ học:

- Thế nào là constraint trigger và khác gì một trigger thông thường.
- `DEFERRABLE`, `NOT DEFERRABLE`, `INITIALLY IMMEDIATE`, `INITIALLY DEFERRED`.
- Thời điểm thực thi `AFTER ROW` và cách `SET CONSTRAINTS ... IMMEDIATE/DEFERRED` tác động đến những sự kiện đang chờ.
- Các giới hạn quan trọng: `WHEN` được kiểm tra ngay; constraint trigger không phải `BEFORE`, `STATEMENT` hay transition-table trigger.
- Ví dụ hai bảng có ràng buộc tổng phân bổ, bao gồm `INSERT`, `UPDATE`, `DELETE`, di chuyển dòng sang nhóm khác và rollback.
- Khác biệt giữa constraint trigger tự viết và `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY`, `EXCLUDE` có `DEFERRABLE`.
- Những trường hợp trì hoãn **không** thể dùng, ví dụ `CHECK` và `NOT NULL`.
- Concurrency, write skew, row locks, isolation levels, chi phí kiểm tra N lần và kế hoạch vận hành.
- Bài tập thực hành cùng câu trả lời và checklist thiết kế.

> **Quan trọng:** “Trì hoãn” không đồng nghĩa “bỏ qua kiểm tra”. Ràng buộc vẫn phải đúng khi các kiểm tra đang chờ được thực thi. Nếu sai ở cuối transaction, `COMMIT` thất bại và các thay đổi của transaction không được xác nhận.

---

## 1. Đặt vấn đề: đúng ở từng statement hay đúng khi commit?

### 1.1. Ràng buộc bất biến của hệ thống

Một *invariant* là điều kiện phải được duy trì tại những thời điểm được quy định. Ví dụ:

```text
Một đợt ngân sách đã chốt:
    expected_total = SUM(amount của tất cả allocations)
```

Nếu ngân sách là 100:

```text
Allocation A = 60
Allocation B = 40
-----------------
SUM          = 100  -> hợp lệ
```

Khi người dùng muốn phân bổ lại:

```text
Bước 1:
    A = 70
    B = 40
    SUM = 110 -> tạm thời không hợp lệ

Bước 2:
    A = 70
    B = 30
    SUM = 100 -> hợp lệ khi commit
```

Trong một transaction có hai câu UPDATE, các thay đổi chưa commit thường chưa được transaction khác thấy dưới quy tắc MVCC tương ứng. Vì thế có những nghiệp vụ cho phép trạng thái **tạm thời không thỏa ràng buộc trong transaction đang thực hiện**, miễn mọi kiểm tra cuối transaction đều thành công.

### 1.2. Ba cách xử lý

1. **Thiết kế một câu SQL nguyên tử** để không có trạng thái sai giữa các statement; thường là cách đơn giản nhất nếu khả thi.
2. **Dùng ràng buộc native DEFERRABLE** nếu invariant là uniqueness, foreign key, exclusion hoặc một trường hợp PostgreSQL hỗ trợ trực tiếp.
3. **Dùng deferrable constraint trigger** khi kiểm tra nghiệp vụ cần SQL tùy biến, thường liên quan nhiều hàng hoặc nhiều bảng, và không biểu diễn được bằng constraint native.

Không chọn trigger ngay khi chỉ cần `NOT NULL`, `CHECK`, `UNIQUE` hoặc `FOREIGN KEY`. Các constraint native thường rõ ràng, tối ưu và dễ vận hành hơn.

### 1.3. Trì hoãn không phải một isolation level

`DEFERRABLE` quyết định **thời điểm thực thi kiểm tra**, không tự:

- Tăng isolation level.
- Khóa toàn bộ các hàng liên quan.
- Bảo đảm mọi transaction đồng thời đều nhìn thấy thay đổi của nhau.
- Biến một câu `SELECT SUM(...)` thành phép kiểm tra an toàn tuyệt đối trước write skew.

Đặc biệt với invariant đa hàng/đa bảng, cần thiết kế concurrency riêng, không chỉ thêm `INITIALLY DEFERRED`.

---

## 2. Trigger thường và constraint trigger

### 2.1. Trigger thông thường

Một trigger PostgreSQL có thể khai báo:

```sql
CREATE TRIGGER ordinary_audit
AFTER UPDATE ON some_table
FOR EACH ROW
EXECUTE FUNCTION some_trigger_function();
```

Trigger `AFTER ROW` thông thường được thực thi theo cơ chế trigger sau statement tương ứng; không có chế độ điều khiển thời điểm bằng `SET CONSTRAINTS`.

Tùy event và loại trigger, PostgreSQL còn hỗ trợ `BEFORE`, `AFTER`, `INSTEAD OF`, `FOR EACH STATEMENT` và `FOR EACH ROW`.

### 2.2. Constraint trigger

Một constraint trigger được khai báo bằng:

```sql
CREATE CONSTRAINT TRIGGER some_constraint_trigger
AFTER INSERT OR UPDATE OR DELETE ON some_table
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION some_trigger_function();
```

Các thuộc tính trọng yếu:

- Dùng cú pháp **`CREATE CONSTRAINT TRIGGER`**.
- Phải là **`AFTER`**.
- Phải là **`FOR EACH ROW`**.
- Gắn vào **bảng thường**, không phải foreign table hoặc view.
- Gọi function trả **`trigger`**, giống quy tắc của các trigger function PL/pgSQL khác.
- Với `DEFERRABLE`, thời điểm gọi function có thể được điều khiển bằng `SET CONSTRAINTS`.
- Function được kỳ vọng **ném exception** nếu ràng buộc không được đáp ứng.

### 2.3. “Constraint” không khiến PostgreSQL tự hiểu nghiệp vụ

Nếu function chỉ:

```sql
BEGIN
    RETURN NEW;
END;
```

thì trigger **không hề kiểm tra** số liệu có đúng hay không. `CREATE CONSTRAINT TRIGGER` chỉ cung cấp **cơ chế kích hoạt và thời điểm**; người viết phải cài đặt logic kiểm tra thật.

### 2.4. Bảng so sánh

| Đặc điểm | Trigger thường | Constraint trigger |
|---|---|---|
| Từ khóa tạo | `CREATE TRIGGER` | `CREATE CONSTRAINT TRIGGER` |
| `BEFORE ROW` | Có | Không |
| `AFTER ROW` | Có | Có, bắt buộc |
| `AFTER STATEMENT` | Có | Không |
| `INSTEAD OF` trên view | Có | Không |
| `SET CONSTRAINTS` đổi thời điểm | Không | Có nếu `DEFERRABLE` |
| `REFERENCING NEW TABLE/OLD TABLE` | Có với các AFTER trigger phù hợp | Không dùng chung với constraint trigger |
| Gán `NEW.column` trước khi ghi | BEFORE trigger thích hợp | Không, vì chạy AFTER |
| Kiểm tra invariant ở cuối transaction | Không trực tiếp qua `SET CONSTRAINTS` | Có |
| Rủi ro chi phí mỗi hàng | Có | Có; sự kiện có thể tích lũy đến commit |

### 2.5. Trigger và rule không phải một thứ

**Rule** trong PostgreSQL là cơ chế **rewrite** câu SQL trước khi lập kế hoạch thực thi. Trigger phản ứng với các event phát sinh khi chạy DML theo loại trigger. Một rule không tương đương với một ràng buộc cuối transaction; không dùng `CREATE RULE` để thay tự động cho constraint trigger có deferral.

Trong đa số tình huống kiểm tra bất biến nghiệp vụ hiện đại, nên ưu tiên constraint native, trigger hoặc transaction protocol rõ ràng thay vì rules phức tạp khó dự đoán.

---

## 3. DEFERRABLE và trạng thái ban đầu của constraint

### 3.1. Ba trạng thái cần biết

| Khai báo | Ý nghĩa |
|---|---|
| `NOT DEFERRABLE` | Không cho hoãn; không thể chuyển sang DEFERRED bằng `SET CONSTRAINTS` |
| `DEFERRABLE INITIALLY IMMEDIATE` | Có thể hoãn, nhưng mặc định kiểm tra cuối mỗi statement |
| `DEFERRABLE INITIALLY DEFERRED` | Có thể hoãn, và mặc định kiểm tra khi kết thúc transaction |

Ví dụ:

```sql
CREATE CONSTRAINT TRIGGER sample_guard
AFTER UPDATE ON some_table
DEFERRABLE INITIALLY IMMEDIATE
FOR EACH ROW
EXECUTE FUNCTION sample_function();
```

Trigger này mặc định kiểm tra sau mỗi câu UPDATE, nhưng một transaction có thể chuyển nó sang chế độ deferred.

### 3.2. Không nhầm DEFERRABLE và INITIALLY DEFERRED

`DEFERRABLE` nghĩa là **được phép đổi thời điểm**; `INITIALLY DEFERRED` là **giá trị mặc định lúc bắt đầu transaction**.

Hai cấu hình khác nhau:

```sql
DEFERRABLE INITIALLY IMMEDIATE
```

và:

```sql
DEFERRABLE INITIALLY DEFERRED
```

đều có thể được chuyển giữa `IMMEDIATE` và `DEFERRED` trong transaction bằng `SET CONSTRAINTS`.

### 3.3. “IMMEDIATE” không luôn nghĩa là kiểm ngay giữa từng row

Theo hợp đồng chung của `SET CONSTRAINTS`, constraint ở chế độ `IMMEDIATE` được kiểm tra tại **cuối statement**. Với constraint không deferrable của một số loại như unique index, các chi tiết thực thi có thể xảy ra sớm hơn. Không suy rằng mọi loại constraint có cùng điểm kiểm tra ở mức mỗi tuple.

Với constraint trigger `AFTER ROW`, ở chế độ immediate, các sự kiện trigger tương ứng được thực thi tại điểm kết thúc statement; ở chế độ deferred, chúng có thể chờ tới commit.

### 3.4. Sự kiện vẫn được ghi nhận

`INITIALLY DEFERRED` không có nghĩa là PostgreSQL quên thay đổi. Khi INSERT/UPDATE/DELETE phù hợp:

1. Event phát sinh.
2. PostgreSQL xác định có cần xếp hàng cho trigger hay không.
3. Function có thể chờ đến cuối transaction.
4. Khi kiểm tra thực thi, function kiểm tra invariant và ném lỗi khi cần.

Chính sách “khi nào cần kiểm tra” vẫn do khai báo event, điều kiện `WHEN` và logic trong function quyết định.

---

## 4. SET CONSTRAINTS: chuyển chế độ trong một transaction

### 4.1. Cú pháp

```sql
SET CONSTRAINTS ALL DEFERRED;
SET CONSTRAINTS ALL IMMEDIATE;

SET CONSTRAINTS constraint_name DEFERRED;
SET CONSTRAINTS constraint_name IMMEDIATE;
```

Có thể chỉ rõ nhiều tên:

```sql
SET CONSTRAINTS guard_a, guard_b DEFERRED;
```

Tên constraint có thể được **schema-qualified**.

### 4.2. Chỉ có tác dụng trong transaction hiện tại

```sql
BEGIN;
SET CONSTRAINTS ALL DEFERRED;
-- Thực hiện các bước DML.
COMMIT;
```

Sau khi transaction kết thúc, transaction mới lại bắt đầu theo trạng thái `INITIALLY ...` của từng constraint.

Khi gọi `SET CONSTRAINTS` ngoài một transaction block, PostgreSQL phát cảnh báo và không có hiệu lực lâu dài như thay đổi cấu hình toàn session.

### 4.3. ALL có thể ảnh hưởng các ràng buộc khác

`SET CONSTRAINTS ALL DEFERRED` có thể hoãn nhiều constraint deferrable trong transaction, bao gồm những FK/unique/exclusion constraints phù hợp. Không dùng `ALL` một cách vô thức khi chỉ muốn hoãn một trigger nghiệp vụ.

Trong một migration hoặc stored procedure quan trọng, ưu tiên **chọn đúng tên** constraint cần đổi.

### 4.4. DEFERRED → IMMEDIATE có hiệu lực hồi tố

Điểm đặc biệt:

```sql
BEGIN;

SET CONSTRAINTS some_guard DEFERRED;

-- Thay đổi dữ liệu, tạo các pending checks.

SET CONSTRAINTS some_guard IMMEDIATE;

COMMIT;
```

Khi chuyển từ deferred sang immediate, PostgreSQL **thực thi ngay các kiểm tra đã bị hoãn và đang chờ**. Nếu vi phạm, chính câu `SET CONSTRAINTS ... IMMEDIATE` báo lỗi và không chuyển thành công sang chế độ mới.

Đây là cách hữu ích để “chốt” invariant ở một mốc trước commit:

```text
BEGIN
    |
    v
Nhiều UPDATE tạm sai
    |
    v
UPDATE cuối sửa đúng
    |
    v
SET CONSTRAINTS ... IMMEDIATE
    |
    +--> PASS: tiếp tục những thao tác khác và COMMIT
    |
    +--> FAIL: xử lý transaction lỗi/ROLLBACK
```

### 4.5. IMMEDIATE → DEFERRED không “quay ngược” kiểm tra đã xảy ra

Nếu statement đã bị lỗi trong chế độ immediate và transaction đã rơi vào trạng thái lỗi, chuyển `SET CONSTRAINTS ... DEFERRED` sau đó không sửa được statement trước. Phải chủ động sử dụng `DEFERRED` **trước** các DML cần trạng thái trung gian.

### 4.6. Tên không phải lúc nào cũng độc nhất trong schema

PostgreSQL cho phép tên constraint được dùng lại trên các bảng khác nhau. Vì vậy `SET CONSTRAINTS schema.name` có thể tác động nhiều constraint trùng tên trong schema theo quy tắc tra cứu. Đặt tên rõ, tránh tái sử dụng cho những nghiệp vụ không liên quan.

---

## 5. Phòng thực hành: bảng ngân sách và các khoản phân bổ

Chúng ta viết **constraint trigger có thể trì hoãn** để kiểm tra một invariant thực tế.

### 5.1. Điều kiện bài toán

- Mỗi batch có `batch_id` duy nhất.
- `status` chỉ có `draft` hoặc `sealed`.
- `expected_total` là tổng ngân sách kỳ vọng, không âm.
- Mỗi allocation thuộc một batch có thật.
- `amount` của allocation không âm.
- Khi batch là `draft`, tổng allocation có thể chưa bằng expected_total.
- Khi batch là `sealed`, tổng allocation **phải bằng expected_total**.
- Một batch sealed có expected_total bằng 0 và chưa có allocations được coi là hợp lệ trong mô hình lab. Nếu nghiệp vụ yêu cầu ít nhất một dòng, cần kiểm tra thêm `COUNT(*) > 0`.

### 5.2. Tạo schema riêng

```sql
CREATE SCHEMA deferred_trigger_lab;
```

Schema dùng cho database thử nghiệm. Nếu schema đã tồn tại, không xóa bằng `DROP SCHEMA ... CASCADE` trong database dùng chung; chọn database lab mới.

### 5.3. Tạo bảng batches

```sql
CREATE TABLE deferred_trigger_lab.batches (
    batch_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'sealed')),
    expected_total NUMERIC(18,2) NOT NULL
        CHECK (expected_total >= 0),
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT transaction_timestamp()
);
```

Ở đây `batch_id` được nhập tường minh để các ví dụ có ID cố định và dễ theo dõi. Trong production có thể dùng identity/sequence hoặc UUID.

### 5.4. Tạo bảng allocations

```sql
CREATE TABLE deferred_trigger_lab.allocations (
    line_id BIGINT PRIMARY KEY,
    batch_id BIGINT NOT NULL
        REFERENCES deferred_trigger_lab.batches(batch_id)
        ON DELETE CASCADE,
    line_name TEXT NOT NULL,
    amount NUMERIC(18,2) NOT NULL
        CHECK (amount >= 0)
);
```

**Lưu ý quan trọng:** `CHECK (amount >= 0)` kiểm tra dữ liệu **một hàng** và không trì hoãn được. Ràng buộc “tổng allocations = expected_total” lại đòi đọc **nhiều hàng**, nên ta dùng một function kiểm tra do mình viết.

### 5.5. Thêm index để tìm allocations theo batch

```sql
CREATE INDEX allocations_batch_id_idx
ON deferred_trigger_lab.allocations (batch_id);
```

Function kiểm tra cần chạy:

```sql
SELECT SUM(amount)
FROM deferred_trigger_lab.allocations
WHERE batch_id = ...;
```

Index trên `batch_id` có thể giảm số row phải đọc khi bảng allocation lớn và các batch có tỷ lệ nhỏ trong tổng dữ liệu. Với bảng nhỏ, planner vẫn có thể Seq Scan vì rẻ hơn.

### 5.6. Sơ đồ quan hệ

```text
deferred_trigger_lab.batches
  batch_id (PK) ─────────────────────┐
  tenant_id                          │
  status = draft | sealed            │
  expected_total                     │
                                     │ FK
                                     ▼
deferred_trigger_lab.allocations
  line_id (PK)
  batch_id (FK)
  line_name
  amount

Invariant:
  IF batches.status = 'sealed'
  THEN batches.expected_total
       = COALESCE(SUM(allocations.amount), 0)
```

---

## 6. Viết function kiểm tra invariant

Ta tách logic nghiệp vụ vào một function thường để có thể gọi từ nhiều trigger và kiểm tra thủ công khi cần.

### 6.1. Function kiểm tra một batch

```sql
CREATE OR REPLACE FUNCTION
    deferred_trigger_lab.assert_sealed_batch_total(
        p_batch_id BIGINT
    )
RETURNS void
LANGUAGE plpgsql
AS $function$
DECLARE
    v_status TEXT;
    v_expected NUMERIC;
    v_actual NUMERIC;
BEGIN
    SELECT b.status, b.expected_total
    INTO v_status, v_expected
    FROM deferred_trigger_lab.batches AS b
    WHERE b.batch_id = p_batch_id;

    -- Bảng mẹ đã bị xóa trong transaction:
    -- không còn một batch sealed để kiểm tra.
    IF NOT FOUND THEN
        RETURN;
    END IF;

    -- Draft được phép chưa cân đối.
    IF v_status <> 'sealed' THEN
        RETURN;
    END IF;

    SELECT COALESCE(SUM(a.amount), 0)
    INTO v_actual
    FROM deferred_trigger_lab.allocations AS a
    WHERE a.batch_id = p_batch_id;

    IF v_actual IS DISTINCT FROM v_expected THEN
        RAISE EXCEPTION
            'Batch %: expected total %, actual allocation total %',
            p_batch_id, v_expected, v_actual
            USING
                ERRCODE = '23514',
                CONSTRAINT = 'batch_total_matches_allocations';
    END IF;
END;
$function$;
```

### 6.2. Vì sao dùng NOT FOUND?

Khi parent batch bị xóa và allocations bị xóa theo `ON DELETE CASCADE`, những event đã xếp hàng của trigger vẫn có thể tồn tại. Function được gọi vào cuối transaction có thể không tìm thấy parent nữa.

Đây là hành vi hợp lệ của mô hình: không còn parent sealed thì không còn invariant cần kiểm tra cho batch đó. Function `RETURN;` để bỏ qua.

Không thay `IF NOT FOUND` bằng điều kiện sai như `IF v_status = NULL THEN`.

### 6.3. Tại sao chỉ kiểm tra khi sealed?

Ở trạng thái draft, người dùng còn được thêm/xóa phân bổ. Nếu kiểm tra số tiền trong mọi trạng thái, một transaction tạo batch rồi thêm allocations có thể bị hạn chế không cần thiết.

`IF v_status <> 'sealed' THEN RETURN; END IF;` là quy tắc nghiệp vụ của lab, không phải đặc điểm bắt buộc của constraint trigger.

### 6.4. COALESCE(SUM(...),0)

`SUM(amount)` trên tập không có row trả `NULL`, không phải 0. Vì định nghĩa lab coi không phân bổ là tổng 0, ta dùng:

```sql
COALESCE(SUM(amount), 0)
```

Nếu nghiệp vụ quy định sealed batch **phải có ít nhất một dòng**, ngoài tổng tiền còn cần `COUNT(*)` hoặc `EXISTS`.

### 6.5. IS DISTINCT FROM phù hợp với kiểm tra dữ liệu

`v_actual` và `v_expected` về cơ bản không NULL trong lab nhờ `COALESCE` và `NOT NULL`, nhưng `IS DISTINCT FROM` vẫn thể hiện rõ ý định “hai giá trị phải bằng nhau, kể cả khi sau này kiểu dữ liệu/logic đổi”.

Trong một mô hình cho phép NULL, `<>` có thể trả UNKNOWN và làm trigger **không** ném lỗi khi một vế NULL. Dùng toán tử so sánh có ngữ nghĩa NULL rõ là thực hành tốt.

### 6.6. SQLSTATE khi báo lỗi

`ERRCODE = '23514'` là mã `check_violation`. Ta dùng mã này cho một invariant nghiệp vụ tự kiểm tra. Giá trị `CONSTRAINT = 'batch_total_matches_allocations'` mô tả tên logic trong diagnostic, không đồng nghĩa PostgreSQL tự tạo một `CHECK` SQL native mang tên đó.

Ứng dụng nên nhận diện `SQLSTATE` và thông tin lỗi có cấu trúc thay vì chỉ parse message tiếng Anh.

### 6.7. Function thường chưa tự được gọi

Tới bước này, function chỉ là logic được định nghĩa trong database:

```sql
SELECT deferred_trigger_lab.assert_sealed_batch_total(101);
```

Nó sẽ kiểm tra batch 101 nếu tồn tại, nhưng **chưa tự chạy** sau INSERT/UPDATE/DELETE. Cần gắn trigger cho các thao tác có thể thay đổi invariant.

---

## 7. Viết một trigger function dùng chung cho hai bảng

Invariant có thể bị ảnh hưởng khi sửa:

- **Header batch:** `status` hoặc `expected_total` thay đổi.
- **Allocation:** thêm một dòng, sửa `amount`, chuyển `batch_id` sang nhóm khác hoặc xóa dòng.
- **Header bị xóa:** các allocations liên quan có thể bị xóa theo FK CASCADE.

Vì vậy cần gắn trigger ở **cả hai bảng**.

### 7.1. Trigger function

```sql
CREATE OR REPLACE FUNCTION
    deferred_trigger_lab.enforce_batch_total_deferred()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM deferred_trigger_lab.assert_sealed_batch_total(
            NEW.batch_id
        );
        RETURN NEW;

    ELSIF TG_OP = 'DELETE' THEN
        PERFORM deferred_trigger_lab.assert_sealed_batch_total(
            OLD.batch_id
        );
        RETURN OLD;

    ELSIF TG_OP = 'UPDATE' THEN
        -- Trường hợp dòng bị chuyển từ batch cũ sang batch mới:
        -- cả hai batch đều có thể bị sai tổng.
        IF OLD.batch_id IS DISTINCT FROM NEW.batch_id THEN
            PERFORM deferred_trigger_lab.assert_sealed_batch_total(
                OLD.batch_id
            );
        END IF;

        PERFORM deferred_trigger_lab.assert_sealed_batch_total(
            NEW.batch_id
        );
        RETURN NEW;
    END IF;

    RAISE EXCEPTION
        'Unsupported trigger event %', TG_OP
        USING ERRCODE = '22023';
END;
$function$;
```

### 7.2. Tại sao có NEW và OLD?

Với row-level trigger:

| Event | Giá trị row phù hợp |
|---|---|
| `INSERT` | `NEW` |
| `UPDATE` | `OLD` và `NEW` |
| `DELETE` | `OLD` |

Sự kiện `DELETE` không có `NEW` row như INSERT. Đừng viết một function luôn đọc `NEW.batch_id` mà không phân biệt `TG_OP`.

### 7.3. UPDATE batch_id cần kiểm tra hai nhóm

Giả sử allocation 1002 chuyển từ batch 101 sang batch 102:

```text
Batch 101: mất amount của dòng 1002
Batch 102: nhận amount của dòng 1002
```

Nếu chỉ kiểm tra `NEW.batch_id`, batch 101 có thể bị sai tổng mà không được đưa vào kiểm tra.

Vì vậy với `UPDATE`, function kiểm tra **batch cũ nếu ID đổi**, rồi batch mới.

### 7.4. AFTER trigger không được dùng để sửa NEW

`RETURN NEW` và `RETURN OLD` ở đây thể hiện cấu trúc function, nhưng với **AFTER ROW trigger**, giá trị trả về không có tác dụng thay row đã được ghi.

Nếu mục tiêu là chuẩn hóa `NEW.amount` trước khi ghi, đó là trách nhiệm của một `BEFORE` trigger hoặc constraints/SQL expression phù hợp. Constraint trigger trong bài chỉ **xác minh và có thể từ chối transaction**.

### 7.5. Deferred function phải kiểm tra dữ liệu hiện tại

Trigger function ở đây **không** dùng giá trị `NEW.amount` của một event cũ để suy ra tổng; nó truy vấn:

```sql
SELECT COALESCE(SUM(amount), 0)
FROM deferred_trigger_lab.allocations
WHERE batch_id = ...;
```

Vì một row có thể được sửa nhiều lần trong cùng transaction, event được xếp hàng trước có thể chứa ảnh cũ của `NEW`. Kiểm tra lại **trạng thái dữ liệu quan sát được tại lúc function chạy** là điều quan trọng để không từ chối một chuỗi sửa hợp lệ chỉ vì trạng thái tạm.

---

## 8. Tạo hai constraint triggers INITIALLY DEFERRED

### 8.1. Trigger cho batch header

```sql
CREATE CONSTRAINT TRIGGER batch_total_guard_header
AFTER INSERT OR UPDATE OR DELETE
ON deferred_trigger_lab.batches
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION
    deferred_trigger_lab.enforce_batch_total_deferred();
```

### 8.2. Trigger cho allocations

```sql
CREATE CONSTRAINT TRIGGER batch_total_guard_lines
AFTER INSERT OR UPDATE OR DELETE
ON deferred_trigger_lab.allocations
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION
    deferred_trigger_lab.enforce_batch_total_deferred();
```

Hai trigger dùng **cùng một function** vì cả hai bảng đều có `batch_id` và invariant chung. Đây là một lựa chọn để giảm trùng code; trong hệ lớn có thể tách function nếu event semantics phức tạp.

### 8.3. Vì sao không chỉ gắn trigger lên allocations?

Giả sử batch 101 đã sealed với tổng 100, sau đó:

```sql
UPDATE deferred_trigger_lab.batches
SET expected_total = 120
WHERE batch_id = 101;
```

Không hề có allocation nào đổi, nhưng invariant đã sai. Nếu chỉ có trigger trên allocations thì thay đổi header **không tạo event kiểm tra** tương ứng. Vì vậy cần trigger trên batches.

### 8.4. Vì sao không chỉ gắn trigger lên batches?

Giả sử:

```sql
UPDATE deferred_trigger_lab.allocations
SET amount = 999
WHERE line_id = 1001;
```

Header không đổi. Trigger trên batches không được gọi. Vì vậy cần trigger trên allocations.

### 8.5. Vì sao có cả INSERT, UPDATE, DELETE?

| Event | Có thể thay đổi tổng? |
|---|---|
| INSERT batch sealed | Có thể tạo invariant phải thỏa khi commit |
| UPDATE batch status/expected_total | Có |
| DELETE batch | Batch biến mất; cần xử lý queued event phù hợp |
| INSERT allocation | Có |
| UPDATE allocation amount/batch_id | Có |
| DELETE allocation | Có |

Nếu business cho phép `TRUNCATE` bảng, đó là **một loại statement riêng** và không kích hoạt row-level DELETE triggers theo cách một DELETE từng row. Cần hạn chế quyền TRUNCATE và thiết kế quy trình migration/bulk load đúng; **constraint trigger row-level không là giải pháp kiểm soát mọi TRUNCATE**.

### 8.6. Tại sao INITIALLY DEFERRED?

Chúng ta muốn những giao dịch bình thường có thể:

1. Chỉnh nhiều dòng allocation.
2. Tạm thời làm sai tổng.
3. Sửa lại trước khi commit.
4. Chỉ chấp nhận commit nếu invariant đúng.

Nếu một nghiệp vụ đa số chỉ cập nhật một lần và muốn phát hiện lỗi sớm, có thể chọn `DEFERRABLE INITIALLY IMMEDIATE` rồi chỉ `SET CONSTRAINTS ... DEFERRED` trong workflow cần nhiều bước.

---

## 9. Thí nghiệm A: tạo batch sealed và các dòng trong một transaction

### 9.1. Tạo batch trước khi có allocation

```sql
BEGIN;

INSERT INTO deferred_trigger_lab.batches
    (batch_id, tenant_id, status, expected_total, description)
VALUES
    (101, 1, 'sealed', 100.00, 'November allocation');
```

Ngay sau INSERT, batch 101 là sealed nhưng có tổng allocations bằng 0. Invariant **tạm thời** sai. Vì trigger `INITIALLY DEFERRED`, event được giữ để kiểm tra khi transaction kết thúc, thay vì từ chối ngay sau INSERT.

### 9.2. Thêm các dòng cân đối

```sql
INSERT INTO deferred_trigger_lab.allocations
    (line_id, batch_id, line_name, amount)
VALUES
    (1001, 101, 'Infrastructure', 60.00),
    (1002, 101, 'Support', 40.00);

COMMIT;
```

Trong cùng transaction, tổng cuối là 100. Khi các kiểm tra deferred chạy, batch 101 thỏa invariant nên commit thành công, giả sử không có lỗi constraint khác.

### 9.3. Xem kết quả

```sql
SELECT
    b.batch_id,
    b.status,
    b.expected_total,
    COALESCE(SUM(a.amount), 0) AS actual_total
FROM deferred_trigger_lab.batches AS b
LEFT JOIN deferred_trigger_lab.allocations AS a
    ON a.batch_id = b.batch_id
WHERE b.batch_id = 101
GROUP BY b.batch_id, b.status, b.expected_total;
```

Kết quả mong đợi:

```text
batch_id | status | expected_total | actual_total
---------+--------+----------------+-------------
101      | sealed | 100.00         | 100.00
```

### 9.4. Trì hoãn cho phép “sửa trong transaction”, không cho “ghi sai vĩnh viễn”

Nếu kết thúc transaction ngay sau INSERT batch sealed 100 mà không thêm allocations, `COMMIT` sẽ báo lỗi từ trigger. Toàn bộ transaction không được xác nhận, nên batch sealed sai không được lưu thành công.

---

## 10. Thí nghiệm B: cập nhật hai dòng, tạm sai rồi đúng

### 10.1. Trạng thái ban đầu

```text
line 1001 = 60.00
line 1002 = 40.00
expected_total = 100.00
```

### 10.2. Thay đổi qua hai statement

```sql
BEGIN;

UPDATE deferred_trigger_lab.allocations
SET amount = 70.00
WHERE line_id = 1001;

-- Tổng tạm thời = 70 + 40 = 110

UPDATE deferred_trigger_lab.allocations
SET amount = 30.00
WHERE line_id = 1002;

-- Tổng đã trở lại = 70 + 30 = 100

SET CONSTRAINTS
    deferred_trigger_lab.batch_total_guard_header,
    deferred_trigger_lab.batch_total_guard_lines
IMMEDIATE;

-- Đã chạy các kiểm tra tồn đọng và chúng đều hợp lệ.

ROLLBACK;
```

Ở ví dụ này chúng ta dùng `ROLLBACK` cuối để **giữ nguyên dữ liệu seed 60/40**, phục vụ các thí nghiệm phía sau. Nếu nghiệp vụ thật muốn lưu 70/30, có thể `COMMIT` thay cho `ROLLBACK` sau khi kiểm tra thành công.

### 10.3. Quan sát giữa hai UPDATE

Trong transaction, có thể chèn thêm:

```sql
SELECT
    COALESCE(SUM(amount), 0) AS current_total
FROM deferred_trigger_lab.allocations
WHERE batch_id = 101;
```

Sau UPDATE thứ nhất, transaction của chính bạn có thể thấy tổng 110. Constraint chưa được kiểm tra ngay do chế độ deferred.

Sau UPDATE thứ hai, tổng là 100. Khi `SET CONSTRAINTS ... IMMEDIATE` được gọi, các event chờ được kiểm tra và hợp lệ.

### 10.4. Không nhầm với việc các transactions khác nhìn thấy giá trị 110

Các transaction khác thường không thấy những UPDATE **chưa commit** ở mức isolation phổ biến của PostgreSQL. Việc cho phép trạng thái tạm trong transaction không có nghĩa dữ liệu sai đã được công khai cho mọi session.

Tuy nhiên, việc transaction khác có nhìn thấy một thay đổi cụ thể hay không còn phụ thuộc isolation level, snapshot và commit timing; không dùng deferred trigger để thay cơ chế kiểm soát giao dịch.

---

## 11. Thí nghiệm C: lỗi bị trì hoãn đến cuối transaction

### 11.1. Lỗi không được phát hiện ngay sau một UPDATE

Thử riêng trên database lab:

```sql
BEGIN;

UPDATE deferred_trigger_lab.allocations
SET amount = 75.00
WHERE line_id = 1001;

-- Tổng hiện là 75 + 40 = 115, nhưng trigger còn deferred.

-- Bỏ comment dòng tiếp theo để quan sát lỗi ngay tại COMMIT:
-- COMMIT;

ROLLBACK;
```

Nếu `COMMIT` được thực thi, constraint trigger sẽ chạy và phát sinh exception vì expected_total 100 khác actual_total 115. Transaction không được commit.

### 11.2. Kiểm tra sớm bằng SET CONSTRAINTS IMMEDIATE

```sql
BEGIN;

UPDATE deferred_trigger_lab.allocations
SET amount = 75.00
WHERE line_id = 1001;

-- Bỏ comment dòng tiếp theo để thử:
-- SET CONSTRAINTS
--     deferred_trigger_lab.batch_total_guard_lines
-- IMMEDIATE;

ROLLBACK;
```

Khi bỏ comment `SET CONSTRAINTS ... IMMEDIATE`, PostgreSQL kiểm tra các event chờ **ngay tại statement SET CONSTRAINTS** và báo lỗi trước COMMIT nếu tổng vẫn là 115.

**Lưu ý thực hành:** Khi một statement gây exception bên trong transaction thông thường, session có thể ở trạng thái transaction lỗi và cần `ROLLBACK` trước khi tiếp tục. Đừng chạy các ví dụ lỗi này cùng một batch migration không cho phép lỗi.

### 11.3. Vì sao không chỉ dùng IF trong application?

Application có thể kiểm tra tổng trước COMMIT, nhưng:

- Một code path khác có thể quên gọi.
- Một session SQL khác có thể sửa bảng trực tiếp.
- Một migration có thể đổi dữ liệu.
- Kết quả kiểm tra trước đó có thể trở nên không còn phù hợp dưới concurrency.

Constraint trigger giúp **gắn logic kiểm tra vào thay đổi dữ liệu tại database**, nhưng vẫn cần bảo vệ concurrency và quyền.

---

## 12. Thí nghiệm D: draft chưa cần cân đối, sealed thì phải cân đối

### 12.1. Tạo batch draft

```sql
INSERT INTO deferred_trigger_lab.batches
    (batch_id, tenant_id, status, expected_total, description)
VALUES
    (102, 1, 'draft', 200.00, 'Draft allocation');

INSERT INTO deferred_trigger_lab.allocations
    (line_id, batch_id, line_name, amount)
VALUES
    (2001, 102, 'Planning', 10.00);
```

Sau hai INSERT, batch 102 vẫn là draft, nên không bắt buộc tổng 10 bằng expected 200.

### 12.2. Chốt batch trong một transaction

```sql
BEGIN;

UPDATE deferred_trigger_lab.batches
SET status = 'sealed'
WHERE batch_id = 102;

-- Tổng hiện có = 10, expected_total = 200.
-- Chưa bị từ chối vì trigger deferred.

INSERT INTO deferred_trigger_lab.allocations
    (line_id, batch_id, line_name, amount)
VALUES
    (2002, 102, 'Delivery', 190.00);

COMMIT;
```

Lúc commit, tổng 10 + 190 = 200; invariant của batch sealed hợp lệ.

### 12.3. Chốt mà không bổ sung phần thiếu

Trên một draft batch khác có tổng 10, nếu chỉ `UPDATE status='sealed'` rồi COMMIT mà không thêm 190, deferred trigger sẽ từ chối transaction.

Điều này minh họa hai tầng:

- `CHECK status IN (...)` đảm bảo status thuộc tập giá trị.
- Constraint trigger đảm bảo **quan hệ giữa status, expected_total và tập allocations**.

### 12.4. Trì hoãn có ích cả khi thêm và khi sửa header

Batch đang sealed 100 có thể được sửa đồng thời `expected_total=120` và thêm allocation 20 trong cùng transaction. Nếu cả hai thao tác hoàn tất trước điểm kiểm tra, kết quả cuối vẫn hợp lệ.

---

## 13. Thí nghiệm E: di chuyển allocation sang batch khác

Giả sử hiện có:

```text
Batch 101:
  expected_total = 100
  allocations = 60 + 40

Batch 102:
  expected_total = 200
  allocations = 10 + 190
```

### 13.1. Một thao tác thay đổi hai nhóm

Chuyển dòng 1002 trị giá 40 từ batch 101 sang 102:

```sql
BEGIN;

UPDATE deferred_trigger_lab.allocations
SET batch_id = 102
WHERE line_id = 1002;

-- Batch 101: tổng = 60
-- Batch 102: tổng = 240

UPDATE deferred_trigger_lab.batches
SET expected_total = 60
WHERE batch_id = 101;

UPDATE deferred_trigger_lab.batches
SET expected_total = 240
WHERE batch_id = 102;

SET CONSTRAINTS
    deferred_trigger_lab.batch_total_guard_header,
    deferred_trigger_lab.batch_total_guard_lines
IMMEDIATE;

-- Đủ điều kiện kiểm tra; ROLLBACK để giữ dữ liệu lab gốc.
ROLLBACK;
```

Trigger function trong mục 7 kiểm tra cả `OLD.batch_id` và `NEW.batch_id` khi ID thay đổi, vì **cả nhóm cũ và nhóm mới** đều bị tác động.

### 13.2. Nếu chỉ kiểm tra nhóm mới?

Nếu function chỉ:

```sql
PERFORM assert_sealed_batch_total(NEW.batch_id);
```

thì batch 101 đã mất một dòng mà có thể không được kiểm tra sau thao tác. Đó là một lỗi thiết kế event coverage thường gặp khi dùng trigger trên nhiều nhóm.

### 13.3. Sửa khóa chính của batch

Trong lab, `batch_id` là PRIMARY KEY và được FK tham chiếu. Sửa khóa chính có những quy tắc referential action riêng. Constraint trigger chạy trên UPDATE header có thể kiểm tra cả OLD và NEW ID, nhưng **không tự thay quy tắc FK**. Hãy hạn chế đổi identity/key của thực thể nếu không có nhu cầu và migration rõ ràng.

---

## 14. WHEN trên constraint trigger: đánh giá ngay, không trì hoãn

Đây là một điểm kỹ thuật rất dễ hiểu sai.

### 14.1. Ví dụ cú pháp WHEN

```sql
-- Ví dụ khái niệm, KHÔNG tạo thêm trigger lên bảng lab:
--
-- CREATE CONSTRAINT TRIGGER sample_sealed_check
-- AFTER INSERT OR UPDATE
-- ON deferred_trigger_lab.batches
-- DEFERRABLE INITIALLY DEFERRED
-- FOR EACH ROW
-- WHEN (NEW.status = 'sealed')
-- EXECUTE FUNCTION
--     deferred_trigger_lab.enforce_batch_total_deferred();
```

### 14.2. WHEN được kiểm tra khi nào?

Với constraint trigger, biểu thức `WHEN` được đánh giá **ngay sau row operation**, tại thời điểm quyết định có xếp hàng event hay không; nó **không được hoãn đến cuối transaction**.

Nếu `WHEN` là FALSE/NULL, event **không được xếp hàng** để chạy deferred function về sau.

### 14.3. Bẫy trạng thái biến đổi nhiều lần

Giả sử:

```text
Đầu transaction: batch đang draft
UPDATE 1: thay expected_total, status vẫn draft
UPDATE 2: đổi status thành sealed
UPDATE 3: sửa một allocation
Cuối transaction: sealed và phải kiểm tra tổng
```

Nếu chỉ có header trigger `WHEN (NEW.status='sealed')` cho UPDATE 2, event cuối có thể đủ cho ví dụ này. Nhưng trong workflow phức tạp hơn, một `WHEN` quá hẹp có thể bỏ qua những thay đổi ảnh hưởng invariant, nhất là khi có cả OLD và NEW, DELETE, cập nhật khóa nhóm hay chuyển trạng thái ngược.

### 14.4. Chiến lược an toàn trong lab

Chúng ta **không đặt WHEN** trên hai constraint triggers và để function đọc trạng thái cuối cùng:

```sql
IF v_status <> 'sealed' THEN
    RETURN;
END IF;
```

Điều này làm phát sinh nhiều event hơn nhưng giúp tránh bỏ sót do một predicate chỉ đúng ở thời điểm DML chứ không đúng ở thời điểm invariant cần được kiểm tra.

### 14.5. WHEN có thể tối ưu nhưng phải chứng minh

Khi dữ liệu lớn, mỗi row event tiêu tốn bộ nhớ/công việc. `WHEN` lọc sớm có thể giảm số event được xếp hàng. Tuy nhiên, trước khi tối ưu cần xác định:

- Event INSERT/UPDATE/DELETE nào có thể phá invariant?
- Nếu OLD và NEW khác trạng thái thì sao?
- Nếu một dòng chuyển group thì sao?
- Nếu header bị xóa hoặc được thay thế trong transaction thì sao?
- `WHEN` có bỏ qua một trạng thái trung gian quan trọng không?

Không dùng `WHEN` như thể nó được đánh giá trên trạng thái cuối transaction.

---

## 15. AFTER ROW và giới hạn transition tables

### 15.1. Constraint trigger bắt buộc AFTER ROW

Không thể khai báo constraint trigger:

```sql
-- Không hợp lệ cho CONSTRAINT TRIGGER:
-- CREATE CONSTRAINT TRIGGER ...
-- BEFORE INSERT ON ...
-- FOR EACH STATEMENT ...
```

Constraint trigger chỉ hỗ trợ **AFTER ROW** trên bảng thường.

### 15.2. Không dùng REFERENCING NEW TABLE với constraint trigger

Một ordinary `AFTER` trigger có thể dùng transition relations:

```sql
-- Mẫu cú pháp ordinary trigger, KHÔNG phải constraint trigger:
-- CREATE TRIGGER ...
-- AFTER UPDATE ON some_table
-- REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows
-- FOR EACH STATEMENT
-- EXECUTE FUNCTION ...;
```

Transition tables cho phép thấy tập rows của statement. Nhưng PostgreSQL **không cho dùng REFERENCING transition relations với constraint trigger**.

### 15.3. Hệ quả hiệu năng

Một statement cập nhật 50.000 allocations có thể tạo nhiều row-level events. Khi kiểm tra bị trì hoãn, function có thể chạy **nhiều lần cho cùng một batch** ở cuối transaction.

Mỗi lần function lại chạy `SUM(amount)`. Đây là một hình thức **lặp công việc** có thể rất đắt nếu mỗi batch chứa nhiều allocations.

### 15.4. Không có DISTINCT tự động theo batch

PostgreSQL không tự biến các 50.000 events thành một event duy nhất `CHECK batch 101` chỉ vì chúng cùng parent ID. Function phải được thiết kế với chi phí đó trong đầu.

### 15.5. Tối ưu cần đánh đổi đúng đắn

Có thể chọn kiến trúc khác:

- Dùng **một SQL statement** cập nhật trực tiếp nhiều allocations, và kiểm tra cuối statement bằng ordinary trigger phù hợp.
- Dùng bảng tổng hợp số tiền theo batch được cập nhật atomically rồi kiểm tra trường hợp cuối transaction.
- Giữ danh sách batch “dirty” và có một bước xác thực cụ thể trước commit theo transaction protocol được quản lý.
- Thiết kế thao tác cập nhật duy nhất cho từng batch ở mức database function, không cho writes tùy tiện.
- Nếu invariant có thể diễn đạt bằng native constraint, chuyển sang native constraint.

Không vội loại bỏ trigger kiểm tra mà không có cơ chế bảo đảm tất cả đường ghi và transaction đều được xác thực.

---

## 16. Constraint trigger so với CHECK

### 16.1. CHECK phù hợp điều kiện trên một hàng

```sql
CREATE TABLE deferred_trigger_lab.single_row_demo (
    id BIGINT PRIMARY KEY,
    amount NUMERIC NOT NULL CHECK (amount >= 0),
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'sealed'))
);
```

`CHECK (amount >= 0)` không cần trigger vì kiểm tra ngay trên row được ghi.

### 16.2. CHECK không dùng để SUM bảng khác

Một ý tưởng không nên dùng:

```sql
-- Không tạo CHECK bằng function quét bảng khác rồi tưởng
-- invariant sẽ được PostgreSQL duy trì ở mọi thay đổi:
--
-- CHECK (expected_total = custom_sum_allocations(batch_id))
```

PostgreSQL không hỗ trợ các `CHECK` tham chiếu dữ liệu hàng khác/bảng khác như một ràng buộc liên hàng đáng tin cậy. Ngay cả nếu nhúng một user function đọc bảng khác vào CHECK có thể vượt qua một số giới hạn cú pháp, database **không tự kiểm tra lại CHECK của parent** khi một child thay đổi. Cách này có rủi ro consistency và dump/restore.

### 16.3. CHECK không DEFERRABLE

`CHECK` và `NOT NULL` được kiểm tra ngay theo quy tắc PostgreSQL; chúng không hỗ trợ chuyển sang deferred bằng `SET CONSTRAINTS`.

Ví dụ:

```sql
-- Không hợp lệ:
-- CREATE TABLE bad_table (
--     amount numeric CHECK (amount >= 0)
--         DEFERRABLE INITIALLY DEFERRED
-- );
```

### 16.4. Không biến constraint trigger thành lý do bỏ CHECK

Lab vẫn dùng:

```sql
amount NUMERIC(18,2) NOT NULL CHECK (amount >= 0)
```

để loại số âm ngay. Constraint trigger chỉ bổ sung invariant tổng theo batch. Cả hai có trách nhiệm khác nhau.

---

## 17. Constraint trigger so với UNIQUE và PRIMARY KEY deferrable

### 17.1. Native UNIQUE có thể DEFERRABLE

Ví dụ một bảng thẻ công việc được xếp thứ tự:

```sql
CREATE TABLE deferred_trigger_lab.board_cards (
    card_id BIGINT PRIMARY KEY,
    board_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    CONSTRAINT board_position_unique
        UNIQUE (board_id, position)
        DEFERRABLE INITIALLY DEFERRED
);
```

### 17.2. Nạp hai vị trí

```sql
INSERT INTO deferred_trigger_lab.board_cards
    (card_id, board_id, position, title)
VALUES
    (1, 10, 1, 'First'),
    (2, 10, 2, 'Second');
```

### 17.3. Đổi chỗ trong một transaction

```sql
BEGIN;

UPDATE deferred_trigger_lab.board_cards
SET position = CASE card_id
    WHEN 1 THEN 2
    WHEN 2 THEN 1
    ELSE position
END
WHERE board_id = 10
  AND card_id IN (1, 2);

COMMIT;
```

Kết quả cuối cùng không có hai thẻ cùng `(board_id,position)`. Do unique constraint được hoãn, PostgreSQL cho phép xử lý thao tác hoán đổi cần trạng thái trung gian có thể trùng key.

### 17.4. Không tự viết trigger quét bảng để thay UNIQUE

Khi yêu cầu chỉ là “không có hai row cùng key”, dùng:

```sql
UNIQUE (...) DEFERRABLE
```

thay vì:

```sql
-- Không nên tự viết:
-- SELECT COUNT(*) FROM table
-- WHERE key = NEW.key;
-- rồi RAISE EXCEPTION nếu > 1
```

Native unique constraint có cơ chế index/concurrency chuyên dụng mà một câu SELECT thường trong trigger **không tự tái tạo được**.

### 17.5. PRIMARY KEY cũng có thể DEFERRABLE

PostgreSQL cho phép `PRIMARY KEY` được khai báo `DEFERRABLE` trong những thiết kế phù hợp. Tuy nhiên, phần lớn khóa định danh thực thể không cần hoán đổi trong transaction; nên giữ mô hình khóa ổn định nếu có thể.

### 17.6. ON CONFLICT và deferrable uniqueness

Một lưu ý quan trọng: constraint uniqueness deferrable **không được dùng làm conflict arbiter** cho `INSERT ... ON CONFLICT` như constraint/index unique không deferrable phù hợp.

Vì vậy không áp `DEFERRABLE` cho mọi unique key rồi mặc định các upsert đang chạy vẫn tương thích.

### 17.7. UNIQUE và NULL

Unique constraint có những quy tắc về NULL; phiên bản PostgreSQL hiện đại còn có `NULLS NOT DISTINCT` khi cần coi NULL như giá trị không phân biệt. Đây là một vấn đề về **ngữ nghĩa khóa**, không phải lý do để chuyển sang custom constraint trigger.

---

## 18. FOREIGN KEY deferrable và thứ tự chèn dữ liệu

### 18.1. Tạo FK có thể hoãn

```sql
CREATE TABLE deferred_trigger_lab.parent_nodes (
    node_id BIGINT PRIMARY KEY
);

CREATE TABLE deferred_trigger_lab.child_nodes (
    child_id BIGINT PRIMARY KEY,
    parent_id BIGINT NOT NULL,
    CONSTRAINT child_parent_fk
        FOREIGN KEY (parent_id)
        REFERENCES deferred_trigger_lab.parent_nodes(node_id)
        DEFERRABLE INITIALLY DEFERRED
);
```

### 18.2. Chèn child trước parent trong transaction

```sql
BEGIN;

INSERT INTO deferred_trigger_lab.child_nodes
    (child_id, parent_id)
VALUES (1, 500);

-- FK tạm thời chưa được thỏa.

INSERT INTO deferred_trigger_lab.parent_nodes (node_id)
VALUES (500);

COMMIT;
```

Với FK deferred, trạng thái cuối đã có parent 500 nên transaction có thể commit thành công.

### 18.3. Tại sao nên dùng FK native?

FK có thể hoãn đã được PostgreSQL triển khai bằng cơ chế referential integrity/constraint triggers nội bộ. Không có lý do viết custom trigger chỉ để kiểm tra:

```sql
EXISTS (SELECT 1 FROM parent WHERE parent_id = ...)
```

Native FK có cơ chế locking/concurrency và semantics chuẩn mà application nên tận dụng.

### 18.4. ON DELETE NO ACTION so với RESTRICT

Với foreign key:

- `NO ACTION` có thể cho phép trì hoãn kiểm tra khi constraint được khai báo DEFERRABLE.
- `RESTRICT` là hành vi chặt hơn và **không cho trì hoãn việc từ chối tham chiếu tương ứng** như `NO ACTION`.
- Các hành động `CASCADE`, `SET NULL`, `SET DEFAULT` có quy tắc thực thi riêng; không hiểu `DEFERRABLE` là trì hoãn mọi thao tác cascade.

Khi nghiệp vụ cần xóa/thay khóa parent rồi khôi phục quan hệ trong cùng transaction, xem xét đúng action và deferral policy.

### 18.5. SET CONSTRAINTS chọn đúng FK

```sql
BEGIN;

SET CONSTRAINTS
    deferred_trigger_lab.child_parent_fk
DEFERRED;

-- Các thay đổi cần tạm thời thiếu parent.

ROLLBACK;
```

Ví dụ lab tạo FK `INITIALLY DEFERRED` nên câu SET trên mang tính minh họa cách nêu tên. Không cần chuyển lại cùng chế độ trong mọi transaction nếu default đã đáp ứng yêu cầu.

---

## 19. EXCLUDE constraint và ràng buộc không chồng lấn

### 19.1. Bài toán đặt lịch

Hai booking của cùng phòng không được trùng thời gian:

```text
room_id = 10
booking A: [09:00,10:00)
booking B: [09:30,10:30) -> chồng lấn
```

Đây là một invariant về **xung đột khoảng thời gian**, không nên tự kiểm bằng:

```sql
-- SELECT COUNT(*) WHERE room_id=... AND slot && ...
```

trong một trigger thông thường nếu có thể dùng exclusion constraint native.

### 19.2. Ví dụ EXCLUDE DEFERRABLE

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE deferred_trigger_lab.room_bookings (
    booking_id BIGINT PRIMARY KEY,
    room_id INTEGER NOT NULL,
    slot TSTZRANGE NOT NULL,
    EXCLUDE USING gist (
        room_id WITH =,
        slot WITH &&
    ) DEFERRABLE INITIALLY IMMEDIATE
);
```

`btree_gist` cung cấp những operator classes GiST thích hợp cho scalar equality trong exclusion constraint. Việc tạo extension cần quyền và môi trường phù hợp.

### 19.3. Hoãn khi cần hoán đổi lịch

```sql
BEGIN;

SET CONSTRAINTS ALL DEFERRED;

-- Thực hiện các thay đổi lịch tạm thời trùng,
-- rồi đảm bảo không còn overlap trước COMMIT.

ROLLBACK;
```

Trong production, nên nêu tên constraint cụ thể thay cho `ALL` nếu có nhiều constraint deferrable.

### 19.4. Tại sao EXCLUDE tốt hơn trigger tự kiểm overlap?

Exclusion constraint tích hợp với index và cơ chế kiểm soát concurrency của PostgreSQL. Trigger chỉ chạy `SELECT ... WHERE slot && ...` ở mức snapshot thường có thể gặp race. Native constraint nên là lựa chọn ưu tiên khi đúng biểu thức invariant.

---

## 20. Constraint trigger và concurrency: điểm nguy hiểm nhất

### 20.1. Trì hoãn không làm các SELECT tự khóa dữ liệu

Function trong lab kiểm tra:

```sql
SELECT COALESCE(SUM(a.amount),0)
FROM deferred_trigger_lab.allocations AS a
WHERE a.batch_id = p_batch_id;
```

Đây là một phép SELECT aggregate. Bản thân nó không đồng nghĩa với một ràng buộc uniqueness/exclusion native có bảo đảm concurrency tương ứng.

### 20.2. Hai transaction cùng sửa một nhóm

Giả sử nhiều workers cập nhật allocations của cùng batch đồng thời:

```text
Transaction A                    Transaction B
--------------------------       --------------------------
Đọc/tính theo snapshot A         Đọc/tính theo snapshot B
Sửa allocation 1                 Sửa allocation 2
Deferred check gần commit        Deferred check gần commit
                                    |
Tùy thời điểm và isolation: kiểm tra có thể không cùng
một góc nhìn nhất quán về tác động của transaction khác.
```

Việc cả hai transaction “đã chạy function check” **không tự chứng minh invariant liên hàng được bảo toàn dưới mọi lịch chạy đồng thời**.

### 20.3. Write skew

*Write skew* là một dạng anomaly trong đó các transaction thay đổi những hàng khác nhau dựa trên dữ liệu đọc mà không nhìn thấy thay đổi chưa commit của nhau. Hai transaction có thể cùng vượt qua những kiểm tra riêng lẻ, nhưng trạng thái chung sau khi cả hai commit lại vi phạm một invariant liên hàng.

Với constraint trigger có `SELECT COUNT/SUM/EXISTS`, phải đánh giá rủi ro này, đặc biệt ở `READ COMMITTED` và `REPEATABLE READ`.

### 20.4. Khóa parent row như một điểm phối hợp

Một chiến lược thường cân nhắc là **serialize mọi writer tác động một batch qua cùng một parent row**:

```sql
BEGIN;

SELECT 1
FROM deferred_trigger_lab.batches
WHERE batch_id = 101
FOR UPDATE;

-- Chỉ sau khi khóa parent thành công mới sửa allocations
-- và expected_total của batch 101.

COMMIT;
```

Điểm quan trọng là **mọi đường ghi liên quan phải tuân thủ cùng giao thức khóa**, trong cùng transaction. Nếu một job khác bỏ qua, bảo đảm mong muốn có thể mất.

### 20.5. Không tùy tiện dùng FOR UPDATE trong phép SUM

PostgreSQL không cho viết mọi dạng aggregate query với `FOR UPDATE` trực tiếp theo cách khóa các nhóm aggregate. Khóa một **row đại diện** (parent) trước khi cập nhật là một chiến lược khác, dễ xác định phạm vi hơn.

### 20.6. Nhiều parent thì cần thứ tự khóa thống nhất

Khi chuyển allocation từ batch A sang batch B, cần phối hợp cả hai batch. Nếu transaction 1 khóa A rồi B, transaction 2 khóa B rồi A, có nguy cơ deadlock.

Một giao thức nên:

- Xác định tập parent bị ảnh hưởng.
- Khóa theo thứ tự ổn định, chẳng hạn `batch_id` tăng dần.
- Giữ transaction ngắn.
- Xử lý deadlock hoặc serialization failure bằng retry có kiểm soát.

### 20.7. SERIALIZABLE và retry

`SERIALIZABLE` có thể phát hiện nhiều anomaly nếu **tất cả transaction liên quan** thực hiện trong isolation phù hợp, nhưng PostgreSQL có thể hủy một transaction bằng serialization failure `40001`. Ứng dụng phải retry **toàn bộ transaction** theo một cơ chế an toàn.

Không dùng `SERIALIZABLE` như cách tránh thiết kế giao thức ghi và test concurrency.

### 20.8. Bảo vệ ở lớp dữ liệu

Với invariant thực sự quan trọng như số dư tài chính hoặc giới hạn quota:

1. Ưu tiên native constraints/atomic SQL nếu có thể.
2. Xác định mô hình locking và isolation.
3. Không tin một custom trigger `SELECT COUNT(*)` đơn độc.
4. Dùng idempotency với các yêu cầu được gửi lại.
5. Có kiểm tra đối soát và giám sát.

---

## 21. Vì sao nhiều deferred events có thể rất đắt?

### 21.1. Một cập nhật nhiều dòng

```sql
UPDATE deferred_trigger_lab.allocations
SET amount = amount + 1
WHERE batch_id = 101;
```

Nếu có 10.000 dòng, constraint trigger `AFTER ROW` có thể xếp hàng 10.000 events.

### 21.2. Mỗi event chạy SUM một lần

Trong function hiện tại:

```sql
PERFORM deferred_trigger_lab.assert_sealed_batch_total(...);
```

và hàm `assert_sealed_batch_total` lại chạy `SUM(amount)`. Nếu 10.000 events cùng kiểm tra batch 101, việc đọc/tính tổng có thể bị lặp 10.000 lần.

### 21.3. Pending event queue cũng cần tài nguyên

Trì hoãn nhiều events tới commit có thể làm tăng:

- Bộ nhớ và công việc quản lý trigger events.
- Thời gian COMMIT vì phải xử lý các pending checks.
- Thời gian giữ locks/transaction.
- Khả năng giao dịch bị rollback rất muộn.

Không cho rằng `INITIALLY DEFERRED` là một tối ưu hiệu năng; nó chủ yếu đáp ứng **semantics thời điểm kiểm tra**.

### 21.4. Thêm index có ích nhưng không giải quyết số lần kiểm tra

`allocations_batch_id_idx` giúp tìm rows theo batch, nhưng nếu function chạy 10.000 lần cho cùng batch thì dù mỗi lần nhanh, tổng chi phí vẫn lớn.

### 21.5. Thời điểm SET CONSTRAINTS cũng là hotspot

Nếu transaction tạo rất nhiều events, `SET CONSTRAINTS ... IMMEDIATE` có thể tốn thời gian đáng kể để chạy toàn bộ các kiểm tra còn chờ. Đừng dùng nó trong đường hot path mỗi request lớn mà chưa benchmark.

### 21.6. Giải pháp thay thế dựa vào cách ghi

Khi workload chủ yếu cập nhật hàng nghìn dòng trong một batch:

- Thiết kế một command cập nhật cả batch trong transaction đã khóa parent.
- Tính tổng một lần trước khi chuyển batch sang sealed nếu đó là thời điểm duy nhất cần invariant.
- Lưu số dư/tổng tiền trong một row summary được cập nhật atomically, kèm cơ chế kiểm tra đối soát.
- Dùng ordinary statement-level trigger + transition table để xử lý tập rows, nếu không cần deferral tới commit.
- Thay đổi mô hình để biểu diễn invariant bằng native constraint.

Mỗi phương án đánh đổi correctness và latency; **không được bỏ kiểm tra cuối transaction nếu nghiệp vụ bắt buộc**.

---

## 22. Quan sát metadata của constraint trigger

### 22.1. pg_trigger

```sql
SELECT
    t.tgname AS trigger_name,
    t.tgrelid::regclass AS table_name,
    t.tgdeferrable,
    t.tginitdeferred,
    t.tgenabled,
    pg_get_triggerdef(t.oid, true) AS definition
FROM pg_trigger AS t
WHERE t.tgrelid IN (
    'deferred_trigger_lab.batches'::regclass,
    'deferred_trigger_lab.allocations'::regclass
)
  AND NOT t.tgisinternal
ORDER BY t.tgrelid::regclass::text, t.tgname;
```

Các cột:

| Cột | Ý nghĩa |
|---|---|
| `tgname` | Tên trigger |
| `tgrelid` | Bảng chứa trigger |
| `tgdeferrable` | Có thể hoãn hay không |
| `tginitdeferred` | Mặc định deferred hay không |
| `tgenabled` | Trạng thái kích hoạt theo chế độ trigger |
| `tgisinternal` | Trigger hệ thống/nội bộ hay do người dùng tạo |

### 22.2. pg_constraint

User-defined constraint triggers được ghi nhận trong catalog `pg_constraint`:

```sql
SELECT
    conname,
    contype,
    conrelid::regclass AS table_name,
    condeferrable,
    condeferred
FROM pg_constraint
WHERE connamespace = 'deferred_trigger_lab'::regnamespace
ORDER BY conrelid::regclass::text, conname;
```

Các giá trị `contype` quan trọng:

```text
c = CHECK
f = FOREIGN KEY
n = NOT NULL (trên phiên bản có catalog entry tương ứng)
p = PRIMARY KEY
u = UNIQUE
x = EXCLUDE
t = user-defined constraint trigger
```

Không dùng catalog query như một cách thay cho chạy thử invariant; metadata cho biết định nghĩa/trạng thái, không cho biết logic function đã đúng cho mọi concurrency schedule.

### 22.3. Kiểm tra function được gắn đúng

```sql
SELECT
    t.tgname,
    p.proname,
    n.nspname AS function_schema
FROM pg_trigger AS t
JOIN pg_proc AS p ON p.oid = t.tgfoid
JOIN pg_namespace AS n ON n.oid = p.pronamespace
WHERE t.tgrelid = 'deferred_trigger_lab.allocations'::regclass
  AND NOT t.tgisinternal;
```

### 22.4. Bảo trì thủ công phải cẩn thận

Nếu trigger bị vô hiệu hóa hoặc function bị thay đổi, những rows cũ **không tự được kiểm tra lại tất cả**. Cần thiết kế migration, kiểm tra toàn bộ dữ liệu và kế hoạch rollback theo mức rủi ro.

---

## 23. ALTER TABLE DISABLE TRIGGER và rủi ro bỏ qua kiểm tra

### 23.1. Trigger có thể bị vô hiệu hóa khi có quyền

```sql
-- Chỉ minh họa; KHÔNG chạy trên bảng production:
-- ALTER TABLE deferred_trigger_lab.allocations
-- DISABLE TRIGGER batch_total_guard_lines;
```

Khi trigger bị disable, các DML sau đó có thể không tạo deferred check như thiết kế.

### 23.2. ENABLE không tự rà soát toàn bộ dữ liệu cũ

```sql
-- Chỉ minh họa:
-- ALTER TABLE deferred_trigger_lab.allocations
-- ENABLE TRIGGER batch_total_guard_lines;
```

Việc bật lại trigger không tự đi qua mọi batch đã từng bị sửa trong lúc trigger tắt và kiểm tra invariant.

### 23.3. Migration/backfill cần một lần xác minh độc lập

Khi nhập dữ liệu legacy hoặc bulk load:

1. Giữ bản ghi rõ lúc nào trigger được bật/tắt và vì sao.
2. Chặn hoặc điều phối writers trong khoảng không bảo vệ.
3. Xác minh toàn bộ batches sealed bằng một truy vấn đối soát.
4. Xử lý mọi nhóm sai lệch.
5. Chỉ mở lại write traffic bình thường khi invariant được xác nhận theo yêu cầu.

### 23.4. Truy vấn đối soát

```sql
SELECT
    b.batch_id,
    b.tenant_id,
    b.expected_total,
    COALESCE(SUM(a.amount), 0) AS actual_total
FROM deferred_trigger_lab.batches AS b
LEFT JOIN deferred_trigger_lab.allocations AS a
    ON a.batch_id = b.batch_id
WHERE b.status = 'sealed'
GROUP BY b.batch_id, b.tenant_id, b.expected_total
HAVING COALESCE(SUM(a.amount), 0)
       IS DISTINCT FROM b.expected_total
ORDER BY b.batch_id;
```

Với dữ liệu lab hợp lệ, query không trả row. Nếu trả row thì có **nhóm sealed lệch tổng** cần được xử lý.

### 23.5. Không dùng trigger như rào chắn bảo mật duy nhất

Một tài khoản có quyền schema/DDL rộng hoặc các cơ chế replication/import đặc biệt có thể ảnh hưởng việc trigger có chạy hay không. Quản lý grants, role, migration quyền cao và audit là một phần của bảo vệ invariant.

---

## 24. Vấn đề transaction, SAVEPOINT và lỗi ở COMMIT

### 24.1. Transaction là phạm vi trì hoãn

`DEFERRABLE INITIALLY DEFERRED` có ý nghĩa mạnh nhất khi có **nhiều statements trong cùng một transaction**.

Nếu application chạy autocommit:

```text
Statement 1 -> commit ngay
Statement 2 -> transaction khác
```

thì trigger deferred của statement 1 vẫn cần thỏa ràng buộc **ngay khi transaction ngắn đó commit**. Nó không biết statement 2 của transaction tương lai sẽ sửa dữ liệu.

### 24.2. Dùng BEGIN/COMMIT đúng

```sql
BEGIN;

-- Nhiều thay đổi phải có tính nguyên tử cùng nhau.

SET CONSTRAINTS
    deferred_trigger_lab.batch_total_guard_header,
    deferred_trigger_lab.batch_total_guard_lines
IMMEDIATE;

COMMIT;
```

Trong code ứng dụng, chuẩn bị transaction và kiểm tra lỗi ở cả `SET CONSTRAINTS` lẫn `COMMIT`. Commit có thể lỗi do các constraints khác, serialization conflict hoặc lỗi hạ tầng.

### 24.3. SAVEPOINT

```sql
BEGIN;

SAVEPOINT before_adjustment;

UPDATE deferred_trigger_lab.allocations
SET amount = amount + 5
WHERE line_id = 1001;

-- Nếu muốn từ bỏ bước điều chỉnh:
ROLLBACK TO SAVEPOINT before_adjustment;

COMMIT;
```

Sau rollback tới savepoint, những thay đổi dữ liệu thuộc phần bị rollback không còn hiệu lực; các queued events liên quan đến thay đổi đã bị rollback cũng được xử lý theo cơ chế transaction/subtransaction.

### 24.4. Kiểm tra hồi tố và savepoint

Khi `SET CONSTRAINTS ... IMMEDIATE` thất bại do một pending check, transaction có thể rơi vào trạng thái lỗi và cần rollback tới savepoint thích hợp hoặc rollback toàn bộ. Đừng tiếp tục chạy nhiều SQL và mong database tự trở lại bình thường.

### 24.5. PL/pgSQL BEGIN ... END không phải transaction boundary

Trong function:

```sql
BEGIN
    UPDATE ...;
END;
```

`BEGIN/END` chỉ là khối PL/pgSQL, **không** tự tạo commit point mới. Một constraint trigger deferred từ UPDATE trong function vẫn có thể chờ tới transaction commit của câu lệnh gọi function.

### 24.6. Không giả định có thể COMMIT trong trigger function

Trigger function không phải nơi bạn tự commit transaction. Công việc của constraint trigger là **kiểm tra và ném lỗi nếu cần** dưới transaction đang chạy, không phải điều khiển transaction lifecycle tùy ý.

---

## 25. RAISE EXCEPTION có ngữ nghĩa gì ở lúc commit?

### 25.1. Nếu invariant sai

Trong helper:

```sql
IF v_actual IS DISTINCT FROM v_expected THEN
    RAISE EXCEPTION '...'
        USING ERRCODE = '23514';
END IF;
```

Lỗi khiến đường thực thi bình thường bị dừng. Nếu phát sinh trong các pending constraint checks tại COMMIT, transaction không được commit thành công.

### 25.2. Không dùng RAISE NOTICE để “bảo vệ” invariant

`RAISE NOTICE` chỉ gửi thông báo chẩn đoán. Nếu function:

```sql
IF v_actual <> v_expected THEN
    RAISE NOTICE 'Totals do not match';
END IF;
```

thì transaction vẫn có thể commit, bất chấp tổng sai. Một constraint trigger thực hiện invariant **phải ném lỗi** khi vi phạm không được phép.

### 25.3. Exception message và SQLSTATE

Ứng dụng nên lưu:

- SQLSTATE để phân loại lỗi.
- Tên constraint nếu có.
- ID nhóm/bản ghi liên quan khi không nhạy cảm.
- Log transaction/correlation ID.

Không dựa vào việc parse một đoạn văn trong exception message để quyết định có retry hay không.

### 25.4. Lỗi nghiệp vụ khác serialization failure

- `23514` trong lab: invariant không thỏa; cần sửa dữ liệu/luồng nghiệp vụ.
- `40001`: serialization failure, có thể retry toàn bộ transaction khi quy trình hỗ trợ.
- `40P01`: deadlock detected, có thể retry có giới hạn sau khi phân tích lock ordering.

Không retry vô hạn một transaction sai tổng 115 khi expected 100; thử lại y nguyên sẽ không tự làm ràng buộc đúng.

---

## 26. Quy trình sửa đổi một constraint trigger

### 26.1. Hàm và trigger là hai loại đối tượng riêng

Function:

```sql
CREATE OR REPLACE FUNCTION
    deferred_trigger_lab.enforce_batch_total_deferred()
RETURNS trigger ...
```

Trigger:

```sql
CREATE CONSTRAINT TRIGGER batch_total_guard_lines
AFTER ... ON ...
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION ...;
```

Thay đổi **thân function** có thể thực hiện bằng `CREATE OR REPLACE FUNCTION` tương thích chữ ký. Nhưng thay đổi **event, deferrability hoặc WHEN của constraint trigger** cần DDL phù hợp trên trigger.

### 26.2. Không dùng CREATE OR REPLACE cho constraint trigger như trigger thường

Theo PostgreSQL hiện hành, `CREATE OR REPLACE TRIGGER` **không hỗ trợ thay thế constraint trigger**. Để thay định nghĩa một constraint trigger, phải lên kế hoạch `DROP TRIGGER` và `CREATE CONSTRAINT TRIGGER` tương ứng với locking/traffic phù hợp.

### 26.3. Rủi ro migration thời gian trống

Nếu drop constraint trigger và tạo lại trong hai transaction riêng biệt, có thể xuất hiện khoảng dữ liệu được ghi mà không có bảo vệ.

Hãy:

- Chọn transaction DDL nhất quán và maintenance window khi cần.
- Xác định quyền/locks.
- Đảm bảo trigger mới được tạo thành công trước khi mở writers.
- Có cách đối soát dữ liệu nếu xảy ra khoảng trống.

### 26.4. Đổi logic function không tự rà soát lịch sử

Nếu phiên bản mới thay quy tắc:

```text
v1: tổng allocations phải bằng expected_total
v2: tổng allocations phải bằng expected_total
    và mọi batch sealed phải có ít nhất 2 lines
```

Những batch sealed được tạo trước khi deploy v2 **không tự tạo event UPDATE** để kiểm tra lại. Cần thực hiện validation riêng trên toàn bộ dữ liệu liên quan và remediation nếu cần.

### 26.5. Không coi việc trigger enabled là chứng cứ dữ liệu sạch

Metadata cho biết trigger đang bật; không chứng minh các dữ liệu lịch sử chưa từng vi phạm khi trigger chưa có, bị disable hoặc function cũ sai.

---

## 27. Phân quyền, SECURITY DEFINER và search_path

### 27.1. Quyền tạo trigger

Người tạo trigger cần các quyền phù hợp trên bảng và quyền thực thi function. Không cho mọi application role quyền DDL rộng chỉ để dùng invariant.

### 27.2. SECURITY INVOKER/DEFINER

PL/pgSQL function thông thường có semantics quyền phù hợp với chế độ function, mặc định `SECURITY INVOKER`.

Nếu function được khai báo `SECURITY DEFINER`, nó chạy với quyền của owner và cần:

- Owner tối thiểu đủ quyền.
- `search_path` an toàn, không cho đối tượng không tin cậy chen vào.
- Schema-qualified table/function names.
- Quyền EXECUTE rõ.
- Không dùng dynamic SQL từ input không đáng tin nếu không xử lý identifier/value đúng.

### 27.3. Tenant isolation

Trong mô hình nhiều tenant, function dùng `batch_id` mà không kiểm `tenant_id` trong phép SUM. Điều này đúng ở lab **vì batch_id là khóa toàn cục duy nhất và FK xác định sở hữu**. Nếu khóa chỉ duy nhất theo tenant, phải gắn tenant vào PK/FK/WHERE hoặc thiết kế scope tương đương.

Constraint trigger không tự thay authorization/RLS; quyền ghi các batches và allocations phải được kiểm soát.

### 27.4. RLS trong trigger

Row-level security có thể ảnh hưởng những rows function nhìn thấy tùy role, function security mode và policies. Một function kiểm tra SUM mà **không nhìn đủ allocations cần thiết** có thể kết luận sai.

Với invariant xuyên tenant/table, xác định rõ owner, execution privileges, RLS và test dưới những role thực tế. Không tự dùng `SECURITY DEFINER` để bỏ RLS mà chưa đánh giá bảo mật.

---

## 28. So sánh constraint trigger với các chiến lược khác

| Bài toán | Công cụ nên ưu tiên | Khi nào constraint trigger phù hợp? |
|---|---|---|
| Một cột bắt buộc có giá trị | `NOT NULL` | Hầu như không cần |
| Số lượng phải không âm | `CHECK` | Hầu như không cần |
| Khóa duy nhất | `UNIQUE` / `PRIMARY KEY` | Không tự viết SELECT COUNT |
| Row con cần parent | `FOREIGN KEY` | Không thay FK native |
| Khoảng đặt phòng không overlap | `EXCLUDE` | Chỉ nếu native không mô tả được nghiệp vụ |
| Tổng allocations bằng header ở commit | Thiết kế giao thức ghi; deferred trigger có thể hỗ trợ | Khi cần kiểm tra nhiều rows sau nhiều statement |
| Cập nhật timestamp/audit sau DML | Ordinary trigger | Không cần deferral |
| Gom tất cả row thay đổi của một statement | AFTER statement + transition table | Constraint trigger không hỗ trợ transition table |
| Kiểm tra chéo hệ thống ngoài database | Giao thức ứng dụng/outbox | Trigger không thể tạo atomic commit với dịch vụ ngoài |
| Bulk aggregate rất lớn | Summary table/procedure/command được kiểm soát | Chú ý chi phí row-level deferred checks |

### 28.1. Chọn native constraint trước

Một ràng buộc native có những tính chất PostgreSQL đã cài sẵn, được planner/catalog hiểu rõ và thường an toàn concurrency hơn một SELECT tự viết. Trigger chỉ nên bổ sung những invariant không thể biểu diễn phù hợp bằng công cụ sẵn có.

### 28.2. Chọn thời điểm kiểm tra theo workflow

Nếu thao tác chỉ gồm một UPDATE:

```text
UPDATE row
-> invariant phải đúng ngay
```

không cần trì hoãn. Nếu thao tác là một transaction nhiều bước:

```text
Update A
Update B
Correct header
Check final total
Commit
```

deferral có thể phản ánh nghiệp vụ tốt hơn.

### 28.3. Nếu cần trạng thái trung gian sai vượt qua transaction?

Không dùng deferred constraint trigger nếu yêu cầu là **commit trạng thái sai tạm rồi sửa ở một transaction khác**. Deferred kiểm tra vẫn xảy ra trước commit.

Với workflow nhiều transaction, cần một mô hình **trạng thái hợp lệ rõ ràng**, chẳng hạn `draft/pending/approved`, cùng các ràng buộc tương ứng. Đừng cố dùng `INITIALLY DEFERRED` để hoãn vô thời hạn qua nhiều transaction.

---

## 29. Những sai lầm thường gặp

**1. “Constraint trigger là BEFORE trigger có thể hoãn.”** Sai. Nó bắt buộc là `AFTER ROW`.

**2. “Có thể tạo constraint trigger FOR EACH STATEMENT.”** Sai.

**3. “REFERENCING NEW TABLE hoạt động với constraint trigger.”** Không. Transition relations không áp dụng cho constraint trigger.

**4. “INITIALLY DEFERRED bỏ kiểm tra.”** Sai. Nó đổi thời điểm kiểm tra.

**5. “DEFERRABLE và INITIALLY DEFERRED là một.”** Sai. Một cái cho phép đổi, một cái đặt trạng thái mặc định.

**6. “NOT DEFERRABLE có thể đổi thành DEFERRED bằng SET CONSTRAINTS.”** Không.

**7. “SET CONSTRAINTS thay default vĩnh viễn cho session.”** Không, nó có hiệu lực trong transaction hiện tại.

**8. “SET CONSTRAINTS ... IMMEDIATE chỉ ảnh hưởng thay đổi tương lai.”** Sai. Nó kiểm tra cả các events đã pending.

**9. “Nếu SET CONSTRAINTS IMMEDIATE lỗi, chỉ cần chạy lại cùng câu mà không ROLLBACK.”** Không. Cần xử lý trạng thái transaction lỗi.

**10. “SET CONSTRAINTS ALL chỉ đổi trigger của tôi.”** Không. Nó có thể ảnh hưởng nhiều constraint deferrable khác.

**11. “Tên constraint chắc chắn duy nhất toàn database.”** Không.

**12. “WHEN trong constraint trigger được đánh giá lúc COMMIT.”** Sai. Nó được đánh giá ngay sau row operation để quyết định xếp hàng event.

**13. “Một WHEN quá hẹp không thể bỏ lọt thay đổi.”** Sai. DELETE, UPDATE đổi nhóm hoặc đổi trạng thái có thể không được queued.

**14. “Deferred event NEW luôn thể hiện giá trị row cuối transaction.”** Không. Không nên dùng ảnh event cũ thay cho việc kiểm tra dữ liệu cuối cùng.

**15. “Chỉ tạo trigger trên child là đủ bảo vệ invariant child SUM = parent total.”** Sai nếu header thay đổi.

**16. “Chỉ tạo trigger trên header là đủ.”** Sai nếu allocation thay đổi.

**17. “UPDATE đổi batch_id chỉ cần kiểm tra NEW.batch_id.”** Sai. Cả nhóm cũ và mới đều có thể sai.

**18. “RETURN NEW trong AFTER trigger làm sửa lại row.”** Không. Giá trị trả về không dùng để thay row đã ghi.

**19. “Một CONSTRAINT TRIGGER tự biết logic kiểm tra.”** Không. Function phải chủ động RAISE EXCEPTION.

**20. “RAISE NOTICE đủ để từ chối transaction sai.”** Không.

**21. “CHECK có thể SELECT SUM từ bảng khác như constraint liên hàng an toàn.”** Không.

**22. “CHECK và NOT NULL có thể SET CONSTRAINTS DEFERRED.”** Không.

**23. “Một trigger SELECT COUNT thay thế UNIQUE tốt hơn.”** Không. Native uniqueness có cơ chế phù hợp hơn.

**24. “Unique deferrable vẫn là arbiter cho ON CONFLICT.”** Không.

**25. “FOREIGN KEY luôn kiểm tra ngay và không thể hoãn.”** Sai. FK `DEFERRABLE` có thể hoãn kiểm tra phù hợp.

**26. “RESTRICT FK action trì hoãn như NO ACTION.”** Không.

**27. “DEFERRABLE khiến CASCADE tự chờ cuối transaction.”** Không; referential actions có quy tắc riêng.

**28. “Có deferred trigger thì SELECT SUM concurrency-safe trong mọi isolation.”** Không.

**29. “SERIALIZABLE tự retry cho application.”** Không. Ứng dụng phải xử lý serialization failure.

**30. “SELECT FOR UPDATE trên một parent đủ khi writers khác không khóa parent.”** Không. Cần một giao thức thống nhất.

**31. “Khóa A rồi B ở mọi transaction bất kể thứ tự sẽ không deadlock.”** Không. Phải giữ thứ tự khóa ổn định.

**32. “Một UPDATE 50.000 rows tạo một deferred event.”** Không. Row-level trigger tạo event theo rows phù hợp.

**33. “PostgreSQL tự gom events trùng batch thành một SUM duy nhất.”** Không.

**34. “Deferred constraints giúp COMMIT nhanh hơn.”** Không chắc; có thể dồn nhiều công việc tới commit.

**35. “Có index batch_id nên lặp SUM hàng nghìn lần không đáng kể.”** Không nên giả định.

**36. “TRUNCATE tương đương DELETE từng row về mặt trigger.”** Không.

**37. “Bật trigger sau bulk load tự kiểm tra dữ liệu đã có.”** Không.

**38. “Đổi function kiểm tra không cần rà soát rows cũ.”** Sai nếu invariant mới khác.

**39. “CREATE OR REPLACE TRIGGER áp dụng như nhau cho constraint trigger.”** Không theo PostgreSQL hiện hành.

**40. “Constraint trigger bảo đảm quyền tenant.”** Không. Vẫn cần grants/RLS/auth.

**41. “Một session autocommit có thể sửa dữ liệu ở statement thứ hai trước khi trigger từ statement thứ nhất kiểm tra.”** Không. Transaction thứ nhất đã kết thúc và kiểm tra trước statement của transaction mới.

**42. “BEGIN ... END của PL/pgSQL tương đương BEGIN/COMMIT SQL.”** Không.

**43. “Dữ liệu ở trạng thái draft phải thỏa invariant sealed.”** Không theo mô hình lab; trạng thái quyết định phạm vi kiểm tra.

**44. “Lỗi ở COMMIT có thể bỏ qua vì UPDATE trước đó đã thành công.”** Không. Transaction chưa commit thành công.

**45. “Chỉ cần thử transaction tuần tự là đủ kiểm tra custom constraint trigger.”** Không. Cần test đồng thời và failure recovery.

---

## 30. Bài tập thực hành và đáp án

### Bài 1 — Nhận diện trường hợp cần deferral

**Tình huống:** Một transaction tăng allocation A từ 60 lên 70 rồi giảm B từ 40 xuống 30; yêu cầu tổng cuối vẫn bằng 100.

**Đáp án:** Deferrable constraint trigger có thể kiểm tra invariant ở cuối transaction, cho phép trạng thái 110 tạm thời sau statement đầu tiên.

### Bài 2 — Viết constraint trigger deferred

**Đáp án:**

```sql
CREATE CONSTRAINT TRIGGER example_deferred_guard
AFTER INSERT OR UPDATE OR DELETE
ON deferred_trigger_lab.allocations
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION
    deferred_trigger_lab.enforce_batch_total_deferred();
```

Đây là mẫu cú pháp; bảng lab đã có trigger `batch_total_guard_lines` thực hiện cùng chức năng. Không cần giữ hai triggers tương đương.

### Bài 3 — Vì sao phải AFTER ROW?

**Đáp án:** PostgreSQL quy định constraint trigger phải là `AFTER ROW` trên bảng thường. `BEFORE` hoặc `FOR EACH STATEMENT` không hợp lệ với loại trigger này.

### Bài 4 — Đổi từ deferred sang immediate

**Đáp án:**

```sql
BEGIN;

SET CONSTRAINTS
    deferred_trigger_lab.batch_total_guard_lines
IMMEDIATE;

COMMIT;
```

Nếu có events chờ, chúng được kiểm tra tại `SET CONSTRAINTS` theo quy tắc hồi tố.

### Bài 5 — Khi SET CONSTRAINTS IMMEDIATE phát hiện sai

**Đáp án:** Statement thất bại và transaction cần được xử lý lỗi/rollback. Không có việc “chấp nhận commit rồi sửa sau”.

### Bài 6 — INITIALLY IMMEDIATE có thể hoãn?

**Đáp án:** Có nếu khai báo `DEFERRABLE INITIALLY IMMEDIATE`. Transaction dùng `SET CONSTRAINTS name DEFERRED` trước những DML cần hoãn.

### Bài 7 — NOT DEFERRABLE

**Câu hỏi:** `SET CONSTRAINTS name DEFERRED` có biến một constraint trigger NOT DEFERRABLE thành deferred được không?

**Đáp án:** Không. Phải đổi định nghĩa constraint/trigger theo DDL phù hợp nếu muốn cho phép trì hoãn.

### Bài 8 — SQL autocommit

**Câu hỏi:** Hai UPDATE ở hai statement tự commit riêng có thể dùng deferred trigger để sửa tổng sai giữa chúng không?

**Đáp án:** Không. Statement đầu kết thúc transaction và phải qua kiểm tra trước khi statement thứ hai được commit ở transaction khác.

### Bài 9 — Kiểm tra SUM

```sql
SELECT
    b.batch_id,
    b.expected_total,
    COALESCE(SUM(a.amount),0) AS actual_total
FROM deferred_trigger_lab.batches b
LEFT JOIN deferred_trigger_lab.allocations a
    ON a.batch_id = b.batch_id
WHERE b.status = 'sealed'
GROUP BY b.batch_id, b.expected_total;
```

**Đáp án:** Query cho thấy expected và actual theo batch sealed. Muốn chỉ lấy lỗi, thêm `HAVING COALESCE(SUM(a.amount),0) IS DISTINCT FROM b.expected_total`.

### Bài 10 — Vì sao COALESCE?

**Đáp án:** `SUM` trên tập rỗng trả NULL. Trong mô hình lab, tập allocation rỗng có tổng được quy ước là 0.

### Bài 11 — Draft lệch tổng

**Tình huống:** Batch draft expected 200, actual 10.

**Đáp án:** Được phép theo invariant của lab vì kiểm tra tổng chỉ áp dụng cho sealed.

### Bài 12 — Chuyển draft thành sealed

**Yêu cầu:** Trong một transaction, đổi status sang sealed và thêm allocation còn thiếu.

**Đáp án:** Dùng `BEGIN; UPDATE batches ...; INSERT allocations ...; COMMIT;`. Deferred trigger kiểm tra tổng cuối ở commit.

### Bài 13 — DELETE allocation

**Câu hỏi:** Vì sao phải gắn trigger cho DELETE?

**Đáp án:** Xóa một dòng làm giảm tổng; nếu không kiểm tra sau DELETE, sealed batch có thể thiếu allocation mà không phát hiện.

### Bài 14 — Di chuyển allocation giữa hai batch

**Đáp án:** Cần kiểm tra cả `OLD.batch_id` và `NEW.batch_id` trong UPDATE, vì nhóm nguồn mất tiền và nhóm đích nhận tiền.

### Bài 15 — Header thay đổi

**Tình huống:** `expected_total` tăng nhưng allocations không đổi.

**Đáp án:** Cần constraint trigger trên batches (hoặc cơ chế khác kiểm soát header) vì child trigger không phát sinh event khi header đổi.

### Bài 16 — WHEN có trì hoãn không?

**Đáp án:** Không. `WHEN` trên constraint trigger được đánh giá ngay sau row operation. Nếu FALSE, event không được queue.

### Bài 17 — CASE NOT FOUND cho parent đã xóa

**Câu hỏi:** Vì sao helper `IF NOT FOUND THEN RETURN;` khi không còn batch?

**Đáp án:** Một pending event có thể thuộc parent đã bị xóa trong cùng transaction. Invariant sealed không còn áp dụng cho parent không tồn tại.

### Bài 18 — Vì sao AFTER trigger không sửa NEW?

**Đáp án:** AFTER trigger chạy sau khi row operation đã thực hiện; giá trị RETURN không được dùng để thay row. Nếu cần thay NEW trước ghi, dùng BEFORE trigger.

### Bài 19 — SQLSTATE

**Câu hỏi:** Function lab dùng SQLSTATE nào cho invariant sai tổng?

**Đáp án:** `23514`, mã `check_violation`, được đặt tường minh trong `RAISE EXCEPTION`.

### Bài 20 — Unique deferrable cho hoán đổi vị trí

**Đáp án:** Khai báo `UNIQUE(board_id, position) DEFERRABLE INITIALLY DEFERRED`, thực hiện hoán đổi trong transaction, bảo đảm không trùng vị trí cuối transaction.

### Bài 21 — Dùng UNIQUE hay custom trigger?

**Tình huống:** Không có hai users cùng email chuẩn hóa.

**Đáp án:** Ưu tiên unique constraint/index trên khóa đã chuẩn hóa phù hợp; không viết constraint trigger quét bảng chỉ để đếm email trùng.

### Bài 22 — FK deferrable

**Yêu cầu:** Chèn child rồi parent trong cùng transaction.

**Đáp án:** `FOREIGN KEY (...) REFERENCES ... DEFERRABLE INITIALLY DEFERRED`, bảo đảm parent được chèn trước commit.

### Bài 23 — ON DELETE RESTRICT và NO ACTION

**Đáp án:** `NO ACTION` có thể hoãn kiểm tra khi FK deferrable; `RESTRICT` không cho hoãn phản ứng từ chối tương ứng.

### Bài 24 — CHECK (amount >= 0)

**Câu hỏi:** Có dùng SET CONSTRAINTS để hoãn CHECK này không?

**Đáp án:** Không. CHECK không deferrable trong PostgreSQL.

### Bài 25 — EXCLUDE cho booking overlap

**Đáp án:** Dùng `EXCLUDE USING gist (room_id WITH =, slot WITH &&)` với `DEFERRABLE` nếu cần hoán đổi lịch trong transaction và điều kiện nghiệp vụ phù hợp.

### Bài 26 — Concurrency

**Câu hỏi:** Hai transaction cùng vượt qua SELECT SUM trong deferred trigger có đủ bảo đảm dữ liệu cuối luôn đúng không?

**Đáp án:** Không tự động. Cần xem MVCC, isolation và giao thức serialize writers theo parent row hoặc native constraints.

### Bài 27 — Khóa parent

**Đáp án gợi ý:**

```sql
BEGIN;
SELECT 1
FROM deferred_trigger_lab.batches
WHERE batch_id = 101
FOR UPDATE;

-- Sau đó thực hiện các thay đổi của batch này.
ROLLBACK;
```

Tất cả writers cần tuân thủ giao thức tương ứng; không chỉ một code path.

### Bài 28 — Hai parent và deadlock

**Đáp án:** Với thao tác chuyển allocation giữa batch A/B, lấy locks theo một thứ tự nhất quán (ví dụ batch_id tăng dần) để giảm nguy cơ deadlock; vẫn cần xử lý lỗi nếu xảy ra.

### Bài 29 — SERIALIZABLE

**Câu hỏi:** SERIALIZABLE có bao giờ làm transaction bị hủy không?

**Đáp án:** Có; ứng dụng cần xử lý SQLSTATE `40001` và retry toàn bộ transaction khi an toàn.

### Bài 30 — Chi phí 50.000 row events

**Đáp án:** Constraint trigger là AFTER ROW nên có thể queue 50.000 events. Nếu mỗi event SUM cả batch, COMMIT có thể cực kỳ tốn kém.

### Bài 31 — Transition table

**Câu hỏi:** Constraint trigger có `REFERENCING NEW TABLE` để gom 50.000 rows không?

**Đáp án:** Không. Transition relations không được dùng với constraint trigger. Có thể cân nhắc ordinary AFTER statement trigger cho workload phù hợp, nhưng mất khả năng deferral qua `SET CONSTRAINTS`.

### Bài 32 — Bulk load khi trigger disabled

**Đáp án:** Sau khi bật trigger lại, phải đối soát dữ liệu cũ; trigger không tự chạy lại cho những writes đã thực hiện khi nó tắt.

### Bài 33 — Đổi function logic

**Câu hỏi:** Đổi function để yêu cầu sealed batch có ít nhất hai allocations có tự kiểm toàn bộ batches cũ không?

**Đáp án:** Không. Cần migration/validation riêng, ngoài việc kiểm tra các DML mới.

### Bài 34 — Constraint trigger và TRUNCATE

**Đáp án:** Constraint trigger AFTER ROW không được kích hoạt như DELETE từng row khi TRUNCATE; cần quản lý quyền TRUNCATE và quy trình bulk operations.

### Bài 35 — Kiểm tra metadata

```sql
SELECT tgname, tgdeferrable, tginitdeferred, tgenabled
FROM pg_trigger
WHERE tgrelid = 'deferred_trigger_lab.batches'::regclass
  AND NOT tgisinternal;
```

**Đáp án:** Query cho biết tên, deferrable/default deferred và trạng thái kích hoạt của user-defined triggers trên batches.

### Bài 36 — Chọn phương án

**Tình huống:** Cần invariant đã đúng ngay sau mỗi UPDATE riêng biệt, không có bước trung gian.

**Đáp án:** Ưu tiên native constraint hoặc kiểm tra immediate. Không cần trì hoãn nếu không có giao dịch nhiều bước hợp lệ.

---

## 31. Checklist thiết kế constraint trigger an toàn

### Định nghĩa invariant

1. Xác định trạng thái nào cần bất biến: draft hay sealed?
2. Điều kiện là trên **một hàng**, nhiều hàng, hay nhiều bảng?
3. Có thể dùng native `CHECK`/`UNIQUE`/`FK`/`EXCLUDE` không?
4. Có cần trạng thái tạm thời sai giữa các statements trong cùng transaction không?
5. Có định nghĩa rõ giá trị NULL, tập rỗng và trường hợp parent bị xóa không?
6. Nếu ràng buộc liên quan tiền, có đúng currency/precision và nghiệp vụ không?

### Thiết kế trigger

7. Dùng `CREATE CONSTRAINT TRIGGER`, đúng `AFTER ROW` trên bảng hợp lệ.
8. Chọn `DEFERRABLE INITIALLY IMMEDIATE` hay `INITIALLY DEFERRED` theo workflow.
9. Tạo trigger cho **mọi bảng** có DML làm sai invariant.
10. Xem đủ INSERT/UPDATE/DELETE và thay đổi khóa nhóm OLD/NEW.
11. Không dùng `WHEN` khi chưa chứng minh nó không bỏ sự kiện cần kiểm tra.
12. Hiểu `WHEN` đánh giá ngay, không ở commit.
13. Trigger function phải `RAISE EXCEPTION` khi sai, không chỉ NOTICE.
14. Với AFTER trigger, không dựa vào RETURN để sửa NEW row.
15. Nếu function đọc state cuối, không dựa mù quáng vào ảnh NEW của event đã queue từ lâu.
16. Không cố dùng transition table trên constraint trigger.

### Transaction và concurrency

17. Nhiều statements cần thuộc **cùng một transaction**.
18. `SET CONSTRAINTS` đặt trước giai đoạn cần trì hoãn.
19. Nếu dùng `SET CONSTRAINTS ... IMMEDIATE`, biết nó kiểm tra hồi tố.
20. Tránh dùng `ALL` nếu chỉ muốn một nhóm constraint.
21. Có cách xử lý lỗi COMMIT/SET CONSTRAINTS và rollback.
22. Xem xét concurrency anomaly và thiết kế lock/isolation.
23. Nếu khóa parent, mọi writers có tuân thủ không?
24. Khi khóa nhiều parents, có thứ tự nhất quán không?
25. Có retry phù hợp cho `40001` và `40P01` không?

### Hiệu năng và vận hành

26. Một statement lớn có tạo quá nhiều events không?
27. Function có đang SUM cùng batch lặp hàng nghìn lần không?
28. Có index thích hợp cho lookup parent/children không?
29. Có benchmark thời gian COMMIT và lock contention không?
30. Bulk load/replication/migration có thể bypass trigger không?
31. Có truy vấn reconciliation chạy định kỳ không?
32. Đổi function logic có đi kèm kiểm tra lịch sử không?
33. DDL thay constraint trigger có tránh thời gian trống không?
34. Đã kiểm tra `pg_trigger`/`pg_constraint` và quyền không?
35. Đã thử NULL, DELETE, UPDATE đổi batch_id và lỗi COMMIT chưa?
36. Đã test song song nhiều connections chứ không chỉ một session chưa?

---

## 32. Tổng kết

**Constraint trigger** là một trigger PostgreSQL đặc biệt có thể trì hoãn việc chạy function kiểm tra tới cuối transaction. Nó được tạo bằng `CREATE CONSTRAINT TRIGGER`, bắt buộc là **AFTER ROW** trên bảng thường và có thể khai báo `DEFERRABLE INITIALLY IMMEDIATE` hoặc `DEFERRABLE INITIALLY DEFERRED`.

Các điểm cần nhớ:

- **`IMMEDIATE`**: kiểm tra ở thời điểm áp dụng cho mỗi statement.
- **`DEFERRED`**: có thể trì hoãn tới điểm kết thúc transaction.
- **`SET CONSTRAINTS ... IMMEDIATE`**: ép các kiểm tra đang chờ chạy **ngay lúc chuyển chế độ**, không chỉ đổi chế độ cho tương lai.
- **`WHEN` trên constraint trigger được đánh giá ngay khi row operation xảy ra**; nếu không TRUE, event không được queue.
- Constraint trigger **không phải** BEFORE trigger, statement trigger hay trigger dùng transition table.
- Một function chỉ kiểm tra `SELECT SUM(...)` cần được gắn với mọi thay đổi liên quan, biết xử lý OLD/NEW và phải ném exception nếu invariant sai.
- **Trì hoãn không tự giải quyết concurrency**. Những invariant đa hàng/đa bảng có thể cần parent locks, transaction protocol, isolation level phù hợp hoặc native constraint.
- **Native constraints nên được ưu tiên** nếu mô tả được bài toán: `UNIQUE`/`PRIMARY KEY`, `FOREIGN KEY` và `EXCLUDE` có thể hỗ trợ deferrability; `CHECK` và `NOT NULL` thì không.
- **Chi phí kiểm tra có thể dồn vào COMMIT**. Hàng nghìn row-level events cùng SUM một nhóm có thể tạo bottleneck đáng kể.
- Thay đổi function, disable trigger hoặc load dữ liệu cũ có thể khiến dữ liệu lịch sử chưa được xác minh. Cần migration, đối soát và giám sát.

**Câu hỏi cuối:** Nếu một giao dịch gồm ba câu UPDATE, invariant sai sau câu thứ nhất nhưng đúng sau câu thứ ba, hệ thống cần từ chối ngay hay chỉ cần bảo đảm đúng khi commit? Và nếu hai transaction khác nhau cập nhật cùng nhóm, cơ chế nào khiến chúng không thể cùng vượt qua một kiểm tra dựa trên snapshot không đủ an toàn? Trả lời hai câu hỏi này giúp bạn quyết định khi nào nên dùng constraint trigger, khi nào cần deferral và khi nào phải bổ sung thiết kế concurrency.

### Tài liệu PostgreSQL chính thức

- [CREATE TRIGGER — Constraint Triggers, DEFERRABLE, WHEN](https://www.postgresql.org/docs/current/sql-createtrigger.html).
- [SET CONSTRAINTS — IMMEDIATE và DEFERRED](https://www.postgresql.org/docs/current/sql-set-constraints.html).
- [Overview of Trigger Behavior](https://www.postgresql.org/docs/current/trigger-definition.html).
- [PL/pgSQL Trigger Functions](https://www.postgresql.org/docs/current/plpgsql-trigger.html).
- [PL/pgSQL Errors and Messages](https://www.postgresql.org/docs/current/plpgsql-errors-and-messages.html).
- [Constraints — CHECK, UNIQUE, FOREIGN KEY và EXCLUDE](https://www.postgresql.org/docs/current/ddl-constraints.html).
- [CREATE TABLE — DEFERRABLE Constraints](https://www.postgresql.org/docs/current/sql-createtable.html).
- [pg_trigger System Catalog](https://www.postgresql.org/docs/current/catalog-pg-trigger.html).
- [pg_constraint System Catalog](https://www.postgresql.org/docs/current/catalog-pg-constraint.html).
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html).
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html).
- [CREATE INDEX — Unique and Exclusion Considerations](https://www.postgresql.org/docs/current/sql-createindex.html).
