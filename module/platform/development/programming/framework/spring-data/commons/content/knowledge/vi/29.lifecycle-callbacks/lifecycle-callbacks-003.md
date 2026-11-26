# Chọn callback trước/sau chuyển đổi hoặc lưu theo store

## 1. Mục tiêu và phạm vi

Trong chương **Vòng đời và callback** của module **Spring Data Commons**, bài này giải quyết việc chọn đúng checkpoint để kiểm tra hoặc thay đổi dữ liệu trong quá trình đọc và ghi.

Sau bài học, bạn cần có khả năng:

- Phân biệt thay đổi entity trước chuyển đổi với thay đổi biểu diễn lưu trữ trước khi ghi.
- Nhận diện `AfterConvert` trong luồng đọc và `AfterSave` trong luồng ghi.
- Chọn interface và chữ ký phương thức đúng với MongoDB, JDBC hoặc R2DBC.
- Giữ đúng hợp đồng trả về entity, thứ tự callback và kiểu đồng bộ/reactive.
- Kiểm tra dữ liệu thực sự được lưu thay vì chỉ quan sát đối tượng trong bộ nhớ.

Entity callbacks là cơ chế dùng chung về mô hình mở rộng, nhưng các interface cụ thể và tham số bổ sung do module store cung cấp. Không có một chữ ký `BeforeSaveCallback` duy nhất dùng thay thế cho mọi kho dữ liệu.

## 2. Chọn checkpoint theo hai chiều xử lý

### 2.1. Luồng ghi

Một sơ đồ khái niệm thường hữu ích:

```text
Entity từ ứng dụng
    -> BeforeConvert
    -> chuyển thành biểu diễn ghi của store
    -> BeforeSave
    -> thực hiện thao tác ghi
    -> AfterSave
    -> entity kết quả trả về ứng dụng
```

Biểu diễn ghi có thể là `Document` của MongoDB, `OutboundRow` của R2DBC hoặc kế hoạch thay đổi aggregate của JDBC.

Sơ đồ chỉ mô tả các checkpoint đang được bàn đến. Việc xác định entity mới, sinh định danh, xử lý version và transaction còn có chi tiết riêng theo store.

### 2.2. Luồng đọc

```text
Dữ liệu được đọc từ store
    -> chuyển thành domain object
    -> AfterConvert
    -> entity kết quả trả về ứng dụng
```

**AfterConvert thuộc luồng đọc trong những store được minh họa ở bài này.** Nó không phải bước mặc định nằm giữa `BeforeConvert` và `BeforeSave` của luồng ghi.

Ví dụ, MongoDB định nghĩa `AfterConvertCallback` là callback sau khi domain object được materialize từ `Document` khi đọc kết quả. Xem [MongoDB AfterConvertCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/AfterConvertCallback.html).

### 2.3. Bảng chọn nhanh

| Nhu cầu | Điểm nên xem xét | Lý do |
| --- | --- | --- |
| Chuẩn hóa thuộc tính domain để giá trị mới được mapper ghi ra | BeforeConvert | Mapper chưa tạo biểu diễn lưu trữ |
| Kiểm tra entity trước khi tạo dữ liệu ghi | BeforeConvert hoặc checkpoint kiểm tra được store hỗ trợ | Có thể từ chối sớm trước thao tác ghi |
| Điều chỉnh trực tiếp Document hoặc OutboundRow sắp gửi đi | BeforeSave của store tương ứng | Biểu diễn ghi đã được tạo và được callback cung cấp |
| Xử lý entity kết quả sau thao tác ghi | AfterSave | Thao tác ghi của checkpoint đã hoàn tất |
| Bổ sung trạng thái tạm sau khi đọc và dựng entity | AfterConvert | Domain object đã được materialize |
| Thực hiện công việc chỉ khi transaction đã commit | Cơ chế gắn với transaction | AfterSave không tự cung cấp ngữ nghĩa after-commit |

Nếu chỉ cần chuyển đổi một kiểu Java thành kiểu lưu trữ, custom converter có thể là điểm mở rộng phù hợp hơn. Callback biểu diễn một thời điểm trong vòng đời; converter biểu diễn quy tắc chuyển đổi giữa các kiểu.

## 3. Những khác biệt theo store cần biết trước khi viết mã

| Store | BeforeConvert | BeforeSave | AfterConvert |
| --- | --- | --- | --- |
| MongoDB | Nhận entity và tên collection | Nhận entity, Document và tên collection | Nhận entity đã đọc, Document nguồn và tên collection |
| JDBC | Làm việc với aggregate root trước khi tạo aggregate change | Làm việc với aggregate và kế hoạch thay đổi theo API JDBC | Sau khi dựng aggregate từ kết quả truy vấn |
| R2DBC | Nhận entity và SqlIdentifier của bảng, trả Publisher | Nhận thêm OutboundRow, trả Publisher | Sau khi đọc entity, trả Publisher |

Đây là bảng định hướng, không phải khai báo interface để copy nguyên trạng. Khi triển khai, cần kiểm tra đầy đủ package, kiểu trả về và chữ ký trong phiên bản của dự án.

Một lớp có tên ngắn `BeforeConvertCallback` trong JDBC khác lớp cùng tên của R2DBC. Với MongoDB, callback reactive còn sử dụng các interface mang tên như `ReactiveBeforeConvertCallback`.

Một ứng dụng dùng nhiều store phải đăng ký đúng callback cho từng hạ tầng. Việc dùng chung repository abstraction không tự khiến callback MongoDB chạy cho repository JDBC.

## 4. MongoDB: thay đổi entity ở BeforeConvert

### 4.1. Model minh họa

Giả sử ứng dụng quản lý khách hàng:

- `displayName` là dữ liệu cần lưu.
- `displayLabel` chỉ dùng tạm sau khi đọc.
- `id` do hạ tầng lưu trữ quản lý theo cấu hình của ứng dụng.

```java
package com.example.lifecycle.mongo;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("customers")
public class Customer {

    @Id
    private String id;

    private String displayName;

    @Transient
    private String displayLabel;

    public Customer() {
    }

    public Customer(String displayName) {
        this.displayName = displayName;
    }

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getDisplayLabel() {
        return displayLabel;
    }

    public void setDisplayLabel(String displayLabel) {
        this.displayLabel = displayLabel;
    }
}
```

`@Transient` ở đây là annotation của Spring Data, dùng để loại trường khỏi persistence mapping. Nó không đồng nghĩa với một callback và không tự tính giá trị cho trường.

Ví dụ giả định ứng dụng đã cấu hình MongoDB và component scanning cho package tương ứng. Những lớp dưới đây là các lớp riêng trong cùng package.

### 4.2. Chuẩn hóa trước khi mapper tạo Document

```java
package com.example.lifecycle.mongo;

import org.springframework.core.annotation.Order;
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
@Order(200)
public class NormalizeCustomerName
        implements BeforeConvertCallback<Customer> {

    @Override
    public Customer onBeforeConvert(
            Customer entity, String collection) {

        String name = entity.getDisplayName();

        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "displayName must not be blank");
        }

        entity.setDisplayName(name.strip());
        return entity;
    }
}
```

Nếu đầu vào là `"  An  "`, callback trả entity có `displayName="An"`. Sau đó mapper mới tạo `Document`, nên giá trị được ánh xạ ra cũng là `"An"`.

Điểm cần giữ là **thay đổi xảy ra trước chuyển đổi**. Việc trả entity là một phần của hợp đồng callback, không phải chi tiết có thể bỏ qua.

Ví dụ dùng entity mutable để nhìn rõ luồng dữ liệu. Với immutable entity, callback có thể trả một instance mới; chuỗi xử lý phải sử dụng instance được trả về.

Giá trị `@Order(200)` chỉ minh họa cách khai báo thứ tự. Không nên sao chép con số này như một quy tắc chung cho mọi ứng dụng hoặc mọi callback auditing.

## 5. MongoDB: thay đổi Document ở BeforeSave

### 5.1. Vì sao sửa entity tại đây có thể quá muộn?

Ở MongoDB, `BeforeSaveCallback` được gọi sau khi entity đã được chuyển thành `Document`.

Nếu chỉ làm việc sau:

```text
entity.displayName = "Tên mới"
return entity
```

tại checkpoint này, không được suy ra rằng `Document` đang chờ ghi cũng tự cập nhật theo.

API MongoDB nêu rõ: thay đổi persistent field trên domain object ở `BeforeSave` không được dùng để ghi thay cho dữ liệu đã chuyển đổi; muốn sửa dữ liệu ghi tại đây cần sửa `Document`. Xem [MongoDB BeforeSaveCallback](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/BeforeSaveCallback.html).

### 5.2. Ví dụ bổ sung metadata của biểu diễn lưu trữ

```java
package com.example.lifecycle.mongo;

import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class AddWriteFormatVersion
        implements BeforeSaveCallback<Customer> {

    @Override
    public Customer onBeforeSave(
            Customer entity,
            Document document,
            String collection) {

        document.put("writeFormatVersion", 1);
        return entity;
    }
}
```

Callback này điều chỉnh `Document` chuẩn bị được ghi. `writeFormatVersion` là metadata lưu trữ trong ví dụ, không phải thuộc tính của lớp `Customer`.

Phần dữ liệu mong đợi trong document:

```json
{
  "displayName": "An",
  "writeFormatVersion": 1
}
```

Document thực tế còn có định danh và có thể có metadata khác do cấu hình mapper cung cấp.

Khi chọn cách chỉnh dữ liệu thô, cần giữ hợp đồng giữa schema lưu trữ và model. Nếu đó là thuộc tính nghiệp vụ mà ứng dụng thường xuyên đọc hoặc truy vấn, việc biểu diễn nó rõ ràng trong domain mapping có thể phù hợp hơn.

### 5.3. Không dùng AfterSave để sửa lại dữ liệu vừa ghi

`AfterSave` xảy ra sau thao tác ghi của checkpoint. Việc đổi một field của entity hoặc sửa đối tượng document lúc này không tự tạo một thao tác ghi mới.

Nếu mục tiêu là làm thay đổi bản ghi của lần lưu hiện tại, hãy chọn checkpoint trước khi dữ liệu được gửi đi. Gọi `save` lại từ chính callback của `save` còn có thể gây lặp callback và khó kiểm soát vòng đời.

## 6. AfterConvert: bổ sung dữ liệu sau khi đọc

Với model ở mục 4, có thể bổ sung `displayLabel` sau khi MongoDB đã dựng entity:

```java
package com.example.lifecycle.mongo;

import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.AfterConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class PopulateCustomerDisplayLabel
        implements AfterConvertCallback<Customer> {

    @Override
    public Customer onAfterConvert(
            Customer entity,
            Document document,
            String collection) {

        String name = entity.getDisplayName();

        entity.setDisplayLabel(
                name == null ? "(chưa có tên)" : name);

        return entity;
    }
}
```

Checkpoint này phù hợp khi cần trạng thái domain tạm sau khi materialize. Với một giá trị hiển thị đơn giản, getter tính toán hoặc projection cũng có thể đáp ứng nhu cầu mà không cần callback; hãy chọn theo cách dữ liệu được sử dụng.

Điều cần phân biệt:

- Callback đã thay đổi object trả về từ lần đọc.
- Callback không tự cập nhật document trong database.
- `displayLabel` tiếp tục không được mapper lưu vì nó có `@Transient`.

Nếu sửa một persistent field trong `AfterConvert`, thay đổi đó có thể được ghi ở một lần `save` tường minh sau này. Vì vậy, không nên dùng callback đọc để âm thầm sửa dữ liệu lâu dài nếu ứng dụng chưa có chính sách rõ ràng.

### 6.1. Đối chiếu hành vi của ba callback

Repository minh họa:

```java
package com.example.lifecycle.mongo;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerRepository
        extends MongoRepository<Customer, String> {
}
```

Luồng sử dụng:

```java
Customer saved = repository.save(new Customer("  An  "));

Customer loaded = repository.findById(saved.getId())
        .orElseThrow();
```

Các điểm nên quan sát:

| Quan sát | Kết quả mong đợi | Callback hoặc mapping liên quan |
| --- | --- | --- |
| displayName trong document thô | `An` | BeforeConvert chuẩn hóa trước mapping |
| writeFormatVersion trong document thô | `1` | BeforeSave sửa Document |
| displayLabel trong document thô | Không có | @Transient loại khỏi mapping |
| displayLabel của loaded | `An` | AfterConvert của luồng đọc |
| AfterConvert chỉ vì vừa gọi save | Không giả định có lần đọc ngầm | Save và đọc là hai luồng riêng |

Không chỉ kiểm tra giá trị trên `saved` rồi kết luận dữ liệu đã được lưu đúng. Cần quan sát document thô và đọc lại qua đường mapping.

## 7. JDBC: lưu ý kế hoạch ghi và thời điểm xác định entity mới

Trong Spring Data JDBC, luồng lưu aggregate có các quyết định quan trọng:

```text
Xác định aggregate mới hay đã tồn tại
    -> BeforeConvert
    -> tạo aggregate change và quyết định liên quan đến giá trị ghi
    -> BeforeSave
    -> thực thi SQL
    -> AfterSave
```

Tài liệu JDBC mô tả `BeforeConvert` là điểm phù hợp khi muốn gán id bằng chương trình. Việc xác định aggregate mới hay cũ đã xảy ra trước checkpoint đó; quyết định về id được gửi xuống database được hình thành khi chuyển aggregate thành kế hoạch ghi. Không dùng `BeforeSave` để tạo id cho aggregate mới. Xem [JDBC Lifecycle Events và EntityCallbacks](https://docs.spring.io/spring-data/relational/reference/jdbc/events.html).

Hệ quả khi chọn callback:

- Nếu cần gán giá trị domain trước khi kế hoạch ghi được tạo, xem xét `BeforeConvert`.
- Không dùng quy tắc của MongoDB rằng mọi thay đổi entity ở `BeforeSave` đều giống hệt nhau cho JDBC.
- Cần xem hợp đồng của aggregate change và API cụ thể trước khi thay đổi kế hoạch ghi.
- Không gán id rồi tự suy ra thao tác insert/update sẽ được chọn lại theo id mới.

Sinh id bằng ứng dụng còn phải phù hợp với chiến lược nhận diện entity mới và schema của store. Callback là nơi thực hiện một bước đã thiết kế, không tự giải quyết toàn bộ hợp đồng định danh.

Spring Data JDBC phát callbacks cho aggregate root trong các đường xử lý được hỗ trợ. Không mặc định mỗi object con của aggregate nhận một callback độc lập. Nếu cần xử lý dữ liệu bên trong aggregate, có thể thực hiện từ callback của root với phạm vi rõ ràng.

## 8. R2DBC: cùng checkpoint nhưng hợp đồng reactive

### 8.1. Tên interface và kiểu trả về

Trong R2DBC, `BeforeConvertCallback` nằm trong package:

```text
org.springframework.data.r2dbc.mapping.event
```

và phương thức trả `Publisher<T>`. Việc tên interface không có tiền tố `Reactive` không làm nó trở thành callback đồng bộ.

Một model riêng cho ví dụ R2DBC:

```java
package com.example.lifecycle.r2dbc;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record SqlCustomer(
        @Id Long id,
        String displayName) {
}
```

Callback:

```java
package com.example.lifecycle.r2dbc;

import org.reactivestreams.Publisher;
import org.springframework.data.r2dbc.mapping.event.BeforeConvertCallback;
import org.springframework.data.relational.core.sql.SqlIdentifier;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class NormalizeSqlCustomerName
        implements BeforeConvertCallback<SqlCustomer> {

    @Override
    public Publisher<SqlCustomer> onBeforeConvert(
            SqlCustomer entity, SqlIdentifier table) {

        return Mono.fromSupplier(() -> {
            String name = entity.displayName();

            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException(
                        "displayName must not be blank");
            }

            return new SqlCustomer(
                    entity.id(),
                    name.strip());
        });
    }
}
```

Ví dụ dùng Java 17 trở lên cho record và giả định ứng dụng đã cấu hình store, schema cùng component scanning tương ứng.

Callback trả publisher phát ra entity mới. Không gọi `subscribe()` bên trong callback để chạy một nhánh riêng, và không gọi `block()` để ép pipeline thành đồng bộ.

Nếu không thay đổi entity, cần trả publisher phát entity đó, chẳng hạn `Mono.just(entity)`. Không dùng publisher rỗng chỉ để diễn đạt “không sửa gì”.

Chữ ký và hợp đồng của checkpoint được mô tả tại [R2DBC BeforeConvertCallback](https://docs.spring.io/spring-data/r2dbc/docs/current/api/org/springframework/data/r2dbc/mapping/event/BeforeConvertCallback.html).

### 8.2. BeforeSave của R2DBC làm việc với OutboundRow

Trước khi lưu, R2DBC có thể cung cấp `OutboundRow` đã được tạo từ entity. Nếu nhu cầu là điều chỉnh giá trị cột ở biểu diễn chuẩn bị ghi, đây là dữ liệu cần xem xét tại `BeforeSave`.

Để thay đổi domain field trước mapping, ví dụ chuẩn hóa tên ở trên vẫn chọn `BeforeConvert`.

Bảng callback của module phân biệt:

- `BeforeConvert`: trước chuyển domain object thành `OutboundRow`.
- `BeforeSave`: trước lưu, có thể thay đổi `OutboundRow`.
- `AfterSave`: sau lưu, có thể điều chỉnh domain object được trả về.
- `AfterConvert`: sau khi domain object được đọc từ row.

Xem [R2DBC EntityCallbacks](https://docs.spring.io/spring-data/relational/reference/r2dbc/entity-callbacks.html).

### 8.3. Callback phải tham gia cùng pipeline

Với luồng reactive, dữ liệu do callback tạo phải được pipeline tiếp tục sử dụng. Nếu tự tách một subscription để chuẩn hóa hoặc kiểm tra dữ liệu, thao tác ghi có thể chạy trước khi nhánh đó hoàn tất.

Tương tự, callback đồng bộ của MongoDB không thay thế cho callback của `ReactiveMongoTemplate`. API đồng bộ và API reactive sử dụng các tập callback tương ứng.

## 9. Đăng ký, thứ tự và phạm vi callback

### 9.1. Đăng ký tại đúng ApplicationContext

Các callback ở ví dụ được khai báo bằng `@Component`. Cần đảm bảo:

- Package của callback được scan.
- Template/repository đang dùng được nối với hạ tầng callback tương ứng.
- Callback triển khai đúng interface của store.
- Generic type phù hợp với entity thực tế.

Tự tạo một callback bằng `new` trong service không đăng ký nó vào hạ tầng store. Với template được tạo thủ công hoặc nhiều template trong ứng dụng, cần kiểm tra cách mỗi template nhận callbacks.

Tài liệu [Entity Callbacks của Commons](https://docs.spring.io/spring-data/commons/reference/entity-callbacks.html) mô tả việc store nhận callback bean từ `ApplicationContext`, hỗ trợ thứ tự và entity có thể được thay thế bằng instance trả về.

### 9.2. Thứ tự chỉ có nghĩa trong checkpoint tương ứng

Có thể dùng `Ordered` hoặc `@Order` để điều phối nhiều callback cùng giai đoạn. Giá trị thứ tự nhỏ hơn thường được chạy trước theo quy tắc sắp xếp của Spring.

Tuy nhiên:

```text
@Order rất nhỏ trên BeforeSave
    không đưa BeforeSave lên trước BeforeConvert
```

Vòng đời của store quyết định checkpoint. Thứ tự callback chỉ điều phối các callback được áp dụng tại vị trí tương ứng.

Không dựa vào thứ tự scan bean để diễn đạt phụ thuộc nghiệp vụ. Nếu bước chuẩn hóa phải chạy trước bước kiểm tra, hãy khai báo thứ tự rõ ràng hoặc gộp chúng thành một bước dễ kiểm soát.

### 9.3. Callback và lifecycle event là hai cơ chế khác nhau

Entity callback trả lại entity để chuỗi xử lý tiếp tục. Lifecycle event phục vụ cơ chế thông báo qua event infrastructure.

Nếu event multicaster chạy bất đồng bộ, việc listener sửa entity để kịp cho lần ghi có thể không còn thứ tự mong đợi. Các store cũng có thể vẫn phát lifecycle events bên cạnh entity callbacks.

Đừng thực hiện cùng một biến đổi trong cả listener và callback mà không có chủ đích, vì dữ liệu có thể bị xử lý hai lần. Với thay đổi entity ở checkpoint xác định, callback thường diễn đạt hợp đồng rõ hơn.

### 9.4. Auditing có cơ chế riêng của module

Các module có thể tích hợp auditing qua callback, chẳng hạn cập nhật trường người tạo, người sửa hoặc thời gian sửa.

Trước khi viết callback thủ công cho cùng trường dữ liệu, kiểm tra cấu hình auditing sẵn có. Hai callback cùng cập nhật một trường có thể tạo phụ thuộc thứ tự khó thấy.

Không giả định một con số order của auditing là cố định cho mọi store hoặc mọi phiên bản.

## 10. AfterSave không đồng nghĩa after-commit

Xét một thao tác lưu nằm trong transaction của tầng service:

```text
Bắt đầu transaction
    -> repository save
    -> driver thực hiện ghi
    -> AfterSave
    -> service tiếp tục xử lý
    -> commit hoặc rollback
```

`AfterSave` phản ánh checkpoint sau ghi của store. Nếu transaction bên ngoài còn đang mở, vẫn có thể xảy ra lỗi khiến transaction rollback sau checkpoint này.

Vì vậy:

- Không dùng tên `AfterSave` làm bằng chứng giao dịch đã commit.
- Không mặc định sửa entity ở đây sẽ tạo thêm dữ liệu ghi.
- Không giả định exception từ callback sau ghi luôn có thể hoàn tác mọi thay đổi khi không có transaction phù hợp.

Nếu công việc phải phụ thuộc commit thành công, cần cơ chế gắn với transaction, chẳng hạn `@TransactionalEventListener` với phase phù hợp. Cơ chế này cũng có điều kiện về việc transaction có đang tồn tại hay không; xem [Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html).

Nếu yêu cầu là truyền thông báo bền vững sang hệ thống khác, chỉ đổi từ callback sang listener after-commit chưa tự tạo cơ chế bảo đảm gửi lại. Cần thiết kế độ tin cậy riêng, chẳng hạn outbox phù hợp với transaction của ứng dụng.

## 11. Đường thực thi quyết định callback có chạy hay không

Callback gắn với những thao tác mà module thực sự tích hợp vào vòng đời entity.

Các thao tác update bằng query, bulk, native SQL/driver hoặc custom repository có thể đi theo đường không materialize entity và không đi qua chuỗi callback mong đợi.

Riêng tài liệu JDBC nêu rằng các callback liên quan save/delete không được gọi cho derived query method hoặc annotated query thực hiện những thao tác tương ứng, vì framework không có đầy đủ aggregate bị ảnh hưởng để cung cấp callback.

Cần phân biệt điều này với việc đọc entity qua một query được hỗ trợ: không suy ra rằng mọi phương thức query đều vô hiệu hóa tất cả callback đọc.

Hệ quả thiết kế:

- Callback không thay thế ràng buộc database cho mọi đường ghi.
- Một bất biến quan trọng cần được bảo vệ ở các tầng phù hợp với những đường dữ liệu thực tế.
- Khi thêm custom repository, phải kiểm tra nó dùng template/entity operation hay truy cập driver trực tiếp.
- Không giả định callback của root sẽ tự chạy cho từng object lồng trong mọi store.

Một callback chuẩn hóa nên có hành vi lặp lại ổn định. Ví dụ, `strip()` hai lần vẫn cho cùng kết quả, còn nối thêm một hậu tố ở mỗi lần lưu có thể làm dữ liệu thay đổi không chủ đích khi retry.

## 12. Xác minh đã chọn đúng callback

Không chỉ kiểm tra callback được gọi. Cần kiểm tra tác động tại ranh giới persistence.

| Câu hỏi | Cách kiểm tra |
| --- | --- |
| Chuẩn hóa ở BeforeConvert có được lưu không? | Lưu entity, quan sát dữ liệu thô rồi đọc lại |
| Sửa Document hoặc OutboundRow có đúng cột/trường không? | Kiểm tra biểu diễn ghi và dữ liệu trong store |
| AfterConvert có chỉ thay đổi đối tượng đọc ra không? | So sánh object trả về với dữ liệu thô |
| Entity immutable mới có được dùng tiếp không? | Kiểm tra instance kết quả và dữ liệu ghi |
| Callback có đúng thứ tự không? | Ghi nhận chuỗi checkpoint và thứ tự trong phép kiểm tra |
| Transaction rollback sau AfterSave thì dữ liệu thế nào? | Kiểm tra trong transaction được cấu hình cho store |
| Đường update/bulk có callback không? | Kiểm tra riêng đúng API mà ứng dụng sử dụng |
| API reactive có dùng đúng callback không? | Subscribe pipeline trong phép kiểm tra và quan sát entity phát ra |

Với ví dụ MongoDB, một kịch bản tối thiểu là:

1. Lưu `Customer` có tên `"  An  "`.
2. Đọc collection bằng driver thô, xác nhận `displayName="An"`.
3. Xác nhận `writeFormatVersion=1`.
4. Xác nhận không có trường `displayLabel` trong document.
5. Đọc lại bằng repository và xác nhận `displayLabel="An"`.
6. Lưu một tên rỗng, quan sát việc kiểm tra ở `BeforeConvert` từ chối thao tác.
7. Kiểm tra riêng một đường update khác nếu ứng dụng có sử dụng đường đó.

Không thêm truy vấn phụ vào callback chỉ để chứng minh callback đang chạy. Việc quan sát nên được thực hiện trong phép kiểm tra hoặc công cụ theo dõi phù hợp.

## 13. Bài thực hành

Chọn **một** store và thực hiện:

1. Liệt kê các callback đọc/ghi mà module và phiên bản đang dùng hỗ trợ.
2. Chọn một thuộc tính domain cần chuẩn hóa trước mapping.
3. Chọn một nhu cầu ở biểu diễn lưu trữ, nếu thực sự cần, và xác định checkpoint có cung cấp biểu diễn đó.
4. Chọn một giá trị tạm sau khi đọc; quyết định dùng callback, getter hay projection.
5. Đăng ký callback có generic type rõ ràng và kiểm tra đường repository/template thực tế.
6. Với immutable entity hoặc reactive API, xác nhận entity trả về được dùng tiếp trong chuỗi xử lý.
7. Giải thích điều gì đã hoàn tất ở AfterSave và điều gì còn phụ thuộc transaction.

Bài thực hành đạt yêu cầu khi bạn chỉ ra được **checkpoint**, **dữ liệu có thể thay đổi tại checkpoint đó**, **ảnh hưởng đến bản ghi thực tế** và **giới hạn của store**, thay vì chỉ dựa vào tên callback.
