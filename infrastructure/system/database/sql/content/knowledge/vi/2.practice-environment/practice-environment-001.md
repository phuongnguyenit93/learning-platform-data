# Chọn hệ quản trị thực hành và ghi nhận phiên bản

Khi bắt đầu học **Database SQL**, cần xác định rõ mình sẽ thực hành trên hệ quản trị cơ sở dữ liệu (DBMS) nào và phiên bản nào. SQL có nền tảng chung, nhưng cú pháp, kiểu dữ liệu, hàm, cách xử lý giao dịch và tính năng của từng DBMS không hoàn toàn giống nhau. Ghi lại môi trường ngay từ đầu giúp chạy lại ví dụ, trao đổi lỗi và so sánh kết quả một cách đáng tin cậy.

## 1. Phân biệt những thành phần thường bị nhầm lẫn

Một buổi thực hành thường có các thành phần sau:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Hệ quản trị cơ sở dữ liệu (DBMS)** | Thực thi câu lệnh SQL, quản lý dữ liệu, giao dịch, quyền truy cập | PostgreSQL, MySQL, SQL Server, Oracle Database; SQLite là thư viện cơ sở dữ liệu nhúng |
| **Cơ sở dữ liệu (database)** | Tập dữ liệu được quản lý bởi DBMS; cách tổ chức cụ thể tùy hệ | `sql_lab` trong PostgreSQL, một tệp `.db` trong SQLite |
| **Ứng dụng khách (client)** | Gửi câu lệnh, hiển thị kết quả; không quyết định toàn bộ cú pháp được server hỗ trợ | `psql`, `mysql`, `sqlcmd`, DBeaver, DataGrip |
| **Môi trường chạy** | Nơi DBMS được cài hoặc triển khai | Cài trực tiếp trên máy, Docker, máy chủ trong mạng, dịch vụ cloud |
| **Driver** | Thư viện để ứng dụng kết nối tới DBMS | JDBC PostgreSQL Driver, MySQL Connector/J |

Ví dụ: mở DBeaver và kết nối đến PostgreSQL nghĩa là đang dùng **DBeaver làm client, PostgreSQL làm DBMS**. Phiên bản DBeaver khác với phiên bản PostgreSQL đang xử lý câu lệnh. Nếu một máy có nhiều instance PostgreSQL, cổng kết nối còn quyết định bạn đang truy vấn instance nào.

Với SQLite, ứng dụng nạp thư viện SQLite và thao tác trực tiếp với tệp dữ liệu; thông thường **không có server SQLite riêng**. Vì vậy, khi ghi nhận phiên bản SQLite, cần chú ý phiên bản thư viện thực sự thực thi truy vấn.

## 2. Chọn một DBMS chính cho bài thực hành

Không cần cài mọi hệ quản trị ngay từ đầu. Hãy chọn **một DBMS chính** phù hợp với mục tiêu học, sau đó chỉ dùng DBMS khác khi cần so sánh cú pháp hoặc tính năng.

| Lựa chọn | Phù hợp khi | Điều cần biết trước khi chọn |
| --- | --- | --- |
| **PostgreSQL** | Học SQL tổng quát, khóa chính/khóa ngoại, `JOIN`, truy vấn tổng hợp, giao dịch và các tính năng quan hệ | Có server; dễ chạy bằng Docker; một số cú pháp và kiểu dữ liệu đặc thù PostgreSQL |
| **MySQL / MariaDB** | Học trên hệ đang được ứng dụng hoặc công ty sử dụng | MySQL và MariaDB là hai sản phẩm khác nhau; ghi đúng tên, phiên bản và chế độ SQL liên quan |
| **SQLite** | Muốn bắt đầu nhanh, thực hành offline với một tệp dữ liệu, không cần quản trị server | Một số giới hạn về kiểu dữ liệu, thay đổi lược đồ, đồng thời ghi và hành vi khóa ngoại khác DBMS dạng server |
| **Microsoft SQL Server** | Cần thực hành T-SQL, môi trường Microsoft hoặc hệ thống dùng SQL Server | Nhiều cú pháp đặc thù như `TOP`, `IDENTITY`; cần chú ý `compatibility_level` của database |
| **Oracle Database** | Khóa học, dự án hoặc môi trường doanh nghiệp yêu cầu Oracle SQL/PL/SQL | Cú pháp và công cụ riêng; cần kiểm tra bản phân phối, quyền truy cập và điều kiện sử dụng |

**Gợi ý mặc định cho lộ trình SQL tổng quát:** chọn **PostgreSQL** vì có đầy đủ khái niệm cơ sở dữ liệu quan hệ, được sử dụng rộng rãi và có thể tạo môi trường cục bộ nhất quán. Nếu chỉ cần thực hành ngay các lệnh `SELECT`, `WHERE`, `ORDER BY` trên máy không có Docker/server, có thể dùng **SQLite** rồi chuyển sang một DBMS dạng server khi học sâu về quyền truy cập, giao dịch nhiều kết nối hoặc quản trị.

Nếu chương trình học hoặc dự án chỉ định một DBMS, hãy ưu tiên **đúng sản phẩm và nhánh phiên bản được yêu cầu**. Ví dụ, bài tập về T-SQL phải được thực hành trên SQL Server; không nên mặc nhiên dùng PostgreSQL rồi kỳ vọng mọi ví dụ chạy nguyên vẹn.

### Các tiêu chí cần chốt trước khi cài đặt

1. **Mục tiêu:** học SQL nền tảng hay học cú pháp/tính năng của một hệ cụ thể?
2. **Khả năng triển khai:** có quyền cài đặt, Docker, tài nguyên máy, mạng và công cụ kết nối phù hợp không?
3. **Tính lặp lại:** có thể giữ cùng phiên bản khi học nhóm, nộp bài và sửa lỗi không?
4. **Tương thích:** ví dụ có phụ thuộc các hàm, kiểu dữ liệu, collation hoặc chế độ tương thích riêng không?
5. **Điều kiện sử dụng:** bản miễn phí, bản đánh giá, tài khoản cloud và hạn mức tài nguyên có phù hợp không?

Viết một quyết định ngắn, chẳng hạn: *“Dùng PostgreSQL 17.x trên Docker để học SQL quan hệ tổng quát; sử dụng `psql` làm client; mọi ví dụ đặc thù DBMS sẽ được ghi chú.”* Con số `17.x` ở đây chỉ minh họa cho **nhánh phiên bản được chọn**, không khẳng định phiên bản mới nhất.

## 3. Tạo môi trường mẫu với PostgreSQL và Docker

Ví dụ này dùng PostgreSQL làm DBMS chính. Máy cần cài Docker và khởi động Docker Engine trước khi chạy lệnh. Kiểm tra Docker từ terminal:

```bash
docker --version
docker info
```

Tạo một container PostgreSQL, database dành cho bài thực hành và volume lưu dữ liệu:

```bash
docker run -d --name sql-lab-postgres -e POSTGRES_USER=labuser -e POSTGRES_PASSWORD=lab-local-password -e POSTGRES_DB=sql_lab -p 127.0.0.1:5433:5432 -v sql-lab-postgres-data:/var/lib/postgresql/data postgres:17
```

Trong lệnh trên:

- `postgres:17` chọn nhánh major 17 của image chính thức. **Tag theo major chưa cố định bản vá**: lần kéo image sau có thể nhận minor/patch mới. Khi cần tái lập chính xác, hãy cố định tag bản vá cụ thể hoặc image digest và ghi lại giá trị đó.
- `sql_lab` là tên database; `labuser` là tài khoản được tạo cho môi trường học.
- `127.0.0.1:5433:5432` cho phép kết nối từ **chính máy đang chạy Docker** ở cổng `5433`, chuyển vào cổng PostgreSQL `5432` trong container. Chọn `5433` để giảm khả năng đụng một PostgreSQL khác đang dùng cổng `5432`.
- `sql-lab-postgres-data` là Docker volume. Dữ liệu còn trong volume khi dừng hoặc xóa riêng container; nếu tái sử dụng volume cũ, các biến `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` không tự tạo lại tài khoản/database như lần khởi tạo đầu.
- `lab-local-password` chỉ là mật khẩu ví dụ dành cho môi trường cá nhân cục bộ; **không dùng mật khẩu này trong hệ thống thật**.

Kiểm tra container đã khởi động và kết nối bằng client `psql` được cài sẵn trong image:

```bash
docker ps --filter name=sql-lab-postgres
docker exec -it sql-lab-postgres psql -U labuser -d sql_lab
```

Trong giao diện `psql`, thử truy vấn:

```sql
SELECT current_database() AS database_name,
       current_user AS login_role,
       current_setting('server_version') AS server_version,
       current_setting('server_version_num') AS server_version_num;

SELECT version() AS server_build_information;
```

Kết quả phải cho biết đang kết nối database `sql_lab`, vai trò `labuser` và **phiên bản PostgreSQL server thực tế**. `server_version` dễ đọc; `server_version_num` hữu ích cho việc so sánh phiên bản bằng công cụ. `version()` cung cấp thêm thông tin build/nền tảng. Dùng `\q` để thoát `psql`.

Nếu kết nối quá sớm khi container vừa khởi động, kiểm tra log rồi thử lại sau khi PostgreSQL sẵn sàng:

```bash
docker logs sql-lab-postgres
```

Bạn cũng có thể kết nối bằng DBeaver hoặc `psql` cài trên máy chủ với các thông số `127.0.0.1`, cổng `5433`, database `sql_lab`, user `labuser` và mật khẩu đã chọn. Nếu đang chạy Docker trên máy từ xa, địa chỉ kết nối cần được xác định lại theo cấu hình mạng thực tế.

**Lưu ý về dữ liệu:** `docker stop sql-lab-postgres` dừng server, `docker start sql-lab-postgres` chạy lại; volume vẫn giữ dữ liệu. Việc xóa volume là thao tác riêng và có thể làm mất toàn bộ dữ liệu thực hành.

## 4. Ghi nhận đúng phiên bản: server, client và môi trường chạy

Một câu lệnh như `psql --version` chỉ trả về phiên bản **client psql**. Nó không chứng minh server đang kết nối cùng phiên bản. Tương tự, phiên bản DBeaver không phải phiên bản DBMS, và tên Docker image không đủ chứng minh bản vá đang chạy nếu tag có thể thay đổi.

Với môi trường PostgreSQL ở trên, ghi nhận các thông tin bằng lệnh sau:

```bash
# Phiên bản ứng dụng khách psql bên trong container
docker exec sql-lab-postgres psql --version

# Image reference khi container được tạo (chẳng hạn postgres:17)
docker inspect --format '{{.Config.Image}}' sql-lab-postgres

# Image ID chính xác đang gắn với container
docker inspect --format '{{.Image}}' sql-lab-postgres
```

Lấy thêm các thiết lập có thể ảnh hưởng tới hành vi truy vấn:

```sql
SHOW server_encoding;
SHOW lc_collate;
SHOW TimeZone;
```

**Thông tin tối thiểu cần lưu** gồm tên DBMS, phiên bản DBMS lấy từ truy vấn trên kết nối đang dùng, tên database, môi trường triển khai và thời điểm kiểm tra. Để người khác tái lập chính xác, nên có thêm phiên bản client, image tag + image ID/digest hoặc nguồn bộ cài, cổng kết nối, encoding, collation, time zone và các chế độ tương thích ảnh hưởng tới bài học. Không ghi mật khẩu hoặc thông tin đăng nhập bí mật trong file nộp bài.

### Mẫu biên bản môi trường

Sao chép mẫu dưới đây sang file riêng như `sql-lab-environment.md`, rồi **thay các chỗ trong dấu ngoặc nhọn bằng kết quả thực tế**:

```markdown
# Môi trường thực hành Database SQL

- Ngày ghi nhận: {YYYY-MM-DD}
- Mục tiêu: Học SQL quan hệ tổng quát
- DBMS: PostgreSQL
- Phiên bản server: {kết quả current_setting('server_version')}
- Phiên bản client: {kết quả psql --version}
- Cách triển khai: Docker
- Image reference: {kết quả docker inspect .Config.Image}
- Image ID hoặc digest: {kết quả docker inspect .Image}
- Database: sql_lab
- Địa chỉ kết nối: 127.0.0.1:5433
- Tài khoản kết nối: labuser (không ghi mật khẩu)
- Encoding: {kết quả SHOW server_encoding}
- Collation: {kết quả SHOW lc_collate}
- Time zone: {kết quả SHOW TimeZone}
- Lệnh xác minh phiên bản: SELECT current_setting('server_version');
- Ghi chú khác: {cấu hình riêng, nếu có}
```

Có thể đính kèm phần văn bản kết quả truy vấn đã chạy. Khi chuyển máy, đổi image, kết nối database khác hoặc nâng cấp server, hãy **ghi nhận lại phiên bản** thay vì dùng biên bản cũ.

## 5. Lấy phiên bản nếu chọn một DBMS khác

Hãy chạy truy vấn **trên chính kết nối dùng để thực hành**. Bảng sau cung cấp điểm bắt đầu cho các hệ phổ biến:

| Hệ quản trị | Truy vấn kiểm tra phiên bản | Ghi chú |
| --- | --- | --- |
| PostgreSQL | `SELECT current_setting('server_version');` hoặc `SELECT version();` | Trả về phiên bản server đang phục vụ kết nối |
| MySQL | `SELECT VERSION();` và `SELECT @@version_comment;` | `@@version_comment` giúp nhận biết bản phân phối |
| MariaDB | `SELECT VERSION();` | Ghi **MariaDB** là sản phẩm riêng, dù dùng giao thức/client tương tự MySQL |
| SQLite | `SELECT sqlite_version();` | Phiên bản thư viện SQLite đang thực thi câu SQL; không có server riêng trong cách dùng phổ biến |
| SQL Server | `SELECT SERVERPROPERTY('ProductVersion');` | Ghi thêm edition và `compatibility_level` nếu bài dùng tính năng phụ thuộc mức tương thích |
| Oracle Database | `SELECT banner FROM v$version;` | Có thể cần quyền xem view; ghi cả edition/bản vá nếu môi trường cung cấp |

Một số cấu hình cần kiểm tra bổ sung:

**SQL Server — mức tương thích của database:**

```sql
SELECT name, compatibility_level
FROM sys.databases
WHERE name = DB_NAME();
```

Server SQL Server có thể được nâng cấp, trong khi database vẫn dùng một `compatibility_level` cũ. Vì vậy chỉ có `ProductVersion` chưa đủ giải thích mọi khác biệt hành vi.

**MySQL — chế độ SQL và múi giờ:**

```sql
SELECT VERSION() AS server_version,
       @@sql_mode AS sql_mode,
       @@session.time_zone AS session_time_zone;
```

**SQLite — thư viện và thiết lập khóa ngoại của kết nối:**

```bash
sqlite3 sql-lab.db "SELECT sqlite_version(); PRAGMA foreign_keys;"
```

SQLite tự tạo `sql-lab.db` nếu tệp chưa tồn tại. Trạng thái `PRAGMA foreign_keys` áp dụng theo **kết nối**, nên cần ghi nhận hoặc bật theo yêu cầu khi làm bài có ràng buộc khóa ngoại. Nếu máy không có lệnh `sqlite3`, có thể dùng một công cụ tương thích SQLite khác, nhưng vẫn phải chạy `SELECT sqlite_version()` trên kết nối dùng để thực hành.

Đối với cơ sở dữ liệu do cloud quản lý, truy vấn SQL vẫn giúp xác định phiên bản engine; đồng thời cần ghi tên dịch vụ, vùng/instance, cấu hình tương thích và các giới hạn do nhà cung cấp áp dụng. Không suy diễn phiên bản chỉ từ tên sản phẩm hay ảnh chụp giao diện quản trị.

## 6. Vì sao phải giữ nhất quán phiên bản trong quá trình học SQL?

Ví dụ hai truy vấn sau phục vụ mục đích gần giống nhau nhưng không dùng chung cú pháp ở mọi hệ:

```sql
-- PostgreSQL, MySQL, SQLite: giới hạn số dòng trả về
SELECT id, name FROM students ORDER BY id LIMIT 5;
```

```sql
-- SQL Server: cú pháp T-SQL tương ứng
SELECT TOP (5) id, name FROM students ORDER BY id;
```

Bảng `students` chỉ là tên minh họa, chưa được tạo trong bài này. Những khác biệt tương tự còn gặp ở cột tự tăng, phép nối chuỗi, kiểu ngày giờ, JSON, upsert, phân biệt chữ hoa/chữ thường, và xử lý giao dịch. Ngay trong cùng một DBMS, các phiên bản hoặc chế độ tương thích khác nhau cũng có thể hỗ trợ tính năng khác nhau.

Khi ví dụ báo lỗi, thực hiện lần lượt:

1. Xác nhận **DBMS đang kết nối**, tên database, host và cổng để tránh chạy nhầm instance.
2. Chạy lại câu lệnh lấy **phiên bản server** tại chính kết nối bị lỗi.
3. So sánh phiên bản và cú pháp được yêu cầu trong bài; kiểm tra cấu hình liên quan như `sql_mode` hoặc `compatibility_level` nếu có.
4. Ghi lại SQL đã chạy, thông báo lỗi, kết quả lấy phiên bản và cách kết nối; từ đó mới chọn cú pháp tương ứng.

Đừng chỉ ghi “em dùng SQL”: SQL là ngôn ngữ, còn lỗi thực tế phụ thuộc vào engine, phiên bản, cài đặt và dữ liệu.

## 7. Bài thực hành: chốt và lưu môi trường của chính bạn

**Yêu cầu:** chọn một DBMS và tạo biên bản có thể dùng để người khác tái lập môi trường học.

1. Chọn một sản phẩm từ bảng ở mục 2 và viết 1–2 câu giải thích sự phù hợp với mục tiêu học.
2. Kết nối tới database sẽ dùng lâu dài cho các bài SQL. Có thể triển khai PostgreSQL theo mục 3 hoặc dùng hệ đã cài sẵn.
3. Chạy câu lệnh lấy **phiên bản DBMS từ kết nối** theo mục 4 hoặc 5. Đảm bảo kết nối đúng database dự định học.
4. Ghi nhận tên sản phẩm, phiên bản, cách triển khai, tên database, địa chỉ/cổng (nếu có), client, thời điểm kiểm tra và những cấu hình có ảnh hưởng. Không đưa mật khẩu vào biên bản.
5. Lưu file `sql-lab-environment.md` và một đoạn kết quả SQL minh chứng. Nếu dùng Docker, ghi thêm image reference và image ID/digest.

**Tự kiểm tra kết quả:** một người đọc biên bản phải trả lời được *“Bài này chạy trên DBMS nào?”, “Phiên bản engine thực tế là gì?”, “Lấy bằng lệnh nào?”, “Kết nối tới database nào?”, “Có đủ thông tin để tái lập hoặc giải thích khác biệt cú pháp không?”* Nếu chưa trả lời được, bổ sung dữ liệu môi trường trước khi chuyển sang bài SQL tiếp theo.
