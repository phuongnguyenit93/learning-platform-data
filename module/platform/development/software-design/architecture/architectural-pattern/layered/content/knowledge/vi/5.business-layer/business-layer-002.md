# Nhận diện thực thể, đối tượng giá trị và quy tắc bất biến cần bảo vệ

Tầng nghiệp vụ mô tả những khái niệm và quy tắc quyết định ứng dụng được phép làm gì. Khi xây dựng tầng này, ta cần nhận ra đối tượng nào có danh tính riêng, đối tượng nào chỉ được xác định bằng giá trị, và những điều kiện nào luôn phải đúng trong suốt vòng đời của chúng. Nếu không phân biệt được ba khái niệm này, mô hình nghiệp vụ dễ biến thành tập hợp các lớp dữ liệu có getter/setter, còn quy tắc quan trọng bị rải rác trong controller, service hoặc câu lệnh cập nhật cơ sở dữ liệu.

Trong module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED` — học tổ chức phần mềm theo kiến trúc phân tầng — bài học này tập trung vào cách nhận diện và bảo vệ các khái niệm cốt lõi ở tầng nghiệp vụ. Entity, value object và invariant là những khái niệm thường dùng trong thiết kế hướng miền (Domain-Driven Design, DDD), nhưng có thể áp dụng có chọn lọc. Không phải ứng dụng nào cũng cần một mô hình miền phức tạp hoặc phải dùng DDD đầy đủ.

## 1. Bắt đầu từ quy tắc và hành vi nghiệp vụ

Khi đọc yêu cầu, đừng vội biến mọi danh từ thành một lớp Java. Một câu như “khách hàng tạo đơn hàng gồm các sản phẩm và thanh toán bằng một loại tiền tệ” có nhiều danh từ, nhưng không phải danh từ nào cũng tương ứng với một entity.

Hãy tìm hiểu:

- Người dùng hoặc hệ thống muốn thực hiện hành động gì: tạo đơn, thêm mặt hàng, đặt đơn, hủy đơn hay hoàn tiền?
- Đối tượng nào cần được nhận diện xuyên suốt nhiều lần đọc và cập nhật?
- Giá trị nào chỉ mô tả một đặc tính tại một thời điểm, không có vòng đời độc lập?
- Điều kiện nào phải đúng trước và sau mỗi hành động?
- Quy tắc nào chỉ phụ thuộc dữ liệu trong một đối tượng, và quy tắc nào cần thông tin từ nhiều đối tượng hoặc hệ thống khác?

Ví dụ, “đơn hàng không thể được đặt nếu chưa có dòng hàng” là một quy tắc có thể phát hiện từ hành động đặt đơn. “Số lượng trong một dòng hàng phải lớn hơn 0” là điều kiện của dữ liệu dòng hàng. “Khách hàng phải có mã định danh ổn định” gợi ý rằng khách hàng có danh tính riêng. Những phát hiện này giúp chọn mô hình phù hợp thay vì chỉ dựa trên cấu trúc bảng dữ liệu.

## 2. Thực thể: đối tượng có danh tính xuyên suốt vòng đời

**Thực thể (entity)** là đối tượng được phân biệt bằng danh tính của nó. Thuộc tính của entity có thể thay đổi nhưng entity vẫn là cùng một đối tượng nghiệp vụ.

Ví dụ:

- Một khách hàng vẫn là khách hàng đó khi đổi tên, email hoặc địa chỉ liên hệ.
- Một đơn hàng vẫn là đơn hàng đó khi được thêm dòng hàng, thay đổi trạng thái hoặc cập nhật địa chỉ giao.
- Một tài khoản vẫn là tài khoản đó khi số dư thay đổi sau giao dịch.

Vì vậy, khi so sánh hai entity, câu hỏi chính thường là “chúng có cùng danh tính không?”, không phải “mọi thuộc tính hiện tại có giống nhau không?”. Nếu hai lần đọc trả về hai đối tượng Java khác nhau nhưng cùng đại diện cho đơn hàng có mã `ORD-100`, chúng có thể là hai biểu diễn của cùng một entity.

```java
public final class Customer {
    private final UUID id;
    private String displayName;
    private String email;

    public Customer(UUID id, String displayName, String email) {
        this.id = Objects.requireNonNull(id);
        changeContact(displayName, email);
    }

    public void changeContact(String displayName, String email) {
        if (displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException("Tên khách hàng là bắt buộc");
        }
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email là bắt buộc");
        }
        this.displayName = displayName.trim();
        this.email = email.trim();
    }

    public UUID id() { return id; }
    public String displayName() { return displayName; }
    public String email() { return email; }

    @Override
    public boolean equals(Object other) {
        return this == other
            || other instanceof Customer customer && id.equals(customer.id);
    }

    @Override
    public int hashCode() {
        return id.hashCode();
    }
}
```

Ví dụ này dùng UUID được cấp khi tạo khách hàng và giữ nguyên trong suốt vòng đời. `equals` và `hashCode` dựa trên ID, nên đổi tên hoặc email không làm thay đổi danh tính. Trong hệ thống thực tế, cách cấp ID và xử lý entity chưa được lưu cần được xác định rõ; tránh dùng các trường có thể thay đổi làm khóa so sánh.

Không phải mọi lớp có trường `id` đều tự động là entity theo nghĩa nghiệp vụ. Một DTO có thể có ID để phục vụ giao tiếp, còn một đối tượng chỉ dùng để gom tham số có thể không có danh tính riêng. Cần xem xét ý nghĩa của ID: nó định danh một khái niệm có vòng đời hay chỉ là khóa kỹ thuật.

### Entity nghiệp vụ và JPA entity

Trong Java, từ “entity” còn xuất hiện trong `@Entity` của Jakarta Persistence. Annotation đó nói rằng lớp được ánh xạ với cơ chế lưu trữ ORM. Nó không tự chứng minh lớp đã mô hình hóa đúng danh tính, hành vi và quy tắc nghiệp vụ.

Một lớp JPA có thể là entity nghiệp vụ, nhưng cũng có thể chỉ là cấu trúc lưu trữ. Ngược lại, mô hình nghiệp vụ có thể không dùng annotation JPA và được ánh xạ bởi repository hoặc adapter ở tầng hạ tầng. Hãy phân biệt khái niệm nghiệp vụ với lựa chọn lưu trữ.

## 3. Đối tượng giá trị: được xác định bằng giá trị

**Đối tượng giá trị (value object)** là đối tượng không có danh tính độc lập trong mô hình. Hai value object được xem là tương đương khi các giá trị cấu thành của chúng bằng nhau theo quy tắc của kiểu đó.

Ví dụ thường gặp:

- `Money`: số tiền và loại tiền tệ.
- `Address`: đường, thành phố, mã bưu chính và quốc gia.
- `DateRange`: ngày bắt đầu và ngày kết thúc.
- `Quantity`: số lượng và đơn vị đo.

Nếu một đơn hàng đổi địa chỉ giao từ A sang B, ta thường không cần giữ lại “danh tính” của đối tượng địa chỉ cũ để nói rằng đó vẫn là cùng một địa chỉ. Có thể thay value object cũ bằng value object mới. Một địa chỉ có thể được lưu trong cơ sở dữ liệu, nhưng việc được lưu không tự biến nó thành entity; tiêu chí vẫn là danh tính và vòng đời trong nghiệp vụ.

Value object thường nên bất biến (*immutable*): sau khi tạo, không sửa một phần giá trị bên trong. Muốn có giá trị khác, tạo đối tượng mới. Bất biến giúp việc so sánh, chia sẻ giữa các đối tượng và kiểm thử trở nên dễ dự đoán.

Ví dụ `Money`:

```java
public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");

        int fractionDigits = currency.getDefaultFractionDigits();
        if (fractionDigits < 0) {
            throw new IllegalArgumentException("Loại tiền không hỗ trợ số lẻ chuẩn");
        }

        // Chuẩn hóa scale theo số chữ số thập phân mặc định của loại tiền.
        amount = amount.setScale(fractionDigits, RoundingMode.UNNECESSARY);
    }

    public Money add(Money other) {
        Objects.requireNonNull(other, "other");
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("Không thể cộng hai loại tiền khác nhau");
        }
        return new Money(amount.add(other.amount), currency);
    }

    public Money multiply(int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException("Số lượng không được âm");
        }
        return new Money(amount.multiply(BigDecimal.valueOf(quantity)), currency);
    }
}
```

Vì `Money` là record, Java sinh `equals` và `hashCode` theo các thành phần; constructor chuẩn hóa scale để những giá trị tiền có cùng độ chính xác tiền tệ được biểu diễn nhất quán. `RoundingMode.UNNECESSARY` khiến việc tạo giá trị có quá nhiều chữ số thập phân bị từ chối thay vì âm thầm làm tròn. Chính sách làm tròn thực tế có thể phụ thuộc nghiệp vụ, loại tiền và quy định kế toán; ví dụ này chọn từ chối để thể hiện rõ hợp đồng.

Không nên áp đặt một quy tắc như “tiền không bao giờ âm” cho mọi `Money`: số âm có thể hợp lệ trong hoàn tiền hoặc bút toán điều chỉnh. Nếu một trường hợp sử dụng chỉ chấp nhận số tiền dương, hãy đặt điều kiện đó ở kiểu hoặc hành động nghiệp vụ phù hợp, chẳng hạn `PaymentAmount` hoặc thao tác thu tiền.

### So sánh entity và value object

| Tiêu chí | Entity | Value object |
|---|---|---|
| Cách nhận diện | Danh tính ổn định | Tập giá trị cấu thành |
| So sánh | Thường dựa trên ID | Dựa trên giá trị |
| Thay đổi | Có thể thay đổi mà vẫn là cùng đối tượng | Thường thay bằng instance mới |
| Vòng đời | Có ý nghĩa độc lập trong nghiệp vụ | Thường phụ thuộc vào entity hoặc hành động chứa nó |
| Ví dụ | Khách hàng, đơn hàng, tài khoản | Money, địa chỉ giao, khoảng ngày |

Đây là tiêu chí định hướng, không phải danh sách cố định. Một địa chỉ có thể là value object trong hệ thống bán hàng nhưng có thể được quản lý như entity trong hệ thống bưu chính nếu mỗi địa chỉ có danh tính, lịch sử và quy trình riêng. Vai trò phụ thuộc vào ngữ cảnh nghiệp vụ.

## 4. Quy tắc bất biến là gì?

**Bất biến (invariant)** là điều kiện phải luôn đúng đối với một đối tượng hoặc phạm vi nghiệp vụ trong những trạng thái mà mô hình cho phép. Một hành động hợp lệ phải giữ cho bất biến tiếp tục đúng sau khi hành động kết thúc.

Ví dụ:

- Số lượng của một dòng hàng phải lớn hơn 0.
- Giá đơn vị không được âm nếu chính sách bán hàng không cho phép giá âm.
- Các dòng trong cùng đơn hàng phải dùng cùng loại tiền.
- Đơn hàng chỉ được đặt khi có ít nhất một dòng hàng.
- Đơn hàng đã đặt không thể tiếp tục thêm hoặc xóa dòng hàng theo quy trình thông thường.
- Ngày kết thúc của một khoảng thời gian không được trước ngày bắt đầu.

Phân biệt bất biến với quy tắc chỉ áp dụng tại một thời điểm. “Khách hàng được giảm giá 10% trong chiến dịch tháng này” có thể là chính sách phụ thuộc thời gian và cấu hình chiến dịch. “Tổng tiền của đơn bằng tổng thành tiền các dòng theo quy tắc tính giá đã chọn” là điều kiện cần được giữ nhất quán trong cách tính và cập nhật đơn. Một điều kiện có thể là bất biến trong một ngữ cảnh nhưng chỉ là chính sách có thể thay đổi trong ngữ cảnh khác.

### Các phạm vi bất biến

1. **Bất biến của một giá trị:** số tiền phải có loại tiền, số lượng phải dương, khoảng ngày phải có thứ tự hợp lệ. Thường được bảo vệ ngay trong constructor hoặc factory của value object.
2. **Bất biến của entity:** một entity không được chuyển sang trạng thái không hợp lệ, ví dụ đơn đã hủy không thể được đặt lại theo quy trình thông thường.
3. **Bất biến của một nhóm đối tượng:** các dòng hàng trong một đơn phải cùng loại tiền, không trùng sản phẩm nếu chính sách yêu cầu, và chỉ được sửa khi đơn còn ở trạng thái nháp. Nhóm đối tượng này thường được bảo vệ qua một đối tượng gốc có quyền điều khiển các thay đổi.
4. **Điều kiện liên quan nhiều entity hoặc hệ thống:** tồn kho phải đủ, hạn mức tín dụng còn khả dụng, mã khuyến mại vẫn hiệu lực. Những điều kiện này cần phối hợp truy vấn, giao dịch hoặc chính sách bên ngoài; một entity đơn lẻ không thể tự xác nhận chúng chỉ từ dữ liệu đang giữ trong bộ nhớ.

## 5. Đặt bất biến gần nơi sở hữu dữ liệu và hành vi

Nếu mọi thuộc tính đều public hoặc có setter tùy ý, bất kỳ caller nào cũng có thể tạo trạng thái sai. Thay vào đó, hãy giới hạn cách thay đổi trạng thái và cung cấp hành vi có tên theo nghiệp vụ.

Ví dụ sau mô hình hóa `Order` là entity và `OrderLine` là value object. Trong ví dụ, một đơn chỉ có tối đa một dòng cho mỗi sản phẩm; nếu nghiệp vụ cho phép nhiều dòng cùng sản phẩm thì cần thay đổi quy tắc này.

```java
public record ProductId(UUID value) {
    public ProductId {
        Objects.requireNonNull(value, "value");
    }
}

public record OrderLine(ProductId productId, int quantity, Money unitPrice) {
    public OrderLine {
        Objects.requireNonNull(productId, "productId");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải lớn hơn 0");
        }
        if (unitPrice.amount().signum() < 0) {
            throw new IllegalArgumentException("Giá đơn vị không được âm");
        }
    }

    public Money subtotal() {
        return unitPrice.multiply(quantity);
    }
}
```

`OrderLine` được xem là value object vì nó không có ID độc lập trong ví dụ này; nó được nhận diện bằng sản phẩm, số lượng và giá đơn vị trong ngữ cảnh của đơn hàng. Nếu dòng hàng có quy trình riêng, được tham chiếu độc lập hoặc có lịch sử riêng cần theo dõi, nhóm có thể quyết định mô hình nó thành entity. Không có một câu trả lời đúng cho mọi hệ thống.

Entity `Order` kiểm soát trạng thái và tập hợp các dòng:

```java
public enum OrderStatus {
    DRAFT, PLACED, CANCELLED
}

public final class Order {
    private final UUID id;
    private OrderStatus status;
    private final List<OrderLine> lines = new ArrayList<>();

    public Order(UUID id) {
        this.id = Objects.requireNonNull(id, "id");
        this.status = OrderStatus.DRAFT;
    }

    public void addLine(OrderLine line) {
        ensureDraft();
        Objects.requireNonNull(line, "line");

        if (!lines.isEmpty()) {
            Currency orderCurrency = lines.get(0).unitPrice().currency();
            if (!orderCurrency.equals(line.unitPrice().currency())) {
                throw new IllegalStateException("Các dòng hàng phải cùng loại tiền");
            }
        }

        boolean productAlreadyPresent = lines.stream()
            .anyMatch(existing -> existing.productId().equals(line.productId()));
        if (productAlreadyPresent) {
            throw new IllegalStateException("Sản phẩm đã có trong đơn hàng");
        }

        lines.add(line);
    }

    public void place() {
        ensureDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException("Không thể đặt đơn hàng trống");
        }
        status = OrderStatus.PLACED;
    }

    public UUID id() { return id; }
    public OrderStatus status() { return status; }
    public List<OrderLine> lines() { return List.copyOf(lines); }

    private void ensureDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Chỉ có thể sửa đơn hàng ở trạng thái nháp");
        }
    }

    @Override
    public boolean equals(Object other) {
        return this == other
            || other instanceof Order order && id.equals(order.id);
    }

    @Override
    public int hashCode() {
        return id.hashCode();
    }
}
```

Các bất biến được bảo vệ qua những điểm vào có chủ đích:

- `OrderLine` từ chối số lượng không dương và giá âm ngay khi tạo.
- `addLine` chỉ cho phép sửa đơn nháp, kiểm tra loại tiền và ngăn sản phẩm trùng theo chính sách của ví dụ.
- `place` không cho đặt đơn trống và chuyển trạng thái bằng một hành động nghiệp vụ có tên.
- `lines()` trả về bản sao không thể sửa cấu trúc danh sách bên trong, tránh caller thêm hoặc xóa dòng mà bỏ qua kiểm tra.
- `Order` so sánh theo ID ổn định, còn `OrderLine` và `Money` so sánh theo giá trị.

Trong sản phẩm thật, có thể dùng ngoại lệ miền có mã lỗi riêng thay cho `IllegalArgumentException` hoặc `IllegalStateException`. Cũng cần định nghĩa các hành động như hủy đơn, thay đổi số lượng và tính tổng theo chính sách thực tế. Đoạn mã minh họa cách đặt trách nhiệm; nó không phải một mô hình đơn hàng hoàn chỉnh.

## 6. Ai bảo vệ quy tắc nào trong kiến trúc phân tầng?

Phân tầng giúp phân chia nơi tiếp nhận, điều phối, thực thi quy tắc và lưu trữ. Không nên dồn mọi kiểm tra vào một lớp service chỉ vì lớp đó dễ gọi.

| Vị trí | Trách nhiệm điển hình | Ví dụ |
|---|---|---|
| Tầng trình bày | Kiểm tra cú pháp, kiểu, trường bắt buộc và hợp đồng giao tiếp | JSON có đọc được không; `quantity` có phải số nguyên không |
| Tầng ứng dụng | Điều phối ca sử dụng, tải entity, gọi dịch vụ miền, quản lý giao dịch | Tải đơn và thông tin tồn kho, sau đó yêu cầu đặt đơn |
| Entity / value object ở tầng nghiệp vụ | Bảo vệ bất biến mà đối tượng sở hữu | Không thêm dòng vào đơn đã đặt; Money không cộng khác loại tiền |
| Repository / tầng dữ liệu | Tải và lưu trạng thái, thực thi truy vấn và ràng buộc lưu trữ | Lưu đơn trong giao dịch; khóa hoặc cập nhật tồn kho theo cơ chế phù hợp |

Ví dụ, request gửi `quantity = -2` có thể bị từ chối ở DTO bằng `@Positive`. Nhưng tầng nghiệp vụ vẫn cần bảo vệ điều kiện số lượng dương trong `OrderLine`, bởi `OrderLine` có thể được tạo từ một consumer hàng đợi, tác vụ nội bộ hoặc một ca sử dụng khác không đi qua HTTP controller.

Ngược lại, kiểm tra “còn đủ hàng trong kho tại thời điểm đặt” không thể chỉ được giải quyết bằng một annotation trên DTO hoặc bằng cách kiểm tra một trường trong `Order`. Tầng ứng dụng cần phối hợp với thành phần quản lý tồn kho và thực hiện thao tác trong ranh giới giao dịch thích hợp. Khi có nhiều yêu cầu đồng thời, cần cơ chế chống tranh chấp như cập nhật có điều kiện, khóa phù hợp hoặc kiểm soát phiên bản; đọc số lượng tồn trước rồi ghi sau mà không có bảo vệ có thể dẫn đến bán vượt tồn.

Tầng ứng dụng thường điều phối, còn entity và value object bảo vệ quy tắc gắn với trạng thái mà chúng sở hữu. Với quy tắc không tự nhiên thuộc về một entity đơn lẻ, có thể dùng domain service hoặc một chính sách miền. Cách đặt cụ thể phụ thuộc độ phức tạp và mô hình của hệ thống.

## 7. Phân biệt bất biến miền với ràng buộc cơ sở dữ liệu

Cơ sở dữ liệu cũng có thể bảo vệ dữ liệu bằng `NOT NULL`, `CHECK`, `UNIQUE`, khóa ngoại và giao dịch. Đây là lớp bảo vệ quan trọng, đặc biệt khi có nhiều tiến trình cùng ghi dữ liệu. Tuy nhiên, ràng buộc lưu trữ và bất biến miền phục vụ những mục đích khác nhau.

- Bất biến miền diễn đạt ý nghĩa và điều kiện hợp lệ của hành vi nghiệp vụ, thường bằng tên và thao tác có thể hiểu trong code.
- Ràng buộc cơ sở dữ liệu bảo vệ tính nhất quán ở nơi dữ liệu được lưu, kể cả khi có đường ghi ngoài ứng dụng.
- Giao dịch và cơ chế đồng thời giúp bảo vệ các điều kiện cần đúng khi nhiều yêu cầu diễn ra cùng lúc.

Ví dụ, `CHECK (quantity > 0)` có thể ngăn lưu dòng hàng có số lượng âm, nhưng không giải thích vì sao đơn đã đặt không được sửa. Quy tắc chuyển trạng thái cần được mô hình hóa trong hành vi của entity hoặc ca sử dụng; ràng buộc lưu trữ có thể bổ sung bảo vệ nếu có cách biểu diễn phù hợp.

Không nên chỉ dựa vào kiểm tra trong bộ nhớ đối với các quy tắc có nguy cơ bị vi phạm bởi ghi đồng thời hoặc ghi từ nhiều nguồn. Cũng không nên chuyển toàn bộ ý nghĩa nghiệp vụ thành trigger hay stored procedure khiến quy tắc khó quan sát ở tầng nghiệp vụ. Hãy chọn nhiều lớp bảo vệ theo rủi ro và kiến trúc triển khai.

## 8. Cách nhận diện trong một bài toán thực tế

Có thể dùng quy trình sau khi phân tích một ca sử dụng:

1. **Đọc động từ trước danh từ.** Ghi lại các hành động như tạo, đổi, đặt, hủy, phê duyệt, thanh toán. Hành động thường cho biết đối tượng nào cần có hành vi và trạng thái.
2. **Tìm danh tính và vòng đời.** Hỏi đối tượng có cần được tham chiếu qua nhiều thao tác, có lịch sử hoặc trạng thái riêng không. Nếu có, xem xét entity.
3. **Tìm giá trị mô tả.** Hỏi hai đối tượng có cùng ý nghĩa khi các thành phần giá trị giống nhau không, và có cần ID riêng không. Nếu không cần danh tính độc lập, xem xét value object.
4. **Viết các điều kiện luôn phải đúng.** Diễn đạt thành câu có thể kiểm chứng: “số lượng lớn hơn 0”, “đơn đã đặt không nhận dòng mới”, “mọi dòng dùng cùng tiền tệ”.
5. **Xác định phạm vi sở hữu.** Điều kiện thuộc một giá trị, một entity, một nhóm đối tượng hay nhiều entity/hệ thống? Đặt kiểm tra gần nơi có đủ dữ liệu và quyền kiểm soát.
6. **Xác định nguồn sự thật.** Nếu quy tắc phụ thuộc tồn kho, hạn mức hoặc trạng thái bên ngoài, chỉ rõ thành phần nào truy vấn và cơ chế nào bảo vệ tính đúng khi cập nhật đồng thời.
7. **Kiểm tra các đường vào khác.** HTTP, message consumer, batch job và lệnh nội bộ có cùng đi qua nơi bảo vệ bất biến không? Nếu không, quy tắc có thể bị bỏ qua.

Một bảng ghi nhận nhỏ giúp nhóm thống nhất quyết định:

| Khái niệm | Danh tính riêng? | Thay đổi theo thời gian? | Quyết định mô hình |
|---|---|---|---|
| Đơn hàng | Có, theo mã đơn | Có trạng thái và dòng hàng | Entity |
| Tiền | Không, theo số tiền và tiền tệ | Tạo giá trị mới khi thay đổi | Value object |
| Dòng hàng | Không trong ví dụ đơn giản | Thay bằng giá trị mới khi sửa | Value object thuộc đơn |
| Sản phẩm | Thường có mã sản phẩm riêng | Có thể đổi tên hoặc giá niêm yết | Entity trong ngữ cảnh quản lý sản phẩm |

Quyết định ở bảng chỉ đúng trong ngữ cảnh đã nêu. Nếu dòng hàng có mã riêng, được hoàn trả độc lập hoặc cần lưu lịch sử thay đổi riêng, vai trò của nó có thể khác.

## 9. Kiểm thử entity, value object và bất biến

Các quy tắc cốt lõi nên có kiểm thử đơn vị nhanh, không cần khởi động Spring hay cơ sở dữ liệu. Hãy kiểm thử cả trường hợp hợp lệ lẫn hành động phải bị từ chối.

| Đối tượng / hành động | Trường hợp kiểm thử | Kết quả mong đợi |
|---|---|---|
| `Money` | Cộng hai giá trị cùng loại tiền | Trả value object mới với tổng đúng |
| `Money` | Cộng hai loại tiền khác nhau | Bị từ chối |
| `OrderLine` | Tạo dòng với số lượng bằng 0 hoặc âm | Bị từ chối |
| `Order` | Thêm dòng có tiền tệ khác dòng hiện tại | Bị từ chối |
| `Order` | Đặt đơn không có dòng | Bị từ chối |
| `Order` | Thêm dòng sau khi đã đặt | Bị từ chối |
| `Order` | Hai instance cùng ID | Được xem là cùng entity theo chính sách equality |
| `OrderLine` | Hai instance có cùng giá trị | Được xem là bằng nhau |

Ví dụ kiểm thử với JUnit:

```java
@Test
void cannotPlaceAnEmptyOrder() {
    Order order = new Order(UUID.randomUUID());

    assertThrows(IllegalStateException.class, order::place);
}

@Test
void cannotAddLineAfterOrderIsPlaced() {
    Order order = new Order(UUID.randomUUID());
    Money price = new Money(
        new BigDecimal("120000"), Currency.getInstance("VND")
    );
    order.addLine(new OrderLine(new ProductId(UUID.randomUUID()), 1, price));
    order.place();

    OrderLine anotherLine = new OrderLine(
        new ProductId(UUID.randomUUID()), 1, price
    );
    assertThrows(IllegalStateException.class, () -> order.addLine(anotherLine));
}
```

Ngoài unit test, kiểm thử tích hợp cần xác minh việc lưu và tải lại không làm mất trạng thái hoặc vi phạm ràng buộc. Với quy tắc liên quan nhiều giao dịch đồng thời, cần kiểm thử ở mức tích hợp phù hợp để xác minh cơ chế khóa, cập nhật có điều kiện hoặc xử lý xung đột thực sự hoạt động.

## 10. Những cách làm dễ làm suy yếu mô hình

- **Biến mọi danh từ thành entity:** tạo nhiều lớp có ID nhưng không có danh tính hoặc hành vi có ý nghĩa, làm mô hình nặng mà không bảo vệ thêm quy tắc.
- **Dùng entity như túi dữ liệu:** cung cấp setter công khai cho mọi trường khiến trạng thái có thể bị thay đổi mà không qua kiểm tra.
- **Dùng value object có thể sửa tại chỗ:** caller giữ tham chiếu và thay đổi giá trị khiến các đối tượng khác bị ảnh hưởng ngoài dự kiến. Ưu tiên bất biến.
- **So sánh entity bằng mọi thuộc tính:** đổi tên hoặc trạng thái sẽ làm entity có vẻ trở thành đối tượng khác. Dùng danh tính ổn định theo chính sách của mô hình.
- **Coi JPA `@Entity` là mô hình miền:** ánh xạ ORM không tự tạo ra hành vi hay bất biến nghiệp vụ.
- **Đặt mọi quy tắc trong application service:** nhiều ca sử dụng có thể lặp lại kiểm tra và một luồng khác có thể quên gọi đúng service. Quy tắc thuộc trạng thái của entity/value object nên được bảo vệ ngay tại đó.
- **Đưa mọi quy tắc vào constructor:** điều kiện cần dữ liệu bên ngoài hoặc phụ thuộc vào nhiều entity không thể được xác minh chỉ bằng một constructor. Phân biệt bất biến nội tại với chính sách cần điều phối.
- **Chỉ kiểm tra trong bộ nhớ:** dữ liệu đồng thời hoặc đường ghi khác có thể phá vỡ điều kiện. Bổ sung transaction và ràng buộc lưu trữ khi cần.
- **Áp dụng DDD quá mức:** một ứng dụng CRUD đơn giản có thể chỉ cần DTO, service rõ ràng và ràng buộc dữ liệu phù hợp. Chỉ tạo entity/value object/domain service khi chúng giúp diễn đạt và bảo vệ quy tắc thực tế.

Khi đã xác định được entity, value object và phạm vi của từng invariant, hãy đặt hành vi thay đổi trạng thái qua những phương thức có tên theo nghiệp vụ, kiểm thử các điều kiện quan trọng và bảo vệ dữ liệu đồng thời ở nơi thích hợp. Cách làm này giúp tầng nghiệp vụ giữ được ý nghĩa của nó: mô tả những điều hệ thống phải luôn bảo đảm, bất kể yêu cầu đến từ màn hình HTTP, tác vụ nền hay một adapter khác.
