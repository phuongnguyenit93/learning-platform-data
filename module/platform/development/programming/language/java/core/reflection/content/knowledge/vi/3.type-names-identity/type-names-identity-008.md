# Nhận diện `isPrimitive()`, `isArray()`, `isInterface()` và `isAnnotation()` trong Java Reflection

Khi xử lý một kiểu dữ liệu chưa biết trước lúc biên dịch, Java cung cấp đối tượng `Class<?>` để mô tả kiểu đó ở runtime. Bốn phương thức `Class.isPrimitive()`, `Class.isArray()`, `Class.isInterface()` và `Class.isAnnotation()` giúp nhận diện **loại cấu trúc của chính kiểu** đang xét. Chúng đều trả về `boolean`, không nhận tham số và không cần tạo instance của kiểu.

Đây là các câu hỏi về **metadata kiểu**, khác với câu hỏi “đối tượng có thuộc kiểu này không?” (dùng `isInstance(...)` hoặc `instanceof`), cũng khác với câu hỏi “lớp này có được gắn annotation X không?” (dùng `isAnnotationPresent(...)`).

## 1. Lấy đối tượng `Class<?>` để kiểm tra

Có thể lấy đối tượng mô tả kiểu bằng một trong các cách sau:

```java
Class<?> primitiveType = int.class;
Class<?> arrayType = String[][].class;
Class<?> interfaceType = Runnable.class;
Class<?> runtimeType = "hello".getClass();
Class<?> loadedType = Class.forName("java.lang.String");
```

Đây là **đoạn minh họa** để đặt trong phương thức Java; nó không phải chương trình độc lập. `SomeType.class` hoạt động khi mã nguồn đã biết kiểu, `obj.getClass()` lấy kiểu runtime của một đối tượng khác `null`, còn `Class.forName(...)` tra cứu lớp theo tên nhị phân phù hợp với class loader và có thể phát sinh `ClassNotFoundException`.

Lưu ý: `Class.forName("int")` không tra ra primitive `int` như `int.class`; các dạng tên class và descriptor của mảng có quy tắc riêng. Để xử lý primitive khi cần lựa chọn từ tên, hãy tạo bảng ánh xạ tường minh, chẳng hạn `"int" → int.class`.

## 2. Ý nghĩa chính xác của từng phương thức

### `isPrimitive()`: kiểu nguyên thủy hoặc `void`

Trả về `true` với các đối tượng `Class` đại diện cho tám kiểu nguyên thủy `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double` **và `void.class`**. `void` không phải kiểu dữ liệu có giá trị thông thường, nhưng `Class.isPrimitive()` vẫn trả về `true` cho `void.class` theo đặc tả API.

```java
int.class.isPrimitive();      // true
void.class.isPrimitive();     // true
Integer.class.isPrimitive();  // false
String.class.isPrimitive();   // false
int[].class.isPrimitive();    // false
```

`Integer` là **wrapper class**, không phải primitive `int`. Một mảng chứa primitive cũng là **kiểu mảng tham chiếu**, vì vậy `int[].class.isPrimitive()` là `false`; muốn kiểm tra **phần tử cơ sở** có nguyên thủy không, cần đi qua `getComponentType()`.

Ứng dụng: bộ chuyển đổi dữ liệu, mapper và thư viện reflection dùng thông tin primitive để chọn quy tắc chuyển kiểu, xử lý giá trị mặc định hoặc yêu cầu một đối tượng tham chiếu. Với `void.class`, đừng xử lý như kiểu primitive có thể chứa giá trị.

### `isArray()`: chính kiểu đang xét là mảng

Trả về `true` nếu `Class` mô tả một kiểu mảng, kể cả mảng một chiều/nhiều chiều, mảng primitive, mảng object và mảng annotation:

```java
int[].class.isArray();          // true
String[][].class.isArray();     // true
Runnable[].class.isArray();     // true
String.class.isArray();         // false
```

`getComponentType()` trả về kiểu thành phần trực tiếp của mảng; với kiểu không phải mảng, kết quả là `null`:

```java
int[].class.getComponentType() == int.class;               // true
String[][].class.getComponentType() == String[].class;      // true
String[].class.getComponentType() == String.class;          // true
```

Với mảng nhiều chiều, `getComponentType()` giảm **một** cấp chiều mỗi lần; lặp cho tới khi `isArray()` là `false` để lấy kiểu phần tử tận cùng.

Không dùng `isArray()` để hỏi một class có **field kiểu mảng** hay method trả về mảng. Chỉ truyền `field.getType()` hoặc `method.getReturnType()` rồi kiểm tra nếu đó mới là thông tin cần biết.

### `isInterface()`: interface, bao gồm annotation interface

Trả về `true` nếu đối tượng `Class` đại diện cho một interface. Điều quan trọng: kiểu khai báo bằng `@interface` **cũng là một interface đặc biệt**, vì vậy `MyAnnotation.class.isInterface()` và `MyAnnotation.class.isAnnotation()` có thể **đồng thời** là `true`.

```java
Runnable.class.isInterface();             // true
java.lang.annotation.Annotation.class
        .isInterface();                   // true
String.class.isInterface();               // false
Runnable[].class.isInterface();           // false
```

Một lớp `implements Runnable` vẫn **là class**, nên `MyWorker.class.isInterface()` là `false`. Muốn kiểm tra lớp **có triển khai một interface** hay không, dùng `Runnable.class.isAssignableFrom(MyWorker.class)` hoặc duyệt metadata phù hợp, thay vì gọi `isInterface()` trên class implementation.

Ứng dụng: framework phân biệt hợp đồng giao tiếp với implementation, xác thực kiểu cấu hình động, hoặc quyết định cách khám phá method. Vì annotation interface là tập con của interface, thứ tự phân nhánh cần được thiết kế rõ ràng.

### `isAnnotation()`: chính kiểu đó là annotation type

Trả về `true` nếu `Class` mô tả một kiểu annotation khai báo bằng `@interface`. Phương thức này **không** kiểm tra lớp đang xét có **được gắn annotation** hay không.

Giả sử có:

```java
@interface Tag {}
@Tag class Book {}
```

Khi đó:

```java
Tag.class.isAnnotation();   // true: Tag là annotation type
Book.class.isAnnotation();  // false: Book vẫn là class
Tag.class.isInterface();    // true: annotation type cũng là interface
Tag[].class.isAnnotation(); // false: đây là kiểu mảng
```

Muốn kiểm tra `Book` được gắn `@Tag` ở runtime, dùng `Book.class.isAnnotationPresent(Tag.class)` và bảo đảm annotation được khai báo retention phù hợp (thường `@Retention(RetentionPolicy.RUNTIME)`). `isAnnotation()` chỉ xét **bản chất kiểu `Tag`**, nên không phụ thuộc vào việc một class cụ thể có sử dụng `@Tag` hay không.

## 3. Bảng so sánh và những giao nhau quan trọng

| Kiểu đem kiểm tra | `isPrimitive()` | `isArray()` | `isInterface()` | `isAnnotation()` |
| --- | --- | --- | --- | --- |
| `int.class` | `true` | `false` | `false` | `false` |
| `void.class` | `true` | `false` | `false` | `false` |
| `Integer.class` | `false` | `false` | `false` | `false` |
| `int[].class` | `false` | `true` | `false` | `false` |
| `String[][].class` | `false` | `true` | `false` | `false` |
| `Runnable.class` | `false` | `false` | `true` | `false` |
| `Tag.class` (khai báo `@interface`) | `false` | `false` | `true` | `true` |
| `Tag[].class` | `false` | `true` | `false` | `false` |
| `Book.class` (class được gắn `@Tag`) | `false` | `false` | `false` | `false` |

Hai nhận xét cần nhớ:

1. **Bốn điều kiện không tạo thành một phép chia thành bốn nhóm loại trừ tuyệt đối:** annotation type đồng thời thỏa `isInterface()` và `isAnnotation()`. Không nên giả định chỉ một cờ được `true`.
2. **Cả bốn đều có thể là `false`:** đó là trạng thái bình thường của nhiều class thông thường, enum, record… Nếu cần nhận diện thêm enum/record, xem `isEnum()`, `isRecord()` (có trên các JDK phù hợp) và những API metadata khác. Không kết luận `false` nghĩa là “kiểu không hợp lệ”.

Một mảng của interface/annotation vẫn là **kiểu mảng**; `Runnable[].class.isInterface()` và `Tag[].class.isAnnotation()` đều `false` vì câu hỏi đang hỏi bản thân kiểu mảng, không hỏi phần tử.

## 4. Chương trình Java 17+ có thể biên dịch và chạy

Tạo đúng tệp `TypeKindDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Marker {}

interface Worker {}

@Marker
class Job implements Worker {}

public class TypeKindDemo {
    private static void inspect(String label, Class<?> type) {
        System.out.println(
                label
                + " => primitive=" + type.isPrimitive()
                + ", array=" + type.isArray()
                + ", interface=" + type.isInterface()
                + ", annotation=" + type.isAnnotation()
        );
    }

    private static int arrayDimensions(Class<?> type) {
        int dimensions = 0;
        while (type.isArray()) {
            dimensions++;
            type = type.getComponentType();
        }
        return dimensions;
    }

    public static void main(String[] args) {
        inspect("int", int.class);
        inspect("void", void.class);
        inspect("Integer", Integer.class);
        inspect("int[]", int[].class);
        inspect("String[][]", String[][].class);
        inspect("Worker", Worker.class);
        inspect("Marker", Marker.class);
        inspect("Marker[]", Marker[].class);
        inspect("Job", Job.class);

        System.out.println(
                "Job annotated with @Marker => "
                + Job.class.isAnnotationPresent(Marker.class)
        );
        System.out.println(
                "String[][] dimensions => "
                + arrayDimensions(String[][].class)
        );

        Class<?> leafType = String[][].class;
        while (leafType.isArray()) {
            leafType = leafType.getComponentType();
        }
        System.out.println(
                "String[][] leaf type => " + leafType.getName()
        );
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac TypeKindDemo.java
java TypeKindDemo
```

Stdout chính xác:

```text
int => primitive=true, array=false, interface=false, annotation=false
void => primitive=true, array=false, interface=false, annotation=false
Integer => primitive=false, array=false, interface=false, annotation=false
int[] => primitive=false, array=true, interface=false, annotation=false
String[][] => primitive=false, array=true, interface=false, annotation=false
Worker => primitive=false, array=false, interface=true, annotation=false
Marker => primitive=false, array=false, interface=true, annotation=true
Marker[] => primitive=false, array=true, interface=false, annotation=false
Job => primitive=false, array=false, interface=false, annotation=false
Job annotated with @Marker => true
String[][] dimensions => 2
String[][] leaf type => java.lang.String
```

**Giải thích kết quả:**

- `Marker` là annotation interface. Vì thế cả `isInterface()` và `isAnnotation()` đều `true`.
- `Job` có `@Marker`, nhưng bản thân `Job` vẫn là class thường. `Job.class.isAnnotation()` là `false`, còn `isAnnotationPresent(Marker.class)` là `true` nhờ retention runtime.
- `Marker[]` là một **kiểu mảng**, nên ba cờ primitive/interface/annotation đều `false` dù các phần tử có kiểu annotation.
- `int.class`, `void.class` là primitive theo kết quả `Class.isPrimitive()`; `Integer.class` không phải.
- `String[][].class` có hai chiều; việc gọi lặp `getComponentType()` lần lượt thu được `String[].class` rồi `String.class`.

## 5. Ứng dụng trong code reflection và cách tổ chức điều kiện

Một công cụ phân tích cấu trúc kiểu có thể phân loại để quyết định cách xử lý metadata:

```java
static String kindOf(Class<?> type) {
    if (type.isAnnotation()) {
        return "annotation";
    }
    if (type.isInterface()) {
        return "interface";
    }
    if (type.isArray()) {
        return "array";
    }
    if (type.isPrimitive()) {
        return "primitive";
    }
    return "other";
}
```

Đây là **method minh họa**, được đặt bên trong một class đang dùng; chưa phải chương trình độc lập. Đặt `isAnnotation()` **trước** `isInterface()` nếu mục tiêu là xác định **một nhãn riêng** cho annotation, vì annotation interface đáp ứng cả hai điều kiện. Tùy mục đích, có thể xét mảng hoặc primitive trước; chỉ cặp annotation/interface đòi hỏi lưu ý về tính chồng lấn.

Tuy nhiên, không phải hệ thống nào cũng cần ép về một nhãn duy nhất. Nếu API cần phân tích đầy đủ khả năng của kiểu, hãy giữ riêng cả bốn cờ vì `annotation` đồng thời là `interface`.

Ví dụ luồng kiểm tra kiểu từ `Field` của một class:

```java
// "field" là Field đã lấy được từ một class khác.
Class<?> fieldType = field.getType();
if (fieldType.isArray()) {
    Class<?> component = fieldType.getComponentType();
    // Xử lý kiểu thành phần trực tiếp của field mảng.
} else if (fieldType.isPrimitive()) {
    // Xử lý field nguyên thủy.
}
```

Đây là **đoạn minh họa trong ngữ cảnh reflection**, không phải ứng dụng Java hoàn chỉnh. Để xử lý mảng nhiều chiều, lặp `getComponentType()`; nếu phần tử là primitive, `component.isPrimitive()` chỉ `true` khi đã xuống tới phần tử primitive.

## 6. Phân biệt với những API thường bị nhầm

| Nhu cầu | API phù hợp | Vì sao khác |
| --- | --- | --- |
| Kiểu `Class<?>` có đại diện primitive không? | `type.isPrimitive()` | Xét bản chất của kiểu, không xét giá trị |
| Kiểu có phải mảng không? | `type.isArray()` | Không cho biết kiểu phần tử nếu chưa gọi `getComponentType()` |
| Kiểu có phải một interface không? | `type.isInterface()` | Không xác định một **class** có implement interface nào |
| Kiểu có phải annotation type không? | `type.isAnnotation()` | Không kiểm tra một đối tượng/class được gắn annotation gì |
| Class/element có annotation `X` ở runtime không? | `element.isAnnotationPresent(X.class)` | Kiểm tra sự hiện diện của annotation có thể truy vấn tại runtime |
| Một class có triển khai/thuộc kiểu khác không? | `SuperType.class.isAssignableFrom(SubType.class)` | Kiểm tra quan hệ gán kiểu; gồm cả interface và class |
| Đối tượng có là instance của kiểu không? | `type.isInstance(object)` | Kiểm tra một object; khác bản chất của `type` |
| Tìm kiểu thành phần mảng | `arrayType.getComponentType()` | Trả về một `Class<?>` hoặc `null` nếu không phải mảng |

Ví dụ quan hệ kiểu:

```java
Worker.class.isInterface();             // true
Job.class.isInterface();                // false
Worker.class.isAssignableFrom(Job.class); // true
Worker.class.isInstance(new Job());     // true
```

Với `isInstance(...)`, đối tượng `null` luôn cho `false`. Với kiểu primitive, `int.class.isInstance(1)` cũng là `false`: biểu thức `1` phải boxing thành `Integer` khi truyền làm `Object`, còn primitive `Class` không đại diện lớp instance tham chiếu.

## 7. Lỗi phổ biến và cách tránh

1. **Nhầm wrapper với primitive.** `Integer.class.isPrimitive()` trả về `false`. Kiểm tra cả `int.class` và `Integer.class` bằng test nếu library của bạn có quy tắc riêng cho boxing.
2. **Nhầm mảng primitive với primitive.** `int[].class.isArray()` là `true` còn `isPrimitive()` là `false`. Muốn biết loại phần tử, gọi `getComponentType()`.
3. **Nhầm annotation type với class được gắn annotation.** `Marker.class.isAnnotation()` là `true`; `Job.class.isAnnotation()` là `false` dù `Job` có `@Marker`. Dùng `isAnnotationPresent(...)` cho câu hỏi gắn annotation.
4. **Kiểm tra interface trước annotation rồi dừng.** `Marker.class.isInterface()` là `true` và làm nhánh annotation phía sau không chạy. Sắp điều kiện phù hợp với mục đích hoặc không ép các cờ vào một loại duy nhất.
5. **Nhầm triển khai interface với chính interface.** Một class triển khai `Worker` không khiến `Job.class.isInterface()` thành `true`. Kiểm tra khả năng gán bằng `isAssignableFrom(...)` khi cần.
6. **Chỉ xét mảng một chiều.** `String[][].class.getComponentType()` là `String[].class`. Lặp qua nhiều mức nếu cần tới kiểu phần tử cuối.
7. **Cho rằng mọi kiểu phải thuộc một trong bốn nhóm.** `String.class`, `Integer.class` hay nhiều kiểu domain đều có cả bốn cờ `false`. Có thể xem thêm `isEnum()`, `isRecord()` hoặc thông tin khác tùy mục đích.
8. **Dựa vào tên chuỗi thay cho metadata.** Tên kiểu mảng ở `getName()` như `[I` hoặc `[[Ljava.lang.String;` dễ gây nhầm. Ưu tiên `isArray()` và `getComponentType()`; dùng `Class<?>` đã lấy đúng từ API thay vì tự phân tích chuỗi tên.

## 8. Ghi nhớ và tự kiểm tra

- `void.class.isPrimitive()` → **`true`**; `Integer.class.isPrimitive()` → **`false`**.
- `int[].class.isArray()` → **`true`**; `int[].class.getComponentType()` → **`int.class`**.
- `String[][].class.getComponentType()` → **`String[].class`**, không đi thẳng tới `String.class`.
- Với `@interface Marker`, `Marker.class.isInterface()` **và** `Marker.class.isAnnotation()` cùng là **`true`**.
- Với `@Marker class Job`, `Job.class.isAnnotation()` → **`false`**; `Job.class.isAnnotationPresent(Marker.class)` chỉ quan sát được annotation nếu retention/runtime metadata phù hợp.
- Mảng annotation (`Marker[].class`) là **mảng**, không phải annotation interface.
- Bốn predicate mô tả **bản thân kiểu**, không kiểm tra mặc định quan hệ kế thừa, instance hoặc annotation hiện diện.

Khi viết công cụ reflection, hãy xác định chính xác **đối tượng `Class<?>` đang mô tả kiểu nào**: kiểu field, kiểu trả về, component của mảng hay kiểu class chính. Sau đó chọn predicate tương ứng, tránh suy luận từ tên hoặc từ kiểu của đối tượng khác.
