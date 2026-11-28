# Khai báo lớp, tạo đối tượng và truy cập thành viên

Trong Java 27, **lớp (class)** là cấu trúc dùng để định nghĩa một kiểu tham chiếu. Lớp mô tả dữ liệu mà đối tượng lưu giữ và các thao tác mà đối tượng cung cấp. **Đối tượng (object)** là một instance được tạo từ lớp trong khi chương trình chạy.

Để làm việc với lớp và đối tượng, cần nắm ba thao tác chính:

1. Khai báo lớp cùng các thành viên như field, constructor và method.
2. Tạo đối tượng từ một lớp cụ thể bằng biểu thức khởi tạo đối tượng, thường dùng từ khóa **new**.
3. Truy cập field hoặc gọi method thông qua tham chiếu đối tượng, đồng thời tuân thủ quy tắc truy cập của thành viên.

Bài viết tập trung vào cú pháp và hành vi lớp, đối tượng đang áp dụng trong Java 27, gồm cả cách phân biệt thành viên instance và thành viên static.

## 1. Lớp và đối tượng

Một lớp có thể được xem là mô tả chung cho một nhóm đối tượng cùng kiểu. Ví dụ, lớp **Book** có thể mô tả thông tin một quyển sách như tiêu đề, tác giả và các thao tác hiển thị thông tin.

Mỗi đối tượng **Book** được tạo ra là một instance riêng. Các instance có thể có giá trị field khác nhau, nhưng cùng tuân theo cấu trúc và các method do lớp định nghĩa.

~~~java
class Book {
    String title;
    String author;

    void printDetails() {
        System.out.println(title + " - " + author);
    }
}
~~~

Lớp **Book** khai báo hai field là **title**, **author** và một method là **printDetails()**. Khi tạo hai đối tượng từ lớp này, mỗi đối tượng có trạng thái instance riêng.

~~~java
Book firstBook = new Book();
Book secondBook = new Book();

firstBook.title = "Effective Java";
firstBook.author = "Joshua Bloch";

secondBook.title = "Java Concurrency in Practice";
secondBook.author = "Brian Goetz";

firstBook.printDetails();
secondBook.printDetails();
~~~

Hai đối tượng có thể gọi cùng một method, nhưng method làm việc với field của chính instance nhận lời gọi.

Trong mã ứng dụng thực tế, nên kiểm soát quyền truy cập field và bảo vệ trạng thái đối tượng bằng cách khai báo field **private**, sau đó cung cấp constructor và method phù hợp. Ví dụ ban đầu ở trên chỉ nhằm minh họa quan hệ giữa lớp và instance.

## 2. Cấu trúc khai báo lớp

Cú pháp cơ bản của một lớp:

~~~java
[access-modifier] class ClassName {
    // Fields
    // Constructors
    // Methods
    // Nested types
}
~~~

Trong đó:

- **access-modifier** xác định phạm vi truy cập của lớp nếu lớp được khai báo ở cấp cao nhất hoặc bên trong một kiểu khác.
- **class** là từ khóa khai báo lớp.
- **ClassName** là tên lớp, thường dùng danh từ và viết theo PascalCase.
- Phần thân lớp nằm giữa cặp dấu ngoặc nhọn và chứa các thành viên.

Ví dụ:

~~~java
public class Product {
    private String name;
    private double price;

    public Product(String name, double price) {
        this.name = name;
        this.price = price;
    }

    public String getName() {
        return name;
    }

    public double getPrice() {
        return price;
    }
}
~~~

### Lớp cấp cao nhất và tên tệp

Lớp cấp cao nhất (top-level class) được khai báo trực tiếp trong một compilation unit, không nằm bên trong lớp khác. Một lớp cấp cao nhất có thể được khai báo **public** hoặc không ghi modifier truy cập (package-private).

Theo quy tắc tổ chức mã nguồn Java thông thường, nếu một compilation unit khai báo lớp cấp cao nhất **public**, tên tệp nguồn tương ứng phải trùng tên lớp đó và có phần mở rộng **.java**. Ví dụ, lớp **public class Product** được đặt trong tệp **Product.java**.

Một tệp nguồn có thể khai báo nhiều kiểu cấp cao nhất không public, nhưng mỗi kiểu vẫn phải có tên riêng trong package. Việc đặt mỗi lớp public trong tệp riêng giúp cấu trúc mã nguồn rõ ràng và dễ bảo trì.

### Thành viên của lớp

Các thành viên thường gặp gồm:

| Thành viên | Vai trò | Ví dụ |
|---|---|---|
| Field | Lưu trạng thái hoặc dữ liệu của lớp/đối tượng | **private String name;** |
| Constructor | Thiết lập trạng thái ban đầu khi tạo instance | **Product(String name) { ... }** |
| Instance method | Thực hiện thao tác trên một instance | **getName()** |
| Static field | Lưu dữ liệu dùng chung ở cấp lớp | **static int productCount;** |
| Static method | Thực hiện thao tác ở cấp lớp | **static int getProductCount()** |
| Nested type | Khai báo kiểu nằm trong phạm vi một kiểu khác | **static class Builder { ... }** |

Một lớp có thể có nhiều field, constructor và method. Các thành viên được truy cập theo phạm vi tên, modifier truy cập và ngữ cảnh gọi.

## 3. Field: dữ liệu của đối tượng và lớp

Field được khai báo trong thân lớp, bên ngoài thân method và constructor. Field instance thuộc về từng đối tượng; mỗi instance có bản lưu trữ riêng. Field **static** thuộc về lớp và được dùng chung.

~~~java
class User {
    private String username;              // Instance field
    private static int registeredUsers;   // Static field
}
~~~

Nếu tạo hai đối tượng **User**, mỗi đối tượng có field **username** riêng. Ngược lại, **registeredUsers** là một field static duy nhất gắn với lớp **User**.

### Giá trị mặc định của field

Field được gán giá trị mặc định theo kiểu khi đối tượng hoặc lớp được khởi tạo:

| Kiểu field | Giá trị mặc định |
|---|---|
| **byte**, **short**, **int**, **long** | Số 0 tương ứng |
| **float**, **double** | 0.0 tương ứng |
| **char** | Ký tự NUL (mã 0) |
| **boolean** | **false** |
| Kiểu tham chiếu | **null** |

Ví dụ:

~~~java
class Defaults {
    int count;
    boolean active;
    String label;

    void print() {
        System.out.println(count);  // 0
        System.out.println(active); // false
        System.out.println(label);  // null
    }
}
~~~

Quy tắc này áp dụng cho field và phần tử mảng. Biến cục bộ trong method không tự nhận giá trị mặc định; nó phải được gán trước khi đọc theo quy tắc definite assignment.

### Đóng gói trạng thái bằng private

Field thường được khai báo **private** để mã bên ngoài không thể tùy ý thay đổi trạng thái của đối tượng:

~~~java
class BankAccount {
    private final String accountNumber;
    private long balanceInCents;

    BankAccount(String accountNumber, long openingBalanceInCents) {
        this.accountNumber = accountNumber;
        this.balanceInCents = openingBalanceInCents;
    }

    public long getBalanceInCents() {
        return balanceInCents;
    }

    public void deposit(long amountInCents) {
        if (amountInCents <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }

        balanceInCents += amountInCents;
    }
}
~~~

Mã bên ngoài có thể gọi **deposit()** để thay đổi số dư thông qua quy tắc mà lớp cung cấp. Mã bên ngoài không thể truy cập trực tiếp **balanceInCents** vì field là **private**.

Đóng gói (encapsulation) giúp lớp kiểm soát cách trạng thái được đọc và thay đổi. Một method công khai có thể kiểm tra dữ liệu đầu vào, bảo đảm bất biến của đối tượng và thực hiện các thao tác cần thiết.

## 4. Constructor: khởi tạo đối tượng

Constructor là thành viên đặc biệt được gọi khi tạo instance. Constructor có tên trùng với tên lớp và không khai báo kiểu trả về, kể cả **void**.

~~~java
class Customer {
    private String name;

    public Customer(String name) {
        this.name = name;
    }
}
~~~

Khi thực hiện **new Customer("Lan")**, Java tạo instance và gọi constructor tương ứng. Constructor thiết lập trạng thái ban đầu cho đối tượng.

### Constructor không tham số

Một lớp có thể khai báo constructor không tham số:

~~~java
class Session {
    private boolean active;

    public Session() {
        active = true;
    }
}
~~~

Khi tạo đối tượng:

~~~java
Session session = new Session();
~~~

### Constructor có tham số

Constructor có thể nhận dữ liệu để thiết lập trạng thái:

~~~java
class Rectangle {
    private final double width;
    private final double height;

    public Rectangle(double width, double height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("Dimensions must be positive");
        }

        this.width = width;
        this.height = height;
    }

    public double area() {
        return width * height;
    }
}
~~~

Sử dụng:

~~~java
Rectangle rectangle = new Rectangle(4.0, 5.0);
System.out.println(rectangle.area()); // 20.0
~~~

Việc kiểm tra tham số trong constructor giúp đối tượng không được tạo với trạng thái không hợp lệ.

### Constructor mặc định và constructor tự khai báo

Nếu một lớp không khai báo constructor nào, trình biên dịch cung cấp một **default constructor** không tham số. Constructor mặc định này thực hiện khởi tạo theo quy tắc của Java và gọi constructor của lớp cha phù hợp.

~~~java
class EmptyService {
    // Không khai báo constructor.
    // Trình biên dịch cung cấp default constructor.
}
~~~

Có thể tạo instance bằng:

~~~java
EmptyService service = new EmptyService();
~~~

Nếu lớp đã khai báo ít nhất một constructor, trình biên dịch không tự sinh default constructor. Ví dụ:

~~~java
class Customer {
    private final String name;

    Customer(String name) {
        this.name = name;
    }
}
~~~

Lời gọi **new Customer()** không hợp lệ vì lớp chỉ có constructor nhận một tham số. Nếu cần tạo đối tượng không tham số, hãy khai báo constructor đó một cách tường minh.

Cần phân biệt **default constructor** do trình biên dịch sinh ra với constructor không tham số do lập trình viên tự viết. Cả hai đều không nhận tham số, nhưng nguồn gốc và phần thân của chúng khác nhau.

### Nạp chồng constructor

Một lớp có thể khai báo nhiều constructor với danh sách tham số khác nhau (constructor overloading):

~~~java
class UserProfile {
    private final String username;
    private final String displayName;

    UserProfile(String username) {
        this(username, username);
    }

    UserProfile(String username, String displayName) {
        this.username = username;
        this.displayName = displayName;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Constructor **UserProfile(String username)** gọi constructor khác trong cùng lớp bằng **this(...)**. Cách này giúp gom logic khởi tạo vào một nơi và tránh lặp mã.

## 5. this: tham chiếu tới đối tượng hiện tại

Trong một instance method hoặc constructor, **this** tham chiếu tới đối tượng hiện tại. Nó thường được dùng để phân biệt field với tham số hoặc biến cục bộ cùng tên.

~~~java
class Employee {
    private final String name;

    Employee(String name) {
        this.name = name;
    }

    public String getName() {
        return this.name;
    }
}
~~~

Trong constructor, **name** ở vế phải là tham số, còn **this.name** ở vế trái là field của instance.

**this** cũng có thể được dùng để gọi method khác của cùng đối tượng:

~~~java
class Printer {
    public void printLine(String message) {
        System.out.println(message);
    }

    public void printWelcome() {
        this.printLine("Welcome");
    }
}
~~~

Dùng **this(...)** trong constructor để gọi một constructor khác của cùng lớp:

~~~java
class Point {
    private final int x;
    private final int y;

    Point() {
        this(0, 0);
    }

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}
~~~

Một constructor chỉ có thể ủy quyền trực tiếp tới một constructor khác trong cùng lớp bằng **this(...)**. Không tạo chuỗi gọi constructor đệ quy, vì việc khởi tạo phải có điểm kết thúc.

Không thể dùng **this** trong ngữ cảnh static vì method hoặc initializer static không gắn với một instance cụ thể.

## 6. Tạo đối tượng bằng new

Biểu thức tạo đối tượng thông thường có dạng:

~~~java
ClassName variableName = new ClassName(arguments);
~~~

Ví dụ:

~~~java
Customer customer = new Customer("Lan");
~~~

Các thành phần:

- **Customer** ở bên trái là kiểu tham chiếu của biến.
- **customer** là tên biến tham chiếu.
- **new** yêu cầu tạo một instance mới.
- **Customer("Lan")** chọn constructor phù hợp và truyền đối số vào.

Sau khi tạo thành công, biểu thức **new** cung cấp một tham chiếu tới đối tượng vừa tạo. Biến **customer** lưu tham chiếu đó để mã nguồn có thể truy cập instance.

### Mỗi lần new tạo một instance mới

~~~java
Customer first = new Customer("Lan");
Customer second = new Customer("Lan");
~~~

Hai biểu thức **new** tạo hai instance độc lập, dù đối số truyền vào giống nhau. Phép so sánh **==** giữa hai biến tham chiếu kiểm tra chúng có trỏ tới cùng một đối tượng hay không; nó không so sánh nội dung các field.

### Nhiều biến tham chiếu có thể cùng trỏ tới một đối tượng

~~~java
Customer first = new Customer("Lan");
Customer alias = first;

System.out.println(first == alias); // true
~~~

Phép gán **alias = first** sao chép giá trị tham chiếu. Nó không tạo một instance mới và cũng không sao chép toàn bộ trạng thái đối tượng.

Nếu đối tượng có trạng thái thay đổi được, việc thay đổi thông qua một tham chiếu sẽ được nhìn thấy khi truy cập cùng đối tượng qua tham chiếu còn lại. Đây là lý do cần hiểu rõ sự khác nhau giữa biến tham chiếu và đối tượng được tham chiếu.

### Tham chiếu null

Một biến tham chiếu có thể nhận giá trị **null**, nghĩa là hiện tại nó không tham chiếu tới đối tượng nào:

~~~java
Customer customer = null;
~~~

Không thể gọi instance method hoặc truy cập instance field thông qua tham chiếu **null**. Thao tác đó gây **NullPointerException** khi được thực thi:

~~~java
Customer customer = null;
// customer.getName(); // Ném NullPointerException khi thực thi
~~~

Nếu tham chiếu có thể là **null**, hãy kiểm tra trước khi truy cập hoặc thiết kế API để tránh truyền giá trị null ngoài ý muốn. Có thể dùng **Objects.requireNonNull()** ở ranh giới phù hợp để kiểm tra đầu vào bắt buộc:

~~~java
import java.util.Objects;

class GreetingService {
    public void greet(String name) {
        Objects.requireNonNull(name, "name");
        System.out.println("Hello, " + name);
    }
}
~~~

## 7. Truy cập field và gọi method

Sau khi có tham chiếu tới đối tượng, dùng toán tử dấu chấm (**.**) để truy cập thành viên được phép:

~~~java
reference.fieldName
reference.methodName(arguments)
~~~

Ví dụ:

~~~java
class Lamp {
    private boolean on;

    public void turnOn() {
        on = true;
    }

    public boolean isOn() {
        return on;
    }
}

Lamp deskLamp = new Lamp();

deskLamp.turnOn();
System.out.println(deskLamp.isOn()); // true
~~~

Trong ví dụ, **deskLamp.turnOn()** gọi instance method trên đối tượng được tham chiếu bởi **deskLamp**. Field **on** là private nên mã bên ngoài lớp không thể viết **deskLamp.on**; trạng thái được truy cập thông qua method công khai.

### Truy cập thành viên instance

Instance field và instance method cần một đối tượng cụ thể để xác định trạng thái hoặc hành vi đang thao tác:

~~~java
Lamp firstLamp = new Lamp();
Lamp secondLamp = new Lamp();

firstLamp.turnOn();

System.out.println(firstLamp.isOn());  // true
System.out.println(secondLamp.isOn()); // false
~~~

Hai đối tượng có trạng thái riêng. Gọi **turnOn()** trên **firstLamp** không làm thay đổi **secondLamp**.

### Truy cập thành viên static

Thành viên **static** thuộc về lớp. Nên truy cập chúng bằng tên lớp thay vì thông qua một instance:

~~~java
class IdGenerator {
    private static int nextId = 1;

    public static int next() {
        return nextId++;
    }
}

int firstId = IdGenerator.next();
int secondId = IdGenerator.next();
~~~

**nextId** được chia sẻ bởi các lời gọi static method của lớp **IdGenerator**. Không cần tạo đối tượng **IdGenerator** để gọi **next()**.

Một static method không thể truy cập trực tiếp instance field hoặc gọi instance method nếu chưa có tham chiếu tới một đối tượng cụ thể. Nó có thể nhận một tham chiếu làm tham số rồi thao tác trên đối tượng đó.

~~~java
class User {
    private String name;

    User(String name) {
        this.name = name;
    }

    public static void printName(User user) {
        System.out.println(user.name);
    }
}
~~~

Trong **printName()**, mã truy cập field thông qua tham chiếu **user**. Nếu **user** là null, thao tác truy cập sẽ gây NullPointerException.

## 8. Modifier truy cập của lớp và thành viên

Modifier truy cập quyết định mã nguồn nào được phép sử dụng lớp hoặc thành viên. Bốn mức truy cập phổ biến là:

| Modifier | Phạm vi truy cập |
|---|---|
| **public** | Có thể truy cập từ mã nguồn được phép nhìn thấy kiểu/thành viên theo package và module |
| **protected** | Truy cập trong cùng package và trong các lớp con theo quy tắc protected |
| Không ghi modifier (package-private) | Chỉ truy cập từ các kiểu trong cùng package |
| **private** | Chỉ truy cập trong phạm vi thân lớp hoặc kiểu khai báo thành viên theo quy tắc private của Java |

Ví dụ:

~~~java
package com.example.catalog;

public class Product {
    public String publicCode;
    protected String category;
    String internalLabel;
    private double cost;
}
~~~

Một lớp khác trong cùng package có thể truy cập các thành viên package-private và protected theo quy tắc của Java. Lớp nằm ngoài package không thể truy cập **internalLabel** chỉ bằng cách tạo đối tượng **Product**. Thành viên **private** không được truy cập trực tiếp từ lớp bên ngoài.

Với lớp cấp cao nhất, chỉ dùng **public** hoặc package-private. Các lớp lồng bên trong có thể dùng những modifier truy cập phù hợp với vị trí khai báo.

### Thiết kế quyền truy cập hợp lý

Một thiết kế phổ biến là:

- Khai báo lớp **public** khi nó là kiểu được các package khác sử dụng.
- Giữ field ở mức **private** để bảo vệ trạng thái.
- Chỉ mở method hoặc constructor **public** khi đó là một phần API cần cung cấp.
- Dùng package-private cho chi tiết triển khai chỉ cần chia sẻ giữa các lớp trong cùng package.
- Dùng **protected** khi thiết kế thực sự cần điểm mở rộng cho lớp con hoặc mã cùng package.

Không nên công khai mọi field chỉ để mã bên ngoài dễ thao tác. API của lớp nên cung cấp các hành động có ý nghĩa và kiểm soát dữ liệu hợp lệ.

## 9. Ví dụ tổng hợp: khai báo lớp, tạo và sử dụng đối tượng

Ví dụ sau kết hợp field private, constructor, method instance, static field, static method, tạo đối tượng và truy cập thành viên.

Tệp **Book.java**:

~~~java
import java.util.Objects;

public class Book {
    private final String title;
    private final String author;
    private static int createdCount;

    public Book(String title, String author) {
        this.title = Objects.requireNonNull(title, "title");
        this.author = Objects.requireNonNull(author, "author");
        createdCount++;
    }

    public String getTitle() {
        return title;
    }

    public String getAuthor() {
        return author;
    }

    public void printDetails() {
        System.out.println(title + " - " + author);
    }

    public static int getCreatedCount() {
        return createdCount;
    }
}
~~~

Tệp **BookDemo.java**:

~~~java
public class BookDemo {
    public static void main(String[] args) {
        Book first = new Book("Effective Java", "Joshua Bloch");
        Book second = new Book("Java Concurrency in Practice", "Brian Goetz");

        first.printDetails();
        second.printDetails();

        System.out.println(first.getTitle());
        System.out.println(Book.getCreatedCount());

        Book alias = first;
        System.out.println(first == alias); // true
        System.out.println(first == second); // false
    }
}
~~~

Kết quả:

~~~text
Effective Java - Joshua Bloch
Java Concurrency in Practice - Brian Goetz
Effective Java
2
true
false
~~~

Giải thích:

- **Book** là lớp mô tả cấu trúc của một quyển sách.
- **title** và **author** là instance field private final, được thiết lập trong constructor.
- **createdCount** là static field dùng chung cho tất cả instance **Book**.
- Constructor nhận hai tham số, kiểm tra chúng không null và thiết lập field bằng **this**.
- **getTitle()**, **getAuthor()** và **printDetails()** là instance method, được gọi qua tham chiếu đối tượng.
- **getCreatedCount()** là static method, được gọi bằng tên lớp **Book**.
- **alias** nhận cùng tham chiếu với **first**, nên **first == alias** là true. **second** được tạo bằng một biểu thức **new** khác nên là instance khác.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không thể tạo đối tượng bằng **new ClassName()** | Lớp không có constructor phù hợp, hoặc là lớp abstract | Khai báo constructor phù hợp hoặc tạo instance của lớp concrete |
| Gọi constructor như method và khai báo kiểu trả về | Constructor không có kiểu trả về và phải trùng tên lớp | Bỏ kiểu trả về, dùng đúng tên lớp |
| Gọi instance method từ ngữ cảnh static mà không có đối tượng | Instance method cần một instance cụ thể | Tạo hoặc nhận tham chiếu đối tượng rồi gọi method qua tham chiếu |
| Truy cập field private từ lớp bên ngoài | Modifier **private** giới hạn quyền truy cập | Cung cấp method phù hợp để đọc hoặc thay đổi trạng thái |
| Gặp NullPointerException | Tham chiếu đang có giá trị **null** khi truy cập thành viên | Kiểm tra null hoặc bảo đảm tham chiếu được khởi tạo hợp lệ |
| Hai biến thay đổi cùng một đối tượng ngoài dự kiến | Hai biến lưu cùng một tham chiếu | Xác định rõ việc chia sẻ đối tượng; tạo instance mới nếu cần đối tượng riêng |
| Gọi **new ClassName()** nhưng không có constructor không tham số | Lớp đã khai báo constructor khác nên không có default constructor tự sinh | Tự khai báo constructor không tham số nếu API cần nó |
| Truy cập thành viên static thông qua đối tượng | Nhầm thành viên cấp lớp với thành viên instance | Gọi bằng tên lớp để thể hiện rõ ngữ nghĩa |

## 11. Nguyên tắc thực hành

Khi thiết kế và sử dụng lớp, nên ghi nhớ:

- Mỗi lớp nên mô tả một khái niệm hoặc trách nhiệm có ý nghĩa trong chương trình.
- Dùng tên lớp là danh từ, tên method là động từ hoặc cụm động từ để mã dễ đọc.
- Khai báo field **private** và chỉ cung cấp thao tác truy cập cần thiết.
- Dùng constructor để thiết lập trạng thái hợp lệ ngay khi tạo instance.
- Dùng **final** cho field không cần gán lại sau khởi tạo.
- Phân biệt instance member với static member và chọn cách gọi tương ứng.
- Kiểm tra các tham chiếu có thể null trước khi gọi method hoặc truy cập field.
- Không nhầm phép gán tham chiếu với việc tạo hoặc sao chép đối tượng.
- Tạo API công khai nhỏ, rõ nghĩa và giữ các chi tiết triển khai ở phạm vi package hoặc private khi phù hợp.

Khi đọc mã Java 27, hãy nhận diện lớp nào định nghĩa kiểu, constructor nào được gọi, biến nào đang giữ tham chiếu tới instance và thành viên nào được phép truy cập. Nắm rõ các điểm này giúp tạo đối tượng đúng cách, sử dụng trạng thái có kiểm soát và tổ chức chương trình theo mô hình hướng đối tượng của Java.
