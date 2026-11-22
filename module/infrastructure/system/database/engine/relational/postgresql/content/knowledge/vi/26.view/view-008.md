# Phụ thuộc schema và thay đổi hợp đồng dữ liệu

Trong PostgreSQL, **view** không đơn thuần là một câu lệnh `SELECT</BT> được lưu dưới một cái tên. View còn là **một lớp giao diện dữ liệu** giữa cấu trúc bảng vật lý và những nơi sử dụng dữ liệu: ứng dụng Java, báo cáo BI, công cụ tích hợp, ETL, API nội bộ hoặc các view khác. Khi cấu trúc bảng, kiểu dữ liệu, tên cột hay ý nghĩa nghiệp vụ thay đổi, các phụ thuộc này quyết định thay đổi nào được PostgreSQL chặn, thay đổi nào vẫn chạy được nhưng làm hỏng client, và cần triển khai theo trình tự nào.

Ví dụ một ứng dụng truy vấn:

~~~sql
SELECT customer_id, display_name, email
FROM api.customer_public_v1
WHERE customer_id = 101;
~~~

View có thể lấy dữ liệu từ bảng `core.customers</BT>, nơi tên cột vật lý là `full_name</BT>. Nếu đổi tên cột vật lý thành `legal_name</BT> mà giữ cột view là `display_name</BT>, ứng dụng có thể không cần đổi SQL. Nhưng nếu xóa cột đã được view tham chiếu, PostgreSQL sẽ bảo vệ dependency theo những quy tắc DDL. Nếu âm thầm thay đổi ý nghĩa `display_name</BT> từ tên hiển thị sang mã định danh dù kiểu dữ liệu vẫn là `text</BT>, database thường **không tự phát hiện hợp đồng nghiệp vụ đã bị phá vỡ**.

Bài thuộc chương **View** của module *Database Engine Relational PostgreSQL*. Nội dung tập trung vào phụ thuộc schema, cách PostgreSQL lưu và bảo vệ view, các giới hạn của `CREATE OR REPLACE VIEW</BT>, chiến lược thay đổi hợp đồng tương thích ngược, quyền truy cập, các truy vấn catalog kiểm tra tác động, thực hành migration và bài tập.

## 1. Hợp đồng dữ liệu là gì?

**Hợp đồng dữ liệu (data contract)** là tập kỳ vọng giữa bên cung cấp dữ liệu và bên sử dụng dữ liệu. Với một SQL view, hợp đồng thường bao gồm cả phần **cấu trúc** lẫn **ngữ nghĩa**.

| Thành phần | Ví dụ | Vì sao quan trọng |
|---|---|---|
| Tên đối tượng | `api.customer_public_v1</BT> | Client gửi SQL theo tên này |
| Tên cột | `display_name</BT> | ORM, JDBC mapper, JSON serialization dựa vào tên |
| Thứ tự cột | `customer_id</BT>, `display_name</BT>, `email</BT> | `SELECT *</BT> và mapping theo vị trí có thể phụ thuộc |
| Kiểu dữ liệu | `bigint</BT>, `text</BT>, `timestamptz</BT> | JDBC types, phép so sánh, serializing |
| Nullability thực tế | `email</BT> có thể NULL hay không? | Code Java có thể bỏ qua null check |
| Ý nghĩa nghiệp vụ | Chỉ khách hàng còn hoạt động | Filter sai làm lệch báo cáo |
| Cardinality | Một dòng trên mỗi khách hàng | JOIN giả định uniqueness |
| Độ tươi dữ liệu | Real time hay snapshot | UI và kiểm soát consistency |
| Quyền và phạm vi | Chỉ thấy tenant được phép | Bảo mật dữ liệu |
| Hành vi ghi | View có cho UPDATE/INSERT không? | Client DML cần semantics ổn định |
| Thứ tự kết quả | Có `ORDER BY</BT> ở truy vấn ngoài | Không dựa vào thứ tự ngầm |
| Phiên bản | `v1</BT>, `v2</BT> | Cho phép các clients chuyển đổi độc lập |

**Phụ thuộc catalog** của PostgreSQL có thể bảo vệ một phần hợp đồng cấu trúc. Nó không tự xác minh mọi kỳ vọng nghiệp vụ như “một customer đúng một dòng”, “doanh thu đã trừ hoàn tiền” hay “thời gian luôn ở UTC”.

## 2. View là quan hệ logic, không phải bản sao bảng

Tạo một view:

~~~sql
CREATE VIEW api.customer_public_v1 AS
SELECT
    customer_id,
    full_name AS display_name,
    email
FROM core.customers
WHERE status = 'active';
~~~

Lệnh này định nghĩa một quan hệ logic. Với **view thông thường**, PostgreSQL lưu định nghĩa truy vấn và sử dụng cơ chế rewrite/planner khi người dùng SELECT từ view. PostgreSQL không tạo một bảng heap chứa toàn bộ kết quả của view ngay khi `CREATE VIEW</BT>.

### 2.1. View giúp ẩn chi tiết vật lý

Ứng dụng chỉ biết `display_name</BT> trong view. Bảng vật lý có thể giữ `full_name</BT> hoặc sau này đổi tên thành `legal_name</BT>; view vẫn có thể giữ giao diện `display_name</BT> nếu định nghĩa tương thích.

### 2.2. View không tự đóng băng dữ liệu

Mỗi truy vấn đối với ordinary view đọc dữ liệu nền theo snapshot/isolation phù hợp. View thông thường không phải cache vĩnh viễn. **Materialized view** lại lưu kết quả vật lý và cần refresh, được trình bày riêng ở phần sau.

### 2.3. View có thể giúp kiểm soát quyền

Bạn có thể cấp quyền SELECT trên view mà không cấp quyền trực tiếp trên một số bảng nền, tùy owner, cấu hình `security_invoker</BT>, RLS và các quy tắc PostgreSQL. Nhưng view không tự là một cơ chế bảo mật tuyệt đối chỉ vì câu SELECT có WHERE.

### 2.4. Tên view là một phần API

Nếu một dashboard chạy SQL trực tiếp trên `api.customer_public_v1</BT>, việc DROP/RENAME view giống như xóa hoặc đổi tên một API endpoint. Migration phải tính cả khách hàng bên ngoài database.

## 3. PostgreSQL lưu định nghĩa view ở đâu?

View được biểu diễn trong system catalogs, với các thành phần đáng chú ý:

- `pg_class</BT>: metadata quan hệ, thường `relkind='v'</BT> cho ordinary view và `relkind='m'</BT> cho materialized view.
- `pg_attribute</BT>: các cột và kiểu dữ liệu hiện hành của quan hệ.
- `pg_rewrite</BT>: rewrite rule `_RETURN</BT> biểu diễn truy vấn định nghĩa view.
- `pg_depend</BT>: các phụ thuộc object/column/function/type/... theo catalog.
- `pg_namespace</BT>: schema sở hữu đối tượng.
- `pg_get_viewdef(...)</BT>: dựng lại SQL định nghĩa view dưới dạng dễ đọc.

### 3.1. Vì sao không chỉ lưu raw SQL?

Khi tạo view, PostgreSQL phân tích và bind tên đối tượng/cột theo catalog. Một số thay đổi tên của đối tượng nền có thể được xử lý thông qua danh tính object/attribute mà không làm view “mất liên kết” chỉ vì SQL text cũ chứa tên khác.

### 3.2. Phụ thuộc có nhiều cấp

~~~text
core.customers
      |
      v
api.customer_public_v1
      |
      +---- api.customer_report_v1
      |
      +---- báo cáo dashboard / JDBC client
                    |
                    +---- API JSON consumer
~~~

PostgreSQL có metadata để nhận diện một số quan hệ **bên trong database** (ví dụ view → table, view → view). Nhưng JDBC client, file SQL trong repository, báo cáo ngoài hệ thống hoặc công cụ BI không phải lúc nào được đăng ký vào `pg_depend</BT>. Vì vậy danh sách phụ thuộc trong catalog **chưa phải toàn bộ bản đồ ảnh hưởng**.

## 4. Phụ thuộc đối tượng và phụ thuộc cột

Một view có thể phụ thuộc vào:

1. Bảng/partitioned table/foreign table được tham chiếu.
2. Một hoặc nhiều **cột** của bảng nền.
3. Một view khác.
4. Function hoặc operator dùng trong biểu thức.
5. Kiểu dữ liệu, collation, domain hoặc những đối tượng liên quan.
6. Các objects khác theo semantics SQL và catalog.

### 4.1. Ví dụ phụ thuộc cột

~~~sql
CREATE VIEW api.customer_id_and_name AS
SELECT customer_id, full_name
FROM core.customers;
~~~

View đọc `customer_id</BT> và `full_name</BT>. Việc xóa `full_name</BT> thường bị từ chối nếu view còn phụ thuộc cột này. Nhưng thêm một cột `phone</BT> vào bảng nền thường không ảnh hưởng trực tiếp đến view này.

### 4.2. Dependency graph có hướng

Ký hiệu:

~~~text
Bảng/cột gốc  --->  View phụ thuộc  --->  View phụ thuộc tiếp
~~~

Khi sửa bảng/cột gốc, cần xét **những đối tượng nằm ở phía sau trong chuỗi phụ thuộc**, không chỉ view được tạo trực tiếp.

### 4.3. Phụ thuộc chức năng khác phụ thuộc SQL text

Trong các trường hợp SQL động, câu SQL được ghép và thực thi ở runtime có thể không được lưu thành dependency tường minh tại thời điểm tạo function. Điều này đặc biệt quan trọng với ứng dụng hoặc các function PL/pgSQL có dynamic SQL. Không coi `pg_depend</BT> là công cụ phát hiện toàn bộ text references trong code.

## 5. Bảng tương thích khi thay schema

Bảng dưới đây nêu hành vi **thường gặp** với ordinary views trên PostgreSQL hiện đại; luôn kiểm tra schema và phiên bản cụ thể.

| Thay đổi | Điều thường xảy ra | Rủi ro hợp đồng |
|---|---|---|
| Thêm cột vào bảng nền | View cũ thường giữ tập cột đã định nghĩa | Client kỳ vọng thấy cột mới nhưng view không có |
| Đổi tên cột bảng nền | View đã bind bằng metadata có thể tiếp tục hoạt động | Tên đầu ra view không tự đổi theo ý API |
| Xóa cột được view dùng | PostgreSQL thường chặn vì dependency nếu không CASCADE | Chặn migration hoặc mất view nếu ép CASCADE |
| Xóa cột không được view dùng | Thường có thể thực hiện nếu không có dependency khác | Logic ngoài database có thể vẫn dùng cột |
| Đổi kiểu cột được view dùng | Thường bị chặn vì view/rule phụ thuộc | Cần migration riêng, không chỉ ALTER TYPE |
| `CREATE OR REPLACE VIEW</BT> thay biểu thức nhưng giữ schema đầu ra | Có thể hợp lệ | Có thể phá semantics dù DDL thành công |
| Đổi tên cột đầu ra view | Cần dùng lệnh rename thích hợp | Clients query bằng tên cũ lỗi |
| Thêm cột cuối của view qua OR REPLACE | Được phép trong giới hạn tương thích | Client `SELECT *</BT> theo vị trí có thể bị ảnh hưởng |
| Đổi loại/sắp xếp cột đầu ra view qua OR REPLACE | Bị hạn chế nghiêm ngặt | Cần versioning hoặc migration có kiểm soát |
| DROP bảng hoặc view có phụ thuộc | RESTRICT mặc định thường chặn; CASCADE có thể xóa phụ thuộc | Đứt toàn bộ chuỗi consumers |

Điểm khó nhất: **DDL thành công không có nghĩa hợp đồng dữ liệu được giữ nguyên**.

## 6. SELECT * trong view là một bẫy tương thích

Giả sử:

~~~sql
CREATE VIEW api.customer_export AS
SELECT *
FROM core.customers;
~~~

Nhiều người hiểu đây là “view luôn lấy mọi cột mới của customers”. Nhưng PostgreSQL phân tích `*</BT> ở **thời điểm tạo định nghĩa view**; danh sách cột của view được thiết lập lúc đó.

### 6.1. Thêm cột bảng nền không tự làm view rộng hơn

~~~sql
ALTER TABLE core.customers
ADD COLUMN phone TEXT;
~~~

View `api.customer_export</BT> đã tồn tại **không tự động có cột phone** chỉ vì bảng có cột mới.

### 6.2. Vì sao có lợi và bất lợi?

Lợi: hợp đồng cột không vô tình thay đổi khi bảng nội bộ thêm dữ liệu mới.

Bất lợi: người viết view dựa trên `SELECT *</BT> có thể ngạc nhiên vì view không phản ánh schema mới.

### 6.3. Luôn khai báo explicit column list cho view đóng vai trò API

~~~sql
CREATE VIEW api.customer_public_v1 AS
SELECT
    customer_id,
    full_name AS display_name,
    email,
    created_at
FROM core.customers
WHERE status = 'active';
~~~

Cách này làm rõ tên, thứ tự, kiểu và nguồn của từng cột. Khi người khác đọc migration, họ dễ thấy hợp đồng nào bị tác động.

### 6.4. SELECT * ở client cũng đáng tránh

Client Java:

~~~sql
SELECT * FROM api.customer_public_v1;
~~~

có thể phụ thuộc vào thứ tự cột và metadata. Khi thêm một cột cuối view, ORM hoặc mapper dùng vị trí có thể hoạt động khác. Nên chỉ yêu cầu cột client thật sự sử dụng.

## 7. Đổi tên cột bảng nền: cột view không tự đổi tên

Giả sử view:

~~~sql
CREATE VIEW api.customer_public_v1 AS
SELECT
    customer_id,
    full_name AS display_name
FROM core.customers;
~~~

Sau khi:

~~~sql
ALTER TABLE core.customers
RENAME COLUMN full_name TO legal_name;
~~~

PostgreSQL thường vẫn có thể thực thi view vì dependency trỏ tới **thuộc tính của bảng**, không chỉ là chuỗi SQL cũ.

### 7.1. Quan sát định nghĩa đã cập nhật

~~~sql
SELECT pg_get_viewdef(
    'api.customer_public_v1'::regclass,
    true
);
~~~

Định nghĩa hiển thị có thể tham chiếu `legal_name</BT> làm cột nguồn, nhưng **đầu ra view vẫn là `display_name</BT>**.

### 7.2. Vì sao hữu ích cho migration?

Bạn có thể đổi tên cột nội bộ để phản ánh mô hình dữ liệu mới mà vẫn giữ tên API bên ngoài. Đây là lợi thế của view như một lớp chống thay đổi (*compatibility layer*).

### 7.3. Không áp dụng suy luận này cho mọi client SQL

Nếu ứng dụng đang query trực tiếp:

~~~sql
SELECT full_name FROM core.customers;
~~~

thì việc rename sẽ làm SQL đó lỗi. PostgreSQL bảo vệ view dependency bên trong database, **không sửa câu SQL nằm trong repository ứng dụng**.

## 8. Xóa một cột được view sử dụng

Giả sử view đọc `email</BT>:

~~~sql
CREATE VIEW api.customer_contact AS
SELECT customer_id, email
FROM core.customers;
~~~

Thử xóa cột:

~~~sql
ALTER TABLE core.customers
DROP COLUMN email;
~~~

Nếu view phụ thuộc cột đó, PostgreSQL thường từ chối thao tác và báo có object dependency. Đây là hành vi bảo vệ quan hệ schema.

### 8.1. RESTRICT giúp tránh đứt gãy ngầm

Với các lệnh DROP hỗ trợ, hành vi RESTRICT/mặc định ngăn xóa đối tượng còn phụ thuộc. Điều này không phiền toái vô cớ: nó nhắc bạn lập kế hoạch thay đổi toàn chuỗi.

### 8.2. CASCADE có thể rất nguy hiểm

~~~sql
-- MINH HỌA RỦI RO: KHÔNG CHẠY TRÊN HỆ THỐNG THẬT
ALTER TABLE core.customers
DROP COLUMN email CASCADE;
~~~

CASCADE có thể xóa view và các đối tượng phụ thuộc liên quan. Nếu những đối tượng đó là API mà client đang sử dụng, toàn hệ thống có thể lỗi dù migration DDL đã commit.

### 8.3. Phương án an toàn hơn

- Tạo cột thay thế.
- Di chuyển dữ liệu.
- Tạo view phiên bản mới dùng cột thay thế.
- Chuyển dần client.
- Xác nhận không còn người dùng cột/view cũ.
- Sau cùng mới drop cột cũ bằng migration có kiểm soát.

**CASCADE là công cụ phụ thuộc**, không phải một nút “sửa lỗi migration”.

## 9. Đổi kiểu dữ liệu của cột được view tham chiếu

Giả sử `email</BT> đang là `text</BT> và bạn muốn chuyển sang kiểu khác hoặc thay đổi representation.

~~~sql
ALTER TABLE core.customers
ALTER COLUMN email TYPE VARCHAR(200);
~~~

Trong nhiều trường hợp PostgreSQL **không cho đổi kiểu cột đang được view hoặc rule sử dụng**, ngay cả khi một phép cast có vẻ đơn giản. Database phải bảo vệ định nghĩa đã bind và kiểu đầu ra view.

### 9.1. Không giả định CAST tự giải dependency

Một statement có `USING email::varchar(200)</BT> không đồng nghĩa PostgreSQL sẽ tự thay đổi mọi view đang tham chiếu cột. Dependency view/rule có thể vẫn chặn thay đổi.

### 9.2. Dùng add-copy-switch thay vì đổi trực tiếp

Một quy trình:

1. `ADD COLUMN email_new ...</BT>.
2. Backfill/đồng bộ giá trị từ email.
3. Tạo view `v2</BT> có kiểu/semantics mới.
4. Cho consumers chuyển sang v2.
5. Xử lý dependencies của v1.
6. Drop cột cũ khi không còn sử dụng.

### 9.3. Thêm CAST trong view cũng có giới hạn

Nếu cần giữ hợp đồng kiểu `text</BT> với bảng nội bộ kiểu mới:

~~~sql
SELECT email_new::text AS email
FROM core.customers;
~~~

Cách làm phù hợp có thể che kiểu mới dưới v1, nhưng **chỉ khi các thay đổi nội bộ được thực hiện theo thứ tự tránh đụng dependency**. Không thể đổi trực tiếp cột cũ đang được view bind rồi hy vọng CAST ở v1 tự xuất hiện.

### 9.4. Kiểu giống nhau không bảo đảm ngữ nghĩa giống nhau

Thay `email</BT> từ địa chỉ gốc sang giá trị đã hash có thể vẫn là `text</BT>, PostgreSQL không chặn được nếu DDL vẫn hợp lệ. Đó là **breaking semantic change**.

## 10. CREATE OR REPLACE VIEW: có thể sửa gì?

PostgreSQL hỗ trợ:

~~~sql
CREATE OR REPLACE VIEW api.customer_public_v1 AS
SELECT
    customer_id,
    full_name AS display_name,
    lower(email) AS email
FROM core.customers
WHERE status = 'active';
~~~

Nhưng **CREATE OR REPLACE VIEW không cho thay đổi tùy ý mọi khía cạnh schema đầu ra**.

### 10.1. Những điều kiện cốt lõi

Với các cột đã tồn tại của view, truy vấn mới phải giữ **cùng tên cột, cùng thứ tự, cùng kiểu dữ liệu** theo các quy tắc PostgreSQL; có thể bổ sung **các cột mới ở cuối** danh sách.

### 10.2. Thêm cột cuối có thể hợp lệ

View ban đầu:

~~~sql
CREATE VIEW api.customer_public_v1 AS
SELECT customer_id, full_name AS display_name
FROM core.customers;
~~~

Thay thế bằng:

~~~sql
CREATE OR REPLACE VIEW api.customer_public_v1 AS
SELECT
    customer_id,
    full_name AS display_name,
    email
FROM core.customers;
~~~

Thêm `email</BT> sau hai cột cũ có thể hợp lệ.

### 10.3. Đổi vị trí cột không phải thao tác tương thích

Nếu một view hiện là:

~~~text
customer_id BIGINT
display_name TEXT
email TEXT
~~~

thì định nghĩa mới trả `email</BT> trước `display_name</BT> không được coi là tương thích chỉ vì cả hai là text. PostgreSQL kiểm tra tên/thứ tự/kiểu cột đầu ra.

### 10.4. Đổi tên cột không dùng OR REPLACE tùy tiện

Nếu muốn đổi tên cột đầu ra, PostgreSQL thường yêu cầu thao tác rename view column, ví dụ:

~~~sql
ALTER VIEW api.customer_public_v1
RENAME COLUMN display_name TO public_name;
~~~

Nhưng đây là **breaking change cho mọi client** đang truy vấn `display_name</BT>. Nếu cần hỗ trợ song song, thường nên tạo `v2</BT> thay vì rename v1.

### 10.5. Thêm cột cuối vẫn có thể phá client

PostgreSQL cho phép bổ sung cột ở cuối, nhưng client dùng `SELECT *</BT>, `INSERT INTO ... SELECT *</BT> hoặc deserialize theo số lượng cột có thể bị ảnh hưởng. **Database-level replace compatibility không đồng nghĩa application-level backward compatibility**.

### 10.6. OR REPLACE có thể đổi semantics âm thầm

Hai SELECT cùng tên/thứ tự/kiểu vẫn có thể dùng điều kiện WHERE khác nhau hoặc đổi công thức:

~~~sql
CREATE OR REPLACE VIEW api.active_customer_count AS
SELECT COUNT(*)::bigint AS count
FROM core.customers
WHERE status = 'active';
~~~

Nếu thay `status='active'</BT> bằng một tiêu chí mới, PostgreSQL có thể chấp nhận DDL nhưng kết quả báo cáo thay đổi. Migration phải có semantic tests.

## 11. DROP VIEW, RESTRICT và CASCADE

Giả sử:

~~~text
core.customers
      |
      v
api.customer_public_v1
      |
      v
api.customer_summary_v1
~~~

Khi:

~~~sql
DROP VIEW api.customer_public_v1;
~~~

PostgreSQL có thể từ chối vì `customer_summary_v1</BT> còn phụ thuộc, trừ khi có xử lý thích hợp.

### 11.1. CASCADE xóa chuỗi phụ thuộc

~~~sql
-- CHỈ MINH HỌA RỦI RO
DROP VIEW api.customer_public_v1 CASCADE;
~~~

Lệnh có thể làm mất view phụ thuộc ở tầng sau.

### 11.2. Còn grants và metadata

Khi DROP rồi CREATE lại, object identity thay đổi. Owner, grants, comments và một số thông tin liên quan có thể cần tái thiết lập, tùy migration. `CREATE OR REPLACE VIEW</BT> thường giữ chính đối tượng view hiện tại và các quyền liên quan, khác với DROP/CREATE.

### 11.3. Không dùng CASCADE để “đơn giản hóa deploy”

Ở database có hàng trăm views/BI clients, xóa theo cascade có thể phá hợp đồng diện rộng. Hãy lập bản đồ phụ thuộc, tạo v2, chuyển consumers và chỉ dọn v1 sau khi xác nhận.

## 12. Đổi tên bảng hoặc chuyển schema

Ngoài cột, PostgreSQL quản lý danh tính các relations bằng metadata như object OID.

### 12.1. Đổi tên bảng nền

~~~sql
ALTER TABLE core.customers
RENAME TO customer_accounts;
~~~

View đã bind tới bảng có thể tiếp tục hoạt động dưới tên bảng mới, trong khi câu SQL mới do client gửi trực tiếp bằng `core.customers</BT> sẽ lỗi nếu tên cũ không tồn tại.

### 12.2. Chuyển bảng sang schema khác

~~~sql
ALTER TABLE core.customer_accounts
SET SCHEMA internal;
~~~

Cần có schema `internal</BT> và quyền phù hợp. View phụ thuộc object có thể còn hoạt động nhờ danh tính object, nhưng **SQL ứng dụng** viết đường dẫn cũ sẽ không được tự sửa.

### 12.3. search_path và tên không đủ điều kiện

Trong `CREATE VIEW</BT>, các tên bảng/hàm không schema-qualified được giải quyết theo `search_path</BT> tại thời điểm phân tích định nghĩa. Khi deploy ở hai môi trường có search_path khác nhau, một DDL cùng text có thể bind vào các objects khác nhau.

### 12.4. Dùng tên schema-qualified cho migrations

~~~sql
CREATE VIEW api.customer_public_v1 AS
SELECT customer_id, full_name AS display_name
FROM core.customers;
~~~

Tên đầy đủ giúp giảm nguy cơ resolve nhầm khi nhiều schemas có tables trùng tên.

### 12.5. Không dùng RENAME như API versioning

Đổi tên bảng vật lý có thể là một bước refactor, nhưng đổi tên view mà client sử dụng vẫn là thay hợp đồng. Cần phân biệt tên nội bộ và tên endpoint SQL.

## 13. View phụ thuộc function, operator và biểu thức

View có thể gọi hàm:

~~~sql
CREATE VIEW api.customer_normalized AS
SELECT
    customer_id,
    lower(email) AS normalized_email
FROM core.customers;
~~~

Ở đây định nghĩa view phụ thuộc vào phép toán/hàm tương ứng và cột `email</BT>.

### 13.1. Hàm tự định nghĩa

~~~sql
CREATE FUNCTION core.format_customer_name(p_name TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT btrim(p_name);
$$;
~~~

Sau đó:

~~~sql
CREATE VIEW api.customer_formatted AS
SELECT
    customer_id,
    core.format_customer_name(full_name) AS display_name
FROM core.customers;
~~~

### 13.2. Thay thân hàm có thể đổi semantics mà không đổi view schema

Nếu `CREATE OR REPLACE FUNCTION</BT> giữ chữ ký nhưng đổi logic formatting, view vẫn có thể compile/chạy nhưng kết quả thay đổi. Đây là một loại **semantic contract change**.

### 13.3. Function overloads và kiểu

Nếu tạo overload mới hoặc đổi tên schema, parser có thể chọn hàm theo tham số và search_path khi tạo/replace view. Không chỉ nhìn tên hàm mà bỏ qua argument types và schema qualification.

### 13.4. Dynamic SQL không được bao phủ toàn bộ bởi catalog

Nếu một function PL/pgSQL dùng `EXECUTE</BT> với SQL động dựa trên tên bảng truyền vào, dependency graph catalog có thể không thấy mọi bảng được tham chiếu ở runtime. Khi thay schema, phải tìm thêm references trong code/tests/logs.

## 14. Sự thay đổi hợp đồng không chỉ nằm ở DDL

Một SQL view có cấu trúc không đổi nhưng có thể làm client sai:

### 14.1. Thay ngữ nghĩa filter

Ban đầu view chỉ chứa customers có `status='active'</BT>. Một người đổi WHERE thành mọi customers, khiến báo cáo tăng số dòng dù không hề thay tên hay kiểu cột.

### 14.2. Thay cardinality

Một view ban đầu một row/customer, sau này JOIN vào bảng addresses có nhiều rows/customer:

~~~sql
SELECT c.customer_id, c.full_name, a.address_line
FROM core.customers AS c
JOIN core.addresses AS a
  ON a.customer_id = c.customer_id;
~~~

Nếu một customer có ba addresses, query có thể trả ba rows cho customer. Các consumers từng giả định `customer_id</BT> unique có thể tính sai.

### 14.3. Thay nghĩa của NULL

Ban đầu email luôn có giá trị; sau migration trả NULL cho khách chưa xác minh. Kiểu vẫn là `text</BT> nhưng Java code có thể gặp NPE hoặc JSON schema không hợp lệ.

### 14.4. Thay timezone

Đổi từ local timestamp sang UTC instant nhưng vẫn trả kiểu `timestamp without time zone</BT> có thể làm lệch dữ liệu hiển thị trong khi schema không đổi. Nên dùng kiểu và contract rõ như `timestamptz</BT> cho instants nếu phù hợp.

### 14.5. Thay đơn vị đo

Một cột `amount</BT> từ đơn vị đồng sang nghìn đồng vẫn là numeric nhưng gây sai báo cáo nghiêm trọng. Có thể cần cột mới như `amount_minor_units</BT> và API version mới.

### 14.6. Thứ tự kết quả không được ngầm bảo đảm

Một view định nghĩa SELECT mà không có thứ tự rõ ràng không hứa thứ tự rows. Client cần `ORDER BY</BT> trong query ngoài khi cần ổn định. Ngay cả khi view có ORDER BY nội bộ, không nên coi đó là hợp đồng thứ tự của mọi truy vấn ngoài.

## 15. View như compatibility layer

Một cách thiết kế là **giữ giao diện ổn định, cho phép schema vật lý tiến hóa**:

~~~text
JDBC / BI / API
       |
       v
api.customer_public_v1
       |
       v
core.customers
       |
       v
physical columns / indexes / partitions
~~~

### 15.1. Alias bảo vệ tên

`full_name AS display_name</BT> giúp tên API không bị đồng nhất với tên nội bộ.

### 15.2. Cast bảo vệ kiểu

Nếu v1 cam kết email dạng text, bạn có thể cast biểu thức thích hợp trong view miễn được tạo/triển khai đúng dependency order.

### 15.3. Filter bảo vệ scope

View chỉ lộ customers active hoặc data theo quy tắc đã công bố; tuy nhiên dùng view để kiểm soát quyền cần phân tích sâu về security semantics.

### 15.4. Compatibility có giới hạn

Một view không tự giải quyết:

- Global uniqueness.
- Data quality.
- Versioning của mọi semantic rule.
- Client dùng SQL trực tiếp trên bảng nền.
- Chênh lệch performance do JOIN phức tạp.
- Permissions mà owner/invoker không được cấp.
- Migration giữa nhiều database servers.

## 16. Tạo view phiên bản v1, v2

Khi thay đổi hợp đồng lớn, thường nên **tạo view mới** thay vì thay ngay v1.

~~~sql
CREATE VIEW api.customer_public_v1 AS
SELECT
    customer_id,
    full_name AS display_name,
    email
FROM core.customers;

CREATE VIEW api.customer_public_v2 AS
SELECT
    customer_id,
    full_name AS display_name,
    email,
    phone AS contact_phone
FROM core.customers;
~~~

### 16.1. Hai contracts cùng tồn tại

- Client cũ tiếp tục query v1.
- Client mới chuyển sang v2 và sử dụng `contact_phone</BT>.
- Migration theo từng consumer, không phải deploy tất cả cùng một thời điểm.

### 16.2. Khi nào không cần v2?

Nếu sửa bug không thay cấu trúc/semantics cam kết và đã được đánh giá tương thích, `CREATE OR REPLACE VIEW</BT> có thể đơn giản hơn. Nhưng thay đổi hành vi dữ liệu vẫn cần đo/test.

### 16.3. Đánh dấu deprecation

Có thể đặt COMMENT và tài liệu vận hành:

~~~sql
COMMENT ON VIEW api.customer_public_v1 IS
'Compatibility contract v1; deprecate after consumers migrate to v2.';
~~~

COMMENT là metadata, **không tự gửi thông báo đến clients**; cần lộ trình và ownership.

### 16.4. Không xóa v1 chỉ vì v2 đã tạo

Phải xác nhận các callers, report jobs, stored queries, permissions và các dependent views đã chuyển. Catalog có thể không nhìn thấy toàn bộ applications bên ngoài.

## 17. Chiến lược expand–migrate–contract

Đây là cách triển khai thay đổi schema khi ứng dụng và database không thể được nâng cấp hoàn toàn cùng một thời điểm.

~~~text
EXPAND
  Thêm cấu trúc mới mà vẫn giữ cũ
          |
          v
MIGRATE
  Backfill, dual-read/dual-write, chuyển clients
          |
          v
VERIFY
  Kiểm tra contract và dữ liệu
          |
          v
CONTRACT
  Gỡ cấu trúc cũ khi không còn phụ thuộc
~~~

### 17.1. Expand: thay đổi cộng thêm

~~~sql
ALTER TABLE core.customers
ADD COLUMN preferred_name TEXT;
~~~

Bảng có cột mới nhưng view v1 chưa cần đổi.

### 17.2. Đồng bộ và backfill

~~~sql
UPDATE core.customers
SET preferred_name = full_name
WHERE preferred_name IS NULL;
~~~

Đây chỉ là ví dụ minh họa; bảng lớn cần backfill theo batches, transaction/locks và xử lý writes phát sinh đồng thời.

### 17.3. Tạo v2

~~~sql
CREATE VIEW api.customer_public_v2 AS
SELECT
    customer_id,
    preferred_name AS display_name,
    email
FROM core.customers
WHERE status = 'active';
~~~

### 17.4. Chuyển consumers

Deploy các ứng dụng có thể đọc v2, cập nhật SQL, DAO/ORM, BI report và contract tests; đo lỗi thực tế.

### 17.5. Contract cuối cùng

Sau khi xác nhận không còn phụ thuộc vào v1 hoặc cột cũ, mới cân nhắc DROP đối tượng cũ với kế hoạch rollback phù hợp.

### 17.6. Vì sao tránh big-bang?

Trong thực tế, instances ứng dụng có thể được rolling deploy và job báo cáo chạy theo lịch. Giữ song song hai versions giảm yêu cầu tất cả callers chuyển cùng thời điểm.

## 18. Lab tổng hợp: thiết lập môi trường an toàn

Những phần sau dùng schema riêng **chỉ để thực hành**. Chạy trong database thử nghiệm; nếu `view_contract_lab</BT> đã tồn tại, dùng tên khác để tránh xung đột. Không xóa các đối tượng có dữ liệu công việc thật.

### 18.1. Tạo schema

~~~sql
CREATE SCHEMA view_contract_lab;
~~~

### 18.2. Tạo bảng nền

~~~sql
CREATE TABLE view_contract_lab.customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

### 18.3. Thêm dữ liệu mẫu

~~~sql
INSERT INTO view_contract_lab.customers(
    full_name, email, status
)
VALUES
    ('Nguyen An', 'an@example.test', 'active'),
    ('Tran Binh', 'binh@example.test', 'active'),
    ('Le Chi', 'chi@example.test', 'inactive');
~~~

Dữ liệu mẫu dùng domain `example.test</BT>, không phải địa chỉ khách hàng thật.

### 18.4. Tạo v1, chủ động alias đầu ra

~~~sql
CREATE VIEW view_contract_lab.customer_public_v1 AS
SELECT
    customer_id,
    full_name AS display_name,
    email,
    created_at
FROM view_contract_lab.customers
WHERE status = 'active';
~~~

### 18.5. Tạo view phụ thuộc v1

~~~sql
CREATE VIEW view_contract_lab.customer_labels_v1 AS
SELECT
    customer_id,
    display_name
FROM view_contract_lab.customer_public_v1;
~~~

Khi đó:

~~~text
view_contract_lab.customers
          |
          v
view_contract_lab.customer_public_v1
          |
          v
view_contract_lab.customer_labels_v1
~~~

Lab này giúp quan sát **dependency chain** và tác động của DROP/ALTER.

## 19. Lab: SELECT từ view và xem định nghĩa

### 19.1. Đọc dữ liệu v1

~~~sql
SELECT
    customer_id,
    display_name,
    email,
    created_at
FROM view_contract_lab.customer_public_v1
ORDER BY customer_id;
~~~

View trả khách hàng active theo WHERE của nó.

### 19.2. Đọc view phụ thuộc

~~~sql
SELECT *
FROM view_contract_lab.customer_labels_v1
ORDER BY customer_id;
~~~

View này chỉ hiển thị customer_id và display_name.

### 19.3. Xem định nghĩa qua pg_get_viewdef

~~~sql
SELECT pg_get_viewdef(
    'view_contract_lab.customer_public_v1'::regclass,
    true
) AS definition;
~~~

Hàm trả SQL SELECT được dựng lại. Dạng whitespace/alias hiển thị có thể khác text ban đầu, nhưng ngữ nghĩa được lưu trong rewrite representation.

### 19.4. Xem thông tin cột qua information_schema

~~~sql
SELECT
    ordinal_position,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'view_contract_lab'
  AND table_name = 'customer_public_v1'
ORDER BY ordinal_position;
~~~

Lưu ý: một số thông tin về nullability qua view có thể không phản ánh đầy đủ mọi ràng buộc suy luận từ bảng nền. Không sử dụng `is_nullable</BT> của view như bằng chứng tuyệt đối cho mọi invariant nghiệp vụ.

## 20. Lab: thêm cột bảng nhưng view vẫn giữ hợp đồng cũ

### 20.1. Thêm phone

~~~sql
ALTER TABLE view_contract_lab.customers
ADD COLUMN phone TEXT;
~~~

### 20.2. Nạp một số số điện thoại mẫu

~~~sql
UPDATE view_contract_lab.customers
SET phone = CASE
    WHEN customer_id = 1 THEN '0900000001'
    WHEN customer_id = 2 THEN '0900000002'
    ELSE NULL
END;
~~~

### 20.3. Kiểm tra view v1

~~~sql
SELECT *
FROM view_contract_lab.customer_public_v1
ORDER BY customer_id;
~~~

Cột `phone</BT> **không tự xuất hiện** trong v1.

### 20.4. Kiểm tra bảng nền

~~~sql
SELECT customer_id, full_name, email, phone
FROM view_contract_lab.customers
ORDER BY customer_id;
~~~

Cột đã có ở bảng nền. Đây là sự khác biệt giữa database schema và view contract.

### 20.5. Tạo v2 thay vì đổi v1

~~~sql
CREATE VIEW view_contract_lab.customer_public_v2 AS
SELECT
    customer_id,
    full_name AS display_name,
    email,
    phone AS contact_phone,
    created_at
FROM view_contract_lab.customers
WHERE status = 'active';
~~~

### 20.6. Kiểm tra cả hai versions

~~~sql
SELECT customer_id, display_name, email
FROM view_contract_lab.customer_public_v1;

SELECT customer_id, display_name, email, contact_phone
FROM view_contract_lab.customer_public_v2;
~~~

V1 tiếp tục hoạt động cho clients cũ; v2 có thêm phone với tên output do API kiểm soát.

## 21. Lab: đổi tên cột vật lý nhưng giữ view contract

Trong **database lab**, chạy:

~~~sql
ALTER TABLE view_contract_lab.customers
RENAME COLUMN full_name TO legal_name;
~~~

### 21.1. View v1 vẫn có display_name

~~~sql
SELECT customer_id, display_name
FROM view_contract_lab.customer_public_v1
ORDER BY customer_id;
~~~

### 21.2. View v2 cũng vậy

~~~sql
SELECT customer_id, display_name, contact_phone
FROM view_contract_lab.customer_public_v2
ORDER BY customer_id;
~~~

### 21.3. Xem định nghĩa sau rename

~~~sql
SELECT pg_get_viewdef(
    'view_contract_lab.customer_public_v1'::regclass,
    true
);
~~~

Bạn có thể thấy tên cột nguồn đổi theo bảng vật lý, nhưng output alias vẫn là `display_name</BT>.

### 21.4. Client truy vấn bảng nền thì khác

SQL:

~~~sql
SELECT full_name
FROM view_contract_lab.customers;
~~~

sẽ không còn hợp lệ sau rename; phải dùng `legal_name</BT>. Do đó giữ clients ở lớp view có thể giảm coupling, nhưng chỉ nếu clients thật sự dùng view.

## 22. Lab: những DDL bị chặn bởi dependency

Các câu tiếp theo **cố ý minh họa lỗi phụ thuộc**, không thuộc phần setup bắt buộc. Chỉ chạy từng câu riêng trong database thử nghiệm khi muốn quan sát thông báo lỗi.

### 22.1. Thử xóa cột đang được view dùng

~~~sql
-- MINH HỌA: DỰ KIẾN BỊ PostgreSQL TỪ CHỐI
ALTER TABLE view_contract_lab.customers
DROP COLUMN email;
~~~

V1/v2 còn tham chiếu email. PostgreSQL thường báo object khác phụ thuộc cột.

### 22.2. Thử thay kiểu cột

~~~sql
-- MINH HỌA: DỰ KIẾN BỊ CHẶN KHI VIEW/RULE DÙNG CỘT
ALTER TABLE view_contract_lab.customers
ALTER COLUMN email TYPE VARCHAR(200);
~~~

Đừng coi đây là bước migration chính thức. Khi lệnh lỗi trong transaction hiện hành, cần ROLLBACK hoặc xử lý savepoint trước khi thực hiện các lệnh khác.

### 22.3. Thử DROP v1 khi view labels còn phụ thuộc

~~~sql
-- MINH HỌA: DỰ KIẾN BỊ CHẶN VÌ VIEW PHỤ THUỘC
DROP VIEW view_contract_lab.customer_public_v1;
~~~

### 22.4. Không dùng CASCADE để vượt qua bài tập

~~~sql
-- KHÔNG CHẠY TRÊN DỮ LIỆU CẦN GIỮ
DROP VIEW view_contract_lab.customer_public_v1 CASCADE;
~~~

Lệnh có thể xóa cả `customer_labels_v1</BT> và các object phụ thuộc khác. Mục tiêu là hiểu PostgreSQL chặn vì lý do đúng, không phá dependency graph để “lệnh chạy được”.

## 23. Lab: CREATE OR REPLACE VIEW tương thích

Nếu muốn **thêm cột cuối** vào v1 (trong một thay đổi đã được kiểm tra tương thích), định nghĩa phải giữ tên, thứ tự và kiểu các cột cũ:

~~~sql
CREATE OR REPLACE VIEW view_contract_lab.customer_public_v1 AS
SELECT
    customer_id,
    legal_name AS display_name,
    email,
    created_at,
    phone AS contact_phone
FROM view_contract_lab.customers
WHERE status = 'active';
~~~

### 23.1. Vì sao lệnh này có thể hợp lệ?

Bốn cột đầu giữ thứ tự/tên/kiểu của v1; `contact_phone</BT> là cột mới ở cuối.

### 23.2. View phụ thuộc trước đó

~~~sql
SELECT customer_id, display_name
FROM view_contract_lab.customer_labels_v1;
~~~

View phụ thuộc đã tồn tại có thể tiếp tục sử dụng hai cột cũ. Nhưng external consumer `SELECT * FROM v1</BT> có thể giờ nhận thêm một cột và cần kiểm tra compatibility.

### 23.3. Đổi tên cột trong OR REPLACE sẽ bị từ chối

Ví dụ chỉ thay `display_name</BT> thành `legal_name</BT> trong vị trí cũ không phải cách rename output column qua CREATE OR REPLACE. Muốn rename dùng `ALTER VIEW ... RENAME COLUMN</BT>; nếu clients cũ còn dùng tên cũ, hãy giữ v1 và tạo v2.

### 23.4. Lời khuyên với hợp đồng versioned

Bài lab cho thấy điều PostgreSQL **cho phép về DDL**. Trong hệ thống production, nếu v1 là hợp đồng được công bố chặt chẽ, thêm cột v1 vẫn nên đánh giá trước, và có thể giữ v1 nguyên để v2 có toàn quyền tiến hóa.

## 24. Đọc dependency của view qua pg_rewrite và pg_depend

PostgreSQL có thể ghi phụ thuộc của view ở các bản ghi liên quan đến rewrite rule `_RETURN</BT>.

~~~sql
SELECT DISTINCT
    v.oid::regclass AS view_name,
    d.refobjid::regclass AS referenced_relation,
    a.attname AS referenced_column,
    d.deptype AS dependency_type
FROM pg_class AS v
JOIN pg_rewrite AS r
  ON r.ev_class = v.oid
JOIN pg_depend AS d
  ON d.classid = 'pg_rewrite'::regclass
 AND d.objid = r.oid
 AND d.refclassid = 'pg_class'::regclass
LEFT JOIN pg_attribute AS a
  ON a.attrelid = d.refobjid
 AND a.attnum = d.refobjsubid
WHERE v.oid =
    'view_contract_lab.customer_public_v1'::regclass
  AND d.refobjid <> v.oid
ORDER BY
    referenced_relation,
    referenced_column;
~~~

### 24.1. Ý nghĩa của refobjid và refobjsubid

- `refobjid</BT>: OID object được tham chiếu.
- `refobjsubid</BT>: với các dependency ở mức cột, giá trị có thể biểu diễn số thứ tự attribute; 0 thường chỉ phụ thuộc mức relation.
- `pg_attribute.attnum</BT>: số thứ tự attribute tương ứng.
- `pg_attribute.attname</BT>: tên cột.

### 24.2. Vì sao join pg_rewrite?

Định nghĩa view là rewrite rule liên kết với relation view. Một số dependency của query nằm trên **rewrite rule**, không chỉ một dependency trực tiếp từ OID của view.

### 24.3. Vì sao loại self-reference?

Rewrite rule có những dependency nội bộ tới chính view, không phải mọi dòng đều là “bảng nguồn”. Điều kiện `d.refobjid <> v.oid</BT> giúp tập trung vào những relations khác.

### 24.4. Không coi catalog output là biểu đồ ứng dụng hoàn chỉnh

Query này chỉ liệt kê nhóm dependency relation được lưu theo catalog và bộ lọc của nó. Nó không tìm Java SQL strings, external dashboards, mọi function runtime hoặc mọi loại dependency ở refclassid khác.

## 25. Tìm những view đang phụ thuộc một bảng

Khi muốn biết đối tượng nào có khả năng bị ảnh hưởng nếu sửa `view_contract_lab.customers</BT>:

~~~sql
SELECT DISTINCT
    dependent.oid::regclass AS dependent_relation,
    a.attname AS referenced_column
FROM pg_depend AS d
JOIN pg_rewrite AS r
  ON r.oid = d.objid
JOIN pg_class AS dependent
  ON dependent.oid = r.ev_class
 AND dependent.relkind IN ('v', 'm')
LEFT JOIN pg_attribute AS a
  ON a.attrelid = d.refobjid
 AND a.attnum = d.refobjsubid
WHERE d.classid = 'pg_rewrite'::regclass
  AND d.refclassid = 'pg_class'::regclass
  AND d.refobjid =
      'view_contract_lab.customers'::regclass
  AND dependent.oid <> d.refobjid
ORDER BY dependent_relation, referenced_column;
~~~

### 25.1. Query này tập trung vào direct references

View `customer_labels_v1</BT> phụ thuộc v1, chứ không nhất thiết có dependency trực tiếp đến bảng customers. Cần xét **đường phụ thuộc nhiều tầng** nếu định xóa hoặc thay đổi object ở đáy.

### 25.2. Phụ thuộc nhiều tầng trong migration

Một graph có thể là:

~~~text
customers -> customer_public_v1 -> customer_labels_v1 -> report_job
~~~

Nếu thay `customers.email</BT>, direct dependency có thể bao gồm v1/v2; nhưng các reports dựa trên v1 vẫn chịu ảnh hưởng ngữ nghĩa. Truy vấn catalog có thể lặp/đệ quy qua view relationships, còn external jobs phải được kiểm tra qua source repository và ownership inventory.

### 25.3. Không chỉ lọc theo tên text

Cột `email</BT> có thể xuất hiện trong nhiều schemas. Dùng `regclass</BT>/OIDs giúp xác định chính xác relation, thay vì tìm chuỗi tên ngắn dễ nhầm.

## 26. Xem toàn bộ các cột của một view bằng catalog

~~~sql
SELECT
    a.attnum AS ordinal_position,
    a.attname AS column_name,
    format_type(a.atttypid, a.atttypmod) AS column_type,
    a.attnotnull AS declared_not_null
FROM pg_attribute AS a
WHERE a.attrelid =
      'view_contract_lab.customer_public_v1'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

### 26.1. Dùng làm contract snapshot

Kết quả cho biết thứ tự cột, tên và kiểu của view hiện tại. Có thể lưu các thông tin này thành manifest migration để so sánh **bằng kiểm thử bên ngoài STEP 4**.

### 26.2. Nullability của view cần diễn giải thận trọng

Một biểu thức `coalesce(email,'')</BT> không đảm bảo catalog của view sẽ thể hiện mọi phép suy luận not-null như người phát triển mong muốn. Hợp đồng nullable/non-nullable cần thêm tests và khai báo ứng dụng khi cần.

### 26.3. Kiểu được report chính xác hơn qua format_type

`format_type</BT> có thể hiển thị `character varying(200)</BT> hoặc numeric precision/scale có ý nghĩa cho client. Không chỉ xem tên kiểu thô mà bỏ typmod.

## 27. Information_schema giúp gì?

Nếu không cần truy cập catalog PostgreSQL-specific, `information_schema</BT> cung cấp một số views thông tin chuẩn SQL, như:

~~~sql
SELECT
    table_schema,
    table_name,
    view_definition
FROM information_schema.views
WHERE table_schema = 'view_contract_lab';
~~~

và:

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    ordinal_position,
    data_type
FROM information_schema.columns
WHERE table_schema = 'view_contract_lab'
ORDER BY table_name, ordinal_position;
~~~

### 27.1. Ưu điểm

Dễ đọc cho các tác vụ kiểm tra thông tin phổ thông và có tính gần chuẩn SQL hơn.

### 27.2. Giới hạn

Metadata có thể phụ thuộc quyền người dùng, không trình bày toàn bộ dependency graph hoặc các thuộc tính PostgreSQL-specific. Khi cần phân tích object references chính xác, dùng catalogs và đúng quyền truy cập.

### 27.3. Không trộn thông tin schemas

Tên view `customer_public_v1</BT> có thể tồn tại trong nhiều schemas. Luôn có `table_schema</BT> trong truy vấn metadata và khi triển khai.

## 28. ALTER VIEW và những thay đổi khác

Ngoài `CREATE OR REPLACE VIEW</BT>, PostgreSQL có một số lệnh quản lý view, chẳng hạn:

~~~sql
ALTER VIEW view_contract_lab.customer_public_v1
RENAME TO customer_public_legacy;
~~~

hoặc:

~~~sql
ALTER VIEW view_contract_lab.customer_public_v1
RENAME COLUMN display_name TO customer_name;
~~~

Các ví dụ này là **DDL có thể phá hợp đồng**. Không chạy sau các bước lab nếu muốn giữ những câu SQL sau đó tham chiếu tên cũ.

### 28.1. Đổi tên view

Phụ thuộc catalog bên trong có thể tiếp tục tham chiếu đúng object theo OID, nhưng external SQL clients gọi tên cũ sẽ lỗi.

### 28.2. Đổi tên cột view

Các dependent views đã bind với cột có thể có hành vi được PostgreSQL quản lý ở metadata, nhưng client SQL trực tiếp đọc tên cũ cần đổi. Không coi DDL thành công là mọi consumers đều đã sẵn sàng.

### 28.3. Đổi owner

`ALTER VIEW ... OWNER TO ...</BT> có thể thay đổi ngữ nghĩa quyền của view với bảng nền tùy cấu hình, dù schema đầu ra không đổi.

### 28.4. Chuyển schema của view

`ALTER VIEW ... SET SCHEMA ...</BT> đổi đường dẫn object được ứng dụng tham chiếu, cần kiểm tra tên đầy đủ và quyền USAGE trên schema.

## 29. Quyền truy cập là một phần hợp đồng

Giả sử client chỉ có quyền:

~~~sql
GRANT SELECT
ON view_contract_lab.customer_public_v1
TO app_reader;
~~~

Đây là ví dụ cấp quyền cho **role đã tồn tại**. Trong lab, không chạy nếu role `app_reader</BT> không có hoặc bạn không có quyền GRANT.

### 29.1. GRANT không thay quyền schema

Người dùng còn cần quyền truy cập namespace/schema theo quy tắc PostgreSQL, ví dụ `USAGE ON SCHEMA</BT> thích hợp.

### 29.2. View mặc định thường dùng quyền owner cho bảng nền

Trong PostgreSQL, với ordinary view theo mặc định, quyền truy cập các base relations được kiểm tra dựa trên view owner theo những ngữ nghĩa cụ thể; quyền của caller trên chính view vẫn phải phù hợp.

### 29.3. SECURITY INVOKER

Từ PostgreSQL 15, view có thể dùng option `security_invoker=true</BT> để quyền trên relations nền được kiểm tra theo invoker trong các trường hợp tương ứng:

~~~sql
CREATE VIEW view_contract_lab.customer_public_invoker
WITH (security_invoker = true)
AS
SELECT customer_id, legal_name
FROM view_contract_lab.customers;
~~~

Nếu user chỉ có SELECT trên view mà **không có quyền cần thiết trên bảng nền**, truy vấn có thể bị từ chối. Không thêm `security_invoker</BT> chỉ vì tên option có vẻ “an toàn hơn” nếu không hiểu mô hình quyền.

### 29.4. Permissions change cũng có thể phá client

Một migration REVOKE/GRANT không thay tên view hay kiểu cột nhưng có thể làm mọi query của application role lỗi. Quyền là một phần của data contract.

## 30. RLS, security_barrier và ranh giới bảo mật

### 30.1. RLS

Row-Level Security trên bảng nền có thể ảnh hưởng rows client được phép nhìn. View owner/invoker mode và role bypass behavior là những yếu tố cần xét; không giả định một query chạy bằng superuser phản ánh đúng kết quả của application role.

### 30.2. security_barrier view

Với một số use cases bảo mật, view có option:

~~~sql
CREATE VIEW view_contract_lab.active_customers_barrier
WITH (security_barrier = true)
AS
SELECT customer_id, legal_name, email
FROM view_contract_lab.customers
WHERE status = 'active';
~~~

Option này giới hạn một số phép tối ưu di chuyển điều kiện của caller xuyên qua view theo quy tắc security/leakproof functions, giúp bảo vệ một số trường hợp lộ thông tin qua evaluation order.

### 30.3. Trade-off hiệu năng

`security_barrier</BT> có thể hạn chế predicate pushdown và khiến kế hoạch khác view bình thường. Không dùng nó như “cờ tăng tốc”. Nó là công cụ bảo mật có chi phí tiềm năng.

### 30.4. security_barrier không thay RLS/GRANT

Một view chứa WHERE không thay toàn bộ authorization. Cần xác định ai có quyền SELECT trực tiếp bảng nền, ai làm owner view, ai có BYPASSRLS, và functions có nguy cơ leak dữ liệu không.

### 30.5. Versioning chính sách quyền

Nếu v2 lộ thêm cột nhạy cảm, không được sao chép grants từ v1 một cách máy móc. Xem rõ dữ liệu nào được phép xuất hiện, vai trò truy cập, audit logging và data classification.

## 31. View có cho INSERT, UPDATE, DELETE không?

Một số view đơn giản trên một bảng có thể **automatically updatable** theo điều kiện PostgreSQL. Nhưng view chứa GROUP BY, aggregates, DISTINCT, nhiều JOIN hoặc cấu trúc phức tạp thường không tự cập nhật được theo cách tương tự.

### 31.1. Ví dụ view đơn giản

~~~sql
CREATE VIEW view_contract_lab.active_customers_editable AS
SELECT customer_id, legal_name, email, status
FROM view_contract_lab.customers
WHERE status = 'active';
~~~

Tùy cấu trúc và điều kiện liên quan, nó có thể là automatically updatable view.

### 31.2. WITH CHECK OPTION

~~~sql
CREATE VIEW view_contract_lab.active_customers_checked AS
SELECT customer_id, legal_name, email, status
FROM view_contract_lab.customers
WHERE status = 'active'
WITH LOCAL CHECK OPTION;
~~~

`WITH CHECK OPTION</BT> liên quan đảm bảo những rows ghi qua view đáp ứng điều kiện view theo semantics PostgreSQL. Nó không thay toàn bộ business validation hoặc RLS.

### 31.3. Thay view có thể thay write contract

Một view từ SELECT đơn giản đổi thành JOIN hoặc aggregate có thể giữ một số cột tương tự nhưng mất khả năng INSERT/UPDATE tự động. Client ghi vào view có thể lỗi sau migration.

### 31.4. INSTEAD OF triggers

Một số view cần trigger `INSTEAD OF</BT> để xử lý ghi theo logic riêng. Khi thay schema bảng nền, trigger functions cũng phải được kiểm tra; catalog không luôn thấy toàn bộ dynamic SQL bên trong function.

### 31.5. Đừng chỉ test SELECT

Nếu view được dùng để ghi dữ liệu, contract tests phải kiểm tra INSERT/UPDATE/DELETE, lỗi constraint, RETURNING, transaction và quyền theo application role.

## 32. Materialized view và hợp đồng dữ liệu

**Materialized view** khác ordinary view vì nó lưu dữ liệu kết quả vật lý.

~~~sql
CREATE MATERIALIZED VIEW view_contract_lab.customer_counts_mv AS
SELECT status, COUNT(*)::bigint AS customer_count
FROM view_contract_lab.customers
GROUP BY status;
~~~

### 32.1. Snapshot, không tự phản ánh write mới tức thì

Sau khi bảng customers thay đổi, materialized view vẫn có snapshot cũ cho tới lúc refresh:

~~~sql
REFRESH MATERIALIZED VIEW
view_contract_lab.customer_counts_mv;
~~~

### 32.2. Refresh là một phần contract freshness

Client phải biết dữ liệu báo cáo được cập nhật bao lâu một lần và có chấp nhận stale không. Đây là khác biệt quan trọng so với ordinary view.

### 32.3. Indexes trên materialized view

Materialized view có storage vật lý riêng và có thể có indexes riêng, khác ordinary view không có heap data để tạo index trực tiếp theo cùng cách.

### 32.4. REFRESH CONCURRENTLY có điều kiện

PostgreSQL hỗ trợ `REFRESH MATERIALIZED VIEW CONCURRENTLY</BT> trong những điều kiện cụ thể, bao gồm index unique thích hợp, và không thể thực hiện tùy ý nếu chưa đáp ứng yêu cầu. Không mặc định cứ có materialized view là có thể refresh concurrently.

### 32.5. Thay schema bảng nền vẫn có dependency

Materialized view cũng có thể phụ thuộc bảng/cột/objects khác. Những migrations làm đổi cột được tham chiếu cần xét đúng dependency và phương án tạo/refresh lại, đồng thời tính đến thời gian snapshot.

## 33. View nối nhiều bảng: contract và cardinality

Một view tổng hợp khách hàng với đơn hàng:

~~~sql
CREATE VIEW view_contract_lab.customer_order_totals AS
SELECT
    c.customer_id,
    c.legal_name AS display_name,
    COUNT(o.order_id)::bigint AS order_count
FROM view_contract_lab.customers AS c
LEFT JOIN view_contract_lab.orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.legal_name;
~~~

Ví dụ này **yêu cầu bảng orders tồn tại** và chỉ minh họa logic; không chạy trong lab nếu chưa tạo `orders</BT>.

### 33.1. JOIN có thể làm thay cardinality

Một customer có nhiều orders. Nếu không aggregate, view có thể trả nhiều rows/customer; với aggregate, group key và JOIN shape xác định cardinality.

### 33.2. Thay bảng phụ thuộc có thể làm query chậm

Thêm JOIN, filter hoặc expression mà không đổi schema view vẫn có thể làm thời gian truy vấn tăng mạnh. Contract của ứng dụng thường có cả latency/SLO, không chỉ cột.

### 33.3. View thường được planner mở rộng

Ordinary view không mặc định tạo lớp materialized tốn I/O. Planner có thể biến đổi truy vấn qua view trong các giới hạn ngữ nghĩa/bảo mật. Tuy nhiên, một query qua nhiều views/JOINs có thể phức tạp và cần EXPLAIN thực tế.

### 33.4. Không đổi semantics để tối ưu nếu chưa thông báo

Nếu bỏ JOIN để giảm latency nhưng làm thiếu dữ liệu nghiệp vụ, bạn đã phá contract dù SELECT nhanh hơn.

## 34. Thay đổi schema trên môi trường đang chạy

Một migration production phải đối diện concurrent queries và rolling deployments.

### 34.1. Database DDL có locks

Các lệnh `ALTER TABLE</BT>, `DROP</BT>, `CREATE OR REPLACE VIEW</BT> và thao tác liên quan có thể yêu cầu locks. Trên hệ thống bận, migration có thể phải chờ transaction dài hoặc chặn câu SQL khác trong thời gian ngắn/dài tùy tình huống.

### 34.2. DDL transactional

Nhiều PostgreSQL DDL statements có thể chạy trong transaction và rollback nếu thất bại. Nhưng không được giả định mọi câu lệnh quản trị với `CONCURRENTLY</BT> hay những thao tác đặc biệt đều có thể nằm trong cùng transaction block.

### 34.3. Tránh DROP+CREATE không cần thiết

Nếu chỉ sửa định nghĩa tương thích, `CREATE OR REPLACE VIEW</BT> thường giảm nguy cơ thay object identity/grants so với DROP/CREATE. Nếu cần breaking change, tạo v2 thay vì phụ thuộc CASCADE.

### 34.4. Chuẩn bị lock timeout

~~~sql
BEGIN;
SET LOCAL lock_timeout = '3s';

-- Thực hiện DDL nhỏ đã kiểm tra trước ở staging.

COMMIT;
~~~

Đây là khung vận hành, không tự thay đổi schema. `lock_timeout</BT> giảm nguy cơ chờ vô hạn, nhưng migration bị timeout cần được xử lý/rollback và có thể phải retry theo kế hoạch.

### 34.5. Backfill bảng lớn

Không mặc định chạy một UPDATE toàn bảng hàng trăm triệu rows trong một transaction. Cần batch sizing, WAL capacity, autovacuum, index costs, concurrency và cơ chế đồng bộ writes mới.

### 34.6. Deploy code theo trình tự

Nếu app mới cần cột v2, tạo cột/view trước rồi deploy app mới. Nếu app cũ vẫn sống trong rolling deploy, giữ v1 đến khi app cũ đã ngừng gọi.

## 35. Ma trận tương thích khi rolling deploy

Giả sử database có hai thế hệ schema và ứng dụng có hai versions.

| App | DB chỉ có v1 | DB có v1 và v2 | DB chỉ có v2 |
|---|---|---|---|
| App cũ dùng v1 | Hoạt động nếu contract v1 đúng | Hoạt động | Lỗi nếu v1 bị gỡ |
| App mới dùng v2 | Lỗi nếu v2 chưa tồn tại | Hoạt động | Hoạt động nếu contract v2 đúng |
| Job cũ theo lịch | Hoạt động | Hoạt động | Lỗi nếu chưa migrate |
| Dashboard ngoài app | Tùy references | Tùy references | Có thể lỗi nếu dùng v1 |

### 35.1. Kịch bản triển khai an toàn

1. Mở rộng bảng nền.
2. Tạo v2 nhưng **giữ v1**.
3. Kiểm tra quyền của application role.
4. Deploy app mới.
5. Chuyển jobs/dashboards.
6. Theo dõi việc còn truy vấn v1.
7. Xác nhận thời hạn deprecation.
8. Sau cùng mới bỏ v1/cột cũ.

### 35.2. Không thể dùng catalog để xác nhận tất cả client đã chuyển

View có thể không có dependent view nào trong database nhưng vẫn được gọi bởi một batch job chạy mỗi quý. Cần inventory và logs/metrics/query telemetry thích hợp, cùng trao đổi với owners.

## 36. Contract tests cho view

Một hợp đồng view tốt cần được xác nhận ở hai tầng: **schema** và **ngữ nghĩa**.

### 36.1. Schema shape

~~~sql
SELECT
    a.attnum,
    a.attname,
    format_type(a.atttypid, a.atttypmod)
FROM pg_attribute AS a
WHERE a.attrelid =
    'view_contract_lab.customer_public_v1'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

Kiểm tra đúng tên, số thứ tự và kiểu cột.

### 36.2. Contract về lọc dữ liệu

~~~sql
SELECT COUNT(*)
FROM view_contract_lab.customer_public_v1
WHERE customer_id IN (
    SELECT customer_id
    FROM view_contract_lab.customers
    WHERE status <> 'active'
);
~~~

Trong lab, kết quả lý tưởng là 0 vì view chỉ xuất khách hàng active. Với dữ liệu lớn, kiểm thử tích hợp nên dùng fixture/điều kiện rõ để tránh phụ thuộc dữ liệu ngẫu nhiên.

### 36.3. Cardinality

~~~sql
SELECT customer_id, COUNT(*)
FROM view_contract_lab.customer_public_v1
GROUP BY customer_id
HAVING COUNT(*) > 1;
~~~

Nếu contract cam kết một row/customer, kết quả cần rỗng.

### 36.4. Truy vấn bằng application role

Schema có thể đúng khi chạy bằng owner nhưng fail do GRANT/RLS khi chạy bằng role ứng dụng. Cần test permissions trong ngữ cảnh đúng.

### 36.5. JDBC mapping

Ứng dụng Java có thể xác nhận `ResultSetMetaData</BT> trả tên/kiểu cột mong muốn và dữ liệu ánh xạ được vào DTO, kể cả NULL, timestamp và numeric precision.

### 36.6. Semantic fixtures

Tạo dữ liệu thử gồm khách active/inactive, tên rỗng/Unicode, email thay đổi, nhiều orders nếu view tổng hợp, rồi assert kết quả cụ thể. Schema checks không thay semantic tests.

## 37. Java/JDBC: view là một phần giao diện ổn định

Ví dụ Java dùng PreparedStatement để query v1:

~~~java
String sql = """
    SELECT customer_id, display_name, email
    FROM view_contract_lab.customer_public_v1
    WHERE customer_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 1L);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            long id = rs.getLong("customer_id");
            String name = rs.getString("display_name");
            String email = rs.getString("email");
            // Map sang DTO theo hợp đồng v1.
        }
    }
}
~~~

Ví dụ dùng Java text blocks (Java 15+). Với Java cũ, thay bằng chuỗi Java thông thường.

### 37.1. Tách DTO v1 và v2

Nếu hợp đồng v2 đổi email/phone/semantics, không ép cùng một DTO nhận mọi phiên bản nếu nó làm mơ hồ nullability hoặc validation.

### 37.2. Tham số thay vì nối chuỗi

Dùng `?</BT> cho giá trị tham số SQL để tránh injection và có typing rõ. Tên schema/view là identifier, không bind bằng dấu `?</BT>; nếu cần chọn nhiều versions, dùng whitelist các tên hợp lệ.

### 37.3. Prepared statements sau DDL

Các cached prepared plans có thể cần invalidation/replanning khi schema thay đổi, và những thay đổi kiểu cột kết quả có thể gây lỗi ở protocol/caller. Việc giữ v1 ổn định giảm nguy cơ những prepared SQL statements đột ngột đổi result shape.

### 37.4. Không cho phép client tự phụ thuộc bảng nền

Nếu ứng dụng chỉ được cấp quyền đọc `api.*</BT> và không đọc trực tiếp `core.*</BT>, lớp view có thể giữ các thay đổi vật lý bên trong không gian ít phụ thuộc client hơn, với điều kiện quyền và security semantics đã được thiết kế đúng.

## 38. Đo tác động hiệu năng bằng EXPLAIN

Khi thay một view từ query đơn giản sang nhiều JOINs hoặc tính toán, thời gian và số lượng hàng có thể đổi dù tên view không đổi.

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    customer_id,
    display_name
FROM view_contract_lab.customer_public_v1
WHERE customer_id = 1;
~~~

### 38.1. Xem kế hoạch base tables

Ordinary view thường được rewrite và tối ưu như một truy vấn. EXPLAIN có thể hiện scan trên `view_contract_lab.customers</BT>, không nhất thiết có node “View Scan” riêng.

### 38.2. Predicate pushdown

Nếu view chỉ là filter/alias, điều kiện `customer_id=1</BT> từ caller có thể được planner đẩy vào scan bảng nền, tùy semantics và rào cản liên quan.

### 38.3. Security barrier

Với `security_barrier=true</BT>, một số phép chuyển predicate có thể bị giới hạn để bảo vệ ngữ nghĩa bảo mật; plan/latency có thể khác view thường.

### 38.4. Materialized view

SELECT từ materialized view đọc dữ liệu đã được materialize và có thể dùng index của materialized view; nhưng dữ liệu có thể stale đến lần REFRESH tiếp theo.

### 38.5. Đừng dùng EXPLAIN ANALYZE bừa bãi với DML

`EXPLAIN ANALYZE</BT> **thực thi câu SQL**. Với INSERT/UPDATE/DELETE, cần transaction thử nghiệm có rollback hoặc môi trường riêng; không chạy trên production rồi nghĩ đó chỉ là kiểm tra lý thuyết.

## 39. Tác động từ index và schema nền

View thường không có index riêng để tạo theo cú pháp index trên bảng vật lý. Khi view query chậm, cần xem indexes ở **bảng nền**.

### 39.1. Index theo predicate

Nếu nhiều clients query v1 theo `customer_id</BT>, primary key/index của bảng nền có thể giúp planner.

### 39.2. Thay view có thể thay index eligibility

Nếu v1 dùng `WHERE status='active'</BT> và v2 thay bằng expression trên status hoặc join qua bảng khác, index path có thể thay. Cần đo plan và statistics.

### 39.3. Không tách view và index tuning

Một view trở thành API lâu dài nên có ownership cả về schema contract lẫn hiệu năng truy vấn. Mỗi lần sửa expression/filter có thể làm index không còn phù hợp.

### 39.4. Cached plans

Prepared/generic plans và phân phối tham số có thể ảnh hưởng chọn index. Test với dữ liệu/tham số đại diện, không chỉ một example row.

## 40. Quản lý thứ tự migration theo dependency graph

Một quy tắc tổng quát:

- **Tạo mới**: tạo bảng/cột/hàm trước, rồi tạo view phụ thuộc.
- **Thay tương thích**: thay đổi phần trong nhưng giữ giao diện ngoài, kiểm tra owner/grants và semantics.
- **Thay breaking**: tạo version mới, migrate consumers, cuối cùng mới xóa version cũ.
- **Xóa**: gỡ consumers phụ thuộc theo thứ tự từ ngoài vào trong.

### 40.1. Graph ví dụ

~~~text
customers
    |
    v
customer_public_v1
    |
    +------ customer_labels_v1
    |              |
    |              +------ report_A
    |
    +------ dashboard_B
~~~

Nếu drop customers, tác động lan đến mọi node sau. Nếu cần bỏ customer_labels_v1, trước đó phải chuyển report_A.

### 40.2. Không dựa vào tên view có số version để giả định dependencies

`v2</BT> có thể được định nghĩa dựa trên `v1</BT>, khiến việc drop v1 vẫn bị chặn. Nếu mục tiêu là tách lifecycle, có thể tạo v2 từ bảng nền hoặc một lớp shared internal view ổn định, tùy cách bảo trì.

### 40.3. Migrations phải idempotent theo ý nghĩa, không chỉ cú pháp

`CREATE OR REPLACE VIEW</BT> không biến mọi thay đổi thành tương thích. Chạy lại migration phải giữ schema/semantics đã công bố, không làm mất grants/comments hoặc sai data transformations.

## 41. Tài liệu hóa quyền sở hữu hợp đồng

Mỗi view có vai trò API nên có:

| Trường | Ví dụ |
|---|---|
| View | `api.customer_public_v1</BT> |
| Owner | Nhóm dữ liệu khách hàng |
| Consumers | Customer service, BI, ETL |
| Version | v1 |
| Trạng thái | Active / Deprecated |
| Key | customer_id |
| Cardinality | Một row/customer active |
| Time semantics | created_at là timestamptz |
| Nullability | email không NULL theo nghiệp vụ |
| Data freshness | Theo snapshot của SELECT |
| Security | Chỉ role được cấp SELECT; RLS theo mô hình |
| SLA/SLO | p95 và availability nếu có |
| Deprecation deadline | Sau khi tất cả consumers chuyển v2 |

### 41.1. COMMENT trong database

~~~sql
COMMENT ON VIEW view_contract_lab.customer_public_v1 IS
'Public customer contract v1. Consumers should migrate before deprecation.';
~~~

### 41.2. COMMENT chưa đủ

Metadata ở database không tự theo dõi những SQL jobs nằm ngoài, không nhắc owners về deadline và không thay governance process.

### 41.3. Có thể version hóa DDL trong repository

Định nghĩa views và migrations trong source control giúp review thay đổi hợp đồng, tạo môi trường staging và phục hồi định nghĩa tương thích.

## 42. Các sai lầm thường gặp

### 42.1. “View là query string, rename cột nền chắc chắn làm view lỗi”

Không đúng chung. PostgreSQL lưu/bind dependencies; rename cột nền có thể được xử lý mà view tiếp tục hoạt động.

### 42.2. “Thêm cột vào bảng sẽ tự thêm cột vào view SELECT *”

Sai. Danh sách cột view được xác lập khi tạo/replace view.

### 42.3. “DDL thành công nghĩa không breaking change”

Sai. Semantics, cardinality, NULL, quyền hoặc latency có thể đổi dù kiểu/tên không đổi.

### 42.4. “CREATE OR REPLACE VIEW cho đổi mọi tên/kiểu/thứ tự”

Sai. PostgreSQL hạn chế thay các cột hiện có; thường chỉ cho thêm cột cuối theo quy tắc.

### 42.5. “Thêm cột cuối luôn tương thích với mọi client”

Không chắc. Clients dùng SELECT * và positional mapping có thể bị ảnh hưởng.

### 42.6. “Có thể DROP column used by view tùy ý”

Sai. PostgreSQL quản lý dependencies và thường chặn nếu không xử lý rõ.

### 42.7. “CASCADE là cách an toàn để deploy nhanh”

Sai. Nó có thể xóa cả dependent views và các đối tượng quan trọng.

### 42.8. “ALTER TYPE với USING sẽ tự đổi mọi view”

Không đúng. Dependency của view/rule có thể chặn.

### 42.9. “Đổi tên cột nền tự đổi tên cột output của view”

Sai. Alias/output contract có thể giữ nguyên.

### 42.10. “Đổi tên view không ảnh hưởng client”

Sai. Client query bằng tên cũ sẽ lỗi.

### 42.11. “Catalog liệt kê hết mọi ứng dụng dùng view”

Sai. External SQL strings/BI/ETL không luôn được ghi vào pg_depend.

### 42.12. “Bảng không có dependent view nên được xóa chắc chắn”

Sai. Có thể có application code, dynamic SQL, jobs hoặc integrations ngoài catalog.

### 42.13. “View không có storage thì không có dependencies”

Sai. Ordinary view vẫn có rewrite rule, column types và dependencies.

### 42.14. “Materialized view luôn là dữ liệu mới nhất”

Sai. Nó là snapshot cần refresh.

### 42.15. “Materialized view giống ordinary view trong DDL/indexes”

Sai. Materialized view có storage và index/refresh semantics riêng.

### 42.16. “View luôn an toàn làm security boundary”

Không đúng chung. Cần phân tích ownership, grants, RLS, security_invoker, security_barrier và leakproof behavior.

### 42.17. “security_invoker và security_barrier cùng nghĩa”

Sai. Một option liên quan quyền invoker ở bảng nền; một option liên quan một số giới hạn optimizer để bảo vệ security semantics.

### 42.18. “GRANT SELECT ON VIEW tự bao gồm USAGE ON SCHEMA trong mọi trường hợp”

Sai. Quyền schema/object là các khía cạnh khác nhau.

### 42.19. “Đổi owner view không thể tác động ai được xem dữ liệu”

Sai. Ownership có thể ảnh hưởng quyền kiểm tra bảng nền theo mô hình view.

### 42.20. “Một view SELECT được thì chắc chắn INSERT/UPDATE được”

Sai. Khả năng updatable có điều kiện; JOIN/aggregate thường cần cơ chế riêng.

### 42.21. “VIEW WITH CHECK OPTION thay mọi constraint”

Sai. Nó kiểm tra điều kiện view theo semantics được hỗ trợ, không thay FK, uniqueness hay mọi business invariant.

### 42.22. “Query qua view luôn chậm hơn query bảng”

Sai. Ordinary view thường được rewrite và tối ưu; chi phí phụ thuộc query thực, indexes và security boundaries.

### 42.23. “View có ORDER BY nội bộ nên mọi client tự thấy đúng thứ tự”

Không nên dựa vào đó. Hãy dùng ORDER BY trong query consumer khi cần ổn định.

### 42.24. “DROP+CREATE giữ nguyên grants/comments”

Không mặc định. Object identity và metadata có thể đổi; cần tái áp dụng quyền và tài liệu hóa.

### 42.25. “Chỉ cần unit test DDL”

Sai. Cần contract tests cho schema, semantics, quyền, DML nếu dùng, và integration với client.

## 43. Bài tập thực hành

### Bài 1 — Hợp đồng

Nêu năm thành phần của data contract cho một view public.

**Gợi ý:** Tên, tên cột, thứ tự, kiểu, semantics, quyền, freshness.

### Bài 2 — Dependency graph

View A đọc bảng B; view C đọc A. Khi drop B, những node nào có nguy cơ bị ảnh hưởng?

**Gợi ý:** A, C và external clients.

### Bài 3 — SELECT *

Tạo view `SELECT * FROM table</BT>, rồi ADD COLUMN cho table. Cột mới tự xuất hiện trong view cũ không?

**Đáp án:** Không mặc định; view đã lưu danh sách cột.

### Bài 4 — Rename physical column

Nếu `full_name</BT> được view xuất dưới alias `display_name</BT>, rename cột nền thành `legal_name</BT> có bắt client đổi alias không?

**Gợi ý:** Không nhất thiết; view dependency/alias có thể giữ.

### Bài 5 — Direct SQL

Vì sao client query trực tiếp cột `full_name</BT> của bảng nền vẫn có thể bị lỗi sau rename?

**Gợi ý:** SQL của client không tự được PostgreSQL sửa.

### Bài 6 — DROP column

Cột email được view tham chiếu. PostgreSQL có thể từ chối DROP COLUMN vì sao?

**Gợi ý:** Object dependency.

### Bài 7 — CASCADE

Vì sao `DROP ... CASCADE</BT> rủi ro với public views?

**Gợi ý:** Nó xóa dependent objects.

### Bài 8 — ALTER TYPE

Một view đọc cột text. ALTER cột nền thành varchar có luôn chạy được không?

**Đáp án:** Không; dependency view/rule có thể chặn.

### Bài 9 — OR REPLACE

Có thể dùng CREATE OR REPLACE VIEW để thay kiểu dữ liệu cột đầu ra đã tồn tại tùy ý không?

**Đáp án:** Không.

### Bài 10 — Thêm cột cuối

Một view có columns (id bigint, name text). Thêm email text ở cuối bằng CREATE OR REPLACE có thể hợp lệ không?

**Gợi ý:** Có trong giới hạn giữ tên/thứ tự/kiểu cũ.

### Bài 11 — Đổi thứ tự

Thay thứ tự name và email trong view có phải chỉ là formatting không?

**Đáp án:** Không; thứ tự là một phần result shape.

### Bài 12 — Rename view column

Lệnh nào dùng để đổi tên output column của view?

**Đáp án:** `ALTER VIEW ... RENAME COLUMN ...</BT>.

### Bài 13 — Semantic break

Một view vẫn trả text `amount</BT> nhưng đơn vị tính đổi; database có bắt lỗi không?

**Gợi ý:** Không tự kiểm tra business semantics.

### Bài 14 — Cardinality

Một JOIN thêm nhiều address rows cho mỗi customer. Kỳ vọng “một row/customer” còn đúng không?

**Đáp án:** Không nhất thiết.

### Bài 15 — Nullability

Nếu email có thể NULL sau migration, Java mapper có thể gặp vấn đề gì?

**Gợi ý:** Null handling, validation, JSON contract.

### Bài 16 — Materialized view

Ordinary view khác materialized view về freshness thế nào?

**Gợi ý:** Ordinary view query bảng nền; materialized lưu snapshot và cần refresh.

### Bài 17 — Dependencies

Hai catalogs quan trọng để tìm view query dependency là gì?

**Đáp án:** `pg_rewrite</BT> và `pg_depend</BT>.

### Bài 18 — pg_attribute

Catalog nào lưu thông tin cột và số thứ tự của view?

**Đáp án:** `pg_attribute</BT>.

### Bài 19 — pg_get_viewdef

Hàm nào dựng lại định nghĩa SELECT của view?

**Đáp án:** `pg_get_viewdef</BT>.

### Bài 20 — Direct vs transitive

Một view phụ thuộc v1 mà không tham chiếu trực tiếp bảng customers. Query tìm direct dependencies của customers có chắc hiển thị nó không?

**Gợi ý:** Không; cần xét nhiều tầng.

### Bài 21 — External consumers

pg_depend có biết mọi truy vấn từ Java repository không?

**Đáp án:** Không.

### Bài 22 — search_path

Vì sao nên schema-qualify bảng/hàm trong CREATE VIEW dùng làm API?

**Gợi ý:** Giảm bind nhầm do search_path.

### Bài 23 — View versioning

Khi muốn đổi kiểu và semantics cột đang có v1, tại sao v2 thường an toàn hơn?

**Gợi ý:** Cho phép clients chuyển dần, giữ v1.

### Bài 24 — Expand–contract

Sắp xếp: xóa cột cũ, thêm cột mới, backfill, chuyển clients, xác minh.

**Đáp án gợi ý:** Thêm → backfill/đồng bộ → chuyển → xác minh → xóa.

### Bài 25 — Rolling deploy

App cũ vẫn query v1. Có nên drop v1 ngay khi app mới đã deploy lên 10% instances?

**Đáp án:** Không.

### Bài 26 — GRANT

Vì sao cần test SQL của view bằng application role, không chỉ superuser?

**Gợi ý:** Quyền, RLS và security_invoker có thể khác.

### Bài 27 — security_invoker

Option này chủ yếu liên quan quyền truy cập bảng nền theo ai?

**Đáp án:** Invoker trong các semantics tương ứng.

### Bài 28 — security_barrier

Option này chủ yếu ảnh hưởng điều gì?

**Gợi ý:** Một số phép tối ưu/đánh giá biểu thức qua view nhằm giữ security semantics.

### Bài 29 — Updatable view

Một view GROUP BY COUNT(*) có tự UPDATE như simple one-table view không?

**Gợi ý:** Không theo cơ chế automatically updatable thông thường.

### Bài 30 — WITH CHECK OPTION

Lựa chọn này giúp kiểm tra gì khi ghi qua view phù hợp?

**Gợi ý:** Row tiếp tục đáp ứng điều kiện view theo semantics hỗ trợ.

### Bài 31 — DDL locks

Vì sao migration ALTER TABLE trên bảng lớn cần xem concurrent workload?

**Gợi ý:** Locks và thời gian chờ có thể ảnh hưởng queries.

### Bài 32 — CREATE OR REPLACE vs DROP/CREATE

Vì sao OR REPLACE thường ít phá object identity hơn?

**Gợi ý:** Giữ view hiện hữu thay vì tạo object mới.

### Bài 33 — Contract metadata

Viết truy vấn liệt kê cột/kiểu/thứ tự của v1 bằng `pg_attribute</BT>.

**Gợi ý:** Dựa trên query ở mục 26.

### Bài 34 — Semantic test

Làm sao xác minh view customer_public_v1 chỉ chứa khách active?

**Gợi ý:** Fixture inactive và assert không trả row đó.

### Bài 35 — Cardinality test

Viết GROUP BY HAVING để tìm customer_id bị trùng trong view.

**Gợi ý:** `GROUP BY customer_id HAVING COUNT(*) > 1</BT>.

### Bài 36 — JDBC

Vì sao `ResultSet.getString("display_name")</BT> bền hơn mapping theo vị trí khi view được mở rộng?

**Gợi ý:** Không phụ thuộc ordinal cột theo cùng mức.

### Bài 37 — Prepared SQL

Có thể bind tên view bằng dấu hỏi như một giá trị thông thường không?

**Đáp án:** Không. Identifier phải được chọn/quote bằng cơ chế riêng; dùng whitelist nếu có nhiều versions.

### Bài 38 — Performance

Ordinary view có luôn cần materialize toàn bộ trước khi lọc `customer_id</BT> ở caller không?

**Đáp án:** Không; planner thường có thể tối ưu qua view theo giới hạn.

### Bài 39 — Inventory

Không thấy dependent view trong catalog; có thể drop v1 chắc chắn không?

**Đáp án:** Không, external consumers có thể tồn tại.

### Bài 40 — Phương án hoàn chỉnh

Bảng customers hiện có `full_name text</BT>. Bạn muốn tên nội bộ thành `legal_name</BT>, thêm `preferred_name</BT>, và API mới dùng preferred name khi có. Thiết kế kế hoạch không phá app cũ.

**Gợi ý:** Giữ v1 display_name; thêm preferred_name, backfill/đồng bộ, tạo v2 display_name theo ngữ nghĩa mới, chuyển clients, xác minh, sau cùng deprecate v1. Rename cột nền có thể thực hiện có kiểm soát khi view dependencies được giữ.

## 44. Bảng ghi nhớ cuối bài

| Khái niệm | Cần nhớ |
|---|---|
| Ordinary view | SELECT logic được PostgreSQL rewrite khi truy vấn |
| Materialized view | Lưu snapshot, cần REFRESH |
| Data contract | Schema và semantics của giao diện dữ liệu |
| Object dependency | View phụ thuộc table/view/function/type/... |
| Column dependency | View tham chiếu những cột cụ thể |
| `pg_rewrite</BT> | Rewrite rule lưu định nghĩa view |
| `pg_depend</BT> | Metadata phụ thuộc |
| `pg_attribute</BT> | Cột và kiểu của relation |
| `pg_get_viewdef</BT> | Dựng SQL định nghĩa view |
| `information_schema.views</BT> | Metadata view cấp thông tin chuẩn |
| `information_schema.columns</BT> | Danh sách cột theo quyền hiện hành |
| `SELECT *</BT> trong CREATE VIEW | Mở rộng lúc tạo, không tự thêm cột mới |
| Rename cột nền | View có thể tiếp tục theo dependency |
| Drop cột được view dùng | Thường bị chặn nếu chưa xử lý dependent |
| ALTER TYPE cột được view dùng | Có thể bị chặn bởi view/rule |
| RESTRICT | Bảo vệ đối tượng còn dependency |
| CASCADE | Có thể xóa phụ thuộc dây chuyền |
| `CREATE OR REPLACE VIEW</BT> | Giữ schema cột cũ, có thể thêm cột cuối |
| `ALTER VIEW RENAME COLUMN</BT> | Đổi tên cột đầu ra, có thể break clients |
| Schema-qualified names | Giảm rủi ro search_path bind sai |
| Contract v1/v2 | Cho phép chuyển clients theo giai đoạn |
| Expand–migrate–contract | Thêm mới → chuyển → xóa cũ |
| Semantic change | Có thể phá nghiệp vụ dù kiểu/tên không đổi |
| Cardinality | Số hàng theo business key cần giữ |
| RLS/GRANT | Quyền và phạm vi cũng là contract |
| `security_invoker</BT> | Quyền bảng nền theo invoker trong điều kiện hỗ trợ |
| `security_barrier</BT> | Giới hạn tối ưu vì security semantics |
| Updatable view | Khả năng ghi phụ thuộc cấu trúc query |
| `WITH CHECK OPTION</BT> | Kiểm tra visibility của rows ghi qua view |
| External consumers | Không luôn có trong pg_depend |
| Contract tests | Schema, semantics, quyền, DML và JDBC |
| EXPLAIN | Đo tác động kế hoạch/performance |
| Migration rollback | Cần chuẩn bị trước khi drop/contract |

---

## Kết luận

Một view trong PostgreSQL vừa là **đối tượng có phụ thuộc schema được database theo dõi**, vừa có thể là **hợp đồng dữ liệu với những người dùng ở bên ngoài database**. Hai lớp bảo vệ này không giống nhau.

PostgreSQL giúp giữ các dependency giữa view và bảng/cột/function, nên những thao tác như DROP cột đang được sử dụng hay thay kiểu cột có thể bị từ chối. Cơ chế metadata cũng cho phép nhiều thao tác rename ở bảng nền mà view tiếp tục sử dụng object được bind. Tuy nhiên, việc thêm cột bảng không tự làm view `SELECT *</BT> mở rộng, `CREATE OR REPLACE VIEW</BT> bị giới hạn về tên/thứ tự/kiểu cột hiện có, và `DROP ... CASCADE</BT> có thể xóa cả chuỗi đối tượng phụ thuộc.

Quan trọng hơn, **database không tự chứng minh mọi semantic contract**: dữ liệu có còn một row/customer, có còn đúng đơn vị tiền tệ, timezone, quyền, độ tươi hoặc kỳ vọng NULL hay không vẫn cần owners và tests xác nhận. Các clients bên ngoài cũng không nhất thiết xuất hiện trong `pg_depend</BT>.

Với thay đổi có thể phá tương thích, hãy ưu tiên **view versioning v1/v2** và chiến lược **expand–migrate–contract**: tạo cấu trúc mới, đồng bộ/backfill, chuyển dần consumers, kiểm tra schema + semantics + quyền + performance, rồi mới xóa phần cũ. Nhờ đó, view trở thành lớp giao diện ổn định có thể giúp PostgreSQL tiến hóa schema mà không buộc toàn bộ ứng dụng đổi cùng một thời điểm.
