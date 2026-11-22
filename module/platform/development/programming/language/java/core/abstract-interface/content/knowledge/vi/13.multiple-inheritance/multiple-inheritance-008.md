# Phương thức abstract của lớp cha chặn triển khai default trong Java

Một abstract method được kế thừa từ superclass vẫn là nghĩa vụ của class con. Default method cùng chữ ký ở interface không tự hoàn thiện nghĩa vụ đó; concrete subclass cần implementation hợp lệ.

~~~java
interface Greeter {
    default String greet() { return "hello from interface"; }
}
abstract class Base {
    public abstract String greet();
}
// Concrete class này không hợp lệ nếu không override:
// class Broken extends Base implements Greeter {}

final class Person extends Base implements Greeter {
    @Override
    public String greet() {
        return "hello from Person";
    }
}
public class Main {
    public static void main(String[] args) {
        Base base = new Person();
        Greeter greeter = (Greeter) base;
        System.out.println(base.greet());
        System.out.println(greeter.greet());
    }
}
~~~

Đầu ra:

~~~text
hello from Person
hello from Person
~~~

Person.greet() là implementation thực sự; nếu bỏ nó mà vẫn để Person concrete, Base.greet() còn abstract.

## Muốn dùng default thì gọi có chủ đích

~~~java
@Override
public String greet() {
    return "custom: " + Greeter.super.greet();
}
~~~

Đây là body thay thế cho method trong class, không phải khai báo bổ sung. Class vẫn cung cấp implementation của mình; Greeter.super.greet() chỉ tái sử dụng default trong ngữ cảnh direct superinterface hợp lệ.

## So sánh với superclass concrete

Nếu superclass có public String greet() với body phù hợp, class con có thể kế thừa method đó; method class được ưu tiên hơn default. Khác biệt là concrete method đã cung cấp body, còn abstract method giữ nghĩa vụ cho subclass.

Abstract class cũng có thể cố ý tái khai báo default thành abstract:

~~~java
abstract class StrictGreeter implements Greeter {
    @Override
    public abstract String greet();
}
~~~

Concrete subclass của StrictGreeter phải cài đặt greet(). Đây là lựa chọn thiết kế để buộc nhánh class cung cấp hành vi riêng.

Tham khảo: [JLS §8.4.8.4](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.4).

## Tự kiểm tra

Superclass có public abstract String status(); interface có default status(). Concrete subclass có thể bỏ qua không? Nếu superclass có method concrete tương thích thì sao? Có thể gọi default từ override không?

**Đáp án:** không; method concrete của superclass được ưu tiên; có, bằng qualified super call hợp lệ.
