# Class đại diện cho primitive, void, mảng, interface, enum và record

## 1. Vì sao các kiểu này đều có đối tượng Class?

Trong Java Reflection, `java.lang.Class<?>` là đối tượng mô tả **một kiểu tại runtime**. Không chỉ lớp thông thường như `String`, Java còn có đối tượng `Class` cho tám kiểu nguyên thủy, `void`, mọi kiểu mảng, interface, enum và record. Ta dùng nó để hỏi một kiểu thuộc nhóm nào, có thành phần gì và có quan hệ kế thừa/triển khai ra sao.

Đối tượng `Class` **không phải** instance của kiểu đang được mô tả. Ví dụ `int.class` mô tả kiểu `int`, nhưng bản thân nó là một đối tượng thuộc `Class`; `void.class` tồn tại dù không thể tạo giá trị `void`. Kiểu khai báo của biến chứa metadata thường là `Class<?>` để chấp nhận nhiều loại kiểu khác nhau.

| Loại được mô tả | Ví dụ lấy `Class` | Phép kiểm tra tiêu biểu | Ý nghĩa |
| --- | --- | --- | --- |
| Primitive | `int.class`, `boolean.class` | `isPrimitive()` | Một trong tám kiểu nguyên thủy |
| `void` | `void.class` | `isPrimitive()` trả `true`; so riêng với `void.class` | Biểu diễn việc không có giá trị trả về |
| Mảng | `String[].class`, `int[][].class` | `isArray()` | Kiểu mảng, độc lập với kiểu thành phần |
| Interface | `Runnable.class` | `isInterface()` | Kiểu giao diện; annotation cũng là một interface |
| Enum | `Level.class` với `enum Level` | `isEnum()` | Lớp enum khai báo trong mã nguồn |
| Record | `Person.class` với `record Person(...)` | `isRecord()` | Lớp record và danh sách thành phần record |

Một lớp thông thường như `String.class` có thể trả `false` cho **tất cả** các phép kiểm tra trong bảng; điều đó không có nghĩa `Class` không nhận diện được nó. Những phép kiểm tra này phân loại đặc điểm của kiểu, không phải phép thử “có phải đối tượng `Class` hay không”.

## 2. Cách lấy đối tượng Class

- **Class literal**: `int.class`, `void.class`, `int[].class`, `Runnable.class`, `Level.class`, `Person.class`. Đây là cách rõ ràng nhất khi biết kiểu ở thời điểm biên dịch.
- **Từ một object**: `value.getClass()` cho biết lớp runtime của đối tượng. `getClass()` không gọi được trên giá trị primitive hay `void`; khi primitive bị boxing, kết quả là lớp wrapper (`Integer`, `Boolean`...), không phải kiểu nguyên thủy.
- **Từ tên kiểu khi chạy**: `Class.forName("java.lang.String")` tìm theo tên nhị phân. Với mảng, tên nhận vào phải theo cú pháp JVM, chẳng hạn `"[I"` cho `int[]` và `"[[Ljava.lang.String;"` cho `String[][]`. `Class.forName("int")` và `Class.forName("java.lang.String[]")` đều không phải cách tìm tương ứng và gây `ClassNotFoundException`.

Ví dụ:

~~~java
Class<?> primitive = int.class;
Class<?> noValue = void.class;
Class<?> array = String[][].class;
Class<?> wrapper = Integer.valueOf(42).getClass();

System.out.println(primitive == Integer.TYPE);    // true
System.out.println(noValue == Void.TYPE);          // true
System.out.println(wrapper == Integer.class);      // true
System.out.println(wrapper == int.class);          // false
~~~

Đoạn trên là **fragment đặt bên trong một phương thức Java**, không phải chương trình độc lập. `Integer.TYPE` và `Void.TYPE` lần lượt tham chiếu đối tượng `Class` của `int` và `void`. `Class.forName(String)` có thể kích hoạt khởi tạo lớp; nếu chỉ cần tải metadata mà không khởi tạo lớp, có overload `Class.forName(name, false, loader)` (vẫn cần tên hợp lệ và class loader thích hợp).

## 3. Primitive và void: cùng isPrimitive(), khác ngữ nghĩa

Java có tám primitive: `boolean`, `byte`, `short`, `char`, `int`, `long`, `float` và `double`. Từng kiểu có `Class` riêng do JVM cung cấp. **`void.class.isPrimitive()` cũng trả `true`** theo hợp đồng API `Class`, dù `void` không phải kiểu cho biến hoặc object có giá trị; đó là trường hợp đặc biệt cần xử lý trước khi phân loại “primitive có giá trị”.

~~~java
System.out.println(int.class.isPrimitive());     // true
System.out.println(void.class.isPrimitive());    // true
System.out.println(Integer.class.isPrimitive()); // false
System.out.println(int[].class.isPrimitive());   // false
System.out.println(void.class.getName());        // void
~~~

Chú ý:

- `int.class != Integer.class`: primitive và wrapper là hai kiểu khác nhau; autoboxing không làm chúng thành cùng đối tượng `Class`.
- `Class#isInstance(Object)` không thay được việc kiểm tra giá trị primitive: giá trị truyền cho tham số `Object` phải là reference, và `int.class.isInstance(Integer.valueOf(1))` trả `false`.
- Không có `void[]` hợp lệ, không thể tạo đối tượng bằng `void.class`. Khi phản chiếu phương thức, `Method#getReturnType() == void.class` cho biết phương thức trả về `void`.
- `getSuperclass()` của primitive và `void` trả `null`; `isInterface()` và `isArray()` đều trả `false`.

## 4. Mảng: Class của mảng khác Class của thành phần

Mỗi kiểu mảng có `Class` của chính nó: `int[].class` khác `int.class`, còn `int[][].class` khác `int[].class`. Mảng luôn là **reference type** dù chứa các phần tử primitive. Java cung cấp `isArray()` và `getComponentType()` để bóc tách từng chiều:

~~~java
Class<?> matrix = int[][].class;
System.out.println(matrix.isArray());                           // true
System.out.println(matrix.getComponentType() == int[].class);  // true
System.out.println(matrix.getComponentType()
                         .getComponentType() == int.class);     // true
System.out.println(String.class.getComponentType() == null);    // true
~~~

`getComponentType()` chỉ bỏ **một** chiều mảng mỗi lần. `Class#getTypeName()` thuận tiện để hiển thị tên dễ đọc, còn `getName()` của mảng trả cú pháp descriptor JVM:

| Biểu thức | Giá trị |
| --- | --- |
| `int[].class.getName()` | `[I` |
| `int[][].class.getName()` | `[[I` |
| `String[].class.getName()` | `[Ljava.lang.String;` |
| `String[][].class.getName()` | `[[Ljava.lang.String;` |
| `String[][].class.getTypeName()` | `java.lang.String[][]` |

Dấu `[` biểu thị một chiều; `I` là descriptor của `int`, còn `L...;` bao tên nhị phân của lớp tham chiếu. Với một đối tượng mảng, `Array.getLength(array)` đọc số phần tử và `Array.newInstance(componentType, length)` tạo mảng bằng reflection. `int[].class.getSuperclass() == Object.class` là `true`; mọi kiểu mảng cũng triển khai `Cloneable` và `java.io.Serializable`. Chúng **không** được phân loại là primitive vì phần tử là primitive.

## 5. Interface: phát hiện và xác định khả năng gán kiểu

`SomeInterface.class.isInterface()` trả `true` cho interface; `getSuperclass()` của interface trả `null`. Muốn biết một lớp có thể gán vào biến của interface hay không, dùng `isAssignableFrom` với đúng chiều:

~~~java
interface Reader { void read(); }
final class FileReaderImpl implements Reader {
    public void read() {}
}

System.out.println(Reader.class.isInterface());                    // true
System.out.println(Reader.class.isAssignableFrom(
        FileReaderImpl.class));                                     // true
System.out.println(FileReaderImpl.class.isAssignableFrom(
        Reader.class));                                             // false
~~~

Đây là fragment mô tả các kiểu và câu lệnh trong ngữ cảnh hợp lệ; chương trình độc lập hoàn chỉnh có ở phần 8. Đọc `A.class.isAssignableFrom(B.class)` là: “Một đối tượng kiểu `B` có thể gán cho biến kiểu `A` không?”. `Reader.class.isInstance(new FileReaderImpl())` cũng trả `true`; nó kiểm tra **một object**, trong khi `isAssignableFrom` so sánh **hai kiểu**.

Một annotation khai báo bằng `@interface` cũng là một loại interface. Vì vậy, với annotation type, cả `isInterface()` lẫn `isAnnotation()` đều có thể là `true`. Nếu chương trình phải phân biệt annotation với interface thường, kiểm tra `isAnnotation()` trước.

## 6. Enum: nhận diện lớp enum và lấy các hằng

Với `enum Level { LOW, HIGH }`, `Level.class.isEnum()` trả `true`. `Level.class.getEnumConstants()` trả mảng `Level[]` chứa các hằng theo thứ tự khai báo; với kiểu không phải enum, `getEnumConstants()` trả `null`. Mảng kết quả của một enum không chứa phần tử là điều hợp lệ nếu enum khai báo không có hằng nào.

~~~java
enum Level { LOW, HIGH }

System.out.println(Level.class.isEnum());                    // true
System.out.println(java.util.Arrays.toString(
        Level.class.getEnumConstants()));                     // [LOW, HIGH]
System.out.println(String.class.getEnumConstants() == null); // true
System.out.println(Enum.class.isEnum());                     // false
~~~

`Enum` là **lớp cơ sở** của các enum, bản thân nó không được khai báo bằng `enum` nên `Enum.class.isEnum()` là `false`. Một enum constant có class body riêng có thể có `constant.getClass()` là lớp con ẩn danh, khiến `constant.getClass().isEnum()` trả `false`; muốn xác định **enum khai báo hằng**, dùng `constant.getDeclaringClass()`. Không giả định mọi đối tượng enum đều trả cùng một `getClass()` trong trường hợp này.

## 7. Record: metadata theo record components

Record (được chuẩn hóa từ Java 16, dùng ổn định trên Java 17+) khai báo tập thành phần dữ liệu ngay trong header:

~~~java
record Person(String name, int age) {}
~~~

`Person.class.isRecord()` trả `true`. `Person.class.getRecordComponents()` trả `RecordComponent[]` theo **thứ tự khai báo trong header**. Mỗi `RecordComponent` cho biết tên (`getName()`), kiểu (`getType()`), kiểu tổng quát (`getGenericType()`) và phương thức truy cập (`getAccessor()`).

~~~java
for (java.lang.reflect.RecordComponent component
        : Person.class.getRecordComponents()) {
    System.out.println(component.getName()
            + ": " + component.getType().getSimpleName());
}
// name: String
// age: int
~~~

`getRecordComponents()` trả `null` nếu kiểu **không phải record**, nhưng trả mảng không-null, có thể rỗng, nếu kiểu **là record**. Do đó, nên kiểm tra `isRecord()` hoặc `null` trước khi duyệt. `Record.class.isRecord()` là `false` vì `java.lang.Record` chỉ là lớp cơ sở; lớp record cụ thể có superclass trực tiếp là `Record` và là `final`.

**Record component khác với Java field.** `getDeclaredFields()` trả metadata field do JVM mô tả, còn `getRecordComponents()` phản ánh hợp đồng thành phần khai báo trong header và giữ thứ tự của header. Record có các field thành phần là `private final`, accessor công khai và các phương thức cơ bản do trình biên dịch hỗ trợ, nhưng tính bất biến là **nông**: nếu một component giữ reference đến đối tượng mutable, dữ liệu bên trong vẫn có thể thay đổi.

## 8. Ví dụ Java 17+ hoàn chỉnh, có thể biên dịch và chạy

Tạo tệp `ReflectionClassKindsDemo.java` với nội dung sau. Ví dụ gom sáu nhóm kiểu vào một chương trình và in những đặc điểm đáng kiểm chứng:

~~~java
import java.lang.reflect.RecordComponent;
import java.util.Arrays;

public class ReflectionClassKindsDemo {
    interface Payment { void pay(); }

    static final class Card implements Payment {
        public void pay() {}
    }

    enum Level { LOW, HIGH }

    record Person(String name, int age) {}

    public static void main(String[] args) throws ClassNotFoundException {
        System.out.println("int/void: " + int.class.isPrimitive() + "/" + void.class.isPrimitive());
        System.out.println("int vs Integer.TYPE: " + (int.class == Integer.TYPE));
        System.out.println("wrapper distinct: " + (int.class != Integer.class));

        Class<?> grid = String[][].class;
        System.out.println("array: " + grid.isArray() + ", name=" + grid.getName());
        System.out.println("component: " + grid.getComponentType().getTypeName());
        System.out.println("loaded int[]: " + (Class.forName("[I") == int[].class));

        System.out.println("interface: " + Payment.class.isInterface());
        System.out.println("implemented: " + Payment.class.isAssignableFrom(Card.class));
        System.out.println("enum: " + Level.class.isEnum());
        System.out.println("constants: " + Arrays.toString(Level.class.getEnumConstants()));
        System.out.println("record: " + Person.class.isRecord());
        for (RecordComponent component : Person.class.getRecordComponents()) {
            System.out.println("component: " + component.getName() + ":" + component.getType().getSimpleName()
                    + ", accessor=" + component.getAccessor().getName());
        }
        System.out.println("Enum base: " + Enum.class.isEnum());
        System.out.println("Record base: " + Record.class.isRecord());
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp:

~~~bash
javac ReflectionClassKindsDemo.java
java ReflectionClassKindsDemo
~~~

Stdout chính xác (đã đối chiếu bằng Java 21, mã tương thích Java 17):

~~~text
int/void: true/true
int vs Integer.TYPE: true
wrapper distinct: true
array: true, name=[[Ljava.lang.String;
component: java.lang.String[]
loaded int[]: true
interface: true
implemented: true
enum: true
constants: [LOW, HIGH]
record: true
component: name:String, accessor=name
component: age:int, accessor=age
Enum base: false
Record base: false
~~~

Vì `Person` là record lồng bên trong lớp demo, tên nhị phân đầy đủ của nó có ký tự `$` (`ReflectionClassKindsDemo$Person`), nhưng `Person.class.getSimpleName()` vẫn là `Person`. Ví dụ cố ý dùng `getSimpleName()` cho component để output ổn định, tránh phụ thuộc package.

## 9. Áp dụng: phân loại kiểu trong công cụ reflection

Một công cụ khám phá schema, serializer hoặc trình hiển thị metadata có thể nhận `Class<?>` bất kỳ và quyết định cách xử lý. Thứ tự kiểm tra giúp tránh nhầm `void` với primitive có giá trị và annotation với interface thường:

~~~java
static String classify(Class<?> type) {
    if (type == void.class) return "void";
    if (type.isPrimitive()) return "primitive";
    if (type.isArray()) return "array";
    if (type.isAnnotation()) return "annotation";
    if (type.isInterface()) return "interface";
    if (type.isEnum()) return "enum";
    if (type.isRecord()) return "record";
    return "ordinary/other class";
}
~~~

Đặt phương thức này trong một class; đây là **fragment minh họa**, còn phần 8 là chương trình chạy độc lập. Nếu nhận `int[][]`, có thể duyệt `getComponentType()` nhiều lần để lấy cả số chiều lẫn kiểu phần tử. Nếu nhận enum, `getEnumConstants()` giúp lấy danh sách giá trị hợp lệ. Nếu nhận record, `getRecordComponents()` giúp lấy đúng danh sách thành phần theo thứ tự định nghĩa. Với interface, dùng `isAssignableFrom()` để kiểm tra các implementation phù hợp.

Không tự suy ra một kiểu là record chỉ vì nó có phương thức `name()` hoặc nhiều field `final`: phải dùng `isRecord()`. Tương tự, đừng xem mọi subclass của `Enum` là một enum declaration, và đừng nhận diện interface chỉ bằng modifier `abstract`.

## 10. Các nhầm lẫn thường gặp và tự kiểm tra

1. **Primitive khác wrapper:** `int.class` và `Integer.class` khác nhau. `new Integer(...)` cũng không cần thiết; boxing thành `Integer` không biến metadata thành `int.class`.
2. **`void` đặc biệt:** `void.class.isPrimitive()` là `true`, nhưng `void` không có instance hay mảng hợp lệ; so `type == void.class` khi cần phân biệt riêng.
3. **Mảng là một kiểu riêng:** `int[].class.isArray()` là `true`, `int[].class.isPrimitive()` là `false` và `getComponentType() == int.class` là `true`.
4. **Tên kiểu để load:** `Class.forName("int")` thất bại; `Class.forName("[I")` tìm được `int[]`. `getTypeName()` dành cho hiển thị dễ đọc; `getName()` của mảng mang dạng descriptor JVM.
5. **Hướng của quan hệ gán:** `Interface.class.isAssignableFrom(Implementation.class)` kiểm tra implementation có gán được cho interface; đảo chiều thường là `false`.
6. **Enum/record là kiểu khai báo cụ thể:** `Enum.class.isEnum()` và `Record.class.isRecord()` đều là `false`; muốn có constants hay components thì kiểm tra đúng class khai báo.
7. **Giá trị trả về của API:** `getEnumConstants()` và `getRecordComponents()` có thể trả `null` khi không đúng loại. Không duyệt trực tiếp trước khi kiểm tra.

Tự trả lời:

- `int[][].class.getComponentType() == int[].class` là đúng hay sai? **Đúng** vì mỗi lần lấy component chỉ bỏ một chiều.
- `void.class.isPrimitive()` có thể dùng để quyết định kiểu có thể chứa một giá trị primitive không? **Không**; `void` là ngoại lệ dù API trả `true`.
- Một class có các field `final` và accessor trông giống record thì `isRecord()` có chắc là `true`? **Không**; chỉ class thực sự khai báo bằng `record` mới thỏa điều kiện.
- Nếu nhận `Class<?>` từ plugin bên ngoài, cần phân biệt annotation interface với interface thường bằng gì? **`isAnnotation()` trước `isInterface()`**.

Tài liệu chuẩn để tra cứu thêm: [Javadoc `Class` (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html), [Javadoc `RecordComponent` (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/RecordComponent.html) và [JLS 17 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10).