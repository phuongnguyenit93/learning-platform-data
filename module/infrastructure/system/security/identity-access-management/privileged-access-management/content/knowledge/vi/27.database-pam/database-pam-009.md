# Temporary database role

Một kỹ sư được cấp quyền đọc dữ liệu production để xử lý sự cố trong 30 phút. Hết thời gian, hệ thống PAM đánh dấu yêu cầu đã kết thúc, nhưng membership trong database vẫn còn. Ở một tình huống khác, password hết hạn đúng giờ nhưng kết nối đã mở tiếp tục được sử dụng.

Cả hai hệ thống đều có “thời hạn” trong hồ sơ, nhưng chưa chứng minh được đặc quyền đã kết thúc.

Temporary database role là cách tổ chức khả năng truy cập database theo một nhiệm vụ và vòng đời hữu hạn. Điều tạm thời có thể là membership của một principal, một login được tạo cho từng yêu cầu hoặc một phiên đi qua cơ chế quản trị. Không có một từ khóa SQL chung bảo đảm mọi loại quyền và phiên đều tự biến mất sau một khoảng thời gian.

Trong Privileged Access Management (PAM), mục tiêu là làm rõ ai được thực hiện việc gì, trên dữ liệu nào, đến khi nào và thành phần nào thực thi việc kết thúc. Bài học sử dụng mô hình trung lập, ví dụ SQL cho PostgreSQL 18 và một phần minh họa về credential động của Vault.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt role quyền ổn định với membership hoặc login có vòng đời tạm thời.
- Thiết kế phạm vi quyền theo nhiệm vụ trước khi đặt thời hạn.
- Tách thời hạn phê duyệt, quyền, credential và phiên.
- Xây dựng luồng cấp, gia hạn, thu hồi và đối chiếu quyền thực tế.
- Nhận diện lỗi thu hồi, role mồ côi, ownership và connection pool.
- Chứng minh quyền đã kết thúc bằng kiểm tra tại database và đường sử dụng thực tế.

## 2. “Role tạm thời” có thể chỉ những thiết kế nào?

| Thiết kế | Phần ổn định | Phần tạm thời |
| --- | --- | --- |
| Membership JIT | Role chức năng như support-reader | Quyền của login được sử dụng role đó |
| Login theo yêu cầu | Mẫu quyền được quản trị | Principal và credential tạo riêng cho một lần sử dụng |
| Phiên qua cổng PAM | Principal backend hoặc nhóm quyền được quản lý | Phiên và khả năng gửi yêu cầu qua cổng |
| Credential động cho workload | Chính sách cấp credential | Credential và thường cả principal được tạo theo lease |

Các thiết kế có thể kết hợp. Ví dụ, login được tạo riêng cho một yêu cầu rồi được gán membership vào role đọc dữ liệu ổn định.

Tên role như temp_admin không tạo cơ chế hết hạn. Một role được đặt NOLOGIN cũng không đồng nghĩa không ai có thể sử dụng quyền của nó thông qua membership.

### 2.1. Role quyền và danh tính đăng nhập

Role quyền có thể dùng để gom một tập khả năng như đọc một nhóm đối tượng. Danh tính đăng nhập gắn với người hoặc workload cụ thể.

Tách hai lớp giúp tránh lặp lại toàn bộ policy khi cấp quyền cho từng yêu cầu. Nhưng phải kiểm tra khả năng thừa hưởng quyền, chuyển vai trò và ủy quyền tiếp theo ngữ nghĩa engine.

Một role ổn định không đăng nhập trực tiếp có thể vẫn rất mạnh. Cần biết ai được trở thành thành viên và ai có thể sửa tập quyền bên trong role.

### 2.2. Không nhầm với bảng tạm

Temporary role theo nghĩa PAM không phải temporary table, schema tạm hay một đối tượng SQL chỉ tồn tại trong session.

Một login được tạo bằng quy trình tự động vẫn có thể tồn tại lâu dài nếu không có cơ chế dọn hoặc thu hồi phù hợp. Việc session kết thúc không mặc định làm login đó biến mất.

## 3. Đặt phạm vi trước khi đặt TTL

Thời hạn ngắn giảm khoảng thời gian sử dụng, nhưng không sửa một tập quyền quá rộng.

Một credential quản trị toàn instance có hiệu lực vài phút vẫn có thể thực hiện thay đổi lớn hoặc tạo khả năng truy cập tồn dư.

Mô tả yêu cầu nên gồm:

```text
Chủ thể và nhiệm vụ
  + database / môi trường
  + đối tượng hoặc dữ liệu
  + hành động
  + thời điểm và điều kiện
  + quyền gia hạn / kết thúc
```

Ví dụ:

> Người được phân công xử lý incident chỉ được đọc mã và trạng thái đơn hàng trong nguồn được phép, tại database đã chỉ định, trong thời gian điều tra được duyệt; không được sửa dữ liệu, tạo đối tượng hoặc cấp quyền tiếp.

### 3.1. Phạm vi dữ liệu phải có nơi thực thi

Một trường case_id trong PAM không tự lọc các hàng database được phép đọc.

Nếu quyền cần giới hạn theo tenant, cột hoặc tập dữ liệu của vụ việc, phải có cơ chế thực thi phù hợp: privilege ở mức được hỗ trợ, view được kiểm soát, policy dữ liệu hoặc giao diện truy vấn hẹp đã được kiểm tra.

Không cấp SELECT trên toàn bộ bảng rồi tuyên bố người dùng chỉ xem được dữ liệu của ticket vì đã có mã ticket trong hồ sơ.

### 3.2. Quyền đọc vẫn là quyền nhạy cảm

Một người chỉ đọc có thể tải lượng dữ liệu lớn hoặc giữ bản sao sau khi role hết hạn.

Phạm vi cần xem xét khả năng xuất, tải, dùng công cụ trực tiếp và nơi lưu kết quả. Thu hồi quyền nguồn không kéo lại được một file đã tải.

### 3.3. Tránh quyền tạo khả năng lâu dài

Với tác vụ đọc thông thường, không cấp mặc định:

- Quyền tạo hoặc quản lý login.
- Quyền cấp role hay privilege cho người khác.
- Ownership đối tượng ứng dụng.
- Khả năng sửa routine hoặc công cụ quản trị đặc quyền.
- Quyền bỏ qua cơ chế kiểm soát dữ liệu.
- Quyền quản trị toàn database hoặc instance.

Nếu nhiệm vụ thật sự cần một khả năng nhạy cảm, mô tả nó riêng và kiểm tra tồn dư sau sử dụng.

## 4. Bốn mốc thời gian phải phân biệt

| Mốc | Ý nghĩa | Ai cần thực thi? |
| --- | --- | --- |
| Hết hiệu lực phê duyệt | Nhiệm vụ không còn được cho phép theo hồ sơ | Hệ thống quản trị yêu cầu và cấp quyền |
| Hết quyền | Principal không còn sử dụng tập quyền đã cấp | Database hoặc bộ điều khiển grant |
| Hết credential | Phương tiện xác thực không còn được chấp nhận | Cơ chế xác thực tương ứng |
| Kết thúc phiên | Kết nối và trạng thái đã mở không còn cho phép sử dụng | Database, proxy hoặc cơ chế quản lý phiên |

Không giả định bốn mốc này tự trùng nhau.

### 4.1. Ví dụ vòng đời

Một yêu cầu được duyệt đến 10:30. Credential được cấp lúc 10:05, có hạn đến 10:25. Người dùng mở kết nối lúc 10:24.

Thiết kế phải trả lời:

- Sau 10:25 có được mở kết nối mới không?
- Kết nối đã mở lúc 10:24 xử lý thế nào?
- Có thể nhận credential thay thế trước 10:30 không?
- Một yêu cầu gia hạn credential lúc 10:27 có được kéo quyền vượt 10:30 không?
- Nếu người điều phối kết thúc incident lúc 10:15, quyền có bị thu hồi sớm không?

Một chính sách có thể giới hạn thời điểm hết hiệu lực theo:

```text
Kết thúc được phép
  = thời điểm sớm nhất trong các giới hạn áp dụng:
      phê duyệt, nhiệm vụ, chính sách và khả năng cấp credential
```

Công thức chỉ mô tả ý định. Mỗi thành phần thực thi phải nhận và kiểm tra giới hạn tương ứng.

### 4.2. Mốc thời gian trong hồ sơ không phải bộ điều khiển

Một annotation, comment SQL hoặc cột expires_at không tự thay đổi quyền.

Cần có thành phần phát hiện đến hạn, thực hiện thu hồi, xác minh kết quả và báo lỗi. Nếu thành phần này hỏng, phải biết quyền nào còn tồn tại và ai xử lý.

## 5. Vòng đời cấp quyền tham khảo

```text
Yêu cầu
   |
   v
Xác minh chủ thể, phạm vi và phê duyệt
   |
   v
Cấp principal / membership / credential
   |
   v
Kiểm tra quyền thực tế và bàn giao
   |
   v
Sử dụng, quan sát và gia hạn có điều kiện
   |
   v
Kết thúc hoặc thu hồi sớm
   |
   v
Xác minh quyền, phiên và dọn tồn dư
```

### 5.1. Yêu cầu

Thu thập principal người hoặc workload, mục đích, database đích, tập quyền, dữ liệu cần tiếp cận, thời hạn mong muốn và người chịu trách nhiệm.

Không để client tự chọn một role tùy ý từ database rồi broker gán mà không đối chiếu policy.

### 5.2. Phê duyệt

Tùy tác động, có thể tự động duyệt một mẫu quyền hẹp hoặc yêu cầu người có thẩm quyền.

Mã ticket không phải credential. Server cần xác minh nó còn hiệu lực, đúng người và đúng phạm vi, không chỉ kiểm tra một chuỗi tham chiếu có tồn tại.

Nếu thay tập quyền, database hoặc dữ liệu sau khi duyệt, phải xác định liệu yêu cầu còn nằm trong quyết định trước đó không.

### 5.3. Cấp phát và kiểm tra

Hệ thống cấp phát nên có định danh duy nhất cho yêu cầu và liên kết tới những tài nguyên đã tạo.

Sau khi cấp:

- Principal có tồn tại trên đúng hệ thống không?
- Membership hoặc grant có đúng không?
- Có thêm quyền từ mẫu, mặc định hoặc đường khác không?
- Credential có được truyền qua kênh phù hợp không?
- Nhiệm vụ hợp lệ có thực hiện được không?

Không cần ghi password vào log để chứng minh cấp phát thành công.

### 5.4. Gia hạn

Gia hạn là một quyết định tiếp tục cho phép, không chỉ thao tác cộng thời gian.

Cần kiểm tra nhiệm vụ còn mở, chủ thể còn được phân công, tập quyền chưa thay đổi, thời hạn tối đa chưa bị vượt và cơ chế hiện tại có cho gia hạn không.

Nếu hệ thống trả một TTL khác giá trị yêu cầu, consumer phải dùng kết quả thực tế. Không suy ra thời hạn mới từ giá trị đã gửi.

### 5.5. Thu hồi sớm

Quyền nên kết thúc khi nhiệm vụ xong hoặc không còn hợp lệ, không chỉ khi hết TTL.

Các lý do gồm người dùng đổi vai trò, incident đã đóng, credential bị nghi lộ hoặc phát hiện sử dụng ngoài phạm vi.

Thu hồi sớm cần đi qua cùng cơ chế kiểm chứng như hết hạn tự động.

## 6. Mô hình quyền của thành phần cấp phát

Một broker tạo login hoặc cấp membership là một principal đặc quyền.

Nếu bị xâm nhập, nó có thể tạo nhiều danh tính, cấp role không phù hợp hoặc thay thời hạn. Vì vậy, cần quản trị cả quyền của broker và đầu vào nó chấp nhận.

### 6.1. Giới hạn theo mẫu được quản lý

Có thể ánh xạ một loại nhiệm vụ sang:

- Kết nối database được phép.
- Role chức năng cố định.
- Cơ chế xác thực.
- Tập tùy chọn credential.
- Thời hạn mặc định và tối đa.
- Quy trình thu hồi, dọn và kiểm chứng.

Không cho người yêu cầu gửi SQL tùy ý để broker chạy bằng credential quản trị.

Các tham số cần được xử lý theo cơ chế an toàn của công cụ và engine, đặc biệt là identifier. Không giả định tham số hóa giá trị thông thường sẽ tự áp dụng được cho mọi tên role, database hoặc đối tượng SQL.

### 6.2. Bảo vệ credential quản trị của broker

Credential này cần được bảo quản, luân chuyển và giám sát. Quyền của nó phải đủ cho cấp phát và thu hồi thực tế, nhưng không tự chọn quyền cao nhất chỉ để tránh xử lý lỗi.

Cần kiểm tra tác vụ dọn và kết thúc phiên có cần quyền khác với tác vụ tạo login không. Một broker cấp được quyền nhưng không thu hồi được vì thiếu quyền là thiết kế chưa hoàn chỉnh.

### 6.3. Tách người dùng và người sửa mẫu

Người được yêu cầu role đọc không mặc nhiên được sửa mẫu role thành quản trị.

Quyền sửa policy broker, mẫu SQL, quyền vault hoặc pipeline triển khai broker phải được quản trị theo tác động của chúng. Đây là những đường ủy quyền gián tiếp vào database.

## 7. Ví dụ PostgreSQL 18: membership tạm thời

Ví dụ này chỉ dành cho database lab. Giả sử:

- `pam_lab.orders` là bảng dữ liệu giả, thuộc một owner ổn định.
- Bảng có các cột order_id, state và customer_email.
- `analyst_login` là danh tính đã được cấp phát an toàn, được phép kết nối database lab.
- Login này không có các đường quyền bổ sung ngoài thiết kế thử nghiệm.

### 7.1. Định nghĩa role chức năng hẹp

Principal quản trị có thẩm quyền thiết lập:

```sql
CREATE ROLE pam_lab_case_reader NOLOGIN;

GRANT USAGE ON SCHEMA pam_lab
TO pam_lab_case_reader;

GRANT SELECT (order_id, state)
ON TABLE pam_lab.orders
TO pam_lab_case_reader;
```

Role này được dùng làm tập quyền ổn định. Nó không cần bị tạo lại cho từng vụ việc nếu nội dung và phạm vi vẫn phù hợp.

Quyền theo cột trong ví dụ không giới hạn hàng. Muốn giới hạn dữ liệu theo tenant hoặc case cần cơ chế bổ sung đã được đánh giá.

### 7.2. Cấp membership cho nhiệm vụ

Trong cửa sổ đã được duyệt:

```sql
GRANT pam_lab_case_reader TO analyst_login
  WITH INHERIT FALSE, SET TRUE;
```

Login được phép chuyển sang role nhưng không tự thừa hưởng qua membership này. Khả năng chuyển role vẫn là một quyền thực tế, không bị loại bỏ bởi INHERIT FALSE.

Trong phiên của analyst_login:

```sql
SELECT session_user, current_user, current_database();

SET ROLE pam_lab_case_reader;

SELECT order_id, state
FROM pam_lab.orders
WHERE order_id = 1001;

RESET ROLE;
```

Ví dụ không cấp SELECT toàn bảng, DML ghi, DDL hoặc quyền ủy quyền tiếp. Những quyền đã có từ đường khác không tự bị trừ đi bởi grant hẹp này.

### 7.3. Không có TTL trong câu GRANT trên

Thời hạn nằm trong hệ thống quản lý yêu cầu và cần một thành phần thực thi thu hồi.

Khi nhiệm vụ kết thúc, principal có thẩm quyền thực hiện:

```sql
REVOKE pam_lab_case_reader FROM analyst_login;
```

Sau đó cần kiểm tra quyền khác, phiên đã mở và những trạng thái liên quan. PostgreSQL cộng các quyền từ nhiều đường; thu hồi một grant không bảo đảm subject mất quyền nếu còn nhận qua role khác hoặc PUBLIC. [REVOKE PostgreSQL 18](https://www.postgresql.org/docs/18/sql-revoke.html).

### 7.4. Xác minh bằng đường sử dụng thật

Bài thử cần chứng minh:

- Trong thời gian được cấp, truy vấn cột được phép thành công.
- Đọc cột customer_email không được phép qua role mẫu.
- Tác vụ ghi và thay cấu trúc không được phép.
- Sau kết thúc, không nhận lại được quyền qua membership đã thu hồi.
- Phiên đã chuyển role hoặc mở từ trước được xử lý theo cơ chế thực tế.

Dùng session quản trị giả lập principal có thể hỗ trợ kiểm tra, nhưng không thay thế thử đường xác thực, mạng và credential thật khi nghiệm thu toàn bộ quy trình.

## 8. Login được tạo riêng cho từng yêu cầu

Một phương án khác là tạo principal riêng cho một lần truy cập. Nó giúp phân biệt hoạt động của từng request và giảm việc chia sẻ credential.

### 8.1. Tạo, kiểm tra rồi mới kích hoạt

Một quy trình có thể:

1. Ghi nhận yêu cầu và định danh cấp phát.
2. Tạo principal chưa được phép đăng nhập.
3. Gắn tập quyền đã được duyệt.
4. Thiết lập credential qua kênh cấp phát phù hợp.
5. Xác minh phạm vi và cấu hình xác thực.
6. Cho phép đăng nhập, bàn giao và theo dõi.
7. Kết thúc, đối chiếu và dọn principal.

Ví dụ phần tạo role trong PostgreSQL lab:

```sql
CREATE ROLE pam_req_4821
  NOLOGIN
  NOSUPERUSER
  NOCREATEDB
  NOCREATEROLE
  NOREPLICATION
  NOBYPASSRLS;

GRANT pam_lab_case_reader TO pam_req_4821
  WITH INHERIT TRUE, SET FALSE;
```

Sau khi cơ chế xác thực đã được cấp phát và kiểm tra theo quy trình, principal có thẩm quyền có thể cho phép đăng nhập:

```sql
ALTER ROLE pam_req_4821 LOGIN;
```

Đây chỉ là các bước minh họa, chưa phải một hệ thống cấp credential hoàn chỉnh. Không có password trong ví dụ và không được suy rằng role đã có đường xác thực phù hợp chỉ từ thuộc tính LOGIN.

Tên role cần được tạo và ánh xạ có kiểm soát. Xử lý giới hạn identifier, trùng tên và retry; không dùng tên do người dùng tùy ý gửi làm đối tượng quản trị.

### 8.2. Role có phạm vi rộng hơn một kết nối

Trong PostgreSQL, role được định nghĩa ở cấp database cluster, không chỉ là một đối tượng cục bộ trong database hiện đang kết nối. VALID UNTIL là thời hạn password, không phải TTL toàn bộ role và không được cưỡng chế như vậy cho đăng nhập không dùng password. [CREATE ROLE PostgreSQL 18](https://www.postgresql.org/docs/18/sql-createrole.html).

Vì thế, cần kiểm tra principal có thể kết nối những database nào và có thể nhận quyền mặc định ở đâu. Tên principal gắn với một database trong PAM không tự tạo ranh giới tại engine.

### 8.3. Tránh ownership ngoài ý muốn

Login tạo riêng cho tác vụ đọc không nên sở hữu đối tượng ứng dụng.

Nếu principal tạm được dùng cho migration, cần thiết kế owner ổn định hoặc phương án xử lý ownership. Đối tượng do login tạo có thể tồn tại sau nhiệm vụ và cản trở dọn login.

Không xóa hàng loạt đối tượng sở hữu bởi role chỉ để quá trình cleanup báo thành công. Có thể đó là dữ liệu hoặc cấu trúc cần giữ.

### 8.4. Không tái sử dụng danh tính để làm đơn giản sổ sách

Nếu cùng một username được cấp lại cho yêu cầu khác, việc liên kết audit lịch sử có thể khó hơn và có rủi ro thừa hưởng tham chiếu hoặc quyền chưa dọn đúng.

Cần chính sách định danh và kiểm kê phù hợp. Giữ liên kết request, principal và thời gian sử dụng, thay vì chỉ ghi username đang tồn tại ở thời điểm kiểm tra.

## 9. Credential động và lease

Một secret engine có thể tạo credential database theo role cấu hình. Ví dụ, Vault có database secrets engine cấp credential động và hỗ trợ cơ chế lease; static role là một mô hình khác gắn với username database ổn định và luân chuyển password. [Database secrets engine](https://developer.hashicorp.com/vault/docs/secrets/databases).

### 9.1. Phân biệt ba khái niệm role

Trong một triển khai có thể đồng thời có:

- Role hoặc policy của hệ thống xác thực vào vault.
- Role cấu hình trong database secrets engine.
- Role hoặc user thật tại database.

Chúng không tự là cùng một đối tượng. Một role cấu hình trong secret engine có thể là mẫu tạo nhiều login database khác nhau.

Cần nối đầy đủ principal gọi hệ thống cấp phát với template được dùng, login thật được tạo và tập quyền thật tại database.

### 9.2. Lease quản lý vòng đời, nhưng phải quan sát tác động thật

Vault cấp lease cho secret động, có cơ chế gia hạn và thu hồi; tài liệu cũng nêu trường hợp thu hồi không thực hiện được. Do đó, vận hành cần theo dõi lỗi revoke và đối chiếu với hệ thống đích, không chỉ dựa vào thời gian lease trên giao diện. [Lease, renew và revoke](https://developer.hashicorp.com/vault/docs/concepts/lease).

Một TTL đã hết không tự chứng minh:

- Login đã bị khóa hoặc xóa tại database.
- Membership đã được gỡ.
- Kết nối cũ đã kết thúc.
- Đối tượng phụ thuộc đã được xử lý.
- Không còn credential bản sao hoặc đường xác thực khác.

### 9.3. Cấu hình plugin và câu lệnh phải khớp engine

Plugin database có cấu hình tạo credential và những khả năng riêng. Ví dụ, plugin PostgreSQL của Vault hỗ trợ credential động theo role cấu hình; phải kiểm tra khả năng và hành vi của phiên bản triển khai thực tế. [Plugin PostgreSQL](https://developer.hashicorp.com/vault/docs/secrets/databases/postgresql).

Không sao chép mẫu SQL rộng rồi chỉ đổi tên database. Cần review cả quyền được cấp, role đích, thời hạn, xử lý session và cách dọn khi lỗi.

Không coi một ví dụ khởi đầu trong tài liệu sản phẩm là chính sách least privilege phù hợp cho dữ liệu của mọi tổ chức.

### 9.4. Luân chuyển static password không tạo principal tạm thời

Một tài khoản được dùng lâu dài nhưng đổi password định kỳ vẫn là danh tính lâu dài. Nó có thể phù hợp một workload, nhưng không cung cấp cùng khả năng phân biệt yêu cầu như login riêng.

Cần chọn mô hình theo mục tiêu: giảm bí mật tĩnh, quy trách nhiệm theo job, giới hạn quyền theo nhiệm vụ hoặc kết thúc khả năng truy cập. Không gọi mọi mô hình có password rotation là JIT.

## 10. Quản lý session và connection pool

### 10.1. Ngăn kết nối mới khác với dừng session cũ

Một cơ chế có thể chặn xác thực mới mà không đóng kết nối đã tồn tại. Một cơ chế khác có thể gỡ quyền nhưng vẫn để transaction hoặc trạng thái phiên cần được xử lý.

Phải kiểm thử hành vi của engine, cơ chế xác thực và proxy được triển khai. Không suy từ một câu lệnh quản trị rằng mọi session đã ngừng ngay.

### 10.2. Phiên đã chuyển role

Nếu người dùng đã SET ROLE trước khi membership bị thu hồi, cần xác định chính xác trạng thái hiệu lực của phiên và cách kết thúc khả năng đó.

Thiết kế có thể cần đóng phiên được cấp cho nhiệm vụ hoặc áp dụng cơ chế quản lý phiên tương ứng. Không chỉ thử một kết nối mới rồi kết luận phiên cũ cũng không còn quyền.

### 10.3. Connection pool giữ credential và kết nối

Ứng dụng hoặc công cụ có thể:

- Cache credential.
- Giữ kết nối lâu hơn TTL.
- Tự retry với credential cũ.
- Mở pool mới trước khi đóng pool cũ.
- Giữ trạng thái role hoặc cấu hình trên một kết nối.
- Dùng một danh tính backend chung cho nhiều người.

Quy trình cần quản lý tuổi thọ kết nối và phân tách pool theo ngữ cảnh quyền. Không để kết nối đặc quyền quay lại pool của công việc thông thường.

Nếu proxy dùng chung principal database, cần biết khả năng quy trách nhiệm ở đâu và có ngăn được đường kết nối trực tiếp không. Danh tính người dùng ở cổng không tự xuất hiện nguyên vẹn trong audit database.

### 10.4. Workload sử dụng credential động

Workload phải biết khi nào credential sắp hết hạn, cách nhận kết quả renewal thực tế và khi nào cần tạo pool mới.

Không chờ tới lúc toàn bộ request lỗi mới bắt đầu xử lý credential hết hạn. Đồng thời, không âm thầm gia hạn vô hạn một quyền được cấp cho job đã kết thúc.

Những thao tác nhận credential, thay pool và đóng kết nối cần có giới hạn retry để tránh tạo hàng loạt principal khi hệ thống cấp phát chậm.

### 10.5. Transaction đang chạy khi tới hạn

Cần định nghĩa cách xử lý theo tác động: ngăn bắt đầu công việc mới, kết thúc ở điểm an toàn, gia hạn có thẩm quyền hoặc chấm dứt khi yêu cầu kiểm soát bắt buộc.

Không xem khó khăn vận hành là sự cho phép giữ quyền vô hạn. Mọi ngoại lệ hoặc gia hạn phải có giới hạn, người chịu trách nhiệm và bằng chứng.

## 11. Thu hồi theo nhiều bước và xác minh

Một quy trình kết thúc có thể gồm:

```text
Ngừng cho phép nhận mới / gia hạn
       |
       v
Khóa đăng nhập hoặc kết thúc grant theo thiết kế
       |
       v
Xử lý session và công việc còn tồn tại
       |
       v
Đối chiếu quyền, ownership và phụ thuộc
       |
       v
Dọn principal nếu phù hợp
       |
       v
Kiểm tra tại hệ thống đích và đóng hồ sơ
```

Thứ tự cụ thể phụ thuộc engine và loại quyền. Điều quan trọng là biết từng bước đã hoàn thành hay chưa.

### 11.1. Dừng cấp lại và gia hạn

Nếu controller vẫn coi yêu cầu còn active, nó có thể cấp lại quyền vừa thu hồi. Cần kết thúc đúng nguồn quyết định.

Tương tự, chặn một token gọi hệ thống cấp phát không tự chứng minh mọi credential database đã được cấp bằng token đó đều vô hiệu; phải hiểu cơ chế liên kết và kết quả thu hồi thực tế.

### 11.2. Khóa đường mới

Với một login riêng trong PostgreSQL lab, có thể có bước:

```sql
ALTER ROLE pam_req_4821 NOLOGIN;
```

Bước này không được mô tả là đã chấm dứt mọi session hoặc gỡ mọi đường sử dụng quyền. Cần xử lý tiếp theo thiết kế.

Nếu principal đã được chia sẻ hoặc dùng sai mục đích, đánh giá ảnh hưởng trước khi kết thúc. Đây là lý do nên tránh dùng cùng login cho nhiều nhiệm vụ không liên quan.

### 11.3. Xử lý membership và quyền

Thu hồi grant hoặc membership theo đúng phạm vi. Kiểm tra grant gián tiếp, PUBLIC, khả năng chuyển role và quyền được cấp tiếp.

Một role hẹp mới không làm giảm những quyền rộng đang tồn tại từ nơi khác. Cũng không kết luận đã mất quyền chỉ vì màn hình PAM không còn hiển thị một grant.

### 11.4. Dọn role và phụ thuộc

PostgreSQL có thể từ chối DROP ROLE nếu role còn được tham chiếu trong database của cluster. Cần xử lý ownership và privilege liên quan theo kế hoạch trước khi xóa. [DROP ROLE PostgreSQL 18](https://www.postgresql.org/docs/18/sql-droprole.html).

Không biến một lỗi dependency thành lệnh dọn phá hủy không kiểm tra. Cần xác định đối tượng nào được giữ, owner đích là ai và quyền nào cần kết thúc.

Có thể một principal không còn khả năng truy cập nhưng vẫn chưa xóa được. Ghi rõ trạng thái “đã ngăn truy cập, còn cleanup”, thay vì báo thất bại mơ hồ hoặc đánh dấu đã dọn hoàn toàn.

### 11.5. Chứng minh kết quả

Bằng chứng kết thúc có thể gồm:

- Grant hoặc membership mục tiêu không còn.
- Đăng nhập mới bị chặn theo thiết kế.
- Session nhiệm vụ đã được xử lý.
- Không còn đường quyền gián tiếp ngoài phạm vi.
- Principal được xóa hoặc có lý do tồn tại rõ ràng.
- Cleanup còn lại có chủ sở hữu và thời hạn xử lý.
- Những kiểm tra có mục tiêu cho kết quả mong đợi.

Không thử quyền bằng cách đọc dữ liệu thật ngoài nhiệm vụ hoặc xóa đối tượng production. Dùng phép kiểm tra phù hợp và dữ liệu thử nghiệm khi có tác động.

## 12. Lỗi phân tán, retry và đối chiếu

Hệ thống PAM, vault, broker và database không luôn thay đổi trạng thái thành công cùng một lúc.

### 12.1. Cấp phát thành công nhưng phản hồi mất

Database có thể đã tạo role trong khi broker nhận timeout. Nếu retry không có liên kết yêu cầu, nó có thể tạo thêm login.

Cần định danh cấp phát, trạng thái bền vững và cách tra cứu tài nguyên đã tạo. Không dựa duy nhất vào tên người dùng do client cung cấp hoặc một dòng log không bảo đảm lưu được.

### 12.2. Thu hồi thất bại

Những nguyên nhân có thể gồm database không tới được, credential quản trị hết hiệu lực, thiếu quyền, dependency hoặc session cần xử lý.

Phải có retry có giới hạn phù hợp, cảnh báo và phương án chuyển cấp. Ghi lại trạng thái chưa được xác minh và thời điểm cần xử lý, thay vì báo “expired” như đã hoàn thành revoke.

### 12.3. Trạng thái tham khảo

Bảng sau là mô hình quản lý đề xuất, không phải tên trạng thái của một sản phẩm:

| Trạng thái | Ý nghĩa |
| --- | --- |
| APPROVED | Có thẩm quyền cấp nhưng chưa xác nhận quyền ở đích |
| PROVISIONING | Đang tạo principal, grant hoặc credential |
| ACTIVE | Quyền đã được kiểm tra và đang được phép sử dụng |
| REVOKING | Đang kết thúc khả năng truy cập |
| REVOCATION_FAILED | Chưa hoàn tất hoặc chưa xác minh được thu hồi |
| CLEANUP_PENDING | Đã xử lý truy cập theo thiết kế nhưng còn đối tượng cần dọn |
| CLOSED | Các điều kiện kết thúc đã được xác minh |

Không chuyển CLOSED chỉ vì đồng hồ đã vượt thời hạn.

### 12.4. Đối chiếu định kỳ

So sánh yêu cầu còn hiệu lực với principal, membership, grant và session tại database.

Cần phát hiện:

- Quyền còn tồn tại nhưng không có yêu cầu hợp lệ.
- Principal tạo dở không được theo dõi.
- Role mang tên mẫu nhưng không thuộc hệ thống quản lý.
- Yêu cầu active nhưng quyền thực tế rộng hơn thiết kế.
- Grant đã gỡ nhưng một nguồn khác cấp lại.
- Cleanup hoặc revoke thất bại chưa có người xử lý.

Không xóa tự động mọi role có prefix giống nhau mà không xác minh ownership quản trị và phạm vi. Tên chỉ là một tín hiệu, không phải bằng chứng duy nhất.

## 13. Audit và quan sát vòng đời

Chuỗi cần nối được:

```text
Người / workload
   → yêu cầu và phê duyệt
   → định danh cấp phát hoặc lease
   → principal thật tại database
   → session và quyền hiệu lực
   → hành động
   → kết quả thu hồi và cleanup
```

### 13.1. Trường dữ liệu cần có

| Nhóm | Nội dung minh họa |
| --- | --- |
| Chủ thể | Người hoặc workload đã xác thực |
| Nhiệm vụ | Incident, job, phạm vi dữ liệu |
| Đích | Instance, database, schema hoặc đối tượng |
| Quyền | Role mẫu, membership, phiên bản policy |
| Vòng đời | Thời gian cấp, thời hạn, renewal, thu hồi sớm |
| Thực thi | Username thật, session phù hợp, principal hiệu lực |
| Kết quả | Cấp thành công, lỗi, revoke đã xác minh, cleanup còn lại |

Không lưu password hoặc token để làm khóa liên kết audit. Định danh cấp phát và lease cũng cần được bảo vệ theo chức năng, không phát tán tùy ý.

### 13.2. Không chỉ theo dõi việc cấp thành công

Cần quan sát quyền tồn tại quá hạn, renewal bị từ chối, session kéo dài, tạo login tăng bất thường và lỗi thu hồi.

Các chỉ số có ích gồm độ trễ từ kết thúc nhiệm vụ tới thu hồi được xác minh, số principal không có yêu cầu hợp lệ và số cleanup pending chưa được xử lý.

Đặt ngưỡng theo tác động và đặc điểm vận hành. Không dùng tỷ lệ cấp phát thành công cao để che một hệ thống thường xuyên không thu hồi được quyền.

### 13.3. Bảo vệ dữ liệu truy vấn và bằng chứng

Query có thể chứa dữ liệu cá nhân hoặc thông tin nghiệp vụ. Chọn mức audit phù hợp và bảo vệ nơi lưu.

Người có quyền sửa mẫu cấp phát, credential quản trị hoặc audit có khả năng tác động bằng chứng. Cần đánh giá quyền ở cả hệ thống cấp phát và database, không chỉ một phía.

## 14. Tình huống thực hành

Nhóm hỗ trợ cần điều tra trạng thái đơn hàng trong một incident. Ban đầu, mọi người dùng chung tài khoản support_admin, password đổi mỗi tháng và không có giới hạn session.

### 14.1. Thiết kế mới

Chọn role đọc hẹp cho dữ liệu được phép. Người hỗ trợ đăng nhập bằng danh tính cá nhân, được phân công incident và yêu cầu một cửa sổ truy cập.

Hệ thống có thể cấp membership tạm cho login cá nhân hoặc login riêng cho yêu cầu. Quyết định phụ thuộc khả năng quy trách nhiệm, kết thúc session và tính năng nền tảng.

Role chức năng không có DDL, quyền cấp tiếp hoặc ownership. Nếu yêu cầu chỉ liên quan một tenant, phải có cơ chế giới hạn dữ liệu tương ứng; role đọc chung không tự đáp ứng.

### 14.2. Trong thời gian sử dụng

Người hỗ trợ dùng đúng công cụ và nguồn được phép. Hệ thống ghi grant, principal thật, hoạt động và thời hạn.

Gia hạn chỉ khi incident còn mở và nhiệm vụ vẫn hợp lệ. Đổi phạm vi dữ liệu hoặc xin quyền ghi là yêu cầu cần được đánh giá lại, không phải renewal thuần túy.

### 14.3. Khi incident đóng

Hệ thống dừng cấp mới và gia hạn, thu hồi quyền hoặc khóa login, xử lý session rồi xác minh tại database.

Nếu database chưa truy cập được để revoke, trạng thái phải phản ánh chưa xác minh, có cảnh báo và người xử lý. Không trả thông báo “đã thu hồi” chỉ vì incident đã đóng trong hệ thống ticket.

Kết quả mong muốn là người dùng không còn khả năng sử dụng quyền của nhiệm vụ, audit nối được các bước và không có principal mồ côi ngoài quản lý.

## 15. Bộ kiểm tra nghiệm thu

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Chủ thể hợp lệ yêu cầu quyền đúng nhiệm vụ | Có thể hoàn thành quy trình được phép |
| Người dùng chọn template ngoài quyền yêu cầu | Bị từ chối trước khi cấp |
| Đổi database, schema hoặc dữ liệu sau phê duyệt | Phạm vi được đối chiếu lại |
| Role chỉ cho đọc vài cột | Không đọc được cột khác qua đường quyền mẫu |
| Có grant rộng qua role khác hoặc PUBLIC | Kiểm kê phát hiện quyền hiệu lực bổ sung |
| Yêu cầu có case_id nhưng không có lọc hàng | Không báo cáo nhầm đã cách ly dữ liệu theo case |
| Cấp phát thành công rồi phản hồi timeout | Retry không tạo principal mất kiểm soát |
| Đến hạn khi không có session | Quyền và credential được xử lý đúng |
| Đến hạn khi có session hoặc SET ROLE | Kiểm tra được trạng thái thật và cơ chế kết thúc |
| Credential hết hạn nhưng pool còn kết nối | Không kết luận thu hồi chỉ từ lỗi xác thực mới |
| Renewal sau khi nhiệm vụ đóng | Bị từ chối theo policy |
| Renewal được trả TTL ngắn hơn yêu cầu | Consumer sử dụng thời hạn thực tế |
| Thu hồi sớm do nghi lộ | Có tác động tại đích và bằng chứng |
| Broker thiếu quyền revoke hoặc database không tới được | Có trạng thái lỗi, cảnh báo và chuyển cấp |
| Role tạm có dependency | Cleanup không phá hủy dữ liệu ngoài phạm vi |
| Principal có thể truy cập database khác | Phạm vi ngoài ý muốn được phát hiện |
| Nguồn quản lý tự cấp lại grant | Quyền không tái xuất hiện ngoài quyết định hợp lệ |
| Kết thúc hoàn chỉnh | Không còn quyền, session hoặc tồn dư chưa được giải thích |

Các phép thử có tác động phải dùng môi trường và đối tượng được phép. Không cần truy cập dữ liệu ngoài nhiệm vụ để chứng minh một bài thử từ chối.

## 16. Bài tập tự áp dụng

Một hệ thống tạo login cho từng job, đặt thời hạn password và ghi lease ID. Tuy nhiên:

- Job dùng connection pool lâu hơn TTL.
- Login tạm đôi khi tạo bảng phục vụ xử lý.
- Revoke lỗi khi database bảo trì.
- Hệ thống vẫn đánh dấu CLOSED theo đồng hồ.
- Một số login nhận thêm quyền qua PUBLIC.

Hãy thiết kế lại:

1. Xác định bốn vòng đời và nơi thực thi từng vòng đời.
2. Chọn quyền chức năng và phạm vi dữ liệu cần thiết.
3. Quản lý session, pool và ownership của đối tượng tạo mới.
4. Định nghĩa trạng thái lỗi thu hồi và cleanup.
5. Thiết kế retry, đối chiếu và chuyển cấp.
6. Nêu phép thử chứng minh kết thúc quyền thật.
7. Xác định bằng chứng để người kiểm toán lần lại một lần truy cập.

Một đáp án tốt giải thích cả trường hợp bình thường lẫn khi thành phần thu hồi không hoạt động. Chỉ giảm TTL không giải quyết các vấn đề trên.

## 17. Tiêu chí hoàn thành

Temporary database role đạt mục tiêu khi có thể chứng minh:

- Nhiệm vụ, principal, dữ liệu và hành động được xác định trước khi cấp.
- Role quyền, membership, login, credential và session được phân biệt rõ.
- Thời hạn có thành phần thực thi và kiểm tra tại hệ thống đích.
- Gia hạn không vượt thẩm quyền hoặc âm thầm kéo dài nhiệm vụ đã đóng.
- Broker và mẫu cấp phát được quản trị như đặc quyền.
- Quyền gián tiếp, PUBLIC và ownership được kiểm kê.
- Session, pool và công việc đang chạy có chính sách kết thúc rõ.
- Lỗi revoke và dependency không bị che bởi trạng thái hết hạn.
- Principal mồ côi và cleanup còn lại được phát hiện, có chủ sở hữu.
- Audit nối được từ yêu cầu tới việc kết thúc đã xác minh.

Một quyền chỉ thực sự tạm thời khi hệ thống kiểm soát được cả lúc bắt đầu lẫn lúc kết thúc khả năng sử dụng. TTL là một giới hạn cần thiết trong nhiều thiết kế, nhưng bằng chứng tại database và trên session thực tế mới cho thấy giới hạn đó đã có tác dụng.

