# Object.clone() protected và yêu cầu public của interface

Object.clone() có phạm vi protected. Một interface có thể khai báo clone() như một method công khai, nhưng lớp triển khai phải cung cấp một implementation public phù hợp; method protected được kế thừa từ Object không đáp ứng hợp đồng public của interface.

## 1. Phạm vi truy cập của Object.clone()

Chữ ký nền tảng có dạng:

~~~java
protected native Object clone() throws CloneNotSupportedException;
~~~

- **protected** là quy tắc truy cập tại compile time. Code trong cùng package có thể truy cập theo quy tắc package; subclass có thể truy cập theo các điều kiện protected. Code ngoài package không thể tùy ý gọi someObject.clone().
- **native** cho biết phần triển khai đến từ runtime thay vì thân Java thông thường.
- **CloneNotSupportedException** là checked exception mà method có thể ném khi object không hỗ trợ cơ chế clone mặc định.
- **Object** là kiểu trả về của method gốc. Override có thể dùng kiểu trả về cụ thể hơn theo quy tắc covariant return type.

Lỗi truy cập lúc biên dịch khác với CloneNotSupportedException lúc chạy. Một lệnh gọi có thể bị từ chối vì caller không có quyền truy cập, hoặc caller có quyền truy cập nhưng cơ chế clone không được hỗ trợ.

## 2. Interface yêu cầu một method public

Method thông thường trong interface là public theo mặc định. Interface không có method protected:

~~~java
interface PublicClone {
    Object clone() throws CloneNotSupportedException;
}
~~~

Dù không ghi modifier public, clone() trong PublicClone vẫn là public. Nếu class chỉ thừa hưởng protected Object.clone(), nó chưa đáp ứng method public mà PublicClone yêu cầu. Class phải override clone() thành public; Java cho phép mở rộng quyền truy cập khi override, nhưng không cho thu hẹp quyền truy cập của method public.

~~~java
interface PublicClone {
    Object clone() throws CloneNotSupportedException;
}

class InvalidNote implements PublicClone {
    // Không hợp lệ: inherited Object.clone() vẫn protected.
    // Class phải cung cấp một implementation public phù hợp.
}
~~~

Tên clone không bị cấm trong interface. Vấn đề là visibility của implementation phải đáp ứng hợp đồng public.

## 3. Ví dụ hoàn chỉnh

~~~java
public class InterfaceCloneDemo {
    interface PublicClone {
        Object clone() throws CloneNotSupportedException;
    }

    static final class Note implements PublicClone, Cloneable {
        private final String text;

        Note(String text) {
            this.text = text;
        }

        @Override
        public Note clone() throws CloneNotSupportedException {
            return (Note) super.clone();
        }

        String text() {
            return text;
        }
    }

    public static void main(String[] args) throws CloneNotSupportedException {
        Note original = new Note("Java");
        PublicClone publicView = original;
        Note copy = original.clone();
        Object throughInterface = publicView.clone();

        System.out.println(copy.text());
        System.out.println(original == copy);
        System.out.println(throughInterface.getClass().getSimpleName());
    }
}
~~~

Kết quả:

~~~text
Java
false
Note
~~~

Note khai báo public clone(), trả về Note theo kiểu covariant và gọi super.clone(). PublicClone cho phép caller gọi clone() qua biến có kiểu interface. Cloneable là cơ chế riêng: nó cho phép Object.clone() mặc định tạo bản sao; nó không làm clone thành public và không khai báo method clone().

## 4. Visibility và khả năng clone không giống nhau

| Trường hợp | Kết quả |
| --- | --- |
| Class implements Cloneable nhưng không override clone() | Biên dịch được; method kế thừa vẫn protected |
| Interface yêu cầu public clone(), class chỉ thừa hưởng protected clone() | Không đáp ứng hợp đồng interface |
| Class override clone() thành public và supports Cloneable | Có thể công khai clone; super.clone() mặc định tạo bản sao |
| Class public clone() gọi super.clone() nhưng không supports Cloneable | Có thể biên dịch, nhưng cơ chế Object.clone() ném CloneNotSupportedException |
| Class không dùng Object.clone() mà tự viết method clone() | Hành vi phụ thuộc implementation do class định nghĩa |

Cloneable là marker interface rỗng. Vì vậy, biến có kiểu Cloneable không thể gọi clone() qua chính interface đó. Nếu API cần một thao tác sao chép đa hình, hãy định nghĩa interface có method copy() với ngữ nghĩa rõ ràng.

## 5. Shallow copy và lựa chọn API

Object.clone() mặc định sao chép giá trị các trường. Trường primitive được sao chép giá trị; trường tham chiếu sao chép tham chiếu nên object mutable bên trong có thể bị chia sẻ giữa bản gốc và bản clone. Public visibility không làm bản sao trở thành deep copy.

~~~java
class Profile implements Cloneable {
    StringBuilder label = new StringBuilder("Java");

    @Override
    public Profile clone() throws CloneNotSupportedException {
        return (Profile) super.clone();
    }
}
~~~

Hai Profile sau clone là hai object khác nhau nhưng có thể dùng chung StringBuilder. Nếu cần trạng thái độc lập, implementation phải sao chép rõ các trường mutable. Copy constructor hoặc static factory thường thể hiện ý định tốt hơn và có thể chạy lại validation trong constructor.

Nguồn tham khảo:
- [Java SE 17 API: Object.clone()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#clone())
- [Java SE 17 API: Cloneable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Cloneable.html)
- [JLS 17 §9.4: Interface Method Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4)
- [JLS 17 §8.4.8: Overriding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8)

Tự kiểm tra:
- Cloneable có khai báo clone() không? Không.
- Interface có thể yêu cầu protected clone() không? Không; method interface thông thường là public.
- Vì sao public clone() không bảo đảm deep copy? Vì Object.clone() sao chép nông các trường.
