# Kiểu mảng với `Object`, `Cloneable` và `Serializable` trong Java

## 1. Mục tiêu và mô hình kiểu

Trong Java, mảng (`array`) là **đối tượng** được tạo ở runtime, đồng thời mỗi mảng có một **kiểu lớp mảng** riêng. Dù phần tử là kiểu nguyên thủy như `int` hay kiểu tham chiếu như `String`, bản thân biến mảng luôn chứa tham chiếu đến một đối tượng mảng (hoặc `null`).

Một lớp mảng bất kỳ đều có các quan hệ sau:

- Có `java.lang.Object` là **lớp cha trực tiếp**.
- Triển khai trực tiếp hai giao diện đánh dấu `java.lang.Cloneable` và `java.io.Serializable`.
- Có thể gán cho biến kiểu `Object`, `Cloneable` hoặc `Serializable` mà không cần ép kiểu.
- Có thể truy vấn qua `Class<?>`, chẳng hạn `isArray()`, `getComponentType()`, `getSuperclass()`, `getInterfaces()` và `isAssignableFrom()`.

Ví dụ, các phép gán sau đều hợp lệ:

```java
int[] numbers = {1, 2, 3};
String[] names = {"An", "Bình"};

Object first = numbers;
Object second = names;
Cloneable cloneable = numbers;
Serializable serializable = names;
```

Để biên dịch ví dụ này trong một lớp độc lập, thêm `import java.io.Serializable;`. `Cloneable` thuộc `java.lang` nên không cần import.

Điểm cần nhớ: *mảng là đối tượng* không đồng nghĩa *mảng nào cũng là `Object[]`*. `Object` là lớp cha của mọi lớp mảng; còn `Object[]` là một **kiểu mảng có phần tử kiểu `Object`**, nên tuân theo các quy tắc tương thích phần tử khác.

## 2. Hiểu đúng quan hệ với `Object`

Khai báo `int[]`, `String[]` và `int[][]` đều biểu thị kiểu tham chiếu. Vì vậy, chúng đều là subtype của `Object`:

```java
Object a = new int[3];
Object b = new String[3];
Object c = new int[2][3];

System.out.println(a instanceof Object); // true
System.out.println(b instanceof Object); // true
System.out.println(c instanceof Object); // true
```

Ví dụ trên là **đoạn mã minh họa**, có thể đặt trong phương thức `main`.

Ở runtime, `new int[3]` tạo một đối tượng mảng và điền phần tử bằng giá trị mặc định `0`. `new String[3]` tạo một đối tượng mảng mà từng phần tử ban đầu là `null`. Việc đối tượng mảng thuộc `Object` không làm biến đổi kiểu phần tử.

Mọi lớp mảng đều trả về `Object.class` khi gọi `getSuperclass()`. Tuy nhiên, lớp mảng không phải lớp Java do lập trình viên khai báo bằng `extends Object`, và không thể khai báo một lớp con tùy ý kế thừa từ `int[]` hay `String[]`. JVM tạo các lớp mảng theo nhu cầu và Java không cho phép khai báo lớp kế thừa từ kiểu mảng.

### Vì sao `int[]` không gán được cho `Object[]`?

`Object[]` chứa các **tham chiếu đối tượng**; `int[]` chứa các giá trị `int` nguyên thủy. Do đó:

```java
int[] values = {1, 2};
Object anything = values;        // Hợp lệ
// Object[] bad = values;       // LỖI BIÊN DỊCH
```

Phép chuyển từ `int[]` sang `Object[]` không trở nên hợp lệ bằng cách ép kiểu trực tiếp. Nếu đưa một `int[]` vào biến `Object` rồi ép thành `Object[]`, chương trình sẽ ném `ClassCastException` tại runtime. Muốn một mảng phần tử tham chiếu, phải tạo kiểu phù hợp, ví dụ `Integer[]`, và chuyển các phần tử một cách tường minh khi cần.

Ngược lại, `String[]` **có thể** gán cho `Object[]`, vì `String` là subtype của `Object`:

```java
String[] strings = {"a", "b"};
Object[] objects = strings;      // Hợp lệ
System.out.println(objects[0]); // a
```

Quy tắc này được gọi là **hiệp biến của mảng tham chiếu** (array covariance), được xét kỹ ở mục 5.

## 3. Quan hệ với `Cloneable`: sao chép mảng

Mọi đối tượng mảng triển khai `Cloneable` và hỗ trợ gọi `clone()` trên biểu thức kiểu mảng. Phép clone tạo **đối tượng mảng mới cùng kiểu runtime, cùng độ dài**, sau đó sao chép giá trị của từng phần tử.

- Với mảng nguyên thủy như `int[]`, mỗi giá trị nguyên thủy được sao chép.
- Với mảng tham chiếu như `StringBuilder[]`, từng **tham chiếu** được sao chép; đối tượng được tham chiếu không được sao chép đệ quy.
- Với mảng nhiều chiều như `int[][]`, chỉ **mảng ngoài** được clone; các mảng con vẫn được hai mảng ngoài cùng tham chiếu. Đây là **shallow copy**.
- `clone()` của mảng trả về đúng kiểu mảng ở thời điểm biên dịch, ví dụ `int[] copy = original.clone();`, không cần ép kiểu.

Ví dụ:

```java
int[] original = {1, 2};
int[] copy = original.clone();
copy[0] = 99;

System.out.println(original[0]); // 1
System.out.println(copy[0]);     // 99

int[][] matrix = {{1, 2}, {3, 4}};
int[][] shallow = matrix.clone();
shallow[0][0] = 99;

System.out.println(matrix[0][0]); // 99
System.out.println(matrix == shallow); // false
System.out.println(matrix[0] == shallow[0]); // true
```

Đây là đoạn minh họa đặt trong `main`. Để sao chép độc lập từng hàng của `int[][]`, cần tự clone từng mảng con (hoặc áp dụng thuật toán sao chép sâu phù hợp với cấu trúc dữ liệu).

**Giới hạn của `Cloneable`:** Gán `int[]` cho biến `Cloneable` chỉ chứng minh đối tượng có giao diện đánh dấu. Giao diện `Cloneable` **không khai báo phương thức `clone()`**. Vì vậy `Cloneable marker = numbers; marker.clone();` không biên dịch; cần giữ hoặc lấy lại kiểu mảng thích hợp. `Object.clone()` là phương thức `protected`, còn cú pháp gọi `clone()` trên kiểu mảng được ngôn ngữ Java cho phép một cách đặc biệt.

## 4. Quan hệ với `Serializable`: khả năng tuần tự hóa

`Serializable` cũng là **marker interface**, không khai báo phương thức. Các kiểu mảng như `int[]`, `String[]` và `Object[]` đều triển khai `Serializable`, bất kể kiểu phần tử của chúng.

Điều này cho phép cơ chế Java Object Serialization xử lý một đối tượng mảng. Tuy nhiên, để **ghi thành công một mảng tham chiếu có phần tử không null**, mỗi đối tượng phần tử được ghi cùng đồ thị đối tượng cần hỗ trợ tuần tự hóa theo hợp đồng của cơ chế này:

- `int[]` có thể tuần tự hóa các giá trị `int`.
- `String[]` chứa các `String` có thể tuần tự hóa vì `String` triển khai `Serializable`.
- Một mảng chứa đối tượng của lớp không triển khai `Serializable` có thể ném `NotSerializableException` trong quá trình `ObjectOutputStream.writeObject(...)`.
- Mảng có kiểu thành phần là lớp không serializable **vẫn là một đối tượng `Serializable`**; chẳng hạn mảng rỗng hoặc các phần tử đều `null` có thể ghi thành công vì không có đối tượng phần tử không serializable phải ghi.

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.NotSerializableException;
import java.io.ObjectOutputStream;

public class ArraySerializationDemo {
    static class PlainItem {
        int value = 1;
    }

    private static void write(Object value) throws IOException {
        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(value);
        }
    }

    public static void main(String[] args) throws IOException {
        write(new int[] {1, 2});
        System.out.println("int[]: OK");

        write(new PlainItem[0]);
        System.out.println("PlainItem[0]: OK");

        try {
            write(new PlainItem[] {new PlainItem()});
        } catch (NotSerializableException e) {
            System.out.println("PlainItem[1]: NotSerializableException");
        }
    }
}
```

Lưu tệp `ArraySerializationDemo.java`, chạy bằng Java 17 trở lên:

```bash
javac ArraySerializationDemo.java
java ArraySerializationDemo
```

Kết quả:

```text
int[]: OK
PlainItem[0]: OK
PlainItem[1]: NotSerializableException
```

`Serializable` chỉ thể hiện khả năng tham gia cơ chế serialization; **không bảo đảm mọi nội dung cụ thể đều tuần tự hóa được**. Serialization gốc của Java còn liên quan đến tương thích phiên bản, an toàn dữ liệu và rủi ro giải tuần tự hóa dữ liệu không tin cậy; không nên dùng nó làm định dạng trao đổi dữ liệu mở mặc định.

## 5. Quy tắc gán kiểu giữa các loại mảng

### 5.1. Mảng nguyên thủy và mảng tham chiếu

| Kiểu nguồn | Kiểu đích | Gán trực tiếp? | Lý do |
| --- | --- | --- | --- |
| `int[]` | `Object` | Có | Mọi mảng là đối tượng |
| `int[]` | `Cloneable` | Có | Mọi mảng triển khai marker interface này |
| `int[]` | `Serializable` | Có | Mọi mảng triển khai marker interface này |
| `int[]` | `Object[]` | Không | `int` không phải kiểu tham chiếu `Object` |
| `String[]` | `Object[]` | Có | Mảng tham chiếu hiệp biến; `String <: Object` |
| `Integer[]` | `Number[]` | Có | Mảng tham chiếu hiệp biến; `Integer <: Number` |
| `int[]` | `long[]` | Không | Không có phép mở rộng kiểu nguyên thủy áp dụng cho **toàn mảng** |
| `int[][]` | `Object[]` | Có | Phần tử của mảng ngoài là `int[]`, một kiểu tham chiếu thuộc `Object` |
| `int[][]` | `Cloneable[]` | Có | Phần tử `int[]` triển khai `Cloneable` |
| `int[][]` | `Object[][]` | Không | `int[]` không phải subtype của `Object[]` |

Ký hiệu `A <: B` ở đây nghĩa là `A` là subtype của `B`.

### 5.2. Hiệp biến không làm mất kiểm tra kiểu runtime

Java cho phép `String[]` được nhìn qua biến `Object[]`. Nhưng đối tượng thực tế vẫn là `String[]`. Nếu cố lưu `Integer` vào đó, JVM ném `ArrayStoreException`:

```java
String[] words = {"Java"};
Object[] array = words;          // Được phép
// array[0] = Integer.valueOf(7); // Biên dịch được, nhưng ném ArrayStoreException
```

Chính xác hơn, câu lệnh ghi ở trên **biên dịch được** do kiểu tĩnh của `array` là `Object[]`; lỗi chỉ phát sinh khi thực thi, do phần tử của mảng runtime chỉ nhận `String` (và `null`).

Mảng là reifiable: thông tin kiểu phần tử của một đối tượng mảng được runtime giữ để kiểm tra phép ghi. Quy tắc này khác với cơ chế xóa kiểu của Java generics; không được suy luận rằng `List<String>` hoạt động giống `String[]`. Việc tạo trực tiếp mảng có kiểu phần tử parameterized không reifiable như `new List<String>[10]` cũng bị Java từ chối khi biên dịch.

### 5.3. Mảng nhiều chiều là mảng chứa mảng

`int[][]` là mảng mà **mỗi phần tử có kiểu `int[]`**. Vì thế, bản thân `int[][]` là một mảng tham chiếu và có thể gán cho `Object[]`, dù các phần tử cuối cùng là giá trị nguyên thủy.

```java
int[][] grid = {{10, 20}, {30}};
Object[] outer = grid;

System.out.println(outer[0] instanceof int[]); // true
System.out.println(((int[]) outer[0])[1]);       // 20
```

Điều đó **không** khiến `int[][]` trở thành `Object[][]`. Để là `Object[][]`, phần tử của mảng ngoài phải tương thích với `Object[]`; còn `int[]` không phải subtype của `Object[]`.

## 6. Kiểm tra bằng Java Reflection

Các API của `java.lang.Class` giúp kiểm tra quan hệ kiểu mà không cần tạo đối tượng:

- `SomeArray.class.isArray()`: kiểm tra đối tượng `Class` biểu diễn kiểu mảng.
- `getComponentType()`: trả về `Class` của kiểu phần tử trực tiếp; với `int[][]`, kết quả là `int[].class`, không phải `int.class`.
- `getSuperclass()`: trả về `Object.class` đối với mọi lớp mảng.
- `getInterfaces()`: đối với lớp mảng trả về `Cloneable` và `Serializable`. Không nên phụ thuộc vào **thứ tự** trả về khi in kết quả.
- `Destination.class.isAssignableFrom(Source.class)`: `true` nếu giá trị có kiểu `Source` gán được cho biến `Destination` bằng phép gán mở rộng hoặc đồng nhất cho kiểu tham chiếu; thứ tự đối số là **đích.isAssignableFrom(nguồn)**.
- `getTypeName()`: hiển thị tên thân thiện, ví dụ `int[]`, `java.lang.String[]`. `getName()` của lớp mảng dùng dạng ký hiệu JVM như `[I` và `[Ljava.lang.String;`, không phải cú pháp mã nguồn thông thường.

Ví dụ hoàn chỉnh:

```java
import java.io.Serializable;
import java.util.Arrays;
import java.util.stream.Collectors;

public class ArrayTypeRelationsDemo {
    public static void main(String[] args) {
        Class<?> arrayClass = int[].class;

        System.out.println("Superclass: " + arrayClass.getSuperclass().getTypeName());
        String interfaces = Arrays.stream(arrayClass.getInterfaces())
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(", "));
        System.out.println("Interfaces: " + interfaces);

        System.out.println("int[] -> Object: "
                + Object.class.isAssignableFrom(int[].class));
        System.out.println("int[] -> Cloneable: "
                + Cloneable.class.isAssignableFrom(int[].class));
        System.out.println("int[] -> Serializable: "
                + Serializable.class.isAssignableFrom(int[].class));
        System.out.println("int[] -> Object[]: "
                + Object[].class.isAssignableFrom(int[].class));
        System.out.println("String[] -> Object[]: "
                + Object[].class.isAssignableFrom(String[].class));
        System.out.println("int[][] -> Object[]: "
                + Object[].class.isAssignableFrom(int[][].class));
        System.out.println("int[][] -> Object[][]: "
                + Object[][].class.isAssignableFrom(int[][].class));
        System.out.println("int[][] component: "
                + int[][].class.getComponentType().getTypeName());

        String[] words = {"Java"};
        Object[] aliases = words;
        try {
            aliases[0] = Integer.valueOf(7);
        } catch (ArrayStoreException e) {
            System.out.println("Checked store: ArrayStoreException");
        }

        int[][] matrix = {{1, 2}};
        int[][] shallow = matrix.clone();
        shallow[0][0] = 99;
        System.out.println("Shallow clone shares row: " + (matrix[0][0] == 99));
    }
}
```

Lưu tệp `ArrayTypeRelationsDemo.java`. Trong thư mục chứa tệp, thực hiện:

```bash
javac ArrayTypeRelationsDemo.java
java ArrayTypeRelationsDemo
```

Stdout mong đợi trên Java 17+:

```text
Superclass: java.lang.Object
Interfaces: Cloneable, Serializable
int[] -> Object: true
int[] -> Cloneable: true
int[] -> Serializable: true
int[] -> Object[]: false
String[] -> Object[]: true
int[][] -> Object[]: true
int[][] -> Object[][]: false
int[][] component: int[]
Checked store: ArrayStoreException
Shallow clone shares row: true
```

Vì đã sắp xếp tên giao diện trước khi in, ví dụ không dựa vào thứ tự `Class.getInterfaces()`.

## 7. Phân biệt các câu hỏi Reflection dễ nhầm

| Câu hỏi | API nên dùng | Ví dụ |
| --- | --- | --- |
| Đây có phải kiểu mảng? | `type.isArray()` | `int[].class.isArray() == true` |
| Phần tử trực tiếp có kiểu nào? | `type.getComponentType()` | `int[][].class.getComponentType() == int[].class` |
| Lớp cha trực tiếp của mảng là gì? | `type.getSuperclass()` | `String[].class.getSuperclass() == Object.class` |
| Mảng triển khai trực tiếp giao diện nào? | `type.getInterfaces()` | `Cloneable` và `Serializable` |
| Một giá trị kiểu A có gán được vào biến kiểu B? | `B.class.isAssignableFrom(A.class)` | `Object[].class.isAssignableFrom(String[].class) == true` |
| Một đối tượng cụ thể có thuộc kiểu cho trước? | `type.isInstance(value)` | `Object[].class.isInstance(new int[1]) == false` |

`isAssignableFrom` hoạt động với đối tượng `Class`, còn `isInstance` kiểm tra một **đối tượng runtime**. Đừng đảo chiều `isAssignableFrom`: `Object.class.isAssignableFrom(int[].class)` là `true`, nhưng `int[].class.isAssignableFrom(Object.class)` là `false`.

Cũng cần tách biệt `instanceof Object` với `instanceof Object[]`. Ví dụ `new int[1] instanceof Object` là đúng, nhưng phép kiểm tra xem đó có phải `Object[]` thì sai. Khi cần kiểm tra động mà kiểu biểu thức cố định khiến phép `instanceof` không hợp lệ ở biên dịch, hãy dùng `Class.isInstance(...)` trên một giá trị đã được nhìn qua `Object`.

## 8. Lỗi thường gặp và cách tự kiểm tra

1. **Cho rằng mảng nguyên thủy không phải đối tượng.** Thực tế, `int[]` là đối tượng và có thể gán cho `Object`, `Cloneable` và `Serializable`.
2. **Đồng nhất `Object` với `Object[]`.** `Object[]` có quy tắc tương thích kiểu phần tử; `int[]` không chuyển thành `Object[]`.
3. **Xem `Cloneable` là cam kết sao chép sâu.** Clone của mảng là sao chép nông; mảng con và các đối tượng tham chiếu vẫn được dùng chung.
4. **Gọi `clone()` qua biến `Cloneable`.** Giao diện đánh dấu này không khai báo `clone()`.
5. **Cho rằng `Serializable` bảo đảm luôn ghi mảng thành công.** Khi serializing, các phần tử không serializable vẫn có thể gây `NotSerializableException`.
6. **Bỏ qua `ArrayStoreException`.** Hiệp biến cho phép phép gán kiểu rộng ở compile time, nhưng JVM kiểm tra kiểu phần tử khi ghi.
7. **Đảo chiều `isAssignableFrom`.** Luôn đọc `ĐÍCH.isAssignableFrom(NGUỒN)`.
8. **Nhầm mảng nhiều chiều với mảng nguyên thủy một chiều.** `int[][]` là mảng ngoài chứa các tham chiếu `int[]`, nên có thể là `Object[]`; còn `int[]` thì không.
9. **Cho rằng `getComponentType()` trả về kiểu phần tử sâu nhất.** Với `String[][][]`, gọi một lần chỉ được `String[][]`; lặp lại mới đi sâu tới `String`.

### Bài tự kiểm tra

Không chạy code ngay: hãy dự đoán rồi dùng `Class.isAssignableFrom` hoặc `Class.isInstance` để kiểm chứng.

```java
Object.class.isAssignableFrom(byte[].class)          // ?
Object[].class.isAssignableFrom(byte[][].class)      // ?
Serializable.class.isAssignableFrom(int[][].class)  // ?
Cloneable[].class.isAssignableFrom(int[][].class)    // ?
Object[][].class.isAssignableFrom(String[][].class)  // ?
Object[][].class.isAssignableFrom(int[][].class)     // ?
```

Đáp án lần lượt: **true, true, true, true, true, false**. Giải thích: mọi mảng là `Object` và triển khai hai marker interface; mảng ngoài của `byte[][]`/`int[][]` chứa đối tượng mảng `byte[]`/`int[]`; `String[]` là subtype của `Object[]`, còn `int[]` thì không.

## 9. Ghi nhớ

Quy tắc gốc là **mọi lớp mảng đều có superclass `Object` và triển khai `Cloneable`, `Serializable`**. Khi hỏi mảng có gán được cho một **kiểu mảng khác** hay không, phải xét thêm kiểu phần tử, phân biệt mảng nguyên thủy, mảng tham chiếu và từng chiều của mảng nhiều chiều. Khi thao tác với dữ liệu, nhớ `clone()` là shallow copy, serialization còn phụ thuộc đối tượng phần tử, và việc ghi vào mảng hiệp biến luôn được JVM kiểm tra ở runtime.