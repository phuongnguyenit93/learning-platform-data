# `findFirst()` và `findAny()` trong Java Stream

## 1. Mục tiêu: tìm một phần tử thay vì thu thập toàn bộ

Trong Stream API, `findFirst()` và `findAny()` là hai **thao tác kết thúc** (*terminal operations*) dùng để tìm một phần tử của luồng. Cả hai có thể **dừng sớm** (*short-circuit*): khi đã có thể trả kết quả, pipeline không nhất thiết phải duyệt hết nguồn.

Ví dụ, cần tìm sản phẩm đầu tiên có giá từ 100 trở lên:

~~~java
record Product(String code, int price) {}

List<Product> products = List.of(
        new Product("A", 80),
        new Product("B", 120),
        new Product("C", 150));

Optional<Product> firstEligible = products.stream()
        .filter(p -> p.price() >= 100)
        .findFirst();

System.out.println(firstEligible.map(Product::code).orElse("none")); // B
~~~

`filter` quyết định phần tử nào đạt điều kiện. `findFirst` chọn phần tử phù hợp **đầu tiên theo encounter order** nếu nguồn có thứ tự. Kết quả không phải trực tiếp một `Product` mà là `Optional<Product>`, bởi có thể không có sản phẩm phù hợp.

Nếu yêu cầu chỉ là “lấy **một** sản phẩm bất kỳ đạt điều kiện”, không quan tâm sản phẩm nào, `findAny()` biểu đạt ý định tốt hơn:

~~~java
Optional<Product> anyEligible = products.stream()
        .filter(p -> p.price() >= 100)
        .findAny();
~~~

`findAny()` không hứa trả `"B"`. Nó có thể trả một phần tử phù hợp bất kỳ; trong nhiều trường hợp chạy tuần tự bạn có thể *quan sát thấy* phần tử đầu, nhưng không nên dựa vào đó làm hợp đồng chương trình.

**Phạm vi cần nắm:** kiểu trả về, thứ tự phần tử, hành vi dừng sớm, chạy tuần tự và song song, cách xử lý khi rỗng hoặc có null, lựa chọn giữa hai thao tác, cũng như những nhầm lẫn khi dùng chúng trong pipeline Stream.

## 2. Chữ ký API và kết quả Optional

Trên `java.util.stream.Stream<T>`:

~~~java
Optional<T> findFirst();
Optional<T> findAny();
~~~

Chữ ký không có tham số: việc **lọc trước khi tìm** được mô tả bằng các thao tác trung gian như `filter`, `map`, `distinct`, `sorted`.

~~~java
List<String> words = List.of("Java", "API", "Stream");

Optional<String> first = words.stream().findFirst();
Optional<String> anyLong = words.stream()
        .filter(s -> s.length() > 4)
        .findAny();
~~~

Nếu luồng rỗng, cả hai trả `Optional.empty()`. Nếu luồng có phần tử được chọn, kết quả là `Optional` chứa phần tử đó. Ví dụ:

~~~java
System.out.println(Stream.<String>empty().findFirst().isEmpty()); // true
System.out.println(Stream.<String>empty().findAny().isPresent()); // false
~~~

Không nên gọi `get()` ngay nếu chưa biết Optional có giá trị, vì `Optional.get()` có thể ném `NoSuchElementException`. Những cách thường dùng:

~~~java
String firstName = words.stream()
        .findFirst()
        .orElse("unknown");

words.stream()
        .findFirst()
        .ifPresent(System.out::println);

String required = words.stream()
        .findFirst()
        .orElseThrow(() -> new IllegalStateException("No name available"));
~~~

- `orElse(value)` trả giá trị thay thế nếu Optional rỗng.
- `orElseGet(supplier)` chỉ gọi supplier để tạo giá trị thay thế khi Optional rỗng, phù hợp với phép tính tốn kém.
- `ifPresent(consumer)` chỉ chạy hành động khi có giá trị.
- `orElseThrow(...)` diễn đạt hợp đồng rằng việc không tìm thấy là lỗi nghiệp vụ.

Với `IntStream`, `LongStream`, `DoubleStream`, kiểu trả về tương ứng là **`OptionalInt`, `OptionalLong`, `OptionalDouble`**:

~~~java
OptionalInt firstPositive = IntStream.of(-2, 0, 7, 9)
        .filter(n -> n > 0)
        .findFirst();

System.out.println(firstPositive.orElse(-1)); // 7
~~~

`OptionalInt` có `getAsInt()` và `orElse(int)`, khác với `Optional<Integer>`. Không giả định `IntStream.findFirst()` trả `Optional<Integer>`; API nguyên thủy tránh boxing trung gian khi có thể.

## 3. Encounter order: “đầu tiên” nghĩa là gì?

**Encounter order** là thứ tự phần tử do nguồn và pipeline xác định. Ví dụ:

- `List`, array, `IntStream.range`, `Stream.of(...)` thường có thứ tự nguồn rõ ràng.
- `HashSet` không cam kết thứ tự encounter của phần tử; thứ tự quan sát trong một lần chạy không phải hợp đồng.
- `TreeSet` có thứ tự lặp theo comparator/sắp xếp của tập; stream từ nó có thứ tự tương ứng.
- Thao tác `sorted` tạo thứ tự theo comparator/sắp xếp, còn `unordered()` bỏ yêu cầu giữ encounter order trong phần còn lại của pipeline.

Với nguồn có thứ tự:

~~~java
List<String> letters = List.of("C", "A", "B");

System.out.println(letters.stream()
        .findFirst().orElse("-"));         // C

System.out.println(letters.stream()
        .sorted()
        .findFirst().orElse("-"));         // A
~~~

Trong ví dụ trên, `findFirst` chọn phần tử đầu tiên **của luồng tại vị trí gọi terminal**: trước `sorted` là `"C"`; sau `sorted` là `"A"`. Nó không tự tìm giá trị nhỏ nhất, mà tôn trọng thứ tự đã xác định.

Với `Stream` **không có encounter order**, `findFirst` không có “đầu tiên” mang ý nghĩa ổn định để tôn trọng. Theo hợp đồng API, lúc này nó có thể trả phần tử bất kỳ. Do đó, `findFirst()` không biến một `HashSet` thành nguồn có thứ tự.

## 4. `findFirst()`: bảo đảm thứ tự khi thứ tự tồn tại

`findFirst()` có ý nghĩa rõ ràng khi muốn phần tử phù hợp sớm nhất theo thứ tự nguồn.

~~~java
List<Integer> scores = List.of(40, 55, 70, 85);

Optional<Integer> firstPass = scores.stream()
        .filter(score -> score >= 60)
        .findFirst();

System.out.println(firstPass.orElse(-1)); // 70
~~~

Bởi `scores` là `List` có thứ tự, `70` là phần tử đầu tiên đạt điều kiện. `85` cũng phù hợp nhưng không được chọn.

### 4.1. Kết hợp `map`, `filter` và `findFirst`

~~~java
List<String> raw = List.of("  ", " Java ", " API ");

Optional<String> firstNonBlank = raw.stream()
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .findFirst();

System.out.println(firstNonBlank.orElse("none")); // Java
~~~

Dòng dữ liệu:

~~~text
"  "     -> trim: ""      -> filter: bỏ
" Java " -> trim: "Java"  -> filter: giữ -> findFirst: trả "Java"
" API "  -> không nhất thiết cần xử lý trong pipeline tuần tự này
~~~

`findFirst` là terminal nên trả `Optional<String>`, không trả `Stream<String>`. Nếu muốn xử lý thêm sau khi tìm, hãy dùng API của Optional như `map`, `filter`, `flatMap` hoặc `stream`, hoặc xây dựng pipeline mới từ nguồn.

### 4.2. Khi cần giá trị nhỏ nhất thay vì đầu tiên

Không thay thế `min()` bằng `findFirst()` trên nguồn chưa sắp xếp:

~~~java
List<Integer> values = List.of(9, 3, 5);

int first = values.stream().findFirst().orElseThrow(); // 9
int minimum = values.stream().min(Integer::compare).orElseThrow(); // 3
~~~

Có thể `sorted().findFirst()` để chọn phần tử nhỏ nhất, nhưng thao tác `sorted` thường yêu cầu xử lý/sắp xếp dữ liệu và có chi phí cao hơn tìm trực tiếp bằng `min` khi chỉ cần một cực trị. Chọn API mô tả đúng mục đích.

## 5. `findAny()`: một phần tử bất kỳ, không cam kết là phần tử đầu

`findAny()` được thiết kế với ngữ nghĩa cố ý **không tất định** về lựa chọn phần tử khi nhiều phần tử phù hợp. Điều này cho phép triển khai tận dụng việc thực thi song song hoặc nguồn không có thứ tự.

~~~java
List<Integer> numbers = List.of(10, 20, 30, 40);

Optional<Integer> chosen = numbers.parallelStream()
        .filter(n -> n >= 20)
        .findAny();

boolean valid = chosen
        .map(n -> n >= 20)
        .orElse(false);

System.out.println(valid); // true
~~~

Trong chương trình này, không nên in kỳ vọng cứng `20`, `30` hay `40` vì phần tử được chọn không được bảo đảm. Ta kiểm tra tính chất bắt buộc: giá trị hiện diện phải thỏa điều kiện lọc.

`findAny()` **không đồng nghĩa với** lựa chọn ngẫu nhiên phân phối đều. Không có hợp đồng nào về xác suất, thứ tự thay phiên, mức độ đa dạng hay việc mỗi lần gọi sẽ trả một phần tử khác. Cùng dữ liệu và cùng runtime có thể liên tục trả một giá trị như nhau.

Ngay cả trên **sequential stream có encounter order**, `findAny` vẫn không bảo đảm chọn phần tử đầu. Nhiều implementation có thể hoạt động như `findFirst` trong tình huống đơn giản, nhưng code không được dựa vào hành vi quan sát đó.

### 5.1. Khi chỉ có một ứng viên, kết quả là xác định

~~~java
List<String> words = List.of("apple", "key", "banana");

String found = words.stream()
        .filter("key"::equals)
        .findAny()
        .orElse("missing");

System.out.println(found); // key
~~~

Chỉ có một phần tử phù hợp, nên `findAny` nếu hoàn thành thành công với giá trị sẽ chọn `"key"`. Đây là ví dụ có kết quả in ổn định mà vẫn dùng đúng ý nghĩa “bất kỳ”.

## 6. Dừng sớm và lazy evaluation

Cả `findFirst` và `findAny` đều là **short-circuit terminal operations**. Nếu đã có thể xác định kết quả, chúng không yêu cầu xử lý tất cả phần tử nguồn.

Ví dụ tuần tự:

~~~java
List<String> items = List.of("no", "yes", "later");

Optional<String> found = items.stream()
        .filter("yes"::equals)
        .findFirst();

System.out.println(found.orElse("-")); // yes
~~~

Về logic, pipeline tuần tự có thể dừng sau khi tìm được `"yes"`. Phần tử `"later"` không cần được kiểm tra để quyết định kết quả. Tuy nhiên, hãy phân biệt **ngữ nghĩa kết quả** với **bảo đảm số lần chạy callback**: API không cho phép dựa vào side effect trong các intermediate operations để xác định tính đúng của toàn chương trình.

Trong parallel pipeline, một số worker có thể đã hoặc đang xử lý phần tử khác trước khi terminal lựa chọn được kết quả. Vì thế, dù terminal dừng sớm theo nghĩa logic, không được mặc định:

- Mapper và predicate chỉ chạy một lần.
- Callback thực thi tuần tự từ trái sang phải trong mọi chế độ.
- `findAny` trả phần tử “được xử lý đầu tiên” theo đồng hồ thực.
- Thêm `peek` để log sẽ có đúng một dòng.

### 6.1. Stream vô hạn

Với nguồn vô hạn, short-circuit rất hữu ích:

~~~java
int firstMultipleOfSeven = IntStream.iterate(1, n -> n + 1)
        .filter(n -> n % 7 == 0)
        .findFirst()
        .orElseThrow();

System.out.println(firstMultipleOfSeven); // 7
~~~

Đây là ví dụ tuần tự xác định, vì điều kiện có phần tử đáp ứng ở vị trí hữu hạn. Nhưng **short-circuit không bảo đảm mọi pipeline sẽ kết thúc**: nếu stream vô hạn mà không có phần tử nào thỏa điều kiện, việc tìm có thể không hoàn tất. Ví dụ `IntStream.iterate(1, n -> n + 1).filter(n -> n < 0).findFirst()` không nên dùng làm demo kết thúc, vì kỳ vọng dừng là không có cơ sở.

Với song song, infinite sources và một số stateful operations như `sorted`, `distinct`, `limit` có thể tương tác phức tạp; không dùng “findFirst là short-circuit” làm lý do chắc chắn rằng mọi tổ hợp đều nhẹ hoặc sẽ dừng.

## 7. Song song: khác biệt quan trọng nhất

So sánh hai pipeline:

~~~java
List<Integer> values = IntStream.rangeClosed(1, 1_000)
        .boxed()
        .toList();

Optional<Integer> first = values.parallelStream()
        .filter(n -> n > 500)
        .findFirst();

Optional<Integer> any = values.parallelStream()
        .filter(n -> n > 500)
        .findAny();

System.out.println(first.orElse(-1)); // 501
System.out.println(any.isPresent());  // true
~~~

`findFirst` phải trả `501` vì nguồn là danh sách có thứ tự và `501` là phần tử phù hợp sớm nhất. `findAny` chỉ phải trả một số thuộc tập `501..1000`, nên ta chỉ in `isPresent()` trong ví dụ có stdout ổn định.

### 7.1. Vì sao `findAny` có thể thuận lợi cho parallel?

Để trả phần tử đầu theo encounter order, `findFirst` có thể phải phối hợp giữa các phần việc, xác nhận không còn phần tử thỏa điều kiện nào nằm trước kết quả tạm thời. `findAny` được phép nhận một phần tử phù hợp từ bất kỳ nhánh nào, nên có thể tránh một phần ràng buộc thứ tự.

Đây là **khả năng tối ưu**, không phải lời hứa `findAny` luôn nhanh hơn `findFirst`. Hiệu năng phụ thuộc kích thước và đặc điểm nguồn, độ tốn kém của predicate, khả năng chia nguồn, số lõi, mức tải và chi phí điều phối. Với pipeline nhỏ, tuần tự có thể nhanh hơn song song.

### 7.2. `unordered()` có ý nghĩa gì?

~~~java
Optional<Integer> result = values.parallelStream()
        .unordered()
        .filter(n -> n > 500)
        .findFirst();
~~~

`unordered()` cho phép pipeline **không còn phải duy trì encounter order**. Trong ngữ cảnh đó, lời gọi `findFirst` không bắt buộc trả `501` nữa, vì luồng đã không có thứ tự gặp phần tử để làm cơ sở chọn “đầu tiên”. Nếu thực sự chỉ cần phần tử bất kỳ, `findAny` diễn đạt ý định trực tiếp hơn.

Ngược lại, nếu nghiệp vụ yêu cầu “bản ghi đầu tiên theo thứ tự ưu tiên”, không nên thêm `unordered()` để tối ưu khi điều đó đánh đổi tính đúng.

### 7.3. Thứ tự kết quả và thứ tự thực thi khác nhau

Một pipeline parallel có encounter order vẫn có thể thực thi callback trên các phần tử ở thứ tự khác nhau. `findFirst` bảo đảm **phần tử được chọn đúng thứ tự nguồn**, không bảo đảm predicate chỉ được chạy từ đầu đến vị trí kết quả và dừng mọi thread ngay lập tức.

Vì vậy, tránh dùng callback có side effect để đếm/ghi nhận chính xác số phần tử được kiểm tra. Nếu muốn ghi metric số lượng dữ liệu, hãy dùng thiết kế metric độc lập với lựa chọn phần tử của terminal.

## 8. Xử lý khi không tìm thấy: Optional

Nếu lọc hết phần tử, cả hai trả Optional rỗng:

~~~java
List<Integer> numbers = List.of(1, 3, 5);

Optional<Integer> even = numbers.stream()
        .filter(n -> n % 2 == 0)
        .findFirst();

System.out.println(even.isEmpty()); // true
System.out.println(even.orElse(-1)); // -1
~~~

Một số cách dùng phù hợp theo nghiệp vụ:

~~~java
// Dùng fallback đơn giản.
int number = even.orElse(0);

// Tính fallback tốn kém chỉ khi cần.
int fromFallback = even.orElseGet(() -> 0);

// Không tìm thấy là trường hợp cần xử lý lỗi.
int required = even.orElseThrow(
        () -> new IllegalArgumentException("No matching element"));
~~~

Dòng `orElseThrow` trong ví dụ trên sẽ ném ngoại lệ vì `even` rỗng; đừng chạy nó trong chương trình demo được kỳ vọng có stdout bình thường nếu không chủ ý xử lý lỗi. `orElseGet(() -> 0)` minh họa lambda Supplier nhưng nếu fallback chỉ là hằng số `0` thì `orElse(0)` thường rõ hơn.

Một tình huống khác:

~~~java
Optional<String> first = Stream.of("An", "Binh")
        .filter(s -> s.length() >= 3)
        .findFirst();

String label = first.map(String::toUpperCase).orElse("NONE");
System.out.println(label); // BINH
~~~

`Optional.map` ở đây chạy **sau khi** đã chọn một phần tử. Nó không phải `Stream.map` áp dụng cho từng phần tử trước `findFirst`. Phân biệt container đứng trước dấu chấm để hiểu dữ liệu còn lại ở giai đoạn nào.

## 9. Null và lỗi: có thể ném NullPointerException

Một điểm dễ bỏ qua: `findFirst` và `findAny` yêu cầu kết quả hiện diện phải được biểu diễn bằng `Optional<T>`, mà `Optional` không chứa giá trị `null`. Vì vậy **nếu phần tử được chọn là null**, thao tác tìm có thể ném `NullPointerException`.

~~~java
List<String> values = java.util.Arrays.asList(null, "Java");

// values.stream().findFirst(); // NullPointerException:
// phần tử đầu tiên của List có thứ tự là null.
~~~

Để bỏ null:

~~~java
Optional<String> firstNonNull = values.stream()
        .filter(java.util.Objects::nonNull)
        .findFirst();

System.out.println(firstNonNull.orElse("none")); // Java
~~~

Với `findAny`, nếu nguồn có null, không thể giả định nó sẽ “tự bỏ qua” null. Nó có thể chọn null và lỗi. Hãy xử lý điều kiện null trước khi gọi terminal, hoặc sử dụng nguồn đã bảo đảm non-null.

Nếu muốn biến **một giá trị nullable** thành luồng 0 hoặc 1 phần tử, Java 9+ có `Stream.ofNullable(value)`:

~~~java
String value = null;
System.out.println(Stream.ofNullable(value).findFirst().isEmpty()); // true
~~~

`Stream.ofNullable(null)` là Stream rỗng; trong khi đó `Stream.of((String) null)` tạo Stream có một phần tử null, và `findFirst` trên đó có thể ném lỗi.

Ngoài lỗi null, mapper/predicate trước terminal có thể ném ngoại lệ. `findFirst` và `findAny` **không tự biến exception thành Optional.empty()`. Optional rỗng có nghĩa không có phần tử được chọn trong quá trình kết thúc bình thường, không đồng nghĩa “bất kỳ lỗi nào cũng được bỏ qua”.

## 10. Những thao tác khác dễ nhầm

| Mục đích | API | Kết quả |
| --- | --- | --- |
| Lấy phần tử đầu theo encounter order | `findFirst()` | `Optional<T>` |
| Lấy một phần tử bất kỳ phù hợp | `findAny()` | `Optional<T>` |
| Kiểm tra có ít nhất một phần tử thỏa điều kiện | `anyMatch(predicate)` | `boolean` |
| Kiểm tra mọi phần tử thỏa điều kiện | `allMatch(predicate)` | `boolean` |
| Kiểm tra không phần tử nào thỏa điều kiện | `noneMatch(predicate)` | `boolean` |
| Tìm phần tử nhỏ nhất/lớn nhất | `min(comparator)` / `max(comparator)` | `Optional<T>` |
| Lấy tối đa `n` phần tử | `limit(n)` | `Stream<T>` |
| Tạo danh sách tất cả phần tử | `toList()` | `List<T>` |
| Đếm phần tử | `count()` | `long` |

### 10.1. Khi chỉ hỏi “có tồn tại không”, `anyMatch` thường rõ hơn

~~~java
List<String> users = List.of("An", "Binh", "Chi");

boolean exists = users.stream()
        .anyMatch(s -> s.startsWith("B"));

System.out.println(exists); // true
~~~

Có thể viết:

~~~java
boolean exists = users.stream()
        .filter(s -> s.startsWith("B"))
        .findAny()
        .isPresent();
~~~

Nhưng nếu chỉ cần boolean, `anyMatch` biểu đạt trực tiếp mục tiêu. Khi cần **đối tượng phù hợp** cho bước sau, `findFirst` hoặc `findAny` phù hợp hơn.

### 10.2. `limit(1)` không cùng kiểu kết quả với `findFirst()`

~~~java
Stream<String> firstAsStream = Stream.of("A", "B").limit(1);
Optional<String> firstAsOptional = Stream.of("A", "B").findFirst();
~~~

`limit(1)` là thao tác trung gian trả `Stream<String>` (để kết hợp tiếp). `findFirst()` là terminal trả `Optional<String>` và tiêu thụ pipeline. Không thay tùy tiện nếu phần xử lý sau mong một kiểu khác.

### 10.3. `findFirst` không tự sắp xếp

~~~java
int first = Stream.of(8, 3, 5).findFirst().orElseThrow(); // 8
int min = Stream.of(8, 3, 5).min(Integer::compare).orElseThrow(); // 3
~~~

Nếu yêu cầu là “đầu tiên theo thứ tự ưu tiên”, hãy kiểm soát thứ tự nguồn hoặc sắp xếp có chủ đích. Nếu yêu cầu là cực trị, dùng `min`/`max` thường thích hợp hơn.

### 10.4. Stream không sử dụng lại sau terminal

~~~java
Stream<String> once = Stream.of("A", "B");
String selected = once.findFirst().orElse("-");

// Không gọi tiếp once.findAny(): stream đã được tiêu thụ.
~~~

Muốn dùng hai terminal độc lập, tạo **hai stream mới** từ nguồn có thể sử dụng lại (như `List`), hoặc thiết kế phép tổng hợp phù hợp.

## 11. Ví dụ Java 17+ đầy đủ và stdout có thể kiểm chứng

Lưu thành **`FindOperationsDemo.java`**:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class FindOperationsDemo {
    record Item(String code, int price) {}

    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("A", 40),
                new Item("B", 70),
                new Item("C", 90),
                new Item("D", 60));

        Optional<Item> first = items.stream()
                .filter(item -> item.price() >= 60)
                .findFirst();
        System.out.println("first=" +
                first.map(Item::code).orElse("none"));

        Optional<Item> any = items.parallelStream()
                .filter(item -> item.price() >= 60)
                .findAny();
        boolean anyEligible = any
                .map(item -> item.price() >= 60)
                .orElse(false);
        System.out.println("anyEligible=" + anyEligible);

        String singleAny = Stream.of("a", "key", "b")
                .filter("key"::equals)
                .findAny()
                .orElse("missing");
        System.out.println("singleAny=" + singleAny);

        boolean empty = Stream.<String>empty()
                .findFirst()
                .isEmpty();
        System.out.println("empty=" + empty);

        String sortedFirst = List.of("z", "a", "b")
                .stream()
                .sorted()
                .findFirst()
                .orElse("-");
        System.out.println("sortedFirst=" + sortedFirst);

        OptionalInt primitive = IntStream.of(2, 5, 8)
                .filter(n -> n > 5)
                .findFirst();
        System.out.println("primitiveFirst=" + primitive.orElse(-1));

        int firstMultipleOfSeven = IntStream.iterate(1, n -> n + 1)
                .filter(n -> n % 7 == 0)
                .findFirst()
                .orElseThrow();
        System.out.println("multipleOfSeven=" + firstMultipleOfSeven);

        boolean exists = items.stream()
                .anyMatch(item -> item.price() >= 80);
        System.out.println("exists80=" + exists);

        Optional<String> firstNonNull = Stream.of("A", "B", "C")
                .filter(s -> s.startsWith("B"))
                .findFirst();
        System.out.println("firstB=" + firstNonNull.orElse("-"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FindOperationsDemo.java
java FindOperationsDemo
~~~

**Stdout xác định:**

~~~text
first=B
anyEligible=true
singleAny=key
empty=true
sortedFirst=a
primitiveFirst=8
multipleOfSeven=7
exists80=true
firstB=B
~~~

Giải thích:

1. `first=B` vì item `B` là phần tử đầu tiên có giá ít nhất 60 trong danh sách có thứ tự.
2. `anyEligible=true`: parallel `findAny` có thể chọn `B`, `C` hoặc `D`, nhưng mọi ứng viên đều đáp ứng điều kiện. Ta cố ý không in mã được chọn để tránh phụ thuộc scheduling.
3. `singleAny=key` vì chỉ có đúng một ứng viên sau `filter`.
4. `empty=true` vì luồng rỗng dẫn tới `Optional.empty()`.
5. `sortedFirst=a` vì `sorted()` xác định thứ tự mới trước khi tìm.
6. `primitiveFirst=8` lấy `OptionalInt` từ `IntStream`; số 8 là ứng viên duy nhất lớn hơn 5.
7. `multipleOfSeven=7` minh họa terminal short-circuit trên luồng phát sinh bằng `iterate`, với điều kiện có lời giải hữu hạn.
8. `exists80=true` minh họa trường hợp chỉ cần boolean thì dùng `anyMatch`.
9. `firstB=B` cho thấy lọc và tìm phần tử đầu theo encounter order.

Không có phụ thuộc bên ngoài; ví dụ dùng JDK 17+ và không in chi tiết lựa chọn không tất định của `parallelStream().findAny()`.

## 12. Khi nào dùng `findFirst` và khi nào dùng `findAny`?

**Dùng `findFirst`** khi thứ tự có ý nghĩa nghiệp vụ, chẳng hạn:

- Bản ghi đầu tiên theo thời điểm, thứ tự ưu tiên hoặc thứ tự sắp xếp đã xác định.
- Quy tắc “lấy ứng viên phù hợp xuất hiện sớm nhất”.
- Giao diện cần tái lập lựa chọn ổn định giữa các lần chạy trên cùng nguồn có thứ tự.

~~~java
Optional<String> preferred = List.of("basic", "pro", "enterprise")
        .stream()
        .filter(s -> !s.equals("basic"))
        .findFirst();

// preferred chứa "pro".
~~~

**Dùng `findAny`** khi chỉ cần một ứng viên hợp lệ và không có quy tắc ưu tiên về thứ tự; điều này đặc biệt hợp lý với parallel stream hoặc nguồn vốn không có encounter order.

~~~java
Optional<Integer> anyEven = List.of(1, 2, 3, 4)
        .parallelStream()
        .filter(n -> n % 2 == 0)
        .findAny();

// Hợp đồng: có thể là 2 hoặc 4, không chọn cụ thể.
~~~

Nếu nghiệp vụ thực sự cần một kết quả “ngẫu nhiên”, hãy dùng cơ chế random rõ ràng với phân phối mong muốn; `findAny` không phải random selection API.

Nếu nguồn là `HashSet` và cần “phần tử đầu” có ý nghĩa, hãy xác định comparator hoặc chuyển sang cấu trúc có thứ tự trước. Nếu thêm `sorted`, cân nhắc chi phí, vì sắp xếp toàn bộ để lấy một cực trị thường không cần thiết.

## 13. Những lỗi thường gặp

| Lỗi | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Mặc định `findAny` luôn trả phần tử đầu trên sequential stream | API không hứa điều này | Dùng `findFirst` khi cần encounter order |
| Mặc định `findFirst` luôn cho cùng kết quả trên `HashSet` | Nguồn không có encounter order được bảo đảm | Chọn nguồn có thứ tự hoặc sắp xếp rõ ràng |
| In một giá trị cụ thể từ parallel `findAny` làm expected output | Lựa chọn có thể thay đổi theo lịch thực thi | Kiểm tra thuộc tính của phần tử trả về |
| Gọi `optional.get()` khi không có giá trị | Ném `NoSuchElementException` | Dùng `orElse`/`orElseThrow`/`ifPresent` phù hợp |
| Coi Optional rỗng là ngoại lệ bị nuốt | Lỗi trong callback không thành Optional.empty | Xử lý ngoại lệ theo hợp đồng riêng |
| Cho rằng kết quả `null` được Optional bọc an toàn | Chọn phần tử null gây `NullPointerException` | Lọc null hoặc chuẩn hóa dữ liệu |
| Đặt side effect bắt buộc trong `filter`/`map` rồi gọi `findFirst` | Pipeline có thể dừng sớm; parallel có thể xử lý nhiều nhánh | Tránh thiết kế side effect phụ thuộc số lần gọi callback |
| Dùng `findFirst` để lấy min của nguồn chưa sắp xếp | “Đầu tiên” khác “nhỏ nhất” | Dùng `min` hoặc sắp xếp theo nghiệp vụ |
| Dùng `findAny().isPresent()` khi chỉ cần kiểm tra điều kiện | Vẫn hợp lệ nhưng dài hơn, thiếu ý định trực tiếp | Dùng `anyMatch(predicate)` |
| Gọi terminal thứ hai trên cùng Stream | Stream đã bị tiêu thụ | Tạo Stream mới từ nguồn |
| Nghĩ short-circuit bảo đảm hoàn thành trên luồng vô hạn | Có thể không có phần tử thỏa điều kiện | Bảo đảm điều kiện dừng, dùng `limit` khi phù hợp |
| Dùng `unordered()` rồi vẫn mong `findFirst` trả phần tử ưu tiên | Đã bỏ ràng buộc encounter order | Giữ nguồn có thứ tự và dùng `findFirst` |

## 14. Bài tập tự kiểm tra

**Câu 1.** Với `List.of(4, 8, 12)`, `stream().filter(n -> n > 5).findFirst()` trả gì?

**Đáp án:** `Optional[8]`. Danh sách có thứ tự và 8 là phần tử đầu tiên thỏa điều kiện.

**Câu 2.** Với cùng danh sách, `parallelStream().filter(n -> n > 5).findAny()` có bắt buộc trả 8 không?

**Đáp án:** Không. Nó có thể trả 8 hoặc 12; chỉ có ràng buộc phần tử được chọn thỏa predicate.

**Câu 3.** Vì sao `findFirst` trên `Set` không có thứ tự không đồng nghĩa với “phần tử nhỏ nhất”?

**Đáp án:** Set không bảo đảm encounter order; tìm đầu tiên không phải so sánh giá trị. Nếu cần nhỏ nhất, dùng `min(comparator)`.

**Câu 4.** `Stream.empty().findFirst()` trả gì?

**Đáp án:** `Optional.empty()` (khi kiểu phần tử được suy ra trong ngữ cảnh), không trả `null`.

**Câu 5.** Có `IntStream.range(1, 10)`, tìm số đầu tiên chia hết cho 3. Dùng gì và kiểu kết quả ra sao?

**Đáp án:** `IntStream.range(1, 10).filter(n -> n % 3 == 0).findFirst()` trả `OptionalInt` chứa 3.

**Câu 6.** Có 1 triệu bản ghi trong parallel stream. Khi `findFirst` tìm được kết quả ở vị trí sớm, predicate có chắc chỉ chạy tới đúng vị trí ấy không?

**Đáp án:** Không. Parallel pipeline có thể xử lý thêm các phần tử ở nhánh khác trước khi xác nhận kết quả đầu tiên theo encounter order; không được dựa vào số lần callback để suy ra số phần tử được xét.

**Câu 7.** Muốn biết có ít nhất một người từ 18 tuổi trở lên, không cần lấy người đó. Dùng gì?

**Đáp án:** `people.stream().anyMatch(p -> p.age() >= 18)` diễn đạt trực tiếp câu hỏi tồn tại. Nếu cần trả chính người phù hợp, dùng `findFirst` hoặc `findAny` sau `filter`.

**Câu 8.** `Stream.ofNullable(null).findAny()` và `Stream.of((String) null).findAny()` khác nhau thế nào?

**Đáp án:** Biểu thức đầu tìm trên Stream rỗng nên trả Optional rỗng; biểu thức sau có một phần tử null được chọn và có thể ném `NullPointerException`.

## 15. Ghi nhớ

`findFirst()` và `findAny()` đều là terminal operations trả **`Optional<T>`** (hoặc Optional nguyên thủy tương ứng) và có thể short-circuit:

- **`findFirst()`** chọn phần tử đầu tiên theo **encounter order**, nếu luồng có thứ tự.
- **`findAny()`** chọn một phần tử bất kỳ, **không cam kết** là phần tử đầu, không phải phép chọn ngẫu nhiên có phân phối xác định.
- Khi luồng rỗng, trả `Optional.empty()`; nếu phần tử được chọn là `null`, có thể ném `NullPointerException`.
- Với parallel stream, `findFirst` có thể cần duy trì ràng buộc thứ tự, trong khi `findAny` được tự do hơn; hiệu năng thực tế phải kiểm chứng.
- Short-circuit không có nghĩa callback sẽ được gọi đúng một số lần cố định, cũng không bảo đảm mọi nguồn vô hạn đều kết thúc.
- Nếu chỉ cần câu trả lời boolean “có phần tử phù hợp không?”, **`anyMatch`** thường rõ nghĩa hơn.

Hãy chọn `findFirst` khi thứ tự là yêu cầu thực sự, chọn `findAny` khi chỉ cần bất kỳ phần tử phù hợp nào, và xử lý Optional/exception theo hợp đồng rõ ràng.
