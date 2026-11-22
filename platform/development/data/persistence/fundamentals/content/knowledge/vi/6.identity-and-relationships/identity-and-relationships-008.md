# Tính toàn vẹn tham chiếu và xử lý bản ghi không còn tồn tại

Trong chương **Định danh và quan hệ** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, một câu hỏi quan trọng là: **điều gì xảy ra khi bản ghi A đang tham chiếu bản ghi B, nhưng B đã bị xóa, ngừng hoạt động hoặc không thể truy cập?** Ví dụ, đơn hàng tham chiếu khách hàng, dòng đơn tham chiếu đơn hàng, bình luận tham chiếu bài viết và hóa đơn tham chiếu giao dịch thanh toán. Nếu các tham chiếu mất ý nghĩa, ứng dụng Java có thể hiển thị sai, gây lỗi lúc truy vấn, hoặc làm hỏng lịch sử nghiệp vụ.

Để thiết kế persistence đúng, cần kết hợp **tính toàn vẹn tham chiếu (referential integrity)** ở lược đồ dữ liệu với **quy tắc vòng đời** ở tầng nghiệp vụ. Các cơ chế này liên quan trực tiếp đến khóa, giao dịch, cô lập, đồng thời, truy vấn và chỉ mục; đồng thời ảnh hưởng tới xử lý lỗi kết nối, tiến hóa schema, bảo mật, backup, khôi phục và hiệu năng.

**Mục tiêu học tập:**

- Phân biệt định danh, quan hệ, khóa ngoại, bản ghi mồ côi và đối tượng không còn khả dụng về mặt nghiệp vụ.
- Giải thích các hành động `ON DELETE RESTRICT`, `NO ACTION`, `CASCADE`, `SET NULL` và `SET DEFAULT` cùng điều kiện sử dụng.
- Thiết kế xóa vật lý, xóa mềm, vô hiệu hóa, lưu lịch sử và thay thế quan hệ mà không phá vỡ bất biến.
- Xử lý tham chiếu không tồn tại trong Java/JDBC và API, kể cả khi có nhiều thao tác ghi đồng thời.
- Nhận diện giới hạn của khóa ngoại khi các thực thể nằm ở những database hoặc dịch vụ khác nhau; xây dựng cơ chế đối soát.

## 1. Tham chiếu có ý nghĩa gì?

Xét quan hệ:

~~~text
Khách hàng (Customer) 1 ----- N Đơn hàng (Order)
Đơn hàng  (Order)    1 ----- N Dòng đơn (OrderLine)
~~~

Mỗi đơn hàng có `customer_id` và mỗi dòng đơn có `order_id`. **Khóa chính (primary key)** định danh một hàng trong bảng. **Khóa ngoại (foreign key)** là ràng buộc buộc giá trị khóa tham chiếu phải tồn tại ở bảng được tham chiếu, với lưu ý rằng giá trị `NULL` có quy tắc riêng theo định nghĩa ràng buộc.

Một khóa ngoại hợp lệ trả lời câu hỏi hẹp: **“giá trị khóa có trỏ tới hàng hợp lệ trong phạm vi database và điều kiện ràng buộc này không?”** Nó chưa trả lời “khách hàng có đang được phép đặt hàng?”, “tài khoản đã bị vô hiệu hóa chưa?”, “đơn hàng có còn được chỉnh sửa không?” hay “người dùng hiện tại có quyền nhìn thấy hàng đó không?”.

| Tình huống | Ý nghĩa kỹ thuật | Cần quyết định nghiệp vụ |
| --- | --- | --- |
| Khóa ngoại trỏ tới hàng đang tồn tại | Quan hệ có thể hợp lệ về cấu trúc | Hàng đích còn hoạt động, có đúng tenant và được phép sử dụng không? |
| Khóa ngoại trỏ tới hàng bị xóa vật lý | **Tham chiếu mồ côi (dangling/orphan reference)** nếu không có ràng buộc ngăn chặn | Phục hồi, đổi tham chiếu, giữ snapshot hay xóa dữ liệu phụ thuộc? |
| Hàng đích còn nhưng `deleted_at` khác `NULL` | Khóa ngoại vẫn có thể hoàn toàn hợp lệ | Có cho dùng lại đối tượng đã xóa mềm hay chỉ hiển thị lịch sử? |
| Khóa ngoại `NULL` | Quan hệ tùy chọn không có đích được chỉ định | Đây là “chưa gán”, “không biết” hay một trạng thái không hợp lệ? |
| Dịch vụ đích trả `404` hoặc timeout | Không đủ dữ kiện để khẳng định đã xóa | Phân biệt không tồn tại, không được phép xem và tạm thời không truy cập được |

**Bản ghi không còn tồn tại** vì thế có ít nhất ba trường hợp cần phân biệt: *xóa thật trong kho dữ liệu*, *không còn sử dụng theo quy tắc nghiệp vụ*, và *không thể quan sát được tại thời điểm đọc*. Cách giải quyết khác nhau đáng kể.

### 1.1. Định danh ổn định và không tái sử dụng

Không nên dùng tên hiển thị hoặc giá trị có thể đổi như email làm khóa tham chiếu chính chỉ vì chúng “dễ đọc”. Một `customer_id` ổn định giúp quan hệ không đổi khi khách sửa email. Nếu sử dụng khóa tự nhiên, phải đánh giá tính bất biến, tính duy nhất và tác động của đổi khóa.

Định danh đã bị xóa **không nên được tái sử dụng cho thực thể khác**. Nếu ID `C-42` từng thuộc khách A rồi được cấp lại cho khách B, bản ghi lịch sử cũ có thể vô tình trỏ sang người mới, dù khóa ngoại vẫn thỏa về mặt kỹ thuật. Với hệ thống cần lưu vết lâu dài, hãy có chính sách cấp ID, lưu dấu xóa (tombstone) và bảo vệ lịch sử.

## 2. Khóa ngoại bảo vệ toàn vẹn tham chiếu trong database

Ví dụ sau dùng cú pháp **PostgreSQL**. Các tên bảng và quy tắc là minh họa, cần điều chỉnh theo domain thật:

~~~sql
CREATE TABLE customer_account (
    customer_id UUID PRIMARY KEY,
    display_name TEXT NOT NULL,
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE purchase_order (
    order_id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer_account(customer_id)
        ON DELETE RESTRICT
);

CREATE TABLE order_line (
    order_id UUID NOT NULL,
    line_no INTEGER NOT NULL,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_line_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_order(order_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_purchase_order_customer
    ON purchase_order (customer_id);
~~~

Hai quy tắc khác nhau được áp dụng có chủ đích:

- Một khách hàng không thể bị xóa vật lý khi còn đơn hàng tham chiếu tới họ: `ON DELETE RESTRICT` chặn thao tác xóa đó.
- Nếu một đơn hàng **được phép xóa vật lý theo chính sách nghiệp vụ**, các `order_line` của nó được xóa cùng bằng `ON DELETE CASCADE`. Điều này **không** có nghĩa mọi đơn đã xác nhận đều nên được xóa vật lý.

Khóa ngoại thường được database kiểm tra ngay trong thao tác ghi và có cơ chế khóa/đồng thời để bảo vệ tính toàn vẹn. Nó giúp tránh lỗi kiểu “hai request chạy gần nhau, một bên xóa parent trong khi bên kia tạo child”. Việc kiểm tra tồn tại ở Java trước khi `INSERT` hữu ích để tạo thông báo tốt nhưng **không thay thế được ràng buộc database**.

### 2.1. Khóa ngoại và giá trị NULL

Với khóa ngoại một cột thông thường, một giá trị `NULL` thường không bắt buộc khớp với hàng đích. Nhưng nếu quan hệ là bắt buộc, hãy dùng `NOT NULL` như `purchase_order.customer_id`.

Với khóa ngoại nhiều cột, cách xử lý khi một hoặc nhiều thành phần là `NULL` phụ thuộc chế độ `MATCH` và DBMS. Tránh suy luận rằng mọi tổ hợp có null đều được chấp nhận. Cần kiểm tra ràng buộc cụ thể và áp dụng `NOT NULL` cho những thành phần bắt buộc.

## 3. Chọn hành động khi bản ghi đích bị xóa

Các hành động khóa ngoại liên quan đến **xóa vật lý** hàng ở bảng được tham chiếu. Chúng không tự xử lý xóa mềm, vô hiệu hóa tài khoản hay xóa trong dịch vụ khác.

| `ON DELETE` | Điều xảy ra khi xóa parent | Khi có thể phù hợp | Điều phải cẩn trọng |
| --- | --- | --- | --- |
| `RESTRICT` | Từ chối xóa nếu còn hàng tham chiếu | Lịch sử đơn hàng phải giữ quan hệ tới khách | Phải có quy trình đóng/ngừng hoạt động thay cho xóa thật |
| `NO ACTION` | Từ chối nếu ràng buộc không thỏa ở thời điểm kiểm tra | Mặc định an toàn khi không muốn thay đổi child | Ở DB hỗ trợ ràng buộc hoãn, thời điểm kiểm tra có thể khác `RESTRICT` |
| `CASCADE` | Xóa các child tham chiếu theo hành động của database | Dòng thuộc một aggregate chỉ tồn tại cùng parent | Xóa lan rộng, ảnh hưởng lịch sử và quy định lưu giữ |
| `SET NULL` | Đặt cột FK ở child thành `NULL` | Quan hệ có thể bỏ gán, như nhân viên phụ trách hiện thời | Cột phải cho phép `NULL`; domain phải hiểu trạng thái không có đích |
| `SET DEFAULT` | Gán giá trị mặc định cho cột FK của child | Có bản ghi mặc định được quản lý hợp lệ, nếu nghiệp vụ cho phép | Giá trị mặc định vẫn phải thỏa FK; có nguy cơ “đẩy vào tài khoản giả” |

Trong PostgreSQL, `NO ACTION` có thể được kiểm tra ở cuối transaction nếu constraint được khai báo `DEFERRABLE` và chế độ kiểm tra được hoãn. `RESTRICT` không cho hoãn chính thao tác hạn chế đó theo cơ chế này. Mặc định, kiểm tra thường diễn ra ngay. Không dựa vào khác biệt này nếu chưa kiểm chứng cú pháp và semantics của DBMS đang dùng.

### 3.1. Tại sao CASCADE phải được thiết kế thận trọng?

Giả sử `Customer → Order → Payment` đều có `ON DELETE CASCADE`. Một lệnh xóa customer có thể làm mất toàn bộ chứng từ thanh toán, dữ liệu cần đối soát và lịch sử nghiệp vụ. Điều đó có thể trái với quy định kế toán và khiến việc khôi phục khó khăn.

Ngược lại, dòng đơn nháp hoặc hàng tạm chỉ có ý nghĩa khi parent còn tồn tại có thể phù hợp với cascade, **nếu việc xóa parent là hợp lệ**. Trước khi chọn cascade, hãy đặt câu hỏi “child có ý nghĩa độc lập hay nghĩa vụ lưu giữ riêng không?”.

Một mẫu an toàn là **chặn hard delete đối với dữ liệu giao dịch cần lưu**, dùng trạng thái `CANCELLED`, `ARCHIVED` hoặc `deleted_at` theo chính sách, còn cascade chỉ dùng cho dữ liệu phụ thuộc thực sự có thể xóa.

### 3.2. Ví dụ SET NULL đúng ngữ nghĩa

Giả sử đơn hàng có nhân viên phụ trách hiện tại nhưng vẫn tồn tại khi nhân viên nghỉ việc:

~~~sql
CREATE TABLE support_agent (
    agent_id UUID PRIMARY KEY,
    display_name TEXT NOT NULL
);

CREATE TABLE support_assignment (
    ticket_id UUID PRIMARY KEY,
    assigned_agent_id UUID NULL REFERENCES support_agent(agent_id)
        ON DELETE SET NULL
);
~~~

Khi agent bị xóa vật lý, `assigned_agent_id` trở thành `NULL` và ticket vẫn tồn tại. Nhưng nếu cần biết *ai từng xử lý ticket*, nên lưu nhật ký phân công riêng; giá trị `NULL` sau xóa không cung cấp lịch sử đó.

## 4. “Không còn tồn tại” trong domain khác với “không còn hàng” trong database

Ba trạng thái xóa/ẩn thường gặp:

1. **Hard delete:** hàng biến mất khỏi bảng; database xử lý ràng buộc FK theo chính sách.
2. **Soft delete:** hàng còn nguyên, được đánh dấu `deleted_at` hoặc trạng thái `DELETED`; FK vẫn có thể hợp lệ.
3. **Deactivate/archive:** hàng còn nhưng không được phép dùng trong thao tác mới; có thể vẫn được đọc cho mục đích lịch sử.

Ví dụ:

~~~sql
UPDATE customer_account
SET deleted_at = CURRENT_TIMESTAMP
WHERE customer_id = :customer_id
  AND deleted_at IS NULL;
~~~

Lệnh trên không xóa hàng khỏi `customer_account`; mọi `purchase_order.customer_id` trước đó vẫn tham chiếu tới một khóa hợp lệ. **Khóa ngoại không kiểm tra điều kiện `deleted_at IS NULL`.** Do đó, nếu ứng dụng chỉ dùng FK, nó vẫn có thể tạo đơn mới cho khách đã bị vô hiệu hóa.

### 4.1. Thiết kế quy tắc tham chiếu đến hàng active

Một cách kiểm tra trong PostgreSQL là khóa parent **trong cùng transaction** trước khi tạo đơn:

~~~sql
BEGIN;

SELECT customer_id
FROM customer_account
WHERE customer_id = :customer_id
  AND deleted_at IS NULL
FOR UPDATE;

-- Chỉ tiếp tục nếu tìm thấy đúng một hàng.
INSERT INTO purchase_order(order_id, customer_id, status)
VALUES (:order_id, :customer_id, 'DRAFT');

COMMIT;
~~~

Đoạn mã minh họa **quy tắc điều phối giữa các đường ghi**. Thao tác soft delete phải tuân thủ quy trình khóa/kiểm tra tương thích để không tạo trạng thái nghiệp vụ sai. Nếu chính sách là “không được vô hiệu hóa khách khi còn đơn đang xử lý”, đường soft delete cần khóa customer, kiểm tra đơn liên quan và quyết định chặn hoặc xử lý đơn trong transaction phù hợp. Nếu chính sách cho phép vô hiệu hóa sau khi đơn nháp đã tạo, thứ tự commit cần được hiểu và chấp nhận.

Không nên tin rằng câu `SELECT deleted_at IS NULL` chạy **trước** transaction sẽ bảo đảm điều kiện tại thời điểm `INSERT`: giữa hai câu lệnh, request khác có thể vô hiệu hóa khách. Một phương án khác là ràng buộc bổ sung, trigger hoặc mô hình trạng thái có thể kiểm tra ngay khi ghi; lựa chọn tùy nghiệp vụ và đặc tính DBMS.

### 4.2. Khóa ngoại không thay thế kiểm tra tenant và quyền

Trong hệ nhiều khách hàng (multi-tenant), `customer_id` tồn tại vẫn chưa đủ: order của tenant A không được tham chiếu customer thuộc tenant B. Có thể dùng **khóa ngoại ghép** qua `(tenant_id, customer_id)`, cùng khóa duy nhất phù hợp trên bảng parent:

~~~sql
CREATE TABLE tenant_customer (
    tenant_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    PRIMARY KEY (tenant_id, customer_id)
);

CREATE TABLE tenant_order (
    order_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES tenant_customer(tenant_id, customer_id)
);
~~~

Ràng buộc này giúp ngăn cross-tenant reference ở tầng dữ liệu. Ứng dụng vẫn phải xác thực `tenant_id` từ danh tính đã kiểm chứng, kiểm tra quyền và giới hạn truy vấn; FK không phải hệ thống phân quyền.

## 5. Xử lý tham chiếu không tồn tại trong Java/JDBC

Giả sử endpoint tạo đơn nháp nhận `customerId`. Bất kể API đã kiểm tra customer hay chưa, **database vẫn là điểm xác nhận cuối cùng** cho ràng buộc tham chiếu trong cùng kho giao dịch.

### 5.1. Câu INSERT để database bảo vệ khóa ngoại

~~~sql
INSERT INTO purchase_order(order_id, customer_id, status)
VALUES (:order_id, :customer_id, 'DRAFT');
~~~

Khi `customer_id` không tồn tại, PostgreSQL thông thường báo **SQLSTATE `23503` (foreign_key_violation)**. Khi đơn hàng trùng `order_id`, nó thường báo `23505` (unique_violation). API không nên gộp mọi `SQLException` thành “khách hàng không tồn tại”: lỗi kết nối, timeout hoặc lỗi khác có nguyên nhân và cách retry khác nhau.

### 5.2. Ví dụ JDBC quản lý transaction

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;

public final class OrderWriter {
    private final DataSource dataSource;

    public OrderWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void createDraft(UUID orderId, UUID customerId)
            throws SQLException {
        String sql = """
                INSERT INTO purchase_order(order_id, customer_id, status)
                VALUES (?, ?, 'DRAFT')
                """;

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                try (PreparedStatement statement =
                        connection.prepareStatement(sql)) {
                    statement.setObject(1, orderId);
                    statement.setObject(2, customerId);
                    statement.executeUpdate();
                }
                connection.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
~~~

Lớp trên minh họa **lưu một đơn nháp có khóa ngoại**. Tầng ứng dụng cần kiểm tra xác thực, quyền, tenant, trạng thái active và quy tắc tạo đơn trước khi gọi; đó là phần chưa được thực hiện trong ví dụ. Nếu cần gộp thêm dòng đơn, outbox hoặc audit, các thao tác đó phải nằm trong cùng transaction phù hợp.

Ở ranh giới HTTP, có thể ánh xạ lỗi theo hợp đồng:

| Trường hợp | Cách trả lời thường phù hợp |
| --- | --- |
| ID đích sai định dạng | `400 Bad Request` với thông báo kiểu dữ liệu |
| ID đích không tồn tại hoặc không khả dụng theo quy tắc input | `404 Not Found` hoặc `422 Unprocessable Content` tùy ngữ nghĩa API; tránh lộ dữ liệu không được phép xem |
| Quan hệ xung đột với trạng thái hiện tại | `409 Conflict` khi hợp đồng biểu diễn được xung đột |
| Resource đã được xóa vĩnh viễn và API có thể xác nhận an toàn | `410 Gone` chỉ khi biết chắc và chủ động công bố trạng thái đó |
| Database tạm thời không truy cập được | Lỗi phía server có thể retry theo chính sách, không báo nhầm thành `404` |

Không bắt buộc mỗi hệ phải chọn cùng mã HTTP. Cần nhất quán với hợp đồng API và bảo mật. **Không thể suy ra “đã xóa” chỉ từ lỗi mạng hoặc việc một cache không tìm thấy dữ liệu.**

### 5.3. ORM/JPA: cascade và orphanRemoval không giống hệt FK

Trong JPA/Hibernate, `CascadeType.REMOVE` hoặc `orphanRemoval = true` có thể làm ORM phát lệnh xóa đối tượng liên quan. Đây là **hành vi lifecycle ở tầng ORM**. `ON DELETE CASCADE` là **ràng buộc/hoạt động ở tầng database**. Chúng có thể cùng tồn tại nhưng không nhất thiết phát cùng số lệnh, thứ tự xử lý hay tác động tới cache/lifecycle callback.

Ví dụ `orphanRemoval = true` trên danh sách `OrderLine` có thể xóa dòng khi ứng dụng bỏ nó khỏi collection được quản lý; điều này chỉ đúng nếu dòng không có vòng đời độc lập. Cần thử các trường hợp xóa trực tiếp bằng SQL, xóa qua ORM và thao tác bulk vì đường nào bỏ qua xử lý của ORM vẫn chịu ràng buộc database.

Đừng dùng cascade để “hết lỗi FK” nếu chưa hiểu quyền sở hữu và nhu cầu giữ lịch sử của từng quan hệ.

## 6. Xóa parent và ghi child đồng thời: race condition

Một lỗi phổ biến:

1. Request A gọi `SELECT customer_id` và thấy khách tồn tại.
2. Request B xóa khách.
3. Request A ghi đơn tham chiếu khách vừa bị xóa.

Nếu không có ràng buộc FK, có thể tạo orphan. Nếu có FK hợp lệ, database sẽ phối hợp thao tác và **không cho kết quả commit phá vỡ ràng buộc**. Yêu cầu A có thể bị chặn/chờ rồi thất bại hoặc B không thể xóa, tùy thời điểm, loại thao tác, mức cô lập và DBMS.

**Không nên dựa vào kiểm tra tồn tại trước rồi mới ghi để giải quyết đồng thời.** Cần đặt bất biến ở database hoặc một giao thức ghi có thẩm quyền.

### 6.1. Trường hợp parent bị xóa mềm

Khi B chỉ chạy `UPDATE customer_account SET deleted_at = ...`, FK vẫn được thỏa. Do đó phải thiết kế quy tắc giao dịch và khóa rõ ràng nếu yêu cầu “không tạo đơn mới sau khi tài khoản đã bị vô hiệu hóa” cần được bảo đảm chặt. Ví dụ, cả đường tạo đơn và đường vô hiệu hóa đều khóa hàng customer theo một thứ tự nhất quán; đường vô hiệu hóa kiểm tra các điều kiện liên quan và ghi trạng thái trong cùng transaction.

Khóa hàng có thể gây chờ khi có nhiều thao tác vào cùng customer. Cần đo lock wait, deadlock, throughput, đặt timeout và xây dựng cơ chế retry cho lỗi tạm thời. Không phải cứ tăng isolation level cao nhất là tốt nhất: hãy chọn giải pháp từ bất biến cần bảo vệ và kết quả kiểm thử tranh chấp.

### 6.2. Nếu kết nối đứt ngay lúc commit

Tạo đơn có thể đã thành công nhưng client chưa nhận phản hồi. Gửi lại với ID mới có thể tạo đơn trùng dù FK vẫn hoàn toàn hợp lệ. Khóa ngoại **không giải quyết idempotency**. Cần `request_id` ổn định, ràng buộc duy nhất theo nghiệp vụ và tra cứu kết quả cũ trước khi retry.

Tương tự, lỗi xóa sau khi client nhận timeout có thể đã commit. Không tự lặp một chuỗi thao tác bù khi chưa xác định trạng thái. Kết hợp mã yêu cầu, version và audit/outbox để đối soát.

## 7. Bản ghi mồ côi: phát hiện và xử lý dữ liệu đã hỏng

Nếu database luôn bật FK đúng, dữ liệu mới không thể vi phạm ràng buộc đó ở trạng thái đã được kiểm tra. Orphan thường xuất hiện trong **dữ liệu cũ chưa có FK**, quá trình import/migration bỏ kiểm tra, hệ không hỗ trợ FK hoặc liên kết qua các database/dịch vụ khác nhau.

### 7.1. Tìm tham chiếu đứt bằng truy vấn

~~~sql
-- Đơn hàng có customer_id nhưng không tìm thấy hàng customer tương ứng:
SELECT o.order_id, o.customer_id
FROM purchase_order AS o
LEFT JOIN customer_account AS c
    ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;

-- Cách tương đương với NOT EXISTS:
SELECT o.order_id, o.customer_id
FROM purchase_order AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM customer_account AS c
    WHERE c.customer_id = o.customer_id
);
~~~

Hai truy vấn trên kiểm tra **hàng đích bị thiếu vật lý**. Chúng không nhận diện hàng đã xóa mềm. Đối với trường hợp “có hàng nhưng không còn active”, truy vấn riêng:

~~~sql
SELECT o.order_id, o.customer_id, c.deleted_at
FROM purchase_order AS o
JOIN customer_account AS c
    ON c.customer_id = o.customer_id
WHERE c.deleted_at IS NOT NULL;
~~~

Không được xem mọi đơn trỏ tới khách đã xóa mềm là dữ liệu sai. Đơn lịch sử có thể **phải giữ tham chiếu** để phục vụ đối soát; chỉ việc tạo đơn mới với khách không active mới bị cấm theo một chính sách cụ thể.

### 7.2. Chọn chiến lược sửa theo ý nghĩa dữ liệu

| Loại dữ liệu | Hướng xử lý có thể phù hợp | Điều kiện trước khi sửa |
| --- | --- | --- |
| Bản ghi tạm, có thể tái tạo | Xóa orphan hoặc dựng lại từ nguồn | Xác minh không có nghĩa vụ lưu lịch sử |
| Dữ liệu giao dịch phải giữ | Khôi phục parent từ backup, giữ snapshot lịch sử hoặc chuyển sang quan hệ archive hợp lệ | Có bằng chứng định danh và trạng thái parent gốc |
| Quan hệ tùy chọn | `SET NULL` hoặc bỏ liên kết | Cho phép về mặt nghiệp vụ và cột nullable |
| Liên kết nhập sai ID | Ánh xạ lại sang đúng parent | Có quy tắc đối soát đủ chắc; không đoán theo tên giống nhau |
| Tham chiếu đến dịch vụ ngoài | Retry xác minh, dùng tombstone, cảnh báo hoặc quy trình bù | Phân biệt lỗi mạng với xóa thật |

**Không dùng một lệnh xóa hàng loạt để “dọn sạch orphan” nếu chưa phân loại dữ liệu.** Với hóa đơn, thanh toán và lịch sử thay đổi, xóa orphan có thể xóa luôn chứng cứ cần thiết. Mọi sửa dữ liệu nên có thống kê trước/sau, bản backup/điểm phục hồi phù hợp, log kiểm toán và người sở hữu nghiệp vụ phê duyệt chính sách.

## 8. Thêm ràng buộc FK vào hệ thống đã có dữ liệu

Nếu bảng `purchase_order` đã chứa hàng triệu bản ghi mà trước đây không có FK, việc thêm ràng buộc có thể thất bại vì orphan cũ. Với PostgreSQL, một chiến lược là:

1. Kiểm kê các liên kết đứt bằng `LEFT JOIN`/`NOT EXISTS`, phân nhóm theo nguồn và thời gian.
2. Chọn cách sửa cụ thể: khôi phục parent, đặt null ở quan hệ tùy chọn, ánh xạ lại hoặc loại dữ liệu tạm khi được phép.
3. Tạo chỉ mục hỗ trợ truy vấn/xóa theo `customer_id` trên bảng child, đánh giá ảnh hưởng tới ghi.
4. Thêm FK bằng `NOT VALID` để **tránh kiểm tra toàn bộ hàng cũ ngay tại thời điểm thêm ràng buộc**.
5. Sau khi sửa các hàng cũ, chạy `VALIDATE CONSTRAINT`; kiểm tra kết quả và theo dõi lỗi của các đường ghi mới.

~~~sql
-- Ví dụ khi FK chưa tồn tại; không chạy lại trên schema ở phần 2.
ALTER TABLE purchase_order
ADD CONSTRAINT fk_order_customer
FOREIGN KEY (customer_id)
REFERENCES customer_account(customer_id)
ON DELETE RESTRICT
NOT VALID;

-- Chạy sau khi đã đối soát và sửa dữ liệu lịch sử.
ALTER TABLE purchase_order
VALIDATE CONSTRAINT fk_order_customer;
~~~

`NOT VALID` ở PostgreSQL **không có nghĩa cho phép các thay đổi mới tạo thêm vi phạm**: ràng buộc mới vẫn được áp dụng với những hàng mới/được thay đổi thuộc phạm vi kiểm tra, trong khi các hàng tồn tại trước đó chưa được quét xác minh cho tới khi validate. Chi tiết lock, thời gian chạy và hỗ trợ cú pháp phụ thuộc DBMS/phiên bản; cần lên kế hoạch migration và đo trên dữ liệu đại diện.

**Chú ý:** ví dụ DDL ở phần 2 đã tạo FK `fk_order_customer`. Các câu trong phần này mô tả *kịch bản một schema cũ chưa có ràng buộc*, không phải bước chạy tiếp trên cùng database đã tạo ở trên.

### 8.1. Chỉ mục và chi phí kiểm tra FK

Ở PostgreSQL, khai báo FK **không tự động tạo index trên cột tham chiếu của bảng child**. Khi xóa hoặc cập nhật khóa parent, DB có thể phải tìm các child liên quan. Index `purchase_order(customer_id)` có thể làm thao tác tìm child nhanh hơn, đồng thời tăng chi phí ghi và dung lượng index. Cần xem query plan, tần suất xóa/cập nhật parent và khối lượng dữ liệu để lựa chọn.

Khóa chính/unique ở phía parent phải có ràng buộc phù hợp cho đích tham chiếu. Với FK ghép, kiểu dữ liệu và thứ tự cột index cũng quan trọng. Đừng thêm index bằng công thức bất biến cho mọi hệ quản trị.

## 9. Quan hệ giữa các dịch vụ: khi không có FK chung

Trong hệ thống phân tán, Order có thể dùng một database riêng, Customer dùng một database khác. Khi đó FK của Order DB **không thể trực tiếp bảo vệ hàng Customer ở database khác** như một ràng buộc cục bộ. Một lệnh tạo đơn thường mang `customerId`, nhưng phép gọi API kiểm tra Customer ở thời điểm T không chứng minh Customer vẫn active ở T+1.

~~~mermaid
flowchart LR
    A["Order Service"] --> OD[("Order DB: customerId")]
    A -->|"Đọc/command theo hợp đồng"| C["Customer Service"]
    C --> CD[("Customer DB")]
    C -->|"CustomerDeactivated + version"| E["Event stream / outbox"]
    E --> P["Order projection / đối soát"]
~~~

Khi không có giao dịch chung, cần thiết kế **hợp đồng vòng đời và tính nhất quán**:

- **Quyền sở hữu:** Customer quyết định danh tính và trạng thái tài khoản; Order quyết định trạng thái đơn hàng và lưu ID/snapshot cần thiết.
- **Quy tắc xóa:** Customer có thể từ chối xóa/vô hiệu hóa khi còn nghĩa vụ cần xử lý, hoặc phát sự kiện để Order cập nhật khả năng thao tác mới. Phải xác định cửa sổ trễ được chấp nhận.
- **Tombstone:** lưu dấu “đã xóa” cùng ID và phiên bản để tránh tái sử dụng hoặc tái xuất hiện từ event cũ; thiết kế retention theo nhu cầu.
- **Sự kiện đáng tin cậy:** transactional outbox, event ID, version và consumer idempotent giúp phát lại khi lỗi, tránh xóa hoặc ghi đè sai vì sự kiện đến trễ/lặp.
- **Đối soát:** định kỳ so sánh tham chiếu ở Order với Customer, phân loại khác biệt và có quy trình sửa đã kiểm chứng.
- **Dữ liệu lịch sử:** Order có thể giữ snapshot tên giao hàng hoặc địa chỉ tại thời điểm đặt, ngay cả khi hồ sơ hiện tại thay đổi; cần chính sách bảo vệ thông tin cá nhân.

Nếu bất biến “không tạo đơn sau khi Customer bị vô hiệu hóa” cần được bảo đảm **mạnh và tức thời**, một luồng sự kiện bất đồng bộ đơn giản chưa đủ. Có thể cần đổi ranh giới sở hữu, dùng một dịch vụ chấp nhận command có thẩm quyền, đặt lock/lease/phê duyệt trong quy trình thống nhất hoặc thiết kế giao thức phân tán rõ ràng. Các phương án có đánh đổi độ trễ và khả dụng; đừng hứa tính nhất quán mạnh chỉ vì “đã gọi API kiểm tra”.

### 9.1. Không nhầm lỗi quan sát với lỗi toàn vẹn

Khi Customer Service timeout, Order Service **không biết** Customer còn tồn tại hay đã bị xóa. Cần phân biệt:

- `404` có ngữ nghĩa được tài liệu hóa trong hợp đồng: không tìm thấy ở phạm vi được phép quan sát.
- `403` hoặc việc cố tình trả `404` để tránh lộ thông tin: không được phép truy cập.
- Timeout/5xx: trạng thái tạm thời không xác định; có thể dùng retry/backoff hoặc đưa yêu cầu vào trạng thái chờ theo chính sách.
- Sự kiện `CustomerDeleted` đã xác thực, có version phù hợp: dữ kiện cụ thể về vòng đời của đối tượng.

Không tự tạo parent giả từ tên hoặc email khi dịch vụ đích không phản hồi, vì điều đó có thể phá vỡ định danh và quyền sở hữu dữ liệu.

## 10. Bảo mật, lưu giữ và khôi phục quan hệ

Tính toàn vẹn tham chiếu còn liên quan đến **quyền truy cập và nghĩa vụ lưu trữ**:

1. **Quyền xóa:** chỉ chủ sở hữu nghiệp vụ hoặc vai trò được cấp quyền mới có thể xóa/vô hiệu hóa. Lệnh xóa cần kiểm tra tenant và trạng thái, không chỉ có ID.
2. **Lịch sử bắt buộc:** một số dữ liệu giao dịch phải được giữ để đối soát; chọn soft delete, ẩn thông tin định danh hoặc snapshot theo nghĩa vụ thực tế. Không áp dụng cascade lên lịch sử cần giữ.
3. **Dữ liệu cá nhân:** xóa hoặc ẩn thông tin phải xét cả bảng child, audit, bản sao, cache và backup; một FK hợp lệ không chứng minh yêu cầu xóa dữ liệu đã được thực hiện đầy đủ.
4. **Audit:** ghi actor, request ID, lý do, thời điểm và kết quả của thao tác xóa hoặc đổi quan hệ; log được bảo vệ để phục vụ điều tra.
5. **Backup/restore:** nếu phục hồi database parent về thời điểm khác với database child, có thể phát sinh tham chiếu lệch. Cần kế hoạch phục hồi nhất quán, đối soát FK và sự kiện ngoài hệ.
6. **Migration:** không được xóa parent trong lúc đổi schema khi còn child chưa chuyển đổi; dùng kế hoạch mở rộng, di chuyển và thu hẹp với khả năng rollback.

Trong hệ thống dùng soft delete, nhiều truy vấn đọc sẽ lọc `deleted_at IS NULL`. Tuy nhiên, API xem đơn hàng lịch sử có thể cần JOIN được customer đã xóa mềm để giải thích giao dịch. Cần thiết kế **view/DTO khác nhau cho luồng hiện tại và luồng lịch sử**, áp dụng quyền và chính sách ẩn thông tin phù hợp.

## 11. Tình huống thực hành: tài khoản bị vô hiệu hóa khi đang đặt hàng

Giả sử hệ thống có:

- `Customer` lưu `customer_id`, `deleted_at`.
- `Order` lưu `order_id`, `customer_id`, `status`.
- `OrderLine` lưu các dòng hàng của đơn.
- API đặt hàng và API vô hiệu hóa tài khoản cùng truy cập database giao dịch.

Hai request xảy ra gần nhau:

1. Request A bắt đầu tạo đơn nháp cho customer `C-17`.
2. Request B được gửi để vô hiệu hóa `C-17`.
3. A và B có thể tranh chấp cùng lúc; hệ thống phải chọn quy tắc nghiệp vụ rõ ràng.

**Câu hỏi:**

- FK `Order.customer_id → Customer.customer_id` có tự ngăn đơn mới tham chiếu customer đã soft delete không?
- Nếu A đã `SELECT deleted_at IS NULL` trước transaction, B có thể vô hiệu hóa khách trước khi A ghi đơn không?
- Khi xóa vật lý customer còn đơn, `RESTRICT` khác `CASCADE` ra sao và chính sách nào phù hợp với lịch sử giao dịch?
- Nếu A mất kết nối ở thời điểm commit rồi thử lại, FK có ngăn đơn trùng không?
- Nếu Customer và Order ở hai database riêng, cần bổ sung những cơ chế nào?

**Hướng giải tham khảo:**

1. FK chỉ bảo vệ *sự tồn tại của hàng*, không kiểm tra `deleted_at`. Cần điều kiện nghiệp vụ tại đường ghi.
2. Chọn quy tắc tuyến tính hóa: ví dụ A và B đều khóa customer trong transaction. Nếu A khóa và tạo đơn trước, sau đó B phải đánh giá các đơn đang hoạt động theo chính sách trước khi vô hiệu hóa. Nếu B vô hiệu hóa trước, A không được tạo đơn mới.
3. Với lịch sử đơn quan trọng, ưu tiên chặn hard delete hoặc lưu trạng thái/ẩn thông tin theo yêu cầu. Không dùng cascade toàn hệ chỉ để làm lệnh DELETE chạy thành công.
4. Dùng request ID duy nhất cho thao tác tạo đơn, trả lại kết quả cũ khi retry. FK ngăn orphan nhưng không ngăn trùng thao tác.
5. Với nhiều service, cần hợp đồng vòng đời, event đã commit, xử lý idempotent, tombstone, đối soát và chấp nhận rõ giới hạn nhất quán. Nếu yêu cầu tức thời, phải bổ sung cơ chế điều phối mạnh hơn.

### 11.1. Bộ ca kiểm thử thiết yếu

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Thêm đơn với `customer_id` không tồn tại | Database từ chối theo FK; API trả lỗi phù hợp |
| Xóa vật lý customer còn đơn khi FK `RESTRICT` | Xóa thất bại; child và parent giữ nguyên |
| Xóa đơn nháp được cho phép và có `ON DELETE CASCADE` ở order_line | Các dòng phụ thuộc bị xóa trong cùng thao tác database |
| Vô hiệu hóa customer nhưng hàng vẫn còn | FK không báo lỗi; đường tạo đơn mới phải áp dụng quy tắc active |
| Hai giao dịch đồng thời tạo đơn/vô hiệu hóa customer | Không xuất hiện trạng thái vi phạm bất biến đã công bố |
| Mất kết nối ngay tại commit và gửi lại request | Không tạo hai tác động cho cùng request ID |
| Nhập dữ liệu cũ có orphan trước khi bổ sung FK | Migration phát hiện, phân loại và giải quyết trước `VALIDATE CONSTRAINT` |
| Khôi phục database hoặc replay sự kiện | Không mất quan hệ hợp lệ; chênh lệch được phát hiện và đối soát |

## 12. Checklist khi thiết kế quan hệ dữ liệu

- [ ] Xác định khóa định danh ổn định, tính duy nhất và chính sách không tái sử dụng ID.
- [ ] Phân biệt quan hệ bắt buộc với tùy chọn; `NULL` mang ngữ nghĩa được mô tả.
- [ ] Dùng FK và ràng buộc phù hợp cho các quan hệ trong cùng database giao dịch.
- [ ] Chọn `RESTRICT`/`NO ACTION`/`CASCADE`/`SET NULL`/`SET DEFAULT` theo vòng đời nghiệp vụ.
- [ ] Xác định rõ khi nào được hard delete, soft delete, archive hoặc vô hiệu hóa.
- [ ] Bảo vệ quy tắc tham chiếu tới đối tượng active, tenant và quyền truy cập trong đường ghi.
- [ ] Có cơ chế đồng thời phù hợp khi tạo child và xóa/vô hiệu hóa parent.
- [ ] API phân biệt không tồn tại, không được phép xem, đã xóa và lỗi mạng.
- [ ] Mọi retry có thể gây tác động lặp đều có request ID/idempotency phù hợp.
- [ ] Có truy vấn tìm orphan, công cụ đối soát và migration thêm FK cho dữ liệu cũ.
- [ ] Với nhiều service, đã định nghĩa hợp đồng vòng đời, tombstone, độ trễ đồng bộ và xử lý sự kiện.
- [ ] Có audit, bảo mật, kiểm thử phục hồi và kế hoạch giữ lịch sử đúng quy định.

**Ghi nhớ:** Khóa ngoại giúp dữ liệu tham chiếu **không trỏ đến hàng không tồn tại về mặt cấu trúc** trong phạm vi database mà ràng buộc bảo vệ. Nhưng **sự tồn tại của hàng không đồng nghĩa với trạng thái nghiệp vụ hợp lệ**. Thiết kế persistence Java đúng cần phối hợp định danh ổn định, hành động xóa có chủ đích, giao dịch và kiểm soát đồng thời, xử lý retry, quyền sở hữu dữ liệu cùng cơ chế đối soát khi quan hệ vượt qua ranh giới của một database.
