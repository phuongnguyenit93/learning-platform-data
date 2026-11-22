# Vì sao enum và record không thể extends một lớp trừu tượng tùy ý?

Trong Java, một lớp chỉ có **một lớp cha trực tiếp**. Khai báo extends xác định lớp cha đó; implements khai báo các interface mà kiểu dữ liệu cam kết thực hiện. enum và record đều là những dạng khai báo lớp có quy tắc kế thừa riêng, vì vậy chúng không thể chọn thêm một lớp cha tùy ý.

- Mỗi enum có lớp cha trực tiếp là java.lang.Enum&lt;E&gt;, trong đó E là kiểu enum đang khai báo.
- Mỗi record có lớp cha trực tiếp là java.lang.Record.
- Cả enum và record đều có thể implements nhiều interface.
- Nếu cần dùng một lớp trừu tượng có sẵn, có thể đặt enum hoặc record bên trong một đối tượng adapter/wrapper kế thừa lớp đó và ủy quyền công việc cho đối tượng được bọc.

## 1. Quy tắc kế thừa của Java

Một lớp thông thường có thể kế thừa một lớp trừu tượng:

~~~java
abstract class Auditable {
    abstract String auditId();
}

final class Invoice extends Auditable {
    @Override
    String auditId() {
        return "INV-17";
    }
}
~~~

Invoice có Auditable làm lớp cha trực tiếp. Java không cho phép khai báo một lớp thông thường kế thừa đồng thời hai lớp, chẳng hạn vừa extends Auditable vừa extends một lớp khác.

enum và record cũng tuân theo giới hạn một lớp cha, nhưng chúng đã có lớp cha do ngôn ngữ quy định. Vì thế, các khai báo sau là **ví dụ minh họa cú pháp không hợp lệ**:

~~~java
abstract class Auditable {
    abstract String auditId();
}

enum OrderStatus extends Auditable {
    OPEN, CLOSED;
}

record Customer(String id) extends Auditable {}
~~~

Cần bỏ phần extends Auditable khỏi cả hai khai báo. Không có cách thêm một lớp cha tùy ý vào cú pháp enum hoặc record; đây là quy tắc của ngôn ngữ Java, không phải giới hạn riêng của một IDE.

## 2. Vì sao enum kế thừa java.lang.Enum?

enum biểu diễn một tập hằng số hữu hạn được khai báo trước. Ví dụ:

~~~java
enum OrderStatus {
    OPEN, PROCESSING, CLOSED
}
~~~

Java cung cấp các hành vi đặc biệt cho enum, chẳng hạn tên hằng số qua name(), vị trí khai báo qua ordinal(), khả năng so sánh giữa các hằng số cùng enum và cách xử lý hằng số enum khi tuần tự hóa. Lớp nền java.lang.Enum&lt;E&gt; cung cấp một phần các hành vi chuẩn này, còn trình biên dịch tạo các hằng số enum theo quy tắc riêng.

Nếu enum có thể kế thừa một lớp tùy ý, nó sẽ cần đồng thời kế thừa cả lớp tùy ý đó lẫn java.lang.Enum&lt;E&gt;. Điều đó vi phạm quy tắc một lớp cha trực tiếp. Java giải quyết bằng cách cố định lớp cha của enum là java.lang.Enum&lt;E&gt;.

enum vẫn có thể chứa trường, constructor, phương thức và triển khai interface. Constructor enum không được gọi bằng new từ bên ngoài để tạo thêm hằng số tùy ý; các hằng số hợp lệ được liệt kê trong khai báo enum.

Ví dụ enum có thể triển khai interface:

~~~java
interface Labelled {
    default String label() {
        return getClass().getSimpleName();
    }
}

enum OrderStatus implements Labelled {
    OPEN, CLOSED
}
~~~

OrderStatus dùng được phương thức mặc định label() từ interface Labelled. Việc triển khai interface bổ sung hợp đồng và hành vi mà không thay đổi lớp cha của enum. Một hằng số enum cũng có thể có phần thân riêng để ghi đè phương thức, nhưng điều đó vẫn không cho phép enum kế thừa một lớp tùy ý.

## 3. Vì sao record kế thừa java.lang.Record?

record được thiết kế để khai báo kiểu dữ liệu chủ yếu mang dữ liệu. Ví dụ:

~~~java
record Customer(String id, String name) {}
~~~

Khai báo trên cho biết Customer có hai thành phần dữ liệu là id và name. Nếu không tự định nghĩa các thành phần tương ứng, trình biên dịch cung cấp các trường thành phần final, phương thức truy cập id() và name(), constructor chuẩn, cùng các triển khai mặc định cho equals(), hashCode() và toString().

Mọi record đều có java.lang.Record làm lớp cha trực tiếp và record là kiểu final. Do đó, record không thể thêm một lớp cha khác, kể cả lớp đó là abstract. Record cũng không có cú pháp extends trong khai báo.

Quy tắc này giúp mô hình dữ liệu của record nhất quán: các thành phần được khai báo xác định dữ liệu của record, còn các hành vi dùng chung có thể đến từ interface hoặc được ủy quyền cho đối tượng khác. Trạng thái tùy ý kế thừa từ một lớp cha có thể làm mờ ranh giới dữ liệu và gây khó hiểu khi đánh giá equality giữa các record.

Record vẫn có thể implements nhiều interface, ghi đè phương thức, khai báo constructor tường minh hoặc compact constructor để kiểm tra dữ liệu đầu vào. Những khả năng đó không thay đổi lớp cha java.lang.Record và không làm record trở thành kiểu có thể được kế thừa.

## 4. Ví dụ chạy được: interface và composition

Ví dụ dưới đây dùng Java 17 trở lên. Customer là record, OrderStatus là enum; cả hai triển khai interface. CustomerAdapter là một lớp thông thường kế thừa lớp trừu tượng ExternalIdSource và ủy quyền việc lấy ID cho Customer.

Lưu toàn bộ mã vào tệp EnumRecordDemo.java:

~~~java
interface Identified {
    String id();
}

interface Labelled {
    default String label() {
        return getClass().getSimpleName();
    }
}

enum OrderStatus implements Labelled {
    OPEN, CLOSED
}

record Customer(String id, String name)
        implements Identified, Labelled {}

abstract class ExternalIdSource {
    abstract String externalId();
}

final class CustomerAdapter extends ExternalIdSource {
    private final Customer customer;

    CustomerAdapter(Customer customer) {
        this.customer = customer;
    }

    @Override
    String externalId() {
        return customer.id();
    }
}

public class EnumRecordDemo {
    public static void main(String[] args) {
        Customer customer = new Customer("C-17", "Lan");

        System.out.println(customer);
        System.out.println(customer.id());
        System.out.println(customer.label());
        System.out.println(OrderStatus.OPEN.label());

        ExternalIdSource legacy = new CustomerAdapter(customer);
        System.out.println(legacy.externalId());
    }
}
~~~

Biên dịch và chạy:

~~~text
javac EnumRecordDemo.java
java EnumRecordDemo
~~~

Kết quả chuẩn trên stdout:

~~~text
Customer[id=C-17, name=Lan]
C-17
Customer
OrderStatus
C-17
~~~

Ở đây, Customer không kế thừa ExternalIdSource. CustomerAdapter mới là lớp kế thừa ExternalIdSource, giữ một tham chiếu đến Customer và chuyển lời gọi externalId() thành customer.id(). Đây là cách kết hợp kiểu dữ liệu record với một API cũ yêu cầu lớp con của lớp trừu tượng.

## 5. Chọn cách thiết kế phù hợp

| Nhu cầu | Cách phù hợp |
|---|---|
| Nhiều kiểu cần cùng cam kết một nhóm phương thức | Khai báo interface và cho enum/record implements interface đó |
| Cần hành vi dùng chung không phụ thuộc trạng thái instance | Có thể dùng phương thức default trong interface |
| API hoặc framework bắt buộc nhận lớp con của một abstract class | Tạo adapter/wrapper kế thừa abstract class và ủy quyền cho enum/record |
| Cần dùng lại trạng thái instance và triển khai dựa trên lớp cha | Cân nhắc một lớp thông thường trong hệ phân cấp kế thừa |
| Record cần thêm thông tin dữ liệu | Thêm thành phần record phù hợp, hoặc chứa một đối tượng khác để composition |

Interface mô tả hợp đồng; nó không thay thế hoàn toàn lớp trừu tượng. Interface không cung cấp các trường instance tùy ý hoặc constructor kế thừa, dù có thể khai báo phương thức default. Nếu cần trạng thái và quy trình khởi tạo chung của một lớp cha, adapter hoặc composition thường là lựa chọn rõ ràng hơn cho enum và record.

## 6. Những nhầm lẫn thường gặp

- **“Lớp abstract không tạo instance nên có thể làm lớp cha thứ hai.”** Không đúng. Quy tắc một lớp cha áp dụng cho mọi lớp, bất kể lớp cha có abstract hay không.
- **“enum chỉ là class có danh sách hằng số.”** enum là một dạng khai báo đặc biệt với lớp cha java.lang.Enum&lt;E&gt; và quy tắc tạo hằng số riêng.
- **“record là class nên có thể extends tùy ý.”** record là dạng khai báo lớp có lớp cha cố định là java.lang.Record và không cho phép khai báo extends.
- **“implements tương đương extends.”** Interface cung cấp hợp đồng và có thể cung cấp phương thức default, nhưng không truyền trạng thái instance hay constructor của một lớp cha.
- **“Có thể sửa lớp cha bằng cách ghi đè phương thức.”** Ghi đè thay đổi hành vi phương thức, không thay đổi cây kế thừa.
- **“Nếu cần hành vi của abstract class thì phải bỏ record hoặc enum ngay.”** Không nhất thiết. Trước hết hãy xem có thể mô hình hóa hành vi bằng interface hay bọc đối tượng bằng adapter hay không. Chỉ chuyển sang lớp thông thường khi mô hình thực sự cần kế thừa trạng thái và hành vi của lớp cha.

## 7. Cách ghi nhớ

enum kế thừa java.lang.Enum&lt;E&gt; vì Java quản lý chúng như các hằng số enum có hành vi chuẩn. record kế thừa java.lang.Record vì Java quản lý chúng như các kiểu dữ liệu có thành phần được khai báo rõ ràng. Cả hai có thể triển khai nhiều interface, nhưng không thể extends một lớp trừu tượng tùy ý.

Khi gặp yêu cầu “enum/record phải là subclass của abstract class”, hãy kiểm tra xem yêu cầu đó thực sự cần hợp đồng phương thức, cần dùng lại trạng thái và triển khai của lớp cha, hay chỉ cần tương thích với một API cũ. Dùng interface cho hợp đồng; dùng adapter/composition khi cần tích hợp với lớp trừu tượng; dùng lớp thông thường nếu mô hình thực sự đòi hỏi một lớp cha do ứng dụng chọn.
