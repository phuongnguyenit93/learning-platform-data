# Xung đột nhiều default method trong Java Interface

## Mục tiêu học tập

Một lớp Java có thể **implements nhiều interface**. Từ Java 8, interface còn có thể khai báo **default method**: phương thức có phần triển khai sẵn và được lớp thực thi kế thừa trong những điều kiện nhất định. Vì thế nảy sinh câu hỏi quan trọng: **nếu hai interface đều cung cấp một default method cùng chữ ký, Java chọn phương thức nào?**

Bài này tập trung giải thích chính xác cơ chế xử lý xung đột default method, cách ưu tiên phương thức ở lớp và interface chuyên biệt hơn, cách ghi đè để giải quyết tình huống mơ hồ, và cú pháp **InterfaceName.super.method()** để gọi một triển khai mặc định cụ thể. Bạn cũng sẽ phân biệt xung đột thật với việc kế thừa cùng một phương thức qua nhiều nhánh, nhận diện trường hợp default method va chạm với phương thức abstract, và hiểu những ràng buộc quan trọng khi thiết kế API.

Các quy tắc này vẫn có hiệu lực trong Java hiện đại. Ví dụ hoàn chỉnh sử dụng cú pháp Java 8 và chạy được trên JDK 8, 17, 21 và các phiên bản tương thích mới hơn.

## 1. Default method là gì và vì sao có thể gây xung đột?

Trước hết, xem interface chứa phương thức có phần thân:

~~~java
interface Named {
    default String name() {
        return "Mặc định";
    }
}
~~~

Đây là **đoạn khai báo kiểu minh họa**. Trong Java 8+, một phương thức instance trong interface được đánh dấu **default** có phần thân và có thể được lớp thực thi sử dụng nếu không có phương thức ưu tiên cao hơn hoặc xung đột bắt buộc phải xử lý.

Một lớp chỉ implements Named có thể gọi phương thức đó:

~~~java
class Service implements Named {
}

Service service = new Service();
System.out.println(service.name()); // Mặc định
~~~

Hai đoạn trên minh họa ý tưởng, cần được đặt đúng phạm vi của một tệp Java hợp lệ; chưa phải chương trình độc lập. Service không phải tự viết lại name() vì đã có default method.

Giờ xét hai interface độc lập:

~~~java
interface Left {
    default String name() {
        return "Left";
    }
}

interface Right {
    default String name() {
        return "Right";
    }
}
~~~

Nếu một lớp **implements Left, Right**, cả hai cùng đưa ra phương thức **name()** không tham số, trả **String**. Không có quan hệ kế thừa nào khiến một interface hiển nhiên cụ thể hơn interface còn lại. Java **không tự chọn ngẫu nhiên**, cũng không ưu tiên theo thứ tự viết trong danh sách implements. Lớp phải giải quyết xung đột một cách tường minh.

Mục tiêu của thiết kế này là tránh cho người đọc phải đoán cách thực thi khi có hai triển khai hợp lệ nhưng mang ý nghĩa khác nhau.

## 2. Trường hợp xung đột trực tiếp: hai default method cùng chữ ký

Ví dụ dưới đây **cố ý không biên dịch**, vì một lớp nhận hai bản triển khai default ngang hàng mà không ghi đè:

~~~java
interface Left {
    default String label() {
        return "L";
    }
}

interface Right {
    default String label() {
        return "R";
    }
}

// Không hợp lệ nếu bỏ qua việc giải quyết xung đột:
// class Bad implements Left, Right { }
~~~

Các interface trong đoạn này có thể khai báo hợp lệ; dòng Bad được đặt trong comment để không vô tình tạo mã không chạy. Điểm lỗi nằm ở việc **Bad** không chỉ định một triển khai thống nhất cho **label()**.

**Cách sửa phổ biến:** ghi đè phương thức trong lớp thực thi.

~~~java
class Good implements Left, Right {
    @Override
    public String label() {
        return "Good";
    }
}
~~~

Bây giờ Good cung cấp **một định nghĩa rõ ràng**, nên không còn mơ hồ. Từ khóa **@Override** giúp trình biên dịch kiểm tra bạn thực sự ghi đè một phương thức phù hợp. Nó không bắt buộc về mặt cú pháp, nhưng nên dùng để phát hiện lỗi đánh máy trong tên hoặc chữ ký.

**Lưu ý về mức truy cập:** phương thức của interface là public theo hợp đồng tương ứng, vì vậy phương thức ghi đè phải là **public**; không thể dùng private hoặc protected làm giảm quyền truy cập.

Không nhất thiết lớp phải chọn nguyên xi một default. Nó có thể đưa ra hành vi mới, hoặc gọi một hay nhiều default cụ thể bằng cú pháp đặc biệt được trình bày ở phần tiếp theo.

## 3. Gọi chính xác default method cần dùng: InterfaceName.super.method()

Trong một lớp implements nhiều interface, sau khi ghi đè, đôi khi ta vẫn muốn tận dụng logic có sẵn của một interface:

~~~java
class Good implements Left, Right {
    @Override
    public String label() {
        return Left.super.label() + "+" + Right.super.label();
    }
}
~~~

**Left.super.label()** gọi phần triển khai default của Left theo quy tắc gọi **qualified super** của Java. **Right.super.label()** gọi phần triển khai của Right. Điều này khác với **super.label()** không kèm tên interface, vốn dùng trong ngữ cảnh lớp cha.

Không được dùng cú pháp **Left.label()** cho một default instance method như thể đó là static method. Cũng không nên viết **new Left()** vì interface không thể được khởi tạo trực tiếp.

Cú pháp **InterfaceName.super.method()** chỉ hợp lệ ở ngữ cảnh và quan hệ kế thừa phù hợp, đặc biệt khi tên interface chỉ ra một **direct superinterface** hợp lệ của kiểu chứa lời gọi và phương thức default có thể truy cập ở nhánh đó. Một interface bị một nhánh con kế thừa và ghi đè có thể khiến việc gọi lại qua tên nhánh cha không được phép. Khi có nhiều lớp/interface lồng nhau, không nên suy luận rằng có thể gọi tùy ý mọi default ancestor chỉ bằng cách viết tên bất kỳ trước **.super**.

### Ví dụ Java chạy được: hai interface độc lập

Tạo tệp **DefaultMethodConflictDemo.java**:

~~~java
public class DefaultMethodConflictDemo {

    interface Left {
        default String label() {
            return "Left";
        }
    }

    interface Right {
        default String label() {
            return "Right";
        }
    }

    static final class Combined implements Left, Right {
        @Override
        public String label() {
            return Left.super.label() + " + " + Right.super.label();
        }
    }

    public static void main(String[] args) {
        Combined combined = new Combined();
        System.out.println(combined.label());
        System.out.println(((Left) combined).label());
        System.out.println(((Right) combined).label());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 DefaultMethodConflictDemo.java
java DefaultMethodConflictDemo
~~~

Kết quả:

~~~text
Left + Right
Left + Right
Left + Right
~~~

**Vì sao cả ba dòng giống nhau?** Biểu thức **((Left) combined).label()** chỉ thay đổi **kiểu tham chiếu** dùng để gọi phương thức, không thay đổi đối tượng thực tế và không yêu cầu Java bỏ qua override của Combined. Lời gọi instance vẫn được dispatch tới phương thức **label()** của Combined.

Muốn gọi một bản default cụ thể, phải sử dụng **Left.super.label()** hoặc **Right.super.label()** **từ bên trong triển khai hợp lệ** như thân override của Combined. Ép kiểu sang interface không phải cách chọn bản default.

**Thứ tự** của các tên trong câu **implements Left, Right** không quyết định ưu tiên. Nếu đổi thành **implements Right, Left**, Java vẫn cần override giống hệt.

## 4. Quy tắc ưu tiên thực tế: lớp trước interface

Khi có một phương thức instance cụ thể từ **lớp cha** khớp chữ ký với default method từ interface, phương thức của lớp **được ưu tiên**.

~~~java
interface Greeting {
    default String message() {
        return "Interface";
    }
}

class Base {
    public String message() {
        return "Class";
    }
}

class Child extends Base implements Greeting {
}
~~~

Đây là đoạn khai báo minh họa. Lời gọi **new Child().message()** sử dụng phần triển khai từ **Base**, nên trả **"Class"**.

Quy tắc thường được tóm tắt là **“class wins”**: phương thức kế thừa từ hệ phân cấp lớp được ưu tiên hơn default method trong interface khi phù hợp.

Điểm tinh tế: nếu **một lớp cha có phương thức abstract tương ứng**, lớp con chưa cung cấp phần triển khai cụ thể không thể chỉ dựa vào default method từ interface như một cách tự động đáp ứng lời hứa của phương thức abstract. Trường hợp đó có thể đòi hỏi lớp con triển khai lại một cách tường minh. Vì vậy quy tắc “class wins” không nên bị hiểu sai là “abstract method có sẵn phần thân để chạy”.

Không áp dụng quy tắc này cho một **static method** cùng tên: static method không phải một default instance method; cần kiểm tra riêng quy tắc static hiding và chữ ký trước khi kết luận.

### Chương trình kiểm chứng class wins

Tạo tệp **ClassAndInterfacePriorityDemo.java**:

~~~java
public class ClassAndInterfacePriorityDemo {

    interface Greeting {
        default String message() {
            return "Interface";
        }
    }

    static class Base {
        public String message() {
            return "Class";
        }
    }

    static final class Child extends Base implements Greeting {
    }

    public static void main(String[] args) {
        Child child = new Child();

        System.out.println("Trực tiếp: " + child.message());
        Greeting asInterface = child;
        System.out.println("Qua interface: " + asInterface.message());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ClassAndInterfacePriorityDemo.java
java ClassAndInterfacePriorityDemo
~~~

Kết quả:

~~~text
Trực tiếp: Class
Qua interface: Class
~~~

Không có xung đột cần giải quyết vì phương thức concrete **Base.message()** chiếm ưu tiên. Việc đổi kiểu biến sang Greeting không thay đổi dispatch ở runtime.

## 5. Interface con cụ thể hơn được ưu tiên

Bây giờ xem hai interface **có quan hệ kế thừa**:

~~~java
interface Parent {
    default String category() {
        return "Parent";
    }
}

interface Child extends Parent {
    @Override
    default String category() {
        return "Child";
    }
}
~~~

Nếu một lớp implements Child, nó nhận phiên bản default **Child.category()**, vì Child đã ghi đè Parent. Ngay cả khi lớp liệt kê thêm Parent như một superinterface trong implements, default chuyên biệt hơn ở Child vẫn có ưu tiên theo quan hệ kế thừa.

Nguyên tắc này thường được diễn đạt là **“most specific interface wins”**. Nó không dựa trên thứ tự tên trong implements, mà dựa trên quan hệ **extends** của các interface và những định nghĩa còn có hiệu lực.

Ví dụ:

~~~java
class Choice implements Parent, Child {
}

System.out.println(new Choice().category()); // Child
~~~

Đây là đoạn minh họa, cần khai báo Parent/Child và đặt lời gọi trong phương thức Java. Java chấp nhận việc Child là interface con có default ghi đè Parent; không cần override tại Choice chỉ để chọn một trong hai bản. 

**Quan trọng:** đừng suy rộng thành “interface nào xuất hiện sau sẽ thắng”. Chỉ có quan hệ thừa kế chuyên biệt thực sự mới làm thay đổi lựa chọn.

## 6. Hình thoi không nhất thiết có xung đột

Trường hợp **diamond inheritance** có thể được tạo bằng hai nhánh interface cùng kế thừa từ một gốc:

~~~text
           Origin
          /      \
      BranchA   BranchB
          \      /
           Result
~~~

Nếu **Origin** định nghĩa default method, còn **BranchA** và **BranchB** đều kế thừa nguyên phiên bản đó mà **không tự ghi đè**, Result không đứng trước hai bản triển khai độc lập. Nó chỉ có **một default method gốc**, được nhìn thấy qua hai đường thừa kế.

Ví dụ:

~~~java
interface Origin {
    default String id() {
        return "Origin";
    }
}

interface BranchA extends Origin {
}

interface BranchB extends Origin {
}

class Result implements BranchA, BranchB {
}
~~~

Đây là đoạn minh họa. Lời gọi **new Result().id()** trả **"Origin"** và không cần override để giải quyết xung đột.

Nếu BranchA và BranchB **mỗi nhánh tự ghi đè id() bằng một default khác nhau**, Result lại đối mặt hai default ngang hàng và phải giải quyết rõ ràng.

Nói cách khác: có **hai đường thừa kế** không đồng nghĩa có **hai triển khai default độc lập**. Cần xem nguồn gốc cuối cùng và những override trên từng nhánh.

## 7. Một ví dụ hoàn chỉnh cho interface chuyên biệt và hình thoi

Tạo tệp **SpecificityAndDiamondDemo.java**:

~~~java
public class SpecificityAndDiamondDemo {

    interface Parent {
        default String name() {
            return "Parent";
        }
    }

    interface Child extends Parent {
        @Override
        default String name() {
            return "Child";
        }
    }

    static final class Specific implements Parent, Child {
    }

    interface Origin {
        default String tag() {
            return "Origin";
        }
    }

    interface BranchA extends Origin {
    }

    interface BranchB extends Origin {
    }

    static final class Diamond implements BranchA, BranchB {
    }

    public static void main(String[] args) {
        System.out.println("Interface cụ thể: " +
            new Specific().name());
        System.out.println("Hình thoi chung gốc: " +
            new Diamond().tag());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 SpecificityAndDiamondDemo.java
java SpecificityAndDiamondDemo
~~~

Kết quả:

~~~text
Interface cụ thể: Child
Hình thoi chung gốc: Origin
~~~

Hai dòng minh họa hai quy tắc **khác nhau**:

1. **Specific** nhận Child.name() vì Child override default từ Parent và cụ thể hơn.
2. **Diamond** chỉ kế thừa một triển khai Origin.tag() qua hai nhánh, nên không có xung đột thật.

Đây là các quy tắc xác định ở thời điểm biên dịch, không dựa trên việc JVM đoán một nhánh khi chương trình đang chạy.

## 8. Interface con kế thừa hai default độc lập cũng phải xử lý

Xung đột không chỉ xảy ra trong lớp **implements A, B**. Một **interface** có thể extends hai interface độc lập cùng định nghĩa default method:

~~~java
interface A {
    default String source() {
        return "A";
    }
}

interface B {
    default String source() {
        return "B";
    }
}

// Không hợp lệ nếu không xử lý:
// interface C extends A, B { }
~~~

Ở đây C cũng cần có một quyết định rõ ràng. Một cách là **định nghĩa lại default method ngay tại C**:

~~~java
interface C extends A, B {
    @Override
    default String source() {
        return A.super.source() + "/" + B.super.source();
    }
}
~~~

Đây là các đoạn khai báo minh họa cần đặt trong ngữ cảnh file phù hợp. Khi C định nghĩa default mới, lớp implements C thông thường có thể dùng phương thức đã được giải quyết mà không phải tự ghi đè nữa.

Một cách khác là **khai báo lại phương thức dưới dạng abstract trong C**:

~~~java
interface C extends A, B {
    @Override
    String source();
}
~~~

Đây là **phương án thay thế**, không thể đặt đồng thời với ví dụ C có default ở trên trong cùng một phạm vi tên. Cách khai báo abstract nói rằng **C không tự chọn triển khai**, và những lớp concrete implements C phải cung cấp phương thức phù hợp. Cách này có ích nếu mỗi lớp thực thi cần một chính sách riêng.

### Default và abstract method không có cùng ý nghĩa

Khi một interface con khai báo lại phương thức là abstract, nó có thể **loại bỏ default được kế thừa** khỏi hợp đồng dành cho các lớp thực thi theo nhánh đó. Vì thế không nên nghĩ rằng cứ tồn tại default ở một ancestor là lớp con chắc chắn có thể dùng mà không cần code.

Việc một interface khác chỉ khai báo abstract method cùng chữ ký cũng phải được xem xét trong toàn bộ tập giao diện kế thừa. Không thể giả định abstract + default luôn tự hòa giải như hai phương thức abstract trùng chữ ký.

## 9. Ví dụ hoàn chỉnh: giải quyết xung đột tại interface con

Tạo tệp **InterfaceCompositionDemo.java**:

~~~java
public class InterfaceCompositionDemo {

    interface AuditA {
        default String audit() {
            return "AuditA";
        }
    }

    interface AuditB {
        default String audit() {
            return "AuditB";
        }
    }

    interface Auditable extends AuditA, AuditB {
        @Override
        default String audit() {
            return AuditA.super.audit() + " | " +
                AuditB.super.audit();
        }
    }

    static final class Job implements Auditable {
    }

    public static void main(String[] args) {
        Auditable job = new Job();
        System.out.println(job.audit());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 InterfaceCompositionDemo.java
java InterfaceCompositionDemo
~~~

Kết quả:

~~~text
AuditA | AuditB
~~~

Ở đây **Auditable** là nơi thể hiện chính sách ghép kết quả. **Job** chỉ implements Auditable và không tự viết audit(), vì interface Auditable đã cung cấp một default rõ ràng.

Nếu hai hành vi không thể hoặc không nên gộp, cách thiết kế phù hợp có thể là khai báo audit() abstract ở Auditable, buộc mỗi lớp đưa ra lựa chọn, hoặc thay đổi thiết kế phân tách hai vai trò để không dùng chung một tên phương thức cho hai ý nghĩa khác nhau.

## 10. Khi chỉ có tên giống nhau nhưng chữ ký khác nhau

Hai phương thức cùng tên không nhất thiết xung đột. Ví dụ:

~~~java
interface TextFormatter {
    default String format(String text) {
        return "[" + text + "]";
    }
}

interface NumberFormatter {
    default String format(int number) {
        return "#" + number;
    }
}
~~~

Các phương thức có **danh sách tham số khác nhau**. Một lớp implements cả hai có thể có hai overload format(String) và format(int). Với đối số String, Java dùng phương thức nhận String; với int, Java dùng phương thức nhận int.

Tuy nhiên, khi các overload có thể cùng phù hợp một lời gọi (ví dụ truyền null tới hai kiểu tham chiếu không liên quan), trình biên dịch vẫn có thể báo **ambiguous method invocation** tại nơi gọi. Đó là **mơ hồ khi chọn overload**, khác với **xung đột hai default cùng chữ ký khi khai báo lớp**.

### Kiểu trả về không đủ để phân biệt overload

Java **không cho overload chỉ khác kiểu trả về**. Nếu hai phương thức có cùng tên và cùng loại/thứ tự tham số nhưng trả hai kiểu không tương thích, việc yêu cầu một kiểu thực thi kế thừa cả hai có thể **không giải quyết được chỉ bằng cách override**, vì Java không thể khai báo một phương thức duy nhất đáp ứng cả hai kiểu kết quả không tương thích.

Ví dụ về mặt ý tưởng:

~~~java
interface Alpha {
    default String status() {
        return "A";
    }
}

interface Beta {
    default Integer status() {
        return 1;
    }
}

// Không hợp lệ: class Incompatible implements Alpha, Beta { }
~~~

Đây là đoạn cố ý minh họa **trường hợp không hợp lệ**; class bị comment lại. Alpha.status() và Beta.status() có cùng danh sách tham số rỗng nhưng kiểu trả về không có quan hệ đáp ứng override tương thích. Không thể sửa đơn giản bằng cách viết một phương thức status() có cả String và Integer làm kiểu trả về. Cần đổi thiết kế API, đổi tên, hoặc phân tách trách nhiệm.

**Ngoại lệ được khai báo throws** cũng không làm hai phương thức trở thành overload khác nhau. Khi override, cần tuân thủ các ràng buộc checked exception và kiểu trả về của phương thức được ghi đè.

## 11. Phương thức của Object và static method của interface

Không phải mọi phương thức trông giống “method của interface” đều là default method.

### Phương thức public của Object

Một interface **không thể cung cấp default implementation ghi đè các phương thức public của Object** như equals(Object), hashCode() hoặc toString(). Chẳng hạn:

~~~java
// Không hợp lệ:
// interface Illegal {
//     default String toString() {
//         return "X";
//     }
// }
~~~

Java xử lý các phương thức public tương ứng của Object theo quy tắc riêng, tránh để default method từ interface thay thế các hành vi nền tảng này. Khi cần tùy chỉnh toString(), hãy viết override ở lớp cụ thể.

### Static method trong interface

Interface có thể có static method:

~~~java
interface Tools {
    static String version() {
        return "v1";
    }
}
~~~

Static method **không phải default instance method và không được kế thừa như phương thức instance**. Lời gọi là **Tools.version()**, không phải một default instance method tự được trộn vào lớp implements Tools.

Ngay cả khi nhiều interface khai báo static method cùng tên, điều đó không tạo ra xung đột **default method** theo cơ chế đang học. Tránh nhầm hai khái niệm chỉ vì cùng được khai báo trong interface.

### Private interface methods trên Java hiện đại

Từ **Java 9**, interface có thể có phương thức private để tái sử dụng logic nội bộ giữa các default/static method. Đây vẫn là một tính năng dùng được trên JDK hiện đại, nhưng **không phải cú pháp của Java 8**. Private method trong interface không được lớp implements kế thừa như default public method và không tham gia loại xung đột này.

## 12. Tác động đến functional interface và lambda

Một functional interface cần đúng một **phương thức trừu tượng** phù hợp quy tắc SAM; nó vẫn có thể có default method:

~~~java
@FunctionalInterface
interface Formatter {
    String format(String text);

    default String decorate(String text) {
        return "**" + format(text) + "**";
    }
}
~~~

Khi sử dụng:

~~~java
Formatter formatter = text -> text.toUpperCase();
System.out.println(formatter.decorate("java")); // **JAVA**
~~~

Đây là đoạn minh họa cần đặt trong ngữ cảnh hợp lệ. **decorate** có phần triển khai nên không làm tăng số phương thức trừu tượng; Formatter vẫn nhận lambda. Đây là lý do default method giúp nhiều API bổ sung hành vi mới mà không buộc mọi lớp đang thực thi phải viết lại.

Tuy nhiên, nếu một interface kế thừa từ hai interface có **default trùng chữ ký**, nó vẫn phải xử lý xung đột theo quy tắc của ngôn ngữ; việc gắn annotation **@FunctionalInterface** không giúp tự chọn một bản default. Trình biên dịch có thể báo lỗi về xung đột hoặc về số SAM khi hợp đồng trừu tượng không còn phù hợp.

**Không nên lạm dụng default** chỉ để né việc viết triển khai ở lớp. Default method phù hợp khi có một **hành vi mặc định hợp lý cho mọi lớp thực thi**, không phụ thuộc tùy tiện vào trạng thái nội bộ chỉ có ở một kiểu triển khai cụ thể.

## 13. Khi nào nên override, khi nào nên thay thiết kế?

Hãy chọn chiến lược phù hợp với ý nghĩa nghiệp vụ:

| Tình huống | Cách xử lý nên cân nhắc | Lý do |
| --- | --- | --- |
| Hai default độc lập trùng chữ ký, nhưng một hành vi là đúng cho lớp | Override trong lớp, chọn logic mong muốn | Quyết định rõ ràng ngay nơi sử dụng |
| Hai default độc lập trùng chữ ký và có thể ghép hợp lý | Override và gọi A.super/B.super | Tận dụng phần triển khai có sẵn |
| Nhiều lớp dùng chung cách giải quyết | Đặt override default ở interface con chung | Gom chính sách, giảm lặp |
| Mỗi lớp cần quy tắc riêng | Khai báo abstract ở interface con hoặc yêu cầu lớp override | Không ép một quy tắc chung sai ngữ cảnh |
| Hai default có tên giống nhưng ý nghĩa hoàn toàn khác | Đổi thiết kế/tên phương thức hoặc dùng composition | Tránh hợp đồng khó hiểu lâu dài |
| Hai phương thức cùng chữ ký nhưng kiểu trả về không tương thích | Thiết kế lại API | Không thể giải quyết bằng một override hợp lệ |
| Default từ interface va với class method concrete | Dùng class method theo quy tắc ưu tiên, hoặc override chủ động | Tránh hiểu nhầm dispatch |
| Hai nhánh chỉ kế thừa một default gốc | Thường không cần override | Không có hai triển khai độc lập để chọn |

**Composition** có thể đơn giản hơn việc cho một lớp implements quá nhiều interface có hành vi mặc định khó phối hợp. Ví dụ một lớp chứa hai đối tượng hỗ trợ riêng cho logging và metrics thay vì nhận hai giao diện cùng muốn định nghĩa method **record()** với ý nghĩa khác nhau. Không phải lúc nào multiple inheritance qua interface cũng là biểu diễn tự nhiên nhất.

Đối với API được dùng rộng rãi, thêm một default method vào interface có thể giúp khả năng tương thích với các lớp cũ, nhưng cũng có thể **tạo xung đột mới** nếu khách hàng đang implements thêm một interface khác có phương thức tương ứng. Vì vậy API evolution vẫn cần kiểm tra khả năng tương thích nguồn/binary trong các tình huống kế thừa thực tế, không thể coi mọi lần thêm default là tuyệt đối an toàn.

## 14. Sơ đồ quyết định khi gặp nhiều method cùng tên

~~~text
Một lớp/interface nhìn thấy nhiều phương thức giống tên
                      |
                      v
          Chữ ký có thực sự đụng nhau?
             /                   \
           Không                  Có
            |                      |
      Xét overload          Có class method phù hợp
      khi gọi phương         với ưu tiên cao hơn?
      thức thực tế            /              \
                            Có              Không
                             |                |
                      Ưu tiên class      Interface con có
                      method phù hợp     override chuyên biệt?
                                          /           \
                                         Có          Không
                                          |             |
                                    Dùng default    Có nhiều default
                                    cụ thể hơn      độc lập ngang hàng?
                                                     /        \
                                                   Không       Có
                                                     |          |
                                            Xét kế thừa    Bắt buộc giải
                                            cùng gốc và     quyết bằng override
                                            ràng buộc khác  hoặc thay thiết kế
~~~

Sơ đồ là công cụ tư duy, không thay thế toàn bộ quy tắc chi tiết về subsignature, return type, abstract method, static method và quan hệ kế thừa. Khi thấy lỗi biên dịch, hãy quay lại chữ ký chính xác chứ đừng chỉ so sánh tên phương thức.

## 15. Những lỗi hay gặp

| Hiểu nhầm hoặc cách viết | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “implements A, B nên A luôn thắng” | Thứ tự implements không quyết định default | Override hoặc dùng quy tắc interface cụ thể hơn |
| “Hai default trùng chữ ký, Java tự chọn cái đầu” | Không có ưu tiên giữa hai default độc lập | Cung cấp override rõ ràng |
| “Ép kiểu sang A để gọi default của A” | Dispatch instance vẫn tìm override ở lớp thực tế | Gọi A.super.method() trong ngữ cảnh hợp lệ |
| “super.method() tương đương A.super.method()” | super theo lớp và qualified interface super khác nhau | Chỉ rõ A.super khi cần default của A |
| “A.super.method() gọi được mọi interface ancestor” | Có ràng buộc về direct superinterface và override | Kiểm tra quan hệ extends/implements và ngữ cảnh |
| “Hai nhánh hình thoi luôn xung đột” | Có thể chỉ là một default cùng gốc | Xem nguồn định nghĩa cuối cùng |
| “Interface con cũng cần implements thay vì extends” | Interface kế thừa interface bằng extends | Dùng interface C extends A, B |
| “default ở interface luôn thắng class method” | Phương thức lớp concrete ưu tiên hơn | Xem class hierarchy trước |
| “Ghi đè được bằng phương thức private” | Interface method là public theo hợp đồng | Dùng public khi override |
| “Hai phương thức khác return type thì là overload” | Return type không phân biệt chữ ký | Chọn tên/hợp đồng khác nếu không tương thích |
| “Static method của interface được trộn vào lớp” | Static interface method không kế thừa như default | Gọi bằng InterfaceName.method() |
| “Thêm default method không ảnh hưởng mã khách hàng” | Có thể gây conflict với interface khác | Kiểm tra giao diện được implements đồng thời |
| “Đổi sang lambda là tự xử lý được conflict” | Lambda chỉ hiện thực SAM, không chọn hai default | Sửa cấu trúc interface hoặc triển khai override |
| “@Override làm thay đổi quy tắc ưu tiên” | Annotation chỉ hỗ trợ kiểm tra override | Quy tắc chọn method vẫn do Java quy định |

## 16. Bài tập tự kiểm tra

### Bài 1: Hai default độc lập

Cho:

~~~java
interface A {
    default int number() { return 1; }
}

interface B {
    default int number() { return 2; }
}
~~~

**Yêu cầu:** khai báo một lớp C implements A, B sao cho number() trả **3**.

**Đáp án gợi ý:**

~~~java
class C implements A, B {
    @Override
    public int number() {
        return A.super.number() + B.super.number();
    }
}
~~~

Hai snippet là ví dụ minh họa, cần đặt cùng phạm vi khai báo thích hợp. C không được bỏ trống vì hai default độc lập cùng chữ ký.

### Bài 2: Lớp cha hay interface?

Cho một Base có **public String name()** trả "Class" và interface I có **default String name()** trả "Interface". Child extends Base implements I nhưng không override. **Child.name()** trả gì?

**Đáp án:** "Class", vì phương thức cụ thể được kế thừa từ lớp cha được ưu tiên.

### Bài 3: Interface cụ thể hơn

Cho Parent có default greet() trả "Parent". Child extends Parent, override default greet() trả "Child". Class Test implements Parent, Child. Kết quả **new Test().greet()** là gì?

**Đáp án:** "Child", vì Child là interface kế thừa chuyên biệt hơn và đã ghi đè default từ Parent.

### Bài 4: Hình thoi chung gốc

Origin có default id(), Left extends Origin, Right extends Origin, và Neither implements Left, Right. Hai nhánh không ghi đè id(). Có cần override id() tại Neither không?

**Đáp án:** không cần chỉ để giải quyết xung đột, vì cả hai nhánh cùng kế thừa một bản default từ Origin.

### Bài 5: Return type bất tương thích

Nếu A có **default String get()**, B có **default Integer get()**, liệu lớp implements A, B có giải quyết bằng **public Object get()** không?

**Đáp án:** không. **Object** không phải kiểu trả về có thể ghi đè thỏa cả String và Integer trong tình huống đó. Hai hợp đồng trả về bất tương thích; cần thiết kế lại interface.

### Bài 6: Interface con giải quyết xung đột

Hai interface A và B cùng có **default void log()**. Hãy nêu cách tạo interface C extends A, B sao cho lớp implements C không phải tự giải quyết xung đột.

**Đáp án:** C khai báo **default void log()** mới và có thể gọi **A.super.log()**, **B.super.log()** theo thứ tự đã thiết kế. Nếu C thay vào đó khai báo log() abstract, lớp concrete implements C phải tự triển khai.

### Bài 7: Phân biệt static method

Nếu A và B đều có **static String version()**, lớp X implements A, B có phải override version() để giải quyết default conflict không?

**Đáp án:** không. Static method của interface không phải default instance method. Gọi bằng A.version() hoặc B.version() theo ngữ cảnh.

### Bài 8: Quan sát dispatch

Nếu Combined implements Left, Right và override **public String label()**, tại sao **((Left) combined).label()** vẫn gọi bản override?

**Đáp án:** vì ép kiểu chỉ thay đổi kiểu nhìn thấy tại vị trí gọi, không đổi class thực tế của đối tượng. Instance method dispatch dùng triển khai phù hợp của class thực tế. Muốn gọi default cụ thể phải dùng cú pháp qualified interface super ở nơi hợp lệ.

## Tổng kết

Với nhiều default method, Java ưu tiên **một phương thức của lớp** khi thích hợp, hoặc **một default từ interface kế thừa chuyên biệt hơn**. Nếu có **hai triển khai default độc lập, ngang hàng, cùng chữ ký**, không có phép chọn tự động: lớp hoặc interface con phải **ghi đè**, hoặc người thiết kế phải thay đổi mô hình.

Cú pháp **InterfaceName.super.method()** cho phép gọi một default cụ thể trong ngữ cảnh hợp lệ, nhưng **ép kiểu** sang interface không làm điều tương tự. Hình thoi nhiều nhánh chỉ xung đột khi thực sự có các định nghĩa cạnh tranh; cùng kế thừa một default gốc thì không nhất thiết xung đột.

Trong mã Java hiện đại, hãy xem default method là một **hợp đồng hành vi dùng chung có chủ đích**, ưu tiên tên phương thức rõ nghĩa, hạn chế những interface có trách nhiệm chồng chéo và kiểm tra tác động khi mở rộng API.