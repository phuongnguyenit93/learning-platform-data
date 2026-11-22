# Thay lớp chiến lược đơn giản bằng lambda khi hợp đồng phù hợp

## 1. Bài toán: API nhận hành vi qua Strategy

Trong mẫu thiết kế **Strategy**, phía sử dụng một thuật toán không tự quyết định mọi chi tiết tính toán. Nó nhận một **hợp đồng hành vi** (interface), còn phía gọi lựa chọn cách triển khai. Chẳng hạn hệ thống báo giá cần thay đổi cách tính tổng tiền tùy chương trình khuyến mãi:

- Giá chuẩn: giữ nguyên tổng tiền ban đầu.
- Khách VIP: giảm 10%.
- Đối tác: áp dụng một công thức khác.

Trong Java trước khi có lambda, một chiến lược đơn giản thường được viết thành một lớp triển khai interface. Với Java 8+, **nếu hợp đồng là functional interface và chiến lược chỉ cần một hành vi nhỏ**, có thể truyền lambda hoặc method reference thay cho lớp triển khai. Phần lớn lợi ích nằm ở việc API nhận **hành vi trực tiếp**, không phải ở việc xóa toàn bộ cấu trúc Strategy.

Ví dụ sơ đồ:

```text
PricingService
      │
      └── quote(subtotal, PricingStrategy strategy)
                                │
                                ├── StandardStrategy (class)
                                ├── VipStrategy      (class)
                                └── subtotal -> ...  (lambda)
```

Cả ba cách đều có thể cung cấp một hành vi thỏa hợp đồng `PricingStrategy`. Phương thức `quote` chỉ gọi phương thức của interface; mã gọi quyết định chiến lược cần dùng.

**Điều kiện cốt lõi:** chuyển từ lớp sang lambda phải giữ nguyên hành vi quan sát được và hợp đồng API. Không tự động thay khi lớp còn chứa nhiều trách nhiệm, vòng đời, trạng thái, dữ liệu cấu hình hay identity mà ứng dụng thực sự cần.

## 2. Xác định hợp đồng có phù hợp lambda hay không

Lambda trong Java được gán cho một **functional interface**: interface có đúng **một phương thức trừu tượng** theo quy tắc của ngôn ngữ. Các phương thức `default`, `static` và những phương thức tương ứng với public method của `Object` không biến nó thành interface nhiều phương thức trừu tượng.

Một hợp đồng Strategy tối giản:

```java
@FunctionalInterface
interface PricingStrategy {
    BigDecimal calculate(BigDecimal subtotal);
}
```

Đây là đoạn khai báo interface, cần import `java.math.BigDecimal` để biên dịch trong một tệp Java phù hợp.

- Đầu vào: một `BigDecimal` chứa tạm tính.
- Đầu ra: một `BigDecimal` là kết quả.
- Một hành vi trừu tượng: `calculate`.
- Lambda tương ứng: `subtotal -> subtotal.multiply(new BigDecimal("0.90"))`.

Annotation `@FunctionalInterface` không bắt buộc để lambda hoạt động nhưng rất hữu ích: trình biên dịch sẽ báo lỗi nếu sửa interface khiến hợp đồng không còn hợp lệ. Tên phương thức cụ thể không phải điều làm nên lambda; chính **chữ ký của phương thức trừu tượng duy nhất (SAM)** quyết định số và kiểu tham số cũng như kiểu trả về.

Functional interface có thể có `default` method để bổ sung tiện ích mà vẫn dùng được lambda:

```java
@FunctionalInterface
interface PricingStrategy {
    BigDecimal calculate(BigDecimal subtotal);

    default String description() {
        return "pricing strategy";
    }
}
```

Ngược lại, nếu interface khai báo **hai phương thức trừu tượng độc lập**, chẳng hạn `calculate(...)` và `explain(...)`, thì nó không còn là functional interface; lambda không đủ để cung cấp cả hai hành vi. Có thể cần một lớp triển khai cụ thể, một mô hình chứa hai callback, hoặc điều chỉnh API nếu phù hợp nhu cầu thực tế. Không nên đổi thiết kế chỉ để ép dùng cú pháp lambda.

## 3. Trước và sau: thay lớp Strategy đơn giản nhưng giữ API

Ví dụ chạy độc lập sau cho thấy cả cách truyền lớp truyền thống và cách truyền lambda vào **cùng một API**. Lưu thành tệp `StrategyLambdaDemo.java`:

```java
import java.math.BigDecimal;
import java.util.Objects;

public class StrategyLambdaDemo {

    @FunctionalInterface
    interface PricingStrategy {
        BigDecimal calculate(BigDecimal subtotal);
    }

    // Cách cũ: một class chỉ để triển khai công thức đơn giản.
    static final class TenPercentDiscount implements PricingStrategy {
        @Override
        public BigDecimal calculate(BigDecimal subtotal) {
            return subtotal.multiply(new BigDecimal("0.90"));
        }
    }

    static final class PricingService {
        BigDecimal quote(BigDecimal subtotal, PricingStrategy strategy) {
            Objects.requireNonNull(subtotal, "subtotal");
            Objects.requireNonNull(strategy, "strategy");
            return strategy.calculate(subtotal);
        }
    }

    static BigDecimal keepOriginal(BigDecimal subtotal) {
        return subtotal;
    }

    public static void main(String[] args) {
        PricingService service = new PricingService();
        BigDecimal subtotal = new BigDecimal("100.00");

        PricingStrategy oldStrategy = new TenPercentDiscount();
        BigDecimal oldResult = service.quote(subtotal, oldStrategy);

        PricingStrategy lambdaStrategy =
                amount -> amount.multiply(new BigDecimal("0.90"));
        BigDecimal lambdaResult = service.quote(subtotal, lambdaStrategy);

        // Method reference khi đã có sẵn phương thức phù hợp.
        BigDecimal standardResult =
                service.quote(subtotal, StrategyLambdaDemo::keepOriginal);

        System.out.println("Class: " + oldResult);
        System.out.println("Lambda: " + lambdaResult);
        System.out.println("Method reference: " + standardResult);
    }
}
```

Biên dịch và chạy trên Java 17+:

```bash
javac StrategyLambdaDemo.java
java StrategyLambdaDemo
```

Kết quả:

```text
Class: 90.0000
Lambda: 90.0000
Method reference: 100.00
```

**Lưu ý về số học:** `BigDecimal("100.00")` có scale 2, `BigDecimal("0.90")` có scale 2 nên phép `multiply` tạo kết quả scale 4: `90.0000`. Ví dụ cố ý giữ nguyên scale để kết quả console chính xác. Khi xuất hóa đơn thật, cần một chính sách làm tròn/scale và currency rõ ràng; không suy ra `BigDecimal` tự động định dạng tiền tệ.

Điểm đáng chú ý:

1. `PricingService.quote` không đổi chữ ký: vẫn nhận `PricingStrategy`.
2. `TenPercentDiscount` có thể thay bằng `lambdaStrategy` mà không thay đổi mã của `PricingService`.
3. Với cùng `subtotal` và công thức, cả hai cách trả cùng giá trị.
4. Lambda có **kiểu đích** `PricingStrategy`, nên compiler suy ra `amount` là `BigDecimal`, và kiểm tra kết quả phải tương thích `BigDecimal`.
5. Method reference `StrategyLambdaDemo::keepOriginal` là lựa chọn khác nếu một phương thức đã có chữ ký phù hợp.

Nếu lớp chiến lược cũ chỉ có một phương thức đơn giản, không có trạng thái riêng hay contract khác, phương án lambda thường giảm boilerplate. Tuy nhiên, không nên xóa lớp dùng chung khi nơi khác phụ thuộc tên, kiểu cụ thể hoặc metadata của nó; cần kiểm tra call site và các phụ thuộc của API trong một refactor thực tế.

## 4. Chuyển từng bước theo đúng hợp đồng

Khi gặp một lớp Strategy trong mã nguồn, có thể đi theo trình tự:

**Bước 1 — Xác định vai trò của lớp.** Nó chỉ triển khai một hàm ngắn, hay còn có thêm cấu hình, cache, lifecycle, metrics, tên nghiệp vụ, validation, state, dependency injection? Hãy đọc những nơi gọi interface và nơi khởi tạo lớp.

**Bước 2 — Xác định interface được dùng làm kiểu đích.** Ví dụ `PricingStrategy` ở trên có một abstract method trả `BigDecimal`. Nếu hợp đồng phù hợp, lambda có thể thay một implementation class.

**Bước 3 — Chuyển thân phương thức.** Lớp:

```java
final class NoDiscount implements PricingStrategy {
    @Override
    public BigDecimal calculate(BigDecimal subtotal) {
        return subtotal;
    }
}
```

có thể trở thành:

```java
PricingStrategy noDiscount = subtotal -> subtotal;
```

Hai đoạn trên là ví dụ đặt trong ngữ cảnh đã có `PricingStrategy` và import `BigDecimal`; dòng khai báo biến đặt trong phương thức/khối, không phải một file riêng độc lập.

**Bước 4 — Truyền lambda vào nơi nhận Strategy.** Ví dụ `service.quote(subtotal, amount -> amount)` có thể dùng inline cho một lần gọi; nếu tái sử dụng ở nhiều nơi, nên đặt tên cho biến `PricingStrategy` hoặc method có tên rõ nghĩa.

**Bước 5 — So sánh hành vi được công khai.** Kiểm thử đầu vào bình thường, biên, lỗi, exception, side effect, độ chính xác số học, null handling và các yêu cầu về đồng thời nếu có. Khi cùng hợp đồng nhưng hành vi không khớp, bản chuyển đổi chưa đúng.

**Bước 6 — Loại bỏ lớp cũ chỉ khi không còn nơi nào cần.** Một lớp public có thể đang là API bên ngoài, loại được framework quét, một thành phần DI, hoặc được khách hàng tạo trực tiếp. Cần xét tính tương thích nguồn và nhị phân; không nên xóa chỉ vì một call site có thể viết lambda.

## 5. Chọn functional interface có sẵn hay interface riêng

Nhiều chiến lược đơn giản có thể được mô tả bằng các interface sẵn trong `java.util.function`:

| Hợp đồng hành vi | Functional interface thường dùng | Phương thức SAM |
| --- | --- | --- |
| Nhận một giá trị, trả một giá trị khác | `Function<T, R>` | `R apply(T value)` |
| Nhận và trả cùng kiểu | `UnaryOperator<T>` | `T apply(T value)` |
| Kiểm tra điều kiện | `Predicate<T>` | `boolean test(T value)` |
| Thực hiện hành động không có kết quả | `Consumer<T>` | `void accept(T value)` |
| Tạo/cung cấp giá trị không cần input | `Supplier<T>` | `T get()` |
| So sánh thứ tự hai giá trị | `Comparator<T>` | `int compare(T a, T b)` |

Nếu API chỉ muốn truyền phép biến đổi `BigDecimal -> BigDecimal`, có thể nhận `UnaryOperator<BigDecimal>`. Nhưng một interface riêng như `PricingStrategy` có thể có giá trị vì nó diễn đạt đúng ngôn ngữ nghiệp vụ, Javadoc, quy tắc kiểm tra và ý nghĩa của hợp đồng. Đừng đổi interface riêng thành `Function` chỉ vì trông ngắn hơn; việc chọn kiểu là quyết định API.

Ví dụ dùng built-in strategy `Comparator` trong Java 17; tạo tệp `ComparatorStrategyDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class ComparatorStrategyDemo {
    record Product(String name, int price) {}

    public static void main(String[] args) {
        List<Product> items = new ArrayList<>(List.of(
                new Product("Pen", 5),
                new Product("Book", 20),
                new Product("Bag", 15)
        ));

        Comparator<Product> byPrice = Comparator.comparingInt(Product::price);
        items.sort(byPrice);

        System.out.println(
                items.stream().map(Product::name).toList());

        // Một chiến lược Comparator khác được truyền trực tiếp.
        items.sort((left, right) ->
                right.name().compareTo(left.name()));

        System.out.println(
                items.stream().map(Product::name).toList());
    }
}
```

Chạy:

```bash
javac ComparatorStrategyDemo.java
java ComparatorStrategyDemo
```

Kết quả:

```text
[Pen, Bag, Book]
[Pen, Book, Bag]
```

Giải thích: cách thứ nhất dùng factory `Comparator.comparingInt` với method reference `Product::price`, sắp theo giá tăng dần. Cách thứ hai dùng lambda phù hợp hợp đồng `Comparator<Product>` để so sánh tên theo thứ tự giảm dần: `Pen`, `Book`, `Bag`. API `List.sort` không cần biết lớp triển khai cụ thể của chiến lược.

Lambda chỉ là biểu thức cung cấp một instance thực thi interface. Không nên giả định class hoặc identity runtime của instance, vì Java có thể sử dụng những cách hiện thực khác nhau.

## 6. Kiểu đích và suy luận tham số trong lời gọi API

Một lambda không đứng riêng với một kiểu “lambda” tự suy ra từ cú pháp. Nó cần functional interface do ngữ cảnh cấp: phép gán, đối số phương thức, phép cast hoặc một ngữ cảnh target typing phù hợp.

Ví dụ hợp lệ trong ngữ cảnh `PricingService` đã khai báo:

```java
PricingStrategy fixed = amount -> amount;
BigDecimal result = service.quote(subtotal, amount -> amount);
```

Tham số `amount` là `BigDecimal` vì `PricingStrategy.calculate(BigDecimal)` định nghĩa hợp đồng. Nếu bạn đổi tham số API sang `UnaryOperator<BigDecimal>`, method SAM và target type cũng đổi tương ứng.

Không hợp lệ:

```java
// Thiếu target type cho lambda:
var strategy = amount -> amount;
```

Đây là ví dụ **cố ý không biên dịch**. Dùng `PricingStrategy strategy = amount -> amount;` hoặc `var strategy = (PricingStrategy) (amount -> amount);` nếu muốn giữ `var`.

Một vấn đề khác là **overload ambiguity**. Nếu API có hai overload cùng nhận functional interface tương thích với biểu thức lambda, compiler có thể không chọn được hàm nào. Khi đó nên gán lambda vào biến với kiểu tường minh hoặc ép kiểu đến đúng functional interface:

```java
PricingStrategy policy = amount -> amount;
service.quote(subtotal, policy);
```

Không cần tạo thêm lớp chỉ để “giải quyết” suy luận kiểu nếu chỉ thiếu target type; tuy nhiên với API public nhiều overload khó phân biệt, cân nhắc thiết kế tên phương thức rõ ràng.

## 7. Một số lớp Strategy không nên thay trực tiếp

### 7.1. Lớp giữ trạng thái và vòng đời

Giả sử chiến lược có bộ đếm request, cache, dependency sống lâu hoặc kết nối có lifecycle. Nếu thay bằng lambda capture trạng thái, bạn vẫn phải xác định ai sở hữu, khởi tạo và đóng tài nguyên, cũng như thread safety khi chia sẻ instance. Lambda không mặc nhiên xóa trạng thái hoặc đảm bảo an toàn đa luồng.

Ví dụ một nhà cung cấp chiến lược có cấu hình thay đổi theo thời gian có thể hợp lý hơn dưới dạng object riêng được kiểm thử, quản lý bằng DI và có phương thức thao tác rõ ràng. Nếu có các thao tác `start()` / `stop()` / `calculate()` cùng là một phần contract, một SAM không còn mô tả đủ.

### 7.2. Chiến lược phức tạp cần tên rõ ràng và kiểm thử độc lập

Nếu công thức dài nhiều nhánh, xử lý ngoại lệ, giải thích kết quả hoặc phối hợp nhiều dependency, một lớp có tên cụ thể thường dễ đọc hơn lambda 30 dòng inline. Bạn vẫn có thể dùng method reference:

```java
PricingStrategy configured = pricingEngine::calculate;
```

Đây là đoạn mã minh họa, giả định `pricingEngine.calculate(BigDecimal)` là instance method trả `BigDecimal`. Method reference giữ điểm ghép chiến lược gọn, còn logic phức tạp nằm trong thành phần có tên và vòng đời.

### 7.3. Hợp đồng dựa trên identity, metadata hoặc annotation của lớp

Nếu hệ thống khám phá strategy thông qua annotation trên class, cấu hình bằng class name, serialization, reflection hoặc dependency injection với qualifier/type, chuyển sang lambda có thể phá vỡ cơ chế nhận diện. Java không cam kết tên lớp sinh ra cho lambda và không biến instance lambda thành một component có metadata giống lớp được chú thích. Giữ lớp hoặc đổi kiến trúc registry/metadata trước khi chuyển.

### 7.4. Hợp đồng kiểm soát checked exception

SAM quyết định những checked exception mà lambda được phép ném. Chẳng hạn `Function<T,R>.apply` không khai báo `throws IOException`; một lambda trực tiếp gọi phương thức có thể ném checked `IOException` phải xử lý hoặc chuyển đổi lỗi phù hợp. Nếu chiến lược thật sự có contract checked exception, một functional interface riêng như:

```java
@FunctionalInterface
interface FileStrategy {
    String load(String path) throws java.io.IOException;
}
```

vẫn dùng được lambda, đồng thời giữ hợp đồng lỗi. Chọn kiểu chỉ vì có sẵn `Function` mà làm mất ý nghĩa exception là sai.

### 7.5. Cần nhiều hành vi phối hợp

Một chiến lược gồm `validate`, `execute` và `rollback` độc lập sẽ không thể được biểu diễn toàn bộ bằng một lambda gắn vào interface có ba abstract method. Đừng tự động làm ba callback rời nếu chúng cần chia sẻ invariant, tài nguyên và vòng đời. Dùng một object có interface đầy đủ sẽ dễ giữ đúng hợp đồng hơn.

## 8. Capture và quản lý phụ thuộc khi dùng lambda

Lambda có thể tham chiếu biến cục bộ từ phạm vi ngoài nếu biến đó là `final` hoặc **effectively final**. Khi lambda capture một đối tượng thay đổi được, nó giữ tham chiếu đến đối tượng; không có bảo đảm rằng đối tượng bên trong là immutable hay thread-safe.

Ví dụ một phương thức tạo chiến lược dựa trên tỷ lệ giảm giá:

```java
static PricingStrategy discount(BigDecimal rate) {
    Objects.requireNonNull(rate);
    return subtotal -> subtotal.multiply(BigDecimal.ONE.subtract(rate));
}
```

Đây là đoạn phương thức tĩnh đặt trong lớp có `PricingStrategy`, với import `BigDecimal` và `Objects`. Biến tham số `rate` là effectively final. Cần xét riêng phạm vi hợp lệ của `rate` (ví dụ từ 0 đến 1) và quy tắc làm tròn theo nghiệp vụ; compiler không tự kiểm tra các ràng buộc đó.

Một lỗi phổ biến:

```java
int percent = 10;
PricingStrategy p = subtotal ->
        subtotal.multiply(
                BigDecimal.valueOf(100 - percent)
                        .movePointLeft(2));
percent = 20; // Không hợp lệ: biến percent được capture không effectively final.
```

Đây là **phản ví dụ cố ý không biên dịch**. Nếu muốn một chiến lược với tỷ lệ cố định, hãy tạo biến `final int percent = 10;` và dùng nó. Nếu muốn tỷ lệ có thể cập nhật, mô hình hóa nó thành trạng thái/configuration có ownership rõ ràng, không tìm cách thay đổi biến local đã capture.

Đặc biệt, lambda không nên bị dùng làm identity cho nghiệp vụ, khóa cache hay tên logging. Nên gắn ID riêng như `"STANDARD"`, `"VIP_10"` cho phép tra cứu có kiểm soát.

## 9. Đăng ký Strategy bằng tên nghiệp vụ, truyền lambda vào API

Khi có nhiều chiến lược nhỏ, có thể lưu chúng trong `Map<String, PricingStrategy>` hoặc một registry, kết hợp **ID ổn định** với hành vi. Tạo tệp `PricingRegistryDemo.java`:

```java
import java.math.BigDecimal;
import java.util.Map;
import java.util.Objects;
import java.util.function.UnaryOperator;

public class PricingRegistryDemo {
    static BigDecimal quote(
            BigDecimal subtotal,
            UnaryOperator<BigDecimal> policy) {
        return Objects.requireNonNull(policy).apply(
                Objects.requireNonNull(subtotal));
    }

    public static void main(String[] args) {
        Map<String, UnaryOperator<BigDecimal>> policies = Map.of(
                "STANDARD", amount -> amount,
                "VIP_10", amount ->
                        amount.multiply(new BigDecimal("0.90"))
        );

        BigDecimal subtotal = new BigDecimal("50.00");
        System.out.println(
                quote(subtotal, policies.get("STANDARD")));
        System.out.println(
                quote(subtotal, policies.get("VIP_10")));
    }
}
```

Chạy:

```bash
javac PricingRegistryDemo.java
java PricingRegistryDemo
```

Output:

```text
50.00
45.0000
```

Ứng dụng biết chiến lược theo khóa chuỗi đã công bố, không theo `getClass().getName()` của lambda. Trong hệ thống sản xuất, có thể dùng `enum` hoặc value object cho key để hạn chế nhầm lẫn; phải xử lý trường hợp key không tồn tại, vì `Map.get` sẽ trả `null` và hàm `quote` ở ví dụ sẽ báo lỗi.

Về thời điểm thực thi, `Map.of` lưu các instance chiến lược tại lúc khởi tạo map; mã lambda bên trong chỉ được gọi khi `quote` gọi `apply`. Không nên giả định mọi lambda luôn được JVM tạo instance mới hoặc luôn dùng singleton; identity không phải cơ chế nhận diện chiến lược.

## 10. Kiểm thử trước/sau để bảo vệ hợp đồng

Khi chuyển một class Strategy sang lambda, câu hỏi chính là **người dùng API có quan sát được thay đổi ngoài chủ đích không?** Trường hợp cơ bản nên được kiểm tra bằng cùng tập đầu vào:

| Tình huống | Điều cần so sánh |
| --- | --- |
| Input bình thường | Giá trị trả về của lớp và lambda có tương đương theo hợp đồng không? |
| Dữ liệu biên | Giá trị 0, số âm, chuỗi rỗng, giá trị lớn có được xử lý đúng không? |
| Input không hợp lệ | Validation và exception type/message được giữ theo yêu cầu? |
| Kết quả decimal | Scale, rounding, quy tắc currency và precision có tương thích? |
| Có side effect | Thứ tự, số lần gọi, transaction, logging bắt buộc có thay đổi? |
| Dùng lại nhiều lần | Có sự thay đổi ngoài ý muốn về trạng thái và tính an toàn đồng thời? |
| Mã bên ngoài sử dụng class | Có phụ thuộc public constructor, annotation, serialization, DI hoặc reflection không? |

Trong các ví dụ đơn giản, có thể kiểm thử bằng so sánh kết quả trực tiếp:

```java
BigDecimal subtotal = new BigDecimal("100.00");
PricingStrategy classBased = new TenPercentDiscount();
PricingStrategy lambdaBased =
        n -> n.multiply(new BigDecimal("0.90"));

boolean sameValue =
        classBased.calculate(subtotal)
                .compareTo(lambdaBased.calculate(subtotal)) == 0;
```

Đoạn trên giả định các kiểu từ ví dụ `StrategyLambdaDemo.java` và đặt trong phương thức. Với giá trị `100.00`, `sameValue` là `true`. Chọn `compareTo` khi chỉ cần so sánh **giá trị số** của `BigDecimal`; `equals` còn phân biệt scale. Nếu scale thuộc hợp đồng API, hãy kiểm tra thêm chính xác scale hoặc so sánh `equals` theo yêu cầu.

Các phép đo như `oldStrategy == lambdaStrategy`, `oldStrategy.getClass()` hay hai lần đánh giá lambda có trả cùng instance không **không chứng minh hợp đồng nghiệp vụ đúng**. Ưu tiên kiểm thử kết quả và side effect đã được đặc tả.

## 11. Lỗi thường gặp

1. **Thay class có nhiều trách nhiệm bằng một lambda inline lớn.** Tách logic ra thành phương thức có tên, method reference hoặc giữ lớp khi cần trạng thái, lifecycle và contract phức tạp.
2. **Không xác nhận SAM.** Hai abstract method làm interface không còn là functional interface; hãy kiểm tra chữ ký và sử dụng `@FunctionalInterface` khi thích hợp.
3. **Mất semantic của checked exception.** Đổi một interface khai báo `throws` thành `Function` có thể khiến code không biên dịch hoặc phải thay đổi cách xử lý lỗi. Giữ exception contract cần thiết.
4. **Đổi kiểu API public mà không xem call site.** Dù SAM giống nhau về hình thức, đổi từ `PricingStrategy` sang `Function<BigDecimal,BigDecimal>` vẫn có thể ảnh hưởng các nơi gọi, generic inference và tương thích nhị phân.
5. **Capture mutable state mà không quản lý thread safety.** Một lambda có thể giữ cùng đối tượng mutable mà nhiều luồng dùng chung; nó không tự sao chép hoặc đồng bộ trạng thái.
6. **Dựa vào class name/identity của lambda để tra cứu.** Dùng ID nghiệp vụ, enum hoặc registry rõ ràng.
7. **Quên quy tắc tính tiền.** Việc chuyển sang lambda không làm biến mất yêu cầu về `BigDecimal`, rounding, scale, precision và xử lý input không hợp lệ.
8. **Kiểm thử chỉ với một case “happy path”.** Hãy thử dữ liệu biên, lỗi, side effect và những hành vi contract cần giữ.
9. **Lạm dụng generic interface có sẵn.** Nếu domain cần hợp đồng ý nghĩa rõ và Javadoc, một functional interface riêng thường dễ bảo trì hơn.
10. **Cho rằng “lambda = async”.** Lambda chỉ biểu diễn hành vi; truyền vào API không làm nó tự chạy song song hay bất đồng bộ. Thời điểm và môi trường chạy do API nhận callback quyết định.

## 12. Bài tập kiểm tra nhanh

Giả sử có hợp đồng:

```java
@FunctionalInterface
interface FeePolicy {
    long charge(long amount);
}
```

Và lớp:

```java
final class FlatFee implements FeePolicy {
    @Override
    public long charge(long amount) {
        return amount + 5L;
    }
}
```

Hãy thực hiện:

1. Thay việc tạo `new FlatFee()` ở một call site bằng lambda cùng hành vi.
2. Nếu đã có phương thức `static long addFee(long amount)`, hãy viết method reference tương ứng.
3. Giải thích vì sao `FeePolicy` vẫn có thể có `default String name()` mà không ảnh hưởng việc dùng lambda.
4. Xác định khi nào nên giữ lớp `FlatFee` thay vì xóa nó.

Đáp án tham khảo: `FeePolicy policy = amount -> amount + 5L;`; method reference là `FeePolicy policy = MyClass::addFee;` nếu `addFee` là phương thức static phù hợp của lớp `MyClass`. Một default method có thân không phải abstract SAM thứ hai. Nên giữ lớp nếu nó là public API được sử dụng, có annotation/metadata, quản lý trạng thái hoặc cung cấp một tên miền nghiệp vụ rõ ràng được dùng rộng rãi.

## 13. Nguyên tắc kết luận cho thiết kế API nhận hành vi

Chỉ chuyển từ Strategy class sang lambda khi thỏa cả ba điều kiện:

1. **Interface hợp lệ:** có một abstract method thực sự cần triển khai, chữ ký/exception/ý nghĩa của contract rõ ràng.
2. **Chiến lược đủ đơn giản:** implementation chủ yếu là một hành vi nhỏ; không cần giữ class để sở hữu nhiều trách nhiệm, lifecycle, metadata hoặc identity.
3. **Hành vi được bảo toàn:** output, lỗi, side effect, tính an toàn đồng thời và phụ thuộc bên ngoài vẫn đúng hợp đồng.

Giữ interface của API để phần sử dụng không cần biết class hay lambda nào đang thực thi. Khi muốn thể hiện nhiều chiến lược, truyền chúng như những giá trị hàm có target type rõ ràng; khi cần quản lý hoặc nhận diện, sử dụng tên/ID nghiệp vụ độc lập với implementation. Như vậy Strategy và lập trình hàm hỗ trợ lẫn nhau: **Strategy định nghĩa điểm có thể thay đổi hành vi, lambda cung cấp một cách triển khai ngắn gọn khi hợp đồng phù hợp**.

**Tài liệu tham khảo:** Java Language Specification §9.8 (Functional Interfaces) và §15.27 (Lambda Expressions); Java SE API `java.util.function`, `java.util.Comparator`, `java.math.BigDecimal`.