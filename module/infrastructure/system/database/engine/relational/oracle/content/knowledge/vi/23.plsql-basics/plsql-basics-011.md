# Collection method, chỉ số thưa và phần tử chưa khởi tạo trong PL/SQL

PL/SQL collection là cấu trúc dữ liệu dùng để lưu nhiều phần tử cùng kiểu trong một biến. Collection xuất hiện trong xử lý batch, BULK COLLECT, FORALL, trao đổi dữ liệu giữa các procedure và các thuật toán chạy trong database. Khi thao tác với collection, chỉ số phần tử không phải lúc nào cũng liên tục từ 1 đến COUNT.

Một collection có thể có các phần tử đã bị DELETE, các chỉ số bị khuyết, hoặc phần tử đã được tạo nhưng giá trị vẫn là NULL. Ngoài ra, với nested table và varray, biến collection có thể còn ở trạng thái **atomically null** (chưa được khởi tạo). Những trạng thái này khác nhau và dẫn đến hành vi khác nhau khi đọc hoặc gọi collection method.

Bài học này trình bày:

- Ba kiểu collection: associative array, nested table và varray.
- Các method COUNT, FIRST, LAST, PRIOR, NEXT, EXISTS và LIMIT.
- Các method DELETE, EXTEND và TRIM.
- Khác biệt giữa collection null, collection rỗng, phần tử NULL và chỉ số không tồn tại.
- Cách duyệt collection thưa an toàn.
- Các exception thường gặp khi truy cập phần tử.
- Ứng dụng trong BULK COLLECT, FORALL và xử lý dữ liệu theo lô.

## 1. Collection trong PL/SQL

Collection là một nhóm phần tử cùng kiểu. Mỗi phần tử được truy cập bằng một subscript (chỉ số hoặc key). Oracle PL/SQL có ba kiểu collection chính:

| Kiểu | Khai báo | Đặc điểm |
|---|---|---|
| Associative array | TABLE OF ... INDEX BY | Mảng tra cứu theo key; có thể dùng chỉ số số nguyên hoặc chuỗi; không cần constructor |
| Nested table | TABLE OF ... | Collection có thể thay đổi kích thước; có thể trở nên thưa sau DELETE |
| VARRAY | VARRAY(n) OF ... | Có giới hạn tối đa n phần tử; các phần tử luôn liên tục từ 1 đến COUNT |

Mỗi kiểu có tập method hỗ trợ khác nhau. Không thể gọi EXTEND trên associative array, cũng không thể dùng DELETE để xóa riêng một phần tử của varray.

## 2. Khai báo ba kiểu collection

### 2.1 Associative array

Associative array (còn gọi là index-by table) dùng key để tìm phần tử. Ví dụ key là PLS_INTEGER:

~~~sql
DECLARE
    TYPE t_score_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    l_scores t_score_map;
BEGIN
    l_scores(10) := 85;
    l_scores(20) := 92;
    l_scores(100) := 77;

    DBMS_OUTPUT.PUT_LINE(l_scores(20));
END;
/
~~~

Associative array bắt đầu ở trạng thái rỗng khi khai báo. Không cần gọi constructor để khởi tạo và không có constructor collection như nested table hoặc varray. Các key có thể rời rạc ngay từ đầu: 10, 20 và 100 không cần liên tiếp.

Associative array cũng có thể dùng key chuỗi:

~~~sql
DECLARE
    TYPE t_price_map IS TABLE OF NUMBER INDEX BY VARCHAR2(30);
    l_prices t_price_map;
BEGIN
    l_prices('BOOK') := 120000;
    l_prices('PEN')  := 5000;

    DBMS_OUTPUT.PUT_LINE(l_prices('BOOK'));
END;
/
~~~

Với key chuỗi, thứ tự FIRST, LAST, PRIOR và NEXT phụ thuộc quy tắc sắp xếp chuỗi của môi trường session (NLS_SORT/NLS_COMP). Associative array không phải cấu trúc giữ thứ tự chèn; nếu nghiệp vụ cần thứ tự riêng, hãy lưu thêm cột thứ tự hoặc dùng một collection khác.

### 2.2 Nested table

Nested table được khai báo bằng TABLE OF:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20, 30);
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_numbers(1));
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT);
END;
/
~~~

Constructor t_numbers(10, 20, 30) tạo ba phần tử với chỉ số 1, 2, 3. Nested table có thể được mở rộng và có thể trở nên thưa nếu một hoặc nhiều phần tử bị DELETE.

Một nested table chưa khởi tạo:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers;
BEGIN
    -- l_numbers đang atomically null.
    l_numbers := t_numbers();
    -- Bây giờ collection đã khởi tạo và rỗng.
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT);
END;
/
~~~

Constructor rỗng t_numbers() tạo một collection đã khởi tạo nhưng chưa có phần tử.

### 2.3 VARRAY

VARRAY khai báo giới hạn số phần tử tối đa:

~~~sql
DECLARE
    TYPE t_tags IS VARRAY(5) OF VARCHAR2(30);
    l_tags t_tags := t_tags('NEW', 'PAID');
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_tags.COUNT);
    DBMS_OUTPUT.PUT_LINE(l_tags.LIMIT);
END;
/
~~~

VARRAY ở ví dụ này có tối đa 5 phần tử và hiện có 2 phần tử. VARRAY luôn dense (liên tục): nếu COUNT = 2 thì các chỉ số hiện có là 1 và 2. Không thể DELETE riêng phần tử ở giữa để tạo lỗ.

### 2.4 Khởi tạo và trạng thái rỗng

| Trạng thái | Nested table / VARRAY | Associative array |
|---|---|---|
| Vừa khai báo biến | Atomically null | Rỗng, có thể dùng ngay |
| Gọi constructor rỗng | Được: type_name() | Không có constructor |
| COUNT khi đã khởi tạo nhưng rỗng | 0 | 0 |
| FIRST và LAST khi rỗng | NULL | NULL |
| Có thể dùng EXISTS để kiểm tra | Có | Có |

Với nested table và varray, khai báo biến mà không gán constructor hoặc giá trị khác sẽ để collection ở trạng thái atomically null. Các method như COUNT, FIRST, LAST, LIMIT, PRIOR, NEXT, DELETE, EXTEND và TRIM trên collection null sẽ phát sinh COLLECTION_IS_NULL. EXISTS là ngoại lệ: có thể gọi trên collection atomically null và trả FALSE.

## 3. Phân biệt bốn trạng thái của collection và phần tử

Đây là phần quan trọng nhất để tránh lỗi runtime.

### 3.1 Collection atomically null

Biến collection chưa được khởi tạo:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers;
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT);
END;
/
~~~

Đoạn trên phát sinh COLLECTION_IS_NULL vì COUNT được gọi trên collection atomically null.

Có thể kiểm tra EXISTS:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers;
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        CASE WHEN l_numbers.EXISTS(1) THEN 'YES' ELSE 'NO' END
    );
END;
/
~~~

EXISTS(1) trả FALSE; method này không làm collection được khởi tạo.

### 3.2 Collection đã khởi tạo nhưng rỗng

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers();
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT); -- 0
    DBMS_OUTPUT.PUT_LINE(l_numbers.FIRST); -- NULL
    DBMS_OUTPUT.PUT_LINE(l_numbers.LAST);  -- NULL
END;
/
~~~

Collection đã tồn tại nhưng chưa có phần tử. COUNT hợp lệ và bằng 0.

### 3.3 Phần tử tồn tại nhưng giá trị là NULL

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, NULL, 30);
BEGIN
    IF l_numbers.EXISTS(2) THEN
        DBMS_OUTPUT.PUT_LINE('Element 2 exists');
    END IF;

    IF l_numbers(2) IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Element 2 has NULL value');
    END IF;
END;
/
~~~

EXISTS(2) trả TRUE vì phần tử số 2 tồn tại. Giá trị của phần tử đó là NULL. Đây không phải phần tử bị thiếu.

### 3.4 Chỉ số không tồn tại hoặc phần tử đã bị xóa

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20, 30);
BEGIN
    l_numbers.DELETE(2);

    DBMS_OUTPUT.PUT_LINE(l_numbers.EXISTS(2)); -- FALSE
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT);     -- 2
END;
/
~~~

Sau DELETE(2), phần tử ở chỉ số 2 không còn tồn tại. COUNT giảm, nhưng collection không tự dồn phần tử 3 về chỉ số 2. Nested table trở thành sparse.

### 3.5 Bảng phân biệt

| Trạng thái | EXISTS(i) | Đọc collection(i) | Ý nghĩa |
|---|---|---|---|
| Collection atomically null | FALSE | Các method/đọc phần tử thường gây COLLECTION_IS_NULL | Chưa khởi tạo collection |
| Collection rỗng đã khởi tạo | FALSE với mọi i | Không có phần tử để đọc | Collection hợp lệ, COUNT = 0 |
| Phần tử tồn tại, giá trị NULL | TRUE | Trả NULL | Slot tồn tại nhưng chưa có giá trị nghiệp vụ |
| Phần tử bị DELETE / key không có | FALSE | Có thể phát sinh NO_DATA_FOUND hoặc lỗi subscript tùy kiểu và phạm vi | Slot/key không tồn tại |

Không dùng kiểm tra giá trị NULL để suy ra phần tử có tồn tại hay không. Hãy dùng EXISTS để kiểm tra sự tồn tại, sau đó mới đọc giá trị.

## 4. Các collection method cơ bản

Các method cung cấp cách kiểm tra số lượng, giới hạn và chỉ số phần tử hiện có.

| Method | Ý nghĩa |
|---|---|
| COUNT | Số phần tử hiện đang tồn tại |
| FIRST | Chỉ số nhỏ nhất đang tồn tại; NULL nếu collection rỗng |
| LAST | Chỉ số lớn nhất đang tồn tại; NULL nếu collection rỗng |
| PRIOR(n) | Chỉ số hiện có ngay trước n |
| NEXT(n) | Chỉ số hiện có ngay sau n |
| EXISTS(n) | TRUE nếu phần tử tại n tồn tại |
| LIMIT | Giới hạn tối đa; có giá trị với VARRAY, NULL với nested table và associative array |

### 4.1 COUNT

COUNT trả về số phần tử đang tồn tại, không phải chỉ số lớn nhất.

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20, 30, 40);
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT); -- 4

    l_numbers.DELETE(2);

    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT); -- 3
    DBMS_OUTPUT.PUT_LINE(l_numbers.LAST);  -- 4
END;
/
~~~

Sau khi xóa phần tử 2, COUNT = 3 nhưng LAST = 4. Không được dùng COUNT như chỉ số cuối trong collection thưa.

### 4.2 FIRST và LAST

FIRST trả chỉ số nhỏ nhất đang tồn tại; LAST trả chỉ số lớn nhất đang tồn tại. Nếu collection đã khởi tạo nhưng rỗng, cả hai trả NULL.

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20, 30, 40, 50);
BEGIN
    l_numbers.DELETE(1);
    l_numbers.DELETE(4);

    DBMS_OUTPUT.PUT_LINE(l_numbers.FIRST); -- 2
    DBMS_OUTPUT.PUT_LINE(l_numbers.LAST);  -- 5
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT); -- 3
END;
/
~~~

Các chỉ số còn tồn tại là 2, 3 và 5. FIRST và LAST không bảo đảm các chỉ số nằm giữa đều có phần tử.

### 4.3 PRIOR và NEXT

PRIOR(n) trả chỉ số hiện có trước n; NEXT(n) trả chỉ số hiện có sau n. Chúng bỏ qua các chỉ số đã bị xóa:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20, 30, 40, 50);
BEGIN
    l_numbers.DELETE(2);
    l_numbers.DELETE(4);

    DBMS_OUTPUT.PUT_LINE(l_numbers.PRIOR(5)); -- 3
    DBMS_OUTPUT.PUT_LINE(l_numbers.NEXT(1));  -- 3
    DBMS_OUTPUT.PUT_LINE(l_numbers.NEXT(3));  -- 5
END;
/
~~~

Nếu không có chỉ số trước hoặc sau, PRIOR/NEXT trả NULL. Đây là cách an toàn để đi qua collection thưa.

### 4.4 EXISTS

EXISTS(n) kiểm tra phần tử có tồn tại hay không:

~~~sql
IF l_numbers.EXISTS(3) THEN
    DBMS_OUTPUT.PUT_LINE(l_numbers(3));
END IF;
~~~

EXISTS trả FALSE nếu phần tử chưa được tạo, đã bị xóa hoặc chỉ số không thuộc collection. Nó vẫn trả TRUE nếu phần tử tồn tại nhưng giá trị là NULL.

EXISTS là method duy nhất có thể gọi trên collection atomically null. Điều đó hữu ích khi procedure nhận một collection có thể chưa được khởi tạo từ caller.

### 4.5 LIMIT

LIMIT trả số phần tử tối đa của VARRAY:

~~~sql
DECLARE
    TYPE t_tags IS VARRAY(10) OF VARCHAR2(20);
    l_tags t_tags := t_tags('A', 'B');
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_tags.COUNT); -- 2
    DBMS_OUTPUT.PUT_LINE(l_tags.LIMIT); -- 10
END;
/
~~~

Với nested table và associative array, LIMIT trả NULL vì hai kiểu này không có giới hạn tối đa được khai báo theo cú pháp collection type.

## 5. Các method thay đổi collection

DELETE, EXTEND và TRIM không được hỗ trợ đồng nhất trên cả ba kiểu collection.

| Method | Associative array | Nested table | VARRAY |
|---|---:|---:|---:|
| DELETE | Có | Có | Không |
| EXTEND | Không | Có | Có |
| TRIM | Không | Có | Có |

### 5.1 DELETE

DELETE xóa phần tử:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20, 30, 40, 50);
BEGIN
    l_numbers.DELETE(3);

    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT); -- 4
    DBMS_OUTPUT.PUT_LINE(l_numbers.EXISTS(3)); -- FALSE
END;
/
~~~

Các dạng thường dùng:

- DELETE: xóa toàn bộ phần tử.
- DELETE(n): xóa phần tử tại chỉ số n.
- DELETE(m, n): xóa các phần tử trong khoảng chỉ số m đến n.

DELETE trên nested table có thể tạo khoảng trống. DELETE trên associative array bỏ key khỏi map. VARRAY không hỗ trợ DELETE; nếu cần bỏ phần tử trong varray, phải thiết kế lại collection (ví dụ tạo varray mới chỉ chứa các phần tử cần giữ) hoặc chọn nested table nếu nghiệp vụ cần xóa rời rạc.

### 5.2 EXTEND

EXTEND thêm phần tử ở cuối nested table hoặc varray:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20);
BEGIN
    l_numbers.EXTEND;
    l_numbers(3) := 30;

    l_numbers.EXTEND(2);
    l_numbers(4) := 40;
    l_numbers(5) := 50;

    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT); -- 5
END;
/
~~~

Các dạng:

- EXTEND: thêm một phần tử mới có giá trị NULL.
- EXTEND(n): thêm n phần tử mới có giá trị NULL.
- EXTEND(n, i): thêm n bản sao của phần tử tại chỉ số i.

Ví dụ EXTEND(n, i):

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20);
BEGIN
    l_numbers.EXTEND(2, 1);

    DBMS_OUTPUT.PUT_LINE(l_numbers(3)); -- 10
    DBMS_OUTPUT.PUT_LINE(l_numbers(4)); -- 10
END;
/
~~~

EXTEND không dùng cho associative array. Không thể EXTEND một nested table hoặc varray atomically null; phải khởi tạo trước bằng constructor hoặc phép gán hợp lệ. VARRAY không thể vượt LIMIT.

Phần tử mới được EXTEND có tồn tại nhưng giá trị ban đầu là NULL. Vì vậy EXISTS trên chỉ số mới trả TRUE, còn kiểm tra giá trị bằng IS NULL cũng trả TRUE.

### 5.3 TRIM

TRIM xóa một hoặc nhiều phần tử ở cuối nested table hoặc varray:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20, 30, 40);
BEGIN
    l_numbers.TRIM;
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT); -- 3
    DBMS_OUTPUT.PUT_LINE(l_numbers.LAST);  -- 3

    l_numbers.TRIM(2);
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT); -- 1
END;
/
~~~

TRIM không dùng cho associative array. TRIM(2) loại bỏ hai phần tử cuối của phần cuối collection theo cấu trúc nội bộ.

### 5.4 Cẩn thận khi trộn DELETE và TRIM

DELETE và TRIM có cách nhìn khác nhau về phần tử đã bị xóa:

- DELETE đánh dấu phần tử không còn tồn tại, có thể để lại khoảng trống trong nested table.
- TRIM thao tác trên phần cuối của collection theo kích thước nội bộ; nó có thể loại bỏ cả vị trí đã bị DELETE ở cuối.

Vì vậy, trộn DELETE và TRIM trên cùng một nested table có thể gây khó dự đoán chỉ số còn lại. Nếu thuật toán cần giữ chỉ số thưa, ưu tiên dùng DELETE và FIRST/NEXT. Nếu thuật toán quản lý một dãy liên tục như stack, dùng EXTEND/TRIM theo quy ước rõ ràng. Không giả định TRIM tương đương DELETE(LAST).

## 6. Chỉ số thưa (sparse collection)

Collection thưa là collection mà các chỉ số phần tử đang tồn tại không liên tục. Nested table có thể trở nên thưa sau DELETE; associative array thường thưa tự nhiên vì key được tạo tùy ý. VARRAY luôn dense.

### 6.1 Ví dụ nested table thưa

~~~sql
DECLARE
    TYPE t_names IS TABLE OF VARCHAR2(30);
    l_names t_names := t_names(
        'An', 'Binh', 'Chi', 'Dung', 'Hoa'
    );
BEGIN
    l_names.DELETE(2);
    l_names.DELETE(4);

    DBMS_OUTPUT.PUT_LINE('COUNT = ' || l_names.COUNT);
    DBMS_OUTPUT.PUT_LINE('FIRST = ' || l_names.FIRST);
    DBMS_OUTPUT.PUT_LINE('LAST  = ' || l_names.LAST);
END;
/
~~~

Kết quả về mặt chỉ số:

| Chỉ số | Phần tử | Trạng thái |
|---:|---|---|
| 1 | An | Tồn tại |
| 2 | Binh | Đã xóa |
| 3 | Chi | Tồn tại |
| 4 | Dung | Đã xóa |
| 5 | Hoa | Tồn tại |

COUNT = 3, FIRST = 1, LAST = 5. Không thể suy ra chỉ số tồn tại từ dãy 1 đến COUNT.

### 6.2 Vì sao FOR i IN 1..COUNT không an toàn?

Đoạn sau chỉ đúng với collection dense có chỉ số liên tục bắt đầu từ 1:

~~~sql
FOR i IN 1 .. l_names.COUNT LOOP
    DBMS_OUTPUT.PUT_LINE(l_names(i));
END LOOP;
~~~

Với collection ở ví dụ trên, COUNT = 3 nên vòng lặp đọc các chỉ số 1, 2, 3. Chỉ số 2 đã bị xóa và gây lỗi khi truy cập; chỉ số 5 bị bỏ qua dù phần tử vẫn tồn tại.

Tương tự, FIRST..LAST cũng không an toàn nếu có lỗ ở giữa:

~~~sql
FOR i IN l_names.FIRST .. l_names.LAST LOOP
    DBMS_OUTPUT.PUT_LINE(l_names(i));
END LOOP;
~~~

Vòng lặp này vẫn đi qua chỉ số đã xóa.

### 6.3 Duyệt bằng FIRST và NEXT

Đây là mẫu tổng quát để duyệt collection thưa:

~~~sql
DECLARE
    TYPE t_names IS TABLE OF VARCHAR2(30);
    l_names t_names := t_names(
        'An', 'Binh', 'Chi', 'Dung', 'Hoa'
    );
    l_idx PLS_INTEGER;
BEGIN
    l_names.DELETE(2);
    l_names.DELETE(4);

    l_idx := l_names.FIRST;

    WHILE l_idx IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Index=' || l_idx || ', value=' || l_names(l_idx)
        );

        l_idx := l_names.NEXT(l_idx);
    END LOOP;
END;
/
~~~

NEXT tự bỏ qua các chỉ số đã xóa và trả NULL sau phần tử cuối. Mẫu này cũng dùng được với associative array; nếu key là chuỗi, biến giữ key phải có kiểu tương thích với kiểu key.

### 6.4 Duyệt associative array có key rời rạc

~~~sql
DECLARE
    TYPE t_score_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    l_scores t_score_map;
    l_key PLS_INTEGER;
BEGIN
    l_scores(10) := 85;
    l_scores(30) := 92;
    l_scores(100) := 77;

    l_key := l_scores.FIRST;
    WHILE l_key IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Key=' || l_key || ', score=' || l_scores(l_key)
        );
        l_key := l_scores.NEXT(l_key);
    END LOOP;
END;
/
~~~

Không cần giả định key bắt đầu từ 1 hoặc liên tục. FIRST/NEXT là cách duyệt tự nhiên của associative array.

## 7. EXISTS trước khi đọc phần tử

Nếu chỉ số có thể không tồn tại, dùng EXISTS để kiểm tra trước:

~~~sql
IF l_values.EXISTS(p_index) THEN
    IF l_values(p_index) IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Element exists but value is NULL');
    ELSE
        DBMS_OUTPUT.PUT_LINE(l_values(p_index));
    END IF;
ELSE
    DBMS_OUTPUT.PUT_LINE('Element does not exist');
END IF;
~~~

Thứ tự rất quan trọng: chỉ đọc l_values(p_index) sau khi EXISTS trả TRUE.

Không viết:

~~~sql
IF l_values(p_index) IS NOT NULL
   AND l_values.EXISTS(p_index) THEN
    ...
END IF;
~~~

Vì biểu thức có thể truy cập phần tử trước khi kiểm tra EXISTS; không nên dựa vào thứ tự đánh giá biểu thức boolean để bảo vệ truy cập collection.

### 7.1 Kiểm tra collection có được khởi tạo

Với nested table hoặc varray có thể atomically null:

~~~sql
IF l_values.EXISTS(1) THEN
    -- Có phần tử 1.
ELSE
    -- Chưa có phần tử 1; collection có thể rỗng hoặc atomically null.
END IF;
~~~

EXISTS không phân biệt collection rỗng với collection atomically null vì cả hai đều trả FALSE cho chỉ số không tồn tại. Nếu cần biết trạng thái khởi tạo để áp dụng logic khác, hãy thiết kế API nhận biết rõ trạng thái hoặc khởi tạo collection ngay khi tạo biến.

## 8. Các exception thường gặp

Truy cập collection sai trạng thái hoặc sai chỉ số có thể gây exception. Các lỗi phổ biến:

| Exception | Mã lỗi thường gặp | Nguyên nhân |
|---|---:|---|
| COLLECTION_IS_NULL | ORA-06531 | Gọi method ngoài EXISTS hoặc truy cập/gán phần tử trên collection atomically null |
| SUBSCRIPT_OUTSIDE_LIMIT | ORA-06532 | Subscript nằm ngoài giới hạn hợp lệ của collection, ví dụ vượt giới hạn VARRAY |
| SUBSCRIPT_BEYOND_COUNT | ORA-06533 | Truy cập phần tử vượt số phần tử hiện có, thường gặp với VARRAY |
| NO_DATA_FOUND | ORA-01403 | Truy cập phần tử không tồn tại, chẳng hạn phần tử nested table đã bị DELETE hoặc key associative array chưa được gán |

Exception cụ thể phụ thuộc loại collection và thao tác. Ví dụ với varray, chỉ số lớn hơn LIMIT nằm ngoài giới hạn; chỉ số lớn hơn COUNT nhưng không vượt LIMIT vẫn chưa có phần tử để đọc. Với nested table thưa, chỉ số bị DELETE có thể gây NO_DATA_FOUND.

### 8.1 COLLECTION_IS_NULL

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers;
BEGIN
    l_numbers.EXTEND;
END;
/
~~~

EXTEND không thể khởi tạo collection atomically null; cần gán constructor trước:

~~~sql
l_numbers := t_numbers();
l_numbers.EXTEND;
~~~

### 8.2 NO_DATA_FOUND do phần tử bị xóa

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20, 30);
BEGIN
    l_numbers.DELETE(2);
    DBMS_OUTPUT.PUT_LINE(l_numbers(2));
END;
/
~~~

Chỉ số 2 không còn phần tử. Hãy kiểm tra EXISTS trước khi đọc.

### 8.3 SUBSCRIPT_BEYOND_COUNT và SUBSCRIPT_OUTSIDE_LIMIT

Với VARRAY:

~~~sql
DECLARE
    TYPE t_small_array IS VARRAY(3) OF NUMBER;
    l_values t_small_array := t_small_array(10, 20);
BEGIN
    -- Chỉ số 3 chưa có phần tử vì COUNT = 2.
    DBMS_OUTPUT.PUT_LINE(l_values(3));
END;
/
~~~

Đọc chỉ số chưa có phần tử vượt COUNT có thể gây SUBSCRIPT_BEYOND_COUNT. Nếu truy cập chỉ số vượt LIMIT hoặc ngoài miền chỉ số hợp lệ, có thể gặp SUBSCRIPT_OUTSIDE_LIMIT. Dùng EXISTS và COUNT/LIMIT để tránh truy cập không hợp lệ.

## 9. VARRAY dense và giới hạn LIMIT

VARRAY phù hợp với danh sách có số phần tử tối đa đã biết và cần giữ thứ tự tuần tự. VARRAY không tạo lỗ bằng DELETE riêng phần tử.

### 9.1 COUNT, LAST và LIMIT

~~~sql
DECLARE
    TYPE t_codes IS VARRAY(4) OF VARCHAR2(10);
    l_codes t_codes := t_codes('A', 'B');
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_codes.COUNT); -- 2
    DBMS_OUTPUT.PUT_LINE(l_codes.LAST);  -- 2
    DBMS_OUTPUT.PUT_LINE(l_codes.LIMIT); -- 4

    l_codes.EXTEND;
    l_codes(3) := 'C';

    DBMS_OUTPUT.PUT_LINE(l_codes.COUNT); -- 3
END;
/
~~~

Với VARRAY không rỗng, COUNT và LAST bằng nhau vì chỉ số luôn liên tục từ 1. LIMIT là giới hạn khai báo.

### 9.2 Không thể vượt LIMIT

~~~sql
DECLARE
    TYPE t_codes IS VARRAY(2) OF VARCHAR2(10);
    l_codes t_codes := t_codes('A', 'B');
BEGIN
    l_codes.EXTEND;
END;
/
~~~

EXTEND sẽ lỗi vì collection đã đạt giới hạn 2. Có thể kiểm tra COUNT < LIMIT trước khi thêm:

~~~sql
IF l_codes.COUNT < l_codes.LIMIT THEN
    l_codes.EXTEND;
    l_codes(l_codes.COUNT) := 'C';
END IF;
~~~

### 9.3 Muốn xóa một phần tử ở giữa

VARRAY không hỗ trợ DELETE( n ). Nếu nghiệp vụ cần xóa tùy ý và để lại chỉ số thưa, nested table hoặc associative array thường phù hợp hơn. Nếu vẫn cần VARRAY, tạo một VARRAY mới và sao chép các phần tử muốn giữ theo thứ tự.

## 10. Nested table: DELETE, EXTEND và TRIM

Nested table có thể vừa thay đổi kích thước vừa trở nên sparse. Cần xác định thuật toán dựa trên việc có cần giữ nguyên subscript hay chỉ cần một danh sách dense.

### 10.1 Xóa phần tử giữa và duyệt phần còn lại

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_values t_numbers := t_numbers(100, 200, 300, 400, 500);
    l_idx PLS_INTEGER;
BEGIN
    l_values.DELETE(2);

    l_idx := l_values.FIRST;
    WHILE l_idx IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(l_idx || ': ' || l_values(l_idx));
        l_idx := l_values.NEXT(l_idx);
    END LOOP;
END;
/
~~~

Phần tử ở chỉ số 2 bị xóa; các chỉ số 3, 4 và 5 vẫn giữ nguyên. Oracle không tự dồn dữ liệu để lấp khoảng trống.

### 10.2 Xóa toàn bộ

~~~sql
l_values.DELETE;
~~~

DELETE không tham số xóa tất cả phần tử. Với collection đã khởi tạo, collection vẫn là collection hợp lệ nhưng rỗng; COUNT = 0 và FIRST/LAST trả NULL. Nó không giống việc gán biến về trạng thái atomically null.

### 10.3 Dùng EXTEND để thêm phần tử

~~~sql
l_values.EXTEND;
l_values(l_values.LAST) := 600;
~~~

EXTEND tạo thêm một slot ở cuối và giá trị ban đầu là NULL. Để code rõ ràng, có thể lưu chỉ số mới sau khi EXTEND hoặc dùng LAST để xác định vị trí cuối hiện có. Với collection thưa, không dùng COUNT làm chỉ số mới nếu không chắc collection dense.

### 10.4 Khi cần danh sách dense mới

Nếu muốn loại bỏ các lỗ và tạo một collection liên tục từ 1, có thể sao chép các phần tử hiện tồn tại sang collection mới:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_source t_numbers := t_numbers(10, 20, 30, 40, 50);
    l_dense  t_numbers := t_numbers();
    l_idx    PLS_INTEGER;
BEGIN
    l_source.DELETE(2);
    l_source.DELETE(4);

    l_idx := l_source.FIRST;
    WHILE l_idx IS NOT NULL LOOP
        l_dense.EXTEND;
        l_dense(l_dense.LAST) := l_source(l_idx);
        l_idx := l_source.NEXT(l_idx);
    END LOOP;

    -- l_dense có chỉ số liên tục 1..3.
    DBMS_OUTPUT.PUT_LINE(l_dense.COUNT);
END;
/
~~~

Đây là thao tác tạo collection mới, không phải DELETE tự compact. Nó hữu ích khi downstream code yêu cầu dãy chỉ số liên tục.

## 11. Associative array: key không liên tục

Associative array thường dùng cho tra cứu trong PL/SQL:

~~~sql
DECLARE
    TYPE t_employee_map IS TABLE OF VARCHAR2(100)
        INDEX BY PLS_INTEGER;
    l_names t_employee_map;
BEGIN
    l_names(100) := 'An';
    l_names(500) := 'Binh';
    l_names(900) := 'Chi';

    l_names.DELETE(500);

    IF l_names.EXISTS(500) THEN
        DBMS_OUTPUT.PUT_LINE(l_names(500));
    ELSE
        DBMS_OUTPUT.PUT_LINE('Key 500 was removed');
    END IF;
END;
/
~~~

Associative array có key rời rạc và DELETE bỏ key. Không có EXTEND/TRIM vì không quản lý dãy phần tử bằng một kích thước liên tục. Dùng FIRST/NEXT để duyệt key hiện có.

### 11.1 Associative array key chuỗi

~~~sql
DECLARE
    TYPE t_config_map IS TABLE OF VARCHAR2(200)
        INDEX BY VARCHAR2(30);
    l_config t_config_map;
    l_key VARCHAR2(30);
BEGIN
    l_config('LANGUAGE') := 'vi';
    l_config('TIMEZONE') := 'Asia/Ho_Chi_Minh';
    l_config('THEME') := 'dark';

    l_key := l_config.FIRST;
    WHILE l_key IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(l_key || '=' || l_config(l_key));
        l_key := l_config.NEXT(l_key);
    END LOOP;
END;
/
~~~

Với key chuỗi, FIRST/NEXT đi theo thứ tự index của associative array, không phải thứ tự INSERT. Thứ tự có thể chịu ảnh hưởng NLS_SORT và NLS_COMP. Nếu cần thứ tự nghiệp vụ ổn định độc lập session, hãy quản lý thứ tự riêng.

## 12. Collection method trong vòng lặp và xử lý batch

### 12.1 Vòng lặp dense đơn giản

Với VARRAY hoặc nested table chắc chắn dense:

~~~sql
FOR i IN 1 .. l_values.COUNT LOOP
    process_value(l_values(i));
END LOOP;
~~~

Đây là mẫu ngắn gọn khi collection đã khởi tạo, COUNT > 0 và chỉ số liên tục từ 1. Nếu COUNT = 0, vòng lặp 1..0 không chạy; tuy nhiên cần đảm bảo collection không atomically null trước khi đọc COUNT.

### 12.2 Vòng lặp sparse tổng quát

~~~sql
DECLARE
    l_idx PLS_INTEGER;
BEGIN
    l_idx := l_values.FIRST;
    WHILE l_idx IS NOT NULL LOOP
        process_value(l_values(l_idx));
        l_idx := l_values.NEXT(l_idx);
    END LOOP;
END;
/
~~~

Đây là mẫu nên dùng khi collection có thể bị DELETE hoặc có key rời rạc.

### 12.3 BULK COLLECT thường tạo collection dense

Ví dụ:

~~~sql
DECLARE
    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    l_employee_ids t_employee_ids;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_employee_ids
    FROM employees
    WHERE department_id = 10
    ORDER BY employee_id;

    FOR i IN 1 .. l_employee_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(l_employee_ids(i));
    END LOOP;
END;
/
~~~

BULK COLLECT nạp các dòng trả về thành collection liên tục từ chỉ số 1 trong tình huống thông thường này. Nếu collection sau đó bị DELETE một số phần tử, không còn giả định dense.

### 12.4 BULK COLLECT với LIMIT

LIMIT trong FETCH BULK COLLECT là giới hạn số dòng lấy mỗi batch; nó không phải method LIMIT của nested table hay associative array. Ví dụ:

~~~sql
DECLARE
    CURSOR c_emp IS
        SELECT employee_id
        FROM employees
        ORDER BY employee_id;

    TYPE t_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_ids;
BEGIN
    OPEN c_emp;
    LOOP
        FETCH c_emp BULK COLLECT INTO l_ids LIMIT 500;
        EXIT WHEN l_ids.COUNT = 0;

        FOR i IN 1 .. l_ids.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(l_ids(i));
        END LOOP;
    END LOOP;
    CLOSE c_emp;
END;
/
~~~

Mỗi lần FETCH thay collection bằng batch kết quả mới. Vì vậy có thể duyệt 1..COUNT nếu không xóa phần tử trong batch.

### 12.5 FORALL và chỉ số thưa

FORALL có thể làm việc với collection thưa bằng các dạng chỉ số phù hợp, chẳng hạn INDICES OF hoặc VALUES OF. Ví dụ:

~~~sql
FORALL i IN INDICES OF l_ids
    UPDATE employees
    SET salary = salary + 100
    WHERE employee_id = l_ids(i);
~~~

INDICES OF cho FORALL đi qua các chỉ số hiện có thay vì giả định 1..COUNT. Khi dùng SAVE EXCEPTIONS, cần xem SQL%BULK_EXCEPTIONS để xử lý từng lỗi DML; chi tiết FORALL là chủ đề riêng nhưng cùng dựa trên việc hiểu đúng collection index.

## 13. Viết procedure nhận collection từ caller

Procedure nên xác định hợp đồng: caller phải truyền collection đã khởi tạo hay procedure tự chấp nhận collection null.

### 13.1 Kiểm tra EXISTS an toàn với collection có thể null

~~~sql
CREATE TYPE t_number_table AS TABLE OF NUMBER;
/

CREATE OR REPLACE PROCEDURE print_first_value (
    p_values IN t_number_table
)
AS
BEGIN
    IF p_values.EXISTS(1) THEN
        DBMS_OUTPUT.PUT_LINE(p_values(1));
    ELSE
        DBMS_OUTPUT.PUT_LINE('No element at index 1');
    END IF;
END;
/
~~~

T_NUMBER_TABLE là kiểu nested table được tạo ở mức schema để procedure độc lập có thể dùng làm kiểu tham số. EXISTS có thể được gọi ngay cả khi tham số collection đang atomically null.

### 13.2 Khởi tạo collection null nếu procedure cần thêm phần tử

Nếu procedure cần EXTEND hoặc gán phần tử cho nested table/varray, phải bảo đảm collection đã khởi tạo:

Nếu procedure cần gọi EXTEND hoặc đọc phần tử bằng FIRST/NEXT, hãy quy định rõ caller phải truyền collection đã khởi tạo. EXISTS có thể kiểm tra một subscript an toàn trên collection null, nhưng không thể phân biệt collection atomically null với collection rỗng chỉ bằng kết quả FALSE. Nếu API cần phân biệt hai trạng thái này, truyền thêm một cờ trạng thái riêng hoặc thiết kế caller luôn khởi tạo collection bằng constructor trước khi gọi.

### 13.3 Không sửa collection IN parameter

Tham số IN không được dùng để thay đổi collection của caller. Nếu cần thêm/xóa phần tử, dùng tham số IN OUT hoặc tạo collection kết quả OUT với hợp đồng rõ ràng.

## 14. Hiệu năng và bộ nhớ

### 14.1 Collection lưu trong bộ nhớ session

PL/SQL collection thường được lưu trong bộ nhớ của session/engine khi xử lý. Một collection rất lớn có thể tiêu tốn PGA hoặc bộ nhớ session, đặc biệt khi có nhiều session chạy đồng thời.

### 14.2 Dùng LIMIT để chia batch

Với truy vấn lớn, FETCH BULK COLLECT ... LIMIT giúp giới hạn số dòng giữ trong collection mỗi lần. Chọn batch size theo độ rộng dòng, lượng bộ nhớ, thời gian xử lý và mức tải.

### 14.3 COUNT không đo dung lượng bộ nhớ

COUNT chỉ là số phần tử đang tồn tại. Nó không cho biết chính xác bytes đang dùng, kích thước capacity nội bộ hoặc tổng chi phí của collection.

### 14.4 Tránh copy collection lớn không cần thiết

Gán collection, truyền collection qua nhiều layer hoặc tạo bản dense mới có thể phát sinh chi phí copy/bộ nhớ. Nếu chỉ cần duyệt, dùng FIRST/NEXT trực tiếp; chỉ tạo bản sao khi nghiệp vụ thực sự cần.

## 15. Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| COLLECTION_IS_NULL | Dùng method trên nested table/varray chưa khởi tạo | Gán constructor trước khi dùng |
| NO_DATA_FOUND | Đọc chỉ số đã DELETE hoặc key chưa được gán | Kiểm tra EXISTS trước |
| SUBSCRIPT_BEYOND_COUNT | Đọc chỉ số vượt số phần tử hiện có, thường với varray | Kiểm tra EXISTS/COUNT |
| SUBSCRIPT_OUTSIDE_LIMIT | Chỉ số vượt giới hạn hợp lệ, chẳng hạn vượt VARRAY LIMIT | Kiểm tra LIMIT và index |
| Lặp 1..COUNT bỏ sót phần tử | Collection sparse, COUNT không phải chỉ số cuối | Dùng FIRST/NEXT |
| Lặp FIRST..LAST gây lỗi | Có chỉ số bị xóa ở giữa | Dùng NEXT để bỏ qua lỗ |
| Gọi EXTEND trên associative array | Method không được hỗ trợ cho kiểu này | Gán trực tiếp theo key |
| Gọi DELETE(n) trên VARRAY | VARRAY không hỗ trợ xóa riêng phần tử | Tạo collection mới hoặc chọn nested table |
| VARRAY EXTEND vượt LIMIT | Đã đạt số phần tử tối đa | Kiểm tra COUNT < LIMIT |
| Nhầm NULL với phần tử không tồn tại | Giá trị NULL vẫn có thể thuộc một phần tử hiện có | Kiểm tra EXISTS trước, rồi IS NULL |
| Dùng TRIM như DELETE(LAST) | TRIM thao tác theo kích thước nội bộ, kể cả vị trí đã xóa | Không trộn DELETE và TRIM tùy tiện |
| Giả định associative array theo thứ tự chèn | Key được duyệt theo thứ tự index | Lưu thứ tự riêng nếu cần |

## 16. Bài lab: quan sát sparse index và collection methods

Các block sau chạy trong schema PL/SQL thực hành. Chúng dùng collection local nên không tạo hoặc thay đổi bảng nghiệp vụ.

### 16.1 So sánh COUNT, FIRST, LAST trước và sau DELETE

~~~sql
SET SERVEROUTPUT ON

DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_values t_numbers := t_numbers(10, 20, 30, 40, 50);
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Before: COUNT=' || l_values.COUNT ||
        ', FIRST=' || l_values.FIRST ||
        ', LAST=' || l_values.LAST
    );

    l_values.DELETE(2);
    l_values.DELETE(4);

    DBMS_OUTPUT.PUT_LINE(
        'After: COUNT=' || l_values.COUNT ||
        ', FIRST=' || l_values.FIRST ||
        ', LAST=' || l_values.LAST
    );

    DBMS_OUTPUT.PUT_LINE('EXISTS(2)=' ||
        CASE WHEN l_values.EXISTS(2) THEN 'TRUE' ELSE 'FALSE' END);
    DBMS_OUTPUT.PUT_LINE('NEXT(1)=' || l_values.NEXT(1));
    DBMS_OUTPUT.PUT_LINE('NEXT(3)=' || l_values.NEXT(3));
END;
/
~~~

Quan sát COUNT giảm nhưng LAST không nhất thiết bằng COUNT; NEXT bỏ qua các chỉ số đã xóa.

### 16.2 Phân biệt phần tử NULL và phần tử bị xóa

~~~sql
DECLARE
    TYPE t_values IS TABLE OF NUMBER;
    l_values t_values := t_values(10, NULL, 30);
BEGIN
    l_values.DELETE(3);

    DBMS_OUTPUT.PUT_LINE(
        'Index 2 exists=' ||
        CASE WHEN l_values.EXISTS(2) THEN 'TRUE' ELSE 'FALSE' END
    );
    DBMS_OUTPUT.PUT_LINE(
        'Index 2 is null=' ||
        CASE WHEN l_values(2) IS NULL THEN 'TRUE' ELSE 'FALSE' END
    );

    DBMS_OUTPUT.PUT_LINE(
        'Index 3 exists=' ||
        CASE WHEN l_values.EXISTS(3) THEN 'TRUE' ELSE 'FALSE' END
    );
END;
/
~~~

Chỉ số 2 tồn tại với giá trị NULL; chỉ số 3 đã bị xóa.

### 16.3 Duyệt nested table thưa

~~~sql
DECLARE
    TYPE t_values IS TABLE OF VARCHAR2(20);
    l_values t_values := t_values('A', 'B', 'C', 'D', 'E');
    l_idx PLS_INTEGER;
BEGIN
    l_values.DELETE(2);
    l_values.DELETE(4);

    l_idx := l_values.FIRST;
    WHILE l_idx IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(l_idx || '=' || l_values(l_idx));
        l_idx := l_values.NEXT(l_idx);
    END LOOP;
END;
/
~~~

Kết quả chỉ in các chỉ số 1, 3 và 5.

### 16.4 So sánh ba kiểu collection

~~~sql
DECLARE
    TYPE t_assoc IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    TYPE t_nested IS TABLE OF NUMBER;
    TYPE t_array IS VARRAY(5) OF NUMBER;

    l_assoc  t_assoc;
    l_nested t_nested := t_nested(10, 20, 30);
    l_array  t_array := t_array(10, 20, 30);
BEGIN
    l_assoc(10) := 100;
    l_assoc(30) := 300;

    l_nested.DELETE(2);
    l_array.EXTEND;
    l_array(4) := 40;

    DBMS_OUTPUT.PUT_LINE('Associative count=' || l_assoc.COUNT);
    DBMS_OUTPUT.PUT_LINE('Nested count=' || l_nested.COUNT);
    DBMS_OUTPUT.PUT_LINE('Nested last=' || l_nested.LAST);
    DBMS_OUTPUT.PUT_LINE('Varray count=' || l_array.COUNT);
    DBMS_OUTPUT.PUT_LINE('Varray limit=' || l_array.LIMIT);
END;
/
~~~

Quan sát associative array dùng key 10 và 30; nested table có khoảng trống ở chỉ số 2; varray vẫn liên tục sau EXTEND.

## 17. Quy tắc thực hành

Khi viết PL/SQL có collection:

1. Xác định collection type trước khi dùng method.
2. Khởi tạo nested table/varray trước khi gọi method ngoài EXISTS.
3. Dùng COUNT để biết số phần tử hiện có, không dùng nó làm chỉ số cuối nếu collection có thể sparse.
4. Dùng FIRST/NEXT để duyệt collection có thể có lỗ hoặc key rời rạc.
5. Dùng EXISTS trước khi đọc chỉ số không chắc chắn.
6. Tách kiểm tra tồn tại khỏi kiểm tra giá trị NULL.
7. Chỉ dùng EXTEND/TRIM với nested table và varray.
8. Chỉ dùng DELETE với associative array và nested table; không xóa riêng phần tử của varray.
9. Kiểm tra LIMIT trước khi EXTEND varray.
10. Không trộn DELETE và TRIM trên cùng nested table nếu chưa hiểu ảnh hưởng đến phần cuối nội bộ.
11. Với associative array key chuỗi, không dựa vào thứ tự chèn.
12. Với collection lớn, cân nhắc BULK COLLECT LIMIT và tránh copy dữ liệu không cần thiết.

## 18. Tổng kết

Collection method là giao diện để kiểm tra và thao tác phần tử trong PL/SQL. Muốn dùng an toàn, cần hiểu collection đang ở trạng thái nào và chỉ số có thực sự tồn tại hay không.

- COUNT đếm phần tử hiện có; LAST trả chỉ số lớn nhất hiện có. Hai giá trị có thể khác nhau trong collection thưa.
- FIRST/LAST xác định biên chỉ số; PRIOR/NEXT đi qua các chỉ số đang tồn tại và bỏ qua phần tử đã xóa.
- EXISTS kiểm tra sự tồn tại, kể cả khi giá trị phần tử là NULL. Đây cũng là method duy nhất có thể gọi trên collection atomically null.
- LIMIT cho biết giới hạn tối đa của VARRAY; nested table và associative array không có LIMIT cố định.
- DELETE tạo lỗ trong nested table hoặc xóa key associative array. VARRAY không hỗ trợ DELETE riêng phần tử.
- EXTEND thêm phần tử NULL vào nested table/varray; TRIM bỏ phần tử ở cuối. Cả hai không áp dụng cho associative array.
- Collection atomically null, collection rỗng, phần tử NULL và chỉ số đã xóa là các trạng thái khác nhau.
- Duyệt collection có thể sparse bằng FIRST/NEXT; chỉ dùng 1..COUNT khi chắc chắn collection dense.

Khi nắm rõ các quy tắc này, code PL/SQL sẽ tránh được lỗi subscript, xử lý được collection thưa và tận dụng collection an toàn trong bulk processing.
