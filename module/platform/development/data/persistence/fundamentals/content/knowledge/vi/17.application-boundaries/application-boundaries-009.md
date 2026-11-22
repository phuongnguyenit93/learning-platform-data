# Giữ điều kiện nghiệp vụ khỏi bị phân tán trong mã truy cập dữ liệu

Trong chương **Ranh giới ứng dụng** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, một câu hỏi thiết kế thường gặp là: **điều kiện nghiệp vụ nên nằm ở đâu khi ứng dụng Java đọc và ghi cơ sở dữ liệu?** Nếu điều kiện được viết rải rác trong controller, service, repository, câu SQL và trigger mà không có nơi chịu trách nhiệm rõ ràng, chúng rất dễ lệch nhau sau mỗi lần thay đổi yêu cầu.

Tuy nhiên, đưa mọi điều kiện vào một lớp Java cũng không đủ: hai giao dịch có thể cùng vượt qua bước kiểm tra rồi ghi dữ liệu sai khi thực thi đồng thời. Thiết kế đúng cần phân biệt **nơi định nghĩa ý nghĩa nghiệp vụ** với **nơi cưỡng chế bất biến một cách nguyên tử**. Domain model và application service diễn đạt quyết định nghiệp vụ; repository/adapter thực hiện truy cập dữ liệu; database bảo vệ dữ liệu và giải quyết cạnh tranh theo giao thức nhất quán.

Bài học này trình bày cách xác định quyền sở hữu quy tắc, tổ chức ranh giới persistence trong Java, sử dụng SQL có điều kiện mà không biến repository thành nơi quyết định nghiệp vụ, và kiểm thử được cả **ngữ nghĩa nghiệp vụ** lẫn **tính đúng đắn khi nhiều yêu cầu chạy đồng thời**.

## 1. Vấn đề: một quy tắc nhưng nhiều bản sao không đồng nhất

Giả sử một cửa hàng chỉ cho phép giữ hàng khi sản phẩm đang bán, số lượng đặt trong khoảng cho phép và tồn kho đủ. Ban đầu quy tắc là:

> Sản phẩm phải ở trạng thái **ACTIVE**; mỗi đơn mua từ **1 đến 5** đơn vị; không được làm tồn kho âm.

Một hệ thống phát triển nhanh có thể vô tình hiện thực điều kiện này ở nhiều nơi:

- Controller A kiểm tra `quantity <= 5` trước khi gọi repository.
- Service B chỉ kiểm tra `quantity > 0`.
- Một repository đặt điều kiện `status = 'ACTIVE'` trong câu `SELECT`.
- Repository khác cập nhật `available = available - quantity` nhưng không kiểm tra số lượng tồn.
- Một batch job nhập đơn hàng đi thẳng vào database, bỏ qua các kiểm tra ở service.
- Một trigger ngăn tồn kho âm nhưng không biết ý nghĩa của giới hạn **5 đơn vị/đơn**.

Khi giới hạn thay đổi thành **8 đơn vị/đơn**, sửa một nơi không tự sửa những nơi còn lại. Người dùng mua qua API A có thể bị từ chối nhưng batch job lại chấp nhận; hoặc có hai yêu cầu cùng đọc tồn kho đủ rồi cùng trừ tiền hàng, khiến tồn kho âm.

Các triệu chứng phổ biến:

| Triệu chứng | Hậu quả |
| --- | --- |
| Nhiều câu `if` giống nhau ở controller/service/repository | Khó biết đâu là quy tắc chính thức; dễ sửa thiếu. |
| Repository trả kết quả khác nhau cho cùng điều kiện | Các đường nghiệp vụ diễn giải sai hoặc không nhất quán. |
| Câu SQL có quá nhiều nhánh quyết định nghiệp vụ | Khó kiểm thử quy tắc thuần, khó giải thích và tái sử dụng. |
| Chỉ kiểm tra trong Java rồi `UPDATE` không điều kiện | Race condition khi dữ liệu thay đổi giữa lúc đọc và ghi. |
| Chỉ có `CHECK`/trigger trong DB nhưng không có chính sách rõ ở domain | Lỗi ràng buộc trở thành thông điệp nghiệp vụ khó hiểu; thay đổi yêu cầu thiếu điều phối. |
| Truy vấn từ web/API dùng quy tắc khác job/consumer | Tính đúng đắn phụ thuộc đường vào hệ thống. |

Vấn đề cốt lõi không phải “Java hay SQL tốt hơn”, mà là **thiếu ranh giới trách nhiệm và một quy trình thay đổi quy tắc có thể kiểm chứng**.

## 2. Tách ba câu hỏi: quy tắc là gì, ai điều phối, lưu như thế nào?

Một ranh giới hữu ích cho ứng dụng Java thường có các vai trò:

| Tầng/thành phần | Câu hỏi chịu trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Domain model / domain policy** | Điều gì được phép? Bất biến nào phải đúng? | “Sản phẩm ACTIVE, số lượng nằm trong giới hạn, không bán vượt tồn kho.” |
| **Application service / use case** | Các bước nào tạo thành một thao tác nghiệp vụ? Ranh giới transaction ở đâu? | Đọc sản phẩm, kiểm tra chính sách, giữ hàng, ghi đơn, commit. |
| **Repository port** | Nghiệp vụ cần đọc/ghi điều gì, không phụ thuộc cách lưu? | `findForPurchase(sku)`, `reserveIfUnchanged(...)`. |
| **Persistence adapter** | Dùng SQL/JDBC/JPA nào để thực hiện port? | `PreparedStatement`, mapping, kiểm tra số hàng ảnh hưởng. |
| **Database** | Những dữ liệu và xung đột nào phải được bảo vệ ngay tại nguồn ghi? | Khóa chính, `CHECK`, `UNIQUE`, giao dịch, cập nhật có điều kiện. |
| **API/controller** | Nhận và kiểm tra định dạng yêu cầu, trả kết quả bằng giao thức nào? | Đọc JSON, xác thực, ánh xạ lỗi nghiệp vụ sang HTTP. |

Sơ đồ quan hệ phụ thuộc ở mức khái niệm:

```text
HTTP / message / batch
         |
         v
Application Service (điều phối use case, transaction)
         |                            |
         v                            v
Domain Policy / Aggregate       Repository Port
(quy tắc và bất biến)                 ^
                                     |
                                JDBC/JPA Adapter
                                     |
                                     v
                                  Database
                          (constraints, locks, WAL)
```

Không nhất thiết phải có một package hoặc lớp riêng cho từng ô nếu ứng dụng nhỏ. Điều cần giữ là **hướng phụ thuộc và quyền sở hữu**:

- Domain policy **không biết** `ResultSet`, `EntityManager`, `DataSource`, HTTP response hay tên bảng.
- Repository adapter **không tự sáng tạo** chính sách “khách hàng nào đủ điều kiện” từ những biểu thức chỉ có trong SQL.
- Application service **không lặp lại toàn bộ** logic SQL và mapping của repository.
- Database ràng buộc dữ liệu, nhưng **không thay thế** ngữ nghĩa, thông báo và quy trình nghiệp vụ ở application/domain.

Đây là một cách tổ chức theo tinh thần *separation of concerns*, *hexagonal architecture* và *domain-driven design*, không phải mệnh lệnh phải áp dụng toàn bộ DDD cho mọi bài toán CRUD.

## 3. Phân loại điều kiện trước khi chọn nơi đặt

Không phải mọi câu `if` đều có cùng mục đích. Phân loại giúp tránh đưa nhầm logic vào tầng persistence.

| Loại điều kiện | Ví dụ | Nơi sở hữu/ngăn lỗi phù hợp |
| --- | --- | --- |
| **Định dạng đầu vào** | Mã sản phẩm không được rỗng, quantity phải là số nguyên. | API boundary/validation; domain vẫn bảo vệ bất biến khi được gọi ngoài API. |
| **Quy tắc nghiệp vụ** | Mỗi đơn tối đa 5 đơn vị, chỉ bán sản phẩm ACTIVE. | Domain policy/aggregate là nơi định nghĩa ý nghĩa. |
| **Bất biến trên một hàng** | Tồn kho không âm, trạng thái chỉ từ tập cho phép. | Database `CHECK` và `UPDATE ... WHERE ...`; domain giải thích quy tắc. |
| **Bất biến trên nhiều hàng** | Một lớp học tối đa 30 học viên. | Domain/application xác định; DB cần transaction, khóa/ràng buộc phù hợp. |
| **Tính duy nhất** | Mỗi `request_id` chỉ được áp dụng một lần. | Chính sách ở use case; `UNIQUE`/PK cưỡng chế tại database. |
| **Bảo mật và phân quyền** | Người dùng chỉ sửa đơn của chính mình. | Kiểm tra quyền ở application/security boundary; có thể thêm RLS/constraint bảo vệ dữ liệu. |
| **Chi tiết hạ tầng** | Retry deadlock, cách bind tham số, phân trang DB. | Persistence/transaction adapter và tầng điều phối phù hợp. |
| **Quy tắc tích hợp hệ ngoài** | Thanh toán phải được xác nhận trước khi giao hàng. | Application workflow/domain; outbox/saga/idempotency hỗ trợ triển khai. |

**Một quy tắc có thể cần nhiều lớp cưỡng chế nhưng chỉ nên có một nơi chịu trách nhiệm về ý nghĩa.** Ví dụ “không bán quá số lượng đang có” được diễn đạt trong domain, rồi bảo vệ ở database bằng câu cập nhật nguyên tử và ràng buộc `CHECK`. Sự hiện diện của điều kiện trong SQL **không phải tự động là logic nghiệp vụ bị phân tán** nếu SQL chỉ là phần hiện thực có chủ đích của cùng một bất biến.

Điều khác biệt nằm ở khả năng trả lời: *Ai phê duyệt thay đổi quy tắc? Thay đổi đó cần sửa những adapter nào? Có test nào chứng minh mọi đường ghi vẫn tuân thủ?*

## 4. Anti-pattern: repository vừa quyết định chính sách vừa ghi dữ liệu

Đoạn Java sau minh họa cấu trúc dễ lỗi; **không nên dùng trong sản phẩm thật**:

```java
public void buy(String sku, int quantity) throws SQLException {
    try (Connection c = dataSource.getConnection()) {
        // Chỉ repository này biết giới hạn tối đa 5.
        if (quantity < 1 || quantity > 5) {
            throw new IllegalArgumentException("Invalid quantity");
        }

        // Đọc tồn kho trước.
        int available = readAvailable(c, sku);
        if (available < quantity) {
            throw new IllegalStateException("Not enough stock");
        }

        // Không kiểm tra lại điều kiện tại thời điểm ghi.
        try (PreparedStatement ps = c.prepareStatement(
                "UPDATE inventory SET available = available - ? WHERE sku = ?")) {
            ps.setInt(1, quantity);
            ps.setString(2, sku);
            ps.executeUpdate(); // Bỏ qua số hàng thực sự được cập nhật.
        }
    }
}
```

Có ít nhất bốn vấn đề:

1. **Chính sách bị giấu trong DAO:** nếu nơi khác cũng bán hàng, dễ đặt giới hạn khác nhau.
2. **Thiếu điều kiện trạng thái:** sản phẩm ngừng bán vẫn có thể bị trừ tồn.
3. **Kiểm tra–ghi bị tách rời:** sau `SELECT`, một transaction khác có thể mua hết hàng; câu `UPDATE` vẫn trừ tiếp.
4. **Không xét số hàng và kết quả commit:** nếu SKU không tồn tại, `executeUpdate()` có thể trả 0, nhưng method không phát hiện.

Giải pháp không phải chỉ di chuyển toàn bộ `if` lên controller rồi giữ nguyên câu `UPDATE` thiếu điều kiện. Cần **tách chính sách ra khỏi mã SQL và vẫn bảo vệ thao tác ghi ở database**.

## 5. Đặt chính sách thuần trong domain

Ta lấy một quy tắc minh họa: yêu cầu mua phải có số lượng dương; sản phẩm phải đang bán; số lượng phải nằm trong khoảng cho phép của sản phẩm; số lượng hiện có phải đủ để giữ hàng.

Biểu diễn dữ liệu mà domain cần bằng các kiểu Java đơn giản:

```java
public record PurchaseRequest(
        java.util.UUID requestId,
        String sku,
        int quantity
) {
    public PurchaseRequest {
        if (requestId == null || sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("Invalid request");
        }
    }
}

public record ProductSnapshot(
        String sku,
        boolean active,
        int available,
        int minimumPerOrder,
        int maximumPerOrder,
        long version
) {
}
```

Domain policy diễn đạt **quy tắc** mà không phụ thuộc database:

```java
public final class PurchasePolicy {
    public void requireReservable(ProductSnapshot product, int quantity) {
        if (quantity <= 0) {
            throw new RuleViolation("INVALID_QUANTITY");
        }
        if (!product.active()) {
            throw new RuleViolation("PRODUCT_NOT_ACTIVE");
        }
        if (quantity < product.minimumPerOrder()
                || quantity > product.maximumPerOrder()) {
            throw new RuleViolation("QUANTITY_OUT_OF_RANGE");
        }
        if (product.available() < quantity) {
            throw new RuleViolation("INSUFFICIENT_STOCK");
        }
    }

    public static final class RuleViolation extends RuntimeException {
        public RuleViolation(String code) {
            super(code);
        }
    }
}
```

Lợi ích:

- Một nơi thể hiện rõ **vì sao** yêu cầu bị từ chối, không phải chuỗi lỗi SQL khó hiểu.
- Có thể kiểm tra bằng **unit test không cần database**, nhanh và tập trung vào nghiệp vụ.
- Controller web, consumer và batch job cùng gọi **application service sử dụng policy này**, thay vì tự sao chép các câu `if`.
- Khi giới hạn mua thay đổi, domain policy là điểm đánh giá hành vi; adapter và schema được cập nhật nếu quy tắc mới đòi khác cấu trúc lưu trữ.

**Giới hạn cần nhớ:** `ProductSnapshot` chỉ là **ảnh chụp tại lúc đọc**. Sau khi `requireReservable(...)` thành công, một transaction khác có thể đã thay đổi tồn kho hoặc trạng thái sản phẩm. **Domain policy đúng không tự làm phép ghi đồng thời trở nên đúng**.

Với các giá trị `minimumPerOrder` và `maximumPerOrder` lấy từ database, domain không nên tự đọc SQL. Repository ánh xạ dữ liệu sang `ProductSnapshot`, còn domain quyết định ý nghĩa của các giá trị.

## 6. Định nghĩa repository port bằng ngôn ngữ nghiệp vụ

Thay vì để application service lắp một chuỗi SQL riêng mỗi lần, ta xác định một port với các thao tác có ý nghĩa:

```java
import java.util.Optional;
import java.util.UUID;

public interface ProductRepository {
    Optional<ProductSnapshot> findBySku(String sku);

    // Trả 1 khi giữ hàng thành công; 0 khi điều kiện không còn đúng.
    int reserveIfUnchanged(
            String sku, int quantity, long expectedVersion);
}

public interface ReservationRepository {
    void insertPending(UUID requestId, String sku, int quantity);
}
```

Repository port mô tả **cần thao tác gì**, không cung cấp mã SQL, tên schema hoặc quy tắc phát sinh HTTP. Tên `reserveIfUnchanged` bộc lộ rằng đây là thao tác **có điều kiện**; phương thức không hứa thành công chỉ vì một bản đọc cũ đã hợp lệ.

Tùy độ phức tạp, có thể trả kiểu kết quả giàu ý nghĩa hơn số hàng:

```java
public enum ReserveWriteResult {
    RESERVED,
    CONDITION_NOT_MET
}
```

Đối với hệ thống thực, nên phân biệt rõ **thao tác không cập nhật hàng nào** với **lỗi SQL, deadlock, serialization failure hoặc mất kết nối quanh commit**. Một kết quả `CONDITION_NOT_MET` không có nghĩa là có thể kết luận ngay “hết hàng”: sản phẩm cũng có thể đã bị khóa bán, version thay đổi hoặc bị xóa.

Repository port không nhất thiết phải là giao diện generic `save(T)` nếu nghiệp vụ đòi một phép cập nhật nguyên tử có điều kiện. Một port như `reserveIfUnchanged` giúp làm rõ hợp đồng concurrency mà `save` chung chung có thể che giấu.

## 7. Application service sở hữu use case và ranh giới transaction

Application service điều phối: đọc ảnh chụp, gọi domain policy, yêu cầu ghi có điều kiện, ghi reservation, rồi commit **cả hai bước ghi** hoặc rollback. Nó không cần biết tên cột SQL, nhưng cần biết thao tác gồm những bước nào và có thể bị cạnh tranh.

Ví dụ dùng Spring (các interface ở trên được hiện thực bằng repository adapter cùng transaction manager):

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.UUID;

@Service
public final class PurchaseApplicationService {
    private final ProductRepository products;
    private final ReservationRepository reservations;
    private final PurchasePolicy policy;

    public PurchaseApplicationService(
            ProductRepository products,
            ReservationRepository reservations,
            PurchasePolicy policy
    ) {
        this.products = products;
        this.reservations = reservations;
        this.policy = policy;
    }

    @Transactional
    public UUID reserve(PurchaseRequest request) {
        ProductSnapshot product = products.findBySku(request.sku())
                .orElseThrow(() -> new PurchasePolicy.RuleViolation(
                        "PRODUCT_NOT_FOUND"));

        policy.requireReservable(product, request.quantity());

        int changed = products.reserveIfUnchanged(
                request.sku(), request.quantity(), product.version());

        if (changed != 1) {
            // Không tự kết luận hết hàng: dữ liệu có thể đã đổi.
            throw new ConcurrentProductChangeException();
        }

        // Nếu INSERT thất bại, transaction phải rollback cả lần giữ hàng.
        reservations.insertPending(
                request.requestId(), request.sku(), request.quantity());

        return request.requestId();
    }

    public static final class ConcurrentProductChangeException
            extends RuntimeException {
    }
}
```

Để dùng mẫu này trong Spring cần đăng ký `PurchasePolicy` là bean (ví dụ một `@Bean` trong cấu hình), đồng thời có adapter thực thi các interface repository. Annotation `@Transactional` cần được gọi qua cơ chế quản lý transaction phù hợp; self-invocation trong cùng class có thể không kích hoạt proxy. Mặc định Spring thường rollback khi gặp `RuntimeException` như hai loại ngoại lệ trong ví dụ.

Lưu ý về mức trách nhiệm:

- Application service quyết định **trình tự** và điều kiện một thao tác được chấp nhận.
- Domain policy quyết định **quy tắc**.
- Repository adapter **thực thi** việc giữ hàng và ghi yêu cầu ở cùng transaction.
- Database đảm bảo phép cập nhật nguyên tử theo ngữ nghĩa SQL và ràng buộc.

Ví dụ này chỉ minh họa một lần đặt giữ hàng. Nó **chưa hoàn chỉnh cho retry sau timeout/commit không rõ kết quả**: triển khai production cần giao thức `requestId` idempotent, đối soát trạng thái và tránh ghi trùng. Phần 11 bàn cách bổ sung mà không rải logic này ở nhiều endpoint.

## 8. Adapter JDBC biến điều kiện thành thao tác nguyên tử

Giả sử PostgreSQL lưu trạng thái sản phẩm như sau:

```sql
CREATE TABLE inventory (
    sku                TEXT PRIMARY KEY,
    status             TEXT NOT NULL
                       CHECK (status IN ('ACTIVE', 'INACTIVE')),
    available          INTEGER NOT NULL CHECK (available >= 0),
    min_per_order      INTEGER NOT NULL CHECK (min_per_order > 0),
    max_per_order      INTEGER NOT NULL
                       CHECK (max_per_order >= min_per_order),
    version            BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0)
);

CREATE TABLE reservations (
    request_id         UUID PRIMARY KEY,
    sku                TEXT NOT NULL REFERENCES inventory(sku),
    quantity           INTEGER NOT NULL CHECK (quantity > 0),
    status             TEXT NOT NULL CHECK (status IN ('PENDING', 'CONFIRMED'))
);
```

Sau khi repository đọc một `ProductSnapshot` với `version = 12`, adapter phải kiểm tra lại điều kiện trong **cùng một câu `UPDATE`**:

```sql
UPDATE inventory
SET available = available - :quantity,
    version = version + 1
WHERE sku = :sku
  AND version = :expected_version
  AND status = 'ACTIVE'
  AND available >= :quantity
  AND :quantity BETWEEN min_per_order AND max_per_order;
```

Ở đây dấu `:name` là placeholder minh họa của một thư viện SQL hỗ trợ named parameter; với JDBC chuẩn, đổi thành `?` và ràng buộc bằng `PreparedStatement`. Câu lệnh cập nhật tối đa một hàng do `sku` là khóa chính.

**Tại sao SQL vẫn có các điều kiện nghiệp vụ nếu domain đã kiểm tra?** Vì domain kiểm tra **trên ảnh chụp**, còn SQL bảo đảm **thời điểm ghi thực tế** không làm sai bất biến. `version` chống dùng ảnh chụp cũ; `available >= :quantity` ngăn tồn kho âm; `status` và giới hạn per-order là điều kiện cuối bảo vệ đường ghi. Đây là **hai hình thức thực thi của cùng một quy tắc có chủ đích**, không phải hai nơi tùy tiện phát minh chính sách.

Một adapter JDBC triển khai đúng phần cập nhật:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class JdbcStockQueries {
    public int reserveIfUnchanged(
            Connection connection,
            String sku,
            int quantity,
            long expectedVersion
    ) throws SQLException {
        String sql = """
            UPDATE inventory
            SET available = available - ?,
                version = version + 1
            WHERE sku = ?
              AND version = ?
              AND status = 'ACTIVE'
              AND available >= ?
              AND ? BETWEEN min_per_order AND max_per_order
            """;

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setInt(1, quantity);
            statement.setString(2, sku);
            statement.setLong(3, expectedVersion);
            statement.setInt(4, quantity);
            statement.setInt(5, quantity);
            return statement.executeUpdate();
        }
    }
}
```

Đoạn mã truyền `Connection` để minh họa việc nhiều câu SQL cần **dùng cùng transaction**. Trong một ứng dụng Spring, adapter có thể lấy connection được transaction manager quản lý qua `JdbcTemplate` hoặc công cụ tương đương, thay vì tự gọi `dataSource.getConnection()` để mở một transaction độc lập.

Ở PostgreSQL với `READ COMMITTED`, khi hai transaction cùng cập nhật một hàng, transaction thứ hai có thể chờ rồi đánh giá lại điều kiện trên phiên bản phù hợp sau khi transaction thứ nhất commit. Với mức cô lập cao hơn, cạnh tranh có thể tạo **serialization failure** thay vì trả 0 hàng; adapter/service phải phân loại lỗi theo cơ chế của DBMS.

Mọi đường ghi vào các trường làm thay đổi quyết định mua hàng — `status`, `available`, `min_per_order`, `max_per_order` — cần **tăng version theo cùng giao thức**. Nếu một batch job sửa giới hạn nhưng không tăng `version`, optimistic locking dựa trên version có thể không nhận biết thay đổi. Các điều kiện trực tiếp trong SQL vẫn tạo thêm lớp bảo vệ, nhưng một hệ thống nhất quán không nên phụ thuộc vào việc adapter này vô tình kiểm tra hộ đường ghi khác.

## 9. Cách hiểu kết quả ghi: đừng biến lỗi kỹ thuật thành phán quyết nghiệp vụ

Trong câu SQL ở phần trên, `executeUpdate()` có thể trả:

| Kết quả | Có thể kết luận | Điều chưa nên kết luận |
| --- | --- | --- |
| **1 hàng** | Điều kiện ghi được thỏa và hàng đã cập nhật trong transaction hiện tại. | Transaction đã commit bền vững, nếu còn bước tiếp theo. |
| **0 hàng** | Không có hàng thỏa **tất cả** điều kiện tại thời điểm lệnh được thực hiện. | Chính xác là “hết hàng”, “ngừng bán” hay “version cũ”. |
| **SQLException** | Thao tác không hoàn tất bình thường theo hợp đồng driver. | Luôn là lỗi nghiệp vụ; luôn chắc chắn transaction chưa commit. |

Application service có thể chuyển 0 hàng thành lỗi **`PRODUCT_CHANGED`** rồi yêu cầu đọc lại trạng thái mới. Nếu cần thông báo lý do cụ thể, có thể truy vấn lại sản phẩm và chạy domain policy để giải thích; nhưng đây là **chẩn đoán theo thời điểm**, không phải bằng chứng trạng thái đã giữ nguyên từ lúc cập nhật thất bại.

Không nên làm như sau:

```java
if (repository.reserveIfUnchanged(...) == 0) {
    throw new OutOfStockException(); // Suy đoán thiếu căn cứ.
}
```

Chỉ nên trả `OUT_OF_STOCK` khi đã có đủ dữ kiện theo hợp đồng use case. Ví dụ sản phẩm có thể vừa chuyển `INACTIVE` hoặc vừa tăng `version` vì thay đổi giá. Định nghĩa lỗi nghiệp vụ ở application/domain và ánh xạ mã lỗi kỹ thuật tại adapter là cách tránh để controller phải đoán thông điệp dựa trên SQL.

## 10. Bất biến trải nhiều hàng không thể chỉ dựa vào policy thuần

Không phải mọi quy tắc đều gói vào `UPDATE ... WHERE` trên một hàng. Xét điều kiện “mỗi ca trực phải luôn có ít nhất một bác sĩ đang trực”. Hai giao dịch cùng đọc số bác sĩ trực = 2, rồi mỗi giao dịch chuyển trạng thái của **một bác sĩ khác nhau** sang nghỉ. Chúng có thể cùng commit dưới snapshot isolation và để lại **0 người trực** — hiện tượng *write skew*.

Một domain policy thuần:

```java
if (onCallCount > 1) {
    allowLeave();
}
```

là đúng về **ý nghĩa**, nhưng không đủ bảo vệ khi hai người đồng thời xin nghỉ. Cách triển khai có thể gồm:

1. **Transaction `SERIALIZABLE`** với retry toàn bộ giao dịch khi xảy ra serialization failure.
2. **Khóa cùng một hàng đại diện** cho ca trực trước khi đếm và cập nhật; mọi đường thay đổi ca phải theo giao thức đó.
3. **Bộ đếm người trực trên một hàng** với `UPDATE ... SET on_call_count = on_call_count - 1 WHERE on_call_count > 1`, duy trì bộ đếm và bảng chi tiết trong cùng transaction.
4. **Ràng buộc hoặc mô hình dữ liệu khác** nếu có cách biểu diễn quy tắc để database bảo vệ trực tiếp.

Điểm kiến trúc quan trọng: **domain sở hữu bất biến**, nhưng chiến lược kiểm soát đồng thời thường cần được thể hiện tại persistence boundary. Application service điều phối transaction; repository adapter biết cách lấy khóa hoặc dùng cập nhật có điều kiện; database thực thi cơ chế cô lập.

Tránh đưa mọi thuật toán khóa vào domain model chỉ để “không có SQL trong repository”, cũng tránh đặt quy tắc “bao giờ bác sĩ được nghỉ” chỉ trong một stored procedure mà phần còn lại của ứng dụng không có mô hình rõ ràng.

## 11. Idempotency: một điều kiện nghiệp vụ quan trọng ở ranh giới ghi

Một yêu cầu giữ hàng có thể đến hai lần vì người dùng nhấn lại, client retry timeout, hoặc message broker gửi trùng. **Hai lần gọi cùng thao tác không có nghĩa là hai ý định mua hàng khác nhau.**

Với `requestId` của `PurchaseRequest`, ta có thể đặt quy tắc:

> Cùng một `requestId` và cùng payload chỉ được áp dụng một lần; cùng ID nhưng payload khác phải bị từ chối.

Để thực thi được, thiết kế cần:

- Khóa chính hoặc `UNIQUE(request_id)` trong bảng thao tác/đơn hàng.
- Ghi **kết quả xử lý** và thay đổi tồn kho trong **cùng transaction**.
- Khi gặp trùng ID, **đọc lại kết quả đã commit và so sánh payload**; không tự động trừ kho một lần nữa.
- Khi không nhận ACK `COMMIT`, đối soát theo `requestId` ở nguồn có thẩm quyền trước khi xem xét thử lại.
- Nếu dùng outbox, ghi sự kiện chờ phát cùng transaction; consumer cần chống xử lý trùng theo event ID.

Trong ví dụ service ở phần 7, `requestId` có khóa duy nhất ở bảng `reservations` nhưng service **chưa kiểm tra trùng trước khi gọi policy/giữ kho**. Nếu `INSERT` phát sinh lỗi trùng, transaction phải rollback để trả lại tồn kho; adapter hoặc lớp orchestration sau đó cần đối soát kết quả cũ. Không được chỉ catch lỗi unique rồi trả thành công mà không so sánh nội dung.

Một cách làm rõ hợp đồng là đưa vào application service hai thao tác riêng:

```text
reserve(requestId, sku, quantity):
    BEGIN
    tra cứu kết quả đã commit của requestId
    nếu có:
        kiểm tra payload giống nhau
        trả kết quả đã lưu; không giữ hàng lần nữa

    đọc product snapshot và áp dụng PurchasePolicy
    cố giữ tồn kho bằng conditional UPDATE / version check
    ghi reservation (UNIQUE requestId), kết quả và outbox nếu có
    COMMIT
    trả kết quả được commit

    nếu UNIQUE conflict từ request đồng thời:
        ROLLBACK
        đối soát requestId; không mặc định thất bại hay thành công
```

Tại sao việc đọc trước không đủ? Vì hai transaction có thể cùng thấy chưa có hàng `requestId` rồi cùng chạy. **Ràng buộc duy nhất ở database** mới là điểm quyết định khi cạnh tranh. Điều này không mâu thuẫn với nguyên tắc domain sở hữu quy tắc: database là nơi cưỡng chế tính duy nhất của một giao thức được định nghĩa ở use case.

## 12. Khi dùng JPA/Hibernate: tránh lẫn aggregate với bảng dữ liệu

JPA giúp ánh xạ entity sang bảng, nhưng entity ORM **không tự động là domain aggregate tốt**. Có thể dùng entity JPA trực tiếp làm domain model khi các quy tắc và ranh giới đủ đơn giản; với hệ thống phức tạp, có thể tách persistence entity khỏi domain model để tránh phụ thuộc vào lazy loading, lifecycle callback và framework.

Một số lựa chọn thiết kế:

| Lựa chọn | Khi nào phù hợp | Cần kiểm soát |
| --- | --- | --- |
| Domain model cũng là JPA entity | Nghiệp vụ gọn, đối tượng tương đối phù hợp ranh giới aggregate. | Không để rule bị chia nhỏ giữa setter, listener, controller và native SQL. |
| Domain model thuần, persistence entity riêng | Domain phức tạp, nhiều adapter, cần test độc lập. | Mapping thêm chi phí; cần tránh cập nhật thiếu trường/version. |
| Repository dùng JPQL/SQL cho conditional update | Bảo vệ bất biến tại thời điểm ghi. | Bulk update có thể bỏ qua cơ chế `@Version` tự động; phải tăng version rõ ràng. |
| `@Version` cho optimistic locking | Tránh ghi đè một entity dựa trên phiên bản cũ. | Không tự bảo vệ bất biến xuyên nhiều entity hoặc mọi đường ghi ngoài ORM. |

Ví dụ với JPA:

```java
@jakarta.persistence.Entity
@jakarta.persistence.Table(name = "inventory")
public class InventoryEntity {
    @jakarta.persistence.Id
    private String sku;

    private String status;
    private int available;

    @jakarta.persistence.Version
    private long version;

    protected InventoryEntity() {
    }
}
```

Trong đường ghi entity được ORM quản lý, `@Version` giúp phát hiện sửa cạnh tranh theo cơ chế provider. Tuy nhiên, một câu native SQL hoặc bulk JPQL kiểu `UPDATE InventoryEntity ...` có thể **không tự động tăng/check version** theo quy trình thông thường của entity manager. Khi dùng các thao tác đó, phải quy định ai cập nhật version và cách đồng bộ persistence context nếu các entity tương ứng đang được quản lý.

Đừng để domain policy phụ thuộc trực tiếp vào việc thuộc tính lazy-load đã được fetch hay chưa. Domain phải nhận được **đủ thông tin để đánh giá quy tắc**, hoặc có một domain service thực hiện phối hợp đúng theo hợp đồng. Repository chịu trách nhiệm truy vấn và mapping, không để ngoại lệ lazy-loading trở thành cách kiểm soát luồng nghiệp vụ.

## 13. Kiểm thử theo ranh giới để ngăn phân tán điều kiện

Mục tiêu kiểm thử không chỉ là đạt coverage nhiều dòng, mà là làm lộ trường hợp một đường ghi bypass quy tắc.

### 13.1. Unit test domain policy

Không cần database để kiểm tra ý nghĩa “đang bán, số lượng hợp lệ, tồn kho đủ”:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class PurchasePolicyTest {
    private final PurchasePolicy policy = new PurchasePolicy();

    @Test
    void rejectsQuantityAboveMaximum() {
        ProductSnapshot stock = new ProductSnapshot(
                "BOOK-1", true, 20, 1, 5, 12);

        PurchasePolicy.RuleViolation error = assertThrows(
                PurchasePolicy.RuleViolation.class,
                () -> policy.requireReservable(stock, 6));

        assertEquals("QUANTITY_OUT_OF_RANGE", error.getMessage());
    }

    @Test
    void acceptsValidPurchase() {
        ProductSnapshot stock = new ProductSnapshot(
                "BOOK-1", true, 8, 1, 5, 12);
        assertDoesNotThrow(() -> policy.requireReservable(stock, 3));
    }
}
```

Những test khác nên bao gồm: sản phẩm ngừng bán, số lượng 0/âm, số lượng dưới tối thiểu, tồn kho vừa đủ, tồn kho thiếu và biên giới hạn tối đa.

### 13.2. Integration test adapter với database thật

Kiểm tra câu `UPDATE` có điều kiện thay vì chỉ mock repository:

1. Tạo sản phẩm `available = 5`, `version = 7`, `status = ACTIVE`.
2. Dùng **hai connection/transaction độc lập**, cho cả hai đọc version 7.
3. Hai bên cùng muốn giữ 4 đơn vị.
4. Cho phép cả hai thử `reserveIfUnchanged(...)` và commit/rollback theo kết quả.
5. Xác nhận **tối đa một yêu cầu được chấp nhận**; tồn kho không âm và version cuối phản ánh lần ghi thành công.
6. Thử đổi `status` hoặc `max_per_order` bằng đường ghi hợp lệ rồi bảo đảm request với snapshot cũ không âm thầm áp dụng.

Một test chạy tuần tự không chứng minh giao thức kiểm soát đồng thời đúng. Cần chủ động tạo lịch xen kẽ hai transaction và kiểm tra **kết quả đã commit cuối cùng**, không chỉ số hàng cập nhật tạm.

### 13.3. Application service test

Kiểm tra thứ tự và kết quả transaction:

- Nếu domain policy từ chối, không gọi thao tác giữ hàng.
- Nếu conditional update trả 0, không ghi đơn thành công và không báo hết hàng khi chưa biết nguyên nhân.
- Nếu ghi reservation thất bại sau khi giảm tồn kho, transaction rollback **cả hai thay đổi**.
- Nếu hai yêu cầu trùng `requestId`, kết quả cuối không trừ tồn kho hai lần.
- Nếu commit đã thành công nhưng ACK bị mất, đối soát theo ID thay vì tạo yêu cầu mới.
- Nếu API hoặc batch gọi cùng use case, chúng cùng đi qua chính sách chung.

### 13.4. Contract test cho các adapter khác nhau

Nếu có một repository adapter JDBC, một adapter JPA và một adapter test, các implementation cần tuân thủ cùng hợp đồng: `reserveIfUnchanged` chỉ trả thành công khi điều kiện ghi đã được áp dụng, không “tự thêm” chính sách khác. Một bộ test hợp đồng có thể chạy lặp lại với từng adapter để phát hiện khác biệt.

**Mock không thay được integration test concurrency.** Mock thường không tái hiện lock, snapshot, serialization failure, unique constraint và race condition tại database.

## 14. Thay đổi quy tắc và tiến hóa schema mà không phá vỡ hệ thống

Giả sử yêu cầu đổi từ “mỗi đơn tối đa 5” sang “giới hạn tùy loại sản phẩm và chương trình khuyến mại”. Nếu quy tắc nằm rải rác ở năm câu SQL và ba controller, gần như chắc sẽ có đường xử lý dùng điều kiện cũ.

Một kế hoạch thay đổi có kiểm soát:

1. **Viết rõ quy tắc mới dưới dạng tình huống cụ thể**: loại nào tối đa bao nhiêu, hiệu lực từ thời điểm nào, có áp dụng đơn đã tạo chưa?
2. **Cập nhật domain policy** và test trước; nếu thay đổi theo thời gian, xác định chính xác dùng thời điểm nào làm mốc.
3. **Xem lại dữ liệu domain cần**. Có cần thêm `min_per_order`, `max_per_order`, `policy_version` hoặc một bảng chính sách mới không?
4. **Thiết kế migration tương thích** với các phiên ứng dụng cũ và mới chạy đồng thời. Ví dụ: thêm cột và điền dữ liệu trước, triển khai code đọc được cả hai trạng thái, sau đó mới thắt ràng buộc.
5. **Cập nhật ranh giới cưỡng chế tại DB**: câu conditional update, constraints/trigger nếu có, cách tăng version và các đường ghi từ batch/job.
6. **Kiểm thử rollout hỗn hợp**: các instance phiên bản cũ và mới có thể cùng gửi yêu cầu; một thay đổi chỉ ở Java không giúp DB tự hiểu chính sách mới.
7. **Theo dõi số lượt từ chối/xung đột** sau triển khai để phát hiện adapter hoặc client còn dùng quy tắc cũ.

Với quy tắc định giá hoặc hạn mức cần giữ lịch sử, một cột `version` của hàng sản phẩm có thể chưa đủ để giải thích **vì sao một đơn đã được chấp nhận ở thời điểm trước**. Cần lưu phiên bản chính sách, giá trị được áp dụng hoặc dữ kiện quyết định vào hồ sơ nghiệp vụ theo yêu cầu kiểm toán.

Nếu thay đổi chính sách có hiệu lực theo lịch, phải quy định rõ các yêu cầu đang xử lý sử dụng **phiên bản chính sách nào** và cách tránh một giao dịch đọc chính sách cũ nhưng áp dụng dữ liệu mới. Đây là ranh giới giữa **quy tắc nghiệp vụ theo thời gian** và **giao thức transaction**, không chỉ là thao tác thêm cột.

## 15. Hiệu năng và bảo mật không nên được dùng để bỏ qua ranh giới

Một lý do phổ biến khiến ứng dụng dồn logic vào SQL là mong muốn “nhanh hơn vì không phải lấy dữ liệu lên Java”. Điều đó có thể đúng trong một số workload, nhưng phải phân biệt:

- **Đặt điều kiện ghi vào SQL** để tránh race condition và giảm round trip là hợp lý.
- **Đưa toàn bộ quyết định và thông điệp nghiệp vụ vào những câu SQL riêng lẻ khó kiểm thử** có thể làm tăng chi phí thay đổi và nguy cơ lệch quy tắc.
- **Dùng stored procedure** cho một thao tác atomically phức tạp có thể hợp lý nếu có API/hợp đồng rõ, test được và domain/application không có định nghĩa mâu thuẫn.
- **Tách một transaction thành nhiều transaction chỉ để trả connection sớm** có thể làm mất atomicity; cần thiết kế lại workflow và cơ chế phục hồi nếu muốn tách.

Về bảo mật, kiểm tra tenant/quyền truy cập không nên chỉ là filter trên giao diện. Khi sử dụng repository để cập nhật tài nguyên đa tenant, câu `WHERE` nên bao gồm phạm vi sở hữu/tenant phù hợp, đồng thời application service xác định người gọi có quyền thực hiện hành động theo chính sách. Database có thể bổ sung **row-level security** nếu kiến trúc yêu cầu, nhưng cấu hình session/connection pool phải bảo đảm không rò rỉ ngữ cảnh tenant giữa các request.

Luôn dùng `PreparedStatement` hoặc cơ chế bind parameter, tránh nối chuỗi đầu vào thành SQL. Validation ở API giúp có thông báo tốt; ràng buộc và phân quyền tại nguồn dữ liệu giúp ngăn sai lệch khi một đường đi khác bypass API.

## 16. Lộ trình refactor một codebase đang rải quy tắc khắp nơi

Không cần làm lại toàn bộ hệ thống trong một lần. Với một nghiệp vụ quan trọng, có thể tiến hành theo từng bước:

1. **Chọn một bất biến rủi ro cao**, ví dụ không bán vượt tồn kho, không trừ tiền hai lần hoặc đơn đã giao không được chỉnh sửa.
2. **Tìm toàn bộ đường ghi của nghiệp vụ**: API, consumer, job, script vận hành và integration; chỉ liệt kê nơi thật sự được phép thay đổi dữ liệu.
3. **Viết quy tắc thành tài liệu và test nghiệp vụ** để có kết quả kỳ vọng độc lập với cách triển khai hiện tại.
4. **Tạo một domain policy/aggregate method** làm nơi chịu trách nhiệm ý nghĩa; chỉnh các đường vào để cùng gọi application service.
5. **Định nghĩa repository port có ngữ nghĩa rõ**; thay các câu `UPDATE` tự do bằng thao tác có điều kiện/phiên bản hoặc cơ chế khóa đã chọn.
6. **Bổ sung constraints và transaction** để bảo vệ dữ liệu ngay cả khi có đường ghi khác, kèm test concurrency trên DB thực.
7. **Loại bỏ bản sao quy tắc cũ** khi đã có test bao phủ; tránh giữ hai nơi quyết định độc lập vì sợ thay đổi.
8. **Quan sát vận hành**: đo lỗi điều kiện, xung đột version, transaction rollback, retry và thời gian giữ connection.

Với hệ thống không thể dừng ghi, cần chú ý migration và rollout nhiều phiên bản. Đặc biệt, không chuyển một bất biến từ SQL sang Java rồi **gỡ constraint trước khi mọi adapter và job đã tuân thủ giao thức mới**.

## 17. Câu hỏi tự đánh giá

**Câu 1.** Nếu đã có `PurchasePolicy.requireReservable(...)`, tại sao `UPDATE inventory` vẫn cần `WHERE available >= ?`?

Vì policy kiểm tra một bản đọc có thể đã cũ. Điều kiện ngay tại câu ghi bảo vệ khỏi transaction khác thay đổi tồn kho giữa lúc đọc và ghi.

**Câu 2.** Đưa `status = 'ACTIVE'` vào SQL có tự động vi phạm nguyên tắc không phân tán nghiệp vụ không?

**Không.** Nếu domain sở hữu ý nghĩa “chỉ bán sản phẩm ACTIVE”, điều kiện trong SQL có thể là phần cưỡng chế của cùng một bất biến. Vấn đề xảy ra khi các câu SQL **tự đặt quy tắc khác nhau** hoặc không được cập nhật đồng bộ khi policy thay đổi.

**Câu 3.** Repository trả 0 hàng khi gọi `reserveIfUnchanged`. Có thể luôn báo `INSUFFICIENT_STOCK` không?

**Không.** Điều kiện cũng có thể thất bại vì version khác, sản phẩm ngừng bán hoặc sản phẩm đã bị xóa. Cần định nghĩa kết quả xung đột và chỉ phân loại nguyên nhân khi có đủ dữ kiện.

**Câu 4.** Hai bác sĩ cùng xin nghỉ và mỗi transaction dùng version check trên hàng riêng của họ. Tại sao vẫn có thể không còn bác sĩ trực?

Vì phiên bản từng hàng không bảo vệ điều kiện chung trên **nhiều hàng**. Đây là dạng write skew, cần serializable, khóa chung hoặc một mô hình cưỡng chế bất biến thích hợp.

**Câu 5.** Một batch job trực tiếp sửa `max_per_order` mà không tăng version có thể gây vấn đề gì?

Một request đã đọc snapshot cũ có thể không phát hiện thay đổi dựa trên version. Mọi đường ghi liên quan phải tuân theo giao thức version và được bao phủ bởi integration test.

**Câu 6.** Tại sao `UNIQUE(request_id)` cần đi cùng ghi kết quả và thay đổi tồn kho trong cùng transaction?

Để sau sự cố, việc nhìn thấy kết quả của request ID phản ánh cùng trạng thái đã commit với thay đổi tồn kho. Nếu hai bản ghi ở hai transaction khác nhau, có thể tồn tại khoảng trống khiến retry áp dụng nghiệp vụ lần hai.

**Câu 7.** Domain policy có nên biết `SQLException`, `SQLSTATE 40001` hoặc `DataSource` không?

**Không.** Đó là chi tiết persistence/transaction. Adapter và application service có thể dịch lỗi thành kết quả/xung đột mang ý nghĩa sử dụng, trong khi domain tập trung vào quy tắc.

## Kết luận

**Giữ điều kiện nghiệp vụ khỏi bị phân tán** không có nghĩa là chỉ viết `if` trong một class Java rồi bỏ mọi kiểm tra ở database. Cách tiếp cận bền vững là: **một nơi chịu trách nhiệm định nghĩa quy tắc**, một application service điều phối use case và transaction, các repository port có hợp đồng rõ, và những ràng buộc/câu SQL nguyên tử thực thi bất biến ngay tại nguồn ghi.

Khi thiết kế persistence cho Java, hãy ưu tiên quy tắc domain dễ đọc và dễ kiểm thử, giảm sự phụ thuộc vào chi tiết hạ tầng, nhưng luôn xét tới đồng thời, lỗi commit không rõ kết quả, tiến hóa schema và mọi đường ghi trong hệ thống. Một thay đổi nghiệp vụ chỉ thực sự an toàn khi **tất cả cách thực thi của nó cùng duy trì bất biến**, kể cả khi hai yêu cầu cạnh tranh hoặc một bước ghi thất bại.
