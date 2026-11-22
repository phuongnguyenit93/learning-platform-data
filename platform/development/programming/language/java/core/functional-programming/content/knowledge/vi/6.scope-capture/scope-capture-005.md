# Truy cập trường đối tượng và trường static từ lambda trong Java

## 1. Mục tiêu

Trong Java, một **lambda expression** có thể dùng dữ liệu được khai báo bên ngoài phần thân của nó. Tuy nhiên, cần phân biệt ba loại dữ liệu:

1. **Biến cục bộ và tham số của phương thức bao ngoài**: chỉ được tham chiếu từ lambda khi chúng là **final** hoặc **effectively final**.
2. **Trường đối tượng (instance field)**: lambda có thể truy cập và cập nhật thông qua đối tượng mà nó thấy, bao gồm **this.field** trong ngữ cảnh instance.
3. **Trường static (class field)**: lambda có thể truy cập và cập nhật qua lớp, ví dụ **TypeName.field**, nếu phạm vi truy cập cho phép.

Quy tắc effectively final áp dụng cho **biến cục bộ được capture**, không cấm lambda thay đổi trường của một đối tượng. Sự khác biệt này rất quan trọng khi viết callback, xử lý sự kiện, Stream, tác vụ nền và code có nhiều luồng.

Sau bài học, bạn có thể giải thích chính xác cách lambda đọc trường instance và static; hiểu **this**, phạm vi tên và thời điểm lambda nhìn thấy giá trị; tránh các nhầm lẫn về tính bất biến, khả năng hiển thị giữa luồng và race condition; kiểm tra hành vi bằng ví dụ Java 17 chạy độc lập.

## 2. Lambda có thể truy cập những gì?

Một lambda được viết trong phạm vi của một lớp hoặc phương thức có thể sử dụng những tên khả dụng theo quy tắc phạm vi và quyền truy cập thông thường của Java. Ví dụ:

~~~java
class Counter {
    private int count;                // Trường instance
    private static int allUpdates;    // Trường static

    void register() {
        int increment = 2;           // Biến cục bộ effectively final

        Runnable action = () -> {
            count += increment;
            allUpdates++;
        };
        action.run();
    }
}
~~~

Đây là đoạn code minh họa cấu trúc, không phải chương trình chạy độc lập có main.

Trong lambda trên:

- **increment** là biến cục bộ. Nó không được gán lại sau lần khởi tạo, nên là effectively final và có thể được lambda capture.
- **count** là trường instance. Vì lambda ở bên trong phương thức instance, tên **count** ở đây ngầm hiểu là **this.count**.
- **allUpdates** là trường static. Nó thuộc về lớp Counter; có thể viết rõ **Counter.allUpdates**.
- Hai lệnh cập nhật chạy **khi action.run() được gọi**, không phải khi biểu thức lambda được tạo.
- Cả **count += increment** lẫn **allUpdates++** đều tạo tác dụng phụ, vì thế lambda này không phải một phép tính thuần.

Chú ý: code trên chạy đúng trong trường hợp đơn luồng minh họa, nhưng các phép cập nhật **+=** và **++** không tự trở thành nguyên tử nếu nhiều luồng thực hiện đồng thời.

## 3. Phân biệt capture biến cục bộ với truy cập trường

### 3.1. Biến cục bộ phải final hoặc effectively final

Java yêu cầu một biến cục bộ được lambda tham chiếu phải là final hoặc **effectively final**. *Effectively final* nghĩa là dù không ghi từ khóa **final**, biến vẫn không bị gán lại sau khi được gán giá trị theo các quy tắc definite assignment.

~~~java
void schedule() {
    int step = 5;
    Runnable task = () -> System.out.println(step);
    task.run();
}
~~~

**step** là effectively final, nên đoạn trên hợp lệ.

Đoạn dưới **không biên dịch**:

~~~java
void invalid() {
    int step = 5;
    Runnable task = () -> System.out.println(step);
    step = 6; // Không còn effectively final.
}
~~~

Nguyên nhân không phải lambda “đã chạy hay chưa”, mà là **biến cục bộ step được tham chiếu trong lambda nhưng bị gán lại** trong phạm vi bao ngoài. Trình biên dịch từ chối ngay cả khi lời gọi **task.run()** không xuất hiện.

Quy tắc tương tự áp dụng cho tham số của phương thức bao ngoài nếu lambda capture tham số đó và đoạn code gán lại tham số.

### 3.2. Final của tham chiếu không làm đối tượng bất biến

~~~java
void register() {
    java.util.List<String> events = new java.util.ArrayList<>();

    Runnable addEvent = () -> events.add("created");
    addEvent.run();

    System.out.println(events); // [created]
}
~~~

Biến cục bộ **events** không được gán sang đối tượng List khác, nên vẫn effectively final. Tuy nhiên, **đối tượng List mà events tham chiếu vẫn mutable**. Lambda có thể gọi phương thức sửa chính đối tượng đó.

Phân biệt:

- **events = new ArrayList<>()** sau khi capture: gán lại biến cục bộ, làm mất effectively final → không biên dịch.
- **events.add(...)**: sửa trạng thái của đối tượng, không gán lại biến events → có thể biên dịch, nhưng phát sinh side effect.

Với nhiều luồng, việc cùng sửa **ArrayList** bằng các lambda khác nhau không tự an toàn; cần ownership hoặc đồng bộ phù hợp.

### 3.3. Trường instance không bị ràng buộc bởi effectively final

~~~java
class Score {
    private int points = 10;

    Runnable bonusTask() {
        return () -> points += 5;
    }
}
~~~

Ở đây **points** là trường instance, không phải biến cục bộ được capture. Java cho phép lambda cập nhật trường đó. Điều cần xem xét là **thời điểm gọi, tính đúng đắn nghiệp vụ và đồng bộ**, không phải điều kiện effectively final.

Một trường được khai báo **final** thì không thể được gán lại sau khi khởi tạo theo quy tắc final của Java. Lambda không vượt qua giới hạn đó. Nhưng **final List<String> history** vẫn có thể bị sửa nội dung nếu List cho phép.

## 4. Lambda truy cập instance field qua this

Trong một **instance method**, lambda có thể tham chiếu trường bằng tên rút gọn hoặc **this.field**:

~~~java
class Account {
    private int balance = 100;

    Runnable depositAction(int amount) {
        return () -> {
            this.balance += amount;
        };
    }
}
~~~

**amount** là tham số của **depositAction**, được capture và phải effectively final. **this.balance** là trường thuộc Account hiện tại. Khi gọi task, trường **balance** lúc ấy mới được đọc và cập nhật.

Nếu sau khi tạo task có thao tác khác đổi balance trước lúc chạy, task sẽ cộng vào **giá trị hiện thời** của trường, không tự lưu snapshot giá trị cũ.

Ví dụ diễn giải:

~~~java
Account account = new Account();
Runnable deposit = account.depositAction(20);
deposit.run();
~~~

Hai đoạn là minh họa phối hợp; nếu muốn đọc balance từ ngoài lớp, cần accessor hoặc kết quả quan sát thích hợp. Sau một lần chạy deposit, balance của account tăng từ 100 lên 120 theo logic của ví dụ.

**this trong lambda** mang ý nghĩa từ vựng (lexical): nó là **this của đối tượng bao quanh nơi lambda được khai báo**. Lambda không tạo ra một đối tượng với **this** riêng để người viết sử dụng theo cách anonymous inner class.

### 4.1. Khác với anonymous inner class

~~~java
class IdentityExample {
    private final String name = "outer";

    Runnable lambda() {
        return () -> System.out.println(this.name);
    }

    Runnable anonymous() {
        return new Runnable() {
            private final String name = "anonymous";

            @Override
            public void run() {
                System.out.println(this.name);
                System.out.println(IdentityExample.this.name);
            }
        };
    }
}
~~~

Nếu gọi **lambda().run()**, dòng in là **outer**. Nếu gọi **anonymous().run()**, nó in **anonymous** rồi **outer**.

Trong lambda, **this** là IdentityExample hiện tại. Trong phương thức **run()** của anonymous class, **this** là chính đối tượng anonymous đó; muốn tham chiếu instance bao ngoài phải viết **IdentityExample.this**.

Đây là khác biệt về phạm vi từ vựng và cách định nghĩa lớp, không nên suy luận rằng lambda luôn được hiện thực bằng một anonymous class. JVM có thể chọn chiến lược hiện thực lambda riêng, và code nghiệp vụ không nên phụ thuộc vào danh tính/kiểu lớp tổng hợp bên dưới.

### 4.2. Tên trường bị che bởi biến cục bộ

~~~java
class ShadowExample {
    int value = 10;

    void print() {
        int value = 3;
        Runnable task = () -> {
            System.out.println(value);
            System.out.println(this.value);
        };
        task.run();
    }
}
~~~

Đầu ra là **3** rồi **10**: tên **value** không có qualifier tìm tới biến cục bộ, còn **this.value** trỏ tới trường instance.

Lambda không tạo một phạm vi khai báo tên hoàn toàn tách khỏi biến cục bộ của phương thức bao ngoài. Bạn **không thể khai báo lại một tham số lambda cùng tên với biến cục bộ đã tồn tại** trong phạm vi bao ngoài của nó. Đặt tên rõ ràng và dùng **this.field** khi việc phân biệt quan trọng.

## 5. Truy cập static field từ lambda

Trường **static** thuộc về lớp, được chia sẻ bởi các instance theo ngữ nghĩa class field. Lambda trong cả **static method** và **instance method** đều có thể truy cập một static field nếu quy tắc visibility cho phép.

~~~java
class Metrics {
    private static int requests = 0;

    static Runnable incrementTask() {
        return () -> Metrics.requests++;
    }
}
~~~

**Metrics.requests** được truy cập khi task chạy. Đoạn code có thể biên dịch nhưng phép tăng **++** không tự đồng bộ. Khi chạy đa luồng, nhiều lần tăng có thể bị mất.

Một static method **không có this** tương ứng với một instance của lớp:

~~~java
class WrongThis {
    int number = 5;

    static Runnable invalid() {
        // Sai trong static context:
        // return () -> System.out.println(this.number);
        return () -> System.out.println("static context");
    }
}
~~~

Muốn đọc một trường instance trong static method, cần **tham chiếu tới đối tượng cụ thể**:

~~~java
class Reader {
    private int number = 7;

    static Runnable readLater(Reader target) {
        return () -> System.out.println(target.number);
    }
}
~~~

**target** là tham số cục bộ được capture, nên phải effectively final; giá trị **target.number** lại là trường instance được đọc tại thời điểm run. Hai quy tắc không mâu thuẫn.

### 5.1. Static field không được capture như biến cục bộ

Có thể thay giá trị của static field sau khi tạo lambda:

~~~java
class GlobalState {
    static int level = 1;

    static Runnable showLevel() {
        return () -> System.out.println(GlobalState.level);
    }
}
~~~

Nếu tạo **Runnable task = GlobalState.showLevel()**, sau đó gán **GlobalState.level = 9** rồi gọi **task.run()** trong cùng một thread, task in **9**. Điều này không vi phạm effectively final, vì **level là trường static**, không phải biến cục bộ.

Điều này cũng giải thích vì sao một lambda dựa trên static mutable field có thể cho kết quả khác nhau dù nhận cùng tham số rõ ràng: đầu vào thực tế còn phụ thuộc trạng thái dùng chung.

## 6. Thời điểm capture và thời điểm đọc giá trị

Một trong những khác biệt dễ gây lỗi nhất là **tham chiếu được giữ lại** so với **giá trị của trường được đọc về sau**.

Xét đoạn code:

~~~java
class Temperature {
    int degrees = 20;

    Runnable liveReader() {
        return () -> System.out.println(degrees);
    }

    Runnable snapshotReader() {
        int snapshot = degrees;
        return () -> System.out.println(snapshot);
    }
}
~~~

Gọi lần lượt:

~~~java
Temperature value = new Temperature();
Runnable live = value.liveReader();
Runnable snapshot = value.snapshotReader();
value.degrees = 27;
live.run();
snapshot.run();
~~~

Đầu ra là:

~~~text
27
20
~~~

- **liveReader** đọc **trường instance** khi lambda chạy, nên thấy 27 trong trường hợp đơn luồng này.
- **snapshotReader** trước hết sao chép giá trị trường vào biến cục bộ **snapshot**. Lambda capture giá trị **int** của biến cục bộ, nên giữ 20.
- Nếu biến cục bộ được capture là **tham chiếu tới đối tượng mutable**, lambda giữ tham chiếu ấy; các thay đổi lên nội dung của đối tượng vẫn có thể được quan sát. “Capture tham chiếu” không đồng nghĩa “sao chép sâu”.

Với nhiều thread, một phép gán ở thread này và phép đọc ở thread kia **không mặc nhiên có quan hệ happens-before**. Khi đó không được suy luận rằng liveReader chắc chắn thấy giá trị mới nhất nếu thiếu đồng bộ/volatile/atomic hoặc một quan hệ bộ nhớ phù hợp.

### 6.1. Một tinh tế với method reference

Giả sử **handler** là trường mutable chứa đối tượng triển khai Runnable:

~~~java
class DelegateHolder {
    Runnable handler = () -> System.out.println("first");

    Runnable dynamic() {
        return () -> handler.run();
    }

    Runnable bound() {
        return handler::run;
    }
}
~~~

Ở thời điểm tạo:

- **dynamic()** tạo lambda đọc trường **handler** khi nó chạy.
- **bound()** tạo bound method reference, biểu thức receiver **handler** được đánh giá tại lúc tạo method reference và đối tượng receiver được giữ lại.

Nếu sau đó gán **handler = () -> System.out.println("second")**, lời gọi task từ **dynamic()** có thể in **second**, còn task từ **bound()** đã tạo trước đó vẫn gọi đối tượng Runnable cũ và in **first** trong trường hợp đơn luồng nêu trên.

Điểm cốt lõi là **biểu thức receiver của bound method reference được đánh giá khi tạo reference**, còn lambda **() -> handler.run()** đánh giá trường handler ở thời điểm chạy. Sự khác biệt này có thể ảnh hưởng thiết kế callback khi dependency có thể được thay thế.

## 7. Ví dụ Java 17 chạy độc lập

Ví dụ dưới đây minh họa đồng thời:

- Trường instance riêng cho mỗi đối tượng.
- Trường static dùng chung giữa các đối tượng.
- Biến cục bộ **step** được lambda capture vì effectively final.
- Lambda có thể được tạo trước nhưng cập nhật trường khi gọi **run()**.
- Trạng thái của đối tượng A và B được cập nhật độc lập, còn static được cộng dồn.

Tạo file **LambdaFieldAccessDemo.java**:

~~~java
public class LambdaFieldAccessDemo {
    private final String name;
    private int instanceCount = 10;
    private static int sharedCount = 100;

    public LambdaFieldAccessDemo(String name) {
        this.name = name;
    }

    public Runnable makeIncrementTask() {
        int step = 3;

        return () -> {
            this.instanceCount += step;
            LambdaFieldAccessDemo.sharedCount += step;

            System.out.println(
                    name + ": instance=" + instanceCount
                    + ", static=" + sharedCount
            );
        };
    }

    public static void main(String[] args) {
        LambdaFieldAccessDemo a = new LambdaFieldAccessDemo("A");
        LambdaFieldAccessDemo b = new LambdaFieldAccessDemo("B");

        Runnable taskA = a.makeIncrementTask();
        Runnable taskB = b.makeIncrementTask();

        taskA.run();
        taskA.run();
        taskB.run();

        System.out.println("A final=" + a.instanceCount);
        System.out.println("B final=" + b.instanceCount);
        System.out.println("Shared final=" + sharedCount);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac LambdaFieldAccessDemo.java
java LambdaFieldAccessDemo
~~~

Đầu ra chính xác:

~~~text
A: instance=13, static=103
A: instance=16, static=106
B: instance=13, static=109
A final=16
B final=13
Shared final=109
~~~

**Diễn giải:**

1. A và B mỗi đối tượng có **instanceCount = 10**; **sharedCount = 100** chỉ có một giá trị ở cấp lớp.
2. **taskA** và **taskB** được tạo, nhưng chưa cập nhật gì cho tới khi gọi **run()**.
3. Lần chạy taskA đầu tiên: A tăng **10 → 13**, shared tăng **100 → 103**.
4. Lần chạy taskA thứ hai: A tăng **13 → 16**, shared tăng **103 → 106**.
5. Lần chạy taskB: B tăng **10 → 13**, shared tăng **106 → 109**.
6. B vẫn có **13**, A có **16**; shared là **109**. Đây là một chuỗi chạy tuần tự trên main thread nên thứ tự và stdout xác định.

**step** không bị gán lại trong **makeIncrementTask**, nên hợp lệ để capture. **name** là trường instance final, còn **instanceCount** và **sharedCount** là các trường mutable và được đọc/cập nhật khi lambda chạy. **this** bên trong lambda là A hoặc B tùy instance gọi **makeIncrementTask**.

Ví dụ này chủ đích chạy tuần tự. Nếu chuyển sang chạy đồng thời, không được dùng kết quả trên để suy luận thao tác **+=** là thread-safe.

## 8. Static final và instance final có nghĩa gì?

Khai báo **final** trên một trường không tự làm toàn bộ object graph bất biến:

~~~java
class Settings {
    static final java.util.List<String> AUDIT =
            new java.util.ArrayList<>();
}
~~~

Tham chiếu **AUDIT** không thể được gán lại sau khởi tạo, nhưng chương trình vẫn có thể gọi **Settings.AUDIT.add("event")**. Một lambda có thể sửa danh sách này, tạo tác dụng phụ toàn cục và có thể gây lỗi trong môi trường đa luồng.

Trái lại, với một trường primitive final:

~~~java
class Options {
    final int retryLimit = 3;
}
~~~

Code thông thường không thể gán lại **retryLimit** sau khởi tạo đúng quy tắc Java. Lambda không thay đổi được điều này. Nếu cần trạng thái thay đổi, hãy thiết kế nó bằng một trường mutable có kiểm soát, hoặc sử dụng đối tượng trạng thái phù hợp.

**static final** thường dùng để đặt hằng số hoặc tham chiếu cố định, nhưng không phải “tem bảo đảm hàm thuần”. Khi giá trị static final là đối tượng mutable, chính object đó vẫn có thể thay đổi qua các phương thức của nó.

## 9. Đa luồng: đọc/ghi trường chưa chắc an toàn

### 9.1. Phép tăng không nguyên tử

~~~java
class Statistics {
    static int total = 0;

    static Runnable newTask() {
        return () -> total++;
    }
}
~~~

Nếu nhiều thread chạy **newTask()** đồng thời, phép **total++** gồm các bước đọc, cộng, ghi và có thể bị mất cập nhật. Tương tự **this.instanceCount++** có thể race khi cùng một instance được nhiều thread sử dụng.

Việc **lambda** có một SAM không tạo cơ chế đồng bộ. Việc sử dụng **volatile** cho một biến int giúp xử lý **khả năng nhìn thấy giá trị và thứ tự bộ nhớ** theo Java Memory Model, nhưng **volatile++ vẫn không phải tăng nguyên tử**.

### 9.2. Giải pháp nguyên tử cho một bộ đếm độc lập

~~~java
import java.util.concurrent.atomic.AtomicInteger;

class SafeStatistics {
    private static final AtomicInteger TOTAL = new AtomicInteger();

    static Runnable newTask() {
        return TOTAL::incrementAndGet;
    }

    static int total() {
        return TOTAL.get();
    }
}
~~~

Đoạn là ví dụ một lớp độc lập, không có main. **AtomicInteger.incrementAndGet()** tăng nguyên tử một biến đếm, và giá trị int trả về có thể bị bỏ đi khi dùng dưới dạng **Runnable**. Nếu số đếm có thể vượt giới hạn int, phải có quy tắc overflow/giới hạn phù hợp; AtomicInteger không tự biến int thành vô hạn.

Với một đối tượng gồm nhiều trường có bất biến liên quan, chỉ đổi từng trường thành AtomicInteger **không bảo đảm** toàn bộ cập nhật nhiều trường là nguyên tử. Khi đó cần synchronized, lock, message queue, immutable state hoặc cơ chế khác tùy mục tiêu.

### 9.3. Ví dụ synchronized ở cấp đối tượng

~~~java
class SafeAccount {
    private int balance;

    synchronized void deposit(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("Negative amount");
        }
        balance = Math.addExact(balance, amount);
    }

    synchronized int balance() {
        return balance;
    }

    Runnable depositTask(int amount) {
        return () -> deposit(amount);
    }
}
~~~

**amount** được capture hợp lệ nếu không bị gán lại. Phương thức **deposit** khóa trên instance **SafeAccount** hiện tại, nên nhiều thread gọi vào **cùng instance** được phối hợp cho cả kiểm tra và ghi. Phương thức synchronized trên **instance** không tự bảo vệ một static field dùng chung giữa nhiều instance.

Các đoạn code này không có main độc lập; chúng minh họa cách bảo vệ trạng thái khi lambda có thể chạy đa luồng.

## 10. Tác dụng phụ, kiểm thử và thiết kế tốt hơn

Một lambda đọc trường instance hoặc static mutable thường phụ thuộc vào **trạng thái ngoài các tham số được khai báo**. Vì vậy, nếu muốn hàm tính toán dễ kiểm thử, hãy cân nhắc truyền giá trị cần thiết thành tham số và trả kết quả thay vì sửa trường.

Ví dụ dạng tính toán thuần:

~~~java
static int nextCount(int current, int step) {
    return Math.addExact(current, step);
}
~~~

Code điều phối có thể gọi **nextCount(instanceCount, step)** rồi cập nhật trường tại một ranh giới có kiểm soát. Bản thân **nextCount** không sửa field, không đọc global state và luôn cho cùng hành vi với cùng hai đối số.

Một thiết kế phân lớp thường có:

- **Đọc dữ liệu/nhận sự kiện:** phụ thuộc môi trường, I/O, thời gian, người dùng.
- **Tính kết quả:** các hàm nhận giá trị cụ thể; dễ kiểm thử độc lập.
- **Cập nhật state hoặc gửi hiệu ứng:** ở lớp sở hữu trạng thái, có hợp đồng lỗi và đồng bộ rõ ràng.

Không cần biến mọi callback thành pure function. Điều quan trọng là nhận diện nơi có side effect và chỉ cho phép cập nhật trong phạm vi phù hợp.

### 10.1. Static mutable field và kiểm thử

Nếu các bài test cùng dùng một **static int state**, test trước có thể để lại giá trị khiến test sau thất bại dù logic của từng test riêng lẻ đúng. Để tránh phụ thuộc thứ tự:

- Hạn chế static mutable state trong logic nghiệp vụ.
- Chuyển trạng thái cần thiết vào instance được tạo riêng cho từng test, hoặc dependency được truyền từ ngoài vào.
- Nếu phải dùng static state, quản lý vòng đời/reset theo hợp đồng kiểm thử và tránh các test chạy song song thiếu cách ly.
- Kiểm tra cả giá trị trả về lẫn trạng thái/hiệu ứng nếu đó là hành vi quan sát được.

### 10.2. Vòng đời lambda và tham chiếu tới this

Một lambda tham chiếu tới **this.instanceField** có thể giữ tham chiếu tới instance bao quanh. Nếu callback được lưu lâu trong một registry static hoặc một đối tượng sống lâu hơn, nó có thể giữ instance đó tồn tại lâu hơn dự kiến.

Ví dụ: đăng ký lambda làm listener nhưng không tháo listener khi component bị hủy có thể khiến component khó được GC khi registry vẫn giữ lambda. Chính sách unregister, vòng đời subscription và ownership của callback cần được thiết kế rõ. Không phải mọi lambda đều giữ **this**; điều đó phụ thuộc nó tham chiếu những gì và cách compiler/JVM hiện thực.

## 11. Các lỗi thường gặp

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Cho rằng field phải effectively final | Quy tắc này áp dụng cho biến cục bộ/parameter được capture | Phân biệt local với instance/static field |
| Cho rằng lambda chụp sẵn giá trị mọi field | Lambda thường đọc field khi thực thi | Dùng snapshot local nếu muốn đóng băng giá trị |
| Gán lại biến local sau khi capture | Biến mất tính effectively final | Tách giá trị local cố định hoặc thay thiết kế |
| Hiểu **final List** là không thể sửa | Final khóa tham chiếu, không khóa nội dung | Dùng immutable data/snapshot phù hợp |
| Dùng **this** trong static method | Static context không có instance this | Truyền object cụ thể làm tham số |
| Nhầm **this** của lambda với anonymous class | Lambda dùng lexical this | Dùng **this.field**, **Outer.this** đúng ngữ cảnh |
| Dùng static mutable field cho dữ liệu từng object | Mọi instance chia sẻ cùng trường | Dùng instance field nếu cần state riêng |
| Tin rằng **volatile++** là nguyên tử | Volatile không biến phép đọc–sửa–ghi thành nguyên tử | AtomicInteger, lock hoặc thiết kế ownership |
| Chạy callback cập nhật object mutable ở parallel stream | Có thể race và mất cập nhật | Dữ liệu độc lập hoặc cơ chế đồng bộ |
| Lưu callback tham chiếu this quá lâu | Có thể kéo dài vòng đời object | Quản lý đăng ký/hủy listener rõ ràng |

## 12. Bài tập thực hành

### Bài 1: Đọc giá trị mới hay giá trị cũ?

~~~java
class Box {
    int value = 2;

    Runnable live() {
        return () -> System.out.println(value);
    }

    Runnable snapshot() {
        int saved = value;
        return () -> System.out.println(saved);
    }
}
~~~

Tạo box, lấy hai Runnable, gán **box.value = 8**, rồi lần lượt gọi **live.run()** và **snapshot.run()** trong cùng một thread.

**Đáp án:** in **8** rồi **2**. Live đọc field lúc chạy; snapshot capture int local được lấy khi tạo Runnable.

### Bài 2: Đoán kết quả của instance và static

~~~java
class Counts {
    int own = 1;
    static int shared = 10;

    Runnable task() {
        return () -> {
            own++;
            shared++;
        };
    }
}
~~~

Tạo hai instance **a** và **b**; gọi **a.task().run()** hai lần và **b.task().run()** một lần, tuần tự. Hỏi **a.own**, **b.own** và **Counts.shared** cuối cùng là bao nhiêu?

**Đáp án:** **a.own = 3**, **b.own = 2**, **Counts.shared = 13**. Trường own độc lập theo instance; trường shared cộng từ cả hai.

### Bài 3: Nhận diện code không biên dịch

~~~java
int step = 1;
Runnable action = () -> System.out.println(step);
step++; // Lỗi: biến cục bộ được capture đã bị thay đổi.
~~~

**Sửa:** giữ step effectively final; nếu muốn cập nhật một trạng thái có kiểm soát, đặt trạng thái đó trong object được sở hữu rõ ràng hoặc chuyển đổi thiết kế để tính giá trị mới. Không nên dùng mảng một phần tử chỉ để “lách” quy tắc effectively final nếu mục tiêu thực sự là state chia sẻ.

### Bài 4: Viết callback an toàn hơn

Thiết kế một bộ đếm dùng chung cho các tác vụ cập nhật từ nhiều thread. Hãy xác định liệu state cần là instance hay static; chọn AtomicInteger hoặc synchronized phù hợp; xử lý overflow nếu có; kiểm thử tính đúng đắn khi nhiều tác vụ hoàn thành. Cuối cùng giải thích vì sao một lambda không làm bảo đảm thread-safe tự xuất hiện.

## 13. Ghi nhớ

**Lambda có thể đọc/sửa trường instance và static** theo quy tắc truy cập Java. **Effectively final** áp dụng cho biến cục bộ và tham số phương thức bao ngoài được lambda capture, không áp dụng như một lệnh cấm sửa trường.

- **this** trong lambda là instance bao ngoài nơi lambda được khai báo; static context không có this.
- **Instance field** thuộc từng đối tượng; **static field** được chia sẻ ở cấp lớp.
- Lambda đọc **field hiện thời khi chạy** trừ khi bạn chủ đích chụp giá trị vào biến local hoặc bound receiver theo kiểu phù hợp.
- **Truy cập được không có nghĩa an toàn đa luồng**: volatile không khiến ++ nguyên tử, và mutable static state có thể ảnh hưởng nhiều instance/test.
- Khi logic nên dễ kiểm thử, hãy tách tính toán từ giá trị đầu vào và đặt các hiệu ứng cập nhật state ở một ranh giới rõ ràng.
