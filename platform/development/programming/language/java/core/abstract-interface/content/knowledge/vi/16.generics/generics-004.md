# Giới hạn kiểu tổng quát bằng abstract class và interface

## 1. Vì sao cần type bound?

Không có giới hạn, một type parameter T có thể đại diện cho nhiều kiểu tham chiếu khác nhau. Compiler chỉ cho phép gọi những phương thức được bảo đảm bởi kiểu đã biết. Nếu thuật toán cần lấy ID, một T tùy ý không đủ thông tin:

~~~java
static <T> String idOf(T value) {
    // value.id() không biên dịch: T chưa đảm bảo có id().
    return value.toString();
}
~~~

Khai báo giới hạn cho compiler biết kiểu nào được chấp nhận và những thành viên nào có thể gọi an toàn. Java dùng từ khóa **extends** cho cả giới hạn class lẫn interface.

## 2. Giới hạn bằng abstract class

Dùng abstract class làm bound khi thuật toán thật sự cần trạng thái hoặc hành vi được chia sẻ trong một họ kế thừa:

~~~java
abstract class NamedEntity {
    private final String name;

    protected NamedEntity(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }

    public abstract String category();
}

static <T extends NamedEntity> String labelOf(T value) {
    return value.name() + " (" + value.category() + ")";
}
~~~

Với **T extends NamedEntity**, mọi đối số kiểu hợp lệ phải là NamedEntity hoặc lớp con hợp lệ của nó. Vì vậy, labelOf có thể gọi name() và category() mà không cast. Không thể khởi tạo trực tiếp NamedEntity vì nó là abstract; lớp cụ thể phải cung cấp category() trước khi tạo đối tượng.

Bound bằng class phù hợp khi lớp nền thể hiện một quan hệ kế thừa thật sự. Đổi lại, Java chỉ cho một class cha trực tiếp, nên giới hạn bằng class có thể loại trừ các kiểu không thuộc họ đó.

## 3. Giới hạn bằng interface

Nếu thuật toán chỉ cần một khả năng, interface thường là bound linh hoạt hơn:

~~~java
interface Identifiable {
    String id();
}

static <T extends Identifiable> String idOf(T value) {
    return value.id();
}
~~~

Bất kỳ lớp nào triển khai Identifiable đều có thể truyền vào idOf, kể cả khi các lớp đó kế thừa những class khác nhau. Bound mô tả khả năng mà thuật toán cần thay vì buộc tất cả đối tượng dùng chung một class cha.

**Cú pháp cần phân biệt:** `class Account extends NamedEntity implements Identifiable` nêu class cha và interface mà `Account` cam kết thực hiện; lớp cụ thể còn phải có constructor hợp lệ và cài đặt các phương thức abstract cần thiết. Trong `<T extends Identifiable>` của generic method, `extends` đặt bound cho T, dù `Identifiable` là interface. Viết **&lt;T implements Identifiable&gt;** là sai cú pháp. Ví dụ chạy được ở phần 5 cho thấy cả hai vị trí.

## 4. Kết hợp class bound và interface bound

Một type parameter có thể yêu cầu kiểu vừa thuộc một họ class vừa thực hiện interface:

~~~java
abstract class NamedEntity {
    public abstract String name();
}

interface Identifiable {
    String id();
}

static <T extends NamedEntity & Identifiable> String describe(T value) {
    return value.name() + ", id=" + value.id();
}
~~~

Nếu có class bound, nó phải đứng đầu; các interface đứng sau và phân cách bằng dấu &. Chỉ được có tối đa một class bound. Chi tiết về nhiều interface, intersection type và intersection cast thuộc bài tiếp theo; ở đây cần hiểu rằng T phải đáp ứng mọi giới hạn đã nêu.

## 5. Ví dụ hoàn chỉnh

Lưu mã vào **TypeBoundsDemo.java**:

~~~java
abstract class NamedEntity {
    private final String name;

    protected NamedEntity(String name) {
        this.name = name;
    }

    public final String name() {
        return name;
    }
}

interface Identifiable {
    String id();
}

final class Account extends NamedEntity implements Identifiable {
    private final String id;

    Account(String name, String id) {
        super(name);
        this.id = id;
    }

    @Override
    public String id() {
        return id;
    }
}

public class TypeBoundsDemo {
    static <T extends NamedEntity & Identifiable> String describe(T value) {
        return value.name() + ", id=" + value.id();
    }

    static <T extends Identifiable> String idOf(T value) {
        return value.id();
    }

    public static void main(String[] args) {
        Account account = new Account("Lan", "U-17");
        System.out.println(describe(account));
        System.out.println(idOf(account));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac TypeBoundsDemo.java
java TypeBoundsDemo
~~~

Kết quả:

~~~text
Lan, id=U-17
U-17
~~~

Account kế thừa NamedEntity và triển khai Identifiable, nên đáp ứng cả hai bound của describe. idOf chỉ cần Identifiable, vì vậy nó có thể nhận những kiểu không kế thừa NamedEntity. Hãy đặt bound theo đúng các thao tác phương thức cần gọi.

## 6. Type bound khác wildcard bound

~~~java
static <T extends Identifiable> T requireId(T value) {
    return value;
}

static void printIds(java.util.List<? extends Identifiable> values) {
    for (Identifiable value : values) {
        System.out.println(value.id());
    }
}
~~~

**&lt;T extends Identifiable&gt;** đặt tên T để liên kết nhiều vị trí trong chữ ký, chẳng hạn đầu vào và kiểu trả về. **? extends Identifiable** mô tả một kiểu phần tử chưa biết nhưng có thể đọc như Identifiable. Wildcard phù hợp với API đọc dữ liệu; type parameter có tên hữu ích khi cần giữ quan hệ kiểu giữa các vị trí. Bài về invariance và wildcard trình bày lựa chọn này chi tiết hơn.

## 7. Lỗi thường gặp

- Dùng **implements** trong bound thay vì **extends**.
- Đặt interface trước class bound, ví dụ **&lt;T extends Identifiable & NamedEntity&gt;** khi NamedEntity là class.
- Khai báo hai class bound cho cùng một T.
- Gọi phương thức riêng của một lớp triển khai khi bound không bảo đảm phương thức đó tồn tại.
- Đặt bound quá hẹp và loại bỏ các kiểu có thể dùng được, hoặc quá rộng khiến compiler không cho gọi thao tác cần thiết.

Type erasure dùng bound đầu tiên để xác định kiểu xóa của type variable; điều đó không làm mất các ràng buộc còn lại ở thời điểm biên dịch. Bài về type erasure giải thích hệ quả ở bytecode/runtime.