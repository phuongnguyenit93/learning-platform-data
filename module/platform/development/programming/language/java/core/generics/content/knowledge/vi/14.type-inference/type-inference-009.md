# Đọc và xử lý thông báo `inference variable ... has incompatible bounds` trong Java Generics

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định **biến kiểu đang được suy luận** (`T`, `U`, `K`, `V`…) trong thông báo lỗi `javac` và tìm đúng phương thức generic sinh ra biến đó.
- Đọc được các nhóm ràng buộc `equality constraints`, `lower bounds`, `upper bounds`, hiểu vì sao chúng không thể cùng thỏa mãn.
- Phân biệt lỗi do **kiểu đích**, đối số truyền vào, giới hạn generic (`extends`), tính bất biến của `List<T>`, và API dùng generic lồng nhau như `Comparator.comparing` hoặc `Collectors.toMap`.
- Sửa lỗi bằng cách làm rõ **ý nghĩa kiểu dữ liệu** hoặc điều chỉnh chữ ký generic, thay vì ép kiểu mù quáng.

Phạm vi: **suy luận kiểu ở thời điểm biên dịch trong Java 17+**. Đây là lỗi kiểm tra kiểu tĩnh; không phải lỗi do type erasure lúc chạy chương trình.

## 2. Một thông báo lỗi điển hình

Xét file `Broken.java`:

```java
import java.util.List;

public class Broken {
    static <T> List<T> singleton(T value) {
        return List.of(value);
    }

    public static void main(String[] args) {
        List<String> words = singleton(42); // Không biên dịch
    }
}
```

Chạy:

```bash
javac Broken.java
```

Phần cốt lõi của thông báo từ `javac` có dạng (cách trình bày, tên đầy đủ và số dòng có thể thay đổi theo phiên bản JDK):

```text
incompatible types: inference variable T has incompatible bounds
    equality constraints: java.lang.String
    lower bounds: java.lang.Integer
```

Đừng chỉ đọc dòng “incompatible types”. Hãy đọc ba thành phần:

| Thành phần | Cách hiểu trong ví dụ |
| --- | --- |
| `inference variable T` | `T` trong khai báo `<T> List<T> singleton(T value)`, là ẩn số mà trình biên dịch cần tìm. |
| `equality constraints: String` | Vì kết quả cần gán cho `List<String>`, chữ ký trả về `List<T>` buộc `T` là `String`. |
| `lower bounds: Integer` | Đối số `42` được boxing thành `Integer`; để truyền vào tham số `T`, kiểu của đối số phải tương thích với `T` (nôm na `Integer` là một cận dưới của `T`). |

Hai ràng buộc cùng tồn tại đòi hỏi `T` vừa bằng `String`, vừa chấp nhận giá trị `Integer`. Không có cách chọn `T` thỏa cả hai, nên trình biên dịch dừng.

**“Bounds” ở đây là các ràng buộc của bài toán suy luận kiểu**, không nhất thiết nghĩa là bạn đã viết `T extends ...`. Một phương thức chỉ khai báo `<T>` vẫn có thể báo `incompatible bounds`.

## 3. Java suy luận kiểu từ đâu?

Xem lại chữ ký:

```java
static <T> List<T> singleton(T value)
```

Tại lời gọi `singleton(42)`, trình biên dịch xét đồng thời:

1. **Kiểu của biểu thức đối số**: literal `42` có kiểu `int`; khi phù hợp với tham số kiểu tham chiếu `T`, Java xét boxing thành `Integer`.
2. **Kiểu đích (target type)**: phép gán `List<String> words = ...` yêu cầu một biểu thức tương thích với `List<String>`.
3. **Chữ ký phương thức**: kiểu tham số `T` và kiểu trả về `List<T>` đặt quan hệ giữa đối số, kết quả và kiểu đích.
4. **Giới hạn generic khai báo**, nếu có: ví dụ `<T extends Number>` thêm điều kiện `T` phải là subtype của `Number`.

Đây là một dạng *constraint solving* khi biên dịch. Không phải Java chạy chương trình rồi đoán kiểu; phép suy luận thất bại thì bytecode không được tạo.

### 3.1. Ba nhóm ràng buộc thường gặp

- **Equality constraints** (`T = X`): thường xuất hiện khi cấu trúc tham số hóa và kiểu đích yêu cầu cùng một đối số kiểu, chẳng hạn `List<T>` phải tương thích với `List<String>`. Vì generic Java **bất biến**, `List<Integer>` không phải subtype của `List<Number>`.
- **Lower bounds** (`L <: T`): `T` phải đủ rộng để chấp nhận kiểu `L` của giá trị đưa vào; ví dụ `Integer` phải tương thích với `T`.
- **Upper bounds** (`T <: U`): `T` phải thỏa giới hạn phía trên, chẳng hạn `T extends Number` hoặc giới hạn Comparable của một API.

Ký hiệu `A <: B` đọc là “`A` là subtype của `B`”. Đây là cách đọc trực quan hữu ích khi debug; chi tiết thuật toán suy luận thực tế của Java còn xét chuyển đổi biểu thức, capture conversion và các bước quy giản ràng buộc.

### 3.2. Đừng đọc nhầm tên biến kiểu thành lớp thật

Trong thông báo:

```text
inference variable U has incompatible bounds
```

`U` thường chỉ là tham số kiểu thứ hai của một phương thức thư viện, **không phải tên lớp `U`**. Ví dụ `Comparator.comparing` khai báo hai tham số kiểu `T` (đối tượng cần so sánh) và `U` (kiểu khóa so sánh). Muốn biết `U` là gì, hãy tìm khai báo generic của phương thức ở vị trí lỗi, không chỉ nhìn biến cục bộ nơi mũi tên `^` trỏ tới.

## 4. Tình huống 1: Kiểu đích xung đột với kiểu đối số

Đoạn sai:

```java
List<String> words = singleton(42);
```

Có ít nhất ba cách sửa, mỗi cách mang ý nghĩa khác nhau:

```java
List<Integer> numbers = singleton(42);             // Muốn danh sách số
List<String> words = singleton(String.valueOf(42)); // Muốn danh sách chuỗi
List<Number> values = singleton(42);                // Muốn kiểu số tổng quát
```

- Sửa **kiểu đích** nếu giá trị thực sự là số.
- **Chuyển đổi dữ liệu** có chủ đích nếu nghiệp vụ cần chuỗi.
- Chọn kiểu rộng hơn (`Number`) nếu API cần chấp nhận nhiều loại số. Đừng đổi thành `Object` chỉ để tắt lỗi khi về sau vẫn cần thao tác đặc thù của `String`.

Một cách tưởng như hợp lý nhưng vẫn sai:

```java
List<String> words = Broken.<String>singleton(42); // Vẫn lỗi
```

Việc ghi rõ `<String>` chỉ yêu cầu `T = String` sớm hơn; nó không biến `Integer` thành `String`.

### 4.1. Vai trò của `var`

```java
var result = singleton(42); // Suy luận result là List<Integer>
```

Ở đây không có đích `List<String>` áp đặt lên lời gọi, nên Java có thể suy luận `T` từ đối số. Tuy nhiên, đổi mọi khai báo thành `var` không phải giải pháp chung: `var` có thể khiến kiểu suy luận được khác với hợp đồng API mà bạn mong muốn. Hãy kiểm tra kiểu được suy luận trước khi quyết định.

## 5. Tình huống 2: Ràng buộc `extends` xung đột với kiểu đích

Một phương thức chỉ nhận kiểu số:

```java
static <T extends Number> T keepNumber(T value) {
    return value;
}
```

Lời gọi sau sai:

```java
String text = keepNumber(10); // Không biên dịch
```

Ta có đồng thời:

- `T` phải thỏa `T extends Number` → `T` không thể là `String`.
- Biểu thức được gán vào `String` → kiểu đích muốn một kết quả là `String`.
- Đối số số nguyên dẫn đến ràng buộc từ `Integer`.

Hãy sửa theo mục đích:

```java
Number value = keepNumber(10);               // Giữ số
String text = keepNumber(10).toString();     // Chuyển số sang chuỗi
```

Thông báo lỗi có thể hiển thị `upper bounds: Number` (hoặc một biểu diễn phức tạp hơn khi có nhiều giới hạn) cùng ràng buộc từ kiểu đích. Lưu ý rằng không phải mọi dòng `upper bounds` đều đến từ `extends` viết ngay trong phương thức của bạn; chúng cũng có thể đến từ chữ ký của API được gọi.

## 6. Tình huống 3: API yêu cầu khóa `Comparable` nhưng khóa không hỗ trợ so sánh

Chữ ký khái quát của overload một đối số:

```java
static <T, U extends Comparable<? super U>>
Comparator<T> comparing(Function<? super T, ? extends U> keyExtractor)
```

Đoạn dưới không hợp lệ:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

record Packet(String id, byte[] payload) {}

List<Packet> packets = new ArrayList<>();
packets.sort(Comparator.comparing(Packet::payload)); // Không biên dịch
```

`Packet::payload` trả về `byte[]`. Trong `Comparator.comparing`, `U` phải là kiểu có thể so sánh bằng `Comparable<? super U>`; mảng `byte[]` **không triển khai `Comparable`**. Vì vậy trình biên dịch có thể báo:

```text
inference variable U has incompatible bounds
    upper bounds: Comparable<? super U>
    lower bounds: byte[]
```

Cách sửa phụ thuộc **quy tắc xếp thứ tự** mong muốn.

Nếu sắp theo độ dài payload:

```java
packets.sort(Comparator.comparingInt(p -> p.payload().length));
```

`comparingInt` nhận khóa `int`, không đòi mảng byte phải tự `Comparable`. Nếu nghiệp vụ thực sự muốn so sánh nội dung byte, hãy cung cấp một `Comparator<byte[]>` có ngữ nghĩa rõ ràng qua overload hai tham số `Comparator.comparing(keyExtractor, keyComparator)`.

**Không nên** sửa bằng cách ép `(Comparable) packet.payload()` vì mảng không bỗng trở thành `Comparable`; một cast như vậy chỉ đẩy vấn đề sang lỗi runtime.

## 7. Tình huống 4: Generic lồng nhau trong Stream/Collector

Ví dụ:

```java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<String, Long> lengths = Stream.of("a", "abc")
        .collect(Collectors.toMap(Function.identity(), String::length)); // Sai
```

`String::length` trả về `int`, được boxing thành `Integer` nếu cần kiểu tham chiếu. Nhưng kiểu đích lại yêu cầu **giá trị trong `Map` là `Long`**. `Integer` và `Long` là hai lớp khác nhau; Java không tự thực hiện chuỗi chuyển đổi `int -> long -> Long` trong mọi ngữ cảnh suy luận kiểu generic này.

Để debug, tách hợp đồng:

```text
Đích:              Map<String, Long>
toMap(keyMapper, valueMapper):
                   Map<K, U>
keyMapper:         String -> String  => K phù hợp String
valueMapper:       String -> int     => U nhận Integer (qua boxing)
Đích đòi hỏi:      U = Long
Mâu thuẫn:         Integer không tương thích với Long
```

Hai cách sửa đúng:

```java
Map<String, Integer> lengthsAsInt = Stream.of("a", "abc")
        .collect(Collectors.toMap(Function.identity(), String::length));

Map<String, Long> lengthsAsLong = Stream.of("a", "abc")
        .collect(Collectors.toMap(Function.identity(), s -> (long) s.length()));
```

Ở cách thứ hai, `(long) s.length()` tạo giá trị `long`, sau đó boxing thành `Long`. Việc đổi kiểu ở **biểu thức sinh giá trị** làm hợp đồng rõ ràng hơn việc ép kiểu sau khi thu thập.

Khi lỗi xuất hiện ngay tại `.collect(...)`, `.map(...)` hoặc `Comparator.comparing(...)`, hãy truy ngược lambda/method reference bên trong. Mũi tên báo lỗi có thể nằm ở lời gọi ngoài cùng, trong khi mâu thuẫn nằm ở kiểu mà callback trả về.

## 8. Tình huống 5: Tính bất biến và wildcard `extends`/`super`

Giả sử có phương thức:

```java
static <T> void copy(List<T> target, List<T> source) {
    target.addAll(source);
}
```

Lời gọi này sai:

```java
List<Number> target = new ArrayList<>();
List<Integer> source = List.of(1, 2);
copy(target, source); // Không suy luận được cùng một T
```

Dù `Integer extends Number`, Java **không** coi `List<Integer>` là `List<Number>`. Khi cả hai tham số có dạng `List<T>`, phương thức buộc hai đối số phải tương thích với **cùng một** `T`. Bạn có thể thấy thông báo về `incompatible bounds`, `incompatible equality constraints`, hoặc “cannot infer type-variable(s)” tùy ngữ cảnh và phiên bản compiler.

Nếu ý định thật là *đọc phần tử từ nguồn và thêm vào đích*, ký hiệu wildcard làm hợp đồng chính xác hơn:

```java
static <T> void copy(
        List<? super T> target,
        List<? extends T> source) {
    for (T item : source) {
        target.add(item);
    }
}
```

Khi gọi với `List<Number>` và `List<Integer>`, có thể lấy `T = Integer`:

- `source` kiểu `List<? extends Integer>`: đọc được các phần tử như `Integer`.
- `target` kiểu `List<? super Integer>`: có thể thêm phần tử `Integer` vào `List<Number>`.

Đây là quy tắc **PECS**: *Producer Extends, Consumer Super*. Không thay `List<T>` bằng wildcard một cách máy móc. Chỉ dùng wildcard khi nó diễn tả đúng hướng dữ liệu và quyền đọc/ghi mà API dự định hỗ trợ.

## 9. Quy trình gỡ lỗi có hệ thống

Khi nhận thông báo, đi từ vị trí lỗi đến các ràng buộc:

1. **Giữ nguyên ví dụ lỗi** và chạy `javac -Xdiags:verbose Broken.java` khi cần thêm thông tin về phương thức/overload. Dùng JDK và tùy chọn biên dịch nhất quán với dự án.
2. **Xác định phương thức generic** xuất hiện trong biểu thức đang lỗi. Tìm khai báo `<T>`, `<T,U>`, kiểu tham số, kiểu trả về và các giới hạn `extends`. Với API thư viện, kiểm tra chữ ký trong Javadoc hoặc mã nguồn tương ứng JDK đang dùng.
3. **Khoanh đúng biến inference** mà compiler nêu, chẳng hạn `U` trong `Comparator.comparing` là kiểu khóa; không nhầm với `T` là kiểu phần tử.
4. **Ghi lại kiểu đích** ở phép gán, tham số phương thức bao ngoài hoặc kiểu trả về của lambda. Một biểu thức generic có thể chịu ràng buộc từ ngữ cảnh bên ngoài.
5. **Ghi lại kiểu thực** của từng đối số và lambda/method reference: primitive, boxing, kiểu mảng, kiểu generic, wildcard, `null`, overload có thể ảnh hưởng đến lựa chọn.
6. **Đặt ba nhóm ràng buộc cạnh nhau**: equality, lower, upper. Tìm cặp không cùng thỏa mãn: `String`/`Integer`, `Long`/`Integer`, hoặc `byte[]`/`Comparable`.
7. **Chọn sửa đổi đúng ý nghĩa dữ liệu**: thay kiểu đích, chuyển đổi kiểu tại nguồn, chọn overload có `Comparator`, điều chỉnh generic/wildcard, hoặc sửa API nếu thiết kế sai. Sau đó biên dịch lại và kiểm tra hành vi.

Bảng thao tác nhanh:

| Triệu chứng | Nơi cần kiểm tra đầu tiên | Hướng sửa thông thường |
| --- | --- | --- |
| `equality constraints: String`, `lower bounds: Integer` | Kiểu đích và đối số của phương thức generic | Giữ cùng kiểu hoặc chuyển đổi dữ liệu. |
| `upper bounds: Comparable...`, `lower bounds: byte[]` | Kiểu khóa được trả về từ key extractor | Đổi khóa thành kiểu có thứ tự hoặc truyền `Comparator` rõ ràng. |
| `U` suy luận là `Integer` nhưng đích yêu cầu `Long` | Hàm biến đổi giá trị của Stream/Collector | Tạo `long`/`Long` một cách chủ đích ở mapper. |
| Hai `List` mang kiểu phần tử khác nhau | Chữ ký dùng `List<T>` ở nhiều vị trí | Xác định có cần `? extends T`/`? super T` không. |
| Lỗi nằm tại lambda hay lời gọi phương thức ngoài | Kiểu tham số và giá trị trả về trong lambda | Thêm kiểu cục bộ hoặc tách biểu thức để cô lập xung đột. |

### 9.1. Kỹ thuật tách biểu thức phức tạp

Khi đoạn mã dài, khai báo kiểu cụ thể ở bước trung gian để làm rõ nơi ràng buộc xuất hiện:

```java
Function<String, Long> lengthMapper = s -> (long) s.length();

Map<String, Long> lengths = Stream.of("a", "abc")
        .collect(Collectors.toMap(Function.identity(), lengthMapper));
```

Nếu dòng khai báo `Function<String, Long>` không biên dịch, vấn đề nằm ở lambda. Nếu khai báo đó chạy được mà `.collect` lỗi, tiếp tục kiểm tra chữ ký `collect`, `toMap`, kiểu phần tử của stream và kiểu đích.

Có thể thử **type witness** để xác minh giả thuyết:

```java
List<Integer> numbers = Broken.<Integer>singleton(42);
```

Type witness chỉ chỉ rõ kiểu cần suy luận; nó **không chữa mâu thuẫn về ngữ nghĩa**. Nếu chọn `<String>` nhưng truyền `42`, lỗi vẫn đúng.

## 10. Ví dụ Java 17+ hoàn chỉnh, có thể chạy

Ví dụ sau thể hiện các sửa đổi có chủ đích cho từng tình huống: chọn đúng kiểu đích, `copy` với PECS, so sánh qua khóa `int`, chuyển `int` thành `long` khi tạo `Map`.

Tạo file `InferenceBoundsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class InferenceBoundsDemo {
    record Packet(String id, byte[] payload) {}

    static <T> List<T> singleton(T value) {
        return List.of(value);
    }

    static <T> void copy(List<? super T> target, List<? extends T> source) {
        for (T item : source) {
            target.add(item);
        }
    }

    public static void main(String[] args) {
        List<String> names = singleton("Java");
        List<Integer> ids = singleton(42);

        List<Number> numbers = new ArrayList<>();
        copy(numbers, List.of(1, 2));

        List<Packet> packets = new ArrayList<>(List.of(
                new Packet("long", new byte[] {1, 2, 3}),
                new Packet("short", new byte[] {7})
        ));
        packets.sort(Comparator.comparingInt(p -> p.payload().length));

        Map<String, Long> lengths = Stream.of("a", "abc")
                .collect(Collectors.toMap(Function.identity(), s -> (long) s.length()));

        System.out.println(names);
        System.out.println(ids);
        System.out.println(numbers);
        System.out.println(packets.stream().map(Packet::id).toList());
        System.out.println(lengths.get("abc"));
    }
}
```

Biên dịch/chạy từ thư mục chứa file:

```bash
javac InferenceBoundsDemo.java
java InferenceBoundsDemo
```

Kết quả chuẩn:

```text
[Java]
[42]
[1, 2]
[short, long]
3
```

Giải thích: `names` và `ids` có kiểu phần tử đúng với đầu vào; `copy` cho phép đưa `Integer` vào `List<Number>`; `packets` sắp theo số phần tử của payload nên `short` đứng trước `long`; giá trị của khóa `"abc"` là `Long` biểu diễn độ dài 3.

## 11. Những cách “sửa” dễ gây lỗi khác

- **Ép kiểu thô** như `(List<String>) (List<?>) someList` có thể giấu sai lệch dữ liệu, sinh cảnh báo unchecked và gây `ClassCastException` khi dùng phần tử. Nó không chứng minh các ràng buộc generic đã được giải quyết đúng.
- **Dùng raw type** (`List` thay vì `List<String>`) làm mất kiểm tra kiểu ở thời điểm biên dịch. Chỉ dùng khi tương tác với API legacy có xử lý cảnh báo rõ ràng, không phải cách chữa lỗi suy luận thông thường.
- **Thêm `<Object>` khắp nơi** có thể làm mã biên dịch nhưng làm mất thông tin kiểu, buộc cast khi đọc và che giấu thiết kế API chưa hợp lý.
- **Suy luận rằng `List.of(1, "a")` luôn lỗi** là sai: Java có thể suy ra một kiểu cha chung cho các đối số khác nhau khi ngữ cảnh cho phép. Vấn đề là kiểu được suy ra có đáp ứng hợp đồng cụ thể (như `List<String>`) hay không.
- **Cho rằng boxing đồng nghĩa mọi chuyển đổi số đều hợp lệ** là sai: `Integer` không phải subtype của `Long`, và suy luận kiểu generic không tự động chuyển một đối tượng `Integer` thành đối tượng `Long`.
- **Chỉ sửa tại dòng compiler gạch chân** có thể bỏ lỡ nguyên nhân ở lambda, method reference hoặc kiểu trả về của phương thức được gọi ở sâu bên trong.

## 12. Tự kiểm tra hiểu bài

**Bài 1.** Với chữ ký `static <T> List<T> singleton(T value)`, vì sao `List<String> names = singleton(7)` lỗi, còn `List<Integer> ids = singleton(7)` hợp lệ?

<details>
<summary>Gợi ý đáp án</summary>

Kiểu đích đầu tiên đặt `T = String`, trong khi đối số cung cấp `Integer`. Kiểu đích thứ hai đặt `T = Integer`, phù hợp đối số đã boxing. Cách sửa phụ thuộc ý định: `singleton("7")` nếu muốn chuỗi, hoặc `List<Integer>` nếu muốn số.

</details>

**Bài 2.** Vì sao `Comparator.comparing(Packet::payload)` không thể sử dụng trực tiếp khi `payload()` trả `byte[]`? Nếu chỉ cần sắp theo số byte, thay bằng gì?

<details>
<summary>Gợi ý đáp án</summary>

`comparing` cần khóa `U` triển khai `Comparable<? super U>`; `byte[]` không triển khai giao diện đó. Dùng `Comparator.comparingInt(p -> p.payload().length)` để sắp theo độ dài.

</details>

**Bài 3.** `List<Number> target` và `List<Integer> source` nên đi cùng tham số phương thức nào khi chỉ sao chép phần tử từ `source` sang `target`?

<details>
<summary>Gợi ý đáp án</summary>

Có thể khai báo `<T> void copy(List<? super T> target, List<? extends T> source)` và thêm từng phần tử đọc từ nguồn vào đích. Với trường hợp này suy luận `T = Integer` là phù hợp. Cần hiểu rõ vai trò producer/consumer trước khi áp dụng wildcard.

</details>

## 13. Ghi nhớ khi gặp lỗi ở dự án thực tế

Một biến suy luận kiểu không thể có giá trị nếu đồng thời bị buộc bằng một kiểu, phải chấp nhận một kiểu đối số không tương thích và/hoặc phải thỏa một giới hạn trên không khả thi. Hãy đọc **tên biến kiểu → nơi khai báo → equality/lower/upper bounds → kiểu đích và đối số → ý nghĩa dữ liệu**, rồi sửa tại ràng buộc thực sự sai.

Thông báo `inference variable ... has incompatible bounds` là **manh mối giải bài toán kiểu** của compiler. Khi chuyển từng manh mối thành quan hệ giữa các kiểu cụ thể, lỗi tưởng khó đọc thường trở thành một sai lệch thiết kế hoặc chuyển đổi dữ liệu rất rõ ràng.