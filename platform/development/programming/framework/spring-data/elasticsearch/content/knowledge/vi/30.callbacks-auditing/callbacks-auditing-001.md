# Entity callback và các mốc xử lý dữ liệu

Spring Data Elasticsearch cung cấp **entity callback** để ứng dụng can thiệp vào entity tại những thời điểm xác định trong vòng đời đọc và ghi dữ liệu. Ví dụ, ứng dụng có thể chuẩn hóa SKU trước khi chuyển entity thành JSON, bổ sung trường vào document trước khi gửi lên Elasticsearch, hoặc hoàn thiện entity sau khi đọc kết quả.

Các callback gắn với những mốc xử lý cụ thể: trước khi convert entity, trước khi lưu document, sau khi lưu và sau khi convert document thành entity. Hiểu đúng thứ tự này giúp đặt logic vào đúng chỗ, tránh sửa dữ liệu quá muộn hoặc thực hiện cùng một công việc ở nhiều tầng.

Trong cùng nhóm tính năng, Spring Data Elasticsearch còn có **mapping events** và **auditing**. Mapping events thông báo các sự kiện trong quá trình đọc/ghi; auditing tự động quản lý các trường như ngày tạo, ngày sửa và người thực hiện. Chúng có liên quan nhưng không thay thế lẫn nhau.

Bài này dùng entity **Product** và index **products** để minh họa các mốc xử lý, callback, event listener và auditing. Các ví dụ tập trung vào API Spring Data Elasticsearch hiện đại; chữ ký chi tiết có thể khác giữa các phiên bản thư viện, vì vậy cần đối chiếu dependency đang dùng trước khi áp dụng.

## 1. Vòng đời của một entity khi ghi vào Elasticsearch

Khi lưu một entity thông qua Spring Data Elasticsearch, ứng dụng không gửi trực tiếp object Java nguyên trạng. Spring Data chuyển entity thành cấu trúc document, sau đó gửi document tới Elasticsearch.

Luồng ghi cơ bản:

~~~text
Product entity
      |
      v
BeforeConvertCallback
      |
      v
MappingElasticsearchConverter
      |
      v
Document (JSON-like structure)
      |
      v
BeforeSaveCallback
      |
      v
Elasticsearch request
      |
      v
Elasticsearch index
      |
      v
AfterSaveCallback
      |
      v
Kết quả trả về cho caller
~~~

Các mốc có ý nghĩa khác nhau:

1. **BeforeConvert:** entity Java vẫn đang ở dạng object. Đây là lúc phù hợp để chuẩn hóa hoặc bổ sung giá trị trên entity trước khi converter đọc các thuộc tính.
2. **Convert:** MappingElasticsearchConverter ánh xạ entity thành Document theo metadata, annotation và custom conversions.
3. **BeforeSave:** document đã được tạo. Callback có thể kiểm tra hoặc thay đổi dữ liệu sẽ được gửi tới Elasticsearch.
4. **Save:** Spring Data gửi request tới index đích.
5. **AfterSave:** thao tác lưu đã hoàn tất. Callback có thể xử lý entity sau khi ghi, chẳng hạn phản ánh metadata được cập nhật trong kết quả.

Callback không phải là một transaction bao trùm Elasticsearch và các hệ thống khác. Nếu callback sau khi lưu phát sinh lỗi, thao tác ghi ở Elasticsearch có thể đã thành công. Không nên giả định exception ở AfterSaveCallback tự động rollback document vừa ghi.

## 2. Vòng đời khi đọc dữ liệu

Khi đọc một document, Spring Data lấy dữ liệu từ Elasticsearch rồi chuyển source thành entity Java.

Luồng đọc khái quát:

~~~text
Elasticsearch response
      |
      v
Document (_source)
      |
      v
AfterLoadEvent (mapping event)
      |
      v
MappingElasticsearchConverter
      |
      v
Product entity
      |
      v
AfterConvertCallback
      |
      v
Entity trả về cho caller
~~~

Ở giai đoạn này:

- AfterLoadEvent thông báo document đã được tải.
- MappingElasticsearchConverter chuyển các trường trong document thành thuộc tính Java.
- AfterConvertCallback nhận entity đã được tạo cùng document nguồn và index coordinates.
- Caller nhận entity sau khi quá trình mapping hoàn tất.

AfterConvertCallback phù hợp khi cần bổ sung trạng thái tính toán trong bộ nhớ hoặc hoàn thiện object sau khi đọc. Nếu giá trị cần được lưu bền vững trong Elasticsearch, hãy xử lý ở giai đoạn trước khi ghi; thay đổi entity sau convert không tự cập nhật document đã lưu.

Một thao tác tìm kiếm có thể chuyển đổi nhiều document, do đó callback sau convert có thể được gọi cho từng entity được ánh xạ. Không nên đặt trong callback một truy vấn bổ sung hoặc thao tác I/O nặng mà không đánh giá chi phí.

## 3. Bốn entity callback thường dùng

Spring Data Elasticsearch cung cấp các callback chính sau:

| Callback | Thời điểm | Đầu vào quan trọng | Mục đích |
|---|---|---|---|
| BeforeConvertCallback<T> | Trước khi entity được convert thành Document | Entity, IndexCoordinates | Chuẩn hóa và bổ sung dữ liệu trên entity |
| BeforeSaveCallback<T> | Sau khi convert, trước khi gửi document | Entity, Document, IndexCoordinates | Kiểm tra hoặc chỉnh document sắp được lưu |
| AfterSaveCallback<T> | Sau khi thao tác lưu hoàn tất | Entity, IndexCoordinates | Xử lý sau khi ghi |
| AfterConvertCallback<T> | Sau khi document được convert thành entity | Entity, Document, IndexCoordinates | Hoàn thiện entity sau khi đọc |

Các callback được tham số hóa theo kiểu entity. Ví dụ BeforeConvertCallback<Product> chỉ xử lý Product; callback có thể được đăng ký riêng cho từng loại tài liệu.

Các phương thức callback trả về entity. Hãy trả về object đã thay đổi hoặc object mới nếu dùng immutable model. Đừng quên trả về entity; callback không phải listener chỉ chạy side effect rồi bỏ qua kết quả.

## 4. BeforeConvertCallback: xử lý entity trước khi convert

BeforeConvertCallback chạy khi dữ liệu vẫn là object Java và trước khi Spring Data chuyển nó thành Document.

Ví dụ chuẩn hóa SKU và tên sản phẩm:

~~~java
import java.util.Locale;

import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class ProductBeforeConvertCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product entity,
            IndexCoordinates index) {

        if (entity.getSku() != null) {
            entity.setSku(
                    entity.getSku().trim().toUpperCase(Locale.ROOT)
            );
        }

        if (entity.getName() != null) {
            entity.setName(entity.getName().trim());
        }

        return entity;
    }
}
~~~

Trong ví dụ:

- SKU được trim khoảng trắng đầu/cuối.
- SKU được chuẩn hóa chữ hoa theo Locale.ROOT, tránh phụ thuộc locale của máy chủ.
- Tên sản phẩm được loại bỏ khoảng trắng thừa ở hai đầu.
- Entity được trả về để converter sử dụng.

Callback này phù hợp với những thay đổi thuộc mô hình entity và cần được phản ánh vào document được ghi.

### Khi nào không nên chuẩn hóa ở BeforeConvert?

Không phải mọi giá trị đều nên bị thay đổi tự động. Ví dụ:

- Tên hiển thị có thể cần giữ nguyên chữ hoa/thường do người dùng nhập.
- SKU có thể phân biệt chữ hoa/thường theo quy tắc nguồn.
- Nội dung cần lưu nguyên bản để phục vụ audit hoặc đối chiếu.
- Một giá trị đã được chuẩn hóa ở service hoặc domain layer có thể không cần chuẩn hóa lần nữa.

Nên xác định quy tắc chuẩn hóa ở một nơi có trách nhiệm rõ ràng. Nếu cùng một trường được sửa ở controller, service, callback và converter, rất khó biết giá trị cuối cùng đến từ đâu.

## 5. BeforeSaveCallback: xử lý Document trước khi ghi

BeforeSaveCallback chạy sau khi entity đã được chuyển thành Document, nhưng trước khi document được gửi tới Elasticsearch. Callback nhận cả entity và document nên có thể kiểm tra hoặc thay đổi cấu trúc dữ liệu được ghi.

Ví dụ bổ sung trường normalizedName vào document:

~~~java
import java.text.Normalizer;
import java.util.Locale;

import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.event.BeforeSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class ProductBeforeSaveCallback
        implements BeforeSaveCallback<Product> {

    @Override
    public Product onBeforeSave(
            Product entity,
            Document document,
            IndexCoordinates index) {

        if (entity.getName() != null) {
            String normalized = Normalizer
                    .normalize(entity.getName(), Normalizer.Form.NFD)
                    .replaceAll("\\p{M}+", "")
                    .toLowerCase(Locale.ROOT);

            document.put("normalizedName", normalized);
        }

        return entity;
    }
}
~~~

Trường normalizedName được thêm vào document gửi đi. Trong ví dụ, entity không được thay đổi; chỉ cấu trúc Document được bổ sung.

Điều này có thể hữu ích khi:

- Cần ghi một trường dẫn xuất.
- Cần thêm metadata không thuộc entity domain.
- Cần điều chỉnh representation trước khi gửi.
- Cần kiểm tra document sau khi converter đã ánh xạ annotation và custom conversion.

Nếu trường mới cần được truy vấn hoặc sắp xếp, mapping của index phải khai báo kiểu phù hợp. Thêm field vào Document không tự bảo đảm mapping đã được thiết lập đúng.

### Không dùng BeforeSave để thay thế domain logic

Nếu normalizedName là một phần dữ liệu nghiệp vụ quan trọng và được nhiều hệ thống sử dụng, cân nhắc đặt nó trong model hoặc service domain để có thể kiểm thử độc lập. BeforeSaveCallback phù hợp với logic gắn với quá trình persistence; nó không nên trở thành nơi chứa toàn bộ quy tắc nghiệp vụ của Product.

Ngoài ra, thay đổi Document ở callback không nhất thiết thay đổi entity được trả về cho caller. Nếu caller cần nhìn thấy trường dẫn xuất đó, hãy cập nhật model hoặc dùng DTO phù hợp.

## 6. AfterSaveCallback: xử lý sau khi lưu

AfterSaveCallback được gọi sau khi thao tác lưu hoàn tất. Callback nhận entity và index coordinates.

Ví dụ:

~~~java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.event.AfterSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class ProductAfterSaveCallback
        implements AfterSaveCallback<Product> {

    @Override
    public Product onAfterSave(
            Product entity,
            IndexCoordinates index) {

        // Chỉ thực hiện xử lý nhẹ, đồng bộ và có thể lặp an toàn.
        return entity;
    }
}
~~~

Một số use case có thể cân nhắc:

- Bổ sung thông tin tạm thời cho object trả về.
- Ghi nhận metric cục bộ.
- Chuẩn bị dữ liệu cho tầng gọi tiếp theo.
- Kiểm tra metadata sau khi lưu nếu API và entity có hỗ trợ.

Không nên dùng callback này để gửi email, gọi hệ thống thanh toán hoặc thực hiện side effect không thể lặp an toàn. Nếu Elasticsearch đã lưu thành công nhưng callback thất bại, caller có thể nhận exception dù document vẫn tồn tại.

Với side effect cần độ tin cậy cao, nên dùng event/outbox hoặc cơ chế phát sự kiện có thể retry độc lập. Không dựa vào AfterSaveCallback như một transaction coordinator giữa Elasticsearch và hệ thống khác.

## 7. AfterConvertCallback: hoàn thiện entity sau khi đọc

AfterConvertCallback chạy sau khi Spring Data đã tạo entity từ Document. Callback có thể sử dụng cả entity lẫn source document.

Ví dụ thêm nhãn hiển thị tạm thời vào Product:

~~~java
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.event.AfterConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class ProductAfterConvertCallback
        implements AfterConvertCallback<Product> {

    @Override
    public Product onAfterConvert(
            Product entity,
            Document document,
            IndexCoordinates index) {

        if (entity.getName() != null
                && entity.getName().isBlank()) {
            entity.setName("Unnamed product");
        }

        return entity;
    }
}
~~~

Ví dụ chỉ minh họa khả năng thay đổi entity sau khi convert. Trong thực tế, nếu dữ liệu thiếu tên là lỗi schema, nên phát hiện và xử lý rõ ràng thay vì âm thầm thay bằng giá trị giả.

Callback này không ghi lại thay đổi vào Elasticsearch. Nếu muốn sửa source đã lưu, cần thực hiện một thao tác update riêng. Cũng cần tránh truy vấn Elasticsearch bên trong callback vì một search trả về nhiều hit có thể tạo ra nhiều request phụ, gây N+1 query.

## 8. Đăng ký callback trong Spring application context

Các callback được đăng ký như Spring bean. Có thể dùng @Component như các ví dụ trên hoặc khai báo bằng @Bean trong cấu hình.

Ví dụ khai báo bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ProductCallbackConfiguration {

    @Bean
    ProductBeforeConvertCallback productBeforeConvertCallback() {
        return new ProductBeforeConvertCallback();
    }
}
~~~

Trong ví dụ này, class callback cần có constructor và dependency phù hợp nếu được khởi tạo thủ công. Không đăng ký đồng thời cùng một callback bằng cả @Component và @Bean, nếu không có thể tạo hai bean cùng xử lý một entity.

Spring Data sử dụng application context để tìm và gọi các entity callback tương ứng. Callback cần được component scan hoặc cấu hình bean trong context mà repository/template đang dùng.

Nếu callback có dependency như Clock, service chuẩn hóa hoặc cấu hình, hãy inject dependency qua constructor. Tránh tự tạo dependency bên trong callback vì sẽ khó kiểm thử và khó thay đổi cấu hình.

## 9. Thứ tự callback và @Order

Một ứng dụng có thể có nhiều callback cùng loại cho một entity. Ví dụ một callback chuẩn hóa SKU và một callback bổ sung trường phân loại. Khi thứ tự ảnh hưởng đến kết quả, hãy khai báo order rõ ràng.

~~~java
import org.springframework.core.annotation.Order;

@Component
@Order(10)
public class ProductSkuNormalizationCallback
        implements BeforeConvertCallback<Product> {
    // ...
}

@Component
@Order(20)
public class ProductNameNormalizationCallback
        implements BeforeConvertCallback<Product> {
    // ...
}
~~~

Giá trị order nhỏ hơn được ưu tiên trước trong cơ chế sắp xếp theo order của Spring. Có thể dùng Ordered nếu muốn xác định thứ tự bằng code.

Không nên phụ thuộc vào thứ tự bean được phát hiện ngẫu nhiên. Nếu callback thứ hai giả định callback thứ nhất đã chạy, hãy biểu đạt quan hệ đó bằng order hoặc hợp nhất logic nếu chúng thực sự là một quy trình.

Nên tránh chia một thay đổi đơn giản thành quá nhiều callback nhỏ. Mỗi callback là một bước persistence riêng; quá nhiều bước làm luồng ghi khó theo dõi và tăng nguy cơ tương tác ngoài ý muốn.

## 10. Mapping events khác entity callbacks như thế nào?

Spring Data Elasticsearch còn phát ra **mapping events** trong quá trình chuyển đổi và lưu dữ liệu. Event thường được lắng nghe bằng @EventListener hoặc cơ chế listener của Spring.

Các event thường gặp:

| Event | Mốc xử lý |
|---|---|
| BeforeConvertEvent | Trước khi entity được convert thành Document |
| BeforeSaveEvent | Trước khi Document được gửi tới Elasticsearch |
| AfterSaveEvent | Sau khi thao tác lưu hoàn tất |
| AfterLoadEvent | Sau khi Document được tải từ Elasticsearch |
| AfterConvertEvent | Sau khi Document được convert thành entity |

Khác biệt khái quát:

| Entity callback | Mapping event |
|---|---|
| API có kiểu generic theo entity | Application event được phát trong Spring context |
| Thường trả về entity đã xử lý | Listener nhận event và xử lý side effect |
| Phù hợp thay đổi entity/document trong lifecycle | Phù hợp quan sát, ghi nhận hoặc phản ứng với mốc xử lý |
| Được gọi trong luồng persistence tương ứng | Có thể được xử lý bởi listener đồng bộ hoặc bất đồng bộ |
| Có thể dùng thứ tự callback qua @Order/Ordered | Listener có cơ chế order riêng của Spring |

Không nên dùng event listener để thay thế callback nếu cần chắc chắn một thay đổi entity được áp dụng trước khi converter hoặc request sử dụng dữ liệu. Event listener bất đồng bộ càng không phù hợp với việc sửa dữ liệu cần có ngay trong request hiện tại.

## 11. Lắng nghe BeforeSaveEvent

Ví dụ listener nhận event trước khi document được lưu:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.data.elasticsearch.core.event.BeforeSaveEvent;
import org.springframework.stereotype.Component;

@Component
public class ProductMappingEventListener {

    @EventListener
    public void onBeforeSave(BeforeSaveEvent<Product> event) {
        Product product = event.getSource();

        // Quan sát entity và document sắp được ghi.
        // Dùng cho logging/metrics nhẹ; tránh sửa dữ liệu
        // nếu logic cần bảo đảm thứ tự với converter.
    }
}
~~~

BeforeSaveEvent cung cấp entity nguồn, document và index coordinates theo API Spring Data Elasticsearch. Tùy phiên bản, có thể lấy document từ getter tương ứng của event.

Listener có thể ghi log, metric hoặc phát tín hiệu quan sát. Nếu cần sửa entity trước khi convert, hãy dùng BeforeConvertCallback; nếu cần sửa Document trước khi gửi, dùng BeforeSaveCallback.

Không nên thực hiện truy vấn Elasticsearch đồng bộ bên trong listener trước save. Nó có thể làm tăng latency và gây vòng lặp nếu listener kích hoạt thêm một thao tác persistence khác.

## 12. Event listener và xử lý bất đồng bộ

Spring application event mặc định thường được xử lý đồng bộ trong thread phát event, trừ khi listener được cấu hình bất đồng bộ. Nếu dùng @Async, listener có thể chạy sau khi thao tác persistence tiếp tục hoặc hoàn tất.

Điều này có ảnh hưởng đến cách đặt logic:

- Validation bắt buộc phải thành công trước khi ghi: dùng validation/service hoặc callback đồng bộ.
- Chuẩn hóa dữ liệu trước khi convert: dùng BeforeConvertCallback.
- Chỉnh document trước khi gửi: dùng BeforeSaveCallback.
- Ghi metric hoặc thông tin quan sát: event listener có thể phù hợp.
- Gửi thông báo sau khi lưu: dùng event/outbox và xử lý retry độc lập.

Một listener bất đồng bộ không thể bảo đảm việc thay đổi dữ liệu sẽ được phản ánh vào document vừa gửi. Đừng đặt việc gán createdAt, chuẩn hóa SKU hoặc bổ sung trường bắt buộc trong listener @Async.

Nếu listener thực hiện side effect, hãy thiết kế để xử lý lặp an toàn và ghi nhận lỗi. Event được phát trong process không tự bảo đảm delivery bền vững sau khi ứng dụng crash.

## 13. Auditing là gì?

**Auditing** tự động ghi nhận ai tạo hoặc sửa một entity và thời điểm tương ứng. Spring Data hỗ trợ các annotation:

- @CreatedDate: thời điểm tạo.
- @LastModifiedDate: thời điểm sửa gần nhất.
- @CreatedBy: người tạo.
- @LastModifiedBy: người sửa gần nhất.

Auditing thường được tích hợp với lifecycle callback nội bộ của Spring Data. Nhờ đó, các trường audit được cập nhật ở mốc trước khi entity được convert và lưu.

Ví dụ Product:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String sku;
    private String name;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant lastModifiedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String lastModifiedBy;

    // Constructors, getters và setters.
}
~~~

Dùng Instant để lưu mốc thời gian tuyệt đối, thường thuận tiện cho dữ liệu hệ thống và trao đổi giữa các máy chủ. Nếu ứng dụng dùng kiểu thời gian khác, cần bảo đảm converter và mapping tương thích.

Auditing không tự tạo một bảng lịch sử mọi thay đổi. Nó thường duy trì các trường audit hiện tại trên entity. Nếu cần lịch sử đầy đủ, cần thiết kế event log hoặc audit index riêng.

## 14. Bật Elasticsearch auditing

Có thể bật auditing bằng @EnableElasticsearchAuditing trong cấu hình:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.config.EnableElasticsearchAuditing;

@Configuration
@EnableElasticsearchAuditing
public class ElasticsearchAuditingConfiguration {
}
~~~

Khi cần ghi nhận người tạo/người sửa, cung cấp bean AuditorAware<T>:

~~~java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;

@Configuration
@EnableElasticsearchAuditing
public class ElasticsearchAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> Optional.of("system");
    }
}
~~~

Ví dụ trả về system chỉ phù hợp với tác vụ chạy dưới danh tính hệ thống. Trong ứng dụng thực tế, nên lấy user hiện tại từ security context hoặc context của tác vụ nền.

Nếu không có auditor phù hợp, có thể trả Optional.empty(). Các trường createdBy và lastModifiedBy khi đó có thể không được gán bởi auditing.

Không hard-code một user chung cho mọi request nếu cần truy vết người dùng. Cũng không lấy tên người dùng từ một header tùy ý mà chưa xác thực; auditor phải đến từ nguồn danh tính đáng tin cậy.

## 15. AuditorAware lấy người dùng hiện tại

Một ví dụ đơn giản với Spring Security:

~~~java
import java.util.Optional;

import org.springframework.data.domain.AuditorAware;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component
public class SecurityAuditorAware implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || "anonymousUser".equals(authentication.getPrincipal())) {
            return Optional.empty();
        }

        return Optional.of(authentication.getName());
    }
}
~~~

Bean này cho phép auditing lấy tên principal đã xác thực. Cần kiểm tra cách ứng dụng quản lý anonymous authentication và principal type; trong hệ thống thực tế principal có thể là một object riêng chứ không phải String.

Với scheduled job hoặc message consumer, không có HTTP security context. Hãy thiết lập danh tính hệ thống rõ ràng trong execution context của job hoặc dùng auditor provider phù hợp với loại tác vụ.

Nếu chạy reactive application, không nên giả định SecurityContextHolder dạng ThreadLocal sẽ có context đúng trong mọi thread. Cần dùng cơ chế context propagation tương ứng với reactive stack và auditing API của phiên bản đang dùng.

## 16. CreatedDate và LastModifiedDate hoạt động ra sao?

Auditing phân biệt thời điểm tạo với thời điểm sửa:

- @CreatedDate được gán khi entity được tạo lần đầu và thường được giữ lại trong các lần cập nhật tiếp theo.
- @LastModifiedDate được cập nhật khi entity được lưu/sửa.
- @CreatedBy ghi người tạo.
- @LastModifiedBy ghi người sửa gần nhất.

Ví dụ lần đầu lưu Product:

~~~json
{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "createdAt": "2026-11-13T08:00:00Z",
  "lastModifiedAt": "2026-11-13T08:00:00Z",
  "createdBy": "alice",
  "lastModifiedBy": "alice"
}
~~~

Sau khi Alice hoặc một người dùng khác sửa giá:

~~~json
{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "price": 94.5,
  "createdAt": "2026-11-13T08:00:00Z",
  "lastModifiedAt": "2026-11-13T09:30:00Z",
  "createdBy": "alice",
  "lastModifiedBy": "bob"
}
~~~

createdAt và createdBy vẫn phản ánh lần tạo ban đầu; lastModifiedAt và lastModifiedBy phản ánh lần sửa gần nhất.

Hành vi chính xác còn phụ thuộc entity metadata và cách ứng dụng ghi dữ liệu. Nếu service tự gán lại createdAt trước mỗi lần save, auditing không thể tự sửa được ý nghĩa nghiệp vụ đã bị code ứng dụng thay đổi.

## 17. Tùy chỉnh nguồn thời gian

Mặc định auditing lấy thời gian hiện tại từ cơ chế date/time provider của Spring Data. Khi cần kiểm thử ổn định hoặc đồng bộ thời gian theo một nguồn chung, có thể cung cấp DateTimeProvider phù hợp.

Ví dụ dùng Clock:

~~~java
import java.time.Clock;
import java.time.temporal.TemporalAccessor;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;

@Configuration
public class AuditTimeConfiguration {

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider dateTimeProvider(Clock auditClock) {
        return () -> Optional.<TemporalAccessor>of(
                auditClock.instant()
        );
    }
}
~~~

Để auditing sử dụng provider tùy chỉnh, tham chiếu bean qua thuộc tính dateTimeProviderRef của annotation EnableElasticsearchAuditing nếu phiên bản đang dùng hỗ trợ:

~~~java
@EnableElasticsearchAuditing(
        dateTimeProviderRef = "dateTimeProvider"
)
~~~

Cách này giúp test có thể dùng Clock.fixed(...) để xác định chính xác thời gian tạo/sửa. Trong production, Clock.systemUTC() tránh phụ thuộc timezone cục bộ của máy chủ.

Hãy kiểm tra tên thuộc tính và API trong phiên bản Spring Data Elasticsearch cụ thể. Không cần tùy chỉnh DateTimeProvider nếu ứng dụng không có yêu cầu về nguồn thời gian hoặc khả năng kiểm thử.

## 18. Callback, auditing và validation có vai trò khác nhau

Các cơ chế này có thể cùng tham gia một luồng ghi, nhưng nên giữ đúng trách nhiệm:

| Cơ chế | Trách nhiệm phù hợp |
|---|---|
| Domain/service validation | Kiểm tra quy tắc nghiệp vụ trước khi persistence |
| BeforeConvertCallback | Chuẩn hóa hoặc bổ sung entity trước convert |
| BeforeSaveCallback | Điều chỉnh Document trước khi gửi |
| Auditing | Gán ngày tạo/sửa và người tạo/sửa |
| Mapping event listener | Quan sát mốc xử lý hoặc phát tín hiệu |
| AfterSaveCallback | Xử lý đồng bộ sau khi ghi |
| AfterConvertCallback | Hoàn thiện entity sau khi đọc |

Ví dụ:

- SKU rỗng: validation nên từ chối trước khi ghi.
- SKU cần uppercase theo quy ước lưu trữ: BeforeConvertCallback có thể chuẩn hóa.
- createdAt cần tự động gán: auditing phù hợp.
- Document cần thêm trường schemaVersion: BeforeSaveCallback có thể phù hợp nếu đó là metadata persistence.
- Ghi metric sau khi lưu: event listener hoặc callback sau lưu tùy yêu cầu.
- Tên hiển thị cần tạo DTO theo locale: thường nên thực hiện ở service/presentation layer, không nhất thiết đặt trong AfterConvertCallback.

Không nên biến callback thành nơi thay thế toàn bộ service layer. Callback nên xử lý các quy tắc gắn với lifecycle persistence và áp dụng nhất quán cho các đường ghi/đọc sử dụng Spring Data.

## 19. Các API nào kích hoạt callback?

Thông thường, khi sử dụng Spring Data repository hoặc các phương thức mapping của ElasticsearchOperations, entity lifecycle callbacks được tích hợp vào luồng xử lý của template.

Ví dụ:

~~~java
productRepository.save(product);
~~~

Hoặc:

~~~java
operations.save(product, IndexCoordinates.of("products"));
~~~

Các thao tác này đi qua Spring Data mapping layer, nơi entity được convert và persistence được điều phối.

Tuy nhiên, không nên giả định mọi API có tên save, bulk hoặc update đều gọi cùng một bộ callback:

- Repository và ElasticsearchOperations.save là đường ghi entity thông thường.
- UpdateQuery có thể gửi partial document hoặc script mà không có một entity đầy đủ để chạy toàn bộ lifecycle như save.
- Bulk APIs có thể dùng IndexQuery, UpdateQuery hoặc object entity; hành vi callback phụ thuộc overload và phiên bản.
- Gọi trực tiếp ElasticsearchClient.index(...), bulk(...) hoặc REST API không đi qua entity callback của Spring Data.
- Tự gọi converter trực tiếp cũng không tự động đồng nghĩa toàn bộ callback lifecycle được thực thi.

Nếu callback hoặc auditing là yêu cầu bắt buộc, hãy kiểm thử đúng đường ghi thực tế mà ứng dụng sử dụng, đặc biệt với bulk import và Update API.

## 20. Callback không tự chạy khi dùng Elasticsearch Java API Client trực tiếp

Ví dụ gọi trực tiếp client:

~~~java
elasticsearchClient.index(
        request -> request
                .index("products")
                .id(product.getId())
                .document(product),
        Product.class
);
~~~

Đây là lời gọi Java API Client. Nó không đi qua repository/template lifecycle của Spring Data, vì vậy không nên kỳ vọng BeforeConvertCallback, BeforeSaveCallback hoặc auditing callback tự chạy.

Nếu ứng dụng có cả hai đường ghi:

- Repository/Operations cho thao tác entity thông thường.
- ElasticsearchClient trực tiếp cho bulk hoặc tính năng cấp thấp.

thì các quy tắc cần áp dụng nhất quán phải được đặt ở một tầng dùng chung hoặc gọi tường minh trước khi gửi request. Ví dụ, có thể gọi một service chuẩn hóa/validation dùng chung, hoặc tạo document đã được chuẩn bị trước khi gửi qua client.

Không nên sao chép logic callback vào nhiều producer. Khi quy tắc thay đổi, các bản sao có thể lệch nhau và tạo dữ liệu không đồng nhất.

## 21. Callback trong thao tác bulk

Bulk ingestion thường xử lý nhiều entity trong một request để giảm round-trip. Đây là nơi cần đặc biệt chú ý đến callback và auditing.

Tùy phiên bản và API được gọi, bulk operation có thể xử lý entity thông qua converter hoặc gửi các query/document đã được dựng sẵn. Vì vậy, không nên mặc định mọi callback được gọi đúng một lần cho mỗi entity trong mọi bulk path.

Trước khi dựa vào callback để gán audit field hoặc chuẩn hóa dữ liệu trong bulk:

1. Xác định chính xác phương thức bulk đang sử dụng.
2. Kiểm tra implementation/API của phiên bản Spring Data Elasticsearch.
3. Viết integration test với callback có thể quan sát được.
4. Xác nhận số lần callback chạy và giá trị trong document thực tế.
5. Kiểm tra bulk item failure không làm ứng dụng đánh dấu toàn bộ batch thành công.

Nếu đường bulk không gọi callback theo mong muốn, chuẩn hóa entity trước khi dựng IndexQuery hoặc dùng một pipeline ingest chung. Không để auditing phụ thuộc vào hành vi chưa được xác nhận.

## 22. Callback và thao tác UpdateQuery

UpdateQuery thường đại diện cho partial document hoặc script, không phải một entity hoàn chỉnh. Ví dụ:

~~~java
Document partial = Document.parse("""
{
  "price": 94.5
}
""");

UpdateQuery update = UpdateQuery.builder("p-1001")
        .withDocument(partial)
        .build();

operations.update(
        update,
        IndexCoordinates.of("products")
);
~~~

Ở đây Spring Data gửi một partial update. Không có đầy đủ Product để suy ra các giá trị LastModifiedDate hoặc LastModifiedBy nếu ứng dụng không đưa chúng vào payload.

Nếu cần audit khi dùng UpdateQuery, hãy bổ sung các trường audit vào partial document hoặc script theo quy tắc đã định. Ví dụ:

~~~json
{
  "doc": {
    "price": 94.5,
    "lastModifiedAt": "2026-11-13T09:30:00Z",
    "lastModifiedBy": "bob"
  }
}
~~~

Đây là payload minh họa; thời gian và user phải lấy từ nguồn đáng tin cậy trong ứng dụng. Không giả định auditing entity tự động xử lý mọi partial update chỉ vì request được gửi qua ElasticsearchOperations.

Nếu có nhiều đường ghi khác nhau, hãy tạo service hoặc helper thống nhất để gán audit metadata trước khi dựng UpdateQuery, Bulk update hoặc Java API Client request.

## 23. Thứ tự xử lý và tác dụng phụ

Khi thiết kế callback, hãy xác định dữ liệu nào đã tồn tại ở mỗi mốc:

| Mốc | Có entity? | Có Document? | Đã ghi Elasticsearch? |
|---|---:|---:|---:|
| BeforeConvert | Có | Chưa | Chưa |
| Sau convert | Có | Có | Chưa |
| BeforeSave | Có | Có | Chưa |
| AfterSave | Có | Tùy API | Có, nếu request thành công |
| AfterLoadEvent | Document nguồn | Có | Đã đọc từ Elasticsearch |
| AfterConvert | Có | Có | Đã đọc và convert |

Một số nguyên tắc:

- Không đọc Document trong BeforeConvertCallback vì document chưa được tạo.
- Không giả định BeforeSaveCallback có thể thay đổi entity và làm thay đổi Document đã convert; hãy sửa Document nếu mục tiêu là dữ liệu gửi đi.
- Không giả định AfterSaveCallback có thể rollback thao tác đã ghi.
- Không ghi lại Elasticsearch từ AfterConvertCallback nếu không có cơ chế ngăn vòng lặp.
- Không thực hiện side effect đắt tiền cho từng hit khi đọc danh sách lớn.

Callback nên ngắn, dễ dự đoán và có thể kiểm thử. Nếu cần gọi dịch vụ bên ngoài hoặc chạy công việc lâu, chuyển sang tầng xử lý phù hợp.

## 24. Callback với entity bất biến

Entity không nhất thiết phải dùng setter. Nếu dùng immutable object, callback có thể trả về một instance mới chứa các giá trị đã chuẩn hóa.

Ví dụ:

~~~java
public record Product(
        String id,
        String sku,
        String name,
        Instant createdAt,
        Instant lastModifiedAt
) {
    Product withSku(String normalizedSku) {
        return new Product(
                id,
                normalizedSku,
                name,
                createdAt,
                lastModifiedAt
        );
    }
}
~~~

Callback:

~~~java
@Component
public class ProductBeforeConvertCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product entity,
            IndexCoordinates index) {

        if (entity.sku() == null) {
            return entity;
        }

        String normalized = entity.sku()
                .trim()
                .toUpperCase(Locale.ROOT);

        return entity.withSku(normalized);
    }
}
~~~

Ví dụ này minh họa ý tưởng trả về instance mới. Để Spring Data tạo entity immutable khi đọc, cần cấu hình constructor/property mapping phù hợp với metadata của entity, chẳng hạn constructor được nhận diện hoặc @PersistenceCreator khi có nhiều constructor.

Nếu callback trả về object mới, hãy bảo đảm ID và các trường cần thiết được giữ lại. Không trả về object chỉ chứa một phần thuộc tính nếu converter hoặc thao tác sau đó cần các trường còn lại.

## 25. Tránh đặt logic nặng trong callback

Callback có thể được gọi thường xuyên:

- Mỗi lần save entity.
- Mỗi entity được convert trong kết quả search.
- Trong các luồng bulk tùy API.
- Trong tác vụ đồng bộ hoặc import chạy với số lượng lớn.

Nếu callback gọi một dịch vụ HTTP hoặc truy vấn Elasticsearch khác cho mỗi entity, latency và tải hệ thống có thể tăng nhanh.

Ví dụ không nên làm:

~~~java
@Override
public Product onBeforeConvert(
        Product entity,
        IndexCoordinates index) {

    PricingInfo info = pricingClient.fetch(entity.getSku());
    entity.setPrice(info.price());

    return entity;
}
~~~

Callback này tạo network call trong mỗi lần lưu. Khi import 10.000 sản phẩm, ứng dụng có thể tạo 10.000 request phụ và làm luồng ghi khó dự đoán.

Thay vào đó:

- Lấy dữ liệu phụ ở service trước khi gọi repository.
- Batch-load dữ liệu cần thiết.
- Truyền giá trị đã tính vào entity.
- Giữ callback cho logic mapping/persistence nhẹ.
- Nếu cần đồng bộ bên ngoài sau ghi, dùng event/outbox.

## 26. Kiểm thử callback

Có thể kiểm thử callback trực tiếp bằng unit test mà không cần Elasticsearch:

~~~java
@Test
void normalizesSkuBeforeConvert() {
    Product product = new Product();
    product.setSku("  kb-1001 ");

    ProductBeforeConvertCallback callback =
            new ProductBeforeConvertCallback();

    Product result = callback.onBeforeConvert(
            product,
            IndexCoordinates.of("products")
    );

    assertEquals("KB-1001", result.getSku());
}
~~~

Với callback thay đổi Document:

~~~java
@Test
void addsNormalizedNameToDocument() {
    Product product = new Product();
    product.setName("Mechanical Keyboard");

    Document document = Document.create();

    ProductBeforeSaveCallback callback =
            new ProductBeforeSaveCallback();

    callback.onBeforeSave(
            product,
            document,
            IndexCoordinates.of("products")
    );

    assertNotNull(document.get("normalizedName"));
}
~~~

Unit test kiểm tra logic callback riêng lẻ. Nó không xác nhận callback được Spring tự động phát hiện hoặc được gọi đúng thứ tự trong repository/template.

### Integration test cho lifecycle

Dùng Elasticsearch tương thích và cấu hình application context thật để kiểm tra:

1. Lưu Product qua repository.
2. Xác nhận BeforeConvert đã chuẩn hóa SKU.
3. Xác nhận BeforeSave đã bổ sung trường vào source.
4. Đọc Product qua repository.
5. Xác nhận AfterConvert được gọi.
6. Xác nhận auditing đã gán createdAt/lastModifiedAt.
7. Cập nhật Product và xác nhận createdAt không bị ghi đè ngoài ý muốn.
8. Gọi đường bulk hoặc UpdateQuery thực tế và kiểm tra callback/auditing có chạy theo yêu cầu không.

Có thể dùng một test callback ghi lại thứ tự vào list hoặc test spy để quan sát. Không chỉ kiểm tra object trả về; hãy đọc source từ Elasticsearch khi cần xác nhận document cuối cùng.

## 27. Lỗi thường gặp khi dùng entity callback và auditing

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Callback không được gọi | Bean không nằm trong application context hoặc đường ghi bypass template | Kiểm tra component scan và API đang dùng |
| Callback chạy hai lần | Đăng ký bean trùng hoặc gọi save lồng nhau | Kiểm tra cấu hình và side effect |
| SKU được chuẩn hóa nhưng source không đổi | Callback trả object khác nhưng caller bỏ qua kết quả, hoặc xử lý ở sai mốc | Trả về entity và kiểm tra luồng converter |
| Document có field mới nhưng entity trả về không có | BeforeSave chỉ sửa Document | Bổ sung model/DTO nếu caller cần field |
| Auditing date luôn null | Chưa bật auditing hoặc entity metadata chưa nhận annotation | Kiểm tra @EnableElasticsearchAuditing và mapping |
| createdBy/lastModifiedBy rỗng | Không có AuditorAware hoặc context không có user | Cấu hình AuditorAware phù hợp |
| User audit luôn là system | Auditor bị hard-code | Lấy principal thực tế hoặc context của job |
| UpdateQuery không cập nhật lastModifiedDate | Partial update không đi qua auditing entity callback | Bổ sung audit fields trong UpdateQuery/script |
| Bulk không cập nhật audit như mong muốn | Bulk path có semantics callback khác | Kiểm thử overload thực tế và chuẩn hóa trước bulk |
| AfterSave ném lỗi nhưng document vẫn tồn tại | Exception xảy ra sau khi ghi | Xử lý callback sau lưu như bước riêng, có retry/idempotency |
| Search chậm sau khi thêm AfterConvert | Callback thực hiện I/O cho từng hit | Loại bỏ N+1 và giữ callback nhẹ |
| Event listener sửa dữ liệu quá muộn | Listener bất đồng bộ hoặc dùng sai lifecycle phase | Dùng callback đồng bộ ở mốc phù hợp |

## 28. Quy trình chọn đúng mốc xử lý

Khi cần thêm logic vào vòng đời entity, hãy xác định dữ liệu cần thay đổi và thời điểm nó phải có hiệu lực:

1. **Cần sửa object trước khi chuyển thành JSON?** Dùng BeforeConvertCallback.
2. **Cần chỉnh cấu trúc Document sau converter?** Dùng BeforeSaveCallback.
3. **Cần xử lý sau khi request ghi thành công?** Dùng AfterSaveCallback hoặc event tùy yêu cầu.
4. **Cần thay đổi object vừa đọc xong?** Dùng AfterConvertCallback.
5. **Cần quan sát sự kiện đọc/ghi hoặc phát tín hiệu?** Dùng mapping event listener.
6. **Cần ghi created/modified date và user?** Bật auditing.
7. **Cần validation nghiệp vụ?** Đặt ở domain/service layer trước persistence.
8. **Cần xử lý side effect bền vững sau ghi?** Dùng outbox hoặc cơ chế event có retry.
9. **Đang dùng UpdateQuery, bulk hoặc Java API Client?** Kiểm tra lifecycle của chính API đó; không giả định callback/auditing tự động chạy.
10. **Cần thay đổi thứ tự nhiều callback?** Dùng @Order hoặc Ordered.

Một callback được đặt đúng mốc sẽ giúp logic persistence nhất quán. Đặt sai mốc có thể khiến dữ liệu không được ghi, thay đổi không xuất hiện trong object trả về hoặc side effect xảy ra sau khi document đã được lưu.

## 29. Nguyên tắc thiết kế callback và auditing

- Dùng BeforeConvertCallback để chuẩn hóa entity trước khi converter chạy.
- Dùng BeforeSaveCallback khi cần chỉnh Document đã được tạo.
- Dùng AfterSaveCallback cho xử lý nhẹ sau thao tác ghi.
- Dùng AfterConvertCallback để hoàn thiện entity sau khi đọc.
- Dùng mapping events để quan sát các mốc lifecycle và phát tín hiệu.
- Bật auditing khi cần created/modified date hoặc user.
- Cung cấp AuditorAware từ nguồn danh tính đáng tin cậy.
- Giữ callback ngắn, xác định và tránh network I/O cho từng entity.
- Khai báo thứ tự bằng @Order khi nhiều callback phụ thuộc nhau.
- Không giả định callback được gọi qua Java API Client trực tiếp.
- Kiểm thử riêng repository, Operations, bulk và UpdateQuery path.
- Không coi AfterSave exception là rollback của thao tác đã ghi.
- Dùng outbox hoặc cơ chế delivery bền vững cho side effect quan trọng.
- Giữ domain validation ở tầng nghiệp vụ, không dồn mọi quy tắc vào callback.

Entity callback cung cấp các điểm mở rộng rõ ràng trong vòng đời persistence của Spring Data Elasticsearch. BeforeConvertCallback tác động lên entity trước khi chuyển đổi; BeforeSaveCallback tác động lên Document trước khi ghi; AfterSaveCallback chạy sau khi lưu; AfterConvertCallback chạy sau khi đọc và ánh xạ. Mapping events phù hợp để quan sát các mốc xử lý, còn auditing quản lý các trường ngày tạo, ngày sửa và người thực hiện. Khi đặt đúng logic vào đúng giai đoạn và kiểm tra riêng từng đường ghi như repository, bulk, UpdateQuery hay Java API Client, ứng dụng sẽ giữ được dữ liệu nhất quán và tránh những side effect khó kiểm soát.
