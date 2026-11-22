# Associative array, nested table và VARRAY trong PL/SQL

Trong PL/SQL, **collection** là cấu trúc dữ liệu chứa nhiều phần tử cùng một kiểu. Collection giúp chương trình xử lý một nhóm giá trị trong bộ nhớ, truyền nhiều giá trị giữa các thủ tục, gom dữ liệu trước khi ghi xuống database và giảm số lần chuyển đổi giữa PL/SQL engine với SQL engine.

Oracle cung cấp ba loại collection chính:

- **Associative array**: tập phần tử được truy cập bằng khóa chỉ mục, thường là số nguyên hoặc chuỗi. Collection này phù hợp với lookup trong bộ nhớ và ánh xạ key-value.
- **Nested table**: tập phần tử có thể thay đổi kích thước, có thể trở nên thưa sau khi xóa phần tử. Nested table có thể được dùng trong SQL khi kiểu được khai báo ở cấp schema và cũng có thể được lưu như một cột collection trong bảng.
- **VARRAY** (*variable-size array*): mảng có giới hạn số phần tử tối đa, giữ thứ tự phần tử và luôn liên tục từ chỉ số 1 đến COUNT. VARRAY phù hợp với danh sách nhỏ có giới hạn rõ ràng.

Ba loại đều là collection nhưng khác nhau về cách đánh chỉ mục, khả năng lưu trong bảng SQL, giới hạn kích thước, cách xóa phần tử và các collection methods được hỗ trợ. Chọn đúng loại giúp code dễ hiểu, tránh lỗi chỉ mục và tận dụng được BULK COLLECT/FORALL khi xử lý dữ liệu lớn.

## 1. Collection trong PL/SQL

Một collection chứa nhiều phần tử cùng kiểu dữ liệu. Ví dụ một danh sách mã nhân viên:

~~~sql
DECLARE
    TYPE t_employee_ids IS TABLE OF PLS_INTEGER;
    l_employee_ids t_employee_ids := t_employee_ids(101, 102, 103);
BEGIN
    DBMS_OUTPUT.PUT_LINE('So phan tu: ' || l_employee_ids.COUNT);
    DBMS_OUTPUT.PUT_LINE('Phan tu dau: ' || l_employee_ids(1));
END;
/
~~~

Kết quả:

~~~text
So phan tu: 3
Phan tu dau: 101
~~~

T_EMPLOYEE_IDS là kiểu collection do chương trình khai báo; L_EMPLOYEE_IDS là biến collection; T_EMPLOYEE_IDS(101, 102, 103) là constructor tạo một nested table có ba phần tử.

### 1.1. Collection khác array trong ngôn ngữ lập trình thông thường

Collection PL/SQL có thể:
- Tăng hoặc giảm số phần tử.
- Có chỉ số thưa, tùy loại.
- Dùng các phương thức như COUNT, FIRST, LAST, NEXT, PRIOR, EXISTS.
- Được nạp từ SQL bằng BULK COLLECT.
- Được dùng để thực hiện nhiều DML bằng FORALL.

Không phải collection nào cũng có cùng khả năng. Ví dụ, associative array không có EXTEND; VARRAY không cho xóa riêng một phần tử; nested table có thể bị thưa sau DELETE.

### 1.2. Khai báo type và variable

Một kiểu collection có thể được khai báo trong:
- Khối DECLARE của anonymous PL/SQL block.
- Phần khai báo package.
- Specification/body của procedure hoặc function.
- Schema bằng CREATE TYPE cho các loại collection SQL hỗ trợ.

Ví dụ kiểu local:

~~~sql
DECLARE
    TYPE t_names IS TABLE OF VARCHAR2(100);
    l_names t_names;
BEGIN
    NULL;
END;
/
~~~

Kiểu khai báo trong block chỉ có phạm vi trong block đó. Nếu cần nhiều procedure dùng chung kiểu, có thể khai báo trong package specification. Nếu cần dùng collection như một kiểu SQL ở ngoài PL/SQL, thường khai báo kiểu ở cấp schema bằng CREATE TYPE.

### 1.3. Ba loại collection ở mức khái niệm

~~~text
Associative array
  key -> value
  10  -> 'An'
  20  -> 'Binh'
  50  -> 'Chi'

Nested table
  1 -> 'An'
  2 -> 'Binh'
  3 -> 'Chi'
  DELETE(2) có thể tạo khoảng trống ở chỉ số 2

VARRAY(5)
  1 -> 'An'
  2 -> 'Binh'
  3 -> 'Chi'
  tối đa 5 phần tử, chỉ số liên tục
~~~

## 2. Associative array

**Associative array** (trước đây thường gọi là index-by table) là collection lưu phần tử theo khóa chỉ mục. Khóa có thể là PLS_INTEGER/BINARY_INTEGER hoặc kiểu ký tự được Oracle hỗ trợ.

Associative array thường được dùng như map/dictionary trong bộ nhớ PL/SQL.

### 2.1. Associative array với chỉ mục PLS_INTEGER

~~~sql
DECLARE
    TYPE t_salary_map IS TABLE OF NUMBER
        INDEX BY PLS_INTEGER;

    l_salary_by_employee t_salary_map;
BEGIN
    l_salary_by_employee(101) := 20000000;
    l_salary_by_employee(102) := 25000000;
    l_salary_by_employee(205) := 18000000;

    DBMS_OUTPUT.PUT_LINE(
        'Luong NV 102: ' || l_salary_by_employee(102)
    );

    DBMS_OUTPUT.PUT_LINE(
        'So phan tu: ' || l_salary_by_employee.COUNT
    );
END;
/
~~~

Ở đây chỉ số 101, 102, 205 là key do chương trình chọn. Chúng không bắt buộc phải liên tục và không nhất thiết bắt đầu từ 1.

Associative array phù hợp khi cần tra cứu nhanh theo một mã nghiệp vụ, ví dụ EMPLOYEE_ID -> SALARY hoặc PRODUCT_CODE -> STOCK.

### 2.2. Associative array với khóa chuỗi

~~~sql
DECLARE
    TYPE t_country_map IS TABLE OF VARCHAR2(100)
        INDEX BY VARCHAR2(10);

    l_country_name t_country_map;
BEGIN
    l_country_name('VN') := 'Viet Nam';
    l_country_name('JP') := 'Japan';
    l_country_name('SG') := 'Singapore';

    DBMS_OUTPUT.PUT_LINE(l_country_name('VN'));
END;
/
~~~

Khóa chuỗi giúp biểu diễn ánh xạ như mã quốc gia sang tên quốc gia. Khi duyệt associative array có key chuỗi, thứ tự FIRST/NEXT chịu ảnh hưởng của quy tắc sắp xếp ký tự/NLS của session; không nên coi đó là thứ tự INSERT.

### 2.3. Associative array không cần constructor

Biến associative array mới khai báo là collection rỗng có thể sử dụng ngay:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    l_numbers t_numbers;
BEGIN
    l_numbers(1) := 10;
    l_numbers(5) := 50;
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT);
END;
/
~~~

Không cần gọi constructor. Cú pháp constructor như T_NUMBERS(10, 20) không dùng cho associative array như nested table hoặc VARRAY.

### 2.4. Associative array có thể thưa

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    l_numbers t_numbers;
BEGIN
    l_numbers(2) := 20;
    l_numbers(10) := 100;
    l_numbers(100) := 1000;

    DBMS_OUTPUT.PUT_LINE('COUNT=' || l_numbers.COUNT);
    DBMS_OUTPUT.PUT_LINE('FIRST=' || l_numbers.FIRST);
    DBMS_OUTPUT.PUT_LINE('LAST=' || l_numbers.LAST);
END;
/
~~~

COUNT = 3, FIRST = 2 và LAST = 100. COUNT là số phần tử hiện có; LAST là chỉ số lớn nhất, không phải số phần tử.

Đừng viết vòng lặp 1..COUNT nếu chỉ số không bảo đảm liên tục. Dùng FIRST/NEXT để duyệt an toàn.

### 2.5. Duyệt associative array bằng FIRST và NEXT

~~~sql
DECLARE
    TYPE t_salary_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    l_salary t_salary_map;
    l_key PLS_INTEGER;
BEGIN
    l_salary(101) := 20000000;
    l_salary(105) := 25000000;
    l_salary(205) := 18000000;

    l_key := l_salary.FIRST;

    WHILE l_key IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Employee ' || l_key || ': ' || l_salary(l_key)
        );

        l_key := l_salary.NEXT(l_key);
    END LOOP;
END;
/
~~~

FIRST trả chỉ số đầu tiên đang tồn tại; NEXT(key) trả chỉ số kế tiếp đang tồn tại. Khi hết phần tử, NEXT trả NULL.

### 2.6. Kiểm tra phần tử bằng EXISTS

~~~sql
IF l_salary.EXISTS(105) THEN
    DBMS_OUTPUT.PUT_LINE('Da co du lieu');
END IF;
~~~

EXISTS kiểm tra key có tồn tại hay không. Dùng EXISTS trước khi đọc một chỉ số có thể chưa được gán để tránh lỗi truy cập phần tử không tồn tại.

### 2.7. Xóa phần tử associative array

~~~sql
l_salary.DELETE(105); -- Xoa key 105
l_salary.DELETE;      -- Xoa tat ca phan tu
~~~

DELETE không làm các key còn lại được đánh số lại. Nếu các key là 101 và 205 sau khi xóa 105, chúng vẫn giữ nguyên key.

Associative array không hỗ trợ EXTEND, TRIM hoặc LIMIT.

## 3. Nested table

**Nested table** là collection có kích thước thay đổi, được khai báo bằng TABLE OF. Nó có thể được dùng trong PL/SQL và, khi kiểu được khai báo ở cấp schema, có thể được dùng như một kiểu SQL và lưu trong cột collection của bảng.

### 3.1. Khai báo và khởi tạo nested table

~~~sql
DECLARE
    TYPE t_names IS TABLE OF VARCHAR2(100);
    l_names t_names := t_names('An', 'Binh', 'Chi');
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_names.COUNT);
    DBMS_OUTPUT.PUT_LINE(l_names(2));
END;
/
~~~

Nested table dùng chỉ số số nguyên bắt đầu từ 1 khi được tạo bằng constructor. Nó có thể thay đổi kích thước bằng EXTEND và có thể có khoảng trống sau khi DELETE một phần tử.

### 3.2. Nested table chưa khởi tạo và nested table rỗng

Biến nested table khai báo nhưng chưa gán constructor là **atomically null collection**:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers;
BEGIN
    -- l_numbers đang atomically null.
    l_numbers := t_numbers(); -- Khởi tạo collection rỗng.
    DBMS_OUTPUT.PUT_LINE(l_numbers.COUNT);
END;
/
~~~

COUNT trên collection atomically null có thể gây ORA-06531 (Reference to uninitialized collection). Gán constructor rỗng T_NUMBERS() để tạo collection đã khởi tạo nhưng không có phần tử.

Phân biệt:
- Atomically null: chưa được khởi tạo.
- Empty collection: đã khởi tạo, COUNT = 0.

Associative array là trường hợp khác: khai báo biến là có thể dùng ngay, không cần constructor.

### 3.3. Thêm phần tử bằng EXTEND

~~~sql
DECLARE
    TYPE t_names IS TABLE OF VARCHAR2(100);
    l_names t_names := t_names();
BEGIN
    l_names.EXTEND;
    l_names(1) := 'An';

    l_names.EXTEND;
    l_names(2) := 'Binh';

    DBMS_OUTPUT.PUT_LINE(l_names.COUNT);
END;
/
~~~

EXTEND thêm phần tử ở cuối collection. Với nested table và VARRAY, có thể dùng EXTEND(n) để thêm n phần tử nguyên tố chưa gán giá trị.

### 3.4. Xóa một phần tử và tạo khoảng trống

~~~sql
DECLARE
    TYPE t_names IS TABLE OF VARCHAR2(100);
    l_names t_names := t_names('An', 'Binh', 'Chi');
BEGIN
    l_names.DELETE(2);

    DBMS_OUTPUT.PUT_LINE('COUNT=' || l_names.COUNT);
    DBMS_OUTPUT.PUT_LINE('FIRST=' || l_names.FIRST);
    DBMS_OUTPUT.PUT_LINE('LAST=' || l_names.LAST);

    IF l_names.EXISTS(2) THEN
        DBMS_OUTPUT.PUT_LINE('Index 2 ton tai');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Index 2 da bi xoa');
    END IF;
END;
/
~~~

Sau DELETE(2):
- Phần tử 1 vẫn là An.
- Chỉ số 2 không tồn tại.
- Phần tử 3 vẫn là Chi.
- COUNT = 2, LAST = 3.

Nested table trở thành sparse (thưa). Các chỉ số không tự dồn lại.

### 3.5. DELETE toàn bộ nested table

~~~sql
l_names.DELETE;
~~~

DELETE không tham số xóa tất cả phần tử nhưng collection vẫn là một collection đã khởi tạo. Có thể thêm phần tử lại bằng EXTEND.

### 3.6. EXTEND và TRIM

- EXTEND: thêm phần tử ở cuối.
- EXTEND(n): thêm n phần tử.
- EXTEND(n, i): thêm n bản sao của phần tử ở chỉ số i.
- TRIM: bỏ phần tử cuối cùng.
- TRIM(n): bỏ n phần tử cuối.

Ví dụ:

~~~sql
DECLARE
    TYPE t_numbers IS TABLE OF NUMBER;
    l_numbers t_numbers := t_numbers(10, 20, 30);
BEGIN
    l_numbers.EXTEND;
    l_numbers(4) := 40;

    l_numbers.TRIM(2);

    DBMS_OUTPUT.PUT_LINE('COUNT=' || l_numbers.COUNT);
    DBMS_OUTPUT.PUT_LINE('LAST=' || l_numbers.LAST);
END;
/
~~~

TRIM loại phần tử từ cuối collection. Cần thận trọng khi trộn DELETE và TRIM trên nested table: DELETE tạo khoảng trống nhưng không thay đổi kích thước nội bộ theo cách giống TRIM. Nếu xóa phần tử rồi TRIM, phần tử bị loại theo vị trí cuối nội bộ, có thể không phải phần tử mà người viết đang nghĩ tới. Chỉ dùng kết hợp khi đã hiểu trạng thái collection.

### 3.7. Nested table không bảo đảm thứ tự khi lưu trong database

Trong PL/SQL variable, có thể truy cập nested table bằng chỉ số. Nhưng khi nested table được lưu trong bảng SQL và truy vấn bằng TABLE(collection_column), không nên dựa vào thứ tự vật lý để suy ra thứ tự phần tử. Nếu cần thứ tự trong kết quả SQL, dùng ORDER BY theo một cột ordinal hoặc thuộc tính dữ liệu được lưu rõ ràng.

## 4. VARRAY

**VARRAY** là collection có kích thước tối đa được xác định ngay khi khai báo type. VARRAY giữ thứ tự phần tử và luôn dense: chỉ số hợp lệ liên tục từ 1 đến COUNT.

Cú pháp:

~~~sql
TYPE type_name IS VARRAY(maximum_size) OF element_type;
~~~

### 4.1. Khai báo và khởi tạo VARRAY

~~~sql
DECLARE
    TYPE t_phone_numbers IS VARRAY(5) OF VARCHAR2(20);
    l_phones t_phone_numbers :=
        t_phone_numbers('0900000001', '0900000002');
BEGIN
    DBMS_OUTPUT.PUT_LINE('COUNT=' || l_phones.COUNT);
    DBMS_OUTPUT.PUT_LINE('LIMIT=' || l_phones.LIMIT);
    DBMS_OUTPUT.PUT_LINE('FIRST=' || l_phones.FIRST);
    DBMS_OUTPUT.PUT_LINE('LAST=' || l_phones.LAST);
END;
/
~~~

VARRAY có tối đa 5 phần tử. Trong ví dụ, COUNT=2 và LIMIT=5.

### 4.2. Thêm phần tử vào VARRAY

~~~sql
DECLARE
    TYPE t_tags IS VARRAY(3) OF VARCHAR2(20);
    l_tags t_tags := t_tags('NEW');
BEGIN
    l_tags.EXTEND;
    l_tags(2) := 'PAID';

    l_tags.EXTEND;
    l_tags(3) := 'SHIPPED';

    DBMS_OUTPUT.PUT_LINE(l_tags.COUNT);
END;
/
~~~

Nếu gọi EXTEND vượt quá LIMIT, Oracle báo lỗi vượt giới hạn VARRAY, thường là ORA-06532 (Subscript outside of limit).

### 4.3. VARRAY luôn dense

Không thể xóa riêng phần tử ở giữa VARRAY bằng DELETE(index). VARRAY không hỗ trợ DELETE method; có thể loại phần tử cuối bằng TRIM hoặc thay thế giá trị phần tử.

Ví dụ:

~~~sql
l_tags.TRIM; -- Bỏ phần tử cuối
~~~

Sau TRIM, COUNT giảm một và các chỉ số còn lại vẫn liên tục từ 1.

### 4.4. VARRAY giữ thứ tự

Nếu danh sách nhỏ có thứ tự nghiệp vụ rõ ràng, chẳng hạn các bước trong một quy trình hoặc một số số điện thoại ưu tiên, VARRAY có thể là lựa chọn phù hợp. Khi VARRAY được lưu trong database, thứ tự phần tử là một phần của semantics của collection; tuy nhiên khi truy vấn qua TABLE(varray_column), hãy dùng cơ chế sắp xếp/ordinal thích hợp nếu cần hợp đồng thứ tự output rõ ràng cho ứng dụng.

### 4.5. LIMIT chỉ có ý nghĩa với VARRAY

LIMIT trả số phần tử tối đa của VARRAY. Với nested table và associative array, LIMIT trả NULL.

~~~sql
DECLARE
    TYPE t_small_list IS VARRAY(10) OF NUMBER;
    l_values t_small_list := t_small_list(1, 2, 3);
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_values.LIMIT); -- 10
END;
/
~~~

## 5. So sánh ba loại collection

| Đặc điểm | Associative array | Nested table | VARRAY |
| --- | --- | --- | --- |
| Chỉ số | PLS_INTEGER hoặc key chuỗi | Số nguyên | Số nguyên |
| Constructor | Không | Có | Có |
| Kích thước tối đa khai báo | Không có giới hạn type cố định | Không khai báo giới hạn tối đa | Có LIMIT |
| Sparse | Có | Có thể sparse sau DELETE | Không, luôn dense |
| Giữ thứ tự phần tử | Duyệt theo thứ tự key, không phải thứ tự INSERT | Không nên dựa vào thứ tự khi lưu/query SQL | Có thứ tự phần tử |
| EXTEND | Không | Có | Có |
| TRIM | Không | Có | Có |
| DELETE(index) | Có | Có | Không |
| DELETE toàn bộ | Có | Có | Không có DELETE method |
| LIMIT | NULL | NULL | Số tối đa |
| Dùng trong PL/SQL | Có | Có | Có |
| Lưu trực tiếp làm cột SQL | Không | Có với SQL type | Có với SQL type |
| Mẫu sử dụng | Map/cache/lookup trong bộ nhớ | Danh sách thay đổi, nested collection trong SQL | Danh sách nhỏ có giới hạn |

### 5.1. Chọn loại theo yêu cầu

- Dùng associative array khi cần ánh xạ key-value, tra cứu theo mã và không cần lưu collection như một cột SQL.
- Dùng nested table khi số phần tử biến đổi, cần dùng collection trong SQL hoặc lưu tập phần tử có thể mở rộng.
- Dùng VARRAY khi số phần tử có giới hạn rõ ràng và thứ tự phần tử có ý nghĩa.

Không chọn collection chỉ theo tên. Hãy xác định:
- Cần key tùy ý hay chỉ số 1..N?
- Có cần xóa phần tử ở giữa không?
- Có cần giữ thứ tự không?
- Có cần lưu collection trong bảng SQL không?
- Kích thước tối đa có biết trước không?
- Có cần BULK COLLECT/FORALL và các chỉ số có liên tục không?

## 6. Collection methods

Oracle cung cấp các collection methods để truy vấn trạng thái và thao tác phần tử. Các phương thức không áp dụng đồng đều cho mọi collection.

| Method | Ý nghĩa | Associative array | Nested table | VARRAY |
| --- | --- | --- | --- | --- |
| COUNT | Số phần tử hiện có | Có | Có | Có |
| FIRST | Chỉ số đầu tiên | Có | Có | Có |
| LAST | Chỉ số cuối cùng | Có | Có | Có |
| PRIOR(n) | Chỉ số trước n | Có | Có | Có |
| NEXT(n) | Chỉ số sau n | Có | Có | Có |
| EXISTS(n) | Kiểm tra phần tử | Có | Có | Có |
| DELETE | Xóa phần tử/phạm vi | Có | Có | Không |
| EXTEND | Thêm phần tử cuối | Không | Có | Có |
| TRIM | Bỏ phần tử cuối | Không | Có | Có |
| LIMIT | Giới hạn tối đa | NULL | NULL | Có |

### 6.1. COUNT

COUNT trả số phần tử hiện có. Với collection sparse, COUNT không nhất thiết bằng LAST.

### 6.2. FIRST và LAST

FIRST và LAST trả chỉ số đầu/cuối đang tồn tại; với collection rỗng, kết quả là NULL.

### 6.3. NEXT và PRIOR

NEXT(index_value) và PRIOR(index_value) trả chỉ số kế tiếp hoặc trước đó đang tồn tại. Chúng đặc biệt hữu ích khi collection sparse hoặc associative array dùng key không liên tục.

### 6.4. EXISTS

~~~sql
IF l_collection.EXISTS(i) THEN
    -- Doc phan tu an toan.
END IF;
~~~

EXISTS trả TRUE nếu phần tử tại chỉ số/key đó tồn tại. Dùng EXISTS trước khi đọc một chỉ số có thể chưa được gán để tránh lỗi truy cập phần tử không tồn tại.

### 6.5. DELETE

~~~sql
l_collection.DELETE;
l_collection.DELETE(i);
l_collection.DELETE(m, n);
~~~

DELETE không tham số xóa tất cả phần tử; DELETE(i) xóa một phần tử; DELETE(m,n) xóa một dải chỉ số trong những loại collection hỗ trợ. Associative array và nested table hỗ trợ DELETE; VARRAY không.

### 6.6. EXTEND

~~~sql
l_collection.EXTEND;
l_collection.EXTEND(n);
l_collection.EXTEND(n, i);
~~~

EXTEND thêm phần tử cho nested table/VARRAY. Dạng EXTEND(n,i) tạo bản sao phần tử ở chỉ số i; nếu phần tử nguồn không tồn tại, thao tác lỗi.

### 6.7. TRIM

~~~sql
l_collection.TRIM;
l_collection.TRIM(n);
~~~

TRIM bỏ một hoặc nhiều phần tử cuối của nested table/VARRAY. Nó không áp dụng cho associative array.

## 7. Duyệt collection an toàn

Một lỗi phổ biến là giả định mọi collection có chỉ số liên tục từ 1 đến COUNT.

Ví dụ không an toàn với collection sparse:

~~~sql
FOR i IN 1 .. l_names.COUNT LOOP
    DBMS_OUTPUT.PUT_LINE(l_names(i));
END LOOP;
~~~

Nếu chỉ số 2 đã bị DELETE và collection còn chỉ số 1,3, vòng lặp vẫn truy cập 2 và có thể gây lỗi.

Duyệt bằng FIRST/NEXT:

~~~sql
DECLARE
    TYPE t_names IS TABLE OF VARCHAR2(100);
    l_names t_names := t_names('An', 'Binh', 'Chi');
    i PLS_INTEGER;
BEGIN
    l_names.DELETE(2);

    i := l_names.FIRST;

    WHILE i IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Index=' || i || ', Value=' || l_names(i)
        );
        i := l_names.NEXT(i);
    END LOOP;
END;
/
~~~

Cách này hoạt động với associative array, nested table sparse và VARRAY.

### 7.1. Duyệt ngược bằng PRIOR

~~~sql
i := l_names.LAST;

WHILE i IS NOT NULL LOOP
    DBMS_OUTPUT.PUT_LINE(l_names(i));
    i := l_names.PRIOR(i);
END LOOP;
~~~

Duyệt ngược hữu ích khi cần xử lý từ phần tử cuối về đầu. Nó không có nghĩa collection đã được sắp xếp theo nghiệp vụ; thứ tự phụ thuộc chỉ số/key.

### 7.2. Duyệt associative array có key chuỗi

~~~sql
DECLARE
    TYPE t_country_map IS TABLE OF VARCHAR2(100)
        INDEX BY VARCHAR2(10);
    l_countries t_country_map;
    l_code VARCHAR2(10);
BEGIN
    l_countries('VN') := 'Viet Nam';
    l_countries('JP') := 'Japan';
    l_countries('SG') := 'Singapore';

    l_code := l_countries.FIRST;

    WHILE l_code IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(
            l_code || ': ' || l_countries(l_code)
        );
        l_code := l_countries.NEXT(l_code);
    END LOOP;
END;
/
~~~

Thứ tự duyệt là thứ tự key theo quy tắc so sánh của session, không phải thứ tự các lệnh gán.

## 8. Collection of records

Collection có thể chứa record thay vì chỉ một scalar value. Điều này hữu ích khi cần gom nhiều thuộc tính của một hàng vào cùng phần tử.

~~~sql
DECLARE
    TYPE t_employee_record IS RECORD (
        employee_id NUMBER,
        full_name   VARCHAR2(100),
        salary      NUMBER
    );

    TYPE t_employee_list IS TABLE OF t_employee_record
        INDEX BY PLS_INTEGER;

    l_employees t_employee_list;
BEGIN
    l_employees(1).employee_id := 101;
    l_employees(1).full_name := 'An';
    l_employees(1).salary := 20000000;

    l_employees(2).employee_id := 102;
    l_employees(2).full_name := 'Binh';
    l_employees(2).salary := 25000000;

    DBMS_OUTPUT.PUT_LINE(l_employees(2).full_name);
END;
/
~~~

Collection of records giúp giữ các cột liên quan trong một phần tử. Nếu dùng BULK COLLECT, có thể nạp record collection từ cursor hoặc dùng nhiều collection song song. Hãy chọn cấu trúc dễ bảo trì và tránh các collection song song có thể lệch chỉ số.

## 9. BULK COLLECT: nạp nhiều hàng vào collection

Thông thường, PL/SQL có thể lấy từng hàng bằng FETCH hoặc SELECT INTO. Khi xử lý nhiều hàng, BULK COLLECT nạp nhiều hàng trong một lần chuyển dữ liệu giữa SQL engine và PL/SQL engine.

Ví dụ:

~~~sql
DECLARE
    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    TYPE t_salaries IS TABLE OF employees.salary%TYPE;

    l_employee_ids t_employee_ids;
    l_salaries     t_salaries;
BEGIN
    SELECT employee_id, salary
    BULK COLLECT INTO l_employee_ids, l_salaries
    FROM employees
    WHERE department_id = 10;

    FOR i IN 1 .. l_employee_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(
            l_employee_ids(i) || ': ' || l_salaries(i)
        );
    END LOOP;
END;
/
~~~

Các collection trong INTO được nạp theo vị trí tương ứng: phần tử thứ i của L_EMPLOYEE_IDS đi cùng phần tử thứ i của L_SALARIES.

### 9.1. BULK COLLECT với cursor

Với tập dữ liệu lớn, không nên mặc định nạp tất cả hàng vào bộ nhớ. Có thể fetch theo batch bằng LIMIT:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, salary
        FROM employees
        ORDER BY employee_id;

    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    TYPE t_salaries IS TABLE OF employees.salary%TYPE;

    l_ids      t_employee_ids;
    l_salaries t_salaries;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees
        BULK COLLECT INTO l_ids, l_salaries
        LIMIT 500;

        EXIT WHEN l_ids.COUNT = 0;

        FOR i IN 1 .. l_ids.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                l_ids(i) || ': ' || l_salaries(i)
            );
        END LOOP;
    END LOOP;

    CLOSE c_employees;
EXCEPTION
    WHEN OTHERS THEN
        IF c_employees%ISOPEN THEN
            CLOSE c_employees;
        END IF;
        RAISE;
END;
/
~~~

LIMIT 500 giới hạn số hàng được nạp mỗi batch. Giá trị LIMIT nên được lựa chọn theo kích thước hàng, bộ nhớ và workload; không có con số tối ưu cho mọi ứng dụng.

### 9.2. Vì sao cần LIMIT?

Nếu SELECT BULK COLLECT nạp hàng triệu bản ghi vào một collection, session có thể tiêu thụ nhiều PGA memory và gặp lỗi bộ nhớ. Fetch theo batch giúp giới hạn lượng dữ liệu đang nằm trong PL/SQL memory.

Mỗi lần FETCH BULK COLLECT trong vòng lặp thay thế nội dung collection với batch vừa fetch; xử lý xong batch hiện tại rồi mới fetch batch tiếp theo.

### 9.3. SELECT BULK COLLECT INTO khi không có hàng

Khác với SELECT INTO thông thường, SELECT BULK COLLECT INTO không ném NO_DATA_FOUND chỉ vì không có hàng. Collection đích trở thành collection rỗng và COUNT = 0.

~~~sql
SELECT employee_id
BULK COLLECT INTO l_ids
FROM employees
WHERE department_id = -1;

IF l_ids.COUNT = 0 THEN
    DBMS_OUTPUT.PUT_LINE('Khong co nhan vien');
END IF;
~~~

## 10. FORALL: thực hiện nhiều DML bằng bulk binding

FORALL là câu lệnh PL/SQL dùng để gửi một loạt DML tới SQL engine với collection làm nguồn bind. Nó giảm số lần chuyển qua lại giữa PL/SQL và SQL engine so với vòng lặp DML thông thường.

Ví dụ vòng lặp thông thường:

~~~sql
FOR i IN 1 .. l_employee_ids.COUNT LOOP
    UPDATE employees
    SET salary = salary + 100000
    WHERE employee_id = l_employee_ids(i);
END LOOP;
~~~

FORALL:

~~~sql
FORALL i IN 1 .. l_employee_ids.COUNT
    UPDATE employees
    SET salary = salary + 100000
    WHERE employee_id = l_employee_ids(i);
~~~

FORALL không phải vòng lặp PL/SQL thông thường; nó là bulk SQL statement. DML vẫn được thực hiện theo từng phần tử bind nhưng giảm overhead chuyển engine.

### 10.1. Ví dụ đầy đủ

~~~sql
DECLARE
    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_employee_ids;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_ids
    FROM employees
    WHERE department_id = 10;

    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employees
        SET salary = salary * 1.05
        WHERE employee_id = l_ids(i);

    DBMS_OUTPUT.PUT_LINE(
        'So hang cap nhat: ' || SQL%ROWCOUNT
    );

    COMMIT;
END;
/
~~~

Trong ví dụ, SELECT BULK COLLECT lấy danh sách ID, FORALL cập nhật các hàng theo ID. SQL%ROWCOUNT sau FORALL phản ánh tổng số hàng bị ảnh hưởng bởi DML bulk gần nhất.

### 10.2. FORALL yêu cầu collection index phù hợp

Mẫu FORALL i IN 1..collection.COUNT giả định các chỉ số tồn tại liên tục từ 1 đến COUNT. Nếu collection sparse hoặc dùng key PLS_INTEGER không liên tục, dùng INDICES OF hoặc VALUES OF phù hợp.

### 10.3. INDICES OF cho collection sparse

~~~sql
DECLARE
    TYPE t_id_map IS TABLE OF employees.employee_id%TYPE
        INDEX BY PLS_INTEGER;

    l_ids t_id_map;
BEGIN
    l_ids(2) := 101;
    l_ids(10) := 102;
    l_ids(50) := 103;

    FORALL i IN INDICES OF l_ids
        UPDATE employees
        SET salary = salary + 50000
        WHERE employee_id = l_ids(i);

    COMMIT;
END;
/
~~~

INDICES OF duyệt các chỉ số thực sự tồn tại trong collection, tránh giả định dãy liên tục.

### 10.4. VALUES OF dùng collection chỉ số

VALUES OF cho phép một collection chỉ ra những chỉ số cần dùng từ collection nguồn:

~~~sql
DECLARE
    TYPE t_id_list IS TABLE OF employees.employee_id%TYPE
        INDEX BY PLS_INTEGER;
    TYPE t_index_list IS TABLE OF PLS_INTEGER
        INDEX BY PLS_INTEGER;

    l_ids     t_id_list;
    l_indexes t_index_list;
BEGIN
    l_ids(10) := 101;
    l_ids(20) := 102;
    l_ids(30) := 103;

    l_indexes(1) := 10;
    l_indexes(2) := 30;

    FORALL i IN VALUES OF l_indexes
        UPDATE employees
        SET salary = salary + 100000
        WHERE employee_id = l_ids(i);

    COMMIT;
END;
/
~~~

Trong ví dụ, chỉ các phần tử L_IDS tại key 10 và 30 được dùng. Collection chứa index values phải có kiểu phù hợp và các giá trị tham chiếu phải tồn tại.

## 11. SAVE EXCEPTIONS trong FORALL

Mặc định, nếu một iteration trong FORALL gặp lỗi, Oracle dừng bulk operation và báo lỗi. Khi muốn tiếp tục xử lý các phần tử khác rồi tổng hợp lỗi, dùng SAVE EXCEPTIONS.

~~~sql
DECLARE
    TYPE t_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_ids := t_ids(101, 102, -1, 103);

    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
        UPDATE employees
        SET salary = salary + 100000
        WHERE employee_id = l_ids(i);

    DBMS_OUTPUT.PUT_LINE('Tong hang: ' || SQL%ROWCOUNT);
EXCEPTION
    WHEN e_bulk_errors THEN
        DBMS_OUTPUT.PUT_LINE(
            'So loi: ' || SQL%BULK_EXCEPTIONS.COUNT
        );

        FOR j IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Iteration=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_INDEX ||
                ', Error=' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_CODE
            );
        END LOOP;

        RAISE;
END;
/
~~~

Khi có lỗi, Oracle hoàn tất các iteration có thể thực hiện và lưu thông tin lỗi trong SQL%BULK_EXCEPTIONS. Sau đó exception ORA-24381 được ném để chương trình xử lý.

Trong ví dụ, RAISE ném lại lỗi sau khi in thông tin. Nếu bỏ RAISE và tiếp tục, phải quyết định rõ các thay đổi thành công có được COMMIT hay ROLLBACK. SAVE EXCEPTIONS không tự động rollback toàn bộ batch.

### 11.1. SQL%BULK_EXCEPTIONS

Mỗi phần tử trong SQL%BULK_EXCEPTIONS có:
- ERROR_INDEX: chỉ số iteration của FORALL gây lỗi.
- ERROR_CODE: mã lỗi Oracle không kèm dấu âm theo cách được lưu trong thuộc tính.

Có thể lấy thông điệp bằng SQLERRM với mã âm tương ứng:

~~~sql
SQLERRM(-SQL%BULK_EXCEPTIONS(j).ERROR_CODE)
~~~

Cần đối chiếu ERROR_INDEX với collection index và dạng FORALL đang dùng; với INDICES OF/VALUES OF, đừng nhầm iteration ordinal với key gốc.

### 11.2. SQL%BULK_ROWCOUNT

SQL%BULK_ROWCOUNT(i) cho biết số hàng bị ảnh hưởng bởi iteration i của FORALL. Ví dụ UPDATE theo primary key thường là 0 hoặc 1.

~~~sql
FOR i IN 1 .. l_ids.COUNT LOOP
    DBMS_OUTPUT.PUT_LINE(
        'Iteration ' || i ||
        ' affected ' || SQL%BULK_ROWCOUNT(i)
    );
END LOOP;
~~~

Thuộc tính này hữu ích khi cần biết ID nào không tìm thấy hàng hoặc một DML tác động nhiều hàng hơn dự kiến.

## 12. Collection trong SQL: kiểu PL/SQL và kiểu schema

Không phải mọi collection PL/SQL đều có thể dùng ở mọi vị trí SQL. Cần phân biệt:
- Collection type khai báo trong PL/SQL block/package.
- Collection type khai báo ở cấp schema bằng CREATE TYPE.

Nếu muốn collection trở thành kiểu SQL có thể dùng trong DDL, cột bảng hoặc TABLE(collection_expression), khai báo SQL collection type ở cấp schema.

### 12.1. Tạo nested table type ở cấp schema

~~~sql
CREATE TYPE number_list_t AS TABLE OF NUMBER;
/
~~~

Sau đó có thể dùng type trong SQL:

~~~sql
SELECT column_value
FROM TABLE(number_list_t(10, 20, 30));
~~~

COLUMN_VALUE là tên cột mặc định khi TABLE() mở rộng collection scalar.

### 12.2. Dùng collection type trong bảng

~~~sql
CREATE TABLE project_demo (
    project_id NUMBER PRIMARY KEY,
    project_codes number_list_t
)
NESTED TABLE project_codes STORE AS project_codes_nt;
~~~

PROJECT_CODES là cột nested table. Oracle lưu các phần tử trong nested table storage table được chỉ định.

Chèn collection:

~~~sql
INSERT INTO project_demo(project_id, project_codes)
VALUES (1, number_list_t(100, 200, 300));

COMMIT;
~~~

Đọc các phần tử:

~~~sql
SELECT p.project_id,
       x.COLUMN_VALUE AS project_code
FROM project_demo p,
     TABLE(p.project_codes) x
ORDER BY p.project_id, x.COLUMN_VALUE;
~~~

ORDER BY ở đây sắp xếp theo giá trị; không giả định thứ tự lưu vật lý của nested table.

### 12.3. Dùng VARRAY type ở cấp schema

~~~sql
CREATE TYPE phone_list_t AS VARRAY(5) OF VARCHAR2(20);
/
~~~

Tạo bảng:

~~~sql
CREATE TABLE customer_phone_demo (
    customer_id NUMBER PRIMARY KEY,
    phone_numbers phone_list_t
);
~~~

Chèn:

~~~sql
INSERT INTO customer_phone_demo
VALUES (
    1,
    phone_list_t('0900000001', '0900000002')
);

COMMIT;
~~~

VARRAY phù hợp với danh sách số điện thoại có giới hạn tối đa 5 trong ví dụ này.

### 12.4. Associative array không phải kiểu cột SQL

Associative array là cấu trúc PL/SQL trong bộ nhớ; không khai báo trực tiếp nó làm cột bảng SQL như nested table hoặc VARRAY SQL type. Nếu cần lưu một danh sách lâu dài trong database, cân nhắc nested table, VARRAY hoặc mô hình quan hệ thông thường với bảng con.

Nếu chỉ cần truyền một danh sách ID trong PL/SQL hoặc bind vào bulk DML, associative array có thể rất phù hợp.

### 12.5. SQL interoperability phụ thuộc cách khai báo type

Một collection type local trong block không có cùng phạm vi và khả năng tương tác SQL như SQL schema type. Trong các phiên bản Oracle hiện đại có hỗ trợ một số PL/SQL types trong SQL, nhưng vẫn có giới hạn về kiểu, vị trí sử dụng và ngữ cảnh. Khi cần kiểu dữ liệu dùng ổn định trong DDL, SQL query, view hoặc nhiều ứng dụng, schema-level SQL type là lựa chọn rõ ràng và tương thích hơn.

## 13. Collection và tham số procedure/function

Collection có thể là tham số IN, OUT hoặc IN OUT của procedure/function.

Ví dụ package type:

~~~sql
CREATE OR REPLACE PACKAGE employee_api AS
    TYPE t_employee_ids IS TABLE OF PLS_INTEGER
        INDEX BY PLS_INTEGER;

    PROCEDURE list_ids(
        p_ids OUT t_employee_ids
    );
END employee_api;
/
~~~

Package body:

~~~sql
CREATE OR REPLACE PACKAGE BODY employee_api AS
    PROCEDURE list_ids(
        p_ids OUT t_employee_ids
    ) IS
    BEGIN
        p_ids(1) := 101;
        p_ids(2) := 102;
        p_ids(3) := 103;
    END list_ids;
END employee_api;
/
~~~

Gọi:

~~~sql
DECLARE
    l_ids employee_api.t_employee_ids;
    i PLS_INTEGER;
BEGIN
    employee_api.list_ids(l_ids);

    i := l_ids.FIRST;
    WHILE i IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(l_ids(i));
        i := l_ids.NEXT(i);
    END LOOP;
END;
/
~~~

Khai báo type trong package specification giúp caller nhìn thấy kiểu và dùng nó để khai báo biến nhận kết quả.

### 13.1. Chọn package type hay schema SQL type

- Package PL/SQL type phù hợp với API nội bộ PL/SQL.
- Schema SQL type phù hợp khi type cần dùng trong SQL, cột bảng, TABLE() hoặc giao tiếp giữa nhiều schema/ứng dụng theo quyền được cấp.
- Associative array phù hợp với lookup/bulk processing trong PL/SQL.
- Nested table/VARRAY SQL type phù hợp với dữ liệu collection được SQL xử lý hoặc lưu trữ.

## 14. Collection và hiệu năng: BULK COLLECT/FORALL

PL/SQL và SQL engine là hai môi trường thực thi có ranh giới chuyển đổi. Nếu code lặp từng hàng rồi gọi một câu SQL cho mỗi hàng, chi phí chuyển đổi có thể lớn.

Ví dụ row-by-row:

~~~sql
FOR r IN (
    SELECT employee_id
    FROM employees
    WHERE department_id = 10
) LOOP
    UPDATE employees
    SET salary = salary * 1.05
    WHERE employee_id = r.employee_id;
END LOOP;
~~~

Bulk processing:

~~~sql
DECLARE
    TYPE t_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_ids;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_ids
    FROM employees
    WHERE department_id = 10;

    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employees
        SET salary = salary * 1.05
        WHERE employee_id = l_ids(i);

    COMMIT;
END;
/
~~~

BULK COLLECT giảm số lần lấy dữ liệu từ SQL sang PL/SQL; FORALL giảm số lần gửi DML từ PL/SQL sang SQL. Hai cơ chế thường đi cùng nhau.

### 14.1. Bulk không phải lúc nào cũng nhanh hơn

Với một câu UPDATE có thể biểu diễn bằng SQL set-based, hãy ưu tiên một câu SQL đơn:

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 10;
~~~

Câu SQL set-based thường đơn giản và hiệu quả hơn việc SELECT ID rồi FORALL UPDATE lại cùng tập hàng.

Dùng BULK COLLECT/FORALL khi logic xử lý cần PL/SQL hoặc phải thực hiện các DML dựa trên từng phần tử collection. Không chuyển mọi câu SQL đơn giản thành bulk code.

### 14.2. Batch size và PGA

BULK COLLECT không LIMIT có thể nạp quá nhiều dữ liệu vào PGA. Dùng LIMIT để kiểm soát batch size. Giá trị phù hợp phụ thuộc:
- Kích thước record.
- Số cột.
- Bộ nhớ session.
- Tốc độ xử lý từng batch.
- Mức độ cạnh tranh tài nguyên.

Hãy đo với dữ liệu đại diện.

### 14.3. Transaction boundary vẫn do COMMIT/ROLLBACK quyết định

FORALL không tự COMMIT. BULK COLLECT cũng không tự kết thúc transaction. Các thay đổi DML vẫn thuộc transaction hiện tại; caller quyết định COMMIT hoặc ROLLBACK.

## 15. Lỗi thường gặp với collection

| Lỗi/tình huống | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| ORA-06531 | Truy cập collection atomically null | Khởi tạo nested table/VARRAY bằng constructor |
| ORA-06532 | Vượt LIMIT của VARRAY | Kiểm tra LIMIT trước EXTEND |
| ORA-06533 | Truy cập vượt số phần tử hợp lệ của collection | Kiểm tra COUNT/EXISTS và chỉ số |
| NO_DATA_FOUND khi đọc phần tử | Chỉ số/key không tồn tại hoặc đã DELETE | Dùng EXISTS, FIRST/NEXT |
| FOR loop truy cập phần tử đã xóa | Giả định collection dense | Duyệt bằng FIRST/NEXT hoặc FORALL INDICES OF |
| Gọi EXTEND trên associative array | Associative array không hỗ trợ EXTEND | Gán trực tiếp vào key |
| Gọi DELETE(index) trên VARRAY | VARRAY không hỗ trợ xóa riêng phần tử | Dùng TRIM cho phần tử cuối hoặc tạo collection mới |
| COUNT bị nhầm với LAST | Collection sparse | Phân biệt số phần tử và chỉ số cuối |
| BULK COLLECT tiêu thụ nhiều PGA | Nạp toàn bộ tập dữ liệu quá lớn | FETCH BULK COLLECT LIMIT |
| FORALL lỗi dừng cả batch | Không dùng SAVE EXCEPTIONS | Dùng SAVE EXCEPTIONS nếu cần thu thập lỗi từng iteration |
| SQL không nhận kiểu collection local | Type không ở phạm vi SQL phù hợp | Khai báo schema-level SQL collection type khi cần |
| Thứ tự nested table query thay đổi | Dựa vào thứ tự lưu vật lý | ORDER BY theo khóa/ordinal rõ ràng |

## 16. Ví dụ thực hành tổng hợp

Ví dụ này tạo một danh sách mã nhân viên trong associative array, nạp hàng loạt từ bảng, sau đó cập nhật bằng FORALL. Chạy trong schema sandbox.

### 16.1. Khai báo và dùng associative array

~~~sql
DECLARE
    TYPE t_salary_map IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    l_salary t_salary_map;
    k PLS_INTEGER;
BEGIN
    l_salary(101) := 20000000;
    l_salary(105) := 25000000;
    l_salary(205) := 18000000;

    k := l_salary.FIRST;
    WHILE k IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(k || ' => ' || l_salary(k));
        k := l_salary.NEXT(k);
    END LOOP;
END;
/
~~~

### 16.2. Nested table với phần tử thưa

~~~sql
DECLARE
    TYPE t_names IS TABLE OF VARCHAR2(50);
    l_names t_names := t_names('An', 'Binh', 'Chi', 'Dung');
    i PLS_INTEGER;
BEGIN
    l_names.DELETE(2);

    i := l_names.FIRST;
    WHILE i IS NOT NULL LOOP
        DBMS_OUTPUT.PUT_LINE(i || ': ' || l_names(i));
        i := l_names.NEXT(i);
    END LOOP;
END;
/
~~~

Kết quả hiển thị chỉ số 1, 3, 4. COUNT=3 nhưng LAST=4.

### 16.3. VARRAY có giới hạn

~~~sql
DECLARE
    TYPE t_steps IS VARRAY(4) OF VARCHAR2(30);
    l_steps t_steps := t_steps('CREATED', 'PAID');
BEGIN
    l_steps.EXTEND;
    l_steps(3) := 'PACKED';

    DBMS_OUTPUT.PUT_LINE('COUNT=' || l_steps.COUNT);
    DBMS_OUTPUT.PUT_LINE('LIMIT=' || l_steps.LIMIT);

    l_steps.TRIM;
    DBMS_OUTPUT.PUT_LINE('COUNT after TRIM=' || l_steps.COUNT);
END;
/
~~~

VARRAY giữ các bước theo thứ tự và không cho vượt quá bốn phần tử.

### 16.4. BULK COLLECT theo batch và FORALL

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id
        FROM employees
        WHERE department_id = 10
        ORDER BY employee_id;

    TYPE t_ids IS TABLE OF employees.employee_id%TYPE;
    l_ids t_ids;
BEGIN
    OPEN c_employee;

    LOOP
        FETCH c_employee BULK COLLECT INTO l_ids LIMIT 200;
        EXIT WHEN l_ids.COUNT = 0;

        FORALL i IN 1 .. l_ids.COUNT
            UPDATE employees
            SET salary = salary + 100000
            WHERE employee_id = l_ids(i);
    END LOOP;

    CLOSE c_employee;
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        IF c_employee%ISOPEN THEN
            CLOSE c_employee;
        END IF;
        ROLLBACK;
        RAISE;
END;
/
~~~

Ví dụ xử lý theo batch 200 nhân viên. Mọi DML trong các batch vẫn thuộc transaction hiện tại cho tới COMMIT cuối. Nếu một lỗi làm exception thoát khỏi block, ROLLBACK hủy toàn bộ các cập nhật chưa COMMIT.

## 17. Quy trình chọn collection type

Trước khi khai báo collection, hãy xác định:

1. Phần tử được truy cập bằng số thứ tự hay một khóa nghiệp vụ?
2. Key có cần là chuỗi không?
3. Collection có cần lưu trực tiếp trong bảng SQL không?
4. Kích thước tối đa có giới hạn cố định không?
5. Có cần xóa phần tử ở giữa không?
6. Có cần giữ thứ tự phần tử như một phần của dữ liệu không?
7. Có thể có khoảng trống trong chỉ số không?
8. Có cần dùng collection trong TABLE(), SQL expression hoặc schema DDL không?
9. Có cần BULK COLLECT/FORALL không?
10. Dữ liệu có đủ lớn để cần fetch theo batch không?

Gợi ý:

| Nhu cầu | Collection phù hợp |
| --- | --- |
| Map employee_id -> salary | Associative array |
| Key là mã chuỗi, tra cứu trong PL/SQL | Associative array |
| Danh sách thay đổi kích thước, dùng trong SQL | Nested table |
| Collection lưu trong cột bảng và có thể có nhiều phần tử | Nested table hoặc VARRAY tùy semantics |
| Danh sách nhỏ có giới hạn và giữ thứ tự | VARRAY |
| Xóa phần tử bất kỳ và chấp nhận sparse index | Associative array hoặc nested table |
| Bulk bind theo PLS_INTEGER indexes | Associative array phù hợp, nested table hoặc VARRAY |
| Cần SQL type dùng trong nhiều schema | Schema-level nested table/VARRAY type |

## 18. Những nhầm lẫn thường gặp

**Associative array, nested table và VARRAY giống nhau, chỉ khác tên.** Không đúng. Chúng khác cách đánh chỉ số, sparse/dense, giới hạn kích thước, lưu trữ SQL và collection methods.

**Associative array bắt đầu từ chỉ số 1.** Không đúng. Key do chương trình chọn, có thể là số nguyên không liên tục hoặc chuỗi.

**COUNT luôn bằng LAST.** Không đúng với collection sparse. COUNT là số phần tử, LAST là chỉ số/key cuối đang tồn tại.

**Nested table luôn dense.** Không đúng. DELETE(index) có thể tạo khoảng trống.

**VARRAY có thể DELETE phần tử ở giữa.** Không đúng. VARRAY không hỗ trợ DELETE method; dùng TRIM để bỏ từ cuối hoặc tạo collection mới.

**Associative array cần constructor trước khi gán.** Không đúng. Biến associative array có thể sử dụng sau khi khai báo.

**Nested table khai báo nhưng chưa khởi tạo có COUNT=0.** Không đúng. Nó có thể atomically null; cần constructor rỗng để khởi tạo.

**EXTEND dùng được cho mọi collection.** Không đúng. EXTEND chỉ áp dụng nested table và VARRAY.

**LIMIT dùng được cho mọi collection.** Không đúng. LIMIT chỉ có giá trị tối đa với VARRAY; các loại còn lại trả NULL.

**Thứ tự INSERT của associative array là thứ tự FIRST/NEXT.** Không đúng. Associative array được duyệt theo key order.

**Nested table query luôn trả đúng thứ tự phần tử ban đầu.** Không đúng. Dùng ORDER BY nếu cần thứ tự output xác định.

**BULK COLLECT tự động giới hạn bộ nhớ.** Không đúng. Cần LIMIT khi fetch tập lớn.

**FORALL là vòng lặp FOR thông thường.** Không đúng. FORALL là bulk DML statement để giảm context switching.

**FORALL tự COMMIT.** Không đúng. Transaction boundary vẫn do COMMIT/ROLLBACK của chương trình quản lý.

**SAVE EXCEPTIONS tự rollback mọi iteration thành công.** Không đúng. Nó thu thập lỗi iteration; chương trình quyết định COMMIT/ROLLBACK.

**Mọi PL/SQL collection đều có thể làm cột bảng SQL.** Không đúng. Associative array không phải kiểu cột SQL; dùng SQL nested table/VARRAY type khi cần lưu collection.

**Nếu một câu UPDATE có thể viết set-based thì luôn nên dùng FORALL.** Không đúng. Một câu SQL set-based thường đơn giản và hiệu quả hơn; FORALL hữu ích khi logic thực sự cần xử lý collection ở PL/SQL.

## 19. Bài tập tự luyện

1. Khai báo associative array ánh xạ EMPLOYEE_ID sang SALARY và thêm ba phần tử.
2. Dùng associative array với key VARCHAR2 để ánh xạ mã quốc gia sang tên quốc gia.
3. Vì sao associative array không cần constructor?
4. Viết vòng lặp FIRST/NEXT để duyệt associative array có key 10, 50, 100.
5. Khai báo nested table và khởi tạo rỗng bằng constructor.
6. Giải thích khác biệt giữa atomically null collection và empty collection.
7. Thêm năm phần tử vào nested table bằng EXTEND.
8. Xóa phần tử thứ hai và giải thích COUNT khác LAST thế nào.
9. Duyệt nested table sparse mà không gặp lỗi chỉ số.
10. Giải thích EXTEND(n,i) hoạt động ra sao.
11. Vì sao phải cẩn thận khi kết hợp DELETE và TRIM?
12. Khai báo VARRAY tối đa năm phần tử và thêm ba giá trị.
13. Thử EXTEND vượt LIMIT và giải thích lỗi.
14. Vì sao VARRAY luôn dense?
15. So sánh DELETE và TRIM trên nested table.
16. Liệt kê collection methods được hỗ trợ cho từng loại.
17. Dùng PRIOR để duyệt collection từ cuối về đầu.
18. Khai báo collection of records chứa EMPLOYEE_ID, FULL_NAME và SALARY.
19. Dùng SELECT BULK COLLECT INTO để lấy ID và lương của phòng ban 10.
20. Viết FETCH BULK COLLECT LIMIT 100 và xử lý từng batch.
21. Vì sao BULK COLLECT không LIMIT có thể gây áp lực PGA?
22. Dùng FORALL cập nhật lương theo danh sách employee ID.
23. Khi collection sparse, vì sao 1..COUNT không an toàn?
24. Viết lại FORALL bằng INDICES OF.
25. Giải thích VALUES OF và tạo collection chỉ số chọn lọc.
26. Dùng SAVE EXCEPTIONS và in ERROR_INDEX/ERROR_CODE.
27. Phân biệt SQL%BULK_EXCEPTIONS và SQL%BULK_ROWCOUNT.
28. Tạo SQL-level nested table type và truy vấn bằng TABLE().
29. Tạo VARRAY type ở schema level và dùng làm cột bảng.
30. Vì sao associative array không thể khai báo trực tiếp làm cột bảng?
31. Một báo cáo cần truyền danh sách ID từ PL/SQL sang SQL. Chọn loại collection và phạm vi type phù hợp.
32. Một câu UPDATE đơn giản có thể xử lý toàn bộ hàng bằng một predicate. Vì sao set-based SQL có thể tốt hơn BULK COLLECT/FORALL?
33. Thiết kế collection cho danh sách tối đa ba bước trạng thái theo đúng thứ tự.
34. Thiết kế collection cho map mã sản phẩm sang số lượng tồn.
35. Viết một block có exception handler để đóng cursor và rollback nếu bulk DML lỗi.

**Associative array phù hợp với ánh xạ key-value trong bộ nhớ; nested table phù hợp với danh sách có kích thước linh hoạt và có thể dùng như SQL collection; VARRAY phù hợp với danh sách có giới hạn và giữ thứ tự.** Hiểu rõ sparse/dense, constructor, collection methods và phạm vi kiểu giúp tránh lỗi chỉ số. Khi xử lý nhiều hàng, BULK COLLECT và FORALL có thể giảm chi phí chuyển đổi giữa PL/SQL và SQL engine, nhưng vẫn cần kiểm soát batch size và transaction bằng COMMIT/ROLLBACK.
