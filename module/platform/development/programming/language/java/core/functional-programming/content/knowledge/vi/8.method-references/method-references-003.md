# Tham chiếu phương thức trên đối tượng đã có trong Java

## 1. Khi nào dùng `existingObject::instanceMethod`?

Trong Java, **method reference** (tham chiếu phương thức) cho phép đưa một phương thức phù hợp vào vị trí cần **functional interface**, thay cho một lambda chỉ gọi phương thức đó. Trường hợp bài học này là **tham chiếu phương thức instance trên đối tượng đã có** (*bound instance method reference*):

~~~java
existingObject::instanceMethod
~~~

**`existingObject` là biểu thức tạo ra hoặc trỏ tới receiver** — đối tượng sẽ nhận lời gọi. Khi tạo method reference, Java đánh giá biểu thức receiver và **gắn receiver đó** với tham chiếu. Khi functional interface được gọi sau này, Java gọi phương thức trên receiver đã gắn, truyền vào những tham số mà SAM cung cấp.

Ví dụ, nếu đã có một `Printer printer`:

~~~java
Consumer<String> output = printer::print;
~~~

thì ý tưởng tương đương với:

~~~java
Consumer<String> output = text -> printer.print(text);
~~~

Hai đoạn này chỉ minh họa trong ngữ cảnh đã định nghĩa `Printer.print(String)` và import `java.util.function.Consumer`. Với biến local `printer` final/effectively final, cách viết lambda thường có cùng hành vi khi được gọi. Tuy nhiên, hai dạng **không tương đương trong mọi tình huống**, đặc biệt khi receiver là biểu thức có tác động phụ hoặc có thể trả `null`; chúng ta sẽ kiểm tra cụ thể ở phần sau.

Lợi ích chính là dùng cách viết ngắn, rõ nơi nhận lời gọi:

- `System.out::println` — gửi mỗi giá trị vào đối tượng `PrintStream` hiện có.
- `formatter::format` — dùng một formatter đã được cấu hình.
- `cache::get` — lấy giá trị từ một cache instance khi chữ ký khớp.
- `listener::onEvent` — dùng một object cụ thể làm callback.

Method reference **không gọi phương thức ngay lúc khai báo**. Nó chỉ tạo hành vi có thể gọi về sau. Riêng **biểu thức xác định receiver** được đánh giá khi tạo method reference, không đợi đến lần gọi callback.

## 2. Functional interface quyết định chữ ký lời gọi

Method reference cần một **target type** là functional interface; trình biên dịch dùng phương thức trừu tượng chức năng (*single abstract method*, SAM) để xác định tham số và kiểu trả về mong đợi.

| Target type | SAM | Ví dụ bound reference | Điều kiện |
| --- | --- | --- | --- |
| `Runnable` | `void run()` | `service::refresh` | `refresh()` gọi không cần tham số |
| `Supplier<String>` | `String get()` | `service::status` | `status()` trả String tương thích |
| `Consumer<String>` | `void accept(String)` | `printer::print` | Receiver có phương thức `print(String)` phù hợp |
| `Function<String,Integer>` | `Integer apply(String)` | `parser::parse` | `parse(String)` trả int/Integer phù hợp |
| `Predicate<Order>` | `boolean test(Order)` | `policy::allows` | `allows(Order)` trả boolean/Boolean phù hợp |
| `BiFunction<A,B,R>` | `R apply(A,B)` | `service::combine` | `combine(A,B)` trả R tương thích |

Các tên `service`, `printer`, `parser`, `policy`, `Order`, `A`, `B`, `R` ở bảng là **minh họa chữ ký**, không phải các biến/lớp đã khai báo để biên dịch.

Đối tượng receiver **không chiếm một tham số** trong SAM của dạng bound reference: nó đã được gắn sẵn. Ví dụ, `printer::print` với `print(String)` tương ứng `Consumer<String>`: callback chỉ cần truyền `String`.

Nếu một phương thức trả giá trị nhưng SAM trả `void`, Java có thể bỏ giá trị trả về khi method reference thích hợp với hợp đồng của SAM. Dù vậy, nên chọn target type thể hiện đúng mục tiêu: `Consumer` cho hành động, `Function` cho phép biến đổi có kết quả, `Supplier` cho việc cung cấp giá trị.

**Không viết `var callback = printer::print;`** khi không có target type bổ sung: method reference không phải biểu thức có kiểu độc lập mà `var` có thể suy luận từ đó. Hãy khai báo `Consumer<String>` hoặc truyền trực tiếp vào một phương thức nhận functional interface có kiểu xác định.

## 3. Ví dụ Java 17 hoàn chỉnh: gắn một formatter đã cấu hình

Giả sử một lớp formatter có cấu hình riêng: tiền tố trước tên sản phẩm và ngưỡng giá được xem là cao. Ta muốn truyền đúng **cùng một instance** vào pipeline xử lý dữ liệu.

Tạo tệp **BoundReferenceBasics.java**:

~~~java
import java.util.List;
import java.util.function.Function;
import java.util.function.Predicate;

record Product(String name, int price) {}

final class ProductFormatter {
    private final String prefix;
    private final int expensiveFrom;

    ProductFormatter(String prefix, int expensiveFrom) {
        this.prefix = prefix;
        this.expensiveFrom = expensiveFrom;
    }

    String format(Product product) {
        return prefix + product.name() + " (" + product.price() + ")";
    }

    boolean isExpensive(Product product) {
        return product.price() >= expensiveFrom;
    }
}

public class BoundReferenceBasics {
    public static void main(String[] args) {
        ProductFormatter formatter =
                new ProductFormatter("Sản phẩm: ", 100);

        Function<Product, String> describe = formatter::format;
        Predicate<Product> expensive = formatter::isExpensive;

        List<Product> products = List.of(
                new Product("Bút", 25),
                new Product("Sách", 120),
                new Product("Balo", 180)
        );

        List<String> result = products.stream()
                .filter(expensive)
                .map(describe)
                .toList();

        result.forEach(System.out::println);
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 BoundReferenceBasics.java
java BoundReferenceBasics
~~~

Stdout:

~~~text
Sản phẩm: Sách (120)
Sản phẩm: Balo (180)
~~~

**Giải thích theo luồng dữ liệu:**

1. `formatter` là **một đối tượng đã có**, giữ `prefix="Sản phẩm: "` và `expensiveFrom=100`.
2. `formatter::format` tạo hành vi có dạng `Product → String`, được gán cho `Function<Product,String>`.
3. `formatter::isExpensive` tạo hành vi `Product → boolean`, được gán cho `Predicate<Product>`.
4. `filter(expensive)` loại sản phẩm có giá 25; `map(describe)` tạo chuỗi từ hai sản phẩm còn lại.
5. `System.out::println` là method reference gắn với đối tượng `PrintStream` đang được lấy từ `System.out` khi tạo biểu thức. Trong lời gọi `forEach`, nó là callback `Consumer<String>` phù hợp.

**Tại sao chọn bound method reference?** Quy tắc định dạng và ngưỡng giá đã được đóng gói trong instance `formatter`. Các bước Stream không phải biết cách định dạng hay đọc ngưỡng; chúng chỉ gọi những hành vi mà object cung cấp. Khi đổi cấu hình, ta tạo hoặc truyền formatter khác thay vì nhân bản lambda trong nhiều nơi.

Bài này đang minh họa cách biểu diễn callback, không khuyến nghị dùng giá `int` cho mọi hệ thống thanh toán thực tế. Hệ thống tiền tệ cần định nghĩa đơn vị, giới hạn số và quy tắc làm tròn thích hợp.

## 4. Phân biệt bound, unbound và static method reference

Java có nhiều hình thức tham chiếu phương thức; cần phân biệt **ai là receiver** và **SAM cung cấp những tham số nào**.

| Dạng | Ví dụ | Receiver khi callback chạy |
| --- | --- | --- |
| `expression::instanceMethod` | `text::toUpperCase` | Đối tượng `text` đã được gắn từ trước |
| `TypeName::instanceMethod` | `String::toUpperCase` | Đối tượng String lấy từ tham số đầu của SAM |
| `TypeName::staticMethod` | `Integer::parseInt` | Không có instance receiver |
| `TypeName::new` | `StringBuilder::new` | Tạo đối tượng mới qua constructor |

Với `String`, ba ví dụ sau thể hiện các chữ ký khác nhau:

~~~java
String source = "java";

Supplier<String> bound = source::toUpperCase;
Function<String, String> unbound = String::toUpperCase;
Function<String, Integer> staticMethod = Integer::parseInt;
~~~

Đây là **đoạn minh họa** cần import `Supplier`, `Function`. Chạy:

~~~text
bound.get()               → "JAVA"
unbound.apply("hello")    → "HELLO"
staticMethod.apply("42")  → 42
~~~

- `bound.get()` không nhận tham số vì đã có receiver `source`.
- `unbound.apply("hello")` dùng **"hello"** làm receiver lúc được gọi. Không có String cụ thể nào được cố định khi viết `String::toUpperCase`.
- `Integer::parseInt` là tham chiếu tới phương thức **static** của `Integer`, nên đầu vào là tham số nghiệp vụ `String`, không phải receiver.

Một đối chiếu rất trực quan:

~~~java
String prefix = "ID-";
UnaryOperator<String> withBoundPrefix = prefix::concat;
BiFunction<String, String, String> withUnboundPrefix = String::concat;
~~~

Hai dòng trên cần import `UnaryOperator` và `BiFunction`.

- `withBoundPrefix.apply("7")` trả **"ID-7"**; receiver `prefix` đã gắn.
- `withUnboundPrefix.apply("ID-", "7")` cũng trả **"ID-7"**, nhưng receiver là **tham số đầu tiên** của BiFunction.

**Lưu ý:** Một biểu thức `TypeName::method` có thể tham chiếu một static method hoặc unbound instance method tùy kiểu phương thức và overload tương thích target type. Vì vậy, đừng phân loại chỉ dựa trên chữ viết `TypeName::...`; hãy xét định nghĩa phương thức và SAM.

## 5. Thời điểm gắn receiver: biểu thức trước dấu :: được đánh giá một lần

Đây là khác biệt quan trọng giữa method reference trên **biểu thức receiver** và một lambda gọi lại biểu thức receiver.

Xét:

~~~java
Runnable bound = factory.create()::run;
Runnable lambda = () -> factory.create().run();
~~~

Đây là **đoạn minh họa**, giả định `factory.create()` tạo một object có `run()`.

- Với `factory.create()::run`, Java gọi **factory.create() ngay khi đánh giá method reference** và gắn đối tượng được trả về. Khi chạy `bound.run()` nhiều lần, callback vẫn dùng đối tượng này.
- Với `() -> factory.create().run()`, Java gọi **factory.create() mỗi lần callback chạy**; có thể tạo nhiều đối tượng khác nhau.

Tạo tệp **ReceiverEvaluationDemo.java** để quan sát hành vi:

~~~java
public class ReceiverEvaluationDemo {
    static int creations = 0;

    static class Task {
        private final int id;
        private int invocations;

        Task(int id) {
            this.id = id;
        }

        void execute() {
            invocations++;
            System.out.println("task " + id + " call " + invocations);
        }
    }

    static Task createTask() {
        creations++;
        System.out.println("create " + creations);
        return new Task(creations);
    }

    public static void main(String[] args) {
        Runnable bound = createTask()::execute;
        Runnable lambda = () -> createTask().execute();

        System.out.println("run bound:");
        bound.run();
        bound.run();

        System.out.println("run lambda:");
        lambda.run();
        lambda.run();
    }
}
~~~

Chạy:

~~~bash
javac ReceiverEvaluationDemo.java
java ReceiverEvaluationDemo
~~~

Stdout:

~~~text
create 1
run bound:
task 1 call 1
task 1 call 2
run lambda:
create 2
task 2 call 1
create 3
task 3 call 1
~~~

**Diễn giải chính xác:**

- `createTask()::execute` làm `createTask()` chạy **ngay lúc gán** cho `bound`, in `create 1`. Chưa có lời gọi nào đến `Task.execute()` ở thời điểm đó.
- Hai lần `bound.run()` cùng dùng Task có id 1 nên bộ đếm tăng từ 1 đến 2.
- `lambda` chỉ lưu hành vi gọi `createTask()` về sau. Mỗi lần `lambda.run()` lại tạo Task mới có id 2 rồi id 3, mỗi Task chỉ thực thi một lần.

Đây là lý do không thể kết luận mọi `obj::method` đều tương đương hoàn toàn với `() -> obj.method()`: **nơi và thời điểm đánh giá receiver** là một phần của ngữ nghĩa, nhất là khi expression có side effect.

### 5.1. Nếu receiver là biến local đã có

Với:

~~~java
Task task = createTask();
Runnable a = task::execute;
Runnable b = () -> task.execute();
~~~

Đây là đoạn minh họa trong ngữ cảnh lớp có `Task` và `createTask()`. Khi `task` là local **final hoặc effectively final**, cả hai callback sẽ gọi lên cùng object `task`; sự khác biệt về thời điểm đánh giá **biểu thức phức tạp** thường không còn đáng kể. Tuy nhiên, bound reference vẫn có quy tắc đánh giá receiver tại lúc tạo; đồng thời, lambda còn tuân thủ quy tắc capture local variable.

Với một trường mutable `this.currentTask` thì khác: `this.currentTask::execute` gắn receiver được lấy **một lần**, còn `() -> this.currentTask.execute()` đọc lại trường khi callback chạy. Nếu trường đổi sang đối tượng khác sau lúc tạo, hai callback có thể dùng những object khác nhau.

## 6. Receiver null: lỗi xảy ra ngay khi tạo bound method reference

Một lỗi dễ bất ngờ là dùng bound method reference trên receiver null.

~~~java
Printer printer = null;
Consumer<String> action = printer::print;
~~~

Đây là **đoạn cố ý gây lỗi khi chạy**, giả định `Printer` có `print(String)` và đã import Consumer. Việc đánh giá `printer::print` ném **NullPointerException ngay khi tạo reference**, trước khi `action.accept(...)` có cơ hội chạy.

Với lambda:

~~~java
Printer printer = null;
Consumer<String> action = text -> printer.print(text);
~~~

Với local `printer` effectively final, việc **tạo lambda** có thể thành công; lỗi **NullPointerException** xảy ra khi `action.accept(text)` thực sự cố gọi phương thức trên null. Khác biệt là **thời điểm phát sinh lỗi**.

Trong API thật, nếu receiver bắt buộc tồn tại, nên kiểm tra rõ ràng ở ranh giới tạo callback:

~~~java
Objects.requireNonNull(printer, "printer");
Consumer<String> action = printer::print;
~~~

Đây là đoạn minh họa cần import `java.util.Objects` và Consumer. Kiểm tra tường minh giúp thông điệp thể hiện điều kiện đầu vào, nhưng không có nghĩa method reference tự xử lý null.

**Đừng nhầm receiver null với tham số null.** Bound receiver có thể hoàn toàn hợp lệ, nhưng `action.accept(null)` vẫn có thể gây lỗi ở **phương thức được gọi** tùy hợp đồng của `print`, `format` hoặc `parse`.

## 7. Receiver được gắn cố định, trạng thái bên trong object thì không nhất thiết cố định

Method reference giữ đối tượng receiver; nó **không chụp ảnh (snapshot)** tất cả trường của object tại thời điểm tạo. Nếu trường được thay đổi, phương thức được gọi sau đó có thể nhìn thấy trạng thái mới.

Tạo tệp **BoundStateDemo.java**:

~~~java
import java.util.function.Function;

final class MutablePrefixer {
    private String prefix;

    MutablePrefixer(String prefix) {
        this.prefix = prefix;
    }

    void setPrefix(String prefix) {
        this.prefix = prefix;
    }

    String addPrefix(String value) {
        return prefix + value;
    }
}

public class BoundStateDemo {
    public static void main(String[] args) {
        MutablePrefixer prefixer = new MutablePrefixer("old-");
        Function<String, String> add = prefixer::addPrefix;

        System.out.println(add.apply("x"));

        prefixer.setPrefix("new-");
        System.out.println(add.apply("x"));

        MutablePrefixer replacement = new MutablePrefixer("other-");
        Function<String, String> other = replacement::addPrefix;
        System.out.println(other.apply("x"));
        System.out.println(add.apply("y"));
    }
}
~~~

Chạy:

~~~bash
javac BoundStateDemo.java
java BoundStateDemo
~~~

Stdout:

~~~text
old-x
new-x
other-x
new-y
~~~

Điều rút ra:

- `add` luôn gắn với **cùng instance `prefixer`**.
- Thay đổi `prefixer.prefix` ảnh hưởng kết quả ở lần gọi sau, vì `addPrefix` đọc trạng thái hiện thời của instance.
- Tạo `replacement` không làm receiver của `add` đổi theo. `other` là callback mới gắn với một object khác.
- “Receiver được gắn cố định” **không đồng nghĩa kết quả luôn cố định** hay hàm thuần.

Khi muốn callback trả cùng kết quả bất kể cấu hình bị thay đổi, có thể dùng object bất biến hoặc chụp giá trị cấu hình cần thiết rồi tạo lambda dựa trên giá trị đó. Hãy xác định chính sách **live state** hay **snapshot state** theo nghiệp vụ.

## 8. Bound reference vẫn dùng virtual dispatch khi cần

Khi receiver có kiểu lớp cha nhưng instance thực tế là lớp con override phương thức, bound method reference đến **instance method** thực thi theo quy tắc dispatch Java thông thường.

Tạo tệp **BoundDispatchDemo.java**:

~~~java
import java.util.function.Supplier;

class BaseService {
    String name() {
        return "base";
    }
}

class ChildService extends BaseService {
    @Override
    String name() {
        return "child";
    }
}

public class BoundDispatchDemo {
    public static void main(String[] args) {
        BaseService service = new ChildService();

        Supplier<String> reference = service::name;
        Supplier<String> lambda = () -> service.name();

        System.out.println(reference.get());
        System.out.println(lambda.get());
    }
}
~~~

Chạy:

~~~bash
javac BoundDispatchDemo.java
java BoundDispatchDemo
~~~

Stdout:

~~~text
child
child
~~~

**Vì sao?** `service` là biến có kiểu tĩnh `BaseService`, còn object thực tế là `ChildService`. `name()` là instance method bị override, nên Java chọn implementation của `ChildService`.

Không nhầm với `super::name` bên trong một lớp con: cú pháp `super::...` có ngữ nghĩa riêng để chọn implementation lớp cha từ ngữ cảnh kế thừa hợp lệ. Chủ đề của bài này là **receiver object đã có**, nên `service::name` sử dụng dispatch instance thông thường.

**Lưu ý overloaded methods:** Nếu receiver có nhiều phương thức cùng tên (ví dụ `print(String)`, `print(int)`), Java dùng target type của functional interface để chọn overload phù hợp. Không thể nhìn `printer::print` mà biết chính xác overload nào khi chưa biết kiểu đích.

## 9. Overload và suy luận kiểu: target type quyết định phương thức

Một object có thể cung cấp nhiều overload:

~~~java
class Converter {
    String convert(String input) {
        return "str:" + input;
    }

    String convert(int input) {
        return "int:" + input;
    }
}
~~~

Đây là **đoạn định nghĩa lớp minh họa**. Có thể viết:

~~~java
Converter converter = new Converter();

Function<String, String> stringRule = converter::convert;
IntFunction<String> numberRule = converter::convert;
~~~

Đoạn trên cần import `java.util.function.Function` và `java.util.function.IntFunction`. Với `stringRule.apply("a")` trả **"str:a"**, còn `numberRule.apply(3)` trả **"int:3"**.

Khi Java không thể phân giải một overload duy nhất theo ngữ cảnh, sẽ có lỗi biên dịch về tham chiếu mơ hồ. Cách xử lý là làm rõ target type hoặc viết lambda chỉ định kiểu tham số khi cần.

Ví dụ:

~~~java
Function<String, String> selected =
        (String input) -> converter.convert(input);
~~~

Nếu phương thức nhận callback bị overload bằng hai functional interface có chữ ký tương tự, method reference/lambda có thể không đủ thông tin để chọn overload ở lời gọi bên ngoài. Có thể gán trước vào biến đúng kiểu hoặc dùng cast có chủ đích, nhưng tránh ép kiểu khi API có thể được thiết kế tên phương thức rõ hơn.

**Generic method references:** Các phương thức generic trên receiver vẫn có thể tham chiếu khi kiểu đối số và kết quả tương thích SAM. Java thực hiện suy luận kiểu theo target type; không phải mọi trường hợp đều tự suy luận được, đặc biệt khi overload và generic ràng buộc chồng chéo. Hãy kiểm tra lỗi cụ thể của trình biên dịch thay vì đoán.

## 10. Method reference trong Stream, callback và các API nhận hành vi

Ba tình huống thường gặp:

### 10.1. Dùng trạng thái đã cấu hình trong pipeline

~~~java
List<String> formatted = items.stream()
        .map(formatter::format)
        .toList();
~~~

Đây là **đoạn minh họa**, giả định `items` chứa đối tượng mà `formatter.format` nhận được. Hành vi có thể đã được cấu hình qua constructor hoặc dependency injection. `map` chỉ quan tâm giá trị trả về.

Nếu `formatter.format` có side effect như sửa trạng thái hoặc gọi mạng, Stream vẫn có thể thực thi nhưng dễ trở nên khó suy luận, khó song song hóa hoặc có hiệu năng không ổn định. Không nên cho rằng syntax method reference làm hành vi tự động thuần túy.

### 10.2. Đăng ký listener cho một object cụ thể

~~~java
Consumer<Event> handler = listener::onEvent;
eventBus.register(handler);
~~~

Đây là **đoạn minh họa**: các kiểu `Event`, `eventBus`, `listener`, phương thức `register` cần được định nghĩa phù hợp. Ứng dụng có thể đăng ký callback để chạy khi có sự kiện tương lai; reference gắn receiver `listener` ở thời điểm tạo.

Nếu listener cần được hủy đăng ký, nên **giữ cùng đối tượng callback** `handler` và dùng lại nó khi gọi `unregister(handler)`, theo hợp đồng của event bus. Tạo một method reference mới rồi giả định nó có object identity bằng reference cũ là không an toàn: Java không cam kết danh tính đối tượng lambda/method reference ổn định như vậy.

### 10.3. Tương tác với API chuẩn

~~~java
StringBuilder builder = new StringBuilder();
Consumer<String> append = builder::append;

append.accept("A");
append.accept("B");
System.out.println(builder); // AB
~~~

Đây là **đoạn minh họa**, cần import `Consumer`. `StringBuilder.append(String)` trả về chính `StringBuilder`, nhưng `Consumer.accept` trả `void`, nên kết quả trả về của lời gọi được bỏ qua. Hai lần callback thay đổi trạng thái của receiver và in **AB**.

Điều này hữu ích khi cần hành động có side effect có chủ đích, nhưng hãy biết rõ kiểu trả về bị bỏ và object mutable đang bị cập nhật. `StringBuilder` không an toàn khi nhiều thread ghi đồng thời vào cùng instance mà không phối hợp.

## 11. Capture, vòng đời đối tượng và an toàn luồng

Method reference gắn receiver có thể giữ **tham chiếu mạnh** đến object đó trong suốt thời gian callback còn được giữ. Nếu callback được lưu trong scheduler, event bus hoặc registry sống lâu, receiver cũng có thể tiếp tục được tham chiếu và chưa thể được thu gom rác theo dự kiến.

Một số nguyên tắc:

1. **Quản lý vòng đời đăng ký:** lưu callback được tạo, hủy đăng ký đúng lúc và kiểm tra hợp đồng của cơ chế listener.
2. **Không tạo callback chỉ để so sánh bằng `==`:** identity của các method reference không được bảo đảm bằng nhau kể cả khi cùng viết `obj::method`.
3. **Phân biệt receiver với trạng thái:** bound reference gắn object, nhưng trạng thái trường của object vẫn có thể thay đổi, như ví dụ `MutablePrefixer`.
4. **Đồng bộ truy cập mutable state:** khi nhiều thread gọi cùng callback lên một object mutable, cần bảo vệ trạng thái bằng synchronization, atomic classes, thiết kế immutable hoặc cơ chế phù hợp.
5. **Xem xét thời điểm tạo:** reference trên biểu thức receiver có side effect thực hiện biểu thức lúc tạo; điều này ảnh hưởng log, exception, mở tài nguyên và tính toán tốn kém.
6. **Đừng dùng bound reference để che dependency phức tạp:** nếu API cần retry, transaction hoặc kiểm soát lỗi, hợp đồng callback phải thể hiện điều đó.

Một callback `counter::increment` không an toàn hơn `() -> counter.increment()` nếu `increment` cập nhật dữ liệu chung không có đồng bộ. Độ ngắn của method reference chỉ liên quan cú pháp; các điều kiện về side effect, thread safety và khả năng quan sát lỗi vẫn do phương thức được gọi quyết định.

### 11.1. Receiver static field thay đổi thì sao?

Giả sử `Manager.current` là trường static trỏ tới một instance. Hai cách sau có thể khác:

~~~java
Runnable fixed = Manager.current::refresh;
Runnable dynamic = () -> Manager.current.refresh();
~~~

Đây là **đoạn minh họa**; các tên cần được khai báo phù hợp. `fixed` gắn receiver đọc từ `Manager.current` **khi tạo**. `dynamic` đọc lại `Manager.current` **mỗi lần được gọi**. Nếu `current` thay đổi, hai callback có thể gọi lên hai instance khác nhau. Nếu `current` là null tại lúc tạo `fixed`, việc tạo bound reference sẽ ném NullPointerException.

## 12. Các lỗi phổ biến

| Lỗi/ngộ nhận | Hệ quả | Cách hiểu đúng |
| --- | --- | --- |
| “`object::method` gọi method ngay” | Dự đoán sai side effect | Chỉ đánh giá receiver khi tạo; method chạy khi gọi SAM |
| “Receiver là tham số đầu của SAM” | Gán sai target type | Với bound reference, receiver đã gắn; tham số SAM là tham số của method |
| Nhầm `obj::instanceMethod` với `Type::instanceMethod` | Lẫn bound và unbound, sai số tham số | Type::instanceMethod dùng tham số SAM đầu làm receiver |
| Nhầm `Type::staticMethod` với unbound instance reference | Phân tích sai receiver | Static method không cần receiver |
| Nghĩ `factory.create()::run` và `() -> factory.create().run()` luôn như nhau | Thời điểm tạo object và số lần gọi factory khác nhau | Bound đánh giá receiver một lần; lambda đánh giá ở mỗi lần chạy |
| Tạo bound reference trên receiver null | NullPointerException lúc tạo reference | Kiểm tra receiver trước; phân biệt thời điểm lỗi của lambda |
| Nghĩ receiver bị “đóng băng” toàn bộ trạng thái | Kết quả callback thay đổi ngoài dự kiến | Object được gắn, trường mutable có thể đổi |
| Không khai báo target type | `var f = obj::method` không đủ kiểu đích | Gán cho một functional interface cụ thể |
| Quên overload | Method reference mơ hồ hoặc chọn chữ ký khác dự đoán | Kiểm tra target SAM và các overload |
| So sánh hai reference mới bằng identity | Không tìm được listener đã đăng ký | Lưu và dùng lại một biến callback |
| Dùng method reference rồi giả định thread-safe | Race condition, lost update | Đánh giá trạng thái và đồng bộ của receiver |
| Giữ callback trong registry quá lâu | Receiver có thể bị giữ sống lâu hơn mong đợi | Gắn vòng đời đăng ký và hủy đăng ký hợp lý |

## 13. Cách chọn giữa method reference và lambda

Dùng **`object::method`** khi:

- Đã có instance đúng để xử lý và muốn truyền chính method của nó;
- Target functional interface và method có chữ ký tương thích;
- Việc **gắn receiver ngay lúc tạo callback** đúng với ý định;
- Tên method thể hiện rõ hành động, code ngắn và dễ đọc.

Dùng **lambda** khi:

- Cần thêm kiểm tra, chuyển đổi, xử lý lỗi hoặc nhiều lệnh trước/sau lời gọi;
- Muốn **đọc lại receiver động** tại mỗi lần thực thi;
- Cần điều chỉnh đối số hoặc kết hợp kết quả từ nhiều phương thức;
- Viết method reference khiến người đọc khó nhận ra phương thức/receiver nào được chọn do overload.

Đừng thay lambda bằng method reference theo quy tắc máy móc. Hãy kiểm tra tính tương đương của **thời điểm đánh giá receiver**, **null**, **overload**, **side effect**, **dispatch** và **vòng đời callback**.

## 14. Bài tập và câu hỏi tự kiểm tra

1. Với `String name = "Java"; Supplier<String> f = name::toLowerCase;`, receiver là gì, và `f.get()` trả gì? Đổi sang `String::toLowerCase` thì target type nào hợp lý?
2. Cho `String prefix = "ID-";`, phân biệt `prefix::concat` và `String::concat`: số tham số của functional interface ở từng trường hợp là bao nhiêu?
3. Tại sao `factory.create()::execute` khác `() -> factory.create().execute()` nếu factory tạo instance mới mỗi lần?
4. Khi `printer == null`, lỗi của `printer::print` xảy ra vào lúc nào? Việc chuyển sang `text -> printer.print(text)` có thể thay đổi thời điểm lỗi ra sao?
5. Một `formatter::format` đã được gắn trước, sau đó `formatter` thay đổi trường `prefix`. Method reference có dùng giá trị mới không? Giải thích sự khác nhau giữa gắn receiver và snapshot trạng thái.
6. Vì sao `BaseService service = new ChildService(); Supplier<String> f = service::name;` chọn implementation của `ChildService` nếu method được override?
7. Một event bus dùng `unregister(callback)`. Vì sao cần lưu lại biến callback đã đăng ký thay vì tạo lại cùng biểu thức `listener::onEvent`?
8. Với object có hai overload `convert(String)` và `convert(int)`, hãy gán `converter::convert` vào `Function<String,String>` và `IntFunction<String>`, rồi dự đoán kết quả khi gọi.

## 15. Ghi nhớ

**`existingObject::instanceMethod` là một bound instance method reference**: biểu thức bên trái dấu `::` được đánh giá tại thời điểm tạo reference, receiver được gắn, còn lời gọi phương thức diễn ra khi SAM được thực thi.

Hãy phân biệt nó với `TypeName::instanceMethod` (unbound, receiver đến từ tham số đầu), `TypeName::staticMethod` (không cần receiver) và lambda gọi biểu thức receiver động. Chú ý **receiver null gây lỗi lúc tạo**, **trạng thái mutable của receiver vẫn có thể đổi**, và **target functional interface quyết định overload/chữ ký**.

Method reference là công cụ thể hiện rõ hành vi trên đối tượng đã có; quyết định dùng nó phải dựa trên tính đúng đắn của receiver, hợp đồng API, vòng đời và tác động phụ, không chỉ vì giảm số ký tự Java.