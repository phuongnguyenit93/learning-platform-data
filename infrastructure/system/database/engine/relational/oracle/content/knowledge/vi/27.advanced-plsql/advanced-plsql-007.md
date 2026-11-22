# Pipelined table function và tiêu thụ dữ liệu dạng luồng

Trong Oracle Database, **pipelined table function** là hàm PL/SQL trả dữ liệu cho SQL engine từng hàng thông qua câu lệnh `PIPE ROW`. Hàm không cần tạo và trả về toàn bộ collection rồi mới để câu truy vấn sử dụng. SQL engine có thể lấy các hàng đã được phát ra trong khi hàm tiếp tục tạo những hàng tiếp theo.

Đặc điểm này hữu ích khi cần biến đổi dữ liệu bằng PL/SQL, kết hợp dữ liệu từ nhiều nguồn hoặc tạo một tập kết quả lớn mà không muốn giữ toàn bộ kết quả trong bộ nhớ của PL/SQL. Người dùng vẫn tiêu thụ kết quả như một nguồn hàng trong câu SQL thông thường: dùng `TABLE(function(...))` trong mệnh đề `FROM`, lọc, nối bảng, tổng hợp hoặc đưa kết quả vào một câu lệnh DML.

## 1. Table function và ý nghĩa của pipelining

Một table function là hàm trả về một collection để SQL có thể xem collection đó như một nguồn hàng. Có hai cách triển khai thường gặp:

- **Table function thông thường:** tạo collection, thêm các phần tử vào collection, sau đó trả về toàn bộ collection. SQL chỉ nhận được kết quả sau khi hàm hoàn thành việc tạo collection.
- **Pipelined table function:** phát từng phần tử bằng `PIPE ROW`. SQL engine có thể tiêu thụ hàng được phát ra mà không cần đợi hàm tạo xong toàn bộ tập kết quả.

Ví dụ, nếu một hàm tạo một triệu số, cách thông thường có thể phải giữ một triệu phần tử trong collection trước khi trả về. Với hàm pipelined, hàm có thể tạo một số, phát số đó, rồi tiếp tục tạo số tiếp theo. Cách này thường giảm bộ nhớ trung gian và cải thiện thời gian có hàng đầu tiên.

Pipelining là cơ chế truyền hàng giữa hàm và SQL engine. Nó không biến câu truy vấn thành một tác vụ bất đồng bộ, không tự tạo giao dịch riêng cho từng hàng và cũng không bảo đảm mọi toán tử phía sau đều xử lý dữ liệu theo kiểu streaming.

## 2. Các thành phần cần có

Một pipelined table function cần:

1. Một kiểu collection làm kiểu trả về, thường là nested table hoặc VARRAY.
2. Kiểu phần tử tương ứng với một hàng đầu ra. Phần tử có thể là kiểu dữ liệu đơn như NUMBER hoặc một object type có nhiều thuộc tính.
3. Khai báo hàm với từ khóa `PIPELINED`.
4. Dùng `PIPE ROW(expression)` để phát từng phần tử.
5. Kết thúc hàm bằng `RETURN;` không có biểu thức collection trả về.

Khi gọi hàm từ SQL, hãy dùng kiểu collection và kiểu phần tử mà SQL engine có thể nhìn thấy. Các kiểu được khai báo ở mức schema bằng `CREATE TYPE` là cách triển khai rõ ràng và dễ tái sử dụng.

## 3. Ví dụ cơ bản: phát dãy số

Đầu tiên, tạo một nested table chứa các giá trị NUMBER:

~~~sql
CREATE TYPE number_nt AS TABLE OF NUMBER;
/
~~~

Sau đó, tạo hàm phát các số từ 1 đến giá trị đầu vào:

~~~sql
CREATE OR REPLACE FUNCTION generate_numbers(
  p_max IN PLS_INTEGER
)
RETURN number_nt PIPELINED
IS
BEGIN
  IF p_max IS NULL OR p_max < 1 THEN
    RETURN;
  END IF;

  FOR i IN 1 .. p_max LOOP
    PIPE ROW(i);
  END LOOP;

  RETURN;
END;
/
~~~

Điểm quan trọng trong hàm:

- `RETURN number_nt PIPELINED` khai báo hàm trả về collection và phát phần tử theo kiểu pipelined.
- `PIPE ROW(i)` gửi một phần tử NUMBER sang SQL engine.
- Sau khi phát một hàng, hàm có thể tạm dừng tại đó cho đến khi phía tiêu thụ cần thêm dữ liệu.
- `RETURN;` kết thúc việc phát dữ liệu. Không cần tạo một biến collection để chứa tất cả các số.

Gọi hàm trong SQL:

~~~sql
SELECT n.COLUMN_VALUE AS generated_number
FROM TABLE(generate_numbers(5)) n
ORDER BY n.COLUMN_VALUE;
~~~

Kết quả:

| GENERATED_NUMBER |
|---:|
| 1 |
| 2 |
| 3 |
| 4 |
| 5 |

Vì collection chứa giá trị đơn NUMBER, SQL dùng thuộc tính `COLUMN_VALUE` để tham chiếu phần tử. Nếu collection chứa object type, có thể tham chiếu trực tiếp từng thuộc tính của object.

## 4. Phát các hàng có nhiều cột

Trong ứng dụng thực tế, một hàng thường có nhiều thuộc tính. Ta có thể định nghĩa một object type làm cấu trúc hàng và một nested table chứa các object đó.

Ví dụ sau sử dụng bảng EMPLOYEES trong schema mẫu HR:

~~~sql
CREATE TYPE employee_stream_ot AS OBJECT (
  employee_id NUMBER,
  full_name   VARCHAR2(200),
  salary      NUMBER
);
/

CREATE TYPE employee_stream_nt AS TABLE OF employee_stream_ot;
/
~~~

Tạo hàm trả về nhân viên của một phòng ban:

~~~sql
CREATE OR REPLACE FUNCTION employees_for_department(
  p_department_id IN employees.department_id%TYPE
)
RETURN employee_stream_nt PIPELINED
IS
BEGIN
  FOR r IN (
    SELECT employee_id,
           first_name || ' ' || last_name AS full_name,
           salary
      FROM employees
     WHERE department_id = p_department_id
  ) LOOP
    PIPE ROW(
      employee_stream_ot(
        r.employee_id,
        r.full_name,
        r.salary
      )
    );
  END LOOP;

  RETURN;
END;
/
~~~

Mỗi lần lặp, hàm tạo một object `employee_stream_ot` và phát object đó bằng `PIPE ROW`. Không cần khai báo collection đầu ra rồi `EXTEND` và gán từng phần tử.

Tiêu thụ kết quả:

~~~sql
SELECT e.employee_id,
       e.full_name,
       e.salary
  FROM TABLE(employees_for_department(50)) e
 ORDER BY e.employee_id;
~~~

Các cột của kết quả tương ứng với thuộc tính trong object type. Điều kiện lọc và sắp xếp có thể đặt ở câu SQL bên ngoài như khi truy vấn một bảng.

Lưu ý: ví dụ giả định schema HR có bảng EMPLOYEES và các cột được nêu. Nếu dùng schema khác, hãy điều chỉnh tên bảng, cột và quyền truy cập tương ứng.

## 5. Tiêu thụ dữ liệu bằng TABLE()

Toán tử `TABLE()` cho phép SQL xem collection do hàm trả về như một nguồn hàng trong mệnh đề `FROM`. Đây là cách gọi tiêu chuẩn của table function.

### Lọc hàng

~~~sql
SELECT e.employee_id,
       e.full_name,
       e.salary
  FROM TABLE(employees_for_department(50)) e
 WHERE e.salary >= 5000
 ORDER BY e.salary DESC;
~~~

### Tổng hợp dữ liệu

~~~sql
SELECT COUNT(*) AS employee_count,
       AVG(e.salary) AS average_salary,
       MAX(e.salary) AS highest_salary
  FROM TABLE(employees_for_department(50)) e;
~~~

### Nối với bảng khác

Khi đối số của table function tham chiếu đến một hàng từ nguồn hàng đứng trước, dùng cú pháp `CROSS APPLY` hoặc `OUTER APPLY` để thể hiện rõ quan hệ tương quan. Ví dụ:

~~~sql
SELECT d.department_id,
       e.employee_id,
       e.full_name,
       e.salary
  FROM departments d
 CROSS APPLY TABLE(
   employees_for_department(d.department_id)
 ) e
 ORDER BY d.department_id, e.employee_id;
~~~

`CROSS APPLY` chỉ giữ phòng ban có hàng được hàm trả về. Nếu muốn giữ cả phòng ban không có nhân viên phù hợp, dùng `OUTER APPLY`:

~~~sql
SELECT d.department_id,
       e.employee_id,
       e.full_name
  FROM departments d
 OUTER APPLY TABLE(
   employees_for_department(d.department_id)
 ) e
 ORDER BY d.department_id, e.employee_id;
~~~

`CROSS APPLY` và `OUTER APPLY` được hỗ trợ từ Oracle Database 12c. Khi hàm được gọi theo từng hàng của bảng bên trái, cần cân nhắc số lần hàm được thực thi và chi phí của mỗi lần gọi. Với nhiều phòng ban, hãy kiểm tra execution plan và so sánh với phương án JOIN trực tiếp nếu nghiệp vụ có thể viết hoàn toàn bằng SQL.

## 6. Tiêu thụ theo từng hàng trong PL/SQL

Pipelined table function được gọi từ SQL. Không gọi trực tiếp như một biểu thức PL/SQL để gán collection:

~~~sql
-- Không dùng theo cách này:
-- l_rows := generate_numbers(1000);
~~~

Table function pipelined không được gọi trực tiếp trong phạm vi biểu thức PL/SQL theo cách trên; Oracle có thể báo lỗi PLS-00653. Nếu chương trình PL/SQL cần xử lý từng hàng, hãy mở cursor trên câu SELECT có `TABLE()` hoặc dùng cursor FOR loop:

~~~sql
BEGIN
  FOR r IN (
    SELECT n.COLUMN_VALUE AS generated_number
      FROM TABLE(generate_numbers(1000)) n
  ) LOOP
    -- Xử lý từng giá trị r.generated_number tại đây.
    NULL;
  END LOOP;
END;
/
~~~

Cursor FOR loop lấy từng hàng trong quá trình duyệt. Chương trình không cần tải toàn bộ kết quả của hàm vào một collection PL/SQL trước khi bắt đầu xử lý.

Có thể dùng cursor tường minh nếu cần kiểm soát thời điểm mở, fetch và đóng:

~~~sql
DECLARE
  CURSOR c_numbers IS
    SELECT n.COLUMN_VALUE AS generated_number
      FROM TABLE(generate_numbers(1000)) n;

  l_number NUMBER;
BEGIN
  OPEN c_numbers;

  LOOP
    FETCH c_numbers INTO l_number;
    EXIT WHEN c_numbers%NOTFOUND;

    -- Xử lý l_number.
    NULL;
  END LOOP;

  CLOSE c_numbers;
EXCEPTION
  WHEN OTHERS THEN
    IF c_numbers%ISOPEN THEN
      CLOSE c_numbers;
    END IF;
    RAISE;
END;
/
~~~

## 7. Nhận nguồn dữ liệu qua REF CURSOR

Một ứng dụng quan trọng của pipelined table function là biến đổi dữ liệu đến từ một truy vấn do bên gọi cung cấp. Thay vì tự truy vấn một bảng cố định bên trong hàm, hàm nhận một `REF CURSOR`, đọc từng hàng từ cursor đó rồi phát kết quả đã biến đổi.

Ví dụ, tạo hàm nhận một cursor chứa lương và phát ra giá trị lương nhân đôi:

~~~sql
CREATE OR REPLACE FUNCTION double_salary_rows(
  p_rows IN SYS_REFCURSOR
)
RETURN number_nt PIPELINED
IS
  l_salary NUMBER;
BEGIN
  LOOP
    FETCH p_rows INTO l_salary;
    EXIT WHEN p_rows%NOTFOUND;

    PIPE ROW(l_salary * 2);
  END LOOP;

  CLOSE p_rows;
  RETURN;

EXCEPTION
  WHEN NO_DATA_NEEDED THEN
    IF p_rows%ISOPEN THEN
      CLOSE p_rows;
    END IF;
    RAISE;
  WHEN OTHERS THEN
    IF p_rows%ISOPEN THEN
      CLOSE p_rows;
    END IF;
    RAISE;
END;
/
~~~

Gọi hàm bằng một cursor expression:

~~~sql
SELECT x.COLUMN_VALUE AS doubled_salary
  FROM TABLE(
    double_salary_rows(
      CURSOR(
        SELECT salary
          FROM employees
         WHERE department_id = 50
      )
    )
  ) x
 ORDER BY x.COLUMN_VALUE;
~~~

Luồng xử lý:

1. SQL mở cursor cho truy vấn con trong biểu thức `CURSOR(...)`.
2. Cursor được truyền vào tham số `SYS_REFCURSOR` của hàm.
3. Hàm FETCH một giá trị lương, biến đổi giá trị đó và phát ra bằng `PIPE ROW`.
4. SQL engine nhận hàng đầu ra và có thể tiếp tục yêu cầu hàng kế tiếp.
5. Khi hết dữ liệu, hàm đóng cursor và kết thúc bằng `RETURN;`.

Ví dụ này dùng `SYS_REFCURSOR` dạng weak cursor và giả định cursor chỉ trả về một cột có thể chuyển đổi sang NUMBER. Nếu truy vấn trả về nhiều cột, phần FETCH phải nhận đúng số lượng và kiểu dữ liệu tương ứng.

## 8. Luồng dữ liệu và thời điểm tiêu thụ

Có thể hình dung pipelined table function như một bộ sản xuất và SQL engine như bộ tiêu thụ:

~~~text
Nguồn dữ liệu / REF CURSOR
          |
          v
  Pipelined function
          |
      PIPE ROW
          |
          v
       SQL engine
          |
   +------+------+---------+
   |             |         |
  WHERE          JOIN    Aggregate
   |             |         |
   +-------------+---------+
                 |
                 v
          Kết quả truy vấn
~~~

Khi SQL engine cần dữ liệu, hàm tiếp tục chạy đến lần `PIPE ROW` tiếp theo. Khi hàm phát hàng, quyền điều khiển có thể quay lại phía tiêu thụ. Cơ chế này cho phép xử lý kết quả từng phần và giảm nhu cầu giữ toàn bộ collection trong bộ nhớ.

Tuy nhiên, cần phân biệt **pipelining ở đầu ra của hàm** với **streaming xuyên suốt toàn bộ execution plan**:

- Một phép lọc đơn giản có thể tiêu thụ từng hàng khi hàng được phát ra.
- Một phép sắp xếp `ORDER BY` thường cần thu thập dữ liệu đầu vào trước khi xác định thứ tự cuối cùng.
- Các phép `GROUP BY`, `DISTINCT`, hash join hoặc một số phép phân tích có thể cần lưu trạng thái hoặc đệm một lượng lớn dữ liệu.
- Parallel execution có thể thay đổi thứ tự và cách dữ liệu được chuyển giữa các tiến trình.

Do đó, pipelined function có thể giảm bộ nhớ ở phía hàm nhưng không bảo đảm toàn bộ câu truy vấn không cần bộ nhớ trung gian. Hãy đọc execution plan để biết các toán tử thực tế của câu SQL.

## 9. Dừng sớm và ngoại lệ NO_DATA_NEEDED

Không phải lúc nào bên gọi cũng cần tiêu thụ tất cả các hàng. Ví dụ:

~~~sql
SELECT n.COLUMN_VALUE
  FROM TABLE(generate_numbers(1000000)) n
 WHERE ROWNUM <= 10;
~~~

Khi SQL engine đã có đủ hàng cho kết quả, nó có thể ngừng yêu cầu hàm phát thêm dữ liệu. Trong tình huống này, Oracle có thể phát sinh ngoại lệ `NO_DATA_NEEDED` trong pipelined function để báo rằng phía tiêu thụ không cần thêm hàng.

Nếu hàm không có xử lý dọn dẹp tài nguyên riêng, Oracle xử lý tín hiệu này như một phần của việc kết thúc pipeline. Nếu hàm có exception handler tổng quát `WHEN OTHERS`, cần chú ý không biến `NO_DATA_NEEDED` thành lỗi ứng dụng thông thường. Có thể xử lý riêng để đóng cursor hoặc giải phóng tài nguyên rồi phát sinh lại ngoại lệ:

~~~sql
EXCEPTION
  WHEN NO_DATA_NEEDED THEN
    -- Giải phóng tài nguyên nếu còn mở.
    RAISE;
  WHEN OTHERS THEN
    -- Dọn dẹp tài nguyên và giữ nguyên lỗi thực tế.
    RAISE;
END;
~~~

Ví dụ `double_salary_rows` ở phần trước minh họa cách đóng REF CURSOR khi pipeline kết thúc sớm hoặc gặp lỗi. Đây là điểm quan trọng với hàm đọc file, cursor hoặc tài nguyên bên ngoài.

## 10. Thứ tự hàng và tính đúng đắn của kết quả

Không nên dựa vào thứ tự `PIPE ROW` để kết luận thứ tự kết quả cuối cùng của câu SQL. SQL chỉ bảo đảm thứ tự hiển thị khi câu truy vấn ngoài cùng có `ORDER BY`.

Ví dụ, dù hàm phát nhân viên theo một thứ tự nhất định, câu truy vấn tiêu thụ nên chỉ định rõ:

~~~sql
SELECT e.employee_id, e.full_name
  FROM TABLE(employees_for_department(50)) e
 ORDER BY e.employee_id;
~~~

Nếu hàm được thực thi song song, thứ tự hàng càng không nên được xem là cố định. Khi thứ tự là một phần của yêu cầu nghiệp vụ, hãy mang cột sắp xếp trong dữ liệu đầu ra và dùng `ORDER BY` ở câu SQL tiêu thụ.

## 11. Parallel execution

Pipelined table function có thể được thiết kế để chạy song song bằng mệnh đề `PARALLEL_ENABLE`. Khi được bật và execution plan phù hợp, Oracle có thể phân phối công việc cho các parallel execution process.

Chỉ bật song song khi hàm thực sự an toàn để chạy trên nhiều luồng xử lý. Cần xem xét:

- Mỗi phần dữ liệu có thể được xử lý độc lập hay không.
- Hàm có phụ thuộc vào biến package, trạng thái session hoặc thứ tự hàng hay không.
- Dữ liệu đầu vào được phân vùng theo cách phù hợp với phép biến đổi hay không.
- Việc chạy song song có làm tăng tải CPU, I/O hoặc số lần truy cập nguồn dữ liệu quá mức hay không.
- Kết quả có cần thứ tự xác định hay không; nếu có, câu SQL ngoài cùng vẫn phải dùng `ORDER BY`.

Với hàm nhận REF CURSOR, cấu hình phân vùng đầu vào cần phù hợp với cách dữ liệu được chia cho các tiến trình. `PARALLEL_ENABLE` không phải một bảo đảm rằng câu truy vấn sẽ chạy song song trong mọi trường hợp. Hãy xác nhận bằng execution plan và đo hiệu năng trên dữ liệu thực tế.

## 12. Khi nào nên dùng pipelined table function?

Pipelined table function phù hợp khi:

- Cần thực hiện phép biến đổi phức tạp bằng PL/SQL mà SQL thuần khó biểu diễn.
- Cần chuyển dữ liệu từ REF CURSOR hoặc một nguồn dữ liệu khác thành tập hàng có thể truy vấn bằng SQL.
- Kết quả lớn và việc tạo toàn bộ collection trước khi trả về gây áp lực bộ nhớ.
- Muốn kết hợp logic PL/SQL với các thao tác SQL như JOIN, WHERE, GROUP BY hoặc INSERT ... SELECT.
- Muốn bên gọi có thể dừng tiêu thụ khi đã nhận đủ hàng.

Nên cân nhắc cách khác khi:

- Phép biến đổi có thể viết rõ ràng và hiệu quả bằng một câu SQL thuần.
- Tập kết quả nhỏ và việc tạo collection thông thường đơn giản hơn.
- Chi phí gọi PL/SQL và phát từng hàng lớn hơn lợi ích giảm bộ nhớ.
- Hàm cần thực hiện nhiều tác động phụ lên dữ liệu hoặc giao dịch.

Pipelined không mặc nhiên nhanh hơn. Với mỗi hàng được phát, vẫn có chi phí chuyển điều khiển và chuyển dữ liệu giữa PL/SQL runtime và SQL engine. Một câu SQL thuần thường cho optimizer nhiều cơ hội hơn để đẩy điều kiện lọc, chọn thứ tự join và tối ưu toàn bộ phép xử lý.

## 13. Các lưu ý khi triển khai

**Giữ kiểu trả về ổn định:** kiểu collection và kiểu phần tử là hợp đồng giữa hàm và câu SQL. Khi thay đổi object type, cần xem xét các hàm, view và ứng dụng đang phụ thuộc vào kiểu đó.

**Không tích lũy toàn bộ đầu ra:** nếu mục tiêu là giảm bộ nhớ, tránh tạo thêm một collection lớn bên trong hàm rồi mới phát từng phần tử. Chỉ giữ trạng thái thực sự cần thiết cho phép biến đổi.

**Quản lý cursor và tài nguyên:** nếu hàm nhận REF CURSOR hoặc mở tài nguyên khác, hãy đóng và giải phóng cả khi xử lý bình thường, có lỗi hoặc bên gọi dừng sớm.

**Tránh tác động phụ trong câu SELECT:** không nên dùng pipelined function như một nơi để cập nhật dữ liệu nghiệp vụ hoặc commit giao dịch. Hãy giữ chức năng phát dữ liệu có thể dự đoán và đặt thao tác ghi trong câu DML hoặc procedure phù hợp.

**Kiểm tra số hàng và kiểu dữ liệu:** giá trị truyền vào `PIPE ROW` phải tương thích với kiểu phần tử của collection. Khi phát object, thứ tự và kiểu đối số của constructor phải khớp định nghĩa object type.

**Kiểm tra execution plan:** các toán tử sort, group, join hoặc parallel execution có thể làm thay đổi lượng dữ liệu được đệm và thời điểm kết quả được trả về. Không đánh giá hiệu năng chỉ từ việc hàm có từ khóa `PIPELINED`.

**Xử lý dừng sớm:** nếu có exception handler `WHEN OTHERS`, hãy xử lý `NO_DATA_NEEDED` riêng để dọn dẹp đúng cách và tránh báo lỗi sai khi người gọi không cần thêm hàng.

## 14. Cách kiểm tra một pipelined table function

Khi đưa hàm vào ứng dụng, nên kiểm tra cách nó được gọi và tiêu thụ:

1. Gọi hàm với đầu vào nhỏ, đầu vào rỗng, đầu vào NULL và đầu vào biên.
2. Xác nhận số lượng hàng, giá trị và kiểu dữ liệu đầu ra.
3. Dùng `TABLE(function(...))` trong SELECT với WHERE, ORDER BY và phép tổng hợp.
4. Nối kết quả với bảng khác; kiểm tra cả trường hợp nguồn bên trái không có hàng phù hợp khi dùng OUTER APPLY.
5. Tiêu thụ qua cursor FOR loop trong PL/SQL.
6. Thử giới hạn kết quả để xác nhận việc dừng sớm không làm rò rỉ cursor hoặc tài nguyên.
7. Kiểm tra đường xử lý ngoại lệ và xác nhận lỗi gốc được truyền về bên gọi.
8. Đọc execution plan, đo thời gian có hàng đầu tiên, tổng thời gian, PGA và mức I/O trên dữ liệu đại diện.
9. Nếu dùng parallel execution, kiểm tra kết quả, thứ tự, tính độc lập của từng phần xử lý và mức tiêu thụ tài nguyên.

## 15. Tổng kết

Pipelined table function cho phép PL/SQL phát các hàng cho SQL engine từng phần bằng `PIPE ROW`. SQL tiêu thụ dữ liệu qua `TABLE(function(...))`, từ đó có thể lọc, nối, tổng hợp hoặc đưa kết quả vào DML. Khi cần xử lý trong PL/SQL, hãy duyệt một cursor dựa trên câu SELECT đó.

Mẫu triển khai cốt lõi là khai báo kiểu collection, tạo hàm `RETURN collection_type PIPELINED`, phát từng phần tử và kết thúc bằng `RETURN;`. Với nguồn dữ liệu do bên gọi cung cấp, có thể nhận `SYS_REFCURSOR`, FETCH từng hàng và phát kết quả đã biến đổi.

Pipelining giúp tránh phải vật chất hóa toàn bộ collection trong PL/SQL và có thể cho phép bên gọi dừng sớm. Hiệu quả thực tế vẫn phụ thuộc execution plan, các toán tử tiêu thụ dữ liệu, chi phí xử lý từng hàng, quản lý tài nguyên và cách triển khai song song. Hãy ưu tiên SQL thuần khi có thể biểu diễn nghiệp vụ rõ ràng bằng SQL; dùng pipelined table function khi cần một bộ biến đổi dạng thủ tục nhưng vẫn muốn cung cấp kết quả như một nguồn hàng cho SQL.
