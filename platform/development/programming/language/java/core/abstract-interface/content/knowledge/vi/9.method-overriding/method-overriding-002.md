# Phân biệt override, overload và static method hiding trong Java

Ba cơ chế có thể xuất hiện cùng lúc trong một hệ phân cấp lớp, nhưng khác nhau ở **cách chọn phương thức**:

- **Override:** lớp con cung cấp triển khai cho một instance method có thể ghi đè. Sau khi chữ ký được chọn lúc biên dịch, runtime dispatch chọn thân phương thức theo đối tượng thực tế.
- **Overload:** cùng tên nhưng danh sách kiểu tham số khác nhau. Compiler chọn chữ ký phù hợp từ kiểu tĩnh của đối số và các phương thức khả dụng.
- **Static method hiding:** lớp con khai báo static method tương ứng với static method được kế thừa. Phương thức được phân giải theo kiểu tại compile time, không theo đối tượng runtime.

## 1. Bảng phân biệt

| Tiêu chí | Override | Overload | Static hiding |
| --- | --- | --- | --- |
| Danh sách tham số | Chữ ký tương ứng | Khác kiểu/số lượng/thứ tự tham số | Chữ ký static tương ứng |
| Cần kế thừa | Có, hoặc thực hiện interface | Không bắt buộc | Có quan hệ class kế thừa phù hợp |
| Cách chọn | Thân instance theo đối tượng runtime | Chữ ký theo kiểu tĩnh lúc biên dịch | Static method theo kiểu lúc biên dịch |
| Đa hình runtime | Có | Bản thân overload không; chữ ký đã chọn vẫn có thể bị override | Không |
| @Override | Nên dùng | Không cho overload đơn thuần | Không áp dụng |

Return type, modifier và throws không tạo ra overload mới nếu danh sách tham số không đổi. Static/instance cùng chữ ký trong quan hệ kế thừa gây lỗi thay vì tạo cơ chế dispatch đặc biệt.

## 2. Ví dụ tổng hợp

~~~java
public class DispatchDemo {
    static class Base {
        String pick(Object value) { return "Base(Object)"; }
        String pick(String value) { return "Base(String)"; }
        static String kind() { return "Base"; }
    }

    static class Child extends Base {
        @Override
        String pick(Object value) { return "Child(Object)"; }

        String pick(Integer value) { return "Child(Integer)"; }
        static String kind() { return "Child"; }
    }

    public static void main(String[] args) {
        Base base = new Child();
        Child child = new Child();

        System.out.println(base.pick("hi"));
        System.out.println(base.pick(Integer.valueOf(3)));
        System.out.println(child.pick(Integer.valueOf(3)));
        System.out.println(base.kind());
        System.out.println(child.kind());
    }
}
~~~

~~~bash
javac DispatchDemo.java
java DispatchDemo
~~~

~~~text
Base(String)
Child(Object)
Child(Integer)
Base
Child
~~~

- base.pick("hi"): compiler chọn overload pick(String) nhìn thấy ở Base. Child không override chữ ký này, nên chạy Base.pick(String).
- base.pick(Integer.valueOf(3)): kiểu Base không có overload pick(Integer), nên chọn pick(Object); runtime dispatch tới Child.pick(Object).
- child.pick(Integer.valueOf(3)): kiểu tĩnh Child có thêm overload pick(Integer), nên compiler chọn chữ ký đó.
- base.kind() và child.kind() chọn static method theo kiểu tĩnh của biểu thức. Trong mã thật, nên gọi Base.kind() và Child.kind() cho rõ ràng.

## 3. Các bẫy thường gặp

**Đổi tham số thành overload:** nếu cha có convert(Object) và con chỉ khai báo convert(String), con chưa triển khai convert(Object); một lớp con concrete có thể vẫn không biên dịch nếu phương thức cha là abstract.

**Overload với null:** nếu có call(String) và call(Integer), lời gọi call(null) mơ hồ vì không kiểu nào cụ thể hơn kiểu còn lại. Với call(Object) và call(String), call(null) chọn String.

**Static không đa hình:** gọi static qua biến đối tượng vẫn dùng kiểu compile-time của biểu thức. Static method ở interface cũng không được class triển khai kế thừa như static method của superclass; hãy gọi qua tên interface.

**Kiểm tra thực hành:** trước khi kết luận một phương thức là override, xác định kiểu tĩnh của receiver, chữ ký overload được chọn, rồi mới xét phương thức instance nào được override ở runtime. Bài về @Override trình bày cách để compiler bắt lỗi sai chữ ký sớm.