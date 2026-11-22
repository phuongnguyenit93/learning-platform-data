# Thiết kế kiểu annotation đánh dấu, một phần tử và nhiều phần tử trong Java

Java cho phép định nghĩa **annotation type** bằng từ khóa **@interface**. Tùy lượng dữ liệu cần biểu diễn, một kiểu annotation thường được thiết kế theo ba dạng: **marker annotation** (không có phần tử), **single-element annotation** (một phần tử) và **multi-element annotation** (nhiều phần tử).

Ba dạng này khác nhau chủ yếu ở **hợp đồng dữ liệu** mà người viết annotation phải cung cấp. Chúng không tự quyết định annotation hoạt động lúc biên dịch hay runtime: việc được gắn vào vị trí nào, được giữ lại đến giai đoạn nào và ai diễn giải metadata là các quyết định riêng.

## 1. Khai báo annotation type bằng @interface

Mẫu cơ bản:

~~~java
@interface TenAnnotation {
    // Các phần tử annotation (nếu có)
}
~~~

Khác với **interface** thông thường, khai báo **@interface** dùng để định nghĩa một kiểu annotation. Các phần tử của nó được viết như phương thức không có tham số, thường khai báo kiểu trả về và tên, ví dụ **String name();**. Dấu chấm phẩy kết thúc khai báo; không cung cấp thân phương thức.

Một số quy tắc cần nắm:

- Tên kiểu annotation tuân theo quy tắc đặt tên kiểu Java. Có thể khai báo trong một package và tham chiếu bằng tên ngắn sau import hoặc tên đầy đủ, ví dụ **@com.example.audit.Review**.
- Top-level annotation type khai báo **public** phải nằm trong tệp nguồn có cùng tên, chẳng hạn **public @interface Review** trong **Review.java**. Những ví dụ nhiều kiểu trong một tệp ở dưới dùng top-level annotation không public để chạy độc lập.
- Phần tử annotation chỉ được trả về những kiểu được Java cho phép: kiểu nguyên thủy, **String**, **Class** (với tham số kiểu hợp lệ), enum, một kiểu annotation, hoặc **mảng một chiều** của các kiểu đó.
- Không khai báo phần tử nhận tham số, kiểu trả về **void**, mảng hai chiều, kiểu bất kỳ như **Object**, **List<String>** hoặc **Map<String, String>**.
- Mỗi phần tử có thể có **default** để chỉ định giá trị mặc định. Nếu không có default, người dùng phải cung cấp giá trị khi gắn annotation.
- Giá trị truyền vào phần tử phải là **annotation element value** hợp lệ tại thời điểm biên dịch: số và chuỗi từ biểu thức hằng thích hợp, hằng enum, class literal, annotation lồng nhau hoặc mảng những giá trị được cho phép. Không dùng **null**, **new** để khởi tạo đối tượng tùy ý, hay dữ liệu chỉ biết được lúc runtime.

Các khai báo kiểu và phần tử quyết định cấu trúc dữ liệu. **@Target** và **@Retention** là meta-annotation thường dùng để xác định vị trí hợp lệ và thời gian tồn tại của metadata; chúng sẽ xuất hiện trong ví dụ đầy đủ.

## 2. Marker annotation: kiểu đánh dấu không có phần tử

**Marker annotation** có phần thân không khai báo annotation element. Nó diễn tả một thông tin nhị phân ở mức khai báo: **có gắn dấu** hoặc **không gắn dấu**.

~~~java
@interface Experimental {
}
~~~

Cách dùng:

~~~java
@Experimental
class NewFeatureService {
}
~~~

Nếu chỉ cần đánh dấu một class để công cụ hoặc chương trình kiểm tra về sau, marker annotation là thiết kế đơn giản nhất. Ví dụ, chương trình có thể tìm class được gắn **@Experimental** để đưa ra cảnh báo hoặc áp dụng quy trình riêng. Bản thân dấu **@Experimental** không tự bật một tính năng nào.

Marker không có phần tử, nên **không được** viết:

~~~java
@Experimental(value = true)
class WrongFeatureService {
}
~~~

Đoạn trên **không biên dịch được**: Experimental không có phần tử tên **value**. Nếu cần lưu boolean, trạng thái hoặc một thông tin khác, hãy chuyển sang annotation có phần tử phù hợp.

Ngoài **@Experimental**, Java cũng cho phép dạng **@Experimental()** vì danh sách cặp tên–giá trị rỗng. Dạng không có ngoặc phổ biến hơn với marker.

Một điểm dễ nhầm: một annotation khai báo nhiều phần tử nhưng **tất cả đều có default** có thể được gắn mà không điền giá trị, nhưng nó **không phải marker annotation** về mặt cấu trúc. Marker thật sự có **0 phần tử**.

**Khi nên dùng marker:** nhu cầu biểu diễn chỉ có/không, không có dữ liệu cấu hình đi kèm; ví dụ đánh dấu một API nội bộ hoặc chỉ ra một class tham gia một bước xử lý do framework định nghĩa.

## 3. Single-element annotation: kiểu có đúng một phần tử

Nếu cần truyền đúng một thông tin, định nghĩa một phần tử:

~~~java
@interface Category {
    String value();
}
~~~

Cách dùng có hai dạng hợp lệ:

~~~java
@Category(value = "payment")
class PaymentService {
}

@Category("report")
class ReportService {
}
~~~

**@Category("report")** là cú pháp rút gọn của **@Category(value = "report")** vì phần tử mang tên đặc biệt **value**. Đây chỉ là cú pháp rút gọn; giá trị và kiểu annotation không thay đổi.

Nếu phần tử duy nhất có tên khác **value**, phải viết rõ tên:

~~~java
@interface Owner {
    String team();
}

@Owner(team = "backend")
class OwnedService {
}
~~~

Với khai báo trên, viết **@Owner("backend")** không hợp lệ. Quy tắc rút gọn gắn với **tên phần tử value()**, không phải cứ annotation chỉ có một phần tử là được bỏ tên.

### Cung cấp giá trị mặc định

~~~java
@interface Category {
    String value() default "general";
}
~~~

Với khai báo này, **@Category** hợp lệ và tương ứng với **value = "general"**. Tuy nhiên, nên cân nhắc liệu giá trị mặc định có làm mất ý nghĩa của việc truyền một thông tin quan trọng hay không: nếu mỗi class bắt buộc có mã category riêng, phần tử **value()** không nên có default.

Một annotation có phần tử **value()** và các phần tử khác với default cũng cho phép dạng rút gọn cho **value** khi các phần tử khác không được chỉ định:

~~~java
@interface Route {
    String value();
    boolean enabled() default true;
}

@Route("/users")
class UserRoute {
}

@Route(value = "/admin", enabled = false)
class AdminRoute {
}
~~~

**Route** ở ví dụ này là annotation **nhiều phần tử**, dù cách dùng **@Route("/users")** trông giống single-element annotation. Để xác định dạng thiết kế, phải nhìn vào **khai báo kiểu**, không suy từ số đối số tại một vị trí sử dụng.

## 4. Multi-element annotation: kiểu có nhiều phần tử

Khi metadata cần mô tả nhiều thuộc tính có ý nghĩa độc lập, khai báo mỗi thuộc tính thành một phần tử:

~~~java
enum Level {
    LOW,
    HIGH
}

@interface Review {
    String owner();
    int version();
    Level level() default Level.LOW;
    String[] tags() default {};
}
~~~

Ở đây **Review** có bốn phần tử. Hai phần tử **owner** và **version** bắt buộc; **level** và **tags** là tùy chọn vì có default.

Cách dùng đầy đủ:

~~~java
@Review(
    owner = "team-a",
    version = 2,
    level = Level.HIGH,
    tags = {"security", "critical"}
)
class PaymentComponent {
}
~~~

Cách dùng chỉ cung cấp những phần tử bắt buộc:

~~~java
@Review(owner = "team-b", version = 1)
class ReportingComponent {
}
~~~

Khi không được chỉ định, **level()** có giá trị **Level.LOW** và **tags()** có mảng rỗng. Tất cả phần tử được đọc theo **tên**, nên thứ tự các cặp **owner = ...**, **version = ...**, **level = ...** không phải quy ước mang ý nghĩa nghiệp vụ.

Với multi-element annotation, tên phần tử giúp tránh nhầm lẫn khi truyền các giá trị cùng kiểu. Ví dụ **owner** và **description** cùng có kiểu String nhưng biểu diễn hai khái niệm khác nhau; đặt tên rõ ràng giúp người đọc hiểu dữ liệu ngay tại nơi gắn annotation.

### Mảng làm giá trị phần tử

Phần tử **String[] tags()** chấp nhận:

~~~java
@Review(owner = "team-a", version = 2, tags = {})
class NoTags {}

@Review(owner = "team-a", version = 2, tags = {"api", "public"})
class MultipleTags {}

@Review(owner = "team-a", version = 2, tags = "internal")
class SingleTag {}
~~~

Trong trường hợp phần tử có kiểu mảng, Java cho phép bỏ cặp ngoặc nhọn khi truyền **một** giá trị duy nhất có kiểu phần tử tương ứng. **tags = "internal"** tương đương với **tags = {"internal"}**. Với nhiều phần tử, dùng cặp ngoặc nhọn như ví dụ **MultipleTags**.

### Default và thiết kế API

Giá trị mặc định nằm trong **khai báo annotation type**, không gắn vào class sử dụng:

~~~java
@interface Retry {
    int attempts() default 3;
    boolean enabled() default true;
}
~~~

Đúng: **int attempts() default 3;**. Sai: **int attempts() = 3;**.

Nếu thêm một phần tử bắt buộc mới vào annotation đã được sử dụng ở nhiều nơi, các chỗ gắn annotation cũ có thể không còn biên dịch được khi được biên dịch lại. Thêm phần tử mới với **default** thường giúp mã sử dụng cũ tiếp tục hợp lệ về mặt cú pháp, dù vẫn cần xét ý nghĩa hành vi của giá trị mặc định. Đổi tên hoặc xóa phần tử cũng ảnh hưởng đến mã nguồn đang tham chiếu nó.

## 5. Ví dụ Java 17+ hoàn chỉnh: ba kiểu thiết kế cạnh nhau

Ví dụ sau thể hiện cùng lúc marker, single-element và multi-element annotation trên class, rồi dùng reflection để đọc metadata.

Tạo tệp **src/demo/AnnotationDesignDemo.java**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Experimental {
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Category {
    String value();
}

enum Level {
    LOW,
    HIGH
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Review {
    String owner();
    int version();
    Level level() default Level.LOW;
    String[] tags() default {};
}

@Experimental
@Category("payment")
@Review(
    owner = "team-a",
    version = 2,
    level = Level.HIGH,
    tags = {"api", "billing"}
)
class PaymentService {
}

@Category(value = "report")
@Review(owner = "team-b", version = 1)
class ReportService {
}

public class AnnotationDesignDemo {
    public static void main(String[] args) {
        printInfo(PaymentService.class);
        printInfo(ReportService.class);
    }

    private static void printInfo(Class<?> type) {
        System.out.println("class=" + type.getSimpleName());
        System.out.println(
            "experimental=" + type.isAnnotationPresent(Experimental.class)
        );

        Category category = type.getAnnotation(Category.class);
        System.out.println("category=" + category.value());

        Review review = type.getAnnotation(Review.class);
        System.out.println(
            "review=" + review.owner() + "/v" + review.version()
        );
        System.out.println("level=" + review.level());
        System.out.println("tags=" + Arrays.toString(review.tags()));
    }
}
~~~

Từ thư mục chứa **src**, chạy:

~~~bash
javac -encoding UTF-8 -d out src/demo/AnnotationDesignDemo.java
java -cp out demo.AnnotationDesignDemo
~~~

Stdout chính xác:

~~~text
class=PaymentService
experimental=true
category=payment
review=team-a/v2
level=HIGH
tags=[api, billing]
class=ReportService
experimental=false
category=report
review=team-b/v1
level=LOW
tags=[]
~~~

**Giải thích từng dạng:**

1. **Experimental** có 0 phần tử. Phần mã **isAnnotationPresent(Experimental.class)** kiểm tra có annotation đó trên class được chỉ định hay không. PaymentService có annotation nên cho kết quả true; ReportService không có nên false.
2. **Category** có đúng 1 phần tử **value()**. PaymentService dùng dạng rút gọn **@Category("payment")**; ReportService dùng dạng đầy đủ **@Category(value = "report")**. **category.value()** trả về chuỗi tương ứng.
3. **Review** có 4 phần tử. PaymentService khai báo đầy đủ các giá trị. ReportService khai báo những giá trị bắt buộc **owner** và **version**; **level** và **tags** nhận default nên in **LOW** và **[]**.
4. Các annotation được khai báo **@Retention(RetentionPolicy.RUNTIME)** để reflection có thể đọc ở runtime. Đặt **@Target(ElementType.TYPE)** để cho phép chúng gắn trên khai báo class.
5. Ví dụ không tạo ra cơ chế quản trị service, kiểm toán hoặc phân quyền tự động. Nó chỉ lưu rồi đọc metadata; hành vi nghiệp vụ (nếu cần) phải do framework, annotation processor hoặc mã ứng dụng quyết định.

Trong hàm **printInfo**, cả hai class đều có Category và Review nên việc gọi các phần tử là an toàn trong ví dụ. Trong chương trình thực tế, **getAnnotation(...)** có thể trả về **null**; cần kiểm tra trước khi gọi phương thức trên kết quả.

**Lưu ý về tệp nguồn:** Tất cả annotation và enum phụ trợ của ví dụ là top-level type không public trong cùng package **demo**, còn class public duy nhất là **AnnotationDesignDemo**, nên chúng có thể đặt chung một tệp nguồn như đã chỉ dẫn.

## 6. So sánh ba dạng khi thiết kế

| Tiêu chí | Marker | Một phần tử | Nhiều phần tử |
| --- | --- | --- | --- |
| Số phần tử khai báo | 0 | 1 | Từ 2 trở lên |
| Ví dụ khai báo | **@interface Experimental {}** | **@interface Category { String value(); }** | **@interface Review { String owner(); int version(); }** |
| Ví dụ sử dụng | **@Experimental** | **@Category("payment")** | **@Review(owner = "team", version = 2)** |
| Thông tin biểu diễn | Có hoặc không có dấu | Một giá trị cấu hình | Nhiều trường metadata |
| Cần chỉ định giá trị | Không | Có, trừ khi phần tử có default | Chỉ các phần tử không có default |
| Cân nhắc thiết kế | Tên phải phản ánh rõ ý nghĩa dấu | Chọn **value()** nếu một giá trị trung tâm | Đặt tên phần tử cụ thể, default hợp lý |

Chọn dạng theo **ý nghĩa cần biểu diễn**:

- Nếu chỉ cần đánh dấu class để một công cụ nhận biết, marker giúp tránh dữ liệu thừa.
- Nếu cần một mã hoặc nhãn trung tâm, single-element annotation là đủ; đặt tên **value** khi mong muốn cú pháp rút gọn trực quan.
- Nếu cần nhiều thông số độc lập như owner, version, level hoặc tags, multi-element annotation giúp khai báo tường minh. Chỉ bổ sung phần tử khi metadata thực sự cần thông tin đó.

Annotation phù hợp cho **metadata được khai báo trong mã nguồn** và xử lý theo quy tắc cụ thể. Nếu một giá trị thay đổi thường xuyên trong môi trường chạy, phụ thuộc người dùng hoặc cần sửa tức thời mà không xây dựng lại ứng dụng, thiết kế có thể cần nguồn cấu hình runtime thay vì mã hóa mọi giá trị vào annotation.

## 7. Ràng buộc của kiểu phần tử và annotation mặc định

Các ví dụ sau minh họa giá trị hợp lệ ở nơi khai báo:

~~~java
@interface Settings {
    int limit() default 10;
    String label() default "default";
    Class<?> target() default String.class;
    Level priority() default Level.LOW;
    String[] names() default {};
}
~~~

Trong đó **Level** là enum đã được khai báo ở cùng package hoặc import hợp lệ. **String.class** là class literal, **Level.LOW** là hằng enum và **{}** là mảng rỗng. Trong annotation, cách khai báo **default** khác phép gán cho field hoặc tham số constructor.

Annotation element cũng có thể có kiểu là annotation khác:

~~~java
@interface TimeLimit {
    int millis() default 100;
}

@interface Action {
    TimeLimit timeout() default @TimeLimit;
}
~~~

Trong ví dụ này, **timeout()** là một phần tử duy nhất có kiểu TimeLimit và **default @TimeLimit** hợp lệ vì các phần tử của TimeLimit có default. **@TimeLimit** là giá trị annotation lồng nhau, không phải lời gọi constructor. Khi chỉ cần hiểu cách thiết kế marker/một/nhiều phần tử, hãy nhìn vào số lượng phần tử khai báo trong từng **@interface**; kiểu giá trị của phần tử có thể là annotation khác mà không thay đổi nguyên tắc phân loại.

Các khai báo sau không hợp lệ làm phần tử annotation:

~~~java
// Ví dụ SAI - chỉ để nhận diện lỗi:
// @interface Invalid {
//     Object data();
//     java.util.List<String> tags();
//     int[][] matrix();
//     void run();
//     String find(String key);
// }
~~~

Lý do lần lượt là kiểu Object không được phép, collection không thuộc tập kiểu hợp lệ, mảng hai chiều không được phép, void không phải kiểu phần tử và phương thức của annotation không nhận tham số. Đây là quy tắc ngôn ngữ, không phụ thuộc framework.

## 8. Meta-annotation không quyết định số phần tử

Khi thiết kế kiểu, các annotation sau thường xuất hiện ngay trên khai báo **@interface**:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Trace {
    String value() default "";
}
~~~

- **@Target(ElementType.METHOD)** cho phép Trace áp dụng trên khai báo method. Nếu cố gắn **@Trace** lên class, trình biên dịch sẽ báo lỗi vì vị trí không phù hợp.
- **@Retention(RetentionPolicy.RUNTIME)** cho phép giữ annotation ở runtime và truy xuất qua reflection. Nếu không chỉ định retention, mặc định là **RetentionPolicy.CLASS**, tức được giữ trong class file nhưng thường không nhìn thấy qua reflection lúc runtime.
- **Trace** có một phần tử **value()**, bất kể @Target và @Retention đứng trên khai báo. Các meta-annotation là annotation áp lên kiểu Trace, không được tính là phần tử của Trace.

Các marker, single-element và multi-element annotation đều có thể sử dụng @Target, @Retention hoặc meta-annotation khác phù hợp. Phân loại theo số phần tử và chính sách giữ lại/áp dụng là hai quyết định tách biệt.

## 9. Lỗi thường gặp và cách khắc phục

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Viết **interface Flag {}** rồi dùng **@Flag** | Flag là interface bình thường, chưa phải annotation type | Khai báo **@interface Flag {}** |
| Viết **@Experimental(true)** cho marker không có phần tử | Không tồn tại **value()** để nhận true | Dùng **@Experimental**, hoặc thiết kế phần tử nếu cần dữ liệu |
| Viết **@Owner("backend")** với phần tử **team()** | Chỉ phần tử **value()** hỗ trợ bỏ tên | Dùng **@Owner(team = "backend")** |
| Viết **@Review(owner = "team")** khi **version()** bắt buộc | Thiếu phần tử không có default | Cung cấp **version = ...** hoặc định nghĩa default nếu hợp lý |
| Viết **String name() = "x";** trong annotation | Cú pháp khai báo default sai | Dùng **String name() default "x";** |
| Viết **String[] tags() default null;** | Annotation value không được null | Dùng **default {}** nếu cần mặc định rỗng |
| Viết **new Category("x")** thay cho annotation value | Annotation không được gắn bằng cú pháp tạo object | Dùng **@Category("x")** |
| Gắn annotation lên vị trí ngoài phạm vi Target | **@Target** không cho phép vị trí đó | Chọn ElementType thích hợp cho chủ đích thiết kế |
| Đọc metadata qua reflection nhưng nhận null | Sai class/kiểu hoặc annotation không có retention RUNTIME | Kiểm tra vị trí, kiểu và retention |
| Xem annotation như logic tự chạy | Annotation là metadata, chưa có thành phần diễn giải | Viết hoặc tích hợp cơ chế xử lý metadata có chủ đích |

Đặc biệt, **annotation có default ở mọi phần tử** vẫn là annotation có phần tử. Ví dụ **@interface Options { boolean enabled() default true; }** thuộc dạng một phần tử, dù có thể dùng **@Options** mà không ghi đối số.

## 10. Bài tập tự kiểm tra

**Bài 1.** Phân loại ba khai báo:

~~~java
@interface Internal {}

@interface Code {
    String value();
}

@interface Feature {
    String name();
    boolean enabled() default true;
}
~~~

Đáp án: **Internal** là marker (0 phần tử); **Code** là single-element (1 phần tử); **Feature** là multi-element (2 phần tử). Việc Feature có default cho enabled không làm nó trở thành single-element.

**Bài 2.** Cho khai báo:

~~~java
@interface Author {
    String name();
    String email() default "";
}
~~~

Cách viết **@Author(name = "Mai")** có hợp lệ không? Có, vì chỉ **name()** bắt buộc. Có được viết **@Author("Mai")** không? Không, vì không có phần tử **value()**.

**Bài 3.** Tại sao **@Category("shop")** dùng được nhưng **@Category** không dùng được khi Category.value() chưa có default? Vì dạng đầu cung cấp giá trị bắt buộc cho phần tử **value()**, còn dạng sau bỏ sót nó.

**Bài 4.** Nếu muốn người dùng đánh dấu class đồng thời truyền mức độ nghiêm trọng **HIGH/LOW**, marker có đủ không? Không. Có thể tạo single-element annotation kiểu enum, chẳng hạn **@interface Severity { Level value(); }** rồi sử dụng **@Severity(Level.HIGH)**. Nếu cần thêm lý do và người chịu trách nhiệm, cân nhắc multi-element annotation với các tên phần tử rõ ràng.

Khi quyết định thiết kế, hãy tự hỏi: **Có cần lưu giá trị không? Nếu có, một giá trị có đủ diễn tả ý nghĩa không? Trường nào bắt buộc, trường nào nên có default? Kiểu giá trị có nằm trong nhóm Java cho phép không?** Trả lời các câu hỏi này sẽ giúp chọn đúng giữa marker, single-element và multi-element annotation trước khi bổ sung chính sách áp dụng hay mã xử lý metadata.
