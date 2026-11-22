# Truyền quy tắc nghiệp vụ qua Predicate hoặc Function trong Java

## 1. Mục tiêu

Trong nhiều ứng dụng, **quy trình xử lý không đổi** nhưng **quy tắc quyết định hoặc tính toán lại thay đổi**. Ví dụ: quy trình báo giá đơn hàng luôn đi qua các bước chọn đơn hợp lệ, tính tiền và trả kết quả; tuy nhiên, điều kiện chọn đơn và chính sách giá có thể khác nhau giữa khách VIP, chương trình khuyến mãi hoặc từng kênh bán hàng.

Thay vì viết nhiều phương thức chứa gần như cùng một vòng lặp, Java có thể **nhận quy tắc nghiệp vụ dưới dạng một đối tượng hành vi**:

- **Predicate<T>**: quy tắc **kiểm tra/ra quyết định**, trả về **boolean**.
- **Function<T,R>**: quy tắc **biến đổi một đầu vào T thành kết quả R**.
- API điều phối nhận các hành vi ấy làm **tham số**, nên luồng xử lý giữ ổn định trong khi chính sách có thể được thay thế hoặc phối hợp.

Sau bài học, bạn có thể nhận diện bài toán thích hợp, thiết kế chữ ký API nhận hàm, dùng lambda và method reference, kết hợp điều kiện bằng Predicate, kết hợp phép tính bằng Function, sử dụng generic wildcard đúng cách, kiểm thử chính sách độc lập và quản lý các rủi ro về dữ liệu không hợp lệ, hiệu ứng phụ và lỗi nghiệp vụ.

## 2. Bản chất của “truyền quy tắc nghiệp vụ”

Một **quy tắc nghiệp vụ** là một quyết định hoặc phép tính có ý nghĩa đối với ứng dụng, ví dụ:

- Đơn hàng có đủ điều kiện hưởng ưu đãi không?
- Đơn hàng có được đưa vào danh sách duyệt tự động không?
- Một sản phẩm có thể bán ở thị trường hiện tại không?
- Tổng tiền sau một chính sách giảm giá là bao nhiêu?
- Dữ liệu đầu vào cần được chuyển thành đối tượng kết quả nào?

Trong mô hình **higher-order function**, phương thức có thể **nhận hàm như tham số**. Với Java, lambda được gán vào functional interface và có thể truyền đi như giá trị của interface ấy.

Ví dụ tối giản:

~~~java
import java.util.function.Predicate;

static boolean approved(int score, Predicate<Integer> rule) {
    return rule.test(score);
}
~~~

Đây là phương thức minh họa phải được đặt trong một lớp. Khi gọi:

~~~java
boolean strict = approved(75, score -> score >= 80);
boolean relaxed = approved(75, score -> score >= 70);
~~~

Kết quả: **strict = false**, **relaxed = true**. Phương thức **approved** không sửa đổi; thứ thay đổi là **rule** mà caller cung cấp.

Điểm cần lưu ý: đây là cách **tách phần quyết định** khỏi **phần điều phối**, không phải “cho phép người dùng bất kỳ chạy code Java”. Quy tắc vẫn cần được cung cấp bởi mã đã được tin cậy, kiểm thử và triển khai theo quy trình của ứng dụng.

## 3. Predicate<T>: truyền quy tắc điều kiện

### 3.1. Chữ ký và ý nghĩa

`java.util.function.Predicate<T>` là functional interface có SAM:

~~~java
boolean test(T value);
~~~

Nó nhận một T và trả **true/false**. Trong nghiệp vụ, hãy đặt tên quy tắc sao cho ý nghĩa của `true` rõ ràng: **isEligible**, **canPublish**, **passesRiskCheck**, **isValidOrder**.

Ví dụ phân loại đơn theo giá trị:

~~~java
record Order(long totalVnd, boolean vip) { }

Predicate<Order> highValue =
        order -> order.totalVnd() >= 100_000;
Predicate<Order> vipCustomer =
        Order::vip;
~~~

Các dòng trên minh họa trong ngữ cảnh đã import `java.util.function.Predicate`; chúng không tạo file Java có main độc lập. Có thể chuyển từng quy tắc cho cùng một API:

~~~java
static List<Order> select(
        List<Order> orders,
        Predicate<? super Order> rule) {
    return orders.stream().filter(rule).toList();
}
~~~

Đoạn này cần import `java.util.List`, có `Order` và đặt trong một lớp. Caller quyết định quy tắc còn phương thức `select` chỉ chịu trách nhiệm duyệt và chọn dữ liệu.

### 3.2. Kết hợp các quy tắc nhỏ

Predicate có các default method:

- **and(other)**: cả hai điều kiện cùng true.
- **or(other)**: một trong hai true.
- **negate()**: phủ định điều kiện.
- **Predicate.not(...)**: cách viết phủ định thuận tiện trong một số ngữ cảnh.

~~~java
Predicate<Order> eligible = highValue.and(vipCustomer);
Predicate<Order> broad = highValue.or(vipCustomer);
Predicate<Order> notVip = vipCustomer.negate();
~~~

**and** và **or** dùng cơ chế **short-circuit**: `and` không kiểm tra vế sau khi vế trước false; `or` không kiểm tra vế sau khi vế trước true. Nếu kiểm tra có thể ném exception, hoặc vế đầu giúp bảo vệ null cho vế sau, thứ tự kiểm tra phải được chọn cẩn thận.

Ví dụ:

~~~java
Predicate<String> notNull = text -> text != null;
Predicate<String> notBlank = text -> !text.isBlank();

Predicate<String> acceptable = notNull.and(notBlank);
System.out.println(acceptable.test(null)); // false
~~~

Kiểm tra null trước khi gọi `isBlank()` giúp tránh NullPointerException. Nếu đảo thứ tự hai predicate trong điều kiện trên, null có thể làm chương trình thất bại.

### 3.3. Phân biệt kiểm tra điều kiện với xác thực lỗi

Một `Predicate<Order>` chỉ trả boolean, nên tự nó không giải thích **vì sao một đơn không được chọn**. Nếu nghiệp vụ cần trả danh sách lỗi đầy đủ, mã lỗi hoặc thông báo chi tiết, hãy dùng kiểu kết quả như `ValidationResult` hoặc một lớp kiểm tra riêng, thay vì cố nhét mọi thông tin vào true/false.

**filter(rule)** chỉ thích hợp khi ứng dụng **chủ ý loại bỏ** những phần tử không đạt điều kiện. Đối với hệ thống thanh toán hoặc nhập liệu bắt buộc báo lỗi, việc âm thầm lọc bỏ bản ghi có thể vi phạm yêu cầu nghiệp vụ.

## 4. Function<T,R>: truyền chính sách tính toán hoặc chuyển đổi

### 4.1. Chữ ký

`java.util.function.Function<T,R>` có SAM:

~~~java
R apply(T value);
~~~

Nó biến một đầu vào kiểu T thành một đầu ra kiểu R. Khác với Predicate, hàm không giới hạn kết quả là boolean.

Ví dụ:

~~~java
Function<Order, Long> regularPrice = Order::totalVnd;
Function<Order, String> orderLabel =
        order -> "Total=" + order.totalVnd();
~~~

Đây là các đoạn minh họa sử dụng record `Order` đã mô tả ở phần 3. Một API có thể nhận chính sách để tính giá:

~~~java
static <T, R> R applyPolicy(
        T item,
        Function<? super T, ? extends R> policy) {
    return policy.apply(item);
}
~~~

Hàm `applyPolicy` không cần biết nghiệp vụ giá hoặc trình bày cụ thể; caller quyết định quy tắc biến đổi.

### 4.2. Ghép các phép biến đổi

`Function` có hai phương thức quan trọng:

- **f.andThen(g)**: chạy f trước, dùng kết quả để chạy g.
- **f.compose(g)**: chạy g trước, dùng kết quả để chạy f.

~~~java
Function<Integer, Integer> addTwo = n -> n + 2;
Function<Integer, Integer> doubleIt = n -> n * 2;

int x = addTwo.andThen(doubleIt).apply(3); // 10
int y = addTwo.compose(doubleIt).apply(3); // 8
~~~

Với cùng đầu vào 3, thứ tự thực hiện làm kết quả khác nhau. Trong nghiệp vụ, “làm tròn trước khi tính thuế” và “tính thuế trước khi làm tròn” cũng có thể khác nhau; không được đổi thứ tự tùy ý.

Khi dùng hàm tính giá, nên xác định rõ **đơn vị tiền, chính sách làm tròn, overflow và các bước được phép kết hợp**. Function chỉ cung cấp cấu trúc gọi hàm, không tự xác định quy tắc tài chính.

## 5. Tách điều phối khỏi chính sách: thiết kế API tổng quát

Giả sử một service nhận danh sách phần tử, một quy tắc chọn và một chính sách biến đổi:

~~~java
static <T, R> List<R> process(
        List<T> items,
        Predicate<? super T> selected,
        Function<? super T, ? extends R> transform) {
    return items.stream()
            .filter(selected)
            .<R>map(transform)
            .toList();
}
~~~

Đây là phương thức minh họa, cần đặt trong lớp có import `List`, `Predicate`, `Function`.

Ba trách nhiệm riêng:

1. **items**: dữ liệu nguồn.
2. **selected**: quyết định mục nào đi tiếp.
3. **transform**: tạo kết quả cho từng mục đã qua điều kiện.

Việc dùng generic **T,R** làm service độc lập với miền nghiệp vụ cụ thể. Hai wildcard có chủ đích:

- **Predicate<? super T>**: Predicate có thể nhận T hoặc supertype của T.
- **Function<? super T, ? extends R>**: hàm có thể nhận T/supertype và trả R/subtype.

**Chú ý cú pháp `.<R>map(transform)`:** đây là **explicit type witness** cho `Stream.map`. Nó giúp Java ấn định kiểu phần tử đầu ra của stream thành đúng R của phương thức process, thay vì suy luận ra một capture type của `? extends R` trong một số ngữ cảnh. Không có cast không an toàn.

Ưu điểm: không nhân bản vòng lặp cho từng biến thể. Thêm chính sách mới chỉ cần cung cấp Predicate/Function mới, miễn phù hợp chữ ký và hợp đồng nghiệp vụ.

Giới hạn: `process` sẽ thực thi hành vi do caller cung cấp, gồm cả lỗi hoặc side effect của chúng; nó không tự bảo đảm rằng các chính sách là đúng, thuần hay có cùng hiệu năng.

## 6. Ví dụ Java 17 hoàn chỉnh: lựa chọn đơn và tính báo giá

Bài toán:

- Hệ thống nhận bốn đơn hàng.
- **Điều kiện hợp lệ cơ bản:** đơn không null, số lượng lớn hơn 0, đơn giá không âm.
- **Chính sách A:** báo giá gốc cho mọi đơn hợp lệ.
- **Chính sách B:** chỉ nhận đơn VIP hợp lệ, sau đó giảm trực tiếp 5.000 VND trên tổng mỗi đơn, nhưng không cho kết quả âm.
- Service giữ nguyên; chỉ thay hai đối tượng hành vi.

Ví dụ dùng record bất biến cho `Order` và `Quote`; mọi phép nhân tiền sử dụng `Math.multiplyExact` để phát hiện overflow. Các thao tác in console chỉ ở `main`.

Lưu file **BusinessRuleDemo.java**:

~~~java
import java.util.List;
import java.util.Objects;
import java.util.function.Function;
import java.util.function.Predicate;

public class BusinessRuleDemo {
    record Order(String id, int quantity, long unitPriceVnd, boolean vip) { }

    record Quote(String orderId, long totalVnd) { }

    static <T, R> List<R> process(
            List<T> items,
            Predicate<? super T> selected,
            Function<? super T, ? extends R> transform) {
        Objects.requireNonNull(items, "items");
        Objects.requireNonNull(selected, "selected");
        Objects.requireNonNull(transform, "transform");

        return items.stream()
                .filter(selected)
                .<R>map(transform)
                .toList();
    }

    static List<String> display(List<Quote> quotes) {
        return quotes.stream()
                .map(q -> q.orderId() + "=" + q.totalVnd())
                .toList();
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", 2, 15_000, true),
                new Order("B", 1, 20_000, false),
                new Order("C", 1, 10_000, true),
                new Order("D", 0, 25_000, true)
        );

        Predicate<Order> valid = o -> o != null
                && o.quantity() > 0
                && o.unitPriceVnd() >= 0;

        Predicate<Order> vipAndValid = valid.and(Order::vip);

        Function<Order, Quote> regularPrice = o ->
                new Quote(
                        o.id(),
                        Math.multiplyExact((long) o.quantity(),
                                o.unitPriceVnd())
                );

        Function<Quote, Quote> discount = q ->
                new Quote(
                        q.orderId(),
                        Math.max(0L, q.totalVnd() - 5_000)
                );

        Function<Order, Quote> vipPrice =
                regularPrice.andThen(discount);

        List<Quote> regular = process(
                orders, valid, regularPrice);

        List<Quote> vip = process(
                orders, vipAndValid, vipPrice);

        System.out.println("Regular: " + display(regular));
        System.out.println("VIP: " + display(vip));
        System.out.println("Original size: " + orders.size());
    }
}
~~~

Biên dịch và chạy với JDK 17 hoặc mới hơn:

~~~bash
javac BusinessRuleDemo.java
java BusinessRuleDemo
~~~

**Đầu ra chính xác:**

~~~text
Regular: [A=30000, B=20000, C=10000]
VIP: [A=25000, C=5000]
Original size: 4
~~~

### 6.1. Đọc từng bước

- **valid** bảo vệ điều kiện số lượng dương và đơn giá không âm. Đơn **D** có quantity=0 nên không được chọn.
- **vipAndValid** ghép `valid.and(Order::vip)`. Đơn **B** hợp lệ về số lượng nhưng không phải VIP, nên chỉ xuất hiện trong báo giá gốc.
- **regularPrice** nhận Order và tạo một **Quote** mới. Đơn A có 2 × 15.000 = 30.000 VND; B có 20.000; C có 10.000.
- **discount** nhận Quote đã tính tiền và tạo Quote mới giảm 5.000, với `Math.max(0L,...)` để không tạo số âm. Đây là **chính sách giảm cố định trên mỗi đơn**, không phải giảm theo phần trăm hoặc cho toàn bộ danh sách.
- **vipPrice = regularPrice.andThen(discount)** xây dựng một Function mới: tính giá gốc rồi áp dụng giảm giá. Với A ra 25.000, C ra 5.000.
- Cả hai lời gọi `process` sử dụng **cùng một thuật toán duyệt → lọc → map**, nhưng truyền chính sách khác nhau.
- Danh sách **orders** còn 4 phần tử. `stream().filter().map().toList()` không xóa phần tử khỏi nguồn. Các record trong ví dụ chứa các trường primitive và String nên không có mutation do các phương thức này.

**Giới hạn nghiệp vụ:** ví dụ minh họa số tiền không âm và tránh overflow khi nhân, nhưng chưa là engine tính tiền production: cần quy định currency, thuế, tỷ giá, thứ tự áp chiết khấu, làm tròn và kiểm tra kết quả tổng nếu có cộng nhiều khoản. Không nên trừ số tiền tùy tiện khi dữ liệu có thể âm hoặc đã vượt phạm vi kiểu.

## 7. Vì sao đây là truyền hành vi, không phải truyền kết quả?

So sánh hai cách:

~~~java
// Truyền giá trị boolean đã tính:
boolean allowed = someOrder.vip();

// Truyền quy tắc sẽ được áp dụng cho từng Order:
Predicate<Order> rule = Order::vip;
~~~

Ở cách đầu, `allowed` chỉ mô tả kết quả cho **một đối tượng tại một thời điểm**. Ở cách sau, `rule` đại diện cho **hành vi có thể chạy nhiều lần** với các Order khác nhau, do đó service có thể quyết định thời điểm và phần tử cần kiểm tra.

Tương tự, `Function<Order,Quote>` là quy tắc **tạo Quote từ bất kỳ Order phù hợp**, không phải một Quote đã được tạo trước.

Truyền hành vi đặc biệt hữu ích khi:

- Các module có cùng luồng xử lý nhưng chính sách khác nhau.
- Cần cấu hình chính sách theo khách hàng, kênh, sản phẩm hoặc thời điểm.
- Cần thử nhiều chính sách trong unit test mà không khởi động database/web server.
- Cần tái sử dụng cùng API duyệt, lọc, chuyển đổi với nhiều kiểu dữ liệu.

Dù vậy, đừng lạm dụng lambda cho các quy tắc lớn nhiều nhánh khó đặt tên. Với nghiệp vụ phức tạp, một lớp `PricingPolicy` hoặc `EligibilityPolicy` được đặt tên rõ và có dependency hợp lệ sẽ dễ quản lý hơn.

## 8. Khác biệt giữa Predicate, Function và những interface khác

| Giao diện | SAM | Hợp đồng nghiệp vụ điển hình |
| --- | --- | --- |
| **Predicate<T>** | `boolean test(T t)` | Kiểm tra điều kiện đúng/sai |
| **Function<T,R>** | `R apply(T t)` | Chuyển đổi hoặc tính kết quả |
| **Consumer<T>** | `void accept(T t)` | Thực hiện hành động, không trả kết quả |
| **Supplier<T>** | `T get()` | Cung cấp giá trị khi được gọi |
| **BiPredicate<T,U>** | `boolean test(T t,U u)` | Kiểm tra điều kiện cần hai đầu vào |
| **BiFunction<T,U,R>** | `R apply(T t,U u)` | Tính kết quả từ hai đầu vào |
| **UnaryOperator<T>** | `T apply(T t)` | Một Function<T,T> cho phép biến đổi cùng kiểu |

Nếu quy tắc “có đủ điều kiện không?” chỉ cần true/false, hãy chọn Predicate. Nếu cần **giải thích vì sao không đủ điều kiện**, Predicate chưa đủ: hãy dùng kết quả có dữ liệu lỗi. Nếu cần **cập nhật hệ thống** thay vì trả một giá trị, Consumer hoặc phương thức nghiệp vụ có tên rõ có thể phù hợp hơn.

### 8.1. BiPredicate khi quy tắc phụ thuộc hai giá trị

Ví dụ điều kiện xét duyệt cần Order và cấu hình:

~~~java
record Limit(long maxVnd) { }

BiPredicate<Order, Limit> withinLimit =
        (order, limit) -> order.totalVnd() <= limit.maxVnd();
~~~

Đây là đoạn minh họa dựa trên một kiểu Order có `totalVnd()`, **khác với record Order trong chương trình ở phần 6** (nó có quantity và unitPriceVnd). Khi dùng thực tế, phải định nghĩa cùng một mô hình dữ liệu nhất quán hoặc tạo hàm tính tổng phù hợp.

Có thể cố định cấu hình vào một lambda nhận một tham số:

~~~java
Limit currentLimit = new Limit(100_000);
Predicate<Order> rule =
        order -> withinLimit.test(order, currentLimit);
~~~

Khi `currentLimit` là biến cục bộ được capture, nó phải **final hoặc effectively final**. Nếu muốn thay đổi cấu hình tại runtime, không nên âm thầm đọc global mutable state không có chính sách quản lý. Hãy cân nhắc truyền một snapshot cấu hình hoặc cập nhật bộ quy tắc ở một điểm đồng bộ rõ ràng.

## 9. Kiểm thử chính sách độc lập và kiểm thử API

Tách điều phối và luật giúp có hai nhóm unit test:

**Nhóm A — test quy tắc riêng:**

- `valid.test(order)` trả false cho quantity=0.
- `vipAndValid.test(order)` trả false nếu không phải VIP.
- `regularPrice.apply(order)` nhân số lượng và đơn giá chính xác.
- `discount.apply(quote)` giảm đúng 5.000 và không tạo giá trị âm.
- `regularPrice.andThen(discount)` bảo toàn thứ tự tính rồi giảm.

**Nhóm B — test quy trình tổng quát:**

- `process` chỉ gọi mapper cho phần tử được Predicate chấp nhận.
- `process` giữ encounter order của `List` đầu vào khi stream tuần tự.
- `process` trả danh sách rỗng với dữ liệu rỗng.
- `process` từ chối tham số hàm null theo chính sách Objects.requireNonNull.
- Nếu Predicate/Function ném exception, service không che giấu lỗi mà để caller xử lý theo hợp đồng.

Ví dụ kiểm tra ngay sau khi tạo `vip` trong `main`:

~~~java
List<String> expected = List.of("A=25000", "C=5000");
if (!display(vip).equals(expected)) {
    throw new AssertionError("Unexpected VIP results");
}
~~~

Đây là đoạn thêm vào chương trình ở phần 6; không phải file độc lập. Với dự án thực tế, dùng JUnit và bổ sung các ca giá trị biên, overflow, lỗi từ policy, null, và kết quả khi input bị thay đổi.

Không nên chỉ test “hàm đã được gọi hay chưa” rồi bỏ qua ý nghĩa nghiệp vụ. Mục tiêu là xác nhận **chính sách đúng**, **service thực thi đúng chính sách được truyền** và **hợp đồng đầu vào/đầu ra** được giữ.

## 10. Quy tắc tham số và wildcard: linh hoạt mà an toàn kiểu

Cụm chữ ký:

~~~java
Predicate<? super T>
Function<? super T, ? extends R>
~~~

được thiết kế theo quy tắc **PECS**:

- `Predicate` nhận (tiêu thụ) một T, nên chấp nhận Predicate của T hoặc supertype T.
- `Function` nhận T (consumer input) và tạo R (producer output), nên `? super T` ở đầu vào, `? extends R` ở đầu ra.

Ví dụ một API xử lý Dog có thể nhận `Predicate<Animal>`; một mapper nhận Animal, trả String vẫn có thể được dùng khi service mong kết quả CharSequence.

~~~java
Predicate<Animal> hasName = animal -> animal.name() != null;
Function<Animal, String> label = Animal::name;

List<Dog> dogs = /* dữ liệu Dog có sẵn */;
List<CharSequence> labels =
        process(dogs, hasName, label);
~~~

Đây là mảnh ghép trong ngữ cảnh có Animal, Dog và helper `process`; không phải chương trình chạy độc lập. Nó minh họa việc xây dựng API nhận hành vi rộng hơn mà không cần cast.

**Quan trọng:** các kiểu generic cụ thể của Java vẫn invariant. `Function<Animal,String>` không đương nhiên là `Function<Dog,CharSequence>`. Wildcard ở **tham số API** mới mô tả được một họ hành vi tương thích.

Đừng khai báo mọi biến bằng wildcard nếu không cần. Implementation cụ thể có tên và kiểu chính xác như `Function<Order,Quote>` thường dễ đọc, dễ suy luận kiểu và dễ gọi method hơn.

## 11. Tránh hiệu ứng phụ trong Predicate và Function

Các callback có thể chạy nhiều lần, chỉ chạy với một số phần tử, hoặc được thực thi bởi framework ở thời điểm mà caller không trực tiếp kiểm soát. Một policy nên càng **dễ dự đoán và dễ kiểm thử** càng tốt.

Ví dụ **không nên** phụ thuộc vào trạng thái global thay đổi tùy lúc:

~~~java
static int promotionCounter = 0;

Predicate<Order> dependsOnCallCount = order ->
        ++promotionCounter % 2 == 0;
~~~

Đây là mảnh ghép minh họa nếu đặt trong lớp có trường static và kiểu Order phù hợp. Hai lời gọi với cùng một Order có thể trả kết quả khác nhau. Nếu chuyển sang parallel stream, phép `++` trên biến chia sẻ còn có thể gây race condition.

**Rủi ro:**

- Không ổn định khi gọi lại: cùng đầu vào cho kết quả khác vì có hidden state.
- Predicate có side effect có thể làm thứ tự đánh giá trở nên quan trọng.
- `and/or` short-circuit có thể không gọi vế thứ hai.
- `Stream` có đặc tính lazy và khả năng tối ưu; không được đặt những hiệu ứng bắt buộc vào `map/filter` rồi dựa vào số lần chạy callback để thực thi nghiệp vụ.
- `parallelStream` có thể chạy callback đồng thời và không bảo đảm thứ tự thực thi side effect.

**Hướng thiết kế:** đưa giá trị chính sách (mức giảm, ngưỡng, thời điểm hiệu lực) vào các tham số hoặc đối tượng cấu hình được quản lý. Tách phần đọc/ghi database, gửi thông báo và log bắt buộc khỏi phần Predicate/Function tính toán nếu có thể.

Không phải mọi Function đều là hàm thuần — giao diện chỉ nói về chữ ký. Sự “thuần” phụ thuộc implementation và mọi trạng thái mà nó truy cập.

## 12. Quản lý lỗi và chính sách thất bại

Một Predicate có thể ném exception và Function cũng vậy. Chữ ký SAM của `Predicate.test` và `Function.apply` **không khai báo checked exception**; nếu policy gọi API có checked exception, người viết phải bắt/xử lý hoặc thiết kế abstraction khác.

Ba chính sách thường gặp:

1. **Fail fast:** gặp dữ liệu hay tính toán không hợp lệ thì ném exception, caller nhận và phản hồi lỗi.
2. **Tích lũy lỗi thành dữ liệu:** dùng kiểu `ValidationResult<T>` hoặc record chứa mã lỗi, thông điệp và dữ liệu để trả về tất cả vấn đề; không chỉ dùng Predicate.
3. **Bỏ qua có chủ đích:** dùng filter khi yêu cầu nghiệp vụ cho phép loại phần tử không phù hợp. Có thể thống kê phần tử bị loại ở nơi điều phối, nhưng phải làm rõ vì sao bỏ.

Trong chương trình ví dụ, policy `valid` loại Quantity=0, tức là **lựa chọn nghiệp vụ đã minh thị**. Nếu đơn D phải được hiển thị là “đơn lỗi”, service không nên chỉ lọc mất nó; thay bằng pipeline phân loại hoặc báo lỗi.

### 12.1. Kiểm soát overflow và dữ liệu tiền tệ

`Math.multiplyExact` giúp phát hiện khi phép nhân tràn kiểu long. Tuy nhiên, các phép trừ/cộng/đổi tiền khác cũng cần chính sách tương tự. Đối với tiền tệ có phần thập phân, thường nên dùng `BigDecimal` với scale và RoundingMode được quy định, thay vì double.

Nếu một chính sách đang đọc trường của đối tượng mutable hoặc cấu hình chung, cần kiểm soát tình trạng thay đổi giữa các bước. Dùng immutable record cho dữ liệu đầu vào/đầu ra có thể giảm một số rủi ro, nhưng **record không tạo bất biến sâu** nếu chứa đối tượng mutable.

### 12.2. Chính sách nào chịu trách nhiệm validate?

Không thể giả định vì service đã có Predicate thì mọi Function đều nhận đầu vào hợp lệ: caller khác vẫn có thể gọi Function trực tiếp. Những **bất biến quan trọng của domain** thường nên được bảo vệ ở constructor hoặc phương thức miền nghiệp vụ, đồng thời API điều phối ghi rõ precondition.

Ví dụ: nếu không bao giờ được tạo Quote có tổng âm, constructor Quote có thể kiểm tra điều ấy; trong ví dụ học, quy tắc được thể hiện qua policy với Math.max. Cách tổ chức cụ thể tùy mức đảm bảo mà hệ thống cần.

## 13. Khi nào nên dùng một interface nghiệp vụ có tên?

`Predicate<Order>` tốt cho điều kiện ngắn và rõ ràng. Nhưng nếu chính sách cần:

- Tên phiên bản, mã chính sách, ngày hiệu lực;
- Tham số cấu hình phức tạp;
- Phản hồi lỗi có cấu trúc hoặc giải thích quyết định;
- Nhiều phép tính hoặc nhiều phương thức liên quan;
- Tài nguyên có vòng đời và dependency chuyên biệt;

thì một interface nghiệp vụ có tên có thể dễ quản lý hơn:

~~~java
interface PricingPolicy {
    Quote calculate(Order order);
}
~~~

Đây là đoạn minh họa, dựa trên Order và Quote từ chương trình ở phần 6, không phải file độc lập.

Interface này là **functional interface về mặt cấu trúc** nếu chỉ có đúng một abstract method, nên vẫn có thể triển khai bằng lambda:

~~~java
PricingPolicy policy = order ->
        new Quote(order.id(), 0L);
~~~

Chỉ nên dùng ví dụ `0L` để nhìn cú pháp, **không coi nó là quy tắc giá đúng cho production**. Một class triển khai PricingPolicy có tên rõ ràng là lựa chọn hợp lý khi nghiệp vụ lớn hoặc cần dependency injection. API nhận Predicate/Function và một interface domain không đối lập nhau: cả hai đều là cách truyền hành vi, với mức diễn đạt chuyên ngành khác nhau.

## 14. Sai lầm thường gặp

| Lỗi | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| Truyền **boolean** khi muốn truyền quy tắc | Chỉ kiểm tra một đối tượng, không có hành vi dùng lại | Truyền Predicate<T> |
| Dùng Predicate để trả thông điệp lỗi | Boolean không chứa lý do thất bại | Dùng kiểu kết quả validation |
| Dùng Function có side effect ẩn | Policy khó kiểm thử, phụ thuộc thứ tự/cách gọi | Trả giá trị mới và tách I/O |
| Gọi `Predicate.and` nhưng quên short-circuit | Vế sau có thể không chạy | Đừng đặt hiệu ứng bắt buộc trong predicate |
| Đổi thứ tự các phép Function | Kết quả tiền hoặc validation thay đổi | Viết hợp đồng thứ tự và test cụ thể |
| Nhân tiền không kiểm soát overflow | Có thể trả tổng sai | Math.multiplyExact và quy tắc số học phù hợp |
| Dùng `Function<T,R>` quá hẹp trong API | Khó tái sử dụng hàm nhận supertype/trả subtype | Cân nhắc `Function<? super T,? extends R>` |
| Lọc dữ liệu sai mà không có báo lỗi | Mất bản ghi âm thầm | Tách luồng phân loại lỗi nếu cần |
| Tin rằng stream sẽ tự rollback khi mapper lỗi | Phần việc đã có side effect có thể còn tồn tại | Thiết kế transaction và ranh giới hiệu ứng |
| Đưa chính sách mutable toàn cục vào callback | Kết quả không tái lập, nguy cơ race | Snapshot, tiêm dependency hoặc đồng bộ |

## 15. Bài tập thực hành

### Bài 1: Lọc ứng viên

Một hệ thống có record:

~~~java
record Candidate(String name, int experienceYears, boolean certified) { }
~~~

Hãy viết Predicate chọn người có **ít nhất 2 năm kinh nghiệm** và **đã có chứng chỉ**.

**Gợi ý:**

~~~java
Predicate<Candidate> enoughExperience =
        c -> c.experienceYears() >= 2;
Predicate<Candidate> certified = Candidate::certified;

Predicate<Candidate> eligible =
        enoughExperience.and(certified);
~~~

Các đoạn này có thể đưa vào một lớp có import Predicate và khai báo record Candidate. Thử với người có kinh nghiệm 1/2 năm và trường certified true/false.

### Bài 2: Truyền Function cho cùng một API

Một danh sách số lượng `List<Integer>` cần xử lý theo hai chính sách:

- Chính sách A: nhân đôi.
- Chính sách B: cộng thêm 10.

**Gợi ý:**

~~~java
Function<Integer, Integer> doubleIt = n -> n * 2;
Function<Integer, Integer> plusTen = n -> n + 10;

List<Integer> values = List.of(1, 2, 3);
List<Integer> first = process(
        values, n -> true, doubleIt);
List<Integer> second = process(
        values, n -> true, plusTen);
~~~

Với helper `process` ở phần 5, **first = [2, 4, 6]** và **second = [11, 12, 13]**. Đây là mảnh ghép chứ không phải file chạy độc lập; không nên dùng `n -> true` nếu bài toán thật có quy tắc chọn dữ liệu cần xác minh.

### Bài 3: Thêm chính sách ưu đãi

Trong BusinessRuleDemo, hãy thay chính sách giảm cố định 5.000 VND bằng giảm **10%** cho đơn VIP. Quy định cách làm tròn trước khi code, và kiểm thử đơn có tổng không chia hết cho 10. Hãy giữ nguyên `process`, chỉ tạo Function khác và truyền nó khi gọi.

**Gợi ý:** có thể viết một Function<Order, Quote> áp dụng Math.multiplyExact và phép tính phần trăm thích hợp, hoặc ghép Function<Order,Quote> với Function<Quote,Quote>. Tránh dùng double nếu yêu cầu tiền tệ chính xác; lựa chọn kiểu BigDecimal/long tùy đơn vị nhỏ nhất và hợp đồng làm tròn.

### Bài 4: Chọn API phù hợp

Hệ thống cần phê duyệt hồ sơ và **trả nguyên nhân từ chối**. Có nên thiết kế chỉ `Predicate<Application>` không?

**Đáp án:** Predicate phù hợp nếu caller chỉ cần true/false. Nếu cần nguyên nhân, dùng Function<Application, Decision> hoặc interface có tên với kiểu Decision gồm trạng thái và lý do. Khi đó vẫn có thể truyền hành vi, nhưng dữ liệu trả ra chứa được hợp đồng nghiệp vụ.

### Bài 5: Thiết kế test

Viết test cho service `process` với đầu vào rỗng, policy null, policy ném exception, và một list có phần tử đạt/không đạt điều kiện. Xác nhận chỉ các phần tử đạt điều kiện mới được biến đổi; nếu policy là hàm thuần, test không phụ thuộc trạng thái toàn cục.

## 16. Ghi nhớ

**Truyền quy tắc nghiệp vụ qua Predicate hoặc Function** nghĩa là **đưa cách quyết định/cách tính toán vào tham số của API**, để luồng điều phối có thể dùng lại mà không sao chép code:

- **Predicate<T> — boolean test(T)**: kiểm tra điều kiện, phối hợp bằng `and/or/negate`.
- **Function<T,R> — R apply(T)**: tạo kết quả, phối hợp bằng `andThen/compose`.
- **API nhận hàm**: tách **dữ liệu + quy trình** khỏi **chính sách thay đổi**; dùng wildcard `? super` và `? extends` khi hữu ích.
- **Chính sách rõ ràng**: có tên, hợp đồng đầu vào/đầu ra, xử lý null/lỗi, kiểm soát overflow và các điều kiện domain.
- **Kiểm thử**: xác minh cả từng rule và quy trình áp dụng chúng; không lẫn lọc dữ liệu với báo cáo lỗi bắt buộc.

Cách tiếp cận này giúp một service linh hoạt với nhiều kịch bản nghiệp vụ mà vẫn dễ đọc, dễ thử nghiệm và giảm sự phụ thuộc giữa các lớp.
