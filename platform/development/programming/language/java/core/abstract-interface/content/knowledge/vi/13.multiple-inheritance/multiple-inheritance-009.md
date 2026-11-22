# Giải quyết xung đột bằng ghi đè và chọn lời gọi super hợp lệ

Khi cần giải quyết xung đột default, trước tiên hãy khai báo một override phù hợp. Sau đó chọn một body mới, gọi một default cụ thể hoặc kết hợp nhiều default nếu hợp đồng yêu cầu.

## Hai cú pháp khác nhau

- super.method() gọi method tương ứng từ superclass.
- InterfaceName.super.method() gọi default từ direct superinterface thích hợp trong ngữ cảnh instance hợp lệ.

~~~java
interface Root {
    default String id() { return "root"; }
}
interface Specific extends Root {
    @Override
    default String id() { return "specific"; }
}
final class Item implements Root, Specific {
    @Override
    public String id() {
        return Specific.super.id();
    }
}
public class Main {
    public static void main(String[] args) {
        System.out.println(new Item().id());
    }
}
~~~

Đầu ra:

~~~text
specific
~~~

Specific là direct superinterface và cung cấp default cụ thể hơn. Không thể dùng Root.super.id() để bỏ qua Specific; qualified-super call chịu quy tắc về superinterface trực tiếp và specificity.

| Biểu thức | Ý nghĩa |
| --- | --- |
| super.label() | Method từ superclass |
| Left.super.label() | Default từ direct superinterface Left, nếu hợp lệ |
| Left.label() | Gọi static method nếu Left khai báo static; không gọi default |
| ((Left) this).label() | Lời gọi instance đa hình, không ép chạy default của Left |

Không dùng InterfaceName.super cho method abstract, static hoặc private không truy cập được. Đây không phải cơ chế phản chiếu để gọi tùy ý tổ tiên.

## Chọn hành vi theo hợp đồng

1. Chọn một default nếu nó đáp ứng đúng hợp đồng.
2. Kết hợp hai default chỉ khi chúng bổ trợ nhau và side effect không bị lặp.
3. Viết body mới nếu cần chính sách riêng.
4. Tái khai báo abstract ở interface con nếu muốn từng class tự quyết định.

Khi điều tra, kiểm tra chữ ký, return type, visibility, checked exceptions, superclass và quan hệ extends. Dùng @Override, biên dịch và kiểm thử qua tham chiếu class lẫn interface.

## Tự kiểm tra

Vì sao ép kiểu ((Left) this) không giống Left.super? Khi nào nên dùng super.method()? Vì sao không nên luôn gọi cả hai default?

**Đáp án:** ép kiểu vẫn dispatch đa hình; super.method() dành cho superclass; hai default có thể có side effect hoặc ngữ nghĩa không tương thích.
