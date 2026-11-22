# Quan hệ “là một” và tính thay thế trong Java OOP

Khi thấy `Dog extends Animal` hoặc `ExpressShipping implements ShippingPolicy`, ta thường nói kiểu con có quan hệ **“là một” (*is-a*)** với kiểu cha. Trong lập trình, câu này có hai tầng ý nghĩa cần phân biệt:

- **Quan hệ kiểu (subtyping):** Java cho phép sử dụng một biểu thức kiểu con tại vị trí đang yêu cầu kiểu cha hoặc interface phù hợp.
- **Tính thay thế về hành vi (behavioral substitutability):** Sau khi thay đối tượng bằng một implementation khác, chương trình sử dụng hợp đồng chung vẫn hoạt động đúng theo những gì hợp đồng đã hứa.

Tầng thứ nhất phần lớn được trình biên dịch kiểm tra. Tầng thứ hai đòi hỏi người thiết kế định nghĩa và thực hiện **hợp đồng hành vi**: điều kiện đầu vào, điều được bảo đảm ở đầu ra, bất biến, lỗi, tác dụng phụ và các cam kết mà client dựa vào.

**Cốt lõi:** Có cú pháp `extends` hoặc `implements` chưa đủ để bảo đảm một quan hệ “là một” tốt về thiết kế. Kiểu con cần thật sự đảm nhiệm được vai trò của kiểu cha.

## 1. Hiểu đúng “là một” trong Java

Ví dụ:

~~~java
class Animal {
    public String describe() {
        return "Một động vật";
    }
}

class Dog extends Animal {
    @Override
    public String describe() {
        return "Một con chó";
    }

    public void bark() {
        System.out.println("Gâu!");
    }
}
~~~

Một đối tượng `Dog` cũng có thể được sử dụng như một `Animal`:

~~~java
Dog dog = new Dog();
Animal animal = dog; // Upcasting: hợp lệ, không cần ép kiểu tường minh.

System.out.println(animal.describe()); // Một con chó
// animal.bark(); // Không biên dịch: Animal không có bark().
~~~

Với đoạn này:

1. **Object thực tế** là `Dog`; phép gán `animal = dog` không tạo một `Animal` mới.
2. **Kiểu khai báo của biến** `animal` là `Animal`, nên compiler chỉ cho gọi những member có thể truy cập qua kiểu đó.
3. **Phương thức instance được override** được chọn tại runtime theo object thực tế: `Dog.describe()`.
4. `bark()` chỉ được khai báo trong `Dog`, không thuộc hợp đồng `Animal`, nên không gọi trực tiếp bằng tham chiếu `Animal`.

Đây là nền tảng của **đa hình động (runtime polymorphism)**.

~~~mermaid
classDiagram
    class Animal {
        +describe() String
    }
    class Dog {
        +describe() String
        +bark() void
    }
    Animal <|-- Dog
~~~

Trong Java, `extends` với class là cơ chế **kế thừa lớp**. Ngoài khả năng được nhìn như kiểu cha, subclass còn có quan hệ triển khai, constructor chaining và quy tắc override của Java. Một class chỉ có thể `extends` trực tiếp một class, nhưng có thể `implements` nhiều interface.

Ví dụ `Printer implements Printable` có nghĩa **Printer làm được vai trò Printable**, dù `Printer` không cần là một loại máy móc nằm trong cùng cây class với các implementation khác.

## 2. Quan hệ kiểu và khả năng thay thế không hoàn toàn giống nhau

| Câu hỏi | Tính thay thế theo kiểu Java | Tính thay thế theo hành vi |
|---|---|---|
| Kiểm tra chủ yếu ở đâu? | Compiler và hệ kiểu runtime | Thiết kế hợp đồng, kiểm thử, quan sát thực tế |
| Điều kiện cơ bản | `Dog` là subtype của `Animal` | `Dog` giữ đúng lời hứa công khai của `Animal` |
| Có cho phép thuật toán riêng? | Có | Có |
| Có yêu cầu đầu ra giống hệt? | Không | Không, trừ khi hợp đồng đòi hỏi |
| Có thể có lỗi mà compiler không phát hiện? | Có, như ép kiểu không hợp lệ | Có, như tự ý siết điều kiện hoặc trả kết quả sai nghĩa |
| Căn cứ đánh giá | `extends`, `implements`, method signature, type rules | Preconditions, postconditions, invariants, exception/side effects |

Chẳng hạn, một `ShippingPolicy` có thể báo mức phí khác nhau giữa gói tiêu chuẩn và hỏa tốc. Việc **mức phí khác nhau** không làm mất khả năng thay thế nếu hợp đồng cho phép mỗi gói có chính sách giá riêng. Nhưng nếu một implementation bất ngờ trả số âm khi hợp đồng quy định phí không âm, nó đã phá tính thay thế.

Ý tưởng này được biết đến qua **Nguyên tắc thay thế Liskov (Liskov Substitution Principle – LSP)**: những đối tượng của subtype phải có thể dùng thay cho đối tượng của supertype ở những nơi kỳ vọng supertype **mà không làm sai các thuộc tính đúng đắn đã được cam kết của chương trình**.

## 3. Ví dụ Java hoàn chỉnh: hai chính sách cùng một hợp đồng

Một ứng dụng bán hàng cần tính phí vận chuyển. Tầng đặt hàng chỉ cần một chính sách có khả năng **báo giá cho kiện hàng hợp lệ**; nó không cần biết mức giá được tính theo phương pháp nào.

Trong ví dụ này, hợp đồng quy định:

- Đầu vào là `Parcel` hợp lệ và khác `null`.
- `quote(parcel)` trả về một `ShippingQuote` khác `null`, phí không âm, tính bằng VND.
- Không được làm thay đổi `Parcel`.
- Với đầu vào `null`, implementation ném `NullPointerException`.
- Nếu phép tính vượt phạm vi `long`, implementation có thể ném `ArithmeticException`; không được âm thầm tràn số rồi báo phí sai.

Tạo file **`Demo.java`**; mã chạy với Java 17 trở lên:

~~~java
import java.util.Objects;

public class Demo {
    public static void main(String[] args) {
        Parcel parcel = new Parcel(1_500, 10);

        CheckoutService standard = new CheckoutService(
                new StandardShipping()
        );
        CheckoutService express = new CheckoutService(
                new ExpressShipping()
        );

        print(standard.calculate(parcel));
        print(express.calculate(parcel));
    }

    private static void print(ShippingQuote quote) {
        System.out.println(quote.method() + ": "
                + quote.feeVnd() + " VND");
    }
}

// Giá trị đầu vào hợp lệ ngay sau khi được tạo.
record Parcel(long weightGrams, int distanceKm) {
    Parcel {
        if (weightGrams <= 0) {
            throw new IllegalArgumentException(
                    "Trọng lượng phải dương");
        }
        if (distanceKm < 0) {
            throw new IllegalArgumentException(
                    "Khoảng cách không được âm");
        }
    }
}

record ShippingQuote(String method, long feeVnd) {
    ShippingQuote {
        Objects.requireNonNull(method, "method");
        if (method.isBlank() || feeVnd < 0) {
            throw new IllegalArgumentException(
                    "Báo giá không hợp lệ");
        }
    }
}

/**
 * Hợp đồng chung cho mọi chính sách vận chuyển.
 *
 * Với Parcel hợp lệ và khác null:
 * - Trả ShippingQuote khác null, feeVnd >= 0.
 * - Số tiền có đơn vị VND.
 * - Không sửa Parcel và không thực hiện ghi dữ liệu.
 *
 * @throws NullPointerException nếu parcel == null
 * @throws ArithmeticException nếu phép tính tràn long
 */
interface ShippingPolicy {
    ShippingQuote quote(Parcel parcel);
}

// Mô phỏng chính sách tiêu chuẩn.
final class StandardShipping implements ShippingPolicy {
    @Override
    public ShippingQuote quote(Parcel parcel) {
        Objects.requireNonNull(parcel, "parcel");

        long kilograms = ceilKilograms(parcel.weightGrams());
        long weightFee = Math.multiplyExact(kilograms, 5_000L);
        long distanceFee =
                Math.multiplyExact(parcel.distanceKm(), 2_000L);

        long total = Math.addExact(
                10_000L,
                Math.addExact(weightFee, distanceFee)
        );

        return new ShippingQuote("STANDARD", total);
    }

    private long ceilKilograms(long grams) {
        // grams > 0; tránh overflow của (grams + 999).
        return 1L + (grams - 1L) / 1_000L;
    }
}

// Mô phỏng chính sách hỏa tốc.
final class ExpressShipping implements ShippingPolicy {
    @Override
    public ShippingQuote quote(Parcel parcel) {
        Objects.requireNonNull(parcel, "parcel");

        long kilograms = 1L + (parcel.weightGrams() - 1L) / 1_000L;
        long weightFee = Math.multiplyExact(kilograms, 8_000L);
        long distanceFee =
                Math.multiplyExact(parcel.distanceKm(), 3_000L);

        long total = Math.addExact(
                20_000L,
                Math.addExact(weightFee, distanceFee)
        );

        return new ShippingQuote("EXPRESS", total);
    }
}

// Client chỉ cần khả năng báo giá, không cần biết class cụ thể.
final class CheckoutService {
    private final ShippingPolicy policy;

    CheckoutService(ShippingPolicy policy) {
        this.policy = Objects.requireNonNull(policy, "policy");
    }

    ShippingQuote calculate(Parcel parcel) {
        return policy.quote(parcel);
    }
}
~~~

Chạy:

~~~bash
javac Demo.java
java Demo
~~~

Kết quả:

~~~text
STANDARD: 40000 VND
EXPRESS: 66000 VND
~~~

Phép tính với kiện hàng 1.500 gram, 10 km:

| Chính sách | Phí cơ bản | Trọng lượng làm tròn 2 kg | Quãng đường 10 km | Tổng |
|---|---:|---:|---:|---:|
| Tiêu chuẩn | 10.000 | 2 × 5.000 | 10 × 2.000 | **40.000 VND** |
| Hỏa tốc | 20.000 | 2 × 8.000 | 10 × 3.000 | **66.000 VND** |

Mức phí khác nhau là **biến thể được hợp đồng cho phép**. Hai implementation vẫn thay thế được vì `CheckoutService` chỉ dựa vào một thao tác có cùng ý nghĩa: nhận kiện hàng hợp lệ và trả báo giá không âm theo VND.

~~~mermaid
classDiagram
    class ShippingPolicy {
        <<interface>>
        +quote(Parcel) ShippingQuote
    }
    class StandardShipping {
        +quote(Parcel) ShippingQuote
    }
    class ExpressShipping {
        +quote(Parcel) ShippingQuote
    }
    class CheckoutService {
        -ShippingPolicy policy
        +calculate(Parcel) ShippingQuote
    }
    ShippingPolicy <|.. StandardShipping
    ShippingPolicy <|.. ExpressShipping
    CheckoutService --> ShippingPolicy : phụ thuộc
~~~

Ở đây, subtype là **vai trò** `ShippingPolicy`. `StandardShipping` và `ExpressShipping` không nhất thiết cùng là một loại “đối tượng vật lý”; chúng là những chiến lược thực hiện cùng một khả năng.

## 4. Upcasting: truyền đối tượng con vào nơi nhận kiểu cha

Trong Java, phép gán hoặc truyền tham số từ subtype sang supertype phù hợp được gọi là **widening reference conversion**, thường được giải thích ngắn là *upcasting*:

~~~java
ShippingPolicy policy = new ExpressShipping();
CheckoutService service = new CheckoutService(policy);

ShippingQuote result = service.calculate(new Parcel(800, 4));
~~~

Phép chuyển kiểu này không làm biến thành một object mới, không sao chép dữ liệu và không “cắt bỏ” phần implementation. Object vẫn là `ExpressShipping`; biến `policy` chỉ cho phép sử dụng những thao tác công khai của `ShippingPolicy`.

Ví dụ dễ kiểm tra bằng Java:

~~~java
interface SoundMaker {
    String sound();
}

class Cat implements SoundMaker {
    @Override
    public String sound() {
        return "Meo";
    }

    public void scratch() {
        System.out.println("Cào");
    }
}

Cat cat = new Cat();
SoundMaker maker = cat;

System.out.println(maker.sound()); // Meo
System.out.println(maker == cat);  // true
// maker.scratch(); // Lỗi biên dịch: không thuộc SoundMaker.
~~~

Các dòng sử dụng đặt bên trong một phương thức Java thích hợp. Chính kiểu khai báo của tham chiếu giới hạn **những phương thức có thể gọi**, còn kiểu runtime của object quyết định **implementation của phương thức instance được override**.

Đừng nhầm với static method và field hiding:

~~~java
class Parent {
    public String kind = "Parent";

    public String describe() {
        return "Parent";
    }
}

class Child extends Parent {
    public String kind = "Child";

    @Override
    public String describe() {
        return "Child";
    }
}

Parent ref = new Child();
System.out.println(ref.kind);       // Parent: field theo kiểu tham chiếu.
System.out.println(ref.describe()); // Child: method theo kiểu runtime.
~~~

Kết quả cho thấy **field không override như instance method**. Vì vậy, thiết kế đa hình nên dựa vào phương thức/hợp đồng hơn là field công khai có cùng tên.

## 5. Điều kiện trước, điều kiện sau và bất biến trong LSP

Để một implementation thực sự thay thế được supertype, cần tôn trọng những lời hứa được client sử dụng.

### Không siết chặt precondition

Nếu `ShippingPolicy` cam kết hỗ trợ mọi `Parcel` hợp lệ, một implementation mới **không thể tự ý** đòi `distanceKm <= 5` rồi từ chối tất cả đơn đi xa hơn, trừ khi hợp đồng chung đã cho phép hành vi từ chối đó.

Đây là một implementation đáng nghi:

~~~java
final class VeryLocalShipping implements ShippingPolicy {
    @Override
    public ShippingQuote quote(Parcel parcel) {
        Objects.requireNonNull(parcel, "parcel");

        if (parcel.distanceKm() > 5) {
            throw new IllegalArgumentException(
                    "Chỉ giao trong bán kính 5 km");
        }
        return new ShippingQuote("LOCAL", 5_000L);
    }
}
~~~

Nó **biên dịch được**, nhưng vi phạm hợp đồng ví dụ đã xác định rằng mọi `Parcel` hợp lệ đều được báo giá, ngoại trừ trường hợp tràn số học. Client có thể truyền kiện hàng 10 km — một đầu vào hợp lệ theo hợp đồng chung — nhưng implementation tự bổ sung điều kiện đầu vào mới.

Nếu nghiệp vụ có chính sách vận chuyển chỉ phục vụ một số địa điểm, có thể thiết kế lại hợp đồng để biểu diễn **không hỗ trợ tuyến đường** như một kết quả hợp lệ, hoặc phân tách khả năng kiểm tra vùng phục vụ. Không nên giấu giới hạn mới trong subtype khiến client bất ngờ.

### Không làm yếu postcondition

Nếu hợp đồng hứa phí không âm, việc trả `null` hoặc một con số âm là sai. Ví dụ:

~~~java
final class NullShipping implements ShippingPolicy {
    @Override
    public ShippingQuote quote(Parcel parcel) {
        return null; // Biên dịch nhưng vi phạm hợp đồng non-null.
    }
}
~~~

Client có quyền dựa vào postcondition được công bố:

~~~java
ShippingQuote quote = policy.quote(parcel);
// Nếu hợp đồng được thực hiện đúng, quote != null.
System.out.println(quote.feeVnd());
~~~

Trong mã thực tế, nếu provider có thể từ chối hoặc hết dịch vụ, hãy thể hiện **trạng thái từ chối** bằng kiểu kết quả/exception đã được hợp đồng thống nhất. Không nên đánh tráo lỗi thành phí 0 nếu `0` mang nghĩa “miễn phí”.

### Giữ bất biến của supertype

Nếu một `Account` cam kết `balance >= 0`, lớp con không được làm `balance` âm qua những phương thức mới của mình. Một hành vi public bổ sung ở subtype cũng phải giữ trạng thái hợp lệ được supertype công bố.

Bất biến thường được bảo vệ qua constructor, kiểm tra trạng thái trước khi thay đổi và hạn chế cho subclass sửa trực tiếp field. Một interface không tự thực thi invariant bằng compiler; cần thiết kế implementation và kiểm thử.

### Giữ quy tắc lỗi và tác dụng phụ có thể quan sát

Một subtype không nên biến lời gọi vốn được hứa là chỉ tính toán thành thao tác âm thầm xóa dữ liệu. Nếu hợp đồng có quy tắc “không thực hiện I/O”, implementation mới không được bất ngờ gửi HTTP request hay ghi database.

Mặt khác, **không phải mọi khác biệt exception hoặc hiệu năng đều vi phạm LSP**. Điều cần xem là hợp đồng thực sự cam kết điều gì. Với kiểu `ShippingPolicy` ví dụ, `ArithmeticException` khi phép toán tràn đã là tình huống được công bố.

## 6. Một tên miền nghiệp vụ đúng chưa chắc có hợp đồng phù hợp

Trong hình học, hình vuông thuộc tập hình chữ nhật. Nhưng xét `Rectangle` **mutable** công khai hai setter độc lập:

~~~java
// Hợp đồng Rectangle: setWidth chỉ đổi width;
// setHeight chỉ đổi height.
rectangle.setWidth(5);
rectangle.setHeight(3);
System.out.println(rectangle.area()); // 15
~~~

Nếu `Square extends Rectangle` override mỗi setter để giữ `width == height`, sau hai lời gọi trên cả hai cạnh bằng `3`, diện tích thành `9`. Subtype đã **làm yếu hậu điều kiện** “chiều còn lại không đổi”. Nếu thay bằng cách ném lỗi khi hai chiều không bằng nhau, subtype lại **siết tiền điều kiện**: một đầu vào hợp lệ đối với `Rectangle` bị từ chối với `Square`.

Điều này minh họa ranh giới giữa *is-a theo cách gọi tên* và khả năng thay thế theo API. Hướng phù hợp là đưa `area()` lên một `Shape` chung, hoặc tách khả năng thay đổi kích thước của rectangle/square theo hợp đồng riêng. Bài cuối chương xây hai chương trình chạy được và contract tests để kiểm chứng từng trường hợp.

**Điểm riêng của bài hiện tại:** hãy đánh giá `ShippingPolicy` theo cùng tiêu chí: mọi implementation phải báo giá cho các kiện hàng hợp lệ được hợp đồng quy định; một biến thể có giá khác là hợp lệ, còn tự ý từ chối tuyến hợp lệ thì không.

## 7. “Is-a” và “has-a”: khi nào ưu tiên composition?

Một quan hệ kế thừa tốt thường đáp ứng được cả cách hiểu miền nghiệp vụ lẫn hợp đồng hành vi.

Các câu hỏi hữu ích:

1. Một đối tượng con có **thực sự là một loại** của đối tượng cha trong cách dùng của hệ thống không?
2. Mọi thao tác mà client có thể gọi trên kiểu cha có hợp lệ và có cùng ý nghĩa trên kiểu con không?
3. Một bất biến ở kiểu con có mâu thuẫn với cách thay đổi trạng thái mà kiểu cha cho phép không?
4. Ta đang muốn **thay thế theo hợp đồng**, hay chỉ đang muốn **tận dụng lại một ít code**?

Ví dụ, `Car extends Engine` là mô hình sai về ý nghĩa: xe **có một động cơ** (*has-a*), không phải **là một động cơ** (*is-a*). Sử dụng composition:

~~~java
final class Engine {
    public void start() {
        System.out.println("Động cơ hoạt động");
    }
}

final class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = java.util.Objects.requireNonNull(engine);
    }

    public void start() {
        engine.start();
    }
}
~~~

Code sử dụng:

~~~java
Car car = new Car(new Engine());
car.start();
~~~

`Car` giữ một collaborator `Engine` và ủy quyền hành vi. Composition thường phù hợp khi mối quan hệ là **có/chứa/sử dụng** hoặc khi muốn thay chi tiết thực hiện mà không ép class thành subtype sai.

Một quan hệ `extends` chỉ nhằm tái sử dụng code có thể khiến subclass phải nhận cả những thao tác của cha mà bản thân không thể đáp ứng đúng.

## 8. Các quy tắc Java khi override giúp bảo vệ một phần hợp đồng

Trình biên dịch Java thực thi một số giới hạn để giảm rủi ro khi subclass thay thế superclass.

| Quy tắc override | Ví dụ/ý nghĩa |
|---|---|
| Không giảm mức truy cập | Method cha `public` không được override thành `protected` |
| Có thể dùng kiểu trả về hiệp biến | Method con có thể trả subtype phù hợp của kiểu trả về tham chiếu |
| Không mở rộng checked exception trái phép | Method override không được khai báo checked exception rộng hơn quy tắc của method cha |
| Không override `final` instance method | `final` chặn override |
| Static method không override instance method | Static hiding và dynamic dispatch khác nhau |
| `private` method của lớp cha không được override | Subclass có thể có method cùng tên độc lập |
| `@Override` được compiler kiểm tra | Giúp phát hiện sai chữ ký hoặc nhầm quan hệ override |

Ví dụ kiểu trả về hiệp biến:

~~~java
class Animal {
    public Animal copy() {
        return new Animal();
    }
}

class Dog extends Animal {
    @Override
    public Dog copy() {
        return new Dog(); // Dog là subtype của Animal.
    }
}
~~~

Client có biến `Animal` vẫn có thể gọi `copy()` và nhận kết quả là `Animal` về mặt kiểu khai báo. Client có biến `Dog` biết rõ hơn rằng phương thức trả `Dog`.

Ví dụ checked exception:

~~~java
import java.io.IOException;

class Source {
    public String read() throws IOException {
        return "data";
    }
}

class CachedSource extends Source {
    @Override
    public String read() {
        return "cached"; // Không cần ném checked exception.
    }
}

// Không thể override read() thành:
// public String read() throws Exception { ... }
// vì Exception rộng hơn IOException.
~~~

Java cho phép override **giảm** phạm vi checked exception trong ví dụ trên, nhưng không cho thêm một checked exception không phù hợp với method gốc. Quy tắc ngôn ngữ hỗ trợ tính thay thế về mặt khai báo, song **không đủ** để chứng minh hành vi nghiệp vụ đúng.

Lưu ý: một subtype vẫn có thể ném unchecked exception lúc chạy. Vì thế việc “không có lỗi biên dịch” chưa đủ để bảo đảm mọi pre/postcondition được giữ.

## 9. Downcasting: vì sao ép kiểu về subtype có thể phá tính linh hoạt?

Upcasting từ subtype sang supertype thường tự động:

~~~java
ShippingPolicy policy = new StandardShipping();
~~~

Nhưng ép từ supertype sang một subtype cụ thể cần kiểm tra vì biến supertype có thể đang trỏ tới implementation khác:

~~~java
ShippingPolicy policy = new ExpressShipping();

// StandardShipping standard = (StandardShipping) policy;
// Nếu chạy: ClassCastException.
~~~

Java 17 hỗ trợ pattern matching với `instanceof` để kiểm tra an toàn:

~~~java
if (policy instanceof StandardShipping standard) {
    System.out.println("Đang dùng gói tiêu chuẩn");
}
~~~

Cách dùng này hợp lệ về cú pháp, nhưng nếu một client liên tục viết:

~~~java
if (policy instanceof StandardShipping) {
    // Một nhánh nghiệp vụ riêng.
} else if (policy instanceof ExpressShipping) {
    // Một nhánh khác.
}
~~~

thì nó bắt đầu phụ thuộc vào implementation cụ thể. Thêm một subtype mới lại phải sửa client, đi ngược mục tiêu đa hình.

Hãy tìm một thao tác chung thích hợp trong interface, hoặc tách chính sách lựa chọn implementation vào factory/configuration. Tuy vậy, `instanceof` vẫn có chỗ dùng khi xử lý kiểu thực tế là yêu cầu hợp lệ, như adapter tương thích ngược hoặc phân biệt một tập kiểu đóng.

**Không lạm dụng cast** chỉ để gọi phương thức ngoài hợp đồng. Nếu một khả năng chỉ thuộc một số implementation, cân nhắc interface vai trò riêng để mã cần khả năng đó có thể khai báo dependency chính xác.

## 10. Subtype của một đối tượng không có nghĩa collection cũng biến thành subtype

Một bẫy Java generics:

~~~java
class Animal {}
class Dog extends Animal {}

java.util.List<Dog> dogs = new java.util.ArrayList<>();

// java.util.List<Animal> animals = dogs; // Lỗi biên dịch.
~~~

Dù `Dog` là subtype của `Animal`, `List<Dog>` **không** là subtype của `List<Animal>`. Java generics mặc định **invariant**.

Nếu phép gán này được phép, ta có thể thêm một `Cat` vào danh sách thực tế chỉ dành cho `Dog`, phá an toàn kiểu.

Nếu muốn đọc các phần tử theo vai trò cha:

~~~java
java.util.List<Dog> dogs = java.util.List.of(new Dog());
java.util.List<? extends Animal> animals = dogs;

Animal first = animals.get(0);

// animals.add(new Animal()); // Không hợp lệ về type safety.
~~~

Wildcard `? extends Animal` cho phép đọc đối tượng như `Animal`, nhưng không thể tùy ý thêm một `Animal` cụ thể vì danh sách có thể đang thực sự chứa `Dog` hoặc một subtype khác.

Với nhu cầu thêm các `Dog` vào consumer:

~~~java
static void addDogs(java.util.List<? super Dog> destination) {
    destination.add(new Dog());
}
~~~

Quy tắc thực hành thường gọi là **PECS**: *Producer Extends, Consumer Super*. Đây là quy tắc variance của Java generics, không nên đồng nhất với phép upcasting giữa hai **đối tượng đơn lẻ**.

### Mảng khác generics

Mảng Java có tính **covariant**:

~~~java
Animal[] animals = new Dog[1];
// animals[0] = new Animal(); // ArrayStoreException lúc chạy.
~~~

Dù phép gán mảng biên dịch, JVM phải kiểm tra kiểu phần tử runtime. Generics invariant ngăn nhiều lỗi tương tự từ giai đoạn biên dịch.

## 11. Thiết kế hợp đồng để subtype có thể thay thế một cách hữu ích

Trong ví dụ tính phí, `ShippingPolicy` tập trung vào một khả năng nhỏ. Nếu cần thêm chính sách chỉ hỗ trợ tuyến ngắn, có hai hướng thiết kế tùy nghiệp vụ:

**Hướng A — Đổi hợp đồng để chấp nhận kết quả không phục vụ được.**

~~~java
sealed interface QuoteResult
        permits QuoteSuccess, UnsupportedRoute {}

record QuoteSuccess(ShippingQuote quote) implements QuoteResult {}
record UnsupportedRoute(String reason) implements QuoteResult {}
~~~

Một hợp đồng khác có thể khai báo `QuoteResult quote(Parcel parcel)`, và tất cả implementation thống nhất khi nào trả `UnsupportedRoute`. Client phải xử lý được trạng thái đó.

**Hướng B — Phân vai trò theo khả năng.** Ví dụ `RouteSupport` chỉ có `boolean supports(Parcel)`, còn `ShippingPolicy` báo giá khi được lựa chọn hợp lệ. Tuy nhiên, nếu `supports()` và `quote()` xảy ra ở thời điểm khác nhau, dữ liệu/điều kiện có thể thay đổi; API cần quy định tính nhất quán phù hợp.

Không có cách nào bắt mọi nhà cung cấp phải xử lý một đối tượng đầu vào vốn nằm ngoài khả năng thực tế của họ mà vẫn giữ nguyên hợp đồng cũ. Hãy thiết kế **ngôn ngữ kết quả hoặc ranh giới trách nhiệm** phản ánh đúng nghiệp vụ.

### Đừng hiểu LSP thành “mọi subtype phải giống nhau”

Một `Comparator<String>` có thể sắp xếp từ A đến Z hoặc Z đến A; một `PaymentMethod` có thể thực hiện thanh toán bằng thẻ hoặc ví; một `ShippingPolicy` có thể tính nhiều mức phí.

Khác biệt là hợp lệ nếu client chỉ dựa vào những cam kết chung. LSP không yêu cầu cùng thuật toán, cùng dữ liệu nội bộ hoặc cùng giá trị đầu ra bất kể hoàn cảnh.

### Phương thức thêm trong subtype có được không?

Có. `Dog` có thể có `bark()` dù `Animal` không có. Thêm khả năng riêng không nhất thiết phá LSP, miễn là khi đối tượng được sử dụng như `Animal`, mọi lời hứa `Animal` tiếp tục được giữ. Client cần `bark()` phải sử dụng kiểu/vai trò phù hợp, chứ không nên giả định mọi `Animal` đều sủa.

## 12. Kiểm thử tính thay thế bằng cùng một tập tình huống

Một cách làm thực tế là kiểm thử **hợp đồng chung** trên mọi implementation, sau đó có test riêng cho thuật toán của từng loại.

Với các class của `Demo.java`, thêm phương thức tĩnh sau vào class `Demo` nếu muốn chạy thử:

~~~java
private static void verifyContract(ShippingPolicy policy) {
    Parcel input = new Parcel(1_200, 8);
    ShippingQuote result = policy.quote(input);

    if (result == null || result.feeVnd() < 0) {
        throw new AssertionError("Báo giá không hợp lệ");
    }

    if (input.weightGrams() != 1_200 || input.distanceKm() != 8) {
        throw new AssertionError("Đầu vào bị thay đổi");
    }

    try {
        policy.quote(null);
        throw new AssertionError("Đáng lẽ phải từ chối null");
    } catch (NullPointerException expected) {
        // Hợp đồng yêu cầu lỗi này cho null.
    }
}
~~~

Dùng trong `main`:

~~~java
verifyContract(new StandardShipping());
verifyContract(new ExpressShipping());
System.out.println("Hai implementation vượt qua kiểm tra cơ bản");
~~~

Đây chỉ là một tập kiểm tra tối thiểu. Nó **không chứng minh** công thức tính tiền luôn đúng, không chứng minh độ an toàn đồng thời và không bao quát mọi tình huống biên. Với hệ thống thật, cần thử nhiều trọng lượng/khoảng cách, giới hạn số học, quy tắc làm tròn, lỗi từ provider và điều kiện tương thích nghiệp vụ.

Điểm đáng chú ý: cùng một bộ test kiểm tra những **lời hứa chung**, còn test riêng provider xác nhận những phần **đặc thù implementation**.

## 13. Các dấu hiệu nên xem lại quan hệ “is-a”

| Dấu hiệu | Nguy cơ | Cách cải thiện |
|---|---|---|
| Subclass phải ném `UnsupportedOperationException` cho nhiều method của cha | Subtype không đáp ứng vai trò được hứa | Tách interface nhỏ hoặc đổi hệ phân cấp |
| Class con thêm precondition bất ngờ | Client hợp lệ bị từ chối | Thiết kế lại hợp đồng hoặc phân vai trò |
| Class con bỏ bớt postcondition | Client đọc kết quả sai | Khôi phục cam kết, mở rộng kiểu kết quả hợp lệ |
| Subclass thường kiểm tra/cast về một kiểu cụ thể | Mã dùng phụ thuộc implementation | Tìm abstraction phù hợp, inject vai trò |
| Kế thừa chỉ để lấy vài utility methods | Quan hệ miền nghiệp vụ sai | Composition hoặc utility class |
| Lớp cha cho sửa field mà lớp con phải duy trì invariant chặt hơn | Xung đột quy tắc trạng thái | Giảm setter, ưu tiên hành vi hoặc immutable value |
| Client sử dụng `instanceof` để chọn nhánh cho mọi loại | Thêm subtype phải sửa client | Polymorphism hoặc factory/strategy đúng chỗ |
| Test qua lớp cha thành công, qua lớp con thất bại trái hợp đồng | Vi phạm khả năng thay thế | Sửa implementation hoặc định nghĩa lại abstraction |

Một câu hỏi thiết kế hữu ích: **“Nếu tôi chỉ biết kiểu cha, liệu tôi có thể dùng đối tượng con mà không phải đọc tên class thực tế hoặc thêm ngoại lệ đặc biệt không?”** Nếu thường xuyên phải trả lời “không”, quan hệ subtype cần xem lại.

## 14. Bài tập tự kiểm tra

**Bài 1: cùng đối tượng hay hai đối tượng?**

~~~java
Dog dog = new Dog();
Animal animal = dog;
~~~

Giả sử `Dog extends Animal`. Hỏi có bao nhiêu object được tạo bởi đoạn code và `animal instanceof Dog` trả gì?

**Đáp án:** một object `Dog`; `animal instanceof Dog` là `true`. Upcasting không tạo object mới.

**Bài 2: override và runtime dispatch**

~~~java
class A {
    String name() { return "A"; }
}
class B extends A {
    @Override String name() { return "B"; }
}
A item = new B();
System.out.println(item.name());
~~~

**Đáp án:** `B`, vì `name()` là instance method được override. Đoạn khai báo biến và in kết quả cần đặt trong một phương thức thích hợp.

**Bài 3: một subtype từ chối mọi đầu vào lớn hơn 5 kg dù hợp đồng cha nhận mọi trọng lượng dương. Có hợp lệ không?**

**Đáp án:** Đây là việc siết precondition của subtype. Nếu hợp đồng cha thực sự hứa xử lý mọi trọng lượng dương thì subtype phá khả năng thay thế. Hãy đưa giới hạn vào hợp đồng hoặc mô hình hóa một kết quả không được hỗ trợ.

**Bài 4: `Square extends Rectangle` luôn là sai?**

**Đáp án:** Không thể kết luận chỉ từ tên hai lớp. Với `Rectangle` mutable có `setWidth()` và `setHeight()` độc lập, `Square` khó giữ cả hợp đồng cha lẫn invariant hai cạnh bằng nhau. Với một `Shape` chỉ có `area()`, cả hai có thể triển khai hợp đồng một cách hợp lệ.

**Bài 5: có thể truyền `List<Dog>` cho phương thức nhận `List<Animal>` không?**

**Đáp án:** Không trực tiếp, vì Java generics invariant. Nếu phương thức chỉ cần đọc, cân nhắc `List<? extends Animal>` hoặc cấu trúc generic thích hợp.

**Bài 6: khi nào dùng `implements` tốt hơn `extends`?**

**Gợi ý:** Khi cần mô tả một **vai trò/khả năng chung** nhưng các implementation không có quan hệ kế thừa trạng thái/cài đặt tự nhiên. Ví dụ nhiều chiến lược vận chuyển cùng `implements ShippingPolicy`, còn công thức riêng của từng class.

**Bài 7: một subclass giữ nguyên chữ ký phương thức nhưng âm thầm sửa input object. Có thể gọi là thay thế được không?**

**Đáp án:** Nếu supertype cam kết không sửa đầu vào, thì không. Giữ chữ ký không đủ; side effect là phần có thể quan sát của hợp đồng.

## Cách áp dụng khi xây dựng một cây kiểu

Hãy xác định **hợp đồng được client sử dụng trước**, sau đó kiểm tra mỗi subtype bằng các câu hỏi:

1. **Is-a ở tầng nghiệp vụ:** kiểu con thực sự là một loại/vai trò của kiểu cha, hay chỉ “có” một thành phần thuộc kiểu cha?
2. **Các lời gọi hợp lệ:** khi dùng qua kiểu cha, subtype có chấp nhận những đầu vào mà hợp đồng cha cho phép không?
3. **Kết quả và lỗi:** subtype có giữ các cam kết về kiểu, ý nghĩa, invariant, điều kiện thành công và lỗi không?
4. **Đa hình:** code sử dụng có thể làm việc qua supertype mà không phụ thuộc liên tục vào tên implementation không?
5. **Kiểm chứng:** cùng một tập contract tests có chạy được trên các implementation không?

Một quan hệ `extends`/`implements` hữu ích khi nó cho phép **thay một đối tượng bằng một đối tượng khác đúng vai trò mà vẫn giữ các lời hứa chung**. Nếu cần liên tục thêm ngoại lệ hoặc sửa client theo từng class con, hãy cân nhắc trừu tượng nhỏ hơn, composition hoặc một mô hình kiểu khác phản ánh nghiệp vụ chính xác hơn.