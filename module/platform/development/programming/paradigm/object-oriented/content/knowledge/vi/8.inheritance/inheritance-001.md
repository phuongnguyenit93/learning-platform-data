# Lớp cha, lớp con và quan hệ kế thừa trong Java OOP

**Kế thừa (inheritance)** cho phép một lớp mới **mở rộng hoặc chuyên biệt hóa** một lớp đã có. Trong quan hệ này, lớp được kế thừa gọi là **lớp cha** (*superclass/parent class*), lớp kế thừa gọi là **lớp con** (*subclass/child class*). Java dùng từ khóa `extends` để khai báo quan hệ kế thừa giữa hai lớp.

Kế thừa hữu ích khi các đối tượng thuộc những loại cụ thể khác nhau nhưng có **bản chất chung** và tuân thủ cùng một hợp đồng hành vi. Ví dụ, nhân viên hưởng lương cố định và nhân viên hưởng lương theo giờ đều là **nhân viên**, có mã, tên và có thể tính lương, nhưng công thức tính lương khác nhau.

Điểm quyết định không chỉ là giảm mã lặp. Kế thừa thiết lập một quan hệ **is-a**: một đối tượng thuộc lớp con phải có thể được sử dụng ở nơi chương trình kỳ vọng đối tượng thuộc lớp cha mà vẫn tôn trọng hợp đồng của lớp cha.

## 1. Nhận diện lớp cha và lớp con

Ví dụ ngắn:

~~~java
class Vehicle {
    void start() {
        System.out.println("Khởi động phương tiện");
    }
}

class Car extends Vehicle {
    void openTrunk() {
        System.out.println("Mở cốp xe");
    }
}
~~~

~~~java
Car car = new Car();
car.start();     // Phương thức kế thừa từ Vehicle
car.openTrunk(); // Phương thức riêng của Car

Vehicle vehicle = car; // Hợp lệ: Car là một Vehicle
vehicle.start();       // Hợp lệ
// vehicle.openTrunk(); // Không biên dịch: Vehicle không khai báo phương thức này
~~~

Ở đây:

- `Vehicle` là **superclass** của `Car`.
- `Car` là **subclass** của `Vehicle`.
- `Car extends Vehicle` mang ý nghĩa “`Car` là một loại `Vehicle`”.
- `Car` có thể dùng hành vi được kế thừa và tự bổ sung hành vi riêng.
- Biến tham chiếu `Vehicle` có thể trỏ đến một instance `Car`. Compiler quyết định **phương thức được phép gọi** dựa vào kiểu khai báo của biến; với instance method được override, runtime quyết định **triển khai nào chạy** theo kiểu thực tế của đối tượng.

Sơ đồ quan hệ giữa các kiểu:

~~~mermaid
classDiagram
    class Vehicle {
        +start() void
    }
    class Car {
        +openTrunk() void
    }
    Vehicle <|-- Car
~~~

Mũi tên tam giác rỗng chỉ từ **lớp con tới lớp cha**. Nó biểu diễn quan hệ kế thừa giữa *kiểu*, không phải hai đối tượng riêng biệt cùng tồn tại mỗi khi gọi `new Car()`.

## 2. Ví dụ thực tế: tính lương với hai loại nhân viên

Yêu cầu:

- Nhân viên nào cũng có mã định danh và họ tên.
- Nhân viên **hưởng lương cố định** có lương tháng.
- Nhân viên **hưởng lương theo giờ** có đơn giá giờ và số giờ làm.
- Hệ thống in phiếu lương mà không phải liên tục viết `if` kiểm tra nhân viên thuộc loại nào.

Thiết kế:

~~~mermaid
classDiagram
    class Employee {
        <<abstract>>
        -id String
        -fullName String
        +getId() String
        +getFullName() String
        +role() String
        +monthlyPay() BigDecimal*
        +printPayslip() void
    }
    class SalariedEmployee {
        -fixedSalary BigDecimal
        +role() String
        +monthlyPay() BigDecimal
    }
    class HourlyEmployee {
        -hourlyRate BigDecimal
        -hoursWorked int
        +role() String
        +monthlyPay() BigDecimal
    }
    Employee <|-- SalariedEmployee
    Employee <|-- HourlyEmployee
~~~

Trong bài này, `Employee` là **lớp cha trừu tượng** vì một “nhân viên chung chung” chưa có công thức tính lương cụ thể. Hai lớp con hoàn thiện phần đó.

### Mã Java chạy độc lập

Lưu toàn bộ đoạn sau vào `InheritanceDemo.java` (Java 11+):

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

public class InheritanceDemo {

    static abstract class Employee {
        private final String id;
        private final String fullName;

        protected Employee(String id, String fullName) {
            this.id = requireText(id, "id");
            this.fullName = requireText(fullName, "fullName");
        }

        public final String getId() {
            return id;
        }

        public final String getFullName() {
            return fullName;
        }

        public String role() {
            return "Nhân viên";
        }

        // Mỗi loại nhân viên có công thức lương riêng.
        public abstract BigDecimal monthlyPay();

        // Quy trình chung không thay đổi giữa các lớp con.
        public final void printPayslip() {
            System.out.println(role() + " | " + id + " | "
                    + fullName + " | "
                    + monthlyPay().toPlainString());
        }

        private static String requireText(String text, String field) {
            String result = Objects.requireNonNull(
                    text, field).trim();
            if (result.isEmpty()) {
                throw new IllegalArgumentException(
                        field + " không được rỗng");
            }
            return result;
        }
    }

    static final class SalariedEmployee extends Employee {
        private final BigDecimal fixedSalary;

        SalariedEmployee(String id, String name,
                         BigDecimal fixedSalary) {
            super(id, name); // Khởi tạo phần Employee trước.
            Objects.requireNonNull(fixedSalary, "fixedSalary");
            if (fixedSalary.signum() < 0) {
                throw new IllegalArgumentException(
                        "Lương cố định không được âm");
            }
            this.fixedSalary = fixedSalary;
        }

        @Override
        public String role() {
            return "Toàn thời gian";
        }

        @Override
        public BigDecimal monthlyPay() {
            return fixedSalary;
        }
    }

    static final class HourlyEmployee extends Employee {
        private final BigDecimal hourlyRate;
        private final int hoursWorked;

        HourlyEmployee(String id, String name,
                       BigDecimal hourlyRate, int hoursWorked) {
            super(id, name);
            Objects.requireNonNull(hourlyRate, "hourlyRate");
            if (hourlyRate.signum() < 0 || hoursWorked < 0) {
                throw new IllegalArgumentException(
                        "Đơn giá và số giờ không được âm");
            }
            this.hourlyRate = hourlyRate;
            this.hoursWorked = hoursWorked;
        }

        @Override
        public String role() {
            return "Theo giờ";
        }

        @Override
        public BigDecimal monthlyPay() {
            return hourlyRate.multiply(
                    BigDecimal.valueOf(hoursWorked));
        }
    }

    public static void main(String[] args) {
        Employee a = new SalariedEmployee(
                "E001", "An", new BigDecimal("15000000"));
        Employee b = new HourlyEmployee(
                "E002", "Bình", new BigDecimal("75000"), 80);

        List<Employee> staff = List.of(a, b);

        for (Employee employee : staff) {
            employee.printPayslip();
        }

        System.out.println("Tổng lương: "
                + staff.stream()
                        .map(Employee::monthlyPay)
                        .reduce(BigDecimal.ZERO, BigDecimal::add)
                        .toPlainString());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac InheritanceDemo.java
java InheritanceDemo
~~~

Kết quả:

~~~text
Toàn thời gian | E001 | An | 15000000
Theo giờ | E002 | Bình | 6000000
Tổng lương: 21000000
~~~

Để tập trung vào kế thừa, chương trình minh họa chỉ tính lương cơ bản, chưa tính thuế, bảo hiểm, làm thêm giờ, kỳ lương hoặc tiền tệ đa quốc gia. Trong hệ thống thực, các quy tắc đó cần được mô hình hóa và xác thực theo nghiệp vụ.

### Phân tích trách nhiệm

| Thành phần | Điều gì được đặt ở đây? | Vì sao? |
| --- | --- | --- |
| `Employee` | `id`, `fullName`, kiểm tra dữ liệu chung, `printPayslip()` | Mọi nhân viên đều cần các dữ liệu/hành vi này |
| `Employee.monthlyPay()` | Khai báo phương thức trừu tượng | Mọi nhân viên phải tính được lương, công thức chưa thống nhất |
| `SalariedEmployee` | `fixedSalary`, cách tính lương cố định | Chỉ nhân viên hưởng lương cố định cần |
| `HourlyEmployee` | `hourlyRate`, `hoursWorked`, phép nhân | Chỉ nhân viên hưởng lương theo giờ cần |
| `List<Employee>` | Chứa các instance thuộc nhiều lớp con | Dùng chung API của lớp cha và đa hình |

Không có lệnh `new Employee()`: lớp `Employee` đang được khai báo `abstract` nên **không thể khởi tạo trực tiếp**. Nếu một lớp cha có hành vi đầy đủ và không khai báo `abstract`, nó có thể là lớp cụ thể và vẫn có lớp con.

## 3. Một đối tượng lớp con có gì từ lớp cha?

Một instance `HourlyEmployee` có trạng thái được khai báo bởi **cả chuỗi lớp cha và lớp con**:

- Phần từ `Employee`: `id`, `fullName`.
- Phần riêng của `HourlyEmployee`: `hourlyRate`, `hoursWorked`.
- Các phương thức được kế thừa/công khai như `getId()`, `getFullName()`, `printPayslip()`.
- Các phương thức được override như `role()`, `monthlyPay()`.

~~~mermaid
flowchart TB
    R["Một instance HourlyEmployee"]
    R --> A["Phần trạng thái Employee\nid, fullName"]
    R --> B["Phần trạng thái HourlyEmployee\nhourlyRate, hoursWorked"]
    R --> C["Hành vi được chọn\nmonthlyPay() của HourlyEmployee"]
~~~

Đây là sơ đồ **khái niệm**, không phải bản đồ vị trí bộ nhớ của JVM. Tạo một đối tượng lớp con không đồng nghĩa với tạo hai đối tượng độc lập (một `Employee` và một `HourlyEmployee`).

Field `private` của lớp cha **vẫn tồn tại trong trạng thái của instance**, nhưng lớp con không được truy cập trực tiếp bằng tên field. Thay vì `this.id` trong `HourlyEmployee`, ta sử dụng getter `getId()` của lớp cha.

### Tại sao `private` vẫn có ích trong kế thừa?

Nếu cho lớp con tùy ý gán `id`, một subclass có thể làm sai quy tắc mã nhân viên. `Employee` sở hữu invariant và cách kiểm tra dữ liệu chung. Việc để `id` là `private final` và chỉ công khai getter giúp lớp cha giữ quyền kiểm soát.

Quyền truy cập thường gặp:

| Mức truy cập ở thành viên lớp cha | Trong lớp con |
| --- | --- |
| `public` | Truy cập qua quy tắc public |
| `protected` | Có thể truy cập từ subclass; ngoài package có quy tắc giới hạn về biểu thức nhận |
| Không ghi modifier (package-private) | Chỉ có thể truy cập trực tiếp nếu ở cùng package |
| `private` | Không thể truy cập trực tiếp từ mã của subclass |

`protected` không phải “public dành cho lớp con trong mọi hoàn cảnh”; Java áp dụng quy tắc quyền truy cập tương đối cụ thể, nhất là khi subclass ở package khác. Thường nên giữ field `private` và cung cấp phương thức có chủ đích thay vì công khai toàn bộ trạng thái cho cây kế thừa.

## 4. Constructor lớp con khởi tạo phần trạng thái của cha

Constructor không phải phương thức kế thừa. Khi tạo `HourlyEmployee`, lời gọi `super(id, name)` chọn constructor `Employee` để thiết lập dữ liệu chung, rồi constructor con kiểm tra `hourlyRate` và `hoursWorked`:

~~~java
HourlyEmployee(String id, String name,
               BigDecimal hourlyRate, int hoursWorked) {
    super(id, name); // Gọi constructor Employee(String, String).
    // Kiểm tra, sau đó gán các trường riêng của HourlyEmployee.
}
~~~

Với Java 11, lời gọi `super(...)`/`this(...)` tường minh phải đứng đầu constructor. Nếu bỏ `super(...)`, compiler thử gọi `super()`; điều này chỉ hợp lệ nếu có constructor cha không tham số và truy cập được. `new HourlyEmployee(...)` vẫn tạo **một đối tượng duy nhất**, không tạo một `Employee` riêng.

Cần tránh gọi một phương thức có thể bị override từ constructor cha: dynamic dispatch có thể dẫn tới phương thức con khi các trường của con còn ở giá trị mặc định. Thứ tự static initializer, field initializer, instance block và constructor được thực hành chi tiết ở bài **Khởi tạo lớp con và chuỗi khởi tạo lớp cha**.

## 5. Ghi đè phương thức (`@Override`) làm thay đổi hành vi

Kế thừa không có nghĩa “bắt buộc dùng nguyên mọi hành vi cha”. Lớp con có thể **ghi đè (override)** phương thức instance có thể được override để cung cấp hành vi chuyên biệt.

Trong ví dụ tính lương:

~~~java
@Override
public BigDecimal monthlyPay() {
    return hourlyRate.multiply(
            BigDecimal.valueOf(hoursWorked));
}
~~~

Hai lớp con có cùng **chữ ký phương thức** và kiểu trả về tương thích với hợp đồng `Employee.monthlyPay()`, nhưng thuật toán khác nhau.

Khi viết:

~~~java
Employee employee = new HourlyEmployee(
        "E003", "Hà", new BigDecimal("100000"), 20);

System.out.println(employee.monthlyPay()); // 2000000
~~~

Dù `employee` được khai báo theo kiểu `Employee`, Java gọi `HourlyEmployee.monthlyPay()` do **kiểu thực tế** của đối tượng là `HourlyEmployee`. Đây là **đa hình động (runtime polymorphism)** đối với phương thức instance được override.

Một lớp con cũng có thể gọi lại phiên bản của lớp cha bằng `super.method()` khi phương thức cha có implementation:

~~~java
class Person {
    String describe() {
        return "Một người";
    }
}

class Student extends Person {
    @Override
    String describe() {
        return super.describe() + " đang học";
    }
}
~~~

~~~java
Person p = new Student();
System.out.println(p.describe()); // Một người đang học
~~~

Ở đây `super.describe()` là lời gọi trực tiếp phương thức triển khai ở lớp cha từ mã của subclass; nó khác với `super(...)` là lời gọi constructor cha.

### `@Override` giúp phát hiện sai sót

~~~java
class Base {
    void calculate() {}
}

class Derived extends Base {
    @Override
    void calcuate() {} // LỖI: sai tên, không thực sự override
}
~~~

Annotation `@Override` khiến compiler báo lỗi thay vì âm thầm tạo một phương thức mới vì sai chính tả. Nên dùng khi chủ đích là override.

Quy tắc cơ bản khi override:

- Tên và danh sách tham số phải phù hợp với phương thức được override.
- Kiểu trả về phải tương thích (có thể covariant đối với kiểu tham chiếu).
- Không giảm mức độ truy cập; ví dụ không override phương thức `public` thành `protected`.
- Quy định về checked exception không được mở rộng tùy ý so với phương thức cha.
- Phương thức `final` không thể override.
- Phương thức `private` của lớp cha không được subclass override vì nó không được kế thừa theo nghĩa đó; phương thức `static` cùng chữ ký là **hiding**, không phải override đa hình.

## 6. Kế thừa + đa hình: cùng API, nhiều cách thực hiện

Trong vòng lặp:

~~~java
for (Employee employee : staff) {
    employee.printPayslip();
}
~~~

Đoạn code không kiểm tra nhân viên là `SalariedEmployee` hay `HourlyEmployee`, nhưng kết quả vẫn đúng cho từng loại.

Luồng gọi được thể hiện bằng sequence diagram:

~~~mermaid
sequenceDiagram
    actor App as Main
    participant E as Employee (API)
    participant H as HourlyEmployee

    App->>E: printPayslip()
    Note over E,H: Một instance HourlyEmployee<br/>đang được tham chiếu qua Employee
    E->>H: role()
    H-->>E: "Theo giờ"
    E->>H: monthlyPay()
    H-->>E: 6000000
    E-->>App: đã in phiếu
~~~

Trong sơ đồ, `Employee (API)` chỉ **vai trò đoạn mã được kế thừa**; không có một object `Employee` riêng biệt được tạo cùng với `HourlyEmployee`. Khi `printPayslip()` gọi `role()` và `monthlyPay()`, Java thực hiện dispatch tới override của instance cụ thể.

Ưu điểm: nếu thêm `ContractEmployee` với quy tắc tính lương mới, vòng lặp tổng hợp lương có thể không cần sửa, miễn lớp mới tuân thủ đúng hợp đồng `Employee`. Đây là một ví dụ thực tế về khả năng mở rộng dựa trên đa hình.

## 7. Dùng tham chiếu lớp cha mà không ép kiểu tùy tiện

**Upcasting** là sử dụng biến kiểu cha cho một đối tượng con; Java thực hiện ngầm định:

~~~java
Employee employee = new HourlyEmployee(
        "E004", "Lan", new BigDecimal("90000"), 100);
System.out.println(employee.monthlyPay()); // 9000000
~~~

Gọi `monthlyPay()` hợp lệ vì nó thuộc API `Employee`, rồi Java chọn implementation của `HourlyEmployee`. Ngược lại, nếu muốn gọi một phương thức **chỉ có ở lớp con**, cần kiểm tra kiểu runtime trước khi downcast. Ép một `SalariedEmployee` sang `HourlyEmployee` sẽ gây `ClassCastException`.

~~~java
if (employee instanceof HourlyEmployee) {
    HourlyEmployee hourly = (HourlyEmployee) employee;
    System.out.println(hourly.monthlyPay());
}
~~~

Nên dùng đa hình qua `Employee` thay vì liên tục hỏi `instanceof` khi nghiệp vụ chỉ cần hợp đồng chung. Lưu ý `List<HourlyEmployee>` không tự là `List<Employee>`: generic `List<T>` của Java **không covariant**. Để đọc các phần tử con qua API nhận kiểu cha, có thể sử dụng `List<? extends Employee>` với giới hạn ghi phù hợp.

## 8. Quan hệ “is-a” khác “has-a”

Không phải cứ hai lớp cùng có dữ liệu hoặc dùng đến nhau thì nên dùng `extends`.

**Is-a (kế thừa):** một `ElectricCar` là một `Vehicle`. Khi hàm nhận `Vehicle`, nó có thể nhận `ElectricCar` nếu xe điện đáp ứng đúng những điều mà hợp đồng `Vehicle` cam kết.

**Has-a (thành phần):** một `Car` có một `Engine`. Xe hơi **không phải** là động cơ, nên viết `class Car extends Engine` chỉ để dùng lại `start()` là quan hệ sai.

~~~java
class Engine {
    void start() {
        System.out.println("Động cơ chạy");
    }
}

class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = engine;
    }

    void drive() {
        engine.start();
        System.out.println("Xe bắt đầu chạy");
    }
}
~~~

~~~java
Car car = new Car(new Engine());
car.drive();
~~~

Đây là **composition**: `Car` giữ tham chiếu đến `Engine` và ủy quyền một phần công việc. Nếu sau này đổi sang một loại động cơ khác, cấu trúc thành phần có thể linh hoạt hơn so với đưa mọi biến thể vào một cây kế thừa.

| Quan hệ | Câu hỏi kiểm tra | Java thường dùng |
| --- | --- | --- |
| **Is-a** | “X là một loại Y” và thay X vào vị trí Y vẫn hợp lệ? | `class X extends Y` hoặc `implements` hợp đồng kiểu phù hợp |
| **Has-a** | “X có/sử dụng Y để làm việc”? | Field tham chiếu, constructor injection, composition |
| **Uses-a** | “X chỉ dùng Y trong một thao tác”? | Tham số phương thức hoặc dependency ngắn hạn |

Một câu “X là Y” trong tiếng Việt có thể nghe hợp lý nhưng chưa đủ. **Hợp đồng hành vi** mới là tiêu chí quyết định: mọi yêu cầu hợp lệ đối với Y có còn thực hiện đúng trên X không?

## 9. Quy tắc kế thừa của Java cần nhớ

| Quy tắc | Ví dụ | Kết quả |
| --- | --- | --- |
| Mỗi class `extends` tối đa một class trực tiếp | `class C extends A, B` | Không hợp lệ |
| Một lớp có thể `implements` nhiều interface | `class C extends A implements X, Y` | Hợp lệ |
| Nếu không khai báo `extends`, lớp thông thường kế thừa `Object` | `class X {}` | Các phương thức phù hợp của `Object` có sẵn |
| Class `final` không được kế thừa | `final class Token {}` rồi `extends Token` | Lỗi biên dịch |
| Method `final` không được override | `final void run() {}` | Subclass không thể thay implementation |
| Abstract class không tạo instance trực tiếp | `new Employee()` trong ví dụ | Lỗi biên dịch |
| Subclass concrete phải hoàn thiện abstract methods còn thiếu | `class X extends Employee` nhưng không có `monthlyPay()` | Lỗi biên dịch |
| Constructor không được kế thừa | `super(id, name)` | Gọi constructor cha để khởi tạo |
| Kế thừa có tính bắc cầu | `C extends B` và `B extends A` | C cũng là subtype của A |

Java còn có **interface** cho quan hệ đa hình theo hợp đồng; cơ chế `implements` không giống với đa kế thừa class. Một class chỉ có một superclass trực tiếp, giúp tránh nhiều vấn đề khi thừa kế trạng thái và implementation từ nhiều class.

### Kế thừa không có nghĩa mọi thành viên đều dùng được

Các thành viên `private` vẫn bị giới hạn truy cập. Constructor không được kế thừa. Static method không tham gia dispatch động như override instance method. Field cùng tên ở lớp con có thể **che khuất (hide)** field của lớp cha; truy cập field được ràng buộc theo kiểu tham chiếu, khác với phương thức instance override. Vì thế nên hạn chế thiết kế dựa trên việc trùng tên field giữa cha và con.

Ví dụ phân biệt field và method:

~~~java
class Animal {
    String name = "Animal";

    String speak() {
        return "Âm thanh chung";
    }
}

class Dog extends Animal {
    String name = "Dog"; // Che khuất field cha.

    @Override
    String speak() {
        return "Gâu";
    }
}

Animal a = new Dog();

System.out.println(a.name);    // Animal (field theo kiểu tham chiếu)
System.out.println(a.speak()); // Gâu (method theo instance thực)
~~~

Ở đây, cả hai field `name` đều tồn tại như thành viên được khai báo ở hai cấp; vì cách truy cập gây nhầm lẫn, nên tránh field hiding trong thiết kế thông thường.

## 10. Tránh lạm dụng kế thừa và giữ hợp đồng của lớp cha

Một lớp con phải tôn trọng kỳ vọng hợp lệ của lớp cha. Điều này liên quan đến **Liskov Substitution Principle (LSP)**: mã dùng lớp cha không nên bị bất ngờ vì lớp con phá vỡ quy tắc quan trọng mà lớp cha cam kết.

Ví dụ thiết kế không tốt:

~~~java
class Bird {
    void fly() {
        System.out.println("Đang bay");
    }
}

class Penguin extends Bird {
    @Override
    void fly() {
        throw new UnsupportedOperationException("Không thể bay");
    }
}
~~~

Chim cánh cụt đúng là một loài chim về sinh học, nhưng **không phù hợp với hợp đồng “mọi Bird đều bay được”** do lớp `Bird.fly()` áp đặt. Mã nhận `Bird` và tin rằng `fly()` luôn làm việc sẽ thất bại với `Penguin`.

Một mô hình tốt hơn là tách năng lực:

~~~java
interface Flyable {
    void fly();
}

abstract class Bird {
    abstract void move();
}

class Sparrow extends Bird implements Flyable {
    @Override
    void move() {
        System.out.println("Chim sẻ di chuyển");
    }

    @Override
    public void fly() {
        System.out.println("Chim sẻ bay");
    }
}

class Penguin extends Bird {
    @Override
    void move() {
        System.out.println("Chim cánh cụt đi hoặc bơi");
    }
}
~~~

Ở đây, `Bird` chỉ cam kết hành vi chung cho tất cả loài chim; `Flyable` biểu diễn năng lực riêng. Kế thừa hợp lý dựa trên **hợp đồng nhất quán**, không phải chỉ dựa trên sự giống nhau về danh từ hay vài dòng code.

Khi quyết định thiết kế, nên tự hỏi:

1. Có quan hệ **is-a** đúng về hành vi, không chỉ giống dữ liệu?
2. Subclass có thể tôn trọng tiền điều kiện, hậu điều kiện và invariant của superclass?
3. Phần chung có thực sự ổn định, hay mỗi subclass sẽ liên tục phải override để chống lại lớp cha?
4. Liệu composition hoặc interface có đáp ứng nhu cầu với ít ràng buộc hơn?
5. Việc mở rộng lớp cha có vô tình thay đổi hành vi các lớp con hiện có không?

**Kế thừa là quan hệ chặt**: subclass phụ thuộc vào hợp đồng và cách tổ chức của superclass. Khi quan hệ “is-a” không rõ ràng hoặc chỉ muốn dùng lại một tiện ích, composition thường đơn giản và dễ bảo trì hơn.

## 11. Các lỗi thường gặp khi học

| Lỗi | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Nghĩ `extends` tạo một object cha và một object con độc lập | Nhầm cấp class với cấp instance | Một lần `new Subclass()` tạo một instance với các phần trạng thái kế thừa |
| Gọi `new Employee()` trong ví dụ | `Employee` là abstract | Tạo một subclass concrete |
| Quên `super(...)` khi cha không có constructor không tham số | Compiler không thể gọi constructor phù hợp | Gọi constructor cha tường minh |
| Override sai chữ ký | Tạo overload mới hoặc thiếu implementation | Dùng `@Override` để compiler hỗ trợ |
| Truy cập `private` field cha trực tiếp | Field không khả dụng qua tên ở subclass | Dùng API `public`/`protected` thích hợp |
| Ép mọi `Employee` sang `HourlyEmployee` | Runtime object có thể là kiểu con khác | Tránh downcast, dùng đa hình hoặc kiểm tra kiểu |
| Lạm dụng setter/override làm hỏng invariant cha | Subclass không tôn trọng hợp đồng | Thiết kế quy tắc chung ở cha, mở rộng tại điểm cho phép |
| Kế thừa chỉ để gọi một helper | Quan hệ “is-a” không đúng | Dùng composition/ủy quyền |
| Nhầm field hiding với method overriding | Java xử lý field và method khác nhau | Tránh trùng tên field, hiểu dispatch động |

## 12. Bài tập tự kiểm tra

**Bài 1.** `Vehicle v = new Car();` có hợp lệ không? `v.openTrunk()` có biên dịch không?

**Đáp án:** Phép gán hợp lệ vì `Car` kế thừa `Vehicle`. Nhưng `v.openTrunk()` không biên dịch nếu kiểu `Vehicle` không khai báo phương thức đó; phương thức hợp lệ dựa vào **kiểu tĩnh** của biến.

**Bài 2.** Với một `HourlyEmployee` có `hourlyRate=100000`, `hoursWorked=15`, gọi `monthlyPay()` qua biến `Employee` trả gì?

**Đáp án:** `1500000`. Java gọi override của `HourlyEmployee` theo instance runtime dù biến được khai báo là `Employee`.

**Bài 3.** Tại sao `HourlyEmployee` không thể tự truy cập `this.id` nếu `id` là `private` ở `Employee`?

**Đáp án:** Quyền `private` giới hạn mã trực tiếp truy cập field ở lớp khai báo (ngoại trừ cơ chế quyền truy cập đặc biệt giữa các lớp lồng/nestmates do Java quy định). Lớp con dùng API như `getId()` do lớp cha công khai.

**Bài 4.** `SalariedEmployee` và `HourlyEmployee` có phải là hai đối tượng khi chỉ gọi `new HourlyEmployee(...)` không?

**Đáp án:** Không. Chỉ một đối tượng `HourlyEmployee` được tạo, bao gồm cả phần trạng thái/hành vi được kế thừa từ `Employee`.

**Bài 5.** Một lớp con không override phương thức thường của lớp cha có được không?

**Đáp án:** Có. Nếu không có nghĩa vụ triển khai abstract method còn thiếu, lớp con có thể kế thừa toàn bộ implementation phù hợp. Override chỉ cần khi lớp con phải chuyên biệt hóa hành vi được phép thay đổi.

**Bài 6.** Khi ứng dụng có `Car` và `Engine`, nên chọn `Car extends Engine` hay `Car` giữ một `Engine`?

**Đáp án:** `Car` **có** động cơ, không phải **là** động cơ. Quan hệ composition (`Car` giữ tham chiếu `Engine`) hợp lý hơn.

**Bài 7.** Việc thêm `Penguin extends Bird` mà lớp `Bird` cam kết `fly()` luôn hoạt động gây nguy cơ gì?

**Đáp án:** Phá vỡ hợp đồng thay thế của `Bird` nếu `Penguin.fly()` ném lỗi không được kỳ vọng. Hãy mô hình hóa hành vi chung đúng với mọi lớp con và tách năng lực bay thành `Flyable` nếu thích hợp.

**Bài 8.** Nếu sau này có `ContractEmployee`, vòng lặp `List<Employee>` tính lương có cần thêm `if (e instanceof ContractEmployee)` không?

**Đáp án:** Thường không, nếu lớp mới triển khai đúng `monthlyPay()`. Đa hình giúp vòng lặp gọi API chung và để mỗi subclass quyết định công thức.

### Ghi nhớ

**Lớp cha** mô tả phần chung và hợp đồng cho một họ đối tượng; **lớp con** là một loại cụ thể hơn, kế thừa phần chung và có thể bổ sung hoặc override hành vi được cho phép. Quan hệ `extends` là cam kết “is-a”, không đơn thuần là mẹo sao chép mã.

Khi đọc code kế thừa, hãy lần lượt xác định: lớp nào là superclass, lớp nào là subclass, constructor cha nào chạy, phương thức nào được kế thừa/override, đối tượng runtime thuộc lớp nào, và liệu subclass có tôn trọng hợp đồng của superclass không.