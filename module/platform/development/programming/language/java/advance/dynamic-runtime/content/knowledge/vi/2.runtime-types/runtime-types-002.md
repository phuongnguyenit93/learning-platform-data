# 2.2 Kiểu nguyên thủy, `void`, mảng, `interface`, `enum` và `record` trong mô hình `Class`

Trong Java, `java.lang.Class` là điểm nhìn thống nhất để khảo sát **kiểu ở thời điểm chạy** (runtime type). Một đối tượng `Class<?>` có thể biểu diễn lớp thông thường, interface, enum, record, lớp mảng, một trong tám kiểu nguyên thủy hoặc `void`. Điều đó **không có nghĩa** mọi kiểu được biểu diễn đều có thể khởi tạo bằng `new`, có constructor, hoặc chứa một đối tượng để truyền cho `isInstance`.

Sau bài này, bạn cần phân biệt đúng các loại kiểu qua Reflection, hiểu quan hệ kiểu của mảng và các kiểu đặc biệt, biết chọn API phù hợp để khám phá enum/record, và tránh suy luận sai từ `getClass()`, `getSuperclass()` hay `isAssignableFrom()`.

## 1. Một mô hình `Class<?>`, nhiều bản chất kiểu

Ví dụ sau đều hợp lệ và đều cho một đối tượng `Class`:

```java
Class<?> primitive = int.class;
Class<?> noReturn = void.class;
Class<?> array = String[][].class;
Class<?> abstraction = Runnable.class;
Class<?> enumeration = Thread.State.class;
Class<?> recordType = Record.class;
```

**Lưu ý:** `Record.class` là lớp nền `java.lang.Record`, **không phải** chính nó là một khai báo `record`; do đó `Record.class.isRecord()` trả `false`. Muốn có kiểu record thực sự, cần khai báo chẳng hạn `record Point(int x, int y) {}`, rồi dùng `Point.class`.

`Class` trả lời hai nhóm câu hỏi khác nhau:

- **Phân loại kiểu:** `isPrimitive()`, `isArray()`, `isInterface()`, `isEnum()`, `isRecord()`, `isAnnotation()`.
- **Khảo sát cấu trúc và quan hệ:** `getComponentType()`, `getSuperclass()`, `getInterfaces()`, `getEnumConstants()`, `getRecordComponents()`, `isAssignableFrom(...)`, `isInstance(...)`.

Các cờ phân loại không thay thế cho nhau. Interface có thể là kiểu annotation; một enum có thể thực thi interface; một record có thể thực thi interface; nhưng chỉ khai báo `enum` mới có `isEnum() == true`, và chỉ khai báo `record` mới có `isRecord() == true`.

| Loại kiểu | Ví dụ `Class` | Nhận diện chính | Lớp cha trực tiếp theo Reflection |
| --- | --- | --- | --- |
| Nguyên thủy | `int.class`, `boolean.class` | `isPrimitive()` là `true` | `getSuperclass() == null` |
| `void` | `void.class` | So sánh `type == void.class`; `isPrimitive()` là `false` | `null` |
| Mảng | `int[].class`, `String[][].class` | `isArray()` | `Object.class` |
| Interface | `Runnable.class` | `isInterface()` | `null` |
| Enum khai báo | `Thread.State.class` | `isEnum()` | `Enum.class` |
| Record khai báo | `Point.class` với `record Point(...)` | `isRecord()` | `Record.class` |

Bảng nói về `Class.getSuperclass()`, không phải mọi quan hệ gán kiểu. Ví dụ mảng có superclass là `Object` và đồng thời thực thi `Cloneable`, `java.io.Serializable`; interface không có superclass nhưng có thể kế thừa nhiều interface khác.

## 2. Lấy đối tượng `Class` đúng cách

Có ba cách quen thuộc nhưng phạm vi khác nhau:

```java
Class<?> c1 = int.class;                  // class literal: dùng được với primitive/void
Class<?> c2 = "hello".getClass();         // lấy từ một đối tượng thực
Class<?> c3 = Class.forName("java.lang.String"); // tra cứu theo tên binary
```

- `T.class` được kiểm tra ở thời điểm biên dịch; hỗ trợ kiểu nguyên thủy, `void`, mảng và kiểu tham chiếu.
- `value.getClass()` yêu cầu một **reference object** khác `null`. Biến nguyên thủy không có phương thức `getClass()`. Nếu viết `((Object) 7).getClass()`, boxing tạo `Integer`, nên kết quả là `Integer.class`, **không phải** `int.class`.
- `Class.forName(String)` tra cứu tên binary của kiểu tham chiếu hoặc tên biểu diễn lớp mảng theo quy ước JVM; **`Class.forName("int")` và `Class.forName("void")` ném `ClassNotFoundException`**. Với kiểu nguyên thủy và `void`, dùng literal hoặc hằng `TYPE`.

`Class.forName(String)` cũng có thể kích hoạt khởi tạo lớp (class initialization) nếu lớp chưa được khởi tạo. Khi chỉ cần metadata trong công cụ phân tích, cân nhắc overload `Class.forName(name, false, loader)` và vẫn xử lý `ClassNotFoundException`, quyền truy cập và class loader phù hợp. Với mảng, dùng tên lớp mảng dạng descriptor như `"[I"` hoặc `"[Ljava.lang.String;"`, không dùng tên trình bày `"int[]"` hay `"java.lang.String[]"`.

`Class<?>` là một **đối tượng metadata**, không tự tạo ra instance của kiểu tương ứng. Đừng đồng nhất `Class` với instance, hoặc tưởng rằng nhìn thấy `Class` thì chắc chắn có constructor công khai.

## 3. Tám primitive và `void`: cùng có `Class` nhưng không phải reference type

Tám primitive là `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double`. Mỗi kiểu có đúng một `Class` tương ứng trong một JVM, chẳng hạn `int.class`. Hằng `TYPE` của wrapper khớp với literal:

```java
System.out.println(int.class == Integer.TYPE);   // true
System.out.println(boolean.class == Boolean.TYPE); // true
System.out.println(void.class == Void.TYPE);      // true
System.out.println(int.class.isPrimitive());      // true
System.out.println(void.class.isPrimitive());     // false
System.out.println(Integer.class.isPrimitive());  // false
System.out.println(Void.class.isPrimitive());     // false
```

`void` diễn tả phương thức không trả giá trị; nó không phải kiểu dữ liệu dùng để khai báo biến chứa giá trị. Mặc dù `void.class` tồn tại, không có mảng `void[]`, không thể tạo instance `void`, và `void` không nằm trong tám kiểu được `isPrimitive()` nhận diện. `Void.class` là lớp `java.lang.Void` khác `void.class`; tên giống nhau không làm chúng thành cùng một kiểu.

Những phép kiểm tra Reflection cần nhớ:

```java
int.class.getSuperclass() == null             // true
void.class.getSuperclass() == null            // true
int.class.isInstance(Integer.valueOf(5))      // false
int.class.isAssignableFrom(int.class)         // true
long.class.isAssignableFrom(int.class)        // false
Number.class.isAssignableFrom(int.class)      // false
Number.class.isAssignableFrom(Integer.class)  // true
```

`isAssignableFrom` phản ánh quan hệ kiểu trong mô hình runtime, **không áp dụng** numeric widening (`int` sang `long`) hay boxing (`int` sang `Integer`) như quy tắc chuyển đổi biểu thức của Java. Tương tự, `isInstance(Object)` không thể nhận một đối tượng primitive trực tiếp; đối số `Object` sau boxing là wrapper, và `int.class.isInstance(...)` vẫn `false`.

Khi viết framework nhận tham số phương thức, tách biệt chính xác `int.class` và `Integer.class`. Chúng có thể cần quy tắc chuyển đổi/boxing ở tầng gọi phương thức, nhưng không thể thay thế nhau chỉ bằng `isAssignableFrom`.

## 4. Mảng: lớp được JVM tạo động, có thành phần và số chiều

Mọi mảng trong Java là **đối tượng tham chiếu** với một `Class` dành cho loại phần tử và số chiều tương ứng. `String[].class`, `String[][].class` và `int[].class` là các kiểu khác nhau. `isArray()` nhận diện chúng; `getComponentType()` trả về kiểu của phần tử ở **một chiều ngay bên trong**:

```java
int[][].class.isArray()                          // true
int[][].class.getComponentType() == int[].class  // true
int[].class.getComponentType() == int.class      // true
String[].class.getComponentType() == String.class // true
String.class.getComponentType() == null          // true
```

Với `int[][]`, component type là `int[]` (một kiểu tham chiếu), trong khi với `int[]`, component type mới là primitive `int`. Muốn tìm phần tử cuối cùng, lặp `getComponentType()` cho đến khi `isArray()` không còn đúng.

### 4.1. Tên mảng dùng bởi Reflection

`getTypeName()` hiển thị tên dễ đọc, còn `getName()` của lớp mảng trả về tên kiểu JVM:

| `Class` | `getTypeName()` | `getName()` |
| --- | --- | --- |
| `int[].class` | `int[]` | `[I` |
| `boolean[].class` | `boolean[]` | `[Z` |
| `double[][].class` | `double[][]` | `[[D` |
| `String[].class` | `java.lang.String[]` | `[Ljava.lang.String;` |
| `String[][].class` | `java.lang.String[][]` | `[[Ljava.lang.String;` |

Một dấu `[` cho mỗi chiều; mã primitive gồm `Z` (boolean), `B` (byte), `S` (short), `C` (char), `I` (int), `J` (long), `F` (float), `D` (double). Với kiểu tham chiếu, dùng `L<tên binary>;`. Mã `V` có thể xuất hiện trong mô tả kiểu trả về phương thức cho `void`, nhưng **không** tạo nên lớp mảng `[V` hợp lệ.

Nếu cần cho người đọc, ưu tiên `getTypeName()`; nếu tương tác với tên binary/descriptor hay `Class.forName`, chú ý quy ước `getName()`. `getSimpleName()` và `getCanonicalName()` phục vụ mục đích đặt tên khác; canonical name có thể `null` đối với lớp cục bộ/vô danh, nên không mặc định mọi kiểu đều có canonical name.

### 4.2. Quan hệ kế thừa và tính hiệp biến

Bất cứ mảng nào cũng là `Object` và thực thi `Cloneable` cùng `java.io.Serializable`:

```java
String[].class.getSuperclass() == Object.class        // true
Object.class.isAssignableFrom(int[].class)            // true
Cloneable.class.isAssignableFrom(int[].class)         // true
java.io.Serializable.class.isAssignableFrom(int[].class) // true
```

**Mảng kiểu tham chiếu hiệp biến (covariant):** vì `String` là subtype của `Object`, `String[]` là subtype của `Object[]`.

```java
Object[].class.isAssignableFrom(String[].class) // true
Object[].class.isAssignableFrom(int[].class)    // false
Object[].class.isAssignableFrom(int[][].class)  // true
```

Dòng cuối đáng chú ý: mỗi phần tử của `int[][]` là một đối tượng `int[]`; vì vậy `int[][]` tương thích với `Object[]`, còn `int[]` thì không. Mảng của primitive không hiệp biến thành `Object[]` do chính phần tử `int` không phải reference object.

Hiệp biến được kiểm tra thêm **lúc chạy** khi ghi phần tử:

```java
Object[] values = new String[1];
values[0] = "ok";             // hợp lệ
// values[0] = Integer.valueOf(3); // biên dịch được nhưng ném ArrayStoreException
```

Compiler chỉ thấy biến `Object[]`, còn JVM bảo vệ loại phần tử thực sự là `String`. Với API xử lý mảng động, kiểm tra `isArray()`, `getComponentType()` và kiểu phần tử trước khi ghi; thư viện `java.lang.reflect.Array` hỗ trợ tạo/đọc/ghi mảng qua Reflection, nhưng việc có một `Class` mảng không có nghĩa mảng nhận tùy ý kiểu phần tử.

## 5. Interface: là kiểu tham chiếu, có thể có nhiều superinterface

`Runnable.class.isInterface()` là `true`, dù không thể `new Runnable()` trực tiếp. Với một interface:

- `getSuperclass()` luôn trả `null`, **không** phải `Object.class`.
- `getInterfaces()` cho các superinterface **được khai báo trực tiếp**; muốn kiểm tra toàn bộ quan hệ gián tiếp, dùng `isAssignableFrom()` hoặc tự duyệt cây interface.
- `Interface.class.isAssignableFrom(Concrete.class)` có thể là `true` nếu lớp triển khai trực tiếp hoặc gián tiếp interface.
- `isInstance(object)` trả `true` nếu object là một instance thực thi interface đó.

Ví dụ:

```java
interface Named { String name(); }
interface Audited extends Named {}
class Service implements Audited {
    @Override public String name() { return "service"; }
}
```

Trong code cùng phạm vi biên dịch, `Named.class.isAssignableFrom(Service.class)` và `Audited.class.isAssignableFrom(Service.class)` đều `true`, trong khi `Service.class.getInterfaces()` chỉ chứa `Audited.class`. `Named.class.getSuperclass()` bằng `null`.

Annotation cũng là một loại interface theo mô hình Java: đối với `@interface Marker {}`, cả `Marker.class.isAnnotation()` và `Marker.class.isInterface()` đều `true`. Nếu cần phân loại annotation riêng, kiểm tra `isAnnotation()` **trước** `isInterface()`. Không dùng `Modifier.isInterface(getModifiers())` để phân biệt annotation thông thường với interface thường; cờ `isAnnotation()` nói rõ ý nghĩa hơn.

## 6. Enum: lớp đặc biệt có các hằng cố định

Một enum như `enum Direction { NORTH, SOUTH }` là kiểu tham chiếu do compiler tạo thành một lớp dẫn xuất trực tiếp từ `java.lang.Enum<Direction>`, không phải interface và không phải primitive.

- `Direction.class.isEnum()` là `true`; `Enum.class.isEnum()` là `false`.
- `Direction.class.getSuperclass() == Enum.class` là `true` (phần generic `Enum<Direction>` có thể xem qua `getGenericSuperclass()`).
- `Direction.class.getEnumConstants()` trả mảng các hằng theo **thứ tự khai báo**. Với kiểu không phải enum, phương thức trả `null`, nên cần kiểm tra `isEnum()` trước khi duyệt.
- `Enum.valueOf(Direction.class, "NORTH")` tra hằng theo tên chính xác; `name()` là tên khai báo, `toString()` có thể được enum override để hiển thị khác.
- Enum có thể thực thi interface và có method/field riêng; `getDeclaredFields()` có thể gồm cả các thành phần khác, nên không lấy các constant chỉ bằng mọi field có trong lớp.

**Góc cạnh thường gặp:** một enum constant có **class body riêng** có runtime class vô danh. Khi đó `constant.getClass().isEnum()` có thể là `false`, dù `constant.getDeclaringClass().isEnum()` vẫn `true`.

```java
enum Mode {
    BASIC,
    CUSTOM {
        @Override String description() { return "custom"; }
    };
    String description() { return "basic"; }
}
```

Với đoạn khai báo này, `Mode.CUSTOM.getClass().isEnum()` trả `false`; `Mode.CUSTOM.getDeclaringClass() == Mode.class` trả `true`. Phương thức `getDeclaringClass()` ở đây là của **instance `Enum`**, khác với `Class.getDeclaringClass()` dùng để tra lớp khai báo một nested/member type. Nếu cần xác định kiểu enum từ **hằng**, dùng `Enum.getDeclaringClass()`.

## 7. Record: lớp dữ liệu có cấu trúc component rõ ràng

Record (chuẩn từ Java 16, có đầy đủ trong Java 17+) là một **lớp tham chiếu** với các component công khai trong header, ví dụ:

```java
record Point(int x, int y) {}
record Person(String name, java.util.List<String> tags) {}
```

Với `Point`, compiler cung cấp private final fields tương ứng, accessor `x()`/`y()`, canonical constructor, và triển khai mặc định cho `equals`, `hashCode`, `toString` (trừ khi được khai báo hợp lệ để thay thế). Record có superclass trực tiếp `java.lang.Record`, mặc định `final`, có thể thực thi interface nhưng không mở rộng lớp tùy ý. `Record.class.isRecord()` là `false`; `Point.class.isRecord()` là `true`.

Record mang ý nghĩa **nông (shallow) về tính bất biến**: reference component không thể được gán lại như field thông thường, nhưng đối tượng mà nó trỏ tới vẫn có thể thay đổi nếu chính đối tượng đó mutable. Chẳng hạn `Person.tags()` có thể trả một `List` mutable; không tự suy ra deep immutability.

Dùng `Class.getRecordComponents()` để lấy metadata đúng bản chất record, theo thứ tự khai báo trong header:

```java
for (java.lang.reflect.RecordComponent rc : Point.class.getRecordComponents()) {
    System.out.println(rc.getName() + ": " + rc.getType().getTypeName());
}
```

Kết quả:

```text
x: int
y: int
```

Mỗi `RecordComponent` cho `getName()`, `getType()` (kiểu đã erasure), `getGenericType()` (giữ thông tin generic trong khai báo nếu có), `getAccessor()`, và metadata annotation phù hợp. Ví dụ với `Person`, component `tags` có `getType() == java.util.List.class`, còn `getGenericType().getTypeName()` có thể hiển thị `java.util.List<java.lang.String>`.

`getRecordComponents()` trả **`null` nếu không phải record**, và mảng **rỗng** nếu đúng là record không có component (`record Empty() {}`). Do đó tránh gọi `.length` hoặc duyệt trực tiếp trước khi xác định `isRecord()`.

Record component là khái niệm ở header, không đồng nhất hoàn toàn với JavaBeans property: accessor có tên `name()`, **không bắt buộc** là `getName()`. Việc duyệt tất cả `getDeclaredFields()` rồi suy luận component sẽ dễ nhầm field khác hoặc thứ tự, vì API đó không bảo đảm thứ tự field. Khi đọc một record qua Reflection, dựa vào `getRecordComponents()` và `getAccessor()`.

## 8. Ví dụ Java 17+ hoàn chỉnh: đối chiếu sáu nhóm kiểu

Lưu đoạn sau vào file **`ClassModelDemo.java`**. Đây là một chương trình độc lập, gồm một interface, một enum thực thi interface, và một record có accessor tự động thực thi interface:

```java
import java.lang.reflect.RecordComponent;
import java.util.Arrays;

interface DisplayName {
    String displayName();
}

enum Stage implements DisplayName {
    NEW, DONE;
    @Override public String displayName() {
        return name();
    }
}

record Task(String displayName, int attempts) implements DisplayName {}

public class ClassModelDemo {
    public static void main(String[] args) {
        System.out.println("primitive(int): " + int.class.isPrimitive());
        System.out.println("primitive(void): " + void.class.isPrimitive());
        System.out.println("void == Void.TYPE: " + (void.class == Void.TYPE));
        System.out.println("Void.class primitive: " + Void.class.isPrimitive());

        System.out.println("array(int[][]): " + int[][].class.isArray());
        System.out.println("component(int[][]): "
                + int[][].class.getComponentType().getTypeName());
        System.out.println("name(int[][]): " + int[][].class.getName());
        System.out.println("name(String[]): " + String[].class.getName());
        System.out.println("array superclass Object: "
                + (String[].class.getSuperclass() == Object.class));
        System.out.println("array implements Cloneable: "
                + Cloneable.class.isAssignableFrom(String[].class));
        System.out.println("String[] -> Object[]: "
                + Object[].class.isAssignableFrom(String[].class));
        System.out.println("int[] -> Object[]: "
                + Object[].class.isAssignableFrom(int[].class));

        System.out.println("interface(DisplayName): "
                + DisplayName.class.isInterface());
        System.out.println("Stage implements DisplayName: "
                + DisplayName.class.isAssignableFrom(Stage.class));
        System.out.println("enum(Stage): " + Stage.class.isEnum());
        System.out.println("enum constants: "
                + Arrays.toString(Stage.class.getEnumConstants()));

        System.out.println("record(Task): " + Task.class.isRecord());
        System.out.println("record superclass Record: "
                + (Task.class.getSuperclass() == Record.class));
        System.out.println("record components:");
        for (RecordComponent component : Task.class.getRecordComponents()) {
            System.out.println("  " + component.getName() + ": "
                    + component.getType().getTypeName());
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 ClassModelDemo.java
java ClassModelDemo
```

Stdout chính xác (không gồm dòng chú thích/lệnh shell):

```text
primitive(int): true
primitive(void): false
void == Void.TYPE: true
Void.class primitive: false
array(int[][]): true
component(int[][]): int[]
name(int[][]): [[I
name(String[]): [Ljava.lang.String;
array superclass Object: true
array implements Cloneable: true
String[] -> Object[]: true
int[] -> Object[]: false
interface(DisplayName): true
Stage implements DisplayName: true
enum(Stage): true
enum constants: [NEW, DONE]
record(Task): true
record superclass Record: true
record components:
  displayName: java.lang.String
  attempts: int
```

Giải thích ba điểm dễ nhầm trong output: `void` có literal `Class` nhưng không là primitive theo `isPrimitive`; `int[][]` có component `int[]` và tên nhị phân `[[I`; `Task` là record thực sự vì được khai báo bằng `record`, không chỉ vì kế thừa trực tiếp `Record`. `Task` tự sinh method `displayName()` có cùng chữ ký với hợp đồng interface.

## 9. Kiểm tra subtype bằng `isAssignableFrom`: chú ý chiều

Cú pháp là **`Target.class.isAssignableFrom(Source.class)`**: có thể xem một giá trị kiểu `Source` là kiểu `Target` trong mô hình gán tham chiếu/runtime hay không. Chữ `Target` đứng bên trái là nơi **nhận** giá trị.

| Biểu thức | Kết quả | Tại sao |
| --- | --- | --- |
| `Object.class.isAssignableFrom(String.class)` | `true` | `String` là subtype của `Object` |
| `Runnable.class.isAssignableFrom(Thread.class)` | `true` | `Thread` thực thi `Runnable` |
| `long.class.isAssignableFrom(int.class)` | `false` | Không thực hiện primitive widening |
| `Integer.class.isAssignableFrom(int.class)` | `false` | Không tự boxing |
| `Object.class.isAssignableFrom(int[].class)` | `true` | Mảng là object |
| `Object[].class.isAssignableFrom(int[].class)` | `false` | Phần tử `int` là primitive |
| `Object[].class.isAssignableFrom(int[][].class)` | `true` | Phần tử là reference `int[]` |
| `Record.class.isAssignableFrom(Task.class)` | `true` | `Task` kế thừa `Record` |

`isInstance(value)` là phép kiểm tra trên **đối tượng** hiện có, gần ý nghĩa runtime của `instanceof`; ví dụ `Runnable.class.isInstance(new Thread())` là `true`. Dùng `isAssignableFrom` khi có hai đối tượng `Class`, dùng `isInstance` khi có một `Class` và một giá trị `Object`. Với primitive/void, `isInstance` không thể nhận một instance primitive.

## 10. Phân loại kiểu cho công cụ Reflection

Thứ tự kiểm tra quan trọng vì `void` không thỏa `isPrimitive()`, còn annotation thỏa `isInterface()`. Phương thức sau có thể đặt trong một class Java 17+:

```java
static String classify(Class<?> type) {
    if (type == void.class)   return "void";
    if (type.isPrimitive())   return "primitive";
    if (type.isArray())       return "array";
    if (type.isAnnotation())  return "annotation";
    if (type.isInterface())   return "interface";
    if (type.isEnum())        return "enum";
    if (type.isRecord())      return "record";
    return "ordinary class";
}
```

Đây là **một method minh họa**, không phải file chương trình độc lập: thêm nó vào class rồi gọi từ `main` để chạy. Thứ tự này cho phép phân biệt trực tiếp những dạng khai báo chính. Một object enum hằng có class body riêng có thể được phân loại `ordinary class` nếu truyền `constant.getClass()`; muốn phân loại kiểu enum khai báo, truyền `constant.getDeclaringClass()`.

Khi xây dựng mapper, serializer, DI container, debugger hay trình tạo tài liệu API, nên chọn luồng xử lý riêng: mảng lấy component type; enum lấy hằng; record lấy component/accessor; interface lấy thông tin hợp đồng; primitive/void xử lý bằng quy tắc riêng. Không lấy constructor hay duyệt field theo một giả định đồng nhất cho mọi `Class`.

## 11. Các lỗi thường gặp và cách sửa

1. **Đồng nhất `int.class` với `Integer.class`.** Sửa bằng phân biệt primitive và wrapper; `Integer.TYPE == int.class` nhưng `Integer.class != int.class`. Reflection `isAssignableFrom` không tự boxing.
2. **Cho rằng `void.class.isPrimitive()` là `true`.** Sửa bằng nhánh `type == void.class` riêng; không tạo instance hay mảng của `void`.
3. **Dùng `Class.forName("int")` hoặc `Class.forName("String[]")`.** Sửa bằng class literal cho primitive, và descriptor JVM như `"[I"` hoặc `"[Ljava.lang.String;"` cho mảng. `String[]` không phải tên binary của lớp mảng.
4. **Tưởng `int[]` là `Object[]`.** `int[]` là một `Object`, nhưng các phần tử `int` không phải reference. Ngược lại, `int[][]` tương thích `Object[]` vì phần tử của nó là `int[]`.
5. **Viết vào `Object[]` trỏ đến `String[]` bằng kiểu phần tử bất kỳ.** Compiler chấp nhận một số phép gán, JVM có thể ném `ArrayStoreException`; bảo vệ bằng kiểm tra kiểu phần tử thực.
6. **Kết luận interface có superclass `Object` vì mọi implementation là object.** `Interface.class.getSuperclass()` thực tế là `null`; dùng `getInterfaces()` và `isAssignableFrom()` để kiểm tra hợp đồng.
7. **Dùng `enumConstant.getClass().isEnum()` để tìm enum khai báo.** Constant có class body có lớp con vô danh; dùng `enumConstant.getDeclaringClass()`.
8. **Dùng `getDeclaredFields()` để suy ra thứ tự và cấu trúc record.** Dùng `getRecordComponents()` (theo thứ tự header), `getAccessor()` và `getGenericType()`; chỉ gọi khi `isRecord()` đúng.
9. **Tưởng record là immutable sâu, hoặc mọi record đều có getter `getX()`.** Field thành phần không thể gán lại, nhưng object mutable tham chiếu vẫn có thể đổi; accessor chuẩn mang tên `x()`.
10. **Tưởng `Class<?>` giữ nguyên mọi generic argument.** `List<String>.class` không hợp lệ; `List.class` chỉ là raw class theo erasure. Khi cần generic khai báo, khảo sát `Type`, `getGenericType()`, `getGenericSuperclass()` hoặc các API generic Reflection phù hợp.

## 12. Tự kiểm tra

**Câu 1.** Dự đoán kết quả của `int[][].class.getComponentType().isArray()` và `int[][].class.getComponentType().getComponentType() == int.class`.

**Đáp án:** cả hai `true`; `int[][] → int[] → int` theo từng lần lấy component type.

**Câu 2.** Với `enum Flag { ON, OFF }`, `Flag.class.getEnumConstants().length`, `Enum.class.isEnum()`, `Flag.class.isEnum()` trả gì?

**Đáp án:** lần lượt `2`, `false`, `true`. `Enum` là superclass của các enum khai báo nhưng bản thân `Enum` không phải khai báo enum.

**Câu 3.** Với `record Empty() {}`, `Empty.class.isRecord()`, `Empty.class.getRecordComponents().length` và `Record.class.getRecordComponents()` là gì?

**Đáp án:** `true`, `0`, `null`. Record không có component vẫn là record; superclass `Record` không phải record.

**Câu 4.** Tại sao `Object[].class.isAssignableFrom(int[][].class)` là `true` mà `Object[].class.isAssignableFrom(int[].class)` là `false`?

**Đáp án:** ở chiều đầu tiên của `int[][]`, phần tử là `int[]` (một reference object). Còn phần tử của `int[]` là primitive `int`, nên không thể xem `int[]` như `Object[]`.

**Câu 5.** Phân biệt `MyInterface.class.getInterfaces()`, `MyInterface.class.getSuperclass()` và `MyInterface.class.isInterface()`.

**Đáp án:** API thứ nhất trả các superinterface trực tiếp, API thứ hai trả `null`, API thứ ba trả `true` nếu `MyInterface` được khai báo là interface.

**Câu 6.** Nếu cần lấy tên và generic type của component trong `record Holder(java.util.List<String> values) {}`, nên dùng API nào?

**Đáp án:** `Holder.class.getRecordComponents()[0].getName()` và `getGenericType()`. `getType()` trả `List.class`, trong khi `getGenericType()` còn thông tin `String` được khai báo trong chữ ký component.

## Tài liệu chuẩn để đối chiếu

- Java SE 21 `Class`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html — mô tả chính xác `isPrimitive`, `isArray`, `isInterface`, `isEnum`, `isRecord`, `getEnumConstants`, `getRecordComponents` và quan hệ kiểu.
- Java SE 21 `RecordComponent`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/RecordComponent.html — `getType`, `getGenericType`, `getAccessor` và annotation của component.
- Java Language Specification, mục Arrays, Enum Classes, Record Classes: https://docs.oracle.com/javase/specs/jls/se21/html/jls-10.html ; https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html .