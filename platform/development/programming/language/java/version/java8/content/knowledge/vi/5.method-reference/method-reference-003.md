# Tham chiếu phương thức instance đã gắn đối tượng (bound instance method reference)

## 1. Mục tiêu và phạm vi

Trong Java, biểu thức **`object::instanceMethod`** tham chiếu một phương thức instance trên **một đối tượng nhận (*receiver*) đã xác định**. Đây là dạng *bound instance method reference*, được Java 8 giới thiệu và vẫn là cú pháp chuẩn trên các JDK được duy trì hiện nay. Nó hữu ích khi muốn chuyển một phương thức có sẵn thành callback ngắn gọn mà không viết lambda chỉ để gọi lại phương thức đó.

Sau bài học, bạn cần có khả năng:

- Phân biệt `object::method` với `Type::instanceMethod`, `Type::staticMethod` và `Type::new`.
- Chọn đúng target functional interface và đếm đúng số tham số: receiver **đã được cố định**, nên không xuất hiện trong tham số của hàm đích.
- Giải thích chính xác **thời điểm đánh giá receiver**, thời điểm gọi phương thức, khác biệt với lambda và lúc xảy ra `NullPointerException`.
- Hiểu object identity: method reference giữ đối tượng nhận đã chọn, trong khi **trạng thái có thể thay đổi** trên cùng đối tượng vẫn được quan sát lúc gọi.
- Áp dụng vào `Supplier`, `Function`, `Consumer`, `Predicate` và callback thực tế; biết giới hạn về exceptions, overload, side effect và đồng thời.
- Biên dịch, chạy chương trình độc lập và giải thích stdout theo từng dòng.

Ví dụ dùng cú pháp và API đã có từ Java 8 nhưng được thực hành trên **JDK hiện đại còn nhận cập nhật**, theo chính sách của dự án. Khi cần kiểm tra tương thích nguồn và API Java 8, dùng `javac --release 8` nếu compiler đang dùng hỗ trợ tùy chọn này. Không cần cài một JDK cũ chỉ để học method reference.

## 2. Định nghĩa và sơ đồ ánh xạ

Ví dụ một đối tượng hiện có:

~~~java
String prefix = "ID-";
java.util.function.Function<String, String> format = prefix::concat;
System.out.println(format.apply("42"));  // ID-42
~~~

Ở đây:

1. `prefix` là **receiver**, một `String` cụ thể chứa `"ID-"`.
2. `concat(String suffix)` là **phương thức instance** được tham chiếu.
3. Target type `Function<String,String>` có phương thức trừu tượng `String apply(String input)`.
4. Khi gọi `format.apply("42")`, chương trình gọi tương đương `prefix.concat("42")` trên **receiver đã được gắn**.

Sơ đồ:

~~~text
Tạo tham chiếu:       prefix::concat
                          |
                          v
               lưu receiver = "ID-"
                          |
                 Function<String,String>
                          |
       format.apply("42") -> receiver.concat("42")
                          |
                          v
                        "ID-42"
~~~

**Quan trọng:** Tạo method reference không có nghĩa phương thức `concat` đã được gọi. Việc **đánh giá biểu thức receiver** xảy ra ngay khi gặp `::`; việc **thực thi phương thức được tham chiếu** xảy ra sau, khi functional method (`apply`, `get`, `accept`,...) được gọi.

Method reference phải xuất hiện trong **ngữ cảnh có target type** là functional interface, hoặc ở nơi compiler có thể suy ra target type qua đối số phương thức, phép gán hay cast. `object::method` không tự chứa một kiểu hàm chung để có thể gán cho `Object` mà không có ngữ cảnh.

## 3. Phân biệt bốn dạng method reference

| Dạng | Ví dụ | Receiver được lấy ở đâu? | Một target type điển hình |
| --- | --- | --- | --- |
| Instance đã gắn đối tượng | `prefix::concat` | `prefix` được đánh giá khi tạo reference | `Function<String,String>` |
| Instance chưa gắn đối tượng (*unbound*) | `String::concat` | Đối số đầu tiên của functional method | `BiFunction<String,String,String>` |
| Static method | `Integer::parseInt` | Không có receiver instance | `Function<String,Integer>` |
| Constructor | `StringBuilder::new` | Tạo đối tượng mới khi gọi | `Supplier<StringBuilder>` |

Ví dụ cùng phép nối chuỗi:

~~~java
import java.util.function.BiFunction;
import java.util.function.Function;

String prefix = "ID-";

// Bound: receiver đã cố định, apply chỉ cần một đối số.
Function<String, String> bound = prefix::concat;

// Unbound: apply cần receiver và phần được nối.
BiFunction<String, String, String> unbound = String::concat;

System.out.println(bound.apply("7"));          // ID-7
System.out.println(unbound.apply("ID-", "7"));  // ID-7
~~~

`String::concat` không có receiver cố định nên `BiFunction.apply(first, second)` lấy `first` làm receiver và `second` làm đối số của `concat`. Trong khi đó `prefix::concat` đã gắn receiver, chỉ cần đối số còn lại. **Đừng chuyển nguyên xi hai dạng rồi giữ nguyên functional interface**; arity và ý nghĩa tham số sẽ sai.

Một method reference bound cũng có thể nhắm tới phương thức **không nhận đối số**:

~~~java
import java.util.function.Supplier;
String message = "  Java  ";
Supplier<String> clean = message::trim;
System.out.println("[" + clean.get() + "]"); // [Java]
~~~

Vì `trim()` không có tham số nên target `Supplier<String>` cũng không nhận tham số. Đây là kỹ thuật gọn khi UI/callback cần một hành vi đọc giá trị trên đối tượng hiện có.

## 4. Quy tắc then chốt: receiver được đánh giá ngay và đúng một lần

Xét hai cách viết tưởng như tương đương:

~~~java
// Giả sử registry.current() trả về một đối tượng có method format(int).
java.util.function.IntFunction<String> bound =
    registry.current()::format;

java.util.function.IntFunction<String> lambda =
    number -> registry.current().format(number);
~~~

**Bound reference:** `registry.current()` được chạy **ngay tại biểu thức tạo reference**, kết quả được giữ làm receiver. Khi gọi `bound.apply(n)` nhiều lần, **không gọi lại `registry.current()`** chỉ để lấy receiver.

**Lambda:** thân `number -> ...` chưa chạy lúc tạo lambda. Mỗi lần gọi `lambda.apply(n)` sẽ đánh giá `registry.current()` lại trong thân lambda. Nếu registry đã trỏ sang đối tượng khác, lambda có thể sử dụng đối tượng mới.

Sự khác biệt có thể quan sát được nếu `registry.current()` ghi log, đếm số lần truy vấn, đọc configuration hiện hành hoặc thay đổi giá trị trả về. Trong code production, chỉ dùng bound reference nếu **cố định receiver tại thời điểm đăng ký callback** đúng với yêu cầu nghiệp vụ.

### Đừng nhầm "cố định đối tượng" với "đóng băng dữ liệu"

Nếu receiver là một object mutable, `receiver::method` lưu **tham chiếu tới object**, không sao chép mọi field của nó. Khi field thay đổi trên **chính object ấy**, lời gọi method reference sau này nhìn thấy trạng thái mới theo các quy tắc Java Memory Model và bảo đảm đồng bộ thực tế.

Ngược lại, nếu biến `receiver` hoặc registry được gán để trỏ sang **một object khác**, bound reference vẫn gắn với object cũ. Đây là mô hình "giữ danh tính, đọc state khi gọi", không phải snapshot bất biến.

### Lambda nào gần giống bound reference hơn?

~~~java
// Trong một method:
Formatter saved = registry.current();
java.util.function.IntFunction<String> callback =
    number -> saved.format(number);
~~~

Cách này cũng gọi `registry.current()` một lần và capture tham chiếu `saved` (phải final/effectively final). Nó gần tương đương về **đối tượng nhận** với `registry.current()::format` khi receiver không null, nhưng **vẫn khác về thời điểm lỗi null**: `saved.format(number)` nằm trong thân lambda, còn bound reference kiểm tra receiver lúc tạo.

## 5. Null receiver: thời điểm phát sinh ngoại lệ khác nhau

Đây là quy tắc đặc biệt dễ gây lỗi khi đổi lambda sang method reference:

~~~java
import java.util.function.Supplier;

String absent = null;

// Bound reference: NPE NGAY khi đánh giá biểu thức.
// Supplier<String> wrong = absent::trim;

// Lambda: tạo được vì thân chưa chạy.
Supplier<String> later = () -> absent.trim();

// later.get() mới ném NullPointerException.
~~~

Nếu biểu thức nằm bên trái `::` là một expression name hoặc primary cho method reference bound và giá trị đánh giá là `null`, Java ném `NullPointerException` **ngay khi tạo method reference**. Lambda tương ứng có thể chỉ ném khi callback được gọi.

Điều đó quan trọng trong quá trình đăng ký handler, cấu hình công việc định kỳ hoặc truyền callback: đổi `() -> service.send()` thành `service::send` có thể đẩy lỗi `null` từ **lúc thực hiện tác vụ** sang **lúc đăng ký tác vụ**. Thời điểm thất bại và nơi bắt lỗi có thể thay đổi.

Nếu receiver có thể vắng mặt, hãy xử lý có chủ đích:

~~~java
import java.util.Objects;
import java.util.function.Supplier;

// Với một String name có thể null:
String nonNull = Objects.requireNonNull(name, "name");
Supplier<String> supplier = nonNull::trim;
~~~

Ví dụ trên là **trích đoạn trong method** và yêu cầu biến `name` đã tồn tại. `Objects.requireNonNull` diễn đạt rõ ràng điều kiện bắt buộc. Nếu vắng mặt là trạng thái nghiệp vụ hợp lệ, thiết kế callback có kết quả vắng mặt hoặc giá trị fallback được quy định thay vì che lỗi tự động.

## 6. Ví dụ chạy độc lập trên JDK được duy trì

Tạo file **`BoundMethodReferenceDemo.java`** với encoding UTF-8:

~~~java
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.IntFunction;
import java.util.function.Supplier;

public class BoundMethodReferenceDemo {
    static final class Formatter {
        String prefix;
        int calls;

        Formatter(String prefix) {
            this.prefix = prefix;
        }

        String format(int value) {
            calls++;
            return prefix + value;
        }
    }

    static final class Registry {
        Formatter current;
        int lookups;

        Registry(Formatter initial) {
            this.current = initial;
        }

        Formatter active() {
            lookups++;
            return current;
        }
    }

    public static void main(String[] args) {
        Formatter first = new Formatter("A=");
        Formatter second = new Formatter("B=");
        Registry registry = new Registry(first);

        // active() được gọi ngay một lần.
        IntFunction<String> bound = registry.active()::format;

        // active() chỉ chạy khi lambda được gọi.
        IntFunction<String> deferred =
            value -> registry.active().format(value);

        System.out.println("lookups after bind: " + registry.lookups);

        registry.current = second;
        System.out.println("bound 7: " + bound.apply(7));
        System.out.println("lambda 7: " + deferred.apply(7));
        System.out.println("lookups after calls: " + registry.lookups);

        // Bound vẫn chọn first, nhưng nhìn thấy state mới trên first.
        first.prefix = "A*=";
        System.out.println("bound after state: " + bound.apply(9));
        System.out.println("calls first/second: "
            + first.calls + "/" + second.calls);

        String sample = "  Java  ";
        Supplier<String> fixedTrim = sample::trim;
        Function<String, String> anyTrim = String::trim;

        System.out.println("fixed trim: [" + fixedTrim.get() + "]");
        System.out.println("any trim: [" + anyTrim.apply("  World ") + "]");

        StringBuilder builder = new StringBuilder("log");
        Consumer<String> append = builder::append;
        append.accept("+ok");
        System.out.println("builder: " + builder);

        Formatter missing = null;
        try {
            // Lỗi xuất hiện trước khi callback có cơ hội được gọi.
            IntFunction<String> impossible = missing::format;
            System.out.println(impossible.apply(1));
        } catch (NullPointerException expected) {
            System.out.println("bound null: creation");
        }

        IntFunction<String> lateFailure = value -> missing.format(value);
        System.out.println("lambda created: yes");
        try {
            lateFailure.apply(1);
        } catch (NullPointerException expected) {
            System.out.println("lambda null: invocation");
        }
    }
}
~~~

**Biên dịch và chạy** trong thư mục chứa file, trên JDK hiện đại có hỗ trợ target 8:

~~~text
javac --release 8 -encoding UTF-8 BoundMethodReferenceDemo.java
java BoundMethodReferenceDemo
~~~

Nếu dự án chỉ nhắm tới bản JDK runtime đang triển khai, dùng toolchain và `--release` đúng theo hợp đồng dự án, không buộc mọi ứng dụng mới phải xuất bytecode Java 8.

**Stdout kỳ vọng, đúng 12 dòng:**

~~~text
lookups after bind: 1
bound 7: A=7
lambda 7: B=7
lookups after calls: 2
bound after state: A*=9
calls first/second: 2/1
fixed trim: [Java]
any trim: [World]
builder: log+ok
bound null: creation
lambda created: yes
lambda null: invocation
~~~

### Giải thích kết quả

1. `registry.active()::format` gọi `active()` ngay: `lookups=1` và receiver cố định là `first`. Bản thân `format` chưa được gọi.
2. Thay `registry.current` bằng `second` không đổi receiver của `bound`: `bound.apply(7)` vẫn gọi `first.format(7)` và in `A=7`.
3. `deferred.apply(7)` thực thi thân lambda, gọi `registry.active()` lần nữa, nhận `second` và in `B=7`; `lookups=2`.
4. Khi sửa `first.prefix` thành `"A*="`, bound reference vẫn dùng `first` nhưng method đọc field mới nên trả `A*=9`. `first.format` đã chạy hai lần, `second.format` một lần.
5. `sample::trim` cố định receiver chứa `"  Java  "`; `String::trim` chưa gắn receiver và nhận chuỗi qua `Function.apply`. Cả hai bỏ khoảng trắng đầu/cuối.
6. `builder::append` phù hợp `Consumer<String>`: mặc dù `StringBuilder.append(String)` trả `StringBuilder`, target `Consumer.accept` trả `void` nên giá trị trả về không được dùng; việc thêm chuỗi vẫn diễn ra trên **cùng builder**.
7. `missing::format` ném `NullPointerException` khi tạo method reference. `value -> missing.format(value)` được tạo thành công; NPE chỉ xuất hiện khi gọi `apply`.

Ví dụ minh họa rõ **lúc gắn receiver**, **lúc chạy method**, **object identity** và **hành vi khi null**; không cần đoán bằng cách kiểm tra bytecode do compiler sinh ra.

## 7. Chọn đúng functional interface cho bound method

Phương thức instance và target interface phải tương thích về **số tham số còn lại**, kiểu tham số, kiểu trả về và checked exceptions. Với bound reference, **không đưa receiver vào danh sách tham số target** vì receiver đã được gắn.

| Method của receiver | Bound reference | Target phù hợp | Cách gọi |
| --- | --- | --- | --- |
| `String trim()` | `text::trim` | `Supplier<String>` | `get()` |
| `String concat(String value)` | `prefix::concat` | `Function<String,String>` | `apply(value)` |
| `boolean startsWith(String prefix)` | `text::startsWith` | `Predicate<String>` | `test(prefix)` |
| `String format(int value)` | `formatter::format` | `IntFunction<String>` | `apply(int)` |
| `void log(String message)` | `logger::log` | `Consumer<String>` | `accept(message)` |
| `int compare(String a,String b)` | `comparator::compare` | `Comparator<String>` | `compare(a,b)` |

`logger` trong bảng đại diện object do ứng dụng định nghĩa có `log(String)`; không mặc định là API của một thư viện cụ thể. `comparator::compare` có hai tham số dù receiver đã gắn, vì method `compare(a,b)` thật sự nhận hai đối số.

### Method trả giá trị có thể thích nghi với callback void

`Consumer<String> append = builder::append;` trong mục 6 hợp lệ mặc dù `append` trả object. Đây là **void-compatible method reference**: giá trị trả về bị bỏ qua khi target SAM trả `void`. Chiều ngược lại không tương đương: một method `void print(String)` không thể gán cho `Function<String,String>` vì `apply` bắt buộc trả `String`.

### Một số lỗi kiểu thường gặp

~~~java
String prefix = "ID-";

// ĐÚNG: receiver đã gắn, một input String.
java.util.function.Function<String, String> f = prefix::concat;

// SAI: BiFunction yêu cầu hai input, trong khi bound concat chỉ cần một.
// java.util.function.BiFunction<String, String, String> wrong = prefix::concat;

// ĐÚNG: dạng unbound cần receiver String như đối số đầu tiên.
java.util.function.BiFunction<String, String, String> g = String::concat;
~~~

Lỗi được đánh dấu `SAI` ở đây là **minh họa không biên dịch**, được comment để có thể đặt cạnh mã đúng.

## 8. Bound method reference không phải cú pháp curry tự động

Có thể dễ nhầm `object::method` với *partial application* chung cho mọi tham số. Thực tế, cú pháp này **chỉ cố định receiver instance**, không tự chọn trước một tham số bất kỳ của method.

Nếu có:

~~~java
class TicketService {
    boolean eligible(String ticketCode, int threshold) {
        return ticketCode.length() >= threshold;
    }
}
~~~

`service::eligible` vẫn yêu cầu **cả hai tham số của method**:

~~~java
// Trong một phương thức:
TicketService service = new TicketService();

java.util.function.BiPredicate<String, Integer> both =
    service::eligible;

// Cố định thêm threshold=5 thì cần lambda:
java.util.function.Predicate<String> minFive =
    code -> service.eligible(code, 5);
~~~

`service::eligible` gắn `service` nhưng **không gắn sẵn `threshold`**. Khi cần cố định bất kỳ tham số nghiệp vụ nào khác, lambda là cách diễn đạt trực tiếp và rõ ràng. Không cố tạo nhiều tầng method reference nếu làm code khó đọc.

## 9. Tích hợp trong ứng dụng hiện đại

### Callback của đối tượng dịch vụ

~~~java
import java.util.List;
import java.util.function.Consumer;

class NotificationSink {
    void emit(String message) {
        System.out.println("Sent: " + message);
    }
}

// Trong một phương thức:
NotificationSink sink = new NotificationSink();
Consumer<String> consumer = sink::emit;
List<String> messages = java.util.Arrays.asList("A", "B");
messages.forEach(consumer);
~~~

`sink::emit` bảo đảm các lần callback gọi trên cùng `sink`. Đây là trích đoạn cho việc đăng ký callback; ví dụ thật nên quy định rõ vòng đời của `sink`, các lỗi có thể phát sinh và liệu callback được chạy đồng thời hay không. Một callback bound có thể giữ object được tham chiếu **còn reachable**; tránh giữ lâu các resource lẽ ra phải được giải phóng.

### Bộ định dạng hoặc comparator đã cấu hình

Nếu đối tượng `formatter` hoặc `comparator` có cấu hình bất biến, tham chiếu `formatter::format` hoặc `comparator::compare` thể hiện rõ việc dùng một cấu hình đã chọn trước. Nếu cấu hình của receiver mutable và đang được chia sẻ giữa thread, bản thân method reference không cung cấp đồng bộ hay snapshot.

Với nhu cầu độ chính xác ngôn ngữ/locale, đừng dùng `String::toLowerCase` không có locale như một phép chuẩn hóa toàn cục để so sánh nghiệp vụ. Nếu thực sự cần xử lý locale, dùng API locale/collation có tham số rõ ràng và kiểm thử dữ liệu quốc tế; lựa chọn này là **ngoài phạm vi** cơ chế bound reference.

### Stream và đánh giá lười

~~~java
String prefix = "CODE-";
java.util.function.Function<String, String> addPrefix = prefix::concat;

java.util.List<String> result =
    java.util.Arrays.asList("1", "2").stream()
        .map(addPrefix)
        .collect(java.util.stream.Collectors.toList());
// result = ["CODE-1", "CODE-2"]
~~~

`prefix::concat` được đánh giá khi tạo `addPrefix`; phương thức `concat` được gọi khi pipeline của Stream được chạy bởi terminal operation `collect`. Đừng nhầm **đánh giá receiver** với việc Stream thực thi pipeline, đặc biệt khi receiver có side effect lúc được tìm qua một lời gọi method.

## 10. Overload, dynamic dispatch và ngoại lệ

### Overload được chọn dựa vào target type

Nếu receiver có nhiều method cùng tên:

~~~java
class Writer {
    void write(String value) {
        System.out.println(value);
    }

    void write(int value) {
        System.out.println(value);
    }
}
~~~

Compiler dùng target functional interface để tìm method phù hợp:

~~~java
// Trong một phương thức:
Writer writer = new Writer();
java.util.function.Consumer<String> stringWriter = writer::write;
java.util.function.IntConsumer intWriter = writer::write;
~~~

Hai reference cùng gắn receiver `writer` nhưng có chữ ký target khác nhau. Nếu overload gây mơ hồ, viết lambda có kiểu rõ ràng hoặc cast target khi hợp lý. Đừng đoán method được chọn chỉ từ tên sau dấu `::`.

### Receiver cố định không có nghĩa phương thức bị "đóng băng"

Bound method reference gắn **một object**. Nếu method là virtual và object thuộc subclass override method đó, quy tắc **dynamic dispatch** Java vẫn áp dụng. `object::method` không tự biến method thành static hay đóng băng nội dung triển khai. Nếu object có field mutable, phương thức vẫn đọc field theo các quy tắc thông thường.

### Checked exception phải khớp hợp đồng

~~~java
import java.io.IOException;
import java.util.function.Supplier;

class FileReaderService {
    String read() throws IOException {
        throw new IOException("I/O failed");
    }
}

// Trong một phương thức:
FileReaderService service = new FileReaderService();

// LỖI: Supplier.get() không khai báo throws IOException.
// Supplier<String> wrong = service::read;
~~~

Để giữ hợp đồng checked exception, định nghĩa một functional interface thích hợp:

~~~java
@FunctionalInterface
interface CheckedSupplier<T> {
    T get() throws java.io.IOException;
}

// Trong một phương thức:
FileReaderService service = new FileReaderService();
CheckedSupplier<String> allowed = service::read;
~~~

Khi gọi `allowed.get()`, caller phải catch `IOException` hoặc khai báo `throws IOException`. Không dùng "sneaky throw" hay nuốt lỗi chỉ để ép reference phù hợp `Supplier`; hãy chọn một adapter có xử lý lỗi rõ ràng nếu API thư viện buộc dùng `Supplier`.

## 11. Vòng đời, thread safety và độ tin cậy

1. **Receiver được giữ tham chiếu:** Callback `service::send` giữ object `service` làm receiver. Nếu callback tồn tại lâu hơn service, cần thiết kế vòng đời đăng ký/hủy để không giữ resource ngoài ý muốn.
2. **Không có đảm bảo thread-safe tự động:** Nhiều thread cùng gọi `builder::append` trên một `StringBuilder` là không an toàn nếu không quản lý truy cập. Method reference không thay thế đồng bộ hoặc cấu trúc thread-safe.
3. **Thời điểm lỗi null là một phần hành vi:** `nullableService::send` thất bại ngay tại chỗ tạo; lambda tương đương có thể thất bại lúc xử lý sau này. Điều này ảnh hưởng vị trí test và xử lý lỗi.
4. **Đừng dựa vào identity của chính callback:** Java không bảo đảm mỗi lần đánh giá method reference đều tạo một object mới, cũng không bảo đảm hai reference bằng nhau theo `==`. Nếu cần hủy listener bằng cùng reference, lưu biến callback đã đăng ký rồi dùng chính biến đó.
5. **Không tự động snapshot trạng thái:** Thay field trên receiver không đổi reference nhưng có thể đổi output. Muốn hành vi bất biến, thiết kế receiver immutable hoặc chụp dữ liệu một cách có chủ đích.
6. **Tránh side effect trong method dùng làm predicate/mapper:** Khi dùng trong Stream hoặc luồng xử lý song song, method side-effectful có thể khiến kết quả khó dự đoán. Đặt side effect ở đúng ranh giới và kiểm thử.
7. **Làm rõ ownership và khả năng hủy:** Callback gắn với UI component, connection, subscription hoặc task cần kế hoạch giải phóng và hủy theo API tương ứng; giữ method reference trong registry lâu dài có thể kéo dài vòng đời receiver.
8. **Đo hiệu năng trước khi tối ưu:** Chọn lambda/method reference theo semantics và khả năng đọc. Đừng giả định method reference luôn ít cấp phát hơn hoặc nhanh hơn lambda, vì JVM có quyền tối ưu hai dạng.

## 12. Lỗi thường gặp và cách sửa

| Tình huống | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Compiler báo functional target không hợp | Đếm sai đối số vì quên receiver đã gắn | Đọc chữ ký method và SAM; chọn `Function` hay `BiFunction` phù hợp |
| `NullPointerException` ngay khi đăng ký callback | Biểu thức bên trái `::` trả null | Kiểm tra/khởi tạo receiver trước; dùng chính sách null có chủ đích |
| Callback vẫn gọi service cũ | Bound reference giữ receiver đã chọn khi tạo | Dùng lambda tra cứu service lúc gọi nếu nghiệp vụ yêu cầu cập nhật |
| Callback nhìn thấy state mới khó hiểu | Object cũ vẫn mutable | Dùng receiver immutable hoặc đồng bộ state đúng cách |
| `incompatible thrown types` | Method ném checked exception không được SAM cho phép | Dùng target SAM khai báo `throws` hoặc adapter xử lý |
| Method overload không rõ | Target type không đủ phân biệt overload | Chỉ rõ kiểu tham số hoặc dùng lambda/cast minh bạch |
| Mất thứ tự/side effect khi dùng Stream | Hiểu nhầm receiver binding với lazy evaluation của pipeline | Tách thời điểm tạo reference khỏi thời điểm terminal operation chạy |
| Không gỡ được listener | Tạo lại một reference khác và giả định `==` cùng object | Giữ đúng instance callback dùng lúc đăng ký |
| Race condition trên mutable receiver | Nhiều callback cùng sửa receiver | Đồng bộ truy cập hoặc chọn thiết kế thread-safe |

## 13. Bài tập tự kiểm tra

**Bài 1 — Đếm lần gọi receiver:** Viết class `Registry` có `lookup()` tăng một biến đếm. Tạo `Function<String,String> f = registry.lookup()::format;` và `Function<String,String> g = s -> registry.lookup().format(s);`. Gọi mỗi callback ba lần. Dự đoán số lần `lookup`: **1** do bound, **3** do lambda (tổng **4**), nếu không có thao tác nào khác.

**Bài 2 — Đổi instance:** Tạo hai formatter lần lượt có prefix `"OLD-"` và `"NEW-"`; gắn `old::format` rồi đổi registry thành `new`. Dự đoán bound vẫn dùng formatter cũ, còn lambda gọi registry mỗi lần có thể dùng formatter mới.

**Bài 3 — Null timing:** Với `String absent = null`, so sánh `Supplier<String> a = absent::trim;` và `Supplier<String> b = () -> absent.trim();`. Xác định chính xác dòng nào gây lỗi tại lúc tạo callback và dòng nào gây lỗi lúc gọi `get()`.

**Bài 4 — Bound và unbound:** Viết `Function<String,String> bound = "P-"::concat;` và `BiFunction<String,String,String> unbound = String::concat;`. Kiểm tra `bound.apply("1")` và `unbound.apply("P-","1")` đều trả `"P-1"`; giải thích vì sao số đối số khác nhau.

**Bài 5 — Thay state receiver:** Viết một class có field `suffix` và method `decorate(String)`. Sau khi gắn `formatter::decorate`, đổi `suffix` trên đúng formatter; dự đoán callback phản ánh dữ liệu mới nhưng vẫn dùng cùng object.

**Bài 6 — Consumer trả void:** Gắn `StringBuilder::append` theo dạng có receiver `builder::append` vào `Consumer<String>`. Giải thích vì sao `accept` hợp lệ dù `append` trả `StringBuilder`; chạy hai lần và đối chiếu nội dung builder.

**Bài 7 — Exception contract:** Viết method `String load() throws IOException` trên một object. Thử gán `object::load` cho `Supplier<String>` và `CheckedSupplier<String>`. Giải thích chỉ target thứ hai hợp lệ khi checked exception có thể thoát ra.

**Bài 8 — Callback ownership:** Trong một API listener có `addListener`/`removeListener`, đăng ký bằng một biến `Consumer<Event> listener = handler::handle;` rồi gỡ bằng đúng biến đó. So sánh với việc viết lại `handler::handle` tại chỗ và giải thích tại sao không nên dựa vào identity của expression mới.

**Đạt yêu cầu khi** bạn giải thích được receiver nào đã gắn và lúc nào, phân biệt thời điểm lỗi null, áp dụng đúng functional interface, chạy chương trình ở mục 6 khớp output, và chọn bound reference hay lambda theo đúng yêu cầu vòng đời/định tuyến của ứng dụng.

## 14. Tài liệu chính thức để đối chiếu

- Java Language Specification `15.13 Method Reference Expressions, đặc biệt `15.13.3 Run-Time Evaluation: https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.13.3
- Java Language Specification `15.27 Lambda Expressions (đối chiếu quy tắc lambda): https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.27
- Java SE API `java.util.function`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/package-summary.html
- Tài liệu `IntFunction`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/function/IntFunction.html

**Ghi nhớ:** `object::method` giữ **đối tượng nhận cụ thể được đánh giá ngay**, còn việc gọi method vẫn xảy ra khi functional callback được thực thi. Hai thời điểm khác nhau này là chìa khóa để hiểu null, state, registry, vòng đời và refactor an toàn trên Java hiện đại.