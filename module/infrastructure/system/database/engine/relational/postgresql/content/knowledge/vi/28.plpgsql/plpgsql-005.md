# LOOP, WHILE, FOR, FOREACH và điều khiển vòng lặp trong PL/pgSQL

Trong PostgreSQL, **PL/pgSQL** là ngôn ngữ thủ tục giúp viết function, procedure và một số khối mã có biến, điều kiện, nhánh xử lý, vòng lặp, ngoại lệ và SQL. Khi thao tác với tập dữ liệu, PostgreSQL đặc biệt mạnh ở **SQL xử lý theo tập (set-based)**; tuy nhiên, có những công việc cần lặp với trạng thái, kiểm tra điều kiện dừng, đi qua phần tử mảng hoặc xử lý từng hàng một cách có chủ đích.

Ví dụ: một batch job cần xử lý tối đa 10 tác vụ đang chờ, đếm số lần thử và dừng nếu vượt ngưỡng. Một function khác cần duyệt những giá trị trong SQL array để tính kết quả hoặc xây thông báo. Những bài toán này có thể dùng các cấu trúc:

- `LOOP ... END LOOP`: vòng lặp tổng quát, điều kiện dừng do ta viết bằng `EXIT`.
- `WHILE condition LOOP ... END LOOP`: kiểm tra điều kiện **trước mỗi lượt**.
- `FOR integer_variable IN lower..upper LOOP`: lặp trên dải số nguyên, có `REVERSE` và `BY`.
- `FOR record_variable IN query LOOP`: duyệt những hàng của một truy vấn SQL.
- `FOR record_variable IN EXECUTE dynamic_query USING ... LOOP`: duyệt kết quả SQL động.
- `FOREACH variable IN ARRAY expression LOOP`: duyệt những phần tử của **SQL array**, hỗ trợ `SLICE`.
- `EXIT`, `CONTINUE`, nhãn vòng lặp và các lệnh `RETURN`: kiểm soát luồng xử lý.

Bài **“LOOP, WHILE, FOR, FOREACH và điều khiển vòng lặp”**, thuộc chương **PL/pgSQL** của module **Database Engine Relational PostgreSQL**, hướng dẫn từ cú pháp đến cách áp dụng đúng trong function/procedure, tránh vòng lặp vô hạn, xử lý lỗi, kiểm soát transaction và lựa chọn SQL set-based khi tốt hơn.

> **An toàn thực hành:** tất cả ví dụ tạo hoặc cập nhật bảng dùng một database lab riêng. Đừng chạy procedure sửa dữ liệu, `DO` block chứa DML, hoặc vòng lặp sinh tải lớn trên production khi chưa kiểm soát phạm vi và transaction.

---

## 1. Vòng lặp PL/pgSQL khác SQL SELECT như thế nào?

SQL diễn đạt **tập dữ liệu cần xử lý**:

~~~sql
SELECT job_id
FROM pl_loop_lab.jobs
WHERE status = 'pending';
~~~

PL/pgSQL diễn đạt thêm **trình tự điều khiển**:

~~~text
Khởi tạo biến
     |
     v
Kiểm tra điều kiện
     |
     +-- sai --> kết thúc
     |
     v
Thực thi thân vòng lặp
     |
     +--> cập nhật trạng thái / ghi log
     |
     +--> CONTINUE, EXIT hoặc đi vòng kế tiếp
~~~

Khi có thể xử lý 100.000 hàng bằng một câu `UPDATE ... WHERE`, thường **không cần** lặp 100.000 lần để thực hiện từng `UPDATE`.

Vòng lặp hữu ích khi mỗi bước cần quyết định khác nhau, có phụ thuộc giữa các lượt, giới hạn batch, xử lý phần tử mảng, hoặc yêu cầu luồng điều khiển không biểu diễn đơn giản bằng một câu SQL.

### 1.1. So sánh bốn cấu trúc

| Cấu trúc | Nguồn lặp | Điều kiện dừng | Tình huống phù hợp |
|---|---|---|---|
| `LOOP` | Không tự xác định | `EXIT`, `RETURN` hoặc lỗi | Retry, state machine, điều kiện dừng phức tạp |
| `WHILE` | Biểu thức Boolean | Khi điều kiện không TRUE | Lặp đến ngưỡng hoặc đến khi trạng thái đổi |
| `FOR i IN a..b` | Dải số nguyên | Duyệt hết dải đã xác định | Đếm lượt, tạo số thứ tự |
| `FOR rec IN SELECT` | Các hàng query | Hết các hàng | Xử lý có thứ tự trên kết quả SQL |
| `FOREACH ... IN ARRAY` | Phần tử SQL array | Hết array | Duyệt scalar/array slices |

`FOR` có nhiều biến thể, vì vậy số cấu trúc thực tế rộng hơn bốn tên thường được nhắc đến.

## 2. Vòng lặp dùng ở đâu?

PL/pgSQL thường xuất hiện trong:

- `CREATE FUNCTION ... LANGUAGE plpgsql`.
- `CREATE PROCEDURE ... LANGUAGE plpgsql`.
- Khối `DO $$ ... $$ LANGUAGE plpgsql`.
- Trigger function viết bằng PL/pgSQL.

Ví dụ ngắn nhất, dùng `DO` để quan sát kết quả:

~~~sql
DO $$
DECLARE
    v_i INTEGER;
BEGIN
    FOR v_i IN 1..3 LOOP
        RAISE NOTICE 'Iteration %', v_i;
    END LOOP;
END;
$$ LANGUAGE plpgsql;
~~~

Các thông điệp `NOTICE` có thể hiển thị ở client như psql, pgAdmin hoặc công cụ quản trị tùy cấu hình thông báo. Đây là **khối chạy ngay**, không tạo function lưu lại.

### 2.1. BEGIN trong PL/pgSQL không phải BEGIN TRANSACTION

~~~sql
DO $$
BEGIN
    RAISE NOTICE 'Hello';
END;
$$;
~~~

`BEGIN ... END` là cú pháp **khối PL/pgSQL**, không mở một transaction con. Transaction SQL bên ngoài dùng các câu riêng như `BEGIN; COMMIT; ROLLBACK;`.

### 2.2. Cấu trúc PL/pgSQL nền tảng

~~~sql
CREATE FUNCTION schema_name.example()
RETURNS INTEGER
LANGUAGE plpgsql
AS $body$
DECLARE
    v_result INTEGER := 0;
BEGIN
    -- Các lệnh, điều kiện, vòng lặp.
    RETURN v_result;
END;
$body$;
~~~

- `DECLARE` chứa khai báo biến.
- `:=` gán giá trị.
- `BEGIN ... END` bao thân khối.
- `LOOP`/`WHILE`/`FOR`/`FOREACH` là những lệnh bên trong khối.
- `RETURN` kết thúc function trả scalar khi được thực thi.

## 3. Schema dữ liệu mẫu có thể tạo lại

Để thực hành với một bảng có trạng thái và đếm lượt xử lý, trong **database lab trống** chạy:

~~~sql
CREATE SCHEMA pl_loop_lab;

CREATE TABLE pl_loop_lab.jobs (
    job_id BIGINT PRIMARY KEY,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending', 'processing', 'done', 'failed'
        )),
    attempt_count INTEGER NOT NULL DEFAULT 0
        CHECK (attempt_count >= 0),
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);

CREATE TABLE pl_loop_lab.job_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id BIGINT NOT NULL
        REFERENCES pl_loop_lab.jobs(job_id),
    event_type TEXT NOT NULL,
    event_note TEXT,
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);

INSERT INTO pl_loop_lab.jobs (
    job_id, description, status, attempt_count
)
VALUES
    (1, 'Validate file A', 'pending', 0),
    (2, 'Import file B', 'pending', 1),
    (3, 'Export report C', 'done', 1),
    (4, 'Validate file D', 'pending', 0),
    (5, 'Send summary E', 'failed', 3),
    (6, 'Import file F', 'pending', 0),
    (7, 'Export report G', 'processing', 1),
    (8, 'Validate file H', 'pending', 2);

ANALYZE pl_loop_lab.jobs;
~~~

Bộ dữ liệu có 8 jobs, trong đó 5 job ở trạng thái `pending` (IDs 1, 2, 4, 6, 8).

### 3.1. Kiểm tra dữ liệu đầu vào

~~~sql
SELECT
    job_id,
    status,
    attempt_count
FROM pl_loop_lab.jobs
ORDER BY job_id;
~~~

Các ví dụ **chỉ đọc** có thể chạy mà không làm đổi dataset. Các ví dụ DML nên chạy trong transaction và ROLLBACK ở lab khi muốn giữ trạng thái ban đầu.

## 4. LOOP: vòng lặp tổng quát

Cú pháp:

~~~sql
[ <<label>> ]
LOOP
    statements;
END LOOP [ label ];
~~~

`LOOP` không chứa biểu thức điều kiện ở đầu. Nó sẽ tiếp tục cho đến khi:

- Gặp `EXIT` phù hợp.
- Function gặp `RETURN`.
- Phát sinh lỗi làm thoát luồng.
- Có hành vi điều khiển hợp lệ khác kết thúc khối.

### 4.1. Ví dụ tăng biến và EXIT

~~~sql
DO $$
DECLARE
    v_counter INTEGER := 0;
BEGIN
    LOOP
        v_counter := v_counter + 1;

        RAISE NOTICE 'counter=%', v_counter;

        EXIT WHEN v_counter >= 5;
    END LOOP;
END;
$$;
~~~

Luồng:

~~~text
counter = 0
  |
  v
+1 -> 1 -> EXIT? no
+1 -> 2 -> EXIT? no
+1 -> 3 -> EXIT? no
+1 -> 4 -> EXIT? no
+1 -> 5 -> EXIT? yes
  |
  v
Kết thúc LOOP
~~~

### 4.2. EXIT WHEN là cú pháp ngắn

Hai cách tương đương về ý định:

~~~sql
EXIT WHEN v_counter >= 5;
~~~

và:

~~~sql
IF v_counter >= 5 THEN
    EXIT;
END IF;
~~~

`EXIT WHEN` thường gọn khi điều kiện dừng đơn giản. `IF ... THEN EXIT` phù hợp khi cần ghi log hoặc thực hiện bước kiểm tra trước khi thoát.

## 5. Đặt EXIT ở đầu hay cuối vòng lặp?

Nếu kiểm tra ngay đầu:

~~~sql
DO $$
DECLARE
    v_i INTEGER := 0;
BEGIN
    LOOP
        EXIT WHEN v_i >= 3;

        v_i := v_i + 1;
        RAISE NOTICE 'i=%', v_i;
    END LOOP;
END;
$$;
~~~

Thân lặp chính được thực hiện 3 lần.

Nếu kiểm tra ở cuối:

~~~sql
DO $$
DECLARE
    v_i INTEGER := 0;
BEGIN
    LOOP
        v_i := v_i + 1;
        RAISE NOTICE 'i=%', v_i;

        EXIT WHEN v_i >= 3;
    END LOOP;
END;
$$;
~~~

vẫn thực hiện 3 lần trong ví dụ này nhưng luồng xử lý khác khi giá trị ban đầu đã thỏa điều kiện.

### 5.1. Rủi ro do kiểm tra cuối

Nếu một operation không được thực hiện dù chỉ một lần khi điều kiện dừng đúng ngay từ đầu, phải kiểm tra điều kiện **trước** operation.

### 5.2. Có thể thoát mà không dùng EXIT không?

`RETURN` thoát function (hoặc khối code tương ứng theo loại routine) chứ không chỉ thoát vòng lặp. Không dùng `RETURN` thay `EXIT` khi bạn cần tiếp tục xử lý sau loop.

## 6. Vòng lặp vô hạn và bộ chặn an toàn

Một lỗi:

~~~sql
DO $$
BEGIN
    LOOP
        RAISE NOTICE 'never stops';
    END LOOP;
END;
$$;
~~~

vòng lặp không có điều kiện dừng có chủ đích. **Đừng chạy đoạn này.**

Vòng lặp vô hạn có thể:

- Giữ backend bận CPU.
- Gây WAL/I/O nếu có DML.
- Giữ transaction/locks dài.
- Lấp logs nếu có RAISE.
- Chặn các thao tác schema khác.
- Cần hủy query/transaction bằng công cụ quản trị.

### 6.1. Thêm giới hạn số lượt

~~~sql
DO $$
DECLARE
    v_attempt INTEGER := 0;
    v_max_attempt INTEGER := 10;
BEGIN
    LOOP
        EXIT WHEN v_attempt >= v_max_attempt;

        v_attempt := v_attempt + 1;
        RAISE NOTICE 'attempt=%', v_attempt;
    END LOOP;
END;
$$;
~~~

Trong chương trình production, điều kiện dừng thường cần thêm timeout, chính sách retry và giới hạn tài nguyên; không chỉ dựa vào việc tác vụ “sớm muộn sẽ xong”.

## 7. WHILE: kiểm tra điều kiện trước mỗi lượt

Cú pháp:

~~~sql
WHILE condition LOOP
    statements;
END LOOP;
~~~

PostgreSQL đánh giá `condition` trước khi chạy thân vòng lặp. Vòng lặp tiếp tục **chỉ khi điều kiện TRUE**.

~~~sql
DO $$
DECLARE
    v_i INTEGER := 0;
BEGIN
    WHILE v_i < 5 LOOP
        v_i := v_i + 1;
        RAISE NOTICE 'i=%', v_i;
    END LOOP;
END;
$$;
~~~

Kết quả thông điệp từ 1 tới 5.

### 7.1. Khi điều kiện FALSE ngay từ đầu

~~~sql
DO $$
DECLARE
    v_i INTEGER := 10;
BEGIN
    WHILE v_i < 5 LOOP
        RAISE NOTICE 'This will not run';
        v_i := v_i + 1;
    END LOOP;
END;
$$;
~~~

Thân vòng lặp chạy **0 lần**.

### 7.2. Khi điều kiện là NULL

Trong PL/pgSQL, `WHILE` chỉ tiếp tục khi biểu thức Boolean TRUE. Nếu điều kiện trả NULL (unknown), vòng lặp không thực hiện lượt đó. Không coi NULL là TRUE.

## 8. Chọn LOOP hay WHILE

Hai cách có thể biểu diễn cùng logic:

~~~sql
-- LOOP + EXIT:
LOOP
    EXIT WHEN v_i >= 5;
    v_i := v_i + 1;
END LOOP;
~~~

~~~sql
-- WHILE:
WHILE v_i < 5 LOOP
    v_i := v_i + 1;
END LOOP;
~~~

Quy tắc thực hành:

- Dùng `WHILE` nếu điều kiện tiếp tục **rõ ràng trước mỗi lượt**.
- Dùng `LOOP` nếu có nhiều điểm thoát hoặc việc kiểm tra xuất hiện tự nhiên giữa/cuối lượt.
- Với một dải số cố định, cân nhắc `FOR integer` thay cả hai.
- Với một tập hàng SQL, cân nhắc `FOR record IN query` thay tự quản cursor.

### 8.1. Tránh nhân bản điều kiện

Nếu một vòng lặp có ba biến trạng thái, đừng copy cùng điều kiện phức tạp ở nhiều nhánh; đặt tên biến Boolean hoặc chia thành function trợ giúp khi làm code rõ hơn.

## 9. FOR integer: duyệt một khoảng số

Cú pháp:

~~~sql
FOR variable IN [ REVERSE ] lower_bound..upper_bound
    [ BY step ]
LOOP
    statements;
END LOOP;
~~~

Ví dụ:

~~~sql
DO $$
DECLARE
    v_i INTEGER;
BEGIN
    FOR v_i IN 1..5 LOOP
        RAISE NOTICE 'i=%', v_i;
    END LOOP;
END;
$$;
~~~

Các giá trị lần lượt: 1, 2, 3, 4, 5.

### 9.1. Biến FOR integer được tạo cho vòng lặp

Với integer FOR, PostgreSQL tạo **biến vòng lặp kiểu integer trong phạm vi loop**, ngay cả khi bên ngoài có biến trùng tên. Vì vậy ví dụ thường viết gọn:

~~~sql
DO $$
BEGIN
    FOR i IN 1..3 LOOP
        RAISE NOTICE '%', i;
    END LOOP;
END;
$$;
~~~

Không cần khai báo `i` trong `DECLARE`.

### 9.2. Biên trên được tính vào dải

`1..5` tương ứng 1 tới 5, **bao gồm cả 1 và 5**. Nếu muốn 5 lượt với index bắt đầu từ 0, có thể dùng `0..4`.

## 10. FOR integer với REVERSE

~~~sql
DO $$
BEGIN
    FOR i IN REVERSE 5..1 LOOP
        RAISE NOTICE 'i=%', i;
    END LOOP;
END;
$$;
~~~

Kết quả 5, 4, 3, 2, 1.

### 10.1. Không viết đảo biên mà quên REVERSE

~~~sql
FOR i IN 5..1 LOOP
    ...
END LOOP;
~~~

với step mặc định tăng dần không phải cách duyệt ngược. Khi lower bound lớn hơn upper bound, vòng lặp tăng dần có thể chạy 0 lượt.

### 10.2. REVERSE cần biên phù hợp

Với `FOR i IN REVERSE lower..upper`, dải thực hiện từ giá trị biên đầu tới biên sau theo hướng giảm. Đặt `5..1` để lặp xuống; đừng đảo thứ tự thành `1..5` rồi mong tự tăng.

## 11. FOR integer với BY

`BY` chỉ bước nhảy dương; hướng được quyết định bởi việc có `REVERSE` hay không.

~~~sql
DO $$
BEGIN
    FOR i IN 2..10 BY 2 LOOP
        RAISE NOTICE 'even=%', i;
    END LOOP;
END;
$$;
~~~

Thông điệp: 2, 4, 6, 8, 10.

~~~sql
DO $$
BEGIN
    FOR i IN REVERSE 10..1 BY 3 LOOP
        RAISE NOTICE 'reverse=%', i;
    END LOOP;
END;
$$;
~~~

Thông điệp: 10, 7, 4, 1.

### 11.1. BY phải dương

Không dùng `BY 0` hoặc `BY -1` để thử tạo bước lặp đặc biệt. Nếu cần đi lùi, dùng `REVERSE` với bước dương.

### 11.2. Khi biên không chia hết cho BY

~~~sql
FOR i IN 1..8 BY 3 LOOP
    ...
END LOOP;
~~~

sẽ chạy qua 1, 4, 7; không tự “ép” đến 8.

## 12. Biên của integer FOR được đánh giá khi vào vòng lặp

Các biểu thức `lower_bound`, `upper_bound` và `step` của integer FOR được đánh giá **một lần khi bắt đầu loop**.

~~~sql
DO $$
DECLARE
    v_upper INTEGER := 3;
BEGIN
    FOR i IN 1..v_upper LOOP
        RAISE NOTICE 'i=% upper=%', i, v_upper;
        v_upper := 10;
    END LOOP;
END;
$$;
~~~

Vòng lặp vẫn chạy 3 lượt chứ không kéo dài đến 10 vì `v_upper` thay đổi trong thân loop.

### 12.1. Khi số lượt cần thay đổi theo dữ liệu runtime

Nếu muốn kiểm tra ngưỡng mới mỗi lượt, `WHILE` hoặc `LOOP + EXIT WHEN` phù hợp hơn integer FOR có dải cố định từ lúc bắt đầu.

## 13. Scope của biến integer FOR

~~~sql
DO $$
DECLARE
    i INTEGER := 100;
BEGIN
    RAISE NOTICE 'before=%', i;

    FOR i IN 1..3 LOOP
        RAISE NOTICE 'inside=%', i;
    END LOOP;

    RAISE NOTICE 'after=%', i;
END;
$$;
~~~

Bên trong integer FOR có biến vòng lặp riêng, che khuất biến ngoài cùng tên. Sau khi kết thúc, biến `i` của khối bên ngoài vẫn có giá trị 100.

Đây là lý do không dựa vào “giá trị của loop counter sau khi FOR kết thúc” để suy số lượt; hãy dùng biến tổng hợp riêng nếu cần.

## 14. FOR integer với phép tính có giới hạn

Một function tính tổng 1 tới N:

~~~sql
CREATE FUNCTION pl_loop_lab.sum_1_to(
    p_n INTEGER
)
RETURNS BIGINT
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $$
DECLARE
    v_total BIGINT := 0;
BEGIN
    IF p_n < 0 OR p_n > 100000 THEN
        RAISE EXCEPTION
            'p_n out of supported range: %', p_n;
    END IF;

    FOR i IN 1..p_n LOOP
        v_total := v_total + i;
    END LOOP;

    RETURN v_total;
END;
$$;
~~~

Gọi:

~~~sql
SELECT pl_loop_lab.sum_1_to(5);
~~~

Kết quả 15.

### 14.1. Dải rỗng

Với `p_n = 0`, dải `1..0` không lặp, kết quả là 0.

### 14.2. Không phải mọi phép cộng dải cần vòng lặp

Với N hợp lệ, công thức toán học:

\[
1 + 2 + \dots + N = \frac{N(N+1)}{2}
\]

thường đơn giản hơn và tránh chi phí lặp. Ví dụ trên nhằm dạy `FOR`, **không phải khuyến nghị dùng loop cho mọi phép tổng dải số**.

## 15. CONTINUE: bỏ phần còn lại của lượt hiện tại

`CONTINUE` không kết thúc toàn bộ vòng lặp; nó chuyển sang **lượt tiếp theo**.

~~~sql
DO $$
BEGIN
    FOR i IN 1..6 LOOP
        CONTINUE WHEN i % 2 = 0;

        RAISE NOTICE 'odd=%', i;
    END LOOP;
END;
$$;
~~~

Chỉ in 1, 3, 5.

### 15.1. CONTINUE WHEN

~~~sql
CONTINUE WHEN condition;
~~~

tương đương ý định:

~~~sql
IF condition THEN
    CONTINUE;
END IF;
~~~

nếu điều kiện có giá trị TRUE.

### 15.2. Luồng điều khiển

~~~text
Duyệt một giá trị
       |
       v
Có cần bỏ qua?
    /       \
  Có       Không
   |          |
CONTINUE      Thực hiện phần còn lại
   |          |
   +----------+
       |
       v
    Lượt tiếp theo
~~~

### 15.3. Không đặt thao tác bắt buộc sau CONTINUE

Nếu mỗi lượt bắt buộc cập nhật bộ đếm thử, đặt việc cập nhật **trước** lệnh CONTINUE hoặc thiết kế tách điều kiện rõ. Mọi statement sau CONTINUE trong cùng lượt đều bị bỏ qua.

## 16. EXIT: kết thúc vòng lặp hiện tại

~~~sql
DO $$
BEGIN
    FOR i IN 1..10 LOOP
        EXIT WHEN i > 4;

        RAISE NOTICE 'i=%', i;
    END LOOP;
END;
$$;
~~~

Thông điệp 1, 2, 3, 4. Khi `i=5`, EXIT chấm dứt loop.

### 16.1. EXIT khác CONTINUE

| Lệnh | Tác động |
|---|---|
| `CONTINUE` | Bỏ phần còn lại của lượt hiện tại, sang lượt kế |
| `EXIT` | Rời vòng lặp |
| `RETURN` | Rời function trả kết quả (hoặc kết thúc routine theo kiểu phù hợp) |
| `RAISE EXCEPTION` | Báo lỗi, có thể được block EXCEPTION xử lý |
| `RETURN NEXT` | Thêm phần tử vào kết quả set-returning function, **không tự dừng loop** |

### 16.2. EXIT WHEN không phải return value

Một vòng lặp `EXIT WHEN ...` chỉ thoát loop, rồi các statement sau `END LOOP;` tiếp tục được thực thi.

## 17. Nhãn vòng lặp: <<label>>

Khi có vòng lặp lồng nhau, nhãn làm rõ lệnh nào cần thoát.

~~~sql
DO $$
BEGIN
    <<outer_loop>>
    FOR i IN 1..3 LOOP
        <<inner_loop>>
        FOR j IN 1..3 LOOP
            RAISE NOTICE 'i=% j=%', i, j;

            EXIT outer_loop
                WHEN i = 2 AND j = 2;
        END LOOP inner_loop;
    END LOOP outer_loop;

    RAISE NOTICE 'finished';
END;
$$;
~~~

Với điều kiện `i=2 AND j=2`, `EXIT outer_loop` kết thúc **cả vòng lặp ngoài**, không chỉ vòng lặp j.

### 17.1. Đặt nhãn ở đâu?

~~~sql
<<my_loop>>
LOOP
    ...
END LOOP my_loop;
~~~

Tên nhãn ở cuối có thể dùng để làm code dễ theo dõi; phải khớp nhãn đầu khi viết.

### 17.2. Không dùng nhãn mơ hồ

Tên `outer_loop` hoặc `jobs_loop` rõ nghĩa hơn `l1`/`l2` khi thủ tục có nhiều tầng. Với 4–5 vòng lặp lồng nhau, cân nhắc refactor thành SQL set-based hoặc function nhỏ hơn để dễ bảo trì.

## 18. CONTINUE với nhãn vòng lặp ngoài

`CONTINUE outer_loop` bỏ phần còn lại của các vòng lặp đang nằm bên trong, rồi bắt đầu **lượt tiếp theo của vòng lặp ngoài**.

~~~sql
DO $$
BEGIN
    <<customer_loop>>
    FOR customer_id IN 1..3 LOOP
        FOR item_no IN 1..3 LOOP
            IF customer_id = 2 AND item_no = 2 THEN
                CONTINUE customer_loop;
            END IF;

            RAISE NOTICE
                'customer=% item=%',
                customer_id, item_no;
        END LOOP;
    END LOOP customer_loop;
END;
$$;
~~~

Với customer 2, khi item 2 được gặp, vòng item dừng cho lượt customer đó và chương trình chuyển sang customer 3.

### 18.1. Label được dùng cho EXIT và CONTINUE khác nhau

`EXIT label` có thể dùng với vòng lặp và trong những tình huống thích hợp với labeled block. `CONTINUE label` phải chỉ tới một loop. Không dùng CONTINUE để nhảy sang một labeled BEGIN block không phải loop.

## 19. Lồng nhiều vòng FOR

Ví dụ tạo cặp tọa độ:

~~~sql
DO $$
BEGIN
    FOR row_no IN 1..3 LOOP
        FOR col_no IN 1..2 LOOP
            RAISE NOTICE
                'cell=(%,%)',
                row_no, col_no;
        END LOOP;
    END LOOP;
END;
$$;
~~~

Số lượt thực thi thân trong là:

\[
3 \times 2 = 6
\]

Nếu mỗi vòng có 1000 lượt, tổng thao tác có thể là một triệu. Với bảng dữ liệu thật, nested loops dễ dẫn tới **độ phức tạp tăng theo tích số lượt**.

### 19.1. Khi nested loops che một phép JOIN

Nếu logic đang duyệt mỗi customer rồi duyệt mỗi order, hãy cân nhắc câu:

~~~sql
SELECT
    c.customer_id,
    j.job_id
FROM pl_loop_lab.jobs AS j
JOIN (
    VALUES (1::BIGINT), (2::BIGINT)
) AS c(customer_id)
    ON (j.job_id % 2) + 1 = c.customer_id;
~~~

Đây chỉ là ví dụ JOIN trên dữ liệu giả định, không phải quan hệ nghiệp vụ thực giữa jobs và customers. Trong ứng dụng thật, dùng khóa ngoại/JOIN condition đúng thay vì vòng lặp hai tầng để tìm matches.

## 20. FOR record IN query: lặp qua các hàng SQL

Cú pháp:

~~~sql
FOR target IN
    SELECT ...
LOOP
    statements;
END LOOP;
~~~

`target` thường là một biến `RECORD` hoặc một row/composite variable có cấu trúc phù hợp.

~~~sql
DO $$
DECLARE
    v_job RECORD;
BEGIN
    FOR v_job IN
        SELECT
            job_id,
            description,
            attempt_count
        FROM pl_loop_lab.jobs
        WHERE status = 'pending'
        ORDER BY job_id
    LOOP
        RAISE NOTICE
            'job=% attempts=% desc=%',
            v_job.job_id,
            v_job.attempt_count,
            v_job.description;
    END LOOP;
END;
$$;
~~~

Kết quả logic: duyệt những job đang pending trong tập kết quả SELECT.

### 20.1. Không nhầm FOR integer với FOR query

- `FOR i IN 1..10 LOOP` tạo biến integer cho dải.
- `FOR rec IN SELECT ... LOOP` dùng record/row hoặc danh sách biến đích phù hợp.
- `FOR rec IN EXECUTE ... LOOP` dùng query SQL động.

Trong dạng query FOR, biến đích thường **cần được khai báo** trước (hoặc dùng danh sách scalar variables được khai báo). Không mặc định record variable tự được tạo như integer loop counter.

## 21. RECORD và %ROWTYPE

Biến `RECORD` có cấu trúc thích ứng theo hàng mà truy vấn trả về:

~~~sql
DECLARE
    v_record RECORD;
~~~

Dùng `v_record.job_id` sau khi câu SELECT trong loop cung cấp cột `job_id`.

`%ROWTYPE` gắn biến với cấu trúc hàng của một bảng hoặc view:

~~~sql
DECLARE
    v_job pl_loop_lab.jobs%ROWTYPE;
~~~

Ví dụ:

~~~sql
DO $$
DECLARE
    v_job pl_loop_lab.jobs%ROWTYPE;
BEGIN
    FOR v_job IN
        SELECT *
        FROM pl_loop_lab.jobs
        WHERE status = 'pending'
        ORDER BY job_id
    LOOP
        RAISE NOTICE
            'job=% status=%',
            v_job.job_id,
            v_job.status;
    END LOOP;
END;
$$;
~~~

### 21.1. Khi nào dùng RECORD?

- Query có tập cột thay đổi.
- Chỉ cần một vài cột từ JOIN.
- Dùng kết quả query động với cấu trúc phù hợp.

### 21.2. Khi nào dùng %ROWTYPE?

- Query khớp kiểu hàng của một bảng/view xác định.
- Muốn truy cập các trường theo cùng schema đối tượng.
- Cần làm việc với toàn hàng trong một thao tác phù hợp.

Nếu query không có trường mong đợi mà code truy cập `v_record.some_field`, có thể phát sinh lỗi. Biến RECORD linh hoạt không thay kiểm tra output contract.

## 22. Query FOR với nhiều scalar variables

PL/pgSQL cho phép dùng danh sách biến đích khi truy vấn trả số cột phù hợp:

~~~sql
DO $$
DECLARE
    v_job_id BIGINT;
    v_attempt INTEGER;
BEGIN
    FOR v_job_id, v_attempt IN
        SELECT
            job_id,
            attempt_count
        FROM pl_loop_lab.jobs
        WHERE status = 'pending'
        ORDER BY job_id
    LOOP
        RAISE NOTICE
            'job=% attempts=%',
            v_job_id, v_attempt;
    END LOOP;
END;
$$;
~~~

Ưu điểm: không cần record khi chỉ có hai cột. Nhược điểm: nếu query thay thứ tự cột hoặc kiểu, code có thể sai hoặc lỗi. Dùng alias/kiểu rõ ràng và không phụ thuộc SELECT * tùy tiện.

## 23. FOR query và ORDER BY

SQL không bảo đảm thứ tự hàng nếu không có `ORDER BY`. Vì vậy nếu logic loop phụ thuộc thứ tự:

~~~sql
FOR v_job IN
    SELECT job_id
    FROM pl_loop_lab.jobs
    WHERE status = 'pending'
    ORDER BY job_id
LOOP
    ...
END LOOP;
~~~

`ORDER BY job_id` giúp xác định thứ tự duyệt.

### 23.1. Có nên luôn ORDER BY?

Không nhất thiết. Nếu mỗi hàng độc lập và thứ tự không quan trọng, sort có thể làm tăng chi phí. Chỉ dùng ordering khi cần tính đúng, fairness, phân trang/batch hoặc output có thứ tự.

### 23.2. Ordering không giải quyết concurrency một mình

Nếu nhiều workers cùng xử lý jobs, `ORDER BY job_id` không ngăn hai workers cùng đọc/cập nhật một hàng. Cần khóa, transaction và chiến lược claim jobs thích hợp.

## 24. FOR query trả 0 hàng

~~~sql
DO $$
DECLARE
    v_job RECORD;
BEGIN
    FOR v_job IN
        SELECT job_id
        FROM pl_loop_lab.jobs
        WHERE status = 'never_exists'
    LOOP
        RAISE NOTICE 'This body will not run';
    END LOOP;

    RAISE NOTICE 'After the loop';
END;
$$;
~~~

Query không có rows, thân `FOR` chạy 0 lần. Các câu sau `END LOOP;` vẫn chạy.

### 24.1. Dùng FOUND sau FOR

Trong PL/pgSQL, một `FOR` loop đặt `FOUND` sau khi loop kết thúc để phản ánh loop đã thực hiện ít nhất một lượt hay chưa.

~~~sql
DO $$
DECLARE
    v_job RECORD;
BEGIN
    FOR v_job IN
        SELECT job_id
        FROM pl_loop_lab.jobs
        WHERE status = 'pending'
    LOOP
        NULL;
    END LOOP;

    IF FOUND THEN
        RAISE NOTICE 'At least one pending job';
    ELSE
        RAISE NOTICE 'No pending jobs';
    END IF;
END;
$$;
~~~

**Quan trọng:** `FOUND` là biến đặc biệt bị những lệnh SQL/PLpgSQL nhất định cập nhật. Nên đọc ngay sau vòng lặp nếu cần phản ánh vòng lặp, tránh để một DML hoặc SELECT INTO khác ghi đè trước khi kiểm tra.

## 25. FOUND bên trong vòng lặp và ngoài vòng lặp

Một điểm dễ nhầm:

- `FOR`/`FOREACH` cập nhật `FOUND` khi **thoát khỏi loop**.
- Những lệnh bên trong loop như `UPDATE`, `PERFORM` hoặc `SELECT INTO` có thể thay `FOUND` ngay trong thân loop.

Do đó `FOUND` đang quan sát **bên trong** một query FOR có thể phản ánh lệnh SQL vừa chạy, chứ không nhất thiết chỉ trạng thái vòng lặp.

Nếu cần kết quả ổn định, dùng biến rõ:

~~~sql
DO $$
DECLARE
    v_job RECORD;
    v_processed INTEGER := 0;
BEGIN
    FOR v_job IN
        SELECT job_id
        FROM pl_loop_lab.jobs
        WHERE status = 'pending'
    LOOP
        v_processed := v_processed + 1;
    END LOOP;

    RAISE NOTICE 'rows visited=%', v_processed;
END;
$$;
~~~

## 26. GET DIAGNOSTICS ROW_COUNT sau DML

Khi thực thi DML trong loop:

~~~sql
DO $$
DECLARE
    v_affected BIGINT;
BEGIN
    UPDATE pl_loop_lab.jobs
    SET updated_at = statement_timestamp()
    WHERE job_id = -1;

    GET DIAGNOSTICS v_affected = ROW_COUNT;

    RAISE NOTICE 'affected=%', v_affected;
END;
$$;
~~~

Kết quả thường là 0 với job_id -1 trong lab.

### 26.1. ROW_COUNT khác FOUND

- `FOUND` là Boolean.
- `ROW_COUNT` là số hàng chịu tác động của lệnh SQL gần nhất mà cơ chế diagnostics hỗ trợ.
- `ROW_COUNT` cần được lấy ngay sau lệnh cần đo, trước khi một câu SQL khác làm thay đổi diagnostics.

Nên dùng `GET DIAGNOSTICS` khi cần đếm hàng để giới hạn batch hoặc kiểm tra điều kiện ghi.

## 27. FOR rec IN EXECUTE: truy vấn động

Cú pháp:

~~~sql
FOR record_variable IN
    EXECUTE dynamic_sql
    [ USING value1, value2, ... ]
LOOP
    statements;
END LOOP;
~~~

Ví dụ chỉ đọc có bảng tên cố định:

~~~sql
DO $$
DECLARE
    v_job RECORD;
    v_sql TEXT :=
        'SELECT job_id, status
         FROM pl_loop_lab.jobs
         WHERE status = $1
         ORDER BY job_id';
BEGIN
    FOR v_job IN
        EXECUTE v_sql USING 'pending'
    LOOP
        RAISE NOTICE
            'job=% status=%',
            v_job.job_id, v_job.status;
    END LOOP;
END;
$$;
~~~

`USING` truyền giá trị an toàn hơn việc nối literal người dùng trực tiếp vào SQL.

### 27.1. Dấu $1 của dynamic query

Trong chuỗi SQL động, `$1` là placeholder được `USING` gán giá trị. Đừng nhầm với tham số của outer function nếu chúng có tên khác.

### 27.2. Query động có overhead

`EXECUTE` không tự động tái sử dụng cùng một plan cache của PL/pgSQL static SQL theo cách giống nhau; nó lập kế hoạch cho truy vấn động khi chạy. Chỉ dùng dynamic SQL khi thật sự cần cấu trúc query thay đổi.

## 28. Dynamic identifiers và SQL injection

Nếu tên bảng được chọn động, không truyền tên đó qua `USING` như một giá trị rồi kỳ vọng nó trở thành identifier.

Mẫu phù hợp:

~~~sql
CREATE FUNCTION pl_loop_lab.count_status_dynamic(
    p_schema NAME,
    p_table NAME,
    p_status TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    v_sql TEXT;
    v_count BIGINT;
BEGIN
    v_sql := format(
        'SELECT COUNT(*) FROM %I.%I WHERE status = $1',
        p_schema, p_table
    );

    EXECUTE v_sql
    INTO v_count
    USING p_status;

    RETURN v_count;
END;
$$;
~~~

- `%I` quote identifier hợp lệ.
- `USING` bind data values.
- `SECURITY INVOKER` dùng context quyền caller theo quy tắc tương ứng.
- Query giả định bảng đích có cột `status`.
- Ứng dụng thật cần **whitelist schema/table** được phép, không chỉ quote tên.

Không tạo SECURITY DEFINER dynamic SQL dùng tên bảng do người gọi điều khiển mà không có authorization/validation nghiêm ngặt.

## 29. Query FOR và FETCH cursor có gì khác?

`FOR rec IN SELECT ... LOOP` giúp duyệt query result mà không phải quản lý cursor thủ công.

Khi cần control fetch từng bước, có thể dùng cursor:

~~~sql
DO $$
DECLARE
    v_job RECORD;
    cur_jobs CURSOR FOR
        SELECT job_id, status
        FROM pl_loop_lab.jobs
        ORDER BY job_id;
BEGIN
    OPEN cur_jobs;

    LOOP
        FETCH cur_jobs INTO v_job;

        EXIT WHEN NOT FOUND;

        RAISE NOTICE
            'job=% status=%',
            v_job.job_id, v_job.status;
    END LOOP;

    CLOSE cur_jobs;
END;
$$;
~~~

### 29.1. Vì sao FETCH kết hợp LOOP tự nhiên?

- `FETCH` cố đọc hàng tiếp theo.
- `FOUND` phản ánh có lấy được hàng hay không.
- `EXIT WHEN NOT FOUND` dừng ở cuối cursor.

### 29.2. Khi nào dùng cursor?

Khi cần API cursor cụ thể (OPEN/FETCH/MOVE/CLOSE), cấu trúc fetch linh hoạt hoặc tương tác với logic khác. Đối với việc đơn giản là “đi qua các hàng query”, query FOR thường gọn hơn và ít lỗi hơn.

### 29.3. Cursor và transaction

Cursor có phạm vi và quy tắc transaction; transaction-ending operations có thể ảnh hưởng cursor. Không mặc định một cursor luôn sống sau COMMIT, đặc biệt khi dùng cursor thông thường thay vì holdable cursor với semantics riêng.

## 30. FOREACH: duyệt SQL array

Cú pháp:

~~~sql
FOREACH target [ SLICE n ]
IN ARRAY array_expression
LOOP
    statements;
END LOOP;
~~~

Ví dụ:

~~~sql
DO $$
DECLARE
    v_number INTEGER;
BEGIN
    FOREACH v_number IN ARRAY
        ARRAY[10, 20, 30]::INTEGER[]
    LOOP
        RAISE NOTICE 'value=%', v_number;
    END LOOP;
END;
$$;
~~~

Kết quả các giá trị 10, 20, 30.

**FOREACH trong PL/pgSQL làm việc với SQL arrays**, không trực tiếp với JSON arrays. Muốn duyệt JSONB array, dùng `jsonb_array_elements` trong query FOR hoặc chuyển hợp lệ sang SQL array.

## 31. FOREACH với mảng text

~~~sql
DO $$
DECLARE
    v_tag TEXT;
BEGIN
    FOREACH v_tag IN ARRAY
        ARRAY['priority', 'gift', 'fragile']::TEXT[]
    LOOP
        RAISE NOTICE 'tag=%', v_tag;
    END LOOP;
END;
$$;
~~~

Ứng dụng:

- Xử lý danh sách IDs/tags đã nhập kiểu SQL array.
- Kiểm tra từng phần tử với rule phức tạp.
- Tạo chuỗi kết quả từ nhiều giá trị.
- Chia nhánh theo phần tử.

Nếu chỉ cần tìm phần tử thỏa điều kiện, một biểu thức SQL với `ANY`/`unnest` thường đơn giản hơn loop.

## 32. FOREACH với input parameter ARRAY

~~~sql
CREATE FUNCTION pl_loop_lab.sum_array(
    p_numbers INTEGER[]
)
RETURNS BIGINT
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_number INTEGER;
    v_total BIGINT := 0;
BEGIN
    FOREACH v_number IN ARRAY
        COALESCE(p_numbers, ARRAY[]::INTEGER[])
    LOOP
        v_total := v_total + COALESCE(v_number, 0);
    END LOOP;

    RETURN v_total;
END;
$$;
~~~

Gọi:

~~~sql
SELECT pl_loop_lab.sum_array(ARRAY[1, 2, 3]);
SELECT pl_loop_lab.sum_array(ARRAY[1, NULL, 3]);
SELECT pl_loop_lab.sum_array(ARRAY[]::INTEGER[]);
~~~

Kết quả tương ứng: 6, 4 và 0 theo chính sách **NULL element được coi là 0**.

### 32.1. Xử lý NULL SQL array

Ở ví dụ này, `COALESCE(p_numbers, ARRAY[]::INTEGER[])` biến SQL NULL array thành empty array. Đây là lựa chọn **có chủ đích**, không phải semantics bắt buộc mọi ứng dụng.

### 32.2. NULL element trong SQL array

Một SQL array có thể chứa phần tử NULL. Nếu dùng `v_total := v_total + v_number` mà không COALESCE, v_total có thể thành NULL. Phải quyết định chính sách bỏ qua, thay bằng 0 hoặc từ chối input.

## 33. FOREACH với SLICE

Khi SQL array nhiều chiều, `SLICE n` cho phép mỗi lượt nhận một **mảng con** có số chiều n thay vì nhận phần tử scalar.

Ví dụ mảng hai chiều:

~~~sql
DO $$
DECLARE
    v_row INTEGER[];
BEGIN
    FOREACH v_row SLICE 1 IN ARRAY
        ARRAY[
            [1, 2, 3],
            [4, 5, 6]
        ]::INTEGER[][]
    LOOP
        RAISE NOTICE 'row=%', v_row;
    END LOOP;
END;
$$;
~~~

Trong mỗi lượt, `v_row` là một SQL array một chiều chứa các phần tử tương ứng của mảng hai chiều.

### 33.1. SLICE 0 so với SLICE 1

- Không ghi SLICE hoặc dùng `SLICE 0`: duyệt các phần tử scalar.
- `SLICE 1`: duyệt các lát một chiều.
- Giá trị SLICE phải hợp lệ với số chiều mảng và target variable có kiểu phù hợp.

### 33.2. Mảng phải có cấu trúc chiều hợp lệ

Không sử dụng `SLICE 1` trên dữ liệu không phải SQL array có cấu trúc phù hợp. PostgreSQL kiểm tra type/shape; các SQL arrays đa chiều phải tuân quy tắc kích thước từng chiều.

## 34. FOREACH khác FOR integer với chỉ số mảng

Có thể duyệt SQL array bằng chỉ số:

~~~sql
DO $$
DECLARE
    v_items INTEGER[] := ARRAY[10, 20, 30];
BEGIN
    FOR i IN
        array_lower(v_items, 1)
        ..
        array_upper(v_items, 1)
    LOOP
        RAISE NOTICE
            'index=% value=%',
            i, v_items[i];
    END LOOP;
END;
$$;
~~~

Dạng này phù hợp khi cần **index**, không chỉ value.

Tuy nhiên `array_lower`/`array_upper` có thể trả NULL cho array rỗng và việc tạo dải số với biên NULL không tương đương lặp 0 lần hợp lệ. Với input có thể rỗng, nên xử lý trước.

### 34.1. FOREACH không phụ thuộc array lower bound

`FOREACH` duyệt các phần tử theo thứ tự lưu trong array, không cần biết index bắt đầu tại 0, 1 hay giá trị khác. Khi chỉ cần values, FOREACH thường gọn hơn tự quản biên chỉ số.

## 35. generate_subscripts: lấy index an toàn hơn cho array

Nếu cần cả index và value:

~~~sql
SELECT
    i,
    a[i] AS value
FROM (
    SELECT ARRAY[10,20,30]::INTEGER[] AS a
) AS src
CROSS JOIN LATERAL generate_subscripts(
    src.a, 1
) AS s(i)
ORDER BY i;
~~~

`generate_subscripts(array, dimension)` tạo indices theo dimension phù hợp. Với array rỗng, nó trả 0 hàng.

Trong PL/pgSQL, có thể:

~~~sql
DO $$
DECLARE
    v_items INTEGER[] := ARRAY[10,20,30];
    v_i INTEGER;
BEGIN
    FOR v_i IN
        SELECT generate_subscripts(v_items, 1)
    LOOP
        RAISE NOTICE
            'index=% value=%',
            v_i, v_items[v_i];
    END LOOP;
END;
$$;
~~~

Đây là query FOR trên indices, khác FOREACH trực tiếp trên values.

## 36. FOREACH trên JSON array không phải cú pháp trực tiếp

JSON array:

~~~sql
'[10,20,30]'::JSONB
~~~

không phải `INTEGER[]`.

Ví dụ mở JSONB thành rows rồi lặp:

~~~sql
DO $$
DECLARE
    v_elem JSONB;
BEGIN
    FOR v_elem IN
        SELECT elem
        FROM jsonb_array_elements(
            '[10,20,30]'::JSONB
        ) AS x(elem)
    LOOP
        RAISE NOTICE 'json element=%', v_elem;
    END LOOP;
END;
$$;
~~~

Khi cần vị trí JSON element:

~~~sql
SELECT elem, ordinality
FROM jsonb_array_elements(
    '["A","B","C"]'::JSONB
) WITH ORDINALITY AS x(elem, ordinality)
ORDER BY ordinality;
~~~

Đừng viết `FOREACH v IN ARRAY jsonb_value`; nó không phải SQL array expression phù hợp.

## 37. CONTINUE và EXIT trong FOREACH

~~~sql
DO $$
DECLARE
    v_value INTEGER;
BEGIN
    FOREACH v_value IN ARRAY
        ARRAY[1, 0, 2, -1, 3]
    LOOP
        CONTINUE WHEN v_value = 0;
        EXIT WHEN v_value < 0;

        RAISE NOTICE 'accepted=%', v_value;
    END LOOP;
END;
$$;
~~~

- Value 1: in.
- Value 0: bỏ qua.
- Value 2: in.
- Value -1: EXIT.
- Value 3: không được xử lý.

Luồng này thể hiện rõ khác biệt giữa bỏ một phần tử và kết thúc toàn bộ duyệt mảng.

## 38. RETURN trong function có vòng lặp

Ví dụ tìm phần tử đầu tiên lớn hơn ngưỡng:

~~~sql
CREATE FUNCTION pl_loop_lab.first_above(
    p_numbers INTEGER[],
    p_limit INTEGER
)
RETURNS INTEGER
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_number INTEGER;
BEGIN
    IF p_numbers IS NULL THEN
        RETURN NULL;
    END IF;

    FOREACH v_number IN ARRAY p_numbers LOOP
        IF v_number > p_limit THEN
            RETURN v_number;
        END IF;
    END LOOP;

    RETURN NULL;
END;
$$;
~~~

Gọi:

~~~sql
SELECT pl_loop_lab.first_above(
    ARRAY[2, 5, 9, 3], 6
);
~~~

Kết quả 9.

### 38.1. RETURN khác EXIT

- `RETURN v_number`: trả kết quả và **kết thúc function ngay**.
- `EXIT`: chỉ thoát vòng lặp hiện tại/loop được chỉ bởi label; function tiếp tục chạy sau `END LOOP`.

### 38.2. NULL trong điều kiện

`v_number > p_limit` có thể trả NULL khi một giá trị NULL. PL/pgSQL `IF` chỉ thực thi nhánh khi điều kiện TRUE, nên phần tử NULL không gây RETURN trong ví dụ.

## 39. RETURN NEXT trong set-returning function

Function trả tập có thể thêm từng hàng từ vòng lặp bằng `RETURN NEXT`:

~~~sql
CREATE FUNCTION pl_loop_lab.even_numbers(
    p_from INTEGER,
    p_to INTEGER
)
RETURNS SETOF INTEGER
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    IF p_to - p_from > 10000 THEN
        RAISE EXCEPTION 'Range too large';
    END IF;

    FOR i IN p_from..p_to LOOP
        IF i % 2 = 0 THEN
            RETURN NEXT i;
        END IF;
    END LOOP;

    RETURN;
END;
$$;
~~~

Gọi:

~~~sql
SELECT *
FROM pl_loop_lab.even_numbers(1, 8)
ORDER BY even_numbers;
~~~

Kết quả logic: 2, 4, 6, 8.

### 39.1. RETURN NEXT không kết thúc loop

Sau `RETURN NEXT i`, thân loop có thể tiếp tục và hàm có thể sinh thêm phần tử. `RETURN;` cuối cùng kết thúc set-returning function.

### 39.2. Kiểm tra giới hạn cả hai phía

Ví dụ trên giới hạn hiệu hai biên để minh họa. Một implementation production phải còn xem overflow, phạm vi số nguyên và tổng số lượt thực tế. Không đưa input không kiểm soát vào vòng lặp tạo hàng triệu phần tử.

## 40. RETURN QUERY thường tốt hơn lặp RETURN NEXT

Nếu dữ liệu đầu ra có thể tạo bằng một SELECT, PL/pgSQL cung cấp `RETURN QUERY`:

~~~sql
CREATE FUNCTION pl_loop_lab.pending_job_ids(
    p_limit INTEGER
)
RETURNS TABLE(job_id BIGINT)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    IF p_limit < 0 OR p_limit > 1000 THEN
        RAISE EXCEPTION 'Invalid limit %', p_limit;
    END IF;

    RETURN QUERY
    SELECT j.job_id
    FROM pl_loop_lab.jobs AS j
    WHERE j.status = 'pending'
    ORDER BY j.job_id
    LIMIT p_limit;
END;
$$;
~~~

Gọi:

~~~sql
SELECT *
FROM pl_loop_lab.pending_job_ids(3);
~~~

Trong dataset mẫu, logic trả job IDs 1, 2, 4.

### 40.1. Khi nào RETURN QUERY tốt hơn?

- Một SELECT đã biểu diễn toàn bộ rows.
- Không cần branching theo từng phần tử.
- PostgreSQL có thể tối ưu query theo tập.
- Code ngắn và ít state hơn loop.

Nếu mỗi hàng cần logic điều khiển phức tạp, `FOR rec IN SELECT ... RETURN NEXT` vẫn có thể phù hợp; cần cân nhắc hiệu năng và tính dễ kiểm chứng.

## 41. Vòng lặp và COUNT(*) không luôn tương đương

Muốn đếm pending jobs:

~~~sql
SELECT COUNT(*)
FROM pl_loop_lab.jobs
WHERE status = 'pending';
~~~

thường đơn giản hơn:

~~~sql
DO $$
DECLARE
    v_count BIGINT := 0;
    v_job RECORD;
BEGIN
    FOR v_job IN
        SELECT job_id
        FROM pl_loop_lab.jobs
        WHERE status = 'pending'
    LOOP
        v_count := v_count + 1;
    END LOOP;

    RAISE NOTICE 'count=%', v_count;
END;
$$;
~~~

Cả hai có thể cho cùng kết quả trong snapshot phù hợp, nhưng vòng lặp tạo state/callback cho từng row mà không cần thiết.

### 41.1. Câu hỏi chọn SQL hay PL/pgSQL

> Nếu bỏ toàn bộ vòng lặp và viết một câu `SELECT`, `UPDATE`, `INSERT ... SELECT` hay `DELETE ... WHERE`, liệu có giữ đúng semantics không?

Nếu câu trả lời là có, ưu tiên SQL set-based trước khi thiết kế loop.

## 42. Batch processing: FOR với giới hạn số hàng

Một nhu cầu hợp lý của loop là xử lý một số tác vụ được chọn, kèm kiểm tra riêng từng tác vụ.

Ví dụ **procedure không tự COMMIT**, claim các job pending:

~~~sql
CREATE PROCEDURE pl_loop_lab.claim_pending_jobs(
    IN p_limit INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_job RECORD;
    v_claimed INTEGER := 0;
BEGIN
    IF p_limit IS NULL
       OR p_limit < 1
       OR p_limit > 100
    THEN
        RAISE EXCEPTION 'Invalid limit %', p_limit;
    END IF;

    FOR v_job IN
        SELECT j.job_id
        FROM pl_loop_lab.jobs AS j
        WHERE j.status = 'pending'
        ORDER BY j.job_id
        FOR UPDATE SKIP LOCKED
        LIMIT p_limit
    LOOP
        UPDATE pl_loop_lab.jobs AS j
        SET status = 'processing',
            attempt_count = attempt_count + 1,
            updated_at = statement_timestamp()
        WHERE j.job_id = v_job.job_id
          AND j.status = 'pending';

        IF FOUND THEN
            INSERT INTO pl_loop_lab.job_events (
                job_id, event_type, event_note
            )
            VALUES (
                v_job.job_id,
                'claimed',
                'Claimed by demo procedure'
            );

            v_claimed := v_claimed + 1;
        END IF;
    END LOOP;

    RAISE NOTICE 'claimed=%', v_claimed;
END;
$$;
~~~

### 42.1. Thử trong transaction lab

~~~sql
BEGIN;

CALL pl_loop_lab.claim_pending_jobs(2);

SELECT job_id, status, attempt_count
FROM pl_loop_lab.jobs
ORDER BY job_id;

SELECT job_id, event_type
FROM pl_loop_lab.job_events
ORDER BY event_id;

ROLLBACK;
~~~

Lúc ROLLBACK, cập nhật trạng thái và sự kiện audit từ procedure trong transaction này được hoàn tác (sequence/identity counters có semantics riêng, không nhất thiết lùi như dữ liệu transactional).

### 42.2. Ý nghĩa của SKIP LOCKED

`FOR UPDATE SKIP LOCKED` bỏ qua các rows đang bị khóa bởi transaction khác thay vì chờ chúng. Nó hữu ích cho **queue-like workflows** với nhiều consumers, nhưng:

- Không cho kết quả nhất quán “toàn bộ pending jobs” như một report.
- Có thể bỏ qua hàng đang bị khóa, kể cả job ID nhỏ hơn.
- Cần thiết kế fairness/retry/timeout.
- Kết quả chịu ảnh hưởng các transaction đồng thời.
- Không tự bảo đảm exactly-once side effects ở hệ thống ngoài DB.

### 42.3. Procedure claim không tự COMMIT

Trong ví dụ này, procedure chỉ UPDATE và INSERT; transaction do caller kiểm soát. Điều này thuận tiện khi service muốn commit claim như một thao tác atomic.

## 43. LIMIT với FOR query và rủi ro trùng xử lý

Không khóa:

~~~sql
SELECT job_id
FROM pl_loop_lab.jobs
WHERE status = 'pending'
ORDER BY job_id
LIMIT 5;
~~~

hai workers có thể cùng nhìn thấy một tập jobs, rồi đều cố xử lý. Vòng `FOR` không tự ngăn điều đó.

Các giải pháp tùy bài toán:

- Lock row với `FOR UPDATE SKIP LOCKED` trong transaction ngắn.
- Atomic claim bằng `UPDATE ... WHERE ... RETURNING`.
- Dùng unique/idempotency keys cho kết quả công việc.
- Timeout/reclaim jobs bị treo.
- Bảo vệ side effects ngoài DB bằng cơ chế idempotency/outbox.

Không coi việc lặp tuần tự trong **một process** là bảo đảm tuần tự trên **toàn bộ hệ thống** có nhiều connections.

## 44. Thay FOR từng row bằng UPDATE set-based

Nếu yêu cầu chỉ là “đánh dấu tối đa 2 job pending thành processing” và không cần logic riêng từng hàng, có thể dùng SQL theo tập:

~~~sql
WITH candidates AS (
    SELECT j.job_id
    FROM pl_loop_lab.jobs AS j
    WHERE j.status = 'pending'
    ORDER BY j.job_id
    FOR UPDATE SKIP LOCKED
    LIMIT 2
)
UPDATE pl_loop_lab.jobs AS target
SET status = 'processing',
    attempt_count = target.attempt_count + 1,
    updated_at = statement_timestamp()
FROM candidates AS c
WHERE target.job_id = c.job_id
RETURNING
    target.job_id,
    target.status,
    target.attempt_count;
~~~

Đây là một statement atomic phù hợp cho bước claim, thường giảm overhead so với PL/pgSQL loop nếu không có việc xử lý riêng từng hàng.

### 44.1. Kết hợp dữ liệu trả về để ghi audit

Trong những workflow phù hợp, có thể dùng `UPDATE ... RETURNING` làm nguồn cho một `INSERT` trong cùng câu lệnh hoặc một transaction. Không phải lúc nào loop là cách tốt nhất để nối các bước DML.

### 44.2. Cân nhắc isolation và transactions

Atomic SQL statement không có nghĩa toàn bộ workflow bên ngoài DB là exactly-once. Sau khi claim, worker có thể crash; cần thiết kế cơ chế retry/reclaim và xử lý idempotent.

## 45. Đếm số lượt và ngắt batch có chủ đích

Nếu trong mỗi lượt cần làm nhiều bước khác nhau, có thể lưu biến số lượt:

~~~sql
DO $$
DECLARE
    v_processed INTEGER := 0;
    v_job RECORD;
BEGIN
    FOR v_job IN
        SELECT job_id
        FROM pl_loop_lab.jobs
        WHERE status = 'pending'
        ORDER BY job_id
    LOOP
        EXIT WHEN v_processed >= 3;

        RAISE NOTICE 'would process %', v_job.job_id;
        v_processed := v_processed + 1;
    END LOOP;

    RAISE NOTICE
        'processed=%',
        v_processed;
END;
$$;
~~~

Nhưng câu SELECT bên trong vẫn có thể cần lấy/đánh giá tập kết quả trước khi EXIT. Khi đã biết giới hạn, **đưa LIMIT vào SQL** thường giúp giảm công việc:

~~~sql
SELECT job_id
FROM pl_loop_lab.jobs
WHERE status = 'pending'
ORDER BY job_id
LIMIT 3;
~~~

## 46. WHILE để xử lý theo từng batch

Một pattern khái niệm:

~~~text
WHILE còn công việc và chưa vượt ngưỡng
    |
    +--> Claim tối đa batch_size jobs
    |
    +--> Kiểm tra số đã claim
    |
    +--> Nếu 0: EXIT
    |
    +--> Xử lý / ghi kết quả
    |
    +--> Tiếp tục lượt sau
~~~

Có thể dùng `LOOP ... EXIT WHEN v_count = 0` thay WHILE khi điều kiện dừng chỉ biết **sau** khi chạy batch SQL.

### 46.1. Đừng “poll” queue không giới hạn trong một transaction

Một loop liên tục kiểm tra bảng khi chưa có công việc có thể gây busy waiting, giữ connection/transaction và làm tăng CPU. Với polling jobs, thường nên điều phối ở application/service scheduler, có backoff và transaction ngắn.

### 46.2. Không gọi pg_sleep để thay kiến trúc queue

`pg_sleep` có thể phục vụ test hoặc backoff nhỏ có chủ đích, nhưng giữ backend connection trong khi chờ. Không mặc định vòng lặp vô hạn kèm pg_sleep trong function là hàng đợi production lành mạnh.

## 47. Procedure có COMMIT từng lượt: ranh giới quan trọng

Khác với function, một procedure có thể điều khiển transaction ở **ngữ cảnh CALL được phép**.

Ví dụ để minh họa cú pháp với số lượt rất nhỏ:

~~~sql
CREATE PROCEDURE pl_loop_lab.write_demo_events(
    IN p_batches INTEGER
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_batches IS NULL
       OR p_batches < 1
       OR p_batches > 3
    THEN
        RAISE EXCEPTION
            'Invalid batch count %',
            p_batches;
    END IF;

    FOR batch_no IN 1..p_batches LOOP
        INSERT INTO pl_loop_lab.job_events (
            job_id, event_type, event_note
        )
        VALUES (
            1,
            'demo_commit',
            format('batch %s', batch_no)
        );

        COMMIT;
    END LOOP;
END;
$$;
~~~

Gọi ở **top-level**, không nằm trong explicit transaction block:

~~~sql
CALL pl_loop_lab.write_demo_events(2);
~~~

### 47.1. Không gọi trong BEGIN ... COMMIT của caller

~~~sql
-- Minh họa trường hợp không phù hợp:
BEGIN;

CALL pl_loop_lab.write_demo_events(2);

COMMIT;
~~~

Procedure chứa `COMMIT` nội bộ bị giới hạn khi caller đang trong explicit transaction block. Với JDBC/Spring, hãy kiểm tra autocommit và `@Transactional`.

### 47.2. COMMIT không “hủy bỏ” các lượt trước

Nếu batch 1 đã COMMIT và batch 2 gặp lỗi, batch 1 không tự rollback. Thiết kế idempotency và checkpoint nếu partial commits được phép.

### 47.3. Không COMMIT trong EXCEPTION block

Một block PL/pgSQL có `EXCEPTION` sử dụng cơ chế subtransaction; không cố kết thúc transaction trong block đang xử lý ngoại lệ. Các hạn chế khác còn liên quan `SECURITY DEFINER` và procedure có `SET` clause trong định nghĩa.

## 48. Function có vòng lặp không được tự COMMIT

Một function có thể lặp và thực hiện DML, nhưng không được thực hiện lệnh kết thúc transaction bên trong:

~~~sql
-- KHÔNG làm trong CREATE FUNCTION:
-- LOOP
--     UPDATE ...;
--     COMMIT;
-- END LOOP;
~~~

Function chạy trong transaction của caller/statement. Nếu cần chia commit giữa các batches:

- Chuyển orchestration ra application, gọi nhiều transactions.
- Hoặc dùng procedure top-level được phép transaction control, với retry/partial commit policy rõ.
- Không lách bằng dynamic SQL để nhúng COMMIT vào function.

## 49. Exception handling bên trong vòng lặp

PL/pgSQL cho phép xử lý lỗi trong khối `BEGIN ... EXCEPTION ... END`.

Ví dụ một demo có chủ đích lưu ý từng phần tử:

~~~sql
DO $$
DECLARE
    v_text TEXT;
    v_integer INTEGER;
BEGIN
    FOREACH v_text IN ARRAY
        ARRAY['10','oops','20']
    LOOP
        BEGIN
            v_integer := v_text::INTEGER;
            RAISE NOTICE 'parsed=%', v_integer;
        EXCEPTION
            WHEN INVALID_TEXT_REPRESENTATION THEN
                RAISE NOTICE
                    'skipped invalid integer: %',
                    v_text;
        END;
    END LOOP;
END;
$$;
~~~

Kết quả logic: parse được 10, bỏ `oops`, parse được 20.

### 49.1. Subtransaction có chi phí

Khi một `EXCEPTION` block bắt lỗi, các thay đổi dữ liệu bên trong phần block bị rollback theo semantics subtransaction, còn một số biến trong PL/pgSQL có quy tắc riêng. Việc tạo exception block cho **mọi row** của batch lớn có thể có overhead đáng kể.

### 49.2. Đừng nuốt mọi lỗi

~~~sql
EXCEPTION WHEN OTHERS THEN
    NULL;
~~~

là anti-pattern nếu làm mất lỗi constraint, permission, deadlock hay dữ liệu sai. Chỉ bắt các loại lỗi có chính sách xử lý xác định, log đủ context không nhạy cảm và cân nhắc báo lại lỗi.

## 50. RAISE NOTICE, WARNING và EXCEPTION

Trong vòng lặp:

~~~sql
RAISE NOTICE 'job=%', v_job_id;
~~~

thường phù hợp demo hoặc instrumentation có giới hạn.

- `RAISE NOTICE`: thông báo; không làm statement tự thất bại.
- `RAISE WARNING`: cảnh báo.
- `RAISE EXCEPTION`: phát sinh lỗi, làm thay đổi control flow trừ khi bị bắt.

### 50.1. Logging mỗi hàng có thể rất tốn tài nguyên

Với hàng triệu lượt, phát hàng triệu notices/logs có thể chiếm CPU, disk và làm client chậm. Chỉ log theo batch hoặc những trạng thái quan trọng; thu thập metrics tổng hợp thay cho việc in từng row trong production.

## 51. ASSERT và giới hạn vòng lặp

PL/pgSQL hỗ trợ `ASSERT` trong những ngữ cảnh thích hợp, dùng cho kiểm tra giả định phát triển:

~~~sql
DO $$
DECLARE
    v_counter INTEGER := 3;
BEGIN
    ASSERT v_counter >= 0,
        'Counter should be nonnegative';
END;
$$;
~~~

Việc `ASSERT` có được kiểm tra hay không còn tùy cấu hình `plpgsql.check_asserts`.

**Không dùng ASSERT thay validation nghiệp vụ bắt buộc**, đặc biệt khi cấu hình có thể vô hiệu hóa kiểm tra. Dùng `IF ... THEN RAISE EXCEPTION` và database constraints cho những điều kiện phải luôn được áp dụng.

## 52. Timeout, statement_timeout và resource safety

Một vòng lặp bị lỗi có thể chạy quá lâu. PostgreSQL có `statement_timeout` và những GUC khác phục vụ giới hạn thời gian.

Trong một session lab:

~~~sql
BEGIN;

SET LOCAL statement_timeout = '5s';

DO $$
DECLARE
    v_count INTEGER := 0;
BEGIN
    WHILE v_count < 1000 LOOP
        v_count := v_count + 1;
    END LOOP;
END;
$$;

ROLLBACK;
~~~

Đây là ví dụ có vòng lặp kết thúc; timeout chỉ là lớp bảo vệ bổ sung.

### 52.1. Không xem statement_timeout là thuật toán dừng

Vòng lặp phải có logic dừng rõ. Timeout chỉ giúp hủy request khi vượt hạn mức; không tự bảo đảm giao dịch/data consistency ở mức workflow sau khi đã có partial commits.

### 52.2. Ràng buộc input là tuyến phòng thủ quan trọng

Trong function/procedure công khai, giới hạn:

- Số lượt tối đa.
- Số records tối đa.
- Kích thước array.
- Thời gian dự kiến.
- Độ sâu nested loops.
- Số lần retry.
- Phạm vi rows được phép sửa.

## 53. CONTINUE WHEN với nhiều điều kiện

Ví dụ bỏ các hàng không thỏa validation:

~~~sql
DO $$
DECLARE
    v_job RECORD;
BEGIN
    FOR v_job IN
        SELECT
            job_id,
            status,
            attempt_count
        FROM pl_loop_lab.jobs
        ORDER BY job_id
    LOOP
        CONTINUE WHEN v_job.status <> 'pending';
        CONTINUE WHEN v_job.attempt_count >= 3;

        RAISE NOTICE
            'eligible job=%',
            v_job.job_id;
    END LOOP;
END;
$$;
~~~

Nếu điều kiện lọc có thể diễn đạt trong SQL, gọn và hiệu quả hơn:

~~~sql
SELECT job_id
FROM pl_loop_lab.jobs
WHERE status = 'pending'
  AND attempt_count < 3
ORDER BY job_id;
~~~

Vòng lặp chỉ đáng dùng khi cần **logic riêng cho từng hàng sau filter**, không chỉ để lặp lại điều kiện WHERE.

## 54. EXIT WHEN điều kiện nhận NULL

`EXIT WHEN boolean_expression` chỉ thoát khi kết quả **TRUE**. Nếu kết quả FALSE hoặc NULL thì không thoát.

~~~sql
DO $$
DECLARE
    v_flag BOOLEAN := NULL;
    v_attempt INTEGER := 0;
BEGIN
    LOOP
        v_attempt := v_attempt + 1;

        EXIT WHEN v_flag;
        EXIT WHEN v_attempt >= 3;
    END LOOP;

    RAISE NOTICE
        'attempts=%',
        v_attempt;
END;
$$;
~~~

Điều kiện `v_flag` NULL không khiến EXIT; bộ chặn 3 lượt mới dừng.

### 54.1. Hãy biểu diễn NULL semantics rõ

Nếu muốn NULL cũng khiến thoát, có thể dùng:

~~~sql
EXIT WHEN v_flag IS NOT TRUE;
~~~

Nếu muốn chỉ thoát khi FALSE mà không thoát ở NULL:

~~~sql
EXIT WHEN v_flag IS FALSE;
~~~

`IS TRUE`/`IS FALSE`/`IS NOT TRUE` thường dễ hiểu hơn khi Boolean có thể NULL.

## 55. Biến đếm và tránh overflow

`INTEGER` có phạm vi giới hạn. Với vòng lặp có thể tích lũy số lượt rất lớn, dùng `BIGINT` cho counter hoặc giới hạn số lượt chặt.

~~~sql
DECLARE
    v_processed BIGINT := 0;
~~~

Nếu mỗi lượt tăng counter không kiểm soát, phép cộng có thể vượt kiểu và làm statement lỗi. Với batch production nên đặt giới hạn thực tế nhỏ hơn nhiều so với giới hạn của BIGINT.

### 55.1. Không dùng sequence như loop counter bình thường

`nextval` thay trạng thái sequence không được rollback theo cùng cách dữ liệu transactional. Nếu chỉ cần đếm số lượt trong procedure, dùng biến PL/pgSQL.

## 56. FOREACH với mảng nhiều chiều và NULL

Một mảng SQL nhiều chiều:

~~~sql
DO $$
DECLARE
    v_value INTEGER;
BEGIN
    FOREACH v_value IN ARRAY
        ARRAY[
            [1, NULL],
            [3, 4]
        ]::INTEGER[][]
    LOOP
        IF v_value IS NULL THEN
            RAISE NOTICE 'null element';
        ELSE
            RAISE NOTICE 'value=%', v_value;
        END IF;
    END LOOP;
END;
$$;
~~~

Nếu không dùng `SLICE`, FOREACH đi qua các **phần tử scalar** theo cách PostgreSQL duyệt SQL array.

### 56.1. SLICE 1 để lấy hàng con

~~~sql
DO $$
DECLARE
    v_slice INTEGER[];
BEGIN
    FOREACH v_slice SLICE 1 IN ARRAY
        ARRAY[
            [1, 2],
            [3, 4]
        ]::INTEGER[][]
    LOOP
        RAISE NOTICE 'slice=%', v_slice;
    END LOOP;
END;
$$;
~~~

`v_slice` là `INTEGER[]`; nếu dùng biến INTEGER scalar làm target cho SLICE 1 thì không khớp kiểu.

## 57. Vòng lặp trên arrays và ANY/ALL

Nếu chỉ cần kiểm tra một giá trị có nằm trong array không:

~~~sql
SELECT
    20 = ANY(ARRAY[10,20,30]) AS contains_20;
~~~

Nếu chỉ cần kiểm tra mọi phần tử có dương:

~~~sql
SELECT
    0 < ALL(ARRAY[1,2,3]) AS all_positive;
~~~

Những biểu thức này thường đơn giản hơn FOREACH + biến Boolean + EXIT.

### 57.1. NULL trong ANY/ALL

Khi array chứa NULL, kết quả của `ANY`/`ALL` có thể là NULL tùy toán tử và các phần tử còn lại. Phải hiểu SQL three-valued logic, không luôn coi kết quả chưa xác định là FALSE.

### 57.2. Khi FOREACH vẫn hữu ích

Nếu mỗi phần tử cần transform phức tạp hoặc cần xây một kết quả phụ thuộc thứ tự, FOREACH có thể diễn đạt rõ hơn. Nhưng hãy cân nhắc `unnest`, `array_agg` và các hàm mảng SQL trước khi viết loop.

## 58. FOR với generate_series

Với tác vụ chỉ tạo một dải dữ liệu, SQL:

~~~sql
SELECT g AS number
FROM generate_series(1, 10) AS g
ORDER BY g;
~~~

thường đủ, không cần vòng lặp.

Nếu cần duyệt các hàng do `generate_series` sinh ra:

~~~sql
DO $$
DECLARE
    v_num INTEGER;
BEGIN
    FOR v_num IN
        SELECT g
        FROM generate_series(1, 5) AS g
    LOOP
        RAISE NOTICE 'n=%', v_num;
    END LOOP;
END;
$$;
~~~

### 58.1. Khác FOR integer thế nào?

- `FOR i IN 1..5` là integer range loop PL/pgSQL.
- `FOR i IN SELECT g FROM generate_series(...)` là query FOR.
- `generate_series` có khả năng kết hợp cùng SQL set-based, JOIN và INSERT ... SELECT.

## 59. FOR với timestamp range

Integer FOR chỉ hỗ trợ dải số nguyên theo cú pháp `lower..upper`. Nếu muốn lặp theo ngày, có thể dùng query FOR trên `generate_series`:

~~~sql
DO $$
DECLARE
    v_day DATE;
BEGIN
    FOR v_day IN
        SELECT d::DATE
        FROM generate_series(
            DATE '2026-11-01',
            DATE '2026-11-05',
            INTERVAL '1 day'
        ) AS d
    LOOP
        RAISE NOTICE 'day=%', v_day;
    END LOOP;
END;
$$;
~~~

Đối với timestamps/time zones, phải cân nhắc DST và kiểu thời gian nếu logic lịch là quan trọng. Ví dụ trên dùng DATE và ngày cố định để minh họa, không giải quyết mọi calendar edge case.

## 60. Loop ở trigger function

Một trigger function có thể chứa vòng lặp, nhưng nhiều trường hợp không nên lặp từng row khi một SQL set-based đủ.

Ví dụ trigger được gọi một lần trên mỗi hàng có thể đã chạy rất nhiều lần khi bulk import. Nếu bên trong trigger lại duyệt nhiều rows, chi phí có thể tăng đột biến.

### 60.1. Bảo vệ khỏi đệ quy không chủ ý

Trigger cập nhật chính bảng đã kích hoạt nó có thể kích hoạt trigger thêm lần nữa. Kết hợp vòng lặp với trigger recursion có thể gây chain khó kiểm soát.

Cân nhắc:

- Statement-level triggers/transition tables khi phù hợp.
- Cơ chế kiểm soát update nhằm tránh self-recursion.
- Giới hạn độ phức tạp trong trigger.
- Đo hiệu năng bulk DML.

Không biến trigger thành một process engine chạy vô hạn.

## 61. Lặp và transaction isolation

Query FOR đọc dữ liệu trong transaction theo isolation/snapshot semantics. Khi một transaction khác sửa các rows, kết quả quan sát được phụ thuộc:

- `READ COMMITTED`/`REPEATABLE READ`/`SERIALIZABLE`.
- Snapshot của từng statement.
- Row-level locks.
- `FOR UPDATE` và các lock variants.
- Việc routine thực hiện SQL statements sau đó.
- Transaction boundaries do caller/procedure quản lý.

### 61.1. Không giả định một SELECT loop thấy mọi thay đổi mới

Một query FOR duyệt kết quả của một câu SELECT không phải cơ chế streaming subscription tự động nhận rows mới được INSERT bởi transaction khác giữa lúc loop đang chạy.

Nếu cần xử lý tác vụ mới liên tục, thiết kế polling/claim thành các transactions hoặc statements riêng.

### 61.2. Vòng lặp không tự bảo đảm exactly-once

Khi transaction có thể rollback hoặc worker crash, logic idempotent và state machine của job mới quyết định khả năng retry an toàn.

## 62. Deadlock khi nhiều loops cập nhật rows khác thứ tự

Hai workers đều cập nhật hai rows nhưng theo thứ tự ngược nhau:

~~~text
Worker A: khóa job 1 -> chờ job 2
Worker B: khóa job 2 -> chờ job 1
~~~

có thể tạo deadlock.

Biện pháp:

- Thống nhất thứ tự khóa, ví dụ `ORDER BY job_id` khi claim.
- Giữ transaction ngắn.
- Tránh khóa nhiều bảng theo thứ tự khác nhau.
- Thử lại transaction khi gặp deadlock theo retry policy.
- Dùng set-based DML và chiến lược locking phù hợp.

Không thể loại bỏ mọi deadlock chỉ bằng FOR có ORDER BY; cần xem thực tế plan/locking và toàn bộ workflow.

## 63. Performance: loop từng row hay SQL theo tập?

Ví dụ xử lý tất cả pending jobs:

**Row-by-row PL/pgSQL:**

~~~sql
DO $$
DECLARE
    v_job RECORD;
BEGIN
    FOR v_job IN
        SELECT job_id
        FROM pl_loop_lab.jobs
        WHERE status = 'pending'
    LOOP
        UPDATE pl_loop_lab.jobs
        SET attempt_count = attempt_count + 1
        WHERE job_id = v_job.job_id;
    END LOOP;
END;
$$;
~~~

**Set-based SQL:**

~~~sql
UPDATE pl_loop_lab.jobs
SET attempt_count = attempt_count + 1
WHERE status = 'pending';
~~~

Cả hai ví dụ **làm thay đổi dữ liệu thật**; không chạy liên tiếp nếu muốn cùng kết quả.

### 63.1. Vì sao set-based thường tốt hơn?

- Ít lần thực thi SQL statement.
- Planner tối ưu một tập hàng.
- Giảm overhead PL/pgSQL ↔ SQL engine cho từng row.
- Thường giảm lock duration và công việc không cần thiết khi thiết kế tốt.
- Code ngắn, dễ audit.

Dù vậy, với logic mỗi row có nhiều bước hoặc side effects riêng, loop có thể dễ diễn đạt hơn. Hãy đo trên workload đại diện.

## 64. Những chỉ số cần đo khi dùng loops

Dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT job_id
FROM pl_loop_lab.jobs
WHERE status = 'pending'
ORDER BY job_id;
~~~

để xem query nguồn.

Với procedure/function có nhiều SQL statements bên trong, `EXPLAIN` của lời gọi bên ngoài không nhất thiết hiển thị chi tiết mọi internal query. Có thể cần instrumentation, tracing, `pg_stat_statements` và log ở mức phù hợp.

Các metric:

- Số iterations.
- Số rows được đọc/ghi.
- Latency mỗi batch và toàn workflow.
- CPU, I/O, WAL.
- Lock waits/deadlocks.
- Rows skipped vì khóa/validation.
- Số retries.
- Lỗi do input hoặc constraint.
- Memory và temp I/O.
- Thời gian transaction.

### 64.1. Đừng đo chỉ một lần

Cache, concurrency và phân bố dữ liệu có thể gây nhiễu. So set-based với loop trên cùng dataset và workload có kiểm soát, không tự kết luận từ một lần chạy.

## 65. Rủi ro N+1 queries bên trong FOR

Một query lấy N jobs, sau đó mỗi lượt chạy một SELECT mới:

~~~sql
FOR v_job IN
    SELECT job_id
    FROM pl_loop_lab.jobs
LOOP
    SELECT COUNT(*)
    INTO v_count
    FROM pl_loop_lab.job_events
    WHERE job_id = v_job.job_id;
END LOOP;
~~~

có thể thực hiện một query ban đầu và N queries phụ. Với số jobs lớn, overhead có thể đáng kể.

Cách SQL set-based:

~~~sql
SELECT
    j.job_id,
    COUNT(e.event_id) AS event_count
FROM pl_loop_lab.jobs AS j
LEFT JOIN pl_loop_lab.job_events AS e
    ON e.job_id = j.job_id
GROUP BY j.job_id
ORDER BY j.job_id;
~~~

Nếu muốn tối ưu hơn có thể cần index:

~~~sql
CREATE INDEX idx_job_events_job_id
ON pl_loop_lab.job_events(job_id);
~~~

Đây chỉ là gợi ý cho lab; index mới có chi phí ghi/lưu trữ và chỉ nên quyết định sau khi đo với dữ liệu thực.

## 66. Kiểm tra tính đúng khi dùng EXIT sớm

Giả sử loop chỉ xử lý tối đa 3 jobs nhưng query trả 5 jobs. Sau `EXIT`, hai jobs cuối sẽ không được xử lý. Đây có thể là yêu cầu batch hoặc một bug nếu code gọi routine tưởng rằng đã xử lý “tất cả”.

Nên đặt tên procedure, output metric và log theo ý nghĩa:

~~~text
claim_up_to_3_jobs  -> giới hạn rõ
process_all_jobs    -> cần chứng minh xử lý đầy đủ
~~~

Với batch API, có thể trả:

- Số rows đã claim.
- Có khả năng còn pending jobs không.
- Batch/cursor identifier.
- Trạng thái thành công hoặc lỗi.

Không gọi “SUCCESS xử lý tất cả” chỉ vì một vòng FOR đã kết thúc do EXIT.

## 67. Một vòng lặp có thể bị huỷ giữa chừng

Một query/function/procedure có thể bị cancel vì:

- Client hủy request.
- `statement_timeout`.
- Connection mất.
- Server shutdown/failover.
- Constraint/deadlock error.

Nếu toàn bộ loop nằm trong một transaction chưa COMMIT, các DML transactional chưa commit sẽ rollback khi transaction bị hủy phù hợp.

Nếu procedure đã COMMIT một số batches, những batches trước đó tồn tại sau lỗi. Vì vậy checkpoint, idempotency và restartability là phần của thiết kế batch, không chỉ cú pháp loop.

## 68. Debugging vòng lặp

Khi loop chạy sai số lượt, kiểm tra:

1. Giá trị ban đầu.
2. Kiểu biến và khả năng NULL.
3. Vị trí thay đổi biến điều khiển.
4. Điều kiện `EXIT WHEN`/`WHILE`.
5. Biên `FOR ... .. ...` và `BY`.
6. Scope của integer FOR variable.
7. Nhãn `EXIT/CONTINUE` có trỏ đúng loop.
8. Các câu `CONTINUE` bỏ qua update bắt buộc.
9. Query FOR có `WHERE`/`ORDER BY`/`LIMIT` đúng không.
10. Có query SQL khác ghi đè `FOUND` không.
11. Dữ liệu có thay đổi đồng thời hay bị lock skip.
12. Exception có bị bắt và nuốt không.

### 68.1. Instrumentation hữu hạn

~~~sql
RAISE NOTICE
    'iteration=% processed=%',
    v_iteration, v_processed;
~~~

Hạn chế bật mỗi row trên production. Cân nhắc logging theo mỗi 100/1000 lượt hoặc theo batch, với input/PII được loại bỏ.

## 69. Những lỗi cú pháp thường gặp

### 69.1. Quên END LOOP

~~~sql
FOR i IN 1..3 LOOP
    RAISE NOTICE '%', i;
-- Thiếu END LOOP;
~~~

Vòng lặp phải có `END LOOP;` và dấu chấm phẩy.

### 69.2. Dùng break thay EXIT

PL/pgSQL dùng `EXIT` chứ không dùng lệnh `break` của một số ngôn ngữ khác.

### 69.3. Dùng continue thay CONTINUE mà sai vị trí

`CONTINUE` chỉ có nghĩa trong loop thích hợp; không phải lệnh nhảy tùy ý trong function.

### 69.4. FOR với cú pháp như Java/Python

Không viết `for (i=0; i<5; i++)` hoặc `for i in range(5)`. PL/pgSQL có cú pháp `FOR i IN 1..5 LOOP`.

### 69.5. Gọi FOREACH trên jsonb

SQL array và JSONB array là hai kiểu khác nhau.

### 69.6. REVERSE nhưng đặt biên tăng

`REVERSE 1..5` không tạo ra dải 5 về 1 như mong muốn; đặt `REVERSE 5..1`.

### 69.7. BY 0 hoặc bước âm

Bước integer FOR phải dương; dùng REVERSE để đi lùi.

### 69.8. Thiếu khai báo RECORD cho query FOR

Khác integer FOR, target của query FOR cần một record/row variable hoặc danh sách biến hợp lệ.

### 69.9. Dynamic query nối raw input

Dễ SQL injection; dùng `format('%I')` cho identifiers và `USING` cho values.

### 69.10. Quên semicolon sau END LOOP

Dễ tạo lỗi cú pháp ở statement tiếp theo.

## 70. Những lỗi logic thường gặp

### 70.1. LOOP không EXIT

Gây loop vô hạn, giữ backend bận.

### 70.2. WHILE không cập nhật biến điều kiện

Ví dụ `WHILE i<10` mà không thay i; vòng lặp không dừng nếu trạng thái khác không thay.

### 70.3. EXIT WHEN gặp NULL

Chỉ TRUE khiến EXIT; cần xử lý NULL rõ.

### 70.4. Dùng EXIT thay CONTINUE

Làm bỏ toàn bộ phần tử còn lại thay vì chỉ bỏ một phần tử.

### 70.5. Dùng CONTINUE trước khi tăng counter

Bỏ lỡ cập nhật, có thể làm vòng lặp không đạt điều kiện dừng.

### 70.6. Dùng RETURN để thoát một loop nhưng còn việc sau loop

RETURN kết thúc function, phần code phía sau không chạy.

### 70.7. Nhầm FOUND từ một UPDATE với FOUND từ FOR

Nên lấy diagnostics kịp thời hoặc dùng biến riêng.

### 70.8. Tin FOR query có thứ tự tự nhiên

Cần ORDER BY nếu thứ tự quan trọng.

### 70.9. Tin loop trên pending rows ngăn race conditions

Cần transaction/locks/atomic claim.

### 70.10. Lặp N lần UPDATE thay vì một UPDATE theo tập

Có thể tăng overhead và lock contention.

### 70.11. FOREACH bỏ qua SQL NULL element semantics

Một phần tử NULL làm biểu thức Boolean hoặc phép cộng cho NULL nếu không xử lý.

### 70.12. Lặp array rỗng bằng array_lower/upper không kiểm tra

Biên có thể NULL; dùng FOREACH/generate_subscripts hoặc kiểm tra trước.

### 70.13. COMMIT bên trong function

Không được phép; phải quản lý transaction theo đúng loại routine.

### 70.14. COMMIT trong CALL có explicit transaction

Procedure transaction control bị giới hạn; không tự kết thúc transaction trong mọi ngữ cảnh.

### 70.15. Bắt WHEN OTHERS rồi bỏ qua

Che lỗi và gây trạng thái khó debug.

### 70.16. Tạo hàng triệu RAISE NOTICE

Tăng overhead/log volume.

### 70.17. Không giới hạn input p_count/p_array

Có thể tạo tải lớn hoặc DoS không mong muốn.

### 70.18. Dùng lock SKIP LOCKED nhưng báo “đã quét tất cả”

Nó có thể bỏ rows đang bị khóa.

### 70.19. Không có idempotency sau partial commits

Retry có thể xử lý/gửi ngoài hệ thống nhiều lần.

### 70.20. Vòng lặp trong trigger gọi lại chính trigger vô hạn

Cần thiết kế tránh recursion.

## 71. Quy tắc lựa chọn cấu trúc lặp

| Nhu cầu | Cấu trúc phù hợp |
|---|---|
| Lặp cho tới khi một điều kiện giữa lượt đúng | `LOOP` + `EXIT WHEN` |
| Điều kiện biết trước ở đầu mỗi lượt | `WHILE` |
| Lặp từ 1 tới 10 | `FOR i IN 1..10` |
| Lặp ngược 10, 8, 6, 4, 2 | `FOR i IN REVERSE 10..1 BY 2` |
| Duyệt hàng có sẵn trong SQL query | `FOR rec IN SELECT` |
| Query có tên bảng/cột phải dựng động | `FOR rec IN EXECUTE ... USING` |
| Duyệt SQL array | `FOREACH variable IN ARRAY` |
| Duyệt từng hàng con của SQL 2D array | `FOREACH slice SLICE 1 IN ARRAY` |
| Duyệt JSONB array | `FOR rec IN SELECT jsonb_array_elements(...)` |
| Bỏ phần tử hiện tại | `CONTINUE` |
| Thoát loop hiện tại | `EXIT` |
| Thoát loop ngoài từ loop trong | `EXIT outer_label` |
| Bỏ lượt loop ngoài | `CONTINUE outer_label` |
| Kết thúc function và trả scalar | `RETURN expression` |
| Sinh nhiều rows trong function | `RETURN NEXT` / `RETURN QUERY` |
| Chỉ đếm/tổng hợp/cập nhật hàng loạt | **SQL set-based** trước khi viết loop |

## 72. Một số mẹo viết loop dễ bảo trì

- Dùng prefix `p_` cho tham số, `v_` cho biến state và tên record có nghĩa.
- Giữ mỗi loop có **một mục đích** rõ ràng.
- Đặt điều kiện dừng gần thao tác liên quan.
- Thêm giới hạn input và số lượt khi có khả năng chạy lâu.
- Sử dụng label nếu có hai tầng lặp trở lên và có EXIT/CONTINUE xuyên tầng.
- Khi array cần index, dùng `generate_subscripts` hoặc ordinality thích hợp.
- Khi query result cần thứ tự, đặt `ORDER BY`.
- Dùng `GET DIAGNOSTICS ROW_COUNT` cho số rows DML.
- Nếu có DML, luôn xác định transaction owner và rollback semantics.
- Bảo vệ logic concurrency bằng constraints, locks và idempotency.
- Ưu tiên SQL set-based thay loop tính tổng hay cập nhật hàng loạt.
- Không gọi external side effect theo từng row trước khi có cơ chế bù trừ/retry phù hợp.

## 73. Bài tập thực hành

### Bài 1 — LOOP cơ bản

Viết DO block dùng `LOOP` in số từ 1 tới 5.

**Gợi ý:** biến counter, tăng mỗi lượt, `EXIT WHEN counter >= 5`.

### Bài 2 — Điều kiện dừng ở đầu

Tại sao LOOP kiểm tra EXIT ở đầu khác ở cuối khi trạng thái ban đầu đã đạt ngưỡng?

**Gợi ý:** kiểm tra cuối có thể cho chạy thân ít nhất một lần.

### Bài 3 — Vòng lặp vô hạn

Một LOOP không có EXIT/RETURN có nguy cơ gì?

**Gợi ý:** CPU, locks, timeout và log volume.

### Bài 4 — WHILE

Viết WHILE in các số chẵn từ 2 tới 10.

**Gợi ý:** biến bắt đầu từ 2 và cộng 2.

### Bài 5 — WHILE FALSE ngay từ đầu

`WHILE 10 < 5 LOOP` chạy mấy lượt?

**Gợi ý:** 0.

### Bài 6 — NULL Boolean

`WHILE NULL LOOP` có tiếp tục thực thi thân không?

**Gợi ý:** không, chỉ TRUE mới tiếp tục.

### Bài 7 — FOR integer

Viết FOR lặp từ 1 tới 10.

**Gợi ý:** `FOR i IN 1..10 LOOP`.

### Bài 8 — FOR ngược

In 5,4,3,2,1.

**Gợi ý:** `FOR i IN REVERSE 5..1 LOOP`.

### Bài 9 — BY

In 1,4,7,10.

**Gợi ý:** `FOR i IN 1..10 BY 3 LOOP`.

### Bài 10 — Biên tính một lần

Nếu upper bound của FOR là biến và thay biến bên trong thân, số lượt có tự thay không?

**Gợi ý:** không; integer FOR đánh giá bounds khi vào loop.

### Bài 11 — Scope

Đặt `i := 100` ngoài FOR, rồi dùng `FOR i IN 1..3`. Biến i ngoài loop còn mấy?

**Gợi ý:** 100.

### Bài 12 — CONTINUE

Chỉ in số lẻ trong dải 1..9.

**Gợi ý:** `CONTINUE WHEN i % 2 = 0`.

### Bài 13 — EXIT

In số 1..4 rồi kết thúc FOR 1..10.

**Gợi ý:** `EXIT WHEN i > 4`.

### Bài 14 — RETURN vs EXIT

Nếu sau `END LOOP` còn phải trả thống kê, nên dùng EXIT hay RETURN trong loop?

**Gợi ý:** EXIT.

### Bài 15 — Nhãn outer

Thoát hai vòng lặp lồng nhau khi i=2 và j=2.

**Gợi ý:** `<<outer_loop>>` và `EXIT outer_loop WHEN ...`.

### Bài 16 — Continue outer

Bỏ tất cả item còn lại của customer hiện tại, chuyển sang customer kế.

**Gợi ý:** `CONTINUE customer_loop`.

### Bài 17 — Query FOR

Duyệt `job_id` các jobs pending trong bảng lab.

**Gợi ý:** `FOR r IN SELECT ... LOOP`.

### Bài 18 — Record

Tại sao cần biến `RECORD` hoặc row variable trong query FOR?

**Gợi ý:** chứa cấu trúc một row do SELECT trả.

### Bài 19 — %ROWTYPE

Viết biến cho toàn hàng `pl_loop_lab.jobs`.

**Gợi ý:** `v_job pl_loop_lab.jobs%ROWTYPE;`.

### Bài 20 — ORDER BY

Có bảo đảm query FOR đọc jobs theo job_id nếu SELECT không ORDER BY?

**Gợi ý:** không.

### Bài 21 — Query rỗng

FOR query trả 0 rows thì phần thân chạy mấy lần?

**Gợi ý:** 0.

### Bài 22 — FOUND

Sau FOR, dùng gì để biết loop có ít nhất một lượt?

**Gợi ý:** `FOUND`, nhưng đọc ngay vì SQL khác có thể thay nó.

### Bài 23 — ROW_COUNT

Lấy số rows vừa UPDATE trong procedure.

**Gợi ý:** `GET DIAGNOSTICS v_count = ROW_COUNT`.

### Bài 24 — EXECUTE USING

Tại sao dùng `USING` thay việc nối dữ liệu text vào dynamic SQL?

**Gợi ý:** parameter binding và an toàn.

### Bài 25 — Dynamic identifier

Muốn dựng tên bảng có nguồn tin cậy được kiểm soát, dùng gì?

**Gợi ý:** whitelist và `format('%I', identifier)`.

### Bài 26 — Cursor

FETCH cursor tới cuối dữ liệu thì kết hợp điều kiện dừng nào?

**Gợi ý:** `EXIT WHEN NOT FOUND`.

### Bài 27 — FOREACH

In từng phần tử của `ARRAY[10,20,30]`.

**Gợi ý:** `FOREACH v IN ARRAY ... LOOP`.

### Bài 28 — NULL element

Cộng từng phần tử array có NULL mà không COALESCE có nguy cơ gì?

**Gợi ý:** tổng trở thành NULL.

### Bài 29 — SLICE 1

Duyệt từng mảng con một chiều trong SQL array hai chiều.

**Gợi ý:** `FOREACH v_slice SLICE 1 IN ARRAY ...`.

### Bài 30 — SQL array vs JSON array

Có dùng FOREACH trực tiếp trên `'[1,2]'::jsonb` được không?

**Gợi ý:** không; query với jsonb_array_elements hoặc chuyển kiểu hợp lệ.

### Bài 31 — generate_subscripts

Lấy index của SQL array ngay cả khi array rỗng.

**Gợi ý:** `generate_subscripts(array, 1)`.

### Bài 32 — RETURN NEXT

`RETURN NEXT` có kết thúc loop không?

**Gợi ý:** không; nó thêm một phần tử vào set-returning result.

### Bài 33 — RETURN QUERY

Khi cần trả tất cả pending jobs từ SELECT, có nên loop RETURN NEXT từng row không?

**Gợi ý:** cân nhắc RETURN QUERY/set-based.

### Bài 34 — Batch LIMIT

Nếu chỉ cần 5 jobs, nên `EXIT` sau 5 hàng hay `LIMIT 5` ngay trong SQL?

**Gợi ý:** LIMIT thường giảm công việc nguồn.

### Bài 35 — Concurrency

Hai workers cùng chọn pending jobs không khóa có thể gặp gì?

**Gợi ý:** trùng claim/race.

### Bài 36 — SKIP LOCKED

`SKIP LOCKED` có bảo đảm quét tất cả pending jobs không?

**Gợi ý:** không; có thể bỏ hàng đang khóa.

### Bài 37 — Set-based UPDATE

Viết một câu UPDATE tăng attempt_count cho toàn bộ pending jobs thay loop.

**Gợi ý:** `UPDATE ... SET attempt_count=attempt_count+1 WHERE status='pending'`.

### Bài 38 — Procedure COMMIT

Procedure có COMMIT trong loop có được gọi trong explicit `BEGIN ... COMMIT` không?

**Gợi ý:** transaction control bị giới hạn, có thể lỗi.

### Bài 39 — Exception

Một phần tử không cast được thành INTEGER, có thể dùng block nào để bỏ qua theo chính sách?

**Gợi ý:** BEGIN ... EXCEPTION WHEN INVALID_TEXT_REPRESENTATION ... END.

### Bài 40 — Không nuốt lỗi

Vì sao `EXCEPTION WHEN OTHERS THEN NULL` nguy hiểm?

**Gợi ý:** che lỗi constraint/permission/dữ liệu.

### Bài 41 — Timeout

`statement_timeout` có thay thế điều kiện dừng vòng lặp không?

**Gợi ý:** không, chỉ là lớp bảo vệ.

### Bài 42 — Boolean NULL

Muốn EXIT nếu Boolean FALSE **hoặc NULL**, viết thế nào?

**Gợi ý:** `EXIT WHEN v_flag IS NOT TRUE`.

### Bài 43 — COUNT(*) vs loop

Để đếm pending jobs, chọn COUNT(*) hay FOR duyệt từng row?

**Gợi ý:** COUNT(*) nếu không cần thao tác riêng từng row.

### Bài 44 — N+1

FOR mỗi job rồi COUNT job_events từng lần có nhược điểm gì?

**Gợi ý:** nhiều query nội bộ; thay bằng JOIN/GROUP BY.

### Bài 45 — Retry sau partial commits

Tại sao batch procedure COMMIT mỗi lượt cần idempotency key/checkpoint?

**Gợi ý:** các batches trước không tự rollback nếu batch sau thất bại.

## 74. Câu hỏi thường gặp

### LOOP và WHILE khác nhau quan trọng nhất ở đâu?

`LOOP` không tự có điều kiện đầu, cần `EXIT`/`RETURN`/lỗi để dừng. `WHILE` kiểm tra điều kiện trước mỗi lượt, chỉ chạy khi TRUE.

### FOR integer có cần khai báo biến i không?

Không nhất thiết. PostgreSQL tạo biến integer loop variable có scope riêng cho integer FOR. Query FOR lại cần target row/record hoặc danh sách biến đích phù hợp.

### FOR i IN 1..5 có chạy 5 không?

Có. Dải bao gồm cả hai biên khi hướng/bước cho phép.

### Muốn đếm ngược dùng BY -1 có được không?

Không nên. Dùng `REVERSE` với bước dương, ví dụ `FOR i IN REVERSE 5..1 LOOP`.

### Bound của integer FOR có thay mỗi lượt không?

Không; các biểu thức bound/step được đánh giá khi vào vòng lặp. Dùng WHILE nếu cần đánh giá trạng thái thay đổi mỗi lượt.

### CONTINUE có kết thúc loop không?

Không. Nó bỏ phần còn lại của lượt và chuyển sang lượt tiếp theo.

### Có thể thoát hai vòng lặp lồng nhau bằng một lệnh không?

Có. Dùng label và `EXIT outer_loop`.

### FOUND có giữ trạng thái của FOR khi có UPDATE trong thân không?

`FOUND` có thể bị SQL statements trong thân cập nhật. Trạng thái FOR được đặt sau khi loop kết thúc; đọc đúng thời điểm hoặc dùng biến đếm riêng.

### FOREACH có dùng trực tiếp với JSONB array không?

Không. `FOREACH ... IN ARRAY` dành cho SQL arrays. Với JSONB, dùng `jsonb_array_elements` trong query FOR hoặc chuyển kiểu.

### FOREACH SLICE 1 nghĩa là gì?

Mỗi lượt nhận một SQL array con một chiều từ một SQL array nhiều chiều, thay vì phần tử scalar.

### Vòng lặp có nhanh hơn một câu UPDATE không?

Không mặc định. Với update hàng loạt đơn giản, SQL set-based thường ít overhead hơn. Loop phù hợp khi thực sự cần control flow theo từng hàng.

### Procedure có thể COMMIT mỗi lượt nhưng function không?

Đúng trong **những ngữ cảnh CALL được PostgreSQL cho phép**. Procedure có COMMIT không thể tùy ý được gọi trong explicit transaction hoặc một số loại procedure/block bị giới hạn.

### Dùng FOR UPDATE SKIP LOCKED có bảo đảm exactly-once không?

Không. Nó giúp nhiều workers claim các rows đang mở khóa theo một cơ chế queue-like, nhưng retry, crash, external effects và idempotency vẫn cần thiết kế riêng.

### Khi lỗi trong một lượt, có thể tiếp tục lượt sau không?

Có thể bắt những exception phù hợp bằng block `BEGIN ... EXCEPTION ... END`, nhưng phải hiểu subtransaction và overhead; không nên nuốt mọi lỗi.

### Có nên log mỗi lượt bằng RAISE NOTICE trên production không?

Thông thường không. Nên đo count/latency/error theo batch và chỉ log những sự kiện quan trọng, tránh làm tăng CPU/log volume.

## 75. Tổng kết

Những cấu trúc PL/pgSQL cần ghi nhớ:

~~~sql
-- Vòng tổng quát:
LOOP
    ...
    EXIT WHEN condition;
END LOOP;

-- Vòng kiểm tra điều kiện đầu:
WHILE condition LOOP
    ...
END LOOP;

-- Vòng số nguyên:
FOR i IN 1..10 BY 2 LOOP
    ...
END LOOP;

-- Vòng số nguyên giảm:
FOR i IN REVERSE 10..1 BY 2 LOOP
    ...
END LOOP;

-- Vòng duyệt query:
FOR rec IN SELECT ... LOOP
    ...
END LOOP;

-- Vòng SQL động:
FOR rec IN EXECUTE sql_text USING value LOOP
    ...
END LOOP;

-- Vòng duyệt SQL array:
FOREACH element IN ARRAY some_sql_array LOOP
    ...
END LOOP;

-- Vòng duyệt slice mảng:
FOREACH slice SLICE 1 IN ARRAY multidim_array LOOP
    ...
END LOOP;

-- Bỏ một lượt:
CONTINUE WHEN skip_condition;

-- Thoát một vòng:
EXIT WHEN stop_condition;

-- Thoát vòng ngoài:
EXIT outer_loop;

-- Sang lượt mới của vòng ngoài:
CONTINUE outer_loop;
~~~

Các nguyên tắc thực hành:

1. **LOOP** linh hoạt, nhưng bắt buộc thiết kế điều kiện dừng rõ ràng.
2. **WHILE** thích hợp khi điều kiện tiếp tục được kiểm tra trước từng lượt.
3. **FOR integer** duyệt dải có biên, hỗ trợ `REVERSE` và bước dương `BY`; các biên được đánh giá một lần lúc bắt đầu.
4. **FOR query** duyệt các hàng SQL, dùng `RECORD`/`%ROWTYPE`/danh sách biến phù hợp và `ORDER BY` nếu thứ tự quan trọng.
5. **FOR EXECUTE** phục vụ SQL động; sử dụng `USING` cho values và `format('%I')`/whitelist cho identifiers.
6. **FOREACH** dành cho SQL arrays; với JSONB arrays dùng `jsonb_array_elements`, không nhầm hai kiểu.
7. **WITH ORDINALITY/generate_subscripts** hữu ích khi cần vị trí phần tử.
8. **CONTINUE** bỏ lượt, **EXIT** thoát loop, còn **RETURN** kết thúc function/routine theo hợp đồng; không dùng thay lẫn nhau.
9. Nhãn `<<outer_loop>>` giúp điều khiển vòng lặp lồng nhau rõ ràng.
10. `FOUND` và `ROW_COUNT` giúp quan sát kết quả, nhưng phải biết lệnh nào cập nhật chúng.
11. Với job queues, **FOR UPDATE SKIP LOCKED** hỗ trợ concurrency theo ngữ cảnh, không tự bảo đảm exactly-once.
12. **Function không được COMMIT**, procedure có COMMIT chỉ trong ngữ cảnh `CALL` phù hợp; transaction boundaries quyết định atomicity và retry.
13. Bắt lỗi có chọn lọc; `EXCEPTION` tạo subtransaction semantics và có overhead.
14. Giới hạn iteration, array size, batch size, retries, logs và thời gian thực thi.
15. Khi bài toán chỉ là tổng hợp/lọc/cập nhật một tập hàng, **ưu tiên SQL set-based** thay vì loop từng row.

Sơ đồ lựa chọn:

~~~text
Bạn đang muốn xử lý một tập dữ liệu?
                  |
                  v
Một SQL SELECT / UPDATE / INSERT / DELETE
có thể diễn đạt toàn bộ logic không?
        /                         \
       Có                         Không
       |                            |
  Dùng SQL set-based        Cần duyệt gì?
                                 |
                  +--------------+--------------+
                  |              |              |
             Dải số nguyên   Query result    SQL array
                  |              |              |
             FOR integer     FOR rec IN       FOREACH
                                  SELECT
                                     |
                      Cần điều kiện dừng thay đổi?
                                  |
                             LOOP / WHILE
                                  |
                      EXIT / CONTINUE / labels
                                  |
                       Bảo vệ transaction, lỗi,
                       concurrency và tài nguyên
~~~

Giá trị quan trọng nhất của vòng lặp PL/pgSQL là **biểu đạt luồng điều khiển khi SQL set-based không đủ hoặc không rõ ràng**. Sử dụng đúng `LOOP`, `WHILE`, `FOR`, `FOREACH`, `EXIT` và `CONTINUE` giúp code dễ đọc và đúng hơn; sử dụng chúng chỉ vì quen phong cách lập trình từng dòng có thể làm PostgreSQL mất đi lợi thế lớn nhất của xử lý quan hệ theo tập.
