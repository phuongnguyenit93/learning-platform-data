# Nguyên tắc quyền tối thiểu và tách tài khoản quản trị/ứng dụng

## Mục tiêu

Trong MySQL, một tài khoản kết nối thành công chưa có nghĩa là tài khoản đó nên được phép làm mọi việc trên máy chủ. Thiết kế quyền tốt bắt đầu từ việc xác định mỗi thành phần cần thực hiện thao tác nào, trên dữ liệu nào và từ nguồn kết nối nào. Sau đó, cấp đúng những quyền cần thiết cho từng danh tính và kiểm tra lại bằng chính tài khoản đó.

Bài học này thuộc module **DATABASE_MYSQL**, tập trung vào thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời và các công việc vận hành cơ sở dữ liệu quan hệ. Trong phạm vi bảo mật, nguyên tắc quyền tối thiểu giúp bảo vệ dữ liệu và giảm tác động khi một mật khẩu, máy chủ ứng dụng hoặc tiến trình bị xâm nhập. Việc tách tài khoản quản trị khỏi tài khoản ứng dụng cũng giúp giới hạn lỗi cấu hình và làm rõ trách nhiệm của từng thành phần.

Sau bài học, bạn có thể:

- Giải thích nguyên tắc quyền tối thiểu và các cấp phạm vi quyền trong MySQL.
- Thiết kế tài khoản riêng cho ứng dụng chạy thường xuyên, tác vụ triển khai và người quản trị.
- Cấp, kiểm tra, thu hồi quyền bằng `CREATE USER`, `GRANT`, `SHOW GRANTS` và `REVOKE`.
- Dùng role để quản lý tập quyền nhất quán trên MySQL 8.0 trở lên.
- Kiểm chứng tài khoản thực tế mà MySQL đã dùng để xác thực và áp dụng quyền.

## 1. Quyền tối thiểu trong MySQL

**Quyền tối thiểu (least privilege)** nghĩa là mỗi tài khoản chỉ nhận những quyền cần cho nhiệm vụ đã xác định, trong phạm vi dữ liệu nhỏ nhất có thể. Nếu một dịch vụ chỉ đọc danh sách sản phẩm, tài khoản của dịch vụ đó thường chỉ cần `SELECT` trên bảng hoặc view liên quan. Nó không cần `DROP`, `ALTER`, `CREATE USER` hay quyền quản trị toàn máy chủ.

MySQL quản lý tài khoản theo cặp tên người dùng và máy chủ nguồn, có dạng `'user_name'@'host_name'`. Vì vậy, `'orders_app'@'10.20.30.15'` và `'orders_app'@'%'` là hai account khác nhau. Phần `host_name` giới hạn nơi được phép kết nối; hãy dùng địa chỉ IP, hostname hoặc phạm vi mạng phù hợp với hạ tầng thực tế. Ký tự `%` cho phép khớp nhiều host, nên chỉ dùng khi có lý do rõ ràng và các lớp kiểm soát mạng bổ sung.

Cần phân biệt hai bước:

- **Xác thực (authentication):** MySQL xác định kết nối có đăng nhập được bằng account phù hợp hay không.
- **Phân quyền (authorization):** sau khi đăng nhập, MySQL kiểm tra account đang có quyền thực hiện câu lệnh trên đối tượng được yêu cầu hay không.

Quyền có thể được cấp ở nhiều phạm vi:

| Phạm vi | Ví dụ | Khi nào nên dùng |
|---|---|---|
| Toàn máy chủ | `ON *.*` | Chỉ cho tác vụ quản trị thực sự cần quyền trên nhiều schema |
| Schema | `ON orders.*` | Dịch vụ chỉ làm việc trong schema `orders` |
| Bảng hoặc view | `ON orders.customer` | Chỉ cần truy cập một đối tượng cụ thể |
| Cột | `GRANT SELECT (id, display_name) ON orders.customer` | Chỉ cần một số cột; hữu ích khi cần giới hạn dữ liệu nhạy cảm |
| Stored procedure hoặc function | `GRANT EXECUTE ON PROCEDURE orders.rebuild_summary` | Chỉ cần gọi routine đã được kiểm soát |

Không nên cấp quyền toàn cục chỉ vì câu lệnh dễ viết hơn. Quyền trên `orders.*` cũng có thể quá rộng nếu ứng dụng chỉ cần một vài bảng. Hãy chọn phạm vi hẹp nhất mà ứng dụng vẫn hoạt động ổn định.

## 2. Vì sao phải tách tài khoản quản trị và ứng dụng?

Tài khoản ứng dụng được sử dụng tự động, thường xuyên và có thể được mở từ nhiều instance trong một cụm triển khai. Tài khoản quản trị được dùng bởi người có trách nhiệm vận hành, thường để tạo account, thay đổi cấu trúc, xử lý sự cố hoặc điều chỉnh cấu hình. Hai loại công việc này có mức độ rủi ro và nhu cầu quyền rất khác nhau.

Nếu ứng dụng chạy bằng `root` hoặc một account có quyền toàn cục, lỗi SQL injection, lộ secret hay lỗi trong mã ứng dụng có thể dẫn đến thay đổi schema, xóa dữ liệu hoặc tạo thêm account. Nếu ứng dụng dùng account riêng với quyền DML giới hạn, phạm vi thiệt hại thường nhỏ hơn và dễ điều tra hơn.

Một mô hình phân tách thường gặp:

| Danh tính | Người hoặc tiến trình sử dụng | Quyền điển hình |
|---|---|---|
| `dba_operator` | DBA hoặc người trực vận hành | Quyền quản trị cần thiết theo nhiệm vụ; dùng khi thao tác có kiểm soát |
| `orders_app` | Tiến trình ứng dụng lúc chạy | `SELECT`, `INSERT`, `UPDATE`, `DELETE` trên schema hoặc bảng cần thiết |
| `orders_migrator` | Pipeline triển khai hoặc công cụ migration | Chỉ các quyền DDL cần cho phiên triển khai; không dùng cho traffic thường ngày |
| `orders_report` | Dịch vụ báo cáo | Thường chỉ `SELECT` trên view hoặc bảng báo cáo |
| Tài khoản backup/monitoring | Công cụ sao lưu hoặc giám sát | Quyền tối thiểu theo công cụ, phiên bản MySQL và phương pháp vận hành đã chọn |

Không dùng chung một account cho người quản trị, ứng dụng và pipeline triển khai. Account riêng giúp truy vết hoạt động, thay secret độc lập và khóa đúng thành phần khi có sự cố.

## 3. Tạo tài khoản ứng dụng với quyền DML cần thiết

Giả sử schema `orders` chứa dữ liệu đơn hàng và ứng dụng chạy từ máy `10.20.30.15`. Tài khoản chạy ứng dụng chỉ cần đọc và cập nhật dữ liệu trong schema này.

```sql
CREATE USER 'orders_app'@'10.20.30.15'
  IDENTIFIED BY '<secret-from-secret-manager>'
  REQUIRE SSL;

GRANT SELECT, INSERT, UPDATE, DELETE
  ON orders.*
  TO 'orders_app'@'10.20.30.15';
```

Thay chuỗi giữ chỗ bằng secret được tạo và lưu trong hệ thống quản lý bí mật của môi trường. Không đưa mật khẩu thật vào mã nguồn, Git, log hoặc tài liệu. `REQUIRE SSL` yêu cầu kết nối của account dùng TLS; máy chủ và client phải được cấu hình TLS tương ứng trước khi bật yêu cầu này trong môi trường thật.

Ví dụ trên cho phép các thao tác dữ liệu thông thường nhưng không cấp quyền tạo bảng, sửa cấu trúc, xóa schema, tạo account hay cấp quyền cho người khác. Nếu ứng dụng chỉ đọc dữ liệu, hãy bỏ `INSERT`, `UPDATE` và `DELETE`. Nếu ứng dụng chỉ truy cập một số bảng, thay `orders.*` bằng từng đối tượng cần dùng, chẳng hạn `orders.order_header` hoặc `orders.order_item`.

Một dịch vụ báo cáo có thể dùng account riêng:

```sql
CREATE USER 'orders_report'@'10.20.30.25'
  IDENTIFIED BY '<report-secret-from-secret-manager>'
  REQUIRE SSL;

GRANT SELECT
  ON orders.v_order_summary
  TO 'orders_report'@'10.20.30.25';
```

Trong ví dụ này, account báo cáo chỉ đọc một view đã chọn. View có thể chỉ đưa ra những cột và bản ghi cần thiết cho báo cáo, giúp giảm việc cấp quyền trực tiếp trên bảng chứa dữ liệu nhạy cảm.

## 4. Tách quyền triển khai schema khỏi quyền chạy ứng dụng

Các công cụ migration có thể cần `CREATE`, `ALTER` hoặc `INDEX` để tạo và cập nhật cấu trúc bảng. Những quyền này thường không cần thiết sau khi triển khai xong. Hãy tạo account riêng cho pipeline và chỉ cấp các quyền DDL mà migration thực sự sử dụng.

```sql
CREATE USER 'orders_migrator'@'10.20.30.40'
  IDENTIFIED BY '<deployment-secret-from-secret-manager>'
  REQUIRE SSL;

GRANT CREATE, ALTER, INDEX
  ON orders.*
  TO 'orders_migrator'@'10.20.30.40';
```

Đây là ví dụ tối thiểu; tập quyền chính xác phụ thuộc vào migration. Chỉ thêm `DROP`, `CREATE VIEW`, `TRIGGER`, `CREATE ROUTINE` hoặc quyền khác khi đã xác nhận migration cần chúng. Không cấu hình ứng dụng thường ngày dùng account migration. Sau đợt triển khai, có thể thu hồi các quyền DDL tạm thời hoặc khóa account theo quy trình vận hành.

Tài khoản DBA cũng cần được quản lý riêng. Không nên dùng `GRANT ALL PRIVILEGES ON *.*` hoặc `WITH GRANT OPTION` như một cách cấp quyền mặc định. Hãy cấp quyền quản trị theo vai trò công việc, giới hạn người được sử dụng, yêu cầu xác thực mạnh và bảo vệ đường kết nối quản trị. Quyền có thể tạo account hoặc cấp quyền cho account khác cần được kiểm soát đặc biệt.

## 5. Dùng role để quản lý quyền nhất quán

Trên MySQL 8.0 trở lên, **role** là một tập quyền có tên. Bạn có thể cấp cùng một role cho nhiều account thay vì lặp lại danh sách quyền cho từng người dùng. Khi thay đổi quyền trong role, các account được gán role sẽ nhận thay đổi theo cơ chế kích hoạt role của MySQL.

Ví dụ tạo role cho ứng dụng có quyền đọc và ghi:

```sql
CREATE ROLE 'orders_runtime_rw'@'%';

GRANT SELECT, INSERT, UPDATE, DELETE
  ON orders.*
  TO 'orders_runtime_rw'@'%';

GRANT 'orders_runtime_rw'@'%'
  TO 'orders_app'@'10.20.30.15';

SET DEFAULT ROLE 'orders_runtime_rw'@'%'
  TO 'orders_app'@'10.20.30.15';
```

Role ở đây đại diện cho tập quyền; account đăng nhập thực tế vẫn là `'orders_app'@'10.20.30.15'`. Lệnh `SET DEFAULT ROLE` giúp role được kích hoạt mặc định khi account đăng nhập. Nếu role đã được gán nhưng không phải role mặc định, hãy kiểm tra cấu hình kích hoạt role hoặc kích hoạt role trong session theo thiết kế của hệ thống.

Role hữu ích khi có nhiều instance hoặc nhiều dịch vụ cần cùng một bộ quyền. Tuy nhiên, role không thay thế việc thiết kế phạm vi quyền: một role chứa quyền quá rộng vẫn tạo ra rủi ro cho tất cả account được gán role đó. Với phiên bản MySQL chưa hỗ trợ role, có thể cấp quyền trực tiếp cho từng account và quản lý thay đổi bằng quy trình kiểm soát phiên bản.

## 6. Kiểm tra account và quyền thực tế

Sau khi tạo account, hãy kết nối bằng chính thông tin đăng nhập của account đó và kiểm tra danh tính mà MySQL nhận diện:

```sql
SELECT USER() AS connection_identity,
       CURRENT_USER() AS privilege_identity;
```

`USER()` cho biết tên người dùng kết nối cùng host nguồn mà máy chủ nhìn thấy. `CURRENT_USER()` cho biết account MySQL đã khớp để xác thực và áp dụng quyền. Hai giá trị có thể khác nhau do quy tắc khớp account theo host. Khi chẩn đoán lỗi quyền, `CURRENT_USER()` đặc biệt hữu ích để tránh kiểm tra nhầm account.

DBA có thể xem quyền đã cấp bằng:

```sql
SHOW GRANTS FOR 'orders_app'@'10.20.30.15';
SHOW GRANTS FOR 'orders_report'@'10.20.30.25';
```

Nếu dùng role, kiểm tra cả role được gán và các quyền trong role. Có thể xem quyền của account cùng role cụ thể bằng lệnh `SHOW GRANTS FOR 'orders_app'@'10.20.30.15' USING 'orders_runtime_rw'@'%';`. Việc kiểm tra cần bao gồm quyền trực tiếp, role mặc định, phạm vi schema/bảng và quyền phát sinh từ view hoặc routine.

Thực hiện cả kiểm tra dương và kiểm tra âm:

1. Đăng nhập bằng `orders_app` và chạy các thao tác mà ứng dụng cần, ví dụ đọc và cập nhật một bản ghi thử nghiệm.
2. Thử một thao tác ngoài phạm vi, chẳng hạn `CREATE TABLE` trong schema `orders`; thao tác này phải bị từ chối nếu account không được cấp quyền DDL.
3. Đăng nhập bằng `orders_report`, xác nhận có thể đọc view báo cáo và không thể ghi dữ liệu.
4. Xác nhận ứng dụng và pipeline đang dùng đúng account, không vô tình dùng account DBA qua cấu hình môi trường.

Không chỉ dựa vào việc câu lệnh `GRANT` đã chạy thành công. Quyền hiệu lực còn phụ thuộc account thực tế được chọn, role được kích hoạt, đối tượng truy cập và các cơ chế như view hoặc stored routine.

## 7. Thu hồi quyền và xử lý account không còn cần thiết

Khi một tác vụ kết thúc hoặc quyền không còn cần thiết, thu hồi quyền tương ứng:

```sql
REVOKE CREATE, ALTER, INDEX
  ON orders.*
  FROM 'orders_migrator'@'10.20.30.40';
```

Nếu cần ngăn account đăng nhập mới trong lúc điều tra, MySQL 8.0 hỗ trợ khóa account:

```sql
ALTER USER 'orders_app'@'10.20.30.15' ACCOUNT LOCK;
```

Khóa account ngăn các kết nối mới; các session đang hoạt động cần được kiểm tra và ngắt riêng nếu quy trình ứng phó sự cố yêu cầu. Khi account không còn được sử dụng, có thể xóa bằng `DROP USER` sau khi xác nhận không còn phụ thuộc vận hành. Nếu account được gán role, có thể thu hồi role bằng `REVOKE role_name FROM user_name`.

Các câu lệnh quản lý account như `CREATE USER`, `GRANT`, `REVOKE`, `ALTER USER` và `DROP USER` tự cập nhật thông tin quyền của MySQL. Không cần chạy `FLUSH PRIVILEGES` sau các câu lệnh này. Tránh chỉnh sửa trực tiếp các bảng hệ thống như `mysql.user`; hãy dùng câu lệnh quản trị được MySQL cung cấp để giữ trạng thái quyền nhất quán.

## 8. Những lỗi thiết kế thường gặp

- **Dùng `root` trong cấu hình ứng dụng:** một lỗi ở ứng dụng có thể ảnh hưởng toàn máy chủ. Tạo account runtime riêng.
- **Cấp `ALL PRIVILEGES` hoặc quyền trên `*.*` cho dịch vụ:** phạm vi quá rộng so với nhiệm vụ. Chọn quyền và schema cụ thể.
- **Dùng chung account cho ứng dụng và migration:** ứng dụng có thể giữ quyền DDL trong suốt thời gian chạy. Tách account theo vòng đời sử dụng.
- **Cho phép kết nối từ mọi host mà không có lý do:** account có thể được dùng từ nguồn ngoài dự kiến. Giới hạn host và kết hợp firewall/network policy.
- **Quên kích hoạt role mặc định:** role đã gán nhưng quyền không xuất hiện trong session như mong đợi. Kiểm tra `SET DEFAULT ROLE` và session hiện tại.
- **Lưu mật khẩu trong repository hoặc log:** secret dễ bị sao chép và tồn tại lâu sau khi bị lộ. Dùng secret manager, giới hạn người đọc và có lịch xoay vòng.
- **Chỉ kiểm tra quyền trực tiếp:** view, stored procedure, function và `DEFINER` có thể tạo đường truy cập gián tiếp. Kiểm tra cả quyền thực thi và ngữ cảnh bảo mật của đối tượng đó.
- **Không thu hồi quyền tạm thời:** account triển khai hoặc hỗ trợ có thể giữ quyền cao lâu hơn cần thiết. Đưa việc thu hồi vào quy trình sau triển khai.

## 9. Quy trình áp dụng trong dự án

Khi đưa một dịch vụ mới vào MySQL, có thể áp dụng quy trình sau:

1. Liệt kê các câu lệnh và đối tượng dữ liệu mà dịch vụ cần trong từng luồng nghiệp vụ.
2. Phân loại account theo mục đích: runtime, báo cáo, migration, backup, monitoring và quản trị.
3. Chọn host nguồn, yêu cầu TLS và phạm vi schema/bảng cho từng account.
4. Tạo account và cấp quyền trực tiếp hoặc qua role; lưu secret trong hệ thống quản lý bí mật.
5. Kiểm tra `CURRENT_USER()` và `SHOW GRANTS`, sau đó chạy cả thao tác được phép lẫn thao tác phải bị từ chối.
6. Theo dõi việc sử dụng account, xoay vòng secret, rà soát quyền định kỳ và thu hồi account/quyền không còn cần thiết.

Với account backup và monitoring, không sao chép quyền của DBA một cách máy móc. Quyền cần thiết phụ thuộc công cụ, phiên bản MySQL, storage engine và lựa chọn nhất quán dữ liệu. Hãy xác định rõ chức năng mà công cụ sử dụng, thử nghiệm trong môi trường tương đương production và chỉ cấp quyền đã được xác minh.

## 10. Bài tập thực hành

Trên một môi trường MySQL thử nghiệm, tạo schema `orders` và ba account riêng: `orders_app`, `orders_report`, `orders_migrator`. Dùng các địa chỉ host thử nghiệm phù hợp với máy kết nối của bạn.

- Cấp cho `orders_app` quyền đọc và ghi trên các bảng nghiệp vụ cần thiết.
- Cấp cho `orders_report` quyền `SELECT` trên một view tổng hợp.
- Cấp cho `orders_migrator` quyền DDL cần thiết để tạo hoặc thay đổi bảng.
- Dùng `SELECT USER(), CURRENT_USER()` và `SHOW GRANTS` để xác nhận danh tính và quyền.
- Thử thao tác hợp lệ và không hợp lệ bằng từng account; ghi lại kết quả mong đợi và kết quả thực tế.
- Thu hồi quyền DDL của `orders_migrator`, khóa một account thử nghiệm rồi xác nhận account đó không thể tạo kết nối mới.

**Tiêu chí hoàn thành:** mỗi account thực hiện được nhiệm vụ của mình, các thao tác vượt quyền bị từ chối, ứng dụng không cần account quản trị, và bạn có thể giải thích vì sao từng quyền được cấp ở phạm vi đó.

## Kết luận

Quyền tối thiểu giúp thu hẹp phạm vi tác động khi có lỗi hoặc sự cố bảo mật. Tách account runtime, migration, báo cáo và quản trị giúp mỗi tiến trình chỉ có năng lực cần thiết cho nhiệm vụ của nó. Trong MySQL, hãy quản lý account theo cặp user/host, cấp quyền ở phạm vi hẹp, dùng role khi cần chuẩn hóa tập quyền, và luôn kiểm chứng quyền thực tế bằng account đang sử dụng.
