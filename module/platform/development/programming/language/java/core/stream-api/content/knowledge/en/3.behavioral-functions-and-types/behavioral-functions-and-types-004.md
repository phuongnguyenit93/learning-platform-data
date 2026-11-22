# Suy luận kiểu, generic và xử lý lỗi biên dịch trong pipeline

## 1. Vì sao cần hiểu kiểu dữ liệu khi dùng Stream API?

Java Stream API giúp xử lý dữ liệu theo cách khai báo: lấy dữ liệu từ nguồn, đưa qua các phép toán trung gian như `filter`, `map` rồi kết thúc bằng `collect` hoặc `reduce`. Pipeline có thể **lazy** (trì hoãn xử lý), nhưng **trình biên dịch vẫn kiểm tra kiểu** của mọi phép toán ngay lúc biên dịch.

Khi mới học Stream API, một biểu thức ngắn có thể gây khó hiểu:

```java
List<Integer> doDai = tenKhoaHoc.stream()
    .filter(ten -> ten.length() >= 4)
    .map(String::length)
    .collect(Collectors.toList());
```

Tại sao `filter` cần trả về `boolean`, `map` có thể đổi từ `String` sang `Integer`, và `collect` phải khớp với `List<Integer>`? Đó là công việc của **generic**, **functional interface** và **type inference** (suy luận kiểu).

Bài thuộc chương **Hàm hành vi và kiểu dữ liệu** của module `JAVA_STREAM_API`, tập trung vào cách đọc kiểu trong pipeline, chẩn đoán lỗi biên dịch và sửa lỗi đúng nguyên nhân. Kỹ năng này cũng là nền tảng trước khi làm việc với `groupingBy`, collector tùy chỉnh, xử lý song song, `Spliterator` và Stream Gatherers.

Sau bài này, bạn có thể:

- Theo dõi kiểu `T` và `R` qua từng bước trong pipeline.
- Hiểu trình biên dịch suy luận kiểu tham số lambda và kết quả `map` như thế nào.
- Nhận ra vai trò của `Predicate`, `Function`, `Comparator` và các wildcard `? super`, `? extends`.
- Sửa các lỗi thường gặp khi kết hợp `filter`, `map`, `flatMap`, `mapToInt` và `collect`.
- Phân biệt lỗi **biên dịch** với lỗi **xảy ra lúc chạy**.

## 2. Ví dụ chạy được: theo dõi kiểu từ đầu đến cuối

Mã sau tương thích **Java 8 trở lên**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class KieuTrongPipeline {
    public static void main(String[] args) {
        List<String> tenKhoaHoc = Arrays.asList(
            " Java ", "Go", "Kotlin", "java api"
        );

        List<Integer> doDai = tenKhoaHoc.stream()
            .map(String::trim)
            .filter(ten -> ten.length() >= 4)
            .map(String::length)
            .collect(Collectors.toList());

        System.out.println(doDai); // [4, 6, 8]
    }
}
```

Đọc pipeline như một chuỗi chuyển đổi kiểu:

```text
List<String> tenKhoaHoc
       │ stream()
       ▼
Stream<String>
       │ map(String::trim)
       ▼
Stream<String>
       │ filter(ten -> ten.length() >= 4)
       ▼
Stream<String>
       │ map(String::length)
       ▼
Stream<Integer>
       │ collect(Collectors.toList())
       ▼
List<Integer>
```

| Biểu thức | Kiểu kết quả | Lý do |
| --- | --- | --- |
| `tenKhoaHoc` | `List<String>` | Mỗi phần tử là một tên dạng `String`. |
| `tenKhoaHoc.stream()` | `Stream<String>` | `stream()` giữ kiểu phần tử của nguồn. |
| `.map(String::trim)` | `Stream<String>` | `trim()` nhận chuỗi và trả về chuỗi. |
| `.filter(ten -> ten.length() >= 4)` | `Stream<String>` | `filter` chỉ chọn hoặc loại phần tử, không thay đổi kiểu. |
| `.map(String::length)` | `Stream<Integer>` | `length()` trả về `int`, được boxing thành `Integer` trong `Stream<Integer>`. |
| `.collect(Collectors.toList())` | `List<Integer>` | Thu phần tử của `Stream<Integer>` thành danh sách. |

Lưu ý: `map` và `filter` là các phép toán trung gian lazy. Suy luận kiểu diễn ra khi biên dịch; việc duyệt dữ liệu thực sự diễn ra khi gọi phép toán kết thúc `collect`. Hai vấn đề này độc lập với nhau.

## 3. Đọc chữ ký generic của các phép toán

Ta có thể hình dung một `Stream<T>` là luồng các phần tử kiểu `T`. Một số chữ ký quan trọng (rút gọn từ API Java) là:

```java
// T là kiểu phần tử hiện tại của Stream<T>.
Stream<T> filter(Predicate<? super T> predicate);

<R> Stream<R> map(Function<? super T, ? extends R> mapper);

<R, A> R collect(Collector<? super T, A, R> collector);
```

Ý nghĩa:

- `filter` nhận điều kiện kiểm tra một phần tử `T` và trả lại luồng **cùng kiểu `T`**.
- `map` nhận hàm biến đổi từ `T` sang `R`; đầu ra là **`Stream<R>`**. `R` có thể bằng hoặc khác `T`.
- `collect` nhận collector có thể xử lý phần tử của luồng và tạo ra giá trị tổng hợp kiểu `R`. Chữ `A` trong `Collector<T, A, R>` là kiểu tích lũy nội bộ, thường không cần viết tường minh khi dùng collector có sẵn.

Chẳng hạn:

```java
List<String> ten = Arrays.asList("Java", "Go", "Kotlin");

List<Integer> doDai = ten.stream()
    .map(String::length)
    .collect(Collectors.toList());
```

Từ `String::length`, trình biên dịch xác định `R = Integer` (sau boxing). Vì vậy, trong lệnh gán cuối, `List<Integer>` là kiểu phù hợp.

### 3.1. Functional interface quyết định kiểu của lambda

Một **functional interface** có đúng một phương thức trừu tượng (Single Abstract Method, SAM). Khi lambda hoặc method reference nằm trong lời gọi Stream, Java dùng kiểu tham số được mong đợi (**target type**) để kiểm tra chúng.

| Functional interface | Phương thức khái niệm | Thường dùng với |
| --- | --- | --- |
| `Predicate<T>` | `boolean test(T value)` | `filter` |
| `Function<T, R>` | `R apply(T value)` | `map` |
| `Consumer<T>` | `void accept(T value)` | `forEach` |
| `Comparator<T>` | `int compare(T a, T b)` | `sorted` |
| `BinaryOperator<T>` | `T apply(T a, T b)` | `reduce` với hai giá trị cùng kiểu |

Cùng một lambda có thể được viết rõ kiểu hơn:

```java
import java.util.function.Function;
import java.util.function.Predicate;

Predicate<String> duDai = ten -> ten.length() >= 4;
Function<String, Integer> layDoDai = ten -> ten.length();

List<Integer> ketQua = ten.stream()
    .filter(duDai)
    .map(layDoDai)
    .collect(Collectors.toList());
```

Trong lời gọi `.filter(ten -> ten.length() >= 4)`, `ten` được suy luận là `String` vì stream đầu vào là `Stream<String>`. Không cần khai báo lại kiểu `String` cho từng tham số lambda.

### 3.2. Method reference cũng cần target type

`String::length` là cách viết gọn tương đương `s -> s.length()` khi target type là `Function<String, Integer>`.

```java
Function<String, Integer> layDoDai = String::length;
List<Integer> doDai = ten.stream()
    .map(layDoDai)
    .collect(Collectors.toList());
```

Không thể suy luận một method reference **đứng riêng** nếu thiếu target type:

```java
// KHÔNG BIÊN DỊCH (Java 10+): method reference thiếu target type.
var layDoDai = String::length;
```

Cách sửa là cung cấp functional interface:

```java
Function<String, Integer> layDoDai = String::length;
```

Từ khóa `var` suy luận kiểu từ biểu thức khởi tạo; bản thân method reference chưa có kiểu cụ thể để `var` suy luận. Trong `stream.map(String::length)`, ngược lại, tham số của `map` đã cung cấp target type.

## 4. Generics trong pipeline: `T`, `R` và wildcard

### 4.1. `Stream<String>` khác `Stream<Integer>`

Java kiểm tra kiểu phần tử qua từng lời gọi. Ví dụ này **không biên dịch**:

```java
List<String> ten = Arrays.asList("Java", "Go");

// SAI: String::length tạo ra Integer, không tạo ra String.
List<String> doDai = ten.stream()
    .map(String::length)
    .collect(Collectors.toList());
```

Sửa kiểu biến nhận kết quả:

```java
List<Integer> doDai = ten.stream()
    .map(String::length)
    .collect(Collectors.toList());
```

Không nên ép kiểu để che lỗi. Hãy đặt câu hỏi: “**Sau bước cuối cùng của pipeline, mỗi phần tử thực sự có kiểu gì?**”

### 4.2. Generic là bất biến (invariant)

Dù `Integer` là kiểu con của `Number`, `Stream<Integer>` **không** phải là kiểu con của `Stream<Number>`.

```java
List<Integer> so = Arrays.asList(1, 2, 3);

// KHÔNG BIÊN DỊCH:
Stream<Number> luongSo = so.stream();
```

Hai cách hợp lệ, tùy mục đích:

```java
// Chỉ cần đọc các giá trị dưới dạng Number:
Stream<? extends Number> luongSo1 = so.stream();

// Cần chính xác Stream<Number>, chủ động chuyển kiểu từng phần tử:
Stream<Number> luongSo2 = so.stream()
    .map(n -> (Number) n);
```

Với cách thứ nhất, `? extends Number` diễn đạt “một kiểu nào đó là `Number` hoặc kiểu con của nó”. Không tự suy đoán rằng mọi generic chứa kiểu con đều thay thế được generic chứa kiểu cha.

### 4.3. Vì sao có `? super T` và `? extends R`?

Chữ ký `map` là:

```java
<R> Stream<R> map(Function<? super T, ? extends R> mapper);
```

- `? super T` ở **đầu vào**: hàm có thể nhận `T` hoặc một kiểu cha của `T`.
- `? extends R` ở **đầu ra**: hàm có thể trả `R` hoặc một kiểu con của `R`.

Ví dụ:

```java
import java.util.function.Function;

Function<CharSequence, String> chuanHoa =
    value -> value.toString().trim();

List<String> ten = Arrays.asList(" Java ", " Go ");
List<String> ketQua = ten.stream()
    .map(chuanHoa)
    .collect(Collectors.toList());

System.out.println(ketQua); // [Java, Go]
```

Hàm `chuanHoa` nhận `CharSequence`, là kiểu cha (interface được `String` triển khai), nên vẫn dùng được để xử lý `Stream<String>`.

Mẹo nhớ **PECS**: *Producer Extends, Consumer Super*. Đầu vào nhận/tiêu thụ `T` thường linh hoạt với `super`; kết quả sinh/xuất ra thường linh hoạt với `extends`. Đây là cách đọc wildcard trong chữ ký API, không phải yêu cầu phải tự viết wildcard ở mọi pipeline.

### 4.4. Viết hàm generic tái sử dụng

Khi truyền bộ lọc và phép biến đổi như tham số, nên giữ mối liên hệ giữa kiểu nguồn `T` và kiểu đích `R`:

```java
import java.util.List;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public static <T, R> List<R> chonVaBienDoi(
        List<T> nguon,
        Predicate<? super T> dieuKien,
        Function<? super T, ? extends R> phepBienDoi) {

    return nguon.stream()
        .filter(dieuKien)
        .map(phepBienDoi)
        .collect(Collectors.toList());
}
```

Lời gọi:

```java
List<String> ten = Arrays.asList("Java", "Go", "Kotlin");

List<Integer> doDai = chonVaBienDoi(
    ten,
    s -> s.length() >= 4,
    String::length
);

System.out.println(doDai); // [4, 6]
```

Trình biên dịch suy luận `T = String`, `R = Integer` từ `List<String>` và `String::length`. Không cần dùng raw type (`List` hoặc `Stream` không có tham số kiểu).

## 5. Những lỗi biên dịch thường gặp và cách sửa

> Các đoạn được ghi “KHÔNG BIÊN DỊCH” là ví dụ cố ý sai để phân tích lỗi; không chép nguyên chúng vào một chương trình cần chạy. Thông báo lỗi cụ thể có thể khác nhau theo phiên bản `javac` hoặc IDE.

### Lỗi 1: `filter` trả về giá trị khác `boolean`

```java
// KHÔNG BIÊN DỊCH: length() trả về int, không phải boolean.
ten.stream()
    .filter(s -> s.length())
    .collect(Collectors.toList());
```

`filter` cần một `Predicate<String>`. Sửa bằng một điều kiện so sánh:

```java
List<String> ketQua = ten.stream()
    .filter(s -> s.length() >= 4)
    .collect(Collectors.toList());
```

Nếu muốn **lấy độ dài** thay vì **lọc theo độ dài**, hãy dùng `map(String::length)`.

### Lỗi 2: Kiểu biến nhận không khớp với `map`

```java
// KHÔNG BIÊN DỊCH: collect tạo List<Integer>.
List<String> ketQua = ten.stream()
    .map(String::length)
    .collect(Collectors.toList());
```

Sửa `List<String>` thành `List<Integer>`, hoặc thay phép `map` để đầu ra thật sự là chuỗi. Tránh dùng ép kiểu `(List<String>)` vì không giải quyết được sự khác biệt kiểu phần tử.

### Lỗi 3: Kiểu của phần tử đã rộng thành `Object`

```java
import java.util.stream.Stream;

Stream<Object> duLieu = Stream.of("Java", 42);

// KHÔNG BIÊN DỊCH: method reference yêu cầu String,
// nhưng mỗi phần tử hiện được nhìn nhận là Object.
duLieu.map(String::length);
```

Một cách xử lý dữ liệu hỗn hợp là lọc và kiểm tra kiểu trước khi chuyển kiểu:

```java
List<Integer> doDai = Stream.<Object>of("Java", 42)
    .filter(String.class::isInstance)
    .map(String.class::cast)
    .map(String::length)
    .collect(Collectors.toList());

System.out.println(doDai); // [4]
```

Sau `.map(String.class::cast)`, kiểu đã là `Stream<String>`, nên `String::length` hợp lệ. Với dữ liệu đồng nhất, giải pháp tốt hơn là khai báo nguồn đúng `List<String>` ngay từ đầu.

### Lỗi 4: Nhầm `map` với `flatMap`

Cho danh sách chứa nhiều danh sách con:

```java
List<List<String>> nhom = Arrays.asList(
    Arrays.asList("Java", "Kotlin"),
    Arrays.asList("Go")
);
```

`map(List::stream)` tạo **stream của các stream**, nên gán vào `List<String>` sẽ không biên dịch:

```java
// KHÔNG BIÊN DỊCH: kết quả là List<Stream<String>>.
List<String> tatCa = nhom.stream()
    .map(List::stream)
    .collect(Collectors.toList());
```

`flatMap` làm phẳng các stream con thành một `Stream<String>`:

```java
List<String> tatCa = nhom.stream()
    .flatMap(List::stream)
    .collect(Collectors.toList());

System.out.println(tatCa); // [Java, Kotlin, Go]
```

Hãy xem kiểu đầu ra của biểu thức trong `map`: nếu nó đã là `Stream<X>` nhưng bạn muốn từng `X`, hãy cân nhắc `flatMap`.

### Lỗi 5: Trộn `Stream<Integer>` và `IntStream`

`map(String::length)` tạo `Stream<Integer>`, còn `mapToInt(String::length)` tạo **`IntStream`**, một luồng chuyên biệt cho kiểu nguyên thủy `int`.

```java
import java.util.stream.IntStream;

IntStream doDai = ten.stream().mapToInt(String::length);
int tongDoDai = ten.stream().mapToInt(String::length).sum();
```

`IntStream` **không** có overload `collect(Collector)` như `Stream<T>`:

```java
// KHÔNG BIÊN DỊCH: IntStream không nhận Collector ở đây.
List<Integer> doDai = ten.stream()
    .mapToInt(String::length)
    .collect(Collectors.toList());
```

Sửa bằng `boxed()` để quay lại `Stream<Integer>`:

```java
List<Integer> doDai = ten.stream()
    .mapToInt(String::length)
    .boxed()
    .collect(Collectors.toList());
```

Nếu chỉ cần tổng, trung bình hoặc giá trị lớn nhất, ưu tiên dùng `sum()`, `average()`, `max()` của `IntStream` mà không boxing không cần thiết.

### Lỗi 6: Lambda gọi phương thức có checked exception

Các functional interface thông dụng như `Function.apply` **không khai báo checked exception**. Ví dụ `Files.readAllLines` có thể ném `IOException`:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.List;

List<Path> tep = Arrays.asList(Paths.get("du-lieu.txt"));

// KHÔNG BIÊN DỊCH: IOException chưa được xử lý.
tep.stream().map(Files::readAllLines);
```

Xử lý lỗi bên trong lambda, ví dụ chuyển thành `UncheckedIOException` để vẫn giữ nguyên nguyên nhân:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Path> tep = Arrays.asList(Paths.get("du-lieu.txt"));

List<String> cacDong = tep.stream()
    .map(path -> {
        try {
            return Files.readAllLines(path);
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    })
    .flatMap(List::stream)
    .collect(Collectors.toList());
```

Đây là một chiến lược xử lý lỗi, không phải cách duy nhất. Để chạy ví dụ, cần có file `du-lieu.txt` ở đúng thư mục làm việc hoặc thay bằng đường dẫn file thực. Với tài nguyên lớn, cần cân nhắc mở/đóng tài nguyên đúng cách; ví dụ `Files.lines` trả về stream gắn với tài nguyên I/O và cần được đóng.

### Lỗi 7: Biến bị lambda bắt giữ không còn “effectively final”

```java
int doDaiToiThieu = 4;

// KHÔNG BIÊN DỊCH khi biến được gán lại bên dưới.
List<String> ketQua = ten.stream()
    .filter(s -> s.length() >= doDaiToiThieu)
    .collect(Collectors.toList());

doDaiToiThieu = 6;
```

Biến cục bộ được lambda sử dụng phải là `final` hoặc **effectively final** (không bị gán lại sau lần khởi tạo).

```java
final int doDaiToiThieu = 4;

List<String> ketQua = ten.stream()
    .filter(s -> s.length() >= doDaiToiThieu)
    .collect(Collectors.toList());
```

Lưu ý: quy tắc này nói về việc **gán lại tham chiếu/biến cục bộ**, không có nghĩa là mọi đối tượng được tham chiếu đều bất biến. Tuy nhiên, thay đổi trạng thái bên ngoài lambda có thể làm pipeline khó hiểu và đặc biệt nguy hiểm khi chuyển sang xử lý song song.

### Lỗi 8: Dùng raw type làm mất thông tin generic

```java
// Không nên: List không có <String>.
List tenKhongKieu = Arrays.asList("Java", "Go");
```

Raw type làm mất kiểm tra kiểu tĩnh, thường phát sinh cảnh báo unchecked và khiến các tham số của lambda bị nhìn nhận quá rộng. Chỉ cần khai báo kiểu đầy đủ:

```java
List<String> ten = Arrays.asList("Java", "Go");

List<Integer> doDai = ten.stream()
    .map(String::length)
    .collect(Collectors.toList());
```

Không dùng `@SuppressWarnings("unchecked")` để giấu lỗi mà chưa khôi phục ràng buộc kiểu dữ liệu thực sự.

## 6. Cách chẩn đoán khi IDE báo “cannot infer type” hoặc “incompatible types”

Các thông báo như `cannot infer type-variable(s)`, `bad return type in lambda expression`, `invalid method reference` hoặc `incompatible types` thường chỉ ra một **điểm xung đột kiểu**. Thông báo chính xác phụ thuộc công cụ biên dịch; hãy xem dòng lỗi cùng các kiểu “required” và “found” nếu có.

Làm theo thứ tự:

1. **Xác nhận kiểu nguồn**: `List<String>`, `List<MyType>`, `Stream<?>` hay raw `List`? Kiểu đầu vào quyết định lambda nhận gì.
2. **Tách pipeline theo từng bước**: sau `filter` kiểu không đổi; sau `map`, `flatMap`, `mapToInt` kiểu có thể đổi.
3. **Xác định kiểu trả về của lambda/method reference**: `boolean` cho `filter`; kiểu `R` cho `map`; `Stream<R>` cho `flatMap`.
4. **Kiểm tra kiểu đích**: kết quả `collect` có thực sự tương thích với `List<R>`, `Set<R>` hoặc `Map<K, V>` mà bạn đang khai báo không?
5. **Kiểm tra đặc thù Java**: method reference cần target type, lambda không tự khai báo checked exception, biến được bắt giữ phải effectively final.
6. **Bổ sung kiểu tường minh để khoanh vùng**: thử một biến trung gian `Stream<String>`, `Stream<Integer>` hoặc `Function<String, Integer>`. Sau khi sửa xong, có thể gộp lại nếu vẫn dễ đọc.

Ví dụ tách pipeline để tìm lỗi:

```java
List<String> ten = Arrays.asList("Java", "Go", "Kotlin");

Stream<String> s1 = ten.stream();
Stream<String> s2 = s1.filter(s -> s.length() >= 4);
Stream<Integer> s3 = s2.map(String::length);
List<Integer> ketQua = s3.collect(Collectors.toList());
```

Đoạn này chỉ tiêu thụ stream **một lần** ở cuối. Nếu bạn khai báo nhầm `Stream<String> s3`, trình biên dịch sẽ chỉ đúng bước `map` bị lệch kiểu. Khi cần suy luận phức tạp hơn, có thể khai báo tham số lambda tường minh:

```java
List<Integer> ketQua = ten.stream()
    .map((String s) -> s.length())
    .collect(Collectors.toList());
```

Kiểu tường minh giúp đọc lỗi dễ hơn, nhưng **không sửa được** một phép biến đổi vốn không tương thích với đầu vào.

### Ranh giới giữa lỗi biên dịch và lỗi lúc chạy

| Tình huống | Phân loại | Ghi chú |
| --- | --- | --- |
| `filter(s -> s.length())` | Lỗi biên dịch | `Predicate` cần `boolean`. |
| Gán `List<Integer>` vào `List<String>` | Lỗi biên dịch | Generic không tương thích. |
| `map(String::length)` trên `Stream<Object>` | Lỗi biên dịch | Phần tử không được bảo đảm là `String`. |
| Gọi phương thức trên phần tử `null` | Lỗi lúc chạy | Có thể xảy ra `NullPointerException`. |
| Dùng lại stream đã chạy `collect` | Lỗi lúc chạy | Có thể xảy ra `IllegalStateException`. |
| `Collectors.toMap` với khóa trùng và không có hàm gộp | Lỗi lúc chạy | Có thể xảy ra `IllegalStateException` do khóa trùng. |
| Chia sẻ/biến đổi trạng thái ngoài từ lambda | Nguy cơ logic hoặc đồng thời | Có thể vẫn biên dịch nhưng cho kết quả khó đoán. |

Ví dụ dùng lại stream:

```java
Stream<String> luong = ten.stream();
long soLuong = luong.count();

// BIÊN DỊCH ĐƯỢC, nhưng không thể dùng lại luồng đã tiêu thụ.
List<String> danhSach = luong.collect(Collectors.toList());
```

Cách đúng: tạo **stream mới** từ nguồn nếu cần một phép toán kết thúc khác.

## 7. Khi generic xuất hiện trong `reduce` và `collect`

Cơ chế suy luận kiểu không chỉ có ở `map`. Ví dụ, sau khi biến tên thành độ dài, các kiểu tiếp tục quyết định phép kết thúc:

```java
List<String> ten = Arrays.asList("Java", "Go", "Kotlin");

int tong = ten.stream()
    .map(String::length)       // Stream<Integer>
    .reduce(0, Integer::sum);  // Integer, tự unboxing thành int

System.out.println(tong); // 12
```

Với collector nhóm phần tử:

```java
import java.util.Map;

Map<Integer, List<String>> nhomTheoDoDai = ten.stream()
    .collect(Collectors.groupingBy(String::length));

System.out.println(nhomTheoDoDai.get(4)); // [Java]
```

`String::length` đóng vai trò `Function<String, Integer>`, nên khóa của map có kiểu `Integer`. `groupingBy` trả về cấu trúc kết quả phù hợp `Map<Integer, List<String>>`. Trình biên dịch kiểm tra kiểu ngay cả khi pipeline mới chỉ được mô tả.

Khi học collector tùy chỉnh, `Spliterator`, stream song song hoặc Gatherers, hãy tiếp tục áp dụng cùng một thói quen: **xác định kiểu phần tử đi vào, kiểu phần tử đi ra và kiểu kết quả cuối cùng**. Các cơ chế đó có hợp đồng kiểu và vòng đời riêng, không nên suy diễn rằng mọi phép toán đều hoạt động như `map`.

## 8. Bài tập thực hành

### Bài 1: Dự đoán kiểu và kết quả

```java
List<String> ma = Arrays.asList(" A1 ", "B22", " C333 ", "D");

List<Integer> ketQua = ma.stream()
    .map(String::trim)
    .filter(s -> s.length() >= 3)
    .map(String::length)
    .collect(Collectors.toList());
```

Hãy ghi kiểu dữ liệu sau mỗi thao tác và dự đoán nội dung `ketQua`.

### Bài 2: Tìm hai lỗi biên dịch

```java
List<String> ten = Arrays.asList("Java", "Go");

List<String> ketQua = ten.stream()
    .filter(s -> s.length())
    .map(String::length)
    .collect(Collectors.toList());
```

Sửa code để thu được `List<Integer>` chứa độ dài của **những tên có ít nhất 3 ký tự**.

### Bài 3: Chọn `map` hay `flatMap`?

```java
List<List<Integer>> nhomSo = Arrays.asList(
    Arrays.asList(1, 2),
    Arrays.asList(3, 4)
);
```

Viết pipeline tạo `List<Integer>` với kết quả `[2, 4, 6, 8]`: làm phẳng các danh sách con rồi nhân đôi từng số.

<details>
<summary>Đáp án và giải thích</summary>

**Bài 1:** sau `stream()` là `Stream<String>`; sau `map(String::trim)` vẫn là `Stream<String>`; sau `filter` vẫn là `Stream<String>`; sau `map(String::length)` thành `Stream<Integer>`; sau `collect` là `List<Integer>`. Kết quả là `[3, 4]`, tương ứng `"B22"` và `"C333"`; `"A1"` và `"D"` bị loại do ngắn hơn 3 ký tự.

**Bài 2:** `filter` phải trả về boolean; sau `map(String::length)`, danh sách chứa `Integer`.

```java
List<Integer> ketQua = ten.stream()
    .filter(s -> s.length() >= 3)
    .map(String::length)
    .collect(Collectors.toList());

// [4]
```

**Bài 3:** `flatMap` biến `Stream<List<Integer>>` thành `Stream<Integer>`, sau đó `map` nhân đôi:

```java
List<Integer> ketQua = nhomSo.stream()
    .flatMap(List::stream)
    .map(n -> n * 2)
    .collect(Collectors.toList());

// [2, 4, 6, 8]
```

</details>

## 9. Ghi nhớ

Một pipeline được kiểm tra kiểu từ trái sang phải:

- `Stream<T>` chỉ ra **kiểu phần tử hiện tại**.
- `filter(Predicate<? super T>)` giữ nguyên `T` và yêu cầu biểu thức trả `boolean`.
- `map(Function<? super T, ? extends R>)` thay đổi kiểu phần tử thành `R`.
- `flatMap` được dùng khi mỗi phần tử cần mở rộng thành một stream con rồi làm phẳng.
- `collect` phải tạo kết quả tương thích với **kiểu biến nhận**.
- Method reference cần target type; raw type, wildcard dùng sai và checked exception đều có thể gây lỗi biên dịch.

Khi gặp lỗi khó hiểu, hãy viết kiểu cụ thể tại các điểm chuyển tiếp rồi kiểm tra từng lambda. Cách này vừa giúp sửa lỗi nhanh vừa làm pipeline dễ đọc, dễ bảo trì trước khi học các phép xử lý Stream API nâng cao.
