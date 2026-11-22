# Tạo functional interface riêng khi cần hợp đồng nghiệp vụ rõ nghĩa

## 1. Vấn đề: một hàm đúng kiểu chưa chắc diễn đạt đúng ý nghĩa

Java cung cấp nhiều functional interface sẵn có trong **java.util.function** như **Predicate<T>**, **Function<T,R>**, **Consumer<T>**, **Supplier<T>**, **UnaryOperator<T>**, **BiFunction<T,U,R>**. Chúng rất tiện khi muốn truyền **hành vi** vào phương thức, dùng lambda và method reference thay vì tạo lớp ẩn danh.

Ví dụ, đoạn mã sau diễn đạt quy tắc chung “đơn hàng nào thỏa điều kiện?”:

~~~java
Predicate<Order> freeShipping = order ->
        order.paid()
        && order.domestic()
        && order.subtotalCents() >= 50_000L;
~~~

Đây là **đoạn minh họa**, giả định có kiểu **Order** cùng các accessor được gọi và import **java.util.function.Predicate**.

Cú pháp này hợp lệ, ngắn và hoàn toàn có thể là lựa chọn tốt. Nhưng với một API nghiệp vụ lớn, tên **Predicate<Order>** chỉ cho biết “hàm nhận Order, trả boolean”. Nó chưa nói rõ đây là quy tắc **đủ điều kiện miễn phí vận chuyển**, liệu có được kết hợp với quy tắc khác, input nào được phép, hoặc điều gì phải được bảo đảm khi trả **true**.

Khi ý nghĩa nghiệp vụ là một phần quan trọng của **hợp đồng API**, ta có thể đặt tên riêng:

~~~java
@FunctionalInterface
interface FreeShippingRule {
    boolean qualifies(Order order);
}
~~~

Đây là **định nghĩa interface minh họa**, không phải chương trình độc lập. Cả **Predicate<Order>** lẫn **FreeShippingRule** đều là kiểu nhận một Order và trả boolean, nhưng kiểu thứ hai tự nói rõ **mục đích** của hành vi. Người đọc thấy **rule.qualifies(order)** sẽ hiểu câu hỏi nghiệp vụ trực tiếp hơn **predicate.test(order)**.

**Không cần tạo functional interface cho mọi lambda.** Tạo kiểu riêng có chi phí: thêm API phải duy trì, thêm tên phải học, có thể phải viết adapter khi tương tác với thư viện dùng các kiểu chuẩn. Chỉ làm vậy khi tên, miền dữ liệu, cách kết hợp, kiểu kết quả hoặc quy tắc lỗi đem lại giá trị cụ thể cho người sử dụng.

## 2. Functional interface là gì?

Một **functional interface** là interface có **một phương thức trừu tượng chức năng** (single abstract method, thường gọi là **SAM**). Java có thể chuyển biểu thức lambda hoặc method reference thành một thể hiện của interface đó khi có **target type** phù hợp.

Ví dụ:

~~~java
@FunctionalInterface
interface FreeShippingRule {
    boolean qualifies(Order order);
}
~~~

Ở đây:

- **@FunctionalInterface** là annotation khuyến nghị: yêu cầu trình biên dịch kiểm tra interface vẫn phù hợp với quy tắc functional interface. Annotation không tự tạo phương thức, không thay đổi cách lambda hoạt động; một interface đủ điều kiện vẫn có thể là functional interface khi không ghi annotation.
- **boolean qualifies(Order order)** là SAM: tên có ý nghĩa miền nghiệp vụ, tham số thể hiện đối tượng được đánh giá và kiểu trả về là một quyết định yes/no.
- Java suy luận kiểu tham số lambda từ ngữ cảnh: **FreeShippingRule rule = order -> order.paid();**; không cần khai báo **(Order order)** nếu trình biên dịch suy ra được.

Functional interface **được phép có các phương thức default, static và private**; chúng không phải là các phương thức abstract chức năng bổ sung. Các phương thức public tương ứng với phương thức của **Object** (như **equals(Object)**) không tính thành nhiều SAM độc lập theo quy tắc của Java. Ngược lại, hai phương thức abstract không liên quan như **qualifies(...)** và **explain(...)** sẽ làm định nghĩa mất tính functional; annotation giúp phát hiện lỗi khi biên dịch.

Ví dụ về lỗi thiết kế:

~~~java
@FunctionalInterface
interface BrokenRule {
    boolean qualifies(Order order);
    String explain(Order order);
}
~~~

Đây là **ví dụ cố ý không biên dịch**: interface có hai phương thức abstract riêng. Nếu cần cả quyết định và lý do, hãy cân nhắc cho **một phương thức abstract** trả về đối tượng kết quả chứa đầy đủ thông tin, hoặc tổ chức API thành các vai trò riêng.

**SAM là ràng buộc về hình dạng kiểu**, không phải bảo đảm hàm thuần (pure), bất biến, thread-safe hay không có ngoại lệ. Một lambda vẫn có thể đọc trạng thái dùng chung, gọi mạng, ghi cơ sở dữ liệu hoặc ném exception. Hợp đồng hành vi phải được viết và kiểm tra riêng.

## 3. Khi nào nên dùng interface có sẵn?

Các kiểu chuẩn phù hợp nếu **hình dạng hàm đã đủ nói rõ mục đích** trong ngữ cảnh:

| Kiểu chuẩn | Phương thức chính | Bài toán phổ biến |
| --- | --- | --- |
| **Predicate<T>** | boolean test(T) | Kiểm tra điều kiện để lọc |
| **Function<T,R>** | R apply(T) | Biến đổi một giá trị |
| **Consumer<T>** | void accept(T) | Thực hiện hành động với đầu vào |
| **Supplier<T>** | T get() | Cung cấp giá trị khi cần |
| **UnaryOperator<T>** | T apply(T) | Chuyển đổi giá trị nhưng giữ cùng kiểu |
| **Comparator<T>** | int compare(T,T) | So sánh thứ tự hai đối tượng |
| **BiFunction<T,U,R>** | R apply(T,U) | Kết hợp hai đầu vào thành một kết quả |

Ví dụ nội bộ đơn giản:

~~~java
List<String> names = List.of("Lan", "Minh", "An");
List<String> shortNames = names.stream()
        .filter(name -> name.length() <= 3)
        .toList();
~~~

Đây là **đoạn minh họa bên trong phương thức**, giả định đã import **java.util.List**. Việc lọc chuỗi ngắn không nhất thiết cần tự định nghĩa interface **ShortNamePredicate**: ý nghĩa đã nằm ngay ở lambda và chỗ sử dụng **filter**.

**Ưu tiên kiểu chuẩn** khi: hàm chỉ dùng cục bộ, có một phép biến đổi chung, không có ràng buộc riêng cần được kiểm soát, và hệ sinh thái đang giao tiếp bằng kiểu chuẩn. Sử dụng loại chuyên biệt cho primitive như **IntPredicate**, **ToLongFunction<T>** khi cần thiết để giảm boxing và nêu rõ kiểu dữ liệu.

**Cân nhắc kiểu riêng** khi: nhiều phần của hệ thống sử dụng cùng khái niệm nghiệp vụ; API công khai phải truyền một vai trò riêng; chữ ký generic che khuất ý nghĩa; cần method có tên phù hợp nghiệp vụ; cần quy tắc kết hợp hoặc ngoại lệ được định nghĩa thống nhất; hoặc cần trả về kiểu kết quả phong phú hơn boolean.

## 4. Ví dụ Java 17: hợp đồng đủ điều kiện miễn phí vận chuyển

Ta có các quy tắc: đơn hàng **đã thanh toán**, **giao nội địa** và **tổng tiền hàng ít nhất 50.000 đơn vị nhỏ nhất của tiền tệ** thì đủ điều kiện miễn phí vận chuyển. Mỗi điều kiện là một quy tắc độc lập, các điều kiện phải đồng thời đúng.

Tạo tệp **ShippingRulesDemo.java**:

~~~java
import java.util.List;
import java.util.Objects;

record Order(String id, long subtotalCents, boolean paid, boolean domestic) {
    Order {
        Objects.requireNonNull(id, "id");
        if (subtotalCents < 0) {
            throw new IllegalArgumentException(
                    "subtotalCents must be non-negative");
        }
    }
}

@FunctionalInterface
interface FreeShippingRule {
    /**
     * Chỉ đánh giá đơn hàng không null.
     * true nghĩa là đơn thỏa điều kiện miễn phí vận chuyển.
     */
    boolean qualifies(Order order);

    default FreeShippingRule and(FreeShippingRule other) {
        Objects.requireNonNull(other, "other");
        return order -> this.qualifies(order) && other.qualifies(order);
    }
}

public class ShippingRulesDemo {
    public static void main(String[] args) {
        FreeShippingRule paid = Order::paid;
        FreeShippingRule domestic = Order::domestic;
        FreeShippingRule minimumSubtotal =
                order -> order.subtotalCents() >= 50_000L;

        FreeShippingRule eligible = paid
                .and(domestic)
                .and(minimumSubtotal);

        List<Order> orders = List.of(
                new Order("A", 60_000L, true, true),
                new Order("B", 75_000L, true, false),
                new Order("C", 20_000L, true, true),
                new Order("D", 90_000L, false, true)
        );

        for (Order order : orders) {
            System.out.println(order.id() + ": "
                    + eligible.qualifies(order));
        }

        long count = orders.stream()
                .filter(eligible::qualifies)
                .count();

        System.out.println("Eligible orders: " + count);
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 ShippingRulesDemo.java
java ShippingRulesDemo
~~~

Đầu ra:

~~~text
A: true
B: false
C: false
D: false
Eligible orders: 1
~~~

**Điểm học từ ví dụ:**

1. **FreeShippingRule** là một khái niệm miền nghiệp vụ. Khả năng dùng lambda được quyết định bởi **một SAM**, không phụ thuộc tên interface.
2. **Order::paid** và **Order::domestic** là method reference phù hợp chữ ký **Order → boolean** của **qualifies(Order)**.
3. **and(...)** là **default method**. Nó thêm cách kết hợp quy tắc nhưng không tạo SAM thứ hai, nên **FreeShippingRule** vẫn là functional interface.
4. Toán tử **&&** có **short-circuit**: nếu quy tắc bên trái trả false, quy tắc bên phải không được đánh giá. Đây là hành vi chủ đích của phép kết hợp.
5. **eligible::qualifies** tương thích với **Predicate<Order>** mà **Stream.filter** yêu cầu. Ta không cần viết adapter phức tạp để dùng lại trong Stream.
6. **subtotalCents** dùng long với quy ước đơn vị tiền nhỏ nhất trong ví dụ; quy định tiền tệ thực tế, thuế, giảm giá, phí vận chuyển và việc làm tròn phải được xác định rõ ở mức hợp đồng nghiệp vụ.

**Hợp đồng không-null:** ví dụ quy định **Order** không được null khi gọi **qualifies**. Bản thân interface không tự kiểm tra điều kiện đó cho mọi lambda; caller cần tuân thủ hoặc một lớp biên (boundary) phải kiểm tra. Phương thức default kiểm tra **other** ngay khi gọi **and**, tránh chờ đến lúc pipeline chạy mới gặp lỗi do thiếu quy tắc.

Ví dụ này tạo interface riêng vì nó **gom một vai trò nghiệp vụ được dùng nhiều lần** và có một phép kết hợp được định nghĩa ở cùng nơi. Nếu chỉ có một điều kiện ngắn nằm trong đúng một lệnh **filter**, **Predicate<Order>** vẫn có thể là lựa chọn đơn giản và tốt hơn.

## 5. Hợp đồng mạnh hơn boolean: trả về quyết định có ý nghĩa

Đôi khi **Predicate<Request>** không đủ để mô tả nghiệp vụ: một hồ sơ có thể được **chấp thuận**, **từ chối** hoặc **cần kiểm tra thủ công**. Thay vì ép mọi trường hợp thành true/false rồi lưu ý nghĩa ở chỗ khác, hãy dùng kiểu kết quả miền nghiệp vụ.

Tạo tệp **ApprovalPolicyDemo.java**:

~~~java
record Request(String id, int amount, boolean verified) {}

enum Decision {
    APPROVE, REJECT, REVIEW
}

@FunctionalInterface
interface ApprovalPolicy {
    Decision decide(Request request);
}

public class ApprovalPolicyDemo {
    public static void main(String[] args) {
        ApprovalPolicy policy = request -> {
            if (!request.verified()) {
                return Decision.REVIEW;
            }
            if (request.amount() > 1_000) {
                return Decision.REJECT;
            }
            return Decision.APPROVE;
        };

        System.out.println(policy.decide(
                new Request("A", 500, true)));
        System.out.println(policy.decide(
                new Request("B", 500, false)));
        System.out.println(policy.decide(
                new Request("C", 1_500, true)));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ApprovalPolicyDemo.java
java ApprovalPolicyDemo
~~~

Stdout:

~~~text
APPROVE
REVIEW
REJECT
~~~

Quy tắc và các con số ở đây chỉ là ví dụ học lập trình, không đại diện cho hệ thống phê duyệt thực. Điểm chính là hợp đồng **Decision decide(Request)**: tên method và kiểu kết quả mô tả được ba trạng thái. Với **Function<Request,Decision>** ta cũng biểu diễn được chữ ký đó, nhưng **ApprovalPolicy** làm rõ vai trò trong API. Nếu cần lưu cả **mã lý do**, **thông điệp** hoặc **thời điểm đánh giá**, có thể cho SAM trả về **record DecisionResult(Decision decision, String reason)**.

Một functional interface có đúng một SAM **không có nghĩa chỉ được trả về boolean**. SAM có thể trả về enum, record, collection hoặc một kiểu miền nghiệp vụ bất kỳ; đây thường là lý do tốt hơn để chọn kiểu riêng khi một Boolean đơn thuần không thể hiện đủ kết quả cần thiết.

## 6. Thiết kế hợp đồng có thể hiểu và kiểm thử

Trước khi công bố một custom functional interface cho nhiều module sử dụng, xác định các thành phần sau.

### 6.1. Tên interface và phương thức phải thể hiện hành vi

Nên đặt tên theo một **vai trò có thể diễn đạt thành câu**: **FreeShippingRule.qualifies(order)**, **ApprovalPolicy.decide(request)**, **PriceCalculator.calculate(item)**. Tránh tên quá chung như **MyFunction**, **Callback2**, **ProcessorX** hoặc phương thức **execute(Object)** khi miền dữ liệu thực ra đã xác định.

Tên tốt không thay thế việc viết tài liệu. Chẳng hạn, **qualifies** phải nêu rõ **true có ý nghĩa gì**; **calculate** phải nêu đơn vị, miền giá trị hợp lệ và cách xử lý tràn số.

### 6.2. Nêu tiền điều kiện và hậu điều kiện

Với **FreeShippingRule** ở ví dụ trên:

- **Tiền điều kiện:** Order không null và dữ liệu đơn hàng hợp lệ.
- **Hậu điều kiện:** true nếu đơn thỏa *quy tắc miễn phí vận chuyển đang đánh giá*, false nếu không.
- **Tác động phụ:** các rule thuần chỉ đọc dữ liệu và trả kết quả; nếu API cho phép rule làm I/O, phải nêu rõ vì nó ảnh hưởng đến caching, retry, hiệu năng và cách kết hợp.
- **Ngoại lệ:** cho biết lỗi đầu vào và lỗi của dependency sẽ được xử lý hay lan truyền.
- **Đặc tính kết hợp:** **and** giữ thứ tự và dừng sớm, vì vậy không được giả định tất cả rule đều được chạy.

Nên ghi các điều kiện ổn định vào **Javadoc** của interface/method; kiểu dữ liệu giúp trình biên dịch kiểm tra phần cấu trúc, còn tài liệu và test xác minh ý nghĩa.

### 6.3. Giữ quy tắc miền nghiệp vụ ở một nơi

Nếu cùng điều kiện xuất hiện trong bộ lọc danh sách, endpoint và batch job, một **FreeShippingRule** được truyền vào những nơi đó có thể giảm việc mỗi nơi tự viết lại điều kiện khác nhau. Nó cũng hỗ trợ dependency injection và test bằng cách truyền rule thay thế.

Ví dụ chữ ký API:

~~~java
static List<Order> selectEligible(
        List<Order> orders,
        FreeShippingRule rule) {

    Objects.requireNonNull(orders, "orders");
    Objects.requireNonNull(rule, "rule");

    return orders.stream()
            .filter(rule::qualifies)
            .toList();
}
~~~

Đây là **phương thức minh họa**, giả định đã import **java.util.List**, **java.util.Objects** và định nghĩa **Order**, **FreeShippingRule** ở ví dụ trước. Không có giả định **toList()** trả về danh sách mutable; trong Java 17, kết quả **Stream.toList()** là danh sách không cho phép sửa.

### 6.4. Tránh để interface tự mang quá nhiều trách nhiệm

Functional interface nên đại diện cho **một hành vi rõ ràng**. Đừng nhét mọi nghiệp vụ vào một default method hoặc biến một callback thành “service interface” có hàng chục phương thức tiện ích. Nếu cần quản lý trạng thái sống lâu, vòng đời, tài nguyên, transaction hay nhiều hành vi phối hợp, một lớp hoặc interface dịch vụ thông thường có thể diễn đạt tốt hơn.

**@FunctionalInterface** chỉ là lời cam kết về số abstract method. Để tránh thay đổi phá vỡ tương thích, không nên thêm abstract method thứ hai về sau; thay đổi như vậy làm mất khả năng dùng các lambda hiện tại và thường khiến mã client không biên dịch.

## 7. Quy tắc kết hợp: default method dùng được, nhưng phải định nghĩa ngữ nghĩa

Custom functional interface có thể cung cấp phép **and**, **or**, **negate**, nhưng **không phải lúc nào cũng cần tự xây lại Predicate**. Khi làm, phải làm rõ thứ tự và side effect.

Ví dụ **and** trong **ShippingRulesDemo** được biểu diễn:

~~~java
return order ->
        this.qualifies(order) && other.qualifies(order);
~~~

Bên trái chạy trước; nếu false thì bên phải không chạy. Nếu cả hai cùng không có side effect, điều này thường hợp với cách hiểu giao của hai điều kiện. Nếu một rule cố ý ghi log, tính phí hoặc cập nhật trạng thái, việc dừng sớm sẽ khiến số lần chạy khác mong đợi.

**Không kết hợp mặc định mọi loại policy bằng phép Boolean.** Với **ApprovalPolicy** trả về ba trạng thái, câu hỏi “APPROVE kết hợp REVIEW thì ra gì?” không có câu trả lời phổ quát. Cần bảng quyết định nghiệp vụ rõ ràng trước khi thêm **and(...)** hoặc **or(...)**. Đây chính là lợi ích của một interface có tên miền nghiệp vụ: nó buộc thiết kế công khai cách diễn giải kết quả.

Nếu có nhiều loại quy tắc có hành vi độc lập, bạn có thể viết bộ phối hợp (orchestrator) ở tầng ứng dụng thay vì đặt toàn bộ logic phối hợp vào interface.

## 8. Khi cần biểu diễn checked exception trong SAM

Một số hành vi nghiệp vụ có thể phát sinh **checked exception** bắt buộc caller xử lý hoặc khai báo. **Function<T,R>** không khai báo checked exception trên **apply**, vì vậy lambda không thể trực tiếp ném một checked exception chưa được xử lý khi gán vào Function.

Ví dụ một hợp đồng đọc tài liệu từ tệp:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

@FunctionalInterface
interface TextLoader {
    String load(Path path) throws IOException;
}
~~~

Và bên trong một phương thức có ngữ cảnh phù hợp:

~~~java
TextLoader loader = Files::readString;
~~~

Hai code block này là **các đoạn minh họa**, có thể đặt trong một đơn vị Java thích hợp; **load(...)** gọi **Files.readString(Path)** và có thể ném **IOException**, nên caller phải bắt hoặc khai báo ngoại lệ đó.

Điểm quan trọng không chỉ là “làm cho lambda biên dịch”: chữ ký **throws IOException** thông báo rõ khả năng lỗi I/O ngay tại ranh giới API. Tránh thiết kế kiểu **ThrowingFunction** chung chung nếu mọi caller lại phải đoán loại lỗi; với một hợp đồng nghiệp vụ xác định, tên và checked exception cụ thể giúp đọc hiểu và test hơn. Tuy nhiên, không cần tạo interface mới chỉ để bao bọc IOException khi các API sẵn có như **Callable<T>** hoặc một phương thức thường đã phù hợp hơn.

Khi dùng custom interface có checked exception trong Stream, **Stream.map(...)** vẫn yêu cầu **Function** không khai báo checked exception. Bạn phải chuyển đổi lỗi theo chính sách của ứng dụng, xử lý bên ngoài pipeline hoặc dùng vòng lặp phù hợp; interface mới không tự thay đổi chữ ký của Stream API.

## 9. Generic functional interface: linh hoạt nhưng vẫn cần tên rõ

Có thể định nghĩa một SAM generic khi cùng một vai trò áp dụng cho nhiều kiểu miền dữ liệu:

~~~java
@FunctionalInterface
interface BusinessRule<T> {
    boolean accepts(T value);
}
~~~

Ví dụ:

~~~java
BusinessRule<String> nonBlank =
        value -> value != null && !value.isBlank();
~~~

Đây là các **đoạn mã minh họa**, không phải chương trình Java độc lập. Generic giúp **T** giữ type safety, tránh ép kiểu thủ công; nhưng một tên quá chung cũng có thể quay lại vấn đề ban đầu: **BusinessRule<T>** có nghĩa gì hơn **Predicate<T>**?

Hãy cân nhắc generic khi thực sự có một **hợp đồng chung dùng qua nhiều miền dữ liệu**, chẳng hạn cùng cơ chế tổ hợp rule hoặc audit. Nếu quy tắc chỉ có nghĩa với Order hoặc Request, **FreeShippingRule** hay **ApprovalPolicy** thường thể hiện ý định tốt hơn.

Lưu ý đến **variance** khi thiết kế API nhận các rule tổng quát; với các kiểu chuẩn như **Predicate<? super T>**, Java cho phép đối tượng nhận cả predicate của kiểu cha phù hợp. Một interface riêng không tự động thừa hưởng các công cụ hỗ trợ chung hoặc chữ ký wildcard của API thư viện; việc giữ kiểu quá cứng có thể gây bất tiện khi mở rộng.

## 10. Lambda có thể được dùng ở đâu và những giới hạn cần nhớ

**Target typing:** lambda cần ngữ cảnh kiểu đích là functional interface. Ví dụ **FreeShippingRule rule = order -> order.paid();** có kiểu đích rõ. Một lambda trần như **var rule = order -> order.paid();** không đủ ngữ cảnh để Java suy ra functional interface, vì vậy không thể biên dịch theo cách đó.

**Không phải mọi method reference đều tương thích:** tham số và kiểu trả về của phương thức được tham chiếu phải phù hợp SAM. **Order::paid** là **Order → boolean**; **Order::subtotalCents** là **Order → long**, không thể dùng trực tiếp thay thế quy tắc trả boolean.

**Overload có thể mơ hồ:** nếu cùng tên phương thức nhận hai interface khác nhau mà cùng tương thích với một lambda, trình biên dịch có thể không chọn được overload. Khi cần, gán lambda cho một biến có kiểu xác định hoặc thiết kế API tránh overload gây nhầm lẫn.

**Lambda không tự bảo đảm thread safety:** một rule ghi vào biến/collection mutable chia sẻ có thể xảy ra race condition khi đánh giá song song. Quy tắc miễn phí vận chuyển lý tưởng là một hàm quyết định dựa trên đối tượng đầu vào và dữ liệu cấu hình ổn định.

**Lambda capture:** biến cục bộ được bắt bởi lambda phải là **final hoặc effectively final**. Điều này không khiến các đối tượng mà lambda tham chiếu trở thành immutable; các trường của đối tượng vẫn có thể thay đổi.

**Equality và identity:** không nên dựa vào danh tính object của lambda, cũng không nên so sánh lambda bằng **==** như cách xác định hai quy tắc có cùng ý nghĩa. Nếu cần mã nhận diện hoặc phiên bản chính sách, hãy lưu metadata rõ ràng ở một cấu trúc riêng.

**Null và exception:** chữ ký **FreeShippingRule** không tự bảo đảm caller không truyền null. Nếu muốn thực thi tiền điều kiện đồng nhất, hãy đưa kiểm tra vào ranh giới sử dụng hoặc một adapter được định nghĩa rõ; không được nghĩ mọi lambda sẽ luôn tuân thủ hợp đồng chỉ vì có annotation.

## 11. Đánh đổi khi tự định nghĩa interface

| Lựa chọn | Ưu điểm | Hạn chế |
| --- | --- | --- |
| **Predicate<Order>** | Chuẩn Java, có sẵn **and/or/negate**, tích hợp trực tiếp với Stream | Tên kiểu/method chung; ý nghĩa rule nằm ở tên biến hoặc tài liệu |
| **FreeShippingRule** | Vai trò nghiệp vụ rõ, có thể định nghĩa quy tắc kết hợp và hợp đồng đầu vào | Thêm kiểu/API phải duy trì; đôi khi cần method reference để truyền vào API chuẩn |
| **Function<Request,Decision>** | Ngắn, phổ biến, truyền được vào API nhận Function | **apply** chung chung; không nói rõ đây là phê duyệt |
| **ApprovalPolicy** | **decide** và **Decision** thể hiện ý nghĩa, có thể thêm tài liệu miền | Thêm một abstraction cần cân nhắc nếu chỉ dùng một nơi |
| **Interface dịch vụ thông thường nhiều method** | Phù hợp với nhiều năng lực hoặc vòng đời phức tạp | Không còn là SAM nếu có nhiều abstract method không tương đương; không thể dùng trực tiếp lambda làm implementation |

Một bài học quan trọng về thiết kế API là **kiểu nên thể hiện điều gì có giá trị với người gọi**. Nếu tên interface chỉ lặp lại kiểu dữ liệu (**OrderPredicate** để dùng đúng một lần), nó có thể chưa đem lại lợi ích. Nếu tên là một khái niệm được bàn tới trong tài liệu nghiệp vụ và nhiều use case, kiểu riêng có thể giúp tránh lệch nghĩa khi hệ thống phát triển.

## 12. Kiểm thử contract thay vì chỉ nhìn lambda ngắn

Các kiểm thử nên bao phủ **quy tắc**, **cách kết hợp** và **ranh giới dữ liệu**:

1. **Ca đúng:** đơn đã trả tiền, nội địa, đạt ngưỡng phải đủ điều kiện.
2. **Ca sai:** mỗi điều kiện sai riêng rẽ; đơn thiếu ngưỡng chỉ một đơn vị.
3. **Biên:** subtotal bằng đúng **50_000L** phải đạt; **49_999L** không đạt.
4. **Kết hợp:** **a.and(b)** chỉ trả true khi cả hai true; kiểm tra short-circuit nếu quy tắc thứ hai có cách quan sát an toàn.
5. **Ngoại lệ và null:** caller vi phạm hợp đồng được xử lý thế nào; **and(null)** phải được từ chối như ví dụ đã định nghĩa.
6. **Tác động phụ:** rule lý tưởng không sửa Order, không phụ thuộc vào thứ tự gọi trừ khi hợp đồng nói rõ.
7. **API tích hợp:** method reference **eligible::qualifies** phải sử dụng được ở **Stream.filter** và cho kết quả thống nhất với gọi trực tiếp.

Một test nhỏ giúp kiểm tra biên trong cùng ngữ cảnh của **ShippingRulesDemo**:

~~~java
FreeShippingRule threshold =
        order -> order.subtotalCents() >= 50_000L;

System.out.println(threshold.qualifies(
        new Order("E", 50_000L, true, true)));  // true
System.out.println(threshold.qualifies(
        new Order("F", 49_999L, true, true)));  // false
~~~

Đây là **đoạn minh họa đặt bên trong phương thức có quyền truy cập Order và FreeShippingRule**, không phải một chương trình độc lập. Chú thích cho biết kết quả khi chạy, đồng thời cho thấy các bất biến có thể được kiểm chứng một cách có hệ thống.

Nếu rule dùng dependency thay đổi theo thời gian (ví dụ cấu hình khuyến mại, hệ thống định giá), test cần kiểm soát dependency, trạng thái và thời điểm; không nên giả định rằng mọi lambda đều là hàm thuần.

## 13. Checklist quyết định tạo custom functional interface

Trước khi thêm một interface mới, trả lời lần lượt:

1. **Có khái niệm nghiệp vụ được gọi tên rõ ràng không?** Nếu có, tên kiểu và SAM có thể làm API tự diễn đạt.
2. **Kiểu chuẩn có đủ dễ đọc chưa?** **Predicate<T>**, **Function<T,R>** có thể đã đáp ứng hoàn toàn.
3. **Có hợp đồng riêng cần công bố không?** Null, đơn vị đo, ý nghĩa boolean hoặc enum, lỗi, side effect, thứ tự đánh giá.
4. **Có cần phép kết hợp riêng không?** Nếu chỉ cần **and** theo logic Boolean, Predicate đã cung cấp; nếu kết hợp mang ý nghĩa đặc biệt, phải thiết kế và test rõ.
5. **Có nhiều caller hoặc API công khai dùng cùng vai trò không?** Tên riêng càng hữu ích khi hợp đồng là điểm giao giữa các module.
6. **Interface vẫn chỉ có một SAM chứ?** Nếu cần nhiều hành vi trừu tượng khác nhau, hãy cân nhắc mô hình service/class thay thế.
7. **Sự tương tác với Java API chuẩn có thuận tiện không?** Dùng method reference hoặc adapter khi cần, không làm người dùng phải viết boilerplate quá nhiều.
8. **Có test minh họa được hợp đồng không?** Tên interface không thay thế việc kiểm tra hành vi ở ca bình thường, biên và lỗi.

**Kết luận học tập:** functional interface riêng có giá trị khi nó biến một chữ ký hàm chung thành **một hợp đồng nghiệp vụ được đặt tên, giải thích và kiểm tra rõ ràng**. Dùng kiểu có sẵn cho phép biến đổi thông dụng; tạo kiểu riêng khi ngữ nghĩa của API thực sự cần nổi bật. Quy tắc **một SAM** giúp tiếp tục dùng lambda và method reference, còn tính đúng đắn của nghiệp vụ vẫn đến từ thiết kế hợp đồng, bất biến và kiểm thử.