# Kiểm thử hồi quy việc công bố ngoài ý muốn khi thêm repository hoặc phương thức

## 1. Mục tiêu

Spring Data REST có thể tự động công bố repository thành REST resource. Khi dự án lớn dần, một repository mới hoặc một public method mới có thể làm API xuất hiện thêm collection, item, search endpoint hoặc association link mà nhóm phát triển không dự định công khai.

Đây là thay đổi về bề mặt API, ngay cả khi code mới chỉ được thêm để phục vụ nội bộ. Nếu không có kiểm thử hồi quy, endpoint mới có thể vô tình:

- Làm lộ entity hoặc dữ liệu nội bộ.
- Cho phép client tạo, sửa hoặc xóa dữ liệu qua CRUD method được export.
- Công bố query method thành search endpoint.
- Tạo thêm association link dẫn tới resource nhạy cảm.
- Thay đổi hợp đồng hypermedia mà client hiện tại đang sử dụng.

Bài thực hành xây dựng các kiểm thử xác nhận chính xác repository, HTTP method, search method và association link nào được phép công bố. Mục tiêu là phát hiện API surface thay đổi ngoài dự kiến ngay trong CI.

## 2. Vì sao thêm repository có thể làm API thay đổi?

Spring Data REST phát hiện repository theo repository detection strategy. Khi một repository được phát hiện và export, framework có thể tạo:

- Collection resource để đọc hoặc tạo entity.
- Item resource cho từng entity.
- Search resource nếu repository có query methods được export.
- Association resource cho các persistent association có thể liên kết.

Ví dụ repository mới:

    public interface InternalAuditRepository
            extends JpaRepository<InternalAudit, Long> {
    }

Nếu repository được phát hiện và export theo cấu hình hiện tại, nó có thể tạo endpoint collection như /internalAudits cùng các item resource. Việc developer chỉ định dùng repository từ service nội bộ không tự động khiến repository đó bị ẩn khỏi REST.

Tương tự, thêm repository public để phục vụ batch job hoặc admin task có thể làm xuất hiện endpoint mà không có controller mới nào được viết. Vì vậy, review code cần xem cả thay đổi repository interface và cấu hình export.

## 3. Repository detection strategy

Spring Data REST hỗ trợ các chiến lược phát hiện repository. Chiến lược cụ thể cần được kiểm tra theo phiên bản và cấu hình ứng dụng. Những lựa chọn phổ biến gồm:

- DEFAULT: chiến lược mặc định của Spring Data REST, áp dụng quy tắc phát hiện mặc định.
- ALL: export tất cả repository được phát hiện.
- ANNOTATED: chỉ export repository được đánh dấu bằng RepositoryRestResource, trừ repository có exported=false.
- VISIBILITY: dựa vào visibility của repository interface theo quy tắc framework.

Có thể cấu hình strategy thông qua RepositoryRestConfiguration:

    @Configuration
    public class RepositoryRestConfig
            implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {

            config.setRepositoryDetectionStrategy(
                RepositoryDetectionStrategy.RepositoryDetectionStrategies.ANNOTATED
            );
        }
    }

Với chiến lược ANNOTATED, repository cần opt-in rõ ràng:

    @RepositoryRestResource(
        collectionResourceRel = "customers",
        path = "customers"
    )
    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {
    }

Repository nội bộ không được đánh dấu vẫn có thể được inject và sử dụng bởi service, nhưng không được export theo strategy này.

Tên enum, package và behavior mặc định có thể khác giữa các thế hệ Spring Data REST. Hãy đối chiếu API của dependency thực tế trước khi áp dụng cấu hình. Regression test nên kiểm tra response root và endpoint trực tiếp, không chỉ tin rằng strategy đã được cấu hình.

## 4. Ẩn repository nội bộ bằng exported=false

Một cách opt-out tường minh là:

    @RepositoryRestResource(exported = false)
    public interface InternalAuditRepository
            extends JpaRepository<InternalAudit, Long> {
    }

Repository vẫn là bean Spring Data để service có thể sử dụng. exported=false ngăn Spring Data REST công bố repository resource tương ứng.

Nên dùng annotation này cho repository chứa dữ liệu nội bộ hoặc repository chỉ dành cho tác vụ hệ thống khi detection strategy hiện tại có thể export chúng.

Nếu dự án dùng strategy ANNOTATED, chỉ repository được đánh dấu mới được export; vẫn có thể giữ exported=false như tín hiệu rõ ràng về ý định không công khai. Hãy thống nhất quy ước trong nhóm để tránh developer thêm annotation export theo mẫu mà không đánh giá dữ liệu.

## 5. Thêm method mới cũng có thể mở rộng API

Repository method không chỉ là code nội bộ. Spring Data REST có thể công bố CRUD method và query method tùy method được khai báo, exposure configuration và annotation.

Ví dụ:

    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {

        List<Customer> findByCity(String city);

        @RestResource(exported = false)
        List<Customer> findInternalByEmail(String email);
    }

Method findByCity có thể xuất hiện trong search resource dưới relation finder tương ứng. Client có thể gọi query endpoint qua HTTP GET và truyền tham số city.

Method findInternalByEmail được đánh dấu exported=false để không công bố finder đó. Method vẫn có thể được gọi từ service hoặc code Java nội bộ.

Khi thêm một public method mới, hãy xác định:

1. Method có trở thành REST endpoint không?
2. Nó có làm xuất hiện relation mới trong search resource không?
3. Query có trả dữ liệu nhạy cảm hoặc bỏ qua tenant/owner filter không?
4. Method có cho phép thao tác ghi hoặc xóa ngoài ý muốn không?
5. Nó có cần exported=false hoặc custom security policy không?

Không coi việc method chỉ được tạo để phục vụ service nội bộ là bằng chứng nó sẽ không được export.

## 6. HTTP method exposure cũng là một phần của API contract

Một collection resource thường hỗ trợ GET và POST nếu repository cung cấp các method tương ứng. Item resource thường hỗ trợ GET, PUT, PATCH và DELETE theo CRUD method được export. Association resource có thể hỗ trợ GET, PUT, POST và DELETE tùy association cùng cấu hình.

Một thay đổi nhỏ như thêm deleteById, save hoặc một repository interface kế thừa CrudRepository có thể làm thay đổi method nào được hỗ trợ.

Có thể tắt method cụ thể bằng cách đánh dấu repository method exported=false khi phù hợp:

    @RestResource(exported = false)
    @Override
    void deleteById(Long id);

Cần kiểm tra chữ ký method và behavior với phiên bản Spring Data hiện tại. Nếu muốn quản lý exposure ở mức rộng hơn, Spring Data REST cung cấp RepositoryRestConfiguration exposure configuration để tắt HTTP method theo domain type hoặc resource type.

Regression test nên kiểm tra từng method, ví dụ:

- GET collection được phép.
- POST collection bị từ chối nếu API chỉ đọc.
- GET item được phép.
- PUT/PATCH/DELETE item bị từ chối nếu không thuộc contract.
- Search chỉ công bố finder được duyệt.
- Association mutation chỉ được bật cho relation cần thiết.

Không chỉ test GET thành công. Một endpoint có thể trông an toàn khi đọc nhưng vẫn vô tình mở PUT hoặc DELETE.

## 7. Association mới có thể làm lộ thêm link

Khi entity thêm persistent association, Spring Data REST có thể thêm relation vào HAL representation của parent resource.

Ví dụ Customer ban đầu chỉ có name và email. Sau đó developer thêm:

    @ManyToOne
    private InternalProfile internalProfile;

HAL response có thể xuất hiện link internalProfile nếu association được export và linkable. Đây là thay đổi API dù collection path của Customer không đổi.

Nếu association không nên được công khai, có thể đánh dấu:

    @ManyToOne
    @RestResource(exported = false)
    private InternalProfile internalProfile;

Regression test cần xác nhận relation nhạy cảm không xuất hiện trong _links và thử gọi trực tiếp association URL để kiểm tra endpoint không bị mở ngoài ý muốn. Ẩn link trong representation không thay thế authorization cho endpoint đích.

Khi thêm association, cũng cần xem entity đích có repository được export hay không, association path/rel có bị tùy chỉnh không và liệu client có thể theo link để đọc dữ liệu ngoài phạm vi mong đợi.

## 8. Xác định API surface mong đợi

Trước khi viết test, lập danh sách contract được phép công bố. Ví dụ:

| Resource | Được phép | Không được phép |
|---|---|---|
| /customers | GET, POST | Không mở DELETE collection |
| /customers/{id} | GET, PATCH | Không mở PUT hoặc DELETE nếu API không cho phép |
| /customers/search | Chỉ finder byCity | Không công bố finder internalByEmail |
| /customers/{id}/address | GET, PUT | Không công bố association nội bộ |
| /internalAudits | Không export | Không có collection/item/search resource |

Bảng chỉ là ví dụ. Hãy lấy danh sách từ API contract thực tế, security requirements và repository exposure configuration.

Có thể lưu expected relation names trong test để so sánh với HAL response. Khi một repository hoặc association mới xuất hiện, test thất bại vì có relation ngoài danh sách cho phép.

## 9. Kiểm thử API root để phát hiện repository mới

API root thường công bố collection resource bằng HAL links. Có thể dùng MockMvc:

    @SpringBootTest
    @AutoConfigureMockMvc
    class RepositoryExposureRegressionTest {

        @Autowired
        private MockMvc mockMvc;

        @Test
        void rootExposesOnlyApprovedRepositories()
                throws Exception {

            mockMvc.perform(get("/")
                    .accept("application/hal+json"))
                .andExpect(status().isOk())
                .andExpect(jsonPath(
                    "$._links.customers.href"
                ).exists())
                .andExpect(jsonPath(
                    "$._links.internalAudits"
                ).doesNotExist());
        }
    }

Test xác nhận collection relation customers tồn tại và internalAudits không xuất hiện trong root representation.

Nếu API dùng base path, đổi request path cho phù hợp. Nếu có profile, environment hoặc security filter khác nhau, chạy test với cấu hình gần production nhất.

Root test chỉ phát hiện relation ở entry point. Cần test thêm direct URL để bảo đảm repository không vô tình được export nhưng bị bỏ sót khỏi root do cấu hình hoặc cách assemble link đặc biệt.

## 10. Kiểm thử search resource và query method

Đọc search resource của Customer:

    mockMvc.perform(get("/customers/search")
            .accept("application/hal+json"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$._links.findByCity.href"
        ).exists())
        .andExpect(jsonPath(
            "$._links.findInternalByEmail"
        ).doesNotExist());

Nếu path hoặc rel được tùy chỉnh bằng RestResource, dùng rel/path thực tế trong assertion.

Có thể kiểm tra finder nội bộ không gọi được qua HTTP. Tùy behavior framework, endpoint không được export có thể trả 404 hoặc search relation không tồn tại; hãy assert contract đã xác nhận trên phiên bản đang dùng.

Không chỉ kiểm tra link bị ẩn. Gọi trực tiếp finder path đã biết để xác nhận server không cho thực thi query nội bộ qua REST.

## 11. Kiểm thử HTTP method exposure

Dùng MockMvc để xác nhận method không được mở ngoài ý muốn:

    @Test
    void internalRepositoryDoesNotAcceptCrudRequests()
            throws Exception {

        mockMvc.perform(get("/internalAudits")
                .accept("application/hal+json"))
            .andExpect(status().isNotFound());

        mockMvc.perform(post("/internalAudits")
                .contentType("application/json")
                .content("{\"message\":\"test\"}"))
            .andExpect(status().isNotFound());
    }

Ví dụ giả định repository hoàn toàn không được export. Nếu repository được export nhưng một method riêng bị tắt, response có thể là 405 Method Not Allowed thay vì 404. Hãy kiểm tra status theo cấu hình exposure cụ thể.

Với repository chỉ đọc, có thể kiểm tra POST/PUT/PATCH/DELETE không được phép:

    @Test
    void customerResourceDoesNotExposeDelete()
            throws Exception {

        mockMvc.perform(delete("/customers/{id}", 42L))
            .andExpect(status().isMethodNotAllowed());
    }

Không copy nguyên status ví dụ nếu project có custom exception handler hoặc exposure configuration khác. Mục tiêu là xác nhận method không thực hiện thay đổi dữ liệu.

## 12. Kiểm thử association links và endpoint trực tiếp

Đọc một Customer:

    mockMvc.perform(get("/customers/{id}", 42L)
            .accept("application/hal+json"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$._links.address"
        ).exists())
        .andExpect(jsonPath(
            "$._links.internalProfile"
        ).doesNotExist());

Sau đó thử direct URL của association nội bộ nếu path đã biết:

    mockMvc.perform(get(
            "/customers/{id}/internalProfile", 42L)
            .accept("application/hal+json"))
        .andExpect(status().isNotFound());

Nếu endpoint bị bảo vệ bằng security thay vì bị ẩn hoàn toàn, status có thể là 401 hoặc 403 theo policy. Điều quan trọng là caller không được phép không thể đọc dữ liệu chỉ bằng cách tự gõ URL.

Khi thêm association mới, kiểm tra cả parent HAL representation và endpoint association. Một link mới có thể mở ra đường dẫn tới resource mà trước đây client không thể khám phá.

## 13. Kiểm thử bằng contract snapshot có kiểm soát

Có thể lưu một bản expected list gồm:

- Relation tại API root.
- Relation trong từng item resource.
- Relation trong search resource.
- HTTP method được phép cho từng resource.
- Status dự kiến cho endpoint bị ẩn hoặc method bị cấm.

Test có thể trích key trong _links rồi so sánh tập relation với danh sách mong đợi. Khi API thay đổi có chủ đích, reviewer cập nhật contract cùng code change.

Không snapshot toàn bộ response JSON nếu response chứa ID, timestamp, ETag hoặc dữ liệu động. Nên snapshot phần API surface ổn định: relation names, href pattern, supported methods và status behavior.

Nếu dùng snapshot file, giữ nội dung nhỏ và dễ review. Không tự động chấp nhận snapshot mới trong CI; việc cập nhật expected contract cần review như một API change.

## 14. Phân biệt API exposure với authorization

Repository không export, association link không xuất hiện và endpoint bị Spring Security từ chối là ba trạng thái khác nhau:

- Export configuration quyết định Spring Data REST có tạo resource/HTTP method hay không.
- Association configuration quyết định relation và association resource có được công bố hay không.
- Spring Security quyết định caller có quyền truy cập endpoint hay không.

Một link biến mất không chứng minh endpoint đích đã được bảo vệ. Một repository bị ẩn cũng không bảo vệ custom controller hoặc service khác trả cùng dữ liệu.

Regression suite nên kiểm tra:

1. Resource/relation có được công bố đúng không.
2. HTTP method có được bật đúng không.
3. Caller thiếu quyền có bị từ chối khi gọi direct URL không.
4. Caller có quyền vẫn truy cập được các resource hợp lệ không.

Không dùng 404, 403 hoặc link omission thay thế lẫn nhau nếu API contract có ý nghĩa riêng cho từng trường hợp.

## 15. Tổ chức regression suite trong CI

Nên chia test thành các nhóm nhỏ:

**Repository exposure tests**

Kiểm tra API root chỉ công bố các repository được duyệt và repository nội bộ không có collection/item/search resource.

**Method exposure tests**

Kiểm tra GET/POST/PUT/PATCH/DELETE theo contract của collection, item và association resource.

**Search exposure tests**

Kiểm tra query finder công khai xuất hiện trong search resource; finder nội bộ bị ẩn và direct URL không thực thi.

**Association exposure tests**

Kiểm tra HAL links đúng danh sách; association mới không làm lộ entity nội bộ.

**Authorization tests**

Kiểm tra caller anonymous, thiếu authority và có authority đối với các URL trực tiếp.

**Persistence safety tests**

Sau request không được phép, kiểm tra repository/database không có thay đổi. Điều này tránh test chỉ pass vì response status nhưng dữ liệu vẫn bị ghi.

Chạy các test này trong CI mỗi khi repository interface, entity association, RepositoryRestConfigurer, security configuration hoặc dependency Spring Data REST thay đổi.

## 16. Ví dụ checklist review cho thay đổi repository

Khi pull request thêm repository hoặc method, reviewer có thể kiểm tra:

1. Repository mới có thực sự cần export qua REST không?
2. Nếu cần export, collection path và rel đã được đặt rõ ràng chưa?
3. Nếu không cần export, repository có exported=false hoặc detection strategy phù hợp không?
4. Public query method mới có xuất hiện trong search resource không?
5. CRUD method mới có làm mở thêm POST/PUT/PATCH/DELETE không?
6. Association mới có xuất hiện trong HAL _links không?
7. Có field hoặc association chứa dữ liệu nội bộ/PII không?
8. Security rule có bao phủ collection, item, search và association endpoint không?
9. Integration test có kiểm tra direct URL không?
10. API contract hoặc snapshot có được cập nhật có chủ đích không?

Checklist giúp reviewer nhận diện thay đổi API ngay cả khi diff chủ yếu nằm ở repository interface hoặc entity mapping.

## 17. Lỗi thường gặp

**Chỉ kiểm tra controller mới**

Spring Data REST tạo endpoint từ repository metadata; không cần controller mới để API surface thay đổi.

**Giả định repository nội bộ không được export**

Một repository public có thể được detection strategy hiện tại phát hiện. Kiểm tra strategy và root links.

**Quên query method**

Thêm finder có thể làm xuất hiện relation trong search resource. Kiểm tra cả link và direct finder URL.

**Chỉ kiểm tra link, không kiểm tra endpoint**

Link bị ẩn không tự động bảo vệ URL. Gửi request trực tiếp trong test.

**Chỉ kiểm tra GET**

Repository method exposure có thể thay đổi method ghi/xóa. Kiểm tra POST, PUT, PATCH và DELETE.

**Bỏ qua association mới**

Thêm persistent property có thể làm HAL representation xuất hiện link mới. Kiểm tra _links của item.

**Test chỉ assert status**

Một response lỗi không đảm bảo dữ liệu không bị thay đổi. Kiểm tra repository/database sau request.

**Tự động cập nhật snapshot**

Snapshot mới có thể vô tình hợp thức hóa endpoint nhạy cảm. Yêu cầu review cho thay đổi API surface.

**Chạy test với cấu hình khác production**

Repository detection, base path, security và profile có thể khác giữa môi trường. Dùng cấu hình test phản ánh production.

## 18. Bài tập thực hành

Với CustomerRepository được export và InternalAuditRepository chỉ dùng nội bộ:

1. Cấu hình repository detection strategy hiện tại và ghi nhận behavior.
2. Tạo InternalAuditRepository mới; chạy test API root và xác nhận repository không xuất hiện.
3. Đánh dấu repository nội bộ exported=false hoặc chuyển sang detection strategy yêu cầu opt-in.
4. Thêm finder findByCity và xác nhận search relation xuất hiện đúng.
5. Thêm finder findInternalByEmail với exported=false; xác nhận finder không xuất hiện và direct URL không thực thi.
6. Thêm association InternalProfile vào Customer; xác nhận relation không xuất hiện nếu association không được export.
7. Thêm một public CRUD method hoặc override method; kiểm tra HTTP method exposure thay đổi ra sao.
8. Viết test cho GET/POST/PUT/PATCH/DELETE theo contract.
9. Thử caller không có authority gọi trực tiếp collection, item, search và association URL.
10. Kiểm tra database không thay đổi sau request bị từ chối.
11. Tạo một expected relation set và so sánh với API root/search/item HAL links.
12. Chạy toàn bộ regression suite trong CI.

Câu hỏi tự kiểm tra:

- Vì sao thêm repository có thể làm REST API thay đổi dù không thêm controller?
- RepositoryDetectionStrategy ảnh hưởng thế nào tới export?
- Vì sao query method mới có thể xuất hiện trong search resource?
- exported=false trên repository khác exported=false trên method/association như thế nào?
- Vì sao cần test cả HAL relation và direct URL?
- Làm sao phát hiện CRUD method mới được công bố ngoài ý muốn?
- Vì sao snapshot API surface cần review thủ công?
- Tại sao cần kiểm tra trạng thái persistence sau request bị từ chối?

## 19. Ghi nhớ

- Spring Data REST có thể tự động tạo collection, item, search và association resource từ repository metadata.
- Thêm repository hoặc public method có thể làm API surface thay đổi.
- Repository detection strategy quyết định repository nào được phát hiện và export.
- Dùng RepositoryRestResource và exported=false để thể hiện ý định công bố rõ ràng.
- Query method có thể xuất hiện trong search resource; kiểm tra cả relation và direct endpoint.
- CRUD method exposure ảnh hưởng HTTP methods được hỗ trợ.
- Association mới có thể thêm relation vào HAL _links.
- Kiểm thử API root, item, search, association và từng HTTP method.
- Link bị ẩn không thay thế authorization; kiểm tra URL trực tiếp.
- Regression test phải xác nhận dữ liệu không thay đổi sau request bị từ chối.
- Cập nhật API snapshot là thay đổi contract cần review.

## Tài liệu tham khảo

- Spring Data REST Reference — Repository resources and repository method exposure: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST Reference — Getting started and repository detection: https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html
- Spring Data REST Reference — Customizing repository exposure and supported methods: https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html
- Spring Security Reference — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
