# Quy tắc không kế thừa và không ghi đè của private method trong interface

Trong Java, **private method của interface là phương thức nội bộ thuộc chính interface khai báo nó**. Từ Java 9, interface có thể khai báo private instance method và private static method có thân hàm. Những phương thức này giúp gom phần xử lý dùng chung bên trong các default method hoặc static method mà không mở rộng API công khai.

Quy tắc cốt lõi là: **private method không được kế thừa và không thể bị override**. Lớp triển khai hoặc interface con không nhận được phương thức private đó như một thành viên có thể gọi; nếu chúng khai báo một phương thức cùng tên và chữ ký, đó là một khai báo độc lập.

## 1. Phạm vi truy cập của private method

Một private method chỉ có thể được gọi từ mã thuộc interface đang khai báo nó. Mã bên ngoài interface không thể gọi helper này qua biến tham chiếu kiểu interface, kể cả khi đối tượng thực tế là một lớp triển khai.

Ví dụ, nếu interface khai báo private method tên là `normalizeInternal`, các default method và private method khác trong chính interface có thể dùng nó. Lớp triển khai không thể gọi `normalizeInternal` như một phương thức được kế thừa, và interface con cũng không thể gọi nó như thành viên của interface cha.

Private method không phải một phần của hợp đồng mà lớp triển khai phải cung cấp. Nó cũng không phải API công khai để code bên ngoài phụ thuộc vào.

## 2. Vì sao private method không được kế thừa?

Trong Java, thành viên private chỉ thuộc phạm vi khai báo của kiểu chứa nó. Cơ chế kế thừa không truyền private method của interface cha xuống interface con hoặc lớp triển khai.

Điều này có ba hệ quả:

- Lớp triển khai không nhận private method như một phương thức được kế thừa.
- Interface con không nhận private method của interface cha và không thể gọi helper đó trực tiếp.
- Private method không tham gia tập phương thức mà Java dùng để xác định việc override hoặc giải quyết xung đột giữa các default method.

Một lớp vẫn có thể tự khai báo phương thức public hoặc package-private cùng tên và cùng tham số với helper private của interface. Phương thức của lớp là thành viên riêng của lớp; nó không override helper private. Tương tự, interface con có thể khai báo phương thức riêng cùng chữ ký với helper private của interface cha. Hai khai báo không có quan hệ override với nhau.

Lời gọi helper bên trong default method của interface cha vẫn gắn với private method được khai báo trong interface cha. Một phương thức trùng tên trong lớp triển khai không thay thế lời gọi đó.

## 3. Hai dạng private method

| Dạng | Nơi có thể gọi | Cách dùng |
|---|---|---|
| Private instance method | Từ default method hoặc private instance method trong cùng interface | Tách phần xử lý cần ngữ cảnh instance |
| Private static method | Từ static method, default method hoặc private method khác trong cùng interface | Tách phần xử lý không cần instance |

Cả hai dạng đều có thân hàm, chỉ dùng nội bộ trong interface khai báo chúng, không được kế thừa và không bị override.

Private instance method không thể được gọi trực tiếp từ static method vì static context không có instance của interface. Private static method không phụ thuộc vào instance nên có thể được gọi từ cả static method lẫn instance method trong cùng interface.

## 4. Ví dụ chạy được: phương thức cùng chữ ký không override helper private

Tạo file **InterfacePrivateMethodsDemo.java**:

~~~java
import java.util.Locale;

interface TextRules {
    default String displayName(String raw) {
        String value = trimToNull(raw);
        return value == null ? "(unknown)" : collapseWhitespace(value);
    }

    static String normalizeKey(String raw) {
        return requireNonBlank(raw).toUpperCase(Locale.ROOT);
    }

    private String trimToNull(String value) {
        if (value == null) {
            return null;
        }

        String trimmed = value.strip();
        return trimmed.isEmpty() ? null : trimmed;
    }

    private String collapseWhitespace(String value) {
        return value.replaceAll("\\s+", " ");
    }

    private static String requireNonBlank(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value must not be blank");
        }

        return value.strip();
    }
}

final class CustomTextRules implements TextRules {
    // Phương thức này độc lập, không override helper private của TextRules.
    public String trimToNull(String value) {
        return "class:" + value;
    }
}

public class InterfacePrivateMethodsDemo {
    public static void main(String[] args) {
        TextRules contract = new CustomTextRules();

        System.out.println(contract.displayName("  Java   9  "));
        System.out.println(TextRules.normalizeKey(" java-9 "));

        CustomTextRules implementation = (CustomTextRules) contract;
        System.out.println(implementation.trimToNull("Java"));
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac InterfacePrivateMethodsDemo.java
java InterfacePrivateMethodsDemo
~~~

Kết quả stdout:

~~~text
Java 9
JAVA-9
class:Java
~~~

Giải thích:

1. `displayName` là default method của `TextRules`. Lời gọi `trimToNull` và `collapseWhitespace` bên trong nó sử dụng hai private instance method do chính `TextRules` khai báo.
2. `normalizeKey` là static method. Nó dùng private static helper `requireNonBlank` để kiểm tra và chuẩn hóa đầu vào.
3. `CustomTextRules` tự khai báo một phương thức public tên `trimToNull`. Phương thức này không override helper private của interface. Vì vậy, lời gọi từ `displayName` vẫn dùng logic trong `TextRules`, còn lời gọi qua biến kiểu `CustomTextRules` dùng phương thức public của lớp.

Nếu đổi kiểu tham chiếu thành `TextRules`, code bên ngoài vẫn không thể gọi helper private. Việc lớp có một phương thức public trùng tên không làm helper private trở thành thành viên của kiểu interface.

## 5. Những giới hạn khi khai báo

Private method trong interface phải có phần thân. Các quy tắc cần nhớ:

- Có thể khai báo private instance method hoặc private static method.
- Không thể kết hợp `private` với `abstract`, vì abstract method không có thân hàm.
- Không thể kết hợp `private` với `default`; default method là phương thức được cung cấp cho kiểu triển khai, còn private method chỉ là helper nội bộ.
- Không khai báo đồng thời các mức truy cập mâu thuẫn như `public private` hoặc `protected private`.
- Lớp triển khai không có nghĩa vụ cài đặt private method và không thể gọi helper đó qua interface.

Một phương thức cùng chữ ký trong lớp chỉ có thể override một phương thức có thể được kế thừa và có thể được override. Private helper của interface không đáp ứng điều kiện này. Vì thế, thêm `@Override` lên phương thức chỉ trùng chữ ký với helper private sẽ không hợp lệ, trừ khi phương thức đó đồng thời override một thành viên khác có thể truy cập và kế thừa.

## 6. Khi nào nên dùng?

Dùng private instance method khi nhiều default method trong cùng interface cần chia sẻ một đoạn xử lý có ngữ cảnh instance. Dùng private static method khi nhiều static hoặc instance method cần chung một hàm tiện ích không phụ thuộc trạng thái instance.

Ví dụ về phần xử lý phù hợp để tách thành helper:

- Kiểm tra đầu vào và chuẩn hóa chuỗi.
- Ghép hoặc định dạng một phần dữ liệu dùng chung trong nhiều default method.
- Chia nhỏ một thuật toán nội bộ để các default method dễ đọc hơn.
- Dùng chung quy tắc kiểm tra trong static method của interface.

Không dùng private method nếu lớp triển khai cần gọi hoặc thay thế hành vi đó. Khi nhiều kiểu bên ngoài cần dùng chung một chức năng, hãy thiết kế nó thành API có phạm vi truy cập phù hợp hoặc chuyển logic sang một thành phần tiện ích riêng.

## 7. Lỗi hiểu thường gặp

**Nhầm rằng lớp triển khai có thể gọi helper private của interface**

Không thể gọi helper đó qua biến kiểu interface. Private method không được kế thừa, nên nó không xuất hiện trong hợp đồng công khai của interface.

**Nhầm rằng phương thức cùng tên trong lớp sẽ override helper private**

Không có quan hệ override. Default method của interface vẫn gọi helper private thuộc interface đó. Phương thức cùng tên trong lớp chỉ được gọi khi code truy cập trực tiếp phương thức của lớp.

**Dùng private method như một điểm mở rộng cho interface con**

Interface con không kế thừa helper private và không thể ghi đè nó để thay đổi cách default method của interface cha hoạt động. Nếu cần hành vi có thể tùy biến, hãy dùng một phương thức public/default phù hợp với hợp đồng.

**Khai báo private method không có thân hàm**

Private method không thể là abstract. Hãy cung cấp phần thân cho phương thức.

**Gọi private instance method từ static method**

Static method không có instance để gọi private instance helper. Nếu logic không cần instance, chuyển helper thành private static method.

## 8. Khả năng tương thích và checklist

Private method trong interface được hỗ trợ từ Java 9 và tiếp tục là một phần hợp lệ của Java hiện đại. Ví dụ trên dùng các API chuỗi có trong Java 11 trở lên và có thể chạy bằng Java 17+.

Trước khi dùng, kiểm tra:

- Interface cần chia sẻ logic giữa các method nội bộ.
- Helper không cần được lớp triển khai hoặc interface con gọi.
- Helper có thân hàm và chọn đúng dạng instance hoặc static.
- Không kỳ vọng lớp triển khai override helper để thay đổi hành vi của default method.
- Mức Java source/release của dự án hỗ trợ private method trong interface.

Hãy nhớ: **private method thuộc riêng interface khai báo nó; nó không được kế thừa, không bị override và chỉ giúp tổ chức phần cài đặt bên trong interface.**
