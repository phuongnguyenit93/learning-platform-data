# Interface là kiểu tham chiếu và ngầm định abstract trong Java

## 1. Kiểu tham chiếu và đối tượng thực tế

Tên interface là một **kiểu tham chiếu**. Nó có thể xuất hiện ở khai báo biến, tham số, kiểu trả về, field và đối số generic, giống như các kiểu tham chiếu khác.

```java
interface MessageSender {
    void send(String message);
}

final class ConsoleSender implements MessageSender {
    @Override
    public void send(String message) {
        System.out.println("Sent: " + message);
    }

    public void clearHistory() {
        System.out.println("History cleared");
    }
}

public class Main {
    public static void main(String[] args) {
        MessageSender sender = new ConsoleSender();
        sender.send("hello");
        System.out.println(sender instanceof MessageSender);
    }
}
```

Kết quả:

```text
Sent: hello
true
```

Có ba điều cần tách biệt:

- **Kiểu khai báo của biến** là `MessageSender`, nên compiler chỉ cho gọi các thành viên có thể truy cập qua kiểu đó.
- **Kiểu runtime của đối tượng** là `ConsoleSender`, nên lời gọi phương thức instance được dispatch đến implementation thích hợp của đối tượng.
- Quan hệ `implements` cho phép gán `ConsoleSender` vào biến `MessageSender`; phép gán không tạo ra một đối tượng interface riêng.

Dù đối tượng thực tế có phương thức `clearHistory()`, biểu thức `sender.clearHistory()` vẫn không biên dịch vì phương thức đó không thuộc API được khai báo bởi kiểu `MessageSender`.

## 2. Vì sao interface ngầm định abstract?

Một khai báo interface vốn đã là trừu tượng. Hai cách viết sau có cùng ý nghĩa về tính abstract:

```java
interface Task {
    void execute();
}

abstract interface LegacyTask {
    void execute();
}
```

Cách viết thông dụng là `interface Task`; từ khóa `abstract` ở khai báo interface là dư thừa. Không thể tạo instance trực tiếp bằng `new Task()` vì interface không có constructor và không định nghĩa một implementation cụ thể cho mọi hành vi.

Một lớp concrete triển khai `Task` phải cung cấp implementation hợp lệ cho các phương thức abstract còn thiếu, hoặc thừa hưởng implementation phù hợp. Một lớp vẫn còn thiếu phương thức có thể được khai báo `abstract`.

**Không suy ra rằng mọi phương thức trong interface đều abstract.** Ví dụ, Java hiện đại cho phép phương thức `default`, `static` và `private` có thân. Một phương thức instance thông thường được khai báo không có thân trong interface có ngữ nghĩa `public abstract` dù không viết hai modifier đó.

## 3. Anonymous class và lambda không phải constructor của interface

Java cho phép tạo một đối tượng triển khai thông qua anonymous class:

```java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("running");
    }
};
task.run();
```

Đối tượng trên thuộc một lớp ẩn danh do cú pháp tạo ra; không có instance trực tiếp của `Runnable`. Với functional interface, lambda cũng có thể cung cấp implementation:

```java
Runnable task = () -> System.out.println("running");
task.run();
```

Lambda chỉ áp dụng khi interface thỏa điều kiện functional interface: có một abstract method phù hợp sau khi xét các quy tắc Java. Phương thức `default`, `static` và `private` không được tính như abstract method bổ sung.

## 4. Những lỗi cần nhận diện

| Cách viết | Vì sao |
| --- | --- |
| `new Task()` | Không thể khởi tạo interface trực tiếp. |
| Lớp concrete bỏ sót abstract method | Không hoàn tất hợp đồng kiểu. |
| Implementation có cùng tên nhưng khác tham số | Đó có thể là overload, không phải override. |
| Gọi phương thức riêng của class qua biến interface | Compiler kiểm tra theo kiểu khai báo của biểu thức. |
| Cho rằng `default` nghĩa là mọi phương thức interface đều có body | `default` chỉ áp dụng cho loại phương thức được khai báo theo cú pháp đó. |

**Tự kiểm tra:** Với `MessageSender sender = new ConsoleSender()`, kiểu nào quyết định các phương thức có thể gọi ở thời điểm biên dịch? `MessageSender`. Kiểu nào cung cấp implementation chạy cho `send`? Đối tượng thực tế `ConsoleSender`.