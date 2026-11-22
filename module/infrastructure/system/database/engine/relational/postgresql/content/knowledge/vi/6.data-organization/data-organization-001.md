# CREATE DATABASE, template database và lựa chọn thuộc tính khởi tạo trong PostgreSQL

Khi thiết kế một hệ thống dùng PostgreSQL, bảng và schema chưa phải là tầng tổ chức dữ liệu đầu tiên. Trước khi tạo bảng, chúng ta thường phải xác định **database nào sẽ chứa dữ liệu, database đó được khởi tạo từ template nào, dùng encoding và collation gì, ai là chủ sở hữu, đặt mặc định ở tablespace nào và có chính sách kết nối ra sao**.

PostgreSQL cung cấp lệnh `CREATE DATABASE` để thực hiện công việc này. Một đặc điểm quan trọng của PostgreSQL là database mới thường được **sao chép từ một template database** thay vì được tạo hoàn toàn từ số không. Hai template mặc định `template0` và `template1` quyết định nhiều hành vi mà người học dễ bỏ qua.

Ví dụ, hai database đều chứa dữ liệu UTF-8 nhưng có thể sắp xếp chuỗi khác nhau do lựa chọn collation; một database tạo từ `template1` có thể nhận những đối tượng đã được cài thêm vào template; một database có tên và schema đúng nhưng có sai quyền kết nối vẫn khiến ứng dụng không truy cập được.

Bài học này hướng dẫn cách tạo database PostgreSQL **có chủ đích, có thể kiểm tra và phù hợp với môi trường triển khai**, từ cú pháp nền tảng đến template, thuộc tính khởi tạo, tình huống thực hành, lỗi thường gặp và các quyết định khó sửa sau khi dữ liệu đã được nạp.

## 1. Phân biệt PostgreSQL cluster, database, schema và bảng

Để hiểu `CREATE DATABASE`, cần biết database nằm ở vị trí nào trong kiến trúc PostgreSQL.

~~~text
PostgreSQL cluster / instance
|
+-- Các đối tượng dùng chung ở cấp cluster
|     +-- Roles
|     +-- Tablespaces
|     +-- Thông tin về databases
|
+-- Database: postgres
|     +-- Schema: public
|
+-- Database: template0
|     +-- Các đối tượng nền của template
|
+-- Database: template1
|     +-- Các đối tượng nền của template mặc định
|
+-- Database: shop_dev
      |
      +-- Schema: public
      |     +-- Table: customer
      |     +-- Table: product
      |
      +-- Schema: sales
            +-- Table: orders
            +-- Table: order_item
~~~

Những điểm chính:

- **Cluster** theo thuật ngữ PostgreSQL truyền thống là tập các database được quản lý bởi một hệ thống PostgreSQL có data directory, không nhất thiết là cụm nhiều máy.
- **Database** là một không gian làm việc có metadata, schema và đối tượng riêng.
- **Schema** là namespace *bên trong một database*, giúp nhóm bảng, view, function và các đối tượng liên quan.
- **Table** lưu hàng dữ liệu nghiệp vụ trong một schema của database.
- **Role** và **tablespace** là những đối tượng cấp cluster, không được tạo riêng trong mỗi database.

Một kết nối PostgreSQL thông thường kết nối tới **một database cụ thể**. Để thao tác bảng ở database khác, không thể đơn giản viết cú pháp ba phần như `other_database.public.table` trong SQL thông thường của PostgreSQL; thường cần kết nối khác hoặc cơ chế như foreign data wrapper/dblink nếu phù hợp.

### 1.1. Database khác schema ở điểm nào?

| Tiêu chí | Database | Schema |
|---|---|---|
| Cách tạo | `CREATE DATABASE` | `CREATE SCHEMA` |
| Phạm vi | Một không gian database trong cluster | Namespace bên trong database |
| Kết nối | Client chọn database khi kết nối | Client chọn/định danh schema trong database |
| Encoding và locale mặc định | Quyết định quan trọng khi tạo database | Thường sử dụng cấu hình/kiểu collation của database hoặc đối tượng |
| Vai trò quản lý | Chủ sở hữu database | Chủ sở hữu schema và quyền đối tượng |
| Truy vấn giữa các đối tượng | Thông thường không JOIN trực tiếp xuyên database | Có thể JOIN các bảng ở nhiều schema cùng database |
| Template | Database mới được sao từ template | Schema không sử dụng cơ chế database template |
| Backup logic | Có thể dump một database | Có thể dump/chọn một hoặc nhiều schema trong database |

Khi ứng dụng cần các bảng giao dịch liên hệ chặt chẽ, nhiều schema trong **cùng database** thường thuận lợi cho join và transaction. Khi cần tách biệt database-level settings hoặc vòng đời vận hành, nhiều database có thể phù hợp. Quyết định này phụ thuộc kiến trúc, không chỉ cách đặt tên.

## 2. CREATE DATABASE thực hiện điều gì?

Lệnh `CREATE DATABASE` tạo một database mới trong PostgreSQL cluster, với tên và các thuộc tính được chọn.

Cú pháp tối giản:

~~~sql
CREATE DATABASE shop_dev;
~~~

Lệnh này yêu cầu server tạo một database tên `shop_dev`, sử dụng template mặc định và những thuộc tính được kế thừa hoặc chọn theo quy tắc hiện hành.

Phần lớn hệ thống PostgreSQL thông thường sử dụng **`template1` làm template mặc định**. Do đó, các đối tượng và thiết lập liên quan đã có trong `template1` có thể ảnh hưởng database mới.

Ví dụ có chỉ định thêm thuộc tính:

~~~sql
CREATE DATABASE shop_dev
WITH
    OWNER = shop_owner
    TEMPLATE = template0
    ENCODING = 'UTF8'
    LC_COLLATE = 'C'
    LC_CTYPE = 'C'
    CONNECTION LIMIT = 50;
~~~

Ví dụ giả định:

- Role `shop_owner` **đã tồn tại** và người chạy có đủ quyền đặt owner.
- PostgreSQL nguồn hỗ trợ các tùy chọn được sử dụng.
- `template0` có cấu hình phù hợp cho các lựa chọn encoding/locale này.
- Database `shop_dev` chưa tồn tại.
- Lệnh được chạy **ngoài transaction block**.

Các mục tiếp theo sẽ giải thích vì sao từng lựa chọn quan trọng.

### 2.1. Không có lệnh CREATE DATABASE IF NOT EXISTS tiêu chuẩn trong PostgreSQL

Không nên áp dụng thói quen từ những hệ quản trị khác rồi viết:

~~~sql
-- Sai cú pháp trong PostgreSQL thông thường:
-- CREATE DATABASE IF NOT EXISTS shop_dev;
~~~

Nếu database đã tồn tại, `CREATE DATABASE shop_dev` sẽ báo lỗi trùng tên. Ta sẽ xem cách kiểm tra trong script bằng `psql` ở phần sau, đồng thời phân biệt phép kiểm tra trước với cơ chế tránh race condition.

## 3. Quyền cần thiết để tạo database

Người thực hiện `CREATE DATABASE` thường phải:

- Là **superuser**, hoặc
- Có thuộc tính role **`CREATEDB`**.

Ví dụ kiểm tra thuộc tính role hiện tại:

~~~sql
SELECT
    current_user AS active_role,
    r.rolcreatedb,
    r.rolsuper
FROM pg_catalog.pg_roles AS r
WHERE r.rolname = current_user;
~~~

Trên một môi trường self-managed và với tài khoản có quyền phù hợp, quản trị viên có thể tạo role chuyên tạo database:

~~~sql
-- Ví dụ dành cho quản trị viên trên môi trường thử.
CREATE ROLE database_creator LOGIN CREATEDB;
~~~

Lệnh này không cấu hình password hay cơ chế đăng nhập cụ thể. Trong hệ thống thật cần thiết lập xác thực, TLS, mạng và cấp quyền theo chính sách. Không lưu mật khẩu thật trong script công khai.

**`CREATEDB` không đồng nghĩa `SUPERUSER`.** Người có quyền tạo database không tự có quyền thay đổi mọi đối tượng và thông tin nhạy cảm của toàn cluster.

### 3.1. Chỉ định OWNER

Nếu không chỉ định `OWNER`, chủ sở hữu database mới thường là role thực thi lệnh.

Có thể chọn chủ sở hữu khác:

~~~sql
CREATE DATABASE shop_test
WITH OWNER = shop_owner;
~~~

Role `shop_owner` phải tồn tại. Người tạo database phải có quyền thích hợp để đặt role đó làm owner; trên môi trường quản lý, chính sách role membership và quyền có thể bị giới hạn.

Chủ sở hữu database có thể thực hiện những thao tác quản trị thuộc phạm vi quyền PostgreSQL cấp cho owner. Nhưng **owner database không tự sở hữu mọi bảng được sao từ một template tùy chỉnh**, và owner database cũng không mặc nhiên là superuser toàn cluster.

### 3.2. Managed PostgreSQL có thể giới hạn thao tác

Trên các dịch vụ PostgreSQL được quản lý, tài khoản quản trị được cung cấp có thể **không phải superuser thực sự**. Việc tạo database, chọn tablespace, locale provider, số kết nối và dùng template tùy chỉnh phải tuân theo tính năng và quyền do nhà cung cấp cho phép.

Không cố sửa system catalog hoặc thay file server để vượt giới hạn. Nếu không tạo được database bằng SQL, cần kiểm tra quyền, chính sách dịch vụ và cách provision được hỗ trợ.

## 4. Vì sao CREATE DATABASE cần kết nối vào database khác?

PostgreSQL client phải kết nối đến một database sẵn có để gửi lệnh SQL.

Ví dụ để tạo `shop_dev`, có thể kết nối `postgres` — một database tiện dụng thường tồn tại cho công việc quản trị:

~~~bash
psql \
  -h 127.0.0.1 \
  -p 5432 \
  -U admin_user \
  -d postgres
~~~

Sau khi kết nối:

~~~sql
SELECT current_database(), current_user;

CREATE DATABASE shop_dev;
~~~

Sau khi tạo, phiên làm việc hiện tại vẫn ở database `postgres`. Muốn kiểm tra các schema hoặc tạo bảng trong database mới, phải mở kết nối tới `shop_dev`.

Trong `psql`:

~~~text
\connect shop_dev
~~~

Hoặc mở một phiên mới:

~~~bash
psql -h 127.0.0.1 -p 5432 -U admin_user -d shop_dev
~~~

Không thể dùng `USE shop_dev` theo cú pháp quen thuộc của một số database engine khác. PostgreSQL chọn database ở **thời điểm thiết lập kết nối**, và `psql` cung cấp meta-command `\connect` để kết nối lại.

## 5. CREATE DATABASE không được chạy trong transaction block

Đây là một trong những quy tắc thực hành quan trọng nhất.

Ví dụ **không hợp lệ**:

~~~sql
BEGIN;

CREATE DATABASE shop_dev;

COMMIT;
~~~

PostgreSQL sẽ từ chối thực hiện `CREATE DATABASE` bên trong một transaction block thông thường.

Điều này ảnh hưởng tới:

- Những migration framework mặc định bọc mọi file SQL trong transaction.
- Script chạy bằng `psql --single-transaction`.
- Khối `DO` PL/pgSQL hay function muốn gọi `CREATE DATABASE` như một lệnh SQL động.
- Công cụ tự động hóa cố kết hợp nhiều bước provision thành một transaction duy nhất.

### 5.1. Cách chạy hợp lý bằng psql

Từ terminal, kết nối database quản trị và chạy lệnh độc lập:

~~~bash
psql \
  -X \
  -v ON_ERROR_STOP=1 \
  -h 127.0.0.1 \
  -p 5432 \
  -U admin_user \
  -d postgres \
  -c "CREATE DATABASE shop_dev"
~~~

`-X` tránh đọc cấu hình khởi động riêng của `psql`, còn `ON_ERROR_STOP=1` giúp script điều phối nhận lỗi rõ ràng.

**Không dùng `--single-transaction` cho lệnh `CREATE DATABASE`**. Sau khi database đã được tạo, nhiều DDL bên trong database như `CREATE SCHEMA` và `CREATE TABLE` có thể được tổ chức trong transaction phù hợp.

### 5.2. Phân chia provisioning và migration

Một quy trình triển khai có thể gồm:

~~~text
[1] Provision role / database (ngoài transaction)
                    |
                    v
[2] Kết nối database mới
                    |
                    v
[3] Chạy schema migrations (có transaction khi phù hợp)
                    |
                    v
[4] Nạp seed / reference data
                    |
                    v
[5] Cấp quyền và kiểm tra
~~~

Những công việc này không nên bị gộp thành một câu “chạy SQL một lần” nếu chúng có yêu cầu giao dịch và quyền khác nhau.

## 6. Template database là gì?

Một đặc điểm khác biệt của PostgreSQL là việc tạo database mới thường được thực hiện bằng **sao chép một database đã tồn tại**.

Hình dung:

~~~text
PostgreSQL cluster
      |
      +-- template1
      |      |
      |      +---- CREATE DATABASE shop_dev;
      |                     |
      |                     v
      |                 shop_dev
      |
      +-- template0
             |
             +---- CREATE DATABASE audit_lab
                             TEMPLATE template0;
                           |
                           v
                        audit_lab
~~~

Template chứa các đối tượng và dữ liệu bên trong database nguồn. PostgreSQL sao chép cấu trúc phù hợp để tạo database đích, chứ không diễn giải một file SQL trống theo cách `pg_dump`/`pg_restore` mỗi lần.

Có ba khái niệm:

- **`template1`:** template mặc định cho nhiều lệnh tạo database.
- **`template0`:** template cơ sở được giữ tương đối nguyên bản để phục vụ tạo database có thuộc tính khác, đặc biệt encoding và locale.
- **Template tùy chỉnh:** một database do quản trị viên chuẩn bị, có thể dùng làm nguồn sao chép nếu đáp ứng điều kiện và quyền.

### 6.1. Template không phải schema mẫu

Một template database có thể chứa bảng, view, function, extension, dữ liệu seed và metadata của các đối tượng đó. Tạo database mới từ template có thể sao chép **nhiều đối tượng bên trong database**, không chỉ phần khai báo schema.

Nếu chỉ cần khởi tạo vài bảng cho ứng dụng, dùng migration và seed có version thường dễ quản lý hơn việc thay đổi template mặc định của cluster.

## 7. template1: bản mẫu mặc định

Trong cluster PostgreSQL được khởi tạo theo quy trình thông thường, `template1` là database mặc định được sử dụng khi tạo database mới nếu không chọn `TEMPLATE` khác.

Ví dụ:

~~~sql
CREATE DATABASE shop_dev;
~~~

có ý nghĩa gần với:

~~~sql
CREATE DATABASE shop_dev
WITH TEMPLATE template1;
~~~

Trong trường hợp không cấu hình khác, database đích nhận những đối tượng, cấu trúc và thuộc tính thích hợp từ `template1`.

### 7.1. Nếu sửa template1 thì sao?

Giả sử quản trị viên kết nối vào `template1` rồi tạo một bảng:

~~~sql
-- Ví dụ minh họa; không chạy trên template1 thật chỉ để thử.
-- CREATE TABLE public.platform_note (
--     note_id INTEGER PRIMARY KEY,
--     note_text TEXT NOT NULL
-- );
~~~

Một database tạo sau đó từ `template1` có thể có bảng `platform_note` ngay từ đầu.

Điều này có thể hữu ích trong các môi trường đã thiết kế template riêng, nhưng cũng tạo rủi ro:

- Tất cả database mới đều nhận những đối tượng không cần thiết.
- Quyền và ownership của các đối tượng mẫu có thể không phù hợp.
- Extension hoặc cấu hình thêm vào template làm việc nâng cấp/backup phức tạp hơn.
- Các môi trường khác nhau có `template1` khác nhau, khiến kết quả tạo database không nhất quán.
- Người mới không biết template đã bị sửa nên khó giải thích vì sao một bảng tự xuất hiện.

**Khuyến nghị thực hành:** không chỉnh sửa `template1` trong môi trường dùng chung chỉ để tiện bài tập hoặc thêm vài bảng mẫu. Nếu cần một template tùy chỉnh, hãy tạo database riêng và quản lý nó bằng quy trình có kiểm soát.

## 8. template0: bản mẫu nền ít thay đổi

`template0` được dự định giữ ở trạng thái nền sạch, phù hợp khi muốn tạo database có **encoding hoặc locale khác với template1**, nếu tổ hợp thuộc tính đó được PostgreSQL và hệ điều hành hỗ trợ.

Ví dụ:

~~~sql
CREATE DATABASE customer_search_lab
WITH
    TEMPLATE = template0
    ENCODING = 'UTF8'
    LC_COLLATE = 'C'
    LC_CTYPE = 'C';
~~~

Lý do chọn `template0` không phải vì nó “nhanh hơn” hoặc “tốt hơn” cho mọi ứng dụng. Điểm quan trọng là có thể lựa chọn các thiết lập khởi tạo không tương thích với việc sao chép một template đã chứa dữ liệu/metadata phụ thuộc vào locale cũ.

### 8.1. Vì sao PostgreSQL hạn chế đổi encoding/locale khi clone?

Nếu một template đã có index hoặc dữ liệu được tổ chức theo quy tắc so sánh ký tự, sao chép những cấu trúc đó rồi tuyên bố database đích sử dụng một locale khác có thể dẫn đến kết quả không nhất quán.

Vì vậy PostgreSQL thường ràng buộc lựa chọn `ENCODING`, `LC_COLLATE` và `LC_CTYPE` với template nguồn. `template0` là đường được thiết kế để chọn các giá trị khác khi được hỗ trợ.

**Không tìm cách sửa dữ liệu trong catalog để bỏ qua kiểm tra tương thích của template.**

### 8.2. Có nên kết nối và sửa template0?

Không. `template0` được duy trì như một điểm nền. Trong nhiều cluster, nó được cấu hình để **không cho phép kết nối thông thường**, chính là để hạn chế thay đổi ngoài ý muốn.

Không biến `template0` thành database thực hành hoặc nơi cài extension tùy tiện. Để thí nghiệm, hãy **tạo một database mới từ template0**.

## 9. So sánh template0, template1 và template tùy chỉnh

| Thuộc tính | template0 | template1 | Template tùy chỉnh |
|---|---|---|---|
| Vai trò | Bản mẫu nền | Bản mẫu mặc định | Bản mẫu theo mục đích riêng |
| Sử dụng mặc định khi CREATE DATABASE | Không | Thường có | Chỉ khi chỉ định |
| Có nên sửa trực tiếp | Không | Chỉ khi quản trị có kế hoạch | Có thể quản lý theo quy trình |
| Chọn encoding/locale khác | Là lựa chọn chủ yếu khi cần thay đổi | Thường bị ràng buộc bởi thuộc tính template | Phụ thuộc tương thích của template |
| Có thể chứa dữ liệu/extension tùy chỉnh | Không nên | Có thể, nhưng cần cẩn trọng | Có thể chủ động chuẩn bị |
| Đối tượng được sao chép | Các đối tượng nền | Đối tượng hiện có trong template1 | Đối tượng đã chuẩn bị trong template |
| Rủi ro quản trị | Làm mất nền sạch | Ảnh hưởng mọi database tạo sau | Sai owner, stale data, session mở |

Không cần tạo database ứng dụng từ template tùy chỉnh nếu chỉ muốn có vài bảng cấu hình. Trong các dự án sử dụng Flyway/Liquibase hoặc migration SQL, cách tạo database trống rồi chạy migration thường dễ theo dõi lịch sử hơn.

## 10. Thuộc tính OWNER: xác định người sở hữu database

Ví dụ:

~~~sql
CREATE DATABASE shop_orders
WITH
    OWNER = shop_owner
    TEMPLATE = template0;
~~~

**Owner database** là role có vị trí quản trị nhất định đối với database đó. Tuy nhiên:

- Owner không phải tự động là superuser.
- Owner database và quyền trên từng schema/table là những khái niệm khác nhau.
- Các object được sao chép từ template tùy chỉnh có thể vẫn mang ownership theo trạng thái template.
- Ứng dụng không nên dùng tài khoản owner có quyền rộng để xử lý mọi truy vấn thường ngày.

Một thiết kế role có thể gồm:

~~~text
database_admin  : provision và quản trị
shop_owner      : sở hữu database / schema do nhóm quản lý
shop_migrator   : thực hiện migration có kiểm soát
shop_app        : quyền đọc/ghi cần thiết cho ứng dụng
shop_readonly   : chỉ đọc các bảng được cấp
~~~

Role cụ thể và cách kế thừa quyền phải được thiết kế theo quy tắc `GRANT`/`REVOKE` của PostgreSQL, không chỉ dựa vào tên.

### 10.1. Database owner không bằng schema owner

Sau khi kết nối database mới, có thể kiểm tra:

~~~sql
SELECT
    current_database(),
    current_user;

SELECT
    nspname,
    pg_catalog.pg_get_userbyid(nspowner) AS schema_owner
FROM pg_catalog.pg_namespace
WHERE nspname = 'public';
~~~

Owner của `public` và quyền trên schema này có thể phụ thuộc phiên bản/đường khởi tạo database. **Không giả định mọi PostgreSQL đều có cùng default grant trên schema public**; hãy kiểm tra thực tế và thiết kế quyền rõ ràng.

## 11. ENCODING: bảng mã của database

**Encoding** quy định cách PostgreSQL mã hóa ký tự văn bản trong database. Trong phần lớn ứng dụng hiện đại có dữ liệu đa ngôn ngữ, **UTF-8** là lựa chọn thông dụng.

Ví dụ:

~~~sql
CREATE DATABASE shop_utf8
WITH
    TEMPLATE = template0
    ENCODING = 'UTF8';
~~~

Có thể kiểm tra database đang kết nối:

~~~sql
SHOW server_encoding;
SHOW client_encoding;
~~~

Hai tham số cần phân biệt:

- `server_encoding`: encoding của database phía server.
- `client_encoding`: cách client gửi và nhận dữ liệu văn bản; PostgreSQL có thể chuyển đổi giữa encoding client và server khi được hỗ trợ.

Ví dụ:

~~~sql
SELECT
    current_database() AS database_name,
    current_setting('server_encoding') AS database_encoding,
    current_setting('client_encoding') AS connection_encoding;
~~~

### 11.1. Tại sao không chọn encoding tùy ý?

Encoding cần tương thích với locale và tính năng đang dùng. Nếu một database được khởi tạo bằng encoding không hỗ trợ những ký tự ứng dụng cần lưu, quá trình chèn dữ liệu có thể lỗi hoặc gây mất khả năng biểu diễn ký tự.

Ví dụ dữ liệu tiếng Việt:

~~~text
Đà Nẵng
Nguyễn Ánh
Trường Sa
Cà phê
~~~

`UTF8` phù hợp để biểu diễn những chuỗi này. Nhưng muốn hệ thống **sắp xếp** đúng theo quy tắc ngôn ngữ lại còn cần chọn collation; encoding và collation là hai khái niệm khác nhau.

### 11.2. Encoding có thể đổi sau khi database đã tạo không?

Không thể coi encoding là tham số có thể `ALTER DATABASE` tùy tiện sau khi đã có dữ liệu. Đường chuyển đổi an toàn thông thường là **tạo database đích với encoding mong muốn rồi di chuyển dữ liệu bằng phương pháp được hỗ trợ**, ví dụ dump/restore hoặc migration logic.

Không đổi giá trị encoding trong system catalog để “chuyển UTF-8”. Làm vậy không chuyển đổi byte của dữ liệu đã lưu.

## 12. Locale: quy tắc văn hóa và ngôn ngữ

Locale liên quan đến các quy tắc ngôn ngữ và vùng, trong đó có:

- Sắp xếp chuỗi theo thứ tự nào.
- So sánh chuỗi theo collation nào.
- Phân loại ký tự và một số hành vi xử lý ký tự.
- Mức độ tương thích với môi trường hệ điều hành hoặc thư viện ICU.

Trong PostgreSQL, hai tham số truyền thống thường gặp là:

- **`LC_COLLATE`:** quy tắc sắp xếp và so sánh chuỗi.
- **`LC_CTYPE`:** phân loại ký tự và những hành vi liên quan.

Ví dụ với locale `C`:

~~~sql
CREATE DATABASE shop_c
WITH
    TEMPLATE = template0
    ENCODING = 'UTF8'
    LC_COLLATE = 'C'
    LC_CTYPE = 'C';
~~~

`C` có tính chất so sánh theo thứ tự byte đơn giản, thường phù hợp với những yêu cầu so sánh định danh kỹ thuật, nhưng không được xem là cách sắp xếp tự nhiên theo tiếng Việt hoặc một ngôn ngữ cụ thể.

### 12.1. Encoding không quyết định thứ tự sắp xếp

Hai database đều có `ENCODING = 'UTF8'` vẫn có thể cho thứ tự khác nhau khi chạy:

~~~sql
SELECT ten
FROM danh_muc
ORDER BY ten;
~~~

vì collation có thể khác nhau. Đừng suy từ “đã dùng UTF-8” rằng ứng dụng sẽ tự sắp xếp tên người đúng theo quy tắc tiếng Việt.

### 12.2. Locale có phải giống nhau trên mọi OS?

Không. Với provider `libc`, tên locale được hỗ trợ và quy tắc chi tiết phụ thuộc hệ điều hành cùng thư viện locale. Một locale có tên tồn tại trên máy này có thể không được cài trên máy khác.

Khi viết script tạo database có lựa chọn locale cụ thể, cần ghi rõ môi trường đích và kiểm tra locale đó có thực sự được hỗ trợ. Nếu deployment dùng container hoặc managed service, không nên mặc định có thể cài mọi locale trên OS bên dưới.

## 13. LOCALE_PROVIDER: libc và ICU

Trong những phiên bản PostgreSQL hỗ trợ lựa chọn provider tương ứng, database có thể sử dụng những cơ chế collation khác nhau. Hai provider phổ biến là:

- **`libc`:** dựa trên quy tắc locale của thư viện hệ điều hành.
- **`icu`:** dùng International Components for Unicode (ICU) để xử lý collation theo quy tắc Unicode và locale được chọn.

Tùy phiên bản PostgreSQL, có thể có các provider hoặc tùy chọn bổ sung. **Cần kiểm tra cú pháp của bản server đang dùng**, không dùng một script duy nhất rồi mặc định chạy trên mọi bản PostgreSQL cũ/mới.

### 13.1. Tạo database dùng libc

Ví dụ cho một phiên bản PostgreSQL hỗ trợ `LOCALE_PROVIDER`:

~~~sql
CREATE DATABASE app_libc
WITH
    TEMPLATE = template0
    ENCODING = 'UTF8'
    LOCALE_PROVIDER = libc
    LC_COLLATE = 'C'
    LC_CTYPE = 'C';
~~~

Với provider `libc`, tên locale và quy tắc phụ thuộc vào OS/libc. `C` là một lựa chọn đơn giản và phổ biến, nhưng không phải thứ tự ngôn ngữ học tự nhiên cho mọi ứng dụng.

### 13.2. Tạo database dùng ICU

Ví dụ trên phiên bản PostgreSQL được build và cấu hình hỗ trợ ICU:

~~~sql
CREATE DATABASE app_icu
WITH
    TEMPLATE = template0
    ENCODING = 'UTF8'
    LOCALE_PROVIDER = icu
    ICU_LOCALE = 'vi-VN';
~~~

`ICU_LOCALE` là mã locale được dùng cho provider ICU. Tên locale và mức hỗ trợ phải phù hợp với phiên bản ICU/PostgreSQL hiện tại. Một số phiên bản có thêm tùy chọn điều chỉnh ICU hoặc các thuộc tính liên quan; không nên giả định mọi tùy chọn có mặt trên tất cả server.

**Hai câu SQL trên là ví dụ cho hai database riêng.** Nếu database tên `app_libc` hoặc `app_icu` đã tồn tại, `CREATE DATABASE` sẽ báo lỗi.

### 13.3. ICU có tự làm mọi phép so sánh tiếng Việt “đúng” không?

Không có một định nghĩa “đúng” cho mọi loại dữ liệu.

Ví dụ:

- Tên người có thể cần thứ tự theo ngôn ngữ.
- Mã đơn hàng cần so sánh định danh ổn định, có thể khác quy tắc tìm kiếm tên.
- Một mã duy nhất có thể cần phân biệt chữ hoa/thường hoặc dấu theo quy tắc nghiệp vụ.
- Tìm kiếm gần đúng và tìm kiếm chính xác thường có yêu cầu khác nhau.

Cần kiểm thử với dữ liệu thực tế trước khi lựa chọn collation và thiết kế `UNIQUE` hoặc index liên quan.

### 13.4. Không chỉ nhìn locale mà quên phiên bản thư viện

Quy tắc collation của ICU hoặc libc có thể thay đổi khi thư viện/OS được nâng cấp. Điều này có thể ảnh hưởng index sắp xếp theo chuỗi và hành vi `ORDER BY`/`UNIQUE`.

PostgreSQL có cơ chế metadata để theo dõi một số **collation version**. Nếu phiên bản thư viện thay đổi, quy trình vận hành có thể cần kiểm tra và **REINDEX những index bị ảnh hưởng** trước khi cập nhật metadata phiên bản collation theo hướng dẫn tương ứng.

Lệnh kiểu:

~~~sql
-- Chỉ sử dụng khi có quy trình xử lý thay đổi collation phù hợp.
-- ALTER DATABASE app_icu REFRESH COLLATION VERSION;
~~~

chủ yếu cập nhật metadata phiên bản được ghi nhận; **nó không tự xây dựng lại mọi index cần thiết**. Không coi đây là “sửa xong collation” nếu chưa xem xét ảnh hưởng dữ liệu và index.

## 14. Vì sao lựa chọn collation cần được quyết định sớm?

Giả sử một bảng người dùng có mã định danh:

~~~sql
CREATE TABLE app_user (
    user_id BIGINT PRIMARY KEY,
    login_name TEXT NOT NULL UNIQUE
);
~~~

Hành vi so sánh `login_name` và kiểm tra `UNIQUE` có thể phụ thuộc collation của cột/biểu thức/index. Nếu đổi quy tắc so sánh sau khi hệ thống đã có dữ liệu, các chuỗi từng được xem khác nhau có thể trở nên tương đương hoặc thứ tự sắp xếp có thể đổi.

Với dữ liệu có dấu:

~~~text
Ánh
Anh
Đặng
dang
Đà Nẵng
da nang
~~~

cần xác định:

1. Những chuỗi nào phải được coi là trùng khi đăng ký tài khoản?
2. Thứ tự tên cần theo ngôn ngữ nào?
3. Tìm kiếm có phân biệt chữ hoa/thường không?
4. Index đã tạo theo collation nào?
5. Kết quả có cần nhất quán giữa các môi trường không?

**Database-level locale là một lựa chọn nền tảng**, nhưng PostgreSQL còn cho phép chỉ định collation ở cấp cột hoặc biểu thức tùy nhu cầu. Việc dùng một collation mặc định không ngăn ứng dụng thiết kế quy tắc khác cho những cột đặc biệt.

## 15. TABLESPACE: vị trí lưu trữ mặc định của database

PostgreSQL hỗ trợ **tablespace** để ánh xạ lưu trữ đối tượng database vào vị trí vật lý được quản trị.

Mặc định, nhiều database được tạo trong tablespace `pg_default`. Nếu đã có một tablespace phù hợp và người tạo có quyền, có thể chọn:

~~~sql
CREATE DATABASE analytics_db
WITH
    TEMPLATE = template0
    TABLESPACE = fast_storage;
~~~

Trong đó `fast_storage` là tên tablespace **đã được tạo trước**; đây không phải thư mục tự tạo bên trong lệnh `CREATE DATABASE`.

Kiểm tra:

~~~sql
SELECT
    d.datname,
    ts.spcname AS default_tablespace
FROM pg_catalog.pg_database AS d
JOIN pg_catalog.pg_tablespace AS ts
    ON ts.oid = d.dattablespace
WHERE d.datname = 'analytics_db';
~~~

### 15.1. Tablespace là đối tượng cấp cluster

Không tạo tablespace mới bên trong database `analytics_db` bằng lệnh `CREATE DATABASE`. Quản trị tablespace là công việc riêng, thường yêu cầu quyền cao, đường dẫn phù hợp và quản lý filesystem. Trên managed PostgreSQL, quyền tạo tablespace hoặc chọn filesystem có thể bị hạn chế.

### 15.2. Database tablespace không có nghĩa mọi object luôn nằm ở đó

Một object có thể được tạo với tablespace riêng khi được hỗ trợ. Cấu hình session hoặc thao tác DDL sau này cũng có thể ảnh hưởng vị trí lưu trữ. Vì thế `TABLESPACE` khi tạo database quyết định **mặc định ban đầu**, không phải bảo đảm rằng tất cả bảng/index mãi mãi ở cùng một chỗ.

### 15.3. Có thể đổi tablespace sau khi tạo?

PostgreSQL có `ALTER DATABASE ... SET TABLESPACE` với những điều kiện và hạn chế vận hành, khác với việc cố đổi encoding/collation tại chỗ.

Việc di chuyển database có thể liên quan I/O lớn, yêu cầu quyền và trạng thái kết nối phù hợp. Không thực hiện chỉ vì muốn thử trên production; cần kế hoạch dung lượng, backup và downtime.

## 16. ALLOW_CONNECTIONS: có cho kết nối vào database không?

Thuộc tính `ALLOW_CONNECTIONS` xác định database có chấp nhận **kết nối mới** hay không.

Ví dụ:

~~~sql
CREATE DATABASE maintenance_template
WITH
    TEMPLATE = template0
    ALLOW_CONNECTIONS = false;
~~~

Database này vẫn được tạo nhưng không nhận kết nối thông thường. Tùy mục đích có thể dùng để bảo vệ template hoặc cô lập database, nhưng đừng chọn `false` cho database ứng dụng rồi bất ngờ khi không kết nối được.

### 16.1. Thay đổi sau tạo

Có thể dùng cú pháp kiểu:

~~~sql
ALTER DATABASE maintenance_template
WITH ALLOW_CONNECTIONS = true;
~~~

Quyền thay đổi và trạng thái hệ thống phải phù hợp. Việc mở kết nối vẫn còn phụ thuộc host/network, `pg_hba.conf` hoặc cơ chế quản lý network, role và đặc quyền `CONNECT`.

**ALLOW_CONNECTIONS = true không có nghĩa bất kỳ ai cũng đăng nhập được.** Nó chỉ là một trong nhiều điều kiện cho phép thiết lập kết nối.

## 17. CONNECTION LIMIT: giới hạn số kết nối

Ví dụ:

~~~sql
CREATE DATABASE batch_lab
WITH
    TEMPLATE = template0
    CONNECTION LIMIT = 20;
~~~

Thuộc tính `CONNECTION LIMIT` đặt một giới hạn kết nối ở mức database.

Điểm cần hiểu:

- Giá trị mặc định thường dùng `-1` để biểu thị **không đặt giới hạn riêng ở mức database**.
- Một giá trị dương đặt giới hạn được áp dụng theo cơ chế PostgreSQL.
- Đây không phải thay thế cho `max_connections` ở cấp server.
- Một số loại kết nối/role có quyền đặc biệt có quy tắc ngoại lệ; giới hạn không phải hàng rào tuyệt đối trong mọi tình huống.
- Giới hạn ở mức database không tự phân bổ connection pool cho từng ứng dụng.

Có thể kiểm tra:

~~~sql
SELECT
    datname,
    datconnlimit
FROM pg_catalog.pg_database
WHERE datname = 'batch_lab';
~~~

### 17.1. Vì sao không nên đặt giới hạn quá thấp?

Ứng dụng có thể có nhiều pod/process, mỗi process giữ connection pool riêng. Nếu có 10 instance ứng dụng, mỗi instance giữ tối đa 10 kết nối, tổng nhu cầu có thể lên đến 100 kết nối trước cả các công cụ admin, batch job hoặc metrics.

Đặt `CONNECTION LIMIT = 20` mà không tính tổng số client có thể gây lỗi mở kết nối khi tải tăng.

Ngược lại, cho phép số kết nối quá lớn cũng có thể gây áp lực bộ nhớ và tài nguyên server. Đôi khi nên sử dụng connection pool/proxy phù hợp, tối ưu ứng dụng và chọn giới hạn server có chủ đích.

## 18. IS_TEMPLATE: đánh dấu database làm nguồn template

Có thể tạo một database tùy chỉnh để dùng lại:

~~~sql
CREATE DATABASE training_template
WITH
    TEMPLATE = template0
    IS_TEMPLATE = true;
~~~

Database đánh dấu là template có thể được sao chép bởi những role đủ điều kiện theo quy tắc PostgreSQL. **Đây không phải lựa chọn nên bật cho mọi database nghiệp vụ.**

Nếu `IS_TEMPLATE` là false, quyền sao chép một database không được mở rộng cho mọi role có `CREATEDB`; chủ sở hữu hoặc superuser có cơ chế quyền đặc biệt liên quan.

### 18.1. Vì sao cần quản lý chặt template tùy chỉnh?

Một template chứa dữ liệu hoặc đối tượng sẵn có có thể:

- Phân phối dữ liệu demo hoặc những cấu trúc sai cho nhiều database mới.
- Mang quyền và ownership không phù hợp.
- Phát sinh khác biệt phiên bản extension.
- Có dependency không được mong muốn.
- Bị thay đổi ngầm, khiến database mới không còn tái tạo được.

Đừng tạo template có dữ liệu thật hoặc secret rồi để mọi role được phép clone. Template cũng phải tuân theo chính sách dữ liệu và truy cập.

## 19. STRATEGY: cách PostgreSQL sao chép template

Ở các phiên bản PostgreSQL có hỗ trợ tùy chọn `STRATEGY` cho `CREATE DATABASE`, hai chiến lược thường được nhắc là:

- **`WAL_LOG`:** ghi WAL cho việc sao chép các block dữ liệu theo cơ chế tương ứng.
- **`FILE_COPY`:** sao chép tệp theo chiến lược có yêu cầu checkpoint riêng để bảo đảm phục hồi.

Ví dụ trên phiên bản hỗ trợ:

~~~sql
CREATE DATABASE reporting_test
WITH
    TEMPLATE = template0
    STRATEGY = WAL_LOG;
~~~

Hoặc:

~~~sql
CREATE DATABASE reporting_copy
WITH
    TEMPLATE = template0
    STRATEGY = FILE_COPY;
~~~

Lưu ý:

- `WAL_LOG` thường là lựa chọn mặc định trong những phiên bản cung cấp tùy chọn này, và có thể phù hợp với database/template không quá lớn.
- `FILE_COPY` có thể giảm lượng WAL phải ghi cho bản sao lớn trong một số điều kiện, nhưng yêu cầu checkpoint bổ sung và tạo ảnh hưởng I/O/độ trễ vận hành riêng.
- Hiệu quả thực tế phụ thuộc kích thước template, tốc độ storage, cấu hình checkpoint và workload.
- Không phải mọi phiên bản PostgreSQL cũ đều có cùng cú pháp/tùy chọn.

**Không nên chọn FILE_COPY chỉ vì nghe “copy file nhanh hơn”**. Hãy đo thời gian, lượng WAL và tác động lên cluster trong môi trường tương đương khi việc tạo database là một hoạt động thường xuyên và có kích thước lớn.

## 20. Bảng tổng hợp các thuộc tính CREATE DATABASE

| Thuộc tính | Mục đích | Cần quyết định lúc nào? |
|---|---|---|
| `OWNER` | Chủ sở hữu database | Khi provision role và mô hình bảo mật |
| `TEMPLATE` | Database nguồn được sao chép | Trước khi khởi tạo cấu trúc/dữ liệu |
| `ENCODING` | Encoding ký tự của database | **Trước khi tạo**, khó đổi trực tiếp sau đó |
| `LC_COLLATE` | Quy tắc sắp xếp/so sánh nền | **Trước khi tạo**, đổi sau cần di chuyển/thiết kế lại |
| `LC_CTYPE` | Phân loại ký tự nền | **Trước khi tạo**, không phải GUC tùy chỉnh tùy ý |
| `LOCALE_PROVIDER` | Cơ chế locale/collation | Cần chọn đúng provider ngay từ đầu |
| `ICU_LOCALE` | Locale khi dùng ICU | Trước khi tạo; yêu cầu build hỗ trợ |
| `TABLESPACE` | Tablespace mặc định | Khi chọn nơi lưu; đổi sau có chi phí/giới hạn |
| `ALLOW_CONNECTIONS` | Chấp nhận kết nối mới | Có thể điều chỉnh khi vận hành |
| `CONNECTION LIMIT` | Giới hạn kết nối của database | Có thể điều chỉnh theo nhu cầu |
| `IS_TEMPLATE` | Có cho phép dùng database làm template theo quy tắc | Chỉ bật khi thật sự tạo template |
| `STRATEGY` | Chiến lược sao chép template | Chủ yếu quan trọng với thao tác clone lớn/tần suất cao |

Những tùy chọn khác có thể xuất hiện tùy phiên bản, như quản lý metadata collation hoặc quy tắc ICU nâng cao. **Không đưa tham số của một phiên bản bất kỳ vào script dùng chung khi chưa xác nhận tài liệu server đích.**

## 21. Bài thực hành 1: tạo database UTF-8 với locale C

Giả sử đã có PostgreSQL phù hợp, role hiện tại có `CREATEDB` và muốn tạo một database lab để học SQL. Từ database `postgres`:

~~~sql
CREATE DATABASE shop_lab
WITH
    TEMPLATE = template0
    ENCODING = 'UTF8'
    LC_COLLATE = 'C'
    LC_CTYPE = 'C'
    CONNECTION LIMIT = 30;
~~~

**Đây là thao tác tạo database mới**, không xóa database hiện hữu. Nếu `shop_lab` đã tồn tại, lệnh báo lỗi; không tự xóa database để chạy lại khi có dữ liệu cần giữ.

Sau khi tạo, chuyển kết nối trong `psql`:

~~~text
\connect shop_lab
~~~

Kiểm tra:

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS role_name,
    current_setting('server_encoding') AS encoding,
    current_setting('lc_collate') AS lc_collate,
    current_setting('lc_ctype') AS lc_ctype;
~~~

Sau đó thử tạo bảng:

~~~sql
CREATE TABLE public.demo_product (
    product_id INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL UNIQUE,
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0)
);

INSERT INTO public.demo_product
    (product_id, product_name, price)
VALUES
    (1, 'Sách PostgreSQL', 185000.00),
    (2, 'Bàn phím', 420000.00),
    (3, 'Chuột', 175000.00);

SELECT product_id, product_name, price
FROM public.demo_product
ORDER BY product_id;
~~~

Dữ liệu này thuộc **database `shop_lab`**, không nằm trong `postgres` chỉ vì phiên ban đầu đã kết nối vào database `postgres`.

### 21.1. Vì sao không tạo bảng trước khi chuyển kết nối?

Lệnh:

~~~sql
CREATE TABLE public.demo_product (...);
~~~

được xử lý trong database hiện tại của connection. Nếu vẫn đang kết nối `postgres`, bảng sẽ được tạo ở `postgres.public` chứ không tự đi vào `shop_lab`.

Trong script điều phối, luôn biết rõ **`-d` đang chỉ database nào**.

## 22. Bài thực hành 2: kiểm tra metadata trong pg_database

`pg_database` là system catalog ở phạm vi cluster, lưu thông tin các database.

Có thể xem:

~~~sql
SELECT
    oid,
    datname,
    pg_catalog.pg_encoding_to_char(encoding) AS encoding_name,
    datcollate,
    datctype,
    datistemplate,
    datallowconn,
    datconnlimit,
    pg_catalog.pg_get_userbyid(datdba) AS database_owner
FROM pg_catalog.pg_database
WHERE datname IN ('postgres', 'template0', 'template1', 'shop_lab')
ORDER BY datname;
~~~

Những cột đáng chú ý:

| Cột | Ý nghĩa |
|---|---|
| `oid` | OID nội bộ của database |
| `datname` | Tên database |
| `datdba` | OID role sở hữu |
| `encoding` | Mã encoding |
| `datcollate` | Giá trị locale/collation truyền thống |
| `datctype` | Giá trị LC_CTYPE |
| `datistemplate` | Database được đánh dấu làm template hay không |
| `datallowconn` | Có chấp nhận kết nối mới không |
| `datconnlimit` | Giới hạn kết nối ở mức database |
| `dattablespace` | OID tablespace mặc định |

Một số trường locale/provider hoặc collation-version bổ sung có thể khác giữa các phiên bản PostgreSQL; câu truy vấn trên sử dụng một tập trường nền tảng thường gặp.

### 22.1. Xem tablespace mặc định

~~~sql
SELECT
    d.datname,
    t.spcname AS tablespace_name
FROM pg_catalog.pg_database AS d
JOIN pg_catalog.pg_tablespace AS t
    ON t.oid = d.dattablespace
WHERE d.datname = 'shop_lab';
~~~

Đây là ví dụ liên kết system catalog bằng OID, không phải nối tên tablespace được hardcode.

### 22.2. Xem database size

~~~sql
SELECT
    datname,
    pg_catalog.pg_size_pretty(
        pg_catalog.pg_database_size(oid)
    ) AS database_size
FROM pg_catalog.pg_database
WHERE datname = 'shop_lab';
~~~

Giá trị dung lượng có thể khác giữa các môi trường do phiên bản PostgreSQL, metadata, đối tượng, VACUUM và các yếu tố lưu trữ. Database mới không nhất thiết có kích thước bằng 0 byte.

## 23. Bài thực hành 3: tạo một template tùy chỉnh

Giả sử nhóm đào tạo muốn tạo nhiều database có cùng bảng danh mục.

### 23.1. Tạo database template

Kết nối vào `postgres`, rồi tạo:

~~~sql
CREATE DATABASE training_seed
WITH
    TEMPLATE = template0
    ENCODING = 'UTF8'
    LC_COLLATE = 'C'
    LC_CTYPE = 'C';
~~~

### 23.2. Chuẩn bị đối tượng bên trong template

Chuyển kết nối tới `training_seed`:

~~~text
\connect training_seed
~~~

Tạo schema và dữ liệu:

~~~sql
CREATE SCHEMA training;

CREATE TABLE training.status_code (
    status_code TEXT PRIMARY KEY,
    description TEXT NOT NULL
);

INSERT INTO training.status_code
    (status_code, description)
VALUES
    ('NEW', 'Mới tạo'),
    ('DONE', 'Hoàn thành'),
    ('CANCELLED', 'Đã hủy');
~~~

Kiểm tra:

~~~sql
SELECT status_code, description
FROM training.status_code
ORDER BY status_code;
~~~

### 23.3. Ngắt kết nối khỏi template rồi clone

Trở lại database quản trị:

~~~text
\connect postgres
~~~

Đảm bảo **không còn session khác đang kết nối tới `training_seed`** trong lúc clone. Sau đó:

~~~sql
CREATE DATABASE training_student_01
WITH TEMPLATE = training_seed;
~~~

Kiểm tra database mới:

~~~text
\connect training_student_01
~~~

~~~sql
SELECT status_code, description
FROM training.status_code
ORDER BY status_code;
~~~

Kết quả sẽ có ba mã trạng thái như template nguồn.

### 23.4. Có cần IS_TEMPLATE = true không?

Nếu người thực hiện là chủ sở hữu hoặc có quyền được phép clone database đó, có thể không cần đánh dấu `training_seed` thành template công khai. Thuộc tính `IS_TEMPLATE = true` ảnh hưởng phạm vi role được phép dùng nó làm nguồn template theo quy tắc PostgreSQL.

Chỉ bật khi thiết kế chủ động muốn chia sẻ khả năng clone cho các role có `CREATEDB` phù hợp. Trên môi trường dùng chung, không mở rộng quyền clone database chứa dữ liệu chỉ để thuận tiện.

### 23.5. Clone không giống migration versioned

Nếu sửa bảng trong `training_seed` sau khi đã tạo `training_student_01`, database học viên **không tự nhận sửa đổi đó**. Mỗi database là bản sao độc lập ở thời điểm tạo.

~~~text
training_seed -- clone tại t1 --> training_student_01
      |
      +-- thay đổi tại t2
                                  training_student_01
                                  không tự thay đổi theo
~~~

Đây là điểm khác giữa **template cloning** và **migration áp dụng cho nhiều database đang tồn tại**.

## 24. Template có nhiều kết nối đang hoạt động thì sao?

`CREATE DATABASE ... TEMPLATE = source_db` có thể bị từ chối khi database nguồn đang có session khác kết nối. PostgreSQL cần bảo đảm trạng thái thích hợp để sao chép.

Ví dụ xem session của template:

~~~sql
SELECT
    datname,
    COUNT(*) AS connection_count
FROM pg_catalog.pg_stat_activity
WHERE datname = 'training_seed'
GROUP BY datname;
~~~

Một thao tác kiểm tra an toàn:

1. Xác nhận template không phải database có người dùng đang làm việc.
2. Thông báo hoặc điều phối ngừng các session ứng dụng.
3. Đảm bảo lệnh clone được chạy từ **database khác**.
4. Chỉ clone khi nguồn đã ổn định.

Không tự động gọi `pg_terminate_backend` trên production chỉ để lệnh clone chạy được. Kết thúc session có thể làm gián đoạn transaction và tác vụ khác.

### 24.1. Tại sao không nên dùng database production làm template?

Có thể gây ra nhiều rủi ro:

- Production luôn có nhiều kết nối, khiến việc clone không khả thi hoặc gián đoạn.
- Dữ liệu thật có thể bị sao sang môi trường kém bảo mật.
- Database lớn đòi hỏi nhiều I/O và dung lượng để clone.
- Các object chứa secret hoặc dữ liệu nhạy cảm có thể được sao chép.
- Ownership, extension và configuration trong bản clone có thể không thích hợp.

Để dựng staging, ưu tiên một quy trình backup/restore hoặc data masking được thiết kế cho mục đích đó, thay vì clone trực tiếp database production tùy tiện.

## 25. Tạo database bằng createdb

PostgreSQL cung cấp tiện ích dòng lệnh `createdb`, về bản chất là client gửi yêu cầu tạo database tới server.

Ví dụ:

~~~bash
createdb \
  -h 127.0.0.1 \
  -p 5432 \
  -U admin_user \
  -O shop_owner \
  -T template0 \
  -E UTF8 \
  -l C \
  shop_cli
~~~

Giải thích:

- `-h` và `-p` chọn host/port.
- `-U` chọn role kết nối.
- `-O` chọn owner, nếu có quyền.
- `-T` chọn template.
- `-E` chọn encoding.
- `-l` chọn locale theo cách tiện ích hỗ trợ.
- `shop_cli` là tên database mới.

Cú pháp và tập option của `createdb` phụ thuộc phiên bản client, nên cần kiểm tra:

~~~bash
createdb --help
~~~

Khi cần chọn provider ICU hoặc tham số mới, xem `CREATE DATABASE` và khả năng của client/version cụ thể. Không giả định một bản `createdb` quá cũ hỗ trợ mọi option của server mới.

### 25.1. Lợi ích của createdb trong script

`createdb` có thể phù hợp với provisioning từ shell hoặc automation. Nhưng nó không thay quyền trên server, không tự tạo role owner và không tự xử lý việc database đã tồn tại theo yêu cầu idempotent nếu script không thiết kế thêm.

Ở CI, cần kiểm tra **exit code** để ngăn bước migration chạy trên database chưa được tạo.

## 26. Tạo database có điều kiện trong script psql

PostgreSQL không cung cấp cú pháp `CREATE DATABASE IF NOT EXISTS` thông dụng. Trong `psql` có meta-command `\gexec` để thực thi SQL do một truy vấn tạo ra.

Ví dụ trên **database quản trị**, chỉ dành cho quy trình provisioning được kiểm soát:

~~~sql
SELECT format(
    'CREATE DATABASE %I WITH TEMPLATE template0 ENCODING %L',
    'ci_lab_01',
    'UTF8'
)
WHERE NOT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_database
    WHERE datname = 'ci_lab_01'
)
\gexec
~~~

Giải thích:

- `WHERE NOT EXISTS` kiểm tra database đã có chưa.
- `format('%I', ...)` quote identifier như tên database theo cách phù hợp.
- `format('%L', ...)` quote literal như chuỗi encoding.
- `\gexec` là **meta-command của psql**, thực thi câu SQL được truy vấn trước tạo ra.
- Việc thực thi `CREATE DATABASE` diễn ra ngoài transaction block thông thường; không dùng `psql --single-transaction`.

**Giới hạn quan trọng:** đây là cách kiểm tra rồi thực thi, **không phải phép tạo-if-not-exists nguyên tử**. Nếu hai tiến trình cùng kiểm tra và cùng tạo database, một tiến trình vẫn có thể gặp lỗi trùng tên. Automation phải xử lý lỗi như `duplicate_database` khi chạy cạnh tranh, hoặc phối hợp concurrency ở tầng điều phối.

Không đưa `\gexec` vào JDBC như một câu SQL thông thường: server không hiểu meta-command của `psql`.

## 27. Quyền CONNECT và TEMPORARY sau CREATE DATABASE

Database vừa tạo không có nghĩa mọi role đều có quyền thao tác bảng, nhưng cần đặc biệt chú ý **quyền mặc định ở mức database**.

Trong PostgreSQL, quyền `CONNECT` và `TEMPORARY`/`TEMP` đối với database thường được cấp cho `PUBLIC` theo mặc định, trừ khi đã có chính sách khác. `PUBLIC` là nhóm quyền bao gồm mọi role, không phải một người dùng riêng.

Điều này **không bảo đảm ai cũng kết nối được** vì còn authentication, host/network và những điều kiện khác. Nhưng nếu muốn mô hình **chỉ role được chỉ định mới kết nối**, cần quản lý grant/revoke rõ ràng.

Ví dụ trên môi trường đã có role `shop_app`:

~~~sql
REVOKE CONNECT ON DATABASE shop_lab FROM PUBLIC;

GRANT CONNECT ON DATABASE shop_lab TO shop_app;
~~~

Có thể xem quyền:

~~~sql
SELECT
    pg_catalog.has_database_privilege(
        'shop_app',
        'shop_lab',
        'CONNECT'
    ) AS app_can_connect;
~~~

### 27.1. CONNECT không bằng quyền đọc bảng

Ngay cả khi role `shop_app` được `CONNECT`, nó còn cần:

- `USAGE` trên schema nếu muốn truy cập object trong đó.
- `SELECT`, `INSERT`, `UPDATE`, `DELETE` trên các bảng phù hợp.
- Quyền sequence hoặc function khi ứng dụng sử dụng.
- Các quyền khác theo mô hình dữ liệu.

Ví dụ trong database `shop_lab`:

~~~sql
-- Chỉ khi schema và role đã tồn tại.
GRANT USAGE ON SCHEMA public TO shop_app;
GRANT SELECT ON TABLE public.demo_product TO shop_app;
~~~

Không cấp `ALL PRIVILEGES` trên mọi đối tượng cho ứng dụng chỉ vì muốn kết nối thử nhanh.

### 27.2. REVOKE không phải công cụ ngắt phiên

Thu hồi `CONNECT` ảnh hưởng khả năng thiết lập kết nối mới theo quy tắc quyền, không nên coi là cách chắc chắn để chấm dứt ngay mọi session đang tồn tại. Muốn ngắt ứng dụng trong maintenance cần quy trình điều phối riêng.

## 28. Tùy chỉnh mặc định ở mức database sau khi tạo

Ngoài thuộc tính khởi tạo, PostgreSQL có thể lưu một số **cấu hình session mặc định theo database** bằng `ALTER DATABASE ... SET`.

Ví dụ:

~~~sql
ALTER DATABASE shop_lab
SET statement_timeout = '15s';

ALTER DATABASE shop_lab
SET idle_in_transaction_session_timeout = '60s';
~~~

Những thiết lập này được áp dụng theo cơ chế cấu hình khi session kết nối, có thể chịu ảnh hưởng bởi cấu hình role hoặc `SET` của session.

Không nhầm các thiết lập này với **encoding/collation nền của database**:

- `statement_timeout` là một parameter quản lý hành vi truy vấn.
- `idle_in_transaction_session_timeout` giới hạn thời gian ở trạng thái idle trong transaction.
- `ENCODING`, `LC_COLLATE` và `LC_CTYPE` là các lựa chọn nền gắn với cách database được khởi tạo, không thể xem như GUC có thể thay tự do.

### 28.1. Có phải ALTER DATABASE SET đã sửa session đang mở?

Thông thường, một thay đổi mặc định ở mức database cần được đánh giá cho **các kết nối mới**, không nên giả định nó ngay lập tức thay đổi mọi session đang chạy. Khi cần xác minh, tạo connection mới và chạy:

~~~sql
SHOW statement_timeout;
SHOW idle_in_transaction_session_timeout;
~~~

Đối với ứng dụng có connection pool, việc thay đổi default có thể chưa xuất hiện cho đến khi connection được tái tạo hoặc cấu hình session được điều chỉnh có chủ đích.

## 29. Các thuộc tính có thể thay đổi và khó thay đổi sau khi tạo

| Thuộc tính | Có thể điều chỉnh sau tạo? | Ghi chú vận hành |
|---|---|---|
| Tên database | Có đường `ALTER DATABASE ... RENAME TO` | Phải xử lý session, endpoint/connection string và quyền |
| Owner | Có `ALTER DATABASE ... OWNER TO` với điều kiện quyền | Không tự đổi owner của mọi object bên trong |
| Connection limit | Có thể chỉnh qua `ALTER DATABASE` | Cần đánh giá tải và connection pools |
| Allow connections | Có thể chỉnh qua `ALTER DATABASE` | Dễ tự khóa khả năng kết nối nếu chọn sai |
| Is template | Có thể thay đổi theo quyền được hỗ trợ | Có thể mở rộng quyền clone |
| Tablespace | Có cơ chế chuyển với hạn chế | Tốn I/O và yêu cầu kiểm soát kết nối |
| Session defaults | Có `ALTER DATABASE ... SET/RESET` | Thường ảnh hưởng session mới |
| Encoding | Không thể đổi tại chỗ như một biến thông thường | Thường tạo database mới rồi migration dữ liệu |
| Locale/Collation nền | Không thể coi là biến thay tự do | Cần chiến lược di chuyển và index phù hợp |
| Template nguồn đã dùng | Không có “liên kết sống” để thay | Database đã tạo là bản sao độc lập |
| Strategy sao chép ban đầu | Chỉ áp dụng lúc CREATE | Không có ý nghĩa đổi cho database đang tồn tại |

**Hãy chốt những yếu tố khó đổi — encoding, locale provider và collation — trước khi nạp dữ liệu nghiệp vụ lớn.**

## 30. Muốn đổi locale/encoding sau khi đã có dữ liệu phải làm sao?

Một phương án phổ biến là **tạo database đích mới với thuộc tính mong muốn, rồi di chuyển dữ liệu logic** bằng công cụ và quy trình phù hợp.

Ví dụ khung quy trình:

~~~text
Database nguồn: shop_old
      |
      | Backup có thể restore + xác định điểm dữ liệu
      v
Logical dump / migration được hỗ trợ
      |
      v
CREATE DATABASE shop_new
  TEMPLATE template0
  ENCODING UTF8
  locale/provider mới
      |
      v
Restore schema + dữ liệu
      |
      v
Xây lại index / kiểm tra UNIQUE / foreign key
      |
      v
So sánh dữ liệu và thử ứng dụng
      |
      v
Điều phối ghi + cutover theo runbook
~~~

Một ví dụ ở mức ý tưởng:

~~~bash
pg_dump \
  -h old-db.example \
  -U backup_user \
  -d shop_old \
  -F c \
  -f shop_old.dump
~~~

Tạo database đích bằng kết nối quản trị:

~~~sql
CREATE DATABASE shop_new
WITH
    TEMPLATE = template0
    ENCODING = 'UTF8'
    LC_COLLATE = 'C'
    LC_CTYPE = 'C';
~~~

Nạp bằng công cụ phù hợp:

~~~bash
pg_restore \
  -h new-db.example \
  -U restore_user \
  -d shop_new \
  shop_old.dump
~~~

**Chưa phải runbook production hoàn chỉnh.** Cần xử lý role/global objects, extension, ownership, grants, kết nối, đồng bộ những giao dịch phát sinh giữa lúc dump và cutover, thay đổi collation, kiểm tra UNIQUE, index và khả năng rollback.

Khi đổi quy tắc collation, dữ liệu/giá trị từng được coi duy nhất có thể bị đánh giá khác. Không giả định restore mọi index/constraint thành công nếu chưa kiểm tra dữ liệu theo collation đích.

## 31. Database template và backup khác nhau

Có điểm giống là đều có thể giúp tạo ra môi trường có schema/dữ liệu, nhưng mục đích khác nhau:

| Tiêu chí | Database template | Backup/restore |
|---|---|---|
| Mục tiêu | Khởi tạo một database mới từ mẫu có sẵn | Phục hồi dữ liệu tại điểm đã bảo vệ |
| Nguồn | Một database trong cluster | File dump, base backup, WAL, backup hệ thống |
| Ngữ cảnh | Thường cùng PostgreSQL cluster | Có thể chuyển máy/cluster theo cách hỗ trợ |
| Dữ liệu thật | Không nên đưa vào mẫu chung tùy tiện | Có thể chứa dữ liệu thật, cần bảo mật |
| Vòng đời | Dùng cho provision nhanh nhiều database | Dùng cho disaster recovery/PITR, migration |
| Quyền | Phụ thuộc quyền clone template | Phụ thuộc quyền backup/restore |
| Khi nguồn thay đổi | Database đã clone không tự thay | Các bản backup có điểm thời gian cụ thể |

**Template không thay thế backup.** Nếu dữ liệu đơn hàng trên production mất, sao chép `template1` sẽ không thể khôi phục dữ liệu nghiệp vụ đã ghi.

Ngược lại, backup production không nên được dùng như một template học tập mở cho mọi người vì rủi ro lộ dữ liệu và kích thước lớn.

## 32. Chi phí và tài nguyên khi tạo database từ template

`CREATE DATABASE` không phải thao tác “miễn phí” trong mọi trường hợp. Khi template chứa nhiều dữ liệu, việc tạo bản sao có thể tiêu thụ:

- Disk I/O.
- CPU và tài nguyên quản lý file.
- WAL hoặc checkpoint tùy chiến lược.
- Dung lượng lưu trữ cho database mới.
- Thời gian giữ trạng thái thích hợp để clone.
- Năng lực lưu trữ và thời gian cần cho những tác vụ đồng thời.

Một template chứa hàng trăm GiB dữ liệu không nên được nhân thành nhiều database test mà không tính dung lượng và băng thông.

Đối với môi trường đào tạo đơn giản, mẫu có ít bảng/seed hoặc quy trình tạo database trống + migration có thể nhẹ nhàng hơn việc clone một cơ sở dữ liệu lớn.

## 33. Kiểm tra và quản lý database bằng psql

Một số meta-command hữu ích:

~~~text
\l              -- Liệt kê database
\l+             -- Thông tin database chi tiết hơn
\conninfo       -- Thông tin kết nối hiện tại
\connect shop_lab
\dn             -- Liệt kê schema trong database hiện tại
\dt             -- Liệt kê bảng theo quy tắc tìm đối tượng
\q              -- Thoát
~~~

Những chuỗi bắt đầu bằng `\` là **meta-command của psql**, không phải SQL để gửi thẳng từ JDBC.

Với SQL thuần:

~~~sql
SELECT
    current_database(),
    current_user,
    current_setting('server_encoding'),
    current_setting('lc_collate'),
    current_setting('lc_ctype');
~~~

Có thể xem danh sách database từ bất kỳ database nào trong cùng cluster nếu có quyền đọc catalog:

~~~sql
SELECT datname
FROM pg_catalog.pg_database
ORDER BY datname;
~~~

Nhưng để xem dữ liệu bảng ở database `shop_lab`, bạn cần kết nối tới đúng database đó.

## 34. Những lỗi thường gặp khi CREATE DATABASE

### Lỗi 1 — Permission denied to create database

Nguyên nhân thường gặp: role không có `CREATEDB` hoặc không đủ quyền theo cơ chế quản trị của hệ thống.

**Cách xử lý:** kiểm tra `rolcreatedb`, `rolsuper` và policy provider. Nhờ quản trị viên cấp quyền đúng nhu cầu; không cố thay system catalog.

### Lỗi 2 — CREATE DATABASE cannot run inside a transaction block

Lệnh đang nằm trong `BEGIN ... COMMIT`, `psql --single-transaction` hoặc transaction do migration framework tạo.

**Cách xử lý:** chạy riêng `CREATE DATABASE` ngoài transaction. Chạy schema migration sau khi đã mở connection tới database đích.

### Lỗi 3 — Database already exists

Database đã được tạo bởi lần trước hoặc một tiến trình khác.

**Cách xử lý:** kiểm tra `pg_database`, phân biệt đúng môi trường và tính idempotent của provisioning; không `DROP DATABASE` chỉ để bỏ lỗi.

### Lỗi 4 — Không tìm thấy database mới trong phiên hiện tại

`CREATE DATABASE` tạo database nhưng không tự chuyển connection.

**Cách xử lý:** dùng `\connect` trong `psql` hoặc tạo connection mới với `-d` phù hợp.

### Lỗi 5 — Encoding hoặc locale không tương thích template

Thường xảy ra khi muốn tạo database với encoding/locale khác `template1`.

**Cách xử lý:** xem tương thích của server và dùng `TEMPLATE template0` khi phù hợp. Không bỏ qua lỗi hoặc sửa catalog trực tiếp.

### Lỗi 6 — Locale không tồn tại trong môi trường

Một locale được cài trên laptop nhưng không có trên OS của PostgreSQL server.

**Cách xử lý:** xác nhận locale thực sự được server hỗ trợ. Nếu dùng managed service, chọn từ khả năng do provider cung cấp.

### Lỗi 7 — ICU không được hỗ trợ

PostgreSQL bản đích hoặc build có thể không có hỗ trợ ICU/provider cần thiết.

**Cách xử lý:** kiểm tra version, build và hướng dẫn của nhà cung cấp; không dùng cấu hình ICU khi nền tảng không hỗ trợ.

### Lỗi 8 — Nhiều session đang kết nối tới template nguồn

PostgreSQL cần clone từ nguồn ở trạng thái phù hợp; session đang dùng source có thể cản trở.

**Cách xử lý:** chọn thời điểm phù hợp, ngắt kết nối có kiểm soát và chạy clone từ database khác. Không ép dừng mọi session trên production.

### Lỗi 9 — Chọn nhầm template1 đã bị tùy chỉnh

Database mới có extension hoặc bảng “tự xuất hiện”.

**Cách xử lý:** xem template nguồn và metadata; dùng `template0` cùng migration nếu muốn trạng thái nền ổn định.

### Lỗi 10 — Coi OWNER là quyền đọc toàn cluster

Database owner không tự có mọi quyền trên các đối tượng hoặc cluster.

**Cách xử lý:** thiết kế role, schema owner và object grants rõ ràng.

### Lỗi 11 — ALLOW_CONNECTIONS = false cho database ứng dụng

Ứng dụng bị từ chối kết nối mặc dù host và role đúng.

**Cách xử lý:** kiểm tra `datallowconn`; thay thuộc tính bằng quyền phù hợp, từ database quản trị nếu cần.

### Lỗi 12 — CONNECTION LIMIT quá thấp

Connection pool hoặc nhiều instance ứng dụng vượt giới hạn.

**Cách xử lý:** tính tổng nhu cầu, xem `max_connections`, proxy/pool và các kết nối quản trị; chọn giới hạn có chủ đích.

### Lỗi 13 — Quên kiểm tra PUBLIC CONNECT

Database có thể đang cho role không mong muốn thử mở connection theo mặc định.

**Cách xử lý:** quản lý `GRANT`/`REVOKE` cùng network/auth policy; kiểm tra `has_database_privilege`.

### Lỗi 14 — Cho rằng UTF8 đồng nghĩa tìm kiếm tiếng Việt đúng

Encoding và collation là hai quyết định khác nhau.

**Cách xử lý:** thiết kế collation phù hợp với từng nhu cầu tìm kiếm, sắp xếp và unique key.

### Lỗi 15 — Đổi collation provider rồi bỏ qua index

Nếu thư viện collation thay đổi, index liên quan có thể cần được xây lại.

**Cách xử lý:** theo dõi collation version, đánh giá tác động và dùng REINDEX theo quy trình; không chỉ refresh metadata.

### Lỗi 16 — Clone database production làm môi trường thử

Có thể gây tải lớn, rò rỉ dữ liệu và xung đột session.

**Cách xử lý:** dùng backup/restore hoặc data masking được thiết kế, hay template không chứa thông tin nhạy cảm.

### Lỗi 17 — Đặt tên database có chữ hoa rồi quên quote

Identifier không quote được PostgreSQL chuyển về chữ thường theo quy tắc parser. Tên có chữ hoa được quote có thể gây khó vận hành.

**Cách xử lý:** ưu tiên tên dạng `snake_case` chữ thường, không khoảng trắng và không cần quote.

### Lỗi 18 — Dùng DROP DATABASE để “chạy lại cho sạch”

`DROP DATABASE` xóa database và dữ liệu bên trong, nguy hiểm nếu nhầm production hoặc shared environment.

**Cách xử lý:** chỉ dùng quy trình reset đã được phê duyệt trên database tạm, xác nhận endpoint/role/tên, backup khi cần; tránh lệnh xóa tự động không điều kiện.

## 35. Cách chọn thuộc tính cho từng tình huống

### 35.1. Một database nhỏ để luyện SQL

Yêu cầu: độc lập, dễ tạo, có thể xóa, chứa tiếng Việt.

Lựa chọn có thể là:

~~~sql
CREATE DATABASE learning_pg
WITH
    TEMPLATE = template0
    ENCODING = 'UTF8'
    LC_COLLATE = 'C'
    LC_CTYPE = 'C';
~~~

Phù hợp cho một phòng lab muốn thứ tự byte đơn giản; nếu bài tập cần thứ tự tên theo tiếng Việt, cần chọn locale/collation tương ứng và thử nghiệm.

### 35.2. Database ứng dụng có tài khoản riêng

Yêu cầu: tách quyền provision/migration và quyền ứng dụng.

Nên lập kế hoạch:

1. Tạo role owner/migrator/app bằng cơ chế quản trị.
2. Chọn template và encoding/locale phù hợp.
3. Tạo database với `OWNER` có chủ đích.
4. Quản lý `CONNECT`/`TEMP` và schema/object grants.
5. Chạy migration với role phù hợp.
6. Chạy ứng dụng với quyền tối thiểu.
7. Thiết lập backup, monitoring, connection pool.

Không dùng owner hoặc superuser làm tài khoản mặc định cho mọi request của ứng dụng.

### 35.3. Database dùng cho tìm kiếm theo ngôn ngữ

Yêu cầu: sắp xếp tên theo quy tắc ngôn ngữ cụ thể.

Nên:

- Xác định locale provider được hỗ trợ.
- Thử bộ dữ liệu có dấu, chữ hoa/thường và những cặp chuỗi dễ bị coi trùng.
- Kiểm tra ảnh hưởng tới `ORDER BY`, `UNIQUE`, index.
- Cố định phiên bản môi trường và có quy trình xử lý collation version khi nâng hệ thống.
- Cân nhắc collation riêng ở cấp cột khi những loại dữ liệu có quy tắc khác nhau.

### 35.4. Database dùng chung một cấu trúc cho nhiều học viên

Nếu thường xuyên tạo database với cùng bảng danh mục, có thể tạo template tùy chỉnh nhỏ, không có thông tin nhạy cảm, không có kết nối thường trực.

Nếu schema thay đổi liên tục, migration script/seed versioned có thể dễ quản lý hơn template đang bị sửa thủ công.

### 35.5. Database phân tích kích thước lớn

Ngoài encoding và locale, cần đánh giá:

- Dung lượng và tablespace.
- Tốc độ sao chép template, WAL và checkpoint.
- Connection limit.
- Khả năng backup/restore.
- Quyền và môi trường đích.
- Chi phí storage khi tạo nhiều bản sao.

Đừng chọn `STRATEGY` hoặc `TABLESPACE` khi chưa biết tác động vận hành.

## 36. Quy trình provisioning đầy đủ gợi ý

Một quy trình tạo database PostgreSQL đáng tin nên đi qua những bước sau:

**Bước 1 — Xác nhận cluster và database quản trị.** Kiểm tra host, port, phiên bản server, môi trường và role trước khi thao tác.

**Bước 2 — Xác nhận quyền.** Role có `CREATEDB`, quyền owner và tablespace thích hợp không?

**Bước 3 — Chọn tên database.** Dùng tên ổn định, rõ môi trường; tránh trùng production và tránh tên phải quote.

**Bước 4 — Chọn template.** `template0` nếu cần nền sạch/thuộc tính locale khác; `template1` nếu chấp nhận mặc định; custom template chỉ khi có yêu cầu rõ.

**Bước 5 — Chốt encoding và locale.** Đặc biệt quan trọng với Unicode, so sánh chuỗi và dữ liệu có nhiều ngôn ngữ.

**Bước 6 — Chọn owner, tablespace và chính sách kết nối.** Không chờ ứng dụng đi vào vận hành mới phát hiện sai quyền hoặc thiếu tài nguyên.

**Bước 7 — Chạy CREATE DATABASE riêng ngoài transaction.** Dùng `psql -c` hoặc `createdb`, kiểm tra exit code.

**Bước 8 — Xác minh metadata trong pg_database.** Đọc encoding, locale, owner, tablespace, connection limit và flags.

**Bước 9 — Kết nối database mới.** Chạy `SELECT current_database()` trước khi migration.

**Bước 10 — Cấu hình quyền SQL.** Quản lý CONNECT và các grants ở cấp schema/table/sequence theo thiết kế.

**Bước 11 — Chạy schema migration và seed phù hợp.** Giữ lịch sử thay đổi có version thay vì sửa template ngầm.

**Bước 12 — Kiểm thử kết nối, dữ liệu, collation và transaction.** Bao gồm driver ứng dụng, tiếng Việt, index và query quan trọng.

**Bước 13 — Bật và thử khả năng khôi phục.** Database mới cũng cần backup/PITR và giám sát theo mục tiêu hệ thống.

**Bước 14 — Lưu quyết định khởi tạo.** Ghi lại template, encoding, locale provider, version PostgreSQL, owner, grants và scripts, để lần triển khai tiếp theo có thể tái lập.

## 37. Bài tập tự luyện

### Bài 1 — Database và schema

Phân biệt database `shop_dev` với schema `sales` nằm trong `shop_dev`. Khi nào nên dùng nhiều schema trong một database thay vì tạo nhiều database?

**Gợi ý:** các bảng cần JOIN và transaction trong cùng database thường phù hợp đặt ở nhiều schema; database tách ở cấp kết nối và thuộc tính khởi tạo.

### Bài 2 — Template mặc định

Lệnh:

~~~sql
CREATE DATABASE test_a;
~~~

thường sử dụng template nào? Tại sao một bảng đã được tạo trong template mặc định có thể xuất hiện trong database mới?

**Gợi ý:** thường là `template1`. PostgreSQL sao chép nội dung template.

### Bài 3 — Encoding và template0

Bạn cần một database UTF-8 với `LC_COLLATE = 'C'`, khác locale của `template1`. Nên chọn template nào và vì sao?

**Gợi ý:** `template0` được thiết kế để tạo database với thuộc tính khởi tạo khác khi được hỗ trợ.

### Bài 4 — Cách chạy CREATE DATABASE

Vì sao đoạn sau không hợp lệ?

~~~sql
BEGIN;
CREATE DATABASE test_a;
COMMIT;
~~~

**Gợi ý:** `CREATE DATABASE` không chạy trong transaction block thông thường.

### Bài 5 — Database đã tạo nhưng không thấy bảng

Bạn đang kết nối `postgres`, chạy `CREATE DATABASE shop_b;` rồi tạo bảng `public.customer`. Bảng thuộc database nào?

**Gợi ý:** session vẫn kết nối `postgres` trừ khi đổi kết nối bằng `\connect` hoặc client connection mới.

### Bài 6 — Quyền CREATEDB và OWNER

Role có thuộc tính `CREATEDB` có mặc nhiên là superuser không? Tài khoản app có nên dùng role owner để xử lý mọi request không?

**Gợi ý:** không. Nên tách role provision, migration và runtime theo quyền tối thiểu.

### Bài 7 — UTF8 và thứ tự tiếng Việt

Hai database cùng UTF-8 có thể trả thứ tự `ORDER BY ten` khác nhau không?

**Gợi ý:** có, nếu locale/collation khác; encoding không quyết định toàn bộ thứ tự sắp xếp.

### Bài 8 — ICU và libc

Trình bày một khác biệt vận hành giữa provider `icu` và `libc`. Khi nâng OS/ICU, vấn đề nào cần kiểm tra?

**Gợi ý:** quy tắc locale phụ thuộc provider và version; index trên chuỗi có thể cần REINDEX nếu collation thay đổi.

### Bài 9 — CONNECTION LIMIT

Ứng dụng có tám instance, mỗi instance giữ pool 10 connection. Đặt database limit 30 có thể gây vấn đề gì?

**Gợi ý:** nhu cầu tối đa có thể lớn hơn giới hạn; còn phải tính batch job và admin connections.

### Bài 10 — Quyền CONNECT

Một role có quyền `CONNECT` vào database nhưng `SELECT` bị từ chối. Đây có phải lỗi PostgreSQL không?

**Gợi ý:** không. Quyền database, schema và table là các lớp khác nhau.

### Bài 11 — Template tùy chỉnh

Tạo `training_seed` có một bảng và ba dòng, rồi clone `training_student_01`. Sau đó sửa dữ liệu trong `training_seed`, dữ liệu database học viên có tự thay đổi không?

**Gợi ý:** không. Database clone là bản sao độc lập.

### Bài 12 — Nhiều session trên template

Tại sao clone một database nguồn đang có kết nối thường trực có thể thất bại? Cần làm gì trước?

**Gợi ý:** PostgreSQL yêu cầu trạng thái thích hợp để sao chép; dùng nguồn ổn định không có session khác.

### Bài 13 — pg_database

Viết SQL liệt kê tên, encoding, owner, `datallowconn` và `datconnlimit` của các database.

**Gợi ý:** `pg_database`, `pg_encoding_to_char(encoding)` và `pg_get_userbyid(datdba)`.

### Bài 14 — Dùng createdb

Viết lệnh terminal tạo database `test_cli` từ `template0` với UTF-8 và locale C.

**Gợi ý:** dùng các tùy chọn `-T template0`, `-E UTF8`, `-l C` của `createdb` trên phiên bản hỗ trợ.

### Bài 15 — IF NOT EXISTS

Tại sao dùng `SELECT NOT EXISTS ... \gexec` không đủ để bảo đảm hai job CI tạo cùng database không bao giờ va chạm?

**Gợi ý:** có race giữa kiểm tra và tạo; cần điều phối concurrency hoặc xử lý lỗi trùng tên.

### Bài 16 — STRATEGY

Phân biệt ý tưởng `WAL_LOG` và `FILE_COPY` khi tạo database từ template lớn.

**Gợi ý:** hai chiến lược có chi phí WAL, checkpoint và I/O khác nhau; cần dùng trên phiên bản hỗ trợ và đo thực tế.

### Bài 17 — Thay locale sau khi có dữ liệu

Vì sao không nên sửa catalog để đổi database từ collation cũ sang collation khác?

**Gợi ý:** index và quy tắc so sánh dữ liệu có thể không phù hợp; cần migration/restore và kiểm tra dữ liệu.

### Bài 18 — Backup và template

Một nhóm nói “đã có template1 nên không cần backup database sản xuất”. Bạn giải thích vì sao sai?

**Gợi ý:** template không giữ lịch sử giao dịch production; backup và PITR có nhiệm vụ phục hồi dữ liệu thật theo điểm thời gian.

### Bài 19 — TABLESPACE

Khi `CREATE DATABASE analytics WITH TABLESPACE fast_storage`, liệu mọi bảng tạo sau này bị buộc nằm trên fast_storage vĩnh viễn?

**Gợi ý:** không. Đó là mặc định, có thể có tablespace riêng hoặc những thay đổi cấu hình/DDL thích hợp.

### Bài 20 — Kịch bản thiết kế

Một ứng dụng phục vụ khách hàng Việt Nam cần dữ liệu UTF-8, tìm kiếm và sắp xếp tên theo quy tắc phù hợp, quyền runtime tối thiểu, và CI thường xuyên tạo database mới. Hãy đề xuất các bước lựa chọn thuộc tính khởi tạo và thử nghiệm trước production.

**Gợi ý:** chốt provider/collation sau khi thử dữ liệu có dấu, chọn template ổn định, tách owner/migrator/app, tự động provisioning không transaction, xác minh pg_database và thử backup/restore.

## 38. Ghi nhớ

- **`CREATE DATABASE`** tạo một database mới trong PostgreSQL cluster, **không tự chuyển session** sang database đó.
- Database khác schema: mỗi database là không gian kết nối và metadata riêng, còn schema là namespace trong database.
- Người tạo thường cần **`CREATEDB` hoặc superuser**; chỉ định `OWNER` còn phụ thuộc quyền trên role owner.
- **`CREATE DATABASE` không chạy trong transaction block**; tách provisioning database khỏi migration bên trong database.
- Database mới thường được **sao chép từ `template1`**; `template0` là template nền dùng khi cần lựa chọn encoding/locale khác trong phạm vi hỗ trợ.
- **Không sửa template0** và không thay đổi template1 tùy tiện; template tùy chỉnh cần quản lý quyền, dữ liệu và vòng đời.
- **`ENCODING` và `LC_COLLATE`/`LC_CTYPE` khác nhau**: encoding quyết định biểu diễn ký tự, collation ảnh hưởng sắp xếp và so sánh.
- **`LOCALE_PROVIDER`** và `ICU_LOCALE` cần được chọn theo phiên bản PostgreSQL, môi trường và quy tắc nghiệp vụ; những thay đổi collation về sau có thể ảnh hưởng index.
- **`TABLESPACE`** đặt lưu trữ mặc định, **`CONNECTION LIMIT`** giới hạn kết nối ở cấp database, **`ALLOW_CONNECTIONS`** bật/tắt khả năng kết nối mới, còn **`IS_TEMPLATE`** liên quan việc sử dụng database làm template.
- **`STRATEGY`** là lựa chọn cách sao chép template trên phiên bản hỗ trợ, không phải giải pháp mặc định để tăng tốc mọi workload.
- **`pg_database`** cung cấp metadata giúp kiểm tra owner, encoding, locale, flags và tablespace.
- **`CONNECT` không đồng nghĩa quyền trên bảng**; phải thiết kế grants riêng cho schema và đối tượng.
- Những thuộc tính **khó đổi sau tạo** — đặc biệt encoding, locale/collation nền — cần được xác định bằng thử nghiệm trước khi nạp dữ liệu thật.
- **Template không phải backup**; ứng dụng production vẫn cần quy trình backup, recovery và đối soát dữ liệu.

Tạo một database PostgreSQL tốt là chọn **một nền tảng dữ liệu bền vững cho ứng dụng**, không chỉ cấp phát một cái tên. Khi hiểu template database và những thuộc tính khởi tạo, bạn có thể chủ động bảo đảm các môi trường được provision nhất quán, dữ liệu được biểu diễn đúng, quyền được cấp hợp lý và những quyết định khó thay đổi không trở thành sự cố khi hệ thống lớn lên.
