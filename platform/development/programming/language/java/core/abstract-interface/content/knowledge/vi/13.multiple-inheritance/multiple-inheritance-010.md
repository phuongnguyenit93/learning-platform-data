# Phân biệt xung đột phương thức, hằng và kiểu thành viên trong Java interface

Cùng một tên trong nhiều interface có thể thuộc các thành viên khác loại. Quy tắc giải quyết method không áp dụng nguyên xi cho static method, field hoặc member type.

| Thành viên | Đặc điểm | Cách định danh |
| --- | --- | --- |
| Abstract method | Hợp đồng chưa có body | Một implementation có thể đáp ứng nhiều hợp đồng tương thích |
| Default method | Instance method có body | Kiểm tra specificity và xung đột |
| Static method | Thuộc interface khai báo nó | JsonCodec.format() |
| Field | Ngầm định public static final | SmallLimits.LIMIT |
| Member type | Kiểu lồng ngầm định public static | LocalOptions.Policy |

## Static method

~~~java
interface JsonCodec {
    static String format() { return "JSON"; }
}
interface XmlCodec {
    static String format() { return "XML"; }
}
class Codec implements JsonCodec, XmlCodec {}

public class StaticMethodsDemo {
    public static void main(String[] args) {
        System.out.println(JsonCodec.format());
        System.out.println(XmlCodec.format());
    }
}
~~~

Kết quả:

~~~text
JSON
XML
~~~

Codec không kế thừa static method như instance method và không cần override chúng.

## Hằng trùng tên

~~~java
interface SmallLimits { int LIMIT = 10; }
interface LargeLimits { int LIMIT = 100; }
class Config implements SmallLimits, LargeLimits {
    int smallLimit() { return SmallLimits.LIMIT; }
    int largeLimit() { return LargeLimits.LIMIT; }
}
~~~

SmallLimits.LIMIT và LargeLimits.LIMIT là hai field tĩnh riêng. Field không được override theo đa hình; dùng tên đầy đủ giúp chỉ rõ nguồn giá trị.

Field của class cũng được tra cứu tĩnh theo kiểu tham chiếu:

~~~java
class Parent { String label = "parent"; }
class Child extends Parent { String label = "child"; }
public class FieldHidingDemo {
    public static void main(String[] args) {
        Parent value = new Child();
        System.out.println(value.label);
        System.out.println(((Child) value).label);
    }
}
~~~

Kết quả là parent rồi child: đây là field hiding, không phải method overriding.

## Member type cùng tên

~~~java
interface LocalOptions { class Policy {} }
interface RemoteOptions { class Policy {} }
class OptionReader implements LocalOptions, RemoteOptions {
    LocalOptions.Policy local = new LocalOptions.Policy();
    RemoteOptions.Policy remote = new RemoteOptions.Policy();
}
~~~

LocalOptions.Policy và RemoteOptions.Policy là hai kiểu khác nhau. Kiểu lồng không thể override hoặc hợp nhất hai kiểu đó; dùng tên được qualify rõ ràng.

## Cách phân tích

1. Xác định thành viên là method, static method, field hay type.
2. Với method, xét chữ ký, body, override và specificity.
3. Với static method, gọi qua interface sở hữu method.
4. Với field/type trùng tên, dùng tên qualify.
5. Không suy ra ưu tiên từ thứ tự khai báo interface.

## Tự kiểm tra

Hai abstract String id() tương thích cần mấy implementation? Hai default String send() độc lập cần làm gì? Hai field LIMIT trùng tên nên được gọi thế nào? LocalOptions.Policy và RemoteOptions.Policy có phải cùng kiểu không?

**Đáp án:** một; override để giải quyết; qualify bằng tên interface; không.
