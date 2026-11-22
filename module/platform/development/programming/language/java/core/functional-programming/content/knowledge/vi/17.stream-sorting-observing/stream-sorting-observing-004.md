# Phân biệt sắp xếp đầu vào với sắp xếp kết quả trong Java Stream

## 1. Hai câu hỏi khác nhau về sắp xếp

Trong Java, câu “sắp xếp danh sách” có thể chỉ hai hành động khác nhau:

1. **Sắp xếp ngay trên collection đầu vào**, thay đổi thứ tự các phần tử mà collection đang lưu. Ví dụ: `list.sort(comparator)`.
2. **Tạo kết quả theo thứ tự đã sắp**, giữ collection đầu vào như cũ. Ví dụ: `list.stream().sorted(comparator).toList()`.

Trong lập trình hàm bằng Stream, còn có một chiều phân biệt nữa: **đặt `sorted()` trước hay sau các phép biến đổi**. Hãy xác định kiểu và giá trị tại thời điểm sắp xếp:

```text
Nguồn List<A> → Stream<A> → sorted theo A → map(A → B) → Stream<B>
Nguồn List<A> → Stream<A> → map(A → B) → sorted theo B → Stream<B>
```

Hai chuỗi này không tự động tương đương. Nếu phép biến đổi `map` không bảo toàn quan hệ thứ tự, danh sách B được tạo ra có thể khác nhau. Ví dụ, sắp các chuỗi theo thứ tự từ điển rồi lấy độ dài không làm cho các độ dài tăng dần.

Ba thông tin cần viết rõ trước khi chọn API: **nguồn có cần giữ nguyên không, tiêu chí sắp xếp thuộc kiểu nào, và sắp xếp diễn ra ở stage nào trong pipeline?**

## 2. API và hợp đồng cần ghi nhớ

| Thao tác | Điều xảy ra | Có thay đổi List nguồn? |
| --- | --- | --- |
| `list.sort(comparator)` | Sắp xếp các phần tử của chính list; trả `void` | Có |
| `Collections.sort(list)` | Sắp xếp list theo natural order | Có |
| `list.stream().sorted()` | Tạo một stage Stream sắp theo natural order | Không |
| `list.stream().sorted(comparator)` | Tạo stage Stream sắp bằng comparator được cung cấp | Không |
| `list.stream().sorted().toList()` | Thu các phần tử theo thứ tự đã sắp thành list kết quả | Không |
| `stream.sorted(c).map(f)` | Sắp các giá trị đầu vào của `f` bằng `c` rồi mới biến đổi | Không |
| `stream.map(f).sorted(c2)` | Biến đổi trước rồi sắp các giá trị kết quả bằng `c2` | Không |

`Stream.sorted` là **stateful intermediate operation**. Chỉ tạo pipeline `stream.sorted()` chưa đồng nghĩa đã duyệt toàn bộ nguồn và hoàn tất sorting; việc xử lý thường diễn ra khi terminal operation như `toList()`, `forEachOrdered()` hoặc `findFirst()` tiêu thụ pipeline.

`List.sort` là thao tác trực tiếp trên collection; list phải hỗ trợ thay thế phần tử đúng hợp đồng. Danh sách từ `List.of(...)` là unmodifiable; danh sách trả bởi `Stream.toList()` cũng **unmodifiable** theo hợp đồng. Không gọi `sort` trực tiếp trên chúng; khi cần sửa hãy tạo `new ArrayList<>(...)`.

## 3. Ví dụ Java 17+ hoàn chỉnh: nguồn và kết quả khác nhau

Lưu tệp `SourceVsResultSortDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class SourceVsResultSortDemo {
    public static void main(String[] args) {
        List<String> source =
                new ArrayList<>(List.of("bbb", "a", "cc"));

        List<String> alphabetical =
                source.stream().sorted().toList();

        List<Integer> lengthAfterWordSort =
                source.stream()
                        .sorted()
                        .map(String::length)
                        .toList();

        List<Integer> sortedLengths =
                source.stream()
                        .map(String::length)
                        .sorted()
                        .toList();

        System.out.println("source=" + source);
        System.out.println("alphabetical=" + alphabetical);
        System.out.println("word order lengths=" + lengthAfterWordSort);
        System.out.println("sorted lengths=" + sortedLengths);

        List<String> mutableCopy = new ArrayList<>(source);
        mutableCopy.sort(Comparator.naturalOrder());
        System.out.println("copy=" + mutableCopy);
        System.out.println("source again=" + source);
    }
}
```

Biên dịch và chạy:

```bash
javac SourceVsResultSortDemo.java
java SourceVsResultSortDemo
```

Đầu ra:

```text
source=[bbb, a, cc]
alphabetical=[a, bbb, cc]
word order lengths=[1, 3, 2]
sorted lengths=[1, 2, 3]
copy=[a, bbb, cc]
source again=[bbb, a, cc]
```

**Tại sao các dòng khác nhau?**

- `alphabetical` là kết quả của sắp xếp theo natural order của `String`: chữ `a` trước `bbb`, rồi `cc`.
- `sorted().map(String::length)` sắp chuỗi trước, rồi lấy độ dài: `a → 1`, `bbb → 3`, `cc → 2`. Vì tiêu chí sắp xếp là **chuỗi**, kết quả số `[1,3,2]` không tăng dần.
- `map(String::length).sorted()` lấy độ dài trước, sau đó dùng natural order của `Integer` nên nhận `[1,2,3]`.
- `mutableCopy.sort(...)` thay đổi `mutableCopy`, nhưng không động đến `source` vì đây là hai list riêng biệt. Nếu gọi `source.sort(...)`, list `source` sẽ đổi thứ tự ngay tại chỗ.

Với cùng một reference tới list mutable, việc gọi `sort` có thể ảnh hưởng đoạn code khác đang giữ reference đó. Ngược lại, `Stream.sorted` không sửa list nguồn; nó cung cấp thứ tự trong luồng kết quả.

## 4. Sắp xếp trước và sau `map`: tiêu chí thuộc dữ liệu nào?

Giả sử các sản phẩm có tên và giá:

```text
Product(name, price)
Zebra, 20
Alpha, 90
Cable, 50
Bee,   20
```

Nếu yêu cầu là **hiển thị tên theo giá tăng dần**, trước tiên phải sắp `Product` bằng `price`, sau đó mới lấy `name`. Nếu yêu cầu là **tên theo bảng chữ cái**, hãy lấy `name` rồi mới `sorted()`.

Tạo tệp `SortProductDemo.java`:

```java
import java.util.Comparator;
import java.util.List;

public class SortProductDemo {
    record Product(String name, int price) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("Zebra", 20),
                new Product("Alpha", 90),
                new Product("Cable", 50),
                new Product("Bee", 20)
        );

        List<String> namesByPrice = products.stream()
                .sorted(Comparator.comparingInt(Product::price))
                .map(Product::name)
                .toList();

        List<String> namesAlphabetically = products.stream()
                .map(Product::name)
                .sorted()
                .toList();

        List<String> namesOriginal = products.stream()
                .map(Product::name)
                .toList();

        System.out.println("original=" + namesOriginal);
        System.out.println("by price=" + namesByPrice);
        System.out.println("by name=" + namesAlphabetically);
    }
}
```

Chạy:

```bash
javac SortProductDemo.java
java SortProductDemo
```

Output:

```text
original=[Zebra, Alpha, Cable, Bee]
by price=[Zebra, Bee, Cable, Alpha]
by name=[Alpha, Bee, Cable, Zebra]
```

Ở `namesByPrice`, comparator nhận hai đối tượng `Product` và so sánh trường giá. Sau `map(Product::name)`, stream đã là `Stream<String>`; thông tin giá không còn ở từng phần tử. Ở `namesAlphabetically`, sắp xếp diễn ra trên chính chuỗi tên.

Đừng viết:

```java
// Ý định "sắp tên theo giá" sẽ không còn đủ thông tin:
// products.stream().map(Product::name)
//         .sorted(Comparator.comparingInt(Product::price))
```

Đây là **phản ví dụ cố ý không hợp lệ về kiểu**: sau `map(Product::name)` là `Stream<String>`, trong khi `Product::price` là phương thức của `Product`, không phải `String`.

Nếu các sản phẩm bằng giá nhưng yêu cầu tên theo thứ tự alphabet, viết comparator nhiều khóa **trước khi mất thông tin Product**:

```java
Comparator<Product> byPriceThenName =
        Comparator.comparingInt(Product::price)
                  .thenComparing(Product::name);

List<String> names = products.stream()
        .sorted(byPriceThenName)
        .map(Product::name)
        .toList();
```

Đoạn này đặt trong phương thức của chương trình đã khai báo `Product` và `products`. `thenComparing` tạo khóa phụ rõ ràng; không phải cứ sắp lần thứ hai theo tên là luôn giữ nguyên quy tắc ưu tiên giá.

## 5. Vai trò của kiểu tại mỗi bước

Khi đọc biểu thức nhiều stage, hãy viết sơ đồ kiểu:

```text
products.stream()                      Stream<Product>
  .sorted(byPrice)                     Stream<Product>
  .map(Product::name)                  Stream<String>
  .toList()                             List<String>
```

So với:

```text
products.stream()                      Stream<Product>
  .map(Product::name)                  Stream<String>
  .sorted()                             Stream<String>
  .toList()                             List<String>
```

Phép `sorted()` không thay đổi kiểu phần tử của Stream. `map(...)` mới thay đổi kiểu, và do vậy cũng thay đổi miền giá trị mà comparator cần hiểu nếu đặt sorting sau `map`.

`sorted()` không đối số đòi hỏi phần tử hỗ trợ natural ordering (thông thường qua `Comparable`) và các giá trị có thể so sánh tương thích. Nếu đối tượng không so sánh được, việc xử lý có thể ném `ClassCastException`. Với một class hoặc record không có natural order, dùng `sorted(Comparator.comparing(...))` để chỉ rõ khóa.

**Phân biệt sorting theo dữ liệu gốc và sorting theo dữ liệu đã chuyển:** Nếu mapper làm mất hoặc biến đổi khóa, hai chuỗi có thể khác nhau. Chỉ khi chứng minh phép biến đổi bảo toàn thứ tự theo comparator tương ứng mới kết luận chúng cho cùng thứ tự.

## 6. `sorted()` trước hay sau `filter()`

Với điều kiện lọc thuần túy, không trạng thái, và cùng comparator trên cùng kiểu phần tử, thường có thể chuyển:

```java
numbers.stream()
        .filter(n -> n > 0)
        .sorted()
        .toList();

numbers.stream()
        .sorted()
        .filter(n -> n > 0)
        .toList();
```

Đây là đoạn minh họa trong phương thức có biến `numbers` là collection số. Hai cách cùng giữ những số dương theo thứ tự tăng dần.

**Chi phí có thể khác nhau:**

- `filter().sorted()` bỏ dữ liệu không cần trước, khiến số phần tử cần sắp xếp nhỏ hơn.
- `sorted().filter()` có thể sắp toàn bộ dữ liệu rồi mới bỏ bớt.

Nhưng không nên đổi thứ tự tùy tiện nếu Predicate hoặc Comparator có side effect, phụ thuộc trạng thái, thay đổi theo thời gian, hoặc một bước cần thông tin ở giai đoạn riêng. Trong Stream, các hàm truyền vào nên tuân thủ yêu cầu non-interference, thường stateless và không chỉnh sửa nguồn đang duyệt.

## 7. `sorted()` và `limit()`: thay vị trí có thể thay chính kết quả

Đây là trường hợp dễ nhầm nhất:

```text
sorted().limit(n):  sắp toàn bộ rồi lấy n phần tử đầu
limit(n).sorted():  lấy n phần tử đầu của nguồn rồi mới sắp nhóm đó
```

Cả hai đều tạo output có thứ tự, nhưng **không nhất thiết chứa cùng phần tử**.

Tạo tệp `SortStagePlacementDemo.java`:

```java
import java.util.List;

public class SortStagePlacementDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(9, 1, 5, 2, 4);

        System.out.println("sorted then limit=" +
                numbers.stream().sorted().limit(2).toList());

        System.out.println("limit then sorted=" +
                numbers.stream().limit(2).sorted().toList());

        System.out.println("even then sorted=" +
                numbers.stream()
                        .filter(n -> n % 2 == 0)
                        .sorted()
                        .toList());

        System.out.println("source=" + numbers);
    }
}
```

Chạy:

```bash
javac SortStagePlacementDemo.java
java SortStagePlacementDemo
```

Output:

```text
sorted then limit=[1, 2]
limit then sorted=[1, 9]
even then sorted=[2, 4]
source=[9, 1, 5, 2, 4]
```

Giải thích:

- Toàn bộ danh sách tăng dần là `[1,2,4,5,9]`, nên hai phần tử đầu sau sorting là `[1,2]`.
- Hai phần tử đầu **trước sorting** là `[9,1]`; sorting nhóm này tạo `[1,9]`.
- Lọc số chẵn trước cho `[2,4]`, rồi sorting không đổi trật tự của hai số đó.
- Dù kết quả được sắp xếp, danh sách `numbers` vẫn nguyên trạng.

Tương tự, hãy kiểm tra kỹ vị trí của `skip(n)`, `findFirst()` hoặc các thao tác chọn phần tử phụ thuộc encounter order. Nếu định nghĩa nghiệp vụ là “n sản phẩm rẻ nhất”, thứ tự thông thường phải là `sorted(byPrice).limit(n)`; nếu chỉ muốn sắp những sản phẩm đầu tiên được lấy từ nguồn, đó là `limit(n).sorted(byPrice)`.

## 8. Stability và encounter order

Một stream từ `List` có **encounter order** theo thứ tự list. Với nguồn có thứ tự như vậy, `Stream.sorted(comparator)` là **stable**: các phần tử được comparator đánh giá bằng nhau (kết quả so sánh bằng 0) giữ thứ tự tương đối từ đầu vào.

Ở ví dụ sản phẩm, `Zebra` và `Bee` cùng giá 20, nên chúng vẫn xuất hiện lần lượt Zebra rồi Bee khi sắp theo giá từ một ordered list. Với stream không có encounter order, đặc tả không bảo đảm stable sorting theo thứ tự gốc.

Khi cần output ổn định ngay cả khi nguồn thay thứ tự, có thể dùng khóa phụ:

```java
Comparator<Product> byPriceThenName =
        Comparator.comparingInt(Product::price)
                  .thenComparing(Product::name);
```

Đây là đoạn minh họa trong ngữ cảnh record `Product` đã khai báo. Tiêu chí thứ hai loại bỏ tình huống các tên khác nhau nhưng cùng giá vẫn bị xem là “bằng nhau theo comparator”.

Đừng dùng comparator có logic không nhất quán, không bắc cầu, hay phụ thuộc biến đổi ngẫu nhiên. Một thứ tự sắp xếp có ý nghĩa cần được định nghĩa rõ; nếu một comparator trả 0 cho nhiều đối tượng khác nhau, phải quyết định đó là “cùng khóa sắp xếp” được phép giữ nguyên encounter order hay cần khóa phụ.

## 9. Null, comparator, kiểu số và độ chính xác

### Null

Natural sorting với `sorted()` thường không thích hợp khi nguồn có phần tử null. Nếu hợp đồng yêu cầu giữ lại null ở cuối, dùng comparator:

```java
List<String> sorted = values.stream()
        .sorted(Comparator.nullsLast(Comparator.naturalOrder()))
        .toList();
```

Đoạn trên giả định `values` là collection chứa `String` có thể null, và có import `List`, `Comparator`. Nếu null là dữ liệu không hợp lệ, thường lọc/validate trước thay vì ngầm tạo thứ tự cho null.

### Sorting theo số

Dùng `Comparator.comparingInt(Product::price)` khi getter trả `int`. Với `long` hoặc `double` có `comparingLong` / `comparingDouble`. Không nên lấy hiệu hai giá trị để so sánh kiểu `(a, b) -> a.price() - b.price()` nếu có thể tràn số nguyên; `Integer.compare(a.price(), b.price())` hoặc factory comparator an toàn hơn.

### Natural order và thứ tự trình bày

`String.compareTo` dùng natural ordering của Java, không phải một thuật toán sắp theo quy tắc ngôn ngữ/hệ địa phương dành cho mọi kiểu tên. Nếu người dùng cần thứ tự tiếng Việt, không suy rằng `sorted()` tự cung cấp collation phù hợp; phải thiết kế comparator theo locale và yêu cầu chuẩn hóa cụ thể. Các thay đổi về collation có thể làm thứ tự khác đi mà không thay dữ liệu.

## 10. Quan sát pipeline đúng cách

Trong quá trình debug, nhiều người viết:

```java
stream.peek(System.out::println).sorted().toList();
```

Lệnh `peek` là intermediate operation dành cho quan sát, nhưng **không phù hợp làm cơ chế log nghiệp vụ bắt buộc**. Các stage trung gian có thể bị tối ưu bỏ qua khi không ảnh hưởng terminal result; với parallel stream, thời điểm/thứ tự side effect còn phức tạp hơn.

Nếu chỉ cần chứng minh thứ tự và tình trạng của nguồn, cách rõ ràng hơn là materialize hai kết quả độc lập:

```java
List<String> before = source.stream().toList();
List<String> after = source.stream().sorted().toList();

System.out.println(before);
System.out.println(after);
System.out.println(source);
```

Đây là đoạn đặt trong phương thức có biến `source` kiểu `List<String>`. Mỗi câu `source.stream()` tạo **một stream mới**. Không gọi hai terminal operation trên cùng đối tượng stream đã bị tiêu thụ.

Một điểm nữa: việc tạo pipeline `Stream<String> sorted = source.stream().sorted();` chưa nhất thiết thực hiện toàn bộ sorting. Muốn kiểm tra output, gọi terminal operation như `sorted.toList()` đúng một lần. Sau đó nếu muốn sắp lại với comparator khác, hãy dựng stream mới.

## 11. Chi phí và phạm vi dữ liệu

Sorting là một thao tác cần quan sát **toàn cục** các phần tử cần sắp, thường tốn thời gian khoảng `O(n log n)` với thuật toán sắp xếp so sánh và cần bộ nhớ để lưu thứ tự trung gian tùy implementation.

- Nếu có thể lọc trước một cách an toàn, `filter(...).sorted()` có thể giúp giảm kích thước đầu vào của sorting.
- Nếu chỉ cần lấy phần tử nhỏ nhất hoặc lớn nhất, `min(comparator)` hoặc `max(comparator)` thường thể hiện ý định phù hợp hơn việc sắp toàn bộ rồi lấy một phần tử.
- `sorted().limit(n)` trên nguồn hữu hạn thường cần xem xét toàn bộ nguồn để biết n phần tử đứng đầu toàn cục, ngay cả khi output ít.
- `limit(n).sorted()` có thể nhẹ hơn vì chỉ sắp n phần tử đầu, nhưng đó là **một câu hỏi khác về dữ liệu**.
- Trên một stream vô hạn, sorting toàn cục thường không thể hoàn tất để đưa ra phần tử đầu tiên; cần chọn cách giới hạn nguồn và thiết kế thao tác khác.
- Sử dụng parallel stream không tự động khiến sorting nhanh hơn; phải cân nhắc chi phí phối hợp, comparator và quy mô thực tế.

Chỉ điều chỉnh thứ tự các stage khi đã kiểm tra sự tương đương nghiệp vụ. Tránh dùng các side effect trong `map`, `filter` hoặc comparator để suy luận về số lần và thứ tự chạy nếu pipeline có thể được tối ưu.

## 12. Lỗi thường gặp và cách sửa

1. **Nhầm `Stream.sorted()` là thao tác sửa collection nguồn.** Hãy kiểm tra lại `source` sau terminal operation; khi muốn sửa nguồn, dùng `List.sort` trên list mutable.
2. **Gọi `sort` lên `List.of(...)` hoặc danh sách từ `Stream.toList()`.** Hai loại list này không cho phép sửa, hãy copy vào `ArrayList`.
3. **Sắp trước `map` nhưng đòi kết quả sau `map` tăng dần.** Nếu mapper không bảo toàn thứ tự, hãy sắp theo giá trị sau biến đổi hoặc xét lại tiêu chí.
4. **Sắp sau `map` nhưng cần thông tin đã bị mất.** Chuyển sorting lên trước `map` để comparator còn truy cập object gốc.
5. **Đổi chỗ `sorted()` và `limit()` mà không xét ý nghĩa.** Hai thứ tự có thể lấy hai tập phần tử khác nhau.
6. **Không nêu comparator khi đối tượng không có natural ordering.** Dùng comparator được định nghĩa theo khóa nghiệp vụ.
7. **Quên phần tử có khóa bằng nhau.** Stable sorting có điều kiện theo encounter order; dùng `thenComparing` khi cần thứ tự xác định.
8. **Sử dụng `(a, b) -> a - b` để so sánh int lớn.** Dễ tràn số; dùng `Integer.compare` hoặc factory comparator.
9. **Không xét null.** Chọn lọc null trước hoặc dùng `Comparator.nullsFirst/nullsLast` theo hợp đồng.
10. **Dùng `peek` làm thay đổi trạng thái quan trọng.** Hãy để các phép biến đổi trung gian không phụ thuộc side effect; kiểm tra kết quả thu được bằng terminal operation.
11. **Sửa danh sách nguồn trong quá trình chạy stream.** Có thể vi phạm non-interference và cho kết quả sai, exception hoặc hành vi không ổn định.
12. **Tái sử dụng stream sau `toList()`.** Mỗi pipeline mới nên bắt đầu từ stream mới.

## 13. Bài tự kiểm tra

Giả sử:

```java
List<String> words = List.of("zz", "a", "bbb");

List<Integer> a = words.stream()
        .sorted().map(String::length).toList();

List<Integer> b = words.stream()
        .map(String::length).sorted().toList();

List<String> c = words.stream()
        .sorted(Comparator.comparingInt(String::length))
        .limit(2).toList();

List<String> d = words.stream()
        .limit(2)
        .sorted(Comparator.comparingInt(String::length))
        .toList();
```

Đoạn nằm trong một phương thức Java 17 với import `List` và `Comparator`.

Câu hỏi: `a`, `b`, `c`, `d` lần lượt bằng gì? List `words` có đổi thứ tự không? Tại sao hai pipeline `c` và `d` có thể khác khi thay dữ liệu?

**Đáp án:**

- Thứ tự từ điển của chuỗi là `["a","bbb","zz"]`, nên `a = [1,3,2]`.
- Độ dài của nguồn là `[2,1,3]`; sắp số tăng dần nên `b = [1,2,3]`.
- Toàn bộ từ sắp theo độ dài rồi chọn hai từ đầu: `c = ["a","zz"]`.
- Hai từ đầu nguồn là `["zz","a"]`, sắp theo độ dài cũng cho `d = ["a","zz"]`. **Trùng kết quả trong bộ dữ liệu này là ngẫu nhiên về mặt cấu trúc phép toán**, không chứng minh hai pipeline tương đương.
- Với `List.of("long", "bbb", "a")`, sắp toàn bộ rồi lấy hai từ ngắn nhất cho `["a","bbb"]`; lấy hai từ đầu rồi sắp chỉ cho `["bbb","long"]`.
- `words` vẫn giữ thứ tự ban đầu vì tất cả pipeline chỉ sử dụng `Stream.sorted`.

## 14. Quy tắc tổng hợp

Khi cần sắp xếp trong lập trình hàm, hãy kiểm tra bốn câu:

1. **Có cần thay đổi collection nguồn?** Nếu có, dùng API sửa collection; nếu không, dùng pipeline sắp xếp kết quả.
2. **Tại thời điểm sorting, mỗi phần tử có kiểu gì?** Trước `map` là kiểu nguồn, sau `map` là kiểu đã biến đổi.
3. **Comparator đang xếp theo khóa nào?** Thứ tự từ điển, giá, độ dài, khóa phụ và null phải được quyết định rõ.
4. **Các stage như `filter`, `limit`, `skip` có đứng trước hay sau sorting?** Vị trí của chúng là một phần của ý nghĩa và chi phí xử lý.

**Ghi nhớ:** `List.sort` thay đổi danh sách; `Stream.sorted` sắp phần tử được phát ra từ pipeline mà không sửa nguồn. `sorted().map(...)` sắp **đầu vào của phép biến đổi**, còn `map(...).sorted()` sắp **kết quả của phép biến đổi**. Chọn đúng vị trí sorting trước khi tối ưu hoặc rút gọn code.

**Tài liệu tham khảo:** Java SE API: `List.sort`, `Stream.sorted`, `Stream.toList`, `Comparator`; Java Stream package specification về stateful intermediate operations, ordering và non-interference.