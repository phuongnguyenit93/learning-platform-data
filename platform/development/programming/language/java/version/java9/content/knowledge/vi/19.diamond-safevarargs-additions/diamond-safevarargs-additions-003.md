# Quy tắc phương thức bổ sung của lớp ẩn danh dùng diamond

## 1. Bối cảnh

Toán tử kim cương (diamond operator) dùng cặp dấu nhọn rỗng <> trong lệnh tạo đối tượng generic. Trình biên dịch suy luận tham số kiểu thay vì buộc người viết lặp lại chúng. Từ Java 9, cú pháp này có thể được dùng cùng phần thân lớp ẩn danh:

~~~java
List<String> names = new ArrayList<>() {
    // phần thân của lớp ẩn danh
};
~~~

Trong ví dụ, kiểu đích List<String> giúp trình biên dịch suy luận tham số kiểu String cho ArrayList. Cú pháp này hữu ích khi cần tùy chỉnh một vài hành vi của đối tượng ngay tại chỗ mà không tạo lớp có tên riêng.

Khi kết hợp diamond với lớp ẩn danh, Java áp dụng một quy tắc riêng cho các phương thức được khai báo trong phần thân lớp. Quy tắc này giúp kiểu được suy luận vẫn có thể biểu diễn qua kiểu cha hoặc interface đã khai báo.

## 2. Quy tắc bắt buộc với phương thức

Nếu biểu thức tạo đối tượng dùng diamond và có phần thân lớp ẩn danh, mọi phương thức được khai báo trong lớp ẩn danh phải thuộc một trong hai nhóm:

1. Phương thức không private phải override một phương thức của lớp cha hoặc implement một phương thức của interface.
2. Phương thức bổ sung không override phương thức nào chỉ được khai báo với quyền truy cập private.

Vì vậy, các phương thức public, protected và package-private trong lớp ẩn danh dùng diamond đều phải override hoặc implement phương thức có sẵn. Một phương thức mới không có trong supertype sẽ gây lỗi biên dịch nếu nó không private.

Quy tắc áp dụng cho phương thức được khai báo trong phần thân lớp ẩn danh. Nó không có nghĩa là mọi phương thức phải viết lại: lớp ẩn danh vẫn kế thừa và sử dụng bình thường các phương thức có sẵn từ lớp cha hoặc interface.

### Phương thức override được phép

Các phương thức override có thể giữ mức truy cập hợp lệ theo quy tắc kế thừa. Ví dụ sau override add của ArrayList và thêm một helper private để chuẩn hóa chuỗi:

~~~java
import java.util.ArrayList;
import java.util.List;

public class DiamondAnonymousDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>() {
            @Override
            public boolean add(String name) {
                return super.add(normalize(name));
            }

            private String normalize(String name) {
                return name.trim();
            }
        };

        names.add("  Java 9  ");
        System.out.println(names.get(0));
    }
}
~~~

Biên dịch và chạy bằng Java 9 trở lên:

~~~bash
javac --release 9 DiamondAnonymousDemo.java
java DiamondAnonymousDemo
~~~

Kết quả:

~~~text
Java 9
~~~

Trong ví dụ:

- add(String) là phương thức override từ ArrayList nên được phép khai báo public.
- normalize(String) là helper bổ sung, không override phương thức nào nên được khai báo private.
- Biến names có kiểu khai báo List<String>; vì vậy mã bên ngoài chỉ gọi được các phương thức thuộc List, chẳng hạn add và get.

### Phương thức bổ sung không private bị từ chối

Ví dụ sau không biên dịch:

~~~java
List<String> names = new ArrayList<>() {
    public void resetNames() {
        clear();
    }
};
~~~

resetNames() là phương thức public mới, không override hay implement phương thức nào của ArrayList hoặc List. Trình biên dịch báo lỗi tương tự:

~~~text
method does not override or implement a method from a supertype
(due to <>, every non-private method declared in this anonymous class
must override or implement a method from a supertype)
~~~

Đổi public thành protected hoặc bỏ modifier để thành package-private cũng không giải quyết được lỗi, vì cả ba mức truy cập đó đều không phải private.

### Cách sửa khi chỉ cần helper nội bộ

Nếu phương thức chỉ phục vụ các phương thức khác bên trong lớp ẩn danh, khai báo nó là private:

~~~java
List<String> names = new ArrayList<>() {
    @Override
    public boolean add(String name) {
        return super.add(normalize(name));
    }

    private String normalize(String name) {
        return name.trim();
    }
};
~~~

Đây là cách phù hợp khi muốn giữ diamond và chỉ cần logic hỗ trợ nội bộ. Phương thức private không trở thành một phần API có thể gọi qua biến kiểu List<String>.

## 3. Khi thật sự cần phương thức bổ sung public

Nếu lớp ẩn danh cần khai báo một phương thức public mới, hãy bỏ diamond và ghi rõ tham số kiểu:

~~~java
new ArrayList<String>() {
    public void addNormalized(String value) {
        add(value.trim());
    }
};
~~~

Khi không dùng diamond, giới hạn đặc biệt nêu trên không áp dụng. Các quy tắc Java thông thường về override, quyền truy cập và kiểu tham chiếu vẫn được áp dụng.

Tuy nhiên, nếu đối tượng được gán cho một biến có kiểu khai báo là List<String> hoặc ArrayList<String>, mã bên ngoài vẫn không thể gọi addNormalized qua biến đó. Kiểu tham chiếu quyết định những thành viên nào có thể được gọi.

Từ Java 10, var có thể giữ lại kiểu của lớp ẩn danh trong biến cục bộ. Kết hợp var với tham số kiểu viết tường minh cho phép gọi phương thức bổ sung:

~~~java
import java.util.ArrayList;

public class ExplicitTypeAnonymousDemo {
    public static void main(String[] args) {
        var names = new ArrayList<String>() {
            public void addNormalized(String value) {
                add(value.trim());
            }
        };

        names.addNormalized(" Java 9 ");
        System.out.println(names);
    }
}
~~~

Kết quả:

~~~text
[Java 9]
~~~

Đây là ví dụ Java 10 trở lên vì sử dụng var. Việc dùng var không loại bỏ giới hạn của diamond: nếu đổi phần tạo đối tượng thành new ArrayList<>() và vẫn khai báo addNormalized() là public, trình biên dịch vẫn từ chối.

Nếu phương thức bổ sung là một phần API mà nhiều nơi cần sử dụng, một lớp có tên riêng thường rõ ràng và dễ bảo trì hơn lớp ẩn danh.

## 4. Cách xác định một phương thức có hợp lệ hay không

Khi đọc phần thân của lớp ẩn danh dùng diamond, hãy kiểm tra từng phương thức:

- Phương thức có thực sự override phương thức của lớp cha hoặc implement phương thức của interface không? Nếu có, có thể khai báo với mức truy cập hợp lệ.
- Nếu không override, phương thức có được khai báo private không? Nếu có, đây là helper nội bộ hợp lệ.
- Nếu phương thức mới cần public, protected hoặc package-private, hãy bỏ diamond và ghi rõ tham số kiểu, hoặc cân nhắc tạo lớp có tên riêng.

Annotation @Override nên được dùng cho các phương thức dự định override. Annotation giúp trình biên dịch phát hiện lỗi sai tên hoặc sai chữ ký; nó không biến một phương thức mới thành phương thức override.

Một phương thức overload cũng không tự động được xem là override. Ví dụ, nếu lớp cha có add(String), một phương thức add(Object) không override chữ ký đó chỉ vì trùng tên. Nếu khai báo nó là non-private trong lớp ẩn danh dùng diamond, nó vẫn có thể bị từ chối.

Các phương thức override từ Object như toString(), equals(Object) và hashCode() vẫn là phương thức override hợp lệ. Phần thân lớp ẩn danh cũng có thể sử dụng các phương thức kế thừa mà không cần khai báo lại chúng.

## 5. Lỗi thường gặp

| Cách viết | Kết quả | Lý do |
|---|---|---|
| Diamond và phương thức override public | Hợp lệ | Phương thức thuộc supertype |
| Diamond và helper private | Hợp lệ | Phương thức bổ sung chỉ dùng nội bộ |
| Diamond và phương thức mới public | Lỗi biên dịch | Phương thức non-private không override |
| Diamond và phương thức mới protected | Lỗi biên dịch | protected vẫn là non-private |
| Diamond và phương thức mới package-private | Lỗi biên dịch | Không phải private |
| Ghi rõ tham số kiểu và thêm phương thức public | Hợp lệ | Không sử dụng diamond |
| Dùng var nhưng vẫn giữ diamond và thêm phương thức public | Lỗi biên dịch | var không thay đổi quy tắc của diamond |

Một lỗi khác là khai báo helper private rồi cố gọi nó qua biến có kiểu interface hoặc lớp cha. Điều này không hợp lệ vì helper private không thuộc API của kiểu tham chiếu bên ngoài. Hãy gọi helper từ chính phương thức override trong lớp ẩn danh, hoặc thiết kế một lớp có tên riêng nếu cần gọi từ bên ngoài.

## 6. Thực hành tốt

- Dùng diamond với lớp ẩn danh khi kiểu generic có thể suy luận rõ ràng từ kiểu đích hoặc đối số constructor.
- Chỉ khai báo phương thức non-private khi chúng thực sự override hoặc implement phương thức của supertype.
- Đặt helper bổ sung ở mức private và đặt tên mô tả đúng nhiệm vụ.
- Dùng @Override cho phương thức dự định override để nhận lỗi sớm khi chữ ký không khớp.
- Chọn kiểu tham chiếu phù hợp. Biến kiểu interface chỉ cung cấp API của interface, dù đối tượng thực tế là một lớp ẩn danh có phần thân riêng.
- Khi cần nhiều phương thức public bổ sung hoặc cần API ổn định, cân nhắc tạo lớp có tên riêng.
- Phân biệt phiên bản ngôn ngữ: diamond với lớp ẩn danh có từ Java 9; var cho biến cục bộ có từ Java 10. Không dùng var trong ví dụ yêu cầu biên dịch bằng Java 9.

## 7. Ghi nhớ

Với lớp ẩn danh dùng diamond, phương thức được khai báo phải override hoặc implement phương thức của supertype, trừ helper bổ sung được khai báo private. Nếu cần một phương thức public mới, hãy bỏ diamond bằng cách ghi rõ tham số kiểu hoặc dùng một lớp có tên riêng. Kiểu của biến tham chiếu vẫn quyết định những phương thức nào có thể được gọi từ bên ngoài.
