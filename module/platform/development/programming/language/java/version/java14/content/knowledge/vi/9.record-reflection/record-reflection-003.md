# Tên, kiểu và accessor trong `RecordComponent` (Java 16+)

## 1. `RecordComponent` dùng để làm gì?

Một **record** khai báo các thành phần dữ liệu (*record components*) ngay trong phần đầu của kiểu:

```java
public record OrderLine(String sku, int count, java.util.List<String> tags) {}
```

Ba component lần lượt là `sku`, `count` và `tags`. Từ thông tin này, Java cung cấp các trường thành viên tương ứng, canonical constructor, accessor `sku()`, `count()`, `tags()` và những phương thức theo giá trị như `equals`/`hashCode`.

Khi cần **đọc cấu trúc record lúc chạy**, API reflection cung cấp lớp **`java.lang.reflect.RecordComponent`**. Mỗi `RecordComponent` là *metadata cho một component được khai báo trong record header*: tên, kiểu, kiểu generic, accessor, annotation và lớp record sở hữu nó.

Phân biệt rõ:

- `RecordComponent` **không phải là giá trị của một component** trong một đối tượng `OrderLine` cụ thể.
- `RecordComponent` **không phải** `Field` hay `Method`, dù nó có quan hệ với trường lưu dữ liệu và accessor của record.
- Muốn **đọc giá trị** từ một instance, lấy `Method` bằng `getAccessor()`, rồi gọi phương thức trên **instance hợp lệ**; hoặc, nếu đã biết kiểu tại compile time, gọi trực tiếp `orderLine.sku()`.
- Reflection giúp các công cụ như mapper, serializer, schema generator hay bộ kiểm tra metadata nhận biết thành phần của record mà không phải viết tên component cố định.

**Phạm vi phiên bản:** Record được giới thiệu ở dạng preview trong Java 14 và chính thức từ **Java 16** ([JEP 395](https://openjdk.org/jeps/395)). Các API `Class.isRecord()`, `Class.getRecordComponents()` và `RecordComponent` là cách làm **hiện hành**, sử dụng với Java 16+ mà không cần preview flag. Ví dụ thực hành dùng `--release 17` để phù hợp JDK 17 trở lên.

## 2. Bắt đầu từ `Class`: kiểm tra record và lấy danh sách component

```java
Class<OrderLine> type = OrderLine.class;

if (type.isRecord()) {
    RecordComponent[] components = type.getRecordComponents();
    for (RecordComponent component : components) {
        System.out.println(component.getName());
    }
}
```

Đây là **đoạn mã minh họa**, yêu cầu import `java.lang.reflect.RecordComponent` và định nghĩa `OrderLine` như trên. Hai phương thức quan trọng của `java.lang.Class` là:

1. **`isRecord()`**: trả `true` nếu lớp được khai báo là record. Một class thông thường, kể cả có các trường `final` và tự viết accessor tương tự record, không trở thành record chỉ vì có cấu trúc giống.
2. **`getRecordComponents()`**: nếu lớp là record, trả mảng `RecordComponent[]`, **giữ nguyên thứ tự khai báo trong record header**. Record không có component trả **mảng rỗng**. Với lớp không phải record, phương thức trả **`null`**, không phải mảng rỗng.

Ví dụ:

```java
record Empty() {}

System.out.println(Empty.class.isRecord());                 // true
System.out.println(Empty.class.getRecordComponents().length); // 0
System.out.println(String.class.isRecord());                // false
System.out.println(String.class.getRecordComponents() == null); // true
```

Đoạn trên là minh họa trong thân phương thức; `Empty` cần được khai báo tại nơi hợp lệ. Vì mảng trả về có thể là `null` khi không phải record, luôn kiểm tra `isRecord()` hoặc giá trị `null` trước khi duyệt.

**Thứ tự có ý nghĩa:** `getRecordComponents()` giữ thứ tự từ record header, vốn cũng xác định thứ tự tham số của canonical constructor. Không dùng thứ tự từ `getDeclaredFields()` hoặc `getDeclaredMethods()` để suy ra thứ tự component; các API đó có ngữ nghĩa và hợp đồng khác.

## 3. Các phương thức cần biết của `RecordComponent`

| API | Kiểu kết quả | Câu hỏi nó trả lời |
| --- | --- | --- |
| `getName()` | `String` | Component tên gì trong record header? |
| `getType()` | `Class<?>` | Kiểu ở mức runtime/erasure của component là gì? |
| `getGenericType()` | `Type` | Kiểu khai báo, bao gồm thông tin generic như `List<String>` hoặc biến kiểu `T`, là gì? |
| `getAccessor()` | `Method` | Method nào là accessor tương ứng với component? |
| `getDeclaringRecord()` | `Class<?>` | Record nào đã khai báo component này? |
| `getGenericSignature()` | `String` | Chữ ký generic theo biểu diễn của JVM là gì? |
| `getAnnotatedType()` | `AnnotatedType` | Các type-use annotation trên kiểu của component là gì? |
| `getAnnotation(...)` và `getAnnotations()` | Annotation / mảng annotation | Annotation khai báo có retention phù hợp được gắn trên component là gì? |

Bài học tập trung ba nhóm thông tin **tên – kiểu – accessor**; những phương thức bổ trợ ở cuối bảng giúp hiểu các tình huống reflection thực tế.

### `getName()`: tên từ khai báo, không phải tên getter JavaBeans

Với:

```java
record Person(String fullName, boolean active) {}
```

tên các component là `fullName` và `active`. Accessor do record cung cấp là `fullName()` và `active()`. Nó **không tự động sinh** `getFullName()` hoặc `isActive()`.

`getName()` trả chính tên trong header, nên rất hữu ích để xây tên trường JSON, tên cột dữ liệu hoặc nhãn hiển thị, nhưng công cụ cần có quy tắc ánh xạ riêng nếu muốn đổi tên.

### `getType()`: kiểu ở mức `Class<?>`

- Với `String sku`: `getType()` là `String.class`.
- Với `int count`: `getType()` là `int.class`, không phải `Integer.class`.
- Với `List<String> tags`: `getType()` là `List.class`, **không phải** “`List<String>.class`”, vì generic type arguments bị erasure khi biểu diễn dưới dạng `Class`.

Có thể dùng `getType().getTypeName()` để in tên dễ đọc, chẳng hạn `java.lang.String`, `int` hoặc `java.util.List`.

### `getGenericType()`: giữ thông tin generic ở mức khai báo

`getGenericType()` trả một `java.lang.reflect.Type`. Khi component được khai báo là `List<String>`, kết quả có thể là `ParameterizedType` mô tả đối số kiểu `String`, và `getTypeName()` sẽ thể hiện `java.util.List<java.lang.String>`.

Với record generic `record Holder<T>(T value) {}`, component `value` có `getType() == Object.class` nếu `T` không có bound, trong khi `getGenericType().getTypeName()` trả `T`.

**Không nhầm generic declaration với kiểu thực tế của một instance.** Nếu gọi reflection trên `Holder.class`, metadata cho `T` vẫn là **biến kiểu `T`**, kể cả tại một vị trí mã có đối tượng `Holder<String>`; Java không lưu mỗi tham số generic đã thay thế của từng instance theo cách làm `getGenericType()` tự thành `String.class`.

### `getAccessor()`: tìm phương thức truy cập đúng của component

`getAccessor()` trả `java.lang.reflect.Method` tương ứng với accessor của component:

- Với component `sku`, accessor là `sku()`, không phải `getSku()`.
- Với `count`, accessor là `count()`, trả `int`.
- Accessor không nhận tham số (`getParameterCount() == 0`); kiểu trả về thể hiện kiểu component phù hợp.
- Phương thức có thể do compiler tạo hoặc do người viết record định nghĩa tường minh. Trong trường hợp người viết định nghĩa accessor, việc gọi accessor vẫn thực thi logic của phương thức đó.

Có thể lấy giá trị bằng `accessor.invoke(recordInstance)`. `Method.invoke` trả `Object`; kết quả primitive như `int` được **boxing** thành wrapper như `Integer`. Nếu gọi với sai instance hoặc thiếu quyền truy cập, reflection có thể phát sinh exception.

## 4. Ví dụ hoàn chỉnh: đọc tên, kiểu và gọi accessor

Tạo tệp **`RecordComponentDemo.java`** sau. Ví dụ dùng một record có ba component, một record generic và annotation riêng trên component. Toàn bộ nằm trong một tệp, có thể biên dịch/chạy bằng JDK 17+:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.lang.reflect.RecordComponent;
import java.util.List;

public class RecordComponentDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.RECORD_COMPONENT)
    public @interface Label {
        String value();
    }

    public record OrderLine(
            @Label("Mã hàng") String sku,
            int count,
            List<String> tags) {
        public OrderLine {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("sku không hợp lệ");
            }
            tags = List.copyOf(tags);
        }
    }

    public record Holder<T>(T value) {}

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Class<OrderLine> type = OrderLine.class;
        System.out.println("record=" + type.isRecord());

        for (RecordComponent c : type.getRecordComponents()) {
            Method accessor = c.getAccessor();
            System.out.println(
                    c.getName()
                    + " | raw=" + c.getType().getTypeName()
                    + " | generic=" + c.getGenericType().getTypeName()
                    + " | accessor=" + accessor.getName() + "()"
                    + " | arity=" + accessor.getParameterCount());
        }

        OrderLine value = new OrderLine(
                "SKU-7", 2, List.of("gift", "new"));
        RecordComponent[] components = type.getRecordComponents();
        System.out.println(
                "tags=" + components[2].getAccessor().invoke(value));
        System.out.println(
                "label=" + components[0]
                        .getAnnotation(Label.class).value());
        System.out.println(
                "declares=" + (components[0].getDeclaringRecord() == type));

        RecordComponent generic =
                Holder.class.getRecordComponents()[0];
        System.out.println("holderRaw="
                + generic.getType().getTypeName());
        System.out.println("holderGeneric="
                + generic.getGenericType().getTypeName());
        System.out.println("nonRecord="
                + (String.class.getRecordComponents() == null));
    }
}
```

**Biên dịch và chạy:**

```bash
javac --release 17 -encoding UTF-8 RecordComponentDemo.java
java RecordComponentDemo
```

Cờ `--release 17` thích hợp khi dùng một `javac` đủ mới để biên dịch theo Java 17. Record và reflection API dùng ở đây đều là tính năng chính thức; không cần `--enable-preview`.

**Đầu ra chính xác:**

```text
record=true
sku | raw=java.lang.String | generic=java.lang.String | accessor=sku() | arity=0
count | raw=int | generic=int | accessor=count() | arity=0
tags | raw=java.util.List | generic=java.util.List<java.lang.String> | accessor=tags() | arity=0
tags=[gift, new]
label=Mã hàng
declares=true
holderRaw=java.lang.Object
holderGeneric=T
nonRecord=true
```

### Giải thích từng phần của kết quả

1. `record=true` vì `OrderLine` được khai báo bằng từ khóa `record`.
2. Ba dòng đầu tiên xuất hiện theo đúng thứ tự trong header: `sku`, `count`, `tags`. `getName()` cho tên, `getType()` cho kiểu erasure, `getGenericType()` cho kiểu khai báo và `getAccessor()` cho phương thức không tham số.
3. Ở `tags`, kiểu `Class<?>` là `java.util.List` nhưng kiểu generic là `java.util.List<java.lang.String>`. Đây là ví dụ trực tiếp vì sao `getType()` và `getGenericType()` không thay thế hoàn toàn cho nhau.
4. `tags=[gift, new]` là **giá trị của component từ một instance `OrderLine` cụ thể**, thu được bằng `Method.invoke(value)`. Metadata không tự chứa danh sách giá trị.
5. `label=Mã hàng` vì annotation `@Label` có `RetentionPolicy.RUNTIME` và được phép áp dụng cho `ElementType.RECORD_COMPONENT`. `getAnnotation(Label.class)` đọc annotation trên component `sku`.
6. `declares=true` vì `getDeclaringRecord()` của `sku` trả `OrderLine.class`.
7. `holderRaw=java.lang.Object` nhưng `holderGeneric=T` là biểu hiện của erasure đối với biến kiểu không có bound trong `Holder<T>`.
8. `nonRecord=true`: đối với `String.class`, `getRecordComponents()` là `null` vì `String` không phải record.

Phần này thể hiện **metadata reflection** và **đọc giá trị thật** trong cùng một ví dụ nhưng qua hai thao tác khác nhau: `getRecordComponents()` và `getAccessor().invoke(instance)`.

## 5. Phân biệt `getType()` và `getGenericType()` chi tiết

Hai API này cùng mô tả **kiểu được khai báo của record component**, nhưng trả về hai mô hình khác nhau.

| Khai báo component | `getType().getTypeName()` | `getGenericType().getTypeName()` |
| --- | --- | --- |
| `int count` | `int` | `int` |
| `String sku` | `java.lang.String` | `java.lang.String` |
| `List<String> tags` | `java.util.List` | `java.util.List<java.lang.String>` |
| `T value` trong `record Holder<T>(T value)` | `java.lang.Object` | `T` |
| `T value` trong `record Numeric<T extends Number>(T value)` | `java.lang.Number` | `T` |

Với thành phần có wildcard như `List<? extends Number>`, `getGenericType()` cho phép xử lý `ParameterizedType` và đối số kiểu `WildcardType` ở mức reflection, thay vì chỉ thấy raw `List.class`.

Có thể kiểm tra loại metadata nếu cần xây schema:

```java
// Đoạn nằm trong phương thức có biến c kiểu RecordComponent.
java.lang.reflect.Type declared = c.getGenericType();
if (declared instanceof java.lang.reflect.ParameterizedType p) {
    System.out.println(p.getRawType());
    for (java.lang.reflect.Type argument
            : p.getActualTypeArguments()) {
        System.out.println(argument.getTypeName());
    }
}
```

Đoạn trên **không tự chạy độc lập**; nó dùng biến `c` từ lần duyệt component. Chỉ truy cập `getActualTypeArguments()` khi thực sự là `ParameterizedType`; nếu kiểu là `Class`, `TypeVariable` hoặc kiểu phản chiếu khác, cần xử lý trường hợp đó.

**`getGenericSignature()` khác `getGenericType()`:** signature biểu diễn kiểu generic theo quy ước ở mức JVM class file và thích hợp cho công cụ chuyên phân tích bytecode. Nếu cần xử lý kiểu bằng Java reflection bình thường, ưu tiên `getGenericType()`, `ParameterizedType` và các kiểu con của `Type` thay vì tự phân tích chuỗi signature theo quy tắc thủ công.

**Đừng dùng `getType()` để xác nhận phần tử danh sách là `String`**: `List<String>` và `List<Integer>` đều có raw type `List.class`. Mặt khác, dữ liệu thực tế vẫn phải được validate; chỉ biết kiểu khai báo không bảo đảm danh sách đầu vào lúc runtime không chứa dữ liệu sai nếu có raw-type/unchecked operations.

## 6. Accessor trong reflection: method nào, gọi ra sao?

### 6.1. Truy cập thông thường so với truy cập động

Khi đã biết record tại compile time:

```java
OrderLine line = new OrderLine("SKU-7", 2, List.of("gift"));
System.out.println(line.sku());  // SKU-7
System.out.println(line.count()); // 2
```

Đây là đoạn minh họa trong phạm vi có thể tham chiếu `RecordComponentDemo.OrderLine` (hoặc import kiểu nested `OrderLine`). Gọi trực tiếp accessor thường rõ ràng, an toàn kiểu và đơn giản hơn.

Khi mã phải xử lý một loại record **chỉ được biết ở runtime**, dùng:

```java
// Giả định đã có: RecordComponent component và Object recordInstance.
// recordInstance phải là instance của record phù hợp, với quyền truy cập cho phép.
java.lang.reflect.Method accessor = component.getAccessor();
Object result = accessor.invoke(recordInstance);
```

Lệnh `invoke` thực thi phương thức accessor. Kết quả trả về là `Object`:

- `String` giữ dạng `String`.
- `List<String>` là instance danh sách; generic type arguments không được phản chiếu thành một object “`List<String>`” riêng ở runtime.
- `int` được boxing thành `Integer` khi trả qua `Method.invoke`.
- Nếu accessor được viết tường minh để thực thi logic bổ sung, lệnh reflection **cũng thực thi logic đó**, kể cả ngoại lệ/tác dụng phụ nếu có.

**Quan trọng:** `getAccessor()` là phương thức của `RecordComponent` để tìm accessor tương ứng; không nhầm với `Class.getDeclaredField(component.getName())`. Reflection trên `Field` đòi hỏi quy tắc quyền truy cập riêng, và `RecordComponent` không có API trực tiếp trả về `Field`. Ưu tiên public accessor để làm việc với record như một giá trị.

### 6.2. Kiểm tra điều kiện trước khi gọi accessor

Khi nhận một `Object` chưa biết kiểu:

```java
static void printComponentValues(Object object)
        throws ReflectiveOperationException {
    if (object == null) {
        throw new IllegalArgumentException("object là null");
    }

    Class<?> type = object.getClass();
    if (!type.isRecord()) {
        throw new IllegalArgumentException("Yêu cầu một record");
    }

    for (java.lang.reflect.RecordComponent component
            : type.getRecordComponents()) {
        java.lang.reflect.Method method = component.getAccessor();
        System.out.println(
                component.getName() + "=" + method.invoke(object));
    }
}
```

Đây là **đoạn phương thức minh họa** để đặt trong một class; nó không phải tệp độc lập. Nó hữu ích khi quan sát các record **có kiểu truy cập công khai trong ngữ cảnh gọi**. Nếu record/class hoặc accessor không thể truy cập do giới hạn Java access control hay module boundary, `invoke` có thể ném `IllegalAccessException` hoặc lỗi truy cập liên quan. Không mặc định gọi `setAccessible(true)` để vượt quyền trong ứng dụng.

Khi gọi qua `Method.invoke`, cần tính đến:

- **`IllegalAccessException`** nếu caller không có quyền truy cập phương thức.
- **`IllegalArgumentException`** nếu instance truyền vào không đúng kiểu khai báo của method hoặc đối số không phù hợp.
- **`InvocationTargetException`** nếu accessor thực thi và ném ngoại lệ; nguyên nhân thực sự nằm trong `getCause()` của exception này.
- **`NullPointerException`** nếu gọi instance method với receiver `null`.

Trong ví dụ hoàn chỉnh, cả record nested và accessor đều là `public`; `main` gọi chúng trong cùng class, nên đường gọi hợp lệ. Khi triển khai cho thư viện tổng quát, cần kiểm tra khả năng truy cập, yêu cầu bảo mật và chính sách xử lý ngoại lệ phù hợp.

### 6.3. Accessor do người viết định nghĩa vẫn là accessor

Một record có thể tự định nghĩa accessor với chữ ký phù hợp:

```java
public record DisplayName(String value) {
    @Override
    public String value() {
        return value.strip();
    }
}
```

Khi gọi `getAccessor()` của component `value`, Java trả `Method` mô tả `value()` hiện hữu, không nhất thiết là một accessor compiler tự tạo. Gọi `invoke` sẽ nhận kết quả của logic `strip()`.

**Lưu ý thiết kế:** Với record, việc biến đổi giá trị ở accessor có thể làm **copy invariant** (xây lại record từ các accessor phải giữ equality) không còn đúng nếu accessor trả dữ liệu khác component field thực tế. Nếu cần chuẩn hóa, nên làm trong canonical/compact constructor để mọi instance giữ dữ liệu đã chuẩn hóa ngay từ lúc tạo. Metadata reflection không tự sửa được một accessor có thiết kế không phù hợp.

## 7. Annotation của component và annotated type

Ngoài tên/kiểu/accessor, `RecordComponent` triển khai `AnnotatedElement`. Ví dụ từ chương trình chính:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.RECORD_COMPONENT)
public @interface Label {
    String value();
}

public record OrderLine(
        @Label("Mã hàng") String sku,
        int count,
        List<String> tags) { /* ... */ }
```

Đoạn trên được **trích để giải thích** từ tệp đầy đủ, không phải một chương trình độc lập. `@Target(ElementType.RECORD_COMPONENT)` nói rằng annotation áp dụng cho phần khai báo record component, còn `RetentionPolicy.RUNTIME` cho phép reflection đọc tại runtime.

`component.getAnnotation(Label.class)` trả annotation của component nếu có, hoặc `null` nếu không có. Đừng gọi `.value()` khi chưa kiểm tra `null` trong công cụ xử lý record tùy ý.

**Phân biệt annotation khai báo và annotation trên phần sử dụng kiểu:**

- `getAnnotation(...)` trên `RecordComponent` tìm annotation khai báo của component.
- `getAnnotatedType()` dành cho thông tin `TYPE_USE` trên **kiểu được khai báo**, chẳng hạn nếu API muốn biết annotation đặt trên kiểu hoặc type argument.
- `getAnnotations()` trả các annotation khai báo mà reflection nhìn thấy theo retention; nó không tự thay thế `getAnnotatedType()` khi cần biết annotation của kiểu con trong generic.
- Cùng tên annotation nhưng `@Target`/`@Retention` không phù hợp thì không thể mặc định quan sát qua API mong muốn.

Các framework sinh schema/validation thường cần xử lý đúng loại annotation, cùng cơ chế runtime retention, thay vì chỉ quét `Field` hoặc chỉ đọc `Method`.

## 8. Những lỗi phổ biến và cách khắc phục

| Lỗi thường gặp | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Gọi `getRecordComponents()` rồi duyệt mảng trên class thường | Kết quả là `null`, gây `NullPointerException` | Kiểm tra `isRecord()` hoặc `null` |
| Cho rằng record rỗng trả `null` | Record vẫn là record, chỉ không có component | Dùng mảng rỗng và `length == 0` |
| Tìm accessor bằng tên `getSku` | Record không tự sinh getter JavaBeans | Dùng `component.getAccessor()`; accessor là `sku()` |
| Dùng `getType()` để biết `List<String>` | `getType()` trả raw `List.class` | Dùng `getGenericType()` và xử lý `ParameterizedType` |
| Cho rằng `getGenericType()` trên `Holder<T>` biết `T=String` của một instance | Phản chiếu kiểu khai báo, không suy ra tự động type argument của từng instance | Truyền type metadata riêng nếu ứng dụng cần |
| Xem `RecordComponent` như một `Field` có thể đọc trực tiếp giá trị | Component là metadata, không chứa giá trị instance | Dùng accessor `Method.invoke(instance)` khi thực sự cần giá trị |
| Gọi accessor bằng sai đối tượng hoặc không có quyền truy cập | Reflection áp dụng quy tắc type/access control | Kiểm tra instance, public API/module boundaries và xử lý ngoại lệ |
| Tưởng `Method.invoke` không thực thi logic của accessor viết tay | Nó thực thi phương thức thực tế | Xem accessor như một lời gọi phương thức có thể phát sinh lỗi |
| Giả định có annotation runtime khi chưa đặt `@Retention(RUNTIME)` | Annotation có thể không tồn tại ở runtime | Chọn retention/target phù hợp và kiểm tra `null` |
| Lấy thứ tự component bằng cách duyệt `getDeclaredFields()` | Field reflection không phải hợp đồng thứ tự record header | Dùng `getRecordComponents()` |
| Dùng `getGenericSignature()` như một chuỗi kiểu Java thân thiện người đọc | Đây là chữ ký biểu diễn theo JVM | Dùng `getGenericType().getTypeName()` cho mục đích hiển thị cơ bản |
| Cho rằng đọc accessor giống truy cập field private trực tiếp | Accessor là method, chịu quy tắc gọi phương thức và có thể tùy biến | Dùng contract public và xử lý kết quả/exception của method |

## 9. Checklist để triển khai công cụ xử lý record bằng reflection

1. **Đầu vào:** `Class<?>` hay instance? Nếu có instance, kiểm tra không `null`.
2. **Nhận diện:** chỉ xử lý khi `isRecord()` là `true`; đừng suy diễn từ tên class hoặc việc có phương thức `componentName()`.
3. **Danh sách:** gọi `getRecordComponents()`, giữ đúng thứ tự trong record header và xử lý trường hợp mảng rỗng.
4. **Tên:** dùng `getName()` cho định danh component; nếu xuất JSON/schema cần một chính sách đổi tên riêng.
5. **Kiểu:** dùng `getType()` cho raw runtime type; dùng `getGenericType()` nếu cần generic type arguments; xem xét `getAnnotatedType()` nếu cần type-use annotation.
6. **Accessor:** dùng `getAccessor()` để lấy `Method` đúng; kiểm tra instance/quyền gọi; nếu chỉ cần compile-time access thì ưu tiên gọi trực tiếp.
7. **Ngoại lệ:** xử lý `ReflectiveOperationException` và các lỗi truy cập/đối số thích hợp; nếu `InvocationTargetException`, phân biệt nguyên nhân trong accessor với lỗi reflection.
8. **Mô hình dữ liệu:** không mặc định accessor do compiler sinh hoặc không có side effect; không mặc định dữ liệu collection bất biến sâu.
9. **Kiểm chứng:** thử với record có primitive, generic, annotation, record rỗng và class không phải record; xác nhận đúng tên, thứ tự, kiểu và giá trị thật từ accessor.

## 10. Câu hỏi tự kiểm tra

**1. `RecordComponent.getName()` của `record Task(String title)` trả gì, accessor tên gì?** Trả `title`, accessor là `title()`; Java không tự tạo `getTitle()`.

**2. Vì sao `getType()` của `List<String>` chỉ ra `List.class`?** Vì nó trả `Class<?>` theo kiểu ở mức runtime/erasure. Cần `getGenericType()` để đọc type argument `String` trong khai báo.

**3. `getRecordComponents()` trên `String.class` và `record Empty()` khác nhau thế nào?** `String.class` không phải record nên trả `null`. `Empty.class` là record không có component nên trả mảng có độ dài 0.

**4. Có thể lấy giá trị của component từ `RecordComponent` mà không có instance không?** `RecordComponent` chỉ có metadata; gọi accessor instance cần một đối tượng phù hợp. Nếu chỉ xem tên/kiểu, không cần instance.

**5. Với `record Holder<T>(T value)`, vì sao `getGenericType()` ra `T` còn `getType()` ra `Object`?** Vì `T` là biến kiểu không có bound; erasure của nó là `Object`, trong khi generic metadata vẫn ghi khai báo `T`.

**6. `component.getAccessor().invoke(obj)` có luôn trả đúng field thô không?** Nó trả kết quả của *phương thức accessor*; accessor viết tường minh có thể xử lý dữ liệu, nên không được tự ý đồng nhất kết quả với cách đọc trực tiếp field.

### Nguồn chính thức, hiện còn áp dụng

- [Oracle Java 25 API — `java.lang.reflect.RecordComponent`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/RecordComponent.html): `getName`, `getType`, `getGenericType`, `getAccessor` và API phụ trợ.
- [Oracle Java 25 API — `java.lang.Class`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html): `isRecord`, `getRecordComponents` và quy tắc trả mảng/`null`.
- [Dev.java — Working with Records through Reflection](https://dev.java/learn/reflection/records/): hướng dẫn thực hành reflection trên record.
- [Oracle Java 25 API — `java.lang.reflect.Method`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html): `invoke`, quyền truy cập và xử lý ngoại lệ.
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): ngôn ngữ record được chuẩn hóa từ Java 16.

**Ghi nhớ:** `RecordComponent` mô tả **component**, `getName()` trả **tên**, `getType()`/`getGenericType()` mô tả **kiểu**, và `getAccessor()` trả **Method để đọc giá trị từ một instance**. Luôn phân biệt metadata, giá trị thực, kiểu generic và quyền gọi reflection.
