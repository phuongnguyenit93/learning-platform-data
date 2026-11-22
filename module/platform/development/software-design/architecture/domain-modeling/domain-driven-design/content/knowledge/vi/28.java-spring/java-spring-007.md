# Phân biệt Bean Validation với bất biến cần được miền bảo vệ

Một API đặt hàng có thể nhận request với quantity bằng 0, thiếu mã sản phẩm hoặc email sai định dạng. Những lỗi này có thể được phát hiện ngay ở ranh giới HTTP trước khi chạy use case. Nhưng giả sử request có cấu trúc hoàn toàn hợp lệ, số lượng là số dương và SKU đúng định dạng: khách vẫn có thể đặt nhiều hơn lượng hàng khả dụng, sửa một đơn đã giao hoặc rút nhiều tiền hơn số dư. Đây là những quy tắc thuộc nghiệp vụ và phải được bảo vệ trong Domain Model.

**Bean Validation và domain invariant giải quyết hai vấn đề khác nhau.** Bean Validation giúp kiểm tra dữ liệu theo contract ở các boundary như REST request, method parameter hoặc object được framework validate. Domain invariant là điều kiện phải luôn đúng đối với trạng thái nghiệp vụ, bất kể thao tác đến từ REST, message consumer, batch job, command line hay một test.

Trong Java/Spring, Jakarta Bean Validation cung cấp các annotation như @NotNull, @NotBlank, @Positive, @Size, @Email và khả năng định nghĩa constraint tùy chỉnh. Spring MVC có thể kích hoạt validation bằng @Valid hoặc @Validated. Những cơ chế này rất hữu ích, nhưng không thay thế constructor, Value Object, hành vi Aggregate, Domain Service hoặc concurrency control.

Sau bài học này, bạn có thể:

- Phân biệt input validation, application validation và domain invariant.
- Dùng Jakarta Bean Validation với Spring MVC để kiểm tra request.
- Xác định quy tắc nào thuộc DTO, Value Object, Entity/Aggregate hoặc Domain Service.
- Thiết kế custom constraint cho các điều kiện liên quan nhiều field.
- Tránh phụ thuộc vào controller validation để bảo vệ trạng thái domain.
- Phân biệt validation theo dữ liệu hiện tại với invariant cần được bảo vệ đồng thời.
- Ánh xạ lỗi validation và lỗi domain thành response rõ ràng.
- Kiểm thử validation ở boundary và invariant trong domain.

## 1. Ba lớp câu hỏi cần được kiểm tra

Khi một dữ liệu đi vào hệ thống, hãy phân biệt ba câu hỏi:

1. **Request có đúng hình dạng và contract không?** Ví dụ field bắt buộc có tồn tại, chuỗi có đúng định dạng, số lượng có lớn hơn zero không?
2. **Use case có đủ điều kiện để chạy không?** Ví dụ khách hàng có quyền đặt đơn, đơn hàng có tồn tại và đang ở trạng thái cho phép không?
3. **Trạng thái domain sau thao tác có giữ được invariant không?** Ví dụ số dư không âm, Order không có dòng hàng trùng SKU, tổng tiền khớp với các dòng hàng và discount không vượt giới hạn.

Ba nhóm có thể liên quan nhưng không nên bị trộn thành một lớp validation duy nhất.

| Nhóm | Mục tiêu | Ví dụ | Nơi thường kiểm tra |
|---|---|---|---|
| Input/contract validation | Dữ liệu đầu vào có đúng cấu trúc và định dạng | quantity là số dương; email đúng định dạng | Request DTO, API adapter |
| Application/use-case validation | Điều kiện để thực hiện use case có đáp ứng không | Order tồn tại; người gọi có quyền; trạng thái hiện tại cho phép | Application Service, authorization policy |
| Domain invariant | Trạng thái nghiệp vụ luôn hợp lệ trước và sau hành vi | Không rút vượt số dư; không sửa Order đã giao | Value Object, Entity, Aggregate, Domain Service |

Một quy tắc có thể được kiểm tra ở nhiều boundary để phản hồi sớm, nhưng nơi có thẩm quyền cuối cùng phải rõ ràng. Ví dụ API có thể kiểm tra quantity dương để trả lỗi thân thiện; Quantity Value Object vẫn phải từ chối giá trị không hợp lệ khi được tạo từ batch job hoặc message consumer.

## 2. Bean Validation là gì?

Jakarta Bean Validation là đặc tả Java để khai báo và thực thi các constraint trên object, field, property, method parameter hoặc return value. Một implementation phổ biến là Hibernate Validator.

Các constraint thường dùng:

| Annotation | Mục đích | Ví dụ |
|---|---|---|
| @NotNull | Giá trị không được null | customerId |
| @NotBlank | Chuỗi không null, không rỗng và có ký tự không phải khoảng trắng | customerName |
| @NotEmpty | Collection/string không được rỗng | Danh sách dòng hàng |
| @Size | Giới hạn kích thước | Tên tối đa 100 ký tự |
| @Positive | Số lớn hơn zero | Số lượng |
| @PositiveOrZero | Số không âm | Phí bổ sung |
| @Min, @Max | Giới hạn số nguyên | Tuổi trong một khoảng |
| @DecimalMin, @DecimalMax | Giới hạn số thập phân | Tỷ lệ discount |
| @Email | Kiểm tra định dạng email ở mức cơ bản | Địa chỉ liên hệ |
| @Pattern | Kiểm tra theo regular expression | Mã tham chiếu có format cố định |
| @Past, @Future | Kiểm tra quan hệ với thời điểm hiện tại | Ngày sinh, thời điểm hẹn |

Constraint thường được khai báo trên DTO:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public record CreateCustomerRequest(
    @NotBlank
    @Size(max = 100)
    String fullName,

    @NotBlank
    @Email
    String email,

    @NotNull
    @Positive
    Integer age
) {}
~~~

Khi controller nhận request, Spring MVC có thể validate object trước khi gọi method body:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CustomerController {
    private final RegisterCustomerUseCase registerCustomer;

    public CustomerController(RegisterCustomerUseCase registerCustomer) {
        this.registerCustomer = registerCustomer;
    }

    @PostMapping("/customers")
    @ResponseStatus(HttpStatus.CREATED)
    public CustomerResponse create(
            @Valid @RequestBody CreateCustomerRequest request) {
        return CustomerResponse.from(
            registerCustomer.execute(
                new RegisterCustomerCommand(
                    request.fullName(),
                    request.email(),
                    request.age()
                )
            )
        );
    }
}
~~~

Nếu request vi phạm constraint, Spring MVC thông thường không gọi method body và trả lỗi validation theo exception handling đã cấu hình. Đây là cách phản hồi sớm cho lỗi contract.

### Dependency cần có

Với Spring Boot, thường thêm starter validation:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Spring Boot 3 dùng namespace jakarta.validation.*. Các ứng dụng Spring Boot 2 cũ có thể dùng javax.validation.*; không trộn hai namespace trong cùng một ứng dụng. Starter thường đưa Hibernate Validator vào classpath và Spring Boot tự cấu hình validator.

## 3. @Valid và @Validated trong Spring

Hai annotation có liên quan nhưng không hoàn toàn giống nhau.

- @Valid là annotation chuẩn Jakarta Bean Validation để yêu cầu validate object và cascade vào object lồng nhau.
- @Validated là annotation của Spring, có thể kích hoạt method validation và hỗ trợ validation groups ở các vị trí Spring quản lý.

Ví dụ:

~~~java
@PostMapping("/orders")
public OrderResponse place(
        @Valid @RequestBody PlaceOrderRequest request) {
    return orderUseCase.place(request);
}
~~~

Ở đây @Valid yêu cầu Spring MVC validate request body.

Với method validation trên một Spring bean:

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.validation.annotation.Validated;
import org.springframework.stereotype.Service;

@Service
@Validated
public class CustomerLookupService {
    public Customer findByEmail(@NotBlank String email) {
        // Lookup...
        return null;
    }
}
~~~

Method validation của Spring thường dựa vào proxy, vì vậy self-invocation trong cùng object có thể không đi qua proxy và không kích hoạt validation như mong đợi. Cần kiểm tra cách gọi thực tế và phiên bản Spring đang dùng.

### Cascade validation với @Valid

@Valid trên field hoặc record component cho phép validator đi sâu vào object lồng nhau:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import java.util.List;

public record PlaceOrderRequest(
    @NotBlank
    String customerId,

    @NotEmpty
    List<@NotNull @Valid PlaceOrderLineRequest> lines
) {}

public record PlaceOrderLineRequest(
    @NotBlank
    String sku,

    @NotNull
    @Positive
    Integer quantity
) {}
~~~

Khai báo @Valid trên phần tử collection giúp validate từng PlaceOrderLineRequest. @NotNull ở phần tử ngăn một phần tử null lọt qua. @NotEmpty trên list chỉ đảm bảo list không rỗng, không chứng minh tổng số lượng hoặc SKU là hợp lệ trong domain.

## 4. Bean Validation không phải nơi duy nhất bảo vệ dữ liệu

Một request có thể đi vào hệ thống qua nhiều đường:

~~~text
REST Controller ----+
Message Consumer ---+----> Application Use Case ----> Domain Model
Batch Job ----------+
Admin CLI ----------+
Scheduled Task -----+
~~~

Nếu quy tắc chỉ được kiểm tra bằng @Valid trên REST controller, các đường vào khác có thể bỏ qua kiểm tra đó. Một message consumer có thể tạo Order với quantity âm; batch job có thể rút tiền vượt số dư; test có thể gọi thẳng constructor.

Domain Model phải bảo vệ invariant tại nơi trạng thái được tạo hoặc thay đổi. Controller validation giúp phát hiện lỗi sớm và cải thiện thông báo, nhưng không phải hàng rào duy nhất.

Một nguyên tắc thực tế:

- Kiểm tra format, độ dài, field bắt buộc và giới hạn request ở DTO/API boundary.
- Đưa quy tắc gắn với ý nghĩa của một giá trị vào Value Object.
- Đưa invariant liên quan trạng thái và vòng đời vào Entity/Aggregate.
- Đưa quy tắc phối hợp nhiều đối tượng vào Domain Service hoặc use case phù hợp.
- Dùng database constraint và concurrency control làm lớp bảo vệ cuối cho các điều kiện persistence cần tính nguyên tử.

## 5. Domain invariant là gì?

Invariant là điều kiện phải luôn đúng đối với một đối tượng hoặc một ranh giới nghiệp vụ. Nó không chỉ là điều kiện để một request được chấp nhận; nó là điều kiện mà mọi hành vi hợp lệ phải duy trì.

Ví dụ:

- Số dư tài khoản không được âm nếu sản phẩm không cho phép thấu chi.
- Quantity của OrderLine phải lớn hơn zero.
- Order đã giao không thể quay lại trạng thái Draft.
- Một Order không chứa hai dòng hàng có cùng SKU nếu domain quy định mỗi SKU chỉ có một dòng.
- Discount không vượt quá subtotal.
- Một Reservation không được giải phóng hai lần.

Invariant thường được diễn đạt như một quy tắc domain, không phải thông báo lỗi HTTP. Ví dụ InsufficientFunds hoặc OrderCannotBeEdited diễn đạt điều kiện nghiệp vụ; controller có thể chuyển chúng thành error code hoặc response phù hợp.

### Invariant phải đúng qua mọi đường gọi

Giả sử chỉ controller kiểm tra số dư:

~~~java
if (request.amount().compareTo(account.balance()) > 0) {
    throw new InsufficientFundsApiException();
}
account.withdraw(request.amount());
~~~

Nếu batch job gọi account.withdraw() trực tiếp, kiểm tra có thể bị bỏ qua. Hãy đặt điều kiện ngay trong hành vi Account:

~~~java
public void withdraw(Money amount) {
    if (amount.isZeroOrNegative()) {
        throw new InvalidWithdrawalAmountException();
    }
    if (balance.isLessThan(amount)) {
        throw new InsufficientFundsException();
    }
    balance = balance.subtract(amount);
}
~~~

Khi đó mọi caller đều phải đi qua cùng quy tắc domain.

## 6. Đưa validation vào Value Object

Value Object đại diện một khái niệm có ý nghĩa và thường tự bảo vệ tính hợp lệ của giá trị. Đây là nơi phù hợp cho những quy tắc chỉ phụ thuộc vào chính giá trị đó.

Ví dụ Quantity:

~~~java
public record Quantity(int value) {
    public Quantity {
        if (value <= 0) {
            throw new InvalidQuantityException(value);
        }
    }
}
~~~

Ví dụ EmailAddress:

~~~java
public record EmailAddress(String value) {
    public EmailAddress {
        if (value == null || value.isBlank()) {
            throw new InvalidEmailAddressException();
        }
        if (!value.contains("@")) {
            throw new InvalidEmailAddressException();
        }
    }
}
~~~

Kiểm tra contains("@") chỉ là minh họa đơn giản; quy tắc xác thực email thực tế có thể cần chuẩn hóa, parser và xác minh qua email. Không nên coi @Email hoặc regular expression là bằng chứng địa chỉ thực sự tồn tại.

Sau khi Value Object được tạo thành công, domain có thể dựa vào contract rằng giá trị đáp ứng điều kiện đã định nghĩa. Điều này giảm việc lặp lại cùng kiểm tra ở nhiều nơi.

### Bean Validation và Value Object có thể bổ trợ nhau

DTO có thể dùng @Positive để phản hồi sớm. Khi mapping sang domain, constructor Quantity vẫn kiểm tra value lớn hơn zero. Hai lần kiểm tra phục vụ hai boundary:

~~~java
public record PlaceOrderLineRequest(
    @NotNull @Positive Integer quantity
) {}

// Mapping/application boundary
Quantity quantity = new Quantity(request.quantity());
~~~

Nếu một message consumer không dùng DTO này, Quantity vẫn không thể được tạo với giá trị không hợp lệ.

Không nhất thiết phải gắn annotation Bean Validation lên mọi Value Object. Có thể làm vậy nếu domain chấp nhận dependency vào Jakarta Validation, nhưng cần cân nhắc việc framework trở thành một phần của domain model. Constructor validation thuần Java thường giữ domain độc lập hơn.

## 7. Đặt invariant trong Entity và Aggregate Root

Invariant phụ thuộc vào state hoặc quan hệ giữa các thành phần bên trong một Aggregate nên được bảo vệ tại Aggregate Root.

Ví dụ Order:

~~~java
public class Order {
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;

    public void addLine(Sku sku, Quantity quantity, Money unitPrice) {
        ensureEditable();

        boolean alreadyExists = lines.stream()
            .anyMatch(line -> line.sku().equals(sku));

        if (alreadyExists) {
            throw new DuplicateOrderLineException(sku);
        }

        lines.add(new OrderLine(sku, quantity, unitPrice));
    }

    public void changeLineQuantity(Sku sku, Quantity quantity) {
        ensureEditable();
        findLine(sku).changeQuantity(quantity);
    }

    public void submit() {
        ensureEditable();
        if (lines.isEmpty()) {
            throw new EmptyOrderCannotBeSubmittedException();
        }
        status = OrderStatus.SUBMITTED;
    }

    private void ensureEditable() {
        if (status != OrderStatus.DRAFT) {
            throw new OrderCannotBeEditedException(status);
        }
    }

    private OrderLine findLine(Sku sku) {
        return lines.stream()
            .filter(line -> line.sku().equals(sku))
            .findFirst()
            .orElseThrow(() -> new OrderLineNotFoundException(sku));
    }
}
~~~

Caller không thể thêm dòng trùng SKU hoặc sửa đơn sau khi submit bằng cách gọi một setter tùy ý. Aggregate Root bảo vệ trạng thái và điều kiện chuyển đổi.

Nếu OrderLine là entity nội bộ của Order Aggregate, không nên để controller hoặc module khác nạp và sửa nó độc lập qua một repository riêng. Thay đổi nên đi qua Order.

## 8. Quy tắc liên quan nhiều field

Một số constraint không thể kiểm tra bằng annotation trên một field đơn lẻ. Ví dụ:

- startDate phải trước endDate.
- minimumAmount không được lớn hơn maximumAmount.
- Chỉ được cung cấp companyTaxId khi customer type là BUSINESS.

Có hai cách thường dùng:

1. Tạo custom class-level constraint trên request DTO để báo lỗi sớm ở API boundary.
2. Biểu diễn quan hệ đó trong constructor/Value Object/Aggregate nếu nó là quy tắc domain.

### Custom class-level constraint

Annotation:

~~~java
import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.Retention;
import java.lang.annotation.Target;
import static java.lang.annotation.ElementType.TYPE;
import static java.lang.annotation.RetentionPolicy.RUNTIME;

@Target(TYPE)
@Retention(RUNTIME)
@Constraint(validatedBy = ValidDateRangeValidator.class)
@Documented
public @interface ValidDateRange {
    String message() default "Ngày kết thúc phải sau ngày bắt đầu";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class ValidDateRangeValidator
        implements ConstraintValidator<ValidDateRange, BookingRequest> {

    @Override
    public boolean isValid(
            BookingRequest value,
            ConstraintValidatorContext context) {
        if (value == null
                || value.startDate() == null
                || value.endDate() == null) {
            return true;
        }

        return value.startDate().isBefore(value.endDate());
    }
}
~~~

DTO:

~~~java
import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;

@ValidDateRange
public record BookingRequest(
    @NotNull LocalDate startDate,
    @NotNull LocalDate endDate
) {}
~~~

Validator trả true khi object hoặc một field cần thiết là null vì @NotNull chịu trách nhiệm báo lỗi null riêng. Cách này tránh tạo hai lỗi chồng lấp cho cùng một nguyên nhân. Nếu contract cần một thông báo tổng hợp, có thể tùy chỉnh ConstraintValidatorContext để gắn violation vào property cụ thể.

### Domain vẫn phải bảo vệ quy tắc

Nếu ngày bắt đầu và kết thúc xác định thời hạn của một Booking, domain nên có kiểu giá trị biểu diễn khoảng ngày hợp lệ:

~~~java
public record BookingPeriod(LocalDate start, LocalDate end) {
    public BookingPeriod {
        Objects.requireNonNull(start);
        Objects.requireNonNull(end);
        if (!start.isBefore(end)) {
            throw new InvalidBookingPeriodException(start, end);
        }
    }
}
~~~

API có thể dùng @ValidDateRange để báo lỗi thân thiện. Domain tạo BookingPeriod để bảo đảm mọi đường tạo Booking đều tuân thủ quy tắc.

## 9. Validation phụ thuộc dữ liệu hiện tại không phải lúc nào cũng là invariant cục bộ

Một số kiểm tra cần truy vấn dữ liệu hoặc phụ thuộc dịch vụ khác:

- Customer có tồn tại không?
- SKU có đang được bán không?
- Coupon đã được sử dụng chưa?
- Phòng có còn trống trong khoảng thời gian yêu cầu không?
- Người dùng có quyền thực hiện thao tác không?

Không nên nhét mọi kiểm tra đó vào annotation validator có truy cập database. Cách này dễ biến validation thành một tầng service locator khó kiểm thử, tạo N+1 query, che giấu transaction và làm domain phụ thuộc framework.

Hãy phân loại:

- Kiểm tra tồn tại để đưa ra lỗi sớm: application service/query có thể thực hiện.
- Quyết định nghiệp vụ: domain policy hoặc Aggregate phải xác nhận.
- Bảo đảm không có race condition: transaction, lock, unique/exclusion constraint hoặc cơ chế atomic reservation.

Ví dụ, API kiểm tra phòng còn trống rồi mới tạo booking. Một request khác có thể đặt phòng giữa hai bước. Kết quả kiểm tra ban đầu trở nên cũ. Vì vậy, thao tác giữ phòng phải được thực hiện nguyên tử tại nơi sở hữu availability.

## 10. Invariant liên Aggregate và Domain Service

Một invariant có thể liên quan nhiều Aggregate. Ví dụ, một Customer có hạn mức mua chịu 100 triệu và nhiều Order đang chờ thanh toán. Việc chấp nhận một Order mới cần kiểm tra tổng exposure của Customer.

Không nên đưa mọi Aggregate vào một object khổng lồ. Có thể dùng Domain Service hoặc application/domain policy để phối hợp:

~~~java
public class CreditPolicy {
    public void ensureCanAccept(
            BuyerAccount buyer,
            Money proposedExposure) {
        Money projected = buyer.currentExposure().add(proposedExposure);

        if (projected.isGreaterThan(buyer.creditLimit())) {
            throw new CreditLimitExceededException();
        }
    }
}
~~~

Use case tải các Aggregate cần thiết, gọi policy và thực hiện thay đổi trong transaction phù hợp:

~~~java
@Transactional
public void acceptOrder(OrderId orderId) {
    Order order = orders.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);
    BuyerAccount buyer = buyers.findById(order.buyerId())
        .orElseThrow(BuyerNotFoundException::new);

    creditPolicy.ensureCanAccept(buyer, order.total());
    buyer.recordExposure(order.id(), order.total());
    order.accept();

    buyers.save(buyer);
    orders.save(order);
}
~~~

Ví dụ giả định cả hai Aggregate có thể được lưu trong cùng transactional resource và transaction bao trùm cả hai. Nếu nhiều request cùng kiểm tra một hạn mức, chỉ kiểm tra trong bộ nhớ là chưa đủ; cần concurrency control để tránh cả hai cùng vượt hạn mức.

Nếu hai Aggregate thuộc hai service/database độc lập, không thể giả định một local transaction bảo vệ invariant toàn cục. Có thể cần reservation, trạng thái chờ, giới hạn phân bổ hoặc Saga tùy nghiệp vụ.

## 11. Database constraint là lớp bảo vệ bổ sung

Database có thể bảo vệ một số điều kiện bằng:

- NOT NULL
- CHECK
- UNIQUE
- FOREIGN KEY
- Exclusion constraint hoặc cơ chế locking phù hợp cho khoảng thời gian chồng lấp.

Ví dụ:

~~~sql
CREATE TABLE order_line (
    order_id UUID NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, sku)
);
~~~

Database đảm bảo quantity dương và mỗi SKU chỉ xuất hiện một lần trong một Order. Domain vẫn cần bảo vệ các quy tắc này để đưa ra hành vi và lỗi có ý nghĩa trước khi ghi. Database constraint bảo vệ trước race condition, bug ở đường ghi khác hoặc dữ liệu bị thao tác ngoài application.

### Database constraint không thay thế domain model

Nếu chỉ dựa vào CHECK (quantity > 0), ứng dụng có thể nhận lỗi SQL khó hiểu khi ghi dữ liệu sai. Nếu chỉ kiểm tra trong Java, một đường ghi khác hoặc hai transaction đồng thời có thể vi phạm điều kiện.

Thiết kế tốt thường có nhiều lớp:

1. DTO validation phản hồi sớm.
2. Domain model bảo vệ invariant và diễn đạt ý nghĩa nghiệp vụ.
3. Database constraint bảo vệ tính toàn vẹn dữ liệu ở tầng lưu trữ.

Không phải mọi quy tắc domain đều có thể hoặc nên biểu diễn bằng constraint SQL. Hãy dùng database constraint cho điều kiện mà database có thể bảo vệ chính xác và nguyên tử.

## 12. Concurrency: validation trước đó có thể trở nên lỗi thời

Một lỗi phổ biến là đọc trạng thái, kiểm tra điều kiện, rồi cập nhật sau mà không bảo vệ khoảng thời gian giữa hai bước.

Ví dụ tồn kho:

~~~text
available = 1

Request A reads available = 1
Request B reads available = 1

A validates quantity 1 <= 1
B validates quantity 1 <= 1

A reserves 1
B reserves 1

Result without concurrency protection: reserved = 2
~~~

Mỗi request đều vượt qua validation khi nhìn trạng thái cũ. Nhưng invariant tồn kho đã bị phá vì hai quyết định cùng dựa trên một snapshot.

Có thể dùng optimistic locking, pessimistic locking hoặc câu lệnh cập nhật có điều kiện:

~~~sql
UPDATE stock
SET available_quantity = available_quantity - :requested
WHERE sku = :sku
  AND available_quantity >= :requested;
~~~

Nếu số hàng cập nhật là zero, thao tác không giữ được hàng. Quyết định cuối phải được diễn đạt thành kết quả domain như StockUnavailable. Cần bảo đảm thao tác cập nhật và ghi Reservation được commit cùng transaction.

Bean Validation không giải quyết concurrency. Nó kiểm tra dữ liệu đầu vào tại thời điểm validate, không khóa trạng thái hay bảo đảm điều kiện vẫn đúng khi commit.

## 13. Validation Groups: dùng có chọn lọc

Jakarta Bean Validation hỗ trợ groups để chạy các constraint khác nhau theo một nhóm. Ví dụ form có thể có chế độ tạo mới và cập nhật.

~~~java
public interface Create {}
public interface Update {}

public record CustomerRequest(
    @NotBlank(groups = {Create.class, Update.class})
    String name,

    @NotNull(groups = Create.class)
    String externalReference
) {}
~~~

Controller:

~~~java
public CustomerResponse create(
        @Validated(Create.class) @RequestBody CustomerRequest request) {
    // ...
}
~~~

Lưu ý: khi gọi validate với một group cụ thể, group Default không tự động luôn được chạy trừ khi được khai báo hoặc cấu hình group sequence phù hợp. Hãy đọc contract của validation groups và test các group cần thiết.

Groups hữu ích khi contract đầu vào thực sự khác nhau. Nhưng nếu create/update có field và semantics khác nhau nhiều, hai request DTO riêng thường dễ hiểu hơn một DTO có hàng chục group và điều kiện.

Không nên dùng validation group để mô phỏng trạng thái domain như Draft, Submitted, Approved. Những trạng thái đó thuộc vòng đời Aggregate và cần được bảo vệ bằng hành vi domain.

## 14. Custom validator không nên chứa business workflow

Một ConstraintValidator nên là phép kiểm tra ngắn, có thể dự đoán và tập trung vào dữ liệu của object đang validate. Không nên biến nó thành nơi:

- Gọi nhiều repository để điều phối use case.
- Thay đổi trạng thái domain.
- Gửi email hoặc message.
- Gọi API thanh toán.
- Giữ lock hoặc mở transaction dài.
- Quyết định một quy trình nghiệp vụ nhiều bước.

Ví dụ @UniqueEmail có thể truy vấn repository để kiểm tra email đã tồn tại, nhưng vẫn có race condition nếu hai request đồng thời cùng qua validator. Unique constraint ở database vẫn cần thiết. Ngoài ra, validator truy vấn database có thể làm validation phụ thuộc vào persistence và khó kiểm soát hiệu năng.

Với quy tắc cần dữ liệu hoặc transaction, application service thường là nơi rõ ràng hơn:

~~~java
public RegisterCustomerResult register(RegisterCustomerCommand command) {
    if (customers.existsByEmail(command.email())) {
        return RegisterCustomerResult.emailAlreadyUsed();
    }

    Customer customer = Customer.register(
        new EmailAddress(command.email())
    );
    customers.add(customer);
    return RegisterCustomerResult.registered(customer.id());
}
~~~

Đoạn code minh họa cách trả kết quả dự kiến. Nếu email phải duy nhất tuyệt đối, database unique constraint cần bảo vệ race condition; application layer chuyển constraint violation tương ứng thành kết quả phù hợp.

## 15. Ánh xạ lỗi Bean Validation trong Spring

Với Spring MVC, request body không hợp lệ thường dẫn đến MethodArgumentNotValidException. Có thể dùng @RestControllerAdvice để chuẩn hóa response:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ProblemDetail handleValidation(
            MethodArgumentNotValidException exception) {
        ProblemDetail problem = ProblemDetail.forStatus(
            HttpStatus.BAD_REQUEST
        );
        problem.setTitle("Request không hợp lệ");
        problem.setDetail("Một hoặc nhiều trường không đáp ứng yêu cầu.");

        var errors = exception.getBindingResult()
            .getFieldErrors()
            .stream()
            .map(error -> new FieldErrorResponse(
                error.getField(),
                error.getCode()
            ))
            .toList();

        problem.setProperty("errors", errors);
        return problem;
    }
}

public record FieldErrorResponse(String field, String code) {}
~~~

ProblemDetail có trong Spring Framework 6+. Với phiên bản cũ hơn, có thể dùng response DTO riêng. Không nên trả trực tiếp thông điệp exception hoặc giá trị rejected có thể chứa dữ liệu nhạy cảm.

### Method validation có thể phát sinh exception khác

Tùy vị trí annotation và phiên bản Spring, lỗi method validation có thể được biểu diễn bởi ConstraintViolationException hoặc HandlerMethodValidationException. Hãy xử lý theo stack đang dùng thay vì giả định mọi validation đều đi qua MethodArgumentNotValidException.

### Domain exception là một nhóm khác

Ví dụ InsufficientFundsException không phải lỗi Bean Validation. Nó là kết quả của quy tắc domain. Application/API boundary có thể ánh xạ thành mã lỗi nghiệp vụ như INSUFFICIENT_FUNDS, thường dùng status theo contract API, ví dụ 409 hoặc 422 tùy semantics.

Không nên biến mọi domain exception thành lỗi field validation. Một lỗi như ORDER_ALREADY_SHIPPED không phải lỗi định dạng của request.

## 16. Không để message validation trở thành contract logic

Annotation có thể khai báo message:

~~~java
@NotBlank(message = "Tên khách hàng là bắt buộc")
String name
~~~

Thông điệp này hữu ích cho người dùng, nhưng client không nên phân tích chuỗi tiếng Việt để quyết định logic. Hãy trả error code ổn định và field path:

~~~json
{
  "type": "https://example.test/problems/validation",
  "title": "Request không hợp lệ",
  "status": 400,
  "errors": [
    {
      "field": "lines[0].quantity",
      "code": "Positive",
      "message": "Số lượng phải lớn hơn 0"
    }
  ]
}
~~~

Message có thể được bản địa hóa; code là contract máy đọc được. Không đưa stack trace, SQL, class name nội bộ hoặc thông tin người dùng khác vào response.

## 17. Validation và bảo mật

Validation không thay thế authorization hoặc kiểm soát quyền truy cập.

Ví dụ, customerId có định dạng UUID hợp lệ không có nghĩa người gọi được phép đặt hàng cho customer đó. Việc xác thực danh tính, kiểm tra quyền và xác định tenant thuộc security/application boundary.

Tương tự:

- @Email không chứng minh người dùng sở hữu email.
- @Pattern không chứng minh SKU tồn tại hoặc được phép bán.
- @Positive không chứng minh khách có đủ hạn mức.
- @Valid không ngăn người dùng sửa ID để truy cập tài nguyên của người khác.

Hãy kiểm tra quyền trên tài nguyên và tenant trong use case hoặc security policy phù hợp. Tránh mass assignment bằng cách dùng request DTO có field được phép rõ ràng, không bind trực tiếp mọi field của Entity.

## 18. Thời gian, múi giờ và validation phụ thuộc đồng hồ

Constraint như @Future có thể hữu ích cho request, nhưng thời điểm hiện tại là một dependency. Test dễ bị phụ thuộc đồng hồ thực và timezone nếu không kiểm soát.

Với quy tắc domain như thời hạn đặt chỗ phải còn hiệu lực, có thể inject Clock:

~~~java
public class Reservation {
    private final Instant expiresAt;

    public void ensureNotExpired(Clock clock) {
        if (!clock.instant().isBefore(expiresAt)) {
            throw new ReservationExpiredException();
        }
    }
}
~~~

Trong test, dùng Clock.fixed(...) để kiểm soát thời điểm. Với Jakarta Bean Validation, ClockProvider cho phép cung cấp clock khi validate temporal constraints. Đừng để test phụ thuộc vào thời điểm chạy thực tế.

Nếu nghiệp vụ dùng ngày địa phương như ngày giao hàng, cần xác định LocalDate và timezone/business calendar thay vì so sánh timestamp theo timezone mặc định của máy chủ.

## 19. Validation ở persistence layer

Một số JPA provider tích hợp Bean Validation trước khi insert/update entity. Điều này có thể giúp phát hiện dữ liệu không hợp lệ khi persistence. Tuy nhiên, không nên dựa vào callback persistence để thực thi toàn bộ domain behavior.

Ví dụ:

- @Column(nullable = false) và @NotNull có thể diễn đạt yêu cầu field.
- @Size có thể giúp đồng bộ giới hạn chuỗi.
- @UniqueConstraint hoặc unique index có thể bảo vệ tính duy nhất.

Nhưng:

- ORM validation không thay thế Value Object và Aggregate invariant.
- Một native SQL update có thể bỏ qua lifecycle validation của entity.
- Một ứng dụng khác có thể ghi vào cùng database.
- Constraint chỉ chạy khi flush/commit, nên lỗi có thể xuất hiện muộn.
- Validation ở persistence không tự giải quyết race condition nếu không có constraint/locking phù hợp.

Hãy xem Bean Validation ở persistence như một lớp kiểm tra bổ sung, không phải nơi duy nhất đặt quy tắc domain.

## 20. Những sai lầm thường gặp

**Chỉ validate ở controller.** Batch job, consumer và test có thể gọi domain trực tiếp. Invariant phải được bảo vệ trong domain.

**Đưa mọi business rule vào DTO annotation.** DTO không nên quyết định số dư, trạng thái Order hoặc hạn mức Customer.

**Dùng @Valid trên Entity rồi nghĩ Aggregate đã an toàn.** Validation chỉ chạy khi được kích hoạt; caller vẫn có thể thay đổi state qua đường khác.

**Gọi database trong mọi custom validator.** Điều này làm validation chậm, khó test và dễ race condition.

**Dùng validation group để mô hình hóa vòng đời domain.** Draft, Approved và Shipped cần hành vi Aggregate, không phải group annotation.

**Chỉ kiểm tra trước khi ghi mà không xử lý concurrency.** Hai request có thể cùng vượt qua validation trên state cũ. Cần locking, optimistic version hoặc atomic constraint.

**Dùng regex để thay thế Value Object.** Regex có thể kiểm tra format nhưng không biểu diễn semantics, equality hoặc hành vi domain.

**Dựa vào database constraint để thay domain model.** Lỗi SQL không diễn đạt tốt quy tắc và caller có thể nhận phản hồi khó hiểu.

**Bắt mọi exception thành validation error.** Lỗi infrastructure hoặc bug bị che giấu và trả sai status.

**Trả message exception làm API contract.** Câu chữ thay đổi theo provider, phiên bản thư viện và ngôn ngữ; client cần error code ổn định.

**Nhầm validation với authorization.** Dữ liệu hợp lệ không đồng nghĩa người gọi có quyền thao tác.

## 21. Quy trình xác định nơi đặt một quy tắc

Khi gặp một quy tắc mới, hãy hỏi:

**Bước 1: Quy tắc chỉ kiểm tra hình dạng dữ liệu?** Ví dụ độ dài, format, field bắt buộc. Đặt trên request DTO hoặc API boundary.

**Bước 2: Quy tắc thuộc ý nghĩa một giá trị?** Ví dụ quantity dương, currency hợp lệ, khoảng ngày có thứ tự. Dùng Value Object/constructor; có thể lặp kiểm tra sớm ở DTO.

**Bước 3: Quy tắc phụ thuộc state của một Aggregate?** Ví dụ Order chỉ sửa khi Draft. Đặt trong hành vi Aggregate Root.

**Bước 4: Quy tắc phối hợp nhiều đối tượng?** Ví dụ Customer credit exposure sau khi nhận Order. Dùng Domain Service hoặc use case phối hợp theo ownership rõ.

**Bước 5: Quy tắc cần dữ liệu ngoài hoặc quyền?** Ví dụ customer tồn tại, user có quyền, coupon chưa dùng. Kiểm tra ở application/security boundary và để domain quyết định cuối cùng nếu nó bảo vệ invariant.

**Bước 6: Có thể xảy ra đồng thời không?** Nếu hai request cùng vượt qua kiểm tra, dùng transaction, version, lock hoặc database constraint để bảo vệ.

**Bước 7: Phản hồi nào phù hợp?** Lỗi input, business rejection, state conflict, concurrency conflict hay infrastructure failure cần error code và hướng xử lý riêng.

## 22. Kiểm thử validation và invariant

Mỗi lớp validation cần được kiểm tra ở đúng boundary. Một test DTO không chứng minh Aggregate an toàn; một unit test domain cũng không chứng minh Spring MVC đã kích hoạt Bean Validation.

### Test DTO với Jakarta Validator

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.Test;

class CreateCustomerRequestTest {
    @Test
    void rejectsInvalidRequestFields() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            var request = new CreateCustomerRequest(
                "",
                "not-an-email",
                0
            );

            var violations = validator.validate(request);

            assertFalse(violations.isEmpty());
        }
    }
}
~~~

Test này xác nhận constraint trên DTO hoạt động. Trong test chi tiết hơn, hãy kiểm tra property path và constraint code thay vì chỉ xác nhận có violation.

### Test invariant của Value Object và Aggregate

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class QuantityTest {
    @Test
    void rejectsZeroQuantity() {
        assertThrows(
            InvalidQuantityException.class,
            () -> new Quantity(0)
        );
    }
}
~~~

Với Account, cần xác nhận cả exception lẫn trạng thái không đổi:

~~~java
@Test
void cannotWithdrawMoreThanAvailableBalance() {
    Account account = Account.open(
        AccountId.of("ACC-01"),
        Money.vnd(100_000)
    );

    assertThrows(
        InsufficientFundsException.class,
        () -> account.withdraw(Money.vnd(150_000))
    );

    assertEquals(Money.vnd(100_000), account.balance());
}
~~~

Test domain không cần Spring context hoặc database nếu đang kiểm tra một invariant thuần của Aggregate.

### Test controller boundary và concurrency

Một MVC integration test có thể gửi request thiếu field hoặc sai format và xác nhận response lỗi, đồng thời xác nhận use case mock không được gọi. Test này chứng minh Spring MVC đã chạy validation ở đúng endpoint.

Với invariant phụ thuộc dữ liệu đồng thời, cần integration test dùng hai transaction/persistence context độc lập:

~~~text
Given stock has one available unit
And request A and request B both read that state
When A reserves one unit and commits
And B attempts to reserve one unit
Then only one reservation is committed
And available quantity never becomes negative
~~~

Mock repository hoặc unit test tuần tự không chứng minh được locking, optimistic version hay database constraint hoạt động đúng. Hãy test với database engine tương thích môi trường triển khai nếu constraint có semantics riêng.

## 23. Checklist cho Bean Validation và domain invariant

- [ ] Request DTO có constraint cho field bắt buộc, format, độ dài và giới hạn cấu trúc.
- [ ] @Valid được dùng cho object lồng nhau và collection khi cần.
- [ ] @Validated/method validation được dùng đúng boundary và proxy semantics.
- [ ] Custom validator chỉ kiểm tra dữ liệu, không điều phối workflow.
- [ ] Value Object tự bảo vệ điều kiện hợp lệ của giá trị.
- [ ] Aggregate Root bảo vệ invariant phụ thuộc trạng thái và quan hệ nội bộ.
- [ ] Domain invariant không phụ thuộc vào việc controller đã chạy @Valid.
- [ ] Quy tắc liên Aggregate có owner và transaction/concurrency strategy rõ.
- [ ] Validation dựa vào dữ liệu hiện tại được đánh giá lại tại điểm ghi nếu cần.
- [ ] Database constraint bảo vệ các điều kiện có thể thực thi nguyên tử ở storage.
- [ ] Không dùng validation group để mô phỏng trạng thái domain.
- [ ] Validation được phân biệt với authorization.
- [ ] API trả field path và error code ổn định, không lộ chi tiết nội bộ.
- [ ] Có test cho DTO validation, Value Object, Aggregate và concurrency.

## 24. Bài tập tự kiểm tra

Một hệ thống đặt lịch khám có request:

~~~json
{
  "patientId": "P-100",
  "doctorId": "D-20",
  "startAt": "2026-12-01T09:00:00+07:00",
  "endAt": "2026-12-01T09:30:00+07:00",
  "reason": "Khám định kỳ"
}
~~~

Các quy tắc:

1. patientId và doctorId bắt buộc.
2. reason không được trống và tối đa 500 ký tự.
3. endAt phải sau startAt.
4. Thời điểm bắt đầu phải nằm trong giờ làm việc của phòng khám.
5. Bác sĩ không được có hai lịch hẹn chồng lấp.
6. Bệnh nhân không được đặt lịch nếu tài khoản đang bị khóa.
7. Hai request đồng thời không được cùng giữ một slot.

Hãy trả lời:

- Quy tắc nào đặt trên request DTO bằng Bean Validation?
- Quy tắc nào nên nằm trong Value Object như AppointmentPeriod?
- Quy tắc giờ làm việc thuộc Domain Service hay Aggregate nào?
- Quy tắc lịch bác sĩ không chồng lấp cần database/locking ra sao?
- Tài khoản bệnh nhân bị khóa là validation error hay business rejection?
- Nếu request đến từ message consumer, invariant nào vẫn phải được bảo vệ?
- Nếu API đã validate thành công nhưng slot bị request khác giữ trước khi commit, kết quả cần là gì?

Gợi ý:

| Quy tắc | Vị trí phù hợp |
|---|---|
| patientId/doctorId bắt buộc | DTO: @NotBlank |
| reason không trống, tối đa 500 | DTO: @NotBlank, @Size(max = 500); domain có thể dùng Value Object nếu là quy tắc nội tại |
| endAt sau startAt | DTO class-level constraint để báo sớm; AppointmentPeriod bảo vệ domain |
| Giờ làm việc | Domain policy/ClinicSchedule hoặc Domain Service vì phụ thuộc lịch nghiệp vụ |
| Bác sĩ không có lịch chồng lấp | Domain/use case kiểm tra; database exclusion constraint hoặc locking/atomic reservation bảo vệ cạnh tranh |
| Bệnh nhân bị khóa | Business rejection/eligibility policy, không phải format validation |
| Message consumer | Domain invariant vẫn chạy vì consumer phải gọi cùng use case/domain behavior |
| Slot bị giữ đồng thời | Concurrency conflict hoặc business rejection sau khi đánh giá lại trạng thái; không trả thành công giả |

## Kết luận

Bean Validation giúp kiểm tra dữ liệu theo contract tại boundary và phản hồi sớm cho caller. Nó phù hợp với field bắt buộc, format, kích thước, giới hạn số và một số quan hệ giữa field. Spring có thể kích hoạt cơ chế này bằng @Valid, @Validated và các custom constraint.

Domain invariant có phạm vi rộng hơn: nó phải luôn đúng dù hành vi được gọi từ REST, message consumer, batch job hay test. Hãy đặt quy tắc gắn với giá trị trong Value Object, quy tắc phụ thuộc state trong Aggregate Root, và quy tắc phối hợp nhiều đối tượng ở Domain Service/use case phù hợp. Với điều kiện dễ bị cạnh tranh, cần transaction, locking hoặc database constraint; kiểm tra trước khi ghi không đủ bảo vệ trạng thái đồng thời. Phân chia đúng trách nhiệm giúp API dễ sử dụng, domain luôn hợp lệ và hệ thống an toàn qua mọi đường thực thi.
