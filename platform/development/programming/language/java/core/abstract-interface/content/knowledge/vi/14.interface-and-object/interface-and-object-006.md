# Giới hạn của marker interface Cloneable trong Java

Cloneable là một dấu hiệu để cơ chế mặc định của Object.clone() biết rằng object được phép clone. Nó không khai báo phương thức sao chép, không mở quyền truy cập public, và không bảo đảm bản sao độc lập hay giữ được mọi invariant của lớp.

## 1. Marker đánh dấu khả năng, không cung cấp thao tác

~~~java
public interface Cloneable {
}
~~~

Đây là hình dạng của interface chuẩn java.lang.Cloneable: không có method nào. Vì vậy, biến có kiểu Cloneable không thể gọi x.clone(); compiler không tìm thấy method clone() trong interface. Object.clone() được khai báo protected và phải được gọi từ ngữ cảnh có quyền truy cập phù hợp. Phần API public và hợp đồng interface được trình bày ở bài về clone protected.

Với hành vi mặc định của Object.clone(), runtime kiểm tra object có thuộc một class implements Cloneable hay không, kể cả qua kế thừa. Nếu không, nó ném CloneNotSupportedException. Nếu có, nó tạo object mới cùng lớp runtime và sao chép giá trị các trường theo kiểu shallow copy.

~~~text
Object.clone() được gọi
    |
    +-- object không hỗ trợ Cloneable
    |       -> CloneNotSupportedException
    |
    +-- object hỗ trợ Cloneable
            -> tạo object mới cùng lớp runtime
            -> sao chép giá trị trường
            -> không clone đệ quy mọi object được tham chiếu
~~~

Một class có thể tự định nghĩa method tên clone() theo cách riêng. Không nên suy ra mọi method cùng tên đều dùng cơ chế Object.clone().

## 2. Chương trình minh họa shallow copy

~~~java
public class CloneableLimitsDemo {
    static final class Address {
        String city;
        Address(String city) { this.city = city; }
    }

    static final class Person implements Cloneable {
        final String name;
        final Address address;

        Person(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        @Override
        public Person clone() {
            try {
                return (Person) super.clone();
            } catch (CloneNotSupportedException e) {
                throw new AssertionError(e);
            }
        }
    }

    static final class WithoutMarker {
        @Override
        public WithoutMarker clone() throws CloneNotSupportedException {
            return (WithoutMarker) super.clone();
        }
    }

    static final class SafePerson {
        final String name;
        final Address address;

        SafePerson(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        SafePerson copy() {
            return new SafePerson(name, new Address(address.city));
        }
    }

    public static void main(String[] args) throws CloneNotSupportedException {
        Person original = new Person("Lan", new Address("Hà Nội"));
        Person cloned = original.clone();
        System.out.println(original != cloned);
        System.out.println(original.address == cloned.address);
        cloned.address.city = "Huế";
        System.out.println(original.address.city);

        SafePerson safe = new SafePerson("Minh", new Address("Đà Nẵng"));
        SafePerson independent = safe.copy();
        independent.address.city = "Cần Thơ";
        System.out.println(safe.address.city);

        try {
            new WithoutMarker().clone();
        } catch (CloneNotSupportedException e) {
            System.out.println(e.getClass().getSimpleName());
        }

        int[][] matrix = {{1, 2}};
        int[][] matrixClone = matrix.clone();
        System.out.println(matrix != matrixClone);
        System.out.println(matrix[0] == matrixClone[0]);
    }
}
~~~

Kết quả:

~~~text
true
true
Huế
Đà Nẵng
CloneNotSupportedException
true
true
~~~

Person là hai object khác nhau sau clone, nhưng cùng tham chiếu Address. Sửa địa chỉ qua bản clone cũng thay đổi dữ liệu mà bản gốc nhìn thấy. SafePerson.copy() chủ động tạo Address mới nên hai object không chia sẻ địa chỉ. WithoutMarker biên dịch được nhưng super.clone() ném CloneNotSupportedException vì object không hỗ trợ marker. Với mảng nhiều chiều, clone mảng ngoài không clone các mảng con.

## 3. Những điều Cloneable không bảo đảm

Cloneable không định nghĩa:
- Deep copy toàn bộ đồ thị object.
- Hai object sau clone phải bằng nhau theo equals().
- Quy tắc giữ, xóa hoặc tạo mới ID nghiệp vụ.
- Cách sao chép socket, file descriptor, lock, listener, cache hay transaction.
- Snapshot nhất quán khi nhiều thread đang sửa trạng thái.
- Việc constructor hoặc field initializer chạy lại để kiểm tra invariant.

Object.clone() tạo object mà không chạy constructor của lớp đích theo cách new thông thường. Vì vậy, nếu constructor đăng ký listener, kiểm tra dữ liệu hoặc khởi tạo tài nguyên, shallow clone có thể bỏ qua những bước đó. Trường final chỉ cấm gán lại tham chiếu sau khởi tạo; nó không khiến object được tham chiếu trở nên immutable. Ví dụ final Address vẫn bị chia sẻ trong chương trình trên.

Không phải mọi clone đều sai. Shallow copy có thể phù hợp với lớp được thiết kế có toàn bộ trạng thái primitive hoặc tham chiếu immutable. Nhưng marker không chứng minh điều đó; lớp phải định nghĩa và kiểm thử ngữ nghĩa bản sao.

## 4. Kế thừa và trạng thái mutable

Nếu superclass implements Cloneable, subclass thường cũng hỗ trợ marker qua kế thừa. Điều đó không tự bảo đảm các trường mới của subclass được sao chép đúng theo nghiệp vụ. Một List mutable mới thêm vào subclass vẫn được chia sẻ sau shallow clone. Superclass cũng có thể override clone() theo hợp đồng riêng, nên không được giả định mọi đường gọi đều đi thẳng đến implementation mặc định của Object.

Mảng Java là trường hợp đặc biệt: mảng hỗ trợ clone(). Clone một mảng primitive tạo mảng mới với các giá trị primitive được sao chép. Với mảng tham chiếu hoặc mảng nhiều chiều, các phần tử là tham chiếu và không được clone đệ quy. Vì thế, matrix.clone() tạo mảng ngoài mới nhưng vẫn dùng chung từng mảng con.

## 5. Khi nào nên dùng copy constructor hoặc factory?

~~~java
public final class Snapshot {
    private final String name;
    private final java.util.List<String> tags;

    public Snapshot(String name, java.util.List<String> tags) {
        this.name = java.util.Objects.requireNonNull(name);
        this.tags = java.util.List.copyOf(tags);
    }

    public Snapshot(Snapshot source) {
        this(source.name, source.tags);
    }

    public Snapshot copy() {
        return new Snapshot(this);
    }

    public java.util.List<String> tags() {
        return tags;
    }
}
~~~

Snapshot dùng List.copyOf để giữ danh sách không sửa được qua API trả ra. Vì phần tử là String immutable, chia sẻ phần tử an toàn cho ví dụ này; List.copyOf không phải deep copy tổng quát cho các phần tử mutable.

Copy constructor hoặc static factory làm rõ trường nào được chia sẻ, trường nào được sao chép, và cho phép kiểm tra invariant trong constructor. Nếu cần một hợp đồng sao chép đa hình, có thể định nghĩa interface riêng:

~~~java
interface Copyable<T> {
    T copy();
}
~~~

Tuy vậy, chữ ký copy() vẫn cần tài liệu hóa mức độ độc lập, lỗi có thể phát sinh và quy tắc giữ trạng thái. Nếu object vốn immutable, có thể không cần clone; tái sử dụng instance thường đơn giản hơn.

## 6. Lỗi thường gặp

| Nhận định | Vấn đề | Cách xử lý |
| --- | --- | --- |
| implements Cloneable nghĩa là caller gọi được clone() từ mọi nơi | Object.clone() vẫn protected | Cung cấp API public nếu thật sự cần |
| Cloneable có method clone() | Marker interface rỗng | Phân biệt marker với method của Object |
| Clone tự sao chép mọi object bên trong | Object.clone() mặc định shallow | Sao chép rõ từng trường mutable cần độc lập |
| final field không bị chia sẻ | final không làm object được tham chiếu immutable | Kiểm tra identity và trạng thái của object con |
| Clone chạy constructor | Cơ chế clone không dùng constructor như new | Dùng constructor/factory nếu cần thiết lập lại invariant |
| Cloneable bảo đảm clone an toàn qua inheritance | subtype có thể thêm trạng thái hoặc tài nguyên | Thiết kế và kiểm thử hợp đồng cho cả hierarchy |

## 7. Checklist thiết kế

1. Xác định API nào cho phép caller yêu cầu sao chép; đừng dựa vào marker để suy ra visibility.
2. Quyết định các object mutable nào được phép chia sẻ giữa bản gốc và bản sao.
3. Kiểm tra field final có tham chiếu tới object mutable hay không.
4. Xem constructor có thiết lập invariant, đăng ký listener hoặc quản lý tài nguyên không.
5. Với inheritance, kiểm tra cả các trường được thêm bởi subtype.
6. Kiểm thử identity bằng == và thay đổi trạng thái sau copy; equals() đúng không có nghĩa hai object không chia sẻ trạng thái.
7. Cân nhắc copy constructor, static factory hoặc copy() có tên rõ ràng khi cần semantics sao chép có kiểm soát.

Tự kiểm tra:
- Class chỉ implements Cloneable nhưng không override clone(): caller bên ngoài có mặc nhiên gọi được không? Không.
- Nếu object không hỗ trợ Cloneable nhưng public clone() gọi super.clone(), điều gì xảy ra? Cơ chế mặc định ném CloneNotSupportedException.
- Vì sao final Address vẫn có thể bị chia sẻ sau clone? Clone sao chép giá trị tham chiếu, còn final chỉ ngăn gán lại trường.
- Mảng hai chiều sau khi clone mảng ngoài có hoàn toàn độc lập không? Không; mảng con vẫn được chia sẻ.

Cloneable chỉ bật một nhánh hành vi đặc biệt của Object.clone(). Nó không thay thế hợp đồng sao chép do API thiết kế, cũng không bảo đảm bản sao an toàn. Hãy chọn Cloneable khi cần tương thích với cơ chế này và đã xác định rõ shallow/deep copy, invariant cùng trạng thái được chia sẻ.
