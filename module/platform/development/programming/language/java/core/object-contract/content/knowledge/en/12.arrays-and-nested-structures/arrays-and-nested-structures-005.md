# Mảng nguyên thủy khác mảng lớp bao trong Java: kiểu dữ liệu, hợp đồng bằng nhau và cấu trúc lồng

## 1. Phân biệt ngay từ khai báo

Trong Java, **mảng nguyên thủy** (primitive array) và **mảng lớp bao** (wrapper array) không phải hai cách viết thay thế cho cùng một kiểu. Chúng có kiểu phần tử, cách lưu trữ, giá trị mặc định, khả năng chứa `null` và hành vi so sánh khác nhau.

Ví dụ:

```java
int[] primitive = {1, 2, 3};
Integer[] wrapper = {1, 2, 3};
```

Đây là hai dòng minh họa được đặt trong phạm vi thích hợp như một phương thức Java; chương trình độc lập ở mục 6 sẽ sử dụng cả hai kiểu.

- `int[]` chứa những phần tử kiểu nguyên thủy `int`. Mỗi phần tử là một giá trị số nguyên 32 bit; phần tử không thể là `null`.
- `Integer[]` chứa những **tham chiếu** đến đối tượng kiểu `java.lang.Integer`. Một phần tử có thể tham chiếu đến một `Integer` hoặc bằng `null`.
- Cả hai biến `primitive` và `wrapper` đều là **tham chiếu đến đối tượng mảng**. Bản thân biến mảng có thể bằng `null`; sự khác biệt là **kiểu của từng phần tử bên trong**.
- Java có **autoboxing** giữa `int` và `Integer` trong ngữ cảnh phù hợp, chẳng hạn khi gán `Integer x = 1`. Nhưng Java **không tự động chuyển cả mảng** `int[]` thành `Integer[]`.

Bảng đối chiếu:

| Đặc điểm | `int[]` | `Integer[]` |
| --- | --- | --- |
| Kiểu phần tử | Giá trị nguyên thủy `int` | Tham chiếu `Integer` |
| Phần tử mặc định khi `new ...[n]` | `0` | `null` |
| Phần tử có thể là `null` | Không | Có |
| Bộ nhớ điển hình | Các phần tử `int` được lưu trực tiếp trong mảng | Mảng lưu các tham chiếu; đối tượng `Integer` có thể được lưu riêng |
| Đọc phần tử thành `int` | Trực tiếp | Cần unboxing; có thể lỗi nếu phần tử là `null` |
| Kiểu runtime | `[I` | `[Ljava.lang.Integer;` |
| Dùng `Arrays.equals` theo nội dung | Overload `Arrays.equals(int[], int[])` | Overload `Arrays.equals(Object[], Object[])` |
| Truyền cho `Object[]` | Không | Có |
| Truyền vào `Arrays.asList` | Một phần tử kiểu `int[]` | Một phần tử danh sách cho mỗi `Integer` |
| Dòng stream phù hợp | `IntStream` từ `Arrays.stream(int[])` | `Stream<Integer>` từ `Arrays.stream(Integer[])` |

Tên kiểu runtime dạng `[I` và `[Ljava.lang.Integer;` là biểu diễn tên lớp mảng của JVM; thông thường khi viết mã ứng dụng, nên dùng kiểu khai báo dễ đọc `int[]` và `Integer[]`.

## 2. Vì sao không thể gán trực tiếp, ép kiểu hoặc tự động chuyển cả mảng?

Autoboxing chỉ giúp chuyển **một giá trị** trong ngữ cảnh phù hợp:

```java
int n = 7;
Integer wrapped = n; // boxing: int -> Integer
int again = wrapped; // unboxing: Integer -> int
```

Ngược lại, cả ba dòng bên dưới **không biên dịch** (đưa ra để giải thích lỗi, không nằm trong chương trình hoàn chỉnh):

```java
// Integer[] boxed = new int[] {1, 2, 3}; // incompatible types
// int[] unboxed = new Integer[] {1, 2, 3}; // incompatible types
// Object[] objects = new int[] {1, 2, 3}; // incompatible types
```

Mỗi mảng là một đối tượng có kiểu thành phần riêng, không có luật boxing tự động đi qua toàn bộ các phần tử. Một phép ép kiểu không thể biến đối tượng mảng `int[]` thành đối tượng mảng `Integer[]`.

Cách chuyển đổi có chủ đích:

```java
int[] numbers = {1, 2, 3};
Integer[] boxed = Arrays.stream(numbers)
        .boxed()
        .toArray(Integer[]::new);
```

Đây là đoạn minh họa có thể đặt trong một phương thức khi đã `import java.util.Arrays`. `Arrays.stream(numbers)` tạo `IntStream`; `boxed()` tạo `Stream<Integer>`; `toArray(Integer[]::new)` tạo một mảng `Integer[]` **mới**. Chuyển đổi có chi phí tạo mảng và có thể tạo/cần các đối tượng lớp bao.

Chiều ngược lại cần xử lý được các phần tử `null`:

```java
Integer[] boxed = {1, 2, 3};
int[] numbers = Arrays.stream(boxed)
        .mapToInt(Integer::intValue)
        .toArray();
```

Nếu có phần tử `null`, `Integer::intValue` sẽ gây `NullPointerException` khi chạy. Phải xác định chính sách miền dữ liệu trước khi chuyển: bác bỏ null, lọc bỏ null (có thể làm thay đổi số phần tử), hoặc ánh xạ null thành giá trị được quy ước. Không tự mặc định null tương đương với 0 khi nghiệp vụ không quy định.

## 3. Hợp đồng `equals()`: mảng khác các đối tượng giá trị thông thường

Trong Java, mảng **không ghi đè `Object.equals` theo nội dung**. Vì thế `array1.equals(array2)`, `Objects.equals(array1, array2)` và toán tử `==` đều kiểm tra **cùng tham chiếu**, nếu cả hai đều là những đối tượng mảng khác nhau.

```java
int[] a = {1, 2, 3};
int[] b = {1, 2, 3};

System.out.println(a == b);                 // false
System.out.println(a.equals(b));            // false
System.out.println(Objects.equals(a, b));   // false
System.out.println(Arrays.equals(a, b));    // true
```

Đoạn trên là mã minh họa đặt trong phương thức với `import java.util.*`. Mảng `Integer[]` cũng có **cùng sự khác biệt giữa tham chiếu và nội dung**: hai mảng mới chứa ba giá trị `Integer` giống nhau vẫn là hai **đối tượng mảng** khác nhau.

Muốn so phần tử của **hai mảng một chiều cùng kiểu tương thích**, dùng:

- `Arrays.equals(int[], int[])` đối với mảng `int[]`: từng cặp phần tử `int` so sánh theo giá trị.
- `Arrays.equals(Object[], Object[])` đối với `Integer[]`: từng cặp phần tử được so theo `Objects.equals`; nhờ vậy hai phần tử `Integer` có cùng giá trị được xem là bằng nhau, và hai phần tử `null` cùng vị trí cũng bằng nhau.

**Không có overload `Arrays.equals(int[], Integer[])` để tự boxing từng phần tử.** Lệnh dưới đây không biên dịch:

```java
// Arrays.equals(new int[] {1, 2}, new Integer[] {1, 2});
```

Nếu nghiệp vụ yêu cầu so sánh **giá trị số tương ứng giữa hai kiểu**, cần chuẩn hóa về một dạng trước, ví dụ:

```java
int[] primitive = {1, 2, 3};
Integer[] boxed = {1, 2, 3};
Integer[] converted = Arrays.stream(primitive)
        .boxed()
        .toArray(Integer[]::new);
boolean equivalent = Arrays.equals(converted, boxed); // true
```

Đây là so sánh sau **chuyển đổi tường minh**, không phải hai kiểu mảng vốn bằng nhau theo `equals`. Nếu dữ liệu có null, cần một định nghĩa nghiệp vụ riêng vì `int[]` không biểu diễn được phần tử null.

### Đừng nhầm `Integer.equals` với `==` trên `Integer`

`Integer.equals(Object)` so theo giá trị nguyên, trong khi `==` trên hai biến kiểu `Integer` so cùng tham chiếu. Cơ chế cache đối tượng `Integer` cho một số giá trị có thể khiến `==` có vẻ đúng trong các trường hợp nhất định; không dựa vào đó để kiểm tra giá trị. Với phần tử lớp bao, `Arrays.equals(Integer[], Integer[])` phù hợp vì nó dùng logic bình đẳng của phần tử thay cho so tham chiếu trực tiếp.

## 4. Mảng đa chiều và `Arrays.deepEquals()`

Một mảng hai chiều Java thực chất là **mảng của các mảng**. Cụ thể:

- `int[][]` có kiểu phần tử trực tiếp là `int[]`. **Mảng ngoài** là mảng tham chiếu nên có thể dùng như `Object[]`; **mảng trong** `int[]` vẫn chứa nguyên thủy và không phải `Object[]`.
- `Integer[][]` có phần tử trực tiếp là `Integer[]`; cả mảng ngoài và từng mảng trong đều là mảng tham chiếu.
- `Arrays.equals(int[][], int[][])` dùng overload đối tượng `Object[]`, rồi so các phần tử là `int[]` theo `equals` của mảng (tham chiếu). Nếu các hàng là hai mảng mới có cùng nội dung, kết quả có thể là `false`.
- `Arrays.deepEquals(int[][], int[][])` kiểm tra sâu các mảng con tương ứng, bao gồm so nội dung nguyên thủy bằng overload phù hợp. Nó là lựa chọn đúng khi cần so **cấu trúc lồng** cùng biểu diễn.

Ví dụ:

```java
int[][] a = {{1, 2}, {3, 4}};
int[][] b = {{1, 2}, {3, 4}};

System.out.println(Arrays.equals(a, b));     // false
System.out.println(Arrays.deepEquals(a, b)); // true
```

`Arrays.deepEquals` nhận hai tham số `Object[]`; một `int[][]` truyền vào được vì mảng ngoài chứa các tham chiếu `int[]`. **Một `int[]` đơn lẻ thì không truyền trực tiếp cho `Arrays.deepEquals` được.**

Điều quan trọng trong bài này là so sánh sâu **không tự boxing** giữa phần tử nguyên thủy và lớp bao:

```java
int[][] primitiveNested = {{1, 2}, {3, 4}};
Integer[][] wrapperNested = {{1, 2}, {3, 4}};
System.out.println(
        Arrays.deepEquals(primitiveNested, wrapperNested)); // false
```

Mặc dù nhìn bằng mắt có cùng các con số, các hàng `int[]` và `Integer[]` có kiểu khác nhau và không thể so bằng nhau chỉ nhờ `deepEquals`. Để định nghĩa *equivalence* xuyên kiểu, bạn phải chuyển đổi dữ liệu hoặc viết bộ so sánh rõ quy tắc cho các kiểu đầu vào.

**Hiển thị dữ liệu:** `Arrays.toString(int[])` và `Arrays.toString(Integer[])` đều in phần tử một chiều; với mảng lồng, `Arrays.deepToString(...)` giúp hiển thị nội dung các mảng con thay vì biểu diễn tham chiếu khó đọc.

## 5. Các hệ quả về null, bộ nhớ, generic và collection

### 5.1. Mảng nguyên thủy không có phần tử null

`new int[3]` chứa ba giá trị mặc định `0`. `new Integer[3]` chứa ba **tham chiếu null**. Phép đọc `int x = boxed[0]` thực hiện unboxing; nếu `boxed[0]` là null thì ném `NullPointerException`. Ngược lại, `Arrays.equals(Integer[], Integer[])` có thể so hai mảng cùng null ở vị trí tương ứng mà không cần unbox chúng.

Khi dữ liệu bên ngoài có khái niệm “thiếu giá trị”, mảng wrapper cho phép biểu diễn null nhưng cũng làm tăng yêu cầu kiểm tra dữ liệu. Không dùng `0` để ngầm biểu thị thiếu giá trị nếu 0 là một giá trị hợp lệ trong miền dữ liệu.

### 5.2. Chi phí bộ nhớ và hiệu năng

Một mảng `int[]` lưu giá trị nguyên thủy trực tiếp, thường sử dụng ít bộ nhớ hơn và có tính cục bộ truy cập tốt hơn so với `Integer[]` chứa tham chiếu. `Integer[]` có thể khiến chương trình tạo thêm đối tượng, tăng chi phí boxing/unboxing và áp lực thu gom rác. Tuy nhiên JVM có thể tối ưu hóa hoặc tái sử dụng một số đối tượng wrapper, vì vậy **không kết luận một con số overhead cố định** hoặc một thứ hạng hiệu năng cho mọi workload. Khi lựa chọn ảnh hưởng đáng kể tới hệ thống, đo benchmark với dữ liệu và JVM thực tế.

### 5.3. Mảng tham chiếu và generic

`Integer[]` dùng được ở nơi nhận `Object[]` vì `Integer` là một kiểu tham chiếu con của `Object`. `int[]` **không** dùng được ở nơi nhận `Object[]` vì phần tử `int` là nguyên thủy. Tuy nhiên cả hai đối tượng mảng đều là `Object`, có thể truyền vào tham số `Object`.

`List<Integer>` nhận các phần tử `Integer`; Java generic không chấp nhận nguyên thủy làm tham số kiểu, ví dụ `List<int>` không hợp lệ. Bạn có thể dùng `Integer[]` hoặc `List<Integer>` khi API đòi kiểu tham chiếu, và dùng `int[]` khi thao tác số lượng lớn với dữ liệu nguyên thủy mà không cần null.

Mảng tham chiếu có tính hiệp biến (*covariant*): `Integer[]` có thể gán vào `Object[]`, nhưng nếu thử ghi một `String` vào đó qua tham chiếu `Object[]`, Java sẽ ném `ArrayStoreException` ở runtime. Tính hiệp biến này **không áp dụng** để biến `int[]` thành `Object[]`.

### 5.4. `Arrays.asList()` là bẫy thường gặp

`Arrays.asList` là phương thức varargs dùng kiểu tham chiếu. Do đó:

```java
int[] raw = {1, 2, 3};
Integer[] boxed = {1, 2, 3};

System.out.println(Arrays.asList(raw).size());   // 1
System.out.println(Arrays.asList(boxed).size()); // 3
```

Với `raw`, toàn bộ đối tượng `int[]` trở thành **một phần tử** trong `List<int[]>`; không hề có tự động boxing ba số. Với `boxed`, mỗi phần tử mảng trở thành một phần tử `List<Integer>`. Danh sách do `Arrays.asList` trả về có độ dài cố định và được hỗ trợ bởi mảng đầu vào; nếu cần danh sách có thể thêm/xóa phần tử, tạo một danh sách phù hợp khác.

Để tạo danh sách các số từ mảng nguyên thủy:

```java
List<Integer> list = Arrays.stream(raw).boxed().toList();
```

Đoạn này dùng Java 17 (API `Stream.toList()` có từ Java 16), cần `import java.util.*`. Kết quả là danh sách không cho phép sửa cấu trúc/nội dung bằng các thao tác mutator của `List`; nếu cần danh sách có thể thay đổi, có thể dùng `new ArrayList<>(list)`.

## 6. Chương trình Java 17+ đầy đủ và kết quả kiểm chứng

Lưu toàn bộ mã dưới đây dưới tên **`PrimitiveWrapperArraysDemo.java`**; ví dụ tập trung vào kiểu runtime, hợp đồng bình đẳng của mảng, so sánh sâu và các khác biệt thường gây lỗi.

```java
import java.util.*;

public class PrimitiveWrapperArraysDemo {
    public static void main(String[] args) {
        int[] raw = {1, 2, 3};
        int[] rawCopy = {1, 2, 3};
        Integer[] boxed = {1, 2, 3};
        Integer[] boxedCopy = {1, 2, 3};

        System.out.println("primitive class = " + raw.getClass().getName());
        System.out.println("wrapper class = " + boxed.getClass().getName());
        System.out.println("primitive is Object = " + (raw instanceof Object));
        System.out.println("primitive is Object[] = "
                + (((Object) raw) instanceof Object[]));
        System.out.println("wrapper is Object[] = " + (boxed instanceof Object[]));

        System.out.println("primitive content equal = "
                + Arrays.equals(raw, rawCopy));
        System.out.println("wrapper content equal = "
                + Arrays.equals(boxed, boxedCopy));
        System.out.println("Objects.equals primitive arrays = "
                + Objects.equals(raw, rawCopy));
        System.out.println("Objects.equals wrapper arrays = "
                + Objects.equals(boxed, boxedCopy));
        System.out.println("mixed deep equality = "
                + Arrays.deepEquals(new Object[] {raw}, new Object[] {boxed}));
        System.out.println("primitive content = " + Arrays.toString(raw));
        System.out.println("wrapper content = " + Arrays.toString(boxed));

        Integer[] converted = Arrays.stream(raw)
                .boxed()
                .toArray(Integer[]::new);
        System.out.println("converted content = "
                + Arrays.toString(converted));
        System.out.println("after conversion equal = "
                + Arrays.equals(converted, boxed));

        Integer[] withNull = {1, null, 3};
        System.out.println("wrapper with null = " + Arrays.toString(withNull));
        System.out.println("wrapper null equal = "
                + Arrays.equals(withNull, new Integer[] {1, null, 3}));
        try {
            int item = withNull[1];
            System.out.println(item);
        } catch (NullPointerException exception) {
            System.out.println("unboxing null = NullPointerException");
        }

        int[][] primitiveNested = {{1, 2}, {3, 4}};
        Integer[][] wrapperNested = {{1, 2}, {3, 4}};
        System.out.println("primitive nested is Object[] = "
                + (((Object) primitiveNested) instanceof Object[]));
        System.out.println("primitive deep equal = "
                + Arrays.deepEquals(
                        primitiveNested, new int[][] {{1, 2}, {3, 4}}));
        System.out.println("wrapper deep equal = "
                + Arrays.deepEquals(
                        wrapperNested, new Integer[][] {{1, 2}, {3, 4}}));
        System.out.println("nested cross-type deep equal = "
                + Arrays.deepEquals(primitiveNested, wrapperNested));

        System.out.println("asList primitive size = "
                + Arrays.asList(raw).size());
        System.out.println("asList wrapper size = "
                + Arrays.asList(boxed).size());
    }
}
```

Chạy từ thư mục chứa tệp:

```bash
javac PrimitiveWrapperArraysDemo.java
java PrimitiveWrapperArraysDemo
```

Kết quả:

```text
primitive class = [I
wrapper class = [Ljava.lang.Integer;
primitive is Object = true
primitive is Object[] = false
wrapper is Object[] = true
primitive content equal = true
wrapper content equal = true
Objects.equals primitive arrays = false
Objects.equals wrapper arrays = false
mixed deep equality = false
primitive content = [1, 2, 3]
wrapper content = [1, 2, 3]
converted content = [1, 2, 3]
after conversion equal = true
wrapper with null = [1, null, 3]
wrapper null equal = true
unboxing null = NullPointerException
primitive nested is Object[] = true
primitive deep equal = true
wrapper deep equal = true
nested cross-type deep equal = false
asList primitive size = 1
asList wrapper size = 3
```

Nhìn vào phần output:

1. `primitive class` và `wrapper class` chứng minh hai **kiểu mảng runtime** khác nhau, dù cùng ba giá trị số.
2. `raw` là một `Object` nhưng **không** là `Object[]`; `boxed` là `Object[]`. Phép thử với `raw` được ép lên `Object` trước khi dùng `instanceof Object[]` để đây là một biểu thức Java hợp lệ có kết quả `false`.
3. Hai cặp mảng riêng biệt bằng nhau theo **nội dung** với `Arrays.equals`, nhưng khác nhau theo `Objects.equals` vì đó không phải cùng đối tượng.
4. So sánh sâu giữa `new Object[]{raw}` và `new Object[]{boxed}` là `false`; dữ liệu mảng nguyên thủy không được tự động boxing trong thuật toán so sánh sâu.
5. Sau khi chuyển `raw` thành `Integer[]` mới, `Arrays.equals(converted, boxed)` là `true`: chuyển đổi làm hai bên có cùng **kiểu biểu diễn thích hợp** cho phép so nội dung.
6. `Integer[]` chứa `null` hợp lệ và có thể so bằng `Arrays.equals`, nhưng đọc phần tử null thành `int` sẽ ném `NullPointerException`.
7. `int[][]` dùng được như `Object[]` ở **tầng ngoài**. `Arrays.deepEquals` là `true` khi so hai ma trận nguyên thủy tương ứng, hoặc hai ma trận wrapper tương ứng; so chéo hai biểu diễn vẫn `false`.
8. `Arrays.asList(raw)` có kích thước 1; `Arrays.asList(boxed)` có kích thước 3. Đây là khác biệt về phần tử varargs, không phải dữ liệu bị mất.

## 7. Chọn phương thức so sánh đúng trong bài toán thực tế

| Bạn muốn kiểm tra | API nên dùng | Ghi chú |
| --- | --- | --- |
| Hai tham chiếu có trỏ cùng đối tượng mảng? | `a == b` hoặc `Objects.equals(a, b)` | Đối với mảng, `Objects.equals` vẫn so tham chiếu |
| Hai `int[]` cùng dãy số? | `Arrays.equals(a, b)` | So từng giá trị nguyên thủy |
| Hai `Integer[]` cùng dãy giá trị, kể cả null? | `Arrays.equals(a, b)` | Phần tử dùng bình đẳng kiểu đối tượng; null được xử lý |
| Hai `int[][]` hoặc `Integer[][]` có nội dung lồng tương ứng? | `Arrays.deepEquals(a, b)` | Dùng ở cấp mảng ngoài của mảng lồng |
| Một `int[]` và một `Integer[]` thể hiện cùng dãy số? | Chuyển về cùng kiểu rồi `Arrays.equals` | Xác định cách xử lý null trước khi so |
| Hiển thị mảng một chiều | `Arrays.toString(array)` | Tránh `array.toString()` |
| Hiển thị mảng lồng | `Arrays.deepToString(array)` | Hiển thị nội dung của mảng con |
| Tạo `List<Integer>` từ `int[]` | `Arrays.stream(raw).boxed().toList()` | Không dùng `Arrays.asList(raw)` nếu muốn một phần tử list cho mỗi số |

## 8. Lỗi phổ biến và cách tự kiểm chứng

1. **Tin rằng autoboxing áp dụng cho cả mảng:** `Integer[] b = intArray` là sai kiểu. Phải tạo mảng mới và chuyển từng phần tử.
2. **Gọi `Objects.equals` hoặc `array.equals` để so nội dung:** với cả hai loại mảng, nó vẫn so cùng tham chiếu. Dùng `Arrays.equals` cho mảng một chiều.
3. **Dùng `Arrays.equals` cho mảng hai chiều và mong so sâu:** phần tử trực tiếp của mảng ngoài là tham chiếu mảng con; với hai ma trận riêng biệt thường cần `Arrays.deepEquals`.
4. **Mong `Arrays.deepEquals` tự quy đổi `int[]` thành `Integer[]`:** hàm không thực hiện chuyển đổi kiểu số nguyên như vậy. Cần chuẩn hóa rõ ràng.
5. **Bỏ quên null trong `Integer[]`:** unboxing null ném `NullPointerException`; mảng nguyên thủy không có phần tử null.
6. **Nhầm `Arrays.asList(int[])` với danh sách từng số:** nó tạo danh sách một phần tử `int[]`. Dùng stream `boxed()` hoặc chuyển sang wrapper trước.
7. **Dùng `==` trên hai đối tượng `Integer` để so giá trị:** đó là so tham chiếu và có thể phụ thuộc caching. Dùng `Objects.equals`/`Integer.equals` khi cần bình đẳng giá trị.
8. **Dùng giả định mọi phần tử `Integer[]` được tạo riêng:** caching, autoboxing và tối ưu JVM có thể ảnh hưởng identity; đừng xây hợp đồng bằng nhau dựa trên cách tạo instance wrapper.

**Tự kiểm tra:** Xét `int[][] a = {{1, 2}}`, `int[][] b = {{1, 2}}` và `Integer[][] c = {{1, 2}}`. Tại sao `Arrays.equals(a, b)` có thể là `false` nhưng `Arrays.deepEquals(a, b)` là `true`, còn `Arrays.deepEquals(a, c)` lại là `false`? Vì `Arrays.equals` ở mảng ngoài so hai tham chiếu `int[]` là hai đối tượng khác nhau; `deepEquals` đi vào nội dung của hai mảng `int[]` tương ứng; nhưng nó **không tự boxing** một hàng `int[]` thành `Integer[]` khi so xuyên kiểu.

Điểm cốt lõi: `int[]` và `Integer[]` có thể trông giống nhau khi in ra, nhưng **khác kiểu dữ liệu và hợp đồng thao tác**. Chọn mảng nguyên thủy khi cần giá trị không-null và thao tác số trực tiếp; chọn mảng lớp bao khi API cần đối tượng, generic hoặc cần biểu diễn null. Khi so sánh, phân biệt rõ **bình đẳng tham chiếu**, **bình đẳng nội dung một chiều**, **bình đẳng sâu của cấu trúc lồng** và **bình đẳng sau chuyển đổi tường minh**.