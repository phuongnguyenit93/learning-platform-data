# Tránh đưa mọi danh từ nghiệp vụ thành thực thể

Khi tìm hiểu một miền nghiệp vụ, đội phát triển thường bắt đầu bằng cách ghi lại các danh từ nghe được từ chuyên gia: Customer, Order, Product, Address, Payment, Discount, Shipment, Contract... Danh sách này rất hữu ích để khám phá domain, nhưng không phải danh từ nào cũng nên trở thành **Entity** trong mô hình.

Trong Domain-Driven Design (DDD), Entity là đối tượng được nhận diện bằng **danh tính xuyên suốt vòng đời**. Hai Entity có cùng các thuộc tính vẫn có thể là hai đối tượng khác nhau; một Entity vẫn là chính nó khi tên, địa chỉ hoặc trạng thái thay đổi. Ngược lại, Value Object được xác định bằng các giá trị cấu thành và thường được so sánh theo giá trị.

Nếu biến mọi danh từ thành Entity, mô hình sẽ có quá nhiều đối tượng mang định danh, quan hệ và vòng đời không cần thiết. Đội ngũ phải quản lý thêm trạng thái, repository, khóa ngoại và quy tắc cập nhật, trong khi ý nghĩa nghiệp vụ không được làm rõ hơn. Cách tốt hơn là xem danh từ như **ứng viên cần điều tra**, rồi quyết định nó thực sự là Entity, Value Object hay một khái niệm khác.

## 1. Danh từ chỉ là điểm bắt đầu để khám phá domain

Giả sử chuyên gia mô tả quy trình bán hàng bằng câu:

> Khách hàng chọn sản phẩm, nhập địa chỉ giao hàng, áp dụng mã giảm giá, đặt đơn và thanh toán.

Ta có thể gạch ra các danh từ: Customer, Product, Address, Coupon, Order và Payment. Nhưng câu này chưa cho biết bản chất mô hình của từng khái niệm.

- Customer có thể là Entity vì doanh nghiệp cần nhận diện cùng một khách hàng qua nhiều lần mua hàng và theo dõi vòng đời tài khoản.
- Product trong Product Catalog có thể là Entity vì có mã sản phẩm, trạng thái công bố và lịch sử thay đổi.
- Address thường có thể là Value Object vì ý nghĩa của nó nằm ở các thành phần địa chỉ; khi địa chỉ đổi, ta thay giá trị địa chỉ gắn với khách hàng.
- Coupon có thể là Entity nếu mỗi mã hoặc chiến dịch có vòng đời, trạng thái và quy tắc sử dụng riêng; một mã giảm giá đơn giản chỉ biểu diễn một giá trị cũng có thể là Value Object.
- Order thường là Entity vì có định danh và vòng đời từ lúc tạo đến khi hoàn tất hoặc hủy.
- Payment thường là Entity trong Payment Context vì một giao dịch có định danh, trạng thái và lịch sử xử lý riêng.

Cùng một danh từ có thể được mô hình hóa khác nhau trong những Bounded Context khác nhau. Vì vậy, không thể quyết định chỉ dựa trên từ ngữ hoặc tên gọi.

### 1.1. Entity không đồng nghĩa với danh từ có trong yêu cầu

Một yêu cầu có thể chứa các từ như “phê duyệt”, “giao hàng”, “giảm giá”, “báo cáo” hoặc “tìm kiếm”. Một số từ biểu đạt hành động, chính sách, vai trò hay kết quả đọc, không phải đối tượng có danh tính.

| Danh từ hoặc cụm từ | Cách hiểu có thể phù hợp | Vì sao chưa chắc là Entity |
|---|---|---|
| Address | Value Object | Giá trị địa chỉ thường được xác định bằng các thành phần của nó |
| Money | Value Object | Số tiền và loại tiền tệ xác định giá trị |
| OrderPlaced | Domain Event | Ghi nhận một sự việc đã xảy ra |
| PlaceOrder | Command / hành vi | Diễn đạt ý định thực hiện hành động |
| DiscountPolicy | Chính sách hoặc Domain Service | Diễn đạt quy tắc tính hoặc áp dụng giảm giá |
| SearchResult | Read Model / kết quả truy vấn | Là dữ liệu trình bày cho một nhu cầu đọc |
| Customer Support | Năng lực hoặc phạm vi nghiệp vụ | Là tên một hoạt động hoặc lĩnh vực |
| Delivery | Quy trình hoặc hành vi | Cần xác định đối tượng có vòng đời riêng hay chỉ là quá trình |
| Premium | Hạng hoặc phân loại | Có thể chỉ là một giá trị phân loại của khách hàng |
| OrderLine | Value Object hoặc Entity con | Phụ thuộc việc dòng hàng có danh tính và vòng đời riêng trong mô hình |

Bảng trên không phải quy tắc phân loại cố định. Nó nhắc rằng một từ trong hội thoại có thể đại diện cho nhiều loại khái niệm khác nhau. Cần hỏi chuyên gia về ý nghĩa và cách doanh nghiệp sử dụng nó.

## 2. Khi nào một khái niệm thực sự cần là Entity?

Một ứng viên Entity thường có một số đặc điểm sau:

- **Có danh tính riêng:** doanh nghiệp cần phân biệt nó với những đối tượng khác, kể cả khi các thuộc tính giống nhau.
- **Danh tính tồn tại theo thời gian:** đối tượng vẫn được nhận ra là cùng một đối tượng khi trạng thái hoặc thuộc tính thay đổi.
- **Có vòng đời nghiệp vụ:** nó được tạo, thay đổi, chuyển trạng thái, kết thúc hoặc lưu dấu lịch sử theo quy tắc.
- **Được tham chiếu trong nhiều tình huống:** các quy trình khác cần nói đến đúng đối tượng đó bằng định danh.
- **Có hành vi hoặc quyết định gắn với danh tính:** thay đổi của nó có ý nghĩa riêng trong domain.

Không nhất thiết một ứng viên phải có đủ mọi dấu hiệu. Điều quan trọng là danh tính của nó có ý nghĩa nghiệp vụ hay chỉ được tạo ra vì tiện lưu trữ.

### 2.1. Danh tính giúp phân biệt hai đối tượng có cùng giá trị

Giả sử có hai khách hàng cùng tên, cùng địa chỉ và cùng số điện thoại. Doanh nghiệp vẫn cần phân biệt họ vì mỗi người có tài khoản, lịch sử mua hàng và nghĩa vụ riêng.

Ví dụ Java:

```java
public record CustomerId(UUID value) {
    public CustomerId {
        Objects.requireNonNull(value);
    }
}

public class Customer {
    private final CustomerId id;
    private String fullName;
    private EmailAddress email;

    public Customer(
            CustomerId id,
            String fullName,
            EmailAddress email) {
        this.id = Objects.requireNonNull(id);
        this.fullName = Objects.requireNonNull(fullName);
        this.email = Objects.requireNonNull(email);
    }

    public void changeEmail(EmailAddress newEmail) {
        this.email = Objects.requireNonNull(newEmail);
    }

    public CustomerId id() {
        return id;
    }

    public String fullName() {
        return fullName;
    }

    public EmailAddress email() {
        return email;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Customer customer)) return false;
        return id.equals(customer.id);
    }

    @Override
    public int hashCode() {
        return id.hashCode();
    }
}
```

Hai Customer có cùng tên và email vẫn là hai Entity khác nhau nếu CustomerId khác nhau. Khi khách hàng đổi email, danh tính không thay đổi. Đó là điểm khác biệt cốt lõi giữa Entity và Value Object.

Trong mô hình thực tế, cách xác định danh tính cần theo quy tắc của Bounded Context. Một email có thể là thông tin liên hệ và thay đổi được; nó chỉ nên được dùng làm định danh nếu nghiệp vụ thực sự bảo đảm tính duy nhất và quy tắc thay đổi phù hợp.

### 2.2. Danh tính là khái niệm của domain, không chỉ là khóa cơ sở dữ liệu

Một hàng trong bảng có cột id không tự động trở thành Entity trong domain. Khóa chính có thể chỉ phục vụ lưu trữ hoặc kỹ thuật đồng bộ.

Ngược lại, Entity có thể có danh tính nghiệp vụ ngay cả khi chưa được lưu vào database. Ví dụ, một đối tượng đơn hàng đang được tạo trong bộ nhớ vẫn có thể có OrderId và vòng đời nghiệp vụ.

Hãy phân biệt:

- **Domain identity:** cách nghiệp vụ nhận diện một đối tượng.
- **Persistence identity:** khóa dùng để lưu và truy xuất bản ghi.
- **Technical identifier:** mã phục vụ tracing, correlation hoặc đồng bộ kỹ thuật.

Ba loại mã có thể trùng nhau trong một thiết kế đơn giản, nhưng không nên mặc định chúng luôn có cùng ý nghĩa.

### 2.3. Entity có thể thay đổi, nhưng không phải mọi dữ liệu thay đổi đều là Entity

Một Entity thường có trạng thái thay đổi theo vòng đời. Tuy nhiên, việc một giá trị thay đổi không đủ để kết luận nó là Entity.

Ví dụ, địa chỉ giao hàng của khách có thể thay đổi. Nếu địa chỉ chỉ là tập hợp các giá trị đường phố, quận, thành phố và mã bưu chính, nó vẫn có thể là Value Object. Khách hàng giữ danh tính của mình; địa chỉ cũ được thay bằng một giá trị địa chỉ mới.

Điều cần hỏi là: doanh nghiệp có cần nhận diện và quản lý chính địa chỉ đó như một đối tượng độc lập hay chỉ cần lưu giá trị hiện tại? Nếu doanh nghiệp quản lý từng địa chỉ giao hàng như một hồ sơ có định danh, trạng thái xác minh, thời gian hiệu lực và lịch sử sử dụng, Address có thể trở thành Entity trong một context phù hợp.

## 3. Phân biệt Entity với Value Object

Value Object là đối tượng được xác định bằng các giá trị cấu thành. Hai Value Object bằng nhau khi các giá trị của chúng bằng nhau theo quy tắc của domain. Chúng thường bất biến: khi cần thay đổi, tạo giá trị mới.

Ví dụ:

```java
public record Address(
    String street,
    String district,
    String city,
    String postalCode
) {
    public Address {
        Objects.requireNonNull(street);
        Objects.requireNonNull(city);
        Objects.requireNonNull(postalCode);
    }
}

public record Money(
    BigDecimal amount,
    Currency currency
) {
    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);

        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                "Amount cannot be negative"
            );
        }
    }
}
```

Hai Address có cùng các thành phần được xem là bằng nhau theo quy tắc của record. Hai Money chỉ có cùng giá trị nếu cả số tiền và loại tiền tệ đều bằng nhau. Trong domain tài chính thực tế, quy tắc số âm, làm tròn và độ chính xác cần được xác định theo nghiệp vụ; ví dụ chỉ minh họa cấu trúc Value Object.

| Tiêu chí | Entity | Value Object |
|---|---|---|
| Cách nhận diện | Danh tính | Giá trị cấu thành |
| So sánh bằng nhau | Theo định danh trong mô hình | Theo các giá trị |
| Vòng đời | Có danh tính xuyên suốt vòng đời | Thường không có vòng đời độc lập |
| Thay đổi | Có thể thay đổi trạng thái nhưng giữ danh tính | Thường thay bằng một giá trị mới |
| Ví dụ | Customer, Order, Payment | Money, Address, EmailAddress |

### 3.1. Câu hỏi kiểm tra nhanh

Khi phân vân giữa Entity và Value Object, hãy đặt các câu hỏi:

1. Nếu hai đối tượng có mọi thuộc tính giống nhau, domain có cần phân biệt chúng không?
2. Nếu một thuộc tính thay đổi, doanh nghiệp có xem đó vẫn là cùng một đối tượng không?
3. Có quy trình nào cần tham chiếu chính đối tượng đó về sau không?
4. Đối tượng có trạng thái, vòng đời hoặc lịch sử riêng cần quản lý không?
5. Nếu bỏ định danh, có làm mất một sự phân biệt quan trọng của nghiệp vụ không?

Nếu câu trả lời cho câu hỏi đầu là “không”, và các giá trị cấu thành đã đủ xác định ý nghĩa, Value Object thường là lựa chọn tự nhiên. Nếu danh tính có ý nghĩa xuyên suốt vòng đời, Entity đáng được xem xét.

Không dùng các câu hỏi này như một phép chấm điểm máy móc. Hãy xác nhận câu trả lời với chuyên gia nghiệp vụ và đặt khái niệm trong đúng Bounded Context.

## 4. Nhận diện những danh từ thuộc loại khái niệm khác

Một danh từ có thể cần được mô hình hóa, nhưng không nhất thiết là Entity hoặc Value Object. Dưới đây là những trường hợp thường gặp.

### 4.1. Hành động và Command

Các từ như “đặt hàng”, “hủy đơn”, “phê duyệt” hoặc “giữ hàng” diễn đạt hành động. Trong mô hình, chúng có thể trở thành phương thức trên Entity/Aggregate hoặc Command gửi đến use case.

Ví dụ:

- PlaceOrder là ý định yêu cầu đặt đơn.
- Order.place() là hành vi trên Aggregate.
- OrderPlaced là sự kiện xác nhận đơn đã được đặt.

Không cần tạo Entity OrderPlacement chỉ vì tài liệu có danh từ “việc đặt hàng”. Chỉ tạo một đối tượng có danh tính nếu quy trình đặt hàng thực sự cần được quản lý như một hồ sơ riêng, có trạng thái và vòng đời riêng.

### 4.2. Domain Event

Các từ như PaymentAuthorized, OrderCancelled hay ShipmentDispatched ghi nhận sự việc đã xảy ra. Chúng là Domain Event, không phải Entity chỉ vì được lưu vào bảng hoặc message broker.

Một số hệ thống có thể lưu lịch sử sự kiện với định danh kỹ thuật hoặc metadata. Điều đó không làm thay đổi vai trò khái niệm của event trong mô hình. Event mô tả sự việc tại một thời điểm; Entity mô tả đối tượng có danh tính xuyên suốt vòng đời.

### 4.3. Chính sách và quy tắc

Các khái niệm như Discount Policy, Pricing Rule, Eligibility Rule hoặc Credit Policy thường biểu đạt chính sách quyết định hành vi. Tùy domain, chúng có thể là:

- Một Value Object chứa tham số chính sách.
- Một Domain Service thực hiện phép tính hoặc quyết định.
- Một Entity nếu chính sách có mã, phiên bản, trạng thái hiệu lực, người phê duyệt và lịch sử thay đổi riêng.

Ví dụ, quy tắc “đơn từ 500.000 đồng được miễn phí giao hàng” có thể được biểu diễn bằng một policy object. Nếu doanh nghiệp quản lý nhiều chương trình khuyến mãi, mỗi chương trình có thời hạn, trạng thái phát hành và quy tắc thay đổi, Promotion Campaign có thể là Entity. Cần phân biệt **quy tắc tính toán** với **hồ sơ chương trình được quản lý**.

### 4.4. Vai trò và tư cách

Các từ như Buyer, Recipient, Approver hoặc Account Owner có thể là vai trò mà một người đảm nhiệm trong một mối quan hệ, thay vì những Entity riêng.

Ví dụ, một Customer có thể vừa là người mua vừa là người nhận hàng. Nếu hai vai trò chỉ là hai vị trí trong một giao dịch, có thể biểu diễn bằng buyerId và recipientAddress hoặc một Value Object chứa thông tin vai trò. Nếu người nhận là một cá nhân độc lập có hồ sơ và vòng đời riêng trong context, người nhận có thể là Entity.

Đừng tạo Entity Buyer chỉ vì nghiệp vụ có cụm từ “người mua”. Hãy hỏi vai trò này có danh tính và trách nhiệm riêng hay chỉ mô tả cách một người tham gia vào một giao dịch.

### 4.5. Kết quả truy vấn và Read Model

Các danh từ như Order Summary, Customer Dashboard, Search Result hoặc Sales Report thường là mô hình đọc được tạo ra để phục vụ truy vấn và hiển thị.

Read Model có thể tổng hợp dữ liệu từ nhiều Entity hoặc context. Nó không nhất thiết có danh tính hay vòng đời domain. Ví dụ, OrderSummary trên màn hình có thể chứa mã đơn, tên khách, tổng tiền và trạng thái giao hàng; đây là dữ liệu trình bày tại thời điểm truy vấn.

Nếu một báo cáo được lưu và quản lý như một hồ sơ nghiệp vụ có người sở hữu, trạng thái duyệt và lịch sử phát hành, mô hình của nó có thể khác. Hãy phân biệt kết quả đọc tạm thời với đối tượng được doanh nghiệp quản lý.

### 4.6. Danh mục, loại và thuộc tính

Các từ như Category, Type, Status, Priority hoặc Segment có thể là enum, Value Object, Entity hoặc chỉ là thuộc tính tùy mức độ quản lý.

- OrderStatus thường là enum hoặc kiểu giá trị.
- Priority có thể là một mức cố định trong quy trình.
- ProductCategory có thể là một giá trị phân loại đơn giản.
- ProductCategory cũng có thể là Entity nếu doanh nghiệp quản lý cây danh mục, mã định danh, trạng thái, quan hệ cha-con và lịch sử thay đổi.

Tên gọi không quyết định loại mô hình. Mức độ độc lập của vòng đời và các quy tắc quản lý mới là căn cứ.

### 4.7. Năng lực, quy trình và Bounded Context

Các từ như Sales, Billing, Customer Support, Fulfillment hoặc Returns có thể chỉ năng lực, quy trình hay Bounded Context. Chúng giúp chia miền nghiệp vụ và xác định phạm vi trách nhiệm, không nhất thiết là đối tượng trong mô hình domain.

Một quy trình Order Fulfillment có thể điều phối nhiều Entity như Order, Reservation và Shipment. Không cần tạo Entity Fulfillment trừ khi doanh nghiệp thực sự quản lý một hồ sơ fulfillment có danh tính, trạng thái và vòng đời riêng.

## 5. Cùng một danh từ có thể là Entity ở context này và Value Object ở context khác

DDD nhấn mạnh Bounded Context vì ý nghĩa của một khái niệm phụ thuộc vào mô hình đang sử dụng nó.

Xét Product:

| Bounded Context | Cách mô hình hóa có thể phù hợp | Lý do |
|---|---|---|
| Product Catalog | Entity Product | Có mã sản phẩm, nội dung công bố, trạng thái và vòng đời danh mục |
| Ordering | ProductReference hoặc OrderLine snapshot | Đơn cần ghi nhận sản phẩm và giá tại thời điểm đặt |
| Inventory | StockItem / SKU Entity | Quản lý số lượng, vị trí kho và reservation |
| Analytics | ProductDimension hoặc dữ liệu phân tích | Phục vụ tổng hợp và báo cáo |

Ordering không nhất thiết cần toàn bộ Entity Product của Catalog. Nó có thể lưu ProductId, tên và giá tại thời điểm giao dịch. Inventory có thể dùng SKU làm danh tính của mặt hàng trong kho. Analytics có thể biểu diễn sản phẩm dưới dạng một chiều dữ liệu.

Tương tự, Customer trong Sales có thể là Entity phục vụ quan hệ mua hàng. Trong Billing, hệ thống có thể cần BillingAccount hoặc BillToParty với định danh và quy tắc riêng. Trong một báo cáo, thông tin khách hàng có thể chỉ là snapshot đọc.

Điều này không có nghĩa một context được tùy ý phân loại. Mỗi mô hình phải có lý do rõ ràng dựa trên ngôn ngữ, quy tắc, dữ liệu và trách nhiệm của context đó.

## 6. Trường hợp dễ nhầm: OrderLine là Entity hay Value Object?

OrderLine là ví dụ tốt để thấy rằng một khái niệm không có loại cố định trong mọi hệ thống.

### 6.1. Khi OrderLine là Value Object

Nếu dòng hàng chỉ biểu diễn sản phẩm, số lượng và đơn giá tại thời điểm đặt, không có vòng đời hoặc danh tính riêng, nó có thể là Value Object:

```java
public record OrderLine(
    ProductId productId,
    int quantity,
    Money unitPrice
) {
    public OrderLine {
        Objects.requireNonNull(productId);
        Objects.requireNonNull(unitPrice);

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }
    }

    public Money subtotal() {
        return unitPrice.multiply(quantity);
    }
}
```

Hai dòng hàng có cùng ProductId, quantity và unitPrice có thể bằng nhau theo giá trị. Khi thay đổi số lượng, tạo một OrderLine mới và thay giá trị cũ bên trong Order.

### 6.2. Khi OrderLine là Entity con

Trong một domain khác, từng dòng hàng có thể có định danh vì người dùng hoặc nhân viên cần tham chiếu chính xác một dòng để chỉnh sửa, phê duyệt, áp dụng trạng thái riêng hoặc theo dõi lịch sử.

Ví dụ, một đơn hàng B2B có thể chứa các dòng được duyệt độc lập, có mã dòng ổn định và thông tin phân bổ ngân sách. Khi đó, OrderLine có thể là Entity con bên trong Aggregate Order.

Dù là Entity con, OrderLine không tự động trở thành Aggregate Root. Bên ngoài vẫn có thể phải thay đổi nó thông qua Order để Aggregate bảo vệ invariant của toàn đơn.

### 6.3. Cách quyết định

Hãy hỏi:

- Có cần phân biệt hai dòng hàng có cùng sản phẩm và giá trị không?
- Có quy trình tham chiếu một dòng cụ thể sau khi đơn được tạo không?
- Dòng hàng có trạng thái hoặc lịch sử riêng không?
- Có quy tắc nào yêu cầu nhận diện dòng hàng xuyên suốt quá trình xử lý không?
- Việc thay đổi dòng hàng có luôn được quản lý như một phần của Order không?

Nếu dòng hàng chỉ là một giá trị cấu thành đơn hàng, Value Object thường đơn giản hơn. Nếu dòng hàng có danh tính và vòng đời riêng, Entity con có thể phù hợp. Quyết định cần dựa vào hành vi nghiệp vụ chứ không phải vì database có bảng order_line với cột id.

## 7. Quy trình phân loại danh từ thành mô hình phù hợp

Có thể dùng quy trình sau khi chuyển ghi chú khám phá nghiệp vụ thành mô hình.

### Bước 1: Ghi lại thuật ngữ trong ngữ cảnh sử dụng

Không chỉ ghi một danh từ đơn lẻ. Ghi câu hoặc tình huống mà chuyên gia đã dùng nó.

Ví dụ: “Nhân viên có thể thay đổi địa chỉ giao hàng trước khi đơn được đóng gói.” Câu này cho biết Address gắn với Order, có điều kiện thay đổi và có thể là một giá trị trong vòng đời đơn.

### Bước 2: Làm rõ ý nghĩa và trách nhiệm

Hỏi khái niệm đại diện cho điều gì, ai quản lý nó và quyết định nào liên quan đến nó. Phân biệt đối tượng nghiệp vụ với vai trò, hành động, quy tắc và kết quả đọc.

### Bước 3: Kiểm tra danh tính và vòng đời

Hỏi liệu doanh nghiệp có cần nhận diện chính đối tượng đó qua nhiều lần thay đổi hay không. Nếu không có danh tính riêng nhưng có ý nghĩa bằng các giá trị, hãy xem xét Value Object.

### Bước 4: Kiểm tra hành vi và invariant

Tìm các quy tắc cần được bảo vệ. Nếu khái niệm có hành vi gắn với danh tính và trạng thái, nó có thể là Entity. Nếu nó chỉ kiểm tra tính hợp lệ của một tập giá trị, Value Object có thể phù hợp hơn.

### Bước 5: Kiểm tra phạm vi Bounded Context

Đặt khái niệm trong context cụ thể. Cùng một từ có thể có ý nghĩa khác nhau ở nơi khác. Không ép các context dùng chung một lớp chỉ để tránh trùng tên.

### Bước 6: Chọn mô hình đơn giản nhất vẫn giữ được ý nghĩa nghiệp vụ

Có thể lựa chọn:

- Entity nếu danh tính và vòng đời có ý nghĩa.
- Value Object nếu giá trị cấu thành xác định ý nghĩa.
- Command hoặc phương thức nếu đó là hành động.
- Domain Event nếu đó là sự việc đã xảy ra.
- Domain Service hoặc Policy nếu đó là quy tắc hoặc hành vi không thuộc tự nhiên về một Entity.
- Read Model nếu đó là dữ liệu phục vụ truy vấn.
- Enum hoặc thuộc tính nếu đó chỉ là phân loại đơn giản.
- Bounded Context hoặc Subdomain nếu đó là phạm vi nghiệp vụ.

### Bước 7: Kiểm chứng bằng ví dụ và kịch bản

Đưa ra hai đối tượng có cùng giá trị, một đối tượng thay đổi thuộc tính, một đối tượng kết thúc vòng đời hoặc một quy trình cần tham chiếu lại đối tượng. Hỏi chuyên gia liệu các trường hợp đó có phải là cùng một đối tượng hay không.

Nếu câu trả lời chưa rõ, giữ phân loại ở dạng giả thuyết và tiếp tục khám phá. Không cần cố tạo Entity ngay để hoàn thiện sơ đồ lớp.

## 8. Ví dụ phân tích một danh sách danh từ trong hệ thống bán hàng

Giả sử đội phát triển nhận được danh sách: Customer, Product, Address, Order, OrderLine, Payment, Discount, Shipment, Delivery, Invoice, Report.

Có thể lập bảng phân tích ban đầu như sau:

| Khái niệm | Phân loại giả thuyết | Câu hỏi cần xác nhận |
|---|---|---|
| Customer | Entity trong Sales | Doanh nghiệp cần nhận diện khách xuyên suốt các giao dịch nào? |
| Product | Entity trong Product Catalog | Sản phẩm có mã và vòng đời công bố riêng không? |
| Address | Value Object trong Order | Địa chỉ có được quản lý như hồ sơ độc lập hay chỉ là giá trị giao nhận? |
| Order | Entity và thường là Aggregate Root | Đơn có vòng đời và invariant nào cần bảo vệ? |
| OrderLine | Value Object hoặc Entity con | Có cần danh tính và trạng thái riêng cho từng dòng không? |
| Payment | Entity trong Payment Context | Mỗi giao dịch có định danh, trạng thái và lịch sử riêng không? |
| Discount | Policy, Value Object hoặc Entity Campaign | Đây là phép tính, tham số hay chương trình có vòng đời? |
| Shipment | Entity trong Shipping Context | Lô hàng có mã vận đơn và vòng đời riêng không? |
| Delivery | Hành vi, quy trình hoặc Entity | Doanh nghiệp quản lý từng lần giao như một hồ sơ riêng không? |
| Invoice | Entity trong Billing Context | Hóa đơn có số, trạng thái phát hành và quy tắc pháp lý riêng không? |
| Report | Read Model hoặc tài liệu nghiệp vụ | Báo cáo chỉ là kết quả truy vấn hay là hồ sơ được phát hành và quản lý? |

Đây là bảng giả thuyết, không phải mô hình cuối cùng. Một doanh nghiệp có thể quản lý Delivery Attempt như Entity vì mỗi lần giao có thời gian, nhân viên giao, kết quả và lý do thất bại. Trong doanh nghiệp khác, thông tin giao hàng có thể chỉ là một phần trạng thái của Shipment.

Tương tự, Discount có thể là một Value Object chứa tỷ lệ và điều kiện tính. Nhưng Promotion Campaign có thể là Entity vì có mã chiến dịch, thời gian hiệu lực, trạng thái phê duyệt, ngân sách và lịch sử thay đổi. Không nên gộp hai khái niệm chỉ vì chúng cùng liên quan đến giảm giá.

## 9. Những sai lầm thường gặp khi mô hình hóa Entity

**Biến mọi danh từ thành Entity.** Danh sách lớp phình to, nhiều đối tượng không có vòng đời hoặc trách nhiệm rõ. Hãy xem danh từ là ứng viên và kiểm tra danh tính trước.

**Coi mọi bảng database là Entity.** Cấu trúc lưu trữ phục vụ persistence, không quyết định bản chất domain. Một bảng có thể lưu Value Object hoặc projection; một Entity có thể được ánh xạ qua nhiều bảng.

**Dùng ID chỉ để làm cho một lớp trông giống Entity.** Một trường UUID không tạo ra ý nghĩa danh tính. Cần biết ai sử dụng ID, để phân biệt điều gì và trong bao lâu.

**So sánh Entity bằng tất cả thuộc tính.** Nếu dùng equals() theo mọi trường, khi tên hoặc email thay đổi, đối tượng có thể bị coi là một đối tượng khác. Entity cần so sánh theo identity theo quy tắc của mô hình.

**Đặt mọi Value Object thành Entity vì cần cập nhật.** Một Address có thể thay đổi mà không cần danh tính riêng. Hãy phân biệt thay thế một giá trị với thay đổi vòng đời của một đối tượng độc lập.

**Tạo Entity cho hành động hoặc sự kiện.** PlaceOrder là hành vi/lệnh, OrderPlaced là sự kiện. Chỉ tạo đối tượng có danh tính nếu nghiệp vụ thực sự quản lý một hồ sơ riêng cho hành động hoặc quy trình đó.

**Tách Entity con thành Aggregate Root quá sớm.** Một Entity có thể sống bên trong Aggregate và được truy cập thông qua Root. Không cần repository cho mọi Entity con.

**Dùng chung một Entity giữa các Bounded Context.** Cùng tên không đảm bảo cùng ý nghĩa. Hãy trao đổi bằng định danh và hợp đồng phù hợp, giữ mô hình nội bộ riêng khi trách nhiệm khác nhau.

**Phân loại theo framework ORM.** Annotation @Entity là khái niệm persistence của JPA. Nó không thay thế quyết định Entity trong domain. Hai loại entity có thể trùng nhau trong một thiết kế, nhưng không phải lúc nào cũng cần.

## 10. Checklist trước khi tạo một Entity

Trước khi thêm một lớp Entity vào mô hình, hãy kiểm tra:

- Khái niệm này có ý nghĩa nghiệp vụ rõ trong Bounded Context hiện tại không?
- Doanh nghiệp có cần phân biệt nó với một đối tượng khác có cùng thuộc tính không?
- Danh tính có ổn định khi các thuộc tính thay đổi không?
- Có vòng đời hoặc trạng thái nghiệp vụ cần quản lý không?
- Có hành vi hoặc invariant gắn với chính đối tượng này không?
- Các quy trình có cần tham chiếu lại chính đối tượng đó không?
- Nếu mô hình nó thành Value Object, có làm mất thông tin danh tính quan trọng không?
- Nó có thực ra là hành động, sự kiện, chính sách, vai trò hoặc Read Model không?
- Nó là Aggregate Root hay chỉ là Entity con bên trong Aggregate khác?
- Quyết định này đã được xác nhận bằng ví dụ với chuyên gia nghiệp vụ chưa?

Nếu chưa thể trả lời những câu hỏi quan trọng về danh tính và vòng đời, hãy tiếp tục khám phá trước khi tạo Entity.

## 11. Kết luận

Danh từ nghiệp vụ giúp đội ngũ tìm ra những khái niệm cần hiểu, nhưng không quyết định loại đối tượng trong mô hình. Entity chỉ phù hợp khi danh tính có ý nghĩa xuyên suốt vòng đời và cần được phân biệt độc lập. Nếu ý nghĩa được xác định bằng các giá trị, Value Object thường đơn giản và chính xác hơn. Những danh từ khác có thể biểu diễn hành động, sự kiện, chính sách, vai trò, dữ liệu đọc hoặc phạm vi nghiệp vụ.

Hãy bắt đầu từ câu chuyện và quy trình thật, hỏi doanh nghiệp cần nhận diện điều gì, điều gì chỉ là một giá trị và điều gì là hành vi. Sau đó kiểm chứng phân loại bằng trường hợp có cùng thuộc tính, thay đổi trạng thái và tham chiếu qua thời gian. Mô hình tốt không phải mô hình có nhiều Entity nhất; đó là mô hình giữ được những phân biệt mà nghiệp vụ thực sự cần.

