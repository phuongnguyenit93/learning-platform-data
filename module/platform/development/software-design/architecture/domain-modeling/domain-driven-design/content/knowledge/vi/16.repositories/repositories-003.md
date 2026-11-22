# Thiết kế hợp đồng tìm theo định danh và tiêu chí nghiệp vụ

Trong Domain-Driven Design (DDD), Repository cung cấp một cách làm việc với aggregate như thể chúng được lấy từ một tập hợp trong bộ nhớ. Người gọi quan tâm đến aggregate cần cho nghiệp vụ và ý nghĩa của thao tác tìm kiếm, không cần biết dữ liệu nằm trong PostgreSQL, MongoDB hay một hệ thống lưu trữ khác.

Hai nhu cầu tìm kiếm thường gặp là tìm theo **định danh** và tìm theo **tiêu chí nghiệp vụ**. Tìm theo định danh trả lời câu hỏi “đây có phải aggregate cụ thể mà tôi cần không?”. Tìm theo tiêu chí trả lời câu hỏi “aggregate nào thỏa điều kiện nghiệp vụ này?”. Hai nhu cầu có thể cùng xuất hiện trong một Repository, nhưng hợp đồng cần thể hiện rõ tính duy nhất, số lượng kết quả, ý nghĩa của điều kiện và cách xử lý khi không tìm thấy.

Một hợp đồng tốt giúp application service diễn đạt use case bằng ngôn ngữ miền, bảo vệ ranh giới aggregate và không làm lộ chi tiết truy vấn của hạ tầng. Với truy vấn đọc phức tạp, phân trang hoặc tổng hợp dữ liệu, một query service/read model riêng thường phù hợp hơn Repository chuyên tải và lưu aggregate.

## Sau bài học này

Bạn có thể:

- Phân biệt tìm aggregate theo định danh với tìm theo tiêu chí nghiệp vụ.
- Thiết kế tên phương thức và kiểu tham số theo ngôn ngữ của bounded context.
- Chọn kiểu kết quả phù hợp với số lượng kết quả và tính duy nhất.
- Biểu diễn tiêu chí tìm kiếm bằng value object hoặc kiểu truy vấn có ý nghĩa.
- Phân biệt Repository của aggregate với query service phục vụ màn hình và báo cáo.
- Tránh để SQL, ORM, framework hoặc cấu trúc database rò rỉ vào hợp đồng.
- Xử lý không tìm thấy, dữ liệu trùng, phân trang, tính nhất quán và cập nhật đồng thời.

## 1. Repository là hợp đồng làm việc với aggregate

Repository là abstraction cho phép tải và lưu aggregate root. Nó thường được thiết kế giống một tập hợp các aggregate mà application có thể tìm, thêm hoặc cập nhật thông qua các thao tác có ý nghĩa.

Ví dụ:

```java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
```

Application service có thể tải `Order` bằng `OrderId`, gọi hành vi miền như `confirm()` rồi lưu aggregate. Repository adapter chịu trách nhiệm chuyển đổi giữa mô hình miền và cơ chế persistence.

Repository trong DDD không đơn giản là một lớp CRUD được sinh cho từng bảng. Nó tập trung vào aggregate root và cách ứng dụng cần truy cập aggregate để thực hiện nghiệp vụ. Nếu `OrderLine` là entity con bên trong aggregate `Order`, caller thường không cần một `OrderLineRepository` độc lập để sửa dòng hàng; thay đổi nên đi qua `Order` để bảo vệ invariant.

### Hợp đồng Repository thuộc layer nào?

Trong cách tổ chức DDD cổ điển, interface Repository thường nằm trong domain layer vì nó diễn đạt cách mô hình miền truy cập tập hợp aggregate. Trong kiến trúc ports-and-adapters, một port chỉ phục vụ điều phối use case cũng có thể được khai báo ở application layer. Hãy đặt interface ở phía sở hữu ý nghĩa của hợp đồng: `OrderRepository` có thể thuộc domain; `OrderQueries` phục vụ màn hình thường thuộc application. Adapter triển khai cả hai nằm ở infrastructure. Dù đặt ở đâu, hợp đồng không nên phụ thuộc ORM hoặc kiểu dữ liệu persistence.

### Repository không phải công cụ truy vấn tổng quát

Một màn hình có thể cần lọc hàng nghìn đơn theo nhiều trường, sắp xếp theo doanh thu, nối dữ liệu khách hàng và phân trang. Đây là nhu cầu đọc có thể phù hợp với query service hoặc read model.

Repository aggregate thường tập trung vào việc tải root để thực hiện hành vi và bảo vệ tính nhất quán. Không nên biến nó thành nơi chứa mọi truy vấn báo cáo chỉ vì dữ liệu cuối cùng nằm trong cùng database.

## 2. Tìm theo định danh: lấy đúng một aggregate cụ thể

Định danh (identity) trả lời câu hỏi “đây là aggregate nào?”. Trong một bounded context, mỗi aggregate root có một định danh ổn định để phân biệt nó với những aggregate khác.

Ví dụ:

```java
public record OrderId(UUID value) {
    public OrderId {
        Objects.requireNonNull(value, "value");
    }
}

public interface OrderRepository {
    Optional<Order> findById(OrderId id);
}
```

`OrderId` thể hiện rõ kiểu định danh mà Repository cần. Nó ngăn việc truyền nhầm `CustomerId`, `PaymentId` hoặc một UUID không rõ ý nghĩa.

### Định danh không phải tiêu chí tìm kiếm thông thường

Khi đã có `OrderId`, caller muốn lấy chính aggregate đó. Repository không nên âm thầm áp thêm điều kiện như “chỉ tìm đơn chưa hủy” trừ khi tên phương thức và use case thể hiện rõ ý nghĩa ấy.

Ví dụ, `findById(orderId)` tìm đơn theo identity. Quyền truy cập đơn của người gọi là một chính sách khác; application cần kiểm tra actor có được phép xem hoặc thao tác trên đơn hay không. Không nên làm cho `findById` có ngữ nghĩa thay đổi tùy người dùng mà không thể hiện điều đó trong hợp đồng.

### Identity và natural key

Một số khái niệm nghiệp vụ có mã tự nhiên như số đơn hàng, mã hợp đồng hoặc mã đăng ký. Chúng có thể được dùng để tìm aggregate nếu có quy tắc duy nhất rõ ràng:

```java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    Optional<Order> findByOrderNumber(OrderNumber orderNumber);
}
```

`OrderNumber` có thể là mã người dùng nhìn thấy và tra cứu. Nó không nhất thiết thay thế `OrderId` nội bộ. Nếu số đơn có thể thay đổi, có thể trùng giữa các chi nhánh hoặc chỉ duy nhất trong một phạm vi, kiểu và hợp đồng cần thể hiện phạm vi đó, ví dụ `OrderNumber` kèm `SalesChannelId`.

Không nên dùng email, số điện thoại hoặc tên người làm identity nếu nghiệp vụ cho phép chúng thay đổi, được dùng chung hoặc được tái cấp. Một natural key chỉ phù hợp khi quy tắc duy nhất và vòng đời của nó đã được xác định.

### Hợp đồng tìm theo định danh

Một phương thức tìm theo định danh thường có các đặc điểm:

- Nhận một kiểu ID rõ ràng, không nhận một chuỗi tùy ý nếu có thể dùng value object.
- Trả về tối đa một aggregate.
- Diễn đạt rõ trường hợp không tồn tại.
- Không để lộ cách lưu trữ hoặc kiểu ID của database.
- Không tự thực hiện một hành vi nghiệp vụ như xác nhận, hủy hoặc thanh toán.

## 3. Tìm theo tiêu chí nghiệp vụ: tìm aggregate thỏa một điều kiện có ý nghĩa

Không phải lúc nào caller cũng biết ID. Có lúc use case cần tìm aggregate theo một điều kiện được diễn đạt bằng nghiệp vụ.

Ví dụ:

- Tìm hợp đồng đang có hiệu lực của khách hàng tại một thời điểm.
- Tìm đăng ký còn đủ điều kiện gia hạn.
- Tìm khoản giữ hàng đã hết hạn để giải phóng.
- Tìm đơn đang chờ thanh toán theo số đơn do khách cung cấp.
- Tìm chính sách giá áp dụng cho một nhóm khách hàng và một ngày bán.

Các phương thức nên thể hiện ý nghĩa điều kiện thay vì tên cột hoặc cấu trúc SQL:

```java
public interface SubscriptionRepository {
    Optional<Subscription> findCurrentFor(
        CustomerId customerId,
        ProductId productId,
        Instant at
    );
}
```

Tên `findCurrentFor` nói rõ mục đích nghiệp vụ: tìm đăng ký hiện hành cho khách hàng và sản phẩm tại một thời điểm. Người gọi không cần biết adapter lọc theo cột `valid_from`, `valid_to` hay `status_code`.

### Tiêu chí nghiệp vụ cần có định nghĩa chính xác

Một cụm từ như “đơn gần đây”, “khách hàng đang hoạt động” hoặc “hợp đồng hợp lệ” có thể được hiểu khác nhau giữa các nhóm. Trước khi đưa vào tên phương thức hoặc kiểu tiêu chí, hãy xác nhận:

- “Hiện hành” được tính theo ngày bắt đầu và ngày kết thúc nào?
- Mốc kết thúc có được bao gồm không?
- “Đang hoạt động” có phụ thuộc vào lần giao dịch gần nhất hay trạng thái tài khoản?
- “Đủ điều kiện gia hạn” có yêu cầu thanh toán đầy đủ hoặc không có tranh chấp không?
- Nếu có nhiều kết quả phù hợp, nghiệp vụ cho phép nhiều hay yêu cầu duy nhất?

Hợp đồng Repository chỉ tốt khi thuật ngữ trong nó có nghĩa ổn định trong bounded context.

## 4. Chọn kiểu kết quả theo số lượng và tính duy nhất

Kiểu trả về phải thể hiện cardinality (số lượng kết quả) mà nghiệp vụ mong đợi. Không nên dùng một `List` cho mọi trường hợp hoặc lấy phần tử đầu tiên để che giấu dữ liệu trùng.

| Số kết quả kỳ vọng | Kiểu kết quả thường phù hợp | Ý nghĩa |
| --- | --- | --- |
| Không hoặc đúng một | `Optional<T>` | Không có kết quả là tình huống có thể xảy ra; nếu có thì chỉ có một. |
| Chính xác một theo hợp đồng | `T` hoặc một kết quả bắt buộc | Caller kỳ vọng tồn tại; cần quy ước rõ cách biểu diễn khi thiếu. |
| Không hoặc nhiều | `List<T>` | Có thể không có phần tử hoặc có nhiều kết quả. |
| Nhiều kết quả, tập dữ liệu lớn | `Page<T>`, `Slice<T>` hoặc kiểu cursor riêng | Có phân trang, giới hạn hoặc tiếp tục đọc. |
| Chỉ cần biết có tồn tại | `boolean` | Không cần tải aggregate nếu chỉ kiểm tra sự tồn tại. |

### Dùng Optional cho kết quả không hoặc một

```java
Optional<Order> findByOrderNumber(OrderNumber number);
```

`Optional.empty()` thể hiện không tìm thấy. Application service quyết định điều đó có phải lỗi use case hay không:

```java
Order order = orders.findByOrderNumber(number)
    .orElseThrow(() -> new OrderNotFoundException(number));
```

Repository không nhất thiết phải ném `OrderNotFoundException` cho mọi trường hợp. Cùng một kết quả “không có” có thể là bình thường với một use case kiểm tra trước, nhưng là lỗi với use case cần thao tác trên đơn đã tồn tại.

### Khi hợp đồng yêu cầu đúng một kết quả

Nếu một customer chỉ được có một subscription hiện hành cho một product tại một thời điểm, `findCurrentFor(...)` có thể trả `Optional<Subscription>`. Nếu không có thì có thể tạo mới; nếu có nhiều hơn một thì dữ liệu vi phạm invariant về tính duy nhất.

Adapter không nên gọi `findFirst()` hoặc `LIMIT 1` rồi giả vờ kết quả duy nhất. Nếu dữ liệu trùng là bất khả thi theo nghiệp vụ, cần phát hiện và báo lỗi toàn vẹn dữ liệu. Cơ sở dữ liệu nên có unique constraint phù hợp để bảo vệ trước cập nhật đồng thời.

### Khi có nhiều kết quả

Nếu nghiệp vụ cho phép nhiều kết quả, trả `List<T>` hoặc kiểu phân trang phù hợp. Nếu caller cần thứ tự, hợp đồng phải định nghĩa thứ tự đó. Không nên dựa vào thứ tự mặc định của database.

## 5. Biểu diễn tiêu chí tìm kiếm bằng kiểu có ý nghĩa

Khi một truy vấn có nhiều điều kiện, truyền nhiều tham số rời rạc có thể làm chữ ký dài và dễ nhầm thứ tự:

```java
findOrders(customerId, from, to, statuses, channel, page, size, sort);
```

Một kiểu tiêu chí có thể nhóm các điều kiện liên quan:

```java
public record SubscriptionLookup(
    CustomerId customerId,
    ProductId productId,
    Instant effectiveAt
) {
    public SubscriptionLookup {
        Objects.requireNonNull(customerId, "customerId");
        Objects.requireNonNull(productId, "productId");
        Objects.requireNonNull(effectiveAt, "effectiveAt");
    }
}

public interface SubscriptionRepository {
    Optional<Subscription> findCurrentFor(SubscriptionLookup lookup);
}
```

Kiểu `SubscriptionLookup` gom các giá trị tạo thành một câu hỏi nghiệp vụ có tên. Nó có thể kiểm tra dữ liệu bắt buộc và làm rõ ý nghĩa của mốc thời gian.

### Phân biệt tiêu chí miền với bộ lọc giao diện

Không phải mọi tập điều kiện tìm kiếm đều là khái niệm miền. Một màn hình quản trị có thể cho phép lọc theo nhiều cột tùy chọn, sắp xếp theo bất kỳ trường nào và phân trang. Đây thường là query model của application, không nhất thiết là hợp đồng Repository của aggregate.

Ví dụ:

```java
public record OrderSearch(
    CustomerId customerId,
    Set<OrderStatus> statuses,
    Instant createdFromInclusive,
    Instant createdToExclusive,
    int page,
    int pageSize
) {
    public OrderSearch {
        statuses = statuses == null ? Set.of() : Set.copyOf(statuses);
        if (page < 0 || pageSize < 1 || pageSize > 200) {
            throw new IllegalArgumentException("Invalid page request");
        }
        if (createdFromInclusive != null && createdToExclusive != null
                && !createdFromInclusive.isBefore(createdToExclusive)) {
            throw new IllegalArgumentException("Invalid creation-time range");
        }
    }
}
```

Kiểu này có thể phù hợp với `OrderQueries.search(...)` trả về `Page<OrderSummary>`. `page`, `pageSize` và cách sắp xếp là yêu cầu truy vấn của caller; chúng thường không thuộc mô hình miền của `Order`.

## 6. Thiết kế tên phương thức theo ngôn ngữ nghiệp vụ

Tên phương thức nên mô tả điều caller đang hỏi, không mô tả cấu trúc vật lý của database.

| Tên quá kỹ thuật hoặc mơ hồ | Tên thể hiện ý nghĩa rõ hơn |
| --- | --- |
| `findByStatusAndDate(...)` | `findOrdersAwaitingPaymentBefore(...)` |
| `getByCustomerAndProduct(...)` | `findCurrentFor(customerId, productId, at)` |
| `findActive(...)` | `findActiveSubscriptionsAt(customerId, at)` nếu “active” được định nghĩa rõ |
| `findByCode(...)` | `findByOrderNumber(orderNumber)` |
| `findByFlag(true)` | `findEligibleForRenewalAt(at)` |

Không cần biến tên phương thức thành một câu dài. Nếu điều kiện phức tạp, dùng một kiểu tiêu chí có tên rõ và tài liệu ngắn mô tả ngữ nghĩa.

### Tránh những tên không xác định nghĩa

Các tên `findLatest`, `findValid`, `findActive` hoặc `findEligible` cần trả lời: mới nhất theo thời gian nào, hợp lệ theo chính sách nào, hoạt động theo trạng thái nào và đủ điều kiện theo quy tắc nào? Nếu không định nghĩa được, tên đó dễ gây hiểu lầm.

### Không để tên phương thức phản ánh tên cột

Một method `findByStatusCodeAndValidToGreaterThan(...)` làm lộ cấu trúc persistence. Khi schema thay đổi, caller có thể phải đổi theo dù ý nghĩa nghiệp vụ không đổi. Hãy dùng tên miền như `findCurrentFor(...)` và để adapter ánh xạ sang cột.

## 7. Tiêu chí thời gian, trạng thái và chuẩn hóa

Tìm theo tiêu chí nghiệp vụ thường có những chi tiết biên dễ gây lỗi. Hợp đồng cần định nghĩa rõ thay vì để mỗi adapter tự suy đoán.

### Khoảng thời gian

Nên chọn quy ước khoảng thời gian rõ ràng. Ví dụ `[fromInclusive, toExclusive)` bao gồm thời điểm bắt đầu và loại trừ thời điểm kết thúc. Quy ước này giúp ghép hai khoảng liên tiếp mà không trùng ở ranh giới.

```java
public record TimeWindow(Instant fromInclusive, Instant toExclusive) {
    public TimeWindow {
        Objects.requireNonNull(fromInclusive, "fromInclusive");
        Objects.requireNonNull(toExclusive, "toExclusive");
        if (!fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException("Invalid time window");
        }
    }
}
```

Nếu nghiệp vụ làm việc theo ngày địa phương, cần xác định múi giờ hoặc `BusinessDate` tương ứng. Không nên chuyển ngày địa phương sang UTC một cách tùy tiện rồi thay đổi ý nghĩa “trong ngày”.

### Trạng thái và vòng đời

Một tiêu chí như “đơn chưa hoàn tất” có thể bao gồm nhiều trạng thái. Đội nên định nghĩa tập trạng thái theo vòng đời, thay vì chỉ tìm `status != COMPLETED` nếu các trạng thái như `CANCELLED`, `REJECTED` hoặc `EXPIRED` không được xem là đang xử lý.

Nếu nhóm trạng thái có ý nghĩa ổn định, có thể dùng value object hoặc specification có tên, chẳng hạn `OrderAwaitingFulfillment`. Nếu nó chỉ là lựa chọn lọc trên màn hình, có thể để ở query model.

### Chuẩn hóa khóa tìm kiếm

Nếu mã đơn không phân biệt hoa thường, cần chuẩn hóa nhất quán khi tạo `OrderNumber` và khi truy vấn. Nếu mã có số 0 đầu, không được parse thành số nguyên làm mất số 0. Nếu tìm theo tên, cần thống nhất có phân biệt dấu, chữ hoa/thường và khoảng trắng hay không.

Những quy tắc này nên được quyết định trong bounded context và phản ánh trong kiểu dữ liệu hoặc hợp đồng, không rải rác trong các câu SQL.

## 8. Specification: biểu diễn một tiêu chí miền có thể tái sử dụng

Khi một điều kiện nghiệp vụ được dùng ở nhiều nơi, có thể cân nhắc Specification Pattern. Specification mô tả một điều kiện có tên và có thể được đánh giá trên đối tượng miền hoặc được adapter chuyển thành truy vấn phù hợp.

Ví dụ về ý nghĩa:

```java
public interface Specification<T> {
    boolean isSatisfiedBy(T candidate);
}

public final class EligibleForRenewal
        implements Specification<Subscription> {
    private final Instant renewalDate;

    public EligibleForRenewal(Instant renewalDate) {
        this.renewalDate = Objects.requireNonNull(renewalDate);
    }

    @Override
    public boolean isSatisfiedBy(Subscription subscription) {
        return subscription.canRenewAt(renewalDate);
    }
}
```

Đây là specification có thể đánh giá trên một đối tượng đã tải. Nếu Repository cần thực thi điều kiện ở database để tránh tải quá nhiều aggregate, adapter có thể ánh xạ specification sang truy vấn tương ứng. Việc ánh xạ phải giữ cùng ngữ nghĩa với `isSatisfiedBy`.

Một interface chỉ có `isSatisfiedBy(T)` không cung cấp đủ thông tin để tự động dịch mọi điều kiện thành SQL. Adapter chỉ có thể tối ưu nếu nó nhận diện được kiểu specification cụ thể hoặc có một biểu diễn điều kiện (expression/AST) mà nó hiểu. Nếu không có cơ chế đó, phải tải đối tượng rồi đánh giá trong bộ nhớ, điều này có thể tốn kém. Với truy vấn database thực tế, method mang tên nghiệp vụ hoặc query criteria có cấu trúc rõ thường đơn giản và an toàn hơn.

Không nên đưa `JpaSpecification`, `Predicate<OrderEntity>`, `CriteriaBuilder`, biểu thức SQL hoặc một query DSL của ORM vào domain contract. Đó là chi tiết hạ tầng. Nếu specification chỉ là bộ lọc động cho một màn hình, nó thường thuộc application/query layer.

### Không lạm dụng Specification tổng quát

Một interface `findAll(Specification<T> specification)` có vẻ linh hoạt nhưng có thể khiến hợp đồng không còn diễn đạt nghiệp vụ. Nếu caller có thể kết hợp tùy ý mọi field, Repository trở thành một query engine và khó biết tiêu chí nào có ý nghĩa miền.

Hãy ưu tiên các method có tên miền rõ. Dùng specification khi điều kiện thực sự là khái niệm có thể tái sử dụng và có định nghĩa ổn định.

## 9. Tách Repository aggregate và query service

Một hệ thống thường có cả thao tác tải aggregate để thay đổi và truy vấn dữ liệu để hiển thị. Hai mục tiêu này có thể cần hợp đồng khác nhau.

```java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    Optional<Order> findByOrderNumber(OrderNumber number);
    void save(Order order);
}

public interface OrderQueries {
    Page<OrderSummary> search(OrderSearch criteria);
    Optional<OrderDetailsView> findDetails(OrderId id);
}
```

`OrderRepository` trả aggregate để thực hiện hành vi miền. `OrderQueries` trả projection phục vụ đọc, có thể kết hợp nhiều bảng hoặc bounded context, có phân trang và sắp xếp.

### Vì sao query service có thể tốt hơn?

- Không phải tải toàn bộ aggregate chỉ để hiển thị vài trường.
- Có thể tối ưu SQL cho màn hình, báo cáo và tìm kiếm toàn văn.
- Có thể trả DTO/read model thay vì domain entity.
- Không làm Repository của aggregate chứa hàng chục method truy vấn không liên quan đến thay đổi nghiệp vụ.
- Có thể dùng CQRS ở mức đơn giản mà không bắt buộc tách database hoặc dùng Event Sourcing.

Nếu query cần dữ liệu từ nhiều bounded context, read model có thể được cập nhật từ integration event hoặc các nguồn dữ liệu được phép. Không nên để Repository của một context truy cập trực tiếp bảng nội bộ của context khác rồi gọi đó là một truy vấn miền.

### Phân trang và sắp xếp

Với tập dữ liệu lớn, nên giới hạn số lượng trả về. `Page` có tổng số phần tử nhưng có thể yêu cầu truy vấn count bổ sung; `Slice` chỉ cần biết còn trang tiếp theo hay không; cursor/keyset pagination có thể ổn định và hiệu quả hơn trên tập dữ liệu thay đổi lớn.

Thứ tự sắp xếp cần xác định rõ. Nếu nhiều bản ghi có cùng `createdAt`, nên thêm khóa phụ ổn định như ID để tránh phần tử bị lặp hoặc bỏ sót giữa các trang. Những chi tiết này thường thuộc query contract, không phải invariant của aggregate.

Nếu muốn query port không phụ thuộc Spring Data, có thể định nghĩa kiểu `PageResult<T>` hoặc `SliceResult<T>` của ứng dụng thay vì trả trực tiếp `Page`/`Pageable` từ framework. Adapter chuyển đổi kiểu phân trang kỹ thuật sang kiểu kết quả mà application sở hữu.

## 10. Không để lộ chi tiết persistence trong hợp đồng

Repository contract nên dùng kiểu và khái niệm của bounded context. Tránh các kiểu chỉ có ý nghĩa với một công nghệ:

```java
// Không nên đưa các chi tiết này vào domain contract
Page<OrderEntity> findAll(Pageable pageable);
List<OrderEntity> findByCriteria(CriteriaBuilder builder);
Stream<OrderEntity> executeNativeQuery(String sql);
```

Những kiểu này làm application hoặc domain phụ thuộc vào ORM, entity persistence và cấu trúc SQL. Nếu đổi công nghệ, nhiều lớp phía trên có thể phải thay đổi theo.

Hãy chuyển thành hợp đồng phù hợp với trách nhiệm:

```java
public interface OrderQueries {
    Page<OrderSummary> search(OrderSearch criteria);
}
```

Adapter có thể dùng Spring Data `Pageable`, JPA Criteria hoặc SQL nội bộ, rồi chuyển kết quả sang `Page<OrderSummary>` hoặc kiểu phân trang do ứng dụng định nghĩa. Caller chỉ thấy hợp đồng ổn định của mình.

### Tránh trả persistence entity

Không nên trả `OrderJpaEntity` từ Repository miền. Persistence entity có thể chứa lazy proxy, annotation, quan hệ hai chiều và trạng thái ORM. Hãy trả aggregate domain đã được khôi phục hợp lệ hoặc projection phù hợp.

## 11. Xử lý không tìm thấy, dữ liệu trùng và tiêu chí không hợp lệ

Các trường hợp này cần được phân biệt:

- **Không có kết quả:** tiêu chí hợp lệ nhưng không có aggregate phù hợp.
- **Tiêu chí sai:** tham số không đáp ứng định nghĩa, ví dụ khoảng ngày đảo ngược hoặc ID null.
- **Dữ liệu vi phạm tính duy nhất:** hợp đồng kỳ vọng tối đa một kết quả nhưng persistence có nhiều bản ghi.
- **Lỗi hạ tầng:** database không sẵn sàng hoặc truy vấn timeout.
- **Không đủ quyền:** caller không được phép truy cập aggregate dù nó tồn tại.

Không nên gom tất cả thành `Optional.empty()` hoặc `null`. `Optional.empty()` thường phù hợp cho trường hợp không có kết quả hợp lệ; dữ liệu trùng hoặc lỗi hạ tầng cần được biểu diễn riêng để không che giấu lỗi hệ thống.

### Ai chịu trách nhiệm báo lỗi không tìm thấy?

Repository có thể trả `Optional.empty()`. Application service biết use case cần gì:

- Với `GetOrderDetails`, không có đơn có thể trở thành `OrderNotFound`.
- Với `CreateSubscription`, không có subscription hiện tại có thể là điều kiện để tạo mới.
- Với `CheckExistingRegistration`, không có kết quả có thể chỉ là `false`.

Đừng ép Repository quyết định ngữ nghĩa HTTP hoặc thông báo người dùng. Controller có thể ánh xạ lỗi use case thành HTTP 404, 409 hoặc mã phù hợp.

### existsBy không thay thế ràng buộc duy nhất

Một luồng “kiểm tra chưa tồn tại rồi tạo mới” có thể gặp race condition: hai request cùng kiểm tra thấy chưa có, sau đó cùng tạo. `existsBy...` chỉ hữu ích để phản hồi sớm; nó không bảo vệ tính duy nhất dưới cập nhật đồng thời.

Nếu nghiệp vụ yêu cầu duy nhất, cần ràng buộc unique ở persistence và xử lý xung đột khi ghi. Nếu có thể, định danh hoặc reservation nên được tạo theo cách an toàn với cạnh tranh.

## 12. Tìm theo tiêu chí qua bounded context

Repository thuộc một bounded context và chỉ nên truy cập mô hình mà context đó sở hữu. Nếu use case cần tìm dữ liệu do context khác sở hữu, hãy dùng hợp đồng tích hợp, API hoặc read model được phép.

Ví dụ, `OrderRepository` không nên tự join trực tiếp bảng `BillingAccount` nội bộ của Kế toán chỉ để tìm các đơn có tài khoản thanh toán đang hoạt động. Tùy yêu cầu, có thể:

- Gọi `BillingAccountProvider` hoặc application port để lấy trạng thái có thẩm quyền.
- Tiêu thụ integration event để duy trì một projection cục bộ.
- Tạo query service kết hợp dữ liệu đã được công bố và chấp nhận độ trễ tương ứng.

Nếu cần quyết định có hậu quả nghiệp vụ ngay lập tức, không nên dùng một projection có thể trễ mà không có bước xác nhận với context sở hữu.

## 13. Ví dụ xuyên suốt: tìm subscription hiện hành và tìm đơn để hiển thị

Giả sử hệ thống quản lý thuê bao. Một khách hàng có thể có nhiều subscription theo sản phẩm, nhưng chỉ được có tối đa một subscription hiện hành cho mỗi cặp khách hàng/sản phẩm tại một thời điểm.

### Tìm subscription cho một quyết định nghiệp vụ

Use case gia hạn cần tìm subscription hiện hành tại thời điểm xử lý:

```java
public interface SubscriptionRepository {
    Optional<Subscription> findCurrentFor(
        CustomerId customerId,
        ProductId productId,
        Instant at
    );
}
```

Hợp đồng có nghĩa:

- Trả `Optional.empty()` nếu không có subscription hiện hành.
- Trả một aggregate nếu có đúng một.
- Nếu có nhiều aggregate cùng thỏa điều kiện duy nhất, đó là lỗi toàn vẹn dữ liệu cần phát hiện.
- `at` là thời điểm nghiệp vụ được dùng để đánh giá hiệu lực, không phải thời điểm database tự chọn.

Adapter có thể truy vấn theo `valid_from <= at` và `valid_to > at`, nhưng cách lưu cột không xuất hiện trong hợp đồng. Nếu quy tắc bao gồm ngày kết thúc, biểu thức và tên tham số phải được điều chỉnh tương ứng.

Application service có thể dùng kết quả:

```java
Subscription subscription = subscriptions
    .findCurrentFor(customerId, productId, decisionTime)
    .orElseThrow(() -> new NoCurrentSubscriptionException(customerId, productId));

subscription.requestRenewal(decisionTime);
subscriptions.save(subscription);
```

Aggregate `Subscription` tự kiểm tra có thể gia hạn hay không. Repository chỉ tìm đúng aggregate theo tiêu chí.

### Tìm đơn cho màn hình quản trị

Màn hình quản trị cần tìm các đơn của một khách hàng, lọc theo nhiều trạng thái, khoảng ngày và phân trang. Đây là query service:

```java
public interface OrderQueries {
    Page<OrderSummary> search(OrderSearch criteria);
}
```

`OrderSummary` chỉ chứa dữ liệu cần hiển thị. Adapter có thể tối ưu truy vấn bằng index, join và projection. Kết quả không được dùng để sửa trạng thái đơn trực tiếp; nếu nhân viên chọn xác nhận một đơn, application cần tải aggregate qua `OrderRepository` và gọi `order.confirm()`.

## 14. Kiểm thử hợp đồng Repository

Repository interface cần được kiểm tra thông qua các test cho adapter và use case.

### Kiểm thử adapter

- Tìm đúng aggregate theo ID.
- Trả empty khi không tồn tại.
- Tìm theo natural key đã chuẩn hóa.
- Áp dụng đúng biên thời gian và trạng thái.
- Phát hiện dữ liệu trùng khi hợp đồng kỳ vọng duy nhất.
- Khôi phục aggregate với invariant hợp lệ.
- Lưu aggregate và đọc lại được các thay đổi.
- Không trả persistence entity hoặc lazy proxy ra ngoài adapter.

### Kiểm thử application

- Không tìm thấy được chuyển thành kết quả use case phù hợp.
- Khi tìm thấy, use case gọi đúng hành vi aggregate.
- Caller không có quyền không thể thao tác chỉ bằng cách biết ID.
- Kết quả tìm nhiều phần tử có thứ tự và phân trang đúng theo hợp đồng.
- Lỗi persistence hoặc timeout được phân biệt với không tìm thấy.

### Kiểm thử tính duy nhất dưới cạnh tranh

Với tiêu chí cần duy nhất, nên có kiểm thử tích hợp xác nhận unique constraint thực sự bảo vệ dữ liệu khi hai thao tác tạo/cập nhật đồng thời. Một unit test cho `existsBy...` không thể chứng minh điều đó.

## 15. Những sai lầm thường gặp

- **Một method `findByCriteria` chung cho mọi thứ:** không nói tiêu chí có ý nghĩa gì và biến Repository thành query engine.
- **Dùng chuỗi hoặc UUID không kiểu cho mọi ID:** dễ truyền nhầm định danh giữa các aggregate.
- **Trả `null`:** caller phải tự đoán trường hợp không có kết quả và dễ phát sinh NullPointerException.
- **Trả List dù chỉ được phép có một kết quả:** dữ liệu trùng bị che giấu hoặc caller tùy tiện lấy phần tử đầu.
- **Dùng `findFirst` để che lỗi duy nhất:** thứ tự database không bảo đảm và vi phạm dữ liệu không được phát hiện.
- **Tên method dựa trên tên cột:** hợp đồng rò rỉ schema và khó thay đổi persistence.
- **Đưa `Pageable`, JPA Specification hoặc SQL vào domain:** tầng nghiệp vụ phụ thuộc framework.
- **Dùng Repository aggregate cho mọi báo cáo:** tải quá nhiều object và làm interface phình to.
- **Trả persistence entity:** lazy loading và chi tiết ORM lan ra ngoài infrastructure.
- **Dùng `existsBy` để bảo vệ duy nhất:** có race condition khi nhiều request cùng tạo.
- **Không định nghĩa biên thời gian và timezone:** kết quả khác nhau giữa các adapter hoặc môi trường.
- **Truy vấn trực tiếp dữ liệu context khác:** phá quyền sở hữu và làm mô hình phụ thuộc cấu trúc nội bộ.
- **Nhầm không tìm thấy với không đủ quyền:** có thể làm lộ sự tồn tại của dữ liệu hoặc tạo lỗi bảo mật.

## 16. Quy trình thiết kế một hợp đồng tìm kiếm

Khi cần thêm một phương thức tìm kiếm, hãy thực hiện theo các bước:

1. **Xác định mục tiêu caller:** cần tải aggregate để thay đổi hay chỉ cần dữ liệu để đọc?
2. **Phân loại câu hỏi:** tìm đúng một aggregate theo identity, tìm theo natural key, tìm theo tiêu chí nghiệp vụ hay truy vấn hiển thị?
3. **Xác nhận ngữ nghĩa:** định nghĩa thuật ngữ, phạm vi, thời điểm, trạng thái và quy tắc chuẩn hóa.
4. **Xác định cardinality:** không/có một, chính xác một, nhiều hay chỉ cần biết có tồn tại.
5. **Chọn kiểu tham số:** ID/value object, tham số miền hoặc criteria object có tên.
6. **Chọn kiểu kết quả:** `Optional`, aggregate, list, page, projection hoặc boolean theo đúng nhu cầu.
7. **Đặt tên theo nghiệp vụ:** không đưa tên cột, bảng hoặc câu SQL vào hợp đồng.
8. **Xác định quyền sở hữu:** dữ liệu thuộc bounded context nào và nguồn nào có thẩm quyền?
9. **Định nghĩa lỗi:** không tìm thấy, tiêu chí sai, dữ liệu trùng, không đủ quyền và lỗi hạ tầng phải phân biệt.
10. **Kiểm tra tính duy nhất và cạnh tranh:** dùng constraint hoặc cơ chế ghi an toàn nếu nghiệp vụ yêu cầu.
11. **Tách query phức tạp:** dùng query service/read model khi cần projection, join, phân trang hoặc báo cáo.
12. **Viết test hợp đồng:** xác nhận adapter giữ đúng ý nghĩa và use case xử lý đúng kết quả.

## Checklist rà soát

- [ ] Repository được thiết kế quanh aggregate root.
- [ ] Tìm theo ID dùng kiểu định danh rõ ràng.
- [ ] Natural key có quy tắc duy nhất và phạm vi rõ.
- [ ] Tiêu chí tìm kiếm có định nghĩa nghiệp vụ được xác nhận.
- [ ] Kiểu trả về phản ánh đúng cardinality.
- [ ] Không dùng `null` hoặc `findFirst` để che trường hợp bất thường.
- [ ] Tên phương thức diễn đạt ý nghĩa miền, không lộ tên cột.
- [ ] Criteria object bất biến và kiểm tra các điều kiện cấu trúc cần thiết.
- [ ] Biên thời gian, trạng thái, timezone và chuẩn hóa đã rõ.
- [ ] Query báo cáo/hiển thị được tách khỏi Repository aggregate khi phù hợp.
- [ ] Không đưa kiểu ORM, SQL hoặc persistence entity vào hợp đồng.
- [ ] Dữ liệu của bounded context khác được truy cập qua hợp đồng được phép.
- [ ] Quy tắc duy nhất được bảo vệ ở persistence khi có cập nhật đồng thời.
- [ ] Không tìm thấy, lỗi dữ liệu, quyền truy cập và lỗi hạ tầng được phân biệt.
- [ ] Adapter và use case có kiểm thử phù hợp.

## Kết luận

Hợp đồng Repository nên diễn đạt rõ hai câu hỏi: cần lấy aggregate nào theo định danh, hay cần aggregate nào thỏa một tiêu chí nghiệp vụ đã được định nghĩa? Tìm theo identity thường trả về không hoặc một aggregate; tìm theo tiêu chí phải thể hiện rõ cardinality, thời điểm, trạng thái và quy tắc duy nhất. Khi nhu cầu chủ yếu là hiển thị, tìm kiếm linh hoạt hoặc báo cáo, query service/read model giúp giữ Repository tập trung vào aggregate root. Đặt tên theo ngôn ngữ miền, chọn kiểu kết quả chính xác và giữ chi tiết persistence trong adapter sẽ giúp hợp đồng ổn định, dễ kiểm thử và bảo vệ ranh giới của bounded context.
