# Bảng so sánh abstract class, interface và concrete class trong Java

Trong Java, **interface**, **abstract class** và **concrete class** giải quyết những nhu cầu khác nhau khi thiết kế kiểu dữ liệu. Interface mô tả một hợp đồng mà các kiểu có thể cung cấp; abstract class là lớp cơ sở có thể chia sẻ trạng thái và hành vi; concrete class là lớp đủ hoàn chỉnh để tạo đối tượng trực tiếp.

Ba khái niệm này không phải ba lựa chọn loại trừ nhau. Một concrete class có thể kế thừa abstract class và đồng thời triển khai một hoặc nhiều interface. Muốn chọn đúng, hãy xem phần nào cần được cam kết trong hợp đồng, phần nào cần dùng chung mã và trạng thái, và kiểu nào cần được khởi tạo thành đối tượng.

## 1. Bảng so sánh nhanh

| Tiêu chí | Interface | Abstract class | Concrete class |
|---|---|---|---|
| Mục đích chính | Định nghĩa hợp đồng hoặc khả năng mà kiểu cung cấp | Chia sẻ nền tảng và hành vi giữa các lớp có liên quan | Cung cấp một kiểu có thể tạo đối tượng và sử dụng |
| Có thể dùng `new` trực tiếp? | Không | Không | Có, nếu constructor và quyền truy cập cho phép |
| Khai báo phương thức trừu tượng | Có thể khai báo phương thức không có thân | Có thể khai báo phương thức không có thân | Không được còn phương thức trừu tượng chưa triển khai |
| Phương thức có thân | Có `default`, `static` và `private` methods theo quy tắc Java | Có thể có phương thức thường và phương thức `static` | Có thể có phương thức thường và `static` |
| Trạng thái đối tượng | Không có trường instance; trường interface là `public static final` ngầm định | Có thể có trường instance và constructor | Có thể có trường instance và constructor |
| Kế thừa / triển khai | Interface có thể `extends` nhiều interface; class dùng `implements` | Một class có thể `extends` một class cha và abstract class có thể `implements` interface | Có thể `extends` một class và `implements` nhiều interface |
| Khi nào hữu ích? | Các lớp khác nhau cần cam kết cùng một hành vi | Các lớp có chung dữ liệu, quy tắc khởi tạo hoặc logic | Cần một kiểu hoàn chỉnh để tạo và sử dụng đối tượng |

Điểm cần nhớ: **interface nói một kiểu có thể làm gì; abstract class có thể cung cấp nền tảng chung; concrete class cung cấp một triển khai có thể tạo đối tượng**. Đây là cách nhớ nhanh, còn quyết định thực tế phụ thuộc vào thiết kế cụ thể.

## 2. Interface: hợp đồng về khả năng

Interface khai báo các phương thức mà kiểu triển khai cần cung cấp. Các class không cần có cùng lớp cha để cùng triển khai một interface. Điều này hữu ích khi nhiều loại đối tượng khác nhau có cùng một khả năng, chẳng hạn thanh toán, ghi log, sắp xếp hoặc cung cấp mã định danh.

~~~java
interface Payable {
    double monthlyPay();
}
~~~

Một class triển khai `Payable` phải cung cấp phương thức `monthlyPay()`, trừ khi chính class đó là abstract. Bên gọi có thể làm việc với kiểu `Payable` mà không cần biết đối tượng thuộc class nào.

~~~java
final class Contractor implements Payable {
    private final double hourlyRate;
    private final int hours;

    Contractor(double hourlyRate, int hours) {
        this.hourlyRate = hourlyRate;
        this.hours = hours;
    }

    @Override
    public double monthlyPay() {
        return hourlyRate * hours;
    }
}
~~~

Interface cũng có thể có `default` method với phần triển khai mặc định, `static` method thuộc interface và `private` method hỗ trợ tái sử dụng logic nội bộ của các method trong interface. Tuy nhiên, interface không dùng để chứa trạng thái riêng cho từng instance. Các trường khai báo trong interface luôn là hằng số `public static final` theo ngữ nghĩa của Java.

Một class có thể triển khai nhiều interface:

~~~java
final class Invoice implements Payable, Comparable<Invoice> {
    // Cung cấp các phương thức cần thiết của cả hai interface.
}
~~~

Đoạn trên chỉ minh họa cú pháp và không phải class hoàn chỉnh, vì một class thật cần khai báo dữ liệu và triển khai mọi phương thức trừu tượng còn thiếu. Điểm quan trọng là Java cho phép một class thực hiện nhiều hợp đồng interface, trong khi class chỉ có một lớp cha trực tiếp.

**Nên chọn interface khi** cần công bố một hợp đồng ổn định, muốn nhiều loại class độc lập có thể cung cấp cùng khả năng, hoặc muốn dễ thay thế implementation trong kiểm thử và cấu hình ứng dụng.

## 3. Abstract class: lớp cơ sở có thể chia sẻ trạng thái và hành vi

Abstract class được khai báo bằng từ khóa `abstract`. Nó không thể được khởi tạo trực tiếp, nhưng có thể chứa constructor, trường instance, phương thức đã triển khai và phương thức trừu tượng. Class con cụ thể kế thừa nó phải triển khai các phương thức trừu tượng còn thiếu.

~~~java
abstract class Employee {
    private final String name;

    protected Employee(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }

    public abstract String role();

    public String summary() {
        return name + " (" + role() + ")";
    }
}
~~~

Trong ví dụ này, abstract class giữ tên nhân viên và triển khai hành vi dùng chung là `summary()`. Phương thức `role()` được để trừu tượng vì mỗi loại nhân viên có thể có vai trò khác nhau. Constructor giúp bảo đảm các lớp con khởi tạo phần trạng thái chung theo cùng quy tắc.

Class con có thể kế thừa phần dùng chung và hoàn thiện phần còn thiếu:

~~~java
final class SalariedEmployee extends Employee {
    private final double salary;

    SalariedEmployee(String name, double salary) {
        super(name);
        this.salary = salary;
    }

    @Override
    public String role() {
        return "Engineer";
    }

    public double salary() {
        return salary;
    }
}
~~~

`SalariedEmployee` là concrete class vì đã triển khai `role()` và không còn phương thức trừu tượng chưa xử lý. Có thể tạo đối tượng `SalariedEmployee`, nhưng không thể viết `new Employee(...)` khi `Employee` vẫn là abstract class.

Abstract class cũng có thể triển khai interface. Ví dụ, nếu `Employee` implements `Payable`, nó có thể để `monthlyPay()` trừu tượng để từng lớp con tự tính lương. Khi đó abstract class vừa cung cấp trạng thái chung, vừa làm lớp cầu nối giữa hợp đồng interface và các triển khai cụ thể.

**Nên chọn abstract class khi** các lớp có mối quan hệ kế thừa hợp lý và cần chia sẻ trạng thái, constructor, quy tắc bất biến hoặc hành vi chung. Không nên tạo abstract class chỉ để gom các phương thức không liên quan; interface thường thích hợp hơn cho một khả năng độc lập.

## 4. Concrete class: kiểu có thể tạo đối tượng

Concrete class là class không được khai báo `abstract` và đã triển khai mọi phương thức trừu tượng bắt buộc. Nếu class có constructor truy cập được, chương trình có thể tạo instance của nó bằng `new`.

Concrete class không có nghĩa là class đó bắt buộc phải khai báo `final`. Một concrete class vẫn có thể được kế thừa nếu không có modifier hoặc ràng buộc khác cấm kế thừa. `final class` là một concrete class không cho phép class khác kế thừa.

~~~java
final class FixedContractor implements Payable {
    private final String name;
    private final double monthlyAmount;

    FixedContractor(String name, double monthlyAmount) {
        this.name = name;
        this.monthlyAmount = monthlyAmount;
    }

    public String name() {
        return name;
    }

    @Override
    public double monthlyPay() {
        return monthlyAmount;
    }
}
~~~

Class này không kế thừa abstract class nào nhưng vẫn triển khai interface `Payable` và có thể được khởi tạo. Nó cũng minh họa rằng các class không liên quan trong cây kế thừa vẫn có thể được xử lý thống nhất thông qua interface.

Một concrete class có thể đồng thời kế thừa abstract class và triển khai interface:

~~~java
final class SalariedEmployee extends Employee implements Payable {
    // Hoàn thiện các phương thức trừu tượng của Employee và Payable.
}
~~~

Đây là minh họa cấu trúc; trong chương trình hoàn chỉnh, nếu cả hai kiểu yêu cầu cùng một chữ ký phương thức thì một implementation phù hợp có thể đáp ứng cả hai hợp đồng. Nếu các hợp đồng có chữ ký hoặc kiểu trả về xung đột, cần điều chỉnh thiết kế để tuân thủ quy tắc tương thích của Java.

## 5. Ví dụ hoàn chỉnh chạy được trên Java 17

Chương trình dưới đây dùng cả ba khái niệm. `Payable` định nghĩa hợp đồng tính lương; `Employee` là abstract class chứa tên và hành vi dùng chung; `SalariedEmployee` là concrete class kế thừa nền tảng đó. `Contractor` là concrete class độc lập chỉ triển khai interface, cho thấy các kiểu không cùng cây kế thừa vẫn có thể dùng chung một hợp đồng.

Lưu toàn bộ mã vào file `TypeComparisonDemo.java`:

~~~java
public class TypeComparisonDemo {
    public static void main(String[] args) {
        Employee employee = new SalariedEmployee("Lan", 3000.0);
        Payable[] payables = {
            employee,
            new Contractor("Minh", 30.0, 40)
        };

        System.out.println("EMPLOYEE: " + employee.summary());

        for (Payable payable : payables) {
            System.out.printf(java.util.Locale.ROOT,
                    "PAY: %.2f%n", payable.monthlyPay());
        }
    }
}

interface Payable {
    double monthlyPay();
}

abstract class Employee implements Payable {
    private final String name;

    protected Employee(String name) {
        this.name = name;
    }

    public String name() {
        return name;
    }

    public abstract String role();

    public String summary() {
        return name + " (" + role() + ")";
    }
}

final class SalariedEmployee extends Employee {
    private final double salary;

    SalariedEmployee(String name, double salary) {
        super(name);
        this.salary = salary;
    }

    @Override
    public String role() {
        return "Engineer";
    }

    @Override
    public double monthlyPay() {
        return salary;
    }
}

final class Contractor implements Payable {
    private final String name;
    private final double hourlyRate;
    private final int hours;

    Contractor(String name, double hourlyRate, int hours) {
        this.name = name;
        this.hourlyRate = hourlyRate;
        this.hours = hours;
    }

    @Override
    public double monthlyPay() {
        return hourlyRate * hours;
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 TypeComparisonDemo.java
java TypeComparisonDemo
~~~

Stdout chính xác:

~~~text
EMPLOYEE: Lan (Engineer)
PAY: 3000.00
PAY: 1200.00
~~~

Trong ví dụ, biến `employee` có kiểu tham chiếu `Employee` nhưng giữ một đối tượng `SalariedEmployee`. Mảng `payables` có kiểu phần tử `Payable`, nên có thể chứa cả nhân viên hưởng lương lẫn nhà thầu. Khi gọi `monthlyPay()`, Java thực thi implementation tương ứng với đối tượng thực tế. Đây là đa hình: mã gọi dựa trên hợp đồng chung trong khi hành vi cụ thể được chọn theo kiểu đối tượng lúc chạy.

## 6. Quan hệ giữa ba khái niệm

Có thể hình dung cấu trúc của ví dụ như sau:

~~~text
Payable (interface)
    ^                  ^
    | implements       | implements
Employee (abstract)   Contractor (concrete)
    ^
    | extends
SalariedEmployee (concrete)
~~~

Mũi tên biểu diễn quan hệ kiểu: `Employee` triển khai `Payable`; `Contractor` cũng triển khai `Payable`; `SalariedEmployee` kế thừa `Employee`. Nhờ vậy, lớp gọi có thể chọn mức trừu tượng phù hợp với nhu cầu:

- Dùng `Payable` nếu chỉ cần gọi `monthlyPay()`.
- Dùng `Employee` nếu cần các hành vi và trạng thái chung của nhân viên như `name()` hoặc `summary()`.
- Dùng `SalariedEmployee` nếu cần hành vi đặc thù của nhân viên hưởng lương như `salary()`, hoặc khi cần tạo đối tượng cụ thể đó.

Nên khai báo biến và tham số bằng kiểu trừu tượng phù hợp nhất với hành vi mà đoạn mã cần. Việc này giảm phụ thuộc vào implementation cụ thể và giúp thay thế đối tượng dễ dàng hơn.

## 7. Những khác biệt trong thiết kế cần hiểu rõ

**Kế thừa class là đơn kế thừa.** Một class Java chỉ có thể có một lớp cha trực tiếp, dù lớp cha đó là abstract hay concrete. Class có thể triển khai nhiều interface. Vì vậy, abstract class phù hợp cho nền tảng chung trong một cây kế thừa, còn interface phù hợp cho các khả năng có thể xuất hiện ở nhiều cây class khác nhau.

**Constructor thuộc class.** Interface không có constructor và không được khởi tạo. Abstract class có constructor, nhưng constructor chỉ được gọi thông qua quá trình khởi tạo lớp con. Concrete class có thể cung cấp constructor để tạo đối tượng.

**Phương thức trừu tượng phải được hoàn thiện.** Một class con vẫn có thể là abstract nếu chưa triển khai tất cả phương thức trừu tượng. Khi muốn tạo instance, cần một concrete class đã đáp ứng đầy đủ các phương thức trừu tượng kế thừa.

**Interface không thay thế mọi nhu cầu của abstract class.** Interface có thể có default method, nhưng không thể chứa trạng thái instance hoặc constructor. Nếu nhiều lớp cần chung một trường dữ liệu cùng quy tắc khởi tạo, abstract class có thể biểu đạt mô hình đó trực tiếp hơn.

**Abstract class không thay thế mọi nhu cầu của interface.** Nếu nhiều class không có quan hệ kế thừa tự nhiên nhưng cần cung cấp cùng khả năng, buộc chúng vào một lớp cha chỉ để chia sẻ tên phương thức sẽ làm cây kế thừa cứng nhắc. Interface thể hiện hợp đồng đó mà không áp đặt một lớp cha chung.

**Concrete class vẫn có thể phụ thuộc vào abstraction.** Dù class được tạo instance trực tiếp, nó có thể triển khai interface và được sử dụng qua kiểu interface. “Concrete” mô tả khả năng khởi tạo của class, không nói rằng class phải được tham chiếu trực tiếp ở mọi nơi.

## 8. Lỗi thường gặp

- **Cố tạo đối tượng từ interface hoặc abstract class:** `new Payable()` và `new Employee(...)` không hợp lệ. Hãy tạo một concrete class triển khai hoặc kế thừa kiểu đó.
- **Quên triển khai phương thức bắt buộc:** concrete class phải triển khai các phương thức trừu tượng còn thiếu. Nếu chưa sẵn sàng, class cần được khai báo `abstract`.
- **Dùng abstract class chỉ để định nghĩa hợp đồng:** nếu không cần trạng thái hoặc hành vi dùng chung, interface thường linh hoạt hơn.
- **Dùng interface để lưu trạng thái instance:** trường interface là hằng số tĩnh, không phải dữ liệu riêng cho từng đối tượng. Hãy đặt trạng thái instance trong class.
- **Nhầm concrete với final:** concrete class có thể được kế thừa; chỉ `final` mới cấm kế thừa class đó.
- **Dùng kiểu cụ thể ở mọi tham số:** điều này có thể gắn mã gọi với một implementation. Nếu chỉ cần hành vi chung, hãy nhận interface hoặc abstract class thích hợp.
- **Tạo cây kế thừa quá sâu:** abstract class nên phản ánh quan hệ “là một” và có hành vi chung thực sự. Với khả năng độc lập, composition và interface thường tạo thiết kế linh hoạt hơn.
- **Quên `@Override`:** chú thích này giúp compiler phát hiện lỗi khi tên hoặc chữ ký phương thức không khớp với phương thức được triển khai.

## 9. Cách chọn trong tình huống thực tế

Chọn **interface** khi bạn muốn định nghĩa một hợp đồng mà nhiều class có thể triển khai, chẳng hạn `Payable`, `Runnable` hoặc `Comparable`. Hợp đồng giúp mã gọi không phụ thuộc vào một loại đối tượng cụ thể.

Chọn **abstract class** khi các kiểu con thuộc cùng một họ khái niệm và cần chia sẻ trạng thái, constructor, hành vi hoặc các quy tắc chung. Để các phương thức trừu tượng dành cho những phần mà từng kiểu con phải tự định nghĩa.

Chọn **concrete class** khi bạn cần một triển khai có thể tạo đối tượng để thực thi nghiệp vụ. Concrete class có thể đứng độc lập, kế thừa abstract class hoặc triển khai một hay nhiều interface.

Một quy trình thiết kế hữu ích là: xác định hành vi mà bên gọi cần, định nghĩa interface nếu cần một hợp đồng có thể thay thế; thêm abstract class nếu có phần trạng thái và logic chung đáng chia sẻ; rồi cung cấp một hoặc nhiều concrete class để thực thi. Không cần tạo đủ cả ba tầng nếu bài toán không có nhu cầu thực tế.

## 10. Checklist tự kiểm tra

- Bạn có thể giải thích interface công bố hành vi nào mà không nói đến implementation cụ thể không?
- Abstract class có thật sự chứa trạng thái hoặc hành vi chung đáng chia sẻ không?
- Concrete class đã triển khai mọi phương thức trừu tượng và có constructor phù hợp chưa?
- Mã gọi có thể dùng interface hoặc abstract class thay vì phụ thuộc vào class cụ thể không?
- Bạn đã phân biệt quan hệ `extends` với `implements` và nhớ rằng class chỉ có một lớp cha trực tiếp chưa?
- Ví dụ đã biên dịch bằng phiên bản Java mục tiêu và kết quả stdout có khớp tài liệu không?

Khi hiểu rõ các vai trò này, bạn có thể thiết kế API Java dễ mở rộng hơn: interface xác định hợp đồng, abstract class cung cấp phần nền tảng dùng chung khi cần, và concrete class biến hợp đồng cùng nền tảng đó thành đối tượng thực thi được.
