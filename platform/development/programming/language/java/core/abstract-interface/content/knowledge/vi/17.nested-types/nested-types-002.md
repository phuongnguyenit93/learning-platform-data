# Interface lồng trong Java: ngầm định static và không cần đối tượng bao ngoài

Một **member interface** khai báo trực tiếp bên trong class hay interface đều là kiểu lồng `static`, dù không viết từ khóa `static`. Điều quan trọng không chỉ là cú pháp `Outer.Listener` mà là hiểu kiểu đó **không mang theo một đối tượng `Outer`**. Bài này phân biệt hợp đồng lồng, đối tượng triển khai và nhu cầu dùng trạng thái của lớp bao ngoài.

## 1. `static` thuộc về kiểu, không thuộc về phương thức

```java
class Dispatcher {
    interface Listener {
        void onEvent(String event);
    }
}
```

`Dispatcher.Listener` là một member interface tĩnh. Phương thức `onEvent` vẫn là phương thức instance thuộc về **đối tượng triển khai `Listener`**. Interface lồng trong interface khác còn ngầm định `public`; interface lồng trong class có thể mang các mức truy cập thông thường của member type.

Việc khai báo `static` cho kiểu không biến `onEvent` thành phương thức tĩnh, cũng không buộc lớp triển khai là `static`.

## 2. Kiểu lồng và lớp triển khai có vòng đời độc lập

```java
class Dispatcher {
    interface Listener {
        void onEvent(String message);
    }

    class BoundListener implements Listener {
        @Override public void onEvent(String message) {
            System.out.println(message);
        }
    }
}
```

Ở nơi truy cập được hai kiểu:

```java
Dispatcher.Listener listenerTypeReference; // Chỉ khai báo tham chiếu kiểu
Dispatcher dispatcher = new Dispatcher();
Dispatcher.BoundListener bound = dispatcher.new BoundListener();
```

Kiểu `Dispatcher.Listener` không cần enclosing instance, nhưng `BoundListener` **là inner class không static** nên cần `dispatcher` khi khởi tạo. Nếu thay `BoundListener` bằng lớp cấp cao nhất triển khai `Dispatcher.Listener`, không còn nhu cầu này. Nhu cầu đối tượng bao ngoài thuộc về **lớp triển khai hoặc logic nghiệp vụ**, không thuộc về kiểu interface lồng.

## 3. Vì sao không cần đối tượng bao ngoài?

Một lớp lồng không static (inner class) thường mang theo liên kết với đối tượng bao ngoài đã tạo ra nó. Member interface thì khác: nó là kiểu thành viên static và không giữ một tham chiếu ngầm đến đối tượng Outer.

Điều đó mang lại một số hệ quả thực tế:

- Có thể dùng tên Outer.Listener trong khai báo biến, tham số, kiểu trả về và mệnh đề implements mà không cần có đối tượng Outer.
- Có thể triển khai Outer.Listener trong một class cấp cao nhất hoặc trong một lớp lồng static.
- Không có cú pháp tạo đối tượng bao ngoài kiểu outer.new Listener(); ngoài ra, Listener là interface nên không thể khởi tạo trực tiếp dù có hay không có Outer.
- Các phương thức của interface lồng không có một đối tượng Outer ngầm định để truy cập trực tiếp trường hoặc phương thức instance của Outer. Nếu cần dữ liệu từ một đối tượng Outer, hãy truyền dữ liệu đó qua tham số, cung cấp một phương thức trên Outer, hoặc truyền đối tượng Outer cho lớp triển khai theo thiết kế phù hợp.
- Kiểu lồng có thể truy cập các thành viên static của kiểu bao ngoài theo quy tắc truy cập Java. Điều này không tạo ra một liên kết đến bất kỳ đối tượng Outer nào.

Lưu ý: việc một interface lồng không cần đối tượng bao ngoài không có nghĩa mọi lớp triển khai nó đều không cần đối tượng bao ngoài. Nếu lớp triển khai được khai báo là inner class không static, chính lớp triển khai đó vẫn cần một đối tượng Outer khi tạo instance. Đây là đặc điểm của lớp triển khai, không phải của interface lồng.

## 4. Ví dụ Java chạy được

Ví dụ dưới đây khai báo Listener bên trong Main, sau đó triển khai interface bằng một class cấp cao nhất. ConsoleListener được tạo độc lập với một đối tượng Main; đối tượng Main chỉ được dùng để gọi phương thức publish.

~~~java
public class Main {
    private final String serviceName;

    public Main(String serviceName) {
        this.serviceName = serviceName;
    }

    public interface Listener {
        void onMessage(String message);
    }

    public void publish(String message, Listener listener) {
        listener.onMessage(serviceName + ": " + message);
    }

    public static void main(String[] args) {
        Main service = new Main("Service");
        Main.Listener listener = new ConsoleListener();
        service.publish("ready", listener);
    }
}

final class ConsoleListener implements Main.Listener {
    @Override
    public void onMessage(String message) {
        System.out.println(message);
    }
}
~~~

Lưu nội dung vào tệp Main.java, sau đó chạy bằng Java 17 trở lên:

~~~text
javac Main.java
java Main
~~~

Kết quả stdout chính xác:

~~~text
Service: ready
~~~

Dòng khai báo Main.Listener listener không yêu cầu một đối tượng Main để xác định kiểu Listener. ConsoleListener cũng không phải inner class của Main, nên có thể tạo nó trực tiếp bằng new ConsoleListener(). Phương thức publish được gọi trên service vì phương thức đó sử dụng trường instance serviceName; đây là nhu cầu riêng của hoạt động publish, không phải điều kiện để dùng kiểu Main.Listener.

## 5. Kiểm tra ba câu hỏi độc lập

| Câu hỏi | Cách xác định |
|---|---|
| Có cần tạo `Outer` để **tham chiếu kiểu** `Outer.Listener`? | Không. Member interface luôn static; việc gọi tên kiểu không tạo đối tượng. |
| Có cần `Outer` để **tạo implementation**? | Chỉ khi chính lớp triển khai là inner class không static hoặc constructor của nó cần dữ liệu đó. |
| Có cần `Outer` để **gọi hành vi**? | Tùy API. `publish` là instance method của `Main`, còn `onMessage` chạy trên đối tượng listener. |

## 6. Ba lỗi dễ lẫn

- Viết `outer.new Listener()`: interface không được khởi tạo trực tiếp và member interface không có enclosing instance. Hãy tạo một implementation hợp lệ.
- Viết `new Outer.BoundListener()` cho một **non-static inner class**: kiểu triển khai này cần `outer.new BoundListener()`; tính static của interface nó implements không thay đổi quy tắc đó.
- Truy cập `Outer.this` từ chính member interface như thể có đối tượng `Outer` gắn sẵn: không tồn tại tham chiếu ngầm định như vậy. Nếu hành vi cần trạng thái instance, hãy truyền nó qua phương thức hoặc implementation.

## 7. Tự kiểm tra

Thử đổi `ConsoleListener` trong ví dụ chạy được thành một non-static inner class của `Main`. Khi đó câu lệnh tạo listener phải thay đổi theo cú pháp `service.new ConsoleListener()` (nếu constructor và phạm vi truy cập phù hợp), nhưng khai báo kiểu `Main.Listener` vẫn giữ nguyên. Đây là phép thử ngắn để phân biệt **tính static của hợp đồng** với **vòng đời của lớp triển khai**.

## Ghi nhớ

`static` ở member interface mô tả quan hệ giữa **kiểu** và kiểu bao ngoài. Nó không quyết định liệu một implementation có enclosing instance, cũng không biến các phương thức trừu tượng thành phương thức static.
