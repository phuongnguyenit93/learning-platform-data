# Ưu tiên phương thức có thân kế thừa từ lớp cha trong Java

Nếu superclass cung cấp một instance method concrete phù hợp với default method của interface, method từ class được ưu tiên. Quy tắc này thường được gọi là **class wins**.

~~~java
class Speaker {
    public String describe() { return "class"; }
}
interface Audible {
    default String describe() { return "interface"; }
    default String channel() { return "default channel"; }
}
final class SmartSpeaker extends Speaker implements Audible {}

public class Main {
    public static void main(String[] args) {
        SmartSpeaker speaker = new SmartSpeaker();
        Audible view = speaker;
        System.out.println(speaker.describe());
        System.out.println(view.describe());
        System.out.println(speaker.channel());
    }
}
~~~

Đầu ra:

~~~text
class
class
default channel
~~~

Speaker.describe() thắng Audible.describe(). Vì superclass không có channel(), class nhận default của interface. Kiểu tham chiếu Audible không ép lời gọi instance dùng default khi class đã có method phù hợp.

Không phải method bất kỳ cùng tên đều đủ. Kiểm tra chữ ký, return type, visibility và checked exceptions. Method protected không tự đáp ứng hợp đồng interface yêu cầu public; method static hoặc private cũng không phải instance implementation tương ứng.

Một superclass có method abstract tạo tình huống khác: concrete subclass vẫn phải hoàn thiện nghĩa vụ abstract. Nếu cần dùng default, nó có thể override tường minh rồi gọi Status.super.status() khi Status là direct superinterface phù hợp.

## Tự kiểm tra

Superclass có public String name() và interface có default String name(): body nào chạy? Superclass không có method tương ứng nhưng interface có default thì sao? Method protected có đáp ứng public không?

**Đáp án:** superclass; có thể dùng default; không.
