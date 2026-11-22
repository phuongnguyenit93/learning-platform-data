# Đánh đổi khi dùng số tăng dần, UUID hoặc định danh phân tán

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **định danh của thực thể**, **khóa chính vật lý** và **mã nghiệp vụ**; giải thích vì sao không nên gộp chúng thành một khái niệm.
2. So sánh khóa số tăng dần, UUID ngẫu nhiên, UUID có thứ tự theo thời gian và ID do nhiều node tự sinh theo các tiêu chí: tính duy nhất, hiệu năng chỉ mục, khả năng mở rộng, bảo mật và vận hành.
3. Chọn phương án sinh ID cho dịch vụ Java dựa trên ranh giới giao dịch, mô hình quan hệ, lưu lượng ghi và số lượng nơi tạo dữ liệu.
4. Nhận diện những sai lầm thường gặp: tưởng rằng ID tăng dần phản ánh thứ tự commit, UUID là cơ chế phân quyền, hoặc ID duy nhất đồng nghĩa với thao tác có tính idempotent.
5. Lập kế hoạch kiểm thử, giám sát và chuyển đổi lược đồ ID mà không làm hỏng quan hệ giữa các bản ghi.

Bài thuộc chương **Định danh và quan hệ** trong **DATA_PERSISTENCE_FUNDAMENTALS**. Việc chọn ID là một quyết định thiết kế persistence: nó ảnh hưởng đến lược đồ, khóa ngoại, truy vấn, chỉ mục, giao dịch, lỗi kết nối, tiến hóa schema, bảo mật và hiệu năng của ứng dụng Java.

## 1. Cần định danh điều gì?

Giả sử dịch vụ quản lý đơn hàng có bản ghi:

```text
id nội bộ:        182745
public_order_id:  019ab0e7-6a75-7d0c-9d3e-0f0a8b6d7011
order_number:     HN-2026-000145
tenant_id:        58e3ad91-2ab7-418b-aa24-c374be35ec79
```

Bốn giá trị có nhiệm vụ khác nhau:

- **ID nội bộ**: khóa định danh ổn định của bản ghi trong kho dữ liệu, thường được tham chiếu bởi khóa ngoại.
- **Public ID**: giá trị API trả về cho client, có thể tách khỏi cách database đánh số bản ghi.
- **Mã nghiệp vụ**: số đơn, số hóa đơn hoặc mã chứng từ theo quy định nghiệp vụ, có thể cần định dạng và quy tắc cấp số riêng.
- **Tenant ID**: xác định phạm vi dữ liệu; có thể là một thành phần của khóa logic hoặc điều kiện phân quyền.

Khóa chính nên **ổn định, không phụ thuộc thuộc tính có thể đổi** như email, số điện thoại hoặc tên đăng nhập. Mã nghiệp vụ có thể phải thay đổi hoặc có quy tắc tuần tự riêng; vì vậy việc dùng luôn mã nghiệp vụ làm khóa chính thường khiến sửa lược đồ và các quan hệ trở nên khó khăn.

**Tính duy nhất luôn có phạm vi.** Khóa `order_number` có thể chỉ duy nhất *trong một tenant*, còn `id` được yêu cầu duy nhất toàn hệ thống. Quy tắc phải thể hiện qua ràng buộc dữ liệu, ví dụ `UNIQUE (tenant_id, order_number)`; đừng chỉ dựa vào kiểm tra “đã tồn tại chưa?” trong Java.

## 2. Các trục đánh giá khi chọn ID

| Tiêu chí | Câu hỏi cần trả lời | Tác động đến persistence |
| --- | --- | --- |
| Phạm vi duy nhất | Trong bảng, tenant, cluster hay giữa nhiều vùng? | Primary key, unique constraint và chiến lược phát hành |
| Nơi sinh | Database, dịch vụ trung tâm hay mỗi node/client? | Số lần round trip, tính sẵn sàng, giao dịch |
| Kích thước | `BIGINT` 64 bit hay UUID 128 bit? | Kích thước PK, chỉ mục và FK tham chiếu |
| Thứ tự | Có cần khóa tăng gần theo thời gian không? | Locality của B-tree, phân trang, cách tạo dữ liệu |
| Tải ghi | Một database hay nhiều writer phân tán? | Contention, hotspot, chi phí phối hợp |
| Lộ thông tin | Có bị lộ quy mô kinh doanh hoặc thời điểm tạo? | Thiết kế API và yêu cầu an toàn thông tin |
| Ngôn ngữ và giao thức | Java, SQL, JSON, JavaScript có biểu diễn nhất quán không? | Ánh xạ kiểu và tương thích dữ liệu |
| Vòng đời | Có nhập dữ liệu offline, merge hay đổi công nghệ lưu trữ? | Di chuyển, đối soát và tính bền vững của tham chiếu |

**Không có một loại ID tối ưu cho mọi tiêu chí.** Nếu lợi ích của số nguyên nhỏ là rõ rệt trong một hệ thống quan hệ tập trung, điều đó không tự động khiến nó là lựa chọn tốt nhất cho các thiết bị offline hoặc dịch vụ tạo bản ghi trên nhiều cụm độc lập.

## 3. Số nguyên tăng dần: dễ dùng, hiệu quả, nhưng gắn với nơi cấp số

Một lược đồ PostgreSQL minh họa:

```sql
CREATE TABLE orders (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    uuid NOT NULL,
    order_number text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, order_number)
);
```

Với `IDENTITY` hoặc sequence, database cấp số mới khi tạo bản ghi. Ứng dụng đọc ID trả về, rồi dùng nó làm khóa ngoại. Java có thể lấy khóa sinh ra bằng JDBC `getGeneratedKeys()` hoặc mệnh đề `RETURNING id` tùy database và driver.

### Lợi ích

- Giá trị số nguyên 64 bit có kích thước gọn: kiểu `BIGINT` thường chiếm 8 byte, trong khi UUID nhị phân chiếm 16 byte; chênh lệch còn lan sang các chỉ mục và bảng có FK.
- ID được cấp theo hướng tăng giúp các lần thêm khóa mới thường tập trung gần cuối một chỉ mục B-tree, có thể giảm page split và truy cập ngẫu nhiên so với ID hoàn toàn ngẫu nhiên.
- Dễ gỡ lỗi và truy vấn trong database; hệ quản trị quan hệ thường có hỗ trợ trực tiếp cho `IDENTITY`/sequence.
- Phù hợp khi một database hoặc một dịch vụ cấp số rõ ràng đã là thành phần trung tâm của hệ thống.

### Những hiểu lầm cần tránh

**Sequence không bảo đảm các số liền nhau.** Transaction bị rollback, cơ chế cache sequence, restart hoặc cấp số trước khi ghi thành công có thể tạo khoảng trống. Đừng lấy ID tăng dần để tính số lượng đơn hàng hoặc để đánh số hóa đơn đòi hỏi quy tắc riêng.

**Thứ tự cấp số không nhất thiết là thứ tự commit.** Transaction A có thể nhận ID 100 rồi chờ; B nhận 101 và commit trước A. `ORDER BY id` không phải định nghĩa chính xác của “đơn mới nhất” nếu nghiệp vụ cần thời điểm tạo/hoàn thành. Hãy chọn trường thời gian và quy tắc hòa giải khi trùng thời điểm.

**Không thể ghép hai database độc lập chỉ nhờ cùng một sequence cục bộ.** Nếu hai nơi đều sinh số 1, 2, 3…, dữ liệu sẽ đụng khóa khi hợp nhất. Có thể chia dải, gắn namespace, dùng bộ cấp số trung tâm hoặc chuyển sang ID sinh phân tán; mỗi cách có chi phí vận hành riêng.

**ID tuần tự dễ đoán.** Client có thể thử `/orders/182746` sau `/orders/182745`. Điều này tạo điều kiện cho hành vi dò tìm, nhưng cơ chế bảo vệ thật sự vẫn phải là **xác thực và kiểm tra quyền truy cập trên từng bản ghi**.

### Khi dùng số tăng dần

Chọn `BIGINT IDENTITY` khi dữ liệu chủ yếu ghi tại một database quan hệ, các quan hệ bằng FK dày đặc, cần chỉ mục gọn và không có yêu cầu sinh ID độc lập trước khi nối đến database. Một hệ thống lớn vẫn có thể dùng số nguyên thành công nếu cơ chế phân vùng và cấp ID được thiết kế đúng.

## 4. UUID: không cần hỏi bộ cấp số trung tâm

**UUID** là định danh 128 bit có quy ước biểu diễn chuẩn, thường thấy dưới dạng chuỗi 36 ký tự (gồm dấu gạch nối), ví dụ:

```text
d2950ad1-143f-4c6e-a0fe-cc745ce6a875
```

Hãy dùng **kiểu dữ liệu UUID gốc** của database nếu có; lưu chuỗi 36 ký tự trong `varchar` chỉ vì API dùng JSON có thể làm tốn không gian và khiến sắp xếp/so sánh phụ thuộc cách lưu chuỗi.

### UUIDv4: ngẫu nhiên

UUID phiên bản 4 sử dụng giá trị ngẫu nhiên cho 122 bit sau khi dành bit cho phiên bản và biến thể. Trong Java:

```java
import java.util.UUID;

UUID orderId = UUID.randomUUID(); // Java tạo UUID phiên bản 4
```

Ưu điểm nổi bật là từng dịch vụ có thể **tạo ID trước khi gửi lệnh ghi**, không cần xin database cấp số. Điều này tiện khi chuẩn bị sự kiện, tạo quan hệ giữa các đối tượng mới, xử lý thiết bị offline hoặc nhập dữ liệu từ nhiều hệ thống.

Xác suất trùng của UUIDv4 được tạo từ nguồn ngẫu nhiên đủ tốt là cực nhỏ, nhưng **không bằng 0**. Vì vậy database vẫn cần khóa chính/unique constraint và hệ thống cần có cách xử lý xung đột hoặc báo lỗi. Nếu nguồn ngẫu nhiên lỗi hoặc bị cấu hình sai, giả định về xác suất cũng không còn.

Mặt trái của UUIDv4 là khóa có thứ tự ngẫu nhiên. Trong một chỉ mục B-tree lớn, nhiều lần ghi có thể chạm các trang khác nhau và làm tăng chi phí cache, page split hoặc I/O. Tác động thực tế thay đổi theo database, fill factor, số lượng chỉ mục và phần cứng; phải đo với workload đại diện thay vì mặc định UUIDv4 luôn chậm.

### UUIDv7: mang thông tin thời gian và có xu hướng tăng

UUID phiên bản 7 sử dụng phần đầu biểu diễn **Unix timestamp theo mili giây**, phần còn lại chứa bit dành cho phiên bản, biến thể và dữ liệu ngẫu nhiên/bộ đếm theo cấu trúc chuẩn. Khi sinh đúng cách, UUIDv7 có xu hướng tăng theo thời gian, giúp việc thêm khóa mới thuận lợi hơn cho các cấu trúc chỉ mục cần tính cục bộ.

Đổi lại:

- Giá trị ID có thể bộc lộ thời gian tạo gần đúng.
- Đồng hồ chạy sai, clock rollback, nhiều ID trong cùng mili giây và các thuật toán xử lý monotonicity khác nhau làm cho thứ tự ID **không phải bằng chứng chắc chắn về thứ tự sự kiện hay commit**.
- Nó vẫn dài 128 bit và có thể cần thư viện sinh phù hợp với phiên bản runtime; **`UUID.randomUUID()` của Java không tạo UUIDv7**.
- Bảo đảm duy nhất phụ thuộc thuật toán sinh đúng chuẩn, entropy và cách nhiều node phối hợp (nếu dùng bộ đếm/trạng thái).

UUIDv7 đáng cân nhắc khi cần tạo ID phân tán nhưng muốn giảm tính ngẫu nhiên của thao tác ghi vào B-tree. Vẫn phải dùng thời gian nghiệp vụ và khóa phụ làm quy tắc sắp xếp khi yêu cầu chính xác.

### Các định dạng gần với UUID

**ULID** cũng có kích thước 128 bit, kết hợp timestamp mili giây và dữ liệu ngẫu nhiên, thường viết thành chuỗi 26 ký tự dùng bảng chữ cái Crockford Base32. Chuỗi ở dạng canonical có thể được so theo thứ tự từ điển nếu quy ước so sánh được giữ nhất quán; không được mặc định mọi collation hay chuyển đổi kiểu sẽ giữ nguyên đặc tính đó.

UUID, ULID và UUIDv7 không thể hoán đổi chỉ vì đều có 128 bit. Cần chọn một định dạng, kiểu cột, chuẩn chuyển đổi và cách kiểm tra tính hợp lệ thống nhất giữa Java, database, API và các consumer.

## 5. ID phân tán kiểu Snowflake: nhỏ gọn nhưng vận hành phức tạp hơn

Một họ giải pháp sinh **ID 64 bit** tại nhiều node thường dùng cách ghép:

```text
| 1 bit dấu | 41 bit thời gian | 10 bit worker | 12 bit số thứ tự |
|     0    |  millis từ epoch |  worker ID    | counter/ms       |
```

Đây là **một cấu hình Snowflake điển hình**, không phải khuôn mẫu bắt buộc cho mọi thư viện. Với bố cục này:

- 41 bit thời gian mili giây đủ biểu diễn khoảng 69,7 năm tính từ **epoch tùy chọn**.
- 10 bit worker phân biệt tối đa 1.024 mã worker đang dùng trong cùng miền cấp ID.
- 12 bit sequence hỗ trợ tối đa 4.096 ID trong một mili giây trên một worker, nếu thuật toán quản lý đúng việc tràn bộ đếm.
- ID có thể lưu dưới kiểu `BIGINT` có dấu nếu bit cao nhất luôn bằng 0; Java có thể dùng `long`.

Nếu hai node nhận **cùng worker ID** trong cùng khoảng thời gian, có thể phát hành ID trùng. Nếu đồng hồ lùi, bộ sinh ID cũng có thể tạo số trùng hoặc làm đảo thứ tự. Nếu một worker vượt năng lực trong một mili giây, nó cần chờ sang mili giây mới hoặc chuyển chính sách khác; không được tự quay counter về 0. Việc khởi tạo worker ID, đồng bộ giờ, giám sát clock skew và xử lý khởi động lại là phần **không thể bỏ qua**.

### Đánh đổi thực tế

Snowflake cung cấp giá trị `long` gọn, tạo ngay ở nhiều node và thường tăng theo thời gian, nhưng chuyển chi phí sang **hạ tầng vận hành generator**. Một thư viện “gắn vào Java” chưa đủ nếu không xác định nơi cấp worker ID và chiến lược phục hồi khi đồng hồ lỗi.

Với JSON và JavaScript, một `long` 64 bit có thể vượt số nguyên an toàn tối đa của JavaScript: `2^53 − 1`. Nếu public API dùng Snowflake ID, nên biểu diễn nó như **chuỗi ký tự** để không bị làm tròn khi client parse.

Các biến thể khác gồm dùng dịch vụ cấp dải số, một database phân phát sequence toàn cục, định danh có prefix theo vùng hoặc ID gồm nhiều trường. Chúng khác nhau ở khả năng sẵn sàng khi mất kết nối, độ trễ và điều kiện hợp nhất dữ liệu; không nên đánh đồng với một thuật toán duy nhất.

## 6. So sánh tổng hợp

| Tiêu chí | `BIGINT IDENTITY` | UUIDv4 | UUIDv7 | Snowflake kiểu 64 bit |
| --- | --- | --- | --- | --- |
| Dung lượng giá trị | 8 byte | 16 byte | 16 byte | 8 byte |
| Nơi phát hành | Database/sequence | Mỗi node | Mỗi node với generator đúng chuẩn | Mỗi node với worker ID và đồng hồ |
| Tránh trùng khi nhiều nơi sinh | Cần phối hợp/chia dải | Xác suất trùng rất thấp nếu entropy tốt | Phụ thuộc generator chuẩn và entropy | Phụ thuộc worker ID, clock, counter |
| Tính gần tăng theo thời gian | Theo **lúc cấp số** | Không | Có xu hướng | Có xu hướng |
| Độ thuận lợi với B-tree insert | Thường thuận lợi | Thường kém locality | Thường tốt hơn v4 | Thường thuận lợi |
| Có thể tự sinh offline | Không, nếu cần DB cấp ID | Có | Có | Có khi có cấu hình worker/clock an toàn |
| Lộ thông tin | Có thể lộ thứ tự và gần đúng lượng bản ghi | Ít bộc lộ từ cấu trúc ID | Có timestamp | Có timestamp/worker |
| Chi phí vận hành riêng | Sequence/điểm cấp số | Nguồn ngẫu nhiên tốt | Generator và đồng hồ | Phân phối worker ID, clock, sequence |

Bảng chỉ so sánh cơ chế định danh. **Thông lượng truy vấn và kích thước index cần benchmark trên chính database đang dùng.** Tốc độ sinh ID ở Java không phải toàn bộ chi phí ghi: vẫn còn transaction, khóa ngoại, chỉ mục phụ, log, replica và mạng.

## 7. ID có tác động đến quan hệ và truy vấn ra sao?

Trong cơ sở dữ liệu quan hệ, khóa chính của bảng cha thường được lưu thêm trong các bảng con:

```sql
-- Ví dụ dùng PostgreSQL, cả hai bảng giữ nguyên kiểu UUID.
CREATE TABLE customers (
    id        uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    email     text NOT NULL
);

CREATE TABLE orders_uuid (
    id          uuid PRIMARY KEY,
    tenant_id   uuid NOT NULL,
    customer_id uuid NOT NULL REFERENCES customers(id),
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_orders_customer_created
    ON orders_uuid (customer_id, created_at DESC);
```

Một ID rộng hơn ảnh hưởng đến nhiều nơi: bản ghi chính, chỉ mục PK, khóa ngoại, index trên FK và các cấu trúc được nhân bản. Thay kiểu khóa chính giữa chừng có thể phải sửa hàng loạt ràng buộc và đường truy cập.

Ngoài ra, **ID không giải quyết thay cho mô hình quan hệ**:

- Với `customers.id` duy nhất toàn hệ thống, `orders_uuid.customer_id` có thể tham chiếu đúng khách, nhưng điều kiện **cùng tenant** vẫn cần được bảo đảm bằng mô hình/schema hoặc kiểm tra nghiệp vụ đáng tin cậy. Nếu bắt buộc bảo đảm ở database, hãy cân nhắc khóa ngoại tổng hợp `(tenant_id, customer_id)` trỏ tới khóa unique tương ứng.
- Với khóa chính composite theo tenant, nhiều API cần truyền cả `tenant_id` lẫn `entity_id` để định danh và định tuyến đúng phạm vi.
- Với Cassandra hoặc hệ wide-column, một UUID làm partition key có thể phân bố dữ liệu tốt, nhưng truy vấn theo tenant/thời gian vẫn đòi hỏi thiết kế partition key và clustering key riêng. Chọn ID ngẫu nhiên **không tự giải quyết** mọi mẫu truy vấn.

Tách **public ID** khỏi **internal PK** cũng hữu ích nếu cần thay đổi cách phân mảnh, nhập dữ liệu hoặc tối ưu khóa ngoại nội bộ. Tuy nhiên, việc duy trì hai ID tạo thêm chỉ mục duy nhất và bước tra cứu ánh xạ.

## 8. Ví dụ Java: một API, hai cách cấp ID

### Cách A — Database cấp `BIGINT`

PostgreSQL:

```sql
CREATE TABLE demo_orders_identity (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id  uuid NOT NULL,
    note       text NOT NULL
);
```

Java JDBC (đã có `Connection` hợp lệ và được quản lý bởi tầng transaction):

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;

public final class IdentityOrderWriter {
    public long create(Connection connection, UUID tenantId, String note)
            throws SQLException {
        String sql = """
            INSERT INTO demo_orders_identity (tenant_id, note)
            VALUES (?, ?)
            RETURNING id
            """;

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setObject(1, tenantId);
            statement.setString(2, note);

            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    throw new SQLException("INSERT did not return an id");
                }
                return result.getLong("id");
            }
        }
    }
}
```

`RETURNING` là cú pháp PostgreSQL, không phải SQL mà mọi JDBC driver đều hỗ trợ. Nếu database khác, chọn cú pháp hoặc `getGeneratedKeys()` theo khả năng driver. Ứng dụng chỉ nhận ID sau khi database trả lời; **nhận được ID không đồng nghĩa transaction đã commit**.

### Cách B — Java sinh UUIDv4 trước khi ghi

PostgreSQL:

```sql
CREATE TABLE demo_orders_uuid (
    id         uuid PRIMARY KEY,
    tenant_id  uuid NOT NULL,
    note       text NOT NULL
);
```

Java:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.UUID;

public final class UuidOrderWriter {
    public UUID create(Connection connection, UUID tenantId, String note)
            throws SQLException {
        UUID id = UUID.randomUUID();
        String sql = """
            INSERT INTO demo_orders_uuid (id, tenant_id, note)
            VALUES (?, ?, ?)
            """;

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setObject(1, id);
            statement.setObject(2, tenantId);
            statement.setString(3, note);
            if (statement.executeUpdate() != 1) {
                throw new SQLException("Unexpected inserted row count");
            }
        }
        return id;
    }
}
```

Trong cách B, ứng dụng biết ID trước khi ghi, nhưng **vẫn phải coi việc ghi là chưa chắc thành công** cho đến khi transaction hoàn tất. Với lỗi timeout hoặc mất kết nối sau khi gửi lệnh, không thể suy ra record đã tồn tại hay chưa chỉ từ exception. Cần xác định rõ cách retry; ví dụ lưu lại ID của yêu cầu đang xử lý thay vì sinh UUID mới cho từng lần gửi lại.

Ví dụ JDBC sử dụng **text block**, một tính năng có từ Java 15 và có thể dùng trực tiếp trên Java 17+. Không có yêu cầu phải dùng Snowflake để đạt mục tiêu sinh ID phân tán; hãy chọn implementation đã được kiểm chứng nếu thực sự cần và có chiến lược cấp worker ID.

## 9. Tính duy nhất, idempotency và nhất quán là ba việc khác nhau

Một ID mới **không có nghĩa một lệnh nghiệp vụ sẽ chỉ diễn ra một lần**.

Ví dụ client gửi yêu cầu “tạo đơn” và bị timeout. Nếu client gửi lại rồi server sinh một UUIDv4 khác, database có thể chứa **hai đơn khác ID nhưng cùng ý định nghiệp vụ**. Dù cả hai khóa đều duy nhất, kết quả vẫn sai.

Một cách xử lý cho luồng tạo đơn:

1. Client cung cấp `Idempotency-Key` ổn định cho một yêu cầu nghiệp vụ; server kết hợp khóa đó với tenant/actor và phạm vi thao tác.
2. Database lưu ràng buộc duy nhất cho khóa idempotency tương ứng, cùng trạng thái/kết quả của yêu cầu.
3. Khi nhận retry, server nhận diện yêu cầu đã xử lý hoặc đang xử lý, trả kết quả nhất quán theo hợp đồng API; không tạo thêm thực thể.
4. Đường xử lý ghi phải giải quyết race condition bằng transaction, unique constraint hoặc cơ chế điều phối phù hợp, không chỉ bằng truy vấn “check trước rồi insert”.

Cơ chế này độc lập với việc primary key là `BIGINT`, UUIDv4 hay Snowflake. Nếu ghi qua nhiều dịch vụ, cần cân nhắc outbox/event deduplication hoặc chiến lược hòa giải vì hai hệ dữ liệu không tự nhiên có chung một transaction ACID.

**Đừng dùng ID làm phân quyền.** UUID khó đoán hơn ID liên tiếp, nhưng ai biết hoặc đoán được ID vẫn có thể yêu cầu tài nguyên. Ở lớp service Java, luôn kiểm tra principal có quyền trên bản ghi/tenant trước khi trả về hoặc sửa đổi. Với ID có timestamp hoặc worker ID, cũng phải xem liệu việc lộ cấu trúc ID có vi phạm yêu cầu riêng tư hay không.

## 10. Cách chọn theo tình huống

### Tình huống A: ứng dụng nội bộ với một PostgreSQL

Hệ thống quản lý kho có nhiều bảng FK, lưu lượng ghi vừa phải, mọi thao tác tạo đều đi qua một database. `BIGINT IDENTITY` thường là lựa chọn đơn giản và tiết kiệm. Nếu cần public ID khó đoán hơn, có thể bổ sung một UUID duy nhất riêng cho API.

### Tình huống B: thiết bị có thể offline nhiều ngày

Ứng dụng di động tạo ghi chú hoặc sự kiện khi không có mạng, sau đó đồng bộ về server. UUIDv4 được sinh trước lúc lưu cho phép các đối tượng giữ nguyên ID khi đồng bộ; cần kiểm soát xung đột nghiệp vụ và xác thực nguồn dữ liệu. UUIDv7 cũng có thể phù hợp nếu có generator đáng tin cậy và bạn chấp nhận ảnh hưởng của đồng hồ thiết bị.

### Tình huống C: nhiều dịch vụ ghi với thông lượng rất cao

Nhiều node cần tạo ID mà không phụ thuộc round trip đến database trung tâm. UUIDv7 có thể giảm yêu cầu điều phối; Snowflake giảm độ rộng khóa xuống `BIGINT` nhưng đòi hỏi quản lý worker ID, thời gian và bộ đếm nghiêm ngặt. Quyết định dựa trên benchmark, tính sẵn sàng và năng lực vận hành, không chỉ dựa trên tốc độ sinh ID trong một microbenchmark.

### Tình huống D: số hóa đơn phải có quy tắc pháp lý

Dùng một **mã hóa đơn nghiệp vụ** được cấp theo quy định áp dụng, tách khỏi primary key. Không tự hứa rằng database sequence hay Snowflake sẽ cho chuỗi liên tục không có khoảng trống hoặc phản ánh chính xác thứ tự giao dịch đã hoàn thành.

## 11. Đổi loại ID khi hệ thống đã có dữ liệu

Chuyển từ số tăng dần sang UUID là thay đổi lớn nếu khóa đã xuất hiện trong nhiều bảng, API và sự kiện. Một lộ trình giảm gián đoạn thường gồm:

1. **Kiểm kê**: xác định bảng cha, FK, chỉ mục, log, cache, URL, sự kiện và tích hợp ngoài đang lưu ID cũ.
2. **Bổ sung khóa mới**: thêm cột nullable và tạo ánh xạ ID cũ → ID mới, bảo đảm duy nhất; không đổi primary key ngay.
3. **Backfill có kiểm soát**: điền ID mới cho bản ghi hiện tại, xử lý lỗi và xác nhận không có bản ghi trùng/thiếu.
4. **Chuyển đường ghi/đọc**: thực hiện theo từng giai đoạn; trong thời gian chuyển tiếp, duy trì ánh xạ, quan sát sai lệch và xử lý retry.
5. **Chuyển quan hệ và tích hợp**: cập nhật các FK, API và consumer bằng cơ chế tương thích; kiểm tra referential integrity và toàn vẹn sự kiện.
6. **Hoàn tất cutover**: chỉ bỏ cách định danh cũ sau khi mọi đường đọc và ghi đã chuyển, có biện pháp phục hồi và đã kiểm chứng dữ liệu.

Với bảng lớn, thêm ràng buộc hoặc tạo index có thể tốn nhiều thời gian và khóa bảng tùy hệ quản trị. Quy trình triển khai cần xem xét rolling deployment, phiên bản ứng dụng, kế hoạch backup/restore và đặc điểm DDL của database đang dùng.

## 12. Bài tập thiết kế và tự kiểm tra

**Đề bài.** Một nền tảng bán hàng hiện có một PostgreSQL trung tâm với 30 bảng dùng FK `bigint`. Sắp tới ứng dụng cho phép nhân viên bán hàng tạo phiếu offline trên điện thoại, đồng thời có dịch vụ xử lý đơn hàng ở hai vùng. Public API đang dùng `/orders/{id}`.

Hãy đề xuất:

1. Có giữ `bigint` làm PK nội bộ hay đổi toàn bộ sang UUID? Nêu tiêu chí quyết định.
2. ID nào được tạo trên điện thoại khi offline và cách ánh xạ về bản ghi chính thức?
3. Nếu dùng Snowflake ở hai vùng, ai cấp worker ID, cần xử lý trường hợp clock rollback và sequence overflow ra sao?
4. Khi client gửi tạo đơn hai lần vì timeout, ID duy nhất đã đủ ngăn trùng đơn chưa?
5. Nếu người dùng thay ID trên URL để truy cập đơn thuộc tenant khác, ứng dụng Java phải làm gì?

**Gợi ý trả lời:** Có thể giữ `bigint` cho quan hệ nội bộ hiện hữu và bổ sung một `client_request_id`/public ID duy nhất để đồng bộ offline, tránh migration PK lớn khi chưa có lý do đủ mạnh. Server kiểm tra idempotency key và ràng buộc duy nhất trong phạm vi tenant, duy trì ánh xạ từ ID offline sang đơn thực, xử lý xung đột nghiệp vụ. Nếu chọn Snowflake thì cấp worker ID không trùng, kiểm soát đồng hồ và chặn/đợi khi tràn sequence. Mọi truy vấn tài nguyên phải kiểm tra quyền của principal và tenant, không phụ thuộc ID khó đoán.

**Checklist trước khi chốt thiết kế:**

- Đã xác định phạm vi duy nhất, nguồn phát hành ID và hành vi khi offline/mất kết nối.
- Kiểu ID được lưu thống nhất ở DB, Java, JSON và các consumer; `long` lớn không bị làm tròn trong JavaScript.
- Có ràng buộc PK/unique tại database và chiến lược xử lý xung đột.
- Đã đo tải ghi, độ rộng PK/FK, tốc độ index và phân bố khóa với dữ liệu thực tế.
- Có cơ chế riêng cho idempotency, phân quyền, thứ tự nghiệp vụ và mã chứng từ.
- Nếu ID mang thời gian hoặc worker ID, các rủi ro clock, lộ metadata, vận hành đã được xử lý.
- Có phương án migration và phục hồi cho các quan hệ, API, sự kiện nếu sau này cần đổi ID.

**Nguyên tắc thực hành:** ID nên ổn định và đủ duy nhất trong phạm vi xác định; còn thứ tự nghiệp vụ, quyền truy cập, giao dịch và tính không trùng lặp thao tác phải được thiết kế **riêng**. Trong hệ persistence Java, một lựa chọn ID phù hợp là lựa chọn làm cho đường ghi, truy vấn, quan hệ và vận hành có thể giải thích, kiểm chứng và mở rộng được.
