# Tài nguyên `null` và lời gọi `close()` tự động trong Java try-with-resources

Trong Java, **try-with-resources** là cấu trúc `try (...) { ... }` dùng để quản lý tài nguyên triển khai `AutoCloseable`. Khi rời khối, Java tự động **cố gắng gọi `close()` trên các tài nguyên đã khởi tạo thành công và có tham chiếu khác `null`**. Nếu biến tài nguyên có giá trị **`null`**, Java **bỏ qua việc gọi `close()` cho tài nguyên đó**; chỉ riêng việc tài nguyên là `null` **không** làm câu lệnh try-with-resources ném `NullPointerException`.

Quy tắc ngắn gọn:

> **Tài nguyên `null` thì không đóng; tài nguyên khác `null` thì được cố đóng khi rời phạm vi.** Việc tự động đóng không làm biến `null` thành đối tượng hợp lệ và không ngăn `NullPointerException` nếu mã trong thân `try` cố dùng tham chiếu `null`.

Bài học này giải thích bản chất của lời gọi `close()` tự động, sự khác nhau giữa **tài nguyên `null`** và **khởi tạo tài nguyên thất bại vì exception**, cách Java đóng nhiều tài nguyên, quan hệ với `catch`/`finally`, lỗi đóng tài nguyên, các quy tắc checked exception, và cách thiết kế API tránh những tình huống khó hiểu.

## 1. Nhắc lại cấu trúc try-with-resources

Một cấu trúc thông thường:

```java
try (SomeResource resource = openResource()) {
    useResource(resource);
}
```

Đây là **mã khung minh họa**, trong đó `SomeResource` phải triển khai `AutoCloseable` và hai phương thức phụ cần được định nghĩa. Tại runtime, Java tiến hành:

1. Đánh giá biểu thức `openResource()` và khởi tạo biến `resource`.
2. Nếu khởi tạo thành công, đi vào thân `try`.
3. Khi rời thân `try`, dù thành công, có `return` hoặc exception, Java **cố đóng** tài nguyên nếu tham chiếu khác `null`.
4. Sau việc đóng, Java chuyển tới `catch` hoặc `finally` gắn với cấu trúc đó nếu có, hoặc tiếp tục/lan truyền theo đường tương ứng.

Thứ tự khởi tạo tài nguyên là từ **trái sang phải**, và thứ tự đóng là **ngược lại, từ phải sang trái**. Java chỉ quản lý những tài nguyên đã được khởi tạo thành công; điều kiện tham chiếu `null` quyết định có thực sự gọi `close()` trên từng tài nguyên hay không.

**`AutoCloseable` không có nghĩa việc đóng chắc chắn thành công.** `close()` có thể ném exception, và try-with-resources sẽ áp dụng các quy tắc về primary và suppressed exceptions để xử lý trường hợp đó.

## 2. Một tài nguyên được gán `null` có hợp lệ không?

Có. Java cho phép khai báo một biến tài nguyên bằng biểu thức có kiểu phù hợp và giá trị runtime là `null`. Ví dụ:

```java
try (MyResource resource = null) {
    System.out.println("Thân try vẫn chạy");
}
```

Đây là **đoạn minh họa**, cần lớp `MyResource` triển khai `AutoCloseable` để biên dịch. Trong trường hợp này:

- Phần khai báo tài nguyên được đánh giá bình thường và có kết quả tham chiếu `null`.
- Thân `try` **vẫn chạy**; Java không tự coi tài nguyên `null` là một điều kiện thất bại.
- Khi rời khối, Java **không gọi** `resource.close()` vì tham chiếu là `null`.
- Không có `NullPointerException` chỉ do thao tác cleanup tự động.
- Nếu ngay trong thân `try` bạn gọi `resource.read()`, Java có thể ném `NullPointerException` do **dereference `null`**, một vấn đề khác với cơ chế đóng.

Một số API thiết kế theo cách “không có tài nguyên” bằng `null`, nhưng đây không phải mặc định tốt cho mọi chương trình. Trong một API cần tài nguyên bắt buộc, trả `null` có thể là sai hợp đồng và nên được xử lý riêng, ví dụ bằng thông báo lỗi rõ ràng.

## 3. Ví dụ Java 17 hoàn chỉnh: `null` không bị đóng

Lưu chương trình sau thành **`NullResourceDemo.java`**:

```java
public class NullResourceDemo {
    static class TrackedResource implements AutoCloseable {
        private final String name;

        TrackedResource(String name) {
            this.name = name;
            System.out.println("Tạo: " + name);
        }

        void work() {
            System.out.println("Dùng: " + name);
        }

        @Override
        public void close() {
            System.out.println("Đóng: " + name);
        }
    }

    static TrackedResource openOrNull(boolean available) {
        if (!available) {
            System.out.println("Không tạo tài nguyên");
            return null;
        }
        return new TrackedResource("R");
    }

    static void execute(boolean available) {
        try (TrackedResource resource = openOrNull(available)) {
            System.out.println("resource == null: " + (resource == null));
            if (resource != null) {
                resource.work();
            } else {
                System.out.println("Bỏ qua thao tác cần tài nguyên");
            }
        }
        System.out.println("Sau try-with-resources");
    }

    public static void main(String[] args) {
        execute(false);
        System.out.println("---");
        execute(true);
    }
}
```

Biên dịch/chạy bằng Java 17 trở lên:

```bash
javac -encoding UTF-8 --release 17 NullResourceDemo.java
java NullResourceDemo
```

**Stdout chính xác** với console UTF-8:

```text
Không tạo tài nguyên
resource == null: true
Bỏ qua thao tác cần tài nguyên
Sau try-with-resources
---
Tạo: R
resource == null: false
Dùng: R
Đóng: R
Sau try-with-resources
```

Với `execute(false)`, biểu thức khởi tạo trả `null`. Thân `try` chạy, nhánh xử lý “không có tài nguyên” được chọn, và không có dòng `Đóng: R` vì không có object để đóng.

Với `execute(true)`, tài nguyên `TrackedResource` được tạo, sử dụng và đóng khi rời khối. Lệnh sau cấu trúc chỉ chạy sau bước đóng, nếu `close()` hoàn tất bình thường.

Bài học cốt lõi: **Java tự động kiểm tra tài nguyên khác `null` trước khi gọi `close()`, không cần viết một `if (resource != null)` chỉ để phòng NPE ở bước đóng**. Nhưng kiểm tra trước khi **sử dụng** tài nguyên có thể vẫn cần nếu hợp đồng cho phép `null`.

## 4. Null-safe cleanup không phải null-safe usage

Xét chương trình **`NullUsageDemo.java`**:

```java
public class NullUsageDemo {
    static class Resource implements AutoCloseable {
        void use() {
            System.out.println("Đã dùng");
        }

        @Override
        public void close() {
            System.out.println("Đã đóng");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = null) {
            System.out.println("Vào try");
            resource.use();
            System.out.println("Sau use");
        } catch (NullPointerException e) {
            System.out.println("Bắt NullPointerException");
        }
        System.out.println("Sau try/catch");
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 NullUsageDemo.java
java NullUsageDemo
```

**Stdout chính xác:**

```text
Vào try
Bắt NullPointerException
Sau try/catch
```

Lệnh `resource.use()` cố gọi instance method trên tham chiếu `null` và ném `NullPointerException`. Sau khi thân `try` bị ngắt, Java xét cleanup, thấy resource là `null` nên **không gọi `close()`**. `catch` nhận `NullPointerException` do thao tác `use`, không phải do đóng tự động.

Đừng suy luận sai rằng “`try-with-resources` xử lý được `null`” có nghĩa mọi thao tác lên đối tượng `null` đều an toàn. Cơ chế chỉ bỏ qua **lời gọi `close()` được tạo tự động**, chứ không kiểm tra mọi biểu thức trong thân `try`.

Nếu tài nguyên là bắt buộc, một thiết kế rõ ràng hơn có thể dùng `Objects.requireNonNull` tại ranh giới để thất bại sớm với ngữ cảnh:

```java
import java.util.Objects;

class RequiredResource {
    static void run(AutoCloseable resource) throws Exception {
        Objects.requireNonNull(resource, "resource là bắt buộc");
        try (resource) {
            System.out.println("Có tài nguyên hợp lệ");
        }
    }
}
```

Đây là **lớp minh họa không có `main`**, dùng cú pháp Java 9+ cho biến tài nguyên đã khai báo trước. Kiểm tra `requireNonNull` xảy ra **trước khi vào `try-with-resources`**, nhằm bộc lộ rõ hợp đồng “không chấp nhận `null`”. Khai báo `throws Exception` xuất phát từ kiểu tĩnh `AutoCloseable.close()`, có thể ném checked `Exception`.

## 5. Vì sao Java không gọi `null.close()`?

Có thể hình dung try-with-resources đơn giản như đoạn cleanup sau:

```java
Resource resource = openOrNull();
try {
    doWork(resource);
} finally {
    if (resource != null) {
        resource.close();
    }
}
```

Đây là **mã giả theo ý tưởng**, không phải bản dịch đầy đủ của mọi ngữ nghĩa try-with-resources. Nó giúp thấy **kiểm tra `resource != null`** trước khi đóng. Cơ chế thật của Java phức tạp hơn: phải bảo toàn ngoại lệ chính, xử lý ngoại lệ khi `close()` thất bại và đóng nhiều tài nguyên theo đúng thứ tự.

Đừng dùng đoạn khung này làm cách thay thế trực tiếp cho try-with-resources nếu cần giữ exception gốc. Nếu `doWork` ném exception A và `close` cũng ném B, một `finally` đơn giản như trên có thể làm **B che mất A**. Trong khi đó, try-with-resources giữ A làm ngoại lệ chính và thường gắn B dưới dạng **suppressed exception**.

Điểm rút ra: việc **bỏ qua đóng với tham chiếu `null`** chỉ là một phần của hợp đồng quản lý tài nguyên; việc quản lý lỗi đồng thời còn quan trọng không kém.

## 6. Phân biệt `null` với khởi tạo tài nguyên thất bại

Hai tình huống sau hoàn toàn khác:

**Tình huống A: factory trả về `null` bình thường.**

```java
Resource resource = openOrNull(); // Trả về null.
```

Trong try-with-resources, biểu thức khởi tạo hoàn tất bình thường, biến `resource` được gán `null`, thân `try` bắt đầu. Khi rời khối, tài nguyên `null` bị bỏ qua ở bước đóng.

**Tình huống B: factory ném exception khi khởi tạo.**

```java
Resource resource = openOrThrow(); // Ném exception.
```

Ở trường hợp này, biểu thức khởi tạo không hoàn tất bình thường. **Thân `try` chưa bắt đầu**; Java thực hiện cleanup đối với các tài nguyên **đã khởi tạo thành công trước đó trong cùng resource specification**, nếu có, rồi lan truyền exception theo luật xử lý.

Không nên coi “trả `null`” và “ném exception” là hai cách báo thất bại tương đương. Chúng khác nhau về luồng thực thi, hợp đồng API và khả năng tạo một kết quả hợp lệ.

## 7. Nhiều tài nguyên có một biến `null`: các biến khác vẫn được đóng

Một resource `null` không cản trở việc đóng những tài nguyên khác. Khi khai báo nhiều biến trong `try (...)`, Java xét chúng theo **thứ tự ngược khai báo**, bỏ qua biến nào có giá trị `null`.

Lưu chương trình **`MultipleNullResourcesDemo.java`**:

```java
public class MultipleNullResourcesDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("Mở " + name);
        }

        @Override
        public void close() {
            System.out.println("Đóng " + name);
        }
    }

    public static void main(String[] args) {
        try (Resource first = new Resource("A");
             Resource middle = null;
             Resource last = new Resource("C")) {
            System.out.println("Trong try: middle null = " + (middle == null));
        }
        System.out.println("Sau try");
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 MultipleNullResourcesDemo.java
java MultipleNullResourcesDemo
```

**Stdout chính xác:**

```text
Mở A
Mở C
Trong try: middle null = true
Đóng C
Đóng A
Sau try
```

Tài nguyên A và C được tạo, còn `middle` được gán `null`. Việc đóng đi từ C → middle (bỏ qua) → A. Vì thế không có dòng “Đóng middle”. Java vẫn đóng C và A dù resource đứng giữa bằng `null`.

Nếu thân `try` ném exception, tài nguyên khác `null` đã khởi tạo thành công vẫn được cố đóng theo thứ tự này trước khi exception được chuyển đến handler phù hợp.

## 8. Tài nguyên trước đã mở, tài nguyên sau trả `null`

Khi một factory nằm ở giữa danh sách trả `null`, Java vẫn tiếp tục **khởi tạo các resource đứng sau**. Sự kiện trả `null` không khiến initialization bị bỏ dở.

Ví dụ:

```java
try (Resource a = open("A");
     Resource optional = optionalResource(); // Có thể null
     Resource b = open("B")) {
    process(a, optional, b);
}
```

Đây là **mã khung minh họa**, các hàm và lớp phải được định nghĩa. Nếu `optionalResource()` trả `null` bình thường, Java vẫn gọi `open("B")` rồi vào thân `try`. Chỉ khi một biểu thức khởi tạo **ném exception** mới có đường đi thoát bất thường.

Hàm `process` cần được thiết kế để biết `optional` có thể `null`. Nếu nó dereference `optional` mà không kiểm tra, `NullPointerException` có thể phát sinh trong thân `try`; khi đó A và B vẫn được đóng bình thường theo cấu trúc.

Đây là điểm khác với một số cấu trúc khác của lập trình có điều kiện: **`null` chỉ là giá trị tham chiếu**, không phải tín hiệu mà câu lệnh try-with-resources tự coi là “bỏ qua toàn bộ block”.

## 9. Nếu khởi tạo tài nguyên thứ hai ném exception, tài nguyên đầu được đóng

Lưu **`InitializationFailureDemo.java`**:

```java
public class InitializationFailureDemo {
    static class Resource implements AutoCloseable {
        private final String name;

        Resource(String name) {
            this.name = name;
            System.out.println("Mở " + name);
        }

        @Override
        public void close() {
            System.out.println("Đóng " + name);
        }
    }

    static Resource open(String name) {
        if ("B".equals(name)) {
            System.out.println("Không mở được B");
            throw new IllegalStateException("Lỗi khởi tạo B");
        }
        return new Resource(name);
    }

    public static void main(String[] args) {
        try (Resource a = open("A");
             Resource b = open("B");
             Resource c = open("C")) {
            System.out.println("Trong try");
        } catch (IllegalStateException e) {
            System.out.println("Catch: " + e.getMessage());
        }
        System.out.println("Sau cấu trúc");
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 InitializationFailureDemo.java
java InitializationFailureDemo
```

**Stdout chính xác:**

```text
Mở A
Không mở được B
Đóng A
Catch: Lỗi khởi tạo B
Sau cấu trúc
```

Resource A đã khởi tạo thành công; B ném `IllegalStateException` trước khi trả về một đối tượng resource; C chưa được khởi tạo. Java cố đóng A rồi truyền lỗi tới `catch`. Không có dòng “Trong try”, “Mở C” hoặc “Đóng C”.

Ví dụ này cho thấy try-with-resources xử lý an toàn **một phần danh sách tài nguyên đã được khởi tạo**, không chỉ trường hợp tất cả đã được mở. Khi một resource trả `null` thay vì ném exception, luồng khởi tạo không bị ngắt theo cách này.

## 10. `close()` được gọi khi nào?

Với tài nguyên không `null`, Java cố gọi `close()` khi rời phạm vi tài nguyên sau thân `try`. Các đường đi phổ biến:

| Đường rời thân `try` | Tài nguyên khác `null` có được cố đóng? | Sau đóng đi đâu? |
| --- | --- | --- |
| Thân `try` hoàn tất bình thường | Có | Tiếp tục sau try-with-resources nếu close bình thường |
| Thân `try` ném exception | Có | Exception được xét bởi `catch` ngoài phạm vi tài nguyên |
| Thân `try` thực hiện `return` | Có | Quay lại caller nếu đóng hoàn tất bình thường |
| Thân `try` thực hiện `break` hoặc `continue` hợp lệ | Có | Chuyển điều khiển theo cấu trúc nếu đóng bình thường |
| Khởi tạo resource sau ném exception | Các resource đã khởi tạo trước đó có | Lan truyền tới handler phù hợp |
| Tài nguyên cụ thể bằng `null` | **Không gọi `close()` cho tài nguyên đó** | Các tài nguyên còn lại vẫn theo quy tắc |

**Không có bảo đảm tuyệt đối** khi JVM bị chấm dứt cưỡng bức, tiến trình crash, hoặc một số tình huống nghiêm trọng khác. “Tự động” ở đây là theo các quy tắc thực thi Java khi rời cấu trúc, không phải phép màu bảo đảm tài nguyên vật lý luôn đóng thành công.

Một chi tiết quan trọng: với cấu trúc có `catch` và `finally` gắn trực tiếp với try-with-resources, **đóng tài nguyên hoàn tất/được thử trước khi handler `catch` hoặc khối `finally` ấy chạy**.

## 11. Thân `try` ném exception, tài nguyên khác `null` được đóng

Ví dụ **`CloseOnFailureDemo.java`**:

```java
public class CloseOnFailureDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("Đóng resource");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("Trong try");
            throw new IllegalArgumentException("Lỗi nghiệp vụ");
        } catch (IllegalArgumentException e) {
            System.out.println("Catch: " + e.getMessage());
        } finally {
            System.out.println("Finally");
        }
        System.out.println("Kết thúc");
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 CloseOnFailureDemo.java
java CloseOnFailureDemo
```

**Stdout chính xác:**

```text
Trong try
Đóng resource
Catch: Lỗi nghiệp vụ
Finally
Kết thúc
```

Dù thân `try` ném exception, lời gọi `close()` vẫn diễn ra trước `catch` của cấu trúc. Trong trường hợp `resource = null`, dòng “Đóng resource” sẽ không có; handler vẫn bắt exception ném từ thân `try`.

## 12. Khi `close()` tự ném exception

`AutoCloseable.close()` được phép ném exception. Lúc đó cần xét có **exception chính** từ thân `try` trước hay không.

### 12.1. Chỉ `close()` thất bại

Lưu **`CloseOnlyFailureDemo.java`**:

```java
public class CloseOnlyFailureDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("Trong close");
            throw new IllegalStateException("Không đóng được");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("Thân try thành công");
        } catch (IllegalStateException e) {
            System.out.println("Catch: " + e.getMessage());
        }
        System.out.println("Sau try/catch");
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 CloseOnlyFailureDemo.java
java CloseOnlyFailureDemo
```

**Stdout chính xác:**

```text
Thân try thành công
Trong close
Catch: Không đóng được
Sau try/catch
```

Ở đây thân `try` hoàn tất, nhưng `close()` ném exception. Lỗi đóng trở thành **exception chính** của cấu trúc. `catch` nhận lỗi đó. Không thể kết luận rằng toàn bộ thao tác đã thành công chỉ vì thân `try` hoàn tất.

Nếu tài nguyên `resource` thực sự bằng `null`, Java không gọi `close()`, nên không có lỗi đóng từ tài nguyên ấy.

### 12.2. Thân `try` và `close()` cùng thất bại

Lưu **`PrimarySuppressedDemo.java`**:

```java
public class PrimarySuppressedDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("Trong close");
            throw new IllegalStateException("Lỗi đóng");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("Trong try");
            throw new IllegalArgumentException("Lỗi chính");
        } catch (IllegalArgumentException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Suppressed: "
                    + e.getSuppressed().length);
            System.out.println("Phụ: "
                    + e.getSuppressed()[0].getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 --release 17 PrimarySuppressedDemo.java
java PrimarySuppressedDemo
```

**Stdout chính xác:**

```text
Trong try
Trong close
Primary: Lỗi chính
Suppressed: 1
Phụ: Lỗi đóng
```

Ngoại lệ `IllegalArgumentException` từ thân `try` là **primary**. Ngoại lệ `IllegalStateException` từ `close()` được gắn vào primary qua `addSuppressed` theo cơ chế try-with-resources, truy cập bằng `getSuppressed()`.

Điều này khác kiểu cleanup thủ công trong `finally`: nếu `finally` ném exception mới, nó có thể **che mất lỗi ban đầu**. Với try-with-resources, Java giữ lỗi chính và lưu lỗi đóng như một lỗi phụ.

**Nếu resource bằng `null`, `close()` không chạy, nên không có suppressed exception từ resource đó.** Không suy đoán rằng cứ một exception trong thân `try` là chắc chắn có phần tử suppressed; chỉ truy `getSuppressed()[0]` sau khi kiểm tra mảng không rỗng trong mã thực.

## 13. Nhiều tài nguyên: lỗi đóng của đối tượng `null` không tồn tại

Giả sử resource A khác `null`, B bằng `null`, C khác `null`. Khi thân `try` thất bại, Java cố đóng C, bỏ qua B, rồi đóng A. Nếu `close()` của C và A đều ném exception, hai lỗi đóng có thể được gắn suppressed vào exception chính theo thứ tự đóng.

Không có lỗi đóng “giả” cho B: vì Java không gọi `close()` trên B, B không tạo thêm một suppressed exception do cleanup.

Ví dụ khung:

```java
try (Resource a = open("A");
     Resource b = null;
     Resource c = open("C")) {
    throw new IllegalArgumentException("Work failed");
}
```

Đây là **khung minh họa**, cần lớp `Resource` và hàm `open` hợp lệ. Nếu `close()` của A/C ném lỗi, có thể kiểm tra `getSuppressed()` ở handler tương ứng. Thứ tự đóng **C trước A** không đổi vì B bằng `null`.

Cách suy luận đúng là xét **mỗi tài nguyên đã khởi tạo thành công và khác `null`**, rồi mới xét các exception do các thao tác đóng đó ném.

## 14. `try (resource)` với biến đã khai báo trước: `null` vẫn được bỏ qua

Từ **Java 9**, resource specification có thể dùng một biến tham chiếu tài nguyên đã được khai báo trước đó, nếu biến đó là `final` hoặc *effectively final* và đã được gán hợp lệ. Java 17 hỗ trợ cú pháp này:

```java
Resource resource = mayReturnNull();
try (resource) {
    System.out.println("Trong try");
}
```

Đây là **mã khung**. Biến `resource` tồn tại ở phạm vi ngoài và vẫn nhìn thấy sau khối `try`. Nếu tham chiếu là `null`, Java bỏ qua việc gọi `close()`; nếu khác `null`, Java cố đóng nó khi rời block.

Ví dụ độc lập **`ExistingVariableNullDemo.java`**:

```java
public class ExistingVariableNullDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() {
            System.out.println("Đóng");
        }
    }

    public static void main(String[] args) {
        Resource resource = null;

        try (resource) {
            System.out.println("Trong try");
        }

        System.out.println("Vẫn truy cập tên resource: "
                + (resource == null));
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 --release 17 ExistingVariableNullDemo.java
java ExistingVariableNullDemo
```

**Stdout chính xác:**

```text
Trong try
Vẫn truy cập tên resource: true
```

Không có dòng `Đóng` vì resource `null`. `resource` được khai báo ở scope ngoài nên tên vẫn dùng được sau cấu trúc, nhưng dùng `try (resource)` không đồng nghĩa mã Java cho phép gán lại biến tùy ý; cú pháp này yêu cầu `final` hoặc *effectively final*.

Nếu biến chưa được **definitely assigned** trước khi dùng trong resource specification, compiler sẽ từ chối. Nếu gán lại nó khiến biến không còn effectively final, cú pháp `try (resource)` cũng sẽ không hợp lệ. Đây là quy tắc kiểm tra **compile time**, khác với việc tham chiếu có thể bằng `null` ở runtime.

## 15. Giá trị đóng được xác định từ tài nguyên trong resource specification

Với dạng khai báo:

```java
try (Resource resource = createResource()) {
    // ...
}
```

biểu thức `createResource()` được đánh giá khi khởi tạo. Việc tài nguyên là `null` hay không được quyết định từ **giá trị tham chiếu được khởi tạo**. Java không tự đánh giá lại `createResource()` khi đến bước đóng.

Điều này quan trọng nếu factory có side effect hoặc kết quả thay đổi theo thời gian. Khởi tạo tài nguyên là một bước có tác dụng rõ ràng; không nên viết mã suy luận rằng factory sẽ được gọi lại lúc cleanup.

Với dạng Java 9+ `try (resource)`, biến là final/effectively final. Điều đó không bảo đảm **trạng thái nội bộ đối tượng** bất biến: tài nguyên vẫn có thể thay đổi trạng thái, nhưng try-with-resources cố gọi `close()` trên đối tượng mà phần resource specification đã chọn.

Đối tượng có thể đã được đóng từ trước bởi mã khác, và `close()` có thể được gọi lại khi ra khỏi `try`. Giao diện `AutoCloseable` không biến tất cả các triển khai thành hoàn toàn idempotent, nên cần xác định rõ quyền sở hữu tài nguyên và không chia sẻ đóng tùy tiện.

## 16. `null` không có nghĩa Java bỏ qua việc kiểm tra checked exception

Quy tắc `close()` tự động còn chịu **kiểm tra kiểu lúc biên dịch**. Theo API chuẩn, `AutoCloseable.close()` khai báo `throws Exception`, trong khi các lớp con có thể override với kiểu checked exception hẹp hơn hoặc không ném checked exception nào.

Ví dụ:

```java
static void useGeneric(AutoCloseable resource) throws Exception {
    try (resource) {
        System.out.println("Trong try");
    }
}
```

Đây là **phương thức minh họa**, với `resource` là tham số effectively final và dùng cú pháp Java 9+. Chữ ký `throws Exception` hợp lý vì kiểu tĩnh của `resource` là `AutoCloseable`; `close()` theo hợp đồng có thể ném `Exception`.

Nếu truyền tham chiếu `null` vào lời gọi này, **runtime sẽ bỏ qua `close()`**, nhưng compiler vẫn kiểm tra hợp đồng kiểu tĩnh của phương thức. Không nên cho rằng “vì lúc chạy biến này `null` nên có thể xóa mọi `throws` hay `catch` liên quan đến `close()`” trong tất cả trường hợp.

Nếu tự định nghĩa class implements `AutoCloseable` và override `close()` **không khai báo checked exception**, như `Resource` ở các ví dụ trên, caller làm việc với kiểu tĩnh `Resource` thường không phải xử lý `Exception` chỉ vì try-with-resources.

## 17. Khi nào nên cho phép factory trả `null`?

Một số API cũ hoặc ranh giới tích hợp có thể cho phép factory trả `null` với nghĩa “không có tài nguyên”. Try-with-resources xử lý cleanup của trường hợp này đúng theo quy tắc, nhưng thiết kế API vẫn cần trả lời:

- `null` có phải là **trạng thái dự kiến, hợp lệ** không?
- Nếu không có tài nguyên, thân `try` có công việc nào được phép tiếp tục không?
- Có cần một giá trị kết quả như `Optional` hoặc một loại trạng thái khác để biểu diễn vắng mặt rõ hơn không?
- Liệu caller có lẫn `null` với lỗi khởi tạo kỹ thuật đáng ra phải ném exception?
- Khi không có resource, liệu tác vụ phải trả kết quả sớm, báo lỗi, hay dùng một fallback thật sự hợp lệ?

Ví dụ, nếu một nguồn cấu hình là tùy chọn, không có reader có thể dẫn đến cấu hình mặc định hợp pháp. Nhưng nếu một giao dịch bắt buộc phải có kết nối, factory trả `null` rồi chương trình âm thầm chạy tiếp có thể tạo sai dữ liệu.

**Try-with-resources không tự định nghĩa ý nghĩa nghiệp vụ của `null`.** Nó chỉ cung cấp quy tắc không gọi `close()` trên `null` khi cleanup. Hãy làm rõ hợp đồng trước khi dựa vào hành vi này.

## 18. Thói quen an toàn khi mở và dùng resource

Cách viết phụ thuộc việc không có tài nguyên có được phép hay không.

### 18.1. Tài nguyên bắt buộc: kiểm tra rõ ràng

```java
import java.util.Objects;

class RequiredResourceExample {
    static void process(AutoCloseable resource) throws Exception {
        Objects.requireNonNull(resource, "resource không được null");
        try (resource) {
            // Thực hiện thao tác mà hợp đồng yêu cầu có resource.
        }
    }
}
```

Đây là lớp hợp lệ **không có `main`**. Nếu caller truyền `null`, chương trình ném `NullPointerException` ở bước kiểm tra chủ động, với message chỉ rõ tiền điều kiện. Cần lưu ý: `Objects.requireNonNull` không tự đóng gì, nó chỉ làm rõ hợp đồng.

### 18.2. Tài nguyên tùy chọn: kiểm tra trước khi sử dụng

```java
static void processOptional(Resource resource) {
    try (resource) {
        if (resource == null) {
            System.out.println("Không có dữ liệu cần xử lý");
            return;
        }
        resource.work();
    }
}
```

Đây là **phương thức minh họa** với `Resource` implements `AutoCloseable` và có method `work()`. `Resource` không khai báo checked exception ở `close()` trong ví dụ giả định. Cần bảo đảm tham số `resource` không bị gán lại, để thỏa điều kiện Java 9+.

Khi giá trị `null`, handler tự quyết định không làm gì và `return`. Java xét cleanup của `try-with-resources`, thấy tham chiếu `null` nên bỏ qua `close()`; khi khác `null`, thực thi `work()` rồi đóng.

Không nên xây API kiểu “thỉnh thoảng trả `null`, thỉnh thoảng ném lỗi” mà không giải thích rõ trường hợp nào là thiếu dữ liệu hợp lệ và trường hợp nào là sự cố kỹ thuật.

## 19. Sai lầm thường gặp

| Hiểu sai | Quy tắc đúng |
| --- | --- |
| “`try (Resource r = null)` lập tức ném `NullPointerException`.” | Không. Thân `try` vẫn chạy, và cleanup bỏ qua `close()` của resource `null`. |
| “Tài nguyên `null` vẫn được gọi `close()`, chỉ là Java tự bắt lỗi.” | Không. Java **không gọi** `close()` trên tham chiếu `null`. |
| “Có thể gọi `r.work()` thoải mái vì try-with-resources tự xử lý `null`.” | Không. Dereference `null` trong thân `try` vẫn có thể ném `NullPointerException`. |
| “Một resource ở giữa `null` thì các resource còn lại không đóng.” | Sai. Những resource khác `null` đã khởi tạo thành công vẫn được cố đóng theo thứ tự ngược. |
| “Factory trả `null` giống như constructor ném exception.” | Không. Trả `null` là hoàn tất bình thường; ném exception làm ngắt khởi tạo và đóng resource trước đó. |
| “Tài nguyên nào cũng đóng khi khởi tạo một resource sau thất bại.” | Chỉ những resource đã khởi tạo thành công trước đó được quản lý để đóng; resource chưa được tạo không có object để đóng. |
| “`close()` không thể ném lỗi vì Java tự gọi.” | Sai. `close()` có thể ném exception, trở thành primary hoặc suppressed tùy tình huống. |
| “Chỉ cần `getCause()` để xem lỗi đóng tài nguyên.” | Trong try-with-resources, lỗi đóng phát sinh khi đã có primary thường ở `getSuppressed()`. |
| “Nếu trong thân `try` có exception, chắc chắn có suppressed exception.” | Không. Nếu đóng bình thường hoặc resource là `null`, có thể không có suppressed nào. |
| “Java 9 `try (resource)` cho phép gán lại biến resource tùy ý.” | Không. Biến dùng trong resource specification phải final/effectively final và đã được gán hợp lệ. |
| “Nếu resource runtime là `null`, compiler khỏi xét checked exception của `close()`.” | Nghĩa vụ compile time được xác định từ hợp đồng kiểu tĩnh, không chỉ giá trị runtime. |
| “Try-with-resources đảm bảo close thành công trong mọi hoàn cảnh.” | Java chỉ cố gọi `close()` khi rời phạm vi; lỗi đóng, crash hoặc chấm dứt cưỡng bức vẫn có thể xảy ra. |

## 20. Tình huống tự kiểm tra

**Câu 1.** `try (Resource r = null) { System.out.println("ok"); }`, với `Resource` là `AutoCloseable`. Có in `ok` không? `close()` có được gọi không?  
**Đáp án:** Có in `ok` nếu thân `try` không ném lỗi; `close()` không được gọi trên `r` vì nó bằng `null`.

**Câu 2.** Trong thân `try`, chương trình gọi `r.read()` khi `r == null`. Có phải lỗi do cleanup tự động không?  
**Đáp án:** Không. `NullPointerException` (nếu có) phát sinh từ việc sử dụng tham chiếu `null` trong thân `try`. Bước cleanup vẫn bỏ qua resource `null`.

**Câu 3.** Có ba resource A, B, C; B bằng `null` còn A/C khác `null`. Thứ tự đóng là gì?  
**Đáp án:** C rồi A. Java xét B ở giữa nhưng không gọi `close()` vì B bằng `null`.

**Câu 4.** Factory tạo resource A thành công, sau đó factory tạo B trả `null`. Chương trình có tiếp tục khởi tạo C không?  
**Đáp án:** Có, nếu không có exception khác. Trả `null` bình thường không cắt ngang resource initialization.

**Câu 5.** Factory tạo A thành công, factory tạo B ném `IOException`. Thân `try` có chạy không?  
**Đáp án:** Không. Java cố đóng A trước khi exception khởi tạo B được xử lý hoặc lan truyền.

**Câu 6.** Thân `try` ném exception A, `close()` ném B. Caller nhận loại nào làm primary?  
**Đáp án:** Với try-with-resources, A là primary, B thường được đính kèm trong `A.getSuppressed()`.

**Câu 7.** Thân `try` thành công nhưng `close()` ném B. B có tự biến mất vì đó là cleanup tự động không?  
**Đáp án:** Không. B trở thành exception chính nếu không có exception chính từ thân `try`.

**Câu 8.** `try (AutoCloseable r = ...)` có thể buộc xử lý checked `Exception` không, dù tại runtime `r` đôi khi bằng `null`?  
**Đáp án:** Có. Hợp đồng kiểu tĩnh `AutoCloseable.close()` khai báo `throws Exception`, được compiler xét khi phân tích.

**Câu 9.** Java 17 có cho `Resource r = null; try (r) {...}` không?  
**Đáp án:** Có nếu `r` là final/effectively final và đã được gán trước khi dùng; vì `r` bằng `null` nên không gọi `close()`.

**Câu 10.** Nếu `null` là tình huống không hợp lệ đối với API, có nên để thân `try` tự phát sinh NPE ở một lệnh ngẫu nhiên không?  
**Đáp án:** Nên xác thực sớm bằng hợp đồng rõ, ví dụ `Objects.requireNonNull`, hoặc để factory ném exception phù hợp thay vì trả `null` mơ hồ.

## 21. Checklist khi review try-with-resources có thể nhận `null`

1. **Hợp đồng của factory:** có thể trả `null` hay bắt buộc trả object? Đây là trường hợp hợp lệ hay bug?
2. **Loại tài nguyên:** resource có triển khai `AutoCloseable` không, và `close()` có thể ném checked exception nào?
3. **Lúc khởi tạo:** biểu thức trả `null` bình thường hay ném exception? Hai đường này khác nhau.
4. **Thân `try`:** có dereference tài nguyên chưa được kiểm tra `null` không?
5. **Lời gọi `close()`:** chỉ xảy ra với tham chiếu khác `null` đã được khởi tạo thành công.
6. **Nhiều resource:** thứ tự khởi tạo trái→phải, thứ tự đóng phải→trái, bỏ qua null.
7. **Khởi tạo một phần:** nếu resource sau thất bại, resource trước đã mở có được cố đóng?
8. **Exception chính/phụ:** khi thân và `close()` cùng lỗi, caller có kiểm tra `getSuppressed()` không?
9. **Cú pháp Java 9+:** dùng `try (resource)` thì biến ngoài có final/effectively final và definite assignment?
10. **Bảo toàn thông tin:** có tránh `finally` tự ném lỗi mới làm che lỗi chính hay không?
11. **Quyền sở hữu:** tài nguyên có bị đóng hai lần hoặc dùng sau khi đóng vì được chia sẻ không?
12. **Kiểm thử:** có bao phủ resource khác `null`, resource `null`, lỗi khởi tạo và lỗi `close()`?

## 22. Ghi nhớ

**Try-with-resources tự động cố đóng tài nguyên triển khai `AutoCloseable`, nhưng chỉ gọi `close()` trên các tham chiếu khác `null` đã được khởi tạo thành công.** Một biến tài nguyên bằng `null` không tự làm câu lệnh ném `NullPointerException`, thân `try` vẫn chạy, và Java bỏ qua lời gọi `close()` cho biến đó. Tuy vậy, bất kỳ lệnh nào trong thân `try` cố dùng object bằng `null` vẫn có thể ném `NullPointerException`.

Với nhiều tài nguyên, Java khởi tạo từ trái sang phải, đóng từ phải sang trái và bỏ qua những tài nguyên `null`. Nếu một biểu thức khởi tạo **ném exception**, thân `try` không được vào; các tài nguyên trước đó đã mở được cố đóng. Nếu `close()` thất bại, lỗi đóng có thể trở thành primary khi thân thành công, hoặc suppressed khi đã có lỗi chính.

Hãy coi sự vắng mặt của tài nguyên là **quyết định thiết kế hợp đồng API**, không phải khả năng mà try-with-resources tự “chữa” cho chương trình. Khi tài nguyên là bắt buộc, xác thực rõ ràng; khi tài nguyên là tùy chọn, xử lý nhánh `null` có chủ đích, và để try-with-resources đảm nhiệm cleanup.
