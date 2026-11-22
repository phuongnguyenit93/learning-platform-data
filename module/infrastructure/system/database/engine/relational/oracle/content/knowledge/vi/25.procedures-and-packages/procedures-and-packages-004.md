# Phạm vi tác dụng của NOCOPY và xử lý tham số khi phát sinh lỗi

Trong PL/SQL, tham số OUT và IN OUT có thể phải sao chép dữ liệu giữa tham số hình thức (formal parameter) và biến thực tế (actual parameter) khi gọi procedure hoặc function. Với record, collection hoặc cấu trúc dữ liệu lớn, việc sao chép có thể tốn thời gian và bộ nhớ. Từ khóa **NOCOPY** là một gợi ý cho compiler để truyền tham số theo tham chiếu (by reference), qua đó có thể giảm chi phí sao chép.

NOCOPY có ảnh hưởng quan trọng khi chương trình phát sinh exception. Nếu compiler thực sự truyền tham chiếu, thay đổi mà procedure đã thực hiện trên tham số có thể tác động trực tiếp tới biến của caller, kể cả khi exception thoát ra ngoài. Với cách truyền có sao chép thông thường, việc copy-out của OUT/IN OUT chỉ xảy ra khi subprogram kết thúc bình thường; nếu exception không được xử lý bên trong và truyền ra caller, giá trị đang thay đổi trong formal parameter không được copy-back theo cơ chế thông thường.

Điểm cốt lõi: **NOCOPY chỉ là compiler hint, không phải cam kết rằng tham số luôn được truyền by reference.** Vì vậy, code phải đúng cả khi compiler áp dụng lẫn khi compiler bỏ qua hint. Không được dựa vào việc NOCOPY chắc chắn giữ hoặc chắc chắn hoàn tác thay đổi khi có lỗi.

## 1. Formal parameter và actual parameter

Khi gọi một procedure, tham số được khai báo trong định nghĩa procedure gọi là formal parameter. Biến hoặc biểu thức được truyền tại nơi gọi là actual parameter.

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE add_tax (
    p_amount IN OUT NUMBER
) AS
BEGIN
    p_amount := p_amount * 1.08;
END;
/

DECLARE
    l_amount NUMBER := 100;
BEGIN
    add_tax(l_amount);
    DBMS_OUTPUT.PUT_LINE(l_amount);
END;
/
~~~

Trong ví dụ:

- P_AMOUNT là formal parameter.
- L_AMOUNT là actual parameter.
- Procedure thay đổi formal parameter; sau khi procedure kết thúc bình thường, kết quả được trả về cho biến caller theo mode IN OUT.

## 2. Ba chế độ tham số IN, OUT và IN OUT

Trước khi tìm hiểu NOCOPY, cần nắm mục đích của từng mode:

| Mode | Truyền dữ liệu vào subprogram | Trả dữ liệu về caller | Có thể gán trong subprogram? |
|---|---|---|---|
| IN | Có | Không theo hợp đồng tham số | Không; tham số chỉ đọc |
| OUT | Không lấy giá trị ban đầu của actual làm dữ liệu đầu vào | Có | Có |
| IN OUT | Có | Có | Có |

### 2.1 IN

IN dùng khi subprogram chỉ cần đọc dữ liệu:

~~~sql
CREATE OR REPLACE PROCEDURE print_amount (
    p_amount IN NUMBER
) AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(p_amount);
END;
/
~~~

Tham số IN không phải mục tiêu của NOCOPY. NOCOPY được dùng với OUT và IN OUT.

### 2.2 OUT

OUT dùng khi subprogram tạo giá trị để trả về:

~~~sql
CREATE OR REPLACE PROCEDURE get_employee_count (
    p_count OUT PLS_INTEGER
) AS
BEGIN
    SELECT COUNT(*)
    INTO p_count
    FROM employees;
END;
/
~~~

Formal parameter OUT không dùng giá trị hiện có của actual làm đầu vào. Subprogram cần gán giá trị trước khi caller sử dụng kết quả.

### 2.3 IN OUT

IN OUT dùng khi subprogram nhận một giá trị hiện tại, xử lý nó và trả giá trị mới:

~~~sql
CREATE OR REPLACE PROCEDURE apply_discount (
    p_amount IN OUT NUMBER
) AS
BEGIN
    p_amount := p_amount * 0.90;
END;
/
~~~

Giá trị ban đầu của actual được dùng làm đầu vào; giá trị mới được trả về caller khi subprogram hoàn tất bình thường.

## 3. Truyền tham số theo giá trị và theo tham chiếu

Hai khái niệm cần phân biệt:

- **Pass by value / copy semantics:** subprogram làm việc với một bản sao. Khi kết thúc bình thường, giá trị OUT hoặc IN OUT được copy về actual parameter.
- **Pass by reference:** formal parameter tham chiếu trực tiếp tới vùng dữ liệu của actual parameter. Thay đổi qua formal có thể tác động trực tiếp tới actual.

Mô hình copy:

~~~text
Caller variable
      |
      | copy-in (IN OUT)
      v
Formal parameter copy
      |
      | subprogram modifies copy
      v
Formal parameter result
      |
      | copy-out on normal return
      v
Caller variable updated
~~~

Mô hình reference:

~~~text
Caller variable <-------------------+
      ^                              |
      |                              |
      +---- Formal parameter --------+
                |
                v
          Subprogram writes
          directly to caller data
~~~

Đây là mô hình khái niệm để hiểu hành vi. Cách compiler triển khai thực tế phụ thuộc kiểu dữ liệu, actual argument, ngữ cảnh gọi và các điều kiện tối ưu.

## 4. NOCOPY là gì?

NOCOPY là một hint đặt trên tham số OUT hoặc IN OUT. Hint yêu cầu PL/SQL compiler truyền tham số theo tham chiếu nếu có thể, thay vì tạo bản sao đầy đủ.

Cú pháp:

~~~sql
PROCEDURE process_items (
    p_items IN OUT NOCOPY t_item_table
);
~~~

Ví dụ khai báo package:

~~~sql
CREATE OR REPLACE PACKAGE item_api AS
    TYPE t_item_table IS TABLE OF NUMBER
        INDEX BY PLS_INTEGER;

    PROCEDURE increase_values (
        p_items IN OUT NOCOPY t_item_table
    );
END item_api;
/
~~~

Phần package body khai báo cùng mode và NOCOPY:

~~~sql
CREATE OR REPLACE PACKAGE BODY item_api AS
    PROCEDURE increase_values (
        p_items IN OUT NOCOPY t_item_table
    ) AS
    BEGIN
        FOR i IN 1 .. p_items.COUNT LOOP
            p_items(i) := p_items(i) + 1;
        END LOOP;
    END increase_values;
END item_api;
/
~~~

NOCOPY không làm thay đổi ý nghĩa nghiệp vụ của mode OUT hoặc IN OUT. Nó gợi ý compiler cách truyền dữ liệu để có thể tránh sao chép.

### 4.1 NOCOPY không phải một kiểu dữ liệu

NOCOPY không phải datatype, không phải constraint và không phải transaction option. Nó là một hint ở khai báo tham số.

Các kiểu thường được cân nhắc:

- Collection có nhiều phần tử.
- Nested table hoặc associative array.
- VARRAY có kích thước lớn.
- Record có nhiều trường hoặc trường dữ liệu lớn.
- Cấu trúc PL/SQL có chi phí sao chép đáng kể.

Với scalar nhỏ như NUMBER hoặc VARCHAR2 ngắn, lợi ích thường không đáng kể. Chỉ thêm NOCOPY khi đo đạc cho thấy có chi phí truyền tham số cần tối ưu.

## 5. Vì sao NOCOPY có thể cải thiện hiệu năng?

Giả sử một procedure nhận collection chứa hàng trăm nghìn phần tử:

~~~sql
TYPE t_number_table IS TABLE OF NUMBER
    INDEX BY PLS_INTEGER;
~~~

Nếu mỗi lần gọi phải sao chép toàn bộ collection, chi phí có thể gồm:

- Cấp phát vùng nhớ cho bản sao.
- Copy từng phần tử.
- Copy kết quả trở lại caller khi procedure kết thúc.
- Tăng áp lực bộ nhớ khi nhiều session gọi đồng thời.

Nếu NOCOPY được compiler áp dụng, procedure có thể làm việc trực tiếp với dữ liệu của caller, giảm một hoặc nhiều lần copy.

Tuy nhiên:

- Không có cam kết rằng hint sẽ luôn được áp dụng.
- Không phải mọi tham số lớn đều được truyền reference trong mọi tình huống.
- NOCOPY không làm giảm số lần duyệt collection hoặc chi phí thuật toán bên trong procedure.
- Lợi ích phải được đo trên dữ liệu, phiên bản và workload thực tế.

## 6. NOCOPY là hint, compiler có thể bỏ qua

Điều quan trọng nhất về mặt hợp đồng là compiler có thể không áp dụng NOCOPY. Khi không thể truyền tham chiếu an toàn hoặc cần chuyển đổi dữ liệu, compiler có thể dùng cách truyền có sao chép.

Các tình huống có thể khiến hint không được áp dụng bao gồm:

- Kiểu actual và formal cần chuyển đổi dữ liệu.
- Actual argument hoặc cách truyền không cho phép tham chiếu trực tiếp an toàn.
- Ngữ cảnh gọi hoặc đặc điểm kiểu dữ liệu buộc compiler tạo temporary.
- Một số trường hợp truyền tham số qua ranh giới remote/distributed call.

Danh sách điều kiện cụ thể phụ thuộc phiên bản và ngữ cảnh; không nên coi các ví dụ này là danh sách đầy đủ.

Không có thuộc tính SQL% hoặc PL/SQL runtime flag đơn giản để hỏi “lần gọi này NOCOPY có được compiler áp dụng không?”. Thiết kế đúng phải chấp nhận cả hai cách triển khai.

### 6.1 Không viết logic phụ thuộc NOCOPY chắc chắn có hiệu lực

Giả sử caller mong đợi biến của mình luôn giữ các thay đổi một phần khi procedure lỗi vì đã khai báo NOCOPY. Điều này không an toàn: nếu compiler bỏ qua hint, actual có thể không nhận các thay đổi chưa copy-out khi exception thoát ra.

Ngược lại, nếu caller cho rằng exception luôn giữ nguyên actual vì tham số OUT/IN OUT được copy, code có thể sai khi compiler áp dụng NOCOPY và đã ghi trực tiếp lên actual.

Hãy định nghĩa hợp đồng exception độc lập với việc compiler có áp dụng hint hay không.

## 7. Phạm vi tác dụng của NOCOPY khi subprogram kết thúc bình thường

Khi subprogram kết thúc bình thường:

- OUT trả kết quả về actual.
- IN OUT trả giá trị đã cập nhật về actual.
- Nếu NOCOPY được áp dụng, thay đổi có thể đã tác động trực tiếp lên actual trong quá trình thực thi.
- Nếu NOCOPY bị bỏ qua, compiler có thể thực hiện copy-out theo cơ chế thông thường.

Với caller, kết quả cuối khi return bình thường vẫn là dữ liệu mà procedure đã trả theo hợp đồng OUT/IN OUT.

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE add_bonus (
    p_salary IN OUT NOCOPY NUMBER
) AS
BEGIN
    p_salary := p_salary + 1000;
END;
/

DECLARE
    l_salary NUMBER := 20000;
BEGIN
    add_bonus(l_salary);
    DBMS_OUTPUT.PUT_LINE(l_salary);
END;
/
~~~

Sau khi procedure kết thúc bình thường, caller nhận giá trị 21000.

## 8. Tham số khi phát sinh exception

Đây là nơi NOCOPY ảnh hưởng rõ nhất tới hành vi chương trình.

### 8.1 OUT/IN OUT theo cơ chế copy thông thường

Với cách truyền có sao chép:

1. OUT/IN OUT formal parameter được subprogram xử lý trong vùng dữ liệu của nó.
2. Subprogram có thể thay đổi formal parameter.
3. Nếu subprogram kết thúc bình thường, giá trị được copy-out về actual.
4. Nếu exception không được xử lý bên trong và truyền ra caller, copy-out thông thường không xảy ra.

Với IN OUT, actual của caller giữ giá trị trước lời gọi nếu exception thoát ra và copy-out không xảy ra. Với OUT, caller không nhận kết quả mới từ lần gọi thất bại.

### 8.2 NOCOPY được áp dụng

Nếu compiler áp dụng NOCOPY, formal parameter tham chiếu trực tiếp tới actual. Những thay đổi đã thực hiện có thể đã xuất hiện trong biến caller trước khi subprogram kết thúc.

Nếu sau đó exception phát sinh và thoát ra:

- Thay đổi đã ghi trực tiếp có thể vẫn còn trong actual.
- PL/SQL không tự khôi phục giá trị ban đầu của biến caller.
- Caller phải có chiến lược phục hồi nếu hợp đồng yêu cầu trạng thái không đổi khi lỗi.

### 8.3 Bảng so sánh

| Tình huống | OUT/IN OUT với copy semantics | OUT/IN OUT khi NOCOPY được áp dụng |
|---|---|---|
| Subprogram return bình thường | Copy kết quả về actual | Thay đổi đã tác động trực tiếp; caller thấy kết quả |
| Exception được xử lý bên trong và subprogram return bình thường | Kết quả hiện tại được copy-out | Thay đổi trực tiếp vẫn ở actual, trừ khi code tự khôi phục |
| Exception không được xử lý và truyền ra caller | Không copy-out kết quả của lần gọi | Thay đổi đã ghi trực tiếp có thể còn |
| Compiler bỏ qua NOCOPY | Hành vi như copy semantics | Không được giả định reference |

Vì compiler có thể bỏ qua hint, ứng dụng không được dựa vào một cột trong bảng này như cam kết cho mọi lần gọi có chữ NOCOPY.

## 9. Ví dụ collection: lỗi sau khi đã sửa một phần

Tạo package:

~~~sql
CREATE OR REPLACE PACKAGE nocopy_demo AS
    TYPE t_values IS TABLE OF NUMBER
        INDEX BY PLS_INTEGER;

    PROCEDURE change_then_fail (
        p_values IN OUT NOCOPY t_values
    );
END nocopy_demo;
/
~~~

Package body:

~~~sql
CREATE OR REPLACE PACKAGE BODY nocopy_demo AS
    PROCEDURE change_then_fail (
        p_values IN OUT NOCOPY t_values
    ) AS
    BEGIN
        p_values(1) := p_values(1) + 100;
        p_values(2) := p_values(2) + 200;

        RAISE_APPLICATION_ERROR(
            -20031,
            'Intentional failure after partial modification'
        );
    END change_then_fail;
END nocopy_demo;
/
~~~

Caller:

~~~sql
DECLARE
    l_values nocopy_demo.t_values;
BEGIN
    l_values(1) := 10;
    l_values(2) := 20;

    BEGIN
        nocopy_demo.change_then_fail(l_values);
    EXCEPTION
        WHEN OTHERS THEN
            DBMS_OUTPUT.PUT_LINE(
                'Error: ' || SQLERRM
            );
    END;

    DBMS_OUTPUT.PUT_LINE('Value 1: ' || l_values(1));
    DBMS_OUTPUT.PUT_LINE('Value 2: ' || l_values(2));
END;
/
~~~

Nếu NOCOPY được áp dụng, caller có thể thấy 110 và 220 dù procedure phát sinh exception. Nếu compiler bỏ qua hint, caller có thể vẫn thấy 10 và 20 vì procedure không return bình thường để copy-out.

Đây là ví dụ minh họa tính không xác định của việc compiler áp dụng hint. Không dùng kết quả của một lần chạy trên một phiên bản làm cam kết cho phiên bản hoặc kiểu actual khác.

## 10. Exception handler bên trong procedure thay đổi kết quả copy-out

Xét procedure có exception handler:

~~~sql
CREATE OR REPLACE PROCEDURE change_and_handle (
    p_value IN OUT NUMBER
) AS
BEGIN
    p_value := p_value + 100;

    RAISE_APPLICATION_ERROR(-20032, 'Test error');
EXCEPTION
    WHEN OTHERS THEN
        -- Xử lý lỗi và không ném lại.
        NULL;
END;
/
~~~

Procedure bắt exception bên trong và kết thúc bình thường. Vì vậy, theo copy semantics thông thường, giá trị hiện tại của formal parameter được copy-out về actual khi procedure return.

Nếu procedure dùng IN OUT NOCOPY, thay đổi đã tác động trực tiếp nếu hint được áp dụng. Dù theo cách truyền nào, caller vẫn có thể nhận giá trị đã thay đổi vì exception đã được xử lý và procedure return bình thường.

Điều này cho thấy “có exception xảy ra” chưa đủ để suy luận copy-out có xảy ra hay không. Cần hỏi exception có thoát khỏi subprogram hay đã được xử lý bên trong.

### 10.1 Nuốt exception có thể tạo kết quả thành công giả

Handler:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        NULL;
~~~

có thể khiến caller tưởng procedure hoàn tất thành công. Nếu dữ liệu tham số đã bị sửa một phần, caller có thể tiếp tục dùng trạng thái không hợp lệ.

Nếu không thể khôi phục trạng thái hợp lệ, hãy ném lại lỗi:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        -- Ghi nhận thông tin cần thiết nếu phù hợp.
        RAISE;
~~~

Không bắt mọi exception rồi bỏ qua chỉ để tránh lỗi hiển thị.

## 11. NOCOPY không tự rollback dữ liệu PL/SQL

Một hiểu nhầm quan trọng là khi gọi ROLLBACK, mọi thay đổi trong procedure đều được khôi phục. Điều đó chỉ áp dụng cho thay đổi database thuộc transaction, không áp dụng cho giá trị biến PL/SQL trong bộ nhớ.

Ví dụ:

~~~sql
DECLARE
    l_value NUMBER := 10;
BEGIN
    l_value := l_value + 5;
    ROLLBACK;

    DBMS_OUTPUT.PUT_LINE(l_value);
END;
/
~~~

Giá trị l_value vẫn là 15. ROLLBACK không khôi phục biến PL/SQL về 10.

Tương tự, nếu procedure dùng NOCOPY sửa collection rồi phát sinh exception, caller không thể kỳ vọng ROLLBACK database sẽ phục hồi collection. Muốn phục hồi biến, cần code lưu bản gốc hoặc tự bù trừ giá trị.

### 11.1 Database transaction và tham số là hai phạm vi khác nhau

| Loại thay đổi | ROLLBACK database có hoàn tác không? |
|---|---|
| INSERT/UPDATE/DELETE chưa commit trong transaction | Có |
| Giá trị NUMBER/VARCHAR2 trong biến PL/SQL | Không |
| Phần tử collection trong bộ nhớ PL/SQL | Không |
| Field của record PL/SQL | Không |
| Thay đổi đã COMMIT trước đó | Không |
| Side effect ngoài database như email/API | Không tự động |

Nếu procedure vừa sửa tham số NOCOPY vừa chạy DML, exception có thể để lại hai trạng thái khác nhau: tham số trong bộ nhớ đã thay đổi, còn DML chưa commit có thể được caller rollback. Phải thiết kế hợp đồng lỗi cho cả hai phạm vi.

## 12. Phạm vi NOCOPY đối với collection và record

NOCOPY thường có giá trị rõ nhất với cấu trúc lớn.

### 12.1 Associative array

~~~sql
TYPE t_amounts IS TABLE OF NUMBER
    INDEX BY PLS_INTEGER;

PROCEDURE recalculate (
    p_amounts IN OUT NOCOPY t_amounts
);
~~~

Collection có thể chứa nhiều phần tử; sao chép toàn bộ trước và sau lời gọi có thể tốn chi phí.

### 12.2 Nested table

~~~sql
TYPE t_employee_ids IS TABLE OF NUMBER;

PROCEDURE normalize_ids (
    p_ids IN OUT NOCOPY t_employee_ids
);
~~~

Nested table có thể được truyền giữa các procedure PL/SQL. Hãy xác định rõ cách xử lý collection rỗng, phần tử NULL và thứ tự phần tử.

### 12.3 VARRAY

~~~sql
TYPE t_scores IS VARRAY(10000) OF NUMBER;

PROCEDURE adjust_scores (
    p_scores IN OUT NOCOPY t_scores
);
~~~

VARRAY có giới hạn số phần tử tối đa và giữ thứ tự. Với VARRAY lớn, NOCOPY có thể giảm chi phí copy nếu compiler áp dụng.

### 12.4 Record

~~~sql
TYPE t_employee_record IS RECORD (
    employee_id NUMBER,
    employee_name VARCHAR2(200),
    salary NUMBER(14,2),
    notes CLOB
);

PROCEDURE update_employee (
    p_employee IN OUT NOCOPY t_employee_record
);
~~~

Record có nhiều field hoặc chứa cấu trúc lớn có thể tốn chi phí sao chép. Cần kiểm tra tương thích kiểu formal/actual và cách sử dụng LOB.

### 12.5 Không phải mọi kiểu lớn đều tự động được hưởng lợi

Kích thước dữ liệu là một yếu tố, nhưng compiler còn xét kiểu, conversion và ngữ cảnh gọi. Đừng kết luận NOCOPY chắc chắn được áp dụng chỉ vì collection có nhiều phần tử hoặc record chứa CLOB.

## 13. Aliasing: cùng một biến được truyền cho nhiều tham số

Một rủi ro khó thấy của NOCOPY là aliasing: nhiều formal parameter cùng tham chiếu tới một actual parameter hoặc các vùng dữ liệu chồng lấn.

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE adjust_two_values (
    p_first  IN OUT NOCOPY NUMBER,
    p_second IN OUT NOCOPY NUMBER
) AS
BEGIN
    p_first := p_first + 10;
    p_second := p_second * 2;
END;
/

DECLARE
    l_value NUMBER := 5;
BEGIN
    adjust_two_values(l_value, l_value);
    DBMS_OUTPUT.PUT_LINE(l_value);
END;
/
~~~

Ở lời gọi trên, cùng một actual L_VALUE được truyền vào hai formal parameter. Nếu cả hai được truyền reference, thao tác qua P_FIRST có thể ảnh hưởng giá trị mà P_SECOND nhìn thấy. Nếu compiler dùng temporary/copy cho một tham số, kết quả quan sát có thể khác.

Không dựa vào một thứ tự cập nhật cụ thể trong trường hợp aliasing. Hãy tránh truyền cùng một actual vào nhiều tham số OUT/IN OUT khi các tham số có thể ghi lên dữ liệu đó, đặc biệt khi dùng NOCOPY.

### 13.1 Aliasing giữa field hoặc phần tử

Rủi ro không chỉ là truyền cùng một biến hai lần. Actual arguments có thể là các phần tử hoặc field liên quan của cùng một cấu trúc. Khi nhiều formal có thể ghi vào vùng dữ liệu chồng lấn, kết quả phụ thuộc cách truyền và thứ tự thao tác.

Thiết kế interface để mỗi tham số có vùng dữ liệu độc lập, hoặc chỉ truyền một record/collection duy nhất nếu các field cần được cập nhật như một đơn vị.

### 13.2 Đừng dùng NOCOPY như cơ chế đồng bộ

NOCOPY không cung cấp khóa, transaction isolation hay thread safety. Nó chỉ liên quan tới cách tham số được truyền trong lời gọi PL/SQL. Nó không bảo vệ biến khỏi việc truy cập đồng thời ở các cơ chế khác và không thay thế thiết kế đồng bộ.

## 14. Thiết kế hợp đồng lỗi khi dùng NOCOPY

Trước khi thêm NOCOPY, hãy xác định caller cần hành vi nào khi procedure lỗi.

### 14.1 Hợp đồng all-or-nothing

Yêu cầu: nếu procedure thất bại, caller phải giữ nguyên collection ban đầu.

Một cách là làm việc trên bản sao cục bộ rồi chỉ gán lại khi tất cả bước thành công:

~~~sql
PROCEDURE transform_safely (
    p_values IN OUT t_values
) AS
    l_work t_values := p_values;
BEGIN
    -- Chỉ sửa bản làm việc.
    FOR i IN 1 .. l_work.COUNT LOOP
        l_work(i) := l_work(i) * 2;
    END LOOP;

    -- Chỉ công bố kết quả sau khi xử lý hoàn tất.
    p_values := l_work;
END transform_safely;
~~~

Mẫu này có chi phí sao chép, nhưng hợp đồng trạng thái rõ ràng hơn. Nếu cần NOCOPY để tránh copy-in/copy-out, có thể thiết kế API khác với bước validate trước và bước apply không còn phát sinh lỗi có thể dự đoán. Tuy vậy, lỗi runtime vẫn có thể xảy ra; muốn all-or-nothing thật sự phải có cơ chế khôi phục.

### 14.2 Hợp đồng cho phép partial progress

Một số xử lý batch có thể chấp nhận kết quả một phần:

- Phần tử nào thành công được giữ.
- Phần tử nào lỗi được ghi vào danh sách lỗi.
- Caller nhận tổng số thành công và danh sách phần tử thất bại.

Trong trường hợp đó, đừng để exception bất ngờ là cơ chế duy nhất báo tiến độ. Hãy thiết kế kết quả rõ ràng, ví dụ collection trạng thái, danh sách lỗi hoặc record kết quả.

### 14.3 Validate trước khi mutate

Nếu có thể, thực hiện kiểm tra đầu vào trước khi sửa collection:

1. Kiểm tra collection không NULL/rỗng theo yêu cầu.
2. Kiểm tra index và phần tử bắt buộc.
3. Kiểm tra miền giá trị.
4. Tính toán các giá trị có thể gây lỗi.
5. Chỉ sau đó mới cập nhật dữ liệu.

Validation trước giúp giảm khả năng lỗi giữa chừng, nhưng không loại bỏ mọi exception như lỗi bộ nhớ hoặc lỗi phát sinh từ lời gọi phụ.

### 14.4 Khôi phục thủ công khi lỗi

Nếu procedure đã sửa trực tiếp actual qua NOCOPY, exception handler có thể khôi phục giá trị nếu có bản gốc:

~~~sql
PROCEDURE transform_with_restore (
    p_values IN OUT NOCOPY t_values
) AS
    l_original t_values := p_values;
BEGIN
    -- Thực hiện các thay đổi trên p_values.
    ...
EXCEPTION
    WHEN OTHERS THEN
        p_values := l_original;
        RAISE;
END transform_with_restore;
~~~

Mẫu này minh họa cách khôi phục nội dung trong bộ nhớ. Bản sao l_original có chi phí bộ nhớ/copy và việc gán lại cũng có thể phát sinh lỗi. Cần điều chỉnh cho đúng kiểu collection và cách xử lý sparse collection; dấu ba chấm không phải câu lệnh PL/SQL có thể chạy.

Nếu không cần tối ưu NOCOPY sau khi đã phải sao chép toàn bộ để rollback, có thể bỏ NOCOPY để hợp đồng dễ hiểu hơn.

## 15. NOCOPY và transaction database

Một procedure có thể nhận collection NOCOPY và đồng thời ghi bảng:

~~~sql
PROCEDURE apply_batch (
    p_values IN OUT NOCOPY t_values
) AS
BEGIN
    -- Sửa collection trong bộ nhớ.
    p_values(1) := p_values(1) + 1;

    -- Ghi database.
    UPDATE batch_control
    SET processed_count = processed_count + 1
    WHERE batch_id = 10;

    -- Có thể phát sinh lỗi sau hai thay đổi trên.
    RAISE_APPLICATION_ERROR(-20040, 'Batch failed');
END apply_batch;
~~~

Nếu caller bắt exception và ROLLBACK:

- UPDATE batch_control chưa commit có thể được rollback.
- Thay đổi p_values trong bộ nhớ không được ROLLBACK database phục hồi.
- Nếu NOCOPY được áp dụng, caller có thể vẫn thấy phần tử collection đã thay đổi.

Vì vậy, khi một procedure có cả DML và tham số NOCOPY, cần thiết kế hai chính sách:

1. Transaction policy cho thay đổi database.
2. Recovery policy cho dữ liệu trong bộ nhớ.

Không coi một lệnh ROLLBACK là đủ để khôi phục toàn bộ trạng thái chương trình.

## 16. NOCOPY trong package specification và body

Nếu procedure được khai báo trong package specification, khai báo trong package body phải tương thích với specification:

~~~sql
CREATE OR REPLACE PACKAGE payroll_api AS
    TYPE t_salary_list IS TABLE OF NUMBER
        INDEX BY PLS_INTEGER;

    PROCEDURE recalculate (
        p_salaries IN OUT NOCOPY t_salary_list
    );
END payroll_api;
/
~~~

~~~sql
CREATE OR REPLACE PACKAGE BODY payroll_api AS
    PROCEDURE recalculate (
        p_salaries IN OUT NOCOPY t_salary_list
    ) AS
    BEGIN
        FOR i IN 1 .. p_salaries.COUNT LOOP
            p_salaries(i) := ROUND(p_salaries(i) * 1.05, 2);
        END LOOP;
    END recalculate;
END payroll_api;
/
~~~

Đặt NOCOPY ở interface công khai làm rõ rằng API cho phép compiler tối ưu truyền tham số. Người dùng package vẫn phải tuân theo hợp đồng exception và aliasing an toàn.

Không thêm hoặc bỏ NOCOPY tùy tiện giữa specification và body. Khi thay đổi chữ ký public API, biên dịch lại các dependent object và kiểm tra tương thích.

## 17. NOCOPY và overload

Package có thể overload procedure theo kiểu tham số. NOCOPY không phải một datatype và không nên được dùng để tạo khác biệt overload. Hai chữ ký chỉ khác hint truyền tham số không tạo thành hai overload có ý nghĩa kiểu dữ liệu khác nhau.

Khi thiết kế overload:

- Dùng datatype và số lượng/thứ tự tham số để phân biệt.
- Giữ mode và NOCOPY nhất quán với ý định của API.
- Tránh chữ ký khiến lời gọi có thể mơ hồ do implicit conversion.

## 18. Cách kiểm thử NOCOPY

NOCOPY là hint nên kiểm thử cần xác nhận cả tính đúng đắn lẫn hiệu năng.

### 18.1 Kiểm thử đường thành công

1. Tạo collection có kích thước đại diện.
2. Gọi procedure không có lỗi.
3. Xác nhận caller nhận đúng kết quả.
4. So sánh phiên bản có và không có NOCOPY.

### 18.2 Kiểm thử exception sau thay đổi một phần

1. Khởi tạo actual parameter với dữ liệu xác định.
2. Procedure sửa một vài phần tử.
3. Cố ý phát sinh exception.
4. Bắt exception ở caller.
5. Quan sát actual parameter.
6. Lặp lại trên môi trường/compiler tương ứng và không dựa vào kết quả partial update như một cam kết.

Mục tiêu là chứng minh API không phụ thuộc vào việc compiler áp dụng hint.

### 18.3 Kiểm thử aliasing

Thử truyền cùng một actual vào nhiều tham số OUT/IN OUT. Nếu logic có thể bị ảnh hưởng, sửa API để không cho phép lời gọi đó hoặc thêm validation phù hợp.

### 18.4 Benchmark

Đo:

- Thời gian gọi với collection nhỏ và lớn.
- Mức sử dụng bộ nhớ khi nhiều lần gọi.
- Số phần tử và kiểu dữ liệu thực tế.
- Tác động khi có nhiều session đồng thời.
- Chi phí của validation và bản sao dự phòng.

Benchmark phải dùng cùng dữ liệu, cùng thuật toán, cùng cách biên dịch và workload tương đương. Chênh lệch của một lần chạy đơn lẻ không đủ để kết luận NOCOPY luôn nhanh hơn.

## 19. Các mẫu code nên và không nên dùng

### 19.1 Nên: lưu kết quả và kiểm soát lỗi rõ ràng

~~~sql
PROCEDURE normalize (
    p_values IN OUT NOCOPY t_values
) AS
BEGIN
    validate_values(p_values);
    normalize_values(p_values);
EXCEPTION
    WHEN OTHERS THEN
        RAISE;
END normalize;
~~~

Ví dụ trên minh họa việc tách validation và xử lý, đồng thời không nuốt exception. Trong code thực tế, cần định nghĩa rõ caller có chấp nhận partial mutation hay không.

### 19.2 Không nên: giả định NOCOPY luôn rollback khi lỗi

~~~sql
PROCEDURE unsafe_update (
    p_values IN OUT NOCOPY t_values
) AS
BEGIN
    p_values(1) := 999;
    RAISE_APPLICATION_ERROR(-20050, 'Failure');
END;
~~~

Không được thiết kế caller dựa trên giả định rằng sau exception, p_values chắc chắn vẫn là dữ liệu cũ. Nếu NOCOPY được áp dụng, thay đổi có thể đã tác động trực tiếp.

### 19.3 Không nên: nuốt exception và tiếp tục

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        NULL;
~~~

Caller không biết thao tác đã thất bại; dữ liệu NOCOPY có thể đang ở trạng thái một phần. Hãy xử lý lỗi có chủ đích và truyền kết quả/trạng thái rõ ràng.

### 19.4 Không nên: alias cùng actual ở nhiều tham số ghi

~~~sql
update_two_values(
    p_first  => l_values,
    p_second => l_values
);
~~~

Nếu cả hai tham số có thể ghi và có NOCOPY, tránh lời gọi aliasing. Hãy dùng hai biến riêng hoặc một tham số record chứa các field cần cập nhật.

## 20. Lựa chọn có dùng NOCOPY hay không

| Điều kiện | Khuyến nghị |
|---|---|
| Tham số là collection/record lớn, chi phí copy đo được | Có thể thử NOCOPY |
| Tham số là scalar nhỏ | Thường không cần |
| API cần giữ nguyên actual nếu lỗi | Ưu tiên copy semantics hoặc tự thiết kế rollback dữ liệu trong bộ nhớ |
| API cho phép partial progress | Có thể dùng NOCOPY nếu caller được thông báo rõ trạng thái |
| Actual có thể được truyền vào nhiều tham số ghi | Tránh NOCOPY/aliasing hoặc sửa interface |
| Kiểu actual cần conversion | Không giả định compiler áp dụng NOCOPY |
| Chưa có benchmark | Chưa có cơ sở để thêm hint |
| Code phụ thuộc chắc chắn vào việc hint được áp dụng | Thiết kế lại vì hint không được bảo đảm |

## 21. Lỗi và hiểu nhầm thường gặp

| Hiểu nhầm hoặc triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| NOCOPY bảo đảm truyền reference | NOCOPY chỉ là hint | Thiết kế đúng cả khi hint bị bỏ qua |
| Exception luôn giữ nguyên actual | Reference có thể đã ghi trực tiếp vào actual | Định nghĩa recovery contract |
| ROLLBACK khôi phục collection | ROLLBACK chỉ xử lý thay đổi database trong transaction | Tự khôi phục biến/collection |
| Procedure bắt exception rồi return bình thường nhưng caller không nhận giá trị | Exception đã được xử lý nên copy-out có thể diễn ra | Kiểm tra handler có nuốt lỗi và có khôi phục dữ liệu không |
| Hai tham số cùng nhận một biến cho kết quả khó đoán | Aliasing giữa formal parameters | Tránh truyền cùng actual cho nhiều tham số ghi |
| Thêm NOCOPY làm thuật toán nhanh rõ rệt | Chi phí có thể nằm ở xử lý nội bộ hoặc SQL | Benchmark toàn bộ workload |
| NOCOPY dùng được với IN | Hint dành cho OUT/IN OUT | Chọn mode phù hợp |
| Tham số lớn chắc chắn được truyền reference | Compiler có thể cần temporary hoặc conversion | Không giả định cách truyền |
| Exception handler luôn tự rollback dữ liệu | Exception không tự rollback biến PL/SQL | Quản lý biến và transaction riêng |

## 22. Bài thực hành tự kiểm tra

Các bài tập nên chạy trong schema thử nghiệm và dùng collection/record PL/SQL.

### Bài 1 — OUT và IN OUT

Viết hai procedure: một procedure OUT trả số lượng hàng, một procedure IN OUT tăng giá trị đầu vào. Gọi từ anonymous block và quan sát giá trị caller sau khi return bình thường.

### Bài 2 — Copy semantics khi exception

Viết procedure IN OUT không có NOCOPY, sửa formal parameter rồi ném exception không được xử lý bên trong. Bắt lỗi ở caller và quan sát actual parameter.

### Bài 3 — NOCOPY và partial mutation

Lặp lại bài 2 với NOCOPY trên collection. Quan sát actual parameter sau lỗi. Giải thích vì sao kết quả không được coi là bảo đảm cho mọi compiler context.

### Bài 4 — Exception handler nội bộ

Bắt exception trong procedure rồi return bình thường. So sánh với trường hợp re-raise exception. Giải thích ảnh hưởng tới copy-out.

### Bài 5 — Collection lớn

Tạo collection có nhiều phần tử, viết hai procedure xử lý cùng thuật toán với và không có NOCOPY. Benchmark thời gian và bộ nhớ trong điều kiện tương đương.

### Bài 6 — Aliasing

Truyền cùng một biến cho hai tham số IN OUT. Thử có và không có NOCOPY. Ghi nhận các giá trị và giải thích vì sao API không nên dựa vào thứ tự cập nhật khi aliasing.

### Bài 7 — Rollback database không rollback biến

Trong cùng một block, thay đổi collection, chạy UPDATE bảng, sau đó phát sinh exception. Bắt lỗi, ROLLBACK và kiểm tra cả dữ liệu bảng lẫn collection.

### Bài 8 — All-or-nothing

Thiết kế procedure xử lý collection bằng một bản làm việc cục bộ, chỉ gán lại tham số khi tất cả bước thành công. So sánh độ an toàn và chi phí copy với NOCOPY.

### Bài 9 — Partial progress

Thiết kế procedure trả về số phần tử thành công và danh sách phần tử lỗi thay vì ném exception ngay ở phần tử đầu tiên. Xác định hợp đồng caller nhận kết quả một phần.

### Bài 10 — Package API

Đưa collection type và procedure NOCOPY vào package specification/body. Biên dịch, gọi từ anonymous block và kiểm tra lỗi chữ ký khi khai báo không nhất quán.

## 23. Checklist trước khi đưa NOCOPY vào production

- Tham số là OUT hoặc IN OUT và có kích thước đủ lớn để việc copy đáng quan tâm?
- Có benchmark chứng minh lợi ích?
- Code vẫn đúng khi compiler bỏ qua NOCOPY?
- Caller có biết trạng thái tham số sau exception không?
- Có cần giữ nguyên actual parameter khi procedure thất bại?
- Có xử lý riêng biến PL/SQL và transaction database không?
- Có exception handler nào nuốt lỗi hoặc return bình thường sau khi chỉ xử lý một phần?
- Có khả năng cùng một actual được truyền vào nhiều tham số ghi?
- Có actual argument cần conversion hoặc temporary?
- Package specification và body có khai báo tương thích?
- API có tài liệu về partial progress và lỗi?
- Đã kiểm thử với collection/record kích thước đại diện và nhiều session?

## 24. Ghi nhớ

| Khái niệm | Quy tắc thực hành |
|---|---|
| IN | Nhận dữ liệu để đọc |
| OUT | Trả dữ liệu do subprogram tạo |
| IN OUT | Nhận giá trị cũ và trả giá trị mới |
| NOCOPY | Hint để compiler có thể truyền OUT/IN OUT theo tham chiếu |
| Copy semantics | Copy-out thông thường xảy ra khi subprogram return bình thường |
| Exception thoát ra | Copy-out thông thường không diễn ra |
| NOCOPY được áp dụng | Thay đổi đã ghi trực tiếp có thể còn trong actual sau exception |
| Hint bị bỏ qua | Hành vi theo cách truyền có sao chép |
| PL/SQL variable | Không được database ROLLBACK khôi phục |
| Aliasing | Cùng actual cho nhiều tham số ghi có thể tạo hành vi khó dự đoán |
| Hiệu năng | Chỉ thêm NOCOPY khi benchmark chứng minh lợi ích |
| Hợp đồng lỗi | Phải xác định all-or-nothing hay cho phép partial progress |

NOCOPY có thể giảm chi phí sao chép cho collection và record lớn, nhưng nó cũng làm thay đổi phạm vi mà caller có thể quan sát khi procedure phát sinh lỗi. Vì compiler có quyền bỏ qua hint, hãy viết code đúng trong cả hai trường hợp. Đặc biệt, tách rõ thay đổi biến PL/SQL khỏi transaction database, tránh aliasing, không nuốt exception và xác định rõ caller phải nhận trạng thái nào khi một phần xử lý đã hoàn thành.
