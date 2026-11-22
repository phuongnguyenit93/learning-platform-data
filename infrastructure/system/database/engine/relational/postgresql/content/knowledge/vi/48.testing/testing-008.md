# Kiểm thử quyền role, RLS và hành vi từ chối truy cập

Trong PostgreSQL, quyền truy cập dữ liệu được quyết định qua nhiều lớp. Một role có thể kết nối được vào cơ sở dữ liệu nhưng vẫn không có quyền dùng schema; có quyền đọc bảng nhưng chỉ được nhìn thấy một phần hàng; hoặc được phép cập nhật một hàng nhưng không được thay đổi hàng đó sang tenant khác. Vì vậy, kiểm thử bảo mật phải xác minh cả quyền của role, quyền trên đối tượng và chính sách Row-Level Security (RLS), đồng thời xác định chính xác PostgreSQL phản hồi thế nào khi truy cập bị từ chối.

Bài học này hướng dẫn cách dựng vai trò kiểm thử, kiểm tra quyền hiệu lực, tạo chính sách RLS, xác minh kết quả cho từng lệnh SQL và phân biệt trường hợp bị lỗi với trường hợp truy vấn chạy thành công nhưng không trả về hàng nào.

## 1. Các lớp cần kiểm thử

Một lượt truy cập thường đi qua những lớp sau:

1. **Xác thực kết nối:** người dùng có đăng nhập được bằng thông tin xác thực và phương thức kết nối hiện hành hay không.
2. **Role và membership:** phiên kết nối đang chạy dưới role nào, role đó được kế thừa quyền từ những role nào và có thể chuyển sang role nào.
3. **Quyền trên đối tượng:** role có quyền dùng schema, đọc bảng, ghi cột, gọi function hoặc dùng sequence cần thiết hay không.
4. **RLS:** nếu bảng bật RLS, các hàng nào được phép đọc, cập nhật, xóa hoặc ghi mới theo policy áp dụng cho role hiện tại.
5. **Đường thực thi đặc biệt:** view, function có SECURITY DEFINER, partition hoặc kết nối qua connection pool có làm thay đổi ngữ cảnh quyền hay không.

Các lớp này có thể tạo ra kết quả giống nhau ở bề mặt nhưng nguyên nhân khác nhau. Ví dụ, câu SELECT trả về 0 hàng có thể do bảng thật sự không có dữ liệu phù hợp hoặc do RLS đã lọc hết hàng. Ngược lại, lỗi “permission denied” thường cho biết role thiếu quyền ở lớp đối tượng trước khi truy vấn có thể đọc dữ liệu.

Khi viết một test, hãy ghi rõ bốn yếu tố: role thực thi, câu lệnh, dữ liệu đầu vào và kết quả mong đợi. Không nên chỉ kiểm tra rằng câu lệnh “không thành công”; cần biết nó bị chặn bởi GRANT/REVOKE hay bởi policy RLS.

## 2. Hiểu đúng role và ngữ cảnh thực thi

Trong PostgreSQL, role là đơn vị quản lý danh tính và quyền. Một role có thể có thuộc tính LOGIN để đăng nhập hoặc NOLOGIN để được dùng như nhóm quyền. Một tài khoản đăng nhập thường được cấp membership vào một hoặc nhiều role nhóm.

Hai hàm thông tin quan trọng là:

- **session_user:** danh tính ban đầu của phiên kết nối.
- **current_user:** role đang được dùng để kiểm tra quyền tại thời điểm câu lệnh chạy.

Lệnh SET ROLE thay đổi current_user sang role đích nếu phiên hiện tại được phép chuyển sang role đó. session_user vẫn giữ nguyên. SET LOCAL ROLE chỉ có hiệu lực trong transaction hiện tại, rất hữu ích cho kiểm thử vì ROLLBACK hoặc kết thúc transaction sẽ khôi phục ngữ cảnh trước đó.

Ví dụ:

~~~sql
BEGIN;
SET LOCAL ROLE app_reader;

SELECT
    session_user,
    current_user;

ROLLBACK;
~~~

Nếu kết nối ban đầu bằng app_login và tài khoản này được phép chuyển sang app_reader, kết quả thường là session_user = app_login và current_user = app_reader. Hãy kiểm tra cả hai giá trị để phát hiện test đang chạy nhầm role.

Membership không đồng nghĩa mọi quyền luôn được kế thừa giống nhau. Thuộc tính INHERIT và các tùy chọn membership quyết định quyền có tự động có hiệu lực hay phải chuyển role bằng SET ROLE. Hành vi membership có thêm tùy chọn chi tiết ở các phiên bản PostgreSQL mới, vì vậy test phải chạy trên phiên bản thực tế của hệ thống. Cách đáng tin cậy là xác minh quyền hiệu lực bằng các hàm kiểm tra privilege và thực thi câu lệnh dưới role đích.

Không cấp SUPERUSER, BYPASSRLS, CREATEROLE hoặc CREATEDB cho role ứng dụng thông thường. Đặc biệt, BYPASSRLS cho phép bỏ qua chính sách RLS và có thể làm cho toàn bộ test phân quyền hàng mất ý nghĩa.

## 3. Kiểm tra quyền trên schema và đối tượng

GRANT và REVOKE quản lý quyền ở nhiều cấp. Có quyền SELECT trên bảng chưa đủ nếu role không có USAGE trên schema chứa bảng. Tương tự, INSERT có thể cần quyền trên sequence nếu cột dùng sequence thông thường như SERIAL. Cần kiểm tra các đối tượng mà câu lệnh thực tế sử dụng.

Một số quyền thường gặp:

| Phạm vi | Quyền cần xem xét | Ý nghĩa |
|---|---|---|
| Database | CONNECT, CREATE, TEMPORARY | Kết nối, tạo schema hoặc tạo bảng tạm |
| Schema | USAGE, CREATE | Tra cứu đối tượng trong schema hoặc tạo đối tượng |
| Table | SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER | Đọc, ghi, xóa, cắt bảng và các thao tác liên quan |
| Column | SELECT, INSERT, UPDATE | Giới hạn truy cập ở từng cột |
| Sequence | USAGE, SELECT, UPDATE | Lấy giá trị hoặc điều chỉnh sequence |
| Function | EXECUTE | Gọi function hoặc procedure |

Ví dụ cấp quyền tối thiểu cho role đọc và role sửa tài liệu:

~~~sql
GRANT USAGE ON SCHEMA public TO app_reader, app_editor;

GRANT SELECT
ON TABLE public.documents
TO app_reader;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE public.documents
TO app_editor;
~~~

Có thể thu hồi quyền không còn cần thiết bằng REVOKE:

~~~sql
REVOKE DELETE
ON TABLE public.documents
FROM app_editor;
~~~

Đừng dùng GRANT ALL chỉ để làm test chạy qua. Cấp quyền quá rộng có thể che giấu lỗi thiết kế và khiến role ứng dụng có khả năng thao tác ngoài yêu cầu.

Các hàm sau giúp kiểm tra quyền hiệu lực. Chúng xét quyền trực tiếp và quyền có hiệu lực thông qua membership phù hợp:

~~~sql
SELECT
    has_schema_privilege(
        'app_reader',
        'public',
        'USAGE'
    ) AS can_use_schema,
    has_table_privilege(
        'app_reader',
        'public.documents',
        'SELECT'
    ) AS can_select,
    has_table_privilege(
        'app_reader',
        'public.documents',
        'INSERT'
    ) AS can_insert,
    has_column_privilege(
        'app_reader',
        'public.documents',
        'title',
        'UPDATE'
    ) AS can_update_title;
~~~

Kiểm tra membership của role đăng nhập:

~~~sql
SELECT
    pg_has_role(
        'app_login',
        'app_reader',
        'MEMBER'
    ) AS is_reader_member;
~~~

Kết quả từ hàm kiểm tra quyền là bằng chứng hữu ích, nhưng vẫn nên chạy câu lệnh thật dưới role đích. Một truy vấn có thể phụ thuộc đồng thời vào quyền schema, quyền bảng, quyền cột, quyền function và policy RLS.

## 4. Cơ chế Row-Level Security

RLS giới hạn những hàng mà một role được phép thao tác. RLS hoạt động cùng với quyền SQL thông thường: role trước hết phải có quyền cần thiết trên đối tượng; sau đó policy RLS xác định hàng nào được phép truy cập.

Bật RLS trên bảng:

~~~sql
ALTER TABLE public.documents
ENABLE ROW LEVEL SECURITY;
~~~

Tắt RLS:

~~~sql
ALTER TABLE public.documents
DISABLE ROW LEVEL SECURITY;
~~~

Khi RLS được bật, nếu không có policy phù hợp với role và loại lệnh đang thực hiện, PostgreSQL áp dụng mặc định từ chối. Với SELECT, điều này thường thể hiện thành không nhìn thấy hàng nào. Với INSERT hoặc UPDATE, hàng mới không vượt qua điều kiện policy sẽ bị từ chối.

### 4.1. USING và WITH CHECK

Hai biểu thức chính trong policy có nhiệm vụ khác nhau:

- **USING** quyết định những hàng hiện có mà câu lệnh được phép nhìn thấy hoặc tác động. Nó được dùng cho SELECT, UPDATE và DELETE.
- **WITH CHECK** xác minh trạng thái của hàng sau khi INSERT hoặc UPDATE. Hàng mới phải thỏa mãn biểu thức này.

Ví dụ policy chỉ cho phép đọc tài liệu thuộc tenant hiện tại:

~~~sql
CREATE POLICY documents_read_tenant
ON public.documents
FOR SELECT
TO app_reader, app_editor
USING (
    tenant_id =
    current_setting('app.tenant_id', true)::uuid
);
~~~

Policy cho phép role sửa tài liệu của tenant hiện tại:

~~~sql
CREATE POLICY documents_update_tenant
ON public.documents
FOR UPDATE
TO app_editor
USING (
    tenant_id =
    current_setting('app.tenant_id', true)::uuid
)
WITH CHECK (
    tenant_id =
    current_setting('app.tenant_id', true)::uuid
);
~~~

USING ngăn role chọn hoặc cập nhật hàng thuộc tenant khác. WITH CHECK ngăn role thay đổi một hàng hợp lệ thành hàng thuộc tenant khác. Nếu chỉ kiểm tra USING, test có thể bỏ sót lỗi cho phép chuyển quyền sở hữu hàng.

Với INSERT, policy thường dùng WITH CHECK. Với DELETE, policy dùng USING. Với UPDATE, cần kiểm tra cả hàng cũ và hàng mới. Khi policy FOR ALL hoặc FOR UPDATE không khai báo WITH CHECK, PostgreSQL có thể dùng biểu thức USING làm điều kiện kiểm tra hàng mới theo quy tắc của policy; nên khai báo rõ cả hai biểu thức khi cần kiểm soát chuyển tenant để người đọc và người bảo trì dễ nhận ra ý định.

### 4.2. Nhiều policy cùng áp dụng

Policy có thể là permissive hoặc restrictive:

- Các policy permissive kết hợp với nhau bằng OR. Một policy permissive cho phép hàng đi qua có thể đủ để mở quyền.
- Các policy restrictive kết hợp với nhau bằng AND. Tất cả policy restrictive áp dụng phải được thỏa mãn.
- Điều kiện tổng thể cần ít nhất một policy permissive cho phép, đồng thời phải vượt qua mọi policy restrictive áp dụng.

Vì vậy, thêm một policy mới có thể mở rộng hoặc thu hẹp quyền tùy thuộc loại policy và role đích. Test phải xem toàn bộ policy cùng áp dụng, không chỉ policy vừa được tạo.

Nếu không ghi TO, policy áp dụng cho PUBLIC. Phạm vi role của policy cũng chịu ảnh hưởng từ membership và role hiện hành. Hãy kiểm tra role thật sự chạy câu lệnh thay vì chỉ nhìn tên role được ghi trong policy.

### 4.3. Chủ sở hữu bảng và role có quyền bỏ qua RLS

Mặc định, chủ sở hữu bảng thường không bị áp dụng RLS trên bảng của mình. SUPERUSER và role có thuộc tính BYPASSRLS luôn có thể bỏ qua RLS.

Có thể buộc chủ sở hữu bảng cũng chịu policy:

~~~sql
ALTER TABLE public.documents
FORCE ROW LEVEL SECURITY;
~~~

FORCE ROW LEVEL SECURITY không biến RLS thành cơ chế chặn SUPERUSER hoặc role BYPASSRLS. Khi kiểm thử, không nên dùng tài khoản quản trị làm đại diện cho role ứng dụng. Hãy dùng role có quyền đúng như cấu hình production.

Thiết lập row_security = off cũng không tắt cơ chế bảo vệ để người dùng đọc mọi hàng. Nếu một truy vấn sẽ bị RLS lọc, PostgreSQL báo lỗi thay vì âm thầm trả về kết quả đã lọc. Thiết lập này hữu ích trong một số quy trình cần phát hiện dữ liệu bị lọc, nhưng không phải cách bỏ qua policy.

## 5. Dựng kịch bản kiểm thử RLS

Ví dụ sau mô phỏng hai tenant. Người đọc chỉ được xem tài liệu; người sửa được đọc, thêm, cập nhật và xóa tài liệu trong tenant hiện tại.

Chạy phần tạo role và bảng bằng tài khoản quản trị trong cơ sở dữ liệu kiểm thử riêng:

~~~sql
CREATE ROLE app_reader NOLOGIN;
CREATE ROLE app_editor NOLOGIN;

CREATE ROLE app_login LOGIN NOINHERIT;
GRANT app_reader, app_editor TO app_login;

CREATE TABLE public.documents (
    id bigint PRIMARY KEY,
    tenant_id uuid NOT NULL,
    title text NOT NULL
);

INSERT INTO public.documents (id, tenant_id, title)
VALUES
    (
        1,
        '11111111-1111-4111-8111-111111111111',
        'Tài liệu tenant A'
    ),
    (
        2,
        '22222222-2222-4222-8222-222222222222',
        'Tài liệu tenant B'
    );

GRANT USAGE ON SCHEMA public
TO app_reader, app_editor;

GRANT SELECT
ON public.documents
TO app_reader;

GRANT SELECT, INSERT, UPDATE, DELETE
ON public.documents
TO app_editor;

ALTER TABLE public.documents
ENABLE ROW LEVEL SECURITY;

CREATE POLICY documents_read_tenant
ON public.documents
FOR SELECT
TO app_reader, app_editor
USING (
    tenant_id =
    current_setting('app.tenant_id', true)::uuid
);

CREATE POLICY documents_insert_tenant
ON public.documents
FOR INSERT
TO app_editor
WITH CHECK (
    tenant_id =
    current_setting('app.tenant_id', true)::uuid
);

CREATE POLICY documents_update_tenant
ON public.documents
FOR UPDATE
TO app_editor
USING (
    tenant_id =
    current_setting('app.tenant_id', true)::uuid
)
WITH CHECK (
    tenant_id =
    current_setting('app.tenant_id', true)::uuid
);

CREATE POLICY documents_delete_tenant
ON public.documents
FOR DELETE
TO app_editor
USING (
    tenant_id =
    current_setting('app.tenant_id', true)::uuid
);
~~~

Trong ví dụ, app_login là role đăng nhập có thể chuyển sang app_reader hoặc app_editor. Thuộc tính NOINHERIT buộc kịch bản thể hiện rõ thao tác chuyển role. Hãy đăng nhập bằng app_login khi kiểm thử tích hợp; trong môi trường test đơn giản, tài khoản quản trị cũng có thể dùng SET ROLE để kiểm tra từng role, nhưng cần xác nhận current_user sau khi chuyển role.

Biểu thức policy dùng biến cấu hình tùy chỉnh app.tenant_id để minh họa cách truyền tenant context. Trong test, có thể đặt giá trị này trong transaction bằng set_config với tham số thứ ba là true:

~~~sql
SELECT set_config(
    'app.tenant_id',
    '11111111-1111-4111-8111-111111111111',
    true
);
~~~

Giá trị true làm thiết lập chỉ tồn tại trong transaction hiện tại. Trong ứng dụng thật, tenant context phải được backend tin cậy thiết lập sau khi xác thực danh tính. Không được tin một tenant_id do người dùng cuối tự gửi hoặc cho phép họ chạy SQL tùy ý để tự đặt biến này; nếu họ có thể tự chọn tenant context thì policy sẽ không bảo vệ được ranh giới tenant.

### 5.1. Kiểm tra role đọc

~~~sql
BEGIN;

SET LOCAL ROLE app_reader;

SELECT
    session_user,
    current_user;

SELECT set_config(
    'app.tenant_id',
    '11111111-1111-4111-8111-111111111111',
    true
);

SELECT id, tenant_id, title
FROM public.documents
ORDER BY id;

ROLLBACK;
~~~

Kết quả mong đợi: truy vấn chỉ trả về tài liệu của tenant A. Tài liệu tenant B vẫn tồn tại nhưng không xuất hiện trong kết quả của role đọc.

Có thể kiểm tra role đọc không được INSERT:

~~~sql
BEGIN;

SET LOCAL ROLE app_reader;

SELECT set_config(
    'app.tenant_id',
    '11111111-1111-4111-8111-111111111111',
    true
);

INSERT INTO public.documents (id, tenant_id, title)
VALUES (
    3,
    '11111111-1111-4111-8111-111111111111',
    'Không được phép thêm'
);

ROLLBACK;
~~~

Kết quả mong đợi là lỗi thiếu quyền INSERT trên bảng. Đây là kiểm thử quyền đối tượng, không phải kiểm thử WITH CHECK của RLS, vì app_reader chưa được GRANT INSERT.

### 5.2. Kiểm tra role sửa

Role sửa được thêm tài liệu trong tenant của mình:

~~~sql
BEGIN;

SET LOCAL ROLE app_editor;

SELECT set_config(
    'app.tenant_id',
    '11111111-1111-4111-8111-111111111111',
    true
);

INSERT INTO public.documents (id, tenant_id, title)
VALUES (
    3,
    '11111111-1111-4111-8111-111111111111',
    'Tài liệu mới của tenant A'
);

SELECT id, tenant_id, title
FROM public.documents
ORDER BY id;

ROLLBACK;
~~~

Kết quả mong đợi: INSERT thành công trong tenant A. ROLLBACK giúp hoàn tác dữ liệu thử nghiệm.

Tiếp theo, thử thêm hàng thuộc tenant B khi context vẫn là tenant A:

~~~sql
BEGIN;

SET LOCAL ROLE app_editor;

SELECT set_config(
    'app.tenant_id',
    '11111111-1111-4111-8111-111111111111',
    true
);

INSERT INTO public.documents (id, tenant_id, title)
VALUES (
    4,
    '22222222-2222-4222-8222-222222222222',
    'Tài liệu ghi sai tenant'
);

ROLLBACK;
~~~

Kết quả mong đợi: PostgreSQL từ chối INSERT vì hàng mới không thỏa WITH CHECK. Lỗi này chứng minh role có quyền INSERT ở cấp bảng nhưng policy không cho ghi hàng sang tenant khác.

Kiểm tra UPDATE không thể chuyển hàng sang tenant khác:

~~~sql
BEGIN;

SET LOCAL ROLE app_editor;

SELECT set_config(
    'app.tenant_id',
    '11111111-1111-4111-8111-111111111111',
    true
);

UPDATE public.documents
SET tenant_id = '22222222-2222-4222-8222-222222222222'
WHERE id = 1;

ROLLBACK;
~~~

Kết quả mong đợi: PostgreSQL từ chối cập nhật vì hàng sau khi thay đổi không vượt qua WITH CHECK. Đây là tình huống quan trọng: role được phép sửa hàng ban đầu nhưng không được chuyển hàng đó ra ngoài phạm vi tenant.

Kiểm tra DELETE với hàng thuộc tenant khác:

~~~sql
BEGIN;

SET LOCAL ROLE app_editor;

SELECT set_config(
    'app.tenant_id',
    '11111111-1111-4111-8111-111111111111',
    true
);

DELETE FROM public.documents
WHERE id = 2;

ROLLBACK;
~~~

Kết quả mong đợi: lệnh chạy nhưng xóa 0 hàng vì policy USING không cho role nhìn thấy hoặc tác động hàng tenant B. Đây không phải lỗi SQL.

## 6. Phân biệt các kiểu từ chối truy cập

Không phải mọi tình huống bị chặn đều sinh ra exception. Đây là điểm cần kiểm thử rõ ràng.

| Tình huống | Hành vi thường gặp | Cách xác nhận |
|---|---|---|
| Thiếu quyền schema hoặc bảng | Lỗi permission denied | Kiểm tra SQLSTATE và quyền bằng has_schema_privilege / has_table_privilege |
| SELECT bị RLS lọc hết | Truy vấn thành công, 0 hàng | Kiểm tra tập dữ liệu và policy dưới role thực tế |
| UPDATE hoặc DELETE nhắm hàng bị RLS ẩn | Truy vấn thành công, 0 hàng bị tác động | Kiểm tra số hàng bị ảnh hưởng |
| INSERT vi phạm WITH CHECK | Lỗi từ chối truy cập | Xác nhận SQLSTATE và policy INSERT |
| UPDATE tạo ra hàng vi phạm WITH CHECK | Lỗi từ chối truy cập | Xác nhận trạng thái hàng sau cập nhật không được chấp nhận |
| Không có policy phù hợp khi RLS bật | Mặc định từ chối hàng | Kiểm tra policy theo role và command |

Lỗi thiếu quyền và lỗi policy RLS thường dùng SQLSTATE 42501, tên điều kiện là insufficient_privilege. Vì vậy, chỉ kiểm tra mã lỗi chưa đủ để biết lớp nào đã chặn. Hãy kết hợp mã lỗi, thông báo, role hiện tại và quyền/policy được cấu hình.

Đối với SELECT, RLS thường lọc hàng mà không báo lỗi. Đối với UPDATE và DELETE, số hàng bị tác động có thể bằng 0. Một test chỉ khẳng định “không có exception” sẽ bỏ sót việc ứng dụng không nhìn thấy dữ liệu; ngược lại, một test đòi exception khi SELECT bị lọc cũng sẽ sai kỳ vọng.

Nếu dùng thư viện kiểm thử có hỗ trợ kiểm tra SQLSTATE, hãy xác nhận cả mã lỗi lẫn kết quả nghiệp vụ. Ví dụ với pgTAP, có thể dùng throws_ok để xác nhận một lệnh INSERT ngoài tenant bị từ chối với mã 42501; các truy vấn SELECT/UPDATE/DELETE bị lọc cần assertion về tập kết quả hoặc số hàng bị tác động.

## 7. Đọc cấu hình RLS để tìm nguyên nhân

View hệ thống pg_policies cho biết policy hiện có, loại lệnh, role áp dụng và biểu thức điều kiện:

~~~sql
SELECT
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd,
    qual,
    with_check
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename = 'documents'
ORDER BY policyname;
~~~

Kiểm tra bảng đã bật RLS và FORCE RLS chưa:

~~~sql
SELECT
    c.relname,
    c.relrowsecurity,
    c.relforcerowsecurity
FROM pg_class AS c
WHERE c.oid = 'public.documents'::regclass;
~~~

Kiểm tra role có khả năng bỏ qua RLS:

~~~sql
SELECT
    rolname,
    rolsuper,
    rolbypassrls
FROM pg_roles
WHERE rolname IN (
    'app_login',
    'app_reader',
    'app_editor'
)
ORDER BY rolname;
~~~

Có thể gọi row_security_active để xác định RLS có đang hoạt động cho quan hệ dưới ngữ cảnh role hiện tại hay không:

~~~sql
BEGIN;

SET LOCAL ROLE app_reader;

SELECT row_security_active('public.documents'::regclass);

ROLLBACK;
~~~

Khi kết quả không như mong đợi, hãy kiểm tra lần lượt: current_user, quyền USAGE của schema, quyền bảng/cột, membership, trạng thái RLS, policy theo command và role, sau đó mới kiểm tra biểu thức USING/WITH CHECK. Cách đi theo từng lớp giúp tìm nguyên nhân nhanh hơn việc thay policy ngay khi thấy truy vấn trả về 0 hàng.

## 8. Những đường thực thi cần kiểm thử thêm

### 8.1. Table owner, SUPERUSER và BYPASSRLS

Luôn có ít nhất một test xác nhận ứng dụng không vô tình kết nối bằng chủ sở hữu bảng hoặc role có BYPASSRLS. Nếu bảng không bật FORCE ROW LEVEL SECURITY, chủ sở hữu bảng có thể nhìn thấy toàn bộ hàng. SUPERUSER và BYPASSRLS có thể bỏ qua policy kể cả khi bảng bật FORCE.

Trong môi trường kiểm thử, hãy so sánh kết quả dưới role quản trị với kết quả dưới role ứng dụng để hiểu khác biệt. Không dùng kết quả từ role quản trị làm bằng chứng rằng policy ứng dụng hoạt động đúng.

### 8.2. View và function

View có thể thực thi truy cập bảng nền theo quyền của chủ sở hữu view. Trên các phiên bản PostgreSQL hỗ trợ tùy chọn security_invoker, view có thể được cấu hình để dùng quyền của người gọi. Vì vậy, nếu ứng dụng đọc dữ liệu qua view, cần kiểm thử trực tiếp view bằng role ứng dụng và kiểm tra hành vi của bảng nền.

Function có thuộc tính SECURITY DEFINER chạy với quyền của chủ sở hữu function. Nếu chủ sở hữu function là table owner hoặc role có BYPASSRLS, function có thể mở đường truy cập vượt qua kỳ vọng của policy. Chỉ dùng SECURITY DEFINER khi thật sự cần; giới hạn EXECUTE, đặt search_path an toàn và kiểm tra quyền của chủ sở hữu function. Test phải gọi function dưới role ứng dụng, không chỉ chạy câu SQL tương đương trực tiếp.

### 8.3. TRUNCATE và các quyền không được RLS bảo vệ

RLS áp dụng cho việc truy cập hàng, nhưng không thay thế mọi quyền trên bảng. TRUNCATE và REFERENCES không được bảo vệ bởi row policy theo cách SELECT/INSERT/UPDATE/DELETE được bảo vệ. Nếu role có quyền TRUNCATE, nó có thể làm rỗng bảng dù policy RLS chỉ cho phép nhìn thấy một tenant.

Do đó, hãy kiểm tra riêng quyền TRUNCATE và không cấp quyền này cho role ứng dụng thông thường. Tương tự, kiểm tra quyền REFERENCES, TRIGGER và EXECUTE khi hệ thống có dùng các khả năng đó.

### 8.4. Connection pool và trạng thái phiên

Nếu ứng dụng dùng connection pool, một kết nối vật lý có thể lần lượt phục vụ nhiều request. SET ROLE hoặc SET app.tenant_id ở cấp session có thể còn hiệu lực khi kết nối được tái sử dụng nếu ứng dụng không reset trạng thái đúng cách.

Ưu tiên transaction có phạm vi rõ ràng:

~~~sql
BEGIN;
SET LOCAL ROLE app_reader;

SELECT set_config(
    'app.tenant_id',
    '11111111-1111-4111-8111-111111111111',
    true
);

SELECT id, title
FROM public.documents;

COMMIT;
~~~

SET LOCAL ROLE và set_config với tham số is_local = true giới hạn trạng thái trong transaction. Kiểm thử hai request liên tiếp trên cùng connection: request thứ nhất dùng tenant A, request thứ hai dùng tenant B; xác nhận request thứ hai không nhìn thấy dữ liệu tenant A do sót context. Đồng thời kiểm tra đường lỗi và rollback, vì transaction thất bại cũng phải được pool xử lý và trả về trạng thái an toàn.

### 8.5. Biến tenant context

Ví dụ ở trên dùng app.tenant_id để minh họa, nhưng biến cấu hình tùy chỉnh không tự xác thực người dùng. Nếu role có thể gửi SQL tùy ý, họ có thể tự đặt biến sang tenant khác. Đây là vấn đề thiết kế danh tính, không thể giải quyết chỉ bằng việc viết thêm một policy so sánh UUID.

Trong ứng dụng nhiều tenant, backend phải xác thực người dùng rồi thiết lập context đáng tin cậy trong transaction. Nếu người dùng có quyền truy cập SQL trực tiếp, hãy cân nhắc ràng buộc tenant với danh tính database hoặc một cơ chế cấp context có kiểm soát mà người gọi không thể tự giả mạo. Test bảo mật cần có trường hợp thử thay tenant context và xác nhận người dùng không thể vượt ranh giới được cấp.

## 9. Ma trận kiểm thử đề xuất

Một bộ test cơ bản nên có các trường hợp sau. Điều chỉnh role và tên bảng theo thiết kế thực tế.

| Nhóm | Role / điều kiện | Thao tác | Kết quả mong đợi |
|---|---|---|---|
| Kết nối | Tài khoản hợp lệ | Kết nối database | Kết nối thành công |
| Kết nối | Tài khoản không hợp lệ hoặc không có CONNECT | Kết nối database | Bị từ chối |
| Schema | Role không có USAGE | Truy cập bảng qua schema | Bị từ chối |
| Table ACL | Reader | SELECT bảng được cấp quyền | Thành công |
| Table ACL | Reader | INSERT / UPDATE / DELETE không được cấp | Permission denied |
| RLS SELECT | Reader, tenant A | SELECT dữ liệu | Chỉ thấy tenant A |
| RLS INSERT | Editor, tenant A | INSERT tenant A | Thành công |
| RLS INSERT | Editor, tenant A | INSERT tenant B | Bị WITH CHECK từ chối |
| RLS UPDATE | Editor, tenant A | UPDATE hàng tenant A | Thành công nếu hàng mới hợp lệ |
| RLS UPDATE | Editor, tenant A | Chuyển hàng sang tenant B | Bị WITH CHECK từ chối |
| RLS DELETE | Editor, tenant A | DELETE hàng tenant B | 0 hàng bị xóa |
| Default deny | Role không có policy phù hợp | SELECT hoặc ghi hàng | Không được truy cập hàng |
| Bypass | Table owner / BYPASSRLS | SELECT dữ liệu | Xác nhận hành vi bypass đã dự kiến |
| Pool | Hai request khác tenant trên cùng connection | Đọc dữ liệu liên tiếp | Không rò context giữa request |
| View/function | Role ứng dụng | Truy cập qua view hoặc SECURITY DEFINER | Quyền vẫn đúng theo thiết kế |

Nên bổ sung test cho từng policy mới hoặc mỗi lần thay đổi GRANT/REVOKE. Khi có nhiều policy permissive/restrictive, tạo dữ liệu đại diện cho cả trường hợp thỏa và không thỏa từng biểu thức để phát hiện policy mới vô tình mở rộng quyền.

## 10. Tổ chức test tự động và dữ liệu kiểm thử

Một quy trình kiểm thử dễ lặp lại có thể chia thành các bước:

1. Tạo database hoặc schema kiểm thử cô lập; tạo role và membership theo cấu hình cần xác minh.
2. Tạo bảng, seed dữ liệu thuộc nhiều tenant và cấu hình GRANT/REVOKE.
3. Bật RLS, tạo policy và xác nhận policy trong pg_policies.
4. Chạy từng nhóm test trong transaction riêng bằng role ứng dụng.
5. Kiểm tra kết quả truy vấn, số hàng bị tác động, SQLSTATE và current_user.
6. ROLLBACK hoặc xóa fixture sau test; không để dữ liệu hay quyền thử nghiệm ảnh hưởng môi trường dùng chung.

Mỗi test nên có dữ liệu đủ phân biệt: ít nhất một hàng thuộc tenant hiện tại, một hàng thuộc tenant khác và một hàng có giá trị biên nếu policy có điều kiện trạng thái. Nếu chỉ seed một tenant, test có thể luôn xanh dù policy đang cho phép mọi tenant.

Đối với test tự động, tách rõ ba nhóm assertion:

- **Assertion quyền:** has_table_privilege, has_column_privilege, has_schema_privilege và kết quả thực thi câu lệnh.
- **Assertion RLS:** hàng nhìn thấy, hàng được phép ghi và hàng bị lọc.
- **Assertion từ chối:** SQLSTATE, thông báo phù hợp và số hàng bị tác động.

Chạy test dưới role gần với production nhất. Việc test bằng SUPERUSER có thể tạo kết quả sai lệch vì tài khoản này bỏ qua RLS. Nếu phải dùng tài khoản quản trị để chuẩn bị fixture, hãy chuyển sang role ứng dụng trước khi thực hiện assertion và xác minh current_user ở đầu mỗi test.

## 11. Lỗi thường gặp khi kiểm thử

- **Chỉ kiểm tra GRANT:** role có SELECT nhưng RLS vẫn có thể lọc hết hàng. Cần kiểm tra cả policy.
- **Dùng table owner để test:** owner có thể bypass RLS, khiến test đọc được mọi tenant và tạo cảm giác policy không hoạt động.
- **Quên quyền schema:** đã GRANT SELECT trên bảng nhưng role không có USAGE trên schema.
- **Chỉ kiểm tra USING:** role có thể sửa một hàng hợp lệ rồi chuyển tenant nếu WITH CHECK thiếu hoặc sai.
- **Cho rằng truy vấn không lỗi là truy cập thành công:** SELECT có thể trả 0 hàng; UPDATE/DELETE có thể tác động 0 hàng.
- **Cho rằng mọi lần từ chối đều do RLS:** permission denied có thể xuất phát từ quyền schema, bảng, cột hoặc function.
- **Cấp BYPASSRLS cho role ứng dụng:** policy không còn là hàng rào bảo vệ đối với role đó.
- **Không reset trạng thái connection:** SET ROLE hoặc tenant context còn sót khi pool tái sử dụng kết nối.
- **Tin tenant context từ client:** người dùng có thể tự chọn tenant nếu được phép đặt biến cấu hình tùy chỉnh.
- **Bỏ qua view và SECURITY DEFINER:** đường truy cập gián tiếp có thể chạy với quyền của chủ sở hữu đối tượng.

Khi một test thất bại, trước tiên ghi nhận role, current_user, session_user, SQLSTATE và số hàng bị tác động. Sau đó đối chiếu quyền đối tượng và policy áp dụng. Không sửa policy ngay khi chưa xác định lớp gây ra kết quả sai, vì thay đổi nhầm policy có thể mở rộng quyền truy cập dữ liệu.

Một bộ kiểm thử tốt chứng minh được từng role chỉ thực hiện đúng thao tác được cấp, chỉ nhìn thấy hàng thuộc phạm vi của mình, không thể ghi hoặc chuyển dữ liệu sang phạm vi khác và không để trạng thái phiên làm rò dữ liệu giữa các request.

