# Phân quyền cơ sở dữ liệu cho chạy Task và quản lý schema

## 1. Vì sao phân quyền database là một phần của vận hành Spring Cloud Task?

**Spring Cloud Task** dùng để chạy ứng dụng Spring Boot có thời gian sống hữu hạn: đối soát giao dịch, nhập file, xuất báo cáo hoặc khởi chạy Spring Batch Job. Khi được cấu hình JDBC, framework ghi metadata của từng lần chạy vào **TaskRepository**, chẳng hạn tên task, thời điểm bắt đầu/kết thúc, mã thoát và tham số.

Một tác vụ có thể chỉ chạy vài phút nhưng lại có quyền truy cập database rất rộng. Nếu tài khoản chạy task được phép `CREATE`, `ALTER`, `DROP` hoặc là chủ sở hữu mọi bảng, một lỗi cấu hình hay lỗ hổng trong code có thể thay đổi cấu trúc schema, xóa lịch sử thực thi hoặc làm hỏng dữ liệu nghiệp vụ.

Ví dụ một `daily-close-task` chạy mỗi đêm:

- Nó **cần** ghi TaskExecution mới và cập nhật trạng thái khi kết thúc.
- Nó có thể **cần** ghi kết quả chốt ngày trong một schema nghiệp vụ.
- Nó **không cần** tạo lại các bảng metadata vào mỗi lần startup.
- Nó **không nên** có quyền thay đổi DDL của toàn database.
- Người vận hành đọc lịch sử task **không nhất thiết** được đọc mọi command-line argument vì argument có thể chứa dữ liệu nhạy cảm.

Giải pháp là phân chia **quyền vận hành runtime**, **quyền quản lý schema/migration**, **quyền đọc giám sát** và **quyền truy cập dữ liệu nghiệp vụ**.

> **Nguyên tắc cốt lõi:** tiến trình task chỉ được cấp quyền phục vụ những thao tác mà nó cần thực hiện tại runtime. Việc tạo, nâng cấp hoặc xóa bảng nên là một bước triển khai có kiểm soát, không đi kèm quyền của tài khoản chạy task.

Bài dùng **PostgreSQL** làm ví dụ chính. Cú pháp `GRANT`, `ALTER DEFAULT PRIVILEGES`, schema và sequence không thể chép nguyên sang MySQL, SQL Server hay Oracle; phải điều chỉnh theo hệ quản trị và DDL Spring Cloud Task của phiên bản dự án.

## 2. Xác định ranh giới giữa TaskRepository, JobRepository và business schema

Một ứng dụng có thể dùng một hoặc nhiều DataSource:

~~~mermaid
flowchart TD
    S["Scheduler / Kubernetes Job"] --> T["Spring Cloud Task JVM"]
    T --> C["TaskRepository"]
    T --> B["Spring Batch JobRepository (nếu có)"]
    T --> D["Business DB"]
    C --> CM["Schema task_meta: TASK_*"]
    B --> BM["Schema batch_meta: BATCH_*"]
    D --> DM["Schema finance: bảng nghiệp vụ"]
    M["Migration Job / CI-CD"] --> CM
    M --> BM
    M --> DM
    O["Monitoring/TaskExplorer"] --> CM
~~~

| Phạm vi | Đối tượng điển hình | Tài khoản dùng để làm gì? | Có cần quyền DDL lúc runtime? |
|---|---|---|---|
| **TaskRepository** | `TASK_EXECUTION`, `TASK_EXECUTION_PARAMS`, `TASK_TASK_BATCH`, `TASK_LOCK` | Lưu và tra trạng thái các lần chạy | Không, khi schema đã migrate |
| **Spring Batch JobRepository** | `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, context, sequence | Quản lý Job/Step/checkpoint/restart | Không, khi schema đã migrate |
| **Business schema** | `finance.daily_close`, hóa đơn, giao dịch | Xử lý dữ liệu nghiệp vụ | Thường không |
| **Migration metadata** | Bảng lịch sử Flyway hoặc Liquibase | Biết migration nào đã áp dụng | Được quản lý bởi quy trình migration |
| **Monitoring** | View hoặc truy vấn metadata | Quan sát, báo cáo, điều tra sự cố | Không |

**TaskRepository không phải JobRepository.** Việc cấp quyền cho `TASK_*` không tự cấp quyền cho `BATCH_*`. Nếu task dùng Spring Batch, cần xem xét quyền của Batch runtime riêng. Nếu sử dụng một JDBC user cho cả ba nhóm, user đó sở hữu **tổng quyền**; nên hạn chế theo schema và tách DataSource khi có yêu cầu bảo mật cao hơn.

Tên bảng ở đây là ví dụ theo schema metadata thông dụng. **Phải đối chiếu DDL được đóng gói cùng phiên bản Spring Cloud Task/Spring Batch đang chạy**, nhất là khi đã tùy chỉnh `tablePrefix`, schema hoặc cơ chế tạo ID.

## 3. Phân vai: migration, runtime, monitoring và quản trị

Mô hình khuyến nghị:

| Vai trò | Có thể làm | Không nên có |
|---|---|---|
| `task_migrator` | Tạo/sửa schema metadata, tạo bảng/sequence/index, nâng cấp DDL | Quyền superuser hoặc sửa schema ngoài phạm vi quản lý |
| `task_runtime` | Đọc/ghi metadata TaskRepository theo thao tác framework cần | `CREATE` trên schema, `DROP`/`ALTER` object, `GRANT OPTION` |
| `task_observer` | Đọc các bảng hoặc view được chọn để quan sát | `INSERT`, `UPDATE`, `DELETE`, đọc dữ liệu nhạy cảm không cần thiết |
| `batch_runtime` | DML và sequence cần cho JobRepository | DDL trên schema Batch |
| `business_runtime` | Các thao tác nghiệp vụ được cấp cụ thể | DDL hoặc truy cập toàn bộ tenant/schema khác |
| DBA/platform administrator | Quản lý role, backup, khôi phục và quyền cấp cao | Không dùng làm credential thường trực trong ứng dụng |

Với quy mô nhỏ, `task_runtime` và `business_runtime` có thể là một login có quyền trên hai schema đã giới hạn. Nhưng việc tách tài khoản/connection giúp giảm phạm vi ảnh hưởng nếu một service bị lộ credential hoặc chạy câu SQL ngoài dự kiến.

**Đừng nhầm tài khoản owner với tài khoản runtime.** Trong PostgreSQL, chủ sở hữu object có khả năng thay đổi hoặc xóa object theo quyền sở hữu, dù không được cấp quyền DML bằng `GRANT`. Vì vậy các bảng metadata nên được tạo bởi role migration/schema owner, **không phải** `task_runtime`.

## 4. Những quyền TaskRepository thực sự sử dụng

Spring Cloud Task thường cần tạo TaskExecution lúc bắt đầu, ghi tham số, cập nhật trạng thái cuối và đọc metadata để truy vấn/lấy trạng thái hiện tại. Khi bật các tính năng tích hợp, nó có thể cần thao tác thêm các bảng liên kết và khóa.

| Đối tượng | Chức năng | Quyền runtime thường cần xem xét |
|---|---|---|
| `TASK_EXECUTION` | Bản ghi cho một lần chạy task | `SELECT`, `INSERT`, `UPDATE` |
| `TASK_EXECUTION_PARAMS` | Tham số của lần chạy | `SELECT`, `INSERT` |
| `TASK_TASK_BATCH` | Liên kết TaskExecution với Batch JobExecution | `SELECT`, `INSERT` khi dùng tích hợp |
| `TASK_LOCK` | Phục vụ chế độ single-instance/locking | `SELECT`, `INSERT`, `UPDATE`, `DELETE` tùy implementation |
| `TASK_SEQ` hoặc đối tượng cấp ID tương đương | Cấp TaskExecution ID | Phụ thuộc **table hay native sequence** trong DDL |
| Bảng `BATCH_*` và các sequence Batch | Job/Step metadata | Tập quyền **riêng** cho Batch repository |

Bảng này là **danh mục khảo sát**, không phải một ma trận quyền tuyệt đối cho mọi release. Chẳng hạn một implementation của `TaskRepository` có thể dùng câu SQL khác hoặc có tính năng dọn metadata riêng cần `DELETE`. Hãy xác định quyền cần từ **hành vi thực tế và DDL phiên bản**, thay vì cấp `ALL PRIVILEGES` vì tiện.

### Sequence thật khác bảng giả lập sequence

Đây là điểm rất quan trọng:

- Với **PostgreSQL native sequence** (đối tượng có `relkind='S'`), lời gọi `nextval(...)` thường cần `USAGE` hoặc `UPDATE` trên sequence, không phải quyền `INSERT` vào table.
- Với **bảng giả lập sequence** (ví dụ `TASK_SEQ` là table, `relkind='r'`), framework có thể thực hiện `SELECT`/`UPDATE` trên table để tăng ID; `GRANT USAGE ON SEQUENCE` không có tác dụng.
- Một số DDL của Spring Cloud Task dùng **sequence table**; tài liệu cũng mô tả biến thể thay bằng native sequence trên một số hệ quản trị. Không được đoán loại đối tượng chỉ dựa vào hậu tố `_SEQ`.

Các quyền `SELECT`, `USAGE`, `UPDATE` trên sequence không hoàn toàn tương đương. Tránh cấp `ALL` cho sequence nếu chỉ cần `nextval`; mở thêm quyền khi đã kiểm tra cách JDBC incrementer hoạt động.

## 5. Kiểm tra schema và loại đối tượng trước khi cấp quyền

Trước khi viết GRANT, dùng tài khoản DBA/migrator để xác định chính xác cấu trúc đã tồn tại:

~~~sql
-- PostgreSQL: liệt kê các đối tượng trong schema TaskRepository.
SELECT
    n.nspname AS schema_name,
    c.relname AS object_name,
    c.relkind AS object_kind,
    pg_get_userbyid(c.relowner) AS owner_name
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'task_meta'
ORDER BY c.relname;
~~~

Các giá trị `relkind` thường thấy:

| Giá trị | Loại đối tượng |
|---|---|
| `r` | Ordinary table |
| `S` | Sequence |
| `v` | View |
| `m` | Materialized view |
| `p` | Partitioned table |

Ví dụ, nếu thấy `task_seq` có `relkind='r'`, dùng **table privileges**. Nếu nó có `relkind='S'`, dùng **sequence privileges**. Nếu không thấy đối tượng, có thể DDL chưa chạy, prefix khác, hoặc kết nối trỏ sai schema.

### Kiểm tra tài khoản và search path

~~~sql
SELECT current_database() AS db_name,
       current_user AS db_user,
       current_schema() AS active_schema;

SHOW search_path;

SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'task_meta'
ORDER BY table_name;
~~~

Lưu ý PostgreSQL gấp đôi chữ hoa/thường trong tên object **không được quote**: `TASK_EXECUTION` trong SQL thường tương đương `task_execution`. Nếu migration tạo tên bằng double quotes, ví dụ `"TASK_EXECUTION"`, cách truy cập phải nhất quán với đúng kiểu đặt tên. Đừng khắc phục lỗi phân quyền bằng cách tùy tiện đổi tên bảng tại runtime.

## 6. Ví dụ PostgreSQL: tạo role và schema riêng

Giả sử database là `appdb`, metadata Task nằm trong schema `task_meta`. Một người quản trị DB thực hiện phần cấp role và tạo schema:

~~~sql
-- Chạy bằng vai trò quản trị được phép tạo role/schema.
-- Không lưu password thật trong migration hay tài liệu.
CREATE ROLE task_migrator LOGIN;
CREATE ROLE task_runtime LOGIN;
CREATE ROLE task_observer LOGIN;

GRANT CONNECT ON DATABASE appdb
    TO task_migrator, task_runtime, task_observer;

CREATE SCHEMA task_meta AUTHORIZATION task_migrator;

REVOKE ALL ON SCHEMA task_meta FROM PUBLIC;

GRANT USAGE ON SCHEMA task_meta TO task_runtime;
GRANT USAGE ON SCHEMA task_meta TO task_observer;
~~~

**Đây là mô hình vai trò, không phải script production copy-paste không kiểm tra.** Khi triển khai thật, role có thể đã tồn tại; việc xác thực nên dùng secret manager/IAM/cơ chế của DB platform. `CREATE ROLE ... LOGIN` không thiết lập password trực tiếp trong ví dụ. Nếu chính sách mạng hoặc cơ chế xác thực yêu cầu credential, tạo/cấp chúng qua quy trình bảo mật riêng.

Điểm cần nhớ:

- `USAGE ON SCHEMA` cho phép tham chiếu object trong schema **khi cũng có quyền trên object**; nó không tự cấp `SELECT`/`INSERT` cho bảng.
- `CREATE ON SCHEMA` cho phép tạo object mới; **không cấp** cho `task_runtime`.
- Role `task_migrator` là owner của schema, thực hiện DDL trong migration job; không được đưa credential đó vào worker task.
- `GRANT CONNECT` có thể không tự cô lập việc kết nối nếu quyền `CONNECT` vẫn còn được cấp cho `PUBLIC` theo mặc định. Nếu cần chính sách chỉ những role cụ thể được kết nối, DBA phải kiểm tra và thay đổi các quyền ở phạm vi database theo kế hoạch, tránh `REVOKE` làm gián đoạn ứng dụng khác.
- Cần kiểm tra cả quyền `TEMP`, schema `public` và những schema khác có trong `search_path` nếu yêu cầu cô lập nghiêm ngặt.

## 7. Cấp DML theo từng bảng TaskRepository sau khi chạy migration

**Bước tạo schema/DDL phải hoàn tất trước**, sau đó mới cấp quyền cho runtime. Các câu lệnh dưới đây giả định các bảng tương ứng đã được tạo trong `task_meta`. Nếu tính năng không dùng hoặc DDL không có một bảng, **bỏ qua câu GRANT tương ứng**; không tự tạo một bảng rỗng chỉ để GRANT chạy được.

~~~sql
-- Các quyền lõi cho vòng đời TaskExecution.
GRANT SELECT, INSERT, UPDATE
ON TABLE task_meta.task_execution
TO task_runtime;

GRANT SELECT, INSERT
ON TABLE task_meta.task_execution_params
TO task_runtime;

-- Chỉ nếu Task-Batch integration dùng bảng liên kết.
GRANT SELECT, INSERT
ON TABLE task_meta.task_task_batch
TO task_runtime;

-- Chỉ nếu schema/tính năng single-instance dùng TASK_LOCK.
GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE task_meta.task_lock
TO task_runtime;
~~~

Nếu runtime có thêm trách nhiệm xóa/làm sạch metadata hoặc dùng một phiên bản DAO có SQL khác, xác minh và bổ sung **quyền trên đối tượng thật sự cần**, không cấp mặc định `DELETE ON ALL TABLES` để tránh lỗi.

### Trường hợp TASK_SEQ là table

~~~sql
-- CHỈ chạy nếu task_meta.task_seq là ordinary table (relkind='r').
-- Các quyền cuối phải khớp SQL thực tế của incrementer.
GRANT SELECT, UPDATE
ON TABLE task_meta.task_seq
TO task_runtime;
~~~

Nếu implementation dùng `INSERT` trong cơ chế khởi tạo/tăng ID tại runtime, phải xem lại thiết kế initializer và quyền tương ứng. Khi tách migration khỏi runtime, bảng sequence nên được **khởi tạo trước** bởi migration.

### Trường hợp TASK_SEQ là native sequence

~~~sql
-- CHỈ chạy nếu task_meta.task_seq là sequence (relkind='S').
GRANT USAGE
ON SEQUENCE task_meta.task_seq
TO task_runtime;
~~~

Không chạy đồng thời hai câu GRANT trên cùng tên object: trong một schema, object đó không thể vừa là ordinary table vừa là sequence. Nếu framework dùng `SELECT` hoặc `setval`, quyền có thể khác; phải kiểm tra version và chạy smoke test bằng chính role runtime.

### Quyền quan sát

~~~sql
-- Cho phép theo dõi trạng thái cơ bản.
GRANT SELECT
ON TABLE task_meta.task_execution
TO task_observer;
~~~

`TASK_EXECUTION_PARAMS` có thể chứa **arguments thô** của task. Không tự cấp `SELECT` bảng này cho mọi người có quyền xem dashboard. Có thể tạo một **view đã hạn chế cột** hoặc dịch vụ `TaskExplorer` có phân quyền để kiểm soát mức dữ liệu được hiển thị.

## 8. ALTER DEFAULT PRIVILEGES: áp dụng cho bảng tạo trong tương lai

Migration mới có thể tạo thêm index, table hoặc sequence. `GRANT` hiện tại **không tự áp dụng** cho mọi object được tạo về sau.

PostgreSQL có `ALTER DEFAULT PRIVILEGES` để quy định quyền mặc định cho các object **sẽ được tạo bởi một role cụ thể**:

~~~sql
-- Chạy dưới task_migrator hoặc người có quyền quản lý role đó.
ALTER DEFAULT PRIVILEGES
FOR ROLE task_migrator
IN SCHEMA task_meta
GRANT SELECT, INSERT, UPDATE
ON TABLES TO task_runtime;

ALTER DEFAULT PRIVILEGES
FOR ROLE task_migrator
IN SCHEMA task_meta
GRANT USAGE
ON SEQUENCES TO task_runtime;
~~~

Đây là **ví dụ quyền mặc định theo phạm vi schema**, thuận tiện cho tổ chức muốn các bảng metadata mới có khả năng đọc/ghi tương tự. Nó có thể rộng hơn nhu cầu tối thiểu của từng bảng. Với yêu cầu least privilege chặt, cách tốt hơn là **ghi GRANT theo object trong mỗi migration** và kiểm tra tự động sau deploy.

Hai hiểu nhầm quan trọng:

1. `ALTER DEFAULT PRIVILEGES` chỉ ảnh hưởng **object tạo trong tương lai**, không bổ sung quyền cho các bảng đã có; các GRANT hiện tại vẫn phải thực hiện riêng.
2. Nó áp dụng cho object tạo bởi **role được chỉ định** trong ngữ cảnh PostgreSQL. Nếu migration chạy dưới role khác, quy tắc `FOR ROLE task_migrator` không tự áp dụng. Cần kiểm tra `current_user` thực tế khi DDL chạy.

Không cấp default `ALL PRIVILEGES` cho runtime; đặc biệt tránh `TRUNCATE`, `REFERENCES`, `TRIGGER` hoặc quyền có thể làm tăng phạm vi ảnh hưởng nếu không có nhu cầu đã chứng minh.

## 9. Tách DDL/migration khỏi startup của ứng dụng Task

Spring Cloud Task có thể khởi tạo metadata schema ở startup theo cấu hình và tính khả dụng của platform. Nhưng nếu runtime role không có quyền `CREATE TABLE`, một startup cố chạy DDL sẽ thất bại, **dù các quyền DML hoàn toàn đúng**.

Khi schema được quản lý bên ngoài bằng Flyway, Liquibase hoặc DBA, cấu hình thường dùng:

~~~yaml
spring:
  main:
    web-application-type: none
  application:
    name: daily-close-task

  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}

  cloud:
    task:
      name: daily-close-task
      initialize-enabled: false
~~~

Các giá trị `${TASK_DB_URL}`, `${TASK_DB_USER}`, `${TASK_DB_PASSWORD}` trong ví dụ đại diện cho Spring property placeholders: runtime phải cung cấp biến qua secret/environment theo hạ tầng.

**`spring.cloud.task.initialize-enabled=false`** tắt cơ chế init schema TaskRepository do Spring Cloud Task quản lý theo dòng phiên bản có hỗ trợ. Khi đặt property này, dự án chịu trách nhiệm **tạo đủ bảng/sequence/index trước khi task chạy**.

Nếu cũng dùng Spring Batch hoặc auto-init SQL khác, cần xem xét riêng:

~~~properties
spring.batch.jdbc.initialize-schema=never
spring.sql.init.mode=never
~~~

Đây là các property Spring Boot thường dùng ở những phiên bản hỗ trợ. `spring.batch.jdbc.initialize-schema=never` tắt khởi tạo schema **Batch**, không ảnh hưởng trực tiếp tới Spring Cloud Task initializer. `spring.sql.init.mode=never` điều khiển SQL initializer chung, không thay thế cấu hình migration tool.

Nếu dùng Flyway/Liquibase **trong cùng JVM runtime** nhưng lại trỏ migration vào schema bằng user chỉ có DML, app có thể tiếp tục lỗi ở khởi động. Để tách quyền sạch sẽ, cần một **migration job riêng** chạy trước, hoặc một cơ chế datasource migration với credential riêng được kiểm soát và không làm lộ quyền đó cho runtime task.

## 10. Pipeline triển khai an toàn: migrate trước, chạy Task sau

Một quy trình hợp lý cho CI/CD:

~~~mermaid
sequenceDiagram
    participant P as CI/CD Pipeline
    participant M as Migration Job
    participant DB as PostgreSQL
    participant T as Runtime Spring Cloud Task
    participant S as Scheduler / Job Controller

    P->>DB: Kiểm tra version + backup/restore plan
    P->>M: Launch bằng task_migrator
    M->>DB: DDL + schema history + GRANT
    DB-->>M: Commit migration thành công
    M-->>P: Exit 0
    P->>S: Cho phép chạy task phiên bản mới
    S->>T: Khởi chạy bằng task_runtime
    T->>DB: DML TaskRepository + business data đã được cấp
    DB-->>T: Kết quả
    T-->>S: Exit code, task lifecycle
~~~

**Tách hai bước có lợi ích bảo mật:**

- Nếu runtime pod bị chiếm quyền, attacker không có credential migration để `ALTER` hay `DROP` bảng.
- Schema được nâng cấp có thể được review, version hóa và triển khai có thứ tự.
- Không xảy ra nhiều task cùng startup đồng thời cố tạo bảng metadata.
- Quyền cấp mới có thể được kiểm tra qua một bước smoke test trước khi scheduler bật lại.
- Rollback ứng dụng không đồng nghĩa có thể rollback DDL; cần kế hoạch tương thích dữ liệu và backup.

Có thể quản lý migration bằng Flyway hoặc Liquibase nhưng **không bắt buộc** dùng cả hai. Đặc biệt khi nhiều service cùng dùng metadata schema, chỉ một quy trình được phép quản lý DDL để tránh tranh chấp và drift.

### Không chạy migration bằng startup hook của mỗi Task

Không nên đặt `CREATE TABLE IF NOT EXISTS` hoặc `ALTER TABLE` trong `ApplicationRunner` của task. Ngoài việc buộc runtime có DDL privilege, nhiều replica/Job retry có thể chạy song song gây race và lỗi schema. DDL nên được quản lý tập trung; task chỉ xác minh dependency sẵn sàng.

## 11. Cấu hình schema và tablePrefix phải khớp DDL

Một lỗi phổ biến: bảng thực sự nằm trong `task_meta` nhưng runtime tìm ở `public`, hoặc DDL dùng prefix khác với SQL do TaskRepository tạo.

Spring Cloud Task có thuộc tính **`spring.cloud.task.tablePrefix`** (thường cũng viết dạng Spring Boot relaxed binding `spring.cloud.task.table-prefix`) để thay prefix mặc định `TASK_`. Trước khi áp dụng, phải xác nhận chính xác cách ghép schema/table name trên bản đang dùng.

Ví dụ nếu dùng schema PostgreSQL `task_meta` và các bảng có tên không quote thông thường:

~~~yaml
spring:
  cloud:
    task:
      initialize-enabled: false
      table-prefix: task_meta.TASK_
~~~

Mục tiêu minh họa là runtime tạo SQL tham chiếu `task_meta.TASK_EXECUTION`. **Không tự giả định** prefix thêm schema hoạt động giống nhau trong mọi custom `TaskConfigurer`, SQL generator hoặc phiên bản; cần kiểm tra SQL thực tế và migration tương ứng.

Một cách khác là giữ prefix `TASK_` và cấu hình kết nối JDBC sử dụng schema mặc định `task_meta`, ví dụ:

~~~properties
spring.datasource.url=jdbc:postgresql://db.internal:5432/appdb?currentSchema=task_meta
spring.cloud.task.initialize-enabled=false
~~~

Nếu dùng cách này, người vận hành phải kiểm tra **search_path hiệu lực** và DataSource mà TaskRepository thực sự sử dụng. Đừng kết hợp schema-qualified prefix, `currentSchema` và `search_path` một cách ngẫu nhiên rồi tạo ra tham chiếu hai lần schema.

### Rủi ro search_path

Trong PostgreSQL, việc để schema mà role không đáng tin có thể `CREATE` object đứng trước schema dự kiến trong `search_path` có thể gây vấn đề an toàn khi resolution các tên không đầy đủ. Với runtime task:

- Chỉ sử dụng các schema **tin cậy** trong search path.
- Không cấp `CREATE` trên schema metadata cho runtime.
- Kiểm tra chính sách schema `public` theo version/DB đã nâng cấp.
- Ưu tiên tên đối tượng schema-qualified ở script quản trị.
- Tách tenant/schema nếu mức cô lập yêu cầu, không dựa vào search path như cơ chế phân quyền duy nhất.

## 12. Khi có Spring Batch: quyền JobRepository độc lập

Một task có thể chạy Spring Batch Job để xử lý hàng triệu bản ghi theo chunk. Spring Batch lưu Job/Step metadata và ExecutionContext trong các bảng `BATCH_*`, có thể cần quyền `SELECT`, `INSERT`, `UPDATE` và quyền trên các đối tượng cấp ID.

Ví dụ thiết kế riêng schema:

~~~text
appdb
├── task_meta    -> task_runtime, task_migrator
├── batch_meta   -> batch_runtime, batch_migrator
└── finance      -> finance_runtime, finance_migrator
~~~

Một migration cho `batch_meta` phải dùng **DDL Spring Batch tương ứng**. Đối với PostgreSQL, DDL thường có native sequences như:

~~~text
BATCH_JOB_INSTANCE_SEQ
BATCH_JOB_EXECUTION_SEQ
BATCH_STEP_EXECUTION_SEQ
~~~

Đây là tên tham khảo, phải kiểm tra script thực tế vì tên/version có thể khác. Nếu native sequence được dùng, `batch_runtime` cần quyền sequence tương ứng, thường là `USAGE` cho `nextval`. Mất quyền sequence có thể khiến job không launch được dù các bảng `BATCH_JOB_INSTANCE` và `BATCH_JOB_EXECUTION` đã có quyền DML.

Đừng cấp `ALL PRIVILEGES ON ALL TABLES IN SCHEMA batch_meta` chỉ vì một Step cần ghi dữ liệu nghiệp vụ. Chia rõ:

- Quyền metadata Batch cho JobRepository.
- Quyền của business writer/reader cho các bảng mà Step xử lý.
- Quyền quản lý schema/DDL cho migration role.
- Quyền quan sát chỉ đọc cho dashboard, nếu có.

Với nhiều DataSource và transaction manager, ứng dụng phải được cấu hình để **TaskRepository dùng đúng DataSource Task**, JobRepository dùng đúng DataSource Batch, và service nghiệp vụ dùng transaction manager tương ứng. `@Transactional` không tự chọn đúng repository khi có nhiều transaction manager nếu cấu hình chưa được làm rõ.

## 13. Quyền xóa và dọn dẹp metadata: không mặc định cho runtime

Metadata task và Batch có thể tăng rất nhanh khi lịch chạy dày. Do đó cần chính sách **retention, archive và cleanup**, nhưng không nên cấp quyền `DELETE` rộng rãi cho mọi task.

Tách các vai trò:

| Hoạt động | Vai trò thường thực hiện |
|---|---|
| Tạo TaskExecution và cập nhật kết quả | `task_runtime` |
| Xóa/lưu trữ metadata quá thời hạn | `task_maintenance` hoặc controlled maintenance job |
| Phân tích lịch sử chạy | `task_observer`, view/dịch vụ read-only |
| Tạo index, thay đổi cột hoặc cleanup schema | `task_migrator` |
| Backup/restore/sửa quyền | DBA/platform administrator |

Với Spring Batch, xóa `JobInstance` hoặc `ExecutionContext` một cách tùy tiện có thể phá khả năng **restart Job đã thất bại**. Với TaskRepository, xóa TaskExecution còn đang chạy hoặc bảng liên kết có thể làm mất audit. Vì vậy cleanup phải có quy trình, điều kiện tuổi đời/trạng thái, backup và kiểm tra referential integrity.

**Quyền `DELETE` có thể vẫn cần trên `TASK_LOCK` khi dùng single-instance**, vì đó là cơ chế khóa runtime; điều này **không đồng nghĩa** nên cấp `DELETE` cho toàn bộ lịch sử `TASK_EXECUTION`.

## 14. Nguy cơ lộ dữ liệu qua TaskExecutionParams và lỗi

`TASK_EXECUTION_PARAMS` ghi tham số mà task nhận được. Nếu khởi chạy:

~~~bash
java -jar daily-close-task.jar \
  --date=2026-11-23 \
  --api-token=THIS_IS_NOT_A_REAL_TOKEN
~~~

Tham số `--api-token=...` có thể xuất hiện trong process arguments, TaskRepository, logs hoặc hệ điều phối. **Không truyền secret theo cách này**, kể cả khi database đã phân quyền tốt.

Thay bằng môi trường/secret manager:

~~~yaml
spring:
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}

partner:
  api:
    token: ${PARTNER_API_TOKEN}
~~~

Cấu hình triển khai phải cung cấp các biến và bảo đảm quyền đọc secret phù hợp. Tránh dump Spring Environment, toàn bộ CLI args hoặc stack trace có chứa credential vào nơi đọc rộng rãi.

Ngoài tham số, `TASK_EXECUTION.ERROR_MESSAGE` có thể chứa thông điệp lỗi và stack trace, bao gồm SQL, hostname hoặc tên file. Vai trò `task_observer` chỉ đọc bảng `TASK_EXECUTION` vẫn cần được kiểm soát theo quy tắc bảo mật và retention.

Khi cần dashboard cho nhiều nhóm:

- Tạo view đã loại bỏ cột `ERROR_MESSAGE` hoặc làm sạch nội dung nhạy cảm.
- Cân nhắc hạn chế xem `TASK_EXECUTION_PARAMS`.
- Phân quyền theo team/tenant ở lớp dịch vụ quan sát nếu nhiều khách hàng chia sẻ metadata.
- Dùng audit log để ghi ai đã đọc/thay đổi quyền hoặc xóa metadata.

## 15. Kiểm tra quyền hiệu lực bằng chính tài khoản runtime

Đừng chỉ đọc câu `GRANT` của migration: cần **test truy cập bằng role runtime thực sự** trong môi trường có schema đúng.

### Kiểm tra quyền catalog bằng SQL

~~~sql
SELECT current_user, current_database(), current_schema();

SELECT
    has_schema_privilege(
        current_user, 'task_meta', 'USAGE') AS can_use_schema,
    has_schema_privilege(
        current_user, 'task_meta', 'CREATE') AS can_create_schema_object;

SELECT
    has_table_privilege(
        current_user, 'task_meta.task_execution', 'SELECT') AS can_select,
    has_table_privilege(
        current_user, 'task_meta.task_execution', 'INSERT') AS can_insert,
    has_table_privilege(
        current_user, 'task_meta.task_execution', 'UPDATE') AS can_update,
    has_table_privilege(
        current_user, 'task_meta.task_execution', 'DELETE') AS can_delete;
~~~

Kỳ vọng ở mô hình metadata runtime: `USAGE=true`, `CREATE=false`; `SELECT/INSERT/UPDATE=true` cho `task_execution`, và `DELETE=false` nếu ứng dụng không cần xóa lịch sử.

Kiểm tra sequence nếu nó thật sự là PostgreSQL native sequence:

~~~sql
SELECT has_sequence_privilege(
    current_user, 'task_meta.task_seq', 'USAGE'
) AS can_nextval;
~~~

Lệnh này **không dùng được nếu `task_seq` là table**; khi đó dùng `has_table_privilege(...)` kiểm tra `SELECT`/`UPDATE`. Tên table/sequence cũng cần đổi nếu DDL thực tế có prefix khác.

### Smoke test dương và âm

1. **Dương:** chạy task thử với `task_runtime`, xác nhận có TaskExecution bắt đầu và kết thúc, được cấp ID và lưu tham số cần thiết.
2. **Dương:** nếu dùng TaskBatch integration hoặc single-instance, kích hoạt đúng đường code liên quan để kiểm tra quyền bảng phụ trợ.
3. **Âm:** xác nhận `task_runtime` **không có quyền CREATE** trong schema, không sở hữu bảng và không thuộc nhóm migration/DB admin.
4. **Âm:** tài khoản observer không được cập nhật `TASK_EXECUTION` hoặc xem các bảng nhạy cảm ngoài nhu cầu.
5. **Dương:** migration job có quyền thay đổi schema, và sau migration các quyền runtime vẫn hoạt động.
6. **Tính nhất quán:** chạy cả đường **thành công** và **exception**, vì quyền `UPDATE` lúc ghi trạng thái cuối có thể chưa được kiểm thử khi chỉ startup.

**Không thực hiện thử DDL gây thay đổi trên production**. Dùng catalog checks hoặc môi trường staging cô lập. Với thử quyền âm, có thể kiểm tra membership/privilege qua catalog thay vì cố chạy `DROP TABLE` để “xem có bị từ chối không”.

## 16. Mẫu pipeline xác minh an toàn trước khi cho scheduler chạy

~~~mermaid
flowchart TD
    A["Chuẩn bị version + schema migration"] --> B["Chạy migration bằng task_migrator"]
    B --> C{"Migration thành công?"}
    C -- "Không" --> X["Dừng phát hành, xử lý lỗi"]
    C -- "Có" --> D["Kiểm tra object, owner và grants"]
    D --> E{"Runtime có đủ DML + quyền cấp ID?"}
    E -- "Không" --> X
    E -- "Có" --> F["Smoke test task bằng task_runtime"]
    F --> G{"Task lifecycle có ghi đúng?"}
    G -- "Không" --> X
    G -- "Có" --> H["Test thiếu quyền DDL và quyền observer"]
    H --> I{"Least-privilege đạt?"}
    I -- "Không" --> X
    I -- "Có" --> J["Cho phép Scheduler/Job chạy production"]
~~~

Một release nên lưu dấu vết:

- Hash/version của file migration và schema version.
- Danh sách object, owner và DML/sequence privileges đã xác minh.
- Artifact version của Spring Cloud Task (và Spring Batch nếu có).
- Kết quả smoke test `TaskExecutionId` của lần chạy thử.
- Thông tin thay đổi credential/role/secret nếu có.
- Kế hoạch rollback ứng dụng, khôi phục backup và xử lý migration không đảo ngược.

Nếu có thay đổi DDL không tương thích giữa hai phiên bản task đang chạy song song, phải có chiến lược **expand/migrate/contract** hoặc chặn scheduler ở thời gian nâng cấp. “Migration chạy thành công” chưa chứng minh mọi worker phiên bản cũ có thể tiếp tục hoạt động.

## 17. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `permission denied for schema task_meta` | Chưa cấp `USAGE` cho runtime | `GRANT USAGE ON SCHEMA` và kiểm tra role/search_path |
| `permission denied for table task_execution` | Thiếu `INSERT`/`UPDATE`/`SELECT` đúng object | Xác minh DML và DataSource của TaskRepository |
| `permission denied for sequence task_seq` | `TASK_SEQ` là native sequence nhưng role thiếu `USAGE` | Kiểm tra `relkind` và grant đúng sequence |
| `permission denied for table task_seq` | `TASK_SEQ` là table giả lập sequence | Grant `SELECT/UPDATE` theo SQL incrementer |
| `relation task_execution does not exist` | Sai schema, prefix, search_path hoặc DDL chưa chạy | Catalog check, JDBC currentSchema, migration logs |
| Runtime cố chạy `CREATE TABLE` | Task schema initialization còn bật | Tắt `spring.cloud.task.initialize-enabled` khi DDL quản lý ngoài |
| Flyway báo không có quyền CREATE/ALTER | Migration đang chạy bằng `task_runtime` | Chạy migration job bằng `task_migrator` |
| Task bắt đầu được nhưng không chốt trạng thái | Có `INSERT` nhưng thiếu `UPDATE` hoặc DB mất kết nối lúc exit | Smoke test cả kết thúc thành công/thất bại |
| Chỉ Batch Job bị lỗi quyền | `BATCH_*` khác `TASK_*`, hoặc sequence Batch thiếu quyền | Tách kiểm tra JobRepository/Step |
| Single-instance lỗi ghi khóa | Thiếu quyền trên `TASK_LOCK` | Kiểm tra quyền và schema lock theo release |
| Quyền biến mất sau migration mới | Đối tượng mới chưa được GRANT hoặc tạo bằng owner khác | GRANT per migration hoặc kiểm tra default privileges |
| Runtime có thể xóa bảng dù không thấy GRANT | Runtime là owner hoặc member role có quyền cao | Kiểm tra ownership/membership, không chỉ ACL |
| Log hoặc TaskExplorer lộ token | Truyền secret qua CLI và truy cập `TASK_EXECUTION_PARAMS` rộng | Chuyển sang secret manager và giới hạn SELECT |
| Task chạy staging được nhưng production lỗi | Khác DDL, schema, search_path, role hoặc datasource | So migration version và current_user/current_schema |
| `GRANT ALL TABLES` hoạt động nhưng quá rộng | Schema trộn bảng metadata và business | Tách schema và quyền per object |

### Trình tự điều tra

1. Xác định **tài khoản thực sự** kết nối bằng `current_user` và DataSource nào được framework dùng.
2. Kiểm tra thông báo lỗi: `schema`, `table` hay `sequence`, tránh giải quyết nhầm loại object.
3. Xác minh object với `pg_class`, owner, schema và prefix.
4. Kiểm tra `USAGE` trên schema **và** DML trên object.
5. Kiểm tra initializer/migration có đang cố tạo DDL khi runtime đã bị tước quyền.
6. Chạy smoke test bằng role runtime để xác nhận startup và ghi trạng thái cuối.
7. Không “sửa nhanh” bằng `GRANT ALL ON DATABASE` hoặc chuyển runtime thành owner/superuser.

## 18. Quyền trong môi trường nhiều tenant, nhiều cluster và nhiều task đồng thời

Tách quyền database còn phải xét phạm vi truy cập dữ liệu:

- **Nhiều tenant cùng database:** chỉ riêng `tenant_id` trong câu SQL chưa tạo bảo mật. Có thể cần PostgreSQL Row-Level Security, schema riêng, tài khoản riêng hoặc policy ở service layer; kiểm tra người dùng runtime không tự bypass policy.
- **Nhiều cluster cùng ghi TaskRepository:** các scheduler có thể tạo nhiều TaskExecution vào cùng kho; cần bảo vệ ID allocator, transaction và lock table đúng DDL.
- **Task readonly và task write-heavy:** không nên dùng chung một credential rộng cho mọi task nếu có thể chia role theo nhóm workload.
- **Task có dữ liệu nhạy cảm:** TaskRepository nên đặt ở schema riêng, backup và log có retention, encryption at rest và TLS in transit theo chính sách tổ chức.
- **Remote partitioning/Spring Batch:** manager và workers phải truy cập được cùng JobRepository (nếu thiết kế như vậy), nhưng không nhất thiết có cùng quyền trên toàn business DB.
- **Job chạy nhiều lần:** account runtime có thể bị cache trong nhiều Pod; khi rotate credential, cần kế hoạch cho task đang chạy, pool connection và Job mới.

**Phân quyền DB không thay thế idempotency.** Một worker có quyền `INSERT` hợp lệ vẫn có thể ghi trùng dữ liệu nếu ứng dụng không dùng business key/unique constraint và xử lý retry/concurrency đúng.

## 19. Bài thực hành kiểm tra quyền runtime và migration

### Mục tiêu

Triển khai một `daily-close-task` không có web server, dùng PostgreSQL lưu TaskExecution. Tài khoản runtime chỉ làm DML còn migrator quản lý schema; cho phép kiểm tra lỗi thiếu quyền mà không cần cấp quyền rộng.

### Các bước

1. **Chọn phiên bản:** khóa Spring Boot và Spring Cloud Task tương thích; lấy DDL TaskRepository cho PostgreSQL đúng release.
2. **Chuẩn bị hai role:** `task_migrator` và `task_runtime`. Cấp credential qua secret manager; không commit password vào repository.
3. **Tạo schema riêng:** `task_meta` thuộc migrator; chỉ cấp `USAGE` cho runtime.
4. **Chạy migration:** tạo bảng/sequence/index đúng DDL và prefix; xác nhận object owner không phải runtime.
5. **Đặt GRANT có mục tiêu:** `SELECT/INSERT/UPDATE` cho `TASK_EXECUTION`, quyền bảng params, lock/batch integration khi thực sự có, và quyền cấp ID đúng loại `TASK_SEQ`.
6. **Tắt initializer startup:** `spring.cloud.task.initialize-enabled=false`, đồng thời tắt các initializer khác nếu schema được quản lý ngoài.
7. **Cấu hình DataSource runtime:** dùng `task_runtime`, search_path/schema rõ ràng và pool nhỏ.
8. **Chạy task thành công:** kiểm tra TaskExecution mới và `END_TIME`, exit code, tham số được lưu đúng.
9. **Chạy task thất bại có chủ đích:** runner ném exception, kiểm tra TaskRepository vẫn có thể ghi metadata lỗi nếu lifecycle hoạt động.
10. **Thử một bản cấu hình thiếu quyền trên staging:** ví dụ thiếu `UPDATE`; quan sát lỗi lúc chốt TaskExecution, rồi khôi phục GRANT đúng đối tượng.
11. **Kiểm tra observer:** đọc view/bảng đã được cấp, không có quyền ghi/xóa lịch sử.
12. **Chạy migration phiên bản mới:** xác minh default/per-object GRANT cho object mới và smoke test sau upgrade.
13. **Nếu dùng Spring Batch:** thêm `batch_meta` và kiểm tra trình tự launch/restart Job bằng quyền Batch phù hợp.
14. **Đối chiếu an toàn dữ liệu:** kiểm tra TaskExecutionParams, logs và secret không chứa password/token.

| Kiểm tra | Kỳ vọng |
|---|---|
| `task_runtime` có `USAGE` schema | Có |
| `task_runtime` có `CREATE` schema | **Không** |
| `task_runtime` là owner bảng TaskRepository | **Không** |
| `TASK_EXECUTION` có DML cần cho lifecycle | Có |
| `TASK_SEQ` được cấp quyền theo loại object thực | Có |
| Startup không tự tạo DDL | Có |
| TaskExecution ghi được đầu/cuối một lần chạy | Có |
| `task_observer` chỉ đọc dữ liệu phù hợp | Có |
| Migration sử dụng role riêng | Có |
| Mật khẩu không có trong args/log/metadata | Có |

## 20. Checklist production và kết luận

- Dùng **role runtime ít quyền nhất**, không dùng superuser hoặc owner schema để chạy task.
- **Tách migration role** và pipeline DDL khỏi JVM task ngắn hạn.
- **Xác minh DDL theo version** Spring Cloud Task trước khi cấp quyền.
- Có `USAGE ON SCHEMA`, đúng DML trên bảng, đúng quyền sequence/table giả lập ID.
- Không cấp `CREATE` trên schema metadata, `DROP`/`ALTER` object hoặc `GRANT OPTION` cho runtime.
- Tắt auto initialization khi schema do migration ngoài quản lý.
- Kiểm tra `tablePrefix`, DataSource và `search_path` khớp schema thực tế.
- Với Spring Batch, cấp quyền riêng cho JobRepository, không nhầm `TASK_*` với `BATCH_*`.
- Dùng `ALTER DEFAULT PRIVILEGES` hoặc per-migration GRANT có kiểm soát; nhớ phân biệt object hiện có và object mới.
- Tách tài khoản maintenance/cleanup khỏi task runtime khi có thể.
- Giới hạn truy cập `TASK_EXECUTION_PARAMS` và `ERROR_MESSAGE`; không truyền credential qua CLI.
- Bảo vệ database bằng TLS, secret rotation, RBAC, backup, retention và audit theo môi trường.
- Chạy **smoke test bằng đúng runtime role**, gồm thành công, thất bại, sequence và các tính năng tùy chọn.
- Kiểm tra multi-tenant authorization và idempotency nghiệp vụ ngoài quyền SQL.
- Đảm bảo rollback/upgrade không làm mất quyền hoặc phá khả năng restart của Batch Job.

**Kết luận:** Đối với Spring Cloud Task, phân quyền database đúng không chỉ là cho phép ứng dụng kết nối. Cần tách **tài khoản chạy TaskRepository** khỏi **tài khoản quản lý schema**, cấp DML và quyền cấp ID theo DDL thực tế, đồng thời giới hạn người đọc metadata có thể chứa tham số/lỗi nhạy cảm. Với schema versioned, migration chạy riêng và kiểm thử runtime role sau mỗi lần nâng cấp, task hữu hạn sẽ dễ vận hành an toàn hơn, kể cả khi chạy theo lịch, được retry hoặc phối hợp Spring Batch.

### Tài liệu tham khảo

- [Spring Cloud Task — Features: DataSource, tablePrefix và schema initialization](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — TaskRepository Schema Appendix](https://docs.spring.io/spring-cloud-task/docs/current/reference/html/appendix-task-repository-schema.html)
- [Spring Batch — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html)
- [PostgreSQL — Privileges](https://www.postgresql.org/docs/current/ddl-priv.html)
- [PostgreSQL — GRANT](https://www.postgresql.org/docs/current/sql-grant.html)
- [PostgreSQL — ALTER DEFAULT PRIVILEGES](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html)
