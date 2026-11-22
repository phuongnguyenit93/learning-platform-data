# Duck typing và đa hình theo khả năng trong Java OOP

> **Ý tưởng cốt lõi:** Thay vì hỏi “đối tượng này thuộc họ lớp nào?”, nhiều bài toán thực tế chỉ cần hỏi “đối tượng này **làm được việc gì**?”. Một con vịt thật, một con vịt robot hay món đồ chơi phát tiếng vịt có thể khác nhau hoàn toàn về cấu tạo, nhưng đều có khả năng **phát tiếng kêu**. Ta muốn viết một thao tác dùng chung để yêu cầu chúng phát tiếng mà không phải kiểm tra từng loại cụ thể.

Tư duy này liên quan đến **duck typing** và **đa hình theo khả năng** (*capability-based polymorphism*). Hai khái niệm gần nhau về cách nhìn hành vi, nhưng cơ chế kiểu của ngôn ngữ **không giống nhau**: Python có thể gọi phương thức phù hợp ngay trên object tại runtime; Java thường cần một **interface hoặc kiểu cha được khai báo rõ**, hay một adapter chuyển đổi đối tượng sang hợp đồng cần dùng.

Bài này giải thích ranh giới đó, dùng mã Java chạy được để thực hành và chỉ ra khi nào nên lựa chọn interface, kiểm tra khả năng, hoặc adapter.

## 1. Duck typing là gì?

Cụm từ phổ biến để gợi nhớ duck typing là: *“Nếu một thứ đi như vịt và kêu như vịt, hãy đối xử với nó như một con vịt.”*

Trong lập trình, ý nghĩa không nằm ở việc một đối tượng **có tên lớp `Duck`**, mà nằm ở việc nó **cung cấp hành vi được yêu cầu**.

Ví dụ ý tưởng bằng Python:

~~~python
class RealDuck:
    def quack(self):
        print("Cạp cạp")

class ToyDuck:
    def quack(self):
        print("Chíp chíp")

def make_sound(thing):
    thing.quack()

make_sound(RealDuck())
make_sound(ToyDuck())
~~~

`make_sound` không cần biết lớp của `thing` có kế thừa một lớp `Duck` hay không. Khi chạy, Python tìm phương thức `quack` trên đối tượng. Nếu phương thức không tồn tại, hoặc lời gọi không phù hợp, lỗi có thể xuất hiện **tại runtime** (chẳng hạn `AttributeError`).

Đây là dạng thường gặp của **duck typing động**: sử dụng đối tượng dựa trên khả năng nó cung cấp trong ngữ cảnh hiện tại, không bắt buộc khai báo quan hệ kế thừa trước.

**Không nên đồng nhất duck typing với structural typing:** hệ thống kiểu **theo cấu trúc** có thể kiểm tra hình dạng thành viên ngay ở thời điểm biên dịch, còn duck typing động thường để hành vi được thử khi chạy. Cả hai có thể quan tâm đến “đối tượng cung cấp những gì”, nhưng khác nhau ở thời điểm và cách kiểm tra.

## 2. Java không tự coi hai lớp cùng có `quack()` là tương thích

Trong Java, quan hệ kiểu con thông thường giữa các lớp/interface là **nominal**: phải được thiết lập qua `extends`, `implements`, hoặc quan hệ subtype hợp lệ đã có trong hệ phân cấp.

Xét hai lớp:

~~~java
class RealDuck {
    public void quack() {
        System.out.println("Cạp cạp");
    }
}

class ToyDuck {
    public void quack() {
        System.out.println("Chíp chíp");
    }
}
~~~

Dù hai class đều có `public void quack()`, ta **không thể** viết một hàm Java nhận kiểu `RealDuck` rồi truyền `ToyDuck` vào chỉ vì chúng có cùng phương thức:

~~~java
static void makeSound(RealDuck duck) {
    duck.quack();
}

// makeSound(new ToyDuck()); // LỖI BIÊN DỊCH
~~~

Và chỉ khai báo một interface giống chữ ký vẫn chưa đủ:

~~~java
interface Quackable {
    void quack();
}

// Quackable q = new ToyDuck(); // Vẫn lỗi nếu ToyDuck không implements.
~~~

Vì vậy, nói “Java có duck typing giống Python” là **không chính xác**. Java hỗ trợ thiết kế dựa trên **khả năng** rất tốt, nhưng cách thông thường là **biểu đạt khả năng thành interface** và để các lớp chủ động hiện thực hợp đồng đó.

| Câu hỏi | Duck typing động, như ví dụ Python | Java qua interface |
| --- | --- | --- |
| Đối tượng phải có tên lớp cụ thể? | Không | Không |
| Cần khai báo `implements` một hợp đồng? | Không trong ví dụ | Có, trực tiếp hoặc qua quan hệ subtype hợp lệ |
| Chỉ cần cùng tên/chữ ký phương thức? | Có thể dùng khi runtime cung cấp hành vi phù hợp | **Chưa đủ** để thành subtype của interface |
| Phát hiện thiếu phương thức | Thường khi thực thi lời gọi | Thường khi biên dịch mã dùng kiểu interface |
| Tách được mã sử dụng khỏi class cụ thể? | Có | Có |
| Ai chịu trách nhiệm tuân thủ ý nghĩa hành vi? | Người viết/lựa chọn object | Người viết implementation và kiểm thử hợp đồng |

**Ghi nhớ:** *Java có thể đạt cùng mục đích thiết kế “hãy yêu cầu một khả năng” mà không vận hành theo cùng cơ chế duck typing động.*

## 3. Đa hình theo khả năng: mỗi interface là một vai trò

Ta không cần ép mọi đối tượng vào một cây kế thừa kiểu `Duck`. Thay vào đó, mô hình hóa những khả năng độc lập:

~~~java
interface Quackable {
    void quack();
}

interface Swimmable {
    void swim(int meters);
}

interface Rechargeable {
    void recharge(int units);
}
~~~

Một **vịt thật** có thể vừa kêu vừa bơi; một **vịt robot** có thể kêu và sạc pin; một **đồ chơi bóp tay** có thể kêu nhưng không bơi hay sạc.

Tương ứng:

- `WildDuck implements Quackable, Swimmable`
- `RobotDuck implements Quackable, Rechargeable`
- Một `SqueakyToy` độc lập có phương thức `quack()`; nếu không implements `Quackable`, cần thích nghi nó với hợp đồng Java.

Chương trình ghi tiếng kêu chỉ cần `Quackable`. Bể bơi chỉ cần `Swimmable`. Trạm sạc chỉ cần `Rechargeable`. Không thành phần nào buộc phải biết “loại vịt” đầy đủ của đối tượng.

~~~mermaid
classDiagram
    class Quackable {
        <<interface>>
        +quack() void
    }
    class Swimmable {
        <<interface>>
        +swim(int) void
    }
    class Rechargeable {
        <<interface>>
        +recharge(int) void
    }
    class WildDuck {
        -distanceMeters int
        +quack() void
        +swim(int) void
    }
    class RobotDuck {
        -battery int
        +quack() void
        +recharge(int) void
    }
    Quackable <|.. WildDuck
    Swimmable <|.. WildDuck
    Quackable <|.. RobotDuck
    Rechargeable <|.. RobotDuck
~~~

Sơ đồ là **quan hệ kiểu**, không phải sơ đồ hai “nửa đối tượng”. Một instance `WildDuck` có thể được xem qua cả hai interface mà vẫn là **một đối tượng duy nhất**, chia sẻ cùng trạng thái nội bộ.

## 4. Ví dụ Java hoàn chỉnh: yêu cầu đúng năng lực

Lưu vào file **`DuckTypingCapabilitiesDemo.java`**. Chạy với Java 11 trở lên, không cần thư viện ngoài.

~~~java
import java.util.List;

public class DuckTypingCapabilitiesDemo {

    interface Quackable {
        void quack();
    }

    interface Swimmable {
        void swim(int meters);
    }

    interface Rechargeable {
        void recharge(int units);
    }

    static final class WildDuck implements Quackable, Swimmable {
        private int totalDistanceMeters;

        @Override
        public void quack() {
            System.out.println("Vịt thật: cạp cạp");
        }

        @Override
        public void swim(int meters) {
            if (meters <= 0) {
                throw new IllegalArgumentException(
                        "Quãng đường phải dương");
            }
            totalDistanceMeters = Math.addExact(
                    totalDistanceMeters, meters);
            System.out.println(
                    "Vịt thật bơi thêm " + meters
                    + " m (tổng " + totalDistanceMeters + " m)");
        }
    }

    static final class RobotDuck implements Quackable, Rechargeable {
        private int battery = 1;

        @Override
        public void quack() {
            if (battery == 0) {
                throw new IllegalStateException("Robot hết pin");
            }
            battery--;
            System.out.println(
                    "Vịt robot: quack điện tử (pin " + battery + ")");
        }

        @Override
        public void recharge(int units) {
            if (units <= 0) {
                throw new IllegalArgumentException(
                        "Năng lượng sạc phải dương");
            }
            battery = Math.addExact(battery, units);
            System.out.println(
                    "Vịt robot sạc thêm " + units
                    + " (pin " + battery + ")");
        }
    }

    // Một lớp có phương thức quack nhưng KHÔNG implements Quackable.
    static final class SqueakyToy {
        public void quack() {
            System.out.println("Đồ chơi: chíp chíp");
        }
    }

    // Chỉ yêu cầu khả năng phát tiếng.
    static void askToQuack(Quackable participant) {
        participant.quack();
    }

    // Tình huống này chọn sử dụng các khả năng tùy chọn.
    static void runActivity(Quackable participant) {
        askToQuack(participant);

        if (participant instanceof Swimmable) {
            Swimmable swimmer = (Swimmable) participant;
            swimmer.swim(10);
        }

        if (participant instanceof Rechargeable) {
            Rechargeable robot = (Rechargeable) participant;
            robot.recharge(2);
        }
    }

    public static void main(String[] args) {
        WildDuck wildDuck = new WildDuck();
        RobotDuck robotDuck = new RobotDuck();
        SqueakyToy toy = new SqueakyToy();

        // Method reference cung cấp một Quackable adapter.
        Quackable toyAsQuackable = toy::quack;

        List<Quackable> participants = List.of(
                wildDuck, robotDuck, toyAsQuackable);

        for (Quackable participant : participants) {
            runActivity(participant);
        }

        // Không hợp lệ:
        // Quackable directToy = toy;
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DuckTypingCapabilitiesDemo.java
java DuckTypingCapabilitiesDemo
~~~

Kết quả:

~~~text
Vịt thật: cạp cạp
Vịt thật bơi thêm 10 m (tổng 10 m)
Vịt robot: quack điện tử (pin 0)
Vịt robot sạc thêm 2 (pin 2)
Đồ chơi: chíp chíp
~~~

### Vì sao kết quả như vậy?

| Phần tử trong `participants` | Đối tượng hoặc adapter thực tế | `quack()` | Khả năng bổ sung được nhận diện |
| --- | --- | --- | --- |
| Phần tử 1 | `WildDuck` | “Cạp cạp” | `Swimmable` → bơi 10 m |
| Phần tử 2 | `RobotDuck` | “Quack điện tử” | `Rechargeable` → sạc 2 đơn vị |
| Phần tử 3 | Adapter từ `toy::quack` | “Chíp chíp” | Không yêu cầu có `Swimmable`/`Rechargeable` |

Khi gọi `runActivity(participant)`, biến `participant` có **kiểu tĩnh** là `Quackable`. Nó luôn gọi được `quack()`. Với `WildDuck` và `RobotDuck`, lời gọi đa hình chọn implementation riêng. Ở phần tử thứ ba, implementation của `Quackable` là một **đối tượng chức năng được tạo/biểu diễn từ method reference**, chuyển lời gọi tới `SqueakyToy.quack()`.

Do đó **không phải** `SqueakyToy` bỗng trở thành subtype của `Quackable`. Ta đã tạo một **giá trị khác** phù hợp với interface để gọi hành vi mà đồ chơi vốn có.

Các bộ đếm `totalDistanceMeters` và `battery` cho thấy mỗi implementation được tự quản lý trạng thái của mình. Chia sẻ interface **không có nghĩa** chúng cùng cấu trúc field hoặc cùng thuật toán.

## 5. Phân biệt “hỏi loại” với “yêu cầu khả năng”

Hai cách tổ chức code dẫn tới khả năng mở rộng khác nhau.

### Cách dễ phụ thuộc lớp cụ thể

~~~java
// Ví dụ minh họa, KHÔNG phải API khuyến nghị:
void makeNoise(Object value) {
    if (value instanceof WildDuck) {
        ((WildDuck) value).quack();
    } else if (value instanceof RobotDuck) {
        ((RobotDuck) value).quack();
    }
}
~~~

Mỗi khi có một lớp mới biết phát tiếng, hàm trên lại phải thêm nhánh, và còn bỏ sót đồ chơi.

### Cách theo hợp đồng khả năng

~~~java
void makeNoise(Quackable value) {
    value.quack();
}
~~~

Hàm này không phải chỉnh sửa khi có implementation mới, miễn đối tượng được truyền vào có một giá trị tham chiếu hợp lệ của `Quackable`.

Đây là lợi ích của đa hình: **bên gọi yêu cầu hành vi thông qua hợp đồng; bên nhận chọn cách thực hiện**.

Không cần dùng `instanceof` ở mọi chỗ chỉ để thay thế các phương thức đa hình đã có. Khi hành vi chính là `quack()`, **gọi thẳng `participant.quack()`** thay vì hỏi nó có phải `WildDuck` hay `RobotDuck`.

Nhưng `instanceof` ở ví dụ `runActivity` có lý do riêng: chương trình đang khám phá **những vai trò tùy chọn** (`Swimmable` hoặc `Rechargeable`) ngoài hợp đồng tối thiểu `Quackable`. Đây là một cách sử dụng hợp lý khi tình huống thực sự tùy chọn, nhưng không nhất thiết là cách tốt nhất cho mọi API.

## 6. Khi nào nên dùng tham số từng interface thay vì kiểm tra `instanceof`?

Nếu một hành động **bắt buộc** đối tượng có khả năng bơi, khai báo ngay kiểu tham số:

~~~java
static void swimmingLesson(Swimmable swimmer) {
    swimmer.swim(100);
}
~~~

Lúc này compiler hỗ trợ phát hiện nơi gọi sai:

~~~java
WildDuck wild = new WildDuck();
swimmingLesson(wild); // Hợp lệ.

// swimmingLesson(new RobotDuck()); // Lỗi: không có Swimmable.
~~~

Tương tự:

~~~java
static void chargingStation(Rechargeable device) {
    device.recharge(5);
}
~~~

Cách này thường tốt hơn API nhận `Object`, rồi tìm hiểu bằng một chuỗi `instanceof` kéo dài.

Nếu một thao tác **bắt buộc đồng thời** phải có hai năng lực, có thể định nghĩa một interface tổ hợp:

~~~java
interface AmphibiousVoice extends Quackable, Swimmable {
}
~~~

Một class khai báo `implements AmphibiousVoice` sẽ cam kết cả hai khả năng. **Chú ý:** Java nominal typing không tự coi `WildDuck implements Quackable, Swimmable` là subtype của `AmphibiousVoice` chỉ vì nó đã có đủ phương thức. Nếu thực sự cần một kiểu hợp đồng gộp, lớp phải triển khai kiểu gộp (trực tiếp/gián tiếp), hoặc dùng adapter.

So sánh lựa chọn:

| Nhu cầu | Thiết kế thường phù hợp |
| --- | --- |
| Mọi đối tượng được truyền đều phải kêu | Tham số `Quackable` |
| Mọi đối tượng được truyền đều phải bơi | Tham số `Swimmable` |
| Chức năng bơi chỉ là một bổ sung tùy chọn | Kiểm tra `instanceof Swimmable` ở ranh giới thích hợp |
| Một đối tượng phải cam kết nhiều năng lực cùng lúc | Interface tổ hợp hoặc abstraction có hợp đồng rõ |
| Thư viện cũ có phương thức giống hợp đồng nhưng không implements | Adapter hoặc method reference/lambda nếu phù hợp |
| Chỉ có dữ liệu/chức năng liên quan trong cùng use case | Có thể dùng composition thay vì ép thành cây kế thừa |

**Tư duy thiết kế:** hãy để kiểu tham số biểu đạt **khả năng thật sự cần thiết**, không nhất thiết biểu đạt tất cả chi tiết của đối tượng.

## 7. Method reference: một cây cầu nhỏ, không phải duck typing tự động

Điểm thú vị ở Java là có thể thích nghi một phương thức tương thích với **functional interface**.

~~~java
@FunctionalInterface
interface Quackable {
    void quack();
}

class SqueakyToy {
    public void quack() {
        System.out.println("Chíp chíp");
    }
}
~~~

~~~java
SqueakyToy toy = new SqueakyToy();

// Sai: SqueakyToy không khai báo implements Quackable.
// Quackable a = toy;

// Đúng: biểu thức method reference có target type Quackable.
Quackable b = toy::quack;
b.quack();
~~~

`Quackable` là **functional interface** vì có một phương thức trừu tượng chức năng duy nhất. Compiler kiểm tra `toy::quack` có thể dùng làm implementation cho phương thức chức năng `void quack()` hay không.

Một lambda tương đương về hành vi:

~~~java
Quackable c = () -> toy.quack();
~~~

Với yêu cầu nhiều phương thức, method reference đơn lẻ không đủ để “tự implements cả interface”. Khi đó có thể viết **adapter class**:

~~~java
interface SoundEmitter {
    void emit();
    String category();
}

final class ToySoundAdapter implements SoundEmitter {
    private final SqueakyToy toy;

    ToySoundAdapter(SqueakyToy toy) {
        this.toy = java.util.Objects.requireNonNull(toy);
    }

    @Override
    public void emit() {
        toy.quack();
    }

    @Override
    public String category() {
        return "TOY";
    }
}
~~~

Ưu điểm của adapter: có thể kết nối API khác tên phương thức, biến đổi dữ liệu, xác thực đầu vào và diễn giải lại lỗi. Nhược điểm là cần thêm một đối tượng/lớp liên kết. Hãy chọn cách đơn giản nhất đáp ứng đúng hợp đồng.

**Không nhầm:** Method reference không biến **class của đối tượng nguồn** thành subtype của interface. Nó tạo ra **một đối tượng chức năng mới** được định kiểu theo interface đích.

## 8. Có thể “duck type” bằng reflection trong Java không?

Có thể dùng reflection để **tìm và gọi phương thức khi chạy**, kể cả khi đối tượng không thực hiện một interface chung:

~~~java
import java.lang.reflect.Method;

static void invokeQuackDynamically(Object target)
        throws ReflectiveOperationException {
    Method method = target.getClass().getMethod("quack");
    method.invoke(target);
}
~~~

Ví dụ:

~~~java
invokeQuackDynamically(new SqueakyToy());
~~~

Điều này mô phỏng phần nào ý tưởng “hãy thử gọi phương thức có tên phù hợp”, nhưng cần nhận thức các giới hạn:

- `getMethod("quack")` tìm phương thức **public** tương ứng (ở đây không có đối số); quy tắc truy cập còn phụ thuộc vào kiểu khai báo và module của Java.
- Nếu không có phương thức, có thể xảy ra `NoSuchMethodException` tại runtime.
- Nếu phương thức bên trong ném ngoại lệ, reflection thường bọc ngoại lệ vào `InvocationTargetException`.
- Sai kiểu tham số, quyền truy cập, hiệu năng và khả năng bảo trì phức tạp hơn lời gọi trực tiếp.
- Compiler không kiểm tra lời gọi này theo hợp đồng `Quackable` như khi dùng interface.

Reflection **không chuyển toàn bộ hệ thống kiểu Java thành structural typing**. Nó là công cụ runtime phù hợp trong một số framework, cơ chế serialization, plugin hoặc tích hợp đặc thù. Trong code ứng dụng bình thường đã biết hợp đồng, interface/adapter rõ ràng hơn và an toàn hơn.

## 9. Tư duy “khả năng” khác cây kế thừa danh từ

Ví dụ nếu tạo:

~~~java
abstract class Duck {
    abstract void quack();
    abstract void swim(int meters);
}
~~~

rồi yêu cầu `RobotDuck extends Duck`, ta đã bắt mọi thứ mang tên Duck phải biết bơi. Nhưng một robot đồ chơi chỉ phát tiếng kêu có thể **không** biết bơi. Nếu nó override `swim` bằng `throw new UnsupportedOperationException(...)`, ta khiến code nhận `Duck` bất ngờ thất bại khi làm điều mà hợp đồng `Duck` hàm ý.

Tách vai trò:

~~~java
interface Quackable {
    void quack();
}

interface Swimmable {
    void swim(int meters);
}
~~~

cho phép lựa chọn đúng tập năng lực:

- `WildDuck` thực hiện cả hai.
- `RobotDuck` chỉ thực hiện `Quackable` (và có thể thêm `Rechargeable`).
- Một `SwimmingRobot` không cần có tên Duck vẫn có thể thực hiện `Swimmable`.

Đây là ứng dụng của **Interface Segregation Principle**: đừng bắt các lớp/client phụ thuộc vào những hành vi chúng không hỗ trợ hoặc không cần dùng.

Tuy nhiên, không nên chia nhỏ interface một cách máy móc: một hợp đồng cần đủ gắn kết và có ý nghĩa với các client thực tế. Nếu hai hành vi luôn phải đi cùng nhau theo nghiệp vụ, gộp chúng có thể hợp lý hơn.

## 10. “Có method đúng tên” chưa bảo đảm “đúng hợp đồng”

Hãy tưởng tượng hai đối tượng cùng có:

~~~java
void send(String target, String message)
~~~

Một đối tượng gửi email, đối tượng kia có thể ghi dữ liệu vào một bộ phận kiểm toán. Chữ ký giống nhau chưa đảm bảo:

- Ý nghĩa của `target` giống nhau.
- Có cùng quy tắc kiểm tra đầu vào.
- Có cùng cách xử lý lỗi hoặc timeout.
- Có cùng tác động phụ, tính idempotent hay mức độ an toàn.
- Có thể sử dụng thay thế trong cùng tình huống nghiệp vụ.

Dù dùng duck typing hay interface Java, **ngữ nghĩa hợp đồng** vẫn phải được định nghĩa và kiểm thử.

Trong ví dụ tiếng kêu, `Quackable.quack()` ngầm có nghĩa phát âm thanh theo một cách hợp lệ. Nếu `RobotDuck.quack()` bí mật xóa dữ liệu hoặc luôn từ chối thao tác trong trạng thái được xem là hợp lệ theo hợp đồng, việc thay thế có thể trở nên không an toàn. Đó là mối quan tâm của **Liskov Substitution Principle (LSP)** và thiết kế API hướng hành vi.

## 11. Kiểm thử các implementation theo cùng khả năng

Một lợi thế của interface là ta có thể viết **cùng một bộ kiểm tra hợp đồng** dành cho nhiều implementation.

Ví dụ kiểm thử **JUnit 5** (cần JUnit Jupiter và test runner phù hợp; chương trình chính ở phần 4 chỉ dùng JDK):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;

class QuackableContractTest {

    @Test
    void implementationsCanPerformCommonOperation() {
        List<DuckTypingCapabilitiesDemo.Quackable> actors =
                List.of(
                        new DuckTypingCapabilitiesDemo.WildDuck(),
                        new DuckTypingCapabilitiesDemo.RobotDuck());

        for (DuckTypingCapabilitiesDemo.Quackable actor : actors) {
            assertDoesNotThrow(actor::quack);
        }
    }

    @Test
    void invalidSwimDistanceIsRejected() {
        DuckTypingCapabilitiesDemo.Swimmable swimmer =
                new DuckTypingCapabilitiesDemo.WildDuck();

        assertThrows(IllegalArgumentException.class,
                () -> swimmer.swim(0));
    }

    @Test
    void adapterCallsAnExistingMethod() {
        DuckTypingCapabilitiesDemo.SqueakyToy toy =
                new DuckTypingCapabilitiesDemo.SqueakyToy();
        DuckTypingCapabilitiesDemo.Quackable adapter = toy::quack;

        assertDoesNotThrow(adapter::quack);
    }
}
~~~

Thử nghiệm thứ nhất xác minh tối thiểu rằng các instance thực hiện hợp đồng `Quackable` được gọi thành công trong trạng thái khởi tạo của bài. Trong hệ thống thật, các bài test hợp đồng còn cần kiểm tra **kết quả, trạng thái, lỗi, và điều kiện tiên quyết/hậu điều kiện**, không chỉ kiểm tra “không ném exception”.

Ngoài unit test, các ca đáng kiểm tra gồm: robot hết pin, quãng bơi bằng 0 hoặc âm, giá trị lớn gây overflow, adapter tới phương thức khác chữ ký và object không cung cấp khả năng tùy chọn.

## 12. Những hiểu nhầm thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “Java tự nhận mọi class có `quack()` là `Quackable`” | **Sai** | Quan hệ interface cần được khai báo hoặc thích nghi qua giá trị adapter |
| “Duck typing bắt buộc object phải là class `Duck`” | **Sai** | Trọng tâm là khả năng được dùng, không phải tên lớp |
| “Hai object cùng implements interface phải có cùng field” | **Sai** | Mỗi implementation có cấu trúc và thuật toán riêng |
| “Một object có thể đảm nhận nhiều interface” | **Đúng** | Một class có thể implements nhiều hợp đồng |
| “`instanceof` phát hiện một method chỉ vì trùng tên” | **Sai** | `instanceof` kiểm tra tương thích kiểu runtime, không dò chữ ký động |
| “Method reference làm class nguồn tự động implements interface” | **Sai** | Nó cung cấp một giá trị/đối tượng chức năng theo target type |
| “Reflection giống hệt duck typing của Python” | **Không** | Chỉ có thể mô phỏng vài cách gọi động, với nhiều ràng buộc khác |
| “Chỉ có interface, không cần kiểm thử nghĩa nghiệp vụ” | **Sai** | Compiler kiểm tra kiểu chứ không bảo đảm hợp đồng nghiệp vụ |
| “Cứ có khả năng tùy chọn là phải dùng `instanceof` ở mọi nơi” | **Sai** | Có thể thiết kế client nhận interface đúng nhu cầu hoặc dùng composition |

## 13. Luyện tập nhanh

**Câu 1.** Lớp `ToyDuck` chỉ khai báo `public void quack()` nhưng không `implements Quackable`. Có gán `Quackable q = new ToyDuck();` được không?

**Đáp án:** Không trong Java, dù chữ ký trùng. Phải khai báo quan hệ interface hoặc dùng adapter/method reference phù hợp.

**Câu 2.** `WildDuck` và `RobotDuck` không có cùng lớp cha tự định nghĩa, tại sao vẫn gọi chung qua `Quackable` được?

**Đáp án:** Cả hai đều công bố `implements Quackable`, nên mỗi instance đều là subtype của hợp đồng `Quackable`. Hàm nhận `Quackable` không cần biết tên lớp cụ thể.

**Câu 3.** Trong code chính, tại sao `runActivity` có thể gọi `participant.quack()` mà không cần `instanceof Quackable`?

**Đáp án:** Tham số đã được khai báo là `Quackable`, compiler bảo đảm lời gọi tồn tại. `instanceof` chỉ cần khi truy cập một **khả năng khác** có thể không được hỗ trợ.

**Câu 4.** Một hàm luôn cần đối tượng biết bơi. Nên khai báo `void exercise(Object obj)` rồi cast, hay `void exercise(Swimmable swimmer)`?

**Đáp án:** Ưu tiên `Swimmable` vì biểu đạt ngay năng lực bắt buộc và để compiler kiểm tra nơi gọi.

**Câu 5.** `WildDuck implements Quackable, Swimmable` có tự trở thành subtype của `interface AmphibiousVoice extends Quackable, Swimmable` không?

**Đáp án:** Không. Java dùng quan hệ kiểu được khai báo; đáp ứng cấu trúc hai interface không tự tạo một quan hệ nominal mới với interface hợp nhất.

**Câu 6.** Điều gì khác biệt giữa `Quackable q = toy::quack;` và `Quackable q = toy;`?

**Đáp án:** Câu đầu là chuyển đổi method reference theo functional interface, tạo giá trị có hành vi gọi tới `toy.quack()`; câu sau yêu cầu chính đối tượng `toy` đã là subtype của `Quackable`, điều không đúng nếu class không implements.

**Câu 7.** Khi nào không nên dùng mô hình “mọi Duck đều bơi được”?

**Đáp án:** Khi có những đối tượng có thể phát tiếng vịt nhưng không bơi được. Ép chúng override `swim` rồi ném lỗi phá kỳ vọng của bên dùng. Hãy tách `Quackable` và `Swimmable` theo khả năng thực sự.

## Ghi nhớ

**Duck typing** nhấn mạnh “đối tượng **có thể làm gì**” thay vì “đối tượng **mang tên kiểu gì**”. Java không tự gán subtype dựa trên hình dạng phương thức như duck typing động; để xây dựng **đa hình theo khả năng** trong Java, hãy mô hình hóa năng lực bằng interface, để các lớp hiện thực đúng những interface chúng hỗ trợ, và dùng adapter/method reference khi tích hợp đối tượng đã có.

Khi thiết kế API, hãy đặt câu hỏi: **“Đối tượng cần cung cấp năng lực tối thiểu nào để tác vụ này thực hiện đúng?”** Khai báo kiểu tham số theo năng lực đó thường mang lại code rõ hợp đồng, dễ mở rộng và ít phải phân nhánh theo tên lớp.