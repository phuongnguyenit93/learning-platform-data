# Khóa tự nhiên và khóa do hệ thống tạo

Trong một ứng dụng Java, mỗi khách hàng, đơn hàng hay sản phẩm cần được nhận diện ổn định để truy vấn, cập nhật và liên kết với dữ liệu khác. Có hai hướng phổ biến: dùng **một thuộc tính có ý nghĩa nghiệp vụ làm khóa** (khóa tự nhiên) hoặc gán **một mã định danh riêng do hệ thống sinh ra** (khóa thay thế, còn gọi là surrogate key). Quyết định này ảnh hưởng đến độ bền của quan hệ, khả năng đổi dữ liệu nghiệp vụ, tính duy nhất, hiệu năng chỉ mục và cách tiến hóa cơ sở dữ liệu.

Bài học thuộc chương **Định danh và quan hệ** trong mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Mục tiêu là thiết kế định danh và ràng buộc dữ liệu bền vững, triển khai ranh giới persistence cho Java và nhận biết tác động của giao dịch, kiểm soát đồng thời, bảo mật, migration và hiệu năng. Các ví dụ SQL dùng PostgreSQL để minh họa cú pháp cụ thể; khi dùng hệ quản trị khác cần đối chiếu khả năng hỗ trợ.

## 1. Phân biệt định danh, khóa và tính duy nhất

Giả sử bảng khách hàng có các cột:

| Cột | Ví dụ | Vai trò |
|---|---|---|
| \`id\` | \`8421\` | Mã nội bộ do cơ sở dữ liệu sinh |
| \`tenant_id\` | \`4e1a…\` | Không gian sở hữu của khách hàng |
| \`customer_code\` | \`KH-2026-018\` | Mã khách hàng theo nghiệp vụ |
| \`email\` | \`an@example.org\` | Thông tin liên hệ có thể thay đổi |
| \`display_name\` | \`An Nguyễn\` | Thuộc tính mô tả |

Một số khái niệm dễ nhầm:

- **Khóa ứng viên (candidate key):** một tập thuộc tính tối thiểu có thể phân biệt duy nhất mọi hàng trong phạm vi ràng buộc đã xác định.
- **Khóa chính (primary key, PK):** khóa ứng viên được chọn làm định danh chính ở mức cơ sở dữ liệu. PK phải duy nhất và không được \`NULL\`.
- **Khóa thay thế (alternate key):** khóa ứng viên khác vẫn được ràng buộc duy nhất nhưng không làm PK.
- **Khóa ngoại (foreign key, FK):** một hoặc nhiều cột ở bảng con tham chiếu khóa được chấp nhận ở bảng cha; ràng buộc FK giúp ngăn liên kết tới bản ghi không tồn tại.
- **Khóa tự nhiên (natural key):** khóa được tạo từ dữ liệu có ý nghĩa trong miền nghiệp vụ, chẳng hạn \`(tenant_id, customer_code)\`.
- **Khóa do hệ thống tạo / khóa thay thế (surrogate key):** mã định danh không đại diện cho một thuộc tính nghiệp vụ, chẳng hạn ID tăng dần hoặc UUID ngẫu nhiên.

Các khái niệm này thuộc **những chiều phân loại khác nhau**: khóa tự nhiên vẫn có thể được chọn làm PK; khóa do hệ thống tạo cũng có thể được chọn làm PK. Dù chọn surrogate PK, **tính duy nhất nghiệp vụ không tự biến mất**. Nếu mỗi tenant chỉ được có một \`customer_code\`, phải tiếp tục ràng buộc \`UNIQUE (tenant_id, customer_code)\`.

> **Nguyên tắc trọng tâm:** Phân biệt “định danh một bản ghi qua các thay đổi của nó” với “giá trị nghiệp vụ nào không được trùng tại một thời điểm hoặc trong một phạm vi”.

## 2. Khóa tự nhiên: thuận lợi và rủi ro

Khóa tự nhiên sử dụng thuộc tính vốn đã tồn tại trong nghiệp vụ làm định danh. Chẳng hạn, mã quốc gia theo một tiêu chuẩn nhất định hoặc mã phòng học trong phạm vi một tòa nhà có thể được cân nhắc, tùy quy tắc thay đổi của miền dữ liệu.

Ví dụ một hệ thống bán hàng quy định mã khách hàng chỉ duy nhất **trong từng tenant**:

~~~text
tenant_id = T1, customer_code = KH-001   -> khách hàng A
tenant_id = T2, customer_code = KH-001   -> khách hàng B
~~~

Ở đây, riêng \`customer_code\` **không** phải khóa duy nhất toàn hệ thống. Tập \`(tenant_id, customer_code)\` mới có thể là khóa ứng viên nếu nghiệp vụ bảo đảm quy tắc đó.

### Điều kiện để khóa tự nhiên là lựa chọn tốt

Một khóa tự nhiên đáng cân nhắc làm PK khi nó:

1. **Thực sự duy nhất** trong phạm vi đã công bố, kể cả sau nhập dữ liệu, sáp nhập hệ thống và đồng bộ với đối tác.
2. **Ổn định theo vòng đời thực thể:** không đổi chỉ vì người dùng sửa thông tin thông thường.
3. **Luôn có mặt** trước lúc tạo thực thể, không phải đợi hệ thống khác cấp mã.
4. **Có biểu diễn nhất quán:** quy tắc viết hoa, khoảng trắng, Unicode, dấu phân cách, múi giờ hoặc chuẩn hóa được công bố rõ.
5. **Có kích thước và độ nhạy cảm phù hợp** để xuất hiện trong chỉ mục, FK, log và truy vấn.
6. **Có quy tắc sửa sai:** nếu mã bị cấp sai hoặc tiêu chuẩn thay đổi, hệ thống biết cách chuyển đổi an toàn.

Ví dụ, dùng email làm PK thường tiềm ẩn rủi ro: email có thể đổi, có thể chưa được xác minh, có trường hợp dùng chung hoặc chịu quy tắc chuẩn hóa khác nhau giữa nhà cung cấp. Mã SKU cũng có thể bị tái phân loại; số giấy tờ tùy thân có thể bị thay thế và thuộc dữ liệu cá nhân nhạy cảm. Không có thuộc tính nào “tự nhiên” đồng nghĩa với “vĩnh viễn bất biến”.

### Khóa tự nhiên ghép

Khóa ghép chứa nhiều cột. Ví dụ \`(country_code, tax_number)\` nếu **chính miền nghiệp vụ** bảo đảm tính duy nhất của tổ hợp. Nó thể hiện rõ bối cảnh nhưng có thể lan truyền qua nhiều FK, làm câu lệnh join và cập nhật khóa phức tạp hơn.

Nếu khóa tự nhiên được dùng trong quan hệ, việc đổi giá trị có thể đòi hỏi cập nhật hàng loạt hàng con hoặc dựa vào chính sách \`ON UPDATE CASCADE\`. Cả hai đều cần xem xét tải ghi, lock, giao dịch và tích hợp với hệ thống bên ngoài.

## 3. Khóa do hệ thống tạo: tách định danh khỏi thuộc tính nghiệp vụ

Surrogate key là định danh được hệ thống phát sinh, không cần chứa thông tin về khách hàng. Nó thường là giá trị đơn, ổn định và thích hợp làm đích tham chiếu FK:

~~~text
customers.id = 8421
customers.customer_code = "KH-001"

Sau khi đổi customer_code thành "KH-NEW":
customers.id vẫn là 8421
orders.customer_id vẫn là 8421
~~~

Sơ đồ quan hệ:

~~~mermaid
erDiagram
    TENANTS ||--o{ CUSTOMERS : owns
    CUSTOMERS ||--o{ ORDERS : places
    TENANTS {
      uuid tenant_id PK
    }
    CUSTOMERS {
      bigint id PK
      uuid tenant_id FK
      text customer_code "unique per tenant"
    }
    ORDERS {
      bigint id PK
      uuid tenant_id FK
      bigint customer_id FK
    }
~~~

Sơ đồ minh họa tính liên kết bằng ID nội bộ; với dữ liệu nhiều tenant, còn phải bảo đảm đơn hàng và khách hàng thuộc **cùng tenant**, như ở phần SQL bên dưới.

### Các cách sinh khóa thường gặp

| Cách sinh | Ưu điểm | Điểm cần cân nhắc |
|---|---|---|
| **Sequence / identity dạng số** | Gọn, dễ đánh chỉ mục, thường thuận lợi cho B-tree tăng dần | Thường cần bộ phát ID hoặc phân vùng phạm vi khi nhiều nơi cùng sinh; có thể lộ mức tăng số lượng nếu công khai |
| **UUID v4** | Xác suất trùng cực nhỏ khi sinh ngẫu nhiên đúng cách; có thể sinh ngoài DB | Chiếm nhiều byte hơn số nguyên; tính ngẫu nhiên có thể làm tăng chi phí ghi/chỉ mục tùy backend |
| **UUID v7 / ID có thành phần thời gian** | Hỗ trợ sắp thứ tự xấp xỉ thời điểm tạo, có thể có tính địa phương tốt hơn với chỉ mục | Có thể tiết lộ thông tin thời gian; thứ tự hoàn toàn và tính duy nhất tùy thuật toán, nguồn ngẫu nhiên và triển khai |
| **ID phát sinh phân tán kiểu Snowflake** | Có thể sinh trong nhiều tiến trình, thường kèm thời gian/node/sequence | Phải quản lý node ID, đồng hồ và quy tắc chống trùng; thành phần thời gian có thể bị suy ra |
| **Mã tạo bởi ứng dụng theo quy tắc riêng** | Có thể tương thích hệ thống cũ | Nguy cơ trùng, thiếu an toàn đồng thời hoặc phải duy trì bộ cấp mã phức tạp |

**Không có bộ phát khóa nào thay thế ràng buộc \`PRIMARY KEY\` / \`UNIQUE\` ở cơ sở dữ liệu.** Cơ chế sinh ID tốt giúp giảm xác suất va chạm; constraint là tuyến bảo vệ cuối cùng để từ chối trùng lặp.

Với identity/sequence, **khoảng trống trong dãy ID là bình thường** do rollback, cấp phát trước hoặc restart. Không dùng ID tăng dần làm số chứng từ phải liên tục theo yêu cầu pháp lý. Nếu cần mã hóa đơn theo nghiệp vụ, hãy thiết kế riêng quy tắc cấp mã và tính duy nhất của mã đó.

## 4. So sánh hai hướng thiết kế

| Tiêu chí | Khóa tự nhiên làm PK | Surrogate key làm PK |
|---|---|---|
| Ý nghĩa | Mang ý nghĩa trong miền nghiệp vụ | Chỉ mang nghĩa định danh |
| Thay đổi quy tắc nghiệp vụ | Có thể cần cập nhật PK/FK và hệ tích hợp | Thường chỉ đổi các thuộc tính nghiệp vụ |
| Khả năng liên kết từ bảng khác | Phụ thuộc độ dài và độ ổn định, có thể là khóa ghép | Thường dùng một cột ID ngắn, ít thay đổi |
| Ràng buộc duy nhất nghiệp vụ | PK có thể bao hàm đúng quy tắc đó | Cần thêm \`UNIQUE\` cho business key |
| Tra cứu bằng mã nghiệp vụ | Truy cập trực tiếp qua PK | Dùng chỉ mục unique trên mã để tìm ID trước |
| Mức lộ thông tin khi hiển thị | Có thể làm lộ dữ liệu nghiệp vụ | ID tuần tự dễ đoán; UUID khó đoán hơn nhưng không thay kiểm tra quyền |
| Chỉ mục và lưu trữ | Khóa dài/ghép có thể làm tăng độ rộng chỉ mục/FK | Có thêm cột/chỉ mục cho business key; chi phí phụ thuộc loại ID |
| Tương tác với hệ ngoài | Thuận tiện nếu cùng dùng chuẩn định danh ổn định | Cần ánh xạ ID nội bộ với external ID/business ID |

Không có đáp án luôn đúng. Khóa tự nhiên ngắn, bất biến và được chuẩn hóa có thể rất hợp lý. Surrogate key thường hữu ích khi thực thể có vòng đời dài, nhiều quan hệ hoặc mã nghiệp vụ dễ bị sửa. Việc dùng surrogate key **không miễn phí**: bảng vẫn cần index/constraint cho các truy vấn theo mã nghiệp vụ.

## 5. Thiết kế minh họa với PostgreSQL

Xét hệ thống nhiều tenant quản lý khách hàng và đơn hàng. Yêu cầu:

- Mỗi khách hàng có một ID nội bộ không đổi.
- Mã khách hàng là duy nhất **trong cùng tenant** nhưng có thể thay đổi theo quy tắc nghiệp vụ.
- Đơn hàng phải thuộc cùng tenant với khách hàng.
- Mỗi đơn có mã nghiệp vụ riêng, duy nhất trong tenant.

Một schema minh họa:

~~~sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY
);

CREATE TABLE customers (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    customer_code TEXT NOT NULL,
    display_name TEXT NOT NULL,
    CONSTRAINT uq_customers_tenant_code
        UNIQUE (tenant_id, customer_code),
    -- Cho phép FK ghép ở bảng orders tham chiếu cặp tenant + id.
    CONSTRAINT uq_customers_tenant_id
        UNIQUE (tenant_id, id)
);

CREATE TABLE orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    customer_id BIGINT NOT NULL,
    order_code TEXT NOT NULL,
    CONSTRAINT uq_orders_tenant_code
        UNIQUE (tenant_id, order_code),
    CONSTRAINT fk_orders_customer_tenant
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers (tenant_id, id)
);
~~~

Ở bảng \`customers\`, \`id\` là PK do DB cấp; \`(tenant_id, customer_code)\` là khóa nghiệp vụ được bảo vệ bằng UNIQUE. Với \`orders\`, FK ghép \`(tenant_id, customer_id)\` giúp chặn việc tạo một đơn dưới tenant T1 nhưng trỏ tới khách hàng của T2. Khóa \`UNIQUE (tenant_id, id)\` có phần dư thừa về mặt logic vì \`id\` đã unique, nhưng tạo khóa đích hợp lệ cho FK ghép trong PostgreSQL; thiết kế này có thêm chi phí chỉ mục cần cân nhắc.

Trong một kiến trúc khác có thể chọn **PK ghép \`(tenant_id, id)\`** ngay từ đầu, nhất là khi phân vùng theo tenant. Phương án nào phù hợp phụ thuộc cách ứng dụng định tuyến, join, partitioning và bảo vệ dữ liệu giữa các tenant.

### Ví dụ chèn và truy vấn

~~~sql
-- Sau khi có tenant hợp lệ, DB cấp customers.id.
INSERT INTO customers (tenant_id, customer_code, display_name)
VALUES (:tenant_id, 'KH-001', 'An Nguyen')
RETURNING id;

-- Tìm khách hàng bằng business key, luôn kèm tenant.
SELECT id, customer_code, display_name
FROM customers
WHERE tenant_id = :tenant_id AND customer_code = 'KH-001';

-- Đổi business key, không đụng tới id hoặc các FK đặt trên id.
UPDATE customers
SET customer_code = 'KH-NEW'
WHERE tenant_id = :tenant_id AND id = :customer_id;
~~~

Ký hiệu \`:tenant_id\`, \`:customer_id\` là tham số đặt tên ở tầng ứng dụng/ORM, **không phải cú pháp tham số của PostgreSQL khi chạy trực tiếp bằng psql**. Với JDBC thuần, dùng dấu \`?\` trong \`PreparedStatement\`.

Nếu một tenant đã có \`KH-NEW\`, câu UPDATE sẽ vi phạm \`uq_customers_tenant_code\`. Đó là đúng mục tiêu: cơ sở dữ liệu bảo vệ quy tắc nghiệp vụ ngay cả khi hai yêu cầu cùng chạy.

**Đối với soft delete:** nếu muốn tái sử dụng \`customer_code\` sau khi xóa logic, constraint UNIQUE thông thường có thể không phù hợp. PostgreSQL có thể dùng unique partial index cho bản ghi đang hoạt động, chẳng hạn \`WHERE deleted_at IS NULL\`; tuy nhiên cần quyết định ý nghĩa của mã bị tái sử dụng trong lịch sử và khi khôi phục dữ liệu. Không tự chuyển sang “unique trên bản ghi active” nếu hệ thống yêu cầu mã không được cấp lại vĩnh viễn.

### NULL và chuẩn hóa mã

Trong PostgreSQL, unique constraint thông thường cho phép nhiều hàng có \`NULL\` trong cột liên quan; vì vậy \`NOT NULL\` là cần thiết khi trường thực sự bắt buộc. Hãy định nghĩa rõ mã \`KH-001\` và \`kh-001\` có được coi là trùng nhau hay không, cũng như có cắt khoảng trắng hoặc chuẩn hóa Unicode không. Có thể chuẩn hóa đầu vào và dùng expression index / kiểu dữ liệu phù hợp, nhưng phải chọn **một quy tắc nhất quán** để tránh application check và DB constraint hiểu khác nhau.

## 6. Java persistence: ID riêng, business key riêng

Ở tầng ứng dụng, ID nội bộ và mã nghiệp vụ nên được biểu diễn thành hai khái niệm khác nhau. Ví dụ Java 17 với JDBC:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;

record CustomerId(long value) {}
record NewCustomer(UUID tenantId, String code, String displayName) {}

final class JdbcCustomerRepository {
    private final DataSource dataSource;

    JdbcCustomerRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    CustomerId create(NewCustomer customer) throws SQLException {
        String sql = """
            INSERT INTO customers (tenant_id, customer_code, display_name)
            VALUES (?, ?, ?)
            RETURNING id
            """;
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setObject(1, customer.tenantId());
            statement.setString(2, customer.code());
            statement.setString(3, customer.displayName());
            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    throw new SQLException("INSERT returned no customer ID");
                }
                return new CustomerId(result.getLong("id"));
            }
        }
    }

    boolean renameCode(UUID tenantId, CustomerId id, String newCode)
            throws SQLException {
        String sql = """
            UPDATE customers
               SET customer_code = ?
             WHERE tenant_id = ? AND id = ?
            """;
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, newCode);
            statement.setObject(2, tenantId);
            statement.setLong(3, id.value());
            return statement.executeUpdate() == 1;
        }
    }
}
~~~

Đây là ví dụ tập trung vào thiết kế định danh và ranh giới persistence, chưa gồm kiểm tra dữ liệu đầu vào, authorization, transaction nghiệp vụ hay chuyển lỗi SQL sang lỗi domain. Nếu ứng dụng dùng Spring Data JPA/Hibernate, ý tưởng tương tự: trường \`@Id\` đại diện ID ổn định, còn mã nghiệp vụ được khai báo ràng buộc unique và tra cứu qua repository riêng. Chọn đúng chiến lược \`@GeneratedValue\` cho backend và kiểm tra tác động tới batch insert.

### Ba lỗi triển khai thường gặp

**1. Chỉ kiểm tra trùng bằng SELECT rồi INSERT**

~~~text
Request A: SELECT code KH-001 -> chưa tồn tại
Request B: SELECT code KH-001 -> chưa tồn tại
Request A: INSERT code KH-001 -> thành công
Request B: INSERT code KH-001 -> vi phạm UNIQUE
~~~

Đây là race condition kiểu *check then act*. \`SELECT\` trước chỉ cải thiện thông báo cho người dùng; **UNIQUE constraint** mới ngăn dữ liệu trùng khi chạy đồng thời. Ứng dụng cần xử lý lỗi vi phạm unique như conflict nghiệp vụ. Với PostgreSQL, SQLSTATE \`23505\` báo unique violation, nhưng nên kiểm tra tên constraint hoặc ngữ cảnh vì một bảng có thể có nhiều unique constraint khác nhau.

**2. Dùng ID do DB sinh làm business code**

ID sequence có thể có khoảng trống, bị reset trong môi trường mới, thay đổi sau import hoặc khác giữa các hệ. Đừng hứa với nghiệp vụ rằng số \`customers.id\` cũng là “mã khách hàng chính thức”. Mã hóa đơn, mã hợp đồng hoặc số chứng từ thường có quy định riêng về thứ tự, hình thức và khả năng tra cứu.

**3. Dùng object identity trộn với database identity**

Trong ORM, hai đối tượng Java có thể mô tả cùng một hàng nhưng là hai instance khác nhau; ngược lại hai entity mới đều chưa có ID. Triển khai \`equals()\`/\`hashCode()\` cho entity có ID sinh muộn cần cẩn thận với trạng thái transient, proxy và hash-based collection. Việc chọn surrogate key **không tự giải quyết** quy tắc equality của object. Cần thống nhất trong nhóm phát triển và kiểm tra hành vi khi entity được persist.

## 7. Khóa ngoại, quan hệ và cập nhật khóa

Một hệ thống persistence cần giữ cho định danh của hàng cha và quan hệ hàng con nhất quán:

~~~mermaid
flowchart TD
    A["Khách hàng id=8421<br/>code=KH-001"] --> B["Đơn hàng 1001<br/>customer_id=8421"]
    A --> C["Đơn hàng 1002<br/>customer_id=8421"]
    D["Đổi code thành KH-NEW"] --> A
    E["PK id=8421 không đổi"] --> B
    E --> C
~~~

Sơ đồ thể hiện ưu điểm của việc giữ ID ổn định khi chỉ thay đổi mã nghiệp vụ. Nhưng khi nghiệp vụ yêu cầu **gộp hai khách hàng**, **tách một hồ sơ thành hai**, hoặc **xóa một thực thể**, hệ thống vẫn phải quyết định chuyển các FK, giữ lịch sử và kiểm tra ràng buộc liên quan. Surrogate ID không tự giải quyết các thay đổi ý nghĩa của danh tính.

Một số chính sách FK cần cân nhắc:

- **RESTRICT / NO ACTION khi xóa:** phù hợp khi cần chặn xóa khách hàng còn đơn hàng; lựa chọn chi tiết và thời điểm kiểm tra phụ thuộc backend.
- **ON DELETE CASCADE:** thuận tiện với dữ liệu con thật sự phụ thuộc vòng đời của cha, nhưng nguy hiểm với lịch sử đơn hàng cần lưu giữ.
- **ON UPDATE CASCADE:** có thể hỗ trợ cập nhật khóa được tham chiếu; tuy nhiên nếu khóa chính do hệ thống tạo và bất biến thì thường không cần thay đổi.
- **Không có FK vật lý:** đôi khi xuất hiện ở hệ phân tán hoặc kho NoSQL; khi đó ứng dụng phải chịu trách nhiệm phát hiện và xử lý tham chiếu mồ côi.

**Đừng dùng việc biết ID như một phép kiểm tra quyền.** Với hệ nhiều tenant, mọi thao tác lấy/cập nhật vẫn phải áp chính sách tenant, xác thực và quyền truy cập phù hợp. ID khó đoán chỉ giúp giảm việc dò tìm đơn giản, không chống được truy cập trái phép.

## 8. Phân tán, nhập dữ liệu và định danh bên ngoài

Định danh thường phải tồn tại qua nhiều hệ thống. Ví dụ CRM cấp \`crmCustomerId = C-77\`, trong khi dịch vụ bán hàng lưu \`customers.id = 8421\`. Phân biệt:

~~~text
Nội bộ ứng dụng:      customer.id = 8421
Mã nghiệp vụ:         customer.customer_code = KH-001
Hệ CRM:               source = "CRM", external_id = "C-77"
~~~

Nếu dữ liệu có thể được nhập từ nhiều nguồn, cần gắn **nguồn cấp mã** vào external ID; \`C-77\` từ CRM có thể khác \`C-77\` từ hệ khác. Có thể tạo bảng ánh xạ \`(source_system, external_id) -> customer_id\` với UNIQUE cho cặp nguồn và mã, kiểm tra khi nhập trùng. Khi retry nhập cùng bản ghi, hãy dùng business/external key ổn định để nhận diện thay vì phát sinh một surrogate ID mới rồi coi đó là bản ghi khác.

Trong hệ phân tán nhiều dịch vụ:

- Sequence/identity do một DB cấp sẽ đơn giản trong phạm vi một DB nhưng cần giải pháp khi sinh ID đồng thời ở nhiều vùng độc lập.
- UUID hoặc bộ sinh ID phân tán cho phép cấp trước khi lưu, nhưng phải kiểm soát cấu hình nguồn ngẫu nhiên, đồng hồ hoặc worker/node ID theo thuật toán.
- Phân vùng theo tenant hay theo ID ảnh hưởng truy vấn, giao dịch nhiều shard và địa phương dữ liệu. Không chọn UUID v4, UUID v7 hay số nguyên chỉ dựa trên nhận định “cái nào nhanh hơn” khi chưa thử tải đúng backend và mẫu truy vấn thực tế.
- Nếu event mang ID, định nghĩa rõ đó là ID nội bộ của một bounded context hay định danh dùng chung; tránh nhầm \`orderId\` của hai dịch vụ khác nhau.

Bản thân việc tạo ID ở client cũng làm thay đổi tình huống retry: sau timeout, client có thể kiểm tra hoặc retry bằng **cùng một ID**. Tuy vậy, để tránh tác động nghiệp vụ trùng lặp, vẫn cần quy tắc idempotency và transaction thích hợp.

## 9. Migration từ khóa tự nhiên sang surrogate key

Giả sử schema cũ dùng \`customers.customer_code\` làm PK, còn \`orders.customer_code\` làm FK. Theo thời gian, nghiệp vụ cho phép đổi mã khách hàng và muốn chuyển quan hệ sang ID ổn định.

Migration nên được chia thành các bước an toàn, có khả năng quan sát:

1. **Khảo sát phụ thuộc:** tìm bảng con, constraint, query, API, batch job, file xuất và ứng dụng ngoài đang dựa vào mã khách hàng; xác định mã có duy nhất toàn hệ hay chỉ theo tenant.
2. **Bổ sung cột ID:** thêm ID nullable hoặc có default/bộ cấp phù hợp; backfill ID cho các hàng cũ theo từng đợt nếu bảng lớn, kiểm tra không trùng và không thiếu.
3. **Thêm khóa tham chiếu mới:** bổ sung \`orders.customer_id\`, tra cứu theo business key cũ để điền ID; kiểm tra hàng con không tìm được hàng cha, dữ liệu trùng và sai tenant.
4. **Giữ dữ liệu đồng bộ trong giai đoạn chuyển tiếp:** bảo đảm thao tác tạo/sửa mới ghi đủ dữ liệu tương ứng, theo cách có transaction hoặc cơ chế đồng bộ được thiết kế và giám sát. Không để bảng con cũ tiếp tục phát sinh mà thiếu ID mới.
5. **Thiết lập constraint mới:** thêm \`NOT NULL\`, \`UNIQUE\`/PK và FK phù hợp khi dữ liệu đã sạch; trên bảng lớn, chọn chiến lược tạo/kiểm tra constraint phù hợp để tránh khóa bảng ngoài dự kiến.
6. **Chuyển đường đọc/ghi:** cập nhật repository, ORM, API và job; giám sát số lỗi tra cứu, conflict và hàng tham chiếu mồ côi. Giữ unique constraint cho business key ngay cả khi không còn là PK.
7. **Loại bỏ cột liên kết cũ và constraint cũ:** chỉ sau khi xác minh không còn người dùng chúng và có chiến lược rollback/khôi phục phù hợp.

Chuyển PK là thay đổi schema có thể đòi hỏi thời gian khóa và tái tạo index tùy cơ sở dữ liệu. Ở hệ thống đang chạy, nên có kế hoạch deploy theo phiên bản tương thích, backup, giám sát tiến độ và phương án xử lý lỗi. Không chạy một lệnh thay PK trực tiếp trên bảng lớn rồi giả định các FK và ứng dụng sẽ tự thích nghi.

## 10. Bảo mật, vận hành và đo hiệu năng

Khóa định danh xuất hiện trong log, URL, message queue, cache và bảng chỉ mục. Khi lựa chọn và triển khai, cần chú ý:

- **Bảo mật:** tránh dùng số giấy tờ, email hoặc token xác thực làm PK công khai. ID tăng dần có thể dễ đoán; ID ngẫu nhiên khó đoán hơn nhưng mọi request vẫn cần kiểm tra quyền sở hữu bản ghi.
- **Giảm PII trong log:** log ID nội bộ hoặc correlation ID có thể đủ cho truy vết; có quy định kiểm soát truy cập log và thời gian lưu log.
- **Sao lưu và khôi phục:** bảo đảm ID và quan hệ FK được khôi phục nhất quán; khi import sang môi trường khác, đừng mặc định sequence hiện tại đã vượt \`MAX(id)\` của dữ liệu được nhập.
- **Chỉ mục:** PK và unique constraint thường kéo theo index; thêm unique business key tăng chi phí ghi và không gian lưu trữ, nhưng cần để giữ bất biến dữ liệu. Index có tiền tố tenant hữu ích khi truy vấn theo tenant và business code.
- **Quan sát:** theo dõi lỗi unique/FK, độ trễ insert và join, kích thước index, phân bố truy vấn theo tenant, tốc độ tăng ID và số bản ghi chưa backfill trong quá trình migration.
- **Giới hạn của định danh:** hai bản ghi có hai ID khác nhau vẫn có thể đại diện cùng một người thật; phát hiện trùng thực thể đòi hỏi logic domain hoặc quy trình đối soát.

Nếu có yêu cầu hiệu năng, hãy đo truy vấn **theo ID**, **theo business key**, và **join theo FK** với quy mô dữ liệu, kiểu khóa, index và tỉ lệ đọc/ghi gần thực tế. Không thể suy ra trực tiếp rằng BIGINT luôn nhanh hơn UUID hoặc khóa tự nhiên trong mọi mô hình lưu trữ, nhất là khi chi phí mạng, truy vấn và chỉ mục phụ khác nhau.

## 11. Quy trình ra quyết định

Khi thiết kế một thực thể mới, hãy trả lời các câu hỏi theo thứ tự:

1. **Thực thể là gì?** Có trường hợp đổi tên, đổi mã, hợp nhất, tách, tái sử dụng mã hay chuyển tenant không?
2. **Có natural key được bảo đảm thật sự không?** Tính duy nhất nằm trong tenant, quốc gia, nguồn dữ liệu, khoảng thời gian hay toàn hệ thống?
3. **Bao nhiêu quan hệ sẽ tham chiếu bản ghi này?** Khóa ghép/khóa có thể thay đổi sẽ gây chi phí sửa quan hệ như thế nào?
4. **Ứng dụng đọc theo gì?** Theo ID nội bộ, mã nghiệp vụ, external ID hay nhiều thuộc tính khác?
5. **ID được sinh ở đâu?** Trong DB, trong ứng dụng, hay bởi nhiều dịch vụ? Khi retry và import phải tránh trùng ra sao?
6. **Bất biến nào phải do DB bảo vệ?** PK, UNIQUE, NOT NULL, FK và kiểm tra tenant cần được định nghĩa độc lập với mã Java.
7. **Ai được biết ID?** Có API công khai, phân quyền, log, trace và quy định về dữ liệu cá nhân không?

Một mẫu phù hợp với nhiều hệ thống nghiệp vụ là: **surrogate PK bất biến để tham chiếu**, cộng **UNIQUE trên khóa nghiệp vụ theo đúng phạm vi**, và **FK bảo vệ quan hệ**. Đây là lựa chọn thực dụng chứ không phải quy tắc bắt buộc cho mọi thực thể; bảng tham chiếu nhỏ có mã chuẩn ổn định vẫn có thể dùng natural PK hiệu quả.

## 12. Bài thực hành: đổi mã khách hàng khi đã có đơn hàng

Một ứng dụng Java quản lý khách hàng cho nhiều tenant:

- Tenant T1 và T2 đều có thể dùng \`customer_code = KH-001\`.
- Một khách hàng có thể đổi \`customer_code\` nhưng các đơn hàng lịch sử phải tiếp tục trỏ đúng khách hàng.
- Khi hai request cùng tạo một mã trong cùng tenant, chỉ một request được thành công.
- Hệ thống nhập dữ liệu từ CRM và cần tránh tạo khách hàng trùng khi job được retry.

**Nhiệm vụ:**

1. Chọn PK cho \`customers\` và \`orders\`; ghi rõ kiểu dữ liệu và nơi cấp ID.
2. Xác định business key và các constraint \`UNIQUE\` cần thiết, kể cả khóa từ CRM.
3. Vẽ quan hệ \`orders -> customers\` và giải thích cách bảo đảm cùng tenant.
4. Viết câu lệnh SQL đổi mã khách hàng, xử lý trường hợp mã mới đã tồn tại.
5. Mô tả race condition của hai lệnh \`SELECT\` rồi \`INSERT\`, chỉ rõ constraint nào bảo vệ dữ liệu.
6. Đề xuất đường migration nếu bảng đơn hàng trước đây tham chiếu trực tiếp \`customer_code\`.
7. Nêu cách kiểm chứng sau khôi phục backup và các chỉ số cần giám sát trong lúc chuyển đổi.

**Gợi ý lời giải:** dùng ID nội bộ bất biến cho hai bảng, đặt \`UNIQUE (tenant_id, customer_code)\` trên khách hàng và \`UNIQUE (source_system, external_id)\` trong bảng ánh xạ hệ ngoài (điều chỉnh phạm vi nếu dữ liệu thực tế yêu cầu). Bảng \`orders\` có FK ghép \`(tenant_id, customer_id)\` để ràng buộc tenant. Khi đổi mã, thực hiện UPDATE theo tenant và ID trong giao dịch phù hợp; xử lý unique violation thành lỗi conflict. Với import, tra cứu/upsert theo external key ổn định và xử lý race tại DB. Khi migration, thêm ID, backfill FK mới, đồng bộ hai đường ghi trong thời gian chuyển tiếp rồi kiểm tra dữ liệu trước khi loại bỏ khóa cũ.

### Câu hỏi tự kiểm tra

- Vì sao email thường không phải lựa chọn tốt làm PK dù có thể đặt \`UNIQUE\`?
- Nếu đã có PK do hệ thống tạo, vì sao vẫn cần \`UNIQUE (tenant_id, customer_code)\`?
- Khác nhau giữa \`id\`, \`customer_code\` và \`external_id\` là gì?
- Việc một sequence tạo ra ID không liên tục có phải lỗi lưu trữ không?
- Khi thay natural PK bằng surrogate PK, phần nào của quan hệ FK, migration và kiểm soát đồng thời phải được xem xét?
- UUID khó đoán có thay thế việc kiểm tra quyền truy cập dữ liệu không?

Kết thúc bài học, người học cần chọn được định danh phù hợp với vòng đời thực thể, nêu chính xác ràng buộc duy nhất của nghiệp vụ, thiết kế quan hệ FK ổn định và triển khai truy cập Java theo ID và khóa nghiệp vụ mà vẫn bảo đảm tính nhất quán khi dữ liệu thay đổi.
