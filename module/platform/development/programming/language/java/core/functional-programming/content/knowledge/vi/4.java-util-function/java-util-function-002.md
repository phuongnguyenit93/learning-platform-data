# Predicate<T> cho điều kiện đúng hoặc sai trong Java

**`Predicate<T>`** là functional interface trong gói `java.util.function`, đại diện cho một phép kiểm tra điều kiện trên đối tượng kiểu `T`. Phương thức trung tâm `boolean test(T value)` trả về `true` hoặc `false`. Predicate giúp truyền quy tắc kiểm tra như dữ liệu: có thể gán vào biến, nhận làm tham số, kết hợp thành điều kiện lớn hơn và dùng trong xử lý tập hợp hoặc Stream.

Ví dụ, quy tắc “chuỗi không rỗng”, “giá không quá 300”, “đối tượng hợp lệ” đều có thể được biểu diễn bằng một Predicate. Điểm mạnh của cách viết này là **tách logic kiểm tra khỏi nơi sử dụng logic**, để cùng một quy tắc có thể được tái sử dụng.

Sau bài học, bạn có thể:
- Định nghĩa và gọi một `Predicate<T>` bằng lambda hoặc method reference.
- Kết hợp các điều kiện bằng `and`, `or`, `negate`, `Predicate.not`, `isEqual` và hiểu cơ chế đoản mạch.
- Dùng Predicate với `Stream.filter`, `anyMatch`, `allMatch`, `noneMatch` và các ví dụ xác định.
- Tránh lỗi null, side effect, quy tắc khó đọc và chọn đúng giữa `Predicate<T>`, `Function<T, Boolean>`, `BiPredicate<T,U>`, `IntPredicate` cùng các interface liên quan.

## 1. Hợp đồng và ý nghĩa của Predicate<T>

Có thể hình dung phần quan trọng của interface như sau:

```java
@FunctionalInterface
public interface Predicate<T> {
    boolean test(T value);
    // Ngoài ra còn các phương thức kết hợp mặc định và static.
}
```

Đây là **bản rút gọn để giải thích**, không phải bản sao đầy đủ khai báo JDK. `@FunctionalInterface` cho phép lambda làm implementation của phương thức trừu tượng duy nhất `test`.

- `T` là kiểu đầu vào, chẳng hạn `String`, `Integer`, `Customer` hay `Product`.
- `test(T value)` nhận một giá trị và trả về **primitive `boolean`**. Không có kết quả `null`.
- Kết quả `true` nghĩa là điều kiện do người viết quy định được thỏa; `false` nghĩa là không thỏa.
- `Predicate` chỉ định nghĩa **hợp đồng nhận một giá trị và trả boolean**; nó không tự kiểm tra null, không bảo đảm hàm thuần, không lưu cache và không bảo đảm an toàn luồng.

Cách khai báo phổ biến:

```java
Predicate<Integer> positive = n -> n > 0;
Predicate<String> startsWithJ = text -> text.startsWith("J");
Predicate<String> blank = String::isBlank;
```

Ba dòng trên là **mảnh mã minh họa** cần `import java.util.function.Predicate;` và đặt trong một phương thức hoặc ngữ cảnh khai báo phù hợp. Lambda `n -> n > 0` nhận một `Integer` rồi trả boolean; method reference `String::isBlank` có chữ ký tương thích với `String -> boolean`.

**Lưu ý về generic:** `Predicate<Integer>` nhận đối tượng `Integer`; toán tử `>` dùng unboxing để so sánh số. Đối với luồng số nguyên lớn, `IntPredicate` có thể tránh boxing/unboxing.

## 2. Ví dụ đầy đủ: gọi test và xử lý null

Lưu thành **`PredicateBasicsDemo.java`**:

```java
import java.util.function.Predicate;

public class PredicateBasicsDemo {
    public static void main(String[] args) {
        Predicate<String> hasText =
                text -> text != null && !text.isBlank();

        Predicate<String> startsWithJ =
                text -> text != null && text.startsWith("J");

        System.out.println("Java có chữ: " + hasText.test("Java"));
        System.out.println("Khoảng trắng có chữ: " + hasText.test("   "));
        System.out.println("null có chữ: " + hasText.test(null));
        System.out.println("Java bắt đầu J: " + startsWithJ.test("Java"));
        System.out.println("Kotlin bắt đầu J: " + startsWithJ.test("Kotlin"));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 PredicateBasicsDemo.java
java PredicateBasicsDemo
```

**Stdout chính xác:**

```text
Java có chữ: true
Khoảng trắng có chữ: false
null có chữ: false
Java bắt đầu J: true
Kotlin bắt đầu J: false
```

`text != null && !text.isBlank()` dùng toán tử `&&` đoản mạch: khi `text == null`, vế `isBlank()` không được gọi. Điều này làm predicate xử lý được đầu vào null theo chủ đích. Ngược lại, `String::isBlank` khi được gọi với null có thể gây `NullPointerException`, vì cần gọi instance method trên đối tượng.

Mỗi lần gọi `test(...)` là **một lần đánh giá điều kiện**. Việc gán lambda vào biến không tự chạy `test`; gọi lại `test` có thể chạy lại toàn bộ logic.

## 3. Ghép các Predicate bằng and, or và negate

`Predicate<T>` có các default methods xây dựng Predicate mới:

| Phương thức | Kết quả | Điều kiện đánh giá |
| --- | --- | --- |
| `p.and(q)` | Đúng khi cả `p` và `q` đúng | Gọi `p.test(x)` trước; chỉ gọi `q.test(x)` khi `p` đúng. |
| `p.or(q)` | Đúng khi ít nhất một điều kiện đúng | Gọi `p.test(x)` trước; chỉ gọi `q.test(x)` khi `p` sai. |
| `p.negate()` | Phủ định kết quả của `p` | Trả kết quả logic đối lập khi được gọi. |

Ví dụ:

```java
Predicate<Integer> atLeast18 = age -> age >= 18;
Predicate<Integer> atMost65 = age -> age <= 65;
Predicate<Integer> workingAge = atLeast18.and(atMost65);

boolean ok = workingAge.test(25); // true
boolean tooYoung = atLeast18.negate().test(16); // true
```

Đây là mảnh mã minh họa. `and`, `or`, `negate` **trả về Predicate mới**, không sửa đối tượng Predicate gốc. Có thể tái sử dụng `atLeast18` và `atMost65` riêng rẽ sau khi tạo `workingAge`.

Các phương thức `and` và `or` là **đoản mạch khi gọi `test`**; điều này quan trọng nếu vế sau đắt đỏ hoặc chỉ an toàn khi vế trước đúng. Chẳng hạn:

```java
Predicate<String> nonNull = text -> text != null;
Predicate<String> longText = text -> text.length() >= 5;
Predicate<String> safeLongText = nonNull.and(longText);
boolean result = safeLongText.test(null); // false, không gọi longText
```

**Phân biệt thời điểm tạo Predicate và thời điểm gọi `test`:** biểu thức đối số `q` trong `p.and(q)` được đánh giá khi gọi `and` theo quy tắc Java. Tuy nhiên `q.test(value)` chỉ được gọi khi Predicate kết hợp được thực thi và điều kiện đoản mạch cho phép.

Khi `other` là null, `p.and(null)` và `p.or(null)` ném `NullPointerException` ngay lúc tạo phép kết hợp.

## 4. Ví dụ chạy được: quan sát thứ tự đoản mạch

Lưu thành **`PredicateShortCircuitDemo.java`**:

```java
import java.util.function.Predicate;

public class PredicateShortCircuitDemo {
    public static void main(String[] args) {
        Predicate<String> longEnough = text -> {
            System.out.println("Kiểm tra độ dài: " + text);
            return text.length() >= 4;
        };

        Predicate<String> startsJ = text -> {
            System.out.println("Kiểm tra chữ J: " + text);
            return text.startsWith("J");
        };

        Predicate<String> rule = longEnough.and(startsJ);

        System.out.println("Hi: " + rule.test("Hi"));
        System.out.println("Java: " + rule.test("Java"));
    }
}
```

Lệnh chạy:

```bash
javac -encoding UTF-8 PredicateShortCircuitDemo.java
java PredicateShortCircuitDemo
```

**Stdout chính xác:**

```text
Kiểm tra độ dài: Hi
Hi: false
Kiểm tra độ dài: Java
Kiểm tra chữ J: Java
Java: true
```

Với `"Hi"`, `longEnough` trả false nên `startsJ` không chạy. Với `"Java"`, vế trái đúng nên vế phải tiếp tục được kiểm tra.

Đối với `p.or(q)`, quy tắc ngược lại: khi `p` đã trả true, Java bỏ qua `q.test(x)`. Đối với `p.negate()`, kết quả sau khi kiểm tra được đảo từ true sang false hoặc ngược lại. **Không nên viết test hoặc ghi dữ liệu phụ thuộc vào số lần các predicate phụ được gọi** nếu số lần đó không phải hợp đồng nghiệp vụ; short-circuit có thể khiến một số predicate không chạy.

## 5. Predicate.not và Predicate.isEqual

Bên cạnh default methods, `Predicate` có static methods hữu ích.

### 5.1. Predicate.not

Từ Java 11, `Predicate.not(Predicate<? super T> target)` tạo Predicate phủ định. Cách này đặc biệt gọn với method reference:

```java
List<String> nonBlank = java.util.List.of("Java", "", "Stream")
        .stream()
        .filter(java.util.function.Predicate.not(String::isBlank))
        .toList();
// nonBlank = [Java, Stream]
```

Đây là mảnh mã minh họa; `toList()` có từ Java 16 nên chạy trên Java 17+. `Predicate.not(String::isBlank)` tương đương ý định với `((Predicate<String>) String::isBlank).negate()`, nhưng không cần ép kiểu rườm rà trong vị trí `filter`.

`Predicate.not` không tự làm method reference null-safe: nếu Stream chứa null, lời gọi `String::isBlank` vẫn có thể ném ngoại lệ. Muốn loại null trước, dùng `filter(java.util.Objects::nonNull)` rồi mới kiểm tra `isBlank`.

### 5.2. Predicate.isEqual

`Predicate.isEqual(targetRef)` tạo Predicate kiểm tra giá trị đầu vào bằng `targetRef` theo ngữ nghĩa `Objects.equals`:

```java
Predicate<String> isJava = Predicate.isEqual("Java");
boolean exact = isJava.test("Java");    // true
boolean other = isJava.test("Kotlin");  // false

Predicate<String> isNull = Predicate.isEqual(null);
boolean missing = isNull.test(null);    // true
```

Đây là mảnh mã minh họa với `import java.util.function.Predicate;`. `isEqual` là so sánh **bằng nhau theo `equals`**, không phải so sánh đồng nhất tham chiếu bằng `==`. Phương thức này phù hợp khi muốn biểu diễn “khớp với giá trị cố định”, kể cả null, mà không phải tự viết lambda.

## 6. Predicate trong Stream: filter và các terminal operations

Các API Stream nhận Predicate ở nhiều vị trí:

| API | Vai trò của Predicate | Kiểu kết quả |
| --- | --- | --- |
| `filter(predicate)` | Giữ phần tử có `test` trả true. | Một `Stream<T>` mới. |
| `anyMatch(predicate)` | Có ít nhất một phần tử thỏa? | `boolean`. |
| `allMatch(predicate)` | Tất cả phần tử đều thỏa? | `boolean`. |
| `noneMatch(predicate)` | Không phần tử nào thỏa? | `boolean`. |
| `takeWhile(predicate)` | Lấy tiền tố liên tiếp còn thỏa điều kiện, theo encounter order nếu có. | Một `Stream<T>` mới. |
| `dropWhile(predicate)` | Bỏ tiền tố liên tiếp còn thỏa điều kiện, theo encounter order nếu có. | Một `Stream<T>` mới. |

`filter`, `takeWhile`, `dropWhile` là **intermediate operations** nên chỉ tạo pipeline, chưa tự duyệt toàn bộ nguồn. `anyMatch`, `allMatch`, `noneMatch` là **terminal operations**, có thể dừng sớm nếu đã xác định được kết quả.

Trên Stream rỗng, `anyMatch` là **false**, còn `allMatch` và `noneMatch` đều là **true**. Hai kết quả sau là các trường hợp “đúng một cách hiển nhiên” do không có phần tử nào làm điều kiện thất bại; đừng nhầm với việc đã tìm thấy dữ liệu hợp lệ.

### Ví dụ Java 17: lọc sản phẩm theo nhiều điều kiện

Lưu thành **`PredicateStreamDemo.java`**:

```java
import java.util.List;
import java.util.function.Predicate;

public class PredicateStreamDemo {
    record Product(String name, String category, int price, boolean available) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("Java Book", "Book", 250, true),
                new Product("USB", "Tech", 120, true),
                new Product("Notebook", "Book", 80, false),
                new Product("Clean Code", "Book", 320, true)
        );

        Predicate<Product> isBook =
                product -> "Book".equals(product.category());
        Predicate<Product> affordable =
                product -> product.price() <= 300;
        Predicate<Product> inStock = Product::available;

        Predicate<Product> eligible =
                isBook.and(affordable).and(inStock);

        List<String> names = products.stream()
                .filter(eligible)
                .map(Product::name)
                .toList();

        System.out.println("Đủ điều kiện: " + names);
        System.out.println("Có sản phẩm phù hợp: "
                + products.stream().anyMatch(eligible));
        System.out.println("Không phải sách: "
                + products.stream()
                        .filter(isBook.negate())
                        .map(Product::name)
                        .toList());
        System.out.println("Danh mục khớp: "
                + Predicate.isEqual("Book").test(products.get(0).category()));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 PredicateStreamDemo.java
java PredicateStreamDemo
```

**Stdout chính xác:**

```text
Đủ điều kiện: [Java Book]
Có sản phẩm phù hợp: true
Không phải sách: [USB]
Danh mục khớp: true
```

Giải thích:
1. `isBook`, `affordable`, `inStock` độc lập; `eligible` yêu cầu thỏa cả ba điều kiện.
2. “Java Book” là sách, giá 250 và còn hàng nên được giữ lại.
3. “Notebook” là sách và giá thấp nhưng `available == false`; “Clean Code” còn hàng nhưng giá 320 vượt 300.
4. “USB” không phải sách, xuất hiện trong kết quả `isBook.negate()`.
5. `anyMatch(eligible)` trả true vì có ít nhất một sản phẩm phù hợp. Terminal này **có thể dừng sớm**, khác với việc duyệt và thu thập mọi phần tử phù hợp bằng `toList()`.

Ví dụ dùng `record` (được hỗ trợ chính thức từ Java 16), `List.of` và `Stream.toList` nên phù hợp với Java 17.

## 7. Độ thuần của predicate, hiệu năng và tính dễ bảo trì

### Ưu tiên điều kiện không có side effect

Thông thường, Predicate nên chỉ đọc đầu vào rồi tính toán `boolean`. Ví dụ `p -> p.price() <= limit` dễ dự đoán hơn một predicate vừa kiểm tra vừa ghi log, sửa collection, tăng biến đếm hoặc gọi dịch vụ ngoài.

Có thể viết predicate có side effect, nhưng cần cân nhắc kỹ: trong Stream, pipeline lazy, terminal operation có thể dừng sớm; với parallel stream, lời gọi có thể chạy trên nhiều thread, thứ tự không chắc chắn. Vì vậy không được lấy số lần gọi Predicate làm thay thế cho logic ghi nhận bắt buộc. Khi cần xử lý từng phần tử với side effect, hãy thiết kế luồng xử lý minh bạch và sử dụng terminal operation phù hợp.

### Đặt thứ tự điều kiện phù hợp

Trong `cheap.and(expensive)`, nếu `cheap` trả false, `expensive` không chạy. Đặt phép kiểm tra rẻ, an toàn và có khả năng loại nhanh ở trước thường giúp tiết kiệm công việc, **nếu đổi thứ tự vẫn giữ nguyên ngữ nghĩa**. Khi các predicate có side effect hoặc có thể ném ngoại lệ, đổi thứ tự có thể thay đổi hành vi quan sát được.

```java
Predicate<String> safe = text -> text != null;
Predicate<String> containsJava = text -> text.contains("Java");
Predicate<String> valid = safe.and(containsJava);
```

Trong mảnh mã minh họa này, `safe` phải ở trước để tránh gọi `contains` trên null. Một predicate chỉ trả false chứ không báo lý do thất bại; nếu nghiệp vụ cần nhiều thông báo lỗi, nên dùng mô hình kết quả validation giàu thông tin hơn.

### Phạm vi dữ liệu đóng trong lambda

```java
int minLength = 5;
Predicate<String> longEnough = value -> value.length() >= minLength;
```

Biến local `minLength` được lambda capture và phải là **final hoặc effectively final** (không gán lại sau khi khởi tạo). Nếu capture một đối tượng mutable, nội dung đối tượng đó vẫn có thể thay đổi; bản thân functional interface không bảo đảm bất biến hoặc thread-safe.

### Ngoại lệ

`Predicate.test(T)` không khai báo checked exception. Nếu lambda gọi phương thức ném checked exception, bạn cần xử lý hoặc chuyển đổi lỗi theo thiết kế; không thể đơn giản khai báo lambda ném một checked exception không được phép bởi target type. Runtime exception vẫn có thể lan ra khi gọi `test`.

## 8. Khi nào dùng Predicate và khi nào dùng interface khác?

| Interface | Functional method | Trường hợp phù hợp |
| --- | --- | --- |
| `Predicate<T>` | `boolean test(T)` | Kiểm tra một đối tượng đúng/sai. |
| `BiPredicate<T,U>` | `boolean test(T,U)` | Kiểm tra quan hệ giữa hai đầu vào. |
| `IntPredicate` | `boolean test(int)` | Kiểm tra `int` không cần boxing. |
| `LongPredicate` | `boolean test(long)` | Kiểm tra `long` nguyên thủy. |
| `DoublePredicate` | `boolean test(double)` | Kiểm tra `double` nguyên thủy. |
| `Function<T,R>` | `R apply(T)` | Chuyển một giá trị sang kết quả kiểu bất kỳ. |
| `Consumer<T>` | `void accept(T)` | Thực hiện hành động không trả kết quả. |
| `Supplier<T>` | `T get()` | Cung cấp một giá trị khi được gọi. |

`Function<T, Boolean>` cũng có thể biểu diễn phép kiểm tra nhưng trả về `Boolean` dạng wrapper, có thể null. Khi mục tiêu là điều kiện đúng/sai, `Predicate<T>` truyền đạt ý định rõ hơn, trả về primitive `boolean` và có sẵn các phép kết hợp logic.

Ví dụ kiểm tra hai đối tượng:

```java
java.util.function.BiPredicate<String, String> sameLength =
        (left, right) -> left.length() == right.length();
boolean equal = sameLength.test("Java", "Kotlin"); // false
```

Với số nguyên:

```java
java.util.function.IntPredicate positive = number -> number > 0;
boolean ok = positive.test(42); // true
```

Hai đoạn là mã minh họa đặt trong phương thức. Các kiểu chuyên biệt hỗ trợ `and`, `or`, `negate` tương tự Predicate tổng quát nhưng không cần ép kiểu boxed cho đầu vào nguyên thủy.

## 9. Các sai lầm thường gặp

1. **Nhầm Predicate với giá trị boolean:** `Predicate<String> p` là quy tắc; muốn biết kết quả cho một đầu vào, gọi `p.test(input)`.
2. **Cho rằng `Predicate<T>` tự xử lý null:** các lambda dereference giá trị null sẽ ném `NullPointerException` nếu không có kiểm tra trước.
3. **Viết `p.and(q)` rồi quên gán kết quả:** phép kết hợp tạo Predicate mới; nó không cập nhật `p`.
4. **Nhầm thứ tự thực thi của `and`/`or`:** vế trái được kiểm tra trước và có thể bỏ qua vế phải.
5. **Đưa công việc bắt buộc vào Predicate của Stream:** terminal có thể xử lý ít phần tử hơn dự đoán; tránh side effect để bảo đảm kết quả ổn định.
6. **Nhầm `allMatch` trên Stream rỗng trả false:** thực tế `allMatch` và `noneMatch` đều trả true cho Stream rỗng.
7. **Dùng `String::isBlank` trực tiếp với dữ liệu có null:** method reference không có xử lý null tự động.
8. **Tạo một Predicate khổng lồ khó đọc:** tách thành các predicate có tên, kết hợp bằng `and`/`or`, và kiểm thử từng quy tắc.
9. **Dùng `Function<T, Boolean>` khi API yêu cầu `Predicate<T>`:** đây là hai interface khác nhau; method `apply` không thay thế trực tiếp `test` nếu không có adapter.
10. **Cho rằng thứ tự gọi predicate luôn giữ nguyên khi chạy song song:** thread và thứ tự duyệt có thể khác; chỉ dựa vào kết quả logic khi các predicate phù hợp với yêu cầu không can thiệp của Stream.

## 10. Tự kiểm tra và bài tập

**Câu 1.** Kết quả của `((Predicate<Integer>) n -> n > 10).test(10)` là gì? **False**, vì 10 không lớn hơn 10.

**Câu 2.** `Predicate<String> p = s -> s != null; Predicate<String> q = s -> s.length() > 3;` thì `p.and(q).test(null)` có ném ngoại lệ không? **Không**: `p.test(null)` trả false, nên `q` không được gọi.

**Câu 3.** Stream rỗng dùng `anyMatch(x -> true)`, `allMatch(x -> false)`, `noneMatch(x -> true)` trả gì? Lần lượt **false**, **true**, **true**.

**Câu 4.** Nếu cần lọc tên không rỗng và bắt đầu bằng “J”, có thể viết thế nào?

```java
Predicate<String> usable = name -> name != null && !name.isBlank();
Predicate<String> beginsJ = name -> name.startsWith("J");
Predicate<String> accepted = usable.and(beginsJ);
```

Đây là mảnh mã minh họa dùng `java.util.function.Predicate`. Thử `accepted.test("Java")` được true; `accepted.test(null)` được false mà không ném ngoại lệ.

**Câu 5.** Nếu predicate trả `false`, API có cho biết *vì sao* thất bại không? **Không.** Đầu ra chỉ là `boolean`. Khi cần lỗi chi tiết, trả một kết quả kiểm tra riêng thay cho việc cố nhồi thông báo vào side effect của predicate.

**Ghi nhớ:** `Predicate<T>` là một **quy tắc kiểm tra kiểu `T -> boolean`**, có thể truyền vào API và kết hợp bằng các phép logic. Hãy viết điều kiện rõ nghĩa, an toàn với dữ liệu đầu vào và phù hợp với cơ chế đoản mạch khi thực thi.