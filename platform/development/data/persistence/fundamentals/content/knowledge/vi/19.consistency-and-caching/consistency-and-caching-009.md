# Tính nhất quán giữa bảng chính, dữ liệu dẫn xuất và chỉ mục tìm kiếm

Một dịch vụ Java có thể lưu sản phẩm trong bảng `products`, duy trì bảng tổng hợp để phục vụ màn hình quản trị, đồng thời đưa tên và mô tả sản phẩm vào một công cụ tìm kiếm. Khi người dùng đổi giá từ 200.000 đồng thành 180.000 đồng, dữ liệu ở ba nơi có thể **không thay đổi cùng lúc**. Nếu tìm kiếm vẫn trả giá cũ, hoặc một sản phẩm đã bị xóa vẫn xuất hiện trong kết quả, hệ thống đang gặp vấn đề **nhất quán giữa nguồn dữ liệu chính và dữ liệu dẫn xuất**.

Không phải mọi trường hợp lệch tạm thời đều là lỗi thiết kế: một hệ thống có thể chấp nhận *eventual consistency* (nhất quán cuối cùng) cho tìm kiếm và vẫn yêu cầu **giao dịch mạnh** khi đặt hàng, giữ tồn kho hoặc tính tiền. Vấn đề là xác định rõ hợp đồng đúng đắn, độ trễ tối đa chấp nhận được, cách truyền thay đổi, cơ chế khôi phục khi sự kiện bị gửi lặp hoặc xử lý sai thứ tự, và cách phát hiện dữ liệu đã lệch lâu.

Bài thuộc chương **Nhất quán và cache** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Người học kết nối kiến thức về persistence trong Java, schema, giao dịch, cô lập, đồng thời, quản lý kết nối, xử lý lỗi và tối ưu hiệu năng để thiết kế những luồng dữ liệu có thể giải thích, kiểm thử và vận hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **nguồn sự thật** (*source of truth*), **dữ liệu dẫn xuất** (*derived data*), cache, materialized view và **chỉ mục tìm kiếm** (*search index*).
2. Giải thích sự khác nhau giữa nhất quán trong **một transaction của cùng DBMS** và nhất quán giữa nhiều hệ thống.
3. Nêu được các tình huống dữ liệu lỗi thời, sự kiện thất lạc, gửi lặp, đến sai thứ tự và chỉ mục chứa tài liệu đã xóa.
4. Thiết kế việc cập nhật dữ liệu chính và outbox trong cùng giao dịch, sau đó đồng bộ bất đồng bộ đến công cụ tìm kiếm.
5. Sử dụng **event ID**, **aggregate version**, idempotency và quy tắc nhận phiên bản mới hơn để ngăn cập nhật ngược.
6. Chọn chiến lược cho delete/tombstone, backfill/reindex, kiểm tra chênh lệch và sửa dữ liệu.
7. Thiết kế API đọc có hợp đồng rõ ràng về độ mới dữ liệu (*freshness*), nhất quán sau ghi và hành vi khi hệ tìm kiếm chậm.
8. Đo lường độ trễ đồng bộ, tồn đọng sự kiện, lỗi projection và độ lệch giữa các nguồn dữ liệu.

## 2. Bốn khái niệm không nên đánh đồng

### 2.1. Bảng chính: nguồn sự thật

**Nguồn sự thật** là nơi hệ thống lựa chọn làm căn cứ có thẩm quyền cho một loại dữ liệu. Ví dụ:

~~~sql
CREATE TABLE products (
    id          BIGINT PRIMARY KEY,
    name        TEXT NOT NULL,
    price       NUMERIC(14, 2) NOT NULL CHECK (price >= 0),
    is_deleted  BOOLEAN NOT NULL DEFAULT FALSE,
    version     BIGINT NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Nếu `products` được định nghĩa là nguồn sự thật, những quyết định nghiệp vụ quan trọng như đơn hàng được chấp nhận với giá nào phải dựa vào quy tắc và giao dịch liên quan đến nguồn dữ liệu này (hoặc snapshot giá đơn hàng đã được xác nhận theo nghiệp vụ). Không nên coi một kết quả tìm kiếm có thể chậm đồng bộ là cơ sở cuối cùng để trừ tiền hoặc ghi hóa đơn.

**Nguồn sự thật không nhất thiết là một bảng duy nhất.** Với một miền nghiệp vụ phức tạp, trạng thái có thẩm quyền có thể gồm nhiều bảng và ràng buộc trong một database. Cần nêu rõ **ai có quyền ghi** và **dữ liệu nào được phép tái tạo**.

### 2.2. Dữ liệu dẫn xuất: tính hoặc biến đổi từ nguồn chính

Dữ liệu dẫn xuất có thể là:

- Bảng `product_search_projection` chứa văn bản tìm kiếm đã chuẩn hóa.
- Bảng `daily_sales_summary` chứa doanh thu tổng hợp theo ngày.
- Bảng thống kê số đơn theo trạng thái.
- Giá trị đọc tối ưu cho API, chẳng hạn DTO kết hợp nhiều bảng.
- Bộ đệm chứa kết quả truy vấn hoặc một phần entity.
- Tài liệu trong hệ tìm kiếm toàn văn.

Điểm chung là dữ liệu **có thể được tái tạo về mặt logic** từ nguồn có thẩm quyền, nếu biết đúng quy tắc và các dữ kiện cần thiết. Khả năng tái tạo phải được thiết kế thực tế: nếu projection phụ thuộc dữ liệu lịch sử đã bị xóa mà nguồn không còn giữ, việc rebuild sẽ không đầy đủ.

### 2.3. Chỉ mục B-tree trong DBMS khác chỉ mục tìm kiếm bên ngoài

Một **chỉ mục quan hệ** như PostgreSQL B-tree trên `products(name)` là cấu trúc do DBMS quản lý. Thay đổi bảng và cập nhật chỉ mục thường tham gia cơ chế transaction/khôi phục của cùng DBMS, theo ngữ nghĩa truy vấn và cô lập của hệ quản trị đó.

Một **search index bên ngoài** như một tập tài liệu phục vụ full-text search có vòng đời, API ghi, cơ chế refresh, bản sao, lỗi mạng và thời gian xử lý riêng. Nó **không mặc nhiên** tham gia transaction của PostgreSQL.

| Đối tượng | Dùng để làm gì? | Cơ chế cập nhật điển hình | Có cùng transaction với bảng chính không? |
|---|---|---|---|
| Chỉ mục B-tree của bảng `products` | Tăng tốc lọc, JOIN, sắp xếp phù hợp | DBMS duy trì khi ghi bảng | Thường có cùng tính nguyên tử/hiển thị giao dịch của DB |
| `VIEW` quan hệ thông thường | Định nghĩa truy vấn logic từ bảng khác | Tính khi truy vấn view | Đọc theo ngữ nghĩa transaction của DB |
| Bảng projection riêng trong cùng DB | Đọc tối ưu, giảm JOIN/tính lại | Application SQL, trigger hoặc job | **Có thể**, nếu cùng transaction; không tự động |
| Materialized view | Lưu kết quả đã tính để đọc nhanh | Refresh theo chính sách DBMS | Không tự đồng bộ với mọi thay đổi nguồn |
| Cache trong JVM/Redis | Truy cập giá trị nhanh | TTL, invalidation, write-through hoặc async | Thường **không** có transaction chung với bảng chính |
| Chỉ mục tìm kiếm ngoài DB | Full-text, ranking, filter, faceting | API indexing/CDC/event pipeline | Thường **không** có transaction chung |

Tên gọi “index” không đủ để suy ra bảo đảm nhất quán. **DB index** là một phần của cơ chế lưu trữ DBMS; **external search index** thường là một bản sao dẫn xuất với hợp đồng đồng bộ riêng.

### 2.4. Cache không phải nguồn sự thật trừ khi được thiết kế như vậy

Nếu Redis giữ `product:42 -> price=200000` trong khi bảng chính đã cập nhật thành `180000`, giá trị Redis là **bản sao lỗi thời** theo thiết kế cache-aside hoặc chính sách cập nhật đã chọn. Cần quy định lúc nào và bằng cơ chế nào cache được làm mới hoặc xóa.

Không nên tự động tin rằng một cache có TTL ngắn “đủ nhất quán” cho mọi nghiệp vụ: TTL chỉ giới hạn vòng đời của một entry theo chính sách cache, không bảo đảm rằng ngay sau commit không có giá trị cũ, đặc biệt khi có request chạy đồng thời.

## 3. Ví dụ xuyên suốt: cập nhật sản phẩm và tìm kiếm

Một hệ thống thương mại điện tử có ba hình thức dữ liệu:

~~~text
PostgreSQL (nguồn chính)
  products(id, name, price, is_deleted, version, updated_at)
           |
           +----> Bảng projection ở PostgreSQL (nếu cần)
           |
           +----> Outbox / CDC ---> Search index
                                     product document {
                                       id, name, price,
                                       searchableText, version
                                     }
~~~

Người bán đổi tên sản phẩm ID 42:

~~~text
Trước cập nhật:
  products:      id=42, name="Bàn gỗ",  version=7
  search index:  id=42, name="Bàn gỗ",  version=7

Sau COMMIT ở PostgreSQL:
  products:      id=42, name="Bàn gỗ sồi", version=8
  search index:  id=42, name="Bàn gỗ",     version=7

Sau khi đồng bộ thành công:
  products:      id=42, name="Bàn gỗ sồi", version=8
  search index:  id=42, name="Bàn gỗ sồi", version=8
~~~

**Khoảng thời gian ở giữa là một cửa sổ không nhất quán tạm thời.** Nếu màn hình tìm kiếm hiển thị dữ liệu lỗi thời trong một khoảng ngắn đã được sản phẩm cho phép, hệ thống có thể vẫn đúng theo hợp đồng. Nếu giao diện hứa “đổi tên xong thấy ngay khi tìm kiếm” thì quy trình trên **chưa đáp ứng**, cần cơ chế khác.

### 3.1. Xác định hợp đồng của từng màn hình

| Luồng người dùng | Độ nhất quán đề xuất cần xem xét |
|---|---|
| Lưu tên/giá sản phẩm | Xác nhận sau khi transaction nguồn chính commit |
| Xem chi tiết sản phẩm vừa sửa | Đọc từ nguồn chính hoặc endpoint đảm bảo giá trị mới |
| Tìm kiếm sản phẩm toàn hệ thống | Có thể eventual consistency với giới hạn độ trễ công bố rõ |
| Đặt hàng, kiểm tra tồn kho và giá | Xác minh lại dữ liệu có thẩm quyền trong transaction nghiệp vụ |
| Báo cáo tổng hợp gần thời gian thực | Cần SLA về độ trễ và cơ chế tính lại khi dữ liệu đến muộn |
| Nhật ký kiểm toán quan trọng | Thường yêu cầu sự kiện bền vững, nhất quán với lần ghi nghiệp vụ hoặc cơ chế tương đương |

Hợp đồng phải được thảo luận với chủ sản phẩm và vận hành, không để một thư viện ORM hoặc công cụ tìm kiếm quyết định thay.

## 4. Những mức bảo đảm cần phân biệt

### 4.1. Atomicity trong một database transaction

Khi cập nhật bảng chính và **bảng projection trong cùng một database transaction**, DBMS có thể commit cả hai hoặc rollback cả hai:

~~~sql
BEGIN;

UPDATE products
SET name = 'Bàn gỗ sồi',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = 42;

UPDATE product_search_projection
SET name = 'Bàn gỗ sồi',
    searchable_text = 'ban go soi',
    version = version + 1
WHERE product_id = 42;

COMMIT;
~~~

Ví dụ minh họa đơn giản: giả định mỗi hàng projection tồn tại, có cùng version trước khi cập nhật, và ứng dụng kiểm tra **số hàng cập nhật**. Trong thực tế, cần chống trường hợp projection vắng mặt, version lệch, hoặc thao tác thứ hai không thực hiện được. Bọc trong transaction giúp tránh commit một nửa khi lỗi xảy ra, nhưng **không tự chứng minh logic projection đã đúng**.

Nếu projection được tạo bằng trigger trong DB, trigger cũng có thể tham gia transaction nguồn (tùy DBMS và thiết kế); đổi lại logic lan vào DB, khó kiểm thử/quản lý hơn và tăng chi phí mỗi lần ghi. Nếu dùng `VIEW` không materialize, dữ liệu được tính lại theo câu truy vấn, không có bản sao phải đồng bộ.

### 4.2. Eventual consistency giữa các hệ thống

Khi PostgreSQL và công cụ tìm kiếm là hai hệ thống khác nhau, chúng thường **không có một transaction ACID chung**. Với cơ chế đồng bộ bất đồng bộ, ta thường chọn:

- Giao dịch nguồn chính commit thành công trước.
- Thay đổi sẽ được chuyển thành sự kiện hoặc đầu việc bền vững.
- Hệ thống xử lý sự kiện có thể chậm, lỗi và thử lại.
- Chỉ mục tìm kiếm **hội tụ về trạng thái đúng** nếu các sự kiện cần thiết được xử lý thành công, thứ tự được giải quyết và có chiến lược sửa lệch.

Eventual consistency **không có nghĩa chắc chắn sẽ hội tụ**, nếu pipeline có sự kiện bị mất vĩnh viễn, worker ngừng hoạt động, dữ liệu bị áp dụng sai thứ tự hoặc index không còn khả năng nhận ghi. Muốn tuyên bố hội tụ, cần đủ cơ chế đảm bảo truyền, xử lý lặp, xung đột, xóa và phục hồi.

### 4.3. Freshness khác durability và correctness

Ba câu hỏi tách biệt:

1. **Durability:** ý định cập nhật projection đã được ghi bền vững chưa, hay chỉ nằm trong RAM/thread queue?
2. **Freshness:** projection đang phản ánh phiên bản dữ liệu gần thời điểm hiện tại tới mức nào?
3. **Correctness:** dù đã bắt kịp mọi sự kiện, công thức chuyển đổi, mapping, bộ lọc và quy tắc xóa có cho ra kết quả đúng không?

Một search index mới cập nhật cách đây một giây vẫn có thể **sai** nếu worker index nhầm tenant hoặc dùng mapping giá không phù hợp. Tối ưu độ trễ không thay thế kiểm tra tính đúng đắn.

### 4.4. Các loại nhất quán thường được nhắc đến

- **Read-your-writes:** sau khi ghi thành công, cùng người dùng đọc lại và thấy kết quả của mình theo hợp đồng.
- **Monotonic reads:** khi quan sát phiên bản mới, không bất ngờ quay lại phiên bản cũ ở lần đọc sau theo cơ chế/route không ổn định.
- **Eventual consistency:** các bản sao cuối cùng hội tụ khi không có thay đổi mới và hệ thống đồng bộ hoạt động đúng.
- **Strong/transactional consistency:** các thao tác quan sát và cập nhật tuân theo bảo đảm giao dịch/cô lập cụ thể; không dùng từ “strong” thiếu ngữ cảnh.

Read-your-writes trên API chi tiết có thể được cung cấp bằng cách đọc bảng chính sau khi commit, dù tìm kiếm toàn văn vẫn nhất quán cuối cùng. Không cần ép toàn hệ thống cung cấp một mức bảo đảm giống nhau nếu yêu cầu nghiệp vụ khác nhau.

## 5. Vì sao ghi trực tiếp hai hệ thống dễ làm lệch dữ liệu?

Một cách cài đặt tưởng như tự nhiên:

~~~text
1. UPDATE products trong PostgreSQL
2. COMMIT PostgreSQL
3. Gửi HTTP PUT /search-index/products/42
4. Trả thành công
~~~

Có ít nhất ba điểm lỗi:

- **DB commit thành công, ứng dụng crash trước bước 3:** không có tín hiệu bền vững cho worker biết cần cập nhật search.
- **DB commit thành công, search API trả lỗi:** dữ liệu chính mới, chỉ mục cũ; nếu chỉ ghi log rồi bỏ qua, tình trạng kéo dài.
- **Search cập nhật trước DB commit, DB rollback:** chỉ mục phản ánh một thay đổi chưa bao giờ trở thành dữ liệu chính hợp lệ.

Đảo thứ tự sang “search trước, DB sau” cũng không giải quyết nguyên tử: thất bại của một bên vẫn để lại trạng thái lệch.

Đây là **dual-write problem**. Thêm khối `try/catch` hoặc gọi hai API trong một method `@Transactional` Java không làm PostgreSQL và search index tham gia cùng một transaction.

~~~mermaid
sequenceDiagram
    participant A as Java API
    participant P as PostgreSQL
    participant S as Search service
    A->>P: UPDATE products
    P-->>A: COMMIT success
    Note over A: Ứng dụng có thể crash tại đây
    A-xS: Index product (không gửi được)
    Note over S: Tài liệu tìm kiếm còn phiên bản cũ
~~~

Nếu yêu cầu nhất quán mạnh giữa các bên thật sự bắt buộc, cần phân tích một giao thức phối hợp phân tán được hỗ trợ hoặc kiến trúc khác. Đa số pipeline tìm kiếm chọn **giao dịch nguồn + log sự kiện bền vững + xử lý dẫn xuất**.

## 6. Transactional outbox: nối commit nguồn với ý định đồng bộ

**Transactional outbox** ghi sự kiện/đầu việc gửi đi **trong cùng transaction với thay đổi dữ liệu chính**. Nó loại bỏ khoảng trống “DB commit nhưng chưa kịp ghi lại ý định đồng bộ” trong phạm vi database đó.

### 6.1. Schema minh họa

PostgreSQL:

~~~sql
CREATE TABLE product_outbox (
    event_id        UUID PRIMARY KEY,
    product_id      BIGINT NOT NULL,
    product_version BIGINT NOT NULL,
    event_type      TEXT NOT NULL,
    payload         JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    delivered_at    TIMESTAMPTZ,
    claimed_until   TIMESTAMPTZ,
    claim_token     UUID,
    attempt_count   INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_product_outbox_pending
    ON product_outbox (created_at, event_id)
    WHERE delivered_at IS NULL;
~~~

Ý nghĩa các cột:

- `event_id` là định danh **duy nhất của sự kiện**, dùng nhận diện khi gửi lại.
- `product_id` chỉ aggregate/hàng nguồn.
- `product_version` là phiên bản tăng khi nguồn thay đổi.
- `event_type` cho biết thao tác diễn giải, ví dụ `ProductChanged` hoặc `ProductDeleted`.
- `payload` chứa thông tin đủ để consumer đồng bộ hoặc biết cách lấy dữ liệu đúng.
- `delivered_at` là trạng thái của **relay**; không phải bằng chứng rằng mọi replica tìm kiếm đã refresh và truy vấn mới chắc chắn thấy dữ liệu.
- `claimed_until` và `claim_token` giúp các worker điều phối việc lấy đầu việc theo kiểu lease.
- `attempt_count` giúp quan sát và giới hạn thử lại.

Trong một hệ thống nhiều tenant, cần gắn `tenant_id` và đảm bảo tenant isolation từ nguồn tới projection, cache và search index. Schema này lược bớt tenant để ví dụ tập trung vào transaction.

### 6.2. Một transaction cập nhật cả nguồn và outbox

~~~sql
BEGIN;

UPDATE products
SET name = 'Bàn gỗ sồi',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = 42
  AND is_deleted = FALSE
RETURNING id, version;

-- Giả sử trả (42, 8), ứng dụng dùng version thực tế nhận được.

INSERT INTO product_outbox (
    event_id, product_id, product_version, event_type, payload
) VALUES (
    '00000000-0000-4000-8000-000000000808',
    42,
    8,
    'ProductChanged',
    '{"productId":42,"version":8}'::jsonb
);

COMMIT;
~~~

Ví dụ sử dụng ID/version cố định sau khi đã biết kết quả để minh họa. Trong mã thực, phiên bản ghi ở outbox **phải lấy từ lần cập nhật thành công**, không tự suy đoán `version + 1` trên dữ liệu đã đọc trước khi cạnh tranh.

Nếu insert outbox thất bại, transaction phải rollback cả thay đổi tên. Nếu DB commit thành công, **ý định đồng bộ còn trong outbox** ngay cả khi service crash trước khi gọi search.

### 6.3. Luồng tổng thể

~~~mermaid
flowchart LR
    W["Write API / Java service"] --> T["DB transaction"]
    T --> P["products: source"]
    T --> O["product_outbox"]
    O --> R["Relay / worker"]
    R --> Q["Search API"]
    Q --> I["Search index"]
    R --> M["Ack / retry / metrics"]
    P --> C["Reconciliation / rebuild"]
    C --> I
~~~

Sơ đồ thể hiện **quan hệ logic**, không có nghĩa mỗi mũi tên là thao tác nguyên tử. Ghi sản phẩm và outbox nguyên tử trong DB; giao tiếp relay–search và ack lại database là các bước ngoài transaction đó.

## 7. Ví dụ Java JDBC giữ đúng ranh giới ghi

Giả sử `products` và `product_outbox` nằm trong cùng PostgreSQL, có thể tạo application service đổi tên sản phẩm và ghi sự kiện trong một transaction JDBC.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;

public final class ProductWriteService {
    private final DataSource dataSource;

    public ProductWriteService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long renameProduct(long productId, String newName)
            throws SQLException {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Product name is blank");
        }

        try (Connection connection = dataSource.getConnection()) {
            boolean previousAutoCommit = connection.getAutoCommit();
            Throwable primaryFailure = null;

            try {
                connection.setAutoCommit(false);

                long version;
                try (PreparedStatement update = connection.prepareStatement(
                        """
                        UPDATE products
                        SET name = ?,
                            version = version + 1,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = ? AND is_deleted = FALSE
                        RETURNING version
                        """)) {
                    update.setString(1, newName);
                    update.setLong(2, productId);

                    try (ResultSet rows = update.executeQuery()) {
                        if (!rows.next()) {
                            throw new IllegalStateException(
                                "Product missing or deleted");
                        }
                        version = rows.getLong("version");
                    }
                }

                try (PreparedStatement outbox = connection.prepareStatement(
                        """
                        INSERT INTO product_outbox (
                            event_id, product_id, product_version,
                            event_type, payload
                        ) VALUES (
                            ?, ?, ?, 'ProductChanged',
                            jsonb_build_object('productId', ?,
                                               'version', ?)
                        )
                        """)) {
                    outbox.setObject(1, UUID.randomUUID());
                    outbox.setLong(2, productId);
                    outbox.setLong(3, version);
                    outbox.setLong(4, productId);
                    outbox.setLong(5, version);
                    outbox.executeUpdate();
                }

                connection.commit();
                return version;
            } catch (SQLException | RuntimeException failure) {
                primaryFailure = failure;
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            } finally {
                try {
                    connection.setAutoCommit(previousAutoCommit);
                } catch (SQLException restoreFailure) {
                    if (primaryFailure != null) {
                        primaryFailure.addSuppressed(restoreFailure);
                    } else {
                        throw restoreFailure;
                    }
                }
            }
        }
    }
}
~~~

Đây là ví dụ **minh họa cơ chế transaction/outbox**, không phải dịch vụ sản xuất hoàn chỉnh. Những điểm cần nhớ:

1. `UPDATE ... RETURNING version` chỉ thành công nếu hàng nguồn còn tồn tại theo điều kiện, và lấy đúng phiên bản mới.
2. `INSERT product_outbox` dùng **cùng connection, cùng transaction**; không cần gửi search từ method này.
3. `commit()` kết thúc đơn vị ghi nguyên tử. `Connection.close()` trong `try-with-resources` trả lease về pool nếu dùng pooled `DataSource`.
4. Khi lỗi, service rollback và giữ lỗi rollback phụ trong `suppressed` để không che nguyên nhân chính.
5. Khi mạng đứt trong lúc `COMMIT`, kết quả transaction có thể **không chắc chắn**. Client/service cần command ID và cơ chế idempotency/đối soát nếu có thể gửi lại lệnh. Không retry mù mọi `SQLException`.
6. Khi reset `autoCommit`/close thất bại, phải phân biệt **lỗi cleanup** với **lỗi commit**, tránh tự kết luận thay đổi chưa được lưu. Transaction manager của framework có thể giúp quản lý những nhánh này trong hệ thống thực.

Nếu dùng Spring, cách đặt `@Transactional` tại application service và để cả update repository lẫn outbox repository tham gia **cùng transaction manager** cũng đạt mục tiêu. Không gọi HTTP indexing ngoài DB trong phần transaction này.

## 8. Relay: ít nhất một lần và tính idempotent

Outbox làm bền vững ý định gửi, nhưng không có một phép commit nguyên tử mặc định cho cả **search API** và **cờ delivered trong PostgreSQL**.

Ví dụ:

~~~text
1. Relay nhận event E8 từ outbox.
2. Relay gửi E8 đến search index -> search chấp nhận.
3. Relay crash trước khi đánh dấu delivered_at.
4. Relay khởi động lại, gửi E8 lần thứ hai.
~~~

Đây là tình huống **at-least-once delivery**: cùng sự kiện có thể được gửi nhiều lần. Hợp đồng thực tế phải làm cho việc xử lý lại **không tạo kết quả sai**, thay vì giả định chính xác một lần (*exactly once*) trên mọi hệ thống.

### 8.1. Không giữ transaction DB khi gọi mạng lâu

Cách sai:

~~~text
BEGIN
 SELECT ... FOR UPDATE SKIP LOCKED
 Gọi search API trong 10 giây             <- vẫn giữ DB transaction
 UPDATE outbox SET delivered = true
COMMIT
~~~

Nó giữ connection và khóa của DB trong khi chờ mạng, làm giảm thông lượng và tạo nguy cơ pool exhaustion.

Một thiết kế worker phổ biến:

1. **Claim** một nhóm event bằng transaction ngắn và một lease/correlation token.
2. Commit transaction claim; giải phóng khóa database.
3. Gọi search API ngoài transaction.
4. Nếu thành công theo hợp đồng indexing, ghi nhận ack/`delivered_at` theo token còn hợp lệ.
5. Nếu thất bại, cho retry với backoff; nếu lease hết hạn, event có thể được claim lại.

Ví dụ minh họa claim trong PostgreSQL:

~~~sql
BEGIN;

WITH picked AS (
    SELECT event_id
    FROM product_outbox
    WHERE delivered_at IS NULL
      AND (claimed_until IS NULL OR claimed_until < CURRENT_TIMESTAMP)
    ORDER BY created_at, event_id
    LIMIT 20
    FOR UPDATE SKIP LOCKED
)
UPDATE product_outbox AS o
SET claim_token = '00000000-0000-4000-8000-000000000999'::uuid,
    claimed_until = CURRENT_TIMESTAMP + INTERVAL '30 seconds',
    attempt_count = attempt_count + 1
FROM picked
WHERE o.event_id = picked.event_id
RETURNING
    o.event_id, o.product_id, o.product_version,
    o.event_type, o.payload, o.claim_token;

COMMIT;
~~~

Sau khi index thành công, ack nên có điều kiện `event_id` và `claim_token`:

~~~sql
UPDATE product_outbox
SET delivered_at = CURRENT_TIMESTAMP,
    claimed_until = NULL,
    claim_token = NULL
WHERE event_id = :event_id
  AND claim_token = :claim_token
  AND delivered_at IS NULL;
~~~

`:event_id` và `:claim_token` là ký hiệu tham số đặt tên của một thư viện SQL; với JDBC `PreparedStatement` thuần phải thay bằng `?` và bind giá trị. Cần kiểm tra **affected row count**; nếu bằng 0, worker có thể đã mất quyền sở hữu lease hoặc event đã được xử lý ở nơi khác.

**Lưu ý:** ví dụ lease 30 giây chỉ là minh họa. Nếu thao tác indexing có thể lâu hơn lease, cần gia hạn hoặc điều phối phù hợp. Token giúp ngăn ack không còn hợp lệ, nhưng **không ngăn worker cũ gọi search muộn**; cơ chế **kiểm tra phiên bản tại search destination** vẫn cần thiết.

### 8.2. ACK không có nghĩa tìm kiếm đã đọc thấy ngay

Nhiều hệ thống tìm kiếm phân biệt “API indexing đã nhận/ghi thay đổi” và “kết quả tìm kiếm đã refresh và có thể truy vấn thấy”. Khi gắn `delivered_at`, phải định nghĩa rõ ack thể hiện **giai đoạn nào**, tránh trình bày delivered như cam kết read-your-writes ở tầng search.

Nếu sản phẩm cần biết tài liệu đã có thể truy vấn, có thể theo dõi thêm trạng thái refresh/visibility theo khả năng công cụ hoặc dùng đường đọc từ nguồn chính cho màn hình sau ghi.

## 9. Sự kiện đến sai thứ tự: tại sao phải có phiên bản?

Hai lần sửa sản phẩm liên tiếp:

~~~text
DB:
  E8: product 42, version 8, name="Bàn gỗ sồi"
  E9: product 42, version 9, name="Bàn gỗ sồi cao cấp"

Do mạng/retry, E9 tới search trước E8.
~~~

Nếu search index chỉ nhận “last write wins theo **thứ tự nhận sự kiện**”:

~~~text
T1: apply E9 -> search version 9, tên mới
T2: apply E8 -> search version 8, tên cũ
~~~

Kết quả cuối **lùi phiên bản**, dù mọi sự kiện đã được gửi thành công.

### 9.1. Quy tắc hội tụ theo phiên bản

Một chiến lược là mỗi tài liệu tìm kiếm có `source_version`. Consumer chỉ áp dụng thay đổi nếu version mới **lớn hơn** version đang lưu, bằng cơ chế **so sánh và ghi nguyên tử ở phía destination** hoặc tính năng versioning của công cụ tìm kiếm:

~~~text
function apply(event):
    current = indexed source_version for product_id

    if event.version < current:
        ignore as stale
    else if event.version == current:
        treat as duplicate / verify idempotency
    else:
        atomically upsert newer document / delete tombstone
~~~

Đoạn pseudocode nêu **hợp đồng logic**. Cách thực thi thật phải ngăn hai worker cùng đọc version cũ rồi ghi đè nhau; một bước **read-then-write** không nguyên tử ở phía consumer là chưa đủ. Dùng conditional update, external versioning, compare-and-set, partition theo khóa hoặc cơ chế đồng bộ tương ứng mà công cụ cung cấp.

### 9.2. Version phải thuộc đúng đơn vị dữ liệu

Một `product_version` tăng đơn điệu trên **mỗi product** là phù hợp để sắp thứ tự các thay đổi của product đó. Nó không tự đưa ra thứ tự toàn cục giữa mọi product hoặc giữa product và các aggregate khác.

Nếu tài liệu tìm kiếm của sản phẩm ghép từ nhiều nguồn (`products` + `categories` + `inventory`), chỉ `product_version` chưa đủ để biết khi category đổi tên thì tài liệu product có lỗi thời không. Cần thiết kế:

- Luồng phát lại sự kiện cho những product bị ảnh hưởng.
- Version vector/điểm mốc cho các nguồn phụ thuộc nếu cần.
- Hoặc worker đọc **trạng thái hiện tại có thẩm quyền** và tái tạo tài liệu từ dữ liệu liên quan, với cơ chế tránh cập nhật ngược khi ghi.

Không dùng timestamp như một sự thay thế đơn giản cho version: đồng hồ giữa nhiều máy, độ phân giải, sự kiện đến trễ và retry khiến so sánh timestamp không nhất thiết phản ánh thứ tự commit mong muốn.

### 9.3. Chỉ lưu ID trong sự kiện hay lưu đầy đủ snapshot?

**Event tối thiểu**:

~~~json
{
  "eventId": "e-8",
  "productId": 42,
  "version": 8,
  "type": "ProductChanged"
}
~~~

Worker đọc lại trạng thái sản phẩm hiện tại từ DB. Ưu điểm: payload nhỏ và có thể xây projection từ dữ liệu mới nhất. Nhược điểm: có truy vấn bổ sung, trạng thái nguồn có thể đã tiến lên version 9 trước khi xử lý event 8, và cần quy tắc version khi ghi.

**Event chứa snapshot đủ để index**:

~~~json
{
  "eventId": "e-8",
  "productId": 42,
  "version": 8,
  "type": "ProductChanged",
  "document": {
    "name": "Bàn gỗ sồi",
    "price": "180000.00",
    "isDeleted": false
  }
}
~~~

Ưu điểm: dễ phát lại đúng nội dung của một thời điểm, giảm truy vấn nguồn. Nhược điểm: payload lớn, schema sự kiện tiến hóa, dữ liệu cá nhân hoặc bí mật có thể bị lưu nhiều nơi, và tài liệu có thể thiếu các trường đến từ bảng khác.

Hai cách đều cần **idempotency, xử lý thứ tự và schema versioning**. Chọn theo nhu cầu projection, mức tải và chính sách dữ liệu, không coi một cách mặc nhiên đúng cho mọi hệ thống.

## 10. Delete, tombstone và nguy cơ sản phẩm “sống lại”

Xóa bản ghi là trường hợp đặc biệt vì sau khi hard delete, worker có thể **không còn đọc được trạng thái nguồn** để biết phải xóa tài liệu tìm kiếm.

~~~text
1. Product 42 có source_version=9 trong search.
2. Nguồn xóa product 42, phát E10: ProductDeleted.
3. Search xóa tài liệu 42.
4. E9 được gửi lại trễ -> search upsert product 42.
5. Product 42 xuất hiện lại dù nguồn đã xóa.
~~~

Nếu hệ tìm kiếm không giữ dấu version của thao tác xóa, một event cũ có thể tái tạo tài liệu đã xóa.

### 10.1. Soft delete và tombstone

Các phương án phổ biến:

- **Soft delete** ở bảng nguồn: `is_deleted = true` và tăng `version`. Worker có thể thấy trạng thái đã xóa và xóa hoặc ẩn tài liệu.
- **Tombstone event**: phát `ProductDeleted(productId, version)` để consumer áp dụng delete có version.
- **Tombstone trong projection**: giữ một bản ghi nhỏ gồm ID và phiên bản xóa, đủ lâu để từ chối các sự kiện cũ.
- **Rebuild từ nguồn hiện tại**: khi tái tạo toàn bộ chỉ mục, không đưa hàng đã xóa trở lại.

Một search engine có thể có cơ chế version/tombstone nội bộ với thời hạn lưu nhất định. **Nếu dấu xóa bị dọn trước khi các sự kiện cũ có thể đến**, bảo vệ chống “resurrection” không còn chắc chắn. Phải phối hợp retention sự kiện, khả năng replay, thời gian tombstone và quy tắc áp dụng phiên bản.

### 10.2. Xóa dữ liệu nhạy cảm không chỉ là xóa một tài liệu

Nếu yêu cầu xóa dữ liệu cá nhân, cần xem mọi nơi sao chép: nguồn chính, outbox payload, log, backup, cache, chỉ mục, dead-letter queue và các bản reindex tạm thời. Chiến lược tombstone/version có thể giúp tính đúng đắn nhưng phải kết hợp chính sách lưu trữ/xóa dữ liệu theo yêu cầu hệ thống.

Không để event snapshot cũ chứa dữ liệu nhạy cảm tồn tại vô hạn chỉ để có thể replay. Thiết kế schema sự kiện và retention cần tuân thủ chính sách dữ liệu ngay từ đầu.

## 11. Change Data Capture (CDC) và event-driven projection

Ngoài polling outbox, có thể dùng **Change Data Capture** (CDC) để đọc thay đổi từ nhật ký giao dịch của database, ví dụ WAL/logical decoding phù hợp trên PostgreSQL hoặc binlog trên MySQL.

Một luồng thường gặp:

~~~text
Ứng dụng ghi DB transaction
        |
        v
Database transaction log
        |
        v
CDC connector
        |
        v
Event stream / queue
        |
        v
Projection worker -> search index
~~~

### 11.1. CDC giải quyết và không giải quyết điều gì?

CDC có thể giảm việc tự polling bảng và cho phép xử lý dòng thay đổi có vị trí log để tiếp tục sau lỗi. Nhưng nó không tự làm cho search index giao dịch chung với DB.

Cần thiết kế:

- **Snapshot ban đầu:** lấy dữ liệu hiện có trước khi bắt đầu dòng thay đổi.
- **Offset/checkpoint:** biết connector đã đọc tới đâu và cách phát lại sau lỗi.
- **Retention của log:** bảo đảm connector không bị tụt quá lâu đến mức mất đoạn log cần thiết.
- **Transaction boundaries:** không phát dữ liệu chưa commit như thay đổi đã có hiệu lực.
- **Thứ tự:** đảm bảo hoặc khôi phục thứ tự cần thiết trên mỗi aggregate; nếu partition event stream, khóa partition theo `product_id` khi phù hợp.
- **Schema evolution:** các thay đổi cột/kiểu không làm hỏng consumer đang chạy.
- **Duplicate/replay:** consumer idempotent để chấp nhận thông điệp phát lại.

Nếu ứng dụng chỉ dựa vào CDC của bảng nguồn để suy ra event nghiệp vụ, một `UPDATE` có thể không nói rõ **ý định** nghiệp vụ hoặc những thay đổi trong transaction liên quan nhiều bảng. Có thể dùng **outbox + CDC**: ghi event nghiệp vụ vào outbox cùng transaction, rồi CDC phát event đó ra stream. Hai kỹ thuật bổ trợ nhau.

### 11.2. Không hứa một thứ tự tuyệt đối thiếu cơ sở

Một event stream có thể giữ thứ tự trong một partition nhưng không bảo đảm thứ tự toàn bộ giữa mọi partition. Worker cũng có thể xử lý song song khiến kết quả đến search khác thứ tự nhận.

Thứ tự commit của database, thứ tự event được phát, thứ tự delivery và thứ tự index refresh **không nhất thiết giống nhau**. Cơ chế hội tụ theo `aggregate_version` và áp dụng nguyên tử ở destination giúp tránh phụ thuộc vào một giả định thứ tự đầu-cuối không được bảo đảm.

## 12. Dữ liệu dẫn xuất trong cùng DB: view, materialized view, bảng projection

Không phải dự án nào cũng cần một hệ tìm kiếm bên ngoài. Với tập truy vấn vừa phải, có thể giữ phần lớn dữ liệu dẫn xuất trong DBMS.

### 12.1. View thông thường

~~~sql
CREATE VIEW active_products AS
SELECT id, name, price
FROM products
WHERE is_deleted = FALSE;
~~~

`VIEW` thông thường là định nghĩa truy vấn; khi query view, DBMS đọc bảng nguồn theo ngữ nghĩa giao dịch. Không có một bản sao chứa riêng cần đồng bộ. Nó giúp tái sử dụng SQL, nhưng không tự làm truy vấn nặng trở thành nhanh.

### 12.2. Materialized view

~~~sql
CREATE MATERIALIZED VIEW product_price_bands AS
SELECT
    CASE
        WHEN price < 100000 THEN 'LOW'
        WHEN price < 500000 THEN 'MID'
        ELSE 'HIGH'
    END AS price_band,
    COUNT(*) AS product_count
FROM products
WHERE is_deleted = FALSE
GROUP BY 1;
~~~

Materialized view lưu kết quả đã tính tại thời điểm tạo/refresh. Với PostgreSQL, cần **REFRESH MATERIALIZED VIEW** theo chính sách; thay đổi nguồn không tự cập nhật mọi hàng của materialized view ở mỗi transaction.

~~~sql
REFRESH MATERIALIZED VIEW product_price_bands;
~~~

`REFRESH MATERIALIZED VIEW CONCURRENTLY` có điều kiện tiên quyết riêng (chẳng hạn unique index phù hợp trên materialized view và các yêu cầu của PostgreSQL). Không giả định tùy chọn này luôn áp dụng được hoặc refresh tức thời.

Hợp đồng freshness của materialized view là **lịch và thời điểm refresh thành công**, không phải mặc định đồng bộ từng bản ghi nguồn.

### 12.3. Bảng projection cập nhật đồng bộ

Ví dụ:

~~~sql
CREATE TABLE product_search_projection (
    product_id      BIGINT PRIMARY KEY REFERENCES products(id),
    name            TEXT NOT NULL,
    searchable_text TEXT NOT NULL,
    price           NUMERIC(14, 2) NOT NULL,
    source_version  BIGINT NOT NULL
);
~~~

Nếu transaction thay đổi `products` cũng cập nhật chính xác `product_search_projection` trước commit, hai bảng có thể có **bảo đảm atomicity chung**. Nhưng:

- Mọi đường ghi dữ liệu nguồn (API, job, migration) đều phải cập nhật projection hoặc có trigger phù hợp.
- Projection phức tạp có thể làm transaction ghi nặng hơn.
- Công thức dẫn xuất sai vẫn tạo dữ liệu sai nhưng được commit nguyên tử.
- Một bảng projection thiếu hàng có thể cần `INSERT ... ON CONFLICT DO UPDATE` với quy tắc version rõ.
- Khi schema/công thức thay đổi, cần backfill và kiểm thử dữ liệu cũ.

**Atomicity không tự bằng correctness.** Đúng transaction không thay thế thiết kế công thức chuyển đổi và chính sách cập nhật.

## 13. Trải nghiệm đọc khi chỉ mục tìm kiếm chậm đồng bộ

Giả sử API cập nhật sản phẩm trả thành công với `version = 8`, nhưng search index còn `version = 7`. Có nhiều cách xây hợp đồng đọc.

### 13.1. Đọc sau ghi từ nguồn chính

API trả đối tượng đã cập nhật hoặc endpoint chi tiết `GET /products/42` đọc PostgreSQL để thấy tên mới ngay. Màn hình tìm kiếm toàn văn có thể hiển thị thông báo “Đang cập nhật kết quả tìm kiếm”.

Ưu điểm: không bắt request ghi phải đợi search. Nhược điểm: cùng một sản phẩm có thể nhìn mới ở trang chi tiết nhưng cũ trong kết quả tìm kiếm một khoảng thời gian.

### 13.2. Có trạng thái đồng bộ rõ ràng

API có thể trả:

~~~json
{
  "productId": 42,
  "sourceVersion": 8,
  "writeStatus": "COMMITTED",
  "searchVisibility": "PENDING"
}
~~~

Ý nghĩa `COMMITTED` chỉ nói transaction nguồn chính hoàn tất. `PENDING` nói chưa có xác nhận search đạt mức visibility yêu cầu; không hứa rằng ngay lập tức query toàn văn đã thấy bản mới.

Nếu worker ghi nhận `indexed_version` theo sản phẩm, UI hoặc API có thể hiển thị tiến trình. Phải hiểu `indexed_version` đang biểu diễn **index API accepted**, **replica refreshed** hay một phép query xác nhận visibility. Không nên gộp ba khái niệm thành một trạng thái mơ hồ.

### 13.3. Chờ tới một phiên bản với timeout có giới hạn

Một API có thể yêu cầu “chờ cho đến khi search thấy version ít nhất 8”, rồi trả kết quả hoặc trả tình trạng đang chờ sau một timeout ngắn. Cách này tăng độ mới dữ liệu nhìn thấy cho người dùng nhưng cần:

- Nguồn tín hiệu phản ánh **visibility** thật ở search.
- Timeout để tránh giữ HTTP request/connection DB vô hạn.
- Hạn chế polling và độ tải sinh thêm.
- Kết quả rõ ràng khi quá thời gian, không giả vờ đã đồng bộ.

Không giữ transaction ghi của PostgreSQL trong lúc chờ external search. Transaction nguồn phải commit trước để relay có thể nhận sự kiện.

### 13.4. Không dùng search làm kiểm tra cuối cho nghiệp vụ nhạy cảm

Khi người dùng chọn sản phẩm từ kết quả tìm kiếm, checkout phải kiểm tra lại giá/tồn kho/trạng thái ở nguồn có thẩm quyền theo ranh giới transaction thích hợp. Một search result đã stale không nên tự làm cơ sở để giao hàng hoặc khấu trừ tiền.

Cũng cần chú ý **an toàn quyền truy cập**: nếu search index lỗi thời về quyền/tenant membership, nó có thể trả tài liệu người dùng không còn quyền xem. Với dữ liệu nhạy cảm, phải áp dụng kiểm tra quyền nhất quán ở đường phục vụ kết quả hoặc thiết kế index và luồng cập nhật quyền đáp ứng đúng SLA bảo mật; không mặc định eventual consistency luôn chấp nhận được cho thay đổi quyền.

## 14. Reindex, backfill và phục hồi dữ liệu lệch

Một pipeline dù có retry tốt vẫn cần cơ chế **tái tạo hoàn toàn** khi đổi mapping, thêm trường, sửa lỗi projection hoặc phát hiện index đã lệch.

### 14.1. Vì sao rebuild “xóa index rồi đổ lại” có thể mất cập nhật?

Tình huống:

~~~text
T0: bắt đầu đọc toàn bộ products để rebuild.
T1: product 42 được đọc với version 8.
T2: ứng dụng cập nhật product 42 lên version 9.
T3: index rebuild ghi lại snapshot version 8.
T4: rebuild kết thúc, không có bước bắt kịp thay đổi T2.
~~~

Nếu một event version 9 chưa được xử lý đúng trên index mới, kết quả sau rebuild có thể **lùi về version 8**. Ngay cả khi rebuild xong rất nhanh, việc không phối hợp snapshot với dòng thay đổi cũng là một lỗ hổng nhất quán.

### 14.2. Chiến lược rebuild có thể chuyển đổi an toàn

Một phương án tổng quát:

1. Tạo **index mới** với tên/version schema mới, chưa dùng cho truy vấn chính.
2. Xác định mốc snapshot/CDC hoặc một cơ chế theo dõi các thay đổi xảy ra trong lúc backfill.
3. Đổ dữ liệu từ nguồn có thẩm quyền vào index mới với `source_version`.
4. Phát lại hoặc tiếp tục dòng thay đổi từ mốc thích hợp; xử lý duplicate/out-of-order bằng version check.
5. Kiểm tra lượng dữ liệu, lấy mẫu nội dung, phiên bản và lag; phải có tiêu chí “đã bắt kịp” rõ ràng.
6. Chuyển alias/router tìm kiếm sang index mới theo cơ chế hỗ trợ, có kế hoạch rollback.
7. Theo dõi hậu chuyển đổi, chỉ xóa index cũ sau khi xác minh và hết thời gian dự phòng.

Nếu snapshot không có mốc nhất quán với stream, cần thiết kế phương án quét bù/đối soát ở cuối. Không chỉ dựa vào câu “CDC vẫn đang chạy” để chứng minh không mất thay đổi.

### 14.3. Reconciliation: đối chiếu và sửa lệch

Định kỳ hoặc sau sự cố, đối chiếu nguồn chính và projection:

- Lấy tập ID, trạng thái xóa và phiên bản nguồn.
- Kiểm tra tài liệu tương ứng ở search/projection.
- Phát hiện **missing** (thiếu), **stale** (version cũ), **extra** (tài liệu không còn trong nguồn), **incorrect** (nội dung/mapping sai dù version khớp).
- Đưa các trường hợp lỗi vào hàng đợi sửa có giới hạn và theo dõi kết quả.
- Với bất đồng do version mới hơn ở search nhưng nguồn cũ hơn, điều tra quy tắc nguồn sự thật trước khi tự ghi đè.

Một `source_version` bằng nhau **không chứng minh mọi trường đã được index đúng**. Có thể sử dụng checksum/canonical representation của các trường liên quan, kiểm tra mẫu và kiểm thử mapping để bắt lỗi chuyển đổi.

Reconciliation cần thiết vì cơ chế at-least-once và idempotency xử lý được nhiều lỗi truyền tải nhưng **không sửa được một hàm projection sai logic**.

## 15. Khả năng phục hồi: lỗi tạm thời, poison event và hàng đợi chết

### 15.1. Phân biệt loại lỗi của projection worker

| Lỗi | Ví dụ | Phản ứng phù hợp |
|---|---|---|
| Tạm thời | Search server không sẵn sàng, mạng đứt, rate limit | Retry có giới hạn, exponential backoff + jitter |
| Xung đột phiên bản | Event 8 tới sau event 9 | Bỏ qua event cũ theo quy tắc version/idempotency |
| Dữ liệu không hợp lệ | Payload thiếu trường bắt buộc, sai schema | Cách ly, alert, sửa serializer/mapping |
| Quyền/xác thực | Credential search hết hạn | Cảnh báo vận hành, rotate credentials, không retry quá nhanh |
| Nguồn không còn dữ liệu | Product đã bị hard delete | Xử lý delete/tombstone theo hợp đồng, không tự hồi sinh |
| Lỗi cấu hình/mapping | Kiểu trường search không khớp dữ liệu | Sửa mapping và cân nhắc reindex |

### 15.2. Dead-letter queue (DLQ)

Khi một sự kiện không thể xử lý sau số lần thử hợp lý, có thể đưa vào **dead-letter queue** hoặc trạng thái lỗi bền vững. DLQ không phải nơi “xóa lỗi”: cần có người chịu trách nhiệm, alert, quy trình phân loại, khả năng replay và chính sách dữ liệu.

Nếu không có DLQ, một poison event có thể làm nghẽn cả partition hoặc vòng lặp retry vô hạn. Nếu DLQ bỏ qua event mà không sửa projection, hệ thống có thể không bao giờ hội tụ. Do đó cần **reconciliation và remediation**.

### 15.3. Không nhầm duplicate với kết quả không hợp lệ

Cùng một event gửi hai lần có thể là bình thường của at-least-once delivery. Consumer idempotent cần chấp nhận hoặc bỏ qua lần lặp mà không tạo side effect sai. Chỉ những duplicate có ý nghĩa bất thường (ví dụ hai event khác ID nhưng cùng version và payload mâu thuẫn) mới cần điều tra sâu.

## 16. Monitoring: đo sự hội tụ, không chỉ số sự kiện đã gửi

Một dashboard phù hợp cần tách **sức khỏe luồng**, **độ trễ đồng bộ** và **tính đúng đắn dữ liệu**.

| Chỉ số | Ý nghĩa |
|---|---|
| Outbox backlog count | Số event chưa hoàn tất |
| Oldest undelivered event age | Event lâu nhất còn tồn đọng; tín hiệu quan trọng khi backlog nhỏ nhưng stuck |
| Source commit → index accepted lag | Thời gian từ commit nguồn đến khi search API chấp nhận |
| Source commit → search visible lag | Thời gian đến khi query tìm kiếm thật sự quan sát được phiên bản |
| Retry count / failure rate | Mức lỗi tạm thời và áp lực thử lại |
| DLQ count / oldest age | Số event cần xử lý thủ công/hệ thống sửa |
| Projection version gap | Chênh lệch version giữa nguồn và tài liệu dẫn xuất |
| Missing / extra / stale rate | Kết quả reconciliation theo mẫu hoặc toàn bộ |
| Rebuild progress / catch-up lag | Trạng thái backfill và khả năng chuyển index an toàn |
| Search indexing throughput | Công suất worker/destination so với tốc độ nguồn thay đổi |
| End-user freshness complaints | Dấu hiệu thực tế khi giao diện chưa đạt hợp đồng |

### 16.1. Đặt SLO về độ mới dữ liệu

Một yêu cầu sản phẩm có thể là: “99% cập nhật tên sản phẩm phải xuất hiện trong tìm kiếm trong vòng 10 giây”. Khi đó cần đo **độ trễ visibility thực**, không chỉ đo `outbox.delivered_at` hoặc số event đã ack.

Con số 10 giây ở đây **chỉ là ví dụ SLO**, không phải mặc định kỹ thuật. Tùy ngành, các thay đổi giá, quyền truy cập, tồn kho hoặc thông tin nhạy cảm có thể cần SLO chặt hơn hay cơ chế đọc từ nguồn chính.

### 16.2. Alert dựa trên tác động

Các cảnh báo thường hữu ích:

- Backlog/oldest age vượt ngưỡng liên tục.
- Không có event mới được đồng bộ trong lúc nguồn vẫn có ghi.
- Tỷ lệ thất bại, retry hoặc DLQ tăng nhanh.
- Reconciliation phát hiện stale/extra/missing vượt ngân sách sai lệch.
- Tốc độ xử lý thấp hơn tốc độ sinh event trong thời gian dài.
- Index mapping/alias chuyển đổi thất bại hoặc có dấu hiệu rollback.

Tránh chỉ đặt cảnh báo theo tổng số event: khi traffic tăng mạnh, backlog có thể tăng tạm thời nhưng vẫn được xử lý kịp trong SLO. **Tuổi backlog và độ trễ thực** thường cung cấp ngữ cảnh tốt hơn.

## 17. Lựa chọn kiến trúc theo yêu cầu

| Điều kiện / nhu cầu | Cách tiếp cận đáng cân nhắc | Giới hạn cần kiểm tra |
|---|---|---|
| Một truy vấn tính được từ bảng chính, không quá nặng | SQL query hoặc VIEW | Chi phí query và chỉ mục |
| Projection cùng DB, phải commit cùng nghiệp vụ | Cập nhật trong transaction hoặc trigger | Mọi đường ghi đều phải giữ bất biến |
| Tổng hợp lớn, chịu được chậm vài phút | Materialized view + refresh | Lịch refresh, backfill, khóa và tài nguyên |
| Read cache, chấp nhận lỗi thời ngắn | Cache-aside + TTL/invalidation | Race nạp giá trị cũ, quyền truy cập, fallback |
| Full-text search, chấp nhận eventual consistency | Outbox/CDC + search index | Retry, ordering, delete, visibility SLO |
| Tìm kiếm phải phản ánh ghi ngay | Đọc từ nguồn có thẩm quyền hoặc chờ phiên bản với timeout | Tải, độ trễ, hợp đồng visibility |
| Projection từ nhiều aggregate | Rebuild từ nguồn + version/dependency tracking | Không chỉ dựa vào version của một bảng |
| Nhiều replica/region và nhiều nơi ghi | Thiết kế ownership/xung đột rõ, có thể cần kiến trúc khác | Không tự giả định last-write-wins theo đồng hồ |
| Dữ liệu có quyền truy cập nhạy cảm | Authorization tại đường đọc / đồng bộ quyền nghiêm ngặt | Eventual search stale có thể là lỗi bảo mật |

Không có một giải pháp duy nhất tối ưu cho tất cả. Chọn kiến trúc sau khi quyết định **nguồn có thẩm quyền**, **cửa sổ stale được phép**, **mức chịu lỗi**, **chi phí vận hành** và **khả năng rebuild**.

## 18. Kiểm thử các lịch chạy cạnh tranh và lỗi

Một bài kiểm thử tích hợp tốt phải cố ý tạo các tình huống mà đường thành công đơn giản không phát hiện.

### 18.1. Những ca cần ưu tiên

1. **DB rollback:** cập nhật `products` thành công trong transaction nhưng insert outbox lỗi; xác minh cả thay đổi nguồn và outbox cùng rollback.
2. **Crash sau commit:** nguồn và outbox commit, Java service dừng trước khi gửi search; sau khi relay khởi động, index vẫn bắt kịp.
3. **Index thành công, ack thất bại:** event được gửi lại, projection vẫn đúng và không tạo tác dụng phụ sai.
4. **Sai thứ tự:** E9 áp dụng trước E8; index không lùi từ version 9 về 8.
5. **Hai worker cùng làm:** lease hết hạn giữa chừng, worker cũ gửi muộn; conditional version update tại search ngăn ghi đè cũ.
6. **Delete sau upsert:** E10 delete trước E9 update đến trễ; tài liệu đã xóa không tự tái xuất hiện.
7. **Backfill đồng thời với ghi:** dữ liệu đổi trong khi rebuild; index mới đạt trạng thái hợp lệ sau catch-up.
8. **Poison event:** payload sai schema; worker không retry vô hạn, có cảnh báo và quy trình sửa.
9. **Search refresh chậm:** `delivered_at` đã đặt nhưng tìm kiếm chưa thấy; API không báo đã visible sai.
10. **Cập nhật nhiều bảng liên quan:** category hoặc giá tồn kho thay đổi; tài liệu dẫn xuất được tái tạo đúng theo tất cả nguồn cần thiết.
11. **Quyền truy cập thay đổi:** search kết quả lỗi thời không lộ dữ liệu vượt quá hợp đồng bảo mật.
12. **Mất mạng lúc COMMIT:** kiểm thử idempotency command và đối soát thay vì retry mù.

### 18.2. Mẫu bảng kỳ vọng

| Lịch chạy | Nguồn DB | Outbox/stream | Search index | Kỳ vọng |
|---|---|---|---|---|
| Ghi commit bình thường | Version 8 | E8 được ghi bền vững | Từ 7 lên 8 | Hội tụ |
| Ghi rollback | Vẫn version 7 | Không có E8 đã commit | Vẫn 7 | Không index thay đổi chưa commit |
| E8 phát lại hai lần | Version 8 | Duplicate E8 | Version 8 | Không nhân đôi tác dụng phụ |
| E9 rồi E8 | Version 9 | Đến sai thứ tự | Version 9 | Không cập nhật ngược |
| Delete E10 rồi upsert E9 | Đã xóa ở version 10 | E9 trễ | Deleted/tombstone 10 | Không hồi sinh |
| Search tạm ngừng | Version 11 | E11 backlog | Có thể vẫn 10 | Alert và retry/reconcile |
| Rebuild từ snapshot cũ | Version 12 | Có tail events | Index mới 12 | Không mất thay đổi phát sinh khi rebuild |

Test nên kiểm tra **trạng thái cuối** và các **trạng thái trung gian cho phép**, không chỉ assert worker đã gọi một mock search client. Nếu có thể, dùng DBMS và search engine thử nghiệm đúng loại sản xuất, điều khiển thứ tự xử lý bằng barrier/latch để tái hiện race.

## 19. Bài tập tự kiểm tra

### Bài 1: Nguồn sự thật hay projection?

Bảng `products` chứa giá chính thức, search index chứa một bản sao giá để lọc kết quả. Sau khi seller cập nhật từ 200.000 xuống 180.000 đồng, search còn 200.000 trong ba giây. Checkout nên dùng giá nào?

**Gợi ý:** Đọc/xác minh giá có thẩm quyền theo quy tắc nghiệp vụ tại checkout, không tin giá stale từ search. Ba giây lệch có thể được chấp nhận cho UI tìm kiếm nếu hợp đồng quy định như vậy.

### Bài 2: Dual-write

Ứng dụng `COMMIT` PostgreSQL rồi gọi API search. Sau commit ứng dụng crash trước khi gọi search. Điều gì giúp hệ thống vẫn đồng bộ?

**Gợi ý:** Ghi outbox trong **cùng transaction** với thay đổi nguồn, hoặc một cơ chế CDC bền vững nắm được mọi thay đổi cần thiết. Worker phục hồi sự kiện khi ứng dụng khởi động lại.

### Bài 3: Duplicate delivery

Worker gửi event E8, search index áp dụng thành công, nhưng worker crash trước khi đánh dấu đã gửi. Event E8 được gửi lại. Đây có phải bug của outbox?

**Gợi ý:** Không nhất thiết. At-least-once có thể gửi lặp; consumer phải idempotent, chẳng hạn kiểm tra event ID/version và áp dụng trạng thái đúng.

### Bài 4: Sai thứ tự

Search đã index version 9 nhưng nhận event version 8. Nên xử lý thế nào?

**Gợi ý:** Bỏ qua event cũ theo một phép so sánh–ghi **nguyên tử ở phía search** hoặc cơ chế versioning tương đương. Không đọc version rồi ghi không điều kiện.

### Bài 5: Xóa và tái xuất hiện

Sản phẩm đã xóa ở version 10, nhưng event upsert version 9 bị gửi lại sau đó. Làm sao tránh tài liệu sống lại?

**Gợi ý:** Dùng tombstone/version delete và chính sách retention đủ dài, hoặc bảo vệ tại destination theo cơ chế versioning. Rebuild cũng phải loại dữ liệu đã xóa.

### Bài 6: Materialized view

Một materialized view PostgreSQL tổng hợp doanh số. Bảng `orders` vừa thêm đơn mới nhưng view vẫn hiển thị tổng cũ. Có mâu thuẫn với tính nguyên tử của transaction chèn đơn không?

**Gợi ý:** Không. Materialized view lưu kết quả từ lần refresh trước; nó không mặc nhiên cập nhật cùng mọi ghi nguồn. Cần hợp đồng lịch refresh/freshness.

### Bài 7: Projection từ nhiều bảng

Search document gồm `product.name` và `category.name`. Khi sửa category, `product.version` không đổi. Chỉ theo dõi product version có đủ không?

**Gợi ý:** Không. Cần sự kiện category và tái tạo các product liên quan, hoặc một cơ chế version/dependency bổ sung.

### Bài 8: Search accepted nhưng chưa visible

Relay nhận phản hồi thành công từ API indexing và đặt `delivered_at`. Ngay sau đó người dùng search chưa thấy sản phẩm mới. Có thể khẳng định hệ thống sai không?

**Gợi ý:** Cần hiểu hợp đồng refresh của search engine và SLO. Ack indexing không nhất thiết đồng nghĩa query visibility tức thời. Nếu UI hứa thấy ngay, phải có cơ chế read-your-writes hoặc chờ visibility.

### Bài 9: Rebuild trong lúc có ghi

Job rebuild đọc snapshot version 5. Trong khi đó nguồn tăng lên version 6. Job hoàn tất và chuyển alias sang index mới nhưng không phát lại thay đổi. Rủi ro?

**Gợi ý:** Index mới chứa dữ liệu cũ; cần ghép snapshot với stream/CDC từ mốc nhất quán và kiểm tra catch-up trước khi chuyển.

### Bài 10: Nguy cơ bảo mật

Quyền truy cập tài liệu vừa bị thu hồi ở database, nhưng chỉ mục tìm kiếm vẫn cho phép truy vấn dựa trên quyền cũ trong 30 giây. Có thể coi đây chỉ là vấn đề trải nghiệm người dùng?

**Gợi ý:** Không. Với tài liệu nhạy cảm, stale authorization có thể là lỗ hổng. Cần kiểm tra quyền theo nguồn có thẩm quyền ở đường đọc hoặc bảo đảm cập nhật quyền đủ chặt theo yêu cầu bảo mật.

## 20. Ghi nhớ

- **Xác định nguồn sự thật trước khi thiết kế bản sao.** Bảng chính giữ dữ liệu có thẩm quyền; projection, cache và search index là những biểu diễn phục vụ truy vấn và hiệu năng.
- **Chỉ mục DB khác search index bên ngoài.** Chỉ mục quan hệ được DBMS bảo trì theo ngữ nghĩa giao dịch của chính DB; external search cần pipeline đồng bộ riêng.
- **Cùng transaction thì có thể cùng commit/rollback.** Projection nằm trong cùng database có thể được cập nhật nguyên tử với nguồn, nhưng vẫn phải đảm bảo công thức và mọi đường ghi đúng.
- **Dual-write không tự nguyên tử.** Outbox/CDC cho một con đường bền vững để truyền thay đổi đã commit mà không phải giữ transaction mở trong khi gọi search.
- **At-least-once cần idempotency và versioning.** Event trùng, đến sai thứ tự hoặc worker gửi muộn không được làm projection lùi trạng thái.
- **Delete cần tombstone hoặc cơ chế ngăn hồi sinh.** Đặc biệt khi có replay và retention dài, chỉ xóa tài liệu mà quên version có thể làm bản cũ xuất hiện lại.
- **Eventual consistency cần SLO và cơ chế sửa lệch.** Đo freshness/visibility, backlog age, DLQ và đối soát, đồng thời có quy trình reindex an toàn khi dữ liệu hoặc mapping thay đổi.
- **Đọc theo tính đúng đắn nghiệp vụ.** Search có thể stale nhưng checkout, quyền truy cập và thao tác nhạy cảm phải dựa trên nguồn/trạng thái có thẩm quyền theo hợp đồng phù hợp.

Thiết kế nhất quán giữa bảng chính, dữ liệu dẫn xuất và chỉ mục tìm kiếm không chỉ là bài toán vận chuyển sự kiện nhanh. Nó là việc **định nghĩa rõ quyền sở hữu dữ liệu, bảo toàn ý định ghi, xử lý sai thứ tự và thất bại, rồi kiểm chứng sự hội tụ**. Khi kết hợp transaction nguồn, outbox/CDC, phiên bản dữ liệu, idempotency, reconciliation và monitoring, lớp persistence Java có thể phục vụ truy vấn nhanh mà vẫn giữ được tính đúng đắn cần thiết cho nghiệp vụ.
