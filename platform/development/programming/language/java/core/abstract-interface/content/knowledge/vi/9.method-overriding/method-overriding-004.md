# Kiểu trả về đồng biến và giới hạn với kiểu nguyên thủy khi ghi đè trong Java

**Covariant return** cho phép override trả về một kiểu tham chiếu cụ thể hơn kiểu được công bố ở cha. Ví dụ, nếu cha trả về Number, con có thể trả về Integer. Điều này không cho phép đổi một primitive sang primitive khác hoặc sang wrapper.

## 1. Quy tắc chính

| Return type ở cha | Return type ở con | Kết quả |
| --- | --- | --- |
| Object | String | Hợp lệ: String là kiểu con của Object |
| Number | Integer | Hợp lệ |
| CharSequence | String | Hợp lệ |
| Object | int[] | Hợp lệ: mảng là kiểu tham chiếu |
| String | Object | Không hợp lệ: kiểu con trả về rộng hơn |
| int | int | Hợp lệ |
| int | long hoặc Integer | Không hợp lệ |
| void | void | Hợp lệ |
| void | String | Không hợp lệ |

Kiểu primitive phải giữ nguyên chính xác. Boxing, unboxing hoặc primitive widening trong biểu thức không biến hai kiểu trả về thành kiểu đồng biến.

## 2. Ví dụ chạy được

~~~java
public class CovariantDemo {
    public static void main(String[] args) {
        Item general = new Note("Java");
        Note specific = new Note("Java");

        Number size = general.size();
        Integer exactSize = specific.size();

        System.out.println(general.label() + ":" + size);
        System.out.println(specific.label() + ":" + exactSize);
        System.out.println(general.copy().getClass().getSimpleName());
    }
}

abstract class Item {
    public abstract CharSequence label();
    public abstract Number size();
    public abstract Item copy();
}

final class Note extends Item {
    private final String text;

    Note(String text) { this.text = text; }

    @Override public String label() { return text; }
    @Override public Integer size() { return text.length(); }
    @Override public Note copy() { return new Note(text); }
}
~~~

~~~bash
javac CovariantDemo.java
java CovariantDemo
~~~

~~~text
Java:4
Java:4
Note
~~~

Integer size() hợp lệ vì Integer là subtype của Number; text.length() được boxing thành Integer trong biểu thức return. Điều này khác với việc đổi chữ ký cha từ int sang Integer. Qua biến Item, compiler vẫn xem kết quả của size() là Number, dù runtime đang chạy Note.size().

## 3. Generic và mảng cần xét kiểu đầy đủ

Generic thường bất biến: List&lt;Integer&gt; không phải subtype của List&lt;Number&gt;. Vì vậy, nếu cha trả về List&lt;Number&gt;, con không thể override bằng List&lt;Integer&gt;. Hợp đồng List<? extends Number> linh hoạt hơn và có thể được triển khai bằng List&lt;Integer&gt;.

Mảng là kiểu tham chiếu: Object data() có thể được override bằng int[] data(), vì int[] là subtype của Object. Nhưng int data() không thể đổi thành long data().

~~~java
import java.util.List;

abstract class NumberReader {
    abstract List<? extends Number> read();
}

final class IntegerReader extends NumberReader {
    @Override
    List<Integer> read() {
        return List.of(2, 5, 7);
    }
}
~~~

Đây là ví dụ về quan hệ kiểu trả về; nó không phải chương trình độc lập có main.

## 4. Bridge method là chi tiết biên dịch

Java dùng type erasure cho generic. Compiler có thể sinh *bridge method* để lời gọi qua kiểu cha vẫn dispatch tới triển khai cụ thể sau erasure hoặc khi return type covariant. Ví dụ Box&lt;T&gt;.get() có thể được hiện thực bởi TextBox extends Box&lt;String&gt; với String get(). Không cần tự khai báo bridge method; hãy viết override hợp lệ và dùng @Override.

## 5. Phân biệt return type với tham số

Covariant return chỉ nói về **kiểu trả về**. Nếu cha có Number convert(Number value), con khai báo Integer convert(Integer value) thì tham số đã đổi; đó là overload, không phải override của convert(Number). Muốn override, giữ tham số tương ứng và có thể thu hẹp kiểu trả về.

**Ghi nhớ:** kiểm tra quan hệ subtype của toàn bộ kiểu tham chiếu trả về; với primitive và void, giữ nguyên kiểu. Return type không được dùng để tạo overload và không quyết định overload nào được chọn.