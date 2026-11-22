# Quy tắc phương thức phần tử trong annotation: không tham số, không generic, không `throws`

## 1. Phương thức phần tử là gì?

Trong Java, ta định nghĩa một **loại annotation** bằng cú pháp `@interface`. Các khai báo trông giống phương thức bên trong loại annotation được gọi là **annotation elements** (phần tử annotation). Chúng mô tả **các giá trị metadata** mà người sử dụng có thể khai báo:

```java
@interface TaskInfo {
    String name();
    int priority() default 1;
}
```

`name()` và `priority()` là hai *phương thức phần tử* của `TaskInfo`. Đây là những khai báo không có thân; chúng không tự tính toán dữ liệu, không nhận tham số khi chạy và không phải lời gọi nghiệp vụ thông thường. Tại nơi sử dụng, các giá trị được gắn theo tên phần tử:

```java
@TaskInfo(name = "IMPORT_DATA", priority = 3)
class Example {}
```

Đoạn mã trên **không biên dịch được** nếu chỉ dựa vào khai báo `TaskInfo` vừa nêu với các vị trí dùng hiện tại? **Có, nó biên dịch được**: khi không khai báo `@Target`, annotation được phép xuất hiện trên nhiều loại declaration, bao gồm khai báo lớp. Ví dụ này chỉ minh họa cú pháp; hai đoạn chưa đủ để tạo thành một chương trình chạy độc lập.

Ba ràng buộc then chốt của **khai báo phương thức phần tử** trong `@interface`:

1. **Không tham số**: cặp ngoặc tròn `()` khi khai báo phần tử phải rỗng.
2. **Không generic**: phương thức phần tử không được có tham số kiểu như `<T>`.
3. **Không `throws`**: phương thức phần tử không được khai báo mệnh đề ngoại lệ `throws ...`.

Những hạn chế này là quy tắc cú pháp/ngôn ngữ mà `javac` áp dụng khi biên dịch; không phụ thuộc việc framework có thực sự sử dụng annotation hay không.

## 2. Quy tắc thứ nhất: không nhận tham số

Khai báo đúng:

```java
@interface EndpointInfo {
    String path();
    int timeoutMillis() default 1000;
}
```

Khai báo **sai**:

```java
// KHÔNG HỢP LỆ — ví dụ lỗi biên dịch, đừng đặt chung với chương trình chạy.
@interface BadEndpointInfo {
    String path(String prefix);
}
```

Trong `@interface`, phương thức phần tử không có danh sách tham số hình thức. `String path(String prefix)` có một tham số nên trái quy tắc ngay tại nơi **khai báo loại annotation**. Dù người viết có đặt `prefix` là `String` và không dùng tới, chương trình vẫn không hợp lệ.

Điểm dễ nhầm là **nơi sử dụng annotation có truyền giá trị**, ví dụ:

```java
@EndpointInfo(path = "/tickets", timeoutMillis = 1500)
class TicketEndpoint {}
```

Giá trị `"/tickets"` thuộc **phần tử** `path`, còn `1500` thuộc `timeoutMillis`. Đó là cú pháp khai báo metadata, **không phải gọi** `path("/tickets")` như phương thức nhận tham số. `path()` vẫn được định nghĩa bằng ngoặc tròn rỗng.

Khi đọc annotation bằng Reflection, đối tượng đại diện cho annotation có các phương thức truy xuất không tham số, như `info.path()`. Lời gọi truy xuất ấy chỉ trả về **giá trị metadata đã gắn**, không biến phương thức phần tử thành phương thức nhận đối số.

## 3. Quy tắc thứ hai: phương thức phần tử không được generic

Một *generic method* có danh sách tham số kiểu riêng nằm trước kiểu trả về:

```java
// KHÔNG HỢP LỆ trong annotation type:
@interface BadGenericInfo {
    <T> T data();
}
```

`<T>` khai báo type parameter của một phương thức. Phương thức phần tử annotation **không được có type parameter**, nên `<T> T data();` bị từ chối ngay cả khi phần tử không nhận tham số thường.

Tuy nhiên, **“không generic” không có nghĩa là mọi dấu `<...>` trong kiểu trả về đều bị cấm**. Ví dụ sau là **hợp lệ**:

```java
@interface HandlerInfo {
    Class<?> type();
}
```

`Class<?>` là dạng `Class` được phép làm **kiểu trả về của phần tử annotation**. Nó không khai báo type parameter `<T>` cho phương thức `type()`. Cần phân biệt:

| Cú pháp trong khai báo | Hợp lệ? | Lý do |
| --- | --- | --- |
| `String name();` | Có | Phần tử không tham số, trả về `String` |
| `Class<?> handler();` | Có | Kiểu trả về `Class` với wildcard được Java cho phép |
| `<T> T value();` | Không | Phần tử khai báo type parameter `T` |
| `java.util.List<String> tags();` | Không | `List` không thuộc tập kiểu trả về hợp lệ của phần tử annotation |
| `String[] tags();` | Có | Mảng một chiều của kiểu `String` hợp lệ |

**Kiểu trả về** của phần tử annotation chỉ có thể là kiểu nguyên thủy, `String`, `Class` (kể cả dạng parameterized cho phép), enum, loại annotation khác, hoặc mảng **một chiều** của một trong những loại đó. Không thể dùng `void`, kiểu tham chiếu tùy ý như `Object` hay `List<String>`, hoặc mảng lồng nhau như `String[][]`.

Nếu cần cấu hình một lớp xử lý, khai báo phần tử kiểu `Class<?>` hoặc `Class<? extends SomeHandler>` phù hợp hơn việc cố truyền một instance hoặc một kiểu generic bất kỳ vào annotation. Đó vẫn chỉ là khai báo metadata, chưa tạo đối tượng xử lý.

## 4. Quy tắc thứ ba: không được khai báo `throws`

Khai báo **sai**:

```java
// KHÔNG HỢP LỆ — ví dụ lỗi biên dịch.
@interface BadConfig {
    String config() throws java.io.IOException;
}
```

Một phương thức phần tử annotation không được có *throws clause*. Quy tắc này áp dụng bất kể loại ngoại lệ checked hay unchecked. Vì vậy cả `throws IOException` lẫn `throws RuntimeException` đều không hợp lệ trong khai báo phần tử.

Khai báo đúng là:

```java
@interface Config {
    String location();
}
```

Lý do về thiết kế: phần tử annotation biểu diễn một **giá trị metadata được xác định khi biên dịch**, không phải một thao tác đọc file, gọi API hoặc xử lý nghiệp vụ có thể thất bại. Java vì thế giới hạn loại phần tử và cú pháp khai báo; mã xử lý metadata nằm ở bên khác.

Ví dụ cần đọc file cấu hình có thể tổ chức như sau:

```java
// Chỉ là ví dụ khai báo/sử dụng, không phải chương trình hoàn chỉnh.
@interface ConfigLocation {
    String value();
}

@ConfigLocation("config/app.properties")
class ApplicationConfig {}
```

`value()` chứa đường dẫn hằng `"config/app.properties"`. Một **consumer** riêng dùng metadata này để mở file; chính phương thức đọc file ở consumer mới có thể xử lý hoặc khai báo `IOException`. Không khai báo `throws` trên `value()`.

Một sắc thái quan trọng: **“không có `throws` ở khai báo” không có nghĩa mọi thao tác Reflection đọc annotation đều tuyệt đối không thể lỗi**. Ví dụ, trong các tình huống annotation/class thay đổi không tương thích, API Reflection có thể phát sinh các lỗi runtime liên quan tới metadata. Quy tắc của đề bài chỉ giới hạn *cú pháp phương thức phần tử*, không phải bảo đảm mọi hệ thống xử lý annotation đều không lỗi.

## 5. Ví dụ Java 17+ đầy đủ, biên dịch và chạy độc lập

Đặt toàn bộ nội dung dưới đây vào tệp **`AnnotationElementRulesDemo.java`**. Chỉ cần JDK 17+; annotation, nơi dùng và mã đọc metadata đều ở cùng một tệp để dễ thử.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface JobInfo {
    String name();                         // Không tham số
    int maxRetries() default 0;            // Giá trị mặc định
    Class<?> handlerType() default Object.class; // Class<?> hợp lệ
}

class JobService {
    @JobInfo(
        name = "SYNC_DATA",
        maxRetries = 2,
        handlerType = String.class
    )
    public void sync() {}

    @JobInfo(name = "AUDIT")
    public void audit() {}
}

public class AnnotationElementRulesDemo {
    public static void main(String[] args)
            throws NoSuchMethodException {
        printInfo(JobService.class.getDeclaredMethod("sync"));
        printInfo(JobService.class.getDeclaredMethod("audit"));
    }

    private static void printInfo(Method method) {
        JobInfo info = method.getAnnotation(JobInfo.class);

        System.out.printf(
            "%s: name=%s, maxRetries=%d, handlerType=%s%n",
            method.getName(),
            info.name(),
            info.maxRetries(),
            info.handlerType().getSimpleName()
        );
    }
}
```

Chạy ở thư mục chứa tệp:

```bash
javac -encoding UTF-8 AnnotationElementRulesDemo.java
java AnnotationElementRulesDemo
```

**Standard output (stdout):**

```text
sync: name=SYNC_DATA, maxRetries=2, handlerType=String
audit: name=AUDIT, maxRetries=0, handlerType=Object
```

### Giải thích chi tiết

- **Khai báo**: `JobInfo` có ba phần tử `name()`, `maxRetries()` và `handlerType()`. Chúng đều không nhận tham số, không định nghĩa type parameter và không có `throws`. Mỗi phần tử có kiểu trả về hợp lệ.
- **Giá trị mặc định**: `maxRetries() default 0` và `handlerType() default Object.class` cho phép nơi sử dụng bỏ qua hai phần tử này. Từ khóa `default` trong trường hợp này chỉ khai báo **giá trị mặc định của phần tử annotation**; đừng nhầm với **default method có thân** trong một interface thông thường.
- **Sử dụng**: `sync()` chỉ định cả ba phần tử. `audit()` chỉ cung cấp `name` (phần tử bắt buộc); `maxRetries` và `handlerType` nhận giá trị mặc định.
- **Retention**: `@Retention(RUNTIME)` cho phép đọc `JobInfo` bằng Reflection trong lúc chạy.
- **Xử lý**: `getDeclaredMethod(...)` lấy đối tượng `Method`, sau đó `getAnnotation(JobInfo.class)` lấy annotation đã gắn. Các lời gọi `info.name()`, `info.maxRetries()`, `info.handlerType()` **không truyền tham số** và trả về metadata.
- **Kết quả**: `String.class.getSimpleName()` là `String`; `Object.class.getSimpleName()` là `Object`. Chương trình không gọi `sync()` hay `audit()`; kết quả được in bởi `printInfo`, không phải do annotation tự động thực thi công việc.

Ví dụ biết trước cả hai phương thức đều có `@JobInfo` nên không cần nhánh `null`. Trong consumer tổng quát, hãy kiểm tra kết quả `getAnnotation(...)` vì nó có thể trả về `null` nếu annotation vắng mặt hoặc không được lưu đến runtime.

### Phân biệt ba chữ “phương thức” trong ví dụ

| Vị trí | Cú pháp | Ý nghĩa |
| --- | --- | --- |
| Phương thức phần tử | `String name();` bên trong `@interface` | Khai báo khóa metadata, không có thân và không tham số |
| Phương thức nghiệp vụ | `public void sync() {}` bên trong `JobService` | Phương thức Java bình thường có thể có mã thực thi |
| Phương thức của consumer | `printInfo(Method method)` | Phương thức Java bình thường **được phép có tham số, generic hoặc throws** nếu cần |

Ràng buộc “không tham số, không generic, không `throws`” áp dụng **riêng cho phương thức phần tử bên trong khai báo loại annotation**. Nó **không cấm** phương thức thông thường được annotation gắn lên nhận tham số, định nghĩa generic hay khai báo `throws`, miễn vị trí gắn phù hợp với `@Target`.

## 6. Những ràng buộc liên quan cần biết khi khai báo phần tử

Dù ba quy tắc của bài là trọng tâm, để viết `@interface` thực tế bạn cũng cần nắm những điều đi kèm:

**Không có thân phương thức.** Phần tử annotation có dạng khai báo kết thúc bằng dấu `;`, không chứa khối `{ ... }` và không được viết thành một phương thức `default` có thân như trong interface thông thường:

```java
// KHÔNG HỢP LỆ — không viết thân cho phần tử.
@interface BadBody {
    String value() { return "x"; }
}
```

**Không được bỏ cặp ngoặc tròn trong phần khai báo.** Dù không có tham số, viết `String value();`, không phải `String value;`. Dạng thứ hai không còn là khai báo phần tử đúng quy cách.

**Phân biệt default value với xử lý runtime.** `int retries() default 3;` hợp lệ và trả về số `3` nếu nơi dùng không chỉ định; nhưng `default` không gắn logic “thử lại ba lần”. Chỉ consumer hiểu `retries` mới có thể tổ chức retry, và nó phải định nghĩa khi nào retry, cách báo lỗi và giới hạn thích hợp.

**Giá trị ở nơi sử dụng phải là giá trị hợp lệ tại compile-time.** Chẳng hạn `@JobInfo(name = "SYNC_DATA")` hợp lệ; không thể lấy `name` từ một chuỗi vừa đọc qua HTTP vào lúc runtime. Ngoài ra, không được gán `null` làm giá trị phần tử annotation.

**Kiểu array được phép là một chiều.** Ví dụ:

```java
@interface Labels {
    String[] value();
}

@Labels({"java", "annotation"})
class Notes {}
```

Ngược lại, `String[][] value();` không phải kiểu phần tử hợp lệ.

Những ràng buộc này giúp compiler xác nhận metadata có cấu trúc ổn định và có thể mã hóa vào thông tin annotation. Chúng cũng giúp bên xử lý biết trước tên và kiểu dữ liệu khi đọc.

## 7. So sánh lỗi tại nơi khai báo với lỗi tại nơi sử dụng

**Lỗi tại nơi khai báo loại annotation** (compiler từ chối ngay):

```java
// MỖI KHAI BÁO SAU ĐỀU KHÔNG HỢP LỆ.
// Các ví dụ độc lập về lỗi; không biên dịch thành chương trình mẫu.
@interface WithParameter {
    String key(int index);          // Có tham số
}

@interface WithTypeParameter {
    <T> T key();                     // Có type parameter
}

@interface WithThrows {
    String key() throws Exception;  // Có throws clause
}
```

**Lỗi tại nơi sử dụng** (loại annotation có thể hợp lệ, nhưng cách gắn không hợp lệ):

```java
// Loại annotation được khai báo đúng.
@interface RequestInfo {
    String route();
    int priority() default 0;
}

// KHÔNG HỢP LỆ: thiếu phần tử route() không có default.
@RequestInfo
class MissingRequired {}

// KHÔNG HỢP LỆ: phần tử priority yêu cầu int.
@RequestInfo(route = "/orders", priority = "high")
class WrongType {}
```

Lỗi khai báo là vấn đề **định nghĩa phần tử**; lỗi sử dụng là vấn đề **giá trị mà người sử dụng gán cho phần tử**. Hai loại được compiler phát hiện trước lúc chương trình chạy. Trong khi đó, việc annotation có tạo ra hành vi nghiệp vụ nào hay không là trách nhiệm của **consumer** và nằm ngoài ba hạn chế cú pháp đang xét.

## 8. Bài tập tự kiểm tra

**Câu 1.** Tại sao `String code();` hợp lệ nhưng `String code(int language);` không hợp lệ bên trong `@interface`?

**Đáp án:** phần tử annotation phải khai báo **không có tham số hình thức**; người sử dụng cung cấp metadata bằng `@Annotation(code = "VI")` chứ không gọi `code("VI")`.

**Câu 2.** `Class<?> implementation();` có vi phạm quy tắc “không generic” không?

**Đáp án:** không. Phần tử không có *method type parameters*; `Class<?>` là kiểu trả về đặc biệt được cho phép. Ngược lại `<T> Class<T> implementation();` là phương thức generic nên không hợp lệ.

**Câu 3.** Nếu muốn đọc file có thể ném `IOException` khi xử lý `@ConfigLocation("app.properties")`, nên khai báo `throws IOException` ở đâu?

**Đáp án:** trong phương thức **consumer đọc file**, nếu phương thức đó lựa chọn truyền ngoại lệ ra ngoài. Không được khai báo `throws` trên phương thức phần tử của `@interface`.

**Câu 4.** Đọc ví dụ `AnnotationElementRulesDemo.java`: vì sao `audit()` in `maxRetries=0` và `handlerType=Object`?

**Đáp án:** vì nơi sử dụng chỉ cung cấp `name`; hai phần tử còn lại được định nghĩa với giá trị mặc định ở nơi khai báo annotation.

**Câu 5.** Phương thức nghiệp vụ `public <T> T convert(T value) throws IOException` có thể được gắn annotation hợp lệ không?

**Đáp án:** có thể, nếu annotation cho phép `METHOD` (hoặc không có hạn chế `@Target` ngăn vị trí ấy) và việc gắn đáp ứng các quy tắc khác. Ba ràng buộc của bài **áp dụng cho phương thức phần tử của `@interface`**, không phải cho mọi phương thức được gắn annotation.

Khi đọc một annotation type, hãy nhận diện **các phần tử khai báo metadata**, kiểm tra chúng có `()` rỗng, không có `<T>` của phương thức và không có `throws`. Các hành vi có xử lý tham số, generic hoặc ngoại lệ phải nằm ở mã nghiệp vụ hay consumer thích hợp.
