# Giữ phần tử annotation ít, rõ nghĩa và có kiểu dữ liệu phù hợp trong Java

Annotation trong Java là **metadata được khai báo ngay trong mã nguồn**. Mỗi phương thức không tham số được khai báo trong một **@interface** là một **annotation element**: nó quyết định người sử dụng được cung cấp những thông tin gì, với kiểu dữ liệu nào và có phải cung cấp hay không.

Một annotation được thiết kế tốt nên giúp người đọc hiểu **ý định** ngay tại nơi gắn annotation, giữ API gọn, giới hạn các trạng thái không hợp lệ và cho phép thư viện phát triển mà không phá vỡ hàng loạt nơi sử dụng. Nguyên tắc không phải “càng ít element càng tốt bằng mọi giá”, mà là **chỉ biểu diễn những khái niệm thật sự thuộc cùng một annotation**, đặt tên rõ ràng và chọn kiểu dữ liệu vừa hợp lệ trong ngôn ngữ Java vừa phù hợp với miền bài toán.

## 1. Annotation element là gì?

Xét khai báo:

~~~java
@interface Endpoint {
    String path();
    boolean enabled() default true;
}
~~~

**path()** và **enabled()** là hai element. Chúng được viết giống phương thức không tham số nhưng chỉ khai báo một giá trị metadata, không có thân hàm. Cú pháp **default** mô tả một giá trị mặc định chứ không phải triển khai một phương thức của Java interface thông thường.

Nơi sử dụng:

~~~java
@Endpoint(path = "/orders")
class OrdersApi {}
~~~

Ở đây:

- **path** là thông tin bắt buộc, vì **path()** không có default.
- **enabled** là thông tin tùy chọn, vì **enabled() default true**. Nếu không truyền, giá trị hiệu lực của enabled là true.
- Annotation không tự mở endpoint hoặc chạy server. Thành phần tiêu thụ metadata (framework, annotation processor hoặc mã reflection) phải đọc và thực thi hành vi tương ứng.

Một annotation type là một dạng interface đặc biệt, định nghĩa bằng **@interface**. Các giá trị element phải tuân theo tập kiểu dữ liệu được Java cho phép, không tùy ý sử dụng mọi kiểu như trong field hay phương thức Java.

## 2. Bắt đầu từ thông tin tối thiểu mà người dùng cần truyền

Trước khi thêm một element, nên trả lời:

1. **Annotation đang biểu diễn điều gì?** Một dấu phân loại, một mã định danh, hay một nhóm thông số có liên hệ chặt chẽ?
2. **Người sử dụng phải quyết định giá trị nào tại nơi khai báo?** Chỉ những thông tin này mới nên trở thành element bắt buộc.
3. **Giá trị nào đã có quy ước ổn định trong thư viện?** Giá trị đó có thể thành default, miễn là default không che giấu quyết định nguy hiểm.
4. **Hai element có thực sự độc lập?** Nếu chúng luôn suy ra được từ nhau, hãy cân nhắc giữ một element và tính giá trị còn lại trong mã tiêu thụ.
5. **Nhóm giá trị có giới hạn không?** Nếu tập lựa chọn là cố định, enum thường biểu diễn ý nghĩa tốt hơn chuỗi tự do.
6. **Thông tin có ổn định tại compile time không?** Cấu hình thay đổi theo tài khoản, môi trường triển khai hoặc yêu cầu lúc chạy có thể không phù hợp để mã hóa thành annotation.

Ví dụ thiết kế chứa quá nhiều cấu hình không gắn chặt với cùng một ý nghĩa:

~~~java
// Ví dụ API khó duy trì: trộn route, retry, logging và giao diện.
@interface MegaConfig {
    String path();
    int attempts() default 3;
    long delayMillis() default 100;
    boolean audit() default false;
    String[] roles() default {};
    String theme() default "light";
}
~~~

Dù cú pháp hợp lệ, kiểu MegaConfig tạo ra một “túi cấu hình” khó hiểu: sửa giao diện và sửa retry đều buộc dùng chung API annotation, trong khi các thuộc tính thuộc những trách nhiệm khác nhau.

Thiết kế tách theo trách nhiệm rõ hơn:

~~~java
@interface Route {
    String value();
}

@interface Retry {
    int attempts();
    long delayMillis() default 100;
}

@interface Audited {
}
~~~

Từng annotation chỉ chịu trách nhiệm cho một khía cạnh. Nơi sử dụng có thể ghép chúng một cách tường minh:

~~~java
@Route("/orders")
@Retry(attempts = 3)
@Audited
class OrderEndpoint {}
~~~

Đây là ví dụ khai báo rút gọn; chưa có **@Target** và **@Retention** nên chưa đại diện đầy đủ một API runtime. Khi triển khai, các meta-annotation cần phản ánh đúng vị trí và thời điểm đọc metadata. Một thiết kế tốt cũng cần tránh chia quá mức: nếu hai giá trị luôn thuộc cùng một hợp đồng và chỉ có nghĩa khi đi cùng nhau, giữ trong một annotation có tên chung rõ ràng là hợp lý.

## 3. Chọn marker, một element hay nhiều element

Có ba hình thức cơ bản:

| Dạng | Khai báo | Cách dùng | Khi phù hợp |
| --- | --- | --- | --- |
| **Marker** | **@interface Audited {}** | **@Audited** | Chỉ cần đánh dấu có/không, không lưu cấu hình |
| **Một element** | **@interface Route { String value(); }** | **@Route("/orders")** | Chỉ có một thông tin trung tâm |
| **Nhiều element** | **@interface Retry { int attempts(); long delayMillis() default 100; }** | **@Retry(attempts = 3)** | Có nhiều thuộc tính độc lập nhưng cùng một mục đích |

### 3.1. Marker: không thêm boolean thừa

Nếu chỉ muốn đánh dấu một class/method sẽ được kiểm toán, **@Audited** là đủ. Cân nhắc trước khi thiết kế:

~~~java
@interface Audited {
    boolean enabled() default true;
}
~~~

Dạng có boolean phù hợp **chỉ khi thật sự cần biểu diễn cả enabled=true và enabled=false tại nơi sử dụng**. Nếu annotation chỉ biểu thị sự tham gia vào chính sách, **@Audited**/không gắn annotation là API đơn giản hơn.

Đừng dùng một marker để hứa hẹn hành vi mà hệ thống không triển khai. **@Audited** không tự ghi log; cần thành phần xử lý hiểu dấu này.

### 3.2. Một element: chọn tên value() khi đó là giá trị chính

~~~java
@interface Route {
    String value();
}

@Route("/orders")
class Orders {}
~~~

Nếu element duy nhất tên **value()**, Java cho phép bỏ **value =**. **@Route("/orders")** là dạng rút gọn của **@Route(value = "/orders")**.

Không có quy tắc tự động rút gọn với tên khác:

~~~java
@interface Owner {
    String team();
}

@Owner(team = "payments")
class Payments {}
~~~

**@Owner("payments")** không biên dịch được vì Owner không có element **value()**. Không nên đổi tên **team()** thành **value()** chỉ để tiết kiệm vài ký tự nếu tên **team** mới giải thích chính xác ý nghĩa và API thường được mở rộng thành nhiều thuộc tính.

### 3.3. Nhiều element: ngắn nhưng đủ mô tả hợp đồng

~~~java
@interface Retry {
    int attempts();
    long delayMillis() default 100;
}
~~~

**attempts** và **delayMillis** cùng mô tả retry, nên đặt chung hợp lý. **attempts** bắt buộc nếu mỗi nơi sử dụng cần chủ động lựa chọn số lần thử; **delayMillis** tùy chọn khi thư viện có giá trị mặc định nhất quán.

Ngược lại, thêm **timeoutMillis**, **route**, **logLevel**, **roles**, **visibleInMenu** chỉ vì “có thể sẽ cần” thường làm API phình to trước khi có yêu cầu thực tế.

## 4. Đặt tên element làm rõ đơn vị và ý nghĩa

Element nên có tên mô tả **dữ liệu thực tế mà nó nắm giữ**, không phải tên mơ hồ hoặc tên dẫn đến cách hiểu khác.

| Tên yếu | Tên rõ hơn | Lý do |
| --- | --- | --- |
| **n()** | **attempts()** | Diễn tả đây là số lần thử |
| **delay()** | **delayMillis()** | Không phải suy đoán đơn vị thời gian |
| **flag()** | **audited()** hoặc một marker **@Audited** | Tránh boolean không rõ nghĩa |
| **name()** | **routeName()**, **ownerTeam()** nếu cần phân biệt | Nói rõ vai trò của chuỗi |
| **type()** | **handlerType()** | Phân biệt class của handler với loại nghiệp vụ |
| **mode()** kiểu String tùy ý | **Backoff mode()** kiểu enum | Tên và kiểu cùng phản ánh tập lựa chọn |

Không phải tên càng dài càng tốt. **path()**, **value()**, **role()** đều có thể là tên tốt nếu ngữ cảnh annotation làm ý nghĩa trở nên rõ ràng.

Với kiểu primitive dễ gây hiểu nhầm, tên chứa đơn vị như **delayMillis()**, **timeoutSeconds()**, **maxBytes()** giúp người đọc tránh truyền sai đơn vị. Một annotation element có kiểu **long** không tự biết đơn vị thời gian. Người thiết kế phải định nghĩa nó trong tên và tài liệu.

Nếu một element có giá trị boolean, nên chọn tên có thể đọc như một mệnh đề, chẳng hạn **required()**, **enabled()**, **audited()**; tránh **isFeature()**, **setEnabled()** nếu cách đặt tên làm người dùng nghĩ nó là phương thức nghiệp vụ.

## 5. Các kiểu dữ liệu hợp lệ của annotation element

Java hạn chế kiểu trả về của một annotation element. Theo Java Language Specification §9.6.1, các nhóm hợp lệ là:

1. **Kiểu nguyên thủy** (*primitive*): **boolean, byte, short, int, long, char, float, double**.
2. **String**.
3. **Class** hoặc một cách tham số hóa được phép của **Class**, ví dụ **Class<?>** hoặc **Class<? extends Handler>**.
4. **Enum type**.
5. **Annotation type khác**.
6. **Mảng một chiều** của một trong các nhóm trên.

Ví dụ khai báo hợp lệ:

~~~java
enum Backoff {
    FIXED,
    EXPONENTIAL
}

@interface Header {
    String name();
    String value();
}

@interface Settings {
    boolean enabled() default true;
    int maxAttempts() default 3;
    long timeoutMillis() default 500;
    String label() default "default";
    Class<?> handlerType() default Object.class;
    Backoff backoff() default Backoff.FIXED;
    Header header() default @Header(name = "Accept", value = "application/json");
    String[] tags() default {};
}
~~~

Điểm cần nhớ:

- **String** là kiểu tham chiếu đặc biệt được cho phép, không phải mọi class Java.
- Với **Class<?>**, giá trị được truyền thường là *class literal* như **String.class**, **SomeHandler.class**, không phải một đối tượng tùy ý tạo bằng new.
- Element kiểu **enum** nhận một hằng của enum, ví dụ **Backoff.EXPONENTIAL**.
- Element kiểu annotation khác nhận **annotation value**, ví dụ **@Header(name="Accept", value="application/json")**.
- **String[]** là mảng một chiều; Java hỗ trợ nhiều phần tử hoặc mảng rỗng thông qua cú pháp annotation element values.

Các loại **không hợp lệ** làm kiểu element:

~~~java
// Sai: không dùng các khai báo này trong @interface thực.
// @interface Invalid {
//     Object object();
//     java.util.List<String> names();
//     java.util.Map<String, String> options();
//     int[][] matrix();
//     void run();
//     String calculate(String input);
// }
~~~

**Object**, **List**, **Map** không nằm trong tập kiểu element cho phép; **int[][]** là mảng hai chiều; **void** không là kiểu giá trị; annotation element cũng không được nhận tham số. **Không thể** dùng annotation như một lớp cấu hình Java thông thường với constructor, collection và object graph tùy ý.

**Mẹo thiết kế:** Nếu thông tin đòi hỏi List/Map phức tạp, đối tượng mutable hoặc giá trị được tải ở runtime, có thể annotation không phải công cụ lưu trữ thích hợp. Hãy cân nhắc file cấu hình, class Java có kiểu rõ ràng hoặc registry do framework quản lý.

## 6. Chọn enum thay vì String khi giá trị là tập lựa chọn đóng

Giả sử chính sách retry chỉ cho phép hai chế độ:

~~~java
enum Backoff {
    FIXED,
    EXPONENTIAL
}

@interface Retry {
    int attempts();
    Backoff mode() default Backoff.FIXED;
}
~~~

Nơi sử dụng:

~~~java
@Retry(attempts = 3, mode = Backoff.EXPONENTIAL)
class PaymentClient {}
~~~

**Ưu điểm của enum:**

- Trình biên dịch kiểm tra tên hằng. Sai chính tả **Backoff.EXPONETIAL** tạo lỗi compile-time thay vì chuỗi hợp lệ nhưng không được thư viện hiểu.
- IDE có thể gợi ý tập lựa chọn.
- Công cụ tiêu thụ metadata không cần tự phân tích chuỗi rồi so khớp hàng loạt literal.
- API nói rõ miền giá trị dự kiến.

So với:

~~~java
@interface Retry {
    String mode() default "FIXED";
}
~~~

Chuỗi **"FIXED"**, **"fixed"**, **"unknown"** đều hợp lệ về kiểu; cần kiểm tra bổ sung để phát hiện chế độ không hỗ trợ. Dùng String vẫn hợp lý nếu miền giá trị có chủ đích mở rộng do bên ngoài đăng ký và không thể liệt kê bằng enum ổn định.

**Chi phí của enum:** Đổi/xóa tên hằng đã dùng trong metadata có thể làm mã nguồn cũ hoặc ứng dụng đã biên dịch gặp vấn đề khi đọc annotation ở phiên bản mới. Nên coi tên hằng enum được công bố như một phần của hợp đồng API và cân nhắc kế hoạch phiên bản.

## 7. Chọn Class thay vì tên class dạng chuỗi

Nếu annotation cần chỉ ra một **kiểu Java**, dùng **Class** hoặc **Class với giới hạn kiểu**:

~~~java
interface Handler {}

final class DefaultHandler implements Handler {}

@interface UseHandler {
    Class<? extends Handler> value();
}

@UseHandler(DefaultHandler.class)
class PaymentGateway {}
~~~

Ưu điểm:

- Compiler kiểm tra **DefaultHandler** thực sự là một kiểu phù hợp với **Handler**.
- IDE nhận diện tham chiếu đến class khi đổi tên/di chuyển mã.
- Hạn chế lỗi do viết sai tên package hoặc class trong chuỗi.
- Reflection có thể trả về một đối tượng **Class<? extends Handler>** khi đọc giá trị element theo quy tắc runtime.

Cách yếu hơn khi thông tin thực sự là kiểu Java:

~~~java
@interface UseHandlerName {
    String value();
}

// Chuỗi này không được trình biên dịch kiểm tra là class tồn tại.
// @UseHandlerName("com.example.handler.DefautHandler")
~~~

**Không phải lúc nào Class cũng thay String**. Nếu giá trị là mã plugin do hệ thống bên ngoài định danh hoặc có thể không nằm trên compile classpath, String có thể là quyết định có chủ ý. Nhưng khi đầu vào là class Java hiện hữu thì class literal thường biểu diễn thông tin chính xác hơn.

**Lưu ý về annotation processing:** Trong compiler model, các giá trị class literal được xử lý qua **TypeMirror/AnnotationMirror**; gọi một class-valued element từ proxy của compiler model có thể gây **MirroredTypeException** vì source chưa được nạp thành class. Đừng cố dùng Class.forName trên source đang biên dịch. Ở runtime reflection, Java có thể trả Class, nhưng cũng cần xử lý lỗi liên quan tới kiểu không còn tồn tại trong binary nếu thư viện thay đổi.

## 8. Dùng mảng khi metadata có tập giá trị nhỏ, cùng loại

Annotation element không nhận **List<String>**, nhưng có thể nhận **String[]**:

~~~java
@interface RolesAllowed {
    String[] value();
}

@RolesAllowed({"reader", "editor"})
class DocumentController {}
~~~

**value()** vẫn có thể được viết ở dạng rút gọn, dù kiểu element là mảng. Với **một phần tử**, Java cho phép cú pháp ngắn:

~~~java
@RolesAllowed("reader")
class ReadOnlyController {}
~~~

Tương đương về giá trị với **@RolesAllowed({"reader"})**.

Cách dùng:

~~~java
@interface Tags {
    String[] value() default {};
}

@Tags
class Untagged {}

@Tags({"public", "v1"})
class PublicApi {}
~~~

Mảng phù hợp với một tập đơn giản, đồng nhất, có số lượng không quá lớn. **Không nên** ép toàn bộ cấu hình dạng bảng hay cây nhiều tầng vào nhiều mảng song song:

~~~java
// Dễ sai vì hai mảng phải giữ cùng số phần tử và cùng thứ tự.
@interface BadHeaders {
    String[] names();
    String[] values();
}
~~~

Thiết kế tốt hơn là **mảng annotation lồng nhau** để các giá trị liên quan được nhóm theo từng bản ghi:

~~~java
@interface Header {
    String name();
    String value();
}

@interface Headers {
    Header[] value() default {};
}

@Headers({
    @Header(name = "Accept", value = "application/json"),
    @Header(name = "X-Client", value = "web")
})
class ClientHeaders {}
~~~

Mỗi Header giữ đúng một cặp name/value. Không thể truyền nhầm độ dài mảng names và values.

Tuy nhiên, nếu cấu hình có nhiều cấp, liên kết phức tạp hoặc cần cập nhật liên tục, hãy cân nhắc file cấu hình hoặc DSL khác thay vì tiếp tục thêm nhiều lớp annotation lồng nhau.

## 9. Default giúp giảm phần tử phải viết — nhưng không được che giấu quyết định quan trọng

**default** chỉ nên áp dụng khi có một giá trị hợp lý và nhất quán cho phần lớn nơi sử dụng.

~~~java
@interface Retry {
    int attempts();
    long delayMillis() default 100;
}
~~~

**@Retry(attempts = 3)** ngắn gọn vì delayMillis có default. Nếu mọi nơi sử dụng cần chọn attempts theo chính sách nghiệp vụ, không khai báo default cho attempts có thể tốt hơn.

Trong một API khác, nếu hầu hết các trường hợp thực sự cần số lần thử = 3 và khác biệt là ngoại lệ, có thể chọn **attempts() default 3**. Đó là quyết định theo domain, không phải yêu cầu bắt buộc của cú pháp Java.

### Khi nào nên tránh default?

- Một giá trị là **định danh bắt buộc** như đường dẫn API, mã sự kiện, tên tài nguyên.
- Giá trị tùy chọn mặc định có thể tạo **hành vi rủi ro**, chẳng hạn cho phép truy cập hoặc bật tính năng quan trọng.
- Không có một default mang ý nghĩa rõ ràng cho mọi bối cảnh.
- Việc thiếu giá trị cần được compiler phát hiện thay vì âm thầm tạo cấu hình.

Một marker annotation không có element không cần default. Một annotation có **mọi element đều có default** vẫn là annotation có element, không phải marker về cấu trúc.

### Sửa default có thể ảnh hưởng các class cũ

Theo JLS §9.6.2, giá trị mặc định được áp dụng **khi annotation được đọc**, không được sao chép vào từng nơi sử dụng. Ví dụ:

~~~java
@interface Retry {
    int attempts() default 3;
}

@Retry
class Billing {}
~~~

Nếu thư viện đổi **default 3** thành **default 5** rồi chạy với annotation type mới, binary cũ của Billing không khai báo attempts tường minh có thể được đọc với giá trị 5 **mà không cần biên dịch lại Billing**. Đây là thay đổi hành vi dù chưa chắc là thay đổi phá vỡ liên kết binary.

Ngược lại, **@Retry(attempts = 3)** đã ghi số 3 tường minh nên không bị default mới ghi đè.

Vì vậy, hãy xem giá trị mặc định là **một phần của hợp đồng công khai**. Muốn nâng cấp an toàn cần xác định nơi sử dụng đang phụ thuộc default và thành phần nào sẽ diễn giải nó.

## 10. Một bài toán API: từ thiết kế khó dùng tới thiết kế rõ ràng

Giả sử có một thư viện gọi HTTP. Thiết kế đầu tiên:

~~~java
@interface HttpAction {
    String name();
    String value();
    String retry();
    String delay();
    String mode();
    boolean a() default false;
}
~~~

Các vấn đề:

- **name()** và **value()** đều là String, không rõ vai trò.
- **retry()**, **delay()** là String dù cần số nguyên; có thể nhận giá trị sai như "many" hoặc "sometime".
- **mode()** là String trong khi miền giá trị có thể đóng.
- **a()** không diễn tả hành vi.
- Người dùng luôn phải cung cấp nhiều dữ liệu không cần thiết, ngay cả khi chỉ muốn khai báo một route đơn giản.

Một thiết kế gọn hơn:

~~~java
enum Backoff {
    FIXED,
    EXPONENTIAL
}

@interface Route {
    String value();
}

@interface Retry {
    int attempts();
    long delayMillis() default 100;
    Backoff backoff() default Backoff.FIXED;
}

@interface Audited {
}
~~~

Cách dùng:

~~~java
@Route("/orders")
@Retry(attempts = 3, backoff = Backoff.EXPONENTIAL)
@Audited
class Orders {}
~~~

Từng thông tin được biểu diễn bằng đúng kiểu phù hợp. **Route** có một chuỗi định danh, **Retry** có số nguyên và enum, **Audited** là marker. Việc tách ba annotation làm API rõ hơn thay vì nhét chúng vào một cấu trúc đa năng.

Đây không phải quy tắc rằng lúc nào cũng phải tách ba annotation. Nếu framework thực sự chỉ có một khái niệm cấu hình cần ba thuộc tính không thể tách rời, một annotation đa phần tử vẫn có thể là lựa chọn đúng. Quan trọng là sự gắn kết về ý nghĩa.

## 11. Ví dụ Java 17+ độc lập: thiết kế ít element và dễ đọc

Tạo tệp **src/demo/AnnotationDesignDemo.java**:

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Audited {
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Route {
    String value();
}

enum Backoff {
    FIXED,
    EXPONENTIAL
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Retry {
    int attempts();
    long delayMillis() default 100;
    Backoff backoff() default Backoff.FIXED;
}

class Gateway {
    @Route("/orders")
    @Audited
    @Retry(attempts = 3, backoff = Backoff.EXPONENTIAL)
    public void submit() {
    }

    @Route("/health")
    public void health() {
    }
}

public class AnnotationDesignDemo {
    public static void main(String[] args)
            throws NoSuchMethodException {
        describe("submit");
        describe("health");
    }

    private static void describe(String methodName)
            throws NoSuchMethodException {

        Method method = Gateway.class.getDeclaredMethod(methodName);

        Route route = method.getAnnotation(Route.class);
        Retry retry = method.getAnnotation(Retry.class);
        boolean audited = method.isAnnotationPresent(Audited.class);

        String routeValue = route == null ? "<none>" : route.value();

        System.out.println(methodName
                + ": route=" + routeValue
                + ", audited=" + audited);

        if (retry == null) {
            System.out.println("retry=<none>");
            return;
        }

        if (retry.attempts() <= 0) {
            throw new IllegalStateException("attempts must be positive");
        }

        System.out.println("retry=" + retry.attempts()
                + ", delayMillis=" + retry.delayMillis()
                + ", backoff=" + retry.backoff());
    }
}
~~~

Từ thư mục chứa **src**:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/demo/AnnotationDesignDemo.java
java -cp out demo.AnnotationDesignDemo
~~~

**Stdout:**

~~~text
submit: route=/orders, audited=true
retry=3, delayMillis=100, backoff=EXPONENTIAL
health: route=/health, audited=false
retry=<none>
~~~

### Phân tích các quyết định thiết kế

1. **Audited** là marker, không có phần tử boolean **enabled()**. Chỉ cần kiểm tra **isAnnotationPresent(Audited.class)**.
2. **Route** có đúng một phần tử **value()**, cho phép ghi **@Route("/orders")**. Đường dẫn là thông tin cần có nên không khai báo default.
3. **Retry** có ba phần tử cùng mô tả retry; **attempts()** là bắt buộc, **delayMillis()** và **backoff()** có default phù hợp với ví dụ.
4. **delayMillis()** dùng **long** và nêu rõ đơn vị mili-giây; **backoff()** dùng **enum Backoff** thay vì một String tự do.
5. **@Target(METHOD)** ghi rõ annotation dành cho phương thức. Nếu người dùng cố gắn chúng lên class, compiler sẽ từ chối. Đây là cách làm rõ nơi dùng hợp lệ.
6. **@Retention(RUNTIME)** cho phép reflection đọc giá trị metadata trên Method ở runtime.
7. **Gateway.health()** không có Retry, nên **getAnnotation(Retry.class)** trả null. Chương trình phân biệt việc **không gắn annotation** với việc có annotation và sử dụng default.
8. **attempts > 0** là ràng buộc nghiệp vụ trong mã tiêu thụ. Kiểu **int** chỉ bảo đảm giá trị số nguyên, **không tự cấm số 0 hoặc âm**. Annotation không tự thi hành validation này.
9. Chương trình không tự gửi HTTP request, retry hay ghi audit. Những annotation ở đây chỉ tạo metadata để in ra và kiểm tra.

Tệp có một public class **AnnotationDesignDemo**; các annotation type, enum và class hỗ trợ không public nên có thể cùng xuất hiện trong một tệp nguồn thuộc package demo.

## 12. Kiểu dữ liệu phù hợp chưa đủ: cần quy định ràng buộc hợp lệ

Ngay cả khi một element có kiểu đúng, tập giá trị Java cho phép có thể lớn hơn tập giá trị hợp lý theo nghiệp vụ.

Ví dụ **int attempts()** vẫn cho phép người dùng viết:

~~~java
@Retry(attempts = -2)
class BadClient {}
~~~

Số âm hợp lệ theo kiểu int nên **javac không tự biết** -2 là cấu hình retry sai. Nếu thư viện cần ngăn cấu hình đó:

- Dùng **annotation processor** đọc giá trị lúc biên dịch và báo lỗi bằng **Messager** với **Diagnostic.Kind.ERROR**.
- Hoặc dùng **reflection** kiểm tra khi ứng dụng khởi động, rồi báo lỗi cấu hình trước khi xử lý request.
- Ghi rõ giới hạn, ví dụ **attempts phải lớn hơn 0** và **delayMillis không âm**, trong tài liệu annotation type.
- Không tuyên bố những ràng buộc domain được kiểm tra chỉ vì Java kiểm tra kiểu dữ liệu.

**String path()** cũng cho phép chuỗi rỗng hoặc chuỗi không bắt đầu bằng "/". Kiểu String không tự xác thực quy tắc đường dẫn HTTP. Nếu một format thật sự cố định và compiler có thể kiểm tra, dùng processor hoặc tool phân tích phù hợp.

## 13. Ảnh hưởng của lựa chọn element tới khả năng nâng cấp API

Annotation có thể là API công khai được hàng trăm class sử dụng. Khi thay đổi một element cần xét ba chiều: **mã nguồn mới có biên dịch không**, **binary đã biên dịch có còn đọc được không**, và **hành vi tiêu thụ metadata có đổi không**.

| Thay đổi | Rủi ro cần đánh giá |
| --- | --- |
| Thêm element có **default** | Nơi sử dụng cũ thường không phải truyền element mới khi biên dịch lại; nhưng công cụ tiêu thụ có thể thay đổi hành vi |
| Thêm element **bắt buộc** (không default) | Mã nguồn hiện có không khai báo element mới có thể không biên dịch lại được; binary cũ có thể thiếu giá trị khi được đọc |
| Đổi tên element | Những nơi dùng tên cũ không còn phù hợp; mã tiêu thụ cũng phải sửa |
| Đổi kiểu **String** sang enum | Thay đổi hợp đồng source và các dữ liệu annotation đã biên dịch; cần migration |
| Xóa element/default | Có thể làm phần mềm đọc metadata cũ gặp lỗi hoặc thiếu giá trị |
| Đổi **default** từ 3 sang 5 | Có thể đổi giá trị hiệu lực của annotation ở binary cũ dù chưa biên dịch lại |
| Đổi tên hằng enum | Nơi sử dụng cũ có thể không tìm thấy hằng khi đọc metadata phiên bản mới |
| Mở rộng **@Target** | Cho phép thêm vị trí sử dụng, nhưng cần chắc rằng công cụ tiêu thụ hiểu các vị trí mới |

Một ví dụ an toàn hơn khi **thêm thông tin tùy chọn**:

~~~java
// Phiên bản ban đầu
@interface RetryV1 {
    int attempts();
}

// Phiên bản phát triển với thêm element có default
@interface RetryV2 {
    int attempts();
    long delayMillis() default 100;
}
~~~

Hai khai báo trên dùng **tên khác nhau để minh họa trước–sau trong cùng một đoạn mã**, không phải cách migration bắt buộc. Trong thư viện thực tế, nếu muốn phát triển một kiểu **Retry** duy nhất, bạn sẽ thay đổi định nghĩa **Retry** qua các phiên bản và đánh giá compatibility theo API Java.

Khi phải thêm một element bắt buộc, hãy cân nhắc xem thật sự mọi nơi sử dụng đều cần cung cấp thông tin đó không. Nếu không, thêm một default hợp lý thường giảm tác động tới mã nguồn cũ. Nhưng **không chọn default giả chỉ để làm mã cũ biên dịch** khi giá trị không có ý nghĩa an toàn.

## 14. @Target và @Retention cũng là một phần thiết kế tối giản

Số lượng element ít không đồng nghĩa annotation có thiết kế tốt nếu nơi dùng hoặc thời gian tồn tại của metadata không rõ.

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Timed {
    long warningMillis() default 250;
}
~~~

**@Target(METHOD)** nói rằng annotation thuộc phương thức, không tùy tiện gắn ở class/field. **@Retention(RUNTIME)** chỉ chọn khi mã/runtime framework cần reflection truy vấn.

Nếu annotation chỉ dùng để **annotation processor** sinh code lúc compile, **@Retention(SOURCE)** có thể đủ. Nếu cần runtime reflection, phải dùng **RUNTIME**. Mặc định của annotation khi không có **@Retention** là **RetentionPolicy.CLASS**, không phải RUNTIME.

Không bổ sung các meta-annotation như **@Inherited**, **@Repeatable** chỉ để trông có vẻ đầy đủ. Chúng có ý nghĩa riêng và tăng ràng buộc khi công cụ đọc metadata. Dùng khi yêu cầu sử dụng thực tế cần kế thừa hoặc lặp annotation.

**Không nhầm** số lượng annotation elements với số lượng meta-annotation. **@Target** và **@Retention** được gắn lên định nghĩa kiểu annotation, nhưng không phải element của kiểu **Timed**.

## 15. Khi nào không nên lưu dữ liệu bằng annotation?

Giả sử cần ánh xạ 20 endpoint tới URL thay đổi theo môi trường (dev/staging/prod), token, hạn mức và biểu thức điều kiện từ người dùng. Nếu tất cả phải nằm trong annotation:

- Mỗi thay đổi cấu hình có thể yêu cầu sửa source hoặc biên dịch/triển khai lại.
- Các element hợp lệ của Java không hỗ trợ cấu trúc dữ liệu tùy ý như Map/List phong phú.
- Dữ liệu cấu hình có thể nhanh chóng vượt quá mức rõ ràng của một annotation.
- Bí mật như password/API key không nên được nhúng trực tiếp trong metadata của class file hay source repository.

Một thiết kế hợp lý thường để annotation làm **khóa nhận diện hoặc mô tả liên kết**, còn dữ liệu runtime nằm trong cấu hình hoặc dependency injection:

~~~java
@interface ConfigurationKey {
    String value();
}

@ConfigurationKey("billing.retry-policy")
class BillingClient {}
~~~

Ở đây annotation chỉ chỉ ra một **key**. Mã ứng dụng sau đó tra thông số trong một nguồn cấu hình phù hợp, thay vì nhét nhiều giá trị runtime vào declaration. Thí dụ này là cách tách trách nhiệm; bản thân **@ConfigurationKey** không tự đọc file cấu hình.

## 16. Checklist thiết kế trước khi công bố annotation mới

Trước khi công bố một annotation dùng chung, nên xem xét:

- **Một trách nhiệm:** Tên annotation diễn tả rõ một mục đích, không gộp những lĩnh vực không liên quan.
- **Số phần tử tối thiểu hợp lý:** Mỗi element có người sử dụng và ý nghĩa rõ ràng; bỏ element suy ra được từ element khác.
- **Tên tự giải thích:** Người đọc có hiểu **attempts()**, **delayMillis()**, **ownerTeam()** mà không đoán đơn vị hoặc ý nghĩa không?
- **Kiểu chặt chẽ:** Chọn enum khi tập lựa chọn đóng, **Class<? extends ...>** khi tham chiếu kiểu Java, primitive khi thật sự là số/boolean, một chiều array khi có danh sách nhỏ.
- **Giá trị bắt buộc được cưỡng chế:** Không lạm dụng default để che giấu dữ liệu bắt buộc.
- **Default an toàn và có nghĩa:** Có thể áp dụng nhất quán, được tài liệu hóa và được test vì thay đổi default có thể ảnh hưởng binary cũ.
- **Target đúng:** Chỉ cho phép các declaration/type-use contexts mà thành phần tiêu thụ hỗ trợ.
- **Retention đúng:** SOURCE, CLASS hay RUNTIME phù hợp thời điểm đọc metadata.
- **Validation domain:** Giá trị sai về nghiệp vụ như số âm/đường dẫn rỗng được processor hoặc ứng dụng bắt lỗi.
- **Khả năng nâng cấp:** Có kế hoạch khi thêm/xóa/đổi tên element hoặc enum constant.
- **Tài liệu sử dụng:** Ít nhất có ví dụ gắn annotation, giải thích element quan trọng và trường hợp thiếu annotation.

Có thể áp dụng nguyên tắc **“mỗi element phải trả lời một câu hỏi cần thiết”**. Nếu không chỉ rõ được câu hỏi, element đó có thể chưa cần nằm trong API công khai.

## 17. Lỗi thường gặp và cách sửa

| Lỗi | Vấn đề | Hướng xử lý |
| --- | --- | --- |
| Dồn route, auth, retry, logging, UI vào một annotation | Quá nhiều trách nhiệm | Tách annotation theo ý nghĩa gắn kết |
| Thêm boolean **enabled() default true** cho marker không cần dữ liệu | Làm phức tạp giao diện | Dùng marker thực sự nếu chỉ biểu diễn có/không |
| Dùng **String delay()** | Không có ràng buộc số và đơn vị | Dùng **long delayMillis()** |
| Dùng **String mode()** cho tập lựa chọn cố định | Cho phép lỗi gõ chuỗi | Dùng enum |
| Dùng **String handlerClass()** cho một class Java tồn tại | Không được compiler kiểm tra tham chiếu | Dùng **Class<? extends Handler>** |
| Khai báo **List<String>**, **Map<...>** trong @interface | Kiểu element không hợp lệ | Cân nhắc mảng một chiều hoặc cấu hình ngoài |
| Cố khai báo **int[][]** | Mảng hai chiều không hợp lệ | Thiết kế lại cấu trúc, có thể dùng annotation lồng nhau |
| Dùng default tùy tiện cho đường dẫn bắt buộc | Không phát hiện thiếu cấu hình | Bỏ default để compiler yêu cầu truyền rõ |
| Mong enum/int tự kiểm tra mọi rule nghiệp vụ | Compiler chỉ kiểm tra kiểu/tên hằng | Thêm validation trong processor/runtime |
| Đổi default mà bỏ qua binary cũ | Default áp dụng khi annotation được đọc | Kiểm thử các class cũ chưa truyền tường minh element |
| Nghĩ **@Target** hoặc **@Retention** là element | Đây là meta-annotation của annotation type | Phân biệt cấu hình loại annotation với các element của nó |
| Dùng mảng song song **names** và **values** | Dễ lệch độ dài/thứ tự | Dùng mảng annotation **@Header(name, value)** |
| Lưu token/bí mật trong annotation | Giá trị có thể có trong source/class metadata | Dùng cơ chế quản lý bí mật ngoài mã nguồn |

## 18. Bài tập và đáp án tự kiểm tra

**Bài 1.** Thiết kế annotation để chỉ đánh dấu method có kiểm toán. Nên chọn:

~~~java
@interface Audited {}
~~~

hay:

~~~java
@interface Audited {
    boolean enabled() default true;
    String code() default "";
}
~~~

**Đáp án:** Chọn marker nếu chỉ cần hiện diện/vắng mặt. Chỉ thêm element khi thực sự có quyết định cấu hình độc lập mà người dùng phải khai báo.

**Bài 2.** Thiết kế annotation cho một đường dẫn bắt buộc và phương thức HTTP thuộc tập **GET, POST, DELETE**, mặc định GET. Một phương án:

~~~java
enum HttpMethod {
    GET, POST, DELETE
}

@interface HttpRoute {
    String value();
    HttpMethod method() default HttpMethod.GET;
}
~~~

Dùng **@HttpRoute("/orders")** hoặc **@HttpRoute(value = "/orders", method = HttpMethod.POST)**. **value()** phù hợp với đường dẫn chính; enum giúp tránh typo ở method.

**Bài 3.** **@Retry(attempts = 0)** có chắc chắn gây lỗi compile-time khi attempts() là int không? **Không**. 0 hợp lệ theo kiểu int; chỉ có processor/framework kiểm tra domain mới từ chối.

**Bài 4.** Tại sao **@UseHandler(DefaultHandler.class)** tốt hơn **@UseHandlerName("demo.DefautHandler")** khi API cần class Java? Class literal và **Class<? extends Handler>** được kiểm tra kiểu và hỗ trợ công cụ refactor, còn chuỗi có thể sai mà compiler không phát hiện.

**Bài 5.** Nếu cần lưu các cặp header HTTP, phương án nào hạn chế lỗi hơn: hai mảng String tên/giá trị hay **Header[]** của annotation lồng nhau? **Header[]** vì mỗi cặp giữ cùng một cấu trúc và không thể bị lệch chỉ số giữa hai mảng.

**Bài 6.** Khi đổi default retries từ 3 sang 5, class cũ dùng **@Retry** có thể nhận giá trị nào nếu chạy với annotation type mới? **5**, nếu không truyền retries tường minh và thư viện đọc kiểu mới. Class dùng **@Retry(retries = 3)** vẫn có giá trị 3.

**Bài 7.** Một API có 11 element, 9 element chỉ dùng ở một thành phần cấu hình môi trường. Có nhất thiết cắt bỏ 9 element đó không? Không máy móc; phải xét trách nhiệm và yêu cầu runtime. Nhưng đây là dấu hiệu cần đánh giá lại: có thể nên giữ annotation như một khóa, chuyển cấu hình biến động sang nơi khác.

## 19. Tài liệu chuẩn

- **Java Language Specification §9.6.1 — Annotation Interface Elements:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.1 — tập kiểu element hợp lệ, cú pháp và các ràng buộc của annotation interface.
- **Java Language Specification §9.6.2 — Defaults for Annotation Interface Elements:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.2 — cách khai báo default và quy tắc áp dụng động khi đọc annotation.
- **Java Language Specification §9.7 — Annotations:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.7 — cấu trúc cặp tên–giá trị, shorthand value và annotation element values.
- **Java SE 17 — ElementType:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html — các vị trí @Target có thể khai báo.
- **Java SE 17 — RetentionPolicy:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html — các chính sách SOURCE, CLASS, RUNTIME.

**Kết luận:** Annotation tốt là một giao diện metadata **nhỏ nhưng đủ nghĩa**. Mỗi element nên có tên dễ hiểu, kiểu chặt chẽ trong giới hạn của Java, trạng thái bắt buộc/default có chủ đích và một lý do rõ ràng để tồn tại. Chọn marker khi chỉ cần đánh dấu, dùng **value()** cho một thông tin trung tâm, dùng enum/Class/mảng/annotation lồng nhau khi mô hình cần, và chuyển cấu hình biến động/phức tạp ra ngoài thay vì biến annotation thành một đối tượng cấu hình đa năng.
