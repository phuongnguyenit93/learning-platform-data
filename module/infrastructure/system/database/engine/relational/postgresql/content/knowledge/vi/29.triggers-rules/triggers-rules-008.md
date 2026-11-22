# Event trigger cho thay đổi DDL trong PostgreSQL

## 1. Khi cần theo dõi hoặc kiểm soát thay đổi cấu trúc database

Một hệ thống PostgreSQL có nhiều nhóm cùng triển khai thay đổi schema. Quản trị viên cần biết:

- Ai đã tạo một bảng hoặc index mới?
- Khi nào một bảng bị đổi tên, thêm cột hoặc đổi kiểu dữ liệu?
- Lệnh `DROP TABLE ... CASCADE` đã kéo theo những đối tượng nào?
- Thay đổi `ALTER TABLE` nào khiến bảng phải **rewrite** toàn bộ dữ liệu?
- Có thể chặn một số thao tác DDL nguy hiểm theo chính sách vận hành không?

**Trigger thông thường trên bảng** không giải quyết trực tiếp các câu hỏi này. Nó gắn với dữ liệu của một bảng, phát sinh khi có các thao tác như `INSERT`, `UPDATE`, `DELETE` hoặc `TRUNCATE`.

**Event trigger** là cơ chế khác của PostgreSQL, được gọi khi **những loại lệnh DDL được hỗ trợ** xảy ra trong database, ví dụ tạo bảng, sửa bảng hoặc xóa đối tượng.

```text
                       PostgreSQL session
                               |
                          DDL command
                               |
                      +--------+---------+
                      |                  |
              ddl_command_start      Kiểm tra/chạy DDL
                      |                  |
             Chặn hoặc kiểm tra          |
                      |                  |
                      +--------+---------+
                               |
                     Object catalog thay đổi
                               |
               +---------------+---------------+
               |                               |
           sql_drop                       table_rewrite
       (nếu có xóa object)           (nếu có rewrite bảng)
               |                               |
               +---------------+---------------+
                               |
                        ddl_command_end
                               |
                   Transaction COMMIT / ROLLBACK
```

Sơ đồ giúp hình dung **các điểm hook** chứ không mô tả một trình tự bắt buộc cho mọi lệnh. Ví dụ, `table_rewrite` xảy ra **trước khi bảng được rewrite**, trong quá trình thực thi DDL, chứ không phải sau khi mọi thay đổi đã xong. `sql_drop` xảy ra khi PostgreSQL đã loại các đối tượng khỏi system catalogs trong transaction tương ứng. Một lệnh DDL có thể không phát sinh đủ bốn loại sự kiện.

> **Ý chính:** event trigger hữu ích để giám sát, áp quy ước và thu thập metadata về các thay đổi DDL, nhưng nó chạy **trong transaction của lệnh DDL**. Ghi log vào bảng qua event trigger thường bị rollback cùng lệnh khi transaction thất bại; nó không thay thế audit logs độc lập, phân quyền và quy trình migration.

## 2. Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt event trigger và table trigger.
2. Liệt kê bốn loại sự kiện `ddl_command_start`, `ddl_command_end`, `sql_drop` và `table_rewrite`.
3. Giải thích thời điểm mỗi sự kiện được phát ra.
4. Viết hàm `RETURNS event_trigger` trong PL/pgSQL.
5. Sử dụng `TG_EVENT` và `TG_TAG` đúng ngữ cảnh.
6. Tạo trigger bằng `CREATE EVENT TRIGGER ... ON ... EXECUTE FUNCTION`.
7. Lọc theo command tag bằng `WHEN TAG IN (...)` khi sự kiện hỗ trợ.
8. Dùng `pg_event_trigger_ddl_commands()` thu thập các đối tượng của lệnh DDL.
9. Dùng `pg_event_trigger_dropped_objects()` nhận diện các đối tượng bị xóa, gồm hiệu ứng `CASCADE`.
10. Dùng `pg_event_trigger_table_rewrite_oid()` và `pg_event_trigger_table_rewrite_reason()` khi bảng rewrite.
11. Hiểu vì sao `ddl_command_start` không có đủ metadata “đã được tạo”.
12. Biết phạm vi database-level của event triggers và những lệnh DDL không được bao phủ.
13. Thiết kế bảng audit DDL và biết các giới hạn về rollback, actor identity và độ bền.
14. Chặn một số lệnh DDL trong một môi trường được kiểm soát.
15. Không tạo recursion hoặc khóa vận hành vì DDL bên trong event trigger.
16. Hiểu quyền tạo event trigger và quyền của handler function.
17. Dùng `SECURITY INVOKER`, `SECURITY DEFINER` và `search_path` an toàn.
18. Đọc catalog `pg_event_trigger` để kiểm kê trạng thái, owner và tag filters.
19. Bật/tắt event trigger bằng `ALTER EVENT TRIGGER` theo quyền thích hợp.
20. Kiểm thử một migration có `CREATE`, `ALTER`, `DROP`, `CASCADE` và rollback.
21. Phân biệt quan sát cấu trúc DDL với capture chính xác câu SQL gốc.
22. Đánh giá chi phí và rủi ro khi event triggers được cài trên database production.
23. Xây checklist vận hành, kiểm thử và khôi phục khi handler bị lỗi.

## 3. Event trigger khác trigger dữ liệu như thế nào?

| Tiêu chí | Table trigger | Event trigger |
| --- | --- | --- |
| Mục đích chính | Phản ứng với thao tác dữ liệu trên bảng | Phản ứng với những lệnh DDL được hỗ trợ |
| Cấp gắn | Một bảng, view hoặc đối tượng hỗ trợ tương ứng | Database hiện tại |
| Câu lệnh tạo | `CREATE TRIGGER` | `CREATE EVENT TRIGGER` |
| Hàm trả về | `trigger` | `event_trigger` |
| Sự kiện điển hình | `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE` | `ddl_command_start`, `ddl_command_end`, `sql_drop`, `table_rewrite` |
| Thông tin ngữ cảnh | `NEW`, `OLD`, `TG_OP`, ... theo loại | `TG_EVENT`, `TG_TAG` và event-trigger helper functions |
| Quyền tạo | Theo privilege model của table/trigger | `CREATE EVENT TRIGGER` yêu cầu superuser theo PostgreSQL |
| Phạm vi ảnh hưởng | Table/view gắn trigger | Các DDL được hỗ trợ trong cùng database |
| Dùng để audit thay đổi bảng? | Audit row changes | Audit schema changes |
| Có thể chặn thao tác? | Có thể raise exception trong ngữ cảnh phù hợp | Có thể raise exception để từ chối DDL |

### 3.1. Ví dụ table trigger không phải DDL event trigger

```sql
CREATE TRIGGER audit_order_updates
AFTER UPDATE ON some_schema.orders
FOR EACH ROW
EXECUTE FUNCTION some_schema.audit_row();
```

Nó quan sát `UPDATE` dữ liệu của bảng `orders`, không quan sát `ALTER TABLE orders`.

### 3.2. Ví dụ event trigger

```sql
CREATE EVENT TRIGGER log_schema_changes
ON ddl_command_end
EXECUTE FUNCTION admin_schema.log_ddl();
```

Nó không thuộc riêng một bảng `orders`. Trong database hiện tại, handler có thể được gọi khi một lệnh DDL được event trigger hỗ trợ hoàn tất.

### 3.3. Không phải mọi thao tác “trông giống quản trị” đều là event được hỗ trợ

`VACUUM`, `ANALYZE`, giao dịch DML và nhiều lệnh khác không trở thành `ddl_command_end` chỉ vì chúng có tác động vận hành. Event trigger có phạm vi command tags được PostgreSQL hỗ trợ; cần kiểm tra phiên bản và danh sách tags khi thiết kế.

## 4. Bốn loại sự kiện quan trọng

| Event | Thời điểm khái quát | Hàm hỗ trợ đặc trưng | Ví dụ sử dụng |
| --- | --- | --- | --- |
| `ddl_command_start` | Trước khi chạy DDL được hỗ trợ | `TG_TAG` | Kiểm tra/chặn loại DDL |
| `ddl_command_end` | Sau khi phần DDL hoàn thành, trước transaction commit | `pg_event_trigger_ddl_commands()` | Audit objects tạo/sửa |
| `sql_drop` | Khi objects đã bị loại khỏi system catalogs trong transaction | `pg_event_trigger_dropped_objects()` | Audit DROP và phụ thuộc CASCADE |
| `table_rewrite` | Ngay trước một thao tác rewrite bảng cần thiết cho DDL | `pg_event_trigger_table_rewrite_oid()`, `pg_event_trigger_table_rewrite_reason()` | Phát hiện các thay đổi bảng có thể tốn I/O/lock |

### 4.1. `ddl_command_start`

Sự kiện xảy ra trước phần thực thi DDL. Nó thích hợp để từ chối một **command tag** hoặc kiểm tra các điều kiện có thể biết ở thời điểm đầu.

Đừng kỳ vọng truy vấn metadata của object mới đã tạo tại đây; object có thể chưa tồn tại.

### 4.2. `ddl_command_end`

Sự kiện xảy ra sau khi lệnh DDL đã thực hiện xong trong transaction, trước commit cuối cùng. Các thay đổi catalog của lệnh có thể quan sát được từ transaction này.

Nếu handler gặp exception và exception không được xử lý, DDL đang thực hiện có thể bị rollback.

### 4.3. `sql_drop`

Sự kiện được dùng cho thông tin xóa object trong DDL. Vì các objects đã bị loại khỏi catalogs tại điểm này, không nên chỉ query `pg_class` để lấy mọi đối tượng đã drop. PostgreSQL cung cấp tập metadata riêng qua `pg_event_trigger_dropped_objects()`.

### 4.4. `table_rewrite`

Một số lệnh `ALTER TABLE` phải rewrite dữ liệu vật lý của bảng. Event này xảy ra trước rewrite và cung cấp OID bảng cùng reason bitmask. Không phải **mọi** `ALTER TABLE` đều rewrite.

## 5. Chuẩn bị môi trường lab và các điều kiện tiên quyết

**Cảnh báo:** event trigger là hook ở cấp database và có thể ảnh hưởng mọi migration trong database đó. Chỉ chạy lab trong **database thử nghiệm riêng**, không cài vào production tùy tiện.

### 5.1. Quyền tạo event trigger

PostgreSQL yêu cầu **superuser** để tạo event trigger. Managed PostgreSQL có thể giới hạn khả năng này hoặc cung cấp cơ chế/quyền thay thế qua nhà cung cấp; không nên giả định role ứng dụng có thể chạy lệnh.

Các ví dụ DDL dưới đây giả định bạn là administrator trong một database lab, có quyền:

- `CREATE SCHEMA`/`CREATE TABLE`/`CREATE FUNCTION`.
- `CREATE EVENT TRIGGER`.
- Quản lý event triggers khi muốn `ENABLE`/`DISABLE`/`DROP`.
- Truy cập các bảng lab.

### 5.2. Schema và bảng audit

```sql
CREATE SCHEMA IF NOT EXISTS et_lab;

CREATE TABLE et_lab.ddl_audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    happened_at timestamptz NOT NULL
        DEFAULT clock_timestamp(),
    transaction_id bigint NOT NULL
        DEFAULT txid_current(),
    event_name text NOT NULL,
    command_tag text NOT NULL,
    effective_role name NOT NULL
        DEFAULT current_user,
    session_login name NOT NULL
        DEFAULT session_user,
    object_type text,
    schema_name text,
    object_identity text,
    in_extension boolean,
    original_drop boolean,
    normal_drop boolean,
    is_temporary boolean,
    rewrite_reason integer,
    details text
);
```

Dữ liệu audit gồm:

- Thời điểm quan sát.
- ID transaction ghi record.
- Loại event và command tag.
- PostgreSQL role đang có hiệu lực cùng login role của session.
- Loại object, schema, identity string.
- Metadata riêng cho extension/drop/rewrite.

### 5.3. Vì sao lưu cả current_user và session_user?

`CURRENT_USER` phản ánh effective role tại nơi biểu thức được đánh giá. `SESSION_USER` thường phản ánh DB login ban đầu của connection, không tự đổi bởi `SET ROLE`.

Nhưng với `SECURITY DEFINER` function, `CURRENT_USER` bên trong là **owner của function**, không phải role đã phát lệnh DDL. Nếu ứng dụng dùng một login chung cho toàn bộ users, `SESSION_USER` cũng không phân biệt người dùng web.

**Hai cột này hỗ trợ điều tra**, không tự chứng minh identity của người dùng ứng dụng cuối cùng.

### 5.4. Vì sao bảng audit cần có trước event trigger?

Một khi event trigger đã được bật, việc tạo bảng khác cũng có thể gọi handler. Nếu handler INSERT vào audit table **chưa tồn tại**, lệnh DDL sẽ lỗi.

Tạo schema, audit table và function **trước khi** tạo event trigger chính là thứ tự triển khai thuận lợi.

## 6. Viết hàm xử lý `ddl_command_end`

Event trigger handler là một function:

- Không có tham số khai báo thông thường.
- Có kiểu trả về `event_trigger`.
- Được PostgreSQL gọi ở ngữ cảnh sự kiện tương ứng.
- Có thể dùng `TG_EVENT` và `TG_TAG` trong PL/pgSQL.

### 6.1. Hàm ghi metadata DDL

```sql
CREATE OR REPLACE FUNCTION et_lab.capture_ddl_end()
RETURNS event_trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, et_lab, pg_temp
AS $fn$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT *
        FROM pg_catalog.pg_event_trigger_ddl_commands()
    LOOP
        INSERT INTO et_lab.ddl_audit (
            event_name,
            command_tag,
            object_type,
            schema_name,
            object_identity,
            in_extension,
            details
        )
        VALUES (
            TG_EVENT,
            r.command_tag,
            r.object_type,
            r.schema_name,
            r.object_identity,
            r.in_extension,
            'ddl_command_end'
        );
    END LOOP;
END;
$fn$;
```

Giải thích:

1. `RETURNS event_trigger` xác định đúng loại handler.
2. `TG_EVENT` phản ánh loại sự kiện hiện tại, ở đây là `ddl_command_end`.
3. `TG_TAG` cũng có sẵn và chứa command tag; ví dụ dùng `r.command_tag` theo từng record vì một lệnh có thể cung cấp nhiều rows metadata.
4. `pg_event_trigger_ddl_commands()` trả danh sách những DDL commands/objects PostgreSQL ghi nhận trong event hiện tại.
5. Mỗi row được lưu vào bảng audit.
6. `SECURITY INVOKER` dùng quyền role thực hiện DDL trong ví dụ lab.
7. `SET search_path` và fully qualified table/function names giúp kiểm soát phân giải tên object.

### 6.2. Tại sao dùng vòng FOR thay vì SELECT INTO một row?

Một lệnh DDL có thể phát sinh **nhiều command records hoặc objects**. Giả định “mỗi statement luôn đúng một row metadata” dễ dẫn đến mất dữ liệu audit.

### 6.3. `pg_event_trigger_ddl_commands()` chỉ dùng đúng ngữ cảnh

Hàm hệ thống này dành cho event handler của `ddl_command_end`. Không dùng như một API bất kỳ:

```sql
-- Không phải lời gọi standalone để lấy lịch sử DDL:
SELECT * FROM pg_event_trigger_ddl_commands();
```

Nó truy cập thông tin **sự kiện đang xử lý**, không phải bảng history toàn database.

### 6.4. Vì sao handler chưa cần SECURITY DEFINER?

Lab giả định administrator đang tạo và thử DDL có quyền `INSERT` vào `et_lab.ddl_audit`.

Nếu nhiều role khác nhau cùng tạo DDL, `SECURITY INVOKER` handler có thể gặp lỗi vì role đó thiếu quyền ghi audit. Chúng ta sẽ thiết kế phương án production với owner role chuyên biệt ở phần bảo mật; không vội bật superuser SECURITY DEFINER.

## 7. Tạo event trigger theo command tag

```sql
CREATE EVENT TRIGGER et_lab_on_ddl_end
ON ddl_command_end
WHEN TAG IN (
    'CREATE TABLE',
    'ALTER TABLE',
    'CREATE INDEX',
    'CREATE VIEW'
)
EXECUTE FUNCTION et_lab.capture_ddl_end();
```

### 7.1. Tên event trigger

`et_lab_on_ddl_end` là tên event trigger trong database, **không phải đối tượng schema-qualified** kiểu `et_lab.et_lab_on_ddl_end`.

Handler function mới nằm trong schema `et_lab`.

### 7.2. `WHEN TAG IN (...)`

Chỉ những command tags được khai báo và được PostgreSQL hỗ trợ sẽ gọi trigger tương ứng. Đây là bộ lọc theo **command type**, không phải theo bảng cụ thể.

Ví dụ, `CREATE TABLE et_lab.samples` phù hợp tag `CREATE TABLE`, còn `CREATE FUNCTION ...` không nằm trong danh sách.

### 7.3. Khi muốn audit mọi DDL được hỗ trợ

Có thể bỏ `WHEN TAG IN`:

```sql
CREATE EVENT TRIGGER et_lab_on_ddl_end_all
ON ddl_command_end
EXECUTE FUNCTION et_lab.capture_ddl_end();
```

**Đây là một phương án thay thế, không nên tạo thêm cùng trigger đã có nếu muốn tránh ghi trùng.** Ngoài ra, bỏ filter cũng không có nghĩa PostgreSQL hỗ trợ mọi command tag có thể tồn tại.

### 7.4. Command tag là giá trị xác định

`'CREATE TABLE'` là tag khác với `'ALTER TABLE'`. Nếu code theo dõi `'CREATE TABLE'`, một `CREATE TABLE AS` có thể có command tag riêng, tùy lệnh/phiên bản. Hãy xác minh tag thực tế và tập tag hỗ trợ khi cần coverage chính xác.

## 8. Thực hành ghi nhận CREATE và ALTER

Sau khi tạo handler và event trigger:

```sql
CREATE TABLE et_lab.samples (
    sample_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL
);

ALTER TABLE et_lab.samples
ADD COLUMN notes text;

CREATE INDEX samples_title_idx
ON et_lab.samples (title);
```

Tất cả đều có khả năng được ghi nhận bởi trigger `ddl_command_end` ở trên.

### 8.1. Đọc bảng audit

```sql
SELECT
    audit_id,
    happened_at,
    event_name,
    command_tag,
    object_type,
    schema_name,
    object_identity,
    in_extension
FROM et_lab.ddl_audit
ORDER BY audit_id;
```

Kết quả sẽ tùy phiên bản/lệnh, nhưng bạn nên quan sát các records liên quan đến bảng `et_lab.samples` và index `samples_title_idx`.

### 8.2. Không đồng nhất audit rows với số DDL statements

Một DDL statement có thể sinh ra nhiều objects/command records; một số hành vi DDL được hệ thống xử lý theo cách khác hoặc không được event trigger hỗ trợ.

Do đó:

```sql
SELECT COUNT(*)
FROM et_lab.ddl_audit;
```

không nhất thiết bằng số câu `CREATE`/`ALTER` user đã gõ.

### 8.3. `object_identity` là văn bản mô tả object

Giá trị này hữu ích để hiển thị trong báo cáo audit. Không coi nó là một SQL identifier đơn an toàn để tự ghép trực tiếp vào câu SQL động sau đó.

### 8.4. `in_extension`

Cờ `in_extension` chỉ ra command được thực thi trong context extension script theo metadata PostgreSQL. Nó giúp phân biệt object tạo bởi migration trực tiếp và object được tạo như một phần cài/upgrade extension trong những trường hợp được ghi nhận.

## 9. Metadata của `pg_event_trigger_ddl_commands()`

Hàm thường cung cấp các trường quan trọng:

| Trường | Ý nghĩa |
| --- | --- |
| `classid` | OID catalog chứa object |
| `objid` | OID object |
| `objsubid` | Sub-object ID, ví dụ thuộc tính cột trong một số trường hợp |
| `command_tag` | Tag của DDL command |
| `object_type` | Loại object |
| `schema_name` | Schema nếu có, có thể NULL |
| `object_identity` | Text mô tả identity của object |
| `in_extension` | Có được chạy trong extension script context không |
| `command` | Internal `pg_ddl_command` representation |

### 9.1. Không cố in nguyên `command` như SQL gốc

Trường `command` là internal representation với kiểu `pg_ddl_command`, **không phải một cột text chứa nguyên câu SQL người dùng đã chạy**.

Nếu cần lưu chính xác SQL text, nhiều yếu tố khác phải được cân nhắc, như PostgreSQL logs, pgAudit hoặc hệ thống migration. Event trigger không tự cung cấp một bản copy câu SQL gốc cho mọi lệnh.

### 9.2. Catalog OID không phải identifier bền vĩnh viễn

`objid`/`classid` hữu ích để tham chiếu object/catalog ở thời điểm event. Sau khi object bị xóa/tạo lại hoặc trên database khác, OID có thể không còn mô tả cùng object.

Để lưu history, nên giữ cả `object_identity` và các thuộc tính nghiệp vụ bổ sung được phép ghi.

### 9.3. Schema_name có thể NULL

Không phải mọi object được ghi nhận đều nằm trong một schema theo cách table/view thông thường. Không tự thêm `NOT NULL` lên cột audit schema_name.

### 9.4. DDL ghi lại không đồng nghĩa đã commit

Handler chạy trong transaction. Nếu transaction bị rollback sau đó, cả thay đổi catalog lẫn row audit do handler INSERT thường bị rollback.

## 10. Ghi nhận DROP bằng sự kiện `sql_drop`

`ddl_command_end` thích hợp cho metadata sau tạo/sửa object. Khi đối tượng bị drop, metadata một số objects đã không còn trong system catalogs ở thời điểm `sql_drop`.

PostgreSQL cung cấp `pg_event_trigger_dropped_objects()` để liệt kê objects đã bị xóa trong lệnh DDL được hỗ trợ.

### 10.1. Hàm xử lý DROP

```sql
CREATE OR REPLACE FUNCTION et_lab.capture_sql_drop()
RETURNS event_trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, et_lab, pg_temp
AS $fn$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT *
        FROM pg_catalog.pg_event_trigger_dropped_objects()
    LOOP
        INSERT INTO et_lab.ddl_audit (
            event_name,
            command_tag,
            object_type,
            schema_name,
            object_identity,
            original_drop,
            normal_drop,
            is_temporary,
            details
        )
        VALUES (
            TG_EVENT,
            TG_TAG,
            r.object_type,
            r.schema_name,
            r.object_identity,
            r.original,
            r.normal,
            r.is_temporary,
            'sql_drop'
        );
    END LOOP;
END;
$fn$;
```

### 10.2. Tạo event trigger

```sql
CREATE EVENT TRIGGER et_lab_on_sql_drop
ON sql_drop
EXECUTE FUNCTION et_lab.capture_sql_drop();
```

### 10.3. Vì sao không gọi `pg_event_trigger_dropped_objects()` ở bất kỳ đâu?

Hàm này chỉ có ý nghĩa trong event trigger context của `sql_drop`. Nó không phải bảng lịch sử ghi mọi DROP trước đây.

### 10.4. Vì sao cần vòng lặp?

`DROP ... CASCADE` có thể loại bỏ nhiều objects, không chỉ object user nêu trong lệnh. Một lệnh drop có thể dẫn tới nhiều records liên quan.

## 11. Thực hành DROP và CASCADE

Sau phần CREATE/ALTER ở trên:

```sql
CREATE VIEW et_lab.samples_view AS
SELECT sample_id, title
FROM et_lab.samples;
```

View `samples_view` phụ thuộc bảng `samples`.

Nếu chạy:

```sql
DROP TABLE et_lab.samples;
```

không có `CASCADE`, PostgreSQL thường từ chối vì vẫn còn view phụ thuộc.

### 11.1. DROP với CASCADE

Trong database lab:

```sql
DROP TABLE et_lab.samples CASCADE;
```

Lệnh có thể làm mất:

- Bảng `et_lab.samples`.
- View `et_lab.samples_view`.
- Index và constraints gắn với bảng, theo dependency semantics.
- Các objects liên quan khác nếu có.

### 11.2. Đọc DROP history

```sql
SELECT
    audit_id,
    command_tag,
    object_type,
    object_identity,
    original_drop,
    normal_drop,
    is_temporary
FROM et_lab.ddl_audit
WHERE event_name = 'sql_drop'
ORDER BY audit_id;
```

### 11.3. `original` và `normal`

`pg_event_trigger_dropped_objects()` có các flags giúp phân biệt object được nêu trực tiếp trong lệnh và những objects bị loại vì dependency processing theo mô hình nội bộ của PostgreSQL.

Đừng chỉ dựa vào một flag để kết luận “user chủ ý xóa toàn bộ objects trong kết quả”; với `CASCADE`, nhiều đối tượng bị xóa do phụ thuộc, không được gõ trực tiếp.

### 11.4. Temporary objects

`is_temporary` giúp nhận biết object tạm thời trong thông tin DROP khi được ghi nhận. Không nên giả định mọi thay đổi tạm thời đều cần audit như thay đổi schema production.

### 11.5. Đếm object identities

```sql
SELECT
    object_type,
    COUNT(*) AS dropped_objects
FROM et_lab.ddl_audit
WHERE event_name = 'sql_drop'
GROUP BY object_type
ORDER BY dropped_objects DESC, object_type;
```

Đây là số records đã ghi, không phải bằng chứng mọi lệnh DROP trong database đều đã được capture.

## 12. Vì sao `DROP TABLE IF EXISTS` vẫn cần xem xét?

`ddl_command_start` có thể được gọi theo command tag ngay cả trước khi PostgreSQL xác minh object được nêu có tồn tại.

Ví dụ:

```sql
DROP TABLE IF EXISTS et_lab.table_that_does_not_exist;
```

Một guard chặn `DROP TABLE` ở `ddl_command_start` có thể từ chối câu này chỉ vì **loại lệnh**, dù không có bảng nào bị xóa.

Ngược lại, `sql_drop` chỉ có metadata của những objects thực sự được xử lý để drop trong event context.

### 12.1. Đừng suy từ command tag rằng chắc chắn có object được xóa

`TG_TAG = 'DROP TABLE'` thể hiện loại câu lệnh, không chứng minh một bảng đã biến mất.

### 12.2. Với CASCADE phải đọc metadata chi tiết

Command tag vẫn là DROP TABLE, nhưng hệ quả có thể gồm views, constraints, indexes và các objects khác. Cần dùng `pg_event_trigger_dropped_objects()` để kiểm kê.

### 12.3. Không áp mọi ví dụ đơn giản vào schema phức tạp

Partitioned tables, views, sequences và extensions có thể có dependency trees đặc biệt. Hãy kiểm thử tập DDL đúng với database thực tế.

## 13. Chặn một loại DDL bằng `ddl_command_start`

Một tổ chức có thể muốn từ chối `DROP TABLE` trong một database thử nghiệm đang phục vụ nhiều nhóm.

### 13.1. Handler đơn giản

```sql
CREATE OR REPLACE FUNCTION et_lab.block_drop_table()
RETURNS event_trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, et_lab, pg_temp
AS $fn$
BEGIN
    RAISE EXCEPTION
        'DROP TABLE is blocked by et_lab policy'
        USING ERRCODE = '42501';
END;
$fn$;
```

### 13.2. Kích hoạt cho đúng command tag

```sql
CREATE EVENT TRIGGER et_lab_guard_drop_table
ON ddl_command_start
WHEN TAG IN ('DROP TABLE')
EXECUTE FUNCTION et_lab.block_drop_table();
```

**Quan trọng:** đây là một **policy minh họa rất rộng**, chặn mọi DROP TABLE được hỗ trợ trong database, kể cả thao tác maintenance/lab cleanup. Chỉ cài khi sẵn sàng quản lý quyền vô hiệu hóa và xử lý lỗi.

### 13.3. Thử trong lab

```sql
CREATE TABLE et_lab.guard_demo (id integer);

-- Lệnh dưới đây được kỳ vọng báo lỗi:
DROP TABLE et_lab.guard_demo;
```

Nếu command chạy trong transaction đã mở, lỗi có thể đưa transaction vào trạng thái aborted. Khi đó cần `ROLLBACK` trước các lệnh thử tiếp.

### 13.4. Tạm vô hiệu hóa để dọn lab

Với quyền quản lý event trigger:

```sql
ALTER EVENT TRIGGER et_lab_guard_drop_table DISABLE;

DROP TABLE et_lab.guard_demo;

ALTER EVENT TRIGGER et_lab_guard_drop_table ENABLE;
```

Không sử dụng việc tắt guard như quy trình vận hành tự do cho app role. Đây là thao tác quản trị được kiểm soát.

### 13.5. Guard không phải biện pháp chống superuser

Một superuser có thể quản lý event triggers hoặc thay đổi database. Không xem `block_drop_table` là cơ chế bảo vệ chống lại chính những quản trị viên có quyền vượt guard.

### 13.6. Guard không kiểm soát mọi thao tác thay thế DROP

Các thay đổi có tính phá hủy có thể xuất hiện dưới nhiều command tags khác nhau. Một trigger chỉ lọc `DROP TABLE` **không phải** một mô hình quản trị DDL hoàn chỉnh.

## 14. `ddl_command_start` không có đủ thông tin object cuối cùng

Một guard muốn cấm `DROP TABLE` trong schema `finance` nhưng cho phép schema `scratch` cần hiểu một hạn chế:

`TG_TAG` chủ yếu cho biết command tag, **không tự cung cấp một structured record chứa schema và danh sách target tables**.

Trong `ddl_command_start`, object còn chưa được xử lý và nhiều objects có thể chưa tồn tại. Vì vậy, kiểm tra theo schema/đối tượng tại start phức tạp hơn chỉ nhìn `TG_TAG`.

### 14.1. Đừng parse `current_query()` như parser SQL bảo mật

Một ý tưởng dễ sai là:

```sql
IF current_query() LIKE '%finance.%' THEN ...
```

SQL có comments, quoting, whitespace, nested statements và nhiều cú pháp hợp lệ. Matching text thô không phải một SQL parser/authorization engine đáng tin.

### 14.2. Alternative phù hợp hơn

- Sử dụng quyền `CREATE`/`ALTER`/`DROP` và ownership để chặn từ gốc.
- Phân role migration theo môi trường.
- Xác thực migration ở CI/CD trước khi chạy.
- Dùng event trigger cho những chính sách có thể kiểm tra an toàn.
- Audit object metadata ở `ddl_command_end`/`sql_drop` và phát hiện thay đổi bất thường.

### 14.3. Chặn ở `ddl_command_end` thì sao?

Nếu handler `ddl_command_end` phát hiện điều kiện không cho phép rồi raise exception, transaction DDL có thể rollback. Tuy nhiên, DDL đã thực hiện phần việc trước thời điểm đó, nên có thể đã tiêu tốn lock/CPU/I/O đáng kể.

Muốn ngăn thao tác đắt **trước khi chạy**, cần chính sách/permissions/validation đủ thông tin, không chỉ một hậu kiểm.

## 15. `table_rewrite`: nhận biết ALTER TABLE tốn chi phí

Không phải mọi `ALTER TABLE` rewrite dữ liệu. Một số thay đổi metadata có thể nhanh, trong khi đổi kiểu một cột hoặc thao tác khác có thể yêu cầu tạo lại biểu diễn vật lý của bảng.

Event `table_rewrite` xảy ra **ngay trước khi rewrite**, cung cấp:

- OID của relation sắp rewrite.
- Một bitmask mô tả lý do rewrite theo semantics PostgreSQL.

### 15.1. Handler

```sql
CREATE OR REPLACE FUNCTION et_lab.capture_table_rewrite()
RETURNS event_trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, et_lab, pg_temp
AS $fn$
DECLARE
    v_relation_oid oid;
    v_reason integer;
BEGIN
    v_relation_oid :=
        pg_catalog.pg_event_trigger_table_rewrite_oid();

    v_reason :=
        pg_catalog.pg_event_trigger_table_rewrite_reason();

    INSERT INTO et_lab.ddl_audit (
        event_name,
        command_tag,
        object_type,
        object_identity,
        rewrite_reason,
        details
    )
    VALUES (
        TG_EVENT,
        TG_TAG,
        'table',
        v_relation_oid::regclass::text,
        v_reason,
        'before physical table rewrite'
    );
END;
$fn$;
```

### 15.2. Tạo trigger

```sql
CREATE EVENT TRIGGER et_lab_on_table_rewrite
ON table_rewrite
EXECUTE FUNCTION et_lab.capture_table_rewrite();
```

### 15.3. Tạo bảng thử

```sql
CREATE TABLE et_lab.rewrite_demo (
    id integer PRIMARY KEY,
    payload integer NOT NULL
);

INSERT INTO et_lab.rewrite_demo (id, payload)
SELECT g, g * 10
FROM generate_series(1, 1000) AS s(g);
```

### 15.4. Thay đổi có khả năng buộc rewrite

```sql
ALTER TABLE et_lab.rewrite_demo
ALTER COLUMN payload TYPE text
USING payload::text;
```

Chuyển từ `integer` sang `text` thường yêu cầu thay biểu diễn dữ liệu và có thể phát sinh `table_rewrite`. Dùng `SELECT` kiểm tra event records thực tế trên PostgreSQL version của bạn; không suy mọi ALTER TYPE đều giống nhau.

### 15.5. Xem lịch sử rewrite

```sql
SELECT
    audit_id,
    command_tag,
    object_identity,
    rewrite_reason,
    happened_at
FROM et_lab.ddl_audit
WHERE event_name = 'table_rewrite'
ORDER BY audit_id;
```

## 16. Hiểu `pg_event_trigger_table_rewrite_reason()`

Hàm trả một **bitmask integer**, không phải mô tả ngôn ngữ tự nhiên.

Tùy phiên bản, các bit có thể thể hiện một hoặc nhiều nguyên nhân như:

- Thay đổi persistence của relation.
- Thay đổi default expression có yêu cầu rewrite.
- Thay đổi column type.
- Thay đổi table access method hoặc loại thay đổi khác được phiên bản hỗ trợ.

Không nên hardcode business policy dựa trên số nguyên một cách thiếu kiểm chứng. Nếu cần diễn giải từng bit, tham khảo **tài liệu chính xác của PostgreSQL version đang chạy** và kiểm thử.

### 16.1. Một rewrite có thể có nhiều lý do

Vì là bitmask, một số nguyên có thể đại diện nhiều flags đồng thời.

### 16.2. Lưu raw reason để phân tích

`et_lab.ddl_audit.rewrite_reason` lưu giá trị integer nguyên gốc. Khi cần tạo báo cáo dễ hiểu, tách bit theo definitions của đúng version trong reporting layer.

### 16.3. Event không có nghĩa rewrite đã thành công/commit

`table_rewrite` xảy ra trước khi rewrite. Nếu lệnh thất bại hoặc bị rollback, audit row insert vào cùng transaction cũng thường bị rollback.

### 16.4. Rewrite ảnh hưởng vận hành

Một `ALTER TABLE` có rewrite trên bảng lớn có thể tiêu tốn:

- I/O.
- WAL.
- Disk tạm/thêm storage.
- Thời gian giữ lock.
- Replication lag tùy cấu hình.
- Thời gian migration.

Event trigger giúp phát hiện/đặt guard, không tự khiến rewrite trở nên online hay không khóa.

## 17. Một lệnh DDL có thể kích hoạt những sự kiện nào?

Đây là **mô hình thường gặp**, không phải bảng bảo đảm mọi command tag đều có đủ events:

| Lệnh | start | end | sql_drop | table_rewrite |
| --- | --- | --- | --- | --- |
| `CREATE TABLE` | Có thể | Có thể | Thường không | Thường không |
| `ALTER TABLE ADD COLUMN` | Có thể | Có thể | Phụ thuộc tác động | Không nhất thiết |
| `ALTER TABLE ALTER TYPE` | Có thể | Có thể | Có thể tùy thay đổi | Có thể |
| `DROP TABLE` | Có thể | Có thể | Thường có nếu thực sự drop | Không |
| `DROP VIEW` | Có thể | Có thể | Thường có nếu thực sự drop | Không |
| `CREATE INDEX` | Có thể | Có thể | Thường không | Không |
| `INSERT` | Không phải event DDL | Không phải event DDL | Không | Không |

“Có thể” được dùng vì event triggers chỉ hỗ trợ một tập command tags và còn chịu filter, trạng thái ENABLE/DISABLE, transaction/error conditions.

### 17.1. Thứ tự các event liên quan

- `ddl_command_start` xảy ra trước việc thực thi DDL.
- `table_rewrite` nếu có, trước khi rewrite.
- `sql_drop` khi drop objects được xử lý.
- `ddl_command_end` khi DDL đã thực hiện xong trong transaction.

Không nên xây dựng một workflow phụ thuộc việc **mọi lệnh** phát sinh đúng một row ở từng giai đoạn.

### 17.2. Nhiều event triggers cho cùng event

Có thể có nhiều event triggers cùng loại. PostgreSQL thực hiện chúng theo quy tắc thứ tự được hệ thống quy định (ví dụ thứ tự tên khi cùng event). Không thiết kế ràng buộc nghiệp vụ quan trọng dựa trên một thứ tự không được quản lý/test rõ.

### 17.3. Một trigger có WHEN filter khác trigger khác

Hai `ddl_command_end` triggers có thể có các danh sách tags khác nhau; một lệnh chỉ kích hoạt những triggers có điều kiện phù hợp.

## 18. Phạm vi áp dụng: database, không phải toàn cluster

Một event trigger được tạo trong **database hiện tại**. Nó không phải một object tự động áp dụng cho mọi database trên cùng PostgreSQL instance.

```text
PostgreSQL instance / cluster
  |
  +-- database A
  |     +-- event trigger A1
  |     +-- event trigger A2
  |
  +-- database B
        +-- event trigger B1
```

### 18.1. Khi có nhiều databases

Nếu muốn quan sát DDL của cả database A và B, cần thiết kế triển khai/giám sát ở từng database hoặc dùng kênh logs/giải pháp tập trung thích hợp.

### 18.2. Không dùng event trigger để audit roles/databases/tablespaces

Theo PostgreSQL, event triggers không phát sinh cho các DDL thao tác trên một số **shared objects**, bao gồm:

- Roles.
- Databases.
- Tablespaces.

Vì vậy, nếu mục tiêu là audit `CREATE ROLE`, `ALTER ROLE` hoặc `CREATE DATABASE`, không thể chỉ dựa vào một event trigger trong một database.

### 18.3. Các thao tác quản lý event trigger

DDL nhắm trực tiếp tới event triggers cũng không bị event triggers quan sát giống các DDL đối tượng thông thường. Điều này giúp tránh recursion và có ý nghĩa khi thiết kế giám sát thay đổi chính audit machinery.

### 18.4. Một số chế độ vận hành đặc biệt

Event triggers có những ngoại lệ vận hành, ví dụ hành vi không hoạt động trong **single-user mode** theo quy tắc PostgreSQL. Không dùng event trigger như một ranh giới tuyệt đối trước superuser hoặc thao tác khôi phục cấp hệ thống.

### 18.5. Phải kiểm tra danh sách command tags hỗ trợ

PostgreSQL mở rộng/thay đổi hỗ trợ DDL theo phiên bản. Bảng `WHEN TAG IN` trong migration nên được thử với command tags thực tế, thay vì khẳng định “bao phủ mọi DDL” từ tên sự kiện.

## 19. Điều mà event trigger không tự cung cấp

Event trigger **không phải** bộ công cụ tự động cho mọi nhu cầu audit DDL:

1. Không tự ghi lại câu SQL raw của mọi statement.
2. Không bảo đảm audit rows tồn tại sau khi transaction thất bại.
3. Không bao phủ mọi DDL của shared objects.
4. Không giám sát trực tiếp các thao tác DML.
5. Không thay authorization của schema/objects.
6. Không thể ngăn superuser quyết định vô hiệu hóa cơ chế.
7. Không tự phân biệt người dùng web cuối cùng khi connection pool dùng chung DB login.
8. Không tự xác định một lệnh `ALTER TABLE` có an toàn về runtime hay không.
9. Không bảo đảm audit object names/metadata sẽ còn tồn tại nguyên vẹn sau khi schemas thay đổi nhiều lần.
10. Không thay quy trình migration review và backup.

### 19.1. Muốn ghi SQL text thật sự thì sao?

Xem xét các kênh PostgreSQL logs, pgAudit (nếu triển khai/hỗ trợ) hoặc hệ thống triển khai migrations có lưu statement text và actor.

Event trigger cung cấp **structured object metadata** tại hooks cụ thể, là dữ liệu bổ sung hữu ích nhưng không thay tất cả các nguồn trên.

### 19.2. Muốn biết ai đổi dữ liệu trong một row?

Dùng row/statement triggers phù hợp, application audit, WAL/logical decoding, logs hoặc cơ chế khác tùy yêu cầu, không dùng event trigger DDL để thay thế.

## 20. Tính giao dịch: audit row có được giữ nếu DDL rollback?

Giả sử:

```sql
BEGIN;

CREATE TABLE et_lab.rollback_demo (
    id integer
);

-- Hàm ddl_command_end đã INSERT audit record.
ROLLBACK;
```

Sau `ROLLBACK`:

- Bảng `et_lab.rollback_demo` không còn.
- Row audit được handler INSERT trong transaction này **cũng bị rollback**.
- Không nên mong thấy một record “đã thử CREATE TABLE” trong bảng audit nội bộ.

### 20.1. Audit không đồng nghĩa attempt log

Bảng audit DDL theo cơ chế trên chủ yếu phản ánh **thay đổi đã commit**, không giữ đầy đủ những thao tác thất bại/đã rollback.

### 20.2. Nếu CREATE thành công nhưng transaction chưa commit

`ddl_command_end` đã được gọi, nhưng session khác chưa chắc quan sát được bảng và audit row vì chúng vẫn chưa commit.

### 20.3. Nếu handler raise exception

```sql
RAISE EXCEPTION 'DDL rejected';
```

Exception không được xử lý có thể làm statement DDL thất bại và transaction tương ứng rollback.

### 20.4. Nếu cần log cả DDL thất bại

Cần một kênh **ngoài transaction DDL** (ví dụ database/server logs được quản lý thích hợp), chứ không chỉ INSERT một row vào bảng trong cùng transaction.

### 20.5. Savepoints

Khi một DDL sau `SAVEPOINT` bị rollback về savepoint, audit rows trong phạm vi bị rollback cũng có thể bị hủy. Hãy kiểm tra recovery semantics trong ứng dụng/migration tool.

## 21. Một vấn đề thiết kế: ghi audit rồi lại DROP chính audit table

Giả sử có event trigger `sql_drop` luôn INSERT vào `et_lab.ddl_audit`. Nếu một migration cố drop chính bảng audit, handler có thể không còn ghi được log như thiết kế và DDL có thể lỗi.

### 21.1. Đừng đặt audit table vào vòng dependency nguy hiểm

Chỉ rõ ai có quyền DROP/ALTER audit objects. Không coi event trigger là cơ chế tự bảo vệ duy nhất cho bảng audit.

### 21.2. Dùng schema riêng và quyền hạn chế

Quyền trên schema `et_lab` nên được cấp giới hạn cho owner của audit module, không cấp `CREATE`/`DROP` tùy tiện cho app roles.

### 21.3. Dọn lab có thứ tự

Trước khi `DROP SCHEMA et_lab CASCADE`, gỡ các event triggers dùng functions/tables trong schema. Nếu không, việc xóa schema chứa audit function/table có thể ảnh hưởng hooks đang hoạt động.

### 21.4. Audit table không phải WORM storage

Bảng PostgreSQL thông thường không tự bất biến. Privileged roles có thể sửa/xóa records hoặc vô hiệu hóa trigger. Nếu compliance yêu cầu log chống sửa, cần kiến trúc ghi ra hệ thống độc lập có cơ chế bảo toàn phù hợp.

## 22. Chống recursion và thao tác nguy hiểm trong handler

Event trigger chạy **khi DDL đang thực thi**. Nếu handler tự thực hiện DDL, có thể kích hoạt event trigger khác (hoặc chính nó) theo điều kiện phù hợp.

### 22.1. Ví dụ không nên dùng

```sql
-- Ý tưởng nguy hiểm trong event handler:
EXECUTE 'CREATE TABLE et_lab.new_log_table (...)';
```

Nếu DDL đó lại kích hoạt `ddl_command_end`, handler có thể tự gọi lại hoặc tạo side effects khó kiểm soát.

### 22.2. Mẫu an toàn hơn

- Chỉ INSERT vào audit table đã tồn tại.
- Hạn chế số câu SQL trong handler.
- Tránh DDL trong handler.
- Không mở network requests hoặc phụ thuộc vào dịch vụ ngoài nếu không có thiết kế riêng.
- Dùng `SET search_path` an toàn.
- Có transaction/error behavior rõ ràng.

### 22.3. Kiểm soát các object tạm

Temporary objects không nên được xem là trusted schema objects trong privileged handlers. `pg_temp` có resolution semantics riêng; dùng fully qualified references và trusted path.

### 22.4. Không commit trong event trigger function

Event trigger chạy bên trong transaction của command. Hàm PL/pgSQL không có quyền tùy ý `COMMIT`/`ROLLBACK` transaction như top-level session manager.

### 22.5. Cẩn thận với locks

DDL có thể đang giữ locks mạnh. Handler chạy truy vấn phức tạp hoặc đợi tài nguyên khác có thể kéo dài thời gian giữ lock và gây ảnh hưởng các sessions khác.

## 23. Hiệu năng: mỗi DDL có thể trả nhiều metadata rows

Một event trigger dùng:

```sql
FOR r IN
    SELECT *
    FROM pg_event_trigger_ddl_commands()
LOOP
    INSERT INTO et_lab.ddl_audit (...);
END LOOP;
```

có thể chèn nhiều audit rows cho một lệnh DDL.

### 23.1. Khối lượng metadata

Một migration tạo nhiều tables, indexes, constraints và views có thể phát sinh nhiều records. Đừng tự suy số inserts là một per statement.

### 23.2. Tránh xử lý nặng trong event trigger

Không chạy:

- Reports quét toàn database.
- Network calls có độ trễ khó dự đoán.
- Lệnh DDL phụ thuộc object vừa được tạo theo cách không kiểm chứng.
- Nested migrations.
- Các truy vấn chờ khóa lâu không cần thiết.

### 23.3. Dùng bảng audit append-oriented

Trong production, tổ chức retention, partitioning nếu log rất lớn, indexing đủ phục vụ báo cáo và monitoring. Nhưng đừng tạo nhiều indexes khiến mỗi DDL ghi audit quá đắt.

### 23.4. Đo cost của migration

Đo thời gian chạy migration có/không handler trong staging, số records, lock duration và WAL. Đừng so một `CREATE TABLE` rỗng với một `ALTER TABLE` rewrite hàng chục GB rồi kết luận về overhead của event trigger.

### 23.5. Xử lý lỗi quyết định độ sẵn sàng của schema changes

Nếu audit table hết disk/không có INSERT privilege, một handler không xử lý lỗi có thể làm thất bại DDL. Đây có thể là **fail-closed chủ ý** hoặc một sự cố vận hành; lựa chọn phải được thiết kế rõ.

## 24. Bảo mật: ai được tạo event trigger và ai ghi log?

Theo mô hình PostgreSQL thông thường, **superuser** mới được tạo event trigger. Tuy nhiên, **hàm handler** cũng có security mode và owner riêng.

### 24.1. SECURITY INVOKER của lab

Hàm `et_lab.capture_ddl_end()` mặc định dùng quyền caller. Trong lab một administrator thực hiện DDL và có quyền INSERT vào bảng audit, nên mẫu hoạt động.

Nếu một role khác tạo bảng nhưng không có INSERT privilege trên `et_lab.ddl_audit`, DDL có thể bị chặn vì handler lỗi quyền.

### 24.2. SECURITY DEFINER trong production

Có thể thiết kế một **dedicated NOLOGIN audit writer role** với quyền INSERT rất hạn chế vào audit table, rồi cho handler:

```sql
SECURITY DEFINER
SET search_path = pg_catalog, et_lab, pg_temp
```

Như vậy handler có thể ghi audit khi nhiều caller roles thực hiện DDL, mà không phải cấp INSERT trực tiếp vào audit log cho mọi DDL role.

**Không tạo function này với superuser owner chỉ để hết lỗi quyền.** Nếu handler có lỗ hổng SQL injection/object hijacking, owner có quyền quá cao làm tăng hậu quả.

### 24.3. Owner phải ít quyền

Một writer role có thể chỉ cần:

- Quyền USAGE trên schema audit.
- INSERT vào audit table.
- Quyền liên quan đến các objects được dùng trong INSERT.
- Quyền đọc catalog/helper functions phù hợp.

Không cần `CREATEROLE`, `BYPASSRLS`, superuser hay quyền sửa dữ liệu ứng dụng.

### 24.4. Security definer làm current_user đổi

Nếu handler `SECURITY DEFINER`, cột audit `effective_role DEFAULT current_user` có thể lưu **audit function owner**, không phải DDL invoker.

Thiết kế actor attribution phải tách:

- DB session login: `session_user`.
- Effective context trong routine.
- `SET ROLE` context và quyền thực tế.
- User cuối ở ứng dụng/migration pipeline.

Nếu nhiều web users chia sẻ DB login, cần đối chiếu identity với một nguồn app/migration đáng tin; không tin tham số hoặc custom GUC mà caller tự đặt.

### 24.5. Schema search_path an toàn

`et_lab` phải là trusted schema không cho untrusted roles CREATE/ALTER objects. Đặt `pg_catalog` trước và `pg_temp` cuối, đồng thời định danh `et_lab.ddl_audit` tường minh.

### 24.6. Event trigger không thay privilege trên DDL

Một role không có quyền `ALTER TABLE` không tự được phép ALTER chỉ vì có event trigger theo dõi. PostgreSQL vẫn kiểm tra quyền DDL theo semantics bình thường.

## 25. `TG_EVENT` và `TG_TAG` khác nhau

Trong event trigger function viết bằng PL/pgSQL:

- `TG_EVENT` là tên sự kiện, như `ddl_command_start` hoặc `ddl_command_end`.
- `TG_TAG` là command tag, như `CREATE TABLE`, `ALTER TABLE` hoặc `DROP TABLE`.

### 25.1. Minh họa

```sql
CREATE OR REPLACE FUNCTION et_lab.print_ddl_context()
RETURNS event_trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, et_lab, pg_temp
AS $fn$
BEGIN
    RAISE NOTICE
        'event=%, tag=%',
        TG_EVENT,
        TG_TAG;
END;
$fn$;
```

Đây chỉ là handler để quan sát; **chưa được kích hoạt** nếu chưa tạo `CREATE EVENT TRIGGER` tương ứng.

### 25.2. Không dùng `TG_OP` từ table trigger

`TG_OP` thuộc ngữ cảnh table trigger để chỉ `INSERT`/`UPDATE`/`DELETE`/`TRUNCATE`, không thay thế `TG_TAG` cho event trigger DDL.

### 25.3. TG_TAG không liệt kê phụ thuộc CASCADE

`TG_TAG` có thể là `DROP TABLE`, nhưng nó không chứa danh sách các objects đã bị xóa. Dùng `pg_event_trigger_dropped_objects()` ở `sql_drop`.

### 25.4. Một command có thể tác động nhiều objects

`TG_TAG` mô tả command level, trong khi helper functions có thể trả nhiều rows object-level.

## 26. Event trigger và extension scripts

Khi `CREATE EXTENSION` hoặc `ALTER EXTENSION ... UPDATE` chạy script tạo/sửa objects, một số DDL bên trong có thể tham gia cơ chế event trigger theo những điều kiện được PostgreSQL hỗ trợ.

Trường `in_extension` từ `pg_event_trigger_ddl_commands()` giúp xác định command thực hiện trong ngữ cảnh extension script.

### 26.1. Vì sao một migration có thể ghi nhiều objects?

Một extension có thể tạo nhiều functions, types, operators, casts, tables hoặc views. Event handler có thể thấy nhiều command records; việc chỉ đếm số `CREATE EXTENSION` bên ngoài không đủ.

### 26.2. Đừng mặc định chặn mọi DDL trong extension

Một policy chặn `CREATE FUNCTION` hoặc `CREATE TYPE` có thể khiến extension installation/upgrade thất bại. Trước khi bật guard ở production, kiểm tra toàn bộ migration và extension workflows.

### 26.3. `in_extension` không thay thế authorization

Dấu hiệu “command nằm trong extension script” không có nghĩa mọi hành động đó đương nhiên an toàn hoặc cần bỏ qua mọi kiểm tra. Hãy định nghĩa policy rõ.

### 26.4. Không dùng audit handler sửa objects của extension

Objects thuộc extension có dependency/ownership lifecycle riêng. Việc tự ALTER chúng trong event handler có thể gây lỗi upgrade hoặc khó bảo trì.

## 27. Theo dõi trạng thái event triggers qua system catalog

Event triggers được lưu trong `pg_event_trigger`.

```sql
SELECT
    e.evtname AS event_trigger_name,
    e.evtevent AS event_name,
    e.evtenabled AS enabled_mode,
    e.evttags AS command_tags,
    e.evtfoid::regprocedure AS handler_function,
    pg_catalog.pg_get_userbyid(e.evtowner) AS owner_name
FROM pg_catalog.pg_event_trigger AS e
ORDER BY e.evtname;
```

### 27.1. `evtname`

Tên event trigger trong database.

### 27.2. `evtevent`

Loại event, ví dụ `ddl_command_end` hoặc `sql_drop`.

### 27.3. `evtenabled`

Trạng thái liên quan đến enable/disable và replication modes; các giá trị nội bộ thường bao gồm:

- `O`: enabled ở mode thông thường/origin.
- `D`: disabled.
- `R`: replica.
- `A`: always.

Đọc trạng thái cùng cấu hình `session_replication_role` và policy vận hành; không mặc định một trigger ENABLE có nghĩa nó chắc chắn chạy trong mọi execution mode.

### 27.4. `evttags`

Danh sách command tags khi tạo trigger với `WHEN TAG IN (...)`, hoặc NULL khi không giới hạn tags theo clause tương ứng.

### 27.5. `evtfoid` và `evtowner`

`evtfoid` tham chiếu handler function, còn `evtowner` là owner event trigger. Owner event trigger và owner handler function là **hai khái niệm** không nên tự xem là trùng nhau.

## 28. Bật/tắt event triggers

Có thể dùng:

```sql
ALTER EVENT TRIGGER et_lab_on_ddl_end DISABLE;

ALTER EVENT TRIGGER et_lab_on_ddl_end ENABLE;
```

Các thay đổi cần quyền phù hợp.

### 28.1. Một số chế độ khác

PostgreSQL hỗ trợ các dạng:

```sql
ALTER EVENT TRIGGER et_lab_on_ddl_end
ENABLE ALWAYS;

ALTER EVENT TRIGGER et_lab_on_ddl_end
ENABLE REPLICA;
```

Các mode liên quan đến `session_replication_role`. Không đổi mode trên production nếu chưa hiểu môi trường replica/logical replication/apply worker và quyền đặc biệt liên quan.

### 28.2. DISABLE không xóa trigger

Trigger vẫn tồn tại trong catalog nhưng không phát sinh theo mode disabled.

### 28.3. DROP xóa định nghĩa

```sql
DROP EVENT TRIGGER et_lab_on_ddl_end;
```

Không còn hook này trong database sau khi transaction commit.

### 28.4. Điều chỉnh handler function

`CREATE OR REPLACE FUNCTION et_lab.capture_ddl_end()` có thể thay body được event trigger gọi. Do đó, quyền sửa handler function là một phần quan trọng của hệ thống audit.

### 28.5. Chế độ khẩn cấp

Nếu một event trigger làm mọi migration fail, DBA có thể cần vô hiệu hóa hoặc sửa nó theo quy trình khôi phục. Luôn chuẩn bị đường vận hành quản trị đáng tin, không để chỉ chính handler hỏng có quyền sửa handler.

## 29. Kiểm tra một migration bằng transaction

Trong staging, có thể thử:

```sql
BEGIN;

CREATE TABLE et_lab.migration_probe (
    id integer PRIMARY KEY,
    label text
);

ALTER TABLE et_lab.migration_probe
ADD COLUMN created_at timestamptz;

SELECT
    event_name,
    command_tag,
    object_identity
FROM et_lab.ddl_audit
WHERE object_identity LIKE '%migration_probe%'
ORDER BY audit_id;

ROLLBACK;
```

### 29.1. Quan sát trong transaction của chính mình

Session hiện tại thấy những audit rows chính nó vừa INSERT dù chưa commit (MVCC read-your-writes).

### 29.2. Sau ROLLBACK

`migration_probe` và audit rows của transaction thử nghiệm thường biến mất.

### 29.3. Không phải cách audit mọi lần thử DDL

Thử transaction rồi ROLLBACK phù hợp học semantics nhưng không tạo attempt history bền vững.

### 29.4. Với migration tools

Một số công cụ chạy nhiều statements trong một transaction; công cụ khác có bước không transaction được hoặc các lệnh đặc biệt như `CREATE INDEX CONCURRENTLY` yêu cầu context riêng.

Event trigger không thay thế hiểu biết về transaction boundaries của từng migration.

## 30. Trường hợp DROP có phụ thuộc nhiều cấp

Một ví dụ có dependency chain:

```sql
CREATE TABLE et_lab.parent_doc (
    id integer PRIMARY KEY,
    title text
);

CREATE VIEW et_lab.doc_view AS
SELECT id, title
FROM et_lab.parent_doc;

CREATE VIEW et_lab.doc_titles AS
SELECT title
FROM et_lab.doc_view;
```

Nếu dùng:

```sql
DROP TABLE et_lab.parent_doc CASCADE;
```

nhiều objects phụ thuộc có thể bị xóa. `pg_event_trigger_dropped_objects()` hữu ích vì catalog relations của những views bị loại khỏi hệ thống ở thời điểm `sql_drop`.

### 30.1. Tại sao không chỉ SELECT pg_class sau DROP?

Một object đã bị remove khỏi catalog không còn được lookup theo cách thông thường. Helper function của event context cung cấp metadata chuyên biệt trước khi thông tin đó bị mất khỏi đường truy cập bình thường.

### 30.2. Tại sao original flag không phải toàn bộ câu chuyện?

Một object bị xóa do dependency có thể tác động business lớn hơn object mà lệnh trực tiếp nêu. Đối với impact analysis, cần lưu **toàn bộ dropped objects** và quan hệ phụ thuộc nếu nghiệp vụ yêu cầu.

### 30.3. DROP EXTENSION có thể ảnh hưởng objects thế nào?

Extension có các thành phần phụ thuộc và có thể chứa nhiều objects. Khi drop extension, các thành phần bị xóa theo dependency model; cần kiểm chứng `sql_drop` records thực tế cho extension trong môi trường cần audit.

### 30.4. Không gán tất cả dropped rows cho “table”

`object_type` có thể là view, index, constraint, type hoặc loại khác, tùy object được PostgreSQL ghi nhận.

## 31. DDL trong transaction dài và tác động lock

Một migration thực hiện:

```sql
BEGIN;

ALTER TABLE large_table
ALTER COLUMN ...;

-- Nhiều thao tác khác...
COMMIT;
```

có thể giữ locks trong thời gian dài.

### 31.1. Event trigger làm tăng thời gian critical section

Nếu handler chạy query chậm, INSERT log nghẽn I/O hoặc đợi lock audit table, thời gian lệnh DDL và các locks liên quan có thể kéo dài.

### 31.2. Handler không biến migration thành online

Ví dụ `table_rewrite` chỉ thông báo một rewrite sắp diễn ra. Nó không có cơ chế tự động chia rewrite thành từng batch để tránh lock.

### 31.3. Không gọi hệ thống bên ngoài thiếu timeout

Một handler phụ thuộc network/external API có thể khiến lệnh DDL chờ lâu hoặc fail khi dịch vụ audit ngoài không hoạt động. Thiết kế đồng bộ/bất đồng bộ phải được cân nhắc riêng; mặc định giữ handler đơn giản.

### 31.4. Sử dụng timeout ở migration phù hợp

`lock_timeout`/`statement_timeout` có thể giúp bảo vệ thời gian chờ trong những môi trường được quản lý, nhưng hủy statement cũng rollback DDL và log nội bộ của nó.

### 31.5. Kiểm thử trên bảng có dữ liệu lớn

Một `ALTER TABLE` thay kiểu có thể gây rewrite rất đắt. Cần plan migration, lịch bảo trì và estimate về storage/locks trước khi triển khai.

## 32. Chiến lược audit: chặn, ghi nhận hay giám sát?

| Mục tiêu | Lựa chọn thường phù hợp |
| --- | --- |
| Chặn một nhóm command tags rõ ràng | `ddl_command_start` + exception |
| Audit objects đã tạo/sửa | `ddl_command_end` + `pg_event_trigger_ddl_commands()` |
| Audit objects bị xóa | `sql_drop` + `pg_event_trigger_dropped_objects()` |
| Phát hiện rewrite tốn kém | `table_rewrite` + OID/reason |
| Ghi thất bại/rollback attempts | PostgreSQL logs/giải pháp ngoài transaction |
| Ghi nguyên statement text | Logs/pgAudit/migration history theo mục đích |
| Ngăn app role DROP table | Ownership/privileges |
| Audit DML row changes | Table triggers/CDC/logical decoding theo nhu cầu |
| Audit cluster roles/database changes | Cluster/system logs và công cụ quản trị |
| Phân tích schema drift | Catalog snapshots, migration checksums, diff tools |

### 32.1. Vì sao vẫn dùng event trigger nếu đã có logs?

Event trigger cung cấp structured metadata về objects, đặc biệt dropped dependencies và rewrite reasons. Logs thường cung cấp thông tin statement/timing/actor theo cấu hình.

Hai nguồn có thể bổ sung, không nhất thiết thay thế nhau.

### 32.2. Vì sao không dùng event trigger thay quyền?

Một policy “không ai được DROP production table” nên bắt đầu từ **không cấp quyền DROP/ownership trái phép**, cùng quy trình change management. Event trigger chỉ là hàng rào bổ sung, không phải quyền nền tảng.

## 33. Vận hành an toàn với nhiều roles

Trong môi trường đa nhóm, có thể chia:

- **Migration role** có quyền DDL trong schema cho phép.
- **App runtime role** chỉ DML cần thiết, không được ALTER/DROP.
- **Audit writer owner** dùng để ghi metadata vào bảng audit.
- **Read-only audit reviewer** được SELECT bảng log.
- **DBA/incident role** quản lý event triggers và khôi phục khi cần.

### 33.1. Least privilege

Không cấp quyền superuser cho app chỉ vì nó cần trigger DDL. Phần CREATE EVENT TRIGGER thuộc bước quản trị được phê duyệt.

### 33.2. Trigger function ownership

Một function `SECURITY DEFINER` với owner có quyền superuser là một bề mặt tấn công nghiêm trọng. Hạn chế owner và search_path, không nhận SQL text tùy ý từ caller.

### 33.3. SQL injection trong handler

Metadata như `object_identity` nên được lưu dưới dạng **data values**, không nối vào dynamic SQL để tự truy vấn bảng bị drop.

Nếu cần xử lý identifiers động, dùng quote đúng `format('%I')`, map/allowlist objects và kiểm tra quyền. Nhưng tốt hơn là không chạy dynamic DDL trong handler.

### 33.4. Không cho untrusted CREATE trong audit schema

Nếu schema `et_lab` bị cho caller tạo/sửa helpers, privileged handler có thể bị thay đổi object resolution. Dùng schema tin cậy, định danh bảng/hàm và đặt `SET search_path = pg_catalog, et_lab, pg_temp`.

### 33.5. Không tin RLS của caller trong definer context

Nếu handler `SECURITY DEFINER`, quyền owner có thể ảnh hưởng RLS. Với audit table và user context, cần phân biệt việc ghi log được cấp quyền và việc đọc dữ liệu nhạy cảm.

## 34. Dùng catalog và báo cáo để phát hiện thay đổi không mong đợi

Khi đã ghi audit:

```sql
SELECT
    date_trunc('day', happened_at) AS audit_day,
    command_tag,
    COUNT(*) AS event_records
FROM et_lab.ddl_audit
GROUP BY
    date_trunc('day', happened_at),
    command_tag
ORDER BY audit_day DESC, event_records DESC;
```

### 34.1. Thống kê theo object type

```sql
SELECT
    event_name,
    object_type,
    COUNT(*) AS n
FROM et_lab.ddl_audit
GROUP BY event_name, object_type
ORDER BY event_name, n DESC;
```

### 34.2. Xem những objects cùng transaction

```sql
SELECT
    transaction_id,
    COUNT(*) AS audit_rows,
    array_agg(command_tag ORDER BY audit_id)
        AS command_tags
FROM et_lab.ddl_audit
GROUP BY transaction_id
ORDER BY transaction_id DESC
LIMIT 20;
```

Một transaction có thể chứa nhiều statements; `transaction_id` giúp nhóm records theo transaction, không nhất thiết xác định duy nhất từng SQL statement.

### 34.3. Báo cáo riêng rewrite

```sql
SELECT
    happened_at,
    object_identity,
    rewrite_reason
FROM et_lab.ddl_audit
WHERE event_name = 'table_rewrite'
ORDER BY happened_at DESC;
```

### 34.4. Cẩn thận với actor attribution

`session_login` có thể là shared migration login; `effective_role` có thể bị ảnh hưởng bởi `SET ROLE` hoặc `SECURITY DEFINER`. Không kết luận cá nhân thực hiện DDL chỉ từ hai cột mà chưa đối chiếu logs/deployment identity.

### 34.5. Metrics không phải số lệnh nguyên gốc

Vì audit là object-level records, tổng các rows có thể lớn hơn số statements; tùy filter và supported events, cũng có thể ít hơn.

## 35. Cài event trigger như một phần migration

Một migration tối thiểu nên có thứ tự:

1. Xác nhận đây là database đúng và môi trường không phải production ngoài kế hoạch.
2. Tạo audit schema/table trước.
3. Tạo owner/permissions thích hợp cho handler.
4. Viết functions `RETURNS event_trigger` với trusted `search_path`.
5. Review logic, scope và command tags.
6. Tạo event trigger bằng superuser/admin role được phép.
7. Kiểm tra `pg_event_trigger` và handler owner.
8. Thực hiện DDL thử có thể rollback.
9. Kiểm tra metadata audit và behavior rollback.
10. Kiểm tra multi-role permissions.
11. Kiểm tra guard/cleanup khi có exception.
12. Bật monitoring, retention và documented incident runbook.

### 35.1. Không tạo trigger trước bảng audit

Nếu handler ghi bảng chưa tồn tại, chính DDL tiếp theo sẽ lỗi.

### 35.2. Không thêm guard blocking quá sớm

Một guard chặn `DROP TABLE` ngay khi cài có thể khiến migrations cần dọn dữ liệu/temp objects bị chặn, kể cả cleanup của lab.

### 35.3. Có đường khôi phục độc lập với handler

DBA phải biết tên event trigger và có quyền `ALTER EVENT TRIGGER ... DISABLE` / `DROP EVENT TRIGGER` khi handler lỗi.

### 35.4. Dùng staging để thử extension upgrades

Một policy dựa trên command tags có thể ảnh hưởng `CREATE EXTENSION`/`ALTER EXTENSION`. Kiểm thử với extension scripts đang dùng.

### 35.5. Có rollback migration

Việc xóa handler function khi event trigger vẫn phụ thuộc vào nó có thể lỗi vì dependency. Xóa/disable event triggers đúng thứ tự trước khi xóa schema/functions.

## 36. Dọn lab theo thứ tự an toàn

Nếu đã thực hành đầy đủ và muốn bỏ các đối tượng của bài:

```sql
-- Cần quyền quản trị event trigger thích hợp.
DROP EVENT TRIGGER IF EXISTS et_lab_guard_drop_table;
DROP EVENT TRIGGER IF EXISTS et_lab_on_table_rewrite;
DROP EVENT TRIGGER IF EXISTS et_lab_on_sql_drop;
DROP EVENT TRIGGER IF EXISTS et_lab_on_ddl_end;

-- Chỉ thực hiện trong database lab.
DROP SCHEMA IF EXISTS et_lab CASCADE;
```

### 36.1. Vì sao DROP event triggers trước?

Các event triggers sử dụng functions và audit table trong `et_lab`. Khi xóa schema, cần tránh tình huống handler còn hoạt động nhưng object đích của nó đã bị xóa.

### 36.2. Vì sao không giữ guard DROP TABLE?

Nó áp dụng ở cấp database. Để lại một guard trong database lab dùng chung có thể chặn công việc của người khác sau bài tập.

### 36.3. `DROP SCHEMA ... CASCADE` là thao tác phá hủy

Chỉ chạy nếu schema `et_lab` đúng là môi trường lab mà bạn sở hữu và không chứa dữ liệu khác ngoài bài. Trong production, không copy lệnh này.

### 36.4. Không gọi cleanup trước khi xem audit

Cleanup sẽ xóa luôn `et_lab.ddl_audit`. Nếu cần giữ kết quả làm bài, xuất dữ liệu hoặc ghi lại báo cáo trước khi xóa.

## 37. Những hiểu lầm thường gặp

| Ngộ nhận hoặc lỗi | Thực tế |
| --- | --- |
| Event trigger giống AFTER INSERT trigger | Không; nó quan sát những DDL được hỗ trợ |
| Event trigger gắn với một bảng | Không; nó thuộc database |
| CREATE EVENT TRIGGER ai cũng dùng được | PostgreSQL yêu cầu superuser |
| `ddl_command_start` xảy ra sau DDL | Nó xảy ra trước |
| `ddl_command_end` nghĩa transaction đã commit | Chưa; vẫn có thể rollback |
| Có DROP TABLE thì chắc có sql_drop object | IF EXISTS thiếu object có thể không drop gì |
| `sql_drop` vẫn query pg_class thấy mọi dropped object | Objects đã bị loại khỏi catalogs trong transaction |
| `pg_event_trigger_dropped_objects()` là history table | Chỉ có metadata của event đang chạy |
| `pg_event_trigger_ddl_commands()` chạy ở mọi lúc | Chỉ đúng trong ddl_command_end context |
| Một DDL tương đương một audit row | Một lệnh có thể tác động nhiều objects |
| `TG_TAG` chứa list objects | Chỉ command tag |
| `TG_EVENT` là command tag | Nó là event name |
| Table rewrite xảy ra sau khi rewrite xong | Event phát trước rewrite |
| Mọi ALTER TABLE rewrite bảng | Không |
| rewrite_reason là text mô tả | Là bitmask integer |
| Audit INSERT bền cả khi rollback | Cùng transaction thường rollback |
| Event trigger bắt mọi DDL cluster | Không bao phủ shared objects, các exceptions |
| CREATE ROLE tự làm ddl_command_end | Không theo cơ chế event trigger DDL thông thường |
| Event trigger luôn giữ được raw SQL | Nó cung cấp metadata, không phải mọi raw statements |
| SUPERUSER không thể tắt guard | Superuser có quyền quản trị |
| SECURITY DEFINER owner nào cũng được | Nên least privilege; superuser owner nguy hiểm |
| Actor là current_user của definer | Có thể là function owner |
| Session_user luôn là web user | Shared pool có thể dùng một login |
| Handler có thể COMMIT độc lập | Không phải transaction manager |
| Handler làm DDL khác luôn an toàn | Có thể recursion/locks/side effects |
| WHEN TAG IN lọc theo table | Lọc theo command tag, không theo relation |
| Chỉ ghi audit table là bất biến | Privileged roles có thể sửa/xóa |
| Bất kỳ DDL đều cần handler chậm để audit sâu | Overhead làm tăng lock/latency |
| DROP EVENT TRIGGER luôn được event trigger khác audit | DDL quản lý event trigger có ngoại lệ |
| ALTER EVENT TRIGGER DISABLE xóa trigger | Chỉ đổi mode |
| `evttags IS NULL` nghĩa trigger bị hỏng | Có thể do không khai báo WHEN filter |
| `evtenabled='D'` nghĩa trigger đã bị drop | Nó vẫn tồn tại nhưng disabled |
| Audit logs đã đủ quyền kiểm soát DDL | Nên kết hợp GRANT, ownership, migrations |
| Chỉ thử CREATE TABLE là đủ | Cần thử DROP CASCADE, ALTER, rollback, rewrite, roles |

## 38. Bài tập thực hành có đáp án

Các bài tập giả định database lab `et_lab` đã được tạo và bạn có quyền cần thiết. Những ví dụ anti-pattern không dùng trên production.

### Bài 1. Event trigger được dùng để quan sát gì?

**Đáp án:** những DDL command tags/sự kiện được PostgreSQL hỗ trợ trong database hiện tại, ví dụ `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`.

### Bài 2. Event trigger khác table trigger ở đâu?

**Đáp án:** table trigger quan sát DML/`TRUNCATE` trên đối tượng cụ thể; event trigger quan sát DDL cấp database theo event/tag.

### Bài 3. Kể tên bốn event

**Đáp án:** `ddl_command_start`, `ddl_command_end`, `sql_drop`, `table_rewrite`.

### Bài 4. Event nào chạy trước DDL?

**Đáp án:** `ddl_command_start`.

### Bài 5. Event nào phù hợp audit metadata sau CREATE TABLE?

**Đáp án:** `ddl_command_end` kết hợp `pg_event_trigger_ddl_commands()`.

### Bài 6. Event nào phù hợp audit DROP CASCADE?

**Đáp án:** `sql_drop` kết hợp `pg_event_trigger_dropped_objects()`.

### Bài 7. Event nào có thể phát hiện ALTER TABLE cần rewrite?

**Đáp án:** `table_rewrite`.

### Bài 8. Hàm handler cần trả về type nào?

**Đáp án:** `event_trigger`.

### Bài 9. Cú pháp tạo một handler function tối giản?

```sql
CREATE FUNCTION et_lab.notice_event()
RETURNS event_trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    RAISE NOTICE 'event=%, tag=%', TG_EVENT, TG_TAG;
END;
$fn$;
```

**Đáp án:** không có function arguments, có `RETURNS event_trigger` và dùng đúng event context.

### Bài 10. Tạo trigger theo dõi ALTER TABLE?

```sql
CREATE EVENT TRIGGER et_lab_alter_notice
ON ddl_command_end
WHEN TAG IN ('ALTER TABLE')
EXECUTE FUNCTION et_lab.notice_event();
```

**Đáp án:** event trigger dùng `ON ddl_command_end` và command tag filter. Nếu đã tạo, không tạo lại tên trùng.

### Bài 11. TG_EVENT và TG_TAG khác nhau?

**Đáp án:** `TG_EVENT` là tên event, `TG_TAG` là loại command DDL.

### Bài 12. Có thể dùng TG_OP từ row trigger cho DDL không?

**Đáp án:** không. Event trigger dùng event context riêng; `TG_OP` không thay thế `TG_TAG`.

### Bài 13. Lệnh CREATE EVENT TRIGGER có tự phát ddl_command_end như CREATE TABLE không?

**Đáp án:** event-trigger-targeting commands có các ngoại lệ và không tự phát các event triggers như DDL objects thông thường.

### Bài 14. Có thể tạo event trigger mà không phải superuser không?

**Đáp án:** `CREATE EVENT TRIGGER` yêu cầu superuser theo PostgreSQL. Managed service có thể không cho thực hiện dù có quyền ứng dụng rộng.

### Bài 15. `WHEN TAG IN` lọc theo cột table không?

**Đáp án:** không. Nó lọc command tags, ví dụ `CREATE TABLE` hoặc `ALTER TABLE`.

### Bài 16. Một DDL có thể tạo nhiều metadata rows không?

**Đáp án:** có. `pg_event_trigger_ddl_commands()` có thể trả nhiều records/objects.

### Bài 17. Vì sao không giả định một statement = một audit row?

**Đáp án:** DDL có thể tạo/sửa nhiều objects, phụ thuộc và command records.

### Bài 18. `pg_event_trigger_ddl_commands()` gọi khi nào?

**Đáp án:** trong handler của sự kiện `ddl_command_end`.

### Bài 19. `pg_event_trigger_dropped_objects()` gọi khi nào?

**Đáp án:** trong handler của sự kiện `sql_drop`.

### Bài 20. Vì sao sql_drop helper quan trọng khi object bị xóa?

**Đáp án:** object có thể đã không còn trong catalogs ở thời điểm hook, helper cung cấp metadata dropped objects.

### Bài 21. `object_identity` là raw SQL statement không?

**Đáp án:** không. Nó là mô tả identity của object.

### Bài 22. `command` kiểu pg_ddl_command có in thành SQL gốc trực tiếp được không?

**Đáp án:** không được coi là text SQL gốc; đây là internal representation.

### Bài 23. `in_extension` cho biết gì?

**Đáp án:** DDL command được thực thi trong ngữ cảnh extension script theo metadata được PostgreSQL ghi nhận.

### Bài 24. Lệnh `DROP TABLE ... CASCADE` có thể ảnh hưởng gì?

**Đáp án:** ngoài bảng gốc, có thể xóa objects phụ thuộc như views/constraints/indexes theo dependency semantics.

### Bài 25. `original_drop` có nghĩa mọi object phải được user gõ trong lệnh?

**Đáp án:** flag giúp phân biệt source/direct object, còn CASCADE có thể tác động thêm nhiều objects không được nêu trực tiếp.

### Bài 26. `is_temporary` phục vụ gì?

**Đáp án:** nhận diện object tạm thời trong metadata dropped objects nếu được ghi nhận.

### Bài 27. `DROP TABLE IF EXISTS missing` có thể kích hoạt guard start không?

**Đáp án:** có thể, vì command tag đã được biết trước existence check.

### Bài 28. `ddl_command_start` có lấy được metadata object mới đã tạo không?

**Đáp án:** không nên kỳ vọng, vì event xảy ra trước phần thực thi DDL.

### Bài 29. Có nên parse current_query bằng LIKE để bảo vệ schema finance không?

**Đáp án:** không; đó không phải SQL parser đáng tin cậy. Dùng quyền/ownership và policy được thiết kế đúng.

### Bài 30. Vì sao một exception ở event trigger có thể rollback DDL?

**Đáp án:** handler chạy trong transaction/lệnh DDL; exception không được xử lý làm statement thất bại.

### Bài 31. Audit INSERT giữ được sau ROLLBACK của DDL không?

**Đáp án:** thường không. Audit row trong cùng transaction cũng rollback.

### Bài 32. Muốn lưu failed DDL attempts cần gì?

**Đáp án:** logs/giải pháp ngoài transaction DDL hoặc cơ chế audit độc lập, không chỉ INSERT vào bảng cùng transaction.

### Bài 33. `table_rewrite` xảy ra trước hay sau rewrite?

**Đáp án:** trước rewrite.

### Bài 34. Lấy OID bảng sắp rewrite bằng hàm nào?

**Đáp án:** `pg_event_trigger_table_rewrite_oid()`.

### Bài 35. Lấy reason bằng hàm nào?

**Đáp án:** `pg_event_trigger_table_rewrite_reason()`, trả bitmask integer.

### Bài 36. Mọi `ALTER TABLE ADD COLUMN` đều rewrite bảng?

**Đáp án:** không. Phụ thuộc loại thay đổi, version và thuộc tính cột/DDL cụ thể.

### Bài 37. Event trigger được áp dụng toàn cluster không?

**Đáp án:** không. Nó thuộc database hiện tại.

### Bài 38. Có capture `CREATE ROLE` qua event trigger ở database không?

**Đáp án:** không theo cơ chế event triggers áp cho shared objects; dùng hệ thống logs/audit phù hợp.

### Bài 39. `SECURITY INVOKER` handler lấy quyền từ đâu?

**Đáp án:** effective caller role; nếu role thực hiện DDL thiếu INSERT audit table, handler có thể lỗi.

### Bài 40. Vì sao không nên SECURITY DEFINER với superuser owner?

**Đáp án:** lỗi code/name resolution có thể chạy dưới quyền quá rộng. Dùng owner riêng ít quyền.

### Bài 41. `CURRENT_USER` trong definer handler có phải DDL invoker?

**Đáp án:** không nhất thiết; nó thường là owner của definer function trong context đó.

### Bài 42. Vì sao `SESSION_USER` không đủ nhận diện web user?

**Đáp án:** nhiều web users có thể dùng chung một database login/connection pool.

### Bài 43. Search path an toàn nên trông như thế nào?

**Đáp án gợi ý:** `pg_catalog, et_lab, pg_temp` với `et_lab` là trusted schema và sensitive tables/functions được định danh đầy đủ.

### Bài 44. Vì sao tránh DDL trong event handler?

**Đáp án:** có thể recursion, tăng lock/overhead và side effects khó kiểm soát.

### Bài 45. `ALTER EVENT TRIGGER ... DISABLE` có xóa object không?

**Đáp án:** không. Nó chuyển enabled mode, trigger vẫn có trong catalog.

### Bài 46. Kiểm kê event triggers bằng catalog nào?

**Đáp án:** `pg_event_trigger` với các trường `evtname`, `evtevent`, `evtenabled`, `evttags`, `evtfoid`, `evtowner`.

### Bài 47. `evttags IS NULL` có nghĩa lỗi không?

**Đáp án:** không nhất thiết; trigger có thể không định nghĩa `WHEN TAG IN`.

### Bài 48. Vì sao event trigger không thay PostgreSQL logging?

**Đáp án:** event trigger tạo object-level metadata trong transaction, còn logs có thể lưu statements và attempts/failures ngoài semantics của audit table.

### Bài 49. Vì sao phải kiểm thử `DROP CASCADE` và extension upgrades?

**Đáp án:** nhiều dependency objects và extension-script DDL có thể tác động command tags/handler, làm migrations fail nếu policy quá rộng.

### Bài 50. Lập checklist triển khai production

**Đáp án gợi ý:**

1. Xác định mục tiêu: block, audit created/altered objects, dropped objects hay table rewrite.
2. Chọn đúng event và helper function theo event.
3. Tạo audit schema/table trước khi bật trigger.
4. Dùng owner role ít quyền và trusted search_path.
5. Cân nhắc handler INVOKER/DEFINER và quyền INSERT audit.
6. Không cho untrusted sửa audit code/schema.
7. Giới hạn tags chỉ khi cần, test coverage với DDL thật.
8. Không viết DDL đệ quy trong handler.
9. Test CREATE/ALTER/DROP CASCADE/rewrite/rollback.
10. Test lỗi quyền, audit table unavailable và recovery.
11. Theo dõi `pg_event_trigger`, hiệu năng, WAL và lock duration.
12. Chuẩn bị DBA runbook cho DISABLE/DROP và dọn đúng thứ tự.

## 39. Ma trận kiểm thử dành cho dự án

| Scenario | Sự kiện/điều cần quan sát | Kỳ vọng |
| --- | --- | --- |
| CREATE TABLE mới | `ddl_command_end` | Metadata object được ghi |
| ALTER TABLE ADD COLUMN | `ddl_command_end` | Metadata thay đổi phù hợp |
| CREATE INDEX | `ddl_command_end` với tag phù hợp | Có command record |
| DROP TABLE không phụ thuộc | `sql_drop` | Có dropped object metadata |
| DROP TABLE CASCADE | `sql_drop` | Liệt kê nhiều objects phụ thuộc |
| DROP TABLE IF EXISTS missing | `ddl_command_start` có thể chạy | Không tự khẳng định đã xóa object |
| ALTER TABLE rewrite type | `table_rewrite` | Có OID/reason khi rewrite thực xảy ra |
| ALTER TABLE metadata-only | `table_rewrite` | Có thể không phát event |
| CREATE FUNCTION | `ddl_command_end` nếu không filter loại | Không bị loại vì filter sai |
| CREATE EXTENSION | Extension scripts | Kiểm tra `in_extension` |
| CREATE ROLE | Shared-object DDL | Không kỳ vọng event trigger capture |
| CREATE EVENT TRIGGER | Event-trigger DDL | Ngoại lệ event trigger machinery |
| ROLLBACK sau CREATE TABLE | Transaction semantics | Table và row audit cùng rollback |
| Handler raise exception | DDL command | DDL bị từ chối/rollback theo scope |
| Caller DDL thiếu INSERT audit | Handler INVOKER | Lỗi quyền nếu không có thiết kế grants |
| Handler DEFINER owner rộng | Security review | Không chấp nhận owner quá quyền |
| Handler chứa dynamic DDL | Recursion review | Tránh vòng lặp/hành vi không kiểm soát |
| Audit table bị drop | Recovery | Có runbook và quyền admin |
| DISABLE event trigger | pg_event_trigger | Catalog mode thay đổi |
| Nhiều statements cùng transaction | Audit grouping | Nhiều rows có thể cùng transaction_id |
| Connection pool/shared login | Attribution | Không nhầm DB login với end user |
| Migration trên bảng lớn | Performance | Đo locks/latency/WAL thực tế |

## 40. Checklist vận hành và bảo mật

| Câu hỏi | Điều cần bảo đảm |
| --- | --- |
| Đã rõ mục tiêu event trigger chưa? | Audit/block/monitor rõ ràng |
| Đã dùng database thử nghiệm riêng? | Không vô tình ảnh hưởng production |
| Có quyền superuser để tạo? | Kiểm tra provider/quyền |
| Có biết event triggers thuộc database nào? | Không nhầm cluster-wide |
| Có bảng audit trước khi bật hook? | Không làm DDL đầu tiên lỗi |
| Handler có `RETURNS event_trigger`? | Kiểu đúng |
| Helper function dùng đúng event? | ddl_commands/end; dropped_objects/drop |
| Có tách TG_EVENT/TG_TAG? | Event name vs command tag |
| Có dùng WHEN TAG IN phù hợp? | Không bỏ sót DDL quan trọng |
| Có kiểm thử CREATE TABLE AS? | Command tag/coverage theo version |
| Có capture phụ thuộc CASCADE? | Dùng sql_drop helper |
| Có lưu object_identity/object_type/schema? | Metadata đủ dùng |
| Có làm mất audit khi rollback? | Đã hiểu và chấp nhận |
| Có nguồn failed attempt logs? | Kênh ngoài transaction nếu cần |
| Có yêu cầu SQL text gốc? | Không trông chờ pg_ddl_command như raw text |
| Có xử lý table rewrite? | OID/reason và cost/locks |
| Có hardcode reason bitmask? | Chỉ khi xác minh theo version |
| Handler có DDL gây recursion? | Tránh |
| Handler có query/log quá nặng? | Hạn chế overhead |
| Handler thiếu quyền INSERT audit? | Kiểm tra multi-role |
| Handler SECURITY DEFINER? | Owner least privilege |
| Có trusted search_path? | pg_catalog, trusted, pg_temp |
| Có schema qualification? | Sensitive objects |
| Có audit của web user cuối không? | Identity đáng tin, không chỉ session_user |
| Schema audit có quyền CREATE rộng? | Không |
| Có bảo vệ audit table khỏi sửa/xóa? | Grants/ownership/retention |
| Có track event trigger state? | pg_event_trigger |
| Có runbook DISABLE/DROP? | Quyền admin đủ khi sự cố |
| Có test migrations/extensions? | Không chặn ngoài ý muốn |
| Có test DDL thất bại? | Kiểm tra rollback/exception |
| Có test transaction dài? | Lock/WAL/time |
| Có metrics migration overhead? | Before/after ở staging |
| Có backup và rollback plan? | Không dựa event trigger như backup |
| Có phương án xóa lab? | Drop event triggers trước schema |
| Có xác minh không ảnh hưởng shared objects? | Dùng logs/công cụ riêng |
| Có document chính sách? | Team migrations nắm được |
| Có periodic review? | Theo dõi owner/tag/path changes |

## 41. Tổng kết

Event triggers là cơ chế PostgreSQL để quan sát và can thiệp vào những thay đổi DDL **ngay trong database**.

Các nguyên tắc quan trọng:

1. **Event trigger khác table trigger.** Nó không quan sát từng row; nó quan sát những DDL commands/sự kiện được hỗ trợ.
2. **`ddl_command_start`** chạy trước DDL, phù hợp với guard theo command tag, nhưng object metadata cuối cùng chưa chắc có sẵn.
3. **`ddl_command_end`** chạy sau phần DDL hoàn thành, trước transaction commit; dùng `pg_event_trigger_ddl_commands()` để lấy object-level metadata.
4. **`sql_drop`** cho metadata những objects bị xóa, kể cả phụ thuộc CASCADE, qua `pg_event_trigger_dropped_objects()`.
5. **`table_rewrite`** chạy ngay trước physical rewrite, với OID và bitmask reason.
6. **Hàm xử lý phải `RETURNS event_trigger`**, dùng `TG_EVENT`/`TG_TAG` đúng ngữ cảnh.
7. **`WHEN TAG IN (...)` lọc theo command tag**, không phải tên table/schema.
8. **Một DDL có thể phát nhiều audit records**, và không phải mọi loại DDL đều được event trigger hỗ trợ.
9. **Event triggers thuộc từng database**, không mặc định áp dụng cho cả cluster.
10. **Shared objects như roles/databases/tablespaces và DDL event-trigger-specific có ngoại lệ**; muốn audit toàn diện cần nguồn khác.
11. **Audit INSERT cùng transaction có thể rollback cùng DDL**. Event trigger không phải bản ghi bất biến về mọi lần thử DDL.
12. **`pg_ddl_command` không phải raw SQL text**; cần logs/migration history khi cần câu SQL nguyên gốc.
13. **Không dùng DDL động/handler nặng một cách tùy tiện** vì recursion, lock contention và migration failures.
14. **SECURITY DEFINER cần owner ít quyền và search_path an toàn**; đừng cho app role chỉnh audit functions.
15. **Actor attribution cần hiểu effective role/session role**, đặc biệt với shared database connection và definer context.
16. **Quyền DDL là hàng rào chính**; event trigger guard bổ sung, không thay `GRANT`/ownership.
17. **Cần kiểm tra catalog và trạng thái ENABLE/DISABLE**, cùng monitoring và incident runbook.
18. **Triển khai tuần tự:** audit table → handler functions → event triggers → integration tests → giám sát.
19. **Kiểm thử cả rollback, DROP CASCADE, table rewrite, extension upgrades và nhiều roles**, không chỉ CREATE TABLE đơn giản.
20. **Chỉ dùng trên production khi đã đo và có đường khôi phục**, bởi một lỗi trong handler có thể chặn các schema migrations.

Mẫu dễ ghi nhớ:

```sql
-- Hàm được tạo trước, trả về event_trigger.
CREATE OR REPLACE FUNCTION et_lab.short_ddl_notice()
RETURNS event_trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, et_lab, pg_temp
AS $fn$
BEGIN
    RAISE NOTICE
        'DDL event: %, command tag: %',
        TG_EVENT,
        TG_TAG;
END;
$fn$;

-- Quản trị viên tạo event trigger trong database lab.
CREATE EVENT TRIGGER et_lab_short_notice
ON ddl_command_end
WHEN TAG IN ('CREATE TABLE', 'ALTER TABLE')
EXECUTE FUNCTION et_lab.short_ddl_notice();
```

Để lấy metadata chi tiết của objects, chuyển sang `pg_event_trigger_ddl_commands()` trong handler `ddl_command_end`; để audit DROP, dùng `sql_drop` cùng `pg_event_trigger_dropped_objects()`; để nhận biết rewrite, dùng `table_rewrite` và hai helper functions tương ứng.

**Quy tắc cuối cùng:** trước khi cài một event trigger, phải trả lời rõ: **“Tôi cần quan sát loại DDL nào, metadata nào thực sự có ở thời điểm hook, audit có cần sống qua rollback không, handler chạy dưới quyền ai, và nếu handler lỗi thì ai có thể khôi phục database?”**. Khi có câu trả lời cho cả năm câu hỏi, event trigger mới trở thành công cụ quản trị hữu ích thay vì một nguồn rủi ro cho hệ thống.
