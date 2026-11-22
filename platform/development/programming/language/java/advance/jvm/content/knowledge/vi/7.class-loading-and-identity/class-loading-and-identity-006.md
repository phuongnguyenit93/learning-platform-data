# Class object, lớp mảng và cách JVM tạo biểu diễn kiểu khi chạy

Khi một chương trình Java hoạt động, JVM không chỉ quản lý **các instance**. Nó còn quản lý **kiểu tại runtime**: class, interface, array type, primitive type và kiểu `void` dùng trong mô hình reflection. Đối tượng `java.lang.Class<?>` là **điểm truy cập bằng Java tới biểu diễn của một kiểu được JVM nhận biết**; còn **array class** là một loại class được JVM tạo theo quy tắc riêng, không cần một file `String[].class` do `javac` xuất ra.

Ba ý chính của bài:

1. **`Class` object khác instance:** nhiều instance cùng runtime class thường nhận cùng một `Class` object qua `getClass()`; đối tượng `Class` mô tả **kiểu**, không phải một instance của kiểu đó.
2. **Định danh kiểu gắn với class loader:** hai định nghĩa class có **cùng binary name** nhưng được định nghĩa bởi hai defining class loaders khác nhau là **hai runtime types khác nhau**. Điều này giải thích các lỗi loader và cast trong ứng dụng plugin/container.
3. **JVM tạo array classes khi cần:** ví dụ `int[].class`, `String[].class`, `String[][].class` là các đối tượng `Class` hợp lệ dù không tồn tại mã nguồn `class String[]`. Một array object còn giữ runtime component type để JVM kiểm tra việc lưu phần tử.

Phạm vi của bài là **nạp/định danh lớp và biểu diễn kiểu khi chạy**, không phải cấu trúc toàn bộ heap hay thuật toán GC. Ví dụ chạy được với **Java 17+**.

## 1. “Class object” nghĩa là gì?

Trong Java, `java.lang.Class<T>` là lớp thư viện đại diện cho thông tin runtime của một kiểu. Đối tượng của lớp này thường được gọi là **class object**, **Class mirror** hay đơn giản là `Class` object.

```java
String first = new String("A");
String second = new String("B");

Class<?> mirror1 = first.getClass();
Class<?> mirror2 = second.getClass();
Class<String> literal = String.class;

System.out.println(mirror1 == mirror2); // true
System.out.println(mirror1 == literal); // true
System.out.println(first == second);    // false
```

Đây là **đoạn Java đặt trong method**, không phải source file độc lập. Hai `String` instance được tạo riêng, nhưng cả hai có cùng runtime class nên hai lệnh `getClass()` trả về cùng `Class` object. Dòng `String.class` cung cấp class literal tương ứng.

**Không nhầm các đối tượng:**

```text
             String instance A                 String instance B
           ┌─────────────────┐               ┌─────────────────┐
first ───► │ nội dung "A"     │   second ───► │ nội dung "B"     │
           └─────────────────┘               └─────────────────┘
                    │                                  │
                    └───────── runtime class ──────────┘
                                     │
                                     ▼
                              Class<String>
                           mirror của String
```

Sơ đồ trình bày **quan hệ logic**, không phải bố cục RAM thực tế. Từ một `Class` object, reflection có thể tra tên, superclass, interface, field, method, constructor, annotation, component type của mảng… nhưng `Class` object không tự lưu tất cả giá trị instance fields của từng object.

### Có những cách nào lấy Class object?

| Cách | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Class literal | `String.class` | Nhắc tới một kiểu ở compile time |
| Class literal của primitive | `int.class` | Lấy Class mirror cho kiểu primitive |
| Class literal của array | `String[][].class` | Lấy Class mirror cho array type |
| Instance runtime | `obj.getClass()` | Kiểu thực tế của **object**, không chỉ kiểu tĩnh của biến |
| Lookup bằng tên | `Class.forName("java.lang.String")` | Tìm/nạp kiểu theo tên nhị phân qua loader phù hợp, với quy tắc initialization của overload |
| Reflection tạo mảng | `Array.newInstance(component, 3).getClass()` | JVM tạo array object/array Class theo component type runtime |

`obj.getClass()` cần `obj != null`; gọi trên `null` gây `NullPointerException`. Ngược lại `String.class` không yêu cầu tạo instance `String`.

**`Class<?>` không phải `Class<Object>`:** dấu `?` là wildcard, phù hợp khi chương trình chỉ muốn mô tả một kiểu runtime mà không biết tham số `T` cụ thể. `Class<String>` mô tả kiểu `String`, nhưng không có nghĩa một `Class<String>` là một **String instance**.

## 2. Runtime class khác kiểu khai báo tĩnh của biến

```java
Object value = "hello";
System.out.println(value.getClass() == String.class); // true
```

Biến `value` có **declared/static type** là `Object`, nhưng object được tham chiếu thuộc **runtime class** `String`. `value.getClass()` phản ánh object thật đang tồn tại, không phải từ khóa `Object` trong khai báo.

Điều này liên quan trực tiếp đến:

- **Dynamic dispatch** của các instance methods có thể override.
- **`instanceof` và reference casts** được quyết định từ runtime type cùng các quan hệ subtype phù hợp.
- **Reflection**: `getDeclaredMethods()` trả method khai báo ở class mô tả; `getMethods()` bao gồm các public methods theo quy tắc API.
- **Serialization/framework mapping**: có thể cần biết runtime class để đọc metadata và tạo/biến đổi dữ liệu.

Class object và **class metadata nội bộ** không hoàn toàn là cùng một khái niệm API. JVM có thể lưu cấu trúc lớp theo cách triển khai riêng và cung cấp `java.lang.Class` làm mirror quan sát được từ Java. Đừng suy ra từ `Class<?> c` rằng toàn bộ class-file bytes hoặc metadata phải nằm bên trong object `c` theo một layout xác định.

## 3. Định danh runtime type: binary name + defining class loader

Một class hay interface không được xác định chỉ bằng chuỗi tên.

Theo mô hình JVM, **danh tính một class/interface được quyết định bởi cặp (binary name, defining class loader)**. Định nghĩa có cùng tên nhưng do loader khác nhau định nghĩa tạo ra các runtime classes **không đồng nhất**. Bởi vậy:

```text
(name = "example.Plugin", loader = Loader-A)  ──► Class A
(name = "example.Plugin", loader = Loader-B)  ──► Class B

A.getName().equals(B.getName())   → true
A == B                            → false
A.isAssignableFrom(B)             → false (nếu không có quan hệ subtype)
```

Sơ đồ giả định hai loader thực sự **định nghĩa** class cùng tên một cách độc lập. Nếu loader B **ủy quyền cho loader A/parent** và trả về cùng định nghĩa đã được nạp, class object sẽ giống nhau. **Initiating loader** (loader được yêu cầu bắt đầu việc nạp) và **defining loader** (loader thực sự định nghĩa class) không nhất thiết là một; phải phân biệt hai vai trò.

### 3.1. Parent delegation và class loader namespaces

Cách nạp class phổ biến dùng parent delegation: loader thử ủy quyền lên parent trước khi tự tìm định nghĩa. Cơ chế này giúp nhiều code dùng chung các lớp nền tảng. Tuy nhiên custom class loader có thể dùng các chiến lược riêng được JVM cho phép, vì vậy không nên nói “mọi class có cùng tên trong một JVM đều tự động là một class”.

Khi hai thư viện/plugin được nạp bởi loader khác nhau:

- Có thể thấy thông báo khó hiểu kiểu `X cannot be cast to X`: tên hiển thị giống nhau nhưng **định danh runtime khác nhau**.
- Một class có thể dùng static fields của định nghĩa A, class còn lại dùng static fields của định nghĩa B.
- Một reference có runtime class của loader A không tự tương thích với class cùng tên thuộc loader B.
- Array types `X[]` tương ứng cũng khác nhau khi component `X` khác runtime type.

**Quan trọng:** class loader quyết định namespace và nạp định nghĩa; nó không làm mọi cast đều thất bại. Nếu hai phần code dùng **cùng `Class` object** qua delegation, identity và các phép cast theo quan hệ kiểu vẫn bình thường.

### 3.2. `getClassLoader()` và bootstrap classes

`SomeClass.class.getClassLoader()` trả defining loader từ góc nhìn Java reflection. Với các kiểu được **bootstrap loader** định nghĩa, API thường trả **`null`**; cũng có các trường hợp như primitive/void và mảng primitive không có defining loader là object `ClassLoader` bình thường. Vì vậy `null` **không có nghĩa class chưa được nạp**.

Một ví dụ không phụ thuộc địa chỉ hay tên triển khai:

```java
System.out.println(int.class.getClassLoader() == null);    // true
System.out.println(int[].class.getClassLoader() == null);  // true
```

Các lớp do application loader định nghĩa thường có `getClassLoader() != null`, nhưng đừng hard-code tên lớp implementation của loader vì các JDK/runtime khác nhau có thể tổ chức khác nhau.

## 4. Primitive, `void` và reference types đều có Class mirror

`Class` API bao gồm cả kiểu không thể có instance object riêng giống `String`:

| Biểu thức | Điều biểu diễn | Ghi chú |
| --- | --- | --- |
| `int.class` | Primitive type `int` | `int.class == Integer.TYPE` |
| `boolean.class` | Primitive type `boolean` | Không tương đương `Boolean.class` |
| `void.class` | Kiểu `void` trong reflection | `void.class == Void.TYPE`; không thể `new void` |
| `String.class` | Runtime class `String` | Reference type |
| `java.util.List.class` | Runtime interface `List` | Không phải một object `List` cụ thể |
| `int[].class` | Array class của `int[]` | Reference type dù element type là primitive |
| `String[][].class` | Array class hai chiều | Component type là `String[]` |

`Class.isPrimitive()` dùng để hỏi về primitive-like Class objects theo API Java (bao gồm trường hợp `void.class`), nhưng **`void` không phải kiểu biến chứa giá trị thông thường** trong Java source. Với wrapper types, `Integer.class.isPrimitive()` là `false`.

Đối với generic code, phân biệt:

```java
Class<?> primitive = int.class;
Class<?> wrapper = Integer.class;
System.out.println(primitive == wrapper); // false
```

Autoboxing/unboxing giữa `int` và `Integer` là chuyển đổi ngôn ngữ, **không** khiến hai kiểu có chung Class mirror.

## 5. JVM tạo lớp mảng khác lớp thường ở điểm nào?

### 5.1. Array class là runtime type thực sự

Mỗi kiểu mảng có runtime class riêng:

```text
int[]           → Class mirror: int[].class
int[][]         → Class mirror: int[][].class
String[]        → Class mirror: String[].class
String[][]      → Class mirror: String[][].class
Plugin[]        → Class mirror tương ứng Plugin[] của đúng defining loader
```

JVM **không yêu cầu một tệp ClassFile tên `int[].class` hoặc `java.lang.String[].class`**. Định dạng và ngữ nghĩa của array class được JVM xử lý đặc biệt. Các array classes **được JVM tạo khi cần**, không phải nạp trực tiếp từ một ClassFile khai báo mảng như class thông thường.

Đối với **array of reference type**, defining loader của array class được xác định từ defining loader của component/reference type. Với mảng primitive, không có defining class loader do người dùng cung cấp. Đó là lý do hai class `Plugin` cùng binary name nhưng khác loader kéo theo hai kiểu `Plugin[]` khác nhau.

### 5.2. `getComponentType()` và `isArray()`

```java
Class<?> t = String[][].class;
System.out.println(t.isArray());                                  // true
System.out.println(t.getComponentType() == String[].class);        // true
System.out.println(t.getComponentType().getComponentType()
        == String.class);                                         // true
```

Đây là đoạn minh họa trong method; `getComponentType()` **bỏ đúng một chiều**. Đối với `String[][]`, component trực tiếp là **`String[]`**, không phải `String`. Với `int[].class`, component là `int.class`.

Với Class object không mô tả mảng, `getComponentType()` trả **`null`**. `isArray()` trả `false` cho primitive, `void`, class và interface thường.

### 5.3. Array superclass và implemented interfaces

Mọi array object trong Java là reference object. JVM đặt các quan hệ kiểu:

- Superclass trực tiếp của array class là **`java.lang.Object`**.
- Array classes implement **`java.lang.Cloneable`** và **`java.io.Serializable`**.
- Array object có **`length`** cố định và có thể **clone** tạo array object mới.
- Không có source `class MyArray extends String[]`; chương trình Java không tự định nghĩa subclass của array class.

Những điều này cũng đúng với `int[]`: `int[]` là object, dù các phần tử bên trong là `int`.

```java
System.out.println(int[].class.getSuperclass() == Object.class); // true
System.out.println(Cloneable.class.isAssignableFrom(int[].class)); // true
System.out.println(java.io.Serializable.class.isAssignableFrom(int[].class)); // true
```

Không nhầm `getSuperclass()` với `getInterfaces()`: array class có superclass `Object` và hai interfaces chuẩn, chứ không kế thừa từ `Object[]` trong mọi trường hợp. **`int[]` không phải subtype của `Object[]`**, nhưng là subtype của `Object`.

### 5.4. Tính covariance và kiểm tra runtime

Với element type là reference, Java arrays có tính **covariance**:

```java
String[] texts = new String[1];
Object[] values = texts;        // hợp lệ
values[0] = "hello";           // hợp lệ
values[0] = new Object();      // ArrayStoreException khi chạy
```

Đây là đoạn minh họa, dòng cuối cố ý gây exception. Kiểu **tĩnh** của `values` là `Object[]`, nhưng runtime class vẫn là **`String[].class`**. Instruction `aastore` kiểm tra giá trị được gán có tương thích với runtime component type hay không. Mảng vẫn là cùng object; phép gán `values = texts` **không chuyển mảng thành một `Object[]` mới**.

Ngược lại, primitive arrays **không covariant theo cách đó**:

```java
Object object = new int[2]; // hợp lệ: int[] là một Object
// Object[] wrong = new int[2]; // lỗi biên dịch
```

Ngay cả khi kiểu array là subtype hợp lệ, **`aastore` kiểm tra lúc runtime** vì compiler có thể chỉ biết biến được khai báo kiểu rộng hơn.

## 6. Binary name và ký hiệu tên array class trong reflection

`Class.getName()` với class thông thường thường trả binary name, còn với array class dùng ký hiệu gần giống **field descriptor**:

| Runtime type | `Class.getName()` | `Class.getTypeName()` |
| --- | --- | --- |
| `int` | `int` | `int` |
| `String` | `java.lang.String` | `java.lang.String` |
| `int[]` | `[I` | `int[]` |
| `long[][]` | `[[J` | `long[][]` |
| `String[]` | `[Ljava.lang.String;` | `java.lang.String[]` |
| `String[][]` | `[[Ljava.lang.String;` | `java.lang.String[][]` |

Giải mã:

- Mỗi ký tự **`[`** biểu thị một chiều mảng.
- `I` biểu thị `int`, `J` biểu thị `long`, `Z` biểu thị `boolean`, `D` biểu thị `double`.
- `L...;` biểu thị reference component type. Trong `Class.getName()`, tên class bên trong dùng dấu **`.`** (`java.lang.String`), không phải dấu `/` mà bạn có thể thấy trong ClassFile descriptor (`java/lang/String`).
- Với nested class, binary name của thành phần có thể chứa ký tự **`$`**, ví dụ `Outer$Inner`.

Lưu ý hai bối cảnh: tên từ **`Class.getName()`** và **field descriptor lưu trong ClassFile** rất giống đối với array nhưng **không đồng nhất cách viết tên class tham chiếu**. Không lấy chuỗi `Ljava/lang/String;` đưa thẳng vào `Class.forName` mà không xét quy tắc tên.

### `Class.forName` với array name

```java
Class<?> ints = Class.forName("[I");
Class<?> texts = Class.forName("[Ljava.lang.String;");

System.out.println(ints == int[].class);        // true
System.out.println(texts == String[].class);    // true
```

Đây là đoạn trong method **`throws ClassNotFoundException`** hoặc có xử lý exception. Tên `java.lang.String[]` **không phải** ký hiệu nhị phân phù hợp cho array lookup theo overload trên; với primitive source name `"int"`, `Class.forName("int")` cũng không cung cấp primitive Class object. Dùng `int.class` hoặc `Integer.TYPE` cho primitive.

Khi dùng `Class.forName(String)`, overload đơn giản mặc định có hành vi yêu cầu initialize class thông thường khi phù hợp. Có overload **`Class.forName(String name, boolean initialize, ClassLoader loader)`** để chọn rõ việc initialize. Khi tên chỉ **array class**, nó không buộc component class phải initialize chỉ để tạo/tra array Class object.

## 7. Các instruction liên quan tới tạo mảng

Compiler/JVM có instruction riêng cho array object; nó không dùng `new` với một tên class file `"int[]"` được khai báo ở Java.

| Instruction | Mục đích | Ví dụ Java source |
| --- | --- | --- |
| `newarray` | Tạo mảng **primitive** một chiều | `new int[3]`, `new byte[2]` |
| `anewarray` | Tạo mảng **reference component** một chiều | `new String[3]`, `new int[2][]` |
| `multianewarray` | Cấp phát các chiều được chỉ định của mảng nhiều chiều | `new int[2][3]` |
| `arraylength` | Lấy độ dài array object từ array reference | `numbers.length` |
| `iaload`, `aaload` và nhóm load | Đọc phần tử theo loại mảng | `numbers[i]`, `names[i]` |
| `iastore`, `aastore` và nhóm store | Ghi phần tử; `aastore` kiểm tra loại runtime khi ghi reference | `numbers[i]=1`, `names[i]="x"` |

Đây là những **mẫu bytecode điển hình**, không có cam kết mỗi biểu thức source luôn có một instruction tương ứng duy nhất. Compiler có thể thay đổi cấu trúc lệnh phù hợp ngữ nghĩa.

### 7.1. Mảng nhiều chiều là mảng chứa mảng

```java
int[][] a = new int[2][3];
int[][] b = new int[2][];

System.out.println(a.length);           // 2
System.out.println(a[0].length);        // 3
System.out.println(b.length);           // 2
System.out.println(b[0] == null);       // true
```

Với `a`, JVM tạo outer array và các inner arrays đủ cho hai chiều đã chỉ định; với `b`, chỉ outer array được tạo và các vị trí component reference ban đầu là `null`. Vì vậy **cùng có runtime type `int[][]`**, nhưng đồ thị các array instances đã cấp phát khác nhau.

**Độ dài là thuộc tính của array instance**, không phải thuộc tính cố định của array Class: `new int[2]` và `new int[7]` có cùng `Class` object `int[].class`, nhưng lần lượt có length 2 và 7. Không suy ra `Class` mô tả `int[2]` là một runtime type khác `int[7]`.

### 7.2. Dữ liệu và lỗi lúc tạo/truy cập

- `new int[-1]` gây **`NegativeArraySizeException`**.
- Cấp phát array có thể gây **`OutOfMemoryError`** nếu thiếu tài nguyên.
- Lấy `length` hoặc đọc/ghi phần tử qua null array reference có thể gây **`NullPointerException`**.
- Chỉ số âm hoặc `>= length` gây **`ArrayIndexOutOfBoundsException`** khi truy cập.
- Ghi object không hợp component type thực sự vào mảng reference có thể gây **`ArrayStoreException`**.
- Không phải mọi phép xử lý `Object[]` đều hợp lệ với `int[]`; kiểu phần tử phải đúng.

Các lỗi trên liên quan **array instances** và giá trị runtime. Bytecode verifier còn kiểm tra những ràng buộc về loại instruction, operand stack và tính hợp lệ của class file; đó là tầng kiểm tra khác.

## 8. Ví dụ chạy Java 17+: Class object cho class, primitive và array

Tạo **`ClassMirrorDemo.java`** trong một thư mục trống:

```java
import java.io.Serializable;
import java.lang.reflect.Array;

public class ClassMirrorDemo {
    interface Marker {}

    static class Item implements Marker {}

    static class Other {}

    public static void main(String[] args) throws ClassNotFoundException {
        Item first = new Item();
        Item second = new Item();

        Class<?> mirror = first.getClass();
        System.out.println("same literal: " + (mirror == Item.class));
        System.out.println("same runtime type: "
                + (mirror == second.getClass()));
        System.out.println("different instances: " + (first != second));

        System.out.println("class name: " + mirror.getName());
        System.out.println("simple name: " + mirror.getSimpleName());
        System.out.println("superclass: "
                + mirror.getSuperclass().getName());
        System.out.println("interface: "
                + mirror.getInterfaces()[0].getSimpleName());

        System.out.println("int primitive: " + int.class.isPrimitive());
        System.out.println("wrapper primitive: "
                + Integer.class.isPrimitive());
        System.out.println("void mirror: " + (void.class == Void.TYPE));

        System.out.println("int array name: " + int[].class.getName());
        System.out.println("String 2D name: "
                + String[][].class.getName());
        System.out.println("component 2D: "
                + (String[][].class.getComponentType()
                        == String[].class));
        System.out.println("component primitive: "
                + int[].class.getComponentType().isPrimitive());

        System.out.println("array superclass: "
                + (int[].class.getSuperclass() == Object.class));
        System.out.println("array Cloneable: "
                + Cloneable.class.isAssignableFrom(int[].class));
        System.out.println("array Serializable: "
                + Serializable.class.isAssignableFrom(int[].class));
        System.out.println("array loader: "
                + (Item[].class.getClassLoader()
                        == Item.class.getClassLoader()));

        int[] numbers = {1, 2, 3};
        System.out.println("same array class: "
                + (numbers.getClass() == int[].class));
        System.out.println("array length: " + Array.getLength(numbers));

        System.out.println("lookup [I: "
                + (Class.forName("[I") == int[].class));
        System.out.println("lookup String[]: "
                + (Class.forName("[Ljava.lang.String;")
                        == String[].class));

        Object[] items = new Item[1];
        items[0] = new Item();
        System.out.println("runtime component: "
                + items.getClass().getComponentType().getSimpleName());
        try {
            items[0] = new Other();
        } catch (ArrayStoreException e) {
            System.out.println("bad store: ArrayStoreException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ClassMirrorDemo.java
java ClassMirrorDemo
```

**Standard output:**

```text
same literal: true
same runtime type: true
different instances: true
class name: ClassMirrorDemo$Item
simple name: Item
superclass: java.lang.Object
interface: Marker
int primitive: true
wrapper primitive: false
void mirror: true
int array name: [I
String 2D name: [[Ljava.lang.String;
component 2D: true
component primitive: true
array superclass: true
array Cloneable: true
array Serializable: true
array loader: true
same array class: true
array length: 3
lookup [I: true
lookup String[]: true
runtime component: Item
bad store: ArrayStoreException
```

### Giải thích quan sát được

1. Hai `new Item()` tạo **hai instance**, nhưng `getClass()` và `Item.class` dẫn tới cùng Class mirror của kiểu `Item` đã được định nghĩa bởi cùng loader.
2. `ClassMirrorDemo$Item` là **binary name của nested class**; `getSimpleName()` trả phần `Item`.
3. `int.class` là primitive; `Integer.class` là wrapper reference class. `void.class` đại diện kiểu `void` trong reflection.
4. `[I` biểu diễn `int[]`; `[[Ljava.lang.String;` biểu diễn `String[][]`.
5. Mảng `int[]` có superclass `Object`, là `Cloneable` và `Serializable`. Một array class của `Item[]` có defining loader tương ứng với `Item`.
6. `Array.getLength` đọc length của **array instance**, không đọc một thuộc tính số phần tử cố định của `int[].class`.
7. `Class.forName("[I")` và tên array nhị phân `[Ljava.lang.String;` trả array Class mirror tương ứng.
8. `Object[] items = new Item[1]` không làm runtime component thành `Object`. Gán `Other` qua `Object[]` phải bị `aastore` bác vì object array thực tế chỉ chứa được `Item` hoặc subtype thích hợp.

Chương trình bắt `ArrayStoreException` và tự in chuỗi cố định, tránh phụ thuộc thông báo chi tiết giữa các phiên bản JVM.

## 9. Class literal và array creation **không** đồng nghĩa initialize component class

Class loading, linking, **class initialization** và **array class creation** là các sự kiện cần phân biệt. Lấy `Target.class` hoặc tạo `Target[]` không phải luôn kích hoạt `Target` static initializer.

Tạo file **`ArrayInitializationDemo.java`**:

```java
public class ArrayInitializationDemo {
    static class Target {
        static {
            System.out.println("Target static initializer");
        }

        Target() {
            System.out.println("Target constructor");
        }
    }

    public static void main(String[] args)
            throws ClassNotFoundException {
        System.out.println("begin");

        Class<?> type = Target.class;
        System.out.println("literal: " + type.getSimpleName());

        Target[] array = new Target[2];
        System.out.println("array length: " + array.length);
        System.out.println("component: "
                + array.getClass().getComponentType().getSimpleName());

        Class.forName(Target.class.getName(),
                false, Target.class.getClassLoader());
        System.out.println("after lookup without initialization");

        Class.forName(Target.class.getName(),
                true, Target.class.getClassLoader());
        System.out.println("after lookup with initialization");

        new Target();
        System.out.println("end");
    }
}
```

Chạy trên Java 17+:

```bash
javac -encoding UTF-8 ArrayInitializationDemo.java
java ArrayInitializationDemo
```

**Standard output chính xác:**

```text
begin
literal: Target
array length: 2
component: Target
after lookup without initialization
Target static initializer
after lookup with initialization
Target constructor
end
```

### Phân tích

- `Target.class` cung cấp Class mirror của nested class `Target`; thao tác này **không tự yêu cầu thực thi static initializer**.
- `new Target[2]` tạo một **array object có hai vị trí tham chiếu**; hai phần tử ban đầu là `null`. Nó **không tạo hai object `Target`**, vì vậy không in constructor; chỉ tạo mảng cũng không tự khởi tạo tĩnh của component class.
- `array.getClass().getComponentType()` trả Class mirror của `Target`, không buộc phải thực hiện `Target.<clinit>`.
- `Class.forName(name, false, loader)` nạp/tra và liên kết lớp nếu cần nhưng yêu cầu **không initialize class** thông qua lời gọi này.
- `Class.forName(name, true, loader)` yêu cầu initialization của class chưa được initialized, nên in đúng **một** dòng `Target static initializer`.
- Sau khi static initialization thành công, `new Target()` tạo instance và gọi constructor; không chạy lại static initializer.

**Ghi nhớ:** array class có thể được JVM tạo hoặc giải quyết mà không khởi tạo component class. Nếu **sau đó** code tạo `new Target()`, gọi static method của `Target` hoặc active-use tương ứng, initialization mới phải xảy ra theo quy tắc JVM/JLS.

Đối với reference array, tạo outer array và **đưa các reference mặc định `null` vào phần tử** khác hoàn toàn việc tạo các instances của component type. Với primitive array, các phần tử có giá trị mặc định của primitive type như `0`, `false` hoặc `0.0`.

## 10. Thử nghiệm định danh lớp với hai defining loaders

Đây là ví dụ minh họa trực tiếp rằng **cùng binary name không đồng nghĩa cùng class object**. Không thay classloader của JVM đang chạy toàn hệ thống; ví dụ dùng hai custom class loaders chỉ để định nghĩa độc lập một class nhỏ từ **cùng bytecode**.

Tạo **`LoaderTarget.java`**:

```java
public class LoaderTarget {
}
```

Tạo **`LoaderIdentityDemo.java`**:

```java
import java.lang.reflect.Array;
import java.nio.file.Files;
import java.nio.file.Path;

public class LoaderIdentityDemo {
    static final class ByteLoader extends ClassLoader {
        Class<?> define(String binaryName, byte[] bytes) {
            return defineClass(binaryName, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of("LoaderTarget.class"));

        ByteLoader loaderA = new ByteLoader();
        ByteLoader loaderB = new ByteLoader();

        Class<?> a = loaderA.define("LoaderTarget", bytes);
        Class<?> b = loaderB.define("LoaderTarget", bytes);

        System.out.println("same binary name: "
                + a.getName().equals(b.getName()));
        System.out.println("same Class object: " + (a == b));
        System.out.println("same defining loader: "
                + (a.getClassLoader() == b.getClassLoader()));

        Class<?> arrayA = Array.newInstance(a, 0).getClass();
        Class<?> arrayB = Array.newInstance(b, 0).getClass();
        System.out.println("same array class: " + (arrayA == arrayB));
        System.out.println("array A component: "
                + (arrayA.getComponentType() == a));
        System.out.println("array B component: "
                + (arrayB.getComponentType() == b));
    }
}
```

Biên dịch cả hai file trong cùng thư mục và chạy ở đó:

```bash
javac -encoding UTF-8 LoaderTarget.java LoaderIdentityDemo.java
java LoaderIdentityDemo
```

**Standard output chính xác:**

```text
same binary name: true
same Class object: false
same defining loader: false
same array class: false
array A component: true
array B component: true
```

### Vì sao ví dụ này hợp lệ?

- `LoaderTarget.class` đã được `javac` tạo; chương trình chỉ **đọc byte của chính file đó**.
- `ByteLoader.define` gọi **`ClassLoader.defineClass`**. Mỗi `ByteLoader` object định nghĩa riêng class cùng binary name `LoaderTarget`.
- `a.getName()` và `b.getName()` giống nhau; nhưng `a != b` và defining class loaders khác nhau.
- `Array.newInstance(a, 0)` và `Array.newInstance(b, 0)` tạo **hai array objects rỗng**, đồng thời cho phép JVM nhận diện array classes tương ứng `LoaderTarget[]` theo hai component types độc lập.
- Vì `a` và `b` khác runtime types, `arrayA` và `arrayB` cũng khác runtime types, dù khi chỉ in tên của chúng có thể trông giống nhau.
- Code cố tình dùng `defineClass` trực tiếp để minh họa **defining loader**; một custom loader hoàn chỉnh phục vụ production còn cần chính sách nạp, đồng bộ, delegation và kiểm tra bảo mật/nguồn bytes phù hợp.

**Giới hạn mô phỏng:** ví dụ không yêu cầu instantiate `LoaderTarget` của loader A hoặc B. Nó chỉ cần định nghĩa class và tạo array classes; vì thế không phụ thuộc việc gọi constructor hoặc class initialization của `LoaderTarget`. Từ việc có `Class` object không suy ra static initializer đã chạy.

## 11. Reflection: thao tác trên runtime types thay vì instance

Một số API `Class` và `java.lang.reflect.Array` giúp quan sát/điều khiển thông tin kiểu:

| API | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `obj.getClass()` | Runtime class của instance | NPE nếu `obj == null` |
| `Class.getName()` | Tên runtime/binary name hoặc dạng array name | Nested class có thể có `$`, array có `[` |
| `Class.getTypeName()` | Tên kiểu dễ đọc hơn cho array | Không phải lời bảo đảm luôn trả source literal |
| `Class.isArray()` | Class mirror có mô tả array type? | `int[].class.isArray()` là `true` |
| `Class.getComponentType()` | Kiểu thành phần của một chiều | Trả `null` nếu không phải array |
| `Class.isPrimitive()` | Primitive/void marker theo API | `Integer.class` là wrapper, không primitive |
| `Class.isInterface()` | Runtime interface type? | Mảng không phải interface |
| `Class.getSuperclass()` | Superclass của class phù hợp | `Object`, primitive, interface có quy tắc khác; array là `Object` |
| `Class.getClassLoader()` | Loader định nghĩa class theo reflection | `null` có thể biểu thị bootstrap/primitive |
| `Class.isInstance(value)` | Kiểm tra object có là instance của runtime type? | Với `null` luôn trả `false` |
| `Class.isAssignableFrom(other)` | Kiểm tra quan hệ gán kiểu từ `other` vào receiver | **Chiều của phép kiểm tra quan trọng** |
| `Array.newInstance(component, n)` | Tạo array instance runtime từ một component `Class` | Kích thước âm gây `NegativeArraySizeException` |
| `Array.getLength(array)` | Lấy độ dài của array object | Đối số phải là array object hợp lệ |

Phân biệt `isInstance` và `isAssignableFrom`:

```java
System.out.println(Number.class.isInstance(Integer.valueOf(3))); // true
System.out.println(Number.class.isAssignableFrom(Integer.class)); // true
System.out.println(Integer.class.isAssignableFrom(Number.class)); // false
```

`isInstance` xét **object đang tồn tại**, còn `isAssignableFrom` xét **quan hệ giữa runtime types**. Cả hai chịu ảnh hưởng identity của defining loader; không chỉ xét chuỗi name.

### Reflection và generics

`Class<List>` không mã hóa riêng một runtime class cho `List<String>` và `List<Integer>` theo generic type arguments. Java generics thông thường dùng **type erasure**; metadata generic có thể được giữ trong `Signature` và đọc qua API như `Field.getGenericType()`, nhưng **không tạo một `Class` object mới cho mỗi tham số kiểu**.

```java
java.util.List<String> words = java.util.List.of("a");
java.util.List<Integer> numbers = java.util.List.of(1);
System.out.println(words.getClass() == numbers.getClass());
```

Trong ví dụ dùng `List.of`, runtime factory implementation cụ thể có thể thay đổi theo JDK; do đó **không nên dùng hai instance trả về từ factory để khẳng định mọi `List<T>` đều có cùng implementation class**. Quy tắc cần ghi nhớ là generic type arguments thông thường **không tách thành runtime classes riêng theo tham số `T`**.

Khi cần tạo mảng generic bằng reflection, nhận một `Class<T>` component rõ ràng và cân nhắc cast kiểu có kiểm tra; không cố gọi `new T[10]` trong generic method nếu Java type system không cho phép.

## 12. Quan sát bytecode và mối liên hệ với ClassFile

Sau khi biên dịch `ClassMirrorDemo.java`, dùng:

```bash
javap -c -p ClassMirrorDemo
javap -verbose ClassMirrorDemo
```

Những mẫu hữu ích để tìm:

| Java source | Bytecode thường thấy | Ý nghĩa |
| --- | --- | --- |
| `Item.class` | `ldc` tham chiếu mục kiểu trong constant pool | Lấy runtime `Class` mirror của kiểu |
| `first.getClass()` | `invokevirtual java/lang/Object.getClass:()Ljava/lang/Class;` | Lấy runtime class của object |
| `new Item()` | `new`, `dup`, `invokespecial <init>` | Tạo object và thực thi constructor |
| `new int[3]` | `newarray int` | Tạo array object primitive |
| `new Item[1]` | `anewarray` | Tạo array object reference |
| `numbers.length` | `arraylength` | Đẩy độ dài `int` lên operand stack |
| `values[index]` / `values[index] = ...` | `*aload` / `*astore` thích hợp | Đọc/ghi phần tử và kiểm tra runtime liên quan |
| `String[][].class` | `ldc` tham chiếu array class | Lấy mirror của runtime array type |

`ldc` với class literal dùng symbolic reference trong constant pool, nhưng **nó không đồng nghĩa gọi constructor `java.lang.Class()` từ mã Java**. JVM quản lý việc lấy/duy trì Class mirror cho runtime type theo các quy tắc nền tảng của VM.

Bytecode `newarray`, `anewarray`, `multianewarray` thực hiện cấp phát array instances và tương tác với array classes; chúng **không cần bytecode constructor `<init>` của class array** giống một class do lập trình viên khai báo. Array có các quy tắc đặc biệt của VM.

**`javap -c` in bytecode lưu trong class file**, không phải mã máy JIT của CPU. Các instruction, offset và thứ tự constant pool có thể khác giữa các compiler/version mà vẫn tuân thủ cùng ngữ nghĩa.

## 13. Các lỗi và cách xác định đúng tầng

| Dấu hiệu | Nguyên nhân cần kiểm tra |
| --- | --- |
| `ClassNotFoundException` khi `Class.forName(...)` | Tên/binary name sai, classpath/module path/loader không tìm thấy định nghĩa |
| `NoClassDefFoundError` | Runtime không thể nạp định nghĩa cần thiết, hoặc class đã lỗi initialization trước đó; không tự gộp mọi nguyên nhân thành thiếu file |
| `LinkageError` hoặc loader constraint violation | Định danh/quan hệ giữa các class và loaders không nhất quán, hoặc class metadata không tương thích |
| `ClassCastException` dù hai tên class in ra giống nhau | Kiểm tra **defining class loader**, không chỉ `getName()` |
| `ArrayStoreException` khi ghi qua `Object[]` | Runtime component type của mảng có thể hẹp hơn kiểu tĩnh `Object` |
| `NegativeArraySizeException` | Kích thước array tạo ra âm |
| `ArrayIndexOutOfBoundsException` | Chỉ số truy cập không thuộc `0 .. length-1` |
| `NullPointerException` khi dùng `getClass()` hoặc `array.length` | Reference là `null` |
| Lấy `Class` được nhưng không thấy log static initializer | Class loading/lấy mirror **không** luôn gây class initialization |
| `Class.forName("java.lang.String[]")` không tìm thấy array type | Dùng array name theo dạng `[Ljava.lang.String;` hoặc class literal `String[].class` |

Đừng dùng `==` giữa **hai instances** để thay cho `==` giữa **hai Class mirrors**; chúng trả lời hai câu hỏi khác nhau. Tương tự, định danh object và định danh class đều khác với so sánh hai chuỗi tên.

## 14. Bài tập và câu hỏi tự kiểm tra

**Bài 1 — Một runtime type, nhiều instances.**  
Cho `String a = new String("x"); String b = new String("y");`. `a == b` và `a.getClass() == b.getClass()` trả gì?  
**Đáp án:** `false` và `true`. Hai instances khác nhau nhưng cùng runtime class.

**Bài 2 — Mảng của mảng.**  
`String[][].class.getComponentType()` có bằng `String.class` không?  
**Đáp án:** **Không**; bằng `String[].class`. Mỗi `getComponentType()` bỏ **một chiều**.

**Bài 3 — Mảng có chiều dài khác nhau.**  
`new int[2].getClass() == new int[9].getClass()` có đúng không?  
**Đáp án:** **Đúng** (nếu viết trong biểu thức Java hợp lệ với dấu ngoặc thích hợp); cả hai cùng kiểu `int[]`; độ dài thuộc từng instance, không thuộc runtime class.

**Bài 4 — Class loader identity.**  
Vì sao `Class<?> a` và `Class<?> b` có cùng `getName()` mà `a == b` lại `false`?  
**Đáp án:** Có thể là **hai định nghĩa cùng binary name từ defining loaders khác nhau**. So sánh `getClassLoader()`, xem đường nạp và quan hệ delegation.

**Bài 5 — Array initialization.**  
`new Target[5]` có gọi constructor `Target()` 5 lần không?  
**Đáp án:** **Không lần nào**; nó tạo mảng chứa 5 reference mặc định `null`. Tạo object `Target` cần hoạt động riêng như `new Target()`.

**Bài 6 — Active use.**  
`Target.class` và `Class.forName("Target", true, loader)` có hiệu ứng initialization như nhau?  
**Đáp án:** **Không**; class literal không tự bắt buộc chạy static initializer; `Class.forName` với `initialize=true` yêu cầu initialization theo quy tắc tương ứng.

**Bài 7 — Primitive Class mirror.**  
`int.class == Integer.class` có đúng không?  
**Đáp án:** **Sai**. Primitive `int` và wrapper class `Integer` là hai kiểu khác nhau.

**Bài 8 — Kế thừa của array.**  
`Object.class.isAssignableFrom(int[].class)` và `Object[].class.isAssignableFrom(int[].class)` lần lượt là gì?  
**Đáp án:** `true` và `false`. Mọi array là Object, nhưng primitive array không là Object[].

**Bài 9 — Runtime store check.**  
Tại sao `Object[] a = new String[1]; a[0] = new Object();` biên dịch nhưng thất bại?  
**Đáp án:** Kiểu tĩnh `Object[]` cho phép gán Object; runtime array object có component type `String`, nên `aastore` ném `ArrayStoreException`.

**Bài 10 — ClassFile.**  
Có bắt buộc phải tìm thấy tệp `int[].class` trên disk để `int[].class` hoạt động không?  
**Đáp án:** **Không**. JVM tạo/nhận diện array class theo quy tắc riêng. Tệp ClassFile thông thường mô tả class/interface được định nghĩa, không phải class array do JVM tạo.

**Bài 11 — `Class.forName` tên array.**  
Tên runtime thích hợp khi tìm `String[]` là `java.lang.String[]` hay `[Ljava.lang.String;`?  
**Đáp án:** Theo cú pháp array name của `Class.getName()`, dùng **`[Ljava.lang.String;`**.

**Bài 12 — Hai lớp cùng tên trong plugin.**  
Nếu loader A và loader B thật sự định nghĩa hai class `com.example.Plugin` độc lập, thì `com.example.Plugin[]` tương ứng có chắc là một array class không?  
**Đáp án:** **Không**. Array classes được định danh qua component type tương ứng; component runtime types khác nhau tạo các array types khác nhau.

### Kết luận

Khi debug Java class loading, luôn phân biệt **object instance**, **Class mirror**, **runtime type identity**, **defining loader** và **array class**. `Class<?> ` là cổng quan sát kiểu runtime, không phải một bản sao object. Kiểu class/interface mang định danh gắn với tên và defining loader. Array classes do JVM tạo theo component type; array objects có length và dữ liệu riêng, trong khi array Class object mô tả **kiểu**, không mô tả độ dài của một instance cụ thể. Class literal và tạo array cũng không buộc component class phải chạy static initializer.

Để đọc quy tắc chi tiết, đối chiếu *The Java Virtual Machine Specification*, mục **§5.3 (Creation of Classes and Interfaces, trong đó §5.3.3 là Creation of Array Classes)**, và *Java Language Specification* mục **§10 (Arrays)**, **§12.4 (Initialization)**. API `java.lang.Class` và `java.lang.reflect.Array` cung cấp phép thử trực tiếp cho những khái niệm trong bài.