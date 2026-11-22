# Nhiều khai báo abstract tương thích và kiểu trả về chung trong Java

Một class có thể triển khai nhiều interface bằng một method khi các chữ ký tương thích và return type đáp ứng mọi hợp đồng. Tên giống nhau chưa đủ; cần xét cả tham số lẫn kiểu trả về.

## Covariant return type

~~~java
interface ObjectValue { Object value(); }
interface StringValue { String value(); }

final class TextValue implements ObjectValue, StringValue {
    @Override
    public String value() { return "Java"; }
}

public class Main {
    public static void main(String[] args) {
        TextValue value = new TextValue();
        Object a = ((ObjectValue) value).value();
        String b = ((StringValue) value).value();
        System.out.println(a);
        System.out.println(b);
        System.out.println(b.length());
    }
}
~~~

Đầu ra:

~~~text
Java
Java
4
~~~

String là subtype của Object, nên một String value() đáp ứng cả hai hợp đồng. Kiểu tham chiếu quyết định kiểu kết quả mà compiler cho phép sử dụng.

## Khi nào không tương thích?

~~~java
interface StringSource { String value(); }
interface IntegerSource { Integer value(); }
// Cố ý không hợp lệ:
// class InvalidSource implements StringSource, IntegerSource {}
~~~

String và Integer không có quan hệ subtype phù hợp để một method cùng chữ ký đáp ứng cả hai. Không thể overload bằng cách chỉ đổi return type.

Covariant return áp dụng cho kiểu tham chiếu, không cho phép thay int bằng long. Chuyển đổi primitive trong biểu thức không làm hai khai báo tương thích để override.

Trước khi gộp method, kiểm tra chữ ký, return type, type argument và ý nghĩa nghiệp vụ. Number amount() và Integer amount() có thể dùng chung Integer amount(); implementation trả Object không đáp ứng hợp đồng yêu cầu String.

## Tự kiểm tra

Number get() và Integer get() có thể dùng return type nào? String get() và Integer get() có thể overload không? int và long có covariant return không?

**Đáp án:** Integer; không; không.

Tham khảo: [JLS §8.4.5 — Method Result](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.5).
