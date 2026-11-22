# map và chuyển đổi giá trị trong Java Stream

## 1. Bài toán: mỗi phần tử đầu vào thành một giá trị đầu ra

Trong Java Stream API, `map` là thao tác trung gian dùng để **biến đổi giá trị** của các phần tử. Chẳng hạn, từ danh sách tên tạo danh sách độ dài, từ đơn hàng tạo DTO hiển thị, từ chuỗi thô tạo chuỗi chuẩn hóa, hoặc từ đối tượng nghiệp vụ chỉ lấy một trường cần thiết.

Ví dụ:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> words = Arrays.asList("Java", "Go", "Kotlin");

List<Integer> lengths = words.stream()
        .map(String::length)
        .collect(Collectors.toList());

System.out.println(lengths); // [4, 2, 6]
```

Mỗi `String` đầu vào được ánh xạ qua `String::length` thành một `Integer` đầu ra. Không cần tự tạo vòng lặp rồi `add` từng phần tử vào List mới; pipeline diễn đạt trực tiếp phép biến đổi.

Định nghĩa quan trọng:

> `Stream.map` trả một Stream gồm những kết quả của việc áp dụng hàm ánh xạ lên các phần tử đầu vào. Đây là **intermediate operation** và được thực thi **lazy**.

“Ánh xạ mỗi phần tử” mô tả **ngữ nghĩa dữ liệu**: mỗi phần tử thực sự được truyền qua `map` đóng góp một kết quả, không tự thêm hoặc bỏ phần tử. Nó **không** có nghĩa callback nhất thiết chạy trên mọi phần tử nguồn khi pipeline bị short-circuit hoặc khi implementation tối ưu hợp lệ không cần thực thi stage đó.

Mục tiêu sau bài:

- Hiểu chữ ký generic `map(Function<? super T, ? extends R>)` và cách suy luận kiểu.
- Phân biệt `map` với `filter`, `flatMap`, `peek` và `forEach`.
- Biến đổi String, đối tượng nghiệp vụ, DTO và giá trị số đúng cách.
- Sử dụng `mapToInt`, `mapToLong`, `mapToDouble` để làm việc với primitive streams khi phù hợp.
- Giải quyết các vấn đề `null`, parse lỗi, checked exception, state chia sẻ và parallel stream.
- Hiểu tính lazy, thứ tự kết quả, vòng đời Stream và những lỗi thường gặp khi thiết kế mapper.
- Viết một chương trình Java hoàn chỉnh có kết quả ổn định trên JDK hiện đại.

Các API cốt lõi của bài tồn tại từ **Java 8** và vẫn được hỗ trợ. Những API bổ sung ở các phiên bản sau sẽ được gắn nhãn phiên bản rõ ràng, không trộn vào ví dụ chạy bằng Java 8.

## 2. Chữ ký của `Stream.map`

Trong `java.util.stream.Stream<T>`:

```java
<R> Stream<R> map(
        Function<? super T, ? extends R> mapper)
```

Ý nghĩa:

| Thành phần | Ý nghĩa |
| --- | --- |
| `T` | Kiểu phần tử của Stream hiện tại |
| `R` | Kiểu phần tử kết quả sau ánh xạ |
| `Function<? super T, ? extends R>` | Một hàm có thể nhận phần tử `T` và trả kết quả tương thích `R` |
| `mapper` | Lambda hoặc method reference thực hiện ánh xạ |
| `Stream<R>` | Stream mới có kiểu phần tử `R` |
| `map` | Intermediate operation; không tạo List hay xử lý toàn bộ phần tử ngay |

Ví dụ `Stream<String>` sang `Stream<Integer>`:

```java
Stream<String> source = Stream.of("abc", "de");

Stream<Integer> mapped = source.map(s -> s.length());

// mapped có kiểu Stream<Integer>.
```

Đoạn cần import `java.util.stream.Stream`. Bạn có thể viết ngắn hơn:

```java
Stream<Integer> mapped = Stream.of("abc", "de")
        .map(String::length);
```

Compiler suy luận `R` là `Integer`. `String.length()` trả `int`, và khi cần đặt trong `Stream<Integer>`, primitive `int` được boxing thành `Integer`.

### 2.1. Tại sao có `? super T` ở đầu vào?

`Function<? super T, ? extends R>` cho phép mapper có thể nhận **kiểu cha** của `T`, không nhất thiết đúng một kiểu `T`.

```java
java.util.function.Function<Object, String> describe =
        obj -> "value=" + obj;

List<String> result = Stream.of(1, 2, 3)
        .map(describe)
        .collect(Collectors.toList());

// [value=1, value=2, value=3]
```

Nguồn là `Stream<Integer>`. Vì `Integer` là một `Object`, `Function<Object,String>` có thể xử lý mọi phần tử. Đây là tính linh hoạt của kiểu đối số `? super T`.

### 2.2. Tại sao có `? extends R` ở đầu ra?

Hàm ánh xạ có thể trả kiểu con của kiểu kết quả mà caller muốn sử dụng:

```java
java.util.function.Function<String, Integer> parse =
        Integer::valueOf;

Stream<Number> numbers = Stream.<String>of("1", "2")
        .<Number>map(parse);
```

Mapper trả `Integer`, là subtype của `Number`; vì vậy kết quả có thể được đặt trong `Stream<Number>` với type witness `<Number>` ở lời gọi `map`. `map` không “biến” instance `Integer` thành class `Number` khác; đây là quan hệ subtype và kiểu khai báo.

### 2.3. `map` không thay đổi kiểu của nguồn gốc

`Stream<String>.map(String::length)` tạo Stream mới có kiểu `Integer`; nó **không** thay các phần tử trong `List<String>` ban đầu. Source collection không bị sửa bởi chính `map`, miễn mapper không có tác dụng phụ can thiệp nguồn.

```java
List<String> source = Arrays.asList("Java", "Go");

List<Integer> lengths = source.stream()
        .map(String::length)
        .collect(Collectors.toList());

System.out.println(source);  // [Java, Go]
System.out.println(lengths); // [4, 2]
```

Đây là một sự **biến đổi dữ liệu thông qua pipeline**, không phải `List.replaceAll`. Nếu muốn cập nhật chính List, đó là bài toán mutation và có API/hợp đồng riêng.

## 3. Lambda và method reference cho mapper

`Function<T,R>` là một **functional interface** với SAM `R apply(T t)`. Vì thế, Java chấp nhận lambda:

```java
List<Integer> lengths = Stream.of("Java", "Go")
        .map(word -> word.length())
        .collect(Collectors.toList());
```

Hoặc method reference tương đương:

```java
List<Integer> lengths = Stream.of("Java", "Go")
        .map(String::length)
        .collect(Collectors.toList());
```

Các lựa chọn:

| Mapper | Ý nghĩa | Khi phù hợp |
| --- | --- | --- |
| `s -> s.trim()` | Xóa khoảng trắng đầu/cuối theo `trim` | Biến đổi chuỗi đơn giản |
| `String::trim` | Method reference đến instance method | Hành vi đã có sẵn một method |
| `String::length` | Trả độ dài `String` | Lấy thuộc tính tính toán |
| `Integer::parseInt` | Parse `String` thành `int`, boxing khi dùng `map` | Biết đầu vào là số hợp lệ |
| `Order::getId` | Trích một trường từ object | Projection |
| `OrderDto::new` | Gọi constructor theo SAM phù hợp | Tạo DTO hoặc value object |
| `Function.identity()` | Trả chính phần tử đầu vào | Chỉ khi thật sự cần mapper identity |

Không bắt buộc chuyển mọi lambda sang method reference. Một lambda rõ nghĩa thường dễ đọc hơn khi có điều kiện, nhiều bước, xử lý null hoặc truyền nhiều tham số vào constructor.

### 3.1. Mapper có thể là method reference static

```java
List<Integer> values = Stream.of("10", "20", "30")
        .map(Integer::valueOf)
        .collect(Collectors.toList());

// [10, 20, 30]
```

`Integer.valueOf(String)` có thể tạo `Integer` từ String. Nếu bất kỳ String nào không hợp lệ, mapper sẽ ném `NumberFormatException` lúc phần tử đó được thực sự đánh giá.

### 3.2. Mapper có thể đóng gói trong hàm riêng

```java
static String normalize(String raw) {
    return raw.trim().toUpperCase(java.util.Locale.ROOT);
}

List<String> normalized = Stream.of(" java ", " go ")
        .map(YourClass::normalize)
        .collect(Collectors.toList());
```

Đây là ví dụ cần đặt `normalize` trong class `YourClass`, không phải file độc lập. Tách mapper thành method riêng hữu ích khi có quy tắc nghiệp vụ dài và cần unit test trực tiếp, đồng thời giảm phức tạp của pipeline.

### 3.3. Mapper có thể là constructor reference

Giả sử DTO có constructor nhận một String:

```java
class Label {
    final String text;

    Label(String text) {
        this.text = text;
    }
}
```

Bạn có thể tạo object từ từng chuỗi:

```java
List<Label> labels = Stream.of("A", "B")
        .map(Label::new)
        .collect(Collectors.toList());
```

Kiểu `R` lúc này là `Label`. Mapper tạo **object mới cho mỗi phần tử được xử lý** theo ngữ nghĩa constructor. Nếu object cần hai hay nhiều giá trị đầu vào, lambda thường dễ sử dụng hơn:

```java
.map(order -> new OrderDto(order.getId(), order.getTotal()))
```

Dòng cuối là phần pipeline minh họa, với `Order` và `OrderDto` là domain classes giả định.

## 4. Lazy evaluation: gọi `map` chưa thực thi mapper

`map` là intermediate operation lazy. Nó mô tả **sẽ làm gì khi cần phần tử**, không lập tức duyệt toàn bộ nguồn.

```java
System.out.println("build");

Stream<Integer> lengths = Stream.of("abc", "d")
        .map(s -> {
            System.out.println("mapping " + s);
            return s.length();
        });

System.out.println("before terminal");

List<Integer> result = lengths.collect(Collectors.toList());
System.out.println("result " + result);
```

Trong pipeline **sequential, ordered** minh họa này, stdout là:

```text
build
before terminal
mapping abc
mapping d
result [3, 1]
```

Không có dòng `mapping` nào xuất hiện trước `before terminal`. Lúc `collect` yêu cầu giá trị thực tế, mapper mới hoạt động.

Điểm cần phân biệt:

- **Đánh giá biểu thức tạo lambda/mapper:** xảy ra khi xây pipeline theo các quy tắc Java; nếu lời gọi tạo mapper có side effect thì tác dụng đó có thể xảy ra ngay.
- **Gọi `Function.apply` trên phần tử:** thông thường xảy ra khi terminal operation yêu cầu phần tử kết quả, không phải khi đăng ký stage `map`.

### 4.1. Terminal không luôn gọi mapper cho mọi phần tử

Với `limit` hoặc `findFirst`, chỉ một phần nguồn có thể được xử lý:

```java
List<String> firstTwo = Stream.of("a", "b", "c", "d")
        .map(String::toUpperCase)
        .limit(2)
        .collect(Collectors.toList());

// [A, B]
```

Trong sequential ordered pipeline, chỉ cần phần tử `a` và `b` để tạo kết quả. Các phần tử `c` và `d` không cần được ánh xạ.

### 4.2. `count()` có thể bỏ mapper

Một tối ưu quan trọng được Javadoc cho phép:

```java
long count = Arrays.asList("one", "two", "three")
        .stream()
        .map(s -> {
            System.out.println("mapper " + s);
            return s.toUpperCase();
        })
        .count();

System.out.println(count); // 3
```

`map` **không thay đổi số lượng phần tử**. Với nguồn Collection có kích thước đã biết, `count()` có thể tính được kết quả trực tiếp mà **không gọi mapper**.

Vì vậy, **không được cam kết** các dòng `mapper one`, `mapper two`, `mapper three` sẽ được in. Bỏ những callback không ảnh hưởng kết quả là hành vi hợp lệ, không phải lỗi của Stream API.

Nếu muốn thay đổi dữ liệu để dùng, hãy dùng terminal yêu cầu các giá trị ấy, ví dụ `collect`, `reduce` hay `forEach` phù hợp. Không dùng `map` để gửi email, ghi log bắt buộc hoặc cập nhật counter khi đầu ra bị bỏ qua.

## 5. Một phần tử đi vào, một giá trị đi ra

Với một phần tử được ánh xạ, `map` cho **một kết quả** (có thể `null` nếu mapper trả `null` cho object Stream). Thao tác này **không có nhiệm vụ loại bỏ hoặc mở rộng số phần tử**.

```java
List<String> source = Arrays.asList("a", "bb", "ccc");

List<Integer> mapped = source.stream()
        .map(String::length)
        .collect(Collectors.toList());

// [1, 2, 3] — ba phần tử đầu vào -> ba giá trị kết quả.
```

Không được nhầm “một kết quả” với “một kết quả khác null”. `Stream.map` chấp nhận một reference result là `null` trong các bối cảnh thông thường, và nó vẫn được xem là phần tử của stream.

Nếu cần **bỏ** một số phần tử, kết hợp `filter`. Nếu cần một phần tử đầu vào sinh ra **nhiều** phần tử đầu ra, cân nhắc `flatMap` hoặc một số API Java mới hơn như `mapMulti` (Java 16+).

### 5.1. `map` không giống `filter`

`filter` nhận `Predicate<T>` và giữ hoặc loại phần tử:

```java
List<String> selected = Stream.of("a", "bbb", "cc")
        .filter(s -> s.length() >= 2)
        .collect(Collectors.toList());

// [bbb, cc]
```

`map` nhận `Function<T,R>` để biến đổi:

```java
List<Integer> lengths = Stream.of("a", "bbb", "cc")
        .map(String::length)
        .collect(Collectors.toList());

// [1, 3, 2]
```

Nếu bạn viết một mapper trả `null` để “loại” phần tử, bạn **chưa loại nó**. Phần tử `null` vẫn nằm trong stream trừ khi downstream stage lọc nó hoặc terminal có hợp đồng khác.

### 5.2. `map` khác `flatMap`

`map` giữ kết quả một-nhánh cho từng phần tử. Nếu mapper trả Collection hoặc Stream, bạn nhận phần tử kiểu Collection/Stream, không tự làm phẳng.

```java
List<List<String>> groups = Arrays.asList(
        Arrays.asList("a", "b"),
        Arrays.asList("c")
);

List<Stream<String>> nested = groups.stream()
        .map(List::stream)
        .collect(Collectors.toList());

// nested chứa hai đối tượng Stream, không phải List<String>.
```

Nếu cần mọi chuỗi:

```java
List<String> flat = groups.stream()
        .flatMap(List::stream)
        .collect(Collectors.toList());

// [a, b, c]
```

`flatMap` trả phần tử từ các Stream con theo cơ chế flatten; số phần tử đầu ra có thể bằng 0, 1 hoặc nhiều hơn trên mỗi input. Đây là khác biệt trọng tâm.

### 5.3. `map` không giống `peek`

`peek(Consumer<? super T>)` thường dùng quan sát phần tử, nhưng trả lại **chính giá trị** trên Stream và không thay đổi kiểu phần tử:

```java
Stream<String> a = Stream.of("a").peek(System.out::println);
// a vẫn là Stream<String>.
```

`map(Function<T,R>)` trả một Stream có giá trị là **kết quả mapper**, có thể đổi kiểu:

```java
Stream<Integer> b = Stream.of("a").map(String::length);
// b là Stream<Integer>.
```

Đừng sử dụng `peek` thay cho `map` để sửa object theo side effect. Cách đó khó reason, dễ xung đột khi parallel, và callback có thể bị tối ưu bỏ qua khi không ảnh hưởng terminal result.

### 5.4. `map` khác `forEach`

`forEach(Consumer<T>)` là terminal operation: không trả một Stream để nối tiếp. Nó phục vụ action trên phần tử, không biểu đạt phép biến đổi dữ liệu có giá trị trả về.

```java
Stream.of("a", "b")
        .map(String::toUpperCase)
        .forEach(System.out::println);
```

Ở đây `map` tạo giá trị mới; `forEach` tiêu thụ chúng và in ra. Với parallel streams, thứ tự in không được bảo đảm trừ khi dùng `forEachOrdered` trên ordered stream.

## 6. Chuỗi phép `map`: pipeline có thể biến đổi qua nhiều kiểu

Một pipeline có thể chứa nhiều stage `map`, mỗi stage lấy kết quả của stage trước làm đầu vào:

```java
List<Integer> lengths = Stream.of(" java ", " kotlin ")
        .map(String::trim)
        .map(s -> s.toUpperCase(java.util.Locale.ROOT))
        .map(String::length)
        .collect(Collectors.toList());

// [4, 6]
```

Các bước:

1. `Stream<String>` ban đầu có hai chuỗi chứa khoảng trắng.
2. `map(String::trim)` vẫn trả `Stream<String>`, nhưng nội dung đã được chuẩn hóa.
3. `map(String::toUpperCase)` (thể hiện qua lambda có Locale) tiếp tục trả `Stream<String>`.
4. `map(String::length)` trả `Stream<Integer>`.
5. `collect` lấy dữ liệu thực tế thành `List<Integer>`.

Các stage stateless có thể được **fuse** trong quá trình duyệt; không cần tạo ba List trung gian riêng. Tuy nhiên, khi có những stage stateful/short-circuit, implementation có các ràng buộc và tối ưu riêng.

### 6.1. Biến đổi trước hay sau lọc?

```java
List<String> result = Stream.of(" a ", "  ", " bb ")
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .collect(Collectors.toList());

// [a, bb]
```

Ở đây cần `map(String::trim)` **trước** `filter`, vì nghiệp vụ muốn loại những chuỗi rỗng **sau khi đã trim**.

Một pipeline khác:

```java
List<String> result = Stream.of(" a ", "  ", " bb ")
        .filter(s -> !s.isEmpty())
        .map(String::trim)
        .collect(Collectors.toList());

// [a, "", bb]
```

Vì `"  ".isEmpty()` là false, chuỗi chứa khoảng trắng vượt qua `filter`, rồi mới bị trim thành chuỗi rỗng. **Thứ tự stage có thể thay đổi kết quả**, nên không hoán đổi `filter` và `map` chỉ theo cảm giác tối ưu.

### 6.2. Tối ưu không vượt qua thay đổi nghĩa nghiệp vụ

Đặt `filter` trước `map` có thể giảm lượng ánh xạ nếu filter có thể được áp dụng trên dữ liệu gốc mà vẫn giữ đúng ý nghĩa. Nhưng nếu filter cần kết quả đã chuẩn hóa, đổi thứ tự sẽ sai. Hãy định nghĩa đúng ý nghĩa dữ liệu trước khi tối ưu.

## 7. Trích trường, tạo DTO và giảm dữ liệu không cần thiết

Trong hệ thống ứng dụng, mapper thường chuyển một **domain object** thành một DTO dành cho API hoặc giao diện người dùng.

Giả sử có lớp:

```java
final class Product {
    private final String id;
    private final String name;
    private final long priceCents;

    Product(String id, String name, long priceCents) {
        this.id = id;
        this.name = name;
        this.priceCents = priceCents;
    }

    String getId() { return id; }
    String getName() { return name; }
    long getPriceCents() { return priceCents; }
}
```

Mapper có thể chỉ lấy tên:

```java
List<String> names = products.stream()
        .map(Product::getName)
        .collect(Collectors.toList());
```

Đây là một đoạn pipeline minh họa, với biến `products` có kiểu `List<Product>` phù hợp. Kết quả là danh sách tên thay vì danh sách toàn bộ object.

Hoặc tạo DTO:

```java
List<ProductDto> output = products.stream()
        .map(p -> new ProductDto(
                p.getId(), p.getName(), p.getPriceCents()))
        .collect(Collectors.toList());
```

`ProductDto` là lớp DTO của ứng dụng, không phải kiểu có sẵn trong JDK. Hãy xác định rõ field và constructor trong code thực tế; chương trình độc lập ở mục 18 sẽ cung cấp một DTO hoàn chỉnh.

### 7.1. DTO là phép projection, không tự động là deep copy

Mapper tạo DTO có thể sao chép các **giá trị hoặc tham chiếu** từ entity nguồn. Nếu DTO chứa tham chiếu tới một List mutable của entity, việc tạo DTO không tự làm List đó bất biến. Cần defensive copy khi contract yêu cầu tách biệt trạng thái.

### 7.2. Không đưa thông tin nhạy cảm vào mapper một cách vô tình

Khi tạo payload API, xác định whitelist field được phép xuất hiện. Thay vì ánh xạ mọi field nội bộ sang JSON rồi cố ẩn ở bước sau, hãy có DTO rõ ràng chứa chính xác dữ liệu cần xuất. `map` chỉ là công cụ biến đổi; kiểm soát dữ liệu vẫn là trách nhiệm của thiết kế ứng dụng.

### 7.3. Cần transform có kiểm soát lỗi

Nếu mapper có thể thất bại do dữ liệu nghiệp vụ, bạn có thể:

- Trả một kiểu kết quả có trạng thái thành công/thất bại.
- Parse/validate trước rồi chỉ ánh xạ dữ liệu hợp lệ.
- Ném exception có ngữ cảnh và xử lý ở tầng gọi.
- Đưa bản ghi lỗi vào một luồng xử lý riêng.

Đừng tùy tiện bắt mọi exception rồi trả một giá trị giả, vì điều đó có thể làm hỏng báo cáo mà không ai biết bản ghi nào bị bỏ.

## 8. Primitive streams: `map`, `mapToInt`, `mapToLong`, `mapToDouble`

`Stream<T>.map` trả **object Stream**. Nếu hàm trả `int`, kết quả nằm trong `Stream<Integer>` và có thể chịu boxing/unboxing. Với pipeline số học, Java cung cấp các primitive specializations.

### 8.1. `mapToInt`

```java
int totalLength = Stream.of("Java", "Go", "Kotlin")
        .mapToInt(String::length)
        .sum();

// 4 + 2 + 6 = 12
```

`mapToInt(ToIntFunction<? super T>)` trả `IntStream`. Bạn có thể gọi `sum`, `average`, `min`, `max`, `summaryStatistics` và nhiều phép toán số học khác mà không phải tự tạo `List<Integer>`.

So sánh:

```java
List<Integer> lengths = Stream.of("Java", "Go")
        .map(String::length)
        .collect(Collectors.toList());

// [4, 2], object Stream<Integer>.
```

Với bài toán chỉ lấy tổng/đếm/average, primitive stream thường diễn đạt ý định rõ và có thể giảm boxing.

### 8.2. `mapToLong`

```java
long totalCents = orders.stream()
        .mapToLong(Order::getPriceCents)
        .sum();
```

Đoạn minh họa cần biến `orders` và method `Order.getPriceCents()` trả `long`. Dùng `long` giúp tránh một số rủi ro overflow trung gian của `int`, nhưng **long vẫn có thể overflow** với dữ liệu đủ lớn. Với tiền tệ, chọn đơn vị, kiểu số và chính sách overflow/rounding theo nghiệp vụ; Java Stream không tự đảm bảo an toàn tài chính.

### 8.3. `mapToDouble`

```java
double average = Stream.of("1.5", "2.5", "3.5")
        .mapToDouble(Double::parseDouble)
        .average()
        .orElse(Double.NaN);

// average = 2.5
```

`average()` trên `DoubleStream` trả `OptionalDouble` vì nguồn có thể rỗng. Ví dụ dùng `orElse(Double.NaN)` như một chính sách minh họa, **không phải lựa chọn mặc định phù hợp cho mọi nghiệp vụ**.

Nếu dữ liệu là tiền hoặc số thập phân đòi hỏi độ chính xác tuyệt đối theo scale, `BigDecimal` và phép tổng hợp phù hợp thường an toàn hơn `double`.

### 8.4. Bảng phân biệt

| Operation | Hàm mapper | Kết quả | Tình huống |
| --- | --- | --- | --- |
| `map` | `Function<? super T,? extends R>` | `Stream<R>` | Đổi sang object/DTO/String/Integer |
| `mapToInt` | `ToIntFunction<? super T>` | `IntStream` | Tính tổng/average trên `int` |
| `mapToLong` | `ToLongFunction<? super T>` | `LongStream` | Đếm/sum số lớn từ object |
| `mapToDouble` | `ToDoubleFunction<? super T>` | `DoubleStream` | Tính toán số thực |
| `IntStream.map` | `IntUnaryOperator` | `IntStream` | Biến đổi mỗi số `int` thành một `int` |
| `IntStream.mapToObj` | `IntFunction<? extends U>` | `Stream<U>` | Từ primitive `int` sang object |
| `IntStream.boxed` | Không nhận mapper | `Stream<Integer>` | Boxing `int` thành `Integer` |

Những overload tương tự có trong `LongStream` và `DoubleStream`. Không cần boxing dữ liệu thành wrapper object để rồi unboxing ngay khi sum nếu có sẵn primitive pipeline.

### 8.5. Từ primitive quay về object

```java
List<String> labels = java.util.stream.IntStream.rangeClosed(1, 3)
        .mapToObj(n -> "item-" + n)
        .collect(Collectors.toList());

// [item-1, item-2, item-3]
```

`mapToObj` là hướng từ primitive stream sang object stream. Không nhầm với `Stream<T>.map`, vốn bắt đầu từ object stream.

## 9. `null`: mapper có thể trả null, nhưng downstream phải biết xử lý

Trong một object `Stream<T>`, `null` có thể là một **phần tử**. `map` không tự bỏ phần tử null.

```java
List<String> result = Stream.of("A", null, "B")
        .map(s -> s == null ? "(missing)" : s.toLowerCase())
        .collect(Collectors.toList());

// [a, (missing), b]
```

Ở đây mapper chủ động xử lý `null`. Ngược lại:

```java
// Có thể ném NullPointerException lúc phần tử null được đánh giá:
// Stream.of("A", null, "B")
//       .map(String::toLowerCase)
//       .collect(Collectors.toList());
```

`String::toLowerCase` không gọi được trên receiver `null`.

### 9.1. Có thể giữ null trong output

```java
List<String> result = Stream.of("A", "B")
        .map(s -> "B".equals(s) ? null : s)
        .collect(Collectors.toList());

// Theo collector toList() Java 8, result có phần tử null.
```

`Collectors.toList()` không bảo đảm một loại List cụ thể hoặc tính mutable, nhưng danh sách được tạo trong ví dụ hỗ trợ phần tử null theo hợp đồng collector thông thường. Dù vậy, các terminal khác có thể có ràng buộc riêng về null.

### 9.2. `findFirst` và `findAny` không trả Optional chứa null

`Optional.ofNullable(null)` cho `Optional.empty()`, nhưng điều đó **không** có nghĩa `Stream.findFirst()` tự biến một phần tử null thành Optional rỗng.

```java
// Khi phần tử đầu thực sự là null, findFirst ném NPE:
// Stream.of("A")
//       .map(s -> (String) null)
//       .findFirst();
```

Javadoc quy định `findFirst` có thể ném `NullPointerException` nếu phần tử được chọn là `null`. Khi pipeline có thể tạo null, hãy xác định rõ chính sách lọc hoặc thay thế trước khi gọi những terminal không chấp nhận null.

### 9.3. Lọc null trước hoặc sau mapper?

Nếu mapper không chấp nhận null đầu vào:

```java
List<Integer> lengths = Stream.of("A", null, "BC")
        .filter(java.util.Objects::nonNull)
        .map(String::length)
        .collect(Collectors.toList());

// [1, 2]
```

Nếu mapper hợp lệ nhưng có thể **trả null**, lọc sau:

```java
List<String> kept = Stream.of("A", "B", "C")
        .map(s -> "B".equals(s) ? null : s)
        .filter(java.util.Objects::nonNull)
        .collect(Collectors.toList());

// [A, C]
```

Vị trí filter quyết định cái gì bị loại và tránh lỗi ở đâu. Hãy chọn đúng theo hợp đồng đầu vào và đầu ra, không áp dụng máy móc “luôn filter null trước map”.

### 9.4. `mapToInt` và null

`ToIntFunction<T>` trả primitive `int`, nên không có kết quả null. Nhưng đầu vào object vẫn có thể null; mapper như `Integer::intValue` sẽ ném NPE nếu nhận null. Nếu muốn biểu diễn thiếu số, hãy xử lý `OptionalInt` hoặc một kiểu dữ liệu thay thế rõ ràng; không thể dùng null làm một phần tử `IntStream`.

## 10. Parse chuỗi và xử lý dữ liệu không hợp lệ

Ví dụ đơn giản:

```java
List<Integer> numbers = Stream.of("1", "2", "3")
        .map(Integer::valueOf)
        .collect(Collectors.toList());

// [1, 2, 3]
```

Nếu dữ liệu là `"oops"`, `Integer.valueOf("oops")` ném `NumberFormatException`. Vì `map` lazy, lỗi xảy ra **khi phần tử đó được đánh giá**, thường trong terminal operation, không nhất thiết khi đăng ký mapper.

### 10.1. Không coi lỗi parse như một giá trị 0 nếu 0 có ý nghĩa

Cách xử lý ngắn nhưng nguy hiểm:

```java
// KHÔNG NÊN nếu số 0 là dữ liệu hợp lệ:
// map(s -> {
//     try { return Integer.parseInt(s); }
//     catch (NumberFormatException e) { return 0; }
// })
```

Cách đó trộn lỗi parse với số 0 thật. Nếu 0 có nghĩa nghiệp vụ, kết quả sẽ bị sai mà không có thông tin bản ghi lỗi.

### 10.2. Biểu diễn “parse thành công hoặc không” bằng Optional

Bạn có thể viết helper:

```java
static java.util.Optional<Integer> tryParse(String raw) {
    if (raw == null) {
        return java.util.Optional.empty();
    }
    try {
        return java.util.Optional.of(
                Integer.valueOf(raw.trim()));
    } catch (NumberFormatException ex) {
        return java.util.Optional.empty();
    }
}
```

Nếu cần bỏ các input không hợp lệ một cách có chủ đích:

```java
List<Integer> parsed = Stream.of(" 7 ", "bad", "12")
        .map(YourClass::tryParse)
        .filter(java.util.Optional::isPresent)
        .map(java.util.Optional::get)
        .collect(Collectors.toList());

// [7, 12]
```

Đây là đoạn minh họa cần helper `tryParse` ở class `YourClass`. `Optional::get` ở đây an toàn do đã lọc `isPresent` ngay trước đó, nhưng nếu tách pipeline hoặc refactor, cần bảo toàn điều kiện này.

Trong Java 9+ có `Optional.stream()`, cho phép viết gọn:

```java
// Java 9+ (không dùng trong file minh họa Java 8):
List<Integer> parsed = Stream.of("7", "bad", "12")
        .map(YourClass::tryParse)
        .flatMap(java.util.Optional::stream)
        .collect(Collectors.toList());
```

Với hệ thống cần ghi nhận lỗi cụ thể, trả một kiểu kết quả có cả input ban đầu và thông tin lỗi sẽ tốt hơn là bỏ dữ liệu không hợp lệ im lặng.

### 10.3. Parse trong `mapToInt`

```java
int total = Stream.of("10", "20", "30")
        .mapToInt(Integer::parseInt)
        .sum(); // 60
```

Cách này phù hợp khi dữ liệu đã được xác thực. Nếu có giá trị sai, `NumberFormatException` sẽ phát sinh trong khi duyệt pipeline. Đừng dùng `mapToInt` như cơ chế tự validate số; nó không tự bắt lỗi.

## 11. Checked exception trong mapper

`Function<T,R>.apply` không khai báo checked exception. Vì vậy lambda truyền vào `Stream.map` **không thể tự ý để một checked exception thoát ra** nếu interface đích không khai báo nó.

Ví dụ không biên dịch:

```java
// KHÔNG BIÊN DỊCH vì Files.readString có checked IOException:
// List<String> texts = paths.stream()
//         .map(path -> java.nio.file.Files.readString(path))
//         .collect(Collectors.toList());
```

`Files.readString` là API từ Java 11; ví dụ trên chỉ để minh họa checked exception trong mapper, không dùng trong chương trình Java 8 độc lập. Trên Java 8, tương tự với `Files.readAllBytes(path)` (cũng khai báo `IOException`).

### 11.1. Xử lý ngoại lệ trong mapper khi hợp đồng cho phép

Một ví dụ Java 8-compatible đọc text từ file:

```java
static String loadUtf8(java.nio.file.Path path) {
    try {
        byte[] bytes = java.nio.file.Files.readAllBytes(path);
        return new String(bytes,
                java.nio.charset.StandardCharsets.UTF_8);
    } catch (java.io.IOException ex) {
        throw new java.io.UncheckedIOException(
                "Cannot read " + path, ex);
    }
}
```

Sau đó:

```java
List<String> texts = paths.stream()
        .map(YourClass::loadUtf8)
        .collect(Collectors.toList());
```

Đây là đoạn minh họa trong class có method `loadUtf8` và biến `paths` thích hợp. `UncheckedIOException` ghi lại nguyên nhân gốc nhưng đưa lỗi vào unchecked exception; đó là **lựa chọn hợp đồng API** phải được caller hiểu và xử lý, không phải cách “bỏ qua lỗi”.

### 11.2. Chọn đúng API khi dữ liệu gắn với I/O

Nếu xử lý nhiều file lớn, ánh xạ bằng `Files.readAllBytes` có thể tạo áp lực bộ nhớ. Đôi khi tốt hơn là dùng streaming I/O có tài nguyên được quản lý đúng scope hoặc đọc từng file theo một đơn vị công việc rõ. Đừng để `map` che khuất việc mở/đóng tài nguyên.

## 12. Non-interference và stateless: mapper tốt cần những gì?

Oracle Stream package documentation yêu cầu callback truyền vào Stream phải **non-interfering** (không sửa nguồn) và trong đa số trường hợp **stateless** (không phụ thuộc state mutable đang đổi trong quá trình thực thi).

### 12.1. Mapper thuần, dễ kiểm thử

```java
List<String> result = Stream.of(" java ", " go ")
        .map(String::trim)
        .map(s -> s.toUpperCase(java.util.Locale.ROOT))
        .collect(Collectors.toList());

// [JAVA, GO]
```

Đầu ra chỉ phụ thuộc input. Không có shared state.

### 12.2. Mapper gây side effect: anti-pattern

```java
List<String> original = new java.util.ArrayList<>(
        Arrays.asList("a", "b", "c"));

// KHÔNG NÊN:
// original.stream()
//         .map(s -> {
//             original.remove(s); // can thiệp Collection đang duyệt
//             return s.toUpperCase();
//         })
//         .collect(Collectors.toList());
```

Sửa source trong callback có thể gây `ConcurrentModificationException` hoặc kết quả sai/không được bảo đảm, kể cả sequential. Với parallel, nguy cơ race và interference còn phức tạp hơn.

### 12.3. Counter dùng chung không an toàn

```java
int[] counter = {0};

// KHÔNG NÊN:
// source.parallelStream().map(s -> {
//     counter[0]++;
//     return s.toUpperCase();
// }).collect(Collectors.toList());
```

`counter[0]++` không atomic khi nhiều worker truy cập. Hơn nữa, nếu terminal không cần kết quả mapper, callback có thể bị bỏ theo tối ưuization hợp lệ. Đừng ghi số lượt xử lý thực tế bằng side effect đặt trong `map`.

Nếu muốn **đếm**, dùng `count()`. Nếu muốn **tổng hợp**, dùng `reduce`, `collect` hoặc primitive `sum` thích hợp.

### 12.4. Stateless không đồng nghĩa “không bao giờ gọi thư viện”

Mapper có thể gọi helper/library để tính một kết quả, miễn hợp đồng tương thích. Nhưng mapper thực hiện network I/O, cập nhật database, sinh identifier bằng shared mutable state hoặc đọc thời gian hệ thống có thể làm output không xác định. Cần cân nhắc đúng tính tái lập, lỗi, retry, cancellation và mức concurrency.

## 13. Map trên sequential và parallel Streams

`map` dùng được với cả hai chế độ:

```java
List<String> source = Arrays.asList("a", "b", "c");

List<String> sequential = source.stream()
        .map(String::toUpperCase)
        .collect(Collectors.toList());

List<String> parallel = source.parallelStream()
        .map(String::toUpperCase)
        .collect(Collectors.toList());

// sequential và parallel đều [A, B, C].
```

Trên ordered `List`, phép `map` giữ encounter order của phần tử ở kết quả logic, và `Collectors.toList()` tôn trọng thứ tự của ordered stream.

Nhưng **thứ tự mapper thực thi không nhất thiết giống encounter order** khi parallel. Đừng phụ thuộc vào việc `map` của phần tử đầu phải chạy xong trước phần tử thứ hai.

### 13.1. Nếu cần thứ tự side effect

```java
source.parallelStream()
        .map(String::toUpperCase)
        .forEachOrdered(System.out::println);
```

`forEachOrdered` giữ encounter order cho **hành động terminal** trên ordered stream; nó không hứa tất cả phép `map` trước đó chạy trên một thread hoặc theo đúng thứ tự.

### 13.2. Parallel map không tự nhanh hơn

`parallelStream()` chỉ chọn parallel execution mode. Chi phí chia task, phối hợp, tạo object, memory bandwidth và stateful stages có thể lớn hơn lợi ích nếu mapper rẻ hoặc nguồn nhỏ.

Cân nhắc parallel khi phép tính đủ nặng, mapper độc lập, nguồn chia được, terminal hỗ trợ ghép kết quả tốt và benchmark thực tế chứng minh có lợi. Không dùng `parallelStream` để che việc mapper làm blocking I/O hoặc chia sẻ mutable state không an toàn.

### 13.3. Xử lý exception trong parallel map

Nếu nhiều mapper có thể ném exception ở các phần tử khác nhau, thứ tự exception lộ ra có thể không tương ứng với thứ tự phần tử nguồn. Đừng xây logic phụ thuộc “lỗi đầu tiên” theo thứ tự của callback parallel. Nếu cần thu thập tất cả lỗi theo thứ tự dữ liệu, biểu diễn kết quả thành một kiểu thành công/thất bại rồi collect theo encounter order.

## 14. Encounter order, `sorted` và `distinct` sau ánh xạ

`map` không tự sắp xếp phần tử và không tự loại trùng.

```java
List<Integer> sizes = Stream.of("a", "bb", "c", "ddd")
        .map(String::length)
        .collect(Collectors.toList());

// [1, 2, 1, 3]
```

Nếu cần unique lengths:

```java
List<Integer> unique = Stream.of("a", "bb", "c", "ddd")
        .map(String::length)
        .distinct()
        .collect(Collectors.toList());

// [1, 2, 3]
```

Vì stream đầu vào ordered, `distinct` giữ phần tử đầu trong mỗi nhóm trùng theo equality.

Nếu cần sắp xếp kết quả:

```java
List<Integer> sorted = Stream.of("a", "bb", "c", "ddd")
        .map(String::length)
        .sorted()
        .collect(Collectors.toList());

// [1, 1, 2, 3]
```

`sorted` và `distinct` là các intermediate operations **stateful** trong nhiều tình huống, nên có thể cần buffer/tracking. `map` là một stateless intermediate operation theo hợp đồng. Tùy chọn stage ảnh hưởng hiệu năng, đặc biệt ở parallel pipeline.

### 14.1. Chọn chỗ `distinct` theo ý nghĩa nghiệp vụ

`distinct().map(...)` loại trùng **trước khi biến đổi**; `map(...).distinct()` loại trùng **theo kết quả biến đổi**.

```java
List<Integer> a = Stream.of("ab", "cd", "ab")
        .distinct()
        .map(String::length)
        .collect(Collectors.toList());
// a = [2, 2], vì ab và cd khác nhau.

List<Integer> b = Stream.of("ab", "cd", "ab")
        .map(String::length)
        .distinct()
        .collect(Collectors.toList());
// b = [2], vì cả ba độ dài đều bằng nhau.
```

Không tùy ý đẩy `distinct` lên trước mapper chỉ vì muốn “lọc sớm hơn”.

### 14.2. Map có thể thay đổi đặc tính sorted/distinct của stream

Một mapper không nhất thiết giữ thứ tự sắp xếp theo comparator hoặc tính distinct của giá trị. Ví dụ từ các phần tử phân biệt nhau, map chúng thành cùng số 0 thì output không còn distinct. Stream implementation quản lý các đặc tính nội bộ theo hợp đồng; người dùng không nên suy luận `map` bảo toàn `SORTED` hoặc `DISTINCT` chỉ vì source có các đặc tính ấy.

## 15. Mapping sang kiểu immutable và Java hiện đại

Bắt đầu từ Java 16, **record** là một cách khai báo dữ liệu bất biến mức cấu trúc tương đối gọn, thích hợp cho một số DTO/value objects. Ví dụ Java 17+:

```java
record UserSummary(String id, String displayName) {}

List<UserSummary> summaries = users.stream()
        .map(user -> new UserSummary(
                user.getId(), user.getName()))
        .collect(Collectors.toList());
```

Đây là đoạn minh họa với biến `users` và các getter cần được định nghĩa. Record ở đây không thay đổi quy tắc `map`: vẫn nhận một input và tạo một output value.

**Phiên bản:** `record` là tính năng ổn định từ Java 16; **không biên dịch trên Java 8**. Với codebase Java 8, dùng một class bất biến có constructor và getter rõ ràng. Chương trình độc lập bên dưới dùng class để tương thích Java 8.

### 15.1. `Stream.toList()` không phải API Java 8

`Stream.toList()` có từ Java 16 và trả List không thể sửa theo hợp đồng. Đừng sao chép ví dụ:

```java
// Java 16+:
List<Integer> sizes = Stream.of("A", "BB")
        .map(String::length)
        .toList();
```

vào dự án compile với `--release 8`. Với Java 8, dùng:

```java
List<Integer> sizes = Stream.of("A", "BB")
        .map(String::length)
        .collect(Collectors.toList());
```

`Collectors.toList()` không hứa một implementation `List` cụ thể hoặc khả năng chỉnh sửa trong API contract. Nếu cần một `ArrayList` cụ thể, chọn `Collectors.toCollection(ArrayList::new)`.

### 15.2. `mapMulti` là một API khác

`Stream.mapMulti` có từ Java 16, cho phép một mapper phát **0 hoặc nhiều** phần tử qua consumer được cung cấp, thay vì tạo Stream con như `flatMap`. Nó không phải tên mới của `map` và không nên dùng lẫn trên dự án chỉ hỗ trợ Java 8.

Nếu bài toán của bạn thực sự là một-đến-một, `map` vẫn là lựa chọn trực tiếp, dễ đọc nhất.

## 16. `map` của Stream khác `Map` của java.util

Hai khái niệm trùng chữ nhưng khác vai trò:

- `Stream.map(...)`: một **intermediate operation** ánh xạ các phần tử trong Stream.
- `java.util.Map<K,V>`: một **data structure** lưu trữ ánh xạ key → value.

Ví dụ Map cấu trúc dữ liệu:

```java
java.util.Map<String, Integer> scores =
        new java.util.HashMap<>();

scores.put("A", 10);
scores.put("B", 20);
```

Nếu cần Stream từ Map, chọn view:

```java
List<String> labels = scores.entrySet().stream()
        .map(e -> e.getKey() + ":" + e.getValue())
        .sorted()
        .collect(Collectors.toList());

// [A:10, B:20]
```

`Map` không trực tiếp kế thừa `Collection`, vì thế `scores.stream()` không tồn tại trong Java Map API. Phải dùng `entrySet().stream()`, `keySet().stream()` hoặc `values().stream()` tùy dữ liệu cần ánh xạ.

## 17. Tối ưu và bảo trì: khi nào `map` là lựa chọn tốt?

`map` phù hợp khi bạn có một quy tắc **mỗi đầu vào → một đầu ra** có thể diễn đạt rõ ràng bằng hàm thuần.

Các trường hợp điển hình:

1. **Projection:** `orders.stream().map(Order::getId)`.
2. **Định dạng:** `names.stream().map(String::trim)`.
3. **Đổi đơn vị:** `measurements.stream().map(v -> convert(v))`.
4. **Tạo DTO:** `entities.stream().map(EntityDto::from)`.
5. **Parse dữ liệu đã xác thực:** `texts.stream().map(Integer::valueOf)`.
6. **Tạo biểu diễn chỉ đọc:** `users.stream().map(UserSummary::new)`, khi constructor phù hợp.
7. **Trích số cho aggregate:** `orders.stream().mapToLong(Order::getTotalCents).sum()`.

### 17.1. Khi nào không nên dùng `map`?

- Cần **loại phần tử**: dùng `filter`.
- Cần **0..N kết quả trên một đầu vào**: dùng `flatMap` hoặc API thích hợp.
- Cần một **side effect** nhưng bỏ qua giá trị trả về: cân nhắc terminal phù hợp hoặc quy trình rõ ràng, không ép `map` làm action.
- Cần **join hai danh sách theo key**: map đơn thuần không giải bài toán join.
- Cần **cập nhật nguồn tại chỗ**: `map` không phải mutation API của Collection.
- Cần **kết quả duy nhất theo key**: phải có chính sách identity/merge, không tự nghĩ `map` làm mất trùng.
- Cần xử lý lỗi nhiều bước và trạng thái phức tạp: đôi khi vòng lặp tường minh hoặc helper trả kiểu kết quả rõ ràng dễ hiểu hơn.

### 17.2. Ưu tiên code dễ đọc hơn một chuỗi lambda dài

Nếu biến đổi cần nhiều phép kiểm tra và tạo DTO, có thể viết:

```java
List<InvoiceDto> dtos = invoices.stream()
        .map(InvoiceMapper::toDto)
        .collect(Collectors.toList());
```

`InvoiceMapper::toDto` là một method ứng dụng phải được định nghĩa. Đây là một cách giữ pipeline ngắn, đưa validation và mapping chi tiết vào method dễ unit test.

Không nên tạo một lambda vài chục dòng với nhiều nhánh và side effect chỉ để tránh khai báo một method/helper riêng.

### 17.3. Chú ý chi phí boxing, phân bổ object và bộ nhớ

- `map(String::length)` tạo object Stream với `Integer` khi cần.
- `mapToInt(String::length)` giữ primitive `int` để tính toán.
- `map(user -> new UserDto(...))` có thể phân bổ object cho từng phần tử mà terminal thực sự cần.
- `collect(toList())` materialize toàn bộ kết quả được duyệt vào List.
- `limit`/`findFirst` có thể giảm số object phải tạo khi chỉ cần prefix/đầu tiên.
- `count()` có thể bỏ mapper khi chỉ cần cardinality và kích thước đã biết.

Dùng primitive streams và các terminal phù hợp khi chúng làm ý định rõ ràng hơn; không tối ưu bằng phỏng đoán. Khi hiệu năng quan trọng, benchmark trên dữ liệu và môi trường thực tế.

## 18. Chương trình Java hoàn chỉnh: String, DTO, số, null và parse lỗi

Chương trình sau dùng **chỉ API Java 8** nhưng biên dịch/chạy trên JDK 17+. Nó trình bày `map` từ nhiều góc độ:

1. Lấy nhãn đơn hàng.
2. Ánh xạ domain object sang DTO.
3. Tính tổng với `mapToLong`.
4. Lọc rồi tính tổng với `mapToInt`.
5. Dùng method reference để chuyển String thành độ dài.
6. Chạy nhiều phép `map` để chuẩn hóa.
7. Lọc kết quả sau khi trim.
8. Xử lý null thành giá trị hiển thị rõ ràng.
9. Parse an toàn bằng `Optional`.
10. So sánh kết quả `parallelStream().map` trên List ordered.
11. Dùng `findFirst` trên Stream đã được map.

Tạo file **`MapValuesDemo.java`**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class MapValuesDemo {

    static final class Order {
        final String id;
        final int cents;
        final String status;

        Order(String id, int cents, String status) {
            this.id = id;
            this.cents = cents;
            this.status = status;
        }
    }

    static final class OrderSummary {
        final String id;
        final int cents;

        OrderSummary(String id, int cents) {
            this.id = id;
            this.cents = cents;
        }

        @Override
        public String toString() {
            return id + ":" + cents;
        }
    }

    static Optional<Integer> tryParseInteger(String text) {
        if (text == null) {
            return Optional.empty();
        }
        try {
            return Optional.of(
                    Integer.valueOf(text.trim()));
        } catch (NumberFormatException ex) {
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("A", 1200, "new"),
                new Order("B", 2500, "paid"),
                new Order("C", 900, "paid"));

        List<String> labels = orders.stream()
                .map(o -> o.id + "=" + o.cents)
                .collect(Collectors.toList());
        System.out.println("Labels: " + labels);

        List<OrderSummary> summaries = orders.stream()
                .map(o -> new OrderSummary(o.id, o.cents))
                .collect(Collectors.toList());
        System.out.println("Summaries: " + summaries);

        long total = orders.stream()
                .mapToLong(o -> o.cents)
                .sum();
        System.out.println("Total cents: " + total);

        int paid = orders.stream()
                .filter(o -> "paid".equals(o.status))
                .mapToInt(o -> o.cents)
                .sum();
        System.out.println("Paid cents: " + paid);

        List<Integer> lengths = Stream.of(
                "Java", "Go", "Kotlin")
                .map(String::length)
                .collect(Collectors.toList());
        System.out.println("Lengths: " + lengths);

        List<String> normalized = Stream.of(
                "  java  ", " go ", "KOTLIN")
                .map(String::trim)
                .map(s -> s.toUpperCase(Locale.ROOT))
                .collect(Collectors.toList());
        System.out.println("Normalized: " + normalized);

        List<String> nonblank = Stream.of(
                " x ", "  ", " y ")
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .collect(Collectors.toList());
        System.out.println("Nonblank: " + nonblank);

        List<String> nullSafe = Stream.of("A", null, "B")
                .map(s -> s == null
                        ? "(missing)"
                        : s.toLowerCase(Locale.ROOT))
                .collect(Collectors.toList());
        System.out.println("Null-safe: " + nullSafe);

        List<Integer> parsed = Stream.of(
                " 7 ", "bad", "12")
                .map(MapValuesDemo::tryParseInteger)
                .filter(Optional::isPresent)
                .map(Optional::get)
                .collect(Collectors.toList());
        System.out.println("Parsed: " + parsed);

        List<String> parallelIds = orders.parallelStream()
                .map(o -> o.id)
                .collect(Collectors.toList());
        System.out.println("Parallel IDs: " + parallelIds);

        Optional<Integer> firstLength = Stream.of(
                "JS", "Java")
                .map(String::length)
                .findFirst();
        System.out.println("First length: "
                + firstLength.orElse(-1));
    }
}
```

Biên dịch và chạy:

```bash
javac MapValuesDemo.java
java MapValuesDemo
```

**Stdout dự kiến chính xác:**

```text
Labels: [A=1200, B=2500, C=900]
Summaries: [A:1200, B:2500, C:900]
Total cents: 4600
Paid cents: 3400
Lengths: [4, 2, 6]
Normalized: [JAVA, GO, KOTLIN]
Nonblank: [x, y]
Null-safe: [a, (missing), b]
Parsed: [7, 12]
Parallel IDs: [A, B, C]
First length: 2
```

### 18.1. Đọc kết quả

**Labels:** `map(o -> o.id + "=" + o.cents)` nhận `Order` và tạo `String` theo mẫu `id=cents`. Đây là phép projection/formatting; không sửa đơn hàng.

**Summaries:** mapper tạo một `OrderSummary` mới từ id và số tiền tính bằng cents. `toString()` của DTO được định nghĩa rõ, nên cách in List ổn định, không phụ thuộc địa chỉ object.

**Total cents:** `mapToLong` chuyển số `int` của đơn hàng thành giá trị `long` và `sum` tính `1200 + 2500 + 900 = 4600`.

**Paid cents:** `filter` giữ hai đơn hàng có status `paid`, rồi `mapToInt` lấy cents và `sum` tính `2500 + 900 = 3400`.

**Lengths:** `String::length` biến ba từ thành ba số 4, 2, 6; đây là một-đến-một.

**Normalized:** hai `map` nối nhau xóa khoảng trắng và chuẩn hóa chữ hoa theo `Locale.ROOT`. `trim` là quy tắc ví dụ; nếu hệ thống cần xử lý Unicode whitespace đầy đủ, phải xem đặc tả đầu vào và cân nhắc API như `String.strip()` từ Java 11.

**Nonblank:** `map(String::trim)` diễn ra trước `filter`, nên chuỗi toàn khoảng trắng trở thành chuỗi rỗng rồi bị loại.

**Null-safe:** mapper dùng biểu thức điều kiện để không gọi method trên null và thay nó bằng nhãn `(missing)`.

**Parsed:** helper `tryParseInteger` trả `Optional.empty()` cho input không hợp lệ. Pipeline lọc các Optional rỗng và lấy giá trị từ các Optional còn lại; kết quả `[7,12]`. Đây là chính sách “loại giá trị không parse được” đã được chọn rõ, không phải behavior tự động của `map`.

**Parallel IDs:** `parallelStream` có thể thực thi mapper trên nhiều thread, nhưng `orders` là ordered List và collector giữ encounter order; đầu ra logic vẫn là `[A,B,C]`. Chương trình không in thứ tự callback hoặc thread name.

**First length:** `findFirst` nhận phần tử đầu tiên của ordered Stream đã ánh xạ, cho `Optional<Integer>` chứa 2. Đoạn không tạo exception hoặc side effect để đoán số lần gọi mapper.

## 19. Lỗi phổ biến và cách sửa

### Lỗi 1. Gọi `map` rồi nghĩ đã có List kết quả

`stream.map(f)` trả **một Stream mới**, không trả `List`. Nếu muốn List trong Java 8, dùng `collect(Collectors.toList())`.

### Lỗi 2. Quên terminal operation

Chỉ viết `source.stream().map(f);` không yêu cầu kết quả được thực thi. Stream có thể bị bỏ mà không có phần tử nào được ánh xạ. Hãy quyết định terminal phù hợp với bài toán.

### Lỗi 3. Dùng `map` để loại phần tử

`map(s -> valid(s) ? s : null)` chỉ tạo phần tử null; nó không loại phần tử. Dùng `filter` trước/sau map hoặc `flatMap` khi cần 0..N kết quả.

### Lỗi 4. Dùng `map` để tạo nhiều giá trị rồi mong tự flatten

`map(List::stream)` tạo `Stream<Stream<T>>`. Dùng `flatMap(List::stream)` nếu cần một `Stream<T>` phẳng.

### Lỗi 5. Cho rằng `map` sửa List nguồn

Stream API là mô hình tính toán, không phải API cập nhật tại chỗ. Muốn đổi List nguồn, dùng một cách cập nhật có hợp đồng rõ ràng, không sửa source trong callback của stream đang duyệt.

### Lỗi 6. Không quan tâm null

`map(String::trim)` trên phần tử null ném NPE khi phần tử được xử lý. Xử lý null theo chính sách dữ liệu hoặc dùng `filter(Objects::nonNull)` thích hợp.

### Lỗi 7. Dùng `Optional.map` với ý nghĩa giống `Stream.map`

`Optional.map` ánh xạ một giá trị tùy chọn và tạo `Optional`; nếu mapper trả null, kết quả thường là Optional rỗng. `Stream.map` ánh xạ các phần tử Stream và có thể giữ null như một phần tử. Hai API cùng tên nhưng khác hợp đồng.

### Lỗi 8. Dùng `map` với phương thức checked exception chưa được xử lý

`Function.apply` không khai báo checked exception. Cần xử lý trong mapper, bọc lỗi phù hợp hoặc thiết kế API khác; cast sang `Function` không làm lỗi biến mất.

### Lỗi 9. Dùng `map` với tác dụng phụ rồi chỉ gọi `count`

JDK được phép tối ưu để không gọi mapper khi số phần tử được xác định từ metadata. Logic nghiệp vụ không được dựa vào tác dụng phụ của mapper.

### Lỗi 10. Đưa shared mutable state vào parallel mapper

Sửa `ArrayList` hay counter ngoài từ nhiều callback gây data race. Trả giá trị qua `map` và dùng collector/reduction an toàn.

### Lỗi 11. Dùng `map(String::length)` cho mọi phép tính primitive

Với `sum`/`average` trên số nguyên, `mapToInt` thường diễn đạt rõ và tránh boxing không cần thiết. Tuy nhiên, nếu cần List số nguyên, `map` vẫn phù hợp.

### Lỗi 12. Nghĩ mapper luôn được gọi đúng một lần cho mọi phần tử nguồn

Pipeline có thể short-circuit, tối ưu bỏ stage hoặc dừng do exception. Java không hứa mọi callback sẽ được gọi trong mọi terminal. Đừng dùng mapper để đếm request hoặc ghi audit bắt buộc.

### Lỗi 13. Nghĩ song song giữ thứ tự callback

Với parallel Stream, thứ tự thực thi mapper không được bảo đảm; chỉ encounter order của **kết quả** được giữ khi nguồn/terminal bảo đảm điều đó.

### Lỗi 14. Tự ép kiểu generic để tránh compiler báo lỗi

`Stream<Order>` không thể được cast an toàn thành `Stream<String>` chỉ để lấy tên. Dùng `map(Order::getName)` để chuyển dữ liệu thực sự, không dùng unchecked cast.

### Lỗi 15. Không xem lại thứ tự giữa `map`, `filter`, `distinct`

`map(...).distinct()` khác `distinct().map(...)`; `map(String::trim).filter(notEmpty)` khác `filter(notEmpty).map(String::trim)`. Thứ tự thay đổi nghĩa nghiệp vụ.

### Lỗi 16. Dùng `Collectors.toList()` rồi mặc định luôn là ArrayList mutable

Javadoc không bảo đảm loại List cụ thể. Nếu yêu cầu `ArrayList`, dùng `Collectors.toCollection(ArrayList::new)`. Nếu cần danh sách không thể sửa trên Java 16+, xem `Stream.toList()` theo hợp đồng phiên bản.

### Lỗi 17. Tưởng `map` tự chuyển đổi schema JSON hoặc join bảng

`map` chỉ gọi hàm ánh xạ. Nếu dữ liệu cần parse JSON, validate schema hoặc join theo khóa, phải chọn logic/library tương ứng và xử lý lỗi riêng.

### Lỗi 18. Bỏ qua bản chất single-use của Stream

`Stream` không được tái sử dụng sau khi đã bị tiêu thụ. Tạo Stream mới từ Collection nếu cần một lần tính toán mới:

```java
List<String> words = Arrays.asList("A", "BB");

long count = words.stream().count();
List<Integer> lengths = words.stream()
        .map(String::length)
        .collect(Collectors.toList());
```

Hai phép tính dùng **hai Stream mới**, không phải cùng Stream đã bị duyệt hai lần.

## 20. Bảng chọn thao tác biến đổi đúng

| Nhu cầu | Operation phù hợp | Ví dụ |
| --- | --- | --- |
| Lấy tên từ mỗi user | `map` | `users.stream().map(User::getName)` |
| Chuyển String thành độ dài | `map` | `words.stream().map(String::length)` |
| Chuẩn hóa mỗi chuỗi | `map` | `words.stream().map(String::trim)` |
| Tạo DTO từ mỗi entity | `map` | `entities.stream().map(EntityDto::from)` |
| Lấy tổng số nguyên không cần boxing | `mapToInt` | `words.stream().mapToInt(String::length).sum()` |
| Lấy tổng số long từ object | `mapToLong` | `orders.stream().mapToLong(Order::amount).sum()` |
| Lấy giá trị double | `mapToDouble` | `texts.stream().mapToDouble(Double::parseDouble)` |
| Loại phần tử không đạt điều kiện | `filter` | `words.stream().filter(s -> !s.isEmpty())` |
| Một input thành nhiều kết quả | `flatMap` | `groups.stream().flatMap(List::stream)` |
| Từ primitive sang String | `mapToObj` | `IntStream.range(1,3).mapToObj(String::valueOf)` |
| Chỉ lấy phần tử đầu sau map | `findFirst` | `stream.map(f).findFirst()` |
| Chuyển kết quả thành List | `collect(toList())` | `stream.map(f).collect(toList())` |
| Cập nhật Collection tại chỗ | Không dùng `Stream.map` như mutation API | Chọn API Collection thích hợp |
| Ghi side effect theo từng phần tử | Terminal rõ nghĩa, ví dụ `forEach` | Không dựa vào `map` mà bỏ kết quả |

Các class `User`, `Order`, `EntityDto` và biến `stream` trong bảng là **tên minh họa**; chúng không phải API built-in của JDK. Mục tiêu bảng là cách chọn operation, không phải tạo chương trình độc lập.

## 21. Checklist trước khi hoàn thành một pipeline `map`

1. **Một input có tạo đúng một output không?** Nếu không, xem `filter`/`flatMap`.
2. **Kiểu `T` và `R` là gì?** Compiler đã suy luận đúng chưa?
3. **Mapper có được phép trả null không?** Nếu có, downstream biết xử lý chưa?
4. **Mapper có nhận null được không?** Nếu không, lọc/validate trước khi gọi.
5. **Có checked exception không?** Nếu có, cần hợp đồng xử lý rõ.
6. **Mapper có sửa Collection nguồn không?** Không được để interference phá traversal.
7. **Mapper có phụ thuộc biến mutable ngoài không?** Nếu có, cân nhắc thiết kế lại để stateless.
8. **Có đang dùng `map` thay cho log/audit/count side effect không?** Đưa công việc đó vào nơi có contract rõ.
9. **Có cần `mapToInt`/`mapToLong`/`mapToDouble` không?** Tránh boxing không cần thiết.
10. **Có cần giữ encounter order không?** Kiểm tra source và terminal, nhất là khi parallel.
11. **Stage map đặt trước/sau filter/distinct đúng nghiệp vụ chưa?**
12. **Có dùng terminal phù hợp không?** `collect`, `sum`, `reduce`, `findFirst`, v.v.
13. **Có thể short-circuit không?** Đừng giả định mọi mapper chạy.
14. **Code có cần tương thích Java 8 không?** Đừng dùng `record`/`Stream.toList`/`Optional.stream`/`mapMulti` nếu source level chưa hỗ trợ.
15. **Nếu tạo DTO, có quản lý field được phép xuất và defensive copies khi cần không?**
16. **Nếu parse dữ liệu lỗi, có ghi nhận policy rõ ràng thay vì âm thầm làm mất dữ liệu không?**
17. **Đã test dữ liệu rỗng, null, sai định dạng, Unicode, giá trị lớn và thứ tự nguồn chưa?**
18. **Đã test riêng helper mapper khi logic phức tạp chưa?** Điều này thường dễ hơn debug một lambda dài trong pipeline.
19. **Có đang dùng lại Stream đã bị tiêu thụ không?** Tạo Stream mới khi cần.
20. **Nếu cần tối ưu hiệu năng, đã đo trên workload thật chưa?** Đừng đoán rằng parallel hoặc boxing luôn là nút thắt.

## 22. Tự kiểm tra

1. `Stream.map` trả một `List` hay một `Stream`?
2. Trong `Stream<String>.map(String::length)`, `T` và `R` là gì?
3. Vì sao `map` là lazy và một terminal như `count` đôi khi không gọi mapper?
4. `map` khác `filter` ở việc thay đổi số phần tử như thế nào?
5. Khi dùng `groups.stream().map(List::stream)`, kết quả là `Stream<T>` hay `Stream<Stream<T>>`?
6. Khi nào nên chọn `mapToInt` thay cho `map`?
7. `map(String::trim).filter(notEmpty)` có giống `filter(notEmpty).map(String::trim)` không?
8. `Stream.map` có tự loại kết quả null không? `findFirst` sẽ làm gì nếu phần tử được chọn null?
9. `map(Integer::valueOf)` gặp input `"bad"` thì điều gì xảy ra và vào lúc nào?
10. Vì sao `Function.apply` không cho checked exception tự thoát ra?
11. Nếu `parallelStream` cho một List ordered, mapper chạy theo thứ tự nguồn hay kết quả List mới giữ encounter order theo collector?
12. Vì sao không nên dùng shared `ArrayList.add` bên trong mapper parallel?
13. `map(...).distinct()` khác `distinct().map(...)` ở tiêu chí duplicate thế nào?
14. `Optional.map` có coi null giống với `Stream.map` không?
15. `Stream.toList()` và `Optional.stream()` có chạy trên Java 8 không?
16. Khi nào tách mapper phức tạp thành một method riêng sẽ tốt hơn một lambda dài?
17. `Stream.map` và `java.util.Map<K,V>` khác nhau ở vai trò nào?
18. Nếu cần tạo object DTO mà các trường chứa mutable collection, bản copy có thật sự độc lập không?

**Kết luận:** `Stream.map` là công cụ chuẩn để diễn đạt phép biến đổi **một phần tử thành một giá trị** trong pipeline. Nó giúp code rõ ràng, có thể chuyển kiểu `T -> R`, kết hợp tốt với `filter`, `distinct` và terminal operations. Nhưng `map` **lazy**, không sửa nguồn, không tự loại phần tử, không tự xử lý lỗi hoặc null, và không được dùng như một lệnh side effect bắt buộc. Khi xử lý số học, chọn primitive mappers nếu phù hợp; khi một input sinh 0..N kết quả, dùng `flatMap`. Một mapper thuần, stateless, non-interfering và có policy lỗi rõ ràng là nền tảng cho pipeline đúng trên cả sequential lẫn parallel Stream.

## Tài liệu tham khảo chuẩn

- Java SE 25 API, **`Stream.map`**, `mapToInt`, `mapToLong`, `mapToDouble`, `flatMap`, `count`, `findFirst`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html
- Java SE 25, **`java.util.stream` package summary** — laziness, stateless/non-interfering mappers, source, terminal, optimization: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html
- Java SE 25 API, **`Function`**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/Function.html
- Java SE 25 API, **`IntStream`**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/IntStream.html
- Java SE 25 API, **`Collectors`**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html
- Java SE 25 API, **`Optional`**: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Optional.html
