# Truyền annotation lồng nhau làm giá trị trong Java

Một **annotation có thể nhận một annotation khác làm giá trị của phần tử (element)**. Khi khai báo, phần tử của annotation bên ngoài có kiểu là một **annotation type**. Khi sử dụng, ta viết trực tiếp cú pháp `@TênAnnotation(...)` ở vị trí giá trị của phần tử đó.

Ví dụ cốt lõi:

~~~java
@interface Retry {
    int attempts();
}

@interface Client {
    Retry retry();
}

@Client(retry = @Retry(attempts = 3))
class ApiService {}
~~~

Trong **@Client(retry = @Retry(attempts = 3))**, **Client** là annotation bên ngoài; phần tử **retry()** có kiểu **Retry**; **@Retry(attempts = 3)** chính là giá trị được truyền vào. Đây là một **annotation-valued element**, không phải việc tạo object bằng `new`.

Bài này tập trung vào cú pháp, khai báo, giá trị mặc định, mảng annotation lồng nhau, cách truy xuất và những lỗi thường gặp.

## 1. Cơ chế: annotation cũng là kiểu hợp lệ của annotation element

Một khai báo annotation trong Java sử dụng **@interface**:

~~~java
@interface Timeout {
    int millis();
}

@interface Command {
    String name();
    Timeout timeout();
}
~~~

Phân biệt hai lớp cấu trúc:

- **Timeout** là một *annotation type* có phần tử **millis()** nhận `int`.
- **Command** là một *annotation type* có phần tử **timeout()** nhận giá trị thuộc kiểu annotation **Timeout**.
- Khi gắn **@Command** lên một khai báo, người viết phải cung cấp cả **name** và **timeout** vì các phần tử này chưa có giá trị mặc định.
- Ở vị trí **timeout = ...**, trình biên dịch yêu cầu một **annotation value** có đúng kiểu Timeout; viết **@Timeout(millis = 800)** là hợp lệ.

~~~java
@Command(
    name = "sync",
    timeout = @Timeout(millis = 800)
)
class SyncCommand {}
~~~

Cú pháp được đọc từ trong ra ngoài: **@Timeout(millis = 800)** mô tả cấu hình thời gian; giá trị đó được gán cho **timeout** của **@Command**. Dấu **@** ở annotation bên trong là bắt buộc.

Theo quy tắc của Java, một phần tử annotation có thể có kiểu primitive, `String`, `Class` (kể cả cách dùng `Class<?>` phù hợp), enum, annotation type hoặc **mảng một chiều** của những kiểu đó. Vì vậy kiểu annotation như **Timeout** và **Timeout[]** được chấp nhận; kiểu đối tượng tùy ý như **Object**, **List<Timeout>** hay mảng hai chiều **Timeout[][]** không hợp lệ làm kiểu phần tử annotation.

Annotation element khai báo dưới dạng phương thức **không có tham số**, chẳng hạn **Timeout timeout();**; đây là mô tả cấu trúc metadata, không phải phương thức nghiệp vụ để gán một đối tượng tại runtime.

## 2. Cú pháp truyền một annotation lồng nhau

Mẫu chung:

~~~java
@Outer(inner = @Inner(key = "value"))
class Example {}
~~~

Với định nghĩa tương ứng:

~~~java
@interface Inner {
    String key();
}

@interface Outer {
    Inner inner();
}
~~~

Một số điểm cần nhớ:

1. **inner =** là tên phần tử của annotation bên ngoài; nó bắt buộc nếu phần tử đó không có `default`.
2. **@Inner(...)** có kiểu đúng bằng kiểu mà **inner()** khai báo.
3. Các giá trị ở bên trong **@Inner** cũng phải tuân thủ quy tắc giá trị annotation: ví dụ chuỗi hằng cho `String`, biểu thức hằng tại thời điểm biên dịch cho số nguyên, hằng enum thích hợp và tiếp tục lồng annotation khi kiểu cho phép.
4. Dấu ngoặc của **@Outer(...)** và **@Inner(...)** là hai cấp riêng biệt. Việc xuống dòng chỉ phục vụ khả năng đọc, không ảnh hưởng ý nghĩa.

**Không** viết `inner = new Inner(...)`: annotation không được khởi tạo bằng `new` trong cú pháp gắn annotation. Cũng không viết `inner = Inner(...)` vì thiếu dấu **@**.

### Phần tử có tên value()

Java hỗ trợ cú pháp rút gọn cho một phần tử tên **value**:

~~~java
@interface Label {
    String value();
}

@interface Endpoint {
    Label label();
}

@Endpoint(label = @Label("public"))
class PublicEndpoint {}
~~~

Cách viết **@Label("public")** tương đương với **@Label(value = "public")**. Bên ngoài, **@Endpoint(label = ...)** vẫn phải nêu tên **label**, vì phần tử của Endpoint không có tên **value**.

Nếu chính phần tử của annotation bên ngoài có tên **value**, cũng có thể rút gọn tầng ngoài:

~~~java
@interface Wrapper {
    Label value();
}

@Wrapper(@Label("public"))
class Example {}
~~~

Cách viết này tương đương **@Wrapper(value = @Label(value = "public"))**. Cả hai tầng rút gọn là quy tắc cú pháp độc lập.

## 3. Giá trị mặc định của annotation lồng nhau

Một annotation-valued element có thể có giá trị mặc định ngay trong khai báo:

~~~java
@interface RetryPolicy {
    int attempts() default 3;
    long delayMillis() default 100L;
}

@interface ClientConfig {
    RetryPolicy retry() default @RetryPolicy;
}
~~~

**@RetryPolicy** không có dấu ngoặc vẫn hợp lệ vì tất cả các phần tử của RetryPolicy đều có giá trị mặc định. Khai báo **default @RetryPolicy** của ClientConfig cũng hợp lệ: nó là một giá trị annotation mặc định, không phải lời gọi constructor.

Khi sử dụng:

~~~java
@ClientConfig
class DefaultClient {}

@ClientConfig(retry = @RetryPolicy(attempts = 5))
class CustomizedClient {}
~~~

Với **DefaultClient**, phần tử **retry()** sử dụng annotation mặc định **@RetryPolicy**; bên trong, **attempts()** mặc định là **3** và **delayMillis()** mặc định là **100**. Với **CustomizedClient**, cả annotation RetryPolicy được chỉ định lại để ghi đè attempts thành **5**; delayMillis vẫn sử dụng mặc định **100**.

Không nhầm hai tầng mặc định:

- **default @RetryPolicy** là giá trị mặc định của phần tử **ClientConfig.retry()**.
- **default 3** và **default 100L** là giá trị mặc định của các phần tử **RetryPolicy.attempts()** và **RetryPolicy.delayMillis()**.

Nếu **RetryPolicy** có phần tử bắt buộc, giá trị mặc định ở tầng ngoài phải cung cấp phần tử bắt buộc đó. Ví dụ, khi `int attempts();` không có default, biểu thức mặc định phải có dạng **default @RetryPolicy(attempts = 3)**.

Giá trị annotation, kể cả giá trị mặc định, được xác định theo cú pháp Java tại thời điểm biên dịch. Không thể viết `default new RetryPolicy(...)`, không thể gán `null` làm giá trị annotation và không thể dùng kết quả tùy ý của một phương thức runtime để điền metadata.

## 4. Truyền mảng các annotation lồng nhau

Khi annotation bên ngoài cần nhiều cấu hình con, khai báo phần tử kiểu **NestedAnnotation[]**:

~~~java
@interface Header {
    String name();
    String value();
}

@interface RequestConfig {
    Header[] headers() default {};
}
~~~

Khi dùng, viết các annotation con trong cặp ngoặc nhọn:

~~~java
@RequestConfig(headers = {
    @Header(name = "Accept", value = "application/json"),
    @Header(name = "X-Client", value = "learning")
})
class JsonRequest {}
~~~

Mỗi phần tử trong **headers** phải có kiểu **Header**. Dấu phẩy ngăn cách các phần tử, giống cú pháp khởi tạo giá trị mảng trong annotation. Với mảng rỗng:

~~~java
@RequestConfig(headers = {})
class NoHeaders {}
~~~

Java còn cho phép **bỏ cặp ngoặc nhọn nếu một phần tử mảng annotation được cung cấp đúng một giá trị**:

~~~java
@RequestConfig(headers = @Header(name = "Accept", value = "text/plain"))
class TextRequest {}
~~~

Cách viết trên tương đương với **headers = { @Header(...) }**, tức là vẫn tạo một giá trị mảng chứa một annotation. Khi hướng dẫn người mới học, dùng ngoặc nhọn cho phần tử mảng giúp phân biệt rõ với phần tử chỉ nhận một annotation.

Không được truyền hai annotation ngăn bằng dấu phẩy mà bỏ ngoặc nhọn, chẳng hạn `headers = @Header(...), @Header(...)`; và không thể gán **@Header** vào phần tử có kiểu **RetryPolicy** vì sai kiểu.

## 5. Ví dụ Java 17+ hoàn chỉnh: cấu hình client với annotation lồng nhau

Tạo duy nhất tệp **src/demo/NestedAnnotationDemo.java** với nội dung:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target({})
@interface Retry {
    int attempts() default 3;
    long delayMillis() default 100L;
}

@Retention(RetentionPolicy.RUNTIME)
@Target({})
@interface Header {
    String name();
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface HttpClient {
    String baseUrl();
    Retry retry() default @Retry;
    Header[] headers() default {};
}

@HttpClient(
    baseUrl = "https://api.example.test",
    retry = @Retry(attempts = 5, delayMillis = 250L),
    headers = {
        @Header(name = "Accept", value = "application/json"),
        @Header(name = "X-App", value = "demo")
    }
)
class ApiService {}

@HttpClient(baseUrl = "https://backup.example.test")
class BackupService {}

public class NestedAnnotationDemo {
    public static void main(String[] args) {
        printConfig(ApiService.class);
        printConfig(BackupService.class);
    }

    private static void printConfig(Class<?> type) {
        HttpClient config = type.getAnnotation(HttpClient.class);
        if (config == null) {
            System.out.println(type.getSimpleName() + " has no @HttpClient");
            return;
        }

        System.out.println(type.getSimpleName() + " -> " + config.baseUrl());

        Retry retry = config.retry();
        System.out.println("retry: " + retry.attempts()
                + " / " + retry.delayMillis());

        for (Header header : config.headers()) {
            System.out.println("header: " + header.name()
                    + "=" + header.value());
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa **src**:

~~~bash
javac -encoding UTF-8 -d out src/demo/NestedAnnotationDemo.java
java -cp out demo.NestedAnnotationDemo
~~~

Kết quả stdout:

~~~text
ApiService -> https://api.example.test
retry: 5 / 250
header: Accept=application/json
header: X-App=demo
BackupService -> https://backup.example.test
retry: 3 / 100
~~~

**Phân tích theo từng bước:**

1. **@HttpClient** là annotation bên ngoài, áp dụng trên class nhờ **@Target(ElementType.TYPE)**. **Retry** và **Header** khai báo **@Target({})**, phù hợp để làm annotation lồng nhau trong phần tử annotation và không dùng trực tiếp trên các khai báo class/method/field.
2. **retry = @Retry(...)** cung cấp một giá trị duy nhất kiểu **Retry**. **headers = { @Header(...), @Header(...) }** cung cấp mảng gồm hai giá trị kiểu **Header**.
3. Các annotation dùng **@Retention(RetentionPolicy.RUNTIME)** trong ví dụ để việc đọc metadata bằng reflection rõ ràng; annotation ngoài phải có runtime retention để lấy được qua **Class.getAnnotation**.
4. **getAnnotation(HttpClient.class)** đọc metadata trên class được chỉ định. **config.retry()** trả về giá trị annotation con; **config.headers()** trả về mảng các annotation con, vì vậy có thể gọi **attempts()**, **name()**, **value()** tương ứng.
5. **BackupService** không truyền **retry** và **headers**. Nó nhận giá trị mặc định của phần tử HttpClient: **@Retry** với attempts=3/delayMillis=100 và mảng headers rỗng. Do đó vòng `for` không in thêm dòng header cho BackupService.

Ví dụ phản ánh cấu hình metadata: Java không tự thực hiện retry mạng hay tự gắn HTTP header vì sự hiện diện của annotation. Chỉ một framework hoặc mã ứng dụng đọc và sử dụng cấu hình này mới có thể tạo ra hành vi thực tế.

**Lưu ý về tên và import:** Retry và Header trong ví dụ cùng package với HttpClient, nên tên ngắn phân giải được trực tiếp. Nếu Retry nằm ở package khác, import đúng kiểu Retry hoặc viết tên đầy đủ sau dấu @, ví dụ **retry = @com.example.policy.Retry(...)**; quy tắc phân giải tên vẫn giống mọi kiểu annotation khác.

## 6. Annotation lồng nhau khác với meta-annotation và annotation lặp

Các cú pháp sau dễ gây nhầm vì đều có nhiều ký hiệu **@**:

**Annotation là giá trị của phần tử annotation** — đúng phạm vi của bài:

~~~java
@interface Constraint {
    int min();
}

@interface FieldRule {
    Constraint constraint();
}

@FieldRule(constraint = @Constraint(min = 1))
class Sample {}
~~~

Ở đây **Constraint** được đặt vào phần tử **constraint** của FieldRule.

**Meta-annotation** — annotation đặt lên khai báo một annotation type:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Marker {}
~~~

Trong trường hợp này, **@Retention** mô tả chính khai báo **Marker**, không được truyền như giá trị của một phần tử tên retention. Metadata mục tiêu khác nhau, mặc dù đều dùng ký hiệu @.

**Annotation lặp** — cùng loại annotation được viết nhiều lần lên một khai báo khi kiểu đã được định nghĩa là `@Repeatable`. Đây là cơ chế riêng của Java, không đồng nghĩa với việc khai báo một phần tử kiểu **Header[]** và truyền nhiều giá trị **@Header** vào phần tử đó.

## 7. Ràng buộc kiểu và lỗi biên dịch thường gặp

| Trường hợp | Vấn đề | Cách đúng |
| --- | --- | --- |
| `retry = Retry(attempts = 2)` | Thiếu dấu @ trước annotation bên trong | `retry = @Retry(attempts = 2)` |
| `retry = new Retry(2)` | Annotation value không dùng cú pháp tạo object | `retry = @Retry(attempts = 2)` |
| `retry = null` | Giá trị annotation không được là null | Cung cấp annotation hợp lệ hoặc khai báo **default** |
| `Retry retry() default null;` | Giá trị default không được là null | Ví dụ `Retry retry() default @Retry;` |
| `retry = @Header(...)` | Kiểu Header không khớp phần tử Retry | Dùng **@Retry(...)** |
| `Header[][] headers();` | Kiểu mảng hai chiều không hợp lệ cho annotation element | Dùng **Header[]** |
| `List<Header> headers();` | Annotation element không hỗ trợ List | Dùng **Header[]** |
| `headers = { @Header(name = "A") }` | Header còn thiếu phần tử bắt buộc **value** | Bổ sung `value = "..."` hoặc định nghĩa default cho phần tử đó |
| `@HttpClient(retry = @Retry)` khi **baseUrl()** bắt buộc | Thiếu phần tử bắt buộc ở tầng ngoài | Cung cấp `baseUrl = "..."` |
| Đọc **getAnnotation(...)** được null | Annotation ngoài không có mặt hoặc không được lưu tới runtime | Kiểm tra đúng class, đúng kiểu và `@Retention(RUNTIME)` |

Khi một annotation lồng nhau có thêm một annotation lồng tiếp nữa, áp dụng đệ quy cùng các quy tắc về tên, kiểu phần tử, cú pháp **@**, `default` và giá trị hợp lệ. Java không đặt quy tắc “chỉ được lồng một tầng”; giới hạn thực tế đến từ định nghĩa kiểu, khả năng biểu diễn hợp lệ và độ dễ đọc của cấu hình.

## 8. Bài tập tự kiểm tra

Cho các annotation sau:

~~~java
@interface Cache {
    int seconds() default 60;
}

@interface Route {
    String path();
    Cache cache() default @Cache;
}

@Route(path = "/users", cache = @Cache(seconds = 120))
class UserRoute {}
~~~

**Câu 1.** Giá trị truyền vào **Route.cache()** là kiểu nào? — Kiểu annotation **Cache**, thông qua giá trị **@Cache(seconds = 120)**.

**Câu 2.** Nếu sửa thành **@Route(path = "/users")** thì có lỗi vì thiếu cache không? — Không; **Route.cache()** có mặc định **@Cache**, trong đó **seconds()** mặc định là **60**.

**Câu 3.** Có thể thay giá trị cache bằng `Cache.class` không? — Không. `Cache.class` có kiểu **Class<Cache>**, còn phần tử **cache()** yêu cầu **Cache**. Nếu muốn phần tử chứa class literal, khai báo của phần tử phải dùng kiểu **Class<?>** hoặc kiểu `Class` hợp lệ phù hợp.

**Câu 4.** Muốn Route chứa nhiều chính sách Cache thì cần đổi gì? — Đổi khai báo từ **Cache cache()** sang phần tử **Cache[] caches()** (ví dụ có **default {}**) và truyền mảng **{ @Cache(seconds = 30), @Cache(seconds = 60) }**.

Khi gặp cú pháp annotation nhiều tầng, hãy đọc từ khai báo phần tử **kiểu gì**, rồi so với giá trị sau dấu **=**. Nếu phần tử khai báo một annotation type, dùng **@AnnotationCon(...)**; nếu là mảng annotation type, dùng **{ @AnnotationCon(...), ... }**. Đây là quy tắc nền tảng để truyền annotation lồng nhau một cách đúng kiểu và rõ ràng.
