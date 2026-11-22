# Quyền hàm SECURITY DEFINER và bảo vệ điểm nâng quyền trong PostgreSQL

Một ứng dụng không được phép đọc trực tiếp bảng chứa số lượng tồn kho, giá vốn hay thông tin khách hàng. Tuy nhiên, ứng dụng vẫn cần gọi một hàm như `get_available_stock('KB-001')` để nhận **một thông tin được phép công bố**. PostgreSQL hỗ trợ xây API hạn chế như vậy bằng **`SECURITY DEFINER`**: hàm chạy các câu SQL bên trong với quyền của **chủ sở hữu hàm**, thay vì chỉ quyền của người gọi.

Điều này tạo ra một **điểm nâng quyền có chủ đích** (*privilege boundary*). Nếu viết an toàn, người gọi chỉ thực hiện được thao tác mà hàm cho phép. Nếu viết bất cẩn — như đọc tên bảng qua `search_path` không tin cậy, ghép dynamic SQL từ input, cho phép gọi hàm quá rộng hoặc sở hữu hàm bằng superuser — nó có thể trở thành đường thực thi những thao tác lẽ ra người gọi bị cấm.

~~~sql
-- Minh họa một function chạy bằng quyền owner.
-- Các role/schema/bảng sẽ được tạo đầy đủ trong lab:
CREATE FUNCTION sec389_api.get_available_stock(p_sku text)
RETURNS integer
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, sec389_private, pg_temp
AS $$
    SELECT available_units
    FROM sec389_private.inventory
    WHERE sku = p_sku
      AND is_public = true
$$;
~~~

**Từ khóa `SECURITY DEFINER` không tự động bảo đảm an toàn.** Cần đồng thời bảo vệ owner role, quyền `EXECUTE`, tên objects mà hàm sử dụng, input, quyền tạo objects trong schema, tính đúng của authorization và cách kiểm thử một người gọi có quyền thấp.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt `SECURITY INVOKER` (mặc định) và `SECURITY DEFINER`.
2. Giải thích `current_user`, `session_user` và tác động của `SET ROLE` trong bối cảnh hàm.
3. Xác định quyền cần có để gọi hàm và quyền nào được kiểm tra khi SQL bên trong hàm chạy.
4. Hiểu quyền `EXECUTE` thường được cấp cho `PUBLIC` theo mặc định đối với hàm mới.
5. Giới hạn khả năng gọi bằng `REVOKE ... FROM PUBLIC` và `GRANT EXECUTE` cho role thích hợp.
6. Chặn khoảng thời gian hàm mới tạo có thể bị gọi bằng cách tạo hàm và thay đổi grants **trong cùng transaction**.
7. Cấu hình `SET search_path = pg_catalog, trusted_schema, pg_temp` một cách có chủ đích.
8. Nhận diện nguy cơ **object shadowing**, fake function/operator, temporary-table hijacking và schema có quyền `CREATE` không tin cậy.
9. Dùng schema-qualified names, trusted search path và parameterized dynamic SQL.
10. Thiết kế một definer role **không LOGIN, không SUPERUSER, không BYPASSRLS**, chỉ có quyền tối thiểu cần thiết.
11. Tách owner dữ liệu khỏi owner hàm để tránh cấp quyền đọc/ghi quá rộng.
12. Kiểm soát quyền trên schema, bảng, cột và hàm theo nguyên tắc **least privilege**.
13. Hiểu khác biệt giữa `USAGE ON SCHEMA`, `EXECUTE ON FUNCTION` và `SELECT/UPDATE` trên bảng.
14. Kiểm tra RLS (*Row-Level Security*) và nguy cơ role owner/BYPASSRLS đi vòng chính sách.
15. Tránh nhầm `current_user` trong definer function với danh tính của người gọi.
16. Thiết kế API đọc giới hạn, API ghi có validation/authorization và audit phù hợp.
17. Viết function `SECURITY DEFINER` không lộ thông tin nhạy cảm qua lỗi, log hay output.
18. Chẩn đoán `permission denied`, `function does not exist`, lỗi `search_path` và sự cố sau migration.
19. Kiểm tra metadata qua `pg_proc`, `pg_namespace`, `pg_roles` và các grants.
20. Xây quy trình review, migration, kiểm thử quyền thấp và ứng phó khi phát hiện lỗ hổng definer.

## 2. Tại sao cần SECURITY DEFINER?

Hãy tưởng tượng bảng nội bộ:

~~~text
private.inventory
  sku
  available_units
  cost_price        <- không được lộ
  is_public
~~~

Một ứng dụng bán hàng cần biết `available_units` của những sản phẩm `is_public=true` để hiển thị tình trạng hàng. Nó **không cần** đọc giá vốn, xem tồn kho sản phẩm bí mật hoặc tự cập nhật số lượng.

Nếu cấp:

~~~sql
GRANT SELECT ON private.inventory TO app_role;
~~~

ứng dụng có thể đọc **tất cả cột/hàng** mà quyền/policies cho phép, vượt yêu cầu ban đầu. Thay vào đó, bạn có thể:

1. Giữ bảng trong schema riêng, không cho ứng dụng quyền truy cập trực tiếp.
2. Tạo hàm `get_available_stock(text)` chỉ trả một giá trị đã kiểm tra.
3. Cho một owner role riêng, hạn chế, có quyền đọc **những cột cần thiết**.
4. Định nghĩa hàm bằng `SECURITY DEFINER`.
5. Chỉ `GRANT EXECUTE` hàm đó cho role ứng dụng.

Khi gọi, người dùng có thể nhận kết quả từ hàm mà không được phép tự gửi `SELECT * FROM private.inventory`.

### 2.1. SECURITY DEFINER là một dạng API có đặc quyền

~~~text
Ứng dụng / role quyền thấp
       |
       | USAGE schema API + EXECUTE hàm cụ thể
       v
   SECURITY DEFINER function
       |
       | SQL bên trong chạy với quyền definer owner
       v
  Bảng hoặc nghiệp vụ nội bộ
       |
       v
  Kết quả đã giới hạn cho ứng dụng
~~~

**Hàm là điểm kiểm soát**, không phải toàn bộ bảng được “mở khóa” cho người dùng.

### 2.2. Khi nào không cần SECURITY DEFINER?

Nếu ứng dụng vốn đã có quyền đúng với bảng và tác vụ, hãy để function mặc định là `SECURITY INVOKER`. Mỗi điểm nâng quyền thêm một phần cần review, test, giám sát và bảo trì.

Một function tính toán thuần túy:

~~~sql
CREATE FUNCTION public.calculate_total(p_price numeric, p_qty integer)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_price * p_qty
$$;
~~~

không cần quyền đặc biệt để truy cập dữ liệu nội bộ; đặt `SECURITY DEFINER` sẽ tạo rủi ro mà không đem lại lợi ích.

### 2.3. Definer không phải quyền vô hạn

Hàm chỉ có các quyền mà **owner role** sở hữu hoặc được thừa hưởng theo role membership/policy. Nếu owner không có quyền `SELECT` bảng nội bộ, `SECURITY DEFINER` không tự sinh quyền ấy.

### 2.4. Điểm nâng quyền có thể hợp lệ

Một API có quyền hạn tối thiểu, được review và giới hạn input/output là mô hình hợp lý. Nguy hiểm không nằm ở việc tồn tại nâng quyền, mà ở việc **người gọi có thể điều khiển hàm thực thi công việc ngoài hợp đồng**.

## 3. SECURITY INVOKER và SECURITY DEFINER

PostgreSQL hỗ trợ hai chế độ thực thi:

| Thuộc tính | `SECURITY INVOKER` | `SECURITY DEFINER` |
| --- | --- | --- |
| Mặc định | **Có** | Không |
| SQL trong hàm dùng quyền ai? | Người gọi | Owner của hàm |
| Rủi ro vượt quyền nếu hàm bị khai thác | Thường giới hạn bởi quyền caller | Có thể vượt quyền caller tới quyền definer |
| Dùng cho | Hàm thường, có quyền theo caller | API được cấp đặc quyền rất hẹp |
| Có cần bảo vệ search_path/dynamic SQL? | Có | **Đặc biệt quan trọng** |
| Owner role | Chủ hàm | Chủ hàm đồng thời là identity thực thi đặc quyền |

### 3.1. Tạo hàm invoker

~~~sql
CREATE FUNCTION public.try_read_count()
RETURNS bigint
LANGUAGE sql
SECURITY INVOKER
AS $$
    SELECT COUNT(*) FROM sensitive_schema.hidden_table
$$;
~~~

Đây là **ví dụ định hướng**: schema/table chưa được tạo. Nếu caller không có quyền cần thiết, gọi function sẽ thất bại theo cơ chế privilege checking của SQL nội bộ.

### 3.2. Tạo hàm definer

~~~sql
CREATE FUNCTION public.try_read_count_privileged()
RETURNS bigint
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, sensitive_schema, pg_temp
AS $$
    SELECT COUNT(*) FROM sensitive_schema.hidden_table
$$;
~~~

Nếu owner có quyền đọc bảng, và caller được phép gọi hàm, truy vấn có thể thành công ngay cả khi caller không có quyền `SELECT` trực tiếp.

### 3.3. Bảng phân biệt quan trọng

| Quyền/thuộc tính | Kiểm tra khi nào? |
| --- | --- |
| `USAGE` trên schema chứa function | Cần để caller resolve/gọi hàm theo tên |
| `EXECUTE` trên function | Cần để caller gọi hàm |
| `SELECT/INSERT/UPDATE/DELETE` trên bảng bên trong | Trong SECURITY DEFINER, kiểm tra theo quyền definer owner |
| Role membership và quyền của owner | Ảnh hưởng quyền thực thi thực tế bên trong |
| RLS policies | Phụ thuộc effective role, table owner/BYPASSRLS và policy |
| Quyền schema/tên object ở runtime | Phụ thuộc statement, name resolution và owner |

Chỉ `GRANT EXECUTE` không có nghĩa người gọi được cấp `SELECT` trên bảng. Ngược lại, dù user không được SELECT trực tiếp, nếu function trả toàn bộ dữ liệu nhạy cảm, **function vẫn làm lộ dữ liệu qua output**.

### 3.4. Tên đầy đủ và hàm overloaded

PostgreSQL hỗ trợ function overloading:

~~~sql
get_stock(text)
get_stock(integer)
~~~

`GRANT EXECUTE ON FUNCTION` cần chọn đúng signature, ví dụ `get_stock(text)`. Nếu cùng tên nhiều overloads, không được giả định revoke/grant cho một signature sẽ áp dụng cho tất cả.

## 4. CURRENT_USER, SESSION_USER và SET ROLE

Ba khái niệm liên quan nhưng không đồng nhất:

- `session_user`: identity gốc của session theo cơ chế PostgreSQL (thường role login), có thể được thay đổi bằng những thao tác được phép.
- `current_user`: role hiện tại để kiểm tra quyền SQL; có thể thay đổi bởi `SET ROLE` hoặc khi đang thực thi `SECURITY DEFINER` function.
- `current_role`: trong PostgreSQL thường tương đương với `current_user`.

### 4.1. Xem identity hiện tại

~~~sql
SELECT
    session_user,
    current_user,
    current_role;
~~~

Nếu chưa `SET ROLE` và không ở definer function, những giá trị này thường cùng là login role.

### 4.2. SET ROLE

~~~sql
-- Chỉ khi role hiện tại được phép SET ROLE:
SET ROLE some_allowed_role;
SELECT session_user, current_user;
RESET ROLE;
~~~

`SET ROLE` có điều kiện về membership/authorization; không được phép tự chọn bất kỳ role nào mình muốn. Nó thay đổi effective role của các SQL statements ngoài definer function.

### 4.3. Bên trong SECURITY DEFINER

~~~sql
CREATE FUNCTION public.inspect_execution_identity()
RETURNS TABLE (
    session_identity name,
    effective_identity name
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT session_user, current_user
$$;
~~~

Khi role quyền thấp gọi hàm (nếu được `EXECUTE`), `current_user` bên trong là **owner của function**, còn `session_user` phản ánh session identity.

### 4.4. Bẫy phân quyền theo current_user

Ví dụ thiết kế **sai mục đích**:

~~~sql
-- Inside SECURITY DEFINER:
-- WHERE resource_owner = current_user
~~~

Nếu ý định là chỉ đọc dữ liệu của caller, biểu thức này có thể lọc theo **definer owner**, không phải caller. Nó dễ dẫn đến kết quả sai hoặc lộ tài nguyên.

### 4.5. SESSION_USER cũng không phải mọi danh tính ứng dụng

Trong ứng dụng dùng connection pool, hàng nghìn người dùng HTTP có thể cùng đăng nhập database bằng **một service role**. Khi đó `session_user` chỉ là service role, không phải user_id đang đăng nhập vào website. Không dùng `session_user` làm authorization người dùng cuối nếu kiến trúc DB connection không ánh xạ 1:1 tới danh tính ấy.

### 4.6. Custom GUC không mặc nhiên đáng tin

Một số framework truyền `user_id` qua `current_setting('app.user_id')`. Nếu caller có thể thực thi SQL tùy ý và thay đổi custom GUC đó, họ có thể giả mạo danh tính. Trước khi dùng vào SECURITY DEFINER authorization, phải xác định **ai có quyền đặt giá trị**, tính đáng tin của tầng middleware và cách chống injection/escalation.

### 4.7. Hướng an toàn

Thiết kế authorization dựa trên một identity nguồn được xác minh (DB role thực sự của caller, service đã chứng thực, token đã xác minh bởi thành phần đáng tin, hoặc policy được database bảo vệ). Không lấy một chuỗi từ input rồi coi đó là bằng chứng caller được phép đọc/ghi dữ liệu.

## 5. Quyền EXECUTE mặc định: mối nguy thường bị bỏ qua

Theo mặc định PostgreSQL thường cấp **`EXECUTE` trên functions cho role `PUBLIC`** khi hàm mới được tạo. `PUBLIC` là nhóm khái niệm bao gồm mọi roles, không phải schema `public`.

### 5.1. Hai chữ PUBLIC khác nhau

| Khái niệm | Ý nghĩa |
| --- | --- |
| Role `PUBLIC` trong `GRANT/REVOKE` | Tất cả roles |
| Schema `public` | Một schema thực trong database |

`REVOKE EXECUTE ON FUNCTION ... FROM PUBLIC` là thu hồi quyền gọi hàm mặc định khỏi **mọi roles** theo cơ chế ACL, không xóa schema public.

### 5.2. Không để cửa sổ thực thi không mong muốn

Mẫu rủi ro:

~~~sql
CREATE FUNCTION sensitive_api.do_privileged_work(...)
RETURNS ...
LANGUAGE plpgsql
SECURITY DEFINER
AS $$ ... $$;

-- Một lúc sau mới:
REVOKE ALL ON FUNCTION sensitive_api.do_privileged_work(...) FROM PUBLIC;
~~~

Giữa hai statements đã commit riêng, function có thể đã có quyền mặc định rộng hơn dự định (tùy quyền schema, database và các role grants).

### 5.3. Tạo và thu hồi trong cùng transaction

~~~sql
BEGIN;

CREATE FUNCTION sensitive_api.read_limited_data(p_id bigint)
RETURNS bigint
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, trusted_private, pg_temp
AS $$
    SELECT id
    FROM trusted_private.records
    WHERE id = p_id
$$;

REVOKE ALL ON FUNCTION
    sensitive_api.read_limited_data(bigint)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
    sensitive_api.read_limited_data(bigint)
TO designated_app_role;

COMMIT;
~~~

Đây là **mẫu cú pháp triển khai**; các schema/roles/tables minh họa chưa được tạo trong ví dụ này. DDL và quyền cùng một transaction giúp không công khai hàm ở trạng thái quyền mặc định giữa các commits.

### 5.4. EXECUTE không thay USAGE schema

Để gọi `sensitive_api.read_limited_data(...)` theo tên, caller còn cần quyền `USAGE` trên schema `sensitive_api`. Nhưng từ chối `USAGE` schema **không nên là biện pháp duy nhất**, vì ACL trên function có thể vẫn quá rộng, và một lần GRANT USAGE về sau sẽ vô tình mở các functions khác.

### 5.5. GRANT EXECUTE chỉ cho đúng signature

~~~sql
GRANT EXECUTE ON FUNCTION
    sensitive_api.read_limited_data(bigint)
TO designated_app_role;
~~~

Không dùng `GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA ... TO PUBLIC` khi schema chứa hàm nâng quyền mà không có lý do được review đầy đủ.

### 5.6. ALTER DEFAULT PRIVILEGES

Với một role chuyên triển khai functions nhạy cảm, có thể thiết lập:

~~~sql
-- Được DBA/owner thực hiện cho role sẽ CREATE FUNCTION:
ALTER DEFAULT PRIVILEGES FOR ROLE designated_function_owner
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
~~~

Điều này thay đổi **default privileges của những functions tạo trong tương lai bởi role đó**, không tự thu hồi quyền những functions đã tồn tại.

Phải phân biệt **global default privileges** với default privileges theo schema: một `REVOKE` chỉ áp dụng ở per-schema layer không nhất thiết loại được grant mặc định từ global layer. Kiểm tra mô hình default ACL thực tế và role **tạo** function, đặc biệt nếu deployment dùng `SET ROLE`.

### 5.7. Function vs procedure

`SECURITY DEFINER` còn được hỗ trợ trên procedures, nhưng **procedure khai báo `SECURITY DEFINER` không được thực thi transaction-control statements (`COMMIT`/`ROLLBACK`) nội bộ** theo quy định của PostgreSQL. Không dùng definer procedure như cách vượt hạn chế transaction ownership của caller.

## 6. Threat model: caller có thể kiểm soát điều gì?

Trước khi dùng SECURITY DEFINER, hãy viết rõ **điểm mà caller có quyền điều khiển**.

| Đầu vào / bề mặt | Nguy cơ |
| --- | --- |
| Tham số `text`, `jsonb`, `uuid` | Injection nếu ghép SQL, logic authorization bị điều khiển |
| `search_path` của session | Tên object không qualified có thể resolve tới object không tin cậy nếu function không cố định search_path |
| Temporary tables | Có thể che khuất bảng có tên không qualified, nếu không đặt `pg_temp` an toàn |
| Schema có quyền `CREATE` cho untrusted roles | Object/function/operator giả mạo được đưa vào name resolution |
| Cách function xử lý tên schema/table/column | Dynamic SQL identifier injection |
| Owner role | Nếu quá mạnh (SUPERUSER/BYPASSRLS/owner của mọi bảng) thì thiệt hại khi bị khai thác lớn |
| Quyền `EXECUTE`/`USAGE` | Function bị gọi ngoài nhóm được phép |
| Function overloads hoặc default arguments | Chọn nhầm function hoặc mở một đường gọi khác |
| Kết quả/exception/log | Lộ dữ liệu bí mật hoặc thông tin tồn tại của rows |
| SECURITY DEFINER helper functions | Có thể tạo chuỗi nâng quyền ngoài ý định |
| RLS/table ownership | Có thể bypass policy khi thực thi với quyền owner |
| Trigger/view/foreign data wrappers | SQL gián tiếp gây side effects hoặc truy cập ngoài phạm vi dự kiến |

### 6.1. Đối tượng cần bảo vệ

**Không chỉ dữ liệu bí mật**, mà còn trạng thái giao dịch, locks, tài nguyên CPU, log và các bảng phụ trợ. Một function chỉ trả một integer vẫn có thể là rủi ro nếu caller được phép chạy UPDATE vô hạn, tạo lock hàng nghìn rows hoặc quan sát timing để suy ra dữ liệu.

### 6.2. Bề mặt mà PostgreSQL không thể đoán thay bạn

Database không tự hiểu người dùng nào đang đặt mua hàng, tài nguyên nào thuộc tenant nào hay hạn mức mỗi khách hàng. Function phải kiểm tra những điều kiện nghiệp vụ ấy hoặc gọi một cơ chế authorization đáng tin. `SECURITY DEFINER` chỉ đổi **role thực thi SQL**, không tạo tự động một policy ứng dụng.

## 7. search_path: bề mặt nguy hiểm nhất của SECURITY DEFINER

`search_path` là danh sách schemas mà PostgreSQL sử dụng để phân giải **tên object không có schema prefix**. Ví dụ:

~~~sql
SELECT available_units FROM inventory;
~~~

Tên `inventory` chưa nói rõ thuộc schema nào. PostgreSQL sẽ dùng quy tắc tra cứu schema trong `search_path`. Trong function chạy bằng quyền thấp, tên sai có thể gây lỗi. Trong **SECURITY DEFINER**, tên sai có thể khiến SQL được phân giải tới object kẻ tấn công kiểm soát nhưng lại thực thi trong một bối cảnh có quyền cao hơn.

### 7.1. Bản chất lỗi object shadowing

~~~text
SECURITY DEFINER function với SQL:
    SELECT value FROM inventory;
                  (không schema-qualified)
         |
         +-- search_path chứa schema không tin cậy
         |
         +-- một relation khác cũng tên "inventory"
         |
         +-- tên được resolve vào object ngoài ý định
~~~

Đây là một trường hợp **name-resolution hijacking**. Nếu function tiếp tục dùng dữ liệu từ object giả để quyết định tác vụ đặc quyền, hậu quả có thể nghiêm trọng.

### 7.2. Schema có quyền CREATE là schema có thể bị thao túng

Một schema không đáng tin nếu role không đáng tin có thể `CREATE` hoặc thay thế objects trong đó. Đưa một schema như vậy vào `search_path` của SECURITY DEFINER function đồng nghĩa để bên ngoài tác động tới tên object mà hàm resolve.

Các mục cần review:

- Schema `public` hoặc schema dùng chung;
- Schema do ứng dụng cho khách hàng tự tạo objects;
- Extension schema do nhiều role có quyền write;
- Temporary schema của session;
- Bất kỳ schema nào có `CREATE` bị cấp quá rộng.

### 7.3. Phân biệt USAGE và CREATE trên schema

| Quyền | Ý nghĩa |
| --- | --- |
| `USAGE ON SCHEMA` | Tra cứu/resolve objects trong schema, tùy quyền trên object |
| `CREATE ON SCHEMA` | Tạo objects trong schema |
| `SELECT ON TABLE` | Đọc dữ liệu bảng theo cột/policy |
| `EXECUTE ON FUNCTION` | Gọi function cụ thể |

**Không cấp CREATE trên schema mà privileged code tin cậy** cho roles không đáng tin. Chỉ cấp USAGE nếu họ cần gọi những functions đã review.

### 7.4. PostgreSQL 15 và schema public

Các phiên bản/cơ sở dữ liệu đã nâng cấp có thể khác nhau về **quyền CREATE mặc định trong schema `public`**. PostgreSQL 15 thay đổi các mặc định liên quan tới schema public ở database mới; môi trường được nâng cấp từ version cũ có thể giữ ACL lịch sử. **Luôn kiểm tra thực tế**, không suy ra "public chắc chắn an toàn" từ major version.

### 7.5. Biểu thức SET search_path an toàn

Một pattern thường được tài liệu PostgreSQL khuyến nghị:

~~~sql
SECURITY DEFINER
SET search_path = trusted_schema, pg_temp
~~~

Ở đây:

- `trusted_schema` chỉ chứa objects do các roles đáng tin kiểm soát.
- `pg_temp` được liệt kê **cuối** để không cho bảng tạm lấn át những bảng được tin cậy.
- `pg_catalog` được tra cứu theo quy tắc đặc biệt; có thể ghi **rõ ở đầu** để dễ review.

Mẫu chủ động hơn cho bài:

~~~sql
SECURITY DEFINER
SET search_path = pg_catalog, sec389_private, pg_temp
~~~

### 7.6. Vì sao phải nêu pg_temp dù không dùng temp table?

Nếu temporary schema của session tồn tại mà **không được ghi rõ** trong `search_path`, PostgreSQL có những quy tắc ưu tiên đặc biệt: temporary schema có thể được tra **trước** các schemas khác khi phân giải **relation và data type names**.

Việc liệt kê `pg_temp` ở **cuối** giúp điều chỉnh thứ tự tìm tên bảng và kiểu dữ liệu, ngăn temporary relation cùng tên che khuất relation tin cậy trước nó.

### 7.7. pg_temp không phải namespace tìm hàm/toán tử theo cùng cách

Temporary schema có vai trò đặc biệt chủ yếu khi tìm relation/type names; PostgreSQL không dùng temporary schema theo cùng quy tắc để tìm **function/operator names**. Tuy nhiên, function/operator hijacking vẫn là rủi ro từ **các schemas khác có quyền CREATE** nằm trong search path.

### 7.8. Bảo vệ pg_catalog

`pg_catalog` chứa các functions, operators và objects hệ thống. PostgreSQL thường tra `pg_catalog` ngầm trước các schema khác nếu không liệt kê nó trong `search_path`. Nhưng nếu bạn ghi `pg_catalog` ở vị trí không phù hợp, bạn có thể khiến tên builtin bị shadow bởi object ở schema đứng trước.

Mẫu minh bạch:

~~~sql
SET search_path = pg_catalog, sec389_private, pg_temp
~~~

Không chủ động đặt một schema untrusted **trước pg_catalog** trong SECURITY DEFINER function.

### 7.9. Schema-qualified names là một lớp phòng thủ bổ sung

~~~sql
-- Không rõ bảng từ schema nào:
SELECT available_units FROM inventory;

-- Đã xác định relation:
SELECT available_units FROM sec389_private.inventory;
~~~

Ngay cả khi đã cố định `search_path`, việc **schema-qualify tables/functions quan trọng** giúp đọc code và review dễ hơn. Tuy nhiên, tên qualified không giải quyết được SQL injection, quyền owner quá rộng hoặc authorization logic sai.

### 7.10. Rủi ro từ functions, operators, casts và overload resolution

Không chỉ tables có thể gây nhầm:

~~~sql
SELECT transform_input(p_text);
~~~

Nếu `transform_input` resolve qua schema do người khác tạo objects, lời gọi có thể đi vào implementation không mong muốn. Operators và function overload/default arguments cũng có logic name resolution. Bảo vệ bằng **trusted search path, đối số có kiểu rõ và qualified function/operator khi cần**, không chỉ bằng việc quote giá trị input.

### 7.11. Không trộn schema có quyền CREATE của client vào search_path

Một function chỉ làm `SELECT` cũng có thể nguy hiểm nếu một object/function được resolve thành code do role khác kiểm soát trong lúc function đang có quyền definer. Tránh để caller tự chọn schema search path hoặc object names từ tham số khi không cần.

## 8. Lab phân quyền theo ba vai trò tách biệt

Ta tạo ví dụ **chỉ để học** về một kho sản phẩm. Ba roles có quyền khác nhau:

| Role | Nhiệm vụ | Quyền dự định |
| --- | --- | --- |
| `sec389_data_owner` | Chủ bảng dữ liệu nội bộ | Sở hữu private schema/table |
| `sec389_fn_owner` | Chủ API SECURITY DEFINER | Chỉ được đọc những cột cần thiết |
| `sec389_app` | Role gọi API | Chỉ có `USAGE` trên API schema và `EXECUTE` một hàm |

Ba roles này đều được tạo **NOLOGIN** trong lab để minh họa identity/role membership. Trên ứng dụng thật, role login của service có thể được phép kế thừa `sec389_app`, nhưng không nên được phép trở thành `sec389_fn_owner` hoặc `sec389_data_owner`.

**Điều kiện môi trường:** cần DBA hoặc role có đủ quyền `CREATEROLE`/quyền tạo schema/`SET ROLE` để chạy toàn bộ provisioning. Nếu là học viên chỉ có quyền trong một database lab bình thường, không nên cố chạy `CREATE ROLE`; hãy dùng phần SQL như thiết kế tham khảo và đề nghị DBA tạo roles an toàn. Không chạy trên production không có change approval.

### 8.1. DBA tạo roles

~~~sql
-- Chạy với quyền quản trị phù hợp trong database lab.
CREATE ROLE sec389_data_owner NOLOGIN;
CREATE ROLE sec389_fn_owner NOLOGIN;
CREATE ROLE sec389_app NOLOGIN;
~~~

Không dùng `SUPERUSER`, `BYPASSRLS` hoặc `CREATEROLE` cho definer owner. Tài khoản deployment có khả năng `SET ROLE` thành owner chỉ nên được cấp cho quy trình triển khai đáng tin và được kiểm soát; nó không phải quyền dành cho ứng dụng runtime.

### 8.2. Tạo private và API schemas

~~~sql
-- DBA chạy trong database lab:
CREATE SCHEMA sec389_private AUTHORIZATION sec389_data_owner;
CREATE SCHEMA sec389_api AUTHORIZATION sec389_fn_owner;

REVOKE ALL ON SCHEMA sec389_private FROM PUBLIC;
REVOKE ALL ON SCHEMA sec389_api FROM PUBLIC;

GRANT USAGE ON SCHEMA sec389_api TO sec389_app;
~~~

Ứng dụng có thể resolve function ở `sec389_api` nhưng **không được USAGE schema `sec389_private`**. Bản thân `USAGE` trên API schema không cấp quyền EXECUTE tất cả functions ở đó: phải kiểm tra function ACL riêng, đặc biệt default PUBLIC EXECUTE.

### 8.3. Data owner tạo bảng nội bộ

~~~sql
-- Mở session deployment có quyền chuyển sang owner.
SET ROLE sec389_data_owner;

CREATE TABLE sec389_private.inventory (
    sku text PRIMARY KEY,
    available_units integer NOT NULL
        CHECK (available_units >= 0),
    cost_price numeric(12,2) NOT NULL
        CHECK (cost_price >= 0),
    is_public boolean NOT NULL DEFAULT false
);

INSERT INTO sec389_private.inventory(
    sku, available_units, cost_price, is_public
)
VALUES
    ('KB-001', 17, 350000, true),
    ('MS-002', 0, 120000, true),
    ('INTERNAL-001', 200, 98000, false);

RESET ROLE;
~~~

Nếu lệnh `SET ROLE` không được phép, dừng phần provisioning và xử lý đúng role membership/deployment privilege; **không** thay bằng `GRANT SUPERUSER` hoặc trao owner role cho account runtime.

### 8.4. Cấp quyền **chỉ theo cột** cho function owner

~~~sql
-- DBA hoặc data owner có quyền phù hợp:
GRANT USAGE ON SCHEMA sec389_private
TO sec389_fn_owner;

GRANT SELECT (sku, available_units, is_public)
ON TABLE sec389_private.inventory
TO sec389_fn_owner;
~~~

`sec389_fn_owner` không được `SELECT` cột `cost_price` theo quyền được cấp ở đây, cũng không có `INSERT/UPDATE/DELETE` trên bảng.

**Lưu ý:** quyền role thực tế có thể đến từ role memberships/grants khác. Một lab sạch với ba roles mới giúp quan sát, còn production phải kiểm tra mọi quyền **kế thừa** của definer owner, không chỉ những lệnh GRANT viết ở đoạn này.

### 8.5. Function owner tạo API, REVOKE và GRANT cùng transaction

~~~sql
-- Deployment identity đã được phép SET ROLE sec389_fn_owner.
SET ROLE sec389_fn_owner;

BEGIN;

CREATE FUNCTION sec389_api.get_available_stock(p_sku text)
RETURNS integer
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, sec389_private, pg_temp
AS $$
    SELECT i.available_units
    FROM sec389_private.inventory AS i
    WHERE i.sku = p_sku
      AND i.is_public = true
$$;

REVOKE ALL ON FUNCTION
    sec389_api.get_available_stock(text)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
    sec389_api.get_available_stock(text)
TO sec389_app;

COMMIT;

RESET ROLE;
~~~

Nếu chưa có quyền chuyển role, DBA nên chuẩn bị một quy trình deployment được phép; các ví dụ trên không tự cấp membership cho bất kỳ người dùng runtime nào.

### 8.6. Vì sao owner của function khác owner của table?

Nếu `sec389_fn_owner` sở hữu chính bảng và có toàn quyền, khi function chứa lỗ hổng, kẻ tấn công có thể khai thác **toàn bộ quyền owner**. Tách owner giúp giảm phạm vi thiệt hại:

~~~text
sec389_app
  |
  +-- EXECUTE get_available_stock(text)
         |
         +-- SECURITY DEFINER -> sec389_fn_owner
                |
                +-- USAGE sec389_private
                +-- SELECT sku, available_units, is_public
                X  Không SELECT cost_price
                X  Không UPDATE/DELETE inventory
~~~

Đây là thiết kế **defense in depth**: ngay cả khi hàm bị điều khiển chạy một SQL khác ngoài ý định, owner role vẫn không có toàn bộ quyền bảng, với điều kiện không có các grants/role memberships khác mở rộng quyền.

### 8.7. Thử gọi bằng role ứng dụng

~~~sql
-- Chỉ trên session lab được phép SET ROLE sec389_app:
SET ROLE sec389_app;

SELECT sec389_api.get_available_stock('KB-001')
    AS available_units;

SELECT sec389_api.get_available_stock('MS-002')
    AS available_units;

SELECT sec389_api.get_available_stock('INTERNAL-001')
    AS available_units;

RESET ROLE;
~~~

Kỳ vọng: lần lượt **17**, **0** và **SQL NULL**. Hàng `INTERNAL-001` có thật nhưng `is_public=false` nên hàm không công bố số lượng, như một SKU không tồn tại.

### 8.8. Thử truy cập bảng trực tiếp với quyền app

~~~sql
-- Chạy riêng để quan sát lỗi trong lab, sau đó RESET ROLE:
SET ROLE sec389_app;

SELECT * FROM sec389_private.inventory;
-- Dự kiến bị từ chối quyền schema/table.

RESET ROLE;
~~~

Đây là **kiểm tra phân quyền**, không phải truy vấn hợp lệ mà ứng dụng nên cố thực hiện. Trong một explicit transaction, statement bị lỗi có thể khiến transaction vào trạng thái aborted; khi đó phải `ROLLBACK` trước khi chạy thêm commands.

### 8.9. Những điều lab chứng minh

- App được phép **gọi một function xác định**.
- App không được trao quyền đọc bảng nội bộ.
- Function trả **chỉ một thuộc tính** và chỉ khi row được phép công bố.
- Function owner không có quyền SELECT cột giá vốn.
- Owner role, schema và function ACL tách thành các lớp kiểm soát.
- Các thay đổi permission không dựa vào việc client "ngoan ngoãn không SELECT bảng".

### 8.10. Những điều lab chưa tự chứng minh

Ví dụ trên **không** tự bảo đảm:

- Phân quyền theo từng người dùng HTTP/tenant;
- Chống lạm dụng gọi API hàng triệu lần;
- Chống suy luận thông tin từ timing/error;
- Bảo vệ nếu một role khác có quyền rộng qua membership;
- Chống việc deployment account thay function ngoài kiểm soát;
- RLS cho nhiều tenants hoặc row ownership;
- Audit chống sửa/xóa và compliance retention.

Đây là các trách nhiệm của kiến trúc và vận hành, sẽ được bàn sâu ở các phần tiếp theo.

## 9. Sai lầm điển hình: hàm đọc bảng không schema-qualified

### 9.1. Mẫu dễ bị ảnh hưởng bởi search_path

~~~sql
-- Không nên dùng làm SECURITY DEFINER function:
CREATE FUNCTION sec389_api.unsafe_stock_lookup(p_sku text)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_stock integer;
BEGIN
    SELECT available_units INTO v_stock
    FROM inventory
    WHERE sku = p_sku;

    RETURN v_stock;
END;
$$;
~~~

Function trên **không cố định search_path**, còn `inventory` không có schema prefix. Nếu caller kiểm soát `search_path` hoặc temporary relations, function có thể resolve tên khác dự định.

### 9.2. Đường tấn công ở mức khái niệm

~~~text
Caller tạo object trùng tên trong namespace mà họ kiểm soát
       |
Caller thay search_path / dùng temporary relation
       |
CALL security-definer function
       |
Function không qualified tên "inventory"
       |
Name resolution có thể chọn object của caller
       |
Logic đặc quyền đọc/xử lý dữ liệu sai nguồn
~~~

Trong một số dạng function, việc thay relation name có thể chỉ làm sai kết quả; trong những dạng khác, nó có thể dẫn tới SQL/logic tiếp theo với quyền owner. **Không chờ có dữ liệu bị lộ mới coi việc thiếu search_path bảo vệ là lỗ hổng.**

### 9.3. Sửa thành version có giới hạn

~~~sql
CREATE FUNCTION sec389_api.safe_stock_lookup(p_sku text)
RETURNS integer
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, sec389_private, pg_temp
AS $$
DECLARE
    v_stock integer;
BEGIN
    SELECT i.available_units INTO v_stock
    FROM sec389_private.inventory AS i
    WHERE i.sku = p_sku
      AND i.is_public = true;

    RETURN v_stock;
END;
$$;
~~~

**Lưu ý triển khai:** nếu thật sự tạo hàm mới này, phải `REVOKE EXECUTE FROM PUBLIC` và grant role thích hợp **trong cùng transaction** giống lab, không tạo và để mặc quyền mặc định rộng.

### 9.4. Đừng hiểu "schema qualified" là đủ mọi thứ

Sau khi viết `sec389_private.inventory`, vẫn phải review:

- Chủ hàm có quá nhiều quyền không?
- Hàm có dùng `EXECUTE` dynamic SQL?
- Có helper function khác không qualified?
- Có đọc dữ liệu của mọi tenant không?
- Kết quả/exception có lộ giá vốn không?
- Có quyền `EXECUTE` mặc định cho PUBLIC không?
- Có schema hay extension object khác từ source không đáng tin không?

Một fix chỉ một dòng có thể giảm một lớp rủi ro, nhưng chưa phải security review hoàn chỉnh.

## 10. SQL injection trong SECURITY DEFINER: hai lỗi khác nhau

Một privileged function có thể nhận tham số từ caller:

~~~sql
SELECT sec389_api.get_available_stock($1);
~~~

Truyền tham số bằng prepared statement giúp tránh một lớp SQL injection ở caller. Nhưng nếu **bên trong function** lại ghép tham số thành câu SQL rồi chạy bằng `EXECUTE`, nguy cơ injection có thể xuất hiện trở lại ngay trong ngữ cảnh definer.

### 10.1. Mẫu sai: ghép giá trị vào query string

~~~sql
-- Không triển khai mẫu này:
--
-- EXECUTE
--     'SELECT available_units FROM sec389_private.inventory
--      WHERE sku = ''' || p_sku || '''';
~~~

Khi `p_sku` chứa ký tự quote hoặc cấu trúc SQL đặc biệt, chuỗi SQL được tạo có thể khác mục tiêu. Trong SECURITY DEFINER function, query bị điều khiển còn có thể thực thi với **quyền owner role**, nên tác động thường nghiêm trọng hơn một query invoker thông thường.

### 10.2. Mẫu đúng: query tĩnh có tham số

Nếu bảng/cột là cố định, **đừng dùng dynamic SQL**:

~~~sql
SELECT i.available_units INTO v_stock
FROM sec389_private.inventory AS i
WHERE i.sku = p_sku
  AND i.is_public = true;
~~~

PL/pgSQL truyền giá trị `p_sku` như một biến có kiểu, không cần nối text SQL.

### 10.3. Mẫu đúng khi thật sự cần dynamic SQL

~~~sql
-- Bên trong PL/pgSQL function:
EXECUTE
    'SELECT available_units
     FROM sec389_private.inventory
     WHERE sku = $1
       AND is_public = true'
INTO v_stock
USING p_sku;
~~~

`USING p_sku` truyền **giá trị**, không ghép literal SQL. `$1` trong dynamic statement do PL/pgSQL `EXECUTE ... USING` cung cấp, không phải string replacement thủ công.

### 10.4. Identifier không thể bind như giá trị

Một table name hoặc column name **không thể thay bằng `$1`** trong vị trí identifier của câu SQL. Nếu cần chọn một relation động, dùng:

~~~sql
-- Mẫu khái niệm, p_table đã được kiểm tra allowlist:
EXECUTE format(
    'SELECT available_units FROM %I.%I
     WHERE sku = $1 AND is_public = true',
    'sec389_private',
    p_table
)
INTO v_stock
USING p_sku;
~~~

`%I` là identifier-quoting trong `format`. Nó ngăn chuỗi trở thành cú pháp SQL ngoài vị trí identifier, nhưng **không phải authorization**: vẫn phải kiểm tra `p_table` có nằm trong **allowlist các bảng được phép đọc** hay không.

### 10.5. Vì sao quote identifier chưa đủ?

Nếu caller được chọn bất kỳ table trong schema có quyền owner truy cập, một table name được quote an toàn về syntax vẫn có thể trỏ tới bảng nội bộ **không được phép công bố**. Cần **allowlist và kiểm tra quyền nghiệp vụ**, không chỉ chống SQL injection.

### 10.6. Dùng format %L và USING

`format('%L', p_value)` có thể quote SQL literal, nhưng với giá trị dữ liệu thông thường trong PL/pgSQL dynamic SQL, `EXECUTE ... USING` thuận tiện hơn và giữ kiểu dữ liệu tốt hơn. Không trộn identifiers/values vào một chuỗi không có phân biệt.

### 10.7. Đừng để user tự chọn schema hoặc function name

Một API nhận `target_function text` rồi thực thi nó bằng quyền definer dễ trở thành **arbitrary privileged operation dispatcher**. Nếu chỉ có ba thao tác được phép, hãy biểu diễn chúng bằng ba nhánh được kiểm soát hoặc ba functions có grants riêng.

## 11. Tách quyền theo chức năng, không theo sự tiện lợi của owner

Một anti-pattern phổ biến:

~~~text
security_definer_owner
  ├── SUPERUSER
  ├── BYPASSRLS
  ├── owner mọi bảng
  ├── có thể tạo extension, schemas, roles
  └── tạo mọi privileged function
~~~

Nếu một function có lỗi, nó có thể trở thành điểm khai thác gần như mọi dữ liệu. Tách owner và quyền giúp **giới hạn blast radius**.

### 11.1. Những quyền nên tránh trên function owner

- `SUPERUSER`;
- `BYPASSRLS`, trừ khi có yêu cầu đặc biệt được review;
- `CREATEROLE`, `CREATEDB`, `REPLICATION` hoặc quyền hạ tầng không cần thiết;
- Membership vào nhóm admin rộng;
- Quyền `CREATE` trên schemas không cần dùng;
- Quyền đọc cột nhạy cảm ngoài output contract;
- Quyền UPDATE/DELETE nếu function chỉ cần SELECT.

### 11.2. Đọc role attributes

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolcreaterole,
    rolcreatedb,
    rolreplication,
    rolbypassrls,
    rolinherit
FROM pg_catalog.pg_roles
WHERE rolname IN (
    'sec389_data_owner',
    'sec389_fn_owner',
    'sec389_app'
)
ORDER BY rolname;
~~~

Hàm trả về các metadata role mà session được phép xem. `rolinherit` và grants/membership cần được xem cùng nhau; một owner tưởng "không có quyền" có thể **kế thừa** quyền từ role khác.

### 11.3. Role NOLOGIN không có nghĩa không thể bị lợi dụng

`NOLOGIN` ngăn role đăng nhập trực tiếp. Nhưng nếu một login role được phép `SET ROLE` thành nó, hoặc SECURITY DEFINER function chạy dưới owner đó, quyền của role vẫn được sử dụng. **NOLOGIN là một lớp giảm bề mặt tấn công**, không thay cho quản lý membership/EXECUTE.

### 11.4. Tách owner đọc và ghi

Nếu một function chỉ đọc public stock và function khác được phép trừ tồn kho, **đừng nhất thiết dùng chung owner role**. Một role chỉ SELECT và một role chỉ có UPDATE/SELECT tối thiểu cho chức năng tồn kho giúp hạn chế thiệt hại khi một function bị khai thác.

### 11.5. Tách người triển khai và người gọi

Role deployment có thể được phép tạo/thay functions; role runtime chỉ nên được `EXECUTE`. Không cấp cho runtime:

~~~sql
GRANT sec389_fn_owner TO sec389_app;
~~~

vì quyền membership hoặc khả năng `SET ROLE` tương ứng có thể phá mục tiêu tách quyền. Muốn app gọi một function cụ thể, **`GRANT EXECUTE`**, không biến app thành owner.

### 11.6. Owner change là thay đổi bảo mật

~~~sql
-- Thực hiện bởi role có quyền phù hợp sau security review:
ALTER FUNCTION sec389_api.get_available_stock(text)
OWNER TO some_other_role;
~~~

Đổi owner của SECURITY DEFINER function có thể thay đổi **tập quyền mà SQL bên trong sử dụng**, kể cả RLS/ownership behavior. Nó không phải thay đổi metadata vô hại. Phải kiểm tra quyền của owner mới, dependencies và grants trước/sau migration.

### 11.7. Đừng dùng SECURITY DEFINER để giải quyết mọi permission denied

Khi thấy `permission denied`, tìm nguyên nhân: schema USAGE? bảng SELECT? view security? RLS? Quyền function? Chỉ khi thật sự cần một API privileged giới hạn mới chọn SECURITY DEFINER. Chuyển một function thành definer để "cho qua lỗi" có thể mở điểm nâng quyền không được thiết kế.

## 12. RLS và SECURITY DEFINER: cảnh báo rất quan trọng

**Row-Level Security** (*RLS*) giúp kiểm soát những hàng một role được thấy/sửa theo policy. Nhưng `SECURITY DEFINER` đổi effective role khi chạy SQL, vì vậy **RLS có thể được áp dụng theo một role khác caller**.

### 12.1. Table owner thường bypass RLS

PostgreSQL thông thường cho table owner **bypass row security** đối với bảng mình sở hữu, trừ khi bảng có `FORCE ROW LEVEL SECURITY`. Superuser và role `BYPASSRLS` cũng có khả năng đi vòng RLS theo quy tắc đặc biệt.

### 12.2. Nguy cơ điển hình

~~~text
Caller chỉ được xem tenant A theo RLS
        |
        +-- gọi SECURITY DEFINER function
              |
              +-- function owner sở hữu bảng hoặc BYPASSRLS
              |
              +-- SQL bên trong có thể nhìn thấy rows tenant B
~~~

Nếu function không lọc tenant đúng cách, nó có thể trả dữ liệu không thuộc quyền của caller.

### 12.3. Lab hiện tại có lớp phòng thủ nào?

`sec389_fn_owner` **không sở hữu** `sec389_private.inventory`, chỉ có SELECT trên những cột được grant. Đây là cách giảm nguy cơ owner bypass mặc định; nếu bật RLS trên bảng, cần có policies phù hợp cho `sec389_fn_owner`, không mặc định nó sẽ nhìn thấy hàng.

### 12.4. Ví dụ bật RLS trên bảng lab (tùy chọn)

~~~sql
-- Chỉ trong database lab, bằng table owner/DBA:
ALTER TABLE sec389_private.inventory
ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_public_inventory_for_fn_owner
ON sec389_private.inventory
FOR SELECT
TO sec389_fn_owner
USING (is_public = true);
~~~

Khi đó function owner, vốn không sở hữu bảng và không có `BYPASSRLS`, vẫn cần thỏa policy mới đọc được rows. Đây là một lớp bảo vệ bổ sung bên cạnh predicate `is_public=true` trong function.

### 12.5. FORCE ROW LEVEL SECURITY không phải câu thần chú

~~~sql
-- Tùy business need và quyền:
ALTER TABLE sec389_private.inventory
FORCE ROW LEVEL SECURITY;
~~~

`FORCE` khiến table owner thường cũng chịu RLS, nhưng **không khắc phục mọi trường hợp BYPASSRLS/superuser hoặc policy sai**. Nó cũng có thể ảnh hưởng tác vụ maintenance của owner; cần test workflow vận hành.

### 12.6. Nếu policy dùng current_user

Trong SECURITY DEFINER function, `current_user` là **owner function**, không tự là caller. RLS policy dùng `current_user` khi SQL được chạy trong definer context có thể đánh giá theo identity definer. Không xây tenant authorization dựa trên giả định hai identities bằng nhau.

### 12.7. Không truyền tenant_id rồi tin ngay

~~~sql
-- Ví dụ rủi ro nếu không có authorization thật:
-- SELECT * FROM private.orders WHERE tenant_id = p_tenant_id;
~~~

Nếu caller được tự chọn `p_tenant_id`, họ có thể yêu cầu dữ liệu tenant khác. Cần so sánh với một **identity đáng tin**, policy được database bảo vệ hoặc một mapping đã được backend xác minh.

### 12.8. SECURITY DEFINER không vô hiệu hóa RLS một cách phổ quát

Một hàm definer có thể chịu RLS, bypass RLS hoặc thấy policy khác tùy role owner và table ownership. **Không suy ra "SECURITY DEFINER luôn bypass RLS" hay "luôn giữ policy của caller"**.

## 13. View, trigger và helper function dưới definer rights

Một SECURITY DEFINER function có thể gọi một SQL function khác, UPDATE một bảng (kích hoạt trigger), hoặc truy vấn view.

### 13.1. Quyền được đánh giá ở nhiều lớp

~~~text
SECURITY DEFINER api_function()
  |
  +-- SELECT view_x
  |      └── view privilege/RLS semantics riêng
  |
  +-- UPDATE table_y
  |      └── trigger function chạy theo SECURITY INVOKER/DEFINER của nó
  |
  +-- CALL helper_function()
         └── nếu helper là INVOKER, chạy trong role hiện tại ở call context
~~~

Một helper function `SECURITY INVOKER` được gọi từ bên trong definer context có thể chạy theo **effective role hiện tại** (definer), không phải tự động quyền HTTP user. Vì vậy review phải theo **call graph**, không chỉ top-level function.

### 13.2. Trigger có thể tiếp tục mở rộng side effects

Giả sử definer function UPDATE bảng, một AFTER trigger trên bảng lại INSERT audit hoặc gọi procedure/helper khác. Tổng tác động có thể lớn hơn code trong function ban đầu thể hiện.

Khi review, xem:

- Triggers của mọi bảng được ghi;
- Foreign key cascades;
- View definitions;
- Functions/operators được gọi;
- Default values/generated columns có function dependencies;
- Row-level security và ownership từng relation.

### 13.3. SECURITY DEFINER trên trigger function

Trigger functions cũng có thể khai báo `SECURITY DEFINER` để viết audit bằng quyền riêng. Đây là điểm nâng quyền khác cần bảo vệ `search_path`, owner và quyền EXECUTE/trigger-management. Nó không tự biến audit write thành transaction riêng; rollback của statement gốc vẫn rollback audit thuộc cùng transaction.

### 13.4. Đừng dùng SECURITY DEFINER như "backend administrator API"

Một function nhận tên bảng hoặc tên tác vụ rồi thực thi tùy ý:

~~~sql
-- Không nên:
-- EXECUTE 'DELETE FROM ' || p_table_name;
~~~

gần tương đương mở một giao diện quản trị có quyền definer. Hãy dùng các APIs hẹp, có input types, allowlists, authorization và giới hạn số lượng/tần suất.

### 13.5. SECURITY DEFINER và procedure transaction control

Hàm PostgreSQL thông thường không thể tự `COMMIT`/`ROLLBACK`. Procedure `SECURITY DEFINER` cũng **không được transaction control** nội bộ. Không cố "giữ lại các thay đổi dù caller rollback" bằng cách gắn một definer wrapper; đó là vấn đề transaction architecture, không phải cấp quyền.

## 14. API ghi đặc quyền: ngoài SQL injection còn có business authorization

Giả sử viết:

~~~sql
-- Pseudocode, không phải API production:
-- UPDATE sec389_private.inventory
-- SET available_units = available_units - p_qty
-- WHERE sku = p_sku;
~~~

Nếu `sec389_app` được EXECUTE hàm kiểu này không giới hạn, ứng dụng/người dùng có thể **trừ tồn kho tùy ý** dù không có quyền UPDATE trực tiếp trên bảng.

### 14.1. Việc có giới hạn tham số chưa đủ

Thêm:

~~~sql
IF p_qty < 1 OR p_qty > 20 THEN
    RAISE EXCEPTION 'invalid quantity';
END IF;
~~~

chặn một số giá trị không hợp lệ, nhưng caller vẫn có thể **gọi lặp lại nhiều lần** hoặc giảm stock của SKU không thuộc đơn hàng có thật.

### 14.2. Cần kiểm tra quyền nghiệp vụ

Một API reserve stock cần tối thiểu:

- Đơn hàng hợp lệ và thuộc quyền xử lý của caller;
- Mã yêu cầu/idempotency key duy nhất;
- Product SKU thuộc đơn hàng;
- Số lượng trong giới hạn cho phép;
- Trạng thái đơn hàng cho phép reserve;
- Không reserve lặp cho cùng request;
- UPDATE nguyên tử, chống race condition;
- Rollback toàn transaction nếu ghi trạng thái/order/reservation lỗi;
- Audit không lộ dữ liệu nhạy cảm.

### 14.3. UPDATE nguyên tử chống tồn kho âm

Một phần của logic có thể là:

~~~sql
UPDATE sec389_private.inventory
SET available_units = available_units - p_qty
WHERE sku = p_sku
  AND available_units >= p_qty
  AND is_public = true
RETURNING available_units;
~~~

Điều kiện trên giúp xử lý concurrency tốt hơn mẫu `SELECT stock` rồi UPDATE không có guard, nhưng **không bảo đảm caller được phép trừ kho**. Quyền nghiệp vụ, idempotency và transaction consistency vẫn phải được giải quyết.

### 14.4. Tách chức năng ghi sang owner riêng

Nếu cần một protected write API, nên cân nhắc `sec389_reservation_owner` chỉ có `UPDATE(available_units)` và các quyền đọc tối thiểu trên bảng, không dùng owner đọc stock cho mọi thao tác ghi nhạy cảm.

### 14.5. Không lộ giá vốn qua lỗi

Tránh:

~~~sql
RAISE EXCEPTION 'cost_price=%', v_cost_price;
~~~

Với lỗi input, trả lỗi theo hợp đồng API có thể quan sát được mà không tiết lộ bảng/giá trị private. Database log cũng cần retention và access controls.

### 14.6. Không dựa vào SQLSTATE duy nhất như authorization

SQLSTATE rõ giúp phân biệt error categories, nhưng một function trả lỗi "SKU exists but you have no access" có thể tiết lộ sự tồn tại của hàng mà caller không được phép xem. Khi cần chống enumeration, cân nhắc thông báo đồng nhất "not found or unavailable" theo yêu cầu sản phẩm và threat model.

## 15. Trạng thái session và cấu hình từ caller

Ngoài tham số function, session có thể có cấu hình:

- `search_path`;
- `role`/`current_user`;
- `row_security` (trong giới hạn quyền của role);
- `TimeZone`, `DateStyle` và formatting;
- Tên temporary relations;
- Custom settings do application thiết lập;
- Các prepared statements và state được pool tái sử dụng.

### 15.1. Cố định search_path ngay trên function

~~~sql
SET search_path = pg_catalog, sec389_private, pg_temp
~~~

ở định nghĩa hàm tạo function-level config khi thực thi, không dựa vào session của caller đang đặt search_path gì.

### 15.2. SET clause có hiệu lực quanh function call

PostgreSQL lưu các configuration settings khai báo ở function definition và khôi phục state tương ứng sau khi call kết thúc, theo ngữ nghĩa GUC. Điều này tốt cho search_path isolation, nhưng không phải lý do để function tự tin vào **mọi** setting khác do caller cung cấp.

### 15.3. Session pooling

Một HTTP request có thể dùng connection pool đã từng có `SET ROLE` hoặc custom GUC từ request trước. Nếu pool không reset state đúng cách, dữ liệu ủy quyền có thể bị lẫn giữa requests. Phải kiểm soát transaction-scoped state, reset và quyền của service role, không để SECURITY DEFINER function đọc một GUC tùy ý rồi tin là identity mới.

### 15.4. Không tự hạ rào bằng SET search_path từ input

Hàm không nên làm:

~~~sql
-- Không nên trong SECURITY DEFINER:
-- PERFORM set_config('search_path', p_schema_from_user, true);
~~~

Vì điều này cho caller cơ hội điều khiển name resolution trong vùng code privileged. Nếu cần chọn tenant schema, phải định nghĩa allowlist và mô hình ownership/authorization cụ thể; nhiều hệ thống sẽ an toàn hơn với **một schema và tenant_id được kiểm soát**, thay vì schema động theo chuỗi input.

### 15.5. Rủi ro cross-tenant qua connection pool

Ngay cả khi `search_path` an toàn, nếu function dựa vào một application variable không được reset giữa tenants hoặc có thể bị caller ghi, dữ liệu của tenant khác vẫn có nguy cơ bị đọc. Bảo vệ nâng quyền gồm **cả dữ liệu ngữ cảnh**, không chỉ object names.

## 16. Dữ liệu qua hàm có thể rò rỉ theo nhiều kênh

Không chỉ `SELECT` trực tiếp mới là rò rỉ:

| Kênh | Ví dụ |
| --- | --- |
| Giá trị trả về | Function trả thêm `cost_price` ngoài hợp đồng |
| Số hàng trả về | Cho biết có bao nhiêu đơn bí mật |
| Lỗi | `RAISE EXCEPTION 'user X exists'` làm lộ tài khoản |
| Thời gian phản hồi | Timing khác nhau theo việc một row có tồn tại |
| `NOTICE`/log | In SQL, địa chỉ, khóa truy cập hoặc giá trị nhạy cảm |
| Side effects | Cập nhật bảng phụ, gửi thông điệp hoặc tạo file |
| Truy vấn đắt đỏ | Caller lặp hàm gây lock contention/DoS |
| Xem metadata | Lộ schema/function signatures có thể hữu ích cho đối thủ |

### 16.1. Định nghĩa hợp đồng output

Ví dụ `get_available_stock(text) RETURNS integer` chỉ nên trả:

- Số lượng của SKU được công bố;
- SQL NULL cho SKU không tồn tại hoặc không được phép công bố;
- Lỗi input có thể dự đoán mà không chứa dữ liệu nội bộ.

Không trả `ROW(*)` hay `to_jsonb(private_table)` khi API chỉ cần một số.

### 16.2. Cân nhắc tránh enumeration

Nếu role có thể gọi function với mọi SKU và quan sát số lượng/timing, họ có thể thu thập một phần danh mục theo dictionary attack. Nếu rủi ro cần ngăn, hạn chế phạm vi truy vấn, quota/rate limit và xét authorization trước khi đọc dữ liệu.

### 16.3. Log nào có thể giữ bí mật?

Database logs và application traces có thể chứa:

- Tham số gọi function;
- SQL statement;
- Error context;
- Giá trị từ `RAISE NOTICE`;
- User/session identifiers.

Quản lý log access và retention như dữ liệu nhạy cảm. Đừng nghĩ không trả giá trị trong resultset thì thông tin không bao giờ ra khỏi database.

### 16.4. Side effects không tự transaction-safe ngoài DB

Các writes vào bảng PostgreSQL bởi SECURITY DEFINER function thuộc transaction của caller. Nhưng nếu function hoặc helper gọi hệ thống ngoài bằng extension/UDF, external side effects có thể không rollback khi transaction DB bị hủy. Dùng outbox/workers khi cần publish sau commit.

## 17. Transaction và SECURITY DEFINER

Function được gọi trong SQL statement chạy **bên trong transaction của caller**:

~~~sql
BEGIN;

SELECT sec389_api.get_available_stock('KB-001');

ROLLBACK;
~~~

Một function đọc dữ liệu không tự commit. Nếu definer function cập nhật bảng, thay đổi đó vẫn thuộc transaction đang chạy và **có thể rollback bởi caller**.

### 17.1. Quyền cao không đồng nghĩa transaction độc lập

~~~text
Caller BEGIN
   |
   +-- CALL/SELECT SECURITY DEFINER function
   |       └── SQL bên trong chạy với quyền definer
   |
Caller ROLLBACK
   |
   └── Thay đổi dữ liệu chưa commit bị hủy
~~~

**Privilege boundary** và **transaction boundary** là hai cơ chế khác nhau.

### 17.2. Function không tự COMMIT

PostgreSQL functions không thể trực tiếp thực hiện `COMMIT`/`ROLLBACK` như procedures được gọi ở bối cảnh hợp lệ. Một function `SECURITY DEFINER` cũng không có khả năng tự kết thúc transaction của caller.

### 17.3. SAVEPOINT và subtransaction

Caller có thể dùng savepoint trong explicit transaction. Bên trong PL/pgSQL function có thể dùng block `BEGIN ... EXCEPTION ... END` tạo subtransaction để xử lý lỗi cục bộ. Nhưng một function có `EXCEPTION` không được phép biến những changes trước đó thành commits độc lập.

### 17.4. Quan sát lỗi

Nếu definer function báo lỗi và caller đang ở explicit transaction, transaction có thể bị đánh dấu aborted; xử lý bằng `ROLLBACK` hoặc savepoint theo contract client. Không cố gọi thêm function đặc quyền trên một transaction đã aborted.

### 17.5. Kết nối tới database khác qua extension

Một số extensions có thể tạo kết nối riêng hoặc side effects ngoài local transaction. Không cho function owner quyền gọi các tính năng ấy nếu không cần; chúng có thể thay đổi assumptions về rollback/authorization. Đây là lý do owner không nên có toàn bộ extension/OS privileges.

## 18. Function attributes: VOLATILITY, LEAKPROOF và PARALLEL

Một function được khai báo bằng những thuộc tính khác ngoài `SECURITY DEFINER`:

~~~sql
CREATE FUNCTION ...
RETURNS ...
LANGUAGE ...
STABLE
SECURITY DEFINER
SET search_path = ...
AS $$ ... $$;
~~~

### 18.1. STABLE / VOLATILE / IMMUTABLE

| Thuộc tính | Ngữ nghĩa cơ bản |
| --- | --- |
| `VOLATILE` | Kết quả có thể thay đổi mỗi lần gọi; có thể có side effects theo ngôn ngữ/SQL cho phép |
| `STABLE` | Đọc dữ liệu nhất quán theo snapshot statement, không được giả định ghi side effects |
| `IMMUTABLE` | Kết quả chỉ phụ thuộc vào arguments và trạng thái bất biến theo hợp đồng |

Function đọc `inventory` thay đổi theo thời gian **không IMMUTABLE**. Lab dùng `STABLE` vì đọc dữ liệu và không sửa bảng.

### 18.2. Không khai IMMUTABLE sai để planner tối ưu

Một function `IMMUTABLE` nhưng phụ thuộc vào quyền hiện tại, `current_setting` do session đặt hoặc bảng đang thay đổi có thể tạo cached/stale results không đúng trong prepared plans hay expression indexes. Khai đúng volatility trước, rồi tối ưu dựa trên dữ liệu thật.

### 18.3. LEAKPROOF không phải nhãn "đã audit"

`LEAKPROOF` là một thuộc tính rất nhạy cảm, ảnh hưởng cách planner có thể sắp xếp evaluation liên quan security barrier và RLS. Thông thường chỉ superuser được phép khai báo, và nó có yêu cầu nghiêm ngặt về không rò rỉ thông tin ngoài return value (kể cả error/timing theo tài liệu).

**Không đánh dấu function tự viết là `LEAKPROOF` chỉ vì đã dùng `SECURITY DEFINER` hoặc đã kiểm thử đầu vào.**

### 18.4. PARALLEL SAFE

Function có side effects, thay đổi trạng thái session hoặc truy cập không phù hợp với parallel execution không nên được gắn `PARALLEL SAFE` tùy tiện. PostgreSQL có quy tắc phân loại `PARALLEL UNSAFE/RESTRICTED/SAFE`; kiểm tra trước khi khai báo để tránh sai kết quả hoặc hành vi vận hành.

### 18.5. COST / ROWS không phải bảo mật

Thuộc tính `COST`, `ROWS` giúp planner ước tính, không áp authorization, không giảm quyền owner và không thay validation. Một function trả đúng một số vẫn cần `EXECUTE` ACL và secure search path.

### 18.6. SQL function inlining không phải yếu tố có thể dùng để nới quyền

Đừng dựa vào optimizer inlining hoặc cache để nghĩ quyền SQL bên trong đã được kiểm chứng an toàn. Việc thực thi SECURITY DEFINER phải đúng với privilege semantics và configuration đã khai báo, bất kể planner chọn cách tối ưu nào.

## 19. Cách đổi hàm đang dùng từ INVOKER sang DEFINER

PostgreSQL hỗ trợ thay đổi thuộc tính của function bằng `ALTER FUNCTION`:

~~~sql
-- Chỉ sau review quyền, trong migration được kiểm soát:
ALTER FUNCTION sec389_api.get_available_stock(text)
SECURITY DEFINER;
~~~

Nhưng **đây là một thay đổi bảo mật lớn**. Nếu hàm trước đó chạy với quyền caller, sau migration nó sẽ chạy bằng quyền owner. Mọi lỗ hổng nhỏ như dynamic SQL, search path hoặc return rộng sẽ có tác động khác.

### 19.1. Checklist trước khi ALTER

1. Ai là owner hiện tại?
2. Owner có quyền gì trên các tables/sequences/functions?
3. Function có dùng tên object không qualified?
4. Có `SET search_path` an toàn?
5. Có dynamic SQL hoặc user-controlled identifiers?
6. Có calls tới helper functions/triggers?
7. `EXECUTE` có đang được PUBLIC hoặc nhiều roles nắm giữ?
8. Có RLS/table ownership và tenant policy không?
9. Dữ liệu output/errors có thể lộ gì?
10. Có test bằng role không có quyền bảng trực tiếp chưa?

### 19.2. Đừng làm migration theo chuỗi commits rời

Sai về ý tưởng triển khai:

~~~text
ALTER FUNCTION ... SECURITY DEFINER; COMMIT;
-- Mãi sau mới khóa search_path / revoke PUBLIC EXECUTE.
~~~

Trong khoảng này, hàm có thể đã thành một điểm nâng quyền chưa được bảo vệ đầy đủ.

Ưu tiên migration:

~~~sql
BEGIN;

-- Các ALTER/CREATE OR REPLACE cần thiết đã được review:
ALTER FUNCTION sec389_api.get_available_stock(text)
SET search_path = pg_catalog, sec389_private, pg_temp;

ALTER FUNCTION sec389_api.get_available_stock(text)
SECURITY DEFINER;

REVOKE ALL ON FUNCTION
    sec389_api.get_available_stock(text)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
    sec389_api.get_available_stock(text)
TO sec389_app;

COMMIT;
~~~

Trong thực tế, một phần của migration có thể cần đổi ownership/grants ngoài một transaction hoặc do các owners khác thực hiện; điều quan trọng là không công khai một function đặc quyền trong trạng thái không an toàn.

### 19.3. CREATE OR REPLACE không tự xóa ACL

`CREATE OR REPLACE FUNCTION` thông thường có thể giữ ownership/permissions hiện có của function; không được giả định replace sẽ **reset grants về an toàn** hoặc đổi owner theo role triển khai. Sau mỗi replace, phải kiểm tra ACL, security mode, function-level SET và owner.

### 19.4. Overloading có thể mở đường gọi không dự định

Một schema có:

~~~text
sec389_api.get_stock(text)
sec389_api.get_stock(varchar)
sec389_api.get_stock(text, boolean DEFAULT true)
~~~

Các signature khác nhau có thể dẫn tới overload resolution phức tạp và quyền EXECUTE khác nhau. Khi dùng ACL, kiểm tra **mọi signature có thể được gọi**, không chỉ hàm được nhắc trong docs.

### 19.5. Chuyển owner có thể vô tình đổi RLS

Sau `ALTER FUNCTION ... OWNER TO new_owner`, effective role và RLS context có thể thay đổi. Kể cả SQL/function body giữ nguyên, output vẫn có thể khác. Test bằng caller role trước/sau migration.

## 20. Quyền trên schema public và extension objects

Trong nhiều databases, schema `public` chứa nhiều functions, views và extensions. Khi một SECURITY DEFINER function dùng unqualified names hoặc phụ thuộc extension functions nằm trong schema người dùng có thể tạo objects, bề mặt hijacking tăng.

### 20.1. Kiểm tra ACL schema

~~~sql
SELECT
    n.nspname AS schema_name,
    n.nspowner::regrole AS owner_role,
    n.nspacl
FROM pg_catalog.pg_namespace AS n
WHERE n.nspname IN (
    'public',
    'sec389_api',
    'sec389_private'
)
ORDER BY schema_name;
~~~

`nspacl` có thể là NULL, thể hiện default privileges chứ không có nghĩa "ai cũng không có quyền"; dùng functions kiểm tra quyền để diễn giải thay vì suy luận chỉ từ NULL.

### 20.2. has_schema_privilege

~~~sql
SELECT
    has_schema_privilege(
        'sec389_app',
        'sec389_api',
        'USAGE'
    ) AS app_can_use_api_schema,
    has_schema_privilege(
        'sec389_app',
        'sec389_api',
        'CREATE'
    ) AS app_can_create_in_api,
    has_schema_privilege(
        'sec389_app',
        'sec389_private',
        'USAGE'
    ) AS app_can_use_private_schema;
~~~

Trong lab sạch, kỳ vọng `true`, `false`, `false`. Trên production, grants/memberships và quyền inherited có thể thay đổi kết quả.

### 20.3. Extensions và trusted schemas

Nếu function cần gọi hàm từ extension, đặt extension trong schema được kiểm soát và schema-qualify lời gọi khi cần. Không chuyển extension sang schema cho mọi user CREATE chỉ để tránh lỗi `search_path`; thay vào đó thiết kế namespaces/GRANT phù hợp.

### 20.4. Cẩn trọng khi thay quyền CREATE trên public

~~~sql
-- Ví dụ chính sách được DBA review, không chạy mù:
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
~~~

Lệnh có thể làm các workflows tạo object mới trong schema public không còn hoạt động. Trước thay đổi production, rà các applications/migrations đang sử dụng public và định nghĩa schema đích rõ ràng.

### 20.5. Nguyên tắc "trusted schema"

Một schema chỉ nên được liệt kê như trusted khi:

- Owner và mọi role có quyền CREATE/ALTER ở đó đều đáng tin;
- Object migrations được review;
- Không có tên functions/operators dễ shadow;
- Không có untrusted input điều khiển object definitions;
- Các quyền đã được kiểm tra, kể cả inherited membership.

## 21. PostgreSQL security barrier không thay SECURITY DEFINER review

Views có thuộc tính `security_barrier` nhằm hạn chế một số cách optimizer đẩy điều kiện có thể gây rò rỉ dữ liệu. Chế độ view security (ví dụ `security_invoker` ở các phiên bản hỗ trợ) cũng tác động cách quyền/RLS được xác định.

### 21.1. Hai cơ chế ở hai lớp khác nhau

- `SECURITY DEFINER` ở **function**: đổi identity thực thi SQL.
- `security_barrier` hoặc `security_invoker` ở **view**: ảnh hưởng query planning/security context cho view.

Chúng không tự triệt tiêu rủi ro của nhau. Một definer function SELECT một view vẫn phải được review theo view owner/security/RLS/underlying tables.

### 21.2. Không cho phép bypass bằng cách bọc function vào view

Một view gọi function đặc quyền và được SELECT bởi app có thể tạo một **đường thực thi khác** tới function. Xác định rõ grants trên view, function và underlying objects; không cho rằng việc user chỉ được SELECT view khiến mọi output của function tự trở nên được phép.

### 21.3. Hàm nhạy cảm và evaluation order

SQL optimizer có quyền sắp xếp expressions theo semantics cho phép. Không viết function trả bí mật rồi dựa vào thứ tự đánh giá `WHERE` để "ngăn nó được gọi" trong những trường hợp cụ thể. Authorization cần được **bảo đảm trong API/hàm/policy**, không phải phụ thuộc một plan tối ưu ngẫu nhiên.

## 22. Một số anti-pattern khi viết privileged functions

| Anti-pattern | Vì sao nguy hiểm | Thay bằng |
| --- | --- | --- |
| Hàm definer được sở hữu bởi superuser | Blast radius cực lớn | Dedicated NOLOGIN owner có quyền tối thiểu |
| Hàm tạo ra rồi mới REVOKE ở transaction khác | Cửa sổ PUBLIC EXECUTE | CREATE+REVOKE+GRANT trong cùng transaction |
| Không SET search_path | Object-name hijacking | SET path trusted, pg_temp cuối |
| Dùng schema public có CREATE cho untrusted roles | Function/operator shadowing | Dedicated trusted schemas |
| SQL không schema-qualify bảng quan trọng | Dễ resolve sai relation | Dùng `schema.table` |
| Để user chọn table/schema/function tự do | Truy cập ngoài API contract | Fixed statements hoặc allowlist |
| Nối `p_input` thành dynamic SQL | SQL injection trong definer context | Static SQL, `EXECUTE ... USING` |
| Chỉ quote identifier mà không authorization | Có thể đọc bảng ngoài phạm vi | Quote + allowlist + privilege checks |
| Dùng current_user để nhận user HTTP | Trong definer function là owner | Identity thực đã chứng thực |
| Tin p_tenant_id từ caller | Cross-tenant access | Xác minh tenant membership |
| Tin custom GUC do caller tự đặt | Impersonation qua session state | Protected context/role mapping |
| Owner function cũng owner tất cả tables | Có thể bypass RLS/đọc mọi cột | Tách data owner và fn owner |
| Function trả `SELECT *` | Lộ cột mới sau migration | Explicit output projection |
| Log toàn bộ parameters/row | Lộ secrets/PII | Redaction và access-controlled logs |
| Bắt lỗi rồi trả SQL text chi tiết | Enumeration/internal data leak | Sanitized errors |
| Dùng SECURITY DEFINER để tránh thiết kế authorization | Escalation tùy ý | API capability hẹp và policy |
| GRANT EXECUTE trên mọi function cho PUBLIC | Mở nhiều điểm nâng quyền | Grants theo signature |
| Không test bằng role quyền thấp | Test với owner luôn pass | Negative tests cho app roles |
| Không kiểm tra function overloading | Signature khác có ACL rộng | Review toàn bộ overloads |
| Dùng RLS theo current_user mà quên definer | Policy đánh giá theo owner | Kiểm tra context và role privileges |
| Đánh dấu LEAKPROOF tùy ý | Planner/security semantics sai | Không đánh dấu nếu không đủ điều kiện |
| Test trên môi trường prod bằng payload thử | Có thể gây lộ/sửa dữ liệu | Lab/isolated test with approved roles |

## 23. Kiểm kê hàm SECURITY DEFINER trong database

Khi tiếp nhận một database có nhiều schemas, việc đầu tiên là **biết có bao nhiêu điểm nâng quyền và ai sở hữu chúng**. PostgreSQL lưu metadata function ở `pg_proc`, schema ở `pg_namespace` và role ở `pg_roles`.

### 23.1. Danh sách SECURITY DEFINER functions

~~~sql
SELECT
    n.nspname AS function_schema,
    p.proname AS function_name,
    p.oid::regprocedure AS signature,
    owner.rolname AS owner_role,
    p.prosecdef AS is_security_definer,
    p.proconfig AS function_settings,
    p.proacl AS function_acl
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
JOIN pg_catalog.pg_roles AS owner
    ON owner.oid = p.proowner
WHERE p.prosecdef
ORDER BY n.nspname, p.oid::regprocedure::text;
~~~

Các cột cần chú ý:

- `prosecdef`: true cho SECURITY DEFINER.
- `proowner`: owner OID, ánh xạ ra role.
- `proconfig`: function-level `SET` clauses (nếu có).
- `proacl`: ACL riêng; có thể NULL nếu dùng default privileges.

### 23.2. Cách đọc proacl NULL

`proacl IS NULL` không có nghĩa function không ai được gọi. Nó thường biểu thị chưa có ACL đặc biệt, và **default privileges** vẫn có hiệu lực. Dùng hàm `has_function_privilege` hoặc `aclexplode`/information_schema để kiểm tra quyền thực.

### 23.3. Kiểm tra ai có EXECUTE

~~~sql
SELECT
    has_function_privilege(
        'sec389_app',
        'sec389_api.get_available_stock(text)',
        'EXECUTE'
    ) AS app_can_execute,
    has_function_privilege(
        'sec389_data_owner',
        'sec389_api.get_available_stock(text)',
        'EXECUTE'
    ) AS data_owner_can_execute;
~~~

Trong một mô hình NOLOGIN roles, kết quả này nói về **quyền của role được nêu**, không có nghĩa role đó đang là người đăng nhập. Không dựa vào `has_function_privilege` của một role đơn lẻ để bỏ qua quyền inherited memberships của actual client.

### 23.4. Kiểm tra PUBLIC execute sau REVOKE

Để kiểm tra grant trực tiếp cho `PUBLIC`, đọc ACL đã materialize. Trong catalog ACL, `grantee=0` đại diện cho PUBLIC:

~~~sql
SELECT
    EXISTS (
        SELECT 1
        FROM pg_catalog.aclexplode(
            COALESCE(
                p.proacl,
                pg_catalog.acldefault('f', p.proowner)
            )
        ) AS a
        WHERE a.grantee = 0
          AND a.privilege_type = 'EXECUTE'
    ) AS public_has_execute
FROM pg_catalog.pg_proc AS p
WHERE p.oid =
    'sec389_api.get_available_stock(text)'::regprocedure;
~~~

`PUBLIC` là một **pseudo-role/grantee trong ACL**, không phải một login role mà bạn nên truyền như user name cho mọi privilege checker. Kết hợp kiểm tra grant PUBLIC với **thử gọi từ role quyền thấp không được cấp quyền**.

Đừng nhầm “role A không trực tiếp được GRANT” với “A không thể gọi”: A có thể có quyền inherited từ role membership hoặc PUBLIC grants.

### 23.5. Liệt kê ACL sau khi tạo hàm

~~~sql
SELECT
    p.oid::regprocedure AS function_signature,
    p.proacl,
    p.proconfig,
    p.prosecdef
FROM pg_catalog.pg_proc AS p
WHERE p.oid =
    'sec389_api.get_available_stock(text)'::regprocedure;
~~~

Quan sát liệu `EXECUTE` có được cấp cho `sec389_app` và bị thu hồi từ `PUBLIC` như contract. Không dựa vào raw `proacl` một mình để biết quyền kết hợp membership; kết hợp các truy vấn privilege checker.

### 23.6. Xuất định nghĩa để review

~~~sql
SELECT
    p.oid::regprocedure AS signature,
    pg_catalog.pg_get_functiondef(p.oid) AS definition
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE p.prosecdef
  AND n.nspname = 'sec389_api'
ORDER BY signature::text;
~~~

Review body, `SET search_path`, volatility, SQL dynamic, helpers và output. Đừng đăng công khai toàn bộ function definitions nếu chúng chứa business logic hoặc internal table names nhạy cảm.

### 23.7. Kiểm tra quyền tạo object ở API schema

~~~sql
SELECT
    has_schema_privilege(
        'sec389_app', 'sec389_api', 'CREATE'
    ) AS app_can_create,
    has_schema_privilege(
        'sec389_fn_owner', 'sec389_api', 'CREATE'
    ) AS definer_can_create;
~~~

Kỳ vọng lab là app không CREATE, fn owner có CREATE vì là schema owner. **Schema owner có toàn quyền thay objects trong schema của mình**, nên không để definer owner có password/login được chia sẻ rộng rãi.

### 23.8. Kiểm tra quyền cột private

~~~sql
SELECT
    has_column_privilege(
        'sec389_fn_owner',
        'sec389_private.inventory',
        'available_units',
        'SELECT'
    ) AS can_read_stock,
    has_column_privilege(
        'sec389_fn_owner',
        'sec389_private.inventory',
        'cost_price',
        'SELECT'
    ) AS can_read_cost;
~~~

Trong lab sạch, kỳ vọng `true` và `false`. Nếu `can_read_cost=true`, tìm quyền inherited hoặc grants khác; không chỉ dựa vào việc dòng `GRANT SELECT(cost_price)` không xuất hiện trong script.

### 23.9. Kiểm tra role membership

~~~sql
SELECT
    r.rolname AS granted_role,
    m.member::regrole AS member_role,
    m.grantor::regrole AS grantor_role
FROM pg_catalog.pg_auth_members AS m
JOIN pg_catalog.pg_roles AS r
    ON r.oid = m.roleid
WHERE r.rolname IN (
    'sec389_data_owner',
    'sec389_fn_owner',
    'sec389_app'
)
ORDER BY granted_role, member_role::text;
~~~

PostgreSQL versions mới có các lựa chọn membership `INHERIT/SET/ADMIN`; role graph cần được review cùng version. Một membership vào role owner có thể quan trọng hơn một `GRANT SELECT` trực tiếp trên bảng.

### 23.10. Ghi chú về thông tin không xem được

Một số catalog fields, role details hoặc function bodies có thể không được phép quan sát đầy đủ bởi role hiện tại. Khi kiểm toán production, DBA/security team cần quyền phù hợp và quy trình truy cập được phê duyệt, không cấp superuser cho ứng dụng chỉ để chạy audit query.

## 24. Kiểm thử âm tính bằng role quyền thấp

Một privilege test tốt phải có cả **positive tests** (hành vi được phép) và **negative tests** (hành vi phải bị chặn).

### 24.1. Ma trận kiểm thử lab

| Lời gọi/thao tác | Role thực hiện | Kỳ vọng |
| --- | --- | --- |
| `SELECT sec389_api.get_available_stock('KB-001')` | `sec389_app` | 17 |
| `SELECT sec389_api.get_available_stock('MS-002')` | `sec389_app` | 0 |
| `SELECT sec389_api.get_available_stock('INTERNAL-001')` | `sec389_app` | SQL NULL |
| `SELECT * FROM sec389_private.inventory` | `sec389_app` | Bị từ chối |
| `UPDATE sec389_private.inventory ...` | `sec389_app` | Bị từ chối |
| `CREATE FUNCTION sec389_api.some_fn(...)` | `sec389_app` | Bị từ chối |
| `SELECT sec389_api.get_available_stock(...)` | Role không có EXECUTE/USAGE | Bị từ chối |
| `SELECT cost_price ...` | `sec389_fn_owner` | Bị từ chối trong lab sạch |

### 24.2. Thử từ caller chính thức

Ở môi trường thật, tốt nhất là dùng **đúng service login role** với transaction manager/connection pool thực tế, không chỉ chạy bằng DBA rồi `SET ROLE`.

Trong lab có quyền:

~~~sql
SET ROLE sec389_app;
SELECT sec389_api.get_available_stock('KB-001');
RESET ROLE;
~~~

Nếu role không thể `SET ROLE sec389_app`, không cấp quyền đó bừa bãi; dùng một account test được DBA chuẩn bị với đúng effective privileges.

### 24.3. Test đối tượng không thuộc quyền

Nếu API dùng tenant_id, tạo hai tenants A và B, cấp caller chỉ tenant A, xác minh:

1. Có thể đọc tài nguyên tenant A;
2. Không thể đọc tenant B dù biết ID;
3. Không lộ sự tồn tại tenant B qua lỗi chi tiết;
4. Cấu hình `SET ROLE`/GUC của caller không đổi kết quả authorization;
5. Connection pool reuse không làm lẫn identity.

### 24.4. Test name shadowing ở lab riêng

Tạo một relation cùng tên trong một **temporary schema** của session test rồi gọi function đã khóa `search_path`. Kết quả phải phản ánh `sec389_private.inventory`, không phải relation tạm.

~~~sql
-- Chỉ ở session lab (không trên production):
CREATE TEMP TABLE inventory (
    sku text,
    available_units integer,
    is_public boolean
);

INSERT INTO inventory(sku, available_units, is_public)
VALUES ('KB-001', 999999, true);

-- Function an toàn phải trả về số từ sec389_private.inventory:
SELECT sec389_api.get_available_stock('KB-001');
~~~

Nếu caller đã được `EXECUTE`, kết quả kỳ vọng là **17**, không phải 999999. Ví dụ này kiểm tra một lớp name-resolution defense; không tự chứng minh mọi helper/dynamic SQL đều đã an toàn.

### 24.5. Thay đổi session search_path

~~~sql
-- Chỉ test trong session đã được phép:
SET search_path = pg_temp, public;

SELECT sec389_api.get_available_stock('KB-001');

RESET search_path;
~~~

Vì SQL trong function schema-qualify relation và function có `SET search_path` an toàn, kết quả không nên phụ thuộc search path caller.

### 24.6. Test SQL input như dữ liệu, không phải SQL

Nếu API chấp nhận `p_sku` kiểu text, nhập các chuỗi chứa quote hoặc ký tự đặc biệt trong **test data được kiểm soát**. Function phải xem chúng như SKU values, không làm thay đổi cú pháp câu SQL.

### 24.7. Test trạng thái NULL và input không hợp lệ

~~~sql
SELECT sec389_api.get_available_stock(NULL::text);
SELECT sec389_api.get_available_stock('');
SELECT sec389_api.get_available_stock('NON-EXISTENT');
~~~

Trong function lab dùng SQL equality, các trường hợp này thường trả SQL NULL. Production có thể chọn validate input và báo lỗi chung, nhưng không được lộ dữ liệu bí mật trong thông báo.

### 24.8. Negative tests phải được tự động hóa

Không chỉ test trong migration một lần. Sau mỗi lần đổi owner, view, RLS policy, schema grants, function body hay quyền role, chạy lại regression tests bằng actual caller roles.

## 25. Dữ liệu audit của việc gọi SECURITY DEFINER

Audit có hai mục đích khác nhau:

1. **Audit hoạt động nghiệp vụ đã thành công:** ai/nhóm nào yêu cầu xem/sửa dữ liệu và thay đổi nào đã commit.
2. **Audit nỗ lực truy cập thất bại/vi phạm:** những lời gọi không được phép, lỗi và dấu hiệu abuse.

### 25.1. Audit INSERT trong cùng database rollback được

Nếu function ghi một hàng vào bảng audit trong transaction của caller, bản ghi đó sẽ rollback khi transaction rollback. Đây là đúng về ACID nhưng có thể không đáp ứng yêu cầu lưu lại **mọi nỗ lực truy cập bị chặn**.

### 25.2. Ghi nhận attempts thất bại

Các dấu hiệu từ application gateway, database logging hoặc cơ chế audit chuyên dụng có thể cần thiết để ghi cả những attempts bị rollback, tùy retention/compliance. Không cố đưa chức năng ghi log độc lập vào SECURITY DEFINER function bằng cách tự COMMIT trong function.

### 25.3. Tối thiểu hóa dữ liệu audit

Ghi:

- Tên API/function hoặc loại tác vụ;
- Request/run identifier;
- Thời điểm và outcome;
- Database/service role đã xác định;
- Resource identifiers đã sanitize;
- Error category/SQLSTATE nếu phù hợp.

Không log thẳng secrets, token, password, full card data hoặc nhiều PII không cần thiết.

### 25.4. Không đặt quyền sửa audit ở app

Nếu bảng audit phục vụ kiểm chứng, app runtime chỉ nên có quyền phù hợp để gửi sự kiện qua một API, không có `DELETE/UPDATE` tùy ý trên audit. Nhưng kể cả bảng audit do owner riêng nắm giữ, log bên trong transaction vẫn có thể rollback. Hai vấn đề cần được giải quyết riêng.

### 25.5. Hạn chế thông tin ở lỗi

Một người dùng không được xem tài khoản khác không nên phân biệt "không tồn tại", "bị khóa", "khác tenant" qua thông báo quá chi tiết nếu threat model coi account enumeration là rủi ro. Thiết kế lỗi rõ cho ứng dụng nhưng không lộ giá trị dữ liệu nội bộ.

## 26. Kiểm soát vận hành và độ sẵn sàng

SECURITY DEFINER function có thể được gọi với tần suất lớn, ngay cả khi output chỉ một dòng.

### 26.1. Rate limit và query cost

Một API có `EXECUTE` cho application role có thể bị abuse bằng:

- Gọi lặp hàng triệu lần;
- Input khiến SQL bên trong không dùng index;
- Query rộng trên bảng lớn;
- Tham số làm phát sinh khóa/ghi nhiều;
- Thao tác dynamic SQL vào tables không dự tính.

Áp dụng giới hạn ở tầng app/gateway, index phù hợp, statement timeout, connection pool budgets và query monitoring.

### 26.2. Không dựa vào STABLE để tránh DoS

`STABLE` nói về tính ổn định/side-effect contract, không phải giới hạn CPU hoặc tần suất gọi. Một stable definer function vẫn có thể thực hiện một SELECT đắt đỏ.

### 26.3. Công cụ quan sát

Các nguồn thường dùng:

- `pg_stat_activity`: query/session/wait events;
- `pg_locks` và `pg_blocking_pids`: lock contention;
- `pg_stat_statements` nếu extension/cấu hình đã bật: thống kê câu SQL;
- Application traces: endpoint, latency, request id;
- Audit logs theo policy;
- DDL migration history: ai thay owner/function ACL.

### 26.4. EXPLAIN không phải phép thử security

`EXPLAIN` giúp đọc kế hoạch và chi phí của SQL nhưng không chứng minh mọi role/tenant bị chặn. `EXPLAIN (ANALYZE)` **thực thi statement**, có thể thay đổi dữ liệu khi áp vào DML hoặc function có side effects. Chỉ chạy trên lab/benchmark đã kiểm soát và không xem một plan nhanh là proof of authorization.

### 26.5. Cấu hình statement_timeout

Timeout có thể bảo vệ tài nguyên trước queries kéo dài nhưng không thay quota/authorization. Các lệnh thay GUC ở session có thể tồn tại qua connection pool nếu không reset đúng; dùng policy nhất quán ở tầng datasource/role hoặc transaction scope thích hợp.

## 27. Runbook sự cố: nghi ngờ function bị khai thác quyền

Khi phát hiện một privileged function trả dữ liệu bất thường, bị gọi bởi role lạ hoặc có hành vi ghi ngoài mong đợi:

### Giai đoạn 1 — Xác định ảnh hưởng

- Function nào, signature nào?
- Owner role hiện tại và trước migration?
- Ai được `EXECUTE`? Có `PUBLIC` hay inherited membership không?
- Functions/helpers/views/triggers nào bị gọi theo?
- Có data access xuyên tenant hoặc đọc cột nhạy cảm?
- Có dấu hiệu external side effects hoặc DML không?
- Thời điểm bắt đầu và phạm vi phiên bản bị ảnh hưởng?

### Giai đoạn 2 — Chặn đường gọi ngoài ý định

Theo quy trình incident response được phê duyệt, cân nhắc **REVOKE EXECUTE** đối với roles không được phép, vô hiệu hóa một API tại gateway, hoặc rollback deployment. Không tự xóa function/bảng production khi còn cần bảo toàn chứng cứ và trạng thái nghiệp vụ.

### Giai đoạn 3 — Kiểm tra object-resolution surface

Đọc `pg_get_functiondef` và:

- Function-level `SET search_path`;
- Schemas có quyền CREATE;
- Temporary-table handling;
- Dynamic SQL;
- Các tên table/function/operator không qualified;
- Role inheritance;
- Overloads/default arguments.

### Giai đoạn 4 — Kiểm tra dữ liệu và quyền

Đối chiếu audit/query logs, row access, bảng bị ghi, current owner privileges và RLS settings. Xem có secrets/cost/tenant data bị tiết lộ hay không; không tự kết luận chưa có lộ dữ liệu chỉ vì function không trả error.

### Giai đoạn 5 — Sửa và kiểm thử

Sửa nguyên nhân gốc (authorization, name resolution, SQL injection hoặc excessive privilege), thực thi migration atomically, kiểm thử bằng role quyền thấp, thử temp shadow và cross-tenant negative tests.

### Giai đoạn 6 — Phục hồi và theo dõi

Nếu function có thể đã lộ bí mật, làm theo quy trình rotate credentials/tokens và thông báo bảo mật phù hợp. Theo dõi failed/suspicious calls, permission changes, latency và role grants sau deploy.

### Giai đoạn 7 — Không quên rollback/fix-forward

Một rollback function code có thể **không tự hoàn lại** dữ liệu đã bị UPDATE/DELETE bởi các calls hợp lệ về mặt transaction trước đó. Cần reconciliations và khắc phục dữ liệu theo nghiệp vụ, không chỉ đổi lại body của function.

## 28. Review checklist cho pull request hoặc migration

| Hạng mục | Câu hỏi phải trả lời |
| --- | --- |
| Use case | Tại sao cần definer thay vì invoker/GRANT/RLS/view? |
| Owner | Dedicated role hay superuser/table owner? |
| Privileges | Owner có đúng các SELECT/UPDATE/USAGE cần thiết? |
| Schema | Có schema untrusted ở search path không? |
| pg_temp | Có được ghi rõ cuối search path không? |
| Object names | Tables/functions/operators có qualified đủ rõ? |
| Function args | Data types, NULL, bounds, identifiers, JSON? |
| Dynamic SQL | Có sử dụng `USING` và allowlist? |
| Authorization | Caller/tenant/resource identity được xác minh ở đâu? |
| ACL | PUBLIC EXECUTE đã REVOKE? Grants đúng signature? |
| DDL atomicity | CREATE/ALTER+REVOKE/GRANT có cửa sổ thiếu an toàn không? |
| RLS | Owner có bypass? Policy có dựa vào current_user sai không? |
| Data output | Có trả cột bí mật, row count hoặc lỗi nhạy cảm không? |
| Dependencies | Helpers/views/triggers/FDWs/extensions được review? |
| Volatility | STABLE/IMMUTABLE/LEAKPROOF/PARALLEL được khai đúng? |
| Side effects | Có external calls, audit/outbox, lock amplification? |
| Testing | Positive và negative tests bằng caller thực tế? |
| Monitoring | Logs, errors, latency, resource budgets? |
| Migration | Owner/ACL/schema dependency review và rollback? |

## 29. Tình huống lựa chọn SECURITY DEFINER hay giải pháp khác

### 29.1. Chỉ cần đọc một subset cột

Có thể dùng **column-level GRANT** trên bảng hoặc một view bảo vệ dữ liệu với quyền/semantics phù hợp. SECURITY DEFINER function chỉ cần thiết nếu muốn API behavior rõ, có logic/hạn chế không diễn đạt phù hợp bằng grant/view thông thường.

### 29.2. Cần chỉ đọc rows của tenant hiện tại

Row-Level Security thường là nền tảng phù hợp khi database có thể tin cậy identity/tenant context. SECURITY DEFINER có thể bỏ qua hoặc đổi RLS context; cân nhắc rất kỹ trước khi dùng nó như lối tắt.

### 29.3. Cần ghi audit tự động

Trigger function với quyền phù hợp có thể giúp ghi audit nhưng vẫn cần bảo vệ owner, search path, PII/retention và transaction semantics. Không phải mọi audit trigger đều cần SECURITY DEFINER nếu caller đã có quyền ghi một bảng audit phù hợp.

### 29.4. Cần thao tác business có kiểm soát

Một SECURITY DEFINER function nhỏ với signature hẹp, validation, authorization và quyền UPDATE tối thiểu có thể hợp lý. Nếu giao dịch liên quan nhiều services/outbox/retries, tầng service/workflow explicit có thể dễ quản lý hơn.

### 29.5. Cần cho client chạy SQL tùy ý trên bảng private

Không nên dùng SECURITY DEFINER làm "SQL execution proxy" cho arbitrary statements. Đó là mô hình quá rộng, không phải một capability API.

### 29.6. Cần kiểm tra quyền trên role gốc

Function `SECURITY INVOKER` kết hợp row-level privileges/RLS có thể phù hợp hơn để giữ quyền của caller. SECURITY DEFINER đổi effective identity; nếu yêu cầu là giữ nguyên quyền caller, không thêm definer vô cớ.

## 30. Bài tập thực hành — quyền cơ bản và search_path

Các bài tập dùng ba roles và hai schemas trong lab. Những bài liên quan `CREATE ROLE`, `ALTER FUNCTION OWNER` hoặc `GRANT` cần một DBA hoặc account có quyền được phê duyệt. Không chạy các thử nghiệm lỗ hổng trên production; các bài “hàm không an toàn” chỉ để phân tích lỗi, không phải mẫu triển khai. **Không phải mọi câu hỏi đều cần thực thi SQL** — một số yêu cầu giải thích semantics hoặc review một đoạn pseudocode.

### Bài 1 — Phân biệt hai chế độ thực thi

Một function mặc định `SECURITY INVOKER` có thể đọc bảng mà caller không có `SELECT` không? Nếu đổi thành `SECURITY DEFINER` nhưng owner cũng không có `SELECT` thì sao?

**Đáp án:** invoker dùng quyền caller; definer dùng quyền owner, nhưng không tự tạo quyền mới cho owner.

### Bài 2 — Mục đích của API có quyền

Role app chỉ cần biết số tồn kho của SKU được công khai, nhưng bảng còn `cost_price`.

**Bài tập:** vẽ ranh giới API sao cho app gọi function được nhưng không SELECT bảng/cột giá vốn.

### Bài 3 — CURRENT_USER bên trong definer

Một service role gọi function do `sec389_fn_owner` sở hữu.

**Câu hỏi:** `current_user` bên trong function là ai? Nó có phải người dùng đăng nhập website không?

**Đáp án:** effective role là owner function; không thể suy ra identity người dùng HTTP.

### Bài 4 — SESSION_USER và SET ROLE

Khi được phép, chạy `SET ROLE sec389_app` rồi xem:

~~~sql
SELECT session_user, current_user;
~~~

**Câu hỏi:** vì sao hai giá trị có thể khác nhau? Điều gì xảy ra bên trong SECURITY DEFINER function?

### Bài 5 — Function EXECUTE mặc định

Vì sao cần `REVOKE EXECUTE ON FUNCTION ... FROM PUBLIC` ngay khi tạo function nhạy cảm?

**Đáp án:** functions mới có thể có default EXECUTE cấp cho PUBLIC, nên phải thu hồi và grant lại cho role được phép.

### Bài 6 — CREATE/REVOKE cùng transaction

~~~sql
BEGIN;
CREATE FUNCTION ... SECURITY DEFINER ...;
REVOKE ALL ON FUNCTION ... FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ... TO sec389_app;
COMMIT;
~~~

**Câu hỏi:** tại sao an toàn hơn việc CREATE rồi COMMIT trước, REVOKE ở migration sau?

### Bài 7 — PUBLIC role vs public schema

Giải thích sự khác nhau giữa `REVOKE ... FROM PUBLIC` và `REVOKE CREATE ON SCHEMA public FROM PUBLIC`. Trong mỗi câu, “public” biểu diễn những gì?

### Bài 8 — USAGE schema

Nếu app có `EXECUTE` trên function nhưng **không có `USAGE`** trên schema API, điều gì có thể xảy ra khi gọi function theo tên fully qualified?

### Bài 9 — Private schema

Trong lab, app có cần `USAGE ON SCHEMA sec389_private` để gọi `sec389_api.get_available_stock(...)` không?

**Đáp án:** không; SQL trong definer function được thực thi theo quyền definer owner, vốn có USAGE private schema.

### Bài 10 — Quyền cột

~~~sql
GRANT SELECT (sku, available_units, is_public)
ON sec389_private.inventory TO sec389_fn_owner;
~~~

**Câu hỏi:** chủ hàm có quyền đọc `cost_price` không nếu không có grants/membership nào khác?

### Bài 11 — Tách owner

So hai thiết kế:

1. Function owner cũng là table owner, có quyền UPDATE/DELETE.
2. Function owner chỉ có quyền SELECT ba cột cần thiết.

**Bài tập:** phân tích blast radius nếu SQL trong function bị điều khiển sai.

### Bài 12 — NOLOGIN

`sec389_fn_owner NOLOGIN` có nghĩa role đó không thể được sử dụng bởi SECURITY DEFINER function không?

**Đáp án:** không; NOLOGIN hạn chế đăng nhập trực tiếp nhưng quyền role vẫn áp dụng khi function thực thi hoặc khi một account được phép SET ROLE.

### Bài 13 — Role membership

Một DBA vô tình cấp app role quyền được `SET ROLE sec389_fn_owner`. Hậu quả đối với mục tiêu “app chỉ được EXECUTE” là gì?

### Bài 14 — search_path không tin cậy

Function:

~~~sql
SELECT available_units FROM inventory;
~~~

không khai báo SET search_path. Caller có quyền tạo temp table `inventory`.

**Câu hỏi:** tên relation có thể resolve sai như thế nào?

### Bài 15 — Khóa search_path

Viết function definition có:

~~~sql
SECURITY DEFINER
SET search_path = pg_catalog, sec389_private, pg_temp
~~~

**Câu hỏi:** vì sao các schemas phải được tin cậy? Vì sao pg_temp ở cuối?

### Bài 16 — pg_temp precedence

Nếu function không đưa `pg_temp` vào search_path, temporary schema có thể được tra ở đâu khi tìm relation/type names?

**Đáp án:** PostgreSQL có quy tắc tra temporary schema sớm khi nó không được chỉ định rõ; vì thế phải xét shadowing và đặt pg_temp cuối.

### Bài 17 — pg_temp và function lookup

**Câu hỏi:** temp schema có được PostgreSQL dùng theo cùng quy tắc khi tìm functions/operators như khi tìm relation/type không?

**Đáp án:** không; đây là một giới hạn quan trọng của search path resolution.

### Bài 18 — pg_catalog

Một function khai báo:

~~~sql
SET search_path = untrusted_schema, pg_catalog
~~~

**Câu hỏi:** vì sao đặt một schema cho untrusted roles CREATE trước pg_catalog có thể gây nguy hiểm?

### Bài 19 — Tên qualified

So:

~~~sql
SELECT available_units FROM inventory;
SELECT available_units FROM sec389_private.inventory;
~~~

**Câu hỏi:** cái nào dễ kiểm toán và khó bị table-name shadowing hơn? Cái nào vẫn cần quyền đúng?

### Bài 20 — Function/operator hijacking

Function có lời gọi `transform_input(p_sku)` không qualified, còn schema đứng trước có quyền CREATE cho khách hàng.

**Bài tập:** nêu khả năng resolve vào helper không mong muốn, và hai lớp bảo vệ: trusted search path + qualified helper/type resolution.

### Bài 21 — SQL injection qua nối text

Trong PL/pgSQL SECURITY DEFINER:

~~~sql
-- Sai:
-- EXECUTE 'SELECT ... WHERE sku = ''' || p_sku || '''';
~~~

**Bài tập:** giải thích vì sao prepared statement ở Java không tự bảo vệ câu SQL bị ghép text bên trong function.

### Bài 22 — EXECUTE USING

Viết lại:

~~~sql
EXECUTE 'SELECT available_units
         FROM sec389_private.inventory
         WHERE sku = $1 AND is_public = true'
INTO v_stock
USING p_sku;
~~~

**Câu hỏi:** vì sao `p_sku` không trở thành một đoạn cú pháp SQL?

### Bài 23 — Identifier và %I

Một function phải chọn giữa hai bảng cấu hình được review sẵn.

**Bài tập:** dùng allowlist table name, `format('%I.%I', schema, table)` cho identifier và `USING` cho value. Vì sao chỉ quote identifier chưa đủ nếu caller được chọn bảng bất kỳ?

### Bài 24 — Chọn schema theo tenant

Một ứng dụng có 200 tenant schemas, API cho phép người dùng truyền `p_schema` và chạy dynamic SQL bằng quyền owner.

**Bài tập:** xác định rủi ro cross-tenant và đề xuất cách an toàn hơn với một schema/tenant_id được authorization hoặc registry allowlist đáng tin.

### Bài 25 — Test temp shadow

Trong session lab, tạo `TEMP TABLE inventory` chứa row giả có available_units=999999, rồi gọi `get_available_stock('KB-001')`.

**Câu hỏi:** function an toàn phải trả số nào và tại sao?

**Đáp án:** 17 từ `sec389_private.inventory`; SQL dùng schema-qualified name và function-level trusted search path.

### Bài 26 — Thay đổi search_path caller

~~~sql
SET search_path = pg_temp, public;
SELECT sec389_api.get_available_stock('KB-001');
~~~

**Câu hỏi:** với function đã cố định search_path và qualified relation, kết quả có nên đổi không?

### Bài 27 — Cột giá vốn

Role `sec389_app` gọi function xem tồn kho thành công. Có thể suy ra role ấy có quyền đọc `cost_price` trực tiếp không?

**Đáp án:** không; EXECUTE trên function không cấp SELECT trên bảng và function owner cũng chưa được grant cột giá vốn.

### Bài 28 — Một SQL view có đủ thay function?

Nhu cầu chỉ là xuất danh sách SKU công khai với available_units.

**Bài tập:** so view được thiết kế với security semantics phù hợp, column-level GRANT, RLS và SECURITY DEFINER function; trường hợp nào mỗi công cụ phù hợp?

### Bài 29 — RLS table owner

Function owner cũng là owner bảng có RLS enabled nhưng không FORCE.

**Câu hỏi:** function có thể bypass RLS theo rule PostgreSQL không? Điều gì thay đổi nếu function owner là một role riêng chỉ có SELECT và phải chịu policy?

### Bài 30 — BYPASSRLS

Definer role được cấp `BYPASSRLS`. Vì sao đây là quyền có nguy cơ lớn khi function đọc dữ liệu nhiều tenants? `FORCE ROW LEVEL SECURITY` có khắc phục toàn bộ tình huống này không?

**Đáp án định hướng:** BYPASSRLS có tác động vượt row policies; FORCE không được xem là cách chống một role có BYPASSRLS/superuser.

### Bài 31 — current_user trong RLS policy

Một policy kiểm tra `resource_owner = current_user`. Bảng được truy vấn từ một function SECURITY DEFINER.

**Câu hỏi:** `current_user` trong câu SQL đó thường là effective role nào? Vì sao có thể sai với mục đích “hàng thuộc người gọi”?

### Bài 32 — Tenant input không đáng tin

Function nhận `p_tenant_id` rồi thực thi:

~~~sql
SELECT * FROM private.orders
WHERE tenant_id = p_tenant_id;
~~~

**Bài tập:** thêm bước xác minh caller thực sự được quyền xem tenant tương ứng. Vì sao việc caller chọn một UUID tenant không đủ làm bằng chứng authorization?

### Bài 33 — Connection pool và session identity

Một application dùng một database login role chung cho hàng nghìn HTTP users.

**Câu hỏi:** `session_user` trong definer function có phân biệt được tất cả HTTP users không? Nên chuyển context như thế nào để chống spoofing?

### Bài 34 — Custom GUC

Function dựa vào `current_setting('app.user_id')` để lọc dữ liệu, còn service role có thể gọi `set_config('app.user_id', ...)` với giá trị tùy ý.

**Bài tập:** phân tích rủi ro và tìm cơ chế xác minh user identity ở tầng đáng tin.

### Bài 35 — Default privileges

~~~sql
ALTER DEFAULT PRIVILEGES FOR ROLE sec389_fn_owner
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
~~~

**Câu hỏi:** có thu hồi quyền các functions đã tồn tại không? Nếu function được tạo bởi một deployment role khác không `SET ROLE`, default privileges của role nào mới áp dụng?

### Bài 36 — Overloading

Có:

~~~text
get_stock(text)
get_stock(integer)
get_stock(text, boolean DEFAULT true)
~~~

**Bài tập:** tại sao chỉ REVOKE một signature có thể chưa khóa tất cả API paths? Viết kế hoạch kiểm tra mọi overloads.

### Bài 37 — CREATE OR REPLACE

Team deploy `CREATE OR REPLACE FUNCTION` và nghĩ mọi EXECUTE grants cũ đã bị xóa.

**Câu hỏi:** nhận định đó có an toàn không? Metadata nào cần kiểm tra sau replace?

### Bài 38 — Đổi owner

~~~sql
ALTER FUNCTION sec389_api.get_available_stock(text)
OWNER TO some_powerful_owner;
~~~

**Bài tập:** vì sao đây là thay đổi mức bảo mật dù SQL body không đổi? Những quyền/RLS policies có thể bị ảnh hưởng thế nào?

### Bài 39 — Function đọc giá vốn qua output

Một definer function chạy đúng search_path nhưng trả cả `cost_price` trong JSON.

**Câu hỏi:** có còn được coi là an toàn không? Vì sao secure search_path không thể thay output minimization?

### Bài 40 — Truy vấn tốn tài nguyên

Role app được EXECUTE hàm chạy một `SELECT` nặng trên bảng 100 triệu rows, có thể gọi bất kỳ lúc nào.

**Bài tập:** đề xuất rate limit, input bounds, index, statement timeout, query monitoring và resource budgets.

### Bài 41 — SECURITY DEFINER trong trigger

Một audit trigger function là SECURITY DEFINER để ghi bảng audit mà caller không có INSERT.

**Câu hỏi:** owner, search_path, side effects, PII retention và rollback cần được kiểm tra thế nào?

### Bài 42 — Chuỗi helper functions

`api_fn` gọi `helper_fn`, helper lại UPDATE một bảng có trigger.

**Bài tập:** vẽ call graph và xác định role/permissions, views/trigger functions, RLS và side effects ở mỗi bước.

### Bài 43 — Lỗi trả thông tin nội bộ

Function báo `RAISE EXCEPTION 'cost for SKU X is ...'`.

**Câu hỏi:** dù resultset rỗng, thông tin có thể bị lộ qua đâu? Hãy thiết kế lỗi đã sanitize.

### Bài 44 — Negative test

Viết bộ test phải thất bại khi role app:

1. `SELECT * FROM sec389_private.inventory`;
2. `UPDATE` bảng private;
3. `CREATE FUNCTION` trong `sec389_api`;
4. Gọi một function nhạy cảm chưa được GRANT EXECUTE.

**Câu hỏi:** vì sao những test thất bại quan trọng như test thành công?

### Bài 45 — LEAKPROOF

Một developer đánh dấu definer function tự viết là `LEAKPROOF` để planner chạy nhanh hơn.

**Bài tập:** giải thích vì sao thuộc tính này liên quan tới bảo mật optimizer/RLS, đòi quyền cao và không nên được khai tùy tiện.

### Bài 46 — Volatility

`get_available_stock` phụ thuộc nội dung bảng có thể được UPDATE. Có nên đánh dấu `IMMUTABLE` để index/caching nhanh hơn không?

**Đáp án:** không; dữ liệu thay đổi theo thời gian. `STABLE` cho function đọc phù hợp ngữ nghĩa hơn trong lab.

### Bài 47 — Transaction rollback

Một definer function UPDATE private table, sau đó caller `ROLLBACK`.

**Câu hỏi:** dữ liệu đã được commit riêng vì owner có quyền cao chưa?

**Đáp án:** không; SQL bên trong function vẫn thuộc transaction của caller.

### Bài 48 — Security incident

Phát hiện một hàm SECURITY DEFINER có owner quyền rộng và EXECUTE cấp PUBLIC. Logs cho thấy nhiều lời gọi bất thường.

**Bài tập:** lập runbook gồm kiểm kê owner/ACL, tạm chặn EXECUTE được phê duyệt, xác định dữ liệu lộ, sửa search_path/SQL injection, test quyền thấp và theo dõi sau deploy.

### Bài 49 — Review một pull request

Một PR:

~~~sql
CREATE FUNCTION public.admin_query(p_sql text)
RETURNS SETOF text
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY EXECUTE p_sql;
END;
$$;
~~~

**Bài tập:** xác định vì sao đây là một privileged arbitrary-SQL endpoint nguy hiểm; đề xuất API functions có signature hẹp, query tĩnh và quyền hạn tối thiểu. Không deploy chức năng này.

### Bài 50 — Capstone: API đa tenant an toàn

Một ứng dụng SaaS muốn expose ba nghiệp vụ:

- Xem số tồn kho của sản phẩm được công bố.
- Reserve tồn kho cho một đơn đã được xác minh quyền.
- Xem thống kê tổng hợp của tenant hiện tại.

Dữ liệu có cột `cost_price` tuyệt đối không được lộ qua public API. Runtime dùng connection pool và có nhiều HTTP users chung một DB login role.

**Yêu cầu triển khai/tài liệu:**

1. Vẽ sơ đồ roles: data owner, read-function owner, write-function owner, app role.
2. Chỉ định private/API schemas, quyền CREATE/USAGE/EXECUTE và column-level grants.
3. Soạn function đọc dạng SECURITY DEFINER với trusted search path và schema-qualified table.
4. Đảm bảo CREATE+REVOKE PUBLIC+GRANT app là một migration atomic.
5. Thiết kế cơ chế tenant identity đã xác minh; không chỉ tin một `p_tenant_id`/GUC do caller đặt.
6. Rà RLS: owner có thể bypass hay phải chịu policy?
7. Dùng UPDATE có điều kiện chống tồn kho âm, đồng thời có idempotency key và authorization.
8. Không trả `cost_price` hay thông báo lỗi tiết lộ SKU bí mật.
9. Không chấp nhận table/function name arbitrary trong dynamic SQL.
10. Đề xuất positive/negative tests cho tenant A/B, temp shadowing, schema injection, retry và pooled connections.
11. Ghi rõ các quyền mà mỗi owner role **không có**.
12. Lập kế hoạch logs, monitoring, rate limit, migration rollback và phản ứng sự cố.

**Tiêu chí đạt:** người học phải giải thích được **ai gọi hàm, hàm thực thi với quyền ai, đối tượng nào được truy cập qua tên nào, tại sao caller không thể điều khiển SQL vượt hợp đồng, và tại sao kết quả không thể lộ dữ liệu ngoài quyền**.

## 31. Checklist an toàn cho mỗi SECURITY DEFINER function

### 31.1. Có thật sự cần nâng quyền?

- [ ] Chức năng không thể đáp ứng rõ ràng hơn bằng SECURITY INVOKER, GRANT theo cột, view hoặc RLS.
- [ ] Có mô tả hợp đồng input/output, side effects và điều kiện authorization.
- [ ] Chỉ những tác vụ cần quyền đặc biệt mới nằm trong function.
- [ ] Không biến function thành arbitrary SQL executor hoặc general admin proxy.

### 31.2. Role và ACL

- [ ] Function owner là role chuyên dụng, không SUPERUSER.
- [ ] Function owner không có BYPASSRLS/CREATEROLE/CREATEDB nếu không có yêu cầu đã được review.
- [ ] Owner không tự động sở hữu mọi bảng nhạy cảm; đã cân nhắc tách data owner.
- [ ] Owner chỉ có quyền SELECT/UPDATE trên những cột/tables cần thiết.
- [ ] Đã kiểm tra inherited role memberships, không chỉ direct grants.
- [ ] Runtime role không được quyền SET ROLE thành definer owner.
- [ ] Runtime role không có CREATE trên trusted schema.
- [ ] PUBLIC EXECUTE đã được REVOKE.
- [ ] GRANT EXECUTE cho đúng role và đúng function signature/overloads.
- [ ] CREATE/ALTER và REVOKE/GRANT được triển khai không mở cửa sổ thiếu an toàn.
- [ ] Có kiểm tra ALTER DEFAULT PRIVILEGES theo đúng role thực sự tạo functions.

### 31.3. Name resolution

- [ ] Có `SET search_path` tin cậy trên function.
- [ ] `pg_catalog` đứng trước untrusted schemas; tốt nhất explicit ở đầu.
- [ ] `pg_temp` được liệt kê cuối theo mô hình an toàn.
- [ ] Không có schema client được CREATE trong search path tin cậy.
- [ ] Các tables/functions quan trọng được schema-qualified.
- [ ] Không có untrusted function/operator shadowing hoặc dependency bất ngờ.
- [ ] Đã kiểm tra temp table shadowing ở môi trường test.
- [ ] Extension/helper schemas có owner/grants an toàn.

### 31.4. Input và dynamic SQL

- [ ] Giá trị input không được nối trực tiếp thành SQL.
- [ ] Dùng static SQL hoặc `EXECUTE ... USING`.
- [ ] Dynamic identifiers dùng `format('%I', ...)`/identifier quoting.
- [ ] Identifiers còn phải qua allowlist, không chỉ quote.
- [ ] Đã kiểm tra NULL, empty text, độ dài, số lượng, kiểu dữ liệu.
- [ ] User/tenant/resource identity được xác minh ở nguồn đáng tin.
- [ ] Không dùng arbitrary custom GUC hoặc client-provided tenant_id như bằng chứng quyền.

### 31.5. RLS, output và side effects

- [ ] Hiểu policy RLS thực thi dưới effective role nào.
- [ ] Đã kiểm tra owner/table-owner bypass và BYPASSRLS.
- [ ] Không dựa vào `current_user` như identity HTTP user khi đang ở SECURITY DEFINER.
- [ ] Kết quả không chứa cột/row ngoài hợp đồng.
- [ ] Lỗi không tiết lộ dữ liệu nhạy cảm hoặc sự tồn tại của tài nguyên bị cấm.
- [ ] Logging/NOTICE đã sanitize PII/secrets.
- [ ] Không dùng external side effects trực tiếp nếu cần đảm bảo after-commit.
- [ ] Đã kiểm soát function/helper/trigger call graph.
- [ ] Đã khai đúng volatility/parallel safety, không LEAKPROOF tùy ý.

### 31.6. Vận hành

- [ ] Có positive test cho role app được phép.
- [ ] Có negative tests cho role không được phép và tenant khác.
- [ ] Có kiểm thử sau đổi owner, grants, overloads, schema hoặc RLS policy.
- [ ] Có quản lý phiên bản/migration rollback.
- [ ] Có quan sát error/latency/abuse và quyền audit data.
- [ ] Có rate limit/query budget khi function được gọi từ API công khai.
- [ ] Có quy trình phản ứng nếu definer function bị khai thác.

## 32. Câu hỏi thường gặp

### 32.1. SECURITY DEFINER có cho caller SELECT thẳng bảng không?

Không. Người gọi có thể `EXECUTE` một function sử dụng quyền owner, nhưng không tự được `SELECT` bảng. Nếu function được viết để trả toàn bộ dữ liệu, nó vẫn có thể **làm lộ dữ liệu qua output**, nên phải giới hạn kết quả.

### 32.2. Tại sao tôi đã REVOKE SELECT bảng mà application vẫn xem được stock?

Vì function SECURITY DEFINER đọc bảng bằng quyền owner, và role application vẫn có EXECUTE trên function ấy. Đây có thể là hành vi API được thiết kế đúng, không mặc định là lỗi.

### 32.3. PUBLIC có phải schema public không?

Không. `PUBLIC` trong GRANT/REVOKE là tập mọi roles; schema `public` là một namespace object cụ thể trong database.

### 32.4. REVOKE EXECUTE FROM PUBLIC rồi có cần GRANT USAGE schema không?

Có nếu caller muốn resolve/gọi function trong schema. Nhưng hai grants độc lập: `USAGE` schema không cấp `EXECUTE` function, và `EXECUTE` function không tự cấp quyền đọc bảng nội bộ.

### 32.5. Chỉ cần SET search_path an toàn là đủ?

Không. Cần kiểm tra owner privileges, dynamic SQL, caller authorization, RLS, output/error, helper functions và quyền EXECUTE. Secure search_path là **một lớp** phòng thủ.

### 32.6. Vì sao pg_temp phải nằm cuối?

Khi temporary schema không được liệt kê, PostgreSQL có thể tra nó sớm khi resolve relations/types. Ghi `pg_temp` cuối làm giảm nguy cơ temporary table/type shadow trusted objects.

### 32.7. SQL dynamic dùng %I đã chống được mọi tấn công?

Không. `%I` giúp quote tên identifier để không phá cú pháp; caller vẫn có thể yêu cầu một **identifier hợp lệ nhưng không được phép truy cập**. Cần allowlist/authorization và bind values bằng `USING`.

### 32.8. Có nên dùng SESSION_USER làm user_id?

Chỉ khi nó thật sự phản ánh một identity đáng tin theo kiến trúc của bạn. Với connection pool dùng một DB login role chung, `session_user` không phân biệt các HTTP users.

### 32.9. SECURITY DEFINER luôn bypass RLS không?

Không. RLS phụ thuộc effective role, table owner, policy và BYPASSRLS/SUPERUSER. Definer function có thể tuân RLS hoặc bypass tùy các điều kiện ấy.

### 32.10. Hàm có thể tự COMMIT để audit sống sót khi caller ROLLBACK không?

Không. Function không có transaction control như procedure trong bối cảnh cho phép; các writes của function thuộc transaction caller. Muốn audit attempts bị rollback cần logging ngoài transaction hoặc cơ chế phù hợp.

### 32.11. Nếu đổi owner function, có cần test lại không?

Có. SECURITY DEFINER sử dụng quyền của owner mới, có thể làm thay đổi dữ liệu nhìn thấy, RLS hoặc các side effects.

### 32.12. Có thể đặt SECURITY DEFINER trên mọi function cho tiện không?

Không nên. Mỗi definer function là một điểm nâng quyền, cần threat model, giới hạn grants, secure search_path và regression tests. Dùng SECURITY INVOKER mặc định khi không cần nâng quyền.

### 32.13. Vì sao cần test role quyền thấp thay vì chỉ test bằng DBA?

DBA có thể xem/sửa mọi thứ, làm cho code thiếu privileges hoặc lộ dữ liệu không bị phát hiện. Test bằng actual caller role xác minh rằng API được phép hoạt động **và** những thao tác ngoài hợp đồng bị chặn.

### 32.14. Nên đặt function trong schema public không?

Function có thể tồn tại trong nhiều schemas, nhưng privileged API thường nên đặt trong **schema riêng được bảo vệ**, cấp USAGE/EXECUTE có chọn lọc. Trạng thái quyền CREATE mặc định của schema public phụ thuộc version/ACL lịch sử.

### 32.15. Làm sao biết function mới có EXECUTE cho PUBLIC?

Xem `pg_proc.proacl`/`aclexplode` kết hợp default ACL và thử bằng một role không được grant. Đừng suy ra `proacl IS NULL` nghĩa không ai có quyền.

## 33. Tài liệu PostgreSQL chính thức

Khi triển khai, chọn tài liệu **đúng major version** PostgreSQL đang dùng; các ví dụ dưới đây trỏ tới tài liệu hiện hành:

- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html): `SECURITY INVOKER`/`SECURITY DEFINER`, function-level `SET`, volatility, parallel, leakproof, cost và quyền.
- [Writing SECURITY DEFINER Functions Safely](https://www.postgresql.org/docs/current/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY): trusted `search_path`, `pg_temp` cuối và tạo/revoke cùng transaction.
- [GRANT](https://www.postgresql.org/docs/current/sql-grant.html): quyền EXECUTE, USAGE/CREATE schema, quyền bảng và cột.
- [REVOKE](https://www.postgresql.org/docs/current/sql-revoke.html): thu hồi quyền từ PUBLIC và roles cụ thể.
- [ALTER DEFAULT PRIVILEGES](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html): default EXECUTE cho future functions và phạm vi role/schema.
- [ALTER FUNCTION](https://www.postgresql.org/docs/current/sql-alterfunction.html): chuyển owner, thay security mode và function SET configuration.
- [Role Attributes](https://www.postgresql.org/docs/current/role-attributes.html): LOGIN, SUPERUSER, BYPASSRLS và các role capabilities.
- [Role Membership](https://www.postgresql.org/docs/current/role-membership.html): inherited grants, SET ROLE và membership options.
- [Role System](https://www.postgresql.org/docs/current/user-manag.html): tạo/kiểm soát roles và ownership.
- [Schemas](https://www.postgresql.org/docs/current/ddl-schemas.html): search_path, namespace privileges và object-name resolution.
- [Function Security](https://www.postgresql.org/docs/current/perm-functions.html): kiểm soát functions không tin cậy và an toàn nâng quyền.
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): RLS, policy role context, table owner và FORCE ROW LEVEL SECURITY.
- [PL/pgSQL EXECUTE](https://www.postgresql.org/docs/current/plpgsql-statements.html#PLPGSQL-STATEMENTS-EXECUTING-DYN): parameterization `USING`, identifiers và SQL dynamic.
- [String Functions and format](https://www.postgresql.org/docs/current/functions-string.html): `format('%I', ...)` và `format('%L', ...)`.
- [SET ROLE](https://www.postgresql.org/docs/current/sql-set-role.html): thay effective role trong session.
- [System Information Functions](https://www.postgresql.org/docs/current/functions-info.html): `current_user`, `session_user` và các privilege-checking functions.
- [System Catalog pg_proc](https://www.postgresql.org/docs/current/catalog-pg-proc.html): owner, `prosecdef`, `proconfig` và `proacl`.
- [System Catalog pg_namespace](https://www.postgresql.org/docs/current/catalog-pg-namespace.html): schema owners/ACL.
- [System Catalog pg_roles](https://www.postgresql.org/docs/current/view-pg-roles.html): role metadata không chứa mật khẩu.
- [Function Volatility Categories](https://www.postgresql.org/docs/current/xfunc-volatility.html): STABLE/VOLATILE/IMMUTABLE đúng ngữ nghĩa.
- [CREATE VIEW](https://www.postgresql.org/docs/current/sql-createview.html): security invoker/barrier và view rights theo version.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity` và các nguồn quan sát.

## 34. Tổng kết

**`SECURITY DEFINER`** cho phép một PostgreSQL function chạy với **quyền của owner**, thay vì chỉ quyền của caller. Đây là công cụ mạnh để tạo API giới hạn trên dữ liệu nội bộ, nhưng cũng tạo **điểm nâng quyền** cần được review như mọi interface có đặc quyền.

Ba lớp bảo vệ không thể thiếu:

1. **Owner quyền tối thiểu:** dùng role chuyên dụng, tránh superuser/BYPASSRLS/quyền bảng quá rộng; tách data owner khỏi function owner khi có thể.
2. **Phân giải tên an toàn:** đặt trusted `search_path`, `pg_catalog` rõ ràng, `pg_temp` cuối, schema-qualified objects quan trọng, và tránh dynamic SQL từ input không đáng tin.
3. **Quyền gọi có chọn lọc:** nhớ default `PUBLIC EXECUTE` cho functions, tạo/revoke/grant **trong cùng transaction**, chỉ cho đúng role và signature được phép.

Các lớp khác quyết định function có thật sự bảo mật hay không: authorization theo tenant/caller identity đã được xác minh; RLS effective-role behavior; output/error minimization; SQL injection protection bằng static SQL hoặc `EXECUTE ... USING`; kiểm soát role membership, views/helpers/triggers và external side effects; cùng positive/negative tests dưới role quyền thấp.

Cuối cùng, **nâng quyền không đồng nghĩa có transaction độc lập**. Những writes của SECURITY DEFINER function vẫn thuộc transaction caller; rollback có thể hủy chúng. Khi một function được thiết kế đúng, app chỉ nhận được capability cụ thể đã cấp — không phải một "vé" đọc hay sửa tùy ý mọi dữ liệu của owner. Đó là nguyên tắc cốt lõi để sử dụng SECURITY DEFINER an toàn trong PostgreSQL.
