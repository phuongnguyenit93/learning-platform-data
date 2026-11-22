# Phân biệt dịch vụ cộng tác với dữ liệu đầu vào của một lần gọi

Khi thiết kế một lớp trong Java, ta thường thấy cả `CustomerRepository`, `PaymentGateway`, `customerId` và `amount` xuất hiện trong chữ ký phương thức hoặc constructor. Chúng đều liên quan đến công việc của lớp, nhưng **không giữ cùng một vai trò**:

- **Dịch vụ cộng tác (collaborator)** cung cấp một năng lực hoặc hành vi mà đối tượng cần để thực hiện công việc: truy vấn dữ liệu, gửi thông báo, tính giá theo chính sách, lấy thời gian hiện tại...
- **Dữ liệu đầu vào của một lần gọi (per-call input)** mô tả *công việc cụ thể lần này*: mã khách hàng cần tìm, số tiền cần thanh toán, địa chỉ giao hàng, thời điểm người dùng lựa chọn...

Trong Dependency Injection (DI), ta thường **đưa cộng tác viên bắt buộc vào constructor** và **đưa dữ liệu của thao tác vào tham số phương thức**. Cách tách này cho phép một đối tượng dịch vụ dùng lại được cho nhiều yêu cầu, trong khi việc tạo và lắp ghép các cộng tác viên được chuyển về *composition root* theo tinh thần Inversion of Control (IoC).

> Quy tắc trên là điểm bắt đầu để thiết kế, không phải phép phân loại dựa vào kiểu Java: một `String` có thể là cấu hình sống cùng đối tượng, còn một đối tượng triển khai interface có thể được chọn riêng cho từng lần gọi. Phải xét **vai trò và vòng đời thực tế**.

## 1. Hai vai trò trong một lời gọi

Giả sử hệ thống cần báo giá vận chuyển:

```text
                        Lắp ghép khi khởi động
                  ┌─────────────────────────────┐
                  │ Composition root            │
                  │ new StandardRatePolicy()    │
                  │ new ShippingQuoteService(…) │
                  └──────────────┬──────────────┘
                                 │ tiêm cộng tác viên
                                 ▼
                      ┌──────────────────────┐
QuoteRequest A ──────►│ ShippingQuoteService │──────► Quote A
QuoteRequest B ──────►│                      │──────► Quote B
                      └──────────┬───────────┘
                                 │ gọi hành vi
                                 ▼
                          RatePolicy
```

`ShippingQuoteService` cần một `RatePolicy` để tính giá. Đây là quan hệ cộng tác: dịch vụ sử dụng hành vi do chính sách cung cấp, còn quyết định dùng triển khai nào nằm ở nơi lắp ghép. Ngược lại, vùng nhận hàng và khối lượng kiện hàng thay đổi theo từng yêu cầu; đó là dữ liệu của lời gọi `quote(...)`.

| Câu hỏi | Dịch vụ cộng tác | Dữ liệu của lần gọi |
|---|---|---|
| Nó trả lời điều gì? | **Thực hiện bằng cách nào / nhờ năng lực nào?** | **Thực hiện cho trường hợp nào / với giá trị nào?** |
| Ví dụ | `RatePolicy`, `OrderRepository`, `Clock` | `QuoteRequest`, `orderId`, `requestedAt` |
| Thường do ai cung cấp? | Composition root, factory hoặc phạm vi (scope) quản lý đối tượng | Caller của thao tác, thường từ request hoặc use case phía trên |
| Thường đặt ở đâu? | Trường `private final`, nhận qua constructor nếu cần trong suốt vòng đời đối tượng | Biến cục bộ và tham số của phương thức |
| Thời gian tồn tại | Theo vòng đời của collaborator và đối tượng sử dụng nó | Trong một lần xử lý cụ thể |
| Cách thay đổi ở kiểm thử | Truyền một fake/stub khác để kiểm soát hành vi | Truyền các giá trị đầu vào khác nhau để kiểm tra trường hợp |

Từ “phụ thuộc” có hai tầng nghĩa dễ gây nhầm: ở nghĩa rộng, hàm cũng phụ thuộc vào dữ liệu đầu vào để tính kết quả; nhưng khi nói về **dependency injection giữa các thành phần**, ta chủ yếu bàn về việc cung cấp các cộng tác viên hoặc tài nguyên cần thiết từ bên ngoài. Không vì một đối tượng là tham số mà mặc định phải đăng ký nó trong DI container.

## 2. Ví dụ Java thuần: tiêm hành vi, truyền dữ liệu

Ví dụ sau chỉ dùng Java 17 trở lên. Lưu toàn bộ vào `ShippingQuoteDemo.java`:

```java
import java.math.BigDecimal;
import java.util.Objects;

public final class ShippingQuoteDemo {

    // Dữ liệu riêng cho từng yêu cầu báo giá.
    record QuoteRequest(String zone, int weightGrams) {
        QuoteRequest {
            Objects.requireNonNull(zone, "zone");
            if (zone.isBlank() || weightGrams <= 0) {
                throw new IllegalArgumentException("Invalid quote request");
            }
        }
    }

    record Quote(BigDecimal amount, String currency) {}

    // Hợp đồng của cộng tác viên: cung cấp hành vi tính cước.
    @FunctionalInterface
    interface RatePolicy {
        BigDecimal calculate(String zone, int weightGrams);
    }

    static final class StandardRatePolicy implements RatePolicy {
        @Override
        public BigDecimal calculate(String zone, int weightGrams) {
            BigDecimal base = switch (zone) {
                case "LOCAL" -> new BigDecimal("10000");
                case "REMOTE" -> new BigDecimal("20000");
                default -> throw new IllegalArgumentException("Unknown zone");
            };
            return base.add(
                BigDecimal.valueOf(weightGrams).multiply(new BigDecimal("5"))
            );
        }
    }

    static final class ShippingQuoteService {
        private final RatePolicy ratePolicy;

        // Constructor injection: nhận cộng tác viên bắt buộc một lần.
        ShippingQuoteService(RatePolicy ratePolicy) {
            this.ratePolicy = Objects.requireNonNull(ratePolicy, "ratePolicy");
        }

        // Dữ liệu thay đổi theo từng lời gọi.
        Quote quote(QuoteRequest request) {
            Objects.requireNonNull(request, "request");
            BigDecimal amount =
                ratePolicy.calculate(request.zone(), request.weightGrams());
            return new Quote(amount, "VND");
        }
    }

    public static void main(String[] args) {
        // Composition root tối giản: nơi tạo và lắp các đối tượng.
        RatePolicy policy = new StandardRatePolicy();
        ShippingQuoteService service = new ShippingQuoteService(policy);

        System.out.println(service.quote(new QuoteRequest("LOCAL", 500)));
        System.out.println(service.quote(new QuoteRequest("REMOTE", 750)));
    }
}
```

Chạy:

```bash
javac ShippingQuoteDemo.java
java ShippingQuoteDemo
```

Kết quả:

```text
Quote[amount=12500, currency=VND]
Quote[amount=23750, currency=VND]
```

Để đọc đúng ý nghĩa thiết kế, hãy lần theo ba ranh giới:

1. **`main` chọn cách triển khai chính sách.** Nó tạo `StandardRatePolicy` và truyền vào constructor. `ShippingQuoteService` chỉ biết hợp đồng `RatePolicy`, không cần biết cách tạo chính sách.
2. **`quote(request)` nhận tình huống cần xử lý.** Hai lời gọi dùng *cùng một* `ShippingQuoteService`, nhưng có `QuoteRequest` khác nhau. Dịch vụ không giữ `zone` và `weightGrams` thành trạng thái của đối tượng.
3. **`Quote` là dữ liệu kết quả.** Nó được tạo riêng cho từng lời gọi; kết quả không cần được inject trở lại dịch vụ.

Ở ví dụ này, `StandardRatePolicy` không giữ trạng thái và có thể dùng chung. Điều đó phù hợp với implementation hiện tại, nhưng **“collaborator” không đồng nghĩa “singleton”**: repository, unit of work hay tài nguyên khác có thể cần scope ngắn hơn. Scope phải tuân theo an toàn truy cập và quyền sở hữu tài nguyên.

## 3. Vì sao không đưa dữ liệu từng lời gọi vào constructor của dịch vụ dùng chung?

Một thiết kế kém phù hợp là bắt `ShippingQuoteService` giữ yêu cầu đang xử lý:

```java
// Ví dụ cần tránh nếu service được dùng lại giữa nhiều request.
final class ProblematicQuoteService {
    private final RatePolicy ratePolicy;
    private QuoteRequest currentRequest;

    ProblematicQuoteService(RatePolicy ratePolicy) {
        this.ratePolicy = ratePolicy;
    }

    Quote quote(QuoteRequest request) {
        this.currentRequest = request;
        return new Quote(
            ratePolicy.calculate(
                currentRequest.zone(), currentRequest.weightGrams()
            ),
            "VND"
        );
    }
}
```

Trong một service được chia sẻ, hai luồng có thể ghi đè `currentRequest` của nhau. Ngay cả khi chương trình chạy tuần tự, trường này vẫn tạo ra trạng thái không cần thiết và làm khó việc suy luận một lời gọi có phụ thuộc lời gọi trước hay không.

Một biến thể khác là tạo `ShippingQuoteService(policy, request)` cho **mỗi lần báo giá** rồi gọi `quote()`. Cách đó không tự động sai: có thể phù hợp cho *command object* được thiết kế cố ý chỉ sống một lần. Tuy nhiên, nếu mục tiêu là một **dịch vụ nghiệp vụ tái sử dụng**, việc truyền `request` vào `quote(request)` diễn đạt hợp đồng rõ hơn và không buộc tạo lại service.

Ở chiều ngược lại, tự tạo cộng tác viên bên trong mỗi lần xử lý cũng làm mất quyền kiểm soát từ bên ngoài:

```java
Quote quote(QuoteRequest request) {
    RatePolicy policy = new StandardRatePolicy(); // Cố định implementation.
    return new Quote(
        policy.calculate(request.zone(), request.weightGrams()), "VND"
    );
}
```

Đoạn mã này vẫn cho kết quả đúng với yêu cầu đơn giản, nhưng khi đổi cách tính phí hoặc cần stub trong kiểm thử, ta phải sửa hoặc đi vòng qua mã sản xuất. Nếu `RatePolicy` là một phụ thuộc bắt buộc và ổn định của dịch vụ, constructor injection là lựa chọn dễ hiểu hơn.

## 4. Kiểm thử hai khía cạnh độc lập, không cần DI container

Vì `ShippingQuoteService` nhận `RatePolicy` qua constructor, có thể thay implementation bằng stub để kiểm tra *đường truyền dữ liệu*, không phụ thuộc công thức giá thật.

Lưu đoạn sau vào `ShippingQuoteServiceCheck.java` cùng thư mục với file ví dụ:

```java
import java.math.BigDecimal;

public final class ShippingQuoteServiceCheck {
    public static void main(String[] args) {
        ShippingQuoteDemo.RatePolicy stub = (zone, weightGrams) -> {
            if (!"REMOTE".equals(zone) || weightGrams != 750) {
                throw new AssertionError("Wrong per-call input");
            }
            return new BigDecimal("35000");
        };

        var service = new ShippingQuoteDemo.ShippingQuoteService(stub);
        var request = new ShippingQuoteDemo.QuoteRequest("REMOTE", 750);

        var result = service.quote(request);

        if (result.amount().compareTo(new BigDecimal("35000")) != 0) {
            throw new AssertionError("Wrong amount");
        }
        if (!"VND".equals(result.currency())) {
            throw new AssertionError("Wrong currency");
        }
        System.out.println("PASS");
    }
}
```

```bash
javac ShippingQuoteDemo.java ShippingQuoteServiceCheck.java
java ShippingQuoteServiceCheck
```

Kiểm thử này xác nhận hai điều riêng biệt:

- Stub được **inject** làm cộng tác viên và quyết định giá trả về; service không âm thầm tạo một `StandardRatePolicy` khác.
- `zone` và `weightGrams` từ **lời gọi hiện tại** được chuyển đúng tới cộng tác viên, không bị cố định trong constructor hoặc lấy từ trạng thái của lời gọi trước.

Để kiểm tra thuật toán tính cước thật, hãy kiểm thử riêng `StandardRatePolicy` với các vùng và khối lượng biên. Khi tách hành vi khỏi dữ liệu theo cách này, mỗi kiểm thử có một đối tượng trách nhiệm rõ ràng.

## 5. Các trường hợp dễ phân loại nhầm

| Thành phần | Cách hiểu theo vai trò | Cách truyền thường phù hợp |
|---|---|---|
| `CustomerRepository` truy vấn khách hàng | Cộng tác viên cung cấp hành vi truy vấn | Constructor của service dùng repository |
| `customerId` của khách đang xem | Dữ liệu xác định đối tượng thao tác lần này | `findCustomer(customerId)` |
| `Clock` để xác định thời điểm “bây giờ” | Cộng tác viên cung cấp nguồn thời gian, thay được khi kiểm thử | Constructor nếu service cần nguồn thời gian |
| `Instant requestedAt` do client gửi | Dữ liệu thời điểm thuộc yêu cầu cụ thể | Tham số phương thức hoặc DTO |
| `EmailSender` | Cộng tác viên thực hiện gửi | Constructor, hoặc cơ chế cung cấp theo scope |
| `emailAddress`, `messageBody` | Dữ liệu của lần gửi | `send(address, body)` |
| `Locale` chọn theo HTTP request | Dữ liệu ngữ cảnh của lần gọi | DTO/tham số của request |
| `Locale` cố định cho một service cấu hình riêng | Giá trị cấu hình của đối tượng | Constructor là hợp lý, dù không phải service hành vi |
| `Connection` hoặc một unit of work | Cộng tác viên/tài nguyên có vòng đời giới hạn | Cấp theo scope hoặc factory, đóng đúng chủ sở hữu |
| `Comparator` được người gọi chọn riêng cho thao tác | Hành vi được cung cấp *theo lần gọi* | Có thể truyền trực tiếp vào phương thức |

**Không dựa vào dấu hiệu bề ngoài** như “interface là service, record là dữ liệu”, “đối tượng thì inject, primitive thì truyền tham số”, hoặc “thứ có thể mock luôn phải đưa vào constructor”. Một `Predicate` là hành vi nhưng có thể là chiến lược riêng cho từng truy vấn; một cấu hình bất biến là dữ liệu nhưng có thể phải truyền khi tạo đối tượng.

Một câu hỏi hữu ích là: **Ai có quyền lựa chọn giá trị hoặc implementation này, và lựa chọn ấy có được kỳ vọng thay đổi giữa hai lời gọi liên tiếp của cùng service không?**

- Nếu composition root chọn implementation để service dựa vào lâu dài, constructor injection thường diễn đạt đúng ý định.
- Nếu caller chọn thông tin cụ thể của thao tác hiện tại, hãy truyền thông tin đó theo lời gọi.
- Nếu caller thực sự chọn một **chiến lược hành vi** cho từng lời gọi, method injection (truyền collaborator như tham số phương thức) cũng có thể đúng. Không cần ép mọi collaborator vào constructor.
- Nếu một tài nguyên chỉ hợp lệ trong request hoặc transaction, cần bảo đảm vòng đời của service sử dụng không vượt quá vòng đời tài nguyên, hoặc dùng provider/factory lấy tài nguyên ở đúng thời điểm.

## 6. Liên hệ với IoC, composition root và scope

**Inversion of Control** ở đây nằm ở việc `ShippingQuoteService` không quyết định cách khởi tạo `RatePolicy`. Trong ứng dụng nhỏ, `main` đóng vai trò composition root; trong ứng dụng lớn, composition root có thể dùng DI container để lắp *object graph*. Việc dùng container không thay đổi sự khác biệt giữa cộng tác viên và dữ liệu của mỗi request.

Có thể hình dung hai luồng thông tin:

```text
Luồng lắp ghép (thường ít thay đổi)
  composition root ──► RatePolicy ──► ShippingQuoteService

Luồng thực thi (lặp lại theo từng request)
  caller ──► QuoteRequest ──► ShippingQuoteService.quote(…) ──► Quote
```

Nếu mỗi HTTP request cung cấp một `QuoteRequest` mới, **không cần đăng ký từng `QuoteRequest` như bean singleton**. Bản thân request có thể là dữ liệu bất biến và đi qua các lời gọi liên quan. Trường hợp bắt buộc dùng request-scoped component là một quyết định riêng về cơ sở hạ tầng và vòng đời; nó không biến mọi trường dữ liệu của request thành service.

Đặc biệt, hãy tránh inject một đối tượng có vòng đời ngắn vào service có vòng đời dài rồi giữ trực tiếp để dùng sau khi scope kết thúc. Ví dụ, một connection gắn với transaction có thể không còn hợp lệ ở lời gọi tiếp theo. Lúc đó cần thiết kế lại scope hoặc inject factory/provider để lấy connection trong phạm vi thao tác, đồng thời đóng tài nguyên theo đúng cơ chế sở hữu. Chi tiết scope khác nhau giữa Java thuần và từng container, nhưng nguyên tắc vòng đời này giữ nguyên.

## 7. Cách tự ra quyết định khi thiết kế API

Khi một lớp cần một giá trị `X`, hãy trả lời lần lượt:

1. **`X` cung cấp hành vi/tài nguyên hay mô tả yêu cầu cụ thể?** Nếu là ID, số lượng, nội dung request hoặc bộ lọc do caller chọn, bắt đầu bằng tham số của thao tác.
2. **Ai chọn `X`?** Nếu thành phần lắp ghép chọn implementation, ưu tiên đưa từ bên ngoài; nếu người gọi chọn theo nghiệp vụ từng lần, giữ quyền chọn ở caller.
3. **`X` có thay đổi giữa hai lời gọi của cùng đối tượng không?** Nếu có, lưu nó vào field của service dùng chung thường làm phức tạp trạng thái và đồng thời.
4. **`X` sống được bao lâu và ai chịu trách nhiệm giải phóng?** Nếu là tài nguyên ngắn hạn, thiết kế scope/factory hoặc truyền tham số có kiểm soát; không mặc định singleton.
5. **Kiểm thử cần thay cái gì?** Muốn thay hành vi truy vấn/tính toán/gửi, inject fake phù hợp. Muốn kiểm tra nhiều trường hợp nghiệp vụ, thay các giá trị input.

### Bài tập ngắn

Xét chữ ký:

```java
final class OrderService {
    // TODO: thiết kế constructor và phương thức đặt hàng.
}
```

Chức năng đặt hàng cần `InventoryGateway` để kiểm tra tồn kho, `Clock` để ghi thời điểm tạo, `customerId`, `sku` và `quantity` từ lần đặt hàng hiện tại. Một phương án hợp lý:

```java
final class OrderService {
    private final InventoryGateway inventory;
    private final Clock clock;

    OrderService(InventoryGateway inventory, Clock clock) {
        this.inventory = Objects.requireNonNull(inventory);
        this.clock = Objects.requireNonNull(clock);
    }

    OrderReceipt place(String customerId, String sku, int quantity) {
        // Kiểm tra dữ liệu đầu vào và tồn kho, tạo đơn theo clock.instant().
        // Trả về thông tin của đơn hàng vừa tạo.
        throw new UnsupportedOperationException("Exercise");
    }
}
```

`InventoryGateway` và `Clock` là cộng tác viên; `customerId`, `sku`, `quantity` là dữ liệu của lời gọi. Đoạn trên chỉ minh họa **chữ ký và vị trí của phụ thuộc**, chưa phải implementation xử lý đặt hàng. Với một yêu cầu chọn `InventoryGateway` theo từng marketplace, cũng có thể cân nhắc factory hoặc method injection thay vì mặc định dùng một gateway cố định.

## Ghi nhớ

- **Collaborator** trả lời “cần năng lực nào để xử lý?”; **per-call input** trả lời “xử lý yêu cầu cụ thể nào?”.
- Constructor injection phù hợp cho cộng tác viên bắt buộc được lựa chọn khi lắp ghép; tham số phương thức phù hợp cho dữ liệu thay đổi theo lời gọi.
- Scope và vòng đời là quyết định độc lập: cộng tác viên không nhất thiết là singleton, còn input không nhất thiết là primitive hoặc DTO.
- Có thể kiểm chứng thiết kế bằng Java thuần: thay collaborator bằng stub, thay input theo từng trường hợp, quan sát rằng service vẫn dùng lại và không giữ trạng thái request không cần thiết.
