# Capture, cấp phát và giới hạn phụ thuộc implementation trong Java

> **Module:** Java 8 — **JVM và công cụ**. Bài tập trung vào việc lambda expression và method reference **capture** dữ liệu từ phạm vi bên ngoài, cách JVM/runtime có thể tạo hoặc tái sử dụng function object, những tối ưu cấp phát của JIT, và các giới hạn đến từ class-file/JVM/runtime. Cần phân biệt rõ **điều Java Language Specification bảo đảm** với **chi tiết của javac, HotSpot hoặc một JVM cụ thể**. Các quy tắc được trình bày vẫn áp dụng trên Java hiện hành.

## 1. Capture là gì?

Một lambda có thể sử dụng dữ liệu được khai báo bên ngoài thân lambda. Việc lấy dữ liệu từ phạm vi bao quanh đó được gọi là **capture**.

~~~java
int minimum = 10;

IntPredicate accepted = value -> value >= minimum;
~~~

Lambda có một tham số riêng là `value`, nhưng nó còn sử dụng `minimum` từ method bao quanh. Vì thế `minimum` là biến được capture.

Trong một ứng dụng, capture thường xuất hiện khi:

- Truyền điều kiện lọc vào `Stream.filter`.
- Tạo callback cho GUI, event handler hoặc listener.
- Gửi tác vụ sang executor.
- Tạo comparator dựa trên một cấu hình bên ngoài.
- Tạo predicate/mapper có tham số cấu hình.
- Dùng method reference có receiver đã xác định, ví dụ `service::handle`.

Capture có thể giúp code ngắn gọn và biểu đạt ý định tốt. Nhưng để hiểu đúng hành vi, cần tách ba thời điểm:

1. **Evaluation:** biểu thức lambda/method reference được đánh giá và tạo ra một function object reference.
2. **Capture:** các giá trị cần thiết từ ngữ cảnh bên ngoài được gắn với function object theo semantics của ngôn ngữ.
3. **Invocation:** method của functional interface được gọi và thân lambda/method được thực thi.

Việc đánh giá lambda không đồng nghĩa thân lambda chạy ngay.

~~~java
int minimum = 10;
IntPredicate accepted = value -> value >= minimum;

// Chỉ khi gọi test thì thân lambda mới chạy.
boolean result = accepted.test(12);
~~~

Đây là ví dụ Java 8 hợp lệ. Việc tạo `accepted` và việc gọi `accepted.test(12)` là hai thao tác khác nhau.

## 2. Quy tắc effectively final khi capture local variable

Java cho phép lambda sử dụng local variable, method parameter và exception parameter từ phạm vi bên ngoài khi biến đó là:

- `final`; hoặc
- **effectively final**: không khai báo `final` nhưng sau khi được gán giá trị, không bị gán lại hoặc tăng/giảm theo cách làm thay đổi binding.

### 2.1. Biến final

~~~java
final int minimum = 10;

IntPredicate accepted = value -> value >= minimum;
~~~

Biến `minimum` không thể bị gán lại sau khi khởi tạo, nên có thể được capture.

### 2.2. Biến effectively final

~~~java
int minimum = 10;

IntPredicate accepted = value -> value >= minimum;

// Hợp lệ: minimum chưa từng bị gán lại.
boolean result = accepted.test(12);
~~~

Không cần thêm từ khóa `final`. Compiler kiểm tra điều kiện effectively final tại thời điểm biên dịch.

### 2.3. Gán lại sau khi capture là lỗi biên dịch

~~~java
int minimum = 10;
IntPredicate accepted = value -> value >= minimum;

// LỖI BIÊN DỊCH:
// minimum = 20;
~~~

Nếu bỏ comment và gán lại `minimum`, chương trình không còn hợp lệ vì biến được capture không effectively final.

### 2.4. Tăng hoặc giảm cũng làm mất effectively final

~~~java
int count = 0;
Runnable task = () -> System.out.println(count);

// LỖI BIÊN DỊCH:
// count++;
~~~

`count++` là phép thay đổi giá trị biến, nên biến không còn effectively final. Quy tắc này áp dụng cả với `++count`, `--count` và các phép gán khác.

### 2.5. Method parameters cũng chịu quy tắc này

~~~java
static Runnable createTask(int retries) {
    return () -> System.out.println(retries);
}
~~~

`retries` là parameter của method. Nó có thể được capture vì không bị gán lại trong method.

### 2.6. Vì sao Java đặt ra quy tắc này?

Một local variable thông thường có vòng đời gắn với lần gọi method. Nhưng lambda có thể được trả ra ngoài, lưu lại hoặc chạy sau khi method đã kết thúc.

Nếu lambda có thể đọc/ghi trực tiếp một local variable đang thay đổi tùy ý, semantics và đồng bộ hóa giữa các lần gọi sẽ phức tạp. Quy tắc effectively final giúp xác định rõ giá trị binding được sử dụng khi tạo lambda.

**Điều quan trọng:** effectively final giới hạn việc thay đổi **biến/reference**, không làm object được tham chiếu trở thành immutable hoặc thread-safe. Phần tiếp theo phân biệt hai việc này.

## 3. Capture giá trị primitive và capture reference

### 3.1. Primitive: capture giá trị

~~~java
int limit = 5;
IntPredicate aboveLimit = number -> number > limit;
~~~

Lambda sử dụng giá trị của `limit` tại thời điểm capture theo semantics Java. Vì `limit` effectively final, code bên ngoài không thể gán lại biến này sau đó.

Không nên mô tả đây là một cam kết về bố trí vật lý trong heap hoặc một field cụ thể của class sinh ra. JLS quy định **hành vi quan sát được**, còn cách lưu trữ bên trong là việc của implementation.

### 3.2. Reference: capture giá trị của reference

~~~java
StringBuilder text = new StringBuilder("Java");

Supplier<String> read = () -> text.toString();

text.append(" 8");

System.out.println(read.get()); // Java 8
~~~

Biến `text` không bị gán sang object khác, nên effectively final. Lambda giữ quyền truy cập tới **cùng StringBuilder object**. Khi object thay đổi nội dung, lần gọi `read.get()` nhìn thấy nội dung mới.

Điều được capture là giá trị reference; không phải một bản sao sâu của toàn bộ object.

### 3.3. Reference final không làm object bất biến

~~~java
final List<String> names = new ArrayList<String>();

Runnable add = () -> names.add("Java");

// Hợp lệ: names vẫn trỏ tới cùng một List.
add.run();
~~~

`names` không thể trỏ sang một List khác, nhưng nội dung List vẫn có thể thay đổi. `final` chỉ ngăn gán lại reference.

Tương tự, `Collections.unmodifiableList` chỉ tạo view không cho sửa qua view đó; nó không tự bảo đảm object nguồn bất biến nếu một reference khác vẫn có thể sửa nguồn.

### 3.4. Không dùng mảng hoặc holder để lách quy tắc mà bỏ qua semantics

~~~java
int[] counter = {0};

Runnable task = () -> counter[0]++;

task.run();
~~~

Đoạn này biên dịch vì biến `counter` không bị gán lại. Lambda thay đổi **phần tử mảng**, không thay đổi local variable `counter`.

Đây là một cách biểu diễn mutable state, nhưng cần xem xét:

- Có cần state thay đổi hay không?
- Có nhiều thread cùng truy cập không?
- Ai chịu trách nhiệm đồng bộ hóa?
- Có cách dùng `AtomicInteger`, `LongAdder`, lock hoặc một object sở hữu state rõ ràng phù hợp hơn không?

Không dùng array holder chỉ để vượt qua compiler nếu nó làm code khó đọc hoặc tạo race condition.

### 3.5. Capture reference không phải deep copy

~~~java
List<String> original = new ArrayList<String>();
original.add("A");

Supplier<Integer> size = () -> original.size();

original.add("B");

System.out.println(size.get()); // 2
~~~

Lambda quan sát cùng List. Nếu cần snapshot tại thời điểm tạo lambda, hãy tạo snapshot rõ ràng:

~~~java
List<String> snapshot =
        Collections.unmodifiableList(new ArrayList<String>(original));

Supplier<Integer> sizeAtCreation = () -> snapshot.size();
~~~

Đây là ví dụ minh họa; snapshot là bản sao cấu trúc nông. Nếu phần tử trong List là object mutable, bản sao vẫn giữ các references tới những object đó.

## 4. Capture trong vòng lặp

### 4.1. Không capture biến điều khiển for thông thường đang thay đổi

~~~java
List<Runnable> tasks = new ArrayList<Runnable>();

for (int i = 0; i < 3; i++) {
    // LỖI BIÊN DỊCH:
    // tasks.add(() -> System.out.println(i));
}
~~~

`i++` làm thay đổi biến `i`, vì vậy `i` không effectively final.

### 4.2. Tạo biến final/effectively final cho mỗi lần lặp

~~~java
List<Runnable> tasks = new ArrayList<Runnable>();

for (int i = 0; i < 3; i++) {
    final int current = i;
    tasks.add(() -> System.out.println(current));
}
~~~

Mỗi vòng lặp tạo một biến `current` mới, gắn với giá trị của vòng lặp đó. Các lambda giữ giá trị tương ứng.

### 4.3. Enhanced for có semantics khác

~~~java
String[] labels = {"A", "B", "C"};
List<Runnable> tasks = new ArrayList<Runnable>();

for (String label : labels) {
    tasks.add(() -> System.out.println(label));
}
~~~

Enhanced-for variable được xử lý như một biến riêng cho mỗi lần lặp theo quy tắc ngôn ngữ, nên có thể capture trực tiếp nếu không bị gán lại trong thân vòng lặp.

Đừng nhầm với biến điều khiển của vòng `for (int i=...)` thông thường.

### 4.4. Chú ý khi tạo task bất đồng bộ

~~~java
for (int i = 0; i < 3; i++) {
    final int jobNumber = i;
    executor.submit(() -> process(jobNumber));
}
~~~

Đây là mẫu phù hợp: mỗi task có giá trị job number riêng. Tuy nhiên, việc capture đúng giá trị không đảm bảo thứ tự thực thi hoặc thứ tự hoàn tất của các task. Nếu thứ tự quan trọng, cần thiết kế queue/sequence hoặc chờ kết quả theo contract.

## 5. Capture this và các field của object

### 5.1. Trong lambda, this là enclosing instance

~~~java
final class Formatter {
    private final String prefix;

    Formatter(String prefix) {
        this.prefix = prefix;
    }

    Supplier<String> prefixSupplier() {
        return () -> this.prefix;
    }
}
~~~

Trong thân lambda, `this` trỏ tới instance `Formatter` bao quanh. Lambda không tạo một ngữ cảnh `this` riêng giống anonymous inner class.

### 5.2. Lambda có thể đọc field thay đổi

~~~java
final class Counter {
    private int value;

    Runnable task() {
        return () -> System.out.println(value);
    }

    void increment() {
        value++;
    }
}
~~~

Lambda đọc field `value` của cùng object. Nếu `increment()` chạy trước lần gọi Runnable, giá trị mới được đọc theo các quy tắc truy cập field thông thường.

Nếu nhiều thread đọc/ghi field, phải giải quyết visibility và atomicity như mọi code Java khác. Capture `this` không tạo memory barrier và không tự thêm `synchronized`.

### 5.3. Capture this có thể giữ cả object graph sống lâu hơn

~~~java
class Controller {
    private final LargeCache cache = new LargeCache();

    Runnable createCallback() {
        return () -> cache.refresh();
    }
}
~~~

Nếu callback được đăng ký vào một event source sống lâu, lambda có thể giữ reference tới `Controller`. Qua `this`, toàn bộ object graph reachable từ controller có thể vẫn còn reachable và không được garbage collector thu hồi.

Khi callback không còn cần thiết:

- Hủy đăng ký listener/callback.
- Xóa reference trong registry/queue khi công việc hoàn tất.
- Tránh capture toàn bộ object chỉ để dùng một giá trị nhỏ.
- Cân nhắc tách dữ liệu cần thiết thành một object nhỏ hơn.

Đây là vấn đề **lifetime và reachability**, không phải lambda tự gây memory leak. Một reference còn được giữ bởi cấu trúc sống lâu mới là nguyên nhân.

### 5.4. Static context không có this

Trong static method không tồn tại enclosing instance `this`. Lambda trong static method có thể capture local variables effectively final và gọi static members, nhưng không thể tham chiếu instance field trực tiếp nếu không có một object reference phù hợp.

## 6. Method reference cũng có thể capture

Method reference không phải lúc nào cũng là stateless. Có các dạng khác nhau:

| Cú pháp | Ý nghĩa | Có receiver được capture? |
| --- | --- | --- |
| `Type::staticMethod` | Gọi static method | Không có instance receiver |
| `object::instanceMethod` | Gọi method trên object đã chỉ định | Có, receiver đã chỉ định |
| `Type::instanceMethod` | Receiver được truyền làm tham số đầu vào | Không capture một receiver cụ thể |
| `Type::new` | Gọi constructor khi functional method chạy | Không capture object được tạo trước |
| `this::instanceMethod` | Gọi method trên enclosing object | Có, `this` |

### 6.1. Bound method reference

~~~java
StringBuilder builder = new StringBuilder("Java");
Supplier<String> text = builder::toString;

builder.append(" 8");

System.out.println(text.get()); // Java 8
~~~

`builder::toString` xác định receiver là object `builder` tại thời điểm method-reference expression được đánh giá. Khi functional method chạy, nó gọi `toString()` trên receiver đó.

### 6.2. Unbound method reference

~~~java
Function<String, String> trim = String::trim;

System.out.println(trim.apply(" Java ")); // Java
~~~

`String::trim` chưa chọn một String receiver cụ thể. Receiver được truyền vào khi gọi `apply`.

### 6.3. Bound receiver có thể giữ object sống lâu

~~~java
Runnable callback = service::refresh;
~~~

Method reference giữ receiver `service`. Nếu callback sống lâu, service và object graph của nó có thể được giữ sống theo. Cần quản lý vòng đời callback như lambda capture `this`.

### 6.4. Không nhầm method reference với lời gọi method

~~~java
service::refresh  // Tạo function object từ method reference.
service.refresh() // Gọi method ngay tại vị trí này.
~~~

Hai biểu thức có ý nghĩa khác nhau. Dòng đầu tạo một giá trị có thể truyền đi; dòng sau thực thi method.

## 7. Capture, evaluation và invocation không đồng nghĩa cấp phát một object mới

JLS quy định đánh giá lambda expression bình thường sẽ tạo ra một reference tới instance của functional interface target type. Nhưng implementation được phép:

- Cấp phát một object mới.
- Trả về một instance phù hợp đã tồn tại.
- Dùng các instance khác nhau hoặc cùng instance giữa những lần đánh giá.
- Tổ chức dữ liệu capture theo cách khác nhau tùy implementation.

Do đó, chương trình **không được dựa vào object identity của lambda**.

### 7.1. Không so sánh lambda bằng ==

~~~java
Supplier<String> first = () -> "Java";
Supplier<String> second = () -> "Java";

// Không dùng kết quả first == second để suy luận semantics.
~~~

Hai biểu thức nằm ở hai vị trí mã khác nhau. Không có cam kết portable rằng chúng cùng hoặc khác object.

Ngay cả khi cùng một biểu thức được đánh giá nhiều lần, implementation có thể tái sử dụng instance hoặc tạo instance khác.

### 7.2. Không khóa monitor trên lambda

~~~java
Runnable callback = () -> performWork();

// Không dùng callback làm lock theo identity.
synchronized (callback) {
    // Critical section.
}
~~~

Identity của lambda không được đảm bảo. Hãy dùng một lock object được khai báo và quản lý rõ ràng:

~~~java
private final Object lock = new Object();

synchronized (lock) {
    // Critical section.
}
~~~

### 7.3. Không dùng identityHashCode của lambda làm ID

`System.identityHashCode(lambda)` không phải ID nghiệp vụ hoặc định danh ổn định. Nó không đảm bảo duy nhất và không đảm bảo giữ nguyên giữa các lần tạo/serialize/deserialize.

Nếu cần định danh callback hoặc task, cấp một ID riêng theo application contract.

### 7.4. Stateless lambda không có nghĩa chắc chắn được cache

~~~java
Runnable task = () -> doWork();
~~~

Lambda này không capture local variable, nhưng không có guarantee rằng runtime luôn cache một instance duy nhất. Một implementation có thể tái sử dụng instance; implementation khác có thể cấp phát.

### 7.5. Capturing lambda không có nghĩa chắc chắn cấp phát một object mỗi lần

~~~java
int limit = 10;
IntPredicate predicate = value -> value > limit;
~~~

Runtime có thể tạo object chứa thông tin capture hoặc dùng cơ chế khác. Không viết performance model dựa trên giả định “mỗi lần đánh giá lambda = một object heap mới”.

**Quy tắc sử dụng:** viết code theo semantics của functional interface; đo allocation bằng công cụ phù hợp nếu hiệu năng là yêu cầu thực tế.

## 8. javac, invokedynamic và LambdaMetafactory

### 8.1. Đây là implementation strategy, không phải cú pháp ngôn ngữ

Với javac hiện đại và các target Java thông dụng, lambda thường được biên dịch thông qua bytecode `invokedynamic` và bootstrap linkage liên quan tới `LambdaMetafactory`.

Mô hình khái quát:

~~~text
Java source lambda
       |
       v
Compiler tạo bytecode / bootstrap metadata
       |
       v
invokedynamic call site
       |
       v
LambdaMetafactory hoặc linkage phù hợp
       |
       v
Functional-interface object
       |
       v
Gọi method của functional interface
~~~

`LambdaMetafactory` là API trong `java.lang.invoke`. Tài liệu hiện hành mô tả linkage có thể tạo class mới hoặc tái sử dụng class phù hợp; capture có thể cấp phát function object mới hoặc trả object đã tồn tại.

### 8.2. Không giả định class sinh ra có tên cố định

Tên class nội bộ, số class, cách lưu captured arguments, bootstrap method và bytecode details là implementation/compiler dependent. Chúng có thể thay đổi giữa:

- javac và compiler khác.
- Các phiên bản JDK.
- Các JVM implementations.
- Cấu hình tối ưu và class loading.

Không viết code production phụ thuộc vào tên class sinh ra như `SomeClass$$Lambda$1` hoặc truy cập private synthetic field của lambda.

### 8.3. javap hữu ích để học, không phải hợp đồng ứng dụng

Có thể quan sát bytecode:

~~~bash
javac --release 8 CaptureAllocationDemo.java
javap -c -v CaptureAllocationDemo
~~~

Khi xem output, chú ý `invokedynamic`, bootstrap methods và method implementation. Output giúp hiểu compiler/runtime đang làm gì trong một bản build cụ thể; **không** phải bằng chứng mọi compiler hoặc JVM phải dùng cùng cách.

### 8.4. Không tự tạo LambdaMetafactory cho tác vụ thông thường

`LambdaMetafactory` phục vụ linkage nâng cao, framework hoặc runtime code generation. Với ứng dụng thông thường, viết lambda/method reference trực tiếp giúp code dễ đọc và để compiler/JVM chọn strategy phù hợp.

Chỉ dùng low-level `MethodHandle`/`CallSite` khi có yêu cầu kiến trúc cụ thể và đã đo/kiểm chứng lợi ích.

## 9. JIT, escape analysis và tối ưu cấp phát

### 9.1. Source code không phản ánh trực tiếp số heap allocations cuối cùng

Một lambda có thể được tạo ở source, nhưng JIT có thể inline method, phân tích object lifetime và tối ưu allocation nếu semantics cho phép.

Điều này có nghĩa:

- Không thể đếm object allocation chỉ bằng số ký tự `->` trong source.
- Không thể kết luận lambda chậm hơn method call chỉ vì nó có cú pháp object-like.
- Không thể kết luận lambda miễn phí chỉ vì một benchmark nhỏ không thấy allocation.
- Kết quả phụ thuộc compiler, runtime, warmup, call-site profile và workload.

### 9.2. Escape analysis

Escape analysis phân tích object có thoát khỏi method hoặc thread hiện tại hay không. Trong HotSpot, thông tin này có thể hỗ trợ loại bỏ một số allocation và lock nếu object không cần tồn tại dưới dạng object riêng biệt.

### 9.3. Scalar replacement

Nếu object không escape và compiler có thể chứng minh cách sử dụng, một số object allocations có thể được loại bỏ; các field có thể được xử lý như giá trị riêng lẻ trong mã máy tối ưu.

Đây là tối ưu của JIT, **không phải cam kết rằng mọi lambda hoặc captured object đều được scalar-replace**.

### 9.4. Không gọi tối ưu hóa này là stack allocation mặc định

Tài liệu HotSpot mô tả escape analysis và scalar replacement; HotSpot không đơn giản chuyển mọi object không escape sang một object heap có địa chỉ stack. Scalar replacement có thể loại bỏ nhu cầu cấp phát object thay vì tạo một object đầy đủ trên stack.

### 9.5. Lambda escape ra ngoài method

~~~java
static Supplier<String> create() {
    String label = "Java";
    return () -> label;
}
~~~

Lambda được trả về cho caller và có thể được dùng sau khi `create()` kết thúc. Implementation phải bảo toàn semantics của capture; caller vẫn đọc được giá trị `label`.

Không được lưu một pointer trỏ tới local stack frame đã hết vòng đời. Cách runtime duy trì giá trị capture là chi tiết implementation.

### 9.6. Escape qua field hoặc collection

~~~java
static final List<Runnable> callbacks =
        new ArrayList<Runnable>();

static void register(String name) {
    callbacks.add(() -> System.out.println(name));
}
~~~

Lambda được giữ trong collection lâu hơn method `register`. Giá trị capture cần còn khả dụng khi callback chạy. Nếu collection là global/long-lived, các references được capture cũng có thể sống lâu.

### 9.7. Allocation elimination không thay đổi semantics

Compiler chỉ được tối ưu khi kết quả quan sát được vẫn đúng theo Java semantics. Không được dựa vào tối ưu hóa để bỏ side effects, bỏ exception hoặc thay đổi thứ tự thực thi mà ngôn ngữ yêu cầu.

## 10. Capture và thread safety

### 10.1. Effectively final không có nghĩa object thread-safe

~~~java
List<String> items = new ArrayList<String>();

Runnable task = () -> items.add("Java");
~~~

`items` effectively final, nhưng `ArrayList` không tự thread-safe. Nếu nhiều task cùng thêm/xóa/đọc đồng thời, cần đồng bộ hoặc chọn cấu trúc dữ liệu concurrency phù hợp.

### 10.2. Capture không tạo happens-before

Việc đưa lambda vào một biến hoặc gọi functional method không tự thiết lập quan hệ happens-before cho mọi dữ liệu mutable mà lambda tham chiếu.

Nếu truyền task qua `ExecutorService`, executor có các quy tắc memory consistency riêng cho submission và task execution; tuy vậy các mutation sau submission và các shared fields khác vẫn phải được quản lý đúng.

### 10.3. Dùng AtomicInteger khi cần mutable counter dùng chung

~~~java
AtomicInteger count = new AtomicInteger();

Runnable task = () -> count.incrementAndGet();
~~~

`AtomicInteger` cung cấp các thao tác nguyên tử cho counter. Nó phù hợp với một số bài toán đếm; không thay thế transaction hoặc lock khi nhiều field phải thay đổi nhất quán cùng nhau.

### 10.4. Dùng synchronized khi invariant cần nhiều thao tác cùng nhau

~~~java
Object lock = new Object();
List<String> values = new ArrayList<String>();

Runnable task = () -> {
    synchronized (lock) {
        values.add("Java");
    }
};
~~~

Lock là object được quản lý riêng. Mọi đường đọc/ghi cùng invariant phải tuân theo cùng synchronization protocol.

### 10.5. Không sửa captured state từ nhiều threads mà không có policy

Một lambda có thể chạy trên executor, scheduler hoặc callback thread bất kỳ theo API được dùng. Đừng giả định thân lambda luôn chạy trên thread tạo ra nó. Xác định thread ownership, visibility, ordering và cancellation.

## 11. Capture có thể giữ bộ nhớ ngoài dự kiến

### 11.1. Capture toàn bộ this để dùng một field nhỏ

~~~java
class ReportService {
    private final LargeRepository repository = new LargeRepository();
    private final String reportName = "daily";

    Runnable callback() {
        return () -> System.out.println(reportName);
    }
}
~~~

Lambda tham chiếu field qua enclosing instance. Nếu callback sống lâu, reference tới `ReportService` có thể giữ `repository` cùng object graph liên quan sống lâu.

Nếu hợp lý, chỉ capture giá trị cần thiết:

~~~java
Runnable callback() {
    final String name = reportName;
    return () -> System.out.println(name);
}
~~~

Compiler/runtime vẫn quyết định representation, nhưng về mặt object graph, lambda không cần dùng enclosing instance để đọc field nếu nó chỉ cần một immutable String value.

### 11.2. Capture một collection lớn khi chỉ cần một con số

~~~java
List<Order> orders = loadOrders();

int countAtCreation = orders.size();
Runnable callback = () -> logCount(countAtCreation);
~~~

Nếu callback chỉ cần count, capture số đếm có thể tránh giữ cả collection. Đây là lựa chọn thiết kế dựa trên lifetime; không phải yêu cầu compiler phải cấp phát ít object hơn.

### 11.3. Listener cần lifecycle rõ ràng

Khi đăng ký callback vào event bus, scheduler hoặc GUI component, xác định:

- Ai sở hữu listener?
- Khi nào đăng ký?
- Khi nào hủy đăng ký?
- Callback có giữ reference tới view/controller/session không?
- Có thể chạy sau khi resource đã đóng không?

Một lambda ngắn không tự bảo đảm lifecycle đúng.

## 12. Giới hạn phụ thuộc implementation: phải phân biệt ba lớp

Cụm từ “implementation-dependent limits” có thể chỉ nhiều loại giới hạn. Không nên gộp thành một con số duy nhất cho capture.

| Lớp giới hạn | Ai quy định? | Ví dụ |
| --- | --- | --- |
| Quy tắc ngôn ngữ Java | JLS | Local variable được capture phải final/effectively final |
| Cấu trúc class file/JVM | JVMS | Giới hạn constant pool, method code, locals, parameters, array dimensions |
| Tài nguyên runtime/OS | JVM implementation và môi trường | Heap, stack, metaspace, thread count, object allocation |

### 12.1. JLS không đưa ra một số lượng biến capture tối đa phổ quát

Không có một quy tắc Java kiểu “một lambda chỉ được capture tối đa N local variables” dùng chung cho mọi compiler/JVM.

Tuy nhiên, compiler phải tạo ra representation hợp lệ theo class-file/JVM constraints. Nếu implementation biểu diễn captured values qua các method descriptor hoặc call-site parameters, giới hạn descriptor có thể liên quan. Điều đó **không biến giới hạn tham số method thành một con số capture độc lập được JLS bảo đảm**.

### 12.2. Một số giới hạn class-file/JVM có tính cấu trúc

JVMS quy định những giới hạn chung, không riêng cho lambda:

| Thành phần | Giới hạn cấu trúc được đặc tả | Ý nghĩa |
| --- | --- | --- |
| Constant pool của một class/interface | Giới hạn bởi trường đếm 16-bit; đặc tả mô tả mức tối đa 65.535 entries | Tổng constants, class/method/field references và dữ liệu liên quan |
| Bytecode của một method | `code_length < 65.536` bytes | Code array của một method không thể dài tùy ý |
| Local-variable slots | Tối đa 65.535 slots | `long` và `double` dùng hai slots |
| Operand-stack depth | Trường `max_stack` có giới hạn 65.535 values/units theo JVMS | `long`/`double` chiếm hai units |
| Method descriptor parameters | Tối đa 255 parameter units | Instance method tính thêm slot cho `this`; `long`/`double` chiếm hai |
| Array dimensions | Tối đa 255 dimensions | Ràng buộc của JVM array instructions/type descriptors |
| Fields/methods trong class file | Trường đếm 16-bit, giới hạn đặc tả 65.535 | Giới hạn cấu trúc class/interface |

Các số trên là giới hạn cấu trúc của class file/JVM, **không phải khuyến nghị thiết kế ứng dụng**. Compiler có thể gặp giới hạn nhỏ hơn trong một số trường hợp thực tế do cách sinh bytecode, metadata hoặc tài nguyên.

### 12.3. Không suy ra “255 captured variables”

Giới hạn 255 parameter units thuộc method descriptor. Một lambda có thể được compiler biểu diễn bằng một call site và implementation method có captured arguments; nhưng cách hạ mã là implementation strategy.

Không dùng 255 làm hằng số business hoặc validation cho số biến lambda được capture. Nếu compiler báo descriptor/code/class-file quá lớn, hãy giảm độ phức tạp method, chia helper hoặc thiết kế lại data object.

### 12.4. Giới hạn heap và object size phụ thuộc runtime

`Runtime.getRuntime().maxMemory()` cho biết mức heap tối đa mà JVM sẽ cố gắng sử dụng theo cấu hình hiện tại. Giá trị này không phải:

- Dung lượng heap còn trống tại thời điểm gọi.
- Kích thước tối đa của một object.
- Bảo đảm một allocation cụ thể thành công.
- Tổng memory của cả process, native memory, metaspace và stacks.

Object allocation có thể thất bại với `OutOfMemoryError`. Kích thước object tối đa còn phụ thuộc VM, object layout, GC, alignment, heap size và OS.

### 12.5. Stack, metaspace và thread cũng có giới hạn riêng

- Stack mỗi thread có thể hết chỗ và dẫn tới `StackOverflowError`.
- Class metadata dùng vùng nhớ runtime riêng (ví dụ metaspace trong HotSpot).
- Thread/native stack và OS thread resources có giới hạn.
- Class loading quá nhiều hoặc giữ classloader sống lâu có thể làm tăng metadata usage.
- Một callback/lambda giữ object graph lâu có thể làm tăng heap retention dù bản thân function object nhỏ.

### 12.6. Không có một giá trị -Xmx/-Xss phù hợp mọi môi trường

`-Xmx` và `-Xss` là tùy chọn launcher/runtime thường dùng để cấu hình heap/stack trên các JVM hỗ trợ. Giá trị phù hợp tùy workload, container limits, OS, GC, số threads và mục tiêu latency.

Đừng sao chép một con số từ laptop sang production mà không đo memory footprint và concurrency.

## 13. Giới hạn về class-file không phải lỗi của lambda

Nếu class chứa quá nhiều constants hoặc một method quá lớn, compiler có thể báo lỗi như code quá lớn, constant pool quá lớn hoặc không tạo được class file hợp lệ.

Những lỗi đó có thể xuất hiện trong một class có nhiều lambda, nhưng cũng có thể xảy ra trong code Java không sử dụng lambda.

Cách xử lý thường là:

1. Chia một method quá lớn thành các method nhỏ có trách nhiệm rõ.
2. Tách generated code hoặc bảng constants lớn thành class/resource phù hợp.
3. Giảm số constants trùng lặp nếu generated source tạo quá nhiều metadata.
4. Kiểm tra bytecode bằng `javap -c -v` khi cần xác định method/constant pool nào quá lớn.
5. Không thay đổi source chỉ để làm vừa một giới hạn tưởng tượng của lambda.

**Đừng tự đặt một giới hạn capture không có trong JLS.** Hãy đọc thông báo compiler và đối chiếu đúng class-file/JVM constraint mà compiler báo.

## 14. Đo allocation và hiệu năng đúng cách

### 14.1. Không dùng System.nanoTime cho một lần chạy ngắn để kết luận

JVM có class loading, interpreter, JIT compilation, warmup, GC và các yếu tố nền. Một phép đo một lần dễ phản ánh startup noise hơn là steady-state performance.

### 14.2. Dùng JMH cho microbenchmark

JMH là công cụ benchmark JVM chuyên dụng. Khi đo lambda/method reference:

- Có warmup iterations.
- Có nhiều measurement iterations và forks.
- Dùng input đủ thực tế để tránh dead-code elimination.
- Tránh tạo benchmark mà compiler có thể tính trước kết quả.
- Đo cả throughput/latency và allocation nếu phù hợp.
- Không so hai đoạn code khác semantics hoặc khác workload.

### 14.3. Dùng profiler để xem allocation thực tế

Tùy JDK và môi trường, có thể dùng Java Flight Recorder (JFR), async-profiler allocation profiling hoặc công cụ tương đương. Xác minh tool support của runtime đang triển khai.

Không kết luận số object chỉ bằng nhìn source hoặc bằng việc gọi `System.gc()`.

### 14.4. Escape analysis có thể làm benchmark sai lệch nếu không thiết kế đúng

Nếu object không escape và kết quả không được quan sát, JIT có thể loại bỏ allocation hoặc computation. Benchmark phải khiến kết quả có ý nghĩa quan sát được, nhưng không thêm side effects đến mức làm thay đổi workload.

### 14.5. Đo workload toàn ứng dụng trước khi tối ưu capture

Chi phí lớn thường nằm ở I/O, boxing, collection growth, synchronization, parsing, network hoặc thuật toán. Đừng thay lambda bằng anonymous class/loop chỉ vì giả định lambda luôn cấp phát nhiều object hơn.

## 15. Chương trình Java 8 hoàn chỉnh: capture, reference và method reference

Ví dụ này kiểm tra:

1. Capture một local variable effectively final.
2. Tạo capture riêng cho từng vòng lặp.
3. Capture một reference tới StringBuilder và thấy mutation của object.
4. Capture receiver qua bound method reference.
5. Capture enclosing instance bằng `this`.
6. Method reference tĩnh không cần receiver.
7. Capture method parameter trong factory.
8. Ghép các predicate trong primitive stream.
9. Đọc thông tin max heap mà không giả định một kích thước cụ thể.

Lưu thành **CaptureAllocationDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.function.Function;
import java.util.function.IntPredicate;
import java.util.function.Supplier;

public final class CaptureAllocationDemo {
    static final class Prefixer {
        private final String prefix;

        Prefixer(String prefix) {
            this.prefix = prefix;
        }

        String apply(String value) {
            return prefix + value;
        }

        Supplier<String> captureThis() {
            return () -> prefix;
        }
    }

    private static boolean isPositive(int value) {
        return value > 0;
    }

    private static IntPredicate thresholdAt(int threshold) {
        return value -> value >= threshold;
    }

    public static void main(String[] args) {
        int minimum = 10;
        IntPredicate atLeastMinimum = value -> value >= minimum;
        System.out.println("effectively final capture = "
                + atLeastMinimum.test(12));

        List<IntPredicate> perIteration = new ArrayList<IntPredicate>();
        for (int i = 0; i < 3; i++) {
            final int currentThreshold = i;
            perIteration.add(value -> value >= currentThreshold);
        }
        System.out.println("loop captures = "
                + perIteration.get(0).test(0) + ","
                + perIteration.get(1).test(0) + ","
                + perIteration.get(2).test(0));

        StringBuilder state = new StringBuilder("before");
        Supplier<String> readState = () -> state.toString();
        state.append("-after");
        System.out.println("captured reference sees mutation = "
                + readState.get());

        StringBuilder receiver = new StringBuilder("bound");
        Supplier<String> boundMethod = receiver::toString;
        receiver.append("-receiver");
        System.out.println("bound method reference = " + boundMethod.get());

        Prefixer prefixer = new Prefixer("Java-");
        Function<String, String> boundInstanceMethod = prefixer::apply;
        System.out.println("bound instance method = "
                + boundInstanceMethod.apply("8"));
        System.out.println("this capture = "
                + prefixer.captureThis().get());

        IntPredicate statelessMethodReference =
                CaptureAllocationDemo::isPositive;
        System.out.println("stateless method reference = "
                + statelessMethodReference.test(5));

        IntPredicate capturedPredicate = thresholdAt(7);
        System.out.println("captured parameter = "
                + capturedPredicate.test(7) + ","
                + capturedPredicate.test(6));

        List<Integer> values = Arrays.asList(-2, -1, 0, 1, 2, 3);
        long count = values.stream().mapToInt(Integer::intValue)
                .filter(statelessMethodReference)
                .filter(thresholdAt(2))
                .count();
        System.out.println("composed predicates = " + count);

        System.out.println("runtime max heap is positive = "
                + (Runtime.getRuntime().maxMemory() > 0L));
    }
}
~~~

Biên dịch với JDK có hỗ trợ target Java 8:

~~~bash
javac --release 8 CaptureAllocationDemo.java
java CaptureAllocationDemo
~~~

Trên JDK 8 trực tiếp, có thể dùng `javac CaptureAllocationDemo.java` rồi `java CaptureAllocationDemo`. Các API trong source đều có từ Java 8.

**Stdout đã được biên dịch và chạy xác minh:**

~~~text
effectively final capture = true
loop captures = true,false,false
captured reference sees mutation = before-after
bound method reference = bound-receiver
bound instance method = Java-8
this capture = Java-
stateless method reference = true
captured parameter = true,false
composed predicates = 2
runtime max heap is positive = true
~~~

### 15.1. Giải thích output

- `effectively final capture = true`: lambda sử dụng local variable `minimum=10`.
- `loop captures = true,false,false`: mỗi predicate giữ threshold 0, 1 và 2; giá trị thử là 0.
- `captured reference sees mutation = before-after`: lambda giữ reference tới StringBuilder, object đã được append sau khi tạo lambda.
- `bound method reference = bound-receiver`: receiver đã xác định là cùng StringBuilder.
- `bound instance method = Java-8`: method reference gọi instance method trên `Prefixer`.
- `this capture = Java-`: lambda trả về field của enclosing instance.
- `stateless method reference = true`: method reference tới static method kiểm tra số dương.
- `captured parameter = true,false`: factory `thresholdAt(7)` tạo predicate có cấu hình threshold.
- `composed predicates = 2`: trong danh sách, hai số 2 và 3 vừa dương vừa lớn hơn hoặc bằng 2.
- `runtime max heap is positive = true`: demo chỉ xác minh JVM cung cấp giá trị max heap dương trong runtime đã chạy; **không** cố định số byte hay suy ra giới hạn object.

### 15.2. Vì sao không in số lambda allocations?

JLS cho phép implementation cấp phát instance mới hoặc dùng instance có sẵn; JIT còn có thể loại bỏ một số allocation. Vì vậy một số lượng cố định in ra sẽ gây hiểu nhầm nếu coi là contract Java.

Nếu cần đo allocation, hãy dùng benchmark/profiler trên đúng JDK, JVM flags, workload và môi trường triển khai.

## 16. Các lỗi thường gặp

### Lỗi 1 — Capture local variable rồi gán lại

Biến không effectively final và compiler từ chối. **Sửa:** tạo một biến final/effectively final riêng nếu cần snapshot giá trị.

### Lỗi 2 — Nghĩ final reference làm object bất biến

Reference không đổi nhưng object có thể mutable. **Sửa:** chọn immutable object hoặc quản lý state/concurrency riêng.

### Lỗi 3 — Capture reference rồi mong có deep copy

Lambda giữ reference theo semantics, không tự sao chép toàn bộ graph. **Sửa:** tạo snapshot/copy rõ ràng khi cần.

### Lỗi 4 — Dùng array holder để lách effectively final

Code có thể chạy nhưng tạo mutable shared state khó hiểu. **Sửa:** dùng holder có semantics rõ như AtomicInteger hoặc object sở hữu state.

### Lỗi 5 — Capture biến điều khiển for đang tăng

Biến không effectively final. **Sửa:** tạo biến final cho từng vòng lặp.

### Lỗi 6 — Nghĩ capture biến là capture stack pointer

Đây không phải semantics Java. **Sửa:** hiểu language guarantees; không dựa vào bố trí stack/heap nội bộ.

### Lỗi 7 — Nhầm capture với invocation

Tạo lambda không đồng nghĩa thân lambda chạy ngay. **Sửa:** phân biệt evaluation/capture và functional method invocation.

### Lỗi 8 — Nghĩ this trong lambda là object lambda

Trong lambda, `this` là enclosing instance. **Sửa:** nhớ semantics lexical của lambda.

### Lỗi 9 — Capture toàn bộ service chỉ để lấy một giá trị nhỏ

Có thể giữ object graph lớn sống lâu. **Sửa:** capture dữ liệu tối thiểu và quản lý listener lifecycle.

### Lỗi 10 — Nghĩ method reference luôn stateless

`service::handle` capture receiver. **Sửa:** phân biệt bound và unbound method reference.

### Lỗi 11 — Nghĩ bound method reference gọi method ngay khi tạo

Expression tạo function object; method được gọi khi functional method chạy. **Sửa:** tách receiver binding và invocation.

### Lỗi 12 — So sánh lambda bằng ==

Identity không được đảm bảo. **Sửa:** so sánh kết quả/behavior hoặc dùng ID nghiệp vụ riêng.

### Lỗi 13 — Khóa synchronized trên lambda

Object identity không ổn định theo contract. **Sửa:** tạo lock object riêng.

### Lỗi 14 — Dùng identityHashCode làm khóa hoặc ID

Không đảm bảo duy nhất hoặc bền vững. **Sửa:** dùng identifier do ứng dụng quản lý.

### Lỗi 15 — Nghĩ stateless lambda luôn cache

Implementation có thể tái sử dụng hoặc cấp phát mới. **Sửa:** không dựa vào cache behavior.

### Lỗi 16 — Nghĩ capturing lambda luôn cấp phát object mới

Runtime có thể tái sử dụng object phù hợp và JIT có thể tối ưu. **Sửa:** đo allocation thật.

### Lỗi 17 — Coi invokedynamic là yêu cầu của ngôn ngữ

Đó là một strategy phổ biến của compiler/runtime, không phải cách duy nhất mà JLS bắt buộc. **Sửa:** không phụ thuộc bytecode detail trong logic nghiệp vụ.

### Lỗi 18 — Phụ thuộc tên class lambda sinh ra

Tên/class layout là implementation detail. **Sửa:** dùng functional interface contract.

### Lỗi 19 — Cho rằng escape analysis luôn loại bỏ allocation

Tối ưu phụ thuộc runtime profile và khả năng phân tích. **Sửa:** không viết correctness/performance assumption dựa vào tối ưu tùy chọn.

### Lỗi 20 — Gọi scalar replacement là stack allocation

Đây là hai khái niệm khác nhau. **Sửa:** mô tả đúng rằng một số object allocation có thể bị loại bỏ và field xử lý như scalar values.

### Lỗi 21 — Nghĩ effectively final bảo đảm thread safety

Nó chỉ bảo vệ binding local, không bảo vệ mutable object. **Sửa:** dùng synchronization/atomic/concurrent collection phù hợp.

### Lỗi 22 — Dùng lambda callback lâu dài nhưng không hủy listener

Callback có thể giữ object graph và resource sống lâu. **Sửa:** quản lý registration/unregistration.

### Lỗi 23 — Cho rằng mọi JVM có cùng heap/object-size limit

Tài nguyên phụ thuộc VM/OS/config. **Sửa:** đo và cấu hình trong deployment thực tế.

### Lỗi 24 — Nhầm 255 method parameter units là 255 captured variables

Không có suy luận portable như vậy. **Sửa:** hiểu đây là giới hạn method descriptor; representation lambda do implementation chọn.

### Lỗi 25 — Nhầm class-file code limit là giới hạn riêng của lambda

Giới hạn code length áp dụng cho mọi method. **Sửa:** chia method/class quá lớn theo cấu trúc hợp lý.

### Lỗi 26 — Dùng Runtime.maxMemory như free heap

Nó là giới hạn heap tối đa theo cấu hình, không phải lượng heap còn trống. **Sửa:** dùng đúng metric và profiler phù hợp.

### Lỗi 27 — Benchmark lambda chỉ một lần bằng nanoTime

Warmup/JIT/GC làm kết quả sai lệch. **Sửa:** JMH với warmup, forks, input và allocation profiler.

### Lỗi 28 — Thêm side effect để ngăn benchmark bị tối ưu mà không kiểm soát

Có thể làm thay đổi workload cần đo. **Sửa:** dùng JMH Blackhole/benchmark design phù hợp.

### Lỗi 29 — Dùng serialized lambda làm format lưu trữ dài hạn

Serialized lambda có implementation details và ràng buộc captured values. **Sửa:** serialize một DTO/schema do ứng dụng sở hữu.

### Lỗi 30 — Tối ưu capture trước khi có số liệu

Độ trễ có thể đến từ I/O, boxing, allocation khác hoặc thuật toán. **Sửa:** profile trước, tối ưu bottleneck đã đo.

## 17. Checklist khi thiết kế lambda và callback

Trước khi capture, hãy tự hỏi:

1. Local variable có final/effectively final không?
2. Tôi đang capture primitive value hay object reference?
3. Object được tham chiếu có mutable không?
4. Lambda chạy ngay hay sau khi method kết thúc?
5. Lambda có được lưu vào collection/listener/executor lâu dài không?
6. Capture `this` có giữ object graph lớn không?
7. Bound method reference có giữ receiver lâu hơn dự kiến không?
8. Có nhiều thread cùng đọc/ghi captured object không?
9. Có cần Atomic/lock/concurrent collection không?
10. Tôi có đang dựa vào lambda object identity không?
11. Tôi có đang giả định một lambda luôn cấp phát mới không?
12. Có thật sự cần low-level LambdaMetafactory không?
13. Có thể viết method reference/lambda đơn giản hơn không?
14. Method/class có đang tiến gần giới hạn class-file không?
15. Đã đo allocation bằng JMH/profiler chưa?
16. Đã kiểm tra đúng JVM, heap, stack và container limits chưa?
17. Có quản lý unregister callback khi resource đóng không?
18. Có serialization hoặc persistence của lambda không? Nếu có, có schema bền vững hơn không?

### 17.1. Ma trận kiểm thử

| Trường hợp | Điều cần xác minh |
| --- | --- |
| Capture local final | Biên dịch và kết quả đúng |
| Capture local effectively final | Biên dịch |
| Gán lại local đã capture | Compile-time error |
| Tăng local đã capture | Compile-time error |
| Capture primitive | Giá trị đúng theo thời điểm capture |
| Capture mutable reference | Cùng object, mutation quan sát được |
| Capture this | this là enclosing instance |
| Bound method reference | Đúng receiver đã chọn |
| Unbound method reference | Receiver được truyền khi invocation |
| Capture trong vòng for | Mỗi iteration có giá trị riêng |
| Capture trong enhanced-for | Kiểm tra semantics từng iteration |
| Callback trả ra khỏi method | Giá trị capture vẫn dùng được |
| Callback lưu lâu dài | Không giữ object graph/resource ngoài ý muốn |
| Lambda chạy nhiều thread | Shared mutable state an toàn |
| So sánh lambda identity | Code không dựa vào identity |
| Runtime khác nhau | Behavior functional interface giống nhau |
| Compiler khác nhau | Không phụ thuộc class name/bytecode layout |
| JIT bật/tắt | Kết quả semantics giống nhau |
| Allocation profiling | Đo trên workload có warmup |
| Class-file lớn | Nhận diện đúng limit và chia code hợp lý |

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Capture trong lambda là gì?

**Đáp án:** Sử dụng local variable, parameter, this hoặc receiver từ phạm vi bên ngoài lambda để tạo function object có thể dùng các giá trị đó khi invocation.

**Câu 2.** Local variable được capture phải thỏa điều kiện nào?

**Đáp án:** Phải final hoặc effectively final.

**Câu 3.** Biến effectively final có cần khai báo từ khóa final không?

**Đáp án:** Không. Compiler suy ra từ việc biến không bị gán lại.

**Câu 4.** Vì sao capture local primitive khác capture object reference?

**Đáp án:** Primitive là giá trị primitive; reference là giá trị trỏ tới object. Mutation của object vẫn có thể quan sát qua cùng reference.

**Câu 5.** Reference final có làm object immutable không?

**Đáp án:** Không. Nó chỉ ngăn gán lại reference.

**Câu 6.** Có thể capture một biến for-loop đang tăng trực tiếp không?

**Đáp án:** Không nếu biến đó không effectively final. Tạo biến final/effectively final cho từng iteration.

**Câu 7.** this trong lambda trỏ tới đâu?

**Đáp án:** Enclosing instance, không phải một object this riêng của lambda.

**Câu 8.** `service::handle` có capture không?

**Đáp án:** Có. Đây là bound method reference, receiver `service` được xác định tại thời điểm tạo expression.

**Câu 9.** `Type::instanceMethod` có capture receiver cụ thể không?

**Đáp án:** Không. Receiver được cung cấp như input khi functional method được gọi.

**Câu 10.** Lambda evaluation có chạy thân lambda ngay không?

**Đáp án:** Không. Nó tạo function object reference; thân chạy khi functional method được invocation.

**Câu 11.** JLS có bắt buộc mỗi lambda evaluation cấp phát object mới không?

**Đáp án:** Không. Implementation có thể cấp phát instance mới hoặc tham chiếu instance phù hợp đã có.

**Câu 12.** Có thể dùng == để xác định hai lambda có cùng object không?

**Đáp án:** Không được dựa vào kết quả đó; identity không được bảo đảm.

**Câu 13.** Có nên synchronize trên lambda không?

**Đáp án:** Không. Dùng lock object riêng có lifecycle rõ.

**Câu 14.** Stateless lambda có chắc được cache không?

**Đáp án:** Không. Reuse/cấp phát là implementation detail.

**Câu 15.** Capturing lambda có chắc tạo object mới mỗi lần không?

**Đáp án:** Không. Implementation có thể tái sử dụng instance phù hợp.

**Câu 16.** invokedynamic có phải yêu cầu của JLS không?

**Đáp án:** Không. Đây là strategy thường gặp của javac/runtime, không phải language guarantee.

**Câu 17.** LambdaMetafactory làm gì?

**Đáp án:** Hỗ trợ linkage để tạo/reuse function objects cho functional interface từ implementation method handle.

**Câu 18.** Escape analysis dùng để làm gì?

**Đáp án:** Phân tích object có thoát khỏi method/thread không, từ đó hỗ trợ các tối ưu như loại bỏ một số allocation/lock.

**Câu 19.** Scalar replacement có đồng nghĩa object được cấp phát trên stack không?

**Đáp án:** Không. Nó có thể loại bỏ object allocation và xử lý field như scalar values.

**Câu 20.** Effectively final có bảo vệ mutable object khỏi race condition không?

**Đáp án:** Không. Nó chỉ giới hạn việc gán lại local binding; object vẫn cần concurrency policy.

**Câu 21.** Vì sao callback có thể giữ service object sống lâu?

**Đáp án:** Lambda/method reference capture `this` hoặc receiver; callback còn reachable thì object graph có thể còn reachable.

**Câu 22.** JVM có giới hạn số captured local variables cố định cho mọi implementation không?

**Đáp án:** JLS không quy định một con số capture độc lập. Compiler/runtime còn phải tuân thủ các giới hạn class-file/JVM phù hợp với representation được chọn.

**Câu 23.** Giới hạn 255 parameters áp dụng cho điều gì?

**Đáp án:** Method descriptor parameter units trong JVM, bao gồm slot `this` cho instance method và hai units cho long/double; không phải một giới hạn portable “255 lambda captures”.

**Câu 24.** `Runtime.maxMemory()` trả về gì?

**Đáp án:** Mức heap tối đa JVM sẽ cố gắng sử dụng theo cấu hình hiện tại, không phải free heap hoặc object size tối đa.

**Câu 25.** Nên đo allocation của lambda bằng cách nào?

**Đáp án:** Dùng benchmark/profiler phù hợp như JMH và allocation profiling trên workload/JDK thực, không đếm object theo source syntax.

## 19. Tổng kết

- **Capture** cho phép lambda/method reference sử dụng dữ liệu từ ngữ cảnh bên ngoài. Evaluation, capture và invocation là những thời điểm khác nhau.
- Local variable, parameter và exception parameter được capture phải **final hoặc effectively final**.
- Capture primitive và capture reference có semantics khác nhau. Reference effectively final vẫn có thể trỏ tới object mutable.
- Trong lambda, `this` là enclosing instance. Bound method reference như `service::handle` giữ receiver đã chọn.
- **Không có bảo đảm lambda được cấp phát mới mỗi lần**. Runtime có thể tạo object hoặc reuse object phù hợp; identity không được dự đoán.
- javac thường dùng `invokedynamic`/`LambdaMetafactory`, nhưng bytecode, class name và object layout là implementation details.
- JIT/HotSpot có thể dùng escape analysis và scalar replacement để loại bỏ một số allocations; tối ưu không phải contract để code dựa vào.
- Capture `this`/receiver có thể giữ object graph sống lâu; quản lý callback lifecycle và memory retention.
- **JLS không đặt một con số captured variables tối đa phổ quát**. JVMS có các giới hạn class-file chung như constant pool, method code, locals, parameters và array dimensions.
- Heap, stack, object size và thread capacity phụ thuộc JVM/OS/configuration; đo trên runtime thực.
- **Java 8 demo đã biên dịch và chạy** để xác minh effectively-final capture, per-loop capture, mutable reference, bound method reference, this và predicate composition.

### Tài liệu tham khảo chính thức

- [Java Language Specification 8 — Lambda Expressions, `15.27](https://docs.oracle.com/javase/specs/jls/se8/html/jls-15.html#jls-15.27)
- [Java Language Specification 26 — Lambda Expressions, `15.27](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-15.html#jls-15.27)
- [Java Language Specification 26 — Effectively final variables, `4.12.4](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-4.html#jls-4.12.4)
- [Java Virtual Machine Specification 26 — Class File Format and Limits, `4](https://docs.oracle.com/en/java/javase/26/docs/specs/jvms/jvms-4.html)
- [Java SE 26 API — LambdaMetafactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html)
- [Oracle JDK 8 — HotSpot Escape Analysis](https://docs.oracle.com/javase/8/docs/technotes/guides/vm/performance-enhancements-7.html)
- [Oracle JDK 24 — HotSpot Virtual Machine Performance Enhancements](https://docs.oracle.com/en/java/javase/24/vm/java-hotspot-virtual-machine-performance-enhancements.html)
- [Java SE 8 API — Runtime.maxMemory](https://docs.oracle.com/javase/8/docs/api/java/lang/Runtime.html#maxMemory--)
- [Java SE 8 API — IntPredicate](https://docs.oracle.com/javase/8/docs/api/java/util/function/IntPredicate.html)
- [Java SE 8 API — Supplier](https://docs.oracle.com/javase/8/docs/api/java/util/function/Supplier.html)
