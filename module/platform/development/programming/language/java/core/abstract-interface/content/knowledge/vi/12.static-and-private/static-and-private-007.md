# Phân biệt private helper với điểm mở rộng cho lớp triển khai

Một API tốt tách rõ **hành vi mà implementation được phép quyết định** khỏi **chi tiết triển khai dùng chung**. Trong interface, abstract/default instance method có thể là một phần API và tham gia cơ chế override; private helper giữ logic nội bộ. Static method thuộc về kiểu khai báo, nên cũng không phải hook đa hình của instance.

## 1. So sánh vai trò

| Dạng method | Vai trò | Lớp triển khai có override được không? |
|---|---|---|
| `public abstract` instance method | Hợp đồng bắt buộc cho implementation cụ thể | Có; class concrete phải cung cấp implementation phù hợp |
| `public default` instance method | Hành vi mặc định mà implementation có thể thay đổi | Có |
| `public static` method trong interface | Tiện ích thuộc về interface, gọi qua tên interface | Không |
| `private` instance helper | Chi tiết nội bộ có ngữ cảnh instance | Không |
| `private static` helper | Chi tiết nội bộ không cần instance hiện tại | Không |
| `protected abstract` method trong abstract class | Điểm mở rộng dành cho class con | Có |

Private method trong interface được hỗ trợ từ Java 9. Các helper phải có thân hàm; chúng không phải hợp đồng cho class triển khai. Còn một method abstract/default công khai được thiết kế như extension point khi API thật sự muốn cho implementation cung cấp hoặc thay đổi hành vi.

Hai interface không liên quan có thể khai báo private helper trùng tên và chữ ký mà không xung đột, vì helper private không được kế thừa. Ngược lại, nếu cả hai cùng công bố default method cùng chữ ký, class triển khai có thể phải override để giải quyết xung đột.

## 2. Ví dụ hoàn chỉnh: hook và helper cùng tồn tại

Lưu mã sau thành `InterfaceHelperDemo.java` và chạy bằng Java 17 trở lên:

~~~java
import java.util.Locale;

interface MessageView {
    String transform(String raw);

    default String render(String raw) {
        String checked = requireText(raw);
        return "Result: " + trimResult(transform(checked));
    }

    private String trimResult(String text) {
        return text.trim();
    }

    private static String requireText(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("text must not be null");
        }
        return raw;
    }

    static String kind() {
        return "MessageView";
    }
}

final class UpperMessageView implements MessageView {
    @Override
    public String transform(String raw) {
        return raw.toUpperCase(Locale.ROOT);
    }

    public String trimResult(String text) {
        return "Class method: " + text;
    }
}

public class InterfaceHelperDemo {
    public static void main(String[] args) {
        MessageView view = new UpperMessageView();

        System.out.println(view.render("  java  "));
        System.out.println(new UpperMessageView().trimResult("test"));
        System.out.println(MessageView.kind());

        try {
            view.render(null);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 17 InterfaceHelperDemo.java
java InterfaceHelperDemo
~~~

Stdout:

~~~text
Result: JAVA
Class method: test
MessageView
Rejected: text must not be null
~~~

### Đọc ví dụ theo từng vai trò

- `transform` là extension point: `UpperMessageView` phải cung cấp implementation công khai. Khi `render` gọi `transform(checked)`, Java dispatch đến implementation của đối tượng thực tế.
- `render` là default method chứa quy trình dùng chung. Một class triển khai có thể override nó nếu API cho phép thay đổi toàn bộ quy trình.
- `trimResult` của interface là private helper. `render` gọi helper này trong interface, nên kết quả là `Result: JAVA`. Method công khai `trimResult` trong class là một method độc lập; nó không override private helper của interface.
- `requireText` là private static helper để kiểm tra đầu vào. Caller bên ngoài không thể gọi `MessageView.requireText(...)`.
- `MessageView.kind()` là public static method của interface. Nó được gọi bằng tên interface, không qua `view`.

Nếu thêm `@Override` vào `UpperMessageView.trimResult`, compiler sẽ từ chối vì không có method tương ứng được kế thừa để override. Tên và chữ ký giống nhau chưa đủ để tạo quan hệ override; phải có một method gốc có thể được override theo quy tắc Java.

## 3. Khi cần một extension point thật sự

Nếu mọi implementation phải tự quyết định cách biến đổi dữ liệu, hãy công bố hành vi đó trong hợp đồng:

~~~java
interface Transformer {
    String transform(String input);
}

final class UpperTransformer implements Transformer {
    @Override
    public String transform(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

`transform` là method abstract công khai; implementation cụ thể có nghĩa vụ cung cấp nó. Nếu chỉ muốn tái sử dụng một bước chuẩn hóa giữa các default method, dùng private helper sẽ tránh thêm method công khai mà người dùng API có thể phụ thuộc vào.

Default method nằm giữa hai nhu cầu: nó cung cấp implementation dùng chung nhưng vẫn có thể override. Nếu muốn bảo vệ toàn bộ quy trình mặc định, hãy cân nhắc xem API có nên cho phép override default method đó hay không; private helper chỉ khóa phần helper, không tự khóa phương thức public đang gọi nó.

## 4. Khi abstract class phù hợp hơn

Abstract class cho phép thiết kế một template method cố định và một hook dành cho class con:

~~~java
abstract class BaseWorkflow {
    public final String run(String input) {
        return normalize(step(input));
    }

    private String normalize(String value) {
        return value.trim();
    }

    protected abstract String step(String input);
}

final class EchoWorkflow extends BaseWorkflow {
    @Override
    protected String step(String input) {
        return " " + input + " ";
    }
}
~~~

Đây là các khai báo lớp hợp lệ trên Java 17, chưa có `main`. `run` là `public final` nên class con không override được khung thuật toán. `step` là `protected abstract` hook mà class con phải cung cấp. `normalize` là private helper của lớp cha, được dùng sau khi hook trả về kết quả.

Dùng interface khi cần mô tả hợp đồng và có thể cung cấp default behavior. Cân nhắc abstract class khi cần trạng thái instance, constructor hoặc một template method với hook được kiểm soát rõ hơn.

## 5. Quy tắc quyết định

- **Implementation phải quyết định hành vi:** khai báo abstract instance method công khai trong interface.
- **Cần hành vi mặc định có thể thay đổi:** dùng default method.
- **Cần chia sẻ chi tiết nội bộ giữa các default method:** dùng private instance helper.
- **Cần chia sẻ logic tĩnh nội bộ:** dùng private static helper.
- **Cần tiện ích thuộc về interface:** dùng public static method và gọi bằng tên interface.
- **Cần giữ một quy trình lớp cha cố định nhưng cho phép class con thay một bước:** cân nhắc template method `final` cùng hook `protected` trong abstract class.

Không đặt helper thành public chỉ để hai method gọi chung nó. Ngược lại, đừng đặt một hành vi bắt buộc cho implementation thành private helper: class triển khai không thể dùng helper đó làm hợp đồng hoặc override nó.

**Tự kiểm tra:** Nếu class triển khai cần thay đổi kết quả của một bước, hãy xác định bước đó có thật sự là extension point không. Nếu có, công bố method phù hợp; nếu không, giữ nó sau ranh giới private để implementation không phụ thuộc vào chi tiết nội bộ.