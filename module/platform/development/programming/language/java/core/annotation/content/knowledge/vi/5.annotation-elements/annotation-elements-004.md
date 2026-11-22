# Mảng một chiều và các kiểu phần tử không được hỗ trợ trong Java Annotation

## 1. Vì sao annotation element bị giới hạn kiểu?

Khi định nghĩa một annotation type bằng `@interface`, mỗi *element* khai báo kiểu dữ liệu mà người dùng có thể cung cấp cho annotation. Ví dụ:

```java
@interface Topics {
    String[] names();
}
```

`names()` là một **element trả về `String[]`**, không phải phương thức dùng để xử lý một mảng tùy ý. Nơi sử dụng annotation phải cung cấp một giá trị hợp lệ ngay trong mã nguồn:

```java
@Topics(names = {"java", "annotation"})
class Guide {}
```

Vì annotation là metadata được Java compiler ghi nhận theo các quy tắc riêng, element chỉ được có một số kiểu nhất định. Java cho phép **mảng một chiều** của các kiểu element hợp lệ nhưng **không** cho phép mảng nhiều chiều, collection, đối tượng tùy ý hay kiểu tổng quát chỉ vì chúng cũng là kiểu Java hợp lệ.

Mục tiêu của bài này là trả lời chính xác ba câu hỏi:

1. Kiểu nào được khai báo cho annotation element, đặc biệt khi thêm `[]`?
2. Viết giá trị, giá trị mặc định và đọc giá trị mảng như thế nào?
3. Vì sao `String[][]`, `List<String>`, `Object[]`, `Integer[]` cùng nhiều kiểu khác bị compiler từ chối?

## 2. Danh sách kiểu element Java cho phép

Một annotation element có thể có kiểu trả về thuộc các nhóm sau:

| Nhóm | Ví dụ element hợp lệ | Dạng mảng một chiều hợp lệ |
|---|---|---|
| Kiểu nguyên thủy | `int count();`, `boolean enabled();` | `int[] codes();`, `boolean[] flags();` |
| `String` | `String title();` | `String[] tags();` |
| `Class` và dạng có tham số kiểu phù hợp | `Class<?> type();` | `Class<?>[] types();` |
| Kiểu `enum` | `Level level();` | `Level[] levels();` |
| Kiểu annotation khác | `Option option();` | `Option[] options();` |

Với nhóm nguyên thủy, tất cả tám kiểu `boolean`, `byte`, `short`, `int`, `long`, `char`, `float` và `double` đều hợp lệ, cả dạng đơn và mảng một chiều.

```java
enum Level {
    LOW, MEDIUM, HIGH
}

@interface Option {
    String key();
    String value();
}

@interface Settings {
    int[] retryDelays();
    String[] aliases();
    boolean[] checks();
    Class<?>[] processors();
    Level[] levels();
    Option[] options();
}
```

Các khai báo trong `Settings` đều hợp lệ. `Class<?>[]` là **một mảng một chiều có phần tử kiểu `Class<?>`**, còn `Option[]` là mảng một chiều chứa giá trị annotation lồng nhau.

Dấu `[]` chỉ cho biết một chiều. Không có ngoại lệ cho mảng nhiều chiều: ngay cả `String[][]` và `int[][]` cũng không được phép làm kiểu trả về của annotation element.

**Chú ý:** Các ràng buộc này áp dụng cho *element* như `String[] tags();`. Một biến Java thông thường có thể dùng nhiều kiểu và cấu trúc dữ liệu khác; đừng nhầm quy tắc của annotation element với quy tắc của biến, field hoặc method Java nói chung.

## 3. Cách khai báo mảng một chiều

Cú pháp:

```java
@interface Marker {
    String[] labels();
    int[] statuses() default {200};
}
```

Trong đó:

- `String[] labels();` khai báo một element bắt buộc có giá trị là mảng chuỗi.
- `int[] statuses() default {200};` khai báo một element tùy chọn, mặc định là mảng gồm một số nguyên `200`.
- `default {}` biểu diễn **mảng rỗng** và cũng là một giá trị mặc định hợp lệ.
- Tên element đi kèm `()` rỗng vì annotation element không được khai báo tham số phương thức.

Ví dụ về cả mảng nguyên thủy và mảng đối tượng thuộc những nhóm được hỗ trợ:

```java
@interface BuildProfile {
    String[] modules() default {};
    int[] supportedVersions() default {17, 21};
    char[] markers() default {'A', 'B'};
    boolean[] featureFlags() default {true, false};
}
```

Mặc dù `String[]` và `Class<?>[]` có cú pháp mảng giống Java thông thường, cách **khai báo giá trị annotation** có những hạn chế riêng. Phần sau giải thích cụ thể.

## 4. Cách truyền một mảng khi sử dụng annotation

Với khai báo:

```java
@interface Roles {
    String[] names();
}
```

Có ba dạng sử dụng hợp lệ:

```java
@Roles(names = {"ADMIN", "EDITOR"}) // Hai phần tử
class AdminService {}

@Roles(names = {"USER"})            // Một phần tử
class UserService {}

@Roles(names = {})                  // Mảng rỗng
class PublicService {}
```

Ở vị trí giá trị của annotation, danh sách `{...}` đóng vai trò cú pháp *array initializer* riêng dành cho annotation, chứa các giá trị phù hợp kiểu element.

Nếu chỉ có **một** giá trị thuộc kiểu phần tử, Java cho phép bỏ cặp ngoặc nhọn:

```java
@Roles(names = "GUEST")
class GuestService {}
```

`@Roles(names = "GUEST")` tương đương về giá trị mảng với `@Roles(names = {"GUEST"})`. Cả hai đều cung cấp một mảng `String[]` gồm một phần tử; Java không thay đổi kiểu khai báo `names()` thành `String`.

Cú pháp mảng annotation cũng cho phép dấu phẩy cuối danh sách:

```java
@Roles(names = {"ADMIN", "EDITOR",})
class TrailingCommaExample {}
```

Dấu phẩy cuối là tùy chọn, thường hữu ích khi mỗi phần tử nằm trên dòng riêng.

### Không dùng `new` để khởi tạo mảng ở nơi sử dụng annotation

Đoạn sau **cố ý sai**:

```java
@Roles(names = new String[] {"ADMIN", "EDITOR"})
class InvalidConstruction {}
```

Khi truyền mảng vào annotation, hãy dùng `{"ADMIN", "EDITOR"}`. Annotation element value có cú pháp riêng và không chấp nhận biểu thức tạo mảng `new String[] {...}` ở vị trí ấy, dù biểu thức đó hợp lệ khi khởi tạo biến Java thông thường.

## 5. Mảng có element tên `value`: cú pháp rút gọn

Nếu annotation khai báo element tên chính xác là `value`, Java cho phép bỏ `value =` khi sử dụng:

```java
@interface Tags {
    String[] value();
}

@Tags({"core", "java"})
class CoreLesson {}

@Tags("java")
class SingleTagLesson {}

@Tags(value = {"annotation", "arrays"})
class ExplicitLesson {}

@Tags({})
class UntaggedLesson {}
```

Tất cả các cách trên đều hợp lệ, với một mảng gồm số phần tử tương ứng.

Hai kiểu rút gọn ở đây là **hai quy tắc độc lập**:

1. `@Tags(...)` bỏ tên element vì nó tên là `value`.
2. `@Tags("java")` bỏ `{...}` vì `value()` là mảng một chiều, trong khi được cung cấp đúng **một** phần tử kiểu `String`.

Với element mang tên khác `value`, không được bỏ tên:

```java
@interface Routes {
    String[] paths();
}

@Routes(paths = {"/users", "/orders"})
class ValidRoutes {}

// Sai: Routes không khai báo element value()
@Routes({"/users", "/orders"})
class InvalidRoutes {}
```

Nếu có nhiều element cần truyền, dùng cú pháp `name = value` rõ ràng:

```java
@interface Permissions {
    String[] value();
    boolean audited() default false;
}

@Permissions(value = {"READ", "WRITE"}, audited = true)
class ReportController {}
```

Không trộn dạng giá trị không tên với các cặp có tên, chẳng hạn `@Permissions({"READ"}, audited = true)`; đây không phải cách viết hợp lệ.

## 6. Giá trị mặc định của element kiểu mảng

Dùng `default` trong **định nghĩa annotation type** để cung cấp giá trị khi nơi sử dụng không truyền element đó:

```java
@interface SupportedFormats {
    String[] value() default {"json"};
    int[] versions() default {1, 2};
    String[] optionalTags() default {};
}

@SupportedFormats
class DefaultFormats {}

@SupportedFormats(value = {"xml", "csv"}, versions = {2, 3})
class CustomFormats {}
```

`@SupportedFormats` hợp lệ do cả ba element đều có `default`. Giá trị mặc định không nhất thiết chứa phần tử: `default {}` là mảng rỗng hợp lệ.

Ngược lại, nếu element mảng không có `default`, nó vẫn là **bắt buộc**, dù người dùng có thể cung cấp mảng rỗng:

```java
@interface RequiredTags {
    String[] names();
}

@RequiredTags(names = {})
class ValidEmptyTags {}

// Sai: bỏ thiếu names(), vì không có default
@RequiredTags
class MissingTags {}
```

Sự khác biệt quan trọng:

- `@RequiredTags(names = {})`: element đã được cung cấp bằng mảng rỗng.
- `@RequiredTags`: element không được cung cấp và không có mặc định, nên là lỗi biên dịch.

`default null` không hợp lệ cho element annotation. Nếu muốn mặc định “không có phần tử nào”, sử dụng `default {}`; nếu muốn phân biệt “không khai báo” và “khai báo mảng rỗng”, cần thiết kế metadata/giá trị phù hợp thay vì dựa vào `null`.

## 7. Ví dụ mảng `enum`, `Class` và annotation lồng nhau

Giả sử muốn khai báo danh sách môi trường triển khai, kiểu handler và tùy chọn cấu hình:

```java
enum Environment {
    DEV, TEST, PROD
}

@interface Property {
    String key();
    String value();
}

@interface Deployment {
    Environment[] environments() default {Environment.DEV};
    Class<?>[] handlers() default {};
    Property[] properties() default {};
}
```

Sử dụng:

```java
@Deployment(
    environments = {Environment.TEST, Environment.PROD},
    handlers = {String.class, Integer.class},
    properties = {
        @Property(key = "region", value = "ap-southeast"),
        @Property(key = "retry", value = "3")
    }
)
class DataProcessor {}
```

Mỗi nhóm có quy tắc rõ ràng:

- `Environment[]` nhận các **enum constant** như `Environment.PROD`, không nhận chuỗi `"PROD"`.
- `Class<?>[]` nhận các **class literal** như `String.class` và `Integer.class`, không nhận `new String(...)`.
- `Property[]` nhận các **annotation literal** như `@Property(...)`; không khởi tạo bằng `new Property()`.
- Mọi giá trị vẫn nằm trong **mảng một chiều** của đúng kiểu element.

Với một phần tử, có thể dùng dạng ngắn như `environments = Environment.DEV`, `handlers = String.class` hoặc `properties = @Property(key = "x", value = "y")`. Tuy vậy, dạng `{...}` thường rõ ràng hơn khi người đọc cần nhận biết ngay element là một mảng.

## 8. Các kiểu element **không được hỗ trợ**

### 8.1. Mảng nhiều chiều

```java
@interface InvalidMatrix {
    String[][] labels();  // Sai
    int[][] coordinates(); // Sai
}
```

Java cho phép những kiểu này cho biến hay field thông thường, nhưng không cho phép làm kiểu trả về của annotation element.

Nếu metadata cần biểu diễn dữ liệu theo nhóm, có thể dùng **mảng một chiều của nested annotation**:

```java
@interface Row {
    int[] values();
}

@interface GridInfo {
    Row[] rows();
}

@GridInfo(rows = {
    @Row(values = {1, 2}),
    @Row(values = {3, 4})
})
class MatrixLikeConfig {}
```

`Row[]` là một mảng một chiều của annotation type, còn mỗi `Row` có element kiểu `int[]`. Cấu trúc này mô tả các hàng có độ dài tùy ý mà vẫn tuân thủ quy tắc kiểu annotation. Nó là một **mô hình metadata có cấu trúc**, không phải một element `int[][]`.

### 8.2. `Object` và các class tùy ý

```java
@interface InvalidObjects {
    Object value();        // Sai
    Object[] values();     // Sai
    Integer[] numbers();   // Sai
    StringBuilder text();  // Sai
}
```

Không phải mọi object trong Java đều là một annotation element type hợp lệ. `Integer` là wrapper class, khác với kiểu nguyên thủy `int`; `Integer[]` không hợp lệ dù `int[]` hợp lệ. Ngoại lệ tiêu biểu trong nhóm tham chiếu được hỗ trợ là `String` và `Class` theo quy tắc ngôn ngữ.

Các sửa đổi tương ứng, khi phù hợp với ý nghĩa dữ liệu:

- `Integer[] numbers()` → `int[] numbers()`.
- `StringBuilder text()` → `String text()`.
- `Object value()` → một kiểu cụ thể được hỗ trợ, chẳng hạn `String`, enum, `Class<?>` hoặc nested annotation. Việc chọn kiểu phụ thuộc ý nghĩa metadata, không có phép đổi tự động tổng quát.

### 8.3. Collection, Map, Optional và kiểu generic tùy ý

```java
import java.util.List;
import java.util.Map;
import java.util.Optional;

@interface InvalidContainers {
    List<String> tags();        // Sai
    Map<String, String> props(); // Sai
    Optional<String> label();    // Sai
    List<String>[] groups();    // Sai
}
```

`List<String>`, `Map<...>` và `Optional<String>` đều là Java reference types hợp lệ ở nhiều ngữ cảnh, nhưng không thuộc tập kiểu trả về annotation element. Thêm `[]` vào `List<String>` cũng không làm nó hợp lệ.

Nếu cần metadata tương tự một danh sách, ưu tiên mảng hợp lệ như `String[]` hoặc mảng enum. Nếu cần các cặp khóa/giá trị, nested annotation có thể diễn đạt chúng:

```java
@interface Pair {
    String key();
    String value();
}

@interface Pairs {
    Pair[] value() default {};
}

@Pairs({
    @Pair(key = "env", value = "test"),
    @Pair(key = "region", value = "asia")
})
class PairConfig {}
```

Đừng dùng annotation làm nơi lưu cấu trúc object động phức tạp; metadata thường nên nhỏ, tĩnh và rõ kiểu.

### 8.4. Kiểu `void`, mảng đa chiều của kiểu hợp lệ và type variable

```java
@interface OtherInvalid {
    void execute();            // Sai: void
    Class<?>[][] classes();    // Sai: mảng hai chiều
}
```

`Class<?>[]` hợp lệ; `Class<?>[][]` không hợp lệ vì có hai chiều.

Annotation type cũng không được khai báo tham số kiểu như một generic interface:

```java
// Sai: annotation type không thể khai báo <T>
@interface GenericMarker<T> {
    T value();
}
```

Thay vì dùng type variable `T` làm element, hãy chọn một kiểu được hỗ trợ, chẳng hạn `Class<?> value();` nếu cần mô tả một class.

## 9. Vì sao `new String[]` và biến mảng không thay thế được annotation initializer?

Giới hạn **kiểu element** và giới hạn **biểu thức giá trị element** là hai vấn đề khác nhau:

- `String[] names();` là *kiểu element hợp lệ*.
- `@Names(value = {"a", "b"})` là *cách truyền giá trị hợp lệ*.
- `@Names(value = new String[]{"a", "b"})` là *biểu thức giá trị không hợp lệ trong annotation*.
- `@Names(value = SOME_ARRAY)` không hợp lệ nếu `SOME_ARRAY` là một biến mảng thông thường, kể cả khi nó khai báo `static final`.

Ví dụ:

```java
@interface Names {
    String[] value();
}

class Constants {
    static final String[] SAVED = {"a", "b"};
}

@Names({"a", "b"})
class ValidNameList {}

// Sai: new-array expression không hợp lệ làm element value
@Names(new String[] {"a", "b"})
class InvalidNewArray {}

// Sai: SAVED là mảng trong biến, không phải annotation array initializer
@Names(Constants.SAVED)
class InvalidVariable {}
```

Điểm dễ nhầm là một biến `static final` không đồng nghĩa nó là *compile-time constant variable*. Trong Java, khái niệm constant variable chỉ áp dụng cho biến `final` có kiểu nguyên thủy hoặc `String` được khởi tạo bằng constant expression. Mảng là đối tượng, vì vậy `static final String[]` không trở thành một giá trị hằng annotation hợp lệ.

Ngược lại, từng giá trị chuỗi trong array initializer có thể là hằng `String`:

```java
@interface Labels {
    String[] value();
}

class LabelConstants {
    static final String MAIN = "core";
    static final String EXTRA = "annotation";
}

@Labels({LabelConstants.MAIN, LabelConstants.EXTRA})
class ValidConstants {}
```

Ở đây **từng element** là chuỗi hằng hợp lệ; bản thân danh sách mảng vẫn được cung cấp bằng `{...}`.

## 10. Ví dụ Java 17+ hoàn chỉnh: khai báo, sử dụng và đọc mảng

Tạo file **`AnnotationArrayDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

enum Level {
    LOW, HIGH
}

@Retention(RetentionPolicy.RUNTIME)
@interface Option {
    String key();
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Catalog {
    String[] names();
    int[] codes() default {200};
    Level[] levels() default {};
    Class<?>[] handlers() default {};
    Option[] options() default {};
}

@Catalog(
    names = {"core", "annotation"},
    codes = {200, 201},
    levels = {Level.LOW, Level.HIGH},
    handlers = {String.class, Integer.class},
    options = {
        @Option(key = "mode", value = "study")
    }
)
class CatalogService {}

public class AnnotationArrayDemo {
    public static void main(String[] args) {
        Catalog catalog =
                CatalogService.class.getAnnotation(Catalog.class);

        System.out.println("names=" + Arrays.toString(catalog.names()));
        System.out.println("codes=" + Arrays.toString(catalog.codes()));
        System.out.println("levels=" + Arrays.toString(catalog.levels()));
        System.out.println("handlers=" + Arrays.toString(catalog.handlers()));
        System.out.println("options=" + catalog.options().length);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên trong thư mục chứa file:

```bash
javac AnnotationArrayDemo.java
java AnnotationArrayDemo
```

Kết quả chuẩn:

```text
names=[core, annotation]
codes=[200, 201]
levels=[LOW, HIGH]
handlers=[class java.lang.String, class java.lang.Integer]
options=1
```

Giải thích:

1. `Catalog` khai báo năm element; tất cả đều là mảng một chiều của kiểu được hỗ trợ.
2. `names()` không có `default` nên giá trị này là bắt buộc. Các element còn lại có mặc định và có thể bỏ qua ở nơi sử dụng.
3. `@Catalog(...)` truyền array initializer cho từng element: chuỗi, số, enum, class literal và annotation literal.
4. `@Retention(RetentionPolicy.RUNTIME)` trên `Catalog` cho phép `getAnnotation(Catalog.class)` truy cập metadata khi chạy.
5. `Arrays.toString(...)` biến các mảng đọc được thành chuỗi để quan sát; `catalog.options().length` xác nhận mảng nested annotation có một phần tử.

Nếu muốn một ví dụ dùng giá trị đơn thay cho mảng một phần tử, viết `@Catalog(names = "single")` trên một class khác. Compiler vẫn xem `names()` là `String[]` và khi đọc sẽ nhận được mảng có độ dài `1`.

## 11. Cách nhận diện và sửa lỗi compiler

Khi `javac` không chấp nhận khai báo hoặc giá trị annotation, hãy phân loại lỗi trước khi sửa:

| Đoạn mã hoặc tình huống | Nguyên nhân | Hướng sửa |
|---|---|---|
| `String[][] values();` | Mảng nhiều chiều không được hỗ trợ | Mảng một chiều của kiểu hợp lệ, hoặc nested annotation |
| `List<String> tags();` | Collection không phải annotation element type | `String[] tags();` nếu phù hợp |
| `Integer[] numbers();` | Wrapper class không nằm trong tập kiểu hợp lệ | `int[] numbers();` |
| `Object[] objects();` | Kiểu phần tử Object không hợp lệ | Chọn kiểu được hỗ trợ |
| `String[] tags() default null;` | `null` không hợp lệ | `default {}` hoặc một mảng giá trị hợp lệ |
| `@Tags(value = new String[]{"a"})` | Cú pháp tạo mảng bằng `new` không hợp lệ | `@Tags({"a"})` |
| `@Tags(value = SOME_STRING_ARRAY)` | Không dùng biến mảng thường làm array element value | Khai báo trực tiếp `{...}` |
| `@Tags` khi `value()` không có `default` | Thiếu element bắt buộc | `@Tags({})` hoặc truyền giá trị phù hợp |
| `@LevelSet(levels = {"LOW"})` | Sai kiểu: yêu cầu enum, nhận chuỗi | `levels = {Level.LOW}` |
| `@Types(values = {new Object()})` | Annotation không nhận object mới tạo tùy ý | Dùng class literal hoặc kiểu metadata khác |

Tên và nội dung chi tiết của thông báo `javac` phụ thuộc đoạn mã và phiên bản JDK. Khi gặp `invalid type for annotation type element`, hãy xem lại **kiểu trả về trong `@interface`**. Khi gặp thông báo lỗi tại phần sử dụng annotation, hãy xem **kiểu element, array initializer, `default` và tính hằng của từng giá trị**.

Đặc biệt, **mảng rỗng khác với thiếu element**. Nếu một element bắt buộc có kiểu mảng, cung cấp `{}` là hợp lệ, nhưng hoàn toàn bỏ element vẫn là lỗi.

## 12. Bài tập tự kiểm tra

Xét ba định nghĩa sau:

```java
enum Color {
    RED, BLUE
}

@interface ColorOptions {
    Color[] colors() default {};
}

@interface MatrixValues {
    int[][] data();
}

@interface Strings {
    String[] value();
}
```

Hãy đánh giá:

1. `@ColorOptions(colors = {Color.RED, Color.BLUE})` có hợp lệ không?
2. `@ColorOptions(colors = Color.RED)` có hợp lệ không?
3. `@Strings({"a", "b"})` có hợp lệ không?
4. `@Strings("a")` có hợp lệ không?
5. `@Strings({})` có hợp lệ không?
6. `@Strings` có hợp lệ không?
7. `int[][] data()` trong `MatrixValues` có hợp lệ không?
8. Nếu đổi `MatrixValues` thành `@interface MatrixValues { int[] data(); }` thì `@MatrixValues(data = {1, 2})` có hợp lệ không?

Đáp án và lý do:

1. **Có.** Đây là mảng một chiều gồm hai enum constants hợp lệ.
2. **Có.** Một element mảng có thể nhận một giá trị đơn cùng kiểu phần tử trong ngữ cảnh annotation.
3. **Có.** `value()` cho phép bỏ tên, mảng chứa hai chuỗi hợp lệ.
4. **Có.** Đồng thời áp dụng viết tắt tên `value` và viết tắt mảng một phần tử.
5. **Có.** Đã cung cấp một mảng rỗng; `Strings.value()` là element bắt buộc nhưng không bắt buộc có phần tử trong mảng.
6. **Không.** `Strings.value()` không có `default`, vì vậy không thể bỏ qua element.
7. **Không.** Mảng hai chiều không phải kiểu annotation element hợp lệ; bản thân định nghĩa `MatrixValues` đã không biên dịch được.
8. **Có.** `int[]` là kiểu hợp lệ và `{1, 2}` là array initializer hợp lệ.

Nếu muốn biên dịch thử, hãy đặt những định nghĩa hợp lệ và ví dụ đúng vào một file riêng; bỏ hoặc sửa `MatrixValues` trước, vì lỗi ngay trong định nghĩa annotation có thể làm các thông báo khác khó đọc.

## 13. Checklist ghi nhớ

- Annotation element chỉ được trả về kiểu nguyên thủy, `String`, `Class` thích hợp, enum, annotation hoặc **mảng một chiều** của các kiểu ấy.
- `T[]` hợp lệ nếu `T` là kiểu element được phép; `T[][]` không hợp lệ, kể cả với `String` hay `int`.
- `List`, `Map`, `Optional`, `Object`, wrapper như `Integer` và các lớp tùy ý không phải kiểu element được hỗ trợ.
- Dùng `{a, b}`, `{a}` hoặc `{}` để truyền mảng; khi có một giá trị đơn cùng kiểu phần tử, Java cho phép bỏ ngoặc nhọn.
- Dùng `@Annotation(...)` không ghi tên element chỉ khi element tên là `value`.
- Giá trị mặc định cho mảng thường viết `default {...}`; `default {}` là mảng rỗng hợp lệ; không dùng `default null`.
- Mảng là element bắt buộc nếu không có `default`, dù giá trị hợp lệ của nó có thể là `{}`.
- Không dùng `new T[]{...}`, một biến mảng `static final` hoặc lời gọi runtime để tạo giá trị cho annotation element.
- Với mảng enum/class/nested annotation, từng phần tử phải là enum constant/class literal/annotation literal tương ứng.
- Nếu cần mô tả cấu trúc nhiều lớp, cân nhắc một mảng một chiều của nested annotations thay cho mảng nhiều chiều hoặc collection.

Hiểu đúng khác biệt giữa **kiểu dữ liệu Java thông thường** và **kiểu element hợp lệ của annotation** giúp tránh lỗi khi định nghĩa `@interface` và khi gắn giá trị metadata tại nơi sử dụng.