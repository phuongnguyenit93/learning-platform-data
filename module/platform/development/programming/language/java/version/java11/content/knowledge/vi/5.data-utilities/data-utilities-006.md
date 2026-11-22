# Kiểu mảng runtime và ArrayStoreException trong Java

## 1. Vấn đề cốt lõi: kiểu khai báo của biến không thay thế kiểu thực tế của mảng

Một biến tham chiếu đến mảng có thể được khai báo bằng kiểu rộng hơn kiểu của đối tượng mảng thực tế. Tuy nhiên, **kiểu phần tử của đối tượng mảng được xác định tại thời điểm tạo mảng và được JVM giữ lại ở runtime**.

Ví dụ:

```java
String[] names = {"Java", "JVM"};
Object[] values = names;

values[0] = "Java 11";        // Hợp lệ: giá trị String
// values[1] = Integer.valueOf(42); // Biên dịch được, nhưng ném ArrayStoreException lúc chạy
```

Tại đây có hai lớp thông tin khác nhau:

| Thành phần | Kiểu | Vai trò |
| --- | --- | --- |
| Biến `names` | `String[]` (kiểu tĩnh) | Compiler chỉ cho phép ghi các giá trị tương thích `String` |
| Biến `values` | `Object[]` (kiểu tĩnh) | Compiler cho phép ghi tham chiếu `Object` và các subtype |
| Đối tượng mà cả hai biến cùng tham chiếu | **`String[]` (kiểu runtime)** | JVM chỉ chấp nhận giá trị tương thích `String` khi lưu vào các ô |

**Gán `values = names` không biến đối tượng `String[]` thành `Object[]`.** Cả hai biến cùng trỏ đến một đối tượng mảng; cách nhìn qua kiểu biến `Object[]` không loại bỏ ràng buộc runtime của mảng `String[]`.

`ArrayStoreException` bảo vệ tính nhất quán ấy. Đây là `RuntimeException` (unchecked exception) được ném khi một thao tác cố lưu giá trị không tương thích với **kiểu phần tử thực tế** của mảng.

Các quy tắc này vẫn áp dụng trong Java 11 và các bản Java hiện hành; không phụ thuộc vào một tính năng chỉ có ở phiên bản cũ.

## 2. Tại sao mã hợp lệ khi biên dịch lại có thể lỗi lúc chạy?

### 2.1. Tính hiệp biến (covariance) của mảng tham chiếu

Trong Java, nếu `String` là subtype của `Object` thì `String[]` cũng là subtype của `Object[]`. Tương tự:

```java
Integer[] integers = {1, 2};
Number[] numbers = integers;  // Hợp lệ vì Integer[] là subtype của Number[]
```

Quy tắc này gọi là **array covariance**. Nó áp dụng cho mảng chứa kiểu tham chiếu, cho phép sử dụng mảng subtype tại vị trí mong đợi mảng supertype.

Điểm quan trọng: **covariance không có nghĩa có thể thêm mọi đối tượng của supertype vào mảng subtype**. Ví dụ:

```java
Number[] numbers = new Integer[2];

numbers[0] = Integer.valueOf(10);  // Hợp lệ
numbers[1] = Double.valueOf(2.5);  // Ném ArrayStoreException lúc chạy
```

Compiler xem `numbers` là `Number[]` nên cho phép đối tượng `Double` vì `Double` kế thừa `Number`. JVM xem đối tượng thật là `Integer[]` nên từ chối lưu `Double`. Nếu JVM không kiểm tra, đọc qua tham chiếu `Integer[]` ban đầu có thể nhận một phần tử không phải `Integer`, làm hỏng đảm bảo kiểu.

Có thể hình dung luồng kiểm tra:

```text
Number[] numbers = new Integer[2]
          |
          | kiểu tĩnh: Number[]
          v
numbers[1] = Double.valueOf(2.5)
          |
          | compiler: Double phù hợp với Number -> chấp nhận
          v
JVM kiểm tra đối tượng mảng: Integer[]
          |
          | Double không thể lưu trong thành phần Integer
          v
ArrayStoreException
```

### 2.2. Kiểm tra kiểu khi gán một phần tử

Theo Java Language Specification `10.5, với mảng có phần tử là **kiểu tham chiếu**, mỗi phép ghi vào phần tử phải bảo đảm giá trị được gán phù hợp với kiểu thành phần của **đối tượng mảng runtime**.

Các trường hợp:

- Giá trị là một instance tương thích với kiểu phần tử runtime → ghi thành công.
- Giá trị là một instance không tương thích → `ArrayStoreException`.
- Giá trị là `null` → hợp lệ với mọi mảng kiểu tham chiếu, vì `null` gán được cho kiểu tham chiếu.
- Biểu thức đã bị từ chối tại compile time do không phù hợp với kiểu biến → không có chương trình hợp lệ để chạy và cũng không phát sinh `ArrayStoreException` từ dòng đó.

Ví dụ phân biệt rõ **compile-time error** và **runtime error**:

```java
String[] a = new String[1];
// a[0] = Integer.valueOf(1); // LỖI BIÊN DỊCH: Integer không gán được cho String

Object[] b = a;                // Hợp lệ: covariance
// b[0] = Integer.valueOf(1); // BIÊN DỊCH ĐƯỢC, runtime ném ArrayStoreException

b[0] = "text";                 // Hợp lệ cả compile time lẫn runtime
b[0] = null;                   // Hợp lệ với String[]
```

Dòng gây lỗi được chú thích để đoạn mã vẫn có thể biên dịch nếu đem chạy. Khi cần chủ động tái hiện exception, bỏ dấu comment của đúng dòng có nhãn runtime (và giữ nguyên `try/catch` nếu dùng trong bài thực hành).

## 3. Phân biệt kiểu tĩnh và kiểu runtime bằng mã

Mảng là một đối tượng Java nên có thể xem lớp runtime và loại phần tử:

```java
String[] strings = new String[2];
Object[] objects = strings;

System.out.println(objects.getClass().getTypeName());
System.out.println(objects.getClass().getComponentType().getTypeName());
System.out.println(objects instanceof String[]);
```

Kết quả:

```text
java.lang.String[]
java.lang.String
true
```

`getClass()` phản ánh lớp của **đối tượng thật**, không phải kiểu của biến `objects`. `getComponentType()` trả về đối tượng `Class<?>` đại diện cho kiểu thành phần runtime; `getTypeName()` hiển thị tên dễ đọc.

Có thể suy ra các trường hợp sau:

| Khởi tạo | Kiểu tĩnh của biến | Kiểu runtime của mảng | Có nhận `Double` khi gán phần tử? |
| --- | --- | --- | --- |
| `Object[] a = new Object[2]` | `Object[]` | `Object[]` | Có |
| `Object[] a = new String[2]` | `Object[]` | `String[]` | Không |
| `Number[] a = new Number[2]` | `Number[]` | `Number[]` | Có |
| `Number[] a = new Integer[2]` | `Number[]` | `Integer[]` | Không |

**Không suy luận kiểu runtime từ nội dung hiện đang có.** Một `Object[]` chứa toàn chuỗi vẫn là `Object[]`; một `String[]` đang toàn `null` vẫn là `String[]`. Loại đối tượng mảng được quyết định khi tạo đối tượng bằng `new String[...]`, `new Object[...]` hoặc các API tạo mảng.

## 4. Ba tình huống dễ nhầm: ArrayStoreException, ClassCastException, lỗi biên dịch

### Tình huống A: Biên dịch được, ghi sai kiểu runtime

```java
String[] strings = {"A", "B"};
Object[] objects = strings;

try {
    objects[0] = Integer.valueOf(7);
} catch (ArrayStoreException e) {
    System.out.println("Wrong element type");
}
```

Kết quả:

```text
Wrong element type
```

Vì đối tượng thật là `String[]`, giá trị `Integer` không được lưu. Dòng thất bại không thay đổi giá trị cũ tại `objects[0]`.

### Tình huống B: Cast cả đối tượng mảng sai kiểu

```java
Object[] objects = {"A", "B"};  // Đối tượng runtime là Object[]

try {
    String[] strings = (String[]) objects;
} catch (ClassCastException e) {
    System.out.println("Wrong array type");
}
```

Kết quả:

```text
Wrong array type
```

Dù tất cả phần tử hiện tại đều là `String`, đối tượng mảng thực tế là `Object[]`, không phải `String[]`. Cast **cả mảng** không chuyển đổi từng phần tử và không tự tạo một mảng `String[]`.

Ngược lại:

```java
Object[] objects = new String[]{"A", "B"};
String[] strings = (String[]) objects;  // Hợp lệ: runtime thật là String[]
```

### Tình huống C: Ghi sai ngay theo kiểu khai báo

```java
String[] strings = new String[2];
// strings[0] = Integer.valueOf(7); // Không biên dịch
```

Compiler loại phép gán vì `Integer` không tương thích `String`. Lỗi compile-time này khác với `ArrayStoreException`, vì JVM chưa có cơ hội thực thi.

### Bảng so sánh nhanh

| Hiện tượng | Điều kiện | Thời điểm |
| --- | --- | --- |
| Compile-time type error | Giá trị không tương thích với **kiểu phần tử của biểu thức mảng tại compile time** | Trước khi chạy |
| `ArrayStoreException` | Phép ghi/copy cố lưu phần tử không tương thích với **kiểu phần tử mảng runtime** | Khi chạy |
| `ClassCastException` | Ép kiểu tham chiếu mảng sang kiểu runtime không phù hợp | Khi chạy |
| `ArrayIndexOutOfBoundsException` | Truy cập phần tử bằng index ngoài phạm vi `0..length - 1` | Khi chạy |
| `NullPointerException` | Truy cập phần tử thông qua tham chiếu mảng bằng `null` | Khi chạy |

Không nên xử lý mọi lỗi bằng `catch (RuntimeException)` hoặc giả định các exception trên tương đương; chúng chỉ ra các nguyên nhân khác nhau.

## 5. Arrays.copyOf(): sao chép không tự thay đổi kiểu mảng runtime

Lỗi phổ biến là tin rằng gán kết quả `Arrays.copyOf` vào biến `Number[]` sẽ tạo mảng runtime `Number[]`. Với overload hai đối số `Arrays.copyOf(T[] original, int newLength)`, **kiểu đối tượng của bản sao giống chính xác kiểu runtime của mảng gốc**, dù kiểu biến nhận rộng hơn.

```java
import java.util.Arrays;

Integer[] original = {1, 2};
Number[] copy = Arrays.copyOf(original, 3);

System.out.println(copy.getClass().getTypeName()); // java.lang.Integer[]
// copy[2] = Double.valueOf(3.5); // Runtime: ArrayStoreException
```

Đây là một trường hợp hai lớp kiểu tiếp tục khác nhau: `copy` có kiểu tĩnh `Number[]` nhưng bản sao mới có kiểu runtime `Integer[]`.

Khi thực sự muốn mảng runtime `Number[]` để có thể chứa cả `Integer` và `Double`, dùng overload có đối số `Class<? extends T[]> newType`:

```java
import java.util.Arrays;

Integer[] original = {1, 2};
Number[] widened = Arrays.copyOf(original, 3, Number[].class);

widened[2] = Double.valueOf(3.5);

System.out.println(widened.getClass().getTypeName());
System.out.println(Arrays.toString(widened));
```

Kết quả:

```text
java.lang.Number[]
[1, 2, 3.5]
```

Lưu ý:

- `Arrays.copyOf(original, newLength)` giữ **lớp runtime** của mảng gốc.
- `Arrays.copyOf(original, newLength, newType)` tạo mảng theo đúng `newType`.
- Nếu một phần tử gốc không thể lưu vào loại mảng đích được yêu cầu, overload có `newType` có thể ném `ArrayStoreException`.
- Tăng độ dài mảng tham chiếu sẽ điền `null` vào các vị trí mới; không tự khởi tạo đối tượng phần tử.

**Thay đổi kiểu tĩnh của biến không làm rộng kiểu của mảng thật**. Muốn thay đổi loại runtime, phải thực sự tạo mảng đúng loại và copy các phần tử tương thích.

## 6. System.arraycopy(): có thể lỗi sau khi đã sao chép một phần

`System.arraycopy(src, srcPos, dest, destPos, length)` thực hiện copy giữa hai mảng. Với mảng kiểu tham chiếu, mỗi phần tử nguồn cần tương thích với kiểu phần tử runtime của mảng đích.

Ví dụ:

```java
import java.util.Arrays;

Object[] source = {"first", 17, "third"};
String[] destination = {"old0", "old1", "old2"};

try {
    System.arraycopy(source, 0, destination, 0, 3);
} catch (ArrayStoreException e) {
    System.out.println("Copy failed");
}

System.out.println(Arrays.toString(destination));
```

Kết quả:

```text
Copy failed
[first, old1, old2]
```

Diễn biến:

1. `source[0]` là chuỗi `"first"`, lưu hợp lệ vào `destination[0]`.
2. `source[1]` là `Integer`, không tương thích với mảng runtime `String[]`.
3. `ArrayStoreException` xuất hiện; phần tử đầu **đã được copy**, còn các phần tử phía sau không được copy.

Tài liệu chuẩn của `System.arraycopy` nêu rõ việc **copy từng phần** có thể xảy ra với lỗi không tương thích phần tử giữa hai mảng tham chiếu. Vì thế, không nên cho rằng thao tác này có tính nguyên tử (*all-or-nothing*).

Cũng phải phân biệt với các lỗi kiểm tra đầu vào: hai mảng primitive không cùng kiểu, hoặc một bên là primitive còn bên kia là reference array, dẫn đến `ArrayStoreException` theo điều kiện loại mảng và **không copy phần tử**. Sai index/length có thể dẫn đến `IndexOutOfBoundsException`, cũng không copy phần tử. Các điều kiện cụ thể được xác định trong Javadoc của `System.arraycopy`.

### Các API khác cũng gặp kiểm tra kiểu runtime

`Arrays.fill(Object[] a, Object value)` có thể ném `ArrayStoreException` nếu `a` thực sự là mảng con hẹp hơn:

```java
import java.util.Arrays;

Object[] view = new String[2];

Arrays.fill(view, "ok");            // Hợp lệ
// Arrays.fill(view, Integer.valueOf(5)); // Runtime: ArrayStoreException
```

Tương tự, các API sao chép/ghi dữ liệu vào mảng có thể phát sinh lỗi nếu kiểu phần tử thực tế của mảng đích không phù hợp. Chỉ tên biến `Object[]` không bảo đảm chấp nhận mọi loại đối tượng.

## 7. Mảng primitive không hoạt động giống mảng tham chiếu

Tính hiệp biến mảng tham chiếu **không mở rộng tùy ý sang các kiểu primitive**.

```java
int[] numbers = {1, 2};
Object asObject = numbers;        // Hợp lệ: mảng là đối tượng Java

// Object[] asObjects = numbers; // Không biên dịch: int[] không phải Object[]
// long[] longs = numbers;       // Không biên dịch: int[] không phải long[]
```

Thêm kiểm tra runtime:

```java
Object value = new int[]{1, 2};

System.out.println(value instanceof Object[]); // false
System.out.println(value.getClass().getComponentType().getTypeName()); // int
```

Trong `int[]`, các phần tử là giá trị `int`. Mảng này không phải một `Object[]` chứa các hộp `Integer`. Nếu cần mảng tham chiếu có thể chứa `null` và làm việc với `Number`, phải chủ động sử dụng `Integer[]` hoặc `Number[]` và hiểu quy tắc boxing/unboxing.

`System.arraycopy` cũng yêu cầu các mảng primitive có kiểu thành phần primitive phù hợp. Không có chuyển đổi tự động từ `int[]` sang `long[]` bằng `System.arraycopy`.

## 8. Mảng đa chiều: mỗi cấp mảng là một đối tượng có kiểu runtime riêng

Mảng nhiều chiều trong Java là **mảng của các mảng**. Do covariance, một tham chiếu `Object[][]` có thể trỏ đến đối tượng `String[][]`, nhưng các phần tử ở cấp đầu phải là mảng `String[]`.

```java
Object[][] matrix = new String[1][2];

matrix[0] = new String[]{"A", "B"}; // Hợp lệ
// matrix[0] = new Object[]{"A", "B"}; // Runtime: ArrayStoreException

Object[] row = matrix[0];
row[0] = "updated";               // Hợp lệ
// row[1] = Integer.valueOf(10);  // Runtime: ArrayStoreException
```

Ở phép gán `matrix[0] = ...`, JVM kiểm tra thành phần runtime của **mảng ngoài** là `String[]`. Ở phép gán `row[1] = ...`, JVM kiểm tra thành phần runtime của **mảng trong** là `String`.

Điều này giải thích vì sao lỗi kiểu mảng vẫn có thể xuất hiện ở nhiều mức khi xử lý bảng, ma trận hoặc dữ liệu lồng nhau. `Object[][]` chỉ là kiểu tham chiếu dùng để nhìn mảng; nó không làm mất kiểu runtime tại mỗi cấp.

## 9. Liên hệ với generics và lựa chọn cấu trúc dữ liệu an toàn

### 9.1. Array covariance khác với generics invariance

Ví dụ đối chiếu:

```java
import java.util.ArrayList;
import java.util.List;

Number[] array = new Integer[2]; // Hợp lệ: array covariance

// List<Number> list = new ArrayList<Integer>();
// Không biên dịch: List<Integer> không phải subtype của List<Number>
```

`List<Integer>` và `List<Number>` là hai kiểu generic bất biến (*invariant*). Compiler không cho phép chuyển thẳng từ danh sách phần tử hẹp sang danh sách phần tử rộng, tránh một nhóm lỗi kiểu ngay từ compile time.

Nếu nghiệp vụ cần chứa nhiều subclass của `Number`, tạo đúng container:

```java
import java.util.ArrayList;
import java.util.List;

List<Number> values = new ArrayList<>();
values.add(Integer.valueOf(10));
values.add(Double.valueOf(2.5));
```

Hoặc nếu cần mảng có kích thước cố định:

```java
Number[] values = new Number[2];
values[0] = Integer.valueOf(10);
values[1] = Double.valueOf(2.5);
```

Cả hai cách đều có kiểu phần tử phù hợp với phạm vi dữ liệu thực sự. Chọn `List<Number>` nếu cần thêm/xóa phần tử và khai thác các API collection; chọn `Number[]` khi phải dùng array hoặc giao tiếp với API yêu cầu mảng.

**Cảnh báo:** generics dựa vào kiểm tra biên dịch và type erasure; raw types hoặc unchecked casts vẫn có thể gây lỗi khác tại runtime. Không nên vì tránh `ArrayStoreException` mà bỏ kiểm tra kiểu bằng raw types.

### 9.2. Vì sao không tạo trực tiếp mảng generic parameterized?

```java
import java.util.List;

// List<String>[] items = new List<String>[2];
// Lỗi biên dịch: generic array creation
```

Thông tin generic như `<String>` không thể được kiểm tra đầy đủ bằng array store check của JVM do type erasure; việc tạo mảng có thành phần generic không *reifiable* bị hạn chế bởi ngôn ngữ. Trong nhiều trường hợp, `List<List<String>>` là lựa chọn rõ ràng và an toàn hơn.

Không nên viết unchecked cast từ `Object[]` sang `T[]` rồi giả định kiểu mảng runtime đã được biến đổi. `@SuppressWarnings("unchecked")` chỉ tắt cảnh báo, **không** loại bỏ các kiểm tra runtime và cũng không tạo ra mảng thuộc kiểu `T[]`.

### 9.3. Chuyển collection hoặc stream sang mảng đúng loại

Với dữ liệu toàn `String`:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> words = List.of("Java", "11");
String[] a = words.toArray(new String[0]);
String[] b = Stream.of("Java", "11").toArray(String[]::new);
```

Cả hai cách đều tạo đối tượng runtime `String[]`. Cách `Stream.toArray(String[]::new)` sử dụng generator để xác định loại mảng cần tạo.

Tuy nhiên, `Collection.toArray(T[])` vẫn có thể ném `ArrayStoreException` nếu collection có phần tử không tương thích với kiểu mảng truyền vào:

```java
import java.util.List;

List<Object> mixed = List.of("Java", Integer.valueOf(11));
// String[] wrong = mixed.toArray(new String[0]);
// Có thể biên dịch; runtime ném ArrayStoreException do phần tử Integer
```

Giải pháp là xác nhận tất cả phần tử thực sự là `String`, hoặc chủ động chuyển đổi theo quy tắc nghiệp vụ:

```java
String[] converted = mixed.stream()
        .map(String::valueOf)
        .toArray(String[]::new); // ["Java", "11"]
```

Cách chuyển đổi này có chủ đích, không dựa vào cast sai kiểu mảng.

## 10. Ví dụ Java 11+ hoàn chỉnh và có thể chạy

Lưu chương trình thành **`ArrayRuntimeDemo.java`**:

```java
import java.util.Arrays;

public class ArrayRuntimeDemo {
    public static void main(String[] args) {
        String[] words = {"java", "jvm"};
        Object[] view = words;

        System.out.println("runtime=" +
                view.getClass().getTypeName());
        System.out.println("component=" +
                view.getClass().getComponentType().getTypeName());

        view[0] = "Java 11";
        System.out.println("valid=" + Arrays.toString(words));

        try {
            view[1] = Integer.valueOf(42);
        } catch (ArrayStoreException ex) {
            System.out.println("store=" +
                    ex.getClass().getSimpleName());
        }
        System.out.println("after=" + Arrays.toString(words));

        view[1] = null;
        System.out.println("nullable=" + Arrays.toString(words));

        Object[] plain = {"a", "b"};
        try {
            String[] wrong = (String[]) plain;
        } catch (ClassCastException ex) {
            System.out.println("cast=" +
                    ex.getClass().getSimpleName());
        }

        Number[] numbers = new Integer[]{1, 2};
        try {
            numbers[1] = Double.valueOf(3.5);
        } catch (ArrayStoreException ex) {
            System.out.println("numberStore=" +
                    ex.getClass().getSimpleName());
        }
        System.out.println("numbers=" + Arrays.toString(numbers));

        Integer[] original = {1, 2};
        Number[] sameType = Arrays.copyOf(original, 3);
        System.out.println("copyRuntime=" +
                sameType.getClass().getTypeName());

        try {
            sameType[2] = Double.valueOf(3.5);
        } catch (ArrayStoreException ex) {
            System.out.println("copyStore=" +
                    ex.getClass().getSimpleName());
        }

        Number[] widened =
                Arrays.copyOf(original, 3, Number[].class);
        widened[2] = Double.valueOf(3.5);
        System.out.println("widened=" + Arrays.toString(widened));

        Object[] src = {"first", 17, "third"};
        String[] dest = {"old0", "old1", "old2"};
        try {
            System.arraycopy(src, 0, dest, 0, 3);
        } catch (ArrayStoreException ex) {
            System.out.println("arraycopy=" +
                    ex.getClass().getSimpleName());
        }
        System.out.println("partial=" + Arrays.toString(dest));

        Object primitive = new int[]{1, 2};
        System.out.println("primitiveIsObjectArray=" +
                (primitive instanceof Object[]));
        System.out.println("primitiveComponent=" +
                primitive.getClass().getComponentType().getTypeName());

        Object[][] matrix = new String[1][2];
        try {
            matrix[0] = new Object[2];
        } catch (ArrayStoreException ex) {
            System.out.println("nestedStore=" +
                    ex.getClass().getSimpleName());
        }
        matrix[0][0] = "ok";
        System.out.println("nested=" + Arrays.deepToString(matrix));
    }
}
```

Biên dịch và chạy bằng JDK 11 trở lên:

```bash
javac --release 11 ArrayRuntimeDemo.java
java ArrayRuntimeDemo
```

Kết quả chính xác:

```text
runtime=java.lang.String[]
component=java.lang.String
valid=[Java 11, jvm]
store=ArrayStoreException
after=[Java 11, jvm]
nullable=[Java 11, null]
cast=ClassCastException
numberStore=ArrayStoreException
numbers=[1, 2]
copyRuntime=java.lang.Integer[]
copyStore=ArrayStoreException
widened=[1, 2, 3.5]
arraycopy=ArrayStoreException
partial=[first, old1, old2]
primitiveIsObjectArray=false
primitiveComponent=int
nestedStore=ArrayStoreException
nested=[[ok, null]]
```

Các kết quả chứng minh:

1. Kiểu runtime của `view` là `String[]` dù biến khai báo `Object[]`.
2. Ghi `Integer` không thành công; phần tử cũ `"jvm"` vẫn còn sau khi ném `ArrayStoreException`. Ghi `null` hợp lệ.
3. Cast `Object[]` thực tế sang `String[]` ném `ClassCastException`; không có phép copy chuyển đổi tự động.
4. `Number[]` trỏ đến `Integer[]` vẫn từ chối `Double`.
5. `Arrays.copyOf` hai tham số giữ runtime `Integer[]`; overload `Number[].class` thực sự tạo `Number[]`.
6. `System.arraycopy` có thể để lại kết quả copy từng phần khi lỗi giữa chừng.
7. `int[]` có thể là `Object` nhưng không phải `Object[]`.
8. Mảng nhiều chiều vẫn kiểm tra kiểu thành phần ở từng cấp.

## 11. Cách đọc lỗi và thiết kế để không gặp ArrayStoreException

Khi thấy `ArrayStoreException`, cách xử lý hữu ích là truy nguyên đối tượng mảng thật và vị trí ghi:

1. Tìm phép gán dạng `array[index] = value` hoặc API ghi/copy như `Arrays.fill`, `System.arraycopy`, `Arrays.copyOf(..., newType)`, `toArray(T[])`.
2. Xác định biểu thức/biến mảng có kiểu tĩnh nào và đối tượng mảng được tạo ở đâu, bằng `new ...[]` hay API tạo mảng.
3. Trong chế độ debug, kiểm tra `array.getClass().getTypeName()` và `array.getClass().getComponentType()` (sau khi bảo đảm tham chiếu không phải `null`).
4. Xác định kiểu runtime của giá trị định ghi và lý do nó không tương thích với kiểu thành phần runtime.
5. Sửa cách **tạo container, kiểu tham số API hoặc luồng chuyển đổi dữ liệu**. Không nên coi `catch (ArrayStoreException)` rồi bỏ qua phần tử là giải pháp cho thiết kế kiểu sai.

Ví dụ thiết kế tham số có thể dẫn đến lỗi:

```java
static void appendDouble(Number[] target) {
    target[0] = Double.valueOf(2.5);
}

// appendDouble(new Integer[1]); // Compile OK, runtime ArrayStoreException
```

Nếu phương thức **phải** lưu `Double`, tham số `Number[]` có thể che giấu mảng runtime `Integer[]`. Cần thiết kế contract chính xác hơn: yêu cầu người gọi cung cấp mảng đích thực sự phù hợp, tạo `Number[]` trong phương thức, trả về cấu trúc dữ liệu mới, hoặc sử dụng một `List<Number>` do phương thức kiểm soát khi hợp với nghiệp vụ. Không thể chỉ thêm cast `(Number[])` để thay đổi runtime type của mảng.

### Phân biệt lỗi bằng thông tin thực sự có ích

| Triệu chứng | Điều cần kiểm tra | Hướng khắc phục |
| --- | --- | --- |
| `ArrayStoreException` ngay tại `array[i] = value` | Loại runtime của mảng và `value` | Tạo mảng rộng đúng loại hoặc chỉ lưu loại tương thích |
| `ClassCastException` tại `(String[]) array` | Mảng thật là `Object[]` hay `String[]` | Chuyển đổi từng phần tử sang mảng mới nếu cần |
| `ArrayStoreException` sau `Arrays.copyOf` | Overload hai đối số giữ runtime class của mảng gốc | Dùng overload có `Number[].class` nếu cần array runtime rộng hơn |
| `ArrayStoreException` trong `System.arraycopy` | Thành phần nguồn và đích, dữ liệu đã copy một phần | Validate/convert trước; không dựa vào tính nguyên tử |
| `ArrayIndexOutOfBoundsException` | Index âm hoặc lớn hơn/equal `length` | Kiểm tra phạm vi chỉ số, không nhầm với lỗi kiểu |
| `NullPointerException` khi gán phần tử | Tham chiếu mảng là `null` | Khởi tạo/kiểm tra tham chiếu trước khi dùng |
| Không thể `new List<String>[n]` | Kiểu phần tử generic không *reifiable* | Dùng collection lồng nhau hoặc API tạo array đúng mô hình |
| Không thể gán `int[]` cho `Object[]` | Primitive array không phải array của tham chiếu `Object` | Chọn `Integer[]` khi cần boxed references hoặc xử lý `int[]` riêng |

## 12. Câu hỏi luyện tập có đáp án

**Câu 1.** Đoạn nào ném `ArrayStoreException`?

```java
Object[] a = new String[2];
a[0] = "ok";
a[1] = Integer.valueOf(1);
```

**Đáp án:** Dòng cuối. Kiểu tĩnh của `a` là `Object[]` nhưng kiểu runtime của mảng là `String[]`.

**Câu 2.** `Object[] a = new Object[]{"x", "y"}; String[] b = (String[]) a;` có hợp lệ không?

**Đáp án:** Biên dịch được nhưng runtime ném `ClassCastException` vì đối tượng thật là `Object[]`. Việc các phần tử hiện tại là `String` không làm thay đổi kiểu của mảng.

**Câu 3.** Tại sao `Number[] values = new Integer[2]` hợp lệ nhưng `values[0] = Double.valueOf(1.5)` không hợp lệ lúc chạy?

**Đáp án:** Array covariance cho phép tham chiếu `Number[]` trỏ đến `Integer[]`; runtime store check vẫn chỉ chấp nhận các giá trị tương thích `Integer`.

**Câu 4.** Gán `null` vào một phần tử của `String[]` thông qua `Object[]` có ném `ArrayStoreException` không?

**Đáp án:** Không. `null` hợp lệ với mọi kiểu thành phần tham chiếu.

**Câu 5.** `Number[] copy = Arrays.copyOf(new Integer[]{1}, 2);` có kiểu runtime gì?

**Đáp án:** `Integer[]`. Overload hai đối số bảo toàn runtime class của mảng gốc. Muốn `Number[]` runtime thì yêu cầu `Arrays.copyOf(original, 2, Number[].class)`.

**Câu 6.** Khi `System.arraycopy` gặp phần tử không phù hợp ở giữa dãy, mảng đích có chắc giữ nguyên không?

**Đáp án:** Không. Với mảng tham chiếu và lỗi ở một phần tử cụ thể, các phần tử trước vị trí sai có thể đã được copy đúng theo hợp đồng API.

**Câu 7.** `Object obj = new int[]{1, 2};` có hợp lệ không? `obj instanceof Object[]` trả gì?

**Đáp án:** Hợp lệ vì mọi mảng đều là đối tượng Java; biểu thức `instanceof Object[]` trả `false` vì `int[]` là mảng primitive.

**Câu 8.** Có nên dùng `List<Number> list = new ArrayList<Integer>();` để mô phỏng `Number[] array = new Integer[2]`?

**Đáp án:** Không biên dịch: generics là invariant. Nếu muốn chứa cả `Integer` và `Double`, dùng `new ArrayList<Number>()` và thêm các phần tử theo API của `List<Number>`.

## Tài liệu chính thức còn áp dụng

- [Java Language Specification, Java SE 27 — Chương 10: Arrays](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-10.html) — `10.1` loại mảng, `10.5` runtime array store check, `10.8` đối tượng `Class` của mảng.
- [Java SE 11 — ArrayStoreException](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/ArrayStoreException.html) — định nghĩa exception và quan hệ với `RuntimeException`.
- [Java SE 11 — Arrays.copyOf](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Arrays.html) — overload giữ nguyên runtime class và overload cho phép chỉ định loại mảng đích.
- [Java SE 27 — System.arraycopy](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/System.html#arraycopy(java.lang.Object,int,java.lang.Object,int,int)) — điều kiện lỗi, kiểm tra tương thích phần tử và quy tắc copy từng phần.
- [Java SE 11 — Collection.toArray](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/Collection.html#toArray(T%5B%5D)) — mảng kết quả và trường hợp `ArrayStoreException` khi phần tử không phù hợp.

**Điểm cần nhớ:** Compiler kiểm tra phép gán theo **kiểu tĩnh của biến**, còn JVM kiểm tra phép lưu phần tử theo **kiểu thành phần runtime của đối tượng mảng**. Array covariance cho phép hai góc nhìn này khác nhau; `ArrayStoreException` là cơ chế ngăn dữ liệu sai kiểu đi vào đối tượng mảng. Khi cần thay đổi phạm vi loại phần tử, hãy tạo container đúng loại thay vì chỉ ép kiểu tham chiếu.