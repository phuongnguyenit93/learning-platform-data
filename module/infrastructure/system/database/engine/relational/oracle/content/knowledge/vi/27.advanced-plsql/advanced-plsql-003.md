# FORALL, INDICES OF và VALUES OF với collection thưa

Trong PL/SQL, khi cần thực hiện cùng một câu lệnh DML cho nhiều phần tử của collection, vòng lặp FOR thông thường có thể tạo nhiều lần chuyển đổi giữa PL/SQL engine và SQL engine. FORALL giải quyết bài toán này bằng bulk binding: PL/SQL gom các giá trị từ collection và gửi các lần thực thi DML theo lô.

Một thách thức xuất hiện khi collection không còn liên tục các chỉ số. Nested table có thể trở nên thưa sau DELETE; associative array có thể có key bất kỳ ngay từ đầu. Khi đó, FORALL với dải chỉ số cố định từ 1 đến COUNT có thể truy cập nhầm index không tồn tại. Oracle cung cấp hai cách chỉ định tập chỉ số thực sự cần chạy:

- **INDICES OF**: chạy theo các index đang tồn tại trong một collection.
- **VALUES OF**: chạy theo các giá trị index được lưu trong một collection khác, thường gọi là index collection hoặc pointer collection.

Bài học này giải thích FORALL, collection dense và sparse, cách chọn INDICES OF hoặc VALUES OF, giới hạn BETWEEN, xử lý lỗi bằng SAVE EXCEPTIONS, đọc SQL%BULK_EXCEPTIONS và SQL%BULK_ROWCOUNT, cùng một lab có thể chạy để quan sát kết quả.

Các ví dụ dùng Oracle Database 19c. Mục tiêu là hiểu cách ánh xạ chỉ số collection vào từng lần DML và giữ dữ liệu giữa các collection đồng bộ.

## 1. Vì sao cần FORALL?

Giả sử cần tăng số lượng tồn kho cho nhiều sản phẩm. Cách đơn giản là lặp từng phần tử rồi chạy UPDATE:

~~~sql
DECLARE
    TYPE t_id_list IS TABLE OF NUMBER;
    TYPE t_qty_list IS TABLE OF NUMBER;

    l_product_ids t_id_list := t_id_list(101, 102, 103);
    l_increments  t_qty_list := t_qty_list(5, 3, 8);
BEGIN
    FOR i IN 1 .. l_product_ids.COUNT LOOP
        UPDATE inventory
        SET quantity = quantity + l_increments(i)
        WHERE product_id = l_product_ids(i);
    END LOOP;
END;
/
~~~

Vòng lặp trên thực hiện nhiều lần gọi SQL từ PL/SQL. Với lượng dữ liệu lớn, chi phí chuyển đổi ngữ cảnh (context switch) có thể đáng kể.

FORALL cho phép bulk bind các giá trị collection vào một câu DML:

~~~sql
DECLARE
    TYPE t_id_list IS TABLE OF NUMBER;
    TYPE t_qty_list IS TABLE OF NUMBER;

    l_product_ids t_id_list := t_id_list(101, 102, 103);
    l_increments  t_qty_list := t_qty_list(5, 3, 8);
BEGIN
    FORALL i IN 1 .. l_product_ids.COUNT
        UPDATE inventory
        SET quantity = quantity + l_increments(i)
        WHERE product_id = l_product_ids(i);
END;
/
~~~

FORALL vẫn thực hiện nhiều lần DML logic, mỗi lần dùng một phần tử collection. Điểm khác biệt là Oracle xử lý các lần bind theo cơ chế bulk, giảm số lần chuyển đổi giữa PL/SQL và SQL engine.

### 1.1. FORALL không phải vòng lặp PL/SQL tổng quát

FORALL chỉ áp dụng cho một câu lệnh DML hoặc một câu lệnh dynamic SQL trong mỗi FORALL. Nó không phải thay thế cho FOR LOOP có nhiều câu lệnh PL/SQL, IF phức tạp hoặc lời gọi procedure tùy ý.

Không viết:

~~~sql
FORALL i IN 1 .. l_ids.COUNT
BEGIN
    validate_item(l_ids(i));
    UPDATE inventory SET quantity = quantity + 1
    WHERE product_id = l_ids(i);
END;
~~~

Hãy xác thực và chuẩn bị dữ liệu trước, sau đó dùng FORALL cho câu DML. Nếu từng phần tử cần logic nghiệp vụ khác nhau, vòng lặp thông thường có thể phù hợp hơn.

### 1.2. Cú pháp tổng quát

FORALL hỗ trợ ba cách xác định chỉ số:

~~~sql
FORALL index_name IN lower_bound .. upper_bound
    dml_statement;

FORALL index_name IN INDICES OF collection_name
    dml_statement;

FORALL index_name IN VALUES OF index_collection
    dml_statement;
~~~

INDICES OF và VALUES OF có thể thêm BETWEEN để giới hạn dải chỉ số được xét:

~~~sql
FORALL i IN INDICES OF l_values BETWEEN 2 AND 10
    UPDATE ...;

FORALL i IN VALUES OF l_indexes BETWEEN 1 AND 5
    UPDATE ...;
~~~

FORALL không tự COMMIT. DML vẫn thuộc transaction hiện tại của session; caller quyết định COMMIT hoặc ROLLBACK.

## 2. Collection dense và sparse

Collection dense có các phần tử liên tiếp trong dải index của nó. Collection sparse có ít nhất một index bị thiếu giữa các index đang tồn tại, hoặc có các index không bắt đầu từ 1.

### 2.1. Dense collection

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_values t_numbers := t_numbers(10, 20, 30, 40);
BEGIN
    DBMS_OUTPUT.PUT_LINE('COUNT=' || l_values.COUNT);
    DBMS_OUTPUT.PUT_LINE('FIRST=' || l_values.FIRST);
    DBMS_OUTPUT.PUT_LINE('LAST=' || l_values.LAST);
END;
/
~~~

Collection có bốn phần tử tại các index 1, 2, 3 và 4. COUNT bằng 4, FIRST bằng 1 và LAST bằng 4.

### 2.2. Tạo sparse nested table bằng DELETE

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_values t_numbers := t_numbers(10, 20, 30, 40, 50);
BEGIN
    l_values.DELETE(2);
    l_values.DELETE(4);

    DBMS_OUTPUT.PUT_LINE('COUNT=' || l_values.COUNT);
    DBMS_OUTPUT.PUT_LINE('FIRST=' || l_values.FIRST);
    DBMS_OUTPUT.PUT_LINE('LAST=' || l_values.LAST);
    DBMS_OUTPUT.PUT_LINE('EXISTS(2)=' || CASE
        WHEN l_values.EXISTS(2) THEN 'Y' ELSE 'N' END);
END;
/
~~~

Sau DELETE, các index còn tồn tại là 1, 3 và 5. COUNT bằng 3 nhưng LAST bằng 5. COUNT là số phần tử hiện có, không phải index lớn nhất.

### 2.3. Associative array cũng có thể thưa

Associative array không yêu cầu index liên tiếp:

~~~sql
DECLARE
    TYPE t_map IS TABLE OF VARCHAR2(30)
        INDEX BY PLS_INTEGER;
    l_values t_map;
BEGIN
    l_values(2) := 'Two';
    l_values(10) := 'Ten';
    l_values(50) := 'Fifty';

    DBMS_OUTPUT.PUT_LINE(l_values.COUNT);
    DBMS_OUTPUT.PUT_LINE(l_values.FIRST);
    DBMS_OUTPUT.PUT_LINE(l_values.LAST);
END;
/
~~~

Các index 2, 10 và 50 đều hợp lệ. Dải 1 .. COUNT sẽ là 1 .. 3, không trùng với các index thực tế.

### 2.4. Vì sao 1 .. COUNT có thể lỗi?

Giả sử nested table còn các index 1, 3 và 5. COUNT bằng 3, nên:

~~~sql
FORALL i IN 1 .. l_values.COUNT
    UPDATE target_table
    SET value = l_values(i)
    WHERE id = i;
~~~

FORALL sẽ tham chiếu l_values(1), l_values(2), l_values(3). Index 2 đã bị DELETE, nên thao tác có thể phát sinh lỗi collection subscript không tồn tại. Index 5 lại bị bỏ qua.

Tương tự, dùng FIRST .. LAST không giải quyết được khoảng trống ở giữa. Cần chọn đúng tập index tồn tại bằng INDICES OF hoặc danh sách index cụ thể bằng VALUES OF.

## 3. FORALL với dải chỉ số cố định

Cú pháp đơn giản:

~~~sql
FORALL i IN 1 .. l_ids.COUNT
    UPDATE inventory
    SET quantity = quantity + l_delta(i)
    WHERE product_id = l_ids(i);
~~~

Cách này phù hợp khi:

- Collection được khởi tạo dense.
- Index bắt đầu từ 1 và liên tục tới COUNT.
- Tất cả collection được tham chiếu trong DML có cùng tập index.

Nếu collection có index bắt đầu từ một số khác hoặc có lỗ, không nên dùng dải 1 .. COUNT. Cũng không nên dùng FIRST .. LAST nếu có index bị thiếu ở giữa.

### 3.1. Các collection phải đồng bộ index

Trong một câu DML, có thể tham chiếu nhiều collection:

~~~sql
FORALL i IN 1 .. l_ids.COUNT
    INSERT INTO order_lines (order_id, product_id, quantity)
    VALUES (l_order_ids(i), l_ids(i), l_quantities(i));
~~~

Các collection l_order_ids, l_ids và l_quantities phải có phần tử tại mọi index mà FORALL sử dụng. Nếu một collection bị thiếu index, tham chiếu đó có thể lỗi dù collection điều khiển dải chỉ số vẫn đầy đủ.

## 4. INDICES OF: chạy theo index đang tồn tại

INDICES OF yêu cầu Oracle lặp qua các index hiện có của một collection. Đây là lựa chọn tự nhiên khi dữ liệu đã nằm trong collection sparse và các collection khác được tham chiếu dùng cùng index.

### 4.1. Cú pháp

~~~sql
FORALL i IN INDICES OF l_ids
    UPDATE inventory
    SET quantity = quantity + l_delta(i)
    WHERE product_id = l_ids(i);
~~~

Oracle chỉ sử dụng các index đang tồn tại trong l_ids. Nếu l_ids có index 1, 3 và 5, các lần DML dùng i bằng 1, 3 và 5.

### 4.2. Ví dụ nested table sparse

~~~sql
DECLARE
    TYPE t_id_list IS TABLE OF NUMBER;
    TYPE t_delta_list IS TABLE OF NUMBER;

    l_ids   t_id_list := t_id_list(101, 102, 103, 104, 105);
    l_delta t_delta_list := t_delta_list(5, 10, 15, 20, 25);
BEGIN
    l_ids.DELETE(2);
    l_delta.DELETE(2);
    l_ids.DELETE(4);
    l_delta.DELETE(4);

    FORALL i IN INDICES OF l_ids
        UPDATE inventory
        SET quantity = quantity + l_delta(i)
        WHERE product_id = l_ids(i);
END;
/
~~~

Chỉ các index 1, 3 và 5 được xử lý. Cả l_ids và l_delta đều phải còn phần tử tại những index đó.

### 4.3. Collection điều khiển và collection được tham chiếu

Collection trong INDICES OF xác định index nào được lặp. Nó có thể là collection được tham chiếu trong câu DML hoặc một collection khác có cùng tập index. Ví dụ:

~~~sql
FORALL i IN INDICES OF l_active_flags
    UPDATE inventory
    SET quantity = quantity + l_delta(i)
    WHERE product_id = l_ids(i);
~~~

Ở đây l_active_flags quyết định index cần chạy. Vì DML truy cập l_delta(i) và l_ids(i), hai collection đó phải có index tương ứng cho mọi i mà l_active_flags cung cấp.

Không chỉ kiểm tra COUNT. Hãy kiểm tra EXISTS(i) hoặc xây dựng các collection song song bằng cùng một quy trình để giữ index đồng bộ.

### 4.4. INDICES OF với BETWEEN

BETWEEN giới hạn các giá trị index của collection điều khiển:

~~~sql
FORALL i IN INDICES OF l_ids BETWEEN 3 AND 8
    UPDATE inventory
    SET quantity = quantity + l_delta(i)
    WHERE product_id = l_ids(i);
~~~

Nếu l_ids có index 1, 3, 5, 9 thì chỉ index 3 và 5 được xét. Hai số 3 và 8 là cận của index, không phải số thứ tự phần tử và cũng không phải giá trị product_id.

BETWEEN hữu ích khi chia một collection thành các vùng xử lý, nhưng cận dưới/cận trên phải được hiểu theo index thực tế. Với associative array có key rời rạc, chỉ các key hiện có nằm trong khoảng mới được chọn.

### 4.5. Khi nào dùng INDICES OF?

- Collection dữ liệu đã sparse sau DELETE.
- Associative array dùng key PLS_INTEGER không liên tiếp.
- Muốn xử lý mọi phần tử đang tồn tại trong một collection.
- Có collection điều khiển chứa index hợp lệ của các collection dữ liệu song song.
- Muốn giới hạn một khoảng index bằng BETWEEN.

INDICES OF không sắp xếp dữ liệu theo giá trị nghiệp vụ. Nó chỉ chọn các index tồn tại; nếu thứ tự nghiệp vụ quan trọng, hãy thiết kế khóa/sort riêng.

## 5. VALUES OF: dùng collection chứa danh sách index

VALUES OF hữu ích khi muốn chọn một tập con hoặc một thứ tự xử lý cụ thể mà không xóa phần tử khỏi collection dữ liệu. Collection thứ hai lưu các index cần dùng; các giá trị trong collection này được dùng làm chỉ số để truy cập collection dữ liệu.

### 5.1. Cú pháp

~~~sql
FORALL i IN VALUES OF l_selected_indexes
    UPDATE inventory
    SET quantity = quantity + l_delta(i)
    WHERE product_id = l_ids(i);
~~~

l_selected_indexes là collection chứa các giá trị index. Ví dụ nếu nó chứa 5, 2 và 9 thì các lần DML dùng i bằng 5, 2 và 9. Các collection l_ids và l_delta phải có phần tử ở các index tương ứng.

### 5.2. Ví dụ dùng pointer collection

~~~sql
DECLARE
    TYPE t_id_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE t_delta_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE t_index_list IS TABLE OF PLS_INTEGER;

    l_ids       t_id_map;
    l_delta     t_delta_map;
    l_selected  t_index_list := t_index_list(5, 2);
BEGIN
    l_ids(2) := 102;
    l_delta(2) := 10;

    l_ids(5) := 105;
    l_delta(5) := 25;

    FORALL i IN VALUES OF l_selected
        UPDATE inventory
        SET quantity = quantity + l_delta(i)
        WHERE product_id = l_ids(i);
END;
/
~~~

Chỉ các index 5 và 2 được xử lý, theo danh sách trong l_selected. Những phần tử khác trong l_ids và l_delta không bị tác động.

### 5.3. VALUES OF với BETWEEN

~~~sql
FORALL i IN VALUES OF l_selected BETWEEN 2 AND 4
    UPDATE inventory
    SET quantity = quantity + l_delta(i)
    WHERE product_id = l_ids(i);
~~~

Với VALUES OF, BETWEEN giới hạn index của chính collection điều khiển l_selected, không lọc theo giá trị index được lưu bên trong. Ví dụ l_selected có các phần tử ở index 1, 2, 3, 4; BETWEEN 2 AND 4 chọn các phần tử l_selected(2), l_selected(3), l_selected(4), rồi dùng giá trị bên trong từng phần tử làm index i của l_ids/l_delta.

Phân biệt hai tầng index:

1. Index của pointer collection, ví dụ l_selected(2).
2. Giá trị nằm trong pointer collection, ví dụ l_selected(2) = 5; giá trị 5 trở thành i trong DML.

Đây là điểm dễ nhầm nhất khi kết hợp VALUES OF và BETWEEN.

### 5.4. VALUES OF có thể biểu diễn tập con

Giả sử l_ids và l_delta có 100 phần tử, nhưng chỉ 3 phần tử cần cập nhật. Có thể tạo pointer collection chỉ chứa ba index đó. Không cần DELETE các phần tử còn lại khỏi collection dữ liệu.

~~~sql
TYPE t_index_list IS TABLE OF PLS_INTEGER;
l_selected t_index_list := t_index_list(7, 22, 81);

FORALL i IN VALUES OF l_selected
    UPDATE inventory
    SET quantity = quantity + l_delta(i)
    WHERE product_id = l_ids(i);
~~~

Cách này tách dữ liệu nguồn khỏi chính sách chọn phần tử. Có thể xây dựng l_selected từ kết quả validation hoặc phân loại nghiệp vụ trước khi chạy DML.

### 5.5. Giá trị lặp trong pointer collection

Nếu pointer collection chứa cùng một index nhiều lần, FORALL có thể thực hiện DML nhiều lần cho index đó:

~~~sql
TYPE t_index_list IS TABLE OF PLS_INTEGER;
l_selected t_index_list := t_index_list(5, 2, 5);
~~~

Index 5 xuất hiện hai lần. Nếu DML cộng thêm số lượng, phần tử đó có thể được cập nhật hai lần. Chỉ giữ giá trị lặp khi đó là yêu cầu nghiệp vụ; nếu không, loại bỏ duplicate trước khi FORALL.

### 5.6. Điều kiện với pointer collection

- Pointer collection phải là collection index bằng số nguyên phù hợp cho FORALL.
- Mỗi giá trị index được lưu phải tồn tại trong mọi collection mà DML truy cập tại index đó.
- Không nhầm index của pointer collection với giá trị pointer.
- Nếu pointer collection có phần tử bị DELETE, chỉ các phần tử còn tồn tại mới được dùng; hãy thiết kế và kiểm tra rõ tập chỉ số.
- Với dữ liệu cần thứ tự, hãy tạo pointer list theo thứ tự mong muốn và kiểm tra kết quả theo khóa nghiệp vụ.

## 6. So sánh dải chỉ số, INDICES OF và VALUES OF

| Cách viết | Tập index được xử lý | Phù hợp khi |
| --- | --- | --- |
| 1 .. COUNT | Các số từ 1 đến COUNT | Collection dense, bắt đầu từ 1 |
| FIRST .. LAST | Mọi số trong dải FIRST đến LAST | Chỉ khi collection dense trong dải đó |
| INDICES OF data | Các index hiện có trong collection data | Xử lý collection sparse |
| INDICES OF control BETWEEN a AND b | Index hiện có của collection control nằm trong khoảng a..b | Chia vùng xử lý theo index |
| VALUES OF pointers | Các giá trị index nằm trong pointer collection | Chọn tập con hoặc thứ tự index tùy ý |
| VALUES OF pointers BETWEEN a AND b | Giá trị pointer tại các index của pointer collection trong khoảng a..b | Chọn một phần danh sách pointer |

Quy tắc chọn:

- Dùng dải cố định khi chắc chắn collection dense.
- Dùng INDICES OF khi muốn xử lý tất cả index tồn tại của collection sparse.
- Dùng VALUES OF khi muốn một danh sách index riêng, có thể chọn tập con hoặc lặp lại index có chủ đích.

## 7. FORALL với nhiều collection và dữ liệu song song

Một câu DML thường dùng nhiều collection, ví dụ product ID, quantity và warehouse ID. Các collection phải ánh xạ đúng cùng một phần tử logic.

~~~sql
DECLARE
    TYPE t_number_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;

    l_product_ids t_number_map;
    l_quantities  t_number_map;
    l_warehouses  t_number_map;
BEGIN
    l_product_ids(2) := 101;
    l_quantities(2) := 5;
    l_warehouses(2) := 1;

    l_product_ids(7) := 102;
    l_quantities(7) := 3;
    l_warehouses(7) := 2;

    FORALL i IN INDICES OF l_product_ids
        INSERT INTO inventory_movements (
            product_id,
            quantity,
            warehouse_id
        )
        VALUES (
            l_product_ids(i),
            l_quantities(i),
            l_warehouses(i)
        );
END;
/
~~~

Collection l_product_ids điều khiển tập index. Hai collection còn lại phải có đủ index 2 và 7. Nếu l_quantities thiếu index 7, DML tương ứng có thể lỗi dù l_product_ids vẫn hợp lệ.

### 7.1. Kiểm tra đồng bộ trước khi DML

Có thể kiểm tra các collection song song trước khi gọi FORALL:

~~~sql
DECLARE
    i PLS_INTEGER;
BEGIN
    i := l_product_ids.FIRST;
    WHILE i IS NOT NULL LOOP
        IF NOT l_quantities.EXISTS(i)
           OR NOT l_warehouses.EXISTS(i)
        THEN
            RAISE_APPLICATION_ERROR(
                -20001,
                'Missing data for collection index ' || i
            );
        END IF;

        i := l_product_ids.NEXT(i);
    END LOOP;
END;
~~~

Đoạn kiểm tra này minh họa nguyên tắc; đặt nó trong cùng block với các collection đã khai báo. Kiểm tra sớm giúp lỗi dữ liệu dễ hiểu hơn so với để FORALL thất bại ở một phần tử khó truy vết.

### 7.2. Chọn collection điều khiển

Collection điều khiển nên có ý nghĩa rõ ràng:

- INDICES OF l_product_ids nếu ID là collection chuẩn và các collection khác song song.
- INDICES OF l_valid_rows nếu đã tạo một collection đánh dấu những hàng được duyệt.
- VALUES OF l_selected_indexes nếu cần danh sách lựa chọn riêng.

Đừng chọn một collection điều khiển chỉ vì nó có COUNT giống các collection khác. Hai collection có cùng COUNT nhưng index khác nhau vẫn không tương thích.

## 8. SAVE EXCEPTIONS và xử lý lỗi từng phần tử

Mặc định, nếu một lần thực thi DML trong FORALL lỗi, Oracle dừng xử lý và phát sinh exception. Các lần DML đã thành công trước đó vẫn thuộc transaction hiện tại và có thể được commit hoặc rollback theo quyết định của caller.

Nếu muốn Oracle tiếp tục các lần DML còn lại và báo lỗi sau khi hoàn tất, dùng SAVE EXCEPTIONS.

### 8.1. Cú pháp

~~~sql
FORALL i IN INDICES OF l_ids SAVE EXCEPTIONS
    UPDATE inventory
    SET quantity = quantity + l_delta(i)
    WHERE product_id = l_ids(i);
~~~

Khi có lỗi ở một hoặc nhiều lần DML, Oracle tiếp tục xử lý các lần còn lại rồi phát sinh ORA-24381. Các lỗi chi tiết nằm trong SQL%BULK_EXCEPTIONS.

### 8.2. Khai báo exception cho ORA-24381

~~~sql
DECLARE
    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    NULL;
EXCEPTION
    WHEN e_bulk_errors THEN
        DBMS_OUTPUT.PUT_LINE('One or more FORALL iterations failed');
END;
/
~~~

### 8.3. Đọc SQL%BULK_EXCEPTIONS

Mỗi phần tử trong SQL%BULK_EXCEPTIONS chứa:

- ERROR_INDEX: chỉ số/iteration được Oracle báo là gây lỗi trong FORALL.
- ERROR_CODE: mã lỗi Oracle của lần DML thất bại, không bao gồm dấu âm.

Ví dụ:

~~~sql
EXCEPTION
    WHEN e_bulk_errors THEN
        FOR j IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Error index=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_INDEX ||
                ', code=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_CODE ||
                ', message=' ||
                SQLERRM(-SQL%BULK_EXCEPTIONS(j).ERROR_CODE)
            );
        END LOOP;
~~~

SQL%BULK_EXCEPTIONS là pseudo-collection do Oracle cung cấp trong exception handler. Dùng chỉ số j để duyệt danh sách lỗi; không nhầm j với index của collection dữ liệu.

Khi dùng INDICES OF hoặc VALUES OF, hãy giữ ánh xạ rõ từ iteration/error index tới business key của phần tử. Không giả định ERROR_INDEX luôn là product ID hoặc luôn là vị trí tuần tự trong một collection khác. Kiểm tra cách ánh xạ theo dạng FORALL cụ thể và phiên bản Oracle; trong hệ thống quan trọng, có thể lưu bảng ánh xạ iteration/index/key trước khi chạy.

### 8.4. SQL%BULK_ROWCOUNT

SQL%BULK_ROWCOUNT cung cấp số hàng bị tác động bởi từng lần thực thi DML trong FORALL. SQL%ROWCOUNT là tổng số hàng bị tác động bởi câu FORALL.

Ví dụ:

~~~sql
FORALL i IN INDICES OF l_ids
    UPDATE inventory
    SET quantity = quantity + l_delta(i)
    WHERE product_id = l_ids(i);

DBMS_OUTPUT.PUT_LINE('Total affected rows=' || SQL%ROWCOUNT);
~~~

Nếu cần biết từng ID có tìm thấy hàng hay không, hãy dùng SQL%BULK_ROWCOUNT theo index/iteration tương ứng của FORALL và đối chiếu tài liệu Oracle cho dạng bounds đang dùng. Một lần DML có thể thành công nhưng tác động 0 hàng; đó không phải bulk exception.

## 9. Lab: cập nhật collection thưa bằng INDICES OF và VALUES OF

Lab dưới đây tạo bảng tồn kho nhỏ để quan sát các index được chọn. Chạy trong schema thực hành riêng.

### 9.1. Tạo bảng

~~~sql
CREATE TABLE lab_inventory (
    product_id NUMBER PRIMARY KEY,
    quantity   NUMBER NOT NULL,
    CONSTRAINT lab_inventory_qty_ck CHECK (quantity >= 0)
);

INSERT INTO lab_inventory VALUES (101, 100);
INSERT INTO lab_inventory VALUES (102, 100);
INSERT INTO lab_inventory VALUES (103, 100);
INSERT INTO lab_inventory VALUES (104, 100);
INSERT INTO lab_inventory VALUES (105, 100);
COMMIT;
~~~

### 9.2. Tạo collection thưa và chạy INDICES OF

~~~sql
DECLARE
    TYPE t_number_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    l_ids   t_number_map;
    l_delta t_number_map;
BEGIN
    l_ids(1) := 101;
    l_delta(1) := 5;

    l_ids(3) := 103;
    l_delta(3) := 15;

    l_ids(5) := 105;
    l_delta(5) := 25;

    FORALL i IN INDICES OF l_ids
        UPDATE lab_inventory
        SET quantity = quantity + l_delta(i)
        WHERE product_id = l_ids(i);

    DBMS_OUTPUT.PUT_LINE('Rows updated=' || SQL%ROWCOUNT);
END;
/

SELECT product_id, quantity
FROM lab_inventory
ORDER BY product_id;
~~~

Kết quả dự kiến: sản phẩm 101 có 105, 103 có 115, 105 có 125; 102 và 104 giữ 100. Các index 1, 3, 5 được xử lý dù COUNT chỉ bằng 3.

### 9.3. Dùng BETWEEN với INDICES OF

~~~sql
DECLARE
    TYPE t_number_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    l_ids   t_number_map;
    l_delta t_number_map;
BEGIN
    l_ids(1) := 101; l_delta(1) := 1;
    l_ids(3) := 103; l_delta(3) := 3;
    l_ids(5) := 105; l_delta(5) := 5;
    l_ids(9) := 104; l_delta(9) := 9;

    FORALL i IN INDICES OF l_ids BETWEEN 3 AND 8
        UPDATE lab_inventory
        SET quantity = quantity + l_delta(i)
        WHERE product_id = l_ids(i);
END;
/
~~~

Chỉ index 3 và 5 nằm trong khoảng 3..8, nên chỉ sản phẩm 103 và 105 được cập nhật. Index 1 và 9 không chạy.

### 9.4. Dùng VALUES OF để chọn một tập con

~~~sql
DECLARE
    TYPE t_number_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE t_index_list IS TABLE OF PLS_INTEGER;

    l_ids      t_number_map;
    l_delta    t_number_map;
    l_selected t_index_list := t_index_list(9, 2);
BEGIN
    l_ids(2) := 102; l_delta(2) := 20;
    l_ids(5) := 105; l_delta(5) := 50;
    l_ids(9) := 104; l_delta(9) := 90;

    FORALL i IN VALUES OF l_selected
        UPDATE lab_inventory
        SET quantity = quantity + l_delta(i)
        WHERE product_id = l_ids(i);
END;
/
~~~

Pointer collection chứa các giá trị 9 và 2, nên DML dùng l_ids(9)/l_delta(9), rồi l_ids(2)/l_delta(2). Index 5 không được chọn.

### 9.5. Dùng VALUES OF với BETWEEN

~~~sql
DECLARE
    TYPE t_number_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE t_index_list IS TABLE OF PLS_INTEGER;

    l_ids      t_number_map;
    l_delta    t_number_map;
    l_selected t_index_list := t_index_list(9, 2, 5, 1);
BEGIN
    l_ids(1) := 101; l_delta(1) := 1;
    l_ids(2) := 102; l_delta(2) := 2;
    l_ids(5) := 105; l_delta(5) := 5;
    l_ids(9) := 104; l_delta(9) := 9;

    FORALL i IN VALUES OF l_selected BETWEEN 2 AND 3
        UPDATE lab_inventory
        SET quantity = quantity + l_delta(i)
        WHERE product_id = l_ids(i);
END;
/
~~~

BETWEEN 2 AND 3 chọn l_selected(2) và l_selected(3), tức pointer values 2 và 5. DML tác động sản phẩm 102 và 105. Nó không chọn pointer values 9 và 2 theo cách so sánh giá trị pointer với 2..3.

## 10. Lab: SAVE EXCEPTIONS và xử lý lỗi

Dùng CHECK constraint của LAB_INVENTORY để tạo một lần cập nhật thất bại có kiểm soát. Sản phẩm 102 có quantity 100; delta âm quá lớn làm giá trị mới âm và vi phạm constraint.

~~~sql
DECLARE
    TYPE t_number_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;

    l_ids   t_number_map;
    l_delta t_number_map;

    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    l_ids(2) := 101;
    l_delta(2) := 10;

    l_ids(5) := 102;
    l_delta(5) := -1000;

    l_ids(9) := 103;
    l_delta(9) := 20;

    FORALL i IN INDICES OF l_ids SAVE EXCEPTIONS
        UPDATE lab_inventory
        SET quantity = quantity + l_delta(i)
        WHERE product_id = l_ids(i);

    DBMS_OUTPUT.PUT_LINE('All iterations succeeded');
EXCEPTION
    WHEN e_bulk_errors THEN
        DBMS_OUTPUT.PUT_LINE(
            'Bulk errors=' || SQL%BULK_EXCEPTIONS.COUNT
        );

        FOR j IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Error index=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_INDEX ||
                ', error code=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_CODE ||
                ', message=' ||
                SQLERRM(-SQL%BULK_EXCEPTIONS(j).ERROR_CODE)
            );
        END LOOP;
END;
/
~~~

Oracle tiếp tục các lần DML sau lỗi nhờ SAVE EXCEPTIONS. Trong ví dụ, các cập nhật cho 101 và 103 có thể thành công; cập nhật cho 102 thất bại vì CHECK constraint. DML thành công vẫn thuộc transaction hiện tại. Hãy kiểm tra dữ liệu rồi chủ động COMMIT hoặc ROLLBACK theo yêu cầu bài lab.

~~~sql
SELECT product_id, quantity
FROM lab_inventory
ORDER BY product_id;
~~~

Không tự động COMMIT chỉ vì FORALL đã tiếp tục qua các lỗi. SAVE EXCEPTIONS là cơ chế thu thập lỗi, không phải chính sách transaction.

## 11. Kết hợp RETURNING BULK COLLECT INTO

Một câu DML trong FORALL có thể dùng RETURNING BULK COLLECT INTO để gom các giá trị được trả về từ những hàng bị tác động.

Ví dụ:

~~~sql
DECLARE
    TYPE t_id_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE t_id_list IS TABLE OF NUMBER;

    l_ids t_id_map;
    l_deleted_ids t_id_list;
BEGIN
    l_ids(2) := 101;
    l_ids(5) := 103;

    FORALL i IN INDICES OF l_ids
        DELETE FROM lab_inventory
        WHERE product_id = l_ids(i)
        RETURNING product_id BULK COLLECT INTO l_deleted_ids;

    FOR j IN 1 .. l_deleted_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE('Deleted product=' || l_deleted_ids(j));
    END LOOP;
END;
/
~~~

Collection nhận kết quả RETURNING được gom theo các hàng thực sự bị tác động. Số phần tử trả về không nhất thiết bằng số iteration FORALL nếu một iteration tác động 0 hàng hoặc nhiều hàng. Hãy dùng chính collection trả về để duyệt kết quả, không suy luận vị trí của nó từ index đầu vào.

## 12. FORALL và transaction

FORALL tối ưu cách gửi DML, không tạo transaction độc lập cho từng phần tử.

- Không có COMMIT tự động sau mỗi iteration.
- Nếu không dùng SAVE EXCEPTIONS, lỗi DML có thể làm FORALL dừng; các DML thành công trước đó vẫn là thay đổi chưa commit của transaction hiện tại.
- Nếu dùng SAVE EXCEPTIONS, Oracle tiếp tục các iteration còn lại và báo ORA-24381 sau đó; các DML thành công vẫn chưa commit.
- Caller có thể COMMIT các phần tử thành công hoặc ROLLBACK toàn bộ transaction.
- Không gọi COMMIT bên trong một vòng lặp xử lý batch chỉ để tránh lỗi collection; điều đó thay đổi atomicity của nghiệp vụ.

Nếu mỗi batch cần là một transaction riêng, hãy chia batch rõ ràng ở tầng điều phối và định nghĩa chính sách retry/idempotency. Đừng nhầm batch binding với transaction batching.

## 13. Hiệu năng và giới hạn thực tế

FORALL giảm context switch nhưng không đảm bảo mọi workload nhanh hơn trong mọi trường hợp. Hiệu năng còn phụ thuộc số hàng, kích thước dữ liệu, index, constraint, trigger, redo/undo và kế hoạch thực thi.

### 13.1. Chuẩn bị dữ liệu trước

Hãy:

- Validate dữ liệu đầu vào trước FORALL.
- Chuẩn hóa collection và index.
- Dùng bind collection thay vì nối giá trị vào dynamic SQL.
- Chọn đúng tập index cần chạy.
- Chỉ lấy các cột cần thiết.

### 13.2. Giữ collection đồng bộ

Nếu một DML dùng l_ids(i), l_qty(i) và l_wh_id(i), mọi collection phải có phần tử tại mỗi index i được chọn. Nếu collection có thể bị DELETE độc lập, cần kiểm tra EXISTS trước khi chạy.

### 13.3. Kích thước batch

Khi nạp dữ liệu từ query, BULK COLLECT ... LIMIT giúp giới hạn bộ nhớ:

~~~sql
FETCH c_source BULK COLLECT INTO l_rows LIMIT 500;
~~~

Sau đó có thể dùng FORALL trên từng batch. Chọn LIMIT dựa trên kích thước record, PGA và hiệu năng đo thực tế.

### 13.4. Không dùng FORALL để che thiết kế DML kém

Nếu có thể thực hiện một UPDATE set-based duy nhất thay cho hàng nghìn lần UPDATE theo collection, câu SQL set-based thường đơn giản và hiệu quả hơn. FORALL phù hợp khi cần áp dụng DML theo từng phần tử đầu vào mà không thể diễn đạt gọn thành một câu SQL set-based.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| FORALL 1..COUNT truy cập index không tồn tại | Collection sparse, COUNT không phải index lớn nhất | Dùng INDICES OF hoặc VALUES OF |
| FORALL FIRST..LAST vẫn lỗi | Có lỗ giữa FIRST và LAST | Dùng INDICES OF |
| DML lỗi dù collection điều khiển hợp lệ | Collection khác trong DML thiếu cùng index | Đồng bộ index hoặc kiểm tra EXISTS |
| VALUES OF truy cập sai phần tử | Nhầm index của pointer collection với giá trị pointer | Theo dõi hai tầng index |
| BETWEEN chọn sai phần tử | Hiểu BETWEEN là lọc giá trị pointer | BETWEEN lọc index của collection điều khiển |
| Một hàng bị cập nhật nhiều lần | Pointer collection có index lặp | Loại duplicate hoặc xác nhận lặp là chủ ý |
| ORA-24381 | Một hoặc nhiều iteration lỗi với SAVE EXCEPTIONS | Đọc SQL%BULK_EXCEPTIONS |
| Bỏ sót lỗi vì chỉ kiểm tra SQL%ROWCOUNT | Tổng row count không liệt kê từng lỗi | Duyệt SQL%BULK_EXCEPTIONS và SQL%BULK_ROWCOUNT |
| Nhầm ERROR_INDEX với business key | ERROR_INDEX là locator của lần FORALL lỗi | Duy trì mapping tới khóa nghiệp vụ |
| Dữ liệu thành công vẫn còn sau lỗi | SAVE EXCEPTIONS không tự rollback các iteration thành công | Chọn COMMIT/ROLLBACK theo chính sách |
| FORALL chậm hơn mong đợi | Có thể DML set-based phù hợp hơn hoặc trigger/index chi phí lớn | Đo và so sánh execution path |

## 15. Quy trình chọn cách lặp

Trước khi viết FORALL, hãy xác định:

1. Collection dữ liệu có dense không?
2. Nếu sparse, index thực sự tồn tại là gì?
3. Các collection được tham chiếu trong DML có cùng tập index không?
4. Muốn xử lý mọi phần tử hay chỉ một tập con?
5. Có cần thứ tự hoặc lặp index có chủ đích không?
6. Cần dừng ngay ở lỗi đầu tiên hay tiếp tục với SAVE EXCEPTIONS?
7. Sau lỗi, commit phần thành công hay rollback toàn bộ?

Lựa chọn:

- Dense 1..COUNT: dùng dải cố định.
- Sparse và muốn tất cả phần tử còn tồn tại: dùng INDICES OF.
- Sparse nhưng chỉ chọn một số index hoặc muốn thứ tự riêng: dùng VALUES OF.
- Cần giới hạn theo index của collection điều khiển: dùng BETWEEN.
- Cần thu thập lỗi từng iteration: thêm SAVE EXCEPTIONS và đọc SQL%BULK_EXCEPTIONS.

## 16. Bài tập thực hành

Sử dụng LAB_INVENTORY trong mục 9.

### Bài 1 — Dense và sparse

Tạo nested table có 6 phần tử, DELETE index 2 và 5. In COUNT, FIRST, LAST, EXISTS cho từng index. Giải thích vì sao COUNT không thể dùng thay index lớn nhất.

### Bài 2 — Lỗi của 1..COUNT

Thử FORALL i IN 1..COUNT trên collection đã tạo ở bài 1. Quan sát lỗi index. Sửa bằng INDICES OF.

### Bài 3 — INDICES OF

Tạo hai associative array l_ids và l_delta có cùng index 2, 7 và 20. Dùng INDICES OF l_ids để cập nhật tồn kho. Sau đó xóa index 7 khỏi một collection và quan sát lỗi do hai collection không đồng bộ.

### Bài 4 — BETWEEN

Tạo collection có index 1, 3, 5, 9 và 12. Dùng INDICES OF ... BETWEEN 3 AND 9. Ghi lại những index được chạy.

### Bài 5 — VALUES OF

Tạo pointer collection chứa các giá trị 12, 3 và 9. Dùng VALUES OF để chọn đúng ba phần tử trong collection dữ liệu. Thêm một giá trị pointer không tồn tại và quan sát lỗi.

### Bài 6 — VALUES OF và BETWEEN

Tạo pointer collection có index 1..5 và value lần lượt 12, 3, 9, 1, 5. Dùng VALUES OF ... BETWEEN 2 AND 4. Ghi lại index của pointer collection được xét và giá trị pointer được dùng trong DML.

### Bài 7 — SAVE EXCEPTIONS

Dùng CHECK constraint quantity >= 0. Tạo một batch có cả delta hợp lệ và delta làm quantity âm. Dùng SAVE EXCEPTIONS, in ERROR_INDEX, ERROR_CODE và SQLERRM. Xác định business key tương ứng.

### Bài 8 — DML set-based hay FORALL

Viết cùng một yêu cầu cập nhật theo hai cách: một câu UPDATE set-based và FORALL với collection. Đo thời gian trên bộ dữ liệu lab lớn hơn, so sánh độ phức tạp và kết quả.

## 17. Dọn dữ liệu lab

Chỉ chạy trong schema lab do bạn tạo, sau khi hoàn thành bài tập:

~~~sql
DROP TABLE lab_inventory PURGE;
~~~

Nếu tạo thêm bảng hoặc object phục vụ bài tập, chỉ xóa đúng object lab của mình. Không chạy lệnh dọn dẹp trên dữ liệu nghiệp vụ.

## Tổng kết

FORALL dùng bulk binding để thực hiện một câu DML cho nhiều phần tử collection, giảm số lần chuyển đổi giữa PL/SQL và SQL engine. Dải 1..COUNT chỉ an toàn khi collection dense và index đúng là 1 tới COUNT. Với collection sparse, INDICES OF chọn các index đang tồn tại; VALUES OF dùng giá trị trong một pointer collection làm index truy cập collection dữ liệu. BETWEEN giới hạn index của collection điều khiển, không lọc trực tiếp giá trị pointer.

Khi một DML tham chiếu nhiều collection, mọi collection phải có phần tử tại từng index được chọn. SAVE EXCEPTIONS cho phép tiếp tục qua các lỗi và báo ORA-24381; SQL%BULK_EXCEPTIONS cung cấp vị trí và mã lỗi, còn SQL%BULK_ROWCOUNT giúp xem số hàng bị tác động theo iteration. FORALL không tự commit: sau khi xử lý lỗi, caller vẫn phải quyết định commit phần thành công hay rollback transaction. Hãy giữ mapping từ index tới business key, kiểm tra collection song song và chỉ dùng VALUES OF với duplicate khi việc thực thi lặp là có chủ ý.

## Tài liệu Oracle tham khảo

- [Oracle Database PL/SQL Language Reference — FORALL Statement (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/FORALL-statement.html) — cú pháp bounds, INDICES OF, VALUES OF và SAVE EXCEPTIONS.
- [Oracle Database PL/SQL Language Reference — Handling FORALL Exceptions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/bulk-sql-and-bulk-binding.html) — bulk exception và xử lý lỗi.
- [Oracle Database PL/SQL Language Reference — Collection Methods (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/collection-methods.html) — COUNT, FIRST, LAST, NEXT, EXISTS và DELETE.
- [Oracle Database PL/SQL Language Reference — Bulk SQL and Bulk Binding (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/bulk-sql-and-bulk-binding.html) — BULK COLLECT, FORALL và bulk binding.
- [Oracle Database PL/SQL Language Reference — Implicit Cursor Attribute (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/implicit-cursor-attribute.html) — SQL%ROWCOUNT và SQL%BULK_ROWCOUNT.

Khi triển khai trên Oracle release khác 19c, hãy đối chiếu PL/SQL Language Reference đúng phiên bản, đặc biệt cú pháp VALUES OF/BETWEEN, cách diễn giải ERROR_INDEX, giới hạn collection và hành vi SAVE EXCEPTIONS.
