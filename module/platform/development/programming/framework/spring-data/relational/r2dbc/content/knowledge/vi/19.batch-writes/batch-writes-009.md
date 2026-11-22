# Upsert bằng SQL đặc thù và kiểm tra tính lũy đẳng

## 1. Upsert là gì?

**Upsert** kết hợp thao tác insert và update: nếu một hàng chưa tồn tại theo khóa xung đột đã xác định, database tạo hàng mới; nếu hàng đã tồn tại, database thực hiện hành động cập nhật được chỉ định.

Ví dụ một hệ thống đồng bộ tồn kho nhận dữ liệu theo cặp `tenant_id` và `sku`. Mỗi lần nhận snapshot, ứng dụng muốn tạo hàng tồn kho nếu chưa có hoặc thay thế số lượng hiện tại nếu đã có:

~~~sql
INSERT INTO inventory (tenant_id, sku, quantity)
VALUES (:tenantId, :sku, :quantity)
ON CONFLICT (tenant_id, sku)
DO UPDATE SET quantity = EXCLUDED.quantity;
~~~

Câu lệnh trên là cú pháp PostgreSQL. `ON CONFLICT` xác định cách xử lý khi insert vi phạm unique constraint hoặc primary key tương ứng. `EXCLUDED` đại diện cho hàng được đề xuất insert.

Upsert hữu ích cho đồng bộ dữ liệu, ghi nhận trạng thái mới nhất, lưu cấu hình theo khóa nghiệp vụ và xử lý thông điệp có thể được gửi lại. Nhưng upsert không tự động làm mọi nghiệp vụ trở nên idempotent. Tính lũy đẳng phụ thuộc vào ý nghĩa của dữ liệu được ghi, khóa nhận diện thao tác và những side effect đi kèm.

Trong Spring Data R2DBC, upsert theo cú pháp riêng của database thường được thực hiện bằng SQL tường minh qua **DatabaseClient** hoặc repository method dùng `@Query`. Cần chọn đúng cú pháp theo database và đặt unique constraint ở database để xử lý cạnh tranh đồng thời.

## 2. Phân biệt upsert với tính lũy đẳng

Hai khái niệm liên quan nhưng không đồng nghĩa.

**Upsert** là chiến lược ghi dữ liệu: insert khi chưa có hàng theo khóa xung đột, update khi đã có.

**Idempotency (tính lũy đẳng)** là thuộc tính của một thao tác: thực hiện cùng một yêu cầu nhiều lần tạo ra cùng trạng thái có ý nghĩa như thực hiện một lần.

Có thể mô tả bằng biểu thức:

```text
f(f(state, request), request) = f(state, request)
```

Nếu một request được gửi lại do timeout, retry hoặc message broker giao lại, hệ thống không tạo thêm tác động ngoài dự kiến.

Ví dụ:

| Thao tác | Gửi cùng request hai lần | Lũy đẳng? |
|---|---|---|
| Đặt quantity thành 12 | Giá trị cuối vẫn là 12 | Có, nếu không có side effect khác |
| Đặt status thành ACTIVE | Trạng thái cuối vẫn ACTIVE | Có, nếu các trường phụ cũng ổn định |
| Tăng quantity thêm 2 | Giá trị tăng thêm 4 | Không |
| Cộng thêm 100 vào balance | Balance tăng hai lần | Không |
| Ghi nhận event có event_id duy nhất và bỏ qua event đã xử lý | Event chỉ được áp dụng một lần | Có, nếu việc ghi event và cập nhật nghiệp vụ cùng atomic |
| Gửi email sau mỗi lần upsert | Có thể gửi hai email | Không, dù hàng database cuối cùng giống nhau |

Một câu lệnh upsert có thể idempotent hoặc không tùy phần `DO UPDATE`. Câu lệnh đặt giá trị tuyệt đối thường dễ lũy đẳng hơn câu lệnh cộng dồn. Nếu thao tác có side effect ngoài database, cần thiết kế cơ chế chống lặp riêng.

## 3. Unique constraint là nền tảng của upsert

Database cần biết thế nào là cùng một bản ghi. Điều này phải được biểu diễn bằng primary key hoặc unique constraint/index.

Ví dụ:

~~~sql
CREATE TABLE inventory (
    tenant_id UUID NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, sku)
);
~~~

Khóa chính tổng hợp `(tenant_id, sku)` xác định duy nhất một hàng tồn kho cho mỗi SKU trong từng tenant.

Nếu không có unique constraint phù hợp, hai request đồng thời có thể cùng kiểm tra thấy chưa tồn tại rồi cùng insert hai hàng. Một truy vấn `SELECT` trước khi `INSERT` không thay thế được constraint vì giữa hai câu lệnh có thể xảy ra race condition.

Quy tắc thực hành:

- Chọn business key phản ánh đúng danh tính bản ghi.
- Đặt primary key hoặc unique constraint/index ở database.
- Dùng đúng các cột của constraint trong conflict target.
- Với khóa tenant-scoped, thường phải đưa tenant ID vào khóa duy nhất.
- Không dựa vào việc service đã kiểm tra tồn tại để bảo đảm duy nhất.

Nếu unique key chỉ có ý nghĩa trong một tenant, unique constraint toàn cục trên SKU có thể làm tenant này xung đột với tenant khác. Thiết kế constraint phải khớp phạm vi nghiệp vụ.

## 4. Upsert trong PostgreSQL với ON CONFLICT

PostgreSQL hỗ trợ `INSERT ... ON CONFLICT` với hai hành động thường dùng: `DO NOTHING` và `DO UPDATE`.

### 4.1. Bỏ qua hàng trùng với DO NOTHING

~~~sql
INSERT INTO external_customers (external_id, name)
VALUES (:externalId, :name)
ON CONFLICT (external_id) DO NOTHING;
~~~

Nếu external_id chưa tồn tại, hàng được insert. Nếu đã tồn tại, database bỏ qua thao tác insert. Không có hàng nào được cập nhật trong trường hợp conflict.

Cách này hữu ích khi muốn ghi nhận một khóa duy nhất một lần, chẳng hạn event ID hoặc idempotency key. Nhưng cần nhớ rằng `DO NOTHING` không tự trả lại hàng cũ. Nếu ứng dụng cần kết quả hiện có, phải truy vấn riêng sau khi biết insert không tạo hàng mới, hoặc dùng một quy trình phù hợp với yêu cầu concurrency.

### 4.2. Cập nhật khi xảy ra conflict

~~~sql
INSERT INTO inventory (tenant_id, sku, quantity, updated_at)
VALUES (:tenantId, :sku, :quantity, :updatedAt)
ON CONFLICT (tenant_id, sku)
DO UPDATE
SET quantity = EXCLUDED.quantity,
    updated_at = EXCLUDED.updated_at
RETURNING tenant_id, sku, quantity, updated_at;
~~~

- `(tenant_id, sku)` là conflict target.
- `EXCLUDED.quantity` là quantity trong hàng đang được đề xuất insert.
- `inventory.quantity` là quantity đang lưu trong hàng hiện tại.
- `RETURNING` yêu cầu PostgreSQL trả lại hàng sau insert hoặc update.

Vì giá trị được gán từ cùng một request, việc gửi lại cùng payload sẽ đặt quantity về cùng một giá trị. Nếu `updatedAt` cũng được lấy từ request và giữ nguyên khi retry, kết quả lưu trữ có thể ổn định.

### 4.3. Giữ nguyên updated_at nếu dữ liệu không đổi

Nếu dùng `updated_at = now()`, mỗi lần retry đều làm timestamp thay đổi dù quantity không đổi. Trạng thái nghiệp vụ chính có thể giống nhau nhưng hàng vẫn thay đổi.

Có thể chỉ cập nhật timestamp khi quantity thực sự khác:

~~~sql
INSERT INTO inventory (tenant_id, sku, quantity, updated_at)
VALUES (:tenantId, :sku, :quantity, :updatedAt)
ON CONFLICT (tenant_id, sku)
DO UPDATE SET
    updated_at = CASE
        WHEN inventory.quantity IS DISTINCT FROM EXCLUDED.quantity
        THEN EXCLUDED.updated_at
        ELSE inventory.updated_at
    END,
    quantity = EXCLUDED.quantity
RETURNING tenant_id, sku, quantity, updated_at;
~~~

`IS DISTINCT FROM` là phép so sánh null-safe của PostgreSQL. Ví dụ này minh họa cách tránh thay đổi metadata khi payload không làm thay đổi quantity. Cần điều chỉnh điều kiện theo tất cả trường được xem là trạng thái có ý nghĩa trong domain.

### 4.4. Chỉ cập nhật một số cột được phép

Không nên tự động cập nhật mọi cột từ hàng mới nếu một số cột là bất biến hoặc do server quản lý.

Ví dụ:

~~~sql
ON CONFLICT (tenant_id, sku)
DO UPDATE SET
    quantity = EXCLUDED.quantity,
    updated_at = EXCLUDED.updated_at;
~~~

Câu lệnh giữ nguyên các cột khác như `created_at`, `created_by` hoặc trạng thái kiểm duyệt. Điều này giúp tránh request đồng bộ vô tình ghi đè dữ liệu thuộc quyền quản lý của một quy trình khác.

### 4.5. DO UPDATE có điều kiện

PostgreSQL cho phép thêm điều kiện `WHERE` sau phần `DO UPDATE`:

~~~sql
INSERT INTO inventory (tenant_id, sku, quantity, version)
VALUES (:tenantId, :sku, :quantity, :incomingVersion)
ON CONFLICT (tenant_id, sku)
DO UPDATE SET
    quantity = EXCLUDED.quantity,
    version = EXCLUDED.version
WHERE inventory.version = :expectedVersion
RETURNING tenant_id, sku, quantity, version;
~~~

Điều kiện này chỉ cập nhật nếu version hiện tại khớp với version mà ứng dụng kỳ vọng. Nếu điều kiện không đúng, hàng không được update và `RETURNING` không phát hàng nào.

Trong code, trường hợp không có hàng trả về cần được phân biệt với insert/update thành công. Nó có thể biểu thị xung đột version hoặc điều kiện update không còn thỏa mãn. Đây là cách phối hợp upsert với optimistic concurrency; cần định nghĩa rõ version đầu vào và version mong đợi trong hợp đồng API.

### 4.6. Conflict target phải khớp constraint

PostgreSQL có thể chọn conflict target theo danh sách cột hoặc constraint:

~~~sql
ON CONFLICT ON CONSTRAINT uq_inventory_tenant_sku
DO UPDATE SET quantity = EXCLUDED.quantity;
~~~

Tên constraint phải tồn tại trong schema. Nếu conflict target không khớp unique index/constraint phù hợp, câu lệnh sẽ lỗi. Với partial unique index, điều kiện predicate và cách suy luận index cũng cần khớp quy tắc PostgreSQL.

## 5. Thực hiện PostgreSQL upsert bằng DatabaseClient

DatabaseClient phù hợp vì câu lệnh upsert có cú pháp SQL đặc thù và ứng dụng muốn kiểm soát phần `RETURNING`.

Giả sử record kết quả:

~~~java
import java.time.OffsetDateTime;
import java.util.UUID;

public record Inventory(
        UUID tenantId,
        String sku,
        Integer quantity,
        OffsetDateTime updatedAt
) {}
~~~

Phương thức upsert:

~~~java
public Mono<Inventory> upsertInventory(
        UUID tenantId,
        String sku,
        int quantity,
        OffsetDateTime updatedAt) {

    return databaseClient.sql("""
            INSERT INTO inventory (
                tenant_id, sku, quantity, updated_at
            )
            VALUES (
                :tenantId, :sku, :quantity, :updatedAt
            )
            ON CONFLICT (tenant_id, sku)
            DO UPDATE SET
                quantity = EXCLUDED.quantity,
                updated_at = EXCLUDED.updated_at
            RETURNING tenant_id, sku, quantity, updated_at
            """)
        .bind("tenantId", tenantId)
        .bind("sku", sku)
        .bind("quantity", quantity)
        .bind("updatedAt", updatedAt)
        .map((row, metadata) -> new Inventory(
                row.get("tenant_id", UUID.class),
                row.get("sku", String.class),
                row.get("quantity", Integer.class),
                row.get("updated_at", OffsetDateTime.class)
        ))
        .one();
}
~~~

Các điểm cần chú ý:

- Tên bảng và cột được viết theo schema PostgreSQL.
- Các giá trị đầu vào đều được bind, không nối chuỗi vào SQL.
- Row callback chịu trách nhiệm chuyển cột thành kiểu Java.
- `one()` trả `Mono<Inventory>` vì câu lệnh kỳ vọng một hàng từ RETURNING.
- Với PostgreSQL R2DBC driver, kiểu Java đọc từ cột thời gian cần phù hợp với SQL type và driver; ví dụ dùng `OffsetDateTime` cho `TIMESTAMPTZ`.

Nếu không dùng RETURNING, có thể gọi `fetch().rowsUpdated()` để nhận số hàng bị tác động. Khi dùng RETURNING, hãy map các hàng trả về bằng `map(...).one()` hoặc API nhiều hàng phù hợp.

Không nên gọi `block()` hoặc tự `subscribe()` bên trong service. Hãy trả `Mono<Inventory>` cho caller để reactive pipeline, lỗi và transaction được quản lý xuyên suốt.

## 6. Upsert trong các hệ quản trị khác

Upsert không có một cú pháp SQL duy nhất được hỗ trợ giống nhau ở mọi database. R2DBC chỉ cung cấp API giao tiếp reactive; cú pháp upsert vẫn do database quyết định.

| Database | Cú pháp thường dùng | Điểm cần chú ý |
|---|---|---|
| PostgreSQL | `INSERT ... ON CONFLICT ... DO UPDATE/NOTHING` | Có conflict target và RETURNING |
| SQLite | `INSERT ... ON CONFLICT ... DO UPDATE/NOTHING` | UPSERT được hỗ trợ ở các phiên bản phù hợp; kiểm tra phiên bản SQLite |
| MySQL | `INSERT ... ON DUPLICATE KEY UPDATE` | Conflict có thể xuất phát từ primary key hoặc unique index; không có conflict target giống PostgreSQL |
| MariaDB | `INSERT ... ON DUPLICATE KEY UPDATE` | Cần kiểm tra phiên bản và khác biệt cú pháp/giá trị được tham chiếu |
| SQL Server | `MERGE` hoặc chiến lược UPDATE/INSERT có kiểm soát | Phải xem xét concurrency, locking và hành vi theo phiên bản |
| Oracle | `MERGE` | Cú pháp và semantics theo Oracle; cần kiểm thử với driver tương ứng |

### 6.1. MySQL

MySQL có cú pháp `ON DUPLICATE KEY UPDATE`:

~~~sql
INSERT INTO inventory (tenant_id, sku, quantity)
VALUES (:tenantId, :sku, :quantity) AS incoming
ON DUPLICATE KEY UPDATE
    quantity = incoming.quantity;
~~~

Ví dụ dùng row alias sau VALUES theo cú pháp MySQL phiên bản hỗ trợ. Ở một số phiên bản hoặc MariaDB, cách tham chiếu giá trị mới có thể khác. Hãy kiểm tra tài liệu đúng phiên bản database triển khai.

Một điểm khác với PostgreSQL là MySQL có thể thực hiện nhánh update khi xảy ra conflict với bất kỳ primary key hoặc unique index phù hợp nào. Nếu bảng có nhiều unique key, cần hiểu rõ conflict nào có thể kích hoạt update. Không giả định hành vi target cụ thể như `ON CONFLICT (tenant_id, sku)` của PostgreSQL.

### 6.2. SQLite

SQLite hỗ trợ UPSERT với `ON CONFLICT`:

~~~sql
INSERT INTO inventory (tenant_id, sku, quantity)
VALUES (:tenantId, :sku, :quantity)
ON CONFLICT (tenant_id, sku)
DO UPDATE SET quantity = excluded.quantity;
~~~

SQLite dùng cách viết `excluded` cho hàng được đề xuất insert. Kiểm tra phiên bản SQLite và R2DBC driver đang dùng trước khi dựa vào cú pháp này.

### 6.3. SQL Server và Oracle

SQL Server và Oracle cung cấp `MERGE` để kết hợp insert/update theo điều kiện so khớp. Tuy nhiên, cú pháp và đặc tính concurrency không giống nhau. Với SQL Server, cần xem xét kỹ locking, unique constraint và hướng dẫn theo phiên bản; một câu MERGE đơn giản không tự bảo đảm mọi workload đồng thời đều an toàn.

Một phương án khác là thực hiện UPDATE trước, nếu không có hàng thì INSERT, nhưng chuỗi thao tác phải được bảo vệ bằng transaction và unique constraint; vẫn cần xử lý trường hợp hai transaction đồng thời cùng insert. Không nên dùng SELECT-then-INSERT đơn giản mà không có cơ chế xử lý race.

### 6.4. Vì sao không thể dùng một câu SQL chung?

Mỗi database có khác biệt về:

- Tên và vị trí conflict clause.
- Cách chỉ định unique constraint.
- Cách tham chiếu hàng mới được đề xuất insert.
- Khả năng trả hàng bằng RETURNING hoặc OUTPUT.
- Hành vi trigger, sequence và affected-row count.
- Semantics của locking và transaction.
- Cách xử lý nhiều unique index cùng xung đột.

Nếu ứng dụng hỗ trợ nhiều database, có thể tách implementation theo dialect/adapter thay vì cố ép một chuỗi SQL duy nhất chạy trên tất cả hệ quản trị.

## 7. Vì sao ReactiveCrudRepository.save() không phải upsert theo business key?

Phương thức `save(entity)` của Spring Data xác định entity mới hay đã tồn tại theo cơ chế state detection, thường dựa trên ID và có thể dựa vào version hoặc `Persistable.isNew()`.

Điều này khác với upsert theo một unique key nghiệp vụ như email, external_id hoặc cặp tenant_id + sku.

Ví dụ entity mới có ID null nhưng external_id đã tồn tại trong database. `save(entity)` có thể chọn INSERT vì entity được nhận diện là mới. Database sau đó trả lỗi unique constraint. Spring Data không tự động diễn giải lỗi đó thành UPDATE theo external_id.

Ngược lại, entity có ID đã được gán có thể được nhận diện là entity cũ và dẫn đến thao tác update. Điều đó cũng không tương đương với câu lệnh upsert nguyên tử theo unique business key.

Phân biệt:

| Cơ chế | Cách quyết định |
|---|---|
| `repository.save(entity)` | Spring Data nhận diện trạng thái entity theo ID/version/Persistable |
| `R2dbcEntityTemplate.insert(...)` | Yêu cầu insert tường minh |
| `DatabaseClient` với upsert SQL | Database xử lý conflict theo unique constraint và câu lệnh |
| `SELECT` rồi INSERT/UPDATE | Ứng dụng tự điều phối nhiều câu lệnh; cần xử lý race condition |

Nếu nghiệp vụ yêu cầu upsert theo external_id, hãy khai báo unique constraint cho external_id và dùng câu lệnh upsert tương ứng với database. Không dựa vào tên phương thức `save` để suy ra semantics đó.

## 8. Tính lũy đẳng của câu lệnh upsert

### 8.1. Gán giá trị tuyệt đối thường có thể lũy đẳng

Ví dụ:

~~~sql
INSERT INTO user_settings (user_id, language)
VALUES (:userId, :language)
ON CONFLICT (user_id)
DO UPDATE SET language = EXCLUDED.language;
~~~

Gửi cùng userId và language nhiều lần tạo cùng trạng thái language. Đây là phép gán, không phải phép cộng dồn.

Để toàn bộ hàng thực sự ổn định, hãy xem cả các cột khác như updated_at, retry_count, audit field và trigger. Nếu mỗi lần chạy lại đều tăng một counter hoặc tạo audit record mới, thao tác tổng thể vẫn có thể không idempotent.

### 8.2. Phép cộng dồn không lũy đẳng

~~~sql
INSERT INTO inventory (sku, quantity)
VALUES (:sku, :delta)
ON CONFLICT (sku)
DO UPDATE SET
    quantity = inventory.quantity + EXCLUDED.quantity;
~~~

Nếu request có delta = 5 được gửi hai lần, quantity tăng tổng cộng 10. Upsert giải quyết conflict nhưng không ngăn cùng một event được áp dụng hai lần.

Không dùng phép cộng dồn trực tiếp nếu message có thể được giao lại mà không có event ID hoặc cơ chế deduplication.

### 8.3. Timestamp và audit field có thể phá tính lũy đẳng

Ví dụ:

~~~sql
DO UPDATE SET
    status = EXCLUDED.status,
    updated_at = CURRENT_TIMESTAMP;
~~~

Cùng một request được gửi lại sẽ làm updated_at thay đổi ở mỗi lần. Nếu hợp đồng chỉ quan tâm status thì có thể xem state nghiệp vụ là tương đương; nếu toàn bộ record hoặc event audit là kết quả quan sát được, thao tác không hoàn toàn lũy đẳng.

Cần xác định rõ phạm vi state nào phải ổn định khi retry. Có thể dùng timestamp do request tạo ra và giữ nguyên qua retry, hoặc chỉ cập nhật timestamp khi giá trị nghiệp vụ thực sự thay đổi.

### 8.4. Side effect ngoài database không được bảo vệ bởi upsert

Giả sử sau khi upsert trạng thái đơn hàng, service gửi email hoặc gọi một dịch vụ thanh toán. Nếu request bị retry, email hoặc lời gọi bên ngoài có thể được thực hiện lần nữa dù hàng database đã có cùng trạng thái.

Upsert chỉ kiểm soát thao tác database trong câu SQL. Nó không tự bảo đảm exactly-once cho email, HTTP call, message broker hoặc hệ thống khác.

## 9. Idempotency key cho request có thể được gửi lại

Một cách phổ biến để xử lý retry ở API là yêu cầu client gửi **idempotency key**. Key nhận diện một yêu cầu logic, không phải một lần truyền HTTP.

Ví dụ schema PostgreSQL:

~~~sql
CREATE TABLE idempotency_requests (
    tenant_id UUID NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    response_status INTEGER,
    response_body JSONB,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, idempotency_key)
);
~~~

Khóa chính bảo đảm mỗi tenant chỉ có một bản ghi cho một idempotency key. request_hash là fingerprint của payload đã chuẩn hóa; nó giúp phát hiện client tái sử dụng cùng key cho một request khác.

Một quy trình xử lý điển hình:

1. Xác thực người gọi và xác định tenant từ nguồn tin cậy.
2. Chuẩn hóa request và tính request hash.
3. Thử insert idempotency key bằng `ON CONFLICT DO NOTHING`.
4. Nếu insert thành công, request hiện tại là request đầu tiên được nhận diện; thực hiện nghiệp vụ.
5. Ghi kết quả nghiệp vụ và response cần lưu vào cùng transaction.
6. Đánh dấu idempotency record hoàn tất trước khi commit.
7. Nếu key đã tồn tại, đọc record hiện có.
8. Nếu request hash khác, từ chối vì key đã được dùng cho payload khác.
9. Nếu hash giống và request đã hoàn tất, trả lại kết quả đã lưu thay vì thực hiện nghiệp vụ lần nữa.

SQL claim key:

~~~sql
INSERT INTO idempotency_requests (
    tenant_id, idempotency_key, request_hash
)
VALUES (:tenantId, :key, :requestHash)
ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
RETURNING tenant_id, idempotency_key;
~~~

Nếu `RETURNING` phát một hàng, thao tác đã tạo key mới. Nếu không có hàng, key đã tồn tại hoặc request cạnh tranh khác đã thắng. Ứng dụng cần đọc record hiện tại và áp dụng chính sách hash/trạng thái.

### 9.1. Cùng key nhưng payload khác phải được xử lý rõ ràng

Không nên âm thầm trả kết quả cũ cho một payload khác. Ví dụ client gửi key `abc` với amount 100, rồi tái sử dụng key đó với amount 500. Nếu chỉ kiểm tra key, hệ thống có thể trả kết quả của request trước và che giấu lỗi phía client.

So sánh request_hash giúp phát hiện trường hợp này. Cần định nghĩa cách chuẩn hóa payload trước khi hash để thứ tự field, format ngày giờ hoặc cách biểu diễn số không làm cùng request logic bị coi là khác nhau.

### 9.2. Key cần có phạm vi và thời hạn

Idempotency key nên được ràng buộc với phạm vi phù hợp như tenant, user hoặc loại thao tác. Không dùng key toàn cục nếu hai khách hàng độc lập có thể tạo cùng chuỗi.

Cũng cần định nghĩa thời gian lưu record. Xóa key quá sớm có thể khiến retry muộn thực hiện lại thao tác. Giữ vĩnh viễn có thể làm bảng tăng không giới hạn. Retention phải phù hợp với thời gian retry của client, broker và nghiệp vụ.

## 10. Kết hợp idempotency record với transaction reactive

Để ngăn hai request đồng thời cùng thực hiện một nghiệp vụ, việc claim idempotency key và ghi dữ liệu nghiệp vụ cần được thiết kế atomic trong cùng database transaction.

Với PostgreSQL, unique constraint trên (tenant_id, idempotency_key) làm cho hai transaction cạnh tranh cùng key phải được database điều phối. Một transaction có thể insert key; transaction còn lại sẽ chờ kết quả conflict theo semantics transaction của PostgreSQL.

Cấu trúc service minh họa:

~~~java
@Transactional
public Mono<PaymentResult> createPayment(
        UUID tenantId,
        String idempotencyKey,
        String requestHash,
        CreatePaymentCommand command) {

    return claimIdempotencyKey(tenantId, idempotencyKey, requestHash)
            .flatMap(claimed -> {
                if (!claimed) {
                    return loadPreviousResult(
                            tenantId, idempotencyKey, requestHash
                    );
                }

                return createPaymentRecord(command)
                        .flatMap(result ->
                                storeIdempotencyResult(
                                        tenantId,
                                        idempotencyKey,
                                        result
                                ).thenReturn(result)
                        );
            });
}
~~~

Các hàm `claimIdempotencyKey`, `loadPreviousResult`, `createPaymentRecord` và `storeIdempotencyResult` là hàm minh họa cần được triển khai bằng repository/template/DatabaseClient. Điều quan trọng là toàn bộ publisher được trả về trong cùng transaction và mọi thao tác dùng cùng ConnectionFactory/transaction manager.

Nếu thao tác nghiệp vụ thất bại trước commit, transaction rollback cả bản ghi idempotency mới tạo và dữ liệu nghiệp vụ. Request retry sau đó có thể claim key và thử lại theo chính sách đã định.

Với xử lý dài hoặc cần trả trạng thái IN_PROGRESS qua nhiều transaction, thiết kế sẽ khác: cần trạng thái xử lý, lease/timeout, recovery và cách xử lý worker chết giữa chừng. Không nên giữ transaction database mở trong suốt một công việc dài hoặc một lời gọi mạng bên ngoài.

## 11. Dùng event ID để chống xử lý message lặp

Với message broker có delivery at-least-once, cùng một event có thể được gửi lại. Có thể lưu event ID đã xử lý với unique constraint:

~~~sql
CREATE TABLE processed_events (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL
);
~~~

Trong transaction:

1. Insert event_id vào processed_events với `ON CONFLICT DO NOTHING`.
2. Nếu không insert được hàng mới, event đã được xử lý; bỏ qua nghiệp vụ.
3. Nếu insert thành công, thực hiện thay đổi dữ liệu nghiệp vụ.
4. Commit cả event marker và thay đổi nghiệp vụ cùng nhau.

Nếu bước nghiệp vụ thất bại, transaction phải rollback để event marker không bị lưu riêng. Khi broker giao lại, event có thể được thử lại.

Với một nghiệp vụ cộng dồn, chẳng hạn tăng tồn kho hoặc cộng điểm, event ID duy nhất là chìa khóa để không áp dụng delta hai lần. Nếu chỉ upsert theo SKU và cộng delta, duplicate delivery vẫn làm tăng giá trị nhiều lần.

Khi message handler cần gửi tiếp event ra broker, có thể ghi outbox record trong cùng transaction với thay đổi nghiệp vụ. Một publisher riêng đọc outbox và gửi message; consumer phía nhận vẫn cần deduplicate theo event ID vì việc gửi ra broker cũng có thể được retry.

## 12. Outbox và side effect ngoài database

Không thể đặt một transaction R2DBC local bao trùm đồng thời database và một dịch vụ HTTP/email bên ngoài. Nếu database commit nhưng HTTP call thất bại, hoặc HTTP call thành công rồi database rollback, hai hệ thống có thể không đồng bộ.

Mẫu transactional outbox giải quyết phần ghi nhận ý định gửi message:

~~~sql
CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ
);
~~~

Trong cùng transaction:

- Upsert hoặc cập nhật dữ liệu nghiệp vụ.
- Insert outbox event với event_id duy nhất.
- Commit.

Một worker/publisher đọc các outbox event chưa gửi, gửi message rồi cập nhật published_at. Nếu publisher gửi thành công nhưng chết trước khi đánh dấu published_at, event có thể được gửi lại. Consumer cần idempotency/deduplication riêng.

Outbox không biến broker thành exactly-once. Nó bảo đảm thay đổi nghiệp vụ và ý định phát event được lưu atomic trong cùng database; duplicate delivery vẫn cần được xử lý.

## 13. Xử lý cạnh tranh và race condition

### 13.1. Vì sao SELECT rồi INSERT không an toàn?

Một cách triển khai dễ mắc lỗi:

~~~text
Request A: SELECT -> không có hàng
Request B: SELECT -> không có hàng
Request A: INSERT -> thành công
Request B: INSERT -> duplicate key error
~~~

Nếu không có unique constraint, cả hai INSERT có thể thành công và tạo hai hàng logic trùng nhau. Nếu có unique constraint, một request thất bại nhưng ứng dụng vẫn cần xử lý conflict đúng cách.

Upsert nguyên tử dựa trên unique constraint cho phép database xử lý cạnh tranh ngay trong câu lệnh. Đây là lý do nên dùng conflict clause của database thay vì tự tách thành SELECT rồi INSERT/UPDATE.

### 13.2. Unique constraint vẫn là lớp bảo vệ bắt buộc

Không nên chỉ dùng distributed lock hoặc kiểm tra ở application layer rồi bỏ unique constraint. Nhiều instance ứng dụng, retry, timeout và process khác có thể cùng thao tác dữ liệu.

Constraint là nguồn bảo đảm cuối cùng ở database. Lock ứng dụng có thể giảm contention nhưng không thay thế constraint.

### 13.3. Upsert không giải quyết mọi xung đột nghiệp vụ

Giả sử hai request cùng cập nhật một sản phẩm với hai giá trị khác nhau. Database sẽ tuần tự hóa thao tác conflict theo cơ chế của nó, nhưng request đến sau có thể ghi đè request đến trước.

Nếu cần phát hiện dữ liệu cũ, dùng version, expected state hoặc điều kiện update. Ví dụ chỉ update khi version hiện tại khớp version mà client đã đọc. Khi không khớp, trả conflict để caller tải lại và quyết định.

### 13.4. Thứ tự sự kiện có thể quan trọng

Nếu hai event có timestamp hoặc sequence khác nhau đến không theo thứ tự, upsert đơn giản theo external_id có thể để event cũ ghi đè event mới. Có thể thêm điều kiện chỉ nhận version/timestamp mới hơn:

~~~sql
INSERT INTO external_status (external_id, source_version, status)
VALUES (:externalId, :sourceVersion, :status)
ON CONFLICT (external_id)
DO UPDATE SET
    source_version = EXCLUDED.source_version,
    status = EXCLUDED.status
WHERE external_status.source_version < EXCLUDED.source_version;
~~~

Câu lệnh này bỏ qua update nếu version đang lưu lớn hơn hoặc bằng version đầu vào. Nếu không có hàng được RETURNING, ứng dụng cần phân biệt event cũ bị bỏ qua với thao tác thành công.

## 14. Retry và lỗi sau khi gửi SQL

Reactive pipeline có thể retry khi gặp lỗi tạm thời, nhưng retry một câu lệnh ghi không tự động an toàn.

Một số tình huống:

- Kết nối bị ngắt trước khi database thực thi câu lệnh.
- Database đã commit nhưng response bị mất.
- Transaction bị deadlock hoặc serialization failure.
- Driver timeout nhưng không biết chắc database đã hoàn tất hay chưa.
- Client retry toàn bộ HTTP request sau khi không nhận response.

Với lỗi mà kết quả commit không rõ, thực hiện lại một thao tác không idempotent có thể áp dụng tác động lần thứ hai. Cần có business key, idempotency key hoặc event ID để xác định request đã được xử lý hay chưa.

Nguyên tắc:

- Chỉ retry các lỗi được xác định là transient theo chính sách.
- Retry toàn bộ transaction khi transaction bị rollback và lỗi có thể thử lại.
- Không đặt `subscribe()` bên trong để tự tạo lần chạy khác.
- Không retry vô hạn; dùng giới hạn số lần và backoff phù hợp.
- Giữ cùng idempotency key qua các lần retry của cùng một request logic.
- Không tạo key mới cho mỗi lần gửi lại vì như vậy hệ thống coi đó là request mới.
- Với side effect ngoài database, dùng outbox và deduplication.

Với Spring transaction, vị trí đặt retry operator có thể ảnh hưởng việc mỗi lần retry có tạo transaction mới hay tiếp tục dùng transaction context cũ. Cần thiết kế và kiểm thử thứ tự transaction/retry theo cấu hình thực tế; không chỉ thêm `retryWhen` vào cuối pipeline rồi giả định mọi lỗi đều được xử lý an toàn.

## 15. R2dbcEntityTemplate và repository trong bài toán upsert

R2dbcEntityTemplate phù hợp với thao tác entity-oriented và cung cấp insert/update riêng. Tuy nhiên, không nên giả định `save()` là một lệnh upsert nguyên tử theo unique business key.

- `ReactiveCrudRepository.save(entity)` chọn insert/update theo entity state detection.
- `R2dbcEntityTemplate.insert(...)` yêu cầu insert.
- `R2dbcEntityTemplate.update(...)` thực hiện update theo query.
- `DatabaseClient` có thể gửi câu SQL upsert đặc thù của database trong một statement.

Nếu cần upsert theo khóa nghiệp vụ hoặc dùng cú pháp `ON CONFLICT`, `ON DUPLICATE KEY UPDATE` hay `MERGE`, DatabaseClient là lựa chọn trực tiếp và dễ kiểm soát. Có thể bọc câu SQL trong custom repository fragment để service không phải biết chi tiết dialect.

Một kiến trúc có thể tách interface:

~~~java
public interface InventoryUpsertRepository {
    Mono<Inventory> upsert(InventoryCommand command);
}
~~~

Implementation dùng DatabaseClient:

~~~java
public class InventoryUpsertRepositoryImpl
        implements InventoryUpsertRepository {

    private final DatabaseClient databaseClient;

    public InventoryUpsertRepositoryImpl(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    @Override
    public Mono<Inventory> upsert(InventoryCommand command) {
        // Thực thi câu SQL upsert theo dialect đã chọn.
        // Bind mọi giá trị và map RETURNING thành Inventory.
        return executeUpsert(command);
    }
}
~~~

`executeUpsert` đại diện cho phần SQL cụ thể của database. Tách fragment giúp phần còn lại của domain/service dùng một hợp đồng ổn định trong khi implementation có thể thay đổi theo dialect.

Nếu ứng dụng hỗ trợ nhiều database, có thể có implementation riêng cho PostgreSQL, MySQL hoặc SQL Server. Không nên giả vờ rằng một câu SQL đặc thù là portable chỉ vì nó được gọi từ API reactive.

## 16. Batch upsert

Một số database hỗ trợ insert nhiều hàng cùng conflict handling:

~~~sql
INSERT INTO inventory (tenant_id, sku, quantity)
VALUES
    (:tenantA, :skuA, :quantityA),
    (:tenantB, :skuB, :quantityB)
ON CONFLICT (tenant_id, sku)
DO UPDATE SET quantity = EXCLUDED.quantity;
~~~

Batch có thể giảm round-trip và phù hợp với đồng bộ dữ liệu. Nhưng cần chú ý:

- Một batch lớn có thể tạo statement và result set lớn.
- Cần giới hạn kích thước batch theo driver/database.
- Payload cần được validate trước khi gửi.
- Cần xác định transaction atomic cho toàn batch hay xử lý theo chunk.
- Các hàng đầu vào trùng conflict key với nhau có thể gây lỗi hoặc hành vi riêng theo database.

Với PostgreSQL, một câu `INSERT ... ON CONFLICT DO UPDATE` không được phép tác động cùng một hàng đích nhiều lần trong cùng một statement; dữ liệu đầu vào có các conflict key trùng nhau có thể gây cardinality violation. Hãy deduplicate hoặc gộp dữ liệu đầu vào theo business key trước khi tạo statement.

Nếu dùng `saveAll`, không nên giả định Spring Data tự tạo một multi-row upsert. `saveAll` là API lưu entity; semantics insert/update dựa trên entity state detection, không tự trở thành dialect-specific upsert theo business key.

## 17. Bảo mật và tính đúng đắn của dữ liệu upsert

Upsert thường được dùng cho đồng bộ hoặc ingest dữ liệu từ bên ngoài. Cần kiểm soát dữ liệu nào được phép ghi đè.

- Validate kiểu, miền giá trị và giới hạn độ dài trước khi bind.
- Không để input quyết định table/column identifier bằng phép nối SQL.
- Chỉ cập nhật các cột mà nguồn dữ liệu được quyền sở hữu.
- Đặt unique constraint và CHECK constraint ở database.
- Xác định tenant trong unique key và trong predicate phù hợp.
- Không tin timestamp/version do client gửi nếu chúng có thể làm lùi trạng thái.
- Không trả thông tin của bản ghi tenant khác khi conflict xảy ra.
- Tránh log idempotency key, token hoặc payload nhạy cảm ở mức không cần thiết.

Bind parameter ngăn giá trị dữ liệu bị diễn giải thành SQL syntax, nhưng không kiểm tra authorization. Một câu upsert có thể hoàn toàn an toàn trước SQL injection mà vẫn cho phép người dùng ghi đè dữ liệu không thuộc quyền của họ nếu service không kiểm tra tenant và quyền sở hữu.

## 18. Kiểm thử upsert và tính lũy đẳng

Kiểm thử cần dùng database tương thích với cú pháp thực tế. Mock DatabaseClient không thể xác nhận conflict target, locking, unique constraint, RETURNING hoặc affected-row behavior.

### 18.1. Kiểm thử insert lần đầu

- Gửi business key chưa tồn tại.
- Xác nhận đúng một hàng được tạo.
- Xác nhận generated/default values phù hợp.
- Xác nhận kết quả RETURNING có các cột cần thiết.

### 18.2. Kiểm thử conflict và update

- Gửi cùng business key với quantity khác.
- Xác nhận vẫn chỉ có một hàng.
- Xác nhận các cột được phép cập nhật đã đổi.
- Xác nhận các cột bất biến như created_at không bị ghi đè.

### 18.3. Kiểm thử cùng payload nhiều lần

- Gửi cùng request hai lần.
- Xác nhận trạng thái cuối giống nhau.
- Xác nhận timestamp hoặc audit field chỉ thay đổi theo chính sách đã định.
- Xác nhận không tạo duplicate event hoặc side effect.

### 18.4. Kiểm thử phép cộng dồn và deduplication

- Gửi cùng event ID hai lần.
- Xác nhận delta chỉ được áp dụng một lần.
- Gửi event ID khác với cùng payload.
- Xác nhận event mới được áp dụng theo nghiệp vụ.

### 18.5. Kiểm thử đồng thời

- Gửi nhiều request đồng thời với cùng unique key.
- Xác nhận database chỉ có một hàng logic.
- Kiểm tra kết quả cuối theo thứ tự/phiên bản mong muốn.
- Xác nhận duplicate request cùng idempotency key không thực hiện nghiệp vụ hai lần.

### 18.6. Kiểm thử rollback

- Claim idempotency key.
- Thực hiện thay đổi nghiệp vụ.
- Cố ý làm một bước sau thất bại.
- Xác nhận transaction rollback cả marker và thay đổi nghiệp vụ nếu chúng được thiết kế cùng transaction.
- Retry cùng key và xác nhận request có thể được xử lý theo chính sách.

### 18.7. Kiểm thử request hash

- Gửi key và payload lần đầu.
- Gửi lại cùng key với cùng payload; trả kết quả trước.
- Gửi cùng key với payload khác; từ chối.
- Kiểm tra phạm vi tenant và retention của key.

Dùng Testcontainers hoặc database test cùng loại/phiên bản với môi trường triển khai. H2 hoặc mock không đủ để chứng minh semantics của PostgreSQL `ON CONFLICT`, MySQL `ON DUPLICATE KEY UPDATE` hay SQL Server `MERGE`.

## 19. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách xử lý |
|---|---|---|
| Insert duplicate key | Không dùng conflict clause hoặc conflict target sai | Kiểm tra unique constraint và SQL dialect |
| Có nhiều hàng cùng business key | Thiếu unique constraint | Tạo primary key/unique index phù hợp |
| Retry làm quantity tăng nhiều lần | Dùng phép cộng dồn không có event deduplication | Dùng event ID duy nhất hoặc gán giá trị tuyệt đối |
| Retry làm updated_at thay đổi liên tục | Gán CURRENT_TIMESTAMP ở mọi lần conflict | Chỉ cập nhật khi dữ liệu đổi hoặc dùng timestamp ổn định |
| Request cùng key trả kết quả sai | Không kiểm tra request fingerprint | Lưu và so sánh request_hash |
| Hai request đồng thời cùng thực hiện nghiệp vụ | Kiểm tra tồn tại ở application trước khi insert | Claim key bằng unique constraint và transaction |
| Upsert ghi đè created_at hoặc field nội bộ | Cập nhật quá nhiều cột | Liệt kê rõ cột được phép thay đổi |
| Event cũ ghi đè trạng thái mới | Không kiểm tra source version/sequence | Dùng điều kiện version trong DO UPDATE |
| RETURNING không phát hàng | DO NOTHING hoặc điều kiện DO UPDATE không thỏa | Xử lý empty result và đọc trạng thái hiện tại |
| SQL chạy ở PostgreSQL nhưng lỗi ở database khác | Cú pháp upsert đặc thù dialect | Tách implementation theo database |
| Side effect bị lặp dù hàng không đổi | Email/HTTP/message được gọi sau mỗi retry | Outbox, consumer deduplication hoặc API idempotency |
| Batch upsert lỗi khi có key lặp | Nhiều input row cùng conflict target trong một statement | Deduplicate/gộp dữ liệu trước khi gửi |

## 20. Quy trình thiết kế upsert an toàn

Trước khi triển khai, hãy xác định:

1. Business key nào nhận diện duy nhất bản ghi?
2. Database đã có primary key hoặc unique constraint tương ứng chưa?
3. Database mục tiêu hỗ trợ cú pháp upsert nào?
4. Nhánh conflict được phép cập nhật những cột nào?
5. Request lặp lại có tạo cùng trạng thái hay cộng dồn tác động?
6. Có timestamp, counter, audit hoặc trigger làm thay đổi kết quả mỗi lần retry không?
7. Có cần idempotency key ở cấp request hoặc event ID ở cấp message không?
8. Cùng key nhưng payload khác được xử lý như thế nào?
9. Claim key và cập nhật nghiệp vụ có cần cùng transaction không?
10. Có side effect bên ngoài database cần outbox/deduplication không?
11. Retry áp dụng cho lỗi nào và giữ nguyên idempotency key ra sao?
12. Đã kiểm thử đồng thời, conflict, rollback và duplicate delivery trên database thật chưa?

Một lựa chọn thiết kế thường phù hợp:

- Dùng **upsert theo unique business key** cho trạng thái mới nhất.
- Dùng **idempotency key** cho request có thể được gửi lại.
- Dùng **event ID** cho message có delivery at-least-once.
- Dùng **transaction** để gắn việc claim/ghi marker với thay đổi nghiệp vụ trong cùng database.
- Dùng **outbox** cho ý định phát event sau commit.
- Dùng **version/condition** khi không muốn dữ liệu cũ ghi đè dữ liệu mới.

## 21. Kết luận

Upsert bằng SQL đặc thù cho phép database xử lý insert và conflict update trong một statement dựa trên unique constraint. Với Spring Data R2DBC, DatabaseClient là lựa chọn trực tiếp để gửi các câu lệnh như PostgreSQL `ON CONFLICT`, MySQL `ON DUPLICATE KEY UPDATE`, SQLite UPSERT hoặc cú pháp `MERGE` của những database hỗ trợ.

Upsert không tự bảo đảm idempotency. Gán một giá trị tuyệt đối thường có thể lặp lại an toàn, trong khi cộng dồn, cập nhật timestamp mỗi lần hoặc gọi side effect bên ngoài có thể tạo tác động lặp. Khi request hoặc message có thể được retry, hãy dùng idempotency key hoặc event ID duy nhất, lưu fingerprint để phát hiện tái sử dụng key với payload khác và đặt các thao tác liên quan trong transaction phù hợp.

Unique constraint xử lý cạnh tranh ở database; transaction bảo đảm các thay đổi liên quan cùng commit hoặc rollback; outbox và consumer deduplication xử lý việc phát message có thể lặp. Kết hợp đúng các cơ chế này giúp thao tác ghi nhiều lần vẫn giữ trạng thái nghiệp vụ nhất quán và có thể dự đoán.

