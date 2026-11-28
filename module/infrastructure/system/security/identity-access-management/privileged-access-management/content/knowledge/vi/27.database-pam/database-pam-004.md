# DML privilege

## Mục tiêu bài học

Sau bài học này, bạn có thể:

- Xác định quyền đọc và thay đổi dữ liệu cần thiết cho một nhiệm vụ.
- Phân biệt quyền theo bảng, cột, hàng và quyền nghiệp vụ.
- Cấp quyền qua role có phạm vi rõ, tránh quyền sở hữu và khả năng cấp tiếp không cần thiết.
- Kiểm tra quyền hiệu lực, tác động của truy vấn và giới hạn của việc thu hồi.
- Thiết kế quy trình PAM cho truy cập DML tạm thời và lưu bằng chứng phù hợp.

## 1. DML privilege là gì?

**DML privilege** là quyền thực hiện thao tác với dữ liệu trong cơ sở dữ liệu. Các thao tác điển hình gồm thêm, sửa và xóa hàng; quyền đọc thường được xem xét cùng nhóm này khi thiết kế truy cập dữ liệu.

Tên gọi và cách phân loại SELECT có thể khác giữa tài liệu, chẳng hạn tách thành truy vấn dữ liệu. Trong bài học, điều quan trọng là quyền thực tế: ai được đọc hoặc thay đổi dữ liệu nào, bằng cách nào và trong điều kiện nào.

Bài dùng PostgreSQL 18 để minh họa cú pháp. Các nguyên tắc PAM có thể áp dụng rộng hơn, nhưng không nên sao chép nguyên cú pháp hoặc giả định quyền sang một hệ quản trị khác.

### 1.1. Có quyền DML không đồng nghĩa có quyền quản trị cấu trúc

Một người có UPDATE trên bảng không vì thế được phép thay định nghĩa bảng hoặc quản trị danh tính. Ngược lại, nếu họ sở hữu đối tượng hoặc có một vai trò quản trị khác, phạm vi thực tế có thể rộng hơn nhiều quyền DML được nhìn thấy.

Cần tách:

- Quyền thao tác dữ liệu.
- Quyền định nghĩa và thay đổi cấu trúc.
- Quyền quản lý người dùng, role và cấp quyền.
- Quyền sở hữu.
- Quyền qua function, procedure, view hoặc cơ chế đặc biệt.

### 1.2. Quyền dữ liệu vẫn có thể là đặc quyền rất mạnh

Một tài khoản không phải DBA vẫn có thể gây hậu quả lớn nếu được sửa số dư, đổi trạng thái thanh toán, xóa lịch sử hoặc đọc toàn bộ thông tin khách hàng.

Đánh giá rủi ro phải dựa trên dữ liệu và hậu quả nghiệp vụ, không chỉ tên role. Role có tên support hoặc read-only không tự chứng minh phạm vi an toàn.

## 2. Các quyền thường gặp

| Quyền hoặc thao tác | Khả năng cần kiểm soát | Rủi ro điển hình |
|---|---|---|
| SELECT | Đọc dữ liệu được phép | Lộ dữ liệu hoặc thu thập diện rộng |
| INSERT | Thêm hàng hoặc gán giá trị cho cột được phép | Tạo giao dịch hoặc bản ghi không hợp lệ về nghiệp vụ |
| UPDATE | Sửa dữ liệu ở phạm vi được phép | Đổi số tiền, chủ sở hữu hoặc trạng thái |
| DELETE | Xóa hàng | Mất dữ liệu và tác động quan hệ phụ thuộc |
| MERGE | Chọn hành động thêm/sửa/xóa theo điều kiện | Khó đánh giá nếu chỉ nhìn tên một câu lệnh |
| TRUNCATE | Thao tác toàn bảng theo quyền riêng của engine | Tác động diện rộng, không tương đương DELETE có điều kiện |

PostgreSQL cho phép cấp một số quyền ở mức cột và phân biệt TRUNCATE với DELETE. Cú pháp GRANT cũng tách quyền đối tượng khỏi membership của role. [PostgreSQL 18: GRANT](https://www.postgresql.org/docs/18/sql-grant.html).

### 2.1. Một câu lệnh có thể cần nhiều quyền

Trong PostgreSQL, UPDATE cần quyền trên cột được sửa và quyền SELECT đối với cột được đọc trong biểu thức hoặc điều kiện. [PostgreSQL 18: UPDATE](https://www.postgresql.org/docs/18/sql-update.html).

Ví dụ:

~~~sql
UPDATE payments.invoice
SET status = 'reviewed'
WHERE invoice_id = 1001
  AND status = 'pending';
~~~

Đây là ví dụ cú pháp, không phải lệnh dành cho cơ sở dữ liệu thật trong workspace. Cần xét cả quyền sửa status lẫn quyền đọc các cột tham gia điều kiện.

Không xử lý mọi lỗi quyền bằng cách cấp SELECT hoặc UPDATE toàn bộ schema. Hãy xác định câu lệnh thực tế và phạm vi dữ liệu cần dùng.

### 2.2. MERGE không phải đường tránh phân quyền

Trong PostgreSQL, không có một quyền MERGE riêng thay cho mọi quyền thành phần. Quyền cần thiết phụ thuộc các hành động và cột được dùng trong câu lệnh. [PostgreSQL 18: MERGE](https://www.postgresql.org/docs/18/sql-merge.html).

Khi đánh giá một công cụ đồng bộ hoặc upsert, cần xem nó có thể thêm, sửa hay xóa gì; không chỉ xem tên thao tác trên giao diện.

## 3. Phân quyền theo bốn chiều

### 3.1. Bảng và đối tượng

Xác định bảng, view hoặc đối tượng cụ thể. Tránh dùng quyền trên toàn schema khi nhiệm vụ chỉ cần một bảng.

Cùng tên bảng ở hai database hoặc hai schema có thể có mức nhạy cảm khác nhau. Kế hoạch cần ghi định danh đích đầy đủ, môi trường và owner dữ liệu.

### 3.2. Cột

Không phải mọi người sửa dữ liệu đều cần sửa mọi cột.

Ví dụ, nhân viên hỗ trợ có thể cần sửa ghi chú nhưng không được đổi số tiền hoặc tenant của bản ghi. Quyền mức cột giúp giảm phạm vi thao tác trực tiếp, nhưng phải kiểm tra các đường quyền rộng hơn còn tồn tại.

### 3.3. Hàng

Quyền UPDATE theo bảng hoặc cột không tự tạo một điều kiện tenant. Nếu cần giới hạn hàng, phải có cơ chế phù hợp ở database hoặc một đường thực thi được kiểm soát đủ chặt.

Một hướng dẫn “nhớ thêm WHERE tenant_id = ...” chỉ là quy trình nếu người dùng vẫn có thể gửi SQL khác.

### 3.4. Điều kiện nghiệp vụ

Quyền trên cột status không tự quy định trạng thái nào được phép chuyển sang trạng thái nào. Quyền INSERT không tự chứng minh hồ sơ đã được phê duyệt.

Những ràng buộc như hạn mức, phân tách người tạo/người duyệt hoặc trạng thái giao dịch cần cơ chế nghiệp vụ riêng. Có thể thực thi bằng constraint, workflow, procedure hoặc lớp ứng dụng theo thiết kế, nhưng phải xác định đúng nơi chịu trách nhiệm.

## 4. Kiểm kê quyền hiệu lực

Trước khi cấp thêm quyền, cần biết danh tính đang có gì qua mọi đường:

- Grant trực tiếp.
- Role được kế thừa.
- Khả năng chuyển vai trò.
- Membership quản trị hoặc quyền sở hữu.
- Quyền được cấp cho PUBLIC theo loại đối tượng và cấu hình.
- View hoặc routine có thể truy cập dữ liệu thay người gọi.
- Credential của ứng dụng hoặc công cụ đang được dùng chung.

Trong PostgreSQL, role membership có thể cho dùng quyền qua INHERIT hoặc SET ROLE tùy tùy chọn và chuỗi membership. [PostgreSQL 18: Role Membership](https://www.postgresql.org/docs/18/role-membership.html).

### 4.1. Một role hẹp không trừ quyền rộng cũ

Nếu một người đã có UPDATE toàn bảng qua role A, cấp thêm role B chỉ sửa note không làm mất khả năng sửa amount.

Tương tự, việc không cấp DELETE cho role mới không chứng minh người dùng không thể xóa dữ liệu qua một role khác hoặc routine được phép gọi.

### 4.2. Tách owner khỏi người vận hành DML

Quyền sở hữu có khả năng quản lý đối tượng vượt quá nhu cầu dữ liệu thông thường. Không nên cho tài khoản hỗ trợ hoặc tài khoản ứng dụng sở hữu mọi bảng chỉ để tránh lỗi permission denied.

Một thiết kế thường tách owner triển khai, role ứng dụng và role vận hành. Cách thực thi cụ thể phụ thuộc hệ quản trị và quy trình triển khai.

### 4.3. Tài khoản con người khác tài khoản ứng dụng

Tài khoản ứng dụng cần quyền phù hợp với chức năng và vòng đời dịch vụ. Người vận hành cần danh tính cá nhân để quy trách nhiệm.

Nếu người dùng đăng nhập bằng credential ứng dụng chung, audit database có thể chỉ thấy ứng dụng. Việc bảo quản credential trong vault không tự khôi phục được danh tính người thao tác.

## 5. Ví dụ phòng lab: role DML có giới hạn

Các câu lệnh dưới đây là tài liệu minh họa cho một database lab trống với dữ liệu giả. Chúng chưa được thực thi lên hệ thống nào.

Giả định:

- Người chuẩn bị lab có thẩm quyền tạo schema, bảng và role.
- Role DML không phải owner, superuser hoặc role vượt kiểm soát hàng.
- Không có grant khác mở rộng quyền ngoài ví dụ.
- example_operator là login cá nhân thử nghiệm đã tồn tại, được quản lý riêng.
- Bài không tạo hoặc phân phối mật khẩu.

### 5.1. Chuẩn bị đối tượng

~~~sql
CREATE SCHEMA pam_lab;

CREATE TABLE pam_lab.adjustment (
    id bigint PRIMARY KEY,
    tenant_id integer NOT NULL,
    amount numeric(12, 2) NOT NULL CHECK (amount > 0),
    status text NOT NULL CHECK (status IN ('pending', 'reviewed')),
    note text
);

INSERT INTO pam_lab.adjustment
    (id, tenant_id, amount, status, note)
VALUES
    (1001, 42, 50.00, 'pending', 'lab tenant 42'),
    (2001, 84, 75.00, 'pending', 'lab tenant 84');
~~~

Bảng dùng id do người tạo bản ghi cung cấp để ví dụ không phụ thuộc sequence.

Constraint số tiền dương và tập trạng thái chỉ bảo vệ một phần tính hợp lệ. Chúng không chứng minh một khoản điều chỉnh đã được người có thẩm quyền duyệt.

### 5.2. Tạo role chứa quyền

~~~sql
CREATE ROLE pam_adjustment_operator NOLOGIN;

GRANT USAGE ON SCHEMA pam_lab
TO pam_adjustment_operator;

GRANT SELECT ON TABLE pam_lab.adjustment
TO pam_adjustment_operator;

GRANT INSERT (id, tenant_id, amount, status, note)
ON TABLE pam_lab.adjustment
TO pam_adjustment_operator;

GRANT UPDATE (status, note)
ON TABLE pam_lab.adjustment
TO pam_adjustment_operator;
~~~

Role được phép đọc bảng, thêm bản ghi và sửa hai cột. Ví dụ không cấp DELETE, TRUNCATE, quyền sửa amount, ownership hoặc WITH GRANT OPTION.

Đây vẫn là quyền đáng kể. SELECT cho phép đọc những hàng cơ chế hàng cho phép; INSERT cho phép gán các cột đã liệt kê, bao gồm số tiền và tenant nếu chưa có giới hạn bổ sung.

### 5.3. Gắn với login thử nghiệm

~~~sql
GRANT pam_adjustment_operator
TO example_operator
WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;
~~~

Ví dụ yêu cầu chuyển role khi dùng quyền và không cấp khả năng quản trị membership đó. Điều này không tự giới hạn thời gian; hệ thống quản lý quyền phải chịu trách nhiệm cấp và thu hồi theo cửa sổ đã duyệt.

Tài khoản thử nghiệm vẫn phải được kiểm tra các nguồn quyền khác. Một login đang có quyền owner không trở thành danh tính least privilege chỉ vì vừa nhận membership này.

## 6. Thêm giới hạn hàng theo tenant

PostgreSQL hỗ trợ Row-Level Security để hạn chế hàng được đọc hoặc sửa theo policy. Chủ sở hữu bảng, superuser và role BYPASSRLS cần được xét riêng; TRUNCATE không chịu lọc hàng theo RLS. [PostgreSQL 18: Row Security Policies](https://www.postgresql.org/docs/18/ddl-rowsecurity.html).

### 6.1. Policy đơn giản cho dữ liệu lab

Người có thẩm quyền trên bảng có thể thiết lập:

~~~sql
ALTER TABLE pam_lab.adjustment
ENABLE ROW LEVEL SECURITY;

CREATE POLICY adjustment_tenant_42
ON pam_lab.adjustment
FOR ALL
TO pam_adjustment_operator
USING (tenant_id = 42)
WITH CHECK (tenant_id = 42);
~~~

Policy dùng tenant cố định để minh họa, không phải thiết kế danh tính đa tenant hoàn chỉnh.

- USING giới hạn những hàng có thể được sử dụng theo policy.
- WITH CHECK giới hạn dữ liệu hàng mới hoặc hàng sau thay đổi tương ứng.
- Policy không tự cấp thêm DELETE nếu role chưa có quyền DELETE.
- Cần kiểm thử bằng danh tính không sở hữu bảng và không có khả năng vượt RLS.

### 6.2. Kiểm tra policy tổng hợp

Nếu tồn tại policy hoặc role khác, kết quả có thể khác ví dụ. Cần kiểm kê những policy đang áp dụng và cách chúng kết hợp.

Không kiểm thử bằng owner rồi kết luận policy hỏng hoặc đúng mà bỏ qua đường bypass của owner. Cũng không xem FORCE ROW LEVEL SECURITY là cách ngăn mọi người có quyền quản lý bảng thay đổi chính sách.

### 6.3. Không tin tenant do client tùy ý khai

Trong hệ thống thực, tenant cần được ràng buộc với danh tính và ngữ cảnh đã được xác minh. Nếu người gọi có thể tự đặt một biến phiên để chọn tenant khác mà không có kiểm tra, policy dựa trên biến đó có thể không tạo ranh giới mong muốn.

Thiết kế cần xác định ai được gán ngữ cảnh, có thể thay đổi lúc nào và connection pool có xóa ngữ cảnh cũ khi chuyển người dùng hay không.

## 7. Kiểm tra quyền và kết quả trong lab

### 7.1. Xác nhận danh tính hiện tại

Đăng nhập bằng example_operator, sau đó:

~~~sql
SET ROLE pam_adjustment_operator;

SELECT session_user, current_user;
~~~

Cần biết ai xác thực ban đầu và role nào đang là ngữ cảnh thực thi. Không chỉ nhìn tên người đăng nhập trên giao diện công cụ.

### 7.2. Kiểm tra quyền cột và quyền bảng

~~~sql
SELECT
    has_column_privilege(
        current_user,
        'pam_lab.adjustment',
        'note',
        'UPDATE'
    ) AS can_update_note,
    has_column_privilege(
        current_user,
        'pam_lab.adjustment',
        'amount',
        'UPDATE'
    ) AS can_update_amount,
    has_table_privilege(
        current_user,
        'pam_lab.adjustment',
        'DELETE'
    ) AS can_delete;
~~~

Trong giả định lab sạch, mong muốn là note được sửa, amount không được sửa và DELETE không được cấp.

PostgreSQL cung cấp các hàm kiểm tra quyền và thông tin phiên như trong ví dụ. [System Information Functions](https://www.postgresql.org/docs/18/functions-info.html).

Các hàm này không tự chứng minh mọi hàng đều truy cập được hoặc nghiệp vụ đã cho phép. Quyền đối tượng và policy hàng cần được kiểm tra riêng.

### 7.3. Kiểm tra khả năng đọc hàng

~~~sql
SELECT id, tenant_id, amount, status
FROM pam_lab.adjustment
ORDER BY id;
~~~

Với policy lab và danh tính phù hợp, chỉ dữ liệu tenant 42 được hiển thị. Nếu thấy tenant 84, cần xem lại danh tính, ownership, thuộc tính bypass, policy và các nguồn quyền liên quan.

Không dùng dữ liệu khách hàng thật để kiểm tra khả năng lọc trong môi trường học.

### 7.4. Thử thay đổi được phép trong transaction lab

~~~sql
BEGIN;

UPDATE pam_lab.adjustment
SET status = 'reviewed',
    note = 'checked in lab'
WHERE id = 1001
  AND tenant_id = 42
  AND status = 'pending'
RETURNING id, tenant_id, status, note;

ROLLBACK;
~~~

Ví dụ dùng ROLLBACK để không giữ thay đổi trong bài thử. Ở môi trường thật, quyết định commit hoặc rollback phải theo kế hoạch đã duyệt.

Điều kiện trạng thái giúp phát hiện dữ liệu không còn ở trạng thái mong đợi. Nếu không có hàng nào được cập nhật, cần chẩn đoán nguyên nhân thay vì tự bỏ điều kiện và chạy lại.

### 7.5. Kiểm tra từ chối

Trong các ca lab riêng, cần xác minh:

- Không sửa được amount bằng quyền role này.
- Không DELETE được hàng.
- Không TRUNCATE được bảng.
- Không thêm được hàng có tenant_id khác 42.
- Không đọc hoặc sửa được hàng tenant khác qua đường đã thiết kế.

Các câu lệnh dự kiến gây lỗi nên được chạy trong ca riêng. Nếu một statement lỗi trong transaction PostgreSQL, cần xử lý trạng thái transaction trước khi chạy tiếp; đừng trộn nhiều phép thử rồi hiểu sai lỗi tiếp theo.

## 8. Quyền SQL không thay thế quyền nghiệp vụ

### 8.1. Một cột có thể chứa nhiều mức hậu quả

Nếu người dùng được UPDATE status, họ có thể có khả năng đổi trực tiếp từ pending sang reviewed trong phạm vi SQL cho phép. Cơ sở dữ liệu không tự biết người đó đã đọc hồ sơ hay có phê duyệt độc lập.

Một yêu cầu nghiệp vụ chặt hơn có thể là:

- Chỉ sửa đúng bản ghi được duyệt.
- Chỉ khi trạng thái hiện tại phù hợp.
- Chỉ trong một khoảng thời gian.
- Có người duyệt khác người thực hiện.
- Có hạn mức giá trị.
- Có kiểm tra dữ liệu liên quan.
- Không được sửa những hồ sơ đang bị giữ lại.

Những điều kiện này phải được thực thi bởi một thiết kế cụ thể, không chỉ nằm trong ghi chú ticket.

### 8.2. Khi nên dùng đường thao tác chuyên biệt

Với hành động hậu quả cao, có thể cho người dùng gọi một tác vụ hoặc routine đã được kiểm soát thay vì cho UPDATE trực tiếp.

Đường đó cần kiểm tra danh tính, tham số, phạm vi và trạng thái. Nếu đồng thời vẫn giữ quyền DML trực tiếp đủ rộng, người dùng có thể bỏ qua workflow.

### 8.3. Routine có quyền cao cần được bảo vệ

Trong PostgreSQL, SECURITY DEFINER thay đổi ngữ cảnh quyền thực thi theo owner của function. Thiết kế phải xem xét owner, quyền EXECUTE, tên đối tượng, search_path và cách xử lý đầu vào. [CREATE FUNCTION và SECURITY DEFINER](https://www.postgresql.org/docs/18/sql-createfunction.html).

Một function nhận SQL tùy ý rồi chạy bằng quyền mạnh có thể làm mất ý nghĩa của role DML hẹp.

Không khẳng định tài khoản là chỉ đọc toàn hệ thống chỉ vì nó không có UPDATE trực tiếp trên bảng. Cần xét những routine và đường thực thi khác mà nó được phép gọi.

## 9. Giới hạn số hàng, giao dịch và thay đổi đồng thời

### 9.1. GRANT không phải hạn mức số hàng

Quyền UPDATE trên một cột không tự giới hạn một hàng mỗi lần. Nếu người dùng được gửi SQL trực tiếp, họ có thể viết điều kiện rộng hơn trong phạm vi hàng được phép.

Giới hạn số lượng, tập ID được duyệt và điều kiện nghiệp vụ cần được thực thi trong workflow hoặc cơ chế đích phù hợp.

### 9.2. Bản xem trước có thể cũ

Đếm số hàng trước khi sửa rồi thực hiện sau đó không bảo đảm cùng một tập dữ liệu. Các transaction khác có thể tạo hoặc thay đổi hàng giữa hai thời điểm.

Tùy nhiệm vụ, cần dùng điều kiện trạng thái, phiên bản, khóa hoặc mức cô lập phù hợp. Không sao chép một giải pháp khóa cho mọi trường hợp vì nó có thể tạo chờ đợi và gián đoạn.

### 9.3. Transaction không giải quyết mọi hậu quả

Transaction hỗ trợ kiểm soát trạng thái trong cơ sở dữ liệu theo khả năng của engine. Nhưng tác dụng phụ bên ngoài hoặc công việc được hệ thống khác nhận có thể có vòng đời riêng.

Cần biết trigger, routine và tích hợp liên quan làm gì trước khi kết luận ROLLBACK sẽ đảo ngược mọi hậu quả.

### 9.4. Số hàng thay đổi chưa chứng minh dữ liệu đúng

Cập nhật một hàng có thể vẫn là cập nhật sai khách hàng hoặc sai trạng thái. Bằng chứng cần kiểm tra cả định danh, điều kiện và kết quả nghiệp vụ.

Một phản hồi “statement executed” cũng không tự chứng minh transaction đã commit. Khi client mất kết nối gần thời điểm commit, có thể cần đối soát trạng thái trước khi retry.

## 10. Phụ thuộc ngoài bảng được cấp quyền

### 10.1. Schema, sequence và đối tượng hỗ trợ

Quyền trên bảng không tự bao gồm mọi quyền trên đối tượng phụ thuộc. Ví dụ, một default dùng sequence có thể đòi xem xét quyền sequence riêng theo cách triển khai.

Khi xử lý lỗi, kiểm tra đối tượng cần dùng thực tế. Tránh cấp ALL cho mọi bảng và sequence chỉ vì một đường INSERT chưa hoạt động.

USAGE trên schema cho phép tìm và dùng đối tượng theo quyền tương ứng; nó không đồng nghĩa CREATE đối tượng hoặc SELECT mọi bảng.

### 10.2. Trigger và quan hệ dữ liệu

Một DML trên bảng có thể kích hoạt trigger hoặc tác động đến dữ liệu liên quan tùy định nghĩa, ràng buộc và quyền thực thi.

Kế hoạch thay đổi cần biết những tác động đó. Không chỉ xem bảng xuất hiện đầu tiên trong câu lệnh rồi bỏ qua ảnh hưởng đến bảng khác.

### 10.3. View và function

Một view hoặc function có thể cung cấp một đường truy cập khác tới dữ liệu. Cần đánh giá ngữ nghĩa bảo mật cụ thể thay vì mặc định quyền trực tiếp trên bảng giải thích mọi quyền hiệu lực.

Những đối tượng được thiết kế để che cột hoặc giới hạn thao tác cũng phải được kiểm tra quyền thay đổi định nghĩa và quyền truy cập đường gốc.

## 11. Quyền mới và đối tượng tạo trong tương lai

Một lần cấp trên tất cả bảng hiện có trong schema không tự giải thích quyền của bảng được tạo sau đó. Ngược lại, default privileges quá rộng có thể âm thầm cấp thêm dữ liệu mới cho role cũ.

PostgreSQL ALTER DEFAULT PRIVILEGES tác động tới đối tượng được tạo trong tương lai và không sửa grant của đối tượng đã tồn tại; cần xét role tạo đối tượng và phạm vi cấu hình. [ALTER DEFAULT PRIVILEGES](https://www.postgresql.org/docs/18/sql-alterdefaultprivileges.html).

### 11.1. Migration là một sự kiện thay đổi quyền

Khi thêm bảng mới hoặc thay cột, cần hỏi:

- Ai sở hữu đối tượng?
- Role nào nhận quyền mặc định?
- Bảng có cùng mức nhạy cảm với các bảng cũ không?
- Policy hàng và đường routine đã được thiết lập chưa?
- Có khoảng thời gian đối tượng tồn tại với quyền không mong muốn không?

Không chỉ kiểm tra ứng dụng chạy được sau migration. Cần kiểm tra cả các truy cập cố ý không cho phép.

### 11.2. Tránh cấp rộng để giảm công bảo trì

Quyền “mọi bảng hiện tại và tương lai” có thể phù hợp một số vai trò được tin cậy, nhưng phải là quyết định có chủ đích. Nó không nên là mặc định cho mọi tài khoản hỗ trợ hoặc báo cáo.

## 12. Thiết kế PAM cho DML tạm thời

Một yêu cầu cấp DML nên chứa:

| Nội dung | Câu hỏi |
|---|---|
| Danh tính | Ai thực hiện và ai chịu trách nhiệm? |
| Đích | Database, schema, bảng và môi trường nào? |
| Quyền | Đọc, thêm, sửa hoặc xóa gì? |
| Cột và hàng | Cột nào, tenant nào, tập đối tượng nào? |
| Nghiệp vụ | Điều kiện trạng thái, hạn mức và phê duyệt nào? |
| Thời hạn | Khi nào được cấp, gia hạn và kết thúc? |
| Phiên | Những connection và transaction nào cần theo dõi? |
| Bằng chứng | Kết quả cấp, thao tác, commit và readback nào? |
| Phục hồi | Có thể rollback, bù trừ hoặc khôi phục bằng cách nào? |

### 12.1. Cấp bằng role hoặc danh tính có vòng đời

Có thể cấp membership tạm thời hoặc một danh tính dành cho yêu cầu theo khả năng hệ thống. Khi dùng credential, cần bảo vệ bằng vault hoặc cơ chế cấp phù hợp.

Không lấy việc credential có thời hạn làm bằng chứng rằng mọi phiên đang mở và quyền được cấp đã tự kết thúc.

### 12.2. Không cấp khả năng phân quyền tiếp nếu không cần

WITH GRANT OPTION trên đối tượng và khả năng quản trị membership là những quyền cần được xét riêng. Người làm một thay đổi dữ liệu thường không cần cấp quyền cho người khác.

Nếu có nhu cầu đặc biệt, phải theo dõi quyền phát sinh và cách thu hồi cả chuỗi liên quan.

### 12.3. Theo dõi ngữ cảnh connection pool

Nếu nhiều người dùng chung một pool, audit database có thể chỉ nhìn thấy principal của pool. Cần một cơ chế liên kết danh tính và yêu cầu có thể tin cậy.

Trường tên ứng dụng hoặc mã yêu cầu do client tự khai có thể hữu ích cho tương quan nhưng không tự là chứng cứ xác thực người dùng.

## 13. Thu hồi và xác minh truy cập kết thúc

Ví dụ thu hồi membership trong lab, do người có thẩm quyền thực hiện:

~~~sql
REVOKE pam_adjustment_operator
FROM example_operator;
~~~

Đây là thao tác loại bỏ một đường membership, không phải cam kết xóa mọi quyền của example_operator.

### 13.1. Kiểm tra các nguồn quyền khác

Cần xét grant trực tiếp, role khác, ownership, PUBLIC và routine được phép gọi. Nếu có quyền cấp tiếp, phải đối soát những grant phát sinh.

Trong PostgreSQL, REVOKE xử lý quyền hoặc membership được chỉ định; các quyền nhận qua nguồn khác và phụ thuộc của grant cần được xem xét. Không dùng CASCADE tùy tiện mà chưa đánh giá tác động. [PostgreSQL 18: REVOKE](https://www.postgresql.org/docs/18/sql-revoke.html).

### 13.2. Phiên đang có quyền cần được kiểm tra riêng

Không suy từ việc thu hồi membership hoặc đổi mật khẩu rằng mọi connection đã biến mất. Đặc biệt, một phiên đã đổi ngữ cảnh role hoặc đang thực hiện câu lệnh cần được xử lý theo hành vi thực tế của hệ quản trị.

Phải xác định khi nào cần đóng connection, dừng statement hoặc xử lý transaction. Những biện pháp đó có thể ảnh hưởng lock, công việc đang chạy và tính nhất quán.

### 13.3. Thu hồi không hoàn tác commit

Dữ liệu đã commit vẫn tồn tại sau khi quyền người thực hiện bị thu hồi. Bản sao đã xuất không tự bị thu hồi.

Phục hồi cần một quyết định riêng: hoàn nguyên, bù trừ, khôi phục hoặc xử lý hậu quả. Không khôi phục dữ liệu một cách mù quáng nếu những giao dịch hợp lệ khác đã thay đổi cùng đối tượng.

### 13.4. Kiểm tra sau thu hồi

Nên xác minh bằng ngữ cảnh danh tính phù hợp:

- Không thể nhận lại quyền qua đường đã đóng.
- Không còn quyền DML ngoài chính sách từ các nguồn còn lại.
- Phiên và transaction liên quan có trạng thái rõ.
- Không còn grant hoặc credential phát sinh chưa xử lý.
- Trạng thái dữ liệu cuối đã được đối chiếu.

## 14. Audit và bằng chứng DML

### 14.1. Những gì cần liên kết

- Người yêu cầu và người phê duyệt.
- Danh tính database, role hiệu lực và phiên.
- Database, schema và đối tượng.
- Loại thao tác và phạm vi được phép.
- Mốc bắt đầu, phản hồi, commit hoặc rollback.
- Kết quả kiểm tra dữ liệu.
- Sự kiện cấp và thu hồi.
- Ngoại lệ còn mở.

Không mặc định mọi hệ quản trị ghi đủ những trường này. Phải cấu hình và kiểm thử nguồn audit phù hợp.

### 14.2. Bảo vệ dữ liệu trong log

SQL có thể chứa thông tin khách hàng, token hoặc giá trị nghiệp vụ nhạy cảm trong literal và tham số. Ghi toàn bộ statement hoặc kết quả không phải lúc nào cũng phù hợp.

Có thể cần kết hợp mẫu truy vấn, metadata phiên, mã công việc, định danh đối tượng được phép lưu và kết quả đã làm sạch. Cần đủ dữ kiện để điều tra nhưng không tạo kho dữ liệu nhạy cảm mới ngoài kiểm soát.

### 14.3. Audit thành công khác với xác minh nghiệp vụ

Một log cho biết UPDATE được chấp nhận chưa chứng minh người dùng sửa đúng giá trị hoặc commit đã được xác nhận sau sự cố mạng.

Người hoặc hệ thống xác minh cần đối chiếu kết quả với kế hoạch. Nếu dữ kiện chưa đủ, báo cáo nên ghi chưa đối soát thay vì đoán thành công hoặc chạy lại ngay.

## 15. Tình huống: sửa ghi chú nhưng vô tình có quyền sửa tiền

Một tài khoản hỗ trợ được cấp role mới chỉ sửa note. Tuy nhiên, tài khoản đã là thành viên của một role cũ có UPDATE toàn bảng.

### 15.1. Vì sao thiết kế nhìn có vẻ đúng nhưng vẫn hở?

Người quản trị chỉ kiểm tra manifest grant mới, không kiểm tra toàn bộ quyền hiệu lực. Role hẹp không loại bỏ role rộng.

Trong cùng hệ thống, một routine được phép gọi cũng có thể tạo đường sửa dữ liệu ngoài dự kiến nếu không được kiểm kê.

### 15.2. Cách xử lý

1. Kiểm kê mọi nguồn quyền của tài khoản.
2. Xác minh quyền cột bằng ngữ cảnh thật.
3. Loại bỏ hoặc điều chỉnh đường rộng không còn cần thiết theo kế hoạch.
4. Rà soát routine và quyền sở hữu liên quan.
5. Kiểm thử tác vụ được phép và tác vụ phải bị từ chối.
6. Theo dõi thay đổi quyền sau migration hoặc thay membership.
7. Lưu bằng chứng trạng thái cuối, không chỉ câu GRANT mới.

### 15.3. Nếu đã có thay đổi sai

Không dừng ở việc thu hồi role. Cần xác định những bản ghi đã bị tác động, transaction nào đã commit và hậu quả nghiệp vụ.

Phương án phục hồi cần tính tới thay đổi hợp lệ diễn ra sau đó, thay vì chép lại toàn bộ một bản dữ liệu cũ.

## 16. Ma trận kiểm thử

| Ca kiểm thử | Kết quả cần xác minh |
|---|---|
| Đọc cột được phép | Thành công trong phạm vi dự kiến |
| Đọc dữ liệu ngoài tenant | Bị giới hạn bởi cơ chế thực thi đã chọn |
| Sửa note | Được phép theo kế hoạch |
| Sửa amount | Bị từ chối nếu không được cấp qua đường nào khác |
| Thêm hàng đúng tenant | Theo đúng quyền và policy |
| Thêm hàng sai tenant | Không vượt giới hạn hàng |
| DELETE hoặc TRUNCATE | Không được phép nếu nằm ngoài nhu cầu |
| Gọi routine | Không tạo đường vượt phạm vi ngoài thiết kế |
| Dùng role khác | Không còn quyền rộng bị bỏ sót |
| Hết cửa sổ JIT | Có bằng chứng về quyền và phiên còn lại |
| Timeout gần commit | Đối soát trước retry |
| Tạo bảng mới | Default privileges và policy phù hợp |
| Ghi log câu lệnh | Không làm lộ dữ liệu ngoài nơi được phép |

Kiểm thử từ chối có giá trị ngang kiểm thử thành công. Các phép thử cần dùng dữ liệu giả hoặc đối tượng được phê duyệt.

## 17. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách cải thiện |
|---|---|---|
| Cấp ALL cho tiện | Thêm quyền ngoài DML cần thiết | Liệt kê quyền và đối tượng |
| Coi USAGE schema là quyền mọi bảng | Hiểu sai phạm vi | Kiểm tra từng lớp quyền |
| Chỉ xem grant trực tiếp | Bỏ sót role và ownership | Kiểm kê quyền hiệu lực |
| Quyền cột hẹp nhưng giữ quyền bảng rộng | Giới hạn cột không đạt mục tiêu | Xử lý nguồn quyền rộng |
| Yêu cầu người dùng tự thêm WHERE tenant | Giới hạn chỉ nằm trong hướng dẫn | Dùng cơ chế hàng hoặc workflow phù hợp |
| Coi RLS bảo vệ khỏi mọi owner/superuser | Bỏ sót đường bypass | Kiểm thử đúng danh tính và quyền quản lý |
| Nghĩ UPDATE status là phê duyệt nghiệp vụ | Bỏ qua phân tách trách nhiệm | Kiểm soát chuyển trạng thái |
| Không xét trigger/routine | Thiếu ảnh hưởng gián tiếp | Rà soát đường thực thi |
| Chỉ đổi password để kết thúc quyền | Có thể còn phiên và nguồn quyền khác | Xác minh quyền và connection |
| Retry khi không rõ commit | Có thể ghi trùng hoặc sai trạng thái | Đối soát và chống lặp theo nghiệp vụ |
| Log toàn bộ dữ liệu để kiểm toán | Tạo nguồn lộ mới | Lưu bằng chứng tối thiểu cần thiết |
| Thu hồi xong thì đóng hồ sơ | Bỏ quên dữ liệu đã commit | Xác minh kết quả và hậu quả |

## 18. Thực hành

### Bài tập 1: Thiết kế role hỗ trợ

Một nhóm chỉ cần đọc mã hồ sơ, trạng thái và sửa ghi chú. Họ không được sửa số tiền hoặc xóa dữ liệu.

Hãy lập ma trận quyền theo bảng và cột. Nêu các nguồn quyền khác phải kiểm tra để role hẹp có hiệu lực thực tế.

### Bài tập 2: Giới hạn tenant

Một người dùng có UPDATE trên cột note nhưng chỉ được thao tác tenant 42.

Hãy giải thích vì sao quyền cột chưa đủ. Thiết kế kiểm thử policy hàng bằng danh tính không phải owner và nêu rủi ro nếu tenant được lấy từ dữ liệu client tự khai.

### Bài tập 3: Cửa sổ DML tạm thời

Một tài khoản được cấp membership trong 20 phút. Sau khi thu hồi, vẫn còn connection mở và một transaction chưa xác định kết quả.

Hãy viết runbook ngăn cấp mới, đánh giá phiên, xử lý transaction và xác minh quyền. Không mặc định đổi mật khẩu sẽ giải quyết toàn bộ.

### Bài tập 4: Mất phản hồi commit

Một công cụ báo timeout ngay khi gửi COMMIT cho tác vụ điều chỉnh dữ liệu.

Hãy xác định bằng chứng cần có trước khi retry, cách đối soát và cách dùng định danh nghiệp vụ để giảm nguy cơ thực hiện hai lần.

### Bài tập 5: Kiểm tra sau migration

Một bảng nhạy cảm mới được tạo trong schema mà role báo cáo trước đây được cấp quyền rộng.

Hãy đánh giá default privileges, owner, quyền hiện có, policy hàng và khả năng truy cập qua view hoặc routine. Nêu ca từ chối cần kiểm thử.

## 19. Điểm cần ghi nhớ

DML privilege phải được thiết kế theo dữ liệu và nhiệm vụ: đúng đối tượng, đúng cột, đúng hàng và đúng điều kiện nghiệp vụ. Quyền SQL chỉ là một phần của hệ thống kiểm soát, không tự tạo quy trình phê duyệt hoặc hạn mức.

PAM cần quản lý cả danh tính, nguồn quyền, thời hạn, phiên và bằng chứng kết quả. Một lần thu hồi hoàn tất phải được xác minh bằng quyền hiệu lực và trạng thái dữ liệu cuối cùng, đồng thời xử lý những truy cập hoặc hậu quả đã phát sinh.
