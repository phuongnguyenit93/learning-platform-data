# Khóa ghép, độ rộng khóa và ảnh hưởng đến tham chiếu hoặc chỉ mục

## 1. Tại sao phải nhìn khóa từ cả mô hình logic lẫn mô hình vật lý?

Trong module `DATABASE_DATA_MODELING`, người học chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu có thể kiểm chứng: nhận diện thực thể, quan hệ, ràng buộc, chuẩn hóa, khóa, chỉ mục và lược đồ vật lý; đồng thời đối chiếu cách biểu diễn trong hệ quan hệ, document, đồ thị và phân tích. Trong bước **Mô hình vật lý**, lựa chọn một khóa không dừng ở câu hỏi “giá trị nào định danh được bản ghi?” mà còn gồm “khóa có bao nhiêu cột, rộng bao nhiêu byte, đi qua bao nhiêu bảng con và tạo ra những chỉ mục nào?”.

Ví dụ, một nền tảng bán hàng phục vụ nhiều nhà bán (*tenant*) có thể có mã sản phẩm `SKU-001` ở cả tenant A lẫn tenant B. `sku` một mình không duy nhất; cặp (`tenant_id`, `sku`) mới định danh sản phẩm **trong phạm vi toàn nền tảng**. Nếu dùng cặp này làm khóa chính, mọi bảng tham chiếu đến sản phẩm cần mang thông tin đủ để trỏ đúng tenant và SKU. Nếu dùng `product_id` làm khóa chính, vẫn phải bảo vệ quy tắc không trùng SKU bằng `UNIQUE(tenant_id, sku)`.

Ba quyết định cần phân biệt:

1. **Danh tính logic:** tập thuộc tính nào phân biệt hai thực thể theo nghiệp vụ, trong phạm vi nào?
2. **Khóa vật lý:** khai báo `PRIMARY KEY`/`UNIQUE` trên cột nào, kiểu và độ rộng ra sao, khóa ngoại tham chiếu thế nào?
3. **Đường truy cập:** thứ tự cột của khóa ghép có giúp truy vấn và join thực tế hay cần chỉ mục bổ sung?

Thiết kế đúng là giữ được tính duy nhất và toàn vẹn khi dữ liệu tăng, khi mã nghiệp vụ thay đổi và khi ứng dụng thêm nhiều luồng ghi.

## 2. Khóa ghép là gì? Đừng nhầm với khóa tổng hợp dạng chuỗi

**Khóa ghép** (*composite key*) là một khóa gồm **hai hoặc nhiều cột** được DBMS đánh giá chung. Nếu `tenant_id` và `sku` tạo thành khóa chính, mỗi giá trị trong cặp có thể lặp riêng, nhưng cả cặp không được trùng:

| `tenant_id` | `sku` | Có hợp lệ khi khóa chính là (`tenant_id`, `sku`)? |
|---:|---|---|
| 10 | `SP-001` | Hợp lệ |
| 10 | `SP-002` | Hợp lệ |
| 20 | `SP-001` | Hợp lệ, khác tenant |
| 10 | `SP-001` | Không hợp lệ, trùng cả cặp |

Ví dụ PostgreSQL 16:

```sql
CREATE TABLE product (
    tenant_id BIGINT NOT NULL,
    sku       VARCHAR(64) NOT NULL,
    name      TEXT NOT NULL,
    CONSTRAINT pk_product PRIMARY KEY (tenant_id, sku)
);
```

`PRIMARY KEY (tenant_id, sku)` vừa yêu cầu **cả hai cột không `NULL`**, vừa yêu cầu tổ hợp giá trị duy nhất. Không cần tạo thêm `UNIQUE (tenant_id, sku)` có đúng cùng khóa và cùng ngữ nghĩa.

**Không nên giả lập khóa ghép** bằng chuỗi `tenant_id || '-' || sku` hoặc băm một chuỗi ghép rồi coi nó là chứng cứ duy nhất. Nối chuỗi cần quy tắc dấu phân cách, thoát ký tự, mã hóa, chuẩn hóa và có thể gây nhầm như (`'A-B'`, `'C'`) với (`'A'`, `'B-C'`). Hàm băm còn có khả năng va chạm. DBMS đã có cơ chế ràng buộc nhiều cột: dùng trực tiếp nếu mục đích là duy nhất của một tổ hợp.

### 2.1. Khóa ghép, khóa ứng viên và khóa thay thế

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| Khóa ứng viên (*candidate key*) | Tập cột tối thiểu đủ phân biệt mỗi hàng | (`tenant_id`, `sku`) |
| Khóa chính (*primary key*) | Một khóa ứng viên được chọn làm định danh hàng chính thức, không `NULL` | `PRIMARY KEY (tenant_id, sku)` |
| Khóa duy nhất thay thế (*alternate key*) | Khóa ứng viên khác được bảo vệ bằng `UNIQUE` | `UNIQUE (tenant_id, external_ref)` nếu bất biến |
| Khóa kỹ thuật (*surrogate key*) | ID sinh riêng, không mang nghĩa nghiệp vụ | `product_id BIGINT` hoặc `UUID` |
| Khóa ngoại ghép (*composite foreign key*) | Nhóm cột ở bảng con cùng tham chiếu một khóa duy nhất hợp lệ ở bảng cha | (`tenant_id`, `sku`) ở `order_line` |

Một bảng chỉ có một `PRIMARY KEY` nhưng có thể có nhiều `UNIQUE`. Khóa ghép không nhất thiết là khóa chính: `UNIQUE (tenant_id, sku)` cũng bảo vệ quy tắc duy nhất trong tenant khi `product_id` được chọn làm khóa chính.

Độ “tối thiểu” trong khóa ứng viên thuộc ngữ nghĩa logic. Nếu `product_id` đã duy nhất toàn cục, tổ hợp (`tenant_id`, `product_id`) vẫn **duy nhất**, nhưng không phải khóa ứng viên tối thiểu về lý thuyết; có thể khai báo thêm `UNIQUE` trên tổ hợp vì nhu cầu kiểm tra khóa ngoại có cùng tenant.

## 3. Khi nào khóa ghép là thiết kế đúng?

Khóa ghép thường xuất hiện tự nhiên ở:

- **Dòng đơn hàng:** (`order_id`, `line_no`), nếu số dòng chỉ duy nhất trong từng đơn và không có yêu cầu định danh dòng độc lập.
- **Bảng liên kết nhiều–nhiều:** (`student_id`, `course_id`), khi một sinh viên chỉ có một lượt ghi danh cho một khóa học trong phạm vi mô hình; nếu có nhiều kỳ học, có thể cần thêm `term_id` hoặc một thực thể lần ghi danh.
- **Mã theo tenant:** (`tenant_id`, `sku`) hoặc (`tenant_id`, `invoice_no`), nếu cùng một mã có thể xuất hiện ở tenant khác.
- **Mã theo nguồn tích hợp:** (`source_system`, `source_record_id`), vì nhiều hệ thống ngoài có thể phát hành cùng một mã cục bộ.
- **Phiên bản có định danh riêng:** (`document_id`, `version_no`), khi mỗi phiên bản là một hàng và số phiên bản chỉ có nghĩa trong một tài liệu.

```mermaid
flowchart LR
    A["Yêu cầu: SKU chỉ duy nhất trong một tenant"] --> B["Khóa logic: tenant_id + sku"]
    B --> C{"SKU có thể đổi?"}
    C -- "Không, được quản trị ổn định" --> D["Có thể chọn PK ghép"]
    C -- "Có, thường xuyên đổi" --> E["Cân nhắc PK kỹ thuật"]
    D --> F["Bảng con tham chiếu đúng cả hai cột"]
    E --> G["Vẫn UNIQUE(tenant_id, sku)"]
    F --> H["Đo kích thước, join và kế hoạch truy vấn"]
    G --> H
```

**Khóa ghép không đồng nghĩa với khóa tốt:** thêm `created_at` vào tổ hợp để làm cho hàng “tình cờ duy nhất” có thể che giấu việc chưa hiểu danh tính nghiệp vụ. Cặp (`order_id`, `product_id`) cũng không phải khóa đúng nếu cùng sản phẩm có thể xuất hiện ở nhiều dòng đơn với mức giá hoặc chương trình khuyến mãi khác nhau. Hãy xác nhận quy tắc trước khi gắn `PRIMARY KEY`.

## 4. Khóa chính ghép và khóa ngoại ghép: toàn vẹn quan hệ

Khóa ngoại ghép yêu cầu **tổ hợp cột ở bảng con** tham chiếu đúng tổ hợp khóa duy nhất/khóa chính ở bảng cha. Nó không thể được thay bằng các khóa ngoại rời rạc mà vẫn giữ nguyên ngữ nghĩa.

Ví dụ sai về mặt mô hình: bảng `order_line` có `tenant_id` tham chiếu bảng `tenant` và `sku` tham chiếu một danh sách SKU toàn cục, nhưng hai khóa ngoại **không bảo đảm SKU thuộc đúng tenant của dòng đơn**. Khóa ngoại `FOREIGN KEY (tenant_id, sku) REFERENCES product(tenant_id, sku)` giải quyết quan hệ cần bảo vệ.

### 4.1. Ví dụ hoàn chỉnh trên PostgreSQL 16: khóa ghép theo tenant

Giả định: mỗi tenant tự quản lý SKU và mã đơn; mỗi đơn có nhiều dòng; một dòng thuộc đúng tenant của đơn và của sản phẩm; số dòng bắt đầu từ 1. Các mã nghiệp vụ trong ví dụ được xem là ổn định trong thời gian giao dịch còn tham chiếu đến chúng.

```sql
CREATE TABLE tenant (
    tenant_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_code VARCHAR(40) NOT NULL UNIQUE
);

CREATE TABLE product (
    tenant_id    BIGINT NOT NULL,
    sku          VARCHAR(64) NOT NULL,
    display_name TEXT NOT NULL,
    CONSTRAINT pk_product PRIMARY KEY (tenant_id, sku),
    CONSTRAINT fk_product_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenant(tenant_id),
    CONSTRAINT ck_product_sku_nonblank
        CHECK (char_length(btrim(sku)) > 0)
);

CREATE TABLE sales_order (
    tenant_id  BIGINT NOT NULL,
    order_no   VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_sales_order PRIMARY KEY (tenant_id, order_no),
    CONSTRAINT fk_order_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenant(tenant_id)
);

CREATE TABLE sales_order_line (
    tenant_id  BIGINT NOT NULL,
    order_no   VARCHAR(40) NOT NULL,
    line_no    INTEGER NOT NULL,
    sku        VARCHAR(64) NOT NULL,
    quantity   INTEGER NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL,

    CONSTRAINT pk_sales_order_line
        PRIMARY KEY (tenant_id, order_no, line_no),
    CONSTRAINT fk_line_order
        FOREIGN KEY (tenant_id, order_no)
        REFERENCES sales_order (tenant_id, order_no)
        ON DELETE RESTRICT,
    CONSTRAINT fk_line_product
        FOREIGN KEY (tenant_id, sku)
        REFERENCES product (tenant_id, sku)
        ON DELETE RESTRICT,
    CONSTRAINT ck_line_no_positive CHECK (line_no > 0),
    CONSTRAINT ck_line_quantity_positive CHECK (quantity > 0),
    CONSTRAINT ck_line_unit_price_nonnegative CHECK (unit_price >= 0)
);

-- Khóa chính đã hỗ trợ tìm dòng theo (tenant_id, order_no).
-- Bổ sung đường tìm theo sản phẩm trong từng tenant khi truy vấn cần.
CREATE INDEX idx_line_tenant_sku
    ON sales_order_line (tenant_id, sku);
```

Giải thích:

1. Hai hàng `product` có `sku = 'P-01'` ở hai tenant khác nhau là hợp lệ; hai hàng có cùng (`tenant_id`, `sku`) bị từ chối.
2. `PRIMARY KEY (tenant_id, order_no, line_no)` cho phép `line_no = 1` xuất hiện ở nhiều đơn, nhưng không thể xuất hiện hai lần trong một đơn thuộc cùng tenant.
3. Cột `tenant_id` trong `sales_order_line` được **tái sử dụng** ở hai khóa ngoại ghép. Do đó một dòng không thể thuộc đơn tenant A nhưng chọn sản phẩm của tenant B.
4. PostgreSQL tạo chỉ mục duy nhất cho các `PRIMARY KEY` ở bảng cha. Tuy nhiên, PostgreSQL **không mặc định tạo chỉ mục ở phía bảng con** chỉ vì có `FOREIGN KEY`. `idx_line_tenant_sku` hỗ trợ tra dòng theo sản phẩm và có thể giúp giảm chi phí kiểm tra khi thay đổi/xóa sản phẩm.
5. Trên bảng dòng đơn, khóa chính ba cột đã cung cấp đường truy cập theo (`tenant_id`, `order_no`) và theo đủ ba cột. Thêm một chỉ mục B-tree trùng đúng ba cột mà không có nhu cầu khác sẽ gây chi phí ghi và lưu trữ dư thừa.

### 4.2. Thứ tự và tính tương thích của các cột khóa ngoại

Trong PostgreSQL, mỗi cặp cột tương ứng của khóa ngoại phải dùng kiểu dữ liệu và toán tử so sánh tương thích; khóa ngoại ghép phải tham chiếu tập cột có một ràng buộc duy nhất, khóa chính hoặc chỉ mục unique đủ điều kiện ở bảng cha. Thứ tự cột trong `FOREIGN KEY (tenant_id, sku) REFERENCES product(tenant_id, sku)` **xác định cặp tương ứng**, không chỉ là tên để đọc cho dễ.

Ví dụ, mã `tenant_id` là `BIGINT` thì đừng tùy tiện định nghĩa bản sao ở bảng con thành `VARCHAR` rồi phụ thuộc ép kiểu. Với chuỗi, charset/collation và quy tắc so sánh cũng có thể ảnh hưởng tương thích và tính duy nhất tùy DBMS.

### 4.3. `NULL` và hành vi mặc định của khóa ngoại ghép

Đây là một bẫy quan trọng. Trong PostgreSQL, khóa ngoại ghép mặc định dùng `MATCH SIMPLE`: **nếu bất kỳ cột tham chiếu nào là `NULL`, ràng buộc tham chiếu có thể được bỏ qua cho hàng đó**. Với một quan hệ bắt buộc, khai báo `NOT NULL` cho từng cột như ví dụ ở trên.

Nếu một tham chiếu ghép **có thể không tồn tại**, cần quy định rõ “cả hai cột cùng vắng” hay “một cột có, một cột thiếu”. PostgreSQL hỗ trợ `MATCH FULL` để ngăn trường hợp chỉ một phần của tổ hợp có `NULL`, trong khi cho phép cả tổ hợp đều `NULL`:

```sql
-- Minh họa riêng cho trường hợp tham chiếu tùy chọn.
CREATE TABLE external_reference (
    tenant_id BIGINT,
    sku       VARCHAR(64),
    note      TEXT,
    CONSTRAINT fk_external_reference_product
        FOREIGN KEY (tenant_id, sku)
        REFERENCES product (tenant_id, sku)
        MATCH FULL
);
```

Trong bảng `external_reference`, (`NULL`, `NULL`) biểu diễn không có tham chiếu và được phép; (`10`, `NULL`) hoặc (`NULL`, `'P-01'`) bị từ chối; (`10`, `'P-01'`) phải tồn tại ở bảng `product`. Không giả định mọi DBMS diễn giải hoặc hỗ trợ cú pháp `MATCH FULL` giống PostgreSQL.

## 5. Độ rộng khóa: chi phí lan qua chỉ mục và tham chiếu

Giả sử dùng khóa chính `BIGINT` 8 byte thay cho khóa ghép (`tenant_id BIGINT`, `order_no VARCHAR(40)`). Khóa ghép có ít nhất một giá trị số 8 byte cùng chuỗi độ dài biến thiên, và chuỗi có thể dùng nhiều byte khi mã hóa Unicode. Chi phí không dừng ở bảng cha:

- **Chỉ mục unique/primary:** mỗi mục chỉ mục cần lưu giá trị các thành phần khóa và thông tin cấu trúc của chỉ mục.
- **Bảng con:** mỗi hàng tham chiếu phải lưu các cột khóa ngoại. Với quan hệ một-nhiều có hàng chục triệu dòng con, việc lặp một khóa dài có thể tạo chi phí lớn.
- **Chỉ mục trên FK:** có thể lưu lại cùng các thành phần khóa để phục vụ join và kiểm tra thay đổi ở bảng cha.
- **Join, sort, hash, truyền dữ liệu:** khóa rộng ảnh hưởng kích thước giá trị, so sánh, cache và dữ liệu truyền giữa các tầng.
- **Chuyển đổi khóa:** nếu một thành phần khóa nghiệp vụ thay đổi, cập nhật phải tính đến các khóa ngoại, chỉ mục và bản sao dữ liệu.

Ví dụ đánh giá **mang tính minh họa**, chưa phải phép đo dung lượng:

| Phương án định danh dòng đơn | Các thành phần khóa | Độ rộng dữ liệu khóa theo kiểu |
|---|---|---|
| ID kỹ thuật | `line_id BIGINT` | 8 byte giá trị số |
| Khóa ghép số | `tenant_id BIGINT`, `order_id BIGINT`, `line_no INTEGER` | 8 + 8 + 4 = 20 byte giá trị số, **chưa tính overhead** |
| Khóa ghép với chuỗi | `tenant_id BIGINT`, `order_no VARCHAR(40)`, `line_no INTEGER` | 8 byte + byte của chuỗi + 4 byte, **chưa tính overhead** |
| UUID kỹ thuật | `line_id UUID` | 16 byte giá trị UUID |

Không lấy các tổng trong bảng làm kích thước mục B-tree hay hàng thật: DBMS còn lưu thông tin hàng/chỉ mục, null bitmap, alignment, metadata, cơ chế nén và đôi khi giá trị nằm ngoài trang. Chuỗi `VARCHAR(40)` là giới hạn về **số ký tự theo quy tắc DBMS**, không cố định 40 byte; byte thực tế phụ thuộc mã hóa và nội dung.

Giả sử 20 triệu dòng con đều giữ thêm trung bình 32 byte dữ liệu khóa so với phương án ngắn hơn thì riêng phần chênh lý thuyết ở các hàng là 640 triệu byte (xấp xỉ 610 MiB), **chưa bao gồm chỉ mục, overhead hay nén**. Đây là một phép ước lượng để đặt câu hỏi về quy mô; kết luận thiết kế cần đo kích thước thực tế trên DBMS đích.

Độ rộng khóa không chỉ ảnh hưởng dung lượng. Khóa lớn khiến ít mục chỉ mục hơn nằm trên một trang, có thể tăng số trang cần đọc và làm giảm hiệu quả cache. Nhưng khóa ngắn hơn không tự động thắng mọi truy vấn: nếu ứng dụng liên tục tra theo (`tenant_id`, `sku`), dùng `product_id` làm PK vẫn cần chỉ mục unique cho cặp nghiệp vụ và có thể khiến một truy vấn phải dùng thêm bước tra cứu.

## 6. Thứ tự cột trong khóa ghép và nguyên tắc tiền tố

Hai chỉ mục B-tree `(tenant_id, order_no, line_no)` và `(order_no, tenant_id, line_no)` có thể bảo vệ cùng tính duy nhất khi dùng làm khóa, nhưng phục vụ **đường truy vấn khác nhau**. Với PostgreSQL B-tree, điều kiện trên các cột **đầu tiên** của khóa thường hữu ích nhất để giới hạn phạm vi duyệt chỉ mục; các cột phía sau tiếp tục giúp lọc/sắp xếp trong phạm vi đó.

Ví dụ khóa chính:

```sql
PRIMARY KEY (tenant_id, order_no, line_no)
```

| Truy vấn | Khả năng tận dụng khóa B-tree trên |
|---|---|
| `WHERE tenant_id = ?` | Có tiền tố đầu tiên; có thể quét các đơn/dòng của tenant |
| `WHERE tenant_id = ? AND order_no = ?` | Có hai cột đầu; phù hợp tra các dòng thuộc đơn |
| `WHERE tenant_id = ? AND order_no = ? ORDER BY line_no` | Thường phù hợp cả lọc và thứ tự `line_no` |
| `WHERE tenant_id = ? AND line_no = ?` | Có thể dùng phần tiền tố `tenant_id` nhưng không có `order_no` để thu hẹp liên tục |
| `WHERE order_no = ?` | Thiếu cột đầu; thường không hiệu quả bằng chỉ mục có `order_no` đứng đầu |
| `WHERE sku = ?` | `sku` không nằm trong khóa này; cần đường truy cập khác nếu truy vấn quan trọng |

Đừng biến quy tắc tiền tố thành khẳng định rằng DBMS “không bao giờ” dùng index khi thiếu cột đầu. Optimizer còn cân nhắc thống kê, scan toàn bộ index, các kiểu scan hoặc tối ưu đặc thù phiên bản. Điều quan trọng là **độ chọn lọc và số trang phải đọc**, không chỉ việc kế hoạch có ghi từ “Index Scan” hay không.

### 6.1. Chọn thứ tự cột theo đường truy cập

Với hệ multi-tenant, nhiều truy vấn có điều kiện `tenant_id` và một mã nghiệp vụ. Đặt `tenant_id` đứng đầu có thể thuận lợi cho truy vấn theo tenant, bảo vệ phạm vi dữ liệu và sắp xếp theo cột tiếp theo. Tuy nhiên:

- Nếu phần lớn truy vấn có **đủ các điều kiện bằng** trên nhiều cột, thứ tự cột có thể ít khác biệt hơn; xét tiếp yêu cầu `ORDER BY`, truy vấn theo tiền tố và tần suất đọc.
- Nếu luôn chỉ tìm một `order_id` duy nhất toàn cục, khóa `BIGINT` đơn có thể tốt hơn cho đường truy cập đó, trong khi unique theo tenant vẫn được giữ cho quy tắc nghiệp vụ.
- Không có quy tắc bất biến “luôn đặt cột có cardinality cao nhất lên trước”. Thứ tự cột phải dựa trên điều kiện lọc, sắp xếp, giới hạn, tham chiếu và kế hoạch trên dữ liệu thực.

Ví dụ truy vấn có thể được phục vụ bởi khóa chính của `sales_order_line`:

```sql
EXPLAIN
SELECT line_no, sku, quantity, unit_price
FROM sales_order_line
WHERE tenant_id = 42 AND order_no = 'SO-2027-0009'
ORDER BY line_no;
```

Để tra theo sản phẩm, chỉ mục `(tenant_id, sku)` ở bảng con phù hợp với truy vấn:

```sql
EXPLAIN
SELECT order_no, line_no, quantity
FROM sales_order_line
WHERE tenant_id = 42 AND sku = 'P-01';
```

`EXPLAIN` cho biết kế hoạch **dự kiến**, chưa có số liệu thời gian thực thi. Khi cần đo, `EXPLAIN (ANALYZE, BUFFERS)` sẽ thực sự chạy truy vấn, vì vậy chỉ dùng ở môi trường và tình huống có thể chấp nhận chi phí.

### 6.2. Thứ tự cột của `UNIQUE` và ngữ nghĩa duy nhất

`UNIQUE (tenant_id, sku)` và `UNIQUE (sku, tenant_id)` đều cấm cùng một cặp trùng khi các cột bắt buộc không `NULL`. Nhưng cấu trúc chỉ mục B-tree được tổ chức theo thứ tự khai báo. Không đảo cột chỉ để tìm kiếm nhanh hơn nếu nó làm mất đường truy cập cần thiết cho truy vấn tenant chính. Khi dùng FK ghép, cần đảm bảo ánh xạ giữa cột con và cột cha đúng thứ tự và phù hợp ràng buộc được DBMS chấp nhận.

## 7. Khi khóa kỹ thuật ngắn hơn là lựa chọn hợp lý

Nếu `sku` hoặc `order_no` có khả năng đổi, dùng chuỗi làm thành phần PK khiến nhiều FK và chỉ mục phụ thuộc vào giá trị mang nghĩa nghiệp vụ đó. Một phương án là tạo `product_id`/`order_id` `BIGINT` làm PK, giữ `UNIQUE(tenant_id, sku)` và `UNIQUE(tenant_id, order_no)` để không mất ràng buộc nghiệp vụ.

Ví dụ **phương án B độc lập** với các bảng ở mục 4; tên bảng được thêm hậu tố `_id` để có thể đối chiếu:

```sql
CREATE TABLE product_id (
    product_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL REFERENCES tenant(tenant_id),
    sku          VARCHAR(64) NOT NULL,
    display_name TEXT NOT NULL,
    CONSTRAINT uq_product_id_tenant_sku UNIQUE (tenant_id, sku),
    CONSTRAINT uq_product_id_tenant_product
        UNIQUE (tenant_id, product_id)
);

CREATE TABLE sales_order_id (
    order_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   BIGINT NOT NULL REFERENCES tenant(tenant_id),
    order_no    VARCHAR(40) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_order_id_tenant_no UNIQUE (tenant_id, order_no),
    CONSTRAINT uq_order_id_tenant_order
        UNIQUE (tenant_id, order_id)
);

CREATE TABLE sales_order_line_id (
    line_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id  BIGINT NOT NULL,
    order_id   BIGINT NOT NULL,
    line_no    INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity   INTEGER NOT NULL,
    CONSTRAINT uq_line_id_order_position
        UNIQUE (tenant_id, order_id, line_no),
    CONSTRAINT fk_line_id_order_same_tenant
        FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales_order_id (tenant_id, order_id),
    CONSTRAINT fk_line_id_product_same_tenant
        FOREIGN KEY (tenant_id, product_id)
        REFERENCES product_id (tenant_id, product_id),
    CONSTRAINT ck_line_id_number CHECK (line_no > 0),
    CONSTRAINT ck_line_id_quantity CHECK (quantity > 0)
);

CREATE INDEX idx_line_id_tenant_product
    ON sales_order_line_id (tenant_id, product_id);
```

**Điểm đánh đổi:** khóa chính của `product_id`/`sales_order_id` chỉ gồm 8 byte số nguyên, nên một tham chiếu đơn cột có thể ngắn. Nhưng để DBMS bảo vệ **không gắn dòng đơn của tenant này vào sản phẩm/đơn của tenant khác**, ví dụ vẫn khai báo FK ghép (`tenant_id`, `product_id`) và (`tenant_id`, `order_id`).

Vì PostgreSQL yêu cầu cặp cột được tham chiếu có khóa unique/primary phù hợp, ví dụ thêm `UNIQUE(tenant_id, product_id)` và `UNIQUE(tenant_id, order_id)`. Hai ràng buộc này **dư thừa về mặt duy nhất toán học** khi ID đã duy nhất toàn cục, nhưng có ích làm đích FK ghép và phát sinh **chỉ mục bổ sung thật**. Đừng bỏ qua chi phí đó khi so sánh với phương án khóa ghép hoàn toàn.

Một lựa chọn khác là dùng khóa chính ghép toàn số (`tenant_id`, `product_id`), hoặc dùng FK chỉ đến `product_id` rồi áp dụng kiểm soát cùng tenant bằng cơ chế khác được kiểm chứng. Mỗi phương án có độ phức tạp ứng dụng và chi phí chỉ mục khác nhau; quyết định phải xem xét ràng buộc toàn vẹn, truy vấn và vận hành cụ thể.

**Chú ý:** khóa ghép không chỉ xuất hiện khi dùng khóa nghiệp vụ. Ngay cả khi đã dùng surrogate ID, khóa ghép vẫn có thể cần để bảo vệ phạm vi tenant, thứ tự dòng, phiên bản hoặc tính duy nhất theo nguồn.

## 8. So sánh PostgreSQL, MySQL/InnoDB và SQL Server

Đặc điểm lưu trữ vật lý của một khóa có thể khác đáng kể giữa các hệ quản trị. Bảng dưới đây định hướng theo PostgreSQL 16, MySQL 8.0/InnoDB và SQL Server 2022; trước khi áp dụng phải kiểm tra phiên bản, cấu hình charset/collation, engine và loại index:

| Khía cạnh | PostgreSQL 16 | MySQL 8.0 / InnoDB | SQL Server 2022 |
|---|---|---|---|
| Khóa chính | Tạo chỉ mục unique B-tree theo mặc định, tách khỏi cách sắp hàng heap | Primary key thường là **clustered index** tổ chức dữ liệu theo khóa | PK là ràng buộc unique, có thể gắn với clustered hoặc nonclustered index theo thiết kế |
| Chỉ mục phụ | Thường chứa key và tham chiếu hàng; không mặc định lặp nguyên PK như InnoDB | Bản ghi secondary index lưu giá trị PK để định vị hàng, vì vậy PK rộng có thể làm phình nhiều secondary index | Chi phí phụ thuộc lựa chọn clustered key; khóa phân cụm có thể góp phần vào locator của nonclustered index |
| Khóa ngoại ghép | Hỗ trợ; FK không tự tạo index ở phía tham chiếu | Hỗ trợ với InnoDB, có các yêu cầu index/kiểu cột riêng và có thể tự tạo index hỗ trợ FK ở phía con nếu thiếu | Hỗ trợ; cần xét index phía con theo đường truy cập |
| Unique với `NULL` | Theo mặc định, nhiều `NULL` không bị xem là trùng; có tùy chọn khác ở các phiên bản phù hợp | Ngữ nghĩa nhiều `NULL` phụ thuộc khóa và DBMS; phải kiểm tra | Ngữ nghĩa unique và cách xử lý `NULL` khác PostgreSQL; cần kiểm thử trực tiếp |
| Giới hạn khóa index | Phụ thuộc trang, kiểu index và dữ liệu; khóa chuỗi quá dài có thể bị từ chối | Giới hạn độ dài key tính bằng byte và thay đổi theo cấu hình/engine | Có giới hạn byte của khóa index tùy loại index; INCLUDE và clustered/nonclustered có quy tắc riêng |
| Chuỗi và collation | `VARCHAR(n)`, `TEXT` và collation của DB/cột | `VARCHAR(n)` với charset như `utf8mb4`, collation tác động so sánh | `VARCHAR`/`NVARCHAR` với collation và quy tắc lưu trữ tương ứng |

**Hệ quả thực tế:** một PK ghép chứa chuỗi dài có thể tương đối chấp nhận được ở PostgreSQL với một số workload, nhưng gây chi phí cao trong InnoDB vì mọi secondary index mang theo PK; ngược lại, trên PostgreSQL cũng không có lý do cho rằng khóa ghép rộng luôn miễn phí. Với SQL Server, phải nêu rõ clustered key vì nó tác động tới locator của nhiều index.

Tránh ghi những ngưỡng như “mỗi khóa có tối đa N byte” theo cách áp dụng cho mọi phiên bản. Giới hạn có thể phụ thuộc kích thước trang, charset, kiểu index, cột INCLUDE, tiền tố và cấu hình. Việc tạo chỉ mục thành công trên dữ liệu thử ngắn cũng chưa chứng minh giá trị chuỗi ở giới hạn nghiệp vụ sẽ không gây lỗi khi insert sau này.

## 9. Thiết kế độ rộng và tính ổn định của các thành phần

Khi khóa ghép có chuỗi, hãy làm rõ:

1. **Miền giá trị:** chiều dài SKU tối đa là bao nhiêu? Có ràng buộc về ký tự hợp lệ? Có cho phép khoảng trắng đầu/cuối không?
2. **Quy tắc so sánh:** `abc` có trùng `ABC` không? Unicode có được chuẩn hóa về một dạng canonical trước khi lưu không? Collation có so sánh phân biệt dấu không?
3. **Tính bất biến:** thay đổi SKU có nghĩa là sửa tên mã của **cùng một sản phẩm** hay tạo danh tính sản phẩm mới? Quyết định này điều khiển thiết kế FK và lịch sử.
4. **Tác động tham chiếu:** có bao nhiêu bảng con, bao nhiêu hàng và bao nhiêu sự kiện ngoài DB đang chứa bản sao khóa?
5. **Tốc độ tăng:** thêm một thành phần vào khóa hôm nay có khiến mọi FK/API/export phải thay đổi khi phạm vi unique được mở rộng không?
6. **Giới hạn DBMS:** kiểu có đánh index được với độ dài tối đa không? Có cần một mã ngắn ổn định và một trường mô tả dài riêng?

Ví dụ, dùng `TEXT` dài hàng nghìn ký tự làm thành phần PK chỉ vì mã đối tác “có thể dài bất kỳ” là quyết định đáng nghi. Có thể lưu `external_ref` đầy đủ dưới dạng thuộc tính, kết hợp `source_system` để xác định phạm vi, dùng một surrogate ID ổn định cho liên kết nội bộ và đặt ràng buộc unique phù hợp nếu giới hạn index cho phép. Nếu buộc dùng biểu diễn băm để giảm chiều dài tra cứu, phải xét **va chạm và xác minh dữ liệu gốc**; chỉ một hash index không chứng minh không có hai mã khác nhau cùng hash.

Tránh dùng thông tin có thể thay đổi hoặc nhạy cảm như email, số điện thoại hay giấy tờ cá nhân làm thành phần khóa được sao chép khắp hệ thống. Tăng chi phí bảo mật và cập nhật thường lớn hơn lợi ích bỏ một cột ID kỹ thuật.

## 10. Đo chi phí thay vì chỉ tính trên giấy

Để đánh giá phương án khóa ghép với surrogate key, dựng hai phiên bản lược đồ trên một môi trường thử và nạp dữ liệu có phân bố tương đương. Đo theo cùng khối lượng và tỉ lệ đọc/ghi:

- Dung lượng hàng và tổng dung lượng index, đặc biệt khi bảng con lớn.
- Thời gian `INSERT`, `UPDATE` và thao tác xóa ở bảng cha có nhiều tham chiếu.
- Độ trễ tìm bản ghi theo ID, theo khóa nghiệp vụ, tìm tập dòng theo đơn và join sang sản phẩm.
- Kế hoạch và số buffer đọc của truy vấn phổ biến; chi phí bộ nhớ và sắp xếp.
- Ảnh hưởng của số lượng index bổ sung, độ dài chuỗi thật, phân bố tenant và lịch sử cập nhật mã.

Với PostgreSQL:

```sql
-- Kích thước bảng gồm heap, TOAST và toàn bộ chỉ mục.
SELECT
    pg_size_pretty(pg_total_relation_size('public.sales_order_line')) AS total_size,
    pg_size_pretty(pg_indexes_size('public.sales_order_line')) AS indexes_size;

-- Xem các chỉ mục và thứ tự cột đã khai báo.
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'sales_order_line'
ORDER BY indexname;

-- Quan sát kế hoạch truy vấn tiêu biểu.
EXPLAIN (ANALYZE, BUFFERS)
SELECT line_no, sku, quantity
FROM sales_order_line
WHERE tenant_id = 42 AND order_no = 'SO-2027-0009'
ORDER BY line_no;
```

`pg_total_relation_size` gồm nhiều loại dung lượng; `pg_indexes_size` tính dung lượng chỉ mục. Không suy ra độ rộng trung bình chỉ từ hai con số khi dữ liệu nạp vào khác nhau, thiếu thống kê hoặc index chưa được sử dụng theo truy vấn. `EXPLAIN (ANALYZE, BUFFERS)` **thực thi truy vấn thật**: chỉ dùng trên truy vấn đọc hoặc môi trường kiểm thử có kiểm soát khi không muốn gây thay đổi ngoài ý muốn.

### Phân biệt ba mục tiêu tối ưu

| Mục tiêu | Điểm ưu tiên khi chọn khóa |
|---|---|
| Toàn vẹn nghiệp vụ | `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY` đúng phạm vi và đúng `NULL` |
| Hiệu năng truy cập | Độ rộng, thứ tự cột, đường truy vấn, số lượng index và cấu trúc của DBMS |
| Khả năng thay đổi | Khóa có ổn định, có nhân bản ra nhiều bảng/hệ thống, chi phí migration ra sao |

Không đánh đổi tính đúng đắn để tiết kiệm vài byte nếu thiếu nó sẽ cho phép dữ liệu chéo tenant hoặc tạo dòng đơn trùng. Ngược lại, một khóa ghép chuỗi dài không cần thiết có thể tạo chi phí lớn khi chỉ một surrogate ID và một `UNIQUE` ngắn hơn vẫn giữ được quy tắc logic.

## 11. Migration khi thay đổi khóa và tham chiếu

Giả sử hệ thống ban đầu dùng `product(tenant_id, sku)` làm PK, nhưng sau này đối tác cần đổi SKU và đã có hàng chục triệu dòng đơn lưu khóa ghép. Thay PK trực tiếp bằng `product_id` rồi xóa hai cột ở bảng con sẽ làm đứt liên kết. Cần một lộ trình có thể đối soát:

1. **Khảo sát:** liệt kê mọi bảng con, FK, unique constraint, index, API, cache, bản ghi sự kiện và dữ liệu xuất chứa (`tenant_id`, `sku`).
2. **Mở rộng schema:** thêm `product_id` dạng nullable trước nếu cần, cấp giá trị cho các hàng cũ; tạo ràng buộc unique của `product_id` và quy tắc nghiệp vụ trên (`tenant_id`, `sku`).
3. **Backfill tham chiếu:** thêm `product_id` vào bảng con và điền bằng join có điều kiện tenant và SKU. Dùng lô nhỏ với checkpoint khi dữ liệu lớn.
4. **Ghi đồng thời có kiểm soát:** sửa ứng dụng hoặc quy trình chuyển tiếp để mọi bản ghi mới giữ cả tham chiếu cũ và mới nhất quán; kiểm soát race condition trong thời gian migration.
5. **Đối soát:** xác minh không có product ID thiếu, không có tham chiếu chéo tenant, không tạo dòng con mồ côi và mã nghiệp vụ không trùng trong tenant.
6. **Siết ràng buộc và chuyển đọc:** áp FK mới, `NOT NULL` khi dữ liệu sạch, chuyển truy vấn/API theo lộ trình; chỉ bỏ FK và cột cũ khi toàn bộ consumer đã chuyển.
7. **Dự phòng và rollback:** kiểm thử khả năng quay về trong từng giai đoạn, thời gian khóa bảng và khối lượng ghi tăng do index mới.

Ví dụ truy vấn **chỉ để kiểm tra** sau khi backfill; giả sử bảng chuyển đổi đã có `product_id` bên cạnh `tenant_id` và `sku`:

```sql
-- Tìm các hàng thiếu ID mới hoặc trỏ sang sai sản phẩm.
SELECT l.tenant_id, l.order_no, l.line_no, l.sku, l.product_id
FROM sales_order_line AS l
LEFT JOIN product_id AS p
       ON p.tenant_id = l.tenant_id
      AND p.product_id = l.product_id
      AND p.sku = l.sku
WHERE l.product_id IS NULL
   OR p.product_id IS NULL;
```

Truy vấn trên là ví dụ cho **trạng thái đang migration**: cột `sales_order_line.product_id` chưa tồn tại ở DDL ban đầu và phải được thêm bằng bước mở rộng schema trước khi chạy. Kết quả rỗng chỉ xác minh một quan hệ tham chiếu hiện tại; cần kiểm tra thêm các bảng con khác, đối chiếu số lượng và quy tắc tenant trước khi hoàn tất.

Nếu yêu cầu chỉ là tăng `INTEGER` thành `BIGINT`, tác động vẫn lan sang các FK và API. Nếu đổi thứ tự cột của PK ghép, có thể phải tái tạo chỉ mục hoặc ràng buộc, nên đánh giá lợi ích truy vấn với chi phí migration. Không dùng `ON UPDATE CASCADE` như giải pháp mặc định cho các khóa nghiệp vụ thường xuyên đổi: cascade có thể tạo cập nhật lớn và vẫn không sửa dữ liệu đã phát ra ngoài DB.

## 12. Sai lầm thường gặp và cách kiểm chứng

| Sai lầm | Tác động | Cách xử lý |
|---|---|---|
| Chỉ đặt `UNIQUE(sku)` cho hệ nhiều tenant | Hai tenant không thể dùng cùng mã hợp lệ | Chốt phạm vi và dùng `UNIQUE(tenant_id, sku)` |
| Tạo hai FK riêng `tenant_id` và `sku` rồi coi là ràng buộc cùng tenant | Có thể tham chiếu sai sản phẩm của tenant khác | Dùng FK ghép tới khóa phù hợp |
| Để một phần của FK ghép `NULL` nhưng nghĩ FK vẫn kiểm tra toàn bộ | `MATCH SIMPLE` có thể bỏ qua việc tra cha | Dùng `NOT NULL` hoặc `MATCH FULL` theo chính sách |
| Chỉ chọn khóa ghép vì “không cần cột ID” | Dữ liệu khóa dài bị sao chép qua nhiều FK/index | Ước lượng và đo chi phí, cân nhắc surrogate + unique |
| Có PK `(tenant_id, order_no, line_no)` rồi tạo index giống hệt | Index trùng, tăng dung lượng và chi phí ghi | Kiểm tra index được PK tạo trước khi thêm |
| Mặc định chỉ mục ghép phục vụ hiệu quả mọi điều kiện ở từng cột | Truy vấn thiếu tiền tố có thể quét nhiều trang | Dùng thống kê truy vấn và `EXPLAIN` để chọn chỉ mục |
| Dùng chuỗi nối hoặc hash như duy nhất tuyệt đối | Có thể xung đột encoding/dấu phân cách hoặc hash collision | Dùng khóa ghép native; nếu hash để tăng tốc, xác thực giá trị gốc |
| Thay khóa nghiệp vụ mà không cập nhật tất cả FK và consumer | Mất liên kết lịch sử và dữ liệu mồ côi | Migration theo giai đoạn, đối soát và kiểm tra rollback |
| Giả định byte của `VARCHAR(n)` bằng `n` | Đánh giá sai dung lượng/index với Unicode | Kiểm tra charset, collation, dữ liệu thực và giới hạn DBMS |
| Cho rằng PK bảo vệ quyền truy cập theo tenant | Có thể vẫn đọc/ghi chéo tenant qua API | Kiểm tra phân quyền độc lập; dùng ràng buộc tenant để bảo vệ tính nhất quán |

## 13. Bài thực hành: lựa chọn và giải thích khóa

**Bối cảnh:** một nền tảng quản lý khóa học có nhiều tổ chức. Mỗi tổ chức dùng một mã học viên `student_code`; một học viên có thể tham gia cùng khóa học ở nhiều học kỳ. Mỗi lượt ghi danh lưu trạng thái, thời điểm đăng ký và điểm cuối kỳ. Nền tảng dự kiến có nhiều chục triệu bản ghi ghi danh, được truy vấn chủ yếu theo tổ chức, học viên, khóa học và học kỳ.

Yêu cầu nghiệp vụ:

- Hai tổ chức có thể dùng cùng `student_code`; trong một tổ chức, mã học viên chỉ thuộc một học viên còn hiệu lực theo chính sách định danh đã công bố.
- Trong một học kỳ, một học viên chỉ có tối đa một lượt ghi danh cho một khóa học; kỳ sau được ghi danh lại.
- Mã học viên có thể được thay đổi trong quá trình chuẩn hóa dữ liệu cũ, nhưng lịch sử ghi danh phải giữ liên kết.
- Hệ thống thường tra danh sách học viên của một khóa học theo tổ chức và học kỳ; đôi khi tra lịch sử của một học viên.

Hãy thực hiện:

1. Xác định khóa nghiệp vụ của `student` và `enrollment`. Đánh giá có dùng `student_id BIGINT` làm PK hay không; giải thích cách giữ `UNIQUE(tenant_id, student_code)`.
2. Đề xuất ít nhất hai thiết kế cho `enrollment`: khóa ghép gồm (`tenant_id`, `student_id`, `course_id`, `term_id`) và khóa `enrollment_id` kỹ thuật kèm `UNIQUE` tương ứng. Chỉ ra điều kiện khiến tổ hợp đó thật sự đủ phân biệt các lượt ghi danh.
3. Viết FK cần thiết để ngăn lượt ghi danh gắn học viên/khóa học của tenant khác. Giải thích vì sao FK tới `student_id` và `course_id` riêng không nhất thiết bảo vệ cùng tenant nếu bản ghi con còn lưu `tenant_id`.
4. Chọn thứ tự cột cho index truy vấn “danh sách học viên của một khóa trong một học kỳ” và index khác cho “lịch sử một học viên”. Xác định index nào đã được `PRIMARY KEY`/`UNIQUE` tạo ra để tránh trùng.
5. Ước lượng ảnh hưởng đến kích thước khóa ngoại và chỉ mục khi `student_code` dài 64 ký tự được dùng thay `student_id BIGINT`, và nêu phép đo sẽ tiến hành trên PostgreSQL/InnoDB.
6. Thiết kế kiểm thử cho giá trị trùng trong cùng tenant, trùng mã khác tenant, thay đổi mã học viên, FK chứa `NULL` và trường hợp cần migration.

### Checklist bàn giao mô hình vật lý

Trước khi chốt lược đồ, người thiết kế cần nêu rõ:

- **Danh tính:** khóa nào tối thiểu, phạm vi duy nhất, cột nào có thể đổi hoặc `NULL`.
- **Quan hệ:** từng FK tham chiếu đúng tổ hợp khóa cha, quy tắc `MATCH SIMPLE`/`MATCH FULL` hoặc tương đương được hiểu rõ.
- **Độ rộng:** kiểu dữ liệu, độ dài, charset/collation, số hàng con và chi phí chỉ mục được ước lượng rồi đo trên DBMS thực.
- **Truy vấn:** thứ tự cột khớp với tiền tố lọc và sắp xếp quan trọng; không tạo index trùng ràng buộc sẵn có.
- **Vận hành:** chiến lược cập nhật khóa, migration, rollback và kiểm thử dữ liệu chéo tenant/khóa ngoại mồ côi đã được chuẩn bị.

Khóa ghép là công cụ mạnh để biểu diễn **tính duy nhất có ngữ cảnh** và bảo vệ quan hệ; độ rộng và thứ tự các thành phần khóa lại quyết định nhiều chi phí vật lý. Khi xác định rõ phạm vi danh tính, đo chi phí lan qua tham chiếu và chỉ mục, và bảo vệ khóa nghiệp vụ ngay cả khi chọn surrogate key, lược đồ mới có thể vừa đúng yêu cầu vừa dễ tiến hóa.
