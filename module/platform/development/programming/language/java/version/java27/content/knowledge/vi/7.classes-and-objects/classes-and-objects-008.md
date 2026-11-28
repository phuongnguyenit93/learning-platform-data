# Lớp lồng nhau, lớp cục bộ và lớp ẩn danh trong Java 27

Trong chương **Lớp và đối tượng**, một câu hỏi thường gặp là: khi một kiểu chỉ phục vụ cho một lớp hoặc một phương thức, có nhất thiết phải khai báo nó thành một lớp riêng ở cấp package hay không? Java cho phép định nghĩa lớp bên trong lớp khác hoặc ngay trong một khối lệnh. Nhờ vậy, ta có thể đặt một kiểu gần nơi nó được sử dụng, giới hạn phạm vi truy cập và tổ chức mã theo quan hệ giữa các thành phần.

Trong Java 27, các hình thức quan trọng gồm **lớp thành viên `static` (static nested class)**, **lớp thành viên không `static` (inner member class)**, **lớp cục bộ (local class)** và **lớp ẩn danh (anonymous class)**. Chúng khác nhau ở tên, vị trí khai báo, phạm vi truy cập, sự gắn kết với đối tượng bao ngoài và cách khởi tạo.

Bài viết tập trung vào các quy tắc vẫn áp dụng trong Java 27. Một số hướng dẫn cũ nói rằng inner class không được khai báo thành viên `static`; hạn chế đó đã thay đổi từ Java 16. Khi tra cứu, nên đối chiếu **Java Language Specification (JLS) phiên bản hiện hành** thay vì dựa vào các bài viết dành riêng cho Java 8.

## 1. Tổng quan và thuật ngữ

Một **nested class** là lớp được khai báo bên trong phần thân của một lớp hoặc interface khác. Theo JLS, nested class có thể là lớp thành viên, lớp cục bộ hoặc lớp ẩn danh. Thuật ngữ **inner class** chỉ những nested class không được khai báo `static` một cách tường minh hay ngầm định.

```java
class Workspace {
    static class Config { }  // static nested member class

    class Session { }        // inner member class

    void execute() {
        class LocalTask { }  // local class

        Runnable task = new Runnable() { // anonymous class
            @Override
            public void run() {
                System.out.println("Running");
            }
        };

        task.run();
    }
}
```

| Loại | Có tên riêng? | Vị trí khai báo | Gắn ngầm với instance bao ngoài? |
| --- | --- | --- | --- |
| Static nested member class | Có | Thân lớp hoặc interface | Không |
| Inner member class | Có | Thân lớp, không `static` | Có, khi được tạo với instance bao ngoài |
| Local normal class | Có | Khối lệnh, chẳng hạn thân phương thức | Tùy ngữ cảnh tạo; không có enclosing instance khi khai báo trong static context |
| Anonymous class | Không có tên khai báo | Biểu thức `new ... { ... }` | Tùy ngữ cảnh tạo; không có enclosing instance khi ở static context |

Một nested `record`, `enum`, hoặc lớp thành viên được khai báo trong interface có tính chất **ngầm định `static`** theo các quy tắc tương ứng. Đừng đồng nhất tất cả các loại lớp đặt bên trong lớp khác với inner class.

### Quan hệ giữa các loại

```text
Nested class
├── Member class
│   ├── Static nested member class
│   └── Non-static member class (inner)
├── Local class
│   ├── Local normal class (inner)
│   ├── Local record (implicitly static)
│   └── Local enum (implicitly static)
└── Anonymous class (inner)
```

Trong Java 27 còn có thể khai báo **local interface** trong một khối lệnh; local interface ngầm định `static` và không phải một inner class. Phần tiếp theo đi sâu vào bốn hình thức lớp thường gặp trong thiết kế ứng dụng.

## 2. Static nested class: nhóm kiểu hỗ trợ cùng lớp bao ngoài

Một lớp thành viên khai báo với `static` là thành viên của kiểu bao ngoài. Nó **không tự giữ một tham chiếu đến đối tượng bao ngoài**. Có thể tạo đối tượng của nó mà không cần khởi tạo đối tượng lớp bao ngoài trước.

```java
public class ApiClient {
    private final String baseUrl;

    public ApiClient(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public static class Options {
        private final int timeoutMillis;

        public Options(int timeoutMillis) {
            if (timeoutMillis <= 0) {
                throw new IllegalArgumentException("Timeout must be positive");
            }
            this.timeoutMillis = timeoutMillis;
        }

        public int timeoutMillis() {
            return timeoutMillis;
        }
    }

    public String baseUrl() {
        return baseUrl;
    }
}
```

Cách sử dụng:

```java
ApiClient.Options options = new ApiClient.Options(5_000);
System.out.println(options.timeoutMillis()); // 5000
```

Không có lệnh `new ApiClient(...)` nào cần được thực thi chỉ để tạo `Options`. Tên kiểu đầy đủ trong mã nguồn là `ApiClient.Options`. Trong phạm vi có thể truy cập, nested class tuân theo các quy tắc access modifier (`private`, `protected`, package-private, `public`) như các thành viên khác của lớp.

### 2.1. Truy cập trạng thái bao ngoài

Lớp `static` lồng nhau có thể truy cập thành viên `static` của lớp bao ngoài trực tiếp và thành viên instance khi có một tham chiếu đến instance cụ thể. Mức truy cập `private` không ngăn hai lớp thuộc cùng nest truy cập thành viên của nhau theo quy tắc ngôn ngữ.

```java
class Order {
    private final int total;
    private static final int DEFAULT_FEE = 10;

    Order(int total) {
        this.total = total;
    }

    static class Calculator {
        int totalWithFee(Order order) {
            return Math.addExact(order.total, DEFAULT_FEE);
        }
    }
}
```

Ở đây, `Calculator` truy cập `order.total` qua một đối tượng `Order` được truyền vào. Viết `return total + DEFAULT_FEE` trong phương thức của `Calculator` sẽ không hợp lệ vì không có đối tượng `Order` ngầm định để lấy `total`.

### 2.2. Khi nào nên dùng?

Static nested class phù hợp khi kiểu hỗ trợ có quan hệ chặt với lớp bao ngoài nhưng không cần sống cùng một instance cụ thể, ví dụ:

- `Request.Options` để mô tả cấu hình request.
- `Graph.Node` khi node là chi tiết triển khai của một cấu trúc dữ liệu.
- Lớp kết quả hoặc helper chỉ phục vụ một abstraction và cần giới hạn khả năng truy cập từ bên ngoài.

Nếu kiểu không cần trạng thái của instance bao ngoài, `static nested class` thường là lựa chọn mặc định rõ ràng hơn inner member class.

## 3. Inner member class: gắn với một instance bao ngoài

Inner member class là lớp thành viên **không khai báo `static`**. Khi khởi tạo, đối tượng inner member class có một enclosing instance tương ứng. Nhờ đó, mã trong inner class có thể truy cập thành viên instance của đối tượng bao ngoài, kể cả `private`, khi các quy tắc phạm vi cho phép.

Ví dụ một playlist có đối tượng con theo dõi vị trí đọc:

```java
import java.util.List;

public class Playlist {
    private final List<String> tracks;

    public Playlist(List<String> tracks) {
        this.tracks = List.copyOf(tracks);
    }

    public class Cursor {
        private int position;

        public boolean hasNext() {
            return position < tracks.size();
        }

        public String next() {
            if (!hasNext()) {
                throw new java.util.NoSuchElementException();
            }
            return tracks.get(position++);
        }
    }

    public Cursor cursor() {
        return new Cursor();
    }
}
```

Cách sử dụng:

```java
Playlist playlist = new Playlist(List.of("Track A", "Track B"));

Playlist.Cursor first = playlist.new Cursor();
Playlist.Cursor second = playlist.cursor();

System.out.println(first.next());  // Track A
System.out.println(second.next()); // Track A
```

Hai đối tượng `Cursor` có vị trí `position` riêng nhưng cùng gắn với một playlist. Trong `Cursor`, biểu thức `tracks.size()` được phân giải đến trạng thái `tracks` của enclosing `Playlist`.

### 3.1. Cú pháp tạo inner member class

Từ bên ngoài lớp bao ngoài, cần có một instance để gọi `new` theo cú pháp:

```java
Playlist outer = new Playlist(List.of("A"));
Playlist.Cursor cursor = outer.new Cursor();
```

Bên trong phương thức instance của `Playlist`, có thể viết `new Cursor()` vì đã có enclosing instance là `this`. Trong một phương thức `static`, không có enclosing instance ngầm định; cần lấy hoặc tạo một đối tượng `Playlist` để khởi tạo `Cursor`.

Không thể viết `new Playlist.Cursor()` như cách tạo static nested class. Đó là lỗi biên dịch vì một `Cursor` cần được liên kết với một `Playlist` cụ thể.

### 3.2. `this` và `Outer.this`

Trong inner class, `this` chỉ **đối tượng inner hiện tại**. Muốn nêu rõ đối tượng bao ngoài, dùng `OuterClass.this`:

```java
class Counter {
    private int value = 10;

    class View {
        private int value = 1;

        void print() {
            System.out.println(this.value);         // 1, của View
            System.out.println(Counter.this.value); // 10, của Counter
        }
    }
}
```

`Counter.this` chỉ hợp lệ khi tại vị trí đó thực sự có enclosing instance `Counter`. Trong static nested class, không có `Counter.this` ngầm định.

### 3.3. Vòng đời và giữ tham chiếu

Inner member class có liên hệ với đối tượng bao ngoài. Nếu một đối tượng inner được đưa vào cache, callback hoặc queue tồn tại lâu, nó có thể đồng thời giữ cho đối tượng bao ngoài còn reachable và chưa được thu hồi. Điều này cần được cân nhắc khi inner class nắm giữ những đối tượng lớn hoặc tài nguyên có vòng đời ngắn.

Không phải tình huống nào cũng là memory leak: giữ đối tượng bao ngoài có thể chính là hành vi cần thiết. Nhưng nếu inner class chỉ cần một dữ liệu nhỏ, hãy cân nhắc static nested class và truyền đúng dữ liệu đó qua constructor.

## 4. Lớp lồng nhau và generic

Một inner member class có thể tham chiếu đến type parameter của lớp bao ngoài. Static nested class không thể dùng trực tiếp type parameter thuộc instance của lớp bao ngoài vì nó không phụ thuộc vào một cách tham số hóa cụ thể của enclosing class.

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    class View {
        T read() {
            return value;
        }
    }

    static class Metadata<U> {
        private final U tag;

        Metadata(U tag) {
            this.tag = tag;
        }

        U tag() {
            return tag;
        }
    }
}
```

Sử dụng:

```java
Box<String> box = new Box<>("Java 27");
Box<String>.View view = box.new View();
System.out.println(view.read()); // Java 27

Box.Metadata<Integer> metadata = new Box.Metadata<>(27);
System.out.println(metadata.tag()); // 27
```

`View` gắn với `Box<String>` cụ thể nên có thể trả `T` (`String` trong ví dụ). `Metadata<U>` khai báo type parameter `U` riêng; không dùng trực tiếp `T` của `Box<T>`.

## 5. Local class: lớp có tên chỉ dùng trong một khối lệnh

**Local class** được khai báo ngay trong một block, thường là thân phương thức, constructor hoặc initializer. Local normal class có tên nhưng phạm vi sử dụng của tên đó chỉ nằm trong block theo quy tắc scope. Local class hữu ích khi một thao tác cần một đối tượng có trạng thái, nhiều phương thức hoặc constructor riêng, nhưng kiểu triển khai không cần xuất hiện như một member class của lớp lớn.

```java
public class ReportService {
    interface Formatter {
        String format(int number);
    }

    static Formatter withPrefix(String prefix) {
        String normalized = prefix.strip();

        class PrefixFormatter implements Formatter {
            private int calls;

            @Override
            public String format(int number) {
                calls++;
                return normalized + " #" + calls + ": " + number;
            }
        }

        return new PrefixFormatter();
    }

    public static void main(String[] args) {
        Formatter formatter = withPrefix("  Score  ");
        System.out.println(formatter.format(10)); // Score #1: 10
        System.out.println(formatter.format(20)); // Score #2: 20
    }
}
```

`PrefixFormatter` chỉ có tên ở trong phương thức `withPrefix`. Sau khi phương thức trả về, đối tượng vẫn có thể tiếp tục tồn tại vì kết quả được giữ trong biến kiểu `Formatter`. Việc kiểu triển khai có phạm vi tên cục bộ **không giới hạn vòng đời của đối tượng** vào thời điểm thực thi phương thức.

### 5.1. Phạm vi và giới hạn khai báo

Tên local class chỉ nằm trong phạm vi được JLS quy định, bắt đầu từ vị trí khai báo và kéo dài trong block tương ứng. Không thể tham chiếu `PrefixFormatter` trực tiếp từ `main` trong ví dụ trên.

Local class không được khai báo với modifier truy cập `public`, `protected`, `private`, cũng không được viết `static` trên chính khai báo local class. Theo Java 27, local class/interface cũng không được khai báo `sealed` hoặc `non-sealed`. Có thể dùng `final` hay `abstract` cho local normal class khi phù hợp.

Ví dụ không hợp lệ:

```java
void method() {
    // private class Helper {} // Sai: local class không có access modifier
    // static class Helper {}  // Sai: không khai báo local class là static
}
```

Local class **khác** static nested member class ở vị trí khai báo: `static class Helper` là cú pháp của lớp thành viên trong một lớp bao ngoài, không phải khai báo lớp cục bộ trong phương thức.

### 5.2. Truy cập biến cục bộ: `final` hoặc effectively final

Local class có thể đọc biến cục bộ và tham số từ phạm vi bao quanh khi những biến đó là `final` hoặc **effectively final** (không bị gán lại sau khi đã được khởi tạo theo quy tắc ngôn ngữ).

```java
static Runnable buildTask(String message) {
    String prefix = "INFO";

    class MessageTask implements Runnable {
        @Override
        public void run() {
            System.out.println(prefix + ": " + message);
        }
    }

    return new MessageTask();
}
```

Ở đây, `prefix` và tham số `message` đều không bị gán lại. Vì vậy chúng được phép được local class sử dụng. Nếu thêm `prefix = "DEBUG";` trong cùng phương thức sau khi khởi tạo, `prefix` không còn effectively final và đoạn local class tham chiếu nó sẽ gây lỗi biên dịch.

Quy tắc áp dụng cho **biến tham chiếu**, không biến đối tượng thành immutable. Ví dụ:

```java
static Runnable taskWithBuffer() {
    var messages = new java.util.ArrayList<String>();

    class Task implements Runnable {
        @Override
        public void run() {
            messages.add("Executed"); // Hợp lệ: không gán lại messages
        }
    }

    return new Task();
}
```

`messages` vẫn effectively final vì không có phép gán tham chiếu mới cho biến. Đối tượng `ArrayList` mà nó trỏ tới vẫn có thể thay đổi. Nếu task chạy đồng thời trên nhiều thread, việc dùng collection mutable còn đòi hỏi thiết kế đồng bộ phù hợp; quy tắc effectively final tự nó không bảo đảm thread safety.

### 5.3. Local class trong static context

Local normal class cũng có thể được khai báo bên trong phương thức `static` như ví dụ `withPrefix`. Khi đó, lớp được khai báo không có enclosing instance của lớp bao ngoài tại vị trí đó. Nó vẫn có thể capture các biến cục bộ effectively final.

```java
class Processor {
    private int instanceValue = 7;

    static Runnable create() {
        int localValue = 3;

        class Task implements Runnable {
            @Override
            public void run() {
                System.out.println(localValue); // Hợp lệ
                // System.out.println(instanceValue); // Sai: thiếu Processor instance
            }
        }

        return new Task();
    }
}
```

Không nên suy rằng mọi local class đều tự giữ đối tượng bao ngoài. Cần xem nó được khai báo và khởi tạo trong instance context hay static context.

### 5.4. Local record, enum và interface trong Java 27

Java còn hỗ trợ record, enum và normal interface được khai báo cục bộ. **Local record, local enum và local interface có tính `static` ngầm định**. Vì thế, chúng không tự capture biến cục bộ như một local normal class.

```java
static void printResult(int quantity) {
    record Result(int quantity, boolean valid) { }

    Result result = new Result(quantity, quantity >= 0);
    System.out.println(result);
}
```

Giá trị `quantity` ở đây được **truyền tường minh vào constructor của record**. Phương thức được khai báo trong `Result` không thể tự đọc biến `quantity` bên ngoài bằng tên như local normal class capture biến. Khi chỉ cần một nhóm dữ liệu có tên và không cần trạng thái bao ngoài, local record là lựa chọn gọn và rõ nghĩa.

## 6. Anonymous class: khai báo kiểu và tạo đối tượng ngay tại chỗ

Anonymous class không có tên khai báo và được tạo bởi một biểu thức khởi tạo đối tượng kèm class body. Nó có thể **triển khai một interface** hoặc **mở rộng một class cho phép kế thừa**. Đây là một lớp thực sự có thể có field, phương thức và instance initializer.

### 6.1. Triển khai interface

```java
public class AnonymousTaskDemo {
    public static void main(String[] args) {
        Runnable task = new Runnable() {
            private int executions;

            @Override
            public void run() {
                executions++;
                System.out.println("Run #" + executions);
            }
        };

        task.run(); // Run #1
        task.run(); // Run #2
    }
}
```

`new Runnable() { ... }` không khởi tạo trực tiếp interface `Runnable`. Biểu thức này khai báo một **lớp vô danh mới triển khai `Runnable`** rồi tạo một instance của lớp đó. Mỗi lần biểu thức tạo đối tượng được đánh giá, nó tạo một instance mới với các field riêng.

### 6.2. Mở rộng lớp có constructor

Anonymous class cũng có thể kế thừa một class, truyền đối số cho constructor của class cha và override hành vi:

```java
abstract class Notification {
    protected final String channel;

    Notification(String channel) {
        this.channel = channel;
    }

    abstract void send(String message);
}

class NotificationDemo {
    public static void main(String[] args) {
        Notification notification = new Notification("console") {
            @Override
            void send(String message) {
                System.out.println(channel + ": " + message);
            }
        };

        notification.send("Java 27");
    }
}
```

Anonymous class **không được khai báo constructor có tên**. Java tạo anonymous constructor theo quy tắc ngôn ngữ, trong đó constructor của lớp cha được gọi với các đối số thích hợp. Nếu cần khởi tạo field riêng, có thể dùng field initializer hoặc instance initializer. Với logic khởi tạo phức tạp, một lớp có tên thường dễ bảo trì hơn.

Không thể tạo anonymous subclass trực tiếp của một class `final` hoặc `record` (record là final), hay khai báo anonymous implementation trực tiếp của một `sealed` interface có danh sách lớp triển khai cho phép. Quy tắc kế thừa và `permits` vẫn có hiệu lực.

### 6.3. Dùng phương thức của kiểu tham chiếu

Khi biến được khai báo bằng kiểu `Runnable`, chỉ các thành viên có thể truy cập từ kiểu đó mới gọi được thông qua biến, dù anonymous class có thêm field hoặc phương thức phụ:

```java
Runnable job = new Runnable() {
    private int count;

    @Override
    public void run() {
        count++;
    }

    private void reset() {
        count = 0;
    }
};

job.run();
// job.reset(); // Sai: Runnable không khai báo reset()
```

Nếu cần API bổ sung có thể gọi từ nơi khác, hãy tạo interface hoặc class có tên rõ ràng thay vì giấu phương thức công khai bên trong anonymous class.

## 7. Capturing biến và ngữ nghĩa của `this`

Anonymous class cũng tuân thủ quy tắc capture biến cục bộ và tham số: biến phải `final` hoặc effectively final. Nó có thể sử dụng các thành viên của enclosing instance khi được khai báo trong instance context.

```java
class Screen {
    private final String title = "Dashboard";

    Runnable createLogger(String prefix) {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(prefix + ": " + Screen.this.title);
            }
        };
    }
}
```

Trong đoạn trên, `prefix` được capture và `Screen.this` chỉ đối tượng `Screen` bao ngoài. Ở bên trong `run`, `this` nếu dùng đơn lẻ sẽ chỉ instance của **anonymous class**, không phải `Screen`.

Đặc điểm này khác với lambda. Một lambda expression **không tạo ngữ cảnh `this` mới**: nếu viết lambda trong phương thức instance của `Screen`, `this` bên trong lambda vẫn là `Screen`.

```java
class Screen {
    private final String title = "Dashboard";

    Runnable withLambda() {
        return () -> System.out.println(this.title);
    }

    Runnable withAnonymousClass() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(Screen.this.title);
            }
        };
    }
}
```

Trong cả hai trường hợp, callback có thể dùng dữ liệu của `Screen`. Tuy nhiên, cách phân giải `this` là khác nhau. Điều này đáng lưu ý khi chuyển một anonymous class sang lambda để làm gọn mã.

## 8. Anonymous class và lambda: chọn công cụ phù hợp

Lambda thường là cách ngắn gọn hơn để biểu diễn hành vi của **functional interface** (interface có đúng một abstract method theo quy tắc SAM), ví dụ `Runnable`, `Comparator<T>`, `Predicate<T>` hoặc `Function<T,R>`.

```java
Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println("Hello");
    }
};

Runnable lambda = () -> System.out.println("Hello");
```

Cả hai có thể được dùng như `Runnable`, nhưng chúng không hoàn toàn tương đương về mô hình ngôn ngữ. Anonymous class khai báo một lớp với instance riêng; lambda là một biểu thức dùng để cung cấp phần triển khai cho functional interface. Đừng dựa vào danh tính hay lớp runtime của đối tượng lambda để thiết kế giao thức ứng dụng.

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Triển khai nhanh một hành động của functional interface | Lambda hoặc method reference |
| Cần ghi đè nhiều phương thức của một abstract class/interface | Anonymous class hoặc lớp có tên |
| Cần field và trạng thái riêng gắn với implementation | Anonymous class hoặc lớp có tên |
| Cần constructor riêng, tái sử dụng hoặc nhiều vị trí tạo instance | Local/member/top-level class có tên |
| Cần `this` biểu diễn đối tượng triển khai callback riêng | Anonymous class |
| Cần `this` của enclosing instance trong một functional interface | Lambda thường trực tiếp hơn |

Một ví dụ với `Comparator`:

```java
import java.util.Comparator;

class ProductSorting {
    record Product(String name, int price) { }

    static final Comparator<Product> BY_PRICE =
        Comparator.comparingInt(Product::price);
}
```

Đây là phương án thường dễ đọc hơn anonymous class chỉ dùng để so sánh một thuộc tính. Không cần tạo lớp cục bộ hoặc anonymous class chỉ vì API nhận một functional interface.

Nếu hành vi đủ phức tạp để có nhiều field, nhiều nhánh, vòng đời riêng hoặc cần kiểm thử độc lập, hãy cân nhắc lớp có tên. Việc chọn kiểu triển khai phụ thuộc độ rõ nghĩa và khả năng bảo trì, không chỉ số dòng mã.

## 9. Quy tắc truy cập, scope và che khuất tên

Mã trong nested class có thể truy cập các thành viên `private` của lớp bao ngoài theo quy tắc truy cập của Java. Điều đó không có nghĩa mọi tên đều được nhìn thấy hoặc mọi biến đều có thể được capture; còn phải xét **scope**, static context, shadowing và các quy tắc definite assignment.

Ví dụ có ba biến cùng tên:

```java
class Container {
    private String name = "outer";

    class Item {
        private String name = "inner";

        void show(String name) {
            System.out.println(name);                // tham số
            System.out.println(this.name);           // field của Item
            System.out.println(Container.this.name); // field của Container
        }
    }
}
```

Để tránh nhầm lẫn, đặt tên thể hiện vai trò của biến; chỉ dùng `Outer.this` khi cần phân biệt với `this` của inner class. Một static nested class không có `Outer.this`, nên nếu cần truy cập một outer instance thì phải giữ hoặc nhận tham chiếu tường minh.

### Những điều không nên giả định

- Lớp lồng nhau có thể truy cập private member không có nghĩa kiểu đó luôn được phép sử dụng từ mọi package; bản thân nested type vẫn có access modifier.
- Một local class có tên không có nghĩa tên đó khả dụng ở ngoài block khai báo.
- Một anonymous class không có tên ở source không có nghĩa nó không phải là một lớp thực sự.
- Một biến được capture là effectively final không có nghĩa đối tượng mà biến đó trỏ đến cũng bất biến.
- Một inner class có thể khai báo thành viên `static` trong Java hiện đại; phân biệt **class không `static`** với **member `static` bên trong class**.

## 10. Thay đổi về thành viên `static` trong inner class

Theo JLS 27 §8.1.3, inner class được khai báo và kế thừa thành viên `static`, kể cả static initializer. Quy tắc cấm thành viên `static` không phải hằng trong inner class đã được loại bỏ kể từ Java SE 16.

```java
class Outer {
    class Inner {
        private static int created;

        Inner() {
            created++;
        }

        static int createdCount() {
            return created;
        }
    }
}
```

Đoạn mã trên hợp lệ trong Java 27. Tuy nhiên, các thành viên `static` của `Inner` vẫn không có một enclosing instance ngầm định. Điều này không biến `Inner` thành static nested class: **mỗi đối tượng `Inner` vẫn cần một `Outer` tương ứng khi được tạo**.

Nếu người học gặp bài viết nói rằng một inner class chỉ được khai báo `static final` constant, hãy kiểm tra phiên bản Java mà bài viết đang mô tả. Quy tắc đó không còn đúng với Java 27.

## 11. Lưu ý khi thiết kế callback và vòng đời đối tượng

Local class và anonymous class thường dùng làm callback, handler hoặc task. Khi một instance được đăng ký vào một service tồn tại lâu, hãy để ý những gì nó đang tham chiếu:

```java
class Controller {
    private final String id;

    Controller(String id) {
        this.id = id;
    }

    Runnable createHandler() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(Controller.this.id);
            }
        };
    }
}
```

Callback trên cần `Controller.this` nên có thể giữ `Controller` sống trong thời gian callback còn được giữ. Nếu callback được đăng ký mà không hủy đăng ký khi không còn cần, nó có thể kéo dài vòng đời các đối tượng liên quan. Với hệ thống xử lý event, hãy xác định lúc đăng ký, lúc đóng/hủy và trách nhiệm quản lý callback.

Nếu callback chỉ cần một giá trị bất biến, có thể dùng lambda hoặc static nested class và truyền giá trị rõ ràng:

```java
static Runnable handlerFor(String id) {
    return () -> System.out.println(id);
}
```

Biến `id` được capture; nếu đối tượng cần giữ ít dữ liệu hơn một enclosing controller, kiểu thiết kế này có thể đơn giản hơn. Tuy nhiên, ngay cả lambda cũng có thể giữ tham chiếu đến đối tượng được capture, nên vẫn cần xem xét vòng đời thực tế.

## 12. Ví dụ tổng hợp: ba kiểu triển khai cùng một yêu cầu

Giả sử ứng dụng cần tạo thao tác định dạng nhãn để in ra console. Ta có thể đặt helper thành static nested class, local class hoặc anonymous class. Ba cách dưới đây cùng triển khai `Runnable` nhưng thích hợp với phạm vi sử dụng khác nhau.

```java
public class LabelTasks {
    // Kiểu hỗ trợ có tên, dùng được ở nhiều phương thức của LabelTasks.
    private static final class PrintTask implements Runnable {
        private final String label;

        PrintTask(String label) {
            this.label = label;
        }

        @Override
        public void run() {
            System.out.println(label);
        }
    }

    static Runnable usingNestedClass(String label) {
        return new PrintTask(label);
    }

    static Runnable usingLocalClass(String label) {
        class LocalPrintTask implements Runnable {
            @Override
            public void run() {
                System.out.println(label);
            }
        }

        return new LocalPrintTask();
    }

    static Runnable usingAnonymousClass(String label) {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(label);
            }
        };
    }

    public static void main(String[] args) {
        usingNestedClass("Nested").run();
        usingLocalClass("Local").run();
        usingAnonymousClass("Anonymous").run();
    }
}
```

Kết quả:

```text
Nested
Local
Anonymous
```

Với trường hợp chỉ in một chuỗi, còn có cách ngắn hơn:

```java
static Runnable usingLambda(String label) {
    return () -> System.out.println(label);
}
```

Ví dụ tổng hợp cho thấy kiểu lồng nhau nên được chọn từ nhu cầu về tên, trạng thái, khả năng tái sử dụng và enclosing instance. Nếu chỉ truyền một hành động đơn giản vào API nhận functional interface, lambda thường dễ đọc nhất.

## 13. Lỗi thường gặp và cách xử lý

| Tình huống | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `new Outer.Inner()` không biên dịch | `Inner` là inner member class, cần outer instance | Dùng `outer.new Inner()` hoặc factory của `Outer` |
| Static nested class truy cập trực tiếp field instance của outer | Không có enclosing instance ngầm định | Truyền một outer instance vào method/constructor |
| Local/anonymous class tham chiếu biến cục bộ bị gán lại | Biến không `final` hoặc effectively final | Không gán lại biến capture; thiết kế trạng thái rõ ràng |
| Dùng `Outer.this` trong static context | Không có enclosing instance | Truyền tham chiếu một cách tường minh |
| Gọi phương thức riêng của anonymous class qua biến kiểu interface | Kiểu của biến không khai báo phương thức đó | Dùng interface/lớp có tên chứa contract phù hợp |
| Dùng anonymous class cho logic nhiều trạng thái, khó kiểm thử | Implementation bị giấu tại một biểu thức | Tách thành lớp có tên khi hành vi phức tạp |
| Callback giữ đối tượng bao ngoài quá lâu | Instance lưu giữ enclosing instance hoặc capture tham chiếu | Quản lý đăng ký/hủy callback; cân nhắc static nested class hoặc dữ liệu tối thiểu |
| Tưởng mọi inner class không được chứa thành viên `static` | Áp dụng quy tắc Java trước SE 16 | Dùng quy tắc JLS 27 hiện hành |
| Dùng local record để truy cập ngầm biến cục bộ | Local record ngầm định `static`, không capture biến cục bộ như local normal class | Truyền dữ liệu qua constructor record |
| Đặt class hỗ trợ rộng phạm vi hơn nhu cầu | Tăng khả năng phụ thuộc và làm rối API | Chọn phạm vi nhỏ nhất vẫn đủ rõ ràng và có thể bảo trì |

## 14. Hướng dẫn chọn loại lớp

Khi cần một kiểu bên trong lớp khác, có thể đặt các câu hỏi theo thứ tự:

1. **Kiểu có cần truy cập trạng thái của một enclosing instance cụ thể không?** Nếu có, inner member class là một lựa chọn tự nhiên. Nếu không, ưu tiên static nested member class khi kiểu được dùng ở nhiều phương thức.
2. **Kiểu chỉ cần trong một block và cần có tên, constructor hoặc nhiều phương thức?** Cân nhắc local class.
3. **Chỉ cần một implementation nhỏ tại đúng nơi dùng?** Anonymous class phù hợp khi cần state/override; nếu là một functional interface đơn giản, ưu tiên lambda hoặc method reference.
4. **Kiểu cần được tái sử dụng bởi nhiều phần khác nhau?** Xem xét member class hoặc top-level class tùy phạm vi API và trách nhiệm.
5. **Đối tượng có thể được giữ lâu hơn enclosing context không?** Xem xét những tham chiếu bị giữ lại, đặc biệt với callback và event listener.

Đặt tên và phạm vi phù hợp giúp tránh các class chỉ tồn tại vì thói quen tổ chức source. Một kiểu lồng nhau là chi tiết thiết kế, không phải cách thay thế bắt buộc cho top-level class hoặc lambda.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `Outer.Nested nested = new Outer.Nested()` hợp lệ với static nested class, còn `new Outer.Inner()` thường không hợp lệ với inner member class?

**Gợi ý:** Static nested class không cần enclosing instance; inner member class cần gắn với một instance của `Outer` khi khởi tạo.

**Câu 2.** Một local class được trả về dưới dạng interface có thể tiếp tục hoạt động sau khi phương thức tạo nó kết thúc không?

**Gợi ý:** Có. Giới hạn phạm vi của tên lớp khác với vòng đời của đối tượng. Giá trị capture có thể được giữ lại theo cơ chế của ngôn ngữ.

**Câu 3.** Vì sao một local class dùng được `final String prefix`, nhưng không dùng được biến `prefix` bị gán lại trong phương thức?

**Gợi ý:** Biến cục bộ được capture phải `final` hoặc effectively final.

**Câu 4.** Trong `new Runnable() { public void run() { ... } }`, `this` là đối tượng nào? So với `() -> { ... }` thì khác gì?

**Gợi ý:** Anonymous class có `this` riêng; lambda kế thừa ngữ cảnh `this` từ nơi khai báo.

**Câu 5.** Một inner class trong Java 27 có được khai báo phương thức `static` không?

**Gợi ý:** Có. Hãy dùng JLS 27 §8.1.3; hạn chế ở các bản Java cũ không còn áp dụng.

## Tài liệu tham khảo

- [Java Language Specification 27 — §8.1.3 Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se27/html/jls-8.html#jls-8.1.3)
- [Java Language Specification 27 — §8.5 Member Class and Interface Declarations](https://docs.oracle.com/javase/specs/jls/se27/html/jls-8.html#jls-8.5)
- [Java Language Specification 27 — §14.3 Local Class and Interface Declarations](https://docs.oracle.com/javase/specs/jls/se27/html/jls-14.html#jls-14.3)
- [Java Language Specification 27 — §15.9 Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se27/html/jls-15.html#jls-15.9)
- [Java Language Specification 27 — §15.9.5 Anonymous Class Declarations](https://docs.oracle.com/javase/specs/jls/se27/html/jls-15.html#jls-15.9.5)
- [Java Language Specification 27 — §15.27 Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se27/html/jls-15.html#jls-15.27)
- [Java Language Specification 27 — §6.3 Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se27/html/jls-6.html#jls-6.3)
