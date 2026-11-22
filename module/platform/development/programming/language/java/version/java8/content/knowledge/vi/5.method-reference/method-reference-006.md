# Method reference: tham chiếu constructor mảng trong Java

**Tham chiếu constructor mảng** (*array constructor reference*) có dạng `ArrayType::new`, ví dụ `String[]::new`, `int[]::new` hoặc `String[][]::new`. Cú pháp này xuất hiện từ Java 8 và vẫn được sử dụng trong Java hiện đại để **truyền khả năng tạo mảng như một hàm**, thay vì tự tạo mảng ngay tại chỗ.

Ứng dụng thường thấy nhất là `Stream.toArray(String[]::new)`: một Stream các chuỗi được kết thúc bằng việc tạo ra `String[]` đúng kiểu. Dù chứa từ `new`, `String[]::new` **không lập tức cấp phát mảng**; nó là một *method reference expression* được gắn với functional interface, và mảng được tạo khi hàm được gọi.

Bài này tập trung vào cơ chế target typing, `IntFunction<T[]>`, Stream/Collection, primitive array, mảng nhiều chiều, generic type, lỗi thường gặp và các ví dụ biên dịch được với Java 17+.

## 1. Cú pháp và phép tương đương với lambda

Hai cách viết sau biểu diễn cùng một phép tạo mảng:

```java
IntFunction<String[]> byLambda = length -> new String[length];
IntFunction<String[]> byReference = String[]::new;

String[] a = byLambda.apply(3);
String[] b = byReference.apply(3);
```

**Đoạn minh họa**, cần `import java.util.function.IntFunction;` và đặt trong phương thức hoặc ngữ cảnh khai báo hợp lệ. Cả `a` và `b` đều là mảng `String[]` mới, mỗi mảng có độ dài `3` và ba phần tử mặc định `null`. Hai lời gọi tạo **hai mảng độc lập**. Có thể hình dung:

```text
String[]::new
    tương đương theo hành vi với
length -> new String[length]
```

Cú pháp `::new` ở đây không trỏ tới một constructor được khai báo trên class mảng như class thông thường. Theo Java Language Specification (JLS), compiler dùng một phương thức tạo mảng mang tính *notional* để tương thích với chữ ký của functional interface đích.

Khác với `new String[3]`, method reference chưa chứa độ dài cụ thể. **Tham số đầu vào của hàm đích chính là độ dài mảng**. Phương thức tạo mảng này nhận một kích thước thuộc kiểu `int` và trả về đối tượng mảng có kiểu được nêu bên trái `::new`.

**Không nhầm với constructor reference của class:**

```java
Supplier<StringBuilder> builderFactory = StringBuilder::new;
IntFunction<String[]> arrayFactory = String[]::new;
```

Đây là hai đoạn minh họa, cần `java.util.function.Supplier` và `IntFunction`. `StringBuilder::new` có thể khớp constructor không tham số của `StringBuilder` khi target là `Supplier`; `String[]::new` cần tham số kích thước khi target là `IntFunction`. Dù đều mang cú pháp method reference, loại đối tượng được tạo và cách suy luận chữ ký khác nhau.

## 2. Vì sao IntFunction<T[]> là target type tự nhiên?

Functional interface `java.util.function.IntFunction<R>` có phương thức trừu tượng:

```java
R apply(int value);
```

Đây là **chữ ký minh họa**, không phải định nghĩa toàn bộ interface. Khi đặt `R = String[]`, hợp đồng là:

```text
int (độ dài)  ->  String[] (mảng mới)
```

Ví dụ thực tế:

```java
IntFunction<String[]> newStrings = String[]::new;
IntFunction<Integer[]> newIntegers = Integer[]::new;
IntFunction<int[]> newInts = int[]::new;

String[] names = newStrings.apply(2);
Integer[] boxedNumbers = newIntegers.apply(4);
int[] primitiveNumbers = newInts.apply(4);
```

Đây là các **đoạn minh họa**, cần import `IntFunction`. Cả ba dùng kích thước `int` nhưng **kiểu phần tử khác nhau**:

| Reference | Target phù hợp | Kết quả khi `apply(3)` |
| --- | --- | --- |
| `String[]::new` | `IntFunction<String[]>` | `String[3]`, các phần tử `null` |
| `Integer[]::new` | `IntFunction<Integer[]>` | `Integer[3]`, các phần tử `null` |
| `int[]::new` | `IntFunction<int[]>` | `int[3]`, các phần tử `0` |
| `boolean[]::new` | `IntFunction<boolean[]>` | `boolean[3]`, các phần tử `false` |
| `String[][]::new` | `IntFunction<String[][]>` | `String[3][]`, ba hàng ban đầu `null` |

Chữ `int` trong `IntFunction` mô tả **kiểu tham số độ dài**, không bắt buộc phần tử của mảng là `int`. Đây là lỗi nhầm tên rất phổ biến.

**Target type là bắt buộc về ngữ nghĩa.** `String[]::new` là *poly expression*: kiểu của nó đến từ ngữ cảnh gán, truyền tham số hoặc cast. Vì vậy `IntFunction<String[]> factory = String[]::new;` hợp lệ, còn `var factory = String[]::new;` **không** hợp lệ vì `var` không cung cấp target type cho method reference.

## 3. Ứng dụng quan trọng nhất: Stream.toArray(generator)

`Stream<T>` có hai overload cần phân biệt:

```java
Object[] toArray();
<A> A[] toArray(IntFunction<A[]> generator);
```

Đây là **chữ ký API giản lược** để so sánh; không phải mã biên dịch độc lập. Với overload thứ hai, Java có thể nhận `String[]::new` làm generator:

```java
String[] names = Stream.of("An", "Binh", "Chi")
        .toArray(String[]::new);
```

Đây là đoạn minh họa, cần `import java.util.stream.Stream;`. `names` có kiểu **`String[]` cả ở compile time lẫn runtime** và chứa các phần tử theo encounter order của nguồn Stream có thứ tự này.

Một phép biến đổi trước khi tạo mảng:

```java
String[] normalized = Stream.of("  Java ", " Lambda  ")
        .map(String::trim)
        .toArray(String[]::new);
// ["Java", "Lambda"]
```

`String[]::new` không tự chuyển đổi phần tử: `map(String::trim)` mới làm việc đó. Generator chỉ tạo **vỏ mảng có đúng kiểu và kích thước mà Stream yêu cầu**; Stream chịu trách nhiệm đưa các kết quả vào mảng.

### Vì sao không chỉ gọi toArray()?

```java
Object[] objects = Stream.of("A", "B").toArray();
String[] strings = Stream.of("A", "B").toArray(String[]::new);
```

Cả hai là **đoạn minh họa hợp lệ**, cần `Stream`. `toArray()` không có đối số trả về `Object[]`, còn `toArray(String[]::new)` trả về `String[]`. Không thể viết `String[] strings = stream.toArray();` vì kết quả của overload không đối số là `Object[]`.

Cũng **không nên cast** như sau:

```java
// SAI tại runtime: toArray() tạo Object[], không phải String[].
// String[] strings = (String[]) Stream.of("A", "B").toArray();
```

Đây là ví dụ lỗi được comment để không chạy. Dù mọi phần tử đều là `String`, runtime type của **đối tượng mảng** vẫn là `Object[]`. Cast sang `String[]` ném `ClassCastException`. Dùng đúng overload nhận `String[]::new` để có mảng đúng runtime type.

### Stream có thể gọi generator nhiều lần

Theo hợp đồng của `Stream.toArray(IntFunction)`, generator có thể được dùng để cấp phát mảng kết quả **và các mảng phụ** trong quá trình xử lý phân vùng hoặc thay đổi kích thước. Vì thế, **không có bảo đảm generator chỉ được gọi một lần**, đặc biệt trong những cách thực thi phức tạp.

```java
String[] values = dataStream.toArray(String[]::new);
```

Đây là đoạn **minh họa API**, `dataStream` phải là một `Stream<String>` đã được định nghĩa. Nên truyền một generator đơn giản, không ghi log bắt buộc, không tăng bộ đếm nghiệp vụ và không sửa trạng thái dùng chung. Đừng coi số lần generator chạy là số lượng phần tử.

`toArray` là terminal operation: khi gọi nó, Stream thực hiện pipeline và thu thập kết quả. Với **ordered Stream**, kết quả tuân theo encounter order; điều này không có nghĩa lambda trong mọi bước của parallel Stream chạy tuần tự theo thứ tự đó.

## 4. Collection.toArray(String[]::new): giống cú pháp, khác overload

Từ **Java 11**, `java.util.Collection` có overload:

```java
default <T> T[] toArray(IntFunction<T[]> generator)
```

Đây là **chữ ký API giản lược**, không phải đoạn khai báo để sao chép vào project. Trên JDK 17+ có thể dùng trực tiếp:

```java
List<String> colors = List.of("red", "blue");
String[] result = colors.toArray(String[]::new);
```

Đoạn minh họa cần `import java.util.List;`. `result` là mảng `String[]` chứa `"red"` và `"blue"`. Cách viết không cần chuyển collection thành Stream.

**Phân biệt thời điểm xuất hiện:** `Stream.toArray(IntFunction)` đã có từ Java 8; `Collection.toArray(IntFunction)` được thêm vào Java 11 và vẫn là lựa chọn hiện đại. Nếu đang dùng Java 8 thật sự, với collection có thể dùng overload `toArray(T[] a)` có sẵn, chẳng hạn `colors.toArray(new String[0])`; trên JDK hiện đại, `colors.toArray(String[]::new)` rất rõ nghĩa.

Quan trọng hơn, **đừng giả định `Collection.toArray(IntFunction)` gọi generator với kích thước collection**. Default implementation được tài liệu hóa gọi generator với kích thước `0` rồi giao mảng đó cho `toArray(T[])`. Vì vậy, generator **không** phải callback để quan sát kích thước thật. Cứ viết `String[]::new` đơn giản; phương thức collection quyết định cấp phát phù hợp.

## 5. Mảng primitive và sự khác nhau với Stream<Integer>

Constructor reference không chỉ dành cho object arrays:

```java
IntFunction<int[]> intArrayFactory = int[]::new;
int[] values = intArrayFactory.apply(3);
// values = [0, 0, 0] (phần tử mặc định)
```

Đây là minh họa cần `IntFunction`. Mảng `int[]` lưu trực tiếp primitive `int`; `Integer[]` chứa tham chiếu tới wrapper `Integer`. Hai kiểu này **không tương đương**.

Ví dụ cần một mảng primitive từ dữ liệu số:

```java
int[] squares = IntStream.rangeClosed(1, 4)
        .map(n -> n * n)
        .toArray();
```

Đoạn minh họa cần `import java.util.stream.IntStream;`. Kết quả là `int[]` chứa `[1, 4, 9, 16]`. **Không cần** `int[]::new` ở đây vì `IntStream.toArray()` đã trả về `int[]` đúng kiểu.

Còn nếu nguồn là `Stream<Integer>`:

```java
Integer[] boxed = Stream.of(1, 2, 3)
        .toArray(Integer[]::new);

int[] primitive = Stream.of(1, 2, 3)
        .mapToInt(Integer::intValue)
        .toArray();
```

Đoạn minh họa cần `Stream`. `Stream<Integer>.toArray(Integer[]::new)` tạo wrapper array; cách dùng `mapToInt` đưa các số sang `IntStream` rồi `toArray()` mới tạo `int[]`. `Stream<Integer>.toArray(int[]::new)` **không phải cách thay thế hợp lệ**: generic `Stream.toArray(IntFunction<A[]>)` yêu cầu mảng có kiểu phần tử tham chiếu tương thích với `A`, còn `int[]` có phần tử primitive.

**Lưu ý:** với dữ liệu có thể chứa `null`, `mapToInt(Integer::intValue)` sẽ lỗi khi unbox phần tử `null`. Hãy quy định việc lọc, từ chối hoặc thay thế null theo yêu cầu nghiệp vụ trước khi chuyển.

## 6. Mảng nhiều chiều: chỉ có một tham số độ dài trong reference

Java hỗ trợ cú pháp sau:

```java
IntFunction<String[][]> rowSlots = String[][]::new;
String[][] rows = rowSlots.apply(2);
```

Đây là đoạn minh họa cần `IntFunction`. Tương đương `n -> new String[n][]`: mảng ngoài có độ dài `2`; `rows[0]` và `rows[1]` **đều là `null`**, vì chưa cấp phát các mảng con.

Điều này **khác** với mảng chữ nhật có đủ hàng và cột:

```java
IntFunction<String[][]> rectangular = rowCount ->
        new String[rowCount][3];

String[][] matrix = rectangular.apply(2);
// matrix có 2 hàng, mỗi hàng có 3 phần tử String mặc định null.
```

Đây là minh họa. `String[][]::new` truyền được **một kích thước**, không truyền trực tiếp hai kích thước như `new String[rows][columns]`. Khi cần thay đổi cả số hàng và số cột, hãy dùng lambda hoặc một functional interface hai tham số.

```java
@FunctionalInterface
interface IntMatrixFactory {
    int[][] create(int rows, int columns);
}

IntMatrixFactory factory = (rows, columns) ->
        new int[rows][columns];
int[][] data = factory.create(2, 3);
```

Đây là **mảnh định nghĩa minh họa**, đặt interface và các câu lệnh tại vị trí hợp lệ trong tệp Java. Interface tự định nghĩa với hai tham số `int` giúp tránh boxing kích thước. Không cần cố sử dụng `BiFunction<Integer,Integer,int[][]>` khi muốn diễn đạt hợp đồng primitive ở cả hai tham số.

## 7. Kết hợp constructor reference với generic API

Tham chiếu `String[]::new` cũng đặc biệt hữu ích khi viết một helper tái sử dụng:

```java
static <T> T[] collect(Stream<T> source,
                       IntFunction<T[]> generator) {
    return source.toArray(generator);
}
```

Đây là **phương thức minh họa**, cần import `Stream` và `IntFunction`, đặt trong class. Cách sử dụng:

```java
String[] names = collect(Stream.of("An", "Binh"), String[]::new);
Integer[] counts = collect(Stream.of(2, 4, 6), Integer[]::new);
```

Các dòng gọi này cần có phương thức `collect` ở trên và import `Stream`.

Tại sao helper nhận `IntFunction<T[]>` thay vì tự viết `new T[size]` hoặc `T[]::new`?

- Java dùng **type erasure** đối với type parameter `T`; một kiểu biến như `T` nói chung không phải *reifiable type*.
- JLS yêu cầu kiểu mảng đứng trước `::new` phải *reifiable*. Vì vậy trong generic method thông thường, `T[]::new` **không hợp lệ** khi `T` là type variable.
- Truyền generator cụ thể như `String[]::new` cho helper cho phép caller cung cấp thông tin **kiểu mảng runtime** thích hợp mà không dùng cast không an toàn.

Ví dụ **sai** ở generic helper:

```java
// SAI: type variable T không reifiable để tạo T[] trực tiếp.
// static <T> IntFunction<T[]> makeFactory() {
//     return T[]::new;
// }
```

Hãy yêu cầu caller cung cấp `IntFunction<T[]>` hoặc một cơ chế tạo mảng có đầy đủ runtime type, thay vì cố ép hệ thống kiểu generic tạo mảng không thể xác định thành phần lúc chạy.

## 8. Target typing và các lỗi cú pháp dễ gặp

### a) Không thể gán method reference vào biến var mà thiếu target

```java
// SAI: Java không có target type ở biểu thức khởi tạo.
// var factory = String[]::new;

// ĐÚNG:
IntFunction<String[]> factory = String[]::new;
```

Đây là đoạn minh họa cần `IntFunction`. Method reference không có kiểu riêng độc lập với functional interface đích. Khi truyền trực tiếp vào `Stream.toArray(...)`, compiler có thể suy luận kiểu từ chữ ký tham số của phương thức được gọi.

### b) Target không khớp số lượng tham số

```java
// SAI: Supplier.get() không có tham số độ dài.
// Supplier<String[]> factory = String[]::new;

// ĐÚNG: kích thước cố định thì dùng lambda.
Supplier<String[]> emptyFactory = () -> new String[0];

// ĐÚNG: kích thước do caller cung cấp.
IntFunction<String[]> sizedFactory = String[]::new;
```

Đây là đoạn minh họa cần import `Supplier` và `IntFunction`. `String[]::new` tương ứng với việc tạo mảng nhận đúng **một** độ dài, không khớp chữ ký không tham số của `Supplier`.

### c) Nhầm kiểu của mảng kết quả

```java
// Không biên dịch: toArray() không đối số trả Object[].
// String[] bad = Stream.of("A").toArray();

// Đúng:
String[] good = Stream.of("A").toArray(String[]::new);
```

Đây là đoạn minh họa cần `Stream`. Mục tiêu của constructor reference là giúp caller cung cấp **kiểu mảng đích**. Nếu chỉ cần `Object[]`, có thể dùng `toArray()` không đối số.

### d) Nhầm số phần tử với số chiều

```java
IntFunction<int[][]> rowsOnly = int[][]::new;
int[][] a = rowsOnly.apply(3);
// a có 3 phần tử kiểu int[], ban đầu đều null.

IntFunction<int[][]> fixedColumns = n -> new int[n][2];
int[][] b = fixedColumns.apply(3);
// b có 3 hàng, mỗi hàng chứa 2 số 0.
```

Đây là minh họa cần `IntFunction`. Mảng đa chiều trong Java là mảng chứa các mảng; không phải một block 2D có mọi hàng luôn tự được cấp phát.

## 9. Kiểu mảng runtime, an toàn kiểu và trường hợp lỗi

### NegativeArraySizeException

Vì kích thước do một `int` cung cấp, một giá trị âm gây lỗi cấp phát mảng:

```java
IntFunction<String[]> factory = String[]::new;
// factory.apply(-1); // Ném NegativeArraySizeException.
```

Đây là minh họa. Nếu kích thước đến từ input người dùng, dữ liệu ngoài hoặc phép tính có thể overflow, cần validate trước khi gọi generator. Kích thước quá lớn có thể dẫn tới `OutOfMemoryError`. Không nên bắt `OutOfMemoryError` như một nhánh điều kiện thông thường.

### ArrayStoreException khi loại phần tử không phù hợp

Một mảng object có **kiểu phần tử runtime**. Nếu code cố ghi object không tương thích vào mảng đó, JVM có thể ném `ArrayStoreException`. Overload `Stream.toArray(generator)` cũng chỉ thành công khi các phần tử thực tế có thể được lưu vào loại mảng do generator tạo.

```java
Object[] objects = new String[1];
// objects[0] = Integer.valueOf(10); // ArrayStoreException.
```

Đây là ví dụ minh họa, dòng gây lỗi đã comment. Mảng `String[]` có thể được nhìn qua kiểu `Object[]` do array covariance, nhưng runtime vẫn bảo vệ component type. Không cố “lách” generic type bằng cast hoặc generator trả sai loại mảng.

### Không dùng generator để giấu tác dụng phụ

```java
// KHÔNG NÊN: không đảm bảo đây là một callback chỉ chạy đúng một lần.
// stream.toArray(size -> {
//     auditLog.add("allocated " + size);
//     return new String[size];
// });

// NÊN: generator chuyên trách cấp phát.
String[] values = Stream.of("A", "B").toArray(String[]::new);
```

Các dòng đầu là **mã minh họa phản diện**, chưa định nghĩa `stream` và `auditLog`; đoạn cuối chạy được với import `Stream`. Trách nhiệm của generator là tạo mảng đúng kích thước và kiểu. Audit, metric hoặc logic nghiệp vụ cần đặt ở bước có hợp đồng rõ ràng, không dựa vào số lần Stream yêu cầu tạo mảng.

### Constructor reference không phải tối ưu thần kỳ

`String[]::new` và `size -> new String[size]` về ngữ nghĩa cùng giải quyết yêu cầu cấp phát. Method reference chủ yếu giúp **cú pháp ngắn, diễn đạt trực tiếp ý định và suy luận kiểu**. Nó không tự bảo đảm giảm cấp phát bộ nhớ hay làm code nhanh hơn. Chỉ tối ưu hiệu năng sau khi đo đúng workload.

## 10. Chương trình hoàn chỉnh chạy được trên JDK 17+

Ví dụ dưới đây gồm: factory trực tiếp, `Stream.toArray`, `Collection.toArray`, mảng primitive, mảng nhiều chiều, và helper generic. Các phần được viết riêng để phân biệt rõ **hàm tạo mảng** với **thao tác điền phần tử**.

Lưu thành tệp **ArrayConstructorReferenceDemo.java**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.function.IntFunction;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class ArrayConstructorReferenceDemo {

    static <T> T[] collect(Stream<T> source,
                           IntFunction<T[]> factory) {
        return source.toArray(factory);
    }

    public static void main(String[] args) {
        IntFunction<String[]> newStrings = String[]::new;
        String[] emptySlots = newStrings.apply(3);
        System.out.println("Allocated: " + emptySlots.length
                + ", first=" + emptySlots[0]);

        String[] names = Stream.of("An", "Binh", "Chi")
                .toArray(String[]::new);
        System.out.println("Stream: " + Arrays.toString(names));

        Integer[] lengths = Stream.of("Java", "Lambda")
                .map(String::length)
                .toArray(Integer[]::new);
        System.out.println("Lengths: " + Arrays.toString(lengths));

        List<String> colors = List.of("red", "blue");
        String[] colorsArray = colors.toArray(String[]::new);
        System.out.println("Collection: "
                + Arrays.toString(colorsArray));

        String[] generic = collect(Stream.of("X", "Y"),
                String[]::new);
        System.out.println("Generic: " + Arrays.toString(generic));

        IntFunction<int[]> newInts = int[]::new;
        int[] zeros = newInts.apply(2);
        System.out.println("Primitive: " + Arrays.toString(zeros));

        int[] squares = IntStream.rangeClosed(1, 4)
                .map(n -> n * n)
                .toArray();
        System.out.println("Squares: " + Arrays.toString(squares));

        IntFunction<int[][]> rowSlots = int[][]::new;
        int[][] rows = rowSlots.apply(2);
        System.out.println("Rows: " + rows.length
                + ", firstNull=" + (rows[0] == null));

        IntFunction<int[][]> fixedWidth =
                count -> new int[count][3];
        int[][] matrix = fixedWidth.apply(2);
        matrix[0][1] = 7;
        System.out.println("Matrix: " + Arrays.deepToString(matrix));
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên**:

```bash
javac ArrayConstructorReferenceDemo.java
java ArrayConstructorReferenceDemo
```

**Kết quả chuẩn (stdout):**

```text
Allocated: 3, first=null
Stream: [An, Binh, Chi]
Lengths: [4, 6]
Collection: [red, blue]
Generic: [X, Y]
Primitive: [0, 0]
Squares: [1, 4, 9, 16]
Rows: 2, firstNull=true
Matrix: [[0, 7, 0], [0, 0, 0]]
```

**Giải thích đầu ra:**

1. `newStrings.apply(3)` tạo mảng mới có độ dài `3`; chưa gán chuỗi nên phần tử đầu là `null`.
2. `Stream.of(...).toArray(String[]::new)` thu thập ba chuỗi theo thứ tự của ordered Stream.
3. `map(String::length)` đổi chuỗi thành `Integer` trong `Stream<Integer>`, vì vậy `Integer[]::new` phù hợp để thu thập `[4, 6]`.
4. `List.toArray(String[]::new)` chạy trên JDK 17+ vì overload collection đã có từ Java 11; kết quả là một `String[]` mới.
5. Helper generic nhận generator từ caller, tránh cố tạo `T[]` trực tiếp.
6. `int[]::new` tạo mảng primitive có giá trị mặc định `0`, trong khi `IntStream.toArray()` trực tiếp trả mảng các số đã được tính.
7. `int[][]::new` chỉ cấp phát mảng ngoài, nên hàng đầu là `null`. Lambda `count -> new int[count][3]` cấp phát cả mảng ngoài và các mảng hàng có ba số `0`; sau đó vị trí `[0][1]` được gán `7`.

## 11. Cách lựa chọn trong code thật

| Trường hợp | Cách viết ưu tiên | Vì sao |
| --- | --- | --- |
| Tạo mảng có độ dài do caller quyết định | `IntFunction<String[]> factory = String[]::new` | Hợp đồng `int -> String[]` minh bạch |
| Thu thập `Stream<String>` thành mảng chuỗi | `stream.toArray(String[]::new)` | Cung cấp đúng runtime component type |
| Chuyển `List<String>` thành mảng trên JDK 11+ | `list.toArray(String[]::new)` | Không cần tạo Stream trung gian |
| Chuyển `IntStream` thành mảng số nguyên | `intStream.toArray()` | API đã trả `int[]` |
| Chuyển `Stream<Integer>` sang `int[]` | `stream.mapToInt(Integer::intValue).toArray()` | Unbox sang primitive stream trước |
| Tạo mảng nhiều chiều, chỉ cấp phát mảng ngoài | `int[][]::new` | Các hàng ban đầu là `null` |
| Tạo mảng 2D có số cột cố định | `rows -> new int[rows][3]` | Lambda diễn đạt thêm kích thước cột |
| Hai kích thước động | Functional interface riêng hoặc lambda nhận hai tham số | Constructor reference mảng không nhận hai chiều |
| Generic helper cần đúng loại mảng | Nhận `IntFunction<T[]>` từ caller | Caller cung cấp runtime array type |
| Kích thước không chắc chắn | Kiểm tra giá trị trước khi tạo mảng | Tránh kích thước âm, quá lớn hoặc overflow |

**Checklist trước khi dùng `ArrayType::new`:**

1. Target functional interface có **một tham số `int`** và trả đúng loại mảng chưa?
2. Bạn cần `String[]`, `Integer[]` hay `int[]`? Chúng không thay thế được cho nhau.
3. Nguồn là `Stream<T>`, `Collection<T>` hay primitive Stream? Mỗi API có overload riêng.
4. Đã xác định rõ kiểu mảng **tại runtime**, không dùng cast từ `Object[]` chưa?
5. Với mảng nhiều chiều, cần chỉ mảng ngoài hay tất cả các hàng?
6. Nếu dùng generic method, có truyền generator thay vì cố tạo `new T[n]` hoặc `T[]::new` không?
7. Generator có chỉ làm việc cấp phát, không ẩn audit hay tác dụng phụ cần đúng một lần không?
8. Kích thước và các phần tử có hợp lệ với mảng cần tạo không?

### Bài tập thực hành

**Bài 1.** Khai báo `IntFunction<String[]>` bằng `String[]::new` rồi gọi `apply(4)`. Hỏi phần tử `[0]` là gì? Đáp án: `null`, vì đó là giá trị mặc định của phần tử mảng tham chiếu.

**Bài 2.** Chuyển `Stream.of("one", "two", "three")` thành `String[]` mà không ép kiểu. Đáp án gợi ý: `Stream.of("one", "two", "three").toArray(String[]::new)`.

**Bài 3.** Chuyển `IntStream.rangeClosed(1, 5)` thành `int[]` và sau đó thành `Integer[]`. Gợi ý: nhánh đầu dùng `toArray()`; nhánh thứ hai tạo lại Stream rồi gọi `boxed().toArray(Integer[]::new)`, bởi mỗi Stream không được tiêu thụ nhiều lần.

**Bài 4.** Dự đoán kết quả của `IntFunction<String[][]> f = String[][]::new; String[][] a = f.apply(2);`. Vì sao `a[0].length` ném `NullPointerException`? Đáp án: hai phần tử của mảng ngoài vẫn `null`; hãy gán mảng con hoặc dùng lambda cấp phát cột.

**Bài 5.** Viết phương thức generic `static <T> T[] collect(Stream<T> stream, IntFunction<T[]> factory)`, rồi dùng nó với `String[]::new` và `Integer[]::new`. Giải thích tại sao không thay factory bằng `T[]::new`.

**Bài 6.** Phân biệt `Stream.toArray(String[]::new)` (từ Java 8) và `Collection.toArray(String[]::new)` (từ Java 11). Vì sao không được giả định callback generator của chúng đều nhận độ dài cuối cùng, và vì sao không được dùng nó để đếm số lần xử lý?

### Tài liệu chính thức

- [Java Language Specification — `15.13 Method Reference Expressions](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.13)
- [Java Language Specification — `15.10 Array Creation and Access](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.10)
- [Java SE 26 — IntFunction](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/IntFunction.html)
- [Java SE 26 — Stream.toArray(IntFunction)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#toArray(java.util.function.IntFunction))
- [Java SE 26 — Collection.toArray(IntFunction)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collection.html#toArray(java.util.function.IntFunction))
- [Java SE 26 — IntStream](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/IntStream.html)
