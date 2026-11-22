# NULL trong UNIQUE, CHECK và khóa ghép

Trong MySQL, \`NULL\` biểu thị giá trị chưa biết hoặc không hiện diện. Nó không phải số 0, chuỗi rỗng hay một giá trị mặc định. Vì SQL dùng logic ba giá trị (TRUE, FALSE, UNKNOWN), \`NULL\` ảnh hưởng trực tiếp đến điều kiện lọc, unique index, check constraint và khóa ghép.

Ba quy tắc cần nắm:

1. **UNIQUE:** MySQL cho phép nhiều hàng có giá trị \`NULL\` trong cột thuộc unique index. Với unique key nhiều cột, nếu một hoặc nhiều thành phần của khóa là \`NULL\`, nhiều tổ hợp có thể cùng tồn tại.
2. **CHECK:** MySQL chỉ từ chối hàng khi biểu thức CHECK cho kết quả FALSE. Kết quả TRUE hoặc UNKNOWN đều được chấp nhận. Vì vậy, \`CHECK (quantity > 0)\` không tự ngăn \`quantity\` nhận NULL.
3. **Khóa ghép:** mọi cột của composite primary key đều phải NOT NULL. Với composite foreign key, nếu một thành phần khóa ngoại là NULL, InnoDB không yêu cầu tìm thấy hàng cha tương ứng cho khóa đó.

Bài học thuộc phạm vi \`DATABASE_MYSQL\`: thiết kế bảng, khóa và ràng buộc dữ liệu; kiểm soát tính duy nhất, tính toàn vẹn tham chiếu và điều kiện nghiệp vụ; đồng thời biết kiểm tra metadata, truy vấn và migration để tránh dữ liệu sai khi hệ thống phát triển.

## 1. NULL khác gì 0, chuỗi rỗng và DEFAULT?

Các giá trị sau có ý nghĩa khác nhau:

| Giá trị | Ý nghĩa |
|---|---|
| \`NULL\` | Không có giá trị hoặc chưa biết giá trị |
| \`0\` | Một giá trị số bằng không |
| \`''\` | Chuỗi có độ dài bằng 0 |
| \`'NULL'\` | Chuỗi gồm bốn ký tự N, U, L, L |
| \`DEFAULT\` | Yêu cầu dùng giá trị mặc định đã khai báo cho cột |

Ví dụ:

~~~sql
CREATE TABLE profile (
    profile_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    age INT NULL,
    nickname VARCHAR(80) NULL,
    note VARCHAR(100) NOT NULL DEFAULT 'Chưa ghi chú'
);
~~~

Các hàng sau không tương đương:

~~~sql
INSERT INTO profile (profile_id, age, nickname)
VALUES
    (1, NULL, NULL),
    (2, 0, ''),
    (3, 25, 'An');
~~~

- Hàng 1 chưa có tuổi và nickname.
- Hàng 2 có tuổi bằng 0 và nickname là chuỗi rỗng.
- Hàng 3 có giá trị cụ thể.
- Cột \`note\` được lấy DEFAULT vì không xuất hiện trong danh sách INSERT.

Nếu khai báo cột cho phép NULL, việc bỏ cột khỏi INSERT thường dùng default đã khai báo; nếu không có default tường minh, mặc định của cột nullable là NULL. Nếu truyền rõ \`NULL\`, MySQL lưu NULL khi cột cho phép. Với cột NOT NULL, truyền NULL có thể bị từ chối hoặc được xử lý khác tùy SQL mode; hãy dùng strict mode và không dựa vào việc tự chuyển đổi giá trị.

Kiểm tra định nghĩa:

~~~sql
SHOW CREATE TABLE profile\\G
~~~

### 1.1. NULL không bằng NULL theo phép so sánh thông thường

Trong SQL:

~~~sql
SELECT
    NULL = NULL AS ordinary_equal,
    NULL <> NULL AS ordinary_not_equal,
    NULL IS NULL AS is_null,
    NULL <=> NULL AS null_safe_equal;
~~~

Hai biểu thức đầu trả về NULL (UNKNOWN), không phải TRUE hoặc FALSE. \`IS NULL\` trả về TRUE. Toán tử MySQL \`<=>\` là phép so sánh bằng an toàn với NULL (NULL-safe equality); nó trả về TRUE khi cả hai vế đều NULL.

Vì vậy, không viết:

~~~sql
SELECT *
FROM profile
WHERE age = NULL;
~~~

Hãy viết:

~~~sql
SELECT *
FROM profile
WHERE age IS NULL;
~~~

Và để tìm các giá trị đã có:

~~~sql
SELECT *
FROM profile
WHERE age IS NOT NULL;
~~~

### 1.2. Logic ba giá trị

SQL dùng ba trạng thái logic:

| Biểu thức | Kết quả |
|---|---|
| TRUE AND TRUE | TRUE |
| TRUE AND FALSE | FALSE |
| TRUE AND UNKNOWN | UNKNOWN |
| FALSE AND UNKNOWN | FALSE |
| TRUE OR UNKNOWN | TRUE |
| FALSE OR UNKNOWN | UNKNOWN |
| NOT UNKNOWN | UNKNOWN |

Trong mệnh đề \`WHERE\`, chỉ hàng có điều kiện TRUE được giữ lại. Hàng cho kết quả FALSE hoặc UNKNOWN đều bị loại.

Điều này giải thích vì sao:

~~~sql
SELECT *
FROM profile
WHERE age > 18;
~~~

không trả về hàng có \`age IS NULL\`: biểu thức \`NULL > 18\` cho kết quả UNKNOWN.

## 2. NULL trong UNIQUE một cột

Unique constraint đảm bảo các giá trị không NULL trong khóa là duy nhất theo quy tắc so sánh của kiểu dữ liệu/collation. Trong MySQL, NULL được xem là không xác định, vì vậy một unique index có thể chứa nhiều NULL.

Ví dụ:

~~~sql
CREATE TABLE employee (
    employee_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    tax_code VARCHAR(30) NULL,
    UNIQUE KEY uq_employee_tax_code (tax_code)
);
~~~

Các dòng sau có thể được chèn:

~~~sql
INSERT INTO employee (employee_id, tax_code)
VALUES
    (1, 'TX-001'),
    (2, NULL),
    (3, NULL);
~~~

Hai dòng có tax_code NULL không bị xem là bản sao vi phạm unique key. Nhưng dòng thứ tư sau đây bị từ chối:

~~~sql
INSERT INTO employee (employee_id, tax_code)
VALUES (4, 'TX-001');
~~~

Vì \`TX-001\` đã tồn tại.

### 2.1. Khi nào hành vi này hữu ích?

Nhiều NULL trong unique column là phù hợp khi thuộc tính chỉ có ở một số bản ghi:

- Mã số thuế chưa được cấp cho mọi đối tượng.
- Mã tham chiếu từ hệ thống bên ngoài chỉ có với một số giao dịch.
- Số giấy phép tùy chọn.
- Email phụ hoặc định danh tùy chọn.
- Mã giao dịch đối tác chỉ xuất hiện khi giao dịch đi qua đối tác đó.

Ví dụ, một khách hàng có thể chưa cung cấp mã số thuế. Hệ thống vẫn cần đảm bảo hai khách hàng không dùng chung một mã số thuế khi mã đã được cung cấp. Unique nullable column thể hiện đúng quy tắc này.

### 2.2. Khi nào cần NOT NULL UNIQUE?

Nếu nghiệp vụ yêu cầu mỗi hàng bắt buộc có một giá trị và giá trị đó không được trùng, phải kết hợp NOT NULL với UNIQUE:

~~~sql
CREATE TABLE login_account (
    account_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    username VARCHAR(80) NOT NULL,
    UNIQUE KEY uq_login_username (username)
);
~~~

Chỉ khai báo UNIQUE là chưa đủ để bắt buộc nhập giá trị. Nếu username có thể NULL, nhiều hàng vẫn có thể không có username.

## 3. NULL trong UNIQUE khóa ghép

Một composite unique key chứa nhiều cột. Trong MySQL, nếu một hoặc nhiều thành phần khóa là NULL, các hàng có thể lặp lại tổ hợp còn lại mà không vi phạm unique constraint.

Ví dụ:

~~~sql
CREATE TABLE external_reference (
    reference_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    tenant_id BIGINT UNSIGNED NOT NULL,
    external_code VARCHAR(80) NULL,
    UNIQUE KEY uq_tenant_external_code (tenant_id, external_code)
);
~~~

Có thể chèn:

~~~sql
INSERT INTO external_reference
    (reference_id, tenant_id, external_code)
VALUES
    (1, 10, 'A-100'),
    (2, 10, NULL),
    (3, 10, NULL),
    (4, 20, NULL);
~~~

Các hàng 2 và 3 có cùng tenant_id nhưng external_code đều NULL. Chúng vẫn được chấp nhận. Hàng 4 cũng được chấp nhận vì external_code NULL.

Ngược lại, hai hàng có cùng tenant_id và cùng external_code khác NULL sẽ vi phạm:

~~~sql
INSERT INTO external_reference
    (reference_id, tenant_id, external_code)
VALUES (5, 10, 'A-100');
~~~

### 3.1. Quy tắc theo từng trường hợp

Với unique key \`(tenant_id, external_code)\`:

| tenant_id | external_code | Kết quả |
|---:|---|---|
| 10 | \`A-100\` | Được nếu chưa tồn tại |
| 10 | \`A-100\` lần nữa | Vi phạm UNIQUE |
| 10 | NULL | Được |
| 10 | NULL lần nữa | Vẫn được |
| 20 | NULL | Được |
| NULL | \`A-100\` | Được nếu các cột cho phép NULL; các hàng có thành phần NULL có thể lặp lại |

Vì vậy, nếu tenant_id là thành phần bắt buộc của phạm vi duy nhất, phải khai báo \`NOT NULL\`. Nếu external_code là tùy chọn, hãy xác định rõ việc cho phép nhiều bản ghi chưa có mã trong cùng tenant có đúng nghiệp vụ hay không.

### 3.2. UNIQUE không có nghĩa là mọi tổ hợp đều khác nhau khi có NULL

Một cách hiểu sai phổ biến là composite UNIQUE sẽ ngăn hai hàng có cùng phần giá trị đã biết, bất kể các phần còn lại. Trong MySQL, NULL khiến điều kiện duy nhất không áp dụng như cách so sánh bằng thông thường.

Nếu nghiệp vụ muốn:

- Nhiều hàng chưa có mã ngoài: giữ external_code nullable và dùng unique như ví dụ.
- Mỗi hàng bắt buộc có mã: thêm NOT NULL.
- Chỉ cho phép một hàng chưa có mã trong mỗi tenant: phải thiết kế thêm quy tắc để biến trường hợp thiếu mã thành một khóa không NULL có thể kiểm soát; unique key thông thường không tự làm điều này.

Không dùng chuỗi rỗng thay NULL một cách tùy tiện. Chuỗi rỗng là một giá trị cụ thể và sẽ bị UNIQUE kiểm soát như các giá trị khác.

## 4. UNIQUE và collation của chuỗi

Unique index trên cột chuỗi tuân theo collation của cột. Nếu collation không phân biệt hoa/thường hoặc dấu, hai cách viết khác nhau có thể bị xem là cùng một giá trị.

Ví dụ:

~~~sql
CREATE TABLE member_name (
    member_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    username VARCHAR(80)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL,
    UNIQUE KEY uq_member_username (username)
);
~~~

Trong collation không phân biệt dấu và hoa/thường, \`'Admin'\` và \`'admin'\` có thể xung đột. Các biến thể dấu cũng có thể được xem là tương đương.

Điều này độc lập với quy tắc NULL: unique key vừa xét giá trị NULL, vừa xét quy tắc so sánh của collation cho các giá trị chuỗi đã có.

Trước khi thay đổi collation, hãy tìm các giá trị sẽ trở thành trùng theo collation đích:

~~~sql
SELECT
    username COLLATE utf8mb4_0900_ai_ci AS normalized_compare,
    COUNT(*) AS total
FROM member_name
GROUP BY username COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
~~~

Đây là kiểm tra dữ liệu trước migration. Cần xử lý trùng theo quy tắc nghiệp vụ trước khi xây dựng lại unique index.

## 5. NULL trong CHECK constraint

CHECK constraint xác nhận biểu thức của một hàng. Trong MySQL, biểu thức CHECK được chấp nhận nếu kết quả TRUE hoặc UNKNOWN; chỉ kết quả FALSE làm hàng bị từ chối.

Đây là điểm quan trọng nhất khi dùng CHECK cùng cột nullable.

### 5.1. CHECK có thể không ngăn NULL

Ví dụ:

~~~sql
CREATE TABLE product (
    product_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    quantity INT NULL,
    CONSTRAINT chk_product_quantity
        CHECK (quantity > 0)
);
~~~

Bạn có thể chèn:

~~~sql
INSERT INTO product (product_id, quantity)
VALUES
    (1, 5),
    (2, 1),
    (3, NULL);
~~~

Hàng 3 được chấp nhận vì \`NULL > 0\` cho kết quả UNKNOWN, không phải FALSE.

Nếu nghiệp vụ yêu cầu quantity bắt buộc có giá trị dương, cần khai báo cả hai điều kiện:

~~~sql
CREATE TABLE product_required (
    product_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    quantity INT NOT NULL,
    CONSTRAINT chk_product_required_quantity
        CHECK (quantity > 0)
);
~~~

\`NOT NULL\` bảo đảm có giá trị; \`CHECK\` bảo đảm giá trị đó lớn hơn 0. Hai ràng buộc giải quyết hai vấn đề khác nhau.

### 5.2. CHECK với cột tùy chọn

Nếu quantity có thể không được xác định, nhưng khi có giá trị thì phải lớn hơn 0, thiết kế nullable cộng CHECK là hợp lý:

~~~sql
CREATE TABLE product_optional (
    product_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    estimated_quantity INT NULL,
    CONSTRAINT chk_estimated_quantity
        CHECK (estimated_quantity IS NULL OR estimated_quantity > 0)
);
~~~

Biểu thức nói rõ ý định: chấp nhận NULL hoặc một số dương.

Trong trường hợp này, điều kiện vẫn đúng khi giá trị NULL vì vế \`IS NULL\` là TRUE.

### 5.3. CHECK cho khoảng giá trị

Nếu giá trị bắt buộc:

~~~sql
CREATE TABLE rating (
    rating_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    score DECIMAL(3, 1) NOT NULL,
    CONSTRAINT chk_rating_score
        CHECK (score >= 0 AND score <= 10)
);
~~~

Nếu giá trị tùy chọn:

~~~sql
CREATE TABLE optional_rating (
    rating_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    score DECIMAL(3, 1) NULL,
    CONSTRAINT chk_optional_rating_score
        CHECK (score IS NULL OR (score >= 0 AND score <= 10))
);
~~~

Không nên nghĩ rằng \`CHECK (score BETWEEN 0 AND 10)\` tự động cấm NULL. Khi score là NULL, biểu thức BETWEEN cũng cho UNKNOWN và được chấp nhận.

### 5.4. CHECK không thay thế UNIQUE

CHECK chỉ kiểm tra biểu thức của hàng đang được INSERT hoặc UPDATE. Nó không thể đảm bảo một giá trị không trùng với hàng khác. Để kiểm tra tính duy nhất giữa các hàng, dùng UNIQUE hoặc PRIMARY KEY.

Ví dụ, CHECK sau không bảo đảm username không trùng:

~~~sql
CHECK (username <> '')
~~~

Nó chỉ kiểm tra username của chính hàng đó khác chuỗi rỗng. Muốn không trùng, phải tạo unique index:

~~~sql
UNIQUE KEY uq_username (username)
~~~

Nếu username bắt buộc, thêm NOT NULL.

### 5.5. CHECK không kiểm tra quan hệ giữa nhiều hàng hoặc nhiều bảng

CHECK constraint không phải công cụ cho các quy tắc cần đọc dữ liệu từ hàng khác hoặc bảng khác. Không dùng CHECK để kiểm tra:

- Mỗi khách hàng chỉ có tối đa một đơn hàng đang mở.
- Tổng chi tiết đơn hàng không vượt ngân sách ở bảng khác.
- Mã cha phải tồn tại trong bảng khác.
- Tổng số lượng trên nhiều dòng phải nhỏ hơn giới hạn.

Dùng UNIQUE, FOREIGN KEY, transaction, trigger hoặc logic nghiệp vụ thích hợp tùy quy tắc. Với tính toàn vẹn tham chiếu, ưu tiên FOREIGN KEY khi mô hình và engine hỗ trợ.

## 6. CHECK khi nhiều cột có thể NULL

Khi biểu thức chứa nhiều cột nullable, UNKNOWN có thể xuất hiện ở những trường hợp không mong muốn. Cách tốt nhất là viết điều kiện thể hiện rõ trạng thái NULL hợp lệ.

### 6.1. Hai cột phải cùng có hoặc cùng không có giá trị

Giả sử một bản ghi có khoảng thời gian bắt đầu và kết thúc. Nghiệp vụ cho phép cả hai chưa xác định, hoặc cả hai phải có giá trị và ngày bắt đầu không sau ngày kết thúc.

~~~sql
CREATE TABLE booking_window (
    window_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    starts_at DATETIME NULL,
    ends_at DATETIME NULL,
    CONSTRAINT chk_window_pair
        CHECK (
            (starts_at IS NULL AND ends_at IS NULL)
            OR
            (
                starts_at IS NOT NULL
                AND ends_at IS NOT NULL
                AND starts_at <= ends_at
            )
        )
);
~~~

Biểu thức này xử lý rõ ba trường hợp:

| starts_at | ends_at | Kết quả |
|---|---|---|
| NULL | NULL | Hợp lệ |
| Có giá trị | Có giá trị, starts_at <= ends_at | Hợp lệ |
| Có giá trị | NULL | Không hợp lệ |
| NULL | Có giá trị | Không hợp lệ |
| Có giá trị | Có giá trị, starts_at > ends_at | Không hợp lệ |

Dùng \`IS NULL\` và \`IS NOT NULL\` giúp biểu thức không bị UNKNOWN ở phần kiểm tra cặp giá trị.

### 6.2. Ít nhất một trong hai cột phải có giá trị

Ví dụ một liên hệ phải có email hoặc số điện thoại:

~~~sql
CREATE TABLE contact (
    contact_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    email VARCHAR(254) NULL,
    phone VARCHAR(30) NULL,
    CONSTRAINT chk_contact_method
        CHECK (email IS NOT NULL OR phone IS NOT NULL)
);
~~~

Biểu thức chỉ từ chối khi cả hai đều NULL. Nếu có một giá trị, điều kiện đúng.

Lưu ý: \`NOT NULL\` không đồng nghĩa chuỗi không rỗng. Nếu email hoặc phone không được là chuỗi rỗng, cần thêm điều kiện:

~~~sql
CHECK (
    (email IS NULL OR email <> '')
    AND
    (phone IS NULL OR phone <> '')
)
~~~

Và giữ CHECK yêu cầu ít nhất một trong hai trường có giá trị. Với nghiệp vụ thực tế, còn cần kiểm tra định dạng email/phone ở tầng phù hợp.

### 6.3. Chính xác một trong hai cột phải có giá trị

Nếu chỉ một phương thức liên hệ được phép có mặt:

~~~sql
CHECK (
    (email IS NOT NULL AND phone IS NULL)
    OR
    (email IS NULL AND phone IS NOT NULL)
)
~~~

Không viết \`CHECK (email <> phone)\` để diễn đạt điều này. Nếu một vế NULL, phép so sánh có thể cho UNKNOWN và không biểu đạt quy tắc mong muốn.

## 7. NULL trong composite PRIMARY KEY

Primary key xác định duy nhất mỗi hàng và không cho phép NULL. Với composite primary key, tất cả các cột cấu thành khóa đều phải NOT NULL.

Ví dụ:

~~~sql
CREATE TABLE order_item (
    order_id BIGINT UNSIGNED NOT NULL,
    line_number INT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    PRIMARY KEY (order_id, line_number),
    CONSTRAINT chk_order_item_quantity CHECK (quantity > 0)
);
~~~

Khóa chính là tổ hợp \`(order_id, line_number)\`. Mỗi cột đều bắt buộc có giá trị. Không thể có hai dòng cùng một order_id và line_number.

Nếu bỏ NOT NULL trong khai báo cột thuộc primary key, MySQL vẫn áp đặt tính không NULL cho các cột khóa chính. Tuy nhiên, nên khai báo rõ để người đọc hiểu mô hình và tránh nhầm với unique key thông thường.

### 7.1. PRIMARY KEY khác UNIQUE nullable

| Thuộc tính | PRIMARY KEY | UNIQUE |
|---|---|---|
| Cho phép NULL | Không | Có, tùy số lượng cột và quy tắc NULL |
| Số lượng trên một bảng | Một | Có thể nhiều |
| Mục tiêu | Định danh hàng | Bảo đảm tính duy nhất của một hoặc nhiều thuộc tính |
| InnoDB | Là clustered index | Thường là secondary unique index nếu không được chọn làm clustered index |
| Cột ghép | Tất cả thành phần NOT NULL | Có thể có thành phần nullable |

Không dùng UNIQUE nullable làm khóa định danh chính của hàng nếu nghiệp vụ cần định danh bắt buộc. Hãy dùng primary key ổn định, thường là surrogate key hoặc khóa nghiệp vụ thực sự không NULL.

## 8. NULL trong composite FOREIGN KEY

Foreign key đảm bảo giá trị ở bảng con tham chiếu tới khóa hợp lệ ở bảng cha. Với InnoDB, nếu một hoặc nhiều cột trong composite foreign key là NULL, hàng con không bắt buộc phải khớp một hàng cha cho khóa đó.

Ví dụ:

~~~sql
CREATE TABLE region (
    country_code CHAR(2) NOT NULL,
    region_code VARCHAR(10) NOT NULL,
    region_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (country_code, region_code)
) ENGINE = InnoDB;

CREATE TABLE customer_location (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    country_code CHAR(2) NULL,
    region_code VARCHAR(10) NULL,
    CONSTRAINT fk_customer_region
        FOREIGN KEY (country_code, region_code)
        REFERENCES region (country_code, region_code)
) ENGINE = InnoDB;
~~~

Các trường hợp:

- \`('VN', 'HN')\`: phải tồn tại cặp tương ứng trong bảng region.
- \`(NULL, NULL)\`: không yêu cầu tham chiếu tới hàng cha.
- \`('VN', NULL)\`: thành phần NULL khiến việc kiểm tra tham chiếu không được thực hiện như một cặp đầy đủ.
- \`(NULL, 'HN')\`: tương tự, có thành phần NULL nên không yêu cầu hàng cha khớp.

Điều này hữu ích nếu quan hệ là tùy chọn. Nhưng nếu nghiệp vụ yêu cầu hoặc không chọn vùng nào, hoặc phải chọn đủ quốc gia và vùng, cần thêm CHECK:

~~~sql
ALTER TABLE customer_location
ADD CONSTRAINT chk_customer_region_pair
CHECK (
    (country_code IS NULL AND region_code IS NULL)
    OR
    (country_code IS NOT NULL AND region_code IS NOT NULL)
);
~~~

CHECK ngăn trường hợp chỉ điền một phần khóa ngoại. FOREIGN KEY tiếp tục bảo đảm cặp giá trị đã điền phải tồn tại ở bảng cha.

### 8.1. Nếu quan hệ bắt buộc

Nếu mỗi customer phải thuộc một region, cách đơn giản nhất là khai báo cả hai cột NOT NULL:

~~~sql
country_code CHAR(2) NOT NULL,
region_code VARCHAR(10) NOT NULL,
FOREIGN KEY (country_code, region_code)
    REFERENCES region (country_code, region_code)
~~~

Như vậy, không thể bỏ qua quan hệ bằng NULL.

### 8.2. Nếu quan hệ tùy chọn nhưng phải đầy đủ

Dùng hai cột nullable, CHECK all-or-none và composite FOREIGN KEY như ví dụ. Không dựa riêng vào foreign key để ngăn khóa tham chiếu một phần.

## 9. NULL trong khóa ghép và index

NULL không làm mất khả năng tạo index. MySQL có thể lưu và tra cứu NULL trong B-tree index. Truy vấn \`IS NULL\` có thể sử dụng index nếu kế hoạch thực thi phù hợp.

Ví dụ:

~~~sql
CREATE INDEX idx_external_code
ON external_reference (external_code);

EXPLAIN
SELECT reference_id
FROM external_reference
WHERE external_code IS NULL;
~~~

Với composite index:

~~~sql
CREATE INDEX idx_tenant_external
ON external_reference (tenant_id, external_code);
~~~

Các truy vấn theo cột đầu tiên hoặc theo cả hai cột có thể sử dụng leftmost prefix của index:

~~~sql
EXPLAIN
SELECT reference_id
FROM external_reference
WHERE tenant_id = 10
  AND external_code IS NULL;
~~~

Không nên tạo index chỉ vì cột có NULL. Cần xem selectivity, số hàng, pattern truy vấn và chi phí ghi. Nếu phần lớn hàng có external_code NULL, index có thể ít chọn lọc cho điều kiện \`IS NULL\`.

### 9.1. NULL và thứ tự sắp xếp

Trong MySQL, khi \`ORDER BY\`:

- ASC: NULL được xếp trước giá trị không NULL.
- DESC: NULL được xếp sau giá trị không NULL.

Có thể thử:

~~~sql
SELECT employee_id, tax_code
FROM employee
ORDER BY tax_code ASC;

SELECT employee_id, tax_code
FROM employee
ORDER BY tax_code DESC;
~~~

Nếu muốn thứ tự riêng, có thể biểu diễn rõ:

~~~sql
SELECT employee_id, tax_code
FROM employee
ORDER BY tax_code IS NULL DESC, tax_code;
~~~

Biểu thức đầu tiên đưa các hàng NULL lên trước, sau đó sắp xếp các giá trị còn lại. Hãy chọn thứ tự phù hợp với giao diện và nghiệp vụ.

## 10. NULL trong hàm tổng hợp và truy vấn

### 10.1. COUNT(*) và COUNT(column)

\`COUNT(*)\` đếm tất cả hàng. \`COUNT(column)\` chỉ đếm các giá trị không NULL.

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(tax_code) AS rows_with_tax_code,
    COUNT(*) - COUNT(tax_code) AS rows_without_tax_code
FROM employee;
~~~

Cách này hữu ích để thống kê độ đầy đủ dữ liệu.

### 10.2. SUM, AVG, MIN và MAX

Các hàm tổng hợp như \`SUM()\`, \`AVG()\`, \`MIN()\`, \`MAX()\` bỏ qua giá trị NULL. Nếu tất cả giá trị đầu vào là NULL hoặc không có hàng phù hợp, kết quả có thể là NULL.

~~~sql
SELECT
    AVG(score) AS average_score,
    COUNT(score) AS scored_rows,
    COUNT(*) AS total_rows
FROM optional_rating;
~~~

Nếu dùng \`COALESCE(AVG(score), 0)\`, cần xác định nghiệp vụ có thực sự coi “không có dữ liệu” là 0 hay không. Trung bình bằng 0 và không có điểm là hai trạng thái khác nhau.

### 10.3. GROUP BY

Trong \`GROUP BY\`, các giá trị NULL được gom vào cùng một nhóm:

~~~sql
SELECT
    tax_code,
    COUNT(*) AS employee_count
FROM employee
GROUP BY tax_code;
~~~

Nhóm NULL thể hiện số hàng chưa có tax_code. Điều này khác với phép so sánh \`NULL = NULL\`, vốn trả về UNKNOWN.

### 10.4. NOT IN và NULL

Một lỗi thường gặp là dùng \`NOT IN\` với danh sách hoặc subquery có NULL:

~~~sql
SELECT employee_id
FROM employee
WHERE employee_id NOT IN (
    SELECT employee_id
    FROM blocked_employee
);
~~~

Nếu subquery trả về NULL, phép so sánh có thể cho UNKNOWN với các giá trị không khớp và làm truy vấn không trả kết quả như dự kiến.

Có thể dùng \`NOT EXISTS\` để diễn đạt anti-join rõ ràng:

~~~sql
SELECT e.employee_id
FROM employee AS e
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_employee AS b
    WHERE b.employee_id = e.employee_id
);
~~~

Nếu khóa so sánh bên trong có thể NULL và muốn so sánh NULL-safe, cân nhắc toán tử \`<=>\` hoặc xác định rõ chính sách dữ liệu.

## 11. Thiết kế schema theo quy tắc nghiệp vụ

Trước khi chọn NULL/NOT NULL và UNIQUE/CHECK, hãy mô tả quy tắc bằng câu đơn giản. Ví dụ:

| Quy tắc nghiệp vụ | Thiết kế MySQL |
|---|---|
| Mỗi tài khoản phải có username duy nhất | \`NOT NULL\` + \`UNIQUE\` |
| Mã thuế tùy chọn, nhưng nếu có phải duy nhất | Nullable + \`UNIQUE\` |
| Số lượng bắt buộc lớn hơn 0 | \`NOT NULL\` + \`CHECK (quantity > 0)\` |
| Điểm đánh giá tùy chọn; nếu có phải từ 0 đến 10 | Nullable + CHECK cho phép NULL hoặc miền hợp lệ |
| Hai cột thời gian phải cùng có hoặc cùng không có | Nullable + CHECK all-or-none |
| Khóa ngoại ghép tùy chọn, nhưng phải điền đủ các thành phần | Nullable + CHECK all-or-none + FOREIGN KEY |
| Khóa định danh gồm hai thành phần bắt buộc | Composite PRIMARY KEY, tất cả NOT NULL |
| Tổ hợp tenant và mã ngoài duy nhất khi mã đã có | \`UNIQUE (tenant_id, external_code)\`, tenant_id NOT NULL |

### 11.1. Mẫu bảng kết hợp nhiều ràng buộc

~~~sql
CREATE TABLE subscription (
    subscription_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    external_code VARCHAR(80) NULL,
    starts_at DATETIME NULL,
    ends_at DATETIME NULL,
    seat_count INT NOT NULL,
    PRIMARY KEY (subscription_id),
    UNIQUE KEY uq_subscription_external (tenant_id, external_code),
    CONSTRAINT chk_subscription_seats
        CHECK (seat_count > 0),
    CONSTRAINT chk_subscription_dates
        CHECK (
            (starts_at IS NULL AND ends_at IS NULL)
            OR
            (
                starts_at IS NOT NULL
                AND ends_at IS NOT NULL
                AND starts_at <= ends_at
            )
        )
) ENGINE = InnoDB;
~~~

Thiết kế này thể hiện:

- Mỗi subscription có khóa chính không NULL.
- tenant_id luôn có giá trị.
- external_code tùy chọn; nhiều subscription trong cùng tenant có thể chưa có mã.
- Nếu có thời gian bắt đầu thì phải có thời gian kết thúc, và bắt đầu không sau kết thúc.
- seat_count luôn dương và không NULL.

Nếu nghiệp vụ yêu cầu external_code bắt buộc, đổi cột thành NOT NULL. Nếu yêu cầu chỉ một subscription trong tenant được phép chưa có external_code, unique key hiện tại không đủ; cần bổ sung thiết kế riêng cho quy tắc đó.

## 12. Chỉ cho phép một NULL trong unique key: khi nào và cách thiết kế

MySQL mặc định cho phép nhiều NULL trong unique index. Nếu yêu cầu nghiệp vụ thật sự là chỉ được có tối đa một hàng chưa có giá trị, cần biểu diễn trường hợp NULL thành một giá trị khóa có thể kiểm soát.

Một cách là dùng generated column với sentinel được dành riêng, kết hợp CHECK để cấm giá trị thật trùng sentinel. Ví dụ sau dành chuỗi rỗng cho trường hợp NULL:

~~~sql
CREATE TABLE optional_email (
    contact_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    email VARCHAR(254) NULL,
    email_unique_key VARCHAR(254)
        GENERATED ALWAYS AS (COALESCE(email, '')) STORED,
    CONSTRAINT chk_email_not_empty
        CHECK (email IS NULL OR email <> ''),
    UNIQUE KEY uq_optional_email (email_unique_key)
) ENGINE = InnoDB;
~~~

Cách hoạt động:

- Nếu email NULL, generated column trở thành chuỗi rỗng.
- Nếu email có giá trị, generated column giữ giá trị email.
- CHECK cấm email thật là chuỗi rỗng, nên sentinel không thể bị dùng bởi dữ liệu nghiệp vụ.
- UNIQUE trên generated column chỉ cho phép một chuỗi rỗng, tức tối đa một email NULL; các email khác vẫn phải duy nhất theo collation của cột.

Cách này yêu cầu CHECK thực sự được thực thi (MySQL 8.0.16 trở lên). Hãy kiểm thử collation, độ dài, biểu thức generated column và migration trên phiên bản đích. Nếu chuỗi rỗng có ý nghĩa hợp lệ hoặc không thể dành riêng một sentinel an toàn, dùng một bảng quản lý trạng thái riêng hoặc thiết kế lại mô hình. Không áp dụng mẹo sentinel nếu nghiệp vụ không yêu cầu chỉ một NULL.

## 13. Phiên bản MySQL và kiểm tra CHECK

MySQL chỉ bắt đầu thực thi CHECK constraint từ MySQL 8.0.16. Trong các phiên bản MySQL trước đó, cú pháp CHECK được chấp nhận nhưng constraint không được thực thi. Vì vậy, không được giả định CHECK đang bảo vệ dữ liệu chỉ vì DDL tạo bảng không báo lỗi.

Kiểm tra phiên bản:

~~~sql
SELECT VERSION();
~~~

Kiểm tra định nghĩa:

~~~sql
SHOW CREATE TABLE product_required\\G
~~~

Trên phiên bản hỗ trợ, có thể kiểm tra thông tin constraint trong INFORMATION_SCHEMA:

~~~sql
SELECT
    CONSTRAINT_SCHEMA,
    TABLE_NAME,
    CONSTRAINT_NAME,
    CHECK_CLAUSE,
    ENFORCED
FROM information_schema.check_constraints
WHERE CONSTRAINT_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, CONSTRAINT_NAME;
~~~

Nếu dùng MySQL 5.7 hoặc một sản phẩm tương thích có hành vi khác, cần xác minh hỗ trợ thực tế. Có thể phải kiểm soát bằng NOT NULL, trigger hoặc logic ứng dụng cho đến khi nâng cấp. Không xem một CHECK không được thực thi là hàng rào bảo vệ dữ liệu.

## 14. Migration khi thay đổi NULL và UNIQUE

Thay đổi một cột từ nullable sang NOT NULL hoặc đổi unique key có thể thất bại nếu dữ liệu hiện có không thỏa mãn quy tắc mới.

### 14.1. Kiểm tra NULL trước khi đặt NOT NULL

~~~sql
SELECT COUNT(*) AS null_rows
FROM employee
WHERE tax_code IS NULL;
~~~

Nếu kết quả lớn hơn 0, phải xác định cách xử lý:

- Bổ sung giá trị đúng từ nguồn dữ liệu đáng tin cậy.
- Giữ nullable nếu nghiệp vụ thực sự cho phép thiếu.
- Loại bỏ bản ghi theo quy tắc nghiệp vụ nếu được phép.
- Chuyển sang một mô hình lưu trạng thái thiếu rõ ràng.

Không tự thay mọi NULL bằng chuỗi rỗng hoặc 0 để DDL chạy qua.

### 14.2. Kiểm tra duplicate trước khi thêm UNIQUE

~~~sql
SELECT tax_code, COUNT(*) AS total
FROM employee
WHERE tax_code IS NOT NULL
GROUP BY tax_code
HAVING COUNT(*) > 1;
~~~

Nếu cột có collation không phân biệt hoa/thường hoặc dấu, truy vấn GROUP BY sẽ áp dụng collation của cột. Kiểm tra duplicate theo đúng quy tắc mà unique index mới sẽ dùng.

Với khóa ghép:

~~~sql
SELECT
    tenant_id,
    external_code,
    COUNT(*) AS total
FROM external_reference
WHERE external_code IS NOT NULL
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1;
~~~

Điều kiện \`external_code IS NOT NULL\` giúp tập trung vào những tổ hợp mà unique key thực sự kiểm soát tính duy nhất. Nếu các thành phần khác cũng nullable, phải phân tích từng tổ hợp NULL theo quy tắc MySQL.

### 14.3. Thêm CHECK sau khi kiểm tra dữ liệu

Ví dụ muốn quantity phải dương và không NULL:

~~~sql
SELECT COUNT(*) AS invalid_rows
FROM product
WHERE quantity IS NULL OR quantity <= 0;
~~~

Sau khi xử lý các hàng không hợp lệ:

~~~sql
ALTER TABLE product
    MODIFY quantity INT NOT NULL,
    ADD CONSTRAINT chk_product_quantity_positive
        CHECK (quantity > 0);
~~~

Thứ tự thay đổi và khả năng online phụ thuộc phiên bản, storage engine và cấu trúc bảng. Thực hiện trên môi trường thử nghiệm, backup trước và đánh giá thời gian lock/rebuild.

## 15. Những lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Nguyên nhân | Cách xử lý |
|---|---|---|
| UNIQUE nhưng vẫn có nhiều hàng chưa nhập mã | UNIQUE cho phép nhiều NULL | Chỉ thêm NOT NULL nếu nghiệp vụ bắt buộc có mã |
| Composite UNIQUE vẫn nhận hai hàng cùng tenant với code NULL | Một thành phần khóa là NULL | Xác định có cho phép nhiều mã chưa biết hay không |
| CHECK quantity > 0 nhưng vẫn có NULL | CHECK chấp nhận UNKNOWN | Kết hợp NOT NULL hoặc biểu thức cho phép NULL rõ ràng |
| CHECK ngày bắt đầu/kết thúc không chặn một phía NULL | So sánh cho UNKNOWN | Viết CHECK all-or-none với IS NULL/IS NOT NULL |
| FK ghép không báo lỗi khi một cột NULL | Có thành phần khóa ngoại NULL | Dùng NOT NULL hoặc CHECK all-or-none |
| WHERE column = NULL không tìm được hàng | Phép so sánh trả UNKNOWN | Dùng IS NULL |
| NOT IN trả kết quả bất ngờ | Danh sách/subquery chứa NULL | Dùng NOT EXISTS hoặc lọc NULL có chủ đích |
| COUNT(column) thấp hơn COUNT(*) | COUNT(column) bỏ qua NULL | Dùng cả hai để đo độ đầy đủ |
| DDL thêm UNIQUE báo duplicate | Dữ liệu trùng theo quy tắc collation | GROUP BY trước migration |
| CHECK tạo được nhưng dữ liệu sai vẫn vào | Phiên bản MySQL cũ không thực thi CHECK | Xác minh phiên bản và ENFORCED |

## 16. Checklist thiết kế NULL và khóa

- [ ] Đã phân biệt NULL, 0, chuỗi rỗng và DEFAULT.
- [ ] Đã xác định cột nào thực sự được phép thiếu giá trị.
- [ ] Đã dùng NOT NULL cho thuộc tính bắt buộc.
- [ ] Đã hiểu UNIQUE nullable cho phép nhiều NULL.
- [ ] Đã kiểm tra hành vi NULL trên từng thành phần composite UNIQUE.
- [ ] Đã khai báo tất cả cột composite PRIMARY KEY là NOT NULL.
- [ ] Đã xác định composite FOREIGN KEY có được phép thiếu một phần hay không.
- [ ] Đã thêm CHECK all-or-none khi các thành phần khóa ngoại phải cùng có hoặc cùng không có giá trị.
- [ ] Đã hiểu CHECK chấp nhận TRUE và UNKNOWN, chỉ từ chối FALSE.
- [ ] Đã kết hợp CHECK với NOT NULL khi dữ liệu bắt buộc.
- [ ] Đã kiểm tra phiên bản MySQL có thực thi CHECK.
- [ ] Đã dùng IS NULL/IS NOT NULL hoặc <=> thay cho = NULL.
- [ ] Đã kiểm tra ảnh hưởng của NULL tới COUNT, GROUP BY, NOT IN và ORDER BY.
- [ ] Đã kiểm tra duplicate và NULL trước khi migration.
- [ ] Đã thử nghiệm các quy tắc trên bản sao dữ liệu trước khi triển khai.

## 17. Bài tập thực hành

### Bài 1: UNIQUE nullable

Tạo bảng nhân viên với \`tax_code VARCHAR(30) NULL UNIQUE\`. Chèn ba hàng NULL và hai hàng có mã khác nhau. Thử chèn lại một mã đã có. Giải thích vì sao chỉ trường hợp mã trùng bị từ chối.

### Bài 2: Composite UNIQUE

Tạo unique key \`(tenant_id, external_code)\`. Chèn hai hàng có cùng tenant_id và external_code NULL. Sau đó chèn hai hàng có cùng tenant_id và external_code giống nhau. Ghi lại trường hợp được phép và bị từ chối.

### Bài 3: CHECK với NULL

Tạo cột \`score DECIMAL(3,1) NULL\` và CHECK \`score BETWEEN 0 AND 10\`. Thử chèn NULL, -1, 5 và 11. Sau đó thêm NOT NULL và thử lại. Giải thích kết quả theo logic ba giá trị.

### Bài 4: Khóa ngoại ghép

Tạo bảng parent có khóa chính \`(country_code, region_code)\` và bảng child có foreign key cùng hai cột. Thử chèn cặp hợp lệ, cặp không tồn tại, cả hai NULL và chỉ một cột NULL. Thêm CHECK all-or-none rồi so sánh.

### Bài 5: Migration nullable sang NOT NULL

Dùng bảng có một số hàng NULL. Viết truy vấn kiểm tra, xác định cách xử lý dữ liệu và thực hiện migration sang NOT NULL. Kiểm tra lại DDL và dữ liệu sau migration.

## 18. Kết luận

NULL là một trạng thái dữ liệu riêng và làm cho SQL sử dụng logic ba giá trị. Trong MySQL, UNIQUE cho phép nhiều NULL; điều này vẫn đúng với composite unique key khi có ít nhất một thành phần NULL. CHECK chỉ từ chối biểu thức FALSE, còn UNKNOWN được chấp nhận. Composite primary key không cho phép NULL, trong khi composite foreign key có thể bỏ qua kiểm tra tham chiếu nếu một thành phần khóa ngoại NULL.

Khi thiết kế, hãy chuyển quy tắc nghiệp vụ thành các ràng buộc rõ ràng: NOT NULL cho giá trị bắt buộc, UNIQUE cho tính duy nhất, CHECK cho điều kiện trên từng hàng và FOREIGN KEY cho quan hệ tham chiếu. Với khóa ghép có các thành phần tùy chọn, viết CHECK all-or-none nếu nghiệp vụ yêu cầu các thành phần cùng có hoặc cùng thiếu. Trước migration, hãy tìm NULL và duplicate theo đúng quy tắc so sánh của collation đích.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – NULL Values](https://dev.mysql.com/doc/refman/8.4/en/working-with-null.html)
- [MySQL 8.4 Reference Manual – UNIQUE Indexes](https://dev.mysql.com/doc/refman/8.4/en/create-index.html)
- [MySQL 8.4 Reference Manual – CREATE TABLE and UNIQUE Constraints](https://dev.mysql.com/doc/refman/8.4/en/create-table.html)
- [MySQL 8.4 Reference Manual – CHECK Constraints](https://dev.mysql.com/doc/refman/8.4/en/create-table-check-constraints.html)
- [MySQL 8.4 Reference Manual – Foreign Key Constraints](https://dev.mysql.com/doc/refman/8.4/en/create-table-foreign-keys.html)
- [MySQL 8.4 Reference Manual – Primary Key Optimization](https://dev.mysql.com/doc/refman/8.4/en/primary-key-optimization.html)
- [MySQL 8.4 Reference Manual – Working with NULL Values](https://dev.mysql.com/doc/refman/8.4/en/working-with-null.html)
- [MySQL 8.4 Reference Manual – Aggregate Functions](https://dev.mysql.com/doc/refman/8.4/en/aggregate-functions.html)

