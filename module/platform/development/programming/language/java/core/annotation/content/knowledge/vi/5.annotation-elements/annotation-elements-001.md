# Các kiểu hợp lệ của phần tử và giá trị annotation trong Java

Trong Java, annotation dùng để **gắn metadata có cấu trúc** lên một khai báo hoặc vị trí được phép. Một annotation type được khai báo bằng `@interface`; các phương thức không có tham số bên trong nó được gọi là **annotation elements (phần tử annotation)**. Khi sử dụng annotation, ta gán giá trị cho những phần tử này.

Điểm quan trọng: **kiểu trả về của phần tử annotation bị Java giới hạn chặt chẽ**, khác với phương thức Java thông thường. Java chỉ cho phép tám kiểu nguyên thủy, `String`, `Class` (kể cả một số dạng tham số hóa), kiểu `enum`, kiểu annotation khác và **mảng một chiều** của những kiểu đó. Giá trị được gán cũng phải tuân theo quy tắc biểu thức giá trị của annotation; không phải biểu thức Java nào trả về đúng kiểu cũng dùng được.

Bài này tập trung vào **những kiểu và giá trị nào hợp lệ**, cách compiler kiểm tra và cách khai báo/sử dụng chúng đúng cách.

## 1. Phần tử annotation là gì?

Ví dụ:

```java
@interface RetryPolicy {
    int attempts();
    String reason() default "temporary";
}
```

- `attempts()` là một phần tử kiểu `int`, **không có giá trị mặc định**. Mọi nơi dùng `@RetryPolicy` phải cung cấp `attempts`.
- `reason()` là một phần tử kiểu `String`, có **giá trị mặc định** `"temporary"`.
- Dù cú pháp trông giống phương thức, ta không viết thân triển khai, tham số hay logic tính toán trong các phần tử.
- Tại điểm sử dụng, `@RetryPolicy(attempts = 3)` hợp lệ; `reason` nhận giá trị mặc định.

Hình thức sử dụng đầy đủ:

```java
@RetryPolicy(attempts = 3, reason = "network")
class NetworkJob {
}
```

Một annotation declaration có thể khai báo nhiều phần tử, nhưng **mỗi phần tử phải có kiểu hợp lệ**. Java compiler kiểm tra điều này khi biên dịch annotation type, trước khi cần tới framework hoặc Reflection.

## 2. Danh sách đầy đủ các kiểu phần tử hợp lệ

Theo quy tắc Java dành cho annotation element, kiểu trả về được phép thuộc một trong các nhóm sau:

| Nhóm | Kiểu khai báo hợp lệ | Ví dụ giá trị khi gắn annotation |
| --- | --- | --- |
| Tám kiểu nguyên thủy | `boolean`, `byte`, `short`, `int`, `long`, `float`, `double`, `char` | `enabled = true`, `count = 3`, `letter = 'A'` |
| Chuỗi | `String` | `name = "checkout"` |
| Kiểu lớp | `Class` hoặc cách tham số hóa hợp lệ của `Class`, ví dụ `Class<?>`, `Class<? extends Runnable>` | `type = String.class`, `handler = Thread.class` |
| Enum | Một kiểu `enum` cụ thể | `priority = Priority.HIGH` |
| Annotation | Một kiểu annotation được khai báo bằng `@interface` | `label = @Label("public")` |
| Mảng một chiều | `T[]` với `T` là một kiểu thuộc năm nhóm trên | `tags = {"java", "core"}`, `types = {String.class, Integer.class}` |

Trong bảng, “tám kiểu nguyên thủy” không bao gồm `void`. Nhóm `Class` là đối tượng lớp trong metadata, ví dụ `String.class`, chứ không phải kiểu trả về tùy ý của một phương thức Java.

**Quy tắc cốt lõi:** nếu `T` là một kiểu phần tử hợp lệ không phải mảng, thì `T[]` cũng là kiểu phần tử hợp lệ; nhưng `T[][]` **không hợp lệ**, dù mảng nhiều chiều là kiểu hợp lệ trong Java thông thường.

### 2.1. Tám kiểu nguyên thủy

Một annotation có thể khai báo:

```java
@interface PrimitiveOptions {
    boolean enabled() default true;
    byte level() default 5;
    short threshold() default 100;
    int retries() default 3;
    long timeoutMillis() default 1000L;
    float ratio() default 0.5f;
    double factor() default 1.25;
    char separator() default ':';
}
```

Các giá trị mặc định đều là những biểu thức hằng tương thích với kiểu phần tử. Với `byte` và `short`, Java có quy tắc chuyển đổi hẹp cho **hằng nguyên nằm trong khoảng giá trị của kiểu đích**; ví dụ `byte level() default 127;` hợp lệ, còn `byte level() default 128;` là lỗi vì vượt phạm vi.

Lưu ý phân biệt kiểu nguyên thủy và wrapper: `int` được phép; `Integer` không được phép làm kiểu phần tử. Tương tự `boolean` hợp lệ còn `Boolean` không hợp lệ.

### 2.2. String

```java
@interface RouteInfo {
    String path();
    String description() default "Endpoint";
}
```

Được sử dụng với các literal hoặc biểu thức hằng của `String`:

```java
@RouteInfo(path = "/api" + "/orders")
class OrdersEndpoint {
}
```

Nối các string literal như trên tạo một biểu thức hằng hợp lệ. Nhưng `path = System.getenv("ROUTE")` không hợp lệ vì phương thức được gọi lúc chạy và kết quả không phải hằng mà compiler có thể dùng làm giá trị annotation.

`String` được cho phép; các kiểu như `StringBuilder`, `CharSequence`, `Optional<String>` hoặc `List<String>` **không được phép** làm kiểu trả về của annotation element.

### 2.3. Class và các class literal

```java
@interface HandlerInfo {
    Class<?> type();
    Class<? extends Runnable> runnableType();
}
```

Sử dụng:

```java
@HandlerInfo(type = String.class, runnableType = Thread.class)
class TaskDefinition {
}
```

- `String.class` biểu diễn kiểu `String`, **không tạo ra một đối tượng `String`**.
- `Thread.class` phù hợp ràng buộc `Class<? extends Runnable>` vì `Thread` triển khai `Runnable`.
- `Class<?>` phù hợp với class literal của nhiều kiểu, chẳng hạn `String.class`, `int.class` hoặc `String[].class`.
- `Class<? extends Runnable>` giúp compiler kiểm tra một ràng buộc kiểu nhất định ngay tại chỗ gắn annotation.

Cần ghi **class literal** như `String.class` thay vì `new String()`, `String.class.getName()` hay kết quả `Class.forName("...")`. Những cách sau không phải cú pháp giá trị `Class` được phép ở annotation. `Class` là một trong những ngoại lệ đặc biệt: class literal là loại giá trị được phép dùng trong annotation, dù không thuộc biểu thức hằng compile-time thông thường như `1 + 2`.

### 2.4. Enum

Định nghĩa:

```java
enum Priority {
    LOW, MEDIUM, HIGH
}

@interface QueueConfig {
    Priority priority() default Priority.MEDIUM;
}
```

Sử dụng:

```java
@QueueConfig(priority = Priority.HIGH)
class FastQueue {
}
```

Giá trị phải là **enum constant** của đúng kiểu yêu cầu: `Priority.HIGH`. Không thể thay bằng `"HIGH"`, `Priority.valueOf("HIGH")` hay một phép gọi phương thức khác, kể cả nếu lúc chạy cho ra cùng một enum constant.

`enum` rất thích hợp khi annotation chỉ được chọn một trạng thái từ một danh sách hữu hạn. Nếu cần nhiều trạng thái cùng lúc, có thể khai báo `Priority[]` và truyền mảng một chiều.

### 2.5. Annotation lồng làm giá trị

Một annotation có thể chứa một annotation khác dưới dạng giá trị phần tử:

```java
@interface Label {
    String value();
}

@interface Endpoint {
    Label label();
}

@Endpoint(label = @Label("public"))
class PublicEndpoint {
}
```

`@Label("public")` là **một annotation value**, không phải một object tùy ý được tạo bằng `new`. Tính hợp lệ được kiểm tra theo khai báo `Label`. Nếu `Label` có nhiều phần tử bắt buộc, mọi phần tử thiếu mặc định phải được cung cấp.

Khi annotation bên ngoài được đọc lúc chạy qua Reflection, những giá trị annotation lồng có thể được truy cập qua phần tử tương ứng, với điều kiện loại annotation ngoài được giữ đến runtime và cấu hình tải kiểu cho phép. Các ràng buộc về cách dùng và vòng đời vẫn cần phân biệt với **tập kiểu phần tử được phép**.

## 3. Mảng một chiều: quy tắc thường dễ nhầm nhất

Ví dụ khai báo hợp lệ:

```java
@interface BatchInfo {
    int[] retries();
    String[] tags() default {};
    Class<?>[] dependencies() default {};
    Priority[] priorities() default {Priority.LOW};
    Label[] labels() default {};
}
```

Các biểu thức trong mảng phải có kiểu phần tử hợp lệ tương ứng. Ví dụ:

```java
@BatchInfo(
    retries = {1, 2, 3},
    tags = {"java", "annotations"},
    dependencies = {String.class, Integer.class},
    priorities = {Priority.HIGH},
    labels = {@Label("stable"), @Label("public")}
)
class BatchTask {
}
```

Trong ví dụ này, `Priority` và `Label` cần được khai báo như ở những mục trước. Đây là đoạn minh họa cách gắn annotation, không phải chương trình độc lập.

Cần nhớ:

1. **Mảng rỗng hợp lệ:** `tags = {}`.
2. **Mảng một phần tử hợp lệ:** `tags = {"java"}`.
3. **Có thể bỏ dấu ngoặc nhọn khi truyền đúng một giá trị phù hợp:** `tags = "java"` tương đương về nội dung với một mảng gồm một phần tử `"java"` trong cú pháp annotation.
4. **Không được dùng `new` để tạo mảng trong annotation:** `tags = new String[]{"java"}` không phải dạng annotation array initializer được ngôn ngữ chấp nhận.
5. **Mảng nhiều chiều không hợp lệ ở định nghĩa phần tử:** `String[][] tags();` sẽ bị compiler từ chối.
6. Mỗi giá trị thành phần phải thỏa chính quy tắc của kiểu phần tử; ví dụ không thể đặt `System.currentTimeMillis()` vào một phần tử mảng `long[]`.

Việc Java bình thường cho phép `new String[] {...}` hoặc `String[][]` không thay đổi các luật riêng của giá trị annotation.

## 4. Ví dụ chạy được: đủ năm nhóm kiểu và mảng

Tạo tệp duy nhất **`AnnotationElementTypesDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

enum Priority {
    LOW, HIGH
}

@Retention(RetentionPolicy.RUNTIME)
@interface Label {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Profile {
    int retries() default 2;                      // Primitive
    String owner();                               // String
    Class<? extends Runnable> handler();          // Class
    Priority priority() default Priority.LOW;     // Enum
    Label label();                                // Annotation
    String[] tags() default {};                   // Mảng một chiều
    boolean enabled() default true;               // Primitive
}

@Profile(
    owner = "core",
    handler = Thread.class,
    priority = Priority.HIGH,
    label = @Label("public"),
    tags = {"annotation", "java"}
)
public class AnnotationElementTypesDemo {
    public static void main(String[] args) {
        Profile profile =
                AnnotationElementTypesDemo.class.getAnnotation(Profile.class);

        System.out.println(profile.owner());
        System.out.println(profile.retries());
        System.out.println(profile.handler().getSimpleName());
        System.out.println(profile.priority());
        System.out.println(profile.label().value());
        System.out.println(String.join(", ", profile.tags()));
        System.out.println(profile.enabled());
    }
}
```

Với JDK 17+:

```bash
javac --release 17 AnnotationElementTypesDemo.java
java AnnotationElementTypesDemo
```

Stdout:

```text
core
2
Thread
HIGH
public
annotation, java
true
```

**Phân tích từng dòng:**

- `owner()` đọc chuỗi đã cung cấp `"core"`.
- `retries()` đọc giá trị **mặc định** `2`, bởi `@Profile` không ghi đè phần tử này.
- `handler()` trả `Class<? extends Runnable>` với giá trị `Thread.class`; `getSimpleName()` trả `Thread`.
- `priority()` nhận enum constant `Priority.HIGH`.
- `label()` trả annotation lồng; gọi tiếp `value()` lấy `"public"`.
- `tags()` là một mảng `String[]` được cung cấp bằng hai phần tử.
- `enabled()` nhận giá trị mặc định `true`.

`@Retention(RetentionPolicy.RUNTIME)` đặt trên `Profile` để Reflection lấy được `Profile` từ class. Chính mã trong `main` **chủ động gọi** `getAnnotation` và các accessor; không phải annotation tự in ra stdout. `@Target(ElementType.TYPE)` giới hạn nơi được phép gắn `Profile` lên các khai báo kiểu phù hợp.

## 5. Cú pháp value(), một phần tử và giá trị mặc định

Một annotation element tên `value` có cú pháp sử dụng rút gọn đặc biệt:

```java
@interface Label {
    String value();
}
```

Hai cách dùng tương đương:

```java
@Label(value = "public")
class A {
}

@Label("public")
class B {
}
```

Nếu tên element **không phải `value`**, phải ghi rõ tên:

```java
@interface Feature {
    String name();
}

@Feature(name = "billing")
class Billing {
}
```

`@Feature("billing")` là lỗi vì `Feature` không khai báo phần tử `value()`.

### 5.1. default là giá trị annotation, không phải thân phương thức

```java
@interface Retry {
    int times() default 3;
    String[] errors() default {};
}
```

Ở chỗ sử dụng, có thể viết `@Retry` mà không chỉ định phần tử nào; khi đọc sẽ nhận mặc định `3` và mảng rỗng.

Giá trị mặc định phải hợp lệ theo đúng nhóm kiểu. Ví dụ:

```java
@interface Notification {
    String channel() default "email";
    Priority priority() default Priority.LOW;
    Class<?> payloadType() default String.class;
    Label label() default @Label("stable");
    int[] codes() default {200, 201};
}
```

Tất cả đều hợp lệ với `Priority` và `Label` đã khai báo ở trên.

**Không có giá trị mặc định `null` trong annotation.** Nếu muốn mô tả “không được chọn”, thiết kế một giá trị rõ nghĩa như enum `UNKNOWN`, mảng rỗng hoặc một sentinel được tài liệu hóa tùy nhu cầu; không thể viết `String name() default null;`.

**Điểm tinh tế:** giá trị default thuộc **khai báo annotation type**; nếu nơi sử dụng không chỉ định phần tử, hệ thống đọc annotation sử dụng mặc định từ định nghĩa annotation tương ứng. Thay default có thể thay đổi giá trị quan sát được của nơi dùng cũ khi chạy với phiên bản annotation type mới, vì vậy default cũng là một phần cần chú ý khi thiết kế API.

### 5.2. Giá trị mảng với value() có thể viết rất gọn

Ví dụ độc lập: tạo tệp **`AnnotationArrayShorthandDemo.java`**.

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@interface Aliases {
    String[] value() default {};
}

@Aliases("one")
class One {
}

@Aliases({"one", "two"})
class Two {
}

@Aliases
class Empty {
}

public class AnnotationArrayShorthandDemo {
    public static void main(String[] args) {
        System.out.println(Arrays.toString(
                One.class.getAnnotation(Aliases.class).value()));
        System.out.println(Arrays.toString(
                Two.class.getAnnotation(Aliases.class).value()));
        System.out.println(Arrays.toString(
                Empty.class.getAnnotation(Aliases.class).value()));
    }
}
```

Chạy:

```bash
javac --release 17 AnnotationArrayShorthandDemo.java
java AnnotationArrayShorthandDemo
```

Stdout chính xác:

```text
[one]
[one, two]
[]
```

Giải thích:

- `@Aliases("one")` vừa rút gọn tên `value` vừa dùng phép rút gọn một phần tử cho `String[]`.
- `@Aliases({"one", "two"})` cung cấp mảng hai phần tử bằng annotation array initializer.
- `@Aliases` không truyền giá trị, nên nhận mảng rỗng mặc định.
- `@Retention(RUNTIME)` giúp ví dụ Reflection đọc được thông tin khi chạy.

Đối với phần tử `int[]`, cách dùng `@Codes(404)` cũng có thể hợp lệ nếu annotation có `int[] value()`; nhưng `@Codes({404, 500})` rõ ràng hơn khi cung cấp nhiều giá trị.

## 6. Giá trị annotation: “đúng kiểu” chưa đủ

Giá trị của annotation thường được **quyết định ở thời điểm biên dịch**. Với kiểu nguyên thủy và `String`, compiler yêu cầu **constant expression** hợp lệ. Với `Class`, cần class literal; với enum, cần enum constant; với annotation lồng, cần annotation expression; với mảng, cần dạng initializer annotation được phép.

### 6.1. Hằng compile-time cho kiểu nguyên thủy và String

```java
final class ConfigConstants {
    static final int RETRIES = 1 + 2;
    static final String PREFIX = "/api";
}

@interface ApiSettings {
    int retries();
    String path();
}

@ApiSettings(
    retries = ConfigConstants.RETRIES,
    path = ConfigConstants.PREFIX + "/items"
)
class ItemApi {
}
```

Các trường `static final` nêu trên là **constant variables** với initializer là constant expression, nên compiler có thể dùng chúng trong annotation.

Trái lại:

```java
class DynamicSettings {
    static final int RETRIES = Integer.parseInt("3");
}
```

`DynamicSettings.RETRIES` tuy là `static final int` nhưng **không phải constant variable** theo nghĩa Java do initializer là lời gọi phương thức, vì vậy không thể làm giá trị `retries = DynamicSettings.RETRIES` trong annotation. `final` tự nó không đủ; biểu thức khởi tạo phải thỏa điều kiện hằng compile-time.

### 6.2. Các dạng giá trị không hợp lệ

Giả sử có khai báo:

```java
@interface Settings {
    String name();
    Class<?> type();
    Priority priority();
}
```

Những cách dùng sau **đều không biên dịch được**; mỗi ví dụ minh họa một lỗi độc lập:

```java
// Sai: lời gọi phương thức không phải hằng String.
@Settings(name = System.getProperty("name"),
          type = String.class, priority = Priority.HIGH)
class BadName {}

// Sai: lời gọi phương thức không phải class literal.
@Settings(name = "ok",
          type = Class.forName("java.lang.String"),
          priority = Priority.HIGH)
class BadType {}

// Sai: kết quả của method call không phải enum constant trực tiếp.
@Settings(name = "ok",
          type = String.class,
          priority = Priority.valueOf("HIGH"))
class BadPriority {}
```

Đây là các ví dụ **cố ý sai** để giải thích quy tắc compiler, không phải file dùng để chạy. Ngoài quy tắc annotation, `Class.forName` còn khai báo checked exception trong ngữ cảnh sử dụng thông thường; tuy nhiên lý do đủ để loại nó ở đây là **nó không phải class literal được phép**.

## 7. Những kiểu element bị cấm và nguyên nhân

Các kiểu dưới đây có thể sử dụng trong Java thông thường nhưng **không được phép** làm kiểu trả về của annotation element:

| Khai báo cố ý sai | Vì sao sai | Hướng khai báo phù hợp |
| --- | --- | --- |
| `Integer count();` | Wrapper `Integer` không thuộc nhóm primitive | `int count();` |
| `Object value();` | `Object` không phải kiểu element được phép | Chọn một kiểu tường minh hợp lệ, tùy ý nghĩa |
| `List<String> tags();` | `List` không thuộc nhóm được phép | `String[] tags();` |
| `Optional<String> name();` | `Optional` không hợp lệ | `String name() default "";` khi có sentinel được định nghĩa |
| `String[][] aliases();` | Mảng đa chiều không được phép | `String[] aliases();` hoặc mô hình annotation lồng |
| `Runnable handler();` | Interface tùy ý không phải `Class` hay annotation type | `Class<? extends Runnable> handler();` |
| `void run();` | `void` không là kiểu annotation element | Chọn kiểu trả về hợp lệ; annotation không chứa hành vi |
| `int[] values() default null;` | `null` không là giá trị phần tử hợp lệ | `int[] values() default {};` |

**Ví dụ interface thay vì Class:** nếu muốn metadata biểu diễn *loại xử lý* có khả năng chạy, `Class<? extends Runnable> handler();` lưu kiểu triển khai dưới dạng `SomeRunnable.class`. Nó không tạo instance hoặc tự gọi `run()`; mã xử lý sau đó mới quyết định cách khởi tạo và sử dụng.

**Ví dụ cấu trúc phức tạp:** thay vì `Map<String, String>` (không hợp lệ), có thể mô hình hóa bằng annotation lồng với những phần tử hợp lệ:

```java
@interface Entry {
    String key();
    String value();
}

@interface Entries {
    Entry[] value();
}

@Entries({
    @Entry(key = "mode", value = "safe"),
    @Entry(key = "region", value = "apac")
})
class ServiceConfig {
}
```

Cách này lưu một danh sách key-value ở mức metadata, **không hề biến annotation thành `Map`**. Nếu cần kiểm tra khóa trùng hoặc chuyển sang Map, mã tiêu thụ annotation phải chủ động làm việc đó.

## 8. Annotation element không phải method thông thường

Ngoài kiểu trả về, phương thức element còn có những giới hạn riêng:

- Không có tham số: `String name();` hợp lệ, còn `String name(int id);` không hợp lệ.
- Không có kiểu tham số hóa riêng của phương thức: không khai báo `<T> T get();` làm element.
- Không khai báo `throws` cho annotation element.
- Không cung cấp thân phương thức Java, kể cả khi muốn “tính giá trị mặc định”. Từ khóa `default` của element chỉ nhận **giá trị annotation**, không phải khối lệnh `default { ... }` của interface method.
- Không khai báo kiểu trả về sai dù phần tử đó có `default`. Ví dụ `Integer count() default 3;` vẫn không hợp lệ.

Ví dụ đúng:

```java
@interface RetryOptions {
    int limit() default 3;
    String[] reasons() default {};
}
```

Cú pháp này mô tả metadata tĩnh. Bản thân `RetryOptions` không phải callback, service hay interface chức năng chứa logic xử lý.

## 9. Kiểm tra lỗi ở compile time và đọc ở runtime là hai bước khác nhau

Compiler kiểm tra **tập kiểu và biểu thức giá trị hợp lệ** khi bạn khai báo/gắn annotation. Muốn mã chạy đọc được annotation từ một phần tử qua Reflection, annotation còn cần chính sách lưu giữ phù hợp:

```java
@Retention(RetentionPolicy.RUNTIME)
@interface VisibleTag {
    String value();
}
```

Không khai báo `@Retention` thì mặc định retention là `CLASS`: annotation có thể còn trong class file nhưng **Reflection chuẩn không thấy nó**. Đặt `RUNTIME` giúp Reflection có thể truy vấn metadata đó.

Hai trách nhiệm độc lập:

1. **Kiểm tra kiểu compile-time:** `String`, `Class`, `enum`, annotation lồng và mảng một chiều có hợp lệ không; biểu thức có thỏa quy tắc giá trị không.
2. **Đọc dữ liệu runtime:** chương trình có Reflection/processor/framework được viết để đọc annotation đó không; retention có thích hợp không.

Annotation kiểu hợp lệ mà retention `SOURCE` có thể hữu ích cho công cụ phân tích source, dù không thể đọc từ class đã biên dịch qua Reflection. Annotation có retention `RUNTIME` vẫn không tự tạo hành vi nghiệp vụ.

Với ví dụ `AnnotationElementTypesDemo`, kết quả in ra bắt nguồn từ các lời gọi `profile.owner()`, `profile.priority()`, `profile.label().value()` sau khi lấy annotation. Chúng là **các accessor đọc metadata**, không phải lời gọi thực thi mã của annotation.

## 10. Lỗi hiểu sai thường gặp

**“Nếu Java method trả được một kiểu thì annotation element cũng trả được.”** Sai. `List<String>`, `Integer`, `Object` hoặc `Map` là kiểu Java bình thường, nhưng không thuộc nhóm được phép cho element.

**“Dùng wrapper như `Integer` tương đương `int`.”** Sai trong khai báo annotation element; phải dùng kiểu nguyên thủy được quy định.

**“`Class<?>` lưu được đối tượng của class.”** Sai. Nó lưu một **class literal**; muốn có instance và hành vi runtime phải có mã xử lý riêng.

**“Enum trong annotation truyền bằng tên chuỗi cũng được.”** Sai. Cần `Priority.HIGH`, không phải `"HIGH"` hoặc `Priority.valueOf("HIGH")`.

**“`static final` nào cũng là hằng annotation.”** Sai. Với giá trị nguyên thủy và chuỗi, initializer phải là compile-time constant expression theo luật Java.

**“Có thể dùng `new String[]{...}` vì đây là mảng String hợp lệ.”** Sai trong biểu thức giá trị annotation. Sử dụng `{...}` cho mảng, hoặc một phần tử đơn khi được phép rút gọn.

**“Có thể dùng `String[][]` miễn các phần tử cuối là String.”** Sai. Annotation element chỉ hỗ trợ mảng một chiều.

**“Có thể dùng `null` để biểu diễn tùy chọn không có.”** Sai. Giá trị phần tử annotation không có cách dùng `null`; hãy thiết kế default/sentinel thích hợp.

**“Đã đọc được annotation ở runtime thì chắc compiler không kiểm tra.”** Sai. Kiểm tra kiểu và biểu thức diễn ra khi biên dịch, còn Reflection là cách tiêu thụ metadata ở runtime.

## 11. Bài tập tự kiểm tra

### Bài 1 — Chọn kiểu hợp lệ

Đánh dấu những kiểu element hợp lệ:

```java
// Đọc từng dòng riêng lẻ như một khai báo element.
int retries();
Integer retryCount();
Class<? extends Runnable> handler();
String[] tags();
String[][] groups();
Priority priority();
Label label();
List<String> names();
char delimiter();
```

**Gợi ý:** hợp lệ là `int`, `Class<? extends Runnable>`, `String[]`, `Priority`, `Label` và `char`; các trường hợp `Integer`, `String[][]`, `List<String>` bị cấm.

### Bài 2 — Hằng và biểu thức tính toán

Đoạn nào hợp lệ?

```java
static final int A = 2 + 3;
static final int B = Integer.parseInt("5");

@interface Limit {
    int value();
}

// Coi A và B là các trường trong một lớp Constants:
// @Limit(Constants.A)
// @Limit(Constants.B)
```

**Gợi ý:** `A` là constant variable nên được phép; `B` được gán từ method call nên không phải constant expression.

### Bài 3 — Giá trị mảng

Với `@interface Tags { String[] value() default {}; }`, dự đoán nội dung mảng thu được của:

```java
@Tags
class NoTag {}

@Tags("java")
class OneTag {}

@Tags({"java", "core"})
class TwoTags {}
```

**Gợi ý:** lần lượt `[]`, `["java"]`, `["java", "core"]`. Đây là biểu diễn nội dung mảng, không phải cú pháp output bắt buộc.

### Bài 4 — Dùng annotation lồng

Vì sao `@Endpoint(label = @Label("public"))` hợp lệ khi `Endpoint.label()` trả về kiểu annotation `Label`? Vì sao `label = new Label()` không phải cách gán tương đương?

**Gợi ý:** phần tử hỗ trợ trực tiếp annotation expression; annotation type không được khởi tạo như object Java thông thường bằng `new`.

### Bài 5 — Thiết kế metadata có danh sách cặp key-value

Nếu `Map<String,String>` không được phép, hãy tự khai báo `@Entry(key, value)` và `@Entries(Entry[] value)` như ở mục 7. Thử thay `@Entries({@Entry(...), @Entry(...)})` bằng annotation một phần tử. Theo quy tắc mảng, bạn có thể viết `@Entries(@Entry(key = "k", value = "v"))`.

## 12. Ghi nhớ khi thiết kế annotation type

Khi muốn thêm một phần tử vào annotation, kiểm tra theo thứ tự:

1. **Kiểu trả về:** thuộc primitive, `String`, `Class`, `enum`, annotation hay mảng một chiều của các kiểu đó không?
2. **Biểu thức giá trị:** là hằng nguyên thủy/String, class literal, enum constant, annotation expression hoặc array initializer hợp lệ không?
3. **Giá trị mặc định:** nếu có, có đúng kiểu và không dùng `null` không?
4. **Độ rõ ràng của cấu trúc:** một `enum`, annotation lồng hoặc `T[]` có diễn đạt metadata tốt hơn việc nhồi nhiều giá trị vào một `String` không?
5. **Bên tiêu thụ:** ai đọc annotation, ở compile time hay runtime, và retention có phù hợp không?

Annotation giúp mô tả metadata rõ ràng khi kiểu và giá trị được Java compiler xác thực sớm. Chọn đúng các kiểu phần tử hợp lệ là nền tảng để xây dựng annotation dễ đọc, tránh lỗi biên dịch và làm cho dữ liệu mà công cụ/framework nhận được có cấu trúc nhất quán.