# Đối chiếu thay đổi API, annotation và mặc định cấu hình khi nâng cấp

## Mục tiêu

Khi nâng cấp Spring Boot, Spring Data hoặc Spring Data REST, thay đổi không chỉ nằm ở dependency. Phiên bản mới có thể đổi API Java, annotation, cách cấu hình, media type, metadata HAL/ALPS, hành vi phân trang, validation, event hoặc cách request được bảo vệ. Một ứng dụng vẫn biên dịch được chưa chắc giữ nguyên hợp đồng HTTP mà client đang sử dụng.

Mục tiêu của việc đối chiếu là xác định rõ ba lớp thay đổi:

- **API công khai:** URL, HTTP method, status code, header, media type, HAL link, projection và cấu trúc response.
- **API lập trình:** package, method signature, annotation, interface mở rộng và event handler.
- **Mặc định runtime:** giá trị cấu hình, transaction, serialization, security và hành vi repository.

Không suy luận thay đổi chỉ từ số phiên bản major. Hãy so sánh đúng phiên bản nguồn và đích đang có trong build, đọc release notes/migration guide tương ứng, sau đó xác nhận bằng test trên ứng dụng.

## Xác định chính xác phiên bản nguồn và đích

Trước khi sửa code, ghi lại phiên bản thực tế của:

- Spring Boot và Spring Framework.
- Spring Data release train, Spring Data REST, Spring Data Commons và module repository đang dùng (ví dụ Spring Data JPA).
- Spring Security, Hibernate/JPA provider, Jackson và Bean Validation provider.
- JDK, Gradle hoặc Maven.

Không chỉ đọc version khai báo trong một file. Dependency management hoặc BOM có thể quyết định version cuối cùng. Với Maven, kiểm tra dependency tree:

    ./mvnw dependency:tree

Với Gradle:

    ./gradlew dependencies --configuration runtimeClasspath

Có thể kiểm tra một module cụ thể:

    ./gradlew dependencyInsight --dependency spring-data-rest-webmvc --configuration runtimeClasspath

Ghi lại kết quả trước và sau nâng cấp. Ưu tiên dùng Spring Boot dependency management để giữ các module Spring tương thích với nhau; chỉ override một module Spring Data riêng khi có lý do và đã xác minh tương thích.

## Lập bảng đối chiếu trước khi thay đổi

Tạo bảng theo từng thành phần đang được ứng dụng sử dụng:

| Thành phần | Phiên bản nguồn | Phiên bản đích | Điều cần đối chiếu |
| --- | --- | --- | --- |
| Spring Data REST | Version runtime thực tế | Version runtime mới | Repository export, REST endpoints, events, metadata |
| Spring Data Commons | Version runtime thực tế | Version runtime mới | `Pageable`, `Sort`, domain events, repository API |
| Spring Data JPA / repository module | Version runtime thực tế | Version runtime mới | Query derivation, persistence behavior, transaction |
| Spring Boot / Framework | Version runtime thực tế | Version runtime mới | Auto-configuration, property binding, bean lifecycle |
| Jackson / validation | Version runtime thực tế | Version runtime mới | JSON binding, null, unknown fields, validation |
| JPA provider / JDK | Version runtime thực tế | Version runtime mới | `javax`/`jakarta`, mapping, optimistic locking |

Đánh dấu mỗi mục là giữ nguyên, đổi tên, đổi signature, deprecated, removed hoặc đổi mặc định. Ghi thêm endpoint/client nào phụ thuộc vào hành vi đó.

## Đối chiếu annotation và extension point

Rà soát các annotation và interface mà ứng dụng dùng để expose hoặc tùy chỉnh repository:

| Thành phần | Vai trò cần xác nhận sau nâng cấp |
| --- | --- |
| `@RepositoryRestResource` | Tên collection, path, exported state, excerpt projection |
| `@RestResource` | Path, relation name và việc export method/association |
| `@Projection` | Tên projection, domain type, package được quét và metadata được công bố |
| `@Param` | Tên query parameter cho finder/search resource |
| `@RepositoryEventHandler` | Domain type mà handler nhận và handler có được đăng ký |
| `@HandleBeforeCreate`, `@HandleBeforeSave`, `@HandleBeforeDelete` | Event có chạy đúng với thao tác REST tương ứng |
| `@HandleBeforeLinkSave`, `@HandleBeforeLinkDelete` | Association event và kiểu đối tượng truyền vào handler |
| `@Version` | Optimistic locking và ETag/conditional request |

Không chỉ kiểm tra rằng annotation vẫn compile. Hãy kiểm tra endpoint hoặc event thực tế sau khi ứng dụng khởi động. Ví dụ, một repository có thể vẫn tồn tại nhưng không còn được export theo cấu hình mới; một projection có thể compile nhưng không xuất hiện trong ALPS profile.

Ví dụ cấu hình repository cần giữ hợp đồng collection path:

    @RepositoryRestResource(
        collectionResourceRel = "orders",
        path = "orders")
    public interface OrderRepository
            extends JpaRepository<Order, Long> {
    }

Kiểm tra cả relation name và path bằng cách đọc API root và collection resource. Client nên đi theo HAL `href` thay vì tự dựng URL từ tên Java repository.

## Đối chiếu `RepositoryRestConfigurer`

Ứng dụng thường dùng `RepositoryRestConfigurer` để đặt base path, pagination, media type, CORS hoặc các tùy chọn REST khác. So sánh method signature và package import với phiên bản đích; không sao chép một ví dụ cũ mà không kiểm tra compile API hiện tại.

Ví dụ triển khai interface ở các phiên bản hỗ trợ signature hai tham số:

    @Configuration
    public class RestConfiguration implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {
            config.setDefaultPageSize(25);
            config.setMaxPageSize(100);
        }
    }

Nếu phiên bản đích cung cấp overload hoặc default method khác, dùng signature trong Javadoc của chính version đó. Kiểm tra import `RepositoryRestConfigurer` và `RepositoryRestConfiguration`, vì class cùng tên hoặc package có thể khác giữa các module.

Ưu tiên implement `RepositoryRestConfigurer` thay vì tiếp tục dựa vào adapter cũ trong hướng dẫn đã lỗi thời. Sau nâng cấp, xác nhận bean configurer được Spring nạp và giá trị thực sự có hiệu lực bằng request HTTP.

## Đối chiếu cấu hình và giá trị mặc định

Kiểm tra cả property trong `application.properties`/`application.yml`, biến môi trường, profile, config server và Java config. Một property bị đổi tên hoặc không còn được bind có thể khiến ứng dụng âm thầm quay về mặc định.

Các property Spring Data REST thường cần rà soát gồm:

| Property | Hành vi cần kiểm tra |
| --- | --- |
| `spring.data.rest.base-path` | Base path của API root, collection và profile |
| `spring.data.rest.default-page-size` | Số phần tử khi client không gửi `size` |
| `spring.data.rest.max-page-size` | Giới hạn trên cho kích thước trang |
| `spring.data.rest.page-param-name` | Tên query parameter trang |
| `spring.data.rest.limit-param-name` | Tên query parameter kích thước trang |
| `spring.data.rest.sort-param-name` | Tên query parameter sắp xếp |
| `spring.data.rest.return-body-on-create` | Có trả representation sau khi tạo hay không |
| `spring.data.rest.return-body-on-update` | Có trả representation sau khi cập nhật hay không |

Đây là danh sách cần xác minh với metadata cấu hình của phiên bản Spring Boot/Spring Data REST đang dùng; không giả định mọi property có mặt hoặc có cùng semantics ở mọi version. Kiểm tra configuration metadata, release notes và kết quả runtime. Nếu giá trị ảnh hưởng API contract, đặt tường minh thay vì phụ thuộc default.

Ví dụ đặt kích thước trang rõ ràng:

    spring.data.rest.default-page-size=25
    spring.data.rest.max-page-size=100

Kiểm tra request không có `size`, request có `size` nhỏ hơn default và request vượt max. Đọc `page.size`, `totalElements`, `totalPages` và các link `next`/`prev` trong HAL response.

## Những thay đổi có thể ảnh hưởng API client

### URL và HAL links

Kiểm tra API root, collection path, item path, association path, search links và `profile` link. Thay đổi `base-path`, `collectionResourceRel` hoặc `@RestResource(path=...)` có thể làm client cũ không tìm thấy resource.

Đừng chỉ so sánh URL bằng string. Đọc HAL response và xác nhận relation, URI template, query parameter cùng các link điều hướng còn phù hợp. Nếu client được thiết kế theo HATEOAS, cập nhật cách theo link khi relation hoặc template thay đổi.

### Media type và representation

Kiểm tra `Accept` và `Content-Type` được hỗ trợ: HAL JSON, JSON thông thường, ALPS profile, JSON Patch và JSON Merge Patch nếu ứng dụng sử dụng. Xác nhận response body, `_embedded`, `_links`, `page`, error representation và header `Location`/`ETag`.

Không giả định response luôn có body sau POST hoặc PUT. Cấu hình trả body, status code và header có thể ảnh hưởng client; ghi rõ hành vi thực tế của version đích.

### Pagination và sorting

Kiểm tra default page size, max page size, tên query parameter và cú pháp `sort`. Nếu default thay đổi, client không truyền `size` có thể nhận số bản ghi khác trước. Đặt default/max tường minh và kiểm tra page metadata.

### Projection, excerpt và ALPS

Kiểm tra các projection name có còn xuất hiện trong ALPS metadata và vẫn hoạt động với `?projection=...`. Kiểm tra excerpt projection của collection, nested projection và các trường nhạy cảm. Metadata chỉ mô tả lựa chọn được công bố; authorization vẫn phải được áp dụng ở server.

### PATCH và giá trị null

Kiểm tra JSON Patch với `application/json-patch+json` và JSON Merge Patch với `application/merge-patch+json` nếu API hỗ trợ. Xác nhận semantics của field bị bỏ qua, `null`, `remove`, object lồng nhau và array. Jackson hoặc patch handler thay đổi version có thể làm khác hành vi binding; hãy đọc lại entity đã lưu trong test.

### ETag và optimistic locking

Nếu entity có `@Version`, xác nhận GET trả ETag và conditional PUT/PATCH/DELETE xử lý `If-Match` đúng. Kiểm tra request dùng ETag cũ nhận `412 Precondition Failed` và không ghi đè dữ liệu mới.

## Đối chiếu namespace `javax` và `jakarta`

Khi nâng cấp qua thế hệ Spring Framework/Spring Boot chuyển sang Jakarta EE, kiểm tra import và dependency của persistence, validation, servlet và annotation liên quan. Ví dụ:

- `javax.persistence.*` chuyển sang `jakarta.persistence.*`.
- `javax.validation.*` chuyển sang `jakarta.validation.*`.
- `javax.servlet.*` chuyển sang `jakarta.servlet.*`.

Không thay thế hàng loạt mọi chuỗi bắt đầu bằng `javax`: một số package Java SE vẫn giữ namespace `javax`, và thư viện bên thứ ba có thể còn dùng API khác. Dùng compiler, dependency tree và migration guide để xác định package nào cần chuyển.

Kiểm tra các annotation `@Entity`, `@Id`, `@Version`, `@Valid` và constraint validation đang được import từ đúng namespace mà provider/runtime đích hỗ trợ. Một annotation cùng tên nhưng đến từ namespace cũ có thể không được persistence hoặc validation provider mới nhận ra.

## Đối chiếu event và validation

Rà soát repository event handler theo đúng thao tác REST:

- `beforeCreate` cho tạo mới.
- `beforeSave` cho cập nhật.
- `beforeDelete` cho xóa.
- `beforeLinkSave` và `beforeLinkDelete` cho thay đổi association.

Kiểm tra bean name convention nếu dùng validator theo event, hoặc việc đăng ký validator qua `RepositoryRestConfigurer`. Xác nhận handler chỉ chạy trong luồng Spring Data REST tương ứng; lời gọi repository trực tiếp từ service, batch hoặc message listener không mặc nhiên đi qua REST event.

Quy tắc nghiệp vụ phải áp dụng cho mọi entry point nên nằm trong domain/service layer. REST event là lớp tích hợp cho endpoint tự động. Sau nâng cấp, test cả request HTTP lẫn service call trực tiếp để phát hiện logic bị bỏ qua.

## Đối chiếu transaction, security và CORS

Kiểm tra transaction boundary của service/repository, optimistic locking, auditing và domain event. Đặc biệt, xác nhận side effect ngoài hệ thống chỉ chạy sau commit nếu đó là yêu cầu của nghiệp vụ.

Với Spring Security, rà soát URL matcher, method security, authentication principal, CSRF và CORS. Cấu hình bảo mật có thể đổi giữa các thế hệ Spring Security; không dựa vào test cũ nếu test không còn chạy qua security filter chain.

Kiểm tra:

- Anonymous request có nhận 401 hoặc redirect theo hợp đồng API.
- User không đủ quyền nhận 403/404 và không đọc hoặc sửa được bản ghi ngoài phạm vi.
- POST/PUT/PATCH/DELETE có CSRF token hợp lệ khi CSRF protection được bật.
- CORS preflight trả allow-origin, allow-methods và allow-headers đúng.
- `ETag`/`Location` được expose nếu browser client cần đọc các header đó.

## Quy trình nâng cấp có kiểm soát

1. Ghi lại dependency tree và cấu hình runtime của version nguồn.
2. Chọn version đích theo Spring Boot BOM/release train tương thích; đọc release notes và migration guide cho đúng khoảng version.
3. Liệt kê annotation, configurer, event handler, repository custom method và endpoint mà ứng dụng sử dụng.
4. So sánh property names và defaults; đặt tường minh các giá trị có ảnh hưởng đến client.
5. Cập nhật package `javax`/`jakarta` và method signature theo API đích.
6. Biên dịch và sửa các API bị deprecated/removed theo hướng dẫn của version đích.
7. Chạy integration test qua HTTP cho HAL links, status, headers, pagination, projection, PATCH, validation và event.
8. Chạy test security cho authentication, record-level authorization, CSRF và CORS.
9. So sánh response mẫu trước/sau nâng cấp; ghi nhận khác biệt có chủ ý và cập nhật client contract.
10. Chạy smoke test trên cấu hình/profile production-like trước khi phát hành.

## Bộ kiểm thử hồi quy tối thiểu

| Khu vực | Kiểm tra trước/sau nâng cấp |
| --- | --- |
| API root | Base path, collection links và `profile` link |
| Repository export | Collection/item/search/association endpoints |
| Representation | HAL media type, `_embedded`, `_links`, error body |
| Pagination | Default/max size, page/sort parameter, metadata |
| Projection | Projection names, excerpt và nested fields |
| PATCH | JSON Patch, Merge Patch, omitted field, null và array |
| Validation/events | Create, save, delete, link và unlink handlers |
| Concurrency | `@Version`, ETag, `If-Match`, 412 |
| Security | Authentication, authorization, CSRF, CORS |
| Configuration | Property binding và giá trị runtime theo profile |

Với mỗi request ghi dữ liệu, kiểm tra cả status/header và trạng thái database sau request. Với request thất bại, xác nhận dữ liệu không bị thay đổi ngoài ý muốn. Lưu một số response HAL/ALPS đại diện làm fixture để phát hiện thay đổi hợp đồng trong lần nâng cấp sau.

## Nguyên tắc kết luận thay đổi

Không đánh dấu một hành vi là breaking change chỉ vì tài liệu cũ và mới có ví dụ khác nhau. Xác định version thực tế, kiểm tra API signature hoặc configuration metadata, chạy request trên ứng dụng và so sánh kết quả. Nếu một default không được tài liệu version đích xác nhận, ghi rõ là chưa xác minh và cấu hình tường minh để tránh phụ thuộc vào nó.

Một lần nâng cấp an toàn cần chứng minh cả ba lớp: code dùng đúng API/annotation của version đích, runtime nạp đúng cấu hình và HTTP contract mà client nhìn thấy vẫn đúng hoặc đã được thay đổi có chủ đích.