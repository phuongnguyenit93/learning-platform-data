# Chọn ID ổn định và xử lý dữ liệu nhập từ hệ thống khác

## 1. Vấn đề định danh trong Spring Data MongoDB

Trong chương **Định danh và trạng thái** của **Spring Data MongoDB**, ID không chỉ là một trường dùng để tìm document. ID còn là hợp đồng giúp ứng dụng nhận biết **cùng một thực thể qua nhiều lần cập nhật, nhập dữ liệu, đồng bộ và khôi phục sau lỗi**.

Ví dụ, một hệ thống bán hàng nhập danh mục sản phẩm từ ERP. ERP gửi sản phẩm có mã `00042` hôm nay, sau đó gửi lại mã `00042` với tên mới vào ngày mai. Nếu ứng dụng tạo một `ObjectId` ngẫu nhiên ở mỗi lần nhập mà không có quy tắc nhận diện nguồn, một sản phẩm có thể xuất hiện thành nhiều document. Ngược lại, nếu lấy tên sản phẩm làm ID, việc đổi tên sẽ bị diễn giải thành một thực thể mới.

Một thiết kế tốt phải trả lời:

1. ID nào là **định danh nội bộ ổn định** trong MongoDB?
2. Khóa nào giúp xác định cùng một bản ghi do **hệ thống bên ngoài** gửi lại?
3. ID bên ngoài có cần được phân biệt theo **nguồn** hoặc **tenant** không?
4. Sẽ làm gì khi dữ liệu được gửi trùng, sai thứ tự, thay đổi hoặc bị xóa?
5. Làm sao kiểm tra sự trùng lặp, xử lý race condition và tái chạy tiến trình nhập mà không làm hỏng dữ liệu?

Các ví dụ dùng Java 17+, Spring Boot 3.x và Spring Data MongoDB 4.x, với `MongoTemplate`/`MongoRepository`. Hành vi chi tiết nên được kiểm chứng theo phiên bản dự án và MongoDB đang vận hành.

## 2. Phân biệt các loại định danh

| Khái niệm | Ví dụ | Vai trò | Có nên đổi? |
|---|---|---|---|
| MongoDB `_id` | BSON ObjectId hoặc chuỗi `ext.ERP.00042` | Khóa duy nhất của **một document trong collection** | Không đổi trong vòng đời document |
| ID nội bộ ứng dụng | `prd_8c62...` | Định danh ổn định mà hệ thống của mình sử dụng | Tránh đổi; có quy trình migration nếu bắt buộc |
| ID từ hệ thống ngoài | ERP: `00042` | Tìm lại cùng bản ghi nguồn trong các lần import | Xem là dữ liệu thuộc hợp đồng của hệ thống nguồn |
| Khóa ghép nguồn + ID ngoài | (`ERP`, `00042`) | Phân biệt `00042` của ERP với `00042` của CRM | Ổn định theo namespace nguồn |
| Business key | SKU `BOTTLE-500-BLUE` | Tra cứu hoặc áp dụng quy tắc nghiệp vụ | Có thể thay đổi do quy định kinh doanh |
| Event ID / revision | `evt-312`, revision `17` | Nhận diện lần phát sự kiện và thứ tự thay đổi | Không thay thế định danh thực thể |

Một số nguyên tắc cần ghi nhớ:

- **ID thực thể phải ổn định.** Tên, giá, trạng thái, địa chỉ và nhiều business key đều có thể đổi; không phù hợp làm `_id` nếu không có cam kết bất biến.
- **ID bên ngoài chỉ duy nhất trong phạm vi do nguồn cam kết.** Hai hệ thống có thể dùng cùng `externalId`; ngay trong một hệ thống nhiều tenant có thể cần khóa (`tenantId`, `sourceSystem`, `externalId`).
- **Không giả định ID ngoài luôn là số.** Mã `00042` và `42` có thể là hai bản ghi khác nhau; chuyển `String` sang `long` sẽ làm mất số 0 đầu.
- **Đừng dùng thông tin cá nhân làm `_id`** nếu không có yêu cầu rõ ràng. Email, số điện thoại và tên hiển thị có thể thay đổi, mang dữ liệu nhạy cảm hoặc dễ bị đoán.
- **ID và revision giải quyết hai vấn đề khác nhau:** ID trả lời *đây là ai?*, revision trả lời *trạng thái nào mới hơn?*

### ObjectId có phải lựa chọn mặc định duy nhất?

MongoDB hỗ trợ nhiều kiểu BSON cho `_id`, miễn giá trị đáp ứng các ràng buộc của trường định danh. **ObjectId** là lựa chọn thuận tiện vì MongoDB driver có thể tạo nhanh ID mới; một ObjectId gồm 12 byte và chứa thành phần timestamp. Tuy nhiên timestamp này không phải thời điểm nghiệp vụ đáng tin cậy và ObjectId không phải cơ chế sắp thứ tự toàn cục tuyệt đối cho mọi sự kiện.

Các ứng dụng cũng có thể dùng UUID hoặc chuỗi ID. Yếu tố quan trọng không phải “ObjectId hay UUID luôn tốt hơn”, mà là ID có **duy nhất, ổn định, dễ tham chiếu và tương thích với hợp đồng tích hợp** hay không.

## 3. Quyết định sử dụng ID nội bộ hay ID được suy ra từ nguồn

Có ba hướng thường gặp:

| Phương án | Cách lưu | Ưu điểm | Rủi ro/cân nhắc |
|---|---|---|---|
| ID nội bộ do MongoDB tạo | `_id: ObjectId(...)`, lưu thêm `sourceSystem` và `externalId` | Không phụ thuộc định dạng khóa nguồn; phù hợp khi một entity gộp dữ liệu từ nhiều nguồn | Phải có unique index theo khóa ngoài và logic tra cứu/upsert để không tạo trùng |
| ID nội bộ của ứng dụng | `_id: "prd_..."`, lưu mapping nguồn riêng | Thuận tiện khi API/public model cần ID riêng, sống lâu | ID phải được cấp đúng một lần; cần quản lý bảng/collection mapping |
| ID suy ra xác định từ nguồn | `_id: encode(sourceSystem, externalId)` | Cùng bản ghi nhập lại sẽ có cùng `_id`, thuận tiện cho tính idempotent | Phải định nghĩa encode không va chạm, namespace rõ ràng và cách xử lý nguồn đổi/tái sử dụng ID |

**Hãy ưu tiên ID nội bộ độc lập với nguồn** khi một thực thể có thể hợp nhất từ nhiều nhà cung cấp, khóa nguồn có thể được cấp lại hoặc hệ thống dự kiến thay ERP/CRM. Khi dữ liệu là một *projection* chỉ phản ánh duy nhất một bản ghi nguồn, ID suy ra từ namespace nguồn là phương án đơn giản và hợp lý.

Không dùng biểu thức ghép chuỗi kiểu `source + ":" + externalId` mà không kiểm tra va chạm. Ví dụ, hai cặp (`A:B`, `C`) và (`A`, `B:C`) có thể cho cùng chuỗi `A:B:C`. Hãy chọn một định dạng có độ dài/escaping rõ ràng hoặc mã hóa từng thành phần riêng biệt.

## 4. Ánh xạ ID bằng Spring Data MongoDB

### 4.1. @Id và đặc điểm chuyển đổi ObjectId

Một entity phổ biến:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public class Product {
    @Id
    private String id;
    private String name;

    public Product() {}
    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}
~~~

`@Id` ánh xạ property `id` thành trường BSON `_id`. Trong Spring Data MongoDB, ID kiểu `String` thường được chuyển sang BSON `ObjectId` **nếu giá trị có thể chuyển đổi hợp lệ**. Giá trị String không thể chuyển thành ObjectId có thể vẫn được lưu dưới dạng BSON String. Nếu không kiểm soát quy tắc này, hai ID nhìn giống chuỗi Java có thể có kiểu BSON khác nhau.

Ví dụ, chuỗi 24 ký tự hex có thể được chuyển thành ObjectId khi dùng `@Id String`, nhưng chuỗi `"p-42"` không phải ObjectId hợp lệ. Truy vấn bằng raw Java Driver phải sử dụng đúng kiểu BSON thực tế.

### 4.2. @MongoId khi cần giữ _id dưới dạng BSON String

Khi hệ thống đã chọn ID nội bộ là chuỗi, có thể chỉ định kiểu lưu rõ ràng:

~~~java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "external_products")
public record ExternalProduct(
        @MongoId(FieldType.STRING) String id,
        String sourceSystem,
        String externalId,
        long sourceRevision,
        String title,
        boolean deleted) {
}
~~~

`@MongoId(FieldType.STRING)` yêu cầu xử lý khóa ở dạng BSON String, kể cả khi nội dung trông giống một ObjectId. Khi sử dụng `MongoTemplate` với `ExternalProduct.class`, mapping biết `id` tương ứng với `_id`.

Nếu muốn dùng `ObjectId` thực sự ở Java, có thể khai báo ID kiểu `org.bson.types.ObjectId`. Việc lựa chọn loại ID nên thống nhất trước khi dữ liệu được tạo hàng loạt; **đổi kiểu `_id` là migration**, không chỉ là đổi annotation.

### 4.3. _id không nên được cập nhật

MongoDB coi `_id` là định danh bất biến của document. Khi cần đổi khóa, hãy lập kế hoạch tạo document với ID mới, cập nhật các tham chiếu và xử lý ID cũ một cách có kiểm soát. Không kỳ vọng `new Update().set("_id", ...)` hoạt động như đổi tên bình thường.

Đối với dữ liệu nguồn đổi mã, thường tốt hơn là **giữ ID nội bộ cũ và cập nhật mapping/alias của khóa ngoài**. Cách này giữ nguyên tham chiếu từ đơn hàng, giao dịch và các collection liên quan.

## 5. Xác định hợp đồng dữ liệu nhập

Trước khi viết importer, cần thống nhất các trường từ nguồn:

~~~json
{
  "sourceSystem": "ERP",
  "externalId": "00042",
  "revision": 17,
  "title": "Bình nước 500 ml",
  "deleted": false
}
~~~

Đây là ví dụ minh họa; nguồn thực tế có thể không có `revision` hoặc dùng tên khác.

Hợp đồng nhập nên nêu rõ:

1. **Namespace:** `ERP` có nghĩa là hệ thống nào, có cần `tenantId`/mã chi nhánh không?
2. **Identity:** `externalId` có phân biệt hoa thường, khoảng trắng, số 0 đầu và được tái sử dụng sau khi xóa không?
3. **Phiên bản:** `revision` có tăng đơn điệu cho từng `externalId` và có bao gồm thao tác xóa không?
4. **Ý nghĩa event:** mỗi bản ghi chứa trạng thái đầy đủ (*snapshot*) hay chỉ chứa thay đổi từng trường (*delta*)?
5. **Null/thiếu:** trường `null` có nghĩa là xóa giá trị, không được cung cấp hay không xác định?
6. **Xóa:** bản ghi bị xóa có event/tombstone hay cần đối soát định kỳ?
7. **Khả năng chạy lại:** nếu job chết sau khi ghi dữ liệu nhưng trước khi checkpoint, có thể nhập lại cùng event an toàn không?

Không tự động `trim()`, lowercase hoặc chuyển kiểu số cho ID ngoài nếu hợp đồng không định nghĩa phép chuẩn hóa đó. Ví dụ `"ab-1"` có thể khác `"AB-1"`, và `"00042"` có thể khác `"42"`. Nếu nguồn cho phép alias, phải quản lý quy tắc đó riêng và kiểm thử.

## 6. Một pipeline nhập an toàn có hình dạng gì?

~~~mermaid
flowchart TD
    A["Nhận dữ liệu từ API/file/queue"] --> B["Xác thực schema + namespace + externalId"]
    B --> C["Xác định khóa thực thể ổn định"]
    C --> D{"Có revision tăng đơn điệu từ nguồn?"}
    D -->|"Có"| E["Ghi có điều kiện nếu revision mới hơn"]
    D -->|"Không"| F["Dùng snapshot có kiểm soát, cursor theo nguồn và đối soát"]
    E --> G["Unique index bảo vệ trùng ID"]
    F --> G
    G --> H["Ghi thành công hoặc bỏ qua event trùng/cũ"]
    H --> I["Checkpoint sau khi ghi bền vững"]
    I --> J["Metrics, retry và đối soát định kỳ"]
~~~

Những bảo đảm cần tách rõ:

- **Duy nhất thực thể:** một khóa ngoài ánh xạ tối đa tới một document nội bộ. Giải bằng `_id`/unique index và quy tắc identity.
- **Idempotent khi retry:** cùng event được xử lý nhiều lần không thay đổi kết quả cuối theo cách sai lệch. Giải bằng khóa ổn định và kiểm tra revision/event ID.
- **Không ghi đè trạng thái mới:** event cũ đến sau không hạ dữ liệu về trạng thái cũ. Giải bằng revision có thứ tự đáng tin cậy và update có điều kiện.
- **Không mất sự kiện:** sau lỗi mạng/worker, vẫn có thể phát lại từ checkpoint, outbox hoặc dữ liệu nguồn. Giải bằng event pipeline bền vững và đối soát.

Một unique index chỉ giải quyết vấn đề **tạo trùng**, không tự ngăn một event cũ ghi đè bản mới. Tương tự, `@Version` của Spring Data phục vụ optimistic locking cho thao tác ghi trong ứng dụng; nó không tự mang ý nghĩa *revision của ERP*. Hai loại version có thể cùng tồn tại nhưng không nên tráo đổi mục đích.

## 7. Mẫu triển khai bằng MongoTemplate: ID xác định và revision

Giả sử bài toán chỉ tạo **một projection nội bộ cho một bản ghi ERP**. Ta chọn ID xác định từ (`sourceSystem`, `externalId`). Để tránh va chạm khi thành phần chứa dấu phân cách, mã hóa Base64 URL-safe từng chuỗi rồi ghép với dấu chấm (dấu chấm không có trong bảng chữ cái Base64 URL-safe).

### 7.1. Mô hình lưu và sự kiện

Sử dụng record `ExternalProduct` đã định nghĩa ở mục 4.2. Mô hình sự kiện:

~~~java
package com.example.integration;

public record ProductChanged(
        String sourceSystem,
        String externalId,
        long revision,
        String title,
        boolean deleted) {
}
~~~

Hai trường `sourceSystem` và `externalId` giữ nguyên theo hợp đồng nguồn. `revision` được giả định là **số tăng đơn điệu theo từng identity**; điều kiện đó rất quan trọng cho logic dưới đây.

### 7.2. Hàm tạo ID xác định

~~~java
package com.example.integration;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class ExternalKeys {
    private ExternalKeys() {}

    public static String productId(String sourceSystem, String externalId) {
        if (sourceSystem == null || sourceSystem.isBlank()
                || externalId == null || externalId.isEmpty()) {
            throw new IllegalArgumentException("Thiếu khóa định danh nguồn");
        }

        Base64.Encoder encoder = Base64.getUrlEncoder().withoutPadding();
        String a = encoder.encodeToString(
                sourceSystem.getBytes(StandardCharsets.UTF_8));
        String b = encoder.encodeToString(
                externalId.getBytes(StandardCharsets.UTF_8));
        return "ext." + a + "." + b;
    }
}
~~~

Đối với cùng cặp khóa, hàm luôn tạo cùng ID. Mã hóa Base64 ở đây **không phải mã hóa bảo mật**; người khác có thể giải mã ra nguồn và external ID. Nếu cần che ID nhạy cảm hoặc giới hạn độ dài, chọn chiến lược ID nội bộ/khóa ánh xạ riêng, hoặc hàm băm có chính sách va chạm phù hợp. Tên nguồn, độ dài ID và quy tắc canonicalization phải được khóa thành hợp đồng; thay đổi quy tắc mã hóa về sau có thể làm phát sinh ID mới.

### 7.3. Import an toàn với sự kiện lặp hoặc sai thứ tự

Trước hết cần cùng package hoặc import `ExternalProduct` từ nơi đặt entity. Ví dụ dưới đây giả sử `ExternalProduct` nằm tại `com.example.integration` và có cấu trúc đúng như mục 4.2.

~~~java
package com.example.integration;

import com.mongodb.client.result.UpdateResult;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Component;

@Component
public class ExternalProductImporter {
    private final MongoTemplate mongo;

    public ExternalProductImporter(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public void apply(ProductChanged event) {
        validate(event);
        String id = ExternalKeys.productId(
                event.sourceSystem(), event.externalId());

        Query onlyNewer = Query.query(
                Criteria.where("id").is(id)
                        .and("sourceRevision").lt(event.revision()));
        Update changes = new Update()
                .set("sourceRevision", event.revision())
                .set("title", event.title())
                .set("deleted", event.deleted());

        UpdateResult changed = mongo.updateFirst(
                onlyNewer, changes, ExternalProduct.class);
        if (changed.getMatchedCount() == 1) {
            return;
        }

        // Không có bản ghi khớp: có thể chưa tồn tại,
        // hoặc event đã trùng/cũ.
        try {
            mongo.insert(new ExternalProduct(
                    id, event.sourceSystem(), event.externalId(),
                    event.revision(), event.title(), event.deleted()));
        } catch (DuplicateKeyException duplicate) {
            ExternalProduct current =
                    mongo.findById(id, ExternalProduct.class);
            if (current == null
                    || !current.sourceSystem().equals(event.sourceSystem())
                    || !current.externalId().equals(event.externalId())) {
                // Có thể là xung đột unique index không liên quan:
                // cần báo lỗi thay vì âm thầm bỏ qua.
                throw duplicate;
            }
            // Nếu worker khác vừa insert hoặc cập nhật thì chỉ ghi
            // khi revision của event thực sự mới hơn.
            mongo.updateFirst(onlyNewer, changes, ExternalProduct.class);
        }
    }

    private static void validate(ProductChanged event) {
        if (event == null
                || event.sourceSystem() == null
                || event.sourceSystem().isBlank()
                || event.externalId() == null
                || event.externalId().isEmpty()
                || event.revision() < 0
                || (!event.deleted()
                        && (event.title() == null
                                || event.title().isBlank()))) {
            throw new IllegalArgumentException("Sự kiện nguồn không hợp lệ");
        }
    }
}
~~~

Giải thích:

1. Với document đã tồn tại và `sourceRevision < incoming.revision`, `updateFirst` cập nhật trạng thái mới trong **một thao tác nguyên tử trên document**.
2. Khi chưa có document, importer thử `insert` với `_id` xác định.
3. Nếu một worker khác vừa tạo document cùng `_id`, MongoDB phát sinh lỗi trùng khóa. Importer xác minh identity rồi **thử update có điều kiện một lần nữa**.
4. Nếu event đến trùng revision hoặc revision thấp hơn, thao tác update không khớp và lần insert trùng ID sẽ không thay đổi document hiện có.
5. `deleted = true` là **tombstone có revision**: giữ document đã đánh dấu xóa giúp chặn event cũ tạo lại trạng thái trước khi xóa.

Ví dụ các event tới theo thứ tự `v17 → v15 → v17 → v18 (deleted)`: trạng thái cuối phải là v18 với `deleted=true`. Một sự kiện v16 đến sau không được kích hoạt lại sản phẩm. Nếu nguồn **tái sử dụng cùng externalId để chỉ một thực thể khác**, cần đưa khái niệm vòng đời/generation vào khóa; revision đơn thuần có thể không đủ.

**Giới hạn của mẫu:** Đây là minh họa cơ chế xử lý snapshot event với revision tăng đơn điệu, chưa phải một importer production hoàn chỉnh. Sự cố có thể xảy ra sau lần thử thứ hai; cần chính sách retry có giới hạn, phân loại lỗi, checkpoint sau khi ghi bền vững, event queue/change streams và giám sát. Nếu event chỉ chứa delta (ví dụ “cộng thêm 3”), không thể thay bằng cách `set` toàn bộ như trên; cần event ID và cơ chế idempotency riêng.

### 7.4. Repository để đọc theo identity

~~~java
package com.example.integration;

import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ExternalProductRepository
        extends MongoRepository<ExternalProduct, String> {

    Optional<ExternalProduct> findBySourceSystemAndExternalId(
            String sourceSystem, String externalId);
}
~~~

Repository giúp đọc entity sau import. Với tên property `sourceSystem` và `externalId`, Spring Data xây dựng điều kiện theo mapping của entity. Nó **không tự bảo đảm uniqueness** nếu database chưa có unique index; việc khai báo `Optional` cũng không tạo unique constraint.

## 8. Unique index và thiết kế nhiều nguồn

MongoDB có unique index mặc định trên `_id`. Khi lưu một ID nội bộ ngẫu nhiên và giữ khóa bên ngoài riêng, cần bảo vệ thêm tính duy nhất của cặp nguồn/khóa:

~~~javascript
db.external_products.createIndex(
  { sourceSystem: 1, externalId: 1 },
  { unique: true, name: "uq_source_external" }
);
~~~

Nếu mỗi tenant có namespace riêng, cân nhắc index:

~~~javascript
db.external_products.createIndex(
  { tenantId: 1, sourceSystem: 1, externalId: 1 },
  { unique: true, name: "uq_tenant_source_external" }
);
~~~

Chỉ dùng biến thể phù hợp với mô hình dữ liệu thực. Trước khi tạo unique index trên collection đã có dữ liệu, phải **kiểm tra và xử lý duplicate hiện hữu**, bảo đảm các field bắt buộc được ghi nhất quán. Unique index không chữa được các bản ghi đã bị tách identity.

Một lựa chọn khác là khai báo metadata:

~~~java
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "external_products")
@CompoundIndex(
    name = "uq_source_external",
    def = "{ 'sourceSystem': 1, 'externalId': 1 }",
    unique = true)
public class ImportedProductIndexModel {
    // Chỉ minh họa annotation index, không thay thế entity ở mục 7.
}
~~~

Đặt annotation trên model chưa đồng nghĩa index sẽ được tạo tự động ở production: việc auto-creation của Spring Data MongoDB phụ thuộc cấu hình, còn thực tế thường nên quản lý index bằng migration/deployment được giám sát. Ví dụ annotation này **chỉ minh họa định nghĩa index**, không phải yêu cầu tạo một entity thứ hai cho cùng collection trong dự án thật.

Khi dùng **ID xác định** như mục 7, unique `_id` đã ngăn tạo hai document có cùng ID. Compound unique index vẫn hữu ích để bảo vệ hợp đồng (`sourceSystem`, `externalId`) nếu có những đường ghi khác, hoặc nếu sau này thay thuật toán cấp `_id`. Đổi index, đổi namespace hoặc thêm tenant phải có kế hoạch chuyển đổi dữ liệu đang tồn tại.

## 9. Những tình huống dữ liệu nhập phức tạp

### 9.1. Nguồn không có revision đáng tin cậy

Không phải API nào cũng cung cấp revision tăng đơn điệu. Trường `updatedAt` từ nhiều máy có thể sai lệch đồng hồ, cùng timestamp hoặc được cập nhật chậm. Không thể tự suy ra thứ tự đúng chỉ từ thời điểm **worker nhận event**.

Các phương án:

- Lấy **snapshot mới nhất** trực tiếp từ nguồn và đồng bộ lại một cách có kiểm soát; không áp dụng event cũ như thể là trạng thái mới nhất.
- Dùng cursor/order do nguồn cấp và bảo đảm tiến trình xử lý có ràng buộc thứ tự trên từng identity.
- Với pipeline có thể tải lại toàn bộ, lưu dấu lần đồng bộ và thực hiện **đối soát định kỳ**, phát hiện bản ghi thiếu hoặc đã bị xóa.
- Nếu nguồn không có bảo đảm thứ tự, tài liệu hóa rõ giới hạn nhất quán; không tuyên bố rằng xử lý sai thứ tự đã được giải quyết.

### 9.2. Xóa và xử lý sự kiện muộn

Nếu xóa document vật lý ngay sau một sự kiện xóa, event cập nhật cũ đến sau có thể tạo lại document. Tombstone giữ `_id`, revision và cờ xóa để ngăn hồi sinh ngoài ý muốn. Việc dọn tombstone cần dựa trên **thời gian lưu event, watermark và chính sách tái sử dụng ID**, không chỉ xóa sau một khoảng thời gian tùy ý.

### 9.3. Một thực thể xuất hiện trong nhiều hệ thống

Khách hàng `crm:123` và `erp:00042` có thể là cùng một người. Nhưng điều này là bài toán **hợp nhất danh tính (entity resolution)**, không thể giải bằng việc hai bản ghi có cùng email hoặc tên.

Nên dùng một ID nội bộ bền vững cùng collection mapping/alias:

~~~json
{
  "_id": "person-7a91",
  "identities": [
    { "sourceSystem": "CRM", "externalId": "123" },
    { "sourceSystem": "ERP", "externalId": "00042" }
  ]
}
~~~

Đây là mô hình khái niệm. Khi nhiều worker thêm alias, cần bảo vệ uniqueness của từng khóa ngoài, xử lý merge/split và cập nhật quan hệ tham chiếu. Với alias số lượng lớn hoặc cần unique index riêng theo khóa, một collection mapping độc lập thường dễ kiểm soát hơn. Không tự động hợp nhất người dùng chỉ dựa trên trường có thể thay đổi hoặc trùng như tên/email.

### 9.4. Bulk import và backfill

Với hàng triệu bản ghi, áp dụng từng lệnh mạng sẽ tốn thời gian. Có thể dùng `MongoTemplate.bulkOps(...)` hoặc driver bulk write để gửi nhiều update/insert theo lô, nhưng phải giữ nguyên:

- khóa ID xác định hoặc unique constraint;
- điều kiện revision để chặn ghi đè event mới bằng dữ liệu backfill cũ;
- retry và xử lý `DuplicateKeyException` theo từng thao tác/lô;
- checkpoint theo lô được xác nhận bền vững;
- giới hạn batch size, memory và thông lượng để không quá tải nguồn/cluster.

Bulk write **không mặc nhiên là transaction nguyên tử cho cả lô**; khi một phần thao tác thất bại, cần hiểu kết quả từng operation và có đường phát lại. Với backlog lớn, chia lô dựa trên nguồn, khóa và mức tải, đo cả chỉ số server lẫn thời gian job.

### 9.5. Bảo mật, phân quyền và dữ liệu nhạy cảm

Không hiển thị thông tin nhạy cảm chỉ vì nó có mặt trong ID hoặc payload. Đối với dữ liệu nhiều tenant, **kiểm tra tenant ở ranh giới truy cập**; có ID đúng không đồng nghĩa người gọi được quyền đọc document. Hạn chế đưa payload chứa email/địa chỉ vào log lỗi, dead-letter queue hoặc index phụ không cần thiết.

Nếu business key bị thay đổi do luật mới, không sửa lại `_id` trong im lặng. Có kế hoạch migration, alias/redirect và kiểm thử các tham chiếu lịch sử. Các cập nhật nhiều document có thể cần transaction khi phải giữ bất biến đồng thời; với read model có thể tái tạo, đồng bộ cuối cùng và đối soát có thể phù hợp hơn.

## 10. Kiểm thử khả năng nhập lại và tính ổn định

Một bộ kiểm thử hữu ích cần sử dụng MongoDB thực (chẳng hạn thông qua Testcontainers) để kiểm tra BSON, unique index và hành vi tranh chấp. `@DataMongoTest` tập trung vào tầng Spring Data MongoDB; test slice này không tự cung cấp MongoDB server.

| Kịch bản | Kết quả mong đợi |
|---|---|
Nhập hai lần cùng (`ERP`, `00042`), cùng revision | Chỉ một document; nội dung cuối không sai khác |
Nhập `v17` rồi `v15` | Giữ dữ liệu `v17` |
Nhập `v17` hai lần rồi `v18` | Cuối cùng là `v18` |
Hai worker import cùng identity lúc collection rỗng | Không có document trùng; revision mới hơn thắng |
Import `ERP:00042` và `CRM:00042` | Hai identity riêng nếu chưa có quy tắc hợp nhất |
Nhập `"00042"` và `"42"` | Không bị gộp nếu nguồn xem là hai ID khác nhau |
Nhập v19 đánh dấu xóa, sau đó nhận v18 cập nhật | Vẫn ở trạng thái xóa v19 |
Khởi động lại job sau khi ghi nhưng trước checkpoint | Có thể phát lại mà không tạo trùng hoặc lùi revision |
Đổi ID ngoài nhưng cùng thực thể miền | ID nội bộ giữ nguyên nếu dùng mapping/alias được quản lý |
Thay kiểu String/ObjectId của `_id` | Test phát hiện khác biệt kiểu BSON và yêu cầu migration |

Có thể kiểm tra trực tiếp bản ghi với MongoDB shell:

~~~javascript
db.external_products.find(
  { sourceSystem: "ERP", externalId: "00042" },
  { _id: 1, sourceRevision: 1, title: 1, deleted: 1 }
);
~~~

Với index đã tạo đúng, truy vấn theo cặp nguồn/ID sẽ có đường truy cập hiệu quả. Chạy `explain("executionStats")` ở môi trường thích hợp để xác nhận plan và số key/document được duyệt, đặc biệt trước khi triển khai import hoặc backfill khối lượng lớn.

Các chỉ số vận hành nên theo dõi:

- Số event nhận, đã áp dụng, bỏ qua do trùng/cũ và lỗi dữ liệu.
- Tỷ lệ duplicate-key exception khi có nhiều worker và số lần retry.
- Độ trễ giữa phiên bản nguồn mới nhất với projection đang lưu.
- Số document trùng identity phát hiện khi đối soát, số bản ghi mồ côi và thời gian backfill.
- Tốc độ nhập, số lệnh ghi, mức sử dụng connection pool và tình trạng index.

## 11. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Biện pháp |
|---|---|---|
Tạo `ObjectId` mới trong mỗi lần import cùng bản ghi | Sinh nhiều document đại diện cùng thực thể | Dùng khóa ngoài ổn định, unique index hoặc ID xác định |
Dùng tên/SKU/email làm `_id` khi chúng có thể thay đổi | Mất liên kết khi đổi thông tin | Tách identity khỏi thuộc tính nghiệp vụ |
Dùng một `externalId` cho mọi hệ thống | Va chạm giữa các nguồn | Tạo namespace (`source`, `externalId`), cộng tenant nếu cần |
Chuyển mọi external ID sang số nguyên | Mất số 0 đầu, không giữ được mã alphanumeric | Lưu String theo hợp đồng nguồn |
Giả định `@Id String` luôn lưu BSON String | Truy vấn raw sai kiểu `_id` | Kiểm tra mapping, dùng `@MongoId(FieldType.STRING)` khi cần |
Chỉ sử dụng `save` mà không kiểm tra event trùng/cũ | Event đến muộn ghi đè trạng thái mới | Revision đáng tin cậy + cập nhật nguyên tử có điều kiện |
Xóa vật lý ngay khi nhận delete | Event cũ có thể hồi sinh document | Tombstone có revision và chính sách dọn an toàn |
Bật nhiều worker nhưng thiếu unique index | Tạo trùng dưới race condition | Tạo unique index/mapping và retry có kiểm soát |
Đồng nhất `@Version` với revision của nguồn | Bỏ sót xung đột hoặc áp dụng sai thứ tự | Tách optimistic lock nội bộ khỏi thứ tự dữ liệu nguồn |
Không có checkpoint/đối soát | Lỗi tạm thời để lại dữ liệu sai lâu dài | Phát lại idempotent, checkpoint bền vững, reconciliation |

## 12. Bài tập vận dụng

**Bài 1 — Chọn khóa.** Một cửa hàng nhận sản phẩm từ ERP và nhà cung cấp B. Cả hai có mã `00042`, SKU đôi khi đổi, tên thay đổi thường xuyên. Hãy đề xuất `_id`, cấu trúc lưu khóa nguồn và unique index. Giải thích khi nào cần một ID nội bộ độc lập.

**Bài 2 — Kiểm tra kiểu BSON.** Tạo hai document có ID Java là chuỗi 24 ký tự hexa: một entity dùng `@Id String`, một entity dùng `@MongoId(FieldType.STRING)`. Đọc bằng driver raw, so sánh kiểu BSON `_id` và kết quả truy vấn với `String`/`ObjectId` tương ứng.

**Bài 3 — Tạo importer idempotent.** Triển khai sự kiện có `sourceSystem`, `externalId`, `revision` và `title`. Chạy chuỗi v7, v8, v7, v8, v9 rồi xác nhận document cuối cùng chứa v9. Thử hai luồng cùng import khi chưa có document.

**Bài 4 — Xử lý xóa.** Bổ sung `deleted` và tombstone vào bài 3. Gửi delete v10 rồi update v9; kiểm tra sản phẩm vẫn bị đánh dấu xóa. Đề xuất điều kiện để có thể xóa tombstone an toàn.

**Bài 5 — Nguồn không có revision.** Giả sử file CSV mỗi ngày chỉ chứa snapshot mới nhất, không có số phiên bản. Hãy thiết kế thứ tự tải, checkpoint, phát hiện record biến mất, xử lý lỗi giữa lô và đối soát. Giải thích vì sao không thể kết luận event nào mới hơn chỉ từ thời điểm worker nhận.

## 13. Ghi nhớ

Trong **Spring Data MongoDB**, `_id` cần là khóa **duy nhất, ổn định và phù hợp với vòng đời thực thể**. `@Id` và `@MongoId` giúp định nghĩa cách ánh xạ định danh sang BSON; khi ID là chuỗi cần chú ý chuyển đổi `ObjectId` và lựa chọn `FieldType.STRING` nếu muốn bảo toàn kiểu lưu.

Với dữ liệu nhập từ hệ thống khác, phải giữ **khóa nguồn có namespace rõ ràng**, tách ID nội bộ khỏi business key có thể thay đổi, và xây dựng đường import có **unique index, idempotency, kiểm tra revision, tombstone, retry, checkpoint và đối soát** theo yêu cầu. `MongoRepository` hỗ trợ truy vấn theo identity; `MongoTemplate` hỗ trợ cập nhật có điều kiện, nhưng chính hợp đồng dữ liệu và mô hình đồng bộ mới bảo đảm một thực thể không bị tạo trùng hoặc quay về trạng thái cũ.
