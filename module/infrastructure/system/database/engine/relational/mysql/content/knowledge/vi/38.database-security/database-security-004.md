# Authentication plugin, `caching_sha2_password` và tương thích driver

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của authentication plugin trong MySQL và phân biệt xác thực với phân quyền.
- Mô tả hai nhánh xác thực nhanh và xác thực đầy đủ của `caching_sha2_password`.
- Kiểm tra plugin đang gắn với tài khoản, chuyển tài khoản sang plugin phù hợp và kiểm tra kết nối an toàn.
- Chẩn đoán lỗi tương thích giữa MySQL Server, driver, ứng dụng và proxy.
- Lập kế hoạch nâng cấp driver và chuyển đổi plugin mà không làm gián đoạn dịch vụ ngoài dự kiến.

## 1. Authentication plugin giải quyết việc gì?

Khi một ứng dụng mở kết nối đến MySQL, máy chủ phải xác minh danh tính của tài khoản trước khi cho phép phiên làm việc được thiết lập. MySQL giao phần xác minh này cho **authentication plugin**. Plugin xác định cách máy khách chứng minh rằng nó biết thông tin xác thực của tài khoản, chẳng hạn mật khẩu.

Authentication plugin không quyết định tài khoản được đọc hoặc sửa bảng nào. Đó là nhiệm vụ của hệ thống quyền (`GRANT`, `REVOKE`, role). Một kết nối có thể xác thực thành công nhưng vẫn nhận lỗi `Access denied` khi truy cập dữ liệu vì thiếu quyền; ngược lại, tài khoản có đủ quyền cũng không thể sử dụng nếu quá trình xác thực thất bại.

MySQL nhận diện tài khoản bằng cặp `user` và `host`, ví dụ `'app_user'@'10.%'`. Plugin được gắn với từng tài khoản. Vì vậy, cùng một tên người dùng ở hai giá trị `host` khác nhau có thể có cấu hình xác thực khác nhau.

Một số plugin thường gặp:

| Plugin | Đặc điểm | Cách sử dụng |
|---|---|---|
| `caching_sha2_password` | Plugin dựa trên SHA-256, có cơ chế xác thực nhanh nhờ bộ nhớ đệm và cơ chế xác thực đầy đủ khi cần | Lựa chọn mặc định được khuyến nghị trên các phiên bản MySQL hiện đại |
| `mysql_native_password` | Cơ chế xác thực cũ, dựa trên thuật toán băm SHA-1 của MySQL | Chỉ duy trì tạm thời khi còn phụ thuộc hệ thống cũ và có kế hoạch loại bỏ |
| `sha256_password` | Xác thực SHA-256 nhưng không có cơ chế cache xác thực nhanh như `caching_sha2_password` | Chỉ dùng khi có yêu cầu tương thích cụ thể |
| `auth_socket` | Xác thực dựa trên danh tính người dùng hệ điều hành qua socket cục bộ | Phù hợp một số tài khoản quản trị cục bộ trên Linux; không phải lựa chọn chung cho ứng dụng từ xa |

Từ MySQL 8.0, `caching_sha2_password` là plugin xác thực mặc định cho tài khoản mới nếu không chỉ định plugin khác. `mysql_native_password` đã bị đánh dấu lỗi thời từ MySQL 8.0.34, bị tắt mặc định trong MySQL 8.4 và bị loại bỏ trong MySQL 9.0. Do đó, một driver cũ có thể vẫn kết nối được với máy chủ cũ nhưng thất bại sau khi nâng cấp máy chủ hoặc đổi plugin tài khoản.

## 2. Cách `caching_sha2_password` hoạt động

Tên plugin mô tả hai ý chính: xác thực dựa trên SHA-256 và cache giúp rút ngắn một số lần xác thực tiếp theo. Cache không phải query cache và không lưu mật khẩu dạng rõ.

### 2.1. Trao đổi trong quá trình bắt tay

Khi máy khách kết nối, MySQL gửi thông tin plugin và dữ liệu thử thách ngẫu nhiên (challenge/nonce). Driver phải hiểu giao thức của plugin để tạo phản hồi xác thực phù hợp. Nếu driver không hỗ trợ plugin được máy chủ yêu cầu, quá trình bắt tay có thể dừng trước khi ứng dụng gửi truy vấn SQL.

`caching_sha2_password` có hai nhánh:

1. **Xác thực nhanh (fast authentication):** nếu thông tin xác thực cần thiết đã có trong cache của máy chủ, máy khách gửi phản hồi dựa trên challenge. Máy chủ xác minh phản hồi và hoàn tất xác thực mà không cần thực hiện trao đổi mật khẩu đầy đủ.
2. **Xác thực đầy đủ (full authentication):** nếu cache chưa có thông tin phù hợp, chẳng hạn lần đầu tài khoản kết nối sau khi cache được làm mới, hai bên chuyển sang bước xác thực đầy đủ. Bước này cần một kênh truyền an toàn hoặc cơ chế mã hóa RSA.

Cache nằm trong bộ nhớ của máy chủ. Nó có thể bị làm mới khi máy chủ khởi động lại hoặc khi thông tin xác thực của tài khoản thay đổi. Vì vậy, một driver chỉ hoạt động được trong trường hợp cache đã có sẵn vẫn có thể thất bại khi kết nối đầu tiên sau triển khai hoặc sau khi máy chủ khởi động lại.

### 2.2. Xác thực đầy đủ qua TLS hoặc RSA

Trong xác thực đầy đủ, máy khách phải chuyển mật khẩu đến máy chủ theo cách được bảo vệ:

- **Qua TLS:** mật khẩu được gửi bên trong kết nối TLS. Đây là phương án nên dùng cho ứng dụng kết nối qua mạng. Cấu hình máy khách để kiểm tra chứng chỉ máy chủ và tên máy chủ, ví dụ chế độ `VERIFY_IDENTITY` của MySQL client hoặc Connector/J.
- **Qua RSA khi không có TLS:** máy khách dùng khóa công khai RSA của máy chủ để mã hóa mật khẩu trước khi gửi. Khóa công khai có thể được cấu hình sẵn ở máy khách hoặc được lấy từ máy chủ theo cơ chế của driver.

Việc tự động lấy khóa công khai qua một kết nối không được xác thực có thể mở ra nguy cơ máy chủ giả mạo hoặc tấn công xen giữa. Trong môi trường production, hãy ưu tiên TLS có xác minh chứng chỉ. Nếu bắt buộc dùng RSA mà không dùng TLS, hãy phân phối và ghim khóa công khai đáng tin cậy theo tài liệu của driver.

`caching_sha2_password` không có nghĩa là máy chủ gửi mật khẩu đã băm để ứng dụng tự so sánh. Máy khách và máy chủ phải triển khai đúng giao thức challenge-response, nhánh xác thực nhanh và nhánh xác thực đầy đủ. Vì vậy, chỉ thay đổi một tham số chuỗi kết nối không thể biến một driver không hỗ trợ plugin thành driver tương thích.

## 3. Kiểm tra plugin và tài khoản trên máy chủ

Trước khi thay đổi cấu hình, hãy xác định phiên bản máy chủ và plugin đang gắn với các tài khoản ứng dụng. Thực hiện bằng một tài khoản quản trị có quyền xem thông tin hệ thống.

```sql
SELECT VERSION() AS mysql_version;

SELECT user, host, plugin, account_locked
FROM mysql.user
ORDER BY user, host;
```

Trên MySQL 8.x, `mysql.user` là view của thông tin tài khoản trong hệ thống quyền. Nếu không muốn truy vấn trực tiếp view này hoặc chỉ cần kiểm tra một tài khoản, có thể dùng:

```sql
SHOW CREATE USER 'app_user'@'10.%';
```

Lệnh `SHOW CREATE USER` có thể hiển thị thông tin xác thực đã băm và thuộc tính tài khoản. Không đưa nguyên kết quả vào ticket công khai, log ứng dụng hoặc tài liệu chia sẻ; hãy che phần thông tin xác thực trước khi gửi cho người khác.

Đừng chỉ kiểm tra tài khoản đăng nhập tương tác. Hãy lập danh sách tất cả tài khoản được dùng bởi API, worker nền, tác vụ định kỳ, công cụ migration, công cụ backup, giám sát, BI và các dịch vụ trung gian. Một hệ thống có thể có nhiều đường kết nối sử dụng driver hoặc thư viện khác nhau.

## 4. Tạo và chuyển tài khoản sang `caching_sha2_password`

### 4.1. Tạo tài khoản mới

Ví dụ tạo một tài khoản ứng dụng chỉ có quyền thao tác trên schema `sales_app`:

```sql
CREATE USER 'sales_app'@'10.%'
  IDENTIFIED WITH caching_sha2_password BY 'REPLACE_WITH_A_UNIQUE_SECRET'
  REQUIRE SSL;

GRANT SELECT, INSERT, UPDATE, DELETE
  ON sales_app.*
  TO 'sales_app'@'10.%';
```

Thay chuỗi mẫu bằng mật khẩu mạnh được cấp từ hệ thống quản lý bí mật. Không dùng nguyên chuỗi mẫu trong môi trường thật. Phạm vi host `10.%` chỉ là ví dụ; hãy giới hạn host hoặc dải mạng theo kiến trúc thực tế. `REQUIRE SSL` yêu cầu tài khoản kết nối qua TLS, còn việc xác minh chứng chỉ máy chủ vẫn phải được cấu hình ở phía máy khách.

### 4.2. Chuyển tài khoản hiện có

Sau khi đã xác nhận mọi ứng dụng sử dụng tài khoản có driver tương thích, có thể chuyển plugin bằng `ALTER USER`:

```sql
ALTER USER 'legacy_app'@'10.%'
  IDENTIFIED WITH caching_sha2_password BY 'REPLACE_WITH_A_NEW_SECRET'
  REQUIRE SSL;
```

Lệnh này thay đổi phương thức xác thực và đặt lại mật khẩu theo giá trị mới. Hãy cập nhật bí mật tương ứng trong secret manager hoặc nơi cấp cấu hình cho ứng dụng theo quy trình triển khai của hệ thống. Nếu tài khoản đang được dùng bởi nhiều dịch vụ, cần xác định đầy đủ các bên tiêu thụ trước khi đổi.

Các lệnh `CREATE USER` và `ALTER USER` cập nhật trực tiếp dữ liệu quyền; không cần chạy `FLUSH PRIVILEGES` sau các lệnh này. Việc thay đổi plugin có hiệu lực với các lần xác thực kết nối mới. Những phiên đã thiết lập trước đó thường tiếp tục tồn tại cho đến khi đóng, vì vậy cần chủ động tạo kết nối mới để kiểm chứng cấu hình.

### 4.3. Kiểm tra quyền riêng với xác thực

Sau khi tạo hoặc chuyển tài khoản, kiểm tra quyền đã cấp:

```sql
SHOW GRANTS FOR 'sales_app'@'10.%';
```

Nếu kết nối thành công nhưng truy vấn bị từ chối, hãy xem quyền và role trước khi thay đổi plugin. Không giải quyết lỗi phân quyền bằng cách cấp `GRANT ALL` hoặc chuyển ứng dụng sang tài khoản quản trị.

## 5. Tương thích driver và các thành phần kết nối

Tương thích cần được xác minh ở toàn bộ đường đi của kết nối, không chỉ ở MySQL Server. Các thành phần có thể tham gia gồm thư viện client, driver của ngôn ngữ, ORM, connection pool, proxy và công cụ vận hành.

| Thành phần | Điều cần kiểm tra |
|---|---|
| MySQL command-line client | Dùng bản client đủ mới để hỗ trợ plugin của máy chủ; kiểm tra tùy chọn TLS và xác thực đầy đủ |
| MySQL Connector/J | Dùng phiên bản hỗ trợ `caching_sha2_password`; cấu hình trust store/CA và xác minh tên máy chủ khi dùng TLS |
| MySQL Connector/Python | Cập nhật connector tương thích với phiên bản máy chủ; bật xác minh chứng chỉ và danh tính máy chủ |
| PHP `mysqli` / PDO MySQL | Xác định PHP đang dùng `mysqlnd` hay `libmysqlclient`, phiên bản thư viện được build cùng PHP và khả năng hỗ trợ plugin |
| Node.js driver | Kiểm tra phiên bản package và hỗ trợ giao thức xác thực; xác minh cả cấu hình TLS của pool |
| Go driver, ORM và framework | Kiểm tra driver MySQL nền mà framework thực sự sử dụng; ORM không tự bổ sung hỗ trợ plugin nếu driver chưa có |
| Proxy hoặc dịch vụ quản lý kết nối | Xác nhận proxy hỗ trợ chuyển tiếp đầy đủ quá trình xác thực và không thay đổi phương thức xác thực giữa client và server |

Không suy ra khả năng tương thích chỉ từ tên ngôn ngữ hoặc ORM. Hai ứng dụng Java có thể dùng hai phiên bản Connector/J khác nhau; một ứng dụng PHP có thể được build với các thư viện client khác nhau. Hãy ghi lại phiên bản thực tế trong môi trường chạy.

Với MySQL Connector/J, ví dụ URL kết nối có bật TLS và xác minh danh tính máy chủ:

```text
jdbc:mysql://db.example.internal:3306/sales_app?sslMode=VERIFY_IDENTITY
```

Máy chạy ứng dụng phải tin cậy CA ký chứng chỉ của máy chủ (qua trust store phù hợp), và tên trong chứng chỉ phải khớp hostname `db.example.internal`. Nếu dùng chứng chỉ nội bộ, hãy cài CA nội bộ vào trust store thay vì tắt xác minh chứng chỉ.

Với MySQL command-line client, có thể kiểm tra kết nối bằng:

```bash
mysql --host=db.example.internal \
      --user=sales_app \
      --password \
      --ssl-mode=VERIFY_IDENTITY \
      --ssl-ca=/path/to/company-ca.pem \
      sales_app
```

Tùy chọn `--password` không kèm giá trị để client hỏi mật khẩu tương tác, tránh đặt mật khẩu trực tiếp trong lịch sử shell hoặc danh sách tiến trình. Đường dẫn CA và hostname trong ví dụ cần được thay bằng cấu hình thật.

Sau khi kết nối, kiểm tra phiên hiện tại có sử dụng TLS hay không:

```sql
SHOW SESSION STATUS LIKE 'Ssl_cipher';
```

Giá trị `Ssl_cipher` không rỗng cho biết phiên đang dùng mã hóa TLS. Kết quả này xác nhận mã hóa đường truyền; việc xác minh danh tính máy chủ còn phụ thuộc cấu hình phía client.

## 6. Quy trình kiểm thử trước khi triển khai

Một bài kiểm thử chỉ chạy được câu `SELECT 1` chưa đủ để xác nhận tương thích. Hãy kiểm tra cả các đường kết nối và tình huống xác thực đầy đủ.

1. **Kiểm kê:** ghi lại phiên bản MySQL Server, plugin của từng tài khoản và phiên bản driver thực tế của từng ứng dụng, tác vụ, công cụ và proxy.
2. **Nâng cấp driver ở môi trường thử nghiệm:** cập nhật thư viện trước khi chuyển plugin tài khoản. Chạy thử với đúng phiên bản runtime, cấu hình TLS, connection pool và proxy như production.
3. **Kiểm tra kết nối lạnh:** dùng một tài khoản thử nghiệm mới hoặc tài khoản thử nghiệm vừa đổi mật khẩu để kiểm tra lần xác thực đầu tiên, khi cache chưa có thông tin phù hợp. Không chỉ kiểm tra các kết nối đã được pool tái sử dụng.
4. **Kiểm tra vòng đời kết nối:** đóng và mở lại pool, khởi động lại ứng dụng thử nghiệm và xác nhận kết nối mới vẫn thành công. Nếu quy trình vận hành có restart MySQL, hãy kiểm thử kịch bản cache được làm mới trong môi trường staging.
5. **Kiểm tra chức năng:** chạy migration, truy vấn đọc/ghi đại diện, transaction, job nền, backup, restore thử nghiệm và health check. Xác nhận không có thành phần nào âm thầm dùng một driver cũ.
6. **Kiểm tra bảo mật:** xác nhận TLS được sử dụng, client kiểm tra chứng chỉ và tài khoản có quyền tối thiểu cần thiết.
7. **Triển khai theo đợt:** chuyển từng nhóm tài khoản hoặc dịch vụ, theo dõi lỗi xác thực và khả năng mở kết nối mới trước khi chuyển nhóm tiếp theo.

Nên có tài khoản thử nghiệm riêng cho từng loại driver hoặc ứng dụng. Việc dùng chung một tài khoản kiểm thử có thể che khuất khác biệt về host matching, cấu hình TLS hoặc quyền truy cập.

## 7. Chẩn đoán lỗi thường gặp

| Thông báo hoặc biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `Authentication plugin 'caching_sha2_password' cannot be loaded` | Client quá cũ, thiếu plugin phía client hoặc đang nạp thư viện không tương thích | Xác định chính xác thư viện client được ứng dụng nạp; nâng cấp driver/client lên bản hỗ trợ plugin |
| `Client does not support authentication protocol requested by server` | Driver hoặc proxy không hiểu plugin máy chủ yêu cầu | Kiểm tra phiên bản driver và proxy; thử kết nối trực tiếp đến MySQL bằng client mới để khoanh vùng |
| `Public Key Retrieval is not allowed` | Driver không có khóa RSA đã cấu hình và không cho phép tự lấy khóa công khai | Ưu tiên bật TLS và xác minh chứng chỉ; nếu không thể dùng TLS, cấu hình khóa công khai đáng tin cậy theo tài liệu driver |
| `Authentication requires secure connection` hoặc lỗi tương tự | Xác thực đầy đủ được yêu cầu nhưng kết nối không có TLS và client chưa thiết lập RSA đúng cách | Bật TLS; hoặc cấu hình RSA key exchange an toàn cho client và server |
| Kết nối đang chạy vẫn ổn nhưng kết nối mới thất bại | Ứng dụng còn giữ session cũ; nhánh xác thực đầy đủ chưa được kiểm thử; pool che khuất lỗi | Mở kết nối mới bằng tài khoản thử nghiệm, kiểm tra sau khi cache được làm mới và xem log của driver |
| `Access denied for user` | Sai mật khẩu, sai cặp `user`/`host`, tài khoản bị khóa, hoặc cơ chế xác thực không hoàn tất | Xác minh chính xác tài khoản và host khớp, trạng thái tài khoản, plugin và cấu hình client; sau đó mới kiểm tra quyền SQL |
| Kết nối được nhưng truy vấn nhận `command denied` hoặc `SELECT command denied` | Xác thực thành công nhưng thiếu quyền | Dùng `SHOW GRANTS`, cấp đúng quyền trên đúng schema/bảng; không đổi plugin để xử lý lỗi quyền |
| Chỉ một số instance ứng dụng lỗi | Các instance chạy runtime, driver, secret hoặc cấu hình TLS khác nhau | So sánh phiên bản và cấu hình đã triển khai trên từng instance; kiểm tra cấu hình connection pool và biến môi trường |

Một dấu hiệu chẩn đoán hữu ích là lỗi chỉ xuất hiện khi tạo kết nối mới sau khi restart hoặc sau khi đổi mật khẩu. Trường hợp này thường hướng sự chú ý đến nhánh full authentication, TLS hoặc RSA. Hãy dùng log của client và server để xác nhận, không kết luận chỉ dựa vào thời điểm xảy ra lỗi.

## 8. Lộ trình chuyển đổi từ plugin cũ

Khi một hệ thống còn dùng `mysql_native_password`, hãy xử lý chuyển đổi như một thay đổi tương thích giữa nhiều thành phần:

**Giai đoạn 1 — Lập danh mục phụ thuộc.** Liệt kê tài khoản, host, dịch vụ sử dụng, phiên bản driver, proxy và cách cấp mật khẩu. Đặc biệt tìm các ứng dụng ít được triển khai như job tháng, tác vụ backup và công cụ quản trị.

**Giai đoạn 2 — Nâng cấp client.** Cập nhật driver và runtime trong môi trường thử nghiệm. Cấu hình TLS, CA và xác minh hostname. Đưa các lỗi tương thích vào log hoặc metric để có thể phát hiện trong quá trình rollout.

**Giai đoạn 3 — Thử nghiệm với tài khoản mới.** Tạo tài khoản có `caching_sha2_password`, quyền tối thiểu và yêu cầu TLS. Chạy toàn bộ luồng ứng dụng với tài khoản này, bao gồm kết nối mới sau khi pool được tạo lại.

**Giai đoạn 4 — Chuyển theo từng dịch vụ.** Cập nhật secret và tài khoản theo từng nhóm nhỏ. Theo dõi số lần kết nối thất bại, lỗi xác thực, thời gian mở kết nối và lỗi từ proxy. Chuẩn bị sẵn phương án khôi phục có kiểm soát nếu một thành phần chưa tương thích.

**Giai đoạn 5 — Loại bỏ phụ thuộc cũ.** Sau khi mọi client đã được xác nhận, chuyển nốt tài khoản còn lại, bỏ cấu hình cho phép plugin cũ nếu có và cập nhật tài liệu vận hành. Không giữ một tài khoản dùng chung với quyền rộng chỉ để duy trì tương thích cho một client chưa được nâng cấp.

Không nên bật lại `mysql_native_password` trên toàn máy chủ chỉ để làm cho một ứng dụng cũ tiếp tục hoạt động. Trước hết hãy xác định đúng client gây lỗi và nâng cấp nó. Nếu cần một giai đoạn chuyển tiếp, giới hạn phạm vi tài khoản, mạng và thời gian tồn tại; ghi nhận chủ sở hữu cùng hạn hoàn tất nâng cấp. Với MySQL 8.4, plugin này bị tắt mặc định; với MySQL 9.0, plugin đã bị loại bỏ nên phương án bật lại không còn khả dụng.

## 9. Các nguyên tắc bảo mật khi vận hành

- **Bắt buộc TLS cho kết nối qua mạng:** ưu tiên xác minh CA và hostname ở phía client. Mã hóa mà không xác minh danh tính máy chủ vẫn có thể không bảo vệ được ứng dụng trước máy chủ giả mạo.
- **Không xem `allowPublicKeyRetrieval=true` là giải pháp production mặc định:** tùy chọn này có thể giúp một số driver lấy khóa RSA khi không có TLS, nhưng cần đánh giá rủi ro tin cậy khóa. Hãy ưu tiên TLS hoặc khóa công khai được phân phối đáng tin cậy.
- **Quản lý mật khẩu ngoài mã nguồn:** dùng secret manager, giới hạn người có quyền đọc bí mật và có quy trình xoay vòng. Không ghi mật khẩu vào URL kết nối, log, shell history hoặc kho mã.
- **Giới hạn quyền và nguồn kết nối:** dùng tài khoản riêng cho từng ứng dụng hoặc vai trò, giới hạn host, cấp quyền tối thiểu và khóa tài khoản không còn sử dụng.
- **Theo dõi khả năng mở kết nối mới:** connection pool có thể che giấu lỗi xác thực trong thời gian dài. Health check nên có cơ chế phát hiện việc tạo kết nối mới và cảnh báo lỗi xác thực.
- **Bảo vệ thông tin chẩn đoán:** kết quả `SHOW CREATE USER`, log bắt tay và cấu hình kết nối có thể chứa thông tin nhạy cảm. Che dữ liệu trước khi chia sẻ.

## 10. Tình huống thực hành

Một dịch vụ bán hàng chạy trên MySQL 8.0. Ứng dụng chính vẫn hoạt động, nhưng sau khi tạo một instance mới, instance đó báo `Public Key Retrieval is not allowed`. Tài khoản `sales_app` đã được chuyển sang `caching_sha2_password`. Một job backup chạy trên máy khác vẫn dùng một client cũ.

Hãy xử lý theo thứ tự:

1. Trên MySQL, xác nhận phiên bản máy chủ và plugin của đúng tài khoản `sales_app` cùng tài khoản backup. Kiểm tra cặp `user`/`host`, vì hai dịch vụ có thể khớp hai tài khoản khác nhau.
2. Trên instance mới, ghi nhận phiên bản driver thực tế và cấu hình TLS. Không vội bật `allowPublicKeyRetrieval=true` để bỏ qua lỗi.
3. Cấu hình CA tin cậy và xác minh hostname, sau đó mở kết nối mới. Nếu kiến trúc chưa thể dùng TLS, đánh giá phương án phân phối khóa RSA công khai đáng tin cậy theo driver.
4. Nâng cấp client của job backup trong môi trường thử nghiệm; chạy backup và restore thử nghiệm để xác nhận toàn bộ luồng.
5. Chỉ sau khi mọi client đã vượt qua kiểm thử kết nối lạnh, chức năng và bảo mật mới hoàn tất chuyển đổi.

**Câu hỏi tự kiểm tra:**

1. Vì sao ứng dụng có thể kết nối thành công trước khi restart MySQL nhưng thất bại khi mở kết nối mới sau restart?
2. `caching_sha2_password` dùng TLS và RSA trong những tình huống nào? Vì sao xác minh chứng chỉ quan trọng?
3. Khi kết nối thành công nhưng truy vấn bị từ chối, bạn cần kiểm tra plugin hay `SHOW GRANTS` trước? Giải thích.
4. Ngoài ứng dụng chính, những client nào cần được kiểm thử trước khi chuyển tài khoản sang plugin mới?
5. Vì sao không nên bật `mysql_native_password` trên toàn máy chủ chỉ để hỗ trợ một driver cũ?

## Kết luận

`caching_sha2_password` là lựa chọn xác thực phù hợp cho các phiên bản MySQL hiện đại. Để sử dụng ổn định, máy chủ, driver và các thành phần trung gian phải cùng hỗ trợ giao thức; nhánh xác thực đầy đủ cần TLS hoặc cấu hình RSA đáng tin cậy. Hãy kiểm kê mọi client, thử nghiệm kết nối mới trong môi trường staging, chuyển đổi từng nhóm tài khoản và xác minh lại quyền SQL cũng như bảo mật đường truyền sau triển khai.
