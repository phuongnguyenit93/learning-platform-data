# Tách dữ liệu giữa môi trường và giữa các đơn vị thuê

## Mục tiêu học tập

Sau bài học này, người học có thể:

1. Phân biệt **tách môi trường** (*environment isolation*) với **tách đơn vị thuê** (*tenant isolation*) trong một nền tảng lưu trữ dữ liệu.
2. Xây dựng ranh giới phát triển/kiểm thử/staging/production theo tài khoản hạ tầng, danh tính dịch vụ, kho dữ liệu, secret, khóa mã hóa, backup và quyền truy cập.
3. So sánh ba mô hình multi-tenancy: **database riêng**, **schema riêng** và **bảng dùng chung có `tenant_id`**, kể cả mô hình lai.
4. Thiết kế khóa chính/khóa ngoại theo tenant, điều kiện truy vấn, phân quyền và Row-Level Security (RLS) để giảm nguy cơ đọc/ghi chéo tenant.
5. Truyền tenant context đã xác thực qua service Java đến JDBC transaction mà không làm rò trạng thái qua connection pool.
6. Nhận diện các đường rò rỉ ngoài database: cache, queue, object storage, search index, log, tracing, export, backup và công cụ quản trị.
7. Lập kế hoạch kiểm thử âm tính, migration, phục hồi, giám sát và đối soát để chứng minh ranh giới vẫn đúng khi hệ thống phát triển.

Bài thuộc chương **An toàn dữ liệu** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Module đặt mục tiêu hiểu lưu trữ bền vững trong Java, từ mô hình dữ liệu, lược đồ, truy vấn, chỉ mục đến transaction, cô lập và kiểm soát đồng thời; đồng thời quản lý lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và hiệu năng. Phân tách đúng phải bảo vệ **đường đọc, đường ghi, vận hành và phục hồi**, không chỉ thêm một cột `tenant_id`.

## 1. Hai trục cô lập khác nhau

Giả sử công ty cung cấp dịch vụ quản lý đơn hàng dạng SaaS. Hệ thống có:

- **Môi trường:** `development`, `test`, `staging`, `production`.
- **Đơn vị thuê:** Tenant A là một doanh nghiệp; Tenant B là doanh nghiệp khác.

Hai trục độc lập tạo thành một ma trận:

~~~text
                         MÔI TRƯỜNG
             DEVELOPMENT    STAGING       PRODUCTION
           +-------------+-------------+-------------+
Tenant A   | dữ liệu giả | dữ liệu thử | dữ liệu thật |
           +-------------+-------------+-------------+
Tenant B   | dữ liệu giả | dữ liệu thử | dữ liệu thật |
           +-------------+-------------+-------------+
Tenant C   | dữ liệu giả | dữ liệu thử | dữ liệu thật |
           +-------------+-------------+-------------+
~~~

Mỗi ô phải tuân theo hai bất biến:

1. **Cross-environment:** tiến trình, credential hay pipeline ở dev/staging không được tùy tiện đọc, ghi, xóa hoặc khôi phục dữ liệu production.
2. **Cross-tenant:** người dùng, token và tác vụ thuộc Tenant A không được đọc hoặc thay đổi dữ liệu Tenant B nếu chưa có quyền rõ ràng và được kiểm soát.

Tách môi trường không thay thế tách tenant. Một production database có thể được cô lập khỏi staging nhưng vẫn bị rò dữ liệu giữa hai tenant vì quên điều kiện `WHERE tenant_id = ?`. Ngược lại, chính sách RLS hoàn chỉnh trong production không ngăn một nhân viên sao chép nguyên bản production database chứa dữ liệu thật vào máy phát triển không được bảo vệ.

### 1.1. Khái niệm “đơn vị thuê”

**Tenant** là ranh giới sở hữu dữ liệu và quyền truy cập theo sản phẩm. Một tenant có thể là một tổ chức, tài khoản doanh nghiệp hoặc workspace. Tenant **không tự đồng nghĩa** với người dùng, database, schema hay một HTTP request.

Ví dụ một người dùng có quyền ở cả Tenant A và B. Lúc đó người dùng vẫn phải chọn/được cấp tenant context cho thao tác cụ thể. Hệ thống không được suy “đã đăng nhập” là đủ để xem mọi tenant.

Ngoài tenant còn có các phạm vi khác: owner, phòng ban, dự án, vùng dữ liệu và vai trò quản trị. Hệ thống có thể cần kiểm tra **cả tenant và quyền trên từng tài nguyên**.

## 2. Đặt mô hình đe dọa và mức bảo đảm trước khi chọn kỹ thuật

Không phải mọi hệ thống cần database vật lý riêng cho từng khách hàng, nhưng mọi hệ thống phải xác định rõ rủi ro.

| Câu hỏi | Ví dụ cần trả lời |
| --- | --- |
| Ai có thể bị xâm nhập? | Người dùng bình thường, tài khoản dịch vụ, nhân viên vận hành, container ứng dụng |
| Lỗi phần mềm nào có thể xảy ra? | Quên filter tenant, SQL injection, truyền nhầm token, cache key thiếu tenant |
| Điều gì cần ngăn tuyệt đối? | Lộ dữ liệu khách hàng khác, staging sửa sản xuất, ghi vượt quyền |
| Điều gì chấp nhận đánh đổi? | Hiệu năng, chi phí thêm database, độ trễ migration, nhu cầu hỗ trợ đa vùng |
| Ai được quyền truy cập xuyên tenant? | Tài khoản hỗ trợ theo quy trình đặc biệt, có phạm vi và audit |
| Có yêu cầu theo vùng/pháp lý không? | Dữ liệu cần lưu ở vị trí xác định, chính sách retention và xóa |
| Nếu một tầng kiểm soát hỏng? | Database policy, ứng dụng, network hoặc IAM còn lớp phòng thủ nào? |

Khả năng tách biệt cần được đánh giá theo **đường tấn công và phạm vi sự cố**. Ví dụ shared-table + RLS có thể bảo vệ tốt trước câu SELECT thiếu filter tenant ở ứng dụng, nhưng không biến quyền DB của một ứng dụng đã bị kiểm soát hoàn toàn thành ranh giới tuyệt đối giữa những tenant.

Nguyên tắc thiết kế: **defense in depth** — xác thực người dùng, kiểm tra quyền ứng dụng, truyền tenant context đáng tin, áp dụng giới hạn ở DB, rồi bảo vệ tài nguyên phụ và hoạt động vận hành.

## 3. Tách môi trường: không chỉ khác tên database

Một setup có thể đặt các database `app_dev`, `app_staging` và `app_prod` trên cùng một PostgreSQL instance. Dù có tên khác, chúng vẫn có thể chia sẻ quyền quản trị, CPU, I/O, storage, lỗi cấu hình, backup hoặc tài khoản cloud.

Đối với production, mức phân tách thường nên mạnh hơn tùy mức rủi ro:

| Thành phần | Mục tiêu phân tách | Sai lầm thường gặp |
| --- | --- | --- |
| Tài khoản/project cloud | Production ở account/project có IAM và policy riêng | Một automation token có quyền quản trị tất cả môi trường |
| Network/VPC/subnet | Chỉ service được cấp quyền kết nối tới database tương ứng | Laptop dev truy cập trực tiếp production qua public endpoint |
| Database/cluster | Resource/backup/maintenance tách theo yêu cầu rủi ro | Staging và prod dùng chung writable cluster với role quá rộng |
| Service identity | Mỗi môi trường có danh tính và quyền tối thiểu riêng | Dùng chung DB user/password cho staging và production |
| Secret và encryption key | Secret scope, rotation, KMS key tách phù hợp | Copy `.env` production vào container test |
| Object storage | Bucket/container và prefix kiểm soát riêng | Job staging ghi nhầm bucket hóa đơn production |
| Queue/event bus | Topic/subscription và quyền publish/consume tách | Consumer thử nghiệm nhận event thanh toán thật |
| Cache/search | Redis namespace/instance và search index tách | Invalidation ở staging xóa cache production |
| Logging/tracing | Dataset và quyền xem dữ liệu riêng, retention phù hợp | Đẩy PII production sang log test |
| Backup/restore | Chính sách, khóa, đích khôi phục và quyền riêng | Restore bản production đầy đủ sang môi trường có quyền yếu |
| CI/CD | Quy trình approval và deployment identity theo env | Pipeline nhánh tính năng có quyền chạy migration prod |

Không phải cấu hình “tách hoàn toàn mọi thứ” luôn khả thi về chi phí. Nhưng **tách danh tính, quyền và đường truy cập production** thường là yêu cầu nền tảng; phần dùng chung phải được đánh giá chủ động và có cơ chế chống lỗi dây chuyền.

### 3.1. Luồng dữ liệu theo môi trường

~~~text
                    SOURCE CODE / MIGRATIONS
                              |
             +----------------+----------------+
             |                |                |
             v                v                v
         DEV deploy       STAGING deploy     PROD deploy
             |                |                |
          IAM dev          IAM staging        IAM prod
             |                |                |
          DB dev           DB staging         DB prod
          Test data        Sanitized data     Customer data
             |                |                |
          Backup dev       Backup staging     Backup prod
~~~

**Mã nguồn và migration** có thể dùng chung, nhưng endpoint, principal, dữ liệu và quyền chạy phải do hệ thống triển khai cấp đúng môi trường. Không để code tự đoán production bằng cách kiểm tra một hostname gần giống nhau hoặc fallback sang production khi cấu hình dev thiếu.

### 3.2. Fail closed khi cấu hình sai

Một dịch vụ test không nên tự động kết nối tới production nếu `DB_URL` thiếu. Nên từ chối khởi động khi biến môi trường quan trọng không hợp lệ.

Ví dụ minh họa policy khi khởi động Java:

~~~java
public final class EnvironmentGuard {
    public static void validate(String environment, String jdbcUrl) {
        if (environment == null || environment.isBlank()) {
            throw new IllegalStateException("Environment not configured");
        }
        if (jdbcUrl == null || jdbcUrl.isBlank()) {
            throw new IllegalStateException("Database endpoint missing");
        }
        if (!environment.equals("production")
                && jdbcUrl.contains("prod-db.internal")) {
            throw new IllegalStateException(
                    "Non-production service targets production database");
        }
    }
}
~~~

Đây chỉ là **guard minh họa để phát hiện một cấu hình sai rõ ràng**; so chuỗi URL không phải biện pháp bảo mật đáng tin (DNS alias, proxy và endpoint có thể đổi). Ranh giới thật cần IAM, network policy, credentials riêng, quy trình phân phối secret và database authorization được thực thi độc lập.

### 3.3. Production data dùng cho kiểm thử

Không sao chép dữ liệu khách hàng thật sang dev/staging chỉ vì cần dữ liệu gần thực tế. Ưu tiên:

1. Sinh dữ liệu tổng hợp có phân bố, kích thước và quan hệ phản ánh workload.
2. Nếu bắt buộc dùng dữ liệu lấy từ production, có quy trình phê duyệt, giới hạn mục đích và phạm vi.
3. Mask/pseudonymize hoặc anonymize theo yêu cầu, đánh giá nguy cơ tái định danh.
4. Loại bỏ secret, access token, email/địa chỉ/số điện thoại thật và những tài liệu đính kèm nhạy cảm trước khi dữ liệu rời vùng tin cậy.
5. Bảo vệ bản sao được tạo trong quá trình xử lý, kể cả file dump tạm, object store, log và bản backup thứ cấp.
6. Dùng tài khoản, endpoint gửi email/SMS/thanh toán giả lập; ngăn test kích hoạt tác dụng phụ thật.

**Pseudonymization không đồng nghĩa anonymization.** Dữ liệu vẫn có thể liên kết lại với cá nhân khi tồn tại khóa hoặc các trường kết hợp dễ nhận dạng. Việc thay email bằng một chuỗi giả không tự bảo đảm dataset không còn thông tin nhạy cảm.

## 4. Ba mô hình tách tenant phổ biến

### 4.1. Database riêng cho từng tenant

~~~text
Application / Tenant Router
         |
   +-----+-----+-----+
   |           |     |
 DB Tenant A  DB B  DB C
~~~

Ưu điểm:

- Ranh giới logic và quyền truy cập ở cấp database rõ ràng.
- Có thể thiết kế backup/restore, retention, encryption và mở rộng độc lập theo tenant.
- Một tenant có thể có yêu cầu riêng về region hoặc cấu hình khi kiến trúc hỗ trợ.

Đánh đổi:

- Số database/connection pool/migration có thể tăng theo số tenant.
- Quản trị version schema, health check và routing phức tạp hơn.
- Dù database khác nhau, chúng có thể vẫn dùng chung instance, storage hoặc quyền quản trị — không tự có cô lập vật lý.
- Giao dịch/chức năng xuyên tenant đòi hỏi quy trình đặc biệt.

### 4.2. Schema riêng trong một database

~~~text
Database instance
    |
    +-- schema tenant_a: orders, order_items
    +-- schema tenant_b: orders, order_items
    +-- schema tenant_c: orders, order_items
~~~

Ưu điểm: tách namespace đối tượng SQL, dễ phân biệt schema và có thể quản lý quyền theo schema.

Rủi ro:

- Quyền truy cập schema, `search_path` và tenant routing phải đúng.
- Shared connection pool dễ giữ trạng thái session của tenant cũ nếu reset thiếu.
- Nâng cấp hàng trăm schema phải có migration orchestration.
- Toàn bộ schema vẫn có thể chia sẻ CPU, I/O, backup và vai trò database.

**Không dùng việc đổi `search_path` trên pooled connection làm biện pháp bảo mật duy nhất.** Cần kiểm soát quyền database và reset tenant scope cho mỗi transaction/request.

### 4.3. Bảng dùng chung, mỗi hàng có `tenant_id`

~~~text
orders
+-----------+----------+------------+
| tenant_id | order_id | amount     |
+-----------+----------+------------+
| A         | 101      | 200000     |
| B         | 101      | 350000     |
| A         | 102      | 180000     |
+-----------+----------+------------+
~~~

Trong mô hình này, `tenant_id` là phần của khóa và điều kiện truy vấn. Ưu điểm là ít đối tượng DB, triển khai schema đồng nhất và kết nối dễ gom theo workload. Nhưng rủi ro rất rõ: một câu SQL thiếu filter tenant có thể đọc hoặc sửa dữ liệu khách hàng khác.

Nếu chọn shared tables, nên kết hợp:

- Kiểm tra tenant ở API/service.
- Composite key và foreign key mang `tenant_id`.
- RLS tại DB nếu engine hỗ trợ phù hợp.
- Chỉ mục được thiết kế cho truy vấn theo tenant.
- Cache key, message và object key chứa tenant scope.
- Test âm tính cố tình truy cập chéo tenant.

### 4.4. Bảng so sánh

| Tiêu chí | Database-per-tenant | Schema-per-tenant | Shared tables |
| --- | --- | --- | --- |
| Ranh giới đối tượng DB | Mạnh hơn về mặt namespace | Tách namespace trong một DB | Chung bảng, tách theo hàng |
| Chi phí vận hành | Tăng với nhiều tenant | Tăng với số schema/migration | Thường ít đối tượng hơn |
| Backup/restore tenant | Thường thuận lợi hơn | Có thể cần quy trình lọc theo schema | Thường cần export/restore theo tenant cẩn trọng |
| Tenant routing | Chọn datasource/database | Chọn schema/context | Truyền tenant_id và policy |
| Rủi ro quên tenant filter | Thường ít hơn nếu credential chỉ thấy một DB | Phụ thuộc quyền/schema | Cao nếu không có RLS/lớp phòng thủ |
| Noisy neighbor | Tùy mức tách hạ tầng | Vẫn chia sẻ nhiều tài nguyên | Chia sẻ tài nguyên nhiều |
| Migration quy mô lớn | Nhiều DB | Nhiều schema | Ít bảng hơn, nhưng bảng có thể rất lớn |
| Khả năng di chuyển tenant | Chuyển DB/route | Chuyển schema/route | Copy và chuyển theo tập hàng |

Mô hình lai khá phổ biến: phần lớn tenant dùng shared-table, còn tenant có yêu cầu pháp lý hoặc tải lớn được chuyển sang database riêng. Router phải có metadata và version để chuyển đúng authority, tránh đồng thời ghi vào hai nơi mà không có protocol nhất quán.

## 5. Thiết kế schema PostgreSQL với ranh giới tenant rõ ràng

Một ví dụ shared-table dùng khóa ghép để mọi tham chiếu từ dòng đơn hàng về đơn đều mang tenant:

~~~sql
CREATE TABLE tenants (
    tenant_id BIGINT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE orders (
    tenant_id BIGINT NOT NULL REFERENCES tenants(tenant_id),
    order_id BIGINT GENERATED ALWAYS AS IDENTITY,
    request_key TEXT NOT NULL,
    status TEXT NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL
        CHECK (total_amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, order_id),
    UNIQUE (tenant_id, request_key)
);

CREATE TABLE order_items (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(14, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES orders (tenant_id, order_id)
);
~~~

**Điểm quan trọng của khóa ghép:** một `order_items` của Tenant B không thể trỏ đến order thuộc Tenant A bằng cách chỉ cung cấp cùng `order_id` mà bỏ tenant, vì khóa ngoại yêu cầu **cả `tenant_id` và `order_id` trùng một hàng cha**.

Cột `order_id` được sinh bằng identity trong ví dụ, nhưng khóa chính logic vẫn là cặp `(tenant_id, order_id)`. Tính không trùng trên toàn hệ thống của riêng `order_id` không được dùng làm bằng chứng về phân quyền.

### 5.1. UNIQUE phải thể hiện đúng phạm vi nghiệp vụ

Nếu mỗi tenant có thể dùng cùng mã yêu cầu `checkout-001`, constraint đúng là:

~~~sql
UNIQUE (tenant_id, request_key)
~~~

Thay vì `UNIQUE (request_key)` gây xung đột giả giữa các tenant. Nhưng nếu một định danh thật sự cần duy nhất trên toàn hệ thống, có thể cần unique toàn cục; không đưa `tenant_id` vào mọi constraint một cách máy móc.

Mọi phép `INSERT ... ON CONFLICT` và idempotency key phải xác định phạm vi tenant. Một request trùng key nhưng khác tenant **không được trả lại kết quả của tenant kia**.

### 5.2. Truy vấn và chỉ mục đi cùng tenant scope

~~~sql
SELECT order_id, status, total_amount, created_at
FROM orders
WHERE tenant_id = ?
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
~~~

Chỉ mục ứng viên:

~~~sql
CREATE INDEX idx_orders_tenant_recent
ON orders (tenant_id, created_at DESC, order_id DESC);
~~~

Khi phần lớn truy vấn được giới hạn theo tenant, đặt `tenant_id` phù hợp trong composite index có thể giúp DB thu hẹp phạm vi đọc. Tuy nhiên, cần kiểm tra **EXPLAIN, actual rows, buffer hit/read** và cả chi phí ghi/index maintenance trên dữ liệu thật.

**Chỉ mục không phải cơ chế authorization.** Một query thiếu tenant predicate có thể vẫn chạy nhanh và lộ dữ liệu nếu database role không bị giới hạn.

### 5.3. Không chỉ kiểm tra tenant ở đầu chuỗi truy vấn

Ví dụ JOIN nguy hiểm nếu sai khóa:

~~~sql
-- Sai về mặt mô hình đa tenant nếu order_id có thể trùng:
SELECT *
FROM orders o
JOIN order_items i ON i.order_id = o.order_id;
~~~

JOIN đúng phải mang đủ tenant scope:

~~~sql
SELECT o.order_id, i.line_no, i.quantity
FROM orders o
JOIN order_items i
  ON i.tenant_id = o.tenant_id
 AND i.order_id = o.order_id
WHERE o.tenant_id = ?;
~~~

Với hàng dữ liệu từ bảng cha sang bảng con, bỏ tenant trong JOIN có thể ghép nhầm dữ liệu và khiến thông tin tenant khác đi vào response. Composite foreign key và code review/query test giúp giảm nguy cơ này.

## 6. Row-Level Security: thêm lớp kiểm soát tại PostgreSQL

PostgreSQL hỗ trợ **Row-Level Security (RLS)** để áp chính sách đối với hàng được phép đọc, sửa, xóa và thêm. Khi dùng shared tables, RLS là một lớp phòng thủ quan trọng trước đường query vô tình quên tenant filter.

Giả định vai trò runtime `app_runtime` đã được quản trị tạo và cấp quyền tối thiểu cần thiết; vai trò này **không phải superuser, không có thuộc tính `BYPASSRLS` và không sở hữu bảng**.

Ví dụ:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_policy
ON orders
FOR ALL TO app_runtime
USING (
    tenant_id = NULLIF(
        current_setting('app.tenant_id', true), ''
    )::BIGINT
)
WITH CHECK (
    tenant_id = NULLIF(
        current_setting('app.tenant_id', true), ''
    )::BIGINT
);

ALTER TABLE order_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_items FORCE ROW LEVEL SECURITY;

CREATE POLICY order_items_tenant_policy
ON order_items
FOR ALL TO app_runtime
USING (
    tenant_id = NULLIF(
        current_setting('app.tenant_id', true), ''
    )::BIGINT
)
WITH CHECK (
    tenant_id = NULLIF(
        current_setting('app.tenant_id', true), ''
    )::BIGINT
);
~~~

Ý nghĩa:

- `USING` giới hạn hàng mà vai trò được nhìn thấy/thao tác theo operation.
- `WITH CHECK` kiểm tra hàng mới sau `INSERT` hoặc `UPDATE` phù hợp tenant hiện hành.
- `current_setting('app.tenant_id', true)` đọc một custom setting; khi chưa có setting, kết quả có thể là NULL và điều kiện so sánh không cho phép hàng nào.
- `NULLIF(..., '')` xử lý trường hợp setting rỗng; giá trị không chuyển được thành BIGINT sẽ báo lỗi, không phải tự nhận một tenant khác.
- `FORCE ROW LEVEL SECURITY` khiến chủ bảng thông thường cũng chịu chính sách, nhưng **superuser và role có `BYPASSRLS` vẫn có thể vượt qua RLS** theo quyền PostgreSQL.

RLS chỉ áp dụng cho các bảng đã bật và những role theo quy tắc phù hợp. Bảng `tenants`, bảng audit, aggregate, view, function hoặc nguồn dữ liệu khác phải được phân quyền riêng; **bật RLS trên `orders` không tự bảo vệ mọi bảng trong database**.

### 6.1. RLS không thay thế xác thực tenant

Phải lấy tenant context từ **principal đã xác thực và đã được phép vào tenant**, không tin `tenant_id` do HTTP client gửi lên như một quyền tự thân. Một client có thể đưa `tenant_id=999` trong URL hoặc JSON; service phải kiểm tra membership và vai trò trước khi thực hiện truy cập.

Quan trọng hơn, nếu application DB role được phép chạy SQL tùy ý và có thể thay đổi `app.tenant_id`, kẻ tấn công kiểm soát hoàn toàn connection dưới role này có thể đặt tenant khác. Do đó **RLS dựa trên session variable do chính application role đặt là defense in depth**, không phải ranh giới bảo mật trước một runtime đã bị chiếm quyền thực thi SQL. Với yêu cầu isolation mạnh hơn, cân nhắc credential/DB riêng theo tenant, role-specific policy, trusted gateway hoặc mô hình hạ tầng khác.

### 6.2. Các ngoại lệ và đường tắt cần kiểm soát

- Superuser và `BYPASSRLS` không được dùng cho traffic ứng dụng thông thường.
- Chủ bảng có thể bỏ qua RLS nếu không `FORCE`; cần hiểu quyền sở hữu và deploy/migration role.
- Function chạy với quyền của chủ sở hữu (`SECURITY DEFINER`), view hoặc extension có thể tạo đường truy cập đặc biệt tùy cấu hình; phải kiểm tra quyền và `search_path`.
- Constraint như UNIQUE/FK được DB thực thi theo quy tắc toàn vẹn, không được xem RLS như một cơ chế ngăn mọi thông tin suy luận qua lỗi ràng buộc hoặc timing.
- Các lệnh maintenance, backup, ETL và migration thường có quyền cao hơn, nên cần audit và kiểm tra môi trường/tenant riêng.

RLS phải được **thử với đúng role mà ứng dụng production sử dụng**, không chỉ thử bằng tài khoản DBA.

## 7. Java/JDBC: tenant context trong một transaction cụ thể

Khi dùng connection pool, nhiều request từ tenant khác nhau có thể mượn **cùng kết nối vật lý** ở các thời điểm khác nhau. Nếu dùng `SET app.tenant_id = '42'` ở cấp session rồi trả connection, request tiếp theo có nguy cơ thừa hưởng state nếu pool không reset custom setting.

Một thiết kế tốt hơn cho PostgreSQL là truyền setting trong **phạm vi transaction** bằng `set_config(..., true)` (tương đương ý tưởng `SET LOCAL`), rồi để commit/rollback kết thúc phạm vi đó.

Ví dụ Java 17:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class TenantOrdersRepository {
    public record TenantContext(long tenantId) {}

    public record OrderSummary(
            long orderId, String status, BigDecimal totalAmount) {}

    private final DataSource dataSource;

    public TenantOrdersRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<OrderSummary> recent(
            TenantContext authorizedTenant, int requestedLimit)
            throws SQLException {

        if (authorizedTenant == null || authorizedTenant.tenantId() <= 0) {
            throw new IllegalArgumentException(
                    "Trusted tenant context is required");
        }
        int limit = Math.max(1, Math.min(requestedLimit, 100));
        List<OrderSummary> results = new ArrayList<>();

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                // Ghi tenant scope chỉ trong transaction hiện tại.
                try (PreparedStatement scope = connection.prepareStatement(
                        "SELECT set_config('app.tenant_id', ?, true)")) {
                    scope.setString(
                            1, Long.toString(authorizedTenant.tenantId()));
                    try (ResultSet ignored = scope.executeQuery()) {
                        if (!ignored.next()) {
                            throw new SQLException("Tenant scope not set");
                        }
                    }
                }

                String sql = """
                    SELECT order_id, status, total_amount
                    FROM orders
                    WHERE tenant_id = ?
                    ORDER BY created_at DESC, order_id DESC
                    LIMIT ?
                    """;

                try (PreparedStatement statement =
                             connection.prepareStatement(sql)) {
                    statement.setLong(1, authorizedTenant.tenantId());
                    statement.setInt(2, limit);

                    try (ResultSet rows = statement.executeQuery()) {
                        while (rows.next()) {
                            results.add(new OrderSummary(
                                    rows.getLong("order_id"),
                                    rows.getString("status"),
                                    rows.getBigDecimal("total_amount")));
                        }
                    }
                }

                connection.commit();
                return results;
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
~~~

**Giả định bắt buộc:** `TenantContext` phải do tầng xác thực/phân quyền tạo ra và được truyền qua service; repository không tự xác minh membership. Constructor của record tự nó không làm giá trị trở thành đáng tin, nên không để HTTP controller dựng record trực tiếp từ header mà không kiểm tra.

Ở ví dụ này:

1. Mượn `Connection` từ `DataSource`.
2. `setAutoCommit(false)` mở phạm vi transaction cần cho setting local.
3. `set_config(..., true)` đặt tenant ID trong cùng transaction và cùng connection.
4. Query có thêm `WHERE tenant_id = ?` để rõ ý nghĩa và giúp truy vấn/chỉ mục, dù RLS cũng kiểm tra.
5. Đọc hết `ResultSet`, rồi commit để kết thúc tenant scope.
6. Khi có lỗi, rollback và đóng tài nguyên bằng `try-with-resources`.

Ví dụ cố ý **không dùng biến `static` chứa current tenant** và không gán tenant vào singleton repository. Nếu framework cung cấp transaction manager, cần đặt tenant scope ở đầu **transaction thật** do framework quản lý, không vô tình mở một transaction JDBC riêng bên ngoài.

### 7.1. Vì sao transaction-scoped setting tốt hơn session-scoped?

~~~text
Request của Tenant A:
  Connection #7
    BEGIN
    SET LOCAL app.tenant_id = 42
    SELECT/UPDATE ...
    COMMIT

Connection #7 trở về pool.

Request của Tenant B:
  Connection #7
    BEGIN
    SET LOCAL app.tenant_id = 77
    SELECT/UPDATE ...
    COMMIT
~~~

Sau commit/rollback, setting local hết hiệu lực theo transaction. Nhờ đó giảm nguy cơ state tenant A ở lại session phục vụ B.

Tuy nhiên, vẫn phải kiểm tra hành vi thực tế của connection pool, transaction manager, thread hopping và các câu query ngoài transaction. Nếu một query chạy **trước khi tenant scope được đặt**, trong policy fail-closed đúng, nó không được nhìn thấy dữ liệu tenant; đây là một test âm tính quan trọng.

## 8. Transaction, concurrency và idempotency theo tenant

Tách tenant không chỉ là chặn SELECT. Mọi đường ghi cần giữ bất biến tại nguồn dữ liệu.

### 8.1. Đặt hàng và tránh request trùng

~~~sql
INSERT INTO orders (
    tenant_id, request_key, status, total_amount
)
VALUES (?, ?, 'PENDING', ?)
ON CONFLICT (tenant_id, request_key) DO NOTHING
RETURNING order_id;
~~~

Key idempotency phải gồm **phạm vi tenant**. Nếu cùng `request_key` được gửi lại sau timeout/COMMIT chưa rõ kết quả, hệ thống cần đọc và so khớp đơn hiện có theo `tenant_id + request_key`, không sinh đơn mới hoặc trả nhầm đơn của tenant khác.

Ràng buộc UNIQUE là nền tảng, nhưng nghiệp vụ còn phải kiểm tra payload gốc, trạng thái và các tác động ngoài DB. Một `SQLException` sau COMMIT không chứng minh transaction thất bại; quy trình đối soát cần dùng connection mới với đúng tenant scope.

### 8.2. Không dựa vào cache để giữ bất biến

Ví dụ stock theo tenant:

~~~sql
UPDATE inventory
SET available = available - ?
WHERE tenant_id = ?
  AND product_id = ?
  AND available >= ?;
~~~

Đây là mẫu có điều kiện; cần tạo bảng `inventory`, constraint `available >= 0` và index phù hợp trước khi dùng. Kiểm tra số hàng cập nhật để biết thao tác có hợp lệ. Nếu cần tạo đơn cùng lúc, đặt cập nhật stock và tạo order **cùng transaction**.

Nếu hệ thống dùng một tenant ID trong cache key nhưng SQL UPDATE lại quên tenant ID, cache không cứu được tính đúng đắn. **Database constraint, transaction và RLS phải độc lập với đường cache**.

### 8.3. Xung đột trên tài nguyên chia sẻ

Hai tenant có thể chia sẻ tài nguyên vật lý DB và ảnh hưởng hiệu năng nhau (noisy neighbor), nhưng không vì vậy mà được chia sẻ object nghiệp vụ sai phạm vi. Các transaction dùng cùng bảng vẫn có thể tranh chấp row/page/index; cần đo lock wait, pool và độ chọn lọc index theo tenant.

Nếu sản phẩm có **tài nguyên thật sự dùng chung nhiều tenant**, chẳng hạn một kho hàng của nhà cung cấp, phải mô hình hóa ownership và quy tắc quyền rõ ràng. Không xóa tenant filter chỉ để giải quyết một use case chia sẻ đặc biệt.

## 9. Ngoài PostgreSQL: mọi bản sao dữ liệu đều cần ranh giới

Một dữ liệu có thể chảy qua nhiều hệ thống:

~~~text
Java service
    |
    +-- PostgreSQL (source of truth)
    +-- Redis / near cache
    +-- Search index
    +-- Queue / outbox / event bus
    +-- Object storage / attachments
    +-- Analytics / warehouse
    +-- Logs / traces / exports
    +-- Backup / replicas
~~~

Mỗi tầng phải thể hiện **environment** và **tenant** đủ để không dùng nhầm dữ liệu.

| Tầng | Rủi ro | Kiểm soát |
| --- | --- | --- |
| Redis/cache | Key chỉ có `order_id`, tenant A nhận cache B | Key gồm env/tenant/object; giới hạn namespace/IAM, TTL và invalidation |
| Search | Query thiếu tenant filter; search index gom mọi khách hàng | Phân quyền theo index/tenant, áp filter đáng tin ở server, test chéo tenant |
| Message/event | Consumer nhận event từ môi trường/tenant khác | Namespace/topic/credential riêng, message metadata đáng tin, authorization |
| Outbox | Worker dùng global query rồi publish sai tenant | Outbox chứa tenant ID, handler kiểm tra scope, idempotency theo tenant |
| Object storage | Hai tenant trùng tên file hoặc pre-signed URL không đúng scope | Bucket/prefix và IAM phù hợp, object ownership, URL có thời hạn/ngữ cảnh |
| Export/report | CSV có dữ liệu nhiều tenant nhưng được gửi một khách hàng | Export job ràng buộc tenant/authorization, kiểm tra trước khi phát hành |
| Logs/traces | Ghi raw SQL/payload/PII hoặc tenant token | Redaction, quyền truy cập theo env, retention, tránh dữ liệu nhạy cảm |
| Backup/restore | Restore data production vào staging hoặc chồng dữ liệu tenant khác | Chính sách đích restore, scrub dữ liệu, mã hóa, kiểm chứng identity |
| Metrics | Label chứa ID bí mật, số lượng nhãn quá cao | Tổng hợp an toàn, phân quyền dashboard, hạn chế cardinality |

Một tiền tố key như `prod:tenant42:order101` giúp tránh nhầm, nhưng **không tự tạo phân quyền** nếu mọi ứng dụng đều có credential đọc toàn bộ Redis. Nên tách Redis instance/ACL khi phạm vi rủi ro đòi hỏi, và kiểm tra tenant ở server trước khi đọc/ghi.

### 9.1. Event nhất thiết phải có nguồn gốc và phiên bản

Ví dụ thông điệp:

~~~json
{
  "environment": "production",
  "tenantId": 42,
  "eventId": "order-created-9c1e",
  "eventType": "OrderCreated",
  "orderId": 101,
  "schemaVersion": 2
}
~~~

Các trường trên là minh họa. Consumer **không được tin mù** giá trị tenant/environ trong payload từ nguồn không đáng tin; cần xác thực nguồn, quyền topic, schema và kiểm tra tenant context.

Khi retry at-least-once, deduplication cần xét `tenantId` và `eventId` theo hợp đồng. Không ghi một event nhận từ staging vào production chỉ vì payload có trường `environment: production`.

### 9.2. Cache invalidation và multi-tenancy

Giả sử Tenant A cập nhật order `101`. Nếu invalidation gửi `DEL order:101` nhưng cache dùng chung ID giữa tenant, có thể xóa nhầm hoặc làm mới sai tenant. Key và event phải có cùng định nghĩa scope, ví dụ:

~~~text
production:tenant:42:order:101
staging:tenant:42:order:101
production:tenant:77:order:101
~~~

Nhưng vẫn cần chống race cache-aside, TTL, versioning hoặc generation guard khi yêu cầu độ mới cao; **key đúng không tự đảm bảo cache luôn mới**.

## 10. Backup, restore và xóa dữ liệu theo tenant/môi trường

Độ bền dữ liệu chỉ có ý nghĩa nếu có thể khôi phục **đúng tập dữ liệu ở đúng nơi**.

### 10.1. Backup theo mô hình tenancy

| Mô hình | Việc sao lưu thường thuận lợi | Thách thức khi khôi phục một tenant |
| --- | --- | --- |
| Database-per-tenant | Sao lưu/restore theo database | Cần quản lý số lượng bản sao và quyền tenant |
| Schema-per-tenant | Có thể xuất schema riêng tùy công cụ | Dependency xuyên schema, quyền, extension và consistency |
| Shared-table | Backup database toàn vẹn | Restore một tenant cần chọn đúng hàng/quan hệ, đối soát FK và dữ liệu phụ |

Nếu dùng shared tables, không thể chỉ `DELETE WHERE tenant_id = ?` để coi như đã xóa mọi dữ liệu tenant: còn dữ liệu ở search, cache, object storage, queue, warehouse, log, backup và bản sao bị giữ theo retention.

### 10.2. Khôi phục thử nhưng không lộ production

Khi diễn tập restore production:

1. Chọn đích restore được bảo vệ tương xứng với dữ liệu gốc.
2. Tạo principal và network policy chỉ cho đội/automation được ủy quyền.
3. Tắt hoặc sandbox các integration gửi email, thanh toán và event ra ngoài.
4. Không để endpoint restore bị nhận nhầm là primary đang phục vụ.
5. Kiểm tra độ nhất quán, version schema, WAL/backup chain và kết quả dữ liệu.
6. Nếu đích là môi trường ít tin cậy hơn, phải **khử nhận dạng phù hợp trước khi cấp quyền rộng**.
7. Hủy dataset tạm và secret sau bài thử theo quy trình có audit.

Mục tiêu phục hồi cần được quy định bằng **RPO** (mức mất dữ liệu chấp nhận) và **RTO** (thời gian phục hồi chấp nhận). Backup riêng tenant không đồng nghĩa RPO = 0; replication không thay thế backup lịch sử khi có xóa nhầm hoặc lỗi logic.

## 11. Migration và mở rộng nhiều tenant

Trong môi trường multi-tenant, thay đổi schema có thể phải chạy trên nhiều database/schema khác nhau hoặc một bảng shared-table rất lớn.

Các nguyên tắc:

- Dùng **expand–contract** để phiên bản ứng dụng cũ và mới có thể cùng chạy khi rollout.
- Với database-per-tenant, theo dõi version migration riêng từng tenant; không giả định tất cả hoàn tất cùng lúc.
- Với shared-table, kiểm tra index, lock, WAL, replication lag và dữ liệu tenant lớn, tránh quét toàn bảng không kiểm soát.
- Khi thêm cột tenant mới, có lộ trình backfill và thắt chặt constraint; không mặc nhiên coi NULL là tenant “chung”.
- Khi thêm RLS, kiểm thử mọi query, job và role sử dụng bảng; một migration role đặc quyền phải được kiểm soát riêng.
- Khi chuyển tenant từ shared DB sang DB riêng, cần chốt authority, sao chép dữ liệu nhất quán, bắt kịp thay đổi và chuyển routing có fencing/quy tắc một writer.
- Không chạy migration production bằng credential staging hoặc dùng cùng secret chỉ vì cấu hình CI/CD thuận tiện.

### 11.1. Chuyển tenant sang database riêng có thể bị ghi phân kỳ

Ví dụ Tenant A được di chuyển:

~~~text
T0: Tenant A ở shared DB
T1: Copy snapshot sang dedicated DB
T2: Ứng dụng vẫn ghi shared DB
T3: Router chuyển đọc sang dedicated DB quá sớm
T4: Dedicated DB thiếu thay đổi từ T2
~~~

Để chuyển an toàn cần có quy trình đồng bộ thay đổi từ snapshot, xác minh checksum/version, chặn hoặc điều phối writes trong thời điểm cutover, cập nhật router theo một nguồn cấu hình đáng tin và có rollback plan. Không dùng việc “copy xong bảng” làm bằng chứng rằng replica/dedicated DB đã bắt kịp.

Một tenant lớn có thể cần tài nguyên riêng để tránh noisy neighbor, nhưng điều đó không cho phép bỏ qua ranh giới bảo mật hoặc idempotency lúc chuyển.

## 12. Định danh, quyền và thao tác quản trị đặc biệt

Ứng dụng có thể cần tài khoản hỗ trợ để xử lý sự cố của khách hàng. Không vì thế mà cấp `SELECT *` mọi tenant cho mọi nhân viên hoặc làm đường truy cập admin không được kiểm toán.

Một cơ chế hỗ trợ nên có:

1. Xác thực mạnh, phân quyền tối thiểu và yêu cầu lý do truy cập.
2. Scope tenant/case cụ thể, thời hạn ngắn và cơ chế phê duyệt khi cần.
3. Audit ai truy cập gì, lúc nào và cho mục đích gì.
4. Cơ chế ngăn xuất dữ liệu hàng loạt ngoài phạm vi được phép.
5. Tách role quản trị migration/backup khỏi role runtime của ứng dụng.
6. Quy trình **break-glass** cho tình huống khẩn cấp, có giám sát và hậu kiểm.

Trong PostgreSQL, một role có `BYPASSRLS` hoặc quyền superuser có thể đi qua hàng rào RLS. Nó phải là **vai trò vận hành đặc biệt**, không phải credential được nhúng trong ứng dụng Java bình thường.

Cũng cần xử lý quyền đến từ token/token cache: khi người dùng mất membership trong tenant, không được tiếp tục dùng quyền đã cache quá thời hạn/hợp đồng cho phép trong hành động nhạy cảm.

## 13. Quan sát: chứng minh rằng ranh giới thật sự hoạt động

Một hệ thống báo “không có sự cố” không đủ chứng minh không có truy cập chéo tenant. Cần chủ động ghi nhận kết quả kiểm thử, audit và các tín hiệu phát hiện bất thường.

| Chỉ số/kiểm tra | Mục đích |
| --- | --- |
| Số query bị RLS từ chối hoặc trả rỗng do thiếu tenant context | Phát hiện code path không đặt scope đúng |
| Query không có tenant predicate trong nơi yêu cầu | Kiểm tra regression ở repository/native SQL |
| Lỗi FK/UNIQUE liên quan `tenant_id` | Phát hiện ghi sai khóa hoặc idempotency scope |
| Connection pool active/idle, transaction age | Phát hiện session state rò rỉ và transaction dài |
| Bản ghi cross-tenant access attempt trong audit | Cảnh báo truy cập trái phép hoặc lỗi routing |
| Số deployment/service không đúng environment identity | Ngăn nhầm endpoint production |
| Lỗi publish tới topic/bucket ngoài môi trường | Phát hiện cấu hình tích hợp chéo môi trường |
| Restore drill, RPO/RTO, số bản sao dữ liệu thử còn tồn tại | Kiểm soát vòng đời dữ liệu nhạy cảm |
| Noisy-neighbor metrics theo tenant hoặc nhóm workload | Điều phối quota và năng lực hạ tầng |
| Độ trễ xóa dữ liệu qua DB, cache, search, backup | Theo dõi retention và yêu cầu xóa |

Đối với log/tracing, tenant ID có thể hữu ích làm thuộc tính truy vết, nhưng tránh đưa dữ liệu nhạy cảm, email, token hoặc tham số SQL nguyên văn vào log. Với metrics, mỗi tenant ID tạo label có cardinality cao; hãy cân nhắc sampling, tập nhóm hoặc hệ thống analytics phù hợp thay vì thêm hàng triệu label.

## 14. Kịch bản kiểm thử âm tính bắt buộc

Trong môi trường test có hai tenant A và B, tạo dữ liệu cố ý gây nhầm lẫn, ví dụ **cùng `request_key`**, tên file hoặc tên đơn tương tự.

### 14.1. Ma trận kiểm thử

| Tình huống | Kết quả mong đợi |
| --- | --- |
| A đọc `order_id` của B | Không trả dữ liệu B; xử lý 403/404 phù hợp để tránh lộ tồn tại |
| A sửa đơn của B bằng URL giả | Không hàng nào của B được sửa |
| A tạo `order_items` tham chiếu order B | FK ghép hoặc policy chặn |
| Query thiếu `WHERE tenant_id` | RLS runtime vẫn không lộ tenant khác |
| Transaction thiếu `app.tenant_id` | Fail closed: không thấy/không ghi được hàng tenant |
| Connection phục vụ A rồi B | B không thừa hưởng tenant scope A |
| Request song song A/B trên nhiều JVM | Không có cross-tenant data hoặc session leak |
| Cùng request_key ở A/B | Không xung đột giả, không trả kết quả tenant khác |
| Cache key có cùng object ID nhưng khác tenant | Hai key độc lập, không cross-tenant hit |
| Sự kiện Tenant B đi vào consumer Tenant A | Bị chặn hoặc chuyển đúng scope theo contract |
| Job staging có secret prod giả định | Chính sách IAM/network phải từ chối |
| Staging cố gọi email/thanh toán thật | Bị chặn hoặc chuyển tới sandbox |
| Backup prod được restore vào đích test | Chỉ thực hiện bằng quy trình/scope được phê duyệt và bảo vệ dữ liệu |
| Admin thiếu quyền cố đọc toàn bộ tenant | Bị từ chối và có audit |
| Tenant mới được tạo/chuyển DB | Router, migration và data boundary đúng |
| Tenant bị xóa theo chính sách | Không còn dữ liệu trên các tầng trong phạm vi retention đã cam kết |

RLS không tự cung cấp phản hồi HTTP 403. Một SELECT bị lọc có thể trả danh sách rỗng; tầng API cần định nghĩa hành vi hợp lý, tránh dùng thông báo lỗi/latency làm kênh tiết lộ việc tài nguyên của tenant khác có tồn tại.

### 14.2. Bài kiểm tra pool với hai tenant

Một test tích hợp có thể cố ý dùng pool tối đa một physical connection:

~~~text
Request A:
  borrow Connection #1
  BEGIN
  SET LOCAL app.tenant_id = 42
  SELECT -> chỉ thấy A
  COMMIT / close handle

Request B:
  borrow lại Connection #1
  BEGIN
  SET LOCAL app.tenant_id = 77
  SELECT -> chỉ thấy B
  COMMIT / close handle

Request thiếu tenant:
  borrow Connection #1
  BEGIN
  không SET LOCAL
  SELECT -> không thấy A hoặc B
  ROLLBACK / close handle
~~~

Chạy với database thật và runtime role không có `BYPASSRLS`. Đừng chỉ mock `EntityManager`: mock không chứng minh chính sách DB đã được bật, query/callback khác không bypass, hoặc pool reset state đúng.

Một test khác cần thử **kết nối bị ngắt giữa transaction**, rollback, retry và request sau: không được lưu tenant context như một global biến dùng chung hoặc tự động phát lại SQL của tenant A trong request B.

## 15. Những sai lầm thường gặp

**“Staging chỉ khác database name nên đã tách production.”** Nếu dùng chung credential đặc quyền và network, một cấu hình nhầm vẫn có thể sửa production.

**“Dùng dữ liệu production trên laptop tiện kiểm thử hơn.”** Dữ liệu thật phải được bảo vệ theo quyền, mục đích, retention và quy trình khử nhận dạng; bản sao ngoài kiểm soát là rủi ro nghiêm trọng.

**“Mỗi hàng có `tenant_id` là an toàn.”** Query, JOIN, FK, cache và job có thể quên tenant scope. Cần nhiều lớp phòng thủ.

**“Composite index trên `tenant_id` tự chặn truy cập chéo.”** Index chỉ phục vụ truy vấn; không xác thực quyền.

**“Bật RLS nghĩa là mọi role đều bị lọc.”** Superuser/`BYPASSRLS`, quyền owner, view/function và bảng chưa có policy cần được kiểm tra.

**“RLS dùng session variable tự bảo vệ trước một application DB role bị chiếm quyền.”** Nếu role có thể tự đặt tenant khác, cần các lớp xác thực/role/hạ tầng mạnh hơn.

**“Đặt `SET app.tenant_id` một lần cho connection pool là đủ.”** Session state có thể rò sang request khác; dùng transaction-local scope và test reset.

**“Truy vấn JOIN chỉ cần lọc tenant ở bảng cha.”** JOIN thiếu tenant trong khóa có thể ghép sai hàng và tạo rủi ro lộ dữ liệu.

**“Mỗi tenant khác nhau chỉ cần tiền tố Redis key.”** Key đúng không thay thế ACL hoặc quyền truy cập cache; còn phải xét invalidation và TTL.

**“Backup database shared-table tự động hỗ trợ khôi phục riêng một tenant.”** Khôi phục theo tenant đòi xuất đúng tập hàng và quan hệ, cùng các hệ phụ trợ.

**“Xóa hàng trong DB tức là xóa hết dữ liệu tenant.”** Dữ liệu vẫn có thể tồn tại ở object storage, search, log, event, replica và backup theo retention.

**“Test bằng role DBA đã chứng minh RLS hoạt động.”** DBA có thể bypass policy; cần test role production.

**“TenantContext là class Java nên client không thể giả.”** Giá trị vẫn có thể đến từ input không đáng tin; phải xác thực quyền trước khi tạo context.

## 16. Bài tập vận dụng

**Bài 1 — phân tích hai trục.** Một đội dùng một PostgreSQL cluster cho dev/staging/prod với ba database khác tên nhưng cùng tài khoản superuser. Production là SaaS shared-table. Hãy lập danh sách cách một bug deploy và một bug thiếu tenant filter có thể gây rò dữ liệu, rồi thiết kế các lớp chặn độc lập.

**Bài 2 — chọn mô hình tenant.** So sánh database-per-tenant, schema-per-tenant và shared-table cho sản phẩm có 500 tenant nhỏ và 3 tenant rất lớn, mỗi tenant có retention khác nhau. Chọn mô hình hoặc mô hình lai; giải thích chi phí migration, backup, isolation và noisy neighbor.

**Bài 3 — sửa schema.** Một bảng `order_items(order_id, line_no, tenant_id)` chỉ có FK trên `order_id`. Hãy thiết kế khóa ghép và constraint sao cho item của Tenant B không thể tham chiếu order Tenant A. Nêu truy vấn JOIN đúng.

**Bài 4 — RLS.** Trên PostgreSQL thử nghiệm, bật policy theo `app.tenant_id`, dùng runtime role không có `BYPASSRLS`. Chạy ba transaction: tenant A, tenant B và không đặt tenant scope. Kiểm tra SELECT/INSERT/UPDATE đều chỉ tác động tenant được phép.

**Bài 5 — connection pool.** Giả sử pool tối đa một connection, request A chạy xong rồi B mượn lại. Phân tích nguy cơ khi code dùng `SET` cấp session thay vì transaction-local `set_config(..., true)`. Thiết kế test xác minh sau rollback/commit không còn scope cũ.

**Bài 6 — rò qua cache và queue.** Một sự kiện `OrderCreated` thiếu tenant ID làm consumer ghi vào search index theo `orderId` duy nhất; Redis cache cũng dùng `order:{id}`. Hãy sửa schema event, key, quyền topic và quy trình kiểm tra ở consumer.

**Bài 7 — production data cho staging.** Nhóm QA cần dữ liệu thực tế để benchmark. Hãy đề xuất quy trình dùng dữ liệu tổng hợp hoặc bản đã khử nhận dạng, bảo vệ file dump tạm, ngăn gửi email/SMS thật, giới hạn quyền và hủy dataset sau thử nghiệm.

**Bài 8 — backup riêng tenant.** Hệ thống shared-table muốn khôi phục một tenant bị xóa nhầm mà không rollback các tenant còn lại. Liệt kê bảng và dịch vụ phụ thuộc, yêu cầu nhất quán thời điểm, cách kiểm tra FK, dữ liệu phụ và idempotency khi nhập lại.

**Bài 9 — tìm đường bypass.** Một DBA kiểm tra RLS và thấy mọi hàng dù đã tạo policy. Giải thích vai trò owner, superuser, `BYPASSRLS`, `FORCE ROW LEVEL SECURITY` và cách viết integration test bằng runtime role để chứng minh ranh giới thật.

## Ghi nhớ

**Tách môi trường** ngăn dev/test/staging truy cập hoặc tác động production ngoài quy trình được ủy quyền; nó đòi hỏi ranh giới từ IAM, network, credentials, data, backup đến integration. **Tách tenant** ngăn một đơn vị thuê đọc/ghi dữ liệu của đơn vị khác; nó cần xác thực và phân quyền đúng ở ứng dụng, schema/constraint phù hợp, tenant context và cơ chế bảo vệ ở DB, đồng thời áp dụng cả cho cache, event, search, object storage và log.

Trong ứng dụng Java, hãy truyền tenant context **đã được xác minh**, đặt phạm vi theo transaction trên connection thật, đóng tài nguyên đúng cách, thử bằng role runtime và chủ động kiểm tra đường đọc/ghi chéo tenant. Chọn mô hình tenancy theo yêu cầu rủi ro/chi phí, nhưng đừng để sự tiện lợi của shared infrastructure xóa bỏ ranh giới dữ liệu mà người dùng và tổ chức đã tin cậy.
