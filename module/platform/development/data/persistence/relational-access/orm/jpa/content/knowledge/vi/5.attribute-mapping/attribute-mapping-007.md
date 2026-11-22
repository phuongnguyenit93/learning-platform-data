# Ánh xạ enum theo tên hoặc theo thứ tự

Trong Java, `enum` giúp biểu diễn một tập giá trị hữu hạn, chẳng hạn trạng thái đơn hàng, mức ưu tiên, loại tài khoản hoặc phương thức giao hàng. Trong cơ sở dữ liệu quan hệ, một cột không tự hiểu các hằng Java như `CREATED`, `PAID` hay `CANCELLED`. JPA cần một quy tắc để **chuyển enum Java thành dữ liệu trong cột SQL** khi ghi và khôi phục enum từ dữ liệu đó khi đọc.

Hai cách ánh xạ cơ bản được chuẩn hóa bằng `@Enumerated` là:

- **Theo tên — `EnumType.STRING`:** lưu tên hằng enum, ví dụ `"PAID"`.
- **Theo thứ tự — `EnumType.ORDINAL`:** lưu vị trí của hằng enum trong khai báo Java, ví dụ `1`.

Lựa chọn này nhìn qua chỉ khác một annotation, nhưng nó ảnh hưởng trực tiếp đến **tính toàn vẹn của dữ liệu đã lưu, khả năng thay đổi mã nguồn và quy trình migration schema**. Đặc biệt, việc thêm hoặc sắp xếp lại một hằng enum có thể khiến dữ liệu cũ mang ý nghĩa khác nếu dùng `ORDINAL`.

Bài học đặt trong chủ đề **Data Persistence, Relational Access, ORM và JPA**, tập trung vào ánh xạ thuộc tính entity và các quyết định lưu trữ liên quan.

## 1. Một enum Java trông như thế nào?

Giả sử hệ thống có ba trạng thái đơn hàng:

```java
public enum OrderStatus {
    CREATED,
    PAID,
    CANCELLED
}
```

Trong Java, enum là một kiểu dữ liệu thực sự, không phải chuỗi tùy ý:

```java
OrderStatus status = OrderStatus.PAID;

System.out.println(status.name());    // PAID
System.out.println(status.ordinal()); // 1
```

`name()` trả về **tên hằng được khai báo**; `ordinal()` trả về **chỉ số của hằng**, bắt đầu từ `0`, tính theo thứ tự khai báo.

| Hằng enum | `name()` | `ordinal()` |
| --- | --- | ---: |
| `CREATED` | `"CREATED"` | 0 |
| `PAID` | `"PAID"` | 1 |
| `CANCELLED` | `"CANCELLED"` | 2 |

Những giá trị `0`, `1`, `2` không phải mã nghiệp vụ ổn định do ứng dụng chủ động thiết kế. Chúng là kết quả của **vị trí hiện tại trong mã nguồn**. Thay đổi thứ tự khai báo sẽ thay đổi `ordinal()`.

Đó chính là khác biệt cốt lõi giữa hai cách lưu enum trong JPA.

## 2. `@Enumerated` nằm ở đâu trong JPA?

JPA/Jakarta Persistence cung cấp annotation chuẩn `@Enumerated` và enum `EnumType` trong package `jakarta.persistence`. Với dự án JPA đời cũ, cùng khái niệm có thể xuất hiện dưới package `javax.persistence`.

Ví dụ entity:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private OrderStatus status;

    protected PurchaseOrder() {
        // JPA cần constructor không tham số.
    }
}
```

Constructor `protected PurchaseOrder()` đáp ứng yêu cầu khởi tạo entity của JPA. Mã nghiệp vụ có thể khai báo thêm constructor có tham số để tạo đơn hàng hợp lệ. Phần sau sẽ minh họa class đầy đủ với cả hai mục đích sử dụng.

Annotation:

```java
@Enumerated(EnumType.STRING)
private OrderStatus status;
```

nói rằng khi persist và load thuộc tính `status`, JPA provider phải ánh xạ enum **theo tên** thay vì theo vị trí.

Nếu đổi thành:

```java
@Enumerated(EnumType.ORDINAL)
private OrderStatus status;
```

provider sẽ ánh xạ theo **thứ tự khai báo** của hằng enum.

Sự khác biệt nằm ở **giá trị được lưu trong database**, không phải ở kiểu Java của thuộc tính. Trong cả hai trường hợp, mã nghiệp vụ vẫn dùng `OrderStatus.PAID`.

## 3. Ánh xạ theo tên: `EnumType.STRING`

### 3.1. Dữ liệu được lưu như thế nào?

Với enum:

```java
public enum OrderStatus {
    CREATED,
    PAID,
    CANCELLED
}
```

và entity:

```java
@Enumerated(EnumType.STRING)
@Column(name = "status", nullable = false, length = 20)
private OrderStatus status;
```

khi lưu `OrderStatus.PAID`, dữ liệu tương ứng thường có dạng:

| id | status |
| ---: | --- |
| 101 | CREATED |
| 102 | PAID |
| 103 | CANCELLED |

Một schema SQL đơn giản có thể dùng:

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL
);
```

JPA provider chọn cách ràng buộc tham số JDBC và DDL cụ thể tùy database, dialect và phiên bản; vì thế **không nên xem `VARCHAR` là kiểu SQL bắt buộc trong mọi provider/database**. Một số môi trường hỗ trợ kiểu `ENUM` native hoặc constraint tương đương. Điều cần nắm là **ý nghĩa của mapping theo chuỗi tên hằng**.

### 3.2. Ưu điểm

**Dữ liệu dễ đọc.** Khi kiểm tra SQL, DBA và lập trình viên thấy ngay `PAID` thay vì phải tra cứu xem số `1` là trạng thái nào.

**Ít nhạy cảm với việc đổi thứ tự khai báo.** Nếu sắp xếp enum thành:

```java
public enum OrderStatus {
    CANCELLED,
    CREATED,
    PAID
}
```

giá trị `"PAID"` trong database vẫn được ánh xạ về `OrderStatus.PAID`, vì tên hằng không đổi.

**An toàn hơn khi chèn thêm hằng ở giữa.** Thêm `SHIPPED` vào danh sách không làm các chuỗi `CREATED`, `PAID`, `CANCELLED` cũ biến thành trạng thái khác.

**Thuận tiện cho truy vấn, log, báo cáo.** Khi nhìn vào một bản ghi riêng lẻ, dữ liệu có tính tự mô tả tương đối cao.

### 3.3. Nhược điểm và giới hạn

**Đổi tên hằng enum có tác động tới dữ liệu cũ.** Ví dụ phiên bản đầu dùng:

```java
PAID
```

nhưng phiên bản sau đổi thành:

```java
PAYMENT_COMPLETED
```

Nếu database còn giá trị `"PAID"`, JPA provider có thể không chuyển được chuỗi này thành enum mới, gây lỗi khi đọc. Không nên xem thao tác rename trong IDE là đủ để cập nhật dữ liệu đã lưu.

**Kích thước lưu trữ lớn hơn số nhỏ** trong nhiều schema, đặc biệt với tên rất dài. Tuy nhiên, hiệu năng và kích thước index thực tế còn phụ thuộc loại database, kiểu cột, số giá trị, độ chọn lọc và workload; không nên suy diễn rằng `ORDINAL` luôn nhanh hơn đáng kể.

**Độ dài và quy tắc dữ liệu phải khớp nhau.** Nếu cột `status VARCHAR(8)` nhưng có enum `PAYMENT_PENDING` dài hơn, thao tác ghi có thể thất bại. Nếu database dùng constraint chỉ cho phép ba trạng thái, thêm một hằng thứ tư cũng cần migration constraint.

**Tên hằng trở thành hợp đồng lưu trữ.** Khi dùng `STRING`, đổi tên hằng là **thay đổi format dữ liệu** và phải được quản lý tương tự thay đổi schema.

## 4. Ánh xạ theo thứ tự: `EnumType.ORDINAL`

### 4.1. Dữ liệu được lưu như thế nào?

Vẫn enum:

```java
public enum OrderStatus {
    CREATED,   // ordinal 0
    PAID,      // ordinal 1
    CANCELLED  // ordinal 2
}
```

nhưng thuộc tính trong entity dùng:

```java
@Enumerated(EnumType.ORDINAL)
@Column(name = "status", nullable = false)
private OrderStatus status;
```

Bảng có thể lưu:

| id | status |
| ---: | ---: |
| 101 | 0 |
| 102 | 1 |
| 103 | 2 |

Một schema minh họa:

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status SMALLINT NOT NULL
);
```

Kiểu số nguyên cụ thể mà provider sinh ra hoặc dùng để bind có thể thay đổi theo provider, dialect và cấu hình schema. Điểm quyết định là `0` được hiểu là hằng đứng đầu, `1` là hằng thứ hai, v.v.

### 4.2. Rủi ro khi thay đổi thứ tự khai báo

Giả sử bảng đã có:

```text
orders.id = 102
orders.status = 1       ← đang có nghĩa là PAID
```

Sau đó một lập trình viên chỉnh enum thành:

```java
public enum OrderStatus {
    CREATED,    // 0
    CANCELLED,  // 1  ← đổi vị trí
    PAID        // 2
}
```

Dữ liệu database **không tự thay đổi**, vẫn là `1`. Nhưng code mới đọc `1` và hiểu thành `CANCELLED`. Một đơn đã thanh toán có thể bị diễn giải là đã hủy.

Đây là lỗi nguy hiểm vì không nhất thiết có exception: chương trình có thể **đọc thành công nhưng hiểu sai ý nghĩa nghiệp vụ**.

### 4.3. Rủi ro khi chèn thêm hằng vào giữa

Phiên bản trước:

```java
public enum OrderStatus {
    CREATED,    // 0
    PAID,       // 1
    CANCELLED   // 2
}
```

Phiên bản sau:

```java
public enum OrderStatus {
    CREATED,          // 0
    PAYMENT_PENDING,  // 1  ← mới
    PAID,             // 2
    CANCELLED         // 3
}
```

Hai giá trị cũ `1` và `2` giờ tương ứng trạng thái khác. Đặc biệt, dữ liệu `CANCELLED` trước đây lưu `2` giờ thành `PAID`, cũng là lỗi có thể không gây exception.

Ngay cả nếu chỉ thêm hằng **ở cuối**, cách làm đó vẫn biến thứ tự khai báo thành hợp đồng ngầm phải giữ mãi. Một lần sắp xếp cho “đẹp code” sau này có thể làm hỏng dữ liệu.

### 4.4. Ưu điểm

- Giá trị được lưu là số nguyên nhỏ, có thể thuận lợi trong một số schema hoặc định dạng trao đổi đã được thiết kế quanh ordinal.
- Không trực tiếp bị ảnh hưởng bởi việc **đổi tên** hằng nếu vị trí vẫn giữ nguyên.
- Code Java vẫn giữ kiểu enum và `@Enumerated` có ngữ nghĩa chuẩn.

Tuy nhiên, những ưu điểm này hiếm khi đáng đánh đổi rủi ro tiến hóa enum ở dữ liệu tồn tại lâu dài. Đối với trạng thái nghiệp vụ có thể thay đổi, `ORDINAL` thường đòi hỏi kỷ luật migration chặt chẽ hơn.

## 5. So sánh trực tiếp `STRING` và `ORDINAL`

| Tiêu chí | `EnumType.STRING` | `EnumType.ORDINAL` |
| --- | --- | --- |
| Giá trị lưu cho `OrderStatus.PAID` | `"PAID"` | `1` nếu `PAID` ở vị trí thứ hai |
| Cách chuyển đổi | Theo tên hằng | Theo chỉ số khai báo, bắt đầu từ `0` |
| Độ dễ đọc trong database | Cao | Cần tra cứu enum đúng phiên bản |
| Đổi thứ tự hằng | Thông thường không đổi ý nghĩa dữ liệu | Có thể âm thầm làm dữ liệu bị hiểu sai |
| Thêm hằng giữa danh sách | Không đổi ý nghĩa chuỗi cũ | Có thể đổi ý nghĩa số cũ |
| Đổi tên hằng | Cần migration dữ liệu/chiến lược tương thích | Không tác động nếu ordinal giữ nguyên |
| Xóa hằng đang có dữ liệu | Dữ liệu cũ có thể không đọc được | Có thể bị lệch chỉ số hoặc vượt phạm vi |
| DDL thường thấy | `VARCHAR`/kiểu tương đương | `SMALLINT`/`INTEGER`/kiểu tương đương |
| Dữ liệu tự mô tả | Tương đối tốt | Kém |
| Sự phụ thuộc vào mã nguồn | Phụ thuộc tên hằng | Phụ thuộc thứ tự hằng |
| Khi nên cân nhắc | Phần lớn trạng thái nghiệp vụ | Trường hợp có lý do và quy trình bảo đảm thứ tự bất biến |

**Lựa chọn thường được ưu tiên cho entity nghiệp vụ là `EnumType.STRING`**, vì khả năng thay đổi thứ tự enum mà không làm sai nghĩa dữ liệu cũ hữu ích hơn lợi thế nhỏ về biểu diễn số. Tuy nhiên, `STRING` vẫn yêu cầu quy trình migration nếu đổi tên hoặc loại bỏ trạng thái.

## 6. Viết entity hoàn chỉnh với `EnumType.STRING`

Giả sử ứng dụng quản lý đơn hàng. Ta khai báo enum và entity ở hai file:

**`OrderStatus.java`**

```java
public enum OrderStatus {
    CREATED,
    PAID,
    CANCELLED
}
```

**`PurchaseOrder.java`**

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "customer_name", nullable = false, length = 120)
    private String customerName;

    protected PurchaseOrder() {
        // JPA khởi tạo entity khi cần.
    }

    public PurchaseOrder(String customerName) {
        if (customerName == null || customerName.isBlank()) {
            throw new IllegalArgumentException("customerName");
        }
        this.customerName = customerName.trim();
        this.status = OrderStatus.CREATED;
    }

    public void markPaid() {
        if (status != OrderStatus.CREATED) {
            throw new IllegalStateException(
                "Only a created order can be marked paid"
            );
        }
        status = OrderStatus.PAID;
    }

    public void cancel() {
        if (status != OrderStatus.CREATED) {
            throw new IllegalStateException(
                "Only a created order can be cancelled"
            );
        }
        status = OrderStatus.CANCELLED;
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public String getCustomerName() {
        return customerName;
    }
}
```

Ở đây:

- `@Entity` khai báo entity JPA.
- `@Id` và `@GeneratedValue` xác định cách tạo khóa chính.
- `@Enumerated(EnumType.STRING)` xác định cách lưu `OrderStatus` theo tên.
- `@Column(nullable = false, length = 20)` mô tả metadata cột.
- Constructor nghiệp vụ khởi tạo trạng thái `CREATED` khi tạo đơn mới.
- Các method `markPaid()` và `cancel()` giữ quy tắc chuyển trạng thái ở tầng domain, thay vì để mọi nơi gọi một setter bất kỳ.

Ví dụ ghi trong transaction resource-local:

```java
EntityManager em = entityManagerFactory.createEntityManager();

try {
    em.getTransaction().begin();

    PurchaseOrder order = new PurchaseOrder("Nguyễn An");
    em.persist(order);

    order.markPaid();

    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Ở trạng thái managed, JPA provider theo dõi thay đổi `status` và đồng bộ khi cần. Giá trị của cột `status` cho entity mới sau khi transaction thành công sẽ tương ứng `PAID`, với điều kiện schema và các constraint tương thích.

Trong ứng dụng dùng Spring/Jakarta EE, transaction có thể được quản lý bởi framework/container; đoạn trên chỉ mô tả trường hợp resource-local.

### Muốn đổi sang `ORDINAL` cần thay đổi gì?

Đối với entity, đoạn mapping tương ứng là:

```java
@Enumerated(EnumType.ORDINAL)
@Column(name = "status", nullable = false)
private OrderStatus status;
```

Nhưng nếu bảng đã có dữ liệu `"CREATED"`, `"PAID"`, `"CANCELLED"` ở dạng chuỗi, **không thể an toàn chỉ sửa annotation**. Cần migration dữ liệu, kiểu cột và constraint.

## 7. Không khai báo `@Enumerated` sẽ ra sao?

Một đoạn entity rất dễ bắt gặp là:

```java
@Entity
public class Payment {
    @Id
    private Long id;

    private PaymentStatus status;
}
```

Nếu dùng cách ánh xạ enum truyền thống, không có annotation tường minh thường dẫn đến ánh xạ **theo ordinal**. Tuy nhiên, các phiên bản mới của Jakarta Persistence có quy tắc suy luận bổ sung khi enum sử dụng cơ chế `@EnumeratedValue`. Vì vậy, không nên lấy một ví dụ mặc định của phiên bản cũ rồi coi là quy tắc không bao giờ đổi.

Để code tự mô tả và dễ review, hãy **ghi rõ loại mapping**:

```java
@Enumerated(EnumType.STRING)
private PaymentStatus status;
```

Một chi tiết khác: nếu viết `@Enumerated` mà không truyền tham số, giá trị mặc định của phần tử `value` trong annotation là `EnumType.ORDINAL`. Đây là lý do hai dòng sau không nên được xem là lựa chọn giống `STRING`:

```java
@Enumerated
private PaymentStatus status;

// Tương đương ý định mapping ordinal:
@Enumerated(EnumType.ORDINAL)
private PaymentStatus status;
```

Đoạn trên chỉ minh họa **hai cách diễn đạt thay thế** cho cùng một thuộc tính, không phải hai field cùng tồn tại trong một class.

### Ghi chú về `@EnumeratedValue` trong các phiên bản Jakarta Persistence mới

Jakarta Persistence 3.2 bổ sung `@EnumeratedValue` để cho phép một enum khai báo **giá trị ánh xạ tường minh** thay vì chỉ dựa vào `name()`/`ordinal()`. Khả năng này có các yêu cầu riêng về kiểu field và sự tương thích của JPA provider. Khi dùng phiên bản JPA đời trước hoặc muốn viết code phổ biến giữa nhiều môi trường, đừng giả định annotation mới đã có sẵn.

Điểm quan trọng cho bài học: **`@Enumerated(EnumType.STRING)` truyền thống ánh xạ tên hằng**, còn **`@Enumerated(EnumType.ORDINAL)` truyền thống ánh xạ vị trí**. Nếu cần giá trị mã nghiệp vụ tùy chỉnh, hãy xem xét giải pháp tường minh như `AttributeConverter` hoặc `@EnumeratedValue` khi phiên bản đặc tả/provider cho phép.

## 8. Query với enum: JPQL khác SQL trực tiếp

Khi dùng JPQL, ta làm việc với **thuộc tính enum Java**, không cần tự đổi enum thành chuỗi hoặc số.

Ví dụ query các đơn đã thanh toán:

```java
List<PurchaseOrder> paidOrders = entityManager.createQuery(
    "SELECT o FROM PurchaseOrder o WHERE o.status = :status",
    PurchaseOrder.class
).setParameter("status", OrderStatus.PAID)
 .getResultList();
```

`:status` nhận `OrderStatus.PAID`. Provider sẽ chuyển tham số sang giá trị database dựa trên mapping của thuộc tính: theo `STRING` hoặc `ORDINAL`.

Nên giữ kiểu mạnh như trên thay vì truyền `"PAID"` vào tham số JPQL có kiểu enum:

```java
// Dễ tạo mismatch kiểu tham số; không nên làm cách mặc định.
.setParameter("status", "PAID")
```

Nếu dùng Criteria API, nguyên tắc vẫn giống nhau: predicate so sánh với `OrderStatus.PAID` theo kiểu thuộc tính enum.

### Khi dùng native SQL

Native SQL thao tác trực tiếp với biểu diễn vật lý trong DB. Ví dụ với cột `VARCHAR` lưu theo `STRING`:

```sql
SELECT id, status
FROM orders
WHERE status = 'PAID';
```

Nếu hệ thống vẫn lưu theo `ORDINAL`:

```sql
SELECT id, status
FROM orders
WHERE status = 1;
```

SQL thứ hai chỉ có nghĩa `PAID` nếu enum ở phiên bản đang dùng đặt `PAID` tại vị trí `1`. Việc hard-code `1` vào script, báo cáo hoặc dịch vụ khác khiến rủi ro lệch thứ tự lan ra ngoài ứng dụng Java.

Nếu sử dụng `EntityManager.createNativeQuery()`, phương thức gọi là API JPA chuẩn, nhưng chuỗi SQL bên trong vẫn phụ thuộc schema và loại giá trị đang lưu.

## 9. Enum không phải một hệ thống trạng thái nghiệp vụ hoàn chỉnh

`enum` giúp giới hạn tập trạng thái hợp lệ trong Java; nó **không tự thực thi** quy tắc chuyển trạng thái hay bảo vệ dữ liệu khi một tác nhân khác ghi trực tiếp SQL.

Ví dụ:

```java
public void markPaid() {
    if (status != OrderStatus.CREATED) {
        throw new IllegalStateException(
            "Invalid transition to PAID"
        );
    }
    status = OrderStatus.PAID;
}
```

Hàm trên áp dụng quy tắc từ `CREATED` sang `PAID`. Nhưng câu SQL:

```sql
UPDATE orders
SET status = 'PAID'
WHERE id = 101;
```

có thể ghi lại trạng thái mà không chạy phương thức Java, trừ khi schema/triggers hoặc cơ chế khác ngăn điều đó.

Các trách nhiệm nên được phân biệt:

| Trách nhiệm | Cơ chế điển hình |
| --- | --- |
| Danh sách tên trạng thái trong Java | `enum OrderStatus` |
| Biểu diễn trạng thái trong DB | `@Enumerated`, converter hoặc cơ chế ánh xạ khác |
| Quy tắc chuyển trạng thái | Method nghiệp vụ, service/domain logic |
| Cấm `NULL` | `NOT NULL` trong DB; `@Column(nullable = false)` là metadata |
| Giới hạn tập giá trị DB cho phép | `CHECK`, native enum, bảng tham chiếu, constraint |
| Ngăn hai transaction ghi đè nhau | `@Version`, locking, transaction strategy |
| Xử lý thay đổi cấu trúc dữ liệu | Migration script và quy trình triển khai |

Cách ánh xạ enum **không thay thế** các biện pháp toàn vẹn dữ liệu.

## 10. `NULL` và giá trị không hợp lệ

Giả sử thuộc tính:

```java
@Enumerated(EnumType.STRING)
@Column(nullable = false)
private OrderStatus status;
```

`null` trong Java và `NULL` trong SQL cần được xử lý rõ ràng. `@Column(nullable = false)` thể hiện ý định cột không chấp nhận null; ứng dụng cần bảo đảm schema thực tế có `NOT NULL` và tránh đưa entity vào trạng thái thiếu dữ liệu.

Một enum không có giá trị `UNKNOWN` vẫn có thể nhận `null` vì enum là kiểu tham chiếu Java. Nếu domain yêu cầu mọi đơn hàng luôn có trạng thái, đặt giá trị khởi tạo hợp lệ trong constructor nghiệp vụ và bảo vệ bằng DB constraint.

### Dữ liệu ngoài tập giá trị Java

Nếu cột đang chứa `"ARCHIVED"` trong khi enum không có hằng `ARCHIVED`, việc đọc bằng `STRING` có thể thất bại khi provider chuyển dữ liệu thành enum.

Với `ORDINAL`, nếu cột chứa `99` nhưng enum chỉ có 3 hằng, chuyển đổi cũng có thể thất bại. Nguy hiểm hơn là trường hợp số **vẫn nằm trong phạm vi** nhưng đã mang nghĩa khác do thay đổi thứ tự; khi đó có thể không có lỗi kỹ thuật.

Đừng tự động biến mọi mã lạ thành một trạng thái hợp lệ tùy tiện. Nếu cần mô hình “giá trị chưa biết”, hãy thiết kế chính sách rõ ràng về tương thích dữ liệu, phát hiện lỗi và logging.

## 11. Dùng ràng buộc database cho enum

### 11.1. Với `EnumType.STRING`

Một ràng buộc có thể diễn đạt tập giá trị:

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT chk_orders_status
        CHECK (status IN ('CREATED', 'PAID', 'CANCELLED'))
);
```

Ưu điểm: database từ chối giá trị `"DONE"` do một script khác ghi vào nếu không thuộc tập cho phép.

Đánh đổi: khi thêm `SHIPPED`, migration phải mở rộng constraint trước khi ứng dụng bắt đầu ghi giá trị mới. Cú pháp chỉnh constraint khác nhau giữa PostgreSQL, MySQL, Oracle và các RDBMS khác.

### 11.2. Với `EnumType.ORDINAL`

Có thể giới hạn các giá trị số trong tập hiện tại:

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status SMALLINT NOT NULL,
    CONSTRAINT chk_orders_status
        CHECK (status IN (0, 1, 2))
);
```

Tuy nhiên, constraint số **không giải quyết lỗi đổi ý nghĩa ordinal**. Khi code đổi `1` từ `PAID` sang `CANCELLED`, DB vẫn thấy số `1` hoàn toàn hợp lệ.

Điều này cho thấy tính hợp lệ về mặt SQL và tính đúng nghiệp vụ không phải lúc nào cũng đồng nhất.

### 11.3. Native enum hoặc lookup table

Một số database có kiểu enum native; một số hệ thống chọn bảng tham chiếu:

```sql
CREATE TABLE order_statuses (
    code VARCHAR(20) PRIMARY KEY,
    display_name VARCHAR(100) NOT NULL
);

INSERT INTO order_statuses(code, display_name)
VALUES
    ('CREATED', 'Created'),
    ('PAID', 'Paid'),
    ('CANCELLED', 'Cancelled');
```

Sau đó cột `orders.status` có thể chứa foreign key đến `order_statuses.code`. Đây là quyết định schema ngoài việc chọn `@Enumerated`. Với tập giá trị cần dữ liệu cấu hình, mô tả đa ngôn ngữ hoặc có thể thay đổi lúc vận hành, **bảng tham chiếu và entity riêng** có thể thích hợp hơn enum hard-code.

Không nên tạo enum Java nếu tập trạng thái thực tế phải được thêm/sửa/xóa tự do bởi người quản trị tại runtime.

## 12. Đổi thứ tự, thêm, xóa hoặc đổi tên enum trong hệ thống đang chạy

Hãy coi enum persistent là một **định dạng dữ liệu có phiên bản**. Mỗi thay đổi trong mã nguồn cần được đánh giá đối với các bản ghi đã tồn tại.

### Trường hợp A: đổi thứ tự khai báo

Ban đầu:

```java
CREATED, PAID, CANCELLED
```

Sau đó:

```java
CANCELLED, CREATED, PAID
```

- Với `STRING`: các chuỗi cũ tiếp tục tương ứng đúng tên hằng.
- Với `ORDINAL`: số cũ mang nghĩa mới; muốn giữ dữ liệu phải migration tất cả số liên quan theo mapping thực tế.

### Trường hợp B: thêm hằng giữa danh sách

```java
CREATED, PAYMENT_PENDING, PAID, CANCELLED
```

- `STRING`: chuỗi cũ ổn, nhưng database constraint có thể cần thêm `PAYMENT_PENDING`; các bản ứng dụng cũ có thể không đọc được giá trị mới.
- `ORDINAL`: `PAID` và `CANCELLED` bị đổi vị trí, dữ liệu cũ sẽ sai nếu không migration.

### Trường hợp C: đổi tên hằng

```java
PAID  // phiên bản trước
PAYMENT_COMPLETED  // phiên bản sau
```

- `STRING`: cần migration chuỗi cũ hoặc cơ chế đọc song song phù hợp trong giai đoạn chuyển đổi.
- `ORDINAL`: nếu thứ tự giữ nguyên, số không đổi; nhưng vẫn có thể cần cập nhật logic nghiệp vụ và API bên ngoài.

### Trường hợp D: xóa hằng

Xóa `CANCELLED` khỏi Java trong khi database vẫn chứa giá trị tương ứng có thể gây lỗi load.

Với `ORDINAL`, xóa một hằng ở giữa còn có thể dịch chuyển mọi ordinal phía sau. Cần xác minh dữ liệu cũ, xử lý các bản ghi tồn tại và kiểm soát thứ tự trước khi triển khai phiên bản mới.

### Trường hợp E: hai phiên bản ứng dụng chạy song song

Khi rolling deployment, phiên bản mới có thể ghi trạng thái `SHIPPED` mà phiên bản cũ chưa biết. Với `STRING`, bản cũ có thể không giải mã được chuỗi mới. Với `ORDINAL`, rủi ro còn có thể là hiểu sai số.

Vì vậy, hỗ trợ triển khai không downtime có thể yêu cầu **giai đoạn tương thích**, chẳng hạn mở rộng schema trước, giữ khả năng đọc cả trạng thái cũ/mới, trì hoãn ghi giá trị mới tới khi toàn bộ ứng dụng đã nâng cấp.

## 13. Migration từ `ORDINAL` sang `STRING`

Chuyển từ số sang chuỗi là một thay đổi phổ biến khi muốn ngăn rủi ro do sắp xếp lại enum. Không nên chỉ sửa:

```java
@Enumerated(EnumType.ORDINAL)
```

thành:

```java
@Enumerated(EnumType.STRING)
```

trên bảng đang có dữ liệu. Provider sẽ cố đọc số như chuỗi tên enum hoặc ghi chuỗi vào cột số, gây lỗi hoặc dữ liệu không phù hợp.

### 13.1. Lập bảng mapping theo phiên bản cũ

Giả sử phiên bản đã ghi dữ liệu có enum:

| Giá trị cũ trong DB | Ý nghĩa |
| ---: | --- |
| 0 | CREATED |
| 1 | PAID |
| 2 | CANCELLED |

Bảng mapping phải được lấy từ **phiên bản code thực sự đã ghi dữ liệu**. Nếu enum từng bị sắp xếp lại trong quá khứ mà không migration, một số giá trị có thể đã mang nghĩa sai. Không được tự động coi enum hiện tại là bằng chứng đủ để chuyển toàn bộ lịch sử.

### 13.2. Thêm cột mới và chuyển có kiểm soát

Ví dụ SQL minh họa ở hệ quản trị hỗ trợ `CASE`:

```sql
ALTER TABLE orders
ADD COLUMN status_name VARCHAR(20);

UPDATE orders
SET status_name = CASE status
    WHEN 0 THEN 'CREATED'
    WHEN 1 THEN 'PAID'
    WHEN 2 THEN 'CANCELLED'
    ELSE NULL
END;
```

Kiểm tra bản ghi không chuyển được:

```sql
SELECT id, status
FROM orders
WHERE status_name IS NULL;
```

Nếu truy vấn trả về bản ghi, cần xử lý nguyên nhân trước khi áp dụng constraint chặt hơn. Không tự gán trạng thái mặc định cho dữ liệu lạ nếu chưa xác định nghiệp vụ.

Sau khi dữ liệu đã chuyển đúng, có thể bổ sung constraint phù hợp:

```sql
ALTER TABLE orders
ADD CONSTRAINT chk_orders_status_name
CHECK (status_name IN ('CREATED', 'PAID', 'CANCELLED'));
```

Và thiết lập `NOT NULL` khi đã xác nhận tất cả bản ghi hợp lệ; cú pháp thao tác này phụ thuộc RDBMS.

### 13.3. Triển khai tương thích nhiều phiên bản

Với hệ thống có thể dừng ghi để migration, cách thực hiện có thể đơn giản: bảo đảm backup, migration có kiểm soát, đổi mapping, chạy kiểm chứng rồi mở lưu lượng trở lại.

Với hệ thống phải rolling deployment, cần thiết kế cụ thể hơn: giai đoạn thêm cột mới, ghi đồng thời hai dạng trong phạm vi cần thiết, backfill, chuyển dần luồng đọc, xác nhận mọi instance đã nâng cấp, rồi mới bỏ cột cũ. Đây là mô hình *expand–migrate–contract*. Không phải mọi hệ thống đều cần quy trình phức tạp này, nhưng **không được bỏ qua khả năng phiên bản cũ và mới cùng ghi dữ liệu trong lúc deploy**.

### 13.4. Đổi tên chuỗi enum cũng là migration

Nếu đang dùng `STRING` và đổi tên `PAID` thành `PAYMENT_COMPLETED`:

```sql
UPDATE orders
SET status = 'PAYMENT_COMPLETED'
WHERE status = 'PAID';
```

Về logic đây là ví dụ đơn giản, nhưng trong triển khai rolling deployment, bước đổi code, constraint và dữ liệu phải được phối hợp để tránh khiến phiên bản cũ không hiểu giá trị mới. Nên kiểm tra tất cả nơi sử dụng chuỗi này, gồm API, job, consumer, báo cáo và hệ thống tích hợp.

## 14. Khi tên enum không phải mã lưu trữ mong muốn: `AttributeConverter`

Một số hệ thống muốn dùng mã ổn định, ngắn gọn trong DB, chẳng hạn:

| Enum Java | Mã DB | Ý nghĩa |
| --- | --- | --- |
| `CREATED` | `"C"` | Vừa tạo |
| `PAID` | `"P"` | Đã thanh toán |
| `CANCELLED` | `"X"` | Đã hủy |

Mã `"C"`, `"P"`, `"X"` **không trùng `name()` và cũng không phải `ordinal()`**. Với các phiên bản Jakarta Persistence hỗ trợ `AttributeConverter`, ta có thể xác định mapping tường minh.

**`OrderStatus.java`**

```java
public enum OrderStatus {
    CREATED("C"),
    PAID("P"),
    CANCELLED("X");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        for (OrderStatus value : values()) {
            if (value.code.equals(code)) {
                return value;
            }
        }
        throw new IllegalArgumentException(
            "Unknown order status code: " + code
        );
    }
}
```

**`OrderStatusConverter.java`**

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = false)
public class OrderStatusConverter
        implements AttributeConverter<OrderStatus, String> {

    @Override
    public String convertToDatabaseColumn(OrderStatus attribute) {
        return attribute == null ? null : attribute.getCode();
    }

    @Override
    public OrderStatus convertToEntityAttribute(String dbData) {
        return dbData == null ? null : OrderStatus.fromCode(dbData);
    }
}
```

**Trong entity:**

```java
import jakarta.persistence.Column;
import jakarta.persistence.Convert;

@Convert(converter = OrderStatusConverter.class)
@Column(name = "status_code", length = 1, nullable = false)
private OrderStatus status;
```

Trong ví dụ này, `OrderStatus.PAID` được lưu là `"P"`. Nếu sau này rename hằng Java thành `PAYMENT_COMPLETED` nhưng **giữ nguyên `code = "P"`**, dữ liệu cũ vẫn có thể ánh xạ về hằng mới mà không đổi mã lưu trữ. Tất nhiên mọi nơi gọi tên hằng trong code phải được cập nhật.

### Lưu ý quan trọng với converter

- **Không đặt `@Enumerated` và `@Convert` trên cùng một thuộc tính enum** để hy vọng cả hai cùng xử lý; chúng là hai chiến lược mapping cạnh tranh.
- `@Converter(autoApply = false)` buộc thuộc tính phải chỉ định converter bằng `@Convert`. Nếu dùng `autoApply = true`, converter có thể được áp dụng cho các thuộc tính cùng kiểu enum trong phạm vi persistence unit theo quy tắc chuẩn, cần cân nhắc tác động lan rộng.
- Converter phải xử lý `null` và giá trị lạ theo chính sách rõ ràng. Ném exception khi gặp mã không hợp lệ giúp phát hiện dữ liệu không đúng, nhưng có thể cần một chiến lược tương thích riêng nếu nhiều phiên bản ứng dụng chạy song song.
- Dữ liệu DB và constraint phải tương ứng `"C"`, `"P"`, `"X"`, không còn là `"CREATED"`/`"PAID"`/`"CANCELLED"`.
- Converter mã ổn định không tự làm toàn bộ hệ thống tương thích khi bổ sung trạng thái chưa biết đối với phiên bản cũ.

Đây là giải pháp phù hợp khi **mã lưu trữ là một hợp đồng nghiệp vụ độc lập với tên class/enum**, thay vì đơn thuần là một lựa chọn tiết kiệm vài byte.

## 15. `@EnumeratedValue` là một hướng khác ở Jakarta Persistence mới

Trong Jakarta Persistence 3.2, `@EnumeratedValue` cung cấp cách khai báo giá trị database trên một trường `final` của enum, với yêu cầu kiểu phù hợp theo `EnumType`. Ví dụ về mặt ý tưởng, nếu API/provider hỗ trợ phiên bản đó:

```java
public enum OrderStatus {
    CREATED("C"),
    PAID("P"),
    CANCELLED("X");

    @jakarta.persistence.EnumeratedValue
    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }
}
```

Với kiểu dữ liệu `String`, cơ chế này hướng tới biểu diễn enum bằng chuỗi giá trị khai báo, thay vì bắt buộc dựa vào `name()`. Các kiểu hỗ trợ và quy tắc suy luận phải tuân theo phiên bản đặc tả cụ thể.

Không nên chép đoạn ví dụ vào dự án đang sử dụng Jakarta Persistence 3.0/3.1 hoặc JPA `javax.persistence` mà chưa kiểm tra API và provider: annotation này có thể chưa tồn tại. Nếu dự án cần hỗ trợ nhiều phiên bản JPA, `AttributeConverter` thường là giải pháp quen thuộc hơn.

Khía cạnh cần ghi nhớ của bài học là sự phân biệt giữa:

- **Theo tên enum**: `@Enumerated(EnumType.STRING)` theo cách truyền thống.
- **Theo vị trí enum**: `@Enumerated(EnumType.ORDINAL)`.
- **Theo giá trị ánh xạ tường minh**: converter hoặc tính năng `@EnumeratedValue` nếu môi trường hỗ trợ.

Chúng không được chọn đồng thời trên cùng một thuộc tính với kỳ vọng provider tự kết hợp kết quả.

## 16. Collection và Map có enum trong JPA

Không chỉ một field enum riêng lẻ mới cần mapping. Một entity còn có thể lưu **tập enum**.

Giả sử khách hàng được bật nhiều quyền nhận thông báo:

```java
public enum NotificationChannel {
    EMAIL,
    SMS,
    PUSH
}
```

Ánh xạ collection:

```java
import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;

@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
    name = "customer_channels",
    joinColumns = @JoinColumn(name = "customer_id")
)
@Enumerated(EnumType.STRING)
@Column(name = "channel", nullable = false, length = 20)
private java.util.Set<NotificationChannel> channels =
    new java.util.HashSet<>();
```

Ví dụ này nằm bên trong một entity `Customer` có `@Id`. Bảng `customer_channels` có thể có các hàng:

| customer_id | channel |
| ---: | --- |
| 42 | EMAIL |
| 42 | PUSH |

Ở đây, `@Enumerated(EnumType.STRING)` áp dụng cho **các phần tử enum trong collection**, và mỗi phần tử được lưu thành một giá trị liên quan tới owner qua `customer_id`.

Một map có enum làm **key** có thể cần `@MapKeyEnumerated` theo quy tắc ánh xạ `Map` của JPA, chẳng hạn `@MapKeyEnumerated(EnumType.STRING)`. Phân biệt annotation dùng cho key và annotation dùng cho giá trị để không vô tình ánh xạ một phía sai.

Các loại collection còn cần xét riêng khóa owner, tính duy nhất, thứ tự, schema và cơ chế tải dữ liệu. `@Enumerated` chỉ giải quyết **cách biểu diễn từng giá trị enum**, không giải quyết toàn bộ cấu trúc quan hệ của collection.

## 17. Sắp xếp, lọc và so sánh enum trong database

Một hiểu lầm thường gặp là giả định thứ tự enum Java luôn được phản ánh khi SQL sắp xếp.

Với `STRING`:

```sql
SELECT status
FROM orders
ORDER BY status;
```

database thường sắp xếp theo quy tắc chuỗi/collation, ví dụ `CANCELLED`, `CREATED`, `PAID`. Đây là **thứ tự từ vựng**, không phải thứ tự tiến triển của quy trình đơn hàng.

Với `ORDINAL`, SQL sắp xếp số `0, 1, 2` theo thứ tự enum **ở phiên bản đã ghi dữ liệu**. Nhưng thứ tự đó vẫn có thể không phản ánh mức ưu tiên hay trật tự nghiệp vụ đúng, và sẽ nguy hiểm khi danh sách được sắp xếp lại trong code.

Nếu nghiệp vụ muốn:

```text
CREATED → PAID → CANCELLED
```

hoặc mức ưu tiên:

```text
HIGH → MEDIUM → LOW
```

hãy mô hình hóa **sort order** như một thông tin tường minh nếu cần sử dụng trong báo cáo/query, thay vì dựa vào `name()` hay `ordinal()` một cách ngẫu nhiên.

Ví dụ với SQL:

```sql
SELECT id, status
FROM orders
ORDER BY CASE status
    WHEN 'CREATED' THEN 1
    WHEN 'PAID' THEN 2
    WHEN 'CANCELLED' THEN 3
    ELSE 99
END;
```

Câu lệnh này minh họa ý nghĩa của sort order; trong dự án thực tế có thể đưa thứ tự nghiệp vụ vào bảng tham chiếu hoặc ánh xạ/projection riêng nếu nó là dữ liệu quan trọng, cần thay đổi linh hoạt.

## 18. Truyền enum qua API và message khác với lưu enum trong DB

Ví dụ DTO REST:

```java
public record OrderResponse(
    Long id,
    OrderStatus status
) {}
```

JSON serialization thường có quy tắc biểu diễn enum riêng, có thể phụ thuộc thư viện Jackson hoặc cấu hình. `@Enumerated(EnumType.STRING)` quy định **cách JPA ánh xạ enum với database**, không tự chuẩn hóa JSON của REST API.

Một hệ thống có thể:

- Lưu `"P"` trong database bằng `AttributeConverter`.
- Sử dụng `OrderStatus.PAID` trong Java.
- Trả `"paid"` hoặc `"PAID"` trong JSON tùy hợp đồng API.

Ba tầng này có thể chọn các biểu diễn khác nhau, và mỗi tầng cần chính sách tương thích khi nâng cấp. Đừng đổi tên enum để sửa JSON nếu việc đó vô tình làm thay đổi dữ liệu JPA lưu theo `STRING`. Khi cần, dùng DTO và mapping rõ ràng tại ranh giới API.

## 19. Những sai lầm phổ biến

**Sai lầm 1: “Ordinal là ID cố định của enum.”**

`ordinal()` là chỉ số vị trí, không phải ID nghiệp vụ. Muốn mã cố định phải thiết kế code tường minh hoặc dùng converter/khả năng chuẩn phù hợp.

**Sai lầm 2: “Chỉ đổi annotation là chuyển được dữ liệu.”**

Đổi `ORDINAL` ↔ `STRING` là đổi định dạng lưu. Cần migration dữ liệu, kiểu cột và constraint; không phải chỉ đổi code Java.

**Sai lầm 3: “STRING không bao giờ cần migration.”**

Đổi tên hoặc xóa enum đang có dữ liệu vẫn cần xử lý các giá trị cũ. Thêm hằng có thể cần cập nhật CHECK/native enum/ứng dụng phiên bản cũ.

**Sai lầm 4: “Không viết `@Enumerated` thì mặc định là STRING.”**

Không nên giả định điều này. Với cách ánh xạ truyền thống, annotation bỏ trống hoặc dùng `EnumType.ORDINAL` sẽ ánh xạ theo số thứ tự; phiên bản mới có thêm quy tắc suy luận cụ thể. Ghi tường minh chiến lược phù hợp giúp tránh mập mờ.

**Sai lầm 5: “Số ordinal bắt đầu từ 1.”**

Java `ordinal()` bắt đầu từ `0`. `PAID` ở vị trí thứ hai có ordinal bằng `1`, không phải `2`.

**Sai lầm 6: “@Enumerated bảo đảm chỉ lưu trạng thái hợp lệ ở DB.”**

Annotation chỉ mô tả quy tắc ánh xạ. Database constraint và transaction mới quyết định các ràng buộc dữ liệu được áp dụng thực tế.

**Sai lầm 7: “Mã enum trên API giống hệt mã trong SQL.”**

Serializer JSON, JPA và database là các tầng khác nhau; mỗi tầng có thể chọn một format riêng.

**Sai lầm 8: “Thêm `UNKNOWN` là đủ để đọc mọi dữ liệu lạ.”**

Khi DB chứa giá trị không ánh xạ được, provider/converter không tự chọn `UNKNOWN` trừ khi có logic hỗ trợ rõ ràng. Nếu quyết định hỗ trợ trạng thái chưa biết, hãy thiết kế chính sách đó có chủ đích và tránh che giấu dữ liệu bị lỗi.

## 20. Bài tập thực hành

### Bài tập 1: Dự đoán dữ liệu

Cho enum:

```java
public enum ShippingMethod {
    STANDARD,
    EXPRESS,
    PICKUP
}
```

Entity có:

```java
@Enumerated(EnumType.STRING)
private ShippingMethod method;
```

Nếu giá trị Java là `ShippingMethod.EXPRESS`, DB lưu gì?

**Đáp án:** `"EXPRESS"` theo mapping tên. Nếu đổi annotation thành `EnumType.ORDINAL`, giá trị sẽ là `1` theo thứ tự hiện tại.

### Bài tập 2: Phát hiện lỗi khi thêm enum

Version 1:

```java
public enum Priority {
    LOW, MEDIUM, HIGH
}
```

DB dùng ordinal và đang lưu `2` cho `HIGH`.

Version 2:

```java
public enum Priority {
    LOW, URGENT, MEDIUM, HIGH
}
```

**Câu hỏi:** DB `2` giờ tương ứng enum nào? Điều gì xảy ra với bản ghi ưu tiên cao cũ?

**Đáp án:** `2` giờ là `MEDIUM`. Bản ghi trước đây thuộc `HIGH` bị hiểu thành `MEDIUM` nếu không chuyển đổi dữ liệu.

### Bài tập 3: Đổi tên trong `STRING`

Ban đầu DB có:

```text
status = "PAID"
```

Mã Java mới chỉ còn:

```java
PAYMENT_COMPLETED
```

**Câu hỏi:** Vì sao có thể lỗi khi tải bản ghi?

**Đáp án:** Mapping theo tên tìm hằng phù hợp với `"PAID"` nhưng hằng đó đã bị xóa/đổi tên. Cần migration hoặc cơ chế tương thích có kiểm soát.

### Bài tập 4: Chọn giải pháp lưu mã chuẩn doanh nghiệp

Hệ thống phải lưu trạng thái bằng các mã `"C"`, `"P"`, `"X"` do một ứng dụng khác đã sử dụng lâu năm; tên enum Java có thể thay đổi.

**Câu hỏi:** Có nên dựa vào `ordinal()` không?

**Đáp án:** Không. Dùng mã ổn định được định nghĩa tường minh và ánh xạ bằng `AttributeConverter`, hoặc sử dụng khả năng ánh xạ giá trị tương đương nếu phiên bản Jakarta Persistence/provider hỗ trợ. Điều này tách format lưu trữ khỏi vị trí hằng Java.

### Bài tập 5: Thiết kế triển khai

Một ứng dụng có nhiều instance chạy rolling deployment. Version mới bổ sung `SHIPPED` vào enum, DB lưu `STRING` và có CHECK chỉ chấp nhận ba trạng thái cũ.

**Câu hỏi:** Ngoài thêm hằng Java, còn phải chuẩn bị gì?

**Gợi ý:** Mở rộng CHECK/DDL, đánh giá ứng dụng phiên bản cũ có đọc được dữ liệu `SHIPPED` không, lập thứ tự bật tính năng ghi trạng thái mới, chuẩn bị migration và test tích hợp trên DB mục tiêu.

## 21. Quy tắc lựa chọn trong dự án thực tế

Khi thêm thuộc tính enum vào entity, có thể dùng chuỗi câu hỏi sau:

1. **Đây có phải tập giá trị hữu hạn ổn định trong Java?** Nếu dữ liệu thay đổi tùy cấu hình runtime, cân nhắc bảng tham chiếu/entity riêng.
2. **Dữ liệu có cần tồn tại qua nhiều bản phát hành?** Nếu có, ưu tiên `STRING` hoặc mã tường minh thay vì ordinal dễ thay đổi theo code.
3. **Tên hằng enum có được phép đổi không?** Nếu cần đổi tên mà không đổi mã lưu trữ, cân nhắc `AttributeConverter` hoặc `@EnumeratedValue` trên môi trường hỗ trợ.
4. **Database đã lưu giá trị theo định dạng nào?** Phải biết trước khi sửa annotation; cần migration nếu đổi format.
5. **Cột có ràng buộc gì?** Xem kiểu cột, `NOT NULL`, `CHECK`, native enum/lookup table và độ dài.
6. **Có hệ thống hoặc phiên bản khác đang đọc/ghi cùng dữ liệu không?** Thiết kế backward/forward compatibility, đặc biệt khi rolling deployment.
7. **Có cần sắp xếp nghiệp vụ hay tính toán trên trạng thái không?** Tách sort order/transition rule khỏi `name()` và `ordinal()`.
8. **Đã có dữ liệu lịch sử sai nghĩa do enum reorder chưa?** Nếu có, cần phân tích dữ liệu thực tế trước migration để tránh tiếp tục ghi đè thông tin.

Với phần lớn entity nghiệp vụ bình thường, mapping rõ ràng:

```java
@Enumerated(EnumType.STRING)
@Column(name = "status", nullable = false, length = 32)
private OrderStatus status;
```

là điểm khởi đầu hợp lý. Khi doanh nghiệp đã có bộ mã riêng bất biến, giải pháp converter hoặc ánh xạ giá trị tường minh phù hợp hơn. `ORDINAL` chỉ nên dùng nếu team chấp nhận và kiểm soát đầy đủ việc coi **thứ tự enum là hợp đồng dữ liệu**.

## Kết luận

`@Enumerated` là cầu nối giữa **enum Java** và **giá trị được lưu trong bảng quan hệ**. `EnumType.STRING` lưu theo tên hằng, dễ đọc và ít rủi ro khi thêm hoặc sắp xếp lại các trạng thái; `EnumType.ORDINAL` lưu theo vị trí hằng, có thể gọn hơn nhưng dễ gây sai nghĩa dữ liệu cũ nếu thứ tự Java thay đổi.

Không có lựa chọn nào tự giải quyết toàn bộ vấn đề tiến hóa dữ liệu. `STRING` cần migration khi đổi tên, còn `ORDINAL` cần bảo vệ thứ tự hoặc migration số một cách chặt chẽ. Khi cần mã nghiệp vụ ổn định độc lập với tên và vị trí enum, hãy dùng mapping giá trị tường minh phù hợp với phiên bản JPA.

Mỗi khi viết một field enum trong entity, hãy tự hỏi: **“Giá trị nào thực sự được lưu xuống database hôm nay, và code phiên bản sau sẽ giải thích giá trị ấy ra sao?”**. Trả lời được câu hỏi đó giúp tránh một trong những lỗi persistence khó phát hiện nhất: bản ghi vẫn đọc được về mặt kỹ thuật nhưng đã bị diễn giải sai về mặt nghiệp vụ.
