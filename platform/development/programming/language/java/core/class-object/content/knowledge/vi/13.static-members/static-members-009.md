# Rủi ro trạng thái `static` có thể thay đổi và kiểm thử phụ thuộc nhau trong Java

Trong Java, một field có từ khóa `static` thuộc **class tại runtime**, không thuộc riêng từng object. Nếu field đó **có thể thay đổi (mutable)**, mọi code cùng sử dụng class runtime tương ứng có thể tác động lên cùng trạng thái chung. Đây là một công cụ hữu ích, nhưng dễ tạo ra các lỗi khó phát hiện: test chạy riêng thì đạt nhưng chạy cả bộ test thì hỏng; thay thứ tự test làm đổi kết quả; hai request tác động lẫn nhau; hoặc chương trình chạy lâu giữ dữ liệu cũ và không giải phóng tài nguyên.

Ví dụ:

~~~java
class Discount {
    static int percent = 0;

    static int priceAfterDiscount(int price) {
        return price - price * percent / 100;
    }
}
~~~

Một test gọi `Discount.percent = 20`. Test khác kỳ vọng giá trị mặc định `0` nhưng lại chạy **trong cùng JVM và trên cùng class runtime**. Nếu không cô lập, kết quả test thứ hai phụ thuộc vào test thứ nhất. Điều đáng ngại không nằm ở phép tính giảm giá mà ở **phụ thuộc ẩn qua field static**.

Bài học tập trung vào chủ đề **Thành viên static** của Java Core — Class & Object: cách shared mutable static state hoạt động, vì sao nó gây test-order dependence, isolation failure, thread-safety và memory-retention problems, cùng những chiến lược xử lý từ mức đơn giản tới thiết kế có thể kiểm thử tốt. Các chương trình độc lập dùng **Java 17+**, có lệnh biên dịch/chạy và stdout để đối chiếu.

## 1. Mục tiêu học tập

Sau khi hoàn thành, bạn sẽ có thể:

1. Giải thích vì sao hai object khác nhau có thể đọc/ghi **cùng một static field**.
2. Phân biệt static **constant**, static **mutable primitive**, static **reference đến mutable object**.
3. Chỉ ra **hidden shared state** khi code không truyền tham số nhưng hành vi vẫn thay đổi.
4. Giải thích vì sao kết quả test phụ thuộc **thứ tự, test chạy trước, chạy cùng JVM và cách reset**.
5. Tạo một demo tái hiện test có thể PASS khi chạy riêng nhưng FAIL khi chạy sau test khác.
6. Phân biệt **isolation between tests** với **thread safety**; một giải pháp có thể chỉ xử lý được một vấn đề.
7. Biết giới hạn của `@BeforeEach`, `@AfterEach`, `@BeforeAll`, reset helpers và các framework test.
8. Cân nhắc alternatives: **instance-owned state**, dependency injection, pure functions, immutable configuration và controlled lifecycle.
9. Hiểu `static final` không đảm bảo object được tham chiếu là immutable.
10. Nhận biết global caches, singletons, mutable registries, static clocks/random generators và `ThreadLocal` có thể gây rò rỉ trạng thái.
11. Sử dụng `AtomicInteger`, synchronization hoặc concurrent collections đúng tình huống.
12. Viết test dựa trên **public behavior**, không phụ thuộc vào môi trường còn sót từ test khác.
13. Xem xét module/class-loader boundaries khi nói “một bản static trên toàn JVM”.
14. Có quy trình điều tra và khắc phục một test bị lỗi ngẫu nhiên theo suite order.

## 2. Vì sao `static` tạo shared state?

Xét hai field:

~~~java
class VisitTracker {
    int localVisits;
    static int totalVisits;

    void visit() {
        localVisits++;
        totalVisits++;
    }
}
~~~

Hai object độc lập:

~~~java
VisitTracker a = new VisitTracker();
VisitTracker b = new VisitTracker();
a.visit();
b.visit();
~~~

Sơ đồ trạng thái:

~~~text
Class VisitTracker
  static totalVisits = 2
          ^       ^
          |       |
      a object   b object
      local=1    local=1
~~~

`a.localVisits` và `b.localVisits` là **instance fields**: mỗi object có một giá trị riêng. `VisitTracker.totalVisits` là **static field**: cùng một giá trị được cập nhật bởi hai lời gọi khác nhau.

Vì vậy, câu hỏi đúng không phải “object A có tác động object B không?”, mà là **“cả hai object có cùng đọc/ghi một field static hoặc một mutable object được tham chiếu bởi field static không?”**.

### Những điều không nên suy ra quá mức

- Static field không được sao chép riêng cho mỗi instance mới.
- `VisitTracker alias = a;` chỉ tạo reference alias; nó không gọi constructor và không tạo bản static mới.
- Static field cũng **không luôn duy nhất tuyệt đối cho mọi class cùng tên trên JVM**. Những class runtime khác nhau được định nghĩa bởi các class loaders khác nhau có thể mang static states riêng.
- Static không tự bảo đảm atomicity, visibility, security, isolation hay tính bất biến.

Trong chương trình học console dùng một class loader thông thường, mô hình “một static field chung cho class” là đủ để hiểu các ví dụ.

## 3. Static mutable state gồm những loại nào?

Không chỉ field không có `final` mới nguy hiểm.

| Khai báo | Có thể thay đổi gì? | Rủi ro khi dùng chung |
| --- | --- | --- |
| `static int count;` | Giá trị int của field | Test khác tăng/giảm giá trị |
| `static String mode;` | Reference field có thể được gán lại | Một test thay cấu hình của test khác |
| `static final int LIMIT = 10;` | Không thể gán lại field, giá trị primitive cố định | Thường ít rủi ro mutable state |
| `static final String PREFIX = "ID-";` | String immutable; field final | Phù hợp làm constant nếu đúng hợp đồng |
| `static final List<String> EVENTS = new ArrayList<>();` | Nội dung List object vẫn sửa được | Test có thể thêm/xóa event của nhau |
| `static final AtomicInteger COUNT = new AtomicInteger();` | Giá trị bên trong AtomicInteger thay đổi | Thread-safe từng atomic operation, vẫn dùng chung giữa tests |
| `static final Map<K,V> CACHE = new ConcurrentHashMap<>();` | Contents map thay đổi | Thread-safe ở mức API nhất định, **không tự cô lập tests** |
| `static final Clock CLOCK = Clock.systemUTC();` | Reference cố định; kết quả clock thay theo thời gian | Test phụ thuộc wall-clock và môi trường |
| `static final Random RNG = new Random();` | Trạng thái PRNG tiến triển khi lấy số | Thứ tự gọi làm đổi sequence trong test |

**Điểm cốt lõi:** `final` trên reference chỉ giới hạn **gán lại reference của field**. Nó không đóng băng toàn bộ object graph bên trong.

## 4. Ví dụ chạy: test-order dependence xuất hiện thế nào?

Tạo file **`StaticTestOrderDemo.java`**:

~~~java
public class StaticTestOrderDemo {
    static final class Discount {
        static int percent = 0;

        static int finalPrice(int base) {
            return base - base * percent / 100;
        }
    }

    static void expect(String label, int expected, int actual) {
        String result = expected == actual ? "PASS" : "FAIL";
        System.out.println(label + ": " + result
                + " (expected=" + expected + ", actual=" + actual + ")");
    }

    static void testDefaultPrice() {
        expect("default", 100, Discount.finalPrice(100));
    }

    static void testWithDiscount() {
        Discount.percent = 20;
        expect("discount", 80, Discount.finalPrice(100));
    }

    public static void main(String[] args) {
        System.out.println("Order A");
        testDefaultPrice();
        testWithDiscount();

        System.out.println("Order B");
        testDefaultPrice();
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticTestOrderDemo.java
java StaticTestOrderDemo
~~~

Stdout:

~~~text
Order A
default: PASS (expected=100, actual=100)
discount: PASS (expected=80, actual=80)
Order B
default: FAIL (expected=100, actual=80)
~~~

### Phân tích từng mốc

1. Khi class `Discount` được khởi tạo, `percent` có giá trị `0`.
2. Lần đầu gọi `testDefaultPrice`, kết quả là 100 → PASS.
3. `testWithDiscount` **ghi static field thành 20**, tính 80 → PASS.
4. Không có lệnh nào đưa field trở về 0.
5. `testDefaultPrice` chạy lại trong **cùng JVM và cùng class runtime** nên nhận `percent = 20`, trả 80 → FAIL.

Đây là **test double-runner mô phỏng**, không dùng JUnit. Mục tiêu là minh họa một lỗi thật: tên method và kết quả mong đợi không thay đổi, chỉ **state bên ngoài method** đã bị một test khác sửa.

### Nếu chạy hai lần `java StaticTestOrderDemo` thì sao?

Mỗi lệnh `java` thông thường khởi chạy một JVM process mới và khởi tạo class runtime mới. State static từ process trước không tự chuyển sang process mới. Nhưng **một bộ test chạy nhiều test cases trong cùng JVM** có thể giữ class state qua các lần gọi. Test runner thường không bảo đảm tạo một JVM mới cho từng test method.

Do đó không nên kết luận “tôi chạy riêng vẫn đạt nên test đúng”. Cần kiểm tra **khi chạy trong cùng suite**.

## 5. Static state tạo phụ thuộc ẩn giữa các test

Một test tốt nên nói rõ:

- Nó cần input gì.
- State ban đầu phải thỏa điều kiện gì.
- Hành vi được thực thi.
- Kết quả được mong đợi.
- Những side effects phải được dọn thế nào.

Với field static, state có thể được thay đổi bởi các phần của hệ thống **không xuất hiện trong lời gọi method của test hiện tại**:

~~~text
Test A:
  set Discount.percent = 20
       |
       v
  Shared static field
       |
       v
Test B:
  calls Discount.finalPrice(100)
  observes 80, expected 100
~~~

Đây là **hidden coupling**: Test B không gọi Test A, không nhận parameter từ Test A và không biết phải phụ thuộc Test A. Nhưng hành vi lại thay đổi theo kết quả chạy của Test A.

### Những triệu chứng thường gặp

- Test đạt khi chạy từ IDE một mình, thất bại khi chạy toàn suite.
- Chạy lại một test nhiều lần trong cùng process thì kết quả thay đổi.
- Đổi thứ tự test làm đổi test nào thất bại.
- Đưa test chạy song song thì xuất hiện lỗi thỉnh thoảng mới xảy ra.
- Đặt `@BeforeEach` ở một test class nhưng một test class khác vẫn sửa global state.
- Static cache làm một test đọc dữ liệu cũ không thuộc scenario hiện tại.
- Mock/static configuration không được phục hồi sau khi test kết thúc.

Đây là **dấu hiệu cần điều tra**, không phải bằng chứng rằng mọi lỗi bất ổn đều do static: cũng có thể là clock, mạng, random, I/O, database, race condition hoặc test setup không đúng.

## 6. Khi nào test thực sự “độc lập”?

Một test được thiết kế tốt cần có khả năng được chạy:

- Riêng lẻ.
- Cùng các test khác.
- Theo nhiều thứ tự khác nhau.
- Nhiều lần.
- Trên các worker/process phù hợp với cấu hình test.
- Song song nếu suite tuyên bố hỗ trợ parallelism.

Không phải mọi suite đều phải chạy song song. Nhưng nếu một test cần test khác chạy trước để chuẩn bị một static field, đó là **phụ thuộc không mong muốn** trừ khi hệ thống test cố ý thiết kế một integration flow có lifecycle được quản lý rõ ràng.

Hai nguyên tắc:

**Independence**: Kết quả test không lệ thuộc vào test khác từng gọi gì.

**Isolation**: Các test không vô tình dùng chung mutable state hoặc tài nguyên mà chúng không kiểm soát.

Isolation là một cách đạt independence, nhưng test còn có thể bị phụ thuộc môi trường qua file, database, network, timezone hoặc system properties. Vì vậy sửa một static field mới chỉ giải quyết một phần của bức tranh.

## 7. Vì sao `static` là rủi ro nhưng không phải lúc nào cũng sai?

Một **static immutable constant** thường dễ dùng và đáng tin:

~~~java
public final class Limits {
    public static final int MAX_ITEMS = 100;

    private Limits() {
    }
}
~~~

Không có đường thay đổi `MAX_ITEMS` trong code Java thông thường. Test sử dụng constant này thường không làm ảnh hưởng trạng thái của test khác.

Ngược lại, mutable registry:

~~~java
class Registry {
    static final java.util.List<String> entries =
            new java.util.ArrayList<>();
}
~~~

cho phép bất kỳ code được cấp quyền truy cập thích hợp gọi `entries.add(...)` và thay nội dung chung.

**Vấn đề không phải từ khóa `static` tự thân, mà là kết hợp giữa:**

1. Trạng thái **có thể thay đổi**.
2. Phạm vi chia sẻ **rộng**.
3. Nhiều caller có quyền thay đổi.
4. Không có cơ chế xác định **owner và lifecycle**.
5. Test không tự dựng lại trạng thái đầu vào.
6. Các thao tác concurrent không được bảo vệ đúng cách.

Một static method **pure** chỉ dựa trên arguments vẫn có thể rất dễ kiểm thử, ví dụ `Math.max(a, b)`. Không nên cấm mọi static member khi mục tiêu chỉ là tránh mutable global state.

## 8. Khắc phục cách 1: reset ở ranh giới test

Một biện pháp nhanh để cứu code cũ là reset static state về một **trạng thái đã biết** trước mỗi test.

Ví dụ:

~~~java
class Discount {
    private static int percent;

    static void configure(int value) {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException("invalid discount");
        }
        percent = value;
    }

    static void resetForTests() {
        percent = 0;
    }

    static int finalPrice(int base) {
        return base - base * percent / 100;
    }
}
~~~

Đây là **class minh họa**, không phải API khuyến nghị công khai reset cho mọi hệ thống. Tùy kiến trúc, `resetForTests` nên chỉ có quyền truy cập phù hợp với tests, hoặc reset thông qua fixture được kiểm soát.

Một test có thể gọi:

~~~java
Discount.resetForTests();
Discount.configure(20);
// Assert Discount.finalPrice(100) == 80.
~~~

Reset giúp mỗi test bắt đầu với điều kiện rõ. Nhưng nó có **giới hạn quan trọng**:

- Nếu hai tests chạy **song song** và dùng cùng static field, reset của test A có thể xóa state mà test B đang dùng.
- Nếu còn một static cache, listener, thread hoặc resource liên quan chưa reset, việc gán `percent=0` chưa hoàn tất cleanup.
- Một test có thể dừng vì exception ở giữa, khiến cleanup cuối test không chạy nếu tổ chức sai.
- Nếu nhiều test classes cùng tác động lên static field, cần một quy ước reset nhất quán giữa các classes.
- Nếu test mãi phải gọi reset global, có thể đó là dấu hiệu nên **thay thiết kế**.

Reset thích hợp để **giảm tác động tạm thời** cho legacy code hoặc shared fixtures đã kiểm soát. Không nên xem reset là giải pháp tổng quát tốt hơn dependency injection.

## 9. Ví dụ chạy: reset làm test tuần tự độc lập hơn

Tạo file **`StaticResetDemo.java`**:

~~~java
public class StaticResetDemo {
    static final class FeatureFlags {
        private static boolean newCheckout;

        static void enableNewCheckout() {
            newCheckout = true;
        }

        static boolean isNewCheckoutEnabled() {
            return newCheckout;
        }

        static void reset() {
            newCheckout = false;
        }
    }

    static void testDefault() {
        FeatureFlags.reset();
        System.out.println("default=" +
                FeatureFlags.isNewCheckoutEnabled());
    }

    static void testEnabled() {
        FeatureFlags.reset();
        FeatureFlags.enableNewCheckout();
        System.out.println("enabled=" +
                FeatureFlags.isNewCheckoutEnabled());
    }

    public static void main(String[] args) {
        testEnabled();
        testDefault();
        testDefault();
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticResetDemo.java
java StaticResetDemo
~~~

Stdout:

~~~text
enabled=true
default=false
default=false
~~~

Mỗi test method chủ động đưa field về trạng thái ban đầu. Trong **thực thi tuần tự của demo**, kết quả ổn định.

### Vì sao reset ở đầu và cleanup ở cuối đều có vai trò?

- Reset ở đầu test đặt **precondition** rõ, kể cả test trước từng để lại state.
- Cleanup ở cuối test giảm tác động sang các phần khác, nhất là tài nguyên cần close.
- Nếu cleanup cần luôn chạy ngay cả khi có exception, dùng `try/finally` hoặc lifecycle hooks của test framework.
- Đối với state shared giữa tests chạy song song, **cả reset ở đầu lẫn cleanup ở cuối vẫn có thể race**.

Tại sao không chỉ gọi reset một lần trong `@BeforeAll`? Vì những test tiếp theo vẫn có thể sửa shared state. Một lần reset đầu class **không tạo isolation giữa các test methods**.

## 10. JUnit 5: sử dụng lifecycle hooks có chủ đích

Với JUnit Jupiter, `@BeforeEach` thường được dùng để chuẩn bị fixture trước từng test method, còn `@AfterEach` để cleanup sau mỗi test method.

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DiscountTest {
    @BeforeEach
    void setUp() {
        Discount.resetForTests();
    }

    @AfterEach
    void tearDown() {
        Discount.resetForTests();
    }

    @Test
    void noDiscount() {
        assertEquals(100, Discount.finalPrice(100));
    }

    @Test
    void twentyPercent() {
        Discount.configure(20);
        assertEquals(80, Discount.finalPrice(100));
    }
}
~~~

**Đây là mã minh họa JUnit 5**, cần khai báo dependency `org.junit.jupiter:junit-jupiter` phù hợp và test runner được cấu hình; không phải một chương trình chỉ cần `javac` của JDK thuần. Hãy sử dụng hệ thống build Maven/Gradle và cấu hình JUnit version của dự án.

Các hook trên giúp kiểm soát trạng thái khi test được thực thi **tuần tự và không bị thành phần khác sửa cùng static field trong lúc test chạy**. Chúng không bảo đảm thread safety hoặc cross-class isolation khi các test khác chạy song song trên cùng state.

### Cẩn thận với `@TestInstance`

JUnit có thể tạo test class instance riêng cho mỗi test method theo lifecycle mặc định, nhưng điều đó **không tạo bản copy riêng của static fields trong class production**. Đổi lifecycle của test instance không xóa global static state.

**Đừng lẫn:** reset **test object instance** và reset **class-level production state** là hai việc khác nhau.

## 11. Khắc phục cách 2: chuyển dữ liệu từ static sang instance

Nếu một giá trị vốn thuộc về một **bài test, một session, một customer hoặc một object**, biến nó thành instance field thường giải quyết triệt để hơn reset global.

Thay vì:

~~~java
class SharedCart {
    static int itemCount;
}
~~~

hãy cân nhắc:

~~~java
class Cart {
    private int itemCount;

    void addOne() {
        itemCount++;
    }

    int itemCount() {
        return itemCount;
    }
}
~~~

Mỗi `new Cart()` tạo instance state mới. Tests có thể tạo Cart riêng mà không reset trạng thái global.

### Chương trình chạy kiểm chứng isolation

Tạo file **`InstanceIsolationDemo.java`**:

~~~java
public class InstanceIsolationDemo {
    static final class Cart {
        private int itemCount;

        void addOne() {
            itemCount++;
        }

        int itemCount() {
            return itemCount;
        }
    }

    static void scenarioA() {
        Cart cart = new Cart();
        cart.addOne();
        cart.addOne();
        System.out.println("scenarioA=" + cart.itemCount());
    }

    static void scenarioB() {
        Cart cart = new Cart();
        System.out.println("scenarioB=" + cart.itemCount());
    }

    public static void main(String[] args) {
        scenarioA();
        scenarioB();
        scenarioA();
        scenarioB();
    }
}
~~~

~~~bash
javac -encoding UTF-8 InstanceIsolationDemo.java
java InstanceIsolationDemo
~~~

Stdout:

~~~text
scenarioA=2
scenarioB=0
scenarioA=2
scenarioB=0
~~~

Mỗi scenario sở hữu một Cart object mới. Không có static mutable counter nào trong Cart; do đó các lần chạy độc lập về state nội bộ của Cart.

**Giới hạn:** Nếu các Cart instances cùng nhận reference đến một mutable service/cache/database, tests vẫn có thể chia sẻ trạng thái qua dependency ấy. Instance field giúp **thu hẹp scope chia sẻ**, không tự bảo đảm mọi dependency đều cô lập.

## 12. Khắc phục cách 3: dependency injection với state có scope

Trong một ứng dụng thật, nhiều object có thể **cần dùng chung dữ liệu**, nhưng việc chia sẻ không nhất thiết phải thông qua static field toàn cục.

Ví dụ, một service cập nhật thống kê:

~~~java
interface Counter {
    void increment();
    int value();
}

final class InMemoryCounter implements Counter {
    private int count;

    @Override
    public void increment() {
        count++;
    }

    @Override
    public int value() {
        return count;
    }
}

final class EventService {
    private final Counter counter;

    EventService(Counter counter) {
        this.counter = java.util.Objects.requireNonNull(counter);
    }

    void processEvent() {
        counter.increment();
    }

    int processedEvents() {
        return counter.value();
    }
}
~~~

Các class trên là mã minh họa, không chứa `main`. Mỗi `EventService` nhận **một Counter dependency**:

- Hai services dùng **cùng một Counter object** sẽ chia sẻ số đếm.
- Hai services dùng **hai Counter objects** riêng sẽ độc lập.
- Trong test, tạo Counter mới cho mỗi test; không cần sửa static production state.
- Scope chia sẻ do **nơi tạo/wire dependencies quyết định** thay vì bị hard-code trong class qua static.

Đây là bản chất hữu ích của dependency injection: kiểm soát **ownership và lifecycle** của dependency.

### Không cần framework mới dùng được DI

Có thể dùng constructor trực tiếp:

~~~java
Counter counter = new InMemoryCounter();
EventService service = new EventService(counter);
~~~

Spring, CDI hoặc framework khác có thể quản lý object graphs trong dự án lớn, nhưng **dependency injection là một nguyên tắc thiết kế**, không bắt buộc dùng framework.

## 13. Ví dụ chạy: test được tạo dependency mới

Tạo file **`DependencyIsolationDemo.java`**:

~~~java
public class DependencyIsolationDemo {
    interface Counter {
        void add(int amount);
        int value();
    }

    static final class InMemoryCounter implements Counter {
        private int value;

        @Override
        public void add(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            value += amount;
        }

        @Override
        public int value() {
            return value;
        }
    }

    static final class EventService {
        private final Counter counter;

        EventService(Counter counter) {
            this.counter = java.util.Objects.requireNonNull(counter);
        }

        void onEvent() {
            counter.add(1);
        }

        int total() {
            return counter.value();
        }
    }

    static void scenarioA() {
        EventService service = new EventService(new InMemoryCounter());
        service.onEvent();
        service.onEvent();
        System.out.println("A=" + service.total());
    }

    static void scenarioB() {
        EventService service = new EventService(new InMemoryCounter());
        System.out.println("B=" + service.total());
    }

    public static void main(String[] args) {
        scenarioB();
        scenarioA();
        scenarioA();
        scenarioB();
    }
}
~~~

~~~bash
javac -encoding UTF-8 DependencyIsolationDemo.java
java DependencyIsolationDemo
~~~

Stdout:

~~~text
B=0
A=2
A=2
B=0
~~~

Mỗi test-like scenario tạo một `InMemoryCounter` riêng. Không phụ thuộc vào thứ tự chạy và không cần bất kỳ phương thức `resetStaticState()` nào.

Đây là state instance và **không tự thread-safe** nếu nhiều threads cùng chia sẻ một Counter. Muốn hỗ trợ concurrent updates, có thể thay implementation bằng một atomic/synchronized Counter **mà không đổi API EventService**. Đó là lợi ích thêm của việc tách interface và cách lưu state.

## 14. Khắc phục cách 4: pure functions và immutable input

Nếu logic không cần nhớ state giữa các lời gọi, có thể dùng một hàm thuần:

~~~java
static long discountedPrice(long base, int percent) {
    if (base < 0 || percent < 0 || percent > 100) {
        throw new IllegalArgumentException("invalid input");
    }
    return base - Math.multiplyExact(base, percent) / 100;
}
~~~

Method được **truyền rõ toàn bộ input**, không đọc static mutable `Discount.percent`. Cùng `base` và `percent` hợp lệ sẽ cho cùng kết quả, độc lập test order và các lời gọi trước.

Lưu ý:

- `Math.multiplyExact` có thể ném `ArithmeticException` nếu tích tràn; cách làm tròn ở đây dùng phép chia số nguyên.
- Chính sách làm tròn/thuế/tiền tệ thực tế có thể khác; ví dụ nhằm minh họa sự **không phụ thuộc shared mutable field**.

Một static method **có thể pure và dễ test**, vì thế không cần biến mọi method thành instance method chỉ để tránh từ khóa `static`.

### So sánh hai API

| API | Đầu vào phụ thuộc gì? | Dễ test độc lập? |
| --- | --- | --- |
| `Discount.finalPrice(100)` đọc static `percent` | Hidden class-level state | Kém nếu field mutable |
| `discountedPrice(100, 20)` | `base` và `percent` tường minh | Tốt hơn |
| `calculator.finalPrice(100)` với immutable calculator config | Constructor-injected instance config | Tốt khi nhiều lời gọi cùng chính sách |
| `service.finalPrice(100)` dùng DB/request/clock | External dependencies | Cần fake/fixture các dependencies |

“Pure” cần nghĩa nghiêm túc: method không có side effect quan sát được và không phụ thuộc mutable external state. Một method static đọc `System.currentTimeMillis()` không pure chỉ vì không nhận parameter.

## 15. Ví dụ chạy: cấu hình bất biến được truyền qua constructor

Tạo file **`ImmutablePricingPolicyDemo.java`**:

~~~java
public class ImmutablePricingPolicyDemo {
    record PricingPolicy(int discountPercent) {
        PricingPolicy {
            if (discountPercent < 0 || discountPercent > 100) {
                throw new IllegalArgumentException("invalid discount");
            }
        }
    }

    static final class PriceCalculator {
        private final PricingPolicy policy;

        PriceCalculator(PricingPolicy policy) {
            this.policy = java.util.Objects.requireNonNull(policy);
        }

        int finalPrice(int base) {
            if (base < 0) {
                throw new IllegalArgumentException("negative price");
            }
            return base - base * policy.discountPercent() / 100;
        }
    }

    public static void main(String[] args) {
        PriceCalculator normal = new PriceCalculator(new PricingPolicy(0));
        PriceCalculator sale = new PriceCalculator(new PricingPolicy(20));

        System.out.println("normal=" + normal.finalPrice(100));
        System.out.println("sale=" + sale.finalPrice(100));
        System.out.println("normal again=" + normal.finalPrice(100));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ImmutablePricingPolicyDemo.java
java ImmutablePricingPolicyDemo
~~~

Stdout:

~~~text
normal=100
sale=80
normal again=100
~~~

Hai calculators giữ hai `PricingPolicy` instances riêng có dữ liệu bất biến. Chúng không cần ghi `static Discount.percent` trước mỗi lần tính, nên kết quả calculator A không bị calculator B làm đổi.

Ví dụ dùng `int` nhỏ để output đơn giản; với giá lớn hoặc yêu cầu tính tiền, phải xử lý overflow, đơn vị tiền và rounding policies phù hợp.

## 16. Giải pháp nào cho rủi ro nào?

| Biện pháp | Cô lập test theo thứ tự | Thread-safety | Phạm vi áp dụng |
| --- | --- | --- | --- |
| Reset static field trước test | Có thể, nếu tests chạy tuần tự và reset đủ | Không | Legacy fixtures |
| Reset sau test bằng `finally`/`@AfterEach` | Giảm state leak nếu cleanup chạy đúng | Không | Temporary global modifications |
| Mỗi test có object instance mới | Tốt với state của object riêng | Không tự bảo đảm | Domain/service local state |
| Constructor DI dependency mới mỗi test | Tốt nếu dependencies thật sự tách biệt | Không tự bảo đảm | Services, repositories, clocks |
| Immutable object/configuration | Giảm mutable state | Thường thuận lợi cho sharing | Value objects, policies |
| Pure function nhận arguments | Tốt nếu không có external hidden state | Thuận lợi vì không shared mutation | Calculation/validation |
| `AtomicInteger` static | Không: giá trị vẫn chia sẻ | Atomic cho một số phép phù hợp | Concurrent counters |
| `synchronized` trên static method | Không: tests vẫn dùng chung field | Có thể bảo vệ critical section | Shared operations |
| `ThreadLocal` | Không bảo đảm per-test isolation | Tách theo thread, có lifecycle risks | Một số per-thread contexts |
| Tách JVM process | Tốt cho static state giữa processes | Không giải quyết race trong một process | Integration suites/tooling |
| Tách class loader | Có thể tạo class runtime riêng trong điều kiện phù hợp | Không tự bảo đảm | Specialized plugin/test runtimes |

Hãy chọn giải pháp theo **nguồn phụ thuộc**, không chỉ theo tên công cụ. Thay `int count` bằng `AtomicInteger` sửa một số race conditions nhưng **không xử lý test B đọc state test A để lại**.

## 17. Parallel tests: reset không còn đủ

Hai test chạy đồng thời:

~~~text
Thread/Test A                       Thread/Test B
--------------------------------    --------------------------------
reset Discount.percent = 0
set Discount.percent = 20
                                    reset Discount.percent = 0
assert price == 80  -> FAIL!
                                    assert price == 100 -> PASS
~~~

Ngay cả nếu mỗi test **đều reset ở đầu**, chúng vẫn cùng ghi một static field. Bất kỳ thứ tự xen kẽ nào cũng có thể xuất hiện dưới concurrency. Test có thể PASS/FAIL không ổn định theo timing.

### Các phương án đúng hướng

1. **Loại bỏ shared mutable state**: truyền policy theo constructor/parameter.
2. Nếu các tests buộc phải sửa một global resource, **không chạy song song những tests đó** bằng cơ chế resource locks/isolation phù hợp của test runner.
3. Tách các test sang process riêng khi bài integration yêu cầu và chi phí cho phép.
4. Với production shared state bắt buộc, dùng synchronization/atomic/concurrent data structures và test các invariant trong concurrency, nhưng vẫn cần isolation giữa test scenarios.
5. Dùng fixture scoped thay global khi có thể; bảo đảm mọi test class cùng tuân thủ lifecycle.

Không nên chỉ thêm `Thread.sleep(100)` để mong test bớt race. Sleep làm timing đổi, không thiết lập một invariant hay happens-before cần thiết.

## 18. Rủi ro race condition trên static counter

Code:

~~~java
class Counter {
    static int hits;

    static void hit() {
        hits++;
    }
}
~~~

`hits++` là read–modify–write, không phải một phép atomic có bảo đảm cho nhiều threads. Nếu hai threads cùng đọc giá trị cũ 10, cùng tính 11 rồi cùng ghi 11, một lần tăng bị mất.

### `volatile` có xử lý được không?

~~~java
static volatile int hits;
~~~

`volatile` hỗ trợ visibility và ordering theo Java Memory Model, nhưng **không biến `hits++` thành atomic**. Vì thế một volatile int vẫn có thể bị lost update.

### Dùng `AtomicInteger` đúng phạm vi

~~~java
private static final java.util.concurrent.atomic.AtomicInteger HITS =
        new java.util.concurrent.atomic.AtomicInteger();

static void hit() {
    HITS.incrementAndGet();
}
~~~

Từng phép `incrementAndGet()` có bảo đảm atomic theo API. Nhưng `HITS` vẫn là một object static **dùng chung giữa tests**. Nếu test A tăng một lần, test B có thể quan sát giá trị ấy trừ khi tests được cô lập hoặc đối tượng state được reset/quản lý rõ.

## 19. Ví dụ chạy: atomicity không đồng nghĩa test isolation

Tạo file **`AtomicButSharedDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicButSharedDemo {
    static final class Metrics {
        private static final AtomicInteger EVENTS = new AtomicInteger();

        static void addEvent() {
            EVENTS.incrementAndGet();
        }

        static int count() {
            return EVENTS.get();
        }

        static void clearForDemo() {
            EVENTS.set(0);
        }
    }

    static void runParallelWork() throws InterruptedException {
        Thread a = new Thread(() -> {
            for (int i = 0; i < 1_000; i++) {
                Metrics.addEvent();
            }
        });

        Thread b = new Thread(() -> {
            for (int i = 0; i < 1_000; i++) {
                Metrics.addEvent();
            }
        });

        a.start();
        b.start();
        a.join();
        b.join();
    }

    public static void main(String[] args)
            throws InterruptedException {
        Metrics.clearForDemo();
        runParallelWork();
        System.out.println("after parallel=" + Metrics.count());

        Metrics.addEvent();
        System.out.println("next scenario=" + Metrics.count());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AtomicButSharedDemo.java
java AtomicButSharedDemo
~~~

Stdout:

~~~text
after parallel=2000
next scenario=2001
~~~

`AtomicInteger` giúp hai threads cập nhật chính xác số lần gọi. `Thread.join()` bảo đảm main chờ threads hoàn tất trước khi đọc. Nhưng `next scenario` vẫn bắt đầu từ giá trị **đã có** sau scenario trước, nên là 2001 thay vì 1.

Nếu bạn muốn mỗi scenario tự có counter, hãy sử dụng **Counter instance được truyền vào** hoặc một dependency có lifecycle rõ. Atomic chỉ giải quyết vấn đề **cập nhật đồng thời**, không sửa vấn đề **tồn dư trạng thái**.

## 20. Không chỉ static primitives: mutable collection dùng chung

Ví dụ:

~~~java
class EventBus {
    static final java.util.List<String> EVENTS =
            new java.util.ArrayList<>();
}
~~~

Các tests có thể thêm:

~~~java
EventBus.EVENTS.add("ORDER_CREATED");
~~~

Sau đó test khác có thể thấy event tồn dư dù chưa gọi add.

Hơn nữa `ArrayList` không đảm bảo safe concurrent mutation. Nếu nhiều threads đồng thời gọi `add`, có thể xảy ra lost updates hoặc vấn đề khác tùy lịch thực thi.

### Nếu thật sự cần một registry cấp class

Nên cân nhắc:

- Ẩn field bằng `private`.
- Public methods kiểm soát `add`, `remove` và invariant.
- Chọn synchronization/concurrent collection phù hợp.
- Không trả một mutable internal reference trực tiếp.
- Có chiến lược lifecycle/clear/eviction.
- Đặt giới hạn dung lượng hoặc time-to-live khi dữ liệu kéo dài.
- Có cách tạo một registry **riêng cho test** thay vì buộc dùng global mặc định.

Một static registry cho sản phẩm không tự trở thành kiến trúc event bus đáng tin cậy; còn có yêu cầu ordering, durability, error handling, asynchronous delivery và thread safety.

## 21. Ví dụ chạy: snapshot an toàn hơn trả raw List

Tạo file **`StaticRegistrySnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class StaticRegistrySnapshotDemo {
    static final class Registry {
        private static final List<String> EVENTS = new ArrayList<>();

        static synchronized void record(String event) {
            if (event == null || event.isBlank()) {
                throw new IllegalArgumentException("event required");
            }
            EVENTS.add(event);
        }

        static synchronized List<String> snapshot() {
            return List.copyOf(EVENTS);
        }

        static synchronized void resetForDemo() {
            EVENTS.clear();
        }
    }

    public static void main(String[] args) {
        Registry.resetForDemo();
        Registry.record("A");
        Registry.record("B");

        List<String> view = Registry.snapshot();
        System.out.println("snapshot=" + view);

        Registry.record("C");
        System.out.println("old snapshot=" + view);
        System.out.println("new snapshot=" + Registry.snapshot());

        try {
            view.add("D");
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot immutable structure");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticRegistrySnapshotDemo.java
java StaticRegistrySnapshotDemo
~~~

Stdout:

~~~text
snapshot=[A, B]
old snapshot=[A, B]
new snapshot=[A, B, C]
snapshot immutable structure
~~~

Ở đây các method `record`, `snapshot` và `resetForDemo` đều `static synchronized`, nên cùng dùng monitor của class `Registry` trong những lần gọi method đó. `List.copyOf` tạo/nhận danh sách không cho thay đổi cấu trúc qua API thông thường; old snapshot không thay đổi sau `record("C")`.

Nhưng **test isolation vẫn phải được xử lý**: static `EVENTS` vẫn có nội dung từ các lần record trước. `synchronized` kiểm soát tính nhất quán giữa các method đồng bộ của Registry, không tự xóa state giữa tests. Khi nội dung list là mutable elements, một snapshot cấu trúc cũng không tự deep copy phần tử.

## 22. Static cache dễ khiến test dùng dữ liệu cũ

Một cache dùng chung:

~~~java
static final java.util.Map<String, Customer> CACHE =
        new java.util.HashMap<>();
~~~

có thể giữ Customer từ test trước. Nếu test B tạo Customer cùng ID với dữ liệu khác nhưng production code lại ưu tiên cache, test B đọc dữ liệu cũ và thất bại.

Trong production cũng có các rủi ro:

- Thiếu cache invalidation khi dữ liệu nguồn thay đổi.
- Dữ liệu user/tenant bị trộn nếu cache key không chứa scope.
- Cache tăng vô hạn, gây memory retention.
- Races giữa threads nếu `HashMap` bị sửa đồng thời mà không đồng bộ.
- Cache là global nên khó thay/fake trong test.
- Test suite có thể phụ thuộc thời điểm cache được warm.

### Cache không phải luôn xấu

Một cache với hợp đồng rõ, bounded size, eviction, concurrency control và owner/lifecycle phù hợp có thể cải thiện hiệu năng. Cần test cả **hit, miss, invalidation, stale data** và isolation. Câu hỏi quan trọng: cache có thật sự cần **global static scope** hay chỉ nên thuộc một service/repository instance?

## 23. Static clock làm test phụ thuộc thời gian

Ví dụ khó test:

~~~java
class DeadlineService {
    static boolean isLate(java.time.Instant deadline) {
        return java.time.Instant.now().isAfter(deadline);
    }
}
~~~

Phương thức không đọc static mutable field riêng, nhưng gọi **thời gian hệ thống**. Kết quả có thể thay đổi theo lúc test chạy. Một test có deadline sát thời điểm hiện tại có thể PASS/FAIL vì timing.

Thay vì dùng clock cứng, inject `java.time.Clock`. Ví dụ:

~~~java
final class DeadlineService {
    private final java.time.Clock clock;

    DeadlineService(java.time.Clock clock) {
        this.clock = java.util.Objects.requireNonNull(clock);
    }

    boolean isLate(java.time.Instant deadline) {
        return java.time.Instant.now(clock).isAfter(deadline);
    }
}
~~~

Bây giờ test kiểm soát thời gian bằng `Clock.fixed(...)`. Cách này không nhất thiết phải có mutable static state để test, giúp giảm nguyên nhân bất ổn.

## 24. Ví dụ chạy: Clock được inject nên test có kết quả xác định

Tạo file **`InjectedClockDemo.java`**:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

public class InjectedClockDemo {
    static final class DeadlineService {
        private final Clock clock;

        DeadlineService(Clock clock) {
            this.clock = clock;
        }

        boolean isLate(Instant deadline) {
            return Instant.now(clock).isAfter(deadline);
        }
    }

    public static void main(String[] args) {
        Instant deadline = Instant.parse("2026-01-01T12:00:00Z");

        DeadlineService before = new DeadlineService(
                Clock.fixed(
                        Instant.parse("2026-01-01T11:00:00Z"),
                        ZoneOffset.UTC));

        DeadlineService after = new DeadlineService(
                Clock.fixed(
                        Instant.parse("2026-01-01T13:00:00Z"),
                        ZoneOffset.UTC));

        System.out.println("before late=" + before.isLate(deadline));
        System.out.println("after late=" + after.isLate(deadline));
    }
}
~~~

~~~bash
javac -encoding UTF-8 InjectedClockDemo.java
java InjectedClockDemo
~~~

Stdout:

~~~text
before late=false
after late=true
~~~

Không phụ thuộc ngày/giờ thật lúc chạy chương trình. Hai `DeadlineService` objects sở hữu clock dependencies riêng và có thể cho kết quả khác nhau theo yêu cầu test.

### Một bẫy tương tự: static random generator

Nếu nhiều tests dùng chung một mutable `Random` object, thứ tự lời gọi ảnh hưởng số ngẫu nhiên tiếp theo. Đặt seed chung ở `@BeforeAll` không đảm bảo các test độc lập khi chúng dùng chung generator. Có thể:

- Inject generator theo instance.
- Tạo generator riêng với seed xác định cho mỗi test.
- Mock/fake các kết quả ở boundary phù hợp.
- Kiểm tra tính chất thay vì hardcode toàn bộ chuỗi ngẫu nhiên khi mục tiêu test không phụ thuộc sequence cụ thể.

Trong production bảo mật, không nhầm deterministic `java.util.Random` với `SecureRandom` phù hợp yêu cầu mật mã.

## 25. Static mutable configuration và test đổi system properties

Không chỉ field của class tự viết mới là global mutable state. Một số môi trường có shared process-level configuration như:

~~~java
System.setProperty("feature.mode", "new");
~~~

Một test khác gọi `System.getProperty("feature.mode")` có thể quan sát giá trị còn sót.

Nếu test cần thay đổi system property:

1. Ghi nhận chính xác **giá trị cũ và việc property có tồn tại không**.
2. Sửa trong phạm vi kiểm soát.
3. Khôi phục trong `finally`/cleanup.
4. Không cho các tests khác chạy song song dựa trên cùng property, trừ khi có isolation/lock thích hợp.
5. Tốt hơn, truyền configuration dưới dạng argument/dependency nếu API cho phép.

Không dùng `System.clearProperty("feature.mode")` vô điều kiện ở cuối test nếu trước test property đã có một giá trị hữu ích của môi trường. **Restore original state**, không mặc định xóa.

## 26. Ví dụ chạy: khôi phục process-level property bằng `finally`

Tạo file **`SystemPropertyRestoreDemo.java`**:

~~~java
public class SystemPropertyRestoreDemo {
    public static void main(String[] args) {
        String key = "learning.example.feature";
        String original = System.getProperty(key);

        try {
            System.setProperty(key, "enabled");
            System.out.println("inside=" + System.getProperty(key));
        } finally {
            if (original == null) {
                System.clearProperty(key);
            } else {
                System.setProperty(key, original);
            }
        }

        System.out.println("restored=" +
                java.util.Objects.equals(
                        original, System.getProperty(key)));
    }
}
~~~

~~~bash
javac -encoding UTF-8 SystemPropertyRestoreDemo.java
java SystemPropertyRestoreDemo
~~~

Stdout:

~~~text
inside=enabled
restored=true
~~~

Dù property ban đầu có hay không, code cố gắng khôi phục giá trị cũ. Tuy nhiên `finally` **không loại bỏ race với code khác đồng thời sửa cùng system property**. Restore cần cơ chế cô lập quá trình kiểm thử nếu nhiều tests thao tác trên cùng key.

## 27. Test order, parallelism và các loại isolation

Phân biệt phạm vi để chọn giải pháp:

| Phạm vi | Ví dụ shared state | Cần cô lập thế nào? |
| --- | --- | --- |
| Trong cùng test method | Local variable, object riêng | Tự tạo fixture |
| Giữa test methods cùng class | Static field hoặc `@TestInstance(PER_CLASS)` state | Per-test setup/instance |
| Giữa test classes cùng JVM | Production static cache, system property | Scoped dependencies, cleanup, resource lock |
| Giữa threads cùng JVM | Static mutable counter/list | Atomic/synchronization/ownership |
| Giữa processes | DB, filesystem, network service | Unique test namespace, transactions, cleanup |
| Giữa JVM class loaders | Có thể có static states riêng; resources ngoài vẫn chung | Hiểu loader identity và external dependencies |
| Giữa các builds/runs | DB data còn sót, file, môi trường | Controlled test environments |

**Một test dùng object instance mới không cô lập database**, và **tách JVM không cô lập một database dùng chung**. Không nên dùng nhầm công cụ: hãy truy ngược **shared resource thực sự**.

### Test class mới có làm static reset không?

Không. Tạo một instance mới của test class không làm tạo một bản mới của production static field. Một class runtime thường giữ static state qua các test methods và classes trong cùng môi trường tải class.

## 28. Vì sao `ThreadLocal` không phải lời giải cho mọi static state?

`ThreadLocal<T>` có thể cung cấp giá trị riêng theo thread, dù bản thân biến `ThreadLocal` thường được giữ trong static final field.

~~~java
private static final ThreadLocal<String> USER =
        new ThreadLocal<>();
~~~

Điều này tránh các threads khác nhau trực tiếp dùng chung **một giá trị USER** theo cơ chế ThreadLocal, nhưng có rủi ro:

- Thread pools tái sử dụng worker threads cho các requests khác nhau.
- Nếu quên `remove()` khi kết thúc request/test, request tiếp theo trên **cùng thread** có thể thấy giá trị cũ.
- Không tự truyền context đúng sang async tasks hoặc threads khác.
- Object được giữ bởi thread-local có thể tồn tại lâu cùng thread pool.
- Trong test chạy tuần tự trên cùng thread, state vẫn có thể lây giữa tests.

Đừng thay mọi `static String currentUser` bằng `static ThreadLocal<String> currentUser` rồi kết luận đã giải quyết hoàn toàn context isolation. Phải xác định scope và cleanup rõ.

### Cleanup mẫu

~~~java
USER.set("Mai");
try {
    // Xử lý trong đúng phạm vi của context.
} finally {
    USER.remove();
}
~~~

Đây là mảnh mã minh họa trong ngữ cảnh class có field USER hợp lệ. Nếu bất kỳ code nào dùng asynchronous boundary, cần thiết kế context propagation có chủ đích.

## 29. Singleton và static field vẫn có thể làm test phụ thuộc nhau

Một singleton được giữ bằng static field:

~~~java
class Registry {
    private static final Registry INSTANCE = new Registry();
    private final java.util.List<String> entries =
            new java.util.ArrayList<>();

    static Registry getInstance() {
        return INSTANCE;
    }
}
~~~

Một Registry instance được dùng chung qua `getInstance()`. Mặc dù `entries` là **instance field** (không static), nó vẫn tạo **shared mutable state** vì mọi caller dùng **cùng singleton object**.

Đây là điểm quan trọng:

> Trạng thái dùng chung nguy hiểm không nhất thiết nằm trực tiếp trong một `static mutable field`. Một `static final` reference tới **singleton mutable object** cũng có thể mang tất cả các rủi ro test-order dependence.

Nếu mục tiêu là test isolation, đôi khi phải thay **singleton dependency** bằng instance có thể inject, chứ không chỉ đổi field `entries` từ static sang instance trong cùng singleton.

## 30. Lifecycle của static caches, registries và listeners

Static field có thể giữ object reachable lâu hơn vòng đời nghiệp vụ:

~~~java
class GlobalListeners {
    static final java.util.List<Runnable> LISTENERS =
            new java.util.ArrayList<>();
}
~~~

Mỗi component đăng ký một listener nhưng không gỡ khi kết thúc sẽ để collection static giữ reference đến callback và có thể giữ cả những object mà callback tham chiếu.

Hậu quả có thể gồm:

- Memory retention tăng trong ứng dụng chạy dài.
- Callback của màn hình/request cũ được gọi lại.
- Test mới quan sát callback được tạo từ test cũ.
- Class loader của plugin có thể không được giải phóng vì vẫn được tham chiếu bởi state ngoài plugin.
- Dữ liệu nhạy cảm có thể tồn tại lâu hơn dự kiến trong object graph.

### Thiết kế cleanup có chủ đích

Cân nhắc method đăng ký trả một handle:

~~~java
AutoCloseable subscription = bus.subscribe(listener);
try {
    // Sử dụng subscription.
} finally {
    subscription.close();
}
~~~

Đây là **mã API minh họa**, không giả định sẵn class `bus`. `close()` phải thực sự gỡ listener hoặc đóng resource theo hợp đồng.

Trong test, có thể tạo **một bus instance mới** cho mỗi test thay vì một static registry chung. Cách này giúp quản lý lifecycle bằng scope của test mà không cần `clearAllListeners()` toàn cục.

## 31. Static initialization có thể gây side effects không mong muốn

Một field static được khởi tạo bằng I/O hoặc method có side effect:

~~~java
class Config {
    static final String MODE = loadFromEnvironment();

    static String loadFromEnvironment() {
        return System.getProperty("mode", "default");
    }
}
~~~

`MODE` được tính khi **class được khởi tạo**, không nhất thiết đọc lại property mỗi lần. Nếu test A dùng Config trước rồi test B đổi system property, test B có thể vẫn thấy MODE cũ.

Điều này gây **timing dependence**:

- Test nào chạm class trước?
- Config được khởi tạo dưới bộ environment nào?
- Một test có kỳ vọng static initializer chạy lại không?

Thông thường, **class initialization không chạy lại cho mỗi test method** trên cùng class runtime. Muốn thay config linh hoạt, dùng instance configuration/service có lifecycle rõ; đừng dựa vào việc thay environment để “đánh thức lại” static final initializer.

### Không ép class initialization thất bại

Static initializer ném unchecked exception có thể gây `ExceptionInInitializerError` ở lần khởi tạo đầu; class runtime sau đó có thể ở trạng thái khởi tạo lỗi và gây `NoClassDefFoundError` ở các lần dùng tiếp. Vì vậy test đẩy static initializer vào tình huống lỗi có thể ảnh hưởng nặng đến các tests sau trong cùng runtime. Tách process hoặc thiết kế khởi tạo explicit khi cần kiểm soát failure isolation.

## 32. Tối ưu hoá test bằng cách để static global state là “nơi giả lập” có hại gì?

Một chiến thuật dễ viết:

~~~java
static FakeDatabase database = new FakeDatabase();
~~~

Test A điền dữ liệu, test B dùng lại. Điều này có thể làm test chạy nhanh lúc đầu nhưng:

- Test không còn tự setup những dữ liệu nó cần.
- Bất kỳ test nào chạy trước có thể thay kết quả.
- Khi test A thất bại, cleanup có thể không chạy.
- Test chạy parallel có thể giẫm dữ liệu của nhau.
- Số lượng fixtures tăng làm test khó hiểu.
- Test runner sharding/reordering phá giả định “A luôn chạy trước B”.

Tốt hơn:

~~~java
FakeDatabase database = new FakeDatabase();
Service service = new Service(database);
~~~

Tạo dependency phù hợp cho **từng test** hoặc **từng scenario đã có lifecycle rõ**. Nếu tạo database thật quá đắt, có thể cân nhắc container/process fixture có namespace riêng, database transactions rollback hoặc isolated schemas, không bắt tests phụ thuộc trạng thái lẫn nhau.

## 33. Phương pháp điều tra một flaky test nghi do static state

### Bước 1 — Ghi nhận triệu chứng

Test nào pass riêng nhưng fail khi chạy suite? Có thay đổi theo thứ tự, tốc độ hoặc parallel execution không?

### Bước 2 — Liệt kê shared state

Tìm các field mutable `static`, `static final` tham chiếu mutable collections/singletons, process system properties, environment wrappers, caches, random generators, clocks và global registries. Đồng thời kiểm tra database/files nếu có.

### Bước 3 — Chỉ ra nơi ghi và nơi đọc

Với mỗi state, ghi:

| State | Ai ghi? | Ai đọc? | Scope | Cleanup? |
| --- | --- | --- | --- | --- |
| `Discount.percent` | Test giảm giá | Calculator/test mặc định | JVM class runtime | Chưa |
| `Registry.EVENTS` | Subscriber/test | Assert sự kiện | Static singleton | Có thể thiếu |
| `System.property` | Setup test | Config loader | Process | Có thể thiếu |
| Clock | Runtime | Deadline logic | External clock | Cần inject |

### Bước 4 — Tái hiện tối thiểu

Chạy test thất bại **đơn lẻ**, rồi chạy sau một test nghi vấn trong cùng process. Nếu thay thứ tự làm kết quả đổi, trace các writes vào state chung.

### Bước 5 — Thêm invariant và fixture

Định nghĩa rõ state khởi đầu của test, không dựa vào người chạy trước. Chỉ dùng reset tạm thời khi chưa thể refactor.

### Bước 6 — Chọn sửa code gốc

Ưu tiên truyền dependency/parameter, tạo object riêng, dùng immutable config, hoặc làm rõ lifecycle. Với shared state bắt buộc, bảo vệ concurrency và tạo isolation strategy.

### Bước 7 — Chạy regression

Thử nhiều thứ tự, chạy suite và chạy parallel theo mức project hỗ trợ. Đảm bảo test không gây ảnh hưởng cho test khác và không chỉ đổi từ FAIL sang PASS trong một thứ tự cụ thể.

## 34. Những nhầm lẫn cần tránh

| Nhận định sai | Vì sao sai? | Giải pháp tư duy |
| --- | --- | --- |
| “Static data nằm trong mỗi object.” | Nó thuộc class runtime. | Vẽ class-level state riêng. |
| “`static final List` là immutable.” | Reference final, List vẫn mutable. | Phân biệt final với deep immutability. |
| “`private static` không bị test khác sửa.” | Public method vẫn có thể sửa field. | Xem mọi đường cập nhật. |
| “Đặt reset vào `@BeforeAll` là đủ.” | Các test methods sau vẫn ghi chung state. | Per-test isolation. |
| “`@BeforeEach` giúp test chạy song song an toàn.” | Hai resets có thể xen kẽ. | Tránh chung mutable state hoặc lock/isolate. |
| “Dùng `AtomicInteger` thì test không lây.” | Atomic chỉ giải quyết cập nhật đồng thời. | Tách instance/scope. |
| “`volatile++` atomic.” | `++` vẫn read–modify–write. | Dùng atomic operation/lock. |
| “Synchronized là tương đương reset.” | Lock không đưa state về ban đầu. | Isolation là bài toán khác. |
| “Cứ test method instance mới thì production static mới.” | Static thuộc production class runtime. | Hiểu test lifecycle vs class lifecycle. |
| “JVM mới sẽ reset cả database.” | DB và external resources không thuộc JVM state. | Dọn/namespace external state. |
| “System property thay đổi làm static final Config chạy lại.” | Static initialization thường một lần per runtime class. | Inject config rõ ràng. |
| “Singleton không có static mutable field thì sạch.” | Singleton object vẫn có mutable instance fields. | Xem object graph. |
| “ThreadLocal là mỗi request có object mới.” | Thread pool tái sử dụng thread. | Cleanup và context propagation. |
| “Một class cùng tên chỉ có một static state toàn JVM.” | Class loaders có thể định nghĩa nhiều runtime classes. | Xét class identity. |
| “Test chỉ lỗi trên CI nên CI sai.” | Thứ tự, timezone, CPU, parallelism có thể lộ hidden dependency. | Tái hiện và trace shared state. |
| “Thêm `Thread.sleep` là sửa flaky test.” | Timing không tạo synchronization đúng. | Sửa invariant/coordination. |
| “Cache static luôn tốt vì tái sử dụng object.” | Có stale data, memory retention, hidden coupling. | Quản lý scope/lifecycle/eviction. |
| “Không dùng static method trong code cần test.” | Static pure methods vẫn dễ test. | Tránh shared mutation, không cấm cú pháp. |

## 35. Bài tập 1 — Tìm test bị phụ thuộc

Cho:

~~~java
class Flags {
    static boolean enabled;
}

static void testA() {
    Flags.enabled = true;
}

static void testB() {
    if (Flags.enabled) {
        throw new AssertionError("expected disabled");
    }
}
~~~

**Câu hỏi:** `testB` chạy một mình có thể pass; vì sao chạy sau `testA` có thể fail?

**Đáp án:** `Flags.enabled` là static mutable field. `testA` đặt giá trị true và không reset, nên `testB` đọc true khi cùng class runtime. Đề xuất: đưa flags vào một instance configuration riêng cho mỗi scenario, hoặc reset ở boundary nếu legacy tests được chạy tuần tự.

Đây là **mảnh mã minh họa**, cần đặt static methods trong class hợp lệ.

## 36. Bài tập 2 — `static final` có thật là constant không?

~~~java
class Store {
    static final java.util.List<String> ITEMS =
            new java.util.ArrayList<>();
}
~~~

Một test thực hiện `Store.ITEMS.add("A")`. Test khác gọi `Store.ITEMS.size()`.

**Đáp án:** Có thể đọc 1 dù field có `final`. `final` chỉ ngăn `ITEMS` được gán lại reference, không ngăn ArrayList mutation. Có thể chuyển state vào Store instance được inject, hoặc API snapshot có lifecycle/isolation rõ.

## 37. Bài tập 3 — Atomic có giải quyết hết không?

~~~java
class Metrics {
    static final java.util.concurrent.atomic.AtomicInteger HITS =
            new java.util.concurrent.atomic.AtomicInteger();
}
~~~

Hai tests tuần tự, test A tăng 10, test B tăng 1 và assert `HITS.get() == 1`.

**Đáp án:** Test B có thể thấy 11. `AtomicInteger` đảm bảo update atomic, không tự reset giữa tests. Nếu muốn đếm trong từng scenario, dùng Metrics instance riêng (có thể sở hữu AtomicInteger riêng), không dùng static global.

## 38. Bài tập 4 — Đổi API để không phụ thuộc static discount

Ban đầu:

~~~java
class Pricing {
    static int discountPercent;

    static int calculate(int amount) {
        return amount - amount * discountPercent / 100;
    }
}
~~~

Hãy chọn một trong hai thiết kế:

**A. Pure function**: `calculate(int amount, int discountPercent)` với validation.

**B. Instance calculator**: `new PriceCalculator(new PricingPolicy(20))` và `finalPrice(amount)`.

Yêu cầu kiểm thử:

- Giá 100, giảm 0% → 100.
- Giá 100, giảm 20% → 80.
- Đổi chính sách calculator thứ hai không làm calculator thứ nhất đổi kết quả.
- Dữ liệu input âm hoặc percent ngoài `0..100` bị từ chối theo contract.

## 39. Bài tập 5 — Tìm cleanup bị thiếu

Một test chạy:

~~~java
System.setProperty("mode", "new");
assertSomething();
~~~

Nếu assert ném exception, câu lệnh cleanup đặt **sau** assert có thể không chạy. Hãy lưu giá trị cũ, dùng `try/finally` khôi phục property bất kể assertion thành công hay thất bại. Giải thích vì sao biện pháp này vẫn không đủ nếu tests khác chạy song song và cùng key.

## 40. Bài tập 6 — Lựa chọn static state trong thiết kế

Quyết định static/instance/injected state cho các tình huống:

| Tình huống | Hướng ưu tiên |
| --- | --- |
| Một hằng số bất biến `MAX_RETRIES` | `public static final` nếu là API constant phù hợp |
| Số sản phẩm trong một Cart | Instance field của Cart |
| Counter riêng của mỗi test scenario | Counter object riêng |
| Counter metrics cấp tiến trình, đa luồng | Shared service/counter với atomic hoặc lock và lifecycle rõ |
| Tên user của mỗi request | Request-scoped context/dependency, không static global |
| Cache có key theo tenant và expiration | Cache service được quản lý, key và lifecycle đúng |
| Time source để kiểm thử deadline | Inject `Clock` |
| Lookup table bất biến chung | Static immutable collection nếu phù hợp |
| Event listeners theo màn hình/test | Event bus instance hoặc managed registry với cleanup |
| Global singleton session mutable | Thường cần thiết kế lại scope và ownership |

## 41. Checklist tự đánh giá

- [ ] Tôi biết static field gắn với class runtime, không tự tạo lại theo mỗi instance.
- [ ] Tôi phân biệt static constant với static mutable field và static final mutable reference.
- [ ] Tôi hiểu hidden coupling qua global state.
- [ ] Tôi có thể tái hiện test order dependence trong `StaticTestOrderDemo`.
- [ ] Tôi biết vì sao test pass riêng có thể fail trong suite.
- [ ] Tôi biết reset đầu/cuối test chỉ là một biện pháp có điều kiện.
- [ ] Tôi không nghĩ `@BeforeEach` tự cho phép parallel tests an toàn với cùng static field.
- [ ] Tôi biết test object instance lifecycle không quyết định production static state lifecycle.
- [ ] Tôi biết `AtomicInteger` xử lý atomic update nhưng không tạo test isolation.
- [ ] Tôi biết `volatile` không làm `++` atomic.
- [ ] Tôi biết static mutable List/Map/cache vẫn có rủi ro race và state leakage.
- [ ] Tôi hiểu singleton instance có thể chứa shared mutable instance fields.
- [ ] Tôi biết lựa chọn instance-owned state hoặc constructor DI để dễ tách tests.
- [ ] Tôi biết dùng pure function hoặc immutable policy khi phù hợp.
- [ ] Tôi biết inject `Clock` để tránh phụ thuộc thời gian thật trong test.
- [ ] Tôi biết giữ và khôi phục system properties đúng trong `finally`.
- [ ] Tôi biết giới hạn của `ThreadLocal` trong thread pools.
- [ ] Tôi có thể giải thích memory retention do static references.
- [ ] Tôi biết class loaders có thể tạo static states riêng cho class cùng tên.
- [ ] Tôi có thể xác định nơi ghi, nơi đọc, scope và cleanup của shared resource.
- [ ] Tôi biết test lại nhiều thứ tự và parallel mode để kiểm chứng giải pháp.
- [ ] Tôi phân biệt lỗi test-order dependence với các lỗi ngoại cảnh như DB/network/clock.
- [ ] Tôi chạy được các ví dụ Java 17+ và giải thích stdout từng ví dụ.

**Kết luận:** `static` không xấu và static pure methods/constants vẫn hữu ích. Rủi ro lớn nằm ở **static state có thể thay đổi mà nhiều thành phần hoặc nhiều bài test cùng dùng**, khiến việc kiểm thử lệ thuộc vào thứ tự thực thi, thời gian và các side effects khó nhìn thấy. Hãy giới hạn mutable state theo đúng owner và lifecycle, ưu tiên dependencies tường minh và fixture riêng, dùng synchronization khi cần concurrency, đồng thời coi reset/cleanup của global state là biện pháp có giới hạn. Một test đáng tin phải **tự thiết lập điều kiện cần, xác minh hành vi và không để lại trạng thái gây ảnh hưởng cho test khác**.
