# Nhận biết lỗi cú pháp, thiếu phần tử và tên phần tử không hợp lệ trong Java Annotation

## 1. Mục tiêu và phạm vi

Khi viết hoặc sử dụng annotation trong Java, cần phân biệt ba nhóm lỗi thường gặp:

1. **Sai cú pháp:** thiếu `@`, dấu ngoặc, dấu phẩy, dấu `=`, dấu `;` hoặc viết sai cấu trúc khai báo annotation.
2. **Thiếu phần tử bắt buộc:** annotation đã khai báo một phần tử không có giá trị mặc định (`default`), nhưng nơi sử dụng không cung cấp giá trị.
3. **Tên phần tử không hợp lệ hoặc không tồn tại:** tên không phải Java identifier hợp lệ, trùng từ khóa, gõ sai tên được khai báo hoặc đặt tên khác chữ hoa/chữ thường.

Một số lỗi trông giống lỗi cú pháp nhưng thực chất là lỗi kiểm tra kiểu hoặc yêu cầu của Java đối với giá trị annotation. Biết phân biệt chúng giúp đọc thông báo `javac` đúng và sửa lỗi tại nguồn.

## 2. Nhận diện cấu trúc hợp lệ

Annotation type được khai báo bằng `@interface`. Mỗi *annotation element* được viết giống phương thức không tham số, không có thân; có thể khai báo giá trị mặc định với `default`.

```java
@interface TaskInfo {
    String name();                    // Bắt buộc
    int priority() default 1;        // Có thể bỏ qua khi sử dụng
    String[] tags() default {};      // Giá trị mặc định là mảng rỗng
}

@TaskInfo(name = "backup")
class BackupJob {}

@TaskInfo(name = "report", priority = 3, tags = {"daily", "finance"})
class ReportJob {}
```

Đọc ví dụ theo hai phía:

- **Phía khai báo:** `name()`, `priority()` và `tags()` là *tên phần tử*. `name()` không có `default` nên là bắt buộc. `priority()` và `tags()` có `default`.
- **Phía sử dụng:** cú pháp thông dụng là `@TenAnnotation(tenPhanTu = giaTri, ...)`. Các tên phía trái dấu `=` phải khớp chính xác với phần tử đã khai báo.
- `@TaskInfo(name = "backup")` hợp lệ vì chỉ thiếu hai phần tử đã có mặc định.
- `@TaskInfo` hoặc `@TaskInfo()` không hợp lệ với khai báo này vì thiếu `name`; việc bỏ ngoặc không làm mất yêu cầu cung cấp phần tử bắt buộc.

Bảng nhận diện nhanh:

| Dấu hiệu | Nhóm vấn đề | Cần kiểm tra |
|---|---|---|
| Thiếu `)`, `,`, `=` hoặc `;` | Cú pháp Java | Vị trí dấu phân cách và khai báo |
| Không truyền `name` trong `@TaskInfo` | Thiếu phần tử bắt buộc | Phần tử nào chưa có `default` |
| Viết `nmae = "..."` | Tên phần tử không tồn tại | Tên chính xác trong `@interface` |
| Khai báo `String 2name();` | Tên Java không hợp lệ | Quy tắc Java identifier |
| Truyền `priority = "high"` | Sai kiểu dữ liệu | Kiểu trả về của `priority()` |
| Truyền `name = createName()` | Giá trị không hợp lệ cho annotation | Quy tắc hằng số của annotation |

## 3. Lỗi cú pháp khi **khai báo** annotation

Khai báo phần tử phải có **kiểu trả về, tên hợp lệ, cặp ngoặc tròn rỗng và dấu chấm phẩy**; `default`, nếu có, đứng sau `()` và trước `;`:

```java
@interface Config {
    String key();
    int retryCount() default 3;
}
```

Các đoạn sau **cố ý sai**, được xem như các trường hợp độc lập; không ghép tất cả vào một file để chạy:

```java
// Sai: thiếu () ở khai báo phần tử
@interface BadA {
    String key;
}

// Sai: thiếu dấu ; cuối khai báo
@interface BadB {
    String key()
}

// Sai: phần tử annotation không nhận tham số
@interface BadC {
    String key(String prefix);
}

// Sai: element không có thân phương thức
@interface BadD {
    String key() { return "x"; }
}

// Sai: thiếu @ trong từ khóa @interface
interface BadE {
    String key();
}
```

Ở trường hợp `BadE`, `interface` là một interface Java thông thường. Dòng `String key();` có thể hợp lệ trong interface thường, nhưng đối tượng đó **không phải annotation type** và không thể dùng với `@BadE`. Đây là lỗi chọn sai cấu trúc khai báo, không nhất thiết là lỗi parser ngay tại dòng `interface`.

Cú pháp mặc định đúng là `String key() default "x";`. Viết `String key() = "x";` hoặc `default` sai vị trí sẽ gây lỗi. Ngoài ra, kiểu phần tử annotation chỉ được là kiểu nguyên thủy, `String`, `Class`, enum, annotation hoặc **mảng một chiều** của các kiểu đó. `List<String>`, `Object` hay `int[][]` không phải kiểu phần tử hợp lệ.

## 4. Lỗi cú pháp khi **sử dụng** annotation

Giả sử có khai báo:

```java
@interface Route {
    String path();
    int timeout() default 30;
}
```

Dạng hợp lệ:

```java
@Route(path = "/users", timeout = 10)
class UserHandler {}

@Route(path = "/health")
class HealthHandler {}
```

Những dạng sau **cố ý sai**:

```java
// Thiếu dấu = giữa tên và giá trị
@Route(path "/users")
class MissingEquals {}

// Thiếu dấu phẩy giữa hai cặp name = value
@Route(path = "/users" timeout = 10)
class MissingComma {}

// Thiếu dấu ) kết thúc annotation
@Route(path = "/users"
class MissingParen {}

// Dùng dấu : thay vì dấu = trong cặp tên/giá trị
@Route(path: "/users")
class WrongSeparator {}
```

Mỗi đoạn sai cần được tách ra để tự kiểm tra. `javac` thường đặt dấu `^` tại hoặc gần token mà bộ phân tích cú pháp không thể tiếp tục; **vị trí được chỉ ra không luôn là ký tự bị thiếu**. Khi thấy `')' expected`, `',' expected`, `'=' expected` hay `illegal start of expression`, hãy kiểm tra cả dấu ngay trước vị trí được đánh dấu.

Cũng cần phân biệt hai cách dùng:

- `@Route(path = "/users")` là annotation có danh sách cặp `tên = giá trị`.
- `@Deprecated` là dạng không có đối số, hợp lệ vì các phần tử của annotation chuẩn này có giá trị mặc định.

## 5. Thiếu phần tử bắt buộc: nhìn vào `default`

Một phần tử là bắt buộc khi nó **không** khai báo `default`. Java không tự suy ra giá trị như chuỗi rỗng, `0`, `false` hay `null`.

```java
@interface Audit {
    String action();                   // Bắt buộc
    boolean enabled() default true;    // Không bắt buộc
}

@Audit(action = "create")
class ValidAudit {}

@Audit(enabled = false)
class InvalidAudit {}                  // Sai: thiếu action

@Audit
class AlsoInvalidAudit {}              // Sai: vẫn thiếu action
```

Với `InvalidAudit` và `AlsoInvalidAudit`, thông báo của `javac` có thể nêu annotation thiếu giá trị mặc định cho `action`. Đây là lỗi **thiếu giá trị bắt buộc theo khai báo**, dù hình thức `@Audit` hoặc `@Audit(enabled = false)` nhìn có vẻ đúng cú pháp.

Cách sửa có hai hướng, tùy yêu cầu thiết kế:

1. Truyền đầy đủ giá trị: `@Audit(action = "delete", enabled = false)`.
2. Nếu nghiệp vụ thật sự có giá trị mặc định hợp lý, khai báo `String action() default "read";` tại annotation type. Khi ấy các cách gọi bỏ `action` mới hợp lệ.

Không nên thêm `default` chỉ để làm im lỗi biên dịch: nó thay đổi hợp đồng sử dụng annotation ở mọi nơi.

## 6. Tên phần tử hợp lệ và tên không tồn tại

Tên phần tử tuân theo quy tắc **Java identifier**: không bắt đầu bằng chữ số, không chứa ký tự như dấu gạch ngang `-` hoặc khoảng trắng, không trùng từ khóa Java. Java phân biệt hoa/thường. Dấu gạch dưới `_` đơn lẻ là từ khóa từ Java 9 nên không dùng làm tên; `request_name` lại hợp lệ.

```java
@interface Names {
    String value();
    String requestName() default "";
    int retry_count() default 0;
}
```

Các khai báo dưới đây sai vì tên không hợp lệ:

```java
@interface InvalidNames {
    String 2name();      // Bắt đầu bằng chữ số
    String request-name(); // Chứa dấu -
    String class();      // class là từ khóa
}
```

Khác với tên *không hợp lệ*, tên *không tồn tại* là tên có cú pháp Java hợp lệ nhưng **không được khai báo** trong annotation type:

```java
@Names(requestname = "sync", value = "job")
class WrongCase {}  // Sai: requestname khác requestName

@Names(value = "job", level = 2)
class UnknownElement {}  // Sai: Names không khai báo level()
```

Trong hai trường hợp, cần sửa tên ở nơi sử dụng thành đúng `requestName`, `retry_count` hoặc `value` nếu đó là ý định; đừng tự thêm một phần tử mới vào annotation khi chỉ gõ sai. Nếu một typo vô tình bỏ trống phần tử bắt buộc, `javac` có thể báo **nhiều lỗi cùng lúc**: phần tử tên lạ và phần tử bắt buộc còn thiếu.

Hai lỗi tên khác cũng cần lưu ý:

- **Lặp tên phần tử trong cùng một annotation:** `@Names(value = "one", value = "two")` không hợp lệ; mỗi phần tử chỉ gán một lần.
- **Đặt tên khác kiểu viết:** `@Names(Value = "job")` sai vì khai báo là `value()`, không phải `Value()`.

## 7. Quy tắc đặc biệt với phần tử tên `value`

Java cho phép viết tắt **duy nhất khi giá trị được truyền cho phần tử có tên đúng là `value`**.

```java
@interface Label {
    String value();
    int level() default 1;
}

@Label("stable")                           // Đúng: viết tắt value
class A {}

@Label(value = "stable", level = 2)        // Đúng: có thêm phần tử khác
class B {}

@Label(value = "stable")                   // Đúng: dạng ghi rõ tên
class C {}
```

Không áp dụng cách viết tắt cho phần tử tên khác:

```java
@interface Endpoint {
    String path();
}

@Endpoint("/users")   // Sai: Endpoint không có phần tử value()
class WrongShorthand {}
```

Nếu cần khai báo đồng thời phần tử `value` và phần tử khác, sử dụng dạng đầy đủ `@Label(value = "stable", level = 2)`. Tránh dạng `@Label("stable", level = 2)`: không trộn lẫn dạng một giá trị không có tên với danh sách `tên = giá trị`.

Với annotation chỉ có phần tử mặc định hoặc không có phần tử bắt buộc, có thể bỏ cặp ngoặc khi sử dụng: `@Marker` và `@Marker()` đều hợp lệ nếu `@interface Marker {}`. Với annotation có phần tử bắt buộc, bỏ ngoặc vẫn không giải quyết thiếu giá trị.

## 8. Sai kiểu và giá trị: phân biệt với lỗi tên/cú pháp

Không phải đoạn mã có đầy đủ dấu câu và tên đúng là sử dụng annotation hợp lệ. Compiler còn kiểm tra kiểu và giới hạn giá trị.

```java
@interface Check {
    String name();
    int retries() default 2;
    Class<?> handler() default Object.class;
}

@Check(name = "daily", retries = 3, handler = String.class)
class ValidCheck {}

@Check(name = "daily", retries = "three")
class WrongType {}             // Sai: retries() yêu cầu int

@Check(name = "daily", handler = "java.lang.String")
class WrongClassValue {}       // Sai: handler() yêu cầu Class<?>
```

Khi giá trị thuộc kiểu số nguyên thủy hoặc `String`, nó phải là **biểu thức hằng tại thời điểm biên dịch** (ví dụ literal hoặc hằng `static final` đủ điều kiện). Lời gọi phương thức lúc chạy không hợp lệ:

```java
@interface BuildInfo {
    String version();
}

class Versioned {
    static String getVersion() { return "1.0"; }

    // Sai: lời gọi phương thức không phải constant expression
    @BuildInfo(version = getVersion())
    static class Incorrect {}

    static final String VERSION = "1.0";
    @BuildInfo(version = VERSION)
    static class Correct {}
}
```

Giá trị mảng được cung cấp bằng `{...}` (hoặc một giá trị phần tử tương ứng khi Java cho phép rút gọn), enum bằng hằng enum, class literal bằng `String.class`. Không dùng `new` để khởi tạo đối tượng tùy ý rồi truyền cho phần tử annotation. Khi gặp lỗi như `incompatible types` hay `element value must be a constant expression`, hãy kiểm tra **kiểu khai báo và tính hợp lệ của giá trị**, trước khi sửa dấu câu.

## 9. Ví dụ Java 17+ đầy đủ, biên dịch và chạy được

Tạo duy nhất file `AnnotationSyntaxDemo.java`:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@interface EndpointInfo {
    String path();
    String method() default "GET";
    int[] successCodes() default {200};
}

@EndpointInfo(path = "/health")
class HealthEndpoint {}

@EndpointInfo(
        path = "/users",
        method = "POST",
        successCodes = {201, 202}
)
class UserEndpoint {}

public class AnnotationSyntaxDemo {
    public static void main(String[] args) {
        EndpointInfo health =
                HealthEndpoint.class.getAnnotation(EndpointInfo.class);
        EndpointInfo users =
                UserEndpoint.class.getAnnotation(EndpointInfo.class);

        System.out.println(health.path() + " " + health.method()
                + " " + Arrays.toString(health.successCodes()));
        System.out.println(users.path() + " " + users.method()
                + " " + Arrays.toString(users.successCodes()));
    }
}
```

Biên dịch và chạy ở thư mục chứa file:

```bash
javac AnnotationSyntaxDemo.java
java AnnotationSyntaxDemo
```

Kết quả chuẩn:

```text
/health GET [200]
/users POST [201, 202]
```

Giải thích: `path` là bắt buộc, còn `method` và `successCodes` có `default` nên `HealthEndpoint` chỉ truyền `path`. `UserEndpoint` truyền đủ ba tên và đúng kiểu. `@Retention(RetentionPolicy.RUNTIME)` chỉ phục vụ việc đọc bằng reflection trong ví dụ; **annotation không cần RUNTIME retention để compiler kiểm tra cú pháp, tên và phần tử bắt buộc**.

## 10. Cách đọc lỗi `javac` có hệ thống

Với mã Java có lỗi, lưu **mỗi tình huống sai** trong một file riêng để lỗi trước đó không che khuất lỗi bạn đang học. Ví dụ file `MissingAction.java`:

```java
@interface AuditAction {
    String action();
    int level() default 1;
}

@AuditAction(level = 2)
class MissingAction {}
```

Chạy:

```bash
javac MissingAction.java
```

Lệnh phải **biên dịch thất bại** vì không cung cấp `action`. Phần diễn đạt chính xác của thông báo có thể khác giữa các bản JDK; không cần thuộc nguyên văn. Điều cần xác định là annotation `AuditAction` yêu cầu `action()` không có `default`. Sau khi sửa thành `@AuditAction(action = "update", level = 2)`, chạy lại `javac MissingAction.java` sẽ biên dịch thành công.

Một quy trình chẩn đoán ngắn gọn:

1. **Khoanh vùng:** đọc vị trí file/dòng và dấu `^` mà `javac` chỉ ra; kiểm tra token ngay trước và sau vị trí đó.
2. **Kiểm tra cặp dấu:** `@`, `(`/`)`, `=`, dấu phẩy giữa cặp, `;` ở khai báo và `{`/`}` khi truyền mảng.
3. **Mở khai báo `@interface`:** đối chiếu *đúng chính tả và hoa/thường* mọi tên nằm trái `=`; xác định tên nào không được khai báo.
4. **Đánh dấu phần tử bắt buộc:** phần tử nào không có `default` thì nơi sử dụng phải truyền, trừ trường hợp được cung cấp qua cách viết tắt `value`.
5. **So kiểu:** giá trị phải khớp kiểu trả về của phần tử; với primitive/`String` còn cần constant expression.
6. **Biên dịch lại:** sửa lỗi gốc trước rồi chạy `javac` lại; một token sai có thể kéo theo nhiều thông báo phụ.

Có thể dùng `javac -Xdiags:verbose MissingAction.java` để xem chẩn đoán chi tiết hơn khi cần. Nếu thông báo là `annotation type not applicable to this kind of declaration`, đó là vấn đề **vị trí áp dụng theo `@Target`**, không phải do thiếu phần tử hay tên phần tử sai. Nếu thông báo là `cannot find symbol` cho chính tên annotation, kiểm tra khai báo/import/package thay vì sửa danh sách phần tử.

## 11. Checklist trước khi hoàn tất

- Annotation type bắt đầu bằng `@interface`; từng phần tử có dạng `Kiểu ten()`, tùy chọn `default giaTri`, và kết thúc bằng `;`.
- Tên phần tử là Java identifier hợp lệ, không trùng từ khóa và được viết đúng hoa/thường ở nơi sử dụng.
- Mỗi tên `name = value` chỉ xuất hiện một lần và thực sự được khai báo trong annotation type.
- Các phần tử không có `default` đều đã được cung cấp; không giả định có `null` hoặc giá trị mặc định ngầm.
- Chỉ phần tử mang tên `value()` được dùng dạng viết tắt `@Annotation(giaTri)`.
- Dấu ngoặc, dấu `=` và dấu phẩy đầy đủ; giá trị đúng kiểu và đúng quy tắc hằng của annotation.
- Đọc lỗi theo nguyên nhân: **cú pháp**, **thiếu phần tử**, **tên**, **kiểu/giá trị** hoặc **vị trí áp dụng**; xác nhận bằng cách biên dịch lại.

Nắm được hai phía `@interface` (định nghĩa hợp đồng) và `@Annotation(...)` (cung cấp giá trị theo hợp đồng) sẽ giúp nhận biết chính xác các lỗi này, kể cả khi một lần biên dịch xuất hiện nhiều thông báo.