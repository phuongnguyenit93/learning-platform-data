# Phần tử bắt buộc và khai báo giá trị mặc định bằng `default` trong Java Annotation

## 1. Vấn đề cần hiểu

Một **annotation type** (kiểu annotation) trong Java được khai báo bằng `@interface`. Bên trong nó có các **annotation elements** (phần tử annotation) trông giống khai báo phương thức không có tham số, chẳng hạn `String name();` hoặc `int priority() default 5;`. Khi gắn annotation lên một khai báo, lập trình viên cung cấp giá trị cho các phần tử mà annotation yêu cầu.

Ví dụ:

```java
@interface TaskInfo {
    String name();                     // Bắt buộc
    int priority() default 5;          // Có giá trị mặc định
    boolean enabled() default true;    // Có giá trị mặc định
}
```

Cách dùng hợp lệ:

```java
@TaskInfo(name = "send-report")
class ReportJob {}

@TaskInfo(name = "sync-data", priority = 9, enabled = false)
class SyncJob {}
```

- `name()` **không có `default`** nên khi dùng `@TaskInfo` phải chỉ rõ `name = ...`.
- `priority()` có `default 5`: không truyền `priority` thì giá trị hiệu lực là `5`; khi cần có thể ghi đè bằng `priority = 9`.
- `enabled()` có `default true`: không truyền thì kết quả là `true`; `enabled = false` là lựa chọn tường minh.
- Những giá trị này là **metadata của annotation**, không tự khiến một tác vụ chạy hoặc thay đổi độ ưu tiên. Bộ xử lý annotation, framework hoặc chương trình đọc annotation phải diễn giải metadata để tạo hành vi.

Điểm quyết định: **phần tử bắt buộc là phần tử không khai báo giá trị mặc định; phần tử tùy chọn là phần tử có khai báo `default`.** Java không dùng quy tắc “kiểu `int` mặc định `0`, kiểu `boolean` mặc định `false` hoặc `String` mặc định `null`” để tự điền giá trị cho phần tử annotation chưa được chỉ định.

## 2. Cú pháp khai báo phần tử và `default`

Một phần tử trong annotation type có dạng cơ bản:

```java
KiểuTraVe tenPhanTu() [default giaTriMacDinh];
```

Dấu ngoặc vuông trong dòng trên chỉ là ký hiệu mô tả phần tùy chọn, **không phải cú pháp Java để chép nguyên văn**.

Ví dụ khai báo annotation:

```java
public @interface EndpointInfo {
    String path();                             // Bắt buộc
    String httpMethod() default "GET";         // Tùy chọn
    int timeoutMillis() default 1500;          // Tùy chọn
    String[] tags() default {};                // Tùy chọn, mảng rỗng
}
```

Trong annotation type:

1. Phần tử được khai báo như một phương thức **không có tham số, không có thân**; kiểu trả về mô tả kiểu dữ liệu của thuộc tính.
2. Từ khóa `default` được đặt **sau `()`** và trước dấu `;`, gắn một giá trị hợp lệ cho **chính phần tử đó**.
3. Không được khai báo phần tử dạng `String path(String prefix);`; annotation element không nhận tham số.
4. Không được khai báo phần tử với `throws`, type parameters hoặc return type không được Java cho phép đối với annotation elements.
5. Tất cả annotation elements có đặc tính `public abstract` theo ngữ nghĩa của annotation type, dù không cần viết hai từ khóa đó. Không có constructor, setter hoặc getter với logic riêng để sinh giá trị mặc định.

`default` trong `String path() default "/";` **khác hoàn toàn** với `default` dùng để khai báo một phương thức có thân trong interface thông thường:

```java
interface Greeting {
    default String hello() {
        return "hello";
    }
}
```

Đây là interface bình thường với **default method có thân**. Trong một annotation type, `default` gắn **giá trị mặc định cho element**, còn element vẫn không có thân phương thức.

## 3. Khi sử dụng annotation: bắt buộc phải điền gì?

Ví dụ có annotation `EndpointInfo` ở trên. Các cách sử dụng sau đều hợp lệ:

```java
@EndpointInfo(path = "/users")
class ListUsers {}

@EndpointInfo(path = "/users", httpMethod = "POST")
class CreateUser {}

@EndpointInfo(
    path = "/audit",
    httpMethod = "POST",
    timeoutMillis = 4000,
    tags = {"security", "write"}
)
class AuditLog {}
```

Có thể cung cấp các phần tử theo thứ tự khác nhau. Tên được viết ở vị trí sử dụng là tên element **không có ngoặc**, ví dụ `path = "/users"`, không viết `path() = ...`.

Khi chỉ viết:

```java
@EndpointInfo(path = "/users")
```

thì các giá trị hiệu lực là:

| Phần tử | Có `default`? | Giá trị hiệu lực |
| --- | --- | --- |
| `path()` | Không | `"/users"` do nơi sử dụng cung cấp |
| `httpMethod()` | Có, `"GET"` | `"GET"` |
| `timeoutMillis()` | Có, `1500` | `1500` |
| `tags()` | Có, `{}` | Mảng `String` rỗng |

Đoạn sau **cố ý sai**:

```java
@EndpointInfo
class MissingPath {}
```

`javac` từ chối vì `path` là phần tử bắt buộc nhưng không được cung cấp. Dùng `@EndpointInfo()` cũng không khắc phục vấn đề: ngoặc rỗng không tự tạo giá trị cho `path`.

Nếu cần `path` thật sự tùy chọn, người thiết kế phải xác định ý nghĩa của một giá trị mặc định, chẳng hạn `String path() default "/";`; việc lựa chọn có nên mặc định như vậy hay không phụ thuộc hợp đồng cụ thể.

## 4. Java 17+: ví dụ đầy đủ có thể biên dịch và chạy

Ví dụ này cho thấy ba hiện tượng trong một lần chạy: element bắt buộc, element mặc định, và element được truyền giá trị riêng. Đồng thời dùng reflection để thấy sự khác biệt giữa **giá trị trên annotation đã sử dụng** và **giá trị default khai báo trong annotation type**.

Lưu toàn bộ đoạn sau vào tệp **`AnnotationDefaultsDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface EndpointInfo {
    String path();
    String httpMethod() default "GET";
    int timeoutMillis() default 1500;
    String[] tags() default {};
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Label {
    String value();
    String language() default "vi";
}

@EndpointInfo(path = "/orders")
class ListOrders {}

@EndpointInfo(
        path = "/orders",
        httpMethod = "POST",
        timeoutMillis = 3000,
        tags = {"write", "audit"}
)
class CreateOrder {}

@Label("orders")
class OrderModule {}

public class AnnotationDefaultsDemo {
    private static void showEndpoint(Class<?> type) {
        EndpointInfo info = type.getAnnotation(EndpointInfo.class);
        System.out.println(
                info.httpMethod() + " " + info.path()
                + " | timeout=" + info.timeoutMillis()
                + " | tags=" + Arrays.toString(info.tags())
        );
    }

    public static void main(String[] args) throws NoSuchMethodException {
        showEndpoint(ListOrders.class);
        showEndpoint(CreateOrder.class);

        Label label = OrderModule.class.getAnnotation(Label.class);
        System.out.println(label.value() + " | " + label.language());

        System.out.println(
                EndpointInfo.class.getDeclaredMethod("path").getDefaultValue()
        );
        System.out.println(
                EndpointInfo.class.getDeclaredMethod("httpMethod").getDefaultValue()
        );
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên trong thư mục chứa tệp:

```bash
javac --release 17 AnnotationDefaultsDemo.java
java AnnotationDefaultsDemo
```

**Stdout chính xác:**

```text
GET /orders | timeout=1500 | tags=[]
POST /orders | timeout=3000 | tags=[write, audit]
orders | vi
null
GET
```

Giải thích theo từng dòng:

1. `ListOrders` chỉ cung cấp `path`, vì thế `httpMethod`, `timeoutMillis` và `tags` lấy các giá trị mặc định `GET`, `1500`, `{}`.
2. `CreateOrder` cung cấp đủ giá trị riêng cho bốn element; giá trị được chỉ định ở nơi sử dụng có hiệu lực thay cho giá trị mặc định tương ứng.
3. `@Label("orders")` là cú pháp rút gọn của `@Label(value = "orders")`; phần tử `language()` dùng mặc định `"vi"`.
4. `getDefaultValue()` trên phương thức đại diện cho `path` trả `null` vì **không có mặc định**; điều này không có nghĩa giá trị `path` của một annotation được dùng hợp lệ có thể là `null`.
5. `getDefaultValue()` của `httpMethod` trả `"GET"` vì annotation type khai báo mặc định như vậy.

Vì ví dụ dùng `@Retention(RetentionPolicy.RUNTIME)`, runtime có thể lấy annotation qua `getAnnotation`. Nếu annotation không hiện diện trên một class, `Class.getAnnotation(...)` có thể trả `null`; trong chương trình này hai class truyền vào `showEndpoint` đều có annotation nên không gây lỗi truy cập `null`.

## 5. Phần tử đặc biệt `value()` và cú pháp rút gọn

Nếu annotation có phần tử tên chính xác là `value`, Java cho phép bỏ cặp `value =` trong một dạng sử dụng phù hợp:

```java
@interface Category {
    String value();
    boolean visible() default true;
}

@Category("payments")
class PaymentFeature {}

@Category(value = "reports", visible = false)
class ReportFeature {}
```

Ở đây:

- `@Category("payments")` tương đương `@Category(value = "payments")`.
- Nếu cần cung cấp thêm element như `visible`, dùng cú pháp **cặp tên–giá trị** đầy đủ như ở `ReportFeature`.
- Tên `value()` **không khiến element tự động tùy chọn**; vì không có `default`, `value` vẫn bắt buộc.
- Nếu `String value() default "general";` thì cả `@Category` lẫn `@Category()` đều có thể hợp lệ (với điều kiện không còn element bắt buộc khác), và `value` sẽ có giá trị mặc định `"general"`.

Đừng nhầm cú pháp rút gọn với quyền được bỏ qua các element khác còn bắt buộc. Ví dụ:

```java
@interface OwnerInfo {
    String value();
    String team();
}
```

`@OwnerInfo("alice")` là **không hợp lệ** vì chưa có `team`. Phải viết `@OwnerInfo(value = "alice", team = "backend")`.

## 6. Kiểu dữ liệu và giá trị hợp lệ cho `default`

Java giới hạn chặt kiểu trả về của annotation element. Đây là **giá trị metadata tĩnh**, không phải nơi chạy mã tùy ý.

| Kiểu element hợp lệ | Ví dụ khai báo `default` |
| --- | --- |
| Kiểu nguyên thủy (trừ `void`) | `int retries() default 3;`, `boolean enabled() default true;` |
| `String` | `String name() default "anonymous";` |
| `Class` hoặc dạng tham số hóa phù hợp | `Class<?> handler() default Object.class;` |
| Một enum type | `Level level() default Level.BASIC;` |
| Một annotation type | `Policy policy() default @Policy("safe");` |
| Mảng **một chiều** của kiểu được phép | `String[] tags() default {};`, `int[] levels() default {1, 2};` |

Đoạn sau minh họa các loại đó; đây là **các khai báo hỗ trợ**, không phải chương trình độc lập có `main`:

```java
enum Level {
    BASIC, STRICT
}

@interface Policy {
    String value();
}

@interface AuditOptions {
    Level level() default Level.BASIC;
    Class<?> handler() default Object.class;
    String[] tags() default {"audit"};
    Policy policy() default @Policy("standard");
}
```

Đối với phần tử kiểu nguyên thủy hoặc `String`, biểu thức default phải thỏa điều kiện hằng số tại compile time; đối với enum phải là enum constant; đối với `Class` thường dùng class literal; đối với nested annotation dùng giá trị annotation như `@Policy("standard")`. Giá trị mảng được mô tả bằng danh sách phần tử hợp lệ trong `{...}`.

**Những kiểu không được dùng làm annotation element** gồm `Object`, `List<String>`, `Map<...>`, một class đối tượng tùy ý, type variable `T`, hoặc mảng nhiều chiều `String[][]`. Không thể dùng constructor hoặc kết quả lời gọi phương thức tùy ý để tạo một default.

### 6.1. Mảng và cú pháp giá trị ở nơi sử dụng

Với khai báo:

```java
@interface Roles {
    String[] value() default {};
}
```

Các cách dùng sau là hợp lệ:

```java
@Roles
class PublicResource {}

@Roles("ADMIN")
class AdminResource {}

@Roles({"ADMIN", "AUDITOR"})
class RestrictedResource {}
```

- `@Roles` sử dụng giá trị mặc định: mảng rỗng.
- `@Roles("ADMIN")` là dạng viết gọn hợp lệ khi một annotation element có kiểu mảng nhận **một giá trị phần tử**.
- `@Roles({"ADMIN", "AUDITOR"})` cung cấp mảng gồm hai giá trị.
- `default {}` có nghĩa không có phần tử, **khác** `default {""}` là một mảng gồm một chuỗi rỗng.
- Khi cần biểu diễn “không được chỉ định” riêng biệt với “danh sách rỗng”, hãy thiết kế hợp đồng rõ ràng thay vì giả định hai trường hợp luôn phân biệt được qua kết quả đọc annotation.

### 6.2. Không có `null` trong giá trị annotation

Các cách sau **không hợp lệ**:

```java
@interface BadDefaults {
    String missing() default null;           // Sai
    int count() default Integer.parseInt("2"); // Sai
    String[] nested() default {null};        // Sai
}
```

Java không cho dùng `null` làm giá trị annotation hoặc giá trị mặc định. Một lời gọi như `Integer.parseInt("2")` không phải biểu thức hằng số tại compile time, dù có thể cho kết quả `2` khi chạy. Dùng trực tiếp `default 2` sẽ hợp lệ.

Nếu nghiệp vụ cần nghĩa “không có giá trị”, các lựa chọn thường gặp là một chuỗi quy ước như `""` (kèm tài liệu), mảng rỗng, enum như `UNSPECIFIED`, hoặc một kiểu `Class` sentinel phù hợp. Mỗi cách đều cần giải thích ý nghĩa, vì chúng là giá trị thật.

## 7. `default` được kiểm tra và áp dụng ở đâu?

Có ba thời điểm cần phân biệt:

**Khi biên dịch khai báo annotation type:** compiler kiểm tra kiểu của element, kiểu và tính hợp lệ của biểu thức default. Nếu khai báo `int timeout() default "slow";`, `javac` báo lỗi vì `String` không phù hợp với `int`.

**Khi biên dịch nơi sử dụng annotation:** compiler bắt buộc mỗi element **không có default** phải có giá trị phù hợp. Những element có default có thể được bỏ qua hoặc truyền giá trị tường minh. Ví dụ, `@EndpointInfo(httpMethod = "POST")` lỗi vì thiếu `path`, còn `@EndpointInfo(path = "/")` hợp lệ.

**Khi đọc annotation đã tồn tại:** nếu một giá trị không được ghi tường minh ở nơi sử dụng, giá trị mặc định được lấy từ khai báo annotation type. Ở runtime, có thể dùng `annotation.httpMethod()` để lấy giá trị hiệu lực, hoặc `EndpointInfo.class.getDeclaredMethod("httpMethod").getDefaultValue()` để lấy chính default khai báo.

Theo cơ chế của Java, các giá trị mặc định **không được sao chép vào mọi lần sử dụng annotation**. Chúng gắn với định nghĩa annotation type và được áp dụng khi đọc. Vì vậy, việc sửa `default` của một annotation library có thể làm thay đổi giá trị quan sát được từ các chỗ dùng đã biên dịch trước đó (nếu những nơi đó không cung cấp giá trị tường minh). Đối với public API, thay đổi default là thay đổi hợp đồng và phải được đánh giá cẩn thận.

Ví dụ: ban đầu `int timeoutMillis() default 1500;`, nhiều class chỉ ghi `@EndpointInfo(path = "/")`. Nếu một phiên bản thư viện sau này sửa default thành `3000`, những chỗ không truyền `timeoutMillis` có thể nhận `3000` khi dùng định nghĩa mới. Những chỗ đã truyền `timeoutMillis = 1000` vẫn giữ giá trị tường minh của chúng.

## 8. `default` không đồng nghĩa với việc giá trị luôn phù hợp nghiệp vụ

Trình biên dịch kiểm tra **kiểu** và việc cung cấp đủ các element, nhưng thường không biết ràng buộc nghiệp vụ của metadata.

Ví dụ:

```java
@interface RetryPolicy {
    int maxAttempts() default 3;
}
```

`@RetryPolicy(maxAttempts = -5)` hợp lệ theo kiểu Java vì `-5` là `int`, nhưng có thể vô nghĩa đối với bộ xử lý retry. Nếu cần các ràng buộc như số lần thử phải dương, hãy kiểm tra ở nơi dùng metadata hoặc áp dụng công cụ kiểm tra phù hợp. Annotation element không cho đặt một thân method với logic validation bên trong.

Một default tốt có ý nghĩa rõ ràng, ít bất ngờ và có thể sử dụng an toàn với phần lớn trường hợp. Nếu không có giá trị hợp lý dùng chung, **giữ element bắt buộc** để buộc caller chỉ định mục đích của họ. Ví dụ `path()` của endpoint thường nên là bắt buộc nếu không thể suy ra đường dẫn chung phù hợp.

## 9. Những lỗi biên dịch phổ biến và cách sửa

| Tình huống | Vì sao sai hoặc dễ nhầm? | Cách xử lý |
| --- | --- | --- |
| `@EndpointInfo` khi `path()` không có default | Thiếu giá trị bắt buộc | `@EndpointInfo(path = "/orders")` |
| `String path() default null;` | `null` không phải annotation element value hợp lệ | Chọn sentinel có tài liệu hoặc không khai báo default |
| `int delay() default loadConfig();` | Lời gọi method không phải hằng số compile time | Dùng hằng số hợp lệ hoặc để hệ thống xử lý giá trị động bên ngoài annotation |
| `String[] tags() default null;` | Mảng annotation cũng không nhận `null` | Dùng `default {}` nếu “rỗng” là đúng nghĩa |
| `List<String> tags() default ...;` | `List` không phải return type annotation element hợp lệ | Chuyển sang `String[]` nếu phù hợp |
| `@OwnerInfo("alice")` khi còn `team()` bắt buộc | Cú pháp `value` rút gọn không miễn các phần tử bắt buộc khác | Dùng `@OwnerInfo(value = "alice", team = "backend")` |
| `@EndpointInfo(path = "/orders", timeoutMillis = "1500")` | Giá trị kiểu `String` không tương thích với `int` | Dùng `timeoutMillis = 1500` |
| Tưởng `@Retention(RUNTIME)` tự thêm default | Retention chỉ điều chỉnh khả năng lưu giữ annotation | Khai báo `default` trên chính element cần tùy chọn |
| Tưởng `default` tự chạy hành vi | Metadata không tự thực hiện nghiệp vụ | Xây dựng bộ xử lý, framework integration hoặc logic đọc metadata |

Ví dụ một lỗi khác là **gán lặp một element**:

```java
@EndpointInfo(path = "/a", path = "/b") // Sai: path bị chỉ định hai lần
class DuplicatePath {}
```

Mỗi element chỉ được chỉ định một lần trong một annotation cụ thể. Muốn có nhiều giá trị, hãy thiết kế element dạng mảng nếu hợp đồng cho phép.

## 10. Hướng dẫn thiết kế và kiểm thử annotation có default

Khi tạo annotation dùng trong Java hoặc trong một framework:

1. Liệt kê những metadata **caller luôn phải quyết định**. Khai báo chúng không có `default`.
2. Với những metadata có thể dùng một chính sách chung rõ ràng, khai báo `default` ngay tại element và ghi tài liệu cho ý nghĩa của nó.
3. Chọn kiểu element nằm trong tập được Java hỗ trợ. Nếu cần nhiều giá trị, cân nhắc mảng một chiều, enum hoặc nested annotation.
4. Xem xét liệu `value()` có thực sự là thành phần chính của annotation trước khi dùng cú pháp rút gọn; tên rõ nghĩa đôi khi dễ hiểu hơn.
5. Biên dịch cả ví dụ tối thiểu chỉ điền các element bắt buộc và ví dụ tùy chỉnh tất cả các element. Kiểm tra thêm trường hợp cố tình thiếu phần tử bắt buộc để chắc chắn compiler bắt lỗi.
6. Nếu một công cụ đọc annotation lúc chạy, đặt retention phù hợp (thường là `RUNTIME`), đọc metadata và kiểm tra ràng buộc nghiệp vụ riêng.
7. Với annotation đã publish, cân nhắc tác động của việc **thêm một element bắt buộc mới**: các nơi sử dụng hiện có sẽ không còn hợp lệ khi biên dịch lại. Thêm element có default thường dễ tương thích hơn ở cấp nguồn, nhưng mọi thay đổi API vẫn cần thử nghiệm với consumer.
8. Khi sửa default, đánh giá những caller không truyền giá trị tường minh vì họ có thể nhận hành vi mới dù không sửa mã nguồn.

**Điểm cần nhớ:** Trong annotation type, `String name();` tạo một element **bắt buộc**, còn `String name() default "guest";` cho phép nơi dùng **bỏ qua** element ấy để lấy giá trị mặc định. Compiler chịu trách nhiệm kiểm tra hợp lệ; hệ thống sử dụng annotation mới quyết định metadata có ý nghĩa và tác động nghiệp vụ ra sao.
