# Sinh khóa bằng sequence, identity và lấy khóa vừa tạo trong Oracle

## 1. Vì sao cần cơ chế sinh khóa?

Khi thêm một khách hàng, đơn hàng hoặc giao dịch mới, ứng dụng thường cần một giá trị định danh duy nhất để phân biệt hàng đó và liên kết nó với các bảng khác. Ví dụ, mỗi đơn hàng cần `ORDER_ID`; các dòng chi tiết đơn hàng sẽ tham chiếu `ORDER_ID` này qua khóa ngoại.

Trong Oracle, hai cơ chế phổ biến để sinh khóa số tự tăng là:

- **Sequence:** một đối tượng database cấp các giá trị số theo yêu cầu. Câu INSERT chủ động gọi `sequence_name.NEXTVAL`.
- **Identity column:** một cột được khai báo tự sinh giá trị; Oracle quản lý bộ sinh số gắn với cột đó. Ứng dụng thường bỏ cột identity khỏi danh sách INSERT.

Sau khi INSERT, ứng dụng có thể cần lấy lại khóa vừa được sinh để ghi các bảng con hoặc trả về API. Oracle hỗ trợ `RETURNING ... INTO`; sequence cũng có `CURRVAL` trong cùng session sau khi đã gọi `NEXTVAL`. Java/JDBC có các cách lấy generated key thông qua driver.

Ví dụ với sequence:

```sql
INSERT INTO orders (
    order_id,
    customer_id,
    order_date
)
VALUES (
    order_seq.NEXTVAL,
    501,
    SYSDATE
)
RETURNING order_id INTO :new_order_id;
```

Ví dụ với identity:

```sql
INSERT INTO orders (
    customer_id,
    order_date
)
VALUES (
    501,
    SYSDATE
)
RETURNING order_id INTO :new_order_id;
```

Trong cả hai trường hợp, khóa mới được lấy trực tiếp từ hàng vừa INSERT.

Bài học thuộc chương **Thay đổi dữ liệu**, tập trung vào cách tạo sequence, khai báo identity, lựa chọn giữa hai cơ chế, lấy khóa vừa sinh, sử dụng trong SQL/PLSQL/JDBC, xử lý transaction và các lưu ý về tính duy nhất, khoảng trống trong dãy số và hiệu năng.

## 2. Khóa chính và giá trị tự sinh là hai khái niệm khác nhau

Một cột ID thường được dùng làm khóa chính, nhưng việc sinh số và việc bảo đảm tính toàn vẹn là hai trách nhiệm riêng:

- **Sequence/identity** cấp giá trị cho cột.
- **PRIMARY KEY** bảo đảm giá trị không NULL và không trùng trong bảng.

Ví dụ:

```sql
CREATE TABLE customers (
    customer_id NUMBER
        CONSTRAINT pk_customers PRIMARY KEY,
    customer_name VARCHAR2(100) NOT NULL
);
```

Cột `CUSTOMER_ID` là khóa chính, nhưng bảng chưa có cơ chế tự sinh giá trị. Người INSERT phải truyền ID hoặc bổ sung sequence/identity.

Một sequence không tự tạo constraint trên bảng. Nếu dùng sequence để cấp ID, vẫn nên khai báo PRIMARY KEY:

```sql
CREATE SEQUENCE customer_seq
    START WITH 1
    INCREMENT BY 1
    NOCYCLE
    CACHE 50;

CREATE TABLE customers (
    customer_id NUMBER
        CONSTRAINT pk_customers PRIMARY KEY,
    customer_name VARCHAR2(100) NOT NULL
);
```

Nếu sequence bị cấu hình `CYCLE`, giá trị có thể quay lại một vùng số đã dùng; constraint khóa chính sẽ ngăn trùng nhưng INSERT có thể thất bại. Với sequence dùng cho ID, thông thường chọn `NOCYCLE`.

## 3. Sequence là gì?

Sequence là một đối tượng độc lập trong schema Oracle, chuyên cấp các giá trị số theo yêu cầu. Nhiều session có thể cùng sử dụng một sequence mà không phải tự khóa bảng để tìm số tiếp theo.

Một sequence có thể được dùng cho:

- Khóa chính của một hoặc nhiều bảng.
- Số tham chiếu kỹ thuật.
- Số thứ tự sự kiện.
- Các mã số cần cấp phát đồng thời.

Sequence không tự biết bảng nào đang sử dụng nó. Một sequence có thể được tham chiếu bởi nhiều câu lệnh và nhiều bảng; vì vậy, nếu cần phạm vi duy nhất theo từng bảng hoặc từng loại đối tượng, phải thiết kế quy tắc riêng.

### 3.1. Tạo sequence

Cú pháp minh họa:

```sql
CREATE SEQUENCE order_seq
    START WITH 1000
    INCREMENT BY 1
    MINVALUE 1
    NOMAXVALUE
    NOCYCLE
    CACHE 50;
```

Ý nghĩa:

| Thuộc tính | Ý nghĩa |
|---|---|
| `START WITH 1000` | Giá trị được cấp đầu tiên là 1000 |
| `INCREMENT BY 1` | Mỗi lần cấp tăng một đơn vị |
| `MINVALUE 1` | Giá trị nhỏ nhất của sequence tăng |
| `NOMAXVALUE` | Không đặt giới hạn MAXVALUE tường minh; Oracle dùng giới hạn mặc định cho chiều tăng |
| `NOCYCLE` | Không quay vòng khi chạm giới hạn |
| `CACHE 50` | Cache trước một nhóm giá trị để giảm chi phí cấp phát |

Đối với sequence tăng dần, Oracle có các giá trị mặc định cho MINVALUE/MAXVALUE nếu không khai báo. Khi thiết kế hệ thống, nên ghi rõ các thuộc tính quan trọng để người bảo trì hiểu quy tắc cấp số.

### 3.2. Các thuộc tính thường gặp

| Thuộc tính | Tác dụng |
|---|---|
| `START WITH n` | Điểm bắt đầu |
| `INCREMENT BY n` | Bước tăng hoặc giảm; không được bằng 0 |
| `MINVALUE n` / `NOMINVALUE` | Giới hạn nhỏ nhất hoặc dùng mặc định |
| `MAXVALUE n` / `NOMAXVALUE` | Giới hạn lớn nhất hoặc dùng mặc định |
| `CYCLE` / `NOCYCLE` | Có hoặc không quay vòng khi đạt giới hạn |
| `CACHE n` / `NOCACHE` | Số giá trị được cache hoặc không cache |
| `ORDER` / `NOORDER` | Có hoặc không bảo đảm thứ tự cấp phát theo yêu cầu của sequence |

`CACHE` thường cải thiện hiệu năng khi nhiều session cùng lấy số. `NOCACHE` tránh việc dự trữ một nhóm số trong cache, nhưng có thể làm tăng chi phí cấp phát. Không nên chọn chỉ theo cảm tính; hãy dựa trên tải ghi và yêu cầu vận hành.

`ORDER` liên quan thứ tự các yêu cầu lấy giá trị, đặc biệt trong môi trường nhiều instance; nó không bảo đảm thứ tự commit của transaction hoặc thứ tự hàng được đọc nếu truy vấn không có `ORDER BY`. `NOORDER` thường phù hợp khi không có yêu cầu thứ tự cấp số nghiêm ngặt.

### 3.3. Kiểm tra sequence trong data dictionary

Các sequence thuộc schema hiện tại có thể xem qua `USER_SEQUENCES`:

```sql
SELECT sequence_name,
       min_value,
       max_value,
       increment_by,
       cycle_flag,
       order_flag,
       cache_size,
       last_number
FROM user_sequences
WHERE sequence_name = 'ORDER_SEQ';
```

`LAST_NUMBER` trong metadata không nên được hiểu đơn giản là giá trị `NEXTVAL` tiếp theo mà session sẽ nhận. Với sequence có cache, metadata có thể phản ánh mốc liên quan đến vùng giá trị đã cache, không phải một phép đọc chính xác giá trị kế tiếp trong bộ nhớ.

Nếu cần xem sequence ở schema khác và có quyền, có thể dùng `ALL_SEQUENCES`; quyền quản trị rộng hơn có thể xem `DBA_SEQUENCES`.

## 4. NEXTVAL và CURRVAL

Sequence cung cấp hai pseudocolumn:

- `NEXTVAL`: lấy và cấp giá trị tiếp theo của sequence.
- `CURRVAL`: đọc giá trị gần nhất mà **session hiện tại** đã lấy từ sequence đó.

### 4.1. Lấy giá trị tiếp theo bằng NEXTVAL

```sql
SELECT order_seq.NEXTVAL
FROM dual;
```

Mỗi lần tham chiếu `NEXTVAL` trong ngữ cảnh cấp phát phù hợp, sequence tiến theo `INCREMENT BY` và trả giá trị mới.

Nếu sequence bắt đầu tại 1000 và tăng một:

| Lần gọi | Giá trị minh họa |
|---:|---:|
| 1 | 1000 |
| 2 | 1001 |
| 3 | 1002 |

Giá trị thực tế còn phụ thuộc sequence đã được session khác hoặc câu lệnh khác sử dụng hay chưa.

### 4.2. Đọc CURRVAL

```sql
SELECT order_seq.CURRVAL
FROM dual;
```

`CURRVAL` chỉ dùng được sau khi session hiện tại đã gọi `NEXTVAL` ít nhất một lần cho sequence đó. Nếu chưa gọi, Oracle báo:

```text
ORA-08002: sequence ORDER_SEQ.CURRVAL is not yet defined in this session
```

Ví dụ hợp lệ:

```sql
SELECT order_seq.NEXTVAL FROM dual;
SELECT order_seq.CURRVAL FROM dual;
```

Hai câu trên phải được chạy trong cùng một database session. Nếu mở một connection khác, session mới chưa có CURRVAL của sequence cho đến khi chính nó gọi NEXTVAL.

### 4.3. CURRVAL không phải khóa vừa tạo của toàn database

Giả sử:

1. Session A gọi `ORDER_SEQ.NEXTVAL` và nhận 1000.
2. Session B gọi `ORDER_SEQ.NEXTVAL` và nhận 1001.
3. Session A đọc `ORDER_SEQ.CURRVAL`.

Session A vẫn nhận 1000. `CURRVAL` không đổi thành 1001 chỉ vì session B vừa lấy giá trị mới.

Đây là lý do `CURRVAL` an toàn để đọc giá trị sequence đã lấy trong session của chính mình, nhưng không nên dùng nó từ một connection khác hoặc connection pool tùy ý.

## 5. INSERT với sequence

### 5.1. Cấp khóa trong VALUES

```sql
INSERT INTO orders (
    order_id,
    customer_id,
    order_date,
    status
)
VALUES (
    order_seq.NEXTVAL,
    501,
    SYSDATE,
    'NEW'
);
```

Oracle lấy giá trị mới từ `ORDER_SEQ` để gán cho `ORDER_ID`. Không cần SELECT NEXTVAL trước nếu chỉ cần insert một hàng và không cần biết khóa trước khi insert.

### 5.2. Lấy CURRVAL sau INSERT trong cùng session

```sql
INSERT INTO orders (
    order_id,
    customer_id,
    order_date
)
VALUES (
    order_seq.NEXTVAL,
    501,
    SYSDATE
);

SELECT order_seq.CURRVAL AS new_order_id
FROM dual;
```

Vì INSERT đã gọi `NEXTVAL` trong session hiện tại, `CURRVAL` trả về giá trị sequence mà câu INSERT vừa dùng, miễn là không có câu lệnh nào khác trong cùng session gọi tiếp `NEXTVAL` trên chính sequence đó trước khi đọc CURRVAL.

Trong ứng dụng có thể có nhiều bước và nhiều helper cùng dùng sequence, nên `RETURNING` thường rõ ràng hơn để lấy khóa từ đúng hàng INSERT.

### 5.3. Cấp khóa cho nhiều hàng bằng INSERT ... SELECT

```sql
INSERT INTO order_archive (
    archive_id,
    order_id,
    archived_at
)
SELECT order_archive_seq.NEXTVAL,
       o.order_id,
       SYSTIMESTAMP
FROM orders o
WHERE o.status = 'CLOSED';
```

Sequence có thể cấp một giá trị cho mỗi hàng được chèn trong dạng INSERT ... SELECT. Hãy xem số hàng nguồn trước khi chạy và bảo đảm bảng đích có constraint phù hợp.

### 5.4. Không lấy ID bằng MAX(ID) + 1

Không nên viết:

```sql
-- Cách không an toàn khi có nhiều session:
SELECT MAX(order_id) + 1
FROM orders;
```

Hai session có thể cùng đọc một MAX rồi cùng tính ra một giá trị kế tiếp. Khi cả hai INSERT, một session có thể vi phạm khóa chính hoặc tạo xung đột.

Sequence được thiết kế để cấp số đồng thời mà không phải dựa vào phép đọc MAX trên bảng.

## 6. Lấy khóa vừa INSERT bằng RETURNING INTO

`RETURNING ... INTO` là cách trực tiếp để lấy giá trị cột từ hàng vừa được DML tác động. Với khóa do sequence hoặc identity sinh ra, đây thường là lựa chọn rõ ràng.

### 6.1. INSERT với sequence và RETURNING

```sql
INSERT INTO orders (
    order_id,
    customer_id,
    order_date,
    status
)
VALUES (
    order_seq.NEXTVAL,
    501,
    SYSDATE,
    'NEW'
)
RETURNING order_id INTO :new_order_id;
```

`:new_order_id` là bind variable do client hoặc ứng dụng đăng ký để nhận giá trị. Trong SQL*Plus/SQLcl có thể minh họa:

```sql
VARIABLE new_order_id NUMBER

INSERT INTO orders (
    order_id,
    customer_id,
    order_date
)
VALUES (
    order_seq.NEXTVAL,
    501,
    SYSDATE
)
RETURNING order_id INTO :new_order_id;

PRINT new_order_id
```

### 6.2. RETURNING trong PL/SQL

```sql
DECLARE
    v_order_id orders.order_id%TYPE;
BEGIN
    INSERT INTO orders (
        order_id,
        customer_id,
        order_date,
        status
    )
    VALUES (
        order_seq.NEXTVAL,
        501,
        SYSDATE,
        'NEW'
    )
    RETURNING order_id INTO v_order_id;

    DBMS_OUTPUT.PUT_LINE('New order ID: ' || v_order_id);
END;
/
```

Biến `v_order_id` nhận khóa được gán cho đúng hàng vừa chèn. PL/SQL block không tự COMMIT; transaction vẫn thuộc quyền kiểm soát của caller.

### 6.3. RETURNING nhiều cột

Có thể nhận nhiều giá trị:

```sql
DECLARE
    v_order_id orders.order_id%TYPE;
    v_created_at orders.order_date%TYPE;
BEGIN
    INSERT INTO orders (
        order_id,
        customer_id,
        order_date,
        status
    )
    VALUES (
        order_seq.NEXTVAL,
        501,
        SYSDATE,
        'NEW'
    )
    RETURNING order_id, order_date
    INTO v_order_id, v_created_at;

    DBMS_OUTPUT.PUT_LINE(
        'Order=' || v_order_id ||
        ', created=' || TO_CHAR(v_created_at, 'YYYY-MM-DD HH24:MI:SS')
    );
END;
/
```

Số biểu thức trong `RETURNING` phải tương ứng với số biến trong `INTO`.

### 6.4. RETURNING không đồng nghĩa COMMIT

Sau INSERT và RETURNING, ứng dụng có thể dùng khóa vừa nhận để chèn các bảng con trong **cùng transaction**:

```sql
INSERT INTO orders (
    order_id,
    customer_id,
    order_date
)
VALUES (
    order_seq.NEXTVAL,
    501,
    SYSDATE
)
RETURNING order_id INTO :new_order_id;

INSERT INTO order_items (
    order_id,
    product_id,
    quantity
)
VALUES (
    :new_order_id,
    2001,
    2
);
```

Nếu INSERT chi tiết thất bại, có thể ROLLBACK cả đơn hàng và chi tiết chưa commit. Giá trị sequence đã cấp vẫn bị tiêu thụ; rollback không trả số đó lại sequence.

## 7. Identity column là gì?

Identity column là cột được Oracle cấu hình tự sinh giá trị. Cơ chế này được hỗ trợ từ **Oracle Database 12c Release 1 (12.1)**.

Khi tạo bảng có identity, ứng dụng thường không cần tạo sequence riêng hoặc gọi `NEXTVAL` trong INSERT. Oracle quản lý bộ sinh giá trị gắn với cột identity.

### 7.1. Tạo bảng với GENERATED ALWAYS AS IDENTITY

```sql
CREATE TABLE customers (
    customer_id NUMBER
        GENERATED ALWAYS AS IDENTITY,
    customer_name VARCHAR2(100) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP,
    CONSTRAINT pk_customers PRIMARY KEY (customer_id)
);
```

Oracle tự cấp `CUSTOMER_ID` khi INSERT. Ứng dụng không được tự cung cấp một giá trị tường minh cho cột `GENERATED ALWAYS` theo cách INSERT thông thường.

INSERT:

```sql
INSERT INTO customers (customer_name)
VALUES ('An Nguyen');
```

Không đưa `CUSTOMER_ID` vào danh sách cột; Oracle tự sinh giá trị.

### 7.2. GENERATED BY DEFAULT AS IDENTITY

```sql
CREATE TABLE products (
    product_id NUMBER
        GENERATED BY DEFAULT AS IDENTITY,
    product_name VARCHAR2(100) NOT NULL,
    CONSTRAINT pk_products PRIMARY KEY (product_id)
);
```

Với `BY DEFAULT`:

- Nếu INSERT bỏ cột `PRODUCT_ID`, Oracle sinh giá trị.
- Nếu INSERT truyền một giá trị tường minh, Oracle sử dụng giá trị được truyền.
- Nếu truyền NULL tường minh, NULL được xử lý như giá trị đã cung cấp; nếu cột có NOT NULL/PRIMARY KEY, thao tác có thể thất bại thay vì tự sinh số.

Ví dụ bỏ cột:

```sql
INSERT INTO products (product_name)
VALUES ('Keyboard');
```

Ví dụ truyền ID:

```sql
INSERT INTO products (product_id, product_name)
VALUES (9001, 'Mouse');
```

Chỉ cho phép ứng dụng truyền ID khi có lý do quản trị dữ liệu rõ ràng. Việc trộn ID thủ công với ID tự sinh có thể làm dữ liệu khó đồng bộ nếu giá trị tường minh nằm phía trước hoặc trùng vùng sequence đang cấp.

### 7.3. GENERATED BY DEFAULT ON NULL AS IDENTITY

```sql
CREATE TABLE tickets (
    ticket_id NUMBER
        GENERATED BY DEFAULT ON NULL AS IDENTITY,
    title VARCHAR2(200) NOT NULL,
    CONSTRAINT pk_tickets PRIMARY KEY (ticket_id)
);
```

Với `BY DEFAULT ON NULL`:

- Bỏ cột `TICKET_ID`: Oracle tự sinh.
- Truyền NULL cho `TICKET_ID`: Oracle cũng tự sinh.
- Truyền một số tường minh: Oracle dùng số đó.

Ví dụ:

```sql
-- Oracle tự sinh ticket_id:
INSERT INTO tickets (title)
VALUES ('Cannot sign in');

-- NULL tường minh cũng kích hoạt sinh giá trị:
INSERT INTO tickets (ticket_id, title)
VALUES (NULL, 'Payment issue');
```

### 7.4. So sánh ba chế độ identity

| Chế độ | Bỏ cột khỏi INSERT | Truyền NULL tường minh | Truyền số tường minh |
|---|---|---|---|
| `GENERATED ALWAYS` | Oracle sinh | Oracle sinh theo cơ chế identity | Bị từ chối trong INSERT thông thường |
| `GENERATED BY DEFAULT` | Oracle sinh | NULL được xem là giá trị đã truyền; constraint có thể từ chối | Chấp nhận giá trị truyền |
| `GENERATED BY DEFAULT ON NULL` | Oracle sinh | Oracle sinh | Chấp nhận giá trị truyền |

Nếu ứng dụng không cần tự cấp ID, `GENERATED ALWAYS` thường thể hiện rõ nhất ý định để database quản lý khóa.

## 8. Tùy chỉnh identity options

Identity column có các tùy chọn của bộ sinh số:

```sql
CREATE TABLE invoices (
    invoice_id NUMBER
        GENERATED ALWAYS AS IDENTITY (
            START WITH 10000
            INCREMENT BY 1
            CACHE 100
            NOCYCLE
        ),
    customer_id NUMBER NOT NULL,
    invoice_date DATE DEFAULT SYSDATE,
    CONSTRAINT pk_invoices PRIMARY KEY (invoice_id)
);
```

Các tùy chọn như `START WITH`, `INCREMENT BY`, `CACHE`, `NOCYCLE`, `ORDER` có ý nghĩa tương tự cấu hình sequence. Hãy chọn theo yêu cầu của hệ thống, không giả định identity tạo dãy liên tục.

Identity sử dụng một sequence do Oracle quản lý nội bộ. Tên sequence nội bộ có thể xuất hiện trong metadata, thường có dạng tên sinh tự động. Không tham chiếu sequence nội bộ đó trực tiếp trong ứng dụng; tên và cách quản lý là chi tiết triển khai của Oracle.

### 8.1. Xem metadata identity

Trong schema hiện tại:

```sql
SELECT table_name,
       column_name,
       generation_type,
       sequence_name,
       identity_options
FROM user_tab_identity_cols
WHERE table_name = 'INVOICES';
```

`GENERATION_TYPE` cho biết chế độ sinh, còn `IDENTITY_OPTIONS` mô tả các tùy chọn. Tên sequence được hiển thị phục vụ tra cứu metadata; không nên dùng nó như một API ổn định.

Nếu cần xem identity ở schema khác và có quyền, có thể dùng `ALL_TAB_IDENTITY_COLS`; quyền quản trị phù hợp có thể xem `DBA_TAB_IDENTITY_COLS`.

## 9. INSERT và lấy khóa vừa tạo từ identity

### 9.1. Bỏ identity column khỏi danh sách INSERT

```sql
INSERT INTO customers (
    customer_name,
    created_at
)
VALUES (
    'Binh Tran',
    SYSTIMESTAMP
);
```

Oracle tự sinh `CUSTOMER_ID`. Cách viết này không phụ thuộc tên sequence nội bộ.

### 9.2. Lấy khóa bằng RETURNING INTO

```sql
DECLARE
    v_customer_id customers.customer_id%TYPE;
BEGIN
    INSERT INTO customers (customer_name)
    VALUES ('Chi Le')
    RETURNING customer_id INTO v_customer_id;

    DBMS_OUTPUT.PUT_LINE('New customer ID: ' || v_customer_id);
END;
/
```

`RETURNING` hoạt động trực tiếp trên cột identity vừa được sinh, vì vậy đây là cách rõ ràng để lấy ID cho bước tiếp theo.

### 9.3. Dùng DEFAULT tường minh

Có thể yêu cầu Oracle dùng default/generator của cột:

```sql
INSERT INTO customers (customer_id, customer_name)
VALUES (DEFAULT, 'Dung Pham');
```

`DEFAULT` yêu cầu dùng giá trị mặc định/generation của cột. Với identity, đây là cách tường minh nếu bạn muốn giữ cột trong danh sách INSERT nhưng không tự cung cấp giá trị.

## 10. Chọn sequence hay identity?

| Tiêu chí | Sequence | Identity column |
|---|---|---|
| Phiên bản | Có từ các phiên bản Oracle lâu đời | Từ Oracle 12c Release 1 |
| Đối tượng | Sequence độc lập | Cột gắn với generator do Oracle quản lý |
| INSERT | Thường gọi `seq.NEXTVAL` | Thường bỏ cột identity |
| Có thể dùng cho nhiều bảng | Có | Mỗi identity gắn với cột của bảng |
| Kiểm soát cấp số | Linh hoạt, dùng trực tiếp NEXTVAL/CURRVAL | Qua identity options và DML trên cột |
| Lấy khóa sau INSERT | `RETURNING`, hoặc CURRVAL trong cùng session | `RETURNING` hoặc JDBC generated keys |
| Phù hợp schema cũ | Rất phù hợp | Cần Oracle 12c+ |
| Tạo trigger cấp ID | Có thể dùng trong mẫu legacy | Thường không cần trigger cho ID |

### 10.1. Chọn sequence khi

- Hệ thống cần hỗ trợ phiên bản Oracle trước 12c.
- Một sequence cần cấp số cho nhiều bảng hoặc nhiều đối tượng.
- Cần lấy `NEXTVAL` trước INSERT để dùng trong nhiều thao tác cùng transaction.
- Có quy tắc cấp số riêng, chẳng hạn nhiều loại bản ghi dùng chung một dãy.
- Ứng dụng/schema hiện tại đã dùng sequence và cần giữ mô hình đó.

### 10.2. Chọn identity khi

- Mỗi bảng có một cột khóa tự sinh riêng.
- Database từ Oracle 12c Release 1 trở lên.
- Muốn khai báo ý định sinh khóa ngay trong DDL của bảng.
- Không cần ứng dụng tham chiếu sequence nội bộ.
- Muốn tránh tạo và bảo trì trigger chỉ để gán ID.

Identity thường đơn giản cho bảng mới. Sequence linh hoạt hơn khi generator là một tài nguyên dùng chung hoặc cần thao tác trực tiếp.

## 11. Trigger và sequence trong schema legacy

Trước khi có identity column, một mẫu phổ biến là sequence kết hợp `BEFORE INSERT` trigger:

```sql
CREATE SEQUENCE customer_seq
    START WITH 1
    INCREMENT BY 1
    NOCYCLE
    CACHE 50;
```

Trigger:

```sql
CREATE OR REPLACE TRIGGER customers_bi
BEFORE INSERT ON customers
FOR EACH ROW
BEGIN
    IF :NEW.customer_id IS NULL THEN
        :NEW.customer_id := customer_seq.NEXTVAL;
    END IF;
END;
/
```

Nếu INSERT không truyền `CUSTOMER_ID` hoặc truyền NULL, trigger lấy NEXTVAL và gán cho `:NEW.CUSTOMER_ID`.

### 11.1. Trigger có thể gây khó khăn gì?

- Cơ chế sinh ID bị ẩn trong trigger; người đọc INSERT không thấy nguồn ID.
- Debug phải kiểm tra cả bảng, sequence và trigger.
- Nếu ứng dụng tự truyền ID, cần quy định rõ trigger có ghi đè hay giữ giá trị đó.
- Trigger có thể bị disable trong một số quy trình import/bảo trì.
- Logic cấp ID có thể bị lặp ở nhiều trigger nếu thiết kế thiếu thống nhất.

Với bảng mới trên Oracle 12c+, identity có thể giảm nhu cầu viết trigger riêng cho ID. Với schema cũ, sequence + trigger vẫn là mô hình hợp lệ và phổ biến.

### 11.2. Không tạo trigger và identity cùng sinh một cột

Nếu cột đã là identity, không thêm trigger khác tiếp tục gán ID cho cùng cột trừ khi có thiết kế đặc biệt được kiểm soát. Hai cơ chế sinh cùng một cột dễ gây xung đột hoặc hành vi khó dự đoán.

## 12. Lấy khóa vừa tạo trong Java/JDBC

Ứng dụng Java thường cần ID của hàng cha để chèn các hàng con. Ví dụ: INSERT một đơn hàng, nhận `ORDER_ID`, rồi INSERT các dòng `ORDER_ITEMS`.

### 12.1. JDBC getGeneratedKeys với tên cột

Oracle JDBC driver hỗ trợ cơ chế generated keys theo cách triển khai của driver. Một mẫu thường dùng là yêu cầu driver trả về cột khóa:

```java
String sql =
    "INSERT INTO orders (order_id, customer_id, status) " +
    "VALUES (order_seq.NEXTVAL, ?, ?)";

try (PreparedStatement ps =
         connection.prepareStatement(sql, new String[] {"ORDER_ID"})) {
    ps.setLong(1, customerId);
    ps.setString(2, "NEW");

    int rows = ps.executeUpdate();
    if (rows != 1) {
        throw new IllegalStateException("Expected one inserted order");
    }

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException("No generated order ID returned");
        }

        BigDecimal orderId = keys.getBigDecimal(1);
        // Dùng orderId để chèn ORDER_ITEMS trong cùng transaction.
    }
}
```

Mẫu trên cần Oracle JDBC driver có hỗ trợ generated-key retrieval cho câu lệnh và phiên bản đang dùng. Truyền tên cột khóa trong `prepareStatement` giúp driver biết cột nào cần trả về. Hãy kiểm tra tài liệu driver/phiên bản thực tế, đặc biệt khi dùng identity hoặc câu INSERT phức tạp.

### 12.2. RETURNING INTO qua PL/SQL block

Một lựa chọn rõ ràng khác là dùng `CallableStatement` gọi một PL/SQL block có `RETURNING INTO`:

```java
String plsql = """
    BEGIN
        INSERT INTO orders (
            order_id,
            customer_id,
            status
        )
        VALUES (
            order_seq.NEXTVAL,
            ?,
            ?
        )
        RETURNING order_id INTO ?;
    END;
    """;

try (CallableStatement cs = connection.prepareCall(plsql)) {
    cs.setLong(1, customerId);
    cs.setString(2, "NEW");
    cs.registerOutParameter(3, java.sql.Types.NUMERIC);

    cs.execute();

    BigDecimal orderId = cs.getBigDecimal(3);
    // Dùng orderId cho các INSERT tiếp theo.
}
```

Text block yêu cầu Java 15 trở lên; với Java cũ hơn, tạo chuỗi PL/SQL bằng cách nối các dòng. Ví dụ giả định cột `ORDER_ID` là NUMBER và driver hỗ trợ bind OUT kiểu NUMERIC.

Với identity, bỏ `ORDER_ID` khỏi danh sách INSERT nhưng vẫn `RETURNING order_id INTO ?`:

```java
String plsql = """
    BEGIN
        INSERT INTO orders (customer_id, status)
        VALUES (?, ?)
        RETURNING order_id INTO ?;
    END;
    """;
```

### 12.3. CURRVAL qua cùng connection

Nếu câu INSERT dùng `ORDER_SEQ.NEXTVAL`, có thể chạy:

```java
try (Statement st = connection.createStatement();
     ResultSet rs = st.executeQuery(
         "SELECT order_seq.CURRVAL FROM dual")) {
    if (rs.next()) {
        BigDecimal orderId = rs.getBigDecimal(1);
    }
}
```

Điều kiện bắt buộc: câu INSERT và câu SELECT CURRVAL phải dùng **cùng một database connection/session**, và không có thao tác khác trong session lấy NEXTVAL trên sequence đó xen giữa. Trong connection pool, không lấy CURRVAL bằng cách mượn một connection mới.

Đối với một hàng INSERT, `RETURNING` thường ít phụ thuộc trạng thái session hơn và gắn khóa trả về trực tiếp với hàng vừa chèn.

### 12.4. Transaction khi chèn hàng cha và hàng con

```java
connection.setAutoCommit(false);

try {
    BigDecimal orderId = insertOrderAndGetId(connection, customerId);

    insertOrderItem(connection, orderId, productId, quantity);

    connection.commit();
} catch (Exception ex) {
    connection.rollback();
    throw ex;
}
```

Đây là cấu trúc minh họa. Các hàm `insertOrderAndGetId` và `insertOrderItem` phải dùng cùng connection. Nếu bước chèn chi tiết thất bại, rollback sẽ hủy cả đơn hàng chưa commit. Sequence vẫn tiêu thụ giá trị đã cấp.

## 13. Sequence không bảo đảm dãy số liên tục

Một hiểu lầm phổ biến là ID phải tăng `1, 2, 3, 4, 5` không có khoảng trống. Sequence và identity chủ yếu cung cấp giá trị có khả năng duy nhất, không phải hệ thống đánh số liên tục không mất số.

### 13.1. Rollback không trả NEXTVAL

```sql
INSERT INTO orders (order_id, customer_id)
VALUES (order_seq.NEXTVAL, 501);

ROLLBACK;
```

Hàng INSERT bị rollback, nhưng giá trị NEXTVAL đã cấp vẫn bị tiêu thụ. Lần tiếp theo không lấy lại giá trị đó.

### 13.2. Transaction lỗi sau khi lấy số

Sequence có thể đã cấp số trước khi INSERT thất bại do:

- Vi phạm khóa chính.
- Vi phạm CHECK hoặc NOT NULL.
- Trigger lỗi.
- Transaction bị rollback.
- Ứng dụng lấy NEXTVAL nhưng sau đó không INSERT.

Số đã cấp không được hoàn lại.

### 13.3. CACHE và sự cố instance

Khi dùng `CACHE`, Oracle dự trữ trước một nhóm giá trị. Nếu instance dừng bất thường, các giá trị đã cache nhưng chưa dùng có thể bị bỏ qua khi khởi động lại. Vì vậy có thể xuất hiện khoảng trống lớn hơn một đơn vị.

### 13.4. Nhiều session lấy số đồng thời

Các session có thể lấy sequence values theo thứ tự khác với thứ tự INSERT hoàn tất hoặc COMMIT. ID nhỏ hơn không nhất thiết có thời điểm commit sớm hơn ID lớn hơn.

### 13.5. Không dùng sequence làm số hóa đơn liên tục nếu luật yêu cầu gapless

Nếu nghiệp vụ hoặc quy định cần số chứng từ liên tục, không được giả định sequence đáp ứng yêu cầu đó. Cần một quy trình đánh số nghiệp vụ có kiểm soát, khóa và xử lý hủy/void theo quy định áp dụng. Thiết kế này khác với khóa kỹ thuật của bảng và có thể có chi phí đồng thời đáng kể.

## 14. Sequence và identity trong môi trường nhiều session

Sequence được thiết kế để nhiều session có thể lấy giá trị mà không cần tự khóa bảng để tìm MAX(ID). Với sequence không quay vòng, các giá trị cấp ra không bị lặp trong phạm vi sequence theo cấu hình và trạng thái của nó.

### 14.1. Tính duy nhất không đồng nghĩa thứ tự commit

Giả sử:

1. Session A lấy ID 100.
2. Session B lấy ID 101.
3. Session B INSERT và COMMIT.
4. Session A INSERT nhưng chờ lâu rồi mới COMMIT.

Hàng có ID 101 có thể được commit trước hàng ID 100. Vì vậy, không dùng ID để suy ra chính xác thứ tự thời gian commit.

Nếu cần thời điểm tạo, lưu cột `CREATED_AT` với timestamp phù hợp. Nếu cần thứ tự sự kiện, lưu một thuộc tính thời gian/số thứ tự nghiệp vụ được định nghĩa riêng.

### 14.2. ORDER và NOORDER

- `NOORDER` không bảo đảm thứ tự cấp phát toàn cục theo thời điểm yêu cầu; thường cho phép hiệu năng tốt hơn.
- `ORDER` bảo đảm thứ tự cấp giá trị theo yêu cầu sequence trong phạm vi semantics của Oracle, nhưng không bảo đảm thứ tự transaction commit và có thể làm giảm khả năng mở rộng.

Chỉ dùng ORDER khi có yêu cầu thực sự về thứ tự cấp số. Nếu mục tiêu là ID duy nhất, thường không cần ORDER.

### 14.3. CACHE và NOCACHE

| Cấu hình | Đặc điểm |
|---|---|
| `CACHE n` | Dự trữ trước n giá trị; thường giảm chi phí cấp số và tăng hiệu năng |
| `NOCACHE` | Không cache nhóm giá trị; có thể tăng chi phí cấp phát và vẫn không bảo đảm gapless |

`NOCACHE` không làm sequence trở thành bộ đánh số không mất số. Rollback và các trường hợp lấy số nhưng không dùng vẫn tạo khoảng trống.

## 15. Thay đổi và quản lý sequence

### 15.1. Thay đổi thuộc tính sequence

```sql
ALTER SEQUENCE order_seq
    INCREMENT BY 1
    CACHE 100
    NOCYCLE;
```

`ALTER SEQUENCE` thay đổi các thuộc tính được phép sửa của sequence. Không phải mọi thuộc tính khởi tạo đều có thể thay đổi theo cùng cách; nếu cần đổi điểm bắt đầu hoặc tái cấu hình lớn, hãy xem tài liệu phiên bản Oracle và quy trình triển khai.

Không thay đổi sequence đang được nhiều ứng dụng sử dụng mà chưa đánh giá tác động.

### 15.2. Xóa sequence

```sql
DROP SEQUENCE order_seq;
```

Chỉ xóa khi đã xác nhận không còn trigger, câu SQL, job hoặc ứng dụng phụ thuộc. `DROP SEQUENCE` không xóa các hàng trong bảng đã được cấp ID.

### 15.3. Đồng bộ sequence sau khi import dữ liệu

Một tình huống phổ biến: import các hàng có ID tường minh, rồi ứng dụng tiếp tục dùng sequence cũ. Nếu sequence đang cấp số nằm dưới MAX(ID) đã import, lần INSERT mới có thể va chạm khóa chính.

Trước khi điều chỉnh, kiểm tra:

```sql
SELECT MAX(order_id) AS max_order_id
FROM orders;
```

Sau đó so sánh với trạng thái sequence theo quy trình quản trị có kiểm soát. Không tùy tiện giả định `USER_SEQUENCES.LAST_NUMBER` luôn là NEXTVAL tiếp theo, nhất là khi sequence có CACHE.

Một cách vận hành có thể là tạm dừng writer, điều chỉnh sequence bằng thủ tục được kiểm soát hoặc tạo sequence mới với điểm bắt đầu an toàn, cập nhật các tham chiếu liên quan, rồi mở lại writer. Cách cụ thể phụ thuộc phiên bản, cache, increment, quyền và số session đang hoạt động. Không thực hiện thay đổi sequence khi ứng dụng vẫn cấp số đồng thời mà chưa có kế hoạch đồng bộ.

Với identity, không thao tác trực tiếp sequence nội bộ. Hãy dùng DDL/khả năng quản lý identity được Oracle hỗ trợ cho phiên bản đang chạy và kiểm tra tài liệu tương ứng.

## 16. Xem metadata identity và sequence

### 16.1. Liệt kê identity columns

```sql
SELECT table_name,
       column_name,
       generation_type,
       sequence_name,
       identity_options
FROM user_tab_identity_cols
ORDER BY table_name, column_name;
```

### 16.2. Liệt kê sequence của schema

```sql
SELECT sequence_name,
       increment_by,
       min_value,
       max_value,
       cycle_flag,
       order_flag,
       cache_size,
       last_number
FROM user_sequences
ORDER BY sequence_name;
```

### 16.3. Xem khóa chính của bảng

```sql
SELECT c.constraint_name,
       cc.column_name,
       c.status
FROM user_constraints c
JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
 AND cc.table_name = c.table_name
WHERE c.table_name = 'ORDERS'
  AND c.constraint_type = 'P'
ORDER BY cc.position;
```

Kiểm tra cả identity/sequence và PRIMARY KEY để biết cột được sinh như thế nào và có constraint bảo vệ tính duy nhất hay không.

## 17. Những lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `ORA-08002: CURRVAL is not yet defined in this session` | Session chưa gọi NEXTVAL | Gọi NEXTVAL trong chính session trước khi đọc CURRVAL |
| `ORA-00001: unique constraint violated` | ID được cấp trùng với dữ liệu hiện có hoặc sequence bị lệch sau import | Kiểm tra PK, sequence và quy trình import |
| `ORA-32795: cannot insert into a generated always identity column` | INSERT truyền giá trị tường minh cho identity ALWAYS | Bỏ cột khỏi INSERT hoặc dùng DEFAULT |
| Identity BY DEFAULT nhận NULL rồi lỗi | BY DEFAULT không tự thay NULL tường minh bằng số | Dùng BY DEFAULT ON NULL hoặc bỏ cột khỏi INSERT |
| ID bị nhảy số | Rollback, cache, lỗi DML, nhiều session | Đây là hành vi bình thường của sequence/identity; không giả định gapless |
| CURRVAL lấy nhầm số | Dùng connection/session khác hoặc đã gọi NEXTVAL khác xen giữa | Dùng cùng session và ưu tiên RETURNING |
| INSERT xong nhưng không lấy được generated key | Driver/JDBC chưa đăng ký hoặc hỗ trợ generated-key chưa phù hợp | Kiểm tra driver, dùng tên cột hoặc RETURNING INTO |
| ID lớn không có nghĩa commit sau | Session khác nhau và transaction commit theo thời điểm riêng | Dùng timestamp hoặc cột thứ tự nghiệp vụ |
| Sequence hết giới hạn | Đạt MAXVALUE/MINVALUE với NOCYCLE | Đánh giá miền số, cấu hình và quy trình mở rộng an toàn |
| Sequence bị trùng sau khi import | Sequence chưa được đồng bộ với ID đã nạp | Dừng writer và đồng bộ có kiểm soát |

### 17.1. Phân biệt lỗi sequence và lỗi khóa chính

Sequence có thể cấp một số hợp lệ theo trạng thái riêng, nhưng bảng đã có hàng mang số đó do import hoặc người dùng chèn ID thủ công. Khi INSERT, PRIMARY KEY phát hiện trùng và báo lỗi. Sequence không tự kiểm tra MAX(ID) trong bảng trước khi cấp số.

### 17.2. Không khắc phục bằng MAX(ID) + 1 trong ứng dụng

Nếu gặp lỗi sequence lệch, giải pháp là đồng bộ sequence theo quy trình có kiểm soát. Đừng sửa code thành `SELECT MAX(id)+1`; cách đó tạo race condition khi nhiều request đồng thời.

## 18. Bài thực hành tổng hợp

Các bước dưới đây tạo bảng và sequence riêng trong schema thực hành. Chỉ chạy nếu có quyền tạo đối tượng và không dùng tên trùng với bảng nghiệp vụ.

### Bước 1. Tạo sequence

```sql
CREATE SEQUENCE demo_order_seq
    START WITH 1000
    INCREMENT BY 1
    MINVALUE 1
    NOMAXVALUE
    NOCYCLE
    CACHE 20;
```

### Bước 2. Tạo bảng sử dụng sequence

```sql
CREATE TABLE demo_orders (
    order_id NUMBER
        CONSTRAINT pk_demo_orders PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_date TIMESTAMP DEFAULT SYSTIMESTAMP,
    status VARCHAR2(20)
);
```

### Bước 3. INSERT bằng NEXTVAL

```sql
INSERT INTO demo_orders (
    order_id,
    customer_id,
    status
)
VALUES (
    demo_order_seq.NEXTVAL,
    501,
    'NEW'
);
```

### Bước 4. Đọc CURRVAL trong cùng session

```sql
SELECT demo_order_seq.CURRVAL AS generated_order_id
FROM dual;
```

Chạy câu này trong chính session đã INSERT ở bước 3.

### Bước 5. INSERT và lấy khóa bằng RETURNING

```sql
VARIABLE generated_id NUMBER

INSERT INTO demo_orders (
    order_id,
    customer_id,
    status
)
VALUES (
    demo_order_seq.NEXTVAL,
    502,
    'NEW'
)
RETURNING order_id INTO :generated_id;

PRINT generated_id
```

Nếu công cụ không hỗ trợ cú pháp bind variable kiểu SQL*Plus, dùng PL/SQL block:

```sql
DECLARE
    v_id demo_orders.order_id%TYPE;
BEGIN
    INSERT INTO demo_orders (
        order_id,
        customer_id,
        status
    )
    VALUES (
        demo_order_seq.NEXTVAL,
        503,
        'NEW'
    )
    RETURNING order_id INTO v_id;

    DBMS_OUTPUT.PUT_LINE('Generated ID=' || v_id);
END;
/
```

### Bước 6. Tạo bảng identity

```sql
CREATE TABLE demo_identity_orders (
    order_id NUMBER
        GENERATED ALWAYS AS IDENTITY
        CONSTRAINT pk_demo_identity_orders PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_date TIMESTAMP DEFAULT SYSTIMESTAMP
);
```

### Bước 7. INSERT và lấy ID identity

```sql
DECLARE
    v_id demo_identity_orders.order_id%TYPE;
BEGIN
    INSERT INTO demo_identity_orders (customer_id)
    VALUES (504)
    RETURNING order_id INTO v_id;

    DBMS_OUTPUT.PUT_LINE('Identity ID=' || v_id);
END;
/
```

### Bước 8. Xem dữ liệu và metadata

```sql
SELECT *
FROM demo_orders
ORDER BY order_id;

SELECT *
FROM demo_identity_orders
ORDER BY order_id;

SELECT table_name,
       column_name,
       generation_type,
       sequence_name
FROM user_tab_identity_cols
WHERE table_name = 'DEMO_IDENTITY_ORDERS';
```

### Bước 9. Thử rollback và quan sát khoảng trống

```sql
INSERT INTO demo_orders (
    order_id,
    customer_id,
    status
)
VALUES (
    demo_order_seq.NEXTVAL,
    505,
    'TEST'
);

ROLLBACK;
```

Gọi NEXTVAL lần nữa:

```sql
SELECT demo_order_seq.NEXTVAL
FROM dual;
```

Giá trị mới tiếp tục tiến lên; giá trị đã lấy trong transaction rollback không được trả lại sequence.

### Bước 10. Dọn đối tượng thực hành

Chỉ sau khi xác nhận đây là các đối tượng do bạn tạo và không cần giữ dữ liệu:

```sql
DROP TABLE demo_identity_orders PURGE;
DROP TABLE demo_orders PURGE;
DROP SEQUENCE demo_order_seq;
```

`DROP TABLE ... PURGE` xóa bảng và dữ liệu, bỏ qua recycle bin theo hành vi lệnh; DDL có commit ngầm. Không chạy lệnh dọn trên bảng nghiệp vụ hoặc đối tượng dùng chung.

## 19. Quy tắc ghi nhớ

| Nhu cầu | Cách dùng |
|---|---|
| Tạo bộ cấp số độc lập | `CREATE SEQUENCE ...` |
| Lấy giá trị mới | `sequence_name.NEXTVAL` |
| Đọc số vừa lấy trong cùng session | `sequence_name.CURRVAL` sau NEXTVAL |
| INSERT khóa từ sequence | Đưa `sequence_name.NEXTVAL` vào VALUES |
| Lấy khóa chính xác của hàng vừa INSERT | `RETURNING id INTO ...` |
| Cột tự sinh trong Oracle 12c+ | `GENERATED ... AS IDENTITY` |
| Không cho ứng dụng tự truyền ID | `GENERATED ALWAYS` |
| Cho phép truyền ID tường minh khi cần | `GENERATED BY DEFAULT` |
| NULL tường minh cũng kích hoạt sinh số | `GENERATED BY DEFAULT ON NULL` |
| Java cần lấy generated key | JDBC `getGeneratedKeys()` theo hỗ trợ driver hoặc `RETURNING INTO` |
| Cập nhật nhiều bảng con bằng khóa mới | Lấy ID và dùng trong cùng transaction |
| Tránh trùng khi nhiều session | Dùng sequence/identity, PK và bind đúng |
| Cần số chứng từ không mất số | Thiết kế quy trình đánh số nghiệp vụ riêng |

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Sequence có tự bảo đảm cột dùng nó là PRIMARY KEY không?

**Trả lời:** Không. Sequence chỉ cấp số; cần khai báo PRIMARY KEY hoặc UNIQUE constraint để database bảo đảm tính duy nhất.

**Câu 2.** `NEXTVAL` và `CURRVAL` khác nhau thế nào?

**Trả lời:** NEXTVAL cấp giá trị mới; CURRVAL đọc giá trị gần nhất mà session hiện tại đã lấy từ sequence.

**Câu 3.** Vì sao CURRVAL có thể báo ORA-08002?

**Trả lời:** Session hiện tại chưa gọi NEXTVAL trên sequence đó.

**Câu 4.** Có nên dùng `MAX(id)+1` để tạo khóa không?

**Trả lời:** Không. Nhiều session có thể cùng tính ra một số; sequence/identity được thiết kế để cấp số đồng thời.

**Câu 5.** Oracle hỗ trợ identity column từ phiên bản nào?

**Trả lời:** Oracle Database 12c Release 1 (12.1).

**Câu 6.** `GENERATED ALWAYS` có cho INSERT một ID tường minh thông thường không?

**Trả lời:** Không. Bỏ cột khỏi INSERT hoặc dùng DEFAULT để Oracle sinh giá trị.

**Câu 7.** `BY DEFAULT` và `BY DEFAULT ON NULL` khác nhau ở đâu?

**Trả lời:** BY DEFAULT dùng generator khi bỏ cột; NULL tường minh được xem là giá trị đã truyền. BY DEFAULT ON NULL dùng generator cả khi cột bị bỏ hoặc được truyền NULL.

**Câu 8.** Vì sao sequence có khoảng trống sau ROLLBACK?

**Trả lời:** NEXTVAL là thao tác cấp số độc lập với transaction; rollback hàng không hoàn lại giá trị đã cấp.

**Câu 9.** `CACHE` có bảo đảm sequence liên tục không?

**Trả lời:** Không. Cache có thể làm bỏ qua các giá trị chưa dùng khi instance gặp sự cố; rollback cũng tạo gap.

**Câu 10.** `RETURNING INTO` có tự COMMIT không?

**Trả lời:** Không. Nó trả giá trị của hàng DML; transaction vẫn do caller quản lý.

**Câu 11.** Có nên truy cập sequence nội bộ của identity bằng tên `ISEQ$$_...` không?

**Trả lời:** Không. Đó là chi tiết Oracle quản lý; dùng identity column và RETURNING/JDBC generated keys.

**Câu 12.** ID lớn hơn có chắc được commit sau ID nhỏ hơn không?

**Trả lời:** Không. Các session có thể commit theo thứ tự khác với thứ tự lấy sequence.

**Câu 13.** Vì sao sequence có thể gây ORA-00001 sau khi import dữ liệu?

**Trả lời:** Sequence có thể đang cấp số nằm trong vùng ID đã được import. Cần đồng bộ sequence với dữ liệu hiện có bằng quy trình có kiểm soát.

**Câu 14.** Trong JDBC, vì sao không nên lấy CURRVAL trên một connection mới?

**Trả lời:** CURRVAL thuộc session. Connection mới có session khác và chưa gọi NEXTVAL của sequence đó.

## 21. Kết luận

Oracle cung cấp hai cách phổ biến để sinh khóa số: **sequence độc lập** và **identity column**. Sequence được gọi tường minh bằng `NEXTVAL`, còn `CURRVAL` chỉ đọc giá trị đã cấp trong session hiện tại. Identity được khai báo ngay trên cột bằng `GENERATED ALWAYS`, `GENERATED BY DEFAULT` hoặc `GENERATED BY DEFAULT ON NULL`; Oracle tự quản lý bộ sinh số gắn với cột. Identity được hỗ trợ từ Oracle 12c Release 1, trong khi sequence phù hợp cả với schema cũ và các trường hợp cần bộ cấp số dùng chung.

Khi cần lấy khóa vừa INSERT, ưu tiên `RETURNING ... INTO` vì giá trị trả về gắn trực tiếp với hàng vừa được tác động. Trong Java/JDBC có thể dùng generated keys theo hỗ trợ của Oracle driver hoặc một PL/SQL block với `RETURNING INTO`. Dùng cùng connection khi đọc CURRVAL, và giữ INSERT hàng cha/hàng con trong cùng transaction nếu chúng thuộc một thao tác nghiệp vụ.

Cuối cùng, sequence và identity **không bảo đảm dãy số liên tục**. Rollback, cache, lỗi DML và nhiều session có thể tạo khoảng trống; thứ tự ID cũng không phải thứ tự commit. Hãy dùng PRIMARY KEY để bảo đảm tính duy nhất, không dùng `MAX(id)+1`, và nếu cần số chứng từ liên tục theo quy định nghiệp vụ thì thiết kế cơ chế đánh số riêng thay vì xem sequence là bộ đếm không mất số.
