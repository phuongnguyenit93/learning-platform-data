# Authentication plugin, SQL mode và collation sau nâng cấp

Sau khi nâng cấp MySQL, ứng dụng có thể kết nối thất bại dù tài khoản và mật khẩu không đổi; câu SQL từng chạy được có thể bắt đầu báo lỗi; kết quả so sánh hoặc sắp xếp chuỗi cũng có thể khác trước. Ba nhóm nguyên nhân cần kiểm tra sớm là authentication plugin của tài khoản, `sql_mode` của server/session và character set/collation của schema.

Các thay đổi mặc định qua những phiên bản lớn không tự động chuyển mọi tài khoản hay mọi cột hiện có sang cấu hình mới. Một số khác biệt chỉ xuất hiện khi tạo đối tượng mới, một số chỉ xuất hiện khi ứng dụng mở kết nối mới, còn một số chỉ lộ ra khi truy vấn chạy trên dữ liệu đặc biệt. Vì vậy, kiểm tra sau nâng cấp cần đối chiếu cấu hình cũ và mới, kiểm thử với đúng driver ứng dụng, đồng thời kiểm tra dữ liệu có nguy cơ xung đột dưới collation mới.

## 1. Ba lớp tương thích cần kiểm tra

| Lớp | Thành phần | Triệu chứng khi không tương thích |
|---|---|---|
| Xác thực | Plugin của tài khoản MySQL, giao thức xác thực và TLS/RSA | Client không đăng nhập được, lỗi plugin không được hỗ trợ hoặc lỗi trao đổi khóa |
| Ngữ nghĩa SQL | `sql_mode` ở cấp GLOBAL/SESSION và mode được lưu cùng stored program | Truy vấn bị từ chối, giá trị ngày/số bị xử lý khác, hành vi SQL thay đổi |
| Chuỗi và so sánh | Character set, collation ở server/database/table/column và collation connection | Thứ tự sort khác, phép so sánh khác, unique key xung đột hoặc index không tạo được |

Không xử lý cả ba bằng một thay đổi cấu hình chung. Mỗi lớp cần được kiểm tra và chuyển đổi theo mục tiêu tương thích riêng.

## 2. Authentication plugin thay đổi qua các phiên bản

Authentication plugin quyết định cách MySQL xác minh thông tin đăng nhập của tài khoản. Plugin được gắn với từng account, tức cặp `user` và `host`; hai tài khoản cùng tên nhưng khác host có thể dùng plugin hoặc chính sách khác nhau.

Một khác biệt quan trọng khi nâng cấp:

- MySQL 5.7 thường dùng `mysql_native_password` làm plugin mặc định.
- Từ MySQL 8.0.4, `caching_sha2_password` trở thành plugin xác thực mặc định.
- `mysql_native_password` bị deprecated từ MySQL 8.0.34, bị tắt mặc định trong MySQL 8.4 và bị loại bỏ trong MySQL 9.0.

Vì vậy, một ứng dụng cũ chỉ hỗ trợ `mysql_native_password` có thể tiếp tục kết nối với một số cấu hình MySQL 8.0 nhưng gặp lỗi khi nâng lên 8.4 hoặc 9.x. Không nên xem việc bật lại plugin cũ là giải pháp lâu dài; hãy nâng cấp driver và chuyển tài khoản sang plugin được hỗ trợ.

### caching_sha2_password hoạt động như thế nào?

`caching_sha2_password` dùng cơ chế xác thực SHA-256 và cache để giảm chi phí xác thực lặp lại. Một kết nối có thể dùng fast authentication nếu thông tin xác thực cần thiết đã có trong cache; nếu cần full authentication, client và server phải trao đổi thông tin an toàn.

Với full authentication, nên dùng TLS để bảo vệ kết nối. Nếu không dùng TLS, client có thể cần cơ chế trao đổi khóa RSA và phải tin cậy đúng public key của server. Cờ lấy public key tự động có thể thuận tiện trong môi trường thử nghiệm, nhưng production nên xác minh danh tính server và bảo vệ kênh kết nối bằng TLS.

Plugin xác thực không tự thay thế TLS. Việc tài khoản dùng `caching_sha2_password` không có nghĩa mọi dữ liệu SQL sau đăng nhập đã được mã hóa trên đường truyền. Cấu hình TLS và xác minh chứng thư vẫn là chính sách kết nối riêng.

## 3. Kiểm kê tài khoản và client trước khi nâng cấp

Trước khi thay đổi plugin, lập danh sách account đang tồn tại, host được phép kết nối, plugin sử dụng và ứng dụng sở hữu account đó. Có thể xem thông tin account bằng:

```sql
SELECT
  User,
  Host,
  plugin
FROM mysql.user
ORDER BY User, Host;
```

`mysql.user` là đối tượng hệ thống được MySQL cung cấp để xem metadata tài khoản; chỉ đọc thông tin cần thiết và không cập nhật trực tiếp bảng hệ thống. Để kiểm tra định nghĩa cùng yêu cầu bảo mật của một account cụ thể, dùng:

```sql
SHOW CREATE USER 'orders_app'@'10.20.30.%';
SHOW GRANTS FOR 'orders_app'@'10.20.30.%';
```

Kiểm tra plugin xác thực đã được nạp:

```sql
SELECT
  PLUGIN_NAME,
  PLUGIN_STATUS
FROM INFORMATION_SCHEMA.PLUGINS
WHERE PLUGIN_TYPE = 'AUTHENTICATION';
```

Sau đó đối chiếu với ma trận client:

- Phiên bản MySQL Connector/J, Connector/NET, Connector/Python, client C API hoặc driver tương ứng.
- Phiên bản framework và thư viện kết nối thực tế đang được đóng gói trong ứng dụng.
- Cấu hình TLS, CA, hostname verification và RSA public key nếu có.
- Account dùng bởi ứng dụng, job batch, monitoring, backup, migration và công cụ vận hành.
- Cơ chế xác thực ngoài như LDAP, PAM, socket hoặc plugin do tổ chức tự triển khai.

Không chuyển đổi hàng loạt account mà chưa xác định owner. Tài khoản monitoring, backup hoặc ứng dụng cũ có thể chạy trên một máy chủ khác với bộ connector khác nhau.

## 4. Chuyển account sang caching_sha2_password

Với account dùng mật khẩu MySQL thông thường, có thể chuyển plugin và đặt lại mật khẩu bằng `ALTER USER`:

```sql
ALTER USER 'orders_app'@'10.20.30.%'
  IDENTIFIED WITH caching_sha2_password BY 'REPLACE_WITH_NEW_SECRET';
```

Thay chuỗi mẫu bằng mật khẩu được tạo và lưu qua secret manager theo quy trình của tổ chức. Không ghi mật khẩu production vào repository, script migration dùng chung, ticket hoặc lịch sử shell. Việc thay mật khẩu có thể yêu cầu cập nhật secret của ứng dụng và mở lại connection pool.

Nếu phiên bản hỗ trợ mật khẩu ngẫu nhiên, có thể để MySQL sinh mật khẩu:

```sql
ALTER USER 'orders_app'@'10.20.30.%'
  IDENTIFIED WITH caching_sha2_password BY RANDOM PASSWORD;
```

Lưu mật khẩu được trả về ngay vào secret manager. Kiểm tra cú pháp và quyền cần thiết trên đúng phiên bản trước khi sử dụng.

Sau thay đổi:

1. Kiểm tra `SHOW CREATE USER` để xác nhận plugin của đúng cặp `user`/`host`.
2. Cập nhật secret trong ứng dụng hoặc secret manager.
3. Mở một kết nối mới bằng đúng phiên bản driver production.
4. Kiểm tra TLS và xác minh chứng thư server.
5. Chạy truy vấn kiểm tra quyền, transaction và thao tác ghi cần thiết.
6. Xác nhận connection pool tái tạo kết nối và không tiếp tục dùng session cũ.

Các session đang mở thường tiếp tục hoạt động với trạng thái xác thực đã thiết lập; phép thử phải mở kết nối mới để chứng minh driver có thể xác thực lại. Đừng chỉ kiểm tra kết nối đang tồn tại sau khi thay plugin.

### Khi vẫn còn client cũ

Trong giai đoạn chuyển tiếp, MySQL 8.4 có thể bật lại `mysql_native_password` bằng cấu hình server `mysql_native_password=ON`, nếu tổ chức chấp nhận rủi ro và cần thời gian nâng cấp client. Đây chỉ nên là biện pháp tạm thời có thời hạn, có danh sách account phụ thuộc và kế hoạch loại bỏ. MySQL 9.0 đã loại bỏ plugin này nên không thể dựa vào giải pháp đó khi nâng lên 9.x.

Không hạ cấp toàn bộ server hoặc đổi mọi account về plugin cũ chỉ để một ứng dụng chưa được cập nhật tiếp tục hoạt động. Nâng cấp driver thường là hướng xử lý bền vững hơn.

## 5. TLS, RSA và các lỗi đăng nhập thường gặp

Các lỗi xác thực sau nâng cấp thường xuất phát từ client hoặc cách trao đổi thông tin xác thực:

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Client báo authentication plugin không được hỗ trợ | Driver cũ không triển khai `caching_sha2_password` | Nâng cấp connector/driver và kiểm thử trên môi trường staging |
| Full authentication thất bại khi không dùng TLS | Client không có RSA public key phù hợp hoặc không hỗ trợ trao đổi khóa cần thiết | Ưu tiên cấu hình TLS; nếu dùng RSA, phân phối và xác minh public key theo chính sách |
| Fast authentication hoạt động nhưng kết nối mới thất bại | Kết nối cũ đã dùng cache; kết nối mới phải thực hiện full authentication | Kiểm tra TLS/RSA và thử mở kết nối mới sau khi cache hết hiệu lực hoặc trên account thử nghiệm |
| Account đúng tên nhưng vẫn bị từ chối | MySQL chọn account khác do host match hoặc account có plugin khác | Kiểm tra chính xác cặp `user`/`host`, `SHOW CREATE USER` và log xác thực |
| Ứng dụng lỗi sau đổi plugin | Secret chưa cập nhật, pool giữ session cũ hoặc connector không tương thích | Cập nhật secret, tái tạo pool và kiểm tra connector |
| Kết nối đăng nhập được nhưng truyền dữ liệu không mã hóa | Authentication plugin không tự bật TLS | Cấu hình TLS riêng và xác minh `Ssl_version`, `Ssl_cipher` trong session |

Kiểm tra trạng thái TLS của phiên kết nối:

```sql
SHOW SESSION STATUS LIKE 'Ssl_version';
SHOW SESSION STATUS LIKE 'Ssl_cipher';
```

Nếu `Ssl_cipher` rỗng, session hiện tại không dùng TLS. Kiểm tra bằng một kết nối TCP mới đúng với cách ứng dụng kết nối; Unix socket local có thể không có cipher TLS.

## 6. SQL mode có thể làm thay đổi hành vi câu lệnh

`sql_mode` là tập hợp các chế độ ảnh hưởng cách MySQL phân tích và thực thi SQL. Một lần nâng cấp có thể thay đổi giá trị mặc định, loại bỏ mode cũ hoặc làm lộ ra câu lệnh vốn phụ thuộc vào hành vi không chuẩn.

Kiểm tra cả giá trị GLOBAL và SESSION:

```sql
SELECT @@GLOBAL.sql_mode;
SELECT @@SESSION.sql_mode;
```

Giá trị GLOBAL làm mặc định cho session mới. Ứng dụng hoặc connection pool có thể đặt lại session mode khi kết nối, nên không thể chỉ nhìn `@@GLOBAL.sql_mode` để kết luận truy vấn production đang chạy với mode nào.

Một số mode cần đặc biệt chú ý:

| Mode | Ảnh hưởng | Vấn đề có thể lộ ra sau nâng cấp |
|---|---|---|
| `STRICT_TRANS_TABLES` | Từ chối hoặc cảnh báo các giá trị sai/thiếu theo quy tắc strict mode | INSERT/UPDATE cũ có thể thất bại vì dữ liệu không hợp lệ trước đây được ép kiểu hoặc thay bằng giá trị mặc định |
| `STRICT_ALL_TABLES` | Áp dụng strict behavior cho nhiều storage engine hơn | Batch import hoặc bảng không transactional có thể xử lý lỗi khác |
| `ONLY_FULL_GROUP_BY` | Yêu cầu cột không aggregate trong SELECT phải phù hợp quy tắc GROUP BY hoặc phụ thuộc hàm | Truy vấn báo cáo từng chạy được có thể báo lỗi vì chọn cột không xác định |
| `ANSI_QUOTES` | Dấu nháy kép được hiểu là dấu nháy định danh | SQL dùng dấu `"` để bao chuỗi có thể lỗi |
| `PIPES_AS_CONCAT` | `||` được hiểu là phép nối chuỗi thay vì OR | Biểu thức logic cũ có thể đổi nghĩa |
| `NO_ZERO_DATE`, `NO_ZERO_IN_DATE` | Kiểm soát giá trị ngày có thành phần bằng 0; trạng thái và mặc định phụ thuộc phiên bản | Dữ liệu ngày cũ hoặc import có ngày zero có thể phát sinh warning/lỗi |
| `NO_AUTO_CREATE_USER` | Mode cũ liên quan cú pháp GRANT tạo user | Đã bị loại bỏ trong MySQL 8.0.11; cấu hình còn chứa mode này có thể không tương thích |

Không sao chép nguyên chuỗi `sql_mode` từ một máy chủ cũ sang phiên bản mới mà chưa kiểm tra mode còn được hỗ trợ. Một mode đã bị loại bỏ có thể khiến server từ chối cấu hình khi khởi động hoặc khi đặt biến.

### Kiểm tra truy vấn bị ảnh hưởng

Với `ONLY_FULL_GROUP_BY`, truy vấn sau có thể bị từ chối nếu `customer_name` không phụ thuộc hàm vào `customer_id` trong schema:

```sql
SELECT customer_id, customer_name, SUM(amount)
FROM sales.orders
GROUP BY customer_id;
```

Cách sửa đúng thường là nhóm theo cả cột, dùng hàm aggregate phù hợp hoặc bảo đảm khóa/unique constraint thể hiện quan hệ phụ thuộc:

```sql
SELECT customer_id, MAX(customer_name) AS customer_name,
       SUM(amount) AS total_amount
FROM sales.orders
GROUP BY customer_id;
```

Chỉ dùng `MAX(customer_name)` nếu mọi hàng của cùng `customer_id` thực sự có cùng tên hoặc nghiệp vụ chấp nhận chọn giá trị lớn nhất theo thứ tự collation. Không thêm hàm aggregate chỉ để làm truy vấn hết lỗi mà không xác định ý nghĩa dữ liệu.

Với strict mode, kiểm tra các câu lệnh INSERT/UPDATE, import CSV, ETL và code đang dựa vào việc ép chuỗi sang số hoặc ngày. Sửa dữ liệu nguồn hoặc mapping để hợp lệ thay vì tắt strict mode toàn server.

## 7. Đối chiếu và cấu hình SQL mode sau nâng cấp

Trước nâng cấp, lưu lại `@@GLOBAL.sql_mode` và các session mode của ứng dụng. Sau nâng cấp, so sánh giá trị mới, xác định mode nào đã đổi hoặc không còn được hỗ trợ.

Nếu cần thay đổi, đặt theo một chuỗi mode đã kiểm thử. Ví dụ minh họa đặt strict mode cùng các mode cần thiết:

```sql
SET GLOBAL sql_mode =
  'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
```

Lệnh trên chỉ là ví dụ chính sách; danh sách thực tế phải phù hợp với ứng dụng và phiên bản. Thay đổi GLOBAL không tự sửa session hiện hữu. Đối với thay đổi lâu dài, quản lý trong file cấu hình hoặc cơ chế persistence được tổ chức sử dụng, sau khi đã kiểm thử:

```sql
SET PERSIST sql_mode =
  'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
```

Đừng loại bỏ `ONLY_FULL_GROUP_BY` hoặc strict mode chỉ để truy vấn cũ tiếp tục chạy mà chưa xem xét dữ liệu và ý nghĩa câu SQL. Nếu phải tạm thời nới lỏng mode cho một session import đã kiểm soát, hãy đặt lại sau tác vụ và ghi nhận lý do, thời hạn.

### Stored routine và trigger có thể giữ SQL mode cũ

MySQL lưu `sql_mode` đang có hiệu lực khi tạo stored procedure, stored function, trigger và event. Khi các đối tượng này thực thi, chúng sử dụng mode được lưu cùng đối tượng thay vì tự động nhận toàn bộ mode mới của server.

Do đó, sau nâng cấp có thể có hai hành vi SQL khác nhau: câu lệnh chạy trực tiếp dùng session mode mới, trong khi routine hoặc trigger cũ tiếp tục dùng mode đã lưu từ lúc tạo. Kiểm tra metadata của các đối tượng và lên kế hoạch tái tạo chúng nếu cần áp dụng mode mới. Trước khi `DROP`/`CREATE` hoặc deploy lại, lưu định nghĩa đầy đủ, `DEFINER`, quyền và lịch chạy event để không làm mất ngữ nghĩa bảo mật hay vận hành.

## 8. Character set và collation sau nâng cấp

Character set quy định cách mã hóa ký tự; collation quy định cách so sánh và sắp xếp chuỗi. Hai khái niệm này liên quan nhưng không giống nhau.

- Character set quyết định tập ký tự và cách biểu diễn byte. `utf8mb4` hỗ trợ tối đa bốn byte cho một ký tự Unicode.
- Collation quyết định các quy tắc so sánh: phân biệt hoa/thường, dấu, ký tự tương đương và khoảng trắng ở cuối.

Trong MySQL 8.0, mặc định server mới chuyển sang `utf8mb4` với collation mặc định `utf8mb4_0900_ai_ci`. Các cài đặt MySQL 5.7 thường dùng `latin1` và `latin1_swedish_ci` làm mặc định. Tuy nhiên, nâng cấp server không tự động chuyển toàn bộ database, table và column cũ sang `utf8mb4`; các đối tượng đã khai báo charset/collation riêng tiếp tục giữ thuộc tính của chúng cho tới khi được chuyển đổi rõ ràng.

Vì vậy, sau nâng cấp có thể tồn tại cùng lúc:

- Bảng cũ dùng `latin1` hoặc `utf8mb4_unicode_ci`.
- Bảng mới được tạo mà không chỉ định charset dùng mặc định server mới.
- Một số cột có collation riêng khác collation của bảng.
- Kết nối client dùng `character_set_client`, `character_set_connection` hoặc `collation_connection` khác với schema.

Kiểm tra các mặc định và session:

```sql
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';
SHOW VARIABLES LIKE 'character_set_database';
SHOW VARIABLES LIKE 'collation_database';
SHOW VARIABLES LIKE 'character_set_client';
SHOW VARIABLES LIKE 'character_set_connection';
SHOW VARIABLES LIKE 'collation_connection';
```

Kiểm tra charset/collation của schema, table và column qua `information_schema`:

```sql
SELECT
  SCHEMA_NAME,
  DEFAULT_CHARACTER_SET_NAME,
  DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = 'sales';

SELECT
  TABLE_NAME,
  TABLE_COLLATION
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'sales';

SELECT
  TABLE_NAME,
  COLUMN_NAME,
  CHARACTER_SET_NAME,
  COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'sales'
  AND CHARACTER_SET_NAME IS NOT NULL;
```

Không dựa vào `collation_server` để suy ra collation thực của mọi cột. Cột có thể ghi đè mặc định table và table có thể ghi đè mặc định database.

## 9. Khác biệt collation có thể làm thay đổi kết quả

Tên collation thường chứa các hậu tố thể hiện quy tắc so sánh:

- `_ai_ci`: accent-insensitive, case-insensitive; thường không phân biệt dấu và chữ hoa/thường.
- `_as_cs`: accent-sensitive, case-sensitive; phân biệt dấu và chữ hoa/thường.
- `_bin`: so sánh theo giá trị nhị phân của ký tự theo charset.
- Collation có hậu tố `_0900` dùng bộ quy tắc Unicode Collation Algorithm phiên bản 9.0 trong MySQL 8.0.

Một khác biệt quan trọng là padding khi so sánh chuỗi. Nhiều collation cũ dùng `PAD SPACE`, nghĩa là khoảng trắng ở cuối chuỗi được đệm để so sánh. Các collation UCA 9.0 như `utf8mb4_0900_ai_ci` dùng `NO PAD`, trong đó khoảng trắng ở cuối có thể làm hai giá trị khác nhau. Điều này ảnh hưởng so sánh `=`, `GROUP BY`, `DISTINCT`, join và unique index.

Ví dụ với collation không phân biệt hoa/thường và dấu, các chuỗi như `Cafe`, `cafe` và `café` có thể được xem là tương đương theo quy tắc collation. Với collation phân biệt, chúng có thể là các giá trị khác nhau. Kết quả cụ thể phụ thuộc collation được chọn, không nên suy đoán chỉ từ cách hiển thị chuỗi.

### Rủi ro unique index khi đổi collation

Giả sử bảng người dùng đang lưu hai giá trị email mà collation cũ xem là khác nhau. Khi đổi sang collation không phân biệt hoa/thường hoặc dấu, hai giá trị có thể trở thành tương đương và không thể cùng tồn tại trong một unique index.

Trước khi chuyển đổi, tìm nhóm giá trị sẽ trùng theo collation đích. Nếu cột hiện tại đã dùng charset `utf8mb4`, có thể kiểm tra:

```sql
SELECT
  email COLLATE utf8mb4_0900_ai_ci AS email_under_new_collation,
  COUNT(*) AS occurrences
FROM users
GROUP BY email_under_new_collation
HAVING COUNT(*) > 1;
```

Thử trên dữ liệu thật và xác nhận collation đích có trong phiên bản server. Nếu cột dùng charset khác, phải chuyển đổi/CAST sang charset đích trong truy vấn kiểm tra. Giải quyết các duplicate theo quy tắc nghiệp vụ trước khi tạo unique index hoặc đổi collation.

Ngoài unique key, collation mới có thể làm thay đổi thứ tự ORDER BY, kết quả LIKE, phép so sánh trong JOIN, nhóm GROUP BY và thứ tự phân trang. Nếu ứng dụng dùng `ORDER BY name LIMIT ... OFFSET ...`, thay đổi thứ tự có thể làm trang kết quả khác dù dữ liệu không đổi.

## 10. Chọn và chuyển collation có kiểm soát

Không phải mọi hệ thống đều nên chuyển tất cả cột sang một collation giống nhau. Ví dụ, tên người có thể cần tìm kiếm không phân biệt dấu, trong khi mã định danh, token hoặc chuỗi có ý nghĩa phân biệt byte có thể cần collation nhị phân hoặc quy tắc chặt hơn.

Kiểm tra các collation được server hỗ trợ:

```sql
SHOW COLLATION LIKE 'utf8mb4_0900_ai_ci';
SHOW COLLATION LIKE 'utf8mb4_unicode_ci';
SHOW COLLATION LIKE 'utf8mb4_bin';
```

Với MySQL 8.0, có thể xem thêm thuộc tính padding trong kết quả `SHOW COLLATION` hoặc `INFORMATION_SCHEMA.COLLATIONS` tùy phiên bản. Đừng sử dụng collation `_0900` nếu một replica hoặc môi trường downstream chưa hỗ trợ nó.

Đổi mặc định cho database chỉ ảnh hưởng các đối tượng được tạo mới hoặc thay đổi mà không chỉ định thuộc tính riêng; nó không tự chuyển các cột hiện có:

```sql
ALTER DATABASE sales
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

Đổi toàn bộ table và các cột ký tự sang charset/collation mới có thể cần rebuild và chuyển đổi dữ liệu:

```sql
ALTER TABLE sales.customers
  CONVERT TO CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

Lệnh trên có thể tốn I/O, dung lượng, thời gian và metadata lock; nó cũng có thể thay đổi kiểu cột văn bản để giữ khả năng biểu diễn ký tự. Kiểm tra index length, duplicate, foreign key, ứng dụng và replication trước khi chạy. Với bảng lớn, xử lý như một schema migration có kế hoạch bảo trì riêng.

Nếu chỉ đổi collation của một cột, có thể dùng `MODIFY` hoặc `CHANGE` để khai báo lại đầy đủ kiểu dữ liệu và thuộc tính cột. Phải giữ nguyên `NULL`/`NOT NULL`, default, comment, generated expression và các thuộc tính khác; nếu bỏ sót, DDL có thể làm mất cấu hình hiện có.

### utf8 và utf8mb4

Trong MySQL, tên `utf8` là alias lịch sử của `utf8mb3`, chỉ hỗ trợ tối đa ba byte cho một ký tự. `utf8mb3` đã deprecated trong MySQL 8.0. Với dữ liệu Unicode mới, nên thiết kế rõ `utf8mb4` và collation phù hợp. Tuy nhiên, chuyển đổi dữ liệu cũ cần kiểm tra encoding thực tế; khai báo sai charset không tự sửa byte đã bị mã hóa sai trước đó.

## 11. Collation giữa connection và column

Ngay cả khi bảng đã dùng collation mong muốn, kết nối ứng dụng vẫn có thể sử dụng charset/collation khác. MySQL chuyển đổi chuỗi giữa client và connection theo các biến session; biểu thức có nhiều collation có thể dẫn tới coercibility hoặc lỗi illegal mix of collations.

Kiểm tra cấu hình session:

```sql
SELECT
  @@character_set_client,
  @@character_set_connection,
  @@character_set_results,
  @@collation_connection;
```

Ứng dụng nên cấu hình connector dùng `utf8mb4` theo hướng dẫn driver. Tránh đặt `SET NAMES` thủ công ở nhiều nơi nếu connector đã quản lý charset, vì có thể khiến trạng thái client và server không đồng nhất. Nếu gặp `Illegal mix of collations`, kiểm tra charset/collation của từng cột, literal, biến và biểu thức trong JOIN/UNION; chỉ dùng `COLLATE` tường minh khi đã xác định quy tắc nghiệp vụ.

Ví dụ ép so sánh theo collation cụ thể:

```sql
SELECT customer_id
FROM customers
WHERE customer_name COLLATE utf8mb4_0900_ai_ci =
      _utf8mb4'Nguyen' COLLATE utf8mb4_0900_ai_ci;
```

Đây là ví dụ khi cột và literal tương thích với charset `utf8mb4`. Không ép collation chỉ để che lỗi thiết kế nếu các cột đang biểu diễn dữ liệu có ngữ nghĩa khác nhau.

## 12. Kế hoạch tương thích sau nâng cấp

Một kế hoạch thực tế nên chia thành các giai đoạn:

### Trước nâng cấp

1. Ghi lại phiên bản MySQL, plugin xác thực của mọi account, driver và connector ứng dụng.
2. Lưu `@@GLOBAL.sql_mode`, session mode thực tế của ứng dụng và cấu hình connection pool.
3. Xuất danh sách database/table/column cùng character set và collation.
4. Tìm account dùng `mysql_native_password` và các client chưa hỗ trợ `caching_sha2_password`.
5. Tìm truy vấn phụ thuộc SQL mode cũ, ngày zero, phép GROUP BY không chuẩn và dấu nháy kép.
6. Xác định unique index, phép JOIN và logic phân trang nhạy với collation.
7. Tạo bản sao staging có cùng dữ liệu, account, routine và cấu hình gần production.

### Sau nâng cấp trên staging

1. Xác nhận server khởi động và plugin cần thiết được nạp.
2. Mở kết nối mới bằng từng loại driver với account đại diện; xác minh TLS.
3. Đặt session mode như production và chạy bộ kiểm thử SQL.
4. Kiểm tra stored procedure, function, trigger và event có SQL mode được lưu từ trước.
5. So sánh charset/collation ở server, database, table, column và connection.
6. Chạy truy vấn duplicate dưới collation đích và thử tạo index trên bản clone.
7. Đối chiếu ORDER BY, LIKE, JOIN, GROUP BY, DISTINCT và phân trang.
8. Kiểm tra replication và tương thích giữa các phiên bản trong topology.

### Sau khi triển khai production

- Theo dõi lỗi xác thực, số kết nối thất bại và lỗi handshake TLS.
- Theo dõi lỗi SQL như `ONLY_FULL_GROUP_BY`, incorrect date và data truncation.
- Theo dõi lỗi duplicate key hoặc illegal mix of collations.
- Xác nhận tất cả pool đã tạo kết nối mới và nhận đúng session variables.
- Ghi nhận account còn dùng plugin cũ cùng owner và thời hạn loại bỏ.
- Chỉ chuyển collation hoặc dữ liệu theo từng nhóm bảng sau khi đã đối soát.

## 13. Chẩn đoán sau nâng cấp

| Triệu chứng | Kiểm tra đầu tiên | Hướng khắc phục |
|---|---|---|
| Một số ứng dụng không đăng nhập được | Account plugin, host match, phiên bản connector, TLS/RSA | Nâng cấp driver, chuyển account có kế hoạch, xác minh CA/hostname |
| Chỉ kết nối mới thất bại | Full authentication, cache, secret và connection pool | Thử kết nối mới với TLS và secret hiện hành; tái tạo pool |
| Truy vấn GROUP BY báo lỗi | `@@SESSION.sql_mode`, `ONLY_FULL_GROUP_BY` | Viết lại query theo ngữ nghĩa aggregate/phụ thuộc hàm |
| Import ngày cũ thất bại | Strict mode, zero date, định dạng file | Chuẩn hóa dữ liệu nguồn và xử lý giá trị ngày không hợp lệ |
| DDL tạo unique index thất bại | Giá trị trùng theo collation đích | Tìm và xử lý duplicate theo nghiệp vụ trước khi tạo index |
| ORDER BY hoặc tìm kiếm trả kết quả khác | Collation thực của column và connection | So sánh collation cũ/mới, kiểm thử quy tắc case/accent/padding |
| Illegal mix of collations | Các operand trong biểu thức dùng collation khác nhau | Chuẩn hóa schema/connection hoặc dùng `COLLATE` tường minh đúng nghiệp vụ |
| Replica dừng khi áp dụng DDL | Replica chưa hỗ trợ collation/plugin hoặc schema khác | Kiểm tra version và log applier; triển khai tương thích trước khi phát DDL |

Không sửa nhanh bằng cách đổi global SQL mode, chuyển tất cả cột sang collation mặc định hoặc bật plugin xác thực cũ trên mọi server. Trước tiên xác định chính xác account, session, query hoặc column gây lỗi; sau đó áp dụng thay đổi có phạm vi hẹp và kiểm thử lại.

## 14. Tình huống thực hành

Một hệ thống đang nâng cấp từ MySQL 5.7 lên MySQL 8.4. Ứng dụng Java cũ, một job ETL và một dashboard dùng các connector ở phiên bản khác nhau. Database có cột email unique, nhiều stored procedure và một số bảng cũ dùng `latin1`.

**Bước 1 — Kiểm kê xác thực.** Liệt kê account và plugin, xác định account nào còn dùng `mysql_native_password`. Lập bảng owner/driver cho từng account, bao gồm ETL và dashboard.

**Bước 2 — Nâng cấp connector.** Nâng cấp driver Java và các client còn lại để hỗ trợ `caching_sha2_password`. Trên staging, mở kết nối mới qua TLS và xác minh hostname với từng account.

**Bước 3 — Chuyển account.** Chuyển account theo từng ứng dụng bằng `ALTER USER`, cập nhật secret và khởi động lại pool. Giữ một account quản trị đã kiểm thử để xử lý nếu ứng dụng gặp lỗi.

**Bước 4 — So sánh SQL mode.** Ghi lại mode cũ/mới, chạy toàn bộ truy vấn báo cáo và ETL. Sửa truy vấn GROUP BY và dữ liệu ngày không hợp lệ; kiểm tra mode đã lưu trong routine và trigger.

**Bước 5 — Đánh giá collation.** Kiểm kê các cột email và tìm duplicate theo collation đích. Kiểm tra trailing spaces, case/accent sensitivity và các truy vấn tìm kiếm. Chỉ chuyển bảng sau khi có quyết định nghiệp vụ cho các giá trị trùng.

**Bước 6 — Triển khai theo giai đoạn.** Nâng cấp replica và kiểm tra tương thích trước khi phát DDL dùng collation mới. Chạy migration trên bảng nhỏ trước, sau đó bảng lớn theo kế hoạch dung lượng/lag. Theo dõi lỗi ứng dụng và đối soát kết quả sau mỗi bước.

Không cần chuyển mọi bảng `latin1` sang `utf8mb4` trong cùng một cửa sổ nâng cấp. Ưu tiên bảng có nhu cầu Unicode rõ ràng, xác định encoding thực tế và lập kế hoạch riêng cho các bảng lớn hoặc có unique index nhạy với collation.

## 15. Checklist production

- [ ] Đã kiểm kê account theo cặp `user`/`host`, plugin và ứng dụng sở hữu.
- [ ] Tất cả connector cần thiết đã hỗ trợ `caching_sha2_password`.
- [ ] Đã thử full authentication trên kết nối mới và xác minh TLS.
- [ ] Không còn phụ thuộc không có thời hạn vào `mysql_native_password`.
- [ ] Đã lưu và so sánh `@@GLOBAL.sql_mode` cùng session mode thực tế.
- [ ] Đã rà soát truy vấn GROUP BY, strict mode, zero date và các mode đã bị loại bỏ.
- [ ] Đã kiểm tra SQL mode được lưu trong procedure, function, trigger và event.
- [ ] Đã kiểm kê charset/collation ở server, database, table, column và connection.
- [ ] Đã tìm duplicate theo collation đích trước khi đổi unique index hoặc collation.
- [ ] Đã kiểm thử ORDER BY, JOIN, LIKE, GROUP BY, DISTINCT và phân trang.
- [ ] Đã kiểm tra replica hỗ trợ plugin/collation và phiên bản tương thích trước khi phát thay đổi.
- [ ] Có kế hoạch chuyển đổi theo giai đoạn, đối soát và khôi phục/forward-fix.

Nâng cấp MySQL an toàn cần xác minh cách client đăng nhập, cách server diễn giải SQL và cách dữ liệu chuỗi được so sánh. Chuyển account sang plugin được hỗ trợ, kiểm soát `sql_mode` theo session và đánh giá collation trước khi chuyển dữ liệu giúp tránh lỗi chỉ xuất hiện khi ứng dụng mở kết nối mới hoặc xử lý các giá trị đặc biệt trong production.
