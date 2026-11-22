# Chiến lược SINGLE_TABLE và cột phân biệt

## 1. SINGLE_TABLE giải quyết vấn đề gì?

JPA hỗ trợ ánh xạ một cây kế thừa Entity xuống cơ sở dữ liệu bằng nhiều chiến lược. Với `InheritanceType.SINGLE_TABLE`, toàn bộ lớp cha và các lớp con trong cùng một hierarchy được lưu trong **một bảng duy nhất**. Một cột phân biệt (discriminator column) cho biết mỗi hàng thuộc kiểu Entity cụ thể nào.

Ví dụ nghiệp vụ thanh toán có lớp cha `Payment`, hai lớp con `CardPayment` và `BankTransfer`. Tất cả bản ghi nằm trong bảng `payment`; cột `payment_type` lưu `CARD` hoặc `BANK_TRANSFER` để Hibernate khởi tạo đúng subtype khi đọc dữ liệu.

Ưu điểm lớn của SINGLE_TABLE là truy vấn đa hình và đọc dữ liệu cả hierarchy thường không cần join nhiều bảng. Đổi lại, các cột chỉ dùng cho một subtype phải cho phép NULL ở những hàng thuộc subtype khác. Bảng có thể rộng và cần quy tắc kiểm tra dữ liệu theo discriminator.

## 2. Khai báo hierarchy bằng JPA

`@Inheritance` được đặt trên entity root để chỉ định chiến lược cho toàn bộ hierarchy. Với SINGLE_TABLE, entity root và các entity con cùng dùng một bảng. `@DiscriminatorColumn` khai báo cột phân biệt trên root; `@DiscriminatorValue` gán giá trị cho từng entity trong hierarchy.

Ví dụ:

```java
import jakarta.persistence.Column;
import jakarta.persistence.DiscriminatorColumn;
import jakarta.persistence.DiscriminatorType;
import jakarta.persistence.DiscriminatorValue;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Inheritance;
import jakarta.persistence.InheritanceType;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "payment")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "payment_type",
    discriminatorType = DiscriminatorType.STRING,
    length = 30
)
public abstract class Payment {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "amount", nullable = false, precision = 19, scale = 2)
    private BigDecimal amount;

    protected Payment() {
    }

    protected Payment(BigDecimal amount) {
        this.amount = amount;
    }
}
```

Entity con khai báo các thuộc tính đặc thù:

```java
@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {
    @Column(name = "card_last_four", length = 4)
    private String cardLastFour;

    protected CardPayment() {
    }
}
```

```java
@Entity
@DiscriminatorValue("BANK_TRANSFER")
public class BankTransfer extends Payment {
    @Column(name = "bank_reference", length = 80)
    private String bankReference;

    protected BankTransfer() {
    }
}
```

Đây là các phần khai báo cốt lõi; ứng dụng thực tế cần bổ sung constructor, getter, setter hoặc factory/domain method phù hợp. Constructor không tham số phải có khả năng truy cập tối thiểu là `protected` theo yêu cầu của JPA. Các entity con kế thừa thuộc tính `id` và `amount` từ root.

Trong hierarchy này, `Payment` là abstract nên không tạo instance trực tiếp. `CardPayment` và `BankTransfer` là các kiểu cụ thể. Chỉ root khai báo `@Inheritance` và `@DiscriminatorColumn`; mỗi subtype khai báo giá trị phân biệt riêng.

## 3. Discriminator column và discriminator value

`@DiscriminatorColumn` xác định cột mà provider dùng để phân biệt subtype:

- `name`: tên cột vật lý, ví dụ `payment_type`.
- `discriminatorType`: kiểu dữ liệu discriminator. `STRING` phù hợp với giá trị dễ đọc như `CARD`; JPA cũng hỗ trợ `CHAR` và `INTEGER`.
- `length`: độ dài cột khi kiểu là chuỗi.

`@DiscriminatorValue` xác định giá trị được lưu cho một entity cụ thể. Trong ví dụ, hàng của `CardPayment` mang `payment_type = 'CARD'`, còn `BankTransfer` mang `payment_type = 'BANK_TRANSFER'`.

Nếu không khai báo `@DiscriminatorColumn`, JPA sử dụng cột mặc định `DTYPE` với kiểu chuỗi. Nếu không khai báo `@DiscriminatorValue`, provider áp dụng giá trị mặc định theo tên entity theo quy định JPA. Với schema được quản lý bằng migration hoặc cần tương thích lâu dài, nên khai báo rõ tên cột và giá trị discriminator để tránh phụ thuộc vào tên class.

Giá trị discriminator là một phần của hợp đồng dữ liệu giữa ứng dụng và schema. Không tùy tiện đổi `CARD` thành `CREDIT_CARD` nếu database đã có dữ liệu cũ; cần migration cập nhật các hàng hiện có và triển khai tương thích với phiên bản ứng dụng.

## 4. Schema vật lý của SINGLE_TABLE

Với ví dụ trên, bảng có thể được mô tả như sau:

```sql
CREATE TABLE payment (
    id BIGINT PRIMARY KEY,
    payment_type VARCHAR(30) NOT NULL,
    amount DECIMAL(19, 2) NOT NULL,
    card_last_four VARCHAR(4),
    bank_reference VARCHAR(80)
);
```

DDL là minh họa; kiểu sinh ID và cú pháp cụ thể phụ thuộc database. Tất cả cột của root và mọi subtype cùng nằm trong `payment`. Vì một hàng chỉ thuộc một subtype, các cột không áp dụng cho subtype đó thường là NULL:

| payment_type | amount | card_last_four | bank_reference |
| --- | ---: | --- | --- |
| `CARD` | 125.00 | `4821` | NULL |
| `BANK_TRANSFER` | 300.00 | NULL | `TRX-2026-001` |

Do đó không đặt `NOT NULL` vô điều kiện cho `card_last_four` hoặc `bank_reference` nếu subtype còn lại không dùng cột đó. Nếu cột bắt buộc trong một subtype, kiểm tra ở tầng domain/Bean Validation và cân nhắc CHECK constraint theo discriminator ở database.

Ví dụ CHECK constraint minh họa:

```sql
ALTER TABLE payment
ADD CONSTRAINT ck_payment_subtype_fields
CHECK (
    (payment_type = 'CARD' AND card_last_four IS NOT NULL AND bank_reference IS NULL)
    OR
    (payment_type = 'BANK_TRANSFER' AND bank_reference IS NOT NULL AND card_last_four IS NULL)
);
```

CHECK constraint trên thể hiện quy tắc cụ thể của ví dụ và cần điều chỉnh theo yêu cầu thật, khả năng của database và cách xử lý giá trị NULL. Nếu subtype có nhiều trường tùy chọn, không nên ép mọi trường đều NOT NULL chỉ vì chúng xuất hiện trong một class con.

## 5. Truy vấn đa hình

JPA truy vấn theo entity root có tính đa hình: truy vấn `Payment` có thể trả về cả `CardPayment` và `BankTransfer`. Hibernate đọc discriminator để khởi tạo đúng lớp Java.

```java
List<Payment> payments = entityManager
    .createQuery("select p from Payment p", Payment.class)
    .getResultList();
```

Kết quả có thể chứa instance của các lớp con. Có thể kiểm tra kiểu trong Java bằng `instanceof` hoặc dùng `TYPE` trong JPQL khi cần lọc subtype:

```java
List<Payment> cardPayments = entityManager
    .createQuery(
        "select p from Payment p where type(p) = CardPayment",
        Payment.class
    )
    .getResultList();
```

JPQL dùng entity name và thuộc tính Java, không dùng tên bảng/cột vật lý. Khi cần truy vấn trường chỉ có ở subtype, có thể dùng `TREAT` trong JPQL hoặc truy vấn repository chuyên biệt theo subtype, tùy use case và khả năng provider.

Vì tất cả subtype cùng bảng, truy vấn root không cần join các bảng con để ghép dữ liệu như JOINED. Hibernate có thể dùng discriminator trong điều kiện truy vấn để giới hạn subtype khi truy vấn entity con.

## 6. INSERT và UPDATE hoạt động ra sao?

Khi persist `CardPayment`, Hibernate ghi một hàng vào `payment`, gồm các thuộc tính kế thừa, các cột riêng của CardPayment và discriminator `CARD`. Các cột chỉ dành cho BankTransfer để NULL. Khi persist `BankTransfer`, discriminator là `BANK_TRANSFER` và các cột dành riêng cho thẻ để NULL.

Về mặt logic, dữ liệu có dạng:

```sql
INSERT INTO payment
    (payment_type, amount, card_last_four, bank_reference)
VALUES
    ('CARD', 125.00, '4821', NULL);
```

Đây là SQL minh họa để giải thích cấu trúc dữ liệu; SQL thực tế có thể khác về thứ tự cột, placeholder, generated key và cách bind tham số theo dialect/provider.

Khi cập nhật một subtype, Hibernate cập nhật hàng trong cùng bảng. Không có bảng con riêng để join. Vì vậy các thuộc tính subtype cùng tồn tại trên một row, nhưng chỉ những cột phù hợp với discriminator mới có ý nghĩa nghiệp vụ.

## 7. SINGLE_TABLE so với JOINED và TABLE_PER_CLASS

| Tiêu chí | SINGLE_TABLE | JOINED | TABLE_PER_CLASS |
| --- | --- | --- | --- |
| Cấu trúc | Một bảng cho cả hierarchy | Bảng root và bảng riêng cho từng subtype | Mỗi concrete class có bảng riêng, thường lặp cột kế thừa |
| Đọc đa hình | Thường không cần join subtype | Thường cần join bảng subtype | Có thể cần UNION |
| Cột riêng của subtype | Nhiều cột nullable trong bảng chung | Nằm trong bảng subtype | Nằm trong bảng subtype |
| Ràng buộc NOT NULL theo subtype | Khó hơn trong một bảng chung | Tự nhiên hơn ở bảng subtype | Có thể áp dụng ở từng bảng |
| Ghi dữ liệu | Thường một bảng | Có thể phải ghi nhiều bảng trong hierarchy | Ghi bảng concrete subtype |
| Phù hợp | Hierarchy vừa phải, truy vấn đa hình nhiều | Cần schema chuẩn hóa và ràng buộc subtype rõ | Các subtype ít cần truy vấn đa hình hoặc có schema độc lập |

SINGLE_TABLE thường có hiệu năng đọc đa hình tốt vì không phải join nhiều bảng. Tuy nhiên, khi hierarchy có rất nhiều subtype với nhiều cột riêng, bảng có thể rất rộng, nhiều giá trị NULL và schema khó quản lý. Chọn chiến lược theo kiểu truy vấn, số lượng subtype, quy tắc dữ liệu và chi phí migration, không chỉ dựa trên số lượng bảng.

## 8. Khi nào nên dùng SINGLE_TABLE?

Phù hợp khi:

- Các subtype có nhiều thuộc tính chung.
- Ứng dụng thường truy vấn danh sách toàn bộ root type.
- Số lượng subtype và trường đặc thù còn kiểm soát được.
- Có thể chấp nhận các cột subtype khác để NULL.
- Cần đơn giản hóa truy vấn đọc đa hình.

Cần cân nhắc chiến lược khác khi mỗi subtype có nhiều trường riêng, ràng buộc NOT NULL khác nhau rất quan trọng, hoặc bảng chung trở nên quá rộng. JOINED có thể phù hợp khi cần tách dữ liệu theo subtype và bảo đảm ràng buộc schema chặt chẽ hơn, đổi lại là join.

## 9. Những lưu ý thiết kế

**Không dùng discriminator làm dữ liệu nghiệp vụ tùy tiện.** Discriminator xác định kiểu Java của hàng. Không nên thay đổi nó như một trạng thái nghiệp vụ thông thường nếu thay đổi đó khiến hàng cần trở thành một subtype khác. Việc đổi subtype có thể cần tạo instance mới, chuyển dữ liệu và xử lý quan hệ liên quan.

**Giá trị discriminator cần ổn định.** Dùng chuỗi tường minh thay vì phụ thuộc tên class mặc định nếu schema tồn tại lâu dài. Khi đổi giá trị, phải migration dữ liệu và bảo đảm các phiên bản ứng dụng tương thích trong giai đoạn triển khai.

**Không khai báo `@DiscriminatorColumn` lặp lại ở class con.** Cột phân biệt thuộc cấu hình hierarchy tại root entity. Class con chỉ cần `@DiscriminatorValue`.

**Không tạo Entity riêng cho từng subtype chỉ để thêm một vài thuộc tính nếu không có lợi ích mô hình.** Cân nhắc composition/association khi các loại không thực sự là quan hệ kế thừa `is-a`.

**Kiểm soát trường subtype.** Dữ liệu không thuộc subtype hiện tại thường phải NULL; có thể thêm CHECK constraint theo discriminator khi database hỗ trợ và quy tắc đủ rõ.

## 10. Migration và tương thích dữ liệu

Với Flyway hoặc Liquibase, migration phải tạo bảng chung, discriminator column, cột dùng chung và toàn bộ cột subtype. Nếu chuyển từ chiến lược khác sang SINGLE_TABLE, cần kế hoạch hợp nhất dữ liệu từ các bảng cũ, gán discriminator cho từng hàng, xử lý ID trùng, cập nhật khóa ngoại, index, view và native query.

Khi thêm subtype mới, cần thêm cột tương ứng và giá trị discriminator mới; các hàng cũ phải tiếp tục đọc được. Khi đổi tên hoặc giá trị discriminator, migration phải cập nhật dữ liệu hiện có. Tránh triển khai code mới trước khi schema có thể lưu giá trị và cột mới.

Không dựa vào `ddl-auto=update` để chuyển đổi dữ liệu production giữa các chiến lược kế thừa. Dùng migration có phiên bản và kiểm tra bằng dữ liệu đại diện.

## 11. Lỗi thường gặp và cách điều tra

**Hibernate không nhận ra subtype.** Kiểm tra class con có `@Entity`, discriminator value có đúng với dữ liệu trong cột discriminator và package scanning có bao gồm class đó không.

**Lỗi không tìm thấy cột.** So sánh tên trong `@Column`, physical naming strategy và DDL. SINGLE_TABLE đặt cột subtype trên bảng root, không tạo bảng riêng cho mỗi class con.

**Lỗi NOT NULL khi insert một subtype.** Xem cột bắt buộc có phải chỉ thuộc subtype khác không. Cột subtype-specific trong bảng chung thường phải nullable hoặc có CHECK constraint có điều kiện.

**Truy vấn root trả nhiều kiểu đối tượng.** Đây là hành vi đa hình bình thường. Nếu chỉ cần một subtype, lọc bằng repository của subtype hoặc JPQL `TYPE`.

**Dữ liệu có discriminator không hợp lệ.** Kiểm tra migration, dữ liệu import thủ công và các phiên bản ứng dụng đã ghi giá trị đó. Không tự đổi discriminator tùy tiện vì nó quyết định lớp được hydrate.

**Bảng chung quá rộng hoặc nhiều cột NULL.** Đánh giá lại số subtype, số trường riêng và kiểu truy vấn. Có thể chuyển sang JOINED hoặc composition nếu lợi ích schema vượt chi phí join.

## 12. Checklist triển khai

- Đặt `@Inheritance(strategy = InheritanceType.SINGLE_TABLE)` trên root entity.
- Khai báo `@DiscriminatorColumn` rõ ràng và một `@DiscriminatorValue` ổn định cho mỗi subtype.
- Đảm bảo tất cả subtype là `@Entity` trong phạm vi scan.
- Thiết kế DDL với cột dùng chung và cột riêng; không áp dụng NOT NULL vô điều kiện cho cột subtype khác.
- Cập nhật migration, index, constraint và native SQL.
- Kiểm tra truy vấn đa hình ở root và truy vấn riêng từng subtype.
- Kiểm tra dữ liệu discriminator và hành vi insert/update trên database mục tiêu.
- Chọn SINGLE_TABLE vì đặc điểm truy vấn và mô hình dữ liệu, không chỉ vì muốn giảm số bảng.

SINGLE_TABLE lưu cả hierarchy trong một bảng và dùng discriminator để xác định subtype. Cách này giúp truy vấn đa hình đơn giản, nhưng yêu cầu thiết kế cột nullable, giá trị discriminator và migration cẩn thận để schema luôn nhất quán với mô hình Entity.