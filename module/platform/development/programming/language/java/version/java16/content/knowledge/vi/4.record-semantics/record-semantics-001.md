# `equals` của record và yêu cầu cùng chính xác kiểu record

**Chuyên đề:** `JAVA_VERSION_JAVA16` · **Chương:** Ngữ nghĩa record · **Nền tảng:** Java 16 trở lên.

Record trở thành tính năng chính thức từ Java 16 và vẫn là cách biểu diễn dữ liệu gọn, rõ nghĩa trong Java hiện đại. Khi khai báo `record`, compiler tạo sẵn `equals(Object)`, `hashCode()` và `toString()` dựa trên các **record component**. Vì vậy, hiểu chính xác quy tắc so sánh bằng nhau giúp tránh lỗi khi dùng record làm khóa của `Map`, phần tử của `Set` hoặc giá trị trao đổi giữa các lớp trong ứng dụng.

## 1. Quy tắc cốt lõi

Với **`equals(Object)` được compiler sinh tự động**, hai đối tượng record bằng nhau khi và chỉ khi **đồng thời** thỏa mãn:

1. Đối tượng được so sánh thuộc **chính xác cùng lớp record tại runtime** (không chỉ có các component giống nhau, không chỉ cùng interface).
2. Mọi cặp component tương ứng có giá trị bằng nhau theo quy tắc so sánh của kiểu component đó.

`null` không bằng một record khác `null`. Hai biến trỏ đến đúng cùng một đối tượng record đương nhiên bằng nhau; quan trọng hơn, hai **đối tượng khác nhau** vẫn có thể bằng nhau nếu cùng kiểu record và có các component bằng nhau.

```java
record CustomerId(long value) {}
record OrderId(long value) {}

CustomerId a = new CustomerId(42);
CustomerId b = new CustomerId(42);
OrderId order = new OrderId(42);

System.out.println(a == b);          // false: hai đối tượng khác nhau
System.out.println(a.equals(b));     // true: cùng CustomerId, cùng value
System.out.println(a.equals(order)); // false: CustomerId khác OrderId
System.out.println(a.equals(null));  // false
```

Điểm quan trọng nhất: `CustomerId(42)` và `OrderId(42)` **không bằng nhau** dù đều chứa một giá trị `long` bằng `42`. Điều này giúp tránh nhầm mã khách hàng với mã đơn hàng, ngay cả khi dữ liệu cơ bản của hai mã trùng nhau.

### Ví dụ đầy đủ có thể chạy từ Java 16

Lưu đoạn sau thành `RecordEqualityDemo.java`, biên dịch bằng `javac RecordEqualityDemo.java` rồi chạy `java RecordEqualityDemo`.

```java
public class RecordEqualityDemo {
    record Point(int x, int y) {}
    record Position(int x, int y) {}
    record CustomerId(long value) {}
    record OrderId(long value) {}

    public static void main(String[] args) {
        Point p1 = new Point(3, 5);
        Point p2 = new Point(3, 5);
        Position position = new Position(3, 5);

        System.out.println(p1 == p2);                 // false
        System.out.println(p1.equals(p2));             // true
        System.out.println(p1.equals(position));       // false
        System.out.println(p1.equals(new Point(3, 6))); // false
        System.out.println(p1.equals(null));           // false

        CustomerId customerId = new CustomerId(7);
        OrderId orderId = new OrderId(7);
        System.out.println(customerId.equals(orderId)); // false
    }
}
```

Hai khai báo `record Point(int x, int y)` và `record Position(int x, int y)` có cùng số lượng, tên và kiểu component nhưng vẫn tạo **hai lớp record độc lập**. `equals` mặc định không áp dụng *structural equality* giữa các lớp record khác nhau.

## 2. Vì sao phải cùng chính xác lớp record?

Record là lớp **ngầm định `final`**: không thể kế thừa một record để tạo một lớp con. Một record có thể `implements` interface, nhưng việc cùng triển khai một interface không làm các record trở thành cùng kiểu để so sánh bằng nhau.

```java
interface HasCode {
    String code();
}

record CountryCode(String code) implements HasCode {}
record ProductCode(String code) implements HasCode {}

HasCode country = new CountryCode("VN");
HasCode product = new ProductCode("VN");

System.out.println(country.equals(product)); // false
```

Ở đây, kiểu khai báo của biến là `HasCode`; lời gọi `equals` vẫn chạy trên đối tượng thật (`CountryCode` hoặc `ProductCode`). Quy tắc của `equals` mặc định xét **lớp record tại runtime**, không xét kiểu biến tham chiếu.

Có thể hình dung sơ bộ bước kiểm tra kiểu là so sánh `this.getClass()` với `other.getClass()`. Đây chỉ là **mô hình giải thích**; đặc tả Java không bắt buộc compiler phải tạo mã `equals` theo đúng thuật toán hay thứ tự kiểm tra đó.

## 3. Component được so sánh như thế nào?

Sau khi vượt qua kiểm tra cùng lớp record, `equals` mặc định dùng quy tắc tương ứng với **kiểu đã khai báo của từng component**:

| Kiểu component | Quy tắc bằng nhau | Hệ quả cần nhớ |
| --- | --- | --- |
| Kiểu nguyên thủy (`int`, `long`, `boolean`, v.v.) | Tương đương kết quả `compare(a, b) == 0` của lớp wrapper tương ứng. | Giá trị nguyên thủy giống nhau được xem là bằng nhau. |
| `float`, `double` | Tương đương `Float.compare` / `Double.compare` trả về `0`. | Hai `NaN` được xem là bằng nhau; `+0.0` và `-0.0` **không** bằng nhau. |
| Kiểu tham chiếu (`String`, record khác, `List`, ...) | Tương đương `Objects.equals(a, b)`. | Cùng `null` thì bằng nhau; khác `null` thì phụ thuộc `equals` của đối tượng thành phần. |
| Mảng (`int[]`, `String[]`, ...) | Là kiểu tham chiếu, nên dùng ngữ nghĩa `Objects.equals`. | Hai mảng khác đối tượng nhưng có cùng nội dung **không** tự động bằng nhau. |

Chẳng hạn, với record lồng record, việc so sánh lan đến `equals` của component:

```java
record Address(String city, String street) {}
record Customer(String name, Address address) {}

Customer c1 = new Customer("An", new Address("Hà Nội", "Tràng Tiền"));
Customer c2 = new Customer("An", new Address("Hà Nội", "Tràng Tiền"));

System.out.println(c1.equals(c2)); // true
```

Hai đối tượng `Address` riêng biệt vẫn bằng nhau vì bản thân `Address` cũng là record có các component bằng nhau.

### Lưu ý về số thực

```java
record Measurement(double value) {}

System.out.println(
    new Measurement(Double.NaN).equals(new Measurement(Double.NaN))
); // true

System.out.println(
    new Measurement(+0.0).equals(new Measurement(-0.0))
); // false
```

Đây là hành vi có chủ ý và ổn định của `equals` mặc định: khác với việc so sánh hai giá trị `double` bằng toán tử `==` trong một số tình huống. Tránh tự viết lại `equals` bằng phép `==` cho `double` hoặc `float` nếu không hiểu tác động lên tính phản xạ và `hashCode`.

## 4. “Cùng chính xác kiểu record” và generic: phân biệt kiểu runtime với tham số kiểu

Một record có thể là generic. Tuy nhiên, Java dùng *type erasure*: tham số kiểu như `String` và `Object` không được lưu như hai lớp record khác nhau tại runtime.

```java
record Box<T>(T value) {}

Box<String> text = new Box<>("hello");
Box<Object> object = new Box<>((Object) "hello");

System.out.println(text.equals(object)); // true
```

Kết quả là `true` vì cả hai đều là instance của **cùng lớp runtime `Box`**, và hai component đều chứa chuỗi `"hello"`. Do đó:

- **Bắt buộc:** cùng lớp record tại runtime, ví dụ `Box` với `Box`.
- **Không bắt buộc:** các tham số generic được viết trong mã nguồn phải giống nhau (`Box<String>` và `Box<Object>` vẫn có thể bằng nhau).
- **Vẫn bắt buộc:** các component phải bằng nhau; `new Box<>("1")` không bằng `new Box<>(1)` vì `String.equals(Integer)` trả về `false`.

Không đồng nhất cụm từ “chính xác kiểu record” với việc so sánh toàn bộ tham số generic trong mã nguồn.

## 5. Bẫy thường gặp: mảng và dữ liệu có thể thay đổi

Record đảm bảo các **trường component là `final`**, nhưng không tự biến những đối tượng được tham chiếu thành bất biến (*deeply immutable*). Điều này ảnh hưởng trực tiếp đến `equals` và `hashCode`.

### Mảng có cùng phần tử vẫn có thể khác nhau

```java
record Numbers(int[] values) {}

Numbers n1 = new Numbers(new int[] {1, 2, 3});
Numbers n2 = new Numbers(new int[] {1, 2, 3});

System.out.println(n1.equals(n2)); // false
```

Mỗi lần `new int[]` tạo một mảng riêng. Mảng không ghi đè `Object.equals`, nên `Objects.equals` so sánh danh tính của hai mảng, không duyệt từng phần tử.

Nếu cần bình đẳng theo nội dung mảng, có thể dùng kiểu dữ liệu có `equals` theo phần tử, ví dụ `List`, và sao chép để tránh thay đổi ngoài ý muốn:

```java
import java.util.List;

record Numbers(List<Integer> values) {
    Numbers {
        values = List.copyOf(values);
    }
}

Numbers n1 = new Numbers(List.of(1, 2, 3));
Numbers n2 = new Numbers(List.of(1, 2, 3));
System.out.println(n1.equals(n2)); // true
```

`List.copyOf` tạo một danh sách không thể sửa qua API của `List`; với `Integer` là kiểu bất biến, giá trị các phần tử cũng ổn định. Nếu component chứa đối tượng con có thể thay đổi, phải đánh giá khả năng thay đổi ở cấp sâu hơn.

Với mảng bắt buộc phải giữ nguyên, có thể tự triển khai `equals` bằng `Arrays.equals`, `hashCode` bằng `Arrays.hashCode`, đồng thời sao chép phòng vệ trong constructor và accessor. Khi tùy biến, hai phương thức này phải giữ nhất quán với nhau; không nên chỉ sửa riêng `equals`.

### Component có thể thay đổi sau khi làm khóa `Map`

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

record QueryKey(List<String> filters) {}

List<String> filters = new ArrayList<>(List.of("active"));
QueryKey key = new QueryKey(filters);
Map<QueryKey, String> cache = new HashMap<>();
cache.put(key, "cached result");

filters.add("premium"); // Thay đổi dữ liệu tham gia equals/hashCode
// Tra cứu key từ HashMap sau thay đổi có thể không còn tìm thấy giá trị.
```

Record ở ví dụ trên giữ nguyên tham chiếu `filters`, nhưng nội dung của danh sách vẫn thay đổi được. Vì `List.hashCode` phụ thuộc vào các phần tử, `hashCode` của `QueryKey` cũng có thể thay đổi sau khi đã chèn vào `HashMap`. Giải pháp phù hợp là bảo vệ dữ liệu ngay lúc xây dựng record:

```java
record QueryKey(List<String> filters) {
    QueryKey {
        filters = List.copyOf(filters);
    }
}
```

## 6. Quan hệ giữa `equals`, `hashCode` và các collection

Record mặc định sinh cả `equals` lẫn `hashCode` từ các component. Cần nhớ hợp đồng chung của Java:

- Nếu `a.equals(b)` là `true` thì **bắt buộc** `a.hashCode() == b.hashCode()`.
- Nếu `a.hashCode() == b.hashCode()` thì **không suy ra** `a.equals(b)`; đụng độ hash (*hash collision*) là hợp lệ.
- Không dựa vào công thức hoặc giá trị số nguyên cụ thể mà compiler/JDK tạo ra cho `hashCode` của record; đặc tả không cố định thuật toán kết hợp component.

```java
import java.util.HashSet;
import java.util.Set;

record CustomerId(long value) {}
record OrderId(long value) {}

Set<Object> ids = new HashSet<>();
ids.add(new CustomerId(10));
ids.add(new CustomerId(10)); // Trùng cùng lớp record + cùng value
ids.add(new OrderId(10));    // Khác lớp record

System.out.println(ids.size()); // 2
```

Khi dùng record làm khóa `Map` hoặc phần tử `Set`, quy tắc cùng lớp record tạo ra ranh giới kiểu rõ ràng: khóa `CustomerId(10)` không thể vô tình được coi là khóa `OrderId(10)` chỉ vì có cùng số `10`.

## 7. Khi nào cần tự viết `equals`?

Với record chỉ chứa các giá trị ổn định có `equals` phù hợp (`String`, số nguyên, enum, record khác, danh sách bất biến...), thông thường **giữ `equals`/`hashCode` do compiler sinh** là lựa chọn rõ ràng và an toàn.

Nếu yêu cầu nghiệp vụ muốn hai cách viết khác nhau được coi là một giá trị, thường nên **chuẩn hóa dữ liệu trong canonical constructor** rồi tận dụng `equals` mặc định:

```java
import java.util.Locale;
import java.util.Objects;

record CategoryCode(String value) {
    CategoryCode {
        Objects.requireNonNull(value, "value");
        value = value.trim().toUpperCase(Locale.ROOT);
    }
}

System.out.println(
    new CategoryCode(" vip ").equals(new CategoryCode("VIP"))
); // true
```

Hai record này bằng nhau vì sau chuẩn hóa chúng chứa **cùng giá trị** `"VIP"`, đồng thời vẫn là cùng lớp `CategoryCode`. Cách này giúp mọi đối tượng giữ một biểu diễn thống nhất, thay vì tạo logic so sánh đặc biệt trong `equals`.

Java vẫn cho phép khai báo tường minh `equals(Object)` trong record. Khi làm vậy, lập trình viên phải bảo đảm hợp đồng `Object.equals`, sự nhất quán với `hashCode` và bất biến đặc thù của record: tạo một record mới bằng cách truyền kết quả các accessor của record cũ vào canonical constructor phải tạo ra một giá trị bằng record cũ. Quy tắc **cùng lớp record + mọi component bằng nhau** ở phần đầu là quy tắc của **phương thức được sinh tự động**; không nên khẳng định rằng Java cấm mọi cách tùy biến `equals`.

## 8. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| Hai record khác tên nhưng có cùng component sẽ `equals` nhau. | **Sai** | Khác lớp record tại runtime. |
| Hai đối tượng khác địa chỉ bộ nhớ thì không thể `equals` nhau. | **Sai** | Record so sánh giá trị component, không chỉ danh tính đối tượng. |
| Hai record cùng triển khai một interface thì có thể mặc định `equals` nhau. | **Sai** | Cùng interface chưa phải cùng lớp record. |
| `Box<String>` và `Box<Object>` luôn không bằng nhau. | **Sai** | Cùng runtime class `Box`; phải xem component. |
| `record Data(byte[] bytes)` so sánh sâu nội dung hai mảng theo mặc định. | **Sai** | Mảng dùng so sánh tham chiếu qua `Objects.equals`. |
| Record có các trường `final` nên mọi component chắc chắn bất biến. | **Sai** | Bản thân đối tượng tham chiếu có thể thay đổi. |
| Cùng lớp record và mọi component bằng nhau thì `equals` mặc định trả về `true`. | **Đúng** | Đây là hợp đồng của implementation tự động. |

## 9. Câu hỏi tự kiểm tra

1. Vì sao `new CustomerId(5).equals(new OrderId(5))` trả về `false` dù cả hai record chỉ chứa số `5`?
2. Tại sao `new Box<String>("A")` có thể bằng `new Box<Object>("A")` dù hai kiểu generic viết khác nhau?
3. Vì sao record có component `int[]` cần xử lý riêng nếu bài toán yêu cầu so sánh theo nội dung mảng?
4. Điều gì có thể xảy ra khi thay đổi nội dung `List` trong component sau khi dùng record làm khóa của `HashMap`?
5. Khi cần loại bỏ khoảng trắng thừa và chuẩn hóa chữ hoa của mã danh mục, vì sao chuẩn hóa trong canonical constructor thường hợp lý hơn việc ghi đè `equals`?

**Ghi nhớ:** Với `equals(Object)` mặc định, **bình đẳng của record = cùng chính xác lớp record tại runtime + bình đẳng của từng component**. Đây là ngữ nghĩa đã ổn định từ Java 16 và tiếp tục áp dụng trong các phiên bản Java hiện đại.

## Tài liệu tham khảo chính thức

- [Java SE 25 API — `java.lang.Record`, hợp đồng của `equals` và `hashCode`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Record.html)
- [Java Language Specification, §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10)
- [JEP 395 — Records, hoàn thiện trong Java 16](https://openjdk.org/jeps/395)
