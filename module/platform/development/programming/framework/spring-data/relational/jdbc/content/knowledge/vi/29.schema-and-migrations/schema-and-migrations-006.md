# Giới hạn sinh chênh lệch schema: đổi tên và chuyển đổi dữ liệu

Trong **Spring Data Relational JDBC (Spring Data JDBC)**, thay đổi entity và mapping thường kéo theo thay đổi schema database. Một property có thể được đổi tên, tách thành hai property, gộp nhiều trường, đổi kiểu dữ liệu hoặc chuyển sang một value object. Công cụ so sánh schema (schema diff) giúp phát hiện khác biệt giữa hai cấu trúc database, nhưng không tự hiểu đầy đủ ý định nghiệp vụ đằng sau thay đổi.

Hai tình huống đặc biệt dễ gây lỗi là **đổi tên** và **chuyển đổi dữ liệu**. Khi một cột cũ biến mất và một cột mới xuất hiện, công cụ diff có thể đề xuất DROP cột cũ rồi ADD cột mới, dù ý định thực sự chỉ là RENAME và giữ nguyên dữ liệu. Khi kiểu hoặc cấu trúc dữ liệu thay đổi, công cụ có thể đề xuất ALTER COLUMN nhưng không biết phải biến đổi từng giá trị cũ thành giá trị mới như thế nào.

Vì vậy, kết quả schema diff nên được xem là **gợi ý để người phát triển xem xét**, còn migration có trách nhiệm bảo toàn dữ liệu, xử lý chuyển đổi và đưa schema đến trạng thái tương thích với phiên bản ứng dụng mới.

## 1. Schema mapping và schema migration là hai việc khác nhau

Spring Data JDBC dùng metadata của domain model để ánh xạ object với bảng/cột:

- `@Table` xác định bảng của entity.
- `@Column` ánh xạ property với cột.
- `@Id` xác định khóa chính.
- `@Embedded` trải phẳng value object thành các cột trong cùng bảng.
- `@MappedCollection` mô tả thành phần con thuộc aggregate và cột tham chiếu root.

Các annotation này mô tả **cách ứng dụng đọc và ghi dữ liệu**. Chúng không tự cung cấp toàn bộ lịch sử thay đổi schema hoặc quy tắc chuyển đổi dữ liệu production.

Ví dụ entity:

~~~java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("display_name")
    private String displayName;
}
~~~

Mapping cho biết property `displayName` tương ứng với cột `display_name`. Nếu đổi property hoặc đổi tên cột, database cần được migration để schema mới khớp với mapping. Việc thay annotation trong Java không tự đổi tên cột đã tồn tại trong database.

### Vai trò của từng thành phần

| Thành phần | Trách nhiệm |
|---|---|
| Spring Data JDBC mapping | Ánh xạ aggregate/property với bảng và cột |
| Schema diff | So sánh cấu trúc database ở hai thời điểm |
| Migration script/changelog | Thực hiện thay đổi schema có thứ tự và có thể tái lập |
| Data migration/backfill | Chuyển đổi các giá trị đang lưu |
| Application code | Đọc/ghi theo mapping và quy tắc domain của phiên bản hiện tại |

Không nên dùng schema diff như thể nó là một công cụ hiểu domain model và tự quyết định cách di chuyển dữ liệu.

## 2. Schema diff thực sự so sánh điều gì?

Schema diff thường so sánh metadata của hai schema hoặc hai snapshot, chẳng hạn:

- Bảng và view.
- Cột, tên cột, kiểu dữ liệu và độ dài.
- Nullability và default.
- Primary key, foreign key và unique constraint.
- Index.
- Một số loại sequence, trigger hoặc object database tùy công cụ.

Ví dụ schema cũ:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL
);
~~~

Schema mới:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(160) NOT NULL
);
~~~

Khi so sánh tên và định nghĩa cột, công cụ có thể thấy:

| Schema cũ | Schema mới | Khác biệt được phát hiện |
|---|---|---|
| `display_name` | Không còn | Cột bị xóa |
| Không có `full_name` | `full_name` | Cột mới được thêm |

Nhìn ở mức cấu trúc, hai cột có tên khác nhau. Nhưng công cụ không thể chắc chắn rằng:

- `display_name` được đổi tên thành `full_name`.
- `full_name` là một trường mới, còn `display_name` phải bị xóa.
- Dữ liệu cũ cần được ghép với một trường khác.
- Một phần nội dung cũ cần được chuẩn hóa trước khi ghi sang cột mới.

Hai schema có thể giống hệt nhau về mặt metadata nhưng mang ý nghĩa nghiệp vụ rất khác nhau. Schema diff nhìn thấy cấu trúc, không tự suy luận được ý nghĩa.

## 3. Vì sao đổi tên thường bị hiểu thành DROP và ADD?

Tên cột là một trong các dấu hiệu chính để công cụ ghép cột giữa hai snapshot. Nếu tên thay đổi, công cụ có thể không biết hai cột là cùng một thuộc tính.

Ví dụ:

~~~text
Trước:
customers.display_name VARCHAR(120)

Sau:
customers.full_name VARCHAR(160)
~~~

Một diff đơn giản có thể sinh:

~~~sql
ALTER TABLE customers DROP COLUMN display_name;
ALTER TABLE customers ADD COLUMN full_name VARCHAR(160);
~~~

Nếu chạy nguyên văn migration này, dữ liệu cũ trong `display_name` bị xóa. Cột mới được tạo nhưng không chứa tên khách hàng trước đó.

Trong khi ý định thực tế có thể chỉ là:

~~~sql
ALTER TABLE customers
RENAME COLUMN display_name TO full_name;
~~~

Lệnh rename giữ nguyên giá trị trong từng hàng. Đây là lý do không được chạy tự động mọi script diff trên database có dữ liệu quan trọng mà chưa xem xét.

### Heuristic nhận diện rename không phải bằng chứng

Một số công cụ có thể đề xuất rename dựa trên độ giống nhau của tên, kiểu dữ liệu hoặc metadata. Heuristic có thể hữu ích nhưng vẫn có trường hợp mơ hồ:

- Hai cột cũ có kiểu giống nhau và một cột mới xuất hiện.
- Một cột được đổi tên đồng thời đổi kiểu/độ dài.
- Cột cũ bị xóa thật và một cột mới được thêm.
- Hai cột được hoán đổi hoặc gộp/tách.

Chỉ người hiểu thay đổi nghiệp vụ mới xác nhận được cột nào tương ứng với cột nào và dữ liệu cần được giữ ra sao.

## 4. Migration đổi tên cột an toàn

Nếu mục tiêu chỉ là đổi tên cột và giữ nguyên dữ liệu, hãy viết migration thể hiện rõ thao tác rename.

### PostgreSQL

~~~sql
ALTER TABLE customers
RENAME COLUMN display_name TO full_name;
~~~

### MySQL

Với MySQL, cú pháp hỗ trợ đổi tên cột phụ thuộc phiên bản. Ví dụ cú pháp hiện đại:

~~~sql
ALTER TABLE customers
RENAME COLUMN display_name TO full_name;
~~~

Một số phiên bản/cú pháp cũ sử dụng `CHANGE COLUMN` và yêu cầu khai báo lại định nghĩa cột:

~~~sql
ALTER TABLE customers
CHANGE COLUMN display_name full_name VARCHAR(120) NOT NULL;
~~~

Khi dùng `CHANGE COLUMN`, phải khai báo đúng kiểu, nullability, default, comment và các thuộc tính cần giữ. Luôn kiểm tra cú pháp theo phiên bản database mục tiêu.

### Cập nhật mapping Java

Sau migration, entity ánh xạ sang cột mới:

~~~java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("full_name")
    private String fullName;
}
~~~

Migration và code phải được triển khai theo một kế hoạch tương thích. Nếu ứng dụng cũ vẫn chạy trong lúc migration diễn ra, đổi tên trực tiếp có thể khiến phiên bản cũ không tìm thấy `display_name`. Với hệ thống cần rolling deployment hoặc không thể dừng dịch vụ, nên dùng chiến lược expand-contract ở phần sau.

## 5. Đổi tên property Java khác với đổi tên cột SQL

Có thể đổi tên property Java mà không đổi tên cột database nếu giữ `@Column`:

~~~java
@Column("display_name")
private String fullName;
~~~

Trong trường hợp này:

- Java code dùng `fullName`.
- Database tiếp tục dùng `display_name`.
- Không cần migration rename cột chỉ vì property Java đổi tên.

Ngược lại, nếu muốn đổi cả property và cột, cần thay mapping và migration cùng nhau:

~~~java
@Column("full_name")
private String fullName;
~~~

Không nhầm hai thay đổi:

| Thay đổi | Có cần đổi schema? |
|---|---|
| Chỉ đổi tên property, giữ `@Column` cũ | Không |
| Đổi tên cột và cập nhật `@Column` | Có |
| Đổi tên property nhưng dùng naming strategy mặc định, cột suy ra từ property | Thường có |
| Đổi tên bảng qua `@Table` | Có nếu bảng vật lý cũng đổi |

Việc giữ mapping tường minh đôi khi hữu ích khi muốn tách refactor code khỏi migration schema. Nhưng không nên để tên property và tên cột lệch nhau vô cớ nếu điều đó làm code khó hiểu.

## 6. Chuyển đổi dữ liệu không thể được suy ra chỉ từ schema

Schema diff có thể nhận thấy kiểu cột thay đổi:

~~~text
Trước: customers.phone_number VARCHAR(30)
Sau:   customers.phone_number VARCHAR(20)
~~~

Nó có thể đề xuất ALTER COLUMN để giảm độ dài. Nhưng nó không biết:

- Có hàng nào chứa chuỗi dài hơn 20 ký tự không?
- Có cần chuẩn hóa mã quốc gia không?
- Có cần loại bỏ dấu cách hoặc dấu phân cách không?
- Dữ liệu dài có phải lỗi hay có ý nghĩa nghiệp vụ cần giữ?
- Nếu cắt chuỗi, phần bị cắt có được lưu ở nơi khác không?

Một thay đổi kiểu dữ liệu có thể cần **data transformation** trước hoặc trong migration. Ví dụ chuyển một trường trạng thái tự do thành enum chuẩn:

~~~text
Trước: status = "in progress", "IN_PROGRESS", "processing"
Sau:   status = "PROCESSING"
~~~

Schema diff chỉ thấy cùng là VARCHAR. Nó không biết các giá trị khác nhau cần được chuẩn hóa thành cùng một trạng thái.

## 7. Ví dụ chuyển đổi dữ liệu với UPDATE

Giả sử cột cũ `status` chứa nhiều cách viết:

~~~sql
SELECT DISTINCT status
FROM sales_orders;
~~~

Kết quả có thể gồm:

~~~text
in progress
IN_PROGRESS
processing
completed
done
cancelled
~~~

Muốn chuẩn hóa sang tập giá trị mới:

~~~sql
UPDATE sales_orders
SET status = CASE
    WHEN LOWER(TRIM(status)) IN ('in progress', 'in_progress', 'processing')
        THEN 'PROCESSING'
    WHEN LOWER(TRIM(status)) IN ('completed', 'done')
        THEN 'COMPLETED'
    WHEN LOWER(TRIM(status)) = 'cancelled'
        THEN 'CANCELLED'
    ELSE 'UNKNOWN'
END;
~~~

Đây là quy tắc nghiệp vụ được viết rõ trong migration. Người phát triển phải quyết định cách xử lý giá trị lạ; không mặc định gán `UNKNOWN` nếu điều đó làm mất thông tin cần điều tra.

Trước khi chạy UPDATE trên production, nên:

1. Liệt kê distinct value và số hàng của từng giá trị.
2. Xác định mapping cho tất cả giá trị đã tồn tại.
3. Xác định cách xử lý NULL và giá trị không nhận diện.
4. Thử migration trên bản sao dữ liệu đại diện.
5. Đối chiếu số lượng và phân bố dữ liệu sau chuyển đổi.

## 8. Chuyển đổi kiểu dữ liệu cần quy tắc tường minh

Ví dụ chuyển `amount_text` dạng chuỗi thành cột số `amount`:

~~~text
"1250.50" -> 1250.50
"1,250.50" -> 1250.50
"unknown" -> không chuyển đổi trực tiếp
~~~

Không phải mọi chuỗi đều parse được thành số. Migration cần xác định locale, dấu thập phân, dấu phân nhóm, đơn vị tiền và giá trị lỗi.

Một chiến lược an toàn hơn là thêm cột mới:

~~~sql
ALTER TABLE invoices
ADD COLUMN amount_numeric NUMERIC(14, 2);
~~~

Backfill dữ liệu đã kiểm tra:

~~~sql
UPDATE invoices
SET amount_numeric = CAST(amount_text AS NUMERIC(14, 2))
WHERE amount_text ~ '^[0-9]+([.][0-9]{1,2})?$';
~~~

Ghi chú: biểu thức regex và phép CAST ở ví dụ trên dành cho PostgreSQL. MySQL và các database khác có cú pháp, hành vi ép kiểu và hàm kiểm tra khác.

Sau đó tìm hàng chưa chuyển đổi:

~~~sql
SELECT id, amount_text
FROM invoices
WHERE amount_text IS NOT NULL
  AND amount_numeric IS NULL;
~~~

Chỉ khi dữ liệu lỗi đã được xử lý và kiểm tra xong mới cân nhắc đặt `NOT NULL`, chuyển ứng dụng sang cột mới và xóa cột cũ.

## 9. Gộp hai cột thành một value object hoặc tách một cột thành nhiều cột

Schema diff nhận thấy thêm/xóa cột, nhưng không thể tự suy luận quy tắc gộp/tách.

### Tách một cột

Trước:

~~~sql
customers.full_address VARCHAR(300)
~~~

Sau:

~~~sql
customers.street VARCHAR(120)
customers.city VARCHAR(80)
customers.postal_code VARCHAR(20)
~~~

Không thể chia địa chỉ tự do một cách chắc chắn chỉ bằng schema diff. Cần parser hoặc quy tắc dữ liệu cụ thể; địa chỉ có thể thiếu thành phần, có dấu phẩy trong tên đường hoặc có định dạng khác nhau theo quốc gia.

### Gộp nhiều cột

Trước:

~~~sql
customers.first_name VARCHAR(80),
customers.last_name VARCHAR(80)
~~~

Sau:

~~~sql
customers.full_name VARCHAR(160)
~~~

Có thể backfill bằng:

~~~sql
UPDATE customers
SET full_name = TRIM(
    COALESCE(first_name, '') || ' ' || COALESCE(last_name, '')
);
~~~

Toán tử nối chuỗi `||` ở ví dụ phù hợp PostgreSQL và một số database khác; cú pháp có thể khác ở MySQL. Quan trọng hơn, quy tắc nối phải xác định cách xử lý tên rỗng, NULL, khoảng trắng và tên có nhiều thành phần.

## 10. Expand-migrate-contract cho hệ thống đang chạy

Nếu ứng dụng có nhiều instance hoặc triển khai rolling update, đổi tên cột trực tiếp có thể làm phiên bản cũ và mới không tương thích trong một khoảng thời gian. Chiến lược **expand-migrate-contract** chia thay đổi thành các bước tương thích.

Giả sử đổi `display_name` thành `full_name`:

~~~mermaid
flowchart TD
    A["1. Expand<br/>Thêm full_name"]
    B["2. Compatible app<br/>Đọc cột mới/cũ, ghi đồng bộ"]
    C["3. Backfill<br/>Copy dữ liệu cũ sang mới"]
    D["4. Switch<br/>Ứng dụng chỉ dùng full_name"]
    E["5. Contract<br/>Ngừng ghi và xóa display_name"]
    A --> B --> C --> D --> E
~~~

### Bước 1: Expand schema

Thêm cột mới nhưng giữ cột cũ:

~~~sql
ALTER TABLE customers
ADD COLUMN full_name VARCHAR(160);
~~~

Cột mới ban đầu có thể nullable để phiên bản ứng dụng cũ vẫn hoạt động.

### Bước 2: Triển khai code tương thích

Phiên bản trung gian có thể đọc giá trị mới nếu đã có, nếu chưa thì fallback về cột cũ. Khi ghi, ứng dụng đồng bộ cả hai cột trong giai đoạn chuyển tiếp.

Đồng bộ hai cột cần được thiết kế cẩn thận. Nếu có nhiều writer, phải xác định một nguồn dữ liệu chuẩn và tránh hai phiên bản cùng ghi theo quy tắc khác nhau.

### Bước 3: Backfill

Copy dữ liệu hiện có:

~~~sql
UPDATE customers
SET full_name = display_name
WHERE full_name IS NULL;
~~~

Với bảng lớn, backfill theo batch hoặc theo khóa chính để giới hạn thời gian khóa và lượng transaction. Có thể chạy nhiều lần nếu câu lệnh được thiết kế idempotent.

### Bước 4: Chuyển ứng dụng sang cột mới

Sau khi kiểm tra dữ liệu đã đồng bộ, triển khai phiên bản chỉ đọc/ghi `full_name`. Theo dõi log, số lượng NULL và các truy vấn còn tham chiếu `display_name`.

### Bước 5: Contract

Khi mọi instance, job, báo cáo và ứng dụng liên quan đã ngừng sử dụng cột cũ, mới xóa:

~~~sql
ALTER TABLE customers
DROP COLUMN display_name;
~~~

Contract thường là bước khó đảo ngược. Chỉ thực hiện khi đã xác nhận không còn consumer cũ và đã có phương án khôi phục dữ liệu cần thiết.

## 11. Migration schema và data migration nên được tổ chức thế nào?

Một migration có thể chứa cả DDL và DML, nhưng cần tách ý định để dễ đọc, review và vận hành.

Ví dụ thứ tự:

1. Thêm cột mới hoặc bảng mới.
2. Thêm index/constraint ở trạng thái phù hợp.
3. Chuyển đổi/backfill dữ liệu.
4. Kiểm tra dữ liệu sau chuyển đổi.
5. Cập nhật ứng dụng sang mapping mới.
6. Loại bỏ cấu trúc cũ ở migration sau.

Không nhất thiết gộp mọi bước vào một migration duy nhất. Với thay đổi nhỏ và database hỗ trợ transactional DDL, một migration đơn giản có thể đủ. Với bảng lớn hoặc deployment nhiều phiên bản, nhiều migration nhỏ giúp kiểm soát rủi ro tốt hơn.

### Migration phải có thứ tự và được version hóa

Ví dụ Flyway:

~~~text
src/main/resources/db/migration/
├── V001__create_customers.sql
├── V002__add_full_name.sql
├── V003__backfill_full_name.sql
└── V004__drop_display_name.sql
~~~

Flyway thực thi các migration theo version và ghi nhận lịch sử đã chạy. Thông thường người phát triển viết/chỉnh sửa migration script tường minh; không giả định Flyway tự suy ra ý nghĩa rename hoặc cách chuyển dữ liệu từ hai snapshot.

Với Liquibase, changelog có thể mô tả thay đổi bằng changeset như rename column, add column, update dữ liệu và drop column. Lệnh diff/diffChangeLog có thể giúp tìm khác biệt cấu trúc giữa hai database, nhưng kết quả vẫn cần review để xác nhận rename, thứ tự và data transformation. Một diff cấu trúc không thay thế changeset chuyển đổi dữ liệu.

Không chỉnh sửa migration đã chạy trên môi trường dùng chung/production để thay đổi lịch sử. Tạo migration mới để tiến schema từ trạng thái hiện tại sang trạng thái tiếp theo.

## 12. Giới hạn của schema diff với constraint và index

Đổi tên cột có thể ảnh hưởng tới:

- Index có chứa cột đó.
- Unique constraint.
- Foreign key.
- View hoặc materialized view.
- Trigger và stored procedure.
- Query/report chạy bên ngoài ứng dụng.

Tùy database, một số object được cập nhật tham chiếu tự động khi rename, trong khi object khác cần thay đổi riêng hoặc có thể bị từ chối. Schema diff có thể nhận diện object khác nhau nhưng không luôn hiểu thứ tự thay đổi an toàn.

Ví dụ đổi `customer_code` thành `external_code`:

~~~sql
CREATE UNIQUE INDEX ux_customers_customer_code
    ON customers(customer_code);
~~~

Sau rename, cần kiểm tra index vẫn tồn tại và có định nghĩa đúng. Nếu công cụ diff đề xuất drop/create index, xác nhận việc tạo lại có cần thiết hay chỉ là khác biệt tên/metadata.

Với foreign key, không xóa cột nguồn trước khi xác định các constraint phụ thuộc. Migration phải xử lý dependency theo thứ tự hợp lệ.

## 13. Schema diff không kiểm tra đầy đủ chất lượng dữ liệu

Hai schema có thể hoàn toàn giống nhau nhưng dữ liệu bên trong không đáp ứng quy tắc mới.

Ví dụ cột:

~~~sql
customers.email VARCHAR(255)
~~~

Schema mới thêm unique constraint:

~~~sql
ALTER TABLE customers
ADD CONSTRAINT uq_customers_email UNIQUE (email);
~~~

Schema diff có thể phát hiện constraint cần thêm. Nhưng nó không thể đảm bảo dữ liệu hiện có không trùng:

~~~sql
SELECT email, COUNT(*)
FROM customers
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
~~~

Nếu có email trùng, migration thêm unique constraint sẽ thất bại. Trước khi áp dụng constraint, phải xác định cách hợp nhất, sửa hoặc từ chối các bản ghi trùng theo quy tắc nghiệp vụ.

Các kiểm tra dữ liệu thường cần chạy trước migration:

- NULL ở cột sắp chuyển thành NOT NULL.
- Giá trị vượt độ dài mới.
- Giá trị không parse được sang kiểu mới.
- Giá trị trùng khi thêm unique constraint.
- Hàng mồ côi khi thêm foreign key.
- Giá trị không nằm trong tập enum/trạng thái mới.

## 14. Backfill bảng lớn và tính idempotent

Với bảng có hàng triệu bản ghi, một UPDATE toàn bảng có thể tạo transaction dài, khóa nhiều hàng, tăng WAL/undo log và ảnh hưởng workload. Có thể chia batch theo khóa chính:

~~~sql
UPDATE customers
SET full_name = display_name
WHERE id > :lastId
  AND id <= :nextId
  AND full_name IS NULL;
~~~

Ứng dụng/job backfill lặp qua các khoảng ID, ghi nhận tiến độ và có thể tiếp tục sau khi bị gián đoạn.

Một backfill tốt nên:

- Có điều kiện giới hạn batch.
- Có thể chạy lại mà không làm hỏng dữ liệu đã chuyển.
- Ghi nhận số hàng đã xử lý và số hàng lỗi.
- Có thể tạm dừng/tiếp tục.
- Kiểm soát tốc độ để tránh gây tải quá mức.
- Có truy vấn đối chiếu sau mỗi batch hoặc sau toàn bộ đợt.

Điều kiện `full_name IS NULL` trong ví dụ giúp tránh ghi đè dữ liệu mới đã được ứng dụng ghi vào cột đích. Nếu ứng dụng vẫn đồng bộ hai cột trong lúc backfill, cần định nghĩa rõ nguồn dữ liệu chuẩn và xử lý xung đột.

## 15. Kiểm tra sau migration

Không chỉ kiểm tra migration kết thúc với exit code 0. Hãy xác minh schema và dữ liệu theo tiêu chí cụ thể.

Ví dụ sau khi copy tên:

~~~sql
SELECT COUNT(*) AS missing_full_name
FROM customers
WHERE display_name IS NOT NULL
  AND full_name IS NULL;
~~~

So sánh giá trị:

~~~sql
SELECT id, display_name, full_name
FROM customers
WHERE display_name IS DISTINCT FROM full_name;
~~~

`IS DISTINCT FROM` là cú pháp PostgreSQL để so sánh có xử lý NULL. Với database khác, dùng phép so sánh tương đương.

Sau migration, kiểm tra:

- Cột/kiểu/nullability/default đúng với mapping mới.
- Số lượng bản ghi trước và sau phù hợp.
- Giá trị được chuyển đổi theo quy tắc.
- Không còn dữ liệu lỗi hoặc chưa backfill.
- Index, foreign key, unique constraint và view hoạt động.
- Ứng dụng mới đọc và ghi thành công.
- Job/report/consumer bên ngoài không còn dùng cấu trúc cũ.

## 16. Rollback và khôi phục dữ liệu

Không phải migration nào cũng có thể rollback bằng cách chạy ngược DDL.

Ví dụ:

- Rename column có thể rename ngược nếu chưa có thay đổi dữ liệu xung đột.
- Drop column làm mất dữ liệu; thêm lại cột không khôi phục được nội dung cũ.
- Chuyển đổi nhiều giá trị thành một trạng thái chuẩn có thể mất phân biệt giữa các giá trị cũ.
- Cắt độ dài chuỗi hoặc làm tròn số có thể không đảo ngược.
- Gộp first/last name thành full name có thể không tách lại chính xác.

Với thay đổi có mất mát, cần backup, giữ cột cũ trong giai đoạn chuyển tiếp hoặc lưu dữ liệu gốc ở nơi có thể phục hồi. Một script rollback chỉ khôi phục cấu trúc không đồng nghĩa khôi phục dữ liệu.

Trước khi migration production:

1. Xác định backup/restore point và thời gian khôi phục.
2. Thử migration trên bản sao dữ liệu đại diện.
3. Ước lượng thời gian, lock và dung lượng log.
4. Chuẩn bị tiêu chí dừng/tiếp tục.
5. Xác định cách tương thích giữa phiên bản ứng dụng cũ và mới.

## 17. Quy trình review kết quả schema diff

Khi công cụ sinh script/changelog, review từng thay đổi theo các câu hỏi:

| Câu hỏi | Điều cần xác nhận |
|---|---|
| Cột bị xóa và cột mới có phải cùng một thuộc tính đổi tên? | Dùng RENAME và giữ dữ liệu nếu đúng |
| Kiểu dữ liệu có thay đổi? | Có quy tắc chuyển đổi và kiểm tra giá trị cũ không? |
| Độ dài bị giảm? | Có hàng vượt giới hạn không? |
| Nullability thay đổi? | Dữ liệu hiện có có NULL không? |
| Thêm unique/FK/check? | Dữ liệu hiện có có thỏa constraint không? |
| Index bị drop/recreate? | Có thực sự cần rebuild không? |
| Có nhiều phiên bản ứng dụng chạy đồng thời? | Có cần expand-contract không? |
| Có data transformation? | Đã viết migration riêng và xác định xử lý giá trị lỗi chưa? |
| Rollback có mất dữ liệu không? | Có backup hoặc chiến lược khôi phục không? |

Chỉ sau khi review mới đưa script vào thư mục migration version hóa. Không chạy script diff chưa xem xét trên production.

## 18. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chạy diff đề xuất DROP + ADD cho một cột thực ra chỉ đổi tên | Mất dữ liệu cột cũ | Thay bằng thao tác RENAME phù hợp database |
| Nghĩ công cụ diff hiểu ý định nghiệp vụ | Mapping dữ liệu sai | Xác nhận rename và transformation thủ công |
| Chỉ đổi `@Column` mà không migration schema | Runtime không tìm thấy cột mới | Triển khai DDL và mapping theo kế hoạch |
| Chỉ đổi tên property Java nhưng tưởng database tự đổi | Schema và mapping lệch nhau | Giữ `@Column` cũ hoặc migration cột tương ứng |
| ALTER kiểu dữ liệu mà không kiểm tra dữ liệu cũ | Migration lỗi hoặc dữ liệu bị ép/cắt | Pre-check, backfill và xử lý giá trị lỗi |
| Thêm NOT NULL/UNIQUE/FK trước khi làm sạch dữ liệu | Constraint không tạo được | Kiểm tra và sửa dữ liệu trước |
| Backfill một lần trên bảng rất lớn | Transaction/lock/log quá lớn | Chia batch, theo dõi tiến độ |
| Backfill ghi đè dữ liệu mới | Mất cập nhật trong lúc rollout | Điều kiện idempotent và quy tắc nguồn dữ liệu chuẩn |
| Xóa cột cũ ngay khi deploy code mới | Instance/job cũ lỗi | Expand-contract và đợi mọi consumer chuyển đổi |
| Sửa migration đã chạy | Lịch sử môi trường không còn đồng nhất | Tạo migration mới |
| Nghĩ rollback DDL phục hồi dữ liệu | Dữ liệu đã bị mất vẫn không quay lại | Backup hoặc giữ dữ liệu gốc trong giai đoạn chuyển tiếp |
| Quên index, view, trigger hoặc FK phụ thuộc cột | Query hoặc constraint lỗi | Kiểm tra toàn bộ dependency của schema |

## 19. Bài thực hành

1. Tạo bảng `customers` có cột `display_name` và chèn dữ liệu mẫu.
2. Đổi entity property sang `fullName` nhưng giữ `@Column("display_name")`; xác định vì sao chưa cần migration.
3. Đổi mapping sang `@Column("full_name")` và xem một schema diff có thể đề xuất những thay đổi nào.
4. Viết migration RENAME COLUMN để giữ dữ liệu; xác minh số hàng và giá trị sau rename.
5. Thử mô phỏng DROP + ADD trên database kiểm thử và quan sát dữ liệu cũ bị mất.
6. Thêm cột `full_name` song song với `display_name`; backfill dữ liệu bằng UPDATE có điều kiện.
7. Viết kiểm tra các hàng chưa được backfill và các hàng có giá trị khác nhau.
8. Chuẩn hóa nhiều trạng thái cũ thành tập trạng thái mới bằng CASE; xử lý giá trị không nhận diện.
9. Thêm một unique constraint sau khi kiểm tra dữ liệu trùng.
10. Thiết kế expand-migrate-contract cho một ứng dụng có nhiều instance chạy rolling deployment.
11. Chia backfill thành batch theo ID và xác minh có thể chạy lại.
12. Viết kế hoạch rollback, chỉ rõ thay đổi nào có thể đảo ngược và dữ liệu nào cần backup.

## 20. Ghi nhớ

Schema diff phát hiện khác biệt cấu trúc giữa hai schema, nhưng không thể chắc chắn suy ra ý định đổi tên, quy tắc gộp/tách trường hoặc cách chuyển đổi từng giá trị. Một cột biến mất và cột khác xuất hiện có thể là rename, nhưng cũng có thể là xóa và thêm thuộc tính hoàn toàn mới.

Với Spring Data JDBC, mapping annotation mô tả cách ứng dụng ánh xạ aggregate; migration mới là nơi định nghĩa thay đổi schema và dữ liệu có thứ tự. Hãy review mọi script diff, thay DROP/ADD bằng RENAME khi cần giữ dữ liệu, viết backfill rõ ràng cho chuyển đổi giá trị, kiểm tra constraint trước khi áp dụng và dùng expand-migrate-contract khi các phiên bản ứng dụng cần cùng hoạt động. Bảo toàn dữ liệu và tương thích triển khai phải là tiêu chí quyết định migration, không phải chỉ làm cho hai snapshot schema giống nhau.
