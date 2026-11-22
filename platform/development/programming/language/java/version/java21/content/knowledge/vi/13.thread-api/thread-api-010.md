# Kiểm soát việc kế thừa InheritableThreadLocal qua thread builder

Khi tạo thread con, Java mặc định truyền các giá trị hiện có của **InheritableThreadLocal** từ thread tạo sang thread mới. Trong Java 21, có thể kiểm soát hành vi này bằng **Thread.Builder.inheritInheritableThreadLocals(boolean)**. Đặt giá trị **false** để thread mới không nhận các giá trị kế thừa đó; giá trị mặc định là **true**.

Thiết lập này có trên cả builder tạo platform thread và builder tạo virtual thread. Nó hữu ích khi tạo tác vụ độc lập, không muốn tự động mang theo context của thread hiện tại, hoặc khi muốn xác định rõ dữ liệu nào được truyền qua ranh giới tạo thread.

## 1. InheritableThreadLocal hoạt động khi thread được tạo

**ThreadLocal<T>** giữ một giá trị riêng cho từng thread. Giá trị của ThreadLocal thông thường không được truyền từ thread cha sang thread con.

**InheritableThreadLocal<T>** mở rộng ThreadLocal và bổ sung cơ chế kế thừa. Khi một thread mới được tạo, nó nhận giá trị ban đầu từ các InheritableThreadLocal mà thread tạo nó đang có giá trị. Mặc định, giá trị ở thread con giống giá trị của thread cha.

~~~java
class InheritableContext {
    static final InheritableThreadLocal<String> REQUEST_ID =
            new InheritableThreadLocal<>();

    static void run() throws InterruptedException {
        REQUEST_ID.set("request-42");

        Thread child = new Thread(() ->
                System.out.println(REQUEST_ID.get()));

        child.start();
        child.join();
    }
}
~~~

Thread con trong ví dụ nhận giá trị **request-42**. Việc kế thừa diễn ra lúc đối tượng Thread con được tạo, không phải lúc gọi **start()**. Vì vậy, nếu giá trị ở thread cha thay đổi sau khi thread con đã được tạo, giá trị đã kế thừa của thread con không tự cập nhật theo.

**ThreadLocal** thông thường không có hành vi kế thừa này. Nếu thread con gọi **get()** trên một ThreadLocal chưa được đặt giá trị, nó nhận giá trị khởi tạo theo **initialValue()** hoặc supplier được cung cấp cho **ThreadLocal.withInitial(...)**.

## 2. Mặc định builder cho phép kế thừa

Java 21 cung cấp hai builder:

- **Thread.ofPlatform()** tạo platform thread.
- **Thread.ofVirtual()** tạo virtual thread.

Cả hai đều dùng phương thức **inheritInheritableThreadLocals(boolean)** được khai báo trên Thread.Builder. Mặc định là **true**, nên nếu không cấu hình, thread mới tiếp tục nhận các giá trị InheritableThreadLocal từ thread tạo nó.

~~~java
class DefaultInheritance {
    static final InheritableThreadLocal<String> CONTEXT =
            new InheritableThreadLocal<>();

    static void startChildren() throws InterruptedException {
        CONTEXT.set("tenant-A");

        Thread platform = Thread.ofPlatform()
                .start(() -> System.out.println(CONTEXT.get()));

        Thread virtual = Thread.ofVirtual()
                .start(() -> System.out.println(CONTEXT.get()));

        platform.join();
        virtual.join();
    }
}
~~~

Hai thread được tạo trong ví dụ đều kế thừa giá trị **tenant-A**. Nếu không muốn truyền context, cần cấu hình builder trước khi tạo thread.

## 3. Tắt kế thừa bằng inheritInheritableThreadLocals(false)

Gọi **inheritInheritableThreadLocals(false)** trên builder để thread được tạo không nhận các giá trị ban đầu từ InheritableThreadLocal của thread tạo nó:

~~~java
class IsolatedThread {
    static final InheritableThreadLocal<String> REQUEST_ID =
            new InheritableThreadLocal<>();

    static void startTask() throws InterruptedException {
        REQUEST_ID.set("request-42");

        Thread child = Thread.ofPlatform()
                .inheritInheritableThreadLocals(false)
                .start(() -> System.out.println(REQUEST_ID.get()));

        child.join();
    }
}
~~~

Với InheritableThreadLocal mặc định, **get()** ở thread con trả về null vì thread con không nhận giá trị **request-42**. Nếu lớp InheritableThreadLocal ghi đè **initialValue()**, thread con sẽ nhận giá trị khởi tạo do phương thức đó cung cấp khi gọi get().

Thiết lập này chỉ kiểm soát việc kế thừa các giá trị ban đầu của InheritableThreadLocal. Nó không xóa dữ liệu static, không ngăn task truy cập object được truyền trực tiếp qua tham số hoặc lambda, và không thay thế việc quản lý context của ứng dụng.

## 4. Áp dụng cho virtual thread

Virtual thread cũng hỗ trợ InheritableThreadLocal. Nếu được tạo bằng builder mặc định, nó kế thừa giá trị từ thread tạo nó. Có thể tắt việc kế thừa tương tự platform thread:

~~~java
class IsolatedVirtualThread {
    static final InheritableThreadLocal<String> SECURITY_CONTEXT =
            new InheritableThreadLocal<>();

    static void runTask() throws InterruptedException {
        SECURITY_CONTEXT.set("user-17");

        Thread task = Thread.ofVirtual()
                .name("independent-task")
                .inheritInheritableThreadLocals(false)
                .start(() -> {
                    System.out.println(SECURITY_CONTEXT.get());
                });

        task.join();
    }
}
~~~

Virtual thread trong ví dụ không nhận giá trị **user-17**. Việc tắt kế thừa có thể hữu ích cho tác vụ nền không nên mang theo context của request tạo ra nó. Nếu tác vụ thực sự cần user ID, tenant hoặc thông tin trace, hãy truyền dữ liệu cần thiết một cách tường minh.

Không nên mặc định tắt kế thừa cho mọi thread mà không kiểm tra ứng dụng. Một số thư viện có thể dựa vào context được truyền qua InheritableThreadLocal, bao gồm context class loader. Khi tắt kế thừa, thread mới không nhận các giá trị ban đầu đó từ thread tạo nó.

## 5. Cấu hình khi tạo ThreadFactory

Nếu API nhận **ThreadFactory** thay vì Thread trực tiếp, có thể tạo factory từ builder đã cấu hình. Mọi thread do factory này tạo sẽ dùng chính sách kế thừa đã chọn:

~~~java
import java.util.concurrent.ThreadFactory;

class IsolatedThreadFactory {
    static ThreadFactory create() {
        return Thread.ofVirtual()
                .name("worker-", 0)
                .inheritInheritableThreadLocals(false)
                .factory();
    }
}
~~~

Factory có thể được dùng ở nơi cần một ThreadFactory, ví dụ executor tạo một thread mới cho mỗi task:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;

class IsolatedExecutor {
    static void runTasks() {
        ThreadFactory factory = Thread.ofVirtual()
                .name("task-", 0)
                .inheritInheritableThreadLocals(false)
                .factory();

        try (ExecutorService executor =
                     Executors.newThreadPerTaskExecutor(factory)) {
            executor.submit(() -> performWork());
        }
    }

    private static void performWork() {
        System.out.println(Thread.currentThread().isVirtual());
    }
}
~~~

**newThreadPerTaskExecutor(factory)** tạo thread mới cho từng task; factory ở ví dụ tạo virtual thread không kế thừa InheritableThreadLocal. Phương thức này có từ Java 21. Nếu dùng một executor tái sử dụng worker, giá trị thread-local gắn với worker có vòng đời khác với context của từng task; không nên coi cấu hình lúc tạo worker là cơ chế truyền context theo từng lần submit.

Khi dùng factory, việc kế thừa được quyết định lúc factory thực sự tạo từng Thread. Tạo builder hoặc factory không chụp sẵn giá trị InheritableThreadLocal của một request để dùng cho mọi thread trong tương lai.

## 6. Thời điểm kế thừa và childValue()

**InheritableThreadLocal.childValue(parentValue)** cho phép xác định giá trị ban đầu của thread con dựa trên giá trị ở thread cha. Phương thức được gọi trong thread tạo con, trước khi thread con bắt đầu chạy. Cài đặt mặc định chỉ trả về chính đối tượng đầu vào.

~~~java
import java.util.ArrayList;
import java.util.List;

class CopyInheritedContext {
    static final InheritableThreadLocal<List<String>> TAGS =
            new InheritableThreadLocal<>() {
                @Override
                protected List<String> childValue(List<String> parentValue) {
                    return parentValue == null
                            ? null
                            : new ArrayList<>(parentValue);
                }
            };

    static void startChild() throws InterruptedException {
        TAGS.set(new ArrayList<>(List.of("billing")));

        Thread child = Thread.ofPlatform().start(() -> {
            TAGS.get().add("child");
            System.out.println(TAGS.get());
        });

        child.join();
        System.out.println(TAGS.get()); // [billing]
    }
}
~~~

Vì **childValue()** tạo một ArrayList mới, thread con có thể thay đổi danh sách của mình mà không sửa danh sách của thread cha. Nếu dùng hành vi mặc định, hai thread sẽ giữ cùng một tham chiếu tới object danh sách; bản thân InheritableThreadLocal không tự sao chép hoặc làm object trở nên thread-safe.

Khi builder đặt **inheritInheritableThreadLocals(false)**, thread mới không nhận các giá trị kế thừa và không cần gọi **childValue()** để tạo chúng. Vì thế, hãy chọn giữa hai cách theo nhu cầu:

- Dùng **childValue()** khi muốn kế thừa nhưng cần biến đổi hoặc sao chép giá trị cho thread con.
- Dùng **inheritInheritableThreadLocals(false)** khi thread mới không nên nhận các giá trị kế thừa.

## 7. Phân biệt kế thừa với truyền context tường minh

Kế thừa tự động thuận tiện khi mọi thread con cần cùng một phần context của thread tạo nó. Tuy nhiên, nó cũng tạo ra phụ thuộc ngầm: một tác vụ có thể nhận thông tin mà chữ ký phương thức không thể hiện.

Với tác vụ độc lập, có thể tắt kế thừa và truyền đúng dữ liệu cần dùng qua tham số:

~~~java
class ExplicitContext {
    static Thread startAuditTask(String auditId) {
        return Thread.ofVirtual()
                .inheritInheritableThreadLocals(false)
                .start(() -> writeAuditRecord(auditId));
    }

    private static void writeAuditRecord(String auditId) {
        System.out.println("Audit: " + auditId);
    }
}
~~~

Cách truyền tường minh giúp người đọc thấy dữ liệu đầu vào của tác vụ và tránh mang theo toàn bộ context không cần thiết. Nếu tác vụ cần một số trường context, hãy tạo một đối tượng dữ liệu nhỏ, bất biến và truyền đối tượng đó thay vì dựa vào nhiều biến thread-local ngầm.

## 8. Những điểm cần lưu ý khi tắt kế thừa

| Thành phần | Ảnh hưởng của inheritInheritableThreadLocals(false) |
|---|---|
| **InheritableThreadLocal** | Không nhận giá trị ban đầu từ thread tạo |
| **ThreadLocal** thông thường | Vốn không được kế thừa; không thay đổi hành vi |
| **initialValue()** hoặc supplier | Vẫn được dùng khi thread con gọi get() mà chưa có giá trị |
| **childValue()** | Không được dùng để tạo giá trị kế thừa cho thread này |
| **Context class loader** | Không nhận giá trị kế thừa theo cơ chế InheritableThreadLocal |
| Tham số, lambda capture, static state | Không bị thiết lập này ngăn truy cập |

Không nhầm việc tắt kế thừa với việc xóa context hiện tại của thread cha. Giá trị trong thread cha vẫn còn nguyên. Thiết lập chỉ ảnh hưởng đến thread mới được tạo từ builder hoặc factory đã cấu hình.

Nếu một thư viện cần context class loader hoặc một InheritableThreadLocal cụ thể, hãy truyền cấu hình phù hợp hoặc cung cấp dữ liệu đó theo cách tường minh. Kiểm tra hành vi của thư viện sau khi thay đổi chính sách kế thừa.

## 9. Checklist sử dụng Thread.Builder

- [ ] Xác định thread mới có thực sự cần kế thừa InheritableThreadLocal hay không.
- [ ] Nhớ rằng mặc định của Thread.Builder là kế thừa (**true**).
- [ ] Gọi **inheritInheritableThreadLocals(false)** trước **start()**, **unstarted()** hoặc **factory()** nếu cần tắt kế thừa.
- [ ] Áp dụng được cùng thiết lập cho **Thread.ofPlatform()** và **Thread.ofVirtual()**.
- [ ] Hiểu rằng việc kế thừa diễn ra lúc Thread được tạo, trước khi thread bắt đầu chạy.
- [ ] Dùng **childValue()** nếu muốn biến đổi hoặc sao chép giá trị kế thừa.
- [ ] Không giả định object mutable được tự động sao chép hoặc thread-safe.
- [ ] Kiểm tra ảnh hưởng tới context class loader và thư viện phụ thuộc vào context.
- [ ] Truyền tường minh dữ liệu quan trọng khi tác vụ chỉ cần một phần context.
- [ ] Kiểm tra ThreadFactory và executor sử dụng builder đã cấu hình đúng chính sách.

## Tài liệu tham khảo

- [Java SE 21 API: Thread.Builder](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.html)
- [Java SE 21 API: Thread.Builder.OfPlatform](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.OfPlatform.html)
- [Java SE 21 API: Thread.Builder.OfVirtual](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.OfVirtual.html)
- [Java SE 21 API: InheritableThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InheritableThreadLocal.html)
- [Java SE 21 API: Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html)
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444)
