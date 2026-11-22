# Identity so với sequence và chiến lược sinh khóa cho ứng dụng trong Oracle Database

Mỗi hàng trong một bảng thường cần một giá trị định danh để ứng dụng có thể tham chiếu, cập nhật và liên kết dữ liệu một cách ổn định. Oracle cung cấp hai cơ chế sinh số phổ biến là **identity column** và **sequence**. Ứng dụng cũng có thể tự sinh khóa, chẳng hạn UUID, hoặc sử dụng khóa nghiệp vụ có sẵn.

Các cơ chế này giải quyết phần sinh giá trị, nhưng không tự quyết định toàn bộ thiết kế khóa. Cần phân biệt:

- **Key generation:** tạo ra giá trị định danh mới.
- **Primary key/unique constraint:** bảo đảm giá trị trong bảng không bị trùng và có thể dùng làm định danh.
- **Business key:** giá trị có ý nghĩa nghiệp vụ, như mã đơn hàng hoặc mã khách hàng.
- **Surrogate key:** khóa thay thế do hệ thống sinh, không mang ý nghĩa nghiệp vụ trực tiếp.

Identity thường phù hợp khi một bảng cần khóa số tự tăng đơn giản. Sequence phù hợp khi ứng dụng cần kiểm soát rõ thời điểm lấy số, chia sẻ bộ sinh giữa nhiều bảng hoặc dùng số trước khi INSERT. UUID hoặc khóa do ứng dụng sinh hữu ích khi cần tạo định danh ở nhiều node hoặc khi client có thể làm việc độc lập với database.

Bài học giải thích cách hoạt động, cú pháp, ưu nhược điểm, tính duy nhất, khoảng trống trong dãy số, hiệu năng, concurrency, lấy lại khóa vừa sinh, tích hợp ứng dụng và cách chọn chiến lược phù hợp.

## 1. Khóa định danh và cơ chế sinh khóa

### 1.1. Khóa chính không đồng nghĩa với identity

Một khóa chính (primary key) là ràng buộc toàn vẹn dữ liệu: các giá trị phải duy nhất và không NULL. Identity là thuộc tính của một cột cho phép Oracle tự sinh giá trị khi thêm hàng.

Ví dụ:

```sql
CREATE TABLE customers (
    customer_id NUMBER GENERATED ALWAYS AS IDENTITY,
    customer_name VARCHAR2(100) NOT NULL,
    CONSTRAINT pk_customers PRIMARY KEY (customer_id)
);
```

Trong ví dụ này có hai thành phần riêng:

- `GENERATED ALWAYS AS IDENTITY` yêu cầu Oracle sinh giá trị cho `CUSTOMER_ID`.
- `PRIMARY KEY` bảo đảm định danh không trùng và không NULL.

Một cột identity không tự động thay thế nhu cầu khai báo PK/UK theo thiết kế dữ liệu. Nên khai báo ràng buộc rõ ràng để database bảo vệ tính duy nhất ngay cả khi dữ liệu được nạp từ ứng dụng, import hoặc quy trình quản trị.

### 1.2. Natural key và surrogate key

**Natural key** là một hoặc nhiều thuộc tính vốn có trong nghiệp vụ, ví dụ mã ISBN của sách hoặc mã quốc gia. **Surrogate key** là giá trị được tạo riêng để định danh hàng, ví dụ `CUSTOMER_ID` dạng NUMBER.

| Tiêu chí | Natural key | Surrogate key |
| --- | --- | --- |
| Ý nghĩa | Có ý nghĩa nghiệp vụ | Thường không mang ý nghĩa nghiệp vụ |
| Độ ổn định | Có thể thay đổi theo quy tắc nghiệp vụ | Nên ổn định trong suốt vòng đời hàng |
| Độ dài | Có thể gồm nhiều cột hoặc chuỗi dài | Thường nhỏ, cố định |
| Tạo khóa | Theo quy tắc nghiệp vụ | Identity, sequence, UUID hoặc ứng dụng |
| Dùng làm PK | Phù hợp khi thực sự ổn định và duy nhất | Thường thuận tiện cho quan hệ nội bộ |
| Ràng buộc nghiệp vụ | Thường cần UNIQUE riêng | Vẫn cần UNIQUE cho mã nghiệp vụ |

Một thiết kế phổ biến là dùng surrogate key làm PK và đặt UNIQUE constraint trên business key. Ví dụ `CUSTOMER_ID` là PK, còn `TAX_CODE` hoặc mã khách hàng do nghiệp vụ cấp có UNIQUE constraint phù hợp.

Không nên dùng một giá trị có thể đổi thường xuyên như email hoặc số điện thoại làm PK chỉ vì hiện tại nó có vẻ duy nhất.

### 1.3. Sinh khóa không tự bảo đảm tính duy nhất của mọi dữ liệu

Sequence và identity có thể sinh ra các giá trị riêng biệt theo cấu hình của chúng, nhưng dữ liệu vẫn cần constraint:

```sql
CREATE TABLE orders (
    order_id NUMBER GENERATED ALWAYS AS IDENTITY,
    order_no VARCHAR2(30) NOT NULL,
    CONSTRAINT pk_orders PRIMARY KEY (order_id),
    CONSTRAINT uq_orders_order_no UNIQUE (order_no)
);
```

`ORDER_ID` là khóa thay thế. `ORDER_NO` là mã nghiệp vụ và cần quy tắc duy nhất riêng. Không nên suy ra rằng vì `ORDER_ID` duy nhất nên `ORDER_NO` cũng duy nhất.

## 2. Identity column trong Oracle

### 2.1. Identity là gì?

Identity column được Oracle giới thiệu từ Oracle Database 12c. Cột identity là cột số mà Oracle tự sinh giá trị khi INSERT theo chế độ generation được khai báo.

Ví dụ đơn giản:

```sql
CREATE TABLE departments (
    department_id NUMBER GENERATED ALWAYS AS IDENTITY,
    department_name VARCHAR2(100) NOT NULL,
    CONSTRAINT pk_departments PRIMARY KEY (department_id)
);
```

INSERT không cần cung cấp `DEPARTMENT_ID`:

```sql
INSERT INTO departments (department_name)
VALUES ('Engineering');

INSERT INTO departments (department_name)
VALUES ('Finance');

COMMIT;
```

Oracle tự tạo giá trị cho cột identity. Người dùng ứng dụng không cần gọi `NEXTVAL` hoặc viết trigger cấp số.

### 2.2. Ba chế độ generation

Oracle hỗ trợ ba cách khai báo chính:

**GENERATED ALWAYS AS IDENTITY**

Oracle luôn tự sinh giá trị. Nếu INSERT cố cung cấp giá trị tường minh cho cột identity, câu lệnh bị từ chối.

```sql
CREATE TABLE always_ids (
    id NUMBER GENERATED ALWAYS AS IDENTITY,
    description VARCHAR2(100),
    CONSTRAINT pk_always_ids PRIMARY KEY (id)
);
```

INSERT thông thường:

```sql
INSERT INTO always_ids (description)
VALUES ('Generated by Oracle');
```

Cách này phù hợp khi ứng dụng không được phép tự chọn giá trị PK trong luồng ghi thông thường.

**GENERATED BY DEFAULT AS IDENTITY**

Oracle sinh giá trị khi cột bị bỏ khỏi danh sách INSERT hoặc dùng từ khóa `DEFAULT`. Nếu ứng dụng cung cấp giá trị tường minh, Oracle chấp nhận giá trị đó.

```sql
CREATE TABLE default_ids (
    id NUMBER GENERATED BY DEFAULT AS IDENTITY,
    description VARCHAR2(100),
    CONSTRAINT pk_default_ids PRIMARY KEY (id)
);
```

Ví dụ:

```sql
INSERT INTO default_ids (description)
VALUES ('Oracle generates the id');

INSERT INTO default_ids (id, description)
VALUES (9000, 'Imported id');
```

Chế độ này thuận tiện cho import hoặc migration cần giữ ID cũ, nhưng phải kiểm soát giá trị được cung cấp. Một giá trị tường minh có thể trùng với PK hiện có hoặc va chạm với giá trị Oracle sẽ sinh ở lần INSERT sau.

**GENERATED BY DEFAULT ON NULL AS IDENTITY**

Oracle sinh giá trị nếu cột bị bỏ qua hoặc được truyền rõ ràng là NULL.

```sql
CREATE TABLE default_on_null_ids (
    id NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY,
    description VARCHAR2(100),
    CONSTRAINT pk_default_on_null_ids PRIMARY KEY (id)
);
```

Cả hai câu sau đều để Oracle sinh ID:

```sql
INSERT INTO default_on_null_ids (description)
VALUES ('Column omitted');

INSERT INTO default_on_null_ids (id, description)
VALUES (NULL, 'Explicit NULL');
```

Chế độ này hữu ích khi ứng dụng có thói quen gửi NULL cho trường chưa có ID. Nếu ứng dụng gửi một số khác NULL, giá trị đó vẫn được chấp nhận theo nghĩa `BY DEFAULT`.

### 2.3. So sánh ba chế độ

| Cách khai báo | Bỏ cột khỏi INSERT | Truyền NULL | Truyền số tường minh |
| --- | --- | --- | --- |
| `GENERATED ALWAYS` | Oracle sinh | Oracle sinh | Bị từ chối |
| `GENERATED BY DEFAULT` | Oracle sinh | NULL không yêu cầu sinh; cột identity là NOT NULL nên thường bị từ chối | Chấp nhận |
| `GENERATED BY DEFAULT ON NULL` | Oracle sinh | Oracle sinh | Chấp nhận |

Nếu cần Oracle luôn kiểm soát ID, chọn `GENERATED ALWAYS`. Nếu cần import ID tường minh, cân nhắc `BY DEFAULT`, nhưng phải quản lý đồng bộ giá trị và sequence nội bộ. Nếu client có thể gửi NULL, `BY DEFAULT ON NULL` thường dễ tích hợp hơn.

### 2.4. Cấu hình identity options

Identity sử dụng một sequence generator do Oracle quản lý. Có thể chỉ định các tùy chọn sequence trong phần identity:

```sql
CREATE TABLE invoices (
    invoice_id NUMBER
        GENERATED ALWAYS AS IDENTITY
        (
            START WITH 1000
            INCREMENT BY 1
            CACHE 100
            NOCYCLE
        ),
    invoice_date DATE DEFAULT SYSDATE NOT NULL,
    amount NUMBER(12,2) NOT NULL,
    CONSTRAINT pk_invoices PRIMARY KEY (invoice_id)
);
```

Ý nghĩa:

- `START WITH 1000`: giá trị khởi đầu.
- `INCREMENT BY 1`: tăng mỗi lần một đơn vị.
- `CACHE 100`: cache một nhóm giá trị để giảm chi phí lấy số.
- `NOCYCLE`: không quay lại đầu dãy khi đạt giới hạn.

Nếu không chỉ định, Oracle dùng các mặc định phù hợp của identity/sequence. Nên chỉ cấu hình các tùy chọn có lý do vận hành rõ ràng.

### 2.5. Identity chỉ nên là một cột trong một bảng

Một bảng Oracle chỉ có một identity column. Identity phù hợp cho một khóa số tự sinh của bảng. Nếu cần nhiều bộ sinh độc lập hoặc một dãy số được dùng chung cho nhiều bảng, sequence tường minh linh hoạt hơn.

Identity column phải dùng kiểu dữ liệu số phù hợp. Hãy chọn precision/scale và giới hạn giá trị đủ cho vòng đời bảng; tránh để một khóa số tăng dần đạt giới hạn kiểu dữ liệu.

### 2.6. Kiểm tra metadata identity

Có thể xem các identity column trong schema:

```sql
SELECT table_name,
       column_name,
       generation_type,
       identity_options
FROM   user_tab_identity_cols
ORDER  BY table_name, column_name;
```

`GENERATION_TYPE` cho biết chế độ generation; `IDENTITY_OPTIONS` hiển thị các tùy chọn liên quan. Quyền và view tương ứng có thể khác khi xem schema khác hoặc môi trường multitenant.

Không xây dựng ứng dụng dựa trên tên sequence nội bộ mà Oracle tạo cho identity. Tên dạng `ISEQ$$_...` là chi tiết triển khai; dùng metadata identity để kiểm tra cấu hình và dùng chính cột identity khi INSERT.

## 3. Sequence tường minh

### 3.1. Sequence là gì?

Sequence là đối tượng schema chuyên sinh các số theo quy tắc tăng/giảm. Nhiều session có thể cùng yêu cầu giá trị từ một sequence mà không phải tự khóa một hàng bộ đếm trong bảng.

Tạo sequence:

```sql
CREATE SEQUENCE orders_seq
    START WITH 1
    INCREMENT BY 1
    MINVALUE 1
    NOMAXVALUE
    CACHE 100
    NOCYCLE;
```

Sequence tồn tại độc lập với bảng. Một sequence có thể cấp ID cho một bảng hoặc được chia sẻ giữa nhiều bảng nếu thiết kế yêu cầu.

### 3.2. NEXTVAL

`NEXTVAL` yêu cầu sequence cấp một giá trị mới:

```sql
SELECT orders_seq.NEXTVAL
FROM   dual;
```

Mỗi lần gọi `NEXTVAL`, sequence tiến thêm theo `INCREMENT BY` và trả giá trị mới. Nhiều session gọi đồng thời vẫn nhận các giá trị sequence khác nhau trong cùng dãy không cycle.

Dùng trực tiếp trong INSERT:

```sql
INSERT INTO orders (
    order_id,
    customer_id,
    order_date,
    total_amount
)
VALUES (
    orders_seq.NEXTVAL,
    100,
    SYSDATE,
    250000
);
```

Ứng dụng có thể không cần SELECT sequence riêng trước INSERT nếu chỉ cần ghi hàng.

### 3.3. CURRVAL

`CURRVAL` trả giá trị gần nhất mà **session hiện tại** đã lấy từ sequence đó bằng `NEXTVAL`.

```sql
SELECT orders_seq.CURRVAL
FROM   dual;
```

Một session phải gọi `NEXTVAL` trước khi dùng `CURRVAL`; nếu chưa, Oracle báo lỗi sequence chưa được định nghĩa trong session hiện tại (thường là ORA-08002).

`CURRVAL` có tính session-local. Nó không phải cách lấy ID vừa tạo một cách an toàn nếu ứng dụng chuyển sang một connection khác trong connection pool. Với INSERT, nên ưu tiên `RETURNING INTO` để nhận đúng khóa của hàng vừa thêm.

### 3.4. Dùng sequence trong SELECT để INSERT nhiều hàng

Sequence có thể cấp giá trị cho từng hàng của một câu INSERT ... SELECT:

```sql
INSERT INTO order_items (
    item_id,
    order_id,
    product_id,
    quantity
)
SELECT order_items_seq.NEXTVAL,
       s.order_id,
       s.product_id,
       s.quantity
FROM   staging_order_items s
WHERE  s.load_batch_id = :batch_id;
```

Mỗi hàng được chèn nhận một giá trị mới. Đây là cách thuận tiện cho nạp dữ liệu theo lô mà không cần vòng lặp cấp số ở tầng ứng dụng.

### 3.5. Các tùy chọn sequence quan trọng

| Tùy chọn | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `START WITH` | Giá trị bắt đầu | Cần tính đến dữ liệu đã có |
| `INCREMENT BY` | Bước tăng hoặc giảm | Thường là 1 cho PK |
| `MINVALUE` / `MAXVALUE` | Giới hạn dãy | Phải đủ cho vòng đời hệ thống |
| `CACHE n` | Cache trước một số giá trị | Tăng hiệu năng; có thể mất số đã cache khi sự cố |
| `NOCACHE` | Không cache giá trị | Có thể giảm hiệu năng; không loại bỏ mọi khoảng trống |
| `CYCLE` | Quay lại đầu dãy khi đạt giới hạn | Không phù hợp với PK cần duy nhất lâu dài |
| `NOCYCLE` | Không quay lại đầu dãy | Thường dùng cho khóa định danh |
| `ORDER` | Đảm bảo thứ tự cấp theo yêu cầu sequence | Có chi phí; không đồng nghĩa thứ tự COMMIT |
| `NOORDER` | Không yêu cầu thứ tự toàn cục theo request | Thường phù hợp khi ưu tiên throughput |

Với PK, thường chọn `NOCYCLE`. `CACHE` thường có lợi cho hiệu năng, đặc biệt khi nhiều session cùng lấy số. Chọn cache size theo workload và chấp nhận rằng dãy số có thể có khoảng trống.

### 3.6. Sequence độc lập với transaction

Sequence không phải bộ đếm transactional:

```sql
SELECT orders_seq.NEXTVAL FROM dual;

ROLLBACK;
```

Giá trị sequence đã lấy không quay trở lại sequence khi transaction rollback. Nếu lấy số 105 rồi rollback, lần gọi sau có thể nhận 106. Giá trị 105 trở thành một khoảng trống.

Điều này là có chủ đích: Oracle không khóa và hoàn tác sequence như một hàng dữ liệu thông thường. Nếu rollback làm sequence quay lại, nhiều session đồng thời có thể nhận trùng giá trị hoặc phải khóa bộ đếm lâu hơn.

## 4. Identity và sequence khác nhau thế nào?

### 4.1. Bảng so sánh

| Tiêu chí | Identity column | Sequence tường minh |
| --- | --- | --- |
| Cách khai báo | Trên cột trong CREATE TABLE | CREATE SEQUENCE riêng |
| Cấp số khi INSERT | Oracle tự sinh theo generation mode | Câu SQL gọi NEXTVAL, default hoặc trigger |
| Liên kết bảng | Gắn với một cột identity của một bảng | Có thể dùng ở nhiều bảng |
| Kiểm soát giá trị | ALWAYS/BY DEFAULT/BY DEFAULT ON NULL | Ứng dụng quyết định lúc gọi NEXTVAL |
| Lấy số trước INSERT | Không có API NEXTVAL công khai cho identity nội bộ | Có thể lấy NEXTVAL trước |
| Dùng chung dãy số | Không phải mục đích của identity | Phù hợp |
| Trigger | Không cần trigger cấp số | Có thể dùng trigger cho schema legacy |
| Độ đơn giản | Cao cho PK tự sinh | Linh hoạt hơn nhưng cần cấu hình |
| Tích hợp legacy | Có thể cần điều chỉnh INSERT cũ | Dễ giữ mô hình sequence/trigger hiện có |

Identity được xây dựng trên cơ chế sequence của Oracle, nhưng Oracle quản lý sequence nội bộ đó. Không nên truy cập hoặc sửa trực tiếp sequence nội bộ thay vì thao tác qua cột identity.

### 4.2. Khi nên chọn identity

Identity thường phù hợp khi:
- Mỗi bảng có một PK số tự sinh riêng.
- Ứng dụng chỉ cần ID tại thời điểm INSERT.
- Không cần dùng cùng dãy số cho nhiều bảng.
- Muốn tránh trigger cấp số và giảm cấu hình thủ công.
- Hệ thống chạy Oracle 12c trở lên và schema có thể dùng identity.

### 4.3. Khi nên chọn sequence

Sequence phù hợp khi:
- Cần cấp ID trước khi INSERT.
- Cần dùng một bộ sinh chung cho nhiều bảng.
- Ứng dụng hoặc stored procedure gọi `NEXTVAL` trực tiếp.
- Cần cấp trước một nhóm số cho batch.
- Cần giữ mô hình tương thích với schema cũ đang dùng sequence/trigger.
- Cần nhiều dãy số với quy tắc khác nhau.

### 4.4. Identity không phải phiên bản “mạnh hơn” của sequence

Identity đơn giản hóa thao tác gắn bộ sinh với cột. Sequence tường minh cho quyền kiểm soát và tái sử dụng cao hơn. Cả hai đều có thể tạo khoảng trống, cả hai đều cần PK/UK constraint, và cả hai đều không nên được dùng như cơ chế đánh số chứng từ liên tục không có gap nếu nghiệp vụ yêu cầu quy tắc pháp lý riêng.

## 5. Trigger cấp khóa: mô hình legacy

### 5.1. Sequence kết hợp trigger

Trước khi có identity column, một mẫu phổ biến là tạo sequence và BEFORE INSERT trigger:

```sql
CREATE SEQUENCE customers_seq
    START WITH 1
    INCREMENT BY 1
    CACHE 100
    NOCYCLE;
```

```sql
CREATE OR REPLACE TRIGGER customers_bir
BEFORE INSERT ON customers
FOR EACH ROW
WHEN (NEW.customer_id IS NULL)
BEGIN
    :NEW.customer_id := customers_seq.NEXTVAL;
END;
/
```

Trigger cấp ID khi ứng dụng không truyền `CUSTOMER_ID`. Nếu ứng dụng truyền ID khác NULL, trigger trong ví dụ không ghi đè giá trị đó.

### 5.2. Vì sao dùng WHEN NEW...?

Điều kiện:

```sql
WHEN (NEW.customer_id IS NULL)
```

giữ lại khả năng import ID tường minh. Nếu trigger gán `NEXTVAL` vô điều kiện, giá trị ứng dụng truyền vào có thể bị ghi đè.

Dù vậy, cho phép nhập ID thủ công cần được kiểm soát. Sau khi import các ID lớn, sequence có thể vẫn sinh ra giá trị thấp hơn và gây va chạm. Cần đồng bộ lại sequence theo quy trình migration có kiểm soát.

### 5.3. Nhược điểm của trigger cấp khóa

- Logic sinh khóa nằm ẩn ngoài câu INSERT.
- Khó lần theo khi debug và kiểm thử.
- Có thể xung đột với ứng dụng cũng tự gọi sequence.
- Dễ bị bỏ sót khi migrate schema hoặc copy dữ liệu.
- Trigger phức tạp có thể tăng chi phí DML và tạo side effect khó dự đoán.

Với schema mới, identity thường đơn giản hơn nếu chỉ cần một khóa số tự sinh. Với schema legacy, sequence/trigger có thể tiếp tục phù hợp nếu ứng dụng phụ thuộc vào hành vi đó.

### 5.4. Sequence làm DEFAULT thay cho trigger

Trong các phiên bản Oracle hỗ trợ sequence trong column default, có thể khai báo:

```sql
CREATE SEQUENCE audit_seq
    START WITH 1
    INCREMENT BY 1
    CACHE 100
    NOCYCLE;

CREATE TABLE audit_events (
    event_id NUMBER DEFAULT audit_seq.NEXTVAL NOT NULL,
    event_type VARCHAR2(50) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_audit_events PRIMARY KEY (event_id)
);
```

INSERT bỏ qua `EVENT_ID` sẽ dùng default. Cần kiểm tra cú pháp và giới hạn theo release Oracle đang chạy. Nếu cần sinh ID cả khi client truyền NULL, xem xét `DEFAULT ON NULL` nếu được hỗ trợ. Không kết hợp nhiều cơ chế cấp số cho cùng một cột nếu không có chủ đích rõ ràng.

## 6. Lấy lại ID vừa INSERT

### 6.1. Dùng RETURNING INTO

Với identity:

```sql
DECLARE
    l_order_id orders.order_id%TYPE;
BEGIN
    INSERT INTO orders (customer_id, total_amount)
    VALUES (100, 250000)
    RETURNING order_id INTO l_order_id;

    DBMS_OUTPUT.PUT_LINE('New order id = ' || l_order_id);
END;
/
```

`RETURNING INTO` trả giá trị của hàng vừa được INSERT trong cùng câu lệnh. Ứng dụng có thể dùng bind output parameter theo driver tương ứng.

### 6.2. Với sequence tường minh

```sql
DECLARE
    l_order_id orders.order_id%TYPE;
BEGIN
    INSERT INTO orders (
        order_id,
        customer_id,
        total_amount
    )
    VALUES (
        orders_seq.NEXTVAL,
        100,
        250000
    )
    RETURNING order_id INTO l_order_id;

    DBMS_OUTPUT.PUT_LINE('New order id = ' || l_order_id);
END;
/
```

Có thể lấy `CURRVAL` trong cùng session sau khi đã gọi `NEXTVAL`, nhưng `RETURNING INTO` gắn trực tiếp với hàng được INSERT nên thường rõ ràng và an toàn hơn trong ứng dụng.

### 6.3. Không dùng MAX(id) để lấy khóa vừa tạo

Cách sai:

```sql
SELECT MAX(order_id)
FROM orders;
```

Nếu hai session INSERT đồng thời, session khác có thể tạo ID lớn hơn trước khi truy vấn MAX chạy. Giá trị MAX không chứng minh đó là ID của hàng vừa INSERT bởi session hiện tại.

Dùng `RETURNING INTO`, hoặc dùng `NEXTVAL` đã lấy trong chính session nếu thiết kế sequence yêu cầu. Không truy vấn MAX để suy ra khóa mới.

### 6.4. Connection pool và session state

`CURRVAL` thuộc session database hiện tại. Trong ứng dụng dùng connection pool:
- Câu INSERT và câu đọc CURRVAL phải thực sự dùng cùng physical database session.
- Nếu pool trả connection khác, CURRVAL có thể chưa được khởi tạo hoặc mang giá trị của một thao tác khác trên session đó.
- Không giả định hai lần gọi repository/service sẽ luôn chạy trên cùng session nếu transaction/pool không bảo đảm.

Dùng `RETURNING INTO` trong cùng DML tránh phụ thuộc vào session state để lấy ID.

## 7. Khoảng trống trong dãy số và tính duy nhất

### 7.1. Vì sao sequence có gap?

Sequence không cam kết số liên tục. Gap có thể xuất hiện khi:
- Transaction lấy NEXTVAL rồi ROLLBACK.
- INSERT lỗi sau khi sequence đã cấp số.
- Ứng dụng lấy số nhưng không sử dụng.
- Sequence CACHE một nhóm giá trị và instance bị dừng bất thường trước khi dùng hết.
- Nhiều session lấy số xen kẽ và các transaction commit theo thứ tự khác nhau.
- Hàng đã INSERT bị DELETE.

Ví dụ:

```text
NEXTVAL -> 100
INSERT thành công
COMMIT

NEXTVAL -> 101
INSERT thất bại
ROLLBACK

NEXTVAL -> 102
INSERT thành công
COMMIT

Các ID còn lại: 100, 102
```

Không có gì sai khi số 101 bị khuyết nếu khóa chỉ cần duy nhất.

### 7.2. Identity cũng có gap

Identity sử dụng cơ chế sequence nội bộ nên cũng có thể có khoảng trống vì rollback, lỗi INSERT, cache hoặc sự cố. Chuyển từ sequence sang identity không biến ID thành dãy liên tục.

### 7.3. NOCACHE không bảo đảm gap-free

`NOCACHE` tránh mất nhóm giá trị đã cache trong một số tình huống instance failure, nhưng không loại bỏ gap do rollback, lỗi DML, transaction hủy hoặc ứng dụng bỏ số.

Vì vậy, không chọn NOCACHE với kỳ vọng có số liên tục. Nó còn có thể làm giảm hiệu năng khi nhiều session cùng lấy sequence.

### 7.4. Sequence bảo đảm duy nhất theo dãy, không bảo đảm thứ tự commit

Giả sử:
- Session A lấy 100.
- Session B lấy 101.
- B COMMIT trước.
- A COMMIT sau.

Bảng có thể thấy hàng 101 được commit trước hàng 100. Sequence phản ánh thứ tự cấp số, không phản ánh thứ tự commit hoặc thời gian tạo nghiệp vụ chính xác.

Trong môi trường RAC, `NOORDER` cho phép sequence tối ưu throughput mà không bảo đảm thứ tự toàn cục theo request giữa các instance. `ORDER` bảo đảm thứ tự cấp theo yêu cầu sequence nhưng không làm thứ tự COMMIT trở thành thứ tự số và có thể tăng chi phí.

### 7.5. Không dùng sequence làm số hóa đơn liên tục nếu pháp lý yêu cầu gap-free

PK nội bộ và số chứng từ nghiệp vụ là hai khái niệm khác nhau. Nếu hóa đơn cần dãy số theo quy định, cần thiết kế riêng:
- Xác định phạm vi đánh số (theo năm, chi nhánh, loại chứng từ).
- Có bảng cấp số và cơ chế serialize/lock phù hợp.
- Chỉ cấp số tại thời điểm nghiệp vụ được xác nhận theo quy định.
- Xác định cách xử lý chứng từ hủy và số đã cấp.
- Lưu audit để giải trình gap hợp lệ.

Cơ chế này thường có trade-off về concurrency. Không nên dùng sequence PK thông thường rồi kỳ vọng nó đáp ứng yêu cầu đánh số liên tục.

## 8. Hiệu năng và concurrency

### 8.1. Vì sao sequence hoạt động tốt với nhiều session?

Sequence là đối tượng chuyên dụng để cấp số, không cần mọi session cùng UPDATE một hàng counter trong bảng. Oracle quản lý việc cấp giá trị đồng thời và có thể cache các số để giảm thao tác đồng bộ.

Một cách thiết kế kém hiệu quả là:

```sql
SELECT next_id
FROM   id_counter
WHERE  counter_name = 'ORDERS'
FOR UPDATE;

UPDATE id_counter
SET next_id = next_id + 1
WHERE counter_name = 'ORDERS';
```

Mọi session phải tranh chấp cùng một hàng counter. Sequence thường là lựa chọn tốt hơn cho surrogate key tăng dần.

### 8.2. CACHE và NOCACHE

`CACHE n` cho phép Oracle giữ trước một nhóm giá trị sequence, giảm chi phí cấp số lặp lại. Với hệ thống có throughput cao, cache thường hữu ích.

`NOCACHE` không cache trước nhóm giá trị. Nó có thể làm sequence chậm hơn khi có nhiều request và không bảo đảm dãy liên tục.

Chọn cache size dựa trên:
- Tần suất lấy NEXTVAL.
- Số session đồng thời.
- Số instance RAC nếu có.
- Mức chấp nhận gap.
- Mục tiêu hiệu năng và đặc tính restart/recovery.

### 8.3. ORDER và NOORDER

`ORDER` yêu cầu giá trị được cấp theo thứ tự request sequence. `NOORDER` không yêu cầu bảo đảm thứ tự này và thường phù hợp khi throughput quan trọng hơn.

Cả hai đều không bảo đảm:
- Thứ tự commit.
- Thứ tự hoàn tất transaction.
- Không có gap.
- ID phản ánh thời gian nghiệp vụ chính xác.

Không bật ORDER chỉ để “ID nhìn có vẻ tuần tự” nếu ứng dụng không có yêu cầu thực sự về thứ tự cấp số.

### 8.4. Index trên khóa tăng dần

PK thường được hỗ trợ bởi unique index. Với ID tăng dần, insert thường tập trung vào vùng cuối của B-tree index. Đây là hành vi phổ biến và thường hiệu quả, nhưng ở workload rất cao có thể xuất hiện cạnh tranh trên các leaf block nóng hoặc vấn đề index block contention.

Không thay đổi chiến lược ID chỉ dựa trên suy đoán. Đo wait events, index contention, tốc độ insert và execution statistics trước khi chọn giải pháp như reverse key index hoặc thiết kế phân vùng. Reverse key index có các giới hạn riêng, chẳng hạn không phù hợp với một số range scan theo khóa.

### 8.5. UUID và index locality

UUID ngẫu nhiên có thể phân tán điểm INSERT trên nhiều vùng của B-tree index, làm giảm một số điểm nóng ở cuối index nhưng có thể tăng block split và giảm locality. Ngoài ra, UUID thường lớn hơn NUMBER và tăng kích thước PK/FK cùng index liên quan.

Nếu cần UUID cho phân tán, hãy chọn kiểu lưu trữ và định dạng nhất quán. Đừng chọn UUID chỉ vì nghĩ nó luôn nhanh hơn sequence.

## 9. Khóa do ứng dụng sinh và UUID

### 9.1. Khi nào ứng dụng nên tự sinh ID?

Ứng dụng có thể cần tạo ID trước khi kết nối database:
- Dữ liệu được tạo offline rồi đồng bộ sau.
- Nhiều service/database độc lập tạo dữ liệu.
- Hệ thống phân tán không muốn phụ thuộc một sequence trung tâm.
- Cần ID trong event/message trước khi lưu database.
- Cần tạo quan hệ giữa các object trong bộ nhớ trước khi INSERT.

Trong các trường hợp này, UUID hoặc một chiến lược distributed ID có thể phù hợp.

### 9.2. UUID

UUID là định danh 128-bit thường được biểu diễn thành chuỗi dạng:

```text
550e8400-e29b-41d4-a716-446655440000
```

Ứng dụng có thể sinh UUID bằng thư viện chuẩn của ngôn ngữ. Các node độc lập có thể tạo ID mà không cần gọi sequence trung tâm. Xác suất trùng cực thấp với generator chuẩn, nhưng database vẫn nên có PRIMARY KEY hoặc UNIQUE constraint để bảo vệ tính duy nhất.

### 9.3. Lưu UUID trong Oracle

Có thể lưu UUID dưới dạng `RAW(16)` để tránh chi phí lưu chuỗi ký tự 36 byte:

```sql
CREATE TABLE distributed_events (
    event_id RAW(16) NOT NULL,
    event_type VARCHAR2(50) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_distributed_events PRIMARY KEY (event_id)
);
```

Nếu muốn Oracle tự sinh GUID:

```sql
CREATE TABLE local_events (
    event_id RAW(16) DEFAULT SYS_GUID() NOT NULL,
    event_type VARCHAR2(50) NOT NULL,
    CONSTRAINT pk_local_events PRIMARY KEY (event_id)
);
```

`SYS_GUID()` trả về giá trị RAW 16 byte. Đây là GUID do Oracle tạo; không nên mặc định rằng định dạng hoặc bit layout của nó tương đương mọi phiên bản UUID chuẩn mà ứng dụng bên ngoài mong đợi. Nếu cần UUID RFC theo phiên bản cụ thể, hãy dùng generator phù hợp và lưu/đổi định dạng có kiểm soát.

### 9.4. RAW(16) và CHAR(36)

| Kiểu lưu | Ưu điểm | Điểm cần cân nhắc |
| --- | --- | --- |
| `RAW(16)` | Gọn, không lưu dấu gạch nối, index nhỏ hơn dạng text | Cần chuyển đổi khi hiển thị hoặc truyền qua API |
| `CHAR(36)` / `VARCHAR2(36)` | Dễ đọc, dễ log và trao đổi | Tốn dung lượng hơn, cần chuẩn hóa chữ hoa/thường và định dạng |

Có thể dùng `RAWTOHEX(event_id)` để hiển thị giá trị RAW thành chuỗi hex. Nếu ứng dụng gửi UUID text, cần chuyển đổi nhất quán bằng `HEXTORAW` sau khi chuẩn hóa và loại dấu gạch nối phù hợp.

### 9.5. UUID ngẫu nhiên và UUID có thứ tự thời gian

Một số phiên bản UUID có cấu trúc hỗ trợ thứ tự thời gian hoặc tính locality tốt hơn UUID ngẫu nhiên. Nếu ứng dụng cần UUID và workload insert lớn, hãy đánh giá định dạng có tính locality, cách lưu RAW và hành vi index.

Không giả định `SYS_GUID()` là UUID v7 hoặc luôn tăng theo thời gian. Hãy xác định đúng đặc tính generator đang dùng.

### 9.6. Distributed ID ngoài UUID

Các hệ thống phân tán có thể dùng:
- ID gồm timestamp, node ID và sequence nội bộ.
- Dải ID được cấp trước cho từng node.
- Snowflake-style ID.
- UUID/ULID theo thư viện chuẩn.

Các chiến lược này cần xử lý đồng hồ hệ thống, định danh node, restart, failover và trùng ID khi cấu hình sai. Nếu chưa có yêu cầu phân tán rõ ràng, identity hoặc sequence trong Oracle thường đơn giản hơn.

## 10. Chiến lược khóa cho nhiều loại ứng dụng

### 10.1. Ứng dụng OLTP đơn database

Mẫu thường phù hợp:
- PK nội bộ NUMBER dùng identity hoặc sequence.
- UNIQUE constraint cho mã nghiệp vụ.
- FK tham chiếu surrogate PK.
- Dùng `RETURNING INTO` để lấy ID vừa tạo.

Identity thường giảm cấu hình. Sequence phù hợp nếu ứng dụng cần lấy ID trước hoặc chia sẻ bộ sinh.

### 10.2. Nhiều service cùng ghi vào một Oracle database

Có thể:
- Dùng một sequence dùng chung cho một loại entity.
- Dùng identity riêng theo bảng nếu các bảng độc lập.
- Dùng UUID nếu ID được tạo ở nhiều service trước khi INSERT.

Không nên để mỗi service tự duy trì một bộ đếm riêng bắt đầu từ 1 nếu chúng cùng ghi vào một cột PK, vì sẽ có va chạm.

### 10.3. Nhiều database hoặc đồng bộ offline

UUID hoặc distributed ID phù hợp hơn khi không thể gọi một sequence trung tâm. Thiết kế cần:
- Generator thống nhất và được kiểm soát.
- Cùng kiểu dữ liệu/encoding ở các hệ thống.
- PK/unique constraint tại đích.
- Quy tắc xử lý conflict khi đồng bộ.
- Quy tắc idempotency cho message/event retry.

### 10.4. Bảng lớn và insert throughput cao

Sequence với CACHE hoặc identity có thể phù hợp cho PK NUMBER. Đo hiệu năng index và sequence trước khi chuyển sang UUID hoặc thay đổi cấu trúc index. Dùng số liệu thực tế để cân nhắc:
- Cache size.
- Số instance.
- Hot index block.
- Partitioning.
- Batch insert.
- Index maintenance.

### 10.5. Bảng staging và dữ liệu import

Nếu dữ liệu nguồn có ID riêng:
- Giữ source ID ở cột riêng nếu cần truy vết.
- Tạo surrogate PK nội bộ bằng identity/sequence.
- Đặt UNIQUE constraint trên source system + source ID nếu định danh nguồn phải duy nhất.
- Không nhập ID thủ công vào identity BY DEFAULT mà không đồng bộ bộ sinh và kiểm tra collision.

Ví dụ:

```sql
CREATE TABLE imported_customers (
    customer_id NUMBER GENERATED ALWAYS AS IDENTITY,
    source_system VARCHAR2(30) NOT NULL,
    source_customer_id VARCHAR2(80) NOT NULL,
    customer_name VARCHAR2(200) NOT NULL,
    CONSTRAINT pk_imported_customers PRIMARY KEY (customer_id),
    CONSTRAINT uq_imported_source_customer
        UNIQUE (source_system, source_customer_id)
);
```

Mô hình này tách khóa nội bộ với định danh từ hệ thống nguồn.

## 11. Tích hợp ứng dụng và ORM

### 11.1. Không lấy ID bằng SELECT MAX

Ứng dụng nên nhận ID từ chính thao tác INSERT:
- `RETURNING INTO` cho DML Oracle.
- API generated keys của driver/ORM nếu hỗ trợ đúng identity/sequence.
- `NEXTVAL` trước INSERT nếu ứng dụng chủ động dùng sequence.

Không dùng `MAX(id)` vì request đồng thời có thể tạo hàng mới giữa lúc INSERT và lúc SELECT MAX.

### 11.2. Identity strategy trong ORM

Các ORM có thể hỗ trợ các chiến lược như identity, sequence hoặc UUID. Lựa chọn ảnh hưởng đến thời điểm ORM cần INSERT để lấy ID, khả năng batch INSERT và việc preallocate ID.

- Identity: ORM thường phải thực hiện INSERT để database sinh ID rồi mới nhận khóa.
- Sequence: ORM có thể lấy NEXTVAL trước, gán ID vào entity và gom INSERT theo batch tùy framework/driver.
- UUID: ứng dụng có thể gán ID trước khi INSERT, thuận tiện khi tạo object graph hoặc event.

Chi tiết phụ thuộc ORM, phiên bản, dialect Oracle và driver JDBC. Không suy ra hiệu năng chỉ từ tên strategy; cần đo với phiên bản thực tế.

### 11.3. Dùng transaction và FK đúng cách

Sau khi nhận ID cha, ứng dụng có thể dùng ID đó để INSERT hàng con trong cùng transaction:

```sql
INSERT INTO orders (customer_id, total_amount)
VALUES (:customer_id, :amount)
RETURNING order_id INTO :order_id;

INSERT INTO order_items (order_id, product_id, quantity)
VALUES (:order_id, :product_id, :quantity);
```

Nếu INSERT hàng con thất bại, transaction có thể ROLLBACK để không giữ một đơn hàng thiếu chi tiết nếu nghiệp vụ yêu cầu atomicity. Giá trị sequence/identity đã cấp có thể vẫn tạo gap sau rollback.

### 11.4. Idempotency không phải chỉ là có PK

Một API tạo đơn hàng có thể bị client retry do timeout dù lần đầu đã commit. PK mới mỗi lần không ngăn hai đơn hàng trùng nghiệp vụ.

Dùng idempotency key hoặc request ID có UNIQUE constraint để nhận diện cùng một yêu cầu retry. Khóa định danh hàng và khóa chống xử lý trùng là hai mục đích khác nhau.

## 12. Migration và vận hành

### 12.1. Từ sequence/trigger sang identity

Trước khi đổi:
1. Kiểm kê mọi INSERT đang truyền ID.
2. Xác định trigger nào đang cấp số.
3. Xác định ứng dụng có gọi sequence trực tiếp hay dùng CURRVAL không.
4. Kiểm tra dữ liệu hiện tại và giá trị lớn nhất.
5. Xác định có cần giữ ID trong import/replication không.
6. Kiểm tra Oracle release hỗ trợ identity.
7. Lập kế hoạch chuyển đổi, kiểm thử rollback và deployment.

Không chỉ xóa trigger rồi thêm identity mà không kiểm tra client. Ứng dụng có thể vẫn truyền ID hoặc gọi sequence cũ.

### 12.2. BY DEFAULT và dữ liệu import

Nếu chọn `BY DEFAULT`, ID tường minh được chấp nhận. Sau khi import giá trị lớn, cần bảo đảm giá trị identity sinh tiếp theo không va chạm với dữ liệu đã nạp.

Tùy phiên bản Oracle và cách migration, có thể cần điều chỉnh identity generator theo cú pháp được hỗ trợ. Hãy tra tài liệu đúng release và thử trên bản sao schema. Không truy cập trực tiếp sequence nội bộ `ISEQ$$_...` để sửa nếu Oracle không công bố đó là API quản trị được hỗ trợ.

### 12.3. Sequence hiện có và giá trị bắt đầu

Khi tạo sequence cho bảng đã có dữ liệu, `START WITH` phải được chọn để không đụng các ID hiện hữu. Ví dụ nếu ID lớn nhất là 50000, sequence mới có thể bắt đầu ở giá trị cao hơn theo quy trình migration.

Không dùng `MAX(id)` trong ứng dụng runtime để cấp ID; truy vấn MAX chỉ có thể là một bước migration được khóa và kiểm soát để xác định mốc bắt đầu.

### 12.4. Backup và restore

Sequence/identity là metadata database và cần được đưa vào quy trình export/import, schema deployment và backup phù hợp. Khi restore hoặc đồng bộ môi trường, kiểm tra:
- Identity generation mode.
- Sequence increment/cache/cycle.
- Giá trị tiếp theo so với dữ liệu đã nạp.
- Trigger/default liên quan.
- PK/UK constraint.
- Quyền truy cập sequence nếu sequence tường minh.

## 13. Quy trình chọn chiến lược sinh khóa

Dùng các câu hỏi sau:

1. **ID có cần tạo trước khi INSERT không?** Nếu không, identity thường đơn giản; nếu có, sequence hoặc ID ứng dụng phù hợp hơn.
2. **Một bảng hay nhiều bảng dùng chung dãy số?** Một bảng: identity; dùng chung: sequence.
3. **Nhiều node tạo dữ liệu offline?** Cân nhắc UUID hoặc distributed ID.
4. **Có phải giữ ID từ hệ thống cũ?** Cân nhắc BY DEFAULT/ON NULL hoặc staging + mapping, kèm kiểm soát collision.
5. **Có yêu cầu số chứng từ liên tục?** Thiết kế bộ đánh số nghiệp vụ riêng, không dựa vào identity/sequence PK.
6. **Cần throughput insert cao?** Đo identity/sequence với cache phù hợp trước khi chọn UUID.
7. **Có ORM hoặc connection pool?** Kiểm tra strategy, driver và cách lấy generated key.
8. **Business key có ổn định không?** Dù dùng surrogate PK, vẫn đặt UNIQUE constraint cho business key khi cần.

### 13.1. Ma trận gợi ý

| Nhu cầu | Chiến lược thường phù hợp |
| --- | --- |
| PK số tự sinh cho một bảng | Identity |
| Cần lấy số trước INSERT | Sequence |
| Nhiều bảng dùng chung bộ sinh | Sequence |
| Schema legacy có trigger | Sequence, hoặc migration có kế hoạch |
| Tạo ID offline/distributed | UUID hoặc distributed ID |
| Import cần giữ ID cũ | Staging/mapping hoặc identity BY DEFAULT được kiểm soát |
| Mã nghiệp vụ ổn định | Natural/business key với UNIQUE |
| Số chứng từ theo quy định | Bộ cấp số nghiệp vụ riêng |

Đây là gợi ý theo mục tiêu phổ biến; cần cân nhắc version Oracle, framework, workload và quy định nghiệp vụ cụ thể.

## 14. Bài thực hành tổng hợp

### Bài 1 — Tạo bảng identity ALWAYS

```sql
CREATE TABLE demo_identity_always (
    id NUMBER GENERATED ALWAYS AS IDENTITY,
    name VARCHAR2(100) NOT NULL,
    CONSTRAINT pk_demo_identity_always PRIMARY KEY (id)
);

INSERT INTO demo_identity_always (name)
VALUES ('Alpha');

SELECT * FROM demo_identity_always;
```

Thử INSERT giá trị tường minh cho `ID` và quan sát Oracle từ chối.

### Bài 2 — BY DEFAULT

```sql
CREATE TABLE demo_identity_default (
    id NUMBER GENERATED BY DEFAULT AS IDENTITY,
    name VARCHAR2(100),
    CONSTRAINT pk_demo_identity_default PRIMARY KEY (id)
);

INSERT INTO demo_identity_default (name) VALUES ('Generated');
INSERT INTO demo_identity_default (id, name) VALUES (9000, 'Explicit');
```

Giải thích vì sao giá trị tường minh được chấp nhận và vì sao phải kiểm soát collision.

### Bài 3 — BY DEFAULT ON NULL

```sql
CREATE TABLE demo_identity_null (
    id NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY,
    name VARCHAR2(100),
    CONSTRAINT pk_demo_identity_null PRIMARY KEY (id)
);

INSERT INTO demo_identity_null (name) VALUES ('Omitted');
INSERT INTO demo_identity_null (id, name) VALUES (NULL, 'Explicit null');
```

Quan sát cả hai hàng đều được Oracle sinh ID.

### Bài 4 — Tạo sequence và dùng NEXTVAL

```sql
CREATE SEQUENCE demo_order_seq
    START WITH 1
    INCREMENT BY 1
    CACHE 20
    NOCYCLE;

INSERT INTO demo_orders (order_id, description)
VALUES (demo_order_seq.NEXTVAL, 'First order');
```

Tạo bảng `DEMO_ORDERS` trước với PK tương ứng.

### Bài 5 — CURRVAL

Trong cùng session, gọi NEXTVAL trước rồi gọi CURRVAL. Mở session mới và thử CURRVAL trước NEXTVAL để quan sát lỗi. Giải thích tính session-local của CURRVAL.

### Bài 6 — Quan sát gap khi rollback

```sql
SELECT demo_order_seq.NEXTVAL FROM dual;
ROLLBACK;
SELECT demo_order_seq.NEXTVAL FROM dual;
```

Giải thích vì sao sequence không quay lại giá trị trước đó.

### Bài 7 — Lấy ID bằng RETURNING

```sql
DECLARE
    l_id NUMBER;
BEGIN
    INSERT INTO demo_orders (order_id, description)
    VALUES (demo_order_seq.NEXTVAL, 'Returning example')
    RETURNING order_id INTO l_id;

    DBMS_OUTPUT.PUT_LINE(l_id);
END;
/
```

Giải thích vì sao RETURNING tốt hơn SELECT MAX(order_id).

### Bài 8 — Trigger cấp ID

Tạo sequence và trigger `BEFORE INSERT` chỉ gán NEXTVAL khi ID là NULL. Thử INSERT bỏ cột ID và INSERT truyền ID tường minh. Phân tích rủi ro nếu import giá trị lớn hơn sequence hiện tại.

### Bài 9 — Kiểm tra identity metadata

```sql
SELECT table_name,
       column_name,
       generation_type,
       identity_options
FROM   user_tab_identity_cols
ORDER  BY table_name;
```

Quan sát generation mode và identity options.

### Bài 10 — So sánh RAW và VARCHAR2 UUID

Tạo hai bảng test: một bảng lưu UUID trong `RAW(16)`, một bảng lưu chuỗi 36 ký tự. So sánh dung lượng row/index và cách hiển thị. Không kết luận hiệu năng chỉ từ kích thước cột; hãy đo bằng dữ liệu đủ lớn và workload tương đương.

### Bài 11 — Kiểm tra business key

Tạo bảng customer với surrogate PK và UNIQUE constraint trên `(source_system, source_customer_id)`. Thử INSERT cùng source key hai lần và quan sát constraint ngăn dữ liệu trùng.

### Bài 12 — Thiết kế cho ứng dụng phân tán

Một service tạo event offline rồi đồng bộ về Oracle. So sánh:
- Sequence do database cấp khi đồng bộ.
- UUID do service tạo trước.
- Distributed ID gồm timestamp và node identifier.

Nêu ảnh hưởng đến tính duy nhất, index, retry, đồng bộ và vận hành.

## 15. Những nhầm lẫn thường gặp

**“Identity tự động là primary key.”** Identity sinh giá trị; PK/UK constraint vẫn cần khai báo để bảo vệ tính duy nhất.

**“Sequence và identity luôn tạo dãy liên tục.”** Không. Rollback, lỗi INSERT, cache và các nguyên nhân khác có thể tạo gap.

**“NOCACHE sẽ không còn gap.”** Không. NOCACHE không giải quyết gap do rollback hoặc giá trị đã lấy nhưng không sử dụng.

**“CURRVAL lấy được ID của session khác.”** Không. CURRVAL là giá trị NEXTVAL gần nhất trong session hiện tại.

**“SELECT MAX(id) là cách an toàn để lấy ID vừa INSERT.”** Không. Session khác có thể tạo ID lớn hơn giữa hai câu lệnh.

**“Sequence tăng dần nghĩa là COMMIT theo đúng thứ tự ID.”** Không. Thứ tự cấp số khác thứ tự hoàn tất transaction.

**“UUID không cần UNIQUE constraint.”** Vẫn cần constraint để database bảo vệ dữ liệu.

**“UUID luôn nhanh hơn NUMBER sequence.”** Không. UUID có thể tăng dung lượng khóa và ảnh hưởng locality của index; phải đo theo workload.

**“Trigger và identity nên cùng cấp số cho một cột.”** Không nên. Chọn một cơ chế chính để tránh logic trùng lặp hoặc ghi đè ngoài ý muốn.

**“Sequence có thể dùng thay số hóa đơn liên tục.”** Không. Sequence thông thường không cam kết gap-free; đánh số chứng từ cần quy tắc nghiệp vụ riêng.

## 16. Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — CREATE TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html): khai báo identity column và các thuộc tính cột.
- [Oracle Database SQL Language Reference — CREATE SEQUENCE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-SEQUENCE.html): START WITH, INCREMENT, CACHE, ORDER và các tùy chọn sequence.
- [Oracle Database SQL Language Reference — Sequence Pseudocolumns](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Sequence-Pseudocolumns.html): NEXTVAL và CURRVAL.
- [Oracle Database SQL Language Reference — INSERT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/INSERT.html): INSERT, default values và RETURNING.
- [Oracle Database Reference — USER_TAB_IDENTITY_COLS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_TAB_IDENTITY_COLS.html): metadata identity column.
- [Oracle Database SQL Language Reference — SYS_GUID](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SYS_GUID.html): tạo GUID kiểu RAW.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/): constraint, index và mô hình dữ liệu.

Khi chọn chiến lược sinh khóa, hãy bắt đầu từ yêu cầu của ứng dụng: ID chỉ cần khi INSERT, cần lấy trước, cần dùng chung giữa nhiều bảng hay phải được tạo ở nhiều node độc lập. Identity đơn giản cho PK số của một bảng; sequence linh hoạt cho các luồng cần kiểm soát NEXTVAL; UUID hoặc distributed ID hỗ trợ hệ thống phân tán. Dù chọn cách nào, hãy khai báo PK/UNIQUE constraint, lấy ID bằng RETURNING hoặc API generated-key phù hợp, và không nhầm khóa nội bộ với mã nghiệp vụ cần quy tắc đánh số riêng.
