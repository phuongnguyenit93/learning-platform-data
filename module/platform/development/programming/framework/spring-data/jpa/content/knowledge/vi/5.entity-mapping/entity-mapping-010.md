# Quy tắc đặt tên vật lý, tên logic và tên trùng từ khóa SQL

## 1. Vì sao cần quy ước tên

Entity trong Java thường dùng `PascalCase` cho class và `camelCase` cho thuộc tính, trong khi schema cơ sở dữ liệu thường dùng `snake_case`. Ngoài khác biệt về kiểu viết, tên bảng và cột còn phải tránh các từ khóa SQL như `ORDER`, `GROUP` hoặc `USER`. Nếu tên trong mapping, tên Hibernate sinh ra và tên thật trong database không thống nhất, ứng dụng có thể gặp lỗi không tìm thấy bảng/cột hoặc lỗi cú pháp SQL khi chạy truy vấn.

Mục tiêu của quy ước đặt tên là làm rõ ba lớp tên, giữ mapping ổn định qua các môi trường và tránh phụ thuộc vào cách một hệ quản trị cơ sở dữ liệu xử lý từ khóa hay chữ hoa/chữ thường.

## 2. Phân biệt tên Entity, tên logic và tên vật lý

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Entity name | Tên entity mà JPQL sử dụng; mặc định thường là tên class, có thể đặt bằng `@Entity(name = "...")` | `PurchaseOrder` |
| Logical name | Tên Hibernate suy ra từ mapping tường minh hoặc quy tắc đặt tên ngầm định | `purchaseOrder`, `orderNumber` |
| Physical name | Tên identifier cuối cùng Hibernate gửi tới database sau khi áp dụng physical naming strategy | `purchase_order`, `order_number` |

Entity name thuộc mô hình đối tượng và truy vấn JPQL. Tên bảng/cột thuộc schema vật lý. `@Entity(name = "PurchaseOrder")` không tự đặt tên bảng; `@Table(name = "purchase_order")` mới khai báo tên bảng trong mapping. Tương tự, JPQL dùng thuộc tính Java `orderNumber`, trong khi SQL có thể dùng cột `order_number`.

## 3. Hibernate tạo tên như thế nào

Quá trình đặt tên có hai bước chính:

1. **Implicit naming strategy** tạo logical name khi mapping không khai báo tên tường minh. Ví dụ, entity `PurchaseOrder` và thuộc tính `orderNumber` có thể sinh tên logic từ tên class/field hoặc ngữ cảnh quan hệ.
2. **Physical naming strategy** nhận logical name và chuyển thành tên vật lý để dùng trong SQL. Đây là nơi quy tắc camelCase sang snake_case, chữ thường hoặc quy ước riêng của dự án được áp dụng.

Trong Spring Boot 3, cấu hình mặc định thường dùng `SpringImplicitNamingStrategy` và `CamelCaseToUnderscoresNamingStrategy`. Vì vậy `purchaseOrder` thường được chuyển thành `purchase_order`, còn `createdAt` thành `created_at`. Cấu hình cụ thể của ứng dụng có thể đã được ghi đè; hãy kiểm tra `spring.jpa.hibernate.naming` trước khi suy luận tên vật lý.

Có thể cấu hình rõ physical strategy trong `application.yml` khi dự án cần thống nhất hành vi:

```yaml
spring:
  jpa:
    hibernate:
      naming:
        physical-strategy: org.hibernate.boot.model.naming.CamelCaseToUnderscoresNamingStrategy
```

Không thay naming strategy giữa các môi trường. Một thay đổi ở đây có thể làm Hibernate tìm một tên bảng/cột khác với tên mà migration đã tạo.

## 4. Khai báo tên tường minh trong Entity

Ví dụ mapping dùng tên Java dễ đọc và tên vật lý theo snake_case:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity(name = "PurchaseOrder")
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column(name = "order_number", nullable = false, length = 40)
    private String orderNumber;

    @Column(name = "order_status", nullable = false, length = 30)
    private String status;
}
```

Đây là phần mapping minh họa; entity thực tế cần bổ sung constructor, accessor và các mapping khác theo yêu cầu ứng dụng. `@Table` khai báo bảng, `@Column` khai báo cột, còn `@Id` xác định khóa chính. `@JoinColumn` cũng có thể khai báo tên vật lý cho cột khóa ngoại.

Khi dùng naming strategy của Spring Boot, tên khai báo tường minh cũng đi qua physical naming strategy. Vì thế nên ghi tên theo đúng quy ước vật lý mong muốn, ví dụ `order_number`, thay vì trộn lẫn `orderNumber` rồi trông chờ mọi chiến lược đều chuyển đổi giống nhau.

## 5. Quy tắc tránh từ khóa SQL

Từ khóa SQL được định nghĩa theo dialect và phiên bản database. Một tên có thể hợp lệ ở hệ quản trị này nhưng lại là từ khóa hoặc tên đặc biệt ở hệ quản trị khác. Các ví dụ thường cần tránh gồm `order`, `group`, `user`, `key`, `value`, `rank`, `limit`, `select` và `table`; danh sách này không phải danh sách đầy đủ hay đồng nhất cho mọi database.

Ưu tiên đổi tên sang một danh từ nghiệp vụ rõ nghĩa:

| Tên dễ xung đột | Tên nên dùng |
| --- | --- |
| `order` | `purchase_order` |
| `user` | `user_account` hoặc `app_user` |
| `group` | `customer_group` hoặc `group_name` |
| `key` | `config_key` hoặc `key_code` |
| `value` | `config_value` hoặc `attribute_value` |
| `rank` | `sort_rank` hoặc `priority_rank` |
| `limit` | `page_limit` hoặc `credit_limit` |

Không nên chỉ dựa vào việc database hiện tại chấp nhận một tên. Khi dự án chuyển dialect, nâng phiên bản database hoặc chạy migration trên môi trường khác, tên đó có thể trở thành vấn đề. Quy tắc an toàn là dùng tên mô tả nghiệp vụ, nhất quán số ít/số nhiều, ưu tiên snake_case và tránh từ khóa phổ biến.

## 6. Khi phải ánh xạ schema cũ có tên trùng từ khóa

Với schema legacy không thể đổi tên ngay, có thể quote identifier trong mapping Hibernate. Hibernate hỗ trợ dấu backtick trong tên mapping và chuyển nó thành ký tự quote phù hợp với dialect:

```java
@Entity
@Table(name = "`order`")
public class LegacyOrder {

    @Id
    private Long id;

    @Column(name = "`group`")
    private String groupName;
}
```

Đây là cú pháp quote của Hibernate, không phải quy ước Java hay cú pháp SQL dùng trực tiếp trong mọi database. Hibernate sẽ sinh cách quote theo dialect, chẳng hạn dấu ngoặc kép hoặc ngoặc vuông tùy hệ quản trị. Nếu cần tính di động giữa các JPA provider, đổi tên bảng/cột trong schema thường là lựa chọn bền vững hơn.

Có thể bật `hibernate.globally_quoted_identifiers` để quote toàn bộ identifier:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        globally_quoted_identifiers: true
```

Chỉ dùng cấu hình toàn cục khi đã đánh giá schema và migration. Quoting có thể làm thay đổi cách database phân biệt hoa/thường; ví dụ PostgreSQL xử lý identifier không quote và identifier có quote theo quy tắc khác nhau. Migration scripts, index, constraint và câu SQL native phải khớp chính xác với tên đã quote. Tránh bật toàn cục chỉ để chữa một cột trùng từ khóa.

## 7. JPQL, SQL và tên cột là ba ngữ cảnh khác nhau

JPQL tham chiếu entity name và thuộc tính Java:

```java
select p from PurchaseOrder p where p.orderNumber = :number
```

SQL thực thi trên database tham chiếu bảng và cột vật lý:

```sql
SELECT id, order_number, order_status
FROM purchase_order
WHERE order_number = ?;
```

Vì vậy, không viết JPQL bằng tên bảng/cột vật lý nếu chưa chủ đích dùng native SQL. Ngược lại, khi viết native SQL, phải dùng đúng tên vật lý trong schema và quy tắc quote của database. Nếu JPQL báo không tìm thấy thuộc tính, kiểm tra tên field/property Java; nếu SQL báo không tìm thấy column/table, kiểm tra physical name và migration.

## 8. Đồng bộ mapping với schema và migration

`@Table` và `@Column` chỉ mô tả mapping cho ORM; chúng không tự đổi tên bảng/cột đang tồn tại khi ứng dụng chạy với migration. Với Flyway hoặc Liquibase, DDL phải tạo đúng physical name mà Hibernate sử dụng. Ví dụ schema tương ứng với entity ở trên:

```sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    order_status VARCHAR(30) NOT NULL
);
```

Khi đổi naming strategy hoặc đổi tên mapping, cần tạo migration đổi tên bảng/cột và cập nhật các foreign key, index, view, native query hoặc báo cáo phụ thuộc vào identifier đó. Không dùng `ddl-auto=update` như công cụ migration cho production; hãy quản lý thay đổi schema bằng migration có kiểm soát và dùng chế độ kiểm tra phù hợp, chẳng hạn `validate`, khi kiến trúc dự án yêu cầu.

## 9. Lỗi thường gặp và cách điều tra

**Lỗi cú pháp gần từ khóa như `order` hoặc `group`.** Xem SQL Hibernate thực sự sinh ra, xác định identifier xung đột, rồi ưu tiên đổi tên vật lý. Nếu schema legacy bắt buộc giữ tên, quote đúng identifier trong mapping và kiểm tra SQL do dialect sinh ra.

**Không tìm thấy bảng hoặc cột sau khi thêm `@Table`/`@Column`.** So sánh tên trong mapping, tên sau physical naming strategy và DDL migration. Kiểm tra xem tên tường minh có bị chuyển camelCase thành snake_case hay không.

**Chạy được trên máy dev nhưng lỗi ở môi trường khác.** Kiểm tra dialect, phiên bản database, quy tắc chữ hoa/chữ thường, schema mặc định và naming strategy có giống nhau không. Tránh tên phụ thuộc vào từ khóa riêng của một database.

**JPQL báo không tìm thấy entity hoặc thuộc tính.** Dùng entity name trong `FROM` và tên thuộc tính Java trong biểu thức JPQL. `@Entity(name = "...")` điều khiển entity name; `@Table` không điều khiển tên JPQL.

**Native SQL không chạy sau khi đổi tên mapping.** Native SQL phải được cập nhật theo physical schema. Naming strategy không tự sửa chuỗi SQL native do ứng dụng viết.

**Quote rồi vẫn lỗi không tìm thấy identifier.** Kiểm tra chính xác chữ hoa/thường và cách database lưu identifier đã quote; đồng thời xác nhận cú pháp quote là của Hibernate mapping, không phải dấu quote được hard-code sai theo dialect.

## 10. Checklist khi thiết kế tên mới

- Đặt entity name rõ ràng nếu cần ổn định tên dùng trong JPQL.
- Dùng `@Table` và `@Column` tường minh cho các bảng/cột quan trọng hoặc schema có quy ước cố định.
- Dùng snake_case cho tên vật lý và camelCase cho thuộc tính Java.
- Tránh từ khóa SQL và tên hàm/tên kiểu dữ liệu phổ biến; ưu tiên tên nghiệp vụ có nghĩa.
- Xác nhận implicit và physical naming strategy của Spring Boot/Hibernate.
- Đảm bảo DDL migration, foreign key, index, view và native SQL dùng cùng physical name.
- Chỉ quote identifier khi phải tương thích schema legacy; cân nhắc tác động chữ hoa/thường và tính di động.
- Kiểm tra SQL sinh ra trên đúng dialect và chạy kiểm tra schema trên môi trường tích hợp.

Quy ước tốt giúp mapping Entity dễ đọc, SQL sinh ra dễ dự đoán và schema ít phụ thuộc vào đặc điểm riêng của từng database. Khi có quyền thay đổi schema, tên vật lý an toàn và có ý nghĩa nghiệp vụ thường là giải pháp đơn giản, ổn định nhất.