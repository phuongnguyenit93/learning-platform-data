# SQL xử lý theo tập hợp so với vòng lặp và bulk processing

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** PL/SQL nâng cao  
> **Mục tiêu:** Biết lựa chọn giữa SQL set-based, vòng lặp PL/SQL và bulk processing; hiểu chi phí chuyển đổi giữa PL/SQL engine và SQL engine; sử dụng BULK COLLECT để lấy nhiều hàng mỗi lần và FORALL để gửi DML theo lô; xử lý collection dày/thưa, lỗi từng phần, số hàng tác động và transaction boundary; đo hiệu năng và chọn kích thước batch phù hợp.

## 1. Vì sao phải phân biệt xử lý theo tập hợp và xử lý từng hàng?

Một yêu cầu nghiệp vụ có thể được diễn đạt theo hai cách:

- Cập nhật lương tất cả nhân viên phòng 10 thêm 5%.
- Đọc từng nhân viên phòng 10, tính lương mới trong PL/SQL rồi UPDATE từng hàng.

Cả hai cách có thể tạo ra cùng kết quả, nhưng cách thực thi khác nhau. Oracle SQL được thiết kế để xử lý tập hợp hàng trong một statement. Khi viết vòng lặp PL/SQL rồi thực hiện một câu SQL cho từng hàng, chương trình có thể tạo rất nhiều lần chuyển điều khiển giữa PL/SQL engine và SQL engine.

Ví dụ xử lý theo tập hợp:

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 10;
~~~

Ví dụ xử lý từng hàng:

~~~sql
BEGIN
    FOR r IN (
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = 10
    ) LOOP
        UPDATE employees
        SET salary = r.salary * 1.05
        WHERE employee_id = r.employee_id;
    END LOOP;
END;
/
~~~

Câu UPDATE đầu tiên để SQL engine xử lý toàn bộ tập hàng. Vòng lặp thứ hai lấy từng hàng về PL/SQL rồi gửi một UPDATE riêng cho mỗi hàng.

Khi số hàng lớn, khác biệt về số lần gọi SQL có thể đáng kể. Vì vậy, khi một phép biến đổi có thể diễn đạt bằng một câu SQL, nên bắt đầu từ SQL set-based. Chỉ chuyển sang vòng lặp hoặc bulk processing khi nghiệp vụ thực sự cần logic PL/SQL hoặc cần chia dữ liệu thành lô có kiểm soát.

## 2. SQL engine và PL/SQL engine

Oracle Database có các thành phần thực thi SQL và PL/SQL. Khi PL/SQL gọi SQL, quyền điều khiển được chuyển sang SQL engine; khi câu SQL hoàn tất, quyền điều khiển quay lại PL/SQL engine.

Một vòng lặp có DML bên trong có thể lặp lại quá trình này hàng nghìn hoặc hàng triệu lần.

~~~text
PL/SQL engine
    |
    | gọi SQL cho một hàng
    v
SQL engine
    |
    | hoàn tất một DML
    v
PL/SQL engine
    |
    | xử lý hàng tiếp theo
    v
SQL engine
    |
    | hoàn tất DML tiếp theo
    v
...
~~~

Đây thường được gọi là **context switching** giữa PL/SQL và SQL.

### 2.1. Row-by-row processing

Với 100.000 hàng, vòng lặp có thể phát sinh:

- Một lần mở/thiết lập cursor.
- Nhiều lần fetch hàng.
- 100.000 lần thực hiện DML riêng.
- Nhiều lần chuyển điều khiển giữa hai engine.
- Chi phí parse/execute/bind lặp lại tùy cách viết và cơ chế tối ưu.

Không phải mỗi lần chuyển engine đều có cùng chi phí, và Oracle có thể tối ưu một số trường hợp. Tuy nhiên, thiết kế row-by-row thường tạo nhiều công việc lặp lại không cần thiết.

### 2.2. Set-based SQL

Với set-based SQL, một statement mô tả phép biến đổi trên toàn bộ tập hàng:

~~~sql
UPDATE employees
SET bonus = CASE
                WHEN performance_score >= 90 THEN salary * 0.20
                WHEN performance_score >= 80 THEN salary * 0.15
                ELSE salary * 0.05
            END
WHERE department_id = 10;
~~~

SQL engine có thể tối ưu access path, join, filter và DML trên cả tập dữ liệu. Optimizer có thêm thông tin toàn cục về câu lệnh để chọn kế hoạch thực thi.

### 2.3. Bulk processing

Khi không thể đưa toàn bộ logic vào một SQL statement, bulk processing giúp giảm số lần chuyển engine:

1. BULK COLLECT lấy nhiều hàng vào collection trong một lần fetch.
2. PL/SQL xử lý dữ liệu của một batch.
3. FORALL gửi DML cho nhiều phần tử collection trong một lần gọi bulk bind.

~~~text
SQL engine
    |
    | BULK COLLECT: lấy một batch
    v
PL/SQL collection
    |
    | xử lý logic theo batch
    v
FORALL
    |
    | gửi nhiều DML bind
    v
SQL engine
~~~

Bulk processing giảm context switching, nhưng không loại bỏ chi phí SQL, index maintenance, constraint, redo, undo hoặc locking. Nó cũng không tự động COMMIT.

## 3. Thứ tự ưu tiên khi chọn cách xử lý

| Cách xử lý | Cơ chế | Khi nên dùng |
|---|---|---|
| SQL set-based | Một câu SELECT/INSERT/UPDATE/DELETE/MERGE xử lý tập hàng | Quy tắc có thể biểu diễn bằng SQL |
| Cursor FOR LOOP | Fetch và xử lý từng hàng, Oracle tự OPEN/FETCH/CLOSE | Cần logic PL/SQL riêng cho từng hàng, số hàng vừa phải |
| Explicit cursor + vòng lặp | Tự quản lý OPEN/FETCH/CLOSE | Cần kiểm soát cursor lifecycle, attributes hoặc locking |
| BULK COLLECT + FORALL | Fetch và DML theo batch | Cần xử lý PL/SQL theo hàng nhưng dữ liệu lớn |
| BULK COLLECT không FORALL | Fetch nhiều hàng để tính toán trong PL/SQL | Cần tập dữ liệu trong bộ nhớ hoặc chỉ đọc/xử lý ngoài DB |

Quy tắc thực tế:

1. Tìm cách viết một câu SQL set-based trước.
2. Nếu logic bắt buộc phải dùng PL/SQL, xem cursor FOR LOOP có đủ không.
3. Nếu vòng lặp phát sinh nhiều DML hoặc fetch trên tập dữ liệu lớn, đo và cân nhắc BULK COLLECT/FORALL.
4. Nếu dữ liệu quá lớn để giữ trong PGA, chia batch bằng LIMIT.
5. Nếu chia batch qua nhiều transaction, thiết kế restartability và tính idempotent.

## 4. Chuyển vòng lặp thành SQL set-based

Trước khi dùng bulk, thử xác định xem phép xử lý có thể diễn đạt bằng SQL hay không.

### 4.1. UPDATE nhiều hàng

Row-by-row:

~~~sql
BEGIN
    FOR r IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = 10
    ) LOOP
        UPDATE employees
        SET status = 'REVIEWED'
        WHERE employee_id = r.employee_id;
    END LOOP;
END;
/
~~~

Set-based:

~~~sql
UPDATE employees
SET status = 'REVIEWED'
WHERE department_id = 10;
~~~

Câu SQL thứ hai ngắn hơn và thường hiệu quả hơn vì database xử lý cả tập hàng trong một statement.

### 4.2. Phân loại bằng CASE

Nếu mỗi hàng được phân loại theo các điều kiện, không cần vòng lặp để gán giá trị:

~~~sql
UPDATE employees
SET salary_band =
    CASE
        WHEN salary IS NULL THEN 'UNKNOWN'
        WHEN salary >= 15000 THEN 'HIGH'
        WHEN salary >= 8000 THEN 'MEDIUM'
        ELSE 'LOW'
    END;
~~~

CASE expression được tính cho từng hàng trong cùng câu UPDATE.

### 4.3. INSERT ... SELECT

Nếu cần chuyển dữ liệu đã lọc/biến đổi sang bảng đích:

~~~sql
INSERT INTO archived_orders (
    order_id,
    customer_id,
    order_date,
    total_amount
)
SELECT order_id,
       customer_id,
       order_date,
       total_amount
FROM orders
WHERE order_date < DATE '2025-01-01'
  AND status = 'CLOSED';
~~~

Đây là một phép nạp theo tập hợp. Không cần SELECT từng hàng vào PL/SQL rồi INSERT từng hàng nếu không có logic riêng bắt buộc.

### 4.4. MERGE

Nếu cần cập nhật hàng đã tồn tại và thêm hàng chưa tồn tại:

~~~sql
MERGE INTO customer_summary t
USING (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(total_amount) AS total_amount
    FROM orders
    WHERE status = 'CLOSED'
    GROUP BY customer_id
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.order_count = s.order_count,
        t.total_amount = s.total_amount
WHEN NOT MATCHED THEN
    INSERT (customer_id, order_count, total_amount)
    VALUES (s.customer_id, s.order_count, s.total_amount);
~~~

MERGE có thể thay thế một số quy trình “đọc từng khóa rồi quyết định UPDATE hay INSERT”. Cần bảo đảm source không tạo nhiều hàng cùng khớp một target row và xử lý concurrency/unique constraint phù hợp.

### 4.5. Aggregation thay vòng lặp cộng dồn

Không cần đọc từng hàng để cộng tổng trong PL/SQL nếu SQL SUM đáp ứng yêu cầu:

~~~sql
SELECT customer_id,
       SUM(total_amount) AS total_sales,
       COUNT(*) AS order_count
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id;
~~~

SQL aggregation tận dụng cơ chế xử lý tập hợp và trả về đúng tập kết quả cần thiết.

### 4.6. Khi nào không thể thay bằng một câu SQL?

Một vòng lặp có thể hợp lý nếu mỗi hàng cần:

- Gọi API hoặc procedure có side effect riêng.
- Thực hiện nhiều bước phụ thuộc kết quả của bước trước.
- Áp dụng thuật toán phức tạp khó biểu diễn bằng SQL.
- Ghi nhận lỗi và quyết định tiếp tục/dừng theo từng hàng.
- Xử lý theo trạng thái bên ngoài database.

Ngay cả khi phải xử lý từng hàng, có thể vẫn gom phần đọc và ghi thành batch để giảm chi phí chuyển engine.

## 5. Cursor FOR LOOP không phải bulk processing

Cursor FOR LOOP giúp code gọn vì Oracle tự quản lý cursor:

~~~sql
BEGIN
    FOR r IN (
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = 10
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r.employee_id || ': ' || r.salary
        );
    END LOOP;
END;
/
~~~

Nhưng vòng lặp vẫn xử lý từng record trong PL/SQL. Nếu bên trong có một UPDATE cho mỗi record, chương trình vẫn tạo row-by-row DML.

Cursor FOR LOOP phù hợp khi:

- Tập dữ liệu nhỏ hoặc vừa.
- Cần thực hiện logic PL/SQL cho từng hàng.
- Không có DML hàng loạt nặng.
- Code rõ ràng quan trọng hơn tối ưu bulk chưa được chứng minh.

Không nên thay mọi cursor FOR LOOP bằng BULK COLLECT/FORALL theo thói quen. Bulk thêm collection, giới hạn bộ nhớ và logic xử lý lỗi; chỉ dùng khi đo được lợi ích hoặc có yêu cầu throughput.

## 6. BULK COLLECT: lấy nhiều hàng vào collection

BULK COLLECT cho phép SQL engine trả nhiều hàng vào collection PL/SQL trong một lần chuyển dữ liệu.

Có thể dùng với:

- SELECT ... BULK COLLECT INTO.
- FETCH cursor BULK COLLECT INTO.
- DML RETURNING BULK COLLECT INTO trong các trường hợp được hỗ trợ.

### 6.1. Khai báo collection

Ví dụ khai báo nested table type trong PL/SQL:

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    TYPE salary_list_t IS TABLE OF employees.salary%TYPE;

    l_ids id_list_t;
    l_salaries salary_list_t;
BEGIN
    NULL;
END;
/
~~~

Một collection có thể lưu nhiều giá trị cùng kiểu. Khi BULK COLLECT nhiều cột, thường khai báo một collection cho mỗi cột được fetch.

### 6.2. SELECT BULK COLLECT INTO

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    TYPE name_list_t IS TABLE OF employees.employee_name%TYPE;

    l_ids id_list_t;
    l_names name_list_t;
BEGIN
    SELECT employee_id, employee_name
    BULK COLLECT INTO l_ids, l_names
    FROM employees
    WHERE department_id = 10
    ORDER BY employee_id;

    FOR i IN 1 .. l_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(
            l_ids(i) || ': ' || l_names(i)
        );
    END LOOP;
END;
/
~~~

Hai collection nhận cùng số hàng và cùng vị trí tương ứng. Hàng thứ i của L_IDS đi cùng hàng thứ i của L_NAMES.

Nếu SELECT không trả hàng nào, các collection nhận kết quả rỗng; SELECT BULK COLLECT không ném NO_DATA_FOUND chỉ vì không có hàng.

### 6.3. Hạn chế của BULK COLLECT không có LIMIT

SELECT BULK COLLECT INTO lấy toàn bộ tập kết quả vào bộ nhớ PL/SQL. Nếu truy vấn trả hàng triệu record hoặc mỗi record có CLOB/LOB lớn, PGA có thể tăng mạnh và gây lỗi bộ nhớ hoặc làm giảm khả năng mở rộng.

Chỉ dùng không LIMIT khi kích thước tập kết quả được kiểm soát và phù hợp với bộ nhớ. Với tập dữ liệu lớn, dùng explicit cursor cùng FETCH BULK COLLECT LIMIT.

## 7. FETCH BULK COLLECT với LIMIT

LIMIT quy định số hàng tối đa được fetch trong một batch. Thay vì đưa toàn bộ kết quả vào collection, chương trình lấy từng nhóm.

Ví dụ:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = 10
        ORDER BY employee_id;

    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    TYPE salary_list_t IS TABLE OF employees.salary%TYPE;

    l_ids id_list_t;
    l_salaries salary_list_t;
    c_limit CONSTANT PLS_INTEGER := 500;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees
        BULK COLLECT INTO l_ids, l_salaries
        LIMIT c_limit;

        EXIT WHEN l_ids.COUNT = 0;

        FOR i IN 1 .. l_ids.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                l_ids(i) || ': ' || l_salaries(i)
            );
        END LOOP;
    END LOOP;

    CLOSE c_employees;
END;
/
~~~

Mỗi lần FETCH lấy tối đa 500 hàng. Batch cuối có thể có ít hơn 500 hàng; lần FETCH sau đó trả collection rỗng và vòng lặp kết thúc.

### 7.1. Vì sao kiểm tra COUNT = 0?

Với FETCH BULK COLLECT LIMIT, batch cuối có thể chứa một số hàng nhỏ hơn LIMIT dù cursor đã đến cuối tập kết quả. Nếu viết EXIT ngay sau FETCH dựa vào cursor%NOTFOUND, có thể bỏ qua batch cuối trong một số mẫu code do %NOTFOUND báo không còn hàng sau lần fetch đó.

Mẫu an toàn, dễ nhớ là:

~~~sql
FETCH c_employees BULK COLLECT INTO l_ids LIMIT c_limit;
EXIT WHEN l_ids.COUNT = 0;

-- Xử lý toàn bộ batch vừa fetch
~~~

Kiểm tra collection rỗng bảo đảm mọi hàng đã fetch được xử lý trước khi vòng lặp kết thúc.

### 7.2. Xử lý batch trước khi fetch tiếp

Collection sau mỗi bulk fetch chứa batch hiện tại. Hãy xử lý batch trước khi FETCH lần tiếp theo vì dữ liệu collection sẽ được thay bằng kết quả fetch mới.

Nếu cần giữ lại dữ liệu nhiều batch, phải copy/append vào collection khác hoặc lưu vào bảng staging; không giả định collection fetch tự tích lũy mọi batch.

### 7.3. LIMIT không phải COMMIT

LIMIT chỉ giới hạn số hàng mỗi lần FETCH. Nó không tự COMMIT, không giải phóng transaction và không tự nhả row lock.

Nếu mỗi batch thực hiện DML, các thay đổi vẫn thuộc transaction hiện tại cho đến khi COMMIT hoặc ROLLBACK. Quyết định commit theo batch là quyết định transaction riêng, có tác động đến atomicity, locking và khả năng chạy lại.

## 8. FORALL: gửi DML theo lô

FORALL là cấu trúc PL/SQL gửi một DML statement lặp trên các phần tử collection bằng cơ chế bulk bind. Nó giảm số lần chuyển giữa PL/SQL engine và SQL engine so với một DML statement trong mỗi vòng LOOP.

Ví dụ:

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    l_ids id_list_t;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_ids
    FROM employees
    WHERE department_id = 10;

    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employees
        SET status = 'REVIEWED'
        WHERE employee_id = l_ids(i);
END;
/
~~~

FORALL không phải vòng lặp PL/SQL thông thường. PL/SQL gửi các giá trị bind từ collection cho SQL engine theo cơ chế bulk. DML vẫn được thực hiện cho từng giá trị bind, nhưng giảm overhead chuyển engine.

### 8.1. Điều kiện collection dày

Cú pháp:

~~~sql
FORALL i IN 1 .. l_ids.COUNT
    DELETE FROM staging_orders
    WHERE order_id = l_ids(i);
~~~

Mẫu này giả định collection có index liên tục từ 1 đến COUNT. Nếu collection có phần tử bị DELETE hoặc index bắt đầu từ giá trị khác, khoảng 1..COUNT có thể truy cập index không tồn tại.

Đối với collection dày được BULK COLLECT nạp mới, index thường là 1..COUNT nên mẫu trên phù hợp.

### 8.2. FORALL chỉ có một DML statement

Trong một FORALL, phần thân là một DML statement được áp dụng theo collection index. Không đặt nhiều câu lệnh UPDATE/INSERT/DELETE khác nhau trong cùng FORALL và không gọi procedure PL/SQL tùy ý bên trong như một vòng LOOP.

Nếu cần nhiều thao tác DML, có thể dùng các FORALL riêng hoặc thiết kế lại thành một SQL statement set-based. Mỗi FORALL có thể tạo một nhóm công việc bulk khác nhau.

### 8.3. FORALL với INSERT

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    TYPE name_list_t IS TABLE OF employees.employee_name%TYPE;

    l_ids id_list_t;
    l_names name_list_t;
BEGIN
    SELECT employee_id, employee_name
    BULK COLLECT INTO l_ids, l_names
    FROM employees
    WHERE department_id = 10;

    FORALL i IN 1 .. l_ids.COUNT
        INSERT INTO employee_snapshot (
            employee_id,
            employee_name,
            captured_at
        )
        VALUES (
            l_ids(i),
            l_names(i),
            SYSTIMESTAMP
        );
END;
/
~~~

### 8.4. FORALL với DELETE

~~~sql
FORALL i IN 1 .. l_ids.COUNT
    DELETE FROM staging_orders
    WHERE order_id = l_ids(i);
~~~

Nếu mỗi ID không tồn tại, DML iteration đó có thể ảnh hưởng 0 hàng; đây không nhất thiết là lỗi. Dùng SQL%BULK_ROWCOUNT để xem số hàng bị tác động ở từng iteration.

## 9. Collection thưa: INDICES OF và VALUES OF

Một collection có thể trở nên thưa sau khi xóa phần tử hoặc chỉ lưu các index được chọn.

Ví dụ:

~~~sql
l_ids(1) := 10;
l_ids(3) := 30;
l_ids(7) := 70;
~~~

Collection có COUNT = 3 nhưng các index là 1, 3 và 7. FORALL 1..COUNT sẽ cố truy cập index 2 và 3 theo khoảng 1..3, không phản ánh tập index thực có.

### 9.1. INDICES OF

INDICES OF yêu cầu FORALL lặp trên các index đang tồn tại trong collection:

~~~sql
FORALL i IN INDICES OF l_ids
    DELETE FROM staging_orders
    WHERE order_id = l_ids(i);
~~~

Có thể giới hạn theo khoảng index với cú pháp phù hợp:

~~~sql
FORALL i IN INDICES OF l_ids BETWEEN 1 AND 100
    DELETE FROM staging_orders
    WHERE order_id = l_ids(i);
~~~

Dùng khi collection nguồn thưa và muốn áp dụng DML cho các phần tử hiện có.

### 9.2. VALUES OF

VALUES OF dùng một collection chỉ mục để xác định các index cần xử lý trong collection dữ liệu:

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE index_list_t IS TABLE OF PLS_INTEGER INDEX BY PLS_INTEGER;

    l_ids id_list_t;
    l_selected_indices index_list_t;
BEGIN
    l_ids(10) := 1001;
    l_ids(20) := 1002;
    l_ids(30) := 1003;

    l_selected_indices(1) := 10;
    l_selected_indices(2) := 30;

    FORALL i IN VALUES OF l_selected_indices
        DELETE FROM staging_orders
        WHERE order_id = l_ids(i);
END;
/
~~~

Ở đây chỉ index 10 và 30 của L_IDS được dùng. L_IDS(20) bị bỏ qua.

Collection dùng với VALUES OF phải có kiểu/index phù hợp với quy tắc FORALL. Kiểm tra index tồn tại trong collection dữ liệu trước khi tạo danh sách index.

## 10. Xử lý lỗi trong FORALL với SAVE EXCEPTIONS

Mặc định, nếu một iteration DML trong FORALL thất bại và exception không được xử lý, FORALL dừng tại lỗi đầu tiên và exception được truyền lên. Khi cần tiếp tục các iteration còn lại và thu thập lỗi, dùng SAVE EXCEPTIONS.

Ví dụ:

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF NUMBER;
    l_ids id_list_t := id_list_t(10, 20, -1, 40);

    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
        INSERT INTO target_ids(id)
        VALUES (l_ids(i));

    DBMS_OUTPUT.PUT_LINE('All rows inserted');

EXCEPTION
    WHEN e_bulk_errors THEN
        DBMS_OUTPUT.PUT_LINE(
            'Number of failed iterations: ' ||
            SQL%BULK_EXCEPTIONS.COUNT
        );

        FOR j IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Iteration=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_INDEX ||
                ', Error=' ||
                SQLERRM(-SQL%BULK_EXCEPTIONS(j).ERROR_CODE)
            );
        END LOOP;
END;
/
~~~

Ví dụ cần có constraint phù hợp trên TARGET_IDS để tạo lỗi có thể quan sát; nếu mọi giá trị đều hợp lệ, exception handler không chạy.

### 10.1. ORA-24381

Khi SAVE EXCEPTIONS gặp một hoặc nhiều iteration lỗi, Oracle tiếp tục thực hiện các iteration còn lại rồi báo ORA-24381 (error(s) in array DML).

Có thể ánh xạ lỗi bằng:

~~~sql
PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
~~~

Trong exception handler:

- SQL%BULK_EXCEPTIONS.COUNT là số iteration lỗi.
- ERROR_INDEX cho biết iteration/index liên quan.
- ERROR_CODE là mã lỗi Oracle không có dấu âm trong thuộc tính.
- SQLERRM(-ERROR_CODE) lấy nội dung thông báo lỗi.

### 10.2. Thành công một phần và transaction

Với SAVE EXCEPTIONS, các iteration thành công vẫn là thay đổi pending trong transaction; các iteration lỗi được báo riêng. Chúng không tự COMMIT.

Caller cần quyết định:

- Chấp nhận các hàng thành công và ghi nhận lỗi để retry.
- ROLLBACK toàn bộ transaction nếu batch phải nguyên tử.
- Chuyển hàng lỗi sang bảng reject/quarantine.
- Đánh dấu trạng thái để lần chạy sau không xử lý trùng.

Không bắt ORA-24381 rồi bỏ qua. Nếu không ghi lại lỗi và trạng thái xử lý, batch có thể mất dữ liệu hoặc tạo kết quả không đầy đủ mà caller tưởng là thành công.

### 10.3. Không dùng SAVE EXCEPTIONS thay validation

Nếu biết trước điều kiện dữ liệu không hợp lệ, hãy validate trước khi FORALL hoặc dùng constraint. SAVE EXCEPTIONS hữu ích khi cần tiếp tục một batch dù một số hàng gặp lỗi không dự đoán được, không phải lý do để bỏ qua kiểm tra dữ liệu.

## 11. SQL%BULK_ROWCOUNT và SQL%BULK_EXCEPTIONS

FORALL cung cấp các thuộc tính để kiểm tra kết quả DML bulk.

### 11.1. SQL%BULK_ROWCOUNT

SQL%BULK_ROWCOUNT(i) cho biết số hàng bị tác động bởi iteration thứ i của FORALL.

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF NUMBER;
    l_ids id_list_t := id_list_t(10, 20, 30);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employees
        SET status = 'REVIEWED'
        WHERE employee_id = l_ids(i);

    FOR i IN 1 .. l_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Input ' || l_ids(i) ||
            ', affected=' || SQL%BULK_ROWCOUNT(i)
        );
    END LOOP;

    DBMS_OUTPUT.PUT_LINE('Total affected=' || SQL%ROWCOUNT);
END;
/
~~~

SQL%ROWCOUNT sau FORALL là tổng số hàng bị tác động bởi DML bulk. SQL%BULK_ROWCOUNT cho phép xem kết quả từng iteration.

Đọc các thuộc tính ngay sau FORALL tương ứng, trước khi chạy DML khác có thể thay đổi implicit SQL cursor attributes.

### 11.2. SQL%BULK_EXCEPTIONS

SQL%BULK_EXCEPTIONS chứa thông tin iteration thất bại khi FORALL dùng SAVE EXCEPTIONS. Chỉ đọc trong exception handler tương ứng; ghi nhận lỗi trước khi thực hiện các công việc khác làm thay đổi ngữ cảnh cần chẩn đoán.

### 11.3. Ánh xạ ERROR_INDEX với dữ liệu nguồn

Nếu FORALL dùng 1 .. l_ids.COUNT, ERROR_INDEX thường ánh xạ trực tiếp đến vị trí collection. Nếu dùng INDICES OF hoặc VALUES OF, cần hiểu index/iteration semantics để truy ngược đúng hàng nguồn.

Khi ghi log lỗi, nên lưu cả khóa nghiệp vụ của hàng cùng mã lỗi, không chỉ số iteration. Điều này giúp retry và điều tra sau khi collection đã hết phạm vi.

## 12. RETURNING BULK COLLECT INTO

Một số DML có thể trả các giá trị của hàng bị tác động. Khi làm việc với nhiều hàng, RETURNING BULK COLLECT INTO đưa các giá trị đó vào collection.

Ví dụ với DELETE:

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    l_deleted_ids id_list_t;
BEGIN
    DELETE FROM employees
    WHERE department_id = 99
    RETURNING employee_id BULK COLLECT INTO l_deleted_ids;

    DBMS_OUTPUT.PUT_LINE(
        'Deleted rows: ' || l_deleted_ids.COUNT
    );
END;
/
~~~

Có thể kết hợp với FORALL trong các trường hợp Oracle hỗ trợ:

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    l_ids id_list_t := id_list_t(100, 200, 300);
    l_deleted_ids id_list_t;
BEGIN
    FORALL i IN 1 .. l_ids.COUNT
        DELETE FROM employees
        WHERE employee_id = l_ids(i)
        RETURNING employee_id BULK COLLECT INTO l_deleted_ids;

    DBMS_OUTPUT.PUT_LINE(
        'Returned IDs: ' || l_deleted_ids.COUNT
    );
END;
/
~~~

Khi nhiều iteration cùng trả kết quả, collection RETURNING chứa các giá trị trả về theo cơ chế bulk; không giả định chỉ số phần tử trả về luôn bằng index của collection input. Nếu cần ánh xạ từng hàng, thiết kế khóa và cách đối soát rõ ràng.

## 13. Mẫu xử lý end-to-end: BULK COLLECT + FORALL

Giả sử cần lấy các order đang READY, tính phí theo customer type trong PL/SQL và cập nhật phí cho nhiều hàng.

Ví dụ đơn giản:

~~~sql
DECLARE
    CURSOR c_orders IS
        SELECT order_id, shipping_fee
        FROM orders
        WHERE status = 'READY'
        ORDER BY order_id;

    TYPE id_list_t IS TABLE OF orders.order_id%TYPE;
    TYPE fee_list_t IS TABLE OF orders.shipping_fee%TYPE;

    l_ids id_list_t;
    l_fees fee_list_t;
    c_limit CONSTANT PLS_INTEGER := 500;
BEGIN
    OPEN c_orders;

    LOOP
        FETCH c_orders
        BULK COLLECT INTO l_ids, l_fees
        LIMIT c_limit;

        EXIT WHEN l_ids.COUNT = 0;

        FOR i IN 1 .. l_ids.COUNT LOOP
            -- Ví dụ minh họa quy tắc tính trong PL/SQL.
            -- Nếu biểu thức đơn giản, có thể đưa thẳng vào UPDATE set-based.
            l_fees(i) := CASE
                WHEN l_fees(i) IS NULL THEN 0
                ELSE l_fees(i)
            END;
        END LOOP;

        FORALL i IN 1 .. l_ids.COUNT
            UPDATE orders
            SET shipping_fee = l_fees(i)
            WHERE order_id = l_ids(i);
    END LOOP;

    CLOSE c_orders;
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        IF c_orders%ISOPEN THEN
            CLOSE c_orders;
        END IF;
        ROLLBACK;
        RAISE;
END;
/
~~~

Đoạn minh họa giả định SELECT list, collection type và cột SHIPPING_FEE tồn tại. Nó chỉ cho thấy pipeline đọc batch, xử lý collection và bulk DML. Nếu quy tắc chỉ là NVL(SHIPPING_FEE, 0), câu UPDATE set-based đơn giản hơn và nên được ưu tiên.

### 13.1. Dùng collection cho dữ liệu đầu vào

Không phải lúc nào cũng cần cursor. Nếu dữ liệu đầu vào đã nằm trong collection từ API hoặc bước xử lý trước, có thể dùng FORALL trực tiếp.

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF NUMBER;
    l_ids id_list_t := id_list_t(10, 20, 30, 40);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT
        UPDATE staging_orders
        SET status = 'PROCESSED'
        WHERE order_id = l_ids(i);
END;
/
~~~

### 13.2. Đọc và ghi theo từng batch

Khi tập dữ liệu lớn:

1. Mở cursor.
2. FETCH BULK COLLECT LIMIT N.
3. Kiểm tra collection rỗng.
4. Validate/transform batch.
5. FORALL DML.
6. Ghi nhận số hàng/lỗi của batch.
7. Fetch batch tiếp theo.
8. Đóng cursor.
9. COMMIT/ROLLBACK theo transaction policy.

LIMIT kiểm soát lượng dữ liệu trong bộ nhớ. Commit boundary phải được thiết kế riêng.

## 14. Chọn batch size

Batch size là số hàng tối đa fetch trong mỗi lần BULK COLLECT LIMIT. Không có một giá trị tối ưu cho mọi bảng và workload.

Batch quá nhỏ:

- Tăng số lần FETCH và FORALL.
- Tăng số lần chuyển engine.
- Tăng overhead điều phối.

Batch quá lớn:

- Dùng nhiều PGA.
- Giữ nhiều dữ liệu trong collection.
- Có thể tăng thời gian xử lý một batch và độ trễ phản hồi.
- Có thể làm tăng lock duration nếu DML/transaction kéo dài.
- Làm việc phục hồi hoặc ghi nhận lỗi khó hơn nếu transaction policy không rõ.

Một số giá trị thử ban đầu có thể là 100, 500, 1.000 hoặc 5.000 hàng, nhưng cần đo trên dữ liệu thật và kích thước row thực tế.

### 14.1. Những yếu tố ảnh hưởng

- Số cột và datatype được fetch.
- Có LOB hoặc payload lớn hay không.
- PGA và concurrency.
- Thời gian xử lý PL/SQL mỗi hàng.
- DML có index, trigger, foreign key hay constraint nặng không.
- Redo/undo và I/O.
- Số hàng thực tế trong mỗi batch.
- Mức độ tranh chấp lock.

Không tăng batch size chỉ vì số lần FETCH ít hơn. Mục tiêu là throughput ổn định với bộ nhớ và transaction phù hợp.

## 15. LIMIT và transaction boundary

Một batch không tự động là một transaction. Có hai thiết kế thường gặp:

### 15.1. Một transaction cho toàn bộ job

- Fetch và xử lý nhiều batch.
- Không COMMIT giữa vòng lặp.
- Nếu lỗi không xử lý, ROLLBACK toàn bộ transaction.
- Khi thành công, COMMIT một lần.

Ưu điểm là tính nguyên tử cho toàn job. Nhược điểm là transaction có thể dài, giữ lock lâu và tạo nhiều undo/redo trước commit.

### 15.2. Commit theo batch

- Xử lý một batch.
- Ghi trạng thái batch/checkpoint.
- COMMIT.
- Chuyển sang batch kế tiếp.

Ưu điểm là transaction ngắn hơn và có thể tiếp tục từ checkpoint. Nhược điểm là job không còn atomic toàn bộ; nếu batch thứ 5 lỗi, các batch trước có thể đã commit.

Nếu commit theo batch, cần:

- Khóa/phân chia phạm vi batch rõ ràng.
- Có trạng thái xử lý và checkpoint bền vững.
- Dùng khóa duy nhất hoặc idempotency để tránh xử lý trùng.
- Có quy trình retry và dead-letter/reject cho hàng lỗi.
- Ghi log batch trong cùng transaction với thay đổi batch đó.
- Tránh đọc lại hàng đã commit mà không có cơ chế loại trừ.

### 15.3. Không COMMIT từng hàng

COMMIT trong mỗi iteration thường tạo overhead lớn và làm logic phục hồi khó hơn. Nếu muốn batch transaction, commit sau khi hoàn tất batch và ghi checkpoint, không commit từng hàng một.

### 15.4. Cursor và commit giữa các batch

Nếu cursor đang mở và truy vấn phụ thuộc consistent read lâu, commit giữa vòng fetch có thể làm thay đổi locking và khả năng fetch; với cursor FOR UPDATE, COMMIT giải phóng row locks và có thể khiến fetch tiếp theo lỗi ORA-01002.

Không dùng một cursor FOR UPDATE mở xuyên nhiều commit. Thiết kế claim/lease hoặc truy vấn batch mới sau mỗi commit nếu cần xử lý queue theo lô.

## 16. Dynamic SQL với FORALL

Khi câu DML phải được xây dựng lúc runtime, FORALL có thể kết hợp EXECUTE IMMEDIATE trong những trường hợp được hỗ trợ:

~~~sql
FORALL i IN 1 .. l_ids.COUNT
    EXECUTE IMMEDIATE
        'UPDATE staging_orders SET status = :1 WHERE order_id = :2'
        USING 'PROCESSED', l_ids(i);
~~~

Bind variable dùng cho giá trị dữ liệu. Tên bảng/cột không thể truyền qua bind; nếu identifier phải động, cần whitelist hoặc xác thực bằng DBMS_ASSERT phù hợp.

Không chuyển sang dynamic SQL nếu statement có thể viết tĩnh. Dynamic SQL làm tăng độ phức tạp, rủi ro SQL injection và khó kiểm tra dependency.

## 17. Giới hạn và lưu ý của bulk SQL

Bulk SQL có một số giới hạn và khác biệt theo Oracle release:

- BULK COLLECT/FORALL làm việc với collection PL/SQL có kiểu/index phù hợp.
- FORALL áp dụng một DML statement trên các phần tử collection; không phải vòng lặp để gọi procedure tùy ý.
- Một số cấu trúc DML, trigger, remote object hoặc parallel DML có giới hạn riêng.
- Bulk SQL không tự loại bỏ constraint, trigger, index maintenance, redo, undo hoặc row lock.
- Các collection lớn có thể tiêu thụ PGA đáng kể.
- Dynamic SQL trong FORALL có quy tắc bind riêng.
- RETURNING BULK COLLECT và collection indexing cần được kiểm tra trên release thực tế.

Oracle có các hạn chế cụ thể với bulk SQL trên remote tables và parallel DML. Trước khi thiết kế batch phân tán hoặc kỳ vọng parallel execution, đối chiếu PL/SQL Language Reference đúng phiên bản.

## 18. Đo hiệu năng thay vì đoán

So sánh ít nhất ba cách trên cùng dữ liệu:

1. Một câu SQL set-based.
2. Cursor FOR LOOP với DML từng hàng.
3. BULK COLLECT + FORALL.

Có thể dùng DBMS_UTILITY.GET_TIME để đo thời gian ở mức đơn giản:

~~~sql
DECLARE
    l_start PLS_INTEGER;
    l_elapsed_cs PLS_INTEGER;
BEGIN
    l_start := DBMS_UTILITY.GET_TIME;

    UPDATE employees
    SET status = 'REVIEWED'
    WHERE department_id = 10;

    l_elapsed_cs := DBMS_UTILITY.GET_TIME - l_start;

    DBMS_OUTPUT.PUT_LINE(
        'Elapsed centiseconds = ' || l_elapsed_cs
    );

    ROLLBACK;
END;
/
~~~

GET_TIME trả thời gian theo centisecond trong cách sử dụng này; dùng chênh lệch giữa hai lần gọi. Benchmark phải dùng cùng dữ liệu, cùng trạng thái cache, cùng transaction và cùng điều kiện index/statistics càng nhiều càng tốt.

### 18.1. Các chỉ số nên quan sát

- Elapsed time.
- CPU time.
- Logical reads/buffer gets.
- Physical reads.
- Số SQL execution.
- Số lần fetch.
- Redo/undo generation.
- PGA memory.
- Row lock wait và blocking.
- Số hàng thành công/thất bại.
- Thời gian commit.

### 18.2. Không chỉ đo một lần

Kết quả có thể thay đổi theo buffer cache, concurrency, statistics, bind values và tải hệ thống. Chạy nhiều lần có kiểm soát, so sánh median hoặc phân bố kết quả, không lấy một lần nhanh nhất làm kết luận.

Dùng SQL Trace/TKPROF, execution plan, runtime statistics hoặc SQL Monitor khi phù hợp và được cấp quyền. Đừng bật tracing diện rộng trên production mà chưa đánh giá dung lượng trace và overhead.

## 19. Bài thực hành

Thực hiện trong schema lab, dùng bảng riêng để có thể rollback hoặc drop an toàn.

### Bài 1 — Set-based UPDATE

Tạo bảng LAB_EMPLOYEES có nhiều hàng. Viết một UPDATE tăng lương 5% cho phòng ban 10. Ghi nhận SQL%ROWCOUNT.

### Bài 2 — Row-by-row UPDATE

Viết lại bài 1 bằng cursor FOR LOOP và UPDATE từng hàng. So sánh code và số lần DML.

### Bài 3 — BULK COLLECT không LIMIT

Fetch tất cả employee_id vào collection rồi in COUNT. Thử với số hàng tăng dần và quan sát bộ nhớ.

### Bài 4 — BULK COLLECT LIMIT

Dùng cursor và LIMIT 100, 500, 1.000. In số hàng từng batch và tổng số hàng đã xử lý. Kiểm tra batch cuối có ít hơn LIMIT.

### Bài 5 — Kiểm tra batch cuối

Thử FETCH BULK COLLECT LIMIT với tổng số hàng không chia hết cho LIMIT. Dùng EXIT WHEN collection.COUNT = 0; so sánh với cách EXIT ngay khi cursor%NOTFOUND.

### Bài 6 — FORALL UPDATE

BULK COLLECT ID, rồi FORALL UPDATE status. So sánh elapsed time với cursor loop.

### Bài 7 — FORALL INSERT

Lấy dữ liệu nguồn vào hai collection rồi FORALL INSERT vào bảng snapshot. Đối chiếu số hàng.

### Bài 8 — Collection thưa

Nạp các index 1, 3, 7 vào associative array. Thử FORALL 1..COUNT và giải thích lỗi. Sửa bằng INDICES OF.

### Bài 9 — VALUES OF

Tạo collection ID và collection chứa các index được chọn. Dùng VALUES OF để chỉ xử lý một tập con.

### Bài 10 — SAVE EXCEPTIONS

Tạo bảng đích có UNIQUE constraint. Cố ý gửi một giá trị trùng qua FORALL SAVE EXCEPTIONS. In ERROR_INDEX, ERROR_CODE và SQLERRM.

### Bài 11 — SQL%BULK_ROWCOUNT

Dùng FORALL UPDATE các ID tồn tại và không tồn tại. In số hàng tác động từng iteration và tổng SQL%ROWCOUNT.

### Bài 12 — Transaction theo batch

Chia dữ liệu thành batch 500 hàng. Thử một transaction cho toàn job và commit sau từng batch. So sánh khả năng retry, trạng thái checkpoint và kết quả khi cố ý gây lỗi giữa job.

### Bài 13 — So sánh ba phương pháp

Dùng cùng một phép cập nhật và cùng số lượng hàng cho set-based SQL, cursor FOR LOOP và BULK COLLECT + FORALL. Ghi elapsed time, buffer gets và số DML.

### Bài 14 — Lựa chọn kiến trúc

Với mỗi tình huống sau, giải thích nên dùng SQL set-based, cursor loop hay bulk:

- Cập nhật cùng một cột theo cùng biểu thức cho một triệu hàng.
- Gọi một procedure PL/SQL phức tạp cho mỗi khách hàng.
- Nạp dữ liệu staging sang bảng đích với validate từng batch.
- Tính tổng doanh thu theo customer.
- Ghi nhận riêng từng hàng lỗi nhưng vẫn tiếp tục xử lý các hàng hợp lệ.

## 20. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng loop cho phép biến đổi có thể viết bằng một UPDATE | Nhiều context switch và DML lặp | Viết set-based SQL |
| Nghĩ cursor FOR LOOP là bulk | Vẫn xử lý từng hàng | Dùng BULK COLLECT/FORALL nếu cần batch |
| BULK COLLECT toàn bộ tập dữ liệu lớn | Tăng PGA, có thể hết bộ nhớ | FETCH LIMIT |
| EXIT ngay theo %NOTFOUND sau bulk fetch | Có thể bỏ qua batch cuối chưa được xử lý | Kiểm tra collection.COUNT = 0 |
| Dùng FORALL 1..COUNT cho collection thưa | Index không tồn tại | INDICES OF hoặc VALUES OF |
| Nghĩ FORALL gọi procedure cho từng phần tử | Sai mô hình và cú pháp | Dùng FORALL cho DML; procedure loop riêng nếu cần |
| Bỏ qua SAVE EXCEPTIONS nhưng mong xử lý các hàng sau lỗi | FORALL dừng tại lỗi đầu tiên | SAVE EXCEPTIONS và xử lý ORA-24381 |
| Bắt ORA-24381 rồi bỏ qua | Mất thông tin hàng lỗi | Ghi khóa nghiệp vụ và mã lỗi |
| Nghĩ BULK COLLECT LIMIT tự COMMIT | Transaction vẫn mở | Thiết kế commit boundary riêng |
| COMMIT từng hàng | Tăng overhead, mất atomicity | Commit theo transaction/batch có checkpoint |
| Commit trong cursor FOR UPDATE | Nhả lock và có thể lỗi fetch | Không commit khi cursor FOR UPDATE còn cần fetch |
| Dùng batch quá lớn | PGA và thời gian xử lý batch tăng | Đo và chọn LIMIT |
| Dùng batch quá nhỏ | Tăng số lần fetch/DML | Đo nhiều kích thước batch |
| Dùng FORALL cho một phép cập nhật đồng nhất | Phức tạp hơn SQL set-based | Một câu UPDATE nếu có thể |
| Đo benchmark trong điều kiện khác nhau | Kết luận sai | Kiểm soát dữ liệu, cache, statistics và concurrency |

## 21. Checklist chọn và triển khai bulk processing

- [ ] Kiểm tra có thể dùng một câu SQL set-based hay không.
- [ ] Dùng CASE, JOIN, GROUP BY, INSERT SELECT hoặc MERGE khi phù hợp.
- [ ] Chỉ dùng vòng lặp khi logic PL/SQL thực sự cần thiết.
- [ ] Phân biệt cursor FOR LOOP với bulk processing.
- [ ] Dùng BULK COLLECT để fetch nhiều hàng mỗi lần.
- [ ] Dùng LIMIT cho tập dữ liệu lớn.
- [ ] Xử lý batch cuối bằng kiểm tra collection rỗng.
- [ ] Chọn collection type và index phù hợp.
- [ ] Dùng FORALL cho DML trên collection.
- [ ] Dùng INDICES OF/VALUES OF cho collection thưa.
- [ ] Dùng SAVE EXCEPTIONS khi cần tiếp tục iteration và thu thập lỗi.
- [ ] Ghi nhận SQL%BULK_EXCEPTIONS và SQL%BULK_ROWCOUNT ngay sau FORALL.
- [ ] Xác định rõ hàng lỗi được retry, reject hay làm rollback toàn batch.
- [ ] Phân biệt batch size với transaction boundary.
- [ ] Có checkpoint/idempotency nếu commit từng batch.
- [ ] Không commit trong vòng lặp cursor FOR UPDATE.
- [ ] Đo elapsed time, CPU, buffer gets, PGA, redo và lock.
- [ ] Thử trên dữ liệu đại diện trước khi triển khai production.

## 22. Ghi nhớ cốt lõi

- SQL set-based là lựa chọn đầu tiên khi một phép biến đổi có thể diễn đạt bằng SELECT, INSERT, UPDATE, DELETE hoặc MERGE.
- Row-by-row PL/SQL thường tạo nhiều lần chuyển giữa PL/SQL engine và SQL engine.
- Cursor FOR LOOP tự quản lý OPEN/FETCH/CLOSE nhưng vẫn xử lý từng hàng; nó không tự trở thành bulk processing.
- BULK COLLECT lấy nhiều hàng vào collection trong một lần chuyển dữ liệu.
- FETCH BULK COLLECT LIMIT giúp giới hạn PGA và xử lý tập dữ liệu lớn theo batch.
- Với bulk fetch, kiểm tra collection.COUNT = 0 để kết thúc sau khi đã xử lý mọi batch, kể cả batch cuối nhỏ hơn LIMIT.
- FORALL dùng collection bind để gửi một DML statement cho nhiều phần tử và giảm context switching.
- FORALL 1..COUNT giả định collection dày; dùng INDICES OF hoặc VALUES OF khi collection thưa.
- SAVE EXCEPTIONS cho phép tiếp tục các iteration còn lại và báo lỗi bằng ORA-24381/SQL%BULK_EXCEPTIONS.
- SQL%BULK_ROWCOUNT(i) cho biết số hàng bị tác động ở từng iteration; SQL%ROWCOUNT cho tổng DML.
- Bulk processing không tự COMMIT và không loại bỏ redo, undo, index maintenance, trigger hay row locks.
- LIMIT là kích thước fetch batch, không phải transaction boundary.
- Commit theo batch đòi hỏi checkpoint, retry, idempotency và quy tắc phục hồi rõ ràng.
- Chọn batch size bằng đo lường trên dữ liệu đại diện; không có một con số tối ưu cho mọi workload.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database PL/SQL Language Reference — Bulk SQL and Bulk Binding](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/bulk-sql-and-bulk-binding.html) — BULK COLLECT, FORALL, LIMIT, SAVE EXCEPTIONS và collection indexing.
- [Oracle Database PL/SQL Language Reference — Cursor Variables and Explicit Cursors](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/cursors-overview.html) — Cursor lifecycle, FETCH và cursor attributes.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — Set-based SELECT, INSERT, UPDATE, DELETE, MERGE và RETURNING.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — SQL execution plans, runtime statistics và đo hiệu năng.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — DBMS_UTILITY, DBMS_APPLICATION_INFO và công cụ hỗ trợ quan sát.

Chi tiết bulk SQL, collection indexing, dynamic SQL và parallel/remote restrictions phụ thuộc Oracle release. Hãy đối chiếu tài liệu đúng phiên bản, đo với dữ liệu có kích thước đại diện và kiểm thử cả batch cuối, collection thưa, lỗi một phần và rollback trước khi triển khai.

