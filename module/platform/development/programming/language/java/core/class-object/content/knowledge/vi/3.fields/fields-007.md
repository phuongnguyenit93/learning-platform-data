# Đọc và cập nhật trường bằng toán tử dấu chấm trong Java

Trong Java, **toán tử dấu chấm** (`.`) được dùng để truy cập **thành viên** của một kiểu hoặc đối tượng. Với **trường dữ liệu** (*field*), cú pháp `object.field` hoặc `ClassName.staticField` cho phép **đọc** giá trị và, nếu trường cho phép ghi và mã có quyền truy cập, **cập nhật** giá trị.

Ví dụ:

```java
Student student = new Student();
student.age = 20;                       // Ghi giá trị mới vào trường age
System.out.println(student.age);        // Đọc trường age: 20
```

Đây là đoạn minh họa, giả sử đã có lớp `Student` với trường `age` truy cập được. Dấu chấm không tự tạo đối tượng, cũng không tự động gọi getter/setter: `student.age` trực tiếp biểu thị trường đã được chọn, còn `student.getAge()` mới là lời gọi phương thức.

Bài này tập trung vào **đọc và cập nhật field** bằng dấu chấm: cú pháp, cách xác định đối tượng bị sửa, instance/static field, `this`, `final`, phạm vi truy cập, `null`, kế thừa và các lỗi thường gặp.

## 1. Trường dữ liệu là gì?

**Field** là biến được khai báo trong thân lớp (hoặc một kiểu có thể chứa field), ở cấp **thành viên**, bên ngoài các phương thức/constructor/khối cục bộ. Field dùng để lưu trạng thái hoặc dữ liệu gắn với lớp hoặc một thể hiện.

```java
class Product {
    String name;                   // Instance field
    int quantity;                  // Instance field
    static int totalCreated;       // Static field

    void add(int amount) {
        int newQuantity = quantity + amount; // newQuantity là biến cục bộ
        quantity = newQuantity;               // quantity là field
    }
}
```

- `name` và `quantity` là **instance fields**: mỗi đối tượng `Product` có trạng thái trường riêng.
- `totalCreated` là **static field**: một trường gắn với lớp `Product` (chính xác hơn, với bản định nghĩa lớp được nạp), dùng chung giữa các thể hiện.
- `newQuantity` là **biến cục bộ**, không thể được đọc thành `product.newQuantity` từ ngoài phương thức.
- Tham số `amount` cũng không phải field: chỉ tồn tại trong phạm vi lời gọi `add`.

Phân biệt **field** và **local variable** giúp biết khi nào có thể sử dụng dấu chấm. Dấu chấm phải chọn một thành viên hợp lệ của kiểu hoặc đối tượng, chứ không thể chọn tùy ý mọi tên biến xuất hiện trong mã nguồn.

## 2. Cú pháp đọc và cập nhật instance field

Giả sử lớp có hai trường truy cập được:

```java
class Rectangle {
    int width;
    int height;
}
```

Trong một phương thức chứa biến tham chiếu `rectangle` có kiểu `Rectangle`:

```java
Rectangle rectangle = new Rectangle();

rectangle.width = 4;              // Ghi instance field
rectangle.height = 3;             // Ghi instance field

int w = rectangle.width;          // Đọc instance field
int area = rectangle.width * rectangle.height;

System.out.println(w);            // 4
System.out.println(area);         // 12
```

Cú pháp quan trọng:

| Cách viết | Tác dụng | Ví dụ |
| --- | --- | --- |
| `object.field` ở phía cần giá trị | Đọc giá trị hiện tại của trường | `int n = rectangle.width;` |
| `object.field = expression;` | Tính biểu thức bên phải rồi gán vào trường | `rectangle.width = 10;` |
| `object.field += expression;` | Đọc, tính toán rồi ghi lại trường | `rectangle.width += 2;` |
| `object.field++;` | Tăng giá trị trường kiểu số phù hợp lên 1 | `rectangle.width++;` |
| `object.field = other.field;` | Sao chép **giá trị** từ trường khác | `a.width = b.width;` |
| `object.method()` | **Gọi phương thức**, không phải cú pháp đọc field | `rectangle.toString();` |

Biến `rectangle` phải tham chiếu đến đối tượng hợp lệ khi truy cập instance field. Việc `rectangle.width = 10` không tạo một `Rectangle` khác; nó thay đổi field `width` trong **đối tượng hiện được tham chiếu**.

Biểu thức sau dấu `=` phải có kiểu **tương thích** với kiểu khai báo của trường. Chẳng hạn `rectangle.width = "rộng";` không biên dịch vì `width` có kiểu `int` còn `"rộng"` là `String`.

Một phép **đọc** field có thể tham gia biểu thức (`rectangle.width * 2`), điều kiện (`rectangle.width > 0`) hoặc lời gọi phương thức (`Math.max(rectangle.width, 1)`). Một phép **ghi** field phải tuân thủ khả năng gán và quyền truy cập (xem mục `final` và `private`).

## 3. Chương trình Java 17 chạy được: đọc, ghi, tăng giá trị và alias

Lưu toàn bộ mã dưới đây vào tệp **`FieldAccessDemo.java`**:

```java
class Account {
    String owner;
    int balance;
    static int created;

    Account(String owner, int balance) {
        this.owner = owner;
        this.balance = balance;
        created++;
    }
}

public class FieldAccessDemo {
    public static void main(String[] args) {
        Account account = new Account("Lan", 100);

        System.out.println(account.owner);
        System.out.println(account.balance);

        account.balance = 130;
        account.balance += 20;
        System.out.println(account.balance);

        Account alias = account;
        alias.balance++;
        System.out.println(account.balance);

        Account other = new Account("Minh", 50);
        System.out.println(other.owner);
        System.out.println(Account.created);

        System.out.println(account == alias);
        System.out.println(account == other);
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 FieldAccessDemo.java
java FieldAccessDemo
```

**Stdout chính xác:**

```text
Lan
100
150
151
Minh
2
true
false
```

Diễn giải:

1. `new Account("Lan", 100)` tạo đối tượng đầu tiên với `owner = "Lan"` và `balance = 100`.
2. `account.owner` và `account.balance` đọc **trường của đối tượng đó**.
3. `account.balance = 130` ghi đè số dư cũ; `account.balance += 20` đọc `130` rồi ghi `150`.
4. `Account alias = account;` chỉ **sao chép giá trị tham chiếu**, không tạo đối tượng mới. `alias.balance++` cập nhật cùng một đối tượng, nên `account.balance` đọc ra `151`.
5. `other` tham chiếu một đối tượng khác có `owner = "Minh"`. Mọi lần thực thi constructor `Account` đều tăng trường static `created`, nên `Account.created` bằng `2`.
6. Toán tử `==` với hai biến tham chiếu kiểm tra chúng có tham chiếu cùng đối tượng không; `account == alias` là `true`, còn `account == other` là `false`.

Sơ đồ logic trước khi in các dòng cuối:

```text
account ──┐
          ├──> Account #1 { owner: "Lan", balance: 151 }
alias   ──┘

other   ─────> Account #2 { owner: "Minh", balance: 50 }

Account.created = 2   (static: gắn với lớp)
```

`#1` và `#2` chỉ là nhãn minh họa danh tính, không phải địa chỉ bộ nhớ thực tế.

Điểm mấu chốt: **dấu chấm truy cập trường của đối tượng mà biểu thức bên trái đang tham chiếu**, không gắn trường vĩnh viễn với tên biến. Vì vậy hai biến cùng tham chiếu một đối tượng có thể thấy cùng một thay đổi.

## 4. Gán lại biến tham chiếu khác với cập nhật field

Hai thao tác này trông gần giống nhau nhưng khác hoàn toàn:

```java
Account first = new Account("An", 100);
Account second = new Account("Bình", 200);

first.balance = 150;       // Sửa trường balance trên đối tượng first tham chiếu
first = second;            // Gán lại biến first, KHÔNG sửa object nào
```

Đoạn này dùng lớp `Account` ở mục 3, không phải một chương trình độc lập. Sau dòng cuối, cả `first` và `second` đều tham chiếu đối tượng của `"Bình"` (số dư `200`). Đối tượng ban đầu của `first` vẫn giữ số dư `150` chừng nào nó còn tồn tại; việc mất một tham chiếu không tự biến nó thành số dư `200`.

Có thể tự xác định tác dụng từ **vế trái phép gán**:

- `first = second;`: nơi nhận phép gán là **biến tham chiếu** `first`.
- `first.balance = 150;`: nơi nhận phép gán là **field** `balance` của đối tượng hiện được chọn qua `first`.
- `first.owner = "Linh";`: nơi nhận phép gán là **field tham chiếu `owner`** của đối tượng; việc gán chuỗi mới thay đổi giá trị tham chiếu của field, không chỉnh sửa bên trong đối tượng `String` cũ.

Nếu field có kiểu tham chiếu, phép gán cũng **sao chép giá trị tham chiếu**. Nó không tự sao chép sâu (deep copy) đối tượng được tham chiếu.

## 5. Dùng `this.field` trong lớp để đọc/ghi chính trường của đối tượng

Bên trong **instance method** hoặc **constructor**, có thể dùng `this` để biểu thị đối tượng hiện tại.

```java
class User {
    String name;

    User(String name) {
        this.name = name;
    }

    void rename(String name) {
        this.name = name;
    }

    void printName() {
        System.out.println(this.name);
    }
}
```

Ở `User(String name)`, tham số `name` có tên trùng field `name`:

- `name` đứng một mình trong phương thức/constructor trỏ tới **tham số** gần nhất vì có hiện tượng *shadowing*.
- `this.name` trỏ tới **instance field** của đối tượng hiện tại.
- `this.name = name;` gán giá trị tham số vào trường của đối tượng.

Nếu không có một biến hoặc tham số cùng tên che khuất, trong instance method có thể viết `name` thay `this.name`. Tuy nhiên, `this.name` hữu ích để làm rõ đang thao tác với field.

**Không thể dùng `this` trong static method hoặc static initializer**, vì chúng không có đối tượng `this`. Muốn truy cập instance field từ phương thức `static`, cần có một tham chiếu tới đối tượng cụ thể:

```java
class User {
    String name;

    static void show(User user) {
        System.out.println(user.name);
    }
}
```

Hai đoạn khai báo `User` trên chỉ là **ví dụ thay thế**, không nên biên dịch trong cùng package/tập nguồn ở cùng một lần vì sẽ định nghĩa trùng lớp `User`.

## 6. Đọc và cập nhật static field qua tên lớp

Một trường khai báo với `static` **thuộc lớp**, không thuộc một thể hiện riêng:

```java
class Settings {
    static String environment = "dev";
    int retries = 3;
}
```

Ví dụ sử dụng bên trong một phương thức:

```java
System.out.println(Settings.environment); // dev
Settings.environment = "prod";
System.out.println(Settings.environment); // prod

Settings instance = new Settings();
System.out.println(instance.retries);      // 3
```

Với field `static`, **ưu tiên `ClassName.field`**: `Settings.environment`. Một câu lệnh như `instance.environment` có thể được Java chấp nhận nhưng nên tránh, vì gợi nhầm rằng `environment` là trạng thái riêng của từng đối tượng.

Đặc biệt:

- `static` không có nghĩa bất biến: `Settings.environment = "prod"` hợp lệ vì trường không `final`.
- `static final` thường dùng để định nghĩa hằng số, nhưng trường có kiểu tham chiếu `static final` không đảm bảo đối tượng được tham chiếu là bất biến.
- Trường `static` có phạm vi truy cập riêng. `private static` chỉ truy cập được từ vị trí được phép theo quy tắc Java, không phải vì static mà thành public.
- Việc dùng `this.environment` nếu được viết trong instance method vẫn biểu thị **static field**, nhưng dễ gây hiểu nhầm và nên thay bằng `Settings.environment`.

### Ví dụ hoàn chỉnh: các đối tượng cùng nhìn thấy static field

Lưu thành **`StaticFieldDemo.java`**:

```java
class Config {
    static int maxConnections = 10;
    int currentConnections;

    Config(int currentConnections) {
        this.currentConnections = currentConnections;
    }
}

public class StaticFieldDemo {
    public static void main(String[] args) {
        Config first = new Config(2);
        Config second = new Config(5);

        System.out.println(first.currentConnections);
        System.out.println(second.currentConnections);
        System.out.println(Config.maxConnections);

        Config.maxConnections = 20;
        second.currentConnections = 7;

        System.out.println(Config.maxConnections);
        System.out.println(first.currentConnections);
        System.out.println(second.currentConnections);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 StaticFieldDemo.java
java StaticFieldDemo
```

Kết quả:

```text
2
5
10
20
2
7
```

`currentConnections` là instance field nên sửa `second.currentConnections` không làm thay đổi `first.currentConnections`. `maxConnections` là một static field, nên truy cập qua tên lớp `Config` phản ánh cùng một giá trị dùng chung.

## 7. Toán tử dấu chấm với nhiều mức và đối tượng lồng tham chiếu

Một field có thể giữ tham chiếu đến đối tượng khác. Khi đó có thể nối nhiều dấu chấm để truy cập field:

```java
class Address {
    String city;
}

class Customer {
    Address address;
}
```

Sử dụng trong một phương thức:

```java
Customer customer = new Customer();
customer.address = new Address();
customer.address.city = "Hà Nội";

System.out.println(customer.address.city); // Hà Nội
```

`customer.address.city` được hiểu về mặt logic là:

1. Đọc `customer`, nhận tham chiếu đến đối tượng `Customer`.
2. Đọc field `address` của `Customer`, nhận tham chiếu đến một đối tượng `Address`.
3. Đọc hoặc ghi field `city` của đối tượng `Address` đó.

**Một cấp tham chiếu trung gian là `null` thì truy cập cấp tiếp theo có thể ném `NullPointerException`.** Ví dụ sau có lỗi runtime:

```java
Customer customer = new Customer();
System.out.println(customer.address.city); // NullPointerException
```

Lý do: `address` chưa được gán nên nhận giá trị mặc định `null`. Java **không có cú pháp safe navigation `customer?.address?.city`** trong Java 17. Có thể kiểm tra:

```java
if (customer != null && customer.address != null) {
    System.out.println(customer.address.city);
}
```

Đây là những đoạn minh họa để đặt vào một phương thức có thể truy cập các lớp nêu trên; chúng không phải tệp chương trình độc lập. Tùy thiết kế, tốt hơn là yêu cầu đối tượng hợp lệ ngay ở constructor thay vì cho phép field quan trọng ở trạng thái `null`.

## 8. `null`: trước khi đọc field, phải có receiver hợp lệ

Một instance field kiểu số có thể mặc định `0`, còn reference field như `String label` có thể mặc định `null`. Nhưng **đọc `box.count` chỉ hợp lệ ở runtime khi `box` tham chiếu một đối tượng**; nếu chính `box == null` thì đọc instance field sẽ ném `NullPointerException`. Nếu `box` không null nhưng `box.label == null`, việc lấy reference field trả về null, còn gọi tiếp `box.label.length()` mới thất bại. Biến cục bộ muốn được đọc cũng phải thỏa *definite assignment* ở compile time.

Bài này nhấn mạnh thứ tự kiểm tra của **biểu thức dấu chấm và receiver**, không trình bày lại bảng mặc định của mọi primitive type.

Ví dụ chạy được, lưu thành **`NullFieldDemo.java`**:

```java
class Box {
    int count;
    String label;
}

public class NullFieldDemo {
    public static void main(String[] args) {
        Box box = new Box();

        System.out.println(box.count);
        System.out.println(box.label);

        Box absent = null;
        System.out.println(absent == null);

        try {
            System.out.println(absent.count);
        } catch (NullPointerException ex) {
            System.out.println("Không thể đọc instance field qua null");
        }
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 NullFieldDemo.java
java NullFieldDemo
```

Stdout:

```text
0
null
true
Không thể đọc instance field qua null
```

`box.count` đọc được vì `box` là đối tượng đã tạo, field kiểu `int` chưa gán nhận `0`. `absent.count` gây `NullPointerException` vì `absent` không tham chiếu đến đối tượng `Box` nào.

**Lưu ý riêng với static field:** nếu viết `Box b = null;` rồi truy cập `b.someStaticField` (giả sử `someStaticField` đã khai báo static trong `Box`), Java có thể vẫn truy cập static field thành công, vì field đó không được lấy từ đối tượng `b`. Đây **không** phải cách nên viết: luôn sử dụng `Box.someStaticField` để tránh nhầm lẫn.

## 9. Quyền truy cập field: dấu chấm không vượt qua access modifier

Toán tử dấu chấm chỉ hợp lệ khi **đường truy cập được Java cho phép**. Không thể đọc hoặc sửa field `private` từ một lớp tùy ý chỉ vì biết tên biến và tên field.

| Modifier của field | Nơi truy cập điển hình |
| --- | --- |
| `public` | Mã có thể truy cập kiểu chứa field, subject to module và các điều kiện Java liên quan |
| `protected` | Cùng package và các trường hợp truy cập qua kế thừa từ package khác theo quy tắc `protected` |
| Không ghi modifier (package-private) | Các lớp trong cùng package |
| `private` | Chỉ trong phạm vi khai báo cho phép của kiểu chứa field và các ngữ cảnh Java liên quan |

Ví dụ:

```java
class Wallet {
    private int money = 100;
}

class Reader {
    void show(Wallet wallet) {
        // System.out.println(wallet.money); // SAI: money private trong Wallet
    }
}
```

Hai lớp ở cùng package cũng không được phép truy cập trực tiếp field `private` của nhau chỉ vì cùng package.

**Điểm tinh tế:** các phương thức nằm trong chính lớp `Wallet` có thể truy cập field `private` của **một đối tượng Wallet khác**, chẳng hạn `other.money`; `private` hạn chế **vị trí mã được phép truy cập**, chứ không gắn bí mật với duy nhất đối tượng `this`.

### Đóng gói: nên cập nhật qua phương thức khi cần kiểm tra dữ liệu

Dấu chấm không phải lúc nào cũng được dùng để sửa field trực tiếp. Một thiết kế phổ biến là giữ field `private` và cung cấp phương thức đọc/ghi có kiểm tra điều kiện.

Lưu thành **`EncapsulationDemo.java`**:

```java
class BankAccount {
    private int balance;

    BankAccount(int initialBalance) {
        if (initialBalance < 0) {
            throw new IllegalArgumentException("Số dư âm");
        }
        this.balance = initialBalance;
    }

    int getBalance() {
        return balance;
    }

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số tiền nạp phải dương");
        }
        this.balance += amount;
    }
}

public class EncapsulationDemo {
    public static void main(String[] args) {
        BankAccount account = new BankAccount(100);

        System.out.println(account.getBalance());
        account.deposit(50);
        System.out.println(account.getBalance());

        // account.balance = -100; // Lỗi biên dịch: field private
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 EncapsulationDemo.java
java EncapsulationDemo
```

Stdout:

```text
100
150
```

`account.getBalance()` và `account.deposit(50)` **gọi phương thức**, còn `this.balance` trong `BankAccount` **truy cập trực tiếp field**. Cùng dùng dấu chấm nhưng việc thêm `()` cho thấy lệnh gọi method thay vì truy cập field.

Đóng gói giúp bảo vệ điều kiện hợp lệ (*invariant*) như số dư không âm, kiểm soát thay đổi dữ liệu và giảm phụ thuộc vào cấu trúc field. Không nhất thiết tạo getter/setter cho mọi field; hãy chọn API theo yêu cầu của đối tượng.

## 10. `final`: khi nào không thể cập nhật field bằng dấu chấm?

Một field khai báo `final` chỉ được gán theo **quy tắc khởi tạo final**. Sau khi khởi tạo, không được gán giá trị mới vào field đó.

```java
class Ticket {
    final int id;
    String owner;

    Ticket(int id, String owner) {
        this.id = id;            // Gán final field trong constructor: hợp lệ
        this.owner = owner;
    }
}
```

Dùng trong phương thức:

```java
Ticket ticket = new Ticket(7, "An");

System.out.println(ticket.id);     // 7
ticket.owner = "Bình";             // Hợp lệ
// ticket.id = 8;                  // SAI: không thể gán lại final field
// ticket.id++;                    // SAI: tăng cũng là cập nhật final field
```

**Phân biệt hai tình huống thường bị nhầm:**

```java
final Ticket ticket = new Ticket(7, "An");
ticket.owner = "Bình";              // Hợp lệ: sửa đối tượng được tham chiếu
// ticket = new Ticket(8, "Lan");   // SAI: biến tham chiếu final không được gán lại
```

- `final Ticket ticket` khóa **việc gán lại biến `ticket`**, không làm toàn bộ đối tượng bất biến.
- `final int id` khóa **giá trị field `id`** sau bước khởi tạo được phép.
- Một field `final` kiểu tham chiếu như `final List<String> items` giữ nguyên **tham chiếu field** sau khi khởi tạo, nhưng nội dung `List` vẫn có thể thay đổi nếu danh sách đó cho phép. Để có tính bất biến cần thiết kế chặt hơn.

Ngoài `final`, field có thể không ghi được vì **quyền truy cập**, vì đối tượng không tồn tại, hoặc vì những ràng buộc cụ thể của ngôn ngữ đối với loại field.

## 11. Trường bị che khuất trong kế thừa: dấu chấm chọn field theo kiểu tham chiếu

Một trường dữ liệu **không được override đa hình như instance method**. Khi lớp con khai báo field trùng tên với lớp cha, đó là **field hiding**; việc chọn field dựa trên **kiểu tại thời điểm biên dịch của biểu thức bên trái dấu chấm** và các quy tắc tra cứu thành viên.

Lưu thành **`FieldHidingDemo.java`**:

```java
class Parent {
    String label = "cha";

    String describe() {
        return "method cha";
    }
}

class Child extends Parent {
    String label = "con";

    @Override
    String describe() {
        return "method con";
    }
}

public class FieldHidingDemo {
    public static void main(String[] args) {
        Parent asParent = new Child();
        Child asChild = new Child();

        System.out.println(asParent.label);
        System.out.println(asParent.describe());
        System.out.println(asChild.label);
        System.out.println(((Child) asParent).label);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 FieldHidingDemo.java
java FieldHidingDemo
```

Stdout:

```text
cha
method con
con
con
```

Tại sao?

- `asParent.label` đọc **field của `Parent`** do kiểu biểu thức `asParent` là `Parent`. Mặc dù đối tượng thực tế là `Child`, truy cập field không phân phối động như phương thức.
- `asParent.describe()` gọi phiên bản override của `Child` vì đây là **instance method** hỗ trợ phân phối động.
- `asChild.label` đọc field `label` của `Child`.
- `((Child) asParent).label` đọc field `label` của `Child` vì phép ép kiểu hợp lệ đã thay đổi kiểu biên dịch của biểu thức chọn thành viên.

Một đối tượng `Child` trong ví dụ thực tế có **hai field khác nhau** cùng tên `label` (một kế thừa từ `Parent` và một khai báo ở `Child`). Trong mã lớp con, có thể dùng `super.label` để truy cập field của lớp cha nếu được phép theo quy tắc truy cập Java.

**Khuyến nghị:** tránh khai báo field cùng tên giữa cha/con khi không có lý do rõ ràng; ưu tiên đóng gói và phương thức để tránh nhầm lẫn giữa field hiding và method overriding.

## 12. `+=`, `++` và phép cập nhật kết hợp: đọc rồi ghi

Các phép toán cập nhật field thường có **hai phần logic**: đọc giá trị hiện tại và ghi giá trị mới.

```java
counter.value = counter.value + 1;
counter.value += 1;
counter.value++;
++counter.value;
```

Nếu `counter.value` là field `int` thông thường và `counter` tham chiếu đối tượng hợp lệ, cả bốn cách đều **tăng giá trị field lên một**, nhưng chúng không hoàn toàn tương đương trong mọi biểu thức:

- `counter.value++` là **post-increment**: giá trị của chính biểu thức là **giá trị cũ**, còn field nhận giá trị tăng.
- `++counter.value` là **pre-increment**: giá trị của chính biểu thức là **giá trị mới**.
- `counter.value += 1` là **compound assignment**: kết hợp phép cộng và gán, có quy tắc kiểu và chuyển đổi riêng của Java; không nên coi nó đồng nhất mọi mặt với `counter.value = counter.value + 1`.
- `counter.value = counter.value + 1` viết rõ phép đọc, cộng, rồi gán lại nhưng có thể đánh giá biểu thức bên trái/receiver theo quy tắc khác khi receiver là một biểu thức có tác dụng phụ.

Ví dụ hoàn chỉnh, tệp **`IncrementDemo.java`**:

```java
class Counter {
    int value = 5;
}

public class IncrementDemo {
    public static void main(String[] args) {
        Counter counter = new Counter();

        int before = counter.value++;
        int after = ++counter.value;

        System.out.println(before);
        System.out.println(after);
        System.out.println(counter.value);

        counter.value += 3;
        System.out.println(counter.value);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 IncrementDemo.java
java IncrementDemo
```

Stdout:

```text
5
7
7
10
```

Giải thích: bắt đầu `5`, post-increment lưu `5` vào `before` và cập nhật field thành `6`; pre-increment tăng tiếp thành `7` và lưu `7` vào `after`. Sau `+= 3`, giá trị field là `10`.

**Lưu ý đa luồng:** `counter.value++` và `counter.value += 1` **không phải thao tác nguyên tử** khi nhiều thread cùng cập nhật. `volatile` cũng không tự biến phép tăng thành nguyên tử. Nếu nhiều thread dùng chung trạng thái, cần đồng bộ phù hợp hoặc giải pháp như `AtomicInteger`; chỉ dùng dấu chấm và `++` không đảm bảo kết quả đúng trong trường hợp cạnh tranh dữ liệu.

## 13. Các lỗi biên dịch và runtime thường gặp

| Ví dụ / tình huống | Loại vấn đề | Cách hiểu hoặc khắc phục |
| --- | --- | --- |
| `account.balance` khi `account == null` | `NullPointerException` lúc chạy (instance field) | Tạo đối tượng, kiểm tra hoặc thiết kế tránh null |
| `account.balance = "100";` với `balance` là `int` | Lỗi kiểu lúc biên dịch | Gán giá trị cùng kiểu/tương thích, ví dụ `100` |
| `account.secret` với `secret` là `private` ở lớp khác | Lỗi quyền truy cập lúc biên dịch | Dùng API hợp lệ như getter/method |
| `account.unknown` khi kiểu không có field truy cập được tên `unknown` | Lỗi tra cứu thành viên | Kiểm tra tên field và kiểu khai báo của receiver |
| `account.id = 2;` với `id` đã là instance `final` được khởi tạo | Lỗi biên dịch | Không gán lại final field |
| `Account.balance` khi `balance` là instance field | Lỗi biên dịch: cần đối tượng | Dùng `account.balance` trong ngữ cảnh phù hợp |
| `account.created` khi `created` là static | Thường có thể biên dịch nhưng khó đọc | Ưu tiên `Account.created` |
| `obj.field++` trong mã nhiều thread | Nguy cơ lost update | Dùng đồng bộ hoặc cấu trúc dữ liệu đồng thời phù hợp |
| `child.field` trùng tên field của cha | Dễ nhầm field hiding | Xét kiểu tĩnh của receiver, tránh trùng tên |
| `record.name` từ bên ngoài record | Field của record thường `private` | Dùng accessor như `record.name()` |
| `object.getValue` khi chỉ có method `getValue()` | Lỗi cú pháp/tra cứu thành viên | Thêm `()`: `object.getValue()` |

Trong bảng, tên lớp/field chỉ là ví dụ giả định. Muốn chẩn đoán chính xác cần xem kiểu khai báo, modifier và ngữ cảnh truy cập của mã thực tế.

**Một nhầm lẫn khác:** dấu chấm không tự gọi setter. `account.balance = 10` ghi trực tiếp field nếu field truy cập được; nó **không** âm thầm thực thi `account.setBalance(10)`. Khi cần kiểm tra dữ liệu, logging, đồng bộ, hoặc thông báo thay đổi, hãy cung cấp API và yêu cầu bên ngoài gọi API đó.

## 14. Khi field thuộc record hoặc kiểu có API đọc chuyên biệt

Java 17 hỗ trợ `record`, thường dùng để chứa dữ liệu có cấu trúc. Với record, các component được cung cấp accessor method, và field tương ứng là `private final`:

```java
record Point(int x, int y) {
}

public class RecordFieldDemo {
    public static void main(String[] args) {
        Point point = new Point(2, 3);

        System.out.println(point.x());
        System.out.println(point.y());

        // System.out.println(point.x); // SAI ở ngoài record: x là private field
        // point.x = 5;                   // SAI: x là private final field
    }
}
```

Lưu thành **`RecordFieldDemo.java`**, rồi chạy:

```bash
javac -encoding UTF-8 RecordFieldDemo.java
java RecordFieldDemo
```

Stdout:

```text
2
3
```

`point.x()` là **lời gọi accessor method**, khác với `point.x` là truy cập field. Với `record`, muốn biểu diễn một giá trị khác, thường tạo một thể hiện mới, ví dụ `new Point(5, point.y())`, thay vì sửa component.

Mục tiêu của ví dụ là tránh suy diễn rằng mọi dữ liệu “có tên” trong Java đều mở cho việc ghi trực tiếp qua dấu chấm.

## 15. Thực hành: dự đoán kết quả trước khi chạy

Giả sử khai báo sau xuất hiện trong tệp thử nghiệm:

```java
class Cart {
    int items;
    static int nextId = 1;
    final int id;

    Cart(int items) {
        this.items = items;
        this.id = nextId++;
    }
}
```

Đoạn mã sử dụng trong `main`:

```java
Cart first = new Cart(2);
Cart shared = first;
Cart second = new Cart(5);

shared.items += 3;
first = second;

System.out.println(shared.items);
System.out.println(first.items);
System.out.println(first.id);
System.out.println(Cart.nextId);
```

Dự đoán:

- Có **hai thể hiện** `Cart`, do `new Cart(...)` chạy hai lần.
- Lúc đầu `shared` trỏ tới cùng đối tượng như `first`, có `items = 2`.
- `shared.items += 3` đổi `items` của đối tượng đầu thành `5`.
- `first = second` chỉ đổi tham chiếu `first` đến đối tượng thứ hai; `shared` vẫn trỏ đối tượng đầu.
- `first.id` đọc field `final` đã được constructor gán là `2` cho đối tượng thứ hai.
- `Cart.nextId` đã được tăng hai lần, từ `1` lên `3`.

**Kết quả stdout:**

```text
5
5
2
3
```

Hai giá trị `items` đều là `5` nhưng đến từ **hai đối tượng khác nhau**. Điều này nhắc rằng **giá trị field bằng nhau không chứng minh cùng tham chiếu**, và việc gán lại một biến không sao chép trạng thái sang đối tượng khác.

Để chạy độc lập, có thể đặt lớp `Cart` và một `public class CartDemo` chứa `main` với phần mã trên trong cùng tệp **`CartDemo.java`**, giữ duy nhất `CartDemo` là top-level `public`.

## 16. Checklist khi đọc một biểu thức `a.b`

Để phân tích đúng một truy cập field qua dấu chấm:

1. **`a` là gì?** Tên lớp, biến tham chiếu, `this`/`super`, hoặc một biểu thức trả về đối tượng? Nếu là tên lớp thường đang truy cập static member.
2. **`b` là gì?** Instance/static field hay phương thức? `a.b` là truy cập field, còn `a.b()` là lời gọi method nếu `b` là phương thức.
3. **Kiểu khai báo của receiver là gì?** Nó quyết định tập thành viên có thể chọn tại compile time; field hiding không có phân phối động như override method.
4. **Có được phép truy cập không?** Kiểm tra `public`/`protected`/package-private/`private` và quy tắc loại kiểu.
5. **Có đối tượng thật không?** Với instance field, nếu receiver là `null` thì phép đọc/ghi có thể ném `NullPointerException`.
6. **Field có thể gán lại không?** Field `final` đã khởi tạo không thể bị sửa bằng `=`, `++` hoặc `+=`.
7. **Thao tác sửa thứ gì?** `a = b` sửa giá trị biến `a`, còn `a.field = value` sửa field của đối tượng đang được `a` tham chiếu.
8. **Có cần kiểm tra/đồng bộ không?** Nếu trường biểu diễn trạng thái quan trọng, cân nhắc phương thức đóng gói; nếu nhiều thread cùng cập nhật, áp dụng cơ chế đồng bộ thích hợp.

### Ghi nhớ

- **Đọc field:** `object.field`; **ghi field:** `object.field = value;` khi mã có quyền và field cho phép gán.
- **Instance field** gắn với từng đối tượng; **static field** gắn với lớp, nên nên viết `ClassName.field`.
- Dấu chấm **không tự tạo đối tượng, không tự gọi getter/setter và không vượt qua access modifier**.
- Hai biến cùng tham chiếu một đối tượng sẽ nhìn thấy cùng những thay đổi ở instance field của đối tượng đó.
- `this.field` xác định rõ field của đối tượng hiện tại; `final` hạn chế ghi; receiver `null` gây lỗi khi truy cập instance field.
- Khi có kế thừa, **field được chọn theo kiểu biên dịch**, khác với instance method có thể được override; với dữ liệu cần kiểm soát điều kiện hợp lệ, ưu tiên đóng gói qua phương thức.
