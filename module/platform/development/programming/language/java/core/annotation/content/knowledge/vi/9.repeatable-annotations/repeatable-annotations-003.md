# Khai báo value() trả về mảng của annotation được lặp

Khi muốn gắn **cùng một loại annotation nhiều lần lên cùng một khai báo**, Java dùng cơ chế **repeatable annotation**. Muốn khai báo một annotation lặp được, ngoài annotation chính, bạn cần định nghĩa **container annotation**: một annotation riêng có phần tử **`value()` trả về mảng một chiều của chính annotation được lặp**.

Ví dụ mục tiêu:

```java
@Role("ADMIN")
@Role("AUDITOR")
class ReportService {
}
```

Để cú pháp hai dòng `@Role` cùng tồn tại hợp lệ, khai báo `Role` phải có `@Repeatable(Roles.class)` và `Roles` phải khai báo **`Role[] value();`**. Khi cần đóng gói những lần xuất hiện lặp, compiler sử dụng container `@Roles` để lưu danh sách các annotation `@Role`. Đây là quan hệ giữa hai *annotation type* do người phát triển khai báo, được compiler kiểm tra ngay khi biên dịch.

Mục tiêu của bài học là hiểu đúng chữ ký `value()`, ý nghĩa mảng annotation, quy tắc đặt `@Repeatable`, cách viết các trường hợp đúng/sai và cách đọc kết quả, kể cả sự khác nhau giữa **annotation xuất hiện trực tiếp** và **annotation nằm trong container**.

## 1. Vì sao container cần value() trả về mảng?

Xét annotation đơn:

```java
@interface Role {
    String value();
}
```

`String value()` trong `Role` mô tả **dữ liệu của một `@Role`**. Một lần dùng `@Role("ADMIN")` chứa chuỗi `"ADMIN"`. Phần tử này **không liên quan đến việc cho phép lặp**.

Muốn tập hợp nhiều `@Role` tại cùng một vị trí, ta cần một **annotation type khác**:

```java
@interface Roles {
    Role[] value();
}
```

`Role[] value()` có nghĩa: một `@Roles` chứa **một mảng phần tử kiểu annotation `Role`**, ví dụ:

```java
@Roles({
    @Role("ADMIN"),
    @Role("AUDITOR")
})
class ReportService {
}
```

Đây là cách viết container tường minh. Muốn viết hai lần `@Role` thay cho `@Roles({...})`, phải liên kết hai khai báo bằng `@Repeatable`:

```java
import java.lang.annotation.Repeatable;

@Repeatable(Roles.class)
@interface Role {
    String value();
}

@interface Roles {
    Role[] value();
}
```

Sau đó, cả hai cách viết đều biểu diễn danh sách các `Role`; cơ chế Reflection có API để đọc thống nhất những annotation trực tiếp và những annotation nằm trong container.

**Hai chữ ký khác nhau, hai chức năng khác nhau:**

| Khai báo | `value()` trả về | Ý nghĩa |
| --- | --- | --- |
| `@interface Role { String value(); }` | `String` | Nội dung của **một `@Role`** |
| `@interface Roles { Role[] value(); }` | `Role[]` | Danh sách **các annotation `@Role`** được chứa bên trong container |

Không bắt buộc annotation chính phải đặt tên phần tử là `value()`; nó có thể có `String name();` hoặc nhiều phần tử khác. Nhưng **container của repeatable annotation phải có phần tử tên chính xác là `value` và kiểu trả về là mảng một chiều của annotation chính**.

## 2. Cặp khai báo đầy đủ để chạy với Java 17+

Ví dụ chuẩn cần thống nhất kiểu annotation, retention và target:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Roles.class)
@interface Role {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Roles {
    Role[] value();
}
```

Giải thích từng phần:

1. `@interface Role` tạo loại annotation mà người dùng muốn đặt nhiều lần.
2. `@Repeatable(Roles.class)` đặt **trên loại annotation được lặp**, nói với compiler rằng **`Roles` là container của `Role`**.
3. `@interface Roles` khai báo loại container. Tên `Roles` là quy ước dễ đọc, **không phải tên bắt buộc**; `RoleContainer` hoặc tên khác cũng hợp lệ nếu tham chiếu đúng trong `@Repeatable`.
4. `Role[] value();` là điểm bắt buộc. Không được đổi thành `String[] value();`, `Object[] value();`, `Role value();` hoặc `Role[][] value();`.
5. Cặp `@Retention(RUNTIME)` khiến các lần dùng này có thể được Reflection đọc khi chương trình chạy. **Khả năng lặp không yêu cầu bắt buộc phải có retention `RUNTIME`**; chọn retention theo nhu cầu sử dụng.
6. Cả hai dùng `@Target(TYPE)` để các annotation được gắn ở khai báo kiểu tương ứng.

Không cần viết một phương thức Java nào để “thêm `Role` vào mảng”. Khi biên dịch những lần dùng lặp hợp lệ, compiler xử lý cách đóng gói annotation theo quy tắc Java.

**Điểm đặc biệt:** `@Repeatable` có đối số `Roles.class`, tức một *class literal* trỏ tới annotation container. Đây không phải đối tượng container, không tạo instance bằng `new Roles()`, cũng không phải tên string `"Roles"`.

## 3. Cách sử dụng: viết lặp, viết container, và viết một lần

Ba trường hợp thường gặp:

### 3.1. Lặp annotation chính

```java
@Role("ADMIN")
@Role("AUDITOR")
class ReportService {
}
```

Compiler chấp nhận việc đặt hai `@Role` ở cùng một khai báo vì `Role` được đánh dấu `@Repeatable(Roles.class)` và container `Roles` đáp ứng các điều kiện hợp lệ.

### 3.2. Viết trực tiếp annotation container

```java
@Roles({
    @Role("ADMIN"),
    @Role("AUDITOR")
})
class ReportService {
}
```

Cách này tường minh về container, cung cấp một mảng các annotation `Role`. Java cho phép mảng annotation một chiều và các thành phần `@Role(...)` là những giá trị annotation hợp lệ.

`@Roles({@Role("ADMIN"), @Role("AUDITOR")})` **không phải một mảng `String[]`**. Nó là **mảng `Role[]`**; mỗi phần tử `@Role` lại có `String value()` bên trong.

### 3.3. Một lần dùng annotation chính

```java
@Role("ADMIN")
class ReportService {
}
```

Một lần `@Role` là hợp lệ; compiler **không bắt buộc phải đóng gói nó vào container**. Sự khác biệt này quan trọng nếu bạn dùng API Reflection chỉ đọc annotation khai báo trực tiếp mà không mở container.

### 3.4. Container có thể nhận mảng rỗng

```java
@Roles({})
class NoRoleService {
}
```

Khai báo container tường minh với mảng rỗng có thể hợp lệ theo chữ ký `Role[]`. Tuy nhiên **mảng rỗng không có nghĩa tồn tại một annotation `Role`**; API trả về các `Role` theo kiểu bằng `getAnnotationsByType(Role.class)` sẽ cho mảng rỗng. Thiết kế có cho phép cấu hình rỗng về mặt nghiệp vụ hay không là trách nhiệm của công cụ đọc annotation.

## 4. Ví dụ độc lập: compile, chạy và đọc kết quả bằng Reflection

Tạo file **`RepeatableContainerDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.stream.Collectors;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Topics.class)
@interface Topic {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Topics {
    Topic[] value();
}

@Topic("java")
@Topic("annotation")
class Lesson {
}

@Topic("single")
class Single {
}

@Topics({@Topic("a"), @Topic("b")})
class Explicit {
}

public class RepeatableContainerDemo {
    private static String joinedTopics(Class<?> type) {
        return Arrays.stream(type.getAnnotationsByType(Topic.class))
                .map(Topic::value)
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args) {
        System.out.println(joinedTopics(Lesson.class));

        // Không có @Topic trực tiếp trong biểu diễn lặp thông thường.
        System.out.println(Lesson.class.getDeclaredAnnotation(Topic.class));

        Topics container = Lesson.class.getDeclaredAnnotation(Topics.class);
        System.out.println(container.value().length);

        System.out.println(joinedTopics(Single.class));
        System.out.println(Single.class.getDeclaredAnnotation(Topics.class));
        System.out.println(joinedTopics(Explicit.class));
    }
}
```

Dùng JDK 17+ trong thư mục chứa file:

```bash
javac --release 17 RepeatableContainerDemo.java
java RepeatableContainerDemo
```

Stdout chính xác:

```text
java, annotation
null
2
single
null
a, b
```

Đọc kết quả theo thứ tự:

- `getAnnotationsByType(Topic.class)` trên `Lesson` trả **hai `Topic`** theo thứ tự khai báo; `joinedTopics` lấy các chuỗi `value()` rồi nối bằng dấu phẩy.
- `getDeclaredAnnotation(Topic.class)` trên `Lesson` trả `null` trong ví dụ này vì các lần `@Topic` lặp được biểu diễn thông qua **`@Topics`**, thay vì một lần `@Topic` khai báo trực tiếp.
- `getDeclaredAnnotation(Topics.class)` trả container và `container.value().length` bằng `2`.
- `Single` chỉ có một `@Topic` trực tiếp, nên `getAnnotationsByType` đọc được `"single"`, nhưng `getDeclaredAnnotation(Topics.class)` trả `null`.
- `Explicit` dùng container tường minh; `getAnnotationsByType(Topic.class)` vẫn có thể **mở container** và trả `"a"`, `"b"`.

Đây là bài kiểm tra **đúng cơ chế Java**, không dựa vào một framework cụ thể. `@Retention(RUNTIME)` làm metadata có thể truy vấn khi chạy; lời gọi Reflection trong `main` là nơi mã chủ động đọc annotation.

## 5. Compiler làm gì với những lần sử dụng lặp?

Khi gặp:

```java
@Topic("java")
@Topic("annotation")
class Lesson {
}
```

Compiler xử lý về mặt ngữ nghĩa tương đương với việc chứa hai annotation `Topic` trong một annotation container `Topics`, phù hợp với khai báo `Topic[] value()`. Vì cùng một loại `Topic` xuất hiện nhiều lần ở một vị trí, container cho phép biểu diễn danh sách.

Một cách hình dung:

```text
Source code:
  @Topic("java")
  @Topic("annotation")
  class Lesson {}

                   compiler
                      |
                      v

Container theo ngữ nghĩa:
  @Topics(value = {
      @Topic("java"),
      @Topic("annotation")
  })

                      |
                      v

Reflection:
  getDeclaredAnnotation(Topics.class) -> Topics chứa Topic[2]
  getAnnotationsByType(Topic.class)  -> Topic[2]
```

Java không tự sinh một **định nghĩa annotation type `Topics`**. Bạn phải khai báo container hợp lệ trước; compiler chỉ xử lý cách các lần sử dụng lặp được biểu diễn. Các cú pháp trong sơ đồ là **mô hình giải thích**; không phải yêu cầu mã Java sẽ được viết lại thành một file source giống hệt.

Khi retention là `RUNTIME`, một công cụ có thể đọc container theo kiểu tường minh:

```java
Topics topics = Lesson.class.getDeclaredAnnotation(Topics.class);
if (topics != null) {
    for (Topic topic : topics.value()) {
        System.out.println(topic.value());
    }
}
```

Đoạn này dựa trên `Topic`, `Topics` và `Lesson` ở ví dụ đầy đủ. Kết quả in hai dòng `java` rồi `annotation`. Tuy nhiên nếu chỉ dùng một `@Topic` trực tiếp, `topics` có thể là `null`. Vì vậy nếu bạn muốn đọc **mọi `Topic`** bất kể được khai báo một lần, lặp nhiều lần hay đặt trong container tường minh, API thích hợp thường là `getAnnotationsByType(Topic.class)`.

## 6. Chữ ký value() của container phải đúng tuyệt đối

Với annotation lặp `@Topic`, container `@Topics` phải khai báo:

```java
@interface Topics {
    Topic[] value();
}
```

Ba chi tiết đều bắt buộc:

1. **Tên phương thức `value`**: không phải `items`, `topics`, `getValue`, `entries`.
2. **Không có tham số**: cú pháp là `value()`, không phải `value(int index)`.
3. **Kiểu trả về chính xác là `Topic[]`**: một mảng một chiều gồm các annotation cùng **annotation type được gắn `@Repeatable`**.

Chú ý: kiểu phần tử **`Topic`** tự nó là một annotation type hợp lệ. Do đó `Topic[]` thuộc nhóm **mảng một chiều của annotation type**, vốn được Java cho phép làm kiểu phần tử annotation.

### 6.1. Những container cố ý sai

Mỗi đoạn sau là **minh họa lỗi độc lập**. Không ghép các khai báo sai này vào chương trình chạy ở mục 4.

**Sai vì mảng chứa String, không phải annotation được lặp:**

```java
@Repeatable(WrongTags.class)
@interface Tag {
    String value();
}

@interface WrongTags {
    String[] value(); // Sai: phải là Tag[].
}
```

Dù `Tag.value()` trả `String`, **`WrongTags.value()` vẫn phải trả `Tag[]`**. Kiểu nội dung bên trong một `@Tag` và kiểu danh sách các `@Tag` là hai cấp dữ liệu khác nhau.

**Sai vì container dùng nhầm tên element:**

```java
@Repeatable(WrongTags.class)
@interface Tag {
}

@interface WrongTags {
    Tag[] items(); // Sai: không có phần tử tên value().
}
```

`@Repeatable` không có tùy chọn đổi tên phần tử chứa. Compiler cần đúng `value()`.

**Sai vì chỉ chứa một annotation:**

```java
@Repeatable(WrongTags.class)
@interface Tag {
}

@interface WrongTags {
    Tag value(); // Sai: phải là Tag[].
}
```

Container phải chứa khả năng biểu diễn **nhiều** annotation, nên một `Tag` đơn lẻ không đáp ứng hợp đồng.

**Sai vì mảng hai chiều:**

```java
@Repeatable(WrongTags.class)
@interface Tag {
}

@interface WrongTags {
    Tag[][] value(); // Sai: mảng nhiều chiều không là kiểu element hợp lệ.
}
```

Java cho phép mảng nhiều chiều trong nhiều ngữ cảnh khác, nhưng kiểu trả về của annotation element chỉ cho phép **mảng một chiều**.

### 6.2. Container có được khai báo thêm phần tử khác không?

Có, **nếu các phần tử khác có giá trị mặc định**. Ví dụ:

```java
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@interface Labels {
    Label[] value();
    String source() default "manual";
}
```

`source()` là phần tử bổ sung, không phải danh sách annotation lặp, và được cung cấp default. Compiler có thể tạo container cho các lần `@Label` lặp mà không cần nơi sử dụng chỉ định thêm `source`.

Ngược lại, khai báo sau **không phù hợp để làm container cho repeated `Label`**:

```java
@interface Labels {
    Label[] value();
    String source(); // Thiếu default.
}
```

Khi compiler cần tạo container ẩn từ những `@Label` lặp, không có giá trị bắt buộc `source` để cung cấp. Vì vậy mọi phần tử khác `value()` trong container phải có default.

Nên giữ container tối giản với duy nhất `value()` nếu bạn không có nhu cầu metadata rõ ràng khác.

## 7. Những ràng buộc phải thống nhất ngoài value()

`Topic[] value()` **cần thiết nhưng chưa đủ**. Java còn có những điều kiện áp dụng cho loại annotation lặp và container của nó.

### 7.1. @Retention của container phải đủ dài

Nếu repeated annotation có:

```java
@Retention(RetentionPolicy.RUNTIME)
@Repeatable(Tags.class)
@interface Tag {
}
```

thì container `Tags` **không được** có retention `SOURCE` hoặc `CLASS`; dùng:

```java
@Retention(RetentionPolicy.RUNTIME)
@interface Tags {
    Tag[] value();
}
```

Lý do: muốn truy vấn các `Tag` lặp tại runtime thì metadata của container cũng phải tồn tại và được nhìn thấy.

Nguyên tắc retention:

| Repeated annotation | Retention container hợp lệ |
| --- | --- |
| `SOURCE` | `SOURCE`, `CLASS` hoặc `RUNTIME` |
| `CLASS` | `CLASS` hoặc `RUNTIME` |
| `RUNTIME` | Chỉ `RUNTIME` |

Bảng diễn đạt quy tắc retention **giữa hai annotation type**. Nếu không gắn `@Retention`, loại annotation mặc định có retention `CLASS`. Đặt `@Repeatable` không tự đổi retention sang `RUNTIME`.

### 7.2. @Target phải tương thích

Nếu repeated annotation được phép gắn trên cả kiểu và phương thức:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@Repeatable(Tags.class)
@interface Tag {
}
```

thì container cũng phải **được phép ở các vị trí thích hợp để chứa những lần lặp đó**. Ví dụ cấu hình đồng nhất:

```java
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Tags {
    Tag[] value();
}
```

Container chỉ cho phép `TYPE` trong khi `Tag` cho phép `METHOD` sẽ không đáp ứng quy tắc về vị trí chứa các `@Tag` lặp trên method. Thông thường cách dễ bảo trì nhất là công bố `@Target` tương ứng trên cả hai, rồi để compiler kiểm tra hợp lệ.

Một số tình huống `TYPE_USE`, `TYPE_PARAMETER`, `ANNOTATION_TYPE` và vị trí đặc thù có thêm quy tắc tương thích target trong Java Language Specification. Khi thiết kế annotation dùng cho nhiều loại vị trí, hãy kiểm tra cặp `@Target` cụ thể bằng compiler thay vì mặc định mọi tập target là tương đương.

### 7.3. @Documented và @Inherited

Nếu annotation được lặp có `@Documented`, container của nó cũng cần `@Documented`. Nếu annotation được lặp có `@Inherited`, container cũng cần `@Inherited` để đáp ứng quy tắc hợp lệ.

Ví dụ:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.Inherited;
import java.lang.annotation.Repeatable;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;

@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Labels.class)
@interface Label {
    String value();
}

@Documented
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Labels {
    Label[] value();
}
```

Đoạn trên là **một ví dụ khai báo riêng**, không trộn với các kiểu `Label` khác ở bài. `@Inherited` có các quy tắc riêng khi truy vấn class theo hệ kế thừa, không có nghĩa annotation trên interface hoặc phương thức cũng tự được kế thừa. Chỉ cần nhớ tại đây rằng metadata bổ sung ở annotation lặp và container phải được thiết kế tương thích.

## 8. Phân biệt API Reflection khi có annotation lặp

Một nguồn lỗi thường gặp là **đọc một annotation đơn lẻ bằng API dành cho single annotation** rồi kết luận annotation không tồn tại.

| API Reflection | Trên class có hai `@Topic` trực tiếp | Ý nghĩa |
| --- | --- | --- |
| `getDeclaredAnnotation(Topic.class)` | `null` trong ví dụ chuẩn | Không tự mở container `Topics` để tìm một `Topic` |
| `getDeclaredAnnotation(Topics.class)` | Container có `Topic[2]` | Đọc loại container trực tiếp |
| `getDeclaredAnnotationsByType(Topic.class)` | Mảng gồm hai `Topic` | Tìm loại `Topic` khai báo trực tiếp **hoặc gián tiếp qua container** |
| `getAnnotationsByType(Topic.class)` | Mảng gồm hai `Topic` | Tương tự trong trường hợp này; có thêm ngữ nghĩa kế thừa theo luật tương ứng |
| `getDeclaredAnnotations()` | Chứa một container `Topics` trong ví dụ này | Lấy các annotation được coi là khai báo trực tiếp, không tự bóc thành hai `Topic` |

Điểm chính: **`getAnnotationsByType` và `getDeclaredAnnotationsByType` được thiết kế để phục vụ repeated annotations**. Các API `getAnnotation` và `getDeclaredAnnotation` trả một annotation đơn không tự diễn giải container thành tập hợp các phần tử lặp.

Nếu bạn dùng container có phần tử phụ (ví dụ `String source() default "manual"`), API `getAnnotationsByType(Topic.class)` chủ yếu cho các `Topic` riêng lẻ. Muốn đọc metadata phụ trên container, phải lấy `Topics` một cách phù hợp.

### 8.1. “Present” và “associated” có thể khác nhau

Trong Java, một annotation có thể **được khai báo trực tiếp**, **xuất hiện gián tiếp thông qua container**, hoặc **được tìm thấy theo luật kế thừa**. Vì vậy không nên cho rằng tất cả API Reflection nói về annotation đều cho kết quả như nhau.

Đặc biệt:

- Với **một** `@Topic` trực tiếp, `getDeclaredAnnotation(Topic.class)` thấy annotation đó.
- Với **hai** `@Topic` trực tiếp tại cùng một vị trí, thông thường chỉ có container `Topics` được lưu như annotation khai báo trực tiếp; muốn lấy hai `Topic` hãy dùng `getDeclaredAnnotationsByType(Topic.class)`.
- Với container được viết **tường minh**, `getAnnotationsByType(Topic.class)` vẫn có thể mở container.
- Với `@Inherited`, `getAnnotationsByType` có cơ chế xem xét annotation từ superclass phù hợp, nhưng cần hiểu các quy tắc về khai báo tại subclass; tránh tự suy diễn rằng kết quả từ cha và con luôn được nối vào một danh sách.

Trong nhiều ứng dụng đọc metadata trên đúng lớp được đánh dấu, lựa chọn đơn giản và ít lỗi nhất là `getDeclaredAnnotationsByType(MyAnnotation.class)` nếu không cần xét kế thừa, hoặc `getAnnotationsByType(MyAnnotation.class)` khi muốn theo các quy tắc kế thừa được API hỗ trợ.

## 9. Điều gì xảy ra nếu annotation không được đánh dấu @Repeatable?

Nếu:

```java
@interface Step {
    String value();
}
```

thì khai báo:

```java
@Step("one")
@Step("two")
class Workflow {
}
```

**Không hợp lệ**: `Step` không phải repeatable annotation type, dù bạn có thể viết một annotation container độc lập kiểu `Steps`. Chỉ định container trong `@Repeatable(Steps.class)` mới tạo quan hệ mà compiler công nhận.

Thêm một khai báo container như sau **vẫn chưa đủ nếu thiếu `@Repeatable` trên `Step`**:

```java
@interface Steps {
    Step[] value();
}
```

Cần cả hai phần: `@Repeatable(Steps.class)` trên annotation lặp **và** chữ ký `Step[] value()` trong container tương thích.

Tương tự, nếu container hiện diện nhưng không đáp ứng những điều kiện ở mục 6 và 7, compiler sẽ báo lỗi thiết kế annotation type, chứ không chờ ứng dụng runtime mới phát hiện.

## 10. Không nên trộn lặp trực tiếp với container tường minh cùng vị trí

Những cách viết sau là **những phương án tương đương về mục tiêu**, hãy chọn một cho một nơi sử dụng:

```java
@Topic("a")
@Topic("b")
class FirstWay {
}

@Topics({@Topic("a"), @Topic("b")})
class SecondWay {
}
```

Tránh viết cả `@Topic` và `@Topics` trên **cùng một khai báo** để biểu diễn danh sách giống nhau. Những tổ hợp trực tiếp/container trên cùng nơi khai báo có các quy tắc chặt chẽ về repeated annotations và có thể khiến compiler từ chối. Cách nhất quán giúp tránh nhầm số lần xuất hiện, thứ tự và kết quả Reflection.

Trong code review, thấy một container như `@Topics({...})` **không nhất thiết là thiết kế sai hoặc lỗi thời**: đó là một cú pháp hợp lệ, đặc biệt khi cần tự viết container. Nhưng việc đặt nhiều `@Topic` riêng lẻ thường dễ đọc hơn khi nhu cầu chỉ là gắn nhiều annotation giống loại.

## 11. Trường hợp thực tế: nhiều quy tắc kiểm tra cùng loại

Giả sử một hệ thống có nhiều rule áp dụng lên cùng loại dữ liệu:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@Repeatable(Checks.class)
@interface Check {
    String field();
    String rule();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Checks {
    Check[] value();
}

@Check(field = "email", rule = "required")
@Check(field = "email", rule = "format")
class Registration {
}
```

Khi xử lý:

```java
for (Check check : Registration.class.getAnnotationsByType(Check.class)) {
    System.out.println(check.field() + ":" + check.rule());
}
```

Đoạn vòng lặp là **mã minh họa đặt trong một phương thức**, sử dụng ba kiểu đã khai báo ở trên.

Stdout của vòng lặp:

```text
email:required
email:format
```

Điều quan trọng:

- `Check` chứa **một bộ dữ liệu** `field`/`rule`.
- `Checks.value()` chứa **nhiều `Check`**, không chứa các chuỗi từ từng `rule` riêng lẻ.
- `getAnnotationsByType(Check.class)` trả những annotation `Check` trong danh sách theo thứ tự phù hợp để mã xử lý duyệt.
- Annotation **không tự kiểm tra dữ liệu nhập**. Muốn biến metadata `rule = "required"` thành hành vi kiểm tra thật, chương trình/framework phải tự hiện thực logic, kiểm soát input, thứ tự xử lý và báo lỗi.

Đây là lý do mảng annotation trong container có giá trị: mỗi phần tử lưu **nhiều trường metadata có cấu trúc**, chứ không chỉ là một phần tử `String`.

## 12. Các lỗi phổ biến và cách sửa

**Lỗi 1 — Container trả về mảng của giá trị bên trong annotation.**

```java
@interface Roles {
    String[] value(); // Sai nếu đây là container cho @Role.
}
```

Sửa thành `Role[] value();`. `String` có thể là kiểu trả về của `Role.value()`, nhưng container phải chứa **các đối tượng annotation `Role`**.

**Lỗi 2 — Dùng tên `roles()` vì nghe tự nhiên hơn.**

```java
@interface Roles {
    Role[] roles(); // Không thay thế được phần tử value().
}
```

Trong cặp `@Repeatable(Roles.class)`, container bắt buộc cung cấp `value()`; bạn có thể đặt tên **annotation type** theo ngữ cảnh, nhưng không đổi quy ước tên phần tử này.

**Lỗi 3 — Cho `value()` một annotation đơn, hoặc mảng đa chiều.**

`Role value()` không biểu diễn được danh sách đúng hợp đồng; `Role[][] value()` vi phạm giới hạn loại phần tử annotation.

**Lỗi 4 — Container có thêm element bắt buộc.**

Nếu `Roles` có `String version();` mà không có default, compiler không có giá trị để cung cấp khi sinh container cho các lần `@Role` lặp. Dùng `String version() default "v1";` nếu thực sự cần phần tử phụ.

**Lỗi 5 — Retention không đồng nhất.**

`@Role` có `RUNTIME` nhưng `@Roles` chỉ có `CLASS` sẽ bị compiler từ chối theo quy tắc container. Hai loại nên có retention phù hợp với mục tiêu Reflection.

**Lỗi 6 — Chỉ khai báo container nhưng quên `@Repeatable`.**

Container annotation độc lập không tự làm `@Role` lặp được. Thêm `@Repeatable(Roles.class)` đúng chỗ.

**Lỗi 7 — Dùng `getAnnotation(Role.class)` để tìm mọi Role.**

Với annotation lặp được đóng gói qua container, truy vấn annotation đơn có thể trả `null`. Dùng `getAnnotationsByType(Role.class)` hoặc `getDeclaredAnnotationsByType(Role.class)` để nhận danh sách.

**Lỗi 8 — Cho rằng container là collection runtime tùy ý.**

`Role[] value()` là phần tử annotation, được Java kiểm tra khi biên dịch. Nó **không phải `List<Role>`**, không tự hỗ trợ thêm/xóa phần tử khi đang chạy và không thể trả `null`.

## 13. Bài tập kiểm tra

### Bài 1: Điền chữ ký bắt buộc

Cho:

```java
@Repeatable(Permissions.class)
@interface Permission {
    String resource();
    String action();
}
```

Hãy hoàn thiện:

```java
@interface Permissions {
    // Điền phần tử bắt buộc ở đây.
}
```

**Đáp án:** `Permission[] value();`. Do `Permission` không khai báo `@Retention`, mặc định là `CLASS`; nếu định dùng Reflection ở runtime, hãy cân nhắc `RUNTIME` cho cả `Permission` và `Permissions`.

### Bài 2: Phân biệt hai value()

Trong:

```java
@Repeatable(Flags.class)
@interface Flag {
    String value();
}

@interface Flags {
    Flag[] value();
}
```

Giá trị của `@Flag("alpha")` là gì, và giá trị của `@Flags({@Flag("alpha"), @Flag("beta")})` là gì?

**Đáp án:** `Flag.value()` cho `"alpha"`; `Flags.value()` cho mảng gồm hai annotation `Flag`. Chúng có cùng tên phần tử nhưng ở **hai loại annotation khác nhau**, với kiểu trả về khác nhau.

### Bài 3: Reflection

Với `@Topic("a") @Topic("b")` trên một class và retention `RUNTIME` cho cặp annotation, dự đoán:

- `getDeclaredAnnotation(Topic.class)`
- `getDeclaredAnnotation(Topics.class).value().length`
- `getAnnotationsByType(Topic.class).length`

**Đáp án:** lần lượt `null`, `2`, `2` trong ví dụ chuẩn (không kèm annotation `Topic` đơn độc nào khác trên class đó).

### Bài 4: Bắt lỗi định nghĩa container

Tìm lỗi:

```java
@Repeatable(MarkList.class)
@Retention(RetentionPolicy.RUNTIME)
@interface Mark {
    int id();
}

@Retention(RetentionPolicy.CLASS)
@interface MarkList {
    Mark[] value();
    String source();
}
```

**Đáp án:** retention của `MarkList` không đủ cho `Mark` có `RUNTIME`; ngoài `value()`, phần tử `source()` không có default. Sửa `MarkList` thành `@Retention(RUNTIME)` và cho `source()` một default hoặc bỏ nó.

### Bài 5: Thiết kế kiểm tra metadata

Tại sao mảng `Check[]` thích hợp hơn `String[]` nếu mỗi check có cả `field` và `rule`? Bạn sẽ dùng API nào để đọc **tất cả check** khi một class chỉ có một `@Check` hoặc có nhiều `@Check`?

**Đáp án:** từng `Check` biểu diễn một bộ giá trị có kiểu rõ ràng. Dùng `getAnnotationsByType(Check.class)` để đọc thống nhất một, nhiều hoặc container tường minh.

## 14. Checklist trước khi tạo repeatable annotation

1. Loại annotation **được lặp** đã khai báo `@Repeatable(Container.class)` chưa?
2. Container là **một annotation type** tồn tại thật với phần tử tên đúng **`value()`** chưa?
3. Chữ ký phần tử chính xác là **`RepeatedAnnotation[] value();`** và là mảng **một chiều** chưa?
4. Các phần tử khác của container, nếu có, đã có **default** chưa?
5. `@Retention`, `@Target`, và khi cần `@Documented`/`@Inherited` của hai loại đã tương thích chưa?
6. Nếu cần Reflection, cả hai đã chọn `RUNTIME` chưa?
7. Code đọc nhiều annotation đã dùng `getAnnotationsByType` hoặc `getDeclaredAnnotationsByType` thay cho cách đọc annotation đơn chưa?
8. Đã thử cả ba trường hợp: **một lần**, **lặp hai lần**, và **container tường minh** chưa?

**Ghi nhớ:** `@Repeatable` chỉ ra container; còn **`RepeatedAnnotation[] value()` là hợp đồng bắt buộc của container**. Compiler cần chính chữ ký đó để nhóm các lần xuất hiện cùng loại annotation. Khi truy vấn sau biên dịch, hãy lựa chọn đúng API để đọc annotation trực tiếp hoặc gián tiếp từ container, đồng thời nhớ rằng metadata không tự tạo ra hành vi nghiệp vụ.