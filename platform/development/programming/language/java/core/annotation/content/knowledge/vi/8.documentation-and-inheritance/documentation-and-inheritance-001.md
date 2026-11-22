# `@Documented` và việc công bố annotation trong Javadoc

## 1. `@Documented` dùng để làm gì?

Trong Java, một annotation tùy chỉnh có thể gắn metadata lên class, method, field hay những phần tử khác. Nhưng **không phải mọi annotation xuất hiện trong mã nguồn đều tự động được công bố trong tài liệu API do `javadoc` tạo ra**.

`java.lang.annotation.Documented` là một **meta-annotation** dùng trên **khai báo annotation type**. Khi một annotation type được đánh dấu `@Documented`, các lần sử dụng annotation đó được xem là **một phần của hợp đồng công khai** của phần tử được đánh dấu. Các công cụ tài liệu như `javadoc` theo mặc định sẽ thể hiện annotation đó khi tạo tài liệu cho phần tử tương ứng.

Ví dụ:

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Documented
@Target(ElementType.METHOD)
@interface PublicRule {
    String value();
}
~~~

Khi `@PublicRule("must-validate")` được gắn lên một method thuộc API công khai, công cụ Javadoc mặc định sẽ hiển thị thông tin annotation đó trong phần tài liệu của method.

Nếu không có `@Documented`, mặc định Javadoc **không công bố việc sử dụng annotation** đó trên khai báo API, dù annotation vẫn tồn tại trong mã nguồn và có thể được công cụ khác xử lý.

Ý nghĩa quan trọng: **`@Documented` điều khiển việc trình bày metadata trong tài liệu API**, không quyết định annotation được phép gắn ở đâu, cũng không tự tạo hành vi nghiệp vụ.

## 2. Cơ chế: khai báo annotation, dùng annotation, sinh Javadoc

Có ba chỗ khác nhau phải phân biệt:

1. **Định nghĩa annotation type** bằng `@interface`. Ta gắn `@Documented` lên định nghĩa này.
2. **Sử dụng annotation** trên class hoặc method, ví dụ `@PublicRule("must-validate")`. Đây là nơi công cụ tài liệu có thể hiển thị metadata.
3. **Chạy công cụ `javadoc`** để tạo HTML hoặc dạng tài liệu do doclet cung cấp. Chính công cụ đọc mã/metadata và quyết định thể hiện theo `@Documented`.

~~~text
@Documented
@interface PublicRule { ... }
            |
            | công bố annotation type trong hợp đồng API
            v
@PublicRule("must-validate")
public void save() { ... }
            |
            v
      javadoc xử lý
            |
            v
Tài liệu public method hiển thị @PublicRule cùng giá trị
~~~

Nếu mã nguồn có annotation nhưng **chưa chạy công cụ tài liệu**, không có HTML nào tự xuất hiện. Nếu annotation chưa được `@Documented` đánh dấu, Javadoc mặc định sẽ không thể hiện việc sử dụng đó trong phần mô tả API dù nó có thể vẫn đọc được ở giai đoạn khác.

`@Documented` chỉ đánh dấu metadata **nên được thể hiện như một phần public contract**. Nó không buộc người dùng gọi method theo cách khác, không tự kiểm tra điều kiện, cũng không có callback chạy trước/sau method.

### Phân biệt annotation type được tài liệu hóa và việc sử dụng annotation được hiện ra

Một annotation type công khai vẫn có thể có **trang Javadoc riêng**, ví dụ trang mô tả các phần tử `value()`, `level()`, nếu được đưa vào tập source mà Javadoc xử lý. Điều đó **không phụ thuộc** vào việc nó có `@Documented`.

Điều `@Documented` bổ sung là **khi annotation type đó được sử dụng trên một class hoặc method khác, việc sử dụng và giá trị annotation trở thành một phần tài liệu của phần tử ấy**.

Ví dụ:

- Trang định nghĩa `InternalTag` có thể xuất hiện trong Javadoc nếu `InternalTag` là annotation type công khai.
- Nhưng `@InternalTag` gắn trên `ApiService` sẽ không tự được hiển thị trên tài liệu của `ApiService` nếu kiểu `InternalTag` không được đánh dấu `@Documented`.

Đó là khác biệt giữa **viết tài liệu cho một annotation type** và **công bố annotation đang gắn trên một API khác**.

## 3. Cú pháp và đặc điểm của `java.lang.annotation.Documented`

Khai báo chuẩn trong Java SE 17 thể hiện:

~~~java
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
public @interface Documented {
}
~~~

Đây là **hình thức API để minh họa**, không phải mã cần chép đè lên định nghĩa có sẵn trong JDK.

Các ý nghĩa:

- `@Documented` bản thân là một **marker annotation**: không có phần tử phải truyền.
- `@Target(ANNOTATION_TYPE)` nghĩa là chỉ gắn `@Documented` lên **khai báo annotation type**, ví dụ `@interface PublicTag`. Đặt nó trực tiếp trên một class hoặc method thông thường là sai target.
- `@Retention(RUNTIME)` là retention của **bản thân meta-annotation `Documented`**. Điều này không bắt buộc annotation tùy chỉnh được đánh dấu bằng nó phải dùng `RUNTIME`.
- `@Documented` cũng được tự đánh dấu bởi `@Documented`; đây là đặc điểm hợp lệ của một meta-annotation chuẩn.

Một khai báo tùy chỉnh hợp lệ thường có cả ba meta-annotation:

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
public @interface PublishedTag {
    String value();
}
~~~

`@Target`, `@Retention` và `@Documented` trả lời ba câu hỏi khác nhau: **được gắn ở đâu, được lưu đến bao lâu, và có được công bố trong tài liệu API không**.

## 4. Ví dụ thực hành Java 17: so sánh annotation có và không có `@Documented`

Ta sẽ tạo một API công khai với hai annotation:

- `@PublishedTag`: có `@Documented`, nên việc sử dụng của nó phải được công bố trong Javadoc mặc định.
- `@InternalTag`: không có `@Documented`, nên việc sử dụng của nó không được công bố trong trang API mặc định.

Cả hai đều có `@Retention(RUNTIME)` để minh họa riêng rằng **runtime reflection vẫn đọc được cả hai**, bất kể chúng có `@Documented` hay không.

Đặt bốn tệp Java trong thư mục `src/example/docs/` của một thư mục thực hành độc lập.

### 4.1. `src/example/docs/PublishedTag.java`

~~~java
package example.docs;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** Đánh dấu thông tin cần công bố cùng API. */
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
public @interface PublishedTag {
    /** Mô tả mức độ cam kết công khai. */
    String value();
}
~~~

### 4.2. `src/example/docs/InternalTag.java`

~~~java
package example.docs;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** Đánh dấu metadata phục vụ công cụ nội bộ. */
@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
public @interface InternalTag {
}
~~~

`InternalTag` là một annotation type công khai; nó vẫn có thể có trang mô tả riêng. Sự khác biệt đang khảo sát là việc **hiển thị chỗ sử dụng `@InternalTag` trên tài liệu API khác**.

### 4.3. `src/example/docs/ApiService.java`

~~~java
package example.docs;

/** API dịch vụ ví dụ. */
@PublishedTag("stable")
@InternalTag
public class ApiService {

    /**
     * Trả về lời chào.
     *
     * @param name tên người được chào
     * @return lời chào có tên
     */
    @PublishedTag("public-operation")
    @InternalTag
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Ở cả khai báo `ApiService` và phương thức `greet`, hai annotation đều **hợp lệ về cú pháp**, có cùng retention, và đều có thể được reflection nhận diện. Tuy nhiên metadata của `PublishedTag` được đánh dấu là thành phần của **hợp đồng tài liệu công khai**, còn metadata của `InternalTag` thì không.

### 4.4. `src/example/docs/DocumentationDemo.java`

~~~java
package example.docs;

import java.lang.annotation.Documented;
import java.lang.reflect.Method;

/** Chứng minh Documented và runtime reflection độc lập. */
public class DocumentationDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        Class<ApiService> type = ApiService.class;
        Method method = type.getMethod("greet", String.class);

        System.out.println("PublishedTag has @Documented: "
                + PublishedTag.class.isAnnotationPresent(Documented.class));
        System.out.println("InternalTag has @Documented: "
                + InternalTag.class.isAnnotationPresent(Documented.class));

        System.out.println("Published on class: "
                + type.isAnnotationPresent(PublishedTag.class));
        System.out.println("Internal on class: "
                + type.isAnnotationPresent(InternalTag.class));
        System.out.println("Published on method: "
                + method.isAnnotationPresent(PublishedTag.class));
        System.out.println("Internal on method: "
                + method.isAnnotationPresent(InternalTag.class));
        System.out.println("Published value: "
                + type.getAnnotation(PublishedTag.class).value());
    }
}
~~~

### 4.5. Biên dịch và chạy

Mở terminal tại thư mục cha của `src/`. Dùng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 -d out src/example/docs/PublishedTag.java src/example/docs/InternalTag.java src/example/docs/ApiService.java src/example/docs/DocumentationDemo.java
java -cp out example.docs.DocumentationDemo
~~~

**Stdout chính xác:**

~~~text
PublishedTag has @Documented: true
InternalTag has @Documented: false
Published on class: true
Internal on class: true
Published on method: true
Internal on method: true
Published value: stable
~~~

Hai annotation đều đọc được bằng runtime reflection vì chúng đều dùng `RetentionPolicy.RUNTIME`. Sự khác nhau ở việc có `@Documented` **không làm một annotation bị mất đi trong runtime**.

### 4.6. Sinh Javadoc và kiểm tra kết quả

Cũng tại thư mục cha của `src/`, chạy:

~~~bash
javadoc -quiet -encoding UTF-8 -docencoding UTF-8 -d docs -public src/example/docs/PublishedTag.java src/example/docs/InternalTag.java src/example/docs/ApiService.java src/example/docs/DocumentationDemo.java
~~~

Mở tệp kết quả:

~~~text
docs/example/docs/ApiService.html
~~~

Trong trang tài liệu của class `ApiService`, hãy quan sát:

1. Khai báo class được thể hiện cùng annotation **`@PublishedTag`** với thông tin giá trị `"stable"`, bởi `PublishedTag` có `@Documented`.
2. Phần khai báo method `greet` được thể hiện cùng **`@PublishedTag`** với giá trị `"public-operation"`.
3. **`@InternalTag` không được công bố như một annotation trên class/method** trong Javadoc mặc định vì không có `@Documented`.
4. Phần Javadoc `/** ... */` của class và method vẫn được hiển thị theo cơ chế tài liệu bình thường, không liên quan tới `@Documented`.

Vị trí, cách hiển thị chữ `value=`, liên kết và bố cục HTML có thể thay đổi theo phiên bản JDK hoặc doclet. Hãy kiểm tra **sự hiện diện và ý nghĩa** của annotation trong trang API, thay vì so sánh chính xác từng ký tự HTML.

Một vài điểm quan trọng về công cụ:

- `javac` thực hiện **biên dịch**. `java` chạy `main`, trong khi `javadoc` tạo tài liệu từ source/API; chúng là các lệnh riêng.
- Tùy chọn `-d docs` chỉ định thư mục xuất tài liệu, không liên quan đến retention.
- Tùy chọn `-public` chọn các declaration có phạm vi public để đưa vào tài liệu; vì vậy một phần tử private không được công bố chỉ vì annotation của nó có `@Documented`.
- Annotation không có `@Documented` **không đồng nghĩa không thể xử lý** bởi compiler, framework, reflection hoặc công cụ kiểm tra mã.

## 5. `@Documented` khác Javadoc comment và Javadoc tag

Trong Java, từ “documented” dễ dẫn đến nhầm giữa ba cơ chế.

### 5.1. Bình luận Javadoc `/** ... */`

~~~java
/** Tính tiền sau khi áp dụng chiết khấu. */
public int total() {
    return 100;
}
~~~

Đây là **một phần của định nghĩa một method**, không phải chương trình Java độc lập. Bình luận Javadoc cung cấp **nội dung giải thích bằng ngôn ngữ tự nhiên** cho một phần tử. Người lập trình viết các thẻ như `@param`, `@return`, `@throws`, `@since` bên trong bình luận để công cụ tài liệu diễn giải.

### 5.2. Annotation `@Documented`

~~~java
@Documented
@interface ApiStatus {
    String value();
}
~~~

Đây là **meta-annotation đặt trên một annotation type**. Nó báo rằng các lần sử dụng `@ApiStatus` thuộc hợp đồng tài liệu công khai. `@Documented` **không tự tạo đoạn mô tả bằng văn xuôi** cho `ApiStatus`.

### 5.3. Java annotation `@Deprecated` và Javadoc tag `@deprecated`

Đây là ví dụ điển hình cho một annotation và một Javadoc tag có mục đích liên quan nhưng khác cơ chế:

~~~java
/**
 * API cũ.
 *
 * @deprecated Sử dụng newApi() thay thế.
 */
@Deprecated(since = "1.2", forRemoval = false)
public void oldApi() {
}
~~~

Đoạn trên là **một khai báo method minh họa**, cần đặt trong class để biên dịch. `@Deprecated` là annotation mà Java/compiler/công cụ có thể nhận biết; `@deprecated` bên trong `/** ... */` là Javadoc tag giải thích cách thay thế. `@Deprecated` chuẩn cũng được thiết kế để xuất hiện trong tài liệu API; nó không thay thế văn bản hướng dẫn chuyển đổi.

So sánh:

| Cơ chế | Đặt ở đâu? | Vai trò chính |
| --- | --- | --- |
| `/** ... */` | Trước khai báo Java | Viết nội dung mô tả API |
| `@param`, `@return`, `@deprecated` | Bên trong Javadoc comment | Cấu trúc thông tin tài liệu |
| `@Documented` | Trên định nghĩa `@interface` | Công bố các lần dùng annotation trong tài liệu API |
| `@Deprecated` | Trên phần tử Java cần đánh dấu | Metadata đánh dấu API lỗi thời |

Không thể viết `@Documented` trong bình luận Javadoc với kỳ vọng nó trở thành meta-annotation; cũng không thể chỉ dùng một đoạn mô tả `/** ... */` để thay đổi target, retention hoặc khả năng reflection đọc annotation.

## 6. Quan hệ với `@Target`, `@Retention` và `@Inherited`

Ba meta-annotation khác nhau được dùng cho ba yêu cầu độc lập.

| Meta-annotation | Câu hỏi trả lời | Tác động thực tế |
| --- | --- | --- |
| `@Target` | Annotation hợp lệ ở đâu? | Compiler kiểm tra vị trí đặt annotation |
| `@Retention` | Metadata được giữ đến giai đoạn nào? | Source, class file hay có thể truy cập runtime |
| `@Documented` | Việc sử dụng annotation có thuộc hợp đồng API được công bố? | Javadoc mặc định hiển thị các annotation đã đánh dấu |
| `@Inherited` | Khi tra cứu annotation trên class con, có thể tìm thấy annotation từ superclass không? | Ảnh hưởng việc tra cứu metadata trên class theo quy tắc kế thừa cụ thể |

### 6.1. Có cần `RetentionPolicy.RUNTIME` để `@Documented` hoạt động?

**Không.** `javadoc` làm việc với mô hình khai báo/source và không cần gọi runtime reflection để biết một annotation đã được gắn ở đâu. Annotation có `@Retention(RetentionPolicy.SOURCE)` vẫn có thể được **hiển thị trong Javadoc** nếu annotation type được đánh dấu `@Documented`.

Ví dụ fragment hợp lệ:

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface SourceApiMark {
}

@SourceApiMark
class Contract {
}
~~~

Mã này minh họa retention `SOURCE`: Javadoc xử lý từ source có thể công bố `@SourceApiMark` trên `Contract` khi phần tử được chọn vào tài liệu; nhưng runtime reflection trên `Contract.class` **không thể nhìn thấy** annotation đó. Nếu muốn `javadoc` tạo tài liệu cho `Contract` trong dự án mẫu, phải đưa khai báo ấy vào tập source và tùy chọn phạm vi tài liệu thích hợp.

Ngược lại, annotation **không có `@Documented` nhưng có retention `RUNTIME`** vẫn có thể đọc bình thường bằng reflection, giống `@InternalTag` trong ví dụ.

Điểm phân biệt: Javadoc công bố metadata và Reflection đọc metadata **giải quyết hai bài toán khác nhau**.

### 6.2. `@Documented` có khiến annotation tự động được kế thừa không?

Không. `@Inherited` điều khiển việc **một số API tra cứu annotation trên class con** có thể tìm annotation của superclass. `@Documented` chỉ nói về việc công bố thông tin annotation trong tài liệu.

- Có `@Documented` nhưng không `@Inherited`: Javadoc có thể thể hiện annotation trên chính class được đánh dấu, nhưng Java không vì `@Documented` mà coi class con được thừa hưởng annotation theo reflection.
- Có `@Inherited` nhưng không `@Documented`: truy vấn reflection trên class con có thể thấy annotation được kế thừa theo quy tắc của `@Inherited` (với retention thích hợp), nhưng Javadoc mặc định không công bố các lần sử dụng annotation đó chỉ nhờ `@Inherited`.
- Có cả hai: hai cơ chế cùng tồn tại nhưng vẫn có vai trò độc lập. Không suy ra rằng Javadoc của class con nhất thiết sẽ chép lại mọi metadata từ superclass; cách hiển thị phụ thuộc tài liệu hóa và công cụ.

Hãy tránh nhầm `@Inherited` với Javadoc inline tag `{@inheritDoc}`: `{@inheritDoc}` dùng để kế thừa **nội dung bình luận tài liệu** ở những trường hợp Javadoc hỗ trợ, hoàn toàn không phải Java annotation.

## 7. Khi nào nên dùng `@Documented`?

Nên dùng khi thông tin annotation thực sự là **một phần ý nghĩa của public API** mà người sử dụng thư viện cần thấy trong tài liệu. Ví dụ:

- `@StableApi`: công bố mức độ ổn định hoặc khả năng tương thích theo chính sách thư viện.
- `@RequiresPermission("REPORT_READ")`: nếu quyền truy cập là hợp đồng chính thức của API và có bộ xử lý thực thi.
- `@Experimental`: cho người dùng biết một API đang thử nghiệm và có thể thay đổi.
- `@SchemaHint`: nếu thông tin schema cần được công bố khi dùng API.

Đây là **những tên annotation tự thiết kế để minh họa**, không phải annotation bắt buộc có sẵn trong Java SE.

Không nhất thiết dùng `@Documented` cho những metadata chỉ phục vụ **công cụ nội bộ**, ví dụ một dấu được gắn để tạo báo cáo kỹ thuật, kiểm tra build hoặc phục vụ implementation mà không cần đưa vào hợp đồng cho người sử dụng API.

Khi chọn `@Documented`, hãy cân nhắc rằng **giá trị các phần tử annotation có thể xuất hiện trong tài liệu công khai**. Không đưa khóa bí mật, mật khẩu, token hay chi tiết nội bộ nhạy cảm vào annotation metadata; công bố hay không công bố trong Javadoc đều không phải cơ chế bảo mật dữ liệu.

### Lựa chọn mang tính thiết kế API

Giả sử một thư viện công bố method:

~~~java
@RequiresPermission("INVOICE_WRITE")
public void submitInvoice() {
}
~~~

Đây là **đoạn khai báo minh họa**; chưa có định nghĩa `RequiresPermission` và không phải chương trình độc lập. Nếu đó là ràng buộc mà người tích hợp API phải biết, `@Documented` giúp Javadoc hiển thị thông tin. Nhưng việc hiển thị không đảm bảo **cơ chế kiểm tra quyền đã hoạt động**. Hệ thống vẫn cần interceptor, validator hoặc logic phân quyền tương ứng.

Nếu annotation chỉ đánh dấu phương thức cho công cụ build, việc không `@Documented` có thể giúp tài liệu API tập trung vào những thông tin người dùng thư viện thực sự cần.

## 8. Trường hợp nâng cao: `@Documented` và `@Repeatable`

Một annotation được dùng lặp lại có thể phải được trình bày qua **containing annotation type**. JLS yêu cầu: nếu annotation type lặp lại được đánh dấu `@Documented`, thì **containing annotation type cũng phải được đánh dấu `@Documented`**.

Ví dụ khai báo hợp lệ:

~~~java
import java.lang.annotation.Documented;
import java.lang.annotation.Repeatable;

@Documented
@Repeatable(Tags.class)
@interface Tag {
    String value();
}

@Documented
@interface Tags {
    Tag[] value();
}
~~~

Nếu giữ `@Documented` trên `Tag` nhưng bỏ `@Documented` khỏi `Tags`, định nghĩa repeatable annotation không còn đáp ứng ràng buộc của ngôn ngữ và gây lỗi compile-time.

Chiều ngược lại **được phép**: containing type có `@Documented` nhưng repeated annotation type không có. Tuy nhiên trong thiết kế thực tế, nên cân nhắc nhất quán những gì được coi là public contract.

Ví dụ trên chỉ nhằm minh họa các định nghĩa liên quan đến tài liệu hóa; khi tự thiết kế repeatable annotation trong dự án, còn phải đảm bảo `@Target`, `@Retention` và hợp đồng `value()` của container tương thích.

## 9. Lỗi thường gặp

**Lỗi 1 — “Gắn `@Documented` trực tiếp lên method để hiện ra Javadoc.”** Không đúng target. Cần gắn `@Documented` trên khai báo `@interface` của annotation mà method sử dụng.

**Lỗi 2 — “Không có `@Documented` thì annotation không hoạt động.”** Sai. Annotation có thể được compiler, framework, runtime reflection hoặc annotation processor dùng bình thường, chỉ mặc định không được công bố trong Javadoc của phần tử.

**Lỗi 3 — “`@Documented` làm annotation trở thành runtime annotation.”** Sai. Retention của annotation tùy chỉnh do `@Retention` quy định, độc lập với `@Documented`.

**Lỗi 4 — “`@Documented` tự viết mô tả về class/method.”** Sai. Nó hiển thị metadata của annotation; mô tả API vẫn cần viết trong `/** ... */`.

**Lỗi 5 — “Không có `@Documented` thì không thể sinh trang Javadoc riêng cho annotation type.”** Sai. Trang Javadoc của annotation type là tài liệu về **khai báo kiểu**; `@Documented` tác động đến **các nơi dùng kiểu đó**.

**Lỗi 6 — “`@Documented` buộc Javadoc hiển thị cả private API.”** Sai. Phạm vi xuất tài liệu phụ thuộc lựa chọn của `javadoc` như `-public` hay `-private`. Meta-annotation không ghi đè bộ lọc visibility.

**Lỗi 7 — “Annotation trên public API đã có `@Documented` thì chắc chắn được enforcement.”** Sai. Hiển thị một constraint trong tài liệu không tự triển khai constraint đó.

**Lỗi 8 — “`@Documented` và `@Inherited` cùng một cơ chế.”** Sai. Một cái thuộc tài liệu API; một cái thuộc quy tắc kế thừa metadata khi tra cứu annotation trên class.

**Lỗi 9 — “Javadoc tag `@deprecated` chính là annotation `@Documented`.”** Sai. `@deprecated` là tag tài liệu, `@Documented` là meta-annotation của Java.

## 10. Bài tập tự kiểm tra

**Câu 1.** Có `@interface Marker {}` và một public class `@Marker class A {}`. Javadoc theo mặc định có công bố việc sử dụng `@Marker` trên tài liệu `A` không?

**Đáp án:** Không, nếu `Marker` không được đánh dấu `@Documented`. Nhưng bản thân `Marker` vẫn có thể có trang tài liệu kiểu riêng nếu được đưa vào tập source được xử lý.

**Câu 2.** `@Documented` nên đặt ở `@interface Marker` hay `class A`?

**Đáp án:** Trên khai báo annotation type `Marker`, vì `Documented` có `@Target(ANNOTATION_TYPE)`.

**Câu 3.** Nếu một annotation dùng `@Documented` và `@Retention(SOURCE)`, Javadoc xử lý từ source có thể công bố nó không? Reflection runtime có đọc được không?

**Đáp án:** Javadoc có thể công bố việc sử dụng theo quy tắc `@Documented`, nhưng runtime reflection không thấy annotation đã bị loại bỏ do `SOURCE`.

**Câu 4.** Trong ví dụ phần 4, `InternalTag` không được công bố trên tài liệu của `ApiService`. Vì sao `isAnnotationPresent(InternalTag.class)` vẫn trả về `true`?

**Đáp án:** `InternalTag` có retention `RUNTIME`. `@Documented` và runtime retention phục vụ hai mục đích riêng.

**Câu 5.** Nếu muốn người dùng thư viện biết rằng method public yêu cầu một quyền nhất định, `@Documented` có thay thế được cơ chế kiểm tra quyền không?

**Đáp án:** Không. Nó giúp hiển thị cam kết trong tài liệu; hành vi kiểm tra quyền vẫn cần phần xử lý thực thi.

**Câu 6.** Một annotation `@Repeatable` được đánh dấu `@Documented` nhưng annotation container không có `@Documented`. Có vấn đề gì?

**Đáp án:** Có. JLS quy định containing annotation type cũng phải được đánh dấu `@Documented`.

**Bài thực hành:** Chạy đầy đủ ví dụ phần 4, kiểm tra `ApiService.html`. Sau đó thêm `@Documented` vào `InternalTag`, sinh lại Javadoc trong một thư mục output khác và quan sát sự thay đổi. Cuối cùng giữ `@Documented` nhưng đổi retention của `PublishedTag` sang `SOURCE`, biên dịch lại và so sánh HTML với kết quả reflection. Hãy giải thích từng kết quả theo đúng **ba tầng: metadata source, tài liệu API, runtime reflection**.

## 11. Tài liệu tham khảo chính thức

- [Java SE 17 API — `java.lang.annotation.Documented`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Documented.html): hợp đồng `@Documented` và việc công bố annotation trong tài liệu API.
- [Java SE 17 API — `java.lang.annotation.Retention`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html): thời điểm lưu metadata.
- [Java SE 17 API — `java.lang.annotation.Inherited`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html): quy tắc kế thừa annotation trên class.
- [Javadoc tool trong JDK 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html): lệnh sinh HTML từ mã nguồn và tùy chọn chọn phần tử public.

`@Documented` giúp người xây dựng thư viện nói rõ rằng **việc hiện diện và giá trị annotation là một phần hợp đồng mà tài liệu công khai cần thể hiện**. Nó kết nối metadata Java với tài liệu API; những cơ chế như runtime reflection, thực thi validation hoặc kế thừa annotation vẫn cần được xét riêng.