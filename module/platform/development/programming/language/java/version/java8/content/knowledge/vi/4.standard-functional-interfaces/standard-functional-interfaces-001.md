# Predicate và biểu diễn điều kiện trong Java

## 1. Predicate là gì?

Trong Java, **`Predicate<T>`** là functional interface chuẩn của gói `java.util.function`, biểu diễn một **điều kiện đúng/sai áp dụng cho giá trị kiểu T**. Hợp đồng chức năng (SAM) của nó là:

~~~java
boolean test(T value);
~~~

Một `Predicate<Product>` có thể trả lời “sản phẩm này còn hàng không?”, `Predicate<String>` trả lời “chuỗi này có hợp lệ theo quy tắc đang xét không?”, và `Predicate<Integer>` trả lời “số này có lớn hơn 0 không?”. Khi truyền predicate cho phương thức, ta truyền **quy tắc kiểm tra**; phương thức nhận được phép chọn thời điểm và số lần gọi `test`.

Ví dụ tối giản (mảnh mã đặt bên trong một phương thức):

~~~java
java.util.function.Predicate<Integer> positive = n -> n > 0;

System.out.println(positive.test(12)); // true
System.out.println(positive.test(-2)); // false
~~~

Trong `n -> n > 0`, `n` là đối số đầu vào và `n > 0` tạo ra giá trị `boolean`. Kiểu `Integer` của `n` được suy ra từ kiểu đích `Predicate<Integer>`. Với kiểu tổng quát `T`, descriptor dễ hiểu của predicate là `(T) -> boolean`; sau khi chỉ định `T = Integer`, nó thành `(Integer) -> boolean`.

**Điều cần nhớ:** Java không có giá trị chân lý ngầm cho chuỗi hay số như một số ngôn ngữ khác. Phần thân predicate phải tạo ra kết quả kiểu `boolean` (có thể qua biểu thức trả `Boolean` rồi unboxing, nhưng nên tránh khả năng `null`). Một lambda như `n -> n + 1` không thể dùng làm `Predicate<Integer>`.

`Predicate` được giới thiệu từ Java 8 và vẫn là cách tiêu chuẩn để biểu diễn điều kiện trong Java hiện đại, đặc biệt với Collection, Stream, Optional và các API nhận callback.

## 2. Khi nào nên truyền điều kiện thay vì viết nhiều phương thức?

Hãy hình dung một danh sách sản phẩm và các yêu cầu:

- Lấy những sản phẩm có giá từ 100 trở lên.
- Lấy sản phẩm đang có hàng.
- Lấy sản phẩm **vừa** có giá từ 100 trở lên **vừa** có hàng.
- Lấy sản phẩm thỏa **ít nhất một** trong hai điều kiện trên.

Nếu sao chép vòng lặp lọc thành nhiều phương thức, ta sẽ lặp lại phần duyệt danh sách và tạo danh sách kết quả. Có thể dùng `Predicate<Product>` để tách **quy trình lọc cố định** ra khỏi **điều kiện thay đổi**:

~~~text
filter(products, predicate)
    |
    +-- duyệt lần lượt từng phần tử
    +-- predicate.test(product) -> true/false
    +-- true: giữ phần tử; false: bỏ qua
~~~

Một phương thức nhận `Predicate<? super T>` có thể nhận nhiều quy tắc cho cùng kiểu phần tử, bao gồm cả predicate xử lý kiểu cha của `T`. Người gọi có thể viết lambda, truyền method reference hoặc kết hợp predicate có sẵn; việc dùng predicate **không yêu cầu tạo interface riêng cho mỗi điều kiện**.

## 3. Ví dụ chạy đầy đủ: lọc một danh sách bằng các điều kiện khác nhau

Tạo tệp **PredicateProductDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.function.Predicate;

public class PredicateProductDemo {
    static final class Product {
        private final String name;
        private final int price;
        private final boolean available;

        Product(String name, int price, boolean available) {
            this.name = name;
            this.price = price;
            this.available = available;
        }

        String getName() {
            return name;
        }

        int getPrice() {
            return price;
        }

        boolean isAvailable() {
            return available;
        }
    }

    static <T> List<T> filter(
            List<T> source, Predicate<? super T> criterion) {
        Objects.requireNonNull(source, "source");
        Objects.requireNonNull(criterion, "criterion");

        List<T> matches = new ArrayList<>();
        for (T item : source) {
            if (criterion.test(item)) {
                matches.add(item);
            }
        }
        return matches;
    }

    static List<String> names(List<Product> products) {
        List<String> result = new ArrayList<>();
        for (Product product : products) {
            result.add(product.getName());
        }
        return result;
    }

    public static void main(String[] args) {
        List<Product> products = Arrays.asList(
                new Product("Sach", 120, true),
                new Product("But", 30, false),
                new Product("Vo", 80, true),
                new Product("Cap", 150, false)
        );

        Predicate<Product> expensive =
                product -> product.getPrice() >= 100;
        Predicate<Product> available = Product::isAvailable;

        System.out.println(
                names(filter(products, expensive.and(available)))
        );
        System.out.println(
                names(filter(products, expensive.or(available)))
        );
        System.out.println(
                names(filter(products, expensive.negate()))
        );
        System.out.println(
                names(filter(products, p -> p.getName().length() <= 2))
        );
    }
}
~~~

Biên dịch và chạy với JDK 17+ (chương trình này cũng dùng được trên Java 8):

~~~bash
javac PredicateProductDemo.java
java PredicateProductDemo
~~~

Kết quả chính xác:

~~~text
[Sach]
[Sach, Vo, Cap]
[But, Vo]
[Vo]
~~~

Giải thích theo thứ tự:

1. `expensive` là điều kiện `price >= 100`; `available` là method reference tương ứng với `p -> p.isAvailable()`.
2. `expensive.and(available)` yêu cầu **cả hai điều kiện** đúng. Chỉ `Sach` vừa có giá từ 100 vừa còn hàng.
3. `expensive.or(available)` yêu cầu **ít nhất một điều kiện** đúng; kết quả là `Sach`, `Vo`, `Cap` theo thứ tự xuất hiện trong danh sách đầu vào.
4. `expensive.negate()` đảo điều kiện đắt thành giá dưới 100, cho `But` và `Vo`.
5. Lambda ở lần gọi cuối thay điều kiện bằng độ dài tên không quá hai ký tự; chỉ `Vo` đạt điều kiện.

Phương thức `filter` không phải biết “đắt”, “còn hàng” hoặc “tên ngắn”; nó chỉ gọi `criterion.test(item)` và quyết định giữ hay bỏ phần tử. Đó là giá trị của **truyền điều kiện như tham số hành vi**.

## 4. Các thao tác chuẩn trên Predicate

`Predicate<T>` cung cấp phương thức SAM `test` và các phương thức tổ hợp, vì vậy có thể xây điều kiện phức tạp từ các điều kiện nhỏ.

| Phương thức | Tính chất | Cách đọc |
| --- | --- | --- |
| `test(T value)` | SAM, gọi điều kiện hiện tại | Giá trị có đạt quy tắc không? |
| `and(Predicate<? super T> other)` | Kết hợp AND, có short-circuit | Cả điều kiện trái **và** phải |
| `or(Predicate<? super T> other)` | Kết hợp OR, có short-circuit | Điều kiện trái **hoặc** phải |
| `negate()` | Tạo phủ định của predicate | **Không** thỏa điều kiện hiện tại |
| `Predicate.isEqual(targetRef)` | Static factory kiểm tra tương đương theo `Objects.equals` | Có bằng giá trị đích không? |
| `Predicate.not(predicate)` | Static factory phủ định; có từ **Java 11** | Không thỏa predicate được truyền vào |

### 4.1. Phép AND: cả hai phải đúng

~~~java
Predicate<Integer> positive = n -> n > 0;
Predicate<Integer> even = n -> n % 2 == 0;
Predicate<Integer> positiveEven = positive.and(even);

System.out.println(positiveEven.test(4));  // true
System.out.println(positiveEven.test(3));  // false
System.out.println(positiveEven.test(-2)); // false
~~~

`positive.and(even)` tạo ra một predicate mới; nó **không thay đổi** đối tượng `positive`. Khi kiểm tra, Java gọi predicate trái trước. Chỉ khi kết quả trái là `true`, predicate phải mới được đánh giá.

### 4.2. Phép OR: ít nhất một điều kiện đúng

~~~java
Predicate<Integer> negative = n -> n < 0;
Predicate<Integer> multipleOfTen = n -> n % 10 == 0;
Predicate<Integer> special = negative.or(multipleOfTen);

System.out.println(special.test(-7)); // true
System.out.println(special.test(20)); // true
System.out.println(special.test(7));  // false
~~~

Trong `negative.or(multipleOfTen)`, nếu vế trái trả `true`, Java **không cần gọi** vế phải. AND/OR của predicate hoạt động theo logic short-circuit giống `&&` và `||` trong Java.

### 4.3. Phủ định: `negate` và `Predicate.not`

~~~java
Predicate<String> empty = String::isEmpty;
Predicate<String> notEmpty = empty.negate();

System.out.println(notEmpty.test("Java")); // true
System.out.println(notEmpty.test(""));     // false
~~~

Với JDK 11+, có thêm cú pháp phù hợp khi truyền method reference vào Stream:

~~~java
java.util.function.Predicate<String> notBlank =
        java.util.function.Predicate.not(String::isBlank);
~~~

`String.isBlank()` và `Predicate.not(...)` đều có từ Java 11. Phương thức `isBlank` kiểm tra chuỗi rỗng hoặc chỉ gồm ký tự trắng; khái niệm này khác với `isEmpty`, vốn chỉ kiểm tra độ dài bằng 0. Không đưa `isBlank` hoặc `Predicate.not` vào một dự án biên dịch trên đúng JDK 8 mà không thay thế API tương thích.

### 4.4. So sánh bằng `Predicate.isEqual`

~~~java
Predicate<String> isJava = Predicate.isEqual("Java");

System.out.println(isJava.test("Java")); // true
System.out.println(isJava.test("java")); // false
System.out.println(isJava.test(null));   // false
~~~

`Predicate.isEqual` dựa trên `Objects.equals(targetRef, candidate)`, nên xử lý `null` có chủ đích. Khi giá trị đích là `null`, predicate tương đương kiểm tra đầu vào có `null` hay không:

~~~java
Predicate<String> isNull = Predicate.isEqual(null);
System.out.println(isNull.test(null)); // true
~~~

Đối với các lớp tự định nghĩa, tính “bằng nhau” phụ thuộc cách lớp đó định nghĩa `equals`; hai đối tượng nhìn giống nhau chưa chắc bằng nhau nếu chưa có `equals` phù hợp.

## 5. Short-circuit và thứ tự đánh giá

Tổ hợp predicate không đơn thuần là phép toán đại số được chạy tự do theo mọi thứ tự. Với `a.and(b)`, `a.test(value)` được gọi trước; `b.test(value)` chỉ được gọi nếu `a` trả `true`. Với `a.or(b)`, `b` chỉ được gọi nếu `a` trả `false`.

Ví dụ minh họa (đặt trong phương thức đã import `Predicate`):

~~~java
Predicate<Integer> positive = n -> {
    System.out.println("check positive");
    return n > 0;
};
Predicate<Integer> even = n -> {
    System.out.println("check even");
    return n % 2 == 0;
};

System.out.println(positive.and(even).test(-3));
System.out.println(positive.and(even).test(4));
~~~

Stdout của **đoạn minh họa**:

~~~text
check positive
false
check positive
check even
true
~~~

Việc thêm `System.out.println` vào predicate ở đây **chỉ nhằm quan sát thứ tự đánh giá**. Trong code ứng dụng, nên ưu tiên predicate không tạo side effect, vì short-circuit khiến số lần gọi khác nhau theo dữ liệu.

### Thứ tự quan trọng khi phòng tránh `NullPointerException`

Điều kiện thường phải kiểm tra khác `null` trước khi truy cập phương thức trên đối tượng:

~~~java
Predicate<String> nonNull = java.util.Objects::nonNull;
Predicate<String> longEnough = text -> text.length() >= 4;

Predicate<String> safe = nonNull.and(longEnough);
System.out.println(safe.test(null)); // false
~~~

`safe` không gọi `text.length()` khi đầu vào `null`. Ngược lại, `longEnough.and(nonNull)` sẽ gọi `length()` trước và có thể ném `NullPointerException`.

Thêm nữa, bản thân `and(null)` hoặc `or(null)` là không hợp lệ: tham số `other` không được `null`; khi tổ hợp, chúng ném `NullPointerException`. Short-circuit của `test` không thay đổi yêu cầu phải truyền một predicate hợp lệ.

## 6. Predicate trong Stream, Collection và Optional

### 6.1. `Stream.filter`: tạo kết quả chọn lọc

~~~java
List<String> names = java.util.Arrays.asList(
        "An", "Binh", "Chi", "Dung");

List<String> longNames = names.stream()
        .filter(name -> name.length() >= 4)
        .collect(java.util.stream.Collectors.toList());

System.out.println(longNames); // [Binh, Dung]
~~~

`Stream.filter` nhận `Predicate<? super T>`. Nó dùng kết quả `test` để giữ hoặc loại phần tử trong pipeline. `filter` là **intermediate operation**, thường được thực thi lười (lazy): các phép kiểm tra không nhất thiết chạy ngay ở dòng khai báo pipeline, mà được xử lý khi terminal operation như `collect`, `count`, `findFirst` yêu cầu kết quả.

Đừng suy luận rằng predicate sẽ được gọi chính xác một lần cho mọi phần tử trong mọi pipeline. Chẳng hạn `findFirst` có thể dừng sau khi tìm thấy phần tử phù hợp; các thao tác tối ưu/short-circuit và cách xử lý song song thay đổi số lần và thứ tự callback thực tế. Hãy viết predicate đúng và ổn định, tránh phụ thuộc side effect.

### 6.2. `Collection.removeIf`: sửa trực tiếp collection

~~~java
java.util.List<String> names =
        new java.util.ArrayList<>(
                java.util.Arrays.asList("An", "Binh", "Chi"));

names.removeIf(name -> name.length() <= 2);
System.out.println(names); // [Binh, Chi]
~~~

`removeIf` nhận `Predicate<? super E>` và **xóa phần tử ngay trong collection có thể sửa đổi** nếu predicate trả `true`. Khác với `stream().filter(...)` vốn tạo pipeline để dẫn tới kết quả mới, `removeIf` có tác động lên collection gốc.

Không phải collection nào cũng cho phép xóa: collection cố định kích thước hoặc không hỗ trợ thao tác remove có thể ném `UnsupportedOperationException`. Ví dụ chủ động dùng `ArrayList` có thể sửa đổi.

### 6.3. `Optional.filter`: giữ giá trị nếu đạt điều kiện

~~~java
java.util.Optional<String> result =
        java.util.Optional.of("Java")
                .filter(s -> s.length() >= 4);

System.out.println(result.orElse("none")); // Java
~~~

`Optional.filter` trả lại Optional có giá trị nếu predicate đúng, hoặc Optional rỗng nếu sai. Với `Optional.empty()`, predicate **không được gọi**. Đây cũng là trường hợp cho thấy số lần gọi callback do API quyết định.

## 7. Ví dụ JDK 17+ đầy đủ: kiểm tra null, chuỗi trắng và điều kiện kết hợp

Ví dụ dưới dùng một số API hiện đại còn được hỗ trợ: `String.isBlank()` và `Predicate.not(...)` có từ Java 11. Chúng giúp biểu diễn điều kiện rõ nghĩa hơn khi làm việc với chuỗi.

Tạo tệp **PredicateTextDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class PredicateTextDemo {
    public static void main(String[] args) {
        List<String> inputs = Arrays.asList(
                null, "", "  ", "Java", "Lambda", "go");

        Predicate<String> nonNull = Objects::nonNull;
        Predicate<String> notBlank = Predicate.not(String::isBlank);
        Predicate<String> atLeastFour = text -> text.length() >= 4;

        Predicate<String> acceptable =
                nonNull.and(notBlank).and(atLeastFour);

        List<String> accepted = inputs.stream()
                .filter(acceptable)
                .collect(Collectors.toList());

        System.out.println(accepted);

        Predicate<String> isJava = Predicate.isEqual("Java");
        System.out.println(isJava.test("Java"));
        System.out.println(isJava.test(null));
        System.out.println(notBlank.test("  "));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac PredicateTextDemo.java
java PredicateTextDemo
~~~

Stdout chính xác:

~~~text
[Java, Lambda]
true
false
false
~~~

Giải thích:

1. `nonNull` bảo đảm không gọi các predicate dùng `String` trên giá trị `null`. Vì `and` short-circuit, `notBlank` và `atLeastFour` không chạy cho phần tử `null`.
2. `Predicate.not(String::isBlank)` phủ định điều kiện rỗng/chuỗi chỉ chứa khoảng trắng. Chuỗi `"  "` không đạt điều kiện.
3. `atLeastFour` yêu cầu tối thiểu bốn ký tự, vì vậy `"Java"` và `"Lambda"` được giữ, còn `"go"` bị loại.
4. `Predicate.isEqual("Java")` cho phép so sánh an toàn với đầu vào `null`. Đối chiếu chuỗi `"Java"` đúng còn `null` sai.

**Giới hạn áp dụng:** Đây là ví dụ JDK 17+, không thể biên dịch nguyên văn trên JDK 8 vì `String.isBlank` và `Predicate.not` xuất hiện từ Java 11. Với JDK 8 có thể viết một predicate tự định nghĩa để kiểm tra chuỗi rỗng/khoảng trắng theo yêu cầu nghiệp vụ; không nên âm thầm giả định `trim().isEmpty()` giống hoàn toàn `isBlank()` với mọi ký tự Unicode.

## 8. Chọn Predicate hay một functional interface khác?

| Nhu cầu | Kiểu phù hợp | SAM | Lý do |
| --- | --- | --- | --- |
| Kiểm tra một đối tượng | `Predicate<T>` | `boolean test(T)` | Một đầu vào, trả đúng/sai |
| Kiểm tra hai đối tượng | `BiPredicate<T,U>` | `boolean test(T,U)` | Hai đầu vào, trả đúng/sai |
| Kiểm tra số `int` | `IntPredicate` | `boolean test(int)` | Tránh boxing `Integer` |
| Kiểm tra số `long` | `LongPredicate` | `boolean test(long)` | Tránh boxing `Long` |
| Kiểm tra số `double` | `DoublePredicate` | `boolean test(double)` | Tránh boxing `Double` |
| Chuyển đổi dữ liệu | `Function<T,R>` | `R apply(T)` | Trả dữ liệu, không phải điều kiện |
| Thực hiện một hành động | `Consumer<T>` | `void accept(T)` | Mục tiêu là tác động/hành động |
| Tạo một giá trị không cần đầu vào | `Supplier<T>` | `T get()` | Không có đối số |

Ví dụ `BiPredicate` (mảnh mã trong phương thức):

~~~java
java.util.function.BiPredicate<Integer, Integer> larger =
        (left, right) -> left > right;

System.out.println(larger.test(9, 4)); // true
~~~

Với luồng số nguyên nguyên thủy, `IntStream.filter` nhận `IntPredicate`:

~~~java
int sum = java.util.stream.IntStream.of(1, 2, 3, 4, 5)
        .filter(n -> n % 2 == 0)
        .sum();

System.out.println(sum); // 6
~~~

Còn `Stream<Integer>.filter` nhận `Predicate<? super Integer>` và việc xử lý số thông qua đối tượng `Integer` có thể phát sinh boxing. Không cần tối ưu hóa trước khi đo lường; chọn kiểu theo ý nghĩa API và dữ liệu thực tế.

**Tránh nhầm `Function<T, Boolean>` với `Predicate<T>`:** về mặt hình thức, cả hai có thể tính một điều kiện. Tuy nhiên `Predicate` có hợp đồng `boolean` nguyên thủy, các phép tổ hợp `and/or/negate` chuẩn và truyền đạt rõ ý nghĩa “đây là điều kiện”. `Function<T, Boolean>` tạo/nhận `Boolean` có thể `null`, thường không phải lựa chọn tốt cho một phép lọc đơn thuần.

## 9. Thiết kế predicate dễ đọc và an toàn

### 9.1. Đặt tên theo quy tắc nghiệp vụ

Các điều kiện dùng nhiều lần nên có tên mang ý nghĩa:

~~~java
Predicate<String> hasText =
        text -> text != null && !text.isBlank();

Predicate<String> isCode =
        text -> hasText.test(text) && text.startsWith("CODE-");
~~~

Đây là mảnh mã dành cho JDK 11+ do dùng `String.isBlank`. Đặt tên `hasText`, `isCode` làm quy tắc dễ kiểm thử hơn một lambda dài có nhiều toán tử logic.

Khi điều kiện được dùng lặp lại trong nhiều chỗ, có thể trích thành phương thức `static boolean isCode(String text)` rồi dùng method reference `YourClass::isCode`, hoặc tạo predicate có tên tại ranh giới của module. Không nhất thiết tạo một lớp chỉ để chứa một predicate ngắn.

### 9.2. Ưu tiên hành vi ổn định, tránh side effect

Một predicate lý tưởng trả lời cùng một câu hỏi với cùng đầu vào và không thay đổi trạng thái hệ thống. Java **không bắt buộc** predicate thuần (pure), nhưng predicate có side effect gây vấn đề:

- Trong Stream, số lần và thứ tự gọi có thể thay đổi nếu pipeline short-circuit hoặc xử lý song song.
- Trong `and/or`, điều kiện thứ hai có thể không được gọi.
- Trong vòng lặp dùng lại, thay đổi dữ liệu nguồn có thể khiến kết quả lần sau khác lần trước.
- Trong xử lý đồng thời, đọc/ghi trạng thái mutable bên ngoài có thể gây data race.

Ví dụ nên tránh:

~~~java
int[] counter = {0};
Predicate<String> counted = s -> {
    counter[0]++; // Side effect bên ngoài điều kiện
    return s.length() > 2;
};
~~~

Đây là mảnh mã minh họa, không phải chương trình đầy đủ. Biến local `counter` effectively final, nên lambda được phép thay đổi phần tử mảng; tuy nhiên đây **không phải** lý do tốt để dùng mảng nhằm né ràng buộc capture. Nếu cần đếm phần tử đạt điều kiện, `stream().filter(predicate).count()` diễn đạt rõ hơn. Nếu thật sự cần thống kê thực thi, thiết kế một cơ chế theo dõi riêng và cân nhắc an toàn luồng.

### 9.3. Xử lý null theo hợp đồng

`Predicate<T>` không tự cấm `null`: `test(null)` chỉ an toàn khi phần thân hỗ trợ. Hãy chọn và công bố một trong những chính sách:

- **Cho phép null**: ví dụ `Objects::nonNull`, `Objects::isNull`, `Predicate.isEqual(null)`.
- **Từ chối null**: API nhận dữ liệu có thể kiểm tra `Objects.requireNonNull` và báo lỗi rõ.
- **Loại null trước khi áp quy tắc khác**: `Objects::nonNull` đứng đầu chuỗi `and`.

Không nhầm khả năng `Predicate` nhận `T` dạng reference với cam kết mọi lambda đều chịu được `null`.

### 9.4. Khi cần biết *vì sao* sai

Một predicate chỉ trả `true/false`; nó không tự giải thích nguyên nhân thất bại. Với form nhập liệu hoặc nghiệp vụ cần **danh sách lỗi cụ thể**, nên thiết kế các quy tắc có tên đi cùng thông báo, hoặc một kết quả validation chứa chi tiết. Dùng chuỗi `and` cho nhiều quy tắc có thể dừng ngay khi lỗi đầu tiên xuất hiện; nếu cần thu thập **tất cả** lỗi, hãy chủ động đánh giá từng quy tắc có liên quan theo đúng hợp đồng nghiệp vụ.

### 9.5. Checked exception

SAM `Predicate.test(T)` **không khai báo checked exception**. Vì vậy lambda truyền vào `Predicate` không thể trực tiếp để một `IOException` chưa xử lý thoát ra. Có thể xử lý ngoại lệ tại lambda, hoặc nếu nghiệp vụ cần quy tắc có thể ném checked exception, thiết kế một functional interface riêng khai báo `throws` rõ ràng. Không bắt exception rồi tự động trả `false` nếu như vậy che giấu lỗi I/O hay lỗi hệ thống. Các unchecked exception vẫn có thể truyền ra ngoài và cần được xem xét trong hợp đồng API nhận predicate.

## 10. Lỗi thường gặp và cách sửa

1. **Trả về kiểu không phải boolean.** `Predicate<String> p = s -> s.length()` không hợp lệ vì `int` không chuyển thành `boolean`. Hãy viết điều kiện như `s -> s.length() > 0`.
2. **Đảo logic của `removeIf`.** `removeIf(p)` **xóa** phần tử nếu `p.test` đúng; còn `Stream.filter(p)` **giữ** phần tử nếu `p.test` đúng.
3. **Không xử lý null.** `String::isEmpty` hoặc `s -> s.length() > 3` sẽ ném `NullPointerException` khi được gọi trên null. Đặt `Objects::nonNull` trước khi ghép `and` nếu cần.
4. **Dựa vào side effect của predicate.** `and`/`or` có short-circuit; Stream cũng có các tối ưu và terminal operation khác nhau. Đừng dựa vào số lần gọi predicate để cập nhật trạng thái nghiệp vụ.
5. **Nhầm `isEmpty` và `isBlank`.** Chuỗi `"   "` không empty nhưng blank theo `String.isBlank()`; cần xác định đúng yêu cầu.
6. **Dùng API theo phiên bản JDK sai.** `Predicate.not` và `String.isBlank` là Java 11+, còn `Predicate.test/and/or/negate/isEqual` đã có từ Java 8.
7. **Dùng `==` để so sánh nội dung String.** `s -> s == "Java"` so reference, không diễn đạt bình đẳng nội dung; dùng `"Java".equals(s)` hoặc `Predicate.isEqual("Java")`.
8. **Tổ hợp predicate quá dài, khó kiểm chứng.** Đặt tên các quy tắc nhỏ, dùng `and/or/negate` với ngoặc/tách biến hợp lý, và viết test cho các ranh giới như 0, null, giá trị bằng ngưỡng.
9. **Xem predicate là cơ chế bảo mật hoàn chỉnh.** Điều kiện như `user -> user.isAdmin()` chỉ là kiểm tra tại một thời điểm; phân quyền thực tế còn cần kiểm soát nguồn dữ liệu, xác thực và thực thi chính sách ở điểm truy cập phù hợp.
10. **Lẫn hành vi với thời điểm gọi.** `Predicate` mô tả điều kiện; API nhận predicate mới quyết định lúc nào gọi `test`. Không giả định mọi lambda chạy ngay khi được định nghĩa.

## 11. Bài tập thực hành

**Bài 1 — Ghép điều kiện với AND/OR.** Với danh sách từ ví dụ phần 3, tạo predicate chọn sản phẩm **còn hàng hoặc giá dưới 50**. In tên kết quả và giải thích vì sao `Cap` không được chọn. Đáp án đối chiếu: `[Sach, But, Vo]`.

**Bài 2 — Đảo điều kiện.** Dùng `Predicate<String> startsWithA = s -> s.startsWith("A")` và `negate()` để chọn tên không bắt đầu bằng `A`. Nếu danh sách có `null`, hãy sửa điều kiện sao cho không ném exception và xác định rõ null có được giữ lại hay không.

**Bài 3 — Phân biệt hai API lọc.** Từ danh sách `["A", "AB", "ABC"]`, hãy thực hiện (a) `stream().filter(s -> s.length() >= 2)` và (b) `removeIf(s -> s.length() >= 2)` trên một `ArrayList` riêng. So sánh kết quả và trạng thái collection ban đầu.

**Bài 4 — Short-circuit và số lần gọi.** Viết hai predicate có in thông báo, rồi gọi `a.and(b).test(x)` cho một giá trị làm `a` trả false. Dự đoán thông báo nào xuất hiện. Lặp lại với `a.or(b)` khi `a` trả true.

**Bài 5 — Dùng `IntPredicate`.** Với `IntStream.rangeClosed(1, 10)`, dùng `filter` để lấy các số chia hết cho 3 rồi `sum()`. Kết quả cần được giải thích từ các số 3, 6, 9, có tổng bằng 18.

## 12. Ghi nhớ

- `Predicate<T>` biểu diễn **điều kiện một đầu vào T, kết quả boolean** qua `test(T)`; đây là functional interface chuẩn vẫn được sử dụng trong Java hiện đại.
- `and`, `or` và `negate` cho phép ghép điều kiện; AND/OR đánh giá từ trái sang phải và có short-circuit, nên thứ tự đặc biệt quan trọng khi cần kiểm tra null.
- `Predicate.isEqual` tạo điều kiện bằng nhau an toàn theo `Objects.equals`; `Predicate.not` là cách phủ định có từ Java 11.
- `Stream.filter` giữ phần tử phù hợp trong pipeline, `Collection.removeIf` xóa phần tử phù hợp khỏi collection có thể sửa đổi, `Optional.filter` giữ hoặc loại giá trị của Optional.
- Để code dễ hiểu và tin cậy, hãy đặt tên quy tắc, kiểm thử điều kiện biên, hạn chế side effect, chọn chính sách null rõ ràng và phân biệt kiểm tra đúng/sai với cơ chế thu thập lỗi chi tiết.
