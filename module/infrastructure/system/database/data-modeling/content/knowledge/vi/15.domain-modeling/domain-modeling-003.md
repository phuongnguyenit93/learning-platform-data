# Cụm nhất quán (aggregate) và đối tượng gốc kiểm soát thay đổi

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **aggregate**, **aggregate root** và **bất biến nghiệp vụ** (*invariant*) bằng một tình huống có nhiều thực thể liên quan.
- Chọn ranh giới aggregate dựa trên điều kiện cần nhất quán ngay sau giao dịch, thay vì dựa vào số lượng bảng, màn hình hoặc dịch vụ.
- Thiết kế thao tác ghi đi qua aggregate root; phân biệt tham chiếu nội bộ, tham chiếu qua ID và dữ liệu bản chụp.
- Ánh xạ ranh giới ghi sang khóa, quan hệ, transaction và cơ chế chống cập nhật đồng thời trong cơ sở dữ liệu quan hệ.
- Nhận ra các quy tắc xuyên aggregate, tổ chức phối hợp bất đồng bộ và kiểm tra lỗi cạnh tranh, lặp thông điệp, mất phản hồi.
- Đánh giá ưu và nhược điểm của việc hiện thực aggregate trên mô hình quan hệ, document, đồ thị và hệ thống phân tích.

Trong **DATABASE_DATA_MODELING**, một lược đồ dữ liệu tốt phải trả lời câu hỏi: **ai được phép thay đổi dữ liệu nào, và sau mỗi thay đổi những điều gì bắt buộc vẫn đúng?** Chỉ biết đơn hàng gồm bảng Order và OrderLine chưa trả lời được liệu ta có thể sửa dòng hàng khi đơn đã xác nhận, hay hai yêu cầu đồng thời có thể làm mất cập nhật. Aggregate là công cụ thiết kế giúp trả lời các câu hỏi đó.

## 1. Aggregate là ranh giới nhất quán nghiệp vụ

**Aggregate** là tập hợp các đối tượng miền được quản lý như một đơn vị nhất quán. Nó có một **aggregate root** là đối tượng được bên ngoài sử dụng để thực hiện các thao tác làm thay đổi trạng thái bên trong. Root chịu trách nhiệm kiểm soát **bất biến**, tức các điều kiện phải đúng ở mọi trạng thái hợp lệ sau khi một thao tác nghiệp vụ hoàn tất.

Ví dụ trong bán hàng:

- **Order** là aggregate root, có ID và trạng thái riêng.
- **OrderLine** là entity con: có danh tính trong đơn, số lượng và đơn giá đã chốt.
- **Money** là value object: gồm số tiền và loại tiền; giá trị không cần danh tính riêng.
- **Customer**, **InventoryBalance** và **Payment** có vòng đời riêng, nên không mặc định là thành viên của Order aggregate.

Một cách nhìn trực quan:

~~~mermaid
flowchart TB
    Client["Use case: Sửa số lượng"]
    Client -->|"order.changeQuantity(lineId, qty)"| Order

    subgraph OA["Aggregate Order — một ranh giới nhất quán"]
      Order["Order (aggregate root)"]
      LineA["OrderLine #1 (entity con)"]
      LineB["OrderLine #2 (entity con)"]
      MoneyA["Money (value object)"]
      Order -->|"điều phối thay đổi"| LineA
      Order -->|"điều phối thay đổi"| LineB
      LineA --- MoneyA
    end

    Customer["Customer (aggregate khác)"]
    Stock["StockBalance (aggregate khác)"]
    Order -.->|"tham chiếu customerId"| Customer
    Order -.->|"yêu cầu giữ hàng"| Stock
~~~

Các đường liền thể hiện quyền kiểm soát trong Order; đường đứt là quan hệ với aggregate khác. Sơ đồ biểu diễn **trách nhiệm nghiệp vụ**, không bắt buộc Order và OrderLine phải được lưu trong cùng một document.

### Phân biệt ba ranh giới dễ nhầm

| Khái niệm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Bounded context** | Mô hình và ngôn ngữ nghiệp vụ nào có hiệu lực trong phạm vi này? | Sales định nghĩa Order, giá đã chốt, trạng thái xác nhận |
| **Aggregate** | Dữ liệu nào cần được thay đổi cùng nhau để bảo đảm bất biến cục bộ? | Order và các dòng hàng của chính đơn đó |
| **Database/schema/service** | Dữ liệu được lưu và triển khai bằng công nghệ nào? | Bảng orders và order_line trong schema sales |

Một bounded context có thể chứa nhiều aggregate. Một aggregate có thể trải trên nhiều bảng; ngược lại, một bảng có thể lưu nhiều aggregate độc lập (mỗi hàng là một root). **Không dùng FK, quan hệ 1-N hoặc cấu trúc thư mục để tự động suy ra ranh giới aggregate.**

## 2. Từ yêu cầu nghiệp vụ đến danh sách bất biến

Giả sử người dùng có thể thêm, bớt và đổi số lượng sản phẩm khi đơn ở trạng thái DRAFT. Sau khi xác nhận, đơn không được sửa dòng hàng hoặc giá mua. Bảng phân tích:

| Quy tắc | Phải nhất quán ngay sau thao tác? | Ai kiểm soát? |
| --- | --- | --- |
| Dòng hàng có số lượng dương | Có | Order/OrderLine |
| Các dòng trong cùng Order có ID khác nhau | Có | Order |
| Order không thể xác nhận khi chưa có dòng | Có | Order |
| Đơn CONFIRMED không được sửa giá hoặc số lượng | Có | Order và đường ghi dữ liệu của Sales |
| Tổng tiền đơn khớp với dòng hàng và quy tắc làm tròn | Có, nếu tổng được lưu như dữ liệu có thẩm quyền | Order |
| Kho không giữ nhiều hàng hơn số lượng có thể cấp | Có, nhưng trong ngữ cảnh Inventory | StockBalance/Reservation |
| Payment đã xử lý thành công mới được kết thúc quy trình bán | Cần phối hợp nhiều aggregate/ngữ cảnh | Quy trình nghiệp vụ; Order kiểm tra bằng chứng đã nhận |

Năm dòng đầu là cơ sở để nhóm Order và OrderLine thành aggregate. Quy tắc kho và thanh toán vẫn rất quan trọng, nhưng đưa toàn bộ Inventory và Payment vào Order chỉ để có một transaction thường khiến mô hình bị ghép chặt, tăng cạnh tranh ghi và khó tiến hóa.

**Bất biến được chọn theo nghiệp vụ**, không phải mọi mong muốn rằng dữ liệu trên các màn hình "luôn giống nhau". Chẳng hạn tổng tiền có thể được tính từ các dòng thay vì lưu trùng; nếu vẫn lưu, ứng dụng phải coi việc cập nhật dòng và tổng là một thay đổi nguyên tử.

## 3. Root kiểm soát thay đổi bằng hành vi

Aggregate root là **cửa vào ghi** của aggregate. Bên ngoài có thể biết một OrderLine tồn tại hoặc xem ảnh chụp của nó, nhưng không được sửa trực tiếp những trường mà Order cần kiểm soát.

Thiết kế thao tác có ý nghĩa miền:

| Thao tác | Điều kiện trước | Điều kiện sau |
| --- | --- | --- |
| addLine(product, price, qty) | Order là DRAFT; qty > 0; đơn giá hợp lệ | Dòng mới duy nhất, cùng loại tiền |
| changeQuantity(lineId, qty) | Order là DRAFT; dòng tồn tại; qty > 0 | Chỉ dòng được chỉ định đổi số lượng; tổng tính lại đúng |
| removeLine(lineId) | Order là DRAFT; dòng tồn tại | Dòng bị bỏ; đơn DRAFT có thể rỗng |
| confirm() | Order là DRAFT; có ít nhất một dòng; yêu cầu liên quan đã được kiểm tra | Status trở thành CONFIRMED; dòng hàng không còn được sửa |
| cancel() | Trạng thái được phép hủy theo chính sách | Status hợp lệ, phát sinh hành động bù nếu đã giữ hàng |

Hãy tránh API kiểu setStatus(value), setLines(value), setTotal(value) cho mã bên ngoài tùy ý thay đổi. Các setter đó dễ tạo trạng thái "CONFIRMED nhưng chưa có dòng" hoặc "tổng khác tổng chi tiết".

### Ví dụ Java rút gọn

Mã dưới minh họa một aggregate có hành vi rõ ràng. Phiên bản sử dụng Java 17+, giả định một loại tiền cho mỗi đơn và đơn giá có hai chữ số thập phân; đây là quy tắc của **ví dụ**, không phải chuẩn bắt buộc cho mọi loại tiền.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

record Money(BigDecimal amount, Currency currency) {
    Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);
        amount = amount.setScale(2, RoundingMode.UNNECESSARY);
        if (amount.signum() < 0) throw new IllegalArgumentException("Negative price");
    }

    Money plus(Money other) {
        if (!currency.equals(other.currency())) {
            throw new IllegalArgumentException("Currency mismatch");
        }
        return new Money(amount.add(other.amount), currency);
    }

    Money times(int quantity) {
        if (quantity <= 0) throw new IllegalArgumentException("Invalid quantity");
        return new Money(amount.multiply(BigDecimal.valueOf(quantity)), currency);
    }
}

record LineView(UUID id, String productId, Money unitPrice, int quantity) {}
enum Status { DRAFT, CONFIRMED, CANCELLED }

// Chỉ aggregate root sở hữu và điều phối map các dòng.
final class Order {
    private final UUID id;
    private final Currency currency;
    private final Map<UUID, LineView> lines = new LinkedHashMap<>();
    private Status status = Status.DRAFT;

    Order(UUID id, Currency currency) {
        this.id = Objects.requireNonNull(id);
        this.currency = Objects.requireNonNull(currency);
    }

    void addLine(UUID lineId, String productId, Money price, int quantity) {
        requireDraft();
        Objects.requireNonNull(lineId);
        Objects.requireNonNull(productId);
        Objects.requireNonNull(price);
        if (quantity <= 0) throw new IllegalArgumentException("quantity <= 0");
        if (!currency.equals(price.currency())) {
            throw new IllegalArgumentException("Currency mismatch");
        }
        if (lines.containsKey(lineId)) {
            throw new IllegalArgumentException("Duplicate line ID");
        }
        lines.put(lineId, new LineView(lineId, productId, price, quantity));
    }

    void changeQuantity(UUID lineId, int newQuantity) {
        requireDraft();
        if (newQuantity <= 0) throw new IllegalArgumentException("quantity <= 0");
        LineView old = lines.get(lineId);
        if (old == null) throw new IllegalArgumentException("Unknown line");
        lines.put(lineId,
            new LineView(old.id(), old.productId(), old.unitPrice(), newQuantity));
    }

    Money total() {
        Money sum = new Money(BigDecimal.ZERO, currency);
        for (LineView line : lines.values()) {
            sum = sum.plus(line.unitPrice().times(line.quantity()));
        }
        return sum;
    }

    void confirm() {
        requireDraft();
        if (lines.isEmpty()) throw new IllegalStateException("Empty order");
        status = Status.CONFIRMED;
    }

    Map<UUID, LineView> linesView() { return Map.copyOf(lines); }
    Status status() { return status; }
    UUID id() { return id; }

    private void requireDraft() {
        if (status != Status.DRAFT) {
            throw new IllegalStateException("Order is not editable");
        }
    }
}
~~~

Các dòng được biểu diễn bằng **bản ghi bất biến** (LineView). Root thay bản ghi khi đổi số lượng, vẫn giữ lineId. Bản ghi Java không cần là một object có thể sửa tại chỗ để khái niệm **dòng hàng có danh tính** trong nghiệp vụ tiếp tục tồn tại; danh tính và địa chỉ trong bộ nhớ là hai vấn đề khác nhau.

Phương thức linesView() trả về bản sao map không thể sửa từ bên ngoài; người gọi không nắm cấu trúc dữ liệu nội bộ để bỏ qua kiểm tra của root. Nếu lineView chứa thành phần có thể sửa được, vẫn phải tạo snapshot sâu phù hợp.

Đoạn mã cố ý chưa có repository, database transaction, lưu sự kiện hoặc chính sách thanh toán. Root giữ bất biến **trong bộ nhớ**; khi có nhiều tiến trình, hệ thống cần thêm cơ chế nhất quán ở tầng lưu trữ.

## 4. Quy tắc chọn ranh giới aggregate

Một phương pháp thiết kế thực tế:

1. **Viết command nghiệp vụ.** Ai ra lệnh, lệnh thay đổi điều gì? Ví dụ "xác nhận đơn", "đặt giữ 3 sản phẩm tại kho A".
2. **Viết bất biến sau command.** Điều gì bắt buộc đúng ngay khi thao tác ghi thành công? Phân biệt điều kiện tại một thời điểm với quy trình hoàn tất về sau.
3. **Tìm nhóm dữ liệu cần đọc/ghi nguyên tử.** Nếu hai phần tử luôn phải được kiểm soát cùng nhau để bảo vệ bất biến, chúng là ứng viên cho cùng aggregate.
4. **Chọn root mang ý nghĩa nghiệp vụ.** Root có ID, hành vi và quyền điều phối thành viên; không chọn chỉ vì nó là bảng cha có nhiều FK.
5. **Kiểm tra kích thước và cạnh tranh ghi.** Một root có hàng triệu thành viên hoặc bị sửa bởi mọi người dùng sẽ gây khóa, xung đột và chi phí nạp dữ liệu lớn.
6. **Xử lý quan hệ còn lại bằng ID và hợp đồng.** Định nghĩa dữ liệu nào là snapshot, dữ liệu nào tham chiếu, khi nào cần xác minh từ aggregate khác.

Ví dụ hàng tồn kho: thay vì cho **một** aggregate Warehouse quản lý mọi SKU tại mọi vị trí, có thể chọn StockBalance theo khóa (warehouseId, sku). Bất biến "không giữ quá lượng khả dụng" được thực thi độc lập cho từng SKU tại từng kho, giảm phạm vi tranh chấp.

Tuy nhiên, nếu nghiệp vụ yêu cầu chuyển hàng giữa hai kho phải đồng thời trừ kho nguồn và cộng kho đích, đó là **bất biến liên hai StockBalance**. Ta phải cân nhắc giao dịch cục bộ bao trùm hai root nếu chúng cùng nơi lưu và yêu cầu tuyệt đối nguyên tử, hoặc dùng quy trình chuyển kho có trạng thái trung gian và bước đối soát. Không nên giả vờ hai root tự cho tính nguyên tử xuyên hệ thống.

### Khi nào nên tách hoặc gộp?

| Dấu hiệu | Cách xem xét |
| --- | --- |
| Mọi thao tác phải nạp cả một cây dữ liệu rất lớn | Aggregate có thể quá rộng; tìm những bất biến thực sự cần nguyên tử |
| Hai nhóm dữ liệu luôn được cập nhật cùng nhau, liên tục lỗi do ghi dở | Có thể đã cắt qua một bất biến cục bộ; xem xét gộp hoặc tạo transaction rõ ràng |
| Một entity con được nhiều bộ phận sửa độc lập | Có thể có vòng đời riêng và nên trở thành root của aggregate khác |
| Hai root chỉ có nhu cầu hiển thị cạnh nhau | Giữ riêng; sử dụng truy vấn kết hợp/read model để đọc |
| Mỗi lần cập nhật một đối tượng lại khóa toàn bộ tổ chức | Ranh giới có thể quá lớn; chia theo đơn vị độc lập có thể cấp quyền quyết định |

**Không có công thức "aggregate càng nhỏ càng tốt" hay "aggregate phải bằng một document".** Điểm cân bằng được xác định bởi bất biến, mức tranh chấp và cách sử dụng dữ liệu.

## 5. Quan hệ bên trong và bên ngoài aggregate

### Thành viên nội bộ

OrderLine thường do Order kiểm soát: thêm dòng, xóa dòng và đổi số lượng đều cần kiểm tra trạng thái của Order. Một giao dịch ghi Order có thể thay đổi cả header và các dòng, nhưng tất cả phải commit/rollback như một đơn vị.

### Aggregate khác

Order có thể giữ customerId, sku hoặc productId mà không biến Customer/Stock/Product thành thành viên. Một ID bên ngoài là **tham chiếu**, không trao quyền sửa dữ liệu của đối tượng được tham chiếu.

Ví dụ Sales cần nhớ đơn giá 23.000.000 VND của mặt hàng vào lúc mua. Nếu chỉ giữ productId rồi luôn đọc giá mới nhất từ Catalog, đơn lịch sử sẽ thay đổi nghĩa khi Catalog sửa giá. Vì vậy OrderLine giữ **priceSnapshot** và **productNameSnapshot** theo giao dịch đã cam kết.

Đường đọc có thể ghép nhiều nguồn, còn đường ghi cần tuân thủ quyền sở hữu. Không đưa Order, Product và Customer vào cùng aggregate chỉ vì màn hình chi tiết đơn hiển thị cả ba.

### Root và repository

Repository được thiết kế quanh việc nạp/lưu aggregate root (ví dụ OrderRepository), không khuyến khích cung cấp OrderLineRepository cho nơi khác tùy ý sửa dòng. Một lớp truy vấn chuyên biệt phục vụ báo cáo có thể đọc dữ liệu ở cấp dòng mà không trở thành đường ghi phá bất biến.

Một lệnh ứng dụng điển hình:

~~~text
ChangeOrderQuantity(orderId, lineId, newQuantity, expectedVersion)
  -> Application service kiểm tra quyền
  -> OrderRepository nạp Order
  -> Order.changeQuantity(lineId, newQuantity)
  -> OrderRepository lưu Order với kiểm tra phiên bản
  -> Transaction commit
~~~

Từ ngoài aggregate, ta nhìn thấy root và thao tác nghiệp vụ; chi tiết các entity con vẫn được kiểm soát tại root.

## 6. Ánh xạ aggregate sang PostgreSQL

Ta giữ schema quan hệ gọn: Order và OrderLine ở **hai bảng**, dù cùng một aggregate; Money của đơn giá được lưu thành cột số tiền và tiền tệ ở Order.

~~~sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.orders (
    order_id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    currency CHAR(3) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sales.order_line (
    order_id UUID NOT NULL REFERENCES sales.orders(order_id),
    line_id UUID NOT NULL,
    product_id VARCHAR(64) NOT NULL,
    product_name_snapshot TEXT NOT NULL,
    unit_price_amount NUMERIC(19, 2) NOT NULL
        CHECK (unit_price_amount >= 0),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_id)
);
~~~

Giải thích lựa chọn:

- **orders.order_id** là danh tính của aggregate root. **(order_id, line_id)** xác định dòng **trong** Order, không ép mọi dòng có ID duy nhất toàn hệ thống.
- FK từ order_line sang orders bảo vệ quan hệ cục bộ. Khóa chính ghép đồng thời tạo chỉ mục bắt đầu bằng order_id, hỗ trợ tải các dòng của một đơn.
- **product_id** là mã tham chiếu sang Catalog. Các cột snapshot bảo vệ thông tin đã cam kết; chúng không cần tự cập nhật mỗi khi dữ liệu gốc thay đổi.
- CHECK và NOT NULL chặn một số dữ liệu sai ở cấp hàng. Chúng **không** tự bảo đảm Order CONFIRMED có ít nhất một dòng hay không được sửa dòng sau xác nhận.
- **version** phục vụ kiểm soát cập nhật đồng thời, không phải ID mới của Order mỗi lần cập nhật.

Khi cần hiển thị một đơn, truy vấn header và dòng trong cùng snapshot/transaction nếu yêu cầu kết quả nhất quán tại một thời điểm. Index bổ sung cho truy vấn theo customer_id và created_at chỉ nên được thiết kế sau khi biết workload, thứ tự sắp xếp và khối lượng dữ liệu thực tế.

### Transaction ghi phải bao trùm các thành viên

Ví dụ thao tác thêm dòng vào Order DRAFT với cơ chế **optimistic locking** ở root:

~~~sql
BEGIN;

-- Bước này cũng giữ khóa hàng Order đến cuối transaction.
UPDATE sales.orders
SET version = version + 1
WHERE order_id = :order_id
  AND status = 'DRAFT'
  AND version = :expected_version;

-- Ứng dụng PHẢI kiểm tra số hàng cập nhật = 1.
-- Nếu bằng 0: ROLLBACK, báo xung đột/trạng thái không hợp lệ.

INSERT INTO sales.order_line
    (order_id, line_id, product_id, product_name_snapshot,
     unit_price_amount, quantity)
VALUES
    (:order_id, :line_id, :product_id, :name_snapshot,
     :unit_price, :quantity);

COMMIT;
~~~

Trong ví dụ, application service đã nạp dữ liệu và gọi hành vi miền trước khi tạo lệnh SQL. Repository phải lưu cả phần thay đổi của aggregate trong **một transaction**. Nếu INSERT thất bại, toàn bộ transaction rollback, gồm cả lần tăng version.

Mọi lệnh thêm, sửa, xóa dòng hoặc chuyển trạng thái phải tham gia **cùng một giao thức khóa/phiên bản của root**. Nếu một tiến trình sửa trực tiếp order_line mà không tăng version hay kiểm tra trạng thái, quy tắc aggregate có thể bị phá mặc dù các lệnh chuẩn đã khóa đúng. Cần giới hạn đường ghi theo quyền DB, giao diện repository, và khi cần dùng constraint/trigger để phòng vệ.

### Xác nhận đơn và bất biến nhiều hàng

Xác nhận đơn cần kiểm tra ít nhất một dòng và status DRAFT. Một thao tác cập nhật điều kiện minh họa:

~~~sql
BEGIN;

UPDATE sales.orders AS o
SET status = 'CONFIRMED',
    version = version + 1
WHERE o.order_id = :order_id
  AND o.status = 'DRAFT'
  AND o.version = :expected_version
  AND EXISTS (
      SELECT 1
      FROM sales.order_line AS l
      WHERE l.order_id = o.order_id
  );

-- Kiểm tra đúng 1 hàng cập nhật, nếu không ROLLBACK.
COMMIT;
~~~

Lưu ý về đồng thời: câu EXISTS chỉ an toàn như một phần của **quy trình ghi nhất quán**. Nếu mọi thao tác xóa dòng cũng khóa Order trước rồi mới sửa order_line, không có tiến trình hợp lệ nào âm thầm xóa dòng cuối cùng trong khi xác nhận. Nếu có đường ghi bỏ qua root, điều kiện EXISTS một mình chưa bảo vệ được bất biến trước mọi kiểu race.

Các lựa chọn kỹ thuật thường dùng:

- **Optimistic locking:** đọc version, ghi có điều kiện version cũ, báo xung đột khi số hàng cập nhật bằng 0. Hợp với aggregate ít cạnh tranh ghi.
- **Pessimistic locking:** dùng SELECT ... FOR UPDATE hoặc cập nhật root để khóa bản ghi khi nhiều lệnh tranh chấp. Đổi lại có thời gian chờ và nguy cơ deadlock nếu thứ tự khóa không thống nhất.
- **Constraint:** PRIMARY KEY, UNIQUE, FOREIGN KEY, CHECK, exclusion constraint tùy loại quy tắc. Đây là lớp bảo vệ đáng tin cậy cho các ràng buộc mà DB diễn đạt được.

Chọn chiến lược theo nhu cầu nghiệp vụ, thông lượng, tỷ lệ xung đột và kiểu database; tránh chỉ dựa vào kiểm tra ở tầng ứng dụng rồi giả định sẽ luôn đúng khi có nhiều request.

## 7. Phân biệt bất biến cục bộ và quy trình xuyên aggregate

Giả sử Sales xác nhận đơn khi đã nhận đủ thông tin giữ hàng và thanh toán. Bốn aggregate có thể tham gia:

- Order trong Sales sở hữu dòng hàng, giá đã chốt và trạng thái đơn.
- StockBalance/Reservation trong Inventory sở hữu số lượng khả dụng và quyền giữ hàng.
- Payment trong Payment sở hữu kết quả ủy quyền/thu tiền và tham chiếu cổng thanh toán.
- Customer trong Customer Management sở hữu hồ sơ khách hàng.

Không đặt cả bốn dưới một root vì chúng có vòng đời và quy tắc thay đổi riêng. Một luồng phối hợp mẫu:

~~~mermaid
sequenceDiagram
    participant S as Sales / Order
    participant I as Inventory
    participant P as Payment
    S->>S: Tạo yêu cầu đơn chờ xác nhận
    S->>I: ReserveStock(requestId, sku, qty)
    I->>I: Kiểm tra và giữ hàng nguyên tử
    I-->>S: StockReserved(reservationId)
    S->>P: AuthorizePayment(paymentRequestId)
    P->>P: Ghi kết quả thanh toán
    P-->>S: PaymentAuthorized(paymentId)
    S->>S: Kiểm tra bằng chứng, confirm Order
~~~

Đây là mô hình phối hợp lý tưởng khi cả hai bước thành công. Để vận hành thực tế, phải tính cả luồng **từ chối giữ hàng, thất bại thanh toán, timeout, thông điệp trùng, đến trễ và hủy đặt giữ**.

- Inventory phải ngăn một SKU tại kho được giữ vượt lượng khả dụng trong transaction cục bộ, ví dụ cập nhật có điều kiện available >= quantity.
- Payment phải xử lý lệnh trùng theo một idempotency key ổn định, tránh thu tiền hai lần do retry.
- Sales cần ghi nhận kết quả từ các hệ thống kia theo mã yêu cầu/sự kiện và chỉ chuyển trạng thái khi các bằng chứng cần thiết đã được chấp nhận.
- Khi thất bại bước sau, quy trình cần hành động bù (ví dụ giải phóng giữ hàng); bù là thao tác nghiệp vụ, không phải rollback ACID xuyên nhiều dịch vụ.

Nếu dùng message broker, **transactional outbox** có thể giúp ghi thay đổi aggregate cùng sự kiện cần phát vào một transaction cục bộ. Người tiêu thụ vẫn cần khử trùng lặp và giải quyết thông điệp ngoài thứ tự. **Nhất quán cuối cùng** nghĩa là có trạng thái trung gian được định nghĩa, có cơ chế phục hồi/đối soát và có giới hạn độ trễ chấp nhận được.

### Một điều kiện cục bộ quan trọng ở Inventory

Khi nhiều Order yêu cầu giữ cùng một SKU, chính root kiểm soát StockBalance phải bảo vệ điều kiện available không âm:

~~~sql
-- Minh họa bước trừ tồn khả dụng nguyên tử trên một hàng.
UPDATE inventory.stock_balance
SET available = available - :quantity,
    reserved = reserved + :quantity
WHERE warehouse_id = :warehouse_id
  AND sku = :sku
  AND available >= :quantity;
~~~

Ứng dụng phải xác nhận đúng một hàng cập nhật, đồng thời ghi quyền giữ hàng trong **cùng transaction**. Lệnh này còn cần cơ chế idempotency dựa vào reservationRequestId để việc gửi lại không trừ tồn nhiều lần. Bảng và schema Inventory không được định nghĩa trong ví dụ SQL Sales ở phần trước; câu trên chỉ minh họa ràng buộc của một aggregate khác.

**Giới hạn quan trọng:** bảo đảm tồn của từng SKU độc lập không tự bảo đảm "phải giữ đủ mọi SKU trong một đơn hoặc không giữ gì". Nếu yêu cầu nguyên tử cho cả giỏ hàng nhiều SKU, cần thiết kế thêm transaction phù hợp trong cùng hệ quản trị hoặc một quy trình đặt giữ theo lô có rollback/bù rõ ràng.

## 8. Aggregate không nhất thiết tương ứng với một bản ghi vật lý

Trong thực tế có các dạng ánh xạ:

| Công nghệ | Cách biểu diễn | Cần kiểm tra |
| --- | --- | --- |
| **Cơ sở dữ liệu quan hệ** | Một root và thành viên qua nhiều bảng, được lưu trong transaction | FK, khóa, version, nhất quán giữa header/chi tiết; không sửa qua đường tắt |
| **Document database** | Một document Order lồng lines, address và price snapshot | Phạm vi ghi nguyên tử của hệ quản trị; kích thước document; phần tử có vòng đời riêng |
| **Graph database** | Root, thành viên và các tham chiếu có thể là node/edge | Quan hệ mạng không tự quy định ranh giới transaction hay quyền sửa |
| **Kho dữ liệu phân tích** | FactOrderLine, factPayment và các dimension | Projection phục vụ phân tích, có thể cập nhật trễ; không phải nguồn điều khiển bất biến giao dịch |

Một document Order có thể rất tiện để tải và lưu toàn bộ dòng hàng cùng nhau, nhưng nếu Order có hàng triệu sự kiện và dòng phụ thuộc, nhúng tất cả vào một document sẽ gây khó cập nhật và phình dữ liệu. Với database quan hệ, hai bảng vẫn có thể tạo **một aggregate logic** nhờ giao dịch. Chọn cấu trúc vật lý dựa trên bất biến, cách đọc/ghi, khả năng mở rộng và nhu cầu tiến hóa.

Một hệ thống phân tích có thể join Orders với Payments để tạo báo cáo, nhưng điều đó **không** có nghĩa hai miền được ghép thành một aggregate. Dữ liệu báo cáo thường là ảnh chụp hoặc projection với độ trễ xác định.

## 9. Các tình huống cạnh tranh cần kiểm chứng

### Hai yêu cầu sửa cùng một đơn

Giả sử T1 và T2 cùng đọc Order phiên bản 7. T1 đổi dòng số 1, T2 đổi dòng số 2. Nếu cả hai ghi lại toàn bộ đơn mà không kiểm tra, lần ghi sau có thể ghi đè lần trước (**lost update**). Khi dùng optimistic locking, T1 lưu thành công và tăng version lên 8, T2 ghi với expectedVersion = 7 bị từ chối; ứng dụng đọc lại rồi áp dụng lệnh theo chính sách phù hợp.

### Xác nhận trong lúc người khác xóa dòng cuối

Nếu một giao dịch đang xác nhận, giao dịch khác xóa dòng cuối, thứ tự khóa ở root và việc kiểm tra trạng thái phải bảo đảm **không tồn tại** đơn CONFIRMED không có dòng sau commit. Đây là ví dụ vì sao việc đặt quy tắc trong class Order vẫn cần transaction thích hợp ở DB.

### Hai đơn cùng mua một sản phẩm cuối cùng

Hai Order aggregate riêng đều có thể ở trạng thái hợp lệ. **Inventory** mới là nơi chịu trách nhiệm cấp quyền giữ sản phẩm cuối. Nếu cả hai Order tự kiểm tra số lượng qua một bản sao tồn kho, cả hai có thể chấp nhận cùng một mặt hàng. Cần kiểm tra và cập nhật số lượng tại chủ sở hữu tồn kho bằng thao tác nguyên tử.

### Một thông điệp gửi hai lần

Nếu cùng ReserveStock được gửi lại sau timeout, Inventory cần nhận biết requestId đã xử lý và trả kết quả nhất quán; root và transaction giữ tồn phải phối hợp với bảng ghi nhận request để không giữ hai lần. Nguyên tắc tương tự áp dụng cho lệnh thanh toán và xử lý sự kiện từ hệ thống khác.

## 10. Những lỗi thiết kế aggregate thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chọn aggregate bằng tất cả quan hệ FK | Root quá lớn, transaction đắt, nhiều xung đột | Nhóm theo bất biến cục bộ và quyền ghi |
| Mỗi bảng là một aggregate | Quy tắc nhiều bảng dễ bị ghi dở, thiếu root điều phối | Gom các thành viên có bất biến cần bảo vệ cùng nhau |
| Cho phép sửa trực tiếp entity con qua repository công khai | Bỏ qua điều kiện trạng thái của root | Cho thao tác ghi đi qua hành vi root và transaction |
| Dùng một trạng thái chung cho mọi dịch vụ | Sai lệch ngữ nghĩa; hệ thống phụ thuộc nhau | Phân định dữ liệu sở hữu và hợp đồng tích hợp |
| Dùng optimistic locking nhưng không cập nhật version khi sửa dòng | Hai request có thể ghi đè hoặc phá bất biến | Mọi lệnh ghi aggregate dùng chung quy trình khóa/version |
| Coi mọi điều kiện xuyên aggregate đều phải đúng ngay trong một transaction phân tán | Khó chịu lỗi, tăng liên kết và khóa | Phân loại bất biến cục bộ với quy trình liên ngữ cảnh |
| Dùng sự kiện mà không có idempotency/retry | Giữ hàng, thanh toán hoặc cập nhật lặp | Dùng requestId/eventId, outbox/inbox và xử lý trùng |
| Dùng bảng báo cáo như nguồn ghi chính | Trạng thái trễ có thể gây quyết định sai | Đọc nguồn có thẩm quyền khi thực hiện command |

## 11. Bài tập thực hành: đặt ghế xem phim

**Tình huống:** Nền tảng bán vé có các suất chiếu. Một khách muốn giữ hai ghế A1 và A2 trong 5 phút. Ghế còn khả dụng phải không được giữ đồng thời cho khách khác. Khi thanh toán thành công, hệ thống phát hành vé. Khách có thể bấm thanh toán hai lần vì kết nối chậm.

**Yêu cầu:**

1. Đề xuất aggregate root cho **Booking** và cho quyền giữ **một ghế tại một suất chiếu**. Chỉ ra dữ liệu nằm trong mỗi aggregate và danh tính phù hợp.
2. Viết ba bất biến cục bộ và một quy tắc cần phối hợp xuyên aggregate.
3. Phân tích hai yêu cầu cùng giữ ghế A1; nêu cơ chế DB hoặc repository giúp ngăn giữ trùng.
4. Nếu nghiệp vụ yêu cầu **giữ đủ A1 và A2 hoặc không giữ ghế nào**, ranh giới aggregate cần thay đổi thế nào? Có thể chỉ dùng hai transaction độc lập không?
5. Khi thanh toán timeout rồi hệ thống retry, làm sao tránh phát hành vé hai lần và thu tiền hai lần?

**Hướng giải định hướng:**

- Booking có bookingId và các thông tin vé/giá đã chốt, trạng thái và danh sách ghế yêu cầu. Quyền chiếm một ghế có thể được quản lý bởi root SeatAllocation/SeatReservation với danh tính gắn (showtimeId, seatId), trạng thái và hạn giữ.
- Bất biến cục bộ gồm: Booking đã xác nhận không thay giá vé; thời điểm hết hạn giữ phải sau thời điểm bắt đầu giữ; một ghế của một suất chiếu không có hai quyền giữ còn hiệu lực. Quy tắc xuyên aggregate: chỉ phát hành vé khi giữ ghế còn hiệu lực và trạng thái thanh toán thỏa điều kiện.
- Chống giữ trùng cần thao tác **nguyên tử** tại bên quản lý ghế, bằng transaction/khóa và constraint phù hợp với trạng thái hiện tại. Đọc "ghế còn trống" từ màn hình rồi ghi sau mà không có khóa/điều kiện là không đủ khi có nhiều request.
- Nếu A1 và A2 bắt buộc được giữ như một lô nguyên tử, hãy cân nhắc một transaction tại dịch vụ Seat Allocation kiểm soát cả hai ghế theo thứ tự khóa ổn định. Có thể thiết kế aggregate theo đơn vị kho ghế/suất chiếu phù hợp nhưng phải cân nhắc contention và kích thước. Nếu việc đặt giữ trải qua nhiều hệ thống, cần quy trình điều phối và bù; hai commit độc lập không tự tạo tính "all-or-nothing".
- Với thanh toán và phát hành vé, dùng idempotency key, định danh paymentAttempt và booking, kiểm soát chuyển trạng thái và ghi nhận sự kiện đã xử lý. Có quy trình xử lý hạn giữ, hoàn tiền/giải phóng ghế khi trạng thái giữa các bên không khớp.

Không có một đáp án aggregate duy nhất cho mọi hệ thống bán vé. Điều cần đánh giá là khả năng bảo vệ bất biến, mức cạnh tranh đặt ghế, yêu cầu giữ nguyên tử nhiều ghế, cách lưu dữ liệu và quy trình bù khi thất bại.

## 12. Checklist trước khi triển khai

- Mỗi aggregate có **root được đặt tên theo nghiệp vụ**, ID và vòng đời rõ ràng chưa?
- Những bất biến nào phải đúng sau **mỗi commit cục bộ**? Bất biến nào chỉ đạt sau một quy trình nhiều bước?
- Entity con và value object có được thay đổi **qua root** không? Có đường ghi trực tiếp nào bỏ qua kiểm tra không?
- Mọi thao tác sửa aggregate có dùng chung **transaction + khóa/phiên bản** và xử lý xung đột không?
- Quan hệ với aggregate khác có được biểu diễn bằng ID/hợp đồng, và dữ liệu lịch sử đã được lưu snapshot đúng nơi chưa?
- Transaction có quá rộng, aggregate có quá lớn hoặc tạo điểm nghẽn cập nhật không?
- Những trường hợp request đồng thời, thông điệp lặp, hết hạn và lỗi giữa chừng đã có kịch bản kiểm tra chưa?
- Quy tắc nào do DB bảo vệ trực tiếp, quy tắc nào do lớp miền/ứng dụng thực thi, và có cơ chế phòng vệ khi dữ liệu bị ghi ngoài quy trình không?

**Kết luận:** Aggregate là **ranh giới để bảo vệ bất biến**, còn aggregate root là **điểm điều phối thay đổi** trong ranh giới ấy. Thiết kế đúng không chỉ vẽ quan hệ giữa các thực thể mà còn định nghĩa command, điều kiện trước/sau, transaction, kiểm soát cạnh tranh và hợp đồng với các aggregate khác. Đó là cách chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng, có thể kiểm chứng và tiến hóa khi hệ thống mở rộng.
