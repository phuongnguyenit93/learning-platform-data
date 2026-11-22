# Phương thức private trong interface từ Java 9

Từ **Java 9**, interface có thể khai báo phương thức `private` có thân hàm. Đây là helper nội bộ để các method khác trong cùng interface chia sẻ logic mà không đưa helper đó thành một phần API công khai.

Java 8 đã bổ sung `default` instance method và `public static` method, nhưng chưa cho phép private method trong interface. Vì vậy, đoạn code dùng private interface method không biên dịch khi target là `--release 8`.

## 1. Private instance và private static

- **Private instance method** có ngữ cảnh đối tượng; thường được gọi từ default method hoặc private instance method khác trong cùng interface.
- **Private static method** không cần instance; có thể được gọi từ static method, default method và các helper phù hợp trong cùng interface.

Cả hai dạng đều phải có thân hàm. Chúng không phải hợp đồng mà class triển khai cần implement, không được kế thừa để override, và không thể được gọi trực tiếp từ code bên ngoài interface khai báo chúng.

## 2. Ví dụ: helper dùng chung nhưng không lộ ra API

Lưu toàn bộ chương trình thành `Main.java`. Ví dụ yêu cầu Java 9 trở lên.

~~~java
interface TextView {
    default String title(String value) {
        return format("TITLE", value);
    }

    default String summary(String value) {
        return format("SUMMARY", value);
    }

    private String format(String label, String value) {
        return label + ": " + normalize(value);
    }

    static String versionLabel() {
        return "[" + normalize(" Java 9+ ") + "]";
    }

    private static String normalize(String value) {
        if (value == null) {
            return "(empty)";
        }
        return value.trim().toUpperCase(java.util.Locale.ROOT);
    }
}

final class ConsoleTextView implements TextView {
}

public class Main {
    public static void main(String[] args) {
        TextView view = new ConsoleTextView();
        System.out.println(view.title(" private helper "));
        System.out.println(view.summary(" shared code "));
        System.out.println(TextView.versionLabel());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 --release 9 Main.java
java Main
~~~

Stdout:

~~~text
TITLE: PRIVATE HELPER
SUMMARY: SHARED CODE
[JAVA 9+]
~~~

`title` và `summary` là default instance method công khai; cả hai gọi `format` để tái sử dụng bước ghép nhãn. `format` có thể hoạt động trong ngữ cảnh instance và gọi `normalize`. Phương thức static công khai `versionLabel` cũng gọi được `normalize` vì helper này là private static, không cần `this`.

`ConsoleTextView` không cần khai báo hoặc override các helper. Nếu lớp này tự khai báo một method trùng tên với `format`, đó không phải override của helper private; lời gọi trong interface vẫn dùng phần cài đặt riêng tư đã khai báo ở `TextView`.

## 3. Quy tắc truy cập cần nhớ

| Khai báo | Bên ngoài interface gọi trực tiếp được? | Class triển khai override được? |
|---|---|---|
| `default String title(...) { ... }` | Có, qua object | Có |
| `static String versionLabel() { ... }` | Có, qua `TextView.versionLabel()` | Không |
| `private String format(...) { ... }` | Không | Không |
| `private static String normalize(...) { ... }` | Không | Không |

**Nếu bỏ comment ở một trong các dòng dưới đây, khai báo đó sẽ không hợp lệ.** Mỗi dòng là một ví dụ riêng; không thể ghép tất cả lỗi vào cùng một chương trình chạy được.

~~~java
interface InvalidHelpers {
    // private abstract String helper();
    // private default String other() { return "x"; }
    // private void missingBody();
}
~~~

`private abstract` và `private default` không hợp lệ. Private method không thể chỉ có dấu chấm phẩy; nó cần body vì không được lớp con kế thừa để cung cấp implementation. Interface cũng không dùng `protected` hoặc package-private method để tạo một phạm vi trung gian như class.

Private helper vẫn có thể khai báo `throws` cho checked exception. Nếu một default/static method gọi helper đó, phương thức gọi phải bắt hoặc khai báo checked exception phù hợp; modifier `private` không làm ngoại lệ biến mất.

## 4. Chọn loại helper theo nhu cầu

Dùng private instance method khi logic cần ngữ cảnh của đối tượng hiện tại, chẳng hạn khi gọi một instance method khác của interface. Dùng private static method khi logic chỉ cần tham số hoặc các thành viên static và cần được dùng từ cả static method.

Nếu mọi class triển khai phải cung cấp một hành vi, hãy công bố một abstract instance method. Nếu cần hành vi mặc định có thể được class thay đổi, dùng default method. Private helper chỉ nên chứa chi tiết cài đặt nội bộ.

**Kiểm tra phiên bản:** nếu build dùng Java 8, hãy chuyển helper sang utility class phù hợp hoặc điều chỉnh target; không thể giữ private method trong interface rồi kỳ vọng `--release 8` chấp nhận nó.