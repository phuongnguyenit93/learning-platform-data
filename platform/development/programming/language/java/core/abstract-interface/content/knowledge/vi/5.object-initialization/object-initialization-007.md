# Constructor không được kế thừa và không thể abstract trong Java

Trong Java, **constructor không được kế thừa** và **không thể khai báo abstract**, kể cả khi constructor nằm trong một abstract class. Hai quy tắc này không mâu thuẫn với việc constructor lớp cha vẫn chạy khi tạo lớp con.

- **Không được kế thừa:** Parent(int) không tự trở thành constructor Child(int). Mỗi lớp có các constructor của riêng mình.
- **Không thể abstract:** constructor cần có thân để tham gia quá trình khởi tạo. Java không có cơ chế override constructor để lớp con cung cấp phần thân còn thiếu.
- **Vẫn được gọi:** constructor Child có thể gọi constructor Parent trực tiếp qua super(...). Đây là chuỗi gọi constructor, không phải kế thừa constructor.

## 1. Constructor gắn với lớp khai báo

~~~java
class Parent {
    Parent() {}
    Parent(int value) {}
}

class Child extends Parent {
    // Compiler sinh Child() vì lớp này chưa khai báo constructor.
}
~~~

`new Child()` hợp lệ vì Child có constructor mặc định không tham số và Parent() có thể được gọi. Nhưng `new Child(10)` không hợp lệ: Parent(int) không được kế thừa thành Child(int).

Để tạo Child bằng một số nguyên, khai báo constructor của chính Child:

~~~java
class Child extends Parent {
    Child(int value) {
        super(value);
    }
}
~~~

`super(value)` gọi Parent(int) để khởi tạo phần superclass của cùng đối tượng Child. Nó không biến constructor cha thành constructor của Child.

## 2. Kế thừa, override, overload và chaining

| Cơ chế | Có áp dụng cho constructor? | Ý nghĩa |
| --- | --- | --- |
| Kế thừa | Không | Parent(int) không được thêm vào tập constructor của Child. |
| Override | Không | Constructor không tham gia dynamic dispatch và không dùng @Override. |
| Overload | Có | Một lớp có thể khai báo nhiều constructor với danh sách tham số khác nhau. |
| this(...) | Có | Gọi constructor khác trong cùng lớp. |
| super(...) | Có | Gọi constructor của superclass trực tiếp. |

Java chỉ sinh constructor mặc định không tham số khi lớp **không khai báo bất kỳ constructor nào**. Nếu đã khai báo Child(int), compiler không tự thêm Child(). Constructor mặc định được sinh cũng là constructor của chính lớp đó và chỉ hợp lệ nếu lời gọi constructor cha tương ứng hợp lệ.

Cũng đừng nhầm constructor với phương thức có tên trùng lớp nhưng có kiểu trả về. Ví dụ `void Child(int value)` là một phương thức, không phải constructor.

## 3. Abstract class có constructor có thân

Abstract class không thể được khởi tạo trực tiếp, nhưng có thể có nhiều constructor để khởi tạo trạng thái chung. Ví dụ sau chạy được; lưu thành **ConstructorRulesDemo.java**:

~~~java
abstract class Resource {
    private final String name;

    protected Resource(String name) {
        this.name = name;
        System.out.println("Resource(String): " + name);
    }

    protected Resource(String name, boolean verbose) {
        this(name);
        if (verbose) {
            System.out.println("Resource(String, boolean): verbose");
        }
    }

    public final String name() {
        return name;
    }

    public abstract String use();
}

final class FileResource extends Resource {
    private final String extension;

    FileResource(String name, String extension) {
        super(name, true);
        this.extension = extension;
        System.out.println("FileResource: " + extension);
    }

    @Override
    public String use() {
        return name() + "." + extension;
    }
}

public class ConstructorRulesDemo {
    public static void main(String[] args) {
        FileResource file = new FileResource("bao-cao", "txt");
        Resource resource = file;
        System.out.println("use: " + resource.use());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ConstructorRulesDemo.java
java ConstructorRulesDemo
~~~

Stdout:

~~~text
Resource(String): bao-cao
Resource(String, boolean): verbose
FileResource: txt
use: bao-cao.txt
~~~

Constructor FileResource gọi Resource(String, boolean) bằng super(...). Constructor đó gọi Resource(String) qua this(...), nên phần gán name chỉ tập trung ở một nơi. Sau khi chuỗi constructor cha hoàn tất, FileResource mới gán extension. Resource là abstract nhưng constructor có thân và vẫn chạy khi tạo FileResource.

## 4. Vì sao constructor không thể abstract?

Phương thức abstract mô tả hành vi chưa được cài đặt và yêu cầu lớp con cung cấp implementation. Constructor có vai trò khác: nó tham gia tạo và khởi tạo đối tượng, và phải đưa quá trình gọi constructor cha vào một chuỗi hợp lệ. Vì constructor không được override, không có cơ chế để chọn một “implementation constructor” ở runtime như với phương thức instance.

Khai báo sau không hợp lệ:

~~~java
abstract class InvalidResource {
    abstract InvalidResource(); // LỖI: constructor không thể abstract.
}
~~~

Cách đúng là để constructor có thân và tách hành vi cần lớp con hiện thực thành phương thức abstract:

~~~java
abstract class ResourceBase {
    protected ResourceBase() {
        // Khởi tạo trạng thái chung.
    }

    public abstract void use();
}

final class ConcreteResource extends ResourceBase {
    @Override
    public void use() {
        System.out.println("using");
    }
}
~~~

`ResourceBase()` khởi tạo phần chung; use() là hợp đồng hành vi mà lớp con cụ thể phải triển khai. Abstract class có constructor và constructor không thể abstract đều đúng.

## 5. Các lỗi biên dịch điển hình

| Tình huống | Nguyên nhân và cách xử lý |
| --- | --- |
| Child không khai báo constructor nhưng Parent chỉ có Parent(int) | Compiler định sinh Child() gọi super(), nhưng Parent() không tồn tại. Khai báo Child(int) gọi super(value). |
| Constructor cha private hoặc không truy cập được | Không có constructor superclass phù hợp mà subclass có quyền gọi. Kiểm tra access modifier và package. |
| Gắn @Override lên constructor | Constructor không override. Bỏ annotation và khai báo constructor riêng của Child. |
| Đặt lệnh thông thường trước super(...) trong Java 17 | Lời gọi constructor tường minh phải đứng đầu. Đưa công việc khác xuống sau super(...). |
| Gọi cả this(...) và super(...) trong cùng constructor | Chỉ chọn một lời gọi đầu tiên; constructor đích tiếp tục chuỗi. |
| Dùng modifier abstract, final hoặc static cho constructor | Các modifier đó không áp dụng cho constructor; chỉ dùng modifier truy cập và throws khi cần. |

Ví dụ thiếu constructor cha không tham số:

~~~java
class Base {
    Base(int id) {}
}

class Derived extends Base {
    // Lỗi: constructor mặc định Derived() sẽ gọi super().
}
~~~

Sửa bằng constructor tường minh:

~~~java
class Derived extends Base {
    Derived(int id) {
        super(id);
    }
}
~~~

Vấn đề là lời gọi super() không hợp lệ, không phải constructor Base(int) được kế thừa hoặc không được kế thừa.

## 6. Một cảnh báo liên quan đến đa hình

Constructor không override được, nhưng constructor cha có thể gọi một phương thức instance mà lớp con override. Khi đó Java vẫn dispatch theo lớp runtime, và trường của lớp con có thể chưa được khởi tạo. Tránh gọi hook overridable từ constructor; bài về rủi ro gọi phương thức override trong constructor trình bày ví dụ, hậu quả và cách thiết kế an toàn.

Đừng cố sửa bằng cách thêm @Override hoặc thay constructor bằng một phương thức tên gần giống. Điều cần thay đổi là điểm gọi của hành vi đa hình, hoặc thiết kế khởi tạo, chứ không phải cơ chế constructor inheritance.

## 7. Bài tập tự kiểm tra

**Câu 1.** Parent có Parent() và Parent(int). Child không khai báo constructor. Lệnh new Child() và new Child(5) có hợp lệ không?  
**Đáp án:** new Child() hợp lệ vì compiler sinh Child() gọi super(). new Child(5) không hợp lệ vì Child(int) không được kế thừa.

**Câu 2.** Abstract class Base chỉ có Base(String). Viết constructor cho Concrete để tạo new Concrete("A").  
**Đáp án:** Concrete(String name) { super(name); }.

**Câu 3.** Vì sao protected Base() hợp lệ nhưng abstract Base() không hợp lệ?  
**Đáp án:** Constructor có thể có thân và mức truy cập; constructor không thể abstract vì không được override. Hành vi chưa cài đặt nên được mô tả bằng phương thức abstract.

**Câu 4.** Có thể gọi cả this(...) và super(...) trực tiếp trong cùng constructor Java 17 không?  
**Đáp án:** Không. Nếu constructor gọi this(...), constructor được ủy quyền sẽ tiếp tục chuỗi đến superclass.

Hãy nhớ bốn điều: constructor không được kế thừa, không override, có thể overload, và có thể gọi constructor cha. Abstract class có constructor có thân; lớp con dùng super(...) để khởi tạo phần superclass và dùng phương thức abstract để cung cấp hành vi còn thiếu.