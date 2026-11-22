# Constructor lớp cha khi khởi tạo lớp con trong Java

Khi gọi `new Child(...)`, Java tạo **một đối tượng Child duy nhất**. Đối tượng đó có cả các trường instance được khai báo ở Parent và Child; Java không tạo thêm một đối tượng Parent độc lập để nhét vào Child. Constructor của Parent chạy để thiết lập phần trạng thái do lớp cha sở hữu trước khi constructor của Child hoàn tất.

Constructor không được kế thừa hoặc override. Tuy vậy, constructor lớp cha vẫn tham gia chuỗi khởi tạo qua `super(...)`. Đây là hai ý khác nhau: **không kế thừa constructor** không có nghĩa là **bỏ qua constructor cha**.

## 1. Hình dung chuỗi constructor

~~~text
new Child(...)
   |
   v
Child constructor
   |
   +-- this(...) ? --> constructor Child khác
   |
   +-- super(...) / super() ngầm định
                    |
                    v
              Parent constructor
                    |
                    v
              ... -> Object constructor
                    |
                    v
              hoàn tất phần superclass
   |
   v
hoàn tất phần Child
   |
   v
trả về tham chiếu Child
~~~

Mỗi lớp chỉ gọi constructor của **lớp cha trực tiếp**. Nếu Parent còn extends Grandparent, constructor của Grandparent cũng nằm trong chuỗi. Java lần lượt hoàn tất phần khởi tạo của các lớp tổ tiên trước khi phần khởi tạo instance và phần thân constructor của Child hoàn tất.

## 2. Gọi constructor cha bằng super(...)

Ví dụ độc lập sau cho thấy lớp con truyền dữ liệu cho constructor cha. Lưu vào tệp **SuperConstructorDemo.java**:

~~~java
public class SuperConstructorDemo {
    static class Parent {
        private final String id;

        Parent(String id) {
            this.id = id;
            System.out.println("Parent(" + id + ")");
        }

        String id() {
            return id;
        }
    }

    static class Child extends Parent {
        private final int level;

        Child(String id, int level) {
            super(id);
            this.level = level;
            System.out.println("Child(level=" + level + ")");
        }

        int level() {
            return level;
        }
    }

    public static void main(String[] args) {
        Child child = new Child("A-01", 3);
        System.out.println(child.id() + " / " + child.level());
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac SuperConstructorDemo.java
java SuperConstructorDemo
~~~

Stdout:

~~~text
Parent(A-01)
Child(level=3)
A-01 / 3
~~~

Khi tạo Child, lời gọi `super(id)` chọn constructor Parent(String). Parent gán trường private final của mình; sau khi constructor cha trả về, Child mới gán level. Hai trường thuộc cùng một đối tượng Child.

`super(id)` là lời gọi constructor tường minh đến superclass trực tiếp, không phải gọi một phương thức thông thường và không tạo Parent mới. Danh sách đối số chọn overload theo luật của Java.

## 3. Khi nào Java tự gọi super()?

Trong Java 17, nếu constructor không bắt đầu bằng `this(...)` hoặc `super(...)`, trình biên dịch chèn lời gọi **super() không tham số**. Constructor không tham số đó phải tồn tại và truy cập được.

~~~java
class Parent {
    Parent(String id) {}
}

class BrokenChild extends Parent {
    BrokenChild() {
        // LỖI: Java chèn super(), nhưng Parent() không tồn tại.
    }
}
~~~

Sửa bằng cách gọi overload có thật:

~~~java
class FixedChild extends Parent {
    FixedChild(String id) {
        super(id);
    }
}
~~~

Khi Parent đã khai báo ít nhất một constructor, Java không tự sinh constructor mặc định không tham số cho Parent. Nếu cần cả Parent() và Parent(String), phải khai báo cả hai. Một constructor private hoặc không truy cập được từ Child cũng không thể được chọn chỉ nhờ `super()` ngầm định.

## 4. this(...) không làm constructor cha chạy hai lần

`this(args)` ủy quyền sang constructor khác **trong cùng lớp**; `super(args)` gọi constructor superclass trực tiếp. Trong Java 17, lời gọi constructor tường minh phải đứng đầu constructor, nên không thể viết trực tiếp cả hai lời gọi trong một thân constructor.

Giả sử `Child()` gọi `this("guest")` và `Child(String role)` gọi `super(role)`. Thứ tự các **phần thân** chạy là `Parent(String)` → `Child(String)` → `Child()`. Chuỗi ủy quyền chỉ chọn đường khởi tạo; nó không tạo thêm đối tượng Parent hoặc Child và không khiến instance initializer chạy hai lần.

Bài “Chuỗi gọi super và truyền dữ liệu bắt buộc” sẽ theo dõi cách chuyển tham số và xác thực dữ liệu qua nhiều tầng kế thừa.

## 5. Constructor của abstract class vẫn chạy

Abstract class không thể được khởi tạo trực tiếp, nhưng vẫn có thể sở hữu trạng thái chung và constructor có thân:

~~~java
abstract class Account {
    private final String id;

    protected Account(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }
        this.id = id;
    }

    public final String id() {
        return id;
    }
}

final class SavingsAccount extends Account {
    SavingsAccount(String id) {
        super(id);
    }
}
~~~

`new SavingsAccount("A-01")` gọi constructor Account qua `super(id)`. Constructor cha kiểm tra và gán dữ liệu do Account sở hữu. Interface thì không có constructor; một lớp implements interface chỉ chạy constructor của các lớp trong chuỗi extends của nó.

## 6. Ngoại lệ và quyền truy cập

Nếu constructor cha khai báo checked exception, constructor con gọi `super(...)` phải khai báo ngoại lệ phù hợp trong `throws` (hoặc chọn một overload superclass không ném ngoại lệ đó). Trong Java 17, không thể bao lời gọi `super(...)` bằng `try/catch` vì lời gọi constructor tường minh phải đứng đầu constructor; caller có thể xử lý exception quanh biểu thức `new Child(...)`.

Nếu constructor cha ném exception, việc khởi tạo bị dừng; phần còn lại của constructor con không chạy và biểu thức `new Child(...)` không trả về một đối tượng khởi tạo thành công. Vì vậy, constructor nên kiểm tra dữ liệu và thiết lập trạng thái thuộc trách nhiệm của lớp mình; tránh thực hiện tác dụng phụ bên ngoài khó hoàn tác.

Mức truy cập cũng áp dụng cho constructor: public, protected, package-private và private quyết định nơi có thể gọi. Constructor private của Parent không thể được Child thông thường ở ngoài phạm vi truy cập gọi bằng `super(...)`.

## 7. Cảnh báo khi constructor gọi phương thức override

Constructor cha có thể gọi một phương thức instance bị Child override. Java vẫn chọn phương thức theo lớp runtime của đối tượng, trong khi các trường và initializer của Child có thể chưa sẵn sàng. Ví dụ, nếu Parent() gọi `label()` và Child override phương thức đó để đọc `label = "ready"`, lời gọi sớm có thể thấy null.

Tránh lời gọi overridable trực tiếp hoặc gián tiếp trong constructor. Phân tích chi tiết về dynamic dispatch, this escape và các cách sửa thuộc các bài chuyên biệt kế tiếp; ở đây chỉ cần nhớ rằng **constructor cha chạy trước khi phần khởi tạo riêng của Child hoàn tất**.

## 8. Phân biệt cú pháp

| Cú pháp | Tác dụng |
| --- | --- |
| `super(args)` | Gọi constructor superclass trực tiếp để khởi tạo phần cha của cùng đối tượng. |
| `this(args)` | Gọi constructor khác trong cùng lớp. |
| `super.method(args)` | Gọi implementation của phương thức ở superclass tại vị trí hợp lệ. |
| `this.method(args)` | Gọi phương thức trên đối tượng hiện tại; override vẫn có thể được dispatch. |
| `new Parent(args)` | Tạo một đối tượng Parent riêng. |

`super(...)` và `super.method(...)` không cùng cơ chế: một bên là lời gọi constructor, bên kia là lời gọi phương thức.

## 9. Lỗi thường gặp và tự kiểm tra

- **Constructor cha không tham số không tồn tại:** gọi `super(args)` đúng chữ ký hoặc cung cấp constructor cha có thể truy cập.
- **Cho rằng Child kế thừa Parent(int):** khai báo constructor Child(int) của chính lớp con rồi gọi `super(value)`.
- **Viết cả this(...) và super(...) trong cùng constructor:** chọn một lời gọi đầu tiên; constructor được gọi tiếp tục chuỗi.
- **Cho rằng abstract class không có constructor:** abstract class có constructor, nhưng không thể `new` trực tiếp.
- **Cho rằng constructor cha không thể ảnh hưởng đến Child:** lời gọi phương thức override từ constructor cha có thể thấy trạng thái Child chưa hoàn chỉnh.

**Câu hỏi 1.** Parent chỉ có Parent(String). Child() {} có biên dịch không?  
**Đáp án:** Không, vì Java 17 chèn super() nhưng Parent() không tồn tại.

**Câu hỏi 2.** Khi Child() gọi this("guest") và Child(String) gọi super("guest"), constructor Parent chạy mấy lần?  
**Đáp án:** Một lần cho đối tượng đó.

**Câu hỏi 3.** new SavingsAccount("A-01") có chạy constructor Account không?  
**Đáp án:** Có. Account không được khởi tạo riêng, nhưng constructor của nó chạy như một phần của chuỗi khởi tạo SavingsAccount.

Hãy nhớ: constructor cha khởi tạo phần trạng thái của mình trong cùng đối tượng lớp con; `super(...)` chọn constructor cha, còn `this(...)` ủy quyền giữa các constructor cùng lớp.