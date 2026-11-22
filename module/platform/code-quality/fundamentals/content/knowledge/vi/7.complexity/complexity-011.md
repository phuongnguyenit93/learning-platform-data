# Nhận diện khi trừu tượng hóa đang làm bài toán khó hiểu hơn

Trong lập trình, trừu tượng hóa giúp ta làm việc với những khái niệm quan trọng mà không phải nhìn toàn bộ chi tiết triển khai cùng lúc. Nhưng đôi khi một yêu cầu rất đơn giản lại phải đi qua `interface`, factory, registry, adapter và nhiều lớp trung gian mới tìm được quy tắc thực sự. Khi đó, cơ chế được tạo ra để giảm độ phức tạp có thể trở thành chính nguồn gây khó hiểu.

Bài học thuộc chương **Độ phức tạp** của module `CODE_QUALITY_FUNDAMENTALS`. Mục tiêu của module là hiểu những thuộc tính giúp mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Một trừu tượng tốt có thể hỗ trợ cả ba mục tiêu; trừu tượng không phù hợp lại khiến người đọc mất nhiều công lần theo mã, dễ sửa nhầm và khó đánh giá tác động khi yêu cầu thay đổi.

Sau bài học, bạn có thể:

- Phân biệt việc **che giấu chi tiết không quan trọng** với việc **che mất quy tắc nghiệp vụ quan trọng**.
- Nhận biết các dấu hiệu cho thấy độ gián tiếp, tính tổng quát hoặc số tầng đang làm bài toán khó hiểu hơn.
- Đánh giá một trừu tượng theo đường đi của thay đổi thực tế, thay vì chỉ đếm số lớp hoặc phương thức.
- Biết khi nào nên giữ một giải pháp trực tiếp, dùng hàm có tên rõ, tạo kiểu miền, hoặc duy trì một interface có lý do.
- Refactor cấu trúc thừa trong khi bảo vệ hành vi bằng kiểm thử.

## 1. Trừu tượng hóa giải quyết vấn đề gì?

**Trừu tượng hóa** là biểu diễn một ý tưởng bằng hợp đồng hoặc khái niệm phù hợp, để người sử dụng không phải xử lý mọi chi tiết bên trong. Ví dụ:

```java
long totalVnd = invoice.calculateTotalVnd();
```

Người đọc có thể hiểu ý định “tính tổng hóa đơn” ngay cả khi chưa xem cách cộng các dòng hàng, thuế hay giảm giá. Nếu phương thức có hợp đồng rõ, tên phù hợp và hành vi nhất quán, việc giấu thuật toán là hữu ích.

Ngược lại, đoạn:

```java
boolean result = executor.execute("rule-17", context);
```

chỉ cho biết chương trình gọi một cơ chế thực thi. Người đọc không biết `rule-17` là gì, `context` chứa gì, kết quả `true` có ý nghĩa nào hoặc quy tắc nằm ở đâu. Trừ khi bài toán thật sự cần định danh và thực thi quy tắc động, cách biểu đạt này **đẩy ý nghĩa nghiệp vụ ra khỏi chỗ sử dụng**.

Điều quan trọng là phân biệt hai loại phức tạp:

- **Phức tạp vốn có (*essential complexity*):** bắt nguồn từ vấn đề thực tế, chẳng hạn quy tắc giá có nhiều mức, giao dịch phải đảm bảo tính nhất quán, hay hệ thống kết nối nhiều nhà cung cấp khác nhau.
- **Phức tạp do giải pháp tạo thêm (*accidental complexity*):** đến từ cơ chế, cấu hình, phụ thuộc hoặc quy ước mà chính thiết kế đưa vào, chẳng hạn dùng công cụ quy tắc tổng quát cho đúng một phép so sánh cố định.

Không thể loại bỏ hết sự phức tạp vốn có bằng cách viết ít dòng hơn. Nhưng có thể hạn chế phần phức tạp do cách tổ chức mã thêm vào mà không đem lại lợi ích tương xứng.

### “Ít dòng mã” chưa chắc là “đơn giản”

So sánh:

```java
return map.get(key).apply(context);
```

và:

```java
return order.isVip() || order.subtotalVnd() >= FREE_SHIPPING_THRESHOLD_VND;
```

Dòng đầu ngắn hơn nhưng có thể buộc người đọc tìm cách khởi tạo `map`, nguồn của `key`, kiểu của `context`, hàm được đăng ký và quy tắc xử lý thiếu key. Dòng sau dài hơn nhưng trình bày trực tiếp nghiệp vụ: khách VIP hoặc đơn đạt ngưỡng được miễn phí giao hàng.

Chi phí đọc mã không thể suy ra từ số ký tự. Cần xét **số khái niệm phải hiểu, số bước phải lần theo và những giả định không được nói rõ**.

## 2. Ví dụ: một quy tắc nhỏ bị bao quanh bởi cơ chế lớn

Giả sử hệ thống bán hàng mới có một quy tắc: khách VIP hoặc đơn từ 500.000 VND được miễn phí giao hàng. Quy tắc chỉ được đánh giá tại một nơi và chưa có nhu cầu chỉnh động lúc chạy.

Một nhóm chọn giải pháp tổng quát để “sẵn sàng cho mọi loại quy tắc”:

```java
import java.util.List;
import java.util.Map;

record Order(long subtotalVnd, boolean vip) {}

interface Rule<T> {
    boolean matches(T input);
}

final class RuleEngine<T> {
    private final Map<String, List<Rule<T>>> rulesByName;

    RuleEngine(Map<String, List<Rule<T>>> rulesByName) {
        this.rulesByName = Map.copyOf(rulesByName);
    }

    boolean matchesAny(String ruleName, T input) {
        List<Rule<T>> rules = rulesByName.get(ruleName);
        if (rules == null) {
            throw new IllegalArgumentException("Unknown rule: " + ruleName);
        }
        return rules.stream().anyMatch(rule -> rule.matches(input));
    }
}
```

Để sử dụng, ứng dụng phải đăng ký các quy tắc:

```java
RuleEngine<Order> engine = new RuleEngine<>(Map.of(
        "free-shipping",
        List.of(
                (Rule<Order>) order -> order.vip(),
                (Rule<Order>) order -> order.subtotalVnd() >= 500_000L
        )
));

boolean eligible = engine.matchesAny("free-shipping", order);
```

Thiết kế này *có thể* hợp lý khi ứng dụng cần đăng ký nhiều bộ quy tắc độc lập, chọn tên bộ quy tắc theo cấu hình và phối hợp các điều kiện ở nhiều nơi. Nhưng trong bối cảnh chỉ có một quy tắc cố định, nó thêm các khái niệm mà người đọc phải hiểu:

1. `Rule<T>` là hợp đồng gì?
2. `RuleEngine<T>` kết hợp các quy tắc bằng `anyMatch` hay `allMatch`?
3. Chuỗi `"free-shipping"` được khai báo và đối chiếu ở đâu?
4. Các lambda được đăng ký tại điểm khởi tạo nào?
5. Nếu tên rule bị gõ sai, lỗi xảy ra lúc biên dịch hay khi chạy?
6. Có trường hợp nào cần thay danh sách quy tắc trong lúc ứng dụng đang hoạt động không?

Dù bản thân các lớp không quá dài, đường đi để hiểu một điều kiện nghiệp vụ đã trở nên quanh co.

### Giải pháp trực tiếp theo đúng nhu cầu

Nếu chưa cần cơ chế đăng ký, một lớp có tên nghiệp vụ có thể diễn đạt đầy đủ:

```java
final class FreeShippingPolicy {
    private static final long MINIMUM_SUBTOTAL_VND = 500_000L;

    boolean isEligible(Order order) {
        if (order == null || order.subtotalVnd() < 0) {
            throw new IllegalArgumentException("Invalid order");
        }

        return order.vip()
                || order.subtotalVnd() >= MINIMUM_SUBTOTAL_VND;
    }
}
```

Điểm sử dụng:

```java
boolean eligible = freeShippingPolicy.isEligible(order);
```

Ở đây, **trừu tượng vẫn tồn tại**: `FreeShippingPolicy` che giấu chi tiết kiểm tra điều kiện và đặt tên cho một khái niệm nghiệp vụ. Nhưng nó không bắt người đọc hiểu registry, tên chuỗi hay cách kết hợp danh sách quy tắc.

Hai cách triển khai không thể đánh giá chỉ bằng một tiêu chí “có dùng interface hay không”. Cần đối chiếu với **những thay đổi hệ thống thật sự cần tiếp nhận**.

## 3. Dấu hiệu trừu tượng đang tăng chi phí hiểu mã

### 3.1. Muốn hiểu một quyết định nhỏ phải nhảy qua quá nhiều nơi

Ví dụ luồng gọi:

```text
OrderController
    -> CheckoutFacade
        -> EligibilityService
            -> RuleDispatcher
                -> RuleRegistry
                    -> FreeShippingHandler
                        -> điều kiện VIP hoặc đạt ngưỡng
```

Một tầng trung gian có thể có ý nghĩa nếu nó xử lý điều phối, chuyển đổi mô hình hoặc bảo vệ ranh giới. Nhưng nếu hầu hết phương thức chỉ nhận tham số rồi chuyển nguyên xi sang tầng kế tiếp, chúng tạo thêm đường đi mà không thêm khái niệm hữu ích.

**Cách nhận diện:** chọn một yêu cầu như “đổi ngưỡng miễn phí giao hàng” và thử lần từ API tới nơi thực hiện quyết định. Nếu người đọc phải xem nhiều file chỉ để tìm một so sánh, hãy kiểm tra vai trò thật sự của các tầng.

Không có ngưỡng cứng như “hơn ba lớp là sai”. Một hệ thống có HTTP layer, domain layer và persistence layer vì yêu cầu phân tách trách nhiệm vẫn có thể rất dễ hiểu. Vấn đề là **mỗi tầng có trách nhiệm riêng có thể giải thích được hay không**.

### 3.2. Tên tổng quát che khuất ý định nghiệp vụ

Các tên như `GenericProcessor`, `BaseManager`, `AbstractHandler`, `RuleExecutor`, `PayloadContext` hoặc `execute(Object input)` không nhất thiết sai. Nhưng nếu đây là tất cả những gì lộ ra ở API, người đọc phải tự suy đoán ý nghĩa từ mã thực thi.

So sánh:

```java
Object execute(String action, Map<String, Object> context);
```

với:

```java
ShippingQuote calculateShippingQuote(Order order);
```

Chữ ký thứ hai truyền tải nhiệm vụ, đầu vào và đầu ra. Chữ ký thứ nhất đòi hỏi kiến thức ngoài kiểu dữ liệu: khóa `action` hợp lệ, các trường bắt buộc trong `context`, kiểu của kết quả và cách báo lỗi.

Một abstraction nên **rút gọn số khái niệm người gọi phải biết**. Nếu phải có tài liệu dài mới giải thích được cách gọi đúng một phép tính đơn giản, hợp đồng có thể quá tổng quát.

### 3.3. Mọi thay đổi vẫn phải sửa cả lớp trừu tượng lẫn các triển khai

Tạo interface với mục tiêu cô lập các biến thể, nhưng mỗi lần thêm quy tắc lại phải:

- Thêm phương thức vào interface chung.
- Sửa toàn bộ lớp triển khai, kể cả lớp không dùng phương thức đó.
- Cập nhật factory và cấu hình.
- Chỉnh các điểm gọi để truyền thêm cờ hoặc dữ liệu tổng quát.

Đây là dấu hiệu hợp đồng chưa xác định đúng **điểm biến thiên**. Một interface tên đẹp không tự làm các thành phần độc lập.

Ví dụ, nếu một `PaymentProvider` vừa tính phí, vừa gửi email, vừa quản lý kho, các nhà cung cấp chỉ làm thanh toán vẫn bị buộc biết tới chức năng không liên quan. Có thể tách hợp đồng theo trách nhiệm hoặc bỏ đi phần trừu tượng không cần thiết.

### 3.4. Cấu hình trở thành ngôn ngữ lập trình thứ hai

Một cơ chế cấu hình ban đầu chỉ để chọn chiến lược; sau đó chứa điều kiện, ưu tiên, biểu thức, tên trường, tham số và cơ chế kế thừa:

```yaml
rules:
  - handler: any
    operands:
      - field: customer.flags.vip
        operator: equals
        value: true
      - field: order.subtotal
        operator: greater_or_equal
        value: 500000
```

Khi đó, người bảo trì phải hiểu **hai hệ thống**: Java thực thi công cụ quy tắc và ngôn ngữ cấu hình chứa quy tắc nghiệp vụ. Những lỗi như gõ sai `customer.flags.vip` có thể chỉ lộ ra khi chạy.

Cấu hình động là yêu cầu hợp lệ khi đội vận hành cần chỉnh quy tắc mà không phát hành mã, cần audit phiên bản hoặc cần cho nhiều đối tác khai báo chính sách. Nhưng nếu đội lập trình vẫn phải deploy mỗi lần sửa file cấu hình, cơ chế này có thể chỉ di chuyển độ phức tạp từ mã Java sang YAML.

### 3.5. Quá nhiều chuyển đổi dữ liệu không mang thêm ý nghĩa

Một luồng kiểu:

```text
OrderRequest
  -> GenericPayload
  -> ProcessContext
  -> RuleInput
  -> DomainCommand
  -> ResultEnvelope
  -> OrderResponse
```

có thể làm người đọc mất dấu dữ liệu nào quan trọng, trường nào có thể rỗng và điều kiện nào đã được kiểm tra.

Việc chuyển từ HTTP DTO sang mô hình nghiệp vụ hoặc từ database entity sang dữ liệu trả về thường có lý do rõ ràng. Nhưng nhiều phép chuyển đổi chỉ sao chép cùng trường mà không thêm validation, trách nhiệm hay ranh giới phụ thuộc có thể gây thêm lỗi ánh xạ và chi phí duy trì.

### 3.6. Đa hình được dùng để né một điều kiện đơn giản

Nếu hai trường hợp ngắn, ổn định và cùng thay đổi một lúc, `switch` có thể là lựa chọn rõ ràng. Tạo hierarchy gồm `BaseAction`, `ActionFactory` và hàng loạt `ActionImpl` chỉ để tránh một `switch` đôi khi làm tăng số nơi phải xem.

Ngược lại, khi mỗi biến thể có thuật toán lớn, phụ thuộc riêng hoặc lịch phát hành độc lập, đa hình hoặc Strategy có thể làm mã dễ thay đổi hơn. **Số lượng nhánh không đủ để quyết định**; quan trọng là mức độ độc lập và tốc độ thay đổi của chúng.

### 3.7. Kiểm thử chủ yếu xác nhận các lớp trung gian gọi nhau

Nếu unit test cho `Facade` chỉ kiểm tra nó gọi `Service`, test cho `Service` chỉ kiểm tra nó gọi `Registry` và test cho `Registry` chỉ kiểm tra nó gọi `Handler`, hệ thống có thể có rất nhiều test nhưng ít test xác nhận quy tắc nghiệp vụ.

Đây là tín hiệu cần kiểm tra: liệu thiết kế đang khiến ta phải bảo vệ những đường nối trung gian, trong khi hành vi “VIP được miễn phí giao hàng” lại khó kiểm thử tại một điểm rõ ràng?

Mock vẫn hữu ích ở ranh giới với dịch vụ ngoài. Vấn đề không nằm ở công cụ mock mà ở việc **test bám vào cấu trúc nội bộ nhiều hơn hợp đồng hành vi**.

## 4. Đánh giá bằng câu hỏi cụ thể thay vì cảm giác

Khi nghi ngờ một abstraction đang cản trở, hãy thử phân tích một đường đi của yêu cầu thay đổi. Không cần ngay lập tức xóa lớp.

| Câu hỏi kiểm tra | Dấu hiệu abstraction hữu ích | Dấu hiệu cần xem lại |
| --- | --- | --- |
| Nó đặt tên cho điều gì? | Một khái niệm miền hoặc một ranh giới kỹ thuật xác định | Một từ tổng quát như “processor” nhưng không rõ xử lý gì |
| Người gọi cần biết bao nhiêu? | Chỉ biết hợp đồng và dữ liệu cần thiết | Phải biết key, thứ tự đăng ký, kiểu cast, cấu hình ẩn |
| Nó che chi tiết nào? | Thuật toán hoặc thay đổi không cần cho mục tiêu của người gọi | Che luôn điều kiện nghiệp vụ quan trọng |
| Khi thêm yêu cầu, sửa ở đâu? | Thay đúng một triển khai hoặc một điểm rõ nghĩa | Phải đồng thời sửa base type, registry và nhiều wrapper |
| Lỗi có được phát hiện sớm không? | Kiểu dữ liệu và bất biến giúp phát hiện khi biên dịch/khởi tạo | Sai key, sai kiểu và thiếu handler chỉ lộ lúc chạy |
| Có biến thể thực tế nào? | Có nhiều triển khai với trách nhiệm độc lập hoặc yêu cầu tích hợp đã rõ | Chỉ có một trường hợp và mọi khả năng khác đều là giả định |
| Nếu bỏ abstraction, chuyện gì xảy ra? | Mất khả năng cô lập, test, thay thế hoặc bảo vệ phụ thuộc quan trọng | Luồng đơn giản hơn và không mất hợp đồng thực sự cần thiết |

Đây là bảng **gợi ý điều tra**, không phải bộ tiêu chí chấm điểm tự động. Một interface chỉ có một triển khai vẫn có thể rất hữu ích ở ranh giới với cơ sở dữ liệu, cổng thanh toán hoặc API bên ngoài. Một phương thức ngắn cũng có thể cần trừu tượng hóa nếu nó diễn đạt khái niệm dùng rộng rãi.

### Thử “mô phỏng một thay đổi” (*change simulation*)

Giả sử sản phẩm yêu cầu: “Khách VIP chỉ được miễn phí khi đơn có ít nhất một mặt hàng đủ điều kiện.”

Hãy đánh giá các cách triển khai bằng cách hỏi:

1. Có xác định được nơi đặt quy tắc mới trong vài phút đọc không?
2. Có cần sửa lớp không liên quan chỉ vì giao diện quá tổng quát không?
3. Có cần thay cấu hình, key chuỗi hoặc tên handler cùng lúc không?
4. Có test nào đang mô tả hành vi miễn phí giao hàng để bổ sung ca mới không?
5. Thay đổi có tác động tới quy tắc khác mà khó quan sát không?

Nếu thiết kế tổng quát luôn buộc thay đổi nhiều cơ chế hơn phần nghiệp vụ, mức trừu tượng đó có thể chưa phù hợp.

Không nên kết luận chỉ từ số lượng file thay đổi. Một thay đổi trải qua DTO, domain và persistence là hợp lý nếu mỗi tầng xử lý một mối quan tâm khác nhau. Điều đáng quan sát là **có bao nhiêu chỉnh sửa cơ học hoặc mang tính thủ tục đăng ký mà không bổ sung ý nghĩa**.

## 5. Phức tạp do trừu tượng hóa khác với phức tạp thật của nghiệp vụ

Không phải mọi luồng dài đều có thể rút gọn mà vẫn đúng.

Ví dụ tính thuế ở nhiều quốc gia có thể phải xử lý địa chỉ tính thuế, ngày hiệu lực, loại sản phẩm, hoàn tiền, miễn trừ và kết quả kiểm toán. Nếu thay toàn bộ bằng một phương thức `calculateTax(int percent)`, mã tuy ngắn nhưng đã loại bỏ các khái niệm cần thiết.

Ngược lại, một tính năng hiển thị nhãn “Còn hàng” từ `stock > 0` không nhất thiết cần engine quy tắc động. Hãy giữ lại sự phức tạp gắn với **quy định nghiệp vụ, độ tin cậy và phụ thuộc thực**, đồng thời giảm những lớp trung gian không đóng góp rõ ràng.

Sơ đồ gợi ý:

```text
Bài toán có quy tắc thật
          |
          v
Những trách nhiệm cần diễn đạt
          |
     +----+--------------------+
     |                         |
Giấu chi tiết triển khai     Làm lộ hợp đồng
không quan trọng             và ràng buộc quan trọng
     |                         |
     +------------+------------+
                  |
                  v
Mã dễ tìm nơi sửa và dễ kiểm thử
```

Mục tiêu không phải “ít abstraction nhất” mà là **mức abstraction vừa đủ để giải thích được bài toán mà không dựng thêm một bài toán thứ hai về cơ chế**.

## 6. Phân biệt các mức trừu tượng thường gặp

### 6.1. Tên phương thức rõ nghĩa

```java
boolean eligible = order.vip()
        || order.subtotalVnd() >= 500_000L;
```

có thể được đưa thành:

```java
boolean eligible = freeShippingPolicy.isEligible(order);
```

Việc trích phương thức đặt tên cho quy tắc và cho phép kiểm thử tập trung mà không yêu cầu registry. Đây là abstraction nhỏ, thường có lợi khi quy tắc không hoàn toàn hiển nhiên hoặc được sử dụng ở nhiều nơi.

### 6.2. Kiểu dữ liệu diễn đạt bất biến

Một `record MoneyVnd(long amount)` hoặc `enum OrderStatus` có thể làm rõ đơn vị và tập trạng thái hợp lệ. Những kiểu này thêm một khái niệm nhưng giảm việc phải nhớ quy ước ngầm ở nhiều chỗ.

```java
record DiscountPercent(int value) {
    DiscountPercent {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException("Percent must be 0..100");
        }
    }
}
```

Ví dụ chỉ phù hợp nếu nghiệp vụ thật sự giới hạn mức chiết khấu trong khoảng 0–100%. Một mô hình tốt cần phản ánh ràng buộc thật, không tự thêm ràng buộc vô căn cứ.

### 6.3. Interface ở ranh giới biến thiên hoặc phụ thuộc

Giả sử ứng dụng cần đổi nhà cung cấp thanh toán hoặc giả lập phản hồi dịch vụ ngoài khi kiểm thử:

```java
interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}
```

Đây có thể là abstraction hữu ích ngay cả khi hiện tại chỉ có một gateway, bởi nó xác định **ranh giới hệ thống bên ngoài** và kiểm soát việc phụ thuộc vào giao thức hoặc thư viện cụ thể.

Điều kiện là `PaymentRequest` và `PaymentResult` phải có nghĩa và hợp đồng nêu rõ chuyện timeout, kết quả không chắc chắn, xử lý trùng yêu cầu. Nếu interface chỉ là `Object call(String operation, Map<String, Object> args)`, mức tổng quát có thể xóa đi những bảo đảm quan trọng mà tầng nghiệp vụ cần.

### 6.4. Framework hoặc engine tổng quát

Một engine có thể đáng giá khi nhiều loại tác vụ thật sự dùng chung cơ chế chọn, thực thi, quan sát và mở rộng; hoặc khi người dùng không phải lập trình viên cần cấu hình hành vi. Nhưng engine là một **sản phẩm nhỏ bên trong hệ thống**, kéo theo API, phiên bản, lỗi cấu hình, tài liệu và test riêng.

Nếu chỉ có một hai phép tính bất biến, engine có thể tạo chi phí lớn hơn giá trị đem lại. Hãy yêu cầu một kịch bản thay đổi thực tế trước khi xây cơ chế có khả năng cấu hình mọi thứ.

## 7. Trừu tượng “rò rỉ”: khi người gọi vẫn phải hiểu chi tiết bị che

Một abstraction *rò rỉ* (*leaky abstraction*) không thể che trọn những chi tiết mà nó hứa che. Ví dụ một lớp `OrderRepository` cung cấp phương thức `save(order)`, nhưng người gọi vẫn phải biết:

- Gọi `flush()` theo thứ tự bí mật.
- Bật transaction ở nơi ngoài hợp đồng.
- Tự nhận diện và thử lại một loại lỗi do cơ sở dữ liệu cụ thể trả về.
- Không được sử dụng `save` trong một số trạng thái dù chữ ký không thể hiện điều đó.

Không phải mọi chi tiết này đều có thể che hoàn toàn; transaction và nhất quán là những ràng buộc thật. Nhưng nếu người gọi buộc phải biết nhiều quy ước ngầm, interface hiện tại có thể đã hứa hẹn mức đơn giản sai.

**Cách cải thiện:** xác định rõ trách nhiệm của ranh giới, làm lộ điều kiện bắt buộc qua chữ ký, kiểu dữ liệu, kết quả hoặc hợp đồng tài liệu hóa. Trong một số trường hợp, nên bỏ lớp wrapper mỏng để người gọi làm việc trực tiếp với API thư viện đã rõ nghĩa. Trong trường hợp khác, nên nâng trách nhiệm giao dịch lên một dịch vụ nghiệp vụ đủ khả năng bảo vệ bất biến.

Đừng dùng abstraction để “giấu” một rủi ro mà người dùng API vẫn bắt buộc phải quyết định.

## 8. Ranh giới giữa tái sử dụng thật và tổng quát hóa sớm

Hai đoạn mã trông giống nhau không nhất thiết có cùng lý do thay đổi.

Ví dụ hai chức năng đều có ba bước “kiểm tra → tính toán → lưu kết quả”:

```text
Duyệt đơn hàng:  kiểm tra tồn kho -> tính giá -> lưu đơn
Duyệt hoàn tiền: kiểm tra quyền -> tính khoản hoàn -> ghi yêu cầu
```

Có thể bị cám dỗ tạo `AbstractApprovalWorkflow<T>` với nhiều hook như `beforeCheck`, `resolveCalculator`, `afterSave` và `onFailure`. Nhưng mỗi quy trình có bất biến, cách xử lý lỗi và lịch phát triển riêng; ép vào một template có thể làm mỗi thay đổi kéo theo điều kiện đặc biệt ở lớp nền.

Nguyên tắc hữu ích:

- **Lặp cùng kiến thức nghiệp vụ** ở nhiều nơi làm tăng nguy cơ các bản sao lệch nhau; thường cần một nguồn sự thật chung.
- **Lặp cấu trúc bề ngoài** chưa đủ để kết luận phải chung một abstraction; hai phần mã có thể thay đổi vì lý do khác nhau.
- Nếu abstraction chung ngày càng nhiều cờ như `skipValidation`, `useLegacyMode`, `ignoreFailure` hoặc phương thức hook rỗng, cần đánh giá liệu các biến thể có thực sự cùng một khái niệm không.

Một cách đánh giá là hỏi: “Nếu sửa quy tắc của trường hợp A, có lý do nghiệp vụ nào buộc B cũng thay đổi không?” Nếu câu trả lời thường là không, gộp cả hai vào một lớp nền có thể làm tăng liên kết thay vì tái sử dụng có ích.

## 9. Khi nào nên giữ abstraction dù mã trông phức tạp hơn?

Không nên “làm phẳng” mọi thiết kế chỉ để giảm số file. Có những ranh giới bảo vệ hệ thống:

| Bối cảnh | Vì sao trừu tượng có thể đáng giữ? | Bằng chứng cần có |
| --- | --- | --- |
| Kết nối dịch vụ thanh toán, vận chuyển hoặc lưu trữ | Cách ly giao thức, lỗi mạng và thư viện bên ngoài khỏi nghiệp vụ | Có ranh giới phụ thuộc thật và hợp đồng cụ thể |
| Nhiều thuật toán tính giá thay đổi độc lập | Có thể kiểm thử và sửa từng biến thể mà ít ảnh hưởng phần chung | Biến thể và tần suất thay đổi đã quan sát được |
| Cần bảo vệ bất biến miền | Kiểu/đối tượng chuyên biệt tránh trạng thái không hợp lệ | Ràng buộc cụ thể, được kiểm chứng |
| Nhiều nhóm bổ sung plugin | Cần hợp đồng mở rộng, quản lý phiên bản và đăng ký | Sản phẩm thật sự cho bên ngoài mở rộng |
| Phụ thuộc cần thay bằng test double | Tách tương tác với hệ thống chậm, không xác định | Kiểm thử hành vi qua ranh giới thay thế được |

**Chi phí kỹ thuật có thể hợp lý nếu nó làm rõ rủi ro hoặc cô lập thay đổi thực sự.** Một interface cho cổng thanh toán không có cùng vai trò với một interface chỉ chuyển tiếp một phép so sánh số học.

Một dấu hiệu tích cực là người mới có thể trả lời: “Lớp này tồn tại để bảo vệ điều gì?” bằng một câu cụ thể, liên quan đến nghiệp vụ hoặc ranh giới kỹ thuật.

## 10. Refactor khi nhận ra abstraction thừa

Đơn giản hóa một thiết kế có sẵn nên là một thay đổi có kiểm soát. Xóa các lớp ngay lập tức có thể làm mất validation, transaction hoặc hành vi lỗi đang nằm rải rác.

### Bước 1: Chọn một đường đi cụ thể

Ví dụ “kiểm tra có được miễn phí giao hàng hay không”. Lần theo điểm gọi, ghi lại những phương thức thực sự thêm trách nhiệm và những phương thức chỉ chuyển tiếp.

Tập trung vào một trường hợp đủ nhỏ để chứng minh kết quả. Tránh bắt đầu bằng việc xóa toàn bộ framework dùng ở nhiều tính năng.

### Bước 2: Viết hoặc củng cố test theo hành vi

Với `FreeShippingPolicy`, những tình huống có ý nghĩa gồm:

| Khách VIP? | Giá trị đơn (VND) | Kết quả mong đợi |
| --- | ---: | --- |
| Không | 499.999 | Không miễn phí |
| Không | 500.000 | Miễn phí |
| Có | 100.000 | Miễn phí |
| Có | 500.000 | Miễn phí |

Đồng thời cần kiểm tra đầu vào không hợp lệ nếu hợp đồng xác định rõ điều đó.

Ví dụ JUnit 5 cho phiên bản trực tiếp:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class FreeShippingPolicyTest {
    private final FreeShippingPolicy policy = new FreeShippingPolicy();

    @Test
    void thresholdAndVipRulesAreApplied() {
        assertFalse(policy.isEligible(new Order(499_999, false)));
        assertTrue(policy.isEligible(new Order(500_000, false)));
        assertTrue(policy.isEligible(new Order(100_000, true)));
    }

    @Test
    void invalidSubtotalIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.isEligible(new Order(-1, false)));
    }
}
```

Các test mô tả điều người dùng cần, thay vì cấu trúc kiểu “registry gọi handler đúng một lần”. Chúng giúp refactor mà vẫn bảo vệ kết quả.

### Bước 3: Xác định hợp đồng còn cần thiết

Kiểm tra abstraction hiện tại có đang được dùng bởi tính năng khác, có bảo đảm thứ tự xử lý, ghi log, quyền truy cập, transaction hoặc cấu hình theo môi trường không. Nếu có, phải quyết định giữ các trách nhiệm này ở đâu trước khi bỏ lớp.

Chỉ loại bỏ cơ chế khi có thể chứng minh phần còn lại vẫn đáp ứng yêu cầu thực tế.

### Bước 4: Chuyển từng điểm gọi sang biểu đạt rõ hơn

Ví dụ thay:

```java
boolean eligible = engine.matchesAny("free-shipping", order);
```

thành:

```java
boolean eligible = freeShippingPolicy.isEligible(order);
```

Tại thời điểm này, có thể giữ adapter tạm thời nếu cần chuyển đổi từng phần, nhưng sau khi đã chuyển hết điểm gọi thì xóa registry/rule không còn dùng. Giữ hai nguồn quy tắc song song dễ khiến hành vi lệch nhau.

### Bước 5: Kiểm tra tác động và loại bỏ đường cũ

Chạy test nghiệp vụ, test tích hợp ở những ranh giới có thay đổi và kiểm tra việc cấu hình khởi tạo. Đặc biệt rà soát những trường hợp mà cơ chế cũ từng có hành vi ngầm như “key không có”, “danh sách rule rỗng” hoặc “thứ tự đánh giá rule”.

Việc giảm abstraction chỉ thành công nếu người đọc thấy dễ lần theo mã hơn **và** chương trình vẫn giữ đúng hành vi đã cam kết. Một thay đổi nghiệp vụ có chủ đích nên được phân biệt rõ với refactor cấu trúc.

## 11. Những ngộ nhận cần tránh

**“Mỗi lớp phải có interface.”** Interface hữu ích khi có hợp đồng thay thế, ranh giới phụ thuộc hoặc biến thể rõ ràng. Một lớp miền cụ thể có tên tốt thường đã đủ để diễn đạt ý định.

**“Dùng design pattern thì mã sẽ sạch.”** Pattern mô tả giải pháp cho một kiểu vấn đề. Nếu vấn đề không tồn tại, áp dụng pattern chỉ thêm cơ chế.

**“Không được có `if` hoặc `switch`.”** Điều kiện là cách biểu diễn tự nhiên của nhiều quy tắc. Vấn đề nằm ở điều kiện rải rác, khó thay đổi, thiếu tên hoặc trộn trách nhiệm không liên quan.

**“Số dòng càng ít càng dễ đọc.”** Một biểu thức hoặc API tổng quát ngắn có thể tạo nhiều truy xuất gián tiếp hơn một phương thức nghiệp vụ rõ ràng.

**“Có nhiều file là bị trừu tượng hóa quá mức.”** Phân tách các trách nhiệm độc lập có thể làm mã dễ hiểu dù tạo nhiều file. Cần đánh giá luồng làm việc và quan hệ giữa các thành phần.

**“Một interface có một triển khai luôn vô dụng.”** Nó vẫn có thể biểu diễn ranh giới với I/O hoặc hỗ trợ test. Hãy xét trách nhiệm thật và mức phụ thuộc trước khi xóa.

**“Gộp mọi thứ vào một lớp sẽ đơn giản hơn.”** Dồn logic thanh toán, giao hàng, tồn kho và email vào một nơi chỉ che số lượng lớp, không giảm phức tạp nghiệp vụ; còn làm tăng ảnh hưởng khi sửa.

**“Abstraction càng tổng quát thì càng tái sử dụng tốt.”** API nhận `Object`, `Map<String, Object>` và key chuỗi có thể dùng cho mọi thứ nhưng khó phát hiện lỗi và thiếu hợp đồng cụ thể. Mức tổng quát cần phục vụ một nhu cầu được xác định.

## 12. Bài tập tình huống

### Tình huống A: bộ xuất báo cáo có một định dạng

Hệ thống nội bộ chỉ xuất CSV, nhưng đã có `ReportPluginManager`, `ProviderFactory`, `ExportContext` và ba lớp chuyển tiếp. Để thêm một cột, lập trình viên phải sửa bốn nơi.

Hãy xác định trách nhiệm nào thật sự cần thiết. Một `CsvReportExporter` có hàm `export(report)` có thể đủ không? Nếu kế hoạch sản phẩm sắp có PDF và Excel với nhóm triển khai độc lập, hợp đồng nào nên tách ngay?

### Tình huống B: hệ thống thanh toán nhiều cổng

Có ba cổng thanh toán khác API, timeout và kết quả đối soát; lớp `PaymentGateway` cùng các adapter giữ logic tích hợp riêng. Mã có nhiều interface và class nhưng mỗi cổng có kiểm thử độc lập.

Hãy giải thích vì sao đây có thể là trừu tượng đáng giá, dù đọc mã phải qua một tầng trung gian. Những điều nào cần bảo đảm ở hợp đồng thanh toán để tránh biến nó thành `execute(Object)`?

### Tình huống C: quy trình giảm giá chung

Một `AbstractDiscountProcessor` có 12 hook, trong đó 9 hook rỗng ở hầu hết các triển khai. Mỗi khi thêm giảm giá theo nhóm khách, nhóm phải thêm cờ `skipBaseValidation` và sửa lớp nền.

Hãy tìm dấu hiệu các biến thể đang bị ép dùng chung quá nhiều. Bạn sẽ chuyển sang những thành phần nghiệp vụ cụ thể hơn hay giữ phần nào của cơ chế hiện tại? Cần test hành vi nào trước khi refactor?

### Tình huống D: cấu hình quy tắc động

Một trang quản trị cho phép nhân viên kinh doanh thay ngưỡng khuyến mãi theo giờ mà không deploy ứng dụng. Quy tắc được lưu theo phiên bản, có phê duyệt và lịch sử.

Trong trường hợp này, quy tắc động có mục đích rõ ràng. Hãy nêu những trách nhiệm thực tế của engine như validation, kiểm tra quyền, lưu phiên bản, rollback và quan sát lỗi. Phần phức tạp nào là cần thiết để bảo đảm nghiệp vụ, phần nào vẫn có thể giữ đơn giản?

Với mỗi tình huống, thử mô phỏng một thay đổi mới, đánh dấu những lớp phải hiểu và sửa, rồi đề xuất một cách tổ chức khiến **quy tắc quan trọng dễ tìm và đường đi của thay đổi có thể dự đoán được**.

## 13. Ghi nhớ

Trừu tượng hóa hữu ích khi nó **đặt tên cho khái niệm đúng, bảo vệ hợp đồng quan trọng hoặc cô lập một nguyên nhân thay đổi thực tế**. Nó trở thành gánh nặng khi người đọc phải học cách vận hành cơ chế chỉ để hiểu một quy tắc đơn giản.

- Tìm dấu hiệu qua đường đi của một yêu cầu: số nơi phải lần theo, cấu hình phải biết, dữ liệu phải chuyển đổi và những chỉnh sửa cơ học.
- Hỏi mỗi tầng che chi tiết gì, mang trách nhiệm nào và giúp giảm rủi ro thay đổi ra sao.
- Đánh giá theo biến thể thực sự tồn tại và lịch sử thay đổi, không theo khả năng “biết đâu sau này cần”.
- Giữ kiểu dữ liệu, tên hàm và ranh giới phụ thuộc mang ý nghĩa rõ; bỏ những wrapper hoặc registry không tạo giá trị.
- Refactor dần, có test bảo vệ hành vi và rà soát cơ chế cũ trước khi loại bỏ.

Một thiết kế dễ hiểu giúp người bảo trì nhìn thấy **điều hệ thống đang quyết định, lý do quyết định và nơi cần sửa khi yêu cầu đổi**. Trừu tượng hóa tốt làm những điều đó rõ hơn; trừu tượng hóa không phù hợp khiến chúng nằm khuất sau các lớp cơ chế.

