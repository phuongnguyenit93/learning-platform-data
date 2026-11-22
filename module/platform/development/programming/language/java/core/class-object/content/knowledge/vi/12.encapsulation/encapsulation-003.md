# Getter và setter: mục đích, giới hạn và khi không cần trong Java

Trong lập trình hướng đối tượng với Java, **getter** là phương thức cung cấp khả năng *đọc* một phần trạng thái của đối tượng; **setter** là phương thức thường dùng để *thay đổi* một thuộc tính của đối tượng. Chúng là những công cụ phổ biến để hỗ trợ **đóng gói (*encapsulation*)**, nhưng **không phải cứ có field là bắt buộc tạo đủ `getX()` và `setX()`**.

Một class thực sự đóng gói tốt không chỉ che field bằng `private` rồi cung cấp các phương thức công khai đọc/ghi mọi giá trị. Class ấy phải **quyết định những gì bên ngoài được biết và được phép thay đổi**, bảo vệ các điều kiện trạng thái hợp lệ (*invariants*), kiểm soát các đối tượng mutable mà nó nắm giữ và công bố những thao tác phù hợp với ý nghĩa nghiệp vụ.

Ví dụ, một tài khoản ngân hàng có thể cho phép đọc số dư qua `getBalance()`, nhưng **không nên mở `setBalance(...)` để caller tùy ý gán một con số**. API `deposit(...)` và `withdraw(...)` diễn đạt chính xác những hành động hợp lệ hơn.

Bài học dành cho **Java 17+**; trình bày cách tạo getter/setter, mục đích, giới hạn, khi nào không cần, sự khác biệt giữa field access và method access, validation, defensive copy, immutable objects, records, quy ước JavaBeans, object mutable, kế thừa và concurrency. Các chương trình hoàn chỉnh đều ghi cách biên dịch và stdout.

## 1. Getter và setter là gì?

Một class có state:

~~~java
class Student {
    private String name;
    private int age;
}
~~~

Hai field được khai báo `private`; code ngoài class không thể trực tiếp viết `student.name` hoặc `student.age`.

Nếu muốn mở quyền đọc tên và tuổi, và cho phép thay đổi tên theo hợp đồng, có thể thêm:

~~~java
class Student {
    private String name;
    private int age;

    Student(String name, int age) {
        setName(name);
        setAge(age);
    }

    public String getName() {
        return name;
    }

    public int getAge() {
        return age;
    }

    public void setName(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.name = name;
    }

    private void setAge(int age) {
        if (age < 0 || age > 150) {
            throw new IllegalArgumentException("Tuổi không hợp lệ");
        }
        this.age = age;
    }
}
~~~

Đây là **đoạn khai báo class**, chưa có `main` để chạy độc lập. Phân tích:

- `getName()` trả tên của object hiện tại; caller có quyền **đọc** thông tin đã được công bố.
- `setName(...)` kiểm tra đầu vào rồi thay field; caller được **yêu cầu đổi tên theo quy tắc** chứ không tự đụng field.
- `getAge()` công khai quyền đọc tuổi.
- `setAge(...)` đặt là `private` chỉ để minh họa rằng **không nhất thiết công khai setter của mọi field**. Constructor có thể dùng phương thức nội bộ này để kiểm tra giá trị ban đầu.
- Bên ngoài class vẫn không thể viết `student.age = -20;` hay gọi `student.setAge(20)` vì không có public access phù hợp.

**Getter và setter là phương thức thông thường**, không phải cú pháp đặc biệt mà Java compiler tự tạo cho mọi field. Các tên `getName`, `setName` là quy ước phổ biến; Java không yêu cầu tất cả getter phải đặt tên như vậy.

## 2. Đóng gói không chỉ là field `private` và đủ bộ getter/setter

Đóng gói có thể hiểu qua hai mục tiêu:

1. **Giấu cách biểu diễn nội bộ:** code ngoài không cần biết field nào tồn tại, dữ liệu được tính hay lưu cache thế nào.
2. **Bảo vệ hành vi và trạng thái hợp lệ:** code ngoài chỉ được thực hiện các thao tác class thực sự hỗ trợ, để các bất biến được duy trì.

Một ví dụ kém:

~~~java
class BadBankAccount {
    private long balance;

    public long getBalance() {
        return balance;
    }

    public void setBalance(long balance) {
        this.balance = balance;
    }
}
~~~

Class này dùng field `private` nhưng công khai `setBalance` vô điều kiện. Caller có thể viết:

~~~java
account.setBalance(-1000);
account.setBalance(1_000_000_000L);
~~~

Nếu nghiệp vụ không cho phép số dư âm hoặc việc thay số dư phải tương ứng một giao dịch, API này đã cho phép trạng thái/hành động không hợp lệ. Getter/setter **không tự động bảo đảm đóng gói**.

Thiết kế phù hợp hơn:

~~~java
class BankAccount {
    private long balance;

    BankAccount(long openingBalance) {
        if (openingBalance < 0) {
            throw new IllegalArgumentException("Số dư âm");
        }
        balance = openingBalance;
    }

    public long getBalance() {
        return balance;
    }

    public void deposit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }
        balance = Math.addExact(balance, amount);
    }

    public void withdraw(long amount) {
        if (amount <= 0 || amount > balance) {
            throw new IllegalArgumentException("Rút tiền không hợp lệ");
        }
        balance -= amount;
    }
}
~~~

Class công bố hai **hành động nghiệp vụ**, thay vì một setter mở toàn quyền gán số dư. Lời gọi `deposit(100)` thể hiện ý định gửi tiền; `withdraw(30)` thể hiện ý định rút tiền; các method có thể thực thi validation, audit, quyền truy cập hoặc logic khác về sau.

**Nguyên tắc:** không đánh đồng “che field” với “kiểm soát thay đổi state”. API nên giúp người dùng **khó thực hiện sai hành vi** và **dễ thực hiện hành vi đúng**.

## 3. Getter cung cấp quyền đọc, nhưng không nhất thiết trả nguyên field

Một getter có thể:

- Trả một primitive hoặc immutable value.
- Trả giá trị được tính từ các field.
- Trả bản sao dữ liệu mutable.
- Trả một view hoặc cấu trúc read-only theo hợp đồng.
- Thực hiện kiểm tra quyền hoặc chuyển đổi định dạng nếu API thật sự cần.
- Không công bố dữ liệu nhạy cảm mà class phải giữ kín.

Ví dụ getter tính giá trị:

~~~java
class Rectangle {
    private final int width;
    private final int height;

    Rectangle(int width, int height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("Cạnh phải dương");
        }
        this.width = width;
        this.height = height;
    }

    public long getArea() {
        return (long) width * height;
    }
}
~~~

`getArea()` **không có field `area`** tương ứng. Nó tính giá trị từ hai field; ép kiểu `(long)` trước phép nhân giúp tránh tràn số nguyên `int` ở bước nhân trung gian (với hai `int` dương, kết quả lớn nhất vẫn nằm trong miền `long`).

Nếu sau này class đổi cách lưu kích thước hoặc cache kết quả mà vẫn bảo đảm hợp đồng `getArea()`, caller không cần sửa logic chỉ vì field nội bộ thay đổi.

### 3.1. Getter của primitive và immutable object thường đơn giản

~~~java
class Product {
    private final String sku;
    private final int quantity;

    Product(String sku, int quantity) {
        this.sku = java.util.Objects.requireNonNull(sku);
        this.quantity = quantity;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }
}
~~~

Trả `int` là trả giá trị primitive; caller không thể sửa field chỉ bằng cách gán lại biến nhận kết quả. Trả `String` cũng thường an toàn về **nội dung String**, vì String là immutable. Nhưng không phải mọi reference type đều immutable: getter trả trực tiếp `List`, mảng, `Date` hoặc một mutable object có thể làm lộ state nội bộ.

### 3.2. Getter không nhất thiết cần tồn tại

Nếu class chỉ cần thực hiện một hành động mà caller không có nhu cầu hợp lệ đọc một field riêng, **không có lý do bắt buộc phải tạo getter**. Ví dụ, một class giữ credential bí mật để gửi request có thể dùng credential nội bộ mà không công bố `getPassword()`.

Getter còn là một phần của **hợp đồng API**: công khai quá nhiều dữ liệu sẽ khiến caller phụ thuộc vào chi tiết triển khai và làm việc thay đổi cấu trúc nội bộ về sau khó hơn.

## 4. Setter cung cấp quyền thay đổi có điều kiện

Setter tốt thường có trách nhiệm:

1. **Xác thực đầu vào** theo nghiệp vụ (không null, không blank, trong miền cho phép).
2. **Duy trì quan hệ giữa các field** của object.
3. **Không khiến object rơi vào trạng thái sai** nếu thao tác thất bại.
4. **Thông báo lỗi rõ ràng** khi caller yêu cầu không hợp lệ.
5. **Xác định tác dụng phụ**: có phát notification, invalidate cache, audit, lưu dữ liệu hay không.

Ví dụ:

~~~java
class Course {
    private String title;

    Course(String title) {
        setTitle(title);
    }

    public void setTitle(String title) {
        if (title == null) {
            throw new IllegalArgumentException("title null");
        }

        String normalized = title.trim();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("title rỗng");
        }

        this.title = normalized;
    }

    public String getTitle() {
        return title;
    }
}
~~~

`setTitle` kiểm tra, chuẩn hóa rồi mới gán field. Nếu đối số sai, method ném `IllegalArgumentException` trước khi đổi `title`. Caller không thể trực tiếp gán title rỗng qua field vì nó private.

**Điểm cần cân nhắc:** việc âm thầm chuẩn hóa `trim()` là một phần hợp đồng. Nếu khoảng trắng ở đầu/cuối có ý nghĩa nghiệp vụ, không được xóa chỉ vì người viết setter cho rằng “nên sạch”.

### 4.1. Setter không bắt buộc tên `setX()` nếu nghiệp vụ là hành động

`setQuantity(100)` truyền tải thông điệp “gán số lượng hiện tại thành 100”. Nếu thao tác thực tế là nhập thêm hàng, `increaseStock(100)` diễn đạt chính xác hơn. Nếu thao tác là đóng tài khoản, `close()` tốt hơn `setStatus("CLOSED")` khi chuyển trạng thái cần các điều kiện.

Các tên method là một phần ngôn ngữ thiết kế API. Không nên gọi mọi command là setter nếu hành động chứa **nghiệp vụ**, **quy tắc chuyển trạng thái** hoặc **tác động nhiều field**.

## 5. Ví dụ hoàn chỉnh: không dùng `setBalance` cho tài khoản

Tạo tệp **`EncapsulationDemo.java`**:

~~~java
public class EncapsulationDemo {
    static final class BankAccount {
        private final String id;
        private long balance;

        BankAccount(String id, long openingBalance) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("ID không hợp lệ");
            }
            if (openingBalance < 0) {
                throw new IllegalArgumentException("Số dư âm");
            }
            this.id = id;
            this.balance = openingBalance;
        }

        public String getId() {
            return id;
        }

        public long getBalance() {
            return balance;
        }

        public void deposit(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("Tiền gửi phải dương");
            }
            this.balance = Math.addExact(this.balance, amount);
        }

        public void withdraw(long amount) {
            if (amount <= 0 || amount > balance) {
                throw new IllegalArgumentException("Số tiền rút sai");
            }
            this.balance -= amount;
        }
    }

    public static void main(String[] args) {
        BankAccount account = new BankAccount("TK-01", 100);

        System.out.println("Account = " + account.getId());
        System.out.println("Initial = " + account.getBalance());

        account.deposit(50);
        account.withdraw(20);
        System.out.println("After transactions = " + account.getBalance());

        try {
            account.withdraw(1_000);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        System.out.println("Final = " + account.getBalance());
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 EncapsulationDemo.java
java EncapsulationDemo
~~~

**Stdout chính xác:**

~~~text
Account = TK-01
Initial = 100
After transactions = 130
Rejected = Số tiền rút sai
Final = 130
~~~

**Phân tích:**

1. Constructor bắt buộc id không blank và số dư đầu không âm; object được tạo thành công với state hợp lệ.
2. `getId()` và `getBalance()` cung cấp những dữ liệu công khai cần thiết, không trao quyền gán vào field.
3. `deposit(50)` cộng 50 có kiểm tra số dương và tràn `long` bằng `Math.addExact`; số dư tăng từ 100 lên 150.
4. `withdraw(20)` trừ 20 sau khi kiểm tra giới hạn, số dư còn 130.
5. `withdraw(1_000)` vượt số dư nên exception xảy ra trước khi sửa field. Catch in ra message cố định; trạng thái cuối vẫn 130.
6. **Không có `setBalance(...)`** vì caller không được tùy ý thay đổi số dư. Không có `setId(...)` vì id được xác định từ lúc tạo và field `final`.

Ví dụ này minh họa API đối tượng cơ bản. Trong hệ thống giao dịch thật, còn cần kiểm soát quyền truy cập, đối soát, lưu bền vững, concurrency, idempotency và điều kiện nghiệp vụ khác; `private` field không tự thay thế chúng.

## 6. Giới hạn lớn của getter: rò rỉ tham chiếu đến mutable state

Một trong những lỗi đóng gói nguy hiểm nhất là getter trả **trực tiếp một mutable object** đang được giữ nội bộ:

~~~java
import java.util.ArrayList;
import java.util.List;

class UnsafeTeam {
    private final List<String> members = new ArrayList<>();

    public List<String> getMembers() {
        return members; // Trả chính mutable list nội bộ
    }
}
~~~

Caller có thể thực hiện:

~~~java
UnsafeTeam team = new UnsafeTeam();
team.getMembers().add("Lan");
team.getMembers().clear();
~~~

Field `members` tuy `private final` nhưng object List do field tham chiếu tới **vẫn có thể bị sửa**. Setter không cần tồn tại mà caller đã giành được quyền thay đổi state!

**`final` bảo vệ phép gán lại tham chiếu field, không làm object được tham chiếu bất biến.** Một public getter trả mutable reference có thể phá mục đích đóng gói dù field được khai báo private.

### 6.1. Getter trả snapshot

Một cách xử lý khi danh sách gồm immutable elements như `String`:

~~~java
import java.util.ArrayList;
import java.util.List;

class Team {
    private final List<String> members = new ArrayList<>();

    void addMember(String member) {
        if (member == null || member.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        members.add(member);
    }

    public List<String> getMembers() {
        return List.copyOf(members);
    }
}
~~~

`List.copyOf` (Java 10+) trả một List không thể sửa qua các thao tác thay đổi và không chứa null. Vì source là mutable `ArrayList`, kết quả là snapshot cấu trúc của danh sách tại thời điểm copy; caller không thể thêm/xóa trên kết quả này để sửa list gốc.

Các lưu ý quan trọng:

- `List.copyOf` **không deep-copy object phần tử**. Với `List<MutableEmployee>`, caller có thể sửa các object MutableEmployee dùng chung nếu API để lộ chúng.
- `Collections.unmodifiableList(original)` tạo **view không sửa được qua view**, nhưng nếu `original` thay đổi từ nơi khác, view có thể phản ánh thay đổi đó; không đồng nghĩa snapshot.
- `new ArrayList<>(members)` tạo snapshot mutable độc lập về **cấu trúc**, nhưng caller có thể sửa bản copy của riêng mình; điều đó có thể hoàn toàn phù hợp nếu mục đích là trả dữ liệu để caller xử lý.
- Nếu state đổi đồng thời giữa thread, việc tạo snapshot nhất quán cũng cần hợp đồng đồng bộ hoặc cấu trúc concurrency phù hợp; `List.copyOf` không tự làm toàn bộ class thread-safe.

### 6.2. Với mảng, getter cũng nên cân nhắc copy

~~~java
class Scores {
    private final int[] marks;

    Scores(int[] marks) {
        this.marks = marks.clone();
    }

    public int[] getMarks() {
        return marks.clone();
    }
}
~~~

Đây là đoạn khai báo. Với `int[]`, clone sao chép mảng và các giá trị primitive, giúp tránh caller sửa mảng nội bộ. Constructor cũng clone **đầu vào**, vì nếu chỉ clone ở getter nhưng giữ mảng gốc caller đưa vào, caller vẫn có thể sửa nội bộ qua tham chiếu ban đầu.

Nếu input có thể null, cần quy định từ chối hoặc xử lý null; đoạn ví dụ dùng `marks.clone()` nên sẽ ném NPE nếu truyền null. Khi viết API production, bổ sung validation và thông báo phù hợp.

### 6.3. Mutable elements đòi hỏi bảo vệ sâu hơn

~~~java
class Item {
    String name;

    Item(String name) {
        this.name = name;
    }
}

class Catalog {
    private final java.util.List<Item> items;

    Catalog(java.util.List<Item> source) {
        this.items = java.util.List.copyOf(source);
    }

    java.util.List<Item> getItems() {
        return items;
    }
}
~~~

List trả về **không sửa được về cấu trúc**, nhưng caller đang giữ một `Item` từ `source` vẫn có thể thực hiện `item.name = ...` nếu quyền truy cập cho phép, và trạng thái Item đó thay đổi trong catalog. Đây là **shallow copy**. Với invariant cần ổn định cả nội dung phần tử, hãy dùng immutable value objects, copy từng phần tử hoặc thiết kế quyền sở hữu rõ ràng.

## 7. Ví dụ hoàn chỉnh: getter an toàn và setter có validation

Tạo tệp **`SafeAccessorsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SafeAccessorsDemo {
    static final class Team {
        private String name;
        private final List<String> members;

        Team(String name, List<String> source) {
            this.members = List.copyOf(source);
            for (String member : this.members) {
                if (member.isBlank()) {
                    throw new IllegalArgumentException("Tên thành viên rỗng");
                }
            }
            setName(name);
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Tên nhóm không hợp lệ");
            }
            this.name = name.trim();
        }

        public List<String> getMembers() {
            return members;
        }

        public int getSize() {
            return members.size();
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(
                List.of("Lan", "Mai"));
        Team team = new Team("Java", source);

        source.clear();
        source.add("Changed");

        System.out.println("Team = " + team.getName());
        System.out.println("Members = " + team.getMembers());
        System.out.println("Size = " + team.getSize());

        team.setName("  Backend  ");
        System.out.println("Renamed = " + team.getName());

        try {
            team.setName("  ");
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        try {
            team.getMembers().add("An");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Cannot edit members");
        }

        System.out.println("Final members = " + team.getMembers());
        System.out.println("Final name = " + team.getName());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SafeAccessorsDemo.java
java SafeAccessorsDemo
~~~

**Stdout chính xác:**

~~~text
Team = Java
Members = [Lan, Mai]
Size = 2
Renamed = Backend
Rejected = Tên nhóm không hợp lệ
Cannot edit members
Final members = [Lan, Mai]
Final name = Backend
~~~

**Giải thích:**

1. Constructor sử dụng `List.copyOf(source)` để chụp cấu trúc danh sách; khi caller thay đổi `source`, state của team **không** đổi.
2. `getMembers()` trả danh sách không sửa được đã lưu, không cho caller thay đổi cấu trúc qua `add` hay `remove`.
3. `getSize()` tính số lượng từ danh sách, không cần field `size` riêng.
4. `setName("  Backend  ")` chuẩn hóa thành `"Backend"`; đây là hành vi được quy định bởi method.
5. `setName("  ")` thất bại **trước phép gán**, nên `name` vẫn là `Backend`.
6. `getMembers().add("An")` ném `UnsupportedOperationException`, ví dụ bắt lỗi để in thông báo ổn định, không phụ thuộc stack trace.

**Giới hạn minh họa:** các phần tử List là `String` immutable nên copy cấu trúc phù hợp. Nếu là object phần tử mutable, cần kiểm tra deep immutability. `List.copyOf` cũng ném NPE nếu source null hoặc có phần tử null; phải bổ sung hợp đồng/validation cụ thể nếu API yêu cầu message khác.

## 8. Một setter riêng lẻ có thể phá invariant liên quan nhiều field

Một class thường có các điều kiện liên quan **nhiều thuộc tính**, ví dụ khoảng ngày hợp lệ yêu cầu `start <= end`. Nếu công khai hai setter độc lập, caller có thể buộc object đi qua một trạng thái trung gian không hợp lệ.

Ví dụ thiết kế dễ gặp vấn đề:

~~~java
import java.time.LocalDate;

class UnsafeRange {
    private LocalDate start;
    private LocalDate end;

    UnsafeRange(LocalDate start, LocalDate end) {
        this.start = start;
        this.end = end;
    }

    public void setStart(LocalDate start) {
        this.start = start;
    }

    public void setEnd(LocalDate end) {
        this.end = end;
    }
}
~~~

Class này không validate, nên có thể có `start > end`. Ngay cả khi thêm kiểm tra ở từng setter, việc thay toàn bộ khoảng vẫn có thể cần thay **cả hai giá trị cùng lúc**. Ví dụ khoảng hiện tại từ ngày 10 đến 20: muốn chuyển thành từ 30 đến 40, nếu setter `setStart(30)` buộc start <= end hiện tại, bước đầu sẽ bị từ chối dù cặp giá trị mới hoàn toàn hợp lệ.

### 8.1. Command thay đổi cả hai thuộc tính cùng một lần

~~~java
import java.time.LocalDate;
import java.util.Objects;

class DateRange {
    private LocalDate start;
    private LocalDate end;

    DateRange(LocalDate start, LocalDate end) {
        reschedule(start, end);
    }

    public void reschedule(LocalDate nextStart, LocalDate nextEnd) {
        Objects.requireNonNull(nextStart, "nextStart");
        Objects.requireNonNull(nextEnd, "nextEnd");

        if (nextEnd.isBefore(nextStart)) {
            throw new IllegalArgumentException("Khoảng ngày không hợp lệ");
        }

        this.start = nextStart;
        this.end = nextEnd;
    }

    public LocalDate getStart() {
        return start;
    }

    public LocalDate getEnd() {
        return end;
    }
}
~~~

`reschedule` validate **cả cặp mới**, rồi gán state. Trong truy cập đơn luồng, caller không gặp lỗi do thứ tự gọi hai setter. `LocalDate` immutable nên getter trả tham chiếu tới chúng là phù hợp.

**Lưu ý concurrency:** hai phép gán field trong method `reschedule` **không phải một transaction nguyên tử giữa thread**. Nếu nhiều thread có thể đọc/ghi đồng thời, cần synchronization, lock hoặc lưu nguyên khoảng trong một immutable object rồi thay cả tham chiếu theo một protocol an toàn.

### 8.2. Kiểu bất biến còn đơn giản hơn khi không cần sửa sau tạo

~~~java
import java.time.LocalDate;
import java.util.Objects;

record DateRangeValue(LocalDate start, LocalDate end) {
    DateRangeValue {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");
        if (end.isBefore(start)) {
            throw new IllegalArgumentException("Khoảng ngày không hợp lệ");
        }
    }
}
~~~

Record `DateRangeValue` có các thành phần final theo quy tắc record, cung cấp accessor `start()`, `end()` và không có setter. Khi cần một khoảng ngày mới, tạo một instance mới hợp lệ thay vì sửa dở dang khoảng cũ.

Với class lớn hoặc object có nhiều ràng buộc liên trường, một **constructor/factory/builder** tạo trạng thái hợp lệ thường phù hợp hơn một chuỗi setter tùy ý.

## 9. Khi nào **không nên** tạo setter?

Không có quy tắc “class nào cũng có cả getter và setter”. Những tình huống điển hình không cần setter:

### 9.1. Giá trị chỉ có thể xác lập khi tạo object

~~~java
class Employee {
    private final String employeeId;

    Employee(String employeeId) {
        if (employeeId == null || employeeId.isBlank()) {
            throw new IllegalArgumentException("ID không hợp lệ");
        }
        this.employeeId = employeeId;
    }

    public String getEmployeeId() {
        return employeeId;
    }
}
~~~

Field `final` phù hợp khi identity không được đổi sau khi tạo. `setEmployeeId(...)` sẽ mâu thuẫn hợp đồng đó, nên không có setter.

### 9.2. Field được tính từ state khác

~~~java
class Basket {
    private final java.util.List<String> items =
            new java.util.ArrayList<>();

    public int getItemCount() {
        return items.size();
    }
}
~~~

Số lượng được suy ra từ list. Không cần `setItemCount(int)` vì caller không thể tùy ý yêu cầu “count = 100” mà không thay số item thực tế. Nếu cần thêm/xóa item, dùng `addItem(...)`, `removeItem(...)` có kiểm soát.

### 9.3. Thay đổi đòi hỏi hành động nghiệp vụ

Một đơn hàng đi qua các trạng thái `NEW → PAID → SHIPPED` theo điều kiện. API `setStatus(Status)` có thể cho caller nhảy thẳng từ NEW sang SHIPPED bỏ qua kiểm tra. Các method `pay()`, `ship()` phản ánh **quy tắc chuyển trạng thái** rõ hơn.

### 9.4. Đối tượng immutable hoặc value object

Một `Money` gồm currency và amount có thể bất biến. Muốn tăng amount thì dùng `plus(...)` trả object mới; không nhất thiết có setter trên Money. Thiết kế immutable giúp dễ suy luận, cache, chia sẻ dữ liệu và tránh nhiều kiểu lỗi do aliasing.

### 9.5. Setter làm lộ cơ chế nội bộ không có ý nghĩa bên ngoài

Một class có field `cachedValue` chỉ để tối ưu có thể không nên mở `setCachedValue(...)`. Caller chỉ cần method tính toán, còn cache là implementation detail.

**Câu hỏi quyết định:** *Caller có một hành vi hợp lệ, có ý nghĩa, yêu cầu gán lại chính thuộc tính đó không?* Nếu không, đừng tự động sinh setter.

## 10. Khi nào **không cần** getter?

Getter cũng không phải mặc định bắt buộc:

- **Dữ liệu nhạy cảm:** credential, khóa bí mật, token nội bộ không nên được trả tùy ý nếu không có nhu cầu rõ.
- **Dữ liệu chỉ hỗ trợ triển khai:** cache, cờ nội bộ, thuật toán, lock, kết quả trung gian không phải contract.
- **Dữ liệu nên biểu diễn thành hành vi:** thay vì `getInternalList()` rồi caller tính, có thể cung cấp `containsItem(x)` hoặc `totalPrice()`.
- **Thông tin chỉ cần công bố dưới dạng hạn chế:** trả `getMaskedCardNumber()` thay vì raw card number nếu phù hợp.
- **Không cần expose state để object làm công việc của nó:** một service nội bộ có thể cung cấp `execute()` mà không công khai mọi dependency qua getter.

### 10.1. Getter cho mọi field dễ tạo “anemic domain model”

Một class chỉ là tập field với getter/setter, trong khi mọi quy tắc nghiệp vụ nằm trong service khác, dễ khiến **logic về cùng state bị phân tán**:

~~~java
class Order {
    private int quantity;
    private long unitPrice;

    public int getQuantity() { return quantity; }
    public void setQuantity(int value) { quantity = value; }

    public long getUnitPrice() { return unitPrice; }
    public void setUnitPrice(long value) { unitPrice = value; }
}
~~~

Trong mô hình domain phức tạp, kiểu thiết kế này có thể cho phép quantity âm, price âm hoặc phép tính sai tràn số. Cân nhắc các method `changeQuantity(...)` có validation, `total()` có tính toán chuẩn, và constructor thiết lập invariant.

Tuy nhiên, **không phải mọi class dữ liệu có getter/setter đều là sai**. Một DTO đơn giản chủ yếu chuyển dữ liệu giữa các tầng có thể hợp lý khi nó không sở hữu hành vi nghiệp vụ. Điều quan trọng là **vai trò của class**, không phải cấm một mẫu mã máy móc.

## 11. Record trong Java 17: có accessor nhưng không có JavaBeans setter

Record giúp khai báo một kiểu dữ liệu bất biến về các **component fields** một cách súc tích:

~~~java
public record UserView(String name, int age) {
    public UserView {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên rỗng");
        }
        if (age < 0) {
            throw new IllegalArgumentException("Tuổi âm");
        }
    }
}
~~~

Đây là **record độc lập**; để biên dịch, lưu trong `UserView.java`.

Compiler tạo các component accessor theo tên component:

~~~java
UserView user = new UserView("Lan", 20);

System.out.println(user.name()); // Lan
System.out.println(user.age());  // 20
~~~

Record **không tự sinh `getName()` hoặc `setName(...)`** như JavaBeans. `name()` và `age()` là accessor chuẩn của record; record components tương ứng là private final fields và object không có setter tự sinh.

Nếu muốn thay tuổi, có thể tạo record mới:

~~~java
UserView next = new UserView(user.name(), 21);
~~~

Lưu ý: record cung cấp **shallow immutability**. Nếu một component có kiểu `List<String>` mutable, record không tự copy sâu List. Compact constructor có thể xử lý bằng `List.copyOf` hoặc validation/immutable modeling phù hợp. Trả component List mutable qua accessor vẫn có thể làm lộ state phần tử hoặc cấu trúc nếu chưa phòng vệ.

### 11.1. Ví dụ với record chứa collection

~~~java
import java.util.List;

record CourseView(String code, List<String> tags) {
    CourseView {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("code rỗng");
        }
        tags = List.copyOf(tags);
    }
}
~~~

Đây là đoạn khai báo. Trong compact constructor, việc gán lại parameter `tags` thành snapshot được chấp nhận; sau phần thân, record fields được gán từ các component parameters theo quy tắc Java. Do `String` immutable và List copy không sửa được, caller không thể dùng list nguồn để thay đổi cấu trúc danh sách tags của record.

## 12. JavaBeans conventions: getter/setter theo tên thuộc tính

Một số công cụ Java dùng quy ước **JavaBeans** để phát hiện “properties”. Những quy ước thường gặp:

| Mục đích | Tên method thường dùng |
| --- | --- |
| Đọc thuộc tính `name` | `getName()` |
| Ghi thuộc tính `name` | `setName(String value)` |
| Đọc thuộc tính boolean `active` | `isActive()` hoặc `getActive()` tùy convention/tool |
| Chỉ đọc | Getter mà không có public setter |
| Chỉ ghi trong mô hình tool nhất định | Setter mà không có getter; không nên mặc định đây là API tốt |
| Record component `name` | `name()` (khác tên JavaBeans cổ điển) |

Ví dụ:

~~~java
class UserBean {
    private String name;
    private boolean active;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public boolean isActive() {
        return active;
    }

    public void setActive(boolean active) {
        this.active = active;
    }
}
~~~

Đây là lớp minh họa. Bean conventions hỗ trợ các công cụ **introspection**, binding, serialization/mapping, giao diện nhập liệu hoặc thư viện dựa vào tên property.

**Không đánh đồng JavaBeans với luật bắt buộc cho mọi class Java:**

- Java cho phép method tên `name()`, `rename(...)` hoặc `isAvailable()` nếu nó hợp lệ về cú pháp/kiểu.
- JavaBeans thường trông đợi các chữ ký cụ thể như `getX()` không tham số và `setX(value)` một tham số, kiểu trả về `void` ở setter thông thường; fluent setter `setX(...)` trả `this` có thể không được một số thư viện nhận diện theo convention.
- Boolean field kiểu `Boolean` (wrapper) có `null` có thể cần cách đặt getter khác với primitive `boolean` để tránh unboxing bất ngờ; kiểm tra yêu cầu framework.
- Record accessors khác JavaBeans getters cổ điển; những framework hiện đại có thể hỗ trợ record theo các đường khác nhau, nhưng **không tự suy luận mọi thư viện sẽ hiểu `name()` như `getName()`**.
- Có framework khai thác field access, constructor binding hoặc annotations thay vì nhất thiết cần public setters.

Nếu dự án dùng một framework, hãy tuân thủ **hợp đồng phiên bản/cấu hình cụ thể của framework** chứ không để quy ước công cụ áp đặt setter không cần thiết lên toàn bộ domain model.

## 13. DTO, entity và domain object không có cùng nhu cầu accessor

### 13.1. DTO (Data Transfer Object)

DTO chuyển dữ liệu giữa các tầng hoặc qua API thường có fields/properties rõ, các getter và setter có thể hữu ích cho thư viện serialization/deserialization hoặc form binding. Ví dụ:

~~~java
class UserForm {
    private String name;
    private Integer age;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

Đây là class dữ liệu minh họa, không chứa logic nghiệp vụ. `Integer` cho phép biểu diễn “chưa nhập tuổi” bằng null; cần validation khi chuyển form sang một domain object có invariant mạnh.

### 13.2. Entity/domain model

Một domain entity có identity và vòng đời, thường cần **hành vi nghiệp vụ có kiểm soát** hơn setter tự do. Ví dụ, `Order.pay()` thay trạng thái theo điều kiện tốt hơn `setPaid(true)` nếu có kiểm tra thanh toán.

### 13.3. Persistence/serialization frameworks

Một số thư viện/ORM yêu cầu constructor, field, method hoặc annotation theo quy ước nhất định. Ví dụ, JPA entities thường có constructor không tham số public/protected theo đặc tả, nhưng **không có nghĩa mọi entity field bắt buộc phải có public setter**; các cơ chế truy cập field/property và proxy có điều kiện riêng.

Nên tách:

1. **Hợp đồng nghiệp vụ** của domain object.
2. **Hợp đồng ánh xạ dữ liệu** mà persistence/serialization framework cần.
3. **Hình thức xuất dữ liệu** để client bên ngoài dùng.

Khi các yêu cầu xung đột, có thể dùng DTO, mapper, factory hoặc constructor binding phù hợp, thay vì mở quyền sửa state không kiểm soát trên domain object chỉ để thỏa một công cụ.

## 14. Getter và setter không quyết định khả năng kế thừa hay overriding một mình

Một getter/setter bình thường là instance method và có thể được override nếu không `private`, `static` hoặc `final` và thỏa quy tắc kế thừa.

~~~java
class BaseProfile {
    protected String name = "Base";

    public String getName() {
        return name;
    }
}

class NamedProfile extends BaseProfile {
    @Override
    public String getName() {
        return "Named:" + super.getName();
    }
}
~~~

Với `new NamedProfile().getName()`, kết quả là `Named:Base`. Một getter gọi trên biến có static type `BaseProfile` nhưng runtime object `NamedProfile` có thể dispatch tới override.

Điều này quan trọng trong constructor:

~~~java
class Base {
    Base() {
        // avoid calling overridable getter/setter here
    }
}
~~~

**Không nên gọi setter/getter có thể override từ constructor khi logic phụ thuộc vào state của subclass**. Constructor superclass có thể dispatch sang override của subclass trước khi fields subclass hoàn tất khởi tạo, dẫn đến null/default values hoặc tác dụng phụ không mong muốn.

Trong constructor, ưu tiên trực tiếp validate tham số và gán state hoặc gọi helper `private`/`static`/`final` thích hợp. Không có yêu cầu kỹ thuật rằng mọi phép gán field từ constructor phải thông qua public setter.

## 15. Getter và setter không tự tạo thread safety

Giả sử:

~~~java
class UnsafeCounter {
    private int value;

    public int getValue() {
        return value;
    }

    public void setValue(int value) {
        this.value = value;
    }
}
~~~

`private`, getter và setter **không tự bảo đảm tính đúng khi nhiều thread dùng chung object**. Với hai thread, có thể có data race và các vấn đề visibility. Một thao tác `setValue(getValue() + 1)` gồm ít nhất hai method call, không phải phép tăng nguyên tử.

Ví dụ:

~~~java
class AtomicCounter {
    private final java.util.concurrent.atomic.AtomicInteger value =
            new java.util.concurrent.atomic.AtomicInteger();

    public int getValue() {
        return value.get();
    }

    public int increment() {
        return value.incrementAndGet();
    }
}
~~~

Method `increment()` cung cấp hành vi **tăng nguyên tử** cho counter, tốt hơn một setter kết hợp getter đọc/sửa/ghi không được bảo vệ. Không cần `setValue(...)` nếu caller chỉ được tăng đếm.

Nếu có nhiều field cần duy trì invariant cùng nhau, một atomic field riêng cũng **không tự biến toàn bộ object thành thread-safe**. Hãy xác định giới hạn đồng bộ theo thao tác nghiệp vụ, sử dụng lock hoặc immutable snapshot đúng cách.

### 15.1. `volatile` trên field không thay thế validation/invariant

Một field `volatile int value` hỗ trợ những quy tắc visibility nhất định, nhưng thao tác `value++` vẫn không phải read-modify-write atomic. Đặt `volatile` không biến getter/setter thành transaction, và cũng không cho phép bỏ các điều kiện nghiệp vụ.

## 16. Chọn immutable object thay vì setter tự do

Khi dữ liệu chủ yếu là **giá trị** chứ không phải entity mutable, immutable design thường hợp lý:

~~~java
final class Point {
    private final int x;
    private final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    public int getX() { return x; }

    public int getY() { return y; }

    public Point movedBy(int dx, int dy) {
        return new Point(
                Math.addExact(x, dx),
                Math.addExact(y, dy));
    }
}
~~~

Đây là đoạn khai báo. `Point` không có setter. `movedBy(...)` tạo object mới với tọa độ mới, giữ object cũ không đổi. Thiết kế như vậy thường dễ chia sẻ hơn vì caller không thể làm thay đổi trạng thái của Point có sẵn qua một setter.

**Không đồng nghĩa mọi object đều nên immutable.** Một entity mô tả giỏ hàng đang thay đổi có thể cần commands cập nhật. Nhưng ngay cả với mutable entity, thay đổi nên thông qua **hành vi có ý nghĩa**, không nhất thiết setter từng field.

### 16.1. Với record, tạo phiên bản mới

~~~java
record Coordinate(int x, int y) {
    Coordinate movedBy(int dx, int dy) {
        return new Coordinate(
                Math.addExact(x, dx),
                Math.addExact(y, dy));
    }
}
~~~

`Coordinate` là record của Java 17; có accessors `x()` và `y()`, không có setter. `movedBy` trả record mới thay cho thay trạng thái record hiện tại.

## 17. Một ví dụ hoàn chỉnh về thay cả trạng thái liên quan

Tạo tệp **`RangeUpdateDemo.java`**:

~~~java
import java.time.LocalDate;

public class RangeUpdateDemo {
    static final class DateRange {
        private LocalDate start;
        private LocalDate end;

        DateRange(LocalDate start, LocalDate end) {
            reschedule(start, end);
        }

        public LocalDate getStart() {
            return start;
        }

        public LocalDate getEnd() {
            return end;
        }

        public void reschedule(LocalDate nextStart, LocalDate nextEnd) {
            if (nextStart == null || nextEnd == null) {
                throw new IllegalArgumentException("Ngày null");
            }
            if (nextEnd.isBefore(nextStart)) {
                throw new IllegalArgumentException(
                        "Khoảng ngày không hợp lệ");
            }
            this.start = nextStart;
            this.end = nextEnd;
        }

        public String summary() {
            return start + " -> " + end;
        }
    }

    public static void main(String[] args) {
        DateRange range = new DateRange(
                LocalDate.of(2026, 1, 10),
                LocalDate.of(2026, 1, 20));

        System.out.println("Before = " + range.summary());

        range.reschedule(
                LocalDate.of(2026, 1, 30),
                LocalDate.of(2026, 2, 5));

        System.out.println("After = " + range.summary());

        try {
            range.reschedule(
                    LocalDate.of(2026, 3, 10),
                    LocalDate.of(2026, 3, 1));
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        System.out.println("Final = " + range.summary());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 RangeUpdateDemo.java
java RangeUpdateDemo
~~~

**Stdout chính xác:**

~~~text
Before = 2026-01-10 -> 2026-01-20
After = 2026-01-30 -> 2026-02-05
Rejected = Khoảng ngày không hợp lệ
Final = 2026-01-30 -> 2026-02-05
~~~

Ở ví dụ này, class có **getter để đọc hai giá trị**, nhưng không có `setStart` và `setEnd` độc lập. Method `reschedule` là một command có ý nghĩa, nhận cả hai giá trị mới rồi kiểm tra **mối quan hệ giữa chúng** trước khi gán. Khi validation thất bại, cả start và end vẫn giữ dữ liệu cũ.

Một lần nữa, nếu nhiều thread đọc/ghi object đồng thời, việc gán hai reference fields cần một chiến lược đồng bộ; ví dụ này chỉ minh họa invariant trong ngữ cảnh đơn luồng.

## 18. Lựa chọn API qua các tình huống thực tế

| Trạng thái/hành vi | Nên cân nhắc | Vì sao |
| --- | --- | --- |
| ID xác định khi tạo | Getter, không setter | ID bất biến của instance |
| Tên hiển thị có thể đổi | Getter + setter có validation hoặc `rename(...)` | Thay đổi hợp lệ và có ý nghĩa |
| Số dư tài khoản | Getter + `deposit/withdraw` | Không cho gán tùy ý phá giao dịch |
| Số phần tử trong collection | Getter tính `size()`, không `setSize` | Giá trị dẫn xuất |
| Danh sách mutable nội bộ | Getter trả snapshot/immutable data | Tránh làm lộ mutable reference |
| Khoảng ngày có quan hệ start/end | `reschedule(start,end)` hoặc immutable value | Cần validate cả cặp |
| DTO chuyển dữ liệu | JavaBeans-style getters/setters nếu framework cần | Hợp đồng chuyển dữ liệu đơn giản |
| Value object immutable | Constructor/record accessors, không setter | State không thay đổi sau khi tạo |
| Cache/lock nội bộ | Không getter/setter công khai | Chi tiết triển khai |
| Bộ đếm được nhiều thread tăng | `increment()` với atomic/synchronization | Read-modify-write phải nguyên tử |
| Password/secret | Không công khai raw getter tùy ý | Giữ ranh giới bảo mật |
| Trạng thái workflow | Commands `approve()`, `cancel()` | Ngăn chuyển trạng thái không hợp lệ |

### 18.1. Setter trả `void` hay trả `this`?

Theo JavaBeans-style thông thường, setter có dạng:

~~~java
public void setName(String name) {
    this.name = name;
}
~~~

Một fluent setter có thể viết:

~~~java
public Builder setName(String name) {
    this.name = name;
    return this;
}
~~~

Cả hai là **method Java hợp lệ**, nhưng một số công cụ nhận diện properties theo quy ước return type và tên có thể xử lý chúng khác nhau. Nếu API hướng tới framework yêu cầu bean convention, xem tài liệu framework; nếu API hướng tới fluent builder, có thể dùng `withName(...)` hoặc `name(...)` để diễn đạt rõ thiết kế.

### 18.2. Có nên dùng `setX` với kiểm tra không?

Có thể. Setter có validation là hợp lệ khi mục đích nghiệp vụ thật sự là **thay thuộc tính X**. Nhưng khi thay đổi kéo theo nhiều field, cần lịch sử giao dịch hoặc có invariant liên quan nhiều trường, command chuyên biệt dễ giữ hợp đồng hơn.

### 18.3. Getter có nên làm I/O hay thay đổi nhiều state không?

Một method tên `getX()` thường tạo kỳ vọng **đọc**. Một getter thực hiện truy cập mạng, thay state lớn hoặc ném lỗi bất ngờ khiến caller khó dự đoán. Lazy initialization/caching đôi khi hợp lý, nhưng nên cân nhắc thread safety, exception behavior, performance và tài liệu hóa. Nếu hoạt động thực sự đắt hoặc có side effect rõ, tên như `load...`, `fetch...` hoặc `refresh...` có thể phù hợp hơn.

## 19. Những lỗi thường gặp

1. **Tạo getter/setter cho mọi field chỉ vì có IDE Generate.** IDE tiết kiệm thao tác gõ; nó **không quyết định hợp đồng public API** thay bạn.
2. **Nghĩ `private` field + public setter tùy ý là đóng gói tốt.** Setter có thể vẫn phá invariant.
3. **Dùng setter thay command nghiệp vụ.** `setBalance`, `setStatus` có thể cho caller thực hiện hành vi không hợp lệ.
4. **Đưa tất cả validation sang caller.** Caller khác có thể quên kiểm tra; class phải tự bảo vệ invariant của mình.
5. **Getter trả thẳng mutable List/array.** Caller có thể sửa object nội bộ qua tham chiếu.
6. **Chỉ copy đầu vào, không xem getter trả ra gì.** Caller vẫn có thể sửa nội bộ qua getter.
7. **Chỉ copy ở getter, không copy đầu vào mutable.** Caller có thể giữ input reference và sửa dữ liệu object sau constructor.
8. **Tin `final List` là list immutable.** Final chỉ chặn gán lại field reference.
9. **Tin `Collections.unmodifiableList(source)` luôn là snapshot.** Nó có thể là view phản ánh thay đổi ở source.
10. **Tin `List.copyOf` deep-copy từng mutable element.** Nó bảo vệ cấu trúc nhưng không copy sâu các object phần tử.
11. **Tạo setters riêng cho hai field có quan hệ.** Một bước cập nhật có thể tạo invariant sai hoặc khiến chuyển trạng thái hợp lệ khó thực hiện.
12. **Công khai setter cho field dẫn xuất như `count`.** State có thể mâu thuẫn với dữ liệu gốc.
13. **Gọi overridable setters trong constructor tùy tiện.** Có thể dispatch vào subclass khi chưa khởi tạo xong.
14. **Cho rằng getter/setter tự thread-safe.** Chúng không tự đồng bộ hoặc tạo atomic transaction.
15. **Cho rằng record có JavaBeans `getX()/setX()` tự động.** Record mặc định có component accessor `x()`, không có setter.
16. **Cho rằng interface hoặc framework nào cũng yêu cầu public setters.** Yêu cầu tùy mô hình ánh xạ, cấu hình và version.
17. **Dùng getter để trả dữ liệu nhạy cảm không có quyền kiểm soát.** Có thể làm rò rỉ thông tin mà API không nên công bố.
18. **Dùng setter làm phát event hoặc lưu DB nhưng không nói rõ.** Caller không lường được side effect, hiệu năng và lỗi.

## 20. Bài tập tự kiểm tra có đáp án

**Câu 1.** Vì sao `private long balance` và `public void setBalance(long x)` không mặc nhiên bảo đảm đóng gói?

**Đáp án:** Vì caller vẫn có quyền gán tùy ý vào state thông qua setter; nếu không có invariant và business validation, object có thể sai nghiệp vụ. Nên xem `deposit`/`withdraw` nếu đó là hành động thật sự.

**Câu 2.** Getter `getMembers()` trả trực tiếp `List<String> members` mutable nội bộ, caller có thể làm gì?

**Đáp án:** Caller có thể gọi `clear`/`add` trên List được trả về, làm thay đổi state nội bộ dù field private và final. Cần snapshot, immutable list hoặc API có kiểm soát.

**Câu 3.** Nếu getter trả `List.copyOf(members)`, caller có thể sửa object phần tử mutable không?

**Đáp án:** Có thể nếu phần tử là object mutable và caller giữ tham chiếu đến chúng. `List.copyOf` không tạo deep copy mọi object phần tử.

**Câu 4.** Field `private final String id` có cần setter không?

**Đáp án:** Thông thường không nếu id là định danh bất biến. Constructor/factory tạo object với id hợp lệ, getter có thể cung cấp id nếu caller cần đọc.

**Câu 5.** `getArea()` có bắt buộc phải có field `area` không?

**Đáp án:** Không. Getter có thể tính diện tích từ `width` và `height`, không cần state dư thừa.

**Câu 6.** Tại sao object khoảng ngày không nên luôn mở độc lập `setStart` và `setEnd`?

**Đáp án:** Vì invariant `start <= end` liên quan hai field; cập nhật từng trường có thể đi qua trạng thái sai hoặc khiến một phép đổi cặp hợp lệ bị chặn. Nên cân nhắc command `reschedule(start,end)` hoặc immutable value.

**Câu 7.** Một Java record `record User(String name)` tự tạo `getName()` và `setName()` không?

**Đáp án:** Không. Record có accessor chuẩn `name()`; không tự sinh setters, component field là final theo quy tắc record.

**Câu 8.** DTO dùng với framework binding có thể cần setters không?

**Đáp án:** Có thể, tùy framework/cấu hình. Nhưng đừng áp dụng nhu cầu đó một cách máy móc lên mọi domain entity; có thể tách DTO và domain object.

**Câu 9.** `setCount(getCount() + 1)` có tự tăng nguyên tử khi nhiều thread cùng gọi không?

**Đáp án:** Không. Đó là một chuỗi đọc/tính/ghi; cần synchronization hoặc atomic operation như `AtomicInteger.incrementAndGet()`.

**Câu 10.** `public String getPassword()` có phải luôn nên tồn tại vì field `password` tồn tại không?

**Đáp án:** Không. Nếu đó là dữ liệu bí mật, API thường không nên công bố raw value vô điều kiện; class chỉ cần hỗ trợ những hành vi an toàn, có quyền kiểm soát phù hợp.

**Câu 11.** Setter `setTitle("  Java  ")` tự `trim` thành `"Java"` có đúng không?

**Đáp án:** Đúng nếu hợp đồng của class quy định chuẩn hóa như vậy. Không đúng nếu khoảng trắng là dữ liệu có ý nghĩa mà caller kỳ vọng được giữ nguyên.

**Câu 12.** `private List<String> list` và method `getList()` trả một `Collections.unmodifiableList(list)` có bảo đảm snapshot không thay đổi sau này không?

**Đáp án:** Không. Đây có thể là unmodifiable **view** của list gốc; nếu list gốc đổi, view vẫn phản ánh. Muốn snapshot cấu trúc, cân nhắc `List.copyOf` hoặc copy tương đương.

**Câu 13.** Constructor gọi public setter có thể gặp rủi ro gì khi class cho phép kế thừa?

**Đáp án:** Setter có thể bị subclass override và dynamic dispatch trong giai đoạn superclass khởi tạo, khi fields subclass chưa sẵn sàng. Dùng helper không overridable hoặc logic khởi tạo được kiểm soát.

**Câu 14.** Một getter `getBalance()` có nghĩa caller được sửa balance không?

**Đáp án:** Không. Getter chỉ cung cấp giá trị đọc theo hợp đồng; setter hoặc command để sửa là quyết định API riêng.

## 21. Checklist chọn getter/setter cho class Java

Trước khi nhấn “Generate Getters and Setters” trong IDE, hãy tự hỏi:

1. **Trách nhiệm class:** đây là DTO, value object, entity hay service? Chúng có nhu cầu công bố state khác nhau.
2. **Getter có mục đích hợp lệ không?** Caller thật sự cần đọc giá trị hay chỉ cần một hành vi trừu tượng hơn?
3. **Getter có làm lộ mutable reference hoặc dữ liệu nhạy cảm không?** Cân nhắc snapshot, immutable view, derived data hoặc không công khai.
4. **Setter có đại diện cho một thao tác hợp lệ không?** Nếu không, chọn command có tên theo nghiệp vụ hoặc loại bỏ setter.
5. **Validation có thuộc class không?** Class phải tự bảo vệ invariant dù caller quên kiểm tra.
6. **Một setter có cần đổi nhiều field cùng lúc không?** Dùng phương thức cập nhật trọn trạng thái nếu cần.
7. **Có field final hoặc computed không?** Thông thường không tạo setter cho chúng.
8. **State nên immutable không?** Constructor, record hoặc phương thức trả object mới có thể đơn giản hơn.
9. **Có aliasing mutable object không?** Kiểm tra cả dữ liệu nhận vào và dữ liệu trả ra.
10. **Có code framework cần bean convention không?** Kiểm tra đúng contract của framework thay vì mở setter đại trà.
11. **Có subclass override method không?** Tránh gọi accessor overridable từ constructor thiếu kiểm soát.
12. **Có nhiều thread truy cập không?** Getter/setter không thay thế concurrency protocol.
13. **Có side effect hoặc I/O không?** Đặt tên và tài liệu hóa hợp đồng thực tế.
14. **API công khai có bền vững không?** Một khi caller phụ thuộc vào method, đổi access/name/behavior có thể gây breaking change.

**Kết luận:** Getter và setter là **công cụ** để đóng gói, không phải **mục đích** của đóng gói. Getter cho caller quyền quan sát một phần trạng thái; setter cung cấp một con đường cập nhật. Khi dữ liệu không nên bị sửa tùy ý, **không cần setter**; khi state không nên lộ, **không cần getter**. Một class Java được thiết kế tốt công bố **đúng những gì caller cần**, xác thực những thay đổi được phép và giữ bất biến của mình, thay vì sao chép máy móc một cặp `getX/setX` cho mọi field.
