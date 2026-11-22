# Viết tài liệu cho annotation: ý nghĩa, phần tử và giá trị mặc định trong Java

Một annotation chỉ thực sự dễ sử dụng khi người đọc hiểu **nó biểu đạt điều gì, được gắn ở đâu, mỗi phần tử (element) có ý nghĩa thế nào và điều gì xảy ra khi bỏ qua một phần tử có giá trị mặc định**. Cú pháp `@interface` cho biết hình dạng dữ liệu; Javadoc giải thích *hợp đồng* của metadata ấy.

Ví dụ ngắn:

```java
/**
 * Khai báo chính sách gọi lại khi thao tác gặp lỗi có thể thử lại.
 *
 * <p>Annotation chỉ mang cấu hình; bộ xử lý chính sách phải tự đọc
 * metadata và quyết định cách thực hiện.</p>
 *
 * @since 1.0
 */
@interface RetryPolicy {
    /**
     * Số lần thử lại tối đa sau lần gọi đầu tiên.
     *
     * @return số lần thử lại, không âm
     */
    int maxRetries() default 2;
}
```

Với định nghĩa này, `@RetryPolicy` hoặc `@RetryPolicy(maxRetries = 2)` biểu đạt cùng **giá trị phần tử**. Nhưng **không có cơ chế tự động thử lại** chỉ vì annotation tồn tại. Code hoặc framework tiêu thụ nó mới có thể thực hiện hành vi đó.

Bài học tập trung vào cách **viết và duy trì tài liệu API của annotation**, cùng những khác biệt giữa Javadoc, cú pháp `default`, và `@Documented`.

## 1. Những điều tài liệu annotation cần nói rõ

Khi thiết kế một annotation tự định nghĩa, hãy xem nó như một giao diện cấu hình nhỏ dành cho trình biên dịch, công cụ phân tích hoặc framework.

Tài liệu tốt thường trả lời sáu câu hỏi:

1. **Ý nghĩa:** Annotation đại diện cho quy tắc hoặc dữ kiện gì? Ví dụ “đánh dấu method có thể được retry”, không đơn thuần “retry annotation”.
2. **Phạm vi áp dụng:** Nên gắn trên class, field, method, constructor, parameter hay type-use? Những giới hạn nào được `@Target` thực thi?
3. **Đơn vị xử lý:** Ai đọc annotation và vào thời điểm nào? Chỉ lúc biên dịch, lúc tạo cấu hình hay trong quá trình chạy?
4. **Hợp đồng từng phần tử:** Giá trị đại diện cho điều gì, có đơn vị đo/ràng buộc gì và mối quan hệ với phần tử khác ra sao?
5. **Giá trị mặc định:** Khi người dùng không truyền một phần tử thì giá trị nào có hiệu lực? Giá trị mặc định có an toàn cho đa số trường hợp không?
6. **Tương thích và thay đổi:** Điều gì xảy ra nếu đổi giá trị mặc định, thêm element hoặc thay thế annotation qua các phiên bản thư viện?

Đây là các câu hỏi dành cho người sử dụng annotation. Không nên chỉ kể lại dòng code; hãy ghi những giả định mà người gọi **không thể suy ra chắc chắn** từ tên và kiểu Java.

## 2. Javadoc trên chính annotation type

Javadoc của annotation type viết **ngay trước khai báo `@interface`**, giống tài liệu của class hoặc interface:

```java
/**
 * Đánh dấu method có thể được một bộ xử lý retry thực hiện lại
 * khi nhận lỗi tạm thời.
 *
 * <p>Chỉ có tác dụng nếu ứng dụng đã cấu hình bộ xử lý đọc annotation.
 * Không dùng cho thao tác có tác dụng phụ không thể lặp an toàn.</p>
 *
 * @since 1.0
 * @see java.lang.annotation.Target
 */
@interface Retryable {
    int attempts() default 2;
}
```

Đoạn này **minh họa annotation type**; nó biên dịch được khi đặt vào một tệp Java phù hợp. Những phần tài liệu có giá trị:

- **Câu đầu tiên** tóm tắt ý nghĩa: dùng làm summary cho API Javadoc.
- **Đoạn tiếp theo** mô tả ràng buộc và giới hạn, đặc biệt những điều không được Java tự bảo đảm.
- **`@since` trong Javadoc** nêu phiên bản API được giới thiệu.
- **`@see`** liên kết với tài liệu liên quan; khi có kiểu thay thế hoặc công cụ xử lý, nên trỏ đúng tới đối tượng đó.
- Có thể dùng `{@link SomeType}`, `{@code retry}` và các inline tag khác để tạo liên kết/định dạng trong trang tài liệu.

Các thẻ `@since`, `@see`, `{@link ...}` là **cú pháp Javadoc**, không phải annotation Java được reflection đọc.

**Quy tắc đặt tên:** tên `Retryable` cho thấy ý đồ khái quát; đoạn Javadoc phải làm rõ “retry” áp dụng với lỗi nào, số lần tính ra sao và ai xử lý. Một tên đẹp không thay được hợp đồng thực tế.

## 3. Viết Javadoc cho từng annotation element

Trong thân `@interface`, mỗi khai báo dạng `Type name();` là một **annotation element**, có thể có phần `default ...`. Mỗi element đáng được mô tả riêng như thành phần của API.

Ví dụ:

```java
/**
 * Cấu hình chính sách retry cho method.
 */
@interface RetryPolicy {
    /**
     * Số lần gọi lại tối đa sau lần thử đầu tiên.
     *
     * <p>0 nghĩa là chỉ gọi một lần và không retry.</p>
     *
     * @return số lần retry; giá trị hợp lệ từ 0 đến 5
     */
    int retries() default 2;

    /**
     * Thời gian chờ giữa hai lần thử lại, tính bằng mili giây.
     *
     * @return khoảng chờ không âm, đơn vị mili giây
     */
    long delayMillis() default 100L;

    /**
     * Mã chính sách, dùng để đối chiếu với cấu hình ứng dụng.
     *
     * @return mã không rỗng do bên sử dụng cung cấp
     */
    String policyId();
}
```

Đoạn này chỉ là **khai báo ví dụ**. Mỗi `@return` trong Javadoc diễn giải **giá trị mà accessor của annotation trả về**; nó không thực thi kiểm tra. Java cho phép tạo giá trị `retries = -1` vì kiểu `int` chấp nhận số âm. Nếu thực sự cần giới hạn `0..5`, một annotation processor hoặc runtime consumer phải kiểm tra và từ chối giá trị sai.

Nên ghi rõ:

| Loại thông tin | Ví dụ trong Javadoc | Vì sao cần |
| --- | --- | --- |
| Ý nghĩa | “Số lần retry **sau** lần gọi đầu tiên” | Tránh nhầm tổng số lần gọi với số lần thử lại |
| Đơn vị | “mili giây” thay vì “khoảng chờ” | Tránh truyền giây vào giá trị tính bằng ms |
| Miền giá trị | “không âm; 0 là tắt retry” | Giúp người dùng tránh cấu hình vô nghĩa |
| Trường hợp mặc định | “Mặc định 2 lần thử lại” | Người dùng hiểu điều gì xảy ra khi bỏ qua |
| Tác dụng với hệ thống | “Chỉ hoạt động khi có RetryProcessor” | Không tạo kỳ vọng annotation tự chạy |
| Thay đổi tương thích | “Đổi giá trị này có thể thay đổi hành vi runtime” | Giúp duy trì thư viện an toàn |

Với element là `Class<?>`, hãy mô tả class token này chỉ ra loại nào và sẽ được khởi tạo hay chỉ được kiểm tra. Với element là enum, hãy giải thích ý nghĩa mỗi lựa chọn. Với mảng, nêu rõ thứ tự có quan trọng không, mảng rỗng có nghĩa gì, và có chấp nhận trùng lặp không. Không thể chỉ dựa vào `String[]` để biết các quy tắc này.

### Không dùng @param cho element không có tham số

Annotation element phải có danh sách tham số trống: `String name();`. Vì thế, thông thường **không có `@param`** để mô tả đầu vào của element. Dùng phần mô tả và `@return` để giải thích giá trị. Đây là khác biệt so với method thông thường như `void execute(String name)`.

Annotation element **không phải default method của interface**: trong `int retries() default 2;`, từ khóa `default` khai báo **giá trị annotation mặc định**, không gắn thân thực thi cho method.

## 4. Giá trị mặc định có ngữ nghĩa như thế nào?

Các element **không có `default`** là bắt buộc phải có giá trị trong mỗi lần sử dụng annotation (trừ những trường hợp kiểu annotation không cần khai báo element đó). Các element **có `default`** có thể được bỏ qua tại vị trí sử dụng; khi truy cập, giá trị mặc định được áp dụng.

```java
@interface RequestConfig {
    String path();                     // Bắt buộc.
    int timeoutMillis() default 1000;  // Tùy chọn.
    boolean audit() default false;     // Tùy chọn.
}

@RequestConfig(path = "/orders")
class OrderResource {}

@RequestConfig(path = "/payments", timeoutMillis = 2500, audit = true)
class PaymentResource {}
```

Đây là **khai báo minh họa**, không phải chương trình độc lập. `OrderResource` có `timeoutMillis() == 1000` và `audit() == false` khi annotation được đọc. `PaymentResource` cung cấp các giá trị tường minh.

Gọi `@RequestConfig` mà không truyền `path` là **lỗi biên dịch**, vì `path()` không có default. Java không suy ra giá trị `""` cho mọi `String` và không suy ra `0` cho mọi `int` khi tác giả annotation chưa khai báo default.

### default nằm trong annotation type, không nằm trên nơi sử dụng

```java
@interface Threshold {
    int value() default 10;
}

// 10 là giá trị hiệu lực từ annotation type.
@Threshold
class DefaultThreshold {}

// 50 được ghi tường minh ở vị trí sử dụng.
@Threshold(50)
class ExplicitThreshold {}
```

Việc dùng cú pháp `@Threshold(50)` là cách viết tắt hợp lệ cho `@Threshold(value = 50)`. Tên element phải là `value`, và các element còn lại (nếu có) phải có default phù hợp để dùng cách viết tắt này.

### Giá trị default không phải null

Giá trị annotation trong Java bị giới hạn theo JLS: primitive, `String`, `Class`, enum, annotation hoặc mảng một chiều của các kiểu hợp lệ. `null` **không phải giá trị hợp lệ** cho annotation element, kể cả element kiểu `String` hay `Class<?>`.

Ví dụ **cố ý sai**:

```java
@interface InvalidName {
    String name() default null; // Lỗi biên dịch.
}
```

Nếu cần biểu đạt “không chỉ định”, hãy thiết kế một giá trị có ý nghĩa và ghi tài liệu cho nó, ví dụ `String description() default "";`, enum `UNKNOWN`, `Class<?> type() default Void.class;` hoặc mảng rỗng `String[] tags() default {};`. Đây là lựa chọn hợp đồng API, **không có sentinel nào phù hợp cho mọi ứng dụng**.

### Giá trị mặc định được áp dụng khi annotation được đọc

JLS §9.6.2 quy định default nằm trong định nghĩa của **annotation type** và được áp dụng động khi giá trị annotation được đọc. Nó không được “chép” thành giá trị tường minh vào từng vị trí sử dụng.

Hệ quả quan trọng đối với tương thích:

- Bản 1.0: `int retries() default 2;`, lớp sử dụng viết `@RetryPolicy` và không khai báo `retries`.
- Bản 2.0: thay định nghĩa thành `int retries() default 5;`.
- Nếu chương trình chạy với bản annotation type mới và lớp sử dụng vẫn chỉ dựa vào default, code đọc annotation có thể thấy **5**, kể cả khi lớp sử dụng được biên dịch từ trước, miễn là các điều kiện tương thích/classpath khác phù hợp.
- Nếu lớp sử dụng viết `@RetryPolicy(retries = 2)` tường minh, việc đổi default của annotation type không tự thay đổi giá trị đã khai báo ấy.

Vì vậy, đổi default có thể là **thay đổi hành vi** dù API vẫn biên dịch được. Đối với annotation điều khiển bảo mật, giao dịch, retry, thời gian chờ, phân quyền hoặc logging, cần đánh giá tương thích trước khi thay giá trị mặc định.

## 5. @Documented dùng để làm gì?

Javadoc có thể mô tả **định nghĩa annotation type** và mỗi element, nhưng một câu hỏi khác là: *khi tạo tài liệu cho class/method đang sử dụng annotation, công cụ có hiển thị chính annotation đó trong hợp đồng công khai của phần tử không?*

Meta-annotation `java.lang.annotation.Documented` có mục đích này:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Khai báo mức ổn định của một API.
 */
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Stability {
    /** @return mã mức ổn định */
    String value();
}

/** API đang được khuyến khích dùng. */
@Stability("stable")
class PublicService {}
```

Đây là **các khai báo minh họa**, chưa có `main`. Khi tạo Javadoc, công cụ như `javadoc` thường hiển thị sự hiện diện và giá trị của `@Stability("stable")` trong tài liệu `PublicService` vì annotation type được đánh dấu `@Documented`.

Nếu bỏ `@Documented`, việc annotation có mặt trong source **không có nghĩa** công cụ mặc định phải thể hiện nó như một phần của hợp đồng tài liệu của `PublicService`. Các công cụ chuyên dụng có thể có quy tắc khác.

### Phân biệt ba trách nhiệm

| Thành phần | Vai trò |
| --- | --- |
| `/** ... */` trên `@interface Stability` | Giải thích **Stability là gì** |
| `/** ... */` trên `String value();` | Giải thích **element value biểu đạt gì** |
| `@Documented` trên `Stability` | Đánh dấu **sự hiện diện và giá trị @Stability tại nơi sử dụng** là thông tin thuộc hợp đồng tài liệu công khai |

`@Documented` không tạo chú thích Javadoc thay người viết; nó cũng không biến element thành logic kiểm tra. `@Documented` không có chức năng kế thừa class, không đồng nghĩa với `@Inherited`, và không khiến annotation được phản chiếu ở runtime nếu retention không phù hợp.

## 6. Kết hợp @Target, @Retention và @Documented khi xuất bản API

Một annotation dùng như cấu hình runtime nên công bố rõ nơi gắn, thời gian lưu và khả năng hiển thị tài liệu:

```java
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface ApiContract {
    String owner();
    boolean experimental() default false;
}
```

Đây là **đoạn minh họa** cần import các meta-annotation tương ứng. Hãy hiểu từng dòng:

- `@Target({TYPE, METHOD})`: compiler giới hạn annotation ở khai báo class/interface/kiểu và method (theo đích cụ thể), không cho tùy tiện gắn trên field.
- `@Retention(RUNTIME)`: annotation có thể được reflection truy xuất lúc chạy qua đối tượng khai báo tương ứng.
- `@Documented`: sự hiện diện của annotation trên API được công cụ tài liệu tiêu chuẩn đưa vào hợp đồng tài liệu theo quy tắc của `@Documented`.
- Javadoc trên `ApiContract` và từng element vẫn cần giải thích ý nghĩa `owner` và `experimental` cùng các giới hạn.

Với annotation chỉ dành cho trình biên dịch, `SOURCE` hoặc `CLASS` retention có thể phù hợp hơn. Không nên bật `RUNTIME` chỉ vì muốn Javadoc đẹp; đây là hai mục tiêu khác nhau.

### Khi nhắc tới kế thừa

`@Inherited` điều khiển cách reflection tìm một **annotation được gắn trên class** dọc superclass hierarchy trong điều kiện phù hợp. Nó không thay thế `@Documented`, không làm annotation trên method tự được sao chép sang override và không khiến Javadoc của một API tự sinh phần giải thích element còn thiếu.

Nếu một annotation cấu hình được kế thừa, tài liệu nên nói rõ **quy tắc kế thừa và cách subclass ghi đè giá trị**. Nếu annotation không có `@Inherited`, không nên tuyên bố nó tự theo subclass, trừ khi một framework chủ động triển khai quy tắc riêng.

## 7. Ví dụ Java 17+ chạy độc lập: ý nghĩa, default và @Documented

Tạo đúng một tệp **`AnnotationDocsDemo.java`** với toàn bộ nội dung sau. Các phần Javadoc minh họa cách tài liệu hóa **annotation type và từng element**, còn đoạn `main` chứng minh default được đọc qua reflection.

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

/** Các mức ưu tiên khi chạy tác vụ. */
enum Priority {
    NORMAL, HIGH
}

/**
 * Cấu hình một tác vụ có thể được bộ xử lý công việc thực thi.
 *
 * <p>Annotation chỉ cung cấp metadata. Bộ xử lý phải tự đọc
 * các giá trị rồi triển khai chính sách thực thi tương ứng.</p>
 *
 * @since 1.0
 */
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface JobPolicy {

    /**
     * Tên logic của tác vụ trong hệ thống.
     *
     * @return tên không rỗng do ứng dụng cung cấp
     */
    String name();

    /**
     * Số lần retry tối đa sau lần thực thi đầu tiên.
     *
     * <p>0 nghĩa là không thử lại.</p>
     *
     * @return số lần retry, không âm; mặc định 2
     */
    int retries() default 2;

    /**
     * Mức ưu tiên của tác vụ.
     *
     * @return mức ưu tiên, mặc định NORMAL
     */
    Priority priority() default Priority.NORMAL;

    /**
     * Nhãn mô tả được hệ thống tra cứu để phân nhóm.
     *
     * @return các nhãn; mảng rỗng nghĩa là không có nhãn
     */
    String[] tags() default {};
}

/** Tác vụ dùng toàn bộ giá trị mặc định ngoại trừ tên. */
@JobPolicy(name = "invoice", tags = {"finance", "daily"})
class InvoiceJob {}

/** Tác vụ ghi đè giá trị mặc định theo hợp đồng của ứng dụng. */
@JobPolicy(name = "alert", retries = 0, priority = Priority.HIGH)
class AlertJob {}

public class AnnotationDocsDemo {

    private static void describe(Class<?> type) {
        JobPolicy config = type.getAnnotation(JobPolicy.class);
        System.out.println(type.getSimpleName()
                + ": name=" + config.name()
                + ", retries=" + config.retries()
                + ", priority=" + config.priority()
                + ", tags=" + String.join(",", config.tags()));
    }

    public static void main(String[] args) throws NoSuchMethodException {
        describe(InvoiceJob.class);
        describe(AlertJob.class);

        Method retriesElement = JobPolicy.class.getDeclaredMethod("retries");
        System.out.println("element-default=" + retriesElement.getDefaultValue());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 AnnotationDocsDemo.java
java AnnotationDocsDemo
```

Stdout chính xác:

```text
InvoiceJob: name=invoice, retries=2, priority=NORMAL, tags=finance,daily
AlertJob: name=alert, retries=0, priority=HIGH, tags=
element-default=2
```

Giải thích:

1. `InvoiceJob` cung cấp `name` bắt buộc, đồng thời gắn nhãn; nó bỏ qua `retries` và `priority`, vì vậy khi đọc được mặc định `2` và `NORMAL`.
2. `AlertJob` chỉ định `retries = 0` và `Priority.HIGH`. Mảng `tags()` mặc định rỗng nên `String.join(",", ...)` trả về chuỗi rỗng; dòng output kết thúc bằng `tags=`.
3. `JobPolicy.class.getDeclaredMethod("retries").getDefaultValue()` trả về **default được định nghĩa trên annotation element**, thay vì lấy giá trị tại một class đang sử dụng.
4. `@Documented` không gây ra bốn dòng output đó. Chính phương thức `describe` và reflection tạo output; `@Documented` dành cho công cụ tài liệu như `javadoc`.

Chương trình không thực thi retry hay lịch ưu tiên. Nếu cần những hành vi đó, ứng dụng phải xây dựng consumer nhận và diễn giải `JobPolicy`.

### Sinh tài liệu HTML

Chạy riêng:

```bash
javadoc -private -encoding UTF-8 -docencoding UTF-8 -d docs AnnotationDocsDemo.java
```

`-private` giúp ví dụ này đưa cả các annotation type/class package-private vào tài liệu. Sau khi lệnh thành công, mở tài liệu HTML được tạo trong thư mục `docs` để xem:

- Trang của `JobPolicy` mô tả ý nghĩa annotation và từng element.
- Phần tử `retries()` có Javadoc `@return` và giá trị default đã được khai báo.
- Tài liệu `InvoiceJob` / `AlertJob` có thể hiển thị `@JobPolicy(...)` ở phần khai báo vì kiểu annotation có `@Documented`.

Các thông báo hoặc warning do lệnh `javadoc` phát ra là **thông tin của công cụ sinh tài liệu**, không thuộc stdout của lệnh `java AnnotationDocsDemo`.

### Một thử nghiệm về default

Nếu đổi `int retries() default 2;` thành `int retries() default 4;` rồi biên dịch/chạy lại:

- `InvoiceJob` sẽ thấy `retries=4` vì nó không ghi số lần retry tường minh.
- `AlertJob` vẫn thấy `retries=0` vì đã chỉ định giá trị tường minh.
- `getDefaultValue()` trên element sẽ trả về `4`.

Đây là thử nghiệm minh họa hành vi của giá trị mặc định. Trong một hệ thống thư viện nhiều phiên bản, việc đổi default cần review cẩn thận vì các client sử dụng giá trị ngầm có thể thay đổi hành vi.

## 8. Cách viết tài liệu tốt hơn cho annotation thực tế

Hãy xét một annotation cấu hình truy cập dữ liệu:

```java
/**
 * Ánh xạ một property tới cột lưu trữ.
 *
 * <p>Chỉ được bộ ánh xạ X sử dụng cho những field mà bộ ánh xạ
 * có quyền đọc. Không tự tạo cột trong cơ sở dữ liệu.</p>
 *
 * @since 1.0
 */
@interface StoredColumn {
    /**
     * Tên cột theo schema hiện tại.
     *
     * @return tên cột không rỗng, phân biệt chữ hoa/thường
     *         theo quy tắc của bộ ánh xạ X
     */
    String name();

    /**
     * Cho phép bộ ánh xạ bỏ qua giá trị chưa được cung cấp.
     *
     * @return true nếu giá trị có thể vắng mặt; mặc định false
     */
    boolean optional() default false;
}
```

Đây là **đoạn minh họa thiết kế**, không đề cập tới một thư viện X cụ thể. Các mô tả “bộ ánh xạ X” chỉ có giá trị nếu thực tế tồn tại consumer với hợp đồng ấy; khi triển khai, phải đổi thành tên và cơ chế thực có.

So với mô tả ngắn `/** Column. */`, người đọc có thêm thông tin:

- Dùng ở đâu và cơ chế xử lý nào đọc metadata.
- Tên cột tuân thủ quy tắc gì.
- `optional = false` mặc định có nghĩa gì.
- Điều annotation **không tự làm**: không cập nhật schema hay bảo đảm dữ liệu.

Khi có thay đổi hành vi, cần sửa Javadoc **cùng lúc với** consumer và test. Tài liệu mô tả một cam kết, không phải công cụ tự đảm bảo cam kết ấy.

## 9. Các lỗi thường gặp

### Lỗi 1: Chỉ chú thích tên annotation, bỏ qua ý nghĩa

Khai báo `/** Policy. */ @interface Policy {...}` không cho người dùng biết chính sách gì, do ai xử lý, có áp dụng mặc định không. Hãy mô tả hành vi mong đợi từ consumer và giới hạn của annotation.

### Lỗi 2: Không ghi tài liệu cho từng element

`int timeout();` khiến người đọc không biết đơn vị giây/mili giây, có cho phép 0 hay số âm hay không, và việc không cung cấp có hợp lệ không. Tên và kiểu chưa đủ thay cho hợp đồng.

### Lỗi 3: Nhầm default với phần mô tả Javadoc

Ghi “mặc định 3” trong Javadoc **không làm Java chọn 3**. Phải khai báo `int retries() default 3;` nếu thật sự muốn element có giá trị mặc định. Cập nhật Javadoc khi đổi mặc định.

### Lỗi 4: Tưởng giá trị mặc định được ghi vào mọi nơi dùng annotation

Theo JLS, default được áp dụng khi đọc annotation. Đổi default ở annotation type có thể thay đổi giá trị hiệu lực tại client không truyền element tường minh, kể cả trong tình huống dùng bytecode cũ với định nghĩa annotation mới.

### Lỗi 5: Dùng null làm default

`String description() default null;` là lỗi biên dịch. Hãy chọn sentinel rõ nghĩa như chuỗi rỗng, enum hoặc mảng rỗng, rồi mô tả trong Javadoc.

### Lỗi 6: Nghĩ @Documented tự tạo tài liệu phần tử

`@Documented` kiểm soát hiển thị **annotation tại nơi sử dụng** trong tài liệu công khai. Nó không viết hộ phần giải thích `@interface` hay `@return` cho các element.

### Lỗi 7: Nghĩ @Documented đồng nghĩa với @Inherited

`@Documented` liên quan tới công cụ tài liệu; `@Inherited` liên quan tới cách tìm annotation trên class qua superclass. Hai meta-annotation có trách nhiệm riêng.

### Lỗi 8: Tuyên bố annotation tự thực thi hành vi

Khai báo `@RetryPolicy` không tự tạo retry; `@Audit` không tự ghi log. Tài liệu phải xác định consumer và các điều kiện cơ chế đó hoạt động.

### Lỗi 9: Ghi giá trị/ràng buộc không khớp triển khai

Nếu Javadoc nói `retries` chỉ nhận từ 0 tới 5, nhưng consumer không kiểm tra, người dùng có thể cấu hình `-1` và gặp hành vi không dự đoán được. Cần đồng bộ hợp đồng, validation và test.

### Lỗi 10: Thay đổi default mà không xét tương thích

Đổi `enabled() default false` sang `true` có thể ảnh hưởng đến client không truyền giá trị tường minh. Những thay đổi liên quan bảo mật hoặc side effect cần đánh giá tác động và mô tả phiên bản rõ ràng.

## 10. Checklist tự review trước khi xuất bản annotation

| Câu hỏi | Dấu hiệu đạt |
| --- | --- |
| Người đọc hiểu annotation biểu đạt điều gì? | Javadoc mở đầu diễn giải chính xác ý nghĩa nghiệp vụ |
| Biết gắn ở đâu? | `@Target` và tài liệu thống nhất |
| Biết ai sử dụng metadata? | Có mô tả annotation processor, framework hoặc runtime consumer |
| Hiểu từng element? | Có Javadoc riêng, `@return` khi thích hợp, đơn vị/ràng buộc rõ |
| Biết phần tử nào bắt buộc? | Element thiếu default được thể hiện và giải thích |
| Hiểu default? | `default` trong code khớp Javadoc |
| Hiểu mảng/enum/sentinel? | Có giải thích giá trị rỗng, thứ tự, trường hợp đặc biệt |
| Có cần xuất hiện trên Javadoc của nơi sử dụng? | Cân nhắc `@Documented` |
| Có cần reflection runtime? | `@Retention(RUNTIME)` và consumer tương ứng |
| Thay đổi có tương thích? | Đánh giá client dựa vào default và các hợp đồng đã công bố |

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Một element `int retries() default 2;` được ghi trong Javadoc là “mặc định 5”. Giá trị hiệu lực khi dùng `@RetryPolicy` là gì?

**Đáp án:** `2` theo cú pháp Java. Javadoc đã lỗi thời và cần được sửa.

**Câu 2.** Viết `String name();` rồi dùng `@Config` không điền `name` có hợp lệ không?

**Đáp án:** Không, nếu `name()` là element không có default và không có giá trị được cung cấp trong annotation usage.

**Câu 3.** Khi thêm `@Documented` lên annotation type, Java có tự gọi code xử lý metadata không?

**Đáp án:** Không. `@Documented` liên quan tới hợp đồng tài liệu và cách các công cụ như `javadoc` hiển thị annotation.

**Câu 4.** `@return` đặt trên annotation element và `default` phía sau khai báo element khác nhau ở đâu?

**Đáp án:** `@return` mô tả ý nghĩa giá trị cho người đọc; `default` xác định giá trị Java sẽ cung cấp khi annotation usage bỏ qua element.

**Câu 5.** Khi thay `default 2` thành `default 4`, client sử dụng `@Policy(retries = 1)` có tự thành 4 không?

**Đáp án:** Không. Giá trị `1` đã được khai báo tường minh. Các usage bỏ qua element mới nhận default mới khi được đọc theo định nghĩa annotation hiện hành.

**Câu 6.** Nếu một annotation có `@Documented` và `@Retention(CLASS)`, Javadoc có nhất thiết phải từ chối nó vì reflection runtime không đọc được không?

**Đáp án:** Không. Công cụ sinh tài liệu và reflection runtime có vai trò khác nhau; retention quyết định lưu giữ, còn `@Documented` nêu yêu cầu hiển thị trong tài liệu công khai.

## Tài liệu tham khảo chính thức

- [JLS 17 §9.6.1 — Annotation Interface Elements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.1).
- [JLS 17 §9.6.2 — Defaults for Annotation Interface Elements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.2).
- [JLS 17 §9.7.1 — Element-value pairs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7.1).
- [Java SE 17 API — Documented](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Documented.html).
- [Java SE 17 API — Annotation](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html).

Khi viết annotation phục vụ người khác, hãy bắt đầu bằng **ý nghĩa và hợp đồng**, rồi thể hiện rõ từng element cùng giá trị mặc định trong cả code và Javadoc. Metadata càng ảnh hưởng mạnh tới hành vi của consumer, tài liệu và cơ chế kiểm tra càng phải cụ thể.
