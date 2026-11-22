# `Stream.toArray()` với mảng có kiểu cụ thể trong Java

## 1. Mục tiêu và bài toán

Trong Java, một `Stream<T>` mô tả luồng xử lý các phần tử. Sau các bước như `filter`, `map`, `distinct` hoặc `sorted`, đôi khi chương trình cần **thu thập kết quả vào một mảng** để truyền cho API nhận `T[]`, thao tác với thư viện cũ hoặc lưu dưới định dạng mảng. Thao tác kết thúc (*terminal operation*) `toArray` thực hiện công việc đó.

Điểm dễ nhầm là có **hai overload** của `Stream.toArray` với ý nghĩa về kiểu mảng khác nhau:

```java
Object[] toArray();

<A> A[] toArray(java.util.function.IntFunction<A[]> generator);
```

- **`stream.toArray()`** trả về `Object[]`, kể cả khi các phần tử đều là `String`. Đây là kiểu mảng của overload không tham số, không tự biến thành `String[]`.
- **`stream.toArray(String[]::new)`** trả về `String[]` có kiểu thành phần lúc chạy là `String`, khi nguồn và kiểu đích tương thích.
- **`stream.toArray(Integer[]::new)`** trả về `Integer[]`; nếu muốn mảng nguyên thủy `int[]`, có thể dùng `IntStream.toArray()`.

Bài này tập trung vào **việc chọn đúng overload, kiểu mảng lúc biên dịch và lúc chạy, constructor reference `Type[]::new`, các giới hạn của mảng kiểu cụ thể**, cũng như khả năng giữ thứ tự, xử lý `null`, sai kiểu và khả năng kiểm thử.

## 2. Vì sao `toArray()` không tham số chỉ cho `Object[]`?

Xem đoạn mã:

```java
import java.util.stream.Stream;

Object[] objects = Stream.of("a", "b", "c").toArray();
```

Mặc dù Stream có kiểu phần tử `String`, phương thức `toArray()` không tham số được khai báo trả về `Object[]`. Vì thế:

```java
// Không biên dịch: Object[] không gán trực tiếp cho String[].
// String[] names = Stream.of("a", "b").toArray();
```

Cũng **không thể ép kiểu một cách an toàn**:

```java
// Biên dịch, nhưng khi chạy ném ClassCastException.
String[] names = (String[]) Stream.of("a", "b").toArray();
```

Nguyên nhân không nằm ở việc các phần tử có phải `String` hay không, mà ở **kiểu runtime của đối tượng mảng**. Đối tượng mà overload không tham số trả về thực sự là `Object[]`, chứ không phải `String[]`. Java kiểm tra phép ép kiểu của *cả mảng*, không chỉ kiểm tra từng phần tử.

Có thể kiểm chứng:

```java
Object[] values = Stream.of("a", "b").toArray();

System.out.println(values.getClass().getComponentType().getName());
// java.lang.Object
```

Nếu đích chỉ yêu cầu `Object[]`, overload không tham số hoàn toàn phù hợp. Nhưng nếu API cần `String[]`, hãy cung cấp cách tạo **mảng đúng kiểu** ngay từ đầu thay vì ép kiểu sau đó.

## 3. Giải pháp: `toArray(String[]::new)`

Cú pháp thông dụng nhất:

```java
import java.util.Arrays;
import java.util.stream.Stream;

String[] names = Stream.of("Lan", "Minh", "An")
        .filter(name -> name.length() > 2)
        .toArray(String[]::new);

System.out.println(Arrays.toString(names));
// [Lan, Minh]
```

`String[]::new` là **tham chiếu constructor của mảng** (array constructor reference). Nó không tạo trước một mảng cố định tại nơi khai báo; nó biểu thị một hàm nhận độ dài và tạo mảng có độ dài ấy.

Có thể hiểu tương đương với lambda:

```java
String[] result = Stream.of("a", "b")
        .toArray(size -> new String[size]);
```

Hai cách đều cung cấp một `IntFunction<String[]>`. Dùng constructor reference ngắn hơn và trực tiếp thể hiện loại mảng cần tạo.

### Chữ ký tổng quát và suy luận kiểu

Overload có generator có dạng:

```java
<A> A[] toArray(java.util.function.IntFunction<A[]> generator)
```

`IntFunction<R>` có phương thức `R apply(int size)`. Đối với `String[]::new`:

```java
java.util.function.IntFunction<String[]> maker = String[]::new;
String[] three = maker.apply(3); // Mảng String[] dài 3 phần tử.
```

Khi gọi `stream.toArray(String[]::new)`, Stream sử dụng factory để tạo mảng lưu kết quả. Nhà triển khai Stream có thể gọi generator để tạo mảng kết quả và/hoặc các mảng cần thiết cho việc chia phần xử lý hoặc đổi kích thước; **không nên gắn tác dụng phụ hay kỳ vọng generator chỉ được gọi một lần**.

Điều quan trọng là factory trả về một mảng đúng **kiểu thành phần**, có khả năng chứa các phần tử kết quả. Với cú pháp `String[]::new`, Java suy luận `A = String`. Do đó biến đích có thể khai báo `String[]` mà không cast.

## 4. `toArray` là thao tác kết thúc và có kiểu kết quả rõ ràng

Xét pipeline:

```java
String[] tags = java.util.stream.Stream.of(
                " java ", " stream ", " java ")
        .map(String::strip)
        .map(String::toUpperCase)
        .distinct()
        .sorted()
        .toArray(String[]::new);
```

Kết quả là `["JAVA", "STREAM"]`, giữ thứ tự mà pipeline đã xác định sau `sorted()`.

Các đặc điểm cần nhớ:

1. `filter`, `map`, `distinct`, `sorted` là thao tác trung gian; chúng tạo pipeline, không trả về `String[]`.
2. `toArray(String[]::new)` **kết thúc** pipeline và thu thập phần tử vào mảng mới.
3. `String[]` là cấu trúc lưu trữ kết quả; Stream trước đó không phải mảng.
4. Sau khi gọi terminal operation, **không được tiêu thụ lại cùng Stream instance**.
5. `toArray` không thay đổi `List` hay mảng được dùng làm nguồn, trừ khi chính lambda chứa tác dụng phụ ngoài ý muốn.

Một ví dụ sai về vòng đời:

```java
java.util.stream.Stream<String> stream =
        java.util.stream.Stream.of("a", "b");

String[] array = stream.toArray(String[]::new);

// Không hợp lệ: Stream đã được tiêu thụ.
// long count = stream.count();
```

Nếu muốn xử lý lại dữ liệu, tạo Stream mới từ nguồn có thể duyệt lại.

## 5. Khi kiểu phần tử và kiểu mảng không trùng khít

### Mảng với kiểu cha hợp lệ

Không nhất thiết phải dùng mảng đúng kiểu tham số `T` của `Stream<T>`. Một Stream của `Integer` có thể thu thập vào `Number[]`:

```java
Number[] numbers = java.util.stream.Stream.<Integer>of(1, 2, 3)
        .toArray(Number[]::new);
```

Các `Integer` đều là `Number` nên có thể được lưu trong mảng `Number[]`. Điều kiện thực sự là **mọi phần tử phải gán được vào kiểu thành phần của mảng**.

### Trường hợp sai kiểu sẽ thất bại khi chạy

Vì chữ ký generic `<A> A[]` không ràng buộc `A` phải là một siêu kiểu của `T` ở cấp khai báo, có thể viết lời gọi mà compiler cho qua nhưng mảng sinh ra không chứa được tất cả phần tử:

```java
// Có thể biên dịch, nhưng phần tử Integer 42
// không thể lưu vào String[].
String[] wrong = java.util.stream.Stream.<Object>of("ok", 42)
        .toArray(String[]::new);
```

Khi cố lưu `Integer` vào `String[]`, Java ném `ArrayStoreException`. Việc đặt `String[]::new` **không biến đối tượng không phải chuỗi thành chuỗi**; nó chỉ chỉ định mảng đích.

Cách đúng là chuyển đổi phần tử:

```java
String[] converted = java.util.stream.Stream.<Object>of("ok", 42)
        .map(String::valueOf)
        .toArray(String[]::new);

// ["ok", "42"]
```

Nếu yêu cầu là giữ các giá trị hỗn hợp, hãy dùng `Object[]` hoặc một kiểu chung phù hợp thay vì chọn `String[]` chỉ để thỏa chữ ký.

### Mảng là *covariant*, nhưng có kiểm tra runtime

`String[]` có thể gán cho `Object[]`:

```java
Object[] aliases = java.util.stream.Stream.of("a", "b")
        .toArray(String[]::new);

System.out.println(aliases instanceof String[]); // true
```

Tuy nhiên, đối tượng thật vẫn là `String[]`. Nếu cố `aliases[0] = 123`, Java sẽ ném `ArrayStoreException`.

Quy tắc này khác generic bất biến như `List<String>` không thể gán thành `List<Object>`. Vì mảng có thông tin kiểu thành phần lúc chạy, runtime phải kiểm soát phép gán. Khi dùng `toArray(Type[]::new)`, cần hiểu cả **kiểu của biến tham chiếu** lẫn **kiểu runtime của đối tượng mảng**.

## 6. Phân biệt mảng đối tượng với mảng nguyên thủy

Đây là một bẫy thường gặp:

```java
Integer[] boxed = java.util.stream.IntStream.rangeClosed(1, 3)
        .boxed()
        .toArray(Integer[]::new);
// boxed = [1, 2, 3]
```

`boxed()` chuyển `IntStream` thành `Stream<Integer>`, sau đó tạo `Integer[]` gồm **wrapper objects**.

Nếu cần `int[]` nguyên thủy, dùng trực tiếp terminal operation của `IntStream`:

```java
int[] primitive = java.util.stream.IntStream.rangeClosed(1, 3)
        .toArray();
// primitive = [1, 2, 3]
```

`IntStream.toArray()` trả `int[]`; `LongStream.toArray()` trả `long[]`; `DoubleStream.toArray()` trả `double[]`. Chúng không dùng overload `toArray(String[]::new)` của `Stream<T>`.

| Dòng nguồn | Lời gọi | Kiểu kết quả |
| --- | --- | --- |
| `Stream<String>` | `.toArray()` | `Object[]` |
| `Stream<String>` | `.toArray(String[]::new)` | `String[]` |
| `Stream<Integer>` | `.toArray(Integer[]::new)` | `Integer[]` |
| `IntStream` | `.toArray()` | `int[]` |
| `IntStream` | `.boxed().toArray(Integer[]::new)` | `Integer[]` |
| `LongStream` | `.toArray()` | `long[]` |
| `DoubleStream` | `.toArray()` | `double[]` |

Không có cách cast trực tiếp `Integer[]` thành `int[]`: đây là hai loại mảng khác nhau. Nếu muốn chuyển đổi, sử dụng `mapToInt(Integer::intValue).toArray()` với `Stream<Integer>` khi phần tử chắc chắn không null.

## 7. Ví dụ Java 17+ hoàn chỉnh và kiểm thử

Lưu chương trình vào file `TypedToArrayDemo.java`. Chương trình chỉ dùng Java Standard Library và tự kiểm tra các tình huống quan trọng.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class TypedToArrayDemo {
    private static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError("Failed: " + label);
        }
    }

    public static void main(String[] args) {
        // Không có generator: runtime component type là Object.
        Object[] untyped = Stream.of("alpha", "beta").toArray();
        check(untyped.getClass().getComponentType() == Object.class,
                "untyped array component");

        // Có generator: tạo đúng String[].
        String[] typed = Stream.of("alpha", "beta")
                .map(String::toUpperCase)
                .toArray(String[]::new);
        check(Arrays.equals(
                new String[]{"ALPHA", "BETA"}, typed), "typed values");

        // Kết hợp filter và thu thập đúng kiểu.
        List<String> people = List.of("Lan", "Minh", "An");
        String[] selected = people.stream()
                .filter(s -> s.length() > 2)
                .toArray(String[]::new);
        check(Arrays.equals(
                new String[]{"Lan", "Minh"}, selected), "filter results");
        check(3, people.size(), "source remains unchanged");

        // Lambda factory tương đương constructor reference.
        String[] lambdaArray = Stream.of("x", "y")
                .toArray(size -> new String[size]);
        check(Arrays.equals(
                new String[]{"x", "y"}, lambdaArray), "lambda factory");

        // Các phần tử Integer lưu được vào Number[].
        Number[] numbers = Stream.<Integer>of(1, 2, 3)
                .toArray(Number[]::new);
        check(numbers.getClass().getComponentType() == Number.class,
                "Number array component");
        check(Arrays.equals(new Number[]{1, 2, 3}, numbers),
                "Number array contents");

        // IntStream tạo int[], không phải Integer[].
        int[] primitive = Stream.of("2", "4", "6")
                .mapToInt(Integer::parseInt)
                .toArray();
        check(Arrays.equals(new int[]{2, 4, 6}, primitive),
                "primitive int array");

        Integer[] boxed = IntStream.rangeClosed(1, 3)
                .boxed()
                .toArray(Integer[]::new);
        check(Arrays.equals(new Integer[]{1, 2, 3}, boxed),
                "wrapper Integer array");

        // Stream rỗng tạo mảng rỗng đúng kiểu.
        String[] empty = Stream.<String>empty()
                .toArray(String[]::new);
        check(empty.length == 0, "empty typed array");
        check(empty.getClass().getComponentType() == String.class,
                "empty component type");

        // Mảng tham chiếu có thể chứa null.
        String[] withNull = Stream.of("left", (String) null, "right")
                .toArray(String[]::new);
        check(Arrays.equals(
                new String[]{"left", null, "right"}, withNull),
                "null element");

        // Cố cast Object[] thành String[] phải thất bại.
        boolean badCastRejected = false;
        try {
            String[] wrong = (String[]) Stream.of("a", "b").toArray();
        } catch (ClassCastException expected) {
            badCastRejected = true;
        }
        check(badCastRejected, "Object[] cast rejected");

        // Cố đưa Integer vào String[] phải thất bại.
        boolean arrayStoreRejected = false;
        try {
            String[] wrong = Stream.<Object>of("ok", 42)
                    .toArray(String[]::new);
        } catch (ArrayStoreException expected) {
            arrayStoreRejected = true;
        }
        check(arrayStoreRejected, "incompatible element rejected");

        System.out.println("untypedComponent="
                + untyped.getClass().getComponentType().getSimpleName());
        System.out.println("typed=" + Arrays.toString(typed));
        System.out.println("selected=" + Arrays.toString(selected));
        System.out.println("lambda=" + Arrays.toString(lambdaArray));
        System.out.println("numberComponent="
                + numbers.getClass().getComponentType().getSimpleName());
        System.out.println("primitive=" + Arrays.toString(primitive));
        System.out.println("boxed=" + Arrays.toString(boxed));
        System.out.println("emptyLength=" + empty.length);
        System.out.println("withNull=" + Arrays.toString(withNull));
        System.out.println("badCastRejected=" + badCastRejected);
        System.out.println("arrayStoreRejected=" + arrayStoreRejected);
        System.out.println("tests=PASS");
    }

    private static void check(int expected, int actual, String label) {
        check(Objects.equals(expected, actual), label);
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac TypedToArrayDemo.java
java TypedToArrayDemo
```

Stdout kỳ vọng khi các kiểm tra thành công:

```text
untypedComponent=Object
typed=[ALPHA, BETA]
selected=[Lan, Minh]
lambda=[x, y]
numberComponent=Number
primitive=[2, 4, 6]
boxed=[1, 2, 3]
emptyLength=0
withNull=[left, null, right]
badCastRejected=true
arrayStoreRejected=true
tests=PASS
```

Các phương thức `check` ném `AssertionError` khi một điều kiện sai, nên bộ kiểm tra hoạt động mà không cần bật `java -ea`.

### Giải thích các kết quả

- `untypedComponent=Object` cho thấy overload `toArray()` tạo đối tượng mảng có kiểu thành phần `Object`.
- `typed=[ALPHA, BETA]` xác nhận `map` chạy trước `toArray(String[]::new)`, còn kết quả có kiểu mảng `String[]`.
- `selected` gồm `Lan` và `Minh`, không có `An` do điều kiện độ dài. Danh sách `people` vẫn có ba phần tử.
- `numberComponent=Number` cho thấy generator có thể tạo mảng theo kiểu cha thích hợp.
- `primitive` là `int[]`, `boxed` là `Integer[]`; cách in `Arrays.toString` giống nhau nhưng kiểu lưu trữ khác nhau.
- Stream rỗng vẫn tạo **mảng `String[]` dài 0**, không phải `null`.
- `withNull` minh họa rằng `Stream<String>` có thể chứa `null`, và mảng tham chiếu `String[]` cũng chứa được `null`.
- Hai tình huống sai kiểu được **bắt có chủ đích trong test**; thông thường hãy để chúng được sửa từ thiết kế, không viết `catch` để che lỗi dữ liệu.
- Trong trường hợp Stream có thứ tự, pipeline tuần tự như ví dụ duy trì thứ tự phần tử kết quả.

## 8. Về thứ tự phần tử và Stream song song

`toArray` thu thập các phần tử theo **encounter order nếu Stream có encounter order**. Với `List.stream()` hoặc `Stream.of(...)`, thứ tự thường được xác định bởi nguồn. Ví dụ:

```java
String[] values = java.util.stream.Stream.of("c", "a", "b")
        .sorted()
        .toArray(String[]::new);

// ["a", "b", "c"]
```

`parallel()` không mặc nhiên đồng nghĩa thứ tự mảng sẽ bị xáo trộn đối với Stream **có thứ tự**:

```java
Integer[] values = java.util.stream.IntStream.range(0, 5)
        .parallel()
        .boxed()
        .toArray(Integer[]::new);
// [0, 1, 2, 3, 4]
```

Tuy nhiên, với nguồn **unordered** hoặc pipeline đã gọi `.unordered()`, không thể suy ra thứ tự kết quả theo giả định của `List`. Khi cần thứ tự cụ thể, phải thiết kế nguồn, sắp xếp (`sorted`) hoặc xử lý theo chính sách phù hợp.

`toArray(generator)` có thể dùng thêm mảng tạm trong triển khai song song; đừng giả định số lần gọi `generator`, kích thước mọi mảng tạm hoặc thứ tự gọi giống nhau giữa các lần chạy. Generator đúng nên **chỉ tạo mảng tương ứng với độ dài được yêu cầu** và không phụ thuộc vào trạng thái bên ngoài.

## 9. Những sai lầm phổ biến

### Sai lầm 1: cast `Object[]` sau `toArray()`

```java
String[] words = (String[]) java.util.stream.Stream.of("a")
        .toArray(); // ClassCastException
```

Sửa bằng:

```java
String[] words = java.util.stream.Stream.of("a")
        .toArray(String[]::new);
```

Việc các phần tử đều là `String` không làm `Object[]` biến thành `String[]`.

### Sai lầm 2: truyền factory có kiểu không chứa được phần tử

```java
// Phần tử Integer không thể đặt vào String[].
String[] bad = java.util.stream.Stream.<Object>of("x", 99)
        .toArray(String[]::new);
```

Không chọn kiểu mảng nhỏ hơn tập kiểu phần tử thực tế. Nếu muốn chuỗi, biến đổi phần tử trước (`map(String::valueOf)`); nếu muốn giữ nhiều kiểu, chọn `Object[]` hoặc mô hình dữ liệu rõ ràng.

### Sai lầm 3: nhầm `Integer[]` với `int[]`

```java
Integer[] objects = java.util.stream.IntStream.of(1, 2)
        .boxed()
        .toArray(Integer[]::new);

int[] primitives = java.util.stream.IntStream.of(1, 2)
        .toArray();
```

Hai mảng khác kiểu, khác cách biểu diễn và hành vi với `null`. `int[]` không chứa được `null`; `Integer[]` có thể chứa `null`.

### Sai lầm 4: cho rằng `toArray(String[]::new)` loại bỏ `null`

Generator không phải phép kiểm tra dữ liệu. Nếu Stream chứa `null`, mảng `String[]` có thể chứa `null` ở đúng vị trí. Nếu nghiệp vụ yêu cầu cấm `null`, hãy kiểm tra rõ ràng trước khi thu thập:

```java
String[] nonNull = java.util.stream.Stream
        .of("a", null, "b")
        .filter(java.util.Objects::nonNull)
        .toArray(String[]::new);
// ["a", "b"]
```

Đây là chính sách **lọc**. Nếu `null` là lỗi cần báo, đừng âm thầm lọc nó: hãy ném lỗi có thông tin vị trí hoặc trả kết quả kiểm tra hợp lệ.

### Sai lầm 5: suy luận mọi Stream phải có kiểu mảng bằng `T[]`

Một `Stream<Integer>` có thể dùng `Number[]::new` để tạo `Number[]`. Hợp đồng generic cho phép chọn kiểu mảng `A[]`; điều kiện runtime là phần tử gán được vào kiểu thành phần. Hãy ưu tiên khai báo đúng đích tiêu thụ, tránh kiểu mảng quá rộng không cần thiết.

### Sai lầm 6: tưởng `toArray()` trả về List

`toArray()` trả mảng; `toList()` trả `List`. Mảng có độ dài cố định sau khi tạo, nhưng có thể thay đổi phần tử ở mỗi vị trí. Danh sách từ `Stream.toList()` (Java 16+) là *unmodifiable*; chúng không thay thế cho nhau. Nếu API cần `List`, dùng `toList()`; nếu cần `T[]`, dùng `toArray(T[]::new)`.

### Sai lầm 7: tái sử dụng Stream sau terminal

`toArray` là terminal operation. Không gọi tiếp `count`, `findFirst` hay `toList` trên chính đối tượng Stream đã tiêu thụ; tạo Stream mới từ nguồn nếu cần.

### Sai lầm 8: in mảng bằng `println(array)`

`System.out.println(myArray)` không phải cách chuẩn để hiển thị nội dung mảng. Với mảng một chiều, dùng `Arrays.toString(array)`. Với mảng lồng nhau, dùng `Arrays.deepToString(array)` khi phù hợp.

### Sai lầm 9: tạo generic array không có kiểu thành phần cụ thể

Do cơ chế xóa kiểu (*type erasure*), không thể nói chung `new T[size]` cho mọi tham số kiểu `T`. Dùng array constructor reference của kiểu cụ thể hoặc nhận `IntFunction<A[]>` do caller cung cấp:

```java
static <T> T[] gather(
        java.util.stream.Stream<T> source,
        java.util.function.IntFunction<T[]> factory) {
    return source.toArray(factory);
}

// Có thể gọi gather(Stream.of("a", "b"), String[]::new).
```

Đây là **phương thức minh họa**, cần đặt trong một class Java với import tương ứng. Việc truyền generator chuyển trách nhiệm lựa chọn mảng runtime hợp lệ cho caller.

## 10. Khi nào nên dùng `toArray()` so với `toArray(Type[]::new)`?

| Nhu cầu | Cách chọn | Lý do |
| --- | --- | --- |
| API nhận `Object[]` | `stream.toArray()` | Ngắn gọn, đúng kiểu trả về |
| API nhận `String[]` | `stream.toArray(String[]::new)` | Tránh cast sai; mảng đúng kiểu runtime |
| API nhận `Number[]` | `stream.toArray(Number[]::new)` khi tương thích | Mảng kiểu cha có thể nhận các phần tử hợp lệ |
| Dữ liệu nguyên thủy `int` | `intStream.toArray()` | Trả `int[]`, không cần boxing |
| API nhận `Integer[]` | `intStream.boxed().toArray(Integer[]::new)` | Chuyển sang wrapper rồi tạo mảng đối tượng |
| Chỉ cần danh sách kết quả | `stream.toList()` | Không cần tạo mảng |
| Cần quy tắc kiểm tra phần tử | `filter`, `map` hoặc kiểm tra rõ lỗi trước `toArray` | Generator không thay thế validation |
| Muốn tái dùng cách tạo mảng | `IntFunction<T[]>` hoặc `Type[]::new` | Tách quyết định kiểu mảng khỏi xử lý phần tử |

Với collection đã tồn tại, còn có `Collection.toArray(T[] array)` và `Collection.toArray(IntFunction<T[]>)` (Java 11+). Đừng nhầm chúng với `Stream.toArray`: overload nhận **mảng cụ thể** `T[] array` thuộc `Collection`, còn `Stream.toArray` nhận **hàm sinh mảng**. Ví dụ `list.toArray(new String[0])` là API của collection, không phải chữ ký của Stream.

## 11. Các bài tập tự luyện

1. Cho `Stream.of("java", "stream", "array")`. Tạo `String[]` chỉ chứa các từ dài ít nhất 5 ký tự, chuyển thành chữ hoa trước khi thu thập. In bằng `Arrays.toString`.
2. Giải thích vì sao `(String[]) Stream.of("x").toArray()` ném `ClassCastException` và cách sửa chính xác bằng constructor reference.
3. Từ `IntStream.rangeClosed(1, 4)`, tạo hai mảng: `int[]` và `Integer[]`. Viết test `Arrays.equals` tương ứng, nêu sự khác nhau về boxing.
4. Với `Stream.<Object>of("one", 2, 3.5)`, thử `toArray(String[]::new)` và giải thích ngoại lệ. Sửa bằng `map(String::valueOf)` trước khi tạo mảng.
5. Tạo `Number[]` từ `Stream.of(10, 20, 30)` bằng `Number[]::new`. Dùng `getClass().getComponentType()` xác nhận kiểu runtime.
6. Tạo `String[]` từ Stream rỗng và Stream chứa `null`; xác định độ dài, nội dung và sự khác nhau giữa “không có phần tử” với “một phần tử null”.
7. Viết phương thức generic `static <T> T[] collect(Stream<T> stream, IntFunction<T[]> factory)` và dùng `String[]::new`, `Integer[]::new` để kiểm tra.
8. Xét Stream có thứ tự được đưa qua `.parallel()`: sử dụng `IntStream.range(0, 100)` và thu thập thành `Integer[]` để kiểm tra thứ tự. Sau đó nghiên cứu vì sao không thể giả định cùng thứ tự với mọi nguồn unordered.

**Tự kiểm tra trọng tâm:** Khi viết `toArray`, hãy hỏi *kết quả cần kiểu mảng gì*, *phần tử thực tế có tương thích kiểu ấy không*, *có cần mảng nguyên thủy không*, *đâu là terminal operation* và *có cần giữ encounter order không*. Năm câu hỏi này giúp tránh phần lớn lỗi về `Object[]`, kiểu mảng runtime và tái sử dụng Stream.

## 12. Kết luận

`Stream.toArray()` là thao tác kết thúc thu thập phần tử vào **`Object[]`**. Khi cần mảng có kiểu cụ thể, hãy dùng **`Stream.toArray(Type[]::new)`**, ví dụ `toArray(String[]::new)` hoặc `toArray(Integer[]::new)`. Factory quy định kiểu mảng lúc chạy; nó **không ép kiểu hay chuyển đổi giá trị phần tử**. Với dữ liệu nguyên thủy, ưu tiên `IntStream`/`LongStream`/`DoubleStream` và overload `toArray()` của chính primitive Stream.

Chọn đúng kiểu mảng, hiểu sự khác nhau giữa Object array và primitive array, kiểm tra tương thích phần tử và coi `toArray` là terminal operation dùng một lần sẽ giúp chương trình an toàn kiểu, dễ đọc và dễ kiểm thử.
