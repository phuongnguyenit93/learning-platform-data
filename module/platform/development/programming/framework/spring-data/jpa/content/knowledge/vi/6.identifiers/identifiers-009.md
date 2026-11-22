# Thiết kế equals và hashCode cho khóa ghép

Trong JPA, khóa chính ghép (composite primary key) được tạo từ hai hoặc nhiều thuộc tính. Ví dụ, một dòng hàng trong đơn đặt hàng có thể được xác định bởi cặp mã đơn hàng và số thứ tự dòng. Khi biểu diễn khóa ghép bằng một lớp Java, lớp đó cần triển khai equals() và hashCode() đúng cách để hai đối tượng khóa có cùng giá trị được xem là cùng một khóa.

Việc triển khai này ảnh hưởng đến cách Java so sánh đối tượng, cách HashMap/HashSet tìm phần tử và cách JPA nhận diện khóa. Quy tắc cốt lõi là: **equals() phải so sánh toàn bộ thành phần của khóa; hashCode() phải được tính từ chính các thành phần đó; các thành phần khóa phải ổn định trong suốt thời gian đối tượng được dùng làm khóa.**

## 1. Khóa ghép là gì?

Khóa chính ghép là khóa chính gồm nhiều cột. Một hàng trong bảng chỉ được xác định duy nhất khi kết hợp các giá trị của tất cả thành phần khóa.

Ví dụ bảng order_lines:

| order_id | line_number | product_name |
|---:|---:|---|
| 100 | 1 | Keyboard |
| 100 | 2 | Mouse |
| 101 | 1 | Monitor |

Trong ví dụ này, order_id riêng lẻ không duy nhất vì một đơn hàng có nhiều dòng. line_number riêng lẻ cũng không duy nhất vì nhiều đơn hàng đều có dòng số 1. Cặp (order_id, line_number) mới xác định duy nhất một dòng.

Mô hình Java tương ứng có thể là:

~~~java
public class OrderLineKey {
    private Long orderId;
    private Integer lineNumber;
}
~~~

Hai đối tượng sau phải được xem là bằng nhau nếu cả orderId và lineNumber đều có cùng giá trị:

~~~java
OrderLineKey first = new OrderLineKey(100L, 2);
OrderLineKey second = new OrderLineKey(100L, 2);
~~~

Nếu không override equals(), Java mặc định so sánh identity của đối tượng. Vì first và second là hai đối tượng khác nhau trong bộ nhớ, biểu thức first.equals(second) sẽ trả về false dù các trường có giá trị giống nhau. Điều đó không phù hợp với ý nghĩa của khóa ghép.

## 2. Hợp đồng equals() và hashCode() của Java

Mọi lớp dùng làm khóa trong HashMap hoặc phần tử trong HashSet cần tuân thủ hợp đồng của Object.equals() và Object.hashCode().

### Hợp đồng equals()

Một phương thức equals() đúng phải có các tính chất:

1. **Phản xạ (reflexive):** một đối tượng luôn bằng chính nó.
2. **Đối xứng (symmetric):** nếu a bằng b thì b cũng phải bằng a.
3. **Bắc cầu (transitive):** nếu a bằng b và b bằng c thì a bằng c.
4. **Nhất quán (consistent):** nếu các dữ liệu dùng để so sánh không thay đổi, kết quả so sánh phải ổn định qua các lần gọi.
5. **Không bằng null:** mọi đối tượng khác null đều phải trả về false khi so sánh với null.

Với khóa ghép, điều kiện bằng nhau phải dựa trên tất cả thành phần khóa. Nếu chỉ so sánh orderId mà bỏ qua lineNumber, hai dòng hàng khác nhau trong cùng đơn sẽ bị coi là cùng một khóa.

### Hợp đồng hashCode()

hashCode() trả về một số nguyên được dùng để phân nhóm đối tượng trong các cấu trúc băm như HashMap và HashSet.

Quy tắc bắt buộc:

- Nếu a.equals(b) là true thì a.hashCode() và b.hashCode() phải bằng nhau.
- Nếu hashCode bằng nhau thì hai đối tượng chưa chắc bằng nhau; va chạm hash là điều có thể xảy ra.
- Khi các trường tham gia equals() không thay đổi, hashCode() cũng phải ổn định.
- hashCode() nên sử dụng cùng tập thành phần với equals().

Không bắt buộc hai đối tượng khác nhau phải có hashCode khác nhau. Mục tiêu là phân bố tốt và bảo toàn hợp đồng, không phải tạo một mã duy nhất cho mọi đối tượng.

## 3. Triển khai bằng Objects.equals() và Objects.hash()

Với khóa ghép gồm orderId và lineNumber, có thể triển khai như sau:

~~~java
import java.io.Serializable;
import java.util.Objects;

public class OrderLineKey implements Serializable {

    private Long orderId;
    private Integer lineNumber;

    public OrderLineKey() {
    }

    public OrderLineKey(Long orderId, Integer lineNumber) {
        this.orderId = orderId;
        this.lineNumber = lineNumber;
    }

    public Long getOrderId() {
        return orderId;
    }

    public Integer getLineNumber() {
        return lineNumber;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }

        if (!(other instanceof OrderLineKey that)) {
            return false;
        }

        return Objects.equals(orderId, that.orderId)
                && Objects.equals(lineNumber, that.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNumber);
    }
}
~~~

Giải thích:

- this == other xử lý nhanh trường hợp hai tham chiếu trỏ đến cùng một đối tượng.
- instanceof kiểm tra đối tượng còn lại có phải kiểu OrderLineKey hay không.
- Objects.equals(a, b) xử lý cả trường hợp null mà không gây NullPointerException.
- Toán tử && yêu cầu mọi thành phần khóa đều bằng nhau.
- Objects.hash(...) tính hash từ đúng hai thành phần đã dùng trong equals().

Với Java 17, cú pháp pattern matching trong instanceof cho phép khai báo biến that ngay trong điều kiện kiểm tra. Nếu dự án dùng Java phiên bản cũ hơn, viết kiểm tra và ép kiểu riêng:

~~~java
if (!(other instanceof OrderLineKey)) {
    return false;
}
OrderLineKey that = (OrderLineKey) other;
~~~

### Vì sao phải so sánh tất cả trường khóa?

Giả sử có ba khóa:

~~~java
OrderLineKey a = new OrderLineKey(100L, 1);
OrderLineKey b = new OrderLineKey(100L, 2);
OrderLineKey c = new OrderLineKey(100L, 1);
~~~

Kết quả đúng phải là:

| Biểu thức | Kết quả |
|---|---|
| a.equals(b) | false |
| a.equals(c) | true |
| a.hashCode() == c.hashCode() | true |
| a.hashCode() == b.hashCode() | Không bắt buộc true hoặc false |

Nếu equals() chỉ kiểm tra orderId, a và b sẽ bị xem là bằng nhau. Đây là lỗi nghiêm trọng vì hai dòng khác nhau có thể bị nhầm là cùng một bản ghi.

## 4. Khai báo khóa ghép với @EmbeddedId

Trong JPA, @EmbeddedId cho phép đặt toàn bộ thành phần khóa vào một lớp riêng được đánh dấu @Embeddable.

Lớp khóa:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class OrderLineKey implements Serializable {

    @Column(name = "order_id")
    private Long orderId;

    @Column(name = "line_number")
    private Integer lineNumber;

    public OrderLineKey() {
    }

    public OrderLineKey(Long orderId, Integer lineNumber) {
        this.orderId = Objects.requireNonNull(orderId);
        this.lineNumber = Objects.requireNonNull(lineNumber);
    }

    public Long getOrderId() {
        return orderId;
    }

    public Integer getLineNumber() {
        return lineNumber;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof OrderLineKey that)) {
            return false;
        }
        return Objects.equals(orderId, that.orderId)
                && Objects.equals(lineNumber, that.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNumber);
    }
}
~~~

Entity sử dụng khóa:

~~~java
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @EmbeddedId
    private OrderLineKey id;

    private String productName;

    protected OrderLine() {
    }

    public OrderLine(OrderLineKey id, String productName) {
        this.id = id;
        this.productName = productName;
    }

    public OrderLineKey getId() {
        return id;
    }

    public String getProductName() {
        return productName;
    }
}
~~~

Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderLineRepository
        extends JpaRepository<OrderLine, OrderLineKey> {
}
~~~

Khi gọi findById(), truyền một OrderLineKey:

~~~java
OrderLineKey key = new OrderLineKey(100L, 2);

Optional<OrderLine> result =
        orderLineRepository.findById(key);
~~~

Ở đây, equals() và hashCode() thuộc về lớp OrderLineKey. JPA dùng lớp này để biểu diễn giá trị khóa chính. Entity OrderLine và lớp khóa OrderLineKey có vai trò khác nhau; không nên nhầm equals() của Entity với equals() của lớp khóa.

## 5. Khai báo khóa ghép với @IdClass

@IdClass là cách ánh xạ khác. Các thuộc tính khóa nằm trực tiếp trong Entity, còn lớp ID mô tả cấu trúc khóa.

Lớp ID:

~~~java
import java.io.Serializable;
import java.util.Objects;

public class OrderLineId implements Serializable {

    private Long orderId;
    private Integer lineNumber;

    public OrderLineId() {
    }

    public OrderLineId(Long orderId, Integer lineNumber) {
        this.orderId = orderId;
        this.lineNumber = lineNumber;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof OrderLineId that)) {
            return false;
        }
        return Objects.equals(orderId, that.orderId)
                && Objects.equals(lineNumber, that.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNumber);
    }
}
~~~

Entity:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_lines")
@IdClass(OrderLineId.class)
public class OrderLine {

    @Id
    private Long orderId;

    @Id
    private Integer lineNumber;

    private String productName;

    protected OrderLine() {
    }
}
~~~

Repository:

~~~java
public interface OrderLineRepository
        extends JpaRepository<OrderLine, OrderLineId> {
}
~~~

Với @IdClass:

- Tên thuộc tính trong lớp ID phải tương ứng với tên thuộc tính khóa trong Entity.
- Kiểu của từng thuộc tính trong lớp ID phải tương ứng với kiểu Java của thuộc tính khóa trong Entity.
- equals() và hashCode() của lớp ID phải xét toàn bộ thành phần khóa.
- Lớp ID cần đáp ứng các yêu cầu của JPA về constructor và khả năng serialize.

Cả @EmbeddedId và @IdClass đều cần lớp khóa có equals() và hashCode(). Khác biệt chính là cách đặt các thành phần khóa trong mô hình Entity.

## 6. So sánh @EmbeddedId và @IdClass

| Tiêu chí | @EmbeddedId | @IdClass |
|---|---|---|
| Thành phần khóa | Gom trong một thuộc tính có kiểu lớp khóa | Khai báo nhiều thuộc tính @Id trên Entity |
| Lớp khóa | Được đánh dấu @Embeddable | Được tham chiếu qua @IdClass |
| Cách truy cập khóa | entity.getId().getOrderId() | entity.getOrderId() |
| ID generic của Repository | Lớp @Embeddable | Lớp ID được khai báo trong @IdClass |
| equals/hashCode | Trong lớp @Embeddable | Trong lớp ID |
| Mục đích | Gom khóa thành một value object | Giữ các trường khóa trực tiếp trên Entity |

Không có lựa chọn bắt buộc cho mọi dự án. @EmbeddedId thường giúp biểu diễn khóa ghép thành một giá trị rõ ràng và gom logic khóa vào một lớp. @IdClass phù hợp khi muốn các thuộc tính khóa xuất hiện trực tiếp trên Entity. Hãy chọn một cách cho mỗi mapping và tuân thủ nhất quán.

## 7. Tại sao khóa ghép nên ổn định và ít thay đổi?

HashMap và HashSet sử dụng hashCode() để xác định vị trí của phần tử. Nếu một đối tượng đã được đưa vào HashSet rồi một trường dùng để tính hashCode() bị thay đổi, đối tượng có thể nằm ở bucket cũ trong khi việc tìm kiếm tính ra bucket mới.

Ví dụ minh họa lỗi với một lớp khóa có setter:

~~~java
OrderLineKey key = new OrderLineKey(100L, 1);

Set<OrderLineKey> keys = new HashSet<>();
keys.add(key);

// Giả sử có setter và thay đổi thành phần khóa:
key.setLineNumber(2);

// Có thể trả về false vì hashCode đã thay đổi:
boolean found = keys.contains(key);
~~~

Khóa chính trong database cũng được kỳ vọng xác định một bản ghi ổn định. Thay đổi thành phần khóa sau khi Entity đã được lưu có thể khiến việc đồng bộ persistence context, cập nhật quan hệ và quản lý Entity trở nên phức tạp hoặc không được provider hỗ trợ.

Các nguyên tắc thiết kế:

- Tạo khóa với đầy đủ giá trị ngay từ đầu.
- Tránh cung cấp setter công khai cho thành phần khóa nếu không cần.
- Không sửa thành phần khóa sau khi Entity đã được persist.
- Không dùng trường mô tả như productName, status hoặc createdAt trong equals/hashCode của khóa nếu chúng không thuộc khóa chính.
- Nếu nghiệp vụ cần thay đổi mã, cân nhắc dùng khóa kỹ thuật ổn định và giữ mã nghiệp vụ thành thuộc tính riêng có unique constraint.

Trong JPA, provider có thể cần constructor không tham số và truy cập field theo mapping. Vì vậy, không nên tùy tiện biến mọi field thành final nếu điều đó làm mapping không tương thích. Có thể giữ field private, chỉ cung cấp constructor tạo giá trị và getter, đồng thời không cung cấp setter để hạn chế thay đổi từ ứng dụng.

## 8. So sánh khóa theo đúng ngữ nghĩa của database

Một lớp khóa Java phải so sánh giá trị theo cách tương thích với cách database xác định khóa duy nhất. Đây là điểm dễ bị bỏ qua khi các kiểu dữ liệu có quy tắc so sánh đặc biệt.

### Chuỗi và collation

String.equals() phân biệt chữ hoa và chữ thường:

~~~java
"ABC".equals("abc"); // false
~~~

Trong khi đó, một cột database có collation không phân biệt hoa thường có thể xem hai giá trị này tương đương trong một số phép so sánh hoặc ràng buộc unique. Nếu database có ngữ nghĩa so sánh khác Java, cần chuẩn hóa giá trị khóa trước khi lưu và bảo đảm quy tắc chuẩn hóa thống nhất ở mọi nơi. Không tự ý lowercase nếu mã nghiệp vụ có phân biệt hoa thường.

### BigDecimal

BigDecimal.equals() xem cả giá trị và scale:

~~~java
new BigDecimal("1.0").equals(new BigDecimal("1.00")); // false
new BigDecimal("1.0").compareTo(new BigDecimal("1.00")) == 0; // true
~~~

Một số kiểu số trong database có thể so sánh hai giá trị số này là tương đương. Vì vậy, dùng BigDecimal làm thành phần khóa có thể gây lệch giữa Java và database nếu không chuẩn hóa scale. Tốt nhất tránh dùng số thập phân làm khóa định danh; nếu bắt buộc, phải xác định và áp dụng quy tắc chuẩn hóa thống nhất.

### Ngày giờ và độ chính xác

Database có thể lưu timestamp với độ chính xác thấp hơn giá trị Java ban đầu. Nếu khóa chứa timestamp, giá trị sau khi round-trip có thể khác với giá trị trước khi lưu. Hãy chuẩn hóa độ chính xác theo kiểu cột và database, hoặc chọn một khóa định danh khác ổn định hơn.

### Mảng byte

Arrays trong Java có hành vi equals mặc định theo identity. Objects.equals(byteArrayA, byteArrayB) cũng không so sánh nội dung của hai mảng byte. Nếu một thành phần khóa thực sự là mảng byte, cần dùng Arrays.equals() và Arrays.hashCode():

~~~java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (!(other instanceof BinaryKey that)) return false;
    return Arrays.equals(value, that.value);
}

@Override
public int hashCode() {
    return Arrays.hashCode(value);
}
~~~

Tuy nhiên, dùng dữ liệu nhị phân lớn làm khóa chính thường không phải thiết kế tốt. Khóa nên nhỏ, ổn định và dễ so sánh.

## 9. Không nhầm equals/hashCode của lớp khóa với Entity

Một lớp khóa ghép là value object: hai đối tượng có cùng các thành phần khóa đại diện cho cùng một giá trị khóa. Vì vậy, equals/hashCode của lớp khóa nên so sánh mọi thành phần khóa.

Entity có vòng đời phức tạp hơn:

- Entity mới có thể chưa có ID nếu ID được sinh tự động.
- Entity được persist sẽ nhận ID sau khi lưu.
- Hibernate có thể dùng proxy để đại diện cho Entity được tải trễ.
- Entity có quan hệ hai chiều, collection và trường mutable.
- Hai Entity có cùng dữ liệu nghiệp vụ nhưng chưa chắc là cùng một persistent identity.

Không nên sao chép nguyên cách triển khai equals/hashCode của lớp khóa sang Entity. Đặc biệt, không đưa mọi quan hệ, collection hoặc LOB vào equals/hashCode của Entity vì có thể tạo vòng lặp, tải dữ liệu ngoài ý muốn hoặc làm hash thay đổi.

Nếu dự án cần định nghĩa equality cho Entity, hãy thiết kế riêng theo quy tắc identity và proxy của JPA provider đang dùng. Nội dung của bài này tập trung vào lớp khóa ghép, nơi các thành phần khóa đã được xác định rõ.

## 10. Lombok có thể tạo equals/hashCode không?

Lombok hỗ trợ tạo equals/hashCode, nhưng cần cấu hình chính xác. Ví dụ:

~~~java
import jakarta.persistence.Embeddable;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Embeddable
@Getter
@NoArgsConstructor
@EqualsAndHashCode(onlyExplicitlyIncluded = true)
public class OrderLineKey {

    @EqualsAndHashCode.Include
    private Long orderId;

    @EqualsAndHashCode.Include
    private Integer lineNumber;
}
~~~

Cách này chỉ đưa các trường được đánh dấu Include vào equals/hashCode. Cần bảo đảm tất cả thành phần khóa đều được đánh dấu và không có trường ngoài khóa bị đưa vào.

Cẩn thận với @Data: annotation này tạo equals/hashCode dựa trên các trường theo mặc định. Nếu lớp khóa có thêm thuộc tính không thuộc khóa, hoặc Entity có quan hệ, cách sinh tự động có thể tạo equality không đúng mục tiêu. Với khóa ghép quan trọng, viết tường minh hoặc cấu hình Lombok rõ ràng thường dễ review hơn.

## 11. Kiểm thử equals/hashCode

Có thể kiểm tra hợp đồng bằng JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;

class OrderLineKeyTest {

    @Test
    void keysWithSameComponentsAreEqual() {
        OrderLineKey first = new OrderLineKey(100L, 2);
        OrderLineKey second = new OrderLineKey(100L, 2);

        assertEquals(first, second);
        assertEquals(first.hashCode(), second.hashCode());
    }

    @Test
    void differentComponentMakesKeysDifferent() {
        OrderLineKey first = new OrderLineKey(100L, 1);
        OrderLineKey second = new OrderLineKey(100L, 2);

        assertNotEquals(first, second);
    }

    @Test
    void equalKeyCanBeFoundInHashSet() {
        OrderLineKey stored = new OrderLineKey(100L, 2);
        OrderLineKey lookup = new OrderLineKey(100L, 2);

        Set<OrderLineKey> keys = new HashSet<>();
        keys.add(stored);

        assertTrue(keys.contains(lookup));
        assertEquals(1, keys.size());
    }

    @Test
    void keyIsNotEqualToNullOrAnotherType() {
        OrderLineKey key = new OrderLineKey(100L, 2);

        assertNotEquals(null, key);
        assertNotEquals("100-2", key);
    }
}
~~~

Test này kiểm tra các trường hợp chính:

- Hai instance độc lập nhưng có cùng thành phần khóa phải bằng nhau.
- Hai khóa khác nhau ở một thành phần phải không bằng nhau.
- HashSet phải tìm được một instance tương đương với instance đã thêm.
- Khóa không được bằng null hoặc đối tượng khác kiểu.

Có thể bổ sung kiểm tra đối xứng, bắc cầu và tính nhất quán:

~~~java
OrderLineKey a = new OrderLineKey(100L, 2);
OrderLineKey b = new OrderLineKey(100L, 2);
OrderLineKey c = new OrderLineKey(100L, 2);

assertTrue(a.equals(b));
assertTrue(b.equals(a));
assertTrue(b.equals(c));
assertTrue(a.equals(c));
assertTrue(a.equals(a));
~~~

Ngoài unit test, nên có integration test lưu Entity dùng khóa ghép vào database rồi tìm lại bằng một instance khóa mới có cùng giá trị. Test đó xác nhận mapping JPA, schema và cách provider xử lý khóa ghép cùng hoạt động đúng.

## 12. Quy trình review một lớp khóa ghép

Khi review lớp ID, hãy kiểm tra:

1. Lớp được dùng đúng với @EmbeddedId hoặc @IdClass.
2. Lớp khóa chứa đúng và đủ các thành phần khóa.
3. Tên và kiểu các trường khớp mapping Entity theo yêu cầu của cách khai báo.
4. Có constructor không tham số phù hợp và đáp ứng yêu cầu của JPA.
5. Lớp khóa đáp ứng yêu cầu Serializable của mô hình khóa ghép truyền thống.
6. equals() so sánh mọi thành phần khóa và không so sánh trường ngoài khóa.
7. hashCode() dùng đúng cùng các thành phần đã dùng trong equals().
8. Giá trị khóa không bị thay đổi sau khi được dùng trong HashMap/HashSet hoặc sau khi Entity được persist.
9. Quy tắc so sánh trong Java tương thích với kiểu dữ liệu, collation và độ chính xác của database.
10. Unit test và integration test bao phủ các trường hợp bằng nhau, khác nhau và round-trip với database.

## 13. Kết luận

Khóa ghép là một giá trị định danh gồm nhiều thành phần. equals() phải so sánh toàn bộ thành phần khóa, còn hashCode() phải được tính từ chính các thành phần đó để bảo đảm hợp đồng của Java. Trong JPA, quy tắc này được triển khai ở lớp khóa dùng với @EmbeddedId hoặc @IdClass. Thiết kế khóa ổn định, không chứa trường ngoài khóa, tương thích với cách database so sánh dữ liệu và được kiểm thử bằng HashSet cùng integration test sẽ giúp việc quản lý Entity đáng tin cậy hơn.
