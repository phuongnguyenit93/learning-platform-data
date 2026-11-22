# Annotation thông thường với các cặp tên–giá trị trong Java

Trong Java, annotation có thể mang **metadata** qua các cặp tên–giá trị, viết trong dấu ngoặc tròn sau tên annotation. Cú pháp này thường dùng khi annotation cần mô tả nhiều thuộc tính: đường dẫn API, thời gian chờ, mức ưu tiên, tên cột, v.v. Phần này tập trung vào **cách khai báo element của annotation và cách truyền nhiều cặp `ten = giaTri` khi sử dụng**; các giá trị phải tuân thủ quy tắc của Java tại thời điểm biên dịch.

## 1. Dạng cú pháp

```java
@TenAnnotation(tenElement1 = giaTri1, tenElement2 = giaTri2)
```

- `TenAnnotation` là kiểu annotation đã được định nghĩa bằng `@interface`, hoặc kiểu annotation cung cấp sẵn trong thư viện.
- `tenElement1`, `tenElement2` phải khớp **chính xác** với tên element được khai báo trong kiểu annotation.
- Dấu `=` gắn giá trị cho element; dấu phẩy `,` ngăn cách các cặp. Không dùng `:` kiểu JSON.
- Mỗi element được chỉ định tối đa **một lần** trong một lần áp dụng annotation; thứ tự các cặp có thể thay đổi.
- Giá trị phải đúng kiểu element. Element không có `default` phải được cung cấp, trừ khi không có cách dùng hợp lệ nào khác.

Ví dụ annotation chuẩn từ JDK:

```java
@Deprecated(since = "17", forRemoval = false)
public void oldMethod() {
}
```

Ở đây `since` nhận `String`, `forRemoval` nhận `boolean`. `@Deprecated` cung cấp thông tin cho compiler và công cụ phát triển; bản thân annotation không ngăn phương thức được gọi.

## 2. Tự định nghĩa và áp dụng một annotation nhiều element

Một **element** trong khai báo `@interface` trông giống phương thức không tham số, không có thân hàm. Giá trị mặc định đặt sau `default`.

Tạo file `AnnotationPairsDemo.java` với toàn bộ mã sau:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface ApiRoute {
    String path();                   // Bắt buộc truyền giá trị
    String method() default "GET";  // Không truyền thì dùng "GET"
    int timeoutMs() default 1000;   // Không truyền thì dùng 1000
}

@ApiRoute(path = "/products", method = "POST", timeoutMs = 1500)
class ProductResource {
}

public class AnnotationPairsDemo {
    public static void main(String[] args) {
        ApiRoute route = ProductResource.class.getAnnotation(ApiRoute.class);

        System.out.println("path=" + route.path());
        System.out.println("method=" + route.method());
        System.out.println("timeoutMs=" + route.timeoutMs());
    }
}
```

Biên dịch và chạy với Java 17 trở lên trong thư mục chứa file:

```bash
javac -encoding UTF-8 AnnotationPairsDemo.java
java AnnotationPairsDemo
```

Kết quả `stdout`:

```text
path=/products
method=POST
timeoutMs=1500
```

Giải thích cơ chế:

1. `@interface ApiRoute` định nghĩa ba element tên `path`, `method`, `timeoutMs`; tên cặp bên phải `@ApiRoute(...)` phải trùng với ba tên này.
2. `@ApiRoute(path = "/products", method = "POST", timeoutMs = 1500)` gắn **giá trị cụ thể** vào class `ProductResource`. Việc xuống dòng hay đổi thứ tự các cặp không ảnh hưởng cách gán.
3. `@Target(ElementType.TYPE)` cho phép gắn `ApiRoute` lên khai báo kiểu (trong ví dụ là một class). Không thể tùy ý đặt nó lên nơi mà `@Target` cấm.
4. `@Retention(RetentionPolicy.RUNTIME)` giữ annotation đến runtime; `getAnnotation(ApiRoute.class)` lấy metadata phản ánh trên class.
5. `route.path()` và các lời gọi khác đọc **element của annotation**, không phải gọi phương thức nghiệp vụ của `ProductResource`.

Tên `method` ở đây chỉ là tên element `String` do chương trình tự định nghĩa. Java không biến `"POST"` thành HTTP endpoint. Framework hoặc code ứng dụng cần đọc metadata rồi tự thực hiện đăng ký và xử lý route.

## 3. Element bắt buộc và giá trị mặc định

Trong `ApiRoute`, `path()` không có `default`, nên phải cung cấp trong mọi chỗ sử dụng. Hai element còn lại có giá trị mặc định. Vì vậy mẫu sau hợp lệ:

```java
@ApiRoute(path = "/items")
class ItemResource {
}
```

Khi đọc `ApiRoute` trên `ItemResource`, `path()` trả về `"/items"`, `method()` trả `"GET"` và `timeoutMs()` trả `1000`. Giá trị mặc định được khai báo ở **kiểu annotation**, chứ không cần viết ở mỗi chỗ áp dụng.

Các ví dụ sau là **những trường hợp riêng biệt không biên dịch được**:

```java
@ApiRoute                       // Thiếu path bắt buộc
@ApiRoute(method = "POST")      // Thiếu path
@ApiRoute(path = 123)           // path() yêu cầu String
@ApiRoute(path = "/", verb = "POST")  // Không có element verb()
@ApiRoute(path = "/a", path = "/b")   // Gán trùng element path
```

Nếu muốn đổi thứ tự, chỉ việc giữ đủ tên và giá trị:

```java
@ApiRoute(timeoutMs = 2000, path = "/orders", method = "PUT")
class OrderResource {
}
```

`default` là cú pháp dành cho **khai báo** kiểu annotation. Khi **sử dụng**, ta viết `ten = giaTri`, không viết `default`.

## 4. Những kiểu giá trị được Java cho phép

Kiểu trả về của một element annotation chỉ được thuộc các nhóm: kiểu nguyên thủy (`int`, `boolean`, ...), `String`, `Class` (kể cả `Class<?>`), một kiểu `enum`, một kiểu annotation khác hoặc **mảng một chiều** của các kiểu đó. Ví dụ các nhóm thường gặp:

| Kiểu element | Giá trị hợp lệ |
| --- | --- |
| `int priority()` | `priority = 2` |
| `boolean enabled()` | `enabled = true` |
| `String name()` | `name = "core"` |
| `Class<?> type()` | `type = String.class` |
| `Severity level()` | `level = Severity.WARNING` |
| `String[] tags()` | `tags = {"java", "core"}` |

Minh họa độc lập về cú pháp khai báo và gán giá trị (đoạn này không có `main`):

```java
enum Severity {
    INFO, WARNING
}

@interface Meta {
    String[] tags() default {};
    Class<?> targetType() default Object.class;
    Severity severity() default Severity.INFO;
    int priority() default 1;
}

@Meta(
    tags = {"java", "annotation"},
    targetType = String.class,
    severity = Severity.WARNING,
    priority = 2
)
class AnnotatedExample {
}
```

Các giá trị lần lượt là mảng `String`, class literal, hằng enum và số nguyên. Không thể khai báo element kiểu `List<String>`, `Map<String, String>`, đối tượng POJO tùy ý hoặc mảng hai chiều `String[][]`; cũng không thể dùng `null` làm giá trị element.

## 5. Trường hợp đặc biệt của element tên `value`

Nếu kiểu annotation có element tên đúng là `value`, có thể **bỏ tên và dấu `=`** khi chỉ truyền element đó:

```java
@interface Label {
    String value();
    int weight() default 1;
}

@Label("core")  // Tương đương @Label(value = "core")
class CoreTopic {
}

@Label(value = "advanced", weight = 2)
class AdvancedTopic {
}
```

Ở lần sử dụng `AdvancedTopic`, vì cần truyền cả `value` và `weight` nên phải dùng cú pháp các **cặp tên–giá trị đầy đủ**. `@Label("advanced", weight = 2)` là sai cú pháp Java.

`value` không phải tên bắt buộc cho mọi annotation: kiểu `ApiRoute` không có element `value` nên `@ApiRoute("/items")` **không hợp lệ**; phải dùng `@ApiRoute(path = "/items")`.

Ví dụ quen thuộc trong JDK: `@SuppressWarnings("unchecked")` tương đương `@SuppressWarnings(value = "unchecked")`, bởi `SuppressWarnings` khai báo một element `value()` kiểu `String[]`.

## 6. Element kiểu mảng

Mảng thường được viết trong `{}` với các phần tử cách nhau bởi dấu phẩy:

```java
@Meta(tags = {"core", "reflection"})
class MultipleTags {
}
```

Với **một** phần tử, Java cho phép bỏ cặp ngoặc nhọn ở giá trị của element mảng:

```java
@Meta(tags = "core")  // Tương đương tags = {"core"}
class OneTag {
}
```

Mảng rỗng viết `tags = {}`. Vì ví dụ `Meta` khai báo `tags() default {}`, cũng có thể bỏ `tags` để nhận mặc định mảng rỗng. Việc bỏ `{}` cho một phần tử không thay đổi kiểu đã khai báo: `tags()` vẫn trả về `String[]`.

## 7. Biểu thức hằng và giá trị xác định khi biên dịch

Giá trị element kiểu nguyên thủy hoặc `String` phải là **biểu thức hằng tương thích tại compile time**. Có thể dùng hằng `static final` được khởi tạo bởi biểu thức hằng:

```java
final class ApiPaths {
    static final String PRODUCTS = "/products";
}

@ApiRoute(path = ApiPaths.PRODUCTS)
class ConstantPathResource {
}
```

`ApiPaths.PRODUCTS` là một constant variable hợp lệ. Ngược lại, cách viết sau không biên dịch vì gọi hàm chỉ cho ra kết quả khi chương trình chạy:

```java
@ApiRoute(path = System.getenv("API_PATH"))  // Không phải hằng compile time
class RuntimePathResource {
}
```

Với element `Class<?>`, dùng class literal như `String.class`; với enum dùng hằng enum trực tiếp như `Severity.INFO`; với annotation lồng dùng một annotation literal phù hợp. Không dùng `new String(...)`, một giá trị từ request, biến cấu hình runtime hoặc `null` làm giá trị annotation.

Compiler kiểm tra tên element, tên lặp, kiểu giá trị và element bắt buộc ngay trong quá trình biên dịch; điều này giúp nhận diện cấu hình sai sớm.

## 8. Annotation không tự tạo hành vi

Có ba mức retention phổ biến:

- `RetentionPolicy.SOURCE`: chỉ tồn tại trong mã nguồn; không lưu trong file `.class`.
- `RetentionPolicy.CLASS`: được lưu trong `.class` nhưng reflection thông thường không đọc được ở runtime. Đây là mức mặc định nếu không khai báo `@Retention`.
- `RetentionPolicy.RUNTIME`: có thể lấy qua reflection tại runtime, như trong `AnnotationPairsDemo`.

Annotation processor có thể xử lý metadata lúc biên dịch; thư viện hoặc framework có thể xử lý metadata runtime nếu phù hợp. `@Target` quyết định những **vị trí** annotation có thể được đặt, còn các cặp tên–giá trị mô tả **dữ liệu** mà annotation mang theo. Hai vấn đề này độc lập.

Một class mang `@ApiRoute` vẫn là class Java bình thường; nếu không có code xử lý annotation, các cặp `path`, `method`, `timeoutMs` không tự kích hoạt routing, timeout hay xử lý HTTP.

## 9. Các lỗi dễ mắc

| Trường hợp | Cách viết/hiểu đúng |
| --- | --- |
| `@ApiRoute(path: "/x")` | Sử dụng `=`: `@ApiRoute(path = "/x")`. |
| `@ApiRoute("/x")` | Không có element `value()`; dùng `@ApiRoute(path = "/x")`. |
| `@ApiRoute(path = "/x", path = "/y")` | Mỗi element chỉ được gán một lần. |
| `@ApiRoute(path = "/x", timeoutMs = "1000")` | `timeoutMs` là `int`, phải viết `1000`. |
| `@Label("core", weight = 2)` | Viết `@Label(value = "core", weight = 2)`. |
| Dùng `System.getenv(...)` làm giá trị `String` | Dùng biểu thức hằng ở compile time. |
| Bỏ `@Retention(RUNTIME)` rồi đọc bằng reflection | Retention mặc định là `CLASS`; reflection runtime không đọc được. |
| Cho rằng annotation tự chạy nghiệp vụ | Phải có processor/framework/code xử lý metadata. |

**Tự kiểm tra:** `@ApiRoute(path = "/health", timeoutMs = 500)` cung cấp hai cặp, trong đó `path = "/health"`, `timeoutMs = 500`; element `method` nhận mặc định `"GET"`. Đổi thành `@ApiRoute(method = "GET")` sẽ gây lỗi biên dịch vì thiếu `path`. Qua đó có thể thấy **tên element xác định rõ giá trị được truyền**, và Java kiểm tra hợp lệ ngay tại compile time.
