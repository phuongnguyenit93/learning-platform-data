# DDL privilege

Một ứng dụng chỉ cần đọc và cập nhật đơn hàng nhưng tài khoản kết nối lại sở hữu toàn bộ bảng. Khi ứng dụng gặp lỗi SQL injection hoặc credential bị lộ, kẻ sử dụng credential không chỉ sửa dữ liệu mà còn có thể thay cấu trúc bảng, bỏ ràng buộc hoặc tạo đối tượng tồn tại lâu dài.

Một tình huống khác: pipeline migration dùng chung tài khoản quản trị database với đội vận hành. Không ai phân biệt được thay đổi đến từ release nào, quyền không hết hạn sau triển khai và một script sai đích có thể tác động nhiều schema.

DDL privilege là khả năng định nghĩa, thay đổi hoặc loại bỏ các đối tượng database theo mô hình quyền của hệ quản trị. Trong Privileged Access Management (PAM), đây là đặc quyền thay đổi cấu trúc và hành vi của hệ thống, cần được cấp theo nhiệm vụ, phạm vi và vòng đời.

Bài học sử dụng nguyên tắc chung, kết hợp ví dụ được giới hạn rõ cho PostgreSQL 18. Cú pháp và ngữ nghĩa quyền khác nhau giữa các hệ quản trị; không dùng một câu lệnh mẫu như chính sách chung cho mọi database.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt quyền DDL, quyền thao tác dữ liệu và quyền quản lý danh tính.
- Đánh giá quyền từ ownership, membership, grant và đường thực thi gián tiếp.
- Tách principal runtime, migration, quản trị và kiểm toán.
- Thiết kế quy trình cấp quyền DDL tạm thời gắn với bản migration được duyệt.
- Kiểm soát khóa, tính tương thích ứng dụng và khả năng phục hồi khi thay đổi schema.
- Kiểm chứng quyền đã thu hồi và các đối tượng hoặc khả năng truy cập còn tồn dư.

## 2. DDL privilege bao gồm những gì?

DDL thường gắn với các thao tác như tạo bảng, sửa cấu trúc cột, tạo index, thay constraint hoặc xóa đối tượng. Phạm vi còn có thể bao gồm schema, view, routine, trigger, type và các đối tượng khác tùy hệ quản trị.

Không nên xem DDL là một bit quyền duy nhất. Cần xác định chính xác:

```text
Principal nào
  + được thực hiện hành động gì
  + trên loại đối tượng nào
  + trong database / schema nào
  + bằng ownership hay grant nào
  + trong thời hạn và điều kiện nào
```

Ví dụ:

> Job triển khai được phép thay đổi những đối tượng thuộc schema billing trong database production được chỉ định, bằng artifact migration đã duyệt, trong cửa sổ triển khai được cấp.

Mô tả này vẫn cần ánh xạ sang quyền thực tế của engine. Nếu quyền sở hữu cho phép nhiều hành động hơn artifact được duyệt, phải ghi nhận giới hạn đó và bổ sung kiểm soát đường thực thi.

### 2.1. Phân biệt DDL, DML và quản lý quyền

| Nhóm hành động | Ví dụ | Câu hỏi PAM cần đặt |
| --- | --- | --- |
| Định nghĩa đối tượng | Tạo hoặc sửa bảng, index, view | Ai được thay cấu trúc và hành vi? |
| Thao tác dữ liệu | Đọc, thêm, sửa, xóa hàng | Ai được tiếp cận và thay đổi dữ liệu? |
| Quản lý quyền | Cấp role, grant, thay membership | Ai có thể ủy quyền hoặc mở rộng quyền? |
| Quản trị nền tảng | Đổi cấu hình, extension hoặc tài nguyên hệ thống | Có cần đặc quyền cao hơn phạm vi ứng dụng không? |

Cách phân loại câu lệnh và quyền cụ thể không hoàn toàn giống nhau giữa các engine. Ví dụ, một thao tác làm trống bảng có thể có privilege riêng và ngữ nghĩa transaction riêng; không kết luận nó được phép chỉ vì tài khoản có quyền xóa hàng.

Đối với PAM, tác động thực tế quan trọng hơn nhãn phân loại: hành động có thể làm mất dữ liệu, phá tính toàn vẹn hoặc tạo đường thực thi đặc quyền hay không?

### 2.2. Quyền sửa cấu trúc có thể ảnh hưởng dữ liệu

Một thay đổi không đọc dữ liệu ra ngoài vẫn có thể:

- Xóa cột chứa dữ liệu cần thiết.
- Thay kiểu dữ liệu và làm chuyển đổi không như mong đợi.
- Bỏ constraint kiểm tra tính hợp lệ.
- Thay định nghĩa view khiến dữ liệu được lộ cho nhóm khác.
- Thêm trigger hoặc routine thay đổi cách xử lý giao dịch.
- Tạo đối tượng chiếm dung lượng hoặc gây quá tải.
- Làm ứng dụng cũ không còn tương thích.

Không đánh giá DDL là ít nhạy cảm chỉ vì script không có câu SELECT xuất dữ liệu.

## 3. Bốn lớp cần kiểm kê

### 3.1. Quyền cấp trực tiếp

Đọc các grant hiện có trên database, schema và đối tượng liên quan. Phân biệt quyền dùng schema, quyền tạo đối tượng, quyền thao tác dữ liệu và quyền ủy quyền.

Không suy rằng quyền ở cấp database luôn bao phủ mọi đối tượng bên trong. Phải xác định cơ chế của engine và phạm vi thực tế.

### 3.2. Ownership

Trong một số hệ quản trị, khả năng sửa hoặc xóa đối tượng gắn với quyền sở hữu hơn là một privilege độc lập tên ALTER hoặc DROP.

PostgreSQL quy định quyền sửa hoặc hủy đối tượng gắn với owner; quyền này không phải một grant thông thường có thể thu hồi riêng để biến owner thành tài khoản ít quyền. Quyền CREATE trên schema cho phép tạo đối tượng ở đó, không tự trao ownership của mọi bảng hiện có. [Mô hình privilege PostgreSQL 18](https://www.postgresql.org/docs/18/ddl-priv.html).

Vì vậy, kiểm kê chỉ dựa trên danh sách GRANT có thể bỏ sót principal đang sở hữu đối tượng.

### 3.3. Role membership và chuyển vai trò

Một login không có grant trực tiếp vẫn có thể sử dụng quyền qua role khác.

Trong PostgreSQL 18, khả năng thừa hưởng quyền và khả năng SET ROLE phụ thuộc membership tương ứng. Một role NOLOGIN vẫn có thể được sử dụng qua membership; NOLOGIN không đồng nghĩa role đó không tạo ra khả năng thực thi. [Role membership](https://www.postgresql.org/docs/18/role-membership.html).

Cần kiểm tra cả chuỗi role và khả năng ủy quyền tiếp. Không chỉ xem thuộc tính của login cuối cùng.

### 3.4. Đường thực thi gián tiếp

Người hoặc workload có thể tác động DDL mà không tự gửi SQL tới database, chẳng hạn:

- Sửa artifact mà migration runner tin cậy.
- Sửa cấu hình hoặc credential của runner.
- Điều khiển một công cụ quản trị có backend quyền cao.
- Sửa routine hoặc cấu hình liên quan tới đường thực thi có đặc quyền.
- Thay nguồn triển khai khiến job khác thực hiện DDL thay mình.

Quyền ghi vào repository migration, quyền duyệt release và quyền sửa runner cũng cần được quản trị tương ứng. Một tài khoản database được bảo vệ tốt vẫn có thể bị lạm dụng nếu mọi người được thay script mà nó tự chạy.

## 4. Rủi ro của quyền DDL quá rộng

| Quyền hoặc khả năng | Tác động cần đánh giá |
| --- | --- |
| Tạo đối tượng trong schema dùng chung | Xung đột tên, thay đường phân giải hoặc mở rộng bề mặt thực thi |
| Sửa bảng | Ảnh hưởng dữ liệu, tương thích ứng dụng và khóa |
| Xóa đối tượng | Mất cấu trúc hoặc dữ liệu, ảnh hưởng các phụ thuộc |
| Sửa view hoặc routine | Thay logic truy cập hoặc xử lý dữ liệu |
| Tạo trigger | Thêm hành vi khi dữ liệu được thay đổi |
| Chuyển ownership | Tạo người kiểm soát mới và quyền tồn dư |
| Cấp quyền tiếp | Mở rộng principal có thể thao tác |
| Quyền quản trị toàn instance | Vượt ranh giới một ứng dụng hoặc một database |
| Điều khiển migration pipeline | Thực thi SQL bằng danh tính của hệ thống triển khai |

### 4.1. DDL và tính sẵn sàng

Một migration hợp lệ về cú pháp và quyền vẫn có thể làm ứng dụng chậm hoặc dừng.

Tác động có thể đến từ thời gian chờ khóa, giữ khóa, xây dựng index, ghi log giao dịch, đồng bộ replica hoặc thay đổi kế hoạch truy vấn. Cần kiểm tra trên dữ liệu và tải đại diện.

Có quyền thực hiện không có nghĩa nên thực hiện ngay, cũng không có nghĩa thao tác đó phù hợp cửa sổ vận hành hiện tại.

### 4.2. DDL và khả năng duy trì truy cập

Một người dùng quyền cao trong thời gian ngắn có thể tạo đối tượng hoặc grant tiếp tục tồn tại sau khi phiên kết thúc.

Do đó, JIT không chỉ là hết hạn credential. Cần kiểm tra thay đổi ownership, role, routine, trigger, job và các đối tượng khác được tạo trong thời gian có quyền.

Không khẳng định mọi đối tượng đó đều là độc hại. Cần đối chiếu chúng với artifact và phạm vi thay đổi đã được phép.

## 5. Tách danh tính theo chức năng

Một mô hình tham khảo:

```text
Ứng dụng runtime
  → role thao tác dữ liệu cần thiết

Pipeline migration
  → danh tính triển khai riêng
  → quyền thay đổi đối tượng trong phạm vi ứng dụng

Người quản trị
  → quyền quản trị theo nhiệm vụ, nâng quyền khi cần

Người kiểm toán
  → đọc metadata và bằng chứng phù hợp

Hệ thống cấp quyền
  → quản lý grant theo hồ sơ và vòng đời
```

### 5.1. Runtime không mặc định sở hữu bảng

Ứng dụng thường cần một tập DML phù hợp với nghiệp vụ. Việc ứng dụng sở hữu bảng khiến credential runtime có thêm năng lực thay cấu trúc và quản trị đối tượng.

Tắt tính năng tự tạo schema trong framework không làm quyền database tự biến mất. Ngược lại, cấu hình không cho framework tự chạy migration cũng không ngăn một người cầm credential gửi DDL trực tiếp.

Kiểm soát phải có tại database và những đường thực thi có liên quan.

### 5.2. Migration là workload đặc quyền

Migration runner cần principal riêng, chủ sở hữu rõ ràng và cơ chế nhận credential phù hợp.

Không dùng credential runtime để triển khai schema rồi giữ nguyên quyền đó cho ứng dụng sau release. Cũng không đưa credential quản trị người dùng vào CI như một secret dùng chung vô thời hạn.

Credential ngắn hạn hoặc cấp phát từ vault có thể giảm thời gian bí mật tồn tại, nhưng không tự giới hạn những câu SQL mà principal được phép chạy.

### 5.3. Owner role không đăng nhập trực tiếp

Một thiết kế có thể dùng role owner ổn định không đăng nhập trực tiếp và danh tính migration được phép sử dụng role đó theo nhiệm vụ.

Lợi ích là tách quyền sở hữu đối tượng khỏi một login cá nhân hoặc một credential triển khai cụ thể. Tuy nhiên, bất kỳ principal nào được sử dụng owner role vẫn có năng lực owner trong phạm vi đó.

Nếu tất cả đối tượng của một ứng dụng thuộc cùng owner, một lần cấp role này có thể cho phép sửa nhiều hơn một bảng. Đây là giới hạn phải được ghi nhận khi chọn mức phân chia ownership.

### 5.4. Người quản trị và người phê duyệt

Người viết migration không nhất thiết được tự cấp quyền production hoặc thay artifact sau khi đã được duyệt.

Tùy mức tác động, cần tách viết, review, phê duyệt và thực thi. Với đội nhỏ, có thể dùng kiểm soát bù phù hợp nhưng phải giữ được bằng chứng ai đã làm gì.

Không biến yêu cầu tách trách nhiệm thành một biểu mẫu hình thức trong khi một người vẫn sửa được cả artifact, phê duyệt và credential runner.

## 6. Ví dụ PostgreSQL 18: tách runtime và owner

Ví dụ chỉ dùng trong database lab được phép. Không chạy nguyên khối trên production. Các role đăng nhập của người hoặc workload đã được hệ thống quản trị danh tính cấp trước; ví dụ không tạo password.

Giả sử:

- `migration_login` là login của phiên triển khai.
- `runtime_login` là login thử nghiệm cho ứng dụng.
- Các login đã được phép kết nối tới đúng database lab.
- Chưa tồn tại schema và role mẫu bên dưới.

### 6.1. Chuẩn bị ownership và role runtime

Được thực hiện bởi principal quản trị có thẩm quyền:

```sql
CREATE ROLE pam_lab_owner NOLOGIN;
CREATE ROLE pam_lab_runtime NOLOGIN;

CREATE SCHEMA pam_lab AUTHORIZATION pam_lab_owner;

REVOKE CREATE ON SCHEMA pam_lab FROM PUBLIC;
GRANT USAGE ON SCHEMA pam_lab TO pam_lab_runtime;

GRANT pam_lab_runtime TO runtime_login
  WITH INHERIT TRUE, SET FALSE;
```

Role runtime được phép sử dụng schema nhưng không được ví dụ này cấp quyền tạo đối tượng tại đó.

Điều đó không bảo đảm runtime_login không có quyền từ nơi khác. Cần kiểm tra ownership, membership, grant cho PUBLIC và các đặc quyền quản trị mà login có thể đang nhận.

### 6.2. Cấp khả năng sử dụng owner role cho phiên migration

Trong phạm vi đã được duyệt, principal quản trị có thẩm quyền có thể thiết lập membership cho login triển khai:

```sql
GRANT pam_lab_owner TO migration_login
  WITH INHERIT FALSE, SET TRUE;
```

Trong ví dụ, login không tự thừa hưởng quyền qua membership này nhưng được phép chuyển sang role đích. Đây không phải rào cản ngăn login chủ động nâng quyền; nó chỉ làm hành vi chuyển vai trò rõ ràng hơn.

Không thêm quyền ủy quyền membership nếu không có nhu cầu. Hệ thống cấp quyền cần quản lý thời hạn bên ngoài câu lệnh này; GRANT trên không tự có TTL.

### 6.3. Tạo đối tượng bằng đúng owner

Trong kết nối migration riêng:

```sql
SELECT session_user, current_user, current_database();

SET ROLE pam_lab_owner;

CREATE TABLE pam_lab.orders (
    order_id bigint PRIMARY KEY,
    state text NOT NULL
);

GRANT SELECT, INSERT, UPDATE
ON TABLE pam_lab.orders
TO pam_lab_runtime;

RESET ROLE;
```

Khi session chuyển sang role được phép, quyền kiểm tra theo role hiện hành. Tách `session_user` và `current_user` giúp giải thích principal kết nối với principal hiệu lực trong ví dụ. [SET ROLE](https://www.postgresql.org/docs/18/sql-set-role.html).

Bảng dùng khóa được cung cấp trực tiếp để tránh làm ví dụ phụ thuộc vào quyền sequence. Nếu thiết kế thật có sequence hoặc đối tượng phụ khác, cần phân tích quyền tương ứng thay vì mặc định quyền bảng bao phủ mọi thứ.

### 6.4. Kiểm chứng runtime bằng đường đăng nhập thật

Dùng kết nối thật của runtime_login để kiểm tra:

- Đọc và thay đổi dữ liệu theo tập quyền được cấp.
- Không tạo bảng trong schema nếu không có đường cấp CREATE khác.
- Không sửa hoặc xóa bảng nếu không sở hữu hay nhận khả năng tương đương.
- Không chuyển sang pam_lab_owner.
- Không truy cập schema ngoài nhiệm vụ.

Không chỉ dùng một phiên quản trị rồi giả định kết quả tương đương đường xác thực và quyền thực tế của runtime.

### 6.5. ALL PRIVILEGES không phải ownership

Trong PostgreSQL, tập privilege của một đối tượng và ownership là các khái niệm khác nhau. Không suy rằng GRANT ALL trên bảng là cách cấp một quyền ALTER phổ quát, cũng không dùng một cú pháp GRANT ALTER tưởng tượng cho mọi engine.

Mặt khác, ALL có thể cấp nhiều quyền hơn runtime cần, chẳng hạn các hành động riêng trên bảng ngoài tập DML đã xác định. Chỉ chọn những privilege thật sự cần theo ngữ nghĩa engine. [Cú pháp và phạm vi GRANT](https://www.postgresql.org/docs/18/sql-grant.html).

## 7. Đối tượng mới và default privileges

Một thiết kế quyền có thể đúng với bảng hiện có nhưng sai với bảng được tạo ở release tiếp theo.

Cần xác định:

- Role nào thực sự tạo đối tượng?
- Đối tượng mới thuộc owner nào?
- Runtime có được cấp quyền cần thiết không?
- Có grant ngoài ý muốn cho nhóm rộng hoặc PUBLIC không?
- Routine, sequence và đối tượng phụ có chính sách riêng không?

PostgreSQL áp dụng ALTER DEFAULT PRIVILEGES cho đối tượng được tạo trong tương lai, không sửa quyền của đối tượng đã tồn tại. Role hiện hành tạo đối tượng có ý nghĩa đối với default privileges được áp dụng. [Default privileges PostgreSQL 18](https://www.postgresql.org/docs/18/sql-alterdefaultprivileges.html).

Nếu mọi bảng tương lai không cùng mức dữ liệu và cùng người dùng, tự động cấp một tập DML cho tất cả bảng mới có thể quá rộng. Có thể chọn grant rõ trong migration hoặc phân chia schema và owner theo phạm vi phù hợp.

Không sửa quyền mặc định chỉ để một release chạy qua lỗi mà không kiểm tra ảnh hưởng tới các đối tượng sẽ được tạo sau đó.

## 8. Quy trình cấp quyền DDL theo nhiệm vụ

Một luồng tham khảo:

```text
Đề xuất thay đổi
    |
    v
Review SQL, phụ thuộc và tác động
    |
    v
Phê duyệt artifact, đích và cửa sổ chạy
    |
    v
Cấp quyền / credential cho migration runner
    |
    v
Xác minh đích, chạy và quan sát
    |
    v
Kiểm tra schema, ứng dụng và quyền
    |
    v
Thu hồi, đóng phiên và lưu bằng chứng
```

### 8.1. Hồ sơ yêu cầu

Nên có ít nhất:

| Thông tin | Mục đích |
| --- | --- |
| Database và môi trường | Tránh chạy đúng SQL trên sai đích |
| Schema và đối tượng | Xác định phạm vi tác động |
| Artifact hoặc version migration | Xác định chính xác nội dung được phép |
| Principal thực thi | Liên kết workload với thay đổi |
| Người review và phê duyệt | Chứng minh thẩm quyền |
| Cửa sổ thực hiện | Giới hạn thời gian vận hành |
| Dự kiến khóa và tải | Đánh giá tính sẵn sàng |
| Tương thích và phục hồi | Xác định cách dừng hoặc xử lý khi lỗi |
| Điều kiện thu hồi | Kết thúc quyền và phiên |

Một ticket có mã hợp lệ không thay thế phê duyệt đúng nội dung. Nếu script thay đổi sau review, phải xác định lại nó còn thuộc phạm vi đã được phép hay không.

### 8.2. Gắn phê duyệt với artifact

Có thể liên kết release với version, commit và digest của artifact bất biến theo thiết kế pipeline.

Runner phải xác minh artifact thực sự được chạy, không chỉ ghi digest trong ticket trong khi vẫn tải một script có thể bị sửa tự do.

Nếu job nhận tên schema, database hoặc danh sách đối tượng từ client, đối chiếu với hồ sơ và nguồn tin cậy. Không để người dùng đổi một tham số thành schema của ứng dụng khác rồi dùng cùng credential owner rộng.

### 8.3. Quyền database và phạm vi SQL được duyệt

Trong mô hình owner, việc cấp quyền để thêm một cột có thể đồng thời cho phép nhiều thay đổi khác đối với các đối tượng cùng owner.

Vì vậy, một approval “chỉ thêm cột external_reference” không tự biến thành một giới hạn tại database nếu engine chỉ kiểm tra ownership.

Có thể giảm rủi ro bằng:

- Chia owner hoặc schema theo phạm vi phù hợp.
- Chỉ cho runner nhận artifact đã được duyệt.
- Hạn chế truy cập tương tác tới credential của runner.
- Review những thao tác phá hủy hoặc quản lý quyền.
- Audit câu lệnh và đối chiếu kết quả.
- Dùng một giao diện tác vụ hẹp nếu cần cưỡng chế chức năng cụ thể.

Một bộ lọc chuỗi đơn giản không thay thế phân tích SQL và mô hình quyền. SQL có nhiều dạng biểu diễn, phụ thuộc và hành vi gián tiếp; không tuyên bố đã giới hạn DDL chỉ bằng kiểm tra tiền tố câu lệnh.

## 9. Thời hạn quyền, credential và phiên

Có ba vòng đời khác nhau:

1. **Quyền:** grant hoặc membership cho phép principal thực hiện hành động.
2. **Credential:** phương tiện để principal xác thực.
3. **Phiên:** kết nối đã được thiết lập và trạng thái hiệu lực bên trong.

Chúng không mặc định kết thúc cùng lúc.

### 9.1. JIT cần cơ chế thực thi

Một trường expires_at trong hồ sơ không tự thu hồi membership ở database. Hệ thống phải có thành phần kết thúc quyền, phát hiện lỗi và kiểm tra kết quả.

Nếu tác vụ vẫn đang chạy khi tới hạn, cần chính sách đã xác định: không cho bắt đầu việc mới, yêu cầu gia hạn hoặc xử lý dừng an toàn. Không ngắt giữa một thao tác nhạy cảm mà không đánh giá trạng thái transaction và tác động phục hồi.

### 9.2. Hết hạn password không phải TTL toàn bộ quyền

Trong PostgreSQL, VALID UNTIL giới hạn hiệu lực password, không phải thời hạn của toàn bộ role, và không được áp dụng như một cơ chế hết hạn đăng nhập cho mọi phương thức xác thực. [CREATE ROLE PostgreSQL 18](https://www.postgresql.org/docs/18/sql-createrole.html).

Cũng không coi thời hạn này là lệnh chấm dứt mọi kết nối đã mở. Thiết kế JIT phải xử lý phiên và đường quyền theo cơ chế thực tế.

### 9.3. Tách pool migration khỏi pool runtime

Không dùng chung một connection pool cho ứng dụng thường ngày và tác vụ nâng quyền nếu thiết kế không bảo đảm cách ly trạng thái.

Một kết nối đã SET ROLE hoặc thay cấu hình session có thể được tái sử dụng ngoài mong đợi nếu reset không đúng. Tách principal, pool và vòng đời giúp giảm rủi ro và làm audit dễ giải thích hơn.

Không dựa duy nhất vào việc ứng dụng “nhớ RESET ROLE” như ranh giới bảo mật. Principal có khả năng chuyển lại role quyền cao vẫn có khả năng đó khi membership còn hiệu lực.

### 9.4. Credential của runner

Runner chỉ nên nhận credential khi cần, trong phạm vi job và qua cơ chế được quản trị. Không in connection string chứa bí mật vào log.

Khi luân chuyển credential, xác minh job mới dùng giá trị mới và giá trị cũ được xử lý theo cơ chế xác thực. Đổi password không được báo cáo là đã đóng mọi phiên cũ nếu chưa kiểm chứng.

## 10. Kiểm soát khóa và transaction

### 10.1. Đánh giá loại thao tác cụ thể

DDL có thể chờ khóa hoặc giữ khóa xung đột với hoạt động đang chạy.

Trong PostgreSQL, nhiều dạng ALTER TABLE và một số thao tác cấu trúc lấy mức khóa có tác động lớn; CREATE INDEX thông thường và CREATE INDEX CONCURRENTLY có hành vi khóa khác nhau. Phải đọc yêu cầu của đúng dạng câu lệnh, không suy từ tên chung “DDL”. [Cơ chế khóa PostgreSQL 18](https://www.postgresql.org/docs/18/explicit-locking.html).

Cần xem:

- Kích thước đối tượng và tải ghi.
- Transaction đang mở lâu.
- Thời gian chờ và thời gian giữ khóa dự kiến.
- Tài nguyên CPU, I/O và dung lượng phát sinh.
- Ảnh hưởng tới replica hoặc các consumer phụ thuộc.
- Điều kiện dừng và người được quyết định can thiệp.

### 10.2. Timeout là giới hạn vận hành, không thay thế phân quyền

Ví dụ migration lab có thể đặt timeout tại transaction:

```sql
BEGIN;

SET LOCAL ROLE pam_lab_owner;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '45s';

ALTER TABLE pam_lab.orders
    ADD COLUMN external_reference text;

COMMIT;
```

Các giá trị thời gian chỉ minh họa cách đặt giới hạn cho một tác vụ; không phải khuyến nghị áp dụng nguyên cho production.

Cần kiểm tra engine, loại câu lệnh và công cụ migration có hỗ trợ cách chạy này không. Nếu câu lệnh lỗi, runner phải xử lý trạng thái transaction trước khi tiếp tục hoặc trả kết nối.

Một principal có thể tự thay timeout của nó thì đây không phải giới hạn bảo mật độc lập. Cần xác định kiểm soát nào do runner hoặc nền tảng cưỡng chế và kiểm soát nào chỉ là cấu hình trong script.

### 10.3. Không mặc định mọi DDL đều rollback được như nhau

Ngữ nghĩa transaction của DDL phụ thuộc engine và câu lệnh.

Ngay trong PostgreSQL, CREATE INDEX CONCURRENTLY không chạy trong transaction block; khi lỗi có thể cần xử lý trạng thái index còn lại. Không bọc mọi migration vào BEGIN/COMMIT rồi giả định đã giải quyết khả năng phục hồi. [CREATE INDEX PostgreSQL 18](https://www.postgresql.org/docs/18/sql-createindex.html).

Với hệ quản trị khác, phải kiểm tra thêm hành vi implicit commit hoặc các hạn chế tương ứng. Một migration đã chạy thử thành công trên engine khác không chứng minh hành vi production.

### 10.4. Đừng retry mù quáng

Khi kết nối mất, có thể chưa rõ thay đổi đã commit hay chưa.

Runner cần đối chiếu trạng thái migration, schema thực tế và kết quả phù hợp trước khi chạy lại. Tên đối tượng tồn tại chưa chứng minh định nghĩa của nó đúng.

Các tùy chọn bỏ qua khi đối tượng đã tồn tại có thể hỗ trợ một số tình huống nhưng không tự xác minh cấu trúc, quyền và nội dung mong muốn.

## 11. Tương thích ứng dụng và phục hồi

### 11.1. Thay đổi schema là thay đổi hợp đồng

Một ứng dụng cũ có thể vẫn hoạt động trong khi phiên bản mới đang triển khai. Xóa hoặc đổi tên cột ngay có thể làm một phần hệ thống lỗi.

Một mô hình triển khai có thể chia thành:

1. **Mở rộng:** thêm cấu trúc tương thích với phiên bản hiện tại.
2. **Chuyển đổi:** triển khai ứng dụng và xử lý dữ liệu chuyển tiếp.
3. **Thu hẹp:** loại bỏ cấu trúc cũ sau khi các bên phụ thuộc đã chuyển.

Các bước cần được thiết kế theo tình huống thực tế. Đây không phải bảo đảm rằng mọi thay đổi đều có thể không gián đoạn.

### 11.2. Phân biệt rollback ứng dụng và phục hồi dữ liệu

Rollback binary không tự đảo một thay đổi schema đã phá hủy dữ liệu. Một script down migration cũng không tự tạo lại giá trị của cột đã bị xóa.

Phương án cần nêu:

- Có thể đảo thay đổi hay phải tiến tới một trạng thái sửa chữa khác?
- Dữ liệu nào có thể mất hoặc cần chuyển đổi lại?
- Backup hoặc khả năng khôi phục đã được kiểm chứng chưa?
- Khi phục hồi có ảnh hưởng giao dịch mới và hệ thống phụ thuộc không?
- Ai quyết định dừng, rollback ứng dụng hoặc khôi phục dữ liệu?

Không cấp credential backup rộng cho mọi migration runner chỉ để dễ xử lý rollback. Đường khôi phục dữ liệu có quyền và thẩm quyền riêng.

### 11.3. Quyền sửa constraint và logic

Thêm hoặc bỏ constraint, thay view, routine hoặc trigger cần review không chỉ về cú pháp mà cả tác động nghiệp vụ.

Một thay đổi nhỏ có thể làm dữ liệu mới không còn được kiểm tra hoặc thay người có thể nhìn thấy thông tin. Đối chiếu chính sách dữ liệu, owner và cách thực thi sau migration.

Nếu cơ chế chạy routine có ngữ cảnh đặc quyền riêng, cần kiểm tra người được gọi, người được sửa nội dung và các phụ thuộc có thể bị thay thế. Không để quyền DDL trở thành đường mở rộng truy cập ngoài nhiệm vụ.

## 12. Audit thay đổi DDL

Một chuỗi bằng chứng hữu ích cần nối được:

```text
Người đề xuất
  → artifact đã review
  → quyết định phê duyệt
  → principal nhận quyền
  → session và role hiệu lực
  → câu lệnh / đối tượng thay đổi
  → kết quả và schema cuối
  → thu hồi và kiểm tra tồn dư
```

### 12.1. Dữ liệu cần ghi nhận

| Nhóm | Nội dung minh họa |
| --- | --- |
| Nguồn thay đổi | Release, commit, artifact, digest |
| Danh tính | Login kết nối, role hiệu lực, workload runner |
| Đích | Instance, database, schema, đối tượng |
| Thời gian | Bắt đầu, kết thúc, các mốc cấp và thu hồi quyền |
| Hoạt động | Loại thao tác, tham chiếu câu SQL được bảo vệ |
| Kết quả | Thành công, thất bại, trạng thái chưa xác định |
| Quyền | Grant, membership hoặc ownership thay đổi |
| Phục hồi | Hành động sửa lỗi và kết quả đối chiếu |

Nếu nhiều job cùng dùng một login, cần thêm liên kết đáng tin tới job và người khởi phát. Một nhãn ứng dụng do client tự khai không nên là bằng chứng duy nhất để quy trách nhiệm.

### 12.2. Bảo vệ log và bí mật

Migration có thể chứa dữ liệu khởi tạo nhạy cảm, giá trị cấu hình hoặc câu lệnh liên quan credential. Không ghi mọi thứ vào log CI đọc rộng mà không phân loại.

Cần biết audit của engine ghi được những loại thao tác nào và có bỏ sót thay đổi qua đường quản trị khác không. Kết hợp metadata, artifact được bảo vệ và kết quả thực tế theo mục đích kiểm toán.

Người có quyền quản trị database có thể tác động các cơ chế audit trong phạm vi nhất định. Đánh giá nơi lưu và miền quản trị bằng chứng; log nằm ngoài database chưa chắc độc lập nếu cùng principal còn quyền xóa kho đích.

### 12.3. Ghi nhận thất bại và trạng thái không rõ

Một dòng “migration failed” không đủ để kết luận schema chưa thay đổi.

Audit và pipeline cần phân biệt chưa bắt đầu, đã gửi lệnh, đang chạy, đã commit, thất bại và chưa xác định. Khi phải xử lý tay, liên kết các thay đổi đó với cùng hồ sơ thay vì để thành một phiên quản trị không có dấu vết.

## 13. Thu hồi quyền sau migration

### 13.1. Kết thúc đường cấp quyền

Với ví dụ lab, principal quản trị có thẩm quyền có thể kết thúc membership được cấp cho đợt triển khai:

```sql
REVOKE pam_lab_owner FROM migration_login;
```

Câu lệnh này mô tả một bước trong vòng đời, không phải bảo đảm mọi khả năng của login đã biến mất.

Cần kiểm tra membership gián tiếp, grant khác, ownership trực tiếp và các đặc quyền quản trị. Nếu công cụ tự động có cấu hình cấp lại quyền, xử lý đúng nguồn đó.

### 13.2. Xử lý session và role đã chuyển

Không giả định thu hồi membership sẽ chấm dứt mọi session đang mở hoặc hoàn nguyên mọi trạng thái đã có trong phiên.

Thiết kế nên dùng kết nối migration riêng, đóng sau job và có nhánh xử lý kết nối còn sống, transaction đang chạy hoặc role hiệu lực chưa trở về trạng thái mong muốn.

Nếu cần kết thúc phiên bằng quyền quản trị, đánh giá tác động và xác định đúng phiên. Không đóng hàng loạt kết nối production chỉ dựa trên một tên role không đủ phân biệt workload.

### 13.3. Đối chiếu ownership và đối tượng tồn dư

Những câu hỏi cần trả lời:

- Đối tượng mới có đúng owner đã thiết kế không?
- Có đối tượng thuộc login tạm sắp bị xóa không?
- Có grant, role hoặc khả năng ủy quyền ngoài artifact không?
- Có routine, trigger, job hoặc cấu hình mới ngoài phạm vi không?
- Runtime có nhận thêm DDL hoặc dữ liệu ngoài nhu cầu không?
- Default privileges có bị thay rộng hơn không?

Một login tạm sở hữu đối tượng có thể khiến việc dọn role khó hơn. Không dùng lệnh dọn toàn bộ đối tượng của role như một bước cleanup máy móc; chúng có thể chứa dữ liệu hoặc quan hệ cần giữ.

### 13.4. Khả năng truy cập sau cùng

Thử lại đường đăng nhập và các hành động tiêu biểu trong phạm vi được phép:

- Runtime vẫn hoàn thành nghiệp vụ.
- Login migration không còn dùng được quyền owner theo thiết kế đã kết thúc.
- Credential cũ được xử lý đúng vòng đời.
- Các phiên và job còn tồn tại được giải thích.
- Schema cuối khớp trạng thái mong muốn.

Đổi mật khẩu không thay thế đối chiếu các đối tượng và grant đã được tạo trong thời gian có quyền.

## 14. Tình huống minh họa: thêm dữ liệu tham chiếu cho đơn hàng

Ứng dụng billing cần một cột external_reference trên bảng orders. Thiết kế ban đầu dùng tài khoản runtime làm owner và cho phép framework tự thay schema khi khởi động.

### 14.1. Xác định vấn đề

Credential runtime có khả năng thay cấu trúc ngoài hoạt động nghiệp vụ. Mỗi lần ứng dụng khởi động có thể trở thành một lần migration, khó kiểm soát review, khóa và thời điểm.

Việc người phát triển tắt tùy chọn tự đổi schema chỉ giải quyết một đường kích hoạt. Quyền owner trong database vẫn còn.

### 14.2. Thiết kế quy trình mới

Đối tượng thuộc owner role ổn định. Runtime có tập DML cần thiết. Migration đi qua job riêng, artifact được review và login triển khai nhận khả năng dùng owner role trong nhiệm vụ.

Đợt thêm cột được đánh giá về:

- Tương thích với ứng dụng cũ và mới.
- Hành vi khóa của câu lệnh cụ thể.
- Giá trị dữ liệu hiện có và bước backfill nếu cần.
- Quyền truy cập trường mới.
- Cách xác minh kết quả.
- Nhánh xử lý khi triển khai ứng dụng mới thất bại.

Nếu sau này cần bắt buộc giá trị hoặc xóa cấu trúc cũ, đó có thể là bước thay đổi riêng, không tự gộp vào cùng quyền được cấp ban đầu.

### 14.3. Thực thi và đóng

Runner xác minh database, role hiệu lực và artifact, thực hiện theo cửa sổ được phép, ghi kết quả rồi đóng kết nối.

Đội vận hành đối chiếu schema, quyền runtime và audit. Sau đó kết thúc grant triển khai, kiểm tra session còn lại và ghi những giới hạn hoặc bước theo dõi.

Kết quả tốt không chỉ là cột xuất hiện. Nó còn là runtime không còn sở hữu bảng và đường quyền migration đã được kết thúc đúng thiết kế.

## 15. Bộ kiểm tra nghiệm thu

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Runtime thực hiện DML đúng nghiệp vụ | Hoàn thành nhiệm vụ được cấp |
| Runtime thử tạo hoặc sửa bảng lab | Không có khả năng DDL ngoài thiết kế |
| Login có membership gián tiếp vào owner | Kiểm kê phát hiện đường quyền này |
| Migration trỏ sang database hoặc schema khác | Runner và quyền thực tế kiểm soát đúng phạm vi |
| Artifact bị sửa sau phê duyệt | Không âm thầm chạy nội dung mới |
| Migration tạo đối tượng mới | Owner và quyền mặc định đúng thiết kế |
| Runtime yêu cầu thao tác riêng ngoài DML được cấp | Không được cho phép do một grant ALL không được đánh giá |
| Job chờ quyền tới sau cửa sổ chạy | Kiểm tra lại hiệu lực phê duyệt và grant |
| DDL gặp khóa lâu hoặc timeout | Runner xử lý trạng thái và báo bằng chứng phù hợp |
| Kết nối mất sau khi gửi lệnh | Đối chiếu trạng thái trước retry |
| Câu lệnh không hỗ trợ transaction block | Công cụ chạy đúng chế độ đã kiểm tra |
| Grant hết hạn nhưng session còn sống | Có cơ chế xử lý và kiểm chứng |
| Login tạm sở hữu đối tượng | Có kế hoạch chuyển quyền hoặc giữ theo thiết kế |
| Người dùng có quyền sửa runner hoặc nguồn migration | Được quản trị như đường thực thi đặc quyền |
| Kết thúc release | Không còn quyền hoặc đối tượng ngoài phạm vi được giải thích |

Kiểm tra trên môi trường và đối tượng được phép. Không xóa bảng thật hoặc đọc dữ liệu thật không cần thiết để chứng minh phân quyền.

## 16. Bài tập áp dụng

Bạn nhận một database trong đó runtime_login sở hữu mọi bảng, pipeline migration dùng cùng password với DBA và một grant tạm được ghi thời hạn trong ticket nhưng không có cơ chế thu hồi.

Hãy thiết kế phương án:

1. Phân loại ownership, grant và membership hiện có.
2. Tách principal runtime, migration và quản trị.
3. Xác định tập DML thật sự cần cho ứng dụng.
4. Chọn phạm vi owner và các giới hạn còn lại.
5. Gắn phê duyệt với artifact cùng đích thực thi.
6. Kiểm soát khóa, transaction và trạng thái chưa xác định.
7. Thiết kế thu hồi quyền, đóng session và xử lý credential.
8. Xây dựng bằng chứng về schema, quyền và đối tượng tồn dư.

Một đáp án tốt nêu rõ những gì engine cưỡng chế và những gì pipeline cưỡng chế. Không chỉ đổi tên tài khoản hoặc cất password trong vault rồi coi bài toán DDL đã được giải quyết.

## 17. Tiêu chí hoàn thành

Thiết kế quản lý DDL privilege đạt mục tiêu khi có thể chứng minh:

- Phạm vi hành động và ngữ nghĩa quyền được xác định theo engine cụ thể.
- Ownership được kiểm kê cùng grant và membership.
- Runtime không mặc định cầm quyền thay cấu trúc ngoài nhiệm vụ.
- Migration có danh tính, artifact và vòng đời được quản trị.
- Quyền nhận được phù hợp phạm vi; khả năng rộng hơn artifact được ghi nhận và kiểm soát.
- Khóa, transaction, tương thích và phục hồi được đánh giá trước thực thi.
- Audit liên kết người đề xuất, job, role hiệu lực và thay đổi thật.
- Quyền, credential, session và đối tượng tồn dư được kiểm tra khi kết thúc.

Quyền DDL cho phép thay đổi nền tảng mà dữ liệu và ứng dụng dựa vào. Đưa quyền này vào PAM nghĩa là làm rõ ai được thay đổi cấu trúc, bằng nội dung nào, trên phạm vi nào và bằng chứng nào chứng minh quyền đã được kết thúc sau nhiệm vụ.

