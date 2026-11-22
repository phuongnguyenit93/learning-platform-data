# Phân biệt thành viên `static` với thành viên đối tượng — Java 17+

## 1. `static` thuộc lớp, instance thuộc từng đối tượng

Trong một lớp Java, **thành viên** thường là trường (*field*) hoặc phương thức (*method*). Từ khóa `static` quyết định thành viên được gắn với **lớp** thay vì gắn với từng **đối tượng (instance)**.

~~~java
class Counter {
    static int createdCount; // Static field: gắn với lớp Counter.
    int value;               // Instance field: thuộc từng Counter.

    Counter(int value) {
        this.value = value;
        createdCount++;
    }

    void increase() {        // Instance method: làm việc với đối tượng hiện tại.
        value++;
    }

    static int count() {     // Static method: làm việc không cần receiver instance.
        return createdCount;
    }
}
~~~

~~~java
Counter a = new Counter(2);
Counter b = new Counter(10);
a.increase();
System.out.println(a.value);
System.out.println(b.value);
System.out.println(Counter.count());
~~~

**Exact stdout**, khi các dòng gọi được đặt trong `main` thích hợp của một lần chạy mới:

~~~text
3
10
2
~~~

Hai lần `new Counter(...)` tạo **hai đối tượng** có `value` riêng. Ngược lại, `createdCount` là **một trường static của lớp `Counter`** và tăng ở cả hai lần gọi constructor.

**Quy tắc nhớ:** `static` gắn với **kiểu/lớp**; **instance** gắn với **đối tượng cụ thể**. Không nên hiểu static là “một bản riêng cho mỗi đối tượng”, cũng không hiểu instance là “biến chung của mọi đối tượng”.

## 2. Bảng phân biệt nhanh

| Tiêu chí | Thành viên `static` | Thành viên instance |
|---|---|---|
| Có từ khóa `static`? | **Có** | **Không** |
| Gắn với | Lớp khai báo | Mỗi đối tượng của lớp |
| Field lưu gì? | Trạng thái chung ở cấp lớp | Trạng thái riêng của object |
| Cách đọc/gọi khuyến nghị | `Counter.count()` | `a.increase()` |
| Cần `new Counter(...)` trước khi gọi? | Không, nếu có quyền truy cập phù hợp | Cần một đối tượng/receiver |
| Có `this` trong phương thức? | Không | Có, trỏ đến receiver hiện tại |
| Có truy cập trực tiếp instance field? | Không, nếu không có receiver cụ thể | Có |
| Có truy cập static field? | Có | Có, nhưng thường dùng tên lớp cho rõ |
| Ví dụ | `static int createdCount` | `int value` |

Chữ `static` không đồng nghĩa với **hằng số**. Một `static int` vẫn có thể thay đổi. Chỉ khi thêm `final` mới có ràng buộc không thể gán lại **biến field** sau khi được khởi tạo theo quy tắc Java.

## 3. Instance fields: trạng thái riêng của từng object

~~~java
class Box {
    private int size;

    Box(int size) {
        this.size = size;
    }

    void grow(int amount) {
        size += amount;
    }

    int getSize() {
        return size;
    }
}
~~~

~~~java
Box small = new Box(2);
Box large = new Box(10);
small.grow(3);
System.out.println(small.getSize());
System.out.println(large.getSize());
~~~

**Exact stdout:**

~~~text
5
10
~~~

`size` là **instance field**. Hai đối tượng cùng kiểu `Box` có các giá trị `size` **độc lập**. Gọi `small.grow(3)` cập nhật đối tượng mà `small` trỏ tới, không cập nhật `large`.

Một biến tham chiếu được gán `Box alias = small;` **không tạo Box mới**: `alias` và `small` trỏ cùng object. Khi đó, `alias.grow(1)` làm `small.getSize()` thay đổi. Đây là **chia sẻ đối tượng qua hai tham chiếu**, không phải do field trở thành static.

## 4. Static fields: dữ liệu chung ở cấp lớp

~~~java
class Ticket {
    private static int nextNumber = 1;
    private final int number;

    Ticket() {
        number = nextNumber++;
    }

    int getNumber() {
        return number;
    }

    static int nextAvailableNumber() {
        return nextNumber;
    }
}
~~~

~~~java
Ticket a = new Ticket();
Ticket b = new Ticket();
System.out.println(a.getNumber());
System.out.println(b.getNumber());
System.out.println(Ticket.nextAvailableNumber());
~~~

**Exact stdout**, với một lần chạy mới:

~~~text
1
2
3
~~~

- `nextNumber` là **static field**, giúp các constructor chia sẻ bộ đếm tiếp theo.
- `number` là **instance field** của từng vé; vé `a` nhận `1`, vé `b` nhận `2`.
- `Ticket.nextAvailableNumber()` là **static method** nên gọi bằng tên lớp, không cần tạo thêm `Ticket`.

Một static field bình thường được Java cấp phát và khởi tạo khi lớp được khởi tạo theo quy tắc của JVM; đây không phải “một field nằm trong từng đối tượng”. Trong môi trường có nhiều class loader, cần phân biệt phạm vi định danh lớp; không nên coi mọi static field là **một biến toàn cục duy nhất trong mọi JVM**.

## 5. Gọi phương thức static và instance

~~~java
class MathBox {
    private int value;

    MathBox(int value) {
        this.value = value;
    }

    int doubleValue() {
        return this.value * 2;
    }

    static int square(int n) {
        return n * n;
    }
}
~~~

~~~java
MathBox box = new MathBox(5);
System.out.println(box.doubleValue());   // Instance method.
System.out.println(MathBox.square(5));   // Static method.
~~~

**Exact stdout:**

~~~text
10
25
~~~

**Phương thức instance** có receiver, tức một object cụ thể. Trong `box.doubleValue()`, `this` chính là object mà `box` đang tham chiếu.

**Phương thức static** không có receiver instance ngầm định. `MathBox.square(5)` hoạt động với đối số `5` và không cần tham chiếu tới object `MathBox` nào.

Java cho phép một số cú pháp gọi static method qua biến instance, ví dụ `box.square(5)`; nhưng cách này dễ tạo ấn tượng sai về receiver. **Nên gọi bằng tên lớp: `MathBox.square(5)`.** Nếu biết tên lớp và phương thức static được phép truy cập, không cần `new` object để gọi.

## 6. `this` không dùng trong static context

~~~java
class User {
    private String name;
    private static int count;

    String describe() {
        return this.name;    // Hợp lệ: đang ở instance method.
    }

    static int getCount() {
        return count;        // Hợp lệ: đọc static field.
    }

    // static String wrong() {
    //     return this.name; // LỖI: static context không có this.
    // }
}
~~~

Một static method **không thể trực tiếp** đọc instance field `name` mà không có object cụ thể. Muốn đọc, nhận object làm đối số hoặc tạo một object hợp lệ:

~~~java
static String describeUser(User user) {
    return user.name;  // Truy cập thông qua tham chiếu user.
}
~~~

Trong ví dụ này, `describeUser` thuộc **cùng lớp `User`**, nên có thể truy cập field `private name` của một đối tượng `User`. Nếu đặt trong lớp khác, cần quyền truy cập thích hợp (ví dụ gọi getter).

Ngược lại, một instance method có thể dùng static field/method cùng lớp; dù viết được `count` không kèm tên lớp, cách `User.count` thường làm rõ đây là dữ liệu chung.

**Lưu ý:** `main(String[] args)` cũng là static method, nên không có `this`. Để gọi một instance method từ `main`, hãy tạo hoặc nhận một object trước.

## 7. Static initializer và thời điểm khởi tạo

~~~java
class Settings {
    static int limit = 10;

    static {
        limit += 5;
    }

    static int getLimit() {
        return limit;
    }
}
~~~

Khi lớp `Settings` được khởi tạo, các static fields và static initializer blocks được xử lý theo thứ tự văn bản khai báo. Trong ví dụ trên, sau khi khởi tạo, `Settings.getLimit()` trả **`15`**.

Instance initializer/constructor là cơ chế khác, xảy ra khi tạo từng đối tượng. **Việc import một lớp** không phải lệnh “chạy constructor” hoặc khởi tạo tất cả object của lớp đó.

Static initialization được JVM quản lý (thông thường trước lần sử dụng chủ động cần khởi tạo lớp). Không nên tự suy đoán mọi lớp được khởi tạo chính xác tại thời điểm biên dịch hoặc ngay khi file nguồn được import.

## 8. `static final`: hằng cấp lớp và giới hạn bất biến

~~~java
class Limits {
    static final int MAX_ITEMS = 100;
    static final String UNIT = "items";
}
~~~

Có thể đọc bằng `Limits.MAX_ITEMS` và `Limits.UNIT` mà không cần tạo đối tượng. Những field kiểu primitive/String dùng `static final` thường thích hợp cho các hằng không đổi như giới hạn, nhãn hoặc đơn vị.

Tuy nhiên, `final` chỉ ngăn **gán lại field**, không tự “đóng băng” nội dung object mà field tham chiếu:

~~~java
class Holder {
    static final int[] VALUES = {1, 2};
}
~~~

`Holder.VALUES = new int[]{3};` không hợp lệ, nhưng `Holder.VALUES[0] = 9;` **vẫn hợp lệ** nếu mảng còn có thể truy cập và không có kiểm soát khác. Vì thế, tránh công khai trực tiếp những static arrays/collections mutable khi cần bảo vệ dữ liệu.

**Thành viên interface** còn có một số quy tắc riêng: field khai báo trong interface là `public static final` theo ngầm định; bài này tập trung vào so sánh static/instance trong lớp thông thường.

## 9. Static mutable state: dùng đúng phạm vi

Static field có thể hữu ích để giữ:

- Hằng cấu hình không đổi: `static final`.
- Bộ đếm số object được tạo hoặc số lần một thao tác diễn ra.
- Hàm tiện ích không cần trạng thái instance, ví dụ `Math.max(...)`.
- Dữ liệu chung có chủ đích, có quy tắc cập nhật rõ ràng.

Không phải dữ liệu nào cũng nên để static. Nếu đặt `balance` của tài khoản ngân hàng thành static thì **mọi object tài khoản cùng dùng một số dư**, sai yêu cầu “mỗi tài khoản một số dư riêng”.

Một static field mutable cũng làm các phần khác của chương trình **chia sẻ trạng thái**. Trong chương trình nhiều luồng, `counter++` không phải phép tăng nguyên tử; có thể cần đồng bộ hoặc các công cụ như `AtomicInteger`, tùy bài toán. Trong test, static mutable state còn có thể tồn tại xuyên các test nếu không được reset. Những vấn đề này không phát sinh chỉ vì từ khóa `static` “xấu”; chúng là hệ quả của **trạng thái chung và cách quản lý vòng đời**.

Với ví dụ giáo dục bên dưới, bộ đếm và tổng số dư dùng static để biểu diễn thống kê chung. Đây là bản minh họa **một luồng**, không phải cài đặt giao dịch tài chính an toàn cho production.

## 10. Chương trình Java 17+ độc lập

Lưu đúng tên file **`StaticInstanceMembersDemo.java`**:

~~~java
public final class StaticInstanceMembersDemo {
    private StaticInstanceMembersDemo() {}

    // Lớp lồng static để ví dụ chạy từ một file.
    static final class Account {
        static final String CURRENCY = "VND";   // Hằng cấp lớp.

        private static int createdCount;        // Field chung.
        private static int nextId = 1;          // Field chung.
        private static int totalBalance;        // Tổng số dư chung.

        private final int id;                   // Field instance.
        private final String owner;             // Field instance.
        private int balance;                    // Field instance.

        Account(String owner, int openingBalance) {
            if (owner == null || owner.isBlank()) {
                throw new IllegalArgumentException("owner must not be blank");
            }
            if (openingBalance < 0) {
                throw new IllegalArgumentException("negative opening balance");
            }

            this.owner = owner.strip();
            this.balance = openingBalance;
            this.id = nextId++;
            createdCount++;
            totalBalance += openingBalance;
        }

        void deposit(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            this.balance += amount;
            totalBalance += amount;
        }

        boolean withdraw(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            if (amount > this.balance) {
                return false;
            }
            this.balance -= amount;
            totalBalance -= amount;
            return true;
        }

        String summary() {
            return id + ":" + owner + ":" + balance;
        }

        static int getCreatedCount() {
            return createdCount;
        }

        static int getTotalBalance() {
            return totalBalance;
        }
    }

    public static void main(String[] args) {
        System.out.println("currency=" + Account.CURRENCY);
        System.out.println("created initially=" + Account.getCreatedCount());
        System.out.println("total initially=" + Account.getTotalBalance());

        Account an = new Account(" An ", 100);
        Account binh = new Account("Binh", 50);
        System.out.println("created after new=" + Account.getCreatedCount());
        System.out.println("total after new=" + Account.getTotalBalance());
        System.out.println("an initial=" + an.summary());
        System.out.println("binh initial=" + binh.summary());

        an.deposit(20);
        System.out.println("withdraw Binh 10=" + binh.withdraw(10));
        System.out.println("withdraw Binh 100=" + binh.withdraw(100));
        System.out.println("an after operations=" + an.summary());
        System.out.println("binh after operations=" + binh.summary());
        System.out.println("shared total=" + Account.getTotalBalance());

        Account alias = an;
        alias.deposit(5);
        System.out.println("alias same An=" + (alias == an));
        System.out.println("an via alias=" + an.summary());
        System.out.println("created after alias=" + Account.getCreatedCount());
        System.out.println("shared total after alias=" + Account.getTotalBalance());

        try {
            new Account(" ", 30);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid owner=" + ex.getMessage());
        }
        System.out.println("created final=" + Account.getCreatedCount());
        System.out.println("shared total final=" + Account.getTotalBalance());
    }
}
~~~

Yêu cầu **JDK 17 trở lên**; không cần Maven, Gradle, thư viện ngoài JDK hoặc preview features. File có một public top-level class khớp tên file. `Account` là **static nested class** nhằm gom ví dụ vào một file; từ khóa `static` ở kiểu lồng nghĩa là không cần một instance của lớp bao ngoài để tạo `Account`, khác với các static fields bên trong `Account`.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 StaticInstanceMembersDemo.java
java -cp . StaticInstanceMembersDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\StaticInstanceMembersDemo.java
java -cp . StaticInstanceMembersDemo
~~~

### Exact expected stdout

~~~text
currency=VND
created initially=0
total initially=0
created after new=2
total after new=150
an initial=1:An:100
binh initial=2:Binh:50
withdraw Binh 10=true
withdraw Binh 100=false
an after operations=1:An:120
binh after operations=2:Binh:40
shared total=160
alias same An=true
an via alias=1:An:125
created after alias=2
shared total after alias=165
invalid owner=owner must not be blank
created final=2
shared total final=165
~~~

**Phân tích:**

1. `Account.CURRENCY` là static final constant. `createdCount` và `totalBalance` là static fields, khởi đầu với giá trị mặc định `0`; `nextId` bắt đầu bằng `1`.
2. Hai constructor thành công tạo `an` và `binh`: số tài khoản là `2`, tổng ban đầu `100 + 50 = 150`. Mỗi object có `id`, `owner`, `balance` riêng.
3. `an.deposit(20)` làm số dư An thành `120`. `binh.withdraw(10)` làm số dư Binh thành `40`. Rút `100` bị từ chối nên không đổi dữ liệu. Tổng static lúc này là `120+40=160`.
4. `Account alias = an;` **không tạo tài khoản mới**, mà chia sẻ một object. Nạp `5` qua alias làm An thành `125`, tổng chung thành `165`, nhưng số account được tạo vẫn là `2`.
5. Constructor với `" "` ném ngoại lệ **trước** các dòng cập nhật static, vì thế đếm/tổng không đổi.

## 11. Những lỗi thường gặp

| Sai lầm | Vì sao sai? | Cách sửa |
|---|---|---|
| Nghĩ `static int count` có một bản trong mỗi object | Static field gắn với lớp | Chỉ dùng static cho dữ liệu chung thực sự |
| Nghĩ `int balance` trong lớp tự là static | Thiếu `static` nên là instance field | Phân biệt từng khai báo |
| Gọi `Account.summary()` như static | `summary()` là instance method | Dùng `an.summary()` |
| Gọi `this.balance` trong static method | Static context không có `this` | Truy cập qua object cụ thể |
| Viết `new Account(...)` chỉ để gọi static method | Tạo object không cần thiết | Dùng `Account.getCreatedCount()` |
| Gọi `an.getCreatedCount()` khiến tưởng count thuộc An | Static member được gọi qua class mới rõ | `Account.getCreatedCount()` |
| Nghĩ `static final int[]` là mảng bất biến | `final` chỉ cố định tham chiếu field | Tránh lộ array mutable hoặc trả bản sao |
| Dùng static cho mọi field để tiện truy cập | Trộn trạng thái các object, khó test | Dùng instance field khi dữ liệu thuộc từng object |
| Tin `counter++` static luôn an toàn giữa các luồng | Read-modify-write không nguyên tử | Cần cơ chế thread safety nếu chia sẻ đa luồng |
| Nhầm gán `alias = an` với sao chép account | Đây là sao chép tham chiếu | Tạo object mới nếu cần trạng thái độc lập |

## 12. Bài tập và đáp án

**A — Phân loại thành viên:**

~~~java
class Sensor {
    static int sensorCount;
    int temperature;
    static int getSensorCount() { return sensorCount; }
    int read() { return temperature; }
}
~~~

**Đáp án:** `sensorCount` và `getSensorCount()` là **static**; `temperature` và `read()` là **instance**.

**B — Hai object chia sẻ gì?**

~~~java
class Marker {
    static int created;
    int color;

    Marker(int color) {
        this.color = color;
        created++;
    }
}
~~~

Sau `new Marker(1)` và `new Marker(2)`, có **hai giá trị instance `color` riêng**, còn `Marker.created == 2` là trạng thái static chung.

**C — Static method có được đọc instance field?**  
**Đáp án:** không thể đọc **trực tiếp** khi không có receiver. Có thể nhận object làm đối số rồi đọc qua tham chiếu đó nếu có quyền truy cập.

**D — Hai biến cùng object có giống static không?**  
**Đáp án:** không. `Account b = a;` khiến hai biến trỏ cùng **một** object; đó là aliasing. Một instance field vẫn thuộc đúng object ấy chứ không trở thành static.

**E — `static final int[] VALUES` có cấm `VALUES[0] = 5` không?**  
**Đáp án:** không; `final` cấm gán lại field `VALUES`, nhưng không tự khiến phần tử mảng bất biến.

**F — Tại sao `createdCount` không nên là instance field nếu mục đích là đếm mọi account được tạo?**  
**Đáp án:** mỗi object sẽ có bản đếm riêng. Static field biểu diễn một bộ đếm dùng chung; cần cập nhật nhất quán và lưu ý vấn đề đa luồng nếu có.

## 13. Checklist và kết luận

- [ ] Nhận diện trường/phương thức nào có từ khóa `static`.
- [ ] Phân biệt field **chung ở cấp lớp** và field **riêng của object**.
- [ ] Biết gọi static method bằng tên lớp, instance method qua receiver.
- [ ] Không dùng `this` trong static context.
- [ ] Hiểu instance method có thể truy cập cả instance lẫn static member.
- [ ] Hiểu constructor tạo object riêng nhưng có thể cập nhật static counter chung.
- [ ] Phân biệt `static` với `final`; biết `static final` không làm object mutable thành bất biến.
- [ ] Biết static initializer liên quan đến khởi tạo lớp, không phải tạo từng object.
- [ ] Hiểu aliasing là chia sẻ object, không phải thành viên static.
- [ ] Biết rủi ro static mutable state trong test/đa luồng.
- [ ] Biên dịch và chạy `StaticInstanceMembersDemo.java` với Java 17+, đối chiếu exact stdout.

**Kết luận:** **Thành viên static thuộc về lớp**, dùng cho dữ liệu và hành vi chung không gắn với một instance cụ thể. **Thành viên đối tượng thuộc về từng instance**, dùng để biểu diễn trạng thái và hành vi riêng. Chọn đúng phạm vi thành viên giúp tránh trộn dữ liệu các object, làm rõ nơi được phép dùng `this` và kiểm soát những trạng thái chia sẻ.