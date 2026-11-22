# SAVE EXCEPTIONS, SQL%BULK_EXCEPTIONS và xử lý lỗi từng phần

Khi xử lý dữ liệu hàng loạt bằng PL/SQL, FORALL giúp gửi nhiều lần thực thi DML theo cơ chế bulk binding, giảm chi phí chuyển đổi qua lại giữa PL/SQL engine và SQL engine. Tuy nhiên, một phần tử trong collection có thể làm DML thất bại vì vi phạm khóa duy nhất, foreign key, CHECK constraint, NOT NULL, lỗi chuyển đổi hoặc quy tắc dữ liệu khác. Nếu không có chiến lược xử lý lỗi, một lỗi có thể làm FORALL dừng trước khi xử lý hết batch.

SAVE EXCEPTIONS cho phép FORALL tiếp tục thực hiện các iteration còn lại khi một iteration gặp lỗi DML. Sau khi thử hết các iteration, Oracle phát sinh exception tổng hợp ORA-24381. Trong exception handler, chương trình đọc SQL%BULK_EXCEPTIONS để biết iteration nào lỗi và mã lỗi tương ứng. SQL%BULK_ROWCOUNT cho biết số hàng bị tác động bởi từng iteration; SQL%ROWCOUNT cho biết tổng số hàng bị tác động bởi bulk DML.

Đây là cơ chế xử lý thành công một phần. Nó không tự COMMIT, không tự retry và không quyết định nghiệp vụ có chấp nhận các hàng thành công hay phải ROLLBACK toàn batch. Người viết phải thiết kế rõ cách ánh xạ lỗi về input, lưu log, retry và kết thúc transaction.

Sau bài học, bạn có thể:

- Hiểu vì sao FORALL cần chiến lược xử lý lỗi theo iteration.
- Phân biệt hành vi FORALL mặc định và FORALL SAVE EXCEPTIONS.
- Bắt exception ORA-24381 bằng PRAGMA EXCEPTION_INIT.
- Đọc SQL%BULK_EXCEPTIONS.COUNT, ERROR_INDEX và ERROR_CODE.
- Dùng SQLERRM với mã lỗi âm để lấy thông báo Oracle.
- Ánh xạ lỗi về phần tử input trong collection.
- Kết hợp SQL%BULK_ROWCOUNT và SQL%ROWCOUNT để thống kê kết quả.
- Xử lý collection dense, sparse, INDICES OF và VALUES OF.
- Lưu lỗi vào bảng log, phân biệt log cùng transaction và log độc lập.
- Quyết định giữ thành công một phần, rollback toàn batch hoặc retry phần lỗi.
- Phân biệt SAVE EXCEPTIONS với DML error logging (LOG ERRORS).
- Thiết kế batch DML có thể theo dõi, khôi phục và chạy lại an toàn.

> Các ví dụ dùng bảng LAB_ trong schema thực hành riêng. Câu lệnh COMMIT/ROLLBACK là quyết định transaction của ứng dụng; FORALL không tự commit.

## 1. Bối cảnh: lỗi trong bulk DML

### 1.1. FORALL giải quyết vấn đề gì?

Một vòng lặp DML thông thường thực hiện nhiều lần chuyển giữa PL/SQL và SQL:

```sql
FOR i IN 1 .. l_employee_ids.COUNT LOOP
    UPDATE employees
    SET status = 'ACTIVE'
    WHERE employee_id = l_employee_ids(i);
END LOOP;
```

Với hàng trăm nghìn phần tử, cách row-by-row này có thể tạo overhead đáng kể. FORALL gửi các giá trị collection vào một DML statement theo cơ chế bulk binding:

```sql
FORALL i IN 1 .. l_employee_ids.COUNT
    UPDATE employees
    SET status = 'ACTIVE'
    WHERE employee_id = l_employee_ids(i);
```

FORALL không phải vòng lặp PL/SQL thông thường. Nó chỉ áp dụng cho một DML statement trong thân FORALL và dùng các chỉ số collection để bind giá trị cho nhiều lần thực thi.

### 1.2. Vì sao có lỗi theo từng phần tử?

Giả sử một batch INSERT có 5 phần tử:

| Iteration | Input | Kết quả |
| ---: | --- | --- |
| 1 | Mã A01, số lượng 10 | Hợp lệ |
| 2 | Mã A02, số lượng 20 | Hợp lệ |
| 3 | Mã A01, số lượng 30 | Trùng unique key |
| 4 | Mã A04, số lượng -5 | Vi phạm CHECK |
| 5 | Mã A05, số lượng 40 | Hợp lệ |

Nếu mỗi iteration là một lần INSERT độc lập trong FORALL, iteration 3 và 4 có thể lỗi trong khi 1, 2 và 5 vẫn hợp lệ. Chương trình cần biết chính xác phần tử nào lỗi và vì sao.

### 1.3. Không phải mọi trường hợp 0 hàng đều là exception

UPDATE không tìm thấy hàng thỏa WHERE thường chạy thành công với số hàng bị tác động bằng 0. Điều này không tự phát sinh exception và không được ghi vào SQL%BULK_EXCEPTIONS.

Ví dụ:

```sql
FORALL i IN 1 .. l_ids.COUNT
    UPDATE lab_employee
    SET status = 'ACTIVE'
    WHERE employee_id = l_ids(i);
```

Nếu một ID không tồn tại, iteration đó có thể có SQL%BULK_ROWCOUNT(i) = 0, nhưng không phải lỗi DML. Phân biệt rõ:

- Không khớp hàng: DML thành công, row count có thể là 0.
- DML thất bại: Oracle phát sinh lỗi, ví dụ ORA-00001 hoặc ORA-02290.

## 2. Hành vi FORALL mặc định

### 2.1. Không dùng SAVE EXCEPTIONS

Ví dụ:

```sql
FORALL i IN 1 .. l_codes.COUNT
    INSERT INTO lab_items (item_code)
    VALUES (l_codes(i));
```

Nếu một iteration phát sinh lỗi DML, FORALL mặc định dừng tại lỗi đó và exception được truyền ra. Các thay đổi do những iteration trước của chính FORALL đã thực hiện sẽ được rollback khi FORALL thất bại. Các thay đổi có trước FORALL trong transaction không tự động bị rollback chỉ vì FORALL lỗi.

Điều này có nghĩa batch không tự động tiếp tục tới các input sau phần tử lỗi. Nếu cần biết lỗi và tiếp tục các phần tử còn lại, dùng SAVE EXCEPTIONS.

### 2.2. Ví dụ minh họa

Giả sử collection có 5 mã, mã thứ 3 trùng unique key. Không dùng SAVE EXCEPTIONS:

```sql
FORALL i IN 1 .. l_codes.COUNT
    INSERT INTO lab_items (item_code)
    VALUES (l_codes(i));
```

Khi iteration 3 lỗi:

- FORALL dừng.
- Iteration 4 và 5 không được thực hiện.
- Những thay đổi từ iteration trước trong cùng FORALL bị rollback.
- Exception được truyền về block bao quanh.

Nếu yêu cầu là hàng hợp lệ vẫn được ghi, hàng lỗi được lưu để xem lại, cách mặc định này không đáp ứng.

### 2.3. Exception DML khác exception do PL/SQL tự kiểm tra

SAVE EXCEPTIONS thu thập lỗi phát sinh khi từng lần thực thi DML trong FORALL. Nó không tự biến mọi lỗi logic trong PL/SQL thành một bản ghi trong SQL%BULK_EXCEPTIONS.

- Vi phạm unique/check/foreign key trong một iteration: có thể được thu thập.
- Một phần tử không khớp WHERE của UPDATE: không phải lỗi, row count bằng 0.
- Lỗi PL/SQL xảy ra trước khi FORALL bắt đầu: không thuộc danh sách lỗi của FORALL.
- Lỗi parse, quyền hoặc lỗi cấu trúc của statement: không nhất thiết là lỗi row-level được lưu như một iteration.

## 3. SAVE EXCEPTIONS hoạt động như thế nào?

### 3.1. Cú pháp

Thêm SAVE EXCEPTIONS sau bounds clause của FORALL:

```sql
FORALL i IN 1 .. l_codes.COUNT SAVE EXCEPTIONS
    INSERT INTO lab_items (item_code)
    VALUES (l_codes(i));
```

Nếu một iteration lỗi:

1. Oracle ghi nhận thông tin lỗi của iteration.
2. DML iteration bị lỗi không được xem là thành công.
3. Oracle tiếp tục các iteration còn lại.
4. Sau khi thử các iteration, nếu có lỗi được lưu, Oracle phát sinh exception ORA-24381.
5. Block PL/SQL bắt exception và đọc SQL%BULK_EXCEPTIONS.

### 3.2. Dòng thời gian

```text
FORALL ... SAVE EXCEPTIONS
          |
          v
     Iteration 1 ---- DML thành công
          |
          v
     Iteration 2 ---- DML lỗi -> lưu error
          |
          v
     Iteration 3 ---- DML thành công
          |
          v
     Iteration 4 ---- DML lỗi -> lưu error
          |
          v
     Iteration 5 ---- DML thành công
          |
          v
     Kết thúc FORALL
          |
          v
     ORA-24381 được phát sinh
          |
          v
     EXCEPTION HANDLER
       - SQL%BULK_EXCEPTIONS
       - SQL%BULK_ROWCOUNT
       - SQL%ROWCOUNT
```

### 3.3. SAVE EXCEPTIONS không bỏ qua lỗi

SAVE EXCEPTIONS không làm statement trở thành luôn thành công. Nó gom lỗi theo iteration để chương trình xử lý sau khi FORALL đã thử các phần tử. Nếu có lỗi, exception tổng hợp vẫn được phát sinh.

Không nuốt ORA-24381 rồi báo batch thành công hoàn toàn. Caller cần nhận được trạng thái partial success hoặc exception nghiệp vụ tương ứng.

### 3.4. Thay đổi thành công vẫn thuộc transaction hiện tại

Với SAVE EXCEPTIONS, các iteration thành công vẫn giữ thay đổi trong transaction hiện tại. Oracle không COMMIT các hàng này. Caller có thể:

- COMMIT để giữ cả các hàng thành công và log lỗi nếu nghiệp vụ chấp nhận partial success.
- ROLLBACK để hủy toàn bộ thay đổi trong transaction.
- ROLLBACK TO SAVEPOINT để hủy phần batch nhưng giữ các thay đổi trước savepoint.

Các iteration lỗi không để lại thay đổi DML thành công của chính iteration đó. Transaction vẫn do caller kiểm soát.

## 4. Bắt ORA-24381 bằng PRAGMA EXCEPTION_INIT

### 4.1. ORA-24381 là lỗi tổng hợp

Khi FORALL SAVE EXCEPTIONS có ít nhất một iteration thất bại, Oracle phát sinh:

```text
ORA-24381: error(s) in array DML
```

Trong PL/SQL, có thể đặt tên exception cho mã lỗi -24381 bằng PRAGMA EXCEPTION_INIT.

### 4.2. Khai báo exception

```sql
DECLARE
    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    NULL;
END;
/
```

ERROR_CODE trong SQL%BULK_EXCEPTIONS được cung cấp dưới dạng số dương; khi khai báo exception, dùng mã Oracle âm -24381.

### 4.3. Bắt lỗi

```sql
EXCEPTION
    WHEN e_bulk_errors THEN
        -- Xử lý danh sách lỗi bulk.
        NULL;
```

Handler chuyên biệt giúp phân biệt partial bulk error với các lỗi khác. Nếu vẫn cần WHEN OTHERS, đặt sau các handler cụ thể và re-raise lỗi không mong đợi.

### 4.4. Phân biệt ORA-24381 với lỗi gốc

ORA-24381 báo rằng một hoặc nhiều iteration DML đã lỗi. Mã lỗi cụ thể của từng iteration nằm trong SQL%BULK_EXCEPTIONS(j).ERROR_CODE, ví dụ:

| Mã lỗi | Ý nghĩa ví dụ |
| --- | --- |
| ORA-00001 | Vi phạm unique constraint/index |
| ORA-01400 | Insert NULL vào cột NOT NULL |
| ORA-02290 | Vi phạm CHECK constraint |
| ORA-02291 | Không tìm thấy khóa cha của foreign key |
| ORA-02292 | Không thể xóa hàng cha vì còn hàng con |
| ORA-12899 | Giá trị quá dài so với cột |

Đây là ví dụ thường gặp; mã lỗi thực tế phụ thuộc statement và schema.

## 5. SQL%BULK_EXCEPTIONS

### 5.1. Cấu trúc

SQL%BULK_EXCEPTIONS là collection thuộc implicit bulk SQL cursor. Mỗi phần tử mô tả một lỗi được lưu bởi FORALL SAVE EXCEPTIONS.

| Thuộc tính | Ý nghĩa |
| --- | --- |
| SQL%BULK_EXCEPTIONS.COUNT | Số lỗi được ghi nhận |
| SQL%BULK_EXCEPTIONS(j).ERROR_INDEX | Chỉ số iteration liên quan tới lỗi |
| SQL%BULK_EXCEPTIONS(j).ERROR_CODE | Mã lỗi Oracle dạng số dương |

Ví dụ đọc lỗi:

```sql
FOR j IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
    DBMS_OUTPUT.PUT_LINE(
        'Iteration = ' ||
        SQL%BULK_EXCEPTIONS(j).ERROR_INDEX
    );

    DBMS_OUTPUT.PUT_LINE(
        'Error code = ' ||
        SQL%BULK_EXCEPTIONS(j).ERROR_CODE
    );

    DBMS_OUTPUT.PUT_LINE(
        SQLERRM(-SQL%BULK_EXCEPTIONS(j).ERROR_CODE)
    );
END LOOP;
```

### 5.2. Vì sao ERROR_CODE là số dương?

ERROR_CODE lưu mã lỗi không có dấu âm. SQLERRM nhận mã lỗi âm để tạo thông báo. Vì vậy, dùng:

```sql
SQLERRM(-SQL%BULK_EXCEPTIONS(j).ERROR_CODE)
```

Không truyền mã dương vào SQLERRM rồi mong nhận thông báo lỗi tương ứng.

### 5.3. ERROR_INDEX ánh xạ về input

Với FORALL dùng range liên tục:

```sql
FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
```

Nếu ERROR_INDEX = 3, lỗi thuộc iteration i = 3; có thể dùng l_ids(3) để tìm input gốc.

Với collection thưa hoặc dùng INDICES OF/VALUES OF, phải hiểu mapping của bounds clause. Không tự giả định vị trí thứ j trong SQL%BULK_EXCEPTIONS là chỉ số collection gốc. Hãy dùng chỉ số được Oracle báo và ánh xạ đúng theo cách FORALL duyệt collection.

### 5.4. Thứ tự lỗi

SQL%BULK_EXCEPTIONS là danh sách các lỗi được thu thập. Dùng ERROR_INDEX làm khóa xác định iteration, không dùng vị trí j trong danh sách lỗi làm chỉ số input. Một batch có thể chỉ lỗi ở iteration 2 và 9; khi đó collection lỗi có hai phần tử, nhưng ERROR_INDEX lần lượt chỉ 2 và 9.

### 5.5. Lỗi nhiều lần trên cùng khóa

Nếu input lặp cùng một business key, một iteration có thể thành công và iteration sau bị unique violation. ERROR_INDEX giúp tìm đúng phần tử input gây lỗi. Đừng chỉ lưu business key nếu cần phân biệt hai dòng input trùng nhau; hãy lưu thêm batch ID, source row number hoặc correlation ID.

## 6. SQL%BULK_ROWCOUNT và SQL%ROWCOUNT

### 6.1. SQL%BULK_ROWCOUNT(i)

SQL%BULK_ROWCOUNT(i) trả về số hàng bị tác động bởi lần thực thi DML tương ứng với iteration i của FORALL.

Ví dụ:

```sql
FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
    UPDATE lab_employees
    SET status = 'ACTIVE'
    WHERE employee_id = l_ids(i);
```

Nếu ID đầu tiên khớp một hàng, ID thứ hai không khớp hàng nào và ID thứ ba khớp một hàng:

| Iteration | SQL%BULK_ROWCOUNT |
| ---: | ---: |
| 1 | 1 |
| 2 | 0 |
| 3 | 1 |

Không có exception chỉ vì iteration 2 có row count 0.

### 6.2. SQL%ROWCOUNT

Sau FORALL, SQL%ROWCOUNT là tổng số hàng bị tác động bởi các lần thực thi DML trong bulk statement. Với ví dụ trên, tổng là 2.

Khi SAVE EXCEPTIONS có lỗi, trong handler hãy chụp tổng số hàng thành công bằng biến PL/SQL:

```sql
EXCEPTION
    WHEN e_bulk_errors THEN
        l_total_rows := SQL%ROWCOUNT;
        l_error_count := SQL%BULK_EXCEPTIONS.COUNT;
```

Chụp giá trị trước khi chạy câu SQL logging hoặc gọi procedure khác, vì SQL%ROWCOUNT mô tả SQL gần nhất.

### 6.3. So sánh

| Thuộc tính | Trả lời câu hỏi |
| --- | --- |
| SQL%ROWCOUNT | Tổng cộng bulk DML đã tác động bao nhiêu hàng? |
| SQL%BULK_ROWCOUNT(i) | Iteration i đã tác động bao nhiêu hàng? |
| SQL%BULK_EXCEPTIONS.COUNT | Có bao nhiêu iteration lỗi được lưu? |
| ERROR_INDEX | Iteration nào gặp lỗi? |
| ERROR_CODE | Mã lỗi Oracle của iteration đó là gì? |

### 6.4. Tổng iteration không đồng nghĩa tổng hàng

Nếu một iteration UPDATE theo điều kiện có thể tác động nhiều hàng, SQL%BULK_ROWCOUNT(i) có thể lớn hơn 1. Nếu không có hàng khớp, giá trị là 0. Vì vậy:

- Số iteration đã thử = số input được FORALL duyệt.
- Số iteration lỗi = SQL%BULK_EXCEPTIONS.COUNT.
- Tổng số hàng bị tác động = SQL%ROWCOUNT.

Ba con số này không nhất thiết bằng nhau.

## 7. Mẫu xử lý lỗi chuẩn

### 7.1. Skeleton tổng quát

```sql
DECLARE
    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);

    l_rows_affected PLS_INTEGER := 0;
    l_error_count   PLS_INTEGER := 0;
BEGIN
    FORALL i IN 1 .. l_values.COUNT SAVE EXCEPTIONS
        INSERT INTO target_table (value_col)
        VALUES (l_values(i));

    l_rows_affected := SQL%ROWCOUNT;

EXCEPTION
    WHEN e_bulk_errors THEN
        l_rows_affected := SQL%ROWCOUNT;
        l_error_count := SQL%BULK_EXCEPTIONS.COUNT;

        FOR j IN 1 .. l_error_count LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Input index = ' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_INDEX
            );
            DBMS_OUTPUT.PUT_LINE(
                'Error = ' ||
                SQLERRM(-SQL%BULK_EXCEPTIONS(j).ERROR_CODE)
            );
        END LOOP;
END;
/
```

Đây là khung minh họa. Trong ứng dụng thực tế, cần thêm collection khai báo, mapping input, policy transaction và cách trả trạng thái cho caller.

### 7.2. Bắt riêng ORA-24381

Handler chuyên biệt giúp phân biệt partial bulk error với các lỗi khác:

```sql
EXCEPTION
    WHEN e_bulk_errors THEN
        -- Xử lý danh sách lỗi bulk.
        NULL;
    WHEN OTHERS THEN
        -- Lỗi ngoài dự kiến.
        RAISE;
```

Không biến mọi exception thành một dòng bulk failed chung; điều đó làm mất thông tin lỗi lập trình, quyền, object invalid hoặc lỗi runtime khác.

### 7.3. Chụp thông tin trước khi ghi log

Nếu handler INSERT vào bảng log, câu INSERT đó sẽ làm thay đổi SQL%ROWCOUNT. Hãy lưu trước:

```sql
l_rows_affected := SQL%ROWCOUNT;
l_error_count   := SQL%BULK_EXCEPTIONS.COUNT;
```

Nếu cần thực hiện thêm FORALL khác, hãy sao chép chi tiết lỗi cần giữ vào collection PL/SQL riêng trước khi chạy FORALL tiếp theo.

## 8. Ví dụ hoàn chỉnh: INSERT nhiều hàng và ghi nhận lỗi

### 8.1. Tạo bảng đích

Chạy trong schema lab:

```sql
CREATE TABLE lab_bulk_items (
    item_id    NUMBER(10)
        CONSTRAINT pk_lab_bulk_items PRIMARY KEY,
    item_code  VARCHAR2(20)
        CONSTRAINT uq_lab_bulk_items_code UNIQUE,
    quantity   NUMBER(10)
        CONSTRAINT ck_lab_bulk_items_qty CHECK (quantity >= 0),
    item_name  VARCHAR2(30) NOT NULL
);
```

### 8.2. Tạo collection input và chạy FORALL

```sql
DECLARE
    TYPE t_item_ids IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE t_item_codes IS TABLE OF VARCHAR2(20) INDEX BY PLS_INTEGER;
    TYPE t_quantities IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE t_item_names IS TABLE OF VARCHAR2(30) INDEX BY PLS_INTEGER;

    l_ids   t_item_ids;
    l_codes t_item_codes;
    l_qty   t_quantities;
    l_names t_item_names;

    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);

    l_rows_affected PLS_INTEGER := 0;
    l_error_count   PLS_INTEGER := 0;
BEGIN
    l_ids(1) := 1;
    l_ids(2) := 2;
    l_ids(3) := 3;
    l_ids(4) := 4;
    l_ids(5) := 5;

    l_codes(1) := 'A01';
    l_codes(2) := 'A02';
    l_codes(3) := 'A01'; -- Trùng mã ở iteration 1.
    l_codes(4) := 'A04';
    l_codes(5) := 'A05';

    l_qty(1) := 10;
    l_qty(2) := 20;
    l_qty(3) := 30;
    l_qty(4) := -5; -- Vi phạm CHECK.
    l_qty(5) := 40;

    l_names(1) := 'Keyboard';
    l_names(2) := 'Mouse';
    l_names(3) := 'Duplicate';
    l_names(4) := 'Invalid quantity';
    l_names(5) := 'Monitor';

    BEGIN
        FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
            INSERT INTO lab_bulk_items (
                item_id, item_code, quantity, item_name
            )
            VALUES (
                l_ids(i), l_codes(i), l_qty(i), l_names(i)
            );

        l_rows_affected := SQL%ROWCOUNT;

    EXCEPTION
        WHEN e_bulk_errors THEN
            l_rows_affected := SQL%ROWCOUNT;
            l_error_count := SQL%BULK_EXCEPTIONS.COUNT;

            DBMS_OUTPUT.PUT_LINE(
                'Successful affected rows = ' || l_rows_affected
            );
            DBMS_OUTPUT.PUT_LINE(
                'Failed iterations = ' || l_error_count
            );

            FOR j IN 1 .. l_error_count LOOP
                DECLARE
                    l_index PLS_INTEGER;
                    l_code  PLS_INTEGER;
                BEGIN
                    l_index := SQL%BULK_EXCEPTIONS(j).ERROR_INDEX;
                    l_code := SQL%BULK_EXCEPTIONS(j).ERROR_CODE;

                    DBMS_OUTPUT.PUT_LINE(
                        'Iteration ' || l_index ||
                        ', item_id=' || l_ids(l_index) ||
                        ', item_code=' || l_codes(l_index)
                    );
                    DBMS_OUTPUT.PUT_LINE(
                        'Oracle error=' || l_code ||
                        ', message=' || SQLERRM(-l_code)
                    );
                END;
            END LOOP;
    END;
END;
/
```

Với bảng ban đầu rỗng và dữ liệu mẫu, iteration 1, 2 và 5 có thể INSERT thành công; iteration 3 vi phạm unique constraint; iteration 4 vi phạm CHECK constraint. Số hàng bị tác động tổng dự kiến là 3, số lỗi là 2.

### 8.3. Xem dữ liệu thành công

```sql
SELECT item_id, item_code, quantity, item_name
FROM lab_bulk_items
ORDER BY item_id;
```

Kết quả dự kiến có các mã A01, A02 và A05. Hàng lỗi không được chèn.

### 8.4. Kiểm tra transaction

Các hàng đã INSERT thành công vẫn thuộc transaction hiện tại. Nếu chạy ROLLBACK, các hàng thành công của batch bị rollback. Nếu muốn giữ kết quả lab, COMMIT sau khi đã xác nhận kết quả. Không thêm COMMIT tự động vào procedure bulk dùng chung nếu caller cần kiểm soát transaction lớn hơn.

## 9. Ghi lỗi vào bảng error log

### 9.1. Vì sao cần error table?

DBMS_OUTPUT chỉ hữu ích khi người vận hành đang xem output. Batch chạy nền cần lưu thông tin lỗi để:

- Biết batch nào có lỗi.
- Tìm lại input nguồn gây lỗi.
- Xem mã và thông báo Oracle.
- Retry đúng phần tử sau khi sửa dữ liệu.
- Theo dõi số hàng thành công và thất bại.
- Đối chiếu với file nguồn hoặc hệ thống upstream.

### 9.2. Tạo bảng log

```sql
CREATE TABLE lab_bulk_error_log (
    error_log_id  NUMBER GENERATED BY DEFAULT AS IDENTITY
                  CONSTRAINT pk_lab_bulk_error_log PRIMARY KEY,
    batch_id      VARCHAR2(50) NOT NULL,
    input_index   NUMBER,
    source_key    VARCHAR2(100),
    error_code    NUMBER,
    error_message VARCHAR2(2000),
    logged_at     TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
```

### 9.3. Ghi từng lỗi

Trong exception handler, chụp các giá trị tổng trước rồi ghi lỗi:

```sql
EXCEPTION
    WHEN e_bulk_errors THEN
        l_rows_affected := SQL%ROWCOUNT;
        l_error_count := SQL%BULK_EXCEPTIONS.COUNT;

        FOR j IN 1 .. l_error_count LOOP
            l_index := SQL%BULK_EXCEPTIONS(j).ERROR_INDEX;
            l_code := SQL%BULK_EXCEPTIONS(j).ERROR_CODE;

            INSERT INTO lab_bulk_error_log (
                batch_id,
                input_index,
                source_key,
                error_code,
                error_message
            )
            VALUES (
                p_batch_id,
                l_index,
                l_source_keys(l_index),
                l_code,
                SQLERRM(-l_code)
            );
        END LOOP;
```

Đoạn trên cần đặt trong procedure/block đã khai báo p_batch_id, l_index, l_code và collection l_source_keys. Nếu collection sparse hoặc dùng VALUES OF, ánh xạ input theo bounds clause thực tế.

### 9.4. Log cùng transaction

Nếu bảng log được INSERT trong cùng transaction:

- COMMIT sẽ giữ cả hàng DML thành công và error log.
- ROLLBACK sẽ hủy cả hàng DML thành công và error log.
- Đây là lựa chọn tốt nếu log là một phần của kết quả batch và phải nhất quán với transaction.

### 9.5. Log độc lập với transaction

Đôi khi cần giữ diagnostic log ngay cả khi caller rollback toàn batch. Có thể thiết kế một logger autonomous transaction riêng, nhưng phải cân nhắc:

- Log độc lập có thể tồn tại dù batch nghiệp vụ bị rollback.
- Logger phải nhận đủ batch ID, input key và error details qua tham số.
- Không gọi external service hoặc ghi quá nhiều log trong mỗi hàng nếu không cần.
- Không để logger đọc dữ liệu chưa commit của transaction cha.
- Không biến autonomous transaction thành cách commit business data một phần không kiểm soát.

Đối với lỗi bulk, cách đơn giản và dễ kiểm soát thường là lưu log cùng transaction rồi để caller quyết định commit/rollback. Chỉ dùng log độc lập khi yêu cầu vận hành thực sự cần.

## 10. Collection dense, sparse và ERROR_INDEX

### 10.1. Dense collection

Collection dense có các chỉ số liên tục, ví dụ 1, 2, 3, 4:

```sql
FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
    INSERT INTO lab_target (id) VALUES (l_ids(i));
```

Trong trường hợp này ERROR_INDEX tương ứng trực tiếp với i, nên dùng được l_ids(ERROR_INDEX) để tìm input.

### 10.2. Sparse collection

Collection associative array có thể có các chỉ số 10, 20, 50 thay vì 1, 2, 3. Khi đó không nên dùng 1..COUNT vì các phần tử 1, 2, 3 không tồn tại.

Dùng INDICES OF:

```sql
FORALL i IN INDICES OF l_ids SAVE EXCEPTIONS
    DELETE FROM lab_target
    WHERE id = l_ids(i);
```

INDICES OF duyệt các subscript hiện có. Khi xử lý ERROR_INDEX, ánh xạ theo subscript/iteration mà FORALL báo, không lấy vị trí thứ tự trong danh sách lỗi làm chỉ số input.

### 10.3. VALUES OF

VALUES OF dùng một collection chỉ số để chỉ định các phần tử của collection dữ liệu:

```sql
TYPE t_index_list IS TABLE OF PLS_INTEGER
    INDEX BY PLS_INTEGER;

l_selected_indices(1) := 10;
l_selected_indices(2) := 50;

FORALL i IN VALUES OF l_selected_indices SAVE EXCEPTIONS
    UPDATE lab_target
    SET status = 'READY'
    WHERE id = l_ids(i);
```

Trong ví dụ, collection chỉ số chọn các phần tử l_ids(10) và l_ids(50). Khi dùng VALUES OF, đọc kỹ ý nghĩa ERROR_INDEX trong ngữ cảnh iteration/index collection và giữ mapping rõ ràng từ iteration tới source row. Đừng hard-code giả định rằng chỉ số lỗi luôn là vị trí liên tục 1..COUNT.

### 10.4. Lưu source key cùng dữ liệu

Để retry và audit, nên giữ song song:

- Collection chứa dữ liệu DML.
- Collection chứa source row number hoặc business key.
- Batch ID/correlation ID.

Khi lỗi, dùng ERROR_INDEX để truy ngược input gốc. Nếu input được transform hoặc lọc trước FORALL, lưu mapping từ iteration sang source record ngay khi xây collection.

## 11. Kết hợp BULK COLLECT và FORALL SAVE EXCEPTIONS

### 11.1. Fetch theo batch

Với bảng nguồn lớn, không BULK COLLECT toàn bộ hàng vào PGA. Dùng cursor và LIMIT:

```sql
DECLARE
    CURSOR c_source IS
        SELECT source_id, item_code, quantity, item_name
        FROM lab_source_items
        WHERE processed_flag = 'N';

    TYPE t_source_id IS TABLE OF lab_source_items.source_id%TYPE;
    TYPE t_code IS TABLE OF lab_source_items.item_code%TYPE;
    TYPE t_qty IS TABLE OF lab_source_items.quantity%TYPE;
    TYPE t_name IS TABLE OF lab_source_items.item_name%TYPE;

    l_source_ids t_source_id;
    l_codes      t_code;
    l_qty        t_qty;
    l_names      t_name;
BEGIN
    OPEN c_source;
    LOOP
        FETCH c_source BULK COLLECT
        INTO l_source_ids, l_codes, l_qty, l_names
        LIMIT 500;

        EXIT WHEN l_source_ids.COUNT = 0;

        -- FORALL xử lý batch hiện tại.
        NULL;
    END LOOP;
    CLOSE c_source;
END;
/
```

Mỗi lần FETCH lấy tối đa 500 hàng trong ví dụ. Kích thước 500 chỉ để minh họa; chọn theo bộ nhớ, kích thước row, latency và khả năng rollback.

### 11.2. Bulk insert có SAVE EXCEPTIONS

Trong vòng lặp batch, có thể thực hiện:

```sql
FORALL i IN 1 .. l_source_ids.COUNT SAVE EXCEPTIONS
    INSERT INTO lab_target_items (
        source_id, item_code, quantity, item_name
    )
    VALUES (
        l_source_ids(i), l_codes(i), l_qty(i), l_names(i)
    );
```

Nếu có lỗi, xử lý ORA-24381 ngay trong vòng lặp để ghi nhận lỗi cho đúng batch trước khi fetch batch tiếp theo. Không để SQL%BULK_EXCEPTIONS của batch sau làm mất ngữ cảnh cần xử lý của batch trước.

### 11.3. Cộng dồn số hàng thành công

SQL%ROWCOUNT chỉ phản ánh FORALL gần nhất. Dùng biến tổng:

```sql
l_total_inserted := l_total_inserted + SQL%ROWCOUNT;
```

Nếu batch phát sinh ORA-24381, chụp SQL%ROWCOUNT trong handler rồi cộng vào tổng. Tương tự, cộng số lỗi từ SQL%BULK_EXCEPTIONS.COUNT.

### 11.4. Giữ mapping khi fetch theo lô

ERROR_INDEX chỉ có ý nghĩa trong batch FORALL hiện tại. Nếu cần biết source row toàn file, lưu source row number trong collection cùng batch. Ví dụ:

```sql
l_source_row_no(i) := l_global_row_no;
```

Khi lỗi, dùng chỉ số iteration để tra l_source_row_no và ghi row number gốc. Nhờ vậy error log chỉ ra được dòng nguồn thay vì chỉ báo iteration 17.

## 12. SAVE EXCEPTIONS và transaction policy

### 12.1. Partial success

Nếu nghiệp vụ cho phép các hàng hợp lệ được giữ lại, quy trình có thể:

1. Chạy FORALL SAVE EXCEPTIONS.
2. Chụp số hàng thành công và danh sách lỗi.
3. Ghi lỗi vào error table.
4. Đánh dấu source record thành công/thất bại theo batch contract.
5. Caller COMMIT khi trạng thái batch đã được ghi đầy đủ.
6. Retry các hàng lỗi sau khi dữ liệu được sửa.

Điểm mấu chốt là trạng thái batch và error log phải nhất quán với các hàng thành công.

### 12.2. All-or-nothing

Nếu nghiệp vụ yêu cầu toàn bộ batch phải thành công hoặc không có hàng nào được giữ, dùng SAVEPOINT trước FORALL:

```sql
SAVEPOINT before_bulk_batch;

BEGIN
    FORALL i IN 1 .. l_values.COUNT SAVE EXCEPTIONS
        INSERT INTO lab_target (value_col)
        VALUES (l_values(i));

EXCEPTION
    WHEN e_bulk_errors THEN
        ROLLBACK TO before_bulk_batch;
        RAISE;
END;
```

ROLLBACK TO SAVEPOINT hủy thay đổi của batch sau mốc đó. Nó không rollback các thay đổi trước SAVEPOINT. Nếu ghi error log sau rollback, log đó thuộc phần transaction còn lại; caller vẫn cần quyết định commit.

### 12.3. Partial success không có nghĩa commit từng hàng

SAVE EXCEPTIONS không commit sau mỗi iteration. Nếu caller chưa commit, các hàng thành công vẫn chưa được commit. Không dùng từ “đã lưu” khi chỉ mới “được DML tác động”.

Trong báo cáo batch, nên tách:

- attempted_count: số input đã gửi vào FORALL.
- affected_count: tổng số hàng DML thực sự tác động.
- failed_iteration_count: số iteration lỗi.
- zero_row_count: số iteration chạy thành công nhưng không tác động hàng nào (đối với UPDATE/DELETE).
- committed_count: số hàng được giữ sau transaction commit, nếu ứng dụng có cách xác định chính xác.

### 12.4. Exception không tự rollback toàn transaction

SAVE EXCEPTIONS phát sinh ORA-24381 nhưng không tự quyết định rollback transaction. Nếu exception thoát ra khỏi procedure, caller có thể rollback; nếu handler bắt và không re-raise, transaction vẫn tiếp tục. Thiết kế exception contract rõ để caller không vô tình commit dữ liệu partial mà không biết.

### 12.5. Không COMMIT trong mỗi iteration

Không đặt COMMIT trong function/procedure được gọi cho từng phần tử của FORALL. FORALL thực thi một DML statement bulk; transaction boundary nên do caller hoặc batch coordinator quản lý. Commit quá thường xuyên làm giảm khả năng rollback toàn batch và tạo trạng thái khó khôi phục.

## 13. Retry an toàn các phần tử lỗi

### 13.1. Không retry mù

Không phải mọi lỗi đều có thể retry ngay:

| Nhóm lỗi | Ví dụ | Cách xử lý thường gặp |
| --- | --- | --- |
| Dữ liệu không hợp lệ | ORA-02290, ORA-01400, ORA-12899 | Sửa input hoặc từ chối record |
| Duplicate | ORA-00001 | Kiểm tra idempotency/business rule; không retry nguyên trạng |
| Thiếu parent | ORA-02291 | Nạp parent trước hoặc chờ dependency |
| Khóa/đồng thời | Một số lỗi deadlock/serialization/lock timeout | Retry có giới hạn sau khi xác định transaction an toàn |
| Lỗi quyền/object | ORA-01031, object invalid | Sửa cấu hình/triển khai, không retry liên tục |

Mã lỗi cụ thể và chính sách retry phụ thuộc workload. Retry chỉ hợp lý khi nguyên nhân có thể biến mất và thao tác có tính idempotent hoặc được bảo vệ bằng khóa nghiệp vụ.

### 13.2. Idempotency key

Một batch có thể được chạy lại sau timeout hoặc lỗi ứng dụng. Dùng source ID hoặc batch ID có constraint unique để tránh insert trùng khi retry:

```sql
CREATE TABLE lab_import_target (
    source_record_id VARCHAR2(100) NOT NULL,
    payload_value    VARCHAR2(200),
    CONSTRAINT uq_lab_import_source UNIQUE (source_record_id)
);
```

Unique key giúp phát hiện record đã được xử lý, nhưng duplicate không tự cho biết dữ liệu cũ có giống dữ liệu mới hay không. Ứng dụng cần quy định duplicate là success-idempotent, conflict cần điều tra hay update theo phiên bản.

### 13.3. Lưu trạng thái retry

Error log nên chứa:

- Batch ID.
- Source record ID.
- Input version/hash nếu cần xác định dữ liệu đã đổi.
- Error code và error message.
- Trạng thái NEW, RETRY_READY, RETRIED, REJECTED hoặc trạng thái tương đương.
- Số lần retry và thời điểm retry cuối.

Không lưu dữ liệu nhạy cảm thô trong error message nếu log được truy cập rộng; lưu khóa tham chiếu và thông tin cần thiết để truy vết.

### 13.4. Giới hạn retry

Đặt retry count tối đa, backoff và điều kiện dừng. Lỗi dữ liệu cố định như CHECK violation sẽ không tự hết nếu chạy lại ngay. Retry vô hạn có thể làm batch kẹt, tăng tải và tạo log lặp.

### 13.5. Retry theo batch nhỏ

Sau khi sửa input lỗi, có thể gom riêng các record thất bại vào collection mới và chạy lại FORALL. Không chạy lại toàn bộ batch nếu các hàng thành công đã được commit, trừ khi DML có tính idempotent và duplicate được xử lý có chủ đích.

## 14. SAVE EXCEPTIONS và DML error logging (LOG ERRORS)

Oracle có hai cơ chế khác nhau để ghi nhận lỗi DML: PL/SQL bulk exception handling và SQL DML error logging.

### 14.1. SAVE EXCEPTIONS

- Chỉ dùng với FORALL.
- Lỗi được ánh xạ về iteration/input index.
- Có thể đọc mã lỗi bằng SQL%BULK_EXCEPTIONS.
- Có thể đọc số hàng từng iteration bằng SQL%BULK_ROWCOUNT.
- Cần viết PL/SQL handler và logic lưu/retry lỗi.
- Phù hợp khi input nằm trong collection và cần biết chính xác phần tử nào lỗi.

### 14.2. LOG ERRORS

DML error logging cho phép một số lỗi row-level được ghi vào error logging table trong khi statement tiếp tục xử lý các hàng khác.

Tạo error table:

```sql
BEGIN
    DBMS_ERRLOG.CREATE_ERROR_LOG(
        dml_table_name => 'LAB_TARGET_ITEMS',
        err_log_table_name => 'ERR$_LAB_TARGET_ITEMS'
    );
END;
/
```

Chạy DML:

```sql
INSERT INTO lab_target_items (
    item_id, item_code, quantity, item_name
)
SELECT
    item_id, item_code, quantity, item_name
FROM lab_source_items
LOG ERRORS INTO err$_lab_target_items ('BATCH-2026-01')
REJECT LIMIT UNLIMITED;
```

Sau đó truy vấn bảng lỗi:

```sql
SELECT
    ora_err_number$,
    ora_err_mesg$,
    ora_err_tag$,
    item_id,
    item_code
FROM err$_lab_target_items
WHERE ora_err_tag$ = 'BATCH-2026-01';
```

Kiểm tra tên cột trong error table được tạo bởi DBMS_ERRLOG vì nó còn phụ thuộc cột của bảng đích và phiên bản. Một số kiểu dữ liệu/loại lỗi không được hỗ trợ ghi error theo cách này.

### 14.3. Chọn cơ chế nào?

| Nhu cầu | Cơ chế thường phù hợp |
| --- | --- |
| Dữ liệu đã nằm trong collection PL/SQL | FORALL SAVE EXCEPTIONS |
| Cần mapping lỗi theo iteration và collection input | SAVE EXCEPTIONS |
| Một câu INSERT ... SELECT lớn cần bỏ qua row errors được hỗ trợ | LOG ERRORS |
| Cần điều khiển retry từng input bằng PL/SQL | SAVE EXCEPTIONS |
| Cần lưu lỗi row-level ngay trong SQL DML | LOG ERRORS |

Hai cơ chế có thể phục vụ workload tương tự nhưng không thay thế hoàn toàn cho nhau. LOG ERRORS có giới hạn loại lỗi và kiểu cột; SAVE EXCEPTIONS yêu cầu FORALL và PL/SQL collection.

### 14.4. Không giả định LOG ERRORS bắt mọi lỗi

Một số lỗi statement-level, lỗi cấu trúc, lỗi parse, lỗi quyền hoặc các trường hợp bị Oracle loại trừ không được chuyển thành row error trong bảng log. Đọc Oracle Database SQL Language Reference và DBMS_ERRLOG documentation cho đúng release, DML type và data type.

## 15. FORALL với UPDATE và DELETE

### 15.1. UPDATE có lỗi một số phần tử

Ví dụ cập nhật số dư:

```sql
DECLARE
    TYPE t_account_ids IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE t_amounts IS TABLE OF NUMBER INDEX BY PLS_INTEGER;

    l_ids t_account_ids;
    l_amounts t_amounts;

    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
    l_total_rows PLS_INTEGER := 0;
BEGIN
    l_ids(1) := 10;
    l_ids(2) := 20;
    l_ids(3) := 30;

    l_amounts(1) := 100;
    l_amounts(2) := -50;
    l_amounts(3) := 200;

    FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
        UPDATE lab_accounts
        SET balance = balance + l_amounts(i)
        WHERE account_id = l_ids(i);

    l_total_rows := SQL%ROWCOUNT;
EXCEPTION
    WHEN e_bulk_errors THEN
        l_total_rows := SQL%ROWCOUNT;

        FOR i IN 1 .. l_ids.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Account ' || l_ids(i) ||
                ', affected rows=' || SQL%BULK_ROWCOUNT(i)
            );
        END LOOP;

        FOR j IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Failed input index=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_INDEX ||
                ', message=' ||
                SQLERRM(-SQL%BULK_EXCEPTIONS(j).ERROR_CODE)
            );
        END LOOP;
END;
/
```

Ví dụ giả định có constraint không cho balance âm. Nếu UPDATE khớp account nhưng dữ liệu vi phạm constraint, iteration đó có thể lỗi; nếu account không tồn tại, iteration có thể thành công với row count 0.

### 15.2. DELETE theo danh sách ID

```sql
FORALL i IN 1 .. l_order_ids.COUNT SAVE EXCEPTIONS
    DELETE FROM lab_orders
    WHERE order_id = l_order_ids(i);
```

Nếu DELETE một order bị chặn bởi foreign key, iteration có thể lỗi và được thu thập. ID không tồn tại có row count 0, không phải lỗi. Dùng SQL%BULK_ROWCOUNT để phân biệt iteration không tác động hàng với iteration lỗi.

### 15.3. MERGE và SAVE EXCEPTIONS

FORALL hỗ trợ một DML statement, trong đó statement có thể là MERGE nếu cú pháp/phiên bản và bind collection phù hợp. SAVE EXCEPTIONS áp dụng cho lỗi từng lần thực thi MERGE trong FORALL. SQL%BULK_EXCEPTIONS chỉ cho biết iteration và mã lỗi, không tự tách số INSERT/UPDATE của mỗi MERGE. Nếu cần thống kê chi tiết từng nhánh, thiết kế audit/action riêng.

## 16. FORALL với dynamic SQL

FORALL cũng có thể dùng với EXECUTE IMMEDIATE trong các trường hợp cú pháp hỗ trợ. Cần giữ câu SQL ổn định và bind collection đúng vị trí:

```sql
FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
    EXECUTE IMMEDIATE
        'UPDATE lab_employees
         SET status = :1
         WHERE employee_id = :2'
    USING l_statuses(i), l_ids(i);
```

Lỗi DML theo iteration có thể được thu thập bằng SAVE EXCEPTIONS. Không nối trực tiếp input không tin cậy vào SQL text; bind giá trị và whitelist/DBMS_ASSERT cho identifier.

Khi dùng dynamic SQL phức tạp, debug khó hơn vì SQL text được tạo lúc chạy. Ghi nhận statement template, batch ID và input index để truy vết. Đảm bảo bind order khớp placeholders.

## 17. Lưu ý với trigger, constraint và lỗi phụ thuộc dữ liệu

### 17.1. Trigger có thể làm DML iteration lỗi

INSERT/UPDATE trong FORALL vẫn kích hoạt trigger theo quy tắc Oracle. Nếu trigger phát sinh exception, iteration tương ứng có thể thất bại và được thu thập nếu lỗi nằm trong phạm vi SAVE EXCEPTIONS.

Không giả định SAVE EXCEPTIONS cô lập side effect của trigger ngoài transaction semantics. Các thao tác trigger thành công thuộc transaction; khi caller rollback, chúng cũng rollback trừ khi trigger/procedure cố ý dùng autonomous transaction.

### 17.2. Constraint deferred

Constraint có thể được kiểm tra ngay hoặc trì hoãn đến thời điểm commit tùy khai báo và trạng thái transaction. Nếu lỗi chỉ xuất hiện khi COMMIT do deferred constraint, nó không nhất thiết xuất hiện như một lỗi iteration để SAVE EXCEPTIONS thu thập.

SAVE EXCEPTIONS không thay thế việc kiểm tra constraint và lỗi ở transaction commit boundary.

### 17.3. Lỗi không thể sửa bằng retry

ORA-01400, ORA-02290, ORA-12899 thường phản ánh dữ liệu đầu vào không hợp lệ. Retry nguyên input mà không sửa dữ liệu sẽ tiếp tục thất bại. Phân loại lỗi để chuyển sang REJECTED hoặc chờ nguồn dữ liệu sửa.

### 17.4. Lỗi có thể tạm thời

Một số lỗi đồng thời hoặc tài nguyên có thể tạm thời. Tuy nhiên, không retry ngay trong handler mà không xem transaction state, lock state, idempotency và khả năng gây lặp side effect. Dùng retry có giới hạn, backoff và transaction boundary rõ ràng.

## 18. Thiết kế quy trình batch có thể vận hành

Một batch bulk DML đáng tin cậy thường có các bước:

1. Tạo batch ID: xác định duy nhất một lần chạy và nguồn dữ liệu.
2. Đọc dữ liệu: fetch theo batch size giới hạn.
3. Chuẩn hóa input: kiểm tra định dạng, null, domain và duplicate nếu có thể.
4. Xây collection: giữ song song source key và source row number.
5. Chạy FORALL SAVE EXCEPTIONS: bulk DML.
6. Chụp thống kê: tổng hàng ảnh hưởng, số lỗi và số iteration không khớp.
7. Lưu error details: batch ID, input key, ERROR_CODE, ERROR_MESSAGE.
8. Cập nhật trạng thái nguồn: chỉ đánh dấu record success khi transaction đã xử lý theo contract.
9. Quyết định transaction: commit partial success hoặc rollback batch theo nghiệp vụ.
10. Retry/reject: retry các lỗi có thể sửa; từ chối lỗi dữ liệu cố định.
11. Đối soát: so sánh input count, success, failure, zero-row và committed count.

### 18.1. Các chỉ số nên ghi

| Chỉ số | Ý nghĩa |
| --- | --- |
| batch_id | Định danh batch |
| input_count | Số input được đọc |
| attempted_count | Số iteration được gửi vào FORALL |
| affected_count | Tổng số hàng DML tác động |
| failed_count | Số iteration có lỗi |
| zero_row_count | Số iteration không tác động hàng nào |
| elapsed_ms | Thời gian xử lý |
| retry_count | Số input được retry |
| final_status | SUCCESS, PARTIAL, FAILED hoặc trạng thái tương đương |

Đối với INSERT một input tương ứng một target row, affected_count có thể bằng attempted_count trừ failed_count. Với UPDATE/DELETE có thể tác động 0 hoặc nhiều hàng, không dùng công thức đó.

### 18.2. Trạng thái batch

| Trạng thái | Điều kiện |
| --- | --- |
| SUCCESS | Không có lỗi và mọi điều kiện nghiệp vụ đạt |
| PARTIAL | Có hàng thành công và có hàng lỗi/không khớp theo chính sách |
| FAILED | Batch bị rollback hoặc không thể tiếp tục |
| RETRY_PENDING | Có input lỗi tạm thời chờ xử lý lại |
| REJECTED | Input lỗi cố định không được retry |

Định nghĩa cụ thể tùy hệ thống. Quan trọng là trạng thái batch phải nhất quán với transaction và error log.

## 19. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| FORALL dừng ở lỗi đầu tiên | Không dùng SAVE EXCEPTIONS | Thêm SAVE EXCEPTIONS nếu cần xử lý tiếp |
| Handler không bắt ORA-24381 | Chưa khai báo exception mapping hoặc bắt sai mã | PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381) |
| ERROR_INDEX trỏ sai input | Nhầm vị trí lỗi trong danh sách với chỉ số collection | Dùng ERROR_INDEX và mapping bounds clause |
| Chỉ thấy tổng số hàng, không thấy từng input | Chỉ đọc SQL%ROWCOUNT | Đọc SQL%BULK_ROWCOUNT(i) và SQL%BULK_EXCEPTIONS |
| SQL%ROWCOUNT đổi sau khi log | Handler chạy INSERT/UPDATE log trước khi chụp | Lưu row count ngay khi vào handler |
| DML 0 hàng không có trong lỗi | Không có hàng khớp WHERE, không phải exception | Kiểm tra SQL%BULK_ROWCOUNT(i) = 0 |
| Batch partial bị báo SUCCESS | Handler nuốt ORA-24381 và không trả trạng thái | Trả trạng thái PARTIAL hoặc re-raise |
| Hàng thành công biến mất sau rollback | Caller rollback transaction | Phân biệt DML affected và committed |
| Log lỗi cũng biến mất | Log cùng transaction bị rollback | Quyết định log cùng transaction hay log độc lập |
| Retry tạo duplicate | Không có idempotency key hoặc không kiểm tra trạng thái đã xử lý | Dùng source key/unique constraint và policy retry |
| FORALL lỗi với collection thưa | Dùng 1..COUNT cho collection không liên tục | Dùng INDICES OF hoặc VALUES OF |
| Error table thiếu thông tin nguồn | Chỉ lưu ERROR_CODE | Lưu batch ID, source key, row number và input reference |
| Lỗi chỉ xuất hiện lúc COMMIT | Deferred constraint hoặc lỗi transaction boundary | Xử lý lỗi commit riêng; SAVE EXCEPTIONS không bắt mọi lỗi |
| Retry liên tục vẫn lỗi | Nguyên nhân là dữ liệu cố định | Phân loại lỗi và chuyển REJECTED |

## 20. Nguyên tắc thực hành tốt

1. **Dùng SAVE EXCEPTIONS khi muốn tiếp tục các iteration còn lại.** Đây là lựa chọn có chủ đích cho partial processing.
2. **Bắt đúng ORA-24381.** Dùng PRAGMA EXCEPTION_INIT và giữ handler WHEN OTHERS cho lỗi khác.
3. **Đọc ERROR_INDEX, không đọc vị trí danh sách lỗi như input index.** Mapping theo bounds clause của FORALL.
4. **Lưu ERROR_CODE và thông báo.** Gọi SQLERRM với mã lỗi âm để tạo message.
5. **Đọc SQL%BULK_ROWCOUNT cho từng iteration.** Phân biệt lỗi với DML thành công nhưng không khớp hàng.
6. **Chụp SQL%ROWCOUNT ngay trong handler.** Đừng để câu INSERT log ghi đè giá trị tổng.
7. **Giữ source key và batch ID.** Chỉ số collection không đủ để truy vết dữ liệu upstream.
8. **Quyết định partial hay all-or-nothing trước khi chạy.** Dùng COMMIT/ROLLBACK/SAVEPOINT theo contract.
9. **Không nuốt ORA-24381.** Caller phải biết batch có lỗi một phần.
10. **Retry có giới hạn và idempotent.** Không retry mù các lỗi constraint cố định.
11. **Fetch theo batch có LIMIT.** Kiểm soát PGA và thời gian transaction.
12. **Phân biệt SAVE EXCEPTIONS với LOG ERRORS.** Chọn theo nguồn dữ liệu, khả năng mapping và loại lỗi.
13. **Kiểm tra lỗi ở commit boundary.** Deferred constraint và lỗi transaction có thể xuất hiện sau FORALL.
14. **Không COMMIT trong mỗi iteration.** Để caller quản lý transaction.
15. **Đối soát số liệu batch.** Input, attempted, affected, failed, zero-row và committed là các con số khác nhau.

## 21. Bài tập tự thực hành

### Bài 1 — Unique violation

Tạo bảng có primary key trên ID và dùng FORALL SAVE EXCEPTIONS để INSERT collection chứa ID bị lặp. In ra:

- Tổng số hàng được INSERT.
- Số iteration lỗi.
- ERROR_INDEX và ERROR_CODE của từng lỗi.
- ID nguồn gây lỗi.

### Bài 2 — Check constraint

Thêm CHECK constraint quantity >= 0. Đưa vào collection cả số lượng âm và dương. Xác định iteration nào lỗi ORA-02290; chứng minh các iteration hợp lệ vẫn được xử lý.

### Bài 3 — UPDATE 0 hàng

Dùng FORALL UPDATE theo danh sách ID có một ID không tồn tại. Đọc SQL%BULK_ROWCOUNT và giải thích vì sao ID đó không xuất hiện trong SQL%BULK_EXCEPTIONS.

### Bài 4 — Collection sparse

Tạo associative array có subscript 10, 20 và 50. Dùng INDICES OF và gây một lỗi DML. Ghi nhận ERROR_INDEX và ánh xạ đúng source record.

### Bài 5 — Error logging

Tạo error table bằng DBMS_ERRLOG.CREATE_ERROR_LOG. So sánh một INSERT ... SELECT dùng LOG ERRORS với FORALL SAVE EXCEPTIONS trên cùng bộ dữ liệu.

### Bài 6 — Transaction policy

Chạy batch có 2 hàng thành công và 1 hàng lỗi. Thử hai kịch bản:

1. COMMIT để giữ hàng thành công và log lỗi.
2. ROLLBACK TO SAVEPOINT để hủy toàn bộ batch.

Giải thích trạng thái bảng đích và error log sau mỗi kịch bản.

### Bài 7 — Retry

Sửa input của các record lỗi, tạo collection mới chỉ chứa phần lỗi và retry. Bảo đảm không insert trùng record đã thành công trong batch đầu.

### Bài 8 — Bulk collect theo lô

Đọc 100.000 record từ staging bằng BULK COLLECT LIMIT. Với mỗi batch, chạy FORALL SAVE EXCEPTIONS, cộng dồn affected count và error count. Đối chiếu tổng input với kết quả cuối.

## 22. Câu hỏi tự kiểm tra

1. FORALL giải quyết chi phí nào so với DML row-by-row?
2. Điều gì xảy ra khi FORALL mặc định gặp lỗi DML?
3. SAVE EXCEPTIONS thay đổi hành vi xử lý iteration như thế nào?
4. Vì sao sau SAVE EXCEPTIONS Oracle phát sinh ORA-24381?
5. Cách khai báo exception cho mã -24381?
6. SQL%BULK_EXCEPTIONS.COUNT biểu thị điều gì?
7. ERROR_INDEX và ERROR_CODE có ý nghĩa gì?
8. Vì sao ERROR_CODE phải đổi dấu khi truyền cho SQLERRM?
9. SQL%BULK_ROWCOUNT(i) và SQL%ROWCOUNT sau FORALL khác nhau ra sao?
10. DML UPDATE không khớp hàng có được ghi vào SQL%BULK_EXCEPTIONS không?
11. Vì sao số iteration khác số hàng bị tác động?
12. Với collection sparse, vì sao không dùng 1..COUNT?
13. INDICES OF và VALUES OF có vai trò gì?
14. Vì sao phải giữ source row number/business key cùng collection?
15. SAVE EXCEPTIONS có tự COMMIT các iteration thành công không?
16. Làm sao rollback toàn bộ batch nhưng giữ các thay đổi trước batch?
17. Vì sao log cùng transaction biến mất khi caller rollback?
18. Khi nào nên dùng autonomous logger?
19. SAVE EXCEPTIONS khác LOG ERRORS ở điểm nào?
20. Vì sao deferred constraint có thể lỗi tại COMMIT thay vì trong FORALL?
21. Những lỗi nào không nên retry nguyên trạng?
22. Cần những trường nào trong error log để hỗ trợ retry và đối soát?

## 23. Mô hình ghi nhớ

```text
FORALL ... SAVE EXCEPTIONS
          |
          v
    Thử mọi iteration
          |
          +-- DML thành công
          |      |
          |      +-- SQL%BULK_ROWCOUNT(i)
          |
          +-- DML thất bại
                 |
                 +-- Lưu ERROR_INDEX
                 +-- Lưu ERROR_CODE
          |
          v
    Sau khi hoàn tất
          |
          +-- Có lỗi -> ORA-24381
          |      |
          |      +-- SQL%BULK_EXCEPTIONS
          |      +-- SQLERRM(-ERROR_CODE)
          |      +-- Ghi log / phân loại / retry
          |
          +-- Không lỗi -> tiếp tục bình thường
          |
          v
    TRANSACTION POLICY
          |
          +-- COMMIT partial success nếu được phép
          +-- ROLLBACK TO SAVEPOINT nếu all-or-nothing
          +-- Caller quyết định transaction cuối cùng
```

**Điểm cần nhớ:** SAVE EXCEPTIONS giúp FORALL tiếp tục qua lỗi DML từng iteration và báo lỗi tổng hợp ORA-24381 sau khi hoàn tất. Dùng SQL%BULK_EXCEPTIONS để tìm input lỗi, SQL%BULK_ROWCOUNT để biết từng iteration tác động bao nhiêu hàng và SQL%ROWCOUNT để tính tổng. Sau đó phải quyết định rõ giữ thành công một phần hay rollback toàn batch; SAVE EXCEPTIONS không tự commit và không thay thế chính sách retry.
