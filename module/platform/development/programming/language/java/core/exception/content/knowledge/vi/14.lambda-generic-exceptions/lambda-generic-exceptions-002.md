# Method reference và tính tương thích của `throws` trong Java

**Method reference** (`::`) là cách viết ngắn để dùng một phương thức hoặc constructor như phần triển khai của một **functional interface**. Khi phương thức được tham chiếu có thể ném **checked exception**, Java không chỉ kiểm tra tham số và kiểu trả về: trình biên dịch còn so sánh **những checked exception mà lời gọi có thể ném** với **mệnh đề `throws` của phương thức trừu tượng chức năng (SAM – single abstract method)** trong kiểu đích.

Một quy tắc cốt lõi:

> **Method reference có checked exception chỉ tương thích với functional interface nếu các checked exception liên quan được cho phép bởi `throws` của SAM**, xét các quy tắc kiểu và suy luận generic của Java. Không có chuyển đổi “tự bắt lỗi”, “tự thêm `throws`” hoặc “tự bọc thành RuntimeException” chỉ vì dùng ký hiệu `::`.

Ví dụ, `Callable<T>.call() throws Exception` có thể nhận một method reference tới phương thức khai báo `throws IOException`. Ngược lại, `Supplier<T>.get()` và `Runnable.run()` không khai báo checked exception nào, nên không thể nhận trực tiếp một method reference mà phương thức được tham chiếu khai báo `throws IOException`.

Bài này giải thích cách Java kiểm tra method reference với `throws` trên Java 17+, phân biệt static/bound/unbound/constructor reference, thử nghiệm bằng chương trình có đầu ra chính xác, cách sửa lỗi biên dịch, generic functional interface có kiểu exception, adapter sang API chuẩn, overload, và những ranh giới thiết kế cần chú ý.

## 1. Nhớ lại các thành phần của một method reference

Một method reference không tự tạo ra một lời gọi ngay khi được viết. Nó là một biểu thức được **kiểu hóa theo ngữ cảnh đích** (*target typing*) và tạo một đối tượng hoạt động theo functional interface được chọn.

Ví dụ:

```java
Runnable task = service::run;
```

Đây là **mã minh họa**; cần biến `service` có method `run()` thích hợp. Ở đây:

- `service::run` là **method reference expression**.
- `Runnable` là **target type**.
- `Runnable.run()` là **SAM**, có chữ ký `void run()`, không khai báo checked exception.
- Phương thức instance `service.run()` là **phương thức được tham chiếu**; nó cần tương thích với SAM.
- Khi `task.run()` được gọi, hành vi được tham chiếu mới thực thi.

Các thành phần phải ăn khớp gồm **số lượng/kiểu tham số, khả năng chuyển đổi kiểu trả về và tập checked exception được phép thoát ra**. Phương thức có `throws` không phải là một overload riêng biệt chỉ bởi mệnh đề `throws`.

**Phân biệt ba thời điểm:**

1. **Biên dịch**: Java kiểm tra method reference có tương thích với target SAM hay không, gồm checked exceptions.
2. **Đánh giá reference**: tạo/capture reference thích hợp; thông thường không gọi phương thức đích.
3. **Gọi SAM**: phương thức đích thực thi và exception thực sự có thể được ném, bắt hoặc lan truyền.

Đối với bound reference như `object::instanceMethod`, việc đánh giá receiver có quy tắc riêng; receiver bằng `null` có thể gây `NullPointerException` ngay khi tạo reference. Điều này khác với checked-exception checking ở compile time.

## 2. Bốn hình thức method reference thường gặp

| Dạng | Ý nghĩa | Ví dụ minh họa |
| --- | --- | --- |
| `ClassName::staticMethod` | Tham chiếu static method | `Parser::parse` |
| `instance::instanceMethod` | Tham chiếu method trên receiver đã có | `reader::read` |
| `ClassName::instanceMethod` | Tham chiếu unbound method; receiver trở thành tham số của SAM | `String::length` |
| `ClassName::new` | Tham chiếu constructor | `InputStreamReader::new` |

Bốn hình thức đều chịu kiểm tra kiểu đích. Nếu lời gọi thực tế theo biểu thức tham chiếu có thể ném checked exception mà SAM không cho phép, **biên dịch thất bại**, dù method reference trông ngắn hoặc chưa được gọi trong chương trình.

Ví dụ, `String::length` khớp `Function<String, Integer>` qua boxing từ `int` thành `Integer`, vì `String.length()` không khai báo checked exception. Ngược lại, một factory có `throws IOException` không thể tự động được dùng như `Function<String, Resource>` nếu `Function.apply` không cho phép checked exception.

## 3. `throws` của SAM đóng vai trò gì?

Functional interface phải có đúng một phương thức trừu tượng theo luật của Java; phương thức ấy cung cấp chữ ký chức năng mà method reference sẽ thực hiện.

Hai interface khác nhau:

```java
@FunctionalInterface
interface PlainAction {
    void run();
}

@FunctionalInterface
interface CheckedAction {
    void run() throws java.io.IOException;
}
```

Đây là **hai interface hoàn chỉnh**, không có `main`. Nếu một phương thức có khai báo `throws IOException`, nó có thể phù hợp với `CheckedAction`, nhưng không phù hợp với `PlainAction` chỉ bởi vì tên method của interface đều là `run()`.

Tập checked exception mà method reference có thể ném phải nằm trong những loại được SAM khai báo cho phép. Quy tắc dùng kiểu **gán được / subtype**:

- Phương thức được tham chiếu `throws FileNotFoundException`; SAM `throws IOException` → **hợp lệ**, vì `FileNotFoundException extends IOException`.
- Phương thức được tham chiếu `throws IOException`; SAM `throws Exception` → **hợp lệ**, vì `IOException extends Exception`.
- Phương thức được tham chiếu `throws Exception`; SAM chỉ `throws IOException` → **không hợp lệ**, vì `Exception` quá rộng.
- Phương thức được tham chiếu `throws IOException, SQLException`; SAM chỉ `throws IOException` → **không hợp lệ**, vì `SQLException` không thuộc `IOException`.
- Phương thức được tham chiếu chỉ ném `RuntimeException` hoặc `Error` → không bị bắt buộc khai báo trong SAM.

**Đừng nghĩ rằng “SAM có một kiểu exception giống tên nào đó” là đủ**; mọi checked exception liên quan từ phương thức đích đều phải được phép theo quy tắc tương thích.

## 4. Ví dụ Java 17 đầy đủ: cùng method, SAM phù hợp và không phù hợp

Lưu **`ThrowsCompatibilityDemo.java`**:

```java
import java.io.IOException;

public class ThrowsCompatibilityDemo {
    @FunctionalInterface
    interface CheckedAction {
        void run() throws IOException;
    }

    static void load() throws IOException {
        System.out.println("Đang tải");
        throw new IOException("Không đọc được cấu hình");
    }

    public static void main(String[] args) {
        CheckedAction action = ThrowsCompatibilityDemo::load;
        System.out.println("Reference đã tạo");

        try {
            action.run();
        } catch (IOException e) {
            System.out.println("Đã bắt: " + e.getMessage());
        }

        System.out.println("Kết thúc");
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 ThrowsCompatibilityDemo.java
java ThrowsCompatibilityDemo
```

**Stdout chính xác**:

```text
Reference đã tạo
Đang tải
Đã bắt: Không đọc được cấu hình
Kết thúc
```

Giải thích:

1. `CheckedAction.run() throws IOException` là hợp đồng của target.
2. `ThrowsCompatibilityDemo.load() throws IOException` được phép bởi hợp đồng đó.
3. Gán `ThrowsCompatibilityDemo::load` chỉ tạo một biểu thức thực thi theo SAM; không gọi `load`, nên dòng `Đang tải` chưa xuất hiện.
4. Khi gọi `action.run()`, method `load` chạy và ném `IOException`.
5. Caller phải catch hoặc khai báo checked `IOException` tại điểm gọi `action.run()`.

Nếu thay dòng gán bằng:

```java
Runnable action = ThrowsCompatibilityDemo::load;
```

đây là **phản ví dụ cố ý không biên dịch**. `Runnable.run()` không khai báo `throws IOException`. Method reference bị từ chối vì checked exception của `load` không được SAM cho phép. Java **không tạo một Runnable rồi âm thầm nuốt lỗi**.

## 5. `Runnable`, `Supplier`, `Function` và `Consumer` không cho phép checked exception

Các functional interface quen thuộc trong JDK thường được sử dụng ở nơi API muốn callback đơn giản:

| Interface | SAM | Mệnh đề checked `throws` |
| --- | --- | --- |
| `Runnable` | `void run()` | Không |
| `Supplier<T>` | `T get()` | Không |
| `Function<T,R>` | `R apply(T t)` | Không |
| `Consumer<T>` | `void accept(T t)` | Không |
| `Predicate<T>` | `boolean test(T t)` | Không |
| `BiFunction<T,U,R>` | `R apply(T t, U u)` | Không |
| `Callable<V>` | `V call() throws Exception` | **Có, Exception** |

Một method reference tới phương thức chỉ ném unchecked exception có thể hợp lệ với các interface không `throws` nếu **những yếu tố kiểu khác đều khớp**.

Ví dụ sau là **mã minh họa**:

```java
java.util.function.Supplier<Integer> supplier = String::length;
```

Dòng này **không hợp lệ**, nhưng **không phải vì throws**: `String::length` là **unbound instance method** cần một receiver kiểu `String`, trong khi `Supplier.get()` không nhận tham số. Cách đúng:

```java
java.util.function.Function<String, Integer> length = String::length;
```

Đây là ví dụ nhấn mạnh: một method reference phải thỏa **cả chữ ký tham số/trả về lẫn checked exceptions**. Khi chẩn đoán lỗi compile, không quy tất cả vào `throws`.

## 6. `Callable<V>` cho phép checked exception rộng `Exception`

`java.util.concurrent.Callable<V>` có SAM:

```java
V call() throws Exception;
```

Do đó một phương thức `String read() throws IOException` có thể được tham chiếu qua `Callable<String>`, vì `IOException` là con của `Exception`.

Lưu **`CallableReferenceDemo.java`**:

```java
import java.io.IOException;
import java.util.concurrent.Callable;

public class CallableReferenceDemo {
    static String readData() throws IOException {
        System.out.println("Đọc dữ liệu");
        return "OK";
    }

    public static void main(String[] args) {
        Callable<String> callable = CallableReferenceDemo::readData;

        try {
            System.out.println("Kết quả: " + callable.call());
        } catch (Exception e) {
            System.out.println("Lỗi: " + e.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 CallableReferenceDemo.java
java CallableReferenceDemo
```

**Stdout chính xác**:

```text
Đọc dữ liệu
Kết quả: OK
```

Ở điểm gán, `Callable<String>` chấp nhận phương thức khai báo `throws IOException`. Nhưng tại điểm **gọi qua biến `Callable<String>`**, chữ ký `call() throws Exception` là chữ ký tĩnh caller nhìn thấy. Do đó ví dụ catch `Exception` thay vì chỉ `IOException`.

**Sự khác biệt quan trọng:**

- **Kiểm tra gán method reference:** `throws IOException` nằm trong `throws Exception` → hợp lệ.
- **Kiểm tra lời gọi SAM:** `call()` được khai báo `throws Exception` → caller phải đáp ứng hợp đồng rộng đó.

Không có nghĩa method `readData` bỗng có khả năng ném mọi `Exception`. Chỉ có nghĩa khi nhìn qua target type `Callable`, compiler kiểm tra lời gọi bằng chữ ký của target interface.

## 7. Thu hẹp hợp đồng ở functional interface riêng

Nếu muốn giữ nghĩa vụ checked exception chính xác hơn `Callable`, có thể định nghĩa SAM riêng:

```java
@FunctionalInterface
interface IoSupplier<T> {
    T get() throws java.io.IOException;
}
```

Ví dụ độc lập **`IoSupplierDemo.java`**:

```java
import java.io.IOException;

public class IoSupplierDemo {
    @FunctionalInterface
    interface IoSupplier<T> {
        T get() throws IOException;
    }

    static String obtain() throws IOException {
        throw new IOException("Nguồn chưa sẵn sàng");
    }

    static String use(IoSupplier<String> supplier)
            throws IOException {
        return supplier.get();
    }

    public static void main(String[] args) {
        IoSupplier<String> supplier = IoSupplierDemo::obtain;

        try {
            System.out.println(use(supplier));
        } catch (IOException e) {
            System.out.println("I/O: " + e.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 IoSupplierDemo.java
java IoSupplierDemo
```

**Stdout chính xác**:

```text
I/O: Nguồn chưa sẵn sàng
```

`IoSupplier.get() throws IOException` chính xác hơn `Callable.call() throws Exception` nếu API chỉ cần mô tả lỗi I/O. Nó giúp caller xử lý đúng loại checked exception mà không mở rộng vô cớ thành `Exception`.

Lưu ý: không cần tạo functional interface mới cho mọi method đơn giản; chỉ nên làm khi giao diện này biểu diễn **hợp đồng callback có checked failure** thật sự cần thiết.

## 8. So sánh với lambda: cùng luật `throws`

Hai cách viết:

```java
IoSupplier<String> first = DataStore::read;
IoSupplier<String> second = () -> DataStore.read();
```

Đây là **mã minh họa**, giả định `DataStore.read() throws IOException` và `IoSupplier<T>` có `get() throws IOException`. Với mục đích tương thích checked exception, cả hai biểu thức đều phải đáp ứng hợp đồng SAM.

Lambda không phải “cửa sau” để né luật. Dạng sau **cố ý không biên dịch** nếu `DataStore.read() throws IOException`:

```java
java.util.function.Supplier<String> s =
        () -> DataStore.read();
```

Lý do: thân lambda có lời gọi có thể ném checked `IOException` nhưng `Supplier.get()` không khai báo checked exception. Dạng method reference:

```java
java.util.function.Supplier<String> s = DataStore::read;
```

cũng **không biên dịch** với cùng nguyên nhân về `throws`. Khác biệt cú pháp không làm thay đổi nghĩa vụ checked exception.

Tuy nhiên, lambda **có thể** chứa `try/catch` để xử lý hoặc chuyển lỗi:

```java
java.util.function.Supplier<String> s = () -> {
    try {
        return DataStore.read();
    } catch (IOException e) {
        return "fallback";
    }
};
```

Đây là **mã minh họa**, với fallback chỉ hợp lệ khi hợp đồng nghiệp vụ thực sự cho phép. Đoạn này phù hợp với `Supplier` vì **không có checked IOException thoát ra khỏi thân lambda**.

Chọn giữa method reference và lambda theo mức độ rõ ràng, không theo suy nghĩ rằng `::` có quy tắc exception “thoáng” hơn.

## 9. Static method reference với checked exception

Cú pháp:

```java
TargetAction action = UtilityClass::operation;
```

Khi `UtilityClass.operation()` là static, Java kiểm tra nó tương thích với SAM của `TargetAction`, gồm checked exceptions.

Một ví dụ Java 17 độc lập **`StaticReferenceDemo.java`**:

```java
import java.io.IOException;

public class StaticReferenceDemo {
    @FunctionalInterface
    interface Parser {
        int parse(String input) throws IOException;
    }

    static int parsePort(String input) throws IOException {
        int port = Integer.parseInt(input);
        if (port < 1 || port > 65535) {
            throw new IOException("Port ngoài giới hạn");
        }
        return port;
    }

    public static void main(String[] args) {
        Parser parser = StaticReferenceDemo::parsePort;

        try {
            System.out.println("Port: " + parser.parse("8080"));
            System.out.println("Port: " + parser.parse("70000"));
        } catch (IOException e) {
            System.out.println("Lỗi: " + e.getMessage());
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 --release 17 StaticReferenceDemo.java
java StaticReferenceDemo
```

**Stdout chính xác**:

```text
Port: 8080
Lỗi: Port ngoài giới hạn
```

`Parser.parse` có cùng tham số/kiểu trả về với `parsePort` và cho phép `IOException`. Việc bắt `IOException` ở `main` áp dụng cho lời gọi qua `parser`.

**Một chú ý quan trọng:** `Integer.parseInt` có thể ném `NumberFormatException`, vốn là unchecked. Nó có thể lan truyền dù `Parser.parse` chỉ khai báo `throws IOException`. Mệnh đề `throws` của SAM không chặn unchecked exception và không bảo đảm mọi đầu vào có lỗi đều biến thành `IOException`.

## 10. Bound instance method reference: `object::method`

**Bound reference** cố định receiver ở thời điểm tạo biểu thức:

```java
ReaderService service = new ReaderService();
CheckedAction action = service::reload;
```

Đây là **mã minh họa**; `ReaderService.reload() throws IOException` được giả định tương thích với `CheckedAction.run() throws IOException`.

Trong hình thức này, SAM **không cần nhận receiver làm đối số**, vì receiver `service` đã được chọn. Checked exceptions được xét từ method đích theo hợp đồng.

Ví dụ đầy đủ **`BoundReferenceDemo.java`**:

```java
import java.io.IOException;

public class BoundReferenceDemo {
    static class Worker {
        private final String name;

        Worker(String name) {
            this.name = name;
        }

        void execute() throws IOException {
            System.out.println("Worker: " + name);
            throw new IOException("Chưa có dữ liệu");
        }
    }

    @FunctionalInterface
    interface CheckedAction {
        void run() throws IOException;
    }

    public static void main(String[] args) {
        Worker worker = new Worker("A");
        CheckedAction action = worker::execute;

        try {
            action.run();
        } catch (IOException e) {
            System.out.println("Bắt: " + e.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 BoundReferenceDemo.java
java BoundReferenceDemo
```

**Stdout chính xác**:

```text
Worker: A
Bắt: Chưa có dữ liệu
```

Method `execute` vẫn khai báo checked `IOException`, nên không thể thay target thành `Runnable` chỉ bằng việc dùng `worker::execute`.

### Receiver `null` là vấn đề riêng với `throws`

Với bound reference `worker::execute`, Java kiểm tra receiver ở **thời điểm đánh giá method reference**. Nếu receiver bằng `null`, một `NullPointerException` có thể xuất hiện **trước khi SAM được gọi**.

Đây là unchecked exception, không phải một `IOException` cần bổ sung vào `throws` của interface. Không nên nhầm lỗi tạo bound reference vì receiver null với lỗi do method được tham chiếu phát sinh lúc SAM chạy.

## 11. Unbound instance reference: `Type::instanceMethod`

Hình thức unbound dùng **receiver là đối số đầu tiên của SAM**. Ví dụ:

```java
java.util.function.Function<String, Integer> length =
        String::length;
```

Khi `length.apply("abc")` chạy, đối số `"abc"` trở thành receiver để gọi `String.length()`. Với method có checked exception, SAM cũng cần khai báo khả năng ném checked exception đó.

Ví dụ Java 17 **`UnboundReferenceDemo.java`**:

```java
import java.io.IOException;

public class UnboundReferenceDemo {
    static class Document {
        private final String name;

        Document(String name) {
            this.name = name;
        }

        String read() throws IOException {
            if ("bad".equals(name)) {
                throw new IOException("Không mở được tài liệu");
            }
            return "Nội dung " + name;
        }
    }

    @FunctionalInterface
    interface Reader {
        String read(Document document) throws IOException;
    }

    public static void main(String[] args) {
        Reader reader = Document::read;
        try {
            System.out.println(reader.read(new Document("good")));
            System.out.println(reader.read(new Document("bad")));
        } catch (IOException e) {
            System.out.println("Bắt: " + e.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 UnboundReferenceDemo.java
java UnboundReferenceDemo
```

**Stdout chính xác**:

```text
Nội dung good
Bắt: Không mở được tài liệu
```

Phân tích: `Document::read` không gắn sẵn một object `Document` nào. SAM `Reader.read(Document)` cung cấp receiver ở lúc gọi, và cho phép checked `IOException`.

Nếu dùng `Function<Document, String> fn = Document::read;`, Java không chấp nhận vì `Function.apply` không khai báo `throws IOException`. Đây là lỗi về hợp đồng exceptions, dù tham số và kiểu trả về khớp.

## 12. Constructor reference cũng kiểm tra checked exceptions

Ký hiệu `Type::new` có thể tạo object thông qua một constructor tương thích với SAM. Nếu constructor khai báo checked exception, **SAM của factory interface phải cho phép exception đó**.

Ví dụ Java 17 đầy đủ **`ConstructorReferenceDemo.java`**:

```java
import java.io.IOException;

public class ConstructorReferenceDemo {
    static class Connection {
        private final String address;

        Connection(String address) throws IOException {
            if (address.isBlank()) {
                throw new IOException("Địa chỉ trống");
            }
            this.address = address;
        }

        String address() {
            return address;
        }
    }

    @FunctionalInterface
    interface ConnectionFactory {
        Connection open(String address) throws IOException;
    }

    public static void main(String[] args) {
        ConnectionFactory factory = Connection::new;
        try {
            System.out.println("Đã tạo: "
                    + factory.open("db.internal").address());
            factory.open("");
        } catch (IOException e) {
            System.out.println("Lỗi factory: " + e.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 ConstructorReferenceDemo.java
java ConstructorReferenceDemo
```

**Stdout chính xác**:

```text
Đã tạo: db.internal
Lỗi factory: Địa chỉ trống
```

`Connection::new` tương thích `ConnectionFactory.open(String) throws IOException`. Nếu viết:

```java
java.util.function.Function<String, Connection> factory =
        Connection::new;
```

đây là **phản ví dụ cố ý không biên dịch** vì constructor `Connection(String) throws IOException`, trong khi `Function.apply` không cho phép checked exception.

**Constructor reference không tự gọi constructor khi reference được gán.** Constructor chạy lúc `factory.open(...)` được gọi. Ngoại lệ từ constructor được kiểm tra theo kiểu tĩnh tại bước gán reference và thực sự ném tại bước gọi.

## 13. Tương thích theo quan hệ kế thừa của exception

Không cần SAM khai báo đúng y nguyên tên exception. Một **supertype hợp lệ** có thể bao phủ checked exception của method đích.

Ví dụ minh họa:

```java
static void openSpecific() throws java.io.FileNotFoundException {
    throw new java.io.FileNotFoundException("Không tìm thấy");
}
```

Nếu có interface:

```java
@FunctionalInterface
interface GeneralIoAction {
    void run() throws java.io.IOException;
}
```

thì `GeneralIoAction action = Example::openSpecific;` (giả sử method nằm trong `Example`) **hợp lệ** vì `FileNotFoundException` là subtype của `IOException`.

Chiều ngược lại không hợp lệ:

```java
@FunctionalInterface
interface SpecificIoAction {
    void run() throws java.io.FileNotFoundException;
}
```

Nếu method được tham chiếu chỉ khai báo `throws IOException` rộng, Java không thể bảo đảm mọi `IOException` đều là `FileNotFoundException`, nên method reference tới nó không tương thích với `SpecificIoAction`.

**Lỗi compile dựa trên những exception được khai báo và phân tích theo kiểu tĩnh, không dựa trên việc nhánh runtime trong một lần thử có ném loại nào.**

## 14. Nhiều checked exceptions phải được SAM bao phủ

Một method có thể khai báo nhiều loại lỗi:

```java
static void synchronize() throws java.io.IOException,
                                 java.sql.SQLException {
    // ...
}
```

Đây là **phương thức minh họa**, thân được lược vì không cần logic thực hiện. SAM tương thích:

```java
@FunctionalInterface
interface SyncAction {
    void run() throws java.io.IOException,
                      java.sql.SQLException;
}
```

Hoặc một SAM có `throws Exception` có thể bao phủ cả hai:

```java
@FunctionalInterface
interface GeneralAction {
    void run() throws Exception;
}
```

Nhưng SAM chỉ `throws IOException` **không đủ** nếu method tham chiếu có thể ném checked `SQLException`. Gộp vào `throws Exception` có thể dễ triển khai, nhưng sẽ khiến caller gọi SAM phải xử lý/khai báo kiểu **rộng hơn**. Khi API cần caller phân loại lỗi, khai báo cụ thể thường hữu ích hơn.

Một ví dụ độc lập **`MultipleThrowsReferenceDemo.java`**:

```java
import java.io.IOException;
import java.sql.SQLException;

public class MultipleThrowsReferenceDemo {
    @FunctionalInterface
    interface SyncAction {
        void run() throws IOException, SQLException;
    }

    static void sync(boolean dbFailure)
            throws IOException, SQLException {
        if (dbFailure) {
            throw new SQLException("DB lỗi");
        }
        throw new IOException("Tệp lỗi");
    }

    public static void main(String[] args) {
        SyncAction io = () -> sync(false);
        SyncAction db = () -> sync(true);

        for (SyncAction action : new SyncAction[] {io, db}) {
            try {
                action.run();
            } catch (IOException e) {
                System.out.println("I/O: " + e.getMessage());
            } catch (SQLException e) {
                System.out.println("SQL: " + e.getMessage());
            }
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 MultipleThrowsReferenceDemo.java
java MultipleThrowsReferenceDemo
```

**Stdout chính xác**:

```text
I/O: Tệp lỗi
SQL: DB lỗi
```

Đoạn này dùng **lambda** để truyền đối số `boolean` cố định; cách dùng method reference trực tiếp sẽ cần SAM có cùng danh sách tham số với `sync(boolean)`, ví dụ `void run(boolean) throws IOException, SQLException`. Trọng tâm là nhiều checked exceptions vẫn phải được target bao phủ.

## 15. Method reference có thêm tham số của phương thức gốc

Method reference phải phù hợp với SAM về các tham số. Nếu muốn gán `Demo::sync` trực tiếp, thay vì lambda đã cố định boolean, có thể định nghĩa:

```java
@FunctionalInterface
interface SyncOperation {
    void run(boolean dbFailure)
            throws java.io.IOException, java.sql.SQLException;
}
```

Rồi trong ngữ cảnh method `sync(boolean)` thuộc lớp `Demo`:

```java
SyncOperation operation = Demo::sync;
```

Đây là **mã minh họa**, không phải chương trình độc lập. Java sẽ kiểm tra:

- Một tham số kiểu `boolean` bên SAM chuyển vào method `sync(boolean)`.
- Kiểu trả về `void` tương thích.
- `throws IOException, SQLException` bên SAM bao phủ các checked exceptions của method `sync`.

Nếu một trong ba nhóm điều kiện không đáp ứng, phép gán có thể thất bại. **Method reference không tự bỏ tham số**; dùng lambda để cố định, chuyển đổi hoặc cung cấp logic bổ sung nếu cần.

## 16. Overload và lựa chọn method reference

Khi một lớp có **overloaded methods**, trình biên dịch tìm phương thức tương thích theo kiểu đích, số tham số, quan hệ kiểu và các quy tắc overload resolution.

Ví dụ:

```java
class Reporter {
    static void report(String text) {
        System.out.println("Text: " + text);
    }

    static void report(Integer code) {
        System.out.println("Code: " + code);
    }
}
```

Đây là **class minh họa**, không có `main`. Các target:

```java
java.util.function.Consumer<String> a = Reporter::report;
java.util.function.Consumer<Integer> b = Reporter::report;
```

được phân giải tới các overload có tham số tương ứng, không dựa trên `throws` vì hai method trên không khai báo checked exception.

**Không thể overload hai method chỉ khác mệnh đề `throws`**:

```java
// Cố ý không hợp lệ nếu đặt trong cùng một class:
void process() throws IOException { }
void process() throws SQLException { }
```

Dù hai danh sách `throws` khác nhau, Java coi hai method cùng tên và cùng danh sách tham số là cùng chữ ký cho mục đích này. Do đó `throws` không phải cách tạo lựa chọn overload.

Nếu gặp method reference không rõ ràng hoặc không tương thích, hãy xem **target type**, overload được chọn và mọi checked exceptions từ method cụ thể. Đừng nghĩ compiler sẽ chọn một overload chỉ vì có `throws` “vừa” với SAM.

## 17. Generic functional interface khai báo kiểu exception

Một pattern phù hợp khi thư viện cần nhiều loại checked exception là tham số hóa kiểu exception:

```java
@FunctionalInterface
interface ThrowingFunction<T, R, E extends Exception> {
    R apply(T input) throws E;
}
```

Ở đây:

- `T` là kiểu đầu vào.
- `R` là kiểu kết quả.
- `E extends Exception` là kiểu exception được phép trong hợp đồng.
- Khi chọn `E = IOException`, SAM được hiểu là `R apply(T) throws IOException` theo cách kiểm tra kiểu Java phù hợp.
- Khi chọn `E = Exception`, SAM cho phép nhiều loại checked exception hơn nhưng hợp đồng caller rộng hơn.

Ví dụ Java 17 độc lập **`GenericThrowingFunctionDemo.java`**:

```java
import java.io.IOException;

public class GenericThrowingFunctionDemo {
    @FunctionalInterface
    interface ThrowingFunction<T, R, E extends Exception> {
        R apply(T input) throws E;
    }

    static Integer parseFile(String text) throws IOException {
        if (text.isBlank()) {
            throw new IOException("Không có nội dung");
        }
        return Integer.parseInt(text);
    }

    static <T, R, E extends Exception> R execute(
            ThrowingFunction<T, R, E> fn, T value) throws E {
        return fn.apply(value);
    }

    public static void main(String[] args) {
        ThrowingFunction<String, Integer, IOException> parser =
                GenericThrowingFunctionDemo::parseFile;

        try {
            System.out.println("Số: " + execute(parser, "25"));
            execute(parser, "");
        } catch (IOException e) {
            System.out.println("I/O: " + e.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 GenericThrowingFunctionDemo.java
java GenericThrowingFunctionDemo
```

**Stdout chính xác**:

```text
Số: 25
I/O: Không có nội dung
```

Dạng này giữ checked exception cụ thể qua interface generic và phương thức `execute`. Vì `execute` khai báo `throws E`, khi `E` là `IOException`, caller vẫn phải xử lý `IOException`.

**Một giới hạn thiết kế:** một tham số `E extends Exception` diễn đạt tốt một nhóm exception có thể bao phủ bằng một kiểu. Nếu callback ném nhiều checked exception **không có một superclass hẹp hữu ích**, bạn có thể cần `throws` nhiều loại cụ thể, một exception domain chung, hoặc một hợp đồng kết quả khác. Không phải generic exception type tự giải quyết mọi bài toán.

## 18. Adapter từ checked function sang `Function`

Một API chuẩn như `Stream.map` nhận `Function`, không cho phép checked exceptions. Nếu bạn có `ThrowingFunction<T,R,IOException>`, cần lựa chọn chính sách chuyển đổi hoặc xử lý lỗi.

Một adapter chuyển `IOException` thành unchecked `UncheckedIOException` là một lựa chọn khi hợp đồng cho phép:

```java
static <T, R> java.util.function.Function<T, R> uncheckedIo(
        ThrowingFunction<T, R, IOException> fn) {
    return value -> {
        try {
            return fn.apply(value);
        } catch (IOException e) {
            throw new java.io.UncheckedIOException(e);
        }
    };
}
```

Đây là **phương thức minh họa**, giả sử `ThrowingFunction` đã khai báo; có import `java.io.IOException` nếu không viết tên đầy đủ. Adapter được dùng:

```java
java.util.function.Function<String, Integer> fn =
        uncheckedIo(Parser::parse);
```

Đây cũng là **mã khung**; `Parser.parse(String) throws IOException` được giả định. Sau chuyển đổi:

- `Function.apply` không khai báo checked `IOException`.
- Nếu callback ném `IOException`, adapter bắt và ném **`UncheckedIOException`** (một unchecked exception).
- `UncheckedIOException.getCause()` giữ exception I/O gốc.
- Caller qua `Function` không phải khai báo `throws IOException` nhưng cần có chiến lược xử lý nếu failure thực sự xảy ra.
- Đổi kiểu exception **không tự phục hồi** và không bảo đảm thao tác thành công.

Không nên bọc mọi `Exception` bằng `RuntimeException` chỉ để trình biên dịch im lặng. Hãy chọn conversion phù hợp với hợp đồng API và giữ `cause`.

## 19. Ví dụ Java 17 chạy được: adapter giữ nguyên `cause`

Lưu **`AdapterReferenceDemo.java`**:

```java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.function.Function;

public class AdapterReferenceDemo {
    @FunctionalInterface
    interface IoFunction<T, R> {
        R apply(T value) throws IOException;
    }

    static <T, R> Function<T, R> unchecked(IoFunction<T, R> fn) {
        return value -> {
            try {
                return fn.apply(value);
            } catch (IOException e) {
                throw new UncheckedIOException(e);
            }
        };
    }

    static String read(String name) throws IOException {
        if ("bad".equals(name)) {
            throw new IOException("Không đọc được bad");
        }
        return "OK:" + name;
    }

    public static void main(String[] args) {
        Function<String, String> fn =
                unchecked(AdapterReferenceDemo::read);

        System.out.println(fn.apply("good"));
        try {
            fn.apply("bad");
        } catch (UncheckedIOException e) {
            System.out.println("Wrapper: "
                    + e.getClass().getSimpleName());
            System.out.println("Cause: "
                    + e.getCause().getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 AdapterReferenceDemo.java
java AdapterReferenceDemo
```

**Stdout chính xác**:

```text
OK:good
Wrapper: UncheckedIOException
Cause: Không đọc được bad
```

Nhờ `IoFunction.apply throws IOException`, method reference `AdapterReferenceDemo::read` được nhận trước khi adapter chuyển thành `Function`. `UncheckedIOException` giữ nguyên object `IOException` ở `getCause()`, giúp không mất trace và message gốc.

Adapter này **chuyển hợp đồng lỗi từ checked sang unchecked**. Đây là lựa chọn thiết kế cần được công bố, không phải một tính năng tự động của method reference.

## 20. Stream API và các thao tác lazy

`Stream.map` nhận `Function<? super T, ? extends R>`, còn `forEach` nhận `Consumer<? super T>`. Các SAM đó **không khai báo checked exceptions**.

Vì vậy code kiểu:

```java
// Đoạn minh họa, cố ý không biên dịch:
stream.map(Files::readString)
      .toList();
```

nếu `stream` là `Stream<Path>` và `Files.readString(Path)` có `throws IOException`, method reference sẽ không tương thích với `Function<Path,String>` do checked `IOException`. Việc terminal operation `toList()` nằm ở cuối không giúp Java tự bắt lỗi.

Có những lựa chọn rõ ràng:

1. **Đọc tuần tự bằng vòng lặp có `throws IOException` hoặc `try/catch`** nếu muốn caller xử lý checked I/O.
2. **Dùng adapter** chuyển `IOException` thành `UncheckedIOException` có `cause` nếu pipeline chỉ phù hợp unchecked exception.
3. **Trả kết quả có trạng thái** (ví dụ success/error) nếu mỗi phần tử có thể thất bại và tác vụ cần thu thập cả kết quả lẫn lỗi.
4. **Xử lý lỗi trong lambda** nếu có fallback thực sự hợp lệ cho một phần tử.
5. **Tách thao tác I/O khỏi pipeline**, khi điều đó giúp luồng lỗi dễ hiểu và kiểm soát tài nguyên hơn.

Một stream pipeline có thể **lazy**: nhiều phép tính trung gian chưa chạy cho đến khi có terminal operation. Nhưng luật checked exception được kiểm tra **ngay lúc biên dịch biểu thức method reference**, không chờ tới khi pipeline chạy.

## 21. `Function` hay `Callable` không tự tạo một quy tắc retry

Bất kỳ method reference nào cũng chỉ mô tả **hành vi có thể gọi**, không tự động bổ sung retry hoặc bù trừ thao tác.

Ví dụ:

```java
Callable<String> task = Client::read;
```

đây là **mã minh họa**: nếu `Client.read() throws IOException` là static không tham số, `Callable.call() throws Exception` nhận được reference. Nếu sau đó `task.call()` ném `IOException`, việc có thử lại hay không tùy mã gọi.

Không nên suy luận rằng chọn SAM rộng `throws Exception` nghĩa là Java “xử lý lỗi ở nền” cho bạn. Nếu dùng `ExecutorService.submit(Callable)`, cơ chế bất đồng bộ có thể **bọc lỗi khi lấy kết quả qua `Future.get()`**, chẳng hạn trong `ExecutionException`, nhưng đó là hợp đồng của executor/future, **không phải của method reference hoặc cú pháp `throws`**.

Nhiệm vụ callback và chính sách xử lý lỗi nên được thiết kế ở hai tầng tách biệt: **chữ ký target** cho tính hợp lệ compile time, và **caller/framework** cho cách phản ứng runtime.

## 22. Phương thức tham chiếu có `throws Exception` rộng

Nếu một method đích khai báo `throws Exception`, Java không tự suy luận rằng nó thực tế chỉ ném `IOException` bên trong để gán vào một SAM chỉ cho phép `IOException`.

Ví dụ:

```java
static void legacyOperation() throws Exception {
    throw new java.io.IOException("I/O lỗi");
}
```

Đây là **phương thức minh họa**. Dù implementation hiện tại chỉ ném `IOException`, hợp đồng tĩnh của method là `throws Exception`. Gán:

```java
IoAction action = Example::legacyOperation;
```

với `IoAction.run() throws IOException` là **không hợp lệ** chỉ vì method đích công bố kiểu quá rộng. Trong một phiên bản sau, `legacyOperation` có thể ném một checked `Exception` không phải `IOException` theo hợp đồng.

Các cách xử lý hợp lý:

- Nếu sở hữu method, **thu hẹp chữ ký `throws`** khi hợp đồng thật sự cho phép.
- Nếu target cho phép `Exception`, dùng target có `run() throws Exception`.
- Nếu cần chuyển loại lỗi, viết một **adapter/lambda có `try/catch`** và chọn cách giữ/đổi hợp đồng rõ ràng.
- Không ép kiểu vô căn cứ từ `Exception` sang `IOException`; làm vậy có thể phát sinh `ClassCastException` ngay trong xử lý lỗi.

Đây là nguyên tắc chung: **compiler tin hợp đồng tĩnh**, không dự đoán mọi hành vi runtime của thư viện trong tương lai.

## 23. Phương thức target khai báo `throws Exception` không buộc reference phải ném checked exception

Chiều ngược lại vẫn hợp lệ: target SAM có `throws Exception` nhưng method được tham chiếu **không** ném checked exception nào.

Ví dụ:

```java
@FunctionalInterface
interface Task {
    String run() throws Exception;
}
```

Với method không checked exceptions:

```java
static String greeting() {
    return "Xin chào";
}
```

thì phép gán `Task t = Example::greeting;` hợp lệ. SAM công bố **tập lỗi có thể được cho phép**, không đòi implementation nhất thiết ném một exception.

Tuy nhiên tại lời gọi `t.run()`, compiler vẫn thấy `throws Exception` của **SAM**, nên caller phải catch/declare `Exception` theo hợp đồng. Đó là chi phí của việc chọn target rộng, dù implementation cụ thể rất đơn giản.

Không nên cố dùng `Callable` chỉ vì có sẵn nếu API của bạn cần hợp đồng checked exception cụ thể để hỗ trợ caller.

## 24. Method reference và ngoại lệ unchecked

`RuntimeException` và `Error` thuộc nhóm unchecked, không bị quy tắc catch-or-declare ép khai báo. Do đó một method reference có thể hợp lệ với `Runnable` dù method có thể ném `IllegalStateException`.

Ví dụ độc lập **`UncheckedReferenceDemo.java`**:

```java
public class UncheckedReferenceDemo {
    static void enforce() {
        throw new IllegalStateException("Trạng thái không hợp lệ");
    }

    public static void main(String[] args) {
        Runnable task = UncheckedReferenceDemo::enforce;
        try {
            task.run();
        } catch (IllegalStateException e) {
            System.out.println("Bắt: " + e.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 UncheckedReferenceDemo.java
java UncheckedReferenceDemo
```

**Stdout chính xác**:

```text
Bắt: Trạng thái không hợp lệ
```

`Runnable.run()` không khai báo checked exception, nhưng không ngăn unchecked `IllegalStateException` thoát ra. `main` vẫn có thể bắt exception để phản hồi có nghĩa.

**Không diễn giải** rằng dùng `Runnable` làm mọi lỗi bất ngờ biến mất. Target type chỉ quy định giới hạn checked exception ở compile time, không tạo ra cơ chế bắt `RuntimeException` tự động.

## 25. `InterruptedException` và callback không khai báo checked exception

Một trường hợp dễ sai trong ứng dụng đa luồng:

```java
static void waitForSignal() throws InterruptedException {
    Thread.sleep(100);
}
```

Method reference `SomeClass::waitForSignal` **không** tương thích `Runnable` vì `Runnable.run()` không cho phép checked `InterruptedException`.

Nếu API cho phép, thiết kế SAM riêng `void run() throws InterruptedException` và để caller quyết định cách xử lý. Khi phải dùng `Runnable`, thường cần lambda/adapter xử lý ngắt có chủ đích:

```java
Runnable task = () -> {
    try {
        waitForSignal();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Tác vụ bị ngắt", e);
    }
};
```

Đây là **mã minh họa trong class chứa `waitForSignal`**. Một số API chờ như `Thread.sleep` xóa trạng thái interrupt khi ném `InterruptedException`; gọi lại `Thread.currentThread().interrupt()` thường cần để không đánh mất tín hiệu hủy.

Nhưng **không áp dụng wrapper một cách máy móc**: nếu framework có chính sách hủy riêng, nên tuân thủ hợp đồng của nó. Nguyên tắc là không nuốt `InterruptedException` hoặc đổi thành một thành công giả chỉ vì muốn gán method reference cho `Runnable`.

## 26. `Files::readString` và kiểm tra `throws` khi dùng JDK API

Từ Java 11, `java.nio.file.Files.readString(Path)` khai báo `throws IOException` và trả `String`. Nó có thể được dùng trong Java 17 bằng target phù hợp:

```java
@FunctionalInterface
interface FileReader {
    String read(java.nio.file.Path path)
            throws java.io.IOException;
}
```

Trong ngữ cảnh đã có interface:

```java
FileReader read = java.nio.file.Files::readString;
```

đây là **mã minh họa**, không phụ thuộc tệp cụ thể tại thời điểm tạo reference. Khi gọi `read.read(path)`, chương trình phải catch/declare `IOException` vì SAM `FileReader.read(Path)` công bố nó.

Ngược lại:

```java
java.util.function.Function<java.nio.file.Path, String> read =
        java.nio.file.Files::readString;
```

là **phản ví dụ cố ý không biên dịch**: target `Function.apply` không khai báo checked `IOException`.

Nếu cần hành vi chỉ đọc từ một `Path` cố định, có thể dùng lambda `() -> Files.readString(path)` với `IoSupplier<String>`. Một method reference `Files::readString` không thể tự biến phương thức nhận `Path` thành SAM không có tham số nếu không có cơ chế cung cấp tham số.

## 27. Có thể bắt exception bên ngoài việc gọi SAM không?

Có. Nếu target SAM có checked `throws`, bạn **bắt ở điểm gọi**:

```java
IoSupplier<String> supplier = Store::load;

try {
    String value = supplier.get();
    System.out.println(value);
} catch (IOException e) {
    System.out.println("I/O: " + e.getMessage());
}
```

Đây là **mã minh họa**, giả định `IoSupplier<T>.get() throws IOException` và `Store.load() throws IOException`. `catch` bên ngoài bao lấy **lời gọi `supplier.get()`**, nơi exception thực sự được phép thoát ra.

Nhưng không thể sửa việc gán **không tương thích** bằng cách chỉ bọc *dòng gán* trong `try/catch`:

```java
try {
    Runnable r = Store::load; // Vẫn lỗi compile nếu Store.load() throws IOException.
} catch (IOException e) {
    // Không làm method reference hợp lệ.
}
```

Đây là **phản ví dụ cố ý không biên dịch**. Vì `Runnable` không cho checked exception, compiler từ chối reference trước khi bàn đến lời gọi. `try/catch` quanh phép gán không thêm `throws` cho SAM, và method được tham chiếu cũng chưa được gọi tại dòng gán.

**Vị trí đặt handler phải theo nơi checked exception thực sự có thể phát sinh và hợp đồng SAM**, chứ không chỉ ở gần cú pháp `::`.

## 28. Method reference và tính đa hình ở runtime

Phân tích checked exception được quyết định từ **kiểu tĩnh** của method tham chiếu và target SAM. Nhưng khi thực thi, Java có thể gọi **implementation override thực tế** theo cơ chế đa hình.

Ví dụ:

```java
interface Repository {
    String fetch() throws IOException;
}

class MemoryRepository implements Repository {
    public String fetch() {
        return "cache";
    }
}
```

Đây là **mã minh họa**, cần import `IOException`. Nếu biến có kiểu `Repository repo = new MemoryRepository();`, method reference `repo::fetch` được kiểm tra dựa trên hợp đồng `Repository.fetch() throws IOException`, ngay cả khi implementation `MemoryRepository.fetch()` không khai báo checked exception.

Nghĩa là:

- `IoSupplier<String> supplier = repo::fetch;` hợp lệ.
- `Supplier<String> supplier = repo::fetch;` có thể bị từ chối vì kiểu tĩnh `Repository` công bố `IOException`.
- Nếu biến được khai báo kiểu `MemoryRepository concrete`, reference `concrete::fetch` không có checked `IOException` theo chữ ký `MemoryRepository.fetch()`, nên có thể hợp lệ với `Supplier<String>`.

**Không nên dùng thông tin “lúc chạy luôn là MemoryRepository” để bỏ qua hợp đồng static type.** Đó là điểm thiết yếu của thiết kế API và polymorphism.

## 29. Constructor `throws` và generic factory

Một factory generic có checked exception có thể được diễn đạt bằng interface:

```java
@FunctionalInterface
interface Factory<T, E extends Exception> {
    T create(String name) throws E;
}
```

Nếu constructor `Resource(String) throws IOException`, có thể chọn:

```java
Factory<Resource, IOException> factory = Resource::new;
```

Đây là **mã minh họa**, giả định đã định nghĩa class `Resource` với constructor thích hợp. `E` biểu diễn ngoại lệ mà constructor có thể ném. Caller khi gọi `factory.create(name)` phải đáp ứng `throws IOException`.

Điều này có giá trị khi một API framework có nhiều factory nhưng muốn cho phép mỗi factory công bố **một checked exception cụ thể**. Nếu một factory có nhiều loại checked exception độc lập, đừng ép mô hình một `E` nếu nó làm hỏng ý nghĩa lỗi: chọn target với `throws` phù hợp hoặc abstraction khác.

## 30. Kiểm thử tính tương thích bằng chương trình tự kiểm tra

Một bài test hữu ích cần phân biệt:

- **Tương thích compile time:** phép gán method reference phải được compiler chấp nhận.
- **Hành vi runtime:** khi SAM được gọi, method đích chạy và ném/không ném đúng exception.
- **Hợp đồng checked:** caller phải catch/declare ở điểm gọi SAM, không phải vì đã gán reference.

Ví dụ độc lập **`MethodReferenceAssertionsDemo.java`**:

```java
import java.io.IOException;

public class MethodReferenceAssertionsDemo {
    @FunctionalInterface
    interface IoTask {
        void run() throws IOException;
    }

    static void failIo() throws IOException {
        throw new IOException("expected");
    }

    static void failUnchecked() {
        throw new IllegalStateException("unchecked");
    }

    public static void main(String[] args) {
        IoTask checked = MethodReferenceAssertionsDemo::failIo;
        Runnable unchecked = MethodReferenceAssertionsDemo::failUnchecked;

        try {
            checked.run();
            throw new AssertionError("Thiếu IOException");
        } catch (IOException e) {
            if (!"expected".equals(e.getMessage())) {
                throw new AssertionError("Sai I/O message");
            }
            System.out.println("PASS checked");
        }

        try {
            unchecked.run();
            throw new AssertionError("Thiếu unchecked");
        } catch (IllegalStateException e) {
            if (!"unchecked".equals(e.getMessage())) {
                throw new AssertionError("Sai unchecked message");
            }
            System.out.println("PASS unchecked");
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 MethodReferenceAssertionsDemo.java
java MethodReferenceAssertionsDemo
```

**Stdout chính xác**:

```text
PASS checked
PASS unchecked
```

Bài test dùng `AssertionError` để chủ động thất bại khi kết quả sai, không phụ thuộc tùy chọn `-ea` của từ khóa `assert`. Kiểm thử compile-negative như `Runnable r = SomeClass::checkedMethod;` nên được tách trong một file/dự án test riêng **và được kỳ vọng không biên dịch**, không trộn cùng file chương trình runnable ở trên.

## 31. Các thông báo lỗi biên dịch thường gặp

| Triệu chứng | Nguyên nhân cần xét | Hướng xử lý |
| --- | --- | --- |
| `incompatible thrown types IOException in functional expression` | Method ref có checked `IOException`; SAM không cho phép | Chọn SAM có `throws IOException` hoặc adapter/lambda bắt phù hợp |
| `unreported exception IOException; must be caught or declared` | Gọi SAM/khối lambda có checked exception chưa xử lý | Bắt tại điểm gọi hoặc khai báo trên phương thức bao ngoài |
| `invalid method reference` | Có thể sai tham số/kiểu trả về hoặc checked exception | Kiểm tra toàn bộ chữ ký, không chỉ `throws` |
| `unexpected instance method ... found in unbound lookup` | Sai cách bound/unbound receiver | Dùng `object::method`, `Type::method` hoặc lambda hợp số tham số |
| `reference to method is ambiguous` | Quá tải, kiểu tham số hoặc target type không đủ rõ | Làm rõ target type, thay reference bằng lambda có kiểu tham số tường minh nếu cần |
| `bad return type in method reference` | SAM cần kiểu trả về không thể thích nghi từ method đích | Chọn target phù hợp hoặc lambda chuyển đổi |
| `Exception is never thrown in body of corresponding try statement` | Handler bắt checked exception ở chỗ không có lời gọi tương ứng | Bắt ở đúng nơi gọi SAM hoặc sửa loại handler |
| `cannot infer type-variable(s)` | Interface generic hoặc method generic không suy luận được | Chỉ rõ tham số kiểu/target type; đảm bảo exception type tương thích |

**Thông báo lỗi nguyên văn phụ thuộc compiler/JDK.** Bảng giúp nhận biết nhóm vấn đề, không phải danh sách chuỗi lỗi ổn định cần dùng trong tool tự động.

Một lỗi ở method reference **không nhất thiết** do `throws`; nếu method có checked exception nhưng số tham số sai, sửa `throws` cũng chưa đủ.

## 32. Sai lầm hiểu biết phổ biến

### 32.1. “Dùng `::` tự biến checked exception thành unchecked.”

Sai. Method reference không tạo wrapper exception. Nếu muốn đổi hợp đồng, bạn phải triển khai adapter/lambda có chính sách rõ ràng.

### 32.2. “Target `Runnable` sẽ nuốt mọi exception.”

Sai. `Runnable.run` không cho checked exception ở compile time, nhưng unchecked exceptions vẫn có thể thoát ra khi thực thi.

### 32.3. “`Callable` nghĩa là mọi checked exception sẽ được tự bắt.”

Sai. `Callable.call() throws Exception` cho phép lỗi thoát; caller hoặc framework thực thi vẫn phải chịu trách nhiệm theo hợp đồng.

### 32.4. “Compiler nhìn thân method nên biết dù `throws Exception` chỉ ném `IOException`.”

Không theo cách đó ở điểm sử dụng thông thường. Chữ ký tĩnh rộng là hợp đồng cần được tôn trọng.

### 32.5. “Bọc dòng `Supplier s = X::read` trong `try/catch` sẽ hợp lệ.”

Không. Handler quanh dòng gán không thay đổi `Supplier.get()` để cho phép checked `IOException`.

### 32.6. “Một method reference sai chỉ vì `throws`.”

Không nhất thiết. Sai receiver, số tham số, overload và kiểu trả về cũng gây lỗi.

### 32.7. “Khai báo SAM `throws IOException` thì implementation bắt buộc phải ném IOException.”

Sai. Một implementation không ném checked exception vẫn tương thích; caller nhìn qua SAM vẫn phải đáp ứng chữ ký đó.

### 32.8. “Method reference tự gọi method ngay khi gán.”

Sai trong trường hợp thông thường. Reference được tạo để gọi về sau; bound reference với receiver null có quy tắc kiểm tra lúc đánh giá nhưng không phải lời gọi nghiệp vụ.

### 32.9. “Checked exception từ method đích có thể bị bỏ qua khi nằm trong Stream API.”

Sai. `Function`/`Consumer` không cho checked exception; cần chọn hợp đồng khác hoặc xử lý/chuyển lỗi.

### 32.10. “Mỗi callback cần `throws Exception` thật rộng.”

Không. Khi có thể, giữ tập exception hẹp giúp người gọi hiểu và xử lý API. Nếu chỉ có một loại I/O, `IoSupplier<T>` có `throws IOException` thường rõ hơn một interface với `throws Exception`.

### 32.11. “Unchecked exception có nghĩa lỗi không quan trọng.”

Sai. Unchecked chỉ là phân loại cho catch-or-declare; hệ thống vẫn phải quản lý trạng thái và lỗi theo hợp đồng.

### 32.12. “Overload theo `throws` là hợp lệ.”

Sai. Không tạo hai method có cùng chữ ký chỉ khác danh sách checked exceptions.

## 33. Câu hỏi tự kiểm tra

**Câu 1.** Phương thức `static void load() throws IOException` có gán trực tiếp vào `Runnable` bằng method reference không?  
**Đáp án:** Không. `Runnable.run()` không cho phép checked `IOException`.

**Câu 2.** Có thể gán `load` vào `CheckedAction.run() throws IOException` không?  
**Đáp án:** Có, nếu tham số và kiểu trả về cũng tương thích.

**Câu 3.** `Callable<String> task = Source::read` có hợp lệ nếu `read() throws IOException` và trả `String` không?  
**Đáp án:** Có. `IOException` là subtype của `Exception`, được `Callable.call()` cho phép.

**Câu 4.** Khi gọi `task.call()` qua `Callable<String>`, caller cần xét kiểu checked nào?  
**Đáp án:** Theo hợp đồng tĩnh `Callable.call() throws Exception`, caller phải catch/declare `Exception` (hoặc xử lý phù hợp).

**Câu 5.** `String::length` gán vào `Supplier<Integer>` có hợp lệ không?  
**Đáp án:** Không. Unbound reference cần receiver `String` như tham số SAM; `Supplier.get()` không có tham số.

**Câu 6.** `String::length` gán vào `Function<String,Integer>` có hợp lệ không?  
**Đáp án:** Có. Receiver `String` là đầu vào, kết quả `int` có thể boxed thành `Integer`.

**Câu 7.** Method `throws FileNotFoundException` có phù hợp với SAM `throws IOException` không?  
**Đáp án:** Có; `FileNotFoundException` là lớp con của `IOException`.

**Câu 8.** Method `throws Exception` có phù hợp SAM chỉ `throws IOException` không?  
**Đáp án:** Không, vì `Exception` rộng hơn `IOException`.

**Câu 9.** Constructor `Resource(String) throws IOException` có gán trực tiếp `Resource::new` vào `Function<String,Resource>` không?  
**Đáp án:** Không. `Function.apply` không cho checked `IOException`.

**Câu 10.** Method reference tới method có hai checked exception `IOException` và `SQLException` có phù hợp SAM chỉ `throws IOException` không?  
**Đáp án:** Không. `SQLException` không thuộc `IOException`.

**Câu 11.** Method reference tới method có thể ném `IllegalStateException` có được dùng với `Runnable` không?  
**Đáp án:** Có, nếu những yếu tố chữ ký khác khớp; unchecked exception không phải khai báo checked.

**Câu 12.** Nếu method reference bị compiler từ chối với `Supplier`, bọc dòng gán trong `try/catch(IOException)` có sửa được không?  
**Đáp án:** Không. `Supplier.get` vẫn không khai báo checked exception.

**Câu 13.** Khi nào dùng lambda thay vì method reference để xử lý checked exception?  
**Đáp án:** Khi cần `try/catch`, fallback, đổi lỗi có cause, truyền tham số bổ sung hoặc logic kết hợp mà `::` không diễn đạt trực tiếp.

**Câu 14.** Vì sao `try/catch` trong lambda có thể giúp dùng `Supplier`?  
**Đáp án:** Vì lambda có thể xử lý hoặc chuyển checked exception để không còn checked exception bị phép tính SAM ném ra ngoài.

**Câu 15.** `@FunctionalInterface interface Task { void run() throws IOException; }` có yêu cầu mọi implementation thực sự ném IOException không?  
**Đáp án:** Không. `throws` cho phép, không bắt buộc phải ném.

**Câu 16.** Có thể overload hai method chỉ khác `throws IOException` và `throws SQLException` không?  
**Đáp án:** Không. Danh sách `throws` không tham gia tạo chữ ký overload khác nhau.

**Câu 17.** Một reference `repo::fetch` với biến kiểu `Repository` công bố `throws IOException` có được kiểm tra khác với biến kiểu implementation override không khai báo checked lỗi không?  
**Đáp án:** Có thể khác vì kiểu tĩnh của receiver quyết định method được nhìn thấy và hợp đồng checked exception ở điểm tham chiếu.

**Câu 18.** Dùng adapter `UncheckedIOException` có còn là checked I/O đối với caller `Function` không?  
**Đáp án:** Không ở mặt chữ ký; `UncheckedIOException` là unchecked, nhưng `getCause()` vẫn giữ `IOException` gốc và caller/framework phải quyết định xử lý.

**Câu 19.** `Stream.map(Files::readString)` với `Stream<Path>` có trực tiếp hợp lệ không?  
**Đáp án:** Không, vì `Files.readString` có checked `IOException` trong khi `Function` của `map` không cho phép checked exception.

**Câu 20.** Lỗi `NullPointerException` do receiver null khi đánh giá bound method reference có yêu cầu thêm `throws` không?  
**Đáp án:** Không. Đây là unchecked exception, khác với các checked exception mà method đích có thể ném khi SAM được gọi.

## 34. Checklist khi review method reference có `throws`

Trước khi gán `Type::method` hoặc `object::method` vào functional interface, hãy kiểm tra:

1. **Target functional interface là gì?** Xác định chính xác SAM và chữ ký của nó.
2. **SAM có `throws` nào?** `Runnable`/`Function` không giống `Callable` hoặc custom interface.
3. **Phương thức được tham chiếu có checked exceptions nào theo kiểu tĩnh?** Đọc chữ ký đã chọn, không đoán từ một lần chạy.
4. **Tất cả checked exceptions có được target cho phép không?** Xét quan hệ subtype/supertype.
5. **Có nhiều checked exceptions không?** Đừng bỏ sót loại thứ hai chỉ vì loại thứ nhất đã khớp.
6. **Method reference thuộc dạng nào?** Static, bound, unbound hay constructor.
7. **Số tham số, receiver và kiểu trả về khớp chưa?** Không chỉ xét `throws`.
8. **Có overloaded methods không?** Đảm bảo target type đủ rõ để chọn overload.
9. **Có generic type parameter về exception không?** Xác định type argument `E` phù hợp, tránh fallback sang `Exception` quá rộng nếu không cần.
10. **Nếu đang dùng Stream/Function/Consumer, có cần adapter không?** Không tự nuốt lỗi hoặc làm giả thành công.
11. **Adapter có giữ `cause` khi chuyển sang unchecked không?** Nên dùng wrapper có nguyên nhân phù hợp.
12. **Tầng nào xử lý lỗi cuối?** Caller, controller, job runner hay framework.
13. **Có `InterruptedException` không?** Tôn trọng ngữ nghĩa ngắt/hủy.
14. **Có nguy cơ receiver `null` với bound reference không?** Đánh giá tại thời điểm tạo reference.
15. **Lỗi có được kiểm thử runtime bằng cách gọi SAM không?** Việc gán thành công không chứng minh hành vi thành công.
16. **Có test compile-negative cho những phép gán bị cấm không?** Tách khỏi ví dụ runnable để tránh phá build.
17. **Tài liệu API có nói rõ checked/unchecked và ý nghĩa lỗi không?** Không chỉ dựa vào tên interface.
18. **Có đang tạo interface mới chỉ để tránh một lỗi compile cục bộ không?** Hãy cân nhắc hợp đồng dài hạn trước khi mở rộng API.

## 35. Tổng kết

**Method reference phải tương thích với `throws` của functional interface đích**, không chỉ với danh sách tham số và kiểu trả về. Một method khai báo `throws IOException` có thể được tham chiếu qua `IoSupplier<T>` có `get() throws IOException` hoặc qua `Callable<T>` có `call() throws Exception`, nhưng không trực tiếp qua `Supplier<T>`, `Function<T,R>` hay `Runnable` vốn không khai báo checked exception.

Điểm kiểm tra thực tế là **chữ ký của method/SAM theo kiểu tĩnh**. Java không tự catch, retry hay chuyển checked exception khi thấy `::`. Bound, unbound, static và constructor reference đều phải tuân thủ luật này; method overload và generic type inference có thể làm bước lựa chọn phức tạp hơn.

Khi API chuẩn không cho checked exception, các lựa chọn đúng là: **định nghĩa callback có `throws` phù hợp, bắt và xử lý trong lambda, đổi sang unchecked wrapper có `cause` theo hợp đồng, hoặc dùng kiểu kết quả có trạng thái**. Không nuốt lỗi chỉ để compile và không ép `throws Exception` rộng nếu caller cần hợp đồng cụ thể.

Ghi nhớ ngắn nhất: **“`::` thay đổi cách diễn đạt lời gọi, không thay đổi luật checked exceptions của Java.”**
