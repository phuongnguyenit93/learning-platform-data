# Tên mảng, component type và `Class.descriptorString()` trong Java Reflection

## 1. Vì sao tên kiểu mảng khác tên lớp thông thường?

Trong Reflection, mỗi kiểu Java có đối tượng `Class<?>` đại diện tại runtime, kể cả kiểu nguyên thủy (`int.class`), lớp (`String.class`) và **kiểu mảng** (`int[].class`, `String[][].class`). Một kiểu mảng là một kiểu riêng: `int[].class != int.class`; hai mảng `new int[2]` và `new int[10]` có **cùng** `Class` vì độ dài thuộc từng đối tượng mảng, không thuộc định danh kiểu.

Java dùng một số cách viết tên kiểu cho những mục đích khác nhau:

- **Cú pháp nguồn Java**: `java.lang.String[][]` hoặc `String[][]`.
- **Tên do `Class.getName()` trả về**: mảng dùng dạng bắt đầu bằng `[` và tên lớp tham chiếu dùng dấu chấm, ví dụ `[[Ljava.lang.String;`.
- **JVM type descriptor** từ `Class.descriptorString()`: mảng vẫn bắt đầu bằng `[` nhưng tên lớp tham chiếu dùng dấu gạch chéo, ví dụ `[[Ljava/lang/String;`.

Không hoán đổi ba dạng tên này một cách máy móc. Chúng phục vụ hiển thị, tra cứu `Class` hoặc mô tả kiểu theo quy tắc JVM khác nhau.

## 2. Component type khác element type

Một mảng đa chiều trong Java thực chất là **mảng chứa các mảng khác**. Với `String[][][]`:

```text
String[][][]                   // kiểu mảng ba chiều
  └── component: String[][]   // kiểu của một phần tử ở chiều ngoài cùng
        └── component: String[]
              └── component: String
                    └── không còn là mảng
```

- **Component type** là kiểu thành phần trực tiếp của **một cấp mảng**. `String[][][].class.getComponentType() == String[][].class`.
- **Element type** (kiểu phần tử cơ sở) là kiểu thu được khi bỏ hết các chiều mảng. Với `String[][][]`, đó là `String.class`.
- `getComponentType()` trả về `null` nếu đối tượng `Class` không biểu diễn mảng, bao gồm lớp thông thường, `int.class` và `void.class`. Luôn kiểm tra `isArray()` trước khi duyệt nhiều cấp.
- `Class.componentType()` (Java 12+) có cùng hành vi với `getComponentType()`. `Class.arrayType()` (Java 12+) làm chiều ngược lại: `String.class.arrayType() == String[].class`.

Đặc điểm quan trọng: `new int[2][]` có kiểu `int[][]` dù chưa tạo các mảng con; thông tin `Class` chỉ cho biết **kiểu**, không cho biết các nhánh đã được cấp phát hay mỗi nhánh dài bao nhiêu.

## 3. Các API tên và định danh kiểu cần phân biệt

| API trên `Class<?>` | Dùng để làm gì? | Với `String[][].class` |
| --- | --- | --- |
| `isArray()` | Kiểm tra có phải kiểu mảng | `true` |
| `getComponentType()` | Kiểu ở **một chiều** phía trong | `String[].class` |
| `getName()` | Tên lớp/kiểu theo quy tắc của `Class`; mảng dùng tên mã hóa | `[[Ljava.lang.String;` |
| `getTypeName()` | Tên dễ đọc, mô tả kiểu | `java.lang.String[][]` |
| `getSimpleName()` | Tên đơn giản, bỏ tên package ở ví dụ thông thường | `String[][]` |
| `getCanonicalName()` | Tên chuẩn dạng nguồn Java, nếu tồn tại | `java.lang.String[][]` |
| `descriptorString()` | Descriptor theo cú pháp JVM | `[[Ljava/lang/String;` |

Với lớp thường, `getName()` trả về **binary name** (`java.lang.String`, `java.util.Map$Entry`), trong khi `getCanonicalName()` của lớp thành viên có thể là `java.util.Map.Entry`. `getCanonicalName()` có thể trả về `null` cho lớp local/anonymous và mảng có kiểu phần tử cơ sở như vậy; `getSimpleName()` cũng không phải định danh toàn cục đáng tin cậy. Những tên thuận tiện cho giao diện (`getSimpleName()`, `getTypeName()`) không phải lúc nào cũng phù hợp để tải lớp.

## 4. Quy tắc của descriptor JVM

Descriptor mô tả **kiểu** một cách ngắn gọn. Các mã primitive:

| Java type | Descriptor | Java type | Descriptor |
| --- | --- | --- | --- |
| `boolean` | `Z` | `byte` | `B` |
| `char` | `C` | `short` | `S` |
| `int` | `I` | `long` | `J` |
| `float` | `F` | `double` | `D` |
| `void` | `V` | | |

`V` biểu diễn `void` nhưng `void` không thể là kiểu phần tử mảng. Với lớp hoặc interface tham chiếu, dạng là **`L<tên-nội-bộ>;`**: tên nội bộ dùng `/` giữa các package, ví dụ `Ljava/lang/String;`, `Ljava/util/List;`. Với mảng, thêm **một dấu `[` cho mỗi chiều** vào trước descriptor của kiểu phần tử cơ sở:

| Java type | `getName()` | `descriptorString()` |
| --- | --- | --- |
| `int.class` | `int` | `I` |
| `int[].class` | `[I` | `[I` |
| `int[][].class` | `[[I` | `[[I` |
| `String.class` | `java.lang.String` | `Ljava/lang/String;` |
| `String[].class` | `[Ljava.lang.String;` | `[Ljava/lang/String;` |
| `String[][].class` | `[[Ljava.lang.String;` | `[[Ljava/lang/String;` |
| `java.util.Map.Entry[].class` | `[Ljava.util.Map$Entry;` | `[Ljava/util/Map$Entry;` |

**Cách đọc `[[Ljava/lang/String;`**: hai dấu `[` chỉ hai chiều; `L...;` chỉ kiểu tham chiếu; `java/lang/String` là tên lớp nội bộ. Với primitive, `getName()` và `descriptorString()` tình cờ giống nhau cho mảng, nhưng **khác nhau với mảng kiểu tham chiếu**. Descriptor của phương thức JVM có dạng `(tham-số)kiểu-trả-về`, ví dụ `(I)Ljava/lang/String;`; `Class.descriptorString()` chỉ trả **descriptor của một kiểu**, không phải cả method descriptor.

## 5. Ví dụ Java 17+ chạy độc lập

Tạo tệp `ArrayTypeInspection.java`:

```java
import java.lang.reflect.Array;

public class ArrayTypeInspection {
    static void show(Class<?> type) {
        Class<?> component = type.getComponentType();
        System.out.printf("%s%n", type.getTypeName());
        System.out.printf(
                "  isArray=%s, component=%s%n",
                type.isArray(),
                component == null ? "<none>" : component.getTypeName());
        System.out.printf("  getName=%s%n", type.getName());
        System.out.printf("  descriptor=%s%n", type.descriptorString());
    }

    public static void main(String[] args) throws Exception {
        show(int.class);
        show(int[].class);
        show(String[][].class);

        Class<?> t = String[][][].class;
        int depth = 0;
        while (t.isArray()) {
            depth++;
            t = t.getComponentType();
        }
        System.out.println("element=" + t.getTypeName()
                + ", dimensions=" + depth);

        Object created = Array.newInstance(String.class, 2, 3);
        System.out.println("created=" + created.getClass().getTypeName());

        System.out.println("roundTrip="
                + (Class.forName(String[][].class.getName())
                        == String[][].class));
    }
}
```

Biên dịch và chạy:

```bash
javac ArrayTypeInspection.java
java ArrayTypeInspection
```

Kết quả chuẩn:

```text
int
  isArray=false, component=<none>
  getName=int
  descriptor=I
int[]
  isArray=true, component=int
  getName=[I
  descriptor=[I
java.lang.String[][]
  isArray=true, component=java.lang.String[]
  getName=[[Ljava.lang.String;
  descriptor=[[Ljava/lang/String;
element=java.lang.String, dimensions=3
created=java.lang.String[][]
roundTrip=true
```

Giải thích: vòng `while` tách dần các `component type` nên đếm đúng ba chiều và tìm được phần tử cơ sở `String`. `Array.newInstance(String.class, 2, 3)` tạo một đối tượng mảng hai chiều (giá trị trả về khai báo là `Object`, nhưng kiểu runtime là `String[][]`). Dòng cuối chứng minh tên từ `getName()` của mảng tham chiếu có thể được `Class.forName(...)` dùng để tìm lại chính kiểu đó.

## 6. Tra cứu lớp mảng: `Class.forName` cần tên nào?

`Class.forName(String)` nhận **binary name** của lớp thường hoặc dạng tên mảng được `Class.getName()` trả về:

```java
Class<?> a = Class.forName("[I");                 // int[]
Class<?> b = Class.forName("[[Ljava.lang.String;"); // String[][]
boolean ok = a == int[].class && b == String[][].class;
```

Đoạn trên là **fragment** dùng trong ngữ cảnh cho phép `ClassNotFoundException` (ví dụ phương thức `throws Exception`). Với mảng tham chiếu, **không** truyền trực tiếp `"[Ljava/lang/String;"` từ `descriptorString()` vào `Class.forName`: cú pháp `/` thuộc descriptor JVM, còn `Class.forName` kỳ vọng tên kiểu mảng với `.` ở binary name thành phần. `Class.forName("java.lang.String[]")` không phải cách tra cứu mảng; `Class.forName("int")` cũng không trả về `int.class`.

Khi đã có `Class<?> component` và chỉ muốn lớp mảng tương ứng, dùng `component.arrayType()` hoặc lấy kiểu của mảng vừa tạo bằng `Array.newInstance(component, 0).getClass()`. Không cần tự nối chuỗi tên và không cần tải lớp bằng tên nếu có sẵn đối tượng `Class`.

## 7. Tạo và truy cập mảng động bằng Reflection

`java.lang.reflect.Array` làm việc với mảng dù lúc biên dịch không biết kiểu phần tử:

```java
Class<?> component = int.class;
Object values = Array.newInstance(component, 3); // runtime: int[]
Array.setInt(values, 0, 42);
int first = Array.getInt(values, 0);              // 42
int size = Array.getLength(values);               // 3
Class<?> arrayClass = values.getClass();          // int[].class
```

Đây là **fragment**, dùng khi đã `import java.lang.reflect.Array;`. Muốn thêm chiều, `Array.newInstance(String.class, 2, 3)` tạo `String[][]`. Nếu `component` bản thân đã là mảng, cấp phát thêm một chiều bằng `Array.newInstance(String[].class, 2)` tạo `String[][]`; các phần tử bên trong ban đầu là `null`, khác với `new String[2][3]`. Dạng `Array.newInstance(component, int... dimensions)` cộng số chiều có sẵn của `component` với số kích thước mới được truyền vào.

`Array.getLength` trả độ dài **một mảng cụ thể**, không trả số chiều của kiểu. Đọc/ghi mảng nhiều chiều phải lấy từng mảng con rồi mới truy cập phần tử; các hàng có thể dài khác nhau hoặc `null`. Với mảng primitive, `Array.get` trả giá trị được boxing; các hàm chuyên biệt như `getInt`/`setInt` tránh nhầm kiểu khi cần thao tác phần tử số nguyên.

Các lỗi dễ gặp:

- `getComponentType()` trả `null` trên `String.class` và `int.class`: không gọi tiếp trên `null`.
- `new int[4][5].getClass()` là `int[][].class` nhưng `getComponentType()` chỉ trả `int[].class`, chưa phải `int.class`.
- `Array.newInstance(void.class, 2)` không hợp lệ; số chiều lớn hơn 255 hoặc độ dài âm cũng bị từ chối.
- Kiểu mảng và độ dài mảng là hai khái niệm khác nhau. `getName()` và descriptor không chứa độ dài.
- Đừng dùng `getTypeName()` hay `getSimpleName()` làm khóa định danh duy nhất: class loader khác nhau có thể định nghĩa các lớp trùng tên. Nếu đang có `Class<?>`, ưu tiên so sánh `Class` hoặc làm việc trực tiếp với nó.
- Reflection bằng `Class<?>` diễn tả **kiểu đã bị erasure**: ví dụ `List<String>[]` ở runtime là kiểu mảng của `List`, descriptor `[Ljava/util/List;`; thông tin tham số generic ở chỗ khai báo, nếu cần, được xem qua API `Type`/`GenericArrayType` thích hợp.

## 8. Chọn API theo tình huống

| Câu hỏi trong chương trình | API nên dùng |
| --- | --- |
| Đầu vào có phải một kiểu mảng? | `type.isArray()` |
| Kiểu của mỗi phần tử tại cấp ngoài cùng? | `type.getComponentType()` |
| Mảng có bao nhiêu chiều, element type là gì? | Lặp `getComponentType()` khi `isArray()` |
| Muốn hiển thị kiểu dễ đọc trong log? | `type.getTypeName()` |
| Muốn cú pháp descriptor cho JVM/tooling? | `type.descriptorString()` |
| Muốn tra cứu lại một kiểu mảng bằng tên được Java hỗ trợ? | `Class.forName(type.getName())`, xử lý ngoại lệ |
| Muốn thêm một chiều từ một `Class` sẵn có? | `type.arrayType()` |
| Muốn cấp phát mảng lúc runtime? | `Array.newInstance(component, dimensions...)` |

**Tự kiểm tra.** (1) `int[][][].class.getComponentType()` trả kiểu nào? **`int[][].class`.** (2) Descriptor của `boolean[][]` là gì? **`[[Z`.** (3) `String[].class.getName()` và `descriptorString()` có giống nhau? **Không:** `[Ljava.lang.String;` so với `[Ljava/lang/String;`. (4) `String.class.getComponentType()` là gì? **`null`.**

Tài liệu tham chiếu: [Java SE 21 — `Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html) và [Java SE 21 — `java.lang.reflect.Array`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Array.html).