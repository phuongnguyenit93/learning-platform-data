# Đơn kế thừa lớp và đa kế thừa interface trong Java

Trong Java, **một lớp chỉ được kế thừa trực tiếp từ một lớp cha**, nhưng **có thể triển khai nhiều interface**. Bản thân một interface cũng có thể **kế thừa nhiều interface khác**. Cơ chế này cho phép dùng lại trạng thái và hành vi theo một hệ phân cấp lớp rõ ràng, đồng thời cho phép một đối tượng thực hiện nhiều hợp đồng hành vi.

Bài học tập trung vào quan hệ giữa kiểu lớp và kiểu interface, cú pháp Java 17+, cách JVM/Java chọn phương thức khi có nhiều nguồn kế thừa hành vi, và cách thiết kế tránh xung đột.

## 1. Ba quy tắc cốt lõi

| Quan hệ | Cú pháp | Số lượng trực tiếp | Ý nghĩa |
| --- | --- | --- | --- |
| Lớp kế thừa lớp | class Child extends Parent | Tối đa **một** lớp cha | Nhận trạng thái và hành vi có thể kế thừa từ lớp cha. |
| Lớp triển khai interface | class Child implements A, B | **Nhiều** interface | Cam kết cung cấp các hành vi theo hợp đồng của các interface; có thể nhận default method. |
| Interface kế thừa interface | interface C extends A, B | **Nhiều** interface | Kết hợp hoặc mở rộng các hợp đồng, có thể nhận default method. |

Ví dụ cú pháp:

~~~java
class Animal {
    void sleep() {}
}

interface Swimmable {
    void swim();
}

interface Trackable {
    String trackingId();
}

class Dolphin extends Animal implements Swimmable, Trackable {
    @Override
    public void swim() {}

    @Override
    public String trackingId() {
        return "D-01";
    }
}

interface Monitored extends Swimmable, Trackable {
    void report();
}
~~~

Đây là **đoạn minh họa khai báo**, không phải chương trình có hàm main. Một lớp ghi extends trước implements; implements liệt kê các interface ngăn bằng dấu phẩy. Một interface dùng extends, không dùng implements. Một lớp không khai báo extends thì mặc nhiên kế thừa trực tiếp từ Object (trừ chính Object).

Cần phân biệt **kế thừa lớp** với **đa hình kiểu**: Dolphin chỉ có một lớp cha trực tiếp là Animal, nhưng một thể hiện Dolphin có thể được tham chiếu bằng kiểu Dolphin, Animal, Swimmable, Trackable hoặc Object.

## 2. Vì sao Java chỉ cho lớp đơn kế thừa?

Lớp có thể mang **trạng thái của đối tượng** (instance fields), constructor, các phương thức cụ thể, phương thức abstract và quy tắc khởi tạo. Nếu cho phép một lớp kế thừa trực tiếp nhiều lớp, hệ thống phải giải quyết nhiều vấn đề như đường khởi tạo lớp cha, xung đột trường và phiên bản phương thức cùng tên. Java chọn một chuỗi lớp cha duy nhất để duy trì mô hình đơn giản và xác định.

~~~java
class Vehicle {}
class Machine {}

// Không hợp lệ trong Java:
// class Robot extends Vehicle, Machine {}
~~~

Một lớp con có thể nối dài chuỗi kế thừa (Car extends Vehicle, ElectricCar extends Car), nhưng tại **mỗi cấp**, lớp đó vẫn chỉ khai báo tối đa một lớp cha trực tiếp. Không thể dùng dấu phẩy sau extends để kế thừa nhiều lớp.

Các điều kiện quan trọng:

- Lớp final không cho phép lớp khác extends nó.
- Constructor không được kế thừa; constructor lớp con gọi constructor lớp cha bằng super(...) hoặc lời gọi mặc định tương ứng.
- Thành viên private của lớp cha không truy cập trực tiếp được từ lớp con; mức truy cập và khả năng override vẫn tuân theo quy tắc Java.
- Một lớp abstract cũng chỉ có thể extends một lớp khác. Lớp cụ thể cuối cùng phải triển khai tất cả abstract method mà nó còn chịu trách nhiệm; lớp abstract có thể để lại chúng chưa triển khai.

**Đơn kế thừa không có nghĩa chỉ được dùng một loại hành vi.** Hành vi bổ sung nên được mô tả bằng interface hoặc được ghép từ các đối tượng cộng tác (composition).

## 3. Đa kế thừa interface hoạt động thế nào?

Interface chủ yếu mô tả **một hợp đồng kiểu và hành vi**. Một lớp implements nhiều interface cùng lúc và phải đáp ứng các abstract method của chúng (trực tiếp hoặc qua phương thức public được kế thừa từ lớp cha), trừ khi chính lớp đó là abstract.

~~~java
interface Readable {
    String read();
}

interface Writable {
    void write(String value);
}

interface ReadWritable extends Readable, Writable {
    void clear();
}
~~~

ReadWritable mở rộng cả Readable và Writable. Bất cứ lớp cụ thể nào implements ReadWritable đều phải có đủ read(), write(String), clear(). Nó cũng được xem là một Readable và Writable. Có thể hình dung:

~~~text
Readable       Writable
      \         /
       ReadWritable
             ^
             | implements
         MemoryStore
~~~

Khác với lớp, interface **không chứa trạng thái instance** và **không có constructor**. Các trường khai báo trong interface mặc nhiên là public static final, nên thường dùng cho hằng số, không dùng để lưu trạng thái riêng của từng đối tượng.

Từ Java 8, interface có default method (phương thức có thân được thừa hưởng như hành vi mặc định) và static method. Từ Java 9, interface còn có private method làm trợ giúp nội bộ cho các phương thức trong interface. Các khả năng đó **không biến interface thành lớp có trạng thái instance hoặc đa kế thừa lớp**.

## 4. Ví dụ đầy đủ: Một lớp cha, nhiều interface, đa hình

Tạo tệp Main.java:

~~~java
public class Main {
    interface Identifiable {
        String id();
    }

    interface Named {
        default String label() {
            return "item-" + name();
        }

        String name();
    }

    interface Auditable {
        default String auditType() {
            return "tracked";
        }
    }

    static abstract class Entity {
        private final String id;

        protected Entity(String id) {
            this.id = id;
        }

        public String id() {
            return id;
        }
    }

    static final class Product extends Entity
            implements Identifiable, Named, Auditable {
        private final String name;

        Product(String id, String name) {
            super(id);
            this.name = name;
        }

        @Override
        public String name() {
            return name;
        }
    }

    public static void main(String[] args) {
        Product product = new Product("P-07", "book");

        Identifiable byId = product;
        Named byName = product;
        Auditable byAudit = product;
        Entity byBase = product;

        System.out.println(byId.id());
        System.out.println(byName.label());
        System.out.println(byAudit.auditType());
        System.out.println(byBase.id());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac Main.java
java Main
~~~

Kết quả chính xác:

~~~text
P-07
item-book
tracked
P-07
~~~

Giải thích:

1. Product chỉ extends **một** lớp cha là Entity, và nhận được trường id cùng phương thức id() thông qua cơ chế kế thừa lớp; trường private id chỉ được dùng trực tiếp bên trong Entity.
2. Product đồng thời implements **ba** interface Identifiable, Named, Auditable.
3. Phương thức public id() có sẵn trong Entity thỏa hợp đồng Identifiable.id(), vì chữ ký và mức truy cập phù hợp; Product không cần viết lại nó.
4. Product tự triển khai Named.name(). Default method Named.label() gọi name() trên đối tượng thực tế, nên trả về item-book.
5. Auditable.auditType() được kế thừa như default method. Các biến byId, byName, byAudit chỉ cho phép gọi phương thức hiển thị bởi kiểu tham chiếu tương ứng, dù cùng trỏ đến một Product.
6. Entity là abstract nhưng vẫn có constructor và phương thức cụ thể. Product là lớp cụ thể có thể khởi tạo và đáp ứng toàn bộ hợp đồng.

**Không cần ép kiểu để gán** Product cho từng interface mà nó implements. Ngược lại, từ biến kiểu interface muốn dùng thành viên chỉ thuộc Product thì phải kiểm tra/ép kiểu phù hợp, chẳng hạn bằng instanceof, và tránh giả định mọi đối tượng cùng interface đều là Product.

## 5. Điều gì xảy ra khi nhiều interface có phương thức trùng nhau?

Trước hết cần phân biệt ba trường hợp.

### 5.1. Cùng abstract method: thường chỉ cần một implementation

~~~java
interface Printable {
    void render();
}

interface Previewable {
    void render();
}

class Report implements Printable, Previewable {
    @Override
    public void render() {
        System.out.println("report");
    }
}
~~~

Một phương thức public void render() trong Report đáp ứng đồng thời hai hợp đồng vì chữ ký tương thích. Điều này khác hoàn toàn với hai default method có phần thân cạnh tranh nhau.

Lưu ý về **kiểu trả về**: các khai báo cùng chữ ký chỉ có thể kết hợp nếu kiểu trả về tương thích theo quy tắc return-type-substitutability của Java (ví dụ một kiểu trả về hiệp biến có thể thỏa nhiều hợp đồng). Hai hợp đồng yêu cầu kiểu trả về không tương thích thì một lớp không thể triển khai hợp lệ cả hai chỉ bằng cách đổi tên biến hoặc thêm @Override.

### 5.2. Hai default method xung đột: lớp phải chọn rõ

Tạo tệp Main.java độc lập cho ví dụ này:

~~~java
public class Main {
    interface Left {
        default String source() {
            return "left";
        }
    }

    interface Right {
        default String source() {
            return "right";
        }
    }

    static class Combined implements Left, Right {
        @Override
        public String source() {
            return Left.super.source() + "+" + Right.super.source();
        }
    }

    public static void main(String[] args) {
        System.out.println(new Combined().source());
    }
}
~~~

Chạy:

~~~bash
javac Main.java
java Main
~~~

Kết quả:

~~~text
left+right
~~~

Nếu bỏ Combined.source(), trình biên dịch báo xung đột vì Left và Right cùng cung cấp default source() có chữ ký trùng nhau. Combined **bắt buộc override** và tự định nghĩa quy tắc. Cú pháp Left.super.source() hay Right.super.source() gọi trực tiếp default method từ superinterface tương ứng; không thể tùy tiện dùng tên của một interface không nằm trong quan hệ superinterface hợp lệ.

Lớp cũng có thể chọn một cách đơn giản hơn:

~~~java
@Override
public String source() {
    return "combined";
}
~~~

Đoạn trên chỉ là phần thân override thay thế đặt bên trong Combined, không phải chương trình Java độc lập.

### 5.3. Phương thức cụ thể từ lớp cha được ưu tiên

Tạo tệp Main.java độc lập:

~~~java
public class Main {
    static class Parent {
        public String message() {
            return "class";
        }
    }

    interface Message {
        default String message() {
            return "interface";
        }
    }

    static class Child extends Parent implements Message {}

    public static void main(String[] args) {
        System.out.println(new Child().message());
    }
}
~~~

Chạy lệnh javac Main.java và java Main cho stdout:

~~~text
class
~~~

Nguyên tắc thường gọi là **class wins**: phương thức instance cụ thể phù hợp được kế thừa từ lớp cha có ưu tiên hơn default method cùng chữ ký từ interface. Phương thức trong lớp vẫn phải có kiểu trả về, mức truy cập và các điều kiện override tương thích với hợp đồng interface.

Không được áp dụng nguyên tắc này máy móc với **phương thức abstract** của superclass: nếu lớp cha khai báo abstract method cùng chữ ký, lớp con cụ thể vẫn phải cung cấp implementation phù hợp; không thể mặc định trông chờ default method của interface tự thay thế yêu cầu đó.

### 5.4. Một default method chung qua nhiều đường không nhất thiết xung đột

~~~java
interface Root {
    default String code() {
        return "root";
    }
}

interface A extends Root {}
interface B extends Root {}

class Both implements A, B {}
~~~

Both nhận cùng một default Root.code() qua hai nhánh và không cần override; đây không phải hai implementation độc lập cạnh tranh. Khi một subinterface định nghĩa lại phương thức, khai báo **cụ thể hơn** trong hệ kế thừa interface thường được chọn theo quy tắc của Java. Vì thế cần xem **nguồn gốc và độ đặc hiệu của phương thức**, không chỉ đếm số interface.

## 6. Các quy tắc cú pháp và quyền truy cập thường gây nhầm lẫn

| Tình huống | Hợp lệ? | Giải thích |
| --- | --- | --- |
| class C extends A implements X, Y | Có | Một lớp cha, nhiều interface; đúng thứ tự từ khóa. |
| class C implements X, Y | Có | Lớp cha trực tiếp mặc định là Object. |
| interface Z extends X, Y | Có | Interface được đa kế thừa interface. |
| class C extends A, B | Không | Java không hỗ trợ đa kế thừa lớp trực tiếp. |
| interface Z implements X | Không | Interface dùng extends để mở rộng interface. |
| class C implements X extends A | Không | Sai cú pháp; phải dùng extends A implements X. |
| class C implements X nhưng thiếu abstract method | Không nếu C là lớp cụ thể | Phải hiện thực đầy đủ hoặc khai báo C là abstract. |
| Một lớp implements cùng generic interface với hai đối số kiểu khác nhau | Không | Xung đột các kiểu được kế thừa do cùng một generic interface và erasure. |

**Mức truy cập:** phương thức abstract khai báo trong interface mặc nhiên là public. Khi lớp triển khai, viết public; không được giảm quyền truy cập thành package-private, protected hay private. Ví dụ dưới đây không hợp lệ:

~~~java
interface Task {
    void execute();
}

class Job implements Task {
    // Sai: phương thức này không public.
    // void execute() {}
}
~~~

Job ở đây cũng thiếu implementation thực sự, nên không biên dịch. Sửa bằng public void execute() { ... } bên trong Job hoặc chuyển Job thành abstract nếu muốn trì hoãn việc triển khai.

**Static method trong interface:** gọi bằng tên interface; phương thức static không được thừa hưởng như instance method của lớp triển khai.

~~~java
interface Numbers {
    static int twice(int n) {
        return n * 2;
    }
}

// Gọi: Numbers.twice(5)
~~~

**Trường trong interface:** là hằng public static final, không đại diện cho trạng thái instance; không thể khai báo một trường instance mutable trong interface. Nếu nhiều interface định nghĩa hằng cùng tên, nên truy cập bằng tên interface để tránh nhập nhằng.

**Thứ tự và quy tắc chữ ký:** khai báo implements theo thứ tự X, Y hay Y, X không phải cơ chế ưu tiên default method. Java dựa vào quy tắc phương thức được kế thừa, độ đặc hiệu của interface, và override tường minh. Các phương thức cùng tên nhưng khác danh sách tham số là overload và không tự động tạo xung đột do trùng tên.

## 7. Khi nào dùng abstract class, interface hoặc composition?

Dùng **abstract class** khi nhiều lớp con thật sự thuộc cùng một họ, cần chia sẻ **trạng thái**, constructor, logic protected hoặc bất biến vòng đời. Vì chỉ được chọn một lớp cha, hãy chọn quan hệ “là một” có ý nghĩa bền vững, không extends chỉ để lấy một phương thức tiện ích.

Dùng **interface** để mô tả **khả năng hoặc vai trò độc lập**: Comparable, AutoCloseable, Runnable và các hợp đồng riêng như Printable, Retryable. Một đối tượng có thể đáp ứng nhiều vai trò mà không phải nằm trong nhiều cây lớp. Giữ abstract contract nhỏ, rõ trách nhiệm; default method nên có hành vi mặc định an toàn, nhất quán và không dựa vào trạng thái instance ẩn.

Dùng **composition** khi muốn tái sử dụng implementation nhưng quan hệ “là một” không đúng hoặc hành vi cần thay đổi linh hoạt. Ví dụ class ReportService có trường private final Formatter formatter và ủy quyền việc định dạng cho formatter, thay vì extends Formatter chỉ để lấy mã nguồn xử lý. Composition cũng tránh bị khóa vào một lớp cha không thích hợp.

Một lựa chọn thiết kế thường gặp:

~~~text
Abstract class: chia sẻ trạng thái/khởi tạo của một họ đối tượng
Interface:      công khai nhiều hợp đồng/khả năng của cùng đối tượng
Composition:    ghép các đối tượng để tái sử dụng hoặc thay thế hành vi
~~~

Có thể kết hợp cả ba: một lớp extends BaseEntity, implements Identifiable, Auditable và chứa một Validator được truyền qua constructor.

## 8. Lỗi thường gặp và cách kiểm tra

1. **Viết nhiều lớp sau extends:** compiler từ chối. Chọn một lớp cha và thay các vai trò còn lại bằng interface hoặc composition.
2. **Quên public khi implements:** phương thức của interface là public; tăng mức truy cập của implementation cho đúng.
3. **Cho rằng implements tự tạo hành vi:** abstract method không có thân; lớp cụ thể phải triển khai. Chỉ default method mới có sẵn implementation.
4. **Dựa vào thứ tự implements để xử lý default conflict:** thứ tự không giải quyết xung đột. Override và quyết định minh bạch.
5. **Nhầm interface với lớp có state:** interface field là static final; dùng lớp hoặc đối tượng cộng tác cho dữ liệu của từng instance.
6. **Gọi interface static method trên instance:** gọi theo tên interface, chẳng hạn Numbers.twice(5).
7. **Nhầm kiểu tham chiếu với kiểu thực tế:** biến kiểu interface chỉ có API của interface tại thời điểm biên dịch; lời gọi instance hợp lệ vẫn dispatch đến implementation trên đối tượng thực tế.
8. **Kế thừa lớp chỉ để dùng lại vài hàm:** làm hệ phân cấp thiếu ý nghĩa, khó thay đổi về sau; cân nhắc composition.

Khi gặp lỗi biên dịch liên quan đến kế thừa, kiểm tra lần lượt: (a) cú pháp extends/implements; (b) quan hệ subtype thực tế; (c) tất cả abstract method có implementation public phù hợp; (d) phương thức cùng chữ ký có kiểu trả về/throws và mức truy cập tương thích; (e) có hai default method không thể tự phân giải hay không.

## 9. Tự kiểm tra kiến thức

**Câu 1.** Lớp ElectricCar extends Car implements Chargeable, Trackable có bao nhiêu lớp cha trực tiếp? Có bao nhiêu interface được khai báo triển khai trực tiếp?

**Đáp án:** Một lớp cha trực tiếp là Car và hai interface khai báo trực tiếp là Chargeable, Trackable. Đối tượng có thể còn thuộc các superclass và superinterface gián tiếp khác.

**Câu 2.** Hai interface có abstract void save() giống nhau. Lớp implements cả hai cần bao nhiêu phương thức save() nếu chữ ký tương thích?

**Đáp án:** Một implementation public void save() là đủ.

**Câu 3.** Hai interface không liên quan đều có default String status() khác nhau. Lớp cụ thể implements cả hai mà không override có hợp lệ không?

**Đáp án:** Không. Lớp phải override status() để giải quyết xung đột. Có thể tự triển khai hoặc gọi InterfaceName.super.status() phù hợp.

**Câu 4.** Một lớp cha có public String status(), interface có default String status(), lớp con extends lớp cha và implements interface. Phương thức nào được gọi?

**Đáp án:** Phương thức instance cụ thể được kế thừa từ lớp cha, miễn các khai báo tương thích.

## 10. Ghi nhớ

- **Lớp đơn kế thừa:** mỗi class chỉ extends tối đa một class trực tiếp; abstract class cũng vậy.
- **Đa interface:** một class có thể implements nhiều interface; một interface có thể extends nhiều interface.
- **Đa hình:** cùng đối tượng có thể được dùng qua nhiều kiểu interface mà nó đáp ứng.
- **Khi trùng phương thức:** abstract contract tương thích có thể dùng chung implementation; hai default implementation không phân giải được phải override; phương thức cụ thể phù hợp từ lớp cha có ưu tiên.
- **Thiết kế:** chọn abstract class cho họ có state chung, interface cho các vai trò, composition khi cần ghép và thay thế hành vi.

Nắm được ranh giới giữa **kế thừa lớp**, **kế thừa hợp đồng interface** và **ủy quyền hành vi** sẽ giúp thiết kế API Java dễ hiểu, dễ mở rộng và ít gặp lỗi xung đột phương thức.