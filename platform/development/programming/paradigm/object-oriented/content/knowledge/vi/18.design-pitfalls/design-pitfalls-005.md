# Lạm dụng ép kiểu và kiểm tra kiểu trong OOP: khi nào nên dùng đa hình?

> **Chủ đề:** OOP → Lỗi thiết kế → Lạm dụng ép kiểu và kiểm tra kiểu.  
> **Mục tiêu:** Nhận diện code smell do lặp lại `instanceof`, downcast hoặc so sánh tên class; phân biệt những kiểm tra kiểu cần thiết với thiết kế phụ thuộc lớp cụ thể; biết refactor sang polymorphism/composition, bảo vệ ranh giới dữ liệu bằng Java 17 và kiểm thử để không đổi sai hành vi.

## 1. Một đoạn mã “biết quá nhiều” về loại đối tượng

Giả sử ứng dụng tính phí vận chuyển theo hai hình thức: tiết kiệm và hỏa tốc. Cả hai đều là lựa chọn vận chuyển, nhưng lớp xử lý đơn hàng lại đi hỏi **đối tượng thực tế thuộc class nào**:

~~~java
// Minh họa lỗi thiết kế; các lớp EconomyOption/ExpressOption
// và hàm calculate... được giả định đã định nghĩa.
long fee(DeliveryOption option, DeliveryRequest request) {
    if (option instanceof EconomyOption) {
        EconomyOption economy = (EconomyOption) option;
        return 12_000L + 2_500L * request.distanceKm();
    } else if (option instanceof ExpressOption) {
        ExpressOption express = (ExpressOption) option;
        return 25_000L + 4_500L * request.distanceKm();
    }
    throw new IllegalArgumentException("Unknown option");
}
~~~

Đoạn này thể hiện *type-checking conditional*: thuật toán nghiệp vụ được chọn bằng cách hỏi subtype của đối tượng rồi thực hiện công thức ngay tại caller. Các biến `economy`/`express` còn không được dùng — phép ép kiểu thực tế không cần thiết.

Nếu sau đó một màn hình dự toán, controller và batch job đều viết lại nhánh tương tự, mỗi lần thêm loại vận chuyển thứ ba phải sửa nhiều nơi. Khả năng “thêm loại mới” phụ thuộc vào việc tìm hết các câu `instanceof` rải rác. **Đó là mùi thiết kế**, không phải vì toán tử `instanceof` bị cấm.

Một câu hỏi hữu ích khi review:

> *Caller đang cần biết đối tượng thuộc lớp nào để quyết định hành vi mà chính đối tượng ấy hoàn toàn có thể chịu trách nhiệm không?*

Nếu câu trả lời là “có”, nên xem xét đưa hành vi vào abstraction và sử dụng **đa hình (polymorphism)**.

## 2. Hiểu đúng ép kiểu và kiểm tra kiểu trong Java

Java là ngôn ngữ **kiểm tra kiểu tĩnh**, nhưng tham chiếu ở kiểu cha/interface có thể trỏ đến đối tượng thuộc subtype cụ thể. Cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Kiểu tĩnh** | Kiểu của biểu thức/biến mà compiler biết | `Animal animal` |
| **Lớp thực tế lúc chạy** | Class của đối tượng đang được tham chiếu | `new Dog()` |
| **Upcasting** | Dùng subtype ở vị trí supertype (thường không cần viết cast) | `Animal a = new Dog();` |
| **Downcasting** | Yêu cầu xem tham chiếu kiểu rộng như kiểu hẹp hơn | `Dog d = (Dog) a;` |
| **`instanceof`** | Kiểm tra tham chiếu có phù hợp một kiểu/pattern tại runtime không | `a instanceof Dog` |
| **Dynamic dispatch** | Chọn implementation của instance method được override lúc chạy | `a.sound()` gọi `Dog.sound()` |

Ví dụ Java 17:

~~~java
interface Animal {
    String sound();
}

final class Dog implements Animal {
    @Override
    public String sound() { return "Gâu"; }

    String fetch() { return "Nhặt bóng"; }
}

final class Cat implements Animal {
    @Override
    public String sound() { return "Meo"; }
}

Animal animal = new Dog(); // Upcast: hợp lệ, không mất đối tượng Dog.
System.out.println(animal.sound()); // "Gâu" nhờ overriding.

// animal.fetch(); // Lỗi biên dịch: Animal không công bố fetch().
if (animal instanceof Dog dog) {
    System.out.println(dog.fetch()); // Pattern matching Java 17.
}
~~~

`animal` vẫn có **kiểu tĩnh `Animal`**, đối tượng thực tế là `Dog`. Upcasting không “cắt” phần Dog ra khỏi object. Nhưng không thể truy cập method riêng của Dog nếu chỉ biết interface Animal, trừ khi thực hiện thu hẹp kiểu có kiểm tra hoặc thiết kế API khác.

### Downcast có thể đúng cú pháp nhưng sai tại runtime

~~~java
Animal animal = new Cat();

// Compiler có thể chấp nhận phép cast từ Animal xuống Dog,
// nhưng đối tượng thật là Cat:
Dog dog = (Dog) animal; // ClassCastException khi chạy.
~~~

`(Dog) animal` không biến `Cat` thành `Dog`. Phép cast tham chiếu chỉ yêu cầu JVM kiểm tra rằng đối tượng đã có phù hợp với kiểu đích không. `instanceof Dog` giúp kiểm tra trước khi dùng một hành vi đặc thù, nhưng **việc kiểm tra thành công cũng không tự tạo ra thiết kế tốt**.

## 3. Những kiểu lạm dụng thường gặp

| Dấu hiệu | Vì sao đáng ngờ | Hướng xử lý |
|---|---|---|
| `if (animal instanceof Dog) ... else if (animal instanceof Cat)` xuất hiện ở nhiều nơi | Caller tự quyết định hành vi thay cho các subtype | Đưa hành vi chung vào interface rồi override |
| `((ConcreteRepo) repository).specialSave(...)` | Caller phụ thuộc lớp triển khai bị che sau interface | Xem lại hợp đồng cần thiết hoặc tách capability rõ ràng |
| So sánh `obj.getClass() == Dog.class` để chọn logic | Gắn chặt với đúng class, không nhận subclass/proxy | Ưu tiên polymorphism; chỉ kiểm tra exact class khi đặc tả đòi hỏi |
| Cast từ `Object` liên tục trong service nghiệp vụ | Dữ liệu bị mất hợp đồng kiểu quá sớm | Generic types, typed DTO, adapter ở boundary |
| `@SuppressWarnings("unchecked")` tràn lan | Che mất bằng chứng kiểm tra kiểu không được bảo đảm | Cô lập API legacy, validate hoặc chuyển sang typed API |
| `switch(typeCode)` lặp lại nhiều lần với các công thức của từng loại | Type code quyết định mọi hành vi thay vì object | Strategy/polymorphism hoặc tổ chức theo capability |
| `catch (ClassCastException)` để thử từng subtype | Dùng exception thay cho mô hình kiểu | Kiểm tra ở boundary, tránh downcast đoán mò |

**Chưa phải mọi trường hợp trong bảng đều là lỗi.** Một `switch` duy nhất để chọn implementation theo cấu hình có thể rất rõ ràng; một `instanceof` để xác thực dữ liệu đầu vào không đáng tin cậy là hợp lý. Vấn đề là **tần suất, vị trí và trách nhiệm** của phép kiểm tra kiểu.

## 4. Refactor đúng trọng tâm: đa hình cho các thuật toán vận chuyển

Thay vì để `Checkout` kiểm tra subtype và chứa công thức từng loại vận chuyển, ta dùng một interface mô tả hành vi cần thiết:

~~~mermaid
flowchart LR
    caller["Client / composition root"] --> checkout["ShippingCheckout"]
    checkout --> port["ShippingPolicy"]
    economy["EconomyShipping"] -.->|implements| port
    express["ExpressShipping"] -.->|implements| port
    caller -.->|chọn implementation| economy
    caller -.->|chọn implementation| express
~~~

Hướng phụ thuộc đáng chú ý: **`ShippingCheckout → ShippingPolicy ← Concrete Shipping`**. Caller chọn strategy khi dựng đối tượng; code tính phí của Checkout không cần biết tên các subtype. Việc chọn strategy có thể nằm ở cấu hình, DI container hoặc một nơi chọn chính sách theo yêu cầu.

### Ví dụ Java 17 đầy đủ, biên dịch và chạy được

Giả định nghiệp vụ demo:

- Mã đơn hàng chỉ gồm `A-Z`, số và dấu gạch ngang.
- Quãng đường nguyên trong khoảng **1–1000 km**.
- Trọng lượng nguyên trong khoảng **1–20.000 g**.
- Tính phí theo **số kilogram làm tròn lên**, không dùng số thập phân tiền tệ để giữ ví dụ tập trung vào thiết kế.
- Đơn vị phí là **VND nguyên**; hai công thức dưới đây chỉ là dữ liệu giả lập, không phải bảng giá vận chuyển thực.

Đặt toàn bộ mã trong **`CastRefactorDemo.java`**:

~~~java
import java.util.Map;
import java.util.Objects;

enum DeliveryTier {
    ECONOMY, EXPRESS
}

record DeliveryRequest(
        String orderId,
        int distanceKm,
        int weightGrams
) {
    DeliveryRequest {
        Objects.requireNonNull(orderId, "orderId");

        if (!orderId.matches("[A-Z0-9-]+")) {
            throw new IllegalArgumentException("Invalid orderId");
        }
        if (distanceKm < 1 || distanceKm > 1_000) {
            throw new IllegalArgumentException("Distance outside 1..1000");
        }
        if (weightGrams < 1 || weightGrams > 20_000) {
            throw new IllegalArgumentException("Weight outside 1..20000");
        }
    }

    int roundedKilograms() {
        // Chặn trên từ record constructor khiến phép cộng an toàn.
        return (weightGrams + 999) / 1_000;
    }
}

// Hợp đồng hành vi: cách tính phí, không yêu cầu caller biết subtype.
interface ShippingPolicy {
    long feeVnd(DeliveryRequest request);
}

final class EconomyShipping implements ShippingPolicy {
    @Override
    public long feeVnd(DeliveryRequest request) {
        Objects.requireNonNull(request);
        return 12_000L
                + 2_500L * request.distanceKm()
                + 2_000L * request.roundedKilograms();
    }
}

final class ExpressShipping implements ShippingPolicy {
    @Override
    public long feeVnd(DeliveryRequest request) {
        Objects.requireNonNull(request);
        return 25_000L
                + 4_500L * request.distanceKm()
                + 5_000L * request.roundedKilograms();
    }
}

record ShippingQuote(String orderId, long feeVnd) {
    ShippingQuote {
        Objects.requireNonNull(orderId, "orderId");
        if (feeVnd < 0) {
            throw new IllegalArgumentException("Negative shipping fee");
        }
    }
}

final class ShippingCheckout {
    private final ShippingPolicy policy;

    ShippingCheckout(ShippingPolicy policy) {
        this.policy = Objects.requireNonNull(policy, "policy");
    }

    ShippingQuote quote(DeliveryRequest request) {
        Objects.requireNonNull(request, "request");
        return new ShippingQuote(
                request.orderId(), policy.feeVnd(request));
    }
}

public class CastRefactorDemo {
    public static void main(String[] args) {
        // Chọn implementation ở composition root, không chọn bằng
        // instanceof/downcast bên trong ShippingCheckout.
        Map<DeliveryTier, ShippingPolicy> policies = Map.of(
                DeliveryTier.ECONOMY, new EconomyShipping(),
                DeliveryTier.EXPRESS, new ExpressShipping()
        );

        DeliveryRequest request =
                new DeliveryRequest("ORD-7", 4, 1_500);

        for (DeliveryTier tier : DeliveryTier.values()) {
            ShippingPolicy selected = policies.get(tier);
            ShippingCheckout checkout = new ShippingCheckout(selected);

            ShippingQuote quote = checkout.quote(request);
            System.out.println(
                    tier + " -> " + quote.feeVnd() + " VND");
        }
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac CastRefactorDemo.java
java CastRefactorDemo
~~~

Kết quả:

~~~text
ECONOMY -> 26000 VND
EXPRESS -> 53000 VND
~~~

Kiểm tra tay với khoảng cách **4 km**, trọng lượng **1.500 g** (làm tròn thành **2 kg**):

| Chính sách | Công thức ví dụ | Phí |
|---|---|---:|
| Economy | 12.000 + 2.500 × 4 + 2.000 × 2 | 26.000 VND |
| Express | 25.000 + 4.500 × 4 + 5.000 × 2 | 53.000 VND |

Lưu ý `DeliveryRequest` **giới hạn khoảng dữ liệu** để các phép nhân/cộng `long` trên không overflow trong phạm vi demo. Trong ứng dụng có biên độ số lớn hoặc công thức từ dữ liệu ngoài, cần kiểm soát overflow rõ ràng (`Math.multiplyExact`, `Math.addExact` hoặc kiểu tiền tệ phù hợp).

### Vì sao việc refactor thực sự giải quyết vấn đề?

Ở phiên bản ban đầu, **caller sở hữu toàn bộ lựa chọn subtype và công thức tính tiền**. Sau refactor:

1. `ShippingPolicy` nói rõ **một khả năng chung**: tính phí cho `DeliveryRequest`.
2. Mỗi implementation tự sở hữu **công thức riêng**.
3. `ShippingCheckout` giữ vai trò điều phối: hỏi policy và tạo kết quả. Không cần `instanceof`, cast, `getClass()` hoặc `switch` trên class.
4. `Map<DeliveryTier, ShippingPolicy>` trong `main` chỉ là **điểm lựa chọn chính sách**, không dàn logic ra toàn ứng dụng.
5. Nếu thêm chính sách `SameDayShipping`, chủ yếu phải thêm implementation và đăng ký nó; `ShippingCheckout.quote()` không bị sửa.

**Đổi sang polymorphism không tự bảo đảm kết quả đúng.** Mỗi implementation vẫn phải tuân thủ hợp đồng: trả phí không âm và không có side effect bất ngờ nếu đây là hàm báo giá thuần. `ShippingQuote` từ chối phí âm; test cần kiểm tra cả công thức.

## 5. So sánh đường đi trước và sau refactor

~~~mermaid
flowchart TB
    subgraph Before["Trước: caller phải phân loại"]
      B0["Checkout nhận DeliveryOption"] --> B1{"instanceof ?"}
      B1 -->|Economy| B2["downcast / công thức Economy"]
      B1 -->|Express| B3["downcast / công thức Express"]
      B1 -->|khác| B4["Unsupported type"]
    end

    subgraph After["Sau: chọn policy và ủy quyền"]
      A0["Composition root chọn policy"] --> A1["Checkout nhận ShippingPolicy"]
      A1 --> A2["policy.feeVnd(request)"]
      A2 --> A3["JVM dispatch tới implementation"]
    end
~~~

Khi nhiều nơi đều cần “làm X khác nhau theo loại Y”, lặp `instanceof` có thể là dấu hiệu **hợp đồng Y còn thiếu hành vi X**. Song không phải cứ thấy nhánh thì bắt buộc thêm một method vào base class: cần xét liệu hành vi có thực sự thuộc trách nhiệm của Y, hay thuộc một dịch vụ/cấu trúc khác.

## 6. `instanceof` khi nào là lựa chọn đúng?

### 6.1. Kiểm tra dữ liệu tại ranh giới không tin cậy

Nếu một thư viện legacy hoặc API nhận dữ liệu cho ta `Object` hoặc `List<?>`, **cần xác nhận hình dạng dữ liệu trước khi chuyển sang miền có kiểu rõ ràng**. Đây là kiểm tra kiểu để bảo vệ hợp đồng, không phải vòng phân nhánh nghiệp vụ rải rác.

Ví dụ cần lấy danh sách nhãn kiểu chuỗi từ một đối tượng không chắc chắn:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class InputParser {
    static List<String> requireTags(Object input) {
        // Java 17: pattern matching for instanceof.
        if (!(input instanceof List<?> rawTags)) {
            throw new IllegalArgumentException("Expected a list");
        }

        List<String> tags = new ArrayList<>();
        for (Object raw : rawTags) {
            if (!(raw instanceof String tag) || tag.isBlank()) {
                throw new IllegalArgumentException(
                        "Expected nonblank String element");
            }
            tags.add(tag);
        }

        return List.copyOf(tags);
    }
}
~~~

Ví dụ sử dụng:

~~~java
List<String> tags = InputParser.requireTags(
        List.of("java", "oop")); // ["java", "oop"]

// InputParser.requireTags(List.of("java", 42));
// Ném IllegalArgumentException, không cố ép cả List thành List<String>.
~~~

Đây là một bước chuyển đổi *Object → typed value*. Sau bước này, phần nghiệp vụ nhận `List<String>` và **không cần kiểm tra từng phần tử thêm lần nữa** nếu không có raw/unchecked operation phá hợp đồng. Lưu ý `List.copyOf` trả một collection không thể sửa qua API và không thay đổi theo nguồn, nhưng không phải deep copy cho phần tử mutable; ở đây `String` là immutable.

### 6.2. Một subtype có năng lực đặc biệt thực sự cần thiết

~~~java
interface Printable {
    void print();
}

interface Scannable {
    void scan();
}

void useDevice(Printable device) {
    device.print();

    if (device instanceof Scannable scanner) {
        scanner.scan();
    }
}
~~~

Trong ví dụ giả lập này, scan là một **khả năng tùy chọn** khác với print. Kiểm tra capability `Scannable` có thể phù hợp hơn ép mọi `Printable` phải có `scan()` rồi ném `UnsupportedOperationException`. Đây không nhất thiết là code smell nếu hành vi tùy chọn được yêu cầu thực sự. Ngược lại, nếu mọi nơi đều liên tục kiểm tra `Scannable`, hãy xem ranh giới API có nên yêu cầu đối tượng `Scannable` ngay từ đầu hay không.

### 6.3. Loại dữ liệu đóng, cần xử lý từ bên ngoài

Một thao tác như **render báo cáo** cho một cấu trúc AST/biểu thức có nhiều biến thể dữ liệu có thể cần phân loại node ở một điểm tập trung. Nếu tập subtype được **cố định và kiểm soát**, Java 17 hỗ trợ `sealed interface` và `instanceof` pattern; đây là lựa chọn hợp lý khi không muốn các node phải biết mọi dạng đầu ra.

~~~java
sealed interface Expr permits Literal, Sum {}

record Literal(int value) implements Expr {}

record Sum(Expr left, Expr right) implements Expr {}

static int evaluate(Expr expr) {
    if (expr instanceof Literal literal) {
        return literal.value();
    }
    if (expr instanceof Sum sum) {
        return Math.addExact(
                evaluate(sum.left()), evaluate(sum.right()));
    }
    throw new IllegalStateException("Unexpected Expr: " + expr);
}
~~~

Đây là minh họa cho Java 17 trong một lớp khai báo phương thức `evaluate`. `Sum` cho phép cây biểu thức phức tạp; `Math.addExact` báo overflow nếu kết quả vượt `int`. Việc loại biểu thức bị giới hạn bởi `sealed` khiến nhánh xử lý tập trung và có thể được kiểm thử đầy đủ.

Lưu ý quan trọng: **pattern matching trong `switch` trên kiểu ở Java 17 còn là preview feature**, không nên trình bày nó như một tính năng không cần cờ của Java 17. Đoạn trên chỉ dùng `instanceof` pattern matching, có thể biên dịch bằng JDK 17 thông thường. Với các Java version mới hơn, có thêm lựa chọn về pattern switch.

**Trade-off của visitor/type dispatch:** Khi liên tục thêm *loại dữ liệu*, hành vi phương thức trên interface/subclass thường dễ mở rộng hơn; khi liên tục thêm *phép toán* trên một họ dữ liệu tương đối đóng, một visitor hoặc bộ xử lý riêng có thể phù hợp. Chọn theo chiều thay đổi thực tế, không loại bỏ mọi kiểm tra kiểu bằng mọi giá.

## 7. Ép kiểu xuống implementation: vì sao dễ phá abstraction?

Xét service nhận một repository qua interface:

~~~java
interface OrderRepository {
    void save(String id);
}

final class JdbcOrderRepository implements OrderRepository {
    @Override
    public void save(String id) { /* ... */ }

    void flushJdbcBatch() { /* ... */ }
}

void process(OrderRepository repository) {
    repository.save("ORD-1");

    // Code smell nếu caller mặc định repo luôn là JDBC:
    ((JdbcOrderRepository) repository).flushJdbcBatch();
}
~~~

Nếu truyền một repository dùng bộ nhớ hoặc mock, `process` có thể ném `ClassCastException`. Dù có thêm `if (repository instanceof JdbcOrderRepository jdbc)`, service vẫn biết chi tiết JDBC và hành vi giữa các adapter trở nên không nhất quán.

Các hướng giải quyết phụ thuộc mục đích:

- Nếu `flush` là một phần hợp đồng mà **mọi repository cần bảo đảm**, cân nhắc đưa nó vào abstraction một cách có chủ đích.
- Nếu flush chỉ là chi tiết tối ưu của JDBC, **giữ bên trong adapter**; người gọi không cần biết.
- Nếu có một **khả năng tùy chọn**, định nghĩa interface capability riêng và chỉ yêu cầu nó tại nơi thực sự cần.
- Nếu workflow chỉ hỗ trợ JDBC một cách có chủ ý, khai báo rõ `JdbcOrderRepository` tại boundary thay vì quảng cáo một interface đa hình không đúng sự thật.

**Không** thêm method vào interface chỉ để tránh viết `instanceof` khi method ấy không phù hợp với các implementation khác: cách đó dễ vi phạm Interface Segregation Principle hoặc Liskov Substitution Principle.

## 8. Lạm dụng cast trong generics và collection

Java generics giúp ngăn nhiều lỗi tại compile time. Hãy giữ thông tin kiểu đi qua API:

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> codes = new ArrayList<>();
codes.add("ORD-1");

// codes.add(100); // Lỗi compile time: 100 không phải String.
String first = codes.get(0);
~~~

Khi dùng raw type, việc bảo vệ có thể bị vô hiệu:

~~~java
List<String> codes = new ArrayList<>();
List raw = codes; // Raw type, compiler phát cảnh báo.
raw.add(123);     // Unchecked call, không an toàn.

// Có thể ném ClassCastException ở đây:
String code = codes.get(0);
~~~

Một kiểu “sửa lỗi” sai thường gặp là:

~~~java
// KHÔNG NÊN: Cast này không kiểm tra từng phần tử của list.
// List<String> names = (List<String>) (List<?>) unknownList;
~~~

Do **type erasure**, Java không thể kiểm tra runtime object là `List<String>` bằng `instanceof List<String>`. `instanceof List<?>` chỉ xác nhận “đây là một List với type argument không biết”; muốn xác thực từng phần tử phải duyệt dữ liệu như `InputParser.requireTags`.

| Tình huống | Cách làm tốt hơn |
|---|---|
| Method trả `Object` nhưng thực chất luôn trả `User` | Sửa chữ ký trả `User`, hoặc `Optional<User>` nếu có thể vắng |
| Một registry chứa nhiều kiểu object | Dùng typed key/`Class<T>` API có kiểm tra tập trung |
| Legacy API buộc trả raw `List` | Chuyển đổi/validate một lần ở adapter; đẩy phần còn lại thành typed API |
| Dùng cast xuống subtype để truy cập method lặp lại | Đưa hành vi chung vào interface hoặc capability phù hợp |
| Cast “cho compiler im lặng” | Tìm lý do mất thông tin kiểu; không bọc warning tràn lan |

### Khi `Class<T>.cast` là công cụ đúng

Một adapter có thể biết `Class<T>` từ cấu hình nhưng chỉ nhận `Object` từ một API động. Có thể kiểm tra theo token loại:

~~~java
final class TypedBoundary {
    static <T> T require(Object value, Class<T> expected) {
        if (!expected.isInstance(value)) {
            throw new IllegalArgumentException(
                    "Expected " + expected.getName());
        }
        return expected.cast(value);
    }
}

String text = TypedBoundary.require("hello", String.class);
~~~

`Class.cast` chỉ kiểm tra **runtime class tương thích**. Nó không biến `List.class` thành một bộ xác nhận phần tử kiểu `String`, và không bảo đảm giá trị đáp ứng quy tắc nghiệp vụ (ví dụ chuỗi không rỗng, ID hợp lệ, quyền được cấp).

## 9. Nhầm lẫn giữa kiểm tra kiểu và kiểm tra trạng thái

Nhiều nhánh `instanceof` thực chất đang cố trả lời câu hỏi về **trạng thái** thay vì kiểu class. Ví dụ:

~~~java
if (order instanceof PaidOrder) {
    ship(order);
}
~~~

Điều này có thể hợp lý nếu `PaidOrder` là một kiểu riêng và toàn bộ hệ thống thực sự dùng *typestate* an toàn, nhưng thường trạng thái là một thuộc tính hoặc invariant nghiệp vụ như `OrderStatus.PAID`. Đừng tạo subtype `CreatedOrder`, `PaidOrder`, `CancelledOrder` chỉ để thay mọi enum, nếu các đối tượng có vòng đời thay đổi trạng thái và hệ thống phải cast qua lại khó quản lý.

Câu hỏi cần phân biệt:

| Câu hỏi thực sự | Công cụ ưu tiên |
|---|---|
| Đối tượng biết thực hiện hành vi của mình thế nào? | Polymorphism/Strategy |
| Dữ liệu chưa tin cậy có kiểu phù hợp không? | `instanceof`/type token/validation tại boundary |
| Đơn hàng đang ở trạng thái nghiệp vụ nào? | State model, domain method, enum có điều kiện chuyển |
| Client cần một khả năng tùy chọn? | Capability interface hoặc hợp đồng rõ |
| Framework cần nạp plugin được chỉ định runtime? | Registry/factory và kiểm tra kiểu tập trung |
| Cần xử lý một cấu trúc dữ liệu đóng theo nhiều phép toán? | Visitor/central dispatch/sealed hierarchy tùy chiều thay đổi |

Lạm dụng ép kiểu thường bắt nguồn từ **API chưa diễn đạt đúng điều caller cần**, không chỉ từ một lỗi cú pháp.

## 10. Kiểm thử sau refactor: hợp đồng quan trọng hơn tên class

Mục tiêu kiểm thử: khi chọn implementation khác, `ShippingCheckout` vẫn dùng cùng một hợp đồng; không có nhánh phụ thuộc class cụ thể.

Ví dụ với JUnit Jupiter 5, cùng package với `CastRefactorDemo.java`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class ShippingCheckoutTest {
    private static final DeliveryRequest REQUEST =
            new DeliveryRequest("ORD-7", 4, 1_500);

    @Test
    void economyAndExpressFollowTheirOwnAlgorithms() {
        ShippingQuote economy = new ShippingCheckout(
                new EconomyShipping()).quote(REQUEST);
        ShippingQuote express = new ShippingCheckout(
                new ExpressShipping()).quote(REQUEST);

        assertEquals(26_000L, economy.feeVnd());
        assertEquals(53_000L, express.feeVnd());
        assertEquals("ORD-7", economy.orderId());
    }

    @Test
    void anotherImplementationWorksWithoutCast() {
        ShippingPolicy promotional = request -> 0L;

        ShippingQuote quote =
                new ShippingCheckout(promotional).quote(REQUEST);

        assertEquals(0L, quote.feeVnd());
    }

    @Test
    void invalidRequestIsRejectedBeforePricing() {
        assertThrows(IllegalArgumentException.class,
                () -> new DeliveryRequest("ORD-7", 0, 1_500));
        assertThrows(IllegalArgumentException.class,
                () -> new DeliveryRequest("ORD-7", 4, -1));
    }

    @Test
    void policyBreakingTheNonnegativeContractIsRejected() {
        ShippingPolicy broken = request -> -100L;

        assertThrows(IllegalArgumentException.class,
                () -> new ShippingCheckout(broken).quote(REQUEST));
    }
}
~~~

Các test cần dependency `org.junit.jupiter:junit-jupiter` và JUnit test runner phù hợp. Test thứ hai dùng **lambda** vì `ShippingPolicy` là functional interface (chỉ có một abstract method), cho thấy Context không quan tâm object có phải `EconomyShipping`/`ExpressShipping` hay không.

### Bổ sung kiểm thử contract dùng chung

Khi số implementation tăng, nên chạy một bộ kiểm thử hợp đồng cho mọi policy:

- Với request hợp lệ, kết quả không âm, không gây tác dụng phụ ngoài mong đợi.
- Với cùng đầu vào và cấu hình ổn định, kết quả dự đoán được theo contract.
- Biên của khoảng cách và trọng lượng, gồm thời điểm làm tròn lên kg.
- Mỗi biến thể có giá trị mong đợi cụ thể, không chỉ kiểm tra `fee >= 0`.

**Đừng nhầm:** unit test passing chưa chứng minh mọi tình huống thực tế; nếu chính sách tính tiền còn dựa vào database, tỷ giá, chính sách thời gian hay mạng, hãy có integration test phù hợp.

## 11. Chọn kỹ thuật refactor theo mức độ thay đổi

Không có một giải pháp duy nhất cho mọi cây `if (x instanceof Y)`:

| Hiện trạng | Hướng refactor | Lý do |
|---|---|---|
| Caller có nhiều nhánh chọn **cùng một hành vi** tùy subtype | **Replace Conditional with Polymorphism** | Hành vi nằm tại object chịu trách nhiệm |
| Mỗi loại có một thuật toán và cần chọn trong runtime | **Strategy + DI/composition** | Hoán đổi hành vi mà Context không biết class cụ thể |
| Chỉ một nơi phân nhánh để dựng implementation | Factory/registry hoặc một `switch` ở composition root | Lựa chọn tập trung không lan vào nghiệp vụ |
| Khối `Object` từ API legacy | **Boundary parser/adapter** | Kiểm tra một lần rồi dùng typed value |
| Nhiều thao tác trên một tập loại dữ liệu đóng | Visitor/central dispatch | Tránh nhồi hành vi không tự nhiên vào data type |
| Cần gọi khả năng bổ sung không phải mọi subtype có | Tách capability interface | Không ép mọi implementation hỗ trợ method vô nghĩa |

**Lưu ý về SOLID:** Đổi conditional thành polymorphism có thể giúp OCP và DIP, nhưng phải tôn trọng **LSP**: mọi implementation phải thực hiện đúng hợp đồng chung. Một interface mà một implementation liên tục ném `UnsupportedOperationException` có thể chỉ là che giấu conditional bằng abstraction kém.

### Quy trình sửa mã đang vận hành

1. **Liệt kê nơi kiểm tra kiểu**: tìm `instanceof`, cast xuống implementation, `getClass()`, các `switch` theo type code. Xem chúng đang kiểm tra type, capability, state hay format.
2. **Ghi nhận hành vi**: test giá trị, đường lỗi, side effect, thứ tự xử lý và trường hợp “loại không hỗ trợ” trước khi sửa. Đừng vô tình bỏ exception cần thiết.
3. **Xác định một hợp đồng thực sự chung**: chọn tên method theo nhu cầu nghiệp vụ, quy định input/output, null policy và failure mode.
4. **Đưa hành vi về nơi sở hữu**: override ở subtype hoặc bọc các thuật toán trong Strategy độc lập; tránh nhập logic hạ tầng vào domain object.
5. **Giới hạn điểm lựa chọn**: composition root/registry nhận type code từ config và tạo/cấp implementation.
6. **Dọn branch/cast dư thừa**: xóa các nhánh đã được thay bằng dispatch; nếu còn cast thì nêu rõ vì sao cần.
7. **Kiểm tra thay đổi với test**: chạy cả unit test lẫn integration test liên quan; theo dõi hiệu năng/GC nếu đổi cơ chế dispatch trong hot path.
8. **Đánh giá lại độ đơn giản**: nếu refactor tạo nhiều lớp hơn lợi ích đạt được, một conditional nhỏ, tập trung và ổn định có thể thích hợp hơn.

## 12. Khi nào KHÔNG cần refactor mọi phép `instanceof`?

Không nên áp dụng mệnh đề “mã OOP tốt tuyệt đối không có `instanceof`”. Những tình huống sau có thể rất chính đáng:

- Đọc dữ liệu không đáng tin từ plugin/JSON/legacy API và kiểm tra type trước khi tạo domain object.
- Dùng pattern matching cho một `sealed` hierarchy ở **một** bộ phân tích/diễn giải có chủ đích.
- Phát hiện capability tùy chọn mà interface cơ sở không có lý do phải hỗ trợ.
- Viết infrastructure code như serializer, persistence adapter, middleware, debugger, nơi phân loại dữ liệu là công việc chính.
- Tại composition root, quyết định một implementation từ enum/config. Dùng `switch` để chọn một lần không đồng nghĩa với vi phạm OOP.

Ngược lại, nếu 15 nơi trong hệ thống phải biết `Dog`, `Cat`, `Bird` chỉ để gọi hành vi “phát âm thanh”, đó là vấn đề cần giải quyết. **Đánh giá nên dựa trên mức phụ thuộc và rủi ro thay đổi**, không dựa vào một luật cấm cú pháp.

## 13. Bài tập thực hành: thay type-checking bằng polymorphism

Một hệ thống có các loại tài liệu:

~~~java
interface Document {}

final class PdfDocument implements Document {
    final int pages;
    PdfDocument(int pages) { this.pages = pages; }
}

final class TextDocument implements Document {
    final int characters;
    TextDocument(int characters) { this.characters = characters; }
}

class DocumentAnalyzer {
    int workload(Document document) {
        if (document instanceof PdfDocument pdf) {
            return pdf.pages * 5;
        }
        if (document instanceof TextDocument text) {
            return text.characters / 100;
        }
        throw new IllegalArgumentException("Unsupported document");
    }
}
~~~

Yêu cầu:

1. Xác định **nhánh type-checking** và lý do lớp `DocumentAnalyzer` phụ thuộc hai implementation.
2. Đưa hành vi hợp lý vào hợp đồng `Document.workload()` hoặc tạo `WorkloadStrategy`, giải thích vì sao chọn cách đó.
3. Thêm `SpreadsheetDocument` với cách tính workload mới mà không sửa caller hiện có.
4. Bổ sung validation cho `pages` và `characters`; tránh overflow khi nhân `pages * 5` nếu input quá lớn.
5. Viết unit test cho ba loại và một test thực hiện `analyzer.workload(document)` qua interface chung.
6. Mở rộng yêu cầu: nếu thêm 10 phép phân tích độc lập khác trên ba loại tài liệu, cân nhắc tại sao một visitor/operation riêng có thể hợp lý hơn nhồi 10 method vào `Document`.
7. Chỉ ra một trường hợp `instanceof` vẫn hợp lệ trong cùng hệ thống, chẳng hạn kiểm tra object đến từ plugin không tin cậy trước khi chuyển sang `Document` có hợp đồng.

### Tự kiểm tra kiến thức

1. Vì sao `Animal a = new Dog()` không làm `Dog` mất những method riêng?
2. Lệnh `(Dog) a` có thay class thực tế của object không?
3. `instanceof` lặp khắp các use case thường tiết lộ điều gì về hợp đồng của chúng?
4. Khi nào kiểm tra `Class.isInstance(...)` là an toàn và có ích?
5. Vì sao `(List<String>) someRawList` không chứng minh mọi phần tử là `String`?
6. Khác nhau giữa `getClass() == T.class` và `instanceof T` khi có subclass?
7. `sealed interface` và mô hình visitor thích hợp khi nào?
8. Thay conditional bằng polymorphism có tự loại bỏ lỗi nghiệp vụ và vi phạm LSP không?
9. Tại sao một `switch` duy nhất ở composition root có thể tốt hơn một hệ thống factory class quá phức tạp?

**Kết luận:** Lạm dụng ép kiểu và kiểm tra kiểu là dấu hiệu **caller phải biết quá nhiều về class cụ thể để ra quyết định nghiệp vụ**. Với hành vi có hợp đồng chung, hãy đặt hành vi ở đối tượng/strategy và dùng polymorphism; với dữ liệu chưa biết kiểu, hãy **kiểm tra tập trung tại boundary**, rồi chuyển sớm về những kiểu rõ ràng. Không cấm `instanceof` hay cast theo khẩu hiệu — hãy dùng chúng ở **đúng trách nhiệm, đúng tầng và đúng phạm vi**.