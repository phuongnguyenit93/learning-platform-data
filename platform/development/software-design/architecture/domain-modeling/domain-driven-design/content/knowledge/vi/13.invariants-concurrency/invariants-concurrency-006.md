# Kết hợp ràng buộc cơ sở dữ liệu với quy tắc trong mô hình

## Vì sao cần bảo vệ bất biến ở cả mô hình và cơ sở dữ liệu?

Trong Domain-Driven Design (DDD), **bất biến (invariant)** là điều kiện nghiệp vụ phải luôn đúng tại những thời điểm mà mô hình quy định. Ví dụ, đơn hàng đã xác nhận phải có ít nhất một dòng hàng; số lượng đặt phải lớn hơn 0; tồn kho không được âm; mã đơn hàng phải duy nhất trong phạm vi doanh nghiệp quy định.

Các bất biến cần được bảo vệ ở nơi có đủ thông tin và quyền sở hữu để quyết định tính hợp lệ. Mô hình miền diễn đạt ý nghĩa và quy tắc nghiệp vụ. Cơ sở dữ liệu bảo vệ tính toàn vẹn của dữ liệu đã lưu, kể cả khi có nhiều tiến trình cùng ghi, khi một đường ghi khác bỏ qua domain model hoặc khi ứng dụng gặp lỗi giữa chừng.

Nếu chỉ kiểm tra trong Java, hai yêu cầu đồng thời có thể cùng đọc một trạng thái hợp lệ rồi cùng ghi kết quả khiến dữ liệu vi phạm quy tắc. Nếu chỉ dựa vào constraint của cơ sở dữ liệu, người dùng có thể nhận lỗi kỹ thuật khó hiểu, và các quy tắc phức tạp phụ thuộc ngữ cảnh có thể bị đẩy vào trigger hoặc câu SQL khó duy trì.

Vì vậy, cần phối hợp hai lớp bảo vệ:

- **Domain model:** diễn đạt quy tắc bằng ngôn ngữ nghiệp vụ, kiểm tra trước khi thay đổi trạng thái và trả về kết quả có ý nghĩa.
- **Database constraints và transaction:** bảo đảm dữ liệu lưu cuối cùng thỏa mãn các điều kiện có thể biểu đạt ở tầng lưu trữ, đồng thời kiểm soát các thay đổi đồng thời.

Sau bài học, người học có thể:

- Phân biệt bất biến nghiệp vụ với ràng buộc toàn vẹn dữ liệu.
- Quyết định quy tắc nào thuộc entity/aggregate và quy tắc nào nên được bảo vệ thêm bằng database constraint.
- Sử dụng `NOT NULL`, `CHECK`, `UNIQUE`, `FOREIGN KEY` và transaction đúng mục đích.
- Hiểu vì sao kiểm tra trước khi ghi không đủ để ngăn mọi race condition.
- Chọn optimistic locking, pessimistic locking hoặc cập nhật nguyên tử theo đặc điểm nghiệp vụ.
- Chuyển lỗi constraint thành phản hồi phù hợp mà không che giấu lỗi dữ liệu.

## Bất biến nghiệp vụ và ràng buộc cơ sở dữ liệu

### Bất biến nghiệp vụ là gì?

Bất biến nghiệp vụ mô tả điều kiện mà nghiệp vụ yêu cầu phải đúng. Nó thường liên quan đến trạng thái, hành vi và quan hệ giữa các khái niệm miền.

Ví dụ:

- Đơn hàng chỉ được đặt khi có ít nhất một dòng hàng.
- Đơn đã đặt không được tùy tiện thay đổi đơn giá đã chốt.
- Tài khoản không được chi vượt hạn mức thấu chi đã được phê duyệt.
- Một phòng không được có hai lượt đặt chỗ trùng thời gian theo chính sách.
- Một khách hàng chỉ được có một hồ sơ chính trong một phạm vi định danh nhất định.

Bất biến có thể phụ thuộc vào một đối tượng, một aggregate, nhiều aggregate hoặc một quy trình kéo dài qua nhiều bước. Phạm vi của bất biến quyết định cách bảo vệ nó.

### Ràng buộc toàn vẹn dữ liệu là gì?

Ràng buộc cơ sở dữ liệu là điều kiện mà hệ quản trị dữ liệu kiểm tra khi thực hiện thao tác ghi. Các loại thường dùng gồm:

| Constraint | Điều kiện được bảo vệ | Ví dụ |
|---|---|---|
| `NOT NULL` | Cột bắt buộc có giá trị | `order_id` không được null |
| `CHECK` | Giá trị thỏa mãn biểu thức | `quantity > 0` |
| `UNIQUE` | Không trùng khóa hoặc tổ hợp cột | Mã đơn duy nhất trong tenant |
| `PRIMARY KEY` | Định danh bản ghi duy nhất và không null | `order.id` |
| `FOREIGN KEY` | Tham chiếu đến bản ghi tồn tại | Dòng hàng phải thuộc một đơn đã lưu |
| Transaction | Một nhóm thay đổi được commit hoặc rollback theo cùng giao dịch | Lưu đơn và các dòng hàng cùng nhau |

Constraint bảo vệ tính toàn vẹn ở tầng dữ liệu. Nó không tự diễn đạt đầy đủ lý do nghiệp vụ hoặc phản hồi phù hợp cho người dùng. Ví dụ, `CHECK (available_quantity >= 0)` ngăn tồn kho âm, nhưng không giải thích chính sách ưu tiên đơn hàng, hàng đang được giữ hay cách xử lý khi hết hàng.

### Hai lớp bảo vệ bổ sung cho nhau

| Câu hỏi | Domain model | Database |
|---|---|---|
| Quy tắc có ý nghĩa gì? | Diễn đạt trực tiếp bằng ngôn ngữ miền | Thể hiện điều kiện lưu trữ có thể kiểm tra |
| Kiểm tra khi nào? | Trước hoặc trong hành vi thay đổi trạng thái | Khi ghi/commit dữ liệu tùy loại constraint và DB |
| Bảo vệ khỏi nhiều writer đồng thời? | Cần cơ chế concurrency phù hợp | Constraint, khóa và transaction là lớp bảo vệ cuối |
| Phản hồi cho nghiệp vụ? | Có thể đưa ra lỗi hoặc kết quả miền rõ ràng | Thường trả lỗi kỹ thuật cần được ánh xạ |
| Phạm vi phù hợp | Quy tắc phụ thuộc trạng thái, ý nghĩa và hành vi miền | Duy nhất, tham chiếu, miền giá trị và các điều kiện dữ liệu |

Không phải bất biến nào cũng có thể biểu diễn bằng một constraint đơn giản. Một quy tắc như “khách hàng được mua tối đa ba sản phẩm thuộc nhóm A trong một tháng nếu đang ở hạng B” có thể cần nhiều dữ liệu, thời gian và chính sách. Domain model hoặc domain service xác định ý nghĩa của quy tắc; transaction, khóa hoặc thiết kế dữ liệu sẽ bảo đảm cách thực thi phù hợp.

## Đặt bất biến trong đúng ranh giới

### Bất biến nội tại của Value Object

Value Object tự bảo vệ tính hợp lệ của giá trị cấu thành. Ví dụ:

- `Money` yêu cầu số tiền và tiền tệ hợp lệ.
- `Quantity` yêu cầu số lượng và đơn vị đo tương thích.
- `DateRange` yêu cầu ngày bắt đầu không sau ngày kết thúc theo quy tắc miền.

Những điều kiện này nên được kiểm tra khi tạo value object. Nếu giá trị không hợp lệ, không nên để nó đi vào aggregate rồi mới phát hiện ở một bước lưu trữ xa hơn.

### Bất biến của Entity và Aggregate

Entity bảo vệ các quy tắc gắn với vòng đời của chính nó. Aggregate Root bảo vệ các bất biến cần được duy trì nhất quán trong toàn bộ aggregate.

Ví dụ, `Order` có thể bảo vệ các điều kiện:

- Chỉ đơn ở trạng thái nháp mới được thêm hoặc xóa dòng hàng.
- Đơn được đặt phải có ít nhất một dòng hàng.
- Dòng hàng phải có số lượng hợp lệ và giá đã chốt.
- Đơn đã đặt không được thay đổi giá theo catalog hiện tại.

Các hành vi như `addLine()`, `removeLine()` và `place()` nên nằm trên `Order` hoặc các đối tượng miền có trách nhiệm. Application Service gọi hành vi đó; nó không tự sửa từng trường nội bộ để tạo ra trạng thái mới.

### Quy tắc phối hợp nhiều Aggregate

Một quy tắc có thể liên quan đến nhiều aggregate. Ví dụ, đặt hàng cần kiểm tra khách hàng và giữ tồn kho. Không nên tự động gộp `Customer`, `Order` và `Inventory` vào cùng một aggregate chỉ để có một transaction lớn.

Hãy xác định:

- Điều kiện nào phải đúng ngay khi một aggregate thay đổi?
- Điều kiện nào có thể được xử lý qua quy trình nhiều bước?
- Có thể chấp nhận trạng thái tạm thời hoặc nhất quán cuối cùng không?
- Khi một bước thất bại, cần hành động bù trừ nào?

Nếu một bất biến thực sự phải đúng nguyên tử trên nhiều dữ liệu, cần thiết kế cơ chế thực thi tương ứng: transaction ở một ranh giới lưu trữ phù hợp, constraint, khóa, reservation hoặc một mô hình dữ liệu khác. Không nên tuyên bố một quy tắc được bảo vệ chỉ vì đã gọi nhiều repository trong cùng một method.

## Chọn constraint phù hợp

### NOT NULL: dữ liệu bắt buộc

Dùng `NOT NULL` khi cột phải có giá trị đối với mọi bản ghi hợp lệ. Ví dụ, một dòng hàng luôn phải thuộc về đơn hàng và phải có số lượng.

Lưu ý: `CHECK (quantity > 0)` không thay thế `NOT NULL`. Trong SQL, biểu thức `CHECK` thường không loại bỏ giá trị `NULL` vì kết quả `UNKNOWN` không bị xem như `FALSE`. Nếu cột bắt buộc, hãy khai báo cả hai:

```sql
quantity NUMERIC(18, 3) NOT NULL CHECK (quantity > 0)
```

### CHECK: giới hạn miền giá trị

Dùng `CHECK` cho điều kiện có thể đánh giá trên một hàng hoặc một biểu thức được DB hỗ trợ:

```sql
CREATE TABLE inventory (
    product_id UUID PRIMARY KEY,
    available_quantity NUMERIC(18, 3) NOT NULL
        CHECK (available_quantity >= 0),
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE order_line (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL,
    line_number INTEGER NOT NULL CHECK (line_number > 0),
    quantity NUMERIC(18, 3) NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(18, 2) NOT NULL CHECK (unit_price >= 0),
    currency CHAR(3) NOT NULL,
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id) REFERENCES orders(id),
    CONSTRAINT uq_order_line_number
        UNIQUE (order_id, line_number)
);
```

Ví dụ dùng kiểu `UUID` và cú pháp phổ biến trong PostgreSQL. Kiểu dữ liệu, cú pháp và khả năng hỗ trợ constraint có thể khác theo hệ quản trị. `CHECK` trên `order_line` bảo vệ các điều kiện đơn giản của từng dòng. Nó không kiểm tra được toàn bộ quy tắc như “đơn đã đặt phải có ít nhất một dòng”, vì quy tắc đó liên quan đến trạng thái của hàng `orders` và tập dòng hàng.

### UNIQUE: bảo vệ tính duy nhất dưới cạnh tranh

Giả sử hệ thống yêu cầu email đã chuẩn hóa phải duy nhất trong một tenant. Ở tầng domain, ứng dụng có thể kiểm tra trước để trả thông báo thân thiện. Nhưng hai yêu cầu đồng thời có thể cùng kiểm tra và cùng thấy email chưa tồn tại.

```sql
CREATE TABLE customer_account (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    normalized_email VARCHAR(320) NOT NULL,
    CONSTRAINT uq_customer_email_per_tenant
        UNIQUE (tenant_id, normalized_email)
);
```

Unique constraint là cơ chế cuối cùng ngăn hai transaction cùng tạo bản ghi trùng. Kiểm tra trước khi insert cải thiện trải nghiệm, nhưng không thay thế constraint. Khi constraint bị vi phạm, ứng dụng cần nhận diện đúng constraint và chuyển thành kết quả miền hoặc lỗi use case phù hợp, chẳng hạn `EmailAlreadyRegistered`.

### FOREIGN KEY: bảo vệ tham chiếu

Foreign key bảo đảm bản ghi được tham chiếu tồn tại trong phạm vi cơ sở dữ liệu đó. Ví dụ, một dòng hàng không thể tham chiếu một đơn hàng không tồn tại.

Tuy nhiên, không phải mọi aggregate reference đều cần foreign key vật lý. Nếu hai bounded context có kho dữ liệu độc lập, tham chiếu qua ID có thể được xác minh bằng hợp đồng tích hợp hoặc quy trình đồng bộ thay vì FK xuyên cơ sở dữ liệu. Không nên tạo phụ thuộc lưu trữ giữa các context chỉ để có một khóa ngoại tiện lợi.

## Transaction: bảo vệ một nhóm thay đổi nguyên tử

Transaction giúp nhóm các thao tác ghi thành một đơn vị commit hoặc rollback. Ví dụ, khi lưu đơn hàng, bản ghi `orders` và các bản ghi `order_line` phải được lưu cùng nhau. Nếu một dòng hàng không hợp lệ hoặc thao tác ghi thất bại, transaction cần rollback để không còn một đơn hàng dở dang.

```java
@Transactional
public OrderId placeOrder(PlaceOrderCommand command) {
    Order order = orderFactory.createDraft(command);
    order.place();
    orderRepository.save(order);
    return order.id();
}
```

Ví dụ giả định repository lưu aggregate `Order` cùng các dòng hàng trong cùng transaction. `@Transactional` là annotation của Spring; transaction boundary thực tế còn phụ thuộc cấu hình, propagation, exception type và cách repository triển khai. Nếu cần gửi message sau khi lưu, không nên giả định lời gọi broker và transaction DB tự động nguyên tử với nhau; hãy xem xét Transactional Outbox.

### Transaction không tự động bảo vệ mọi bất biến

Một transaction có thể đảm bảo tính nguyên tử của các thao tác bên trong, nhưng kết quả phụ thuộc isolation level, loại truy vấn và cơ chế khóa. Hai transaction có thể cùng đọc một giá trị cũ rồi cùng ghi dựa trên giá trị đó. Một transaction lớn cũng không tự động khiến mọi quy tắc nghiệp vụ xuyên nhiều aggregate trở nên an toàn.

Hãy phân biệt:

- **Atomicity:** tất cả thay đổi trong transaction cùng commit hoặc cùng rollback.
- **Consistency:** transaction phải đưa dữ liệu từ một trạng thái hợp lệ sang trạng thái hợp lệ theo các constraint và quy tắc được thực thi.
- **Isolation:** các transaction đồng thời nhìn thấy và tác động lẫn nhau theo mức cô lập được chọn.
- **Durability:** thay đổi đã commit được lưu bền vững theo bảo đảm của hệ quản trị.

ACID là nhóm thuộc tính của transaction. Nó không thay thế việc thiết kế bất biến, isolation, locking và cách xử lý lỗi.

## Đồng thời: vì sao kiểm tra trước khi ghi có thể sai?

### Race condition khi đặt chỗ hoặc trừ tồn kho

Giả sử tồn kho của một sản phẩm còn 5 chiếc. Hai yêu cầu đồng thời, mỗi yêu cầu đặt 4 chiếc:

1. Transaction A đọc tồn kho là 5 và thấy đủ hàng.
2. Transaction B cũng đọc tồn kho là 5 và thấy đủ hàng.
3. A trừ 4, còn 1.
4. B cũng trừ 4 dựa trên giá trị đã đọc trước đó.

Nếu cách ghi không được bảo vệ, tồn kho có thể thành âm hoặc một thay đổi bị ghi đè. Việc kiểm tra `available >= requested` trong Java trước khi ghi không đủ, vì cả hai request đều có thể vượt qua kiểm tra trước khi một request cập nhật.

Đây là race condition kiểu **check-then-act**. Cần gắn điều kiện kiểm tra với thao tác cập nhật nguyên tử hoặc dùng cơ chế concurrency phù hợp.

### Cập nhật có điều kiện trong một câu lệnh

Với một phép giữ hàng đơn giản, có thể dùng câu lệnh cập nhật có điều kiện:

```sql
UPDATE inventory
SET available_quantity = available_quantity - :requested,
    version = version + 1
WHERE product_id = :product_id
  AND :requested > 0
  AND available_quantity >= :requested;
```

Ứng dụng kiểm tra số dòng được cập nhật:

- Một dòng được cập nhật: giữ hàng thành công.
- Không có dòng được cập nhật: sản phẩm không tồn tại, số lượng không hợp lệ hoặc tồn kho không đủ; có thể cần truy vấn thêm để phân biệt các trường hợp.

Điều kiện và phép trừ nằm trong cùng một câu lệnh. Hệ quản trị thực hiện cập nhật có kiểm soát cạnh tranh trên bản ghi, nhờ đó hai yêu cầu không thể cùng tiêu thụ một lượng tồn kho ban đầu như thể không có request kia. Cần chạy trong transaction và xử lý kết quả cập nhật rõ ràng.

`CHECK (available_quantity >= 0)` vẫn hữu ích như lớp bảo vệ cuối cùng. Câu lệnh cập nhật nguyên tử xử lý quy tắc cạnh tranh của thao tác giữ hàng; `CHECK` ngăn mọi đường ghi lưu tồn kho âm.

### Optimistic locking

**Optimistic locking** phù hợp khi xung đột không quá thường xuyên và hệ thống muốn phát hiện thay đổi đồng thời thay vì khóa bản ghi trong suốt quá trình đọc-sửa.

Một entity persistence có thể chứa trường version:

```java
@Entity
public class InventoryRecord {
    @Id
    private UUID productId;

    @Column(nullable = false)
    private BigDecimal availableQuantity;

    @Version
    private long version;
}
```

Với JPA, `@Version` khiến câu lệnh update kiểm tra version đã đọc. Nếu transaction khác đã cập nhật bản ghi, update của transaction hiện tại không khớp version và ORM báo optimistic locking failure. Ứng dụng cần rollback transaction, tải lại trạng thái mới và quyết định retry hoặc trả lỗi xung đột theo nghiệp vụ.

Không nên retry vô hạn. Retry chỉ an toàn khi hành động có thể thực hiện lại mà không tạo tác dụng phụ trùng lặp và khi số lần retry có giới hạn. Với thao tác thanh toán hoặc gửi thông điệp, cần idempotency và cơ chế phối hợp tương ứng.

### Pessimistic locking

**Pessimistic locking** khóa bản ghi hoặc phạm vi dữ liệu để transaction khác phải chờ hoặc thất bại khi truy cập xung đột. Trong SQL, một truy vấn như `SELECT ... FOR UPDATE` có thể khóa các hàng được chọn cho đến khi transaction kết thúc, tùy hệ quản trị.

Phương pháp này có thể phù hợp với dữ liệu tranh chấp cao hoặc khi cần đọc rồi thực hiện nhiều bước phụ thuộc cùng một trạng thái. Tuy nhiên, khóa lâu làm giảm throughput, tăng thời gian chờ và có nguy cơ deadlock. Cần giữ transaction ngắn, truy cập tài nguyên theo thứ tự nhất quán và xử lý timeout/deadlock.

### Chọn chiến lược concurrency

| Chiến lược | Phù hợp khi | Chi phí và lưu ý |
|---|---|---|
| Optimistic locking | Xung đột ít hoặc vừa; có thể phát hiện và xử lý retry | Phải xử lý version conflict và retry có giới hạn |
| Pessimistic locking | Xung đột cao hoặc cần tuần tự hóa một vùng dữ liệu | Giữ khóa lâu làm giảm khả năng xử lý đồng thời |
| Conditional atomic update | Một quy tắc có thể biểu diễn trong một câu lệnh update | Cần kiểm tra số dòng ảnh hưởng và ánh xạ kết quả |
| Unique/Check constraint | Duy nhất hoặc miền giá trị cần đúng ở mọi đường ghi | Phản hồi DB cần được chuyển thành lỗi phù hợp |
| Serializable transaction | Một quy tắc phụ thuộc nhiều hàng cần mức cô lập mạnh | Có thể phát sinh serialization failure và cần retry |

Không có chiến lược duy nhất phù hợp mọi tình huống. Hãy chọn theo tần suất tranh chấp, mức độ quan trọng của dữ liệu, chi phí retry, yêu cầu latency và khả năng của hệ quản trị.

## Kết hợp Domain Model và Database Constraint trong một luồng

Hãy xem ví dụ đặt đơn hàng có dòng hàng và giữ tồn kho.

### Trong Domain Model

`OrderLine` kiểm tra số lượng dương và giá hợp lệ khi được tạo. `Order` kiểm tra chỉ đơn nháp mới được thêm dòng và chỉ đơn có dòng hàng mới được đặt. Những kiểm tra này giúp mọi caller nhận được lỗi miền rõ ràng trước khi ghi.

```java
public record OrderLine(Quantity quantity, Money unitPrice) {
    public OrderLine {
        Objects.requireNonNull(quantity, "quantity");
        Objects.requireNonNull(unitPrice, "unitPrice");
        if (quantity.isZeroOrNegative()) {
            throw new InvalidOrderQuantity();
        }
        if (unitPrice.isNegative()) {
            throw new InvalidUnitPrice();
        }
    }
}

public final class Order {
    private OrderStatus status = OrderStatus.DRAFT;
    private final List<OrderLine> lines = new ArrayList<>();

    public void addLine(OrderLine line) {
        if (status != OrderStatus.DRAFT) {
            throw new OrderCannotBeChanged();
        }
        lines.add(Objects.requireNonNull(line));
    }

    public void place() {
        if (status != OrderStatus.DRAFT) {
            throw new OrderCannotBePlaced();
        }
        if (lines.isEmpty()) {
            throw new EmptyOrderCannotBePlaced();
        }
        status = OrderStatus.PLACED;
    }
}
```

Các kiểu lỗi và `Quantity`/`Money` trong đoạn mã là minh họa. Mục tiêu là thể hiện quy tắc nằm trong mô hình miền và không cho phép caller tự gán trạng thái tùy ý.

### Trong Database

Cơ sở dữ liệu có thể bảo vệ thêm các điều kiện đơn giản:

```sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('DRAFT', 'PLACED', 'CANCELLED'))
);

CREATE TABLE order_line (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL REFERENCES orders(id),
    quantity NUMERIC(18, 3) NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(18, 2) NOT NULL CHECK (unit_price >= 0),
    currency CHAR(3) NOT NULL
);
```

Schema bảo vệ trạng thái thuộc tập cho phép, dòng hàng phải thuộc một đơn tồn tại, số lượng phải dương và đơn giá không âm. Quy tắc “đơn đã đặt phải có ít nhất một dòng” vẫn được bảo vệ trong hành vi `Order.place()` và transaction lưu aggregate. Nếu có nhiều đường ghi trực tiếp vào DB, cần đánh giá thêm trigger, stored procedure hoặc thiết kế lại luồng ghi; không nên giả định hai constraint trên đã kiểm tra được sự tồn tại của ít nhất một dòng hàng.

### Khi constraint bị vi phạm

Ngay cả khi domain model đã kiểm tra, constraint vẫn có thể bị vi phạm do cạnh tranh, dữ liệu cũ, migration, tác vụ quản trị hoặc một writer khác. Khi đó:

1. Transaction phải rollback nếu lỗi làm transaction không còn hợp lệ.
2. Persistence adapter nhận diện loại lỗi và constraint cụ thể nếu hệ quản trị cung cấp thông tin đó.
3. Application layer ánh xạ sang lỗi use case hoặc kết quả phù hợp, ví dụ `EmailAlreadyRegistered`, `InsufficientStock` hoặc `ConcurrentModification`.
4. Ghi log đủ ngữ cảnh để điều tra nhưng không lộ chi tiết nhạy cảm của dữ liệu.
5. Không bắt mọi lỗi integrity rồi trả về cùng một thông báo; vi phạm foreign key, unique và check có nguyên nhân khác nhau.

Tên constraint ổn định và quy ước ánh xạ lỗi giúp ứng dụng phân biệt nguyên nhân. Không nên dựa vào việc phân tích chuỗi thông báo lỗi DB nếu driver cung cấp mã SQL state hoặc tên constraint có cấu trúc.

## Khi nào dùng constraint, khi nào dùng quy tắc miền?

| Loại quy tắc | Nơi bảo vệ chính | Bảo vệ bổ sung |
|---|---|---|
| Giá trị bắt buộc | Value Object/Entity kiểm tra ngữ nghĩa | `NOT NULL` |
| Số lượng phải dương | `Quantity`/`OrderLine` | `CHECK (quantity > 0)` |
| Mã định danh duy nhất | Quy tắc miền và use case | `PRIMARY KEY` hoặc `UNIQUE` |
| Quan hệ bản ghi phải tồn tại | Aggregate/use case xác định ý nghĩa liên hệ | `FOREIGN KEY` khi cùng ranh giới lưu trữ |
| Đơn hàng phải có dòng trước khi đặt | `Order` Aggregate Root | Transaction; cân nhắc cơ chế DB nếu có writer ngoài |
| Tồn kho không âm | Quy tắc giữ hàng | `CHECK`, conditional update hoặc locking |
| Không trùng lịch đặt | Chính sách đặt chỗ | Unique/exclusion constraint hoặc khóa/transaction phù hợp với DB |
| Giảm giá theo hạng khách hàng và thời điểm | Domain policy/service | Lưu dấu vết quyết định và transaction phù hợp |
| Quy tắc xuyên nhiều bounded context | Quy trình phối hợp/Saga và hợp đồng | Idempotency, outbox, reconciliation |

Ranh giới “chính” không có nghĩa chỉ kiểm tra ở một nơi. Với những điều kiện quan trọng, domain model và DB có thể cùng bảo vệ một phần quy tắc ở các mức khác nhau. Điều cần tránh là hai nơi có hai định nghĩa khác nhau hoặc một constraint không được hiểu và ánh xạ lỗi đúng.

## Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Chỉ kiểm tra trong Java rồi tin dữ liệu không thể sai | Các writer đồng thời hoặc đường ghi khác có thể phá bất biến | Dùng constraint và concurrency control phù hợp |
| Đưa mọi quy tắc vào trigger hoặc stored procedure | Ngữ nghĩa miền khó nhìn thấy và khó kiểm thử cùng mô hình | Giữ quy tắc nghiệp vụ trong domain model; dùng DB để bảo vệ tính toàn vẹn phù hợp |
| Nghĩ transaction mặc định giải quyết mọi race condition | Có thể vẫn gặp lost update hoặc write skew tùy isolation | Chọn isolation, version hoặc lock theo quy tắc |
| Dùng `CHECK` thay `NOT NULL` | `NULL` có thể vẫn lọt qua biểu thức check | Khai báo cả `NOT NULL` khi bắt buộc |
| Kiểm tra tồn kho rồi mới trừ ở hai câu lệnh tách rời | Hai request có thể cùng vượt qua kiểm tra | Dùng conditional update hoặc khóa/version |
| Bắt mọi lỗi DB rồi báo “dữ liệu không hợp lệ” | Che giấu lỗi kỹ thuật và nguyên nhân khác nhau | Phân loại theo SQL state/constraint và ánh xạ có chủ đích |
| Dùng FK xuyên bounded context độc lập | Tạo liên kết lưu trữ chặt giữa các context | Dùng ID qua hợp đồng tích hợp và xử lý đồng bộ |
| Mở rộng transaction qua nhiều dịch vụ | Khó vận hành, khóa lâu hoặc cần distributed transaction | Dùng quy trình bất đồng bộ/Saga khi nghiệp vụ cho phép |
| Retry mọi lỗi concurrency vô hạn | Tăng tải và có thể lặp tác dụng phụ | Retry giới hạn, idempotent và có chính sách backoff |

## Checklist rà soát bất biến và constraint

Trước khi phát hành một luồng ghi quan trọng, hãy kiểm tra:

- [ ] Bất biến được mô tả bằng ngôn ngữ nghiệp vụ và có ví dụ hợp lệ/không hợp lệ.
- [ ] Đã xác định bất biến thuộc Value Object, Entity, Aggregate hay quy trình nhiều bước.
- [ ] Aggregate Root bảo vệ các bất biến nội bộ qua hành vi, không cho caller sửa tùy ý.
- [ ] Các cột bắt buộc có `NOT NULL` và các miền giá trị đơn giản có `CHECK` phù hợp.
- [ ] Các định danh duy nhất có `PRIMARY KEY`/`UNIQUE` làm lớp bảo vệ cuối.
- [ ] Các quan hệ trong cùng ranh giới lưu trữ có foreign key phù hợp.
- [ ] Đã kiểm tra `NULL` và semantics của constraint trong hệ quản trị đang dùng.
- [ ] Transaction bao phủ đúng nhóm thay đổi cần nguyên tử.
- [ ] Race condition đã được xem xét cho các luồng đọc-sửa-ghi.
- [ ] Optimistic/pessimistic locking hoặc conditional update được chọn theo mức tranh chấp.
- [ ] Lỗi constraint và concurrency được ánh xạ sang kết quả nghiệp vụ phù hợp.
- [ ] Retry có giới hạn và không lặp tác dụng phụ.
- [ ] Có log, metric và cách đối soát cho các luồng ghi quan trọng.
- [ ] Ranh giới giữa bounded context không bị ràng buộc chặt bằng FK hoặc transaction không cần thiết.

## Kết luận

Domain model và cơ sở dữ liệu bảo vệ bất biến ở hai góc nhìn bổ sung cho nhau. Mô hình miền diễn đạt ý nghĩa, trạng thái và hành vi; constraint bảo vệ dữ liệu đã lưu trước các đường ghi khác nhau và cạnh tranh; transaction cùng concurrency control bảo đảm các thay đổi diễn ra theo mức nhất quán mà nghiệp vụ yêu cầu. Khi đặt mỗi quy tắc đúng ranh giới, chọn constraint phù hợp và xử lý lỗi có chủ đích, hệ thống vừa dễ hiểu với chuyên gia nghiệp vụ vừa vững chắc trước các tình huống ghi dữ liệu thực tế.
