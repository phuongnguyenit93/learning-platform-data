# Nhận tham chiếu tài nguyên bằng AggregateReference khi phiên bản hỗ trợ

## Mục tiêu

Khi một API nhận dữ liệu có liên kết tới resource khác, client thường gửi URI của resource liên quan thay vì gửi toàn bộ object lồng nhau. Ví dụ, khi tạo Scanner, client có thể gửi URI của Producer đã được Spring Data REST export.

Spring Data REST cung cấp abstraction `org.springframework.data.rest.core.AggregateReference<T, ID>` để custom controller nhận một tham chiếu URI và giải quyết nó thành identifier hoặc aggregate. Tính năng dùng kiểu tham số này có từ Spring Data REST 4.1.

Cần phân biệt abstraction này với `org.springframework.data.jdbc.core.mapping.AggregateReference<T, ID>` của Spring Data JDBC. Hai kiểu có cùng tên nhưng khác package và mục đích:

- Spring Data REST AggregateReference biểu diễn một URI HTTP trỏ đến aggregate được export.
- Spring Data JDBC AggregateReference bọc identifier của một aggregate khác trong domain model để Spring Data JDBC ánh xạ quan hệ giữa các aggregate.

Bài này trình bày cách nhận URI reference trong custom controller, cách dùng URI trong request body DTO, cách xử lý identifier và aggregate, cùng những giới hạn tương thích và kiểm soát quyền truy cập.

## 1. Vì sao dùng URI để tham chiếu resource?

Giả sử API có hai aggregate độc lập:

- Producer là aggregate quản lý thông tin nhà sản xuất.
- Scanner là aggregate lưu cấu hình quét và tham chiếu đến Producer.

Client tạo Scanner cần chỉ ra Producer đã tồn tại. Thay vì gửi toàn bộ Producer object, client gửi URI:

    {
      "name": "nightly-scanner",
      "producer": "http://localhost:8080/producers/42"
    }

URI thể hiện danh tính resource mà server đã công bố. Cách này có một số lợi ích:

- Client không gửi lại toàn bộ dữ liệu của aggregate liên quan.
- API giữ ranh giới giữa các aggregate.
- Server có thể giải quyết URI thành identifier hoặc object theo mapping của Spring Data REST.
- URI theo hypermedia cho phép client lấy link từ response trước đó thay vì tự xây dựng đường dẫn.

URI không phải bằng chứng rằng caller có quyền sử dụng resource. Sau khi giải quyết reference, ứng dụng vẫn phải kiểm tra authorization và quy tắc nghiệp vụ.

## 2. Phân biệt hai AggregateReference cùng tên

Hai kiểu sau không thể thay thế trực tiếp cho nhau:

| Kiểu | Package | Mục đích |
|---|---|---|
| Spring Data REST AggregateReference | `org.springframework.data.rest.core.AggregateReference` | Nhận URI resource trong custom REST handler và resolve ID/aggregate |
| Spring Data JDBC AggregateReference | `org.springframework.data.jdbc.core.mapping.AggregateReference` | Lưu một ID tham chiếu tới aggregate khác trong mô hình Spring Data JDBC |

Khi làm việc với custom controller của Spring Data REST, import:

    import org.springframework.data.rest.core.AggregateReference;

Khi mô hình hóa thuộc tính trong entity Spring Data JDBC, import:

    import org.springframework.data.jdbc.core.mapping.AggregateReference;

Đừng chọn import chỉ dựa trên tên class. Hãy xác định đang xử lý URI HTTP ở tầng REST hay identifier ở tầng persistence.

## 3. AggregateReference trong Spring Data REST

Spring Data REST 4.1 bổ sung `AggregateReference<T, ID>` trong package `org.springframework.data.rest.core`. Kiểu này đại diện cho một reference được tạo từ URI theo scheme item resource mà Spring Data REST export.

Reference có thể được giải quyết thành:

- URI nguồn thông qua `getUri()`.
- Identifier của aggregate thông qua `resolveId()`.
- Aggregate đầy đủ thông qua `resolveAggregate()`.
- Identifier bắt buộc thông qua `resolveRequiredId()`.
- Aggregate bắt buộc thông qua `resolveRequiredAggregate()`.

Hai phương thức có chữ Required phù hợp khi handler không thể tiếp tục nếu URI không giải quyết được thành giá trị. Các phương thức không Required có thể trả về null theo API contract.

Ví dụ:

    import org.springframework.data.rest.core.AggregateReference;

    AggregateReference<Producer, Long> producerReference;

    Long producerId = producerReference.resolveRequiredId();

    Producer producer = producerReference.resolveRequiredAggregate();

Trong đó:

- `Producer` là kiểu aggregate được tham chiếu.
- `Long` là kiểu identifier của Producer.
- Giá trị reference đầu vào là URI resource, không phải object JSON tùy ý.

## 4. Nhận reference trong @RepositoryRestController

Tài liệu Spring Data REST hướng dẫn khai báo `AggregateReference` làm kiểu của handler method parameter. Với GET, URI reference được truyền qua request parameter.

Ví dụ controller:

    import org.springframework.data.rest.core.AggregateReference;
    import org.springframework.data.rest.webmvc.RepositoryRestController;
    import org.springframework.web.bind.annotation.GetMapping;
    import org.springframework.web.bind.annotation.RequestParam;

    @RepositoryRestController
    class ScannerController {

        @GetMapping("/scanners")
        ResponseEntity<?> getScanners(
                @RequestParam
                AggregateReference<Producer, Long> producer) {

            Long producerId = producer.resolveRequiredId();

            Producer resolvedProducer =
                producer.resolveRequiredAggregate();

            // Use producerId or resolvedProducer in application logic.
            return ResponseEntity.ok(
                scannerService.findByProducer(producerId)
            );
        }
    }

Ví dụ trên tập trung vào cách bind reference. Tên repository, service, kiểu trả về và cách tạo response cần được thay bằng domain model thực tế.

Client truyền URI của Producer trong query parameter:

    curl --get       --data-urlencode "producer=http://localhost:8080/producers/42"       -H "Accept: application/hal+json"       http://localhost:8080/scanners

Dùng `--data-urlencode` để mã hóa URI đúng cách trong query string. Trong ứng dụng thực tế, client nên lấy URI từ HAL link của Producer thay vì hard-code đường dẫn.

### 4.1. Chọn resolve ID hay resolve aggregate

Dùng `resolveRequiredId()` khi logic chỉ cần identifier:

    Long producerId = producer.resolveRequiredId();

Ví dụ service có query method chỉ cần producer ID:

    return scannerRepository.findAllByProducerId(producerId);

Dùng `resolveRequiredAggregate()` khi logic cần object Producer:

    Producer producerEntity =
        producer.resolveRequiredAggregate();

Ví dụ service cần đọc trạng thái hoặc thuộc tính của Producer trước khi tạo Scanner.

Không resolve aggregate đầy đủ nếu chỉ cần ID. Việc tải aggregate có thể tạo thêm truy vấn và làm tăng chi phí xử lý. Ngược lại, nếu cần xác nhận trạng thái nghiệp vụ của Producer, chỉ lấy ID rồi lưu association mà không kiểm tra trạng thái có thể không đủ.

### 4.2. URI phải theo resource mapping của Spring Data REST

Reference được giải quyết dựa trên URI scheme mà Spring Data REST dùng để export item resource. Ví dụ:

    http://localhost:8080/producers/42

Nếu repository có base path, custom item URI hoặc EntityLookup thay đổi cách nhận diện resource, client phải dùng đúng URI server công bố.

Không tự suy đoán URI từ tên class hoặc tên bảng. Dùng link trả về trong HAL:

    {
      "_links": {
        "producer": {
          "href": "http://localhost:8080/producers/42"
        }
      }
    }

Nếu URI không thuộc resource mapping có thể nhận diện, việc chuyển đổi reference có thể thất bại.

## 5. Tùy chỉnh cách trích identifier bằng withIdSource

Mặc định, Spring Data REST trích identifier từ URI theo quy ước item resource. Nếu API dùng URI có cấu trúc định danh tùy chỉnh, có thể dùng `withIdSource(...)` để cung cấp hàm trích giá trị từ `UriComponents`.

Ví dụ ý tưởng:

    AggregateReference<Producer, Long> reference =
        producer.withIdSource(uriComponents -> {
            // Extract the identifier from the URI structure
            // used by this application.
            return extractProducerId(uriComponents);
        });

    Long producerId = reference.resolveRequiredId();

Hàm extractor nhận `UriComponents` và trả về giá trị identifier mà Spring Data REST có thể chuyển đổi sang kiểu ID cần thiết.

Chỉ dùng tùy chỉnh này khi URI mapping của ứng dụng thực sự khác quy ước mặc định. Nếu URI item resource dùng ID thông thường, cơ chế mặc định đơn giản và ít lỗi hơn.

Không dùng extractor để bỏ qua kiểm tra resource mapping hoặc biến một chuỗi bất kỳ thành quyền truy cập resource. Identifier sau khi trích xuất vẫn phải được kiểm tra tồn tại và authorization.

## 6. AssociationAggregateReference và jMolecules

Nếu domain model sử dụng jMolecules, Spring Data REST cung cấp `AssociationAggregateReference<T, ID>`, một subinterface của `AggregateReference`. Nó có thể giải quyết reference thành kiểu `Association` của jMolecules.

Ví dụ:

    @GetMapping("/scanners")
    ResponseEntity<?> getScanners(
            @RequestParam
            AssociationAggregateReference<
                Producer,
                ProducerIdentifier
            > producer) {

        var association = producer.resolveRequiredAssociation();

        return ResponseEntity.ok(
            scannerService.findByProducer(association)
        );
    }

Kiểu này chỉ phù hợp khi aggregate và identifier tuân theo các abstraction jMolecules tương ứng. Nếu ứng dụng không dùng jMolecules, `AggregateReference<T, ID>` thông thường là lựa chọn phù hợp.

Không khai báo `AssociationAggregateReference` chỉ để thay thế một identifier đơn giản. Nó mang thêm semantics của jMolecules Association và yêu cầu đúng dependency/type model.

## 7. Nhận URI reference trong POST hoặc PUT request body

Với custom controller nhận POST hoặc PUT, body thường là JSON document có URI để biểu diễn tham chiếu tới resource khác.

Spring Data REST cung cấp Jackson support để deserialize URI của aggregate được quản lý bởi Spring Data REST thành aggregate instance trong DTO. `AggregateReferenceResolvingModule` được mô tả là module cho phép ánh xạ URI thành aggregate root trong payload mapping DTO.

Ví dụ DTO:

    public record CreateScannerRequest(
        String name,
        List<Producer> producers
    ) {
    }

Request body:

    {
      "name": "nightly-scanner",
      "producers": [
        "http://localhost:8080/producers/42",
        "http://localhost:8080/producers/43"
      ]
    }

Ví dụ controller:

    @BasePathAwareController
    class ScannerCommandController {

        @PostMapping("/scanners")
        ResponseEntity<?> create(
                @RequestBody CreateScannerRequest request) {

            Scanner scanner = scannerService.create(
                request.name(),
                request.producers()
            );

            return ResponseEntity.ok(scanner);
        }
    }

Trong môi trường có Spring Data REST Jackson integration phù hợp, các URI trong DTO có thể được resolve thành aggregate instance tương ứng. Khả năng này được giới thiệu trong dòng Spring Data REST 3.5 thông qua `AggregateReferenceResolvingModule`.

Nếu ứng dụng tự tạo hoặc thay thế ObjectMapper/message converter, hãy xác nhận module chuyển URI thành aggregate vẫn được đăng ký trong converter xử lý request. Một ObjectMapper riêng không tự động kế thừa mọi module và converter mà Spring Data REST cấu hình.

### 7.1. DTO body reference khác handler parameter AggregateReference

Hai cách nhận dữ liệu có vai trò khác nhau:

| Luồng | Cách khai báo | Dữ liệu client gửi |
|---|---|---|
| GET custom handler | `@RequestParam AggregateReference<T, ID>` | URI trong query parameter |
| POST/PUT DTO body | DTO có property kiểu aggregate hoặc collection aggregate, với SDR Jackson URI resolution | URI string trong JSON body |
| Domain model Spring Data JDBC | Property kiểu `org.springframework.data.jdbc.core.mapping.AggregateReference<T, ID>` | Identifier được map vào persistence model |

Không nhầm rằng `@RequestParam AggregateReference` tự động có nghĩa mọi JSON body property đều phải dùng cùng kiểu wrapper. Với DTO body, cơ chế URI deserialization của Jackson có thể bind URI thành aggregate property của DTO.

### 7.2. Chỉ nhận các aggregate được export và resolve được

URI trong DTO cần trỏ tới resource mà Spring Data REST có thể nhận diện. Nếu URI sai, repository không được export hoặc target không thể resolve, quá trình binding có thể thất bại.

Sau khi binding thành công, service vẫn cần kiểm tra các quy tắc nghiệp vụ như:

- Aggregate liên quan đang ở trạng thái cho phép sử dụng.
- Caller có quyền tham chiếu aggregate đó.
- Các aggregate thuộc cùng tenant nếu nghiệp vụ yêu cầu.
- Reference không tạo ra quan hệ vòng hoặc trạng thái không hợp lệ.
- Các quan hệ được phép theo aggregate boundary.

Không xem Jackson URI resolution là validation hoặc authorization.

## 8. AggregateReference trong Spring Data JDBC

Spring Data JDBC có một kiểu khác cùng tên:

    import org.springframework.data.jdbc.core.mapping.AggregateReference;

Kiểu này được dùng trong domain model để biểu diễn reference tới aggregate root khác. Nó bọc ID của aggregate đích và thể hiện type của aggregate qua generic parameter.

Ví dụ:

    import org.springframework.data.annotation.Id;
    import org.springframework.data.jdbc.core.mapping.AggregateReference;
    import org.springframework.data.relational.core.mapping.Table;

    @Table("purchase_order")
    public class PurchaseOrder {

        @Id
        private Long id;

        private AggregateReference<Customer, Long> customer;
    }

Tạo reference:

    PurchaseOrder order = new PurchaseOrder();

    order.setCustomer(AggregateReference.to(customerId));

Lấy ID:

    Long customerId = order.getCustomer().getId();

Đây là mapping ở tầng persistence Spring Data JDBC. `AggregateReference.to(id)` tạo wrapper từ ID, không nhận hoặc phân tích URI HTTP.

### 8.1. Tại sao Spring Data JDBC dùng AggregateReference?

Spring Data JDBC tổ chức dữ liệu theo aggregate boundary:

- Entity nằm trong cùng aggregate được quản lý theo vòng đời của aggregate root.
- Reference tới aggregate khác nên được biểu diễn bằng ID hoặc AggregateReference.
- Spring Data JDBC không tự tải toàn bộ aggregate liên quan chỉ vì property giữ reference.

Tài liệu Spring Data Relational giải thích rằng quan hệ n-1 hoặc n-m thường biểu diễn hai aggregate độc lập; `AggregateReference` là wrapper quanh ID và type parameter ghi rõ aggregate đích.

Ví dụ `PurchaseOrder` tham chiếu `Customer` là hai aggregate độc lập. Xóa hoặc lưu PurchaseOrder không có nghĩa Spring Data JDBC sẽ quản lý toàn bộ vòng đời Customer như một nested entity.

### 8.2. Khi nào dùng simple ID, khi nào dùng AggregateReference?

| Cách biểu diễn | Khi phù hợp |
|---|---|
| `Long customerId` | Chỉ cần lưu ID và không cần type-safe aggregate target |
| JDBC `AggregateReference<Customer, Long>` | Muốn biểu diễn rõ reference tới aggregate Customer trong domain model |
| Object `Customer` lồng trong aggregate | Customer thực sự thuộc cùng aggregate và vòng đời được quản lý cùng root |
| SDR `AggregateReference<Customer, Long>` | Custom REST handler nhận URI resource và cần resolve ID/aggregate |

Không dùng JDBC AggregateReference trong DTO chỉ vì tên giống Spring Data REST AggregateReference. Chọn kiểu dựa trên tầng đang làm việc.

## 9. Kiểm tra tồn tại và xử lý reference không hợp lệ

Reference URI có thể hợp lệ về cú pháp nhưng resource đích không tồn tại hoặc không thể được resolve.

Với handler nhận AggregateReference:

    Long producerId = producer.resolveRequiredId();

    Producer producerEntity =
        producer.resolveRequiredAggregate();

Nếu chỉ cần ID, service có thể xác nhận tồn tại:

    if (!producerRepository.existsById(producerId)) {
        throw new ProducerNotFoundException(producerId);
    }

Nếu đã resolve aggregate, kiểm tra null hoặc dùng phương thức Required theo đúng contract của API. Chọn cách xử lý lỗi thống nhất cho URI sai, resource không tồn tại và resource không được phép truy cập.

Các tình huống cần phân biệt:

- URI không đúng cú pháp.
- URI không khớp resource mapping.
- Không trích xuất được identifier.
- Identifier có kiểu không chuyển đổi được.
- Resource đích không tồn tại.
- Resource tồn tại nhưng caller không có quyền.
- Resource tồn tại nhưng vi phạm quy tắc nghiệp vụ.

Không trả stack trace hoặc thông tin nội bộ của converter/repository cho client.

## 10. Authorization khi resolve reference

Giải quyết URI thành aggregate chỉ trả lời câu hỏi resource nào được tham chiếu. Nó không tự quyết định caller có được phép dùng resource đó hay không.

Ví dụ user có thể đọc Producer nhưng không có quyền gắn Producer vào Scanner. Service cần kiểm tra quyền theo hành động và theo tenant/ownership:

    Producer producer =
        producerReference.resolveRequiredAggregate();

    authorizationService.assertCanUseProducer(
        currentUser,
        producer
    );

    scannerService.createForProducer(producer);

Nếu ứng dụng multi-tenant, xác nhận Producer thuộc tenant hiện tại trước khi lưu association. Không dựa vào URI hoặc ID mà client gửi để chứng minh tenant.

Với custom controller, dùng Spring Security method/request authorization theo policy của ứng dụng. Nếu cần, đặt kiểm tra trong service để các đường gọi khác cũng áp dụng cùng quy tắc.

## 11. Chọn loại custom controller phù hợp

Spring Data REST cung cấp hai annotation thường gặp:

### 11.1. @RepositoryRestController

Dùng khi custom handler gắn với URI space của repository resource và muốn tận dụng cấu hình Spring Data REST như:

- API base path.
- Message converters.
- Exception handling.
- CORS configuration liên quan repository.
- Hỗ trợ xử lý lazy property khi JPA được dùng.

Ví dụ:

    @RepositoryRestController
    class ScannerController {
        // Repository-related custom operations.
    }

Controller này nên dùng cho custom operation nằm trong URI space của repository.

### 11.2. @BasePathAwareController

Dùng khi cần custom operation nằm dưới API base path nhưng không nhất thiết là thao tác trên một repository resource cụ thể.

Ví dụ:

    @BasePathAwareController
    class ScannerCommandController {
        // Application-specific endpoints under the SDR base path.
    }

Với request DTO chứa URI references, cần bảo đảm handler dùng message converter có Spring Data REST URI-to-aggregate support. Nếu tự cấu hình converter, kiểm tra module tương ứng.

Nếu dùng `@Controller` hoặc `@RestController` thông thường, handler nằm ngoài phạm vi tích hợp của Spring Data REST; message converters và exception handling có thể khác.

## 12. Tương thích phiên bản

Kiểm tra Spring Data release train và dependency thực tế trước khi dùng API.

| Tính năng | Mốc phiên bản được tài liệu Spring ghi nhận |
|---|---|
| Jackson URI-to-aggregate mapping cho DTO payload | Spring Data REST 3.5 |
| `org.springframework.data.rest.core.AggregateReference<T, ID>` cho handler method parameter | Spring Data REST 4.1 |
| `AssociationAggregateReference` cho jMolecules Association | Spring Data REST 4.1 |
| `org.springframework.data.jdbc.core.mapping.AggregateReference<T, ID>` trong Spring Data JDBC | Có từ Spring Data JDBC 1.0 |

Các mốc trên nói về sự xuất hiện của API, không bảo đảm mọi phiên bản Spring Boot hoặc Spring Data module đều tương thích với nhau. Spring Boot quản lý một tập phiên bản Spring Data theo release train; không nâng riêng Spring Data REST/JDBC mà không kiểm tra compatibility matrix.

Nếu dự án dùng Spring Data REST trước 4.1, handler parameter type `org.springframework.data.rest.core.AggregateReference` có thể chưa tồn tại. Khi đó có thể nhận `URI` hoặc `String` rồi tự resolve bằng service/repository và các mapping phù hợp, hoặc nâng cấp release train tương thích.

## 13. Ví dụ kiểm thử

Nên kiểm tra binding URI, resolution và authorization riêng biệt.

### 13.1. GET handler nhận URI reference

- Gửi URI của Producer tồn tại và xác nhận handler nhận đúng ID.
- Xác nhận `resolveRequiredAggregate()` trả đúng Producer.
- Gửi URI không thuộc resource mapping và xác nhận lỗi theo API contract.
- Gửi URI tới Producer không tồn tại và xác nhận lỗi phù hợp.
- Kiểm tra URI có custom identifier mapping nếu ứng dụng dùng EntityLookup.

### 13.2. POST/PUT DTO body

- Gửi một URI Producer hợp lệ trong JSON body.
- Gửi danh sách nhiều URI nếu DTO hỗ trợ collection.
- Gửi URI sai định dạng.
- Gửi URI resource không export hoặc không resolve được.
- Xác nhận custom ObjectMapper không làm mất SDR URI deserializer.
- Kiểm tra response status và error body không lộ nội bộ.

### 13.3. Authorization và domain rules

- User có quyền tham chiếu Producer được phép tạo Scanner.
- User không có quyền sử dụng Producer bị từ chối.
- Reference khác tenant bị từ chối nếu domain yêu cầu cùng tenant.
- Producer đã archived/disabled không được dùng nếu business rule cấm.
- Request lỗi không tạo Scanner hoặc association một phần.

### 13.4. Spring Data JDBC mapping

Nếu dùng JDBC AggregateReference:

- Lưu PurchaseOrder với ID Customer hợp lệ.
- Reload PurchaseOrder và kiểm tra `getCustomer().getId()`.
- Xác nhận wrapper được map vào foreign-key value theo schema.
- Kiểm tra foreign key database nếu cần bảo đảm reference target tồn tại.
- Không giả định load PurchaseOrder tự động load toàn bộ Customer.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Không inject được AggregateReference vào handler | Spring Data REST version thấp hơn 4.1 hoặc import sai package |
| URI parameter không resolve | URI không khớp item resource mapping |
| resolveRequiredId thất bại | Không trích được ID hoặc URI không hợp lệ |
| resolveRequiredAggregate thất bại | Aggregate đích không resolve được |
| DTO nhận URI string thay vì object | SDR Jackson URI deserializer không có trong converter đang dùng |
| Custom ObjectMapper làm binding ngừng hoạt động | Converter riêng không đăng ký SDR Jackson support |
| Dùng sai AggregateReference | Nhầm org.springframework.data.rest.core với org.springframework.data.jdbc.core.mapping |
| AssociationAggregateReference không compile | Thiếu Spring Data REST 4.1+ hoặc jMolecules types/dependency phù hợp |
| Resource resolve thành công nhưng user vẫn không được dùng | Chưa kiểm tra authorization/business rule |
| URI tự ghép không hoạt động | Resource path hoặc EntityLookup khác giả định của client |
| Chỉ lưu ID nhưng cần kiểm tra trạng thái target | Cần resolve aggregate hoặc tải từ repository/service |
| JDBC reference không tự tải aggregate đích | JDBC AggregateReference chỉ bọc ID, không phải object relationship được tự động fetch |

## 15. Checklist triển khai

1. Xác định đang dùng Spring Data REST URI reference hay Spring Data JDBC persistence reference.
2. Dùng đúng package và dependency cho AggregateReference.
3. Kiểm tra phiên bản Spring Data REST có hỗ trợ handler parameter API từ 4.1.
4. Với GET custom handler, khai báo `@RequestParam AggregateReference<T, ID>`.
5. Dùng `resolveRequiredId()` nếu chỉ cần ID.
6. Dùng `resolveRequiredAggregate()` nếu cần object đầy đủ.
7. Dùng `withIdSource(...)` chỉ khi URI có identifier mapping tùy chỉnh.
8. Dùng `AssociationAggregateReference` khi domain model thực sự dùng jMolecules Association.
9. Với POST/PUT DTO, gửi URI resource trong JSON và xác nhận SDR Jackson URI resolution được cấu hình.
10. Chọn `@RepositoryRestController` hoặc `@BasePathAwareController` theo URI space và nhu cầu tích hợp.
11. Kiểm tra resource tồn tại, tenant, ownership và authorization sau khi resolve.
12. Không xem URI/ID là bằng chứng quyền truy cập.
13. Với Spring Data JDBC, dùng `AggregateReference.to(id)` cho reference giữa aggregate.
14. Kiểm thử URI hợp lệ, URI sai, target không tồn tại, quyền truy cập và custom ObjectMapper.
15. Đối chiếu Spring Data version với Spring Boot release train trước khi áp dụng API.

## Tài liệu tham khảo

- [Spring Data REST — Obtaining Aggregate References in custom controllers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)
- [Spring Data REST — AggregateReference API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/AggregateReference.html)
- [Spring Data REST — AggregateReferenceResolvingModule API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/json/AggregateReferenceResolvingModule.html)
- [Spring Data REST — AssociationAggregateReference API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/AssociationAggregateReference.html)
- [Spring Data Relational — Referenced entities and AggregateReference](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html)
- [Spring Data JDBC — AggregateReference API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/mapping/AggregateReference.html)
- [Spring blog — Spring Data REST aggregate reference mapping for DTOs](https://spring.io/blog/2021/04/20/what-s-new-in-spring-data-2021-0/)
- [Spring Data REST — Overriding response handlers and controller integration](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)
