# Interface lồng trong lớp và interface lồng trong interface

Bài này giải thích cách khai báo, truy cập và sử dụng một interface được đặt bên trong lớp hoặc bên trong một interface khác trong Java. Hai trường hợp có cùng quy tắc cốt lõi: member interface luôn là kiểu `static`, nên nó không cần một đối tượng của kiểu bao ngoài.

## 1. Khái niệm

**Nested interface** là interface được khai báo bên trong một kiểu khác. Khi interface được khai báo trực tiếp như thành viên của một lớp hoặc interface, nó được gọi là **member interface**.

- **Interface lồng trong lớp:** nhóm một hợp đồng nhỏ với lớp liên quan, chẳng hạn callback chỉ phục vụ một API cụ thể.
- **Interface lồng trong interface:** nhóm một kiểu phụ trợ với hợp đồng API mà nó mô tả, chẳng hạn `Listener` bên trong `EventSource`.
- Interface lồng vẫn là một kiểu độc lập. Nó có thể được lớp khác triển khai, được dùng làm kiểu tham số hoặc kiểu trả về, và có thể là kiểu đích của lambda nếu chỉ có một phương thức trừu tượng.

## 2. Quy tắc ngôn ngữ Java

### Interface lồng trong lớp

```java
class TaskRunner {
    public interface CompletionCallback {
        void onComplete(String result);
    }
}
```

- `CompletionCallback` là member interface của `TaskRunner` và **ngầm định là `static`**, dù từ khóa `static` không xuất hiện. Viết `public static interface CompletionCallback` cũng hợp lệ nhưng `static` là dư thừa.
- Trong một lớp, interface lồng có thể dùng mức truy cập `public`, `protected`, `private` hoặc package-private. Chọn mức truy cập theo nơi cần sử dụng hợp đồng.
- Từ bên ngoài lớp bao ngoài, tên kiểu thường được viết đầy đủ là `TaskRunner.CompletionCallback`. Bên trong phạm vi có thể nhìn thấy tên thành viên, có thể dùng tên ngắn `CompletionCallback`.
- Vì interface lồng là `static`, nó không giữ tham chiếu ngầm tới một đối tượng `TaskRunner`. Không cần tạo `TaskRunner` để truy cập kiểu này.
- Khai báo interface bên trong một lớp **không tự động làm cho lớp bao ngoài triển khai interface đó**. Nếu cần triển khai, phải khai báo `implements TaskRunner.CompletionCallback` ở một lớp phù hợp.

### Interface lồng trong interface

```java
interface EventSource {
    void start();

    interface Listener {
        void onEvent(String event);
    }
}
```

- `Listener` được ngầm định là `public static`. Có thể ghi rõ `public static interface Listener`, nhưng hai từ khóa này là dư thừa trong ngữ cảnh đó.
- Từ bên ngoài, tên kiểu là `EventSource.Listener`. Kiểu lồng vẫn chịu ảnh hưởng bởi khả năng truy cập của `EventSource`: nếu interface bao ngoài không thể truy cập từ một nơi nào đó, tên kiểu lồng cũng không thể được dùng từ nơi đó.
- Các phương thức thông thường khai báo trong interface là `public abstract` ngầm định, trừ khi được khai báo với dạng khác được Java cho phép như `default`, `static` hoặc `private` (private methods trong interface được hỗ trợ từ Java 9).
- Không khai báo `private` hoặc `protected` cho member type trong interface; member type của interface luôn công khai và tĩnh theo quy tắc ngôn ngữ.

### Điểm chung cần nhớ

1. Member interface luôn `static`; không dùng cú pháp tạo đối tượng kiểu `outer.new NestedInterface()`.
2. Interface không thể được khởi tạo trực tiếp bằng `new`. Hãy cung cấp một lớp triển khai, lớp ẩn danh hoặc lambda phù hợp.
3. Tên kiểu lồng được phân tách bằng dấu chấm, ví dụ `TaskRunner.CompletionCallback` và `EventSource.Listener`.
4. Nếu interface chỉ có một phương thức trừu tượng, nó là functional interface và có thể dùng làm kiểu đích cho lambda. Các phương thức `default` và `static` không làm tăng số phương thức trừu tượng.

## 3. Ví dụ chạy được với Java 17+

Lưu toàn bộ đoạn mã sau vào tệp `NestedInterfacesDemo.java`. Ví dụ có một interface lồng trong lớp `NestedInterfacesDemo` và một interface lồng trong interface `MessageSource`.

```java
public class NestedInterfacesDemo {
    // Member interface trong lớp: static là ngầm định.
    public interface CompletionCallback {
        void onComplete(String message);
    }

    public static void run(CompletionCallback callback) {
        callback.onComplete("job done");
    }

    public static void main(String[] args) {
        CompletionCallback callback =
                message -> System.out.println("callback: " + message);
        run(callback);

        // Listener là member interface của MessageSource.
        MessageSource.Listener listener =
                message -> System.out.println("event: " + message);

        MessageSource source = (target, message) -> target.onMessage(message);
        source.publish(listener, "ready");
    }
}

interface MessageSource {
    void publish(Listener listener, String message);

    // Trong interface, Listener ngầm định là public static.
    interface Listener {
        void onMessage(String message);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac NestedInterfacesDemo.java
java NestedInterfacesDemo
```

Kết quả stdout chính xác:

```text
callback: job done
event: ready
```

Trong ví dụ, `CompletionCallback` là kiểu tham số cho `run`. Lambda cung cấp phần triển khai của `onComplete`. Tương tự, `MessageSource.Listener` mô tả cách nhận thông điệp; lambda thứ hai triển khai listener, còn lambda cho `MessageSource` cung cấp hành vi của phương thức `publish`.

## 4. Truy cập và triển khai interface lồng

### Dùng tên kiểu đầy đủ

```java
TaskRunner.CompletionCallback callback = result ->
        System.out.println(result);

EventSource.Listener listener = event ->
        System.out.println("Nhận sự kiện: " + event);
```

Đây là cách viết thường dùng khi tham chiếu từ một lớp khác. Kiểu lồng vẫn được truy cập qua kiểu bao ngoài, không qua một đối tượng của kiểu bao ngoài.

### Dùng lớp triển khai tường minh

```java
class ConsoleListener implements EventSource.Listener {
    @Override
    public void onEvent(String event) {
        System.out.println("Nhận sự kiện: " + event);
    }
}
```

`ConsoleListener` triển khai hợp đồng `EventSource.Listener`. Vì `onEvent` là phương thức `public` của interface, phương thức triển khai cũng phải có quyền truy cập `public`; giảm mức truy cập sẽ gây lỗi biên dịch.

## 5. Khi nào nên lồng interface?

- Đặt interface trong lớp khi hợp đồng gắn chặt với lớp đó và không cần trở thành khái niệm độc lập trong API. Ví dụ: callback riêng cho một bộ xử lý công việc.
- Đặt interface trong interface khi kiểu phụ trợ có ý nghĩa như một phần của hợp đồng công khai. Ví dụ: `EventSource.Listener` mô tả cách nhận sự kiện do nguồn sự kiện phát ra.
- Để interface ở cấp cao nhất khi nhiều lớp hoặc nhiều gói cần sử dụng nó độc lập. Cách này giúp tên kiểu ngắn hơn và tránh phụ thuộc không cần thiết vào kiểu bao ngoài.
- Giữ độ sâu lồng hợp lý. Các tên như `A.B.C.Listener` có thể làm API khó đọc nếu việc lồng không đem lại lợi ích rõ ràng.

## 6. Lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| Viết `new TaskRunner.CompletionCallback()` để tạo interface | Interface không thể được khởi tạo trực tiếp. Dùng lambda nếu đó là functional interface, hoặc viết lớp triển khai/lớp ẩn danh. |
| Cho rằng cần `new TaskRunner()` để dùng `TaskRunner.CompletionCallback` | Member interface là `static`, nên không cần đối tượng của lớp bao ngoài. |
| Nghĩ lớp bao ngoài tự động triển khai interface lồng | Việc khai báo kiểu lồng không tạo quan hệ `implements`. Khai báo triển khai một cách tường minh ở lớp cần thiết. |
| Quên tên bao ngoài khi dùng kiểu từ nơi khác | Dùng dạng `Outer.Nested`, chẳng hạn `EventSource.Listener`, và bảo đảm kiểu bao ngoài có thể truy cập được. |
| Nghĩ interface lồng trong interface có thể là `private` hoặc `protected` | Member type của interface ngầm định là `public static`; không thể giảm quyền truy cập của nó bằng `private` hoặc `protected`. |
| Dùng lambda cho interface có nhiều phương thức trừu tượng | Lambda chỉ phù hợp khi kiểu đích là functional interface, tức có đúng một phương thức trừu tượng theo quy tắc Java. |
| Cho rằng interface lồng có thể truy cập trực tiếp trường instance của lớp bao ngoài | Vì member interface là `static`, nó không có đối tượng bao ngoài ngầm định. Muốn dùng dữ liệu instance, hãy truyền đối tượng hoặc giá trị cần thiết vào. |

## 7. Checklist nhanh

- [ ] Xác định interface được khai báo trong lớp hay trong interface.
- [ ] Dùng tên kiểu đúng: `Outer.Nested` khi tham chiếu từ bên ngoài phạm vi bao ngoài.
- [ ] Kiểm tra mức truy cập của kiểu bao ngoài và interface lồng.
- [ ] Nhớ rằng member interface ngầm định là `static`; không cần tạo đối tượng bao ngoài.
- [ ] Chọn lambda chỉ khi interface là functional interface; nếu không, cung cấp một lớp triển khai đầy đủ.
- [ ] Với ví dụ chạy được, kiểm tra tên tệp trùng tên lớp `public`, lệnh biên dịch và stdout.

## 8. Kết luận về quy tắc

Khác biệt chính giữa hai vị trí khai báo nằm ở mức truy cập ngầm định: interface lồng trong lớp có mức truy cập do người viết chọn, còn member interface trong interface luôn là `public static`. Cả hai đều là member interface tĩnh, được tham chiếu bằng tên kiểu bao ngoài và có thể được triển khai hoặc dùng làm kiểu đích cho lambda khi thỏa điều kiện functional interface.
