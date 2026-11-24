# Tùy chỉnh tablePrefix và tên schema trong Spring Cloud Task

## 1. Vì sao cần tùy chỉnh kho metadata?

Mỗi lần một ứng dụng **Spring Cloud Task** khởi chạy, framework có thể lưu một bản ghi **TaskExecution** vào **TaskRepository** để theo dõi tên tác vụ, thời điểm bắt đầu, kết thúc, mã thoát và các thông tin thực thi. Với ứng dụng hữu hạn như nhập dữ liệu, xuất báo cáo hoặc chạy theo lịch, kho metadata này giúp truy vết lần chạy, phát hiện tác vụ thất bại và đối chiếu kết quả nghiệp vụ.

Trong một hệ thống thực tế, nhiều ứng dụng hoặc môi trường có thể sử dụng chung máy chủ CSDL. Nếu mọi ứng dụng cùng truy cập các bảng metadata mặc định mà không có chiến lược tổ chức, sẽ phát sinh vấn đề:

- Đụng tên bảng giữa các ứng dụng hoặc thành phần dùng chung một database.
- Không rõ bảng nào do môi trường phát triển, kiểm thử hay sản xuất quản lý.
- Khó áp dụng quyền truy cập, migration và backup riêng cho metadata.
- Khi đổi cấu hình tên bảng, ứng dụng không tìm thấy lịch sử TaskExecution trước đó.
- Spring Cloud Task và Spring Batch dùng các bộ bảng metadata khác nhau nhưng cùng xuất hiện trong một kho dữ liệu, gây nhầm lẫn khi cấu hình.

Hai cơ chế tổ chức thường được sử dụng là **`tablePrefix`** (tiền tố tên đối tượng metadata của Spring Cloud Task) và **schema** (namespace của cơ sở dữ liệu). Chúng phục vụ mục đích khác nhau và phải được đồng bộ với **DDL thực tế** mà CSDL đã tạo.

## 2. Phân biệt tablePrefix, schema, database và DataSource

| Khái niệm | Là gì? | Ví dụ PostgreSQL | Vai trò |
|---|---|---|---|
| Database | CSDL logic nằm trên máy chủ | `appdb` | Phạm vi kết nối cơ bản |
| Schema | Namespace chứa bảng, sequence, index… bên trong một database | `task_meta` | Phân nhóm đối tượng và hỗ trợ phân quyền |
| `tablePrefix` | Chuỗi đặt trước **hậu tố tên bảng metadata** do framework sử dụng | `OPS_TASK_` | Đổi tên các bảng framework truy vấn |
| Table | Đối tượng lưu bản ghi thực tế | `task_meta.ops_task_execution` | Nơi chứa TaskExecution |
| DataSource | Cấu hình kết nối của ứng dụng | JDBC URL + user + pool | Xác định nơi framework kết nối |
| TaskRepository | Thành phần Spring Cloud Task lưu/đọc lịch sử lần chạy | Dùng bảng metadata ở DataSource được chọn | Quan sát vòng đời TaskExecution |

Mô hình minh họa:

~~~mermaid
flowchart TD
    A["Spring Cloud Task Application"] --> B["TaskRepository"]
    B --> C["DataSource: appdb / task_runner"]
    C --> D["Schema: task_meta"]
    D --> E["OPS_TASK_EXECUTION"]
    D --> F["OPS_TASK_EXECUTION_PARAMS"]
    D --> G["Các bảng/sequence metadata khác"]
    A --> H["Business Service"]
    H --> I["Bảng và dữ liệu nghiệp vụ"]
~~~

Sơ đồ biểu diễn **một cách tổ chức có thể triển khai**, không có nghĩa Spring Cloud Task tự tạo tất cả đối tượng khi chỉ đặt hai thuộc tính cấu hình.

Ví dụ với tiền tố mặc định thường dùng **`TASK_`**, tên bảng thực thi là **`TASK_EXECUTION`**. Nếu thay bằng **`OPS_TASK_`**, tên tương ứng trở thành **`OPS_TASK_EXECUTION`**. Nếu đặt chúng dưới schema **`task_meta`**, tên được phân giải thành **`task_meta.ops_task_execution`** trong PostgreSQL khi sử dụng identifier không đặt trong dấu nháy kép.

Có ba điểm cần nhớ:

1. **Tiền tố không phải schema.** Thay `tablePrefix` không tự tạo schema mới.
2. **Schema không phải tiền tố.** Chuyển default schema của kết nối không đổi hậu tố hoặc tiền tố của tên bảng.
3. **Cấu hình và DDL phải khớp nhau.** Nếu repository tìm `OPS_TASK_EXECUTION` nhưng database chỉ có `TASK_EXECUTION`, truy vấn sẽ thất bại ngay cả khi cả hai nằm trong cùng schema.

## 3. Những đối tượng nào bị ảnh hưởng bởi tablePrefix?

Spring Cloud Task dùng một nhóm bảng và, tùy hệ quản trị/phiên bản, các đối tượng hỗ trợ sinh khóa như sequence hoặc bảng sinh ID. Tên và cấu trúc chính xác phải lấy từ **script DDL của phiên bản Spring Cloud Task đang triển khai**, phù hợp với database đích.

Các bảng quen thuộc bao gồm:

| Ý nghĩa | Tên thường gặp với prefix `TASK_` | Tên minh họa với prefix `OPS_TASK_` |
|---|---|---|
| Lần chạy ứng dụng | `TASK_EXECUTION` | `OPS_TASK_EXECUTION` |
| Tham số gắn với lần chạy | `TASK_EXECUTION_PARAMS` | `OPS_TASK_EXECUTION_PARAMS` |
| Liên kết task và batch job | `TASK_TASK_BATCH` | `OPS_TASK_TASK_BATCH` |

**Quy tắc:** Framework ghép tiền tố được cấu hình với phần tên đối tượng mà nó định nghĩa. Do đó, khi muốn bảng kết quả có tên `OPS_TASK_EXECUTION`, ta chọn tiền tố `OPS_TASK_`, không phải chỉ `OPS_`. Việc tên bảng cụ thể, bảng bổ sung và sequence có tồn tại hay không vẫn phụ thuộc schema/phiên bản.

Một số hệ thống dùng identifier có phân biệt chữ hoa/chữ thường khi đặt trong dấu nháy kép. Với PostgreSQL, tên **không quote** viết `OPS_TASK_EXECUTION` sẽ được lưu/phân giải thành `ops_task_execution`; bảng được tạo dưới tên có quote `"OPS_TASK_EXECUTION"` lại là một identifier khác. Hãy để DDL và các câu SQL của framework dùng cách đặt tên nhất quán.

> **Giới hạn:** `tablePrefix` là cấu hình địa chỉ bảng, không phải tính năng tự động rename, move hoặc migrate dữ liệu. Một TaskRepository đổi tiền tố sẽ đọc một nhóm bảng khác. Lịch sử cũ không được tự chuyển sang nhóm bảng mới.

## 4. Cấu hình table-prefix trong ứng dụng Spring Cloud Task

Với phiên bản Spring Cloud Task hỗ trợ cấu hình qua Spring Boot properties, có thể đặt tiền tố bảng trong `application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none

  application:
    name: nightly-revenue-task

  cloud:
    task:
      name: nightly-revenue-task
      table-prefix: OPS_TASK_
~~~

`spring.cloud.task.table-prefix` thể hiện tiền tố tên bảng mà hạ tầng Spring Cloud Task sử dụng để truy cập metadata. Spring Boot hỗ trợ relaxed binding, vì vậy trong những phiên bản tương ứng, dạng property Java như `tablePrefix` có thể được biểu diễn ở YAML theo lối `table-prefix`. Hãy kiểm tra cấu hình mà **phiên bản đã khóa dependency** thực sự chấp nhận; tránh giả định mọi nhánh Spring Cloud Task có API cấu hình giống nhau.

Một ví dụ `application.properties` tương đương:

~~~properties
spring.main.web-application-type=none
spring.application.name=nightly-revenue-task
spring.cloud.task.name=nightly-revenue-task
spring.cloud.task.table-prefix=OPS_TASK_
~~~

**Không nên đặt prefix tùy tiện theo từng lần chạy** nếu chưa đồng thời chuẩn bị bảng và quyền truy cập. Nếu một CronJob khởi chạy lần A với `OPS_TASK_` nhưng lần B với `TASK_`, hai lần chạy có thể xuất hiện ở **hai kho metadata khác nhau** dù cùng tên task. Điều này khiến dashboard, truy vấn giám sát và quy trình xử lý lỗi đưa ra kết luận thiếu dữ liệu.

Trong môi trường phức tạp, Spring Cloud Task cũng cho phép tùy biến hạ tầng repository/configurer ở mức bean theo API của từng phiên bản. Chỉ nên dùng cách đó khi cấu hình properties không đáp ứng được và phải kiểm tra cách chọn DataSource, transaction manager, repository và khả năng tương thích thư viện. Với trường hợp đổi tiền tố thông thường, ưu tiên cấu hình properties nhất quán.

## 5. Đặt metadata vào một schema riêng: ví dụ PostgreSQL

Giả sử ứng dụng dùng database `appdb` và muốn đặt metadata Spring Cloud Task vào schema `task_meta`, bên cạnh các bảng nghiệp vụ ở `business`.

~~~text
PostgreSQL server
└── appdb
    ├── business
    │   ├── orders
    │   └── payments
    └── task_meta
        ├── ops_task_execution
        ├── ops_task_execution_params
        └── ... (các đối tượng metadata theo phiên bản)
~~~

Với PostgreSQL, một phương án là cấu hình **default schema/search path** cho kết nối JDBC của DataSource dùng bởi TaskRepository:

~~~yaml
spring:
  main:
    web-application-type: none

  datasource:
    url: jdbc:postgresql://db.internal:5432/appdb?currentSchema=task_meta
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}

  cloud:
    task:
      name: nightly-revenue-task
      table-prefix: OPS_TASK_
~~~

Đường dẫn `db.internal:5432/appdb` chỉ là ví dụ. `currentSchema=task_meta` là tham số của **PostgreSQL JDBC Driver**; nó tác động cách resolve tên đối tượng **không có schema qualifier** trên các connection dùng URL đó. Nó **không tạo schema `task_meta`** và **không đổi tên bảng**.

Nếu cùng DataSource được dùng cho nghiệp vụ và Spring Batch, việc thay default schema có thể tác động các truy vấn không ghi rõ schema của **mọi thành phần dùng connection đó**. Vì vậy, khi hệ thống cần phân vùng dữ liệu và quyền truy cập chặt chẽ, hãy thiết kế rõ ràng DataSource nào phục vụ metadata task, DataSource nào phục vụ nghiệp vụ/Batch; đừng đổi search path toàn cục mà chưa kiểm tra các repository khác.

Với HikariCP và driver hỗ trợ `Connection.setSchema(...)`, một số triển khai còn có thể cấu hình default schema của pool. Tuy nhiên cách hoạt động phụ thuộc JDBC driver, pool, cấu hình và phiên bản. Ví dụ `currentSchema` ở trên là cách **dành riêng cho PostgreSQL**; không sao chép nguyên xi sang MySQL, Oracle hoặc SQL Server.

### Tạo schema và cấp quyền bằng migration

Một migration riêng có thể chuẩn bị namespace và quyền trước khi khởi chạy task:

~~~sql
-- Ví dụ cho PostgreSQL; thực thi bằng tài khoản quản trị/migration.
CREATE SCHEMA IF NOT EXISTS task_meta;

-- task_runner là role runtime đã được tạo trước.
GRANT USAGE ON SCHEMA task_meta TO task_runner;

-- Sau khi migration tạo đủ bảng/sequence metadata:
GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA task_meta TO task_runner;

GRANT USAGE, SELECT
ON ALL SEQUENCES IN SCHEMA task_meta TO task_runner;
~~~

Đoạn trên **chưa tạo các bảng TaskRepository**. Phải tiếp tục dùng DDL phù hợp phiên bản Spring Cloud Task và điều chỉnh tiền tố thành `OPS_TASK_`, đồng thời bảo đảm đối tượng được tạo bên trong `task_meta`.

Cấp quyền `ON ALL ... IN SCHEMA` chỉ áp dụng cho các đối tượng đã tồn tại lúc chạy lệnh. Với migration sau này, cần cấp quyền cho đối tượng mới hoặc thiết lập `ALTER DEFAULT PRIVILEGES` phù hợp với **role sở hữu đối tượng do migration tạo**. Không nên yêu cầu tài khoản runtime có quyền `CREATE/DROP` schema trong production nếu việc triển khai schema được thực hiện qua pipeline migration.

## 6. Đồng bộ cấu hình runtime với DDL thực tế

Thay `spring.cloud.task.table-prefix` chỉ thay **địa chỉ bảng mà repository sẽ sử dụng**. Việc tạo schema, bảng, khóa, index và bộ sinh ID là một công việc triển khai CSDL riêng.

Quy trình hợp lý:

~~~mermaid
flowchart TD
    A["Khóa phiên bản Spring Cloud Task + database dialect"] --> B["Lấy DDL chuẩn đi kèm đúng phiên bản"]
    B --> C["Chọn schema và tablePrefix"]
    C --> D["Biến đổi DDL có kiểm soát"]
    D --> E["Áp dụng Flyway / Liquibase / DBA migration"]
    E --> F["Cấp quyền cho runtime user"]
    F --> G["Cấu hình DataSource và table-prefix"]
    G --> H["Khởi chạy task thử nghiệm"]
    H --> I{"TaskExecution được ghi đúng bảng?"}
    I -- "Có" --> J["Kiểm tra kết thúc, tham số, truy vấn giám sát"]
    I -- "Không" --> K["Đối chiếu schema, tên bảng, sequence, quyền"]
    K --> D
~~~

**Bước 1 — Xác định DDL gốc.** Lấy script schema đi kèm release đang sử dụng, đúng hệ CSDL và cách sinh khóa. Không tự tạo một bảng chỉ có cột `TASK_EXECUTION_ID` rồi xem như hoàn thành; repository cần những cột, constraint và đối tượng khác để hoạt động.

**Bước 2 — Chọn chiến lược tên.** Ví dụ `schema=task_meta` và `tablePrefix=OPS_TASK_`. Ghi nhận rõ giá trị này trong cấu hình triển khai, migration và tài liệu vận hành.

**Bước 3 — Áp dụng DDL có kiểm soát.** Nếu script gốc chứa tên tiền tố mặc định, việc biến đổi cần áp dụng nhất quán lên tên bảng, khóa/sequence và các quan hệ phụ thuộc. Kiểm tra việc replace không đổi nhầm tên cột hoặc các đối tượng không liên quan. Nên review SQL sau biến đổi trước khi chạy.

**Bước 4 — Tạo repository bằng đúng kết nối.** Khởi chạy một task nhỏ qua DataSource runtime đã được cấu hình. Xác minh repository ghi vào schema và bảng mong muốn; xác minh cả lúc thành công và khi runner ném exception.

**Bước 5 — Đưa việc tạo schema vào CI/CD hoặc migration.** Tránh để nhiều Pod cùng tranh nhau tạo bảng ở thời điểm chạy đầu tiên. Cơ chế auto-initialize, nếu có ở phiên bản đang dùng, cần được xem xét kỹ cùng với việc đã tùy chỉnh prefix/schema. Đừng giả định công cụ auto-init luôn biến đổi script DDL theo prefix mới.

### Một ví dụ kiểm tra schema PostgreSQL

~~~sql
-- Chạy trên đúng database bằng connection tương đương runtime.
SELECT current_database();
SELECT current_schema();
SHOW search_path;

-- Tìm các bảng metadata được triển khai trong schema đã chọn.
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'task_meta'
  AND table_name LIKE 'ops_task_%'
ORDER BY table_name;

-- Ví dụ truy vấn lịch sử (nếu schema phiên bản này có tên bảng như dưới).
SELECT task_execution_id, task_name, start_time, end_time, exit_code
FROM task_meta.ops_task_execution
ORDER BY task_execution_id DESC
LIMIT 10;
~~~

Nếu kết quả ở `information_schema` không có bảng mong đợi, cần xác minh migration đã chạy, chúng được tạo ở đúng schema, tài khoản có quyền nhìn thấy metadata và tên bảng có khác vì quy tắc chữ hoa/chữ thường hay không.

## 7. Các chiến lược tổ chức: đổi prefix, đổi schema hay cả hai?

| Phương án | Ví dụ | Ưu điểm | Giới hạn |
|---|---|---|---|
| Giữ prefix mặc định, tách schema | `task_a.task_execution`, `task_b.task_execution` | Dễ áp quyền/backup theo namespace, cùng DDL bảng chuẩn | Cần cấu hình schema/DataSource chính xác cho mỗi ứng dụng |
| Chung schema, đổi prefix | `public.ops_task_execution` và `public.billing_task_execution` | Phân biệt nhóm bảng cùng namespace | Không tự cách ly quyền và tài nguyên |
| Tách cả schema và prefix | `task_meta.ops_task_execution` | Rõ trách nhiệm và dễ nhận diện khi quan sát | Thêm cấu hình và migration cần đồng bộ |
| Tách database hoặc DataSource | Metadata đặt trong database `taskmeta` khác database nghiệp vụ | Cách ly ở cấp kết nối/quyền và vận hành | Phức tạp hơn trong cấu hình, giám sát và sao lưu |

Không có phương án duy nhất phù hợp mọi hệ thống:

- **Một ứng dụng đơn lẻ:** giữ nguyên tên mặc định thường đơn giản nhất.
- **Nhiều ứng dụng cùng database:** cân nhắc tách schema theo team/môi trường trước khi đặt prefix riêng nếu hệ CSDL hỗ trợ.
- **Một ứng dụng cùng chạy nhiều loại task:** có thể dùng chung bộ bảng TaskRepository và phân biệt bằng `TASK_NAME`, `TASK_EXECUTION_ID`. Không cần đặt một tiền tố riêng cho từng task nghiệp vụ nếu mục tiêu chỉ là phân biệt lịch sử.
- **Yêu cầu phân quyền mạnh:** prefix chỉ là quy ước tên. Quyền CSDL thực sự dựa trên role, schema, database và đặc quyền đối tượng.

**Quan trọng:** thay đổi schema hoặc tiền tố không cấp cơ chế “mỗi ngày chỉ chạy một lần”. Nếu có hai CronJob kích hoạt cùng ngày, mỗi lần vẫn có thể tạo TaskExecution riêng. Cần idempotency/locking hoặc chính sách điều phối theo khóa nghiệp vụ.

## 8. Khi cùng ứng dụng dùng Spring Batch

Spring Cloud Task và Spring Batch thường đi cùng nhau: một ứng dụng task chạy hữu hạn có thể khởi chạy một job batch, ghi dữ liệu và kết thúc.

Hai framework có repository riêng:

| Phạm vi | Spring Cloud Task | Spring Batch |
|---|---|---|
| Repository | `TaskRepository` | `JobRepository` |
| Lịch sử | `TaskExecution`: vòng đời **ứng dụng task** | `JobExecution` / `StepExecution`: job, step, checkpoint |
| Bộ bảng quen thuộc | `TASK_*` | `BATCH_*` |
| Prefix | Cấu hình của **Spring Cloud Task** | Cấu hình **Spring Batch** riêng |
| Đổi schema | Phải chọn namespace và kết nối tương ứng | Phải chọn namespace và kết nối cho Batch tương ứng |

Thay `spring.cloud.task.table-prefix=OPS_TASK_` **không đồng thời đổi các bảng `BATCH_*`**. Nếu có cấu hình table prefix của Spring Batch, nó phải được thiết lập riêng theo phiên bản Spring Boot/Spring Batch, ví dụ qua hạ tầng `JobRepository` hoặc thuộc tính cấu hình tương ứng của phiên bản.

Ví dụ bố trí:

~~~text
appdb
├── task_meta
│   ├── ops_task_execution
│   ├── ops_task_execution_params
│   └── ...
├── batch_meta
│   ├── batch_job_instance
│   ├── batch_job_execution
│   └── ...
└── business
    ├── imported_orders
    └── report_exports
~~~

Trong cách bố trí này, TaskRepository và JobRepository có thể cần **hai bộ cấu hình repository/DataSource riêng**, dù cùng sử dụng một PostgreSQL database. Cấu hình search path của một datasource không tự biến hai repository thành hai datasource khác nhau. Tùy phiên bản, việc chọn DataSource cho Task/Batch và tạo custom configurer cần được kiểm tra trực tiếp ở cấu hình bean.

Nếu dùng chung schema thay vì tách riêng, hãy giữ namespace bảng Task và Batch rõ ràng để tránh nhầm lẫn giữa dữ liệu lần chạy ứng dụng và dữ liệu job/step. Khi gỡ bỏ hoặc di chuyển một framework, tuyệt đối không xóa nhầm các bảng đang phục vụ framework còn lại.

## 9. Từ đổi cấu hình sang chuyển dữ liệu: một bài toán migration

Giả sử hệ thống đang có lịch sử trong `public.task_execution` và muốn chuyển sang `task_meta.ops_task_execution`. Nếu chỉ sửa YAML mà không di chuyển dữ liệu:

- Ứng dụng mới tìm bảng `task_meta.ops_task_execution`, có thể không tồn tại và lỗi khi chạy.
- Nếu bảng mới được tạo trống, các bản ghi cũ **không tự xuất hiện** trong repository mới.
- Dashboard và truy vấn cũ có thể tiếp tục đọc bảng cũ, gây lệch số liệu.
- Bộ sinh khóa có thể gặp xung đột nếu copy dữ liệu nhưng không đồng bộ sequence/identity.
- Ứng dụng cũ và mới chạy song song có thể ghi vào hai nơi khác nhau.

Một kế hoạch migration cần làm rõ:

1. **Mục tiêu:** chỉ tách metadata cho **các lần chạy mới**, hay di chuyển **cả lịch sử**?
2. **Chọn thời gian chuyển đổi:** dừng hoặc điều phối để không còn tiến trình task ghi vào schema cũ khi cutover. Xác minh task đang chạy và các lần chạy chưa có `END_TIME`.
3. **DDL đích:** tạo đúng bảng/sequence/index/constraint cho phiên bản đích trước khi chuyển dữ liệu.
4. **Dữ liệu và quan hệ:** nếu cần giữ lịch sử, copy bảng/sequence/khóa ngoại liên quan, bảo đảm ID và mapping không thay đổi sai. Không chỉ copy bảng `TASK_EXECUTION` mà bỏ quên bảng tham số hoặc liên kết Batch.
5. **Bộ sinh ID:** nếu đã copy ID, kiểm tra giá trị next sequence/identity lớn hơn ID tối đa để lần ghi mới không trùng.
6. **Quyền truy cập:** áp dụng quyền cho role runtime, migration, giám sát và backup.
7. **Cập nhật ứng dụng và công cụ quan sát cùng lúc:** YAML/properties, DataSource, dashboards, SQL, alert và quy trình hỗ trợ.
8. **Kiểm tra rollback:** ghi nhận snapshot/backup, cách quay lại bản triển khai cũ và nguyên tắc xử lý các lần chạy phát sinh sau cutover.

Nếu không cần giữ lịch sử trong cùng repository, vẫn nên **lưu trữ hoặc backup** bộ bảng cũ theo chính sách retention, thay vì xóa ngay. Đổi prefix/schema nên được coi là một **thay đổi cấu trúc dữ liệu sản xuất**, không phải sửa tên hiển thị.

~~~mermaid
sequenceDiagram
    participant O as Operator / Migration
    participant DB as Database
    participant A as Spring Cloud Task
    participant M as Monitoring
    O->>A: Tạm dừng lịch khởi chạy mới
    O->>DB: Tạo schema + DDL đích, chuẩn bị quyền
    O->>DB: Di chuyển dữ liệu nếu cần, đồng bộ bộ sinh ID
    O->>A: Triển khai cấu hình schema/prefix mới
    A->>DB: Ghi TaskExecution thử nghiệm
    O->>DB: Kiểm tra bảng đích và trạng thái
    O->>M: Cập nhật truy vấn / dashboard
    O->>A: Mở lại lịch khởi chạy
~~~

Trong vận hành theo Kubernetes Job hoặc scheduler, cũng phải bảo đảm các **job cũ chưa hoàn tất** được xử lý theo kế hoạch trước khi đổi repository đích. Schema mới không có khả năng tự phát hiện hay hoàn tất TaskExecution còn treo tại schema cũ.

## 10. Ví dụ hoàn chỉnh: metadata riêng cho một task xuất báo cáo

### 10.1. Mục tiêu

Một ứng dụng `nightly-revenue-task` chạy theo lịch hoặc theo yêu cầu với:

- PostgreSQL database `appdb`.
- Schema metadata: `task_meta`.
- Table prefix: `OPS_TASK_`.
- Metadata bền vững phục vụ tra cứu lịch sử các lần chạy.
- Bảng nghiệp vụ có thể nằm ở schema khác, được quản lý bởi service nghiệp vụ.

### 10.2. Cấu hình Spring Boot

~~~yaml
spring:
  main:
    web-application-type: none

  application:
    name: nightly-revenue-task

  datasource:
    url: jdbc:postgresql://db.internal:5432/appdb?currentSchema=task_meta
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}

  cloud:
    task:
      name: nightly-revenue-task
      table-prefix: OPS_TASK_
~~~

Giá trị `${...}` đại diện cho biến môi trường được cấp an toàn khi triển khai. Phải thêm dependency driver PostgreSQL, Spring Cloud Task cùng phiên bản Spring Boot/Spring Cloud phù hợp, datasource, và **migration đã tạo schema/bảng trước khi task chạy**.

### 10.3. Runner và nghiệp vụ

~~~java
import java.time.LocalDate;
import java.util.List;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class RevenueTaskApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
            SpringApplication.run(RevenueTaskApplication.class, args);
        System.exit(SpringApplication.exit(context));
    }

    @Bean
    ApplicationRunner revenueRunner(RevenueService service) {
        return arguments -> {
            List<String> dates = arguments.getOptionValues("date");

            if (dates == null || dates.size() != 1) {
                throw new IllegalArgumentException(
                    "Can truyen --date=yyyy-MM-dd");
            }

            LocalDate date = LocalDate.parse(dates.get(0));
            // Đợi service hoàn thành, hoặc cho exception lan lên.
            service.exportForDate(date);
        };
    }
}
~~~

`RevenueService` là service nghiệp vụ do dự án xây dựng. Một lần chạy:

~~~bash
java -jar nightly-revenue-task.jar --date=2026-11-23
~~~

Sau khi chạy thành công, TaskRepository sẽ có cơ hội lưu lần chạy vào các đối tượng metadata đã cấu hình. **Bảng đầu ra báo cáo** và điều kiện idempotency ngày xuất là trách nhiệm của `RevenueService`; repository không tự lưu kết quả nghiệp vụ.

### 10.4. Xác minh sau khi chạy

Kiểm tra bằng tài khoản có quyền đọc metadata:

~~~sql
SELECT task_execution_id, task_name, start_time, end_time, exit_code
FROM task_meta.ops_task_execution
WHERE task_name = 'nightly-revenue-task'
ORDER BY task_execution_id DESC
LIMIT 5;
~~~

Trong môi trường có nhiều schema và cấu hình khác nhau, truy vấn này kiểm tra **vị trí vật lý cụ thể**, nên giúp xác nhận task không âm thầm ghi vào bộ bảng mặc định khác. Cũng nên kiểm tra bảng tham số và kết quả nghiệp vụ, thử đường lỗi (ví dụ ngày không hợp lệ) và xác minh mã thoát bên điều phối.

## 11. Lỗi thường gặp và cách tìm nguyên nhân

| Biểu hiện | Nguyên nhân có thể | Kiểm tra ưu tiên |
|---|---|---|
| `relation "ops_task_execution" does not exist` | Chưa tạo DDL, sai schema/search_path, sai prefix hoặc identifier được quote khác kiểu | Tra `information_schema`, `current_schema()`, tên bảng thực tế |
| `permission denied for schema task_meta` | Role thiếu `USAGE` hoặc quyền đối tượng | Kiểm tra `GRANT` cho schema/bảng/sequence |
| Lỗi tạo ID, thiếu sequence hoặc duplicate key | Script sinh khóa/sequence sai, dữ liệu copy nhưng chưa đồng bộ generator | Xem DDL đúng dialect, giá trị ID tối đa và bộ sinh ID |
| Task chạy nhưng dashboard “không có lịch sử” | Dashboard đọc prefix/schema cũ hoặc datasource khác | So sánh connection string và SQL quan sát |
| Chỉ chạy lỗi ở production | Schema không được migration, user runtime không có quyền, search path khác staging | So migration version, grants và JDBC URL thực tế |
| TaskRepository và JobRepository bị lẫn bảng | Nhầm namespace metadata Spring Task và Batch | Kiểm tra bảng `TASK_*` vs `BATCH_*` và cấu hình từng repository |
| Task mới có ID bắt đầu từ đầu | Đang truy cập **bộ bảng mới** sau đổi prefix/schema | Đối chiếu migration/historical rows và sequence đích |
| Nhiều môi trường ghi lẫn metadata | Dùng chung schema/prefix và cùng DB hoặc dùng nhầm secret | Kiểm tra profile, DataSource, role, database và schema |

### Quy trình chẩn đoán gọn

1. **Chụp cấu hình thực tế một cách an toàn:** phiên bản dependency, `table-prefix`, JDBC URL đã che thông tin nhạy cảm, profile và tên DataSource mà TaskRepository đang dùng.
2. **Xác minh kết nối:** dùng cùng role và database để chạy `SELECT current_database(), current_schema()`, đồng thời xem `SHOW search_path` trên PostgreSQL.
3. **Đối chiếu DDL:** kiểm tra tên bảng, sequence, index và quyền. Không chỉ tìm mỗi bảng `TASK_EXECUTION`.
4. **Tìm bản ghi lần chạy thử:** khởi chạy một task có tên dễ xác định, sau đó kiểm tra trực tiếp nhóm bảng đã chọn.
5. **So với cấu hình Batch và nghiệp vụ:** nếu có nhiều DataSource hoặc profile, xác nhận repository nào đang dùng connection nào.

Tránh sửa dữ liệu TaskRepository bằng `UPDATE`/`DELETE` trực tiếp để “chữa” lỗi cấu hình, vì có thể làm mất lịch sử thực thi hoặc phá vỡ quan hệ tới metadata Batch. Hãy điều tra mapping schema/prefix trước khi can thiệp dữ liệu.

## 12. Checklist trước khi triển khai production

| Câu hỏi | Điều kiện đạt |
|---|---|
| Phiên bản Spring Cloud Task và dialect đã được cố định? | Có dependency và DDL tương ứng được review |
| Giá trị `tablePrefix` đã thống nhất? | Runtime config, DDL, migration và monitoring dùng cùng quy ước |
| Schema thực sự tồn tại? | Được tạo bởi migration và truy cập đúng namespace |
| Quyền runtime đủ nhưng có giới hạn? | Có quyền DML/sequence cần thiết, không phụ thuộc quyền tạo/drop schema |
| Sequence/identity đúng trạng thái? | Ghi TaskExecution mới không trùng ID sau migration |
| Các thành phần dùng nhiều DataSource đã được kiểm tra? | TaskRepository, JobRepository và nghiệp vụ dùng đúng kết nối |
| Đã thử cả thành công và thất bại? | TaskExecution xuất hiện đúng bảng với thời gian và mã thoát phù hợp |
| Có kế hoạch xử lý dữ liệu cũ? | Đã quyết định copy, lưu trữ hay giữ repository cũ |
| Dashboard, alert và backup đã đổi cùng lúc? | Không còn truy vấn nhầm bộ bảng metadata |
| Có kế hoạch rollback/cutover? | Có backup, thời điểm dừng khởi chạy và cách phục hồi an toàn |

**Kết luận:** `tablePrefix` quyết định **tên bảng metadata Spring Cloud Task truy cập**, còn schema quyết định **namespace mà kết nối CSDL sử dụng**. Muốn tùy chỉnh an toàn, phải làm đồng bộ **cấu hình repository, DataSource, DDL/migration, quyền truy cập và các công cụ quan sát**. Khi hệ thống xử lý các tác vụ có vòng đời hữu hạn, sự nhất quán này giúp TaskRepository ghi đúng lịch sử thực thi, hỗ trợ điều tra lỗi, chạy lại tác vụ và vận hành nhiều ứng dụng hoặc môi trường mà không lẫn metadata.
