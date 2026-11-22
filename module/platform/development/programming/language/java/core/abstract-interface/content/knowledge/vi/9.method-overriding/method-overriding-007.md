# Phương thức final, private và static trong quan hệ kế thừa Java

Ba modifier này tạo ra ba quan hệ khác nhau với lớp con. **Final** ngăn override, **private** không được kế thừa để override, còn **static** dùng method hiding thay vì dispatch đa hình theo đối tượng.

## 1. So sánh nhanh

| Loại phương thức cha | Lớp con kế thừa? | Khai báo cùng chữ ký ở lớp con |
| --- | --- | --- |
| Instance method thường | Có, nếu được truy cập | Override nếu thỏa các quy tắc |
| final instance method | Có | Lỗi nếu cố override |
| private instance method | Không | Phương thức độc lập, không override |
| Static method có thể kế thừa | Có | Static method tương ứng sẽ hide |
| Static final method | Có thể gọi theo quyền truy cập | Không thể hide bằng khai báo tương ứng |

## 2. Ví dụ: final, private, static và override

~~~java
public class MethodKindsDemo {
    static class Base {
        public final String category() { return "base"; }
        private String secret() { return "base-secret"; }
        public String reveal() { return secret(); }
        public static String kind() { return "Base"; }
        public String describe() { return "Base.describe"; }
    }

    static class Child extends Base {
        public String category(int level) { return "level-" + level; }
        public String secret() { return "child-secret"; }
        public static String kind() { return "Child"; }

        @Override
        public String describe() { return "Child.describe"; }
    }

    public static void main(String[] args) {
        Child child = new Child();
        Base ref = child;
        System.out.println(ref.category());
        System.out.println(child.category(2));
        System.out.println(ref.reveal());
        System.out.println(child.secret());
        System.out.println(ref.kind());
        System.out.println(ref.describe());
    }
}
~~~

~~~text
base
level-2
base-secret
child-secret
Base
Child.describe
~~~

category() là final và được kế thừa; category(int) là overload hợp lệ. Base.secret() là private, nên Child.secret() là method riêng và không thay đổi lời gọi bên trong Base.reveal(). kind() là static, nên lời gọi qua biến ref được phân giải theo kiểu Base. Chỉ describe() là instance override và dispatch tới Child.

## 3. Các quy tắc dễ quên

- final trên method không cấm gọi hay kế thừa method đó; nó cấm override. final trên class thì cấm subclass.
- Không thể khai báo một method vừa abstract vừa final: một bên yêu cầu override để cung cấp thân, bên kia cấm override.
- private helper của superclass vẫn có thể được gọi từ method khác được định nghĩa trong superclass khi object thực là subclass. Điều không xảy ra là dispatch sang method cùng tên do subclass tự khai báo.
- Static method của interface không được class triển khai kế thừa. Gọi nó bằng tên interface, ví dụ Tools.version(). Private interface methods là helper nội bộ cho các method có thân trong interface.
- Nếu superclass và subclass khai báo static/instance cùng chữ ký tương ứng, compiler báo lỗi; đổi modifier không biến static thành override.

## 4. Dùng final để kiểm soát thuật toán chung

Một mẫu thiết kế phổ biến là *Template Method*: superclass giữ trình tự bằng method final và giao một bước cụ thể cho subclass.

~~~java
abstract class Job {
    public final void run() {
        prepare();
        execute();
        finish();
    }

    private void prepare() { System.out.println("prepare"); }
    protected abstract void execute();
    private void finish() { System.out.println("finish"); }
}

final class ImportJob extends Job {
    @Override
    protected void execute() {
        System.out.println("import");
    }
}
~~~

run() cố định thứ tự; execute() là điểm mở rộng; các helper private không phải API dành cho subclass. Cách này hữu ích khi bắt buộc quy trình chung phải chạy đầy đủ mà không phụ thuộc vào việc subclass có nhớ gọi super hay không.

**Ghi nhớ:** cùng tên không đồng nghĩa override. Hãy xác định modifier, khả năng kế thừa và cơ chế dispatch trước khi kết luận quan hệ giữa hai khai báo.