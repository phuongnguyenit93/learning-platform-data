# Xác thực mật khẩu SCRAM và quản lý thông tin bí mật

Khi một ứng dụng Java kết nối PostgreSQL, nó thường phải chứng minh danh tính qua một vai trò đăng nhập (*login role*) và một phương thức xác thực được server lựa chọn. Trong các môi trường sử dụng mật khẩu, **SCRAM-SHA-256** là cơ chế xác thực hiện đại của PostgreSQL, được thiết kế để không phải truyền mật khẩu gốc trực tiếp qua giao thức khi xác thực, đồng thời cho phép server lưu **password verifier** đã được dẫn xuất từ mật khẩu thay vì lưu mật khẩu dạng rõ.

Tuy nhiên, chuyển từ `md5</BT> sang `scram-sha-256</BT> **không tự động biến một hệ thống thành an toàn**. Một cấu hình tốt cần đồng thời xem xét **TLS**, kiểm tra danh tính server, `pg_hba.conf</BT>, độ mạnh mật khẩu, quyền role, cách đưa secret vào ứng dụng, vòng đời xoay vòng thông tin xác thực, connection pooling, logs, backups và cách xử lý khi secret bị lộ.

Ví dụ, một hệ thống có thể dùng SCRAM nhưng vẫn gặp rủi ro nếu mật khẩu được hard-code trong repository, xuất hiện trong JDBC URL được log, hoặc dùng chung một database superuser cho mọi microservice. Ngược lại, một ứng dụng quản lý secret tốt nhưng cấu hình `pg_hba.conf</BT> sai có thể cho phép kết nối bằng phương thức không mong muốn.

Bài học thuộc chương **Bảo mật** của module *Database Engine Relational PostgreSQL*. Mục tiêu là hiểu SCRAM đúng bản chất, cấu hình kết nối mật khẩu một cách an toàn, xây dựng quy trình quản lý bí mật và biết cách kiểm tra các lỗi triển khai thường gặp.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **authentication**, **authorization** và **transport security**.
2. Giải thích cơ chế challenge–response của SCRAM-SHA-256 ở mức khái niệm.
3. Hiểu vì sao PostgreSQL lưu verifier chứ không cần lưu mật khẩu gốc để xác thực SCRAM.
4. Phân biệt SCRAM-SHA-256 với SCRAM-SHA-256-PLUS và TLS channel binding.
5. Dùng `password_encryption</BT> và `pg_hba.conf</BT> đúng phạm vi tác dụng.
6. Tạo login role có quyền tối thiểu và đặt mật khẩu bằng công cụ tránh để lộ trong lịch sử SQL.
7. Hiểu cách `libpq</BT>, `psql</BT>, JDBC và connection pool sử dụng secret.
8. Biết những phương pháp dễ làm lộ mật khẩu: source code, command line, connection URI, environment variables, logs và CI artifacts.
9. Thiết kế quy trình **secret rotation**, thay đổi quyền, vô hiệu hóa tài khoản và thu hồi phiên kết nối.
10. Đọc những trạng thái có thể kiểm tra một cách an toàn mà không xuất password verifier.
11. Xử lý lỗi xác thực SCRAM, TLS, role, cơ sở dữ liệu và quyền truy cập.
12. Lựa chọn thời điểm nên dùng SCRAM thay vì các cơ chế danh tính khác.

## 2. Ba lớp bảo vệ khác nhau

~~~text
Ứng dụng / psql / JDBC
          |
          v
 [1] TRANSPORT SECURITY
      TLS, CA, hostname verification,
      khả năng channel binding
          |
          v
 [2] AUTHENTICATION
      PostgreSQL role là ai?
      pg_hba.conf chọn phương thức nào?
      SCRAM/password/cert/...
          |
          v
 [3] AUTHORIZATION
      Role có CONNECT database không?
      Có USAGE schema không?
      Có SELECT/INSERT/UPDATE table không?
      Có bị RLS lọc hàng không?
~~~

### 2.1. Authentication: ai đang kết nối?

PostgreSQL kiểm tra client có thể xác thực thành một login role như `app_orders</BT> hay không. SCRAM thuộc **lớp xác thực**.

### 2.2. Authorization: được làm gì?

Dù đã xác thực thành công, role vẫn có thể không có quyền truy cập bảng hoặc function. Quyền được quản lý qua `GRANT</BT>, `REVOKE</BT>, ownership, role membership, RLS và những cơ chế liên quan.

### 2.3. Transport security: dữ liệu đi qua mạng có được bảo vệ không?

TLS giúp mã hóa và xác thực kênh truyền khi được cấu hình, đặc biệt nếu client xác minh chain CA và hostname server. SCRAM **không thay thế TLS** cho traffic SQL và kết quả trả về sau đăng nhập.

### 2.4. Kết luận đầu tiên

Không đồng nhất ba khái niệm:

- **SCRAM đúng** chưa chứng minh đường truyền TLS được xác minh.
- **TLS đúng** chưa chứng minh role chỉ có quyền cần thiết.
- **Role có quyền tối thiểu** chưa giải quyết việc mật khẩu bị lộ trên CI log.

Bảo mật là tổ hợp của cả ba lớp và quy trình vận hành.

## 3. SCRAM là gì?

**SCRAM** là viết tắt của *Salted Challenge Response Authentication Mechanism*. PostgreSQL hỗ trợ cơ chế **SCRAM-SHA-256** cho xác thực mật khẩu.

Ý tưởng tổng quát:

- Client giữ hoặc nhận được mật khẩu từ nơi quản lý secret.
- Server lưu một password verifier được dẫn xuất từ mật khẩu cùng thông số như salt và iteration count.
- Khi kết nối, hai bên thực hiện các bước thách thức–đáp ứng để chứng minh khả năng biết bí mật thích hợp.
- Client **không cần gửi plaintext password trực tiếp** như một thông điệp xác thực dạng rõ.
- Server có thể xác thực client và client có thể kiểm tra bằng chứng server biết dữ liệu xác thực tương ứng.

### 3.1. Vì sao không chỉ gửi password qua TLS?

TLS bảo vệ kênh truyền, còn SCRAM giảm việc truyền password ở dạng rõ trong cơ chế xác thực và dùng verifier có salt/work factor. Hai tầng bổ trợ nhau, không phải lựa chọn loại trừ.

### 3.2. SHA-256 ở đây không phải hash một lần đơn giản

Không nên hình dung database chỉ lưu `SHA256(password)</BT>. SCRAM dùng quá trình dẫn xuất khóa từ mật khẩu với **salt** và số vòng lặp, rồi tính các giá trị verifier phục vụ challenge–response.

### 3.3. Salt dùng để làm gì?

Salt làm hai mật khẩu gốc giống nhau khó tạo ra cùng verifier chỉ vì giống mật khẩu, và hạn chế hiệu quả của những bảng hash dựng sẵn dùng chung. Salt **không thay mật khẩu mạnh**.

### 3.4. Iterations dùng để làm gì?

Quá trình dẫn xuất khóa có work factor, tăng chi phí của việc thử đoán mật khẩu từ dữ liệu bị lộ. Nhưng kẻ tấn công vẫn có thể thử đoán ngoại tuyến nếu có đủ verifier và tài nguyên; vì vậy mật khẩu mạnh và bảo vệ metadata xác thực vẫn rất quan trọng.

## 4. Diễn biến challenge–response ở mức khái niệm

~~~text
CLIENT                                   POSTGRESQL
  |                                           |
  |------ Yêu cầu kết nối, user/db ---------->|
  |                                           |
  |<----- Server chọn SASL mechanisms --------|
  |        SCRAM-SHA-256 [+ PLUS]             |
  |                                           |
  |------ Client-first, nonce --------------->|
  |                                           |
  |<----- Server-first: nonce + salt + i -----|
  |                                           |
  |  Client dẫn xuất khóa từ password         |
  |  Tạo client proof                         |
  |                                           |
  |------ Client-final + proof -------------->|
  |                                           |
  |  Server dùng verifier để xác thực proof   |
  |                                           |
  |<----- Server-final signature -------------|
  |                                           |
  | Client kiểm tra server signature          |
  |                                           |
  |======= Phiên SQL đã xác thực =============|
~~~

Sơ đồ nhằm giúp hiểu các bên trao đổi proof, nonce, salt và chữ ký; đây **không phải** mô tả đầy đủ byte-level SASL protocol.

### 4.1. Nonce

Các giá trị ngẫu nhiên dùng trong một phiên xác thực giúp chống replay theo thiết kế của protocol.

### 4.2. Client proof

Client tạo proof từ mật khẩu và dữ liệu trao đổi; server có thể kiểm tra bằng verifier đã lưu, không cần server biết plaintext password.

### 4.3. Server signature

Client kiểm tra phản hồi xác thực từ server theo SCRAM protocol. Đây không tự thay thế việc kiểm tra chứng chỉ TLS và hostname của server khi kết nối qua mạng.

### 4.4. Không coi handshake là mã hóa toàn bộ phiên

Sau xác thực, traffic SQL cần TLS nếu muốn bảo vệ nội dung truy vấn, kết quả, thông tin cá nhân và các dữ liệu ứng dụng khác.

## 5. Password verifier trong PostgreSQL

PostgreSQL lưu thông tin xác thực mật khẩu cho role đăng nhập dưới một biểu diễn verifier thích hợp. Với SCRAM, giá trị dạng khái niệm:

~~~text
SCRAM-SHA-256$iterations:salt$StoredKey:ServerKey
~~~

Chuỗi ví dụ chỉ thể hiện cấu trúc; đây **không phải một mật khẩu/verifier hợp lệ để sử dụng**.

### 5.1. Verifier khác plaintext password

Server không cần lưu mật khẩu người dùng dưới dạng rõ để kiểm tra SCRAM. Điều này giảm rủi ro lộ plaintext từ dữ liệu xác thực trên server.

### 5.2. Verifier vẫn là dữ liệu nhạy cảm

Nếu ai đó đọc được verifier, họ có thể thực hiện những hình thức tấn công đoán mật khẩu ngoại tuyến hoặc hỗ trợ tấn công khác tùy threat model. Không đưa verifier vào logs, dashboards hoặc ticket hỗ trợ.

### 5.3. Không truy vấn pg_authid để “chứng minh bảo mật”

Catalog `pg_authid</BT> chứa dữ liệu xác thực nhạy cảm và bị giới hạn quyền truy cập. Không in `rolpassword</BT> lên màn hình, báo cáo hoặc kết quả chụp gửi người khác.

### 5.4. pg_roles có thể dùng để xem metadata ít nhạy cảm hơn

View `pg_roles</BT> phù hợp để xem tên role, khả năng LOGIN và thời hạn password mà không cần tiết lộ verifier.

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolvaliduntil
FROM pg_roles
WHERE rolcanlogin
ORDER BY rolname;
~~~

### 5.5. Đừng nhầm verifier với mã hóa có thể giải ngược

SCRAM verifier là dữ liệu dẫn xuất dành cho xác thực, không phải một password được mã hóa đối xứng để decrypt ra plaintext tùy ý.

## 6. SCRAM-SHA-256 và SCRAM-SHA-256-PLUS

Trong môi trường TLS và client/server hỗ trợ, PostgreSQL có thể thương lượng biến thể **SCRAM-SHA-256-PLUS** với **channel binding**.

### 6.1. SCRAM-SHA-256 thông thường

Challenge–response chứng minh khả năng biết secret tương ứng với verifier.

### 6.2. SCRAM-SHA-256-PLUS

Bổ sung ràng buộc thông tin của kênh TLS vào quá trình xác thực SCRAM. Điều này giúp phát hiện một số kiểu can thiệp *man-in-the-middle* hoặc kết thúc TLS giữa đường mà hai bên không nhất trí cùng một kênh.

### 6.3. Channel binding không phải một TLS option trang trí

Nếu app yêu cầu PLUS nhưng kết nối đi qua một proxy kết thúc TLS hoặc thiếu hỗ trợ ở client/server, xác thực có thể thất bại. Phải kiểm tra kiến trúc TLS thực tế, proxy và khả năng client.

### 6.4. Không đồng nhất PLUS với mTLS

- **SCRAM-PLUS**: password-based authentication có ràng buộc kênh TLS.
- **mTLS/client certificate authentication**: client chứng minh danh tính bằng chứng chỉ và khóa riêng theo mô hình xác thực chứng chỉ.

Hai cơ chế có thể có mục tiêu chung về danh tính nhưng không tương đương về quản lý credential.

## 7. TLS vẫn cần thiết khi dùng SCRAM

SCRAM không gửi password gốc dưới dạng rõ trong handshake, nhưng không mã hóa toàn bộ traffic ứng dụng. TLS cần được xem như lớp bảo vệ riêng.

### 7.1. Các mức sslmode của libpq

Các lựa chọn thông dụng gồm:

| `sslmode</BT> | Ý tưởng | Phù hợp môi trường production nhạy cảm? |
|---|---|---|
| `disable</BT> | Không dùng TLS | Thường không phù hợp khi kết nối qua mạng không tin cậy |
| `allow</BT> | Có thể kết nối không TLS trước | Không phải chính sách TLS bắt buộc |
| `prefer</BT> | Thích TLS nhưng có thể fallback | Không đủ nếu yêu cầu mã hóa bắt buộc |
| `require</BT> | Yêu cầu TLS | Mã hóa; cần xem thêm xác minh server |
| `verify-ca</BT> | TLS và xác minh chuỗi CA | Hơn require, nhưng không đầy đủ kiểm tra hostname |
| `verify-full</BT> | TLS, CA và hostname verification | Thường là lựa chọn đáng ưu tiên với PKI đúng |

### 7.2. Vì sao verify-full quan trọng?

Mã hóa kết nối đến **một server bất kỳ** không tương đương biết chắc đó là PostgreSQL server mình muốn. Kiểm tra hostname giúp ràng buộc chứng chỉ với endpoint mong đợi.

### 7.3. Server hostname và chứng chỉ

Nếu certificate được phát hành cho `db.example.test</BT>, client nên kết nối bằng tên DNS tương ứng thay vì đổi sang một IP không nằm trong certificate, trừ khi PKI và client hỗ trợ SAN IP được cấu hình đúng.

### 7.4. Không chuyển qua disable chỉ để “sửa lỗi SCRAM”

Khi TLS verification thất bại, cần kiểm tra CA, SAN/hostname, chain và proxy. Tắt TLS có thể che lỗi triển khai và làm suy giảm bảo mật.

## 8. Channel binding ở client

Với libpq, thuộc tính kết nối `channel_binding</BT> có các lựa chọn thông dụng như `disable</BT>, `prefer</BT> và `require</BT>, phụ thuộc phiên bản hỗ trợ.

~~~text
host=db.example.test
dbname=appdb
user=app_orders
sslmode=verify-full
channel_binding=prefer
~~~

### 8.1. prefer

Client ưu tiên channel binding khi có thể dùng được, theo negotiation và môi trường TLS.

### 8.2. require

Client yêu cầu channel binding thích hợp; nếu không đạt, kết nối phải thất bại. Dùng khi đã xác nhận toàn chuỗi client–proxy–server hỗ trợ đúng cơ chế.

### 8.3. disable

Không yêu cầu/không dùng channel binding. Không chọn chỉ để vượt qua một lỗi mà chưa hiểu nguyên nhân.

### 8.4. JDBC có thể khác libpq

PostgreSQL JDBC driver không phải libpq. Thuộc tính/cách hỗ trợ channel binding, TLS và chứng chỉ có thể khác theo driver version. Không sao chép cấu hình libpq sang JDBC và giả định mọi option/behavior giống hệt.

## 9. pg_hba.conf quyết định phương thức xác thực

PostgreSQL dùng file **Host-Based Authentication** để định nghĩa các quy tắc kết nối: loại kết nối, database, user, địa chỉ nguồn và phương thức xác thực.

Một ví dụ HBA:

~~~text
# TYPE    DATABASE     USER             ADDRESS             METHOD
hostssl   appdb        app_orders       10.20.0.0/16        scram-sha-256
~~~

Đây là **dòng cấu hình trong pg_hba.conf**, không phải SQL.

### 9.1. host

Dùng cho TCP/IP connections theo cơ chế hỗ trợ, không tự yêu cầu TLS.

### 9.2. hostssl

Chỉ khớp các TCP/IP connections dùng SSL/TLS. Nó có ích khi muốn không cho một rule password authentication phục vụ kết nối plaintext.

### 9.3. local

Áp dụng cho Unix-domain socket connections trên nền tảng hỗ trợ. Đây không giống kết nối TCP tới `127.0.0.1</BT> hoặc `::1</BT>. `local</BT> có thể dùng peer authentication tùy chính sách.

### 9.4. user và database

Một HBA rule phải khớp cả database và role theo cú pháp được hỗ trợ. Một app có nhiều databases/roles có thể đi qua các rules khác nhau.

### 9.5. ADDRESS

Là nguồn kết nối nhìn từ PostgreSQL server. Với proxy, VPN hoặc NAT, IP mà server thấy có thể là IP của proxy, không phải IP workstation cuối cùng.

## 10. Quy tắc pg_hba.conf: dòng khớp đầu tiên có ý nghĩa quyết định

PostgreSQL xét các quy tắc HBA theo **thứ tự**; quy tắc đầu tiên khớp loại kết nối, database, user và address được chọn. Nếu xác thực trên quy tắc đó thất bại, PostgreSQL **không tự thử tiếp quy tắc thấp hơn như một cơ chế fallback mật khẩu**.

~~~text
# Ví dụ minh họa thứ tự nguy hiểm:
host    all     all         10.20.0.0/16     trust
hostssl appdb   app_orders  10.20.0.0/16     scram-sha-256
~~~

Nếu dòng rộng `trust</BT> khớp trước, dòng SCRAM sau không có cơ hội áp dụng cho kết nối đó.

### 10.1. Rule cụ thể phải được xem trong tổng thể

Không chỉ thêm một dòng `scram-sha-256</BT> rồi tin là tất cả connections sẽ dùng SCRAM. Phải đọc các rules ở phía trên, include files và các rule rộng hơn.

### 10.2. trust là rủi ro lớn

`trust</BT> cho phép những kết nối khớp rule đăng nhập không qua xác minh password tương ứng. Điều này chỉ có thể phù hợp cho một số môi trường thử nghiệm cô lập; không nên dùng rộng rãi trên production.

### 10.3. reject giúp đóng các đường không mong muốn

HBA có thể dùng phương thức `reject</BT> để chặn rõ một nhóm kết nối. Nhưng nếu đặt sai thứ tự, reject có thể khóa toàn bộ ứng dụng. Thay đổi HBA production cần phương án rollback/console access.

### 10.4. IPv4 và IPv6

`127.0.0.1/32</BT> và `::1/128</BT> là hai trường hợp khác nhau. Một kết nối tới hostname `localhost</BT> có thể resolve IPv6 thay vì IPv4, khiến bạn nhìn nhầm rule.

## 11. scram-sha-256 và md5 trong HBA khác nhau ra sao?

Trong PostgreSQL, `pg_hba.conf</BT> có thể chứa phương thức:

~~~text
hostssl appdb app_orders 10.20.0.0/16 scram-sha-256
~~~

Lệnh này yêu cầu xác thực bằng cơ chế SCRAM thích hợp.

Một số hệ thống cũ còn dùng:

~~~text
hostssl appdb legacy_user 10.20.0.0/16 md5
~~~

### 11.1. md5 là phương thức legacy

Phương thức MD5/password verifier cũ không có các đặc tính thiết kế của SCRAM. Với các triển khai PostgreSQL hiện đại, nên có kế hoạch chuyển sang SCRAM thay vì xây hệ thống mới trên MD5.

### 11.2. Điểm tương thích chuyển tiếp quan trọng

Trong những phiên bản PostgreSQL hỗ trợ behavior này, **HBA method `md5</BT> có thể tự chọn SCRAM authentication nếu password của role đang được lưu dưới dạng SCRAM verifier**. Đây là một đặc tính giúp migration, không phải lý do giữ HBA MD5 vĩnh viễn.

### 11.3. Chiều ngược lại không tương đương

Nếu HBA yêu cầu `scram-sha-256</BT> nhưng role chỉ còn MD5 verifier cũ, server không thể xác thực SCRAM bằng verifier MD5 như thể hai định dạng giống nhau. Phải đặt lại password với `password_encryption='scram-sha-256'</BT> tương ứng.

### 11.4. Kiểm tra server version

Các phiên bản PostgreSQL có thay đổi hỗ trợ/deprecation của password methods qua thời gian. Kế hoạch migration phải kiểm tra phiên bản server/clients đang chạy thay vì giả định một phiên bản legacy mãi được hỗ trợ.

## 12. password_encryption làm gì?

Cấu hình `password_encryption</BT> quyết định **cách PostgreSQL mã hóa/dẫn xuất password verifier khi mật khẩu được thiết lập theo đường phù hợp**.

~~~sql
SHOW password_encryption;
~~~

Một giá trị mong đợi trong triển khai SCRAM là:

~~~text
scram-sha-256
~~~

### 12.1. Không biến đổi mật khẩu cũ

Đổi cấu hình:

~~~sql
SET password_encryption = 'scram-sha-256';
~~~

không tự quét mọi role để chuyển verifier cũ sang SCRAM. Những mật khẩu đã được đặt trước đó cần được **đặt lại/xoay vòng** để có verifier mới phù hợp.

### 12.2. Không phải cài đặt phương thức HBA

`password_encryption</BT> kiểm soát verifier tạo ra khi đặt password, còn HBA quyết định client phải dùng **authentication method nào** lúc kết nối. Hai phần liên quan nhưng độc lập.

### 12.3. Cần đặt trước khi đổi mật khẩu

Một migration thông thường kiểm tra cấu hình trước, rồi thay đổi mật khẩu của role, cuối cùng kiểm tra HBA/client support.

### 12.4. Không mặc định mọi môi trường giống nhau

Máy dev, CI và production có thể có cấu hình khác. Dùng `SHOW password_encryption</BT> hoặc `pg_settings</BT> để quan sát, không suy từ tệp cấu hình trong repository.

## 13. Đặt mật khẩu bằng psql mà không đưa plaintext vào SQL history

Nếu dùng `psql</BT>, có meta-command:

~~~text
\password app_orders
~~~

Nó yêu cầu nhập mật khẩu theo cơ chế tương tác, tránh phải viết plaintext trực tiếp trong một câu SQL hiện ra trong lịch sử lệnh hoặc log SQL.

### 13.1. Vì sao không nên dùng literal PASSWORD?

Ví dụ sau **không nên sử dụng với secret thật trong terminal hoặc migration script**:

~~~sql
-- KHÔNG NHÚNG MẬT KHẨU THẬT VÀO SQL TEXT
ALTER ROLE app_orders PASSWORD 'secret-cua-production';
~~~

Text có thể xuất hiện trong shell/psql history, log của tooling, trace, hệ thống audit hoặc script được commit.

### 13.2. \password cần quyền thích hợp

Role đăng nhập có thể đổi password của chính nó theo cơ chế cho phép; quản trị viên có thể đổi password role khác nếu có quyền. Nếu thiếu quyền, lệnh sẽ thất bại.

### 13.3. Không lấy ví dụ làm mật khẩu thật

Các chuỗi minh họa trong tài liệu (như `secret-cua-production</BT>) không phải mật khẩu an toàn. Khi thực hành, sinh mật khẩu ngẫu nhiên mạnh bằng công cụ được phép, không sao chép literal.

### 13.4. \password không phải secret manager

Nó tránh một số rò rỉ do SQL literal; tổ chức vẫn cần cách cấp secret tới ứng dụng, lưu trữ an toàn, rotation, audit và thu hồi.

## 14. Tạo role đăng nhập riêng thay vì dùng postgres

Một ứng dụng không nên kết nối bằng superuser `postgres</BT> chỉ vì cách đó bỏ qua lỗi quyền.

~~~sql
CREATE ROLE app_orders LOGIN;
~~~

Sau đó dùng `\password app_orders</BT> trong psql với người có quyền phù hợp.

### 14.1. LOGIN chỉ là khả năng xác thực

Role cần `LOGIN</BT> để đăng nhập, nhưng không tự có quyền đọc/ghi mọi bảng.

### 14.2. Superuser là đặc quyền lớn

Dùng superuser cho microservice có thể khiến một lỗi injection hoặc secret leak có tác động trên toàn cluster.

### 14.3. Một role cho mỗi workload

Có thể chia roles theo service, môi trường và tác vụ:

~~~text
app_orders_rw
app_reporting_ro
batch_importer
migration_admin
monitoring_ro
~~~

Tách quyền giúp thu hồi một role mà ít ảnh hưởng role khác, và hỗ trợ audit.

### 14.4. Không nhất thiết mỗi instance một password riêng

Có nhiều mô hình: cùng role/secret cho một service pool, mỗi service một role, per-tenant roles hoặc identities ngắn hạn. Chọn dựa trên quản trị và threat model; đừng tạo hàng triệu login roles khi không cần.

## 15. Quyền tối thiểu: một ví dụ SQL

Giả sử trong database ứng dụng có schema `sales</BT> và bảng `sales.orders</BT>.

~~~sql
GRANT CONNECT
ON DATABASE appdb
TO app_orders;

GRANT USAGE
ON SCHEMA sales
TO app_orders;

GRANT SELECT, INSERT, UPDATE
ON sales.orders
TO app_orders;
~~~

Đây là ví dụ và yêu cầu database, schema, table, role tồn tại, cùng quyền cấp phát phù hợp.

### 15.1. CONNECT

Cho phép quyền kết nối database theo mô hình privileges, nhưng trong một số database `PUBLIC</BT> đã có CONNECT mặc định; GRANT một mình chưa chứng minh DB đã được khóa kín.

### 15.2. USAGE schema

Quyền đi vào namespace không đồng nghĩa có quyền trên mọi table trong namespace.

### 15.3. Table privileges

Quyền SELECT/INSERT/UPDATE/DELETE cần cấp riêng theo nhu cầu. Nếu chỉ đọc, không cấp quyền ghi.

### 15.4. Function và sequences

Ứng dụng có thể cần EXECUTE trên function hoặc USAGE trên sequence tương ứng nếu dùng cơ chế cấp ID, tùy thiết kế. Không mặc định quyền trên bảng tự kéo theo mọi quyền đối tượng khác.

### 15.5. Default privileges

Đối tượng tạo mới trong tương lai không nhất thiết có cùng GRANT như bảng cũ. Nếu cần, thiết kế `ALTER DEFAULT PRIVILEGES</BT> cho đúng role chủ sở hữu tạo objects và phạm vi schema.

## 16. Tại sao HBA thành công nhưng SELECT vẫn lỗi?

Một tình huống thực tế:

~~~text
SCRAM authentication: SUCCESS
Database connection: SUCCESS
SELECT * FROM sales.orders: ERROR permission denied
~~~

Không có mâu thuẫn: người dùng đã chứng minh được danh tính nhưng không có quyền trên schema/table.

### 16.1. Khi xử lý lỗi

Kiểm tra theo thứ tự:

1. Login role có tồn tại và có LOGIN không?
2. HBA rule có khớp kết nối không?
3. Password verifier/client negotiation có phù hợp không?
4. Kênh TLS có được xác minh không?
5. Database có tồn tại và role có CONNECT không?
6. Role có USAGE schema không?
7. Role có quyền đối tượng thực tế không?
8. Có RLS policy hoặc SECURITY DEFINER/INVOKER ảnh hưởng kết quả không?

### 16.2. Không sửa bằng GRANT ALL ON EVERYTHING

Cấp quyền quá rộng giải quyết triệu chứng nhưng tăng blast radius. Lỗi authentication phải sửa ở authentication; lỗi authorization phải cấp đúng quyền còn thiếu.

## 17. Lab an toàn: chuẩn bị database và role

**Môi trường:** Một PostgreSQL instance/cluster thử nghiệm, tài khoản quản trị được cấp phép, một database mới chỉ dành cho lab. Các thao tác role/HBA ảnh hưởng cluster nên không thực hiện trên production nếu không có thay đổi được phê duyệt.

### 17.1. Tạo database riêng

~~~sql
CREATE DATABASE scram_demo_db;
~~~

Lệnh cần quyền `CREATEDB</BT> hoặc superuser tương đương; hãy làm bằng role quản trị thử nghiệm.

### 17.2. Tạo login role không có password ban đầu

~~~sql
CREATE ROLE scram_demo_login
LOGIN
NOSUPERUSER
NOCREATEDB
NOCREATEROLE
NOREPLICATION;
~~~

Role mới chưa có password hữu dụng cho password authentication.

### 17.3. Đặt password an toàn

Trong psql, kiểm tra:

~~~sql
SHOW password_encryption;
~~~

Nếu cần kiểm soát tạo verifier trong session được phép:

~~~sql
SET password_encryption = 'scram-sha-256';
~~~

Sau đó chạy lệnh psql tương tác:

~~~text
\password scram_demo_login
~~~

Không dán mật khẩu thật vào bài học, lệnh SQL hiển thị, chat hoặc log.

### 17.4. Cấp quyền kết nối

~~~sql
GRANT CONNECT
ON DATABASE scram_demo_db
TO scram_demo_login;
~~~

Để tránh quyền CONNECT mặc định của PUBLIC ở lab cô lập, có thể áp dụng `REVOKE CONNECT ON DATABASE scram_demo_db FROM PUBLIC</BT> sau khi xác định không ảnh hưởng công cụ quản trị; đây là quyết định quản lý quyền database, không phải điều kiện SCRAM.

## 18. Lab: tạo dữ liệu chỉ-đọc trong database thử nghiệm

Dùng psql kết nối với `scram_demo_db</BT> bằng role quản trị, rồi chạy:

~~~sql
CREATE SCHEMA scram_lab;

CREATE TABLE scram_lab.healthcheck (
    id INTEGER PRIMARY KEY,
    marker TEXT NOT NULL
);

INSERT INTO scram_lab.healthcheck(id, marker)
VALUES (1, 'scram-demo-ok');

GRANT USAGE ON SCHEMA scram_lab
TO scram_demo_login;

GRANT SELECT ON scram_lab.healthcheck
TO scram_demo_login;
~~~

### 18.1. Vì sao làm lab này?

Bạn có thể kiểm tra hai mục tiêu độc lập:

- Kết nối thành công bằng password/SCRAM.
- Role có đúng quyền SELECT trên một bảng, nhưng không có quyền sửa bảng.

### 18.2. Không cấp quyền ghi

Trong lab, không cấp INSERT/UPDATE/DELETE để kiểm tra least privilege. Nếu client thử UPDATE, PostgreSQL nên từ chối theo privileges hiện hành.

### 18.3. Đối tượng nằm trong database nào?

Role tồn tại cấp cluster, nhưng schema/table tồn tại trong database cụ thể. Hãy chắc chắn đang kết nối đúng `scram_demo_db</BT> khi tạo bảng.

## 19. Lab: cấu hình một quy tắc HBA cụ thể

Một cấu hình minh họa cho PostgreSQL server test với TLS đã bật:

~~~text
# pg_hba.conf - minh họa, không phải SQL
hostssl scram_demo_db scram_demo_login 127.0.0.1/32 scram-sha-256
hostssl scram_demo_db scram_demo_login ::1/128      scram-sha-256
~~~

### 19.1. Điều kiện

- Server TLS/SSL được bật và cấu hình certificate/key thích hợp.
- PostgreSQL được phép nhận TCP/IP connections trên interfaces cần thiết.
- HBA có rule tương ứng đúng thứ tự.
- Client dùng TLS và có khả năng SCRAM.
- Test bằng hostname khớp certificate khi dùng `verify-full</BT>.

### 19.2. Đây chỉ là ví dụ loopback

Nếu PostgreSQL nằm trên server khác, địa chỉ nguồn phải là CIDR của client/proxy được phép và đủ hẹp. Không thay thành `0.0.0.0/0</BT> tùy ý để “cho chạy”.

### 19.3. Đừng thay HBA trực tiếp nếu không có quyền

File do DBA/infrastructure quản lý. Trong managed PostgreSQL, cơ chế cấu hình network/auth có thể được nhà cung cấp giới hạn hoặc cung cấp giao diện khác.

### 19.4. Không xóa hết HBA cũ

Luôn giữ cách truy cập quản trị phục hồi, backup file và đường rollback. Một lỗi thứ tự rule có thể khóa truy cập từ xa.

## 20. Reload cấu hình HBA và kiểm tra rule

Một số thay đổi `pg_hba.conf</BT> cần reload để áp dụng cho các kết nối mới.

~~~sql
SELECT pg_reload_conf();
~~~

Lệnh này cần quyền phù hợp và chỉ gửi tín hiệu reload; không tự chứng minh mọi rule đã parse đúng hoặc kết nối mới sẽ thành công.

### 20.1. Kiểm tra parser HBA

Khi có quyền xem:

~~~sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_hba_file_rules
ORDER BY line_number;
~~~

### 20.2. Chú ý cột error

Nếu parser báo lỗi, phải sửa theo cấu hình thật. Một rule trong file nhưng parse lỗi không phải bằng chứng server đang dùng nó.

### 20.3. Có thể có include files

Một số deployments dùng include/include_dir hoặc cấu hình tương ứng; cần xem **thứ tự rules thực tế** sau khi mở rộng các file include.

### 20.4. Existing sessions vẫn tồn tại

Reload HBA không tự ngắt tất cả connections đang đăng nhập. Các pool connections đã xác thực có thể tiếp tục hoạt động, khiến bạn tưởng password/HBA mới đã được kiểm tra dù chỉ đang tái sử dụng session cũ.

## 21. Lab: kiểm tra connection thực sự bằng psql

Sau khi role/password, TLS và HBA sẵn sàng, kết nối từ môi trường được phép.

Ví dụ dạng libpq conninfo **không chứa password**:

~~~text
psql "host=db.example.test port=5432 dbname=scram_demo_db user=scram_demo_login sslmode=verify-full"
~~~

Trong bài lab loopback, thay `db.example.test</BT> bằng endpoint thực tế có chứng chỉ khớp hostname và rule HBA phù hợp. Dòng lệnh là ví dụ terminal, không phải SQL.

### 21.1. Nhập password qua prompt

Để psql hỏi password hoặc dùng cơ chế secrets/file được bảo vệ. Không đưa password vào command line arguments.

### 21.2. Thử query danh tính

~~~sql
SELECT
    current_user,
    session_user,
    current_database();
~~~

Nếu không có SET ROLE, current_user và session_user thường phản ánh role đăng nhập.

### 21.3. Thử quyền đọc

~~~sql
SELECT *
FROM scram_lab.healthcheck;
~~~

Kỳ vọng đọc được marker của bảng đã GRANT SELECT.

### 21.4. Thử thao tác không có quyền

~~~sql
-- Chỉ chạy trong lab, kỳ vọng lỗi thiếu quyền
UPDATE scram_lab.healthcheck
SET marker = 'should-not-update'
WHERE id = 1;
~~~

Nếu role chỉ có SELECT, lệnh phải bị từ chối bởi privileges phù hợp. Nếu nó thành công, cần xem quyền PUBLIC, role membership, table ownership và các grants khác.

### 21.5. Test bằng connection mới

Chấm dứt session rồi mở kết nối mới khi kiểm tra password/HBA changes; không chỉ query trên kết nối cũ trong pool.

## 22. Kiểm tra TLS của kết nối đang chạy

PostgreSQL có view `pg_stat_ssl</BT> có thể giúp quan sát trạng thái TLS của backend connections.

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.client_addr,
    s.ssl,
    s.version AS tls_version,
    s.cipher
FROM pg_stat_activity AS a
JOIN pg_stat_ssl AS s
  ON s.pid = a.pid
WHERE a.datname = current_database()
ORDER BY a.pid;
~~~

### 22.1. ssl=true có nghĩa gì?

Kết nối đang dùng TLS tại server. Nó **không tự chứng minh client đã xác minh hostname hoặc CA**; phần đó phải kiểm tra cấu hình client/cert.

### 22.2. ssl=false có thể bình thường ở socket local

Một kết nối Unix-domain socket không dùng TLS và có thể xác thực bằng `peer</BT> hoặc phương thức khác. Không đánh đồng mọi kết nối local ssl=false với lỗi SCRAM.

### 22.3. pg_stat_ssl không nói trực tiếp HBA method

View thể hiện trạng thái TLS, không phải một bảng lịch sử đầy đủ “client đã dùng SCRAM-SHA-256-PLUS hay chưa”. Cần phối hợp HBA config, client settings và logs/monitoring phù hợp.

### 22.4. Hạn chế quyền quan sát

Một số thông tin của phiên người dùng khác có thể bị hạn chế tùy privileges. Không cấp quyền xem mọi hoạt động nhạy cảm cho application role chỉ để lập dashboard.

## 23. .pgpass: lưu password cho libpq/psql

Với client libpq, một password file giúp tránh đặt password trong script/connection string.

Mẫu cấu trúc:

~~~text
hostname:port:database:username:password
~~~

Ví dụ minh họa, **không dùng giá trị này như secret thật**:

~~~text
db.example.test:5432:appdb:app_orders:<replace-with-generated-secret>
~~~

### 23.1. Vị trí phổ biến

Trên Unix-like systems, file mặc định thường là `~/.pgpass</BT>. Trên Windows, vị trí mặc định thường là `%APPDATA%\postgresql\pgpass.conf</BT>, hoặc dùng đường dẫn riêng qua biến `PGPASSFILE</BT> theo khả năng client.

### 23.2. Quyền file trên Unix

Đặt permission chặt:

~~~sh
chmod 0600 ~/.pgpass
~~~

libpq trên Unix có thể bỏ qua password file nếu permission quá rộng theo quy tắc bảo vệ của nó.

### 23.3. Windows permissions

Quản lý ACL theo user/service account, không coi việc đặt trong thư mục profile là bằng chứng mọi account khác đều không đọc được.

### 23.4. Dấu hai chấm và backslash trong password

Cú pháp password file có quy tắc escape cho các ký tự đặc biệt như `:</BT> và backslash. Nếu secret chứa ký tự này, cần ghi đúng định dạng theo tài liệu của libpq thay vì cắt chuỗi ngẫu nhiên.

### 23.5. File vẫn chứa secret

.pgpass giúp tránh một số rò rỉ trong command line, nhưng vẫn là plaintext password file trên disk. Phải bảo vệ filesystem, backups, ownership và lifecycle rotation.

## 24. PGPASSWORD và environment variables: tiện nhưng có rủi ro

Một số tools libpq có thể đọc biến `PGPASSWORD</BT>.

~~~text
PGPASSWORD = secret supplied by environment
~~~

### 24.1. Vì sao không phải lựa chọn đầu tiên?

Environment variables có thể bị lộ qua:

- Process introspection trên một số OS/container configurations.
- Debug dumps, diagnostics và support bundles.
- CI/CD job output do lệnh debug.
- Logs in giá trị environment.
- Misconfigured orchestration/metadata.
- Subprocesses thừa hưởng environment.

### 24.2. Cũng không mặc định hoàn toàn cấm

Một số nền tảng có secrets injection qua environment và controls phù hợp. Nhưng cần biết threat model, chính sách vận hành và mức độ dễ lộ; không xem env var là secret vault an toàn chỉ nhờ đặt tên `DB_PASSWORD</BT>.

### 24.3. Không in env var để kiểm tra

Một lệnh `echo</BT> hoặc debug dump có thể đưa secret vào terminal log. Kiểm tra sự hiện diện và đường kết nối theo cách không tiết lộ giá trị.

### 24.4. Không đưa secret vào shell history

Các lệnh gán literal password trong terminal có thể nằm trong lịch sử shell, session recording hoặc CI logs. Sử dụng secret retrieval/injection có kiểm soát thay vì thao tác copy/paste lộ bí mật.

## 25. Connection URI cũng có thể làm lộ password

Một URI có thể chứa user/password:

~~~text
postgresql://user:password@db.example.test:5432/appdb
~~~

Đây là cấu trúc minh họa, **không phải cách khuyến nghị lưu secret thật**.

### 25.1. Vì sao nguy hiểm?

URI có thể xuất hiện trong:

- Application logs.
- Monitoring attributes.
- Stack traces.
- Command line/process listings.
- Browser history hoặc tài liệu nội bộ.
- Copy/paste vào ticket/chat.
- Source/config repository.

### 25.2. URL-encoding không phải mã hóa bảo mật

Mật khẩu có ký tự đặc biệt được URL-encode vẫn có thể giải ra. Không xem encoding là biện pháp che secret.

### 25.3. Tách endpoint và secret

Lưu hostname, port, dbname và TLS config trong configuration không bí mật; secret được lấy qua cơ chế được kiểm soát và chỉ đưa vào password property khi thật sự cần.

### 25.4. Redaction có kiểm soát

Nếu log connection configuration để chẩn đoán, phải lọc password và các token khác, không chỉ tìm chuỗi `password=</BT> mà bỏ qua password nằm trong userinfo của URI.

## 26. Secret manager và mô hình đưa bí mật vào ứng dụng

Một hệ thống production có thể dùng secret manager hoặc cơ chế identity integration để quản lý credential.

~~~text
Secret Manager / Credential Issuer
          |
          | auth bằng workload identity
          v
Application startup / rotation agent
          |
          | nhận credential có quyền giới hạn
          v
Memory / protected file / platform secret mount
          |
          v
JDBC connection pool
          |
          v
PostgreSQL TLS + SCRAM
~~~

### 26.1. Secret manager lưu những gì?

Thường gồm username, password, endpoint metadata, phiên bản secret, thời hạn hoặc thông tin phục vụ rotation. Không cần lưu plaintext password ở repository.

### 26.2. Workload identity

Ứng dụng nên xác thực với secret manager bằng danh tính workload (máy, service account, federated identity...) thay vì hard-code một “password để lấy password”.

### 26.3. Chỉ cấp quyền đọc secret cần thiết

Service A không nên có quyền lấy DB password của Service B. Secret permissions là một lớp phân quyền độc lập với PostgreSQL GRANT.

### 26.4. Secret caching và rotation

Ứng dụng có thể cache secret trong memory để tránh gọi secret manager mỗi query. Cần quy tắc refresh, TTL, invalidation và xử lý lỗi khi secret version thay đổi.

### 26.5. Secret manager không tự đổi PostgreSQL verifier

Nếu chỉ sửa giá trị trong vault nhưng không cập nhật password của role PostgreSQL tương ứng, new connections sẽ lỗi. Rotation phải điều phối **cả database và client distribution**.

## 27. Java/JDBC: kết nối mà không hard-code password

Một ví dụ khái niệm Java:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.util.Properties;

public final class DbConnectionExample {
    public Connection open(String passwordFromSecretProvider)
            throws Exception {
        String url =
            "jdbc:postgresql://db.example.test:5432/appdb"
            + "?sslmode=verify-full";

        Properties props = new Properties();
        props.setProperty("user", "app_orders");
        props.setProperty("password", passwordFromSecretProvider);

        return DriverManager.getConnection(url, props);
    }
}
~~~

### 27.1. Password đến từ đâu?

Biến `passwordFromSecretProvider</BT> phải do một thành phần được phép lấy secret tạo ra. Đoạn code **không minh họa** hard-code secret, cũng không tự cài đặt secret manager.

### 27.2. String trong Java có giới hạn bảo mật

JDBC APIs thường nhận password dạng String, một đối tượng không thể xóa memory chắc chắn như buffer có thể ghi đè. Giảm thời gian giữ secret, không log/serialize, bảo vệ heap dumps và process access.

### 27.3. TLS settings phải đúng driver

`sslmode=verify-full</BT> là ví dụ với PostgreSQL JDBC driver hiện đại; việc cấu hình trust store/certificate và channel binding cần đối chiếu driver version, môi trường và policy cụ thể.

### 27.4. Không bật debug logging nhạy cảm

Không log toàn bộ `Properties</BT>, JDBC URL nếu có userinfo, exception data chứa secret hoặc raw configuration objects.

### 27.5. Xử lý exception

Một lỗi kết nối có thể do password, TLS, HBA, network, DNS, database hoặc quyền. Tránh phản hồi cho người dùng cuối bằng toàn bộ connection string chứa thông tin nhạy cảm.

## 28. Connection pool làm rotation phức tạp hơn

Một service thường dùng HikariCP hoặc pool khác để tái sử dụng sessions.

~~~text
Application
    |
    v
Connection Pool
  conn A ---- authenticated yesterday
  conn B ---- authenticated yesterday
  conn C ---- new connection now
    |
    v
PostgreSQL
~~~

### 28.1. SCRAM diễn ra lúc thiết lập connection

Mỗi kết nối mới thường phải đi qua quy trình xác thực. Một connection đã đăng nhập thành công không làm SCRAM handshake lại cho mọi SQL query.

### 28.2. Sau khi đổi password

Các sessions đã xác thực thường **không tự bị đăng xuất** khi password role thay đổi. Những connections mới dùng password cũ sẽ thất bại.

### 28.3. Biểu hiện khó hiểu

Ứng dụng hoạt động bình thường vài phút sau rotation vì vẫn còn connections cũ, sau đó bắt đầu báo authentication failures khi pool cần mở connections mới.

### 28.4. Không chỉ đổi config rồi xong

Nếu pool đang giữ cấu hình secret cũ, thay secret manager mà không reload pool có thể làm các connections mới dùng sai password.

### 28.5. Phương án điều phối

Cần cập nhật secrets, tạo pools/connections mới có password đúng, dừng dùng connections cũ theo kế hoạch và quan sát failures. Với triển khai không downtime, thường cần rolling migration hoặc chiến lược hai roles.

## 29. Rotation một password cho một role

Với một PostgreSQL login role dùng password thông thường, cấu hình cơ bản chỉ có **một password verifier hiện hành** cho role tại một thời điểm; không coi nó tự hỗ trợ hai password song song.

### 29.1. Trình tự đơn giản

1. Tạo secret mới mạnh.
2. Chuẩn bị ứng dụng có khả năng nạp secret mới.
3. Thay password role trong PostgreSQL.
4. Cập nhật secret distribution đúng version.
5. Tái tạo pool connections khi cần.
6. Theo dõi authentication failures.
7. Thu hồi/quản lý secret cũ.
8. Xác minh new connection thật sự dùng thông tin mới.

### 29.2. Cửa sổ lỗi có thể xảy ra

Nếu DB đổi trước app, new connections của app cũ lỗi. Nếu app dùng mật khẩu mới trước DB, new connections cũng lỗi. Đây là lý do cần phối hợp thời điểm và khả năng rollback.

### 29.3. Rotation không chỉ là ALTER ROLE

Quy trình phải xem những nơi còn giữ secret: CI runner, script bảo trì, reporting job, old pods, CronJob, developer workstation và disaster-recovery automation.

### 29.4. Kiểm tra mà không tiết lộ

Thử mở một **new connection** theo đường TLS/SCRAM mong đợi; đừng in plaintext password hay verifier để chứng minh đã cập nhật.

## 30. Rotation gần như không gián đoạn bằng hai login roles

Một chiến lược cho ứng dụng cần zero/low downtime là tách hai danh tính đăng nhập có quyền tương đương, được cấp qua một **NOLOGIN privilege role**.

~~~text
             Role quyền (NOLOGIN)
                   app_orders_access
                    /           \
                   /             \
          app_orders_a         app_orders_b
             LOGIN               LOGIN
             secret A            secret B
~~~

### 30.1. Tạo role nhóm quyền

~~~sql
CREATE ROLE app_orders_access NOLOGIN;
~~~

Cấp các quyền đối tượng cần thiết cho role nhóm:

~~~sql
GRANT CONNECT ON DATABASE appdb
TO app_orders_access;

GRANT USAGE ON SCHEMA sales
TO app_orders_access;

GRANT SELECT, INSERT, UPDATE ON sales.orders
TO app_orders_access;
~~~

### 30.2. Tạo hai login roles

~~~sql
CREATE ROLE app_orders_a LOGIN;
CREATE ROLE app_orders_b LOGIN;
~~~

Với PostgreSQL version/role inheritance settings phù hợp, cấp membership:

~~~sql
GRANT app_orders_access TO app_orders_a;
GRANT app_orders_access TO app_orders_b;
~~~

Role inheritance semantics phải được xác minh để các logins có quyền mong đợi.

### 30.3. Đặt hai mật khẩu riêng bằng psql

~~~text
\password app_orders_a
\password app_orders_b
~~~

Không hard-code secrets vào SQL.

### 30.4. Cutover

1. App dùng `app_orders_a</BT> ban đầu.
2. Chuẩn bị `app_orders_b</BT> với mật khẩu mới.
3. Kiểm tra quyền và new connection của B.
4. Rolling deploy/pool replacement từ A sang B.
5. Quan sát sessions và lỗi.
6. Khi chắc chắn A không còn callers, vô hiệu hóa hoặc thu hồi A theo chính sách.

### 30.5. Chi phí của phương án

Có thêm roles, audit identity theo phiên và cần bảo trì grants/membership. Nhưng nó cho phép hai secrets tồn tại song song mà không phải chấp nhận một password verifier có hai giá trị cho cùng role.

## 31. VALID UNTIL và NOLOGIN: hai điều khác nhau

PostgreSQL hỗ trợ thuộc tính thời hạn password role:

~~~sql
ALTER ROLE app_orders_a
VALID UNTIL '2027-06-30 00:00:00+00';
~~~

Và khả năng tắt LOGIN:

~~~sql
ALTER ROLE app_orders_a NOLOGIN;
~~~

### 31.1. VALID UNTIL

Giới hạn hiệu lực mật khẩu theo quy tắc xác thực password. Nó không phải toàn bộ account expiration framework và không nhất thiết ngăn các phương thức xác thực không dựa trên password trong cùng cách.

### 31.2. NOLOGIN

Role không còn được dùng làm login role cho kết nối mới, dù vẫn có thể giữ quyền/membership để phục vụ mô hình khác.

### 31.3. Không tự đóng các sessions đang sống

Thay VALID UNTIL, NOLOGIN hoặc password **không mặc định kết thúc mọi session đã đăng nhập trước đó**. Phải xử lý existing sessions nếu mục tiêu là thu hồi ngay lập tức.

### 31.4. Không dùng PASSWORD NULL như đồng nghĩa với NOLOGIN

~~~sql
ALTER ROLE app_orders_a PASSWORD NULL;
~~~

Thao tác này loại bỏ password hữu dụng cho các phương thức password authentication, nhưng role vẫn có thể đăng nhập bằng phương thức khác nếu HBA và quyền cho phép. Để ngăn login mới theo vai trò, dùng NOLOGIN khi phù hợp.

## 32. Thu hồi existing sessions khi secret bị lộ

Khi có sự cố credential compromise, chỉ đổi password chưa chắc đủ vì kẻ tấn công có thể giữ một session đã đăng nhập.

### 32.1. Quan sát sessions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    backend_start,
    state
FROM pg_stat_activity
WHERE usename = 'app_orders_a'
ORDER BY backend_start;
~~~

### 32.2. Hủy session cần quyền đặc biệt

PostgreSQL có hàm `pg_terminate_backend</BT> để chấm dứt backend sessions với quyền phù hợp.

~~~sql
-- Ví dụ quản trị cần đánh giá tác động trước khi chạy:
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE usename = 'app_orders_a'
  AND pid <> pg_backend_pid();
~~~

### 32.3. Vì sao không chạy bừa trên production?

Nó có thể cắt transaction đang làm việc, gây lỗi ứng dụng, rollback và retry storms. Trong sự cố thực, cần cân bằng yêu cầu thu hồi khẩn cấp với mức ảnh hưởng, cùng incident response plan.

### 32.4. Đừng chỉ xem role name

Nếu secret bị chia sẻ cho nhiều jobs hoặc services, cần kiểm tra source IP, application_name, times, connection pool behavior và activity logs phù hợp, trong phạm vi quyền được phép.

### 32.5. Thu hồi đa lớp

Có thể cần đồng thời rotate password, NOLOGIN role cũ, terminate sessions, thu hồi secret từ vault/CI, đổi tokens liên quan, kiểm tra logs và xác định phạm vi dữ liệu đã truy cập.

## 33. Quy trình quản lý secrets theo vòng đời

Một credential production cần được quản trị theo chu trình:

~~~text
Generate -> Approve/Issue -> Store -> Distribute
     ^                               |
     |                               v
   Revoke <- Retire <- Rotate <- Use/Monitor
~~~

### 33.1. Generate

Dùng generator ngẫu nhiên mật mã học, mật khẩu dài, không đoán được, không lặp lại giữa môi trường/dịch vụ.

### 33.2. Issue/approve

Xác định owner, purpose, quyền, thời hạn, môi trường và cơ chế yêu cầu cấp secret.

### 33.3. Store

Dùng secret manager hoặc kho được bảo vệ; không lưu plaintext trong source code, shared documents hoặc ticket.

### 33.4. Distribute

Cấp quyền đọc secret tối thiểu cho workload identity; bảo vệ kênh lấy secret và việc inject vào process.

### 33.5. Use

Kết nối với SCRAM qua TLS đúng chính sách, sử dụng role có quyền tối thiểu.

### 33.6. Monitor

Theo dõi thất bại xác thực, lượng kết nối, quyền và sử dụng secret bất thường mà không ghi giá trị bí mật.

### 33.7. Rotate

Thay secret định kỳ hoặc theo sự kiện, đồng bộ với DB verifier, restart/reload pools và xác minh new connections.

### 33.8. Revoke/retire

Thu hồi role/secret, kiểm tra sessions còn sống, xóa bản sao không cần thiết và cập nhật tài liệu/quy trình.

## 34. Sinh mật khẩu mạnh cho SCRAM

SCRAM không cứu được một mật khẩu phổ biến hoặc ngắn.

### 34.1. Độ dài và entropy

Đối với credential sinh tự động, ưu tiên mật khẩu dài, ngẫu nhiên, có entropy cao; không dựa chỉ vào quy tắc “phải có một chữ hoa, một số và một ký tự đặc biệt”.

### 34.2. Không dùng lại

Mật khẩu production, staging, dev và các services khác nhau phải độc lập. Nếu secret bị lộ trong môi trường dev, không nên suy ra được production credential.

### 34.3. Không dùng tên dự án/ngày tháng

Các mẫu như `Project2026!</BT>, `Company@123</BT> dễ đoán dù thỏa một số quy tắc hình thức.

### 34.4. Lưu ý khả năng nhập và encoding

Mật khẩu có Unicode, ký tự đặc biệt hoặc quá dài cần được client/server handling hỗ trợ đúng. Dùng secret generator và API bảo quản bytes/encoding nhất quán; không tự `trim()</BT> hoặc `lower()</BT> password từ secret manager.

### 34.5. Không “hash thêm” ở client tùy ý

Nếu application tự tính SHA-256(password) rồi gửi kết quả như password mới, kết quả hash trở thành bí mật tái sử dụng, không nhất thiết tăng bảo mật. SCRAM đã có cơ chế dẫn xuất trong protocol; cần quản lý original secret đúng cách.

## 35. Secrets trong CI/CD và infrastructure-as-code

Những nơi thường vô tình lộ DB password:

- Git commit chứa `application.properties</BT>.
- File `.env</BT> được push lên repository.
- CI job in tất cả biến môi trường.
- Terraform plan/state chứa secret ở attributes nhạy cảm.
- Helm values/plain YAML được lưu công khai.
- Kubernetes Secret bị hiểu nhầm là đã được mã hóa an toàn chỉ vì base64.
- Docker image chứa secret trong layer.
- Build arguments hoặc Dockerfile ENV có password.
- Test fixtures dùng production credential.
- Support bundle/heap dump được chia sẻ không hạn chế.

### 35.1. IaC state là dữ liệu nhạy cảm

Một plan che giá trị trên console không có nghĩa state/storage backend không chứa bản sao secret. Bảo vệ encryption-at-rest, IAM, version history, logging và retention.

### 35.2. Container image không phải chỗ lưu password

Secret baking vào Docker image tạo bản sao khó thu hồi và thường bị phân phối rộng. Hãy inject lúc chạy qua cơ chế nền tảng được kiểm soát.

### 35.3. Không tin base64 là encryption

Kubernetes Secret data có thể được encode base64 trong manifest; encoding không bảo vệ khỏi người đọc được manifest/API. Cần RBAC, encryption at rest, node isolation và secret distribution policy.

### 35.4. Rotate sau khi commit nhầm

Nếu secret đã vào Git hoặc CI log, xóa dòng khỏi branch hiện tại **không làm secret chưa từng bị lộ**. Phải rotate/revoke secret, đánh giá lịch sử artifact/backup và phạm vi truy cập.

## 36. Logs và observability: quan sát mà không in secrets

Một hệ thống cần biết xác thực lỗi, nhưng không cần biết password người dùng đã nhập.

### 36.1. Có thể log

- Timestamp.
- Role/username dự kiến.
- Database.
- Application name nếu có.
- Source IP.
- Nhóm lỗi authentication/TLS/network.
- Connection count, pool wait, retry rate.
- Secret version identifier không nhạy cảm (không phải giá trị).
- Certificate expiry và TLS policy status.

### 36.2. Không log

- Plaintext password.
- PostgreSQL SCRAM verifier.
- Connection URI chứa password.
- Secret manager response raw.
- Token/API key để lấy secret.
- Authorization header.
- Dump toàn bộ environment.
- Private keys/certificates nhạy cảm.
- Memory dump chứa credential.

### 36.3. Password thất bại không nên phản hồi như dữ liệu debug

Không ghi “client đã thử password xyz”. PostgreSQL error/logging configuration có thể chứa thông tin kết nối và statement tùy chế độ; cần thiết kế redaction và quyền xem logs.

### 36.4. Parameterized SQL vẫn cần lưu ý

Thậm chí khi ứng dụng dùng prepared statements, diagnostics/middleware có thể log parameters hoặc bind values. Không gửi plaintext password qua câu SQL `ALTER ROLE ... PASSWORD '...'</BT> nếu có đường an toàn hơn cho thao tác quản trị.

## 37. Bảo vệ backups và snapshots

PostgreSQL backup có thể chứa dữ liệu hoặc cấu hình nhạy cảm, kể cả các vật liệu xác thực trong những phạm vi backup phù hợp.

### 37.1. Physical backup

Một bản sao data directory/cluster có thể bao gồm dữ liệu system catalogs và bí mật phục vụ xác thực. Quyền truy cập backup phải được bảo vệ tương đương dữ liệu production nhạy cảm.

### 37.2. Logical backup

Các công cụ dump có phạm vi object/roles khác nhau. Không giả định mọi dump đều có hoặc không có password verifier; phải biết lệnh và options đang sử dụng.

### 37.3. Encryption và access control

Mã hóa backup at rest, kiểm soát IAM, key management, audit downloads và test restore là các lớp bắt buộc theo threat model.

### 37.4. Retention sau rotation

Ngay cả khi password live đã rotate, backups cũ có thể còn chứa verifier cũ hoặc application secrets. Quản lý retention và khả năng truy cập các bản sao cũ.

### 37.5. Không dùng backup để xác minh password

Không trích xuất verifier từ backup và đăng vào ticket; hãy dùng các kiểm tra new login và metadata không nhạy cảm.

## 38. Chuyển hệ thống cũ từ MD5 sang SCRAM

Một kế hoạch migration nên làm **theo giai đoạn**, tránh khóa toàn bộ clients.

~~~text
Inventory clients + server versions
            |
            v
Kiểm tra driver/libpq hỗ trợ SCRAM
            |
            v
Bật cơ chế tạo verifier SCRAM
            |
            v
Rotate passwords của login roles
            |
            v
Kiểm tra new connections
            |
            v
Chuyển HBA sang scram-sha-256
            |
            v
Theo dõi lỗi, thu hồi legacy
~~~

### 38.1. Kiểm kê trước

Liệt kê service, DB users, driver versions, batch jobs, BI tools, migration tools, monitoring agents và các database endpoints.

### 38.2. Nâng cấp clients chưa hỗ trợ

Nếu một ứng dụng cũ dùng driver không hỗ trợ SCRAM, thay verifier/HBA trước khi nâng driver có thể làm nó không đăng nhập được.

### 38.3. Đổi cấu hình verifier cho password mới

~~~sql
SHOW password_encryption;
~~~

Đảm bảo định hướng sang SCRAM; sau đó **đặt lại** password từng role bằng cơ chế an toàn.

### 38.4. Dùng behavior HBA md5 để chuyển tiếp khi được hỗ trợ

Một số PostgreSQL versions cho phép HBA `md5</BT> xác thực SCRAM nếu role có SCRAM verifier. Điều này tạo cửa sổ migration hữu ích, nhưng phải kiểm tra compatibility matrix thực tế.

### 38.5. Cuối cùng siết HBA

Sau khi tất cả clients/passwords sẵn sàng, chuyển rules mong muốn sang `scram-sha-256</BT>, reload và thử kết nối mới từ mọi đường.

### 38.6. Theo dõi production

Quan sát login failures, pool reconnects, deployment waves và batch jobs chạy không liên tục. Đừng tuyên bố migration thành công chỉ vì web app hoạt động trong một giờ.

## 39. Checklist khi đổi password_encryption

Một sai lầm là đổi:

~~~sql
SET password_encryption = 'scram-sha-256';
~~~

rồi cho rằng tất cả roles đã chuyển từ MD5.

### 39.1. Những gì thay đổi

Setting ảnh hưởng cách mật khẩu mới được đặt theo đường tương ứng.

### 39.2. Những gì không tự thay đổi

- Verifier đã lưu của mọi role.
- HBA method.
- TLS certificates.
- Password trong secret manager.
- Password mà ứng dụng/pool đang giữ.
- Driver/JDBC version.
- Existing sessions.
- Role privileges.

### 39.3. Tiêu chí hoàn tất

Mỗi role cần được kiểm tra bằng **new connection** theo HBA SCRAM rule và secret mới, từ client tương ứng, không dựa vào mỗi giá trị `SHOW password_encryption</BT>.

## 40. Các lỗi xác thực SCRAM thường gặp

| Triệu chứng | Khả năng cần kiểm tra |
|---|---|
| `password authentication failed</BT> | Password sai, verifier/role/HBA không tương thích, secret chưa cập nhật |
| `no pg_hba.conf entry</BT> | Không có rule khớp host/db/user/SSL |
| `role does not exist</BT> | Role sai tên hoặc chưa tạo trong cluster |
| `database does not exist</BT> | DB name sai hoặc chưa tạo |
| `permission denied for schema</BT> | Auth OK, thiếu USAGE schema |
| `permission denied for table</BT> | Auth OK, thiếu quyền table |
| `certificate verify failed</BT> | CA/chain/hostname/cert trust |
| `channel binding required</BT> hoặc lỗi tương tự | TLS/cơ chế PLUS/client không tương thích |
| Chỉ app instances mới lỗi | Pool cũ còn sống, new connections dùng secret sai |
| CI thành công, production lỗi | HBA IP/proxy/TLS/driver/secret khác |
| Kết nối TCP lỗi nhưng socket local được | Các HBA rules/local-vs-host khác |
| Rotation xong vẫn có sessions cũ | Thay password không terminate backend cũ |

### 40.1. Không kết luận từ một thông báo duy nhất

Một số errors được làm chung để tránh leak thông tin hoặc có nhiều nguyên nhân. Hãy đối chiếu server logs, cấu hình HBA, role metadata và client settings theo quyền được cấp.

### 40.2. Không thử password bằng cách in ra

Việc copy secret vào SQL query/log thường tạo thêm sự cố. Dùng new connection test với secret injection an toàn.

### 40.3. Không giảm bảo mật để tìm cách kết nối

Tắt TLS, dùng trust hoặc cho superuser đăng nhập chỉ để vượt lỗi có thể làm môi trường test chạy nhưng tạo rủi ro production. Chẩn đoán đúng lớp.

## 41. Quy trình phân tích lỗi một kết nối mới

~~~text
Kết nối không thành công
         |
         v
 DNS / network / port tới server?
         |
         +-- Không -> kiểm tra endpoint, firewall, listen_addresses
         |
         v
 TLS handshake/certificate OK?
         |
         +-- Không -> CA, hostname, certificate, TLS proxy
         |
         v
 pg_hba.conf có rule đầu tiên khớp?
         |
         +-- Không -> type, db, user, source CIDR, SSL, order
         |
         v
 Role LOGIN và verifier/password đúng?
         |
         +-- Không -> secret version, rotation, SCRAM support
         |
         v
 SCRAM/channel binding negotiation OK?
         |
         +-- Không -> client version, TLS/PLUS capability
         |
         v
 Database CONNECT / schema/table rights?
         |
         +-- Không -> GRANT/RLS/ownership
         |
         v
 Query hoạt động, không in secret
~~~

### 41.1. Xác định first-match HBA

Một rule rộng phía trên có thể nuốt connection trước rule SCRAM. Xem toàn bộ thứ tự, không chỉ grep dòng username.

### 41.2. Xác định client thực

JDBC driver, psql/libpq, ODBC, BI connector và proxy đều có compatibility riêng. Nếu CLI psql đăng nhập được nhưng Java không, có thể vì driver/TLS settings chứ không phải server password.

### 41.3. Xác định new vs reused connection

Một pool giữ session cũ không chứng minh password mới hợp lệ. Tạo kết nối mới bằng client tương đương app.

### 41.4. Xác định credential version

Secret manager có thể phát v2 nhưng app đọc cache v1. Dùng non-secret version ID/metadata để chẩn đoán mà không hiển thị password.

## 42. pg_hba_file_rules không tự là bản đồ tấn công toàn diện

View `pg_hba_file_rules</BT> giúp kiểm tra parse và thứ tự các rule theo khả năng server, nhưng không trả lời toàn bộ:

- Firewall có mở port không?
- Server có listen trên interface nào?
- Proxy có thay source IP không?
- TLS certificate đã được client verify-full chưa?
- Client có thực sự chọn SCRAM-PLUS không?
- Role có còn sessions cũ không?
- Secret có bị log ra ngoài không?

### 42.1. Đánh giá cấu hình theo đường đi thực tế

Một HBA rule chặt trên server nhưng một proxy trung gian cho phép public connections có thể thay threat model. Xem topology của production.

### 42.2. HBA không phải secret distribution system

HBA chỉ chọn auth method và phạm vi IP/user/database; nó không cung cấp password cho app hoặc quản lý vòng đời secret.

### 42.3. IP allowlist không thay credential

Một service nằm đúng CIDR nhưng có secret bị lộ vẫn là rủi ro; ngược lại có password đúng nhưng IP không được phép cũng không kết nối được nếu HBA/network policy cấm.

## 43. Tại sao connection pooling liên quan đến hiệu năng SCRAM?

SCRAM dùng quá trình dẫn xuất và xác minh trong handshake, có chi phí CPU nhất định. Nếu ứng dụng mở connection mới cho mỗi SQL statement, nó vừa tăng network/TLS/SCRAM handshake overhead, vừa tạo áp lực số lượng sessions.

### 43.1. Dùng pool vừa phải

Tái sử dụng connections giúp giảm số lần handshake, giảm overhead đăng nhập, nhưng pool quá lớn có thể chiếm nhiều RAM và backend resources của PostgreSQL.

### 43.2. Pool không có nghĩa giữ secret mãi

Một pool giữ credential có thể khiến rotation chậm và rủi ro tồn tại dài hơn. Cần cơ chế refresh/drain và kiểm tra new connections.

### 43.3. SSL/TLS và auth không phải chỉ số request latency

Nếu query 100ms chủ yếu vì thiếu index, tối ưu SCRAM handshake sẽ không làm câu SQL nhanh hơn trên connection đã mở. Đo riêng connection-setup latency và query execution latency.

### 43.4. Connection storms

Khi secret đổi đồng loạt hoặc PostgreSQL failover, nhiều app instances có thể reconnect cùng lúc, gây tải authentication/TLS cao. Cần backoff, jitter, pool sizing và rollout theo đợt.

### 43.5. Không giảm SCRAM work factor tùy ý

Security cost và performance phải cân bằng theo phiên bản/cấu hình đã hỗ trợ. Thay đổi các tham số mật mã mà không có đánh giá an ninh không phải cách sửa connection storm; thường nên xử lý pooling và retry.

## 44. Managed PostgreSQL và authentication không dùng password truyền thống

Một số môi trường cung cấp:

- Client certificate authentication.
- Kerberos/GSSAPI hoặc SSPI trong hệ thống tích hợp tương ứng.
- Peer authentication cho local system accounts.
- Cloud-provider token/IAM-based database authentication.
- Connection proxies hoặc identity-aware gateways.

### 44.1. Khi nào SCRAM phù hợp?

Khi dịch vụ cần credential mật khẩu PostgreSQL truyền thống và các clients hỗ trợ SCRAM. Đây là giải pháp tốt nếu secret được quản lý đúng.

### 44.2. Khi nào cân nhắc cơ chế khác?

Nếu tổ chức đã có identity platform và hỗ trợ tokens ngắn hạn/client certificates đáng tin cậy, chúng có thể giảm khối lượng quản lý password dài hạn trong một số use cases.

### 44.3. Không mặc định token cloud là SCRAM

Một token được truyền vào field password theo cơ chế của nhà cung cấp chưa chắc được PostgreSQL tự xử lý như SCRAM verifier truyền thống. Cần theo tài liệu/kiến trúc xác thực của provider.

### 44.4. Kế hoạch migration phải xét nền tảng

Managed services có thể không cho sửa trực tiếp `pg_hba.conf</BT> hoặc xem `pg_authid</BT>. Dùng management interface và quyền phù hợp, không cố vượt hạn chế của provider.

## 45. Tách môi trường và role identities

Một nguyên tắc vận hành:

~~~text
Development:
  db-dev.example.test
  role app_orders_dev
  secret ref /dev/orders/db

Staging:
  db-stage.example.test
  role app_orders_stage
  secret ref /stage/orders/db

Production:
  db-prod.example.test
  role app_orders_prod
  secret ref /prod/orders/db
~~~

### 45.1. Không dùng lại production password ở dev

Nếu máy dev hoặc CI bị tấn công, credential riêng giúp hạn chế lateral movement.

### 45.2. Không dùng chung admin role

Ứng dụng chỉ phục vụ SELECT/INSERT/UPDATE không cần CREATEROLE, CREATEDB hoặc SUPERUSER.

### 45.3. Không khôi phục secret production xuống môi trường test

Một bản restore production có thể cần xử lý roles/passwords hoặc harden access theo chính sách. Không đưa credentials thật vào môi trường có bảo mật kém hơn chỉ vì cần test dữ liệu.

### 45.4. Đặt tên và ownership

Tên role nên giúp truy vết service/workload; tài liệu hóa owner, quyền, rotation cadence, điều kiện thu hồi và emergency access.

## 46. Incident response khi nghi lộ password

Một sự cố có thể phát hiện qua repository leak, log leak, alert từ vault, hoạt động đăng nhập bất thường hoặc truy vấn không mong đợi.

### 46.1. Khoanh vùng trước

Xác định secret nào, role nào, database nào, quyền đến đâu, những môi trường nào đang dùng, khả năng attacker có verifier hay plaintext.

### 46.2. Thu hồi/khoanh vùng

Tùy mức độ, rotate password, revoke secret, NOLOGIN role, terminate suspicious sessions, giảm network exposure và khóa khả năng dùng lại.

### 46.3. Quan sát lịch sử

Xem PostgreSQL logs/connection records, application traces và audit logs theo phạm vi được phép. Những công cụ này có thể không lưu mọi query; cần tránh kết luận “không thấy log nên không có truy cập”.

### 46.4. Kiểm tra backup và bản sao

Nếu verifier hoặc secret nằm trong backup, CI artifacts, telemetry hoặc lịch sử Git, xác định khả năng người khác đã lấy các bản sao đó.

### 46.5. Phục hồi an toàn

Tạo credential mới, đảm bảo permissions tối thiểu, cập nhật secret distribution, deploy pool mới, test TLS/SCRAM, rồi theo dõi sau cutover.

### 46.6. Rút kinh nghiệm mà không tiết lộ thêm

Viết postmortem gồm nguyên nhân, tác động, thời gian, biện pháp và control improvements; tuyệt đối không chèn plaintext password/verifier vào báo cáo.

## 47. Những hiểu lầm phổ biến

### 47.1. “SCRAM nghĩa password không thể bị đoán khi verifier lộ”

Sai. Salt/work factor tăng chi phí đoán nhưng password yếu vẫn là rủi ro.

### 47.2. “SCRAM tự mã hóa toàn bộ SQL traffic”

Sai. Cần TLS để bảo vệ kênh và dữ liệu ứng dụng.

### 47.3. “sslmode=require tương đương verify-full”

Không phải một bảo đảm chung. verify-full kiểm tra hostname cùng CA theo mô hình tương ứng.

### 47.4. “SCRAM-SHA-256-PLUS là mật khẩu dài hơn”

Sai. PLUS liên quan TLS channel binding, không phải độ dài password.

### 47.5. “Channel binding=require luôn hoạt động qua mọi proxy”

Sai. Cần xác minh hỗ trợ và cách proxy xử lý TLS.

### 47.6. “Đổi password_encryption là đổi hết verifier cũ”

Sai. Passwords hiện có phải được đặt lại/xoay vòng.

### 47.7. “pg_hba.conf có một dòng SCRAM nghĩa mọi login đều dùng SCRAM”

Sai. Rule first-match, type, database, user, address và SSL quyết định.

### 47.8. “Khi HBA auth thất bại, PostgreSQL thử rule kế tiếp”

Sai. Không có kiểu fallback qua rules sau khi một rule đã khớp.

### 47.9. “hostssl tự kiểm tra client certificate”

Sai. hostssl yêu cầu kết nối TLS theo rule, không tự đồng nghĩa mTLS/client certificate authentication.

### 47.10. “HBA md5 luôn có nghĩa server thực hiện MD5”

Không đúng trong các versions có behavior chuyển sang SCRAM khi verifier của role là SCRAM.

### 47.11. “HBA scram-sha-256 dùng được với verifier MD5 cũ”

Sai trong tình huống thông thường; cần SCRAM verifier tương ứng.

### 47.12. “Password verifier không nhạy cảm vì không phải plaintext”

Sai. Nó cần được bảo vệ như vật liệu xác thực nhạy cảm.

### 47.13. “Có quyền LOGIN là có SELECT trên mọi bảng”

Sai. Authentication và authorization khác nhau.

### 47.14. “GRANT SELECT trên table tự có USAGE schema”

Không mặc định; kiểm tra schema privileges.

### 47.15. “Dùng postgres superuser cho service là cách đơn giản nhất”

Có thể dễ ban đầu nhưng tạo blast radius rất lớn.

### 47.16. “\password chỉ là cú pháp khác của hard-coded SQL password”

Không. Nó hỗ trợ nhập password tương tác và tránh một số rò rỉ plaintext trong lịch sử câu SQL.

### 47.17. “Environment variable tự động an toàn hơn file”

Không luôn. Cả hai có threat model và đường rò rỉ khác nhau.

### 47.18. “Base64-encoded Kubernetes Secret là encrypted”

Sai. Base64 là encoding.

### 47.19. “Dùng URL-encoding trong PostgreSQL URI là bảo mật”

Sai. Nó chỉ giúp biểu diễn ký tự.

### 47.20. “Lưu password trong source code rồi đặt repository private là đủ”

Sai. Quyền clone, history, backups và CI logs vẫn là rủi ro.

### 47.21. “Secret manager tự cập nhật password trong PostgreSQL”

Không nhất thiết. Cần orchestration hoặc tính năng rotation tích hợp cụ thể.

### 47.22. “Đổi password sẽ tự ngắt toàn bộ connections cũ”

Sai. Existing authenticated sessions thường tiếp tục cho đến khi đóng/terminate.

### 47.23. “Pool vẫn query được nghĩa password mới đã đúng”

Sai. Pool có thể tái sử dụng sessions cũ.

### 47.24. “VALID UNTIL vô hiệu hóa mọi phương thức auth và session”

Sai. Nó chủ yếu liên quan thời hạn password auth, không thay NOLOGIN/session revocation.

### 47.25. “PASSWORD NULL giống NOLOGIN”

Sai. Vai trò có thể xác thực bằng phương thức khác nếu HBA cho phép.

### 47.26. “Terminate backend không ảnh hưởng transaction”

Sai. Nó có thể rollback giao dịch và làm ứng dụng lỗi.

### 47.27. “Một role dùng được cho mọi service và mọi môi trường”

Không nên mặc định; quyền tối thiểu và rotation isolation thường tốt hơn khi tách roles.

### 47.28. “Java JDBC dùng tất cả libpq properties y nguyên”

Không đảm bảo. Driver version và cách cấu hình TLS/channel binding khác nhau.

### 47.29. “pg_stat_ssl cho biết chính xác SCRAM method đã dùng”

Không. Nó cho trạng thái TLS, không thay lịch sử auth negotiation.

### 47.30. “Secret không còn ở branch mới nghĩa đã hết lộ”

Sai. Nó có thể vẫn nằm trong Git history, CI artifacts hoặc bản sao đã tải.

## 48. Bài tập thực hành

### Bài 1 — Ba lớp

Phân biệt authentication, authorization và TLS transport security bằng ví dụ kết nối PostgreSQL.

**Gợi ý:** SCRAM kiểm tra danh tính, GRANT cho phép đọc bảng, TLS bảo vệ đường truyền.

### Bài 2 — Verifier

SCRAM verifier có phải plaintext password không?

**Đáp án:** Không; nó là dữ liệu dẫn xuất cho xác thực.

### Bài 3 — Salt

Tại sao SCRAM dùng salt?

**Gợi ý:** Hạn chế dùng chung precomputed hashes và làm các verifier từ password giống nhau ít trùng.

### Bài 4 — Work factor

Iteration count giúp gì?

**Gợi ý:** Tăng chi phí thử đoán password offline.

### Bài 5 — Password yếu

Một password ngắn, phổ biến có an toàn chỉ vì dùng SCRAM không?

**Đáp án:** Không.

### Bài 6 — TLS

SCRAM có tự mã hóa kết quả query trả về không?

**Đáp án:** Không; cần TLS theo yêu cầu bảo mật.

### Bài 7 — verify-full

Vì sao verify-full đáng ưu tiên hơn chỉ mã hóa TLS?

**Gợi ý:** Xác minh danh tính endpoint server qua CA/hostname.

### Bài 8 — PLUS

SCRAM-SHA-256-PLUS bổ sung lớp gì?

**Đáp án:** TLS channel binding.

### Bài 9 — Proxy

Một proxy kết thúc TLS có thể ảnh hưởng channel binding=require không?

**Đáp án:** Có thể; cần xác minh topology và capability.

### Bài 10 — HBA

`pg_hba.conf</BT> có những thành phần quan trọng nào để match rule?

**Gợi ý:** Type, database, user, address và method.

### Bài 11 — First-match

Một dòng trust rộng đứng trước scram cho cùng connection. Dòng nào có thể được chọn?

**Đáp án:** Dòng trust đứng trước nếu khớp.

### Bài 12 — Không fallback

Nếu rule đầu khớp nhưng password sai, PostgreSQL có tự thử rule sau không?

**Đáp án:** Không.

### Bài 13 — hostssl

hostssl yêu cầu điều gì?

**Gợi ý:** TCP/IP connection dùng TLS/SSL.

### Bài 14 — Local

Vì sao kết nối Unix socket khác kết nối 127.0.0.1?

**Gợi ý:** Match HBA type khác nhau.

### Bài 15 — md5 migration

Tại sao cần kiểm tra client version trước khi chuyển mọi HBA sang SCRAM?

**Gợi ý:** Client cũ có thể không hỗ trợ SCRAM.

### Bài 16 — password_encryption

Sau khi đổi setting sang SCRAM, mọi role tự có SCRAM verifier chưa?

**Đáp án:** Chưa.

### Bài 17 — \password

Lệnh psql nào giúp đặt lại password tương tác?

**Đáp án:** `\password role_name</BT>.

### Bài 18 — pg_authid

Có nên in rolpassword từ pg_authid lên ticket hỗ trợ không?

**Đáp án:** Không.

### Bài 19 — pg_roles

Viết query xem role có LOGIN và thời hạn mật khẩu mà không lộ verifier.

~~~sql
SELECT rolname, rolcanlogin, rolvaliduntil
FROM pg_roles
WHERE rolname = 'scram_demo_login';
~~~

### Bài 20 — Least privilege

Service chỉ đọc bảng healthcheck cần các quyền gì?

**Gợi ý:** CONNECT database, USAGE schema, SELECT table theo cấu hình hiện tại.

### Bài 21 — Permission error

SCRAM thành công nhưng SELECT báo permission denied. Lớp nào có vấn đề?

**Đáp án:** Authorization.

### Bài 22 — HBA debug

View nào giúp thấy các rules và lỗi parse của HBA?

**Đáp án:** `pg_hba_file_rules</BT> khi có quyền.

### Bài 23 — Reload

`pg_reload_conf()</BT> có tự chứng minh HBA parse và auth đều đúng không?

**Đáp án:** Không.

### Bài 24 — New connection

Tại sao phải tạo kết nối mới sau rotation?

**Gợi ý:** Session cũ đã xác thực trước đó.

### Bài 25 — .pgpass

Cấu trúc năm trường của .pgpass là gì?

**Gợi ý:** host:port:database:user:password.

### Bài 26 — File permissions

Trên Unix, permission tối thiểu hay dùng cho ~/.pgpass là gì?

**Đáp án:** 0600.

### Bài 27 — PGPASSWORD

Nêu hai cách environment secret có thể bị lộ.

**Gợi ý:** Process inspection, debug logs, CI output.

### Bài 28 — URI

Vì sao password trong PostgreSQL URI nguy hiểm dù URL-encoded?

**Gợi ý:** URI có thể được log và encoding đảo ngược được.

### Bài 29 — Java

Làm sao JDBC nhận password mà không hard-code trong source code?

**Gợi ý:** Lấy từ secret manager, đưa vào properties trong memory theo API được hỗ trợ.

### Bài 30 — Connection pooling

Vì sao app bắt đầu lỗi sau rotation khi pool mở connection mới?

**Gợi ý:** Pool còn secret cũ/đã tái sử dụng session cũ.

### Bài 31 — Một role

Một role password-based có hỗ trợ hai password active độc lập mặc định không?

**Đáp án:** Không theo cách thông thường.

### Bài 32 — Hai login roles

Hai roles A/B cùng thừa hưởng một NOLOGIN privilege role giúp gì?

**Gợi ý:** Cutover secret giảm gián đoạn.

### Bài 33 — VALID UNTIL

VALID UNTIL có tự đóng current sessions không?

**Đáp án:** Không.

### Bài 34 — NOLOGIN

NOLOGIN khác PASSWORD NULL thế nào?

**Gợi ý:** Chặn login role với các connection mới so với loại bỏ khả năng password authentication.

### Bài 35 — Terminate

Vì sao phải cân nhắc trước pg_terminate_backend trong production?

**Gợi ý:** Cắt transaction, gây lỗi/retry.

### Bài 36 — Secret manager

Một ứng dụng đọc secret từ vault thì PostgreSQL password có tự đổi không?

**Đáp án:** Không nhất thiết.

### Bài 37 — Workload identity

Tại sao tốt hơn hard-code token để đọc vault?

**Gợi ý:** Tránh một secret tĩnh khác và giới hạn quyền workload.

### Bài 38 — Kubernetes

Data được mã hóa base64 trong Kubernetes Secret có phải được mã hóa an toàn tự động không?

**Đáp án:** Không.

### Bài 39 — Git leak

Nếu lỡ commit password, xóa commit mới nhất là đủ chưa?

**Đáp án:** Không; phải rotate/revoke và đánh giá lịch sử.

### Bài 40 — Backup

Tại sao backup PostgreSQL cần cùng mức bảo vệ nhạy cảm?

**Gợi ý:** Có thể chứa dữ liệu và vật liệu xác thực.

### Bài 41 — pg_stat_ssl

pg_stat_ssl cho biết điều gì và không cho biết điều gì?

**Gợi ý:** TLS status nhưng không xác nhận client verify-full hoặc SCRAM-PLUS.

### Bài 42 — Managed service

Vì sao không phải mọi cloud PostgreSQL cho sửa pg_hba.conf trực tiếp?

**Gợi ý:** Provider quản lý network/auth policy qua lớp riêng.

### Bài 43 — Endpoint certificate

Kết nối verify-full bằng IP trong khi certificate chỉ có hostname có thể lỗi vì sao?

**Gợi ý:** Hostname/SAN mismatch.

### Bài 44 — Zero-trust

Có IP allowlist rồi có cần password và TLS không?

**Đáp án:** Vẫn cần theo threat model; các lớp bảo vệ bổ trợ nhau.

### Bài 45 — Log redaction

Liệt kê năm loại dữ liệu không nên xuất hiện trong log kết nối.

**Gợi ý:** Password, SCRAM verifier, URI chứa secret, token, private key.

### Bài 46 — Rotation checklist

Liệt kê ít nhất sáu bước của quy trình rotation.

**Gợi ý:** Sinh secret mới, chuẩn bị clients, update verifier, phân phối, reset pools, test new connections, monitor, revoke old.

### Bài 47 — Credential incident

Nếu password bị lộ và attacker có session đang mở, chỉ đổi password đã đủ chưa?

**Đáp án:** Chưa; cần xử lý sessions và điều tra.

### Bài 48 — Auth không dùng password

Nêu hai phương án authentication khác có thể phù hợp tùy môi trường.

**Gợi ý:** Client certificates, GSS/SSPI, peer, provider IAM tokens.

### Bài 49 — Migrate MD5

Vì sao cần inventory cả batch jobs và BI clients trước khi chuyển HBA?

**Gợi ý:** Client ít chạy có thể chỉ lỗi sau khi migration tưởng hoàn tất.

### Bài 50 — Thiết kế tổng thể

Một hệ thống Java có ba services, mỗi service dùng PostgreSQL, chạy trên Kubernetes, và đang dùng cùng một password superuser hard-code trong application.yml. Hãy đề xuất quy trình cải thiện có kiểm soát.

**Gợi ý:** Tách role per service và per environment, quyền tối thiểu, SCRAM verifiers, TLS verify-full, HBA đúng source CIDR, secret manager/workload identity, bỏ secrets khỏi Git/CI, rotation theo hai login roles hoặc giai đoạn, connection pool refresh, audit/new-connection tests và thu hồi superuser credential bị dùng sai.

## 49. Checklist triển khai SCRAM an toàn

### 49.1. Server và HBA

- [ ] PostgreSQL version hỗ trợ SCRAM theo kiến trúc hiện tại.
- [ ] `password_encryption</BT> đặt phù hợp cho passwords mới.
- [ ] Những login roles cần SCRAM đã được đặt lại password.
- [ ] HBA rules chọn `scram-sha-256</BT> theo database/user/address đúng.
- [ ] Thứ tự HBA không bị một rule trust/md5 rộng nuốt trước.
- [ ] Remote production access yêu cầu TLS đúng chính sách.
- [ ] Không mở CIDR rộng hơn nhu cầu.
- [ ] HBA parser không báo lỗi.
- [ ] Đã thử **new connections** từ đúng đường truy cập.

### 49.2. TLS và client

- [ ] Client dùng TLS và xác minh CA/hostname khi phù hợp.
- [ ] Certificate SAN/hostname và CA chain đúng.
- [ ] Libpq/JDBC/ODBC/BI driver versions hỗ trợ SCRAM.
- [ ] Channel binding policy được kiểm tra trên toàn tuyến.
- [ ] Proxy/load balancer không làm sai giả định TLS.
- [ ] Có retry/backoff tránh connection storms.
- [ ] Các pools được thiết kế refresh credentials khi rotate.

### 49.3. Roles và authorization

- [ ] Ứng dụng không dùng superuser.
- [ ] Roles phân tách theo workload/môi trường.
- [ ] Chỉ cấp CONNECT/USAGE/SELECT/INSERT/... cần thiết.
- [ ] RLS và role inheritance được kiểm tra nếu sử dụng.
- [ ] Không cấp CREATEROLE/CREATEDB/REPLICATION vô cớ.
- [ ] VALID UNTIL/NOLOGIN có chính sách rõ.
- [ ] Đã test dưới role ứng dụng thật, không chỉ admin.

### 49.4. Secrets và vận hành

- [ ] Password được sinh ngẫu nhiên, đủ mạnh.
- [ ] Không tái sử dụng giữa services/environments.
- [ ] Secret lưu trong vault hoặc cơ chế bảo vệ thích hợp.
- [ ] Không hard-code trong source/IaC/logs.
- [ ] CI/CD và container secrets được bảo vệ bằng IAM/RBAC.
- [ ] Không in verifier/plaintext password khi kiểm tra.
- [ ] Có owner, rotation process, revocation plan.
- [ ] Backup/telemetry/heap dumps có chính sách bảo vệ.
- [ ] Có quy trình thu hồi sessions nếu compromise.
- [ ] Có playbook sự cố và kiểm tra reconnect sau rotation.

## 50. Bảng tra cứu nhanh

| Khái niệm | Ghi nhớ |
|---|---|
| SCRAM-SHA-256 | Challenge–response password authentication |
| SCRAM verifier | Salt/work-factor-derived authentication data, vẫn nhạy cảm |
| SCRAM-SHA-256-PLUS | SCRAM có TLS channel binding |
| TLS | Mã hóa/bảo vệ transport |
| `sslmode=verify-full</BT> | Xác minh CA và hostname |
| `channel_binding=require</BT> | Yêu cầu channel binding khi client/server hỗ trợ |
| `pg_hba.conf</BT> | Quy tắc chọn authentication method theo connection |
| `hostssl</BT> | Chỉ khớp TCP/IP connection qua TLS |
| HBA first-match | Rule khớp đầu tiên quyết định method; không fallback |
| `trust</BT> | Không xác minh password cho kết nối khớp; rủi ro nếu rộng |
| `scram-sha-256</BT> | HBA method yêu cầu SCRAM |
| `md5</BT> | Legacy method; cần kế hoạch loại bỏ |
| `password_encryption</BT> | Cách tạo password verifier mới |
| `\password</BT> | psql prompt giúp tránh SQL literal plaintext |
| `pg_roles</BT> | Metadata role ít nhạy cảm hơn pg_authid |
| `pg_authid</BT> | Catalog chứa vật liệu xác thực, kiểm soát chặt |
| `pg_hba_file_rules</BT> | Kiểm tra parse và thứ tự HBA |
| `pg_reload_conf()</BT> | Yêu cầu reload config, không tự kiểm chứng login |
| `pg_stat_ssl</BT> | Trạng thái TLS các sessions |
| LOGIN | Role có thể đăng nhập |
| CONNECT | Quyền kết nối database |
| USAGE schema | Quyền dùng namespace |
| GRANT table | Quyền truy cập dữ liệu |
| Least privilege | Chỉ cấp quyền công việc cần |
| `~/.pgpass</BT> | Password file cho libpq trên Unix |
| `PGPASSFILE</BT> | Chọn đường dẫn password file |
| `PGPASSWORD</BT> | Env password, có rủi ro lộ |
| JDBC Properties | Truyền password tách URI/source code |
| Secret manager | Quản lý và phân phối secrets theo quyền |
| Workload identity | Danh tính dịch vụ lấy secret |
| Connection pool | Tái dùng sessions, ảnh hưởng rotation |
| Rotation | Cập nhật DB verifier và client secret |
| Dual login roles | Cắt chuyển A/B gần như không gián đoạn |
| NOLOGIN | Vô hiệu hóa khả năng đăng nhập mới |
| VALID UNTIL | Giới hạn hiệu lực password theo semantics |
| Existing session | Không tự bị ngắt khi password đổi |
| pg_terminate_backend | Chấm dứt backend khi có quyền/đánh giá |
| Secret leak | Cần rotate/revoke, không chỉ xóa text |
| CI logs/IaC state | Có thể chứa secrets, phải bảo vệ |
| TLS proxy | Có thể ảnh hưởng source IP và channel binding |

---

## Kết luận

**SCRAM-SHA-256 là cơ chế xác thực mật khẩu hiện đại của PostgreSQL** dựa trên challenge–response và password verifier có salt/work factor, giúp tránh gửi plaintext password trực tiếp trong handshake. Biến thể **SCRAM-SHA-256-PLUS** có thể bổ sung TLS channel binding. Nhưng SCRAM không tự mã hóa toàn bộ SQL traffic, không bảo đảm client đã xác minh server certificate và không thay quyền truy cập dữ liệu; cần kết hợp **TLS verify-full**, **HBA đúng thứ tự**, và **role privileges tối thiểu**.

Hai cấu hình rất dễ bị nhầm là `password_encryption</BT> và `pg_hba.conf</BT>. Cấu hình thứ nhất ảnh hưởng cách tạo **verifier cho mật khẩu mới**; cấu hình thứ hai chọn **phương thức xác thực cho connection**. Đổi password_encryption không tự chuyển toàn bộ passwords cũ, và một dòng HBA SCRAM đặt sau rule rộng không bảo đảm nó sẽ được dùng. Mỗi thay đổi phải được xác nhận bằng **kết nối mới** từ đúng client/endpoint, không dựa vào sessions cũ trong pool.

**Quản lý thông tin bí mật là một quy trình vòng đời**, không phải một dòng `password=...</BT> trong cấu hình ứng dụng. Hãy sinh secrets mạnh, không tái sử dụng, lưu trong kho được kiểm soát, tránh xuất chúng ra source code/CI/logs/URI, cấp quyền theo workload identity, chuẩn bị rotation và quản lý pool reconnects. Với môi trường yêu cầu cắt chuyển ít gián đoạn, hai login roles thừa hưởng một privilege role có thể giúp chuyển secrets theo từng đợt. Khi credential bị lộ, phải nhớ **đổi mật khẩu không tự chấm dứt các sessions đã đăng nhập**.

Nguyên tắc cuối cùng: **xác thực bằng SCRAM đúng cơ chế, bảo vệ đường truyền bằng TLS, giới hạn hành động bằng quyền PostgreSQL, và vận hành secret như tài sản nhạy cảm có owner, rotation, revocation, monitoring và incident response**.
