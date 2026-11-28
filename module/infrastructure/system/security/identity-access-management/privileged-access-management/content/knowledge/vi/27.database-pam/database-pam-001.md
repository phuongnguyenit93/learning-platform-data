# Database superuser

Database superuser là danh tính hoặc trạng thái quyền có khả năng quản trị rất rộng trong một hệ quản trị cơ sở dữ liệu. Đây là quyền cần được kiểm kê và kiểm soát riêng trong Privileged Access Management (PAM), vì người sử dụng có thể tác động đồng thời tới dữ liệu, tài khoản, cấu hình và các cơ chế bảo vệ.

Khái niệm này không có một cách triển khai giống nhau trên mọi sản phẩm. Một hệ thống dùng thuộc tính SUPERUSER, hệ thống khác dùng server role quản trị, còn dịch vụ database được quản lý có thể chỉ cung cấp một tập quyền quản trị do nhà cung cấp giới hạn. Cần xác định khả năng thực tế thay vì suy từ tên tài khoản như postgres, root, admin hoặc sa.

Bài học dùng PostgreSQL 18 làm ví dụ kỹ thuật chính và đối chiếu ngắn với SQL Server, Amazon RDS for PostgreSQL. Các truy vấn minh họa chỉ phục vụ kiểm kê hoặc xác minh trong môi trường được phép; không thực hiện thao tác cấp quyền, ngắt kết nối hay thay credential trên một hệ thống thật.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao superuser khác với một role được cấp nhiều quyền thông thường.
- Phân biệt login, role, object owner, quản trị hệ điều hành và quản trị cloud.
- Nhận diện đường có thể đạt quyền cao ngoài việc đăng nhập trực tiếp.
- Tách công việc DBA thường ngày khỏi công việc thực sự cần superuser.
- Thiết kế luồng JIT, phê duyệt, vault, giám sát phiên và thu hồi.
- Hiểu giới hạn của RLS, quyền trên bảng và log nội bộ đối với một superuser.
- Xây dựng bằng chứng, kiểm thử và runbook cho tình huống credential bị lộ.

## 2. Superuser là một ranh giới quyền đặc biệt

### 2.1. Không chỉ là nhiều GRANT hơn

Trong PostgreSQL, database superuser bỏ qua các kiểm tra quyền, ngoại trừ quyền đăng nhập. Vì vậy, không thể xem việc thu hồi một quyền trên bảng khỏi superuser là cách buộc danh tính ấy tuân theo cùng giới hạn với người dùng thông thường. [Thuộc tính role trong PostgreSQL 18](https://www.postgresql.org/docs/18/role-attributes.html).

Sự khác biệt có ý nghĩa thiết kế:

~~~text
Role thông thường
    -> được phép làm việc nhờ quyền và điều kiện được cấp

Superuser
    -> có khả năng vượt nhiều ranh giới kiểm tra quyền trong engine
~~~

Nếu nhiệm vụ chỉ cần đọc một view, người sử dụng nên được cấp quyền phù hợp với view đó. Không cấp superuser rồi kỳ vọng view tiếp tục là ranh giới bắt buộc đối với họ.

### 2.2. Phạm vi có thể lớn hơn một database

Trong PostgreSQL, role được định nghĩa ở cấp database cluster, không chỉ trong một database riêng lẻ. Ở đây cluster là tập database dùng chung một PostgreSQL installation và catalog role, không phải khái niệm Kubernetes cluster. [Lệnh CREATE ROLE](https://www.postgresql.org/docs/18/sql-createrole.html).

Một người đăng nhập vào database billing không vì thế chỉ có tác động tới billing khi đang giữ trạng thái superuser. Inventory cần xác định đúng instance hoặc cluster và toàn bộ phạm vi có thể bị ảnh hưởng.

### 2.3. Superuser không thay thế xác thực

Có quyền cao bên trong engine không có nghĩa tự vượt qua mọi lớp kết nối:

- Đường mạng vẫn cần cho phép.
- Client phải đi qua cơ chế xác thực phù hợp.
- Credential hoặc phương thức xác thực vẫn cần hợp lệ.
- Điều kiện tại gateway vẫn có thể được áp dụng nếu đường đó bắt buộc.

Trong PostgreSQL, cấu hình client authentication như pg_hba.conf quyết định cách các kết nối được xác thực. Đây là lớp khác với quyền trên đối tượng sau khi đã kết nối. [Cấu hình xác thực kết nối PostgreSQL](https://www.postgresql.org/docs/18/auth-pg-hba-conf.html).

PAM nên tận dụng các ranh giới độc lập đó, đồng thời xác minh không còn đường kết nối trực tiếp phá vỡ quy trình.

### 2.4. Quyền cao không đồng nghĩa quyền root của hệ điều hành

Database superuser và root của hệ điều hành là hai khái niệm khác nhau. Tuy nhiên, một số năng lực database có thể tác động tới tệp hoặc chương trình trên máy chủ theo quyền của tiến trình database.

Ví dụ, PostgreSQL phân biệt COPY dùng phía client với thao tác tệp hoặc PROGRAM phía server; thao tác phía server chịu các kiểm tra và quyền hệ điều hành tương ứng. [Lệnh COPY của PostgreSQL](https://www.postgresql.org/docs/18/sql-copy.html).

Khi đánh giá phạm vi ảnh hưởng, cần xét tài khoản dịch vụ database, mount, dữ liệu trên máy chủ, kết nối mạng và giới hạn của dịch vụ được quản lý. Không giả định database superuser luôn là OS root, nhưng cũng không coi ranh giới SQL là ranh giới tác động cuối cùng.

## 3. Những khái niệm thường bị nhầm

| Khái niệm | Ý nghĩa cần phân biệt |
| --- | --- |
| Login | Khả năng khởi tạo kết nối bằng một danh tính |
| Role đặc quyền | Tập năng lực quản trị được engine hoặc nền tảng định nghĩa |
| Object owner | Chủ sở hữu đối tượng, có khả năng quản trị gắn với đối tượng đó |
| Database owner | Chủ sở hữu một database theo mô hình của sản phẩm |
| Database superuser | Trạng thái quyền rất rộng trong phạm vi engine |
| OS administrator | Quản trị máy chủ và tiến trình bên dưới |
| Cloud administrator | Quản trị dịch vụ, mạng, backup hoặc credential qua control plane |
| PAM administrator | Quản trị hệ thống cấp quyền, vault hoặc broker |

Các quyền có thể tạo đường tác động chéo. Ví dụ, người quản trị máy chủ có thể kiểm soát tệp hoặc tiến trình database; người quản trị cloud có thể quản lý snapshot hoặc cơ chế đặt lại tài khoản theo quyền của dịch vụ.

Vì vậy, kiểm kê Database PAM không nên dừng ở danh sách tài khoản SQL.

### 3.1. Object owner chưa chắc là superuser

Object owner có khả năng quản trị đối tượng của mình theo quy tắc engine. Điều đó có thể đủ để sửa dữ liệu, cấu trúc hoặc policy gắn với đối tượng, nhưng không nên mặc định owner là superuser toàn instance.

Ngược lại, bỏ thuộc tính superuser không bảo đảm danh tính đã ít quyền nếu nó vẫn sở hữu nhiều đối tượng, có quyền quản trị role hoặc có đường chuyển sang principal khác.

### 3.2. Tên tài khoản không phải bằng chứng quyền

Một tài khoản tên readonly có thể được cấp quyền quản trị. Một tài khoản tên postgres trong dịch vụ được quản lý có thể không có thuộc tính SUPERUSER thật.

Báo cáo phải dựa trên:

- Thuộc tính role.
- Membership và khả năng chuyển role.
- Quyền trực tiếp.
- Ownership.
- Khả năng cấp quyền tiếp.
- Chức năng hoặc cơ chế thực thi được phép.
- Ranh giới do nhà cung cấp đặt ra.

Không dùng naming convention làm kiểm soát thay cho xác minh.

## 4. Khác biệt giữa các nền tảng

### 4.1. PostgreSQL tự quản lý

PostgreSQL biểu diễn quyền superuser bằng thuộc tính role. Các thuộc tính khác như CREATEDB hoặc CREATEROLE là các khả năng riêng, không được đánh đồng với SUPERUSER.

Trong thiết kế, nên mô tả chính xác “cần tạo database”, “cần xem số liệu giám sát” hoặc “cần quản lý một nhóm role” trước khi chọn quyền. Từ “DBA” chưa đủ để xác định phải cấp superuser.

### 4.2. SQL Server

Trong SQL Server, thành viên của fixed server role sysadmin có thể thực hiện mọi hoạt động trên server và không bị giới hạn bằng DENY theo cách thông thường. Đây là lý do không nên dùng một quyền từ chối trên dữ liệu làm bảo đảm cho người vẫn giữ sysadmin. [Server-level roles trong SQL Server](https://learn.microsoft.com/en-us/sql/relational-databases/security/authentication-access/server-level-roles?view=sql-server-ver17).

Không suy rằng mọi role có chữ admin trong tên đều có cùng phạm vi với sysadmin, hoặc mô hình SQL Server tự quản lý giống mọi dịch vụ Azure SQL.

### 4.3. Amazon RDS for PostgreSQL

RDS for PostgreSQL cung cấp rds_superuser cho các công việc quản trị được dịch vụ hỗ trợ. Tài khoản quản trị của khách hàng không có PostgreSQL SUPERUSER thật và không được truy cập host OS như một PostgreSQL tự quản lý. [Vai trò rds_superuser](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Appendix.PostgreSQL.CommonDBATasks.Roles.rds_superuser.html).

Tuy vậy, quyền quản trị được quản lý vẫn có thể gây tác động lớn tới dữ liệu và tài khoản. Không hạ mức kiểm soát chỉ vì nhà cung cấp giữ lại một phần quyền.

### 4.4. Ghi phiên bản và mô hình triển khai

Mỗi bản thiết kế nên chỉ rõ:

- Engine và phiên bản.
- Tự quản lý hay dịch vụ được quản lý.
- Phạm vi instance hoặc cluster.
- Cơ chế xác thực.
- Các role quản trị được dùng.
- Chức năng bị nhà cung cấp giới hạn.
- Quyền cloud hoặc OS có thể tạo đường thay thế.

Thông tin này cần được đánh giá lại khi nâng cấp hoặc đổi nền tảng.

## 5. Tác động của một credential superuser bị lộ

### 5.1. Bảo mật dữ liệu

Một phiên quyền cao có thể tiếp cận dữ liệu vượt phạm vi ứng dụng thông thường, xuất dữ liệu hoặc tạo đường truy cập mới. Phạm vi cụ thể phụ thuộc engine và môi trường.

Cần đánh giá cả:

- Dữ liệu nghiệp vụ.
- Metadata có thể dẫn tới hệ thống khác.
- Credential hoặc secret được lưu không phù hợp.
- Backup và bản sao.
- Dữ liệu trên nhiều database cùng phạm vi quản trị.

### 5.2. Toàn vẹn

Các tác động có thể gồm:

- Sửa hoặc xóa dữ liệu.
- Đổi cấu trúc.
- Thay logic thực thi.
- Thay ownership hoặc policy.
- Tạo principal mới.
- Cấp quyền cho một danh tính khác.
- Thay cấu hình ảnh hưởng xử lý giao dịch.

Chỉ nhìn sự kiện đăng nhập sẽ không phát hiện đủ các đường duy trì quyền sau đó.

### 5.3. Tính sẵn sàng

Quyền quản trị có thể ảnh hưởng kết nối, workload, cấu hình và tài nguyên. Một thao tác hợp lệ về quyền vẫn có thể gây gián đoạn nghiêm trọng nếu dùng sai phạm vi.

PAM cần gắn quyền với runbook và mục tiêu công việc, không chỉ xác nhận người vận hành là thành viên nhóm DBA.

### 5.4. Khả năng che giấu

Nếu cùng principal có thể sửa cấu hình audit, xóa log cục bộ hoặc thay nơi xuất bằng chứng, dữ liệu điều tra có thể bị suy yếu.

Một ranh giới bảo vệ quan trọng là lưu bằng chứng ở nơi người đang sử dụng quyền database không thể tự quản trị trong cùng phạm vi đó. Phải đánh giá cả quyền cao hơn ở OS, cloud và tổ chức để biết ranh giới thực tế tới đâu.

## 6. Vì sao RLS và quyền trên bảng không giới hạn được mọi quản trị viên?

### 6.1. PostgreSQL RLS

Trong PostgreSQL, superuser và role có BYPASSRLS bỏ qua row-level security. Chủ bảng thông thường cũng bỏ qua RLS, trừ trường hợp áp dụng FORCE ROW LEVEL SECURITY cho owner. FORCE RLS không biến superuser thành principal bị RLS giới hạn. [Row Security Policies](https://www.postgresql.org/docs/18/ddl-rowsecurity.html).

Hệ quả trong thiết kế:

- RLS có thể là ranh giới cho role ứng dụng phù hợp.
- RLS không phải bảo đảm chống truy cập của PostgreSQL superuser.
- Một yêu cầu “chỉ xem dữ liệu của một tenant” không nên được thực hiện bằng phiên superuser không bị ràng buộc khác.

### 6.2. Masking và mã hóa cần được đặt trong đúng mô hình

Một view che dữ liệu hoặc cơ chế masking có thể phục vụ nhóm người dùng nhất định. Cần xác minh quản trị viên có khả năng truy cập nguồn, đổi định nghĩa hoặc đi vòng hay không.

Tương tự, mã hóa lưu trữ bảo vệ theo mô hình của lớp lưu trữ; nó không tự ngăn một engine đã được cho phép giải mã dữ liệu trả kết quả cho principal quyền cao.

Nếu mục tiêu là hạn chế ngay cả quản trị viên database tiếp cận plaintext, cần kiến trúc phân tách khóa hoặc dữ liệu tương ứng và đánh giá mọi đường truy cập. Không suy ra bảo đảm ấy chỉ từ việc bật mã hóa ở một lớp.

### 6.3. “Read-only superuser” là tuyên bố cần kiểm chứng

Một người giữ superuser nhưng chỉ được dặn chạy SELECT chưa phải danh tính chỉ đọc. Thiết lập mặc định phiên hoặc quy ước vận hành cũng chưa chắc là ranh giới người ấy không thể thay đổi.

Nếu một gateway cung cấp chức năng giới hạn, bảo đảm chỉ tồn tại trong phạm vi mà gateway thật sự thực thi và không thể bị đi vòng. Cần kiểm tra protocol, câu lệnh, chức năng được gọi và đường kết nối trực tiếp.

Ưu tiên role được engine giới hạn đúng nhu cầu khi điều đó đáp ứng được công việc.

## 7. Kiểm kê danh tính và đường đạt quyền cao

### 7.1. Inventory tối thiểu

| Thuộc tính | Ví dụ cần ghi |
| --- | --- |
| Đích | Instance hoặc cluster PostgreSQL cụ thể |
| Môi trường | Production, staging hoặc recovery |
| Principal | Login người dùng, automation hoặc tài khoản khẩn cấp |
| Owner | Người hoặc nhóm chịu trách nhiệm |
| Nguồn xác thực | Password, certificate, federation hoặc cơ chế khác |
| Đường sử dụng | Gateway, trực tiếp, local socket, job |
| Quyền cao | SUPERUSER, membership hoặc cơ chế quản trị tương ứng |
| Phạm vi | Database, cluster và hệ thống liên quan |
| Mục đích | Công việc nào thực sự cần |
| Credential | Nơi quản lý và cơ chế luân chuyển |
| Phiên | Thời hạn, khả năng refresh và ngắt |
| Bằng chứng | PAM, database audit, OS hoặc cloud audit |
| Ngoại lệ | Lý do, owner và thời hạn đánh giá |

Tài khoản không đăng nhập trực tiếp vẫn cần được xem xét nếu người khác có thể chuyển sang role đó.

### 7.2. Truy vấn role trong PostgreSQL 18

~~~sql
SELECT
    rolname,
    rolsuper,
    rolcanlogin,
    rolcreatedb,
    rolcreaterole,
    rolreplication,
    rolbypassrls,
    rolvaliduntil
FROM pg_roles
ORDER BY rolname;
~~~

pg_roles cung cấp thông tin role và che trường password. Những cột trên hỗ trợ kiểm kê thuộc tính; chúng không tự biểu diễn mọi quyền hiệu lực hoặc mọi đường đạt quyền. [View pg_roles](https://www.postgresql.org/docs/18/view-pg-roles.html).

Không cần xuất password hash để lập danh sách superuser. Bản inventory vẫn có thể chứa metadata nhạy cảm và cần giới hạn quyền đọc.

### 7.3. Membership và khả năng chuyển role

Ở PostgreSQL 18, quyền kế thừa và khả năng SET ROLE chịu ảnh hưởng của tùy chọn membership. Các thuộc tính role đặc biệt không tự được kế thừa giống quyền đối tượng; cần phân tích khả năng chuyển sang role tương ứng theo quy tắc của phiên bản. [Role membership](https://www.postgresql.org/docs/18/role-membership.html), [quy tắc thuộc tính và membership của CREATE ROLE](https://www.postgresql.org/docs/18/sql-createrole.html).

Ví dụ kiểm kê quan hệ trực tiếp:

~~~sql
SELECT
    granted_role.rolname AS granted_role,
    member_role.rolname AS member_role,
    membership.admin_option,
    membership.inherit_option,
    membership.set_option
FROM pg_auth_members AS membership
JOIN pg_roles AS granted_role
    ON granted_role.oid = membership.roleid
JOIN pg_roles AS member_role
    ON member_role.oid = membership.member
ORDER BY granted_role.rolname, member_role.rolname;
~~~

Các cột phản ánh membership trong catalog PostgreSQL 18. [Catalog pg_auth_members](https://www.postgresql.org/docs/18/catalog-pg-auth-members.html).

Truy vấn chỉ hiển thị từng cạnh trực tiếp. Khi đánh giá một principal, phải xử lý đường membership nhiều cấp và các điều kiện liên quan; không coi kết quả này là báo cáo quyền hiệu lực hoàn chỉnh.

### 7.4. Quyền ngoài catalog role

Cần kiểm kê thêm:

- Credential trong vault hoặc tệp cấu hình.
- Quyền đặt lại password qua control plane.
- Quyền quản trị máy chủ và tài khoản dịch vụ.
- Quyền sửa authentication mapping.
- Quyền đọc backup hoặc snapshot.
- Quyền tạo môi trường khôi phục từ bản sao.
- Quyền quản trị broker hoặc connector database.
- Quyền sửa automation có thể dùng credential cao.

Một principal không mang cờ rolsuper vẫn có thể kiểm soát một principal khác đang có quyền đó.

## 8. Tách công việc thường ngày khỏi superuser

### 8.1. Liệt kê nhiệm vụ trước khi cấp quyền

Một nhóm DBA có thể cần:

- Theo dõi hiệu năng.
- Xem số liệu kết nối.
- Triển khai schema.
- Quản lý một nhóm object.
- Hủy truy vấn gây ảnh hưởng.
- Vận hành backup.
- Quản lý account theo phạm vi.
- Khôi phục sự cố.
- Thực hiện thao tác đặc biệt trên engine.

Các nhiệm vụ không có cùng phạm vi và không phải tất cả đều cần superuser.

### 8.2. Sử dụng quyền chuyên biệt khi phù hợp

PostgreSQL có predefined role cho các năng lực như giám sát và một số công việc quản trị. Chúng vẫn là quyền nhạy cảm, có thể thay đổi theo phiên bản và phải được đánh giá trước khi cấp. [Predefined Roles](https://www.postgresql.org/docs/18/predefined-roles.html).

Không cần tự động cấp cả một role rộng chỉ vì nó có tên gần với công việc. Ví dụ, nhu cầu xem một chỉ số không nhất thiết cần mọi quyền giám sát toàn hệ thống.

Một ma trận nhiệm vụ có thể là:

| Nhiệm vụ | Hướng phân quyền |
| --- | --- |
| Xem dashboard | Nguồn số liệu hoặc view đã giới hạn |
| Đọc dữ liệu đối soát | View, bảng hoặc phạm vi tenant cần thiết |
| Migration schema | Role triển khai có ownership và phạm vi được quản lý |
| Chẩn đoán kết nối | Quyền giám sát phù hợp và có audit |
| Vận hành đặc biệt | Quyền chuyên biệt hoặc runbook có kiểm soát |
| Thao tác thực sự cần superuser | Phiên ngoại lệ có phê duyệt và giám sát |

### 8.3. Ứng dụng không dùng superuser để sửa lỗi thiếu quyền

Nếu ứng dụng bị permission denied, cần xác định đúng hành động, object và role đang sử dụng.

Không sửa bằng cách:

- Chuyển application user thành superuser.
- Dùng credential quản trị để chạy mọi request.
- Cho migration và runtime dùng chung tài khoản mạnh.
- Cấp quyền toàn hệ thống để tránh phải theo dõi schema mới.

Application runtime, migration, monitoring và backup nên có danh tính riêng theo nhu cầu. Cách chia cụ thể phụ thuộc engine và công cụ.

### 8.4. Automation cũng cần ranh giới

Một job chạy mỗi đêm không ít rủi ro hơn người dùng chỉ vì không có giao diện tương tác.

Cần owner, phạm vi, thời hạn credential, cơ chế refresh và bằng chứng cho mỗi lần chạy. Nếu automation có thể tự tạo superuser mới hoặc sửa connector để lấy credential khác, phải xem xét cả quyền điều khiển automation đó.

## 9. Workflow cấp quyền superuser có điều kiện

### 9.1. Trình tự tham khảo

~~~text
Nhu cầu công việc
    |
    v
Chứng minh quyền hẹp hơn không đáp ứng
    |
    v
Xác định đích, runbook, tác động và thời hạn
    |
    v
Policy hoặc người có trách nhiệm phê duyệt
    |
    v
Tạo grant và cấp đường truy cập được kiểm soát
    |
    v
Xác minh danh tính và quyền hiệu lực
    |
    v
Thực hiện, giám sát và lưu bằng chứng
    |
    v
Chặn cấp tiếp, kết thúc phiên, thu hồi và đối soát
~~~

Đây là mô hình PAM đề xuất. Không có nghĩa mọi engine có sẵn đối tượng grant hoặc khả năng hết hạn toàn bộ quyền theo một trường cấu hình.

### 9.2. Yêu cầu phải đủ cụ thể

Một yêu cầu nên nêu:

- Instance hoặc cluster đích.
- Môi trường.
- Công việc và lý do cần superuser.
- Runbook hoặc thay đổi dự kiến.
- Tác động có thể xảy ra.
- Thời gian dự kiến.
- Người thực hiện.
- Phê duyệt và owner.
- Nhu cầu recording hoặc audit.
- Phương án phục hồi nếu thao tác thất bại.

Nếu cấp true superuser, đừng ghi rằng quyền chỉ hiệu lực trên một bảng khi engine không thực thi giới hạn đó. Phạm vi nhiệm vụ được duyệt và phạm vi kỹ thuật của quyền phải được trình bày riêng.

### 9.3. Grant nghiệp vụ minh họa

~~~yaml
grantId: DB-GRANT-2841
requester: dba-017
target:
  service: billing-database
  instanceId: pg-production-01
  environment: production
requestedCapability: emergency-superuser-session
purpose: Thuc hien runbook khoi phuc da duoc danh gia
runbookReference: DB-RUNBOOK-42
approvalReference: CHG-2841
session:
  maximumDurationSeconds: 900
  monitoredAccessRequired: true
  renewalRequiresEvaluation: true
state: approved
~~~

Đây là schema PAM minh họa, không phải SQL hoặc đối tượng native của PostgreSQL.

Một thời hạn 900 giây chỉ có giá trị bảo đảm nếu hệ thống thực thi được trên đường cấp mới và có chính sách rõ cho kết nối đã tồn tại.

### 9.4. Tách phê duyệt với thực hiện theo mức tác động

Với công việc quyền cao, có thể cần người phê duyệt độc lập với người thực hiện, tùy policy của tổ chức.

Cần xác định ai có thể sửa:

- Điều kiện phê duyệt.
- Danh mục role.
- Connector.
- Quy trình cấp credential.
- Bản runbook được tin cậy.
- Chính dữ liệu grant.

Không để người xin quyền tự sửa căn cứ rồi dùng căn cứ đó để được cấp quyền.

## 10. Vault, broker và credential

### 10.1. Vault bảo vệ credential, không tự thu hẹp quyền

Đưa password superuser vào vault giúp quản lý việc lưu và lấy credential theo khả năng hệ thống. Nó không tự thay đổi quyền trong database hoặc tự đóng kết nối đang mở.

Cần xác định:

- Ai được lấy secret hoặc yêu cầu kết nối.
- Secret có lộ cho người dùng không.
- Có đường kết nối trực tiếp không.
- Ai luân chuyển credential.
- Cách xác minh credential mới và cũ.
- Hành vi khi vault không hoạt động.
- Cách tránh lộ credential trong log và công cụ client.

MFA tại cổng vault chỉ bảo vệ đường đó nếu không còn một credential hoặc phương thức khác cho phép đi vòng.

### 10.2. Hai kiểu cấp truy cập

| Kiểu | Ưu điểm có thể có | Điều cần kiểm soát |
| --- | --- | --- |
| Cấp credential cho client | Phù hợp nhiều công cụ | Khả năng sao chép, cache và dùng ngoài đường giám sát |
| Broker kết nối thay người dùng | Có thể giảm việc lộ secret và quản lý phiên | Quyền broker, khả năng protocol, đường bypass và bằng chứng danh tính |

Cần kiểm thử sản phẩm cụ thể. Không mặc định một proxy database hiểu đầy đủ mọi câu lệnh, extension hoặc giao thức liên quan.

### 10.3. Tài khoản riêng và tài khoản dùng chung

Ưu tiên truy vết tới từng người hoặc lần chạy.

Nếu bắt buộc dùng một principal database chung qua broker:

- Broker phải xác thực người dùng riêng.
- Có session ID và grant.
- Liên kết tới backend tương ứng.
- Kiểm soát truy cập trực tiếp.
- Lưu bằng chứng ngoài phạm vi người sử dụng database.
- Quản lý khả năng nhiều người dùng cùng lúc.

Một trường client tự đặt như application name hoặc comment SQL không phải bằng chứng danh tính không thể giả mạo.

### 10.4. Luân chuyển credential có kế hoạch

Luân chuyển cần kiểm tra:

- Nơi dùng credential hiện tại.
- Tác động tới job, pool và công cụ phục hồi.
- Cơ chế phân phối credential mới.
- Khả năng ngăn kết nối mới bằng credential cũ.
- Kết nối đang tồn tại.
- Cách khôi phục nếu connector mất truy cập.

Đổi password không nên được báo như thao tác đã chấm dứt toàn bộ phiên cũ. Trạng thái credential và trạng thái kết nối cần xác minh riêng.

## 11. JIT không chỉ là ngày hết hạn password

### 11.1. VALID UNTIL có phạm vi cụ thể

Trong PostgreSQL, VALID UNTIL đặt hạn cho password, không đặt hạn cho role nói chung và không áp dụng như vậy cho xác thực không dùng password. [Quy tắc VALID UNTIL](https://www.postgresql.org/docs/18/sql-createrole.html).

Vì vậy, không dùng riêng trường này để tuyên bố:

- Mọi phương thức đăng nhập đã hết hạn.
- Membership đã bị thu hồi.
- Mọi kết nối cũ đã kết thúc.
- Mọi tác vụ quyền cao đã dừng.
- Role tạm đã được dọn.

### 11.2. Phân tách các thời hạn

Một thiết kế có thể có:

- Thời hạn grant PAM.
- Thời hạn credential.
- Thời gian được mở kết nối mới.
- Thời hạn sử dụng role đặc quyền.
- Thời hạn tối đa của kết nối.
- Điều kiện gia hạn.
- Thời điểm cleanup.

Các giá trị cần liên kết nhưng không nên bị coi là một đối tượng duy nhất. Hệ thống phải biết thành phần nào thực thi mỗi mốc.

### 11.3. Cleanup role tạm cần xem ownership

Một role tạm có thể đã sở hữu object hoặc cấp quyền cho principal khác. Không nên tự động xóa hàng loạt object phụ thuộc chỉ để làm cho cleanup thành công.

Cần xác định trước:

- Role được phép tạo gì.
- Ownership dự kiến.
- Cách xử lý quyền hoặc object phát sinh.
- Cách phát hiện cleanup chưa hoàn tất.
- Owner xử lý ngoại lệ.
- Bằng chứng xác minh quyền không còn sử dụng được.

Cleanup là công việc quản trị có tác động riêng, không phải bước xóa mù sau khi đóng terminal.

## 12. Xác minh danh tính và quyền hiệu lực

### 12.1. Kiểm tra ngữ cảnh phiên PostgreSQL

~~~sql
SELECT
    session_user,
    current_user,
    current_database(),
    pg_backend_pid();
~~~

session_user và current_user có ý nghĩa khác nhau. current_user phản ánh ngữ cảnh thực thi dùng để kiểm tra quyền; SET ROLE hoặc chức năng thực thi với ngữ cảnh khác có thể làm nó thay đổi. Superuser còn có khả năng thay session authorization theo quy tắc của PostgreSQL. [Các hàm thông tin phiên](https://www.postgresql.org/docs/18/functions-info.html).

Vì vậy, kết quả truy vấn hỗ trợ kiểm tra ngữ cảnh, nhưng không thay thế bằng chứng xác thực và cấp phiên ngoài engine.

### 12.2. Xác định đúng đích

Trước thao tác đặc biệt, đối chiếu:

- Endpoint thật.
- Instance hoặc cluster.
- Database hiện tại.
- Môi trường.
- Principal đăng nhập.
- Role hiệu lực.
- Session ID của PAM và backend liên quan.
- Tình trạng primary, replica hoặc recovery nếu công việc phụ thuộc.

Một tên connection profile trong công cụ client không đủ chứng minh đích. Không dựa vào màu giao diện hoặc tên file để phân biệt production với lab.

### 12.3. Connection pool làm phức tạp truy vết

Một kết nối database có thể được dùng lại cho nhiều request. Nếu ứng dụng hoặc công cụ dùng pooling:

- Phải biết đơn vị nào ánh xạ tới người dùng.
- Phải hiểu thời điểm đổi và reset ngữ cảnh.
- Không để quyền đặc biệt rò sang người dùng kế tiếp.
- Không gán toàn bộ hoạt động của backend cho người đầu tiên đã dùng nó.

Với phiên quản trị tương tác, có thể cần tách khỏi pool dùng chung hoặc có cơ chế mapping được kiểm thử.

## 13. Audit độc lập với superuser

### 13.1. Chuỗi bằng chứng

~~~text
Danh tính người hoặc workload
        |
        v
Yêu cầu và quyết định cấp quyền
        |
        v
Grant PAM và lần lấy credential / mở kết nối
        |
        v
Login database và backend
        |
        v
Hành động, kết quả và thay đổi trạng thái
        |
        v
Kết thúc, thu hồi và hậu kiểm
~~~

Một bản ghi đăng nhập thành công không đủ trả lời đã đọc hay sửa dữ liệu nào. Ngược lại, một câu SQL trong log chưa chắc cho biết người thật nào đứng sau principal dùng chung.

### 13.2. Không mặc định log database ghi toàn bộ hoạt động cần biết

Cấu hình logging quyết định loại thông tin được ghi. Trong PostgreSQL, các lựa chọn ghi statement, thông tin kết nối và đầu ra log có ý nghĩa riêng; logging quá rộng còn có thể ghi dữ liệu nhạy cảm từ câu lệnh. [Logging trong PostgreSQL 18](https://www.postgresql.org/docs/18/runtime-config-logging.html).

Cần kiểm thử độ bao phủ cho:

- Đăng nhập và lỗi xác thực.
- Chuyển ngữ cảnh role.
- Cấp và thu hồi quyền.
- Tạo principal.
- Thay cấu hình audit.
- Truy cập dữ liệu quan trọng.
- DDL và thao tác quản trị.
- Kết quả hoặc trạng thái giao dịch khi cần.

Audit không tự bảo đảm có toàn bộ result set hay mọi tác động đã hoàn tất. Phải nêu rõ giới hạn quan sát.

### 13.3. Bảo vệ nguồn và đích log

Có thể kết hợp:

- Log engine.
- Audit chuyên biệt theo khả năng nền tảng.
- Log gateway.
- Recording client hoặc phiên nếu phù hợp.
- Log OS.
- Audit cloud.
- Lịch sử cấu hình và quyền.

Đích lưu bằng chứng cần được phân tách quyền phù hợp. Theo dõi cả việc đổi filter, tắt collector, rút ngắn retention và thay khóa mã hóa.

Không dùng một bảng audit mà superuser có thể tự sửa trong cùng database làm bằng chứng độc lập duy nhất.

### 13.4. Metadata cần giữ

Một hồ sơ phiên nên có:

- Người yêu cầu và principal trực tiếp.
- Grant, mục đích và phê duyệt.
- Đích và phiên bản hệ thống.
- Thời điểm bắt đầu, kết thúc và múi giờ.
- Session ID và thông tin backend phù hợp.
- Phạm vi audit thực tế.
- Hành động quan trọng và kết quả có thể xác minh.
- Cấu hình quyền trước và sau khi liên quan.
- Trạng thái thu hồi.
- Ngoại lệ và dữ liệu còn thiếu.

Không đưa password, token hoặc dữ liệu nghiệp vụ không cần thiết vào hồ sơ.

## 14. Kết thúc phiên và ứng phó sự cố

### 14.1. Ba việc khác nhau

| Việc | Mục tiêu |
| --- | --- |
| Chặn truy cập mới | Không cấp tiếp hoặc không cho mở kết nối mới |
| Xử lý kết nối đang tồn tại | Dừng sử dụng quyền trong phiên đã mở theo runbook |
| Xử lý tác động đã tạo | Đánh giá dữ liệu, quyền, cấu hình và tác vụ phát sinh |

Không báo cả ba đã hoàn tất chỉ vì đã khóa cổng PAM hoặc đổi password.

### 14.2. Xác định phiên trước khi can thiệp

Nếu cần hủy truy vấn hoặc kết thúc backend, phải xác minh:

- Đúng instance.
- Đúng principal.
- Đúng backend và thời điểm bắt đầu.
- Quan hệ với grant.
- Tác động tới giao dịch và ứng dụng.
- Khả năng client tự kết nối lại.

PostgreSQL có các hàm quản trị để hủy truy vấn hoặc kết thúc backend với điều kiện quyền tương ứng. Đây là các khả năng khác nhau và cần dùng theo runbook. [Hàm quản trị PostgreSQL](https://www.postgresql.org/docs/18/functions-admin.html).

Không dùng một bộ lọc rộng trên mọi session để giải quyết một sự cố của một người dùng.

### 14.3. Đóng kết nối không hoàn tác mọi thứ

Một thay đổi đã commit, dữ liệu đã xuất hoặc credential đã sao chép không tự biến mất khi phiên kết thúc.

Cần kiểm tra:

- Principal mới được tạo.
- Membership hoặc quyền mới.
- Object hoặc logic được thay.
- Cấu hình xác thực và audit.
- Job nền.
- Backup hoặc bản xuất.
- Hệ thống khác được truy cập bằng credential liên quan.

Khôi phục phải dựa trên phạm vi tác động. Không mặc định rollback một transaction có thể xử lý mọi hoạt động quản trị.

### 14.4. Credential bị lộ

Trình tự tham khảo:

1. Xác định credential, principal và phạm vi.
2. Bảo toàn bằng chứng phù hợp.
3. Chặn cấp hoặc lấy credential tiếp nếu cần.
4. Ngăn kết nối mới theo cơ chế được phép.
5. Xử lý kết nối cũ đã xác định.
6. Luân chuyển credential và xác minh connector.
7. Đánh giá quyền và thay đổi phát sinh.
8. Điều tra truy cập dữ liệu với nguồn audit hiện có.
9. Khôi phục dịch vụ hợp lệ.
10. Sửa nguồn làm lộ và hậu kiểm.

Nếu audit thiếu, phải ghi mức độ chưa biết. Không kết luận “không đọc dữ liệu” chỉ vì chỉ tìm thấy log login.

## 15. Break-glass và khả năng khôi phục

### 15.1. Cần tồn tại một đường phục hồi được kiểm soát

Quá trình giảm quyền không nên khiến hệ thống mất mọi khả năng phục hồi hợp lệ. Trước khi thay đường quản trị chính, cần có phương án khẩn cấp đã được kiểm thử theo mô hình triển khai.

Break-glass nên có:

- Owner.
- Điều kiện kích hoạt.
- Cách truy cập khi hệ thống PAM chính gián đoạn.
- Giới hạn phạm vi theo khả năng.
- Bằng chứng độc lập phù hợp.
- Cơ chế đóng quyền và luân chuyển sau sử dụng.
- Hậu kiểm.

Không dùng tài khoản khẩn cấp cho công việc thường ngày chỉ vì nó nhanh hơn quy trình chuẩn.

### 15.2. Backup có thể mang theo quyền cũ

Khôi phục từ bản sao có thể đưa lại dữ liệu, role hoặc cấu hình cũ tùy cách backup và restore.

Quy trình recovery cần đánh giá:

- Principal nào xuất hiện sau phục hồi.
- Credential nào còn dùng được.
- Quyền và membership có phù hợp không.
- Authentication và audit có đúng không.
- Endpoint mới có nằm trong inventory và giám sát không.
- Dữ liệu nhạy cảm có bị mở ở môi trường kém bảo vệ hơn không.

Không coi môi trường restore tạm là ngoài phạm vi PAM nếu nó chứa dữ liệu production hoặc credential có giá trị.

### 15.3. Broker cấp superuser cũng cần được kiểm soát

Một connector có khả năng cấp hoặc sử dụng quyền cao là tài sản đặc quyền. Cần quản lý:

- Credential bootstrap.
- Phạm vi instance.
- Quyền sửa template cấp tài khoản.
- Plugin hoặc script mà connector chạy.
- Người được quản trị cấu hình.
- Bằng chứng mỗi lần tạo quyền.
- Khả năng tự nâng quyền hoặc tạo đường tồn tại lâu dài.

Không để một người dùng tác nghiệp tùy ý gửi SQL cấp quyền cho connector chạy bằng tài khoản quản trị.

## 16. Bài thực hành: bỏ superuser khỏi ứng dụng Billing

### 16.1. Bối cảnh

Billing API dùng một tài khoản PostgreSQL có SUPERUSER vì trước đây migration và runtime dùng chung credential. Credential được nhiều pipeline và người vận hành biết.

Một báo cáo đề xuất “đưa password vào vault” nhưng giữ nguyên mọi quyền.

### 16.2. Yêu cầu phân tích

Xác định ít nhất bốn loại công việc:

- Runtime xử lý request.
- Migration.
- Monitoring.
- Quản trị khẩn cấp.

Với mỗi loại, ghi:

- Hành động cần thiết.
- Object và môi trường.
- Principal riêng.
- Cơ chế xác thực.
- Quyền cần cấp.
- Thời hạn.
- Owner.
- Bằng chứng.
- Cách thu hồi.

### 16.3. Phương án cần tạo

1. Inventory tài khoản và mọi nơi đang dùng credential chung.
2. Danh sách quyền ứng dụng thực sự cần.
3. Tách principal runtime khỏi migration và công cụ quản trị.
4. Kế hoạch xử lý ownership và membership.
5. Luồng superuser ngoại lệ có phê duyệt.
6. Kế hoạch vault và luân chuyển.
7. Cách quản lý pool và kết nối cũ.
8. Kế hoạch audit ngoài phạm vi người vận hành database.
9. Phương án break-glass và khôi phục.
10. Kiểm thử cả hành động được phép và bị cấm.

Đưa password vào vault là một phần bảo vệ credential. Nó không thay thế việc giảm quyền hay xóa đường chia sẻ cũ.

### 16.4. Ma trận kiểm thử tham khảo

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Runtime đọc và ghi đúng bảng nghiệp vụ | Hoạt động theo phạm vi được thiết kế |
| Runtime thử tạo role hoặc đổi quyền | Bị từ chối |
| Runtime thử đọc dữ liệu ngoài phạm vi | Bị giới hạn bởi quyền hoặc policy phù hợp |
| Migration chạy thay đổi được duyệt | Đúng principal và có bằng chứng |
| Monitoring thực hiện chẩn đoán cần thiết | Không cần true superuser nếu thiết kế đáp ứng |
| Người không có grant yêu cầu phiên quản trị | Bị từ chối |
| Grant staging dùng cho production | Bị từ chối |
| Superuser lab truy cập bảng có RLS | Minh chứng đúng giới hạn của RLS, không suy ra nó chặn superuser |
| Credential cũ sau luân chuyển | Không mở được kết nối mới theo thiết kế |
| Kết nối đã mở trước luân chuyển | Được xác định và xử lý riêng |
| Grant hết hạn | Ngăn cấp tiếp và xử lý phiên theo policy |
| Một principal còn membership mạnh khác | Phát hiện quyền hiệu lực còn tồn tại |
| Cấu hình audit bị thay | Có tín hiệu ở nguồn bằng chứng độc lập phù hợp |
| Restore môi trường lab từ bản sao | Rà soát lại role, credential và audit |

Các thử nghiệm quyền cao chỉ dùng dữ liệu và tài nguyên lab được phép. Không thực hiện thay đổi phá hủy production để chứng minh một tài khoản mạnh đến đâu.

## 17. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| DBA nào cũng cần superuser | Cần phân quyền theo nhiệm vụ cụ thể |
| Tài khoản có tên admin thì chắc là superuser | Xác minh thuộc tính và quyền hiệu lực |
| Cấp superuser nhưng REVOKE một bảng là đủ hạn chế | Superuser có khả năng bỏ qua kiểm tra quyền tương ứng |
| FORCE RLS chặn PostgreSQL superuser | Không tạo ranh giới như vậy |
| Vault biến tài khoản mạnh thành tài khoản ít quyền | Vault quản lý credential, engine vẫn giữ mô hình quyền |
| VALID UNTIL là TTL cho toàn bộ quyền | Trong PostgreSQL, nó chỉ có phạm vi password |
| Đổi password sẽ đóng mọi session | Cần xử lý kết nối đang tồn tại riêng |
| Không có LOGIN nghĩa là không có đường dùng role | Phải kiểm tra membership và khả năng chuyển role |
| Log nội bộ là bằng chứng độc lập tuyệt đối | Cần xét ai có thể sửa nguồn và đích log |
| Không thấy SELECT trong log nghĩa là không có truy cập | Phải kiểm tra độ bao phủ và cấu hình audit |
| Hết phiên là hết mọi tác động | Thay đổi đã commit và quyền phát sinh vẫn cần xử lý |

## 18. Chỉ số duy trì kiểm soát

Các chỉ số có ích:

- Số principal có quyền superuser hoặc tương đương.
- Tỷ lệ principal quyền cao có owner và mục đích.
- Số ứng dụng còn dùng quyền quản trị.
- Số credential quyền cao được dùng chung.
- Tỷ lệ phiên nối được người hoặc workload với grant và backend.
- Số quyền tạm chưa cleanup đúng hạn.
- Thời gian ngăn kết nối mới sau quyết định thu hồi.
- Tỷ lệ kết nối cũ được xác định và xử lý theo policy.
- Tỷ lệ công việc thường ngày đã chuyển sang quyền hẹp hơn.
- Kết quả kiểm thử break-glass và recovery.
- Số khoảng trống audit chưa có owner xử lý.
- Số thay đổi quyền không thuộc quy trình đã xác nhận.

Cần nêu engine, instance và phạm vi trong mẫu số. Việc giảm số tài khoản có cờ superuser chưa đủ nếu một tài khoản còn lại được chia sẻ cho mọi ứng dụng và người dùng.

## 19. Câu hỏi tự kiểm tra

**Vì sao superuser khác role được cấp nhiều quyền?**

Vì trạng thái này có thể bỏ qua các kiểm tra quyền trong engine, thay vì chỉ hoạt động nhờ tập quyền đối tượng đã cấp.

**Có thể dùng RLS làm ranh giới chống PostgreSQL superuser không?**

Không. Superuser và BYPASSRLS có khả năng bỏ qua RLS theo mô hình PostgreSQL.

**Một tài khoản không có SUPERUSER đã chắc ít quyền chưa?**

Chưa. Cần xét membership, ownership, quyền quản trị, cơ chế thực thi và đường OS hoặc cloud liên quan.

**Vault có tự thực hiện least privilege không?**

Không. Phải thiết kế quyền trong database và kiểm soát đường sử dụng credential.

**VALID UNTIL có đóng kết nối khi đến hạn không?**

Không nên dùng nó làm bảo đảm vòng đời phiên. Nó đặt hạn cho password trong phạm vi xác thực tương ứng, không phải hạn cho role và mọi kết nối.

**Vì sao phải lưu bằng chứng ngoài phạm vi superuser đang dùng?**

Để giảm khả năng một sự cố quyền cao đồng thời ảnh hưởng cả hoạt động lẫn nguồn bằng chứng về hoạt động đó.

**Thay password có xử lý quyền mới đã được cấp trong phiên cũ không?**

Không. Principal, membership hoặc thay đổi phát sinh cần được kiểm tra và xử lý riêng.

**Managed database có cần PAM cho tài khoản quản trị không?**

Có. Nhà cung cấp có thể giữ lại một phần quyền, nhưng phần khách hàng được sử dụng vẫn có thể gây tác động lớn.

Quản lý database superuser hiệu quả bắt đầu bằng việc giảm nhu cầu sử dụng quyền đó trong vận hành thường ngày. Khi thực sự cần, quyền phải gắn với công việc rõ ràng, danh tính có thể truy vết, credential được bảo vệ, phiên được quản lý và bằng chứng đủ độc lập để đối soát sau khi quyền đã kết thúc.
