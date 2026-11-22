# Thiết kế hợp đồng lưu trữ cho một danh mục có định danh

Một hệ thống bán hàng lưu danh mục nhóm sản phẩm như Điện tử, Sách, Phụ kiện. Mỗi nhóm có một UUID, một mã có thể hiển thị và một tên. Một yêu cầu tưởng đơn giản — “đổi tên nhóm SACH thành Sách & Tạp chí” — lập tức đặt ra nhiều câu hỏi: UUID có đổi không? Mã SACH có được tái sử dụng khi nhóm cũ đã xóa? Hai tenant có thể cùng dùng mã SACH? Khi hai người cùng sửa tên, thay đổi nào thắng? Sản phẩm tham chiếu đến nhóm bị xóa sẽ được xử lý thế nào?

Đó là lý do **hợp đồng lưu trữ cho một danh mục có định danh** phải mô tả rõ identity, uniqueness, vòng đời, quy tắc đọc/ghi, transaction, lỗi, tính nhất quán và cách kiểm chứng. Chỉ tạo một class Java và một bảng SQL chưa đủ.

Bài thuộc chương **Thực hành tổng hợp** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Qua một ví dụ nhất quán, người học vận dụng thiết kế mô hình dữ liệu, lược đồ PostgreSQL, JDBC/Spring, chỉ mục, giao dịch, kiểm soát đồng thời, xử lý lỗi kết nối, bảo mật theo tenant, migration, sao lưu và tối ưu hiệu năng để tạo ra một persistence boundary rõ ràng cho ứng dụng Java.

> **Mục tiêu sản phẩm:** một nhóm sản phẩm có định danh ổn định, có thể được tra cứu và tham chiếu an toàn; thao tác ghi phải bảo vệ invariant ngay cả khi request lặp, nhiều writer đồng thời hoặc transaction gặp lỗi. Repository là công cụ thực hiện hợp đồng, không phải nguồn tự quyết định nghiệp vụ.

## 1. Kết quả cần đạt

Sau khi hoàn thành bài này, người học có thể:

- Phân biệt **identity ổn định**, **business code**, **display name** và khóa tham chiếu.
- Xác định uniqueness theo tenant, quy tắc chuẩn hóa code và chính sách khi đổi/tái sử dụng mã.
- Viết invariant và trạng thái vòng đời cho danh mục có định danh.
- Định nghĩa contract Create, Get, List, Rename, Archive dưới dạng input, output, precondition, effect và failure.
- Thiết kế PostgreSQL schema, PRIMARY KEY, UNIQUE, CHECK, FOREIGN KEY và index phục vụ đúng mẫu truy cập.
- Xây dựng port Java độc lập công nghệ, adapter JdbcTemplate có SQL rõ ràng và mapping nhất quán.
- Sử dụng transaction và optimistic concurrency để không ghi đè thay đổi hợp lệ.
- Xử lý duplicate request, lost ACK sau COMMIT, lỗi SQLSTATE, idempotency và retry đúng phạm vi.
- Phân biệt dữ liệu committed ở primary với dữ liệu stale ở cache/replica.
- Lập kế hoạch xóa mềm, tham chiếu lịch sử, migration và kiểm thử persistence theo hợp đồng.
- Đánh giá các lựa chọn thiết kế và giải thích vì sao một phương án đáp ứng hoặc vi phạm invariant.

## 2. Bối cảnh bài thực hành

Giả sử Catalog Service cung cấp danh mục nhóm sản phẩm cho nhiều cửa hàng (tenant). Mỗi tenant có thể tự tạo các nhóm:

| Tenant | ID (rút gọn) | Mã | Tên hiển thị |
|---|---|---|---|
| 101 | C1 | SACH | Sách |
| 101 | C2 | DIENTU | Điện tử |
| 202 | C3 | SACH | Books |
| 101 | C4 | PHUKIEN | Phụ kiện |

Một sản phẩm có thể tham chiếu đến một nhóm bằng ID. Một mã nhóm có thể xuất hiện ở hai tenant khác nhau, nhưng không được trùng trong cùng tenant.

### 2.1. Nhu cầu chức năng

- Tạo nhóm mới với mã và tên.
- Tra cứu nhóm còn hoạt động bằng UUID hoặc mã trong phạm vi tenant.
- Liệt kê nhóm còn hoạt động, có phân trang ổn định.
- Đổi tên/miêu tả nhóm mà không làm thay đổi identity của nó.
- Xóa mềm (archive) nhóm; dữ liệu tham chiếu lịch sử vẫn có thể giải thích.
- Không cho hai writer ghi đè thay đổi của nhau một cách im lặng.
- Ghi audit/outbox cho những thay đổi cần được hệ khác đồng bộ.
- Tránh tạo hai nhóm cho cùng một ý định khi client gửi lại request sau timeout.

### 2.2. Nhu cầu phi chức năng

- Tách dữ liệu tenant A và tenant B ở mọi thao tác.
- Có giới hạn kết nối, độ trễ, số row mỗi page và tải trên database.
- Ràng buộc quan trọng được DB kiểm tra, không chỉ Java validation.
- Lỗi duplicate/conflict/infra được phân loại rõ.
- Có thể triển khai nhiều phiên bản service trong lúc tiến hóa schema.
- Có backup/restore và chính sách retention phù hợp với danh mục đã archive.
- Có test database thật cho SQL, constraint, transaction và concurrency.

### 2.3. Những điều không nằm trong ví dụ chính

Bài **không** mặc định danh mục có cây phân cấp hay quan hệ nhiều-cha. Nếu nghiệp vụ cần cây, phải bổ sung parent_id, quy tắc chống cycle, chiến lược di chuyển nhánh và test cạnh tranh riêng. Bài cũng không mô phỏng một sàn thương mại điện tử hoàn chỉnh; mục tiêu là thiết kế **ranh giới persistence cho danh mục có identity** có thể mở rộng an toàn.

## 3. Trước hết phải định nghĩa identity

Một entity có identity vẫn là “cùng entity” ngay cả khi nhiều thuộc tính thay đổi. Trong ví dụ:

~~~text
Identity logic trong tenant: (tenantId, categoryId)
categoryId: UUID ổn định cho suốt vòng đời record
categoryCode: mã nghiệp vụ để con người/khách hàng tra cứu
displayName: nhãn có thể đổi, không phải identity
~~~

### 3.1. Vì sao dùng UUID làm định danh nội bộ?

UUID có thể được tạo trước khi INSERT và mang qua API/event mà không phụ thuộc tên hoặc mã của nhóm. Khi đổi tên hoặc đổi quy tắc hiển thị, các tham chiếu dùng UUID vẫn có ý nghĩa.

Nhưng UUID **không tự bảo đảm**:

- Row đã được INSERT/COMMIT.
- Người gọi được phép đọc/ghi row đó.
- Request không tạo record trùng nghiệp vụ nếu retry với UUID mới.
- Mã nhóm là duy nhất.
- Không có hai tenant dùng trùng cùng UUID theo thiết kế composite key.

UUID là một chiến lược định danh, không thay authorization, UNIQUE nghiệp vụ hay idempotency.

### 3.2. Phân biệt khóa kỹ thuật và khóa nghiệp vụ

| Trường | Vai trò | Có nên đổi? | Ràng buộc |
|---|---|---|---|
| tenantId | Phạm vi quyền và định danh tổ chức | Không qua update tùy ý | Có trong mọi khóa/query quan trọng |
| categoryId | Identity ổn định cho reference | Không | PRIMARY KEY cùng tenantId |
| categoryCode | Alternate/business key | Trong contract này: không | UNIQUE theo tenant, chuẩn hóa |
| displayName | Giá trị hiển thị | Có, kèm kiểm soát version | NOT NULL, không chỉ whitespace |
| description | Nội dung mô tả | Có | Nullable theo hợp đồng |
| version | Dấu mốc optimistic concurrency | Tăng theo mutation | Không âm |
| deletedAt | Dấu mốc archive | Chuyển từ NULL sang thời điểm | Luồng đọc active loại record đã archive |

Nếu mã danh mục được phép thay đổi sau này, phải quyết định alias, redirect, history và external references. Không đổi ngầm code trong cùng câu UPDATE tên rồi hy vọng mọi hệ thống phụ thuộc vẫn hoạt động.

### 3.3. Code là khóa tra cứu, không phải text tùy ý

Ví dụ quy ước chuẩn hóa:

~~~text
Client nhập:  " sach "
Normalize:   "SACH"
Lưu DB:      "SACH"
Lookup:      normalize(input) rồi tra (tenantId, code)
~~~

Contract cần công bố chính xác Unicode/case sensitivity và kí tự được phép. Ở ví dụ, chọn mã ASCII gồm A–Z, 0–9, dấu gạch dưới/gạch ngang; viết hoa theo Locale.ROOT, loại khoảng trắng ở hai đầu, dài từ 2 đến 40 ký tự. Đây là **một quyết định nghiệp vụ minh họa**, không áp đặt cho mã tiếng Việt hoặc toàn bộ hệ thống.

**Không chỉ dựa vào normalize ở Java:** batch/ETL hoặc phiên bản ứng dụng cũ có thể viết trực tiếp vào bảng. DB phải bảo vệ miền giá trị và uniqueness cuối cùng.

### 3.4. Chính sách tái sử dụng mã sau archive

Trong bài này, mã **không được tái sử dụng** trong cùng tenant dù nhóm cũ đã archive. Lý do:

- URL, file import, hệ thống ngoài có thể vẫn lưu mã SACH.
- Mã tái sử dụng có thể làm lịch sử báo cáo trỏ tới nhóm mới.
- Một alias cũ có thể bị hiểu sai sau nhiều tháng.

Chính sách này dẫn đến UNIQUE(tenant_id, code) trên **mọi** row, không chỉ row active. Nếu hệ thống khác yêu cầu cho phép reuse, cần chọn hợp đồng khác và test rõ: mã cũ còn dùng được ở đâu, có cần bảng lịch sử alias không, và nguồn tham chiếu có bắt buộc dùng UUID không.

## 4. Invariant nghiệp vụ và trạng thái vòng đời

Một invariant là điều **phải đúng trong mọi trạng thái đã commit hợp lệ**. Để dễ kiểm chứng, viết chúng thành các câu có thể diễn đạt bằng SQL/test.

### 4.1. Invariant tối thiểu

~~~text
I1: Với một tenant, categoryId xác định tối đa một category.
I2: Với một tenant, categoryCode chuẩn hóa xác định tối đa một category,
    kể cả category đã archive.
I3: categoryId và categoryCode không đổi trong vòng đời record.
I4: displayName khác NULL và không rỗng sau khi trim.
I5: version khởi đầu bằng 0 và tăng đúng một lần cho mutation được chấp nhận.
I6: Category đã archive không được sửa hoặc archive lần nữa bằng contract thường.
I7: Read active không trả category đã archive.
I8: Update/Archive không tác động sang tenant khác, dù cùng UUID.
I9: Dữ liệu tham chiếu lịch sử không mất nghĩa sau archive.
I10: Một lệnh ghi thất bại không được để lại record/audit dở dang trong DB.
~~~

### 4.2. Sơ đồ vòng đời

~~~mermaid
stateDiagram-v2
    [*] --> Active: Create thành công và COMMIT
    Active --> Active: Rename / edit description, version + 1
    Active --> Archived: Archive, version + 1
    Archived --> Archived: Read lịch sử
~~~

Trong contract này, không có Restore bằng API công khai. Nếu muốn Restore, phải định nghĩa thêm:

- Ai có quyền restore?
- Restore có khôi phục nguyên code và ID không?
- Product nào được hiển thị lại?
- Có cần tăng version và ghi audit?
- Liệu các writer đang xử lý archive đồng thời có thể gây trạng thái sai?

**Không tạo Restore bằng cách SET deleted_at=NULL tùy tiện** nếu hợp đồng mới chưa được duyệt.

### 4.3. Invariant nhiều bảng cần xử lý riêng

Một nhóm đã archive vẫn có thể được tham chiếu bởi sản phẩm lịch sử. Đây không phải lỗi FK: group row vẫn tồn tại. Trong bài này ta cho phép archive dù còn product tham chiếu, nhưng giao diện lựa chọn nhóm cho sản phẩm **mới** chỉ hiển thị category active.

Nếu nghiệp vụ yêu cầu “product active phải tham chiếu category active”, FOREIGN KEY đơn thuần không bảo vệ được predicate deleted_at IS NULL. Cần transaction/locking/protocol hoặc quy tắc thay thế được kiểm chứng dưới ghi đồng thời. Không suy FK đảm bảo mọi invariant liên quan trạng thái.

## 5. Chốt phạm vi transaction và nguồn sự thật

Chọn PostgreSQL primary làm nguồn authoritative của danh mục. Các câu INSERT/UPDATE/ARCHIVE và việc ghi outbox của chính danh mục nằm trong **cùng local DB transaction** khi workflow yêu cầu.

~~~mermaid
flowchart TD
    API["HTTP API / Worker"] --> APP["Category Application Service"]
    APP --> PORT["CategoryRepository port"]
    PORT --> JDBC["PostgreSQL JDBC adapter"]
    JDBC --> P[("PostgreSQL primary")]
    P --> R[("Read replica")]
    P --> O[("Outbox table")]
    O --> WORKER["Outbox dispatcher"]
    WORKER --> MQ["Event broker / Search projection"]
~~~

Các mức khẳng định:

| Mốc | Có thể kết luận | Chưa thể kết luận |
|---|---|---|
| Java đã tạo Category object | Có dữ liệu dự kiến | DB đã INSERT |
| Repository gọi INSERT thành công | Statement đã thành công trong transaction | Outer COMMIT hoàn tất |
| COMMIT primary được xác nhận | Dữ liệu đã commit theo durability policy | Replica/cache/search đã kịp cập nhật |
| Outbox row commit cùng category | Ý định phát event được lưu cùng business change | Consumer đã nhận chính xác một lần |
| GET từ replica hiển thị mới | Replica đó đã bắt kịp đủ cho query | Mọi node đã đồng bộ |

**Nguyên tắc thiết kế:** một thành công ở tầng Java không được được nâng thành cam kết durability hoặc consistency mạnh hơn mức mà transaction và hệ thống lưu trữ thực sự cung cấp.

## 6. Chuyển invariant thành hợp đồng CRUD có thể kiểm thử

Mỗi thao tác phải công bố đầu vào, hậu điều kiện và lỗi. Không viết port chỉ có save(Entity) chung chung rồi để caller tự suy “update hay insert”, “đã commit hay chưa”, “có thể sửa code hay không”.

| Operation | Precondition | Postcondition khi commit | Không thành công |
|---|---|---|---|
| Create | Tenant hợp lệ, code/name hợp lệ, ID/code chưa tồn tại | Một category active, version=0, ID/code ổn định | Duplicate ID/code, invalid data, lỗi DB |
| FindActiveById | Tenant/ID hợp lệ | Trả đúng row active của tenant hoặc empty | Lỗi DB không biến thành empty |
| FindActiveByCode | Code đã chuẩn hóa | Trả category active khớp (tenant,code) | Empty nếu không có/archived |
| ListActive | Limit và cursor hợp lệ | Danh sách active có thứ tự xác định | Bad cursor/limit, lỗi DB |
| Rename | Category active, expectedVersion khớp | Chỉ tên/mô tả và version/updatedAt đổi | Missing/archived/version conflict |
| Archive | Category active, expectedVersion khớp | deletedAt được đặt, version+1 | Missing/archived/version conflict |

### 6.1. Hợp đồng Create

Create phải đảm bảo:

- Tạo đúng **một** row khi transaction commit.
- Không tự tạo row khác khi phát hiện code trùng.
- Cùng code ở tenant khác được phép theo chính sách.
- Không âm thầm đổi code do data truncation hoặc lower/upper không được chuẩn hóa.
- Khi lệnh thứ hai trong transaction lỗi, category và outbox nếu có được rollback.
- API có thể cấp ID trước INSERT, nhưng ID đó chỉ là **ý định định danh**, không phải bằng chứng COMMIT.

Với request đến từ mạng, cần phân biệt create cùng **ID** và create cùng **idempotency key**; ID duy nhất không tự định nghĩa replay semantics khi client đổi ID.

### 6.2. Hợp đồng Read

Read active trả đúng row của tenant hiện tại và chỉ row chưa archive. Trả Optional.empty() chỉ khi query đã thực thi thành công nhưng không có row phù hợp. Connection error, SQL timeout hoặc schema mismatch phải được biểu diễn là lỗi hạ tầng, **không** chuyển thành not found.

Read dùng primary sau write nếu API hứa read-your-writes; read replica chậm chỉ được dùng khi contract chấp nhận stale hoặc có watermark phù hợp.

### 6.3. Hợp đồng Rename và Archive

Cả hai thao tác nhận expectedVersion để chống lost update:

~~~text
Input:
  tenantId, categoryId, expectedVersion, update fields

When row is active AND version matches:
  update permitted fields
  version = version + 1
  updatedAt = timestamp từ DB
  return committed-intended row in current transaction

Otherwise:
  no row changed; caller nhận conflict/missing theo policy
~~~

Tên không ảnh hưởng identity; code và ID không được đưa vào trường update. Nếu client gửi cả entity stale từ trước rồi merge tất cả, các field không dự định thay đổi có thể bị ghi đè.

### 6.4. Chọn contract cho thất bại của UPDATE có 0 hàng

Một câu UPDATE có điều kiện trả 0 có thể do:

- ID không tồn tại.
- ID thuộc tenant khác.
- Row đã archive.
- expectedVersion cũ.
- Row bị transaction khác thay đổi giữa lúc đọc và ghi.

Trong bài, repository trả Optional.empty() cho **mọi** trường hợp không khớp và không tự lộ bản ghi tenant khác. Application service có thể trả một lỗi ConflictOrNotFound được công bố hoặc làm truy vấn bổ sung khi cần phân loại và đã xác thực quyền. Truy vấn thứ hai chỉ là snapshot sau đó, có thể chịu race mới; không tự xem nó là phân loại tuyệt đối về trạng thái tại thời điểm UPDATE.

## 7. Schema PostgreSQL phản ánh contract

Một schema minh họa:

~~~sql
CREATE TABLE catalog_categories (
    tenant_id bigint NOT NULL,
    id uuid NOT NULL,
    code varchar(40) NOT NULL,
    display_name varchar(150) NOT NULL,
    description text NULL,
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz NULL,

    CONSTRAINT catalog_categories_pk
        PRIMARY KEY (tenant_id, id),

    CONSTRAINT catalog_categories_tenant_positive
        CHECK (tenant_id > 0),

    CONSTRAINT catalog_categories_code_unique
        UNIQUE (tenant_id, code),

    CONSTRAINT catalog_categories_code_format
        CHECK (code ~ '^[A-Z0-9][A-Z0-9_-]{1,39}$'),

    CONSTRAINT catalog_categories_name_nonblank
        CHECK (btrim(display_name) <> ''),

    CONSTRAINT catalog_categories_version_nonnegative
        CHECK (version >= 0)
);
~~~

Giải thích:

- PRIMARY KEY bảo vệ một identity trong tenant.
- UNIQUE trên (tenant_id,code) ngăn trùng mã kể cả row đã archive.
- CHECK regex bảo vệ miền code ngay cả khi một batch job không dùng Java validator.
- CHECK name không chỉ whitespace cùng NOT NULL bảo vệ tên có ý nghĩa.
- version để ứng dụng thực hiện compare-and-swap khi cập nhật.
- created_at, updated_at theo timezone-aware timestamp; chọn DB làm nguồn thời gian của bản ghi.
- deleted_at NULL nghĩa là active; khác NULL nghĩa là archived.

Các CHECK không tự cưỡng chế **mọi** invariant: DB vẫn cho đổi id/code nếu có câu UPDATE trực tiếp có quyền và không có thêm cơ chế chặn. Contract application cần cấm; nếu môi trường có nhiều writer và cần bảo đảm tuyệt đối, có thể dùng quyền SQL tách biệt, trigger hoặc chế độ chỉ ghi qua stored procedure có kiểm soát. Không coi “setter Java là private” là bảo vệ dữ liệu toàn hệ.

### 7.1. Chính sách VARCHAR và Unicode

Code dùng ASCII, còn display_name có thể chứa tiếng Việt. varchar(150) giới hạn số ký tự theo cách PostgreSQL xác định đối với chuỗi; application cũng cần validation về độ dài và cách xử lý Unicode.

Trong mẫu, CHECK btrim(display_name) <> '' không bắt mọi ký tự Unicode trông như khoảng trắng. Nếu domain yêu cầu chuẩn hóa nghiêm ngặt hơn, cần định nghĩa rõ trong code và test; không suy SQL btrim đủ cho mọi trường hợp quốc tế.

### 7.2. Index cho đường đọc

PRIMARY KEY tạo index phù hợp tra (tenant_id,id). UNIQUE(tenant_id,code) tạo index phục vụ findByCode và keyset pagination theo code.

Nếu cần danh sách nhóm gần thay đổi nhất:

~~~sql
CREATE INDEX idx_catalog_categories_active_recent
ON catalog_categories
    (tenant_id, updated_at DESC, id DESC)
WHERE deleted_at IS NULL;
~~~

Index bổ sung có chi phí ghi, lưu trữ và bảo trì. Chỉ tạo khi có truy vấn danh sách recent cần thiết và xác minh bằng EXPLAIN trên dữ liệu đại diện. Không tạo index cho mọi field “cho chắc”; PostgreSQL vẫn phải cân nhắc selectivity, số lượng row theo tenant và pattern sort/filter.

### 7.3. Quan hệ sản phẩm tham chiếu danh mục

Nếu products tham chiếu category qua khóa định danh, khóa ngoại nên bảo vệ phạm vi tenant:

~~~sql
CREATE TABLE catalog_product_links (
    tenant_id bigint NOT NULL,
    product_id uuid NOT NULL,
    category_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, product_id, category_id),

    CONSTRAINT catalog_product_links_category_fk
        FOREIGN KEY (tenant_id, category_id)
        REFERENCES catalog_categories(tenant_id, id)
        ON DELETE RESTRICT
);
~~~

Ở ví dụ, bảng này mô tả một liên kết sản phẩm–nhóm; trong hệ thống đầy đủ, product_id còn cần FK tới bảng products có ranh giới tenant tương ứng. Không suy bảng liên kết một mình chứng minh sản phẩm tồn tại.

**Quan trọng:** ON DELETE RESTRICT ngăn xóa vật lý category đang được tham chiếu; nó **không** ngăn SET deleted_at khi archive. Đây là chủ đích của hợp đồng lưu lịch sử. Đường tạo link mới phải kiểm tra category active theo giao thức có xét cạnh tranh, hoặc cân nhắc ràng buộc chặt hơn nếu invariant bắt buộc. FK không kiểm tra deleted_at IS NULL.

### 7.4. Đọc lịch sử khác đọc active

Nếu một đơn hàng năm trước tham chiếu category đã archive, màn hình lịch sử có thể cần biết tên nhóm thời điểm bán. Hai lựa chọn:

- Đọc category hiện tại (kể cả archived) qua identity; tên có thể đã đổi so với lúc bán.
- Lưu snapshot tên/mã tại thời điểm giao dịch trong order line để bảo tồn lịch sử thực tế.

Danh mục hiện hành và chứng cứ lịch sử có contract khác nhau. Không ép một JOIN tới category active làm các đơn hàng cũ biến mất khỏi báo cáo.

## 8. Port Java độc lập tầng lưu trữ

Dùng record immutable để hạn chế chia sẻ mutable entity qua nhiều tầng:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

public record CategoryRecord(
    long tenantId,
    UUID id,
    String code,
    String displayName,
    String description,
    long version,
    Instant createdAt,
    Instant updatedAt,
    Instant deletedAt
) {}

public record NewCategory(
    long tenantId,
    UUID id,
    String code,
    String displayName,
    String description
) {}

public interface CategoryRepository {
    CategoryRecord insert(NewCategory category);

    Optional<CategoryRecord> findActiveById(
        long tenantId, UUID categoryId);

    Optional<CategoryRecord> findActiveByCode(
        long tenantId, String normalizedCode);

    List<CategoryRecord> listActiveAfterCode(
        long tenantId, String afterCode, int limit);

    Optional<CategoryRecord> renameIfVersionMatches(
        long tenantId,
        UUID categoryId,
        long expectedVersion,
        String displayName,
        String description);

    Optional<CategoryRecord> archiveIfVersionMatches(
        long tenantId, UUID categoryId, long expectedVersion);
}
~~~

Contract của port:

- insert trả representation do DB trả từ INSERT ... RETURNING, nhưng **chưa tuyên bố outer transaction đã commit**.
- Các read chỉ trả active row; đường báo cáo/historical lookup khác cần method riêng có kiểm soát quyền.
- rename và archive trả Optional.empty() khi không có row khớp toàn bộ điều kiện.
- Port không có phương thức “đổi code” hoặc “hard delete”, bởi chính sách hiện tại cấm.
- Port không phát HTTP response, gửi email hay publish Kafka trực tiếp.
- Các lỗi constraint/connection/timeout phải nổi lên theo loại có thể phân biệt; không biến thành Optional.empty() tùy tiện.

### 8.1. Chuẩn hóa code ở application boundary

~~~java
import java.util.Locale;

public final class CategoryCode {
    private CategoryCode() {}

    public static String normalize(String input) {
        if (input == null) {
            throw new IllegalArgumentException("code is required");
        }
        String code = input.strip().toUpperCase(Locale.ROOT);

        if (!code.matches("[A-Z0-9][A-Z0-9_-]{1,39}")) {
            throw new IllegalArgumentException("invalid category code");
        }
        return code;
    }
}
~~~

Code gọi normalize trước khi chạm DB; DB CHECK là tuyến phòng thủ thứ hai. Nếu một input có Unicode hoặc độ dài ngoài quy ước, từ chối có kiểm soát thay vì sửa âm thầm thành một mã khác gây collision.

### 8.2. Khi nào nên dùng entity có hành vi domain?

Một Category domain object có thể bảo vệ transition và quy tắc đổi tên, nhưng **không nên** tự biết JDBC URL, EntityManager hoặc chi tiết Spring. Port nhận command/data phù hợp với bất biến; adapter lo truy vấn và mapping.

Nếu dùng JPA, vẫn giữ phân biệt domain entity/managed entity/DTO và cẩn trọng với dirty checking: object thay đổi trong RAM không phải bằng chứng transaction đã commit. Port là ranh giới hợp đồng, không phải cơ chế tự động biến mọi setter thành durable write.

## 9. Ma trận lỗi của repository

| Hiện tượng | Kết quả nên có ở boundary | Không nên làm |
|---|---|---|
| Trùng (tenant,id) hoặc (tenant,code) | Duplicate/Conflict có nguyên nhân đã kiểm chứng | Tạo ID khác và retry như một thao tác mới |
| CHECK/NOT NULL violation | Validation/data integrity failure | Nuốt lỗi, chèn default tùy ý |
| UPDATE/ARCHIVE ảnh hưởng 0 row | MissingOrConflict hoặc Optional.empty theo port | Luôn trả true |
| Connection timeout trước khi có statement | Infrastructure unavailable | Trả not found |
| Mất ACK ở COMMIT | Unknown outcome, cần reconciliation | Suy DB rollback |
| PostgreSQL 40001/40P01 | Transaction abort, cân nhắc retry toàn transaction | Retry vô hạn riêng một SQL |
| Query hủy do deadline | Lỗi có phân loại và deadline tổng | Retry không giới hạn |
| Replica đọc stale | Freshness policy: primary/watermark hoặc eventual result | Dùng stale result làm quyết định ghi authoritative |

SQLSTATE trong PostgreSQL giúp chẩn đoán, còn cách ánh xạ sang exception/domain result phụ thuộc Spring/adapter. Cần kiểm thử đúng contract thực tế chứ không phụ thuộc chuỗi thông báo lỗi database.

## 10. Trước khi viết adapter, xác định ranh giới commit

Một application service thường sở hữu transaction của use case; repository chỉ thực hiện SQL trong transaction đó:

~~~text
API / Command handler
    |
    v
Application service (@Transactional)
    |
    +-- Repository.insert/update/rename
    +-- OutboxRepository.appendEvent (nếu cần)
    |
    v
Transaction manager COMMIT
    |
    v
Caller nhận kết quả bình thường nếu proxy sở hữu transaction thành công
~~~

Nếu service method **tham gia outer transaction**, việc nó return không có nghĩa outer transaction đã commit. Nếu method được gọi bằng self-invocation bỏ qua proxy, @Transactional có thể không được áp dụng theo mô hình AOP đã cấu hình.

**Quy tắc:** mô tả rõ port trả kết quả của statement/trạng thái transaction đang chạy; chỉ nâng kết quả thành “đã lưu” ở boundary thực sự sở hữu commit và chỉ theo mức durability đã cấu hình.

## 11. JDBC adapter: thực thi hợp đồng bằng SQL có điều kiện

Các ví dụ dùng PostgreSQL JdbcTemplate của Spring. Adapter cần đảm bảo:

- Mọi truy vấn có tenant_id.
- Các tham số được bind, không nối input thành SQL.
- Mỗi UPDATE/ARCHIVE chỉ thay đổi row active có version khớp.
- Cột do DB sinh được lấy bằng RETURNING khi contract cần.
- Trường mutable/nullable được map theo đúng kiểu.
- Connection/transaction do DataSource và transaction manager quản lý.

### 11.1. Mapping một row thành CategoryRecord

~~~java
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.UUID;
import org.springframework.jdbc.core.RowMapper;

final class CategoryRowMapper implements RowMapper<CategoryRecord> {
    @Override
    public CategoryRecord mapRow(ResultSet rs, int rowNum)
            throws SQLException {

        Timestamp deleted = rs.getTimestamp("deleted_at");
        return new CategoryRecord(
            rs.getLong("tenant_id"),
            rs.getObject("id", UUID.class),
            rs.getString("code"),
            rs.getString("display_name"),
            rs.getString("description"),
            rs.getLong("version"),
            rs.getTimestamp("created_at").toInstant(),
            rs.getTimestamp("updated_at").toInstant(),
            deleted == null ? null : deleted.toInstant()
        );
    }
}
~~~

Mapper dùng JDBC timestamp theo một chiến lược timezone đã được kiểm thử; trong ứng dụng thật, hãy xác minh driver/DB/session timezone và mapping của timestamptz sang Instant. Đừng chuyển qua LocalDateTime hệ thống rồi suy nó là instant UTC một cách mù quáng.

### 11.2. INSERT và RETURNING

~~~java
@Repository
public class JdbcCategoryRepository implements CategoryRepository {
    private static final CategoryRowMapper MAPPER =
        new CategoryRowMapper();

    private final JdbcTemplate jdbc;

    public JdbcCategoryRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public CategoryRecord insert(NewCategory c) {
        List<CategoryRecord> rows = jdbc.query(
            """
            INSERT INTO catalog_categories
                (tenant_id, id, code, display_name, description)
            VALUES (?, ?, ?, ?, ?)
            RETURNING tenant_id, id, code, display_name, description,
                      version, created_at, updated_at, deleted_at
            """,
            MAPPER,
            c.tenantId(), c.id(), c.code(),
            c.displayName(), c.description()
        );

        if (rows.size() != 1) {
            throw new IllegalStateException("Unexpected insert count");
        }
        return rows.get(0);
    }

    // Các method khác được trình bày bên dưới.
}
~~~

Đây là một phần class adapter. Trong triển khai thực, đưa các method dưới đây vào cùng class và import List, UUID, Optional, JdbcTemplate, Repository tương ứng.

**Ý nghĩa của RETURNING:** Row được DB trả lại là kết quả của statement trong transaction hiện hành. Nó **không** xác nhận transaction bên ngoài đã COMMIT. Nếu sau INSERT có bước ghi outbox thất bại, cả hai cần rollback theo contract.

### 11.3. FIND active theo identity

~~~java
@Override
public Optional<CategoryRecord> findActiveById(
        long tenantId, UUID categoryId) {

    List<CategoryRecord> rows = jdbc.query(
        """
        SELECT tenant_id, id, code, display_name, description,
               version, created_at, updated_at, deleted_at
        FROM catalog_categories
        WHERE tenant_id = ?
          AND id = ?
          AND deleted_at IS NULL
        """,
        MAPPER, tenantId, categoryId
    );
    return rows.stream().findFirst();
}
~~~

Không có row khớp trả Optional.empty(). Lỗi connection/SQL không bị bắt rồi chuyển thành empty. Lỗi hạ tầng phải lên tới tầng ứng dụng để phân loại và trả kết quả thích hợp.

Nếu một method trả historical category đã archive, nó phải có tên và quyền tương ứng. Đừng bỏ filter deleted_at trong method findActive chỉ để một report cũ chạy được.

### 11.4. FIND theo alternate key code

~~~java
@Override
public Optional<CategoryRecord> findActiveByCode(
        long tenantId, String normalizedCode) {

    List<CategoryRecord> rows = jdbc.query(
        """
        SELECT tenant_id, id, code, display_name, description,
               version, created_at, updated_at, deleted_at
        FROM catalog_categories
        WHERE tenant_id = ?
          AND code = ?
          AND deleted_at IS NULL
        """,
        MAPPER, tenantId, normalizedCode
    );
    return rows.stream().findFirst();
}
~~~

Caller phải truyền normalized code (hoặc adapter xác minh lại), không dựa vào database để tự lower/upper theo một collation chưa được quy định. Vì UNIQUE(tenant_id,code), tìm theo code trả tối đa một row trong schema hợp lệ.

### 11.5. LIST theo keyset cursor

~~~java
@Override
public List<CategoryRecord> listActiveAfterCode(
        long tenantId, String afterCode, int limit) {

    if (limit < 1 || limit > 100) {
        throw new IllegalArgumentException("Invalid page size");
    }

    // Theo domain: code hợp lệ luôn lớn hơn chuỗi rỗng.
    String cursor = afterCode == null
        ? ""
        : CategoryCode.normalize(afterCode);

    return jdbc.query(
        """
        SELECT tenant_id, id, code, display_name, description,
               version, created_at, updated_at, deleted_at
        FROM catalog_categories
        WHERE tenant_id = ?
          AND deleted_at IS NULL
          AND code > ?
        ORDER BY code ASC
        LIMIT ?
        """,
        MAPPER, tenantId, cursor, limit
    );
}
~~~

Lựa chọn cursor chuỗi rỗng là hợp lệ **vì** schema chỉ cho code bắt đầu bằng A–Z hoặc 0–9. Nếu domain cho phép code rỗng, Unicode/collation đặc biệt hoặc thay cách sort, thiết kế cursor phải thay tương ứng.

Cursor từ client phải được kiểm tra/encode đáng tin và gắn với tenant, filter, sort order nếu cần. Query này trả một trang theo trạng thái khi SELECT chạy; **không** bảo đảm snapshot ổn định xuyên nhiều HTTP request khi dữ liệu bị insert/archive đồng thời.

### 11.6. RENAME có expectedVersion

~~~java
@Override
public Optional<CategoryRecord> renameIfVersionMatches(
        long tenantId,
        UUID categoryId,
        long expectedVersion,
        String displayName,
        String description) {

    List<CategoryRecord> rows = jdbc.query(
        """
        UPDATE catalog_categories
        SET display_name = ?,
            description = ?,
            version = version + 1,
            updated_at = now()
        WHERE tenant_id = ?
          AND id = ?
          AND version = ?
          AND deleted_at IS NULL
        RETURNING tenant_id, id, code, display_name, description,
                  version, created_at, updated_at, deleted_at
        """,
        MAPPER,
        displayName, description, tenantId, categoryId, expectedVersion
    );
    return rows.stream().findFirst();
}
~~~

Không thay id/code trong UPDATE, dù caller gửi DTO chứa các trường đó. Khi hai writer cùng expectedVersion, PostgreSQL xử lý conflict ở row và điều kiện version; chỉ một mutation có thể cập nhật từ version cũ thành version mới nếu không có lỗi transaction khác.

Nếu ứng dụng đổi tên thành cùng giá trị đang lưu, contract hiện tại **vẫn tăng version** khi UPDATE thành công. Nếu muốn no-op không tăng version, phải thiết kế điều kiện IS DISTINCT FROM và nói rõ semantics/return, không thay đổi ngầm giữa các adapter.

### 11.7. ARCHIVE có điều kiện

~~~java
@Override
public Optional<CategoryRecord> archiveIfVersionMatches(
        long tenantId, UUID categoryId, long expectedVersion) {

    List<CategoryRecord> rows = jdbc.query(
        """
        UPDATE catalog_categories
        SET deleted_at = now(),
            version = version + 1,
            updated_at = now()
        WHERE tenant_id = ?
          AND id = ?
          AND version = ?
          AND deleted_at IS NULL
        RETURNING tenant_id, id, code, display_name, description,
                  version, created_at, updated_at, deleted_at
        """,
        MAPPER, tenantId, categoryId, expectedVersion
    );
    return rows.stream().findFirst();
}
~~~

Một lần archive thành công không làm mất row vật lý; findActive không thấy, nhưng đường đọc lịch sử với quyền phù hợp còn có thể đọc record. Replay với expectedVersion cũ trả empty; nếu API muốn DELETE idempotent về effect, application phải quyết định response phù hợp thay vì thay câu SQL theo cảm tính.

### 11.8. Những gì adapter chưa tự bảo vệ

Các method trên giả định caller đã chuẩn hóa code, validate displayName và lấy tenant từ nguồn đáng tin. Database constraints là lớp bảo vệ cuối cho dữ liệu nhập sai; contract validation ở tầng API giúp trả lỗi có ý nghĩa hơn.

Đoạn adapter chưa có idempotency key, outbox, API authorization hoặc retry policy. Các trách nhiệm đó nằm ở application service/transaction boundary; không nhét tất cả vào một generic save() khó kiểm chứng.

## 12. Validation ở hai lớp: ứng dụng và database

Ứng dụng cần từ chối đầu vào sớm, nhất quán và có thông điệp phù hợp. Database cần bảo vệ invariant khi có writer không đi qua validation đó.

Ví dụ:

~~~java
public final class CategoryValidation {
    private CategoryValidation() {}

    public static String normalizeName(String input) {
        if (input == null) {
            throw new IllegalArgumentException("name is required");
        }
        String value = input.strip();

        if (value.isEmpty() || value.length() > 150) {
            throw new IllegalArgumentException("invalid display name");
        }
        return value;
    }

    public static long requireTenant(long tenantId) {
        if (tenantId <= 0) {
            throw new IllegalArgumentException("invalid tenant");
        }
        return tenantId;
    }
}
~~~

**Không nhầm hai quy tắc whitespace:** Java strip xử lý một số Unicode whitespace theo Java, còn PostgreSQL btrim() mặc định chủ yếu loại khoảng trắng thông thường. Nếu yêu cầu chuẩn hóa mạnh, thiết kế một canonicalization rule và test dữ liệu Unicode/batch writer. DB CHECK trong ví dụ bảo vệ tối thiểu, application kiểm tra bổ sung theo contract.

### 12.1. Các trường hợp biên

- Code chứa chữ thường, khoảng trắng hai đầu, dấu, Unicode, ký tự không hợp lệ.
- Code dài 1, 2, 40 và 41 ký tự.
- Tên bằng NULL, chuỗi rỗng, toàn khoảng trắng, tiếng Việt có dấu và emoji.
- Description là NULL khác với chuỗi rỗng; cần quyết định có chuẩn hóa không.
- Tenant không hợp lệ hoặc tenant không được actor truy cập.
- UUID hợp lệ về cú pháp nhưng chưa tồn tại ở DB.
- Version âm hoặc version vượt phạm vi kiểu long nếu đến từ input.
- Input có ký tự như dấu nháy đơn: phải được bind, không nối SQL.

Test nên bao gồm cả dữ liệu từ migration/batch, vì không phải mọi writer đều đi qua cùng HTTP validation.

## 13. Không dùng ORM entity như hợp đồng API

Nếu ứng dụng dùng JPA/Hibernate, có thể map catalog_categories thành entity và dùng @Version. Tuy nhiên:

- Setter trên entity chỉ thay đổi object trong persistence context; flush/commit vẫn là mốc riêng.
- merge detached entity cũ có thể ghi đè field không chủ ý.
- @Version có thể phát hiện conflict ở flush/commit, không nhất thiết ở setter.
- @Transactional trên self-invocation có thể không hoạt động theo proxy-based Spring AOP.
- Trả JPA entity trực tiếp ra HTTP có thể lộ field nội bộ, kích hoạt lazy loading hoặc khiến caller tưởng object đã commit.

Trong bài này, port trả record immutable và thao tác cập nhật nêu rõ tên trường. Dù thay adapter bằng JPA, phải giữ nguyên behavior contract; không bắt client biết provider có dirty checking hay gọi flush lúc nào.

## 14. Service Java: kiểm soát một use case trọn vẹn

Một service nên xác định tenant từ principal/context đáng tin, chạy validation, gọi repository trong transaction và dịch kết quả statement thành domain outcome.

~~~java
@Service
public class CategoryApplicationService {
    private final CategoryRepository categories;

    public CategoryApplicationService(CategoryRepository categories) {
        this.categories = categories;
    }

    @Transactional
    public CategoryRecord create(
            long authorizedTenantId,
            String rawCode,
            String rawName,
            String description) {

        long tenantId = CategoryValidation.requireTenant(
            authorizedTenantId);
        String code = CategoryCode.normalize(rawCode);
        String name = CategoryValidation.normalizeName(rawName);

        NewCategory candidate = new NewCategory(
            tenantId,
            UUID.randomUUID(),
            code,
            name,
            description
        );
        return categories.insert(candidate);
    }

    @Transactional
    public CategoryRecord rename(
            long authorizedTenantId,
            UUID categoryId,
            long expectedVersion,
            String rawName,
            String description) {

        if (expectedVersion < 0) {
            throw new IllegalArgumentException("Invalid version");
        }
        String name = CategoryValidation.normalizeName(rawName);

        return categories.renameIfVersionMatches(
            authorizedTenantId,
            categoryId,
            expectedVersion,
            name,
            description
        ).orElseThrow(() ->
            new CategoryConflictOrNotFoundException()
        );
    }
}
~~~

Ví dụ giả định tồn tại CategoryConflictOrNotFoundException thuộc domain application, các import Spring/UUID tương ứng và một transaction manager cho DataSource chính. Không dùng phương thức create như trên cho một **HTTP idempotency contract** mà vẫn khẳng định replay tuyệt đối an toàn: nó sinh UUID mới mỗi attempt. Khi API cần idempotency, phải bổ sung request key và transaction theo mục sau.

### 14.1. Authorization trước khi gọi repository

authorizedTenantId phải được suy từ identity/principal đã được xác thực, không phải ID do client tự quyết định. Nếu request chứa tenant path, so sánh với quyền/claim một cách rõ ràng trước khi truy vấn.

Repository có WHERE tenant_id là lớp giới hạn cần thiết, nhưng **không thay kiểm tra actor có quyền với tenantId nào**. Một attacker có thể gửi đúng UUID của tenant khác; backend không được dùng tenantId do attacker chọn để truy vấn thẳng.

### 14.2. Ghi audit/outbox cùng local transaction

Một create có yêu cầu phát event có thể dùng:

~~~java
@Transactional
public CategoryRecord createWithOutbox(CreateCategoryCommand command) {
    CategoryRecord row = categories.insert(command.toNewCategory());
    outbox.appendCategoryCreated(row.tenantId(), row.id(),
                                 row.code(), row.version());
    return row;
}
~~~

Đây là pseudocode với outbox, command và transaction manager được cấu hình cùng DB. Nếu outbox INSERT thất bại, category INSERT phải rollback. Không publish event trực tiếp trước COMMIT rồi suy nghiệp vụ đã bền vững. Dispatcher có thể phát lặp event khi retry, nên event ID và consumer idempotency vẫn cần.

### 14.3. Lưu kết quả của service có nghĩa ở ranh giới nào?

Với Spring proxy thực sự mở và sở hữu transaction, caller **bên ngoài proxy** nhận kết quả bình thường sau khi commit thành công. Nếu method tham gia outer transaction, kết quả trả về từ method không chứng minh outer transaction đã commit. Không trả HTTP success từ bên trong transaction trước khi transaction owner hoàn tất.
## 15. Idempotency: cùng một ý định không tạo hai danh mục

HTTP client có thể timeout sau khi server đã COMMIT. Nếu server mỗi lần gọi create đều sinh UUID mới, hai request cùng nội dung có thể là:

- Hai ý định hợp lệ khác nhau từ người dùng.
- Một ý định được client gửi lại vì không nhận được response.
- Một request lỗi được proxy/job tự retry.

**Không thể phân biệt các trường hợp chỉ bằng việc so code hoặc nhìn object trong JVM.** UNIQUE code giúp không có hai row cùng code trong tenant, nhưng không định nghĩa response cho replay hay việc cùng key với payload khác phải xử lý thế nào.

### 15.1. Hợp đồng idempotency ở API

Thiết kế một endpoint:

~~~text
POST /categories
Idempotency-Key: 5a2f0bb6-aac6-4c7f-b7e7-63dc8074c0dd

Payload: { code: "SACH", displayName: "Sách" }
~~~

Hợp đồng:

1. Key R có phạm vi tenant và thao tác CreateCategory.
2. Lần đầu xử lý R thành công lưu category và bản ghi idempotency trong cùng transaction.
3. Replay R với **cùng canonical payload** trả lại category/result đã lưu hoặc trạng thái xử lý được định nghĩa.
4. Replay R với payload khác bị từ chối, không thay đổi kết quả cũ.
5. Request key có retention đủ dài so với thời gian client có thể retry; chính sách sau hết hạn phải được công bố.
6. Khi kết quả COMMIT chưa rõ, đối soát ở primary hiện hành theo key R, không đọc replica trễ rồi tạo record mới.

### 15.2. Schema request key

~~~sql
CREATE TABLE category_create_requests (
    tenant_id bigint NOT NULL,
    request_key uuid NOT NULL,
    payload_hash bytea NOT NULL,
    category_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (tenant_id, request_key),
    CONSTRAINT category_request_hash_size
        CHECK (octet_length(payload_hash) = 32),

    CONSTRAINT category_request_category_fk
        FOREIGN KEY (tenant_id, category_id)
        REFERENCES catalog_categories(tenant_id, id)
);
~~~

Ví dụ dùng digest 32 byte để so canonical payload (chẳng hạn SHA-256) chứ không dùng hash đơn thuần làm lớp bảo vệ bí mật. Không ghi payload nhạy cảm vào log. Nếu input có field nullable, thứ tự JSON khác nhau hoặc whitespace khác nhau, cần canonicalization rõ để “cùng payload” được xác định nhất quán.

### 15.3. Một giao thức thực hiện có transaction rõ ràng

Có thể thiết kế theo hướng:

~~~text
BEGIN transaction
  Đọc request (tenant,R) nếu đã tồn tại.
    - Cùng payload_hash: trả category/result tham chiếu.
    - Khác payload_hash: từ chối.
  Nếu chưa tồn tại:
    - INSERT category mới.
    - INSERT category_create_requests(tenant,R,hash,categoryId).
COMMIT
~~~

**Race quan trọng:** hai transaction có thể đồng thời không thấy request R rồi cùng thử tạo. PRIMARY KEY trên (tenant,R) sẽ bảo vệ uniqueness, nhưng bên thua có thể gặp UNIQUE category_code hoặc request key trước khi nó biết kết quả đối thủ.

Phải xử lý constraint conflict có kiểm soát: rollback transaction thất bại, **bắt đầu transaction mới** đọc request R ở primary, so hash và trả kết quả đã commit nếu trùng; nếu vẫn chưa thấy bản ghi (đối thủ đang chạy hoặc outcome chưa rõ), chờ/backoff có deadline và tái đối soát. Không chỉ catch DuplicateKeyException trong một transaction PostgreSQL đã bị abort rồi tiếp tục SELECT trên chính transaction lỗi.

Một thiết kế nâng cao có thể serialize ngay từ đầu bằng request-key claim với một row khóa và trạng thái PROCESSING, nhưng cần bảo đảm không bao giờ commit row PROCESSING mà chưa có protocol phục hồi/stale claim. Hợp đồng ở đây quan trọng hơn lựa chọn cụ thể của SQL.

### 15.4. Duplicate code khác duplicate request key

Nếu hai actor gửi **hai key khác nhau** nhưng cùng code SACH, đó là xung đột business key; API nên trả duplicate/conflict theo contract. Không tự trả category hiện có như thể hai request là một ý định nếu yêu cầu của chúng khác nhau.

Nếu cùng key R và payload nhưng actor đổi code trên retry, đó là replay khác payload — phải bị từ chối; không để một key dần đại diện cho những thao tác khác nhau.

### 15.5. Không coi timeout là rollback

~~~text
Client -> POST R
Service -> PostgreSQL COMMIT category C1 và request R
ACK bị mất
Client thấy timeout
Client -> POST R lần nữa
Service -> trả lại C1 theo request R
~~~

Nếu client tạo key mới R2 cho lần retry, server không còn đủ bằng chứng đó là cùng ý định. Vì vậy key phải được tạo/giữ ổn định ở request boundary, không sinh lại tùy tiện trong mỗi retry.

## 16. Concurrency: version là một phần hợp đồng, không phải trường trang trí

### 16.1. Hai người cùng đổi tên

~~~text
T0: Category C1, name="Sách", version=4

Actor A đọc version=4
Actor B đọc version=4

A đổi tên thành "Sách học thuật", expectedVersion=4
B đổi tên thành "Sách thiếu nhi", expectedVersion=4
~~~

Với UPDATE có WHERE version=4, chỉ một mutation từ version 4 có thể cập nhật row; transaction còn lại sẽ thấy 0 row hoặc lỗi transaction phù hợp. Sau khi winner COMMIT, version là 5.

**Nếu bỏ điều kiện version**, request đến sau có thể lặng lẽ ghi đè tên người trước, dù người dùng đã sửa dựa trên dữ liệu cũ. Đó là lost update.

### 16.2. Rename và Archive tranh chấp

Hai request cùng version=7: một rename, một archive. Vì cả hai UPDATE có deleted_at IS NULL và version=7, chỉ một có thể thắng từ cùng state:

- Rename thắng: row active version=8.
- Archive thắng: row archived version=8.
- Không được cho cả hai báo thành công với cùng expectedVersion.

Nếu muốn archive được ưu tiên hơn rename trong mọi trường hợp, cần contract/locking riêng; optimistic CAS chỉ quyết định theo lịch commit, không tự định nghĩa ưu tiên nghiệp vụ.

### 16.3. Version phải tăng đúng phạm vi mutation

Nếu update tên thất bại vì name không hợp lệ, version không được tăng. Nếu UPDATE/ARCHIVE thành công, version tăng đúng một lần. Nếu một transaction khác rollback sau UPDATE, version committed phải giữ giá trị cũ.

Nếu entity có trigger tự tăng version và adapter cũng tăng, một lần cập nhật có thể tăng 2; test phải phát hiện. Chọn **một nguồn chịu trách nhiệm tăng version** và ghi rõ trong contract.

### 16.4. Cạnh tranh liên quan nhiều bảng

Ví dụ business yêu cầu: chỉ được link product vào category còn active.

~~~text
T1: Kiểm tra category C1 đang active.
T2: Archive category C1.
T1: INSERT product-category link tới C1.
~~~

Foreign key có thể cho phép link vì row vẫn tồn tại, dù category đã archived. Nếu invariant bắt buộc “mọi link mới phải trỏ category active”, cần điều phối:

- T1 khóa category theo một mode đủ để serialize với archive, kiểm tra deleted_at trong transaction trước INSERT.
- T2 dùng một UPDATE/lock tương thích để không vượt qua kiểm tra của T1 mà không bị điều phối.
- Có thể phải tách active product link và historical link, hoặc dùng một state machine khác.
- Test interleaving thực tế, không chỉ unit test kiểm tra isActive() ở Java.

Đặc biệt, SELECT FOR KEY SHARE do FK thông thường không thay thế mọi yêu cầu đồng bộ trạng thái deleted_at của nghiệp vụ. Nếu dùng khóa explicit, phải hiểu mode khóa, row update, deadlock và hiệu năng của DBMS đang triển khai.

## 17. Đọc danh mục: tính mới và tính ổn định của trang kết quả

### 17.1. Read-after-create và read-after-rename

Nếu POST create/rename ghi primary rồi GET qua replica bất đồng bộ, GET có thể trả 404 hoặc tên cũ trong khoảng replay lag. Contract phải chọn:

- GET sau ghi đọc primary cho use case cần read-your-writes.
- Hoặc client giữ minVersion/watermark và chỉ dùng replica đã đạt mốc.
- Hoặc API công bố eventual consistency và giao diện hiển thị trạng thái đang đồng bộ.

Không biến một result từ replica chưa bắt kịp thành bằng chứng create rollback hoặc category đã biến mất.

### 17.2. Cache key phải có tenant

Một cache key chỉ dùng category code có thể trộn hai tenant:

~~~text
Sai:   category:SACH
Đúng:  category:{tenantId}:SACH
~~~

Đúng hơn chỉ ở bước **namespace**; cache vẫn phải bảo vệ quyền truy cập, TTL, invalidation, version và khả năng category đã archive.

Nếu đổi tên/ archive thành công ở DB rồi process chết trước khi xóa cache, cache có thể giữ state cũ. Có thể dùng TTL có kiểm soát, versioned key, transactional outbox cho invalidation và routing primary với luồng cần freshness nghiêm ngặt.

### 17.3. Vì sao không cache Category object mutable dùng chung?

Một in-memory cache giữ đúng cùng reference Category mutable trong JVM có thể khiến một setter ở request A làm request B quan sát thay đổi chưa commit. Dùng immutable DTO/record, hạn chế chia sẻ managed entity và phân biệt cache entry với nguồn dữ liệu authoritative.

### 17.4. Keyset pagination và thay đổi dữ liệu giữa hai trang

Với code là khóa immutable và UNIQUE trong tenant, keyset theo code giúp kết quả trang có thứ tự xác định. Nhưng nếu hai HTTP request được thực hiện ở hai snapshot khác nhau, category mới được insert trước cursor đã đi qua sẽ **không xuất hiện** trong các trang sau.

Do đó:

- Danh sách UI thường có thể chấp nhận một kết quả đang thay đổi.
- Export chính xác toàn bộ danh mục tại một mốc cần snapshot/job riêng.
- Cursor nên ghi scope tenant/filter/sort và có chính sách hết hạn.
- Không dùng OFFSET với dữ liệu thay đổi mạnh rồi hứa không bao giờ trùng/thiếu row.

### 17.5. Đọc category archived cho lịch sử

Endpoint public GET active có thể trả not found cho category archived. Nhưng đọc lịch sử order vẫn cần giải thích category cũ; nên có read path riêng, giới hạn quyền, hoặc snapshot lịch sử tại order.

Đừng xóa hard category để làm kết quả GET active trống: hành động đó có thể phá FK, báo cáo hoặc audit.

## 18. Bảo mật và ranh giới đa tenant

Danh mục có identity rõ ràng nhưng identity **không phải bí mật và không phải quyền truy cập**.

### 18.1. Không dùng ID từ client để tự xác thực tenant

Một request:

~~~text
PATCH /tenants/202/categories/C1
Authorization: token của tenant 101
~~~

Backend phải đối chiếu tenant path với security context. Nếu actor không có quyền tenant 202, từ chối trước khi truy vấn. Không chỉ lấy 202 từ URL rồi gọi repository.rename(202,...).

SQL vẫn cần WHERE tenant_id để giảm blast radius nếu ứng dụng sai hoặc dữ liệu có UUID trùng giữa tenant. Có thể dùng RLS trên PostgreSQL như lớp phòng thủ bổ sung, nhưng phải cấu hình DB role/session setting và connection pool chính xác; RLS không thay policy phân quyền ở API.

### 18.2. Không tiết lộ sự tồn tại của category tenant khác

Nếu category thuộc tenant B, API cho actor tenant A có thể trả 404 thay vì 403 để tránh tiết lộ identity tùy contract. Trong mọi trường hợp phải bảo đảm **không sửa** row tenant B. Kết quả repository empty khi WHERE tenant_id không khớp hỗ trợ che scope nhưng không thay xác thực principal.

### 18.3. Audit và dữ liệu nhạy cảm

Category thông thường không quá nhạy cảm, nhưng tenantId, tên nội bộ, người thực hiện và lịch sử sửa vẫn có thể là dữ liệu doanh nghiệp cần bảo vệ. Ghi audit ở mức cần thiết:

- Actor identity được xác thực, tenant, categoryId, commandId.
- Phiên bản cũ/mới và loại thao tác.
- Transaction/correlation ID để điều tra.
- Không ghi token, connection password hoặc dữ liệu bí mật vào error log.
- Phân biệt “đã yêu cầu” với “đã commit”; audit business event cần bám transaction đúng.

### 18.4. SQL injection và mã code đặc biệt

Dù code được regex ASCII, vẫn phải bind SQL parameter. Nếu sau này mở rộng cho mã quốc tế hoặc tên có dấu nháy, parameterization vẫn bảo vệ query. Không dùng input để tạo dynamic ORDER BY hoặc tên bảng trực tiếp; nếu cần sort tùy chọn, dùng whitelist field đã xác định.

## 19. Lỗi kết nối và giao dịch: contract phải nói gì khi kết quả chưa rõ?

### 19.1. Phân loại lỗi thực hành

| Lỗi | Nguồn phát hiện | Hướng xử lý |
|---|---|---|
| Duplicate PK/code | PostgreSQL UNIQUE, thường SQLSTATE 23505 | Conflict; đối chiếu idempotency key nếu replay |
| Invalid code/name | Validation và CHECK, có thể 23514/23502 | Không ghi; báo input/data error |
| Version mismatch | UPDATE ... WHERE version không khớp | Conflict/refresh, không ghi đè |
| Connection pool timeout | Pool không cấp connection đúng hạn | Infrastructure unavailable, deadline/bulkhead |
| Lock wait/cancel | DB/driver statement timeout | Xác định transaction outcome và rollback |
| Deadlock 40P01 | DB abort một transaction | Retry toàn transaction khi an toàn, có budget |
| Serialization 40001 | DB phát hiện serialization anomaly | Retry toàn transaction khi an toàn |
| Lỗi nhóm 08xxx | Lỗi connection | Có thể tạo outcome chưa rõ ở COMMIT |
| HTTP 504 sau create | Không có response upstream | Không suy DB chưa tạo category |

Lỗi không được gom hết thành NotFound; một read không trả kết quả vì DB unavailable khác bản ghi không tồn tại.

### 19.2. Retry phải có điểm dừng

Một policy retry nên có deadline tổng, số lần thử tối đa, exponential backoff với jitter, và chỉ áp dụng với lỗi/công việc được xác định có thể retry. Retry vô hạn khi DB đang quá tải có thể tạo retry storm làm hệ thống tệ hơn.

Đặc biệt, retry **toàn transaction** sau 40001/40P01 khác với retry riêng câu INSERT sau khi transaction đã bị abort. Với PostgreSQL, sau một lỗi SQL làm transaction ở trạng thái aborted, cần rollback và bắt đầu transaction mới.

### 19.3. Không mở transaction dài khi chờ dịch vụ khác

Nếu service mở transaction PostgreSQL, khóa row category rồi chờ một hệ thống bên ngoài, nó có thể giữ connection/lock lâu, làm tăng latency và deadlock. Khi cần đồng bộ search/broker, ghi outbox cùng local transaction và để worker xử lý sau commit, có idempotent consumer.

### 19.4. Failover và dữ liệu đã ACK

Với asynchronous replication, một commit được primary cũ ACK có thể không có trên replica mới nếu failover promote node chưa nhận commit. Đây là bài toán RPO/replication policy, không phải chỉ là “SELECT stale”. Hợp đồng persistence cần nêu giới hạn durability/availability được tổ chức cam kết; idempotency/reconciliation và backup/DR phải được thử tương ứng. Không tự cho rằng mọi cấu hình PostgreSQL bảo đảm RPO=0.

## 20. Tiến hóa schema mà không phá identity

Một category có identity ổn định thường sống lâu hơn một phiên bản ứng dụng. Khi mở rộng lược đồ, phải bảo toàn các reference, code alias nếu có và khả năng nhiều phiên bản service cùng hoạt động.

### 20.1. Expand → migrate → contract

~~~mermaid
flowchart LR
    A["Schema và app v1"] --> B["Expand cột/ràng buộc tương thích"]
    B --> C["Writer v2 cùng tồn tại v1"]
    C --> D["Backfill và reconciliation"]
    D --> E["Reader v2 + cutover"]
    E --> F["Contract sau quan sát"]
~~~

Ví dụ nếu bảng cũ chưa có description/version:

~~~sql
ALTER TABLE catalog_categories
ADD COLUMN description text;

ALTER TABLE catalog_categories
ADD COLUMN version bigint;
~~~

Đây mới là expand, chưa đủ cho contract hiện tại. Cần xác định dữ liệu version NULL của record cũ được xử lý thế nào, các writer cũ có tiếp tục UPDATE mà không tăng version không, và thời điểm đặt CHECK/NOT NULL.

**Rủi ro chính:** triển khai writer mới dùng version CAS trong khi writer cũ vẫn có thể sửa row không tăng version. Khi đó optimistic concurrency chỉ bảo vệ một phần traffic, có thể để lost update. Cần kiểm soát mọi writer hoặc thiết kế compatibility mechanism ở DB, thử race giữa nhiều phiên bản trước cutover.

### 20.2. Kiểm tra dữ liệu trước khi thêm UNIQUE/CHECK

~~~sql
SELECT tenant_id, code, COUNT(*) AS duplicate_count
FROM catalog_categories
GROUP BY tenant_id, code
HAVING COUNT(*) > 1;

SELECT tenant_id, id, code
FROM catalog_categories
WHERE code IS NULL
   OR code !~ '^[A-Z0-9][A-Z0-9_-]{1,39}$';

SELECT COUNT(*) AS missing_versions
FROM catalog_categories
WHERE version IS NULL;
~~~

Không tự đổi code của record có external references để làm migration pass. Hãy phân loại record legacy, mapping và cách xử lý xung đột theo nghiệp vụ. Backfill theo batch có checkpoint và replay idempotent, sau đó xác minh dữ liệu mới phát sinh trong lúc chạy cũng tuân thủ constraint.

### 20.3. Không thay categoryId khi đổi thuộc tính

Nếu một nhóm đổi tên, categoryId phải giữ nguyên để sản phẩm/report không bị đứt liên kết. Nếu có yêu cầu đổi code, cần bổ sung contract chuyển đổi code, alias lịch sử và cách xử lý URL/import cũ. Không tạo categoryId mới rồi xóa cái cũ chỉ để đổi code.

### 20.4. Migration và rollback

Các điều kiện trước khi bỏ field cũ:

- Mọi writer/reader đã hiểu representation mới.
- Có reconciliation theo key và các invariant cần bảo vệ.
- Không còn batch/ETL/consumer dùng field cũ.
- Có backup/restore đã thử, RPO/RTO và retention phù hợp.
- Rollback ứng dụng không đọc bản field cũ đã ngừng cập nhật.
- Có phương án forward fix nếu phát hiện mapping sai sau cutover.

Kết quả “migration tool applied” không thay thế kiểm tra dữ liệu committed và hành vi ứng dụng.

## 21. Kiểm thử trên PostgreSQL thật theo hợp đồng

Unit test của CategoryCode/CategoryValidation hữu ích, nhưng không chứng minh UNIQUE, transaction, row lock hoặc JDBC mapping. Những điều đó nên được kiểm tra bằng PostgreSQL thật với schema từ migration production.

### 21.1. Khung Testcontainers

~~~java
@SpringBootTest
@Testcontainers
class CategoryRepositoryIT {
    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void dbProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired CategoryRepository categories;
    @Autowired JdbcTemplate jdbc;
    @Autowired TransactionTemplate tx;

    @BeforeEach
    void clean() {
        // Chỉ dùng khi test sở hữu DB/schema riêng, không chạy song song.
        jdbc.execute("TRUNCATE TABLE catalog_categories CASCADE");
    }
}
~~~

Ví dụ là khung, cần imports/dependencies JUnit Jupiter, Spring Test/Jdbc, Testcontainers PostgreSQL/JUnit, migration và transaction manager đúng. Không chạy cleanup destructive trên production/staging chia sẻ; khi có FK hoặc nhiều test cùng DB, thiết kế fixture isolation thay vì TRUNCATE CASCADE tùy tiện.

### 21.2. Create: đúng identity và version

~~~java
@Test
void createStoresIdentityAndInitialVersion() {
    UUID id = UUID.randomUUID();

    CategoryRecord returned = categories.insert(
        new NewCategory(101L, id, "SACH", "Sách", null)
    );
    CategoryRecord stored =
        categories.findActiveById(101L, id).orElseThrow();

    assertEquals(id, returned.id());
    assertEquals(id, stored.id());
    assertEquals("SACH", stored.code());
    assertEquals("Sách", stored.displayName());
    assertEquals(0L, stored.version());
    assertNull(stored.deletedAt());
    assertNotNull(stored.createdAt());
}
~~~

Nếu test không có outer transaction, INSERT JdbcTemplate autocommit theo cấu hình thông thường và lần đọc kế tiếp có thể quan sát row đã commit. Với service @Transactional, phải gọi service qua proxy và xác nhận transaction kết thúc trước khi kiểm chứng committed state.

### 21.3. UNIQUE theo tenant

~~~java
@Test
void duplicateCodeInOneTenantIsRejected() {
    UUID first = UUID.randomUUID();
    UUID second = UUID.randomUUID();

    categories.insert(new NewCategory(
        101L, first, "SACH", "Sách", null
    ));
    assertThrows(DuplicateKeyException.class, () ->
        categories.insert(new NewCategory(
            101L, second, "SACH", "Tên khác", null
        ))
    );

    assertEquals(first, categories
        .findActiveByCode(101L, "SACH")
        .orElseThrow().id());
    assertTrue(categories.findActiveById(101L, second).isEmpty());
}
~~~

Nếu adapter dịch lỗi thành domain exception riêng, assert contract công khai của adapter thay vì bắt buộc Spring exception class. Cần thêm test cùng code ở hai tenant được phép và test cùng UUID hai tenant không lẫn khi tra cứu.

### 21.4. Rename chống stale version, không sửa code

~~~java
@Test
void renameUsesVersionWithoutChangingCode() {
    UUID id = UUID.randomUUID();
    categories.insert(new NewCategory(
        101L, id, "SACH", "Sách", null
    ));

    CategoryRecord renamed = categories.renameIfVersionMatches(
        101L, id, 0L, "Sách & Tạp chí", null
    ).orElseThrow();

    assertEquals("SACH", renamed.code());
    assertEquals("Sách & Tạp chí", renamed.displayName());
    assertEquals(1L, renamed.version());

    assertTrue(categories.renameIfVersionMatches(
        101L, id, 0L, "Ghi đè", null
    ).isEmpty());

    assertEquals("Sách & Tạp chí",
        categories.findActiveById(101L, id)
            .orElseThrow().displayName());
}
~~~

### 21.5. Archive giữ record lịch sử

~~~java
@Test
void archiveHidesActiveButKeepsRow() {
    UUID id = UUID.randomUUID();
    categories.insert(new NewCategory(
        101L, id, "DIENTU", "Điện tử", null
    ));

    CategoryRecord archived = categories
        .archiveIfVersionMatches(101L, id, 0L)
        .orElseThrow();

    assertNotNull(archived.deletedAt());
    assertEquals(1L, archived.version());
    assertTrue(categories.findActiveById(101L, id).isEmpty());
    assertTrue(categories.findActiveByCode(101L, "DIENTU").isEmpty());

    Long count = jdbc.queryForObject(
        """
        SELECT COUNT(*) FROM catalog_categories
        WHERE tenant_id = ? AND id = ?
        """,
        Long.class, 101L, id
    );
    assertEquals(1L, count);
}
~~~

Chỉ assert findActive empty không chứng minh “soft delete”: implementation vô tình DELETE vật lý cũng làm test ấy pass. Truy vấn row lịch sử giúp bảo vệ đúng semantics.

### 21.6. Transaction rollback

~~~java
@Test
void failedTransactionDoesNotPersistCategory() {
    UUID id = UUID.randomUUID();
    assertThrows(IllegalStateException.class, () ->
        tx.executeWithoutResult(status -> {
            categories.insert(new NewCategory(
                101L, id, "TX-TEST", "Thử nghiệm", null
            ));
            throw new IllegalStateException("Later step failed");
        })
    );

    assertTrue(categories.findActiveById(101L, id).isEmpty());
}
~~~

Test giả định tx dùng cùng DataSource/transaction manager và không bị một outer test transaction che commit. Nếu create cũng ghi outbox, gây lỗi bước outbox rồi kiểm tra cả hai bảng rollback.

## 22. Kiểm thử cạnh tranh, lỗi mạng và đường API

### 22.1. Hai rename cùng expectedVersion

~~~java
@Test
void competingRenamesCannotBothWin() throws Exception {
    UUID id = UUID.randomUUID();
    categories.insert(new NewCategory(
        101L, id, "RACE", "Ban đầu", null
    ));

    ExecutorService workers = Executors.newFixedThreadPool(2);
    CountDownLatch start = new CountDownLatch(1);

    try {
        Future<Boolean> first = workers.submit(() -> {
            start.await();
            return categories.renameIfVersionMatches(
                101L, id, 0L, "Tên A", null
            ).isPresent();
        });
        Future<Boolean> second = workers.submit(() -> {
            start.await();
            return categories.renameIfVersionMatches(
                101L, id, 0L, "Tên B", null
            ).isPresent();
        });

        start.countDown();
        boolean a = first.get(10, TimeUnit.SECONDS);
        boolean b = second.get(10, TimeUnit.SECONDS);

        assertTrue(a ^ b, "Exactly one mutation must succeed");

        CategoryRecord current = categories
            .findActiveById(101L, id).orElseThrow();

        assertEquals(1L, current.version());
        assertEquals(a ? "Tên A" : "Tên B",
                     current.displayName());
    } finally {
        workers.shutdownNow();
    }
}
~~~

Ví dụ cần import java.util.concurrent.* và JUnit assertion tương ứng. Fixture phải commit trước khi hai thread lấy connection riêng; pool cần đủ năng lực. Latch chỉ đồng bộ thời điểm bắt đầu, không kiểm soát chính xác lịch lock, nhưng assertion “không hai update cùng thắng từ version 0” vẫn có giá trị.

### 22.2. Rename cạnh tranh với Archive

Hai task dùng cùng expectedVersion=0, một rename và một archive. Kỳ vọng chỉ một mutation thành công:

- Rename thắng: record active version=1, tên mới.
- Archive thắng: record archived version=1, getActive empty.
- Không có trạng thái cả hai thao tác cùng trả success với version=0.
- Dữ liệu tenant khác dù trùng UUID không đổi.

### 22.3. Test SQL scope theo tenant

Tạo category cùng UUID ở tenant 101 và 202 nhưng tên khác nhau. Assert:

- findActiveById(101,id) trả row tenant 101.
- findActiveById(202,id) trả row tenant 202.
- rename(101,id,...) chỉ đổi tenant 101.
- archive(202,id,...) không ảnh hưởng tenant 101.
- API với principal không có quyền không thể đổi tenant path để thao tác.

### 22.4. Test idempotency sau COMMIT mất ACK

Trong môi trường fault injection có điều khiển:

~~~text
Request R tới API
  -> DB ghi category C1 + request key R
  -> COMMIT thành công
  -> Chặn response trên đường về
Client thấy timeout
Client retry R với cùng payload
  -> API đọc request R từ primary
  -> Trả C1, không tạo C2
~~~

Không coi test ngắt socket ngẫu nhiên là đã tái hiện chính xác “commit rồi mất ACK”. Cần xác minh transaction thực sự commit trước khi chặn response, hoặc giới hạn kết luận của test đúng với cửa sổ đã thử.

### 22.5. Bảng kiểm thử lỗi

| Tình huống | Assertion |
|---|---|
| Code sai regex | Validation/DB constraint từ chối, không tạo row |
| Trùng code trong cùng tenant | Một row được lưu, không overwrite |
| Cùng code khác tenant | Hai row hợp lệ |
| Rename với version cũ | 0 row thay đổi, version hiện hành giữ nguyên |
| Rename và archive tranh chấp | Chỉ một transition thành công |
| Archive lặp | Không thay đổi thêm, không tăng version lần hai |
| FK reference lịch sử | Archive không phá link, hard delete được kiểm soát |
| Outbox INSERT thất bại | Category + outbox rollback cùng nhau |
| Query pool timeout | Lỗi hạ tầng, không trả not found |
| DB COMMIT ACK mất | Outcome unknown, replay theo key an toàn |
| Replica lag | Read-after-write đi theo freshness contract |
| Schema migration giữa hai phiên bản | Không có writer phá version invariant |
| Restore backup | Category ID/code/reference vẫn nhất quán |

### 22.6. Hợp đồng HTTP độc lập repository

Một API có thể chọn:

| Request | Thành công | Lỗi điển hình |
|---|---|---|
| POST /categories + idempotency key | 201/response replay theo contract | 400 input, 409 duplicate/khác payload |
| GET /categories/{id} | 200 nếu active | 404 khi missing/archived/không được phép tiết lộ |
| GET /categories?after=... | 200 list với next cursor | 400 limit/cursor không hợp lệ |
| PATCH /categories/{id} với If-Match | 200/204, version tăng | 412 stale precondition; 404 theo policy |
| DELETE /categories/{id} với If-Match | 204 hoặc representation archive | 412/404 theo policy |

ETag/If-Match cần ánh xạ expectedVersion chính xác và kiểm tra tại database. Một HTTP DELETE có thể idempotent về effect dù hai lần gọi trả status khác nhau; không ép repository.archive luôn return success khi row đã archived nếu contract repository đã chọn false/empty.

## 23. Tối ưu hiệu năng và quan sát ranh giới lưu trữ

Thiết kế đúng mà không xét tải có thể khiến cả đường ghi lẫn đường đọc quá chậm. Nhưng tối ưu phải dựa trên mẫu truy cập, không thêm index và cache chỉ vì “có thể nhanh hơn”.

### 23.1. Những truy vấn chính

| Query | Access path mong muốn | Cần đo |
|---|---|---|
| Find by tenant+ID | PRIMARY KEY (tenant_id,id) | p95/p99, rows scanned |
| Find by tenant+code | UNIQUE(tenant_id,code) | Selectivity, index usage |
| List active after code | Range trên code và lọc active | Sort cost, LIMIT, page size |
| List recent active | Partial index (tenant_id,updated_at,id) | Buffer reads, index size |
| Rename/Archive by version | Seek row theo PK rồi kiểm tra version | Row locks, deadlocks, throughput |
| Read category history | Tenant+ID kể cả archived | Authorization, retention |

Nếu một tenant rất lớn và nhiều tenant nhỏ, chỉ số trung bình toàn hệ có thể che truy vấn chậm ở tenant lớn. Đánh giá phân bố kích thước dữ liệu và query plans.

### 23.2. Đọc execution plan

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, code, display_name, version
FROM catalog_categories
WHERE tenant_id = 101
  AND deleted_at IS NULL
  AND code > 'SACH'
ORDER BY code ASC
LIMIT 50;
~~~

EXPLAIN ANALYZE thực sự chạy SELECT. Chỉ chạy trên dữ liệu/điều kiện phù hợp, đọc các mốc buffer, rows, timing và sort/index scan. Không assert exact execution-plan text trong test vì planner thay đổi theo thống kê, cardinality và PostgreSQL version.

### 23.3. Connection pool là tài nguyên hữu hạn

Giả sử có 15 instance, mỗi instance cấp tối đa 20 physical connections; riêng service đã có khả năng tạo tới 300 connection trước khi tính job/migration/admin. Database max_connections, memory, CPU và workload transaction phải được capacity-plan. Một test tạo pool mới mỗi request có thể làm hệ thống cạn connection mà không liên quan thiết kế index.

Kiểm soát:

- Kích thước pool và số worker/instance.
- Connection acquisition timeout, statement timeout và transaction deadline.
- Không giữ transaction/row lock khi gọi external HTTP/KMS/broker.
- Circuit breaker/bulkhead bảo vệ primary khi read replica hỏng và tất cả GET fallback.
- Retry budget để không biến lỗi ngắn thành bão request.

### 23.4. Metrics có giá trị chẩn đoán

- Create/rename/archive success, duplicate, conflict, invalid input.
- SQLSTATE theo nhóm lỗi, rollback và transaction timeout.
- Pool active/idle/pending/acquisition latency.
- Query latency p50/p95/p99 theo operation và tenant size class.
- Optimistic-lock conflicts theo thao tác.
- Outbox pending/retry/duplicate delivery và consumer lag.
- Cache hit/stale detection, replica replay lag khi có.
- Migration backlog, constraint mismatches và số request-key replay.
- Restore rehearsal success, RPO/RTO quan sát được.

Không dùng category code hay payload nhạy cảm làm metric label có cardinality vô hạn; khi cần tìm record, dùng trace ID/audit theo quyền phù hợp.

### 23.5. Backup và dữ liệu có định danh

Backup không chỉ cần restore được bảng categories; còn phải giữ reference tới products, aliases/outbox và lịch sử đủ để giải thích các giao dịch. Một restore thử phải kiểm tra:

- Khóa (tenant,id) và UNIQUE code không bị phá.
- FK sang category vẫn hợp lệ.
- Archive semantics không biến historical category thành missing.
- Schema/migration version khớp binary khôi phục.
- Quyền truy cập và connection TLS được cấu hình lại phù hợp.
- Những ghi nhận từ sau snapshot có mất theo RPO dự kiến không.

### 23.6. Không tối ưu bằng cách phá contract

Một số cách tối ưu sai:

- Bỏ WHERE tenant_id để tận dụng index có vẻ nhanh.
- Bỏ version check vì update tranh chấp tăng latency.
- Chuyển mọi đọc sang replica mà vẫn hứa read-your-writes.
- Cache mutable entity toàn cục dùng chung giữa tenant.
- Hard delete archive row cho nhẹ bảng dù sản phẩm lịch sử cần tham chiếu.
- Nuốt lỗi timeout rồi trả Optional.empty() để API “nhanh”.

Hiệu năng là một phần của contract vận hành, nhưng không được mua bằng mất an toàn dữ liệu hoặc vi phạm invariant.

## 24. Case study xuyên suốt: từ yêu cầu tới trạng thái committed

### 24.1. Bước 1 — Tạo danh mục

Actor thuộc tenant 101 muốn tạo SACH:

~~~text
POST /categories
Idempotency-Key: 7c4183b2-7670-48a4-a3df-9facce52e45f

Body: code=" sach ", displayName="Sách"
~~~

Service xác thực actor, xác định tenant=101, chuẩn hóa code SACH, validate tên, cấp categoryId C1, ghi category và idempotency record trong cùng transaction. Sau khi COMMIT thành công, caller nhận response chứa:

~~~json
{
  "id": "4d9b5006-3c83-4f59-89a7-24ebfe777311",
  "code": "SACH",
  "displayName": "Sách",
  "version": 0,
  "archived": false
}
~~~

UUID/Idempotency-Key trong ví dụ là minh họa; hệ thống thật cần phát request key hợp lệ, phân scope tenant và xác minh identity theo auth context. Không gửi HTTP 201 từ trong transaction trước khi transaction owner hoàn tất nếu API cam kết ghi đã được xác nhận.

### 24.2. Bước 2 — Tra theo ID và code

GET theo (tenant=101,id=C1) và GET theo code SACH phải cùng trỏ đến C1, miễn cùng nguồn đọc đã bắt kịp commit. Ở tenant 202, SACH có thể trỏ category khác, tuyệt đối không trả C1.

Nếu một read replica chưa replay, use case cần read-your-writes phải đọc primary hoặc có watermark/version protocol; không đoán POST rollback từ response GET cũ.

### 24.3. Bước 3 — Đổi tên có kiểm tra version

Actor A đọc category version=0, gửi Rename với expectedVersion=0 thành “Sách & Tạp chí”. UPDATE có điều kiện và COMMIT thành công: categoryId C1, code SACH vẫn vậy, displayName mới, version=1.

Actor B gửi Rename với expectedVersion=0 thành “Sách thiếu nhi” sau đó: UPDATE trả 0; API theo contract trả precondition failed/conflict hoặc hướng dẫn refresh. Không ghi đè tên A.

### 24.4. Bước 4 — Archive nhưng không mất tham chiếu

Một product lịch sử đang giữ categoryId C1. Actor hợp lệ archive C1 với expectedVersion=1:

~~~text
Category C1: deletedAt != NULL, version=2
GET active category C1 -> không trả
Link product -> C1 vẫn tồn tại ở DB
Historical report -> có thể giải thích nhóm cũ
Create category code=SACH khác -> UNIQUE từ chối
~~~

Nếu business muốn ngăn tạo link product mới tới archived C1, cần kiểm tra active theo protocol giao dịch phù hợp, không chỉ dựa vào FK.

### 24.5. Bước 5 — Một request tạo khác bị timeout

Client gửi Create mã PHUKIEN với key R2. COMMIT hoàn tất nhưng response mất. Client retry với **cùng R2 và cùng payload**; service trả categoryId đã lưu. Nếu client dùng R3 mới và server tạo UUID mới, UNIQUE(code) có thể ngăn trùng code nhưng không thay thế policy trả replay result.

### 24.6. Bước 6 — Đổi schema

Nhà phát triển muốn bổ sung search_label. Quy trình expand/backfill/validate/reader cutover phải giữ C1 và những UUID khác ổn định, bảo đảm code uniqueness và version CAS trong toàn bộ giai đoạn mixed versions. Chỉ sau đối soát và quan sát mới contract phần legacy.

### 24.7. Tiêu chí nghiệm thu case study

| Điều kiện | Bằng chứng |
|---|---|
| Identity ổn định | UUID giữ nguyên qua rename/archive |
| Uniqueness | Một (tenant,code) duy nhất, kể cả archived |
| Tenant isolation | Không read/mutate row tenant khác |
| Optimistic concurrency | Hai writer cùng expectedVersion chỉ một thắng |
| Atomicity | Category + outbox/idempotency cùng COMMIT/ROLLBACK |
| Retry safety | Một request key tạo tối đa một effect nghiệp vụ |
| Read semantics | Active query lọc archived; historical read có policy |
| Reference safety | FK không orphan vì archive; liên kết mới theo contract |
| Durability/visibility | Return sau transaction boundary; read-your-writes rõ |
| Performance | Chỉ mục phù hợp, bounded page, pool có giới hạn |
| Evolution | Migration tương thích và reconciliation đạt |
| Recovery | Restore giữ identity, liên kết và schema version |

## 25. Anti-pattern và những đánh đổi cần nói rõ

| Anti-pattern | Vì sao nguy hiểm | Quyết định phù hợp hơn |
|---|---|---|
| Dùng displayName làm khóa chính | Đổi tên phá reference và lịch sử | UUID ổn định, tên mutable |
| Dùng code toàn cục không có tenant | Tenant khác nhau bị va chạm | UNIQUE(tenant_id,code) |
| Cho phép code thay đổi tùy ý | External link, import và audit có thể trỏ sai | Code immutable hoặc alias/migration chính thức |
| Tái sử dụng code archived mà không có policy | Mã cũ bị hiểu là category mới | Chốt UNIQUE cho cả archived hoặc chính sách alias |
| Repository.save(Entity) là contract duy nhất | Không rõ create/update, version, commit, lỗi | Method theo intent và kết quả cụ thể |
| SELECT trước rồi INSERT để tránh duplicate | Race giữa các request song song | UNIQUE tại DB; xử lý conflict |
| Rename không expectedVersion | Lost update | CAS theo version |
| Archive bằng DELETE vật lý | FK và lịch sử bị mất | Soft delete có semantics rõ |
| FK bảo đảm category còn active | FK chỉ kiểm tra row tồn tại | Kiểm tra trạng thái với transaction/locking phù hợp |
| Bắt mọi exception trả empty | DB lỗi bị giả làm not found | Phân loại absence và infrastructure |
| Trả 201 khi entity đã có UUID | UUID có thể sinh trước COMMIT | Phát success theo transaction boundary |
| Retry create với UUID mới khi timeout | Duplicate ý định nếu lần đầu commit | Idempotency key bền vững |
| Update cache trước DB commit | Cache có thể chứa dữ liệu chưa từng commit | Invalidation/outbox/after-commit policy |
| GET qua replica rồi luôn hứa mới nhất | Replica có lag | Primary hoặc watermark/freshness contract |
| Dùng OFFSET và hứa không thiếu row | Trang đổi khi dữ liệu biến động | Keyset hoặc snapshot job tùy yêu cầu |
| Mỗi request tạo một connection pool | Cạn DB connections | Pool chia sẻ theo lifecycle |
| Đọc code từ request làm tenant identity | Bị truy cập chéo tenant | Authenticated tenant context + SQL scoping |
| Migration chỉ chạy DDL, không đối soát | Row legacy sai/lệch pha writer | Expand/backfill/validate/cutover |
| Không test lỗi COMMIT/rollback | Test xanh dù API tạo event sai | Fault injection, outbox và readback |
| Bỏ index và bảo SQL chậm là do Java | Không đọc plan/workload | EXPLAIN và capacity planning |
| Thêm mọi index để “tối ưu” | Tăng WAL/chi phí ghi và storage | Index theo truy vấn, đo trước/sau |

### 25.1. Quyết định: mã có thể đổi hay không?

Giữ code immutable giúp đơn giản hóa reference/uniqueness và giảm rủi ro khi đổi tên; đổi lại doanh nghiệp phải tạo alias hoặc category mới cho những thay đổi mã hợp lệ. Với các hệ thống mà code do bên ngoài cấp và thường xuyên thay, immutable code có thể không đáp ứng yêu cầu. Khi ấy contract phải mở rộng để quản lý mã hiện hành, mã lịch sử và hiệu lực theo thời gian.

### 25.2. Quyết định: khóa global hay composite?

Nếu dùng UUID global unique làm PRIMARY KEY(id) và có tenant_id chỉ để phân quyền, mọi foreign key vẫn cần cách bảo đảm không tham chiếu chéo tenant. Composite PRIMARY KEY(tenant_id,id) giúp biểu diễn scope ngay tại DB, nhưng khiến foreign key và index phức tạp hơn. Không có lựa chọn duy nhất cho mọi hệ; điều bắt buộc là mọi query/reference/API **nhất quán** với identity model đã chọn.

### 25.3. Quyết định: archival hay hard delete?

Soft delete giữ identity và khả năng giải thích lịch sử nhưng tăng nhu cầu filter, index, retention và cleanup. Hard delete giảm dữ liệu đang lưu nhưng có thể phá reference hoặc làm phức tạp nghĩa vụ audit, backup và xóa dữ liệu. Chọn theo domain, quy định dữ liệu và mục tiêu vận hành, không theo phương thức repository thuận tiện hơn.

## 26. Bài tập tự kiểm tra

### Bài A — Trùng mã giữa hai tenant

Tenant 101 và 202 cùng muốn tạo code SACH. Trong tenant 101 đã có category khác code SACH.

**Hỏi:** Những thao tác nào được chấp nhận? Ràng buộc DB nào làm quyết định này bền vững?

**Gợi ý:** Tenant 202 được tạo; tạo thêm SACH ở tenant 101 bị từ chối. UNIQUE(tenant_id,code) bảo vệ cả khi nhiều writer đồng thời.

### Bài B — Đổi tên có làm đổi identity?

Category C1 mã SACH đổi displayName từ “Sách” sang “Sách & Tạp chí”.

**Hỏi:** ID, code, version và link sản phẩm nên thay đổi thế nào?

**Gợi ý:** Giữ ID và code; tăng version một lần khi commit; link vẫn trỏ C1. Chỉ các field mutable được phép đổi.

### Bài C — Hai người cùng sửa

A và B đọc category version=8. A rename thành công. B gửi rename với expectedVersion=8.

**Hỏi:** Nếu B vẫn update thành công là lỗi gì?

**Gợi ý:** Có nguy cơ lost update. Dùng UPDATE WHERE version=8 và tăng version; B cần conflict/refresh nếu row đã lên version=9.

### Bài D — Archive và liên kết

Một sản phẩm lịch sử đang trỏ category C1. Actor archive C1.

**Hỏi:** FK có mất hiệu lực không? Product có nên biến mất khỏi report lịch sử?

**Gợi ý:** Với soft delete, row C1 vẫn tồn tại nên FK còn hợp lệ. Report lịch sử có thể đọc archived category hoặc snapshot lúc giao dịch; lọc category active cho mọi JOIN sẽ làm mất ngữ cảnh lịch sử.

### Bài E — Create lặp sau timeout

Client tạo category với request R1, DB commit nhưng response mất. Client retry với R2 và UUID mới.

**Hỏi:** UNIQUE code có đủ thay idempotency không?

**Gợi ý:** Không. Nó có thể ngăn trùng cùng code, nhưng không định nghĩa result replay hay payload mismatch. Client phải giữ stable request key; lưu key và business effect atomically.

### Bài F — Truy vấn theo tên để update

Một developer muốn dùng displayName để xác định category khi rename.

**Hỏi:** Vì sao cách đó yếu hơn ID?

**Gợi ý:** Tên có thể không duy nhất, có thể đổi và có quy tắc Unicode/locale phức tạp. Cần identity ổn định và scope tenant.

### Bài G — List khi có insert mới

Trang 1 trả A01, A02; client giữ cursor A02. Ngay sau đó có một category mới mã A015.

**Hỏi:** Trang 2 có bắt buộc trả A015 không?

**Gợi ý:** Không với keyset theo code > A02. API danh sách đang biến động cần nói rõ eventual listing; export snapshot là hợp đồng khác.

### Bài H — Phân biệt not found và lỗi DB

findActiveById bị timeout nhưng adapter bắt tất cả exception rồi trả Optional.empty().

**Hỏi:** Vì sao API 404 có thể nguy hiểm?

**Gợi ý:** Record có thể tồn tại; DB chỉ không trả kết quả. Cần giữ lỗi infrastructure riêng để tránh retry tạo lại, xóa cache hoặc thông báo sai nghiệp vụ.

### Bài I — FK và xóa mềm

Bảng link có FK tới category. Một transaction archive category, transaction khác tạo link mới.

**Hỏi:** FK có bảo đảm link chỉ trỏ tới category active không?

**Gợi ý:** Không. Row archived vẫn tồn tại; cần policy trạng thái và kiểm tra/locking cùng transaction nếu invariant này bắt buộc.

### Bài J — Mutation ở Java nhưng chưa COMMIT

Service gọi INSERT RETURNING và nhận CategoryRecord version=0, sau đó outbox INSERT thất bại.

**Hỏi:** Có thể báo category đã lưu không?

**Gợi ý:** Không. Nếu cùng transaction, rollback phải xóa cả business row và outbox; giá trị object trả từ RETURNING chỉ thuộc statement chưa commit.

### Bài K — Nhiều writer trong migration

App v2 đã dùng expectedVersion, nhưng một worker v1 vẫn UPDATE display_name mà không tăng version.

**Hỏi:** CAS của v2 còn đảm bảo chống mất thay đổi không?

**Gợi ý:** Không đầy đủ. Worker v1 làm dữ liệu đổi mà version không đổi; cần chấm dứt hoặc điều phối writer cũ trước khi dựa trên invariant version.

### Bài L — Điểm đo hiệu năng

Một API list chậm khi một tenant có 2 triệu category và 100 tenant khác chỉ có vài chục row.

**Hỏi:** Cần đo/thiết kế gì?

**Gợi ý:** Xem EXPLAIN với workload đại diện, index theo tenant/code và filter, bounded page, pool, transaction duration; không dựa vào latency trung bình của mọi tenant.

## 27. Checklist hoàn thành bài thực hành

### Identity và hợp đồng dữ liệu

- [ ] Đã chọn identity ổn định và giải thích phạm vi tenant.
- [ ] Đã phân biệt UUID, code, displayName và các field chỉ hiển thị.
- [ ] UNIQUE, CHECK, FK phản ánh invariant thiết yếu.
- [ ] Đã chốt code có được đổi/tái sử dụng sau archive hay không.
- [ ] Có policy cho category archived và tham chiếu lịch sử.
- [ ] Đã chốt phiên bản và optimistic concurrency của từng mutation.
- [ ] Repository port diễn đạt Create/Get/List/Rename/Archive rõ ràng.
- [ ] Thất bại UPDATE 0 row có cách diễn giải được công bố.
- [ ] Có định nghĩa no-op rename có tăng version hay không.
- [ ] Có contract read-after-write và nguồn authoritative.

### Triển khai persistence

- [ ] Mọi SQL đọc/ghi có WHERE tenant_id khi cần.
- [ ] Dùng bind parameters, không nối input vào SQL.
- [ ] Schema dùng migrations versioned, không tự suy từ Java annotation.
- [ ] Không dùng Save của ORM làm bằng chứng COMMIT.
- [ ] DB-generated timestamps/value được map và test đúng.
- [ ] UPDATE/ARCHIVE có WHERE expectedVersion và trạng thái active.
- [ ] Transaction owner, propagation và rollback rule được xác định.
- [ ] Outbox và business change commit/rollback atomically nếu cùng DB.
- [ ] Không gọi hệ ngoài lâu trong transaction DB.
- [ ] Có kiểm soát connection pool và retry budget.

### Bảo mật, lỗi và dữ liệu phân tán

- [ ] Tenant từ security context đáng tin, không từ client tự khai.
- [ ] API test read/write không lộ hoặc đổi dữ liệu tenant khác.
- [ ] Validation và constraint của DB đồng nhất theo contract.
- [ ] Không đổi lỗi hạ tầng thành not found.
- [ ] Có xử lý lost ACK/ambiguous commit theo yêu cầu.
- [ ] Có idempotency key nếu API hứa retry an toàn.
- [ ] Replica/cache có freshness/invalidation policy rõ.
- [ ] Không tạo trạng thái cache/event “committed” trước transaction boundary.
- [ ] Có quyền kiểm soát read historical/archived và retention.
- [ ] RPO/RTO và failover semantics được tài liệu hóa, không mặc định bằng 0.

### Kiểm thử, vận hành và tiến hóa

- [ ] Có integration test PostgreSQL với schema migration thực.
- [ ] Test create, duplicate, tenant scope, rename, archive và readback.
- [ ] Test 0 row update không làm thay đổi dữ liệu hiện hành.
- [ ] Test hai concurrent writers dùng cùng expectedVersion.
- [ ] Test rollback sau bước ghi đầu và outbox failure.
- [ ] Test idempotent replay sau mất ACK nếu có contract.
- [ ] Test pagination/filter/sort với dữ liệu đang biến động.
- [ ] Query plan và index được đánh giá theo workload.
- [ ] Có metrics về latency, pool, SQLSTATE, conflict và outbox.
- [ ] Migration mixed-version writer và backfill được kiểm tra.
- [ ] Backup/restore thử giữ identity, FK và schema version.
- [ ] Không thao tác thử nghiệm destructive trên môi trường dùng chung.

## 28. Kết luận

Một **danh mục có định danh** không chỉ là tập row có tên. Nó là một tập entity được tham chiếu lâu dài, với identity và uniqueness rõ, quyền sở hữu theo tenant, vòng đời có thể giải thích, các thao tác ghi có điều kiện, lỗi được phân loại và khả năng phục hồi khi môi trường không thuận lợi.

Bài thực hành chỉ hoàn tất về mặt thiết kế khi có thể trả lời:

1. **Cái gì làm nên cùng một category?** ID, tenant và các field mutable được phân biệt rõ.
2. **Database bảo vệ invariant nào?** PRIMARY KEY, UNIQUE, CHECK, FK và transaction/locking được dùng có chủ đích.
3. **Một request thành công cam kết điều gì?** Statement, COMMIT, read freshness và event delivery không bị trộn lẫn.
4. **Điều gì xảy ra khi hai writer hoặc một retry cùng đến?** Version, uniqueness, idempotency và error contract đủ để bảo vệ dữ liệu.
5. **Ai kiểm chứng được điều đó?** Integration tests trên PostgreSQL, concurrency/fault-injection tests, metrics và restore drill cung cấp bằng chứng.

**Ghi nhớ:** thiết kế hợp đồng lưu trữ tốt bắt đầu từ ý nghĩa của identity và invariant trong nghiệp vụ, sau đó mới chọn schema, repository và SQL. Dữ liệu chỉ thực sự đáng tin khi hợp đồng đó còn đúng qua transaction, concurrency, retry, read replica, schema evolution và phục hồi sự cố.

