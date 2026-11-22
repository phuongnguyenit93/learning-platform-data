# Java: Có phương thức giống nhau vẫn chưa phải kiểu con

Trong Java, **một lớp không tự động trở thành kiểu con của interface hoặc lớp khác chỉ vì nó có phương thức cùng tên, cùng tham số và cùng kiểu trả về**. Quan hệ kiểu con phải được thiết lập theo hệ thống kiểu danh nghĩa (*nominal typing*) qua `implements`, `extends` hoặc quan hệ kế thừa đã được khai báo. Đây là điểm cốt lõi khi **triển khai hợp đồng** bằng interface.

Sau bài này, bạn có thể giải thích vì sao mã có phương thức phù hợp vẫn không truyền được vào tham số interface, khai báo đúng quan hệ kiểu con và dùng adapter khi không thể sửa lớp có sẵn.

## 1. Chữ ký phương thức và quan hệ kiểu con là hai việc khác nhau

Xét hai khai báo:

```java
interface MessageSender {
    void send(String message);
}

final class ConsoleSender {
    public void send(String message) {
        System.out.println(message);
    }
}
```

`ConsoleSender` có phương thức `send(String)` trùng chữ ký mà `MessageSender` yêu cầu. Nhưng `ConsoleSender` **chưa khai báo `implements MessageSender`**, nên trình biên dịch không coi nó là `MessageSender`.

- **Có phương thức phù hợp** mô tả khả năng gọi một phương thức trên một đối tượng với kiểu đã biết.
- **Là kiểu con** mô tả một quan hệ kiểu được Java công nhận: đối tượng của kiểu con có thể được sử dụng tại vị trí yêu cầu kiểu cha/interface.
- **Triển khai hợp đồng** có hai phần: khai báo tham gia hợp đồng (`implements`) và cung cấp hoặc kế thừa các phương thức trừu tượng cần thiết với cách triển khai hợp lệ.

Java dùng **nominal typing** cho các kiểu lớp và interface: danh tính kiểu cùng các quan hệ kế thừa được khai báo quyết định khả năng gán và truyền tham số. Trong hệ thống *structural typing* của một số ngôn ngữ khác, hình dạng thành viên có thể đủ để thỏa mãn một kiểu; đừng áp dụng suy luận đó cho Java.

## 2. Ví dụ không biên dịch dù có phương thức giống nhau

Lưu đoạn dưới đây thành `Main.java` để quan sát lỗi có chủ ý:

```java
public class Main {
    interface MessageSender {
        void send(String message);
    }

    static final class ConsoleSender {
        public void send(String message) {
            System.out.println("Gửi: " + message);
        }
    }

    static void dispatch(MessageSender sender) {
        sender.send("xin chào");
    }

    public static void main(String[] args) {
        ConsoleSender sender = new ConsoleSender();
        dispatch(sender); // Lỗi biên dịch: không phải MessageSender
    }
}
```

Chạy `javac Main.java` sẽ **không biên dịch thành công**. Tại lời gọi `dispatch(sender)`, Java cần một giá trị có thể chuyển thành `MessageSender`, nhưng kiểu `ConsoleSender` không có quan hệ kiểu con tương ứng. Thông báo thường mang ý nghĩa `ConsoleSender cannot be converted to MessageSender`; cách trình bày cụ thể phụ thuộc JDK.

Việc phương thức `send(String)` là `public`, có đúng tên và chạy được khi gọi `sender.send("...")` **không thay thế** khai báo `implements`. Tương tự, phép gán `MessageSender target = new ConsoleSender();` cũng không hợp lệ.

## 3. Giải pháp: khai báo `implements` và thực hiện hợp đồng

Sửa `ConsoleSender` để khai báo chính thức interface. Đây là phiên bản **độc lập, biên dịch và chạy được trên Java 17+**:

```java
public class Main {
    interface MessageSender {
        void send(String message);
    }

    static final class ConsoleSender implements MessageSender {
        @Override
        public void send(String message) {
            System.out.println("Gửi: " + message);
        }
    }

    static void dispatch(MessageSender sender) {
        sender.send("xin chào");
    }

    public static void main(String[] args) {
        ConsoleSender concrete = new ConsoleSender();
        MessageSender abstraction = concrete; // Phép gán hợp lệ
        dispatch(abstraction);
    }
}
```

Biên dịch và chạy:

```bash
javac Main.java
java Main
```

Kết quả stdout:

```text
Gửi: xin chào
```

Lúc này, `ConsoleSender implements MessageSender` thiết lập quan hệ kiểu con, còn `public void send(String)` đáp ứng phương thức trừu tượng. `@Override` giúp trình biên dịch kiểm tra phương thức thực sự ghi đè hoặc triển khai một phương thức từ kiểu cha/interface; annotation này **không tự tạo quan hệ kiểu con**. Với lớp cụ thể khai báo `implements` nhưng chưa triển khai đủ phương thức trừu tượng được yêu cầu, Java báo lỗi biên dịch (hoặc lớp phải là `abstract`).

Điểm quan trọng của đa hình là `dispatch` chỉ phụ thuộc `MessageSender`. Khi chạy, lời gọi `sender.send(...)` được phân phối đến cách triển khai tương ứng với đối tượng thực tế. Người gọi không cần biết đối tượng được tạo từ lớp nào, miễn kiểu của nó thỏa hợp đồng.

## 4. Quan hệ có thể được kế thừa, không cần lặp lại `implements`

Một lớp cũng có thể trở thành kiểu con của interface **gián tiếp** thông qua lớp cha hoặc interface cha. Ví dụ sau là các khai báo minh họa, có thể đặt cùng một tệp Java trong một package thích hợp:

```java
interface Sender {
    void send(String text);
}

class BaseSender implements Sender {
    @Override
    public void send(String text) {
        System.out.println(text);
    }
}

class LoggedSender extends BaseSender {
    // Kế thừa quan hệ Sender và cách triển khai send(String).
}
```

`LoggedSender` không ghi trực tiếp `implements Sender`, nhưng vì `LoggedSender extends BaseSender` và `BaseSender implements Sender`, nên `LoggedSender` vẫn là `Sender`. Phép gán `Sender s = new LoggedSender();` hợp lệ. Lớp con có thể kế thừa phương thức thực thi phù hợp hoặc ghi đè nó theo quy tắc Java.

Tương tự, khi `interface Child extends Parent`, mọi lớp cụ thể triển khai `Child` cũng có quan hệ kiểu con với `Parent`. Điều quyết định vẫn là **chuỗi quan hệ kiểu đã khai báo**, không phải Java tự so khớp các tên phương thức.

## 5. Khi không thể sửa lớp cũ: dùng adapter

Đôi khi bạn sử dụng thư viện ngoài có phương thức đúng nhu cầu nhưng lớp không `implements` interface của ứng dụng. Không thể truyền trực tiếp đối tượng ấy vào API nhận interface. Có thể viết một adapter để **chuyển lời gọi**, giữ ranh giới hợp đồng rõ ràng.

Ví dụ đầy đủ với một *functional interface* (interface có đúng một phương thức trừu tượng):

```java
public class AdapterExample {
    @FunctionalInterface
    interface Printer {
        void print(String text);
    }

    static final class LegacyPrinter {
        public void print(String text) {
            System.out.println("Legacy: " + text);
        }
    }

    static void printNotice(Printer printer) {
        printer.print("ready");
    }

    public static void main(String[] args) {
        LegacyPrinter legacy = new LegacyPrinter();

        // printNotice(legacy); // Không hợp lệ: thiếu quan hệ kiểu con.
        Printer adapter = legacy::print;
        printNotice(adapter);
    }
}
```

```bash
javac AdapterExample.java
java AdapterExample
```

Stdout:

```text
Legacy: ready
```

`legacy::print` là **method reference** được chuyển theo *target type* `Printer` thành một đối tượng thực thi phương thức trừu tượng của functional interface. Nó **không biến `LegacyPrinter` thành kiểu con của `Printer`**. Với interface không phải functional interface, hãy tạo lớp adapter có `implements` và chuyển tiếp từng phương thức cần thiết.

Cách tiếp cận này cũng giải thích vì sao Java cho phép `Runnable task = () -> System.out.println("run");`: lambda được chuyển sang functional interface đích; Java không tự coi một lớp bất kỳ có `run()` là `Runnable`.

## 6. Khai báo `implements` chưa đủ nếu triển khai không đúng

Khi đã khai báo quan hệ kiểu, Java vẫn kiểm tra quy tắc triển khai phương thức. Các trường hợp dễ nhầm:

| Trường hợp | Có đáp ứng `void send(String)` của interface không? | Lý do |
| --- | --- | --- |
| `public void send(String text)` | Có | Chữ ký và mức truy cập phù hợp. |
| `void send(String text)` (package-private) | Không | Không thể giảm mức truy cập `public` của phương thức interface. |
| `private void send(String text)` | Không | Phương thức `private` không triển khai phương thức `public` của interface. |
| `public void send(Object text)` | Không | Khác kiểu tham số; đây là overload, không phải override. |
| `public static void send(String text)` | Không | Phương thức `static` không thực thi phương thức instance của interface. |

Với hợp đồng có kiểu trả về, Java còn kiểm tra kiểu trả về tương thích (có quy tắc *covariant return* cho kiểu tham chiếu), ngoại lệ checked được khai báo và các quy tắc ghi đè khác. Việc chỉ nhìn thấy hai tên phương thức giống nhau có thể gây hiểu lầm ngay cả sau khi thêm `implements`.

**Lưu ý:** Interface có thể chứa `default` method và thừa kế các phương thức từ interface cha; lớp triển khai không nhất thiết phải tự viết lại tất cả. Ngược lại, nếu interface có phương thức trừu tượng chưa được đáp ứng, lớp cụ thể không thể bỏ qua hợp đồng.

## 7. Quy tắc kiểm tra khi dùng interface trong API

Khi trình biên dịch báo không thể chuyển một kiểu cụ thể sang interface, hãy kiểm tra lần lượt:

1. Lớp có `implements InterfaceName` trực tiếp, hoặc kế thừa quan hệ ấy qua `extends`/interface cha không?
2. Bạn có đang truyền chính đối tượng của lớp chưa khai báo hợp đồng chỉ vì nó có các phương thức cùng tên không?
3. Nếu đã `implements`, chữ ký, mức truy cập, kiểu trả về, `static`/instance và ngoại lệ checked có phù hợp không? Dùng `@Override` để được kiểm tra sớm.
4. Nếu không thể sửa lớp gốc, bạn có thể khai báo adapter thực hiện interface và chuyển tiếp hành vi, hoặc dùng lambda/method reference khi interface là functional interface không?

Đừng dựa vào ép kiểu để “tạo” quan hệ. Một phép cast không bổ sung `implements` vào định nghĩa lớp; phép cast được chấp nhận về mặt cú pháp vẫn có thể gây `ClassCastException` khi đối tượng thực tế không thuộc kiểu đích.

**Ghi nhớ:** Trong Java, *có cùng bộ phương thức* là một nhận xét về hình dạng API; *là kiểu con và thực hiện hợp đồng* là quan hệ kiểu được khai báo và được trình biên dịch xác thực. Chính quan hệ ấy cho phép gán vào biến interface, truyền tham số interface và sử dụng đa hình an toàn.
