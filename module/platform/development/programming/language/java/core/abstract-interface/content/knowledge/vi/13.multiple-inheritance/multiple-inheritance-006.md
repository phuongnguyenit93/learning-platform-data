# Xung đột default method từ hai interface không liên quan trong Java

Khi hai interface không có quan hệ kế thừa ưu tiên cùng cung cấp default method có cùng chữ ký, Java không tự chọn một body. Class hoặc interface con kết hợp phải xác định hành vi.

~~~java
interface AuditLog {
    default String format(String event) {
        return "AUDIT:" + event;
    }
}
interface ConsoleLog {
    default String format(String event) {
        return "CONSOLE:" + event;
    }
}
final class UnifiedLog implements AuditLog, ConsoleLog {
    @Override
    public String format(String event) {
        return AuditLog.super.format(event)
                + " | " + ConsoleLog.super.format(event);
    }
}
public class Main {
    public static void main(String[] args) {
        System.out.println(new UnifiedLog().format("LOGIN"));
    }
}
~~~

Đầu ra:

~~~text
AUDIT:LOGIN | CONSOLE:LOGIN
~~~

UnifiedLog.format() là override public duy nhất. Các lời gọi AuditLog.super.format() và ConsoleLog.super.format() chọn rõ default từ direct superinterface phù hợp.

## Ba chiến lược

- **Chọn một default** nếu một nguồn đáp ứng đúng hợp đồng.
- **Kết hợp hai default** nếu chúng bổ trợ nhau và side effect không bị lặp.
- **Viết body mới** nếu cả hai default đều không phù hợp.

Không gọi cả hai chỉ để hết lỗi biên dịch; chúng có thể ghi log, phát sự kiện hoặc cập nhật trạng thái hai lần.

## Xung đột tại interface con

~~~java
interface Left {
    default String name() { return "left"; }
}
interface Right {
    default String name() { return "right"; }
}
interface Combined extends Left, Right {
    @Override
    default String name() {
        return Left.super.name() + "/" + Right.super.name();
    }
}
~~~

Combined cung cấp default mới, nên class implement Combined có thể kế thừa body này. Một lựa chọn khác là khai báo name() abstract để đẩy trách nhiệm xuống class concrete.

Đừng nhầm với hai nhánh cùng kế thừa một default duy nhất từ tổ tiên, hoặc hai abstract method tương thích. Hai method cùng tên nhưng khác tham số là overload. Nếu return type không tương thích, override không sửa được hợp đồng kiểu.

Tham khảo: [JLS §9.4.1.3 — Inheriting Methods with Override-Equivalent Signatures](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4.1.3).

## Tự kiểm tra

Hai interface độc lập có default name(); class không override thì sao? Vì sao Java không so sánh body để chọn một? Khi nào InterfaceName.super.method() hữu ích?

**Đáp án:** lỗi biên dịch; quy tắc dựa vào kiểu và kế thừa; khi override cần gọi default phù hợp.
