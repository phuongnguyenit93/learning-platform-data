# Method reference và constructor reference

Trong Java 27, **method reference** (tham chiếu phương thức) và **constructor reference** (tham chiếu constructor) là những cú pháp giúp truyền hành vi hoặc cách tạo đối tượng vào nơi đang cần một **functional interface**. Chúng thường giúp mã ngắn gọn hơn lambda khi công việc cần thực hiện đã có sẵn dưới dạng một phương thức hoặc constructor phù hợp.

Ví dụ, thay vì viết:

~~~java
List<String> names = List.of("Lan", "Minh", "An");
names.forEach(name -> System.out.println(name));
~~~

có thể viết:

~~~java
names.forEach(System.out::println);
~~~

Cả hai ví dụ đều gọi **println(...)** cho từng tên. Biểu thức **System.out::println** là một method reference, không phải lời gọi **println(...)** ngay tại nơi khai báo.

Bài viết giải thích các loại method reference, constructor reference, cách Java suy luận chữ ký, sự khác biệt với lambda, những lỗi thường gặp và cách dùng trong API Java hiện đại. Các ví dụ sử dụng cú pháp và API đang áp dụng trong Java 27, không phụ thuộc tính năng preview hoặc API legacy.

## 1. Ôn lại functional interface và lambda

**Functional interface** là interface có đúng một phương thức trừu tượng cần được triển khai, xét theo các quy tắc functional interface của Java. Interface vẫn có thể chứa default method, static method và các khai báo phù hợp khác. Annotation **@FunctionalInterface** giúp trình biên dịch kiểm tra ý định của người khai báo.

~~~java
@FunctionalInterface
interface TextTransformer {
    String transform(String text);
}
~~~

Ta có thể triển khai hợp đồng bằng lambda:

~~~java
TextTransformer transformer = text -> text.strip();

System.out.println(transformer.transform("  Java  ")); // Java
~~~

Nếu chỉ đơn giản gọi một method đã tồn tại, có thể dùng method reference:

~~~java
TextTransformer transformer = String::strip;

System.out.println(transformer.transform("  Java  ")); // Java
~~~

**String::strip** tương thích với hợp đồng **String transform(String)**: đối số **text** trở thành đối tượng nhận lời gọi **strip()**, và kết quả String được trả về.

Method reference thường **không khai báo loại tham số hoặc kiểu trả về riêng**. Nó nhận ngữ cảnh kiểu từ functional interface đích (*target type*) và được kiểm tra tính tương thích với phương thức được tham chiếu.

### Các functional interface thường dùng

| Interface | Phương thức trừu tượng | Mục đích phổ biến |
|---|---|---|
| **Runnable** | **void run()** | Một thao tác không có tham số và không trả giá trị |
| **Supplier<T>** | **T get()** | Cung cấp giá trị khi được gọi |
| **Consumer<T>** | **void accept(T value)** | Nhận và xử lý một giá trị |
| **Predicate<T>** | **boolean test(T value)** | Kiểm tra điều kiện |
| **Function<T, R>** | **R apply(T value)** | Biến đổi T thành R |
| **BiFunction<T, U, R>** | **R apply(T, U)** | Kết hợp hai đầu vào tạo kết quả |
| **UnaryOperator<T>** | **T apply(T value)** | Biến đổi một giá trị nhưng giữ cùng kiểu |
| **Comparator<T>** | **int compare(T a, T b)** | So sánh thứ tự giữa hai giá trị |
| **IntFunction<R>** | **R apply(int value)** | Nhận tham số int, thường dùng tạo mảng |
| **ToIntFunction<T>** | **int applyAsInt(T value)** | Biến một giá trị thành int |

Một số giao diện có phương thức nhận kiểu nguyên thủy như **ToIntFunction<T>** giúp tránh boxing ở các vị trí phù hợp.

## 2. Cú pháp :: và các dạng tham chiếu

Toán tử **::** dùng để tạo tham chiếu phương thức hoặc constructor trong ngữ cảnh có target type. Các dạng phổ biến:

| Dạng | Cú pháp | Ý nghĩa |
|---|---|---|
| Tham chiếu static method | **TypeName::staticMethod** | Gọi phương thức static của kiểu được chỉ định |
| Tham chiếu instance method có receiver | **expression::instanceMethod** | Gọi method trên đối tượng đã được xác định |
| Tham chiếu instance method không gắn receiver | **ReferenceType::instanceMethod** | Lấy receiver từ đối số đầu tiên của functional interface |
| Tham chiếu method của lớp cha | **super::instanceMethod** | Gọi cách triển khai phù hợp ở lớp cha, trong ngữ cảnh hợp lệ |
| Tham chiếu constructor | **ClassName::new** | Tạo đối tượng khi functional method được gọi |
| Tham chiếu constructor mảng | **ElementType[]::new** | Tạo mảng với kích thước nhận từ functional method |

Các biểu thức tham chiếu phải được đặt vào **ngữ cảnh functional interface phù hợp**. Dấu **::** không phải một cách viết khác của dấu chấm trong mọi tình huống.

Ví dụ, **String::length** chưa phải giá trị thuộc một kiểu phương thức độc lập mà có thể gán trực tiếp cho bất cứ biến nào:

~~~java
// var length = String::length; // Không biên dịch: thiếu target type.
~~~

Thay vào đó:

~~~java
java.util.function.ToIntFunction<String> length = String::length;

System.out.println(length.applyAsInt("Java")); // 4
~~~

## 3. Dạng 1: tham chiếu phương thức static

Với static method, cú pháp cơ bản:

~~~java
TypeName::methodName
~~~

Ví dụ, **Integer.parseInt(String)** nhận một chuỗi và trả về **int**:

~~~java
import java.util.function.Function;

Function<String, Integer> parser = Integer::parseInt;

System.out.println(parser.apply("27")); // 27
~~~

Chữ ký của functional interface là **Integer apply(String)**, còn phương thức static được chọn trả về **int**. Việc chuyển **int** sang **Integer** ở kết quả được Java hỗ trợ thông qua boxing.

Dạng lambda tương đương về hành vi trong ví dụ này:

~~~java
Function<String, Integer> parser = text -> Integer.parseInt(text);
~~~

### Khi dùng với Predicate

~~~java
import java.util.Objects;
import java.util.function.Predicate;

Predicate<String> present = Objects::nonNull;

System.out.println(present.test("Java")); // true
System.out.println(present.test(null));   // false
~~~

**Objects.nonNull(Object)** là static method trả boolean, nên phù hợp với **Predicate<String>**.

### Static method có nhiều overload

Một static method có thể có nhiều phiên bản. Chẳng hạn **String.valueOf(...)** có các overload nhận nhiều kiểu khác nhau. Java dùng **target type** và các quy tắc overload resolution để chọn phương thức phù hợp.

~~~java
import java.util.function.Function;

Function<Integer, String> toText = String::valueOf;

System.out.println(toText.apply(42)); // 42
~~~

Không phải ngẫu nhiên Java chọn một overload: nó dựa vào chữ ký của functional interface đích. Khi ngữ cảnh không đủ để phân biệt những overload hợp lệ, trình biên dịch sẽ báo nhập nhằng; cần làm rõ target type hoặc dùng lambda.

## 4. Dạng 2: tham chiếu instance method đã có receiver

Khi đã có một đối tượng cụ thể, dùng:

~~~java
expression::instanceMethod
~~~

Ví dụ:

~~~java
import java.util.function.Consumer;

Consumer<String> printer = System.out::println;

printer.accept("Hello Java"); // Hello Java
~~~

**System.out** là đối tượng **PrintStream**. Method reference lưu ngữ cảnh receiver phù hợp, sau đó **accept(String)** chuyển giá trị nhận được tới **println(String)**.

Một ví dụ khác:

~~~java
import java.util.function.Predicate;

String text = "Java programming";

Predicate<String> startsWith = text::startsWith;

System.out.println(startsWith.test("Java")); // true
System.out.println(startsWith.test("Kotlin")); // false
~~~

Receiver **text** được xác định khi tạo method reference; giá trị truyền vào **test(...)** trở thành đối số của **startsWith(...)**.

Dạng lambda tương đương về ý nghĩa lời gọi:

~~~java
Predicate<String> startsWith = prefix -> text.startsWith(prefix);
~~~

### Dùng this::method trong lớp hiện tại

~~~java
import java.util.function.Consumer;

class EventHandler {
    void handle(String event) {
        System.out.println("Event: " + event);
    }

    Consumer<String> callback() {
        return this::handle;
    }
}
~~~

Ví dụ sử dụng:

~~~java
EventHandler handler = new EventHandler();

handler.callback().accept("started"); // Event: started
~~~

**this::handle** tham chiếu tới instance method của đối tượng **EventHandler** hiện tại. Nó phù hợp khi cần cung cấp callback cho một API khác.

Trong static context không có **this** của một đối tượng hiện tại, nên không thể viết **this::method** ở đó.

## 5. Dạng 3: tham chiếu instance method không có receiver cụ thể

Dạng này thường có cú pháp:

~~~java
ReferenceType::instanceMethod
~~~

Nó không gắn sẵn một đối tượng nhận lời gọi. Thay vào đó, **đối số đầu tiên** của functional interface trở thành receiver.

Ví dụ:

~~~java
import java.util.function.Function;

Function<String, Integer> length = String::length;

System.out.println(length.apply("Java")); // 4
~~~

Tương đương về hành vi với:

~~~java
Function<String, Integer> length = value -> value.length();
~~~

**String::length** ở đây **không** phải tham chiếu static method; **length()** là instance method. Kiểu đầu vào **String** của **Function<String, Integer>** cung cấp receiver.

### Method có thêm tham số

~~~java
import java.util.function.BiPredicate;

BiPredicate<String, String> beginsWith = String::startsWith;

System.out.println(beginsWith.test("Java 27", "Java")); // true
System.out.println(beginsWith.test("Hello", "Java"));   // false
~~~

Functional method **test(String text, String prefix)** có hai đối số:

- Đối số thứ nhất **text** là receiver.
- Đối số thứ hai **prefix** được chuyển tới **text.startsWith(prefix)**.

Lambda tương đương:

~~~java
BiPredicate<String, String> beginsWith =
        (text, prefix) -> text.startsWith(prefix);
~~~

### Dùng làm Comparator

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> languages =
        new ArrayList<>(List.of("java", "Python", "kotlin"));

languages.sort(String::compareToIgnoreCase);

System.out.println(languages); // [java, kotlin, Python]
~~~

Method **String.compareToIgnoreCase(String)** có một tham số String, nhưng **Comparator<String>** có hai tham số. Đối số thứ nhất là receiver, đối số thứ hai là tham số của **compareToIgnoreCase(...)**.

Phương pháp này phù hợp với yêu cầu so sánh không phân biệt hoa/thường theo hợp đồng method. Nếu cần sắp xếp văn bản cho người dùng theo locale, nên cân nhắc **Collator** thay vì mặc định rằng **compareToIgnoreCase()** áp dụng quy tắc ngôn ngữ địa phương.

## 6. Phân biệt bound và unbound instance method reference

Hai dạng nhìn tương tự nhưng dùng functional interface khác nhau.

~~~java
import java.util.function.Function;
import java.util.function.Supplier;

String word = "Java";

Supplier<Integer> bound = word::length;
Function<String, Integer> unbound = String::length;

System.out.println(bound.get());        // 4
System.out.println(unbound.apply("Hi")); // 2
~~~

| Thuộc tính | **word::length** | **String::length** |
|---|---|---|
| Receiver | Đối tượng **word** đã được xác định | Receiver do người gọi truyền vào |
| Functional interface ở ví dụ | **Supplier<Integer>** | **Function<String, Integer>** |
| Đối số chức năng | Không có đối số | Một đối số String |
| Lời gọi thực tế | **word.length()** | **value.length()** |
| Khả năng tái sử dụng | Gắn với receiver đang có | Dùng được trên nhiều instance |

Không thể thay thế trực tiếp **word::length** bằng **String::length** mà giữ nguyên **Supplier<Integer>** vì method reference thứ hai cần một receiver qua tham số đầu tiên.

### Đối với static method

Với static method, dạng nên dùng là **TypeName::staticMethod**. Không xem **someObject::staticMethod** là cách thông thường để tạo bound reference tới static method; cú pháp và kiểm tra tính phù hợp có quy tắc riêng, và static method không có receiver instance.

## 7. Dạng 4: tham chiếu phương thức của lớp cha bằng super::

Java cho phép tạo method reference tới cách triển khai phù hợp của lớp cha trong ngữ cảnh instance.

~~~java
import java.util.function.Supplier;

class BaseMessage {
    String describe() {
        return "base message";
    }
}

class DetailedMessage extends BaseMessage {
    @Override
    String describe() {
        return "detailed message";
    }

    Supplier<String> baseDescription() {
        return super::describe;
    }
}
~~~

Ví dụ:

~~~java
DetailedMessage message = new DetailedMessage();

System.out.println(message.describe());            // detailed message
System.out.println(message.baseDescription().get()); // base message
~~~

Trong method **baseDescription()**, **super::describe** tạo một reference trỏ tới cách triển khai từ lớp cha. Nó khác **this::describe**, vốn áp dụng hành vi dispatch của instance method thông thường và sẽ gọi phiên bản ghi đè trong **DetailedMessage**.

**super::method** chỉ hợp lệ trong ngữ cảnh mà Java cho phép truy cập **super** của đối tượng hiện tại; không dùng nó như một tham chiếu tĩnh ở ngoài lớp hay trong static method.

Dạng này có ích khi muốn tái sử dụng một thao tác của lớp cha dưới dạng callback, nhưng không nên tạo cây kế thừa sâu chỉ để sử dụng method reference.

## 8. Constructor reference: ClassName::new

Constructor reference có cú pháp:

~~~java
ClassName::new
~~~

Nó mô tả cách **tạo đối tượng khi functional method được gọi**, chứ không tạo ngay tại biểu thức tham chiếu.

### Constructor không tham số

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

Supplier<List<String>> listFactory = ArrayList::new;

List<String> first = listFactory.get();
List<String> second = listFactory.get();

first.add("Java");

System.out.println(first);              // [Java]
System.out.println(second);             // []
System.out.println(first == second);    // false
~~~

**ArrayList::new** được ánh xạ tới constructor không tham số tương ứng với target type **Supplier<List<String>>**. Mỗi lần gọi **get()** tạo một ArrayList mới; danh sách **first** và **second** độc lập.

Lambda tương đương:

~~~java
Supplier<List<String>> listFactory = () -> new ArrayList<>();
~~~

### Constructor có một tham số

~~~java
import java.util.function.Function;

record Customer(String name) {}

Function<String, Customer> customerFactory = Customer::new;

Customer customer = customerFactory.apply("Lan");

System.out.println(customer.name()); // Lan
~~~

Record **Customer** có canonical constructor nhận String, phù hợp với **Function<String, Customer>**.

### Constructor có hai tham số

~~~java
import java.util.function.BiFunction;

record LineItem(String sku, int quantity) {}

BiFunction<String, Integer, LineItem> lineItemFactory = LineItem::new;

LineItem item = lineItemFactory.apply("BOOK-01", 2);

System.out.println(item.sku());      // BOOK-01
System.out.println(item.quantity()); // 2
~~~

Functional method **apply(String, Integer)** tương thích với constructor **LineItem(String, int)** nhờ unboxing **Integer** sang **int**.

### Constructor có nhiều overload

Nếu một lớp khai báo nhiều constructor, **target type** giúp chọn constructor phù hợp.

~~~java
class Message {
    private final String text;

    Message() {
        this("empty");
    }

    Message(String text) {
        this.text = text;
    }

    String text() {
        return text;
    }
}
~~~

~~~java
import java.util.function.Function;
import java.util.function.Supplier;

Supplier<Message> defaultMessage = Message::new;
Function<String, Message> fromText = Message::new;

System.out.println(defaultMessage.get().text()); // empty
System.out.println(fromText.apply("Ready").text()); // Ready
~~~

Cùng cú pháp **Message::new** có thể tham chiếu tới constructor khác nhau tùy chữ ký phương thức trừu tượng của functional interface.

## 9. Array constructor reference: T[]::new

Java cho phép tạo reference tới constructor mảng bằng cú pháp:

~~~java
ElementType[]::new
~~~

Ví dụ:

~~~java
import java.util.function.IntFunction;

IntFunction<String[]> stringArrayFactory = String[]::new;

String[] values = stringArrayFactory.apply(3);

System.out.println(values.length); // 3
System.out.println(values[0]);     // null
~~~

**IntFunction<String[]>** mô tả thao tác nhận một **int** là kích thước mảng và trả về **String[]**. Method reference **String[]::new** tương đương với:

~~~java
IntFunction<String[]> stringArrayFactory = size -> new String[size];
~~~

Tương tự:

~~~java
IntFunction<int[]> numbersFactory = int[]::new;

int[] numbers = numbersFactory.apply(4);
System.out.println(numbers.length); // 4
~~~

Kích thước mảng phải hợp lệ; ví dụ **apply(-1)** sẽ dẫn tới **NegativeArraySizeException** khi cố tạo mảng.

### Tạo mảng trong Stream.toArray()

Constructor reference tới mảng thường được dùng trong Stream API:

~~~java
import java.util.List;

List<String> names = List.of("Lan", "Minh", "An");

String[] array = names.stream().toArray(String[]::new);

System.out.println(array.length); // 3
~~~

Method **Stream.toArray(IntFunction<A[]>)** cần một factory nhận kích thước và trả về mảng đúng kiểu. **String[]::new** khớp với hợp đồng đó.

Không tạo được mảng trực tiếp với phần tử generic non-reifiable như **new List<String>[3]**; constructor reference không phải cách để vượt qua giới hạn của generic array creation. Nếu cần lưu nhiều danh sách generic, có thể dùng **List<List<String>>**.

## 10. Target typing: vì sao cùng :: có thể có nghĩa khác nhau?

Method reference là một **poly expression**: cách diễn giải và kiểu của biểu thức phụ thuộc vào ngữ cảnh nơi nó xuất hiện, thường là functional interface ở bên trái phép gán hoặc tham số phương thức.

Ví dụ:

~~~java
import java.util.function.Function;
import java.util.function.ToIntFunction;

Function<String, Integer> boxedLength = String::length;
ToIntFunction<String> primitiveLength = String::length;

System.out.println(boxedLength.apply("Java"));          // 4
System.out.println(primitiveLength.applyAsInt("Java")); // 4
~~~

Cả hai tham chiếu tới instance method **String.length()** trả **int**. Functional interface thứ nhất yêu cầu **Integer** nên kết quả được boxing; interface thứ hai giữ kết quả nguyên thủy.

### Không thể gán trực tiếp cho Object

~~~java
// Object reference = String::length; // Không hợp lệ.
~~~

**Object** không định nghĩa một functional method tương ứng để Java biết cần ánh xạ **String::length** vào chữ ký nào.

Nếu thật sự cần dùng **var**, hãy cung cấp target type thông qua một phép ép kiểu phù hợp:

~~~java
var length = (java.util.function.ToIntFunction<String>) String::length;

System.out.println(length.applyAsInt("Java")); // 4
~~~

Trong API dễ đọc, khai báo trực tiếp tên functional interface thường rõ ràng hơn phép ép kiểu chỉ để làm cho **var** suy luận được.

### Gắn method reference vào một generic API

~~~java
import java.util.List;

List<String> names = List.of("Lan", "Minh");

names.stream()
        .map(String::length)
        .forEach(System.out::println);
~~~

**Stream.map(...)** nhận **Function<? super T, ? extends R>**. Khi nguồn là **Stream<String>**, Java suy luận rằng **String::length** dùng receiver String và cho ra giá trị Integer sau boxing khi cần.

**forEach(System.out::println)** cũng được kiểm tra theo target type **Consumer<? super R>**. Mỗi biểu thức tham chiếu được giải nghĩa trong ngữ cảnh chức năng cụ thể của nó.

## 11. Overloading và khả năng nhập nhằng

Khi tên method có nhiều overload, Java cần xác định phiên bản nào tương thích với target type. Ví dụ **System.out.println(...)** có nhiều overload, nhưng:

~~~java
java.util.function.Consumer<String> printer = System.out::println;

printer.accept("Hello");
~~~

Target type **Consumer<String>** giúp xác định overload phù hợp cho tham số String.

### Chọn target type cụ thể

~~~java
import java.util.function.Function;

Function<String, Integer> length = String::length;
Function<String, String> cleaned = String::strip;
~~~

Mỗi biến mô tả rõ kiểu đầu vào và kết quả, giảm khả năng diễn giải sai.

Nếu một phương thức API có nhiều overload nhận những functional interface khác nhau, một method reference có thể khớp với nhiều overload và khiến lời gọi nhập nhằng. Khi đó nên dùng biến trung gian có kiểu rõ ràng hoặc một lambda tường minh.

Ví dụ nguyên tắc:

~~~java
// Khi lời gọi API bị nhập nhằng giữa các functional interface:
// 1. Khai báo biến trung gian với functional interface mong muốn.
// 2. Hoặc thêm kiểu tham số lambda để làm rõ mục đích.
~~~

Không nên dùng một phép ép kiểu phức tạp chỉ để lách lỗi mà chưa hiểu chữ ký được chọn; việc xác định đúng overload quan trọng hơn viết mã thật ngắn.

## 12. Generic method reference và suy luận tham số kiểu

Method reference có thể trỏ tới **generic method**. Java dùng target type để suy luận type argument của phương thức được tham chiếu.

Ví dụ, **Collections.emptyList()** là generic static method:

~~~java
import java.util.Collections;
import java.util.List;
import java.util.function.Supplier;

Supplier<List<String>> emptyStrings = Collections::emptyList;
Supplier<List<Integer>> emptyNumbers = Collections::emptyList;

System.out.println(emptyStrings.get().isEmpty()); // true
System.out.println(emptyNumbers.get().isEmpty()); // true
~~~

Không cần tự truyền type argument trong trường hợp này, vì **Supplier<List<String>>** hoặc **Supplier<List<Integer>>** cung cấp thông tin cần thiết.

### Generic constructor reference

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

Supplier<List<String>> strings = ArrayList::new;

List<String> result = strings.get();
result.add("Java");
~~~

Java suy luận kiểu tham số phù hợp của ArrayList dựa trên target type.

### Trường hợp cần viết lambda

Nếu chữ ký generic phức tạp, việc ghi lambda có tên tham số rõ ràng có thể giúp mã dễ hiểu hơn hoặc làm rõ sự suy luận kiểu:

~~~java
import java.util.function.Function;
import java.util.List;

Function<String, List<String>> wrap = value -> List.of(value);
~~~

Một method reference chỉ nên được chọn nếu ngữ nghĩa được ánh xạ chính xác vào functional interface. Không cần biến mọi lambda thành method reference.

## 13. Method reference và giá trị trả về void

Một functional interface như **Consumer<T>** có phương thức **void accept(T)**. Trong nhiều trường hợp, method reference vẫn có thể tham chiếu tới một method trả giá trị mà lời gọi có thể được dùng như một statement expression; kết quả trả về không được sử dụng.

Ví dụ:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

List<String> values = new ArrayList<>();

Consumer<String> addValue = values::add;

addValue.accept("Java");
addValue.accept("27");

System.out.println(values); // [Java, 27]
~~~

**List.add(E)** trả **boolean**, còn **Consumer.accept(E)** trả **void**. Trong ngữ cảnh này, kết quả boolean được bỏ qua.

Điều này không làm cho mọi method trả giá trị tự động tương thích với mọi functional interface: số lượng/kiểu tham số và quy tắc tương thích của biểu thức vẫn phải được đáp ứng.

Nếu muốn sử dụng giá trị trả về của **add(E)**, có thể chọn một target type phù hợp, ví dụ **Predicate<String>**:

~~~java
java.util.function.Predicate<String> append = values::add;

System.out.println(append.test("extra")); // true
~~~

Với List thông thường, **add(E)** trả true khi thao tác làm thay đổi danh sách theo hợp đồng của nó.

## 14. Thời điểm đánh giá receiver: method reference khác lambda

Đây là khác biệt quan trọng khi một biểu thức bên trái **::** có tác dụng phụ hoặc có khả năng là null.

### Bound receiver được đánh giá khi tạo reference

~~~java
import java.util.function.Supplier;

class ValueHolder {
    private final String text;

    ValueHolder(String text) {
        this.text = text;
    }

    String read() {
        return text;
    }
}

ValueHolder holder = new ValueHolder("ready");
Supplier<String> reader = holder::read;

System.out.println(reader.get()); // ready
~~~

Khi tạo **holder::read**, biểu thức receiver **holder** được đánh giá ngay. Phương thức **read()** vẫn chỉ chạy khi gọi **reader.get()**.

### Receiver null: khác thời điểm ném lỗi

~~~java
ValueHolder holder = null;

// Supplier<String> direct = holder::read;
// Ném NullPointerException ngay khi đánh giá method reference.

Supplier<String> deferred = () -> holder.read();

// deferred.get();
// Ném NullPointerException khi gọi functional method.
~~~

Trong ví dụ này, biến **holder** không bị gán lại nên có thể được lambda capture. Khi receiver của một **bound method reference** là null, lỗi xảy ra trong quá trình tạo reference. Với lambda **() -> holder.read()**, biểu thức truy cập method nằm trong phần thân lambda và chỉ được đánh giá khi functional method được gọi.

Điều này có thể quan trọng khi đăng ký callback, nơi callback chưa được thực thi ngay.

### Biểu thức receiver có side effect

~~~java
import java.util.function.Supplier;

class Service {
    String message() {
        return "hello";
    }
}

class Factory {
    static Service choose() {
        System.out.println("choose()");
        return new Service();
    }

    static void demo() {
        Supplier<String> bound = choose()::message;

        System.out.println(bound.get());
        System.out.println(bound.get());
    }
}
~~~

Khi gọi **demo()**, **choose()** được thực thi **một lần** lúc tạo **bound**, sau đó **message()** được gọi hai lần trên cùng receiver.

So sánh:

~~~java
Supplier<String> deferred = () -> Factory.choose().message();

System.out.println(deferred.get());
System.out.println(deferred.get());
~~~

Trong trường hợp lambda, **Factory.choose()** được gọi **mỗi lần** thực thi **get()**. Hai cách viết không hoàn toàn tương đương về thời điểm đánh giá và số lần xuất hiện side effect.

**Quy tắc thực hành:** method reference làm mã ngắn nhưng vẫn phải xét đến receiver và tác dụng phụ. Không thay lambda bằng method reference chỉ vì chúng trông giống nhau.

## 15. Method reference không tự gọi method và không cache kết quả

Một method reference là một cách cung cấp hành vi phù hợp functional interface. Nó không yêu cầu Java thực thi method ngay lập tức hoặc tự động ghi nhớ giá trị trả về của method sau lần gọi đầu.

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

AtomicInteger counter = new AtomicInteger();

Supplier<Integer> nextNumber = counter::incrementAndGet;

System.out.println(nextNumber.get()); // 1
System.out.println(nextNumber.get()); // 2
~~~

**counter::incrementAndGet** được tạo một lần, nhưng mỗi **get()** vẫn gọi method, tăng counter và trả về giá trị mới.

Không nên dùng toán tử **==** giữa hai instance functional interface để suy ra rằng các method reference được chia sẻ hoặc cache. Danh tính đối tượng biểu diễn lambda/method reference là chi tiết không cần thiết cho hợp đồng ứng dụng; hãy so sánh kết quả và hành vi mà API hứa hẹn.

## 16. Exception và tương thích functional interface

Một method reference phải tương thích với chữ ký của functional interface, kể cả các ràng buộc về **checked exception**.

Ví dụ, **Files.readString(Path)** có thể ném **IOException**. Vì **Function<Path, String>.apply(Path)** không khai báo checked exception này, không thể gán trực tiếp:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.function.Function;

// Function<Path, String> reader = Files::readString;
// Không hợp lệ vì checked IOException không được khai báo bởi Function.apply.
~~~

Nếu API thực sự cần một thao tác có checked exception, hãy định nghĩa functional interface tương ứng:

~~~java
import java.io.IOException;
import java.nio.file.Path;

@FunctionalInterface
interface TextReader {
    String read(Path path) throws IOException;
}
~~~

Có thể tham chiếu method:

~~~java
TextReader reader = java.nio.file.Files::readString;
~~~

Khi gọi **reader.read(path)**, mã gọi phải xử lý hoặc khai báo **IOException**.

Nếu phải thích ứng sang một API chỉ nhận **Function<Path, String>**, cần quyết định cách chuyển checked exception một cách có chủ đích (chẳng hạn xử lý tại ranh giới hoặc chuyển thành exception không kiểm tra có ngữ nghĩa phù hợp). Không dùng method reference để che việc xử lý lỗi.

## 17. Dùng method reference trong Stream và collection

Method reference thường xuất hiện trong Stream pipeline, nhưng nó không chỉ dành riêng cho Stream.

### map: biến đổi phần tử

~~~java
import java.util.List;

List<String> names = List.of("  Lan  ", " Minh ", "An");

List<String> cleaned = names.stream()
        .map(String::strip)
        .toList();

System.out.println(cleaned); // [Lan, Minh, An]
~~~

**String::strip** nhận một String làm receiver và trả String đã loại bỏ khoảng trắng theo hợp đồng method. **Stream.toList()** tạo danh sách không sửa được theo hợp đồng của API.

### filter: giữ phần tử theo điều kiện

~~~java
List<String> values = List.of("Java", "", "API");

List<String> nonBlank = values.stream()
        .filter(java.util.function.Predicate.not(String::isBlank))
        .toList();

System.out.println(nonBlank); // [Java, API]
~~~

**String::isBlank** phù hợp **Predicate<String>**, còn **Predicate.not(...)** đảo điều kiện.

### forEach: xử lý từng phần tử

~~~java
List<String> values = List.of("A", "B", "C");

values.forEach(System.out::println);
~~~

**System.out::println** phù hợp **Consumer<String>**. Trong mã sản xuất, tránh giả định thứ tự thực thi hoặc thời điểm side effect không được bảo đảm khi chuyển sang xử lý Stream song song; chọn API phù hợp với yêu cầu thứ tự.

### sorted: phương thức comparator và accessor

~~~java
import java.util.Comparator;
import java.util.List;

record Product(String name, int price) {}

List<Product> products = List.of(
        new Product("Book", 300),
        new Product("Pen", 50),
        new Product("Notebook", 120)
);

List<Product> byPrice = products.stream()
        .sorted(Comparator.comparingInt(Product::price))
        .toList();

byPrice.forEach(product ->
        System.out.println(product.name() + ": " + product.price()));
~~~

Kết quả:

~~~text
Pen: 50
Notebook: 120
Book: 300
~~~

**Product::price** là unbound instance method reference tới accessor của record. **Comparator.comparingInt(...)** yêu cầu **ToIntFunction<Product>**, vì vậy Java truyền mỗi Product làm receiver và lấy int từ **price()** mà không cần boxing giá trị int của key trong comparator.

### Method reference bên ngoài Stream

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> values = new ArrayList<>(List.of(" java ", " api "));

values.replaceAll(String::strip);

System.out.println(values); // [java, api]
~~~

**List.replaceAll(UnaryOperator<E>)** chấp nhận một hàm chuyển đổi từng phần tử trong danh sách có thể thay đổi. **String::strip** là lựa chọn ngắn gọn vì method đã thể hiện chính xác thao tác.

## 18. Khi nào lambda dễ hiểu hơn method reference?

Method reference tốt khi lời gọi lambda **chỉ chuyển tiếp tham số** vào một method hoặc constructor phù hợp, không bổ sung ý nghĩa khác. Ví dụ:

~~~java
Function<String, Integer> size = String::length;
~~~

Tuy nhiên, lambda thường rõ hơn trong các trường hợp:

**Có xử lý thêm điều kiện:**

~~~java
java.util.function.Predicate<String> valid =
        text -> text != null && !text.isBlank();
~~~

Không có một method reference đơn lẻ tới **String::isBlank** có thể thay thế toàn bộ logic null-safe này.

**Có truyền một tham số cố định đặc biệt:**

~~~java
import java.util.Locale;
import java.util.function.Function;

Function<String, String> normalizeCase =
        text -> text.toLowerCase(Locale.ROOT);
~~~

**String::toLowerCase** không tự truyền **Locale.ROOT**; overload không tham số dùng locale mặc định theo hợp đồng của method. Lambda là cách rõ ràng để đưa tham số locale vào lời gọi.

**Cần diễn đạt nhiều bước và xử lý lỗi:**

~~~java
Function<String, Integer> parsePositive = text -> {
    int number = Integer.parseInt(text.strip());

    if (number <= 0) {
        throw new IllegalArgumentException("Number must be positive");
    }

    return number;
};
~~~

Việc cố thay một logic nhiều bước bằng chuỗi method reference thường không thể thực hiện trực tiếp và có thể làm API khó đọc.

**Method reference gây nhập nhằng:** nếu có nhiều overload cùng phù hợp, lambda có tham số kiểu tường minh hoặc một biến trung gian có thể giúp lập trình viên và trình biên dịch xác định đúng mục đích.

Nguyên tắc: **ưu tiên cách viết diễn đạt đúng ý nghĩa với ít thao tác tinh thần nhất**, không theo số ký tự ngắn nhất.

## 19. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| **var f = String::length** không biên dịch | Thiếu target type là functional interface | Khai báo **Function<String, Integer>** hoặc **ToIntFunction<String>** |
| Gán **String::length** cho **Supplier<Integer>** bị lỗi | Unbound reference cần receiver từ tham số | Dùng **Function<String, Integer>** hoặc **word::length** với Supplier |
| Reference đến overloaded method nhập nhằng | Target type không đủ thông tin hoặc API đích có nhiều overload phù hợp | Chỉ định functional interface rõ ràng, dùng lambda khi cần |
| Bound reference ném **NullPointerException** ngay | Biểu thức receiver là null khi tạo reference | Kiểm tra receiver trước; dùng lambda nếu chủ đích muốn trì hoãn thao tác |
| Dùng **Type::new** nhưng constructor không khớp | Số lượng/kiểu tham số không phù hợp với functional method | Chọn target type tương ứng hoặc viết constructor phù hợp |
| Mong **ClassName::new** tạo object ngay | Constructor reference chỉ cung cấp hành vi tạo đối tượng | Gọi **get()**, **apply()** hoặc functional method tương ứng |
| Dùng **Function<Path, String>** cho **Files::readString** | Checked exception không tương thích | Dùng interface có **throws IOException** hoặc adapter xử lý lỗi |
| Dùng **String[]::new** ở nơi đòi Supplier<String[]> | Constructor mảng cần độ dài từ tham số int | Dùng **IntFunction<String[]>** |
| Cố dùng **new List<String>[...]** | Generic array với phần tử non-reifiable bị cấm | Dùng **List<List<String>>** hoặc giải pháp kiểu phù hợp |
| Dùng method reference làm ẩn biến đổi nghiệp vụ | Method được tham chiếu không thực hiện đủ các bước | Dùng lambda với logic rõ ràng |
| Giả định reference gọi method chỉ một lần | Method reference không tự memoize kết quả | Phân biệt số lần tạo reference và số lần gọi functional method |
| Dùng **String::toLowerCase** khi yêu cầu locale trung tính | Không truyền rõ Locale | Dùng lambda **s -> s.toLowerCase(Locale.ROOT)** |
| Dùng callback với collection thay đổi nhưng không xét đồng thời | Reference không làm đối tượng bên ngoài thread-safe | Thiết kế đồng bộ và side effect theo hợp đồng thực tế |

## 20. Ví dụ tổng hợp: xử lý đơn hàng với method và constructor reference

Ví dụ sau có thể lưu thành tệp **ReferenceDemo.java**. Nó kết hợp:

- **Constructor reference** để tạo record từ dữ liệu đầu vào.
- **Static method reference** để chuyển chuỗi thành số.
- **Unbound instance method reference** để lấy thuộc tính record và xử lý String.
- **Bound instance method reference** cho callback in kết quả.
- **Array constructor reference** để chuyển Stream thành mảng.
- **Comparator.comparingInt(...)** với primitive accessor.
- Logic có tham số cố định được giữ dưới dạng lambda khi method reference không diễn đạt trực tiếp.

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.function.BiFunction;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.IntFunction;
import java.util.function.ToIntFunction;

public class ReferenceDemo {
    record OrderLine(String sku, int quantity) {}

    public static void main(String[] args) {
        // Constructor reference: tạo một OrderLine từ hai đối số.
        BiFunction<String, Integer, OrderLine> newLine = OrderLine::new;

        // Static method reference: parse số lượng từ String.
        Function<String, Integer> parseQuantity = Integer::parseInt;

        // Unbound instance method reference: làm sạch chuỗi.
        Function<String, String> strip = String::strip;

        List<OrderLine> lines = List.of(
                newLine.apply(strip.apply("  BOOK-01  "),
                        parseQuantity.apply("3")),
                newLine.apply(strip.apply(" PEN-02 "),
                        parseQuantity.apply("5")),
                newLine.apply(strip.apply(" NOTE-03 "),
                        parseQuantity.apply("2"))
        );

        // Record accessor dưới dạng unbound method reference.
        ToIntFunction<OrderLine> quantity = OrderLine::quantity;

        int totalItems = lines.stream()
                .mapToInt(quantity)
                .sum();

        // Sort theo số lượng, giữ danh sách ban đầu không đổi.
        List<OrderLine> sorted = lines.stream()
                .sorted(Comparator.comparingInt(OrderLine::quantity))
                .toList();

        // Bound instance method reference: dùng callback in ra console.
        Consumer<OrderLine> printLine = System.out::println;
        sorted.forEach(printLine);

        // Array constructor reference.
        IntFunction<OrderLine[]> arrayFactory = OrderLine[]::new;
        OrderLine[] array = sorted.stream().toArray(arrayFactory);

        // Lambda phù hợp khi cần tham số Locale cố định.
        Function<String, String> uppercase =
                text -> text.toUpperCase(Locale.ROOT);

        List<String> normalizedSkus = Arrays.stream(array)
                .map(OrderLine::sku)
                .map(uppercase)
                .toList();

        System.out.println("Total items: " + totalItems);
        System.out.println("Array size: " + array.length);
        System.out.println(normalizedSkus);
    }
}
~~~

Kết quả:

~~~text
OrderLine[sku=NOTE-03, quantity=2]
OrderLine[sku=BOOK-01, quantity=3]
OrderLine[sku=PEN-02, quantity=5]
Total items: 10
Array size: 3
[NOTE-03, BOOK-01, PEN-02]
~~~

Diễn giải:

1. **OrderLine::new** được ánh xạ tới canonical constructor **OrderLine(String, int)**. Số lượng kiểu **Integer** từ **BiFunction** được unbox thành **int** khi cần.
2. **Integer::parseInt** là static reference, trả số nguyên từ nội dung chuỗi; nếu nội dung không hợp lệ, nó có thể ném **NumberFormatException**.
3. **String::strip** là unbound reference: chuỗi đầu vào trở thành receiver của method **strip()**.
4. **OrderLine::quantity** được dùng với **ToIntFunction<OrderLine>**, trả int và tránh boxing cho việc tính tổng và so sánh khóa.
5. **System.out::println** là bound reference của đối tượng **PrintStream** hiện có. Giá trị **OrderLine** được in thông qua overload phù hợp.
6. **OrderLine[]::new** nhận kích thước mảng do Stream cung cấp và tạo mảng đúng kiểu.
7. Phần chuyển tên sang chữ hoa dùng lambda để truyền **Locale.ROOT**, vì không có một reference đơn giản biểu đạt cùng lúc việc nhận String đầu vào và ràng buộc đối số locale.

Đây là một ví dụ xử lý dữ liệu trong bộ nhớ, không bao gồm lưu trữ, I/O ngoài console hoặc giao dịch. Khi thiết kế phần mềm thực tế, hãy kiểm tra dữ liệu đầu vào, ranh giới lỗi và tính bất biến theo yêu cầu nghiệp vụ.

## 21. Checklist trước khi dùng ::

- Nơi sử dụng có **functional interface** rõ ràng không?
- Phương thức được tham chiếu có đúng **số lượng, kiểu tham số và kiểu trả về** tương thích với functional method không?
- Đây là **static method**, **bound instance method** hay **unbound instance method**?
- Với **ReferenceType::instanceMethod**, đối số đầu tiên có thực sự là receiver không?
- Với **expression::method**, receiver có thể null không, và có tác dụng phụ khi đánh giá không?
- Constructor reference có được chọn bởi đúng chữ ký của **Supplier**, **Function** hoặc **BiFunction** không?
- Khi tạo mảng, đã dùng **ElementType[]::new** với **IntFunction<ElementType[]>** phù hợp chưa?
- Phương thức có overload nào khiến lời gọi khó hiểu hoặc nhập nhằng không?
- Checked exception có được khai báo hoặc xử lý bởi hợp đồng của functional interface không?
- Nếu cần biến đổi thêm, điều kiện, locale hoặc xử lý lỗi, lambda có diễn đạt rõ hơn không?
- Có đang lầm tưởng method reference sẽ gọi method ngay, cache kết quả hoặc làm đối tượng bên ngoài an toàn khi dùng đồng thời không?
- Ví dụ và API có dùng những tính năng Java hiện hành, tránh phụ thuộc hành vi triển khai không được bảo đảm không?

## Kết luận

**Method reference** cho phép dùng một phương thức đã tồn tại làm cách triển khai functional interface, thông qua **TypeName::staticMethod**, **expression::instanceMethod**, **ReferenceType::instanceMethod** hoặc **super::method** ở ngữ cảnh hợp lệ. **Constructor reference** dùng **ClassName::new** để cung cấp cách tạo đối tượng; **array constructor reference** dùng **ElementType[]::new** để cung cấp cách tạo mảng có độ dài do người gọi chỉ định.

Để dự đoán chính xác hành vi trong Java 27, luôn xem xét **target type**, cách ánh xạ receiver và tham số, quy tắc chọn overload, thời điểm đánh giá bound receiver và ràng buộc ngoại lệ. Method reference là lựa chọn tốt khi nó trực tiếp thể hiện một lời gọi sẵn có; nếu cần kết hợp nhiều bước hoặc làm rõ quy tắc nghiệp vụ, **lambda vẫn là lựa chọn thích hợp**.
