# DSL nhúng trong ngôn ngữ chủ

Một ngôn ngữ miền đặc thù (Domain-Specific Language — DSL) có thể được xây dựng như một ngôn ngữ riêng với cú pháp và bộ xử lý độc lập, hoặc được biểu diễn ngay bên trong một ngôn ngữ lập trình tổng quát. Cách thứ hai được gọi là **DSL nhúng** (*embedded DSL*), thường cũng được gọi là **DSL nội bộ** (*internal DSL*). DSL nhúng tận dụng cú pháp, hệ thống kiểu, hàm, đối tượng và công cụ của một **ngôn ngữ chủ** (*host language*) để diễn đạt các khái niệm của một miền cụ thể.

Ví dụ, Java Stream API cho phép mô tả thao tác lọc và biến đổi dữ liệu theo một chuỗi biểu thức:

~~~java
List<String> customerNames = orders.stream()
    .filter(Order::isPaid)
    .map(Order::customerName)
    .toList();
~~~

Người đọc có thể nhận ra ý nghĩa nghiệp vụ của các bước `filter` và `map`, trong khi trình biên dịch vẫn phân tích chương trình theo cú pháp Java. Các phương thức của Stream API tạo nên một cách diễn đạt có tính DSL cho miền xử lý luồng dữ liệu.

DSL nhúng phù hợp khi người sử dụng có thể làm việc trong ngôn ngữ chủ, khi miền có thể được mô hình hóa tốt bằng API và khi lợi ích từ kiểu dữ liệu, IDE, trình biên dịch cùng hệ sinh thái của ngôn ngữ chủ lớn hơn nhu cầu có cú pháp hoàn toàn độc lập.

## 1. Khái niệm và cách hoạt động

### Ngôn ngữ chủ là gì?

Ngôn ngữ chủ là ngôn ngữ lập trình tổng quát chứa phần biểu diễn DSL. Ví dụ:

- Java có thể làm ngôn ngữ chủ cho DSL cấu hình quy trình, kiểm thử hoặc truy vấn dữ liệu thông qua API.
- Kotlin có thể làm ngôn ngữ chủ cho DSL xây dựng giao diện, cấu hình hoặc kiểm thử với lambda có receiver.
- Groovy có thể làm ngôn ngữ chủ cho DSL cấu hình build và tự động hóa.
- Scala có thể làm ngôn ngữ chủ cho DSL xử lý dữ liệu hoặc mô hình hóa tính toán.
- Ruby có thể làm ngôn ngữ chủ cho DSL mô tả cấu hình, định tuyến hoặc kiểm thử.

Ngôn ngữ chủ cung cấp nền tảng cú pháp và ngữ nghĩa. DSL nhúng bổ sung một bộ API, quy ước và kiểu dữ liệu có tên gọi gần với thuật ngữ của miền nghiệp vụ.

### DSL nhúng là gì?

DSL nhúng là một cách diễn đạt chuyên biệt được xây dựng bằng các cấu trúc hợp lệ của ngôn ngữ chủ. Người thiết kế tạo các hàm, phương thức, lớp, đối tượng, kiểu dữ liệu và quy tắc kết hợp để người dùng có thể viết chương trình gần với ngôn ngữ của miền.

Thông thường, DSL nhúng không cần một bộ phân tích cú pháp độc lập. Trình biên dịch hoặc trình thông dịch của ngôn ngữ chủ phân tích mã nguồn; các API của DSL tiếp nhận lời gọi và xây dựng cấu trúc, kiểm tra quy tắc hoặc thực hiện hành động tương ứng.

Ví dụ, một thư viện có thể cung cấp phương thức `rule`, `when` và `then`. Khi người dùng viết:

~~~java
policy("standard")
    .rule("confirm paid orders", Order::isPaid, Order::confirm);
~~~

thì `policy` và `rule` là các phương thức Java. Thư viện định nghĩa ý nghĩa của chúng trong miền chính sách đơn hàng. Trình biên dịch Java kiểm tra cú pháp, kiểu tham số, phương thức được gọi và kiểu trả về.

### DSL nhúng không phải một đoạn văn bản DSL nằm trong chuỗi

Cần phân biệt DSL nhúng thực sự với một ngôn ngữ khác được đặt trong chuỗi ký tự của chương trình chủ.

Ví dụ:

~~~java
String sql = "select id, name from customer where active = true";
PreparedStatement statement = connection.prepareStatement(sql);
~~~

Đoạn SQL nằm trong chương trình Java, nhưng cú pháp `select ... from ... where ...` không phải cú pháp Java. SQL có ngữ pháp và bộ xử lý riêng; Java chỉ lưu và chuyển chuỗi đó cho hệ quản trị cơ sở dữ liệu. Đây thường được gọi là ngôn ngữ ngoài được nhúng trong mã nguồn hoặc chuỗi truy vấn, chứ không phải DSL nội bộ được biểu diễn bằng API Java.

Ngược lại, khi dùng API có kiểu như Criteria API hoặc một thư viện xây dựng truy vấn bằng các lời gọi phương thức Java, phần diễn đạt đó là DSL nhúng. Một ứng dụng có thể kết hợp cả hai cách: API Java tạo cấu trúc truy vấn, sau đó thư viện sinh SQL để gửi đến cơ sở dữ liệu.

## 2. Vị trí của DSL nhúng trong nhóm DSL nội bộ và bên ngoài

Hai hướng triển khai thường được phân biệt như sau:

- **DSL nội bộ (internal DSL):** dựa trên cú pháp và cơ chế của ngôn ngữ chủ. DSL thường được biểu diễn bằng API có kiểu, biểu thức, lambda, builder hoặc các cấu trúc ngôn ngữ khác.
- **DSL bên ngoài (external DSL):** có ngữ pháp và cú pháp riêng, thường cần lexer/parser, bộ phân tích ngữ nghĩa, mô hình trung gian và trình thực thi hoặc trình sinh mã riêng.

DSL nhúng là cách triển khai tiêu biểu của DSL nội bộ. Tuy nhiên, một dự án có thể phối hợp cả hai: cung cấp DSL bên ngoài cho chuyên viên nghiệp vụ, đồng thời cung cấp API nhúng cho nhà phát triển cần tích hợp sâu vào ứng dụng.

| Tiêu chí | DSL nhúng trong ngôn ngữ chủ | DSL bên ngoài |
|---|---|---|
| Cú pháp | Tuân theo cú pháp ngôn ngữ chủ, được định hình qua API và quy ước. | Có ngữ pháp riêng được thiết kế cho miền. |
| Phân tích cú pháp | Dùng parser của ngôn ngữ chủ. | Thường cần lexer/parser riêng hoặc công cụ sinh parser. |
| Kiểm tra kiểu | Có thể tận dụng hệ thống kiểu của ngôn ngữ chủ. | Cần tự định nghĩa và triển khai kiểm tra kiểu/ngữ nghĩa của DSL. |
| IDE | Thường có thể tận dụng hoàn thành mã, điều hướng, tái cấu trúc và kiểm tra lỗi của IDE chủ. | Cần plugin hoặc hỗ trợ ngôn ngữ riêng để có trải nghiệm tương đương. |
| Tự do thiết kế cú pháp | Bị giới hạn bởi ngữ pháp của ngôn ngữ chủ. | Có thể thiết kế cú pháp gần với ngôn ngữ nghiệp vụ hơn. |
| Người sử dụng | Thường phù hợp với lập trình viên quen ngôn ngữ chủ. | Có thể hướng đến chuyên viên nghiệp vụ nếu cú pháp dễ tiếp cận. |
| Tích hợp | Gọi trực tiếp kiểu, hàm, thư viện và thành phần của ứng dụng chủ. | Cần cơ chế tích hợp, ánh xạ dữ liệu hoặc sinh mã. |
| Triển khai | Thường phân phối như thư viện hoặc module của ngôn ngữ chủ. | Phải phân phối bộ xử lý, công cụ và có thể cả môi trường chạy riêng. |
| Phụ thuộc | Gắn với phiên bản, quy ước và hệ sinh thái của ngôn ngữ chủ. | Phụ thuộc vào bộ xử lý và công cụ riêng của DSL. |

Không có hướng nào tốt nhất cho mọi trường hợp. Quyết định cần dựa vào người sử dụng, độ phức tạp của miền, yêu cầu cú pháp, môi trường tích hợp và chi phí duy trì.

## 3. Các kỹ thuật xây dựng DSL nhúng

DSL nhúng thường được hình thành từ một hoặc nhiều kỹ thuật dưới đây. Các kỹ thuật có thể kết hợp để tạo ra một API vừa dễ đọc vừa có kiểm tra kiểu tốt.

### 3.1. Fluent interface và method chaining

**Fluent interface** là cách thiết kế API sao cho các lời gọi phương thức nối tiếp nhau thành một biểu thức có thể đọc như một chuỗi thao tác. Phương thức thường trả về đối tượng hiện tại hoặc một đối tượng builder tiếp theo.

Ví dụ:

~~~java
List<Order> eligibleOrders = orders.stream()
    .filter(Order::isPaid)
    .filter(order -> !order.isCancelled())
    .sorted(Comparator.comparing(Order::createdAt))
    .toList();
~~~

Chuỗi lời gọi thể hiện lần lượt các điều kiện và thao tác trên tập đơn hàng. Mỗi phương thức trả về một `Stream` để bước tiếp theo có thể tiếp tục được nối.

Khi thiết kế API kiểu này, cần chú ý:

- Tên phương thức nên dùng từ vựng của miền.
- Kiểu trả về phải cho phép bước kế tiếp hợp lệ.
- Thứ tự lời gọi phải có ý nghĩa rõ ràng.
- Không nên tạo chuỗi quá dài hoặc yêu cầu người dùng nhớ nhiều quy tắc ngầm.
- Cần xác định thao tác nào chỉ cấu hình, thao tác nào thực sự thực thi.

### 3.2. Builder pattern

Builder pattern giúp tạo một đối tượng cấu hình hoặc mô hình nhiều bước bằng API có thể đọc được. Nó đặc biệt hữu ích khi DSL có nhiều thuộc tính tùy chọn, quy tắc hoặc nhánh cấu hình.

Ví dụ xây dựng chính sách giao hàng:

~~~java
DeliveryPolicy policy = DeliveryPolicy.builder()
    .name("standard-delivery")
    .maxDistanceKm(30)
    .allowWeekendDelivery(false)
    .requireSignature(true)
    .build();
~~~

Người dùng không phải gọi constructor với nhiều tham số khó nhớ. Mỗi phương thức builder thể hiện một phần ý nghĩa của cấu hình. Phương thức `build()` có thể kiểm tra các trường bắt buộc và bất biến trước khi tạo đối tượng cuối cùng.

Builder phù hợp khi cấu trúc được mô tả theo từng thuộc tính. Nếu miền có các nhánh điều kiện hoặc luồng hành động, có thể kết hợp builder với lambda hoặc các đối tượng cấu hình lồng nhau.

### 3.3. Lambda và functional interface

Lambda cho phép người dùng truyền một đoạn hành vi vào API. Trong Java, các functional interface như `Predicate<T>`, `Function<T, R>`, `Consumer<T>`, `Supplier<T>` và `BiFunction<T, U, R>` thường được dùng để biểu diễn điều kiện, phép biến đổi, hành động hoặc giá trị được tính sau.

Ví dụ:

~~~java
List<Order> urgentOrders = orders.stream()
    .filter(order -> order.priority() == Priority.HIGH)
    .filter(order -> order.deliveryDate().isBefore(deadline))
    .toList();
~~~

Hai lambda biểu diễn điều kiện theo ngôn ngữ miền. Người thiết kế API có thể chọn kiểu hàm để kiểm soát dữ liệu đầu vào và kết quả mà người dùng được phép cung cấp.

Lambda cũng cho phép xây dựng cấu trúc lồng nhau:

~~~java
workflow("fulfill-order", workflow -> {
    workflow.step("validate", context -> validateOrder(context));
    workflow.step("reserve", context -> reserveInventory(context));
    workflow.step("ship", context -> createShipment(context));
});
~~~

Trong ví dụ, lambda nhận một đối tượng cấu hình `workflow` và khai báo các bước. Cấu trúc này hữu ích cho DSL mô tả quy trình, kiểm thử hoặc chính sách.

### 3.4. Static import và tên API gần ngôn ngữ miền

Java hỗ trợ `static import`, cho phép gọi phương thức tĩnh mà không phải viết tên lớp ở mỗi lần gọi. Điều này có thể làm biểu thức DSL ngắn hơn:

~~~java
import static com.example.policy.Policies.policy;

Policy standard = policy("standard")
    .rule("paid orders", Order::isPaid, Order::confirm)
    .build();
~~~

Tên phương thức và tham số nên được chọn sao cho người đọc hiểu được mục đích. Tuy nhiên, không nên lạm dụng tên chung như `of`, `do`, `with`, `run` ở mọi nơi nếu chúng làm mất ngữ cảnh hoặc gây xung đột khi import.

### 3.5. Generics và kiểu dữ liệu miền

Generics giúp API DSL giới hạn kiểu dữ liệu hợp lệ và truyền thông tin kiểu qua các bước. Ví dụ, một builder có thể đảm bảo một bước chỉ nhận `Order`, còn bước xử lý thanh toán chỉ nhận `Payment`.

~~~java
public interface Rule<T> {
    boolean matches(T value);
    void apply(T value);
}

public final class Rules {
    public static <T> Rule<T> rule(
            Predicate<T> condition,
            Consumer<T> action) {
        return new Rule<>() {
            @Override
            public boolean matches(T value) {
                return condition.test(value);
            }

            @Override
            public void apply(T value) {
                action.accept(value);
            }
        };
    }
}
~~~

Khi gọi `Rules.rule(Order::isPaid, Order::confirm)`, trình biên dịch có thể suy luận `T` là `Order` nếu chữ ký phương thức tương thích. Nếu truyền một hàm không nhận `Order`, lỗi kiểu có thể được phát hiện ngay khi biên dịch.

Kiểu dữ liệu miền cũng giúp ngăn nhầm lẫn giữa các giá trị có cùng kiểu nguyên thủy. Chẳng hạn, `OrderId` và `CustomerId` có thể là hai kiểu riêng thay vì cùng dùng `String`. Cách này làm API rõ ràng và giảm lỗi truyền nhầm dữ liệu.

### 3.6. Extension function và receiver lambda

Một số ngôn ngữ chủ hỗ trợ mở rộng cú pháp API mạnh hơn Java. Kotlin có extension function và lambda với receiver, cho phép tạo cấu trúc lồng nhau gần với ngôn ngữ cấu hình.

~~~kotlin
data class Order(val id: String, val paid: Boolean)

class OrderPolicyBuilder {
    private val checks = mutableListOf<(Order) -> Boolean>()

    fun require(description: String, check: (Order) -> Boolean) {
        checks += check
    }
}

fun orderPolicy(block: OrderPolicyBuilder.() -> Unit): OrderPolicyBuilder {
    return OrderPolicyBuilder().apply(block)
}

val policy = orderPolicy {
    require("order must be paid") { order -> order.paid }
}
~~~

Lambda `OrderPolicyBuilder.() -> Unit` có `OrderPolicyBuilder` làm receiver. Vì vậy, bên trong khối, người dùng có thể gọi `require` trực tiếp mà không cần viết `builder.require(...)`. Đây là một kỹ thuật thường dùng để xây dựng Kotlin DSL.

Java không có extension function hoặc lambda receiver theo cách Kotlin cung cấp. Trong Java, có thể đạt trải nghiệm gần tương tự bằng builder, phương thức lồng nhau, static import và lambda nhận đối tượng cấu hình tường minh.

### 3.7. Operator overloading và cú pháp đặc thù của ngôn ngữ chủ

Một số ngôn ngữ cho phép định nghĩa lại ý nghĩa của toán tử trong những kiểu do người dùng tạo. Kotlin và Scala có những cơ chế như vậy; Java không hỗ trợ nạp chồng toán tử do người dùng định nghĩa.

Ví dụ Kotlin có thể dùng toán tử `plus` cho một kiểu miền:

~~~kotlin
data class Money(val amount: Long) {
    operator fun plus(other: Money) = Money(amount + other.amount)
}

val total = Money(100) + Money(50)
~~~

Biểu thức `+` có ý nghĩa cộng hai giá trị tiền. Khi sử dụng operator overloading, cần bảo đảm ý nghĩa gần với trực giác của toán tử và không tạo hành vi bất ngờ. Không nên dùng toán tử quen thuộc cho thao tác có tác dụng phụ hoặc ý nghĩa nghiệp vụ khó đoán.

Các ngôn ngữ như Scala còn cung cấp nhiều khả năng trừu tượng hóa để xây dựng DSL ngắn gọn. Tuy vậy, cú pháp càng dựa nhiều vào tính năng nâng cao của host language thì người mới càng cần hiểu ngôn ngữ chủ để đọc và sửa DSL.

## 4. Ví dụ xây dựng DSL nhúng bằng Java

Giả sử cần mô tả các quy tắc xác nhận đơn hàng. Người dùng mong muốn khai báo điều kiện và hành động bằng thuật ngữ của miền, đồng thời tận dụng hệ thống kiểu Java.

### Mục tiêu API

Một cách sử dụng mong muốn:

~~~java
Policy policy = policy("standard-order")
    .rule("confirm paid orders", Order::isPaid, Order::confirm)
    .rule("reserve confirmed orders", Order::isConfirmed, Order::reserveItems)
    .build();
~~~

API cần cung cấp:

- `policy(name)` để bắt đầu khai báo chính sách.
- `rule(name, condition, action)` để thêm một quy tắc.
- `condition` là điều kiện nhận `Order` và trả về `boolean`.
- `action` là hành động nhận `Order` và không cần trả về giá trị.
- `build()` để kiểm tra và tạo đối tượng chính sách bất biến hoặc đã hoàn chỉnh.

### Các kiểu miền tối thiểu

~~~java
public final class Order {
    private boolean paid;
    private boolean confirmed;
    private boolean itemsReserved;

    public boolean isPaid() {
        return paid;
    }

    public boolean isConfirmed() {
        return confirmed;
    }

    public void confirm() {
        confirmed = true;
    }

    public void reserveItems() {
        itemsReserved = true;
    }
}
~~~

Đây là mô hình tối giản để minh họa DSL. Trong ứng dụng thực tế, các phương thức miền cần bảo vệ bất biến, kiểm tra trạng thái hiện tại và xử lý lỗi phù hợp.

### Cài đặt builder và quy tắc

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Consumer;
import java.util.function.Predicate;

public final class Policy {
    private final String name;
    private final List<Rule> rules;

    private Policy(String name, List<Rule> rules) {
        this.name = name;
        this.rules = List.copyOf(rules);
    }

    public String name() {
        return name;
    }

    public void apply(Order order) {
        for (Rule rule : rules) {
            if (rule.condition().test(order)) {
                rule.action().accept(order);
            }
        }
    }

    private record Rule(
        String description,
        Predicate<Order> condition,
        Consumer<Order> action
    ) {}

    public static PolicyBuilder policy(String name) {
        return new PolicyBuilder(name);
    }

    public static final class PolicyBuilder {
        private final String name;
        private final List<Rule> rules = new ArrayList<>();

        private PolicyBuilder(String name) {
            this.name = Objects.requireNonNull(name);
            if (name.isBlank()) {
                throw new IllegalArgumentException("Policy name is required");
            }
        }

        public PolicyBuilder rule(
                String description,
                Predicate<Order> condition,
                Consumer<Order> action) {
            rules.add(new Rule(
                Objects.requireNonNull(description),
                Objects.requireNonNull(condition),
                Objects.requireNonNull(action)
            ));
            return this;
        }

        public Policy build() {
            return new Policy(name, rules);
        }
    }
}
~~~

Đoạn mã minh họa một triển khai nhỏ, trong đó builder thu thập quy tắc và `Policy.apply` thực thi chúng theo thứ tự khai báo. Các quy tắc được biểu diễn bằng `Predicate<Order>` và `Consumer<Order>`, nên trình biên dịch kiểm tra kiểu dữ liệu được truyền vào.

### Sử dụng DSL

~~~java
import static com.example.Policy.policy;

Policy standardPolicy = policy("standard-order")
    .rule("confirm paid orders", Order::isPaid, Order::confirm)
    .rule("reserve confirmed orders", Order::isConfirmed, Order::reserveItems)
    .build();

Order order = new Order();
standardPolicy.apply(order);
~~~

Người đọc có thể hiểu ý nghĩa tổng thể mà không cần xem phần cài đặt builder. Tuy nhiên, để DSL đáng tin cậy trong sản phẩm thật, cần bổ sung những quyết định mà ví dụ tối giản chưa xử lý:

- Nếu một hành động làm thay đổi điều kiện của quy tắc tiếp theo, chính sách có chủ ý đánh giá lại điều kiện đó không?
- Nếu một hành động phát sinh lỗi, các quy tắc còn lại có tiếp tục chạy không?
- Nếu hai quy tắc xung đột, thứ tự khai báo có quyết định kết quả không?
- Có cần dừng sau quy tắc đầu tiên khớp điều kiện không?
- Có cần kiểm tra trùng tên, quy tắc không thể đạt tới hoặc điều kiện mâu thuẫn không?
- Các hành động có cần chạy trong một giao dịch để bảo đảm tính nhất quán không?

Những câu hỏi này thuộc ngữ nghĩa của DSL và phải được xác định rõ. Cú pháp fluent dễ đọc không tự động bảo đảm hành vi đúng.

## 5. Một số dạng DSL nhúng phổ biến

### DSL truy vấn và biến đổi dữ liệu

Java Stream API là ví dụ nổi bật. Người dùng mô tả một pipeline gồm nguồn dữ liệu, thao tác trung gian và thao tác kết thúc:

~~~java
Map<Department, Long> counts = employees.stream()
    .filter(Employee::isActive)
    .collect(Collectors.groupingBy(
        Employee::department,
        Collectors.counting()
    ));
~~~

Các thao tác như `filter`, `map`, `flatMap`, `sorted`, `groupingBy` và `counting` tạo nên từ vựng của miền xử lý dữ liệu. Người dùng kết hợp các thao tác bằng cú pháp Java và nhận lợi ích từ generic type, lambda và kiểm tra kiểu.

### DSL kiểm thử

Các framework kiểm thử thường cung cấp API có thể đọc như một kịch bản:

~~~java
assertThat(order.status())
    .isEqualTo(OrderStatus.CONFIRMED);

verify(paymentGateway).capture(order.total());
~~~

Các thư viện kiểm thử hành vi còn cho phép diễn đạt điều kiện, hành động và kết quả bằng các lời gọi liên tiếp. DSL kiểm thử làm cho ý định của ca kiểm thử rõ hơn, đồng thời vẫn chạy trong hệ sinh thái ngôn ngữ chủ.

### DSL cấu hình build

Gradle hỗ trợ DSL bằng Groovy hoặc Kotlin. Ví dụ Kotlin DSL:

~~~kotlin
plugins {
    java
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.0")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Các khối `plugins`, `dependencies` và `tasks.test` là API cấu hình được biểu diễn bằng cú pháp Kotlin. Người dùng khai báo mong muốn cấu hình; Gradle đọc cấu trúc đó để tạo và thực thi đồ thị tác vụ.

### DSL định tuyến hoặc cấu hình ứng dụng

Framework web có thể cung cấp API để khai báo tuyến:

~~~java
router.get("/orders/{id}", request -> {
    String id = request.pathParam("id");
    return orderService.findById(id);
});
~~~

Các lời gọi `get`, `pathParam` và lambda handler tạo một cách diễn đạt chuyên biệt cho miền định tuyến HTTP. Kiểu dữ liệu và chữ ký hàm giúp người dùng biết dữ liệu nào có thể truy cập ở từng bước.

### DSL mô tả giao dịch hoặc truy vấn bằng API

Một API có thể mô tả điều kiện truy vấn bằng đối tượng và lời gọi phương thức:

~~~java
Predicate<Order> condition = order ->
    order.status() == OrderStatus.PENDING
        && order.total().compareTo(minimumTotal) >= 0;
~~~

Ở mức phức tạp hơn, thư viện có thể tạo cây biểu thức để phân tích, tối ưu hoặc sinh câu truy vấn. Khi API chỉ tạo và giữ cấu trúc biểu thức, nó có thể trì hoãn việc thực thi đến một thời điểm khác.

## 6. Tận dụng hệ thống kiểu của ngôn ngữ chủ

Một lợi thế quan trọng của DSL nhúng là khả năng sử dụng hệ thống kiểu của host language. Thay vì phân tích một văn bản tùy ý rồi tự kiểm tra mọi loại giá trị, DSL có thể biểu diễn nhiều ràng buộc ngay trong chữ ký API.

### Kiểm tra kiểu khi biên dịch

Giả sử API yêu cầu một `Predicate<Order>`:

~~~java
rule("paid", Order::isPaid, Order::confirm);
~~~

Nếu người dùng truyền một phương thức không tương thích với `Order`, trình biên dịch có thể báo lỗi. Điều này giúp phát hiện một số lỗi trước khi chương trình chạy.

Tuy nhiên, kiểm tra kiểu không thay thế kiểm tra nghiệp vụ. Trình biên dịch có thể xác nhận rằng một hàm nhận `Order` và trả về `boolean`, nhưng không biết điều kiện đó có đúng với chính sách thanh toán của tổ chức hay không. Những quy tắc như “thanh toán đã được chấp nhận” vẫn cần được xác nhận bằng mô hình miền và kiểm thử.

### Kiểu miền thay cho kiểu nguyên thủy

Thay vì dùng `String` cho mọi mã định danh, có thể định nghĩa:

~~~java
public record OrderId(String value) {}
public record CustomerId(String value) {}
~~~

API nhận `OrderId` sẽ không vô tình chấp nhận `CustomerId` nếu hai kiểu không có quan hệ chuyển đổi. Các kiểu như `Money`, `Quantity`, `EmailAddress` và `TimeRange` cũng có thể chứa quy tắc kiểm tra riêng.

### Kiểu trạng thái và API theo từng giai đoạn

Một DSL có thể sử dụng kiểu khác nhau cho từng giai đoạn builder để hạn chế gọi sai thứ tự. Ví dụ, builder của một yêu cầu đặt chỗ có thể chỉ cho phép `confirm()` sau khi đã chọn phòng và thời gian.

~~~java
interface NeedRoom {
    NeedTime room(RoomId roomId);
}

interface NeedTime {
    Ready at(TimeRange timeRange);
}

interface Ready {
    Booking build();
}
~~~

API theo giai đoạn giúp một số trạng thái không hợp lệ khó biểu diễn ngay từ lúc biên dịch. Đổi lại, số lượng kiểu và độ phức tạp của API tăng lên. Chỉ nên dùng khi lợi ích của việc ngăn lỗi đủ lớn.

### Giới hạn của kiểm tra tĩnh

Không phải mọi điều kiện đều biết được khi biên dịch. Một quy tắc có thể phụ thuộc vào dữ liệu trong cơ sở dữ liệu, quyền hiện tại của người dùng hoặc trạng thái của dịch vụ bên ngoài. DSL cần phân biệt:

- **Lỗi cú pháp hoặc kiểu:** cấu trúc lời gọi sai, kiểu tham số không phù hợp.
- **Lỗi cấu hình tĩnh:** thiếu trường bắt buộc, khai báo trùng hoặc tham chiếu không hợp lệ có thể phát hiện trước khi chạy.
- **Vi phạm quy tắc lúc chạy:** dữ liệu thực tế không đáp ứng điều kiện nghiệp vụ tại thời điểm thực thi.
- **Lỗi môi trường:** dịch vụ ngoài không sẵn sàng, timeout hoặc lỗi truy cập.

Thông báo lỗi nên chỉ rõ loại lỗi, vị trí hoặc quy tắc liên quan và cách xử lý nếu có thể.

## 7. Thiết kế cú pháp của một DSL nhúng

DSL nhúng không có quyền tự do tạo ngữ pháp hoàn toàn mới, vì vậy thiết kế chủ yếu là thiết kế API và cách kết hợp các cấu trúc hợp lệ của ngôn ngữ chủ.

### Bắt đầu từ từ vựng của miền

Thu thập động từ, danh từ và điều kiện mà chuyên gia miền thường dùng. Ví dụ trong miền giao hàng:

- Danh từ: `Shipment`, `Address`, `DeliveryWindow`, `Carrier`.
- Động từ: `dispatch`, `assign`, `track`, `cancel`, `confirm`.
- Điều kiện: `withinDistance`, `available`, `requiresSignature`.
- Kết quả: `scheduled`, `inTransit`, `delivered`, `failed`.

Chọn tên API có ý nghĩa trong ngữ cảnh. Tránh tạo ra một lớp từ vựng hoàn toàn khác với cách gọi trong nghiệp vụ.

### Thiết kế cách đọc từ ngoài vào trong

Một lời gọi DSL nên giúp người đọc trả lời nhanh:

1. Đang khai báo hoặc thực hiện đối tượng gì?
2. Điều kiện hoặc hành động nào được mô tả?
3. Dữ liệu nào được sử dụng?
4. Kết quả hoặc tác dụng phụ nào có thể xảy ra?

Ví dụ:

~~~java
deliveryPolicy("regional")
    .allowWhen(address -> address.region().equals("NORTH"))
    .requireSignature()
    .maxDistance(Duration.ofKilometers(30))
    .build();
~~~

Người đọc nhận ra đây là cấu hình chính sách giao hàng theo vùng. Tuy nhiên, cần làm rõ `maxDistance` có đơn vị gì, khoảng cách được tính theo đường chim bay hay tuyến đường, và điều gì xảy ra khi vượt giới hạn.

### Cân nhắc cú pháp lồng nhau

Lambda hoặc builder lồng nhau phù hợp khi cấu hình có cấu trúc cha-con:

~~~java
workflow("refund")
    .step("validate", step -> step
        .requires("payment exists")
        .action(context -> validatePayment(context)))
    .step("refund", step -> step
        .requires("refund is allowed")
        .action(context -> issueRefund(context)))
    .build();
~~~

Cấu trúc lồng giúp gom các thiết lập cùng một bước. Không nên lồng quá nhiều cấp khiến người dùng khó xác định phạm vi của lambda hoặc biến đang được tham chiếu.

### Tránh API có ngữ nghĩa mơ hồ

Một số phương thức như `apply`, `execute`, `process`, `use` có thể quá chung nếu không có ngữ cảnh. Hãy dùng tên miền cụ thể hoặc cung cấp kiểu tham số và kiểu trả về rõ ràng.

Ví dụ, `cancelOrder(order)` dễ hiểu hơn `process(order)` nếu hành động thật sự là hủy đơn. Tương tự, phân biệt `validate`, `authorize`, `reserve` và `confirm` vì chúng có thể là các bước nghiệp vụ khác nhau.

## 8. Ngữ nghĩa và mô hình thực thi

Thiết kế DSL nhúng không dừng ở việc tạo ra một API đẹp. Cần xác định chính xác mỗi lời gọi có ý nghĩa gì và khi nào hành vi xảy ra.

### Thực thi ngay (eager execution)

Một lời gọi có thể thực hiện hành động ngay khi được gọi. Ví dụ, `repository.save(order)` thường ghi dữ liệu ngay trong thao tác gọi, tùy hợp đồng của API.

Ưu điểm là luồng điều khiển dễ hiểu. Nhược điểm là khi DSL được dùng để mô tả một kế hoạch hoặc quy trình, việc thực thi ngay có thể làm khó phân tích, tối ưu, xem trước hoặc xác nhận toàn bộ cấu hình trước khi chạy.

### Xây dựng cấu trúc rồi thực thi (deferred execution)

Một DSL có thể chỉ tạo đối tượng biểu diễn hoặc cây biểu thức trước, sau đó mới thực thi:

~~~java
Query<Order> query = query(Order.class)
    .where(order -> order.status().eq(OrderStatus.PENDING))
    .orderBy(Order::createdAt);

List<Order> result = query.execute();
~~~

Ở đây, các lời gọi đầu tiên mô tả truy vấn. `execute()` mới yêu cầu hệ thống chạy truy vấn. Thư viện có thể kiểm tra, tối ưu hoặc chuyển cấu trúc đó thành SQL.

Hai cách thực thi có thể cùng tồn tại trong một DSL. Cần đặt tên rõ để người dùng biết lời gọi nào chỉ xây dựng cấu hình, lời gọi nào thực hiện tác dụng phụ.

### Mô hình lệnh và mô hình khai báo

DSL theo phong cách mệnh lệnh (*imperative*) mô tả các bước cần thực hiện:

~~~java
order.validate();
inventory.reserve(order);
payment.capture(order);
shipment.create(order);
~~~

DSL theo phong cách khai báo (*declarative*) mô tả điều kiện hoặc kết quả mong muốn:

~~~java
orderPolicy("standard")
    .requirePaidBeforeConfirmation()
    .reserveAvailableInventory()
    .shipAfterConfirmation();
~~~

Phong cách khai báo có thể giúp người dùng tập trung vào chính sách và để thư viện quyết định cách thực hiện. Tuy nhiên, DSL cần định nghĩa rõ thứ tự, ưu tiên, xử lý xung đột và hành vi khi thất bại.

## 9. Lợi ích của DSL nhúng

### Tận dụng trình biên dịch và hệ thống kiểu

Các lỗi cú pháp, lỗi tên phương thức, sai số lượng tham số và nhiều lỗi kiểu có thể được phát hiện bởi trình biên dịch của ngôn ngữ chủ. Nhóm không cần tự xây dựng toàn bộ lexer, parser và bộ kiểm tra kiểu cho một cú pháp mới.

### Tích hợp trực tiếp với mã ứng dụng

DSL có thể gọi trực tiếp đối tượng miền, dịch vụ, thư viện và thành phần hiện có. Không cần một lớp chuyển đổi văn bản DSL sang mô hình ứng dụng nếu API đã biểu diễn được cấu trúc cần thiết.

### Tận dụng IDE và công cụ phát triển

Người dùng có thể nhận gợi ý mã, điều hướng đến định nghĩa, đổi tên, tìm tham chiếu, định dạng mã và chạy kiểm thử bằng công cụ của ngôn ngữ chủ. Trải nghiệm thực tế tùy thuộc cách API được thiết kế và mức độ hỗ trợ của IDE.

### Phân phối và quản lý phụ thuộc quen thuộc

DSL thường được đóng gói cùng thư viện hoặc module của ngôn ngữ chủ. Nhóm có thể sử dụng hệ thống dependency, build, test và phát hành đang có.

### Dễ tái sử dụng cơ chế của host language

Hàm, generic, module, interface, annotation, exception và các thư viện chuẩn có thể được tận dụng. Những khả năng này giúp giảm lượng hạ tầng phải xây dựng riêng.

### Phù hợp với lập trình viên

Khi người dùng đã thành thạo ngôn ngữ chủ, họ có thể học DSL bằng cách hiểu thêm từ vựng và API của miền. Họ không phải học thêm một trình soạn thảo hoặc bộ công cụ hoàn toàn mới.

## 10. Hạn chế và chi phí cần cân nhắc

### Bị giới hạn bởi cú pháp ngôn ngữ chủ

Ngôn ngữ chủ quyết định những biểu thức nào hợp lệ. Nếu cú pháp của nó không hỗ trợ cách diễn đạt tự nhiên cho miền, API có thể trở nên dài, nhiều dấu ngoặc hoặc khó đọc.

Ví dụ, Java không cho phép định nghĩa toán tử mới hoặc extension function như Kotlin. Một biểu thức có thể cần gọi phương thức tĩnh hoặc builder nhiều bước thay vì dùng ký hiệu gần với ngôn ngữ nghiệp vụ.

### Người dùng phải hiểu ngôn ngữ chủ

Một DSL nhúng thường khó tiếp cận với người không lập trình. Chuyên viên nghiệp vụ có thể phải hiểu kiểu dữ liệu, lambda, generic, import hoặc cấu trúc chương trình để sửa cấu hình.

### API có thể rò rỉ chi tiết kỹ thuật

Nếu người dùng phải biết quá nhiều về lớp triển khai, repository, transaction hoặc framework thì DSL không còn diễn đạt tốt ngôn ngữ miền. Cần tạo một lớp trừu tượng đủ rõ để che đi chi tiết không cần thiết.

### Kiểm tra nghiệp vụ vẫn cần được xây dựng

Trình biên dịch của host language chỉ hiểu quy tắc của ngôn ngữ chủ và chữ ký API. Nó không tự biết chính sách nghiệp vụ. Nhóm vẫn cần kiểm tra ngữ nghĩa, xác thực dữ liệu, thông báo lỗi và kiểm thử miền.

### Thay đổi host language có thể ảnh hưởng DSL

Nâng cấp phiên bản ngôn ngữ, thư viện chuẩn hoặc framework có thể làm thay đổi hành vi, API hoặc khả năng tương thích của DSL. Người duy trì cần quản lý phiên bản và kiểm thử hồi quy.

### Có thể tạo ra API khó bảo trì

Một fluent API quá nhiều overload, generic phức tạp, lambda lồng sâu hoặc trạng thái builder khó hiểu sẽ làm tăng chi phí học và bảo trì. Cú pháp ngắn chưa chắc là cú pháp dễ hiểu.

## 11. Khi nào nên chọn DSL nhúng?

DSL nhúng thường phù hợp khi:

- Người sử dụng chủ yếu là lập trình viên quen ngôn ngữ chủ.
- Miền có thể được biểu diễn bằng lời gọi API, biểu thức, kiểu dữ liệu và các cấu trúc hàm.
- Cần tích hợp chặt với mô hình đối tượng, thư viện và dịch vụ của ứng dụng.
- Cần tận dụng hệ thống kiểu, IDE, trình biên dịch và công cụ build có sẵn.
- Cú pháp riêng không phải yêu cầu bắt buộc.
- Quy mô ngôn ngữ và số lượng quy tắc có thể quản lý bằng một thư viện có cấu trúc tốt.

DSL nhúng có thể không phù hợp khi:

- Người dùng chính là chuyên viên nghiệp vụ không quen lập trình.
- Miền cần cú pháp rất khác với ngôn ngữ chủ để dễ đọc và dễ kiểm soát.
- Cần cho phép người dùng chỉnh sửa cấu hình độc lập với quá trình biên dịch ứng dụng.
- Cần phân tích, xác thực, chuyển đổi hoặc tối ưu một chương trình DSL như một tài liệu độc lập.
- Cần hỗ trợ nhiều ngôn ngữ chủ hoặc nhiều môi trường thực thi khác nhau.
- Yêu cầu kiểm soát chặt quyền thực thi, giới hạn tài nguyên hoặc sandbox cho mã do người dùng cung cấp.

Đây là các dấu hiệu để cân nhắc, không phải quy tắc tuyệt đối. Một DSL nhúng vẫn có thể phục vụ cấu hình nghiệp vụ nếu API đủ đơn giản và người dùng có năng lực phù hợp; một DSL bên ngoài cũng có thể yêu cầu người dùng hiểu nhiều khái niệm kỹ thuật.

## 12. So sánh Java, Kotlin, Groovy và Scala khi xây dựng DSL nhúng

Mỗi ngôn ngữ chủ cung cấp mức độ biểu đạt khác nhau. Việc lựa chọn cần xét đến kỹ năng đội ngũ, môi trường chạy và hệ sinh thái hiện tại.

| Ngôn ngữ chủ | Khả năng thường dùng để xây dựng DSL | Điểm cần cân nhắc |
|---|---|---|
| Java | Fluent API, builder, lambda, method reference, generic, static import, annotation. | Cú pháp tương đối tường minh; không có operator overloading hoặc extension function do người dùng định nghĩa. |
| Kotlin | Lambda with receiver, extension function, infix function, operator overloading, type-safe builder. | Cần hiểu thêm cú pháp Kotlin và một số quy ước của DSL; tương thích JVM nhưng cần cân nhắc API khi dùng từ Java. |
| Groovy | Closure, dynamic dispatch, builder, method missing và cú pháp linh hoạt. | Khả năng động giúp DSL ngắn gọn nhưng một số lỗi chỉ xuất hiện lúc chạy; cần quản lý rõ hợp đồng API. |
| Scala | Higher-order function, implicit/given, extension method, operator notation, type system phong phú. | Có khả năng biểu đạt mạnh nhưng một DSL quá trừu tượng có thể khó học và khó gỡ lỗi với người chưa quen Scala. |

### Java

Java phù hợp khi dự án đã sử dụng JVM và cần API rõ ràng, có kiểu tĩnh. Builder, generic, lambda và static import có thể tạo ra DSL nội bộ đủ dễ đọc cho nhiều miền. Các giới hạn về cú pháp được bù lại bằng tính tường minh và khả năng hỗ trợ công cụ tốt.

### Kotlin

Kotlin có các tính năng thuận lợi cho DSL nhúng như extension function và lambda with receiver. Nhờ đó, có thể tạo cấu trúc lồng giống ngôn ngữ cấu hình mà vẫn giữ kiểm tra kiểu. Kotlin thường được chọn khi cần DSL có cú pháp gọn nhưng vẫn nằm trong hệ sinh thái JVM.

### Groovy

Groovy có cú pháp linh hoạt và closure, thường được dùng để viết cấu hình build hoặc tự động hóa. Khả năng động có thể làm DSL dễ đọc, nhưng cần thiết kế thông báo lỗi và kiểm tra cấu hình cẩn thận để giảm lỗi chỉ phát hiện lúc thực thi.

### Scala

Scala cung cấp abstraction mạnh để tạo DSL biểu đạt cao. Các hàm bậc cao, kiểu dữ liệu và cú pháp toán tử có thể giúp biểu diễn phép tính phức tạp. Nhóm cần kiểm soát độ trừu tượng để DSL không trở nên khó hiểu với người đọc thông thường.

## 13. Tổ chức mã nguồn của một DSL nhúng

Khi DSL lớn dần, nên tổ chức mã nguồn theo trách nhiệm thay vì gom toàn bộ API vào một lớp tiện ích.

Một cấu trúc minh họa:

~~~text
order-policy-dsl/
  domain/
    Order.java
    Payment.java
    OrderStatus.java
    Quantity.java
  api/
    Policies.java
    PolicyBuilder.java
    RuleBuilder.java
    Policy.java
  validation/
    PolicyValidator.java
    ValidationIssue.java
  execution/
    PolicyExecutor.java
    ExecutionContext.java
  integration/
    InventoryGateway.java
    PaymentGateway.java
  examples/
    StandardOrderPolicy.java
  tests/
    PolicyBuilderTest.java
    PolicyValidationTest.java
    PolicyExecutionTest.java
~~~

Ý nghĩa các phần:

- `domain` chứa khái niệm và quy tắc miền độc lập với cách viết DSL.
- `api` cung cấp từ vựng và cấu trúc để người dùng khai báo DSL.
- `validation` kiểm tra cấu hình và phát hiện lỗi trước khi thực thi khi có thể.
- `execution` diễn giải hoặc thực thi mô hình chính sách.
- `integration` định nghĩa ranh giới với hệ thống bên ngoài.
- `examples` cung cấp chương trình mẫu.
- `tests` kiểm tra cú pháp API, ngữ nghĩa, xác thực và hành vi.

Tách mô hình miền khỏi API DSL giúp thay đổi cách diễn đạt mà không phải viết lại toàn bộ quy tắc nghiệp vụ. Nó cũng giúp nhóm kiểm thử mô hình độc lập với cách người dùng khai báo.

## 14. Kiểm thử DSL nhúng

DSL nhúng là mã của ngôn ngữ chủ, nhưng vẫn có ngữ nghĩa riêng cần kiểm thử. Không nên chỉ kiểm tra rằng chương trình biên dịch thành công.

### Kiểm thử API và builder

Kiểm tra builder tạo đúng cấu trúc, từ chối giá trị thiếu hoặc sai và bảo đảm các bất biến được giữ. Ví dụ, tên chính sách rỗng hoặc quy tắc không có điều kiện phải được xử lý theo hợp đồng API.

### Kiểm thử ngữ nghĩa

Kiểm tra ý nghĩa của mỗi cấu trúc DSL. Nếu `rule` được khai báo trước `build`, cần xác nhận quy tắc được giữ đúng thứ tự và được áp dụng theo chính sách đã định.

### Kiểm thử hành vi đầu cuối

Tạo chương trình DSL mẫu, áp dụng lên dữ liệu đại diện và kiểm tra kết quả. Ví dụ, chính sách xác nhận đơn không được xác nhận đơn chưa thanh toán.

### Kiểm thử lỗi và chẩn đoán

Kiểm tra thông báo khi cấu hình không hợp lệ, hành động ném exception, dữ liệu ngoài thiếu hoặc dịch vụ tích hợp gặp lỗi. Thông báo nên giúp người dùng biết lỗi nằm ở khai báo nào và cách khắc phục.

### Kiểm thử tương thích

Khi nâng cấp host language hoặc thư viện, chạy kiểm thử trên các chương trình DSL mẫu đã phát hành. Điều này giúp phát hiện thay đổi hành vi hoặc lỗi nguồn tương thích.

Ví dụ kiểm thử JUnit:

~~~java
@Test
void confirmsOnlyPaidOrders() {
    Policy policy = policy("standard")
        .rule("confirm paid", Order::isPaid, Order::confirm)
        .build();

    Order order = new Order();
    policy.apply(order);

    assertFalse(order.isConfirmed());
}
~~~

Ví dụ này giả định `Order` mới tạo chưa thanh toán. Trong một bộ kiểm thử thực tế, nên có cả trường hợp thanh toán thành công, trường hợp chưa thanh toán và trường hợp trạng thái không hợp lệ.

## 15. Tài liệu hóa và trải nghiệm người dùng

Một DSL nhúng tốt cần tài liệu hướng dẫn theo góc nhìn người sử dụng, không chỉ tài liệu Javadoc của từng phương thức.

Nên cung cấp:

- **Từ vựng miền:** giải thích ý nghĩa của các khái niệm, trạng thái và quy tắc.
- **Ví dụ hoàn chỉnh:** chương trình DSL có thể biên dịch hoặc chạy được, kèm đầu vào và kết quả mong đợi.
- **Hướng dẫn theo tác vụ:** cách tạo một chính sách, truy vấn, quy trình hoặc cấu hình thường gặp.
- **Tài liệu API:** kiểu tham số, giá trị trả về, ngoại lệ, tác dụng phụ và thứ tự gọi.
- **Hướng dẫn lỗi:** giải thích lỗi thường gặp và cách sửa.
- **Quy tắc tương thích:** thay đổi API, phiên bản thư viện và cách di chuyển mã cũ.

Ví dụ nên thể hiện cả trường hợp thành công lẫn trường hợp bị từ chối. Nếu API có nhiều kiểu builder, tài liệu cần chỉ ra bước tiếp theo hợp lệ và thời điểm cấu hình được thực thi.

## 16. Bảo mật và ranh giới thực thi

DSL nhúng có thể chạy với đầy đủ quyền của chương trình chủ. Nếu người dùng được phép cung cấp lambda hoặc đoạn mã tùy ý, họ có thể gọi bất kỳ API nào mà ngữ cảnh thực thi cho phép. Vì vậy, không nên coi DSL nhúng là sandbox tự động.

Với mã chỉ do lập trình viên tin cậy viết và được biên dịch như một phần của ứng dụng, quyền thực thi thường được quản lý theo quy trình phát triển phần mềm. Với cấu hình hoặc mã do người dùng bên ngoài cung cấp, cần đánh giá kỹ hơn:

- Ai được phép tạo và sửa chương trình DSL?
- DSL có cho phép thực thi lambda tùy ý hay chỉ khai báo dữ liệu và biểu thức giới hạn?
- Chương trình có thể truy cập file, mạng, biến môi trường hoặc dịch vụ nhạy cảm không?
- Có giới hạn thời gian, bộ nhớ và số lần gọi dịch vụ không?
- Có ghi nhận người tạo, người phê duyệt và lịch sử thực thi không?
- Có thể xác thực cấu hình trước khi đưa vào môi trường chạy thật không?

Nếu cần cho phép người dùng không đáng tin cậy khai báo quy tắc, một DSL bên ngoài với ngữ pháp và tập biểu thức giới hạn có thể dễ kiểm soát hơn. Dù chọn hướng nào, ranh giới quyền hạn và dữ liệu phải được xác định rõ.

## 17. Quản lý phiên bản và tương thích

Vì DSL nhúng phụ thuộc vào API của ngôn ngữ chủ, thay đổi chữ ký phương thức có thể làm mã DSL hiện tại không biên dịch hoặc thay đổi hành vi.

Một số nguyên tắc:

1. Xem các phương thức và kiểu công khai của DSL là hợp đồng được sử dụng bởi mã bên ngoài.
2. Ưu tiên bổ sung API mới mà vẫn giữ cách gọi cũ trong thời gian chuyển tiếp.
3. Khi cần loại bỏ phương thức, đánh dấu deprecated và cung cấp hướng thay thế.
4. Viết kiểm thử tương thích cho các chương trình DSL đại diện.
5. Ghi rõ phiên bản Java/Kotlin/Groovy/Scala và phiên bản thư viện được hỗ trợ.
6. Phân biệt thay đổi cú pháp API với thay đổi ngữ nghĩa nghiệp vụ.
7. Nếu hành vi thay đổi, nêu rõ tác động lên dữ liệu, kết quả và chương trình DSL đã tồn tại.

Ví dụ, đổi tên `requirePaid()` thành `requirePaymentAccepted()` có thể là thay đổi API dễ hiểu hơn nhưng làm mã nguồn cũ không biên dịch. Ngược lại, giữ tên cũ nhưng đổi ý nghĩa của nó có thể gây lỗi nghiệp vụ khó phát hiện hơn. Cần quản lý cả tính tương thích nguồn lẫn tính tương thích hành vi.

## 18. Những lỗi thiết kế thường gặp

**Cố mô phỏng cú pháp của một ngôn ngữ khác.** Ngôn ngữ chủ có quy tắc riêng. Cố tạo cú pháp trông giống một DSL bên ngoài có thể dẫn đến nhiều dấu ngoặc, overload khó hiểu và lỗi thông báo kém rõ.

**Đặt tên theo cách triển khai.** API như `invokeProcessor`, `setFlag` hoặc `executeInternalStep` làm lộ chi tiết kỹ thuật. Hãy tìm từ vựng miền nếu người dùng cần hiểu hành vi nghiệp vụ.

**Dùng lambda cho mọi thứ.** Lambda ngắn nhưng nhiều khối lồng nhau có thể khó đọc và khó gỡ lỗi. Hãy cân nhắc phương thức có tên, kiểu dữ liệu hoặc builder khi cấu trúc phức tạp.

**Lạm dụng generic và overload.** API có thể trở nên khó suy luận kiểu, gây thông báo lỗi dài hoặc mơ hồ. Nên ưu tiên kiểu rõ và số lượng overload vừa phải.

**Không phân biệt cấu hình với thực thi.** Người dùng không biết lời gọi đã gây tác dụng phụ hay chỉ ghi nhận một khai báo. Tên phương thức và tài liệu cần làm rõ thời điểm thực thi.

**Để thứ tự gọi tạo ra hành vi bất ngờ.** Nếu đổi thứ tự hai lời gọi làm kết quả thay đổi, cần xác định đó là ngữ nghĩa chủ ý và ghi rõ trong tài liệu.

**Không có thông báo lỗi theo miền.** Một exception chung như `IllegalStateException` không đủ nếu người dùng cần biết quy tắc nghiệp vụ nào bị vi phạm. Có thể định nghĩa lỗi miền và gắn ngữ cảnh thích hợp.

**Trộn API DSL với mô hình nghiệp vụ.** Nếu lớp miền chứa nhiều phương thức chỉ phục vụ cú pháp builder, việc thay đổi cách viết DSL sẽ ảnh hưởng đến mô hình. Nên tách phần API và phần ngữ nghĩa khi cần.

**Không kiểm tra chương trình DSL như một sản phẩm.** Cần có ví dụ, kiểm thử ngữ nghĩa, kiểm thử tương thích và tài liệu cho người dùng DSL.

## 19. Quy trình thiết kế một DSL nhúng

Một quy trình thực tế có thể thực hiện theo các bước sau:

1. **Xác định người dùng và mục tiêu:** ai sẽ viết DSL, họ muốn mô tả công việc nào và mức độ quen thuộc với ngôn ngữ chủ ra sao?
2. **Khám phá từ vựng miền:** thu thập khái niệm, hành động, điều kiện, trạng thái và quy tắc từ ví dụ nghiệp vụ.
3. **Xây dựng mô hình miền:** định nghĩa kiểu dữ liệu, quan hệ, bất biến và hành vi cần thiết.
4. **Chọn ngôn ngữ chủ:** xét hệ sinh thái hiện tại, khả năng biểu đạt, kiểu dữ liệu, công cụ và kỹ năng nhóm.
5. **Phác thảo cách sử dụng:** viết vài đoạn DSL mẫu trước khi triển khai API để kiểm tra độ dễ đọc.
6. **Chọn kỹ thuật API:** fluent interface, builder, lambda, generic, extension function hoặc cấu trúc khác phù hợp.
7. **Định nghĩa ngữ nghĩa:** làm rõ thứ tự, thời điểm thực thi, tác dụng phụ, lỗi, trạng thái và xử lý xung đột.
8. **Triển khai và kiểm tra:** xây dựng API, xác thực cấu hình, kiểm thử kiểu, ngữ nghĩa và hành vi đầu cuối.
9. **Tài liệu hóa:** cung cấp ví dụ, hướng dẫn, API reference và thông báo lỗi có ý nghĩa.
10. **Phát hành và duy trì:** quản lý phiên bản, tương thích, phản hồi người dùng và thay đổi mô hình miền.

### Phác thảo API trước khi viết phần triển khai

Trước khi tạo nhiều lớp, hãy viết một số chương trình ví dụ thể hiện trải nghiệm mong muốn. Chẳng hạn:

~~~java
orderPolicy("standard")
    .requirePaymentAccepted()
    .reserveAvailableItems()
    .allowCancellationBeforeShipment()
    .build();
~~~

Sau đó kiểm tra với người dùng:

- Họ có hiểu ý nghĩa từng dòng không?
- Có thuật ngữ nào không đúng với cách gọi trong nghiệp vụ không?
- Có quy tắc quan trọng nào chưa thể diễn đạt không?
- Có trường hợp nào cần tham số hoặc điều kiện rõ hơn không?
- Có thể đọc cấu hình mà không phải xem mã triển khai không?

Nếu ví dụ ban đầu đã khó đọc, việc triển khai thêm nhiều lớp thường không giải quyết được vấn đề cốt lõi. Hãy điều chỉnh cách diễn đạt và mô hình trước khi mở rộng API.

## 20. Cách đánh giá chất lượng DSL nhúng

Có thể đánh giá DSL nhúng qua nhiều góc độ:

| Tiêu chí | Câu hỏi đánh giá |
|---|---|
| Tính biểu đạt | API có diễn đạt được các khái niệm và quy tắc quan trọng của miền không? |
| Khả năng đọc | Người có kiến thức miền có hiểu cấu hình mà không cần lần theo toàn bộ mã nguồn thư viện không? |
| An toàn kiểu | Trình biên dịch có phát hiện được những cách sử dụng sai có thể phát hiện tĩnh không? |
| Ngữ nghĩa rõ ràng | Thứ tự gọi, thời điểm thực thi, tác dụng phụ và lỗi có được định nghĩa không? |
| Khả năng tích hợp | DSL có làm việc tự nhiên với đối tượng, dịch vụ và thư viện của ứng dụng không? |
| Khả năng kiểm thử | Có thể kiểm tra riêng cấu hình, ngữ nghĩa và kết quả thực thi không? |
| Trải nghiệm công cụ | IDE có hỗ trợ gợi ý, điều hướng, tái cấu trúc và thông báo lỗi hữu ích không? |
| Khả năng bảo trì | API có thể mở rộng và thay đổi mà không phá vỡ quá nhiều chương trình DSL không? |
| Tính bảo mật | Quyền thực thi và khả năng truy cập tài nguyên có được giới hạn phù hợp không? |
| Chi phí học | Người dùng mục tiêu cần biết bao nhiêu về ngôn ngữ chủ để sử dụng DSL hiệu quả? |

Một DSL có cú pháp ngắn nhưng người dùng phải biết nhiều chi tiết nội bộ có thể có chi phí học cao. Một DSL tường minh hơn đôi khi lại dễ bảo trì và dễ gỡ lỗi hơn. Cần đánh giá trên các tác vụ thực tế, không chỉ dựa vào số dòng mã.

## 21. Bài tập minh họa

### Bài tập 1: Nhận diện DSL nhúng

Xem các đoạn mã sau và xác định phần nào là DSL nhúng, phần nào là ngôn ngữ ngoài được lưu trong chuỗi.

~~~java
// A
orders.stream()
    .filter(Order::isPaid)
    .toList();

// B
String query = "select * from orders where status = 'PAID'";
connection.prepareStatement(query);

// C
assertThat(order.status()).isEqualTo(OrderStatus.PAID);
~~~

Gợi ý: A và C sử dụng API Java để biểu diễn thao tác chuyên biệt; B lưu một câu SQL có cú pháp và bộ xử lý riêng trong chuỗi Java.

### Bài tập 2: Thiết kế API

Hãy thiết kế một DSL nhúng để mô tả chính sách giảm giá. DSL cần hỗ trợ:

- Đặt tên chính sách.
- Xác định điều kiện áp dụng theo hạng khách hàng.
- Xác định mức giảm theo phần trăm.
- Giới hạn số tiền giảm tối đa.
- Xác định thời gian hiệu lực.
- Xây dựng đối tượng chính sách sau khi kiểm tra cấu hình.

Một cách sử dụng mong muốn có thể là:

~~~java
discountPolicy("member-sale")
    .forCustomerTier(CustomerTier.GOLD)
    .percent(10)
    .maximumDiscount(Money.of(500_000))
    .validDuring(period)
    .build();
~~~

Hãy xác định kiểu dữ liệu, chữ ký phương thức, bất biến và thông báo lỗi cần có. Ví dụ, phần trăm phải nằm trong phạm vi hợp lệ, mức giảm tối đa không âm và thời gian kết thúc phải sau thời gian bắt đầu.

### Bài tập 3: Xác định ngữ nghĩa

Giả sử DSL cho phép khai báo nhiều quy tắc giảm giá. Hãy trả lời:

- Nếu một khách hàng thỏa mãn hai quy tắc, áp dụng cả hai hay chỉ quy tắc ưu tiên cao nhất?
- Thứ tự khai báo có ảnh hưởng đến kết quả không?
- Điều kiện được đánh giá khi xây dựng chính sách hay khi tính giá?
- Nếu dữ liệu hạng khách hàng thay đổi trong lúc thực thi, dùng giá trị nào?
- Có cần ghi lại quy tắc nào đã tạo ra mức giảm cuối cùng không?

Các câu hỏi này cho thấy DSL cần ngữ nghĩa được xác định trước khi triển khai API.

## 22. Kết luận về cách sử dụng DSL nhúng

DSL nhúng cho phép xây dựng ngôn ngữ chuyên biệt ngay trong một ngôn ngữ lập trình tổng quát. Bằng cách kết hợp fluent interface, builder, lambda, generic, kiểu dữ liệu miền và các tính năng đặc thù của ngôn ngữ chủ, nhóm có thể tạo API diễn đạt nghiệp vụ mà vẫn tận dụng trình biên dịch, IDE, thư viện và quy trình phát triển hiện có.

Đổi lại, cú pháp của DSL bị giới hạn bởi ngôn ngữ chủ và người dùng thường cần hiểu ngôn ngữ đó. Nhóm thiết kế phải xác định rõ ngữ nghĩa, thời điểm thực thi, tác dụng phụ, cách xử lý lỗi và chính sách tương thích. Một DSL nhúng hiệu quả cần giúp người dùng diễn đạt đúng công việc bằng thuật ngữ miền, đồng thời giữ cho API có kiểu, dễ đọc, dễ kiểm thử và có thể duy trì lâu dài.
