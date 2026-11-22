# Tự cấp UUID hoặc mã nghiệp vụ và nguy cơ `save` chọn nhầm update

Trong **Spring Data JDBC**, một aggregate root có thể dùng khóa do database sinh, UUID do ứng dụng tự tạo hoặc một mã nghiệp vụ như `SO-2026-000123`. Tự cấp khóa giúp ứng dụng biết định danh của đối tượng ngay khi tạo, thuận tiện cho việc tham chiếu và tích hợp. Tuy nhiên, có một điểm dễ gây lỗi: **Spring Data JDBC phải xác định đối tượng là mới hay đã tồn tại trước khi quyết định `save()` thực hiện INSERT hay UPDATE**.

Nếu ứng dụng tạo UUID trước khi lưu, thuộc tính `@Id` đã khác `null`. Với chiến lược nhận diện mặc định dựa trên ID, Spring Data JDBC có thể coi aggregate là đã tồn tại và chọn nhánh UPDATE. Khi database chưa có hàng mang UUID đó, lệnh lưu không tự trở thành INSERT. Kết quả có thể là không cập nhật hàng nào hoặc phát sinh lỗi tùy cơ chế versioning và phiên bản framework.

Bài học này giải thích cách Spring Data JDBC nhận diện entity mới, cách dùng `@Version` hoặc `Persistable` khi ID được gán trước, cách tách UUID kỹ thuật khỏi mã nghiệp vụ, và cách tổ chức luồng tạo mới/cập nhật an toàn.

## 1. Ba loại định danh cần phân biệt

Trước khi viết entity, cần phân biệt ba khái niệm thường bị gộp chung:

| Loại | Ví dụ | Mục đích |
|---|---|---|
| **Khóa kỹ thuật (surrogate ID)** | UUID `b9f...`, số `101` | Định danh ổn định cho hàng/aggregate trong hệ thống |
| **Mã nghiệp vụ (business key)** | `SO-2026-000123`, `INV-HCM-0088`, `SKU-CHAIR-01` | Mã có ý nghĩa với người dùng, quy trình hoặc hệ thống bên ngoài |
| **Trạng thái mới/cũ của entity** | New / Existing | Quyết định `save()` cần INSERT hay UPDATE |

Khóa kỹ thuật trả lời câu hỏi: *đây là aggregate nào?* Mã nghiệp vụ trả lời: *người dùng hoặc quy trình gọi aggregate này bằng mã nào?* Trạng thái mới/cũ trả lời: *aggregate này đã tồn tại trong database chưa?*

Ba điều đó có liên quan nhưng không đồng nhất. Một UUID được tạo trong bộ nhớ có thể đã có giá trị, trong khi bản ghi tương ứng **chưa hề tồn tại trong database**.

### 1.1. UUID do ứng dụng tạo

Ứng dụng có thể tạo UUID trước khi insert:

~~~java
UUID id = UUID.randomUUID();
~~~

Ưu điểm:

- Có định danh ngay khi tạo object, trước khi gọi database.
- Có thể tạo aggregate ở nhiều tiến trình mà không cần xin số thứ tự từ một database trung tâm.
- Thuận tiện khi tạo các object liên quan hoặc message cần mang ID trước lúc ghi.
- Khó đoán hơn số tăng tuần tự trong một số trường hợp, dù UUID không phải cơ chế phân quyền hay bí mật.

Điểm cần lưu ý:

- UUID khác `null` ngay từ lúc khởi tạo, nên có thể ảnh hưởng đến cơ chế nhận diện entity mới.
- Cần bảo đảm kiểu UUID được database và JDBC driver hỗ trợ đúng. PostgreSQL và H2 có kiểu UUID; với hệ quản trị khác có thể cần `CHAR(36)`, `BINARY(16)` hoặc converter.
- Vẫn cần khóa chính/unique constraint trong database. UUID có xác suất trùng rất thấp nhưng database vẫn là nơi thực thi tính duy nhất.

### 1.2. Mã nghiệp vụ do ứng dụng cấp

Ví dụ:

~~~text
SO-2026-000123
INV-2026-00451
CUSTOMER-HN-000078
~~~

Mã nghiệp vụ thường có định dạng, quy tắc hoặc ý nghĩa riêng. Nó có thể được in trên hóa đơn, gửi cho khách hàng hoặc trao đổi với hệ thống khác. Vì vậy, mã thường cần ổn định trong suốt vòng đời nghiệp vụ.

Không nên mặc định dùng mã nghiệp vụ làm khóa chính. Nếu mã có thể đổi khi chuyển chi nhánh, đổi quy tắc đánh số hoặc hợp nhất dữ liệu, việc dùng nó làm `@Id` sẽ khiến thay đổi định danh lan sang các bảng tham chiếu.

Một thiết kế thường linh hoạt hơn:

~~~text
purchase_orders
├── id            UUID PRIMARY KEY       (khóa kỹ thuật)
├── order_number  VARCHAR UNIQUE         (mã nghiệp vụ)
├── version       BIGINT                 (optimistic locking)
└── status        VARCHAR
~~~

Trong đó, `id` dùng cho quan hệ và repository; `order_number` dùng để tra cứu và hiển thị. Database áp đặt unique constraint lên mã nghiệp vụ để ngăn hai đơn có cùng số.

## 2. `save()` quyết định INSERT hay UPDATE như thế nào?

`CrudRepository.save(entity)` là một API chung cho thao tác lưu. Nó **không có nghĩa là luôn chạy INSERT**, cũng không có nghĩa là luôn thực hiện câu lệnh SQL `UPSERT`.

Về khái niệm, Spring Data JDBC thực hiện:

~~~text
repository.save(aggregate)
          |
          v
  Xác định aggregate mới?
       /          \
     Có            Không
     |               |
   INSERT          UPDATE
~~~

Việc xác định mới/cũ được thực hiện trước khi ghi. Spring Data JDBC sử dụng chiến lược nhận diện entity mới (`IsNewStrategy`) dựa trên metadata của entity:

1. Nếu entity có thuộc tính `@Version`, giá trị version được ưu tiên để xác định trạng thái mới. Với kiểu wrapper như `Long`, `null` biểu thị entity mới; với kiểu primitive như `long`, giá trị `0` biểu thị entity mới.
2. Nếu không có version property, Spring Data dựa vào thuộc tính `@Id`. ID kiểu tham chiếu có giá trị `null` thường biểu thị mới; ID kiểu primitive có giá trị mặc định `0` thường biểu thị mới.
3. Nếu entity triển khai `Persistable`, phương thức `isNew()` do entity cung cấp được dùng để xác định trạng thái.

Vì vậy, **giá trị ID đã được gán không đồng nghĩa với việc hàng đã tồn tại**. Đây là nguyên nhân cốt lõi của lỗi khi tự cấp UUID hoặc business code.

## 3. Ví dụ lỗi: UUID đã có giá trị khiến `save()` đi theo nhánh UPDATE

Giả sử entity đơn giản:

~~~java
import java.util.UUID;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(
        @Id UUID id,
        String orderNumber,
        String status
) {
    public static PurchaseOrder create(String orderNumber) {
        return new PurchaseOrder(
            UUID.randomUUID(),
            orderNumber,
            "DRAFT"
        );
    }
}
~~~

Và schema:

~~~sql
CREATE TABLE purchase_orders (
    id UUID PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL
);
~~~

Khi gọi:

~~~java
PurchaseOrder order = PurchaseOrder.create("SO-2026-000123");
System.out.println(order.id()); // Đã có UUID

PurchaseOrder saved = repository.save(order);
~~~

`order.id()` đã khác `null`. Vì entity không có `@Version` và không tự triển khai `Persistable`, chiến lược mặc định dựa trên ID có thể xem object là **đã tồn tại**. `save()` chọn UPDATE thay vì INSERT.

Nếu database chưa có hàng với ID đó, UPDATE không thể tạo hàng mới. Tùy cơ chế thực thi và cấu hình versioning, thao tác có thể không tác động hàng nào hoặc dẫn đến ngoại lệ. Không nên dựa vào một hành vi lỗi cụ thể để điều khiển luồng tạo mới.

Đặc biệt, thêm đoạn kiểm tra kiểu:

~~~java
if (repository.existsById(order.id())) {
    repository.save(order);
} else {
    repository.save(order);
}
~~~

không giải quyết được vấn đề. Cả hai nhánh vẫn gọi cùng `save()` với cùng một entity có ID khác `null`; ngoài ra, `existsById()` rồi insert còn tạo race condition nếu hai request cùng kiểm tra trước khi một request ghi dữ liệu.

## 4. Cách khuyến nghị: dùng `@Version` để phân biệt entity mới và kiểm soát cập nhật đồng thời

Khi aggregate dùng UUID hoặc mã ID tự cấp, một cách phù hợp là thêm thuộc tính version:

~~~java
import java.util.UUID;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(
        @Id UUID id,
        @Version Long version,
        String orderNumber,
        String status
) {
    public static PurchaseOrder create(String orderNumber) {
        return new PurchaseOrder(
            UUID.randomUUID(),
            null,
            orderNumber,
            "DRAFT"
        );
    }

    public PurchaseOrder changeStatus(String newStatus) {
        return new PurchaseOrder(id, version, orderNumber, newStatus);
    }
}
~~~

Schema tương ứng:

~~~sql
CREATE TABLE purchase_orders (
    id UUID PRIMARY KEY,
    version BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL
);
~~~

Hai thuộc tính có vai trò khác nhau:

- `@Id UUID id`: UUID được ứng dụng tạo trước khi lưu.
- `@Version Long version`: `null` trước lần insert đầu tiên, giúp Spring Data JDBC nhận diện aggregate mới.

Khi insert thành công, Spring Data JDBC khởi tạo version theo cơ chế versioning (thường là `0` cho bản ghi mới). Khi update, version được kiểm tra và tăng lên. Vì `version` là kiểu `Long`, giá trị `null` trước khi lưu có thể phân biệt rõ với một aggregate đã tồn tại.

### 4.1. Repository

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, UUID> {

    Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
}
~~~

Kiểu ID generic của repository phải trùng với kiểu của `@Id`: ở đây là `UUID`, không phải `Long`.

### 4.2. Tạo mới với UUID đã cấp

~~~java
PurchaseOrder draft = PurchaseOrder.create("SO-2026-000123");

// id đã có UUID, nhưng version == null nên entity được nhận diện là mới.
PurchaseOrder saved = repository.save(draft);

System.out.println(saved.id());
System.out.println(saved.version());
~~~

Lần `save()` đầu thực hiện INSERT. Hãy sử dụng **đối tượng trả về** vì version do framework quản lý được cập nhật trong instance được trả về. Với record bất biến, biến `draft` ban đầu vẫn có `version == null`.

### 4.3. Cập nhật aggregate đã tồn tại

~~~java
PurchaseOrder current = repository.findById(saved.id())
    .orElseThrow();

PurchaseOrder changed = current.changeStatus("CONFIRMED");
PurchaseOrder updated = repository.save(changed);

System.out.println(updated.version());
~~~

Lần lưu này thực hiện UPDATE. `current.version()` là version đang có trong database; Spring Data JDBC dùng nó để phát hiện cập nhật xung đột và tăng version khi lưu thành công.

### 4.4. Vì sao không nên bỏ qua đối tượng trả về?

Giả sử:

~~~java
PurchaseOrder first = repository.findById(id).orElseThrow();
PurchaseOrder updated = repository.save(first.changeStatus("CONFIRMED"));
~~~

Với record, `first` vẫn giữ version cũ, còn `updated` có version mới. Nếu tiếp tục dùng `first` để lưu một thay đổi khác, version cũ không còn khớp với database. Spring Data JDBC có thể ném `OptimisticLockingFailureException`, giúp phát hiện cập nhật lạc hậu thay vì âm thầm ghi đè.

Hãy tiếp tục từ đối tượng mới nhất:

~~~java
PurchaseOrder next = repository.save(
    updated.changeStatus("SHIPPED")
);
~~~

Không nên tự gán hoặc tự tăng version. Version là cơ chế đồng bộ do Spring Data JDBC quản lý.

## 5. Vì sao `@Version` hữu ích hơn một cờ “isNew” đơn thuần?

`@Version` giải quyết hai vấn đề liên quan:

1. **Nhận diện entity mới:** giá trị version chưa được khởi tạo cho biết aggregate chưa được lưu.
2. **Optimistic locking:** khi nhiều transaction cùng cập nhật một aggregate, version giúp phát hiện một transaction đang ghi trên dữ liệu đã cũ.

Ví dụ hai request cùng tải version `3`:

~~~text
Database ban đầu: version = 3

Request A đọc version 3
Request B đọc version 3

Request A UPDATE ... WHERE id = ? AND version = 3
  -> thành công, database version = 4

Request B UPDATE ... WHERE id = ? AND version = 3
  -> không còn hàng khớp version
  -> OptimisticLockingFailureException
~~~

Ứng dụng có thể yêu cầu người dùng tải lại dữ liệu, trả lỗi xung đột hoặc retry theo quy tắc nghiệp vụ. Không nên retry vô hạn, vì xung đột có thể là dấu hiệu hai thao tác cần được người dùng giải quyết.

**Lưu ý:** thêm `@Version` yêu cầu thêm cột tương ứng trong database và triển khai migration cho bảng hiện có. Với bảng đã có dữ liệu, cần xác định giá trị version ban đầu và thứ tự migration phù hợp trước khi phát hành code mới.

## 6. Lựa chọn khác: triển khai `Persistable` khi không dùng `@Version`

Spring Data cung cấp interface `Persistable<ID>` để entity tự quyết định kết quả `isNew()`. Cách này hữu ích khi ID luôn được gán trước nhưng ứng dụng không muốn dùng version property.

Khái niệm:

~~~java
public interface Persistable<ID> {
    ID getId();
    boolean isNew();
}
~~~

Một entity triển khai `Persistable<UUID>` có thể giữ cờ trạng thái mới trong bộ nhớ:

~~~java
@Table("purchase_orders")
public class PurchaseOrder implements Persistable<UUID> {

    @Id
    private UUID id;

    private String orderNumber;
    private String status;

    @org.springframework.data.annotation.Transient
    private boolean newEntity;

    protected PurchaseOrder() {
        // Dành cho mapping.
    }

    private PurchaseOrder(
            UUID id,
            String orderNumber,
            String status,
            boolean newEntity) {
        this.id = id;
        this.orderNumber = orderNumber;
        this.status = status;
        this.newEntity = newEntity;
    }

    public static PurchaseOrder create(String orderNumber) {
        return new PurchaseOrder(
            UUID.randomUUID(), orderNumber, "DRAFT", true);
    }

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public void markPersisted() {
        this.newEntity = false;
    }
}
~~~

Đoạn trên minh họa cơ chế `Persistable`, **chưa phải một implementation hoàn chỉnh để đưa thẳng vào production**. Cần bảo đảm cờ `newEntity` chuyển thành `false` sau khi insert thành công và entity được tải từ database cũng được đánh dấu là đã tồn tại. Việc này phải được quản lý qua lifecycle callback phù hợp của Spring Data Relational hoặc một factory/mapper có quy ước rõ ràng. Nếu không, một object đã insert nhưng vẫn trả `isNew() == true` có thể khiến lần `save()` sau lại chọn INSERT và gặp trùng khóa.

Khi dùng entity bất biến hoặc record, quản lý cờ trạng thái thường phức tạp hơn. `@Version` thường gọn và có thêm lợi ích optimistic locking, nên là lựa chọn dễ bảo trì cho nhiều aggregate.

### So sánh `@Version` và `Persistable`

| Tiêu chí | `@Version` | `Persistable.isNew()` |
|---|---|---|
| Nhận diện UUID tự cấp | Có, nếu version ban đầu biểu thị mới | Có, theo kết quả `isNew()` |
| Kiểm soát cập nhật đồng thời | Có optimistic locking | Không tự cung cấp version locking |
| Cần quản lý trạng thái sau insert | Framework cập nhật version | Ứng dụng phải quản lý cờ `isNew` |
| Phù hợp với record immutable | Thường thuận tiện | Khó hơn nếu cần thay đổi cờ |
| Cột database bổ sung | Có cột version | Không bắt buộc |
| Khi nên chọn | Cần phát hiện xung đột và muốn chiến lược rõ ràng | Có quy tắc nhận diện riêng, đã kiểm soát lifecycle |

Không nên triển khai cả hai cơ chế một cách tùy tiện. Hãy chọn một chiến lược nhận diện entity mới phù hợp và kiểm thử luồng tạo, đọc, cập nhật của chính aggregate.

## 7. Mã nghiệp vụ tự cấp cũng gặp vấn đề tương tự

Giả sử đơn hàng dùng mã `SO-2026-000123` làm `@Id`:

~~~java
@Table("purchase_orders")
public record PurchaseOrder(
        @Id String orderNumber,
        String status
) {
    public static PurchaseOrder create(String orderNumber) {
        return new PurchaseOrder(orderNumber, "DRAFT");
    }
}
~~~

Vì `orderNumber` đã có giá trị, Spring Data JDBC có thể coi entity là đã tồn tại nếu không có version property hoặc `Persistable`. Mặc dù mã `SO-2026-000123` mới được cấp và database chưa có hàng nào, `save()` vẫn có thể chọn UPDATE.

Vấn đề này không chỉ xảy ra với UUID. Nó áp dụng cho mọi ID được gán trước:

- `String` chứa mã đơn hàng.
- `Long` do ứng dụng tự cấp.
- `UUID` do `UUID.randomUUID()` tạo.
- Mã lấy từ hệ thống bên ngoài.

Nếu vẫn muốn business key là `@Id`, hãy dùng `@Version` hoặc chiến lược `Persistable` phù hợp. Tuy nhiên, cần cân nhắc kỹ việc dùng mã nghiệp vụ làm khóa chính.

### 7.1. Thiết kế thường khuyến nghị: UUID làm ID, business key là cột unique

~~~java
@Table("purchase_orders")
public record PurchaseOrder(
        @Id UUID id,
        @Version Long version,
        String orderNumber,
        String status
) {
    public static PurchaseOrder create(String orderNumber) {
        return new PurchaseOrder(
            UUID.randomUUID(), null, orderNumber, "DRAFT");
    }
}
~~~

Schema:

~~~sql
CREATE TABLE purchase_orders (
    id UUID PRIMARY KEY,
    version BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL
);
~~~

Repository vẫn dùng UUID làm kiểu ID:

~~~java
interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, UUID> {

    Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
}
~~~

Lợi ích:

- UUID là định danh kỹ thuật ổn định, không phải thay đổi khi format mã đơn thay đổi.
- Mã nghiệp vụ có unique constraint và có thể dùng để tra cứu.
- Version tách trạng thái mới/cũ khỏi sự hiện diện của UUID.
- Quan hệ giữa các aggregate dùng UUID; người dùng vẫn có thể tìm đơn bằng mã `SO-...`.

Nếu business code là một định danh tự nhiên thực sự bất biến, duy nhất và có ý nghĩa trong toàn bộ vòng đời, dùng nó làm `@Id` vẫn có thể hợp lý. Nhưng cần quyết định có chủ ý, không chỉ vì cột đó đã có giá trị.

## 8. Sinh mã nghiệp vụ an toàn khi có nhiều request đồng thời

Một lỗi khác là tự tạo số đơn bằng cách đọc số lớn nhất:

~~~sql
SELECT MAX(order_number) FROM purchase_orders;
~~~

Sau đó cộng 1 để tạo mã mới. Cách này không an toàn khi nhiều request chạy đồng thời:

~~~text
Request A đọc số lớn nhất = 100
Request B đọc số lớn nhất = 100
Request A tạo mã 101
Request B cũng tạo mã 101
~~~

Unique constraint sẽ ngăn một trong hai insert, nhưng request bị từ chối vẫn thất bại. Nếu không có xử lý retry đúng, người dùng có thể gặp lỗi ngẫu nhiên khi tải cao.

### Những cách tạo business code phổ biến

**Database sequence:** database cấp số tuần tự bằng sequence; ứng dụng định dạng số thành `SO-2026-000123`. Sequence thường an toàn khi nhiều request đồng thời, nhưng có thể tạo khoảng trống khi transaction rollback. Khoảng trống có chấp nhận được hay không là yêu cầu nghiệp vụ riêng.

**Bảng cấp phát số có khóa/atomic update:** một thao tác transaction cập nhật bộ đếm và trả về số mới. Cần thiết kế khóa và xử lý retry để không phát sinh duplicate.

**Dịch vụ cấp mã chuyên biệt:** phù hợp hệ thống nhiều dịch vụ hoặc cần quy tắc cấp số theo chi nhánh, năm tài chính, loại chứng từ.

**UUID làm mã tham chiếu:** nếu nghiệp vụ không yêu cầu số tuần tự dễ đọc, có thể dùng UUID làm mã công khai hoặc mã tham chiếu; vẫn phải phân biệt yêu cầu bảo mật và tính không đoán được.

Tránh `MAX(...) + 1` trong các luồng có concurrency. Dù mã cuối cùng có unique constraint, unique constraint là hàng rào bảo vệ cuối cùng, không phải thuật toán cấp mã.

### Business code có thể là idempotency key

Một API tạo đơn có thể nhận `requestKey` để chống tạo trùng khi client gửi lại yêu cầu. Khóa idempotency này nên được lưu với unique constraint và gắn với kết quả tạo đơn. Không đồng nhất nó với UUID nội bộ hoặc mã đơn hiển thị nếu vòng đời và phạm vi duy nhất khác nhau.

## 9. Luồng tạo mới và cập nhật nên tách rõ ở tầng service

Đừng để một request tùy ý quyết định rằng entity có ID thì phải update. Hãy thiết kế use case tường minh:

~~~java
@Service
public class OrderService {

    private final PurchaseOrderRepository repository;

    public OrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public PurchaseOrder create(String orderNumber) {
        PurchaseOrder draft = PurchaseOrder.create(orderNumber);
        return repository.save(draft);
    }

    @Transactional
    public PurchaseOrder changeStatus(UUID id, String status) {
        PurchaseOrder current = repository.findById(id)
            .orElseThrow(() ->
                new NoSuchElementException("Không tìm thấy đơn " + id));

        PurchaseOrder changed = current.changeStatus(status);
        return repository.save(changed);
    }
}
~~~

Phương thức `create` luôn dựng aggregate mới theo factory. Phương thức `changeStatus` phải tải aggregate hiện có, áp dụng quy tắc nghiệp vụ rồi lưu. Nếu dùng `@Version`, version được mang theo từ object đã tải.

Ví dụ trên minh họa cấu trúc service; trong ứng dụng thực tế nên dùng enum `OrderStatus` và các method domain như `confirm()`, `cancel()` thay cho truyền chuỗi trạng thái tùy ý.

### Có nên gọi `existsById()` trước khi tạo?

Không nên dùng mô hình “kiểm tra tồn tại rồi quyết định save” như một biện pháp chống trùng:

~~~java
if (!repository.existsById(id)) {
    repository.save(order);
}
~~~

Hai request vẫn có thể cùng thấy ID chưa tồn tại trước khi một request insert. Hãy để primary key/unique constraint bảo vệ tính duy nhất và xử lý lỗi duplicate một cách có chủ ý. Nếu cần thao tác tạo idempotent, xác định khóa idempotency và quy tắc trả lại kết quả của lần tạo trước.

### Không biến `save()` thành upsert nghiệp vụ

`save()` chọn INSERT hoặc UPDATE dựa trên trạng thái entity theo chiến lược nhận diện. Nó không tự xác minh rằng “nếu không có hàng thì insert, nếu có hàng thì update” theo cách upsert nguyên tử mà mọi database hỗ trợ. Nếu thật sự cần upsert theo unique business key, hãy thiết kế SQL riêng phù hợp database, xử lý cạnh tranh và xác định rõ tác dụng phụ lên aggregate.

## 10. Kiểm tra lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| UUID mới nhưng `save()` không tạo hàng | ID đã khác `null`, không có version hoặc `Persistable` | Thêm `@Version Long` ban đầu `null`, hoặc triển khai `Persistable` đúng lifecycle |
| Repository generic dùng `Long` nhưng entity ID là UUID | Sai kiểu ID | Đổi thành `CrudRepository<PurchaseOrder, UUID>` |
| Cập nhật lần hai báo optimistic locking | Dùng object/version cũ hoặc có transaction khác đã cập nhật | Tải lại aggregate, xử lý conflict, dùng instance trả về từ `save()` |
| `version` null nhưng schema cấm null khi insert | Mapping/version strategy hoặc DDL không phù hợp | Kiểm tra `@Version`, kiểu wrapper, cấu hình SQL và DDL của phiên bản đang dùng |
| Tạo hai đơn có cùng order number | Thiếu unique constraint hoặc bộ cấp mã không an toàn | Đặt unique constraint và dùng sequence/allocator an toàn concurrency |
| Rollback nhưng số chứng từ bị nhảy | Sequence không rollback theo transaction | Xác định yêu cầu có cần số liên tục tuyệt đối hay không |
| Cờ `isNew` luôn true | `Persistable` không chuyển trạng thái sau insert | Quản lý lifecycle callback và trạng thái entity đã lưu |
| ID UUID tự cấp bị coi là existing | Không tách ID đã cấp khỏi trạng thái persistence | Dùng `@Version` hoặc `Persistable` |

Khi điều tra, nên xem SQL thực tế và giá trị `id`, `version` ngay trước khi gọi `save()`. Không nên chỉ nhìn log “saved” hoặc sự tồn tại của UUID trong object rồi kết luận database đã có bản ghi.

## 11. Lộ trình lựa chọn

| Tình huống | Hướng thiết kế thường phù hợp |
|---|---|
| Database tự sinh ID, entity mới có ID `null` | Để Spring Data JDBC nhận diện entity mới từ ID |
| Ứng dụng cần UUID ngay từ lúc tạo aggregate | Dùng `@Version Long` ban đầu `null` để nhận diện mới và có optimistic locking |
| ID tự cấp nhưng không muốn version property | Cân nhắc `Persistable`, quản lý `isNew()` sau insert và sau load |
| Có mã đơn nghiệp vụ dễ đọc | Dùng UUID làm `@Id`, business code làm cột unique |
| Business key thực sự bất biến và là natural key | Có thể dùng làm `@Id`, nhưng phải xử lý new detection |
| Nhiều request cấp số tuần tự | Database sequence hoặc allocator atomic; không dùng `MAX + 1` |
| API cần chống tạo trùng khi retry | Thiết kế idempotency key và unique constraint riêng |

## 12. Kết luận

Trong Spring Data JDBC, **ID có giá trị không đồng nghĩa với entity đã tồn tại trong database**. `save()` chọn INSERT hay UPDATE dựa trên chiến lược nhận diện entity mới. Vì vậy, khi tự cấp UUID hoặc mã nghiệp vụ trước khi lưu, nếu chỉ dựa vào ID khác `null`, ứng dụng có thể khiến `save()` chọn nhầm UPDATE.

Với aggregate dùng UUID, cách dễ kiểm soát thường là kết hợp `@Id UUID` và `@Version Long` khởi tạo `null`. Version vừa giúp nhận diện lần insert đầu, vừa phát hiện cập nhật đồng thời. `Persistable.isNew()` là lựa chọn khác khi có lý do cụ thể, nhưng cần quản lý vòng đời cờ trạng thái chính xác.

Hãy tách **khóa kỹ thuật**, **mã nghiệp vụ** và **trạng thái mới/cũ** thành ba khái niệm rõ ràng. Dùng unique constraint cho business code, bộ cấp mã an toàn khi concurrency và luồng service tách biệt tạo mới với cập nhật. Như vậy, việc tự cấp UUID hoặc mã nghiệp vụ không còn khiến repository phải đoán sai ý định lưu dữ liệu.
