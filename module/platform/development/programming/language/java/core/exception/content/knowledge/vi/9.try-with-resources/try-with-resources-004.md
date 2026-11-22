# Dùng resource có sẵn là `final` hoặc *effectively final* từ Java 9

## 1. Mục tiêu học tập

`try-with-resources` là cú pháp Java giúp **tự động gọi `close()`** đối với các tài nguyên triển khai `AutoCloseable` khi rời phạm vi `try`. Từ Java 7, cấu trúc này đã hỗ trợ khai báo tài nguyên mới ngay trong dấu ngoặc của `try`. **Từ Java 9**, Java bổ sung cách tham chiếu trực tiếp đến **biến tài nguyên đã tồn tại**, miễn là biến đó là `final` hoặc *effectively final*.

Ví dụ trọng tâm:

```java
java.io.BufferedReader reader =
        new java.io.BufferedReader(new java.io.StringReader("hello"));

try (reader) { // Hợp lệ từ Java 9 nếu reader effectively final.
    System.out.println(reader.readLine());
}
```

Đây là **mảnh mã minh họa** đặt trong một phương thức khai báo hoặc xử lý `IOException`. Không cần khai báo lại `BufferedReader` trong dấu ngoặc và cũng không cần tạo biến alias chỉ để đưa vào `try-with-resources`.

Học xong bài này, bạn có thể:

- Viết đúng cú pháp `try (resource)`, `try (first; second)` và phối hợp resource đã có với khai báo resource mới.
- Phân biệt `final` tường minh và `effectively final`; biết các dạng gán lại gây lỗi biên dịch.
- Giải thích resource được đóng khi hoàn thành bình thường, `return` hoặc ném ngoại lệ, với thứ tự đóng ngược.
- Hiểu biến tài nguyên **vẫn ở trong scope** sau `try` nhưng đối tượng tài nguyên có thể đã đóng.
- Hiểu xử lý ngoại lệ của `close()`, đặc biệt là *suppressed exception*.
- Tránh đóng trùng, dùng lại resource đã đóng, chia sẻ sai quyền sở hữu và dùng nhầm biểu thức không phải variable access.
- Phân biệt chính xác Java 7/8 với cải tiến ngôn ngữ trong Java 9; chạy ví dụ trên JDK 17+.

## 2. Nhắc lại `try-with-resources` trước Java 9

`try-with-resources` ra đời từ **Java 7**. Khi đó, danh sách tài nguyên trong dấu ngoặc phải chứa **các khai báo biến tài nguyên**. Ví dụ:

```java
try (java.io.BufferedReader reader =
             new java.io.BufferedReader(new java.io.StringReader("A\nB"))) {
    System.out.println(reader.readLine());
}
```

Đây là **mảnh mã** ở trong một phương thức có thể xử lý hoặc khai báo `IOException`. Ở cuối khối, Java tự gọi `reader.close()`; bạn không cần thêm `finally { reader.close(); }`.

Yêu cầu về kiểu tài nguyên: biểu thức khai báo phải có kiểu tương thích với `java.lang.AutoCloseable`. Các lớp `Closeable` cũng phù hợp vì `java.io.Closeable` kế thừa `AutoCloseable`.

Trước Java 9, nếu biến đã khai báo từ **bên ngoài**:

```java
java.io.BufferedReader reader =
        new java.io.BufferedReader(new java.io.StringReader("A"));

try (java.io.BufferedReader managed = reader) {
    System.out.println(managed.readLine());
}
```

Java 7/8 cho phép dùng một **biến khai báo mới trong header** như `managed` để quản lý cùng đối tượng mà `reader` đang trỏ đến. Cơ chế này đúng nhưng tạo thêm tên biến và dễ khiến người đọc lầm rằng có hai reader độc lập. Trên thực tế, `managed` và `reader` là hai tham chiếu đến **cùng một đối tượng**; đối tượng ấy được đóng khi ra khỏi khối.

### Thay đổi trong Java 9

Java 9 chấp nhận **truy cập trực tiếp biến đã khai báo trước đó**:

```java
java.io.BufferedReader reader =
        new java.io.BufferedReader(new java.io.StringReader("A"));

try (reader) {
    System.out.println(reader.readLine());
}
```

Trong cú pháp mới, `reader` là một *variable access*, không phải khai báo resource mới. Điều kiện cốt lõi là **biến được truy cập phải `final` hoặc effectively final**, đã được gán giá trị phù hợp trước lúc vào `try` và có kiểu tài nguyên tương thích với `AutoCloseable`.

So sánh nhanh:

| Khía cạnh | Java 7/8 | Java 9+ |
| --- | --- | --- |
| Khai báo resource ngay tại header | `try (BufferedReader r = open())` | Vẫn hợp lệ |
| Dùng biến đã khai báo trước đó | Dùng alias: `try (BufferedReader managed = reader)` | `try (reader)` nếu đủ điều kiện |
| Cần viết `final` tường minh? | Không phải điều kiện của khai báo mới | Không, `effectively final` cũng được |
| Resource được đóng tự động? | Có | Có |
| Thứ tự đóng khi nhiều resource? | Đảo ngược thứ tự khai báo | Đảo ngược thứ tự liệt kê/quản lý |
| Xử lý lỗi `close()` và suppressed? | Có | Giữ nguyên |
| Biến khai báo bên ngoài còn trong scope sau `try`? | Có | Có |

**Quan trọng:** Java 9 **không** thay đổi điều kiện một tài nguyên cần hỗ trợ `AutoCloseable` hay quy tắc đóng. Điểm mới chỉ là cho phép một dạng biểu thức tham chiếu tới **biến tài nguyên đã có**.

## 3. `final` và *effectively final* nghĩa là gì?

### 3.1. Biến `final` tường minh

Một biến cục bộ khai báo bằng `final` không thể được gán lại sau khi đã được khởi tạo:

```java
final java.io.BufferedReader reader =
        new java.io.BufferedReader(new java.io.StringReader("input"));

try (reader) {
    System.out.println(reader.readLine());
}
```

Ví dụ là **mảnh mã** cần nằm trong phương thức xử lý hoặc khai báo `IOException`. Đây là cách dùng hợp lệ từ Java 9.

`final` áp dụng cho **biến tham chiếu**, không làm nội dung đối tượng trở thành bất biến. Trong khi tài nguyên đang mở, lời gọi `reader.readLine()` vẫn thay đổi vị trí đọc của reader; khi rời `try`, cơ chế ngôn ngữ vẫn gọi `close()`.

### 3.2. Biến *effectively final*

Biến cục bộ **không có từ khóa `final`** nhưng không bị gán lại sau lần khởi tạo hợp lệ được coi là *effectively final*:

```java
java.io.BufferedReader reader =
        new java.io.BufferedReader(new java.io.StringReader("input"));

// Không có câu lệnh reader = ... ở bất kỳ nơi nào sau đó.
try (reader) {
    System.out.println(reader.readLine());
}
```

Java 9+ chấp nhận đoạn này. Compiler xác định tính effectively final dựa trên **các phép gán trong mã**, không phải dựa trên nhận xét của lập trình viên hoặc việc dòng gán lại có thực sự chạy trong một bài test.

Một số điều cần phân biệt:

- Biến `reader` có thể chưa ghi `final` nhưng vẫn effectively final.
- Có thể **gọi phương thức làm thay đổi trạng thái đối tượng** qua `reader` mà không làm biến mất tính effectively final.
- Gán lại chính biến bằng `reader = anotherReader;` hoặc `reader = null;` khiến biến không còn effectively final.
- Điều kiện này xét trong phạm vi phù hợp của biến, **không chỉ các câu lệnh trước `try`**. Gán lại biến sau khi ra khỏi `try` cũng có thể khiến `try (reader)` bị compiler từ chối.
- Không nên đồng nhất effectively final với `AutoCloseable`, tính bất biến của đối tượng, hoặc thread-safety. Đây là những khái niệm độc lập.

### 3.3. Ví dụ cố ý không biên dịch: gán lại resource

Tệp **`InvalidReassignment.java`** dưới đây **chủ ý sai**:

```java
import java.io.StringReader;

public class InvalidReassignment {
    public static void main(String[] args) {
        StringReader reader = new StringReader("first");
        reader = new StringReader("second");

        try (reader) { // LỖI: reader không effectively final.
            System.out.println(reader.read());
        }
    }
}
```

Lệnh kiểm tra:

```bash
javac InvalidReassignment.java
```

Compiler từ chối vì biến được dùng làm resource **không phải final hoặc effectively final**. Thông báo cụ thể có thể thay đổi giữa phiên bản javac. Không chạy `java InvalidReassignment` như chương trình thành công vì mã chưa biên dịch được.

Trong chương trình thực tế, còn cần tránh tạo resource thứ nhất rồi **đánh mất tham chiếu để đóng nó** khi gán đè bằng resource thứ hai. Giải pháp không phải thêm `try (reader)` ở cuối, vì resource cũ đã không còn được quản lý. Hãy quản lý từng resource trong phạm vi phù hợp.

### 3.4. Gán lại sau `try` vẫn có thể làm mã không hợp lệ

Mảnh mã **cố ý sai**:

```java
java.io.StringReader reader = new java.io.StringReader("A");
try (reader) {
    System.out.println(reader.read());
}
reader = new java.io.StringReader("B"); // reader không effectively final.
```

Với cú pháp `try (reader)`, điều kiện effectively final áp dụng cho biến trong phạm vi của nó. Việc bạn gán lại ở **phía sau** khối không “khôi phục” tính hợp lệ.

Nếu cần tiếp tục dùng tên biến cho một resource mới, hãy dùng các biến khác nhau hoặc chia tách scope để đảm bảo rõ quyền sở hữu của từng resource.

## 4. Ví dụ chạy được: dùng biến đã có sau khi đóng resource

Tạo tệp **`ExistingResourceDemo.java`**:

```java
public class ExistingResourceDemo {
    static class TrackedResource implements AutoCloseable {
        private final String name;
        private boolean closed;

        TrackedResource(String name) {
            this.name = name;
        }

        void use() {
            if (closed) {
                throw new IllegalStateException("already closed");
            }
            System.out.println("using " + name);
        }

        boolean isClosed() {
            return closed;
        }

        @Override
        public void close() {
            closed = true;
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        TrackedResource resource = new TrackedResource("A");

        try (resource) {
            resource.use();
        }

        System.out.println("resource closed: " + resource.isClosed());
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac ExistingResourceDemo.java
java ExistingResourceDemo
```

`stdout`:

```text
using A
close A
resource closed: true
```

**Phân tích:**

1. `resource` được khai báo **trước** header `try`.
2. Biến không có từ khóa `final` nhưng được gán đúng một lần và không gán lại, nên effectively final.
3. `try (resource)` bắt đầu quản lý vòng đời resource hiện có; không tạo ra một đối tượng `TrackedResource` mới.
4. Khi phần thân hoàn thành bình thường, Java gọi `resource.close()`. Ví dụ in `close A`.
5. Biến `resource` còn trong scope sau `try`, nên vẫn có thể gọi `resource.isClosed()` và nhận `true`.

Điểm cuối rất quan trọng: **còn trong scope không có nghĩa còn mở**. Sau `try`, biến vẫn trỏ tới đối tượng cũ, nhưng đối tượng đã được đóng. Nếu gọi `resource.use()` một lần nữa thì sẽ nhận `IllegalStateException` theo hợp đồng tự định nghĩa của ví dụ.

### Trách nhiệm của người dùng tài nguyên

Khi bạn đưa một resource đã tồn tại vào `try (resource)`, bạn đang chấp nhận rằng **khối đó sẽ đóng resource**. Nếu resource được quản lý bởi thành phần khác và vẫn phải mở sau lời gọi, không thể tự ý dùng `try (resource)` mà bỏ qua hợp đồng sở hữu.

Thí dụ thực tế: không tùy tiện đóng một `InputStream` thuộc sở hữu của framework, của một HTTP request do container quản lý, hoặc một kết nối đang được chia sẻ theo lifecycle dài hơn phạm vi hiện tại.

## 5. Dùng biến `final` tường minh: ví dụ độc lập

Tạo tệp **`ExplicitFinalResourceDemo.java`**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;

public class ExplicitFinalResourceDemo {
    public static void main(String[] args) throws IOException {
        final BufferedReader reader =
                new BufferedReader(new StringReader("alpha\nbeta"));

        try (reader) {
            System.out.println(reader.readLine());
            System.out.println(reader.readLine());
        }

        System.out.println("finished reading");
    }
}
```

```bash
javac ExplicitFinalResourceDemo.java
java ExplicitFinalResourceDemo
```

`stdout`:

```text
alpha
beta
finished reading
```

`BufferedReader.readLine()` có khả năng ném `IOException`; thao tác `close()` cũng được quản lý tự động. `main throws IOException` thỏa kiểm tra checked exception. `StringReader` cho dữ liệu trong bộ nhớ để đầu ra ổn định, không phụ thuộc hệ thống tệp.

Biến `reader` vẫn tồn tại sau `try` nhưng reader đã bị đóng. Dòng `finished reading` không cố đọc lại resource. Đừng dùng việc biến vẫn tồn tại để suy ra có thể tiếp tục thực hiện I/O qua nó.

## 6. Nhiều resource có sẵn: thứ tự đóng từ phải sang trái

Khi quản lý nhiều resource trong một header, mỗi resource phải thỏa điều kiện kiểu và tính final/effectively final. Java đóng chúng theo **thứ tự ngược** với thứ tự khai báo hoặc liệt kê trong header.

Tạo tệp **`ExistingResourcesOrderDemo.java`**:

```java
public class ExistingResourcesOrderDemo {
    static class Tracked implements AutoCloseable {
        private final String name;

        Tracked(String name) {
            this.name = name;
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        Tracked first = new Tracked("first");
        final Tracked second = new Tracked("second");

        try (first; second) {
            System.out.println("body");
        }

        System.out.println("after try");
    }
}
```

```bash
javac ExistingResourcesOrderDemo.java
java ExistingResourcesOrderDemo
```

`stdout`:

```text
body
close second
close first
after try
```

Giải thích:

- `first` là effectively final; `second` là final tường minh.
- `try (first; second)` quản lý cả hai, dù đã được tạo **trước** câu lệnh `try`.
- Khi khối kết thúc, `close()` của `second` được gọi trước `close()` của `first`.
- Đây là quy tắc có ý nghĩa với tài nguyên phụ thuộc nhau: nếu `second` bọc `first`, hãy thiết kế quyền sở hữu và thứ tự đóng phù hợp.

Header cũng cho phép **dấu chấm phẩy cuối** tùy chọn; ví dụ `try (first; second;)` hợp lệ. Tuy vậy, dùng dấu chấm phẩy phân cách giữa các tài nguyên sẽ rõ nhất.

### Tạo resource trước khi vào `try` có rủi ro gì?

Xét:

```java
Resource first = openFirst();
Resource second = openSecond(); // Có thể thất bại.
try (first; second) {
    work();
}
```

Đây là **mảnh minh họa**, không phải chương trình độc lập; các kiểu/hàm chưa khai báo. Nếu `openSecond()` ném ngoại lệ trước khi thực thi `try`, chương trình **chưa đi vào phạm vi quản lý tài nguyên của try-with-resources**. `first` có thể vẫn còn mở và cần được xử lý bởi một phạm vi quản lý bên ngoài.

Đây là nhược điểm đáng cân nhắc khi tạo nhiều resource trước header. Cách an toàn phổ biến là khai báo tài nguyên trực tiếp trong một `try-with-resources`:

```java
try (Resource first = openFirst();
     Resource second = openSecond()) {
    work();
}
```

Đây cũng là **mảnh minh họa** cần khai báo `Resource` và các phương thức tương ứng. Khi `openSecond()` thất bại **trong quá trình khởi tạo các resource của header**, Java tự đóng resource `first` đã được khởi tạo và quản lý thành công trước đó.

**Kết luận:** cú pháp ngắn hơn của Java 9 không có nghĩa nó luôn tốt hơn khai báo resource tại header. Cần xét **thời điểm resource được tạo** và **phạm vi chịu trách nhiệm đóng**.

## 7. Kết hợp resource có sẵn với resource khai báo ngay trong header

Java 9+ có thể kết hợp hai kiểu phần tử trong danh sách resource:

```java
java.io.StringReader source = new java.io.StringReader("first\nsecond");

try (source;
     java.io.BufferedReader buffered =
             new java.io.BufferedReader(source)) {
    System.out.println(buffered.readLine());
}
```

Đây là **mảnh mã** bên trong phương thức khai báo/xử lý `IOException`. `source` đã có sẵn và effectively final; `buffered` là biến resource được khai báo mới trong header. Khi rời khối, Java đóng `buffered` trước, rồi đóng `source`.

Tuy nhiên, cần lưu ý **quyền sở hữu lồng nhau**: `BufferedReader.close()` cũng đóng reader mà nó bao bọc. Vì vậy, ví dụ này có khả năng gọi `close()` đến `source` nhiều hơn một lần. Một số triển khai có thể xử lý việc đóng lặp, nhưng không phải mọi `AutoCloseable` đều bảo đảm idempotent. Trong ứng dụng, thường chỉ nên quản lý **wrapper sở hữu delegate** một lần:

```java
java.io.StringReader source = new java.io.StringReader("first\nsecond");

try (java.io.BufferedReader buffered =
             new java.io.BufferedReader(source)) {
    System.out.println(buffered.readLine());
}
```

Đây là mảnh minh họa theo kiểu Java 7+, trong đó đóng `buffered` sẽ đóng `source` đi kèm. Khi chọn cú pháp kết hợp, hãy xác định rõ ai sở hữu resource gốc để tránh đóng trùng.

### Kết hợp với hai tài nguyên độc lập

Trường hợp thực sự cần trộn hai dạng header mà không gây rủi ro wrapper/delegate, có thể dùng hai tài nguyên không bao bọc nhau. Tạo tệp **`MixedResourcesDemo.java`**:

```java
public class MixedResourcesDemo {
    static class Tracked implements AutoCloseable {
        private final String name;

        Tracked(String name) {
            this.name = name;
        }

        @Override
        public void close() {
            System.out.println("close " + name);
        }
    }

    public static void main(String[] args) {
        Tracked existing = new Tracked("existing");

        try (existing; Tracked temporary = new Tracked("temporary")) {
            System.out.println("working");
        }

        System.out.println("done");
    }
}
```

```bash
javac MixedResourcesDemo.java
java MixedResourcesDemo
```

`stdout`:

```text
working
close temporary
close existing
done
```

`existing` được tham chiếu trực tiếp theo tính năng Java 9; `temporary` được khai báo tại chỗ như Java 7. Hai resource được đóng theo thứ tự ngược của danh sách trong header. Biến `temporary` không tồn tại ngoài `try`; biến `existing` vẫn tồn tại trong scope bên ngoài nhưng resource đã đóng.

## 8. `try-with-resources` đóng trên đường bình thường, `return` và ngoại lệ

Cơ chế đóng không phụ thuộc thân `try` có chạy hết bình thường hay không. Khi thoát do `return`, `break`, `continue` hoặc một ngoại lệ, Java thực hiện thao tác đóng theo quy tắc `try-with-resources`.

Tạo tệp **`EarlyReturnResourceDemo.java`**:

```java
public class EarlyReturnResourceDemo {
    static class Tracked implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("close called");
        }
    }

    static int calculate() {
        Tracked resource = new Tracked();

        try (resource) {
            System.out.println("inside");
            return 7;
        }
    }

    public static void main(String[] args) {
        System.out.println("returned=" + calculate());
    }
}
```

```bash
javac EarlyReturnResourceDemo.java
java EarlyReturnResourceDemo
```

`stdout`:

```text
inside
close called
returned=7
```

Câu lệnh `return 7` chuẩn bị kết quả trước, resource được đóng, sau đó bên gọi nhận `7`. Nếu `close()` ném ngoại lệ trên đường `return` đang chờ, ngoại lệ đóng có thể làm lời gọi kết thúc bằng lỗi thay vì trả về giá trị như dự kiến.

**Phân biệt** việc biến vẫn ở scope sau `try` với thời điểm gọi `close()`: resource được đóng **khi rời khối `try-with-resources`**, không phải khi biến địa phương đi ra khỏi scope hoặc khi garbage collector chạy.

### Null resource trong Java 9

Một biến tài nguyên có kiểu phù hợp nhưng chứa `null` vẫn có thể xuất hiện trong header. Java không gọi `close()` trên một tham chiếu null. Ví dụ:

```java
AutoCloseable resource = null;
try (resource) {
    System.out.println("body runs");
}
```

Đây là **mảnh minh họa** có thể cần xử lý/khai báo checked `Exception` tùy kiểu tĩnh của resource, vì `AutoCloseable.close()` khai báo `throws Exception`. Thân `try` vẫn chạy và không có đối tượng nào để đóng ở cuối. Dù ngôn ngữ cho phép, việc sử dụng null như “không có resource” không nên che giấu một lỗi thiếu tài nguyên bắt buộc.

## 9. Ngoại lệ trong `close()` và *suppressed exceptions*

Resource chỉ được đóng tự động nếu quá trình chạy thực sự đi qua cơ chế đóng của `try-with-resources`. Khi `close()` ném ngoại lệ, Java không đơn giản bỏ qua lỗi đó.

Có ba tình huống chính:

1. Thân `try` hoàn thành bình thường, `close()` ném ngoại lệ: lỗi từ `close()` đi ra (nếu không được bắt).
2. Thân `try` ném ngoại lệ, sau đó `close()` cũng ném: lỗi của **thân `try`** thường được giữ làm lỗi chính; lỗi đóng được thêm vào danh sách **suppressed**.
3. Có nhiều resource: chúng vẫn được đóng lần lượt theo thứ tự ngược; các lỗi đóng tiếp theo có thể trở thành suppressed của lỗi chính theo quy tắc ngôn ngữ.

Điều này khác với cách viết `finally` thủ công nếu một lệnh `close()` trong `finally` ném lỗi mới và vô tình che mất lỗi gốc.

### Ví dụ chạy được: giữ lỗi thân và lỗi đóng

Tạo tệp **`SuppressedCloseDemo.java`**:

```java
public class SuppressedCloseDemo {
    static class ExplodingResource implements AutoCloseable {
        @Override
        public void close() {
            throw new IllegalStateException("close failed");
        }
    }

    public static void main(String[] args) {
        ExplodingResource resource = new ExplodingResource();

        try (resource) {
            throw new IllegalArgumentException("body failed");
        } catch (IllegalArgumentException failure) {
            System.out.println("primary: " + failure.getMessage());
            System.out.println("suppressed count: "
                    + failure.getSuppressed().length);
            System.out.println("suppressed: "
                    + failure.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac SuppressedCloseDemo.java
java SuppressedCloseDemo
```

`stdout`:

```text
primary: body failed
suppressed count: 1
suppressed: close failed
```

`resource` là biến effectively final tạo trước `try`. Lỗi từ phần thân `try` là `IllegalArgumentException`; lỗi từ `close()` trở thành suppressed. Thông tin này có thể được quan sát bằng `getSuppressed()`; khi chẩn đoán lỗi tài nguyên cần xem cả primary, cause và suppressed exceptions.

Nếu `close()` có thể ném **checked exception**, trình biên dịch yêu cầu bắt hoặc khai báo kiểu đó, kể cả khi thân `try` không có thao tác nào ném checked exception. Quy tắc này **không đổi** chỉ vì resource được tham chiếu theo cú pháp Java 9.

### Ví dụ checked exception khi đóng

Tạo tệp **`CheckedCloseDemo.java`**:

```java
import java.io.IOException;

public class CheckedCloseDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("closing");
            throw new IOException("cannot close");
        }
    }

    public static void main(String[] args) {
        Resource resource = new Resource();

        try (resource) {
            System.out.println("processing");
        } catch (IOException failure) {
            System.out.println("caught: " + failure.getMessage());
        }
    }
}
```

```bash
javac CheckedCloseDemo.java
java CheckedCloseDemo
```

`stdout`:

```text
processing
closing
caught: cannot close
```

`Resource.close()` khai báo `throws IOException`; lời gọi đóng do ngôn ngữ tự phát sinh tại cuối `try` vẫn tham gia kiểm tra checked exception. Không cần gọi `resource.close()` thủ công trong thân `try`.

## 10. Những điều **không** được Java 9 cho phép

Tính năng Java 9 không chấp nhận một biểu thức tùy ý trong danh sách tài nguyên. Một phần tử resource dùng cú pháp tham chiếu mới phải là **variable access** hợp lệ, như tên biến cục bộ hoặc trường phù hợp với quy tắc ngôn ngữ.

Ví dụ **cố ý không biên dịch**:

```java
try (new java.io.StringReader("A")) {
    // Không được viết trực tiếp biểu thức new trong resource header.
}
```

Muốn tạo mới trong header, dùng **resource declaration**:

```java
try (java.io.StringReader reader = new java.io.StringReader("A")) {
    System.out.println(reader.read());
}
```

Cả hai đều là **mảnh minh họa**, đoạn đầu sai cú pháp; đoạn thứ hai hợp lệ nếu đặt trong phương thức/lớp Java phù hợp.

### Kiểu tĩnh phải thực thi `AutoCloseable`

Đoạn này **cố ý không biên dịch**:

```java
Object resource = new java.io.StringReader("A");
try (resource) {
    System.out.println("read");
}
```

Dù đối tượng thực tế là `StringReader`, **kiểu tĩnh** của biến resource là `Object`, không phải subtype của `AutoCloseable`. Tham số resource bị compiler từ chối. Khai báo biến bằng kiểu phù hợp, chẳng hạn `StringReader`, `Reader`, `Closeable` hoặc `AutoCloseable` tùy API bạn cần sử dụng.

### `final` không có nghĩa resource vẫn mở mãi

Có thể viết `final StringReader reader = ...`, nhưng khi dùng `try (reader)`, **đối tượng vẫn sẽ được đóng**. `final` chỉ bảo đảm biến không bị gán lại; nó không ngăn gọi `close()` và không biến trạng thái resource thành immutable.

### Không dùng cùng đối tượng trong hai vị trí nếu không hiểu close semantics

Nếu hai biến khác nhau cùng trỏ đến **một đối tượng AutoCloseable**, một header `try (first; second)` có thể gọi `close()` cho **cùng đối tượng đó hai lần**. Java bảo đảm thực hiện các thao tác đóng theo danh sách resource, không bảo đảm mọi implementation chấp nhận close lặp hoặc không tạo tác dụng phụ.

Hãy quản lý ownership rõ ràng, đặc biệt với resource được bọc hoặc chia sẻ.

## 11. Kiểm tra ranh giới phiên bản Java 8 và Java 9

Tính năng `try (resource)` xuất hiện từ **Java 9**. Khi dùng JDK 17, bạn có thể yêu cầu compiler giả lập mức ngôn ngữ và API mục tiêu bằng tùy chọn `--release`.

Giả sử tệp `ExistingResourceDemo.java` ở mục 4 đã lưu:

```bash
javac --release 9 ExistingResourceDemo.java
java ExistingResourceDemo
```

Chương trình biên dịch và chạy thành công vì Java 9 đã hỗ trợ cú pháp này. Có thể dùng `--release 17` hoặc biên dịch bình thường trên JDK 17.

Thử:

```bash
javac --release 8 ExistingResourceDemo.java
```

Lệnh biên dịch sẽ **báo lỗi** vì cú pháp tham chiếu trực tiếp biến tài nguyên không được hỗ trợ ở nguồn ngôn ngữ Java 8. Thông báo cụ thể phụ thuộc compiler; không xem đây là chương trình build thành công.

Nếu bạn đang bảo trì mã nguồn cần tương thích Java 8, hãy sử dụng dạng khai báo resource trong header:

```java
TrackedResource resource = new TrackedResource("A");
try (TrackedResource managed = resource) {
    managed.use();
}
```

Đây là **mảnh minh họa trong ngữ cảnh có sẵn lớp `TrackedResource`** từ ví dụ mục 4. Dạng alias `managed` dùng được ở Java 7/8 và các phiên bản sau. Nó đóng đúng đối tượng mà `resource` và `managed` cùng trỏ tới, không tạo một resource độc lập mới.

Đừng nhầm **phiên bản của JDK đang chạy** với **mức source language được chọn cho project**. Bạn có thể chạy JDK 17 nhưng build bằng `--release 8`, và cú pháp Java 9 vẫn không hợp lệ trong project đó.

## 12. Resource field: cần thận trọng hơn biến cục bộ

Java 9 cho phép một số dạng truy cập **trường** trong resource specification khi thỏa điều kiện theo ngôn ngữ, chẳng hạn trường được khai báo `final` với kiểu tài nguyên hợp lệ. Tuy nhiên, cần đặc biệt cân nhắc khi một trường là resource dài hạn thuộc lifecycle của đối tượng.

Ví dụ mảnh mã ý tưởng:

```java
class ReaderOwner {
    private final java.io.StringReader reader =
            new java.io.StringReader("data");

    void readOnce() throws java.io.IOException {
        try (this.reader) {
            System.out.println(reader.read());
        }
    }
}
```

Đây là **định nghĩa lớp để minh họa**, không có `main`. `this.reader` là truy cập trường `final`, khác với biến cục bộ effectively final. Sau lần `readOnce()` đầu tiên, trường `reader` vẫn trỏ đến đối tượng đã đóng. Gọi `readOnce()` lần nữa có thể thất bại khi cố đọc vì resource không còn mở.

**Thiết kế nên cân nhắc:** nếu một trường sở hữu tài nguyên lâu dài, thường để phương thức quản lý vòng đời như `close()` của lớp chủ sở hữu đóng nó ở thời điểm phù hợp, thay vì đóng nó âm thầm ở một lời gọi phương thức ngắn. Hãy phân biệt quyền truy cập ngôn ngữ `final` với quyền sở hữu/vòng đời tài nguyên.

## 13. Những lỗi hiểu nhầm phổ biến

**“Chỉ biến viết từ khóa `final` mới dùng được trong `try (resource)`.”** Sai. Java 9+ cho phép biến cục bộ *effectively final*, nghĩa là không bị gán lại dù không ghi từ khóa.

**“Có thể gán lại resource sau `try` vì khối đã kết thúc.”** Sai về tính effectively final: compiler xét các phép gán của biến trong phạm vi liên quan, không chỉ trước câu lệnh `try`.

**“Nếu gọi `reader.readLine()`, reader không còn effectively final.”** Sai. Gọi phương thức thay đổi **trạng thái đối tượng**, không phải gán lại **biến tham chiếu**.

**“Dùng `try (reader)` tạo ra bản sao của reader.”** Sai. Nó quản lý **chính đối tượng** đang được tham chiếu, không tự clone resource.

**“Biến vẫn nhìn thấy sau `try` nghĩa là resource còn mở.”** Sai. Đối tượng có thể đã đóng; scope của biến và lifetime mở của tài nguyên là hai chuyện khác nhau.

**“Đã khai báo resource trước `try` thì mọi lỗi khi khởi tạo resource đều được try-with-resources quản lý.”** Sai. Nếu lỗi xuất hiện **trước khi vào `try`**, cơ chế tự đóng của `try` đó chưa áp dụng. Đây là lý do khai báo resource trực tiếp trong header vẫn rất hữu ích.

**“Đóng các resource theo thứ tự từ trái sang phải.”** Sai. Java đóng theo thứ tự ngược từ phải sang trái trong header.

**“Có `try-with-resources` thì lỗi `close()` bị bỏ qua.”** Sai. Lỗi có thể truyền ra hoặc được lưu là *suppressed exception* nếu đã có lỗi chính.

**“Biến có kiểu `Object` được chấp nhận miễn runtime object có `close()`.”** Sai. Kiểm tra kiểu resource diễn ra khi biên dịch; kiểu tĩnh phải phù hợp `AutoCloseable`.

**“Java 9 cho phép `try (new MyResource())`.”** Sai. Một biểu thức tạo đối tượng trần không phải variable access resource hợp lệ; hãy khai báo resource mới: `try (MyResource r = new MyResource())`.

**“Dùng một resource trong hai slot của header sẽ tự nhận diện và chỉ đóng một lần.”** Sai. Không được dựa vào cơ chế khử trùng lặp khi đóng. Hãy tránh quản lý hai alias đến cùng đối tượng mà không hiểu hợp đồng `close()`.

**“`StringReader` đóng xong vẫn đọc được vì dữ liệu nằm trong RAM.”** Sai. Hợp đồng của reader vẫn điều khiển trạng thái đóng; việc dữ liệu nằm trong bộ nhớ không có nghĩa bạn được đọc vô hạn sau `close()`.

## 14. Bài tập tự kiểm tra

1. **`BufferedReader r = ...; try (r) { ... }` hợp lệ ở Java 17 khi nào?** Khi `r` được gán chắc chắn trước `try`, có kiểu phù hợp với `AutoCloseable` và là final hoặc effectively final.
2. **Không có từ khóa `final` nhưng không gán lại, compiler có chấp nhận không?** Có, đó là effectively final.
3. **Viết `r = anotherReader;` ở phía sau `try (r)` thì sao?** Biến không còn effectively final; compiler có thể từ chối resource specification.
4. **Có thể thay đổi trạng thái resource bên trong `try` không?** Có, nếu API cho phép. Điều kiện effectively final chỉ ràng buộc phép gán **biến**.
5. **Sau `try (r)`, biến `r` còn trong scope không?** Có nếu nó được khai báo ở scope bên ngoài; nhưng đối tượng đã được đóng.
6. **`try (a; b)` đóng theo thứ tự nào?** `b` trước, rồi `a`.
7. **`try (new FileInputStream(path))` là cú pháp trực tiếp hợp lệ từ Java 9?** Không; cần resource declaration hoặc biến có sẵn hợp lệ.
8. **Nếu `close()` ném trong khi thân `try` đã ném lỗi, điều gì thường xảy ra?** Lỗi thân là primary, lỗi đóng là suppressed; kiểm tra `getSuppressed()`.
9. **Nếu tạo resource A thành công, rồi tạo B thất bại trước `try (a; b)`, A có tự được đóng bởi `try` này không?** Không, vì chưa vào phạm vi tự quản lý của `try`.
10. **Với Java 8, muốn dùng resource khai báo bên ngoài, viết thế nào?** Tạo biến resource mới ngay trong header, ví dụ `try (Reader managed = reader)`.
11. **Dùng biến `final` có khiến resource immutable không?** Không, chỉ làm tham chiếu không thể gán lại.
12. **Nếu `AutoCloseable.close()` có checked exception, cú pháp Java 9 bỏ nghĩa vụ `catch/throws` không?** Không. Bên gọi vẫn cần xử lý hoặc khai báo checked exception phù hợp.
13. **Có nên đóng một connection do framework quản lý bằng `try (connection)` không?** Chỉ khi hợp đồng quyền sở hữu cho phép; nếu framework quản lý vòng đời thì tự đóng có thể sai.

## 15. Tài liệu tham khảo chuẩn

- [Java Language Specification 17 — §14.20.3, try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): cú pháp và ngữ nghĩa tài nguyên, tự đóng, thứ tự đóng và suppressed exceptions.
- [Java Language Specification 17 — §4.12.4, final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): biến final và effectively final.
- [Java SE 17 API — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng `close()` và lưu ý về tính idempotent.
- [Java SE 17 API — Closeable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Closeable.html): biến thể đóng resource I/O.
- [Java SE 17 API — Throwable.getSuppressed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html#getSuppressed()): quan sát lỗi bị suppressed.
- [JEP 213 — Milling Project Coin](https://openjdk.org/jeps/213): cải tiến cú pháp try-with-resources sử dụng biến tài nguyên đã có từ Java 9.

**Ghi nhớ:** Từ Java 9, có thể viết `try (resource)` cho biến tài nguyên **đã tồn tại**, nếu biến là `final` hoặc *effectively final* và có kiểu hợp lệ với `AutoCloseable`. Java tự đóng **đối tượng được tham chiếu** khi rời khối; biến vẫn có thể còn trong scope nhưng tài nguyên không còn mở. Tính ngắn gọn về cú pháp không thay thế việc quản lý đúng quyền sở hữu, thời điểm tạo tài nguyên và ngoại lệ từ `close()`.
