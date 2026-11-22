# LOOP, WHILE, FOR, EXIT và CONTINUE trong PL/SQL

PL/SQL cung cấp các cấu trúc vòng lặp để thực hiện một nhóm câu lệnh nhiều lần. Ba dạng cơ bản là **LOOP**, **WHILE LOOP** và **FOR LOOP**. Khi cần kết thúc sớm hoặc bỏ qua phần còn lại của một lượt lặp, ta dùng **EXIT** và **CONTINUE**.

Vòng lặp hữu ích khi một thủ tục cần xử lý từng phần tử, đọc cursor, thử lại một bước có giới hạn hoặc thực hiện một chuỗi thao tác có điều kiện. Tuy nhiên, với dữ liệu quan hệ, nhiều công việc có thể được giải quyết hiệu quả hơn bằng một câu SQL xử lý theo tập hợp. Cần chọn vòng lặp khi logic thực sự tuần tự hoặc phụ thuộc vào kết quả từng lượt.

Bài học này trình bày cú pháp, luồng thực thi, phạm vi biến đếm, vòng lặp lồng nhau, cursor FOR LOOP, xử lý ngoại lệ và các ví dụ có thể chạy trong Oracle SQL Developer hoặc SQL*Plus.

## 1. Vòng lặp trong PL/SQL

Vòng lặp là cấu trúc điều khiển cho phép chạy một nhóm lệnh nhiều lần. Một vòng lặp thường có:

- Phần thân: các câu lệnh được thực hiện trong mỗi lượt.
- Điều kiện tiếp tục hoặc điều kiện dừng.
- Có thể có bước cập nhật biến điều khiển.

PL/SQL có ba dạng vòng lặp chính:

| Dạng | Cách kiểm soát số lượt | Thường dùng khi |
|---|---|---|
| LOOP cơ bản | Tự viết EXIT hoặc EXIT WHEN | Cần điều khiển điểm dừng linh hoạt |
| WHILE LOOP | Kiểm tra điều kiện trước mỗi lượt | Tiếp tục khi điều kiện còn đúng |
| FOR LOOP số | Chạy qua một khoảng số xác định | Biết cận dưới và cận trên |

Ngoài ra, **cursor FOR LOOP** là dạng FOR LOOP duyệt kết quả truy vấn. Oracle tự quản lý việc mở cursor, lấy từng dòng và đóng cursor.

### 1.1. Sơ đồ tổng quát

~~~text
             Bắt đầu vòng lặp
                    |
                    v
          Có kiểm tra điều kiện đầu?
               /          \
             Có            Không
             |               |
             v               v
      Điều kiện TRUE?     Chạy thân LOOP
        /       \
      Có         Không
      |            |
      v            v
 Chạy thân      Kết thúc
      |
      v
 EXIT hoặc CONTINUE?
      |
      v
 Sang lượt tiếp theo hoặc thoát
~~~

Sơ đồ chỉ mô tả ý tưởng chung. Vị trí kiểm tra điều kiện khác nhau giữa LOOP, WHILE và FOR; cần nắm rõ từng dạng để tránh chạy thừa một lượt hoặc tạo vòng lặp vô hạn.

## 2. LOOP cơ bản

LOOP cơ bản bắt đầu chạy thân vòng lặp ngay lập tức. Nó không có điều kiện dừng ở đầu cấu trúc; lập trình viên phải dùng EXIT hoặc EXIT WHEN để kết thúc.

### 2.1. Cú pháp

~~~sql
LOOP
    statements;
END LOOP;
~~~

Nếu không có câu lệnh EXIT, vòng lặp tiếp tục mãi cho đến khi bị ngắt hoặc phát sinh lỗi làm thoát khỏi block.

Ví dụ:

~~~sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Start');
    LOOP
        DBMS_OUTPUT.PUT_LINE('This statement repeats');
        EXIT;
    END LOOP;
    DBMS_OUTPUT.PUT_LINE('End');
END;
/
~~~

EXIT không có điều kiện kết thúc vòng lặp hiện tại ngay tại vị trí nó được thực thi.

### 2.2. Dùng EXIT WHEN

EXIT WHEN kết thúc vòng lặp khi điều kiện có giá trị TRUE:

~~~sql
DECLARE
    v_counter PLS_INTEGER := 1;
BEGIN
    LOOP
        DBMS_OUTPUT.PUT_LINE('Counter = ' || v_counter);
        v_counter := v_counter + 1;

        EXIT WHEN v_counter > 5;
    END LOOP;
END;
/
~~~

Kết quả in ra các số từ 1 đến 5. Sau khi in 5, biến được tăng thành 6; điều kiện V_COUNTER > 5 trở thành TRUE nên vòng lặp kết thúc.

Lưu ý vị trí của EXIT WHEN:

~~~sql
LOOP
    EXIT WHEN v_counter > 5;
    DBMS_OUTPUT.PUT_LINE(v_counter);
    v_counter := v_counter + 1;
END LOOP;
~~~

Ở ví dụ thứ hai, điều kiện được kiểm tra trước khi in. Nếu V_COUNTER đã lớn hơn 5 từ đầu, thân vòng lặp không chạy lượt tiếp theo. Với LOOP cơ bản, thân vòng lặp luôn được bắt đầu ít nhất một lần; nhưng EXIT đặt ngay đầu thân có thể làm lượt đó kết thúc ngay.

### 2.3. Dùng EXIT không điều kiện

~~~sql
DECLARE
    v_counter PLS_INTEGER := 1;
BEGIN
    LOOP
        DBMS_OUTPUT.PUT_LINE(v_counter);

        IF v_counter = 3 THEN
            EXIT;
        END IF;

        v_counter := v_counter + 1;
    END LOOP;
END;
/
~~~

EXIT thường được đặt trong IF khi điều kiện dừng cần nhiều nhánh hoặc cần thực hiện thêm xử lý trước khi thoát.

### 2.4. Khi nào dùng LOOP cơ bản?

LOOP phù hợp khi:

- Điểm dừng chỉ biết sau khi thực hiện một số thao tác.
- Cần lặp cho đến khi cursor hết dòng hoặc không còn công việc.
- Cần kiểm tra nhiều điều kiện dừng ở các vị trí khác nhau.
- Cần thử lại thao tác nhưng có giới hạn số lần.

Khi đã biết rõ điều kiện trước mỗi lượt, WHILE LOOP thường thể hiện ý định dễ đọc hơn.

## 3. WHILE LOOP

WHILE LOOP kiểm tra điều kiện trước mỗi lượt. Nếu điều kiện TRUE, thân vòng lặp được thực hiện. Nếu điều kiện FALSE hoặc NULL, vòng lặp kết thúc mà không chạy thân ở lượt đó.

### 3.1. Cú pháp

~~~sql
WHILE condition LOOP
    statements;
END LOOP;
~~~

Ví dụ:

~~~sql
DECLARE
    v_counter PLS_INTEGER := 1;
BEGIN
    WHILE v_counter <= 5 LOOP
        DBMS_OUTPUT.PUT_LINE('Counter = ' || v_counter);
        v_counter := v_counter + 1;
    END LOOP;
END;
/
~~~

Kết quả là 1, 2, 3, 4, 5. Sau lượt in 5, biến tăng lên 6. Oracle kiểm tra lại điều kiện 6 <= 5, nhận FALSE và kết thúc.

### 3.2. Điều kiện được kiểm tra trước thân vòng lặp

~~~sql
DECLARE
    v_counter PLS_INTEGER := 10;
BEGIN
    WHILE v_counter <= 5 LOOP
        DBMS_OUTPUT.PUT_LINE('This line is not printed');
        v_counter := v_counter + 1;
    END LOOP;

    DBMS_OUTPUT.PUT_LINE('Loop finished');
END;
/
~~~

Vì điều kiện sai ngay từ đầu, thân vòng lặp không chạy lần nào. Đây là khác biệt quan trọng so với LOOP cơ bản.

### 3.3. Cập nhật biến điều khiển

Điều kiện WHILE phải có khả năng chuyển từ TRUE sang FALSE. Nếu thân vòng lặp không thay đổi biến tham gia điều kiện và không có thao tác nào khác làm điều kiện đổi giá trị, vòng lặp có thể chạy vô hạn.

Ví dụ sai:

~~~sql
DECLARE
    v_counter PLS_INTEGER := 1;
BEGIN
    WHILE v_counter <= 5 LOOP
        DBMS_OUTPUT.PUT_LINE(v_counter);
        -- Thiếu câu lệnh tăng v_counter.
    END LOOP;
END;
/
~~~

Điều kiện V_COUNTER <= 5 luôn TRUE vì biến không đổi. Ví dụ này chỉ để nhận diện lỗi; không chạy trong session dùng chung hoặc môi trường production.

### 3.4. Điều kiện có giá trị NULL

Điều kiện vòng lặp PL/SQL là biểu thức BOOLEAN. Với WHILE, thân vòng lặp chỉ chạy khi điều kiện TRUE. Nếu điều kiện FALSE hoặc NULL, thân không được thực hiện.

Ví dụ:

~~~sql
DECLARE
    v_limit PLS_INTEGER := NULL;
    v_counter PLS_INTEGER := 1;
BEGIN
    WHILE v_counter <= v_limit LOOP
        DBMS_OUTPUT.PUT_LINE(v_counter);
        v_counter := v_counter + 1;
    END LOOP;

    DBMS_OUTPUT.PUT_LINE('No iteration');
END;
/
~~~

So sánh với NULL cho kết quả UNKNOWN/NULL, nên thân vòng lặp không chạy. Khi giá trị điều khiển có thể NULL, hãy kiểm tra hoặc gán giá trị mặc định trước khi vào vòng lặp.

## 4. FOR LOOP với khoảng số

FOR LOOP số lặp qua một dãy số nguyên từ cận dưới đến cận trên. Oracle tự tạo biến đếm cho vòng lặp và tự tăng hoặc giảm biến theo hướng đã chọn.

### 4.1. Cú pháp

~~~sql
FOR loop_index IN lower_bound .. upper_bound LOOP
    statements;
END LOOP;
~~~

Ví dụ:

~~~sql
BEGIN
    FOR i IN 1 .. 5 LOOP
        DBMS_OUTPUT.PUT_LINE('i = ' || i);
    END LOOP;
END;
/
~~~

Kết quả là 1, 2, 3, 4, 5. Không cần khai báo hoặc tự tăng biến I.

### 4.2. Biến đếm được khai báo ngầm

Trong FOR LOOP:

- Oracle khai báo biến đếm ngầm với phạm vi trong vòng lặp.
- Biến đếm chỉ dùng được trong thân vòng lặp.
- Không được gán giá trị trực tiếp cho biến đếm.
- Sau END LOOP, biến đếm không còn trong phạm vi sử dụng.

Ví dụ không hợp lệ:

~~~sql
BEGIN
    FOR i IN 1 .. 5 LOOP
        i := i + 1; -- Không được phép gán biến đếm.
    END LOOP;
END;
/
~~~

FOR LOOP tự điều khiển biến đếm; không sửa nó bên trong thân vòng lặp.

### 4.3. Cận dưới và cận trên

Các biểu thức cận dưới và cận trên được xác định khi bắt đầu vòng lặp. Nếu cần giới hạn thay đổi trong lúc vòng lặp chạy, hãy dùng WHILE hoặc LOOP với biến điều khiển tường minh.

Ví dụ:

~~~sql
DECLARE
    v_start PLS_INTEGER := 2;
    v_end   PLS_INTEGER := 4;
BEGIN
    FOR i IN v_start .. v_end LOOP
        DBMS_OUTPUT.PUT_LINE(i);
        v_end := 10;
    END LOOP;
END;
/
~~~

Vòng lặp vẫn dùng cận đã xác định khi bắt đầu, nên việc gán V_END bên trong không kéo dài vòng lặp đến 10.

### 4.4. Khoảng không có lượt lặp

Với FOR LOOP thông thường, nếu cận dưới lớn hơn cận trên, thân vòng lặp không chạy:

~~~sql
BEGIN
    FOR i IN 5 .. 1 LOOP
        DBMS_OUTPUT.PUT_LINE(i);
    END LOOP;

    DBMS_OUTPUT.PUT_LINE('Finished');
END;
/
~~~

Chỉ dòng Finished được in. Nếu muốn đếm lùi, dùng REVERSE.

## 5. FOR REVERSE: lặp theo chiều giảm

Từ khóa REVERSE khiến biến đếm đi từ cận trên xuống cận dưới:

~~~sql
BEGIN
    FOR i IN REVERSE 1 .. 5 LOOP
        DBMS_OUTPUT.PUT_LINE(i);
    END LOOP;
END;
/
~~~

Kết quả:

~~~text
5
4
3
2
1
~~~

Lưu ý: với REVERSE, thứ tự khai báo cận vẫn là lower_bound .. upper_bound. Oracle bắt đầu từ cận trên và giảm dần về cận dưới. Không đảo cận thành 5 .. 1:

~~~sql
-- Không có lượt lặp vì cận dưới 5 lớn hơn cận trên 1.
FOR i IN REVERSE 5 .. 1 LOOP
    NULL;
END LOOP;
~~~

### 5.1. Ứng dụng của FOR REVERSE

FOR REVERSE phù hợp khi:

- Duyệt chỉ số từ cuối về đầu.
- Xử lý các bước theo thứ tự ngược.
- Gỡ bỏ các phần tử hoặc công việc theo thứ tự giảm.

Ví dụ:

~~~sql
BEGIN
    FOR step_no IN REVERSE 1 .. 4 LOOP
        DBMS_OUTPUT.PUT_LINE('Undo step ' || step_no);
    END LOOP;
END;
/
~~~

Kết quả in thứ tự 4, 3, 2, 1.

## 6. EXIT: thoát khỏi vòng lặp

EXIT kết thúc vòng lặp hiện tại. Có hai dạng thường dùng:

~~~sql
EXIT;
~~~

~~~sql
EXIT WHEN condition;
~~~

### 6.1. EXIT trong LOOP

~~~sql
DECLARE
    v_counter PLS_INTEGER := 1;
BEGIN
    LOOP
        EXIT WHEN v_counter > 3;
        DBMS_OUTPUT.PUT_LINE(v_counter);
        v_counter := v_counter + 1;
    END LOOP;
END;
/
~~~

Kết quả 1, 2, 3.

### 6.2. EXIT trong WHILE hoặc FOR

EXIT không chỉ dùng với LOOP cơ bản; có thể dùng trong WHILE và FOR để dừng sớm:

~~~sql
BEGIN
    FOR i IN 1 .. 10 LOOP
        IF i = 4 THEN
            EXIT;
        END IF;

        DBMS_OUTPUT.PUT_LINE(i);
    END LOOP;
END;
/
~~~

Kết quả in 1, 2, 3. Khi I bằng 4, EXIT kết thúc vòng FOR ngay.

### 6.3. EXIT chỉ thoát vòng lặp gần nhất

Trong các vòng lặp lồng nhau, EXIT không có nhãn chỉ kết thúc vòng lặp trong cùng chứa câu lệnh EXIT:

~~~sql
BEGIN
    FOR i IN 1 .. 3 LOOP
        DBMS_OUTPUT.PUT_LINE('Outer ' || i);

        FOR j IN 1 .. 3 LOOP
            IF j = 2 THEN
                EXIT;
            END IF;

            DBMS_OUTPUT.PUT_LINE('  Inner ' || j);
        END LOOP;
    END LOOP;
END;
/
~~~

Mỗi lượt vòng ngoài chỉ in Inner 1 rồi thoát vòng trong. Vòng ngoài tiếp tục với giá trị I tiếp theo.

## 7. EXIT với nhãn để thoát vòng lặp ngoài

PL/SQL cho phép gắn nhãn cho vòng lặp bằng cặp dấu << và >>. EXIT có thể chỉ rõ nhãn của vòng lặp cần kết thúc.

### 7.1. Cú pháp

~~~sql
<<outer_loop>>
LOOP
    ...
    <<inner_loop>>
    LOOP
        ...
        EXIT outer_loop;
    END LOOP inner_loop;
END LOOP outer_loop;
~~~

### 7.2. Ví dụ thoát hai tầng

~~~sql
BEGIN
    <<outer_loop>>
    FOR i IN 1 .. 3 LOOP
        FOR j IN 1 .. 3 LOOP
            DBMS_OUTPUT.PUT_LINE('i=' || i || ', j=' || j);

            IF i = 2 AND j = 2 THEN
                EXIT outer_loop;
            END IF;
        END LOOP;
    END LOOP outer_loop;

    DBMS_OUTPUT.PUT_LINE('Exited outer loop');
END;
/
~~~

Khi I = 2 và J = 2, EXIT OUTER_LOOP kết thúc vòng FOR ngoài. Dòng Exited outer loop được thực hiện sau đó.

### 7.3. Khi nào dùng nhãn?

Nhãn hữu ích khi:

- Có nhiều vòng lặp lồng nhau.
- Điều kiện dừng nằm trong vòng lặp sâu nhưng cần kết thúc vòng ngoài.
- Muốn làm rõ vòng lặp đích trong code có nhiều tầng.

Không lạm dụng nhãn nếu một cấu trúc đơn giản có thể diễn đạt rõ bằng điều kiện và EXIT ở vòng lặp gần nhất.

## 8. CONTINUE: bỏ qua phần còn lại của lượt lặp

CONTINUE không kết thúc vòng lặp. Nó bỏ qua các câu lệnh còn lại của lượt hiện tại và chuyển sang lượt tiếp theo của vòng lặp.

CONTINUE và CONTINUE WHEN được hỗ trợ trong PL/SQL từ Oracle Database 11g trở lên. Nếu cần chạy trên phiên bản cũ hơn, hãy kiểm tra khả năng tương thích và có thể viết logic tương đương bằng IF.

### 8.1. Cú pháp

~~~sql
CONTINUE;
~~~

~~~sql
CONTINUE WHEN condition;
~~~

### 8.2. Ví dụ bỏ qua số chẵn

~~~sql
BEGIN
    FOR i IN 1 .. 10 LOOP
        CONTINUE WHEN MOD(i, 2) = 0;
        DBMS_OUTPUT.PUT_LINE(i);
    END LOOP;
END;
/
~~~

Kết quả là 1, 3, 5, 7, 9. Khi I chẵn, Oracle bỏ qua câu DBMS_OUTPUT.PUT_LINE trong lượt đó và chuyển sang lượt tiếp theo.

### 8.3. CONTINUE trong IF

~~~sql
BEGIN
    FOR i IN 1 .. 5 LOOP
        IF i = 3 THEN
            CONTINUE;
        END IF;

        DBMS_OUTPUT.PUT_LINE('Process ' || i);
    END LOOP;
END;
/
~~~

Lượt I = 3 không in dòng Process 3. Các lượt khác vẫn chạy bình thường.

### 8.4. CONTINUE không làm biến điều khiển của WHILE tự tăng

Với FOR LOOP, Oracle tự chuyển biến đếm sang giá trị tiếp theo sau CONTINUE. Với LOOP hoặc WHILE, lập trình viên tự cập nhật biến điều khiển.

Ví dụ nguy hiểm:

~~~sql
DECLARE
    v_counter PLS_INTEGER := 1;
BEGIN
    WHILE v_counter <= 5 LOOP
        CONTINUE WHEN v_counter = 3;
        v_counter := v_counter + 1;
    END LOOP;
END;
/
~~~

Khi V_COUNTER bằng 3, CONTINUE bỏ qua câu lệnh tăng biến. V_COUNTER giữ nguyên 3 và điều kiện WHILE tiếp tục TRUE mãi. Đây là vòng lặp vô hạn.

Sửa bằng cách cập nhật biến trước khi CONTINUE:

~~~sql
DECLARE
    v_counter PLS_INTEGER := 1;
BEGIN
    WHILE v_counter <= 5 LOOP
        IF v_counter = 3 THEN
            v_counter := v_counter + 1;
            CONTINUE;
        END IF;

        DBMS_OUTPUT.PUT_LINE(v_counter);
        v_counter := v_counter + 1;
    END LOOP;
END;
/
~~~

Với WHILE, hãy kiểm tra mọi đường đi qua thân vòng lặp để bảo đảm biến điều khiển tiến triển.

## 9. CONTINUE với nhãn trong vòng lặp lồng nhau

Giống EXIT, CONTINUE có thể nhận nhãn để tác động đến vòng lặp ngoài.

### 9.1. Cú pháp

~~~sql
<<outer_loop>>
FOR i IN 1 .. 3 LOOP
    FOR j IN 1 .. 3 LOOP
        CONTINUE outer_loop WHEN j = 2;
        ...
    END LOOP;
END LOOP outer_loop;
~~~

Khi điều kiện TRUE, CONTINUE OUTER_LOOP bỏ phần còn lại của lượt vòng ngoài hiện tại và chuyển sang lượt tiếp theo của OUTER_LOOP. Vòng lặp trong bị bỏ dở ở lượt đó.

### 9.2. Ví dụ

~~~sql
BEGIN
    <<outer_loop>>
    FOR i IN 1 .. 3 LOOP
        DBMS_OUTPUT.PUT_LINE('Outer start ' || i);

        FOR j IN 1 .. 3 LOOP
            IF j = 2 THEN
                CONTINUE outer_loop;
            END IF;

            DBMS_OUTPUT.PUT_LINE('  Inner ' || j);
        END LOOP;

        DBMS_OUTPUT.PUT_LINE('Outer end ' || i);
    END LOOP outer_loop;
END;
/
~~~

Với mỗi giá trị I, khi J bằng 2, CONTINUE OUTER_LOOP chuyển thẳng sang I tiếp theo. Vì vậy:

- Inner 1 được in.
- Inner 2 và Inner 3 không được in.
- Outer end cũng bị bỏ qua vì nó nằm sau vòng lặp trong trong cùng lượt ngoài.

### 9.3. Phân biệt EXIT và CONTINUE có nhãn

| Câu lệnh | Tác động |
|---|---|
| EXIT | Kết thúc vòng lặp hiện tại |
| EXIT outer_loop | Kết thúc vòng lặp có nhãn OUTER_LOOP |
| CONTINUE | Bỏ phần còn lại của lượt hiện tại trong vòng lặp hiện tại |
| CONTINUE outer_loop | Bỏ phần còn lại của lượt vòng ngoài và sang lượt ngoài tiếp theo |

## 10. So sánh LOOP, WHILE và FOR

| Đặc điểm | LOOP | WHILE LOOP | FOR LOOP |
|---|---|---|---|
| Kiểm tra điều kiện trước thân? | Không có điều kiện đầu tự động | Có | Khoảng số điều khiển lượt |
| Có thể chạy 0 lần? | Thân bắt đầu ít nhất một lần, trừ khi thoát ngay | Có | Có |
| Tự tăng biến đếm? | Không | Không | Có |
| Cần EXIT để kết thúc bình thường? | Thường có | Không bắt buộc | Không bắt buộc |
| Phù hợp | Điểm dừng linh hoạt | Điều kiện tiếp tục rõ ràng | Khoảng số xác định |

Chọn cấu trúc theo ý định:

- Dùng LOOP khi chưa biết số lượt và cần điều kiện dừng bên trong.
- Dùng WHILE khi muốn kiểm tra điều kiện trước mỗi lượt.
- Dùng FOR khi có cận số rõ ràng hoặc cần duyệt cursor.

## 11. Cursor FOR LOOP

Cursor FOR LOOP duyệt từng dòng của một truy vấn. Oracle tự động:

1. Mở cursor.
2. Fetch một dòng vào record vòng lặp.
3. Chạy thân vòng lặp.
4. Lặp lại cho đến khi hết dòng.
5. Đóng cursor, kể cả khi thoát vòng lặp theo luồng điều khiển bình thường hoặc có exception thoát khỏi vòng lặp.

### 11.1. Cú pháp dùng truy vấn trực tiếp

~~~sql
FOR rec IN (
    SELECT employee_id, employee_name
    FROM employees
    ORDER BY employee_id
) LOOP
    statements;
END LOOP;
~~~

REC là record được khai báo ngầm cho vòng lặp và có các field tương ứng với cột trong SELECT.

### 11.2. Ví dụ

~~~sql
BEGIN
    FOR rec IN (
        SELECT employee_id, employee_name
        FROM lab_employee
        WHERE department_id = 10
        ORDER BY employee_id
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            rec.employee_id || ' - ' || rec.employee_name
        );
    END LOOP;
END;
/
~~~

Ví dụ giả định bảng LAB_EMPLOYEE có các cột được truy vấn. Thay bằng tên bảng và cột của schema thực tế.

### 11.3. Cursor FOR LOOP với cursor đã khai báo

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, employee_name
        FROM lab_employee
        ORDER BY employee_id;
BEGIN
    FOR rec IN c_employee LOOP
        DBMS_OUTPUT.PUT_LINE(
            rec.employee_id || ': ' || rec.employee_name
        );
    END LOOP;
END;
/
~~~

Cursor FOR LOOP giúp giảm code quản lý cursor thủ công. Không cần OPEN, FETCH hoặc CLOSE cho cursor được dùng trực tiếp trong FOR LOOP.

### 11.4. EXIT và CONTINUE trong cursor FOR LOOP

Có thể dùng EXIT và CONTINUE như các vòng lặp khác:

~~~sql
BEGIN
    FOR rec IN (
        SELECT employee_id, employee_name
        FROM lab_employee
        ORDER BY employee_id
    ) LOOP
        CONTINUE WHEN rec.employee_id < 100;

        DBMS_OUTPUT.PUT_LINE(rec.employee_name);

        EXIT WHEN rec.employee_id >= 200;
    END LOOP;
END;
/
~~~

Khi employee_id nhỏ hơn 100, lượt đó bị bỏ qua. Khi gặp ID từ 200 trở lên sau khi in tên, vòng lặp kết thúc. Truy vấn có ORDER BY để thứ tự xử lý xác định theo employee_id.

### 11.5. Cursor FOR LOOP và hiệu năng

Cursor FOR LOOP thuận tiện, nhưng vẫn xử lý từng dòng trong PL/SQL. Với hàng triệu dòng, chuyển dữ liệu qua lại giữa SQL engine và PL/SQL engine từng dòng có thể tốn chi phí.

Nếu mục tiêu chỉ là cập nhật hoặc xóa hàng loạt theo cùng điều kiện, hãy cân nhắc một câu UPDATE/DELETE theo tập hợp. Nếu mỗi dòng cần logic PL/SQL riêng, có thể xem xét BULK COLLECT và FORALL để giảm context switch, tùy yêu cầu và khả năng xử lý lỗi.

## 12. Vòng lặp lồng nhau

Vòng lặp lồng nhau là vòng lặp nằm bên trong thân của một vòng lặp khác. Chúng thường dùng khi xử lý ma trận, tổ hợp, hoặc nhiều nhóm con.

Ví dụ:

~~~sql
BEGIN
    FOR i IN 1 .. 3 LOOP
        FOR j IN 1 .. 2 LOOP
            DBMS_OUTPUT.PUT_LINE(
                'i=' || i || ', j=' || j
            );
        END LOOP;
    END LOOP;
END;
/
~~~

Số lượt của vòng trong được thực hiện cho mỗi lượt vòng ngoài. Ở ví dụ này có 3 × 2 = 6 lần in.

### 12.1. EXIT trong vòng lặp lồng nhau

EXIT không nhãn chỉ thoát vòng lặp gần nhất:

~~~sql
BEGIN
    FOR i IN 1 .. 2 LOOP
        FOR j IN 1 .. 4 LOOP
            EXIT WHEN j = 3;
            DBMS_OUTPUT.PUT_LINE(i || ',' || j);
        END LOOP;
    END LOOP;
END;
/
~~~

Mỗi lượt I chỉ in J = 1 và 2. Khi J = 3, vòng trong kết thúc; vòng ngoài chuyển sang I tiếp theo.

### 12.2. CONTINUE trong vòng lặp lồng nhau

~~~sql
BEGIN
    FOR i IN 1 .. 2 LOOP
        FOR j IN 1 .. 4 LOOP
            CONTINUE WHEN j = 3;
            DBMS_OUTPUT.PUT_LINE(i || ',' || j);
        END LOOP;
    END LOOP;
END;
/
~~~

Chỉ bỏ qua J = 3 trong mỗi vòng trong. Các lượt J = 4 vẫn được thực hiện.

## 13. Dùng vòng lặp để xử lý DML

Một số quy trình cần thực hiện DML theo từng bước. Ví dụ minh họa tạo bảng log xử lý số:

~~~sql
CREATE TABLE lab_loop_result (
    value_no NUMBER PRIMARY KEY,
    square_value NUMBER NOT NULL,
    created_at DATE NOT NULL
);
~~~

Dùng FOR LOOP để chèn các giá trị:

~~~sql
BEGIN
    FOR i IN 1 .. 5 LOOP
        INSERT INTO lab_loop_result (
            value_no,
            square_value,
            created_at
        )
        VALUES (
            i,
            i * i,
            SYSDATE
        );
    END LOOP;

    COMMIT;
END;
/
~~~

Kiểm tra:

~~~sql
SELECT value_no, square_value, created_at
FROM lab_loop_result
ORDER BY value_no;
~~~

Kết quả square_value là 1, 4, 9, 16 và 25.

Với ví dụ đơn giản này, một câu INSERT ... SELECT có thể hiệu quả hơn:

~~~sql
INSERT INTO lab_loop_result (
    value_no,
    square_value,
    created_at
)
SELECT
    LEVEL,
    LEVEL * LEVEL,
    SYSDATE
FROM dual
CONNECT BY LEVEL <= 5;

COMMIT;
~~~

Ví dụ so sánh cho thấy không nên dùng loop chỉ vì có thể dùng loop. SQL xử lý theo tập hợp thường là lựa chọn tốt hơn khi tất cả dòng có cùng phép biến đổi.

## 14. Dùng WHILE để thử lại với giới hạn

Một vòng lặp có thể được dùng để thử lại một thao tác tối đa N lần. Ví dụ sau chỉ mô phỏng bộ đếm thử lại, không thực hiện kết nối mạng hay thao tác bên ngoài:

~~~sql
DECLARE
    v_attempt PLS_INTEGER := 0;
    v_max_attempts CONSTANT PLS_INTEGER := 3;
    v_success BOOLEAN := FALSE;
BEGIN
    WHILE v_attempt < v_max_attempts
      AND NOT v_success
    LOOP
        v_attempt := v_attempt + 1;

        DBMS_OUTPUT.PUT_LINE(
            'Attempt ' || v_attempt
        );

        -- Mô phỏng điều kiện thành công ở lần thứ ba.
        IF v_attempt = 3 THEN
            v_success := TRUE;
        END IF;
    END LOOP;

    IF v_success THEN
        DBMS_OUTPUT.PUT_LINE('Completed');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Attempts exhausted');
    END IF;
END;
/
~~~

Khi áp dụng cho thao tác thực tế:

- Giới hạn số lần thử.
- Chỉ retry lỗi có thể phục hồi.
- Có khoảng chờ/backoff nếu hệ thống yêu cầu.
- Tránh lặp lại thao tác không idempotent mà không có khóa idempotency.
- Ghi log đủ để điều tra.

Không retry vô hạn khi lỗi là lỗi dữ liệu, lỗi quyền hoặc vi phạm constraint cố định.

## 15. CONTINUE để lọc các phần tử không cần xử lý

Giả sử cần xử lý danh sách số nhưng bỏ qua số không chia hết cho 3:

~~~sql
BEGIN
    FOR i IN 1 .. 15 LOOP
        CONTINUE WHEN MOD(i, 3) <> 0;

        DBMS_OUTPUT.PUT_LINE(
            'Process value ' || i
        );
    END LOOP;
END;
/
~~~

CONTINUE làm cho ý định “bỏ qua lượt này” rõ ràng. Với điều kiện phức tạp, có thể dùng IF để bao phần logic cần chạy:

~~~sql
BEGIN
    FOR i IN 1 .. 15 LOOP
        IF MOD(i, 3) = 0 THEN
            DBMS_OUTPUT.PUT_LINE(
                'Process value ' || i
            );
        END IF;
    END LOOP;
END;
/
~~~

Hai cách có thể cho cùng kết quả. Chọn cách dễ đọc trong ngữ cảnh thực tế; tránh lồng quá nhiều CONTINUE khiến luồng xử lý khó theo dõi.

## 16. Xử lý exception trong vòng lặp

Nếu một câu lệnh trong thân vòng lặp phát sinh exception và exception không được xử lý trong block hiện tại, luồng thực thi rời block đó. Vòng lặp không tự động tiếp tục lượt sau.

Nếu muốn một dòng lỗi không ngăn việc xử lý các dòng còn lại, có thể đặt block BEGIN...EXCEPTION...END bên trong vòng lặp.

Ví dụ:

~~~sql
BEGIN
    FOR i IN 1 .. 5 LOOP
        BEGIN
            IF i = 3 THEN
                RAISE_APPLICATION_ERROR(
                    -20001,
                    'Simulated error at value 3'
                );
            END IF;

            DBMS_OUTPUT.PUT_LINE('Processed ' || i);

        EXCEPTION
            WHEN OTHERS THEN
                DBMS_OUTPUT.PUT_LINE(
                    'Failed at ' || i || ': ' || SQLERRM
                );
        END;
    END LOOP;
END;
/
~~~

Exception được xử lý trong block con của lượt I = 3. Sau khi handler kết thúc bình thường, vòng FOR tiếp tục với I = 4.

### 16.1. Phạm vi rollback của câu lệnh lỗi

Oracle bảo đảm tính nguyên tử ở mức câu lệnh: nếu một câu DML thất bại, tác động của chính câu lệnh đó được hoàn tác. Các câu DML thành công trước đó trong transaction vẫn còn cho đến khi COMMIT hoặc ROLLBACK.

Nếu một lượt vòng lặp có nhiều câu DML và câu thứ hai lỗi, câu thứ nhất có thể vẫn còn trong transaction. Nếu cần coi cả lượt là một đơn vị, có thể dùng SAVEPOINT trước lượt và ROLLBACK TO trong exception handler:

~~~sql
DECLARE
BEGIN
    FOR i IN 1 .. 5 LOOP
        SAVEPOINT before_iteration;

        BEGIN
            INSERT INTO lab_loop_result (
                value_no, square_value, created_at
            )
            VALUES (100 + i, i * i, SYSDATE);

            IF i = 3 THEN
                RAISE_APPLICATION_ERROR(
                    -20003,
                    'Stop this iteration'
                );
            END IF;

        EXCEPTION
            WHEN OTHERS THEN
                ROLLBACK TO before_iteration;
                DBMS_OUTPUT.PUT_LINE(
                    'Rolled back iteration ' || i
                );
        END;
    END LOOP;
END;
/
~~~

Ví dụ này minh họa ranh giới hoàn tác cho từng lượt. Trong ứng dụng thật, hãy đặt tên savepoint phù hợp và thống nhất với transaction do caller quản lý; savepoint thuộc transaction của session, không phải biến cục bộ độc lập.

### 16.2. Không che giấu lỗi một cách máy móc

WHEN OTHERS có thể giúp xử lý lỗi theo từng dòng, nhưng không nên chỉ in thông báo rồi bỏ qua mọi lỗi. Cần phân loại:

- Lỗi dữ liệu có thể bỏ qua theo nghiệp vụ.
- Lỗi tạm thời có thể retry.
- Lỗi cấu hình/quyền cần dừng xử lý.
- Lỗi hệ thống cần rollback và truyền lên caller.

Nếu không thể phục hồi, hãy RAISE lại exception hoặc ghi nhận trạng thái batch thất bại theo quy trình.

## 17. Vòng lặp và biến BOOLEAN

PL/SQL có kiểu BOOLEAN trong PL/SQL, với ba trạng thái TRUE, FALSE và NULL. BOOLEAN không phải kiểu cột SQL thông thường trong nhiều phiên bản Oracle trước 23c; đừng nhầm biến BOOLEAN PL/SQL với kiểu dữ liệu lưu bảng.

Ví dụ:

~~~sql
DECLARE
    v_continue BOOLEAN := TRUE;
    v_counter PLS_INTEGER := 1;
BEGIN
    WHILE v_continue LOOP
        DBMS_OUTPUT.PUT_LINE(v_counter);

        IF v_counter >= 3 THEN
            v_continue := FALSE;
        ELSE
            v_counter := v_counter + 1;
        END IF;
    END LOOP;
END;
/
~~~

Điều kiện WHILE chỉ tiếp tục khi BOOLEAN là TRUE. Nếu biến BOOLEAN là NULL, thân không chạy. Khi dùng BOOLEAN điều khiển loop, hãy khởi tạo giá trị và bảo đảm mọi nhánh cập nhật đều có ý nghĩa.

## 18. Vòng lặp và hiệu năng: row-by-row so với set-based SQL

PL/SQL loop có chi phí điều khiển lặp và có thể phát sinh nhiều lần chuyển đổi giữa PL/SQL engine và SQL engine. Với thao tác dữ liệu hàng loạt, một câu SQL thường có thể xử lý hiệu quả hơn.

### 18.1. Cách xử lý từng dòng

~~~sql
BEGIN
    FOR rec IN (
        SELECT employee_id
        FROM lab_employee
        WHERE department_id = 10
    ) LOOP
        UPDATE lab_employee
        SET employee_status = 'INACTIVE'
        WHERE employee_id = rec.employee_id;
    END LOOP;
END;
/
~~~

### 18.2. Cách xử lý theo tập hợp

~~~sql
UPDATE lab_employee
SET employee_status = 'INACTIVE'
WHERE department_id = 10;
~~~

Nếu mọi dòng đều nhận cùng phép cập nhật, câu UPDATE theo tập hợp ngắn hơn và thường hiệu quả hơn.

### 18.3. Khi nào loop là hợp lý?

- Mỗi dòng cần quy tắc xử lý khác nhau và phụ thuộc vào kết quả trước.
- Cần gọi một thủ tục PL/SQL cho từng phần tử.
- Cần kiểm soát retry hoặc xử lý lỗi theo từng bản ghi.
- Cần duyệt cursor theo thứ tự và thực hiện logic tuần tự.
- Dữ liệu đầu vào không thể diễn đạt gọn bằng một câu SQL.

Nếu loop phải thực hiện hàng nghìn hoặc hàng triệu DML riêng lẻ, hãy đánh giá BULK COLLECT và FORALL. Bulk processing có thể giảm số lần context switch trong khi vẫn giữ khả năng xử lý theo nhóm.

## 19. BULK COLLECT và FORALL là hướng tối ưu khi cần PL/SQL

BULK COLLECT lấy nhiều dòng từ SQL vào collection; FORALL gửi nhiều DML tương ứng theo cơ chế bulk binding.

Ví dụ khái niệm:

~~~sql
DECLARE
    TYPE t_employee_ids IS TABLE OF lab_employee.employee_id%TYPE;
    v_ids t_employee_ids;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO v_ids
    FROM lab_employee
    WHERE department_id = 10;

    FORALL i IN 1 .. v_ids.COUNT
        UPDATE lab_employee
        SET employee_status = 'INACTIVE'
        WHERE employee_id = v_ids(i);
END;
/
~~~

Ví dụ giả định bảng LAB_EMPLOYEE tồn tại và có các cột tương ứng. Nếu số dòng lớn, BULK COLLECT không giới hạn có thể tiêu thụ nhiều PGA; dùng LIMIT với cursor fetch theo batch khi phù hợp. FORALL có tùy chọn SAVE EXCEPTIONS để thu thập lỗi từng phần tử, nhưng cách xử lý cần được thiết kế rõ.

Không dùng BULK COLLECT/FORALL nếu một câu SQL set-based đã đáp ứng đúng nghiệp vụ; bulk PL/SQL vẫn phức tạp hơn SQL thuần.

## 20. Các lỗi thường gặp khi viết vòng lặp

| Dấu hiệu | Nguyên nhân | Cách xử lý |
|---|---|---|
| Vòng lặp chạy vô hạn | Biến điều khiển không đổi hoặc điều kiện không thể thành FALSE | Kiểm tra mọi đường đi, giới hạn số lượt |
| WHILE không chạy | Điều kiện FALSE hoặc NULL ngay từ đầu | Kiểm tra giá trị và kiểu của biến điều khiển |
| LOOP chạy thừa một lượt | EXIT đặt sau phần xử lý cần bỏ qua | Đặt EXIT WHEN trước phần thân phù hợp hoặc dùng WHILE |
| FOR LOOP không chạy | Cận dưới lớn hơn cận trên | Kiểm tra cận; dùng REVERSE nếu muốn đếm lùi |
| Gán biến đếm FOR gây lỗi biên dịch | Biến đếm được khai báo ngầm và không được gán | Dùng biến khác hoặc WHILE/LOOP |
| EXIT chỉ thoát vòng trong | EXIT không có nhãn chỉ kết thúc loop gần nhất | Dùng EXIT label khi cần thoát loop ngoài |
| CONTINUE làm WHILE vô hạn | Bỏ qua câu lệnh cập nhật biến điều khiển | Cập nhật biến trước CONTINUE hoặc đổi cấu trúc |
| Cursor FOR LOOP không tiếp tục sau lỗi | Exception thoát khỏi block vòng lặp | Xử lý exception bên trong từng lượt nếu nghiệp vụ cho phép |
| Chương trình chậm khi xử lý nhiều dòng | DML từng dòng, nhiều context switch | Cân nhắc set-based SQL, BULK COLLECT/FORALL |
| Kết quả xử lý khác thứ tự mong đợi | SELECT không có ORDER BY | Thêm ORDER BY nếu thứ tự có ý nghĩa |

## 21. Bài tập thực hành

### Bài 1 — LOOP cơ bản

Viết LOOP in các số từ 1 đến 10. Dùng EXIT WHEN để kết thúc sau khi in số 10.

**Yêu cầu:** đặt câu lệnh tăng biến đúng vị trí và giải thích vì sao không in 11.

### Bài 2 — WHILE LOOP

Viết WHILE LOOP tính tổng các số từ 1 đến 100.

**Gợi ý:** dùng biến đếm và biến tổng; điều kiện dừng là biến đếm vượt quá 100.

### Bài 3 — FOR LOOP

Dùng FOR LOOP in bảng nhân 7 từ 7 × 1 đến 7 × 10.

### Bài 4 — FOR REVERSE

Dùng FOR REVERSE đếm ngược từ 20 đến 1. Sau đó thử cận REVERSE 20 .. 1 và giải thích vì sao không có lượt lặp.

### Bài 5 — EXIT trong vòng lặp lồng nhau

Tạo hai vòng FOR. Khi biến vòng ngoài bằng 2 và vòng trong bằng 3, dùng EXIT không nhãn. Quan sát vòng nào kết thúc.

Sau đó đổi thành EXIT outer_loop và so sánh kết quả.

### Bài 6 — CONTINUE

Viết FOR LOOP từ 1 đến 30, chỉ in các số chia hết cho 5. Dùng CONTINUE WHEN để bỏ qua các số khác.

### Bài 7 — WHILE và CONTINUE

Viết WHILE LOOP có biến đếm từ 1 đến 10, bỏ qua số 5 bằng CONTINUE.

**Yêu cầu:** bảo đảm biến đếm vẫn tăng khi bị bỏ qua số 5 và giải thích nguy cơ vòng lặp vô hạn nếu không cập nhật biến.

### Bài 8 — Cursor FOR LOOP

Dùng cursor FOR LOOP đọc nhân viên theo department_id, in employee_id và employee_name theo thứ tự tăng dần.

### Bài 9 — Exception từng dòng

Viết FOR LOOP từ 1 đến 5. Cố tình phát sinh lỗi ở lượt 3, xử lý lỗi trong block con để các lượt 4 và 5 vẫn được chạy.

### Bài 10 — Chọn SQL hay LOOP

Một bảng có 100000 nhân viên. Yêu cầu cập nhật STATUS thành INACTIVE cho tất cả nhân viên thuộc DEPARTMENT_ID = 10.

**Câu hỏi:** nên dùng một câu UPDATE hay cursor FOR LOOP? Giải thích dựa trên set-based SQL và chi phí xử lý từng dòng.

## 22. Quy trình chọn cấu trúc vòng lặp

Trước khi viết loop, hãy xác định:

1. Có biết trước số lượt không?
2. Điều kiện cần kiểm tra trước hay sau khi chạy thân?
3. Biến điều khiển do Oracle quản lý hay lập trình viên cập nhật?
4. Có cần thoát sớm hoặc bỏ qua một lượt không?
5. Có vòng lặp lồng nhau và cần tác động đến loop ngoài không?
6. Có phải duyệt kết quả SQL không?
7. Nếu một lượt lỗi, cần dừng toàn bộ hay tiếp tục dòng sau?
8. Có thể thay loop bằng một câu SQL theo tập hợp không?

Gợi ý:

| Nhu cầu | Cấu trúc |
|---|---|
| Chạy cho đến khi gặp điều kiện dừng bên trong | LOOP + EXIT WHEN |
| Chỉ chạy khi điều kiện đầu còn TRUE | WHILE LOOP |
| Lặp theo khoảng số xác định | FOR LOOP |
| Đếm từ trên xuống | FOR REVERSE |
| Duyệt từng dòng SELECT | Cursor FOR LOOP |
| Kết thúc loop hiện tại | EXIT |
| Bỏ phần còn lại của lượt hiện tại | CONTINUE |
| Thoát/bỏ lượt của loop ngoài | EXIT label / CONTINUE label |
| Cập nhật/xóa hàng loạt cùng điều kiện | Ưu tiên set-based SQL |

Sơ đồ quyết định:

~~~text
Cần lặp để xử lý công việc?
          |
          v
Có thể giải quyết bằng một câu SQL?
       /              \
     Có                Không
      |                  |
      v                  v
Set-based SQL       Duyệt cursor hay lặp số?
                         |
                   +-----+-----+
                   |           |
                 Cursor       Số lượt
                   |           |
                   v           v
             Cursor FOR     Biết cận số?
                LOOP          /    \
                            Có      Không
                            |         |
                            v         v
                         FOR LOOP   Điều kiện đầu?
                                      /    \
                                    Có      Không
                                    |         |
                                    v         v
                                  WHILE     LOOP
                                      |
                                      v
                          Cần thoát/bỏ qua lượt?
                                      |
                                      v
                                EXIT / CONTINUE
~~~

LOOP, WHILE và FOR giải quyết các kiểu lặp khác nhau trong PL/SQL. LOOP cho phép điều khiển điểm dừng linh hoạt; WHILE kiểm tra điều kiện trước mỗi lượt; FOR quản lý biến đếm theo một khoảng xác định; cursor FOR LOOP tự quản lý việc duyệt kết quả truy vấn. EXIT kết thúc vòng lặp, còn CONTINUE bỏ phần còn lại của lượt hiện tại. Khi kết hợp nhãn trong vòng lặp lồng nhau, có thể điều khiển đúng tầng cần thoát hoặc chuyển lượt. Hãy bảo đảm mọi vòng lặp có đường kết thúc, xử lý rõ điều kiện NULL và cân nhắc SQL theo tập hợp trước khi dùng xử lý từng dòng.
