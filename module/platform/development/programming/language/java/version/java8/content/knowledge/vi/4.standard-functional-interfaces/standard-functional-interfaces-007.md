# Predicate.and, or, negate và isEqual trong Java

## 1. Mục tiêu: ghép các điều kiện thành quy tắc có thể tái sử dụng

`java.util.function.Predicate<T>` là functional interface biểu diễn một điều kiện nhận giá trị kiểu `T` và trả về `boolean`. Phương thức trừu tượng duy nhất của nó là:

~~~java
boolean test(T value);
~~~

Thay vì tạo một lambda dài chứa nhiều toán tử `&&`, `||`, `!`, chúng ta có thể đặt tên từng quy tắc và kết hợp chúng bằng bốn phương thức quan trọng:

| API | Loại | Ý nghĩa | Phiên bản Java |
| --- | --- | --- | --- |
| `a.and(b)` | `default` | Cả `a` và `b` phải đúng | Java 8+ |
| `a.or(b)` | `default` | Ít nhất `a` hoặc `b` đúng | Java 8+ |
| `a.negate()` | `default` | Đảo kết quả của `a` | Java 8+ |
| `Predicate.isEqual(target)` | `static` | Tạo điều kiện bằng `target` theo `Objects.equals` | Java 8+ |

Tất cả vẫn được sử dụng trong Java hiện đại. Chúng hữu ích cho bộ lọc danh sách, điều kiện nghiệp vụ, validation đơn giản, tìm kiếm, xử lý Stream và callback.

Điểm mấu chốt: bốn API này **tạo hoặc trả về predicate**, chứ không tự duyệt dữ liệu. Chúng mô tả **cách kiểm tra**; điều kiện mới được thực thi khi ai đó gọi `test` hoặc một API như `Stream.filter` gọi nó.

~~~java
java.util.function.Predicate<Integer> positive = x -> x > 0;
java.util.function.Predicate<Integer> even = x -> x % 2 == 0;

java.util.function.Predicate<Integer> positiveEven =
        positive.and(even);

System.out.println(positiveEven.test(8));  // true
System.out.println(positiveEven.test(7));  // false
System.out.println(positiveEven.test(-4)); // false
~~~

Đây là mảnh mã minh họa bên trong một phương thức. `positiveEven` không phải một boolean cố định; nó là một **đối tượng hành vi** có thể kiểm tra nhiều giá trị khác nhau.

## 2. `and`: hai điều kiện cùng đúng

Về mặt logic:

~~~text
a.and(b).test(x)  ~  a.test(x) && b.test(x)
~~~

Dấu `~` ở đây chỉ mang nghĩa **tương đương về cách đánh giá điều kiện**, không phải một toán tử Java. Với `and`:

1. Gọi `a.test(x)` trước.
2. Nếu `a` trả `false`, trả `false` ngay, **không gọi `b.test(x)`**.
3. Nếu `a` trả `true`, gọi `b.test(x)` và dùng kết quả của `b`.

Bảng chân trị:

| `a` | `b` | `a.and(b)` |
| --- | --- | --- |
| `false` | `false` | `false` |
| `false` | `true` | `false` |
| `true` | `false` | `false` |
| `true` | `true` | `true` |

Ví dụ nghiệp vụ: “đơn hàng **đã thanh toán và** tổng tiền từ 500 trở lên”.

~~~java
Predicate<Order> paid = Order::isPaid;
Predicate<Order> sufficientlyLarge = order -> order.getTotal() >= 500;

Predicate<Order> eligibleForGift = paid.and(sufficientlyLarge);
~~~

Đây là **mảnh mã minh họa**: giả định đã có lớp `Order` và import `java.util.function.Predicate`. Nên đặt tên rõ vai trò của từng predicate để người đọc hiểu quy tắc.

Đặc tính quan trọng là **short-circuit**: thứ tự không chỉ liên quan hiệu năng mà còn tránh lỗi. Nếu một predicate có thể ném exception hoặc tạo side effect, đảo thứ tự có thể thay đổi hành vi. Vì vậy dù AND có tính giao hoán trong đại số Boolean thuần, `a.and(b)` và `b.and(a)` **không nhất thiết có cùng hành vi quan sát được trong chương trình**.

## 3. `or`: ít nhất một điều kiện đúng

Về logic:

~~~text
a.or(b).test(x)  ~  a.test(x) || b.test(x)
~~~

Quy tắc thực thi:

1. Gọi `a.test(x)` trước.
2. Nếu kết quả là `true`, trả `true` ngay, **không gọi `b.test(x)`**.
3. Chỉ khi `a` trả `false`, Java mới gọi `b.test(x)`.

| `a` | `b` | `a.or(b)` |
| --- | --- | --- |
| `false` | `false` | `false` |
| `false` | `true` | `true` |
| `true` | `false` | `true` |
| `true` | `true` | `true` |

Ví dụ: “người dùng là quản trị viên **hoặc** là người sở hữu tài nguyên”.

~~~java
Predicate<User> admin = User::isAdmin;
Predicate<User> owner = user -> user.getId().equals(resourceOwnerId);

Predicate<User> mayEdit = admin.or(owner);
~~~

Đây là mảnh mã minh họa, chưa gồm khai báo `User` và `resourceOwnerId`. Các phép kiểm tra quyền thật sự phải dùng dữ liệu xác thực đáng tin cậy tại điểm thực thi chính sách; `Predicate` là cách biểu diễn điều kiện, không phải một cơ chế phân quyền hoàn chỉnh.

`or` có short-circuit: nếu `admin` đúng, predicate `owner` không được gọi. Đừng dựa vào `owner` để thực hiện ghi log hoặc cập nhật một giá trị bắt buộc trong mọi trường hợp.

## 4. `negate`: đảo điều kiện hiện có

`a.negate()` trả về predicate có kết quả ngược với `a`:

~~~text
a.test(x)           negate().test(x)
true                false
false               true
~~~

Ví dụ:

~~~java
Predicate<String> empty = String::isEmpty;
Predicate<String> nonEmpty = empty.negate();

System.out.println(nonEmpty.test("Java")); // true
System.out.println(nonEmpty.test(""));     // false
~~~

Khi gọi `a.negate()`, Java không thay đổi ý nghĩa của `a`; nó tạo một hành vi phủ định có thể tái sử dụng. Vì vậy `empty.test("")` vẫn là `true` sau khi tạo `nonEmpty`.

### Phân biệt `negate()` và `Predicate.not(...)`

`negate()` là **phương thức instance** có từ Java 8:

~~~java
Predicate<String> notEmpty = ((Predicate<String>) String::isEmpty).negate();
~~~

`Predicate.not(predicate)` là **phương thức static**, được bổ sung trong Java 11, phù hợp khi cần phủ định một method reference mà không muốn ép kiểu:

~~~java
Predicate<String> nonBlank = Predicate.not(String::isBlank);
~~~

Ví dụ thứ hai cần JDK 11+ bởi cả `Predicate.not` và `String.isBlank` được giới thiệu ở Java 11. Chúng vẫn là các API hiện đại. Với JDK 8, có thể gán method reference cho biến kiểu `Predicate<String>` rồi gọi `negate()`, đồng thời dùng quy tắc riêng nếu cần kiểm tra ký tự trắng.

### Phủ định không tự thêm xử lý null

~~~java
Predicate<String> shortText = s -> s.length() < 4;
Predicate<String> notShort = shortText.negate();
~~~

Nếu gọi `notShort.test(null)`, lambda gốc `shortText` vẫn gọi `null.length()` và ném `NullPointerException`. `negate()` chỉ đảo **kết quả boolean nếu predicate gốc thực thi thành công**, không biến một predicate không chịu được null thành predicate null-safe.

## 5. `Predicate.isEqual(target)`: biểu diễn phép so sánh bằng

`Predicate.isEqual(targetRef)` tạo một predicate trả lời xem giá trị được kiểm tra có **bằng target** hay không theo tiêu chuẩn `java.util.Objects.equals`. Cách hình dung gần đúng:

~~~java
// Minh họa hành vi; đây KHÔNG phải mã nguồn triển khai nội bộ bắt buộc:
Predicate<String> sameAsJava =
        candidate -> java.util.Objects.equals("Java", candidate);
~~~

Thay vì viết lambda này nhiều lần:

~~~java
Predicate<String> sameAsJava = Predicate.isEqual("Java");

System.out.println(sameAsJava.test("Java")); // true
System.out.println(sameAsJava.test("java")); // false
System.out.println(sameAsJava.test(null));   // false
~~~

### 5.1. So sánh `null` an toàn

`Objects.equals(a, b)` trả về `true` khi cả hai là `null`, `false` khi một bên là `null`, và nếu cả hai khác `null` thì sử dụng `a.equals(b)`.

Do đó:

~~~java
Predicate<String> isNull = Predicate.isEqual(null);
Predicate<String> isJava = Predicate.isEqual("Java");

System.out.println(isNull.test(null));  // true
System.out.println(isNull.test("x"));   // false
System.out.println(isJava.test(null));  // false
~~~

Trong mã chỉ cần nhận diện null, method reference `Objects::isNull` và `Objects::nonNull` thường còn dễ hiểu hơn. Nhưng `isEqual(null)` cho thấy quy tắc null của API `isEqual` rõ ràng.

### 5.2. So sánh nội dung, không phải `==`

Với `String`, `==` so sánh **reference**; `equals` so sánh nội dung. Vì vậy:

~~~java
Predicate<String> expected = Predicate.isEqual("Java");
System.out.println(expected.test(new String("Java"))); // true
~~~

`Predicate.isEqual` không tự định nghĩa thế nào là “bằng” cho mọi loại dữ liệu: nó dựa vào `equals` của kiểu tương ứng. Nếu lớp tự viết không override `equals`, hành vi kế thừa từ `Object` thường kiểm tra cùng object identity.

### 5.3. `isEqual` không phải so sánh bỏ qua hoa/thường, deep equality, hoặc “bằng về số học”

- `Predicate.isEqual("Java")` **không** coi `"java"` là bằng.
- Với array, `array.equals(otherArray)` không so sánh sâu từng phần tử; nếu cần so sánh cấu trúc, chọn `Arrays.equals` hoặc `Arrays.deepEquals` phù hợp.
- Với `BigDecimal`, `equals` xét cả giá trị và scale; `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` là `false`. Khi yêu cầu là bằng về số học, `compareTo(...) == 0` thường thích hợp hơn.

Ví dụ dùng predicate tùy biến:

~~~java
Predicate<String> javaIgnoreCase =
        s -> s != null && "Java".equalsIgnoreCase(s);

Predicate<java.math.BigDecimal> numericallyOne =
        x -> x != null &&
             x.compareTo(new java.math.BigDecimal("1.00")) == 0;
~~~

Hai mảnh mã trên minh họa rằng phải chọn **định nghĩa equality theo nghiệp vụ**, chứ không dùng `isEqual` cho mọi yêu cầu một cách máy móc.

### 5.4. Dùng `isEqual` với kiểu generic

Định nghĩa API là một static generic factory về mặt sử dụng:

~~~java
Predicate<String> sameName = Predicate.isEqual("An");
Predicate<Integer> isTen = Predicate.isEqual(10);
~~~

Kiểu đích giúp trình biên dịch suy luận kiểu. `isEqual` không hạn chế chỉ truyền `String` hoặc số; một object có hợp đồng `equals` phù hợp cũng có thể trở thành target. Tên `targetRef` nhấn mạnh rằng factory nhận một reference tới giá trị đích; cần cẩn thận khi target là object mutable: thay đổi trạng thái có thể ảnh hưởng hành vi `equals` trong những lần gọi sau.

## 6. Ví dụ chạy hoàn chỉnh: lọc sản phẩm bằng `and`, `or`, `negate`, `isEqual`

Tạo tệp **PredicateCompositionDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.function.Predicate;

public class PredicateCompositionDemo {
    static final class Product {
        private final String name;
        private final int price;
        private final int stock;
        private final String category;

        Product(String name, int price, int stock, String category) {
            this.name = name;
            this.price = price;
            this.stock = stock;
            this.category = category;
        }
    }

    static List<String> namesMatching(
            List<Product> products, Predicate<Product> condition) {
        List<String> result = new ArrayList<>();
        for (Product product : products) {
            if (condition.test(product)) {
                result.add(product.name);
            }
        }
        return result;
    }

    public static void main(String[] args) {
        List<Product> products = Arrays.asList(
                new Product("Book", 120, 3, "READ"),
                new Product("Pen", 15, 0, "OFFICE"),
                new Product("Notebook", 115, 8, "OFFICE"),
                new Product("Bag", 250, 0, "TRAVEL"),
                new Product("Marker", 40, 5, "OFFICE"),
                new Product("Gift", 100, 2, "TRAVEL")
        );

        Predicate<Product> inStock = product -> product.stock > 0;
        Predicate<Product> affordable = product -> product.price <= 100;

        Predicate<String> officeCategory = Predicate.isEqual("OFFICE");
        Predicate<Product> isOffice =
                product -> officeCategory.test(product.category);

        // Có hàng VÀ (giá <= 100 HOẶC thuộc nhóm OFFICE).
        Predicate<Product> highlighted =
                inStock.and(affordable.or(isOffice));

        // Có hàng VÀ KHÔNG thuộc nhóm OFFICE.
        Predicate<Product> inStockNonOffice =
                inStock.and(isOffice.negate());

        System.out.println(namesMatching(products, highlighted));
        System.out.println(namesMatching(products, inStockNonOffice));
        System.out.println(officeCategory.test(null));
        System.out.println(Predicate.<String>isEqual(null).test(null));
    }
}
~~~

Biên dịch/chạy với JDK 17+; tất cả API được dùng trong chương trình này đã có ở Java 8:

~~~bash
javac PredicateCompositionDemo.java
java PredicateCompositionDemo
~~~

Kết quả chính xác:

~~~text
[Notebook, Marker, Gift]
[Book, Gift]
false
true
~~~

**Giải thích:**

- `Book`: còn hàng nhưng giá 120 và không thuộc `OFFICE`, nên không thỏa `highlighted`. Khi kiểm tra `inStockNonOffice`, Book thỏa.
- `Pen`: giá thấp và thuộc `OFFICE`, nhưng hết hàng, nên hai phép lọc có `inStock` đều loại.
- `Notebook`: giá 115 (không `affordable`), nhưng thuộc `OFFICE` và còn hàng; nhờ `affordable.or(isOffice)`, nó vẫn được giữ.
- `Bag`: hết hàng, nên bị loại sớm trước khi xét điều kiện còn lại.
- `Marker`: còn hàng, giá 40, thuộc `OFFICE`; được chọn bởi `highlighted`.
- `Gift`: còn hàng, giá 100, không `OFFICE`; được chọn bởi cả `highlighted` và `inStockNonOffice`.
- `officeCategory.test(null)` là `false`, còn `Predicate.isEqual(null).test(null)` là `true`.

Ví dụ sử dụng vòng lặp trong `namesMatching` để thấy rõ nơi `test` được gọi. Trong ứng dụng có thể thay bằng Stream:

~~~java
// Mảnh mã minh họa trong main của lớp trên:
List<String> highlightedNames = products.stream()
        .filter(highlighted)
        .map(product -> product.name)
        .collect(java.util.stream.Collectors.toList());
~~~

Ở đây `filter(highlighted)` giữ phần tử có `test` trả `true`. Dùng `Stream.filter` không thay đổi semantics của `and/or/negate/isEqual`; nó chỉ cung cấp cách tổ chức pipeline. Với Stream song song, không nên phụ thuộc vào side effect của predicate.

## 7. Short-circuit quan sát được bằng chương trình chạy thật

Để tránh nhầm `and`/`or` luôn gọi cả hai vế, tạo tệp **PredicateShortCircuitDemo.java**:

~~~java
import java.util.function.Predicate;

public class PredicateShortCircuitDemo {
    public static void main(String[] args) {
        Predicate<String> nonNull = text -> {
            System.out.println("nonNull: " + text);
            return text != null;
        };

        Predicate<String> lengthAtLeastFour = text -> {
            System.out.println("length: " + text);
            return text.length() >= 4;
        };

        Predicate<String> startsWithJ = text -> {
            System.out.println("prefix: " + text);
            return text.startsWith("J");
        };

        Predicate<String> safe =
                nonNull.and(lengthAtLeastFour).and(startsWithJ);

        System.out.println("null=" + safe.test(null));
        System.out.println("Go=" + safe.test("Go"));
        System.out.println("Java=" + safe.test("Java"));

        Predicate<Integer> isZero = number -> {
            System.out.println("check zero");
            return number == 0;
        };
        Predicate<Integer> positive = number -> {
            System.out.println("check positive");
            return number > 0;
        };

        System.out.println("or0=" + isZero.or(positive).test(0));
        System.out.println("or3=" + isZero.or(positive).test(3));

        Predicate<String> isJava = Predicate.isEqual("Java");
        System.out.println("notJava=" + isJava.negate().test("Kotlin"));
    }
}
~~~

Chạy:

~~~bash
javac PredicateShortCircuitDemo.java
java PredicateShortCircuitDemo
~~~

**Stdout chính xác:**

~~~text
nonNull: null
null=false
nonNull: Go
length: Go
Go=false
nonNull: Java
length: Java
prefix: Java
Java=true
check zero
or0=true
check zero
check positive
or3=true
notJava=true
~~~

Diễn giải:

1. Với `null`, `nonNull` trả `false`; `lengthAtLeastFour` và `startsWithJ` không chạy. Vì vậy không có lỗi `NullPointerException`.
2. Với `"Go"`, `nonNull` đúng, nhưng độ dài không đạt 4; `startsWithJ` không chạy.
3. Với `"Java"`, cả ba predicate lần lượt được kiểm tra.
4. `isZero.or(positive)` trên `0` dừng ngay khi `isZero` đúng, nên không in `check positive`. Trên `3`, `isZero` sai mới gọi `positive`.
5. `isJava.negate()` trả `true` cho `"Kotlin"`. Hàm `isEqual` không cần gọi `test` bằng một bước riêng để tạo phủ định.

Các lệnh `println` trong predicate **chỉ phục vụ mục đích học về thứ tự gọi**. Khi viết quy tắc sản xuất, nên tránh tác dụng phụ và không dựa vào số lần gọi `test`.

## 8. Kết hợp nhiều điều kiện: ngoặc, thứ tự và định luật De Morgan

### 8.1. Mỗi lần gọi là một lớp kết hợp mới

Các toán tử Java `&&`, `||` có quy tắc ưu tiên, nhưng chuỗi `Predicate` là **lời gọi phương thức**. Ví dụ:

~~~java
Predicate<T> rule1 = a.and(b.or(c)); // a && (b || c)
Predicate<T> rule2 = a.and(b).or(c); // (a && b) || c
~~~

Hai dòng là **mã minh họa dùng các biến `a`, `b`, `c` có kiểu Predicate<T> đã khai báo**, không biên dịch độc lập nếu thiếu ngữ cảnh. Chúng biểu diễn hai logic khác nhau. Khi yêu cầu phức tạp, ưu tiên biến trung gian có tên:

~~~java
Predicate<T> oneOfAlternatives = b.or(c);
Predicate<T> combined = a.and(oneOfAlternatives);
~~~

Giữ cách nhóm bằng biến giúp review yêu cầu nghiệp vụ dễ hơn khi predicate có nhiều nhánh.

### 8.2. Luật De Morgan

Theo logic Boolean thuần:

~~~text
!(A && B) = (!A || !B)
!(A || B) = (!A && !B)
~~~

Áp dụng cho predicate:

~~~java
Predicate<T> notBoth = a.and(b).negate();
Predicate<T> eitherFails = a.negate().or(b.negate());

Predicate<T> neither = a.or(b).negate();
Predicate<T> bothFail = a.negate().and(b.negate());
~~~

Đây là các **mảnh mã minh họa** cần có `T` và `a`, `b` hợp lệ. Với predicate **thuần, kết thúc bình thường và không side effect**, các cặp trên cho cùng kết quả Boolean.

Tuy nhiên, nếu predicate có side effect, phụ thuộc thời gian, hoặc có thể ném exception, cần xem xét điều kiện thực thi cụ thể trước khi thay thế công thức. Việc coi các biểu thức là tương đương về toán học không cho phép bỏ qua hợp đồng runtime của các phương thức.

### 8.3. Đừng nhầm phủ định toàn bộ với phủ định từng nhánh

~~~java
Predicate<Integer> positive = n -> n > 0;
Predicate<Integer> even = n -> n % 2 == 0;

Predicate<Integer> notPositiveAndEven =
        positive.and(even).negate();

Predicate<Integer> notPositiveButEven =
        positive.negate().and(even);
~~~

Hai điều kiện khác nhau:

- `positive.and(even).negate()`: **không phải** số dương chẵn; `-3`, `3` và `0` đều thỏa.
- `positive.negate().and(even)`: số **không dương và chẵn**; `0`, `-2` thỏa, còn `3` không thỏa.

Tên rõ ràng và test theo biên giúp tránh đảo nhầm toàn bộ biểu thức logic.

## 9. Null safety khi tổ hợp Predicate

### 9.1. Kiểm tra giá trị đầu vào trước khi gọi method

Đây là lỗi hay gặp:

~~~java
Predicate<String> atLeastFour = s -> s.length() >= 4;
atLeastFour.test(null); // Ném NullPointerException
~~~

Một cách dùng `and` an toàn khi muốn loại null:

~~~java
Predicate<String> valid =
        ((Predicate<String>) java.util.Objects::nonNull)
                .and(s -> s.length() >= 4);
~~~

`valid.test(null)` sẽ trả `false` mà không gọi `length()`. Một cách diễn đạt khác, dễ đọc hơn:

~~~java
Predicate<String> nonNull = java.util.Objects::nonNull;
Predicate<String> atLeastFour = s -> s.length() >= 4;
Predicate<String> valid = nonNull.and(atLeastFour);
~~~

Không đổi thành `atLeastFour.and(nonNull)`: predicate đầu tiên sẽ gọi `length()` trước khi kiểm tra null.

Với `or`, có thể tạo điều kiện “null hoặc chuỗi rỗng”:

~~~java
Predicate<String> isNull = java.util.Objects::isNull;
Predicate<String> isEmpty = String::isEmpty;
Predicate<String> absent = isNull.or(isEmpty);
~~~

`absent.test(null)` trả `true` do `isNull` đúng, nên `isEmpty` không chạy. Lưu ý điều kiện `isEmpty` chỉ kiểm tra chuỗi có độ dài 0, không kiểm tra chuỗi chứa toàn dấu cách; với Unicode whitespace cần định nghĩa riêng tiêu chí mong muốn, chẳng hạn `String.isBlank` từ Java 11.

### 9.2. Predicate đối số null khác với dữ liệu đầu vào null

Một predicate tự viết *có thể* chấp nhận `test(null)` nếu thân hàm định nghĩa rõ. Nhưng với đối số `other` của các phương thức `and` và `or`, Java yêu cầu một predicate **không null**:

~~~java
Predicate<String> a = s -> s != null;
a.and(null); // Ném NullPointerException ngay khi kết hợp
a.or(null);  // Tương tự
~~~

Đây là mảnh mã cố ý minh họa lỗi runtime. `negate()` không nhận đối số, nên không có vấn đề truyền một `other` null. Còn `Predicate.isEqual(null)` lại **hoàn toàn hợp lệ**: `null` lúc này là *giá trị đích để so sánh*, không phải một predicate để gọi.

**Ghi nhớ ba trường hợp khác nhau:**

- `predicate.test(null)`: có thể đúng/sai hoặc ném exception tùy thân predicate.
- `predicate.and(null)` và `predicate.or(null)`: không hợp lệ, ném `NullPointerException` khi ghép.
- `Predicate.isEqual(null)`: hợp lệ và tạo predicate kiểm tra đầu vào có null hay không.

## 10. Thiết kế quy tắc ổn định trong ứng dụng

### 10.1. Đặt tên theo ý nghĩa nghiệp vụ

Đặt tên như `hasPermission`, `withinBudget`, `validEmailFormat` (khi đã định nghĩa rõ tiêu chí), `isActive` sẽ dễ hiểu hơn viết liền 5 phép `and`, `or`, `negate`. Với quy tắc dùng ở nhiều nơi, trích thành phương thức rõ trách nhiệm:

~~~java
static boolean containsKeyword(String text) {
    return text != null && text.contains("Java");
}
~~~

Đây là mảnh mã cần đặt trong một lớp. Khi phù hợp, dùng method reference `YourClass::containsKeyword`; nó có thể được chuyển thành `Predicate<String>` theo target typing.

### 10.2. Ưu tiên predicate thuần

Các quy tắc `a.and(b)` và `a.or(b)` có short-circuit. `Stream.filter`, `anyMatch`, `allMatch`, `noneMatch` có thể gọi predicate trên tập phần tử khác nhau và dừng sớm. Trong parallel Stream, thứ tự callback thực tế cũng có thể thay đổi. Vì vậy:

- Tránh vừa kiểm tra vừa sửa `List`, `Map`, số đếm ngoài luồng hoặc gọi API tạo tác dụng phụ trong `test`.
- Đừng dùng `test` để thực hiện một hành động bắt buộc, bởi nhánh logic có thể không được gọi.
- Nếu cần audit/tracing, thiết kế phần ghi nhận độc lập và nêu rõ điểm thực thi, thay vì ẩn side effect vào predicate lọc.
- Các predicate có thể được gọi nhiều lần với cùng giá trị; nếu nguồn dữ liệu là mutable, kết quả có thể thay đổi giữa những lần gọi.

### 10.3. Tránh giả định `isEqual` chụp đối tượng bất biến

`Predicate.isEqual(target)` giữ target tham chiếu đến object đã truyền. Khi object mutable thay đổi, kết quả `equals` có thể thay đổi. Nếu cần điều kiện **ổn định theo thời điểm tạo**, hãy dùng dữ liệu bất biến (ví dụ `String`, một record bất biến với các thành phần bất biến, hoặc bản sao bất biến thật sự theo yêu cầu). **Không** chỉ thêm `final` vào reference rồi cho rằng trạng thái bên trong object đã bị khóa.

### 10.4. Những giới hạn của Predicate

`Predicate<T>` có SAM `boolean test(T)`, không khai báo checked exception. Nếu logic điều kiện có thể phát sinh `IOException` hay checked exception khác, cần xử lý đúng lỗi trong lambda hoặc định nghĩa một functional interface riêng có `throws` phù hợp; không nên tự biến lỗi hệ thống thành `false` nếu như vậy che giấu sự cố.

Predicate chỉ trả lời “đúng/sai”. Khi validation cần thông điệp giải thích, nhiều lỗi đồng thời hoặc phân biệt sai đầu vào với lỗi hạ tầng, nên dùng kiểu kết quả có thông tin chi tiết thay vì cố nhồi tất cả vào `boolean`.

## 11. Lỗi thường gặp

| Lỗi | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Hiểu `and/or` luôn gọi cả hai vế | Cả hai short-circuit | Không gắn logic bắt buộc vào vế sau |
| Gọi `length()` trước khi kiểm tra null | Gây NPE khi dữ liệu null | Ghép `Objects::nonNull` ở bên trái của `and` |
| Nhầm `negate()` thành sửa predicate gốc | Nó tạo một predicate phủ định | Lưu giá trị mới vào biến nếu cần |
| `isEqual` được hiểu là `==` | `isEqual` dùng `Objects.equals` | Dùng đúng định nghĩa equality |
| Dùng `isEqual` cho so sánh bỏ qua chữ hoa | `String.equals` phân biệt hoa/thường | Tạo predicate với `equalsIgnoreCase` có xử lý null |
| Dùng `isEqual` để so sánh số `BigDecimal` khác scale | `BigDecimal.equals` xét cả scale | Cân nhắc `compareTo(...) == 0` nếu phù hợp |
| Ghép `a.and(b).or(c)` khi muốn `a.and(b.or(c))` | Nhóm logic khác nhau | Dùng biến trung gian rõ ý |
| Truyền `null` vào `and` hoặc `or` | Tham số `other` phải không null | Kiểm tra nguồn predicate trước khi kết hợp |
| Dùng mutable state để đếm trong predicate | Side effect phụ thuộc số lần và thứ tự gọi | Dùng terminal operation hoặc công cụ thống kê riêng |
| Cho rằng `isEqual(null)` là lỗi | `null` là target hợp lệ | Dùng `Objects::isNull` nếu dễ đọc hơn |

## 12. Bài tập thực hành

**Bài 1 — Suy ra kết quả.** Cho:

~~~java
Predicate<Integer> a = x -> x > 10;
Predicate<Integer> b = x -> x % 2 == 0;

Predicate<Integer> first = a.and(b);
Predicate<Integer> second = a.or(b);
Predicate<Integer> third = a.and(b).negate();
~~~

Hãy tính ba kết quả khi truyền lần lượt `8`, `11`, `12`. Đáp án để tự đối chiếu:

| Giá trị | `first` | `second` | `third` |
| --- | --- | --- | --- |
| `8` | `false` | `true` | `true` |
| `11` | `false` | `true` | `true` |
| `12` | `true` | `true` | `false` |

Các đoạn trên là mã trong phương thức đã import `Predicate`.

**Bài 2 — Null-safe.** Tạo predicate cho phép một chuỗi chỉ khi không null, không rỗng và có độ dài tối đa 8 ký tự. Hãy ghép các điều kiện bằng `and`, kiểm tra với `null`, `""`, `"Java"`, `"JavaLanguage"`; giải thích vị trí của điều kiện `nonNull`.

**Bài 3 — `isEqual` hay so sánh đặc biệt?** Viết hai predicate: một kiểm tra `"OPEN"` chính xác, một chấp nhận `"open"` không phân biệt hoa/thường. Sau đó thử đầu vào `null`. Giải thích vì sao hai quy tắc không thể dùng `Predicate.isEqual("OPEN")` y hệt nhau.

**Bài 4 — Grouping.** Cho ba điều kiện `vip`, `paid`, `eligibleRegion`. Biểu diễn quy tắc “khách VIP hoặc đã thanh toán, và thuộc khu vực được hỗ trợ” bằng biến trung gian rõ nghĩa. So sánh với `vip.or(paid.and(eligibleRegion))` bằng một ví dụ giá trị khiến hai biểu thức khác nhau.

**Bài 5 — Kiểm tra short-circuit.** Tạo `a`, `b` có in thông báo mỗi lần được gọi. Chạy `a.and(b)` với `a=false` và `a.or(b)` với `a=true`. Dự đoán stdout trước khi chạy; sau đó bỏ các side effect và giữ nguyên điều kiện.

**Bài 6 — Quy tắc lọc danh sách.** Dùng `Predicate.isEqual("OFFICE")`, `and`, `or` và `negate` để tạo ba tiêu chí trên danh sách ở phần 6: (a) còn hàng và thuộc OFFICE, (b) giá rẻ hoặc thuộc OFFICE, (c) không thuộc OFFICE. Kiểm tra thứ tự phần tử trong kết quả, và giải thích vì sao `Pen` có thể xuất hiện ở tiêu chí (b) nhưng không xuất hiện ở tiêu chí (a).

## 13. Tóm tắt

- **`and`** là AND với short-circuit: vế trái sai thì vế phải không chạy.
- **`or`** là OR với short-circuit: vế trái đúng thì vế phải không chạy.
- **`negate`** tạo predicate có kết quả đảo ngược; nó không sửa predicate gốc và không tự thêm null safety.
- **`Predicate.isEqual(target)`** kiểm tra bình đẳng theo `Objects.equals`; `target=null` là hợp lệ. Đây là equality theo hợp đồng `equals`, không phải so sánh reference `==`, so sánh không phân biệt hoa/thường hay deep equality.
- Khi ghép quy tắc, cần quan tâm **thứ tự**, **nhóm biểu thức**, **null**, **side effect** và khả năng ném exception. Các phương thức này vẫn là thành phần cốt lõi của cách viết điều kiện bằng Java hiện đại.
