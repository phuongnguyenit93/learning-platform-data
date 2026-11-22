# Lựa chọn Java record hoặc lớp thông thường theo yêu cầu của mô hình

Trong Domain-Driven Design (DDD), lựa chọn giữa Java record và lớp thông thường cần bắt đầu từ ý nghĩa nghiệp vụ của khái niệm. Câu hỏi không chỉ là cú pháp nào ngắn hơn, mà là đối tượng cần được so sánh theo giá trị hay theo danh tính, có bất biến nào phải bảo vệ, trạng thái có được phép thay đổi trong vòng đời hay không và công nghệ lưu trữ có yêu cầu cấu trúc cụ thể nào.

**Java record** phù hợp với những dữ liệu có ngữ nghĩa giá trị rõ ràng, thường bất biến và được xác định bởi các thành phần của nó. **Lớp thông thường (class)** linh hoạt hơn khi mô hình cần danh tính, vòng đời, trạng thái thay đổi có kiểm soát, kế thừa hoặc tương thích với một số framework.

Không có quy tắc rằng mọi Value Object phải là record hoặc mọi Entity phải là class. Record là một công cụ ngôn ngữ hữu ích để biểu diễn dữ liệu theo giá trị; class cũng có thể biểu diễn Value Object tốt nếu được thiết kế bất biến và định nghĩa equality đúng. Hãy chọn dựa trên hợp đồng mà mô hình cần thể hiện.

## 1. Bắt đầu từ ngữ nghĩa của mô hình

### 1.1. Value Object được nhận diện bằng giá trị

Value Object mô tả một khái niệm nghiệp vụ mà ý nghĩa được xác định bởi các thuộc tính của nó, không cần danh tính riêng xuyên suốt vòng đời.

Ví dụ:

- **Money:** số tiền và loại tiền.
- **DateRange:** ngày bắt đầu và ngày kết thúc.
- **Percentage:** một tỷ lệ hợp lệ trong phạm vi nghiệp vụ.
- **EmailAddress:** địa chỉ email đã được chuẩn hóa và kiểm tra.
- **ShippingAddress:** địa chỉ giao hàng với các thành phần cần thiết cho một lần giao.

Hai Value Object được xem là bằng nhau khi chúng có cùng giá trị theo quy tắc nghiệp vụ. Một địa chỉ có cùng số nhà, đường, thành phố và mã bưu chính có thể được xem là cùng một giá trị, dù được tạo từ hai lần nhập khác nhau.

Value Object thường có các đặc điểm:

- Không có identity độc lập cần theo dõi.
- Equality dựa trên các thành phần có ý nghĩa.
- Nên bất biến sau khi được tạo.
- Có thể thay thế bằng một instance khác mang cùng giá trị.
- Tự bảo vệ các quy tắc hợp lệ của giá trị.

### 1.2. Entity được nhận diện bằng danh tính

Entity là đối tượng có danh tính liên tục trong vòng đời. Các thuộc tính có thể thay đổi nhưng đối tượng vẫn là cùng một Entity.

Ví dụ:

- **Order:** đơn hàng vẫn là cùng một đơn khi trạng thái thay đổi từ Submitted sang Confirmed.
- **Customer Account:** tài khoản vẫn giữ danh tính khi tên hoặc số điện thoại thay đổi.
- **Shipment:** lô giao hàng vẫn là cùng một lô khi trạng thái vận chuyển thay đổi.

Với Entity, hai đối tượng có cùng các thuộc tính hiện tại vẫn có thể là hai đối tượng khác nhau nếu identity khác nhau. Vì vậy, equality thường dựa trên định danh nghiệp vụ hoặc định danh được cấp trong vòng đời.

### 1.3. Quyết định mô hình trước, chọn cú pháp sau

Hãy trả lời những câu hỏi sau trước khi chọn record hay class:

- Khái niệm này có identity riêng không?
- Hai instance có cùng giá trị thì nghiệp vụ có xem chúng là một không?
- Trạng thái có được thay đổi sau khi tạo không?
- Có cần bảo vệ invariant qua các hành vi trong suốt vòng đời không?
- Các thành phần có bất biến hoặc cần sao chép phòng vệ không?
- Cần kiểm soát chặt cách khởi tạo hoặc cách thay đổi không?
- Có yêu cầu tương thích với ORM, proxy, serializer hoặc framework cụ thể không?

Nếu câu trả lời cho thấy đây là một giá trị bất biến, được xác định bởi các thành phần của nó, record thường là lựa chọn tự nhiên. Nếu đối tượng có identity và vòng đời thay đổi, class thường thể hiện đúng ý nghĩa hơn.

## 2. Java record cung cấp điều gì?

Record được giới thiệu như một dạng lớp đặc biệt để khai báo các nhóm dữ liệu có thành phần xác định. Từ Java 16, record là tính năng chính thức của ngôn ngữ.

Ví dụ:

~~~java
public record DateRange(
    LocalDate start,
    LocalDate end
) {
    public DateRange {
        Objects.requireNonNull(start, "start");
        Objects.requireNonNull(end, "end");

        if (end.isBefore(start)) {
            throw new IllegalArgumentException(
                "End date must not be before start date"
            );
        }
    }

    public boolean contains(LocalDate date) {
        return !date.isBefore(start) && !date.isAfter(end);
    }
}
~~~

Khai báo trên tạo ra một lớp có hai component, constructor canonical, accessor, equals, hashCode và toString. Phần compact constructor cho phép kiểm tra hoặc chuẩn hóa dữ liệu trước khi các component được gán.

### 2.1. Đặc điểm của record

- Record là **final**, không thể được kế thừa bởi class khác.
- Mỗi component tạo thành một field private final và một accessor cùng tên component.
- Record có constructor canonical tương ứng với danh sách component.
- Record tự sinh equals, hashCode và toString dựa trên các component, trừ khi lập trình viên tự định nghĩa lại.
- Record có thể khai báo phương thức instance, static method, static field và implement interface.
- Record không thể kế thừa một class tùy ý vì mọi record đều kế thừa java.lang.Record.
- Không thể khai báo thêm instance field độc lập ngoài các component đã khai báo.

Các đặc điểm này giúp record diễn đạt rõ một nhóm dữ liệu có cấu trúc cố định. Người đọc nhìn vào header là biết thành phần nào định nghĩa giá trị của đối tượng.

### 2.2. Constructor và validation

Record hỗ trợ compact canonical constructor. Các tham số có cùng tên với component; sau khi phần thân constructor hoàn tất, Java tự gán giá trị tham số vào field tương ứng.

~~~java
public record Percentage(BigDecimal value) {
    public Percentage {
        Objects.requireNonNull(value, "value");

        if (value.compareTo(BigDecimal.ZERO) < 0
                || value.compareTo(BigDecimal.valueOf(100)) > 0) {
            throw new IllegalArgumentException(
                "Percentage must be between 0 and 100"
            );
        }
    }
}
~~~

Nếu cần chuẩn hóa, có thể gán lại tham số trong compact constructor trước khi constructor kết thúc. Ví dụ, một EmailAddress có thể trim khoảng trắng và chuyển phần domain sang dạng chuẩn theo chính sách của ứng dụng.

Không nên đặt mọi quy tắc nghiệp vụ vào constructor một cách máy móc. Constructor nên bảo đảm giá trị được tạo ra là hợp lệ; các hành vi phức tạp có thể được thể hiện bằng phương thức hoặc dịch vụ miền phù hợp.

### 2.3. Record không chỉ là DTO

Record thường được dùng cho DTO, request, response hoặc dữ liệu truyền giữa các lớp. Tuy nhiên, trong mô hình miền, record cũng có thể là Value Object thực thụ nếu nó có định nghĩa, validation và hành vi phù hợp với ngôn ngữ nghiệp vụ.

Ví dụ Money không chỉ là cặp số và tiền tệ để truyền dữ liệu. Nó có thể bảo vệ quy tắc cộng tiền cùng loại tiền, so sánh, nhân số lượng và làm tròn theo chính sách tiền tệ.

~~~java
public record Money(
    BigDecimal amount,
    Currency currency
) {
    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
    }

    public Money add(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    public Money subtract(Money other) {
        requireSameCurrency(other);
        return new Money(amount.subtract(other.amount), currency);
    }

    private void requireSameCurrency(Money other) {
        Objects.requireNonNull(other, "other");
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                "Cannot combine different currencies"
            );
        }
    }
}
~~~

Ví dụ này chỉ minh họa quy tắc cùng loại tiền. Hệ thống thực tế cần xác định thêm cách làm tròn, số chữ số thập phân, quy tắc chuyển đổi tiền tệ và việc có cho phép số tiền âm hay không. Những quyết định đó thuộc chính sách nghiệp vụ và tiền tệ của context.

## 3. Lớp thông thường cung cấp điều gì?

Class thông thường cho phép thiết kế linh hoạt hơn về trạng thái, identity, constructor, visibility, kế thừa và cách triển khai equality.

Một class có thể biểu diễn:

- Entity có identity và vòng đời.
- Value Object có cấu trúc phức tạp hoặc cách khởi tạo cần kiểm soát.
- Domain Service hoặc thành phần có hành vi.
- Adapter, repository implementation và các thành phần kỹ thuật.

### 3.1. Class cho Entity có trạng thái thay đổi

~~~java
public final class Order {
    private final OrderId id;
    private OrderStatus status;
    private final List<OrderLine> lines;

    public Order(OrderId id, List<OrderLine> lines) {
        this.id = Objects.requireNonNull(id, "id");
        this.lines = new ArrayList<>(lines);
        if (this.lines.isEmpty()) {
            throw new IllegalArgumentException(
                "An order must contain at least one line"
            );
        }
        this.status = OrderStatus.DRAFT;
    }

    public void submit() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Only a draft order can be submitted"
            );
        }
        status = OrderStatus.SUBMITTED;
    }

    public OrderId id() {
        return id;
    }

    public OrderStatus status() {
        return status;
    }
}
~~~

Order có identity là OrderId. Trạng thái thay đổi thông qua hành vi submit, trong đó đối tượng tự bảo vệ điều kiện chuyển trạng thái. Đây là mô hình Entity điển hình nên class thường phù hợp hơn record.

### 3.2. Class cũng có thể là Value Object

Không phải mọi Value Object đều nên là record. Một class bất biến có thể phù hợp khi:

- Cần ẩn cấu trúc nội bộ và chỉ cho phép tạo qua factory.
- Cần kiểm tra nhiều điều kiện hoặc chuẩn hóa phức tạp.
- Cần kiểm soát chính xác equality.
- Cần triển khai interface hoặc tương thích với một API/framework yêu cầu class cụ thể.
- Có cấu trúc nội bộ không muốn công khai thành component.

Ví dụ:

~~~java
public final class EmailAddress {
    private final String value;

    private EmailAddress(String value) {
        this.value = value;
    }

    public static EmailAddress of(String input) {
        Objects.requireNonNull(input, "input");
        String normalized = input.trim();

        if (normalized.isEmpty() || !normalized.contains("@")) {
            throw new IllegalArgumentException(
                "Invalid email address"
            );
        }

        return new EmailAddress(normalized);
    }

    public String value() {
        return value;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof EmailAddress that)) return false;
        return value.equals(that.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }
}
~~~

Class trên có constructor private và factory để kiểm soát việc tạo giá trị. Nó không có identity độc lập; equality dựa trên email đã chuẩn hóa. Đây vẫn là Value Object dù được triển khai bằng class.

Kiểm tra định dạng email trong ví dụ chỉ là minh họa tối giản. Nghiệp vụ thực tế cần xác định quy tắc chuẩn hóa, so sánh chữ hoa/chữ thường, xác minh quyền sở hữu và các giới hạn theo nhà cung cấp.

## 4. So sánh record và class theo yêu cầu mô hình

| Tiêu chí | Java record | Class thông thường |
|---|---|---|
| Mục đích tự nhiên | Nhóm dữ liệu có component cố định | Đối tượng có cấu trúc và hành vi linh hoạt |
| Equality mặc định | Theo tất cả component | Theo identity tham chiếu nếu không override |
| Identity nghiệp vụ | Không phải lựa chọn tự nhiên | Có thể biểu diễn rõ bằng ID |
| Immutability | Field component là final, nhưng chỉ bất biến nông | Có thể bất biến hoặc thay đổi tùy thiết kế |
| Trạng thái thay đổi | Không phù hợp với trạng thái instance có thể sửa | Hỗ trợ thay đổi có kiểm soát |
| Constructor | Canonical hoặc compact canonical | Tùy biến nhiều constructor, factory và visibility |
| Accessor | Sinh accessor theo tên component | Tự định nghĩa getter hoặc API đọc |
| Kế thừa class | Không thể kế thừa class khác | Có thể kế thừa nếu không final |
| Instance field bổ sung | Không thể có instance field ngoài component | Có thể có nhiều field |
| Equality tùy chỉnh | Có thể override nhưng cần cân nhắc ngữ nghĩa component | Hoàn toàn do thiết kế quyết định |
| Phù hợp Value Object | Rất tự nhiên với giá trị bất biến, cấu trúc rõ | Phù hợp khi cần kiểm soát cấu trúc hoặc khởi tạo |
| Phù hợp Entity | Thường không phù hợp | Thường là lựa chọn tự nhiên |
| Tương thích ORM | Cần kiểm tra giới hạn của ORM; không phù hợp với nhiều yêu cầu Entity chuẩn | Thường linh hoạt hơn với ORM |

Không nên hiểu bảng này là luật cứng. Record có thể implement interface và chứa hành vi; class có thể bất biến và có equality theo giá trị. Điều quyết định vẫn là ngữ nghĩa mà mô hình phải bảo vệ.

## 5. Equality: điểm khác biệt quan trọng nhất

### 5.1. Record mặc định so sánh theo component

~~~java
var first = new DateRange(
    LocalDate.of(2026, 1, 1),
    LocalDate.of(2026, 1, 31)
);
var second = new DateRange(
    LocalDate.of(2026, 1, 1),
    LocalDate.of(2026, 1, 31)
);

System.out.println(first.equals(second)); // true
~~~

Hai record khác nhau về tham chiếu nhưng có các component bằng nhau, nên equals trả về true theo equality được sinh tự động.

Đây là hành vi phù hợp với Value Object: hai giá trị ngày bắt đầu và ngày kết thúc giống nhau có thể được xem là cùng một khoảng thời gian.

### 5.2. Class Entity thường so sánh theo identity

~~~java
public final class CustomerAccount {
    private final CustomerId id;
    private String displayName;

    public CustomerAccount(CustomerId id, String displayName) {
        this.id = Objects.requireNonNull(id);
        this.displayName = Objects.requireNonNull(displayName);
    }

    public void changeDisplayName(String newName) {
        this.displayName = Objects.requireNonNull(newName);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof CustomerAccount that)) return false;
        return id.equals(that.id);
    }

    @Override
    public int hashCode() {
        return id.hashCode();
    }
}
~~~

Hai tài khoản có cùng tên hiển thị nhưng ID khác nhau vẫn là hai Entity khác nhau. Khi tên thay đổi, identity vẫn giữ nguyên.

Trong hệ thống có Entity chưa được cấp ID trước khi lưu, cần thiết kế equality cẩn thận. Không nên dùng các thuộc tính có thể thay đổi làm hashCode nếu đối tượng có thể nằm trong HashSet hoặc làm key của HashMap. Một thay đổi làm thay đổi hashCode có thể khiến đối tượng không còn được tìm thấy đúng trong collection.

### 5.3. Class Value Object phải tự định nghĩa equality

Class không tự động có equality theo giá trị. Nếu dùng class để biểu diễn Value Object, cần override equals và hashCode dựa trên tất cả thành phần có ý nghĩa nghiệp vụ.

Hai phương thức phải nhất quán: nếu hai object bằng nhau theo equals thì hashCode phải giống nhau. Không nên đưa vào equality các trường kỹ thuật như thời điểm tạo object hoặc bộ đếm nội bộ nếu chúng không ảnh hưởng đến ý nghĩa giá trị.

### 5.4. Cẩn thận với BigDecimal và các kiểu dữ liệu đặc biệt

BigDecimal có quy tắc equals phân biệt scale: 10.0 và 10.00 không bằng nhau theo equals, dù compareTo xem chúng có cùng giá trị số.

Nếu Money là Value Object, đội cần quyết định scale có ý nghĩa hay không. Có thể chuẩn hóa số thập phân theo quy tắc tiền tệ trước khi lưu vào component, hoặc định nghĩa cách so sánh phù hợp. Không nên vô tình để chi tiết biểu diễn quyết định equality nghiệp vụ.

Các component kiểu array cũng cần chú ý: equality mặc định của array dựa trên identity của array, không phải so sánh sâu từng phần tử. Nếu record chứa mảng, hãy cân nhắc chuyển sang List bất biến hoặc tự định nghĩa cách so sánh và sao chép.

## 6. Immutability: record chỉ bất biến nông

Record có các component final, nhưng điều đó không làm mọi object mà component tham chiếu đến trở nên bất biến.

Ví dụ không an toàn:

~~~java
public record OrderSnapshot(List<String> itemNames) {
}
~~~

Người gọi vẫn có thể truyền một ArrayList rồi sửa danh sách sau khi record được tạo. Record giữ tham chiếu final đến danh sách, nhưng nội dung danh sách vẫn thay đổi.

Có thể tạo defensive copy:

~~~java
public record OrderSnapshot(List<String> itemNames) {
    public OrderSnapshot {
        itemNames = List.copyOf(itemNames);
    }
}
~~~

List.copyOf tạo danh sách không thể sửa thông qua tham chiếu được trả về. Tuy nhiên, nếu phần tử bên trong là object mutable thì chúng vẫn có thể thay đổi. Cần dùng các phần tử bất biến hoặc sao chép sâu theo yêu cầu.

Với class, nguyên tắc tương tự vẫn áp dụng:

- Dùng field private final cho dữ liệu không thay đổi.
- Không trả trực tiếp collection mutable nội bộ.
- Sao chép đầu vào khi cần.
- Trả về view bất biến hoặc bản sao.
- Không để object bên ngoài sửa trạng thái mà không đi qua hành vi có kiểm soát.

Immutability giúp Value Object an toàn khi chia sẻ, dễ kiểm thử và không phải lo trạng thái thay đổi sau khi đã được dùng trong phép tính. Nhưng một class Entity vẫn có thể thay đổi trạng thái vì vòng đời của nó yêu cầu điều đó.

## 7. Chọn record cho Value Object khi nào?

Record thường là lựa chọn tốt khi các điều kiện sau đúng:

- Khái niệm có ngữ nghĩa giá trị, không cần identity riêng.
- Tập hợp component tương đối ổn định và công khai là hợp lý.
- Các component có thể được làm bất biến hoặc sao chép phòng vệ.
- Equality theo component đúng với nghiệp vụ.
- Việc tạo object có thể được kiểm tra trong canonical constructor hoặc factory.
- Không cần kế thừa class khác hoặc lưu trạng thái instance có thể thay đổi.
- Framework và cách lưu trữ hỗ trợ record theo phiên bản đang dùng.

Các ví dụ thường phù hợp:

- Money.
- DateRange.
- Coordinates.
- Percentage.
- Quantity.
- ProductCode nếu equality dựa trên mã đã chuẩn hóa.
- AddressSnapshot nếu địa chỉ là giá trị được chốt cho một giao dịch.

Record có thể chứa phương thức nghiệp vụ. Đừng biến nó thành túi dữ liệu chỉ vì record thường được gọi là data carrier. Nếu một Value Object có phép cộng, kiểm tra khoảng thời gian hoặc quy tắc chuẩn hóa, hãy đặt hành vi đó gần dữ liệu mà nó bảo vệ.

## 8. Chọn class khi nào?

Class thông thường phù hợp khi có một hoặc nhiều nhu cầu sau:

- Đối tượng có identity và vòng đời.
- Trạng thái thay đổi qua các hành vi nghiệp vụ.
- Cần bảo vệ transition hoặc invariant trong nhiều giai đoạn.
- Cần constructor private/protected, factory hoặc quá trình khởi tạo nhiều bước.
- Cần kiểm soát các API đọc/ghi thay vì công khai mọi component.
- Cần kế thừa một class nền hoặc hỗ trợ proxy của framework.
- Cần instance field nội bộ không phải thành phần equality.
- Cần triển khai equality theo identity hoặc theo một quy tắc đặc biệt.

Class cũng phù hợp cho Value Object khi cấu trúc phức tạp. Ví dụ, một ShippingAddress có thể được tạo qua factory theo quốc gia, cần chuẩn hóa mã vùng, phân biệt địa chỉ dân cư và địa chỉ doanh nghiệp, hoặc cần ẩn một số trường không nên được truy cập trực tiếp.

Không nên chọn class chỉ vì quen dùng class. Nếu một record đơn giản biểu diễn đúng ngữ nghĩa và tương thích với hạ tầng, record có thể làm mô hình rõ hơn và giảm mã lặp.

## 9. Tương thích với ORM, serialization và framework

Mô hình miền có thể được lưu trữ hoặc trao đổi qua nhiều công nghệ. Những yêu cầu này cần được xem xét nhưng không nên tự động chi phối ngữ nghĩa nghiệp vụ.

### 9.1. JPA và Entity

Các yêu cầu của JPA đối với entity class truyền thống bao gồm class không final và có constructor không tham số với visibility phù hợp; provider cũng có thể cần khả năng tạo proxy hoặc truy cập field theo cách riêng. Record là final và không được thiết kế để làm JPA entity mutable theo vòng đời, vì vậy không phải lựa chọn portable cho Entity JPA thông thường.

Với Value Object, khả năng ánh xạ record phụ thuộc phiên bản JPA provider, Hibernate hoặc framework đang sử dụng và loại mapping. Không nên giả định mọi phiên bản đều hỗ trợ record như embeddable hoặc component. Hãy kiểm tra tài liệu và thử mapping với phiên bản cụ thể.

Một cách giữ mô hình rõ là tách domain model khỏi persistence model khi yêu cầu ORM xung đột với thiết kế miền. Adapter hoặc mapper chịu trách nhiệm chuyển đổi giữa hai biểu diễn.

### 9.2. JSON và serialization

Nhiều thư viện JSON hiện đại hỗ trợ record, nhưng khả năng cụ thể phụ thuộc phiên bản thư viện, cách cấu hình và yêu cầu constructor. Hãy xác minh:

- Tên property được serialize có đúng hợp đồng API không?
- Constructor có thể tạo object khi deserialize không?
- Validation có được chạy khi dữ liệu đi vào không?
- Component mới hoặc thay đổi tên có ảnh hưởng client cũ không?
- Có cần DTO riêng để không công khai cấu trúc nội bộ của domain không?

Record tiện cho request/response có cấu trúc cố định, nhưng không nên để hợp đồng API tự động trở thành mô hình miền chỉ vì cả hai có cùng field.

### 9.3. Framework proxy và dependency injection

Một số framework tạo subclass hoặc proxy để bổ sung lazy loading, transaction hoặc interception. Vì record là final, những cơ chế dựa vào subclass không thể áp dụng trực tiếp lên record. Khả năng hỗ trợ còn tùy framework và cơ chế proxy cụ thể.

Nếu framework cần proxy cho một Entity, class không final thường phù hợp hơn. Nếu một Value Object không cần proxy, record có thể là lựa chọn tốt.

### 9.4. Không để framework quyết định toàn bộ mô hình

Hãy ưu tiên ngữ nghĩa miền trước. Khi framework có giới hạn, có thể:

- Dùng class domain và class persistence riêng.
- Dùng mapper hoặc adapter chuyển đổi.
- Cấu hình mapping phù hợp với provider.
- Chọn cách lưu Value Object theo cấu trúc đơn giản hơn nếu không làm mất ý nghĩa.

Chi phí chuyển đổi cần được cân nhắc. Không cần tách mọi class nếu framework hỗ trợ trực tiếp và không làm méo mô hình.

## 10. Ví dụ lựa chọn theo từng khái niệm

| Khái niệm | Ngữ nghĩa | Lựa chọn thường phù hợp | Lý do |
|---|---|---|---|
| Money | Giá trị tiền được xác định bởi amount và currency | Record | Equality theo component, bất biến, có thể chứa phép tính |
| DateRange | Khoảng ngày hợp lệ | Record | Hai component xác định toàn bộ giá trị |
| Order | Đơn hàng có ID, trạng thái và vòng đời | Class | Identity ổn định, hành vi làm thay đổi trạng thái |
| CustomerAccount | Tài khoản có ID và thông tin có thể thay đổi | Class | Equality theo identity, hành vi quản lý vòng đời |
| EmailAddress | Giá trị email đã chuẩn hóa | Record hoặc class | Record nếu cấu trúc đơn giản; class nếu cần factory và ẩn biểu diễn |
| ShippingAddress | Địa chỉ được chốt cho giao dịch | Record hoặc class | Chọn theo mức phức tạp của validation và mapping |
| OrderSubmitted | Sự kiện gửi đơn đã xảy ra | Record thường phù hợp | Dữ liệu sự kiện cố định, equality theo nội dung nếu cần |
| PaymentAttempt | Lần thử thanh toán có ID và trạng thái riêng | Class | Cần theo dõi identity và chuyển trạng thái |

Các lựa chọn trong bảng là điểm xuất phát. Ví dụ, PaymentAttempt có thể chỉ là dữ liệu bất biến trong một mô hình khác, nhưng nếu nghiệp vụ cần theo dõi vòng đời và các lần thử độc lập, class Entity sẽ diễn đạt tốt hơn.

## 11. Những lỗi thiết kế thường gặp

### Dùng record cho Entity chỉ vì có nhiều field

Một Entity có nhiều thuộc tính không vì thế trở thành Value Object. Nếu nó có ID và trạng thái thay đổi, record với equality theo tất cả component có thể làm hai Entity khác identity bị xem là bằng nhau hoặc khiến việc thay đổi trạng thái không tự nhiên.

### Dùng class cho mọi Value Object nhưng quên equality

Class mặc định so sánh theo tham chiếu. Nếu hai Money được tạo riêng nhưng có cùng giá trị, chúng vẫn không bằng nhau nếu chưa override equals và hashCode. Điều này có thể làm các phép so sánh và collection hoạt động sai với kỳ vọng nghiệp vụ.

### Cho rằng record tự động bất biến sâu

Field final chỉ cố định tham chiếu. List, Map, array hoặc object mutable bên trong vẫn có thể thay đổi. Cần defensive copy hoặc dùng thành phần bất biến.

### Đưa component kỹ thuật vào equality

Nếu một Value Object có field ghi nhận thời điểm tạo hoặc nguồn nhập nhưng những thông tin đó không làm thay đổi ý nghĩa giá trị, đưa chúng vào record component sẽ khiến equals xem hai giá trị nghiệp vụ giống nhau là khác nhau. Hãy phân biệt dữ liệu mô tả giá trị với metadata kỹ thuật.

### Dùng mutable field trong equals/hashCode

Nếu class dùng equality theo các field có thể thay đổi, object có thể bị mất khả năng tra cứu trong HashMap hoặc HashSet sau khi mutation. Value Object nên bất biến; Entity nên thường dùng identity ổn định.

### Dùng record như DTO rồi coi đó là mô hình miền

Một request API có thể có field do client gửi, field tùy chọn hoặc cách đặt tên theo giao thức. Mô hình miền có thể cần validation, chuẩn hóa và khái niệm khác. Hãy chuyển đổi request sang command hoặc Value Object phù hợp.

### Ép ORM sử dụng record mà chưa kiểm tra hỗ trợ

Mapping có thể thất bại do constructor, proxy, lazy loading hoặc giới hạn của provider. Kiểm tra phiên bản cụ thể và chọn adapter/mapping phù hợp trước khi quyết định dùng record trong persistence model.

### Tạo class quá phức tạp cho một giá trị đơn giản

Nếu một giá trị chỉ gồm vài component bất biến, có validation rõ và equality theo giá trị, class với nhiều getter, constructor và equals/hashCode lặp lại có thể tạo mã dư thừa. Record giúp diễn đạt ý định trực tiếp hơn.

## 12. Quy trình lựa chọn record hay class

Có thể sử dụng trình tự sau cho từng khái niệm:

1. **Xác định loại khái niệm:** Entity, Value Object, event, command, DTO hay thành phần kỹ thuật?
2. **Xác định equality:** bằng identity, bằng giá trị hay theo quy tắc đặc biệt?
3. **Xác định vòng đời:** object có cần thay đổi trạng thái sau khi tạo không?
4. **Xác định bất biến:** thành phần nào phải luôn hợp lệ và được bảo vệ ở đâu?
5. **Xác định cách khởi tạo:** constructor công khai có phù hợp hay cần factory/constructor riêng?
6. **Kiểm tra cấu trúc:** component có ổn định và công khai hợp lý không, có cần kế thừa hoặc field nội bộ không?
7. **Kiểm tra hạ tầng:** ORM, serializer, proxy và framework có hỗ trợ cách biểu diễn đó không?
8. **Thử với kịch bản:** so sánh, lưu, tải, thay đổi và truyền object qua các ranh giới.
9. **Ghi lại lý do:** để người đọc hiểu vì sao mô hình dùng record hoặc class.

~~~mermaid
flowchart TD
    A["Xác định khái niệm nghiệp vụ"] --> B{"Có identity và vòng đời riêng?"}
    B -->|Có| C["Ưu tiên class Entity"]
    B -->|Không| D{"Equality dựa trên giá trị?"}
    D -->|Không / Quy tắc đặc biệt| E["Thiết kế class với equality phù hợp"]
    D -->|Có| F{"Giá trị bất biến, component ổn định?"}
    F -->|Có| G{"Framework hỗ trợ record?"}
    G -->|Có| H["Ưu tiên record"]
    G -->|Không| I["Dùng class hoặc persistence model riêng"]
    F -->|Không| J["Dùng class và kiểm soát trạng thái"]
    C --> K["Kiểm tra invariant, equality và mapping"]
    E --> K
    H --> K
    I --> K
    J --> K
~~~

Sơ đồ là hướng dẫn suy nghĩ, không phải bộ luật tự động. Một class bất biến có thể là Value Object tốt; một record có thể implement interface và có hành vi miền. Hãy ưu tiên ngữ nghĩa và kiểm tra tương thích thực tế.

## 13. Checklist trước khi chốt kiểu Java

Với một Value Object:

- Định nghĩa giá trị và các component đã rõ chưa?
- Equality theo các component có đúng với nghiệp vụ không?
- Giá trị có được chuẩn hóa trước khi so sánh không?
- Có thành phần mutable cần defensive copy không?
- Validation và invariant được kiểm tra tại thời điểm tạo chưa?
- Có hành vi nghiệp vụ nào nên đặt ngay trên Value Object không?
- Record có làm lộ cấu trúc mà context không muốn công khai không?
- Framework và persistence provider có hỗ trợ record theo phiên bản đang dùng không?

Với một Entity:

- Identity có ổn định và duy nhất trong phạm vi cần thiết không?
- Equality có dựa trên identity đúng cách không?
- Trạng thái thay đổi thông qua hành vi có kiểm soát không?
- Invariant có được bảo vệ xuyên suốt vòng đời không?
- Có yêu cầu ORM/proxy cần class không final không?
- Có tránh dùng field mutable trong hashCode không?

Với mọi lựa chọn:

- Kiểu Java đang thể hiện đúng ngôn ngữ nghiệp vụ không?
- Người đọc có thể hiểu ý nghĩa object từ tên và API không?
- Có tách biệt mô hình miền với DTO hoặc persistence model khi cần không?
- Có ví dụ kiểm thử chứng minh equality, validation và mutation hoạt động đúng không?

## 14. Kết luận

Java record là lựa chọn tự nhiên cho Value Object có cấu trúc rõ, bất biến và equality theo giá trị. Class thông thường phù hợp với Entity có identity và vòng đời, đồng thời vẫn là lựa chọn tốt cho Value Object cần factory, kiểm soát cấu trúc hoặc tương thích hạ tầng đặc biệt.

Hãy quyết định từ ngữ nghĩa nghiệp vụ: đối tượng đại diện cho điều gì, được so sánh thế nào, có thể thay đổi ra sao và phải bảo vệ quy tắc nào. Sau đó mới chọn record hoặc class, kiểm tra equality, immutability và khả năng ánh xạ. Khi cú pháp Java phản ánh đúng hợp đồng của mô hình, mã nguồn sẽ dễ đọc, dễ kiểm thử và ít tạo ra những giả định sai về nghiệp vụ.
