# Thời điểm đánh giá receiver và lỗi khi receiver null trong Java Method Reference

## 1. Trọng tâm: tạo method reference không giống gọi phương thức

Java method reference (`::`) cho phép cung cấp một cách gọi phương thức hoặc constructor làm hành vi phù hợp với **functional interface**. Ví dụ, `Supplier<String>` có một phương thức chức năng `String get()`, nên có thể nhận một method reference đến phương thức instance không có đối số và trả `String`.

Điểm rất quan trọng khi chuyển lambda sang method reference là **thời điểm đánh giá receiver** — đối tượng sẽ nhận lời gọi phương thức instance.

~~~java
Service service = new Service();
java.util.function.Supplier<String> action = service::read;
~~~

Ở đây `service` đứng **bên trái `::` dưới dạng một biểu thức chỉ đến đối tượng cụ thể**. Java đánh giá biểu thức `service` **ngay lúc tạo method reference**, kiểm tra kết quả có `null` hay không, rồi giữ đối tượng nhận được để gọi `read` sau này. Nó **chưa chạy phương thức `read()`** tại thời điểm tạo reference.

Nếu receiver là `null`, **`NullPointerException` được ném ngay khi đánh giá biểu thức method reference**, kể cả khi callback chưa được gọi lần nào.

Ngược lại:

~~~java
java.util.function.Supplier<String> action =
        () -> service.read();
~~~

Với lambda trên, thân `service.read()` thường chỉ chạy lúc `action.get()` được gọi. Nếu `service` là `null`, lỗi xảy ra **khi gọi callback**, không phải lúc tạo lambda. Nếu `service` là biến local được lambda tham chiếu, nó còn phải thỏa quy tắc `final` hoặc *effectively final*.

> Quy tắc ghi nhớ: `objectExpression::instanceMethod` **đánh giá receiver trước**; `() -> objectExpression.instanceMethod()` **để việc đánh giá trong thân lambda đến lúc gọi**. Đừng đánh đồng hai biểu thức chỉ vì chúng có thể trả cùng kết quả với receiver ổn định, không null.

Các quy tắc này đã có từ Java 8 và tiếp tục áp dụng trên Java hiện đại.

## 2. Phân biệt các dạng method reference

Không phải mọi biểu thức dùng `::` đều có receiver được đánh giá trước. Cần phân biệt **bound instance reference**, **unbound instance reference**, **static method reference** và **constructor reference**.

| Dạng | Ví dụ | Receiver ở đâu? | Thời điểm receiver được xác định |
| --- | --- | --- | --- |
| Bound instance | `service::read` | Biểu thức `service` bên trái `::` | Ngay khi tạo reference |
| Bound instance có biểu thức | `holder.current::read` | Kết quả đánh giá `holder.current` | Ngay khi tạo reference; đánh giá một lần |
| Unbound instance | `Service::read` | Đối số đầu tiên của functional method | Khi callback được gọi |
| Static method | `Integer::parseInt` | Không có receiver instance | Không có bước null-check receiver instance |
| Constructor | `Service::new` | Chưa có đối tượng; sẽ tạo đối tượng mới | Khi callback được gọi |

**Bound instance reference** thường phù hợp với `Supplier<R>`, `Runnable` hoặc `Consumer<A>` khi receiver đã cố định.

**Unbound instance reference** ví dụ `String::length` thường phù hợp với `Function<String,Integer>` hoặc `ToIntFunction<String>`, vì đối số của functional method chính là đối tượng `String` để gọi `length()`.

**Static reference** ví dụ `Integer::parseInt` không capture đối tượng nhận; nó chỉ gọi static method với các đối số được cung cấp khi thực thi hành vi. **Constructor reference** ví dụ `ArrayList::new` tạo object khi được gọi, không phải khi khai báo tham chiếu.

### Cùng tên phương thức, thời điểm khác nhau

~~~java
// Các mảnh mã minh họa, giả định đã có Service.read() -> String:
Supplier<String> a = service::read;
Supplier<String> b = () -> service.read();
Function<Service, String> c = Service::read;
~~~

- `a` đánh giá `service` ngay khi khởi tạo `a`. Nếu null, lỗi xuất hiện ngay.
- `b` chưa đánh giá lời gọi trong thân lambda. Việc tham chiếu biến local `service` đòi hỏi nó effectively final.
- `c` không cần một đối tượng `Service` khi tạo. Khi gọi `c.apply(someService)`, `someService` trở thành receiver; nếu truyền null, lỗi xảy ra lúc gọi.

Các dòng trên không phải chương trình chạy độc lập; hai chương trình hoàn chỉnh ở phần sau minh họa với kết quả xác định.

## 3. Khi tạo bound reference: điều gì được đánh giá ngay?

Xét:

~~~java
Supplier<String> supplier = findService()::read;
~~~

Đây là mảnh mã minh họa, cần có `findService()`, `read()` và `Supplier` phù hợp.

Thứ tự có ý nghĩa:

1. Java **đánh giá biểu thức `findService()`**, nghĩa là `findService` có thể được gọi ngay tại dòng này.
2. Nếu biểu thức trả `null`, việc đánh giá bound method reference ném `NullPointerException` ngay. Callback không được tạo thành công và chưa có lần gọi `supplier.get()` nào.
3. Nếu trả một đối tượng không null, method reference giữ **receiver được đánh giá ở bước 1**.
4. Phần thân `read()` chưa chạy. Nó chỉ được gọi khi một nơi gọi phương thức chức năng, ví dụ `supplier.get()`.
5. Trong những lần gọi sau, chính đối tượng đã được giữ ở bước 3 là receiver. Không tự động chạy lại `findService()` để lấy receiver mới.

Điều đó khác rõ rệt với:

~~~java
Supplier<String> supplier = () -> findService().read();
~~~

Khi tạo lambda, `findService()` trong thân chưa chạy. Mỗi lần `supplier.get()` gọi thân lambda, `findService()` mới được đánh giá. Vì vậy nếu kết quả `findService()` thay đổi theo thời gian, callback có thể dùng những receiver khác nhau ở mỗi lần gọi.

**Không suy rộng sai:** tạo bound reference không gọi `read()`; nó chỉ đánh giá **biểu thức receiver**. Nếu biểu thức receiver chứa method call như `findService()`, method call đó chạy ngay vì nó được dùng để **tìm receiver**, không phải vì method reference đã gọi phương thức đích.

### Những side effect của biểu thức receiver

Nếu `findService()` có log, tăng bộ đếm hoặc truy vấn tài nguyên, những hành động đó có thể xảy ra ngay khi tạo `findService()::read`. Với lambda `() -> findService().read()`, chúng xảy ra lúc gọi callback. Đó là sự khác biệt hành vi quan sát được, không chỉ khác hiệu năng.

Vì vậy không nên thay thế máy móc:

~~~java
() -> loadReceiver().execute()
~~~

bằng:

~~~java
loadReceiver()::execute
~~~

khi `loadReceiver()` có side effect, có thể trả null, hoặc trả các đối tượng khác nhau qua thời gian.

## 4. Ví dụ chạy đầy đủ 1: receiver được lấy một lần hay mỗi lần gọi?

Tạo tệp **ReceiverTimingDemo.java**:

~~~java
import java.util.function.Supplier;

public class ReceiverTimingDemo {
    static final class Service {
        private final String name;

        Service(String name) {
            this.name = name;
        }

        String read() {
            return name;
        }
    }

    static final class Holder {
        Service current;

        Holder(Service initial) {
            this.current = initial;
        }
    }

    static Service find(Holder holder) {
        System.out.println("find");
        return holder.current;
    }

    public static void main(String[] args) {
        Holder holder = new Holder(new Service("A"));

        Supplier<String> bound = find(holder)::read;
        Supplier<String> deferred = () -> find(holder).read();

        System.out.println("created");
        System.out.println("bound1=" + bound.get());
        System.out.println("deferred1=" + deferred.get());

        holder.current = new Service("B");

        System.out.println("bound2=" + bound.get());
        System.out.println("deferred2=" + deferred.get());
    }
}
~~~

Biên dịch/chạy bằng JDK 17+; ví dụ chỉ dùng cú pháp/API đã có từ Java 8:

~~~bash
javac ReceiverTimingDemo.java
java ReceiverTimingDemo
~~~

**Stdout chính xác:**

~~~text
find
created
bound1=A
find
deferred1=A
bound2=A
find
deferred2=B
~~~

Giải thích:

- `find(holder)::read` gọi `find(holder)` ngay **một lần** lúc tạo bound reference. Vì vậy `find` được in trước `created`; `bound` giữ receiver `Service("A")`.
- `() -> find(holder).read()` chưa gọi `find` lúc tạo. Mỗi lần `deferred.get()`, phương thức `find` chạy và in ra một dòng `find`.
- Sau khi `holder.current = new Service("B")`, bound reference vẫn giữ đối tượng `A` cũ, nên `bound2=A`; lambda đọc lại `holder.current` và trả `B`.
- Thân phương thức `read()` không tạo dòng log; chỉ `find` in log. Vì thế số dòng `find` chứng minh **thời điểm đánh giá receiver**, không phải số lần gọi `read`.

Trong chương trình này, biến local `holder` không bị gán lại nên lambda có thể capture nó. Việc thay đổi **field `holder.current`** không phá vỡ tính effectively final của biến local `holder`.

## 5. Trường hợp receiver `null`: lỗi xảy ra ở đâu?

Với bound reference:

~~~java
Service service = null;
Supplier<String> task = service::read;
// Ném NullPointerException tại dòng khởi tạo task.
~~~

Đây là mảnh mã minh họa. Receiver null bị phát hiện **ngay khi đánh giá `service::read`**, không phải khi gọi `task.get()`.

Với lambda:

~~~java
Service service = null;
Supplier<String> task = () -> service.read();
// Đến đây chưa gọi read() và chưa ném NPE từ lời gọi read.
task.get(); // Ném NullPointerException khi thân lambda chạy.
~~~

Nếu service là local không bị gán lại, hai dòng trên hợp lệ về ràng buộc capture. Nếu đặt `service = ...` ở phía sau, lambda sẽ **không biên dịch** vì biến local không còn effectively final — hoàn toàn khác với việc một **field của holder** đổi đối tượng.

Với unbound reference:

~~~java
Function<Service, String> task = Service::read;
task.apply(null); // NPE khi callback được gọi với receiver null.
~~~

`Service::read` không đánh giá một đối tượng `Service` cụ thể khi khởi tạo. Đối tượng đến từ tham số đầu tiên khi gọi `Function.apply`, nên null-check liên quan receiver diễn ra ở **thời điểm gọi**.

**Chú ý:** lỗi NPE không nhất thiết xảy ra “ngay ở `test` hay `apply`” nếu một callback không bao giờ được gọi. Với bound reference, ngược lại, NPE có thể xảy ra dù callback sẽ không bao giờ được sử dụng.

## 6. Ví dụ chạy đầy đủ 2: cùng receiver null, ba thời điểm khác nhau

Tạo tệp **ReceiverNullDemo.java**:

~~~java
import java.util.function.Function;
import java.util.function.Supplier;

public class ReceiverNullDemo {
    static final class Service {
        String read() {
            return "ready";
        }
    }

    static Service getMissingService() {
        System.out.println("receiver expression");
        return null;
    }

    public static void main(String[] args) {
        try {
            Supplier<String> bound = getMissingService()::read;
            System.out.println("unreachable: " + bound.get());
        } catch (NullPointerException ex) {
            System.out.println("bound creation: NPE");
        }

        Supplier<String> deferred =
                () -> getMissingService().read();
        System.out.println("lambda created");

        try {
            deferred.get();
        } catch (NullPointerException ex) {
            System.out.println("lambda invocation: NPE");
        }

        Function<Service, String> unbound = Service::read;
        System.out.println("unbound created");

        try {
            unbound.apply(null);
        } catch (NullPointerException ex) {
            System.out.println("unbound invocation: NPE");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ReceiverNullDemo.java
java ReceiverNullDemo
~~~

**Stdout chính xác:**

~~~text
receiver expression
bound creation: NPE
lambda created
receiver expression
lambda invocation: NPE
unbound created
unbound invocation: NPE
~~~

Diễn giải theo thứ tự thực thi:

1. `getMissingService()::read` phải đánh giá `getMissingService()` ngay. Hàm in `receiver expression`, trả null, sau đó method reference ném NPE. Vì vậy không có dòng `unreachable`.
2. `() -> getMissingService().read()` chỉ tạo lambda, nên in `lambda created` được thực hiện trước khi hàm `getMissingService()` trong thân lambda chạy.
3. Đến `deferred.get()`, thân lambda đánh giá `getMissingService()`, in `receiver expression`, trả null và ném NPE; khối catch in `lambda invocation: NPE`.
4. `Service::read` được tạo mà không cần receiver instance. Chỉ khi gọi `unbound.apply(null)` mới có receiver null và NPE được bắt.
5. Những dòng `try/catch` ở đây chỉ để chứng minh thời điểm phát sinh lỗi. Trong sản phẩm thật nên chủ động xác định chính sách cho receiver thiếu, thay vì dùng NPE làm nhánh nghiệp vụ thông thường.

Ví dụ không dựa vào nội dung thông báo NPE cụ thể (thông báo có thể khác nhau giữa môi trường); nó bắt đúng **loại ngoại lệ** và in thông điệp ổn định do ứng dụng tự định nghĩa.

## 7. `object::method` giữ object reference, không chụp kết quả phương thức

Một hiểu lầm phổ biến: khi tạo `service::read`, Java đã “chụp sẵn” kết quả của `read()`. Điều này **không đúng**. Java giữ receiver; **mỗi lần thực thi SAM**, method reference mới gọi method trên receiver đó.

Nếu chính đối tượng đó có trạng thái mutable, method reference sẽ nhìn thấy trạng thái của đối tượng theo quy tắc truy cập bộ nhớ thông thường:

~~~java
// Mảnh mã minh họa trong một phương thức:
StringBuilder builder = new StringBuilder("A");
Supplier<String> read = builder::toString;

builder.append("B");
System.out.println(read.get()); // AB

builder.append("C");
System.out.println(read.get()); // ABC
~~~

`read` giữ cùng một đối tượng `StringBuilder`; không giữ một bản sao bất biến của chuỗi. `toString()` được gọi lại ở mỗi `get()`, nên kết quả phản ánh nội dung cập nhật.

Từ đây phân biệt ba thời điểm:

1. **Đánh giá biểu thức receiver** khi tạo bound reference.
2. **Gọi phương thức đích** khi SAM được gọi.
3. **Đọc trạng thái bên trong đối tượng** khi phương thức đích thực sự thực thi.

Một đối tượng có thể cố định ở bước 1 nhưng trạng thái được dùng ở bước 3 vẫn thay đổi.

### Khi local receiver được gán lại

Bound reference giữ **giá trị object reference đã đánh giá**, không cần tham chiếu lại biến local mỗi lần chạy:

~~~java
// Mảnh mã minh họa bên trong phương thức:
StringBuilder builder = new StringBuilder("Old");
Supplier<String> original = builder::toString;

builder = new StringBuilder("New");
System.out.println(original.get()); // Old
~~~

Đoạn trên hợp lệ: việc gán lại biến local `builder` **không làm thay đổi receiver đã bound** vào `original`. Ngược lại, nếu viết `Supplier<String> original = () -> builder.toString();` rồi gán lại `builder`, trình biên dịch sẽ từ chối lambda vì biến local bị capture không effectively final.

Điều này không có nghĩa method reference cho phép phá ràng buộc effectively final của bất kỳ biến nào. Nó chỉ minh họa rằng receiver expression của bound reference được **đánh giá ở thời điểm tạo**. Nếu bạn viết một lambda khác bên trong quá trình dựng receiver, các quy tắc capture biến local vẫn áp dụng cho lambda đó.

## 8. Biểu thức field, đối tượng thay thế và null thay đổi theo thời gian

Giả sử một `Holder` có field `current` trỏ đến một dịch vụ:

~~~java
// Mảnh mã minh họa, giả định Holder.current và Service.read đã tồn tại:
Supplier<String> fixed = holder.current::read;
Supplier<String> dynamic = () -> holder.current.read();
~~~

Hai cách này có hợp đồng trả `String` giống nhau, nhưng:

- Với `fixed`, **biểu thức `holder.current` được đánh giá ngay**. Nếu null ở thời điểm này, NPE xuất hiện lập tức. Nếu không null, reference giữ đối tượng được đọc ra lúc đó.
- Với `dynamic`, **lần đọc field `holder.current` xảy ra trong thân lambda**. Nó có thể là một đối tượng khác hoặc null ở lần thực thi tiếp theo.
- Nếu `holder.current` bị thay sang đối tượng mới, `fixed` vẫn dùng receiver cũ. Nếu bản thân receiver cũ bị thay đổi trạng thái, `fixed` có thể phản ánh trạng thái mới của chính đối tượng cũ.
- Nếu nhiều luồng đọc/ghi `holder.current`, việc thấy bản cập nhật mới nhất còn phụ thuộc **Java Memory Model**, đồng bộ hoặc `volatile`; không được dựa vào lambda để tự tạo bảo đảm visibility.

### Một rủi ro về vòng đời

Khi một callback được lưu trong listener, executor hoặc scheduler, bound reference như `service::read` có thể giữ cho `service` tiếp tục được tham chiếu khi callback còn được giữ. Nếu dịch vụ có tài nguyên cần đóng, việc giữ reference **không đồng nghĩa tài nguyên còn dùng được**. Cần quản lý vòng đời callback và tài nguyên riêng, không dựa vào garbage collector để hoàn tất nghiệp vụ.

Nếu API thực sự cần đọc dịch vụ mới nhất khi thực thi, lambda truy cập `holder.current` có thể diễn đạt điều đó rõ hơn. Nếu API cần làm việc với đúng phiên bản dịch vụ tại lúc tạo callback, bound reference phù hợp hơn — với điều kiện receiver được xác nhận không null và vòng đời hợp lệ.

## 9. `TypeName::instanceMethod`: receiver là tham số đầu tiên

Ví dụ kinh điển:

~~~java
java.util.function.ToIntFunction<String> length = String::length;
System.out.println(length.applyAsInt("Java")); // 4
~~~

Dạng `String::length` không có biểu thức `String` instance bên trái `::`. Nó nói rằng “khi callback được gọi, lấy đối số `String` làm receiver và gọi `length()`”.

Có thể hình dung tương đương khi receiver không null:

~~~java
java.util.function.ToIntFunction<String> length =
        text -> text.length();
~~~

Nhưng:

~~~java
java.util.function.ToIntFunction<String> length = String::length;
length.applyAsInt(null); // NPE tại thời điểm gọi SAM
~~~

Không có receiver null ở thời điểm *khởi tạo* `String::length`; nó chỉ xuất hiện khi truyền null vào `applyAsInt`.

Dạng unbound còn áp dụng cho phương thức có tham số. Chẳng hạn:

~~~java
java.util.function.BiPredicate<String, String> startsWith =
        String::startsWith;

System.out.println(startsWith.test("Java", "Ja")); // true
~~~

Trong lời gọi này, **tham số thứ nhất** của `BiPredicate.test` là receiver `"Java"`; **tham số thứ hai** là đối số `"Ja"` đưa vào `String.startsWith`. Nếu tham số thứ nhất null, lời gọi bị NPE; nếu tham số thứ hai null, `String.startsWith` có thể ném NPE theo hợp đồng của chính phương thức. Dạng method reference không tự thêm null validation.

### Static method reference không có receiver instance

~~~java
java.util.function.Function<String, Integer> parse =
        Integer::parseInt;
~~~

`Integer::parseInt` gọi một **static method**. Không có receiver instance cần kiểm tra tại thời điểm tạo; lỗi như `NumberFormatException` khi chuỗi không hợp lệ chỉ xảy ra lúc `parse.apply(text)` thực thi.

**Cẩn thận**: không phải cứ `TypeName::methodName` là unbound instance reference. Khi phương thức được chọn là `static`, nó là static method reference. Kiểu đích và quy tắc phân giải overload quyết định phương thức được tham chiếu.

## 10. Constructor reference cũng không tạo đối tượng ngay

Một constructor reference:

~~~java
java.util.function.Supplier<java.util.ArrayList<String>> factory =
        java.util.ArrayList<String>::new;
~~~

Mới tạo một hành vi **sẽ tạo danh sách** khi `factory.get()` được gọi:

~~~java
java.util.ArrayList<String> first = factory.get();
java.util.ArrayList<String> second = factory.get();

System.out.println(first == second); // false
~~~

Hai lần gọi tạo hai instance khác nhau. Không có receiver instance ở bên trái `::new` để null-check tại thời điểm tạo. Điều này khác với `someList::size`, vốn bound vào một danh sách đã tồn tại.

Tương tự, `String[]::new` phù hợp với `IntFunction<String[]>`: tham số số nguyên cho biết độ dài mảng cần tạo **khi callback được gọi**. Kích thước âm sẽ gây lỗi lúc gọi, không phải lúc khởi tạo reference.

Các trường hợp constructor/static được nêu ở đây để **phân biệt đúng loại method reference**; trọng tâm của bài vẫn là receiver của instance method.

## 11. Xử lý null có chủ đích ở đúng ranh giới

Một API nhận callback cần quyết định: receiver bắt buộc tồn tại ngay bây giờ, hay có thể chưa tồn tại và sẽ được cung cấp lúc chạy?

### 11.1. Receiver bắt buộc có mặt tại lúc đăng ký callback

Nếu `service` phải hợp lệ khi dựng callback, hãy kiểm tra rõ ở ranh giới:

~~~java
// Mảnh mã minh họa, cần có biến service và kiểu Service:
Service validated = java.util.Objects.requireNonNull(
        service, "service must exist at registration"
);

Supplier<String> callback = validated::read;
~~~

`requireNonNull` báo lỗi có chủ đích và thông điệp rõ. Dù `validated::read` cũng sẽ ném NPE nếu receiver null, kiểm tra ranh giới riêng giúp xác định **hợp đồng**: tại thời điểm đăng ký, dịch vụ phải hiện diện. Trong môi trường thực tế, có thể thêm xác thực vòng đời hoặc trạng thái trước khi đăng ký.

### 11.2. Receiver có thể chưa tồn tại: định nghĩa chính sách khi gọi

Nếu việc có dịch vụ là tùy chọn và có thể thay đổi, không dùng một bound reference từ field hiện tại với kỳ vọng nó sẽ tự cập nhật về sau. Hãy quyết định fallback:

~~~java
// Mảnh mã minh họa, giả định Holder.current có thể null:
Supplier<String> callback = () -> {
    Service current = holder.current;
    return current == null ? "UNAVAILABLE" : current.read();
};
~~~

Ở mỗi lần `callback.get()`, lambda đọc `holder.current` và kiểm tra null. Điều này **không** tự giải quyết thread safety của field; nếu nhiều luồng cập nhật/đọc, phải dùng cơ chế đồng bộ hoặc thiết kế xuất bản trạng thái phù hợp.

### 11.3. Receiver có thể null ngay bây giờ, muốn fallback cố định

Nếu chính sách là chốt trạng thái tại thời điểm tạo, có thể chọn callback lúc đăng ký:

~~~java
// Mảnh mã minh họa:
Service snapshot = holder.current;
Supplier<String> callback =
        snapshot == null ? () -> "UNAVAILABLE" : snapshot::read;
~~~

Nếu `snapshot` null, nhánh `snapshot::read` không được đánh giá. Nếu khác null, reference cố định receiver `snapshot`. Đây là **lựa chọn snapshot về đối tượng**, không phải snapshot về dữ liệu mà `read()` trả về.

### 11.4. Không dùng exception để thay thế thiết kế trạng thái

Không nên dùng cách sau làm luồng nghiệp vụ chính:

~~~java
// Mảnh mã minh họa về anti-pattern:
try {
    Supplier<String> action = holder.current::read;
    // đăng ký action
} catch (NullPointerException ignored) {
    // tự động bỏ qua việc đăng ký
}
~~~

Bắt NPE quá rộng dễ che lỗi lập trình hoặc trạng thái sai không liên quan đến “dịch vụ chưa tồn tại”. Hãy kiểm tra null có chủ đích và quyết định rõ **bỏ qua**, **trả fallback**, **báo lỗi nghiệp vụ**, hay **đợi dịch vụ có mặt**.

## 12. Lưu ý về thời điểm thực thi callback và thread

Các API như executor, event handler, listener và stream đều có thể nhận method reference, nhưng không có nghĩa chúng thực thi ngay:

~~~java
// Mảnh mã minh họa:
Runnable r = service::refresh; // bound receiver được đánh giá ngay
executor.execute(r);           // executor quyết định lúc chạy refresh()
~~~

Nếu `service` là null, NPE xảy ra **trước khi gọi `executor.execute(r)`**. Nếu khác null, method reference giữ service, nhưng phương thức `refresh` chỉ chạy khi executor thực thi `Runnable.run()`.

So với:

~~~java
Runnable r = () -> holder.current.refresh();
executor.execute(r);
~~~

Trong trường hợp này, field `holder.current` được đọc khi task chạy; nếu thành null giữa lúc đăng ký và lúc chạy, NPE có thể xuất hiện **trên luồng thực thi task** thay vì luồng đăng ký. Điều đó ảnh hưởng nơi ghi nhận lỗi, cách truyền exception và thiết kế retry.

**Thêm hai giới hạn quan trọng:**

- *Có receiver ổn định không có nghĩa là object thread-safe.* Một bound reference dùng cùng đối tượng trong nhiều luồng có thể gây data race nếu phương thức hoặc trạng thái object không an toàn đồng thời.
- *Có reference không có nghĩa tài nguyên luôn sống.* Dịch vụ có thể đã đóng kết nối hoặc hết phiên dù object vẫn được tham chiếu. Cần kiểm tra/điều phối vòng đời, không chỉ null.

## 13. Bảng so sánh thời điểm và lỗi

| Biểu thức | Khi tạo | Khi gọi SAM | Receiver thay đổi sau lúc tạo? |
| --- | --- | --- | --- |
| `service::read` | Đánh giá `service` một lần, NPE nếu null | Gọi `read` trên object đã bound | Không đổi object được bound |
| `getService()::read` | Gọi `getService()` một lần, NPE nếu trả null | Gọi `read` trên object đã lấy | Không chạy lại `getService()` |
| `() -> getService().read()` | Chỉ tạo lambda | Gọi `getService()`, rồi `read`; có thể NPE | Có thể đổi qua từng lần gọi |
| `Service::read` | Không cần instance receiver | Đối số thứ nhất là receiver, có thể NPE nếu null | Tùy đối số mỗi lần gọi |
| `Integer::parseInt` | Không có receiver instance | Gọi static method, có thể báo lỗi parse | Không áp dụng |
| `Service::new` | Không tạo instance | Tạo object khi callback được gọi | Mỗi lần gọi có thể tạo object mới |

Đọc bảng theo đúng chữ “receiver”: đối tượng nhận lời gọi instance method. **Một biểu thức bên trái `::` là tên kiểu (`Service`) không tự tương đương với một receiver instance.**

## 14. Các lỗi và ngộ nhận thường gặp

1. **“Method reference chỉ là lambda ngắn nên luôn thay thế được.”** Sai khi khác thời điểm đánh giá receiver, null-check hoặc side effect của biểu thức receiver.
2. **“`service::read` gọi `read()` ngay.”** Sai: nó đánh giá và kiểm tra receiver ngay; phương thức đích chỉ chạy khi callback được gọi.
3. **“Null receiver chỉ gây lỗi lúc gọi `get()`.”** Sai đối với bound reference: lỗi xảy ra lúc tạo expression.
4. **“`Service::read` có cùng receiver với `service::read`.”** Sai: dạng `Service::read` là unbound instance method reference khi `read` là instance method, receiver được truyền khi gọi SAM.
5. **“Thay `holder.current` thì bound reference sẽ trỏ đến object mới.”** Sai: reference giữ object đã đánh giá tại lúc tạo.
6. **“Bound reference chụp sẵn kết quả `read()`.”** Sai: nó giữ object, rồi gọi method khi SAM thực thi. State nội bộ vẫn có thể đổi.
7. **“Đã bound object thì luôn an toàn luồng.”** Sai: chỉ cố định identity của receiver; không đảm bảo atomicity, visibility hoặc thread safety.
8. **“Lambda truy cập biến local có thể gán lại biến đó thoải mái.”** Sai: captured local trong lambda phải final hoặc effectively final.
9. **“Mọi dạng `Type::method` đều đánh giá receiver lúc tạo.”** Sai: static/unbound method references khác bound receiver expression.
10. **“Bắt `NullPointerException` ở mọi nơi là cách xử lý receiver thiếu.”** Sai về thiết kế: nên xác định chính sách null ở ranh giới thích hợp và phân biệt lỗi nghiệp vụ với bug.

## 15. Bài tập thực hành

**Bài 1 — Dự đoán lỗi.** Với `Service service = null;`, biểu thức nào ném NPE khi khởi tạo, biểu thức nào chỉ ném khi gọi?

~~~java
Supplier<String> a = service::read;
Supplier<String> b = () -> service.read();
Function<Service, String> c = Service::read;
~~~

Đây là ba mảnh mã **cần đặt độc lập** để lần tạo `a` không ngăn những phép gán sau được chạy. Đáp án: `a` ném lúc tạo; `b` tạo được nhưng `b.get()` ném; `c` tạo được nhưng `c.apply(null)` ném.

**Bài 2 — Đếm số lần lấy receiver.** Với `Supplier<String> bound = find(holder)::read;` và `Supplier<String> delayed = () -> find(holder).read();`, giả sử gọi `bound.get()` ba lần và `delayed.get()` hai lần. Khi `find` không được gọi ở nơi nào khác, `find` chạy bao nhiêu lần cho mỗi biểu thức? Đáp án: **1 lần** lúc tạo bound; **2 lần** lúc gọi delayed.

**Bài 3 — Thay field.** Một `Holder` có `current = Service("A")`. Tạo `fixed = holder.current::read` và `dynamic = () -> holder.current.read()`, rồi thay `current = Service("B")`. Hãy giải thích tại sao `fixed.get()` vẫn trả `A` còn `dynamic.get()` trả `B`, với giả định mỗi service có `read()` trả tên cố định.

**Bài 4 — Chuyển lambda sang method reference có an toàn không?** Phân tích:

~~~java
Supplier<String> lambda = () -> provider.resolve().read();
Supplier<String> methodRef = provider.resolve()::read;
~~~

Hãy liệt kê các khác biệt nếu `resolve()` có thể trả null, có log, hoặc lần đầu trả object A rồi lần sau trả B. Không chỉ trả lời “ngắn hơn/dài hơn”.

**Bài 5 — Giữ object, không giữ output.** Tạo một `StringBuilder("A")`; lập `Supplier<String> s = builder::toString`; gọi `builder.append("B")`, rồi `s.get()`. Kết quả gì? Thử gán lại biến `builder` sang một đối tượng mới; `s` có thay receiver không? So sánh với lambda capture biến local có bị gán lại.

**Bài 6 — Thiết kế với callback chạy sau.** Một tác vụ sẽ chạy trong executor sau khi người dùng đổi tài khoản hoặc sau khi kết nối có thể đóng. Quyết định tác vụ nên dùng receiver cố định hay đọc receiver mới ở thời điểm chạy; nêu chính sách null, vòng đời, an toàn luồng và nơi cần ghi nhận lỗi.

## 16. Checklist cho code review

Trước khi thay lambda thành method reference, hãy hỏi:

- Bên trái `::` là **biểu thức đối tượng** hay **tên kiểu**?
- Nếu là biểu thức đối tượng, nó được đánh giá **bao nhiêu lần** và **lúc nào**?
- Nó có thể trả `null` hoặc gây side effect không?
- Có yêu cầu giữ **cùng receiver** hay phải tìm receiver **mới khi gọi**?
- Tạo callback và gọi callback có diễn ra trên các luồng khác nhau không?
- Đối tượng được giữ có mutable state, vòng đời hoặc tài nguyên cần đóng không?
- Chữ ký SAM có đúng với kiểu tham số/kiểu trả về và method reference được chọn không?
- Test đã bao phủ **receiver null lúc tạo**, **receiver null lúc gọi**, **receiver bị thay thế**, **state bị thay đổi**, và **callback gọi nhiều lần** chưa?

## 17. Ghi nhớ

- Với `objectExpression::instanceMethod`, Java **đánh giá receiver expression ngay khi tạo method reference**, ném `NullPointerException` ngay nếu kết quả null, và giữ receiver thu được.
- Với `() -> objectExpression.instanceMethod()`, phần thân chỉ đánh giá biểu thức receiver khi callback chạy; nếu tham chiếu biến local, biến đó phải effectively final.
- Với `TypeName::instanceMethod`, receiver đến từ **đối số thứ nhất khi gọi SAM**; null ở đối số này gây lỗi lúc gọi, không phải lúc tạo.
- Bound reference **không gọi phương thức đích ngay** và **không chụp sẵn kết quả**. Nó cố định object reference; phương thức vẫn có thể đọc trạng thái mutable của object ở từng lần chạy.
- Static reference và constructor reference không có receiver instance để kiểm tra lúc tạo theo cách của bound instance reference.
- Thiết kế callback đúng cần quyết định rõ **thời điểm chọn receiver, chính sách null, side effect, vòng đời và đồng bộ hóa**. Đây là kiến thức tiếp tục quan trọng trong Java hiện đại.
