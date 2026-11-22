# Versioning hợp đồng API và chiến lược chuyển tiếp cho máy khách

## Mục tiêu

Hợp đồng API mô tả những gì máy khách có thể dựa vào khi giao tiếp với server: đường dẫn và quan hệ tài nguyên, HTTP method, tham số, cấu trúc request/response, kiểu dữ liệu, mã trạng thái, quy tắc lỗi, xác thực và ý nghĩa nghiệp vụ. Versioning là cách công bố và duy trì những phiên bản hợp đồng khác nhau khi API phát triển.

Với Spring Data REST, repository có thể tự động tạo collection resource, item resource, search resource và các liên kết hypermedia. Điều này giúp giảm lượng controller phải viết, nhưng không loại bỏ trách nhiệm quản lý tương thích. Một thay đổi trong entity, projection, repository exposure hoặc relation name vẫn có thể làm máy khách hiện tại ngừng hoạt động.

Mục tiêu của versioning là cho phép API tiếp tục phát triển trong khi các máy khách có thời gian và hướng dẫn rõ ràng để chuyển sang hợp đồng mới.

## 1. Phân biệt version API với version ứng dụng

Không nên đồng nhất version API với version build hoặc version triển khai của ứng dụng.

- **Application version** mô tả phiên bản phần mềm server được build và triển khai, ví dụ `2.8.1`.
- **API version** mô tả hợp đồng mà client nhìn thấy, ví dụ `v1` hoặc `v2`.
- **Resource representation version** mô tả một hình dạng biểu diễn cụ thể của tài nguyên.
- **Schema version** mô tả phiên bản schema hoặc cấu trúc dữ liệu được dùng để trao đổi.

Server có thể phát hành nhiều lần build mà vẫn giữ nguyên hợp đồng API v1. Ngược lại, một bản triển khai duy nhất có thể phục vụ đồng thời API v1 và v2 trong giai đoạn chuyển tiếp.

Versioning hợp đồng cần xét toàn bộ hành vi quan sát được, không chỉ tên trường JSON:

- URI, relation name và cách khám phá tài nguyên.
- HTTP method, query parameter, pagination và sorting.
- Request/response fields, kiểu dữ liệu, nullability và format.
- HTTP status, cấu trúc lỗi và quy tắc retry.
- Authentication, authorization, rate limit và semantics của thao tác.
- Thứ tự mặc định, quy tắc lọc và ý nghĩa của dữ liệu trả về.

## 2. Xác định thay đổi tương thích và thay đổi phá vỡ tương thích

Một thay đổi tương thích cho phép client cũ tiếp tục hoạt động với server mới mà không cần sửa ngay. Một thay đổi phá vỡ tương thích (breaking change) có thể khiến client cũ không biên dịch, không parse được response hoặc thay đổi hành vi.

| Thay đổi | Đánh giá thường gặp | Lý do |
|---|---|---|
| Thêm field response tùy chọn | Tương thích | Client cũ có thể bỏ qua field chưa biết. |
| Thêm endpoint hoặc relation mới | Tương thích | Client cũ không cần sử dụng khả năng mới. |
| Thêm query parameter tùy chọn với default giữ nguyên hành vi | Tương thích | Request cũ vẫn có cùng ý nghĩa. |
| Xóa hoặc đổi tên field/endpoint/relation | Breaking | Client cũ không còn tìm thấy phần tử mà nó phụ thuộc. |
| Đổi kiểu field, đơn vị hoặc format | Breaking | Client có thể parse sai hoặc tính toán sai. |
| Biến field request tùy chọn thành bắt buộc | Breaking | Request cũ có thể bị từ chối. |
| Thay đổi ý nghĩa nghiệp vụ nhưng giữ nguyên tên field | Breaking về hành vi | Client vẫn parse được nhưng nhận kết quả khác. |
| Thay đổi status code hoặc cấu trúc lỗi | Có thể breaking | Client có thể phân nhánh xử lý theo status hoặc error code. |
| Thêm giá trị enum | Có thể breaking | Client dùng enum đóng hoặc switch exhaustive có thể không xử lý giá trị mới. |
| Thay đổi default sort, page size hoặc quy ước chỉ số trang | Có thể breaking | Cùng request nhưng tập kết quả hoặc thứ tự có thể thay đổi. |

Không nên chỉ dùng số lượng field để đánh giá tương thích. Ví dụ, đổi `amount` từ đồng sang nghìn đồng vẫn giữ kiểu số nhưng thay đổi ý nghĩa; đây là thay đổi phá vỡ hợp đồng.

Với response, client nên bỏ qua field và relation không nhận biết khi có thể. Với enum, nên có nhánh xử lý giá trị chưa biết hoặc ánh xạ sang trạng thái dự phòng. Với request, server vẫn cần validation rõ ràng và thông báo lỗi có cấu trúc.

## 3. Các chiến lược lựa chọn phiên bản API

Có nhiều cách để client chỉ định hợp đồng muốn sử dụng. Chọn một quy ước nhất quán cho toàn API và ghi rõ trong tài liệu.

### 3.1. Version trong URI

Ví dụ:

~~~http
GET /api/v1/people/42
GET /api/v2/people/42
~~~

Ưu điểm:

- Nhìn vào URL có thể nhận biết phiên bản.
- Dễ cấu hình route, gateway, log, cache và giám sát.
- Client có thể pin một phiên bản rõ ràng.
- Hai phiên bản có thể được triển khai song song trong thời gian chuyển tiếp.

Nhược điểm:

- Phải duy trì nhiều route và thường là nhiều representation.
- Link hypermedia cần dẫn tới đúng không gian URI của phiên bản.
- Có thể tạo thêm code mapping giữa domain model và DTO của từng phiên bản.

Đây là lựa chọn dễ quan sát và vận hành khi cần nhiều phiên bản cùng tồn tại. Không nên tạo version mới chỉ vì mỗi lần server release.

### 3.2. Version qua media type

Client chỉ định phiên bản trong header `Accept`:

~~~http
GET /api/people/42
Accept: application/vnd.example.person-v2+json
~~~

Server trả về representation tương ứng nếu hỗ trợ media type đó. Với request có body, `Content-Type` mô tả media type của dữ liệu gửi lên.

Ưu điểm:

- URI tài nguyên có thể giữ nguyên.
- Version gắn với representation hoặc contract được thương lượng.
- Phù hợp với thiết kế REST dựa trên content negotiation.

Nhược điểm:

- Khó quan sát hơn URI versioning nếu chỉ nhìn URL.
- Cache và proxy phải tính đến header `Accept`; response cần cấu hình `Vary: Accept` khi representation thay đổi theo header.
- Client phải gửi đúng media type và xử lý phản hồi không hỗ trợ loại nội dung.

Nếu sử dụng vendor media type, hãy công bố chính xác media type được chấp nhận, ví dụ `application/vnd.example.person-v1+json` và `application/vnd.example.person-v2+json`.

### 3.3. Version qua custom header

Ví dụ:

~~~http
GET /api/people/42
Api-Version: 2
~~~

Cách này giữ URI gọn nhưng yêu cầu client và server thống nhất tên header, giá trị hợp lệ, default version và cách xử lý khi thiếu header. Cache phải phân biệt response theo header version, thường bằng `Vary: Api-Version`. Gateway và công cụ debug cũng cần biết header này.

Custom header không tự trở thành một chuẩn versioning chung. Chỉ chọn cách này khi hạ tầng của tổ chức đã có quy ước và hỗ trợ đầy đủ.

### 3.4. Version qua query parameter

Ví dụ:

~~~http
GET /api/people/42?version=2
~~~

Cách này dễ thử nghiệm nhưng có thể làm API khó thống nhất khi mọi endpoint đều phải mang tham số version. Nó cũng làm tăng nguy cơ cache nhầm nếu cache key không bao gồm query parameter. Chỉ dùng khi có lý do rõ ràng và đã xác định quy tắc cho mọi resource.

### 3.5. Chọn chiến lược nào?

| Tiêu chí | URI | Media type | Custom header | Query parameter |
|---|---|---|---|---|
| Dễ nhận biết trong log | Cao | Trung bình | Trung bình | Cao |
| Giữ nguyên URI resource | Không | Có | Có | Có |
| Cache cần phân biệt theo | URI | `Accept` | Header version | Query parameter |
| Client cần cấu hình | URL | Accept/Content-Type | Header riêng | Query |
| Vận hành song song nhiều phiên bản | Rõ ràng | Được | Được | Được |

Không có lựa chọn phù hợp cho mọi hệ thống. URI versioning thường dễ triển khai và vận hành nhất khi nhiều client cần chọn phiên bản rõ ràng. Media type versioning phù hợp khi tổ chức đã dùng content negotiation nhất quán. Dù chọn cách nào, phải tránh để cùng một request có thể được diễn giải thành hai hợp đồng khác nhau mà client không nhận biết được.

## 4. Spring Data REST hỗ trợ versioning đến đâu?

Spring Data REST tập trung vào việc xuất bản repository và representation hypermedia. Một số khả năng liên quan gồm:

- `@RepositoryRestResource(path = "people")` đặt đường dẫn collection resource.
- `@RestResource(path = "...", rel = "...")` tùy chỉnh đường dẫn hoặc relation của method.
- `@Projection` định nghĩa một góc nhìn của entity.
- `excerptProjection` chọn projection dùng cho phần tử trong collection.
- `RepositoryRestConfigurer` cấu hình base path, exporter, media type, converter và các tích hợp khác.
- `@BasePathAwareController` và `@RepositoryRestController` hỗ trợ endpoint tùy chỉnh trong không gian URL liên quan tới Spring Data REST.

Các tính năng trên giúp xây dựng representation và route, nhưng không tạo ra một quy trình quản lý nhiều version hợp đồng hoàn chỉnh. Projection là lựa chọn hình dạng representation, không tự động tương đương với API v1/v2. ALPS profile mô tả ngữ nghĩa của API; nó cũng không phải cơ chế chọn phiên bản request.

Đổi `path` hoặc `rel` của repository đang được client sử dụng có thể là breaking change. Khi cần giữ v1 trong khi cung cấp v2, phải chủ động duy trì hai hợp đồng và route tương ứng, hoặc dùng content negotiation có quy ước rõ ràng.

## 5. Tổ chức v1 và v2 trong ứng dụng Spring Data REST

Một cách thực tế là giữ repository và domain service làm nguồn dữ liệu/nghiệp vụ dùng chung, sau đó tạo representation riêng cho mỗi API version.

Ví dụ domain model có thể tiếp tục giữ `firstName` và `lastName`, trong khi v2 muốn công bố `displayName`:

~~~java
public record PersonV1(
        Long id,
        String firstName,
        String lastName,
        String email) {
}

public record PersonV2(
        Long id,
        String displayName,
        String emailAddress) {
}
~~~

Mapper chịu trách nhiệm chuyển domain model thành contract tương ứng:

~~~java
public final class PersonApiMapper {

    private PersonApiMapper() {
    }

    public static PersonV1 toV1(Person person) {
        return new PersonV1(
                person.getId(),
                person.getFirstName(),
                person.getLastName(),
                person.getEmail());
    }

    public static PersonV2 toV2(Person person) {
        return new PersonV2(
                person.getId(),
                person.getFirstName() + " " + person.getLastName(),
                person.getEmail());
    }
}
~~~

Với URI versioning, endpoint v2 tùy chỉnh có thể nằm dưới base path của Spring Data REST:

~~~java
import org.springframework.data.rest.webmvc.BasePathAwareController;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

@BasePathAwareController
@RequestMapping("/v2/people")
public class PersonV2Controller {

    private final PersonRepository repository;

    public PersonV2Controller(PersonRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/{id}")
    public ResponseEntity<PersonV2> findById(@PathVariable Long id) {
        Person person = repository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND));

        return ResponseEntity.ok(PersonApiMapper.toV2(person));
    }
}
~~~

Nếu base path của Spring Data REST là `/api`, route ví dụ sẽ là `/api/v2/people/{id}`. Đây là skeleton minh họa cho một GET endpoint; cần bổ sung các method, status, validation, error mapping, link và security policy tương ứng với toàn bộ contract v2 trước khi công bố.

Các nguyên tắc quan trọng:

1. **Giữ domain logic dùng chung:** v1 và v2 gọi cùng application service nếu quy tắc nghiệp vụ không đổi.
2. **Tách DTO theo version:** không đổi trực tiếp entity chỉ để phù hợp với một representation mới.
3. **Tách mapper:** mapper v1/v2 thể hiện rõ tên field, format và quy tắc chuyển đổi.
4. **Giữ route độc lập:** tránh mapping v1 và v2 vào cùng một handler nhưng diễn giải request khác nhau không rõ ràng.
5. **Giữ hypermedia nhất quán:** self link, relation và link điều hướng phải thuộc đúng không gian URI hoặc contract mà client đã chọn.
6. **Kiểm tra quyền và validation:** v2 không được vô tình bỏ qua chính sách bảo mật mà v1 đang áp dụng.

Không nên đăng ký hai repository interface cùng quản lý một domain type chỉ để tạo hai version rồi kỳ vọng Spring Data REST tự phân biệt chúng. Nếu cần nhiều representation, hãy thiết kế route/controller, projection và mapper có chủ đích, sau đó kiểm tra toàn bộ mapping thực tế.

## 6. Dùng projection mà không nhầm với versioning

Projection có thể giúp giới hạn các thuộc tính xuất hiện trong representation:

~~~java
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    Long getId();

    String getFirstName();

    String getLastName();
}
~~~

Client có thể yêu cầu projection theo cơ chế mà repository công bố, ví dụ:

~~~http
GET /people/42?projection=personSummary
~~~

Projection hữu ích khi client cần nhiều góc nhìn của cùng một resource. Tuy nhiên, nếu projection bị xóa, đổi field hoặc thay đổi ý nghĩa thì client vẫn có thể bị ảnh hưởng. Projection không tự cung cấp:

- Version namespace riêng và chính sách hỗ trợ.
- Bộ status/error semantics độc lập.
- Quy trình deprecation và sunset.
- Route v1/v2 được duy trì song song.
- Contract tests và migration guide.

Hãy dùng projection cho lựa chọn representation trong cùng một contract. Khi hai client cần cam kết tương thích khác nhau trong thời gian dài, quản lý version rõ ràng hơn.

## 7. Quy trình chuyển tiếp máy khách từ v1 sang v2

Chuyển version là một quá trình có thời gian, người chịu trách nhiệm và tiêu chí kết thúc. Một quy trình có thể triển khai theo các giai đoạn sau.

### Giai đoạn 1 — Kiểm kê máy khách và mức sử dụng

Xác định:

- Client nào đang gọi v1: web frontend, mobile app, đối tác, batch job hoặc service nội bộ.
- Phiên bản ứng dụng/client, chủ sở hữu và môi trường đang sử dụng.
- Endpoint, relation, field, projection và thao tác mà mỗi client phụ thuộc.
- Tần suất gọi và các luồng nghiệp vụ quan trọng.
- Client nào có thể nâng cấp nhanh và client nào cần thời gian phát hành dài.

Có thể dùng API gateway log, request metric hoặc telemetry có định danh client. Không đưa access token, dữ liệu cá nhân hoặc payload nhạy cảm vào log chỉ để theo dõi version.

### Giai đoạn 2 — Thiết kế và công bố contract v2

Trước khi triển khai:

1. Viết change log v1 → v2, liệt kê từng thay đổi và lý do.
2. Công bố schema, ví dụ request/response, status và error format.
3. Xác định cơ chế chọn version và default behavior.
4. Ghi rõ authentication, authorization, pagination, sorting, rate limit và retry policy.
5. Cung cấp migration guide với ví dụ trước/sau.
6. Xác định ngày bắt đầu deprecation và ngày dự kiến ngừng v1 nếu chính sách cho phép.

OpenAPI có thể mô tả contract HTTP, operation, schema và response. Với Spring Data REST, ALPS profile cung cấp metadata ngữ nghĩa và liên kết; hãy dùng tài liệu phù hợp với cách API thực tế được công bố. Không nên giả định ALPS tự thay thế OpenAPI hoặc mô tả đầy đủ mọi ràng buộc của request/response.

### Giai đoạn 3 — Triển khai song song và kiểm tra

Duy trì v1 trong khi đưa v2 vào hoạt động. Trước khi cho client sử dụng rộng rãi:

- Chạy contract test cho cả v1 và v2.
- Kiểm tra serialization/deserialization của DTO.
- Kiểm tra status code, lỗi, quyền truy cập và pagination.
- Kiểm tra link HAL và relation có trỏ tới đúng version.
- Kiểm tra cache key, `Vary` và gateway routing nếu version được chọn bằng header.
- Chạy integration test qua HTTP thật thay vì chỉ gọi mapper hoặc repository trực tiếp.

Có thể triển khai v2 cho nhóm client nhỏ trước, dùng feature flag hoặc cấu hình gateway. Nếu có thể, so sánh kết quả v1/v2 trong môi trường thử nghiệm; không thực hiện hai thao tác ghi thật chỉ để so sánh vì có thể tạo side effect trùng lặp.

### Giai đoạn 4 — Hỗ trợ client chuyển đổi

Cung cấp:

- Hướng dẫn đổi URL hoặc header.
- Bảng mapping field cũ sang field mới.
- Ví dụ request/response và cách xử lý lỗi.
- Thông tin thay đổi pagination, sorting, relation và projection.
- SDK hoặc client library nếu tổ chức có duy trì.
- Kênh hỗ trợ và đầu mối chịu trách nhiệm cho từng client.

Client nên pin version đã chọn thay vì phụ thuộc vào một default version có thể thay đổi theo thời gian. Client hypermedia nên theo các relation được công bố, tránh ghép URL bằng chuỗi nếu server đã cung cấp link phù hợp.

### Giai đoạn 5 — Deprecation, theo dõi và sunset

Khi v2 đã sẵn sàng và client có lộ trình chuyển đổi:

1. Công bố v1 bị deprecated với thời điểm và lý do rõ ràng.
2. Gửi thông báo tới các chủ sở hữu client còn sử dụng v1.
3. Theo dõi lưu lượng v1 theo client, route và môi trường.
4. Nhắc lại trước thời hạn sunset.
5. Chỉ ngừng v1 khi đã đạt tiêu chí chuyển đổi và chính sách hỗ trợ cho phép.
6. Giữ tài liệu lưu trữ và hướng dẫn xử lý nếu client cũ còn gọi sau ngày kết thúc.

Có thể dùng các HTTP response header chuẩn để truyền thông tin vòng đời:

~~~http
Deprecation: @1798761600
Link: <https://api.example.com/docs/deprecations/people-v1>; rel="deprecation"
Sunset: Wed, 30 Jun 2027 00:00:00 GMT
~~~

- `Deprecation` được định nghĩa trong RFC 9745. Giá trị là Structured Field Date (Unix timestamp có tiền tố `@`), biểu thị thời điểm API hoặc phần tử bị đánh dấu deprecated.
- `Link` với relation `deprecation` có thể dẫn tới tài liệu giải thích thay đổi và hướng dẫn chuyển đổi.
- `Sunset` được định nghĩa trong RFC 8594, dùng HTTP-date để công bố thời điểm tài nguyên dự kiến không còn khả dụng.

Ngày trong ví dụ chỉ minh họa định dạng, không phải lịch sunset mặc định. Header deprecation không tự chặn request và header sunset không tự xóa route; server vẫn cần chính sách thực thi và thông báo tới client.

## 8. Thiết kế máy khách chịu được thay đổi

Máy khách cũng cần được thiết kế để không dễ hỏng khi server bổ sung khả năng:

- Bỏ qua field JSON không nhận biết nếu field đó không ảnh hưởng tới logic bắt buộc.
- Xử lý enum chưa biết bằng nhánh fallback thay vì giả định tập giá trị đóng.
- Theo HAL relation và link server trả về thay vì hard-code mọi đường dẫn.
- Không phụ thuộc vào thứ tự field JSON.
- Xử lý đúng status code, error body và retry policy.
- Chỉ retry request an toàn hoặc idempotent khi có cơ sở; không tự động retry POST tạo tài nguyên nếu không có idempotency key hoặc cơ chế chống tạo trùng.
- Pin API version và cập nhật có chủ đích.
- Dùng contract test để phát hiện thay đổi ngoài dự kiến.

Tính chịu lỗi ở client không thay thế cam kết tương thích từ server. Server vẫn phải công bố rõ field nào bắt buộc, field nào có thể vắng mặt và semantics của từng thao tác.

## 9. Kiểm thử hợp đồng và giám sát nhiều phiên bản

Một API version cần được kiểm thử như một sản phẩm độc lập.

| Lớp kiểm thử | Nội dung cần xác nhận |
|---|---|
| Contract test | Request/response, field, media type, status và error format đúng đặc tả. |
| Integration test | Route, repository, mapper, controller và hypermedia link hoạt động cùng nhau. |
| Authorization test | Quyền của v1 và v2 không bị nới lỏng ngoài chủ đích. |
| Compatibility test | Client cũ tiếp tục chạy khi server triển khai thay đổi tương thích. |
| Consumer-driven contract | Những giả định quan trọng của client được kiểm chứng tự động. |
| Regression test | Các luồng nghiệp vụ quan trọng không đổi ngoài phạm vi version mới. |

Dashboard nên tách metric theo API version, client identity, route và status code. Theo dõi ít nhất:

- Request count và tỷ lệ lỗi của từng version.
- Client còn gọi version deprecated.
- Các route hoặc relation được sử dụng.
- Latency và tỷ lệ timeout.
- Các lỗi validation hoặc deserialization nổi bật.

Đặt ngưỡng hoàn tất migration có thể đo được, ví dụ tất cả client đã xác nhận chuyển đổi, lưu lượng v1 bằng 0 trong khoảng thời gian quy định và không còn luồng nghiệp vụ bắt buộc phụ thuộc v1. Không nên xóa v1 chỉ vì v2 đã triển khai thành công.

## 10. Các lỗi thường gặp khi versioning API

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Client cũ không parse được response mới | Field bị đổi tên/kiểu, enum mới hoặc cấu trúc lồng nhau thay đổi. |
| URL v1 bất ngờ trả representation v2 | Default version hoặc gateway routing thay đổi; version không được pin rõ ràng. |
| Link HAL dẫn client sang route không tương thích | Hypermedia link được tạo từ route mặc định hoặc mapping không gắn với version. |
| Cache trả response của version khác | Cache key thiếu URI/header/query parameter dùng để chọn version hoặc thiếu `Vary`. |
| Projection được xem như version hợp đồng | Projection chỉ thay đổi representation; không có lifecycle và compatibility policy độc lập. |
| v2 làm thay đổi nghiệp vụ của v1 | Hai version dùng chung service nhưng quy tắc mới không được cô lập; cần phân biệt mapping với domain behavior. |
| Không biết client nào còn dùng v1 | Thiếu telemetry, client identification hoặc dashboard theo version. |
| Ngừng v1 nhưng client vẫn gọi | Sunset chưa được thông báo/giám sát hoặc chưa có tiêu chí chuyển đổi rõ ràng. |
| Retry làm tạo trùng tài nguyên | Client retry POST mà không có idempotency key hoặc cơ chế chống duplicate. |

## Ghi nhớ

Versioning là cam kết về hợp đồng và thời gian hỗ trợ. Hãy phân loại thay đổi trước khi phát hành; giữ thay đổi tương thích trong cùng version khi có thể; tạo version mới cho breaking change; và duy trì các version song song đủ lâu để client chuyển đổi. Trong Spring Data REST, repository và projection giúp tạo representation, còn controller, DTO, mapper, configurer và hypermedia link giúp triển khai các contract version có chủ đích. Deprecation, telemetry, migration guide, contract test và sunset policy hoàn tất vòng đời của mỗi version.

## Tài liệu tham khảo

- [Spring Data REST — Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST — Overriding Response Handlers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [RFC 9745 — The Deprecation HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9745)
- [RFC 8594 — The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594)
