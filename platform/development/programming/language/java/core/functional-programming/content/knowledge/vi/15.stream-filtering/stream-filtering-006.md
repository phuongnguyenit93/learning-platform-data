# Kết hợp điều kiện lọc bằng Predicate trong Java

## 1. Mục tiêu: biến điều kiện thành các hàm có thể ghép

Khi lọc danh sách bằng Java Stream, điều kiện được truyền vào `filter` có kiểu `Predicate<T>`. Đây là một **functional interface** nhận một giá trị kiểu `T` và trả về `boolean` thông qua phương thức trừu tượng duy nhất:

```java
boolean test(T value);
```

Vì vậy, một biểu thức như `item -> item.price() >= 20` là một điều kiện có thể lưu, đặt tên, tái sử dụng, kết hợp hoặc truyền vào API. Thay vì nhồi toàn bộ quy tắc vào một lambda dài, ta có thể tách từng điều kiện rồi ghép chúng bằng:

- `and(...)`: **cả hai** điều kiện đều phải đúng.
- `or(...)`: **ít nhất một** điều kiện đúng.
- `negate()`: đảo giá trị đúng/sai của điều kiện.
- `Predicate.not(...)` (Java 11+): cách viết dạng static để phủ định một Predicate, thuận tiện với method reference.

Khi kết hợp, điều quan trọng là hiểu **kiểu của đối tượng được lọc**, **thứ tự đánh giá** và **short-circuit**. Một điều kiện phụ thuộc dữ liệu không-null phải được đặt sau bước kiểm tra null trong một phép kết hợp `and`, nếu không có thể ném ngoại lệ.

## 2. Từ lambda đơn lẻ đến các Predicate có tên

Giả sử ứng dụng quản lý sản phẩm gồm tên, giá và trạng thái còn hàng. Một bộ lọc có thể đặt điều kiện “còn hàng, giá từ 20 đến 60” như sau:

```java
Predicate<Product> inStock = Product::available;
Predicate<Product> minPrice = p -> p.price() >= 20;
Predicate<Product> maxPrice = p -> p.price() <= 60;

Predicate<Product> eligible = inStock.and(minPrice).and(maxPrice);
```

Đây là **đoạn minh họa**, giả sử `Product` là record hoặc lớp có phương thức `available()` và `price()`; cần import `java.util.function.Predicate`.

Kiểu chung của cả bốn biến là `Predicate<Product>`. Mỗi lần gọi `test(product)` trả một giá trị boolean:

```text
eligible(product)
    = inStock(product) && minPrice(product) && maxPrice(product)
```

Phía dùng không cần biết điều kiện được viết bằng lambda, method reference hay một lớp triển khai `Predicate`. Nó chỉ gọi `test` qua hợp đồng.

Bảng chân trị cho hai điều kiện A và B:

| A | B | A AND B | A OR B | NOT A |
| --- | --- | --- | --- | --- |
| false | false | false | false | true |
| false | true | false | true | true |
| true | false | false | true | false |
| true | true | true | true | false |

Đây là logic boolean thông thường, nhưng API `Predicate` còn xác định **khi nào điều kiện thứ hai được gọi**, thông qua short-circuit.

## 3. Ví dụ đầy đủ Java 17+: `and`, `or`, `negate` cùng `Stream.filter`

Lưu tệp `PredicateCompositionDemo.java`:

```java
import java.util.List;
import java.util.function.Predicate;

public class PredicateCompositionDemo {
    record Product(String name, int price, boolean available) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("Pen", 15, true),
                new Product("Book", 40, true),
                new Product("Bag", 80, false),
                new Product("Cable", 60, true)
        );

        Predicate<Product> inStock = Product::available;
        Predicate<Product> minPrice = p -> p.price() >= 20;
        Predicate<Product> maxPrice = p -> p.price() <= 60;

        Predicate<Product> eligible =
                inStock.and(minPrice).and(maxPrice);
        Predicate<Product> unavailable = inStock.negate();
        Predicate<Product> cheapOrUnavailable =
                minPrice.negate().or(unavailable);

        System.out.println("Eligible: " +
                products.stream()
                        .filter(eligible)
                        .map(Product::name)
                        .toList());

        System.out.println("Unavailable: " +
                products.stream()
                        .filter(unavailable)
                        .map(Product::name)
                        .toList());

        System.out.println("Cheap or unavailable: " +
                products.stream()
                        .filter(cheapOrUnavailable)
                        .map(Product::name)
                        .toList());
    }
}
```

Biên dịch/chạy:

```bash
javac PredicateCompositionDemo.java
java PredicateCompositionDemo
```

Kết quả chính xác:

```text
Eligible: [Book, Cable]
Unavailable: [Bag]
Cheap or unavailable: [Pen, Bag]
```

Giải thích từng phép lọc:

- `inStock.and(minPrice).and(maxPrice)` chỉ giữ sản phẩm còn hàng, giá không dưới 20 và không trên 60. `Book` (40) và `Cable` (60) thỏa cả ba.
- `inStock.negate()` giữ sản phẩm có `available() == false`. Chỉ có `Bag`.
- `minPrice.negate().or(unavailable)` có nghĩa “giá dưới 20 **hoặc** hết hàng”. `Pen` (15) và `Bag` (hết hàng) được giữ.
- `Stream.filter` giữ nguyên phần tử đầu vào nếu Predicate trả `true`; nó **không biến phần tử thành boolean**. Sau lọc, `map(Product::name)` chuyển phần tử còn lại thành tên.
- Với stream tuần tự có nguồn §List§ được tạo theo thứ tự trên, `toList()` giữ thứ tự encounter order: các tên được in theo thứ tự trong `products`.

Nếu muốn dùng `Predicate.not(inStock)` thay cho `inStock.negate()` thì kết quả kiểm tra logic cũng là phủ định `inStock.test(product)`.

## 4. Cơ chế short-circuit: điều kiện nào thật sự chạy?

Phương thức default `and` được mô tả bởi quy tắc:

```text
left.and(right).test(x)
    ≈ left.test(x) && right.test(x)
```

Quy tắc `or`:

```text
left.or(right).test(x)
    ≈ left.test(x) || right.test(x)
```

Dấu `≈` biểu thị hành vi tương đương ở mức boolean và thứ tự đánh giá (đây là pseudocode, không phải mã nguồn API). Cụ thể:

- Với `and`, luôn đánh giá Predicate bên trái trước; **nếu trái trả false, không gọi bên phải**.
- Với `or`, luôn đánh giá Predicate bên trái trước; **nếu trái trả true, không gọi bên phải**.
- Với `negate`, gọi Predicate gốc rồi đảo boolean; exception từ Predicate gốc vẫn truyền ra ngoài.
- Không có bảo đảm rằng tất cả Predicate được ghép sẽ chạy cho mọi phần tử. Số lần gọi phụ thuộc nhánh short-circuit.

Các phép kết hợp được tạo thành Predicate mới; phần thân điều kiện chỉ đánh giá khi ứng dụng gọi `test(...)`, hoặc khi terminal operation của Stream thực sự tiêu thụ phần tử.

### Ví dụ log thứ tự thực thi

Tạo `PredicateShortCircuitDemo.java`:

```java
import java.util.function.Predicate;

public class PredicateShortCircuitDemo {
    public static void main(String[] args) {
        Predicate<String> nonNull = s -> {
            System.out.println("check-null: " + s);
            return s != null;
        };
        Predicate<String> longEnough = s -> {
            System.out.println("check-length: " + s);
            return s.length() >= 3;
        };
        Predicate<String> startsJ = s -> {
            System.out.println("starts-J: " + s);
            return s.startsWith("J");
        };
        Predicate<String> containsA = s -> {
            System.out.println("contains-a: " + s);
            return s.contains("a");
        };

        Predicate<String> safeLength = nonNull.and(longEnough);
        System.out.println("null result=" + safeLength.test(null));
        System.out.println("Java result=" + safeLength.test("Java"));
        System.out.println("or result=" +
                startsJ.or(containsA).test("Java"));
    }
}
```

Chạy:

```bash
javac PredicateShortCircuitDemo.java
java PredicateShortCircuitDemo
```

Output:

```text
check-null: null
null result=false
check-null: Java
check-length: Java
Java result=true
starts-J: Java
or result=true
```

Không có log `check-length: null` vì `nonNull.test(null)` trả `false` và `and` dừng. Không có log `contains-a: Java` vì `startsJ.test("Java")` trả `true` và `or` dừng.

Đây cũng là lý do **thứ tự các điều kiện không thể thay tùy tiện khi chúng có phụ thuộc dữ liệu, exception hoặc side effect**. Về logic thuần túy, A AND B có cùng giá trị boolean với B AND A, nhưng thứ tự gọi `test` có thể làm hai cách chạy khác nhau. Cùng nguyên tắc áp dụng cho OR.

## 5. Lọc an toàn khi dữ liệu có thể là `null`

Giả sử danh sách dữ liệu đầu vào có giá trị null, chuỗi trống hoặc chuỗi chỉ chứa khoảng trắng. Muốn chọn các chuỗi khác null, không blank, có chứa “Java” hoặc “Spring”, trước hết phải bảo đảm những phương thức như `isBlank()` và `contains()` chỉ được gọi trên chuỗi không-null.

Mẫu an toàn:

```java
Predicate<String> nonBlank =
        s -> s != null && !s.isBlank();

Predicate<String> aboutJavaOrSpring =
        s -> s.contains("Java") || s.contains("Spring");

Predicate<String> accepted =
        nonBlank.and(aboutJavaOrSpring);
```

Nếu `s == null`, điều kiện `nonBlank` trả false và `aboutJavaOrSpring` không chạy. Nếu viết ngược:

```java
// Cần tránh khi input có thể null:
Predicate<String> unsafe =
        aboutJavaOrSpring.and(nonBlank);
```

thì `unsafe.test(null)` ném `NullPointerException` vì phép `contains(...)` được gọi trước khi kiểm tra null.

### Chương trình Java 17+ với danh sách có null

Lưu `NullSafePredicateDemo.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.function.Predicate;

public class NullSafePredicateDemo {
    public static void main(String[] args) {
        List<String> input = Arrays.asList(
                null, "", "  ", " Java ", "Spring", "Py");

        Predicate<String> nonBlank =
                s -> s != null && !s.isBlank();
        Predicate<String> relevant =
                s -> s.contains("Java") || s.contains("Spring");

        List<String> result = input.stream()
                .filter(nonBlank.and(relevant))
                .map(String::trim)
                .toList();

        System.out.println(result);
    }
}
```

Biên dịch/chạy:

```bash
javac NullSafePredicateDemo.java
java NullSafePredicateDemo
```

Output:

```text
[Java, Spring]
```

Ví dụ dùng `Arrays.asList(...)` vì `List.of(...)` **không chấp nhận phần tử null**. Ở `filter(nonBlank.and(relevant))`, các phần tử null và blank bị loại trước khi `relevant.test(...)` được gọi. Sau đó `map(String::trim)` chỉ tác động lên chuỗi đã được giữ lại.

Nếu không cần tạo Predicate riêng, có thể dùng:

```java
stream.filter(java.util.Objects::nonNull)
      .filter(Predicate.not(String::isBlank));
```

Đây là đoạn pipeline minh họa, giả sử biến `stream` có kiểu `Stream<String>` và đã import `Predicate`. `Predicate.not(String::isBlank)` cần Java 11+. **Phải lọc null trước**; chỉ sử dụng `String::isBlank` trực tiếp trên phần tử null sẽ ném lỗi.

## 6. Ghép Predicate theo thứ tự và dấu ngoặc logic

Với ba điều kiện A, B, C, hai biểu thức sau có ý nghĩa khác nhau:

```text
(A AND B) OR C       khác       A AND (B OR C)
```

Phương thức kết hợp trả về Predicate mới nên có thể mô tả chính xác cấu trúc:

```java
Predicate<Product> first =
        conditionA.and(conditionB).or(conditionC);

Predicate<Product> second =
        conditionA.and(conditionB.or(conditionC));
```

Đây là **đoạn mã minh họa** trong ngữ cảnh ba biến `Predicate<Product>` đã tồn tại.

Do lời gọi phương thức kết hợp theo thứ tự từ trái sang phải, `conditionA.and(conditionB).or(conditionC)` ứng với `(A && B) || C`. Trong khi `conditionA.and(conditionB.or(conditionC))` ứng với `A && (B || C)`.

Ví dụ quy tắc “còn hàng và (giá rẻ hoặc đang khuyến mãi)” nên diễn đạt:

```java
Predicate<Product> eligible =
        available.and(cheap.or(onSale));
```

Không nên viết `available.and(cheap).or(onSale)` nếu **mọi** sản phẩm đều phải còn hàng: biểu thức sau có thể cho phép sản phẩm hết hàng nhưng đang khuyến mãi lọt qua.

Khi kết hợp nhiều `negate()`, nhớ quy tắc De Morgan:

- `!(A && B)` tương đương `!A || !B`.
- `!(A || B)` tương đương `!A && !B`.

Ví dụ `eligible.negate()` có thể dùng để lấy toàn bộ sản phẩm **không thỏa** quy tắc đủ điều kiện. Tuy nhiên một Predicate có tên mang nghĩa phủ định như `notEligible` cần được ghi chú rõ ràng khi điều kiện có nhiều nhánh để tránh đọc ngược ý.

## 7. Dùng nhiều `filter` hay một `filter` với Predicate đã ghép?

Hai phong cách thường gặp:

```java
List<Product> result = products.stream()
        .filter(inStock)
        .filter(minPrice)
        .filter(maxPrice)
        .toList();
```

và:

```java
Predicate<Product> eligible =
        inStock.and(minPrice).and(maxPrice);

List<Product> result = products.stream()
        .filter(eligible)
        .toList();
```

Đây là các đoạn code trong phương thức, giả định biến `products` và các Predicate đã được khai báo đúng kiểu. Với điều kiện **thuần túy, xác định, không side effect**, chúng diễn đạt cùng kết quả: chỉ giữ phần tử vượt qua tất cả điều kiện.

Nhưng lưu ý:

- Dùng nhiều `filter` khi muốn trình bày một pipeline tuyến tính, dễ quan sát mỗi giai đoạn.
- Dùng một `Predicate` đã ghép khi muốn **đặt tên quy tắc nghiệp vụ**, tái sử dụng cho nhiều collection/API, kiểm thử `test(...)` độc lập, hoặc cần biểu diễn OR/NOT phức tạp.
- §filter§ là intermediate operation của Stream: pipeline thường được đánh giá khi có terminal operation như `toList()`, `count()`, `findFirst()`.
- Cả `Predicate.and/or` lẫn `Stream.filter` có thể short-circuit trong những điều kiện thích hợp; đừng gắn side effect vào Predicate rồi mặc định nó sẽ chạy đúng một lần cho mọi phần tử trong mọi pipeline, nhất là pipeline parallel hoặc terminal operation dừng sớm.

Trình biên dịch bảo đảm kiểu tham số của Predicate phù hợp kiểu phần tử Stream. Nó **không** bảo đảm điều kiện nghiệp vụ được viết đúng, không ném exception hay thread-safe. Những điều này cần đánh giá riêng.

## 8. Tách Predicate thành hàm factory tái sử dụng

Khi ứng dụng có các điều kiện tùy chọn từ bộ lọc tìm kiếm, có thể khởi đầu bằng Predicate luôn trả true rồi ghép điều kiện do người dùng cung cấp. Điều này giữ code xây bộ lọc dễ kiểm thử.

Lưu `DynamicPredicateDemo.java`:

```java
import java.util.List;
import java.util.function.Predicate;

public class DynamicPredicateDemo {
    record Employee(String name, String department, int age) {}

    static Predicate<Employee> buildFilter(
            String department, Integer minAge) {
        Predicate<Employee> filter = employee -> true;

        if (department != null && !department.isBlank()) {
            filter = filter.and(
                    employee -> employee.department().equals(department));
        }

        if (minAge != null) {
            filter = filter.and(employee -> employee.age() >= minAge);
        }

        return filter;
    }

    public static void main(String[] args) {
        List<Employee> employees = List.of(
                new Employee("Anna", "Sales", 28),
                new Employee("Binh", "IT", 34),
                new Employee("Chi", "IT", 22),
                new Employee("Dung", "IT", 40)
        );

        Predicate<Employee> itAdults = buildFilter("IT", 30);
        System.out.println(
                employees.stream()
                        .filter(itAdults)
                        .map(Employee::name)
                        .toList());

        Predicate<Employee> all = buildFilter(null, null);
        System.out.println(
                employees.stream()
                        .filter(all)
                        .map(Employee::name)
                        .toList());
    }
}
```

Chạy:

```bash
javac DynamicPredicateDemo.java
java DynamicPredicateDemo
```

Output:

```text
[Binh, Dung]
[Anna, Binh, Chi, Dung]
```

Giải thích:

1. `employee -> true` là điểm xuất phát luôn cho qua phần tử, tương đương giá trị trung hòa của phép AND.
2. Khi có `department` hợp lệ, ghép thêm so sánh phòng ban.
3. Khi có `minAge`, ghép thêm giới hạn tuổi.
4. Kết quả trả về là một `Predicate<Employee>` đã cấu hình xong, có thể truyền vào `filter` hoặc dùng trực tiếp qua `test`.

Các tham số `department` và `minAge` được lambda capture vì chúng là **effectively final** (không bị gán lại trong phương thức). Không cần tạo một class Strategy riêng cho hai điều kiện nhỏ này.

Đây là ví dụ tối giản. Với đầu vào thực tế cần quyết định cách so sánh có phân biệt chữ hoa/thường không, xử lý null trong trường `department()` ra sao, kiểm tra `minAge >= 0` và giới hạn dữ liệu lớn. Nếu `employee.department()` có thể null, biểu thức `employee.department().equals(department)` sẽ ném lỗi; có thể đổi thành `department.equals(employee.department())` sau khi đã xác minh `department != null`, hoặc dùng §Objects.equals§.

## 9. `Predicate.not`, `isEqual` và các dạng viết gọn

### 9.1. `negate()` và `Predicate.not(...)`

Cả hai đều tạo Predicate phủ định. Ví dụ:

```java
Predicate<String> blank = String::isBlank;

Predicate<String> nonBlank1 = blank.negate();
Predicate<String> nonBlank2 = Predicate.not(String::isBlank);
```

Đây là khai báo trong phương thức có import `java.util.function.Predicate`, giả định dữ liệu đầu vào không-null. Hai Predicate đều trả true với chuỗi không blank. `Predicate.not` đặc biệt hữu ích để đặt method reference trực tiếp trong `Stream.filter(...)`, nơi viết `String::isBlank.negate()` không phải cú pháp hợp lệ.

**Không tự động xử lý null:** cả `blank.negate()` lẫn `Predicate.not(String::isBlank)` đều gọi `String.isBlank()` khi kiểm thử. Nếu input có thể null, phải ghép thêm điều kiện null-safe đặt trước.

### 9.2. `Predicate.isEqual(...)`

Factory `Predicate.isEqual(targetRef)` tạo điều kiện so sánh bằng nhau theo quy tắc `Objects.equals(targetRef, input)`, thay vì buộc bạn phải so sánh tham chiếu:

```java
Predicate<String> isJava = Predicate.isEqual("Java");
Predicate<String> isNull = Predicate.isEqual(null);

System.out.println(isJava.test("Java")); // true
System.out.println(isJava.test(null));   // false
System.out.println(isNull.test(null));   // true
```

Đây là đoạn mã nằm trong phương thức. Với đối tượng có `equals` định nghĩa theo giá trị, điều kiện kiểm tra equality theo hợp đồng đó; không nên thay bằng `==` khi mục tiêu là so sánh nội dung. §isEqual(null)§ kiểm tra đầu vào null theo §Objects.equals§.

## 10. Kiểu generic và phối hợp nhiều API nhận Predicate

Một Predicate phải tương thích với kiểu phần tử được kiểm thử. Ví dụ, §Stream<String>.filter(...)§ yêu cầu một đối tượng tương thích với `Predicate<? super String>`. Do contravariance ở tham số đầu vào, Predicate có thể khai báo theo **siêu kiểu** phù hợp:

```java
Predicate<CharSequence> nonEmpty =
        text -> text.length() > 0;

// Hợp lệ: CharSequence là siêu kiểu của String.
List<String> accepted = List.of("A", "", "BB").stream()
        .filter(nonEmpty)
        .toList();
```

Đây là đoạn mã trong phương thức có import `List` và `Predicate`. Kết quả `accepted` là `["A", "BB"]`.

§Predicate<T>.and§ và §or§ nhận `Predicate<? super T>`. Vì thế có thể kết hợp một điều kiện khai báo trên siêu kiểu với điều kiện của kiểu phần tử cụ thể khi quan hệ kiểu phù hợp, mà không cần cast thô. Khi compiler báo lỗi, hãy xem lại hướng quan hệ kiểu, không ép kiểu không an toàn chỉ để làm cho chương trình biên dịch.

Các API phổ biến nhận Predicate: `Stream.filter(Predicate<? super T>)`, `Collection.removeIf(Predicate<? super E>)`, các thao tác tìm kiếm như `anyMatch`, `allMatch`, `noneMatch` trên Stream. Dù cùng nhận Predicate, ý nghĩa khác nhau:

- `filter(p)` giữ phần tử khi `p.test(x)` đúng.
- `removeIf(p)` **xóa** phần tử khỏi collection có thể thay đổi khi `p.test(x)` đúng.
- `anyMatch(p)` trả boolean và có thể dừng khi tìm thấy phần tử thỏa.
- `allMatch(p)` có thể dừng khi gặp phần tử không thỏa; trên stream rỗng trả true.
- `noneMatch(p)` có thể dừng khi gặp phần tử thỏa; trên stream rỗng trả true.

Nhất là với `anyMatch/allMatch/noneMatch`, các phép kiểm tra có thể dừng sớm, nên **không dùng số lần gọi Predicate như một cơ chế đếm phần tử đáng tin**.

## 11. Predicate cho primitive và vấn đề boxing

Nếu lọc số nguyên, `Predicate<Integer>` hoạt động nhưng có thể kéo theo boxing/unboxing khi kết hợp với primitive. Java có các functional interface chuyên cho primitive như `IntPredicate`, `LongPredicate` và `DoublePredicate`, cũng hỗ trợ `and`, `or`, `negate` với kiểu primitive tương ứng.

Ví dụ Java 17+:

```java
import java.util.function.IntPredicate;
import java.util.stream.IntStream;

public class IntPredicateDemo {
    public static void main(String[] args) {
        IntPredicate positive = n -> n > 0;
        IntPredicate even = n -> n % 2 == 0;

        System.out.println(
                IntStream.of(-2, 0, 1, 2, 3, 4)
                        .filter(positive.and(even))
                        .boxed()
                        .toList());
    }
}
```

Chạy:

```bash
javac IntPredicateDemo.java
java IntPredicateDemo
```

Output:

```text
[2, 4]
```

§IntStream.filter§ nhận `IntPredicate`, vì vậy đối số kiểm thử là `int` thay vì `Integer`. §boxed()§ ở ví dụ chỉ dùng để chuyển kết quả thành stream boxed cho §toList()§ khi hiển thị, không phải điều kiện để thực hiện phép lọc.

## 12. Exception, side effect, trạng thái và đồng thời

Predicate tốt nhất cho lọc thường là **stateless**, không sửa đổi nguồn dữ liệu và trả cùng kết quả cho cùng đầu vào trong một ngữ cảnh ổn định. Java không bắt buộc Predicate phải thuần túy, nhưng kết hợp Predicate có side effect làm code khó dự đoán:

- Nếu Predicate trái của `and` trả false, Predicate phải không chạy.
- Nếu Predicate trái của `or` trả true, Predicate phải không chạy.
- Nếu Predicate ném unchecked exception, exception truyền khỏi `test` và có thể làm terminal operation thất bại.
- §Predicate.test§ không khai báo checked exception. Với API ném checked exception như §IOException§, phải xử lý theo đúng hợp đồng hoặc thiết kế một abstraction khác; không thể để lambda ném checked exception chưa xử lý rồi gán trực tiếp cho `Predicate<T>`.
- Với parallel stream, điều kiện lọc có thể được thực thi đồng thời trên nhiều phần tử. Tránh ghi vào collection mutable không đồng bộ, thay đổi biến đếm không an toàn hoặc phụ thuộc thứ tự in log.
- Khi dữ liệu hoặc điều kiện có trạng thái thay đổi, việc sắp xếp lại Predicate có thể thay đổi output và số lượng side effect. Hãy đảm bảo điều kiện có ngữ nghĩa rõ trước khi tối ưu thứ tự.

Không cần tối ưu chi phí bằng cách bỏ điều kiện rẻ/tốn trước một cách máy móc. Khi các Predicate có phụ thuộc (chẳng hạn null-check trước `String::length`), **độ an toàn và đúng đắn của thứ tự luôn là ràng buộc bắt buộc**. Chỉ khi các điều kiện độc lập, thuần túy, có thể hoán đổi mới nên cân nhắc đưa điều kiện dễ loại bỏ phần tử và chi phí thấp lên đầu, rồi đo thực tế nếu cần.

## 13. Lỗi thường gặp khi kết hợp điều kiện lọc

1. **Đặt điều kiện cần dữ liệu khác null trước null-check.** Ví dụ `s -> s.length() > 2` chạy trên null sẽ ném lỗi; dùng `nonNull.and(longEnough)` theo đúng thứ tự.
2. **Nhầm `and` với `or`.** “Còn hàng và (rẻ hoặc khuyến mãi)” phải dùng `available.and(cheap.or(onSale))`.
3. **Bỏ qua dấu ngoặc kết hợp.** `A.and(B).or(C)` không tương đương `A.and(B.or(C))`.
4. **Tưởng Predicate bên phải luôn chạy.** `and/or` short-circuit; không dùng điều kiện bên phải để ghi audit bắt buộc cho mọi phần tử.
5. **Chỉ định kiểu lambda quá chung hoặc dùng raw type.** Nên khai báo `Predicate<Product>` và tên điều kiện rõ ràng; để compiler phát hiện lỗi kiểu.
6. **Nhầm `filter(p)` với `removeIf(p)`.** Một bên giữ phần tử thỏa trên stream; bên kia xóa phần tử thỏa trên collection mutable.
7. **Dùng §==§ để so sánh nội dung String.** Ưu tiên `Objects.equals` hoặc `Predicate.isEqual(value)` theo nhu cầu so sánh giá trị.
8. **Dùng `Predicate.not(String::isBlank)` trực tiếp trên nguồn có thể null.** Phủ định không thay thế null-guard.
9. **Cho rằng `filter` chạy ngay khi nối pipeline.** Stream intermediate operation thường lazy và cần terminal operation. Việc tạo Predicate mới cũng không đồng nghĩa đã gọi `test`.
10. **Dựa vào thứ tự side effect khi dùng parallel stream.** Hãy giữ Predicate không trạng thái và an toàn khi thực thi đồng thời.
11. **Nối Predicate khác kiểu thiếu quan hệ.** Một §Predicate<Employee>§ không thể dùng trực tiếp để lọc §Stream<Product>§.
12. **Nhầm kết quả boolean với dữ liệu sau lọc.** §filter§ không biến phần tử thành boolean; nó giữ hoặc loại chính đối tượng đầu vào.

## 14. Bài tập tự kiểm tra

Cho danh sách:

```java
List<Integer> numbers = List.of(-3, -2, 0, 1, 2, 3, 4, 8);
Predicate<Integer> positive = n -> n > 0;
Predicate<Integer> even = n -> n % 2 == 0;
Predicate<Integer> underFive = n -> n < 5;
```

Các đoạn trên được viết trong một phương thức và cần import `List`, `Predicate`.

Hãy tự dự đoán:

1. `numbers.stream().filter(positive.and(even)).toList()` trả gì?
2. `numbers.stream().filter(positive.and(even.or(underFive))).toList()` trả gì?
3. Kết quả của `numbers.stream().filter(positive.and(even).negate()).toList()`?
4. Nếu thay `positive.and(even)` thành `even.and(positive)` trên danh sách số nguyên này, kết quả boolean khác không? Điều gì có thể khác khi hai Predicate có side effect?
5. Với §Predicate<String> nonNull = Objects::nonNull§ và §Predicate<String> startsJ = s -> s.startsWith("J")§, cách ghép nào cho phép §test(null)§ an toàn: `nonNull.and(startsJ)` hay `startsJ.and(nonNull)`?

**Đáp án:**

1. `[2, 4, 8]` vì đó là các số dương chẵn.
2. `[1, 2, 3, 4, 8]`: số dương và (chẵn hoặc nhỏ hơn 5); 8 thỏa nhánh chẵn.
3. `[-3, -2, 0, 1, 3]`: phủ định điều kiện “dương và chẵn”.
4. Cùng kết quả boolean vì hai điều kiện thuần túy trên số nguyên. Khi Predicate có side effect, thứ tự gọi và số lần gọi có thể khác do short-circuit.
5. `nonNull.and(startsJ)` an toàn với null: `nonNull` trả false nên `startsJ` không chạy.

## 15. Quy tắc thực hành

Khi xây bộ lọc, hãy diễn đạt mỗi điều kiện bằng **một Predicate có tên rõ ràng**, sau đó ghép thành một biểu thức boolean phản ánh chính xác yêu cầu:

```text
giữ phần tử = (đúng kiểu/không null)
              AND (thỏa điều kiện nghiệp vụ A)
              AND (B OR C)
              AND NOT (trạng thái bị cấm)
```

Đối với Stream, dùng `filter(composedPredicate)` để giữ các phần tử phù hợp; dùng `test(value)` khi kiểm thử một giá trị riêng lẻ. Đọc phép kết hợp từ trái sang phải với ý thức về short-circuit, kiểm tra kiểu generic, bảo vệ dữ liệu null trước khi truy cập, và tránh side effect trong các điều kiện có thể không được gọi.

**Tham khảo:** Java SE API `java.util.function.Predicate` (§test§, §and§, §or§, §negate§, §not§, §isEqual§); `java.util.stream.Stream.filter§; `java.util.function.IntPredicate`; Java Language Specification về lambda, functional interface và short-circuit boolean operators.