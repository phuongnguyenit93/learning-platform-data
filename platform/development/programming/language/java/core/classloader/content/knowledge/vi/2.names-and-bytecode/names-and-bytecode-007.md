# Descriptor của kiểu, phương thức và lớp mảng trong JVM

## 1. Descriptor giải quyết vấn đề gì?

Ở mã nguồn Java, ta viết `int`, `java.lang.String`, `String[][]` hoặc `String join(int, String[])`. Trong bytecode và cấu trúc `.class`, JVM cần cách biểu diễn **kiểu dữ liệu** bằng chuỗi ngắn, có cú pháp xác định để đọc được chính xác từng kiểu mà không phụ thuộc cách trình bày của mã nguồn. Chuỗi đó gọi là **descriptor**.

Có hai dạng chính:

- **Field descriptor**: mô tả **một kiểu** của field, biến, tham số hoặc giá trị. Ví dụ: `I` là `int`, `Ljava/lang/String;` là `java.lang.String`, `[[I` là `int[][]`.
- **Method descriptor**: mô tả **danh sách kiểu tham số theo thứ tự và kiểu trả về**. Ví dụ: `(I[Ljava/lang/String;)V` là phương thức nhận `int` và `String[]`, trả về `void`.

Descriptor **không chứa** tên biến, tên phương thức, tên tham số, generic type argument, access modifier, `throws` hay nội dung thân hàm. Tên phương thức và descriptor là hai thông tin riêng trong class file. Đây là nền tảng để đọc kết quả `javap -s`, phân biệt các phương thức overload, dùng reflection/method handle và hiểu lúc JVM liên kết các tham chiếu đến lớp.

> Phân biệt ngay từ đầu: `java.lang.String` là tên nhị phân (*binary name*) dùng nhiều ở Java API; `java/lang/String` là dạng tên nội bộ (*internal name*) ở class file; `Ljava/lang/String;` mới là descriptor cho kiểu tham chiếu ấy.

## 2. Cú pháp field descriptor

Theo JVMS §4.3.2, một field descriptor biểu diễn đúng một kiểu:

```text
FieldType = BaseType | ObjectType | ArrayType
BaseType  = B | C | D | F | I | J | S | Z
ObjectType = L InternalClassName ;
ArrayType  = [ FieldType
```

Bảng ánh xạ kiểu nguyên thủy:

| Kiểu Java | Descriptor | Ghi nhớ |
|---|---|---|
| `byte` | `B` | byte |
| `char` | `C` | char |
| `double` | `D` | double |
| `float` | `F` | float |
| `int` | `I` | int |
| `long` | `J` | long, dùng ký hiệu `J` |
| `short` | `S` | short |
| `boolean` | `Z` | boolean |

`V` biểu diễn `void`, **chỉ hợp lệ làm kiểu trả về của method descriptor**; `V` không phải descriptor hợp lệ cho field, tham số hoặc phần tử mảng.

### Kiểu class hoặc interface

Cú pháp là `L` + tên nội bộ + `;`:

| Kiểu mã nguồn | Field descriptor |
|---|---|
| `String` | `Ljava/lang/String;` |
| `java.lang.Object` | `Ljava/lang/Object;` |
| `java.util.List` | `Ljava/util/List;` |
| `java.util.Map.Entry` | `Ljava/util/Map$Entry;` |

Trong tên nội bộ, dấu `/` ngăn cách package; ký hiệu `$` thường nằm trong binary name của nested class. Hai dấu `L` và `;` là thành phần bắt buộc của descriptor tham chiếu; chỉ viết `java/lang/String` là tên nội bộ, chưa phải field descriptor.

Descriptor không biểu diễn chi tiết kiểu generic. Ví dụ, khi xét kiểu đã bị xóa (*erasure*), `List<String>` và `List<Integer>` cùng có descriptor `Ljava/util/List;`. Thông tin generic có thể được giữ ở thuộc tính `Signature`, vốn có ngữ pháp khác với descriptor.

## 3. Descriptor của lớp mảng

Mỗi dấu `[` thể hiện **một chiều mảng**; sau các dấu `[` là descriptor của kiểu phần tử cuối cùng.

| Kiểu Java | Descriptor |
|---|---|
| `int[]` | `[I` |
| `long[][]` | `[[J` |
| `boolean[][][]` | `[[[Z` |
| `String[]` | `[Ljava/lang/String;` |
| `String[][]` | `[[Ljava/lang/String;` |
| `java.util.Map.Entry[][]` | `[[Ljava/util/Map$Entry;` |

Cách đọc `[[Ljava/lang/String;`: hai dấu `[` cho biết mảng hai chiều; `Ljava/lang/String;` cho biết phần tử cuối cùng là `String`. Khi bỏ một dấu `[`, ta được kiểu thành phần trực tiếp: `String[][]` có component type là `String[]`; chỉ sau khi bỏ dấu `[` thứ hai mới tới `String`.

Một số điều dễ nhầm:

- `String[]` và `String[][]` là **hai lớp mảng runtime khác nhau**, tương ứng hai đối tượng `Class<?>` khác nhau. JVM tạo lớp mảng khi cần; không cần một file nguồn riêng mang tên `[Ljava/lang/String;`.
- Với mảng tham chiếu, lớp mảng có defining loader tương ứng với defining loader của kiểu phần tử tham chiếu; mảng của kiểu nguyên thủy gắn với bootstrap loader (`getClassLoader()` có thể trả `null`). Cùng descriptor chưa đủ xác định duy nhất một lớp runtime nếu cùng tên tham chiếu được định nghĩa bởi các class loader khác nhau.
- Mảng Java là object; lớp mảng có superclass trực tiếp là `java.lang.Object` và thực thi `java.lang.Cloneable`, `java.io.Serializable`. Các đặc điểm này không xuất hiện trong chuỗi descriptor.
- Mảng nhiều chiều của Java thực chất là **mảng của mảng**; ví dụ `new int[2][]` và `new int[2][3]` đều có kiểu runtime `int[][]`, tức descriptor `[[I`. Descriptor mô tả **kiểu**, không mô tả kích thước hay số phần tử.
- JVMS giới hạn field descriptor của kiểu mảng tối đa **255 chiều**; đây là giới hạn cấu trúc class file, không phải cú pháp khai báo thông thường cần sử dụng trong ứng dụng.

## 4. Cú pháp method descriptor

Theo JVMS §4.3.3:

```text
MethodDescriptor = ( ParameterType* ) ReturnType
ParameterType    = FieldType
ReturnType       = FieldType | V
```

Từng parameter type viết **liền nhau**, không dấu phẩy, không khoảng trắng; đặt toàn bộ trong cặp ngoặc tròn. Sau `)` phải có **đúng một** kiểu trả về, kể cả khi phương thức trả về `void`.

| Khai báo Java | Method descriptor |
|---|---|
| `void ping()` | `()V` |
| `int square(int n)` | `(I)I` |
| `boolean contains(String s)` | `(Ljava/lang/String;)Z` |
| `String format(int n, String[] tags)` | `(I[Ljava/lang/String;)Ljava/lang/String;` |
| `long[][] convert(byte[] input, double factor)` | `([BD)[[J` |
| `void accept(String... values)` | `([Ljava/lang/String;)V` |

Ví dụ tách chuỗi `(I[Ljava/lang/String;)Ljava/lang/String;`:

1. `(`: bắt đầu danh sách tham số.
2. `I`: tham số thứ nhất là `int`.
3. `[Ljava/lang/String;`: tham số thứ hai là `String[]`; ký tự `;` chấm dứt descriptor của phần tử tham chiếu.
4. `)`: kết thúc tham số.
5. `Ljava/lang/String;`: kiểu trả về là `String`.

**Không có tên method trong descriptor.** Hai khai báo `int sum(int a, int b)` và `int add(int x, int y)` đều có `(II)I`. Trong class file, tên kết hợp với descriptor mới tham gia nhận diện phương thức; việc hai method có cùng tham số nhưng khác kiểu trả về không tạo thành overload hợp lệ trong mã nguồn Java.

**Không ghi `this` vào descriptor.** Method instance `String label(int id)` vẫn có `(I)Ljava/lang/String;`, mặc dù lúc gọi JVM cần object receiver. Tương tự, constructor `Person(String name)` có tên đặc biệt `<init>` trong bytecode và descriptor `(Ljava/lang/String;)V`; `V` ở đây không có nghĩa constructor khai báo trả về `void` trong mã nguồn. Static initializer `<clinit>` dùng `()V`.

**Varargs là mảng** ở descriptor: `void log(String... lines)` và `void log(String[] lines)` có cùng descriptor `([Ljava/lang/String;)V` (vì vậy không thể khai báo cả hai để overload). `throws IOException` không đổi descriptor; exception là thông tin khác của method.

Với method descriptor, JVMS còn quy định tổng độ dài tham số không quá 255 *units*: `long`/`double` đóng góp hai units, kiểu khác một unit; đối với method instance, tính thêm một unit cho receiver. Đây là ràng buộc định dạng/kiểm tra bytecode, không phải cú pháp nhìn thấy trong source.

## 5. Vì sao descriptor quan trọng khi đọc bytecode?

Ở class file, `field_info` và `method_info` tham chiếu chuỗi descriptor trong constant pool. Các tham chiếu symbolic đến field hoặc method cũng gắn với tên và descriptor thông qua các cấu trúc constant pool tương ứng. Nhờ vậy JVM biết đúng loại dữ liệu và chữ ký cần liên kết.

Xét đoạn mã minh họa:

```java
class Example {
    String[][] names;

    int count(String[] values) {
        return values.length;
    }
}
```

Trong class file, field `names` có descriptor `[[Ljava/lang/String;` và method `count` có descriptor `([Ljava/lang/String;)I`. Ta có thể kiểm tra sau khi biên dịch bằng `javap -s -p Example`. Những dòng tương ứng sẽ có dạng:

```text
java.lang.String[][] names;
  descriptor: [[Ljava/lang/String;

int count(java.lang.String[]);
  descriptor: ([Ljava/lang/String;)I
```

`javap` hiển thị khai báo theo cách dễ đọc và đồng thời in descriptor thực tế từ class file. Dùng thêm `javap -c -p Example` nếu cần quan sát bytecode lệnh; `-s` mới là tùy chọn tập trung vào descriptor.

Descriptor tuân theo *erasure* của Java generics. Ví dụ:

```java
java.util.List<String> normalize(java.util.List<Integer> input)
```

Descriptor của phương thức trên là:

```text
(Ljava/util/List;)Ljava/util/List;
```

`String` và `Integer` là generic type arguments nên không có trong descriptor này. Kiểu biến generic có upper bound cũng bị xóa về kiểu bound phù hợp (hoặc `Object` nếu không có bound tương ứng). Nếu cần biết type arguments ở runtime, phải xét metadata generic khi có, chẳng hạn `Signature` và reflection `getGenericParameterTypes()`; đừng suy ra chúng từ descriptor.

Khi compiler tạo **bridge method** để giữ tính tương thích sau erasure, bridge là một method thật trong class file và có descriptor riêng; đây là lý do kết quả `javap -v` đôi khi có nhiều method hơn số method thấy trực tiếp trong source.

## 6. Tên lớp mảng trong reflection khác descriptor ở chỗ nào?

Java có nhiều API trả về **cách viết tên khác nhau**; đừng chuyển đổi bằng cách thay dấu `.` thành `/` một cách mù quáng.

| Biểu thức Java 17 | Kết quả |
|---|---|
| `String.class.getName()` | `java.lang.String` |
| `String.class.descriptorString()` | `Ljava/lang/String;` |
| `int.class.getName()` | `int` |
| `int.class.descriptorString()` | `I` |
| `String[][].class.getName()` | `[[Ljava.lang.String;` |
| `String[][].class.getTypeName()` | `java.lang.String[][]` |
| `String[][].class.descriptorString()` | `[[Ljava/lang/String;` |
| `String[][].class.getComponentType().descriptorString()` | `[Ljava/lang/String;` |

Điểm tinh tế: `Class.getName()` đối với **mảng tham chiếu** cho dạng tên mảng có `[` và `L...;`, nhưng dùng **dấu chấm** trong tên phần tử (`[[Ljava.lang.String;`); descriptor trong class file dùng **dấu gạch chéo** (`[[Ljava/lang/String;`).

Khi cần lấy `Class<?>` qua `Class.forName`:

- `Class.forName("java.lang.String")`: class thường, dùng binary name.
- `Class.forName("[[Ljava.lang.String;")`: lớp mảng `String[][]`, dùng dạng tên mà `Class.getName()` trả về cho mảng.
- `Class.forName("[[I")`: lớp mảng nguyên thủy `int[][]`.
- `Class.forName("Ljava/lang/String;")` và `Class.forName("[Ljava/lang/String;")` **không phải cách truyền tên hợp lệ** cho các lớp trên.

Trong Java 17, `Class.descriptorString()` là cách trực tiếp lấy descriptor cho kiểu, còn `java.lang.invoke.MethodType.descriptorString()` cung cấp method descriptor. `MethodType.fromMethodDescriptorString(descriptor, loader)` chuyển ngược method descriptor thành một `MethodType` và phân giải các tên lớp tham chiếu bằng loader được cung cấp.

## 7. Ví dụ Java 17 chạy độc lập

Tạo file `DescriptorDemo.java`:

```java
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

public class DescriptorDemo {
    static String format(int id, String[] tags) {
        return id + ":" + tags.length;
    }

    public static void main(String[] args) throws Exception {
        System.out.println(int.class.descriptorString());
        System.out.println(String.class.descriptorString());
        System.out.println(String[][].class.descriptorString());
        System.out.println(String[][].class.getName());
        System.out.println(
                String[][].class.getComponentType().descriptorString());

        Method method = DescriptorDemo.class.getDeclaredMethod(
                "format", int.class, String[].class);
        MethodType type = MethodType.methodType(
                method.getReturnType(), method.getParameterTypes());
        System.out.println(type.descriptorString());

        Class<?> arrayClass = Class.forName("[[Ljava.lang.String;");
        System.out.println(arrayClass == String[][].class);

        MethodType parsed = MethodType.fromMethodDescriptorString(
                type.descriptorString(),
                DescriptorDemo.class.getClassLoader());
        System.out.println(parsed.parameterCount());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac DescriptorDemo.java
java DescriptorDemo
```

Stdout chính xác:

```text
I
Ljava/lang/String;
[[Ljava/lang/String;
[[Ljava.lang.String;
[Ljava/lang/String;
(I[Ljava/lang/String;)Ljava/lang/String;
true
2
```

Ý nghĩa:

- Năm dòng đầu đối chiếu primitive, class, mảng hai chiều, cách viết của `getName()` và component type.
- Dòng method descriptor sinh từ kiểu trả về `String` cùng hai tham số `int`, `String[]`. Vì method `format` là static nên không có receiver để nhầm với tham số.
- Giá trị `true` cho thấy chuỗi tên mảng theo `getName()` có thể đưa vào `Class.forName` để nhận chính đối tượng `Class` đó.
- `2` là số **tham số method**, khác với số chiều mảng và số ký tự trong descriptor.

Xem trực tiếp metadata đã biên dịch:

```bash
javap -s -p DescriptorDemo
```

Trong output, method `format` sẽ có dòng:

```text
descriptor: (I[Ljava/lang/String;)Ljava/lang/String;
```

Lưu ý: `MethodType` biểu diễn danh sách tham số và kiểu trả về; khi sử dụng method handle cho một phương thức instance, loại method handle cụ thể có thể bao gồm receiver trong *method type của handle*. Điều đó không thay đổi quy tắc descriptor của method khai báo trong class file.

## 8. Descriptor, tên và class loader khi liên kết kiểu

Descriptor cho biết **cần loại kiểu nào**, nhưng một tham chiếu như `Lcom/example/Plugin;` còn phải được giải quyết trong **ngữ cảnh class loader**. JVM không coi hai lớp có cùng binary name do hai defining class loader khác nhau tạo ra là cùng một runtime type. Vì thế hai `Class<?>` có thể có `descriptorString()` giống nhau nhưng `==` là `false`.

Với mảng `[Lcom/example/Plugin;`, kiểu phần tử tham chiếu `com.example.Plugin` cũng chịu quy tắc này. Hai loader khác nhau có thể dẫn đến hai lớp mảng khác nhau dù chuỗi descriptor giống hệt. Ngược lại, descriptor mảng `[[I` chỉ chứa primitive `int` nên không có tên class người dùng cần resolve.

Điều cần nhớ khi xử lý bytecode hoặc API động:

1. Dùng **descriptor** để hiểu chữ ký ở mức JVM; dùng **binary name** đúng chuẩn khi gọi API yêu cầu tên lớp như `Class.forName`.
2. Khi parse method descriptor, đi từng kiểu theo ngữ pháp. Không thể cắt tham số theo dấu phẩy (descriptor không có dấu phẩy) hay lấy từng ký tự (một object type có nhiều ký tự tới dấu `;`).
3. Khi cần biến descriptor thành runtime `Class`/`MethodType`, phải tính tới loader có thể resolve class được nhắc đến; chỉ có chuỗi descriptor chưa xác nhận class có tồn tại hoặc loader hiện tại truy cập được nó.
4. Không coi descriptor là nơi lưu thông tin generic, tên parameter, nullability hay annotations.

## 9. Cách đọc descriptor nhanh và lỗi hay gặp

Một quy trình đọc có thể dùng ngay:

1. Nếu chuỗi bắt đầu bằng `(`, đọc như **method descriptor**: parse lần lượt các tham số tới `)`, sau đó parse đúng một kiểu trả về.
2. Với mỗi kiểu: `B/C/D/F/I/J/S/Z` là primitive; `L` yêu cầu đọc tới dấu `;`; mỗi `[` tăng thêm một chiều mảng, rồi parse **một** kiểu phần tử.
3. Chuyển `/` trong tên nội bộ sang package dạng dấu chấm để giải thích theo Java; giữ `$` khi cần nói chính xác binary name của nested class.
4. Kiểm tra `V` chỉ xuất hiện khi làm method return type, và bảo đảm không có ký tự thừa sau kiểu cuối.

| Lỗi thường gặp | Vì sao sai | Dạng đúng |
|---|---|---|
| Viết `Lint;` | `int` là primitive, không phải class | `I` |
| Viết `Ljava.lang.String;` trong class-file descriptor | Tên nội bộ dùng `/` | `Ljava/lang/String;` |
| Quên `;` sau object type | Không biết nơi kết thúc kiểu tham chiếu | `Ljava/lang/String;` |
| Viết `[V` | Không tồn tại mảng `void[]` | Mảng cần kiểu phần tử hợp lệ như `[I` |
| Viết `(I, J) V` | Descriptor không có dấu phẩy/khoảng trắng | `(IJ)V` |
| Viết `(String[])String` | Đó là ký pháp gần với source, chưa phải descriptor | `([Ljava/lang/String;)Ljava/lang/String;` |
| Ghi receiver vào descriptor instance | Receiver `this` được JVM xử lý ngầm | `int size()` → `()I` |
| Nghĩ `List<String>` giữ `String` trong descriptor | Generic arguments bị erasure | `Ljava/util/List;` |

### Tự kiểm tra

Hãy tự giải mã trước khi xem đáp án:

1. `[[D` mô tả kiểu nào?
2. `(Ljava/lang/String;[[I)Z` mô tả chữ ký nào?
3. Descriptor của `void print(long id, String... labels)`?
4. Descriptor của field kiểu `java.util.Map<String, Integer>[]`?
5. Descriptor của `Object[][] build(byte[] bytes, double factor)`?

**Đáp án:**

1. `double[][]`.
2. Method nhận `String` và `int[][]`, trả về `boolean`.
3. `(J[Ljava/lang/String;)V`, vì varargs được biểu diễn là mảng.
4. `[Ljava/util/Map;`, vì arguments `String` và `Integer` bị erasure.
5. `([BD)[[Ljava/lang/Object;`: `[B` là `byte[]`, `D` là `double` và `[[Ljava/lang/Object;` là `Object[][]`.

## 10. Ghi nhớ và tài liệu chuẩn

- **Kiểu nguyên thủy:** `B C D F I J S Z`; `V` chỉ dành cho kiểu trả về `void`.
- **Class/interface:** `L` + internal name + `;`.
- **Mảng:** một `[` cho mỗi chiều, sau đó là descriptor kiểu phần tử.
- **Method:** `(` + các descriptor tham số ghép liền + `)` + descriptor trả về.
- **Class loader:** descriptor là mô tả cú pháp; danh tính runtime còn phụ thuộc nơi và cách tên lớp được resolve.

Tham khảo chính thức:

- [Java Virtual Machine Specification, §4.2–4.3: Names và Descriptors](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3).
- [Java SE 17 `Class.descriptorString()`, `getName()` và `getComponentType()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).
- [Java SE 17 `MethodType` và `fromMethodDescriptorString`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html).