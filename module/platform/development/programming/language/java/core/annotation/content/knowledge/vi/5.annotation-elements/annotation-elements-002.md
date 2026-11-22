# Phần tử `Class<?>` và `Class<? extends T>` trong Java annotation

Trong Java, một **phần tử (element) của annotation** có thể lưu tham chiếu đến *kiểu* qua giá trị `Class`. Thông thường, người viết annotation khai báo `Class<?>` khi muốn nhận nhiều loại bất kỳ, hoặc `Class<? extends SomeType>` khi chỉ muốn nhận các kiểu nằm trong một họ kế thừa hay triển khai interface xác định. Giá trị đặt trên annotation thường là **class literal** như `String.class`, `MyHandler.class`; nó biểu thị kiểu được chọn, không tạo sẵn đối tượng của kiểu đó.

Ví dụ ngắn:

```java
interface Handler {}

class EmailHandler implements Handler {}
class SmsHandler implements Handler {}

@interface AnyType {
    Class<?> value();
}

@interface HandlerType {
    Class<? extends Handler> value();
}

@AnyType(String.class)
class A {}

@HandlerType(EmailHandler.class)
class B {}
```

Hai cách khai báo đều hợp lệ. Với `@AnyType`, compiler chấp nhận `String.class` hay `EmailHandler.class`. Với `@HandlerType`, compiler kiểm tra rằng kiểu được chỉ định phải là `Handler` hoặc kiểu con/kiểu triển khai `Handler`.

## 1. Phần tử `Class` trong annotation thực chất chứa gì?

Một `Class<?>` là đối tượng đại diện cho thông tin của một kiểu Java ở runtime, thường gọi là **class token**. Trong cú pháp annotation, `SomeType.class` là cách chỉ định class token phù hợp với quy tắc *giá trị annotation phải được xác định tại thời điểm biên dịch*.

```java
@interface ModelInfo {
    Class<?> model();
}

@ModelInfo(model = String.class)
class StringModel {}

@ModelInfo(model = int.class)
class PrimitiveModel {}

@ModelInfo(model = String[].class)
class ArrayModel {}
```

Điểm cần phân biệt:

- `String.class` chỉ ra kiểu `String`; nó **không** tạo chuỗi mới.
- `int.class` là class literal của kiểu nguyên thủy `int`, không phải một đối tượng có thể khởi tạo bằng constructor.
- `String[].class` là class literal của kiểu mảng `String[]`.
- `Class<?>` là **kiểu khai báo** của element; `String.class` là **giá trị** được truyền vào element.

Annotation lưu metadata về lựa chọn kiểu. Nếu chương trình cần khởi tạo một instance từ class token đó thì phải thực hiện riêng, chẳng hạn qua factory, dependency injection hoặc reflection; chỉ viết `@ModelInfo(model = String.class)` không tự chạy constructor.

Theo JLS Java 17 `9.6.1, kiểu trả về hợp lệ của annotation element có thể là `Class` hoặc một dạng tham số hóa của `Class`, ví dụ `Class<?>` hoặc `Class<? extends Handler>`. Đây là trường hợp hợp lệ đặc biệt của annotation element; không được suy rộng rằng mọi kiểu generic như `List<String>` hay `Map<String, Integer>` đều dùng được làm element.

## 2. Ý nghĩa dấu `?`: `Class<?>`

Trong Java generics, dấu `?` là **unbounded wildcard**: không cố định class token phải đại diện cho kiểu nào. Khi khai báo:

```java
@interface TypeHint {
    Class<?> value();
}
```

ta có thể ghi:

```java
@TypeHint(String.class)
class A {}

@TypeHint(Integer.class)
class B {}

@TypeHint(Runnable.class)
class C {}

@TypeHint(int.class)
class D {}
```

Dấu `?` không biến element thành `Object`. Mọi giá trị vẫn phải là một class token thuộc kiểu `Class`. Chẳng hạn `@TypeHint("String")` sai vì `"String"` là một `String`, không phải `Class<?>`; `@TypeHint(new Object())` cũng sai.

Cần hiểu tính **bất biến (invariance)** của generic `Class<T>`:

```java
Class<String> stringType = String.class;

// Không hợp lệ dù String extends Object:
// Class<Object> objectType = String.class;

Class<?> anyType = String.class; // Hợp lệ
```

`String` là con của `Object` nhưng `Class<String>` không phải con của `Class<Object>`. Dấu wildcard giải quyết nhu cầu nhận nhiều class token mà vẫn giữ thông tin rằng giá trị đó thuộc kiểu `Class`.

## 3. Giới hạn bằng `Class<? extends T>`

`Class<? extends T>` là class token của một kiểu **có thể gán cho `T`**, nghĩa là `T` hoặc lớp con của `T`, hoặc một lớp triển khai `T` nếu `T` là interface.

Trong khai báo annotation thực tế, hãy thay ký hiệu minh họa `T` bằng một **kiểu cụ thể đã biết**, chẳng hạn `Number`, `Runnable` hoặc interface nghiệp vụ do bạn định nghĩa:

```java
@interface NumericType {
    Class<? extends Number> value();
}

@NumericType(Integer.class)
class IntegralCase {}

@NumericType(Double.class)
class DecimalCase {}

@NumericType(Number.class)
class BaseCase {}
```

`Integer` và `Double` kế thừa `Number`; `Number.class` cũng hợp lệ vì cận trên `extends Number` bao gồm chính `Number`. Ngược lại:

```java
// Lỗi biên dịch: String không là subtype của Number.
// @NumericType(String.class)
// class InvalidNumericCase {}
```

Ở đây, `extends` trong wildcard bao quát cả **kế thừa class** và **triển khai interface**:

```java
interface Task {}

class BackupTask implements Task {}
class CleanupTask implements Task {}

@interface TaskType {
    Class<? extends Task> value();
}

@TaskType(BackupTask.class)
class BackupConfig {}

@TaskType(CleanupTask.class)
class CleanupConfig {}

// Sai: String không implements Task.
// @TaskType(String.class)
// class WrongTaskConfig {}
```

Không nên nhầm `Class<? extends T>` với `Class<T>`:

| Element type | `Integer.class` | `Number.class` | `String.class` |
|---|---|---|---|
| `Class<?>` | Hợp lệ | Hợp lệ | Hợp lệ |
| `Class<Number>` | Không hợp lệ | Hợp lệ | Không hợp lệ |
| `Class<? extends Number>` | Hợp lệ | Hợp lệ | Không hợp lệ |

`Class<Number>` chỉ chấp nhận class token có kiểu generic tương ứng là `Number`; `Class<? extends Number>` mở rộng cho các subtype của `Number`. Chính nhờ vậy, annotation có thể kiểm tra phần quan trọng của hợp đồng kiểu ngay khi biên dịch.

### Vì sao ví dụ thường viết `T` nhưng không khai báo `@interface Config<T>`?

Ký hiệu `T` trong `Class<? extends T>` thường là **biến kiểu trong giải thích generic**. Annotation interface của Java **không được generic**: không thể viết `@interface Config<T>`. Vì vậy không dùng:

```java
// Không hợp lệ: annotation interface không khai báo type parameter.
// @interface Config<T> {
//     Class<? extends T> value();
// }
```

Hãy thay `T` bằng tên kiểu thực tế:

```java
interface Service {}

@interface ServiceConfig {
    Class<? extends Service> implementation();
}
```

Bên ngoài annotation, trong generic class/method thông thường, `Class<? extends T>` hoàn toàn có thể dùng `T` là type parameter; giới hạn ở đây đến từ **quy tắc khai báo annotation**, không phải cấm chung của generics.

## 4. Cú pháp khi truyền class literal vào element

Khi element có tên `value`, Java cho phép bỏ phần `value =`:

```java
@interface JsonModel {
    Class<?> value();
}

@JsonModel(value = String.class)
class Explicit {}

@JsonModel(String.class)
class ShortForm {}
```

Hai annotation trên chứa cùng giá trị `String.class`.

Nếu tên element khác `value`, phải ghi tên element:

```java
@interface UseImplementation {
    Class<? extends Runnable> implementation();
}

@UseImplementation(implementation = Thread.class)
class WorkerConfig {}
```

`Thread` implement `Runnable` nên phép gán hợp lệ. `@UseImplementation(Thread.class)` sẽ lỗi vì annotation không có element tên `value`.

Giá trị phải là **class literal phù hợp**, không lấy từ một biến/runtime expression:

```java
class InvalidInputExamples {
    static final Class<?> CACHED = String.class;

    // Sai: không được truyền biến Class dù static final.
    // @JsonModel(CACHED)
    // class ByVariable {}

    // Sai: method call được tính ở runtime, không phải class literal.
    // @JsonModel(String.class.getClass())
    // class ByCall {}

    // Sai: annotation element không nhận null.
    // @JsonModel(null)
    // class NullValue {}
}
```

Một trường hợp khác: `List<String>.class` không phải cú pháp class literal hợp lệ; generics Java áp dụng *type erasure*, vì vậy có thể dùng `List.class` nhưng không dùng `List<String>.class`. Tương tự, không có `T.class` nếu `T` là type parameter.

## 5. Ví dụ Java 17+ chạy được: chọn Formatter bằng annotation

Ví dụ dưới đây dùng `Class<? extends Formatter>` làm element bắt buộc để compiler chỉ chấp nhận các class phù hợp. Đồng thời dùng `Class<?>` để chứa metadata không cần ràng buộc quan hệ kế thừa.

Tạo một file duy nhất tên `AnnotationClassElementsDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.Locale;

interface Formatter {
    String format(String input);
}

class UppercaseFormatter implements Formatter {
    public String format(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}

class LowercaseFormatter implements Formatter {
    public String format(String input) {
        return input.toLowerCase(Locale.ROOT);
    }
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface UseFormatter {
    Class<? extends Formatter> value();
    Class<?> marker() default Void.class;
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Candidates {
    Class<? extends Formatter>[] value() default {};
}

@UseFormatter(value = UppercaseFormatter.class, marker = String.class)
@Candidates({UppercaseFormatter.class, LowercaseFormatter.class})
class Report {}

@UseFormatter(LowercaseFormatter.class)
@Candidates(LowercaseFormatter.class)
class Message {}

public class AnnotationClassElementsDemo {
    static void inspect(Class<?> owner) throws ReflectiveOperationException {
        UseFormatter config = owner.getAnnotation(UseFormatter.class);
        Candidates candidates = owner.getAnnotation(Candidates.class);

        Class<? extends Formatter> type = config.value();
        Formatter formatter = type.getDeclaredConstructor().newInstance();

        String[] names = Arrays.stream(candidates.value())
                .map(Class::getSimpleName)
                .toArray(String[]::new);

        System.out.println(owner.getSimpleName() + " -> "
                + formatter.format("Java"));
        System.out.println("marker=" + config.marker().getSimpleName());
        System.out.println("candidates=" + Arrays.toString(names));
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        inspect(Report.class);
        inspect(Message.class);
    }
}
```

Biên dịch với Java 17 hoặc JDK mới hơn có hỗ trợ `--release 17`:

```bash
javac --release 17 AnnotationClassElementsDemo.java
java AnnotationClassElementsDemo
```

Kết quả:

```text
Report -> JAVA
marker=String
candidates=[UppercaseFormatter, LowercaseFormatter]
Message -> java
marker=Void
candidates=[LowercaseFormatter]
```

Các bước xảy ra:

1. `@UseFormatter(UppercaseFormatter.class)` hoặc `@UseFormatter(LowercaseFormatter.class)` lưu metadata về class; compiler xác minh kiểu đó implements `Formatter`.
2. `@Retention(RetentionPolicy.RUNTIME)` giữ annotation trong metadata runtime, để `Class.getAnnotation(...)` đọc được. `@Target(ElementType.TYPE)` cho phép gắn annotation vào class.
3. `config.value()` trả về `Class<? extends Formatter>` đã chọn; `getDeclaredConstructor().newInstance()` là lệnh **tạo đối tượng thật**, tách biệt với bước khai báo annotation.
4. `marker` có kiểu `Class<?>` nên `String.class` được chấp nhận. Ở `Message`, không truyền `marker` nên nhận `Void.class` từ giá trị mặc định.
5. `Candidates` chứa **mảng class token**; array một phần tử được phép viết ngắn gọn `@Candidates(LowercaseFormatter.class)`.

Ví dụ được thiết kế để có constructor không đối số và lớp truy cập được từ chính chương trình. Trong ứng dụng thực tế, class token không bảo đảm kiểu được chọn có constructor phù hợp hay có thể khởi tạo: interface, abstract class, constructor có tham số, constructor không truy cập được hoặc constructor ném ngoại lệ vẫn có thể gây lỗi ở bước tạo instance. Trong môi trường framework, factory hoặc dependency injection thường là nơi khởi tạo service.

**Lưu ý phạm vi kiểm tra:** `Class<? extends Formatter>` kiểm tra **quan hệ kiểu tại compile time** đối với class literal; nó không chứng minh rằng formatter thực thi đúng yêu cầu nghiệp vụ hoặc thread-safe.

## 6. Mảng `Class<?>[]` và `Class<? extends T>[]`

Annotation element cho phép **mảng một chiều** của kiểu `Class` hợp lệ, kể cả Class có wildcard. Đây là cách mô tả nhiều kiểu cùng lúc.

```java
@interface Dependencies {
    Class<?>[] value();
}

@Dependencies({String.class, Integer.class})
class UsesSeveralTypes {}

@Dependencies(String.class)
class UsesOneType {}

@Dependencies({})
class UsesNoTypes {}
```

Như mọi annotation element kiểu mảng, có thể dùng cú pháp ngắn khi chỉ có một phần tử. Nếu muốn hạn chế mọi phần tử về cùng một họ kiểu:

```java
interface Plugin {}

class FilePlugin implements Plugin {}
class NetworkPlugin implements Plugin {}

@interface Plugins {
    Class<? extends Plugin>[] value() default {};
}

@Plugins({FilePlugin.class, NetworkPlugin.class})
class TwoPlugins {}

@Plugins(FilePlugin.class)
class OnePlugin {}

@Plugins
class NoPlugins {}

@Plugins({})
class ExplicitlyEmpty {}
```

So sánh:

- `Class<?>`: một class token của kiểu bất kỳ.
- `Class<? extends Plugin>`: một class token thuộc họ `Plugin`.
- `Class<?>[]`: mảng class token của các kiểu bất kỳ.
- `Class<? extends Plugin>[]`: mảng class token, **mỗi phần tử** thuộc họ `Plugin`.

Mảng rỗng `{}` là một giá trị hợp lệ cho element kiểu mảng; bỏ element chỉ hợp lệ nếu khai báo có `default`. Annotation không cho element kiểu mảng nhiều chiều như `Class<?>[][]`; quy tắc element chỉ cho mảng một chiều có component type thuộc danh sách kiểu được phép.

## 7. `default`, class sentinel và chuyện không có `null`

Với element kiểu `Class<?>`, annotation không cho truyền `null`; cũng không có cú pháp “không có class” tự nhiên như một giá trị `Class`. Tùy yêu cầu, thiết kế có thể chọn:

**Cách 1: element bắt buộc**

```java
@interface RepositoryBinding {
    Class<?> entity();
}

@RepositoryBinding(entity = String.class)
class StringRepository {}
```

Bỏ `entity` sẽ lỗi biên dịch.

**Cách 2: đặt một class đại diện cho trạng thái “chưa chọn”**

```java
@interface OptionalEntity {
    Class<?> value() default Void.class;
}

@OptionalEntity
class UnspecifiedEntity {}

@OptionalEntity(String.class)
class SpecifiedEntity {}
```

`Void.class` chỉ là một **quy ước sentinel do người thiết kế chọn**. Nó là một class token hợp lệ, không tự động mang nghĩa “không có giá trị” theo ngôn ngữ Java. Code đọc annotation phải chủ động diễn giải:

```java
Class<?> selected = UnspecifiedEntity.class
        .getAnnotation(OptionalEntity.class).value();

if (selected == Void.class) {
    System.out.println("No entity selected");
}
```

Nếu dùng `Class<? extends Plugin>`, `Void.class` **không hợp lệ** vì `Void` không implements `Plugin`. Có thể khai báo `default Plugin.class` nếu `Plugin` là interface, nhưng khi đọc cần coi `Plugin.class` là sentinel theo quy ước; bản thân interface đó không thể tạo instance trực tiếp. Một lựa chọn khác là tạo một loại plugin đặc biệt theo hợp đồng ứng dụng, hoặc đổi thiết kế để element không bắt buộc ở nơi cần vắng mặt.

## 8. Những điều kiểu ràng buộc `extends` kiểm tra được và không kiểm tra được

Khi sử dụng `Class<? extends Service>`:

```java
interface Service {
    void execute();
}

abstract class AbstractService implements Service {}

class ConcreteService implements Service {
    public void execute() {
        System.out.println("done");
    }
}

@interface ServiceSelector {
    Class<? extends Service> value();
}

@ServiceSelector(Service.class)
class SelectInterface {}

@ServiceSelector(AbstractService.class)
class SelectAbstract {}

@ServiceSelector(ConcreteService.class)
class SelectConcrete {}
```

**Cả ba trường hợp đều hợp lệ ở thời điểm biên dịch**: bản thân `Service`, abstract class triển khai `Service` và concrete class đều thỏa cận `extends Service`. Nhưng chỉ có `ConcreteService` phù hợp để khởi tạo trực tiếp qua constructor tương ứng trong ví dụ này.

Ràng buộc generic **không thể** bảo đảm:

- class được chỉ định là concrete thay vì interface hoặc abstract class;
- có constructor công khai không đối số;
- class có đủ quyền truy cập qua reflection/module system;
- constructor chạy thành công và đối tượng đáp ứng yêu cầu nghiệp vụ.

Nếu hệ thống thực sự cần những điều kiện đó, phải xác minh thêm ở tầng xử lý annotation: bằng annotation processor khi biên dịch hoặc bằng validation khi khởi động/runtime. Khi class được chỉ định là subtype về mặt Java, compiler đã giúp loại bỏ lựa chọn **khác họ kiểu** từ sớm, nhưng không thay thế kiểm tra khả năng khởi tạo.

## 9. Đọc element `Class<?>` và giới hạn generic lúc runtime

Bởi annotation metadata có thể tồn tại tới runtime nếu khai báo retention phù hợp, một chương trình có thể đọc:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Mapping {
    Class<?> requestType();
}

@Mapping(requestType = String.class)
class StringEndpoint {}

class MetadataReader {
    static void read() {
        Mapping mapping = StringEndpoint.class.getAnnotation(Mapping.class);
        Class<?> type = mapping.requestType();
        System.out.println(type.getName());
    }
}
```

`Class<?>` là đối tượng mang thông tin về kiểu ở runtime. Tuy nhiên, Java generics có *type erasure*: class token `List.class` không mang đầy đủ kiểu tham số `List<String>`. Annotation element nhận `Class<?>` không thể biểu diễn một kiểu tổng quát như `List<String>` chỉ bằng `List.class`.

Nếu cần metadata có cả generic type, hãy cân nhắc thiết kế khác như khai báo nhiều element riêng (kiểu thô `Class<?>` cùng thông tin cấu hình bổ sung) hoặc xử lý biểu diễn kiểu ở tầng reflection/annotation processing phù hợp. Không nên giả vờ rằng `Class<List<String>>` có thể được truyền bằng `List<String>.class`.

## 10. Cảnh báo và lỗi thường gặp

### Lỗi 1: Truyền giá trị là tên class bằng chuỗi

```java
@interface Select {
    Class<?> value();
}

// Sai: giá trị String, không phải Class.
// @Select("java.lang.String")
// class WrongName {}

@Select(String.class)
class CorrectName {}
```

Nếu API được thiết kế để nhận tên class dạng chuỗi thì element phải khai báo `String`; trường hợp này không được compiler kiểm tra quan hệ type như `Class<? extends T>`.

### Lỗi 2: Cận generic không khớp

```java
@interface NumberType {
    Class<? extends Number> value();
}

// Sai: String không là Number.
// @NumberType(String.class)
// class Wrong {}

@NumberType(Integer.class)
class Right {}
```

Đây là lỗi compile time, không phải lỗi mà `@SuppressWarnings("unchecked")` có thể xóa.

### Lỗi 3: Dùng `Class<T>` quá chặt

```java
@interface ExactNumber {
    Class<Number> value();
}

// Sai: Class<Integer> không gán cho Class<Number>.
// @ExactNumber(Integer.class)
// class Wrong {}

@ExactNumber(Number.class)
class Right {}
```

Nếu yêu cầu thật sự là “một class thuộc họ Number”, đổi sang `Class<? extends Number>`.

### Lỗi 4: Truyền kết quả của phương thức hoặc biến class token

```java
@interface InspectType {
    Class<?> value();
}

class Lookup {
    static final Class<?> TYPE = String.class;
}

// Sai dù biến khai báo final:
// @InspectType(Lookup.TYPE)
// class Wrong {}

@InspectType(String.class)
class Right {}
```

Giá trị annotation phải đáp ứng cú pháp/giới hạn của *element value*; biến `Class<?>` không trở thành class literal chỉ vì có `final`.

### Lỗi 5: Nhầm class token với instance

```java
interface Job {}
class SendJob implements Job {}

@interface JobConfig {
    Class<? extends Job> value();
}

@JobConfig(SendJob.class)
class Sender {}
```

Gắn annotation không gọi `new SendJob()`. Chỉ khi phần code khác chủ động đọc `JobConfig` rồi yêu cầu factory/reflective constructor thì instance mới có thể được tạo. Kiểu ràng buộc giúp kiểm tra đối tượng **nếu được tạo** sẽ thuộc họ `Job`, nhưng không tạo ra đối tượng.

### Lỗi 6: Giả định mọi class token có thể khởi tạo

Nếu element khai báo `Class<? extends Runnable>`, `Runnable.class` vẫn khớp bound vì chính interface đó thỏa cận kiểu; nhưng gọi `Runnable.class.getDeclaredConstructor().newInstance()` không thể tạo instance cho interface. Tương tự abstract class hoặc class không có constructor không đối số. Hãy đặt ra hợp đồng rõ cho ứng dụng và kiểm tra lúc xử lý metadata.

### Lỗi 7: Quên retention hoặc mảng một phần tử

Mặc định annotation có retention `CLASS`; khi muốn dùng `getAnnotation(...)` ở runtime, cần `@Retention(RetentionPolicy.RUNTIME)`. Với element mảng, `@Plugins(FilePlugin.class)` là mảng **một** class token, còn `@Plugins({})` là mảng rỗng; đây là cú pháp hợp lệ và không đổi kiểu khai báo `Class<? extends Plugin>[]`.

## 11. Chọn kiểu element nào cho đúng bài toán?

| Nhu cầu | Kiểu element phù hợp | Ví dụ giá trị |
|---|---|---|
| Ghi nhận một kiểu bất kỳ | `Class<?>` | `String.class` |
| Chỉ chấp nhận kiểu thuộc họ interface/base class | `Class<? extends Handler>` | `EmailHandler.class` |
| Ghi nhiều kiểu không cần chung bound | `Class<?>[]` | `{String.class, Integer.class}` |
| Ghi nhiều implementation thuộc cùng hợp đồng | `Class<? extends Handler>[]` | `{EmailHandler.class, SmsHandler.class}` |
| Bắt buộc đúng một kiểu chính xác, không nhận subtype qua generic | `Class<Number>` | `Number.class` |

Trong thiết kế annotation dùng cho plugin, strategy hoặc handler, `Class<? extends Handler>` thường diễn đạt intent rõ hơn `Class<?>`: compiler sẽ phát hiện sớm việc truyền class không implement `Handler`. Với metadata mô tả một loại payload hoặc một kiểu không có quan hệ kế thừa bắt buộc, `Class<?>` có thể phù hợp hơn.

## 12. Bài tập tự kiểm tra

**Bài 1.** Cho:

```java
interface Parser {}
class JsonParser implements Parser {}
class XmlParser implements Parser {}

@interface Parsers {
    Class<? extends Parser>[] value();
}
```

Hãy phân loại:

1. `@Parsers({JsonParser.class, XmlParser.class})`
2. `@Parsers(JsonParser.class)`
3. `@Parsers({})`
4. `@Parsers(String.class)`
5. `@Parsers`

**Đáp án:** 1, 2, 3 hợp lệ. Trường hợp 4 sai vì `String` không implements `Parser`. Trường hợp 5 sai vì `value()` là element bắt buộc chưa có `default`.

**Bài 2.** Tại sao `Class<?>` nhận `String.class` nhưng `Class<Object>` không nhận?

**Đáp án:** `Class<T>` là kiểu generic bất biến: quan hệ `String extends Object` không suy ra `Class<String> extends Class<Object>`. Wildcard `?` cho phép `Class<?>` tham chiếu tới class token của nhiều kiểu.

**Bài 3.** `@interface Factory<T> { Class<? extends T> value(); }` có phải annotation hợp lệ không? Muốn giới hạn implementation thuộc `Runnable` thì khai báo thế nào?

**Đáp án:** Không. Annotation interface không thể generic. Dùng `@interface Factory { Class<? extends Runnable> value(); }`.

**Bài 4.** `@Factory(Runnable.class)` có hợp lệ với khai báo bài 3 không? Nó có đủ để gọi constructor và chạy một Runnable không?

**Đáp án:** Hợp lệ về quan hệ kiểu vì `Runnable` thỏa `extends Runnable`. Nhưng `Runnable` là interface, không khởi tạo được trực tiếp. Phần code đọc metadata vẫn cần kiểm tra được phép khởi tạo hay dùng factory/container thích hợp.

**Bài 5.** Khi `Class<?> marker() default Void.class;`, việc bỏ `marker` có làm annotation trả về `null` không?

**Đáp án:** Không. Giá trị của element là `Void.class` đúng như khai báo mặc định; ý nghĩa “không chọn” chỉ tồn tại khi ứng dụng chủ động quy ước.

## Tài liệu tham khảo

- [JLS Java SE 17 — `9.6.1 Annotation Interface Elements`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.1): xác nhận kiểu `Class`, dạng parameterized `Class`, mảng một chiều, và ví dụ chính thức `Class<? extends Formatter>`.
- [JLS Java SE 17 — `9.7.1 Normal Annotations`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.1): cú pháp và giới hạn giá trị của annotation element.
- [Java SE 17 API — `Class<T>`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): class token, `getAnnotation`, `getDeclaredConstructor` và các API runtime liên quan.
- [JLS Java SE 17 — `4.5 Parameterized Types`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5): wildcard và quan hệ kiểu generic.
