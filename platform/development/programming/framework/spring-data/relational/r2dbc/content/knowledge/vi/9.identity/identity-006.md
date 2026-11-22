# Điều khiển trạng thái mới bằng Persistable

Spring Data cần xác định một entity đang đại diện cho bản ghi mới hay bản ghi đã tồn tại để chọn thao tác ghi phù hợp. Khi gọi repository save, entity mới thường đi theo nhánh insert; entity đã tồn tại đi theo nhánh update.

Spring Data Relational có cơ chế phát hiện trạng thái mới mặc định dựa trên thuộc tính version hoặc ID. Khi quy tắc đó không phù hợp với mô hình định danh của ứng dụng, có thể triển khai **Persistable** để tự quyết định kết quả qua phương thức **isNew()**.

Persistable đặc biệt hữu ích khi ứng dụng tự cấp ID trước khi insert, chẳng hạn UUID, hoặc khi trạng thái mới của entity không thể suy ra chỉ từ ID. Vì isNew() quyết định nhánh ghi dữ liệu, cờ trạng thái phải được khởi tạo, cập nhật và loại khỏi persistent mapping một cách nhất quán.

## 1. Vì sao Spring Data cần biết entity có mới hay không?

Repository trong Spring Data cung cấp phương thức save để lưu entity. Ở thời điểm gọi save, framework phải chọn thao tác phù hợp:

- Entity mới: thực hiện insert để tạo bản ghi.
- Entity đã tồn tại: thực hiện update để thay đổi bản ghi hiện có.

Spring Data không thể luôn suy ra trạng thái này bằng cách kiểm tra database trước mỗi lần save. Thay vào đó, nó sử dụng quy tắc new-state detection trên chính entity.

Điều này quan trọng với entity có ID do ứng dụng tạo. Ví dụ, một đơn hàng có thể nhận UUID ngay khi được khởi tạo, trước khi bản ghi được insert. Nếu chỉ nhìn vào ID, framework có thể hiểu nhầm rằng entity đã tồn tại vì ID không null.

Persistable cho phép domain model cung cấp câu trả lời rõ ràng cho câu hỏi: “Entity này hiện đang là mới hay đã được lưu?”

## 2. Cơ chế phát hiện trạng thái mới mặc định

Khi entity không triển khai Persistable, Spring Data Relational thường sử dụng các thuộc tính persistent để xác định trạng thái mới.

### 2.1. Ưu tiên thuộc tính @Version

Nếu entity có thuộc tính version không phải kiểu primitive, Spring Data dùng giá trị version để nhận diện trạng thái:

- Version là null: entity được xem là mới.
- Version có giá trị: entity được xem là đã tồn tại.

Ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public record PurchaseOrder(
    @Id String id,
    String description,
    @Version Long version
) {}
~~~

Ứng dụng có thể cấp ID trước khi lưu nhưng để version null:

~~~java
PurchaseOrder order =
    new PurchaseOrder("PO-2026-001", "Office supplies", null);
~~~

Dù ID đã có giá trị, version null vẫn cho biết entity là mới theo cơ chế version-based detection.

Khi insert thành công, Spring Data quản lý version theo cơ chế optimistic locking và entity được trả về sẽ mang version phù hợp. Các lần save tiếp theo có thể được nhận diện là update.

Dùng kiểu wrapper như Long hoặc Integer cho version giúp biểu diễn trạng thái chưa được gán bằng null. Nếu version là kiểu primitive, nó không thể mang null; khi đó cơ chế mặc định dựa vào version không có cùng ý nghĩa và Spring Data cần dựa vào ID theo quy tắc của nó.

### 2.2. Nếu không có @Version thì kiểm tra ID

Nếu entity không có thuộc tính version phù hợp, Spring Data kiểm tra ID:

- ID là null: entity được xem là mới.
- ID có giá trị: entity được xem là đã tồn tại.

Ví dụ:

~~~java
@Table("customer")
public record Customer(
    @Id Long id,
    String fullName
) {}
~~~

Entity tạo mới thường có ID null:

~~~java
Customer customer = new Customer(null, "Nguyen An");
~~~

Cơ chế này phù hợp khi database tự sinh ID, chẳng hạn identity hoặc sequence được driver/database hỗ trợ qua thao tác insert.

### 2.3. Hạn chế khi ID được cấp trước

Giả sử ứng dụng tạo UUID trước khi ghi:

~~~java
import java.util.UUID;

Customer customer =
    new Customer(UUID.randomUUID(), "Nguyen An");
~~~

Nếu entity không có version property phù hợp, ID khác null khiến cơ chế mặc định xem entity là đã tồn tại. Repository có thể chọn update dù database chưa có bản ghi đó.

Đây là tình huống Persistable giải quyết: trạng thái mới có thể độc lập với việc ID đã được gán hay chưa.

## 3. Persistable là gì?

Persistable là interface thuộc Spring Data Commons, cho phép entity tự cung cấp ID và trạng thái mới.

~~~java
public interface Persistable<ID> {
    ID getId();
    boolean isNew();
}
~~~

Khi entity triển khai Persistable, Spring Data ủy quyền quyết định trạng thái mới cho phương thức isNew() của entity.

Hai phương thức có ý nghĩa:

- getId(): trả về định danh mà Spring Data sử dụng cho entity.
- isNew(): trả về true nếu entity cần được insert; trả về false nếu entity đã tồn tại và cần được update.

Persistable không tạo SQL, không kiểm tra database và không tự sinh ID. Nó chỉ điều khiển quyết định entity đi theo nhánh insert hay update trong quá trình save.

## 4. Triển khai Persistable với ID do ứng dụng cấp

Một cách phổ biến là dùng cờ boolean không được lưu xuống database. Cờ bắt đầu là true khi ứng dụng tạo entity mới; sau khi entity được insert hoặc đọc từ database, cờ chuyển thành false.

Ví dụ entity đơn hàng:

~~~java
import java.util.UUID;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.domain.Persistable;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder implements Persistable<UUID> {

    @Id
    private UUID id;

    private String description;

    @Transient
    private boolean newEntity = true;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(UUID id, String description) {
        this.id = id;
        this.description = description;
    }

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public void markNotNew() {
        this.newEntity = false;
    }
}
~~~

Một số điểm quan trọng:

- ID được gán ngay khi tạo entity.
- newEntity khởi tạo là true nên lần save đầu tiên chọn insert.
- @Transient của Spring Data loại cờ newEntity khỏi mapping database.
- Sau khi insert thành công, cờ phải chuyển thành false.
- Khi entity được tải từ database, cờ cũng phải là false để lần save tiếp theo chọn update.

Không được để cờ này luôn true. Nếu entity đã lưu nhưng isNew() vẫn trả về true, lần save tiếp theo có thể tiếp tục đi theo nhánh insert và gây lỗi khóa chính trùng lặp.

## 5. Cập nhật trạng thái sau khi insert và khi đọc dữ liệu

Triển khai Persistable chỉ đúng khi vòng đời của cờ trạng thái được quản lý đầy đủ.

Có hai thời điểm cần xử lý:

1. Sau khi lưu thành công: entity không còn là mới.
2. Sau khi tải entity từ database: entity đã tồn tại.

Spring Data Relational cung cấp entity callback để can thiệp vào vòng đời lưu và đọc. Có thể dùng callback sau save để đánh dấu entity đã lưu, và callback sau khi chuyển đổi dữ liệu đọc để đánh dấu entity được tải là đã tồn tại.

Với entity mutable ở ví dụ trên, callback có thể gọi phương thức markNotNew(). Ví dụ minh họa phần thân xử lý sau save:

~~~java
entity.markNotNew();
return entity;
~~~

Với callback sau khi chuyển đổi một Row thành entity, cũng thực hiện thao tác tương tự:

~~~java
entity.markNotNew();
return entity;
~~~

Hai đoạn trên mô tả hành động trong callback tương ứng; khi triển khai cần dùng đúng interface callback và chữ ký phương thức của phiên bản Spring Data Relational trong dự án.

Nếu ứng dụng không dùng callback, có thể cập nhật cờ trong service sau khi publisher save phát ra kết quả thành công. Tuy nhiên, cách đó yêu cầu mọi đường ghi đều đi qua service này và mọi đường đọc cũng phải bảo đảm trạng thái entity được đánh dấu đúng. Callback thường giúp tập trung quy tắc hơn.

### 5.1. Vì sao phải xử lý cả sau save và sau load?

Chỉ đánh dấu sau save là chưa đủ.

Ví dụ:

1. Một entity được insert thành công.
2. Ứng dụng khởi động lại.
3. Entity được tải từ database.
4. Nếu cờ transient luôn khởi tạo true và không được đặt lại, isNew() sẽ trả về true.
5. Khi save entity vừa tải, Spring Data có thể chọn insert thay vì update.

Cờ transient không được khôi phục từ database vì nó không phải cột persistent. Vì vậy, callback sau khi đọc dữ liệu phải đặt trạng thái mới thành false.

### 5.2. Callback phải chạy đúng thời điểm

Đánh dấu entity đã tồn tại trước khi insert thành công có thể khiến trạng thái trong bộ nhớ không còn phản ánh kết quả persistence. Nếu insert thất bại nhưng cờ đã chuyển false, lần thử lại có thể chọn update sai.

Hãy cập nhật trạng thái sau khi thao tác lưu thành công. Khi dùng transaction, cần hiểu callback được gọi ở giai đoạn nào trong vòng đời persistence và cách ứng dụng xử lý rollback; không xem việc callback đã chạy là bằng chứng transaction cuối cùng chắc chắn commit.

## 6. Dùng Persistable với Spring Data R2DBC Repository

Repository vẫn sử dụng ReactiveCrudRepository như thông thường:

~~~java
import java.util.UUID;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface PurchaseOrderRepository
        extends ReactiveCrudRepository<PurchaseOrder, UUID> {
}
~~~

Khi gọi save, Spring Data hỏi trạng thái mới của entity:

~~~java
import java.util.UUID;

import reactor.core.publisher.Mono;

public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    public Mono<PurchaseOrder> create(String description) {
        PurchaseOrder order =
            new PurchaseOrder(UUID.randomUUID(), description);

        return repository.save(order);
    }
}
~~~

Vì entity mới có isNew() trả về true, repository chọn insert dù ID đã được cấp trước.

Sau khi insert thành công, callback cần đánh dấu entity không còn mới. Nếu dùng entity mutable và callback trả về entity sau khi cập nhật cờ, caller có thể tiếp tục dùng kết quả save.

~~~java
return repository.save(order)
    .map(saved -> {
        // Tiếp tục xử lý entity đã được lưu.
        return saved;
    });
~~~

Không cần tự gọi subscribe() trong service để ép lưu. Hãy trả về Mono hoặc Flux cho tầng gọi phía trên để giữ luồng reactive và để lỗi được truyền theo publisher.

## 7. Persistable và entity immutable

Persistable không bắt buộc entity phải mutable. Tuy nhiên, cờ trạng thái trong ví dụ trước được thay đổi trực tiếp nên phù hợp với class mutable.

Với entity immutable, trạng thái mới cũng phải được biểu diễn bất biến. Có thể thiết kế entity sao cho callback tạo instance mới với isNew=false sau khi save hoặc sau khi đọc.

Ví dụ mô hình khái niệm:

~~~java
public final class PurchaseOrder implements Persistable<UUID> {

    private final UUID id;
    private final String description;
    private final boolean newEntity;

    public PurchaseOrder(
            UUID id,
            String description,
            boolean newEntity) {
        this.id = id;
        this.description = description;
        this.newEntity = newEntity;
    }

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public PurchaseOrder markNotNew() {
        return new PurchaseOrder(id, description, false);
    }
}
~~~

Callback sau save hoặc sau convert cần trả về instance mới từ markNotNew(). Không thể chỉ gọi một setter trên immutable entity vì không có setter và các field không được thay đổi.

Với immutable entity có version property wrapper, hãy cân nhắc dùng cơ chế mặc định theo version trước khi thêm một cờ Persistable riêng. Nếu version null biểu thị entity mới một cách chính xác, cách mặc định thường đơn giản và ít trạng thái cần đồng bộ hơn.

## 8. So sánh cách phát hiện trạng thái mới

| Cách phát hiện | Quy tắc | Phù hợp khi |
|---|---|---|
| @Version | Version wrapper null nghĩa là mới; có giá trị nghĩa là đã tồn tại | Có optimistic locking hoặc version là chỉ dấu trạng thái phù hợp |
| @Id | ID null nghĩa là mới; có giá trị nghĩa là đã tồn tại | Database sinh ID và entity mới chưa có ID |
| Persistable.isNew() | Entity tự trả lời true/false | ID được cấp trước hoặc cần quy tắc new-state riêng |

Ưu tiên cơ chế mặc định khi nó phản ánh đúng mô hình dữ liệu. Dùng Persistable khi ứng dụng cần điều khiển trạng thái rõ ràng.

## 9. Sai lầm thường gặp khi dùng Persistable

### 9.1. Luôn trả về true

Nếu isNew() luôn true, mọi lần save đều có thể chọn insert. Khi bản ghi đã tồn tại, database có thể báo vi phạm khóa chính hoặc unique constraint.

Cách xử lý: chuyển cờ sang false sau insert thành công và khi tải entity từ database.

### 9.2. Luôn trả về false

Entity mới sẽ đi theo nhánh update. Nếu bản ghi chưa tồn tại, thao tác có thể không tạo ra dữ liệu như mong đợi hoặc phát sinh lỗi optimistic locking tùy cấu hình.

Cách xử lý: khởi tạo trạng thái mới đúng với vòng đời entity.

### 9.3. Đánh dấu đã lưu ngay khi tạo object

ID đã được cấp không đồng nghĩa entity đã được insert. Nếu ứng dụng tạo UUID rồi lập tức đặt isNew=false, Spring Data có thể chọn update cho một bản ghi chưa tồn tại.

Cách xử lý: tách biệt trạng thái “đã có ID” và trạng thái “đã tồn tại trong database”.

### 9.4. Quên đánh dấu entity sau khi đọc

Cờ @Transient không được lưu xuống database. Entity mới được dựng từ Row sẽ khởi tạo cờ theo giá trị mặc định trong class, thường là true nếu dùng ví dụ ở trên.

Cách xử lý: dùng callback sau convert/load để đặt cờ thành false.

### 9.5. Cờ trạng thái bị lưu thành cột

Nếu quên @Transient, Spring Data có thể xem cờ newEntity là property persistent và cố ánh xạ nó thành cột.

Cách xử lý: dùng org.springframework.data.annotation.Transient cho thuộc tính chỉ phục vụ logic persistence trong bộ nhớ.

### 9.6. Cập nhật cờ trước khi save hoàn tất

Nếu cờ chuyển false trước khi thao tác insert thành công, lần thử lại sau lỗi có thể chọn update nhầm.

Cách xử lý: thay đổi cờ ở giai đoạn sau save thành công hoặc dùng callback đúng vòng đời.

### 9.7. Dùng chung entity mutable giữa nhiều request

Một instance có cờ isNew và các property mutable có thể bị nhiều nhánh xử lý cùng thay đổi. Điều này tạo ra race condition: một nhánh có thể đổi cờ trong khi nhánh khác vẫn đang save.

Cách xử lý: không chia sẻ instance mutable đang được lưu giữa các request; mỗi đơn vị nghiệp vụ nên sở hữu entity của nó.

## 10. Persistable không thay thế ID generation

Persistable chỉ điều khiển lựa chọn insert/update. Nó không tạo ID, không cấu hình sequence, không sinh UUID và không bảo đảm database có thể lưu ID đó.

Nếu ứng dụng dùng UUID tự cấp:

- Tạo UUID trước khi insert.
- Bảo đảm kiểu cột database tương thích.
- Triển khai getId() trả về UUID.
- isNew() phải trả true cho instance mới.
- Sau khi lưu và khi đọc lại, trạng thái phải chuyển false.

Nếu database tự sinh ID:

- Có thể để ID null khi tạo entity mới.
- Dùng cơ chế mặc định theo ID nếu phù hợp.
- Hoặc dùng version wrapper null nếu version-based detection đã được thiết kế.
- Chỉ dùng Persistable khi có lý do rõ ràng để thay đổi cách phát hiện trạng thái.

## 11. Lưu ý với optimistic locking

Persistable và @Version giải quyết hai vấn đề liên quan nhưng khác nhau:

- Persistable.isNew() quyết định entity đi theo insert hay update.
- @Version kiểm soát việc update có dựa trên phiên bản dữ liệu mà entity đã đọc hay không.

Không nên dùng một cờ isNew để thay thế version. Một entity có thể đã tồn tại nhưng dữ liệu của nó đã bị một transaction khác cập nhật; @Version giúp phát hiện xung đột đó.

Nếu entity triển khai Persistable và có @Version, hãy bảo đảm hai tín hiệu không mâu thuẫn. Ví dụ, entity có version null nhưng isNew() trả false sẽ được điều khiển theo Persistable. Cơ chế Persistable có ưu tiên cho trạng thái mới, vì vậy lỗi trong isNew() có thể làm sai nhánh save dù version cho thấy entity chưa được lưu.

## 12. Khi nào nên dùng Persistable?

Dùng Persistable khi:

- ID được ứng dụng gán trước khi insert, chẳng hạn UUID, và không có version property phù hợp để xác định trạng thái mới.
- Quy tắc xác định entity mới phụ thuộc thông tin domain khác với ID.
- Cần chủ động điều khiển insert/update trong một mô hình persistence cụ thể.
- Có thể bảo đảm cờ trạng thái được khởi tạo và chuyển đổi đúng qua các vòng đời tạo, lưu và đọc entity.

Không cần triển khai Persistable chỉ vì entity dùng UUID. Nếu entity có @Version wrapper null khi mới và được Spring Data cập nhật sau insert, cơ chế mặc định có thể đã đủ.

## 13. Quy trình sử dụng Persistable trong ứng dụng

Một quy trình điển hình với ID do ứng dụng cấp:

1. Tạo entity mới và cấp ID.
2. Khởi tạo cờ transient để isNew() trả true.
3. Gọi repository.save(entity).
4. Spring Data thấy entity mới và thực hiện insert.
5. Sau khi lưu thành công, callback chuyển trạng thái entity sang đã tồn tại.
6. Khi entity được đọc từ database, callback sau convert cũng đặt trạng thái thành đã tồn tại.
7. Những lần save tiếp theo đi theo nhánh update.

~~~mermaid
flowchart TD
    A["Tạo entity, gán ID"]
    B["isNew() = true"]
    C["repository.save(entity)"]
    D["INSERT"]
    E["Sau save thành công: isNew = false"]
    F["Đọc entity từ database"]
    G["Sau convert/load: isNew = false"]
    H["save lần tiếp theo"]
    I["UPDATE"]

    A --> B
    B --> C
    C --> D
    D --> E
    F --> G
    E --> H
    G --> H
    H --> I
~~~

Nếu insert thất bại, entity không được xem là đã lưu chỉ vì ID đã có giá trị. Hãy giữ trạng thái mới để có thể xử lý lỗi hoặc thử lại theo chính sách ứng dụng.

## 14. Ghi nhớ

Spring Data cần biết entity mới hay đã tồn tại để chọn insert hoặc update. Mặc định, framework có thể dựa vào @Version hoặc @Id. Khi ID được cấp trước hoặc quy tắc mặc định không phản ánh đúng vòng đời dữ liệu, entity có thể triển khai Persistable và cung cấp isNew().

Một triển khai Persistable đáng tin cậy phải quản lý trạng thái trong suốt vòng đời entity: true khi tạo mới, false sau khi lưu thành công và false khi đọc lại từ database. Cờ trạng thái cần được đánh dấu @Transient để không trở thành cột dữ liệu. Persistable chỉ điều khiển new-state detection; nó không sinh ID, không thay thế @Version và không tự xác minh bản ghi tồn tại.

Khi dùng Spring Data R2DBC, hãy giữ publisher reactive xuyên suốt service và xử lý lỗi insert/update rõ ràng. Nếu cơ chế mặc định theo ID hoặc version đã phù hợp, hãy dùng cơ chế đó; chỉ thêm Persistable khi ứng dụng thật sự cần tự điều khiển trạng thái mới.

