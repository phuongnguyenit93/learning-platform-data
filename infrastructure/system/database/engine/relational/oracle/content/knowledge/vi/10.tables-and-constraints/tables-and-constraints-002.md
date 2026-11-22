# CREATE TABLE, giá trị DEFAULT và cột bắt buộc

Trong Oracle Database, thiết kế một bảng không dừng ở việc đặt tên cột và chọn `VARCHAR2`, `NUMBER` hay `DATE`. Ngay lúc `CREATE TABLE`, người thiết kế cần trả lời: **cột nào phải có giá trị**, **cột nào được phép `NULL`**, **khi người dùng không gửi một cột thì Oracle điền giá trị gì**, và **giới hạn nào được database bảo vệ thay vì chỉ kiểm tra ở giao diện**.

Bài học này tập trung vào ba cơ chế liên quan chặt chẽ:

- `CREATE TABLE` khai báo cấu trúc và kiểu dữ liệu của bảng.
- `DEFAULT` cung cấp giá trị mặc định trong những tình huống chèn dữ liệu phù hợp.
- `NOT NULL` và các ràng buộc như `PRIMARY KEY` bảo vệ những cột bắt buộc, kể cả khi ứng dụng hoặc công cụ SQL gửi dữ liệu thiếu.

Điểm dễ nhầm nhất là **bỏ hẳn một cột khỏi câu `INSERT` khác với gửi tường minh `NULL`**. Bài sẽ sử dụng một bảng đơn hàng nhỏ, thử các trường hợp này và liên hệ với Java/JDBC. Những lệnh tạo bảng/chèn dữ liệu chỉ nên chạy trong **schema thực hành** có quyền phù hợp, không chạy trong database production.

## 1. Bảng, cột và ràng buộc trong Oracle

Một bảng lưu các hàng dữ liệu cùng cấu trúc. Mỗi cột có **tên**, **kiểu**, **giới hạn độ dài/độ chính xác** và có thể kèm **mặc định** hoặc **ràng buộc**.

~~~mermaid
flowchart TD
    A["CREATE TABLE LAB_ORDERS"] --> B["Cột và kiểu dữ liệu"]
    A --> C["DEFAULT: giá trị được đề xuất khi INSERT"]
    A --> D["NOT NULL: cấm lưu giá trị NULL"]
    A --> E["PRIMARY KEY: định danh mỗi hàng"]
    A --> F["CHECK: quy tắc nghiệp vụ tối thiểu"]
    B --> G["Hàng dữ liệu được Oracle lưu"]
    C --> G
    D --> G
    E --> G
    F --> G
~~~

| Thuộc tính | Chức năng | Ví dụ |
|---|---|---|
| `NUMBER(12,2)` | Kiểu số, giới hạn precision/scale | Đơn giá |
| `VARCHAR2(30 CHAR)` | Chuỗi, giới hạn theo số ký tự với trần byte của Oracle | Mã khách hàng |
| `DATE` | Ngày và thời gian tới giây, không chứa timezone | Ngày tạo |
| `DEFAULT 1` | Cung cấp mặc định khi không có giá trị đầu vào thuộc trường hợp được hỗ trợ | Số lượng mặc định |
| `NOT NULL` | Không cho cột lưu giá trị `NULL` | Mã khách hàng |
| `PRIMARY KEY` | Xác định hàng duy nhất và không `NULL` | `ORDER_ID` |
| `CHECK` | Chặn một số giá trị trái quy tắc | `QUANTITY > 0` |

**`DEFAULT` không thay thế `NOT NULL`.** Ngược lại, **`NOT NULL` không tự tạo giá trị**. Nếu một cột bắt buộc không có mặc định và câu `INSERT` không cung cấp giá trị hợp lệ, Oracle không thể tạo hàng thành công.

## 2. Đọc cú pháp CREATE TABLE

Mẫu cơ bản:

~~~sql
CREATE TABLE ten_bang (
    ten_cot_1 kieu_du_lieu [DEFAULT bieu_thuc] [rang_buoc],
    ten_cot_2 kieu_du_lieu [DEFAULT bieu_thuc] [rang_buoc],
    ...
    [CONSTRAINT ten_rang_buoc PRIMARY KEY (ten_cot_1)]
);
~~~

Các phần trong dấu ngoặc vuông là ký hiệu mô tả cú pháp, **không phải đoạn SQL nguyên vẹn để chạy**. Trong câu lệnh thật, Oracle cần kiểu dữ liệu hợp lệ, dấu phẩy phân tách cột và dấu `;` kết thúc câu SQL ở công cụ tương ứng.

Trong Oracle, có thể đặt một số constraint **ngay sau cột** (*inline*) hoặc khai báo ở **cấp bảng** (*out-of-line*). Chẳng hạn:

~~~sql
CREATE TABLE lab_customers (
    customer_id   NUMBER(10),
    customer_code VARCHAR2(30 CHAR)
                  CONSTRAINT nn_lab_customers_code NOT NULL,
    display_name  VARCHAR2(100 CHAR) NOT NULL,
    CONSTRAINT pk_lab_customers PRIMARY KEY (customer_id)
);
~~~

Ở đây:

1. `CUSTOMER_ID` có khóa chính khai báo ở cấp bảng nên bắt buộc không `NULL` và không trùng.
2. `CUSTOMER_CODE` có `NOT NULL` được đặt tên `NN_LAB_CUSTOMERS_CODE`.
3. `DISPLAY_NAME` cũng bắt buộc, dù Oracle có thể tự sinh tên constraint nếu không ghi tên.
4. Không cột nào có `DEFAULT`; ứng dụng phải cung cấp giá trị phù hợp nếu muốn chèn một hàng.

Đặt tên constraint có ý nghĩa giúp dễ đọc lỗi và metadata. Ví dụ `PK_LAB_CUSTOMERS` hoặc `NN_LAB_CUSTOMERS_CODE` dễ nhận diện hơn tên tự sinh như `SYS_C...`.

### 2.1 Bảng được tạo trong schema và PDB nào?

Trước khi chạy DDL, xác nhận kết nối:

~~~sql
SELECT USER AS session_user,
       SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS current_schema,
       SYS_CONTEXT('USERENV','CON_NAME') AS container_name
FROM dual;
~~~

Tên `LAB_CUSTOMERS` không có tiền tố schema được phân giải theo ngữ cảnh session và quyền. Trong CDB/PDB, chạy đúng server nhưng nhầm PDB có thể tạo bảng sai phạm vi. Với bài thực hành, đăng nhập trực tiếp vào **service của PDB thực hành** bằng user được phép tạo bảng trong schema của mình.

**Lưu ý về DDL:** Trong Oracle, nhiều lệnh DDL như `CREATE TABLE` thực hiện commit ngầm theo cơ chế Oracle. Không dùng `ROLLBACK` với kỳ vọng xóa một bảng vừa tạo hoặc hoàn tác một DDL đã hoàn tất. Chỉ tạo bảng mẫu trong môi trường được phép.

## 3. Ví dụ xuyên suốt: tạo bảng đơn hàng có DEFAULT và NOT NULL

Tạo bảng thực hành:

~~~sql
CREATE TABLE lab_orders (
    order_id      NUMBER(10),
    customer_code VARCHAR2(30 CHAR)
                  CONSTRAINT nn_lab_orders_customer NOT NULL,
    status        VARCHAR2(12 CHAR) DEFAULT 'NEW'
                  CONSTRAINT nn_lab_orders_status NOT NULL,
    quantity      NUMBER(6) DEFAULT 1
                  CONSTRAINT nn_lab_orders_quantity NOT NULL,
    unit_price    NUMBER(12,2)
                  CONSTRAINT nn_lab_orders_price NOT NULL,
    created_at    DATE DEFAULT SYSDATE
                  CONSTRAINT nn_lab_orders_created NOT NULL,
    note          VARCHAR2(200 CHAR),

    CONSTRAINT pk_lab_orders PRIMARY KEY (order_id),
    CONSTRAINT ck_lab_orders_status
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    CONSTRAINT ck_lab_orders_quantity
        CHECK (quantity > 0),
    CONSTRAINT ck_lab_orders_price
        CHECK (unit_price >= 0)
);
~~~

Đây là bảng minh họa một **đơn hàng có một số lượng và đơn giá**, không phải mô hình thương mại điện tử đầy đủ. Mục tiêu là nhìn rõ tương tác của các ràng buộc.

| Cột | Kiểu | Có `DEFAULT`? | Cho `NULL`? | Ý nghĩa |
|---|---|---|---|---|
| `ORDER_ID` | `NUMBER(10)` | Không | Không, vì `PRIMARY KEY` | Mã định danh đơn hàng, cần giá trị duy nhất |
| `CUSTOMER_CODE` | `VARCHAR2(30 CHAR)` | Không | Không | Bắt buộc nhập mã khách hàng |
| `STATUS` | `VARCHAR2(12 CHAR)` | `'NEW'` | Không | Nếu bỏ qua khi chèn, mặc định `NEW` |
| `QUANTITY` | `NUMBER(6)` | `1` | Không | Nếu bỏ qua, mặc định một đơn vị |
| `UNIT_PRICE` | `NUMBER(12,2)` | Không | Không | Bắt buộc nhập đơn giá, không âm |
| `CREATED_AT` | `DATE` | `SYSDATE` | Không | Thời điểm tạo theo đồng hồ database server |
| `NOTE` | `VARCHAR2(200 CHAR)` | Không | **Có** | Ghi chú tùy chọn |

`DEFAULT SYSDATE` được tính cho thao tác chèn phù hợp, không phải chuỗi văn bản cố định `'SYSDATE'`. Cột `DATE` lưu cả ngày lẫn giờ/phút/giây, mặc dù một công cụ có thể chỉ hiển thị phần ngày do `NLS_DATE_FORMAT`.

Các `CHECK` chỉ là quy tắc dữ liệu đơn giản:

- `STATUS` chỉ thuộc tập `NEW`, `PAID`, `CANCELLED`.
- `QUANTITY` phải lớn hơn 0.
- `UNIT_PRICE` không được âm.

Vì đã có `NOT NULL` cho các cột tương ứng, không cần dựa vào `CHECK` để cấm `NULL`. Trong SQL ba giá trị của Oracle, một điều kiện `CHECK` có kết quả *UNKNOWN* (ví dụ do `NULL`) không giống kết quả `FALSE`; khi muốn một cột chắc chắn có giá trị, hãy khai báo `NOT NULL` rõ ràng.

## 4. DEFAULT hoạt động thế nào khi INSERT?

### 4.1 Bỏ cột có mặc định khỏi danh sách INSERT

~~~sql
INSERT INTO lab_orders (
    order_id,
    customer_code,
    unit_price
)
VALUES (
    101,
    'CUS-001',
    120000
);

COMMIT;
~~~

Trong câu trên, bốn cột `STATUS`, `QUANTITY`, `CREATED_AT`, `NOTE` không được truyền:

- `STATUS` nhận `'NEW'` theo `DEFAULT`.
- `QUANTITY` nhận `1` theo `DEFAULT`.
- `CREATED_AT` nhận kết quả `SYSDATE` tại thời điểm thích hợp.
- `NOTE` không có mặc định, không `NOT NULL`, nên nhận `NULL`.

Đọc lại:

~~~sql
SELECT order_id,
       customer_code,
       status,
       quantity,
       unit_price,
       TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_text,
       note
FROM lab_orders
WHERE order_id = 101;
~~~

Kết quả ví dụ:

~~~text
ORDER_ID  CUSTOMER_CODE  STATUS  QUANTITY  UNIT_PRICE  CREATED_TEXT         NOTE
--------  -------------  ------  --------  ----------  -------------------  ----
101       CUS-001        NEW     1         120000      <thoi-diem-chen>      NULL
~~~

`CREATED_TEXT` thực tế là ngày giờ do server cung cấp; không sao chép một mốc cố định từ ví dụ. `TO_CHAR` với format tường minh giúp đọc rõ phần thời gian, không phụ thuộc định dạng hiển thị ngày của mỗi session.

### 4.2 Truyền trực tiếp giá trị khác mặc định

~~~sql
INSERT INTO lab_orders (
    order_id, customer_code, status, quantity, unit_price, note
)
VALUES (
    102, 'CUS-002', 'PAID', 3, 89000, 'Da thanh toan'
);

COMMIT;
~~~

`STATUS` nhận `PAID` và `QUANTITY` nhận `3`; giá trị mặc định **không ghi đè giá trị hợp lệ được cung cấp**. `CREATED_AT` vẫn nhận `SYSDATE` vì không có trong danh sách cột.

### 4.3 Dùng từ khóa DEFAULT trong danh sách VALUES

Oracle hỗ trợ dùng từ khóa `DEFAULT` ở vị trí giá trị thích hợp:

~~~sql
INSERT INTO lab_orders (
    order_id, customer_code, status, quantity, unit_price
)
VALUES (
    103, 'CUS-003', DEFAULT, DEFAULT, 150000
);

COMMIT;
~~~

`DEFAULT` tại vị trí `STATUS` và `QUANTITY` yêu cầu Oracle dùng biểu thức mặc định đã khai báo cho cột, tương tự trường hợp bỏ cột đó khỏi danh sách `INSERT`. Đây là từ khóa SQL, **không phải chuỗi `'DEFAULT'`**.

Nếu cột không có `DEFAULT` thì yêu cầu dùng mặc định thường dẫn tới `NULL`; nếu cột đó có `NOT NULL`, phép chèn sẽ bị từ chối. Không nên mặc định mọi cột đều có một giá trị hợp lệ khi gõ `DEFAULT`.

### 4.4 DEFAULT có áp dụng khi gửi tường minh NULL?

Đối với cú pháp `DEFAULT` thông thường, **không**. Ví dụ:

~~~sql
-- Minh họa lệnh sẽ thất bại; không chạy cùng batch INSERT thành công:
INSERT INTO lab_orders (
    order_id, customer_code, status, unit_price
)
VALUES (
    104, 'CUS-004', NULL, 70000
);
~~~

Trong bảng đã tạo, `STATUS` có `DEFAULT 'NEW'` **và** `NOT NULL`. Vì câu `INSERT` **đã truyền `NULL` tường minh**, Oracle không thay nó bằng `NEW` theo quy tắc `DEFAULT` thông thường; `NOT NULL` bị vi phạm và kết quả thường là:

~~~text
ORA-01400: cannot insert NULL into ...
~~~

Đây là sự khác nhau thiết yếu giữa **“không gửi giá trị”** và **“gửi một giá trị null”**. Chỉ có `DEFAULT` không đủ để điều khiển cả hai trường hợp.

### 4.5 DEFAULT không tự chạy lại khi UPDATE

Giả sử `ORDER_ID = 101` có `STATUS = NEW`; sau đó:

~~~sql
UPDATE lab_orders
SET status = 'PAID'
WHERE order_id = 101;
~~~

Oracle không tự “áp lại `DEFAULT 'NEW'`” khi một cột khác được cập nhật, hoặc sau mỗi lần `UPDATE`. Định nghĩa `DEFAULT` chủ yếu điều khiển giá trị mặc định ở thao tác chèn và các ngữ cảnh chỉ định `DEFAULT` rõ ràng. Trong trường hợp có hỗ trợ, người dùng có thể viết:

~~~sql
UPDATE lab_orders
SET status = DEFAULT
WHERE order_id = 101;

COMMIT;
~~~

Khi đó `STATUS` được đặt lại theo mặc định khai báo. Hai câu `UPDATE` này được đưa ra để giải thích hành vi: hãy chạy trong bảng thực hành nếu muốn quan sát, không phải trong dữ liệu đơn hàng thật.

## 5. NOT NULL: cột bắt buộc không có nghĩa tự có giá trị

`NOT NULL` bảo đảm một cột **không nhận giá trị null** khi Oracle ghi hoặc cập nhật hàng. Trong bảng `LAB_ORDERS`:

~~~sql
-- Sẽ lỗi vì CUSTOMER_CODE là cột bắt buộc và không có DEFAULT.
INSERT INTO lab_orders (order_id, unit_price)
VALUES (105, 100000);
~~~

Giải thích:

- `ORDER_ID` được cung cấp.
- `UNIT_PRICE` được cung cấp.
- `STATUS`, `QUANTITY` và `CREATED_AT` có mặc định, nên có thể nhận giá trị hợp lệ.
- `CUSTOMER_CODE` bị bỏ qua, không có mặc định, nên giá trị ngầm định là `NULL`; vì `NOT NULL`, câu `INSERT` thất bại.

Khai báo `NOT NULL` không tạo ra mã khách hàng giả; database yêu cầu ứng dụng cung cấp giá trị phù hợp.

### 5.1 DEFAULT và NOT NULL là hai chiều độc lập

| Khai báo cột | Khi không gửi cột trong INSERT | Khi gửi `NULL` tường minh | Kết luận |
|---|---|---|---|
| `note VARCHAR2(100)` | Nhận `NULL` | Nhận `NULL` | Cột tùy chọn |
| `note VARCHAR2(100) DEFAULT 'N/A'` | Nhận `N/A` | **Nhận `NULL`** | Có mặc định nhưng vẫn nullable |
| `note VARCHAR2(100) NOT NULL` | Lỗi vì không có giá trị | Lỗi | Bắt buộc ứng dụng cung cấp |
| `note VARCHAR2(100) DEFAULT 'N/A' NOT NULL` | Nhận `N/A` | Lỗi | Bỏ qua thì được, gửi null thì lỗi |
| `note VARCHAR2(100) DEFAULT ON NULL 'N/A'` | Nhận `N/A` | Nhận `N/A` khi INSERT | Trường hợp đặc biệt, cần phiên bản hỗ trợ |

Chính sự khác biệt giữa các dòng này quyết định cách ứng dụng thiết kế request, validate và bind dữ liệu.

### 5.2 NULL không phải chuỗi rỗng hay số 0

`NULL` nghĩa là không có giá trị được ghi nhận, không phải số 0 hoặc một chữ `"NULL"`.

~~~sql
-- Chuỗi 'NULL' là bốn ký tự, không phải SQL NULL:
SELECT 'NULL' AS literal_text
FROM dual;

-- Kiểm tra NULL đúng cách:
SELECT order_id
FROM lab_orders
WHERE note IS NULL;
~~~

Trong Oracle, **chuỗi ký tự độ dài 0** ở các kiểu ký tự thông dụng như `VARCHAR2` hiện được xử lý như `NULL`. Vì thế, một ứng dụng gửi chuỗi rỗng `''` cho `CUSTOMER_CODE NOT NULL` có thể gặp vi phạm `NOT NULL`. Nhưng một chuỗi chứa khoảng trắng như `' '` **không phải `NULL`**; nếu nghiệp vụ không chấp nhận mã toàn khoảng trắng, cần kiểm tra bổ sung ở tầng dữ liệu/ứng dụng.

Không dùng:

~~~sql
WHERE note = NULL
~~~

để tìm hàng không có ghi chú. Trong SQL, so sánh với `NULL` cho kết quả không xác định (*UNKNOWN*); để kiểm tra thiếu giá trị phải dùng `IS NULL` hoặc `IS NOT NULL`.

## 6. DEFAULT ON NULL: giải quyết trường hợp ứng dụng gửi NULL

Từ các phiên bản Oracle hỗ trợ cú pháp `DEFAULT ON NULL` (được giới thiệu trong dòng Oracle Database 12c), có thể khai báo cột sao cho Oracle sử dụng mặc định **cả khi cột không được cung cấp lẫn khi `INSERT` truyền `NULL`**.

Trong schema thực hành:

~~~sql
CREATE TABLE lab_default_compare (
    id                   NUMBER PRIMARY KEY,
    standard_default     VARCHAR2(12 CHAR) DEFAULT 'NEW',
    default_when_null    VARCHAR2(12 CHAR) DEFAULT ON NULL 'NEW'
);
~~~

Thử ba cách chèn:

~~~sql
-- 1) Bỏ cả hai cột: đều dùng mặc định
INSERT INTO lab_default_compare (id)
VALUES (1);

-- 2) Truyền NULL vào cả hai cột
INSERT INTO lab_default_compare (
    id, standard_default, default_when_null
)
VALUES (
    2, NULL, NULL
);

-- 3) Truyền các giá trị hợp lệ tường minh
INSERT INTO lab_default_compare (
    id, standard_default, default_when_null
)
VALUES (
    3, 'PAID', 'PAID'
);

COMMIT;

SELECT id, standard_default, default_when_null
FROM lab_default_compare
ORDER BY id;
~~~

Kết quả dự kiến:

| ID | `STANDARD_DEFAULT` | `DEFAULT_WHEN_NULL` |
|---:|---|---|
| 1 | `NEW` | `NEW` |
| 2 | `NULL` | `NEW` |
| 3 | `PAID` | `PAID` |

`DEFAULT ON NULL` có liên hệ với ràng buộc **không nullable** của cột theo quy tắc Oracle; nó không chỉ là phép thay thế hiển thị. Chẳng hạn nếu cố gắng cập nhật cột kiểu này thành `NULL` theo cơ chế thường, sẽ không được coi là một thao tác gán giá trị null hợp lệ. Để tìm hiểu hành vi của phiên bản cụ thể với các biến thể hỗ trợ cập nhật, cần xem tài liệu theo đúng release; ví dụ ở đây tập trung vào **INSERT**.

### 6.1 Khi nào nên dùng DEFAULT ON NULL?

Đây là lựa chọn phù hợp khi **mọi lần tạo hàng đều cần một trạng thái mặc định**, kể cả nếu một client cũ gửi `NULL`. Tuy nhiên cũng có trường hợp gửi `NULL` là **một lỗi nghiệp vụ cần được phát hiện**, ví dụ mã khách hàng bắt buộc, email cần nhập hoặc thời hạn do người dùng lựa chọn.

Nếu gửi `NULL` là sai, nên để ràng buộc `NOT NULL` báo lỗi thay vì âm thầm thay bằng giá trị giả. Không nên dùng `DEFAULT ON NULL 'UNKNOWN'` cho mọi cột chỉ để làm biến mất lỗi dữ liệu.

### 6.2 Khác nhau giữa DEFAULT ON NULL và NVL

`NVL` là hàm SQL thường dùng khi **đọc hoặc tính biểu thức**:

~~~sql
SELECT id, NVL(standard_default, 'NOT_SET') AS displayed_status
FROM lab_default_compare;
~~~

Hàm này trả về một giá trị biểu thức thay thế khi dữ liệu là `NULL`, nhưng **không sửa giá trị đã lưu** trong bảng. `DEFAULT ON NULL` lại tác động tới giá trị được đặt vào cột theo quy tắc `INSERT`. Đừng nhầm logic hiển thị lúc `SELECT` với chính sách lưu dữ liệu.

## 7. PRIMARY KEY, CHECK và các ràng buộc liên quan

Bài tập về “cột bắt buộc” nên phân biệt `NOT NULL` với những quy tắc bổ sung:

### 7.1 PRIMARY KEY không chỉ là NOT NULL

~~~sql
CONSTRAINT pk_lab_orders PRIMARY KEY (order_id)
~~~

Khóa chính yêu cầu **mỗi giá trị khóa tồn tại và duy nhất**. Cột thuộc khóa chính không được `NULL`. Nếu cố chèn hai hàng cùng `ORDER_ID`, Oracle báo lỗi tính duy nhất, thường là `ORA-00001`. Nếu chỉ đặt `ORDER_ID NOT NULL` mà không có `PRIMARY KEY` hoặc `UNIQUE` thì vẫn có thể tồn tại nhiều hàng cùng mã; do đó hai ràng buộc không tương đương.

Với khóa chính gồm nhiều cột, tất cả cột khóa tham gia đều phải có giá trị không `NULL`. Trong thiết kế thông thường, ưu tiên khóa định danh rõ ràng, ổn định cho bảng.

### 7.2 CHECK bảo vệ tập giá trị hoặc khoảng giá trị

~~~sql
CONSTRAINT ck_lab_orders_status
CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
~~~

`CHECK` chỉ cho phép dữ liệu phù hợp tập trạng thái. Nếu gửi `'REFUNDED'` trong khi chưa thêm nó vào quy tắc, Oracle có thể báo `ORA-02290: check constraint violated`. Nhưng một `CHECK` không tự tạo giá trị trạng thái và không thay thế chính sách `NULL` nếu không khai báo cấm null rõ ràng.

Một thiết kế đầy đủ sẽ phối hợp:

- Kiểu dữ liệu đúng.
- `DEFAULT` hợp lý với trạng thái lúc tạo.
- `NOT NULL` cho cột phải có giá trị.
- `CHECK` cho miền giá trị; `PRIMARY KEY` / `FOREIGN KEY` / `UNIQUE` cho các quan hệ cần bảo vệ.

### 7.3 FOREIGN KEY không tự sinh khóa cha

Giả sử một hệ thống có `CUSTOMERS(CUSTOMER_ID)` và muốn `LAB_ORDERS.CUSTOMER_ID` tham chiếu tới nó:

~~~sql
-- Ví dụ riêng về cú pháp, không bổ sung trực tiếp vào bảng mẫu bên trên:
CREATE TABLE lab_order_refs (
    order_id    NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    CONSTRAINT fk_lab_order_refs_customer
        FOREIGN KEY (customer_id)
        REFERENCES lab_customers (customer_id)
);
~~~

Ràng buộc khóa ngoại đảm bảo giá trị `CUSTOMER_ID` tham chiếu tới một khóa cha hợp lệ theo cơ chế Oracle. `NOT NULL` đảm bảo không được bỏ mã khách hàng. Hai vai trò này khác nhau: khóa ngoại cho phép `NULL` nếu cột không bị ràng buộc `NOT NULL`, trong khi `NOT NULL` không chứng minh mã khách hàng đó tồn tại ở bảng cha.

## 8. Giá trị mặc định của DATE, TIMESTAMP và NUMBER

### 8.1 DEFAULT là biểu thức được Oracle sử dụng lúc thích hợp

~~~sql
CREATE TABLE lab_event_log (
    event_id    NUMBER PRIMARY KEY,
    event_code  VARCHAR2(30 CHAR) NOT NULL,
    event_time  TIMESTAMP DEFAULT LOCALTIMESTAMP NOT NULL,
    retry_count NUMBER(4) DEFAULT 0 NOT NULL
);
~~~

`LOCALTIMESTAMP` tạo timestamp hiện tại trong ngữ cảnh timezone session, trả về kiểu `TIMESTAMP` không chứa timezone. `SYSDATE` trả thời gian hệ thống database server dưới kiểu `DATE`. Nếu một hệ thống cần ghi lại **thời điểm tuyệt đối kèm ý nghĩa múi giờ**, cần lựa chọn loại cột và API thời gian phù hợp; không dùng mỗi `DATE DEFAULT SYSDATE` như lời đảm bảo có lưu timezone.

Với số:

~~~sql
retry_count NUMBER(4) DEFAULT 0 NOT NULL
~~~

mặc định `0` là **giá trị NUMBER**, không phải chuỗi `'0'`. Ứng dụng nên bind số bằng kiểu số tương ứng. Nếu nghiệp vụ muốn phân biệt “chưa ghi nhận số lần thử” với “đã ghi nhận là 0 lần”, thì việc đặt `DEFAULT 0` có thể xóa mất sự khác biệt ấy; thiết kế cần tuân theo hợp đồng dữ liệu.

### 8.2 Mặc định không phải “giá trị luôn cập nhật”

Giả sử thêm cột:

~~~sql
created_at DATE DEFAULT SYSDATE NOT NULL
~~~

Nó hữu ích để biết thời điểm tạo hàng, nhưng **không tự cập nhật mỗi khi hàng thay đổi**. Với `updated_at`, cần thiết kế logic cập nhật riêng, ví dụ ứng dụng đặt timestamp trong `UPDATE` hoặc dùng trigger theo chính sách hệ thống. Không nên suy rằng hai tên cột `CREATED_AT` và `UPDATED_AT` có hành vi đặc biệt chỉ vì tên gọi.

### 8.3 Tránh mặc định gây phụ thuộc NLS

Không nên coi một chuỗi tùy ý là mặc định kiểu ngày:

~~~sql
-- Không nên phụ thuộc định dạng NLS của session/database:
-- some_date DATE DEFAULT '14/11/2026'
~~~

Khi cần một mốc cố định, ưu tiên date literal:

~~~sql
CREATE TABLE lab_campaigns (
    campaign_id NUMBER PRIMARY KEY,
    start_date  DATE DEFAULT DATE '2026-11-14' NOT NULL
);
~~~

`DATE 'YYYY-MM-DD'` có cú pháp cố định, không phải chuỗi ngày được diễn giải theo `NLS_DATE_FORMAT`. Với dữ liệu người dùng gửi từ Java, nên bind kiểu ngày/giờ thay vì ghép chuỗi trong SQL. Ngôn ngữ và múi giờ khi chuyển sang văn bản là bài toán khác với ràng buộc bắt buộc của cột.

## 9. DEFAULT, IDENTITY và cách tạo khóa chính

`DEFAULT` trên một cột mã không đồng nghĩa Oracle sẽ tự tăng mã theo từng hàng. Nếu viết:

~~~sql
order_id NUMBER DEFAULT 1 PRIMARY KEY
~~~

thì nhiều hàng bỏ `ORDER_ID` sẽ cố nhận cùng mã `1`, dẫn tới lỗi khóa chính. Khi cần Oracle sinh khóa định danh, hãy dùng **identity column** hoặc sequence phù hợp với phiên bản.

Từ dòng Oracle Database 12c, có thể sử dụng:

~~~sql
CREATE TABLE lab_identity_orders (
    order_id NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY,
    note     VARCHAR2(100 CHAR),
    CONSTRAINT pk_lab_identity_orders PRIMARY KEY (order_id)
);
~~~

Trong ví dụ này, `ORDER_ID` dùng cơ chế identity, **khác với `DEFAULT ON NULL 'NEW'` cho một cột văn bản**. Oracle sinh giá trị khóa khi câu `INSERT` không cung cấp mã hoặc cung cấp `NULL` theo biến thể `BY DEFAULT ON NULL`. Các lựa chọn identity còn gồm `GENERATED ALWAYS` và `GENERATED BY DEFAULT` với quy tắc cho phép/không cho phép giá trị do client tự truyền khác nhau.

Ví dụ:

~~~sql
INSERT INTO lab_identity_orders (note)
VALUES ('Don tu sinh ma');

COMMIT;

SELECT order_id, note
FROM lab_identity_orders;
~~~

ID sinh tự động **không bảo đảm liền nhau tuyệt đối**: sequence/identity có thể có khoảng trống vì rollback, cache, concurrency hoặc thao tác khác. Do đó không dùng số thứ tự tăng của identity làm chứng từ kinh doanh đòi hỏi liên tục không thiếu số, nếu chưa có cơ chế nghiệp vụ riêng.

Với Oracle phiên bản cũ không hỗ trợ identity, có thể dùng sequence và thiết kế DML/trigger phù hợp; **đừng chép nguyên cú pháp identity 12c+ sang Oracle 11g**. Quan trọng nhất là phân biệt: khóa chính bảo vệ tính duy nhất, còn cơ chế sinh khóa giải quyết việc tạo giá trị.

## 10. Xem cấu trúc, DEFAULT và NOT NULL trong data dictionary

Sau khi tạo bảng, không nên chỉ tin vào file DDL cũ. Dùng metadata của **bảng đang tồn tại** để biết trạng thái thực tế.

### 10.1 Cột, khả năng nullable và giá trị mặc định

Với bảng do user hiện tại sở hữu:

~~~sql
SELECT column_id,
       column_name,
       data_type,
       data_length,
       nullable,
       data_default
FROM user_tab_columns
WHERE table_name = 'LAB_ORDERS'
ORDER BY column_id;
~~~

Trong `USER_TAB_COLUMNS`:

- `COLUMN_NAME`: tên cột.
- `DATA_TYPE`, `DATA_LENGTH`: kiểu và giới hạn byte thuộc metadata kiểu.
- `NULLABLE = 'N'`: cột được metadata ghi nhận là không được `NULL`; `Y` cho phép `NULL` theo trạng thái ràng buộc liên quan.
- `DATA_DEFAULT`: biểu thức mặc định được lưu trong metadata, nếu có.

`DATA_DEFAULT` là một cột metadata kiểu `LONG` ở nhiều phiên bản; một số công cụ có thể hiển thị bị cắt nếu cấu hình độ dài output nhỏ. Trong SQL*Plus, có thể dùng:

~~~sql
SET LONG 10000
~~~

trước khi chọn `DATA_DEFAULT`. Nếu cần xem schema khác mà mình có quyền quan sát, dùng `ALL_TAB_COLUMNS` và thêm điều kiện `OWNER`:

~~~sql
SELECT owner, table_name, column_name, nullable, data_default
FROM all_tab_columns
WHERE owner = 'APP_OWNER'
  AND table_name = 'LAB_ORDERS';
~~~

Thay `APP_OWNER` bằng tên schema thực tế; `ALL_TAB_COLUMNS` không có nghĩa user thường nhìn được tất cả bảng trong database.

### 10.2 Xem DEFAULT ON NULL trong phiên bản hỗ trợ

Trên các phiên bản có cột metadata phù hợp, có thể quan sát:

~~~sql
SELECT column_name,
       nullable,
       default_on_null
FROM user_tab_columns
WHERE table_name = 'LAB_DEFAULT_COMPARE'
ORDER BY column_id;
~~~

`DEFAULT_ON_NULL` giúp nhận diện trường hợp khai báo mặc định đặc biệt. Nếu database/version không có cột này thì truy vấn có thể báo `ORA-00904`; hãy xem định nghĩa view theo phiên bản thay vì kết luận bảng không có `DEFAULT`. Kết hợp với `DATA_DEFAULT` để biết **biểu thức** được áp dụng.

### 10.3 Xem các constraint và cột liên quan

~~~sql
SELECT c.constraint_name,
       c.constraint_type,
       c.status,
       c.validated,
       cc.column_name,
       cc.position
FROM user_constraints c
JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
 AND cc.table_name = c.table_name
WHERE c.table_name = 'LAB_ORDERS'
ORDER BY c.constraint_name, cc.position;
~~~

| `CONSTRAINT_TYPE` | Loại thường gặp |
|---|---|
| `P` | Primary key |
| `U` | Unique |
| `R` | Referential integrity / foreign key |
| `C` | Check constraint; các ràng buộc `NOT NULL` thường cũng được phản ánh trong nhóm này |

`STATUS` và `VALIDATED` giúp biết constraint đang bật và được xác thực ở trạng thái nào. Một constraint có mặt trong metadata nhưng bị vô hiệu hóa hoặc chưa validate không thể được diễn giải giống ràng buộc đang bảo vệ mọi hàng theo chế độ bình thường. Trong môi trường học, nên tạo constraint có hiệu lực và để Oracle kiểm tra dữ liệu ngay từ đầu.

Để xem điều kiện `CHECK`, phiên bản Oracle hỗ trợ có thể dùng `SEARCH_CONDITION_VC` trong `USER_CONSTRAINTS`; một số bản cũng có `SEARCH_CONDITION` kiểu `LONG`. Với khả năng tương thích rộng, có thể dùng lệnh xem DDL từ công cụ hoặc `DBMS_METADATA.GET_DDL` theo quyền của user để kiểm tra định nghĩa thực tế.

## 11. Thay đổi DEFAULT hoặc NOT NULL trên bảng đã tồn tại

Thiết kế có thể thay đổi, nhưng phải đánh giá dữ liệu hiện có trước khi áp dụng constraint mới.

### 11.1 Đổi DEFAULT cho những INSERT về sau

Trong bảng thực hành:

~~~sql
ALTER TABLE lab_orders
MODIFY (quantity DEFAULT 2);
~~~

Sau lệnh này, các `INSERT` phù hợp không cung cấp `QUANTITY` sẽ dùng mặc định mới `2`. Việc sửa biểu thức default **không đồng nghĩa tự cập nhật tất cả hàng cũ** từ `1` thành `2`. Nếu muốn đổi dữ liệu cũ, phải có phương án `UPDATE` riêng, kiểm soát tác động nghiệp vụ và transaction.

### 11.2 Trước khi thêm NOT NULL, kiểm tra NULL hiện có

Giả sử cột `NOTE` hiện tùy chọn:

~~~sql
SELECT COUNT(*) AS null_note_rows
FROM lab_orders
WHERE note IS NULL;
~~~

Nếu có hàng đang `NOTE IS NULL`, việc áp thêm ràng buộc bắt buộc bằng:

~~~sql
-- Chỉ thực hiện sau khi xử lý dữ liệu null và xác nhận nghiệp vụ:
ALTER TABLE lab_orders
MODIFY (note NOT NULL);
~~~

có thể bị từ chối vì dữ liệu cũ vi phạm constraint mới. Oracle có thể báo lỗi như `ORA-02296: cannot enable ... null values found`. **Không** tự thay tất cả `NULL` bằng chữ `N/A` nếu “không có ghi chú” có ý nghĩa khác với “ghi chú là N/A”.

Quy trình thay đổi an toàn gồm: xem dữ liệu thực tế, xác định ý nghĩa của `NULL`, chuẩn hóa dữ liệu khi được nghiệp vụ chấp thuận, áp constraint vào thời điểm phù hợp và kiểm tra tác động tới ứng dụng.

### 11.3 Thêm cột bắt buộc vào bảng đang có dữ liệu

Nếu bảng đã chứa hàng, thao tác thêm cột `NOT NULL` không có default có thể thất bại vì các hàng hiện tại không có giá trị cho cột mới:

~~~sql
-- Ví dụ thay đổi có rủi ro, không chạy trên bảng production:
ALTER TABLE lab_orders
ADD (source_system VARCHAR2(20 CHAR) NOT NULL);
~~~

Với chính sách nghiệp vụ cho phép một mặc định hợp lý, có thể cân nhắc:

~~~sql
ALTER TABLE lab_orders
ADD (source_system VARCHAR2(20 CHAR)
     DEFAULT 'MANUAL' NOT NULL);
~~~

Tùy kiểu cột, phiên bản và điều kiện của bảng, Oracle có những tối ưu khác nhau khi thêm cột có default. Không suy rằng mọi trường hợp đều được bổ sung metadata-only hay không tạo I/O. Trên bảng lớn cần đánh giá lock, kế hoạch migration, backfill và thời gian bảo trì.

## 12. INSERT từ ứng dụng Java và các giá trị thiếu

Với JDBC, sự khác nhau giữa **không đưa cột vào SQL** và **bind `NULL` vào tham số** đặc biệt quan trọng.

### 12.1 Bỏ cột để Oracle áp DEFAULT

Giả sử ứng dụng đã có `Connection connection`, không cần tự tạo `STATUS`, `QUANTITY` hay `CREATED_AT` nếu muốn dùng mặc định:

~~~java
String sql = """
    INSERT INTO lab_orders (order_id, customer_code, unit_price)
    VALUES (?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 201L);
    ps.setString(2, "CUS-JAVA");
    ps.setBigDecimal(3, new java.math.BigDecimal("250000.00"));
    ps.executeUpdate();
}
~~~

Trong SQL này, **ba cột có default không nằm trong danh sách** nên Oracle có thể điền mặc định. Đoạn ví dụ giả định có import `java.sql.*` phù hợp và transaction/`COMMIT` được ứng dụng kiểm soát; `executeUpdate` không đồng nghĩa giao dịch đã commit nếu connection đang tắt autocommit.

### 12.2 Bind NULL không đồng nghĩa “để trống cho DEFAULT”

Ví dụ khác:

~~~java
String sql = """
    INSERT INTO lab_orders (order_id, customer_code, status, unit_price)
    VALUES (?, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 202L);
    ps.setString(2, "CUS-JAVA");
    ps.setNull(3, java.sql.Types.VARCHAR);
    ps.setBigDecimal(4, new java.math.BigDecimal("250000.00"));
    ps.executeUpdate();
}
~~~

Đây là ví dụ **sẽ thất bại** với bảng `LAB_ORDERS` ban đầu: `STATUS` là `DEFAULT 'NEW' NOT NULL`, còn JDBC đã truyền `NULL` rõ ràng. Oracle phải tôn trọng quy tắc `NOT NULL`, không thay bằng mặc định thông thường. Nếu nghiệp vụ yêu cầu xử lý cả `NULL` thành `NEW`, có thể xem xét `DEFAULT ON NULL` phù hợp thay vì thay đổi cách hiểu của một lệnh `setNull`.

### 12.3 JSON, ORM và PATCH cần thiết kế riêng

Trong một API, ba trạng thái của trường đầu vào thường cần được phân biệt:

| Đầu vào từ client | Ý nghĩa nghiệp vụ có thể có | Cách SQL có thể xử lý |
|---|---|---|
| Không có key `status` | Sử dụng trạng thái mặc định | Bỏ `STATUS` khỏi `INSERT` hoặc dùng từ khóa `DEFAULT` |
| Key `status` có `null` | Client không cung cấp giá trị hợp lệ hoặc yêu cầu xóa giá trị | Từ chối validation hoặc bind `NULL` nếu cột cho phép; `DEFAULT ON NULL` chỉ khi thiết kế chấp nhận |
| Key `status` có `"PAID"` | Muốn đặt trạng thái cụ thể | Bind `'PAID'`, bị kiểm tra bởi `CHECK` |

Một ORM có thể sinh câu `INSERT` chứa toàn bộ cột và bind `NULL` cho những field chưa được gán. Khi đó mặc định chỉ áp dụng cho cột **đã bị bỏ khỏi SQL** hoặc theo cơ chế `DEFAULT ON NULL` đã khai báo. Không mặc định rằng một annotation hoặc giá trị mặc định trong Java sẽ luôn đồng bộ với `DEFAULT` trên database.

Với endpoint cập nhật (`PATCH`), “không có trường” thường có nghĩa **giữ nguyên giá trị cũ**, khác với việc chèn hàng mới. Không dùng quy tắc `DEFAULT` của `INSERT` để vô tình ghi đè dữ liệu trong `UPDATE`.

## 13. Những lỗi thường gặp và hướng điều tra

| Thông báo/triệu chứng | Khả năng liên quan | Cách kiểm tra |
|---|---|---|
| `ORA-01400: cannot insert NULL into ...` | Bỏ cột `NOT NULL` không có default, hoặc gửi `NULL` tường minh vào cột bắt buộc | Xem danh sách cột `INSERT`, giá trị bind, `NULLABLE` và `DATA_DEFAULT` |
| `ORA-00001: unique constraint violated` | Trùng khóa chính/unique | Đọc tên constraint và giá trị khóa; xem cơ chế sinh ID |
| `ORA-02290: check constraint violated` | Giá trị ngoài miền `CHECK` | Tra `USER_CONSTRAINTS` và giá trị thực tế |
| `ORA-12899: value too large for column` | Chuỗi vượt giới hạn byte/ký tự của cột | Xem DDL, `DATA_LENGTH`, `CHAR_USED`, đo `LENGTHB` |
| `ORA-01438` | Số vượt giới hạn precision của `NUMBER(p,s)` | Kiểm tra precision/scale và số đầu vào |
| `ORA-00947: not enough values` | Danh sách `VALUES` không khớp số cột mục tiêu | Dùng `INSERT INTO t (col1, col2) VALUES (...)` tường minh |
| `ORA-02296` khi đặt `NOT NULL` | Bảng hiện có hàng `NULL` ở cột đó | Đếm hàng vi phạm; lên phương án backfill |
| `ORA-00904` khi truy vấn metadata | Cột/view metadata không có ở phiên bản hoặc tên sai | Xem data dictionary theo release, không suy bảng dữ liệu bị lỗi |
| Có `DEFAULT 'NEW'` nhưng insert vẫn lỗi `NOT NULL` | Client truyền `NULL` rõ ràng | Phân biệt bỏ cột, `DEFAULT` và `NULL`; cân nhắc `DEFAULT ON NULL` |
| Ngày tạo hiển thị chỉ có ngày | `NLS_DATE_FORMAT` không hiển thị giờ | `TO_CHAR(created_at,'YYYY-MM-DD HH24:MI:SS')` |
| Bản ghi cũ không đổi sau `ALTER TABLE MODIFY DEFAULT` | Default mới áp dụng theo các thao tác tương lai, không đồng loạt sửa dữ liệu cũ | Phân biệt DDL default với kế hoạch `UPDATE` |
| Chèn chuỗi rỗng vào cột bắt buộc bị lỗi | Oracle xử lý chuỗi rỗng như `NULL` ở kiểu ký tự thường | Validate chuỗi đầu vào; phân biệt với chuỗi khoảng trắng |

Mỗi mã lỗi giúp khoanh vùng, nhưng không thay thế việc xem **SQL thực tế**, **giá trị bind**, **metadata** và **container/schema**. Ví dụ `ORA-01400` có thể xuất hiện vì một cột hoàn toàn khác cột mà người lập trình đang chú ý.

### Sơ đồ chẩn đoán INSERT không thành công

~~~mermaid
flowchart TD
    A["INSERT vào bảng báo lỗi"] --> B["Xác nhận PDB và schema đúng"]
    B --> C["Đọc USER_TAB_COLUMNS / ALL_TAB_COLUMNS"]
    C --> D{"Cột bị lỗi có NOT NULL?"}
    D -->|Có| E{"Client bỏ cột hay truyền NULL?"}
    E -->|Bỏ cột| F["Kiểm tra DATA_DEFAULT; nếu không có thì cần giá trị"]
    E -->|Truyền NULL| G["DEFAULT thường không thay NULL; cân nhắc validation / ON NULL"]
    D -->|Không| H["Kiểm tra CHECK, PK/UNIQUE, độ dài, precision"]
    F --> I["Sửa SQL/DDL theo hợp đồng dữ liệu"]
    G --> I
    H --> I
~~~

## 14. Bài thực hành tự kiểm tra

**Bước 1 — Tạo bảng.** Trong một PDB/schema thực hành, chạy `CREATE TABLE LAB_ORDERS` đã nêu ở phần 3. Ghi lại tên các cột và xác định cột nào bắt buộc do `NOT NULL` hoặc `PRIMARY KEY`.

**Bước 2 — Bỏ cột có DEFAULT.** Chèn `ORDER_ID = 301`, `CUSTOMER_CODE = 'CUS-301'`, `UNIT_PRICE = 100000` nhưng không gửi `STATUS`, `QUANTITY`, `CREATED_AT`, `NOTE`. Dự đoán rồi truy vấn các giá trị thực tế; tại sao `NOTE` là `NULL` còn `STATUS` là `NEW`?

**Bước 3 — Truyền NULL.** Ở câu chèn mới dùng `ORDER_ID = 302`, truyền `STATUS = NULL`. Viết ra lý do lệnh sẽ lỗi trên bảng `LAB_ORDERS` dù cột có mặc định. Không cần cố chạy liên tục câu lệnh cố ý gây lỗi trong script triển khai.

**Bước 4 — So sánh hai kiểu DEFAULT.** Tạo `LAB_DEFAULT_COMPARE`, chèn dữ liệu ID 1, 2, 3 và so sánh `STANDARD_DEFAULT` với `DEFAULT_WHEN_NULL`. Giải thích vì sao `DEFAULT ON NULL` chỉ nên dùng khi nghiệp vụ chấp nhận thay null bằng một mặc định.

**Bước 5 — Đọc metadata.** Truy vấn `USER_TAB_COLUMNS` và `USER_CONSTRAINTS`. Xác định biểu thức default, cột nullable, khóa chính và các `CHECK`. Đối chiếu với DDL đã chạy và chú ý việc tên constraint có thể được Oracle tự tạo.

**Bước 6 — Bảo vệ dữ liệu bằng CHECK.** Dự đoán kết quả chèn `QUANTITY = 0` hoặc `STATUS = 'DONE'`. Vì sao `DEFAULT` không sửa các giá trị tường minh trái `CHECK`?

**Bước 7 — Đổi DEFAULT.** Trong bảng thử, đổi `QUANTITY DEFAULT 2`. Trước khi thêm hàng mới, dự đoán liệu hàng `ORDER_ID = 301` có tự đổi `QUANTITY` thành 2 không. Chèn thêm một hàng mới không truyền quantity và so sánh.

**Bước 8 — Java/JDBC.** So sánh hai câu `INSERT`: một câu chỉ gửi ba cột `ORDER_ID`, `CUSTOMER_CODE`, `UNIT_PRICE`; câu còn lại có thêm `STATUS` nhưng `setNull`. Dự đoán câu nào thành công và giải thích bằng ràng buộc trong database.

**Bước 9 — Thiết kế mới.** Một bảng đăng ký tài khoản có `EMAIL` bắt buộc, `STATUS` mặc định `PENDING` và `CREATED_AT` mặc định thời điểm hiện tại. Hãy viết DDL và trả lời: `EMAIL` có nên `DEFAULT 'UNKNOWN'` để mọi câu chèn đều thành công không? `STATUS` nên dùng `DEFAULT` hay `DEFAULT ON NULL` trong API mà client có thể gửi `null`? Cần dựa vào hợp đồng nghiệp vụ trước khi chọn.

## 15. Ghi nhớ khi thiết kế bảng Oracle

| Muốn đạt điều gì? | Cơ chế phù hợp | Không nên nhầm với |
|---|---|---|
| Khai báo cột và kiểu dữ liệu | `CREATE TABLE` | Tự động kiểm tra mọi quy tắc nghiệp vụ |
| Điền giá trị khi không cung cấp cột | `DEFAULT` | Thay thế mọi `NULL` tường minh |
| Điền giá trị cả khi INSERT gửi `NULL` | `DEFAULT ON NULL` trên phiên bản hỗ trợ | Hàm hiển thị `NVL` |
| Bắt buộc cột có giá trị | `NOT NULL` | Tự tạo giá trị thay client |
| Mỗi hàng có mã khóa duy nhất | `PRIMARY KEY` | Sinh mã tự động |
| Tự sinh khóa số | `IDENTITY`/sequence phù hợp | `DEFAULT 1` |
| Giới hạn miền dữ liệu | `CHECK` | Tự sinh giá trị trong miền |
| Xác minh thiết kế đang chạy | `USER_TAB_COLUMNS`, `USER_CONSTRAINTS` | Chỉ dựa vào bản DDL lưu ở tài liệu |
| Chèn dữ liệu từ Java | `PreparedStatement` và bind đúng kiểu | Giả định bind `NULL` sẽ kích hoạt `DEFAULT` |

Một thiết kế vững chắc tách bạch **giá trị ứng dụng phải cung cấp**, **giá trị Oracle có thể mặc định** và **giá trị database tuyệt đối không cho phép**. Cách thực hành tốt là viết DDL có ý nghĩa rõ ràng, chèn thử cả trường hợp bỏ cột lẫn truyền `NULL`, đọc metadata để xác minh, và thiết kế API/JDBC nhất quán với ràng buộc. Khi đó dữ liệu vẫn được bảo vệ ngay cả khi có nhiều công cụ, dịch vụ hoặc chương trình khác nhau cùng ghi vào Oracle.
