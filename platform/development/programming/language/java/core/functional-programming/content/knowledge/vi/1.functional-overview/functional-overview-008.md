# Lộ trình học lập trình hàm trong Java và kiến thức nền tảng cần có

## 1. Mục tiêu và phạm vi

**Lập trình hàm (functional programming, FP)** là cách tổ chức chương trình xoay quanh việc tạo, kết hợp và áp dụng các hàm lên dữ liệu. Thay vì tập trung vào một chuỗi lệnh thay đổi trạng thái, ta thường mô tả *dữ liệu đầu vào được biến đổi thành kết quả nào*. Java là ngôn ngữ đa mô hình: có thể dùng tư duy hàm cùng lập trình hướng đối tượng, vòng lặp và API truyền thống. Sử dụng lambda hoặc Stream **không tự động** khiến một đoạn mã trở thành hàm thuần khiết.

Bài này là **bản đồ học tập** cho module Java Core – functional-programming: biết cần chuẩn bị gì, học theo thứ tự nào, thực hành ra sao và tự kiểm tra thế nào. Sau lộ trình, người học nên có thể:

- Nhận diện đầu vào, đầu ra, trạng thái có thể thay đổi và tác dụng phụ của một phép xử lý.
- Đọc, viết và chọn đúng functional interface, lambda, method reference.
- Thực hiện chuỗi chuyển đổi dữ liệu bằng Stream, hiểu thời điểm Stream thực thi.
- Sử dụng `Optional` và phép kết hợp hàm trong phạm vi phù hợp.
- Cân nhắc tính dễ đọc, chi phí, lỗi và tính an toàn khi áp dụng FP vào Java thực tế.

Không cần có kinh nghiệm với Haskell, Scala hoặc thư viện lập trình hàm chuyên biệt để bắt đầu.

## 2. Kiến thức nền tảng trước khi bắt đầu

| Kiến thức | Vì sao cần | Tự kiểm tra |
| --- | --- | --- |
| Biến, kiểu nguyên thủy và kiểu tham chiếu; toán tử, `if`, `for` | Đọc điều kiện lọc, phép biến đổi, phân biệt giá trị với đối tượng | Lọc danh sách số chẵn bằng vòng lặp |
| Phương thức, tham số, giá trị trả về, phạm vi biến | Hiểu hàm như một phép biến đổi có đầu vào/đầu ra | Viết `int square(int x)` |
| Class, object, interface, kế thừa cơ bản | Functional interface vẫn là một interface; lambda có kiểu đích | Khai báo interface với một phương thức trừu tượng |
| Generic `List<T>`, `Map<K,V>`, kiểu tham số hóa | `Stream<T>`, `Function<T,R>` và kết quả `collect` phụ thuộc generic | Viết phương thức nhận `List<String>` |
| Collections, `equals`, `hashCode`, thứ tự phần tử | Stream thường xử lý collection; so sánh và sắp xếp cần đúng ngữ nghĩa | Sắp xếp danh sách, loại phần tử theo điều kiện |
| Ngoại lệ checked/unchecked và `null` | Lambda có giới hạn xử lý checked exception; `Optional` mô hình hóa khả năng vắng mặt | Phân biệt `throw` và `throws`, kiểm tra `null` |
| Đọc Javadoc, chạy `javac`/`java`, dùng IDE/debugger | Tự kiểm chứng chữ ký API, kiểu dữ liệu, hành vi thực tế | Biên dịch và chạy một class Java |

**Mốc xuất phát:** nếu còn gặp khó khăn khi viết vòng lặp thao tác `List`, nên ôn phương thức, generic và Collections trước khi chuyển sang Stream. Nếu đã vững các phần đó, có thể học ngay từ functional interface và lambda. Các ví dụ chạy độc lập dưới đây dùng **JDK 17 trở lên**.

## 3. Tư duy nền: hàm, dữ liệu và tác dụng phụ

Một phép xử lý nên được xem xét qua ba câu hỏi:

1. **Đầu vào và đầu ra là gì?** Ví dụ `priceWithTax(price)` nhận giá và trả giá sau thuế.
2. **Kết quả có chỉ phụ thuộc đầu vào không?** Một hàm thuần (pure function) trả cùng kết quả cho cùng đầu vào và không tạo tác dụng phụ có thể quan sát được.
3. **Có thay đổi gì bên ngoài không?** Ghi file, gọi API, cập nhật biến toàn cục, sửa collection được chia sẻ hoặc in ra màn hình đều có thể là tác dụng phụ.

Ví dụ minh họa (các phương thức bên trong một class, không phải chương trình độc lập):

~~~java
static int doubleValue(int value) {
    return value * 2;          // Thuần: không sửa trạng thái bên ngoài
}

static int total = 0;
static void addToTotal(int value) {
    total += value;            // Có tác dụng phụ: thay đổi biến dùng chung
}
~~~

Ưu tiên tách **tính toán thuần** khỏi **đọc/ghi và điều phối** khi làm mã dễ kiểm thử. Tính bất biến (immutability) giảm nguy cơ dữ liệu bị thay đổi ngoài ý muốn; `String` và `record` hỗ trợ mô hình dữ liệu, `List.of(...)` tạo danh sách không cho sửa cấu trúc. Tuy nhiên, một `List` không sửa được vẫn có thể chứa đối tượng có trạng thái thay đổi được. **Không được nhầm tham chiếu `final` hoặc danh sách unmodifiable với tính bất biến sâu.**

Dạng tư duy thường gặp:

~~~text
Dữ liệu đầu vào → lọc → ánh xạ → nhóm/tổng hợp → kết quả
                        ↘ tác dụng phụ được quản lý ở ranh giới chương trình
~~~

Không phải thao tác nào cũng cần viết theo FP: thuật toán có trạng thái, mã thao tác tài nguyên, phần tối ưu ở vòng lặp hoặc logic ngắn gọn có thể rõ hơn ở cách viết mệnh lệnh.

## 4. Lộ trình theo thứ tự phụ thuộc kiến thức

### Chặng 1 — Tách phép biến đổi khỏi trạng thái

**Học:** tham số/giá trị trả về; hàm thuần và không thuần; sao chép so với sửa trực tiếp; vì sao trạng thái chia sẻ làm test khó.

**Luyện:** từ danh sách giá tiền, tạo danh sách giá đã giảm mà không sửa danh sách đầu vào. Viết riêng hàm tính giá mới. Kiểm tra gọi hai lần cùng đầu vào có kết quả như nhau.

**Đạt khi:** có thể chỉ ra chính xác phần nào tính toán và phần nào in ra, lưu dữ liệu hoặc chỉnh sửa đối tượng.

### Chặng 2 — Functional interface và lambda

**Học:** interface chỉ có **một phương thức trừu tượng** (SAM) là kiểu đích phù hợp cho lambda; `@FunctionalInterface` để trình biên dịch kiểm tra ràng buộc. Phương thức `default`, `static` và các phương thức từ `Object` không biến interface thành nhiều SAM. Cú pháp `x -> x + 1`, `(a, b) -> a + b`, block lambda có `return`.

Các kiểu thường dùng trong `java.util.function`:

| Kiểu | Ý nghĩa | Khi nào chọn |
| --- | --- | --- |
| `Predicate<T>` | `T -> boolean` | Lọc hoặc kiểm tra điều kiện |
| `Function<T,R>` | `T -> R` | Biến đổi một giá trị sang kiểu khác |
| `UnaryOperator<T>` | `T -> T` | Biến đổi nhưng giữ kiểu |
| `Consumer<T>` | `T -> void` | Thực hiện thao tác có tác dụng phụ |
| `Supplier<T>` | `() -> T` | Cung cấp giá trị khi được gọi |
| `BiFunction<T,U,R>` | Hai đối số tạo một kết quả | Kết hợp hai giá trị |
| `Comparator<T>` | So sánh hai giá trị | Sắp xếp hoặc chọn thứ tự |

Ví dụ đoạn mã dùng được bên trong phương thức (với `import java.util.function.*;`):

~~~java
Predicate<String> hasText = s -> s != null && !s.isBlank();
Function<String, Integer> length = String::length;

boolean valid = hasText.test("Java");  // true
int count = length.apply("Java");      // 4
~~~

**Cần phân biệt:** lambda **không phải** phương thức độc lập không có kiểu; trình biên dịch suy luận kiểu theo *target type*. Lambda chỉ chụp biến cục bộ `final` hoặc *effectively final*; đối tượng được tham chiếu vẫn có thể bị thay đổi (điều đó không khiến phép xử lý an toàn trước concurrency).

**Đạt khi:** chuyển được anonymous class đơn giản thành lambda, giải thích được đầu vào/đầu ra của `Predicate` và `Function`, biết khi nào cần interface tự định nghĩa.

### Chặng 3 — Method reference và kết hợp hàm

**Học:** `Type::staticMethod`, `object::instanceMethod`, `Type::instanceMethod`, `Type::new`. Chỉ dùng method reference khi nó giữ đúng ngữ nghĩa và dễ đọc. Học `Function.compose`, `Function.andThen`, `Predicate.and`, `or` và `negate`.

~~~java
Function<String, String> trim = String::trim;
Function<String, String> upper = String::toUpperCase;
Function<String, String> normalize = trim.andThen(upper);

String result = normalize.apply("  java  "); // "JAVA"
~~~

`trim.andThen(upper)` có nghĩa là **trim trước, upper sau**; `trim.compose(upper)` chạy theo thứ tự ngược. Cần xem xét `null` và tính hợp lệ của đầu vào, không mặc định rằng mọi chuỗi xử lý đều an toàn.

**Đạt khi:** có thể diễn đạt một pipeline nhỏ bằng các hàm có tên, không lạm dụng lambda lồng nhau khó đọc.

### Chặng 4 — Stream API: xử lý dữ liệu theo pipeline

**Học:** tạo stream từ collection; các phép trung gian `filter`, `map`, `flatMap`, `distinct`, `sorted`, `limit`; phép kết thúc `toList`, `forEach`, `count`, `reduce`, `collect`, `findFirst`, `anyMatch`. Học stream nguyên thủy `IntStream`, `LongStream`, `DoubleStream` để tính tổng/trung bình tiện và tránh boxing khi phù hợp.

Pipeline có tính **lazy**: phần lớn thao tác trung gian chỉ được thực thi khi gặp terminal operation. Một stream đã tiêu thụ **không dùng lại** được. Stream không phải nơi lưu trữ dữ liệu và thao tác `stream()` không tự sao chép collection nguồn. Cần hiểu *encounter order*, thứ tự sắp xếp, short-circuit và tác dụng phụ.

~~~java
List<String> names = List.of("An", "Bình", "Anh");
List<String> result = names.stream()
        .filter(name -> name.startsWith("A"))
        .sorted()
        .toList(); // ["An", "Anh"] theo thứ tự so sánh String
~~~

**Đạt khi:** đọc được kiểu `Stream<T>` sau từng bước, biết thao tác nào trả stream mới, thao tác nào trả kết quả, và biết dùng vòng lặp khi phù hợp hơn.

### Chặng 5 — Tổng hợp dữ liệu và Optional

**Học:** `Collectors.groupingBy`, `partitioningBy`, `mapping`, `counting`, `summingInt`, `toMap` (phải có chiến lược xử lý khóa trùng), `joining`. Phân biệt `reduce` tổng hợp một giá trị với `collect` gom vào cấu trúc kết quả.

`Optional<T>` biểu diễn một giá trị **có thể có hoặc không**. Ưu tiên `map`, `flatMap`, `filter`, `ifPresent`, `orElseGet`, `orElseThrow` trong tình huống phù hợp. `Optional` không thay thế mọi chỗ dùng `null`, và thường phù hợp hơn cho **giá trị trả về** so với trường dữ liệu hoặc tham số bất kỳ. `orElse(value)` đánh giá đối số ngay; `orElseGet(supplier)` chỉ gọi supplier khi Optional rỗng.

~~~java
String displayName = Optional.ofNullable(rawName)
        .map(String::trim)
        .filter(name -> !name.isEmpty())
        .orElse("Khách");
~~~

Đoạn trên giả sử `rawName` là biến `String` có thể `null`; code là một mảnh đặt trong phương thức với import tương ứng.

**Đạt khi:** tổng hợp được dữ liệu thực tế, giải thích rõ kiểu của kết quả và hành vi khi không có phần tử.

### Chặng 6 — Độ đúng, kiểm thử và tối ưu hợp lý

**Học:** kiểm thử hàm thuần bằng bảng input/output và các trường hợp rỗng, trùng, `null`, giới hạn; đọc stack trace trong lambda; cách checked exception tương tác với SAM. Không nuốt ngoại lệ chỉ để vừa chữ ký lambda.

Nắm rằng `parallelStream()` **không bảo đảm nhanh hơn** và có thể khiến code sai nếu thay đổi mutable state chung. Cần cân nhắc dữ liệu đủ lớn, chi phí chia việc/gộp kết quả, thứ tự, tính kết hợp của phép giảm, shared state và phép đo benchmark. Với `reduce` song song, toán tử kết hợp phải phù hợp tính kết hợp (*associative*) và giá trị khởi đầu (*identity*). Tránh dùng `forEach` để cập nhật `ArrayList` chung từ parallel stream.

**Đạt khi:** có thể chứng minh một cách xử lý đúng và dễ đọc trước khi cân nhắc hiệu năng, biết thử các trường hợp biên thay vì chỉ thử dữ liệu đẹp.

## 5. Ví dụ hoàn chỉnh: chuyển từ vòng lặp sang pipeline

Bài toán: từ danh sách sản phẩm, chỉ lấy sản phẩm **đang bán** với giá **không quá 200.000 đồng**, xuất danh sách tên theo thứ tự chữ và tính tổng giá. Hai cách triển khai dưới đây tạo kết quả giống nhau; cách thứ hai nhấn mạnh phép biến đổi dữ liệu.

Tạo tệp **`LearningPathDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.function.Predicate;

public class LearningPathDemo {
    record Product(String name, int price, boolean available) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("Sách Java", 250_000, true),
                new Product("Bút", 20_000, true),
                new Product("Sách SQL", 180_000, true),
                new Product("Sách cũ", 100_000, false)
        );

        // Cách 1: mệnh lệnh; nêu rõ từng lần cập nhật.
        List<String> imperativeNames = new ArrayList<>();
        int imperativeTotal = 0;
        for (Product product : products) {
            if (product.available() && product.price() <= 200_000) {
                imperativeNames.add(product.name());
                imperativeTotal += product.price();
            }
        }
        Collections.sort(imperativeNames);

        // Cách 2: mô tả tiêu chí và các phép biến đổi.
        Predicate<Product> eligible =
                p -> p.available() && p.price() <= 200_000;

        List<String> functionalNames = products.stream()
                .filter(eligible)
                .map(Product::name)
                .sorted()
                .toList();

        int functionalTotal = products.stream()
                .filter(eligible)
                .mapToInt(Product::price)
                .sum();

        System.out.println(functionalNames);
        System.out.println(functionalTotal);
        System.out.println(imperativeNames.equals(functionalNames)
                && imperativeTotal == functionalTotal);
    }
}
~~~

Chạy với JDK 17+ trong terminal hỗ trợ UTF-8:

~~~bash
javac -encoding UTF-8 LearningPathDemo.java
java LearningPathDemo
~~~

Kết quả chuẩn:

~~~text
[Bút, Sách SQL]
200000
true
~~~

**Đọc từng bước:** `filter(eligible)` giữ sản phẩm hợp lệ; `map(Product::name)` chỉ lấy tên; `sorted()` sắp xếp tên; `toList()` kết thúc pipeline và tạo danh sách không sửa được qua `add/remove` theo hợp đồng API của `Stream.toList()`. Pipeline khác dùng `mapToInt` để biến giá thành luồng `int` và `sum` để tổng hợp. Hai pipeline đi qua dữ liệu hai lần; ở bài nhỏ tính rõ ràng quan trọng hơn vi tối ưu. Khi xử lý dữ liệu lớn hoặc nguồn có chi phí truy cập cao, có thể cân nhắc gom các kết quả trong một lượt với collector thích hợp hoặc một vòng lặp dễ hiểu. Không nên giả định pipeline luôn nhanh hơn.

**Vì sao vẫn cần hiểu cách mệnh lệnh?** Cả hai cách đều có ngữ nghĩa rõ; dùng vòng lặp khi phải giữ nhiều trạng thái có quan hệ phức tạp, xử lý điều kiện thoát sớm theo ý định hoặc khi bản mô tả bằng stream làm mã khó theo dõi. Chọn cách dễ kiểm chứng cho nhóm phát triển.

## 6. Những lỗi phổ biến nên học cách phát hiện sớm

| Lỗi/nhầm lẫn | Tác hại | Hướng xử lý |
| --- | --- | --- |
| Cho rằng lambda luôn là pure function | Tác dụng phụ ẩn làm hành vi khó dự đoán | Rà trạng thái bị đọc/ghi bên ngoài |
| Dùng `map` chỉ để gọi `println` | Biến bước biến đổi thành thao tác phụ | Tách logging ở ranh giới; dùng `forEach` khi chủ đích là side effect |
| Quên terminal operation | Không thấy biến đổi diễn ra vì pipeline còn lazy | Xác định bước kết thúc như `toList` hoặc `count` |
| Tái sử dụng cùng một `Stream` | Có thể gặp `IllegalStateException` | Tạo stream mới từ nguồn khi cần lần xử lý mới |
| Gọi `Optional.get()` không kiểm tra | `NoSuchElementException` khi rỗng | Dùng `orElseThrow`/`orElseGet` hoặc xử lý vắng mặt rõ ràng |
| Gọi `toMap` khi khóa có thể trùng | `IllegalStateException` do duplicate key | Chọn merge function phù hợp ngữ nghĩa |
| Sửa collection nguồn trong pipeline | Có thể gây lỗi và làm mất tính dự đoán | Tránh sửa nguồn khi stream đang duyệt; tạo kết quả mới |
| Cập nhật biến dùng chung trong `parallelStream` | Race condition, kết quả không ổn định | Dùng phép reduction/collector phù hợp và kiểm chứng |
| Nhầm `==` với `equals` trên object | Lọc/so sánh sai | Dùng so sánh giá trị đúng loại; xem xét `Objects.equals` |
| Lạm dụng chuỗi stream quá dài | Khó debug và khó giải thích kiểu | Đặt tên cho predicate/function hoặc tách hàm, dùng vòng lặp khi rõ hơn |

## 7. Kế hoạch thực hành đề xuất

Đây là **thứ tự học**, không phải cam kết thời lượng cố định. Chỉ chuyển chặng khi giải thích được kết quả mình tạo ra.

| Buổi học | Bài tập trọng tâm | Bằng chứng hoàn thành |
| --- | --- | --- |
| 1 — Nền tảng | Chuyển hàm tính giá sang dạng không sửa tham số/biến ngoài; ôn `List<T>` | Hai lần gọi cùng đầu vào cho cùng giá trị |
| 2 — Lambda | Viết `Predicate<Integer>` kiểm tra số dương, `Function<String,Integer>` lấy độ dài | Giải thích được target type và effectively final |
| 3 — Kết hợp hàm | Chuẩn hóa tên bằng `trim` rồi đổi hoa; kết hợp hai predicate | Phân biệt thứ tự `andThen`/`compose` |
| 4 — Stream cơ bản | Lọc số chẵn, bình phương, sắp xếp, lấy 5 phần tử | Nêu đúng kiểu dữ liệu qua từng phép |
| 5 — Stream nâng cao | `flatMap` danh sách lồng nhau; nhóm giao dịch theo loại; xử lý duplicate key | Đối chiếu kết quả bằng vòng lặp |
| 6 — Optional và lỗi | Xử lý tên có thể rỗng; bổ sung trường hợp biên | Không gọi `get` vô điều kiện |
| 7 — Bài tập tổng hợp | Hoàn thiện báo cáo danh sách sản phẩm/đơn hàng | Có chương trình chạy, stdout đúng, test với dữ liệu rỗng |
| 8 — Ôn, kiểm chứng | So sánh loop/stream; xem xét boxing, side effect và parallel | Giải thích lựa chọn rõ ràng, không tối ưu theo cảm tính |

**Bài tự luyện tăng dần:**

1. Với `List<Integer>`, tính tổng bình phương số chẵn theo vòng lặp, rồi viết lại với `mapToInt` và `sum`. Thử danh sách rỗng (tổng bằng 0), số âm và giá trị lớn; cân nhắc tràn `int`.
2. Với `List<String>` có tên trùng/chuỗi trống, tạo danh sách tên không rỗng, loại trùng, sắp xếp. Thử trường hợp `null` riêng: `List.of` không chứa `null`, nên cần xác định hợp đồng dữ liệu đầu vào rõ ràng.
3. Với các giao dịch có `category` và `amount`, tạo tổng số tiền theo loại bằng `Collectors.groupingBy` kết hợp `summingInt`. So kết quả với vòng lặp.
4. Viết phương thức trả `Optional<Product>` để tìm sản phẩm đầu tiên thỏa điều kiện. Viết test cho trường hợp có/không có kết quả.
5. Thử dùng side effect trong `map` rồi giải thích vì sao khó kiểm thử; sửa thành phép biến đổi thuần và đặt thao tác ghi/in ở cuối.

### Cách kiểm thử bài thực hành

- Bắt đầu với dữ liệu nhỏ có kết quả tính tay được, thêm dữ liệu rỗng, không khớp điều kiện, phần tử trùng, giá trị biên.
- Dùng phép so sánh kết quả `equals` giữa bản vòng lặp và bản stream khi cả hai có cùng yêu cầu thứ tự; tránh so bằng tham chiếu `==`.
- Khi có số thực, xem xét sai số; khi cộng giá trị tiền, xem xét `long` hoặc `BigDecimal` tùy miền dữ liệu. Không làm tròn tùy tiện.
- Nếu sửa code để chạy song song, kiểm chứng lại tính đúng và chỉ đo hiệu năng trên dữ liệu/kịch bản đại diện.

## 8. Tiêu chí tự đánh giá và hướng đi tiếp

Bạn đã sẵn sàng đi sâu vào các bài chuyên đề của module khi có thể tự trả lời:

- `Function<T,R>` khác `Predicate<T>`, `Consumer<T>`, `Supplier<T>` ở đâu?
- Tại sao biến cục bộ bị lambda capture phải effectively final? Điều đó có bảo vệ mọi đối tượng khỏi thay đổi không?
- Chặng `filter → map → collect` khác gì vòng lặp? Khi nào pipeline thực sự thực thi?
- `map` khác `flatMap` ra sao? `Stream.toList()` và `Collectors.toList()` có bảo đảm giống nhau về tính sửa được không? (**Không**: `Stream.toList()` trả danh sách unmodifiable; `Collectors.toList()` không cam kết loại hoặc tính sửa được.)
- Tại sao không dùng `Optional.get()` tùy tiện? `orElse` và `orElseGet` khác nhau khi tính giá trị mặc định?
- Khi nào tính toán có side effect gây lỗi, đặc biệt trong stream song song?
- Có thể giải thích bằng dữ liệu cụ thể vì sao cách viết đã chọn đúng, rõ và dễ kiểm thử không?

**Hướng đọc tiếp theo:** đi lần lượt từ Java functional interfaces và lambda/method references đến Stream API, collectors/reduction, Optional, thiết kế hàm thuần và các giới hạn hiệu năng/concurrency. Dùng Javadoc của `java.util.function`, `java.util.stream`, `java.util.Optional` như nguồn tham chiếu chữ ký và hợp đồng API. Mục tiêu là biết *khi nào* mô hình hàm làm mã dễ hiểu, an toàn và kiểm thử được, đồng thời vẫn sử dụng linh hoạt các cấu trúc Java khác khi phù hợp.
