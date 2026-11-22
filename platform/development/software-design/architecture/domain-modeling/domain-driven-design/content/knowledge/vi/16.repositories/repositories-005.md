# Quyền sở hữu giao dịch và giới hạn trách nhiệm của repository

Trong một use case chuyển tiền, ứng dụng cần tải tài khoản nguồn và tài khoản đích, kiểm tra quy tắc chuyển tiền, ghi nợ một tài khoản và ghi có tài khoản còn lại. Nếu việc ghi nợ thành công nhưng ghi có thất bại, hệ thống không được để một nửa giao dịch được lưu. Hai thay đổi phải cùng commit hoặc cùng rollback theo yêu cầu nghiệp vụ.

Repository giúp domain model truy xuất và lưu Aggregate thông qua một abstraction có ngôn ngữ gần với domain. Nhưng repository không tự quyết định toàn bộ ranh giới của một use case. Một repository thường tập trung vào việc tải và lưu một loại Aggregate Root; transaction có thể bao trùm nhiều repository và nhiều thao tác domain. Vì vậy, cần phân biệt rõ **trách nhiệm truy xuất dữ liệu của repository** với **trách nhiệm điều phối transaction của application layer**.

Trong Domain-Driven Design (DDD), repository thường được mô tả như một tập hợp đối tượng domain có thể được truy xuất theo cách gần giống collection. Application Service điều phối use case, gọi các repository cần thiết và xác định transaction boundary. Unit of Work hoặc transaction manager phối hợp việc commit/rollback ở tầng persistence. Các repository tham gia vào cùng Unit of Work thay vì tự ý commit độc lập sau mỗi lần lưu.

Sau bài học này, bạn có thể:

- Giải thích repository sở hữu trách nhiệm nào và giới hạn ở đâu.
- Phân biệt Repository, DAO, Unit of Work và Transaction Manager.
- Xác định transaction boundary theo use case và consistency requirement.
- Dùng nhiều repository trong một transaction khi nghiệp vụ cần atomicity.
- Nhận diện các thao tác có thể phá vỡ Aggregate invariant hoặc transaction.
- Thiết kế repository cho Aggregate Root, query model và tích hợp giữa Bounded Context.

## 1. Repository có trách nhiệm gì?

Repository cung cấp cách truy xuất Aggregate theo ngôn ngữ domain mà không buộc phần còn lại của mô hình phải biết chi tiết lưu trữ. Một repository thường có các trách nhiệm:

- Tìm và nạp Aggregate Root theo định danh hoặc tiêu chí domain cần thiết.
- Khôi phục Aggregate cùng các thành phần thuộc ranh giới của nó theo mapping đã chọn.
- Đưa Aggregate mới hoặc Aggregate đã thay đổi vào cơ chế persistence.
- Che giấu chi tiết database, ORM, SQL, mapping và cách truy vấn.
- Thể hiện các thao tác truy xuất có ý nghĩa đối với use case/domain.

Ví dụ:

```java
public interface AccountRepository {
    Optional<Account> findById(AccountId id);
    void add(Account account);
    void save(Account account);
}
```

Interface này cho biết ứng dụng có thể tìm, thêm và lưu `Account`. Nó không cho biết dữ liệu nằm trong PostgreSQL, document store hay một cơ chế persistence khác.

Repository thường được định nghĩa cho Aggregate Root. Nếu `OrderLine` chỉ được truy cập và thay đổi thông qua `Order`, thông thường ta dùng `OrderRepository`, không tạo `OrderLineRepository` để code bên ngoài sửa dòng hàng độc lập. Quy tắc này giúp giữ Aggregate Root là cổng vào của thay đổi và bảo vệ invariant.

### Repository không phải bản sao của mọi bảng

Một database có thể có các bảng `orders`, `order_lines`, `order_addresses`, `order_events`. Không cần tạo một repository cho mỗi bảng. Repository tập trung vào Aggregate mà domain cần làm việc như một đơn vị.

Một lần gọi `orderRepository.findById(orderId)` có thể đọc nhiều bảng để tái dựng một `Order` Aggregate. Chi tiết đó thuộc persistence adapter. Domain caller chỉ làm việc với Order và hành vi của nó.

## 2. Repository không đồng nghĩa với DAO

Repository và DAO (*Data Access Object*) đều giúp tách phần truy cập dữ liệu, nhưng thường có trọng tâm khác nhau.

| Tiêu chí | Repository trong DDD | DAO |
|---|---|---|
| Ngôn ngữ | Domain và Aggregate | Cấu trúc lưu trữ hoặc thao tác dữ liệu |
| Đơn vị chính | Thường là Aggregate Root | Có thể là bảng, view hoặc truy vấn |
| Mục tiêu | Cung cấp cách lấy/lưu đối tượng domain | Đóng gói thao tác persistence |
| API | `findById(OrderId)`, `save(Order)` | `selectOrderRow`, `updateOrderStatus` |
| Người sử dụng | Application/domain layer | Thường là persistence adapter hoặc application layer |

DAO vẫn hữu ích bên trong infrastructure. Một repository adapter có thể dùng một hoặc nhiều DAO để đọc và ghi dữ liệu. Điều quan trọng là không để domain model phụ thuộc vào DAO mang cấu trúc bảng hoặc SQL.

Ví dụ:

```text
Application Service
       |
       v
OrderRepository (domain-facing port)
       |
       v
JpaOrderRepository (adapter)
       |
       +--> OrderDao
       +--> OrderLineDao
       +--> AddressDao
       |
       v
Database
```

Sơ đồ minh họa cách tổ chức có thể dùng. Một dự án nhỏ có thể triển khai repository bằng một class JPA trực tiếp mà không cần nhiều DAO riêng. Không nên tạo thêm lớp nếu chúng không giúp tách trách nhiệm hoặc làm rõ cách truy cập.

## 3. Repository không sở hữu transaction của toàn use case

Một repository thường không nên tự mở transaction, commit hoặc rollback sau mỗi phương thức `save()`. Nếu mỗi repository tự commit, một use case dùng hai repository có thể bị lưu một phần.

Ví dụ không an toàn:

Giả sử mỗi lần `save()` bên dưới tự mở và commit một transaction riêng:

```java
public void transfer(Account source, Account destination, Money amount) {
    source.debit(amount);
    accountRepository.save(source);       // Tự commit

    destination.credit(amount);
    accountRepository.save(destination);  // Tự commit riêng
}
```

Nếu lần lưu thứ hai thất bại, tài khoản nguồn đã bị ghi nợ nhưng tài khoản đích chưa được ghi có. Đây là trạng thái không phù hợp với yêu cầu chuyển tiền nguyên tử.

Một cách tổ chức phù hợp hơn là để Application Service xác định transaction cho use case:

```java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void transfer(TransferMoneyCommand command) {
    Account source = accounts.findById(command.sourceId())
        .orElseThrow(AccountNotFoundException::new);
    Account destination = accounts.findById(command.destinationId())
        .orElseThrow(AccountNotFoundException::new);

    fundsTransferService.transfer(source, destination, command.amount());

    accounts.save(source);
    accounts.save(destination);
}
```

Trong ví dụ này, hai lần `save()` tham gia cùng transaction. Nếu một thao tác persistence thất bại và transaction bị rollback, cả hai thay đổi được rollback. `@Transactional` là ví dụ theo Spring; framework khác có thể dùng Unit of Work hoặc transaction boundary riêng.

### Ai thực sự commit?

Application Service quyết định *ranh giới use case* và khai báo nơi transaction bắt đầu/kết thúc. Transaction manager hoặc Unit of Work của infrastructure thực hiện commit/rollback với database. Repository tham gia vào Unit of Work đó để nạp và lưu Aggregate.

Vì vậy, nói “Application Service sở hữu transaction” là nói về trách nhiệm điều phối và xác định boundary. Nó không có nghĩa Application Service tự triển khai giao thức commit của database.

## 4. Unit of Work phối hợp nhiều repository

Unit of Work là cơ chế theo dõi những thay đổi cần được ghi trong một đơn vị công việc và phối hợp commit/rollback chúng trong cùng transaction.

Trong một ORM như Hibernate, persistence context có thể hoạt động như một Unit of Work:

- Entity được nạp vào persistence context.
- ORM theo dõi các thay đổi (dirty checking).
- Khi flush, ORM phát các câu lệnh insert/update/delete cần thiết.
- Transaction manager commit hoặc rollback tất cả thay đổi thuộc transaction.

Ví dụ, một use case có thể cập nhật Order và tạo một Invoice trong cùng database transaction. `OrderRepository` và `InvoiceRepository` vẫn có trách nhiệm riêng, nhưng các thao tác được phối hợp bởi một Unit of Work.

```java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void issueInvoice(OrderId orderId) {
    Order order = orders.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);

    order.ensureCanBeInvoiced();
    Invoice invoice = Invoice.issueFrom(order);
    order.markInvoiced(invoice.id());

    orders.save(order);
    invoices.add(invoice);
}
```

Nếu yêu cầu nghiệp vụ là Order được đánh dấu đã xuất hóa đơn khi và chỉ khi Invoice được tạo thành công, một transaction chung có thể phù hợp khi cả hai Aggregate được lưu trong cùng transactional resource. Nếu hai phần thuộc hai database hoặc hai service, transaction cục bộ không đủ; cần quy trình phối hợp khác.

### Repository có thể gọi `flush()` không?

Persistence adapter có thể cần flush trong một số tình huống kỹ thuật, nhưng flush không đồng nghĩa commit. Flush gửi các thay đổi đang chờ xuống database trong transaction hiện tại; transaction vẫn có thể rollback sau đó.

Không nên nhầm:

- `save()`: đưa thay đổi vào cơ chế persistence theo contract của adapter.
- `flush()`: đẩy thay đổi đang chờ xuống database trong transaction hiện tại.
- `commit()`: xác nhận transaction hoàn tất.

Một repository có thể cung cấp phương thức flush nếu application layer thật sự cần điều khiển thời điểm đồng bộ, nhưng API domain không nên biến flush thành thao tác nghiệp vụ. Phần lớn use case có thể để Unit of Work/transaction manager flush theo cơ chế mặc định.

## 5. Một transaction có thể dùng nhiều repository

Transaction boundary nên được xác định theo use case và consistency requirement, không theo số lượng repository.

Ví dụ một use case “xác nhận đơn và tạo hóa đơn” có thể cần:

1. Nạp Order qua `OrderRepository`.
2. Nạp chính sách thuế hoặc thông tin cần thiết.
3. Gọi hành vi domain để xác nhận Order.
4. Tạo Invoice Aggregate.
5. Lưu Order và Invoice trong cùng transaction nếu chúng cùng transactional resource và cần atomicity.

Việc dùng hai repository không có nghĩa phải có hai transaction. Ngược lại, dùng một repository cũng không có nghĩa mọi phương thức của nó phải nằm trong một transaction riêng.

### Ví dụ ranh giới use case

```text
Use case: ConfirmOrderAndIssueInvoice

BEGIN TRANSACTION
  OrderRepository.findById()
  Order.confirm()
  Invoice.issueFrom(order)
  OrderRepository.save(order)
  InvoiceRepository.add(invoice)
COMMIT
```

Nếu bất kỳ thao tác persistence nào thất bại trước commit, transaction rollback. Nếu event cần công bố sau commit, hãy ghi outbox record trong cùng transaction và để publisher gửi sau đó.

## 6. Transaction boundary không nên kéo dài theo thời gian người dùng

Một lỗi thiết kế thường gặp là mở transaction khi người dùng bắt đầu chỉnh sửa form và giữ nó mở cho đến khi họ nhấn Save vài phút sau. Điều này giữ connection và có thể giữ lock lâu, làm tăng contention và deadlock.

Thông thường, transaction chỉ nên bao quanh phần xử lý use case trên server:

```text
Client đọc dữ liệu
    |
    | người dùng chỉnh sửa ngoài transaction
    v
Client gửi command/update với version đã đọc
    |
    v
Application Service mở transaction
    |
    +--> Repository load Aggregate
    +--> Domain behavior
    +--> Repository save
    |
    v
Commit / Rollback
```

Nếu Aggregate đã thay đổi trong lúc người dùng chỉnh sửa, optimistic locking hoặc ETag có thể phát hiện stale state. Ứng dụng tải lại và yêu cầu người dùng xác nhận hoặc áp dụng lại thay đổi theo policy.

Repository không nên giữ connection hoặc transaction sống trong suốt thời gian người dùng tương tác.

## 7. Repository và Aggregate Root

Một repository thường được định nghĩa cho mỗi Aggregate Root cần được nạp/lưu độc lập. Nó không nên cho phép caller sửa các thành phần bên trong Aggregate theo cách bỏ qua Root.

Ví dụ:

```java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void add(Order order);
    void save(Order order);
}
```

Nếu `OrderLine` thuộc Order Aggregate, API như sau thường đáng nghi:

```java
public interface OrderLineRepository {
    void updateQuantity(OrderId orderId, OrderLineId lineId, int quantity);
}
```

Caller có thể cập nhật quantity mà không kiểm tra invariant của Order, ví dụ giới hạn số lượng, giá đã chốt hoặc trạng thái cho phép chỉnh sửa. Thay vào đó, hãy nạp Order rồi gọi hành vi:

```java
Order order = orders.findById(orderId).orElseThrow();
order.changeLineQuantity(lineId, quantity);
orders.save(order);
```

Không phải mọi bảng con đều bắt buộc phải được nạp toàn bộ trong một lần. Persistence adapter có thể dùng lazy loading, batch query hoặc các kỹ thuật tối ưu khác. Điều cần giữ là các thay đổi domain vẫn đi qua Aggregate Root và invariant được bảo vệ.

## 8. Repository không nên trở thành nơi chứa business rule

Repository có thể thực hiện truy vấn và persistence mapping, nhưng không nên sở hữu quy tắc như:

- Order có được phép hủy hay không.
- Customer có đủ điều kiện mua chịu hay không.
- Số lượng hàng nào được phép reserve.
- Khoản thanh toán có thể hoàn tiền hay không.

Các quyết định đó thuộc domain model hoặc Domain Service phù hợp. Repository chỉ cung cấp dữ liệu cần thiết và lưu thay đổi.

Ví dụ, phương thức `findEligibleOrdersForCancellation()` có thể được hiểu theo domain nếu nó chỉ truy xuất những Order thỏa tiêu chí đã xác định. Nhưng nếu repository tự quyết định và thực hiện hủy, phát event, hoàn tiền và gửi email, nó đã vượt quá trách nhiệm truy xuất dữ liệu.

Hãy phân biệt truy vấn với quyết định:

- Repository có thể tìm các Order đang chờ xử lý.
- Aggregate quyết định Order có thể bị hủy hay không.
- Application Service điều phối use case hủy.
- Payment Context xử lý refund nếu policy yêu cầu.

## 9. Phân biệt command-side repository và read-side query

Repository trong DDD chủ yếu phục vụ việc lấy và lưu Aggregate cho hành vi ghi. Một màn hình báo cáo hoặc tìm kiếm có thể cần dữ liệu tổng hợp từ nhiều Aggregate và context. Không nhất thiết phải tải các Aggregate đầy đủ chỉ để hiển thị.

Có thể dùng query service hoặc read model riêng:

```java
public interface OrderSummaryQueries {
    Optional<OrderSummaryView> findSummary(OrderId id);
    Page<OrderSummaryView> search(OrderSearchCriteria criteria, PageRequest page);
}
```

`OrderSummaryView` có thể chứa tên khách hàng, tổng tiền, trạng thái thanh toán và trạng thái giao hàng. Nó là mô hình đọc, không phải Aggregate để sửa.

Trong CQRS, write model và read model có thể tách biệt. Tuy nhiên, không cần áp dụng CQRS chỉ vì có một query phức tạp. Hãy chọn cách đọc đơn giản phù hợp với nhu cầu và giữ ranh giới giữa query data và domain behavior rõ ràng.

### Tránh dùng repository để tải cả thế giới

Một phương thức như `findEverythingForDashboard()` trả về object graph lớn có thể làm tăng tải database và coupling. Màn hình dashboard thường phù hợp với projection/query tối ưu cho nhu cầu đọc, có phân trang và dữ liệu tổng hợp.

## 10. Repository và transaction qua nhiều Bounded Context

Repository thường thuộc một Bounded Context và truy cập dữ liệu do context đó sở hữu. Không nên dùng repository của Sales để đọc hoặc sửa trực tiếp bảng Payment hay Inventory chỉ vì chúng nằm trong cùng database.

Mỗi context có mô hình và quyền sở hữu dữ liệu riêng. Khi một use case cần phối hợp:

- Application Service trong context sở hữu use case điều phối phần công việc của mình.
- Context khác nhận command hoặc contract tích hợp theo cơ chế đã thống nhất.
- Mỗi context dùng repository riêng để tải/lưu Aggregate của mình.
- Kết quả được trao đổi qua event, API hoặc message contract.
- Process Manager/Saga theo dõi tiến trình nếu cần nhiều bước và compensation.

Một transaction ACID cục bộ không thể tự commit nguyên tử hai database độc lập hoặc hai service có vòng đời deploy riêng. Nếu cần một quy trình xuyên context, hãy mô hình hóa trạng thái trung gian và eventual consistency thay vì giả định repository có thể mở transaction toàn cục.

## 11. Outbox và công bố event sau commit

Một use case có thể cần lưu Aggregate và công bố event để context khác phản ứng. Nếu ứng dụng commit database trước rồi publish message, có thể xảy ra:

1. Database commit thành công.
2. Ứng dụng gặp sự cố trước khi publish.
3. Context khác không nhận được event dù domain state đã thay đổi.

Nếu publish trước commit, message có thể được gửi ra ngoài trong khi transaction database rollback. Khi đó consumer phản ứng với một sự kiện chưa thực sự được ghi nhận.

Transactional Outbox giải quyết vấn đề phối hợp này bằng cách ghi trạng thái domain và một bản ghi outbox trong cùng transaction:

```text
BEGIN TRANSACTION
  OrderRepository.save(order)
  OutboxRepository.add(OrderAcceptedMessage)
COMMIT

Outbox Publisher
  -> đọc message chưa gửi
  -> publish lên broker
  -> đánh dấu đã gửi (hoặc lưu checkpoint)
```

Outbox record có thể được lưu bởi một repository/adapter hạ tầng riêng, nhưng việc tạo record cần tham gia cùng transaction với thay đổi domain. Publisher gửi message sau commit và cần xử lý retry, duplicate cùng idempotency ở consumer.

Outbox không làm message được gửi đúng một lần tuyệt đối trong mọi tình huống. Một publisher có thể gửi thành công nhưng chưa kịp đánh dấu đã gửi trước khi process dừng, dẫn đến gửi lại. Consumer cần xử lý idempotent hoặc deduplicate theo event ID.

## 12. Repository và optimistic locking

Repository adapter cần phối hợp với cơ chế concurrency của persistence layer. Nếu Aggregate có version, thao tác save phải bảo đảm cập nhật chỉ thành công khi version vẫn là version đã đọc.

Với JPA:

```java
@Entity
class OrderRecord {
    @Id
    private UUID id;

    @Version
    private long version;

    // Các trường persistence khác
}
```

Khi hai transaction cùng tải một Order, transaction commit trước sẽ tăng version. Transaction còn lại khi flush/commit sẽ gặp optimistic locking conflict. Repository không nên bắt exception rồi tự commit dữ liệu cũ; application layer cần rollback transaction và quyết định có tải lại, thử lại hay trả conflict.

Nếu adapter sử dụng bulk update hoặc SQL tùy chỉnh, cần tự đưa expected version vào điều kiện `WHERE`, tăng version và kiểm tra số hàng bị cập nhật. Không được để một đường ghi bỏ qua version protocol.

### `save()` có nghĩa là commit không?

Không nhất thiết. Trong nhiều ORM, `save()` chỉ đưa entity vào persistence context hoặc đánh dấu cần persist. SQL có thể được gửi khi flush; commit xảy ra ở cuối transaction. Hãy đọc contract của framework đang dùng và không suy diễn rằng một lời gọi `save()` đồng nghĩa dữ liệu đã bền vững.

## 13. Xử lý nhiều repository khi có lỗi

Khi một use case dùng nhiều repository, cần xác định lỗi ở từng bước và cách transaction phản ứng.

| Tình huống | Nếu cùng transaction cục bộ | Nếu qua nhiều context/service |
|---|---|---|
| Repository thứ nhất lưu thành công, repository thứ hai lỗi | Rollback toàn transaction | Có thể phải compensation hoặc tiếp tục tiến trình phục hồi |
| Version conflict ở Aggregate thứ hai | Rollback cả transaction, tải lại và đánh giá lại | Xử lý trong context sở hữu Aggregate đó và cập nhật process state |
| Publish event thất bại sau commit | Dùng outbox để retry | Message contract, retry và deduplication |
| Context đích tạm thời không khả dụng | Không áp dụng nếu cùng DB transaction | Giữ trạng thái chờ, retry có giới hạn và quan sát được |
| Kết quả bên ngoài không xác định | Đối soát trước khi lặp side effect | Process Manager/Saga và reconciliation |

Không nên bắt lỗi rồi bỏ qua để tiếp tục commit phần còn lại nếu use case yêu cầu atomicity. Ngược lại, không nên rollback một transaction dài cho một tác vụ bên ngoài có thể được xử lý bất đồng bộ nếu domain cho phép trạng thái chờ.

## 14. Khi nào repository có thể quản lý transaction?

Trong một số hệ thống nhỏ hoặc legacy, repository/DAO có thể tự mở và đóng transaction cho một thao tác đơn giản. Điều này có thể chấp nhận nếu thao tác thực sự độc lập và contract thể hiện rõ phạm vi đó.

Tuy nhiên, khi use case cần phối hợp nhiều repository, transaction ẩn bên trong từng repository khiến khó bảo đảm atomicity. Nếu repository tự commit, application service không thể dễ dàng gộp các thao tác vào cùng một transaction.

Một số framework có repository tham gia vào transaction hiện tại dù không khai báo transaction ở application method. Điều đó không có nghĩa repository sở hữu transaction. Cần phân biệt:

- **Tham gia transaction:** repository sử dụng connection/persistence context hiện hành.
- **Bắt đầu transaction:** một boundary mới được mở.
- **Commit transaction:** thay đổi được xác nhận.
- **Rollback transaction:** thay đổi được hủy.

Thiết kế phổ biến trong DDD là transaction boundary được đặt ở application use case hoặc một command handler tương đương. Repository tham gia vào boundary đó.

## 15. Thiết kế API repository vừa đủ

Repository không nên phơi bày toàn bộ khả năng truy vấn của database. API nên tập trung vào nhu cầu domain/use case đã biết.

Ví dụ API có ý nghĩa:

```java
public interface SubscriptionRepository {
    Optional<Subscription> findById(SubscriptionId id);
    List<Subscription> findDueForRenewal(Instant at, int limit);
    void add(Subscription subscription);
    void save(Subscription subscription);
}
```

Phương thức `findDueForRenewal()` diễn đạt một tiêu chí có ý nghĩa trong domain. Tuy vậy, nếu nó trả về hàng nghìn Aggregate hoặc chỉ phục vụ một báo cáo, query service có thể phù hợp hơn.

Tránh các API quá tổng quát như:

```java
List<Object> find(String table, String field, String operator, Object value);
void update(String table, Map<String, Object> values);
```

Những API này làm lộ cấu trúc storage và khiến domain caller có thể truy cập hoặc sửa dữ liệu ngoài ranh giới Aggregate.

### Không cần `save()` cho mọi thay đổi nếu Unit of Work đã theo dõi

Trong ORM có dirty checking, một Aggregate được nạp trong transaction có thể được cập nhật khi thay đổi và tự flush khi commit. Repository vẫn có thể cung cấp `save()` để làm rõ ý định hoặc hỗ trợ persistence adapter khác, nhưng không nên gọi `save()` sau mỗi setter chỉ vì nghĩ rằng database sẽ không nhận thay đổi nếu thiếu lời gọi đó.

Hãy thống nhất semantics của repository trong project: `save()` là persist/merge, đánh dấu thay đổi, hay thao tác upsert? Không nên để người gọi phải đoán.

## 16. Repository và phân trang, khóa, truy vấn lớn

Một repository có thể cung cấp truy vấn theo tiêu chí và giới hạn kết quả. Nhưng không nên tải toàn bộ Aggregate chỉ để tìm kiếm hoặc thống kê.

Với tập dữ liệu lớn:

- Dùng phân trang hoặc cursor/keyset pagination.
- Chọn projection chỉ gồm field cần thiết.
- Dùng query service cho màn hình và báo cáo.
- Tránh eager-load graph quá lớn.
- Chỉ dùng pessimistic lock khi domain và workload thực sự cần.
- Đánh giá index và execution plan ở persistence layer.

Nếu truy vấn phục vụ quyết định ghi, hãy đảm bảo kết quả đủ mới và quyết định cuối cùng vẫn được thực hiện ở nơi sở hữu invariant. Ví dụ, query `availableQuantity` để hiển thị không thể thay thế thao tác `reserve()` của Inventory Aggregate.

## 17. Test repository và transaction boundary

Unit test cho Aggregate kiểm tra quy tắc domain mà không cần database. Repository adapter cần test mapping và persistence behavior. Application use case cần test transaction boundary và cách phối hợp nhiều repository.

Một bộ kiểm tra có thể gồm:

**Domain unit test:** Order không cho hủy khi đã giao; Account không cho ghi nợ vượt hạn mức.

**Repository integration test:** Lưu và nạp lại Aggregate giữ đúng identity, Value Object, collection và trạng thái.

**Transaction integration test:** Nếu repository thứ hai thất bại, thay đổi từ repository thứ nhất cũng rollback trong cùng transaction.

**Concurrency test:** Hai transaction cùng cập nhật một Aggregate; một transaction bị optimistic conflict thay vì ghi đè.

**Outbox test:** Thay đổi domain và outbox record cùng commit hoặc cùng rollback; publisher có thể retry và consumer xử lý duplicate.

Ví dụ kịch bản kiểm tra transaction:

```text
Given Order đang ở trạng thái Pending
When use case xác nhận Order và tạo Invoice
And InvoiceRepository thất bại khi lưu
Then transaction rollback
And Order vẫn ở trạng thái Pending khi đọc lại
And không có Invoice được ghi nhận
```

Test này cần chạy với transaction/persistence thực hoặc test container phù hợp. Mock hai repository rồi xác minh method được gọi không chứng minh database đã rollback nguyên tử.

## 18. Những sai lầm thường gặp

**Mỗi repository tự commit.** Một use case nhiều repository có thể lưu thành công một phần. Hãy để transaction boundary bao trùm toàn bộ thao tác cần atomicity.

**Repository chứa business rule.** Repository nên truy xuất/lưu Aggregate; quy tắc thuộc Entity, Value Object, Domain Service hoặc policy phù hợp.

**Tạo repository cho từng bảng.** Điều này có thể cho phép sửa Entity con ngoài Aggregate Root và làm lộ cấu trúc database.

**Dùng repository ghi để phục vụ mọi báo cáo.** Query lớn nên dùng projection/read model phù hợp, tránh tải Aggregate không cần thiết.

**Nhầm `save()` với commit.** ORM có thể trì hoãn SQL đến flush hoặc commit. Cần hiểu lifecycle của Unit of Work.

**Gọi repository xuyên Bounded Context.** Một context không nên truy cập trực tiếp dữ liệu do context khác sở hữu. Dùng contract tích hợp và mô hình riêng.

**Bulk update bỏ qua invariant và version.** Cập nhật trực tiếp có thể phá Aggregate consistency hoặc không phát hiện concurrency conflict.

**Giữ transaction quá lâu.** Không giữ database transaction trong khi người dùng chỉnh sửa form hoặc chờ API ngoài.

**Publish event trước commit hoặc sau commit mà không có outbox.** Cả hai cách đều có thể tạo message sai hoặc làm mất event. Dùng transactional outbox khi cần bảo đảm lưu thay đổi và ý định công bố cùng nhau.

**Cho rằng nhiều repository đồng nghĩa nhiều transaction.** Transaction boundary được xác định bởi use case và transactional resource, không phải số lượng repository.

## 19. Quy trình xác định transaction boundary cho một use case

Khi thiết kế use case có nhiều thao tác persistence, hãy thực hiện:

**Bước 1: Viết mục tiêu nghiệp vụ.** Mô tả kết quả cần đạt bằng ngôn ngữ của chuyên gia.

**Bước 2: Xác định Aggregate liên quan.** Ghi rõ Aggregate Root nào được đọc hoặc thay đổi và context nào sở hữu chúng.

**Bước 3: Xác định invariant.** Những điều kiện nào phải đúng ngay sau khi use case hoàn tất?

**Bước 4: Phân loại consistency requirement.** Thay đổi nào phải cùng commit? Thay đổi nào có thể được xử lý cuối cùng?

**Bước 5: Kiểm tra transactional resource.** Các repository có thể tham gia cùng database transaction không? Có service hoặc database độc lập không?

**Bước 6: Đặt transaction boundary ở application layer.** Bao trùm các thao tác cần atomicity, giữ transaction ngắn và tránh network I/O không cần thiết bên trong.

**Bước 7: Để repository tham gia Unit of Work.** Repository thực hiện load/save và mapping; không tự commit độc lập làm vỡ boundary.

**Bước 8: Xác định concurrency và failure path.** Optimistic/pessimistic locking, rollback, retry, idempotency và compensation.

**Bước 9: Xử lý event sau commit.** Dùng outbox nếu thay đổi domain phải đi cùng ý định công bố message.

**Bước 10: Viết integration test.** Kiểm tra rollback toàn bộ, version conflict và behavior của adapter bằng persistence thực.

## 20. Checklist đánh giá Repository và transaction

- [ ] Repository được định nghĩa theo Aggregate Root cần truy xuất/lưu.
- [ ] API repository dùng identifier và thuật ngữ domain.
- [ ] Domain model không phụ thuộc SQL, ORM hoặc cấu trúc bảng.
- [ ] Repository không chứa business rule hoặc điều phối toàn use case.
- [ ] Repository không tự commit độc lập khi use case cần transaction chung.
- [ ] Application Service xác định transaction boundary theo consistency requirement.
- [ ] Các repository cần atomicity tham gia cùng Unit of Work/transaction.
- [ ] Flush được phân biệt với commit.
- [ ] Thay đổi Entity con đi qua Aggregate Root.
- [ ] Query/reporting dùng projection phù hợp khi không cần Aggregate.
- [ ] Bulk update không bỏ qua invariant và version protocol.
- [ ] Mỗi Bounded Context truy cập dữ liệu do mình sở hữu.
- [ ] Event được công bố đáng tin cậy qua outbox khi cần.
- [ ] Có test rollback khi một thao tác trong transaction thất bại.
- [ ] Có test concurrency cho các Aggregate chịu tranh chấp.

## 21. Bài tập tự kiểm tra

Một nền tảng thương mại điện tử có use case `ConfirmOrderAndReserveStock`. Khi khách xác nhận đơn, hệ thống cần:

1. Nạp Order và kiểm tra có thể xác nhận.
2. Ghi nhận Order đã được chấp nhận.
3. Yêu cầu Inventory giữ số lượng cho từng SKU.
4. Ghi nhận kết quả giữ hàng.
5. Nếu tất cả hàng được giữ, đưa Order sang trạng thái sẵn sàng thực hiện.

Hãy trả lời:

1. Nên có những repository nào và mỗi repository sở hữu Aggregate nào?
2. Có nên tạo `OrderLineRepository` để cập nhật số lượng riêng không? Vì sao?
3. Nếu Sales và Inventory dùng cùng một database transactional resource, có thể dùng một transaction chung không? Những đánh đổi nào cần cân nhắc?
4. Nếu Inventory là service/database độc lập, `OrderRepository` có thể trực tiếp mở transaction để cập nhật stock không?
5. Application Service và Process Manager khác nhau thế nào trong use case này?
6. Nếu Inventory reserve thành công nhưng event phản hồi bị mất, làm sao tránh reserve lần hai?
7. Nếu `OrderRepository.save()` thành công nhưng `OutboxRepository.add()` thất bại, kết quả cần là gì?
8. Màn hình danh sách đơn hàng nên tải toàn bộ Order Aggregate hay dùng read model?

Gợi ý:

- Sales có `OrderRepository`; Inventory có repository riêng cho Stock/Reservation Aggregate. Mỗi repository chỉ thao tác Aggregate thuộc context của mình.
- `OrderLine` nên được sửa thông qua `Order` nếu nó là thành phần của Order Aggregate.
- Nếu cùng một transactional resource và nghiệp vụ yêu cầu atomicity tức thời, có thể dùng một transaction chung, nhưng cần cân nhắc coupling và contention. Nếu khác service/database, dùng message/contract và quy trình eventual consistency.
- Sales không nên truy cập database hoặc repository nội bộ của Inventory. Application Service/Process Manager điều phối qua contract.
- Idempotency key hoặc reservation reference duy nhất giúp Inventory nhận diện command lặp. Consumer/outbox cần xử lý duplicate.
- Nếu Order và outbox phải được ghi cùng nhau, lỗi ghi outbox cần rollback transaction chứa thay đổi Order.
- Màn hình danh sách thường phù hợp với projection/read model phân trang thay vì tải toàn bộ Aggregate.

## Kết luận

Repository là abstraction để truy xuất và lưu Aggregate theo ngôn ngữ domain. Nó không phải nơi chứa business rule và thường không nên tự commit độc lập sau mỗi thao tác. Một use case có thể dùng nhiều repository trong cùng transaction khi các Aggregate cùng nằm trong transactional resource và nghiệp vụ yêu cầu thay đổi nguyên tử.

Application Service xác định transaction boundary; Unit of Work và transaction manager phối hợp commit/rollback; repository tham gia vào cơ chế đó để load/save Aggregate. Khi quy trình đi qua Bounded Context hoặc service độc lập, transaction cục bộ không đủ: cần contract tích hợp, trạng thái trung gian, idempotency và Saga/Process Manager nếu phù hợp. Phân biệt rõ những trách nhiệm này giúp repository giữ API đơn giản, Aggregate bảo vệ invariant và use case có hành vi nhất quán khi thành công lẫn thất bại.
