# Đọc thấy hàng không tồn tại rồi cùng tạo mới

Một tình huống phổ biến trong ứng dụng cơ sở dữ liệu là **kiểm tra một bản ghi chưa tồn tại, rồi tạo bản ghi đó nếu chưa có**. Ví dụ: đăng ký username, tạo hồ sơ khách hàng, khởi tạo cấu hình theo tenant, cấp mã đặt chỗ hoặc tạo tài nguyên theo một khóa nghiệp vụ.

Khi chỉ có một request, quy trình có vẻ đơn giản: tìm bản ghi, nếu không thấy thì insert, sau đó commit. Nhưng nếu hai request chạy đồng thời, cả hai transaction có thể cùng đọc và đều nhận kết quả “không tồn tại”. Sau đó, cả hai cùng thử tạo. Đây là **race condition do kiểm tra rồi mới hành động (check-then-act race)**, còn gọi là *concurrent insert race*, *absence race* hoặc *create-if-absent race*.

Điểm đặc biệt là xung đột xảy ra ngay cả khi tại thời điểm đọc **chưa có hàng nào để khóa**. Một câu lệnh đọc thông thường hoặc thao tác khóa hàng trên kết quả rỗng không mặc nhiên bảo vệ được khoảng trống ấy. Cần đặt quy tắc duy nhất tại nơi có thẩm quyền ghi, hoặc dùng cơ chế khóa/phân xử phù hợp với DBMS và phạm vi nghiệp vụ.

## 1. Diễn biến: hai transaction cùng thấy “không có”

Giả sử hệ thống đăng ký username. Bảng người dùng có cột username; nghiệp vụ yêu cầu một username chỉ thuộc về một người.

```text
Request A / T1                 Request B / T2
---------------                ---------------
BEGIN                          BEGIN
SELECT username='lan'
 -> không có hàng
                               SELECT username='lan'
                                -> không có hàng
INSERT username='lan'
                               INSERT username='lan'
COMMIT                         COMMIT?
```

Cả hai transaction đều kiểm tra ở thời điểm mà username chưa được commit vào bảng. Kết quả đọc riêng của mỗi transaction có thể đúng với snapshot mà nó quan sát, nhưng kết luận “mình là request duy nhất được phép tạo” lại sai khi xét toàn bộ lịch đồng thời.

Kết quả phụ thuộc vào cách DB bảo vệ dữ liệu:

- Nếu không có ràng buộc duy nhất, cả hai dòng có thể được insert và commit. Dữ liệu vi phạm quy tắc nghiệp vụ.
- Nếu có UNIQUE constraint trên username, chỉ một transaction có thể tạo thành công; transaction còn lại nhận lỗi uniqueness hoặc đi theo nhánh conflict của câu lệnh upsert.

```text
Thời gian ---------------------------------------------------->

T1: BEGIN -- SELECT('lan') = empty -- INSERT('lan') -- COMMIT
T2:     BEGIN -- SELECT('lan') = empty -- INSERT('lan') -- COMMIT?
                                                   |
                              UNIQUE constraint: chỉ một lần tạo hợp lệ
```

Đây không đơn giản là “hai transaction cùng cập nhật một hàng”, bởi hàng mục tiêu chưa hiện diện khi cả hai đọc. Đây là cuộc đua trên **khóa nghiệp vụ hoặc điều kiện tồn tại**.

## 2. Vì sao SELECT rồi INSERT không an toàn?

Giả sử bảng không có unique constraint:

```sql
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL
);
```

Ứng dụng thực hiện:

```sql
BEGIN;

SELECT id
FROM users
WHERE username = 'lan';

-- Nếu không có hàng thì:
INSERT INTO users (username)
VALUES ('lan');

COMMIT;
```

Khi hai transaction chạy đồng thời, cả hai có thể nhận tập kết quả rỗng rồi cùng insert. Bảng có thể chứa:

| id | username |
|---:|---|
| 101 | lan |
| 102 | lan |

Mỗi câu SQL riêng lẻ đều có thể chạy thành công, nhưng **bất biến username duy nhất đã bị phá vỡ**. Kiểm tra ở tầng ứng dụng không thay thế được ràng buộc ở cơ sở dữ liệu, bởi hai request có thể thực hiện phép kiểm tra cùng một lúc.

### BEGIN/COMMIT không tự loại bỏ race

Gói hai bước vào transaction xác định ranh giới commit/rollback cho từng request. Nó không tự biến hai bước kiểm tra và tạo thành một thao tác nguyên tử dùng chung giữa mọi request.

Ở mức READ COMMITTED, hai transaction có thể thực hiện các câu SELECT khác nhau và đều không thấy bản ghi chưa được transaction còn lại commit:

```text
T1: SELECT -> empty
T2: SELECT -> empty
T1: INSERT
T2: INSERT
T1: COMMIT
T2: COMMIT
```

Vì vậy, “đã dùng transaction” chưa phải bằng chứng rằng một khóa chưa tồn tại đã được giữ độc quyền.

## 3. Hàng chưa tồn tại thì khóa cái gì?

Một nhầm lẫn phổ biến là dùng SELECT ... FOR UPDATE và cho rằng DB sẽ khóa hàng dù truy vấn không tìm thấy kết quả:

```sql
BEGIN;

SELECT id
FROM users
WHERE username = 'lan'
FOR UPDATE;

-- Không có hàng nào được trả về.

INSERT INTO users (username) VALUES ('lan');
COMMIT;
```

Trong PostgreSQL, FOR UPDATE khóa các hàng thực sự được chọn. Nếu truy vấn không trả về hàng nào, không có row lock trên hàng mang username lan, vì hàng đó chưa tồn tại. Ở READ COMMITTED, chỉ riêng truy vấn này không khóa một “hàng tương lai” để ngăn transaction khác chèn cùng username.

Một số hệ quản trị và isolation level có cơ chế khóa phạm vi, khóa khoảng trống (gap lock) hoặc khóa predicate khác nhau. Những cơ chế ấy có thể bảo vệ một khoảng giá trị/điều kiện trong các điều kiện cụ thể. Nhưng không thể suy luận rằng mọi SELECT FOR UPDATE trên mọi DBMS đều khóa được bản ghi chưa tồn tại. Phải kiểm tra đúng loại chỉ mục, isolation level và ngữ nghĩa khóa của sản phẩm.

**Quy tắc thiết kế:** bất biến “chỉ được có một hàng cho khóa K” phải được bảo vệ ở tầng ghi bằng unique constraint/index hoặc một giao thức khóa được thiết kế rõ ràng. Đừng dựa vào một lần đọc rỗng như bằng chứng rằng request có quyền độc quyền tạo hàng.

## 4. Cách cơ bản: UNIQUE constraint

Nếu nghiệp vụ yêu cầu username không trùng, khai báo ràng buộc tại DB:

```sql
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    CONSTRAINT users_username_unique UNIQUE (username)
);
```

Với bảng đã có sẵn:

```sql
ALTER TABLE users
ADD CONSTRAINT users_username_unique UNIQUE (username);
```

Ràng buộc duy nhất là **hàng rào cuối cùng có thẩm quyền**. Khi hai transaction cố insert cùng giá trị, DBMS điều phối xung đột trên unique index/constraint. Một transaction có thể phải chờ transaction kia kết thúc; nếu giá trị đã được một transaction tạo thành công, transaction còn lại không thể commit bản sao vi phạm uniqueness.

Trong PostgreSQL, thao tác insert cơ bản:

```sql
INSERT INTO users (username)
VALUES ('lan');
```

Ứng dụng bắt lỗi unique violation (SQLSTATE 23505) và chuyển thành phản hồi nghiệp vụ thích hợp, chẳng hạn HTTP 409 Conflict — username đã được sử dụng.

| Kết quả | Ý nghĩa với ứng dụng |
|---|---|
| Insert thành công | Request đã tạo được bản ghi |
| Unique violation | Một bản ghi có cùng khóa duy nhất đã thắng cuộc đua hoặc đã tồn tại; cần xử lý như conflict |

Không nên trả lỗi máy chủ chung cho mọi unique violation. Cần nhận diện constraint hoặc khóa nghiệp vụ gây lỗi để phân biệt xung đột dự kiến với lỗi dữ liệu khác.

### Constraint phải phản ánh đúng khóa nghiệp vụ

Nếu username không phân biệt chữ hoa/thường, quy tắc duy nhất có thể cần chuẩn hóa giá trị hoặc dùng kiểu dữ liệu/index phù hợp. Ví dụ, Lan và lan là trùng hay khác phải do chính sách sản phẩm quyết định.

Trong PostgreSQL, có thể tạo unique index trên giá trị chuẩn hóa:

```sql
CREATE UNIQUE INDEX users_username_ci_unique
ON users (lower(username));
```

Logic tìm kiếm và ghi cũng phải dùng quy tắc chuẩn hóa tương thích. Nếu chỉ kiểm tra ở ứng dụng nhưng unique index áp dụng quy tắc khác, người dùng có thể nhận kết quả khó hiểu.

Khóa duy nhất đôi khi là tổ hợp nhiều cột:

```sql
CREATE TABLE tenant_settings (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    setting_key TEXT NOT NULL,
    setting_value TEXT NOT NULL,
    CONSTRAINT tenant_setting_once
        UNIQUE (tenant_id, setting_key)
);
```

Ràng buộc này bảo vệ bất biến “một tenant chỉ có một cấu hình cho mỗi setting key”. Khóa duy nhất phải xuất phát từ mô hình nghiệp vụ, không chỉ từ cấu trúc câu truy vấn.

## 5. INSERT ... ON CONFLICT: tạo nếu chưa có

Với PostgreSQL, INSERT ... ON CONFLICT cho phép diễn đạt thao tác tạo hoặc xử lý khi khóa đã tồn tại ngay trong một câu lệnh:

```sql
INSERT INTO users (username)
VALUES ('lan')
ON CONFLICT (username) DO NOTHING;
```

Kết hợp unique constraint trên username, chỉ một bản ghi cho username này được tạo. Request cạnh tranh có thể không insert được dòng nào; ứng dụng cần kiểm tra số dòng được trả về/ảnh hưởng để biết mình có thực sự tạo bản ghi hay không.

Một biến thể upsert cập nhật dữ liệu khi đã có:

```sql
INSERT INTO tenant_settings (
    tenant_id,
    setting_key,
    setting_value
)
VALUES (7, 'timezone', 'Asia/Ho_Chi_Minh')
ON CONFLICT (tenant_id, setting_key)
DO UPDATE
SET setting_value = EXCLUDED.setting_value
RETURNING tenant_id, setting_key, setting_value;
```

EXCLUDED đại diện cho hàng dự kiến được insert nhưng gặp xung đột. Trong ví dụ, nếu khóa đã tồn tại, câu lệnh cập nhật giá trị. Đây là chính sách ghi đè theo thứ tự DB xử lý, không phải lúc nào cũng đúng nghiệp vụ.

Nếu muốn giữ nguyên giá trị đã tạo trước, DO NOTHING phù hợp hơn. Nếu cần trả về bản ghi hiện có, ứng dụng có thể đọc nó sau khi xử lý conflict, tùy isolation và yêu cầu. Không nên dùng DO UPDATE chỉ để né lỗi uniqueness khi việc ghi đè dữ liệu không được cho phép.

### Khi nào dùng DO NOTHING?

Nó phù hợp với thao tác khởi tạo idempotent kiểu “tạo nếu chưa có”:

```sql
INSERT INTO tenant_settings (tenant_id, setting_key, setting_value)
VALUES (7, 'language', 'vi')
ON CONFLICT (tenant_id, setting_key) DO NOTHING;
```

Nếu hai worker cùng khởi tạo cấu hình, unique constraint bảo đảm chỉ có một hàng. Worker còn lại không tạo hàng trùng và có thể đọc cấu hình hiện hữu để tiếp tục.

Lưu ý: DO NOTHING chỉ giải quyết thao tác insert bị xung đột. Nếu quy trình cần biết ai là người tạo, phân biệt “đã tạo mới” với “đã tồn tại”, hoặc cần phát sự kiện sau tạo, ứng dụng phải thiết kế kết quả và side effect tương ứng.

### Ví dụ: một hồ sơ cho mỗi khách hàng

```sql
CREATE TABLE customer_profiles (
    customer_id BIGINT PRIMARY KEY,
    display_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO customer_profiles (customer_id, display_name)
VALUES (9001, 'Nguyen An')
ON CONFLICT (customer_id) DO NOTHING;
```

Hai request khởi tạo hồ sơ cho cùng customer ID có thể đến đồng thời. Primary key customer_id chính là unique constraint bảo vệ quy tắc “một hồ sơ cho mỗi khách hàng”. Một request tạo mới; request còn lại không tạo trùng.

Nếu chính sách là “request mới luôn cập nhật tên hiển thị”, có thể dùng DO UPDATE, nhưng phải kiểm tra rằng mọi request đều được phép ghi đè và thứ tự ghi phù hợp:

```sql
INSERT INTO customer_profiles (customer_id, display_name)
VALUES (9001, 'Nguyen An')
ON CONFLICT (customer_id)
DO UPDATE SET display_name = EXCLUDED.display_name;
```

DO NOTHING và DO UPDATE có ý nghĩa nghiệp vụ khác nhau. Lựa chọn phải dựa trên quy tắc sở hữu và cập nhật dữ liệu.

## 6. Khi điều kiện phức tạp: Serializable và khóa nghiệp vụ

Không phải mọi quy tắc “chỉ một tiến trình được tạo” đều biểu diễn được bằng một cột duy nhất. Có trường hợp điều kiện phụ thuộc vào khoảng, nhiều bảng hoặc quy tắc phức tạp. Khi đó có thể cần cơ chế điều phối khác.

### Serializable isolation

Một cách tiếp cận là chạy cả kiểm tra và tạo trong transaction SERIALIZABLE:

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT id
FROM reservations
WHERE resource_id = 42
  AND status = 'ACTIVE';

-- Nếu chưa có bản ghi phù hợp:
INSERT INTO reservations (resource_id, status)
VALUES (42, 'ACTIVE');

COMMIT;
```

Với hai transaction cùng kiểm tra một predicate rồi cùng insert, DBMS có thể phát hiện phụ thuộc khiến lịch không thể tuần tự hóa và hủy một transaction. Ứng dụng phải:

- Bắt lỗi serialization failure.
- Rollback đúng transaction.
- Retry **toàn bộ transaction** với số lần hữu hạn và backoff phù hợp.
- Bảo đảm side effect bên ngoài transaction không bị lặp ngoài ý muốn.

Trong PostgreSQL, SERIALIZABLE dùng Serializable Snapshot Isolation. Hai transaction có thể cùng đọc predicate rỗng rồi ghi các hàng khác nhau; một transaction có thể bị hủy do xung đột tuần tự hóa. Cách xử lý predicate và khóa khác nhau giữa DBMS.

Nếu quy tắc thực chất là uniqueness đơn giản, unique constraint vẫn trực tiếp và dễ kiểm soát hơn serializable.

### Advisory lock theo khóa nghiệp vụ

Một số DBMS hỗ trợ advisory lock: khóa do ứng dụng chủ động xin theo một khóa logic thay vì khóa hàng vật lý. Với PostgreSQL, có thể dùng transaction-level advisory lock:

```sql
BEGIN;

-- Ví dụ: khóa namespace của customer 9001.
SELECT pg_advisory_xact_lock(9001);

SELECT id
FROM customer_profiles
WHERE customer_id = 9001;

-- Nếu chưa có:
INSERT INTO customer_profiles (customer_id, display_name)
VALUES (9001, 'Nguyen An');

COMMIT;
```

Các transaction cùng tuân thủ một quy ước lock sẽ lần lượt đi qua phần kiểm tra/tạo. Khóa transaction-level được giữ đến hết transaction. Tuy nhiên:

- Mọi đường ghi có thể tạo cùng khóa phải xin cùng advisory lock.
- Khóa ứng dụng không tự thay thế unique constraint; code path quên lấy khóa vẫn có thể phá bất biến.
- Cần thiết kế ánh xạ khóa không va chạm hoặc quản lý namespace rõ ràng.
- Phải chú ý thứ tự lấy nhiều khóa để tránh deadlock.
- Không giữ advisory lock lâu qua lời gọi mạng hoặc xử lý không cần thiết.

Một thiết kế bền vững có thể dùng advisory lock để giảm cạnh tranh và vẫn giữ unique constraint làm hàng rào dữ liệu cuối cùng.

### Bảng điều phối có hàng tồn tại từ trước

Nếu cần khóa theo tài nguyên nghiệp vụ có định danh ổn định, hệ thống có thể tạo một hàng điều phối từ trước rồi khóa hàng đó. Khác với việc cố khóa bản ghi nghiệp vụ chưa tồn tại, hàng điều phối đã có nên được khóa rõ ràng.

Ví dụ, bảng resource_mutex có một hàng cho mỗi resource_id. Transaction xin khóa hàng tương ứng trước khi kiểm tra và tạo reservation. Cơ chế này cần bảo đảm hàng điều phối luôn tồn tại và mọi writer tuân thủ cùng giao thức.

Đây là cách tuần tự hóa ở tầng ứng dụng/DB. Chi phí là nhiều thao tác phải chờ cùng một hàng điều phối, kể cả khi một số thao tác có thể độc lập. Nếu constraint đơn giản đủ bảo vệ dữ liệu, không cần thêm bảng khóa chỉ vì muốn khóa “hàng chưa tồn tại”.

## 7. Phân biệt absence race với phantom read và lost update

Các bất thường có thể liên quan nhưng không đồng nghĩa:

| Hiện tượng | Tình huống điển hình | Điều cốt lõi |
|---|---|---|
| **Absence/check-then-act race** | Hai transaction cùng truy vấn key K và đều không thấy hàng, rồi cùng tạo | Tranh chấp trên sự vắng mặt của một khóa nghiệp vụ |
| **Phantom read** | Một transaction chạy lại predicate query và thấy tập hàng thay đổi do transaction khác insert/delete | Tập kết quả truy vấn thay đổi |
| **Lost update** | Hai transaction đọc cùng giá trị hiện có, cùng tính giá trị mới rồi một lần ghi đè mất cập nhật kia | Cập nhật dựa trên dữ liệu cũ bị ghi đè |
| **Unique conflict** | Hai transaction cùng insert giá trị mà unique constraint bảo vệ | DB từ chối hoặc xử lý một thao tác theo chính sách conflict |

Absence race có thể được mô tả qua phantom/predicate conflict trong một số mô hình isolation, nhưng trong ứng dụng thường được gọi riêng để nhấn mạnh chuỗi “kiểm tra không có → tạo mới”. Nếu unique constraint tồn tại, kết quả được bảo vệ ngay cả khi transaction isolation thấp hơn serializable.

## 8. Xử lý lỗi, conflict và retry

Khi constraint là hàng rào bảo vệ, request thua cuộc không nên tự động coi mọi lỗi là “đã thành công”. Ứng dụng cần diễn giải theo nghiệp vụ:

- **Username đã được dùng:** trả conflict và yêu cầu người dùng chọn username khác.
- **Cấu hình đã có:** đọc cấu hình hiện hữu rồi tiếp tục nếu đó là hành vi idempotent được phép.
- **Bản ghi định danh theo request đã tồn tại:** có thể trả lại kết quả cũ nếu cùng idempotency key và payload phù hợp.
- **Serialization failure/deadlock:** rollback và retry toàn transaction khi lỗi có thể phục hồi.
- **Lỗi khác:** không nuốt lỗi hoặc giả định bản ghi đã tồn tại.

Không retry vô hạn. Có thể giới hạn số lần, dùng exponential backoff có jitter và quan sát tỷ lệ conflict. Retry phải bao trọn phần đọc quyết định và ghi, vì chỉ chạy lại câu insert có thể không sửa được các giả định cũ đã dùng ở bước trước.

### Idempotency key khác business key

Hai loại khóa này có thể cùng cần:

- **Business key** như username, (tenant_id, setting_key) hoặc (resource_id, slot) bảo vệ quy tắc không tạo hai thực thể trùng nghiệp vụ.
- **Idempotency key** như request_id giúp một yêu cầu được gửi lại do timeout không tạo thêm tác dụng phụ. Cùng key cần gắn với cùng ý định/payload; hệ thống cần lưu kết quả hoặc trạng thái xử lý của request.

Hai người khác nhau cùng đăng ký username lan có hai request khác nhau nhưng đụng cùng business key. Một người bấm nút đăng ký nhiều lần do mạng chậm có thể gửi nhiều request; idempotency key giúp nhận diện lần gửi lại của cùng ý định. Unique constraint và idempotency key giải quyết hai khía cạnh khác nhau.

Ví dụ cấu trúc lưu idempotency:

```sql
CREATE TABLE idempotency_records (
    idempotency_key TEXT PRIMARY KEY,
    response_body JSONB,
    completed_at TIMESTAMPTZ
);
```

Quy trình hoàn chỉnh còn cần quản lý trạng thái IN_PROGRESS, timeout khi worker chết, ghi kết quả trong transaction thích hợp và định nghĩa hành vi khi cùng key nhưng payload khác nhau. Chỉ có primary key chưa tạo ra toàn bộ giao thức idempotency.

## 9. Ví dụ: đặt chỗ một lần cho một tài nguyên và khung giờ

Giả sử mỗi tài nguyên chỉ có một đặt chỗ đang hoạt động trong cùng khung giờ:

```sql
CREATE TABLE reservations (
    id BIGSERIAL PRIMARY KEY,
    resource_id BIGINT NOT NULL,
    slot_start TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    customer_id BIGINT NOT NULL
);
```

Nếu trạng thái ACTIVE là trạng thái duy nhất chiếm chỗ, PostgreSQL hỗ trợ unique partial index:

```sql
CREATE UNIQUE INDEX one_active_reservation_per_slot
ON reservations (resource_id, slot_start)
WHERE status = 'ACTIVE';
```

Hai request có thể cùng đọc và thấy chưa có reservation cho resource 42 ở slot đã chọn. Cả hai cùng thử insert:

```sql
INSERT INTO reservations
    (resource_id, slot_start, status, customer_id)
VALUES
    (42, '2026-12-01 09:00:00+07', 'ACTIVE', 9001);
```

Unique partial index bảo vệ bất biến tại điểm ghi. Chỉ một đặt chỗ ACTIVE cho cặp (resource_id, slot_start) có thể tồn tại. Nếu transaction thua cuộc nhận unique violation, API có thể trả 409 Conflict cùng thông tin “khung giờ vừa được đặt”.

Khi một booking chuyển sang CANCELLED, partial unique index không còn áp dụng cho hàng đó; một booking ACTIVE khác có thể được tạo. Quy tắc này phải khớp với định nghĩa trạng thái nào được xem là chiếm chỗ. Nếu PENDING cũng giữ chỗ, điều kiện index cần bao gồm trạng thái đó.

Lưu ý về thời gian: nếu nghiệp vụ cho phép đặt các khoảng có thời lượng chồng lấn, uniqueness trên slot_start không đủ. Có thể cần exclusion constraint với range type trong PostgreSQL hoặc cơ chế phát hiện giao nhau tương ứng. Cấu trúc constraint phải biểu diễn đúng bất biến thời gian thực tế.

## 10. Cách kiểm tra và chẩn đoán lỗi

Khi gặp lỗi trùng bản ghi hoặc tạo tài nguyên hai lần, hãy xác định:

1. **Khóa nghiệp vụ là gì?** Một cột, nhiều cột, giá trị chuẩn hóa, tenant scope hay một khoảng thời gian?
2. **Có ràng buộc ở DB không?** Kiểm tra primary key, unique constraint/index, partial index và quy tắc NULL.
3. **Hai transaction đọc ở thời điểm nào?** Cả hai có thể cùng nhận tập kết quả rỗng không?
4. **Cơ chế nào phân xử insert?** Unique index, upsert, serializable validation, predicate/gap lock hay advisory lock?
5. **Kết quả conflict được xử lý ra sao?** Trả 409, đọc bản ghi hiện có, bỏ qua tạo lặp hay retry toàn transaction?
6. **Side effect có bị lặp không?** Có phát event, gửi email, thu tiền hoặc gọi dịch vụ ngoài trước khi biết transaction thắng không?
7. **Có kiểm thử đồng thời thật không?** Hai kết nối độc lập phải bắt đầu gần đồng thời hoặc được đồng bộ hóa đủ để tái hiện cửa sổ race.

Kiểm thử nên xác nhận cả hai khả năng: một bản ghi duy nhất tồn tại sau hai request cạnh tranh, và ứng dụng trả kết quả phù hợp cho request thắng/thua. Đếm số hàng sau khi chạy tuần tự hai lần không đủ tái hiện race condition.

## 11. Những nhầm lẫn thường gặp

**“Cả hai SELECT đều trả rỗng nên cả hai có quyền tạo.”** Không. Kết quả rỗng chỉ nói transaction chưa nhìn thấy hàng trong snapshot của nó; không phải quyền sở hữu độc quyền đối với khóa đó.

**“Đặt BEGIN/COMMIT quanh SELECT và INSERT là đủ.”** Không nhất thiết. Transaction bảo vệ phạm vi của từng request, nhưng không tự loại bỏ race giữa các request.

**“SELECT FOR UPDATE luôn khóa cả hàng chưa tồn tại.”** Sai với PostgreSQL khi truy vấn không trả về hàng; DBMS khác có thể có cơ chế khóa khoảng/predicate riêng.

**“Chỉ cần kiểm tra tồn tại ở backend.”** Backend vẫn nhận nhiều request đồng thời. Kiểm tra ứng dụng cần kết hợp constraint hoặc giao thức phân xử ở tầng lưu trữ.

**“ON CONFLICT dùng được mà không cần unique constraint.”** Không. DBMS cần unique/exclusion constraint hoặc arbiter phù hợp để xác định xung đột.

**“DO UPDATE luôn an toàn hơn DO NOTHING.”** Không. DO UPDATE có thể ghi đè dữ liệu đã tồn tại; chính sách cập nhật phải được nghiệp vụ cho phép.

**“Serializable có nghĩa không bao giờ có lỗi.”** Không. DBMS có thể hủy một transaction để bảo đảm lịch tuần tự; ứng dụng vẫn cần xử lý serialization failure và retry.

**“Retry insert là đủ.”** Không phải lúc nào. Nếu logic trước insert dựa trên dữ liệu đã đọc hoặc đã thực hiện side effect, phải thiết kế lại ranh giới retry và idempotency.

## 12. Ghi nhớ

Lỗi “đọc thấy hàng không tồn tại rồi cùng tạo mới” bắt nguồn từ việc **sự vắng mặt cũng là một điều kiện mà nhiều transaction có thể cùng quan sát**, nhưng một lần đọc rỗng không trao quyền độc quyền để tạo bản ghi.

Với quy tắc duy nhất đơn giản, cách bảo vệ trực tiếp là khai báo PRIMARY KEY hoặc UNIQUE đúng theo khóa nghiệp vụ rồi dùng insert/upsert và xử lý conflict. Với điều kiện phức tạp hơn, có thể cân nhắc serializable isolation, khóa predicate/range, advisory lock hoặc hàng điều phối đã tồn tại; phải làm rõ mọi writer có tuân thủ cùng giao thức hay không.

Điều quyết định là **DB hoặc cơ chế điều phối phải phân xử cạnh tranh tại điểm tạo**, còn ứng dụng phải diễn giải kết quả thành công, conflict, retry và side effect theo đúng quy tắc nghiệp vụ.
