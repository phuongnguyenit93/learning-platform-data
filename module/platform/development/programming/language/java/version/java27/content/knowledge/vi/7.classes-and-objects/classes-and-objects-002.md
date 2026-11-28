# Field, phương thức instance và thành viên static

## 1. Thành viên của một lớp Java

Một lớp Java mô tả dữ liệu và hành vi của các đối tượng thuộc kiểu đó. Những khai báo nằm trực tiếp trong thân lớp có thể là field, constructor, phương thức, lớp lồng nhau hoặc các thành viên kiểu khác. Trong bài này, trọng tâm là field và phương thức, cùng sự khác biệt giữa thành viên gắn với từng đối tượng và thành viên gắn với lớp.

Hai nhóm quan trọng:

- **Instance member** thuộc về một đối tượng cụ thể. Mỗi object có trạng thái instance riêng; phương thức instance được gọi trên một đối tượng và có thể truy cập trạng thái đó.
- **Static member** thuộc về lớp. Field static được chia sẻ bởi các đối tượng của lớp; phương thức static được gọi qua tên lớp và không có đối tượng hiện tại.

~~~mermaid
flowchart TD
    A[Lop BankAccount] --> B[Static state]
    A --> C[Instance state]
    B --> D[NEXT_ID, accountCount]
    C --> E[Object A: id, balance]
    C --> F[Object B: id, balance]
    D --> E
    D --> F
~~~

Ví dụ, hai tài khoản ngân hàng có số dư riêng nhưng cùng sử dụng bộ đếm số tài khoản đã được tạo. Số dư là trạng thái instance; bộ đếm dùng chung là trạng thái static.

## 2. Field và biến cục bộ

**Field** là biến được khai báo trong thân lớp hoặc record, bên ngoài thân phương thức, constructor và block cục bộ. Field biểu diễn trạng thái của object hoặc trạng thái dùng chung của lớp.

~~~java
public class Product {
    private String name;                 // Instance field
    private java.math.BigDecimal price;  // Instance field

    private static int productCount;     // Static field

    public void printName() {
        String prefix = "Product: ";      // Local variable
        System.out.println(prefix + name);
    }
}
~~~

Trong ví dụ:

- **name** và **price** là instance field; mỗi object Product giữ giá trị riêng.
- **productCount** là static field; tất cả object Product trong cùng định nghĩa lớp được nạp chia sẻ một biến này.
- **prefix** là biến cục bộ của lần gọi phương thức; nó không phải field và không trở thành trạng thái của object.

Field được gán giá trị mặc định khi vùng nhớ của object hoặc lớp được khởi tạo. Ví dụ, field kiểu số nguyên có giá trị mặc định **0**, kiểu boolean là **false**, còn field kiểu tham chiếu là **null**. Biến cục bộ không có giá trị mặc định có thể sử dụng; trình biên dịch yêu cầu biến cục bộ phải được gán chắc chắn trước khi đọc.

~~~java
public class Defaults {
    int count;             // 0
    boolean enabled;       // false
    String label;          // null

    void run() {
        int attempts;
        // System.out.println(attempts); // Compile error: chưa được gán
        attempts = 1;
        System.out.println(attempts);
    }
}
~~~

Không nên dựa vào giá trị mặc định để biểu diễn trạng thái nghiệp vụ khi điều đó gây mơ hồ. Hãy khởi tạo field theo bất biến của lớp, ví dụ số dư ban đầu, trạng thái đơn hàng hoặc tập hợp rỗng.

## 3. Instance field: trạng thái riêng của từng object

Instance field lưu dữ liệu thay đổi theo từng đối tượng. Khi tạo hai object từ cùng một lớp, mỗi object có bản sao field riêng:

~~~java
public class UserProfile {
    private String displayName;
    private int loginCount;

    public UserProfile(String displayName) {
        this.displayName = displayName;
    }

    public void recordLogin() {
        loginCount++;
    }

    public String displayName() {
        return displayName;
    }

    public int loginCount() {
        return loginCount;
    }
}
~~~

~~~java
UserProfile alice = new UserProfile("Alice");
UserProfile bob = new UserProfile("Bob");

alice.recordLogin();
alice.recordLogin();
bob.recordLogin();

System.out.println(alice.loginCount()); // 2
System.out.println(bob.loginCount());   // 1
~~~

Việc thay đổi **loginCount** của Alice không làm thay đổi trạng thái của Bob. Mỗi object có identity riêng và field instance là một phần trạng thái của identity đó.

Field có thể là kiểu nguyên thủy hoặc kiểu tham chiếu. Nếu field là kiểu tham chiếu, object giữ giá trị tham chiếu đến đối tượng khác; nó không tự động sao chép đối tượng được tham chiếu. Vì vậy, nhiều object có thể cùng tham chiếu một collection hoặc một đối tượng mutable. Khi thiết kế lớp, cần quyết định rõ dữ liệu nào được chia sẻ và ai có quyền thay đổi nó.

## 4. Static field: trạng thái dùng chung của lớp

Khai báo field với từ khóa **static** tạo thành viên cấp lớp. Một biến static gắn với định nghĩa lớp đã được nạp, thay vì được tạo riêng cho mỗi object. Nó thường dùng cho dữ liệu chung như hằng số, registry bất biến, bộ đếm hoặc cấu hình dùng chung đã được kiểm soát.

~~~java
public class Session {
    private static long createdCount;
    private final long id;

    public Session(long id) {
        this.id = id;
        createdCount++;
    }

    public long id() {
        return id;
    }

    public static long createdCount() {
        return createdCount;
    }
}
~~~

~~~java
Session first = new Session(101);
Session second = new Session(102);

System.out.println(first.id());             // 101
System.out.println(second.id());            // 102
System.out.println(Session.createdCount()); // 2
~~~

**id** là instance field vì mỗi session có mã riêng. **createdCount** là static field vì lớp Session duy trì một bộ đếm chung.

Nên truy cập thành viên static bằng tên lớp, ví dụ **Session.createdCount()**. Cách gọi này thể hiện rõ thành viên thuộc về lớp. Java cho phép một số cách truy cập static qua biểu thức tham chiếu, nhưng cách viết đó dễ gây hiểu nhầm rằng thành viên thuộc về object.

Static field được khởi tạo trong quá trình khởi tạo lớp. Mỗi lớp được định nghĩa bởi một class loader có trạng thái static riêng; nếu cùng một tên lớp được nạp bởi hai class loader khác nhau, chúng là hai định nghĩa lớp khác nhau và không chia sẻ static field với nhau.

## 5. Hằng số và static final

Từ khóa **final** ngăn việc gán lại biến sau khi đã được khởi tạo. Kết hợp **static final** thường dùng để khai báo hằng số cấp lớp:

~~~java
public final class Limits {
    public static final int MAX_RETRIES = 3;
    public static final java.time.Duration REQUEST_TIMEOUT =
        java.time.Duration.ofSeconds(5);

    private Limits() {
    }
}
~~~

Tên hằng số public thường dùng chữ hoa và dấu gạch dưới. Có thể truy cập bằng **Limits.MAX_RETRIES**. Các giá trị được khai báo final nên có ý nghĩa ổn định và không phụ thuộc vào trạng thái của từng object.

Cần hiểu rằng **final** trên một field tham chiếu chỉ ngăn thay đổi tham chiếu sau khởi tạo; nó không tự làm object được tham chiếu trở nên bất biến. Ví dụ:

~~~java
private static final java.util.List<String> ROLES =
    new java.util.ArrayList<>();

void addRole(String role) {
    ROLES.add(role); // Vẫn có thể thay đổi nội dung list
}
~~~

Nếu cần danh sách không cho sửa đổi, có thể dùng collection factory bất biến:

~~~java
private static final java.util.List<String> ROLES =
    java.util.List.of("ADMIN", "EDITOR", "VIEWER");
~~~

Đối với hằng compile-time, Java có thể nhúng giá trị vào mã đã biên dịch của nơi sử dụng. Nếu một thư viện thay đổi giá trị hằng public kiểu primitive hoặc String, ứng dụng phụ thuộc có thể cần biên dịch lại để nhận giá trị mới. Với giá trị cấu hình có thể thay đổi theo lần chạy hoặc cần nạp động, không nên mô hình hóa nó như compile-time constant.

## 6. Phương thức instance

Phương thức instance được khai báo không có **static**. Nó được gọi trên một object và có thể đọc hoặc thay đổi instance field của object đó. Trong phương thức instance, **this** tham chiếu đến object hiện tại.

~~~java
public class Counter {
    private int value;

    public Counter(int initialValue) {
        this.value = initialValue;
    }

    public void increment() {
        this.value++;
    }

    public void add(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("amount must be non-negative");
        }
        this.value += amount;
    }

    public int value() {
        return this.value;
    }
}
~~~

~~~java
Counter first = new Counter(10);
Counter second = new Counter(100);

first.increment();
second.add(5);

System.out.println(first.value());  // 11
System.out.println(second.value()); // 105
~~~

Lời gọi **first.increment()** thực thi trên trạng thái của first; **second.add(5)** thực thi trên trạng thái của second. Cùng một phần mã phương thức được sử dụng cho nhiều object, nhưng mỗi lần gọi có receiver và trạng thái instance tương ứng.

**this** thường được dùng để phân biệt field với tham số cùng tên, như **this.value = value**, hoặc truyền object hiện tại cho phương thức khác. Không thể sử dụng **this** trong ngữ cảnh static vì ở đó không có object hiện tại.

## 7. Phương thức static

Phương thức static thuộc về lớp và được gọi bằng tên lớp. Nó không có receiver instance ngầm định, không thể truy cập trực tiếp instance field hoặc gọi phương thức instance nếu chưa có tham chiếu đến một object.

~~~java
public final class Temperature {
    private Temperature() {
    }

    public static double celsiusToFahrenheit(double celsius) {
        return celsius * 9.0 / 5.0 + 32.0;
    }

    public static boolean isAbsoluteZero(double celsius) {
        return Double.compare(celsius, -273.15) == 0;
    }
}
~~~

~~~java
double fahrenheit = Temperature.celsiusToFahrenheit(25.0);
System.out.println(fahrenheit); // 77.0
~~~

Phương thức static phù hợp với thao tác không cần trạng thái instance, ví dụ phép chuyển đổi, hàm kiểm tra, factory method hoặc tiện ích có đầu vào và kết quả rõ ràng. Nó có thể truy cập static field và gọi phương thức static khác của lớp.

Nếu cần dùng trạng thái instance, hãy nhận object làm tham số hoặc gọi phương thức instance thông qua một tham chiếu:

~~~java
public class Invoice {
    private final java.math.BigDecimal total;

    public Invoice(java.math.BigDecimal total) {
        this.total = total;
    }

    public java.math.BigDecimal total() {
        return total;
    }

    public static java.math.BigDecimal totalOf(Invoice invoice) {
        return invoice.total();
    }
}
~~~

Không nên biến mọi phương thức thành static chỉ vì chúng có thể viết theo cách đó. Khi hành vi thuộc về một đối tượng và cần bảo vệ bất biến trạng thái của đối tượng, phương thức instance thường thể hiện mô hình tốt hơn.

## 8. Phân biệt truy cập instance và static

Các quy tắc truy cập cơ bản:

| Vị trí gọi | Instance field/method | Static field/method |
|---|---|---|
| Phương thức instance | Truy cập trực tiếp qua object hiện tại | Truy cập trực tiếp qua lớp |
| Phương thức static | Cần một tham chiếu object rõ ràng | Truy cập trực tiếp |
| Bên ngoài lớp | Qua object và quyền truy cập phù hợp | Ưu tiên qua tên lớp và quyền truy cập phù hợp |
| Constructor | Có thể khởi tạo trạng thái object | Có thể đọc hoặc cập nhật trạng thái lớp |

Ví dụ minh họa:

~~~java
public class Example {
    private int instanceValue = 10;
    private static int sharedValue = 20;

    public void instanceMethod() {
        System.out.println(instanceValue); // Hợp lệ
        System.out.println(sharedValue);   // Hợp lệ
        staticMethod();                    // Hợp lệ
    }

    public static void staticMethod() {
        System.out.println(sharedValue);   // Hợp lệ
        // System.out.println(instanceValue); // Compile error
        // instanceMethod();                 // Compile error
        // System.out.println(this);         // Compile error
    }

    public static void main(String[] args) {
        Example example = new Example();
        System.out.println(example.instanceValue);
        example.instanceMethod();
        Example.staticMethod();
    }
}
~~~

Phương thức static có thể tạo object hoặc nhận object từ tham số; điều bị giới hạn là truy cập instance ngầm định. Từ bên ngoài, quyền truy cập vẫn chịu ảnh hưởng của **public**, **protected**, package access và **private**. Từ khóa static không thay thế cơ chế đóng gói.

## 9. Khởi tạo field và thứ tự khởi tạo

Field có thể được khởi tạo ngay tại nơi khai báo. Static field initializer và static initializer block chạy trong quá trình khởi tạo lớp; instance field initializer và instance initializer block chạy khi tạo object.

~~~java
public class InitializationOrder {
    private static int nextCode = 100;
    private static final String CLASS_MARKER = initializeClassMarker();

    private final int code = nextCode++;
    private final String instanceMarker = initializeInstanceMarker();

    static {
        System.out.println("Static initializer");
    }

    {
        System.out.println("Instance initializer");
    }

    public InitializationOrder() {
        System.out.println("Constructor: " + code);
    }

    private static String initializeClassMarker() {
        System.out.println("Static field initializer");
        return "CLASS";
    }

    private String initializeInstanceMarker() {
        System.out.println("Instance field initializer");
        return "INSTANCE";
    }
}
~~~

Trong một lớp, các field initializer và initializer block cùng loại được thực hiện theo thứ tự văn bản. Quá trình khởi tạo lớp thực hiện phần khởi tạo static theo thứ tự khai báo; lớp cha được khởi tạo trước lớp con. Việc khởi tạo lớp chỉ xảy ra khi JVM thực hiện một hành động kích hoạt theo quy tắc của Java, chẳng hạn tạo instance, gọi phương thức static được khai báo trong lớp hoặc truy cập một static field không phải compile-time constant.

Khi tạo object, các field instance trước tiên nhận giá trị mặc định. Constructor chain gọi constructor lớp cha; sau khi phần khởi tạo của lớp cha hoàn tất, initializer của lớp hiện tại và phần thân constructor tương ứng được thực thi theo quy tắc ngôn ngữ. Với constructor gọi constructor khác cùng lớp bằng **this(...)**, chuỗi constructor chỉ khởi tạo instance một lần.

Nên giữ initializer đơn giản, dễ dự đoán. Tránh gọi phương thức có thể bị override từ constructor vì phương thức của lớp con có thể được dispatch khi các field lớp con chưa hoàn tất khởi tạo.

## 10. Static method hiding và instance method overriding

Hai khái niệm này không giống nhau:

- **Overriding:** phương thức instance của lớp con thay thế hành vi kế thừa từ lớp cha; lời gọi được phân giải động theo kiểu thực tế của object.
- **Hiding:** phương thức static cùng chữ ký trong lớp con che khuất phương thức static cùng tên của lớp cha; lựa chọn dựa trên kiểu được dùng để tham chiếu, không dựa trên kiểu runtime của object.

~~~java
class Parent {
    static String category() {
        return "Parent";
    }

    String description() {
        return "Parent instance";
    }
}

class Child extends Parent {
    static String category() {
        return "Child";
    }

    @Override
    String description() {
        return "Child instance";
    }
}
~~~

~~~java
Parent value = new Child();

System.out.println(value.category());    // Parent: static method được chọn theo kiểu tham chiếu
System.out.println(value.description()); // Child: instance method được dispatch theo object
System.out.println(Child.category());    // Child
~~~

Dù Java cho phép gọi static method qua biểu thức tham chiếu như **value.category()**, cách đó dễ khiến người đọc hiểu nhầm. Hãy gọi bằng tên lớp: **Parent.category()** hoặc **Child.category()**. Static method không thể được override theo nghĩa đa hình; annotation **@Override** không hợp lệ trên một phương thức static.

## 11. Thiết kế field và phương thức an toàn

Field thường nên có mức truy cập **private** để lớp kiểm soát cách trạng thái được đọc và thay đổi. Cung cấp phương thức công khai theo nhu cầu nghiệp vụ thay vì mở trực tiếp field. Cách này cho phép kiểm tra dữ liệu, duy trì bất biến và thay đổi cách lưu trữ mà không làm hỏng hợp đồng bên ngoài.

~~~java
public class BankAccount {
    private final String accountNumber;
    private java.math.BigDecimal balance;

    public BankAccount(
            String accountNumber,
            java.math.BigDecimal openingBalance) {
        this.accountNumber = java.util.Objects.requireNonNull(accountNumber);
        this.balance = java.util.Objects.requireNonNull(openingBalance);

        if (openingBalance.signum() < 0) {
            throw new IllegalArgumentException("Opening balance cannot be negative");
        }
    }

    public String accountNumber() {
        return accountNumber;
    }

    public java.math.BigDecimal balance() {
        return balance;
    }

    public void deposit(java.math.BigDecimal amount) {
        java.util.Objects.requireNonNull(amount);
        if (amount.signum() <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        balance = balance.add(amount);
    }
}
~~~

Ở đây, **accountNumber** không thay đổi sau khi khởi tạo; **balance** chỉ được cập nhật qua phương thức **deposit** có xác thực. Người dùng lớp không thể gán trực tiếp một số dư âm.

Nếu trả về một object mutable từ getter, việc đóng gói vẫn có thể bị phá vỡ vì caller có thể thay đổi object bên trong. Cân nhắc trả về kiểu immutable, bản sao phòng vệ (*defensive copy*) hoặc view không cho sửa đổi tùy theo hợp đồng dữ liệu.

## 12. Static state, vòng đời và an toàn đa luồng

Static field mutable được nhiều object và nhiều thread chia sẻ. Từ khóa **static** không tự cung cấp đồng bộ, visibility hay atomicity. Nếu nhiều thread đọc/ghi một biến static mà không có cơ chế phối hợp phù hợp, chương trình có thể gặp race condition hoặc dữ liệu không nhất quán.

~~~java
public class RequestMetrics {
    private static long requestCount;

    public static void recordRequest() {
        requestCount++; // Không an toàn khi nhiều thread gọi đồng thời
    }

    public static long requestCount() {
        return requestCount;
    }
}
~~~

Phép tăng **requestCount++** là thao tác đọc, cộng và ghi; nó không nguyên tử. Nếu cần bộ đếm đồng thời, có thể dùng **AtomicLong**:

~~~java
public final class RequestMetrics {
    private static final java.util.concurrent.atomic.AtomicLong REQUEST_COUNT =
        new java.util.concurrent.atomic.AtomicLong();

    private RequestMetrics() {
    }

    public static long recordRequest() {
        return REQUEST_COUNT.incrementAndGet();
    }

    public static long requestCount() {
        return REQUEST_COUNT.get();
    }
}
~~~

Với trạng thái phức tạp gồm nhiều field phải cập nhật nhất quán, hãy chọn một cơ chế đồng bộ phù hợp như **synchronized**, lock hoặc thiết kế immutable/atomic phù hợp. **volatile** hỗ trợ visibility và thứ tự truy cập theo memory model nhưng không biến phép cập nhật kết hợp như **count++** thành nguyên tử.

Static mutable state cũng tồn tại theo vòng đời của lớp trong class loader. Nó có thể làm test phụ thuộc thứ tự chạy, giữ dữ liệu giữa các request hoặc cản trở việc giải phóng class loader trong môi trường plugin. Ưu tiên dependency được truyền tường minh và trạng thái có vòng đời rõ ràng; chỉ dùng static mutable state khi có lý do kiến trúc và đã kiểm soát truy cập.

## 13. Instance field trong record và giới hạn của record

Record phù hợp để mô hình hóa dữ liệu có thành phần được xác định rõ. Các record component tạo ra field instance tương ứng, có tính **final**, cùng accessor và các phương thức được sinh tự động. Record có thể khai báo static field và static method như một kiểu lớp thông thường.

~~~java
public record Point(int x, int y) {
    public static final Point ORIGIN = new Point(0, 0);

    public static Point origin() {
        return ORIGIN;
    }

    public int manhattanDistance() {
        return Math.abs(x) + Math.abs(y);
    }
}
~~~

Các component **x** và **y** là trạng thái instance của mỗi Point. **ORIGIN** là static field dùng chung. Phương thức **manhattanDistance()** là instance method vì nó tính toán dựa trên component của object; **origin()** là static method vì không cần một Point hiện tại.

Record không cho khai báo thêm instance field tùy ý bên ngoài các record component. Nếu mô hình cần trạng thái instance bổ sung có thể thay đổi, hãy cân nhắc dùng class thông thường. Field final của record cũng không làm sâu các object được tham chiếu trở nên immutable; nếu component là collection mutable, cần bảo vệ dữ liệu đầu vào theo hợp đồng của record.

## 14. Lựa chọn instance hay static

| Câu hỏi thiết kế | Lựa chọn thường phù hợp |
|---|---|
| Giá trị có khác nhau giữa các object không? | Instance field |
| Dữ liệu là hằng số hoặc chính sách dùng chung? | Static final |
| Hành vi cần đọc/cập nhật trạng thái của object hiện tại? | Instance method |
| Phép tính chỉ phụ thuộc tham số đầu vào và không cần object hiện tại? | Static method |
| Trạng thái dùng chung có thể thay đổi? | Static field chỉ khi có quản lý vòng đời và đồng bộ rõ ràng |
| Dữ liệu phải được bảo vệ khỏi thay đổi bên ngoài? | Private field, accessor và kiểm tra bất biến |

Một số lỗi thiết kế thường gặp:

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Mọi object có cùng giá trị ngoài ý muốn | Dùng static cho dữ liệu cần riêng từng object | Chuyển thành instance field |
| Static method không truy cập được field | Field là instance member và không có object hiện tại | Truyền object vào hoặc dùng instance method |
| Một object thay đổi làm object khác đổi theo | Các object chia sẻ cùng tham chiếu mutable | Tạo bản sao hoặc dùng dữ liệu immutable |
| Bộ đếm sai khi có nhiều thread | Cập nhật static field không nguyên tử | Dùng atomic hoặc cơ chế đồng bộ |
| Giá trị static final vẫn thay đổi | final chỉ khóa việc gán lại tham chiếu | Dùng object immutable hoặc bản sao không cho sửa |
| Gọi static method cho kết quả khó hiểu | Gọi static qua tham chiếu có kiểu khác kiểu runtime | Gọi qua tên lớp |
| Constructor gọi hành vi lớp con quá sớm | Gọi phương thức có thể override trong constructor | Tránh gọi phương thức có thể override trong quá trình khởi tạo |

## 15. Checklist khi thiết kế field và phương thức

- [ ] Xác định dữ liệu thuộc riêng từng object hay được chia sẻ ở cấp lớp.
- [ ] Dùng instance field cho trạng thái riêng và static field cho dữ liệu thực sự dùng chung.
- [ ] Khởi tạo field theo bất biến của lớp thay vì phụ thuộc vào giá trị mặc định.
- [ ] Để field ở mức private và cung cấp hành vi qua phương thức phù hợp.
- [ ] Dùng **this** để thể hiện rõ object hiện tại trong instance method.
- [ ] Dùng static method cho hành vi không cần trạng thái instance.
- [ ] Gọi static member bằng tên lớp để thể hiện đúng phạm vi sở hữu.
- [ ] Phân biệt static method hiding với instance method overriding.
- [ ] Dùng static final cho hằng số và bảo đảm object tham chiếu có tính bất biến khi cần.
- [ ] Kiểm soát đồng thời khi static mutable state được chia sẻ giữa nhiều thread.
- [ ] Xác định vòng đời và khả năng reset trạng thái static trong kiểm thử.
- [ ] Hiểu giới hạn instance field của record khi mô hình hóa dữ liệu.

Thiết kế field và phương thức tốt bắt đầu từ việc xác định ai sở hữu trạng thái và trạng thái tồn tại trong bao lâu. Instance member mô tả từng object; static member mô tả dữ liệu hoặc hành vi thuộc lớp. Khi phạm vi sở hữu, quyền thay đổi và cơ chế đồng bộ được thể hiện rõ, lớp Java dễ sử dụng, dễ kiểm thử và an toàn hơn khi ứng dụng phát triển.
