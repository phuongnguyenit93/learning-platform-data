# Thiết kế mô hình khách hàng–sản phẩm–đơn hàng và hợp đồng repository

## 1. Mục tiêu của bài thực hành

Trong chương **Thực hành tổng hợp** của **SPRING_DATA_COMMONS**, bài này thiết kế một hệ thống đặt hàng nhỏ để kết nối mô hình domain với hợp đồng repository.

Trọng tâm là quyết định:

- Đối tượng nào là aggregate root và có repository riêng.
- Dữ liệu nào là tham chiếu, dữ liệu nào là snapshot.
- Những invariant nào phải được giữ trong một đơn hàng.
- Mỗi use case cần kiểu kết quả và thao tác repository nào.
- Phần nào thuộc abstraction Commons, phần nào phải do module store thực hiện.

Bài thực hành không yêu cầu dùng mọi API Spring Data. Một thiết kế tốt chọn những abstraction phù hợp và giải thích được khả năng của store đã chọn.

Kết quả cần đạt là một mô hình có quy tắc rõ cùng các interface đủ cụ thể để triển khai và kiểm thử, không chỉ ba class có getter/setter và ba repository CRUD toàn quyền.

## 2. Phạm vi nghiệp vụ và các quyết định ban đầu

Hệ thống cần hỗ trợ:

1. Đăng ký và tra cứu khách hàng.
2. Tạo, đổi thông tin và ngừng bán sản phẩm.
3. Tạo đơn nháp cho một khách hàng đang hoạt động.
4. Thêm sản phẩm vào đơn theo giá được chụp tại thời điểm thêm dòng.
5. Xác nhận một đơn hợp lệ.
6. Hủy đơn theo quy tắc trạng thái.
7. Xem chi tiết và danh sách đơn của khách hàng.

Các quy tắc được chọn cho bài:

| Quy tắc | Quyết định |
| --- | --- |
| Email khách hàng | Có emailKey chuẩn hóa theo chính sách ứng dụng và không trùng |
| SKU sản phẩm | Có skuKey ổn định và không trùng |
| Tiền tệ | Mỗi đơn dùng một loại tiền tệ |
| Giá bán lịch sử | Giữ snapshot tại dòng đơn, không đọc lại giá hiện tại để tính đơn cũ |
| Sản phẩm xuất hiện nhiều lần | Từ chối dòng trùng productId; sửa số lượng bằng thao tác riêng nếu bổ sung |
| Số lượng | Từ 1 đến 1000 mỗi dòng trong bài |
| Đơn rỗng | Được tồn tại ở trạng thái nháp, không được xác nhận |
| Sửa dòng | Chỉ được thực hiện khi đơn còn nháp |
| Tồn kho và thanh toán | Chưa thuộc phạm vi bài |
| Xóa dữ liệu lịch sử | Không xóa đơn chỉ vì khách hàng hoặc sản phẩm ngừng hoạt động |

Giới hạn 1000 và chính sách snapshot là quyết định của bài, không phải mặc định của Spring Data.

EmailKey cần có quy tắc chuẩn hóa được mô tả rõ. Không coi việc viết thường toàn bộ email là quy luật kỹ thuật bắt buộc của mọi hệ thống; đó phải là chính sách nghiệp vụ được chọn.

## 3. Chia thành ba aggregate root

~~~mermaid
flowchart LR
    C[Customer: aggregate root]
    P[Product: aggregate root]
    O[PurchaseOrder: aggregate root]
    L[OrderLine: thành phần thuộc đơn]

    O -->|customerId và snapshot tên| C
    O -->|sở hữu vòng đời| L
    L -->|productId và snapshot sản phẩm/giá| P
~~~

Các mũi tên tham chiếu không yêu cầu một kiểu annotation quan hệ cụ thể. Đây là mô hình nghiệp vụ trước khi chọn mapping.

### Customer

Customer quản lý danh tính và trạng thái khách hàng. Việc đổi tên khách hàng không tự viết lại snapshot tên trên mọi đơn cũ.

### Product

Product quản lý SKU, tên, giá hiện tại và khả năng bán. Đổi giá sản phẩm không tự thay đổi dòng đơn đã được tạo.

### PurchaseOrder

PurchaseOrder quản lý toàn bộ vòng đời đơn cùng các dòng. Những invariant như không trùng sản phẩm, cùng tiền tệ và không xác nhận đơn rỗng được kiểm soát tại root.

### OrderLine

OrderLine thuộc PurchaseOrder, không được cập nhật độc lập để bỏ qua invariant của đơn.

Trong phạm vi bài, không có OrderLineRepository công khai. Có bảng hoặc collection con ở mức lưu trữ không tự làm đối tượng đó trở thành aggregate root.

## 4. Xác định dữ liệu của từng mô hình

### Customer

| Property | Kiểu gợi ý | Ý nghĩa |
| --- | --- | --- |
| id | UUID | Identifier kỹ thuật |
| displayName | String | Tên hiện tại |
| email | String | Biểu diễn email được lưu theo chính sách |
| emailKey | String | Khóa chuẩn hóa phục vụ tra cứu và duy nhất |
| active | boolean | Có được tạo đơn mới không |
| version | Long | Metadata optimistic locking nếu module hỗ trợ |
| createdAt, lastModifiedAt | Instant | Metadata auditing theo cấu hình |

### Product

| Property | Kiểu gợi ý | Ý nghĩa |
| --- | --- | --- |
| id | UUID | Identifier kỹ thuật |
| skuKey | String | Khóa SKU chuẩn hóa, không trùng |
| name | String | Tên hiện tại |
| price | Money | Giá hiện tại |
| active | boolean | Có được thêm vào dòng đơn mới không |
| version | Long | Metadata cạnh tranh nếu được hỗ trợ |
| createdAt, lastModifiedAt | Instant | Metadata auditing |

### PurchaseOrder

| Property | Kiểu gợi ý | Ý nghĩa |
| --- | --- | --- |
| id | UUID | Identifier đơn |
| customerId | UUID | Tham chiếu đến Customer |
| customerNameSnapshot | String | Tên tại thời điểm tạo đơn |
| currency | String | Tiền tệ của đơn |
| status | OrderStatus | Trạng thái |
| lines | List<OrderLine> | Dữ liệu thuộc aggregate |
| confirmedAt | Instant | Thời điểm nghiệp vụ xác nhận |
| version | Long | Phiên bản cập nhật |
| createdAt, lastModifiedAt | Instant | Metadata auditing |

### OrderLine

| Property | Kiểu gợi ý | Ý nghĩa |
| --- | --- | --- |
| productId | UUID | Tham chiếu sản phẩm |
| skuSnapshot | String | SKU tại thời điểm tạo dòng |
| productNameSnapshot | String | Tên tại thời điểm tạo dòng |
| unitPrice | Money | Giá được chốt cho dòng |
| quantity | int | Số lượng |

UUID là lựa chọn của bài. Module store có thể lưu UUID theo những biểu diễn khác nhau; cần mapping và conversion phù hợp. Không yêu cầu store nào cũng tự sinh UUID theo cùng cơ chế.

## 5. Phân biệt identifier với khóa nghiệp vụ

Customer.id và Product.id được dùng làm tham chiếu giữa các aggregate. EmailKey và skuKey phục vụ các quy tắc tra cứu/duy nhất.

Không dùng tên khách hàng hoặc tên sản phẩm làm identifier vì chúng có thể thay đổi và không duy nhất.

Một kiểm tra như:

~~~java
if (customers.existsByEmailKey(emailKey)) {
    throw new DuplicateCustomerEmailException(emailKey);
}
~~~

có thể giúp đưa ra phản hồi sớm, nhưng chưa bảo vệ được hai request đồng thời cùng đăng ký một email.

Cần cơ chế bảo đảm duy nhất phù hợp ở store, chẳng hạn constraint, unique index hoặc thao tác có điều kiện được hỗ trợ. Sau đó ứng dụng chuyển xung đột thực tế thành kết quả nghiệp vụ thích hợp.

Tương tự, version cần được mapping và tham gia đúng đường cập nhật. Một field tên version không tự kích hoạt optimistic locking.

### ID được cấp trước và nhận diện đối tượng mới

Nếu ứng dụng cấp UUID trước khi save, ID khác null không tự chứng minh đối tượng đã tồn tại. Cần hiểu cơ chế isNew của module, ảnh hưởng của version và tùy chọn Persistable nếu chọn dùng.

Không sửa thiết kế bằng cách tùy tiện bỏ ID hoặc version chỉ để ép một nhánh insert/update.

## 6. Value object Money và quy tắc số lượng

Ví dụ Java 17:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;
import java.util.Objects;

public record Money(BigDecimal amount, String currency) {

    public Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");

        currency = currency.strip().toUpperCase(Locale.ROOT);
        if (!currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException("Mã tiền tệ không hợp lệ");
        }

        if (amount.signum() < 0) {
            throw new IllegalArgumentException("Số tiền không được âm");
        }

        amount = amount.setScale(2, RoundingMode.UNNECESSARY);
    }

    public Money plus(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("Khác tiền tệ");
        }
        return new Money(amount.add(other.amount), currency);
    }

    public Money times(int quantity) {
        if (quantity < 1 || quantity > 1000) {
            throw new IllegalArgumentException("Số lượng ngoài phạm vi");
        }
        return new Money(
                amount.multiply(BigDecimal.valueOf(quantity)),
                currency);
    }
}
~~~

Bài dùng quy ước hai chữ số thập phân cho dữ liệu thực hành. Regex chỉ kiểm tra hình dạng mã, không phải danh mục tiền tệ được phép của sản phẩm. Nếu ứng dụng hỗ trợ nhiều loại tiền tệ, cần chính sách đơn vị nhỏ nhất và tập mã hợp lệ cụ thể.

Không tạo BigDecimal từ double cho các giá trị cần biểu diễn thập phân chính xác trong fixture.

OrderLine:

~~~java
import java.util.Objects;
import java.util.UUID;

public record OrderLine(
        UUID productId,
        String skuSnapshot,
        String productNameSnapshot,
        Money unitPrice,
        int quantity) {

    public OrderLine {
        Objects.requireNonNull(productId, "productId");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (skuSnapshot == null || skuSnapshot.isBlank()) {
            throw new IllegalArgumentException("Thiếu SKU snapshot");
        }
        if (productNameSnapshot == null || productNameSnapshot.isBlank()) {
            throw new IllegalArgumentException("Thiếu tên snapshot");
        }
        if (quantity < 1 || quantity > 1000) {
            throw new IllegalArgumentException("Số lượng ngoài phạm vi");
        }
    }

    public Money subtotal() {
        return unitPrice.times(quantity);
    }
}
~~~

Record ở đây mô tả value object. Khả năng mapping record hoặc embedded value cần được kiểm tra trong module đã chọn, không suy ra chỉ từ việc Java biên dịch được.

## 7. Đặt invariant tại PurchaseOrder

Trạng thái:

~~~java
public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
~~~

Chuyển trạng thái của bài:

~~~text
DRAFT → CONFIRMED
DRAFT → CANCELLED
CONFIRMED → CANCELLED
CANCELLED không quay lại trạng thái khác.
~~~

Không mô hình hóa hoàn tiền hoặc hoàn kho trong bài này vì chưa có nghiệp vụ thanh toán/tồn kho.

Phần logic root có thể được phác thảo:

~~~java
public void addLine(OrderLine line) {
    requireDraft();

    if (!currency.equals(line.unitPrice().currency())) {
        throw new IllegalArgumentException("Dòng đơn khác tiền tệ");
    }

    boolean duplicated = lines.stream()
            .anyMatch(existing ->
                    existing.productId().equals(line.productId()));

    if (duplicated) {
        throw new IllegalStateException(
                "Sản phẩm đã có trong đơn");
    }

    lines.add(line);
}

public Money total() {
    Money total = new Money(BigDecimal.ZERO, currency);

    for (OrderLine line : lines) {
        total = total.plus(line.subtotal());
    }

    return total;
}

public void confirm(Instant confirmedAt) {
    requireDraft();

    if (lines.isEmpty()) {
        throw new IllegalStateException(
                "Không thể xác nhận đơn rỗng");
    }

    this.confirmedAt = Objects.requireNonNull(confirmedAt);
    this.status = OrderStatus.CONFIRMED;
}

private void requireDraft() {
    if (status != OrderStatus.DRAFT) {
        throw new IllegalStateException(
                "Chỉ được sửa đơn nháp");
    }
}
~~~

Đây là các phương thức thuộc một PurchaseOrder đã có các field trong bảng thiết kế; không phải toàn bộ class cùng mapping persistence.

Root không trả ra một List mutable để caller gọi add/remove trực tiếp. Có thể trả snapshot bất biến hoặc một view phù hợp để việc sửa phải đi qua phương thức giữ invariant.

confirmedAt là thời điểm nghiệp vụ do use case cung cấp, có thể lấy từ Clock được inject. createdAt/lastModifiedAt là metadata auditing. Không để cả domain và auditing cùng ghi một field thời gian mà không có quy tắc rõ.

## 8. Snapshot giúp giữ lịch sử đúng nghĩa

Giả sử:

~~~text
P1: name = Keyboard, price = 100.00 USD.
P2: name = Mouse, price = 50.00 USD.

Đơn O1:
P1 × 2 → 200.00 USD.
P2 × 1 → 50.00 USD.
Tổng = 250.00 USD.
~~~

Sau đó P1 đổi tên hoặc đổi giá thành 160.00 USD. O1 vẫn giữ giá dòng 100.00 USD.

Không tính lại O1 bằng cách đọc Product.price hiện tại.

Tương tự, khi khách hàng đổi tên, customerNameSnapshot không tự thay đổi. Thông tin hiện tại và thông tin lịch sử là hai nhu cầu đọc khác nhau.

### Thời điểm chốt giá

Bài chọn chốt giá lúc thêm dòng. Xác nhận đơn giữ nguyên snapshot đó.

Nếu sản phẩm thực tế cần kiểm tra lại giá lúc xác nhận, phải có quy tắc reprice rõ ràng. Không thay đổi giá âm thầm bằng một callback persistence.

Sản phẩm phải active khi thêm dòng mới theo quy tắc bài. Một sản phẩm ngừng bán sau đó không tự xóa dòng lịch sử.

## 9. Hợp đồng repository bắt đầu từ use case

Không cần expose mọi method của một interface CRUD nếu ứng dụng không cho phép mọi thao tác đó.

Có thể kế thừa Repository và khai báo những thao tác cần dùng. Ví dụ:

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.repository.Repository;

public interface CustomerRepository
        extends Repository<Customer, UUID> {

    Optional<Customer> findById(UUID id);

    Optional<Customer> findByEmailKey(String emailKey);

    boolean existsByEmailKey(String emailKey);

    <S extends Customer> S save(S customer);
}
~~~

Product:

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.repository.Repository;

public interface ProductRepository
        extends Repository<Product, UUID> {

    Optional<Product> findById(UUID id);

    Optional<Product> findBySkuKey(String skuKey);

    Iterable<Product> findAllById(Iterable<UUID> ids);

    Slice<Product> findByActiveTrueAndNameContainingIgnoreCase(
            String keyword,
            Pageable pageable);

    <S extends Product> S save(S product);
}
~~~

Đây là hợp đồng minh họa cho module hỗ trợ các dạng CRUD và derived query tương ứng. ContainingIgnoreCase, slicing và kiểu kết quả cần được xác minh trên store thật.

Nếu module không hỗ trợ một truy vấn theo tên, có thể giữ ý định nghiệp vụ thông qua fragment triển khai tường minh thay vì giả định tính di động tuyệt đối.

Không expose delete chỉ vì có sẵn. Trong phạm vi bài, ngừng hoạt động là thay đổi trạng thái; lịch sử đơn vẫn cần được giữ.

## 10. Hợp đồng đọc và ghi của đơn hàng

Một projection phục vụ danh sách:

~~~java
import java.time.Instant;
import java.util.UUID;

public interface OrderSummary {
    UUID getId();
    UUID getCustomerId();
    OrderStatus getStatus();
    Instant getCreatedAt();
}
~~~

Repository:

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.repository.Repository;

public interface PurchaseOrderRepository
        extends Repository<PurchaseOrder, UUID> {

    Optional<PurchaseOrder> findById(UUID id);

    Page<OrderSummary> findByCustomerId(
            UUID customerId,
            Pageable pageable);

    Slice<OrderSummary> findByCustomerIdAndStatus(
            UUID customerId,
            OrderStatus status,
            Pageable pageable);

    <S extends PurchaseOrder> S save(S order);
}
~~~

Các property trong method và projection phải tồn tại theo mô hình domain/mapping. Tên cột hoặc field vật lý có thể khác.

### Chọn kiểu trả về theo yêu cầu

| Use case | Kiểu hợp đồng |
| --- | --- |
| Xem chi tiết một đơn | Optional<PurchaseOrder> |
| Danh sách cần tổng số | Page<OrderSummary> |
| Danh sách chỉ cần xem tiếp | Slice<OrderSummary> |
| Ghi aggregate | Kết quả save để lấy instance/metadata hiệu lực |
| Duyệt dữ liệu lớn | Hợp đồng window/stream riêng khi có yêu cầu |

Không dùng findAll rồi lọc customerId tại Java. Điều kiện thuộc query.

Không giả định projection luôn làm query lấy ít field; cần kiểm tra implementation và dữ liệu thực tế. Tuy vậy, projection thể hiện rõ ý định đọc của use case.

### Nếu danh sách cần tổng tiền

Ví dụ OrderSummary chưa có total vì tổng đang được tính từ các dòng trong domain.

Nếu danh sách cần tổng tiền, phải chọn một thiết kế rõ:

- Lưu một trường tổng hợp và cập nhật nó trong cùng invariant của đơn.
- Hoặc viết query/aggregation phù hợp với store.
- Hoặc dùng một read model có hợp đồng cập nhật riêng.

Không thêm getTotal() vào projection rồi giả định framework tự dịch mọi vòng lặp Java qua OrderLine thành một phép tính ở store.

## 11. Dùng fragment khi tìm kiếm vượt khỏi tên method dễ đọc

Ví dụ cần tìm đơn theo nhiều điều kiện tùy chọn:

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderCriteria(
        UUID customerId,
        OrderStatus status,
        Instant createdFrom,
        Instant createdBefore) {
}
~~~

~~~java
public interface OrderSearch {
    Slice<OrderSummary> search(
            OrderCriteria criteria,
            Pageable pageable);
}
~~~

Có thể ghép OrderSearch vào repository và triển khai theo module.

Hợp đồng phải định nghĩa:

- Null ở từng điều kiện có nghĩa là không lọc hay là giá trị cần tìm.
- Khoảng thời gian có bao gồm điểm đầu/cuối không.
- Sort mặc định.
- Page size tối đa.
- Kiểu kết quả và metadata có sẵn.
- Hành vi khi điều kiện không hợp lệ.

Fragment không làm truy vấn tự trở nên độc lập với store. Nó giúp tách một hợp đồng rõ khỏi cách triển khai cụ thể.

Query by Example có thể phù hợp cho một số bộ lọc đơn giản khi module hỗ trợ, nhưng không nên dùng nó thay cho mọi truy vấn khoảng, quan hệ hoặc aggregation.

## 12. Điều phối use case tạo đơn

Một luồng hợp lý:

~~~text
1. Kiểm tra command: customerId, currency, danh sách dòng.
2. Tìm Customer và kiểm tra active.
3. Thu thập các productId, phát hiện dòng trùng theo chính sách.
4. Tải các Product cần thiết.
5. Đối chiếu ID yêu cầu với kết quả thực tế.
6. Kiểm tra active, tiền tệ và số lượng.
7. Tạo PurchaseOrder và các OrderLine snapshot.
8. Lưu root.
9. Trả kết quả dựa trên instance được save trả về.
~~~

findAllById không phải cam kết kết quả giữ nguyên thứ tự đầu vào hoặc luôn có đủ mọi ID. Cần lập map theo ID và phát hiện sản phẩm thiếu.

Cũng không mặc định findAllById luôn tạo đúng một query IN. Cách thực thi phụ thuộc module và giới hạn store.

### Ranh giới transaction

Nếu use case cần một transaction, đặt nó ở điểm vào service phù hợp và gọi qua cơ chế transaction đang dùng. Mỗi repository tự có transaction không tự làm cả use case nguyên tử.

Transaction manager phải quản lý đúng tài nguyên. Nếu các aggregate nằm ở nhiều store, không thể mặc định một annotation tạo ra transaction phân tán.

Đọc giá sản phẩm trong transaction cũng chưa tự định nghĩa mọi vấn đề cạnh tranh. Bài chọn giữ snapshot giá đã đọc; nếu cần quy tắc mạnh hơn tại thời điểm xác nhận, phải thiết kế isolation, khóa hoặc kiểm tra version phù hợp.

### Đơn hàng cập nhật đồng thời

Hai request cùng sửa đơn có thể làm mất thay đổi nếu không có bảo vệ thích hợp. Khi module hỗ trợ optimistic locking, cần mapping version và kiểm tra xung đột thật.

Không tự retry mọi xung đột bằng cách ghi lại command mà chưa xem thao tác có thể lặp và snapshot giá có được phép thay đổi không.

## 13. Mapping theo store nhưng giữ ranh giới nghiệp vụ

| Khía cạnh | Relational/JPA | Document | Aggregate-oriented relational như JDBC |
| --- | --- | --- | --- |
| Root | Entity được mapping | Document root | Aggregate root được mapping |
| Dòng đơn | Thành phần/value collection hoặc entity nội bộ theo thiết kế | Có thể nhúng trong document đơn | Thành phần thuộc aggregate, thường có biểu diễn bảng con |
| Product tham chiếu | ID hoặc quan hệ được chọn rõ | ID/reference phù hợp | Tham chiếu sang aggregate khác |
| Snapshot giá | Cột hoặc cấu trúc value | Field/document nhúng | Mapping value theo module |
| Transaction | Theo provider, manager và database | Theo khả năng store/topology | Theo manager và database |
| Auditing/version | Annotation/cấu hình tương ứng | Annotation/cấu hình tương ứng | Annotation/cấu hình tương ứng |

Bảng không khẳng định mọi module có cùng khả năng cascade hoặc traversal.

Không cấu hình xóa Customer/Product chỉ vì xóa một PurchaseOrder. Chúng là aggregate độc lập, còn OrderLine mới thuộc vòng đời đơn trong bài.

Với document nhúng, cần kiểm tra kích thước và số dòng được phép. Với relational, cần kiểm tra constraint, join và cách tải collection.

Money, UUID và Instant cần được mapping đúng. Nếu dùng converter, kiểm tra cả giá trị domain và raw representation, nhất là precision tiền và thời gian.

## 14. Metadata auditing và sự kiện nghiệp vụ

Auditing có thể điền createdAt, lastModifiedAt và thông tin người thao tác theo khả năng module.

Nên chọn một nguồn thời gian điều khiển được trong test. Không dựa vào sleep để phân biệt lần tạo và cập nhật.

Cần phân biệt:

~~~text
createdAt: metadata tạo bản ghi/aggregate theo chính sách.
confirmedAt: thời điểm nghiệp vụ chuyển sang CONFIRMED.
~~~

Nếu bổ sung sự kiện OrderConfirmed, root đăng ký nó khi chuyển trạng thái đúng. Việc đăng ký/publish sự kiện qua repository không tự đồng nghĩa transaction đã commit hoặc thông điệp đã được giao bền vững ra hệ thống ngoài.

Bài thiết kế hợp đồng không yêu cầu triển khai đầy đủ messaging. Chỉ cần nêu rõ nếu có side effect sau xác nhận thì nó thuộc giai đoạn nào và có phụ thuộc commit hay không.

Không đưa validation quan trọng của đơn vào một callback mà các đường ghi khác có thể bỏ qua. Invariant nghiệp vụ cần nằm ở mô hình hoặc use case thích hợp; callback phục vụ vai trò tích hợp được xác định rõ.

## 15. Fixture và bằng chứng cần có

Dùng các nhãn C1, P1, P2, O1 để mô tả fixture; khi triển khai cần gán UUID cụ thể.

| Đối tượng | Dữ liệu |
| --- | --- |
| C1 | Khách hàng active |
| C2 | Khách hàng inactive |
| P1 | Active, 100.00 USD |
| P2 | Active, 50.00 USD |
| P3 | Inactive |
| O1 | C1, P1 số lượng 2 và P2 số lượng 1 |

Kỳ vọng O1 có tổng 250.00 USD.

Sau khi P1 đổi giá, đọc lại O1 phải giữ giá snapshot. Sau khi C1 đổi tên, snapshot trên O1 giữ nguyên theo chính sách bài.

Các ca kiểm chứng trọng tâm:

| Nhóm | Ca kiểm chứng |
| --- | --- |
| Domain | Quantity bằng 0 bị từ chối |
| Domain | Hai dòng cùng productId bị từ chối |
| Domain | Trộn tiền tệ bị từ chối |
| Domain | Xác nhận đơn rỗng bị từ chối |
| Domain | Sửa dòng sau xác nhận bị từ chối |
| Use case | Khách hàng hoặc sản phẩm không tồn tại được báo rõ |
| Use case | Khách hàng inactive không tạo đơn mới |
| Use case | Sản phẩm inactive không thêm dòng mới |
| Snapshot | Đổi giá/tên hiện tại không viết lại lịch sử |
| Repository | Derived query trả đúng khách hàng và trạng thái |
| Repository | Projection và sort hoạt động đúng |
| Store | Khóa emailKey/skuKey được bảo vệ khi cạnh tranh |
| Store | Version phát hiện cập nhật stale nếu dùng optimistic locking |
| Mapping | Money, UUID, Instant và lines đọc/ghi đúng |

Unit test có mock phù hợp để kiểm tra điều phối service. Query derivation, mapping, constraint và optimistic locking cần integration test trên module/store thật.

## 16. Tiêu chí hoàn thành thiết kế

Một bản thiết kế đạt yêu cầu cần giải thích được:

1. Vì sao Customer, Product và PurchaseOrder có repository riêng.
2. Vì sao OrderLine không được sửa qua repository công khai riêng.
3. Những dữ liệu nào được snapshot và lúc nào chốt snapshot.
4. Invariant nào nằm ở root, invariant nào cần kiểm tra ở use case/store.
5. Vì sao mỗi method repository có kiểu trả về đã chọn.
6. Cách bảo đảm duy nhất và xử lý cạnh tranh.
7. Cách mapping theo store cùng những tính năng không được hỗ trợ.
8. Cách kiểm thử hợp đồng bằng dữ liệu phân biệt được lỗi.

Không cần ép mọi store có cùng schema hoặc cùng annotation. Điều cần giữ là hợp đồng nghiệp vụ và các giới hạn đã được thừa nhận.

Một interface có nhiều method không tự chứng minh thiết kế tốt. Method nên tồn tại vì có use case và hành vi được kiểm chứng.

## 17. Các lỗi thiết kế cần tránh

| Lỗi | Hệ quả |
| --- | --- |
| Mỗi bảng/document đều có repository công khai | Dễ bỏ qua ranh giới aggregate |
| OrderLine chỉ giữ productId rồi đọc giá hiện tại | Đơn cũ thay đổi khi sản phẩm đổi giá |
| Cho caller sửa trực tiếp List lines | Bỏ qua invariant của đơn |
| Chỉ dùng exists để bảo vệ duy nhất | Có race condition khi ghi đồng thời |
| Dùng getter total để kỳ vọng query tự tổng hợp | Không có hợp đồng thực thi ở store |
| Trả toàn bộ entity graph cho màn hình danh sách | Tải dữ liệu ngoài nhu cầu |
| Dùng Page khi không cần tổng mà không cân nhắc chi phí | Có thể phát sinh công việc count không cần thiết |
| Dùng Slice nhưng bịa totalElements | Metadata sai hợp đồng |
| Xóa cascade sang Customer/Product | Làm mất dữ liệu độc lập và lịch sử |
| Coi UUID có sẵn là chắc chắn entity cũ | Có thể sai nhánh nhận diện đối tượng mới |
| Annotation transaction bao nhiều store nhưng không kiểm chứng | Kỳ vọng nguyên tử không có bằng chứng |
| Mock repository rồi kết luận mapping/query đúng | Không thực thi hạ tầng cần kiểm tra |

## 18. Bài tập triển khai

1. Chọn một store và lập bảng khả năng cần dùng.
2. Cài đặt Customer, Product, Money, OrderLine và PurchaseOrder theo các invariant.
3. Viết hợp đồng repository tối thiểu cho các use case đã nêu.
4. Mapping identifier, value object, audit field và version theo module.
5. Cài đặt luồng tạo đơn với snapshot giá, kiểm tra sản phẩm thiếu và dòng trùng.
6. Cài đặt xác nhận đơn và kiểm tra trạng thái.
7. Viết truy vấn danh sách có filter, sort ổn định và projection phù hợp.
8. Kiểm chứng bằng fixture có dữ liệu đối chứng và các ca cạnh tranh quan trọng.

Sản phẩm bàn giao của người học cần có sơ đồ aggregate, quy tắc nghiệp vụ, hợp đồng repository, lựa chọn mapping và bằng chứng kiểm thử tương ứng.

Một mô hình hoàn chỉnh phải bảo vệ được ý nghĩa của đơn hàng qua thời gian, đồng thời cho mỗi use case một cách truy cập dữ liệu rõ ràng. Repository là cổng làm việc với aggregate; khả năng thực thi vẫn phải được xác nhận trên store đã chọn.
