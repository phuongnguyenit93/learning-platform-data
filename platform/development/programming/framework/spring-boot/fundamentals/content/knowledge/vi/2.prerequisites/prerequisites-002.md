# Class, interface và quan hệ phụ thuộc giữa các đối tượng

Khi xây dựng một ứng dụng Spring Boot, bạn thường thấy các lớp như `UserController`, `UserService`, `UserRepository` hoặc `PaymentGateway`. Mỗi lớp đảm nhiệm một phần việc, nhưng ứng dụng chỉ hoạt động khi những đối tượng được tạo từ các lớp ấy biết cách cộng tác với nhau.

Muốn hiểu **Dependency Injection (DI)** của Spring, trước hết cần nắm ba ý tưởng trong Java:

1. **Class** mô tả dữ liệu và hành vi của một loại đối tượng; **object** là một thể hiện được tạo trong lúc chương trình chạy.
2. **Interface** mô tả hợp đồng mà các lớp triển khai cam kết cung cấp; nhờ đó mã sử dụng có thể làm việc với nhiều cách triển khai khác nhau.
3. **Dependency (quan hệ phụ thuộc)** xuất hiện khi một thành phần cần một thành phần khác để hoàn thành công việc. Cách tổ chức và cung cấp các dependency ảnh hưởng trực tiếp đến khả năng bảo trì, thay thế và kiểm thử.

Bài học đi từ Java thuần đến cách Spring Boot kết nối các đối tượng. Mục tiêu là hiểu bản chất của từng quan hệ, không chỉ nhớ các annotation.

## 1. Phân biệt class và object

### 1.1. Class mô tả cấu trúc và hành vi

Trong Java, một **class (lớp)** có thể khai báo:

- **Field (trường):** dữ liệu hoặc trạng thái mà mỗi đối tượng lưu giữ.
- **Constructor (hàm tạo):** quy tắc khởi tạo đối tượng.
- **Method (phương thức):** hành vi của đối tượng.
- **Access modifier:** phạm vi truy cập như `public`, `private` hoặc package-private.

Ví dụ tạo lớp `Customer` trong file `Customer.java`:

~~~java
public class Customer {
    private final String name;
    private int rewardPoints;

    public Customer(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Customer name is required");
        }
        this.name = name;
        this.rewardPoints = 0;
    }

    public String getName() {
        return name;
    }

    public int getRewardPoints() {
        return rewardPoints;
    }

    public void earnPoints(int points) {
        if (points <= 0) {
            throw new IllegalArgumentException("Points must be positive");
        }
        rewardPoints += points;
    }
}
~~~

Ý nghĩa:

- `Customer` là **kiểu dữ liệu** do người lập trình định nghĩa.
- `name` và `rewardPoints` là trạng thái thuộc từng đối tượng `Customer`.
- `Customer(String name)` là constructor, tạo trạng thái ban đầu hợp lệ.
- `earnPoints` là hành vi; nó kiểm tra đầu vào trước khi thay đổi trạng thái.
- `private` che giấu field khỏi mã bên ngoài; các method công khai là cách sử dụng có kiểm soát.
- `final` trên `name` ngăn việc gán lại tham chiếu của field sau khi khởi tạo; nó không có nghĩa mọi đối tượng được tham chiếu bởi một field `final` đều bất biến.

### 1.2. Object là một thể hiện cụ thể

Tạo và sử dụng đối tượng trong `Main.java`:

~~~java
public class Main {
    public static void main(String[] args) {
        Customer lan = new Customer("Lan");
        Customer minh = new Customer("Minh");

        lan.earnPoints(20);
        minh.earnPoints(5);

        System.out.println(lan.getName() + ": " + lan.getRewardPoints());
        System.out.println(minh.getName() + ": " + minh.getRewardPoints());
    }
}
~~~

Kết quả:

~~~text
Lan: 20
Minh: 5
~~~

Hai biến `lan` và `minh` đang tham chiếu đến **hai đối tượng khác nhau**, đều được tạo từ cùng class `Customer`. Thay đổi điểm của `lan` không tự làm thay đổi điểm của `minh`.

~~~text
                   class Customer
                 +----------------+
                 | name           |
                 | rewardPoints   |
                 | earnPoints()   |
                 +----------------+
                        │
                 tạo các thể hiện
                   /          \
                  ▼            ▼
          object "Lan"    object "Minh"
          points = 20     points = 5
~~~

Một biến có kiểu class hoặc interface thường lưu **tham chiếu** đến đối tượng, không chứa toàn bộ đối tượng. Ví dụ:

~~~java
Customer first = new Customer("Lan");
Customer second = first;

second.earnPoints(10);
System.out.println(first.getRewardPoints()); // 10
~~~

`first` và `second` là hai biến tham chiếu **cùng một đối tượng**. Đây là khác biệt quan trọng so với ví dụ tạo hai lần bằng `new`.

### 1.3. Tại sao đóng gói (encapsulation) quan trọng?

Nếu công khai `rewardPoints` để mọi nơi sửa trực tiếp, một đoạn mã khác có thể gán `-100` và phá vỡ quy tắc nghiệp vụ. Để field ở chế độ `private` rồi cung cấp `earnPoints` giúp lớp tự bảo vệ tính hợp lệ của trạng thái.

Một lớp có thiết kế tốt thường:

- Có trách nhiệm rõ ràng.
- Bảo vệ các bất biến quan trọng của dữ liệu.
- Cung cấp phương thức diễn tả thao tác hợp lệ.
- Hạn chế để nơi khác phụ thuộc vào chi tiết lưu trữ nội bộ.

Việc đặt tất cả field thành `private` chưa đủ bảo đảm thiết kế tốt; phương thức công khai cũng phải phản ánh hành vi có ý nghĩa.

## 2. Interface: mô tả hợp đồng, không cố định cách thực hiện

Giả sử một ứng dụng cần gửi thông báo cho người đăng ký. Hôm nay thông báo được in ra console; sau này có thể gửi email hoặc đẩy vào message queue.

Nếu mã nghiệp vụ luôn gọi trực tiếp một lớp gửi email cụ thể, việc đổi sang kênh khác sẽ kéo theo sửa mã nghiệp vụ. Ta có thể định nghĩa phần **hợp đồng** trước.

### 2.1. Khai báo interface

File `NotificationSender.java`:

~~~java
public interface NotificationSender {
    void send(String recipient, String message);
}
~~~

`NotificationSender` nói rằng một đối tượng tuân thủ hợp đồng này phải cung cấp thao tác `send` với hai tham số. Interface **không quy định** việc gửi thông báo phải thực hiện bằng email, HTTP hay console.

Trong Java:

- Dùng từ khóa `interface` để khai báo hợp đồng.
- Dùng `implements` để một class cam kết triển khai interface.
- Những phương thức thông thường khai báo như ví dụ trên mặc định là `public abstract`.
- Interface cũng có thể có `default` method, `static` method và một số thành phần hỗ trợ khác. Nó không chỉ giới hạn ở các phương thức trừu tượng.
- Không thể tạo đối tượng trực tiếp bằng `new NotificationSender()` vì interface không phải một class cụ thể có constructor để khởi tạo.

### 2.2. Các lớp triển khai cùng hợp đồng

File `ConsoleNotificationSender.java`:

~~~java
public class ConsoleNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println("[To: " + recipient + "] " + message);
    }
}
~~~

File `SilentNotificationSender.java`:

~~~java
public class SilentNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        // Cố ý không gửi: hữu ích trong một số tình huống thử nghiệm.
    }
}
~~~

Cả hai lớp đều có thể được dùng tại nơi yêu cầu kiểu `NotificationSender`:

~~~java
NotificationSender sender = new ConsoleNotificationSender();
sender.send("lan@example.com", "Welcome!");
~~~

Biến `sender` được khai báo bằng kiểu **interface**, còn đối tượng thật được tạo từ class `ConsoleNotificationSender`. Lúc thực thi, Java gọi `send` của class triển khai tương ứng. Cơ chế gọi cùng một hợp đồng với những cách thực hiện khác nhau là một biểu hiện của **polymorphism (đa hình)**.

~~~text
              <<interface>>
            NotificationSender
               + send(...)
                     ▲
            implements
                /     \
               /       \
              /         \
  ConsoleNotificationSender   SilentNotificationSender
       + send(...)                + send(...)
~~~

Đa hình giúp mã sử dụng nói **cần thao tác gì**, trong khi mã triển khai quyết định **thao tác đó được thực hiện như thế nào**.

### 2.3. Interface khác abstract class thế nào?

| Đặc điểm | Interface | Abstract class |
| --- | --- | --- |
| Mục đích thường gặp | Xác định vai trò/hợp đồng có thể được nhiều lớp khác nhau thực hiện | Chia sẻ trạng thái hoặc hành vi nền cho một họ lớp liên quan |
| Từ khóa sử dụng | `implements` | `extends` |
| Quan hệ với nhiều kiểu | Một class có thể triển khai nhiều interface | Một class chỉ có thể kế thừa trực tiếp một class |
| Trạng thái thể hiện (instance state) | Không khai báo instance field thông thường; field của interface là hằng `public static final` | Có thể có instance field |
| Constructor | Không có constructor của interface | Có constructor để khởi tạo phần trạng thái của lớp cha |
| Method có phần thân | Có `default`, `static` và các method được ngôn ngữ cho phép | Có cả method thường lẫn abstract method |

Ví dụ: `NotificationSender` là hợp đồng hợp lý vì nhiều cách gửi khác nhau không nhất thiết phải dùng chung trạng thái hoặc thuật toán. Ngược lại, một họ class thực sự chia sẻ logic, dữ liệu và bất biến có thể cân nhắc abstract class.

**Không cần tạo interface cho mọi class.** Interface có ích khi diễn tả ranh giới có ý nghĩa, hợp đồng với nhiều cách triển khai, hoặc giúp quản lý dependency rõ ràng. Một class đơn giản, ổn định, không có nhu cầu trừu tượng hóa vẫn có thể được dùng trực tiếp.

## 3. Dependency: khi một đối tượng cần đối tượng khác

Trong lập trình hướng đối tượng, **A phụ thuộc B** nếu A cần B hoặc một khả năng của B để thực hiện công việc. Dependency có thể xuất hiện qua:

- Field hoặc constructor của A nhận đối tượng B.
- Method của A gọi method của B.
- Method của A nhận B làm tham số hoặc trả về B.
- A trực tiếp tạo B bằng `new B()`.
- A sử dụng API, kiểu dữ liệu, hằng hoặc phương thức tĩnh của B.

Không phải mọi dependency đều có cùng mức độ gắn kết. Hai lớp có thể phụ thuộc lẫn nhau sâu về logic hoặc chỉ phụ thuộc một hợp đồng nhỏ.

### 3.1. Một ví dụ phụ thuộc chặt vào lớp cụ thể

Giả sử `RegistrationService` chịu trách nhiệm đăng ký người dùng và gửi lời chào:

~~~java
public class RegistrationService {
    public void register(String email) {
        // Giả lập phần đăng ký thành công.
        ConsoleNotificationSender sender = new ConsoleNotificationSender();
        sender.send(email, "Welcome!");
    }
}
~~~

Đồ thị phụ thuộc:

~~~text
RegistrationService
        │
        │ tự new và gọi
        ▼
ConsoleNotificationSender
~~~

Điều này có thể chấp nhận được trong chương trình rất nhỏ, nhưng có những bất lợi khi hệ thống lớn lên:

1. `RegistrationService` biết rõ class gửi thông báo cụ thể.
2. Muốn chuyển từ console sang email, ta phải sửa `RegistrationService`.
3. Muốn kiểm thử mà không tạo tác động gửi thật, ta khó thay thế thành phần gửi.
4. Nếu `ConsoleNotificationSender` cần URL, token, connection pool hoặc một dependency khác, service đăng ký bị kéo vào trách nhiệm khởi tạo chuỗi đối tượng ấy.

Các vấn đề này thường được gọi là **tight coupling** (kết dính chặt). Chúng không bắt nguồn từ `new` là “sai”, mà từ việc đặt quyết định về hạ tầng cụ thể vào phần mã nghiệp vụ không nên biết chi tiết đó.

### 3.2. Phụ thuộc vào interface và nhận đối tượng từ bên ngoài

Có thể thiết kế lại `RegistrationService.java` như sau:

~~~java
import java.util.Objects;

public class RegistrationService {
    private final NotificationSender notificationSender;

    public RegistrationService(NotificationSender notificationSender) {
        this.notificationSender =
                Objects.requireNonNull(notificationSender, "notificationSender");
    }

    public void register(String email) {
        // Giả lập phần đăng ký thành công.
        notificationSender.send(email, "Welcome!");
    }
}
~~~

Lúc này `RegistrationService` chỉ biết hợp đồng `NotificationSender`. Nó không cần biết thông báo được gửi qua console, email hay một kênh khác.

Ở bên ngoài, ta kết nối các đối tượng:

~~~java
public class Main {
    public static void main(String[] args) {
        NotificationSender sender = new ConsoleNotificationSender();
        RegistrationService service = new RegistrationService(sender);

        service.register("lan@example.com");
    }
}
~~~

Kết quả:

~~~text
[To: lan@example.com] Welcome!
~~~

Đây là **constructor injection** thực hiện bằng Java thuần: dependency được đưa vào qua constructor của đối tượng cần sử dụng.

~~~mermaid
flowchart TD
    M["Main: nơi lắp ghép đối tượng"] -->|tạo| C["ConsoleNotificationSender"]
    M -->|tạo với dependency| R["RegistrationService"]
    R -->|phụ thuộc hợp đồng| I["NotificationSender (interface)"]
    C -.->|implements| I
~~~

Quan hệ `RegistrationService -> NotificationSender` vẫn là một **dependency**. Dependency Injection không xóa dependency; nó làm rõ dependency và đưa quyền quyết định đối tượng cụ thể sang bên ngoài.

Cùng `RegistrationService` ấy có thể dùng cách triển khai khác:

~~~java
NotificationSender sender = new SilentNotificationSender();
RegistrationService service = new RegistrationService(sender);
service.register("lan@example.com");
~~~

Không cần chỉnh sửa code của `RegistrationService`.

### 3.3. Ai phải chịu trách nhiệm tạo và nối đối tượng?

Trong chương trình Java thuần ở ví dụ trên, `Main` đóng vai trò **composition root**: nơi tạo các đối tượng và nối các dependency để hình thành ứng dụng.

Đây là một ý tưởng thiết kế quan trọng: quyết định “dùng cách triển khai nào” có thể tập trung tại điểm khởi tạo, trong khi lớp nghiệp vụ chỉ nhận những thứ nó cần.

Nếu `RegistrationService` lại phụ thuộc `CustomerRepository` và `PasswordEncoder`, constructor sẽ cho thấy rõ các nhu cầu đó:

~~~java
public RegistrationService(
        CustomerRepository customerRepository,
        PasswordEncoder passwordEncoder,
        NotificationSender notificationSender) {
    // Lưu các dependency để dùng trong những phương thức nghiệp vụ.
}
~~~

Đoạn trên chỉ minh họa chữ ký constructor; `CustomerRepository` và `PasswordEncoder` là các kiểu giả định, chưa được định nghĩa trong ví dụ chạy ở phần trước.

Việc một constructor cần quá nhiều dependency có thể là dấu hiệu class đang đảm nhận quá nhiều trách nhiệm. Tuy nhiên, không có một con số tuyệt đối áp dụng được cho mọi ứng dụng.

## 4. Phân biệt các quan hệ giữa class và object

Người học thường nhầm “class A biết class B” với “A là một loại B”, hoặc nhầm mọi mối quan hệ tham chiếu đều là kế thừa. Những mối quan hệ sau có ý nghĩa khác nhau.

| Quan hệ | Câu hỏi dễ nhớ | Minh họa |
| --- | --- | --- |
| **Inheritance** | A có phải là một dạng của B? | `Dog extends Animal` |
| **Interface implementation** | A có thực hiện hợp đồng B? | `EmailSender implements NotificationSender` |
| **Association** | Một đối tượng A có liên hệ/giữ tham chiếu đến đối tượng B? | `Order` biết `Customer` của đơn hàng |
| **Aggregation** | A chứa hoặc tập hợp B nhưng B có thể tồn tại độc lập? | `Team` có nhiều `Member` tồn tại ngoài team |
| **Composition** | A sở hữu thành phần B với vòng đời gắn chặt về mặt mô hình? | `Order` sở hữu các `OrderLine` của nó |
| **Dependency / uses** | A cần dùng B để thực hiện một hành vi? | `RegistrationService` dùng `NotificationSender` |

### 4.1. Kế thừa `extends`: quan hệ “is-a”

Ví dụ:

~~~java
class Animal {
    void sleep() {
        System.out.println("Sleeping");
    }
}

class Dog extends Animal {
    void bark() {
        System.out.println("Woof");
    }
}
~~~

`Dog` là một kiểu con của `Animal`, vì thế đối tượng `Dog` có thể được tham chiếu bởi biến kiểu `Animal`:

~~~java
Animal animal = new Dog();
animal.sleep();
~~~

Kế thừa giúp xây dựng quan hệ kiểu và tái sử dụng một phần hành vi, nhưng cũng tạo sự phụ thuộc vào cấu trúc lớp cha. Không nên dùng `extends` chỉ vì hai class có một vài dòng code giống nhau.

### 4.2. Triển khai `implements`: “thực hiện hợp đồng”

~~~java
interface Printable {
    void print();
}

class Invoice implements Printable {
    @Override
    public void print() {
        System.out.println("Printing invoice");
    }
}
~~~

`Invoice` thực hiện hợp đồng `Printable`. Một class có thể đồng thời triển khai nhiều interface nếu các hợp đồng đó đều phù hợp với vai trò của nó.

### 4.3. Association: có liên hệ đến một đối tượng khác

~~~java
class Order {
    private final Customer customer;

    Order(Customer customer) {
        this.customer = customer;
    }
}
~~~

`Order` giữ tham chiếu đến `Customer`. Hai đối tượng có thể tồn tại độc lập; việc đơn hàng bị loại bỏ không nhất thiết làm khách hàng biến mất.

Đây là một **association**: quan hệ cấu trúc giữa các đối tượng. Mối quan hệ đó cũng tạo ra một dạng phụ thuộc trong mã nguồn.

### 4.4. Composition: cấu thành từ thành phần được sở hữu

~~~java
import java.util.ArrayList;
import java.util.List;

class Order {
    private final List<OrderLine> lines = new ArrayList<>();

    void addLine(String sku, int quantity) {
        lines.add(new OrderLine(sku, quantity));
    }

    List<OrderLine> getLines() {
        return List.copyOf(lines);
    }
}

record OrderLine(String sku, int quantity) {
}
~~~

Ví dụ mô hình hóa `Order` là chủ sở hữu các dòng hàng của nó: dòng hàng được tạo và quản lý trong phạm vi đơn hàng, và danh sách trả ra là bản sao không cho phép thay đổi cấu trúc trực tiếp. Trong thiết kế domain, dòng hàng riêng lẻ thường không mang ý nghĩa độc lập sau khi đơn hàng bị xóa.

Khái niệm composition nói về **sở hữu và vòng đời theo mô hình thiết kế**; Java không tự động xóa đối tượng B đúng lúc A không còn tồn tại. Bộ gom rác (garbage collector) thu hồi bộ nhớ theo khả năng truy cập, không theo ký hiệu UML.

### 4.5. Aggregation: tập hợp không sở hữu hoàn toàn

~~~java
import java.util.List;

class Team {
    private final List<Customer> members;

    Team(List<Customer> members) {
        this.members = List.copyOf(members);
    }
}
~~~

Trong một mô hình phù hợp, `Team` tập hợp các `Customer` làm thành viên nhưng không sở hữu vòng đời của họ. Một thành viên có thể tồn tại hoặc tham gia nhóm khác ngay cả khi `Team` bị xóa.

Trong Java, association, aggregation và composition **có thể đều dùng field tham chiếu**. Điểm phân biệt nằm ở ý nghĩa nghiệp vụ và quy tắc sở hữu; chỉ nhìn kiểu `List<Customer>` thường không đủ để xác định chính xác.

### 4.6. Dependency là quan hệ rộng hơn việc giữ field

~~~java
class ReceiptPrinter {
    void printReceipt(Order order) {
        System.out.println("Order: " + order);
    }
}
~~~

`ReceiptPrinter` sử dụng `Order` làm tham số nên phụ thuộc vào kiểu `Order`, dù không lưu `Order` trong field.

Tương tự, một lớp dùng `LocalDate.now()` phụ thuộc vào API `LocalDate` tại vị trí gọi. Không phải dependency nào cũng cần đưa qua constructor; ta ưu tiên injection cho những cộng tác viên cần thay thế, quản lý vòng đời hoặc kiểm soát hành vi ở ranh giới có ý nghĩa.

## 5. Dependency Injection và Inversion of Control có quan hệ gì?

Hai thuật ngữ thường đi cùng Spring nhưng không đồng nghĩa.

**Dependency Injection (DI)** là kỹ thuật một đối tượng nhận dependency từ nơi khác thay vì tự chọn và tự tạo mọi dependency của mình.

**Inversion of Control (IoC)** là ý tưởng rộng hơn: một phần quyền điều phối hoặc khởi tạo được chuyển sang thành phần bên ngoài, chẳng hạn một container. Spring IoC container quản lý việc tạo và kết nối nhiều đối tượng ứng dụng, gọi chúng là **bean**.

### 5.1. Ba cách cung cấp dependency phổ biến

**Constructor injection**

~~~java
class ReportService {
    private final ReportRepository repository;

    ReportService(ReportRepository repository) {
        this.repository = repository;
    }
}
~~~

Dùng khi dependency bắt buộc để đối tượng hoạt động. Có thể giữ field `final` và biểu diễn rõ những gì class cần ngay lúc tạo.

**Setter injection**

~~~java
class ReportService {
    private AuditLogger auditLogger;

    void setAuditLogger(AuditLogger auditLogger) {
        this.auditLogger = auditLogger;
    }
}
~~~

Có thể phù hợp khi dependency là tùy chọn hoặc được thay đổi có chủ đích trong vòng đời đối tượng. Cần thiết kế rõ trường hợp chưa được gán và cân nhắc khả năng thay đổi trạng thái trong runtime.

**Method parameter injection**

~~~java
class ReportService {
    void generateReport(ReportRepository repository) {
        // Dùng repository cho riêng lần gọi này.
    }
}
~~~

Dependency được cung cấp trong từng lời gọi. Phù hợp khi cộng tác viên chỉ cần cho một thao tác nhất định, hoặc khi phụ thuộc thực sự thay đổi theo từng lần thực thi.

`ReportRepository` và `AuditLogger` trong ba đoạn trên là kiểu giả định để minh họa hình thức truyền dependency. Các đoạn chỉ tập trung vào thiết kế quan hệ, không phải ví dụ biên dịch độc lập.

Trong ứng dụng Spring thông dụng, **constructor injection** là lựa chọn dễ hiểu cho các dependency bắt buộc vì đối tượng không thể được tạo hợp lệ nếu thiếu chúng. Spring cũng hỗ trợ cách tiêm qua setter, field và một số cơ chế khác, nhưng field injection có thể che giấu dependency khi khởi tạo class bằng Java thuần.

### 5.2. Dependency Inversion Principle (DIP) khác DI

DIP là một nguyên lý thiết kế: phần logic ở cấp cao nên phụ thuộc vào các abstraction phù hợp, thay vì ràng buộc trực tiếp với chi tiết triển khai ở cấp thấp. Abstraction ấy không nên bị thiết kế chỉ để phục vụ một implementation cụ thể.

Trong ví dụ:

~~~text
           RegistrationService
           (nghiệp vụ đăng ký)
                    │
                    ▼
       NotificationSender (interface)
                    ▲
                    │
       ConsoleNotificationSender
           (chi tiết gửi)
~~~

`RegistrationService` phụ thuộc vào **hợp đồng** `NotificationSender`, trong khi `ConsoleNotificationSender` thực hiện hợp đồng đó. DI là **cách cung cấp** một implementation cho service.

Có thể dùng DI mà vẫn phụ thuộc lớp cụ thể:

~~~java
class RegistrationService {
    RegistrationService(ConsoleNotificationSender sender) {
        // Vẫn nhận từ ngoài, nhưng phụ thuộc lớp cụ thể.
    }
}
~~~

Do đó, **DI không tự động bảo đảm DIP**. Hai ý tưởng thường bổ sung cho nhau: DIP giúp thiết kế ranh giới phụ thuộc hợp lý, DI giúp nối các đối tượng tại runtime.

## 6. Từ Java thuần đến Spring Boot: ai tạo và kết nối đối tượng?

Đến đây, `Main` đang trực tiếp tạo các dependency:

~~~java
NotificationSender sender = new ConsoleNotificationSender();
RegistrationService service = new RegistrationService(sender);
~~~

Cách làm này hợp lệ và phù hợp với ứng dụng nhỏ. Khi có hàng chục controller, service, repository và cấu hình, việc quản lý toàn bộ đồ thị đối tượng bằng tay dễ trở nên lặp lại. Spring giải quyết phần việc đó thông qua **IoC container**.

Spring Boot giúp khởi động và cấu hình Spring application context thuận tiện hơn. Các annotation mô tả component và constructor làm rõ quan hệ phụ thuộc để container có thể tạo bean và kết nối chúng.

### 6.1. Ví dụ Spring Boot tối thiểu

Giả sử một dự án Spring Boot 3.x có dependency `spring-boot-starter-web` và các file dưới package `com.example.registration`:

~~~text
src/main/java/com/example/registration/
├── RegistrationApplication.java
├── NotificationSender.java
├── ConsoleNotificationSender.java
├── RegistrationService.java
└── RegistrationController.java
~~~

**File `RegistrationApplication.java`**

~~~java
package com.example.registration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RegistrationApplication {
    public static void main(String[] args) {
        SpringApplication.run(RegistrationApplication.class, args);
    }
}
~~~

**File `NotificationSender.java`**

~~~java
package com.example.registration;

public interface NotificationSender {
    void send(String recipient, String message);
}
~~~

**File `ConsoleNotificationSender.java`**

~~~java
package com.example.registration;

import org.springframework.stereotype.Component;

@Component
public class ConsoleNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println("Notify " + recipient + ": " + message);
    }
}
~~~

**File `RegistrationService.java`**

~~~java
package com.example.registration;

import org.springframework.stereotype.Service;

@Service
public class RegistrationService {
    private final NotificationSender notificationSender;

    public RegistrationService(NotificationSender notificationSender) {
        this.notificationSender = notificationSender;
    }

    public String register(String email) {
        notificationSender.send(email, "Welcome!");
        return "Registered: " + email;
    }
}
~~~

**File `RegistrationController.java`**

~~~java
package com.example.registration;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/registrations")
public class RegistrationController {
    private final RegistrationService registrationService;

    public RegistrationController(RegistrationService registrationService) {
        this.registrationService = registrationService;
    }

    @PostMapping
    public ResponseEntity<String> register(@RequestParam String email) {
        return ResponseEntity.ok(registrationService.register(email));
    }
}
~~~

Khi ứng dụng chạy, có thể gọi:

~~~bash
curl -X POST "http://localhost:8080/registrations?email=lan%40example.com"
~~~

Phản hồi mẫu:

~~~text
Registered: lan@example.com
~~~

Console của ứng dụng xuất hiện:

~~~text
Notify lan@example.com: Welcome!
~~~

Ví dụ này chỉ minh họa **quá trình nối các đối tượng**. Nó chưa lưu đăng ký, kiểm tra email, thực sự gửi thư hay xây dựng API production.

### 6.2. Spring thực hiện điều gì khi khởi động?

Từ package chứa lớp `@SpringBootApplication`, cơ chế component scan mặc định phát hiện các loại component phù hợp trong package đó và package con. Trong ví dụ:

1. `@Component` đánh dấu `ConsoleNotificationSender` là ứng viên bean.
2. `@Service` đánh dấu `RegistrationService` là ứng viên bean, đồng thời thể hiện ý nghĩa thuộc lớp dịch vụ.
3. `@RestController` đánh dấu `RegistrationController` là web component.
4. Khi tạo `RegistrationService`, Spring thấy constructor cần `NotificationSender`, tìm bean tương thích và cung cấp `ConsoleNotificationSender`.
5. Khi tạo `RegistrationController`, Spring cung cấp bean `RegistrationService`.
6. Spring MVC sử dụng controller để xử lý request đến `POST /registrations`.

~~~mermaid
flowchart TD
    A["Spring ApplicationContext"] -->|tạo/quản lý| B["ConsoleNotificationSender"]
    A -->|tạo và inject NotificationSender| C["RegistrationService"]
    A -->|tạo và inject RegistrationService| D["RegistrationController"]
    D -->|gọi| C
    C -->|gọi qua interface| E["NotificationSender"]
    B -.->|implements| E
~~~

Điểm cần hiểu là **Spring quản lý bean của ứng dụng**, chứ không nhất thiết quản lý mọi đối tượng Java. Một đối tượng được tự tạo bằng `new` ở nơi khác không mặc nhiên trở thành Spring bean.

Ví dụ:

~~~java
RegistrationService service =
        new RegistrationService(new ConsoleNotificationSender());
~~~

Đây vẫn là Java hợp lệ, nhưng `service` được tạo thủ công và không tự động được container quản lý. Việc gọi constructor trực tiếp cũng không kích hoạt toàn bộ cơ chế lifecycle hoặc các xử lý do Spring thực hiện cho bean do nó quản lý.

### 6.3. Tại sao không cần `@Autowired` trên constructor ở ví dụ này?

Khi một Spring bean chỉ có **một constructor**, Spring có thể sử dụng constructor đó để thực hiện injection mà không cần viết `@Autowired`. Vì thế:

~~~java
@Service
public class RegistrationService {
    private final NotificationSender sender;

    public RegistrationService(NotificationSender sender) {
        this.sender = sender;
    }
}
~~~

là cách viết phổ biến và rõ ràng.

Nếu có nhiều constructor hoặc trường hợp lựa chọn bean phức tạp, cần xét quy tắc lựa chọn constructor và có thể dùng annotation, tên bean hoặc cấu hình bổ sung. Điều quan trọng là dependency bắt buộc xuất hiện rõ trong chữ ký constructor.

## 7. Nếu có nhiều lớp cùng triển khai một interface thì sao?

Giả sử ứng dụng đăng ký thêm:

~~~java
package com.example.registration;

import org.springframework.stereotype.Component;

@Component
public class LoggingNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println("[LOG] " + recipient + ": " + message);
    }
}
~~~

Bây giờ context có thể có **hai bean** cùng tương thích với `NotificationSender`:

~~~text
NotificationSender
       ▲
       ├── ConsoleNotificationSender  (@Component)
       └── LoggingNotificationSender  (@Component)
~~~

Khi `RegistrationService` yêu cầu duy nhất một `NotificationSender`, container phải xác định dùng bean nào. Nếu không có quy tắc nào giải quyết sự nhập nhằng, Spring có thể báo lỗi vì có nhiều candidate phù hợp.

Một số cách thiết kế:

### Cách 1: Chỉ đăng ký đúng implementation đang cần

Nếu một ứng dụng chỉ gửi qua console, không cần tạo thêm `LoggingNotificationSender` thành bean. Điều này làm đồ thị dependency đơn giản và dễ đọc.

### Cách 2: Dùng `@Qualifier` để chọn bean có chủ đích

~~~java
package com.example.registration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class RegistrationService {
    private final NotificationSender sender;

    public RegistrationService(
            @Qualifier("consoleNotificationSender") NotificationSender sender) {
        this.sender = sender;
    }

    public String register(String email) {
        sender.send(email, "Welcome!");
        return "Registered: " + email;
    }
}
~~~

Theo quy ước đặt tên bean khi dùng component scan thông thường, `ConsoleNotificationSender` có tên mặc định `consoleNotificationSender`. `@Qualifier` giúp chọn đúng candidate mang qualifier đó.

### Cách 3: Dùng `@Primary` để khai báo lựa chọn ưu tiên

~~~java
@Component
@Primary
public class ConsoleNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println("Notify " + recipient + ": " + message);
    }
}
~~~

Ví dụ giả định file đã có package và import cần thiết cho `@Component`, `@Primary`.

`@Primary` làm bean này được ưu tiên khi có nhiều candidate phù hợp và không có chỉ định cụ thể hơn. Cách chọn phải phản ánh nhu cầu thực tế; không nên đánh dấu mọi implementation là primary.

Nếu bạn **thực sự cần tất cả implementation**, Spring cũng có thể inject một collection như `List<NotificationSender>`. Đây là một mô hình thiết kế khác với yêu cầu chọn một implementation.

## 8. Phạm vi sống của đối tượng và ý nghĩa của state

Khi tự viết:

~~~java
Customer a = new Customer("Lan");
Customer b = new Customer("Minh");
~~~

ta chủ động tạo hai đối tượng. Với Spring, container có thể quản lý vòng đời bean theo **scope**.

Scope mặc định phổ biến của Spring bean là **singleton trong phạm vi một Spring application context**. Nghĩa là container thường tạo một instance của bean đó và sử dụng lại khi các bean khác yêu cầu dependency tương ứng. “Singleton của Spring” không nên bị hiểu thành “chỉ có đúng một instance của class trong toàn bộ JVM ở mọi application context”.

Điều này quan trọng với class có trạng thái thay đổi:

~~~java
@Service
public class CounterService {
    private int count;

    public int increase() {
        return ++count;
    }
}
~~~

Trong một ứng dụng web xử lý nhiều request đồng thời, `count` của singleton bean là **trạng thái dùng chung**; thao tác `++count` không an toàn trước truy cập đồng thời. Ví dụ này minh họa rủi ro, không nên dùng làm bộ đếm request production.

Ngược lại, một service chỉ chứa dependency và các biến cục bộ trong method thường dễ kiểm soát hơn:

~~~java
@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Một dependency được inject không mặc định là đối tượng mới cho mỗi HTTP request. Cần hiểu scope, tính thay đổi của state, thread safety và vòng đời thực tế khi thiết kế.

## 9. Những lỗi tư duy thường gặp

### 9.1. “Thêm `@Service` vào class là mọi nơi gọi `new` đều được inject”

Không đúng. Container chỉ thực hiện injection cho đối tượng được nó quản lý theo cơ chế áp dụng. Nếu gọi `new` thủ công rồi mong field được `@Autowired` tự lấp đầy, bạn có thể nhận `null` hoặc gặp lỗi sử dụng dependency.

Cách ổn định là để Spring quản lý các bean cần injection và truyền dependency qua constructor.

### 9.2. “Class A có field kiểu B thì A chắc chắn sở hữu vòng đời của B”

Không. `RegistrationService` có field kiểu `NotificationSender` nhưng chính Spring context có thể quản lý sender. Giữ tham chiếu không đồng nghĩa sở hữu hoặc phải tự tạo/hủy đối tượng đó.

### 9.3. “Có interface thì mã chắc chắn ít phụ thuộc”

Không hẳn. Nếu interface quá lớn hoặc chứa các chi tiết riêng của implementation, mã sử dụng vẫn bị phụ thuộc đáng kể. Một interface tốt diễn tả **khả năng cần thiết với người sử dụng**, tránh ép mọi implementation gánh các method không liên quan.

Ví dụ một `NotificationSender` chỉ cần `send` sẽ dễ sử dụng hơn interface yêu cầu cả những hàm như `connectToSmtpServer`, `flushKafkaTopic` và `openDesktopWindow` cho mọi implementation.

### 9.4. “Có dependency vòng thì cứ inject qua field hoặc setter là xong”

Ví dụ:

~~~text
ServiceA → ServiceB → ServiceA
~~~

Đây là **circular dependency**. Với constructor injection, không thể khởi tạo cả hai theo chuỗi bình thường nếu mỗi bean đều bắt buộc nhận bean kia. Spring Boot ở các dòng hiện đại mặc định không khuyến khích và thường từ chối loại vòng phụ thuộc này.

Đổi cách inject để qua mặt triệu chứng thường che giấu vấn đề thiết kế. Nên xem lại trách nhiệm giữa A và B, tách phần logic chung, hoặc đưa orchestration lên một thành phần khác khi phù hợp.

### 9.5. “Dùng interface nghĩa là phải dùng Spring”

Không. Toàn bộ ví dụ `NotificationSender` và `RegistrationService` ban đầu là Java thuần. Spring không phát minh ra interface, đa hình hoặc DI. Spring cung cấp container và quy tắc cấu hình để **quản lý việc tạo và kết nối đối tượng** trên quy mô ứng dụng.

### 9.6. “Mỗi dependency đều cần tạo interface riêng”

Không có quy tắc đó. Có thể injection một class cụ thể khi chưa tồn tại nhiều implementation hay ranh giới abstraction có ý nghĩa. Đừng thiết kế interface hình thức chỉ để tên interface trùng với tên implementation.

Ưu tiên tính rõ ràng của trách nhiệm, khả năng thay thế ở ranh giới cần thiết và nhu cầu kiểm thử thực tế.

## 10. Đọc đồ thị phụ thuộc trong một ứng dụng Spring Boot

Xét một ứng dụng xử lý đơn hàng với các thành phần:

~~~text
OrderController
       │
       ▼
OrderService
       │
       ├──► OrderRepository (interface)
       │           ▲
       │           │ implements
       │           │
       │       JpaOrderRepository
       │
       └──► PaymentGateway (interface)
                   ▲
                   │ implements
                   │
             CardPaymentGateway
~~~

Cách đọc:

- Controller nhận request và gọi service; controller **phụ thuộc** service.
- Service triển khai quy tắc đặt hàng và cần khả năng lưu đơn, thanh toán.
- Repository và payment gateway là các **abstraction** mô tả khả năng cần dùng.
- Những lớp triển khai cung cấp cách làm cụ thể.
- Spring có thể tạo các bean và truyền implementation cho service nếu chúng được đăng ký, đủ điều kiện và giải quyết được việc lựa chọn candidate.

Sơ đồ này là mô hình thiết kế minh họa; `JpaOrderRepository` và `CardPaymentGateway` không phải class được Spring Boot tự sinh ra theo tên.

Khi đọc constructor sau:

~~~java
public OrderService(
        OrderRepository orderRepository,
        PaymentGateway paymentGateway) {
    this.orderRepository = orderRepository;
    this.paymentGateway = paymentGateway;
}
~~~

bạn có thể suy ra ngay: `OrderService` cần hai cộng tác viên để hoạt động. Còn việc hệ thống đang dùng MySQL, PostgreSQL, cổng thanh toán giả lập hay cổng thực tế phụ thuộc vào những implementation được lắp ghép bên ngoài.

Việc **đọc constructor và kiểu tham số** thường là bước đầu hữu ích nhất để hiểu một class Spring Boot liên hệ với các thành phần khác.

## 11. Thực hành từng bước

### Bài tập A: Nhận diện class và object

Cho đoạn mã:

~~~java
Customer a = new Customer("Lan");
Customer b = a;
Customer c = new Customer("Lan");

b.earnPoints(15);
~~~

Hãy xác định:

1. Có bao nhiêu đối tượng `Customer` được tạo?
2. `a.getRewardPoints()` bằng bao nhiêu?
3. `c.getRewardPoints()` bằng bao nhiêu?
4. Vì sao `a` và `c` có cùng tên nhưng không phải cùng một object?

**Gợi ý giải:** Có hai lệnh `new` nên tạo hai đối tượng; `b` tham chiếu cùng đối tượng với `a`. Điểm của `a` là 15, còn `c` là 0. Giá trị tên bằng nhau không quyết định hai biến tham chiếu cùng một đối tượng.

### Bài tập B: Thay implementation mà không sửa service

Từ ví dụ Java thuần ở phần 3, thêm một class:

~~~java
public class PrefixNotificationSender implements NotificationSender {
    @Override
    public void send(String recipient, String message) {
        System.out.println("NOTICE: " + recipient + " - " + message);
    }
}
~~~

Sửa điểm khởi tạo:

~~~java
NotificationSender sender = new PrefixNotificationSender();
RegistrationService service = new RegistrationService(sender);
service.register("minh@example.com");
~~~

Hãy thử giải thích vì sao chỉ cần đổi **đối tượng được truyền vào constructor** mà không cần thay đổi phương thức `RegistrationService.register`.

**Gợi ý:** Service chỉ biết interface `NotificationSender` và gọi `send`. Cách xử lý cụ thể phụ thuộc đối tượng triển khai được truyền vào.

### Bài tập C: Phân loại quan hệ

Với từng mô tả, hãy xác định quan hệ phù hợp nhất:

| Tình huống | Gợi ý đáp án |
| --- | --- |
| `Bird extends Animal` | Inheritance |
| `SmsSender implements NotificationSender` | Interface implementation |
| `CheckoutService` gọi `PaymentGateway.charge(...)` | Dependency |
| `Order` sở hữu các `OrderLine` của chính nó | Composition theo mô hình nghiệp vụ |
| `Team` chứa những `Member` vẫn tồn tại nếu team bị xóa | Aggregation theo mô hình nghiệp vụ |

Lưu ý: một đoạn mã có thể đồng thời thể hiện nhiều loại liên hệ. Ví dụ `Order` giữ tham chiếu đến các dòng hàng nên có quan hệ cấu trúc, đồng thời phụ thuộc vào kiểu `OrderLine` trong mã nguồn.

### Bài tập D: Dự đoán lỗi injection

Một dự án Spring có hai bean:

~~~java
@Component
class EmailSender implements NotificationSender {
    public void send(String recipient, String message) {
        // ...
    }
}

@Component
class SmsSender implements NotificationSender {
    public void send(String recipient, String message) {
        // ...
    }
}
~~~

Trong khi service cần:

~~~java
@Service
class RegistrationService {
    RegistrationService(NotificationSender sender) {
        // ...
    }
}
~~~

Điều gì có thể xảy ra khi khởi động? Hãy nêu hai hướng xử lý.

**Gợi ý:** Nếu có nhiều bean hợp lệ mà Spring không xác định được một candidate duy nhất, việc tạo bean có thể thất bại. Có thể đăng ký một implementation phù hợp, sử dụng `@Qualifier` hoặc `@Primary` theo quy tắc lựa chọn cụ thể.

## 12. Những điều cần nắm trước khi học sâu Spring Boot

Trong Java, **class** định nghĩa khả năng và trạng thái của đối tượng, còn **interface** diễn tả hợp đồng. Một đối tượng có thể cộng tác với đối tượng khác bằng cách giữ tham chiếu, nhận qua constructor hoặc sử dụng trong lời gọi method. Những mối quan hệ này hình thành một **đồ thị dependency**.

Khi thiết kế ứng dụng, ta muốn dependency rõ ràng, đúng trách nhiệm và đủ linh hoạt để thay đổi phần triển khai. **Constructor injection** làm các dependency bắt buộc lộ rõ ngay tại điểm khởi tạo. **Dependency inversion** giúp hướng phần nghiệp vụ đến các abstraction phù hợp. Hai cách tiếp cận kết hợp giúp mã dễ mở rộng và kiểm thử hơn khi hệ thống phát triển.

Spring Boot dùng Spring IoC container để làm việc tạo và lắp ghép nhiều bean theo cấu hình ứng dụng. Vì vậy, khi gặp `@Service`, `@Repository`, `@Component`, `@RestController` hoặc một constructor nhận các kiểu khác, hãy đọc chúng như những dấu hiệu cho biết **đối tượng nào đảm nhiệm trách nhiệm gì và cần cộng tác với những đối tượng nào**. Hiểu được điều đó là nền tảng để học tiếp Spring IoC, Dependency Injection, bean lifecycle, auto-configuration và kiến trúc ứng dụng Spring Boot.

