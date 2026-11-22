# Rà soát bề mặt API được công bố sau mỗi lần phát hành

## Mục tiêu

Spring Data REST tạo REST API từ các Spring Data repository. Vì vậy, thay đổi ở interface repository, entity, association, projection, cấu hình export hoặc Jackson có thể làm thay đổi API mà client nhìn thấy dù không có controller mới. Sau mỗi lần nâng phiên bản hoặc phát hành ứng dụng, cần kiểm tra lại toàn bộ hợp đồng HTTP đã công bố để phát hiện endpoint bị thêm/mất, thay đổi biểu diễn, quyền truy cập hoặc hành vi.

Việc rà soát cần trả lời được ba câu hỏi:

1. Client hiện có thể khám phá và gọi những resource nào?
2. Cấu trúc request/response, HTTP method, media type, status code và metadata có thay đổi so với bản đã phát hành không?
3. Thay đổi đó có tương thích với client hiện tại, có được chủ động chấp thuận và có kiểm thử chứng minh không?

Bề mặt API là hợp đồng quan sát được từ bên ngoài. Nó bao gồm cả HAL links, URI template, ALPS/JSON Schema, query parameter, header và response status, chứ không chỉ danh sách URL.

## 1. Xác định phiên bản cần so sánh

Trước khi kiểm tra, ghi lại phiên bản đang chạy và phiên bản dự kiến phát hành:

- Phiên bản Spring Boot và Spring Framework.
- Spring Data release train và phiên bản Spring Data REST.
- Phiên bản các module Spring Data được dùng (Commons, JPA, MongoDB, JDBC, ...).
- Java, Jackson và các thư viện tích hợp có ảnh hưởng đến serialization hoặc HTTP.
- Các cấu hình ứng dụng có thể thay đổi việc export: repository detection, base path, repository visibility, `@RepositoryRestResource`, `@RestResource`, projection, excerpt, custom controller, serializer và security.

Các module Spring Data không nhất thiết có cùng số phiên bản. Dùng Spring Data release train BOM để chọn nhóm phiên bản tương thích; không tự nâng riêng một module chỉ vì số phiên bản trông gần nhau.

Khi nâng cấp, đọc hướng dẫn nâng cấp và release notes từ phiên bản đang dùng đến phiên bản đích. Nếu bỏ qua nhiều release train, đọc cả release notes của các phiên bản trung gian. Spring Data ghi chú rằng hướng dẫn nâng cấp nằm ở đầu release notes. Ghi lại các thay đổi liên quan đến Spring Data REST, Spring Data Commons, module lưu trữ và Spring Framework/Boot.

Không lấy số phiên bản thư viện làm phiên bản hợp đồng API của dịch vụ. Một release train mới có thể không làm thay đổi API đang công bố; ngược lại, thay đổi repository hoặc projection trong ứng dụng có thể làm API thay đổi dù dependency không đổi.

## 2. Lập danh mục bề mặt API thực tế

Không suy ra toàn bộ API chỉ từ source code. Hãy khởi động ứng dụng với đúng profile, feature flag, security và cấu hình sẽ phát hành, sau đó khám phá API qua HTTP.

### 2.1. Resource root và HAL links

Gọi root URL và lưu response cùng header:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/
~~~

Spring Data REST mặc định dùng HAL để biểu diễn liên kết. Trong `_links`, mỗi relation cho biết resource tiếp theo có thể khám phá. Kiểm tra:

- Những relation nào xuất hiện và relation nào biến mất.
- `href` có thay đổi path, base path, scheme, host hoặc context path không.
- Link nào là URI template và có thay đổi biến template không.
- `profile` có còn được công bố và trỏ đến metadata đúng không.
- Những resource mới có vô tình xuất hiện do repository mới được phát hiện không.

Đừng hard-code một URL metadata dựa trên ví dụ cũ. Hãy đi theo `profile` link được trả về ở root, sau đó theo link của từng resource. Cấu hình base path và phiên bản Spring Data REST có thể làm URI cụ thể khác nhau.

### 2.2. Collection, item, association và search resource

Với mỗi repository được export, kiểm tra tối thiểu các loại resource sau:

| Loại resource | Điều cần ghi nhận |
|---|---|
| Collection | relation, URI, `GET`/`POST`, phân trang, sắp xếp, media type, status |
| Item | URI template, `GET`/`PUT`/`PATCH`/`DELETE`, response fields, ETag |
| Association | relation và URI, `GET`/`PUT`/`POST`/`DELETE`, `text/uri-list`, quy tắc liên kết |
| Search | relation `search`, tên/path query method, tham số, phân trang, kiểu kết quả |
| Profile | link metadata, ALPS descriptors, JSON Schema |
| Endpoint tùy chỉnh | controller path, method, request/response, security và lỗi |

Spring Data REST thường suy ra collection path từ tên domain type đã chuyển thành dạng không viết hoa và số nhiều. `@RepositoryRestResource` có thể thay đổi path hoặc relation. Association path mặc định lấy từ tên thuộc tính và có thể được tùy chỉnh bằng `@RestResource`.

Việc một HTTP method có được export hay không phụ thuộc vào method repository hiện có và cấu hình export. Method bị loại bỏ hoặc đánh dấu `@RestResource(exported = false)` có thể làm một operation biến mất. Kiểm tra thực tế bằng request; đừng giả định mọi repository đều có đủ CRUD.

Search resource chỉ xuất hiện khi repository công khai query method. Tên và path query resource cũng có thể được tùy chỉnh bằng `@RestResource` trên method. Khi so sánh, ghi nhận cả tên tham số, kiểu tham số, URI template và kết quả query.

Ví dụ kiểm tra discovery:

~~~bash
curl -sS -H "Accept: application/hal+json" http://localhost:8080/orders
curl -sS -H "Accept: application/hal+json" http://localhost:8080/orders/search
curl -i -H "Accept: application/hal+json" http://localhost:8080/orders/1
~~~

Các URL trên chỉ là ví dụ. Dùng link thực tế từ root/collection response của ứng dụng.

### 2.3. Request, response và HTTP semantics

Với mỗi operation đã công bố, ghi lại:

- HTTP method và điều kiện được phép gọi.
- `Content-Type` request và `Accept` response được hỗ trợ.
- Các field bắt buộc, tùy chọn, nullable, read-only và kiểu dữ liệu.
- Cách biểu diễn association: dữ liệu inline hay URI link.
- Status code cho thành công, validation, không tìm thấy, xung đột, method không hỗ trợ và lỗi xác thực/phân quyền.
- Header như `Location`, `ETag`, `Last-Modified`, `Allow`, `Cache-Control` và header do ứng dụng/proxy bổ sung.
- Quy tắc `page`, `size`, `sort`, filter và query parameter tùy chỉnh.

Spring Data REST có thể trả `201 Created` cho thao tác tạo, `200 OK` hoặc `204 No Content` cho một số thao tác cập nhật/xóa tùy cấu hình và header. Không ghi một status code chung cho toàn API; kiểm tra từng operation và cấu hình thực tế.

Kiểm tra cả request không hợp lệ: thiếu field, sai kiểu, media type không hỗ trợ, URI association không tồn tại, method bị tắt và user không có quyền. Thay đổi status code hoặc cấu trúc lỗi cũng có thể phá client.

### 2.4. Representation, projection và excerpt

Kiểm tra JSON/HAL của collection và item. Đặc biệt chú ý:

- Tên field, kiểu, định dạng ngày giờ, precision số, enum và cách xử lý `null`.
- Field mới hoặc bị loại bỏ.
- Association chuyển từ link sang object inline hoặc ngược lại.
- Thay đổi do Jackson serializer/deserializer, mixin, `@JsonIgnore` hoặc cấu hình `ObjectMapper`.
- Projection mới, projection bị xóa hoặc đổi tên.
- Excerpt projection được áp dụng mặc định trong collection.

Projection có thể thay đổi field được trả về khi client gửi tham số `projection`. Excerpt projection được dùng tự động cho resource được nhúng trong collection hoặc association theo cấu hình repository; nó không tự động áp dụng cho item resource. Thay đổi excerpt mặc định có thể là breaking change với client đang đọc collection.

Đừng coi field mới luôn vô hại: client deserialize bằng schema nghiêm ngặt có thể từ chối field lạ. Field bị xóa, đổi tên, đổi kiểu hoặc thay đổi từ nullable sang bắt buộc thường có rủi ro cao hơn. Cần kiểm tra theo cách client thực tế parse response.

### 2.5. Metadata ALPS và JSON Schema

Spring Data REST cung cấp ALPS document cho mỗi repository được export. Metadata mô tả representation, thuộc tính và các transition/operation. Projection được công bố cũng có thể xuất hiện trong ALPS.

Theo `profile` link ở root, lấy profile resource của từng repository:

~~~bash
curl -i -H "Accept: application/alps+json" http://localhost:8080/profile/orders
curl -i -H "Accept: application/schema+json" http://localhost:8080/profile/orders
~~~

Path `/profile/orders` là ví dụ theo cấu hình mặc định trong tài liệu. Trong ứng dụng thực tế, phải theo các link được trả về từ root/profile và dùng đúng `Accept` header.

So sánh:

- ALPS descriptor của representation và operation.
- Tên descriptor, kiểu `SEMANTIC`, `SAFE`, `IDEMPOTENT`, `UNSAFE`.
- Các tham số như `projection` và lựa chọn projection.
- JSON Schema `properties`, `type`, `format`, `readOnly`, cấu trúc lồng nhau và schema version.
- Metadata mô tả nghiệp vụ được khai báo qua `rest.description.*`.

Metadata là một phần của bề mặt API nếu client hoặc công cụ tự động dùng nó để khám phá và tạo request. Không bỏ qua metadata chỉ vì endpoint CRUD vẫn trả `200`.

## 3. Tạo baseline có thể so sánh

Lưu baseline của bản phát hành đang chạy trong kho mã hoặc artifact của pipeline. Baseline nên có:

1. Root HAL response.
2. Danh sách repository relation và các link được khám phá.
3. Collection/item/association/search response đại diện.
4. ALPS và JSON Schema của từng repository được công bố.
5. Header và status của các operation quan trọng.
6. Các response của projection/excerpt quan trọng.
7. Ma trận quyền truy cập cho các role chính.
8. Phiên bản dependency và cấu hình profile/feature flag tạo ra snapshot.

Ví dụ thu thập baseline bằng `curl`:

~~~bash
mkdir -p api-baseline
curl -fsS -H "Accept: application/hal+json" http://localhost:8080/ > api-baseline/root.json
curl -fsS -H "Accept: application/alps+json" http://localhost:8080/profile/orders > api-baseline/orders.alps.json
curl -fsS -H "Accept: application/schema+json" http://localhost:8080/profile/orders > api-baseline/orders.schema.json
~~~

Đây là lệnh mẫu; thay host và các URI bằng địa chỉ/link của ứng dụng. Nếu URI được khám phá qua HAL, tự động hóa bước theo link thay vì giả định tên repository hoặc path.

Đối với collection/item response có dữ liệu động, dùng fixture ổn định trong môi trường test. Chuẩn hóa các giá trị không thuộc hợp đồng như host/port, ID sinh tự động, timestamp và thứ tự mảng không có cam kết thứ tự. Không xóa hoặc chuẩn hóa những khác biệt có ý nghĩa như relation, URI template, field, kiểu dữ liệu, status hoặc header.

Lưu raw response gốc song song với bản chuẩn hóa để khi diff có thể truy ngược lại dữ liệu thực tế. Không đưa token, cookie, thông tin cá nhân hoặc dữ liệu production nhạy cảm vào snapshot.

## 4. Phân loại thay đổi sau mỗi release

So sánh baseline với bản build mới và phân loại từng khác biệt:

| Thay đổi | Rủi ro với client |
|---|---|
| Xóa/đổi URI, relation hoặc query method | Cao: client không tìm thấy resource |
| Xóa field, đổi tên/kiểu field hoặc thay cấu trúc association | Cao: client parse hoặc xử lý sai |
| Tắt HTTP method hoặc thay đổi request media type | Cao: thao tác không còn thực hiện được |
| Đổi status code hoặc cấu trúc lỗi | Trung bình đến cao: logic retry/error handling có thể sai |
| Thay đổi pagination, sort, filter hoặc default size | Trung bình đến cao: dữ liệu trả về khác |
| Đổi ETag/Last-Modified hoặc điều kiện `If-Match` | Cao với client cập nhật đồng thời/cache |
| Thay đổi projection/excerpt mặc định | Cao nếu client dựa vào representation cũ |
| Thêm field, relation hoặc query method | Thường là additive, nhưng vẫn có thể ảnh hưởng client parse nghiêm ngặt |
| Siết quyền hoặc thay CORS | Có thể làm client hiện tại không gọi được API |
| Thay đổi metadata ALPS/JSON Schema | Có thể ảnh hưởng client tự khám phá hoặc sinh form |

Không tự động coi mọi khác biệt là breaking hoặc non-breaking. Hãy xét client đang dùng response theo cách nào, có dùng HAL relation hay hard-code URI, có strict schema validation không và có phụ thuộc vào default behavior không.

Với mỗi khác biệt, ghi rõ:

- Snapshot cũ và mới.
- Resource/operation bị ảnh hưởng.
- Tác động đến client và mức tương thích.
- Lý do thay đổi.
- Cách migrate hoặc thời gian deprecation.
- Người chịu trách nhiệm chấp thuận.

Nếu một thay đổi phá hợp đồng đã công bố, cân nhắc giữ alias/field cũ trong giai đoạn chuyển tiếp, thêm endpoint/representation mới hoặc phát hành phiên bản API mới theo chính sách của dịch vụ. Không âm thầm đổi contract chỉ vì dependency mới đã build thành công.

## 5. Kiểm thử hợp đồng với MockMvc

Dùng `@SpringBootTest` cùng `@AutoConfigureMockMvc` để kiểm tra toàn bộ cấu hình Spring Data REST trong application context. MockMvc thực thi request qua Spring MVC mà không cần khởi động HTTP server thật; phù hợp để xác nhận route, status, media type, HAL links và JSON body.

Ví dụ kiểm tra root và collection:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PublishedApiContractTest {

    @Autowired
    MockMvc mvc;

    @Test
    void rootPublishesOrdersAndProfileLinks() throws Exception {
        mvc.perform(get("/")
                .accept("application/hal+json"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith("application/hal+json"))
            .andExpect(jsonPath("$._links.orders.href").exists())
            .andExpect(jsonPath("$._links.profile.href").exists());
    }

    @Test
    void ordersCollectionPublishesExpectedContract() throws Exception {
        mvc.perform(get("/orders")
                .accept("application/hal+json"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.profile.href").exists())
            .andExpect(jsonPath("$._links.search").exists());
    }
}
~~~

Ví dụ giả định repository được export với relation `orders`, query method được công bố và root path không có prefix khác. Nếu ứng dụng cấu hình relation/path khác, thay các giá trị mong đợi theo contract đã chốt.

Bổ sung test cho:

- Item resource: field và association links.
- Search resource: tên query method, tham số và kiểu kết quả.
- Association resource: method và `text/uri-list` khi cập nhật liên kết.
- Projection/excerpt: field trả về cho từng lựa chọn.
- ALPS/JSON Schema: descriptor và property quan trọng.
- Content negotiation: `Accept` và `Content-Type`.
- Status code, `Location`, ETag và conditional request.
- Anonymous/user/role khác nhau: quyền đọc, tạo, sửa và xóa.
- Request lỗi: validation, not found, unsupported method và access denied.

Không chỉ kiểm tra endpoint trả `200`. Một response `200` vẫn có thể đã mất relation, field hoặc metadata mà client cần.

Với test tạo/sửa dữ liệu, dùng fixture có khóa duy nhất và cleanup/rollback theo transaction boundary. Nếu dùng `RANDOM_PORT`, request client và server chạy trong thread/transaction riêng; `@Transactional` trên test không tự rollback thao tác server. Khi cần xác nhận behavior qua server thật, dùng cleanup độc lập cho dữ liệu đã commit.

## 6. Kiểm thử khác biệt qua pipeline release

Một pipeline kiểm tra bề mặt API có thể chạy theo trình tự:

1. Build ứng dụng với dependency và cấu hình dự kiến phát hành.
2. Khởi động ứng dụng trong profile kiểm thử với database/fixture cô lập.
3. Chờ health check và xác nhận đúng build/version đang chạy.
4. Thu thập root, collection, search, profile, ALPS, JSON Schema và các response mẫu.
5. Chuẩn hóa dữ liệu động, giữ nguyên các thuộc tính thuộc hợp đồng.
6. So sánh snapshot mới với baseline đã phát hành.
7. Chạy MockMvc contract tests, integration tests và security tests.
8. Tạo báo cáo khác biệt, yêu cầu owner API duyệt các thay đổi có rủi ro.
9. Chỉ cập nhật baseline sau khi release mới được chấp thuận.

Có thể dùng script `curl`/JSON parser trong CI để tạo snapshot. Nếu dự án có OpenAPI document do thư viện riêng sinh ra, có thể thêm bước diff OpenAPI. Spring Data REST cung cấp HAL và metadata ALPS/JSON Schema; không mặc định rằng nó tự sinh OpenAPI cho mọi repository.

Lệnh chạy test minh họa:

~~~bash
./mvnw test
./gradlew test
~~~

Nếu dự án dùng Maven/Gradle wrapper, chọn lệnh tương ứng và profile kiểm thử của dự án. Thêm bước chạy contract snapshot trong pipeline phát hành thay vì chỉ chạy unit test.

## 7. Checklist trước khi chấp thuận release

- [ ] Đã ghi lại Spring Boot, Spring Framework, Spring Data release train và Spring Data REST version.
- [ ] Đã đọc upgrade notes/release notes của mọi release train nằm giữa phiên bản cũ và mới.
- [ ] Đã chạy ứng dụng bằng đúng profile/cấu hình dự kiến triển khai.
- [ ] Root HAL links và các repository relation đã được so sánh.
- [ ] Collection, item, association và search resource đã được kiểm tra.
- [ ] HTTP method, media type, query parameter, status và header đã được so sánh.
- [ ] Field, kiểu dữ liệu, association, projection và excerpt đã được so sánh.
- [ ] ALPS và JSON Schema đã được lưu và diff.
- [ ] Quyền truy cập và response lỗi đã được kiểm tra theo role.
- [ ] Các khác biệt đã được phân loại, giải thích và chấp thuận.
- [ ] Contract tests và pipeline snapshot đều pass.
- [ ] Baseline mới chỉ được cập nhật sau khi thay đổi được duyệt.

## 8. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Một collection relation biến mất | Repository không còn được phát hiện/export hoặc đổi `exported` | Kiểm tra repository interface, package scan, `@RepositoryRestResource` và root HAL |
| Collection còn nhưng `POST`/`PUT` trả `405` | Repository method bị thiếu hoặc export bị tắt | Kiểm tra method tương ứng và `@RestResource(exported = false)` |
| Search link biến mất | Query method không được export hoặc tên/path thay đổi | Kiểm tra repository method, annotation `@RestResource` và response `/search` |
| Field JSON biến mất/đổi cấu trúc | Projection, excerpt, Jackson config hoặc model thay đổi | So sánh item/collection response và ALPS |
| Collection khác item | Excerpt projection chỉ được áp dụng mặc định cho dữ liệu nhúng | Kiểm tra `excerptProjection` và gọi item trực tiếp |
| Schema/ALPS khác nhưng CRUD vẫn chạy | Metadata hoặc projection descriptor thay đổi | Theo `profile` link, kiểm tra `Accept` header và diff descriptor |
| URI trả về có host/path sai | Base path, servlet context path, proxy forwarded headers hoặc cấu hình link | Kiểm tra root links trong môi trường triển khai và cấu hình proxy |
| Test pass nhưng client production lỗi | Test dùng mock thiếu security/proxy/container hoặc fixture không giống thực tế | Thêm integration test qua live server/ingress cho phần phụ thuộc hạ tầng |
| Snapshot thay đổi ở mọi lần chạy | ID, timestamp, host, thứ tự hoặc dữ liệu fixture không ổn định | Cô lập fixture và chuẩn hóa đúng các giá trị động |
| Nâng dependency làm nhiều module lệch phiên bản | Tự quản lý version riêng thay vì dùng release train BOM | Kiểm tra dependency tree và BOM đang import |

Khi gặp khác biệt, giữ lại request, response, header, phiên bản và cấu hình đã tạo ra nó. Điều đó giúp tái hiện lỗi và phân biệt thay đổi contract thật với khác biệt do môi trường.

## Tài liệu chính thức

- [Spring Data REST Reference](https://docs.spring.io/spring-data/rest/reference/): tổng quan tính năng, repository resources, representations, conditionals, metadata, security và customization.
- [Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): resource collection/item/association/search, method exposure, media type và status code.
- [Metadata: ALPS and JSON Schema](https://docs.spring.io/spring-data/rest/reference/metadata.html): profile link, ALPS descriptor, projection metadata và JSON Schema.
- [Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html): projection, excerpt projection và tác động đến representation.
- [Upgrading Spring Data](https://docs.spring.io/spring-data/rest/reference/introduction/upgrade.html): hướng dẫn nâng cấp và yêu cầu xem release notes của các phiên bản trung gian.
- [Spring Data release notes and supported versions](https://github.com/spring-projects/spring-data-commons/wiki): release train, phiên bản hỗ trợ và release notes.
- [Spring Data dependencies and release train BOM](https://docs.spring.io/spring-data/rest/reference/data-commons/dependencies.html): chọn các phiên bản Spring Data tương thích bằng BOM.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest`, mock/live web environment và transaction boundary.
- [Spring Framework — MockMvc](https://docs.spring.io/spring/reference/testing/mockmvc.html): kiểm thử request/response Spring MVC mà không cần server thật.
- [Spring Framework — Spring MVC Test](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): setup, assertion và các giới hạn của MockMvc.
