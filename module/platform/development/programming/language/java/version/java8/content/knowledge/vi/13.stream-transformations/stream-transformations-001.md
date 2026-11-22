# filter và chọn phần tử trong Java Stream

## 1. Mục tiêu: chọn đúng phần tử, không nhầm với biến đổi dữ liệu

Trong Java Stream API, **`filter(Predicate<? super T>)`** là thao tác trung gian (*intermediate operation*) giúp **giữ lại** những phần tử thỏa một điều kiện. Nó có từ **Java 8**, vẫn được dùng phổ biến trong Java hiện đại và là một trong các công cụ dễ đọc nhất để biểu diễn yêu cầu “chọn các phần tử phù hợp”.

Ví dụ yêu cầu: từ danh sách điểm, chỉ lấy điểm đạt từ 5 trở lên:

~~~java
// Mảnh mã minh họa trong một method trên JDK 17+.
List<Integer> scores = List.of(3, 8, 5, 2, 10);

List<Integer> passed = scores.stream()
        .filter(score -> score >= 5)
        .toList();

// passed = [8, 5, 10]
~~~

Giải thích từng phần:

1. `scores` là **nguồn** dữ liệu.
2. `scores.stream()` tạo một `Stream<Integer>` từ nguồn.
3. `filter(score -> score >= 5)` giữ phần tử có điều kiện trả `true`, bỏ phần tử có điều kiện trả `false`.
4. `toList()` là **terminal operation** kích hoạt việc đánh giá pipeline và thu kết quả thành `List<Integer>`.
5. Nguồn `scores` không bị xóa phần tử vì dùng `filter`; kết quả là một danh sách khác về mặt cấu trúc dữ liệu.

**Điểm dễ nhầm:** `filter` **không tự sửa dữ liệu** và cũng **không chuyển** một phần tử thành giá trị khác. Nếu muốn biến `String` thành số, chuyển tên sang chữ hoa hoặc đổi object sang DTO, đó là công việc của `map` hoặc một thao tác biến đổi phù hợp.

**Phiên bản:** `Stream.filter`, `Predicate` và `Collectors.toList()` đã có từ Java 8; `List.of` từ Java 9; `Stream.toList()` từ Java 16. Các chương trình chạy độc lập trong bài sử dụng JDK 17+ và nêu rõ điểm phân biệt để không gán API mới cho Java 8 nguyên bản.

## 2. Chữ ký, cách hiểu `Predicate`, và quy tắc `true`/`false`

Chữ ký về bản chất là:

~~~java
Stream<T> filter(Predicate<? super T> predicate);
~~~

Nó nhận một `Predicate` và trả về một `Stream<T>`. Không đổi kiểu `T` sang kiểu khác, vì chức năng chính là **chọn một tập con các phần tử** theo điều kiện.

`java.util.function.Predicate<T>` là functional interface với phương thức trừu tượng:

~~~java
boolean test(T value);
~~~

Vì `Predicate` là functional interface, ta có thể truyền **lambda**, **method reference** hoặc một object thực thi `Predicate`.

Ví dụ tương đương về ý nghĩa:

~~~java
// Mảnh mã minh họa, có import Predicate, Stream:
Predicate<String> nonEmpty = text -> !text.isEmpty();

Stream.of("a", "", "bb")
        .filter(nonEmpty)
        .toList(); // [a, bb]

Stream.of("a", "", "bb")
        .filter(text -> !text.isEmpty())
        .toList(); // [a, bb]
~~~

Nếu `predicate.test(element)` trả:

- **`true`**: phần tử được **giữ lại** và có thể chuyển đến thao tác kế tiếp.
- **`false`**: phần tử bị **loại khỏi pipeline phía sau**.
- **ném exception**: pipeline đang đánh giá thường bị gián đoạn và exception lan theo quy tắc của lời gọi/terminal, không có giá trị `false` tự động.

Ví dụ `filter(x -> x > 0)` trên `[-2, 0, 5]` giữ `5`; điều kiện không cần trả object, danh sách, `Optional` hoặc chuỗi. Nó bắt buộc trả kết quả kiểu `boolean` sau khi áp dụng conversion thích hợp.

### `filter` không phải `if` trên cả collection

Mỗi lần predicate được đánh giá, đầu vào là **một phần tử**, không phải nguyên `List`. Nếu cần kiểm tra thuộc tính chung cả tập, dùng terminal như `allMatch`, `anyMatch`, `count` hoặc collector tùy yêu cầu. `filter` có thể được nối với các terminal đó, nhưng tự nó chỉ tạo một Stream mô tả tập phần tử được phép đi tiếp.

### Kiểu `? super T` nghĩa là gì?

Nếu luồng là `Stream<Child>`, một `Predicate<Parent>` vẫn có thể sử dụng khi `Child extends Parent`, bởi predicate có khả năng kiểm tra cả đối tượng Child như một Parent.

~~~java
// Mảnh mã minh họa; Animal, Dog được định nghĩa ở đây:
class Animal {}
class Dog extends Animal {}

Predicate<Animal> exists = animal -> animal != null;
List<Dog> dogs = List.of(new Dog());

long count = dogs.stream()
        .filter(exists)
        .count(); // 1
~~~

Đây là một ví dụ nhỏ về **contravariance theo tham số đầu vào**; không cần dùng cast vô nghĩa chỉ để lọc một kiểu con bằng điều kiện áp dụng cho kiểu cha.

## 3. `filter` là intermediate và thường lazy

Một đoạn:

~~~java
Stream<Integer> prepared = Stream.of(1, 2, 3)
        .filter(n -> {
            System.out.println("test " + n);
            return n > 1;
        });
~~~

chỉ **tạo pipeline**. Với kiểu Stream thông thường, các dòng `test ...` không được in ngay lúc gán `prepared`. Khi gọi một terminal phù hợp như `prepared.toList()`, hệ thống mới cần quyết định phần tử nào đi qua filter.

Điều này được gọi là **lazy evaluation** của intermediate operation. Nó cho phép JVM thực hiện các thao tác theo pipeline, phối hợp lọc và biến đổi thay vì nhất thiết tạo một `List` tạm sau mỗi giai đoạn.

Tuy nhiên, **lazy không bảo đảm predicate được gọi đúng một lần trên tất cả phần tử nguồn trong mọi pipeline**. Với short-circuit terminal, Stream có thể dừng sớm; với tối ưu hóa dựa trên metadata, một số thao tác có thể bị bỏ qua nếu kết quả cuối không đòi hỏi duyệt dữ liệu. Không thiết kế nghiệp vụ phụ thuộc vào việc một predicate nhất định luôn được gọi đúng N lần.

### Một terminal khởi động đánh giá

~~~java
List<Integer> result = Stream.of(1, 2, 3)
        .filter(n -> n > 1)
        .toList(); // [2, 3]
~~~

`toList` yêu cầu tạo danh sách kết quả; `filter` phải xác định phần tử nào được giữ. Nhưng khi dùng terminal như `findFirst` hay `anyMatch`, pipeline chỉ cần xem đủ phần tử để xác định câu trả lời, không nhất thiết phải duyệt tất cả.

## 4. Ví dụ chạy độc lập 1 — lọc các đối tượng theo nhiều thuộc tính

Tạo tệp **FilterProductsDemo.java**:

~~~java
import java.util.List;

public class FilterProductsDemo {

    record Product(String name, int price, boolean available) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("Pen", 12, true),
                new Product("Notebook", 85, true),
                new Product("Bag", 240, true),
                new Product("Pencil", 5, false),
                new Product("Folder", 40, true));

        List<String> selected = products.stream()
                .filter(p -> p.available() && p.price() <= 100)
                .map(Product::name)
                .toList();

        System.out.println("selected=" + selected);
        System.out.println("source-size=" + products.size());
        System.out.println("selected-count=" + selected.size());
    }
}
~~~

Biên dịch và chạy trên JDK 17+ (`record` đã được chuẩn hóa từ Java 16):

~~~bash
javac FilterProductsDemo.java
java FilterProductsDemo
~~~

**Stdout chính xác:**

~~~text
selected=[Pen, Notebook, Folder]
source-size=5
selected-count=3
~~~

Phân tích:

1. `products.stream()` lấy năm sản phẩm.
2. `filter(p -> p.available() && p.price() <= 100)` giữ `Pen`, `Notebook`, `Folder`. `Bag` bị loại vì giá 240, còn `Pencil` không khả dụng.
3. `map(Product::name)` mới **biến** `Product` thành `String`. Không được lẫn chức năng của `filter` với `map`.
4. `toList()` gom các tên theo encounter order của nguồn `List`; không tự sắp xếp theo tên hoặc giá.
5. `products` có kích thước 5 sau pipeline. `filter` không xóa phần tử trong collection gốc.

Nếu nghiệp vụ cần danh sách `Product` đầy đủ, có thể bỏ `map(Product::name)` và giữ `Stream<Product>` cho đến terminal. Chỉ biến sang tên khi đó là hợp đồng output.

## 5. Nối nhiều `filter` hay gộp một predicate?

Hai cách sau tương đương về tập phần tử với điều kiện thuần, không có side effect:

~~~java
// Mảnh mã minh họa:
orders.stream()
        .filter(Order::isPaid)
        .filter(order -> order.total() >= 100)
        .toList();
~~~

và:

~~~java
// Mảnh mã minh họa:
orders.stream()
        .filter(order -> order.isPaid() && order.total() >= 100)
        .toList();
~~~

**Tiêu chí đọc hiểu** mới là yếu tố chọn. Nối hai `filter` thường giúp mỗi điều kiện có một tên/ý nghĩa riêng; gộp một `filter` có thể ngắn hơn nếu điều kiện thuộc cùng một quy tắc nghiệp vụ.

Đừng suy rằng predicate đã được gọi cho mọi phần tử ở mỗi `filter`. Với pipeline tuần tự, phần tử bị loại ở bộ lọc trước không đi tới bộ lọc sau. Với expression `&&`, Java short-circuit phần vế sau nếu vế trước false. Nếu predicate thuần và không gây tác dụng phụ, hai cách đều biểu diễn đúng ý định chọn phần tử.

### Dùng `Predicate.and`, `or`, `negate`

`Predicate` từ Java 8 hỗ trợ ghép điều kiện:

~~~java
// Mảnh mã minh họa, có import java.util.function.Predicate:
Predicate<String> nonBlank = s -> s != null && !s.isBlank();
Predicate<String> longEnough = s -> s.length() >= 4;

Predicate<String> accepted = nonBlank.and(longEnough);

List<String> result = values.stream()
        .filter(accepted)
        .toList();
~~~

`and` kết hợp bằng logical AND và short-circuit; `or` là OR; `negate` đảo kết quả. Với điều kiện `nonBlank.and(longEnough)`, một `null` sẽ bị loại trước nên `longEnough` không được gọi trên null.

Khi có nhiều điều kiện cấu hình được, đặt tên `Predicate` có ý nghĩa giúp code test được từng quy tắc, thay vì viết một lambda dài và khó đọc.

## 6. `filter` có bảo toàn thứ tự không?

Với **ordered stream**, `filter` giữ **encounter order** của các phần tử đi qua điều kiện. Nó không tự đảo thứ tự, tự sort hoặc di chuyển phần tử.

Ví dụ:

~~~java
List<Integer> result = List.of(8, 3, 6, 1, 4).stream()
        .filter(n -> n % 2 == 0)
        .toList();

// [8, 6, 4], không tự đổi thành [4, 6, 8]
~~~

Nhiều nguồn có encounter order rõ, ví dụ `List.stream()`, `Stream.of(...)`, `IntStream.range(...)`. Nhưng **không phải mọi nguồn** đều có encounter order được bảo đảm, ví dụ một số `Set` hoặc stream đã được đánh dấu `unordered()`. Nếu nguồn không có thứ tự, không được yêu cầu filter “giữ thứ tự” mà nguồn chưa cam kết.

### `filter` và `sorted` là hai thao tác khác nhau

~~~java
List<Integer> result = List.of(8, 3, 6, 1, 4).stream()
        .filter(n -> n % 2 == 0)
        .sorted()
        .toList();

// [4, 6, 8]
~~~

`sorted()` chịu trách nhiệm sắp xếp; `filter()` chỉ quyết định giữ/bỏ. Nếu muốn thứ tự theo tiêu chí riêng, dùng `sorted(Comparator)`.

### Lọc trước hay sau `limit`?

Đây là điểm ngữ nghĩa quan trọng:

~~~java
List<Integer> source = List.of(9, 2, 8, 3, 4);

List<Integer> a = source.stream()
        .filter(n -> n % 2 == 0)
        .limit(2)
        .toList(); // [2, 8]

List<Integer> b = source.stream()
        .limit(2)
        .filter(n -> n % 2 == 0)
        .toList(); // [2]
~~~

Lọc rồi giới hạn hai phần tử **thỏa điều kiện** khác với giới hạn hai phần tử **nguồn** rồi mới lọc. Thứ tự các intermediate operation có thể thay đổi kết quả, dù mỗi operation đều hợp lệ.

## 7. Null: `filter` không tự bỏ phần tử null

Một Stream có thể chứa null nếu nguồn cho phép. Ví dụ `Arrays.asList("An", null, "Binh")` là một danh sách có null. `filter(String::isBlank)` hoặc `map(String::trim)` nếu nhận null sẽ ném `NullPointerException`.

Nếu hợp đồng muốn loại null:

~~~java
// Mảnh mã minh họa:
List<String> cleaned = values.stream()
        .filter(java.util.Objects::nonNull)
        .map(String::trim)
        .filter(s -> !s.isBlank())
        .toList();
~~~

Điểm quan trọng ở thứ tự:

1. **Lọc null trước** để tránh gọi instance method trên null.
2. Trim khoảng trắng sau khi biết phần tử không null.
3. Lọc chuỗi rỗng/blank sau khi chuẩn hóa.
4. Gom kết quả.

Nếu đổi `map(String::trim)` lên trước `filter(Objects::nonNull)`, chương trình có thể lỗi trước khi đến bộ lọc null. Có lúc `Objects::nonNull` không cần nếu nguồn đã có contract bảo đảm không null; không nên thêm kiểm tra dư thừa mà không rõ yêu cầu.

### Khác nhau giữa `isEmpty()` và `isBlank()`

- `"   ".isEmpty()` trả **false**, vì chuỗi vẫn có ký tự.
- `"   ".isBlank()` trả **true**, vì chỉ gồm whitespace theo định nghĩa Java.
- `String.isBlank()` có từ Java 11, vẫn phù hợp trên JDK 17+.

Nếu target thực sự là Java 8, có thể chọn một quy tắc cụ thể như `s.trim().isEmpty()` nhưng cần nhận ra `trim` và `isBlank` **không hoàn toàn đồng nghĩa** với mọi ký tự Unicode. Tránh thay đổi semantics lúc hạ mức phiên bản.

## 8. Ví dụ chạy độc lập 2 — null, trim, blank và distinct

Tạo tệp **FilterNullAndBlankDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class FilterNullAndBlankDemo {

    public static void main(String[] args) {
        List<String> source = Arrays.asList(
                " An ", null, "", "   ", "Binh", "An");

        List<String> cleaned = source.stream()
                .filter(Objects::nonNull)
                .map(String::trim)
                .filter(s -> !s.isBlank())
                .distinct()
                .toList();

        long nonNullCount = source.stream()
                .filter(Objects::nonNull)
                .count();

        System.out.println("source-size=" + source.size());
        System.out.println("non-null=" + nonNullCount);
        System.out.println("cleaned=" + cleaned);
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac FilterNullAndBlankDemo.java
java FilterNullAndBlankDemo
~~~

**Stdout chính xác:**

~~~text
source-size=6
non-null=5
cleaned=[An, Binh]
~~~

Giải thích:

- `Arrays.asList` cho phép phần tử null trong ví dụ này.
- `Objects::nonNull` loại một phần tử null, còn năm phần tử.
- `map(String::trim)` biến `" An "` thành `"An"`, `"   "` thành `""`.
- `filter(s -> !s.isBlank())` loại các chuỗi rỗng/blank.
- `distinct()` loại `"An"` xuất hiện hai lần, giữ bản đầu theo encounter order của List.
- `source` vẫn có sáu phần tử; filter không thay đổi collection nguồn.

Nếu yêu cầu là **giữ cả duplicate** sau chuẩn hóa, bỏ `distinct`. Nếu cần **giữ vị trí ban đầu** hoặc báo lỗi của từng dòng null, hãy giữ thêm index/metadata, không chỉ trả danh sách String đã lọc.

## 9. `filter` khác `map`, `flatMap`, `distinct` và `takeWhile`

Các thao tác thường được nối chung, nhưng không thay thế trực tiếp cho nhau.

| Operation | Đầu vào → đầu ra | Trách nhiệm |
| --- | --- | --- |
| `filter(predicate)` | Mỗi phần tử giữ hoặc bỏ | Chọn phần tử |
| `map(function)` | Mỗi phần tử tạo một giá trị khác | Biến đổi giá trị hoặc kiểu |
| `flatMap(function)` | Một phần tử thành 0/nhiều phần tử qua Stream con | Trải phẳng dữ liệu |
| `distinct()` | Giữ các phần tử không trùng | Loại duplicate theo `equals` |
| `sorted()` | Thay đổi thứ tự theo comparator/natural order | Sắp xếp |
| `limit(n)` | Lấy tối đa n phần tử | Giới hạn kích thước |
| `skip(n)` | Bỏ qua n phần tử đầu | Bỏ tiền tố |
| `takeWhile(predicate)` | Lấy tiền tố liên tiếp còn thỏa | Dừng khi điều kiện đầu tiên sai trên ordered stream |
| `dropWhile(predicate)` | Bỏ tiền tố liên tiếp thỏa | Giữ phần còn lại sau tiền tố |

`takeWhile` và `dropWhile` được thêm vào Java 9; không nhầm chúng là API của Java 8.

### `filter` không giống `takeWhile`

~~~java
List<Integer> nums = List.of(1, 2, 5, 3, 4);

List<Integer> filtered = nums.stream()
        .filter(n -> n < 5)
        .toList(); // [1, 2, 3, 4]

List<Integer> prefix = nums.stream()
        .takeWhile(n -> n < 5)
        .toList(); // [1, 2]
~~~

Với ordered stream, `filter` vẫn có thể chọn các phần tử thỏa điều kiện **sau** một phần tử không thỏa; `takeWhile` chỉ lấy **tiền tố liên tiếp**. Nếu bạn dùng `takeWhile` thay cho filter mà không chứng minh dữ liệu được sắp theo điều kiện đơn điệu, kết quả sẽ khác.

### `filter` không thể tự “tách hai danh sách” trong một lượt

Nếu yêu cầu là chia dữ liệu thành hai nhóm **đạt/chưa đạt**, có thể dùng hai stream riêng với `filter(predicate)` và `filter(predicate.negate())`, hoặc dùng một collector `partitioningBy(predicate)` để thu cả hai nhánh trong một phép terminal.

Ví dụ:

~~~java
// Mảnh mã minh họa:
Map<Boolean, List<Integer>> parts =
        numbers.stream()
                .collect(Collectors.partitioningBy(
                        n -> n >= 5));
~~~

`partitioningBy` trả map chứa nhóm theo boolean `true`/ `false`; đây là **tổng hợp kết quả**, khác `filter` chỉ cho một tập con.

## 10. `filter` và lựa chọn một phần tử: `findFirst`, `findAny`

Nhiều tác vụ không cần danh sách đầy đủ: “tìm **một** sản phẩm phù hợp”, “lấy phần tử **đầu tiên** hợp lệ”, “kiểm tra có tồn tại phần tử lỗi không”.

Với ordered stream:

~~~java
Optional<Integer> first = Stream.of(3, 8, 4, 9)
        .filter(n -> n % 2 == 0)
        .findFirst();

// Optional[8]
~~~

`filter` giữ các số chẵn, `findFirst` lấy phần tử đầu tiên theo encounter order. Không cần tạo `List` rồi lấy index 0.

Một số terminal giúp dừng sớm:

- `findFirst()`: trả `Optional<T>`, có nghĩa phần tử đầu theo encounter order nếu stream có thứ tự.
- `findAny()`: trả `Optional<T>`, có thể chọn một phần tử bất kỳ phù hợp. Đừng mặc định nó luôn bằng `findFirst`, nhất là trong pipeline song song.
- `anyMatch(predicate)`: trả boolean và có thể dừng ngay khi tìm thấy một phần tử hợp lệ.
- `allMatch(predicate)`: trả boolean và có thể dừng khi gặp phần tử không hợp lệ.
- `noneMatch(predicate)`: trả boolean và có thể dừng khi gặp phần tử hợp lệ.

Nếu chỉ cần biết **có hay không**, `anyMatch` thường rõ hơn `filter(predicate).findFirst().isPresent()`. Hai cách có mục tiêu tương tự nhưng `anyMatch` diễn đạt trực tiếp ý định kiểm tra tồn tại.

### Đừng dùng `findFirst().get()` thiếu kiểm tra rỗng

Nếu không có phần tử nào qua filter, `findFirst` trả `Optional.empty()`, và `get()` ném `NoSuchElementException`. Chọn `orElse`, `orElseGet`, `orElseThrow` hoặc truyền `Optional` cho caller theo hợp đồng.

`findFirst` trên stream có một phần tử null có thể ném `NullPointerException`, vì `Optional` không chứa null. Nếu dữ liệu có thể null, filter `Objects::nonNull` trước.

## 11. Ví dụ chạy độc lập 3 — lazy và short-circuit khi chọn phần tử

Tạo tệp **FilterLazyFindDemo.java**:

~~~java
import java.util.Optional;
import java.util.stream.Stream;

public class FilterLazyFindDemo {

    public static void main(String[] args) {
        System.out.println("build");

        Stream<Integer> prepared = Stream.of(1, 2, 3, 4, 5, 6)
                .filter(n -> {
                    System.out.println("checking=" + n);
                    return n > 2 && n % 2 == 0;
                });

        System.out.println("before-terminal");

        Optional<Integer> first = prepared.findFirst();
        System.out.println("first=" + first.orElse(-1));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac FilterLazyFindDemo.java
java FilterLazyFindDemo
~~~

**Stdout chính xác:**

~~~text
build
before-terminal
checking=1
checking=2
checking=3
checking=4
first=4
~~~

Đây là pipeline **tuần tự có encounter order**. Khi gọi `findFirst`, predicate kiểm tra lần lượt các phần tử; `1,2,3` không thỏa, `4` thỏa nên terminal có thể trả về ngay. `5` và `6` không bị đánh giá trong chương trình này.

Không biến việc in log từ predicate thành một hợp đồng nghiệp vụ. Trong pipeline có parallel hoặc tối ưu hóa khác, số lần và thứ tự thực thi side effect không được suy đơn giản từ encounter order của kết quả.

## 12. `filter(...).count()` khác `anyMatch(...)`

Giả sử cần biết có số âm nào không.

Cách A:

~~~java
boolean hasNegative = numbers.stream()
        .filter(n -> n < 0)
        .count() > 0;
~~~

Cách B:

~~~java
boolean hasNegative = numbers.stream()
        .anyMatch(n -> n < 0);
~~~

Với điều kiện thuần và dữ liệu phù hợp, hai cách cho cùng câu trả lời boolean, nhưng **B rõ ý định và có thể dừng sớm** khi tìm thấy phần tử âm. `count()` có mục đích tính số lượng; nếu thật sự cần số phần tử âm, dùng filter rồi count.

### `filter` không bắt buộc chạy hết nguồn

Nối filter với `limit` hoặc short-circuit terminal cho phép pipeline dừng trước khi duyệt hết:

~~~java
List<Integer> firstThreeEven =
        IntStream.rangeClosed(1, 1000)
                .filter(n -> n % 2 == 0)
                .limit(3)
                .boxed()
                .toList();
// [2, 4, 6]
~~~

Ví dụ lấy ba số chẵn đầu tiên, không có lý do nghiệp vụ để kiểm tra toàn bộ 1..1000 nếu đủ kết quả. `limit(3)` là **intermediate short-circuiting operation**, còn `toList` là terminal.

Đừng suy rằng các hàm truyền vào mọi intermediate nhất định được gọi một lần trên tất cả phần tử nguồn. Việc có side effect trong `filter`, `peek` hay `map` sẽ làm cách đọc kết quả và số lần gọi khó đáng tin hơn.

## 13. Dùng `Predicate` có tên khi điều kiện nghiệp vụ phát triển

Một lambda rất dài có thể che khuất yêu cầu. Thay vì:

~~~java
// Mảnh mã minh họa:
orders.stream()
    .filter(o -> o != null && o.paid()
            && o.amount() >= 100
            && o.category() != null
            && !o.category().isBlank())
    .toList();
~~~

có thể tách quy tắc thành các helper có tên:

~~~java
// Mảnh mã minh họa:
static boolean isPaid(Order order) {
    return order != null && order.paid();
}

static boolean hasValidAmount(Order order) {
    return order.amount() >= 100;
}

static boolean hasCategory(Order order) {
    return order.category() != null
            && !order.category().isBlank();
}
~~~

Sau đó:

~~~java
// Mảnh mã minh họa trong cùng class:
List<Order> selected = orders.stream()
        .filter(MyRules::isPaid)
        .filter(MyRules::hasValidAmount)
        .filter(MyRules::hasCategory)
        .toList();
~~~

`MyRules` là tên class minh họa chứa các helper; code chỉ chạy khi có class và `Order` tương ứng. Tách helper giúp test được từng rule, tránh trùng logic khi dùng ở nhiều pipeline và giảm độ dài lambda.

Nếu dùng `Predicate.and`, nhớ **thứ tự short-circuit có ý nghĩa về an toàn với null**. Điều kiện kiểm tra null cần nằm trước những điều kiện truy cập thuộc tính.

### Đừng gắn mọi điều kiện vào Stream nếu vòng lặp rõ hơn

Khi một thao tác cần `try/catch` riêng theo phần tử, `break`, `continue`, cập nhật trạng thái hoặc nhiều side effect theo thứ tự, vòng lặp tuần tự có thể dễ hiểu hơn. Không có quy tắc rằng “Java hiện đại phải dùng Stream” cho mọi lựa chọn.

## 14. Ví dụ chạy độc lập 4 — tái sử dụng Predicate, lọc và kiểm tra tập

Tạo tệp **FilterPredicateCompositionDemo.java**:

~~~java
import java.util.List;
import java.util.function.Predicate;

public class FilterPredicateCompositionDemo {

    public static void main(String[] args) {
        List<String> source = List.of(
                "Java", "go", "Stream", "Java 8", "API");

        Predicate<String> longEnough =
                text -> text.length() >= 4;
        Predicate<String> hasA =
                text -> text.toLowerCase(
                        java.util.Locale.ROOT).contains("a");

        Predicate<String> selectedRule =
                longEnough.and(hasA);

        List<String> selected = source.stream()
                .filter(selectedRule)
                .toList();

        List<String> rejected = source.stream()
                .filter(selectedRule.negate())
                .toList();

        boolean anySelected = source.stream()
                .anyMatch(selectedRule);

        boolean allSelected = source.stream()
                .allMatch(selectedRule);

        System.out.println("selected=" + selected);
        System.out.println("rejected=" + rejected);
        System.out.println("any=" + anySelected);
        System.out.println("all=" + allSelected);
    }
}
~~~

Lệnh chạy:

~~~bash
javac FilterPredicateCompositionDemo.java
java FilterPredicateCompositionDemo
~~~

**Stdout chính xác:**

~~~text
selected=[Java, Java 8]
rejected=[go, Stream, API]
any=true
all=false
~~~

Giải thích từng chuỗi:

- `"Java"`: dài 4, có chữ `a`, được giữ.
- `"go"`: dài 2, không đạt `longEnough`; không cần đánh giá `hasA` vì `and` short-circuit.
- `"Stream"`: dài 6 nhưng không chứa `a`, bị loại.
- `"Java 8"`: dài 6, chứa `a`, được giữ.
- `"API"`: dài 3 nên bị loại dù có `A`.

`negate()` tạo predicate đảo kết quả để chọn các phần tử không thỏa. Việc đọc `source.stream()` nhiều lần là hợp lệ vì đây là **các stream mới từ List**, không phải dùng lại một Stream đã tiêu thụ.

Nếu source có null, các predicate ví dụ này **không null-safe**. Cần xử lý null ngay từ đầu hoặc định nghĩa một predicate tổng hợp bảo vệ những lời gọi instance method.

## 15. Primitive Stream: `IntStream.filter`, `LongStream.filter`, `DoubleStream.filter`

Không phải mọi thao tác lọc đều cần `Stream<Integer>`. Java có các primitive stream:

- `IntStream.filter(IntPredicate)`
- `LongStream.filter(LongPredicate)`
- `DoubleStream.filter(DoublePredicate)`

Ví dụ:

~~~java
int sum = java.util.stream.IntStream.rangeClosed(1, 10)
        .filter(n -> n % 2 == 0)
        .sum(); // 2 + 4 + 6 + 8 + 10 = 30
~~~

`IntStream` chứa giá trị `int` nguyên thủy và có terminal như `sum`, `average`, `summaryStatistics`, `count`. Với xử lý số, nó có thể giảm boxing so với việc dùng `Stream<Integer>` cho mỗi phép toán.

Không phải cứ primitive stream là nhanh hơn trong mọi tình huống; nếu hiệu năng là mục tiêu, hãy benchmark trên dữ liệu và JVM thực tế. Các phép tính vẫn cần xem xét overflow: `IntStream.sum()` trả `int`, không tự mở rộng sang `long` nếu tổng vượt giới hạn.

### `filter` không thay đổi cận nguồn Range

`IntStream.rangeClosed(1,10)` tạo 1..10; `filter(n -> n % 2 == 0)` giữ 2,4,6,8,10. Không nên đọc như thể `rangeClosed` tự tạo bước nhảy 2. Nếu muốn tạo dãy có quy luật bước nhảy và số lượng rõ, có thể dùng `map`, `iterate` hoặc giải pháp khác phù hợp.

## 16. Ví dụ chạy độc lập 5 — lọc số, tổng, đếm và giữ thứ tự

Tạo tệp **IntFilterDemo.java**:

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class IntFilterDemo {

    public static void main(String[] args) {
        int sum = IntStream.rangeClosed(1, 12)
                .filter(n -> n % 3 == 0)
                .sum();

        long count = IntStream.rangeClosed(1, 12)
                .filter(n -> n % 3 == 0)
                .count();

        List<Integer> selected =
                IntStream.rangeClosed(1, 12)
                        .filter(n -> n % 3 == 0)
                        .boxed()
                        .toList();

        System.out.println("selected=" + selected);
        System.out.println("count=" + count);
        System.out.println("sum=" + sum);
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac IntFilterDemo.java
java IntFilterDemo
~~~

Stdout chính xác:

~~~text
selected=[3, 6, 9, 12]
count=4
sum=30
~~~

Ba terminal ở đây nằm trên **ba stream được tạo mới độc lập** từ `rangeClosed`. Không gọi `sum()`, `count()` và `boxed().toList()` lần lượt trên cùng một object `IntStream` đã tiêu thụ.

`boxed()` đổi primitive stream thành `Stream<Integer>` để thu danh sách object. Nếu chỉ cần tổng hoặc đếm, bỏ `boxed()` để pipeline đơn giản hơn.

## 17. Phân nhóm sau khi lọc: từ tập con đến kết quả tổng hợp

Một use case thường gặp: từ các đơn hàng, **chỉ chọn đơn đã thanh toán có số tiền đủ điều kiện**, sau đó **tính tổng theo nhóm**. `filter` đóng vai trò cổng dữ liệu; `collect` là terminal tổ chức kết quả.

~~~java
// Mảnh mã minh họa, cần Order có paid(), amount(), group().
Map<String, Integer> totals = orders.stream()
        .filter(Order::paid)
        .filter(o -> o.amount() >= 30)
        .collect(Collectors.groupingBy(
                Order::group,
                TreeMap::new,
                Collectors.summingInt(Order::amount)));
~~~

`filter` không xây Map. Nó chỉ quyết định các order nào được truyền đến `groupingBy`. Collector mới gom theo group và cộng tiền.

Khi dùng `groupingBy` trong production, cần xác định điều kiện với key null, thứ tự map, kiểu tổng số học có thể overflow và hợp đồng mutability. Đừng tự giả định collector mặc định luôn trả `TreeMap`; muốn thứ tự key ổn định, cung cấp map factory phù hợp.

## 18. Ví dụ chạy độc lập 6 — filter rồi collect theo nhóm

Tạo tệp **FilterOrdersDemo.java**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class FilterOrdersDemo {

    record Order(String group, int amount, boolean paid) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("book", 80, true),
                new Order("book", 200, false),
                new Order("pen", 20, true),
                new Order("pen", 30, true),
                new Order("book", 120, true));

        Map<String, Integer> totals = orders.stream()
                .filter(Order::paid)
                .filter(order -> order.amount() >= 30)
                .collect(Collectors.groupingBy(
                        Order::group,
                        TreeMap::new,
                        Collectors.summingInt(Order::amount)));

        long acceptedCount = orders.stream()
                .filter(Order::paid)
                .filter(order -> order.amount() >= 30)
                .count();

        System.out.println("totals=" + totals);
        System.out.println("accepted-count=" + acceptedCount);
        System.out.println("original-count=" + orders.size());
    }
}
~~~

Biên dịch/chạy JDK 17+:

~~~bash
javac FilterOrdersDemo.java
java FilterOrdersDemo
~~~

**Stdout chính xác:**

~~~text
totals={book=200, pen=30}
accepted-count=3
original-count=5
~~~

Đơn `book/80`, `pen/30`, `book/120` thỏa cả hai điều kiện. Đơn `book/200` chưa thanh toán và `pen/20` thấp hơn ngưỡng nên bị loại. `TreeMap` giúp thứ tự key lúc in ra ổn định theo natural order.

Một điểm đáng chú ý: `filter(Order::paid)` không có nghĩa “xóa các đơn chưa thanh toán khỏi collection” và không ném lỗi khi gặp đơn chưa thanh toán. Nó đơn thuần khiến đơn đó **không đi tiếp** trong pipeline đang đánh giá.

## 19. Chọn điều kiện có ý nghĩa, test ranh giới bao gồm/loại trừ

Hầu hết lỗi `filter` không đến từ API mà đến từ **điều kiện sai**:

- `price > 100` khác `price >= 100`.
- `age < 18` khác `age <= 18`.
- `date.isAfter(start)` khác “từ start trở đi” (cần tính cả bằng start nếu yêu cầu inclusive).
- `status.equals("ACTIVE")` có thể NPE nếu status null; `"ACTIVE".equals(status)` null-safe trong ngữ cảnh so sánh đó.
- `text.contains("a")` khác so sánh không phân biệt hoa thường.
- `&&` là giao các điều kiện; `||` là hợp — khác nhau về tập phần tử được chọn.

### Ví dụ kiểm thử biên giá

~~~java
// Mảnh mã minh họa:
Predicate<Integer> eligible = price ->
        price != null && price >= 100 && price <= 500;
~~~

Test nên gồm ít nhất:

| Giá | Kỳ vọng |
| --- | --- |
| `null` | Loại |
| `99` | Loại |
| `100` | Giữ |
| `250` | Giữ |
| `500` | Giữ |
| `501` | Loại |

Điều kiện này mang semantics khoảng đóng `[100,500]`. Nếu hợp đồng nghiệp vụ nói cận dưới/cận trên loại trừ, cần sửa toán tử chứ không đổi pipeline.

### Dùng kiểu số đúng

Nếu giá có đơn vị thập phân, không tự ý dùng `double` cho tiền hoặc so sánh làm tròn mà không có quy tắc. Trong bài toán tài chính, `BigDecimal` và quy định rounding có thể phù hợp hơn. `filter` không giải quyết hộ tính đúng đắn của miền dữ liệu.

## 20. Tính thuần, non-interference và stateless predicate

Đặc tả Stream mong đợi **behavioral parameters** của phần lớn operation là **non-interfering** (không sửa nguồn trong khi đang duyệt) và **stateless** (không phụ thuộc trạng thái thay đổi làm kết quả khó đoán). Điều này quan trọng với `filter` vì predicate là tiêu chí chọn phần tử.

Ví dụ tốt:

~~~java
// Mảnh mã minh họa:
.filter(product -> product.available() && product.price() <= 100)
~~~

Predicate chỉ đọc giá trị phần tử và trả boolean. Nó dễ test và có thể dùng trong nhiều pipeline.

Ví dụ rủi ro:

~~~java
// Mảnh mã minh họa về anti-pattern, không chạy trong chương trình mẫu:
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));

List<Integer> result = numbers.stream()
        .filter(n -> {
            numbers.add(n * 10); // Sửa nguồn đang được duyệt!
            return n > 1;
        })
        .toList();
~~~

Sửa collection nguồn trong lúc Stream đang duyệt có thể tạo `ConcurrentModificationException`, kết quả không đáng tin hoặc vấn đề khác phụ thuộc nguồn và cách thực thi. Không dùng side effect để “tiện vừa lọc vừa cập nhật” khi hai hành vi nên được thiết kế riêng.

### Stateful predicate có thể tạo lỗi khó thấy

~~~java
// Mảnh mã minh họa KHÔNG nên áp dụng như filter thuần:
AtomicInteger counter = new AtomicInteger();
stream.filter(item -> counter.incrementAndGet() <= 3);
~~~

Dù `AtomicInteger` thread-safe cho tăng số, kết quả chọn phần tử có thể phụ thuộc **thứ tự thực thi predicate**, nhất là trên parallel stream; nó không diễn đạt chắc chắn “ba phần tử đầu theo encounter order”. Nếu mục đích là lấy ba phần tử đầu, dùng `limit(3)` trên ordered stream. Nếu mục đích là lấy ba phần tử đầu **thỏa điều kiện**, dùng `filter(condition).limit(3)`.

**Không đánh đồng an toàn thao tác nguyên tử với tính đúng của thuật toán chọn phần tử.**

## 21. Parallel Stream: điều kiện phải độc lập với lịch thực thi

`filter` cũng hoạt động trên parallel stream:

~~~java
List<Integer> result = IntStream.range(0, 10)
        .parallel()
        .filter(n -> n % 3 == 0)
        .boxed()
        .toList();

// [0, 3, 6, 9]
~~~

Với nguồn có encounter order như `IntStream.range`, `toList()` thu danh sách theo encounter order, dù phép kiểm tra có thể diễn ra trên nhiều thread.

Tuy nhiên:

~~~java
IntStream.range(0, 10)
        .parallel()
        .filter(n -> n % 3 == 0)
        .forEach(System.out::println);
~~~

**không có stdout thứ tự cố định**. `forEach` trên parallel stream không cam kết callback chạy theo encounter order. Dùng `forEachOrdered` nếu thực sự cần thứ tự hành động theo encounter order, nhưng lợi ích song song có thể giảm.

### Parallel không tự làm mọi filter nhanh hơn

Chi phí phân chia công việc, đồng bộ/gom kết quả, dữ liệu nhỏ và predicate rất rẻ có thể khiến xử lý song song chậm hơn tuần tự. Nếu predicate gọi I/O, sửa state dùng chung hoặc phụ thuộc kết quả trước đó, parallel còn có thể sai logic. Cần đo workload với benchmark và kiểm thử concurrency trước khi đổi chế độ.

Đừng dùng `parallel()` chỉ vì có nhiều phần tử. Độ rõ ràng, tính đúng đắn và khả năng bảo trì quan trọng hơn một tối ưu hóa chưa chứng minh.

## 22. Ví dụ chạy độc lập 7 — filter trong pipeline song song nhưng kết quả có thứ tự

Tạo tệp **ParallelFilterDemo.java**:

~~~java
import java.util.List;
import java.util.stream.IntStream;

public class ParallelFilterDemo {

    public static void main(String[] args) {
        List<Integer> selected = IntStream.range(0, 10)
                .parallel()
                .filter(n -> n % 3 == 0)
                .boxed()
                .toList();

        long count = IntStream.range(0, 10)
                .parallel()
                .filter(n -> n % 3 == 0)
                .count();

        System.out.println("selected=" + selected);
        System.out.println("count=" + count);
    }
}
~~~

Biên dịch/chạy trên JDK 17+:

~~~bash
javac ParallelFilterDemo.java
java ParallelFilterDemo
~~~

Stdout chính xác:

~~~text
selected=[0, 3, 6, 9]
count=4
~~~

Hai pipeline đều dùng `IntStream.range(0,10)`, tức các số 0..9. Điều kiện giữ bội của 3; bốn phần tử là 0, 3, 6, 9. Danh sách giữ encounter order; kết quả `count` đúng mà không cần biết thứ tự thread đã chạy predicate.

Nếu cần side effect cho từng phần tử, không suy từ ví dụ này rằng chúng được thực hiện theo đúng thứ tự 0,3,6,9. Đó là vấn đề tách biệt giữa **thứ tự kết quả** và **lịch thực thi**.

## 23. Trường hợp Stream rỗng

Nếu nguồn rỗng, mọi phép `filter` vẫn tạo stream rỗng:

~~~java
long count = Stream.<String>empty()
        .filter(s -> s.length() > 3)
        .count(); // 0
~~~

Predicate không có phần tử nào để kiểm tra. Các terminal trả theo hợp đồng:

- `count()` trả `0L`.
- `findFirst()` trả `Optional.empty()`.
- `anyMatch(...)` trả `false`.
- `allMatch(...)` trả `true` theo quy tắc *vacuous truth*.
- `noneMatch(...)` trả `true`.
- `toList()` trả danh sách rỗng.

Nếu nghiệp vụ yêu cầu “ít nhất một phần tử và tất cả hợp lệ”, **`allMatch` đơn độc không đủ**, vì nguồn rỗng vẫn trả true. Phải thêm kiểm tra không rỗng hoặc thiết kế một phép tổng hợp thể hiện cả hai điều kiện.

### Không có phần tử được chọn không hẳn là lỗi

`filter` có thể loại toàn bộ dữ liệu; đó là hành vi hợp lệ. Nhưng API nghiệp vụ cần quyết định “kết quả rỗng” có nghĩa không tìm thấy, không đủ điều kiện hay lỗi cấu hình. Đừng gộp các ý nghĩa khác nhau nếu ứng dụng cần thông báo khác.

## 24. Một Stream chỉ dùng cho một lượt xử lý

Không được gọi nhiều terminal trên cùng đối tượng Stream đã tiêu thụ:

~~~java
// Mảnh mã cố ý mô tả lỗi runtime:
Stream<Integer> filtered = Stream.of(1, 2, 3)
        .filter(n -> n >= 2);

long n = filtered.count();
List<Integer> list = filtered.toList(); // IllegalStateException
~~~

Code có thể biên dịch, nhưng terminal thứ hai dùng lại Stream đã tiêu thụ và thường ném `IllegalStateException`. Nếu muốn vừa số lượng vừa danh sách, một cách đơn giản là:

~~~java
List<Integer> selected = source.stream()
        .filter(predicate)
        .toList();
long count = selected.size();
~~~

Ở đây count phụ thuộc kích thước danh sách đã tạo, không cần duyệt stream lần hai. Nếu dữ liệu rất lớn và chỉ cần đếm, tránh materialize list không cần thiết: dùng `source.stream().filter(predicate).count()`.

Nếu cần nhiều kết quả tổng hợp trong một lượt mà không muốn giữ danh sách, cân nhắc `Collector` hoặc một cấu trúc tổng hợp chuyên dụng phù hợp; đừng cố giữ một Stream để gọi hai terminal.

## 25. Hiệu năng và cách sắp xếp các bước filter

### Đặt điều kiện rẻ và loại nhiều phần tử trước, khi không thay đổi semantics

Trong các predicate **thuần**, một điều kiện rẻ có khả năng loại phần tử sớm có thể làm giảm số lần gọi hàm đắt ở bước sau:

~~~java
// Mảnh mã minh họa:
requests.stream()
        .filter(Request::isValidShape)
        .filter(this::expensiveEligibilityCheck)
        .toList();
~~~

Nếu `isValidShape` nhanh và trả false cho nhiều request, các request không hợp lệ không đi đến phép kiểm tra đắt. Đây là cách mô tả **có thể** tối ưu, không bảo đảm luôn tốt hơn; cần xem phân bố dữ liệu, chi phí và khả năng thay đổi semantics.

**Đừng đổi thứ tự khi điều kiện có tiền đề:** một predicate `s -> s.length()>5` không null-safe. Nếu phải có `filter(Objects::nonNull)` trước, việc đảo thứ tự có thể gây NPE.

### Không khẳng định `filter` chạy một lần cho mỗi phần tử trong mọi tình huống

Các phép như `findFirst` hoặc `anyMatch` short-circuit. `count` trên source với một số đặc tính có thể được tối ưu; nhưng filter với predicate bất kỳ thường làm thay đổi số phần tử nên không thể mặc định đếm chỉ bằng size nguồn. Mức tối ưu thực tế thuộc về implementation và pipeline. **Không ghi audit hoặc thay đổi số dư trong predicate** rồi giả định số lần gọi luôn cố định.

### So sánh với vòng lặp

Vòng lặp:

~~~java
List<String> chosen = new ArrayList<>();
for (String item : items) {
    if (condition(item)) {
        chosen.add(item);
    }
}
~~~

Stream:

~~~java
List<String> chosen = items.stream()
        .filter(this::condition)
        .toList();
~~~

Cả hai có thể dễ hiểu. Vòng lặp phù hợp nếu có nhiều nhánh, `break`, xử lý lỗi theo bước hoặc side effect có thứ tự. Stream phù hợp nếu ý định là chọn và thu kết quả bằng predicate rõ ràng. Không coi Stream luôn nhanh hơn hoặc luôn hiện đại hơn về mọi mặt. Dùng benchmark như JMH với warmup, dữ liệu đại diện và tiêu chí đo đúng nếu hiệu năng là yêu cầu thực tế.

## 26. Lỗi thường gặp

| Lỗi/ngộ nhận | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `filter` đổi `Product` thành `String` | Filter chỉ giữ/bỏ, không đổi kiểu | Dùng `map(Product::name)` |
| `filter` xóa phần tử khỏi List nguồn | Nó tạo một Stream chọn lọc | Dùng collection operation thích hợp nếu chủ đích sửa nguồn |
| `filter` chạy ngay khi tạo pipeline | Intermediate thường lazy | Có terminal để đánh giá |
| Predicate true nghĩa là loại | Ngược lại: true là giữ | Đặt tên điều kiện theo nghĩa giữ |
| `filter(s -> !s.isBlank())` luôn an toàn | Null có thể gây NPE | Lọc null trước nếu nguồn cho phép |
| `filter(...).count()>0` luôn là cách tốt nhất để kiểm tra tồn tại | Không thể hiện rõ short-circuit | Dùng `anyMatch(predicate)` |
| `filter` tự sắp xếp | Nó không tự sort | Dùng `sorted` khi cần |
| `filter().limit(2)` giống `limit(2).filter()` | Thứ tự thay đổi ngữ nghĩa | Xem mục tiêu: chọn trước hay giới hạn trước |
| `takeWhile` giống `filter` | TakeWhile lấy tiền tố trên ordered stream | Chọn đúng API, lưu ý Java 9+ |
| Dùng `peek` để đếm số phần tử lọc được | Tác dụng phụ không có bảo đảm cần thiết | Dùng terminal `count` |
| Thêm phần tử vào nguồn trong predicate | Gây interference, có thể lỗi | Không sửa nguồn khi đang stream |
| Predicate đếm “ba phần tử đầu” bằng `AtomicInteger` | Phụ thuộc lịch thực thi, đặc biệt parallel | Dùng `limit(3)` trên ordered stream |
| `findFirst().get()` khi không có phần tử | Optional có thể empty | Dùng phương thức xử lý empty |
| Filter source rỗng luôn báo lỗi | Stream rỗng là hợp lệ | Định nghĩa chính sách nghiệp vụ riêng |
| Gọi hai terminal trên một Stream | Stream one-shot | Tạo stream mới hoặc tổng hợp một lượt |
| `parallel().forEach` luôn in theo thứ tự | Không bảo đảm thứ tự callback | Dùng `forEachOrdered` hoặc tuần tự |
| `Stream.toList()` có trong Java 8 | Được bổ sung Java 16 | Target Java 8 dùng collector phù hợp |
| `Stream.toList()` luôn mutable | Trả danh sách unmodifiable | Nếu cần sửa, dùng `Collectors.toCollection(ArrayList::new)` |

## 27. Bài tập tự luyện

**Bài 1 — Chọn điểm đạt.** Với `[4,5,9,2,10]`, dùng `filter(n -> n>=5)` để lấy điểm đạt. So sánh `>=5` với `>5`; xác định tác động của ranh giới bằng 5.

**Bài 2 — Pipeline có nhiều điều kiện.** Viết filter cho sản phẩm `available` và `price <= 100`. So sánh hai `filter` liên tiếp với một lambda dùng `&&`. Thêm điều kiện `category` có thể null và xử lý an toàn.

**Bài 3 — Null/blank.** Với `Arrays.asList(" An ", null, " ", "Binh", "An")`, tạo danh sách không null, không blank, bỏ khoảng trắng và không trùng. Giải thích thứ tự `filter`, `map`, `distinct`.

**Bài 4 — Chọn một phần tử.** Từ `[1,3,8,6]`, tìm số chẵn đầu tiên bằng `filter(...).findFirst()`. Trả `Optional<Integer>` hoặc một fallback có chủ đích. Thử dữ liệu không có số chẵn.

**Bài 5 — Tồn tại hay đếm.** Viết `anyMatch(n -> n<0)` và `filter(n -> n<0).count()`. Khi nào nên dùng mỗi cách? Test trường hợp số âm ở đầu và ở cuối list.

**Bài 6 — Dùng `Predicate`.** Khai báo `nonBlank`, `lengthAtLeast4`, kết hợp bằng `and`, rồi dùng `negate` để chia phần tử đạt/không đạt. Thử null và giải thích short-circuit.

**Bài 7 — Primitive.** Dùng `IntStream.rangeClosed(1,30)` chọn bội số của 3, tính tổng và đếm. So sánh với vòng lặp `for` tương đương. Chọn kiểu số phù hợp nếu miền rộng.

**Bài 8 — Thứ tự operation.** Cho `[9,2,8,3,4]`, so sánh `filter(even).limit(2)` với `limit(2).filter(even)`. Nêu cả hai output và giải thích khác biệt.

**Bài 9 — Short-circuit.** Đặt log trong predicate rồi dùng `findFirst` trên `Stream.of(1,2,3,4,5,6)`. Xác định phần tử được kiểm tra trong phiên bản tuần tự. Chuyển sang parallel và giải thích vì sao không dự đoán thứ tự log.

**Bài 10 — Chọn lọc và gom nhóm.** Lọc các order đã thanh toán và đạt ngưỡng tiền, sau đó `groupingBy` theo loại. Test `null` group, overflow tổng và việc giữ/không giữ thứ tự key.

**Bài 11 — Side effect.** Viết predicate không thuần làm tăng bộ đếm shared, rồi phân tích rủi ro khi thêm `parallel()`. Thay bằng `filter(condition).limit(3)` nếu yêu cầu là ba phần tử đầu đạt điều kiện.

**Bài 12 — Test filter như một quy tắc nghiệp vụ.** Xây ma trận cận `null,99,100,250,500,501` cho điều kiện giá `[100,500]`; test cả đầu vào rỗng và nhiều duplicate. Xác định khi nào cần `distinct`.

## 28. Checklist trước khi dùng `filter` trong dự án

- Predicate đã mô tả đúng quy tắc **giữ** phần tử chưa?
- Ranh giới bao gồm/loại trừ (`>` hay `>=`, `<` hay `<=`) đã được test chưa?
- Nguồn có thể chứa null không? Đã lọc null trước khi dereference chưa?
- Có nhầm nhiệm vụ filter với map, flatMap, distinct, sorted, takeWhile không?
- Nếu chỉ cần tồn tại, đã cân nhắc `anyMatch` thay vì đếm không?
- Nếu chỉ cần phần tử đầu, đã dùng `findFirst` và xử lý `Optional.empty` chưa?
- Có đang dựa vào side effect trong predicate hoặc `peek` không?
- Predicate có non-interfering và stateless; có tránh sửa nguồn khi duyệt không?
- Encounter order có thật sự được nguồn bảo đảm và có cần giữ không?
- Việc đặt `limit`/ `sorted` trước hoặc sau filter có đổi kết quả không?
- Kết quả thu bằng `toList()` có đúng hợp đồng **unmodifiable** không?
- Đã tránh gọi hai terminal trên cùng một Stream chưa?
- Trong parallel, kết quả có độc lập với thứ tự callback và shared mutable state không?
- Nếu làm thống kê, có chọn primitive stream và kiểu số đủ lớn không?
- Có test null, empty source, không phần tử nào đạt, mọi phần tử đều đạt, duplicate và cận giá trị chưa?
- API và ví dụ đang dùng có đúng mức Java của dự án (Java 8 cơ bản, `toList` Java 16+) không?

## 29. Tóm tắt

**`Stream.filter(Predicate)`** giữ phần tử có predicate trả **true**, loại phần tử trả **false** và trả về một Stream để tiếp tục pipeline. Nó là **intermediate operation lazy**, không tự thu kết quả, không chuyển kiểu phần tử và không xóa dữ liệu khỏi nguồn. `filter` có thể kết hợp với `map`, `distinct`, `sorted`, `limit`, `collect`, `toList`, `findFirst`, `anyMatch`, `count` tùy mục tiêu.

Để dùng đúng trong Java hiện đại, hãy chú ý **null**, cận điều kiện, short-circuit, encounter order, việc dùng Stream một lần, side effect và parallel. Khi logic là chọn lọc thuần, `filter` diễn đạt rất rõ; khi bài toán có nhiều bước thay đổi trạng thái và kiểm soát lỗi, một vòng lặp có thể dễ bảo trì hơn. Điều quan trọng là chọn các phần tử **đúng hợp đồng nghiệp vụ** và có test cho các trường hợp biên.
