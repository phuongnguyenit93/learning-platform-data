# Nhận diện tài liệu mới và ảnh hưởng đến trường kiểm toán

Trong Spring Data Elasticsearch, việc một entity được xem là **mới** hay **đã tồn tại** ảnh hưởng trực tiếp đến auditing. Khi lưu entity, auditing có thể điền người tạo và thời điểm tạo, đồng thời cập nhật người sửa và thời điểm sửa. Nếu Spring Data nhận diện sai trạng thái entity, các trường như `createdAt`, `createdBy`, `lastModifiedAt` và `lastModifiedBy` có thể không phản ánh đúng lịch sử nghiệp vụ.

Trạng thái mới/đã tồn tại thường được xác định từ metadata của entity ở phía Spring Data, chẳng hạn ID, trường version hoặc hợp đồng `Persistable.isNew()`. Nó không đơn giản là một truy vấn kiểm tra document có đang tồn tại trong Elasticsearch hay không. Đặc biệt, entity có ID được gán trước có thể bị xem là entity cũ nếu không có cơ chế nhận diện phù hợp.

Để auditing đáng tin cậy, cần thiết kế cùng lúc cách xác định entity mới, cách gán ID và version, cách khai báo các trường audit, nguồn cung cấp người dùng hiện tại, thứ tự callback và quy tắc bảo vệ trường tạo khỏi bị ghi đè.

## 1. Auditing ghi nhận điều gì?

Auditing là cơ chế tự động ghi lại ai tạo hoặc sửa một entity và thời điểm thao tác diễn ra. Trong Spring Data, các annotation thường dùng gồm:

| Annotation | Ý nghĩa |
|---|---|
| `@CreatedDate` | Thời điểm entity được tạo |
| `@CreatedBy` | Người hoặc tiến trình tạo entity |
| `@LastModifiedDate` | Thời điểm entity được sửa gần nhất |
| `@LastModifiedBy` | Người hoặc tiến trình sửa gần nhất |

Ví dụ một sản phẩm:

~~~text
id: product-42
name: Keyboard
createdAt: 2026-11-13T08:00:00Z
createdBy: account-17
lastModifiedAt: 2026-11-13T08:00:00Z
lastModifiedBy: account-17
~~~

Khi người dùng khác cập nhật sản phẩm:

~~~text
id: product-42
name: Mechanical Keyboard
createdAt: 2026-11-13T08:00:00Z
createdBy: account-17
lastModifiedAt: 2026-11-13T09:30:00Z
lastModifiedBy: account-29
~~~

Thông thường, trường created phản ánh lần tạo đầu tiên và được giữ nguyên khi cập nhật; trường last-modified phản ánh lần sửa gần nhất. Khi tạo mới, các trường last-modified thường cũng được thiết lập theo cấu hình auditing. Các trường audit là metadata nghiệp vụ, không nên để request client tự do truyền giá trị vì caller có thể giả mạo lịch sử.

## 2. Bật auditing trong Spring Data Elasticsearch

Spring Data Elasticsearch tích hợp cơ chế auditing của Spring Data Commons. Có thể bật bằng `@EnableElasticsearchAuditing` trong cấu hình ứng dụng.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.elasticsearch.repository.config.EnableElasticsearchAuditing;

import java.time.temporal.TemporalAccessor;
import java.util.Optional;

@Configuration
@EnableElasticsearchAuditing
public class ElasticsearchAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.of("system");
    }
}
~~~

Ví dụ trả về `system` để minh họa một tiến trình hệ thống. Trong ứng dụng thật, `AuditorAware` thường lấy user ID từ security context, request context hoặc thông tin người chạy batch job.

Nếu chỉ cần ngày giờ tạo/sửa, auditing có thể hoạt động mà không cần một auditor cụ thể. Nếu muốn điền `@CreatedBy` và `@LastModifiedBy`, cần cung cấp nguồn auditor phù hợp.

### 2.1. Lấy auditor từ người dùng hiện tại

Một triển khai thực tế có thể đọc principal từ Spring Security:

~~~java
@Bean
AuditorAware<String> auditorAware() {
    return () -> {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null || !authentication.isAuthenticated()) {
            return Optional.empty();
        }

        return Optional.of(authentication.getName());
    };
}
~~~

Đây là ví dụ minh họa; ứng dụng cần xử lý anonymous principal, tài khoản dịch vụ và các luồng không có HTTP request. Không nên trả về tên hiển thị nếu hệ thống cần một định danh ổn định. Dùng user ID hoặc service account ID giúp audit có thể đối chiếu lâu dài.

### 2.2. Cấu hình DateTimeProvider

Nếu cần kiểm soát nguồn thời gian, có thể cấu hình `DateTimeProvider`. Điều này hữu ích khi kiểm thử với clock cố định hoặc khi hệ thống có quy tắc thời gian riêng.

~~~java
@Bean
Clock auditClock() {
    return Clock.systemUTC();
}

@Bean
DateTimeProvider dateTimeProvider(Clock auditClock) {
    return () -> Optional.<TemporalAccessor>of(Instant.now(auditClock));
}
~~~

Sau đó tham chiếu provider trong cấu hình auditing theo API của release train đang sử dụng. Tùy phiên bản, kiểu temporal được trả về và tên thuộc tính cấu hình có thể khác; hãy đối chiếu chữ ký của `DateTimeProvider` trong dependency thực tế.

Dùng UTC cho timestamp thường giúp tránh nhập nhằng múi giờ. Khi hiển thị cho người dùng, chuyển sang múi giờ phù hợp ở tầng trình bày.

## 3. Khai báo các trường audit trên entity

Một entity có thể khai báo các trường audit bằng annotation:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Version
    private Long version;

    private String name;

    @CreatedDate
    @Field(type = FieldType.Date)
    private Instant createdAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedDate
    @Field(type = FieldType.Date)
    private Instant lastModifiedAt;

    @LastModifiedBy
    private String lastModifiedBy;

    // constructors, getters and setters
}
~~~

`@CreatedDate` và `@LastModifiedDate` đánh dấu các trường thời gian. `@CreatedBy` và `@LastModifiedBy` đánh dấu trường auditor. `@Version` là metadata versioning riêng, đồng thời có thể tham gia vào chiến lược nhận diện entity mới.

Không bắt buộc mọi entity đều có đủ bốn trường audit. Hãy chọn những trường mà nghiệp vụ cần. Ví dụ một index dữ liệu tham chiếu có thể chỉ cần created date, còn hệ thống quản trị cần cả created/modified user và timestamp.

### 3.1. Kiểu dữ liệu của trường thời gian

Các kiểu Java thường dùng gồm `Instant`, `LocalDateTime` hoặc các kiểu temporal mà Spring Data hỗ trợ. Với dữ liệu cần biểu diễn một thời điểm toàn cục, `Instant` thường dễ xử lý nhất vì nó không mang múi giờ địa phương.

Field thời gian cần mapping tương ứng, thường là `date`. Hãy kiểm tra mapping được tạo và định dạng serialize thực tế. Không lưu timestamp audit dưới dạng chuỗi tùy ý nếu ứng dụng cần sort, range query hoặc date aggregation.

### 3.2. Trường audit nên do server quản lý

DTO nhận request tạo/sửa không nên cho phép client quyết định `createdAt`, `createdBy`, `lastModifiedAt`, `lastModifiedBy` hoặc `version`. Tách DTO đầu vào khỏi persistence entity giúp tránh việc dữ liệu gửi từ client ghi đè metadata do server quản lý. Khi map DTO sang entity, chỉ sao chép các field nghiệp vụ được phép thay đổi.

## 4. Spring Data nhận diện entity mới như thế nào?

Spring Data cần biết entity đang được persist lần đầu hay đã được lưu trước đó. Thông tin này được dùng trong nhiều phần của persistence lifecycle, bao gồm auditing.

Chiến lược nhận diện entity mới thông thường dựa trên:

1. Trường version nếu entity có version property phù hợp.
2. Nếu không có version property, kiểm tra identifier.
3. Nếu entity triển khai `Persistable`, phương thức `isNew()` có thể cung cấp quyết định tùy chỉnh.

Quy tắc chi tiết còn phụ thuộc kiểu property và mapping metadata của phiên bản Spring Data. Vì vậy, cần kiểm tra chiến lược đang áp dụng cho entity cụ thể thay vì chỉ suy luận từ việc ID có giá trị.

### 4.1. Dựa trên ID

Với entity không có version property và không triển khai `Persistable`, ID null thường là dấu hiệu entity mới:

~~~java
Product product = new Product();
product.setId(null);
product.setName("Keyboard");
~~~

Spring Data có thể xem entity này là mới dựa trên ID chưa được gán. Đây là trường hợp đơn giản khi hệ thống để persistence layer sinh ID hoặc gán ID sau khi tạo entity.

Ngược lại, nếu ID đã có giá trị:

~~~java
Product product = new Product();
product.setId("product-42");
product.setName("Keyboard");
~~~

entity có thể được xem là đã tồn tại nếu không có thông tin version hoặc cơ chế tùy chỉnh chứng minh nó là mới. Điều này vẫn có thể xảy ra ngay cả khi document ID đó chưa từng được index vào Elasticsearch.

**ID đã được gán không đồng nghĩa document đã tồn tại trong index**, nhưng chiến lược mặc định dựa trên ID có thể xem entity là cũ.

### 4.2. Dựa trên version property

Khi entity có version property, Spring Data có thể dùng giá trị version để nhận diện trạng thái. Với version object nullable như `Long`, version null thường biểu thị entity mới; version đã có giá trị biểu thị entity đã được lưu và có version hiện tại.

Ví dụ:

~~~java
Product product = new Product();
product.setId("product-42"); // ID được gán trước
product.setVersion(null);    // Chưa có version được lưu
product.setName("Keyboard");
~~~

Trong mô hình này, version null cho phép Spring Data nhận diện entity mới dù ID đã được gán trước. Sau khi lưu thành công, persistence layer trả về hoặc cập nhật version theo cơ chế versioning của Elasticsearch.

Nên dùng kiểu wrapper nullable như `Long` nếu cần trạng thái null biểu thị chưa được lưu. Kiểu primitive như `long` không thể mang giá trị null; Spring Data có quy tắc riêng cho giá trị mặc định của primitive, nhưng wrapper thường diễn đạt trạng thái mới rõ ràng hơn.

### 4.3. Version vừa nhận diện trạng thái vừa hỗ trợ optimistic locking

`@Version` không chỉ là cờ new/existing. Nó còn tham gia vào kiểm soát cập nhật đồng thời. Khi lưu entity đã tồn tại với version cũ, Elasticsearch có thể phát hiện version conflict thay vì ghi đè một cập nhật mới hơn.

Vì vậy:

- Không tự ý đặt version của entity đang tồn tại về null để ép auditing coi entity là mới.
- Không lấy version từ request client làm dữ liệu tin cậy.
- Khi đọc entity, giữ version trả về từ persistence layer.
- Khi update, dùng entity/version mới nhất hoặc xử lý conflict theo nghiệp vụ.

Dùng version để nhận diện new entity chỉ có ý nghĩa nếu vòng đời version được quản lý nhất quán.

## 5. Khi ID được gán trước khi lưu

Nhiều ứng dụng cần ID ổn định trước khi ghi, ví dụ ID đến từ hệ thống nghiệp vụ khác, UUID được tạo ở tầng service, mã sản phẩm hoặc dữ liệu import từ nguồn ngoài.

Trong trường hợp đó, chỉ dựa trên ID để nhận diện entity mới có thể dẫn đến auditing sai. Hai cách thường cân nhắc:

1. Dùng version property nullable để phân biệt entity chưa có version và entity đã được lưu.
2. Triển khai `Persistable<ID>` để cung cấp trạng thái new theo quy tắc của ứng dụng.

Không nên dùng một truy vấn tồn tại cho từng entity chỉ để quyết định created hay modified nếu có thể giải quyết bằng metadata vòng đời. Cách đó thêm round-trip, dễ phát sinh race condition và vẫn cần xử lý đồng thời.

## 6. Tùy chỉnh trạng thái mới bằng Persistable

Spring Data Commons cung cấp interface `Persistable<ID>` với hai phương thức chính: `getId()` trả về identifier và `isNew()` cho biết entity có phải mới hay không.

Khi entity triển khai `Persistable`, ứng dụng có thể tự định nghĩa trạng thái mới. Điều này hữu ích khi ID được gán trước nhưng entity chưa được lưu.

~~~java
import org.springframework.data.domain.Persistable;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.elasticsearch.annotations.Document;

@Document(indexName = "products")
public class Product implements Persistable<String> {

    @Id
    private String id;

    @Transient
    private boolean newEntity = true;

    private String name;

    @Override
    public String getId() {
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

`newEntity` được đánh dấu `@Transient` để không trở thành field dữ liệu trong Elasticsearch. Sau khi save thành công, ứng dụng phải chuyển trạng thái entity sang đã lưu. Cách chuyển trạng thái cần được thiết kế phù hợp với cách Spring Data trả về entity và vòng đời object của ứng dụng.

Ví dụ service:

~~~java
Product saved = operations.save(product);
saved.markPersisted();
~~~

Đây là minh họa cho hợp đồng trạng thái; trong ứng dụng thực tế, cần bảo đảm object được trả về là object được quản lý tiếp theo và việc đánh dấu không bị mất khi entity được copy hoặc tái tạo. Với entity immutable hoặc aggregate được tạo lại thường xuyên, version property thường dễ quản lý hơn.

### 6.1. Vì sao phải đồng bộ cờ new với lifecycle?

Nếu cờ vẫn là true sau khi lưu, lần save tiếp theo có thể tiếp tục được xem là create và các trường created có thể bị đặt lại. Nếu cờ bị chuyển false trước khi write thành công, lần retry có thể bị xem là update dù document chưa được tạo.

Hãy đổi trạng thái sau khi persistence thành công và bảo đảm trạng thái được giữ nhất quán qua reload, retry và các luồng tạo entity.

## 7. Entity mới ảnh hưởng đến auditing ra sao?

Auditing handler nhận biết entity mới để quyết định có đặt các trường tạo hay không. Về mặt khái niệm:

~~~text
Entity được gửi vào persistence
             |
             v
       Xác định isNew
             |
        +----+----+
        |         |
       true      false
        |         |
        v         v
  Điền created  Giữ created
  metadata      metadata
        |         |
        +----+----+
             |
             v
     Cập nhật modified
     metadata theo cấu hình
             |
             v
     Chuyển entity thành
       Elasticsearch
             |
             v
          Index
~~~

Kết quả thường mong muốn:

| Trạng thái | Created fields | Last-modified fields |
|---|---|---|
| Entity mới | Được thiết lập | Được thiết lập theo cấu hình auditing |
| Entity đã tồn tại | Được giữ nguyên | Được cập nhật |
| No-op hoặc không có thay đổi | Không nên bị thay đổi ngoài ý muốn | Phụ thuộc thao tác có thực sự được lưu hay không |

Nếu entity mới bị nhận diện thành entity cũ, auditing có thể bỏ qua việc điền created fields. Nếu entity cũ bị nhận diện thành entity mới, created fields có thể bị ghi đè bằng thời điểm hoặc người tạo mới.

## 8. Callback trong vòng đời lưu entity

Spring Data Elasticsearch cung cấp Entity Callback để chạy logic ở các thời điểm khác nhau trong quá trình chuyển đổi và lưu document.

| Callback | Thời điểm | Use case |
|---|---|---|
| `BeforeConvertCallback` | Trước khi entity được chuyển thành Document | Chuẩn hóa entity, điền giá trị cần được serialize |
| `BeforeSaveCallback` | Sau khi chuyển đổi, trước khi ghi Document | Điều chỉnh hoặc kiểm tra Document sẽ được lưu |
| `AfterSaveCallback` | Sau khi ghi thành công | Ghi log, phát tín hiệu hoặc xử lý hậu lưu |
| `AfterConvertCallback` | Sau khi đọc và chuyển Document thành entity | Bổ sung dữ liệu sau khi load |

Auditing thường được thực hiện ở giai đoạn trước khi entity được chuyển thành Document, để các trường audit được đưa vào nội dung lưu trữ.

### 8.1. BeforeConvertCallback

Callback này nhận entity và index coordinates. Nếu cần thay đổi entity trước khi serialize, đây thường là điểm phù hợp:

~~~java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class ProductBeforeConvertCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product entity,
            IndexCoordinates index
    ) {
        entity.normalizeName();
        return entity;
    }
}
~~~

Ví dụ chuẩn hóa tên sản phẩm. Callback phải trả về entity sẽ được chuyển đổi. Nếu thay đổi field cần được lưu, thực hiện trước conversion để converter đưa giá trị mới vào Document.

### 8.2. BeforeSaveCallback

Callback này chạy sau conversion, nhận cả entity và Document. Có thể dùng khi cần điều chỉnh nội dung document sau khi converter đã tạo:

~~~java
@Component
public class ProductBeforeSaveCallback
        implements BeforeSaveCallback<Product> {

    @Override
    public Product onBeforeSave(
            Product entity,
            Document document,
            IndexCoordinates index
    ) {
        document.put("schemaRevision", 3);
        return entity;
    }
}
~~~

Ở đây `schemaRevision` được thêm trực tiếp vào Document. Thay đổi Document ở callback này không nhất thiết cập nhật lại object entity trong bộ nhớ. Nếu cần cập nhật trường audit trên entity để các giá trị được phản ánh cả trong object trả về lẫn Document, hãy thực hiện ở giai đoạn trước conversion.

### 8.3. AfterSaveCallback

`AfterSaveCallback` chạy sau khi thao tác ghi hoàn tất. Có thể dùng để ghi log hoặc phát sự kiện:

~~~java
@Component
public class ProductAfterSaveCallback
        implements AfterSaveCallback<Product> {

    @Override
    public Product onAfterSave(
            Product entity,
            IndexCoordinates index
    ) {
        auditLog.recordSaved(entity.getId(), index.getIndexName());
        return entity;
    }
}
~~~

Không dùng AfterSave để điền `createdAt` hoặc `lastModifiedAt` nếu các giá trị đó phải được lưu trong chính document vừa ghi. Lúc callback này chạy, write đã hoàn tất; thay đổi entity lúc này không tự động được ghi lại lần nữa.

### 8.4. Callback không thay thế auditing

Có thể tự viết callback để điền audit fields, nhưng nếu đã dùng auditing infrastructure, không nên tạo một cơ chế khác ghi cùng trường mà không có quy tắc ưu tiên rõ ràng.

Ví dụ một custom BeforeConvertCallback đặt createdAt sau auditing callback có thể ghi đè timestamp do auditing đã thiết lập. Callback order vì vậy có ý nghĩa. Khi có nhiều callback cùng thay đổi một field, hãy xác định thứ tự bằng cơ chế ordering của Spring và kiểm thử kết quả cuối cùng.

## 9. Thứ tự callback và ảnh hưởng đến trường audit

Một luồng save điển hình có thể hình dung như sau:

~~~text
Repository / ElasticsearchOperations.save(entity)
                       |
                       v
             BeforeConvert callbacks
                       |
                       v
              Convert entity
                       |
                       v
               BeforeSave callbacks
                       |
                       v
             Ghi document vào index
                       |
                       v
                AfterSave callbacks
                       |
                       v
                Trả entity đã lưu
~~~

Auditing callback là một callback trong lifecycle này. Khi entity được xem là mới, auditing điền created metadata; khi entity đã tồn tại, nó giữ created metadata và cập nhật modified metadata theo cấu hình.

Nếu có callback tùy chỉnh:

- Không xóa hoặc ghi đè audit fields không có chủ đích.
- Đặt thứ tự rõ ràng nếu nhiều callback sửa cùng entity.
- Tránh thực hiện một lần save lồng bên trong callback vì có thể tạo vòng lặp hoặc write dư thừa.
- Không phát sự kiện nghiệp vụ “đã lưu” từ BeforeSave; chỉ phát sau khi write thành công.
- Nếu callback trả về một instance khác, bảo đảm các field audit và version được giữ lại.

## 10. modifyOnCreate và trường last-modified

Auditing configuration có tùy chọn `modifyOnCreate`. Với cấu hình mặc định thông dụng, các trường last-modified cũng được điền khi entity mới được tạo. Nếu đặt `modifyOnCreate = false`, auditing có thể chỉ cập nhật modified fields khi entity đã tồn tại.

Ý nghĩa nghiệp vụ:

- Nếu muốn một record vừa tạo cũng có `lastModifiedAt` bằng `createdAt`, giữ hành vi modify-on-create.
- Nếu định nghĩa “modified” là đã có một lần sửa sau khi tạo, có thể tắt modify-on-create.

Hãy thống nhất semantics với nhóm phát triển và báo cáo. Nếu dashboard kỳ vọng mọi document đều có lastModifiedAt, tắt modify-on-create có thể làm một số bản ghi mới không có giá trị.

## 11. Trường created có bị ghi đè khi update không?

Theo semantics auditing, created fields đại diện lần tạo đầu tiên nên được giữ nguyên khi update entity đã tồn tại. Modified fields được cập nhật theo thời điểm và auditor hiện tại.

Ví dụ:

~~~json
{
  "name": "Keyboard",
  "createdAt": "2026-11-13T08:00:00Z",
  "createdBy": "user-17",
  "lastModifiedAt": "2026-11-13T08:00:00Z",
  "lastModifiedBy": "user-17"
}
~~~

~~~json
{
  "name": "Mechanical Keyboard",
  "createdAt": "2026-11-13T08:00:00Z",
  "createdBy": "user-17",
  "lastModifiedAt": "2026-11-13T09:30:00Z",
  "lastModifiedBy": "user-29"
}
~~~

Nếu update request tạo một entity mới chỉ với ID và field name rồi bỏ trống created fields, kết quả phụ thuộc cách entity được nhận diện và cách save/index được thực hiện. Đừng tự map created fields thành null rồi kỳ vọng auditing luôn khôi phục đúng giá trị cũ.

Đối với update, cách an toàn thường là load entity hiện tại, thay đổi field nghiệp vụ rồi save lại, hoặc dùng một update API có quy tắc giữ nguyên audit fields rõ ràng. Nếu ứng dụng gửi một entity detached với ID đã gán, cần bảo đảm trạng thái new/existing được xác định đúng và created fields không bị xóa.

## 12. Assigned ID và trường hợp auditing bị sai

Xét entity có ID do ứng dụng cấp:

~~~java
Product product = new Product();
product.setId("SKU-2026-001");
product.setName("Keyboard");

operations.save(product);
~~~

Nếu entity không có version property và không triển khai `Persistable`, chiến lược dựa trên ID có thể xem nó là entity đã tồn tại vì ID khác null. Khi đó created fields có thể không được điền và last-modified fields có thể được cập nhật như một lần sửa.

Điều này không có nghĩa document chắc chắn đã tồn tại trong Elasticsearch. Nó chỉ phản ánh cách Spring Data suy ra trạng thái entity.

### 12.1. Cách khắc phục bằng version

Khai báo version nullable:

~~~java
@Id
private String id;

@Version
private Long version;
~~~

Khi tạo mới, để version null. Khi đọc document đã lưu, giữ version mà Spring Data trả về. Không tự đặt version null trên một entity đang tồn tại để buộc auditing xem nó là mới.

### 12.2. Cách khắc phục bằng Persistable

Nếu nghiệp vụ có trạng thái new riêng, triển khai `Persistable` và quản lý cờ isNew qua lifecycle. Đây là lựa chọn phù hợp khi ID được gán trước và version không phải công cụ phù hợp với mô hình dữ liệu.

### 12.3. Không dùng ID trong bộ nhớ để kết luận document tồn tại

ID có thể được tạo ở tầng application trước khi có write. Ngược lại, ID có thể đã tồn tại nhưng entity detached hiện tại không chứa version. Hãy phân biệt ID đã được tạo, document đã được lưu và entity được Spring Data nhận diện là mới hay cũ. Ba trạng thái này liên quan nhưng không đồng nhất.

## 13. save, index và các API ghi khác

Trong Spring Data Elasticsearch, repository hoặc `ElasticsearchOperations.save(...)` là các abstraction có thể áp dụng mapping và entity callbacks theo lifecycle của Spring Data.

Nếu gọi trực tiếp Elasticsearch Java Client hoặc REST API ở tầng thấp, ứng dụng tự chịu trách nhiệm serialize field, gán created/modified metadata, truyền version/concurrency token và áp dụng quy tắc ID/trạng thái entity. Không mặc định callback hoặc auditing của Spring Data tự chạy khi ghi bằng low-level client.

### 13.1. save với ID đã có

Elasticsearch index operation ghi document theo ID. Nếu ID chưa tồn tại, thao tác có thể tạo document; nếu ID đã tồn tại, thao tác có thể thay thế nội dung document theo semantics index. Việc write có thể là upsert về mặt storage không đồng nghĩa auditing biết chính xác đó là create hay update.

Auditing dựa trên trạng thái entity mà Spring Data xác định. Vì vậy, cần bảo đảm new detection phù hợp với cách ứng dụng tạo ID.

### 13.2. Update API và script

Partial update hoặc script update ở mức Elasticsearch có thể thay đổi document mà không đi qua entity callback auditing. Nếu dùng các API này, hãy tự quản lý modified fields trong script/params hoặc chuyển thao tác qua một abstraction có hỗ trợ callback phù hợp.

Ví dụ update script chỉ thay name:

~~~json
{
  "script": {
    "source": "ctx._source.name = params.name",
    "params": {
      "name": "Mechanical Keyboard"
    }
  }
}
~~~

Script này không tự cập nhật `lastModifiedAt` hoặc `lastModifiedBy`. Nếu muốn audit metadata nhất quán, cần bổ sung rõ vào script hoặc dùng cơ chế update được ứng dụng quản lý.

### 13.3. Bulk operations

Bulk API và các abstraction bulk của Spring Data có thể đi theo con đường mapping khác với save từng entity. Không nên giả định mọi callback auditing đều được gọi cho từng item trong mọi phiên bản và mọi overload.

Nếu dùng bulk indexing cho dữ liệu cần audit:

- Xác minh callback nào được áp dụng trong API/version đang dùng.
- Nếu callback không chạy, chuẩn bị audit fields trước khi tạo bulk request.
- Đặt created fields và modified fields theo đúng trạng thái new/existing của từng item.
- Kiểm tra kết quả từng item và xử lý retry.

## 14. Auditing trong import và đồng bộ dữ liệu

Import thường có dữ liệu ID được cấp từ nguồn ngoài. Đây là tình huống dễ nhầm giữa create và update.

Ví dụ một batch chứa record hoàn toàn mới với ID được gán từ hệ thống nguồn, record đã tồn tại và cần thay đổi nội dung, hoặc record có ID nhưng dữ liệu nguồn không biết document đã tồn tại hay chưa.

Ứng dụng cần định nghĩa semantics:

| Trường hợp | Quy tắc audit thường dùng |
|---|---|
| Tạo mới từ nguồn ngoài | Điền created và modified theo thời điểm/user import |
| Cập nhật document đã có | Giữ created, cập nhật modified |
| Đồng bộ lại cùng dữ liệu, không có thay đổi | Có thể bỏ qua update để tránh đổi modifiedAt không cần thiết |
| Ghi đè toàn bộ document | Phải bảo đảm created fields được giữ nếu nghiệp vụ yêu cầu |
| Import lịch sử có timestamp gốc | Quyết định rõ giữ timestamp nguồn hay ghi timestamp import; không trộn hai ý nghĩa |

Nếu cần giữ thời điểm tạo gốc từ hệ thống nguồn, hãy thiết kế field riêng hoặc một quy tắc import có thẩm quyền rõ ràng. Không để auditing tự động ghi đè dữ liệu lịch sử mà nghiệp vụ cần bảo toàn.

## 15. No-op và trường last-modified

Một thao tác save có thể được gửi dù giá trị nghiệp vụ không thay đổi. Tùy API và cách cập nhật, auditing có thể vẫn tạo timestamp modified mới nếu lifecycle coi đó là một lần sửa.

Nếu muốn `lastModifiedAt` chỉ thay đổi khi dữ liệu thực sự đổi:

1. So sánh dữ liệu mới với dữ liệu hiện tại.
2. Nếu không có khác biệt, bỏ qua write.
3. Nếu có khác biệt, cập nhật entity và để auditing điền modified fields.

Với update script, có thể đặt no-op khi không có thay đổi:

~~~painless
if (ctx._source.status == params.status) {
    ctx.op = 'noop';
} else {
    ctx._source.status = params.status;
    ctx._source.lastModifiedAt = params.modifiedAt;
    ctx._source.lastModifiedBy = params.modifiedBy;
}
~~~

Trong trường hợp này, script chịu trách nhiệm điền modified metadata vì thao tác không đi qua auditing callback thông thường. Nếu hệ thống dùng cả repository save và script update, cần dùng cùng một quy tắc timestamp và auditor để tránh hai đường ghi tạo audit khác nhau.

## 16. Callback order và nhiều callback cùng sửa entity

Một ứng dụng có thể có nhiều callback: callback chuẩn hóa dữ liệu, callback sinh slug, auditing callback và callback thêm metadata tenant hoặc schema.

Nếu callback sau cùng thay đổi field mà auditing vừa điền, giá trị cuối có thể khác mong đợi. Dùng cơ chế ordering được Spring hỗ trợ để xác định thứ tự và kiểm thử kết quả sau khi save.

~~~java
@Component
@Order(100)
public class NormalizeProductCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product product,
            IndexCoordinates index
    ) {
        product.setName(product.getName().trim());
        return product;
    }
}
~~~

Thứ tự số cụ thể cần được chọn dựa trên callback auditing đang được đăng ký trong phiên bản ứng dụng. Không mặc định rằng mọi callback đều có thứ tự như ví dụ. Nếu callback chỉ thay đổi field nghiệp vụ, đặt trước auditing thường giúp lifecycle dễ hiểu; nếu callback cần đọc audit fields đã được gán, nó phải chạy sau auditing.

## 17. Kiểm thử trạng thái mới và audit fields

Nên kiểm thử auditing với cả entity ID tự sinh và ID được gán trước.

### 17.1. Kiểm thử tạo mới

Điều kiện: entity được xác định là mới, AuditorAware trả về user A và clock trả về thời điểm T1.

Kỳ vọng:

- `createdAt = T1`.
- `createdBy = user A`.
- `lastModifiedAt` theo cấu hình modify-on-create.
- `lastModifiedBy` theo cấu hình modify-on-create.
- Version được thiết lập sau khi lưu theo cơ chế persistence.

### 17.2. Kiểm thử cập nhật

Load entity đã lưu với version hiện tại, chuyển auditor sang user B, chuyển clock sang thời điểm T2, thay đổi field nghiệp vụ và save.

Kỳ vọng:

- `createdAt` vẫn là T1.
- `createdBy` vẫn là user A.
- `lastModifiedAt = T2`.
- `lastModifiedBy = user B`.
- Version được tăng hoặc thay đổi theo cơ chế versioning.

### 17.3. Kiểm thử assigned ID

Tạo entity có ID được gán trước và version null. Xác nhận entity được xem là mới và created fields được điền. Sau khi save, đọc lại entity và xác nhận lần save tiếp theo được xem là update.

Nếu dùng `Persistable`, kiểm thử cả việc cờ isNew chuyển false sau save thành công và vẫn đúng khi write thất bại.

### 17.4. Kiểm thử entity ID có giá trị nhưng chưa tồn tại

Đây là trường hợp bắt lỗi nhầm lẫn:

1. Tạo ID cố định.
2. Xác nhận document chưa có trong index.
3. Tạo entity với ID đó.
4. Kiểm tra new detection.
5. Save và xác nhận created fields được điền.

Nếu entity bị xem là cũ chỉ vì ID khác null, cần dùng version hoặc Persistable theo thiết kế.

## 18. Ma trận trường hợp biên

| Trường hợp | Rủi ro | Cần xác nhận |
|---|---|---|
| ID null, chưa có version | Thường là new | Created fields được điền |
| ID được gán trước, version null | Dễ bị nhầm nếu không có version strategy | Entity được xem là new |
| ID có giá trị, không có version | Có thể bị xem là existing | Chọn Persistable hoặc chiến lược khác nếu ID mới |
| Version đã có giá trị | Existing | Created fields được giữ |
| Version bị đặt null trên entity cũ | Có thể bị xem là new | Không làm mất version hiện tại |
| Client gửi createdAt | Có nguy cơ giả mạo | DTO không cho phép ghi đè |
| AuditorAware trả Optional.empty | By fields không có giá trị mới | Xử lý user hệ thống hoặc cho phép thiếu có chủ đích |
| Callback tùy chỉnh sửa audit field | Có thể ghi đè auditing | Thứ tự callback rõ ràng |
| Update bằng low-level client | Callback không chạy tự động | Script/client tự cập nhật modified fields |
| Bulk write | Callback phụ thuộc API/version | Kiểm tra audit fields từng item |
| Save không thay đổi dữ liệu | ModifiedAt có thể đổi dù nội dung không đổi | Xác định semantics no-op |
| Write thất bại | Không được đánh dấu entity persisted quá sớm | Retry vẫn nhận diện đúng trạng thái |

## 19. Quy trình thiết kế auditing đáng tin cậy

Khi thêm auditing vào một entity:

1. Xác định ID do Elasticsearch, ứng dụng hay hệ thống ngoài cấp.
2. Chọn chiến lược new detection phù hợp: ID, version hoặc Persistable.
3. Nếu ID được gán trước, không mặc định entity là existing chỉ vì ID khác null.
4. Khai báo created/modified fields với kiểu dữ liệu và mapping phù hợp.
5. Bật `@EnableElasticsearchAuditing`.
6. Cung cấp `AuditorAware` nếu cần createdBy/lastModifiedBy.
7. Cấu hình DateTimeProvider nếu cần kiểm soát nguồn thời gian.
8. Kiểm tra callback nào được gọi trên đường save, bulk và low-level client.
9. Đảm bảo created fields được bảo toàn qua update.
10. Đảm bảo modified fields được cập nhật theo đúng semantics nghiệp vụ.
11. Kiểm soát callback order nếu nhiều callback cùng sửa entity.
12. Kiểm thử insert, update, assigned ID, retry, no-op và version conflict.

## 20. Kết luận

Auditing phụ thuộc vào việc Spring Data nhận diện entity mới hay đã tồn tại. Khi entity mới, auditing điền created metadata; khi entity đã tồn tại, created fields cần được giữ nguyên và modified fields được cập nhật theo cấu hình. Việc nhận diện thường dựa trên version property, ID hoặc hợp đồng `Persistable.isNew()`.

Entity có ID được gán trước là trường hợp cần chú ý: ID khác null không chứng minh document đã tồn tại, nhưng chiến lược mặc định dựa trên ID có thể xem entity là cũ. Dùng version nullable hoặc `Persistable` khi cần biểu diễn rõ entity mới với assigned ID. Không đặt version của entity cũ về null để ép auditing chạy theo nhánh tạo mới.

Trong Spring Data Elasticsearch, `@EnableElasticsearchAuditing`, `AuditorAware`, các annotation created/modified và entity callbacks phối hợp để điền metadata trong lifecycle save. `BeforeConvertCallback` phù hợp với thay đổi entity cần serialize; `BeforeSaveCallback` làm việc với Document sau conversion; `AfterSaveCallback` phù hợp với xử lý hậu lưu. Ghi trực tiếp qua client hoặc một số bulk path có thể không đi qua cùng callback lifecycle, nên phải xác minh API thực tế và tự quản lý audit fields khi cần.

Hãy kiểm thử riêng entity mới, entity đã lưu, assigned ID, version, callback order, retry và thao tác không làm thay đổi dữ liệu. Khi trạng thái new/existing được xác định đúng, các trường created và last-modified mới phản ánh đáng tin cậy lịch sử của document.
