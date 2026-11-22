# Phân biệt ẩn tài nguyên, ẩn liên kết và thực thi kiểm tra quyền

## 1. Mục tiêu

Spring Data REST có nhiều cách kiểm soát phần API được công bố. Ba khái niệm thường bị nhầm lẫn là:

- **Ẩn tài nguyên (repository/resource export):** quyết định repository resource có được Spring Data REST công bố hay không.
- **Ẩn liên kết (association export):** quyết định một association có được công bố thành relation và endpoint hypermedia hay không.
- **Kiểm tra quyền (authorization):** quyết định một caller cụ thể có được phép thực hiện request hay không.

Ba cơ chế này giải quyết các câu hỏi khác nhau. Một link không xuất hiện trong HAL không chứng minh endpoint đích đã được bảo vệ. Một repository không được export qua Spring Data REST cũng không tự động bảo vệ controller tùy chỉnh hoặc service khác truy cập cùng dữ liệu. Authorization phải được thực thi ở ranh giới request hoặc tại lớp nghiệp vụ phù hợp.

Bài này trình bày cách ẩn repository, ẩn association link, cấu hình Spring Security và kiểm thử các đường truy cập trực tiếp để tránh lộ dữ liệu.

## 2. Ẩn repository resource

Spring Data REST mặc định có thể phát hiện và export repository trong phạm vi cấu hình. Khi một repository không nên trở thành REST resource, có thể đánh dấu repository bằng @RepositoryRestResource(exported = false):

    @RepositoryRestResource(exported = false)
    public interface InternalProfileRepository
            extends JpaRepository<InternalProfile, Long> {
    }

Repository này vẫn có thể được inject và sử dụng bên trong ứng dụng Spring. Annotation exported=false ngăn Spring Data REST công bố các repository resource tương ứng qua REST exporter.

Khi repository bị ẩn, client không thể khám phá collection resource, item resource hoặc search resource của repository đó thông qua cơ chế export tương ứng. Tuy nhiên, điều này không có nghĩa dữ liệu đã được bảo vệ ở mọi nơi:

- Một controller tùy chỉnh vẫn có thể trả dữ liệu từ repository.
- Một service khác vẫn có thể đọc hoặc thay đổi entity.
- Một API khác hoặc một ứng dụng khác có thể truy cập cùng database.
- Một association từ repository khác cần được kiểm tra riêng để biết nó có còn được export hay không.

Ẩn repository là quyết định về bề mặt API do Spring Data REST tạo ra, không phải thay thế cho authorization.

## 3. Ẩn một association link

Giả sử Customer có quan hệ tới InternalProfile:

    @Entity
    public class Customer {

        @Id
        @GeneratedValue
        private Long id;

        private String name;

        @ManyToOne
        @RestResource(exported = false)
        private InternalProfile internalProfile;
    }

@RestResource(exported = false) trên association yêu cầu Spring Data REST không export association resource đó. Relation tương ứng sẽ không được công bố như một link có thể theo từ Customer representation.

Cần phân biệt điều này với việc ẩn toàn bộ repository InternalProfile. Nếu InternalProfileRepository vẫn được export, client có thể vẫn truy cập collection hoặc item resource của InternalProfile qua endpoint repository độc lập, tùy cấu hình và quyền. Việc ẩn link từ Customer không tự động làm endpoint repository đích biến mất.

Ngược lại, nếu repository đích bị ẩn nhưng association vẫn được cấu hình export, khả năng tạo và resolve association link còn phụ thuộc metadata, repository export và phiên bản Spring Data REST. Khi muốn loại bỏ quan hệ khỏi API, hãy cấu hình association export rõ ràng và kiểm tra representation thực tế.

## 4. Ẩn query method khỏi search resource

Query method của repository có thể được công bố trong search resource. Nếu một finder chỉ dành cho xử lý nội bộ, có thể ẩn riêng method:

    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {

        @Query("select c from Customer c where c.email = :email")
        @RestResource(exported = false)
        Optional<Customer> findInternalByEmail(
            @Param("email") String email
        );
    }

Method vẫn là một phần của repository API dùng bên trong ứng dụng, nhưng Spring Data REST không công bố finder đó như một search link.

Cần kiểm tra cả search resource sau khi cấu hình. Việc link finder biến mất là bằng chứng endpoint finder không còn được công bố theo cấu hình đó; nó không thay thế kiểm tra quyền cho những endpoint khác trả cùng dữ liệu.

## 5. Ẩn liên kết không phải là bảo mật

HAL giúp client khám phá những bước tiếp theo bằng các relation trong _links. Nếu một relation không xuất hiện, client tuân theo hypermedia sẽ không nhìn thấy đường đi đó từ representation hiện tại.

Tuy nhiên, một người dùng vẫn có thể thử gọi URL trực tiếp nếu biết hoặc đoán được đường dẫn. URL có thể xuất hiện trong log, tài liệu, lịch sử trình duyệt, response khác hoặc được suy ra từ ứng dụng. Vì vậy:

- Không dùng việc giấu link như một cơ chế phân quyền.
- Không coi URL khó đoán là biện pháp bảo vệ dữ liệu.
- Không cho rằng client không nhìn thấy link đồng nghĩa server từ chối request.
- Kiểm tra trực tiếp endpoint association và repository resource bằng một request độc lập.

Ví dụ: nếu Customer response không còn link internalProfile, vẫn cần thử GET endpoint InternalProfile bằng một caller không có quyền. Nếu endpoint đích vẫn trả dữ liệu nhạy cảm, vấn đề nằm ở export hoặc authorization của endpoint đó.

## 6. Thực thi authorization bằng Spring Security

Spring Security kiểm tra caller có được phép truy cập endpoint hay không. Có thể cấu hình quy tắc theo URL bằng SecurityFilterChain.

Ví dụ minh họa: chỉ người dùng có authority customer:read mới được GET Customer resource; chỉ authority customer:write mới được thay đổi Customer:

    @Configuration
    @EnableWebSecurity
    public class SecurityConfig {

        @Bean
        SecurityFilterChain securityFilterChain(
                HttpSecurity http) throws Exception {

            return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers(
                        HttpMethod.GET,
                        "/customers/**"
                    ).hasAuthority("customer:read")
                    .requestMatchers(
                        HttpMethod.POST,
                        "/customers/**"
                    ).hasAuthority("customer:write")
                    .requestMatchers(
                        HttpMethod.PUT,
                        "/customers/**"
                    ).hasAuthority("customer:write")
                    .requestMatchers(
                        HttpMethod.PATCH,
                        "/customers/**"
                    ).hasAuthority("customer:write")
                    .requestMatchers(
                        HttpMethod.DELETE,
                        "/customers/**"
                    ).hasAuthority("customer:delete")
                    .anyRequest().authenticated()
                )
                .build();
        }
    }

Các URL và authority trên chỉ là ví dụ. Điều chỉnh matcher theo base path, repository path, association endpoint, search endpoint và các route tùy chỉnh của ứng dụng. Nếu API dùng HTTP Basic, form login, OAuth2 Resource Server hoặc session, cấu hình authentication phù hợp với cơ chế đó.

Không sao chép cấu hình CSRF một cách máy móc. Ứng dụng dùng session/cookie và ứng dụng API stateless có yêu cầu khác nhau. Hãy cấu hình CSRF theo cách xác thực và threat model thực tế, đồng thời kiểm thử các thao tác ghi.

Quy tắc URL là lớp kiểm soát ở HTTP boundary. Nó phù hợp để giới hạn một nhóm endpoint theo method và path, nhưng có thể chưa đủ khi quyền phụ thuộc vào owner, tenant hoặc trạng thái của từng entity.

## 7. Authorization theo đối tượng và quy tắc nghiệp vụ

Có trường hợp hai người dùng đều được GET /customers nhưng chỉ được xem những Customer thuộc tenant của mình. Một matcher URL đơn giản không thể quyết định quyền dựa trên nội dung entity.

Khi cần kiểm tra theo đối tượng:

- Lấy danh tính caller từ SecurityContext.
- Xác định owner hoặc tenant của entity.
- Kiểm tra quyền tại service hoặc repository operation thực sự được gọi.
- Từ chối request nếu caller không có quyền.
- Áp dụng kiểm tra cho cả đọc, cập nhật, xóa và association operation.

Có thể bật method security và dùng @PreAuthorize trên service:

    @Configuration
    @EnableMethodSecurity
    public class MethodSecurityConfig {
    }

    @Service
    public class CustomerService {

        @PreAuthorize(
            "@customerAccess.canRead(authentication, #customerId)"
        )
        public Customer getCustomer(Long customerId) {
            return customerRepository.findById(customerId)
                .orElseThrow();
        }
    }

customerAccess là bean nghiệp vụ kiểm tra caller có quyền đọc customerId hay không. Ví dụ chỉ có hiệu lực nếu request thực sự đi qua CustomerService.getCustomer. Nếu Spring Data REST gọi repository trực tiếp, annotation trên một service không được gọi sẽ không bảo vệ endpoint đó.

Với repository resource được export trực tiếp, hãy đặt kiểm soát tại HTTP authorization layer hoặc tại method/repository/service thực sự được Spring Data REST gọi, rồi xác nhận bằng integration test. Không cho rằng thêm @PreAuthorize vào một service bất kỳ sẽ tự động chặn mọi đường truy cập repository.

Cần kiểm tra quyền trên association resource riêng. Caller có thể được phép đọc Customer nhưng không được phép đọc InternalProfile hoặc Orders. Quyền trên parent resource không nhất thiết đồng nghĩa quyền trên mọi resource liên quan.

## 8. Kết hợp ba cơ chế

Có thể xem ba cơ chế theo mục đích:

| Cơ chế | Câu hỏi được giải quyết | Ví dụ |
|---|---|---|
| Repository export | Spring Data REST có công bố repository thành REST resource không? | @RepositoryRestResource(exported = false) |
| Association export | Relation/association endpoint có được công bố không? | @RestResource(exported = false) trên association |
| Authorization | Caller hiện tại có được phép gọi endpoint không? | Spring Security request matcher hoặc method security |

Một cấu hình an toàn thường dùng cả ba theo nhu cầu:

1. Chỉ export repository cần thiết cho API.
2. Chỉ export association và finder phù hợp với hợp đồng API.
3. Áp dụng authentication và authorization cho mọi endpoint được export.
4. Kiểm tra quyền theo object/tenant ở nơi có đủ thông tin nghiệp vụ.
5. Kiểm thử các endpoint trực tiếp, không chỉ kiểm tra HAL response.

Ẩn resource/link giúp thu nhỏ bề mặt API và đơn giản hóa khả năng khám phá. Authorization là lớp quyết định request được phép hay bị từ chối.

## 9. HTTP 401, 403 và 404

Khi Spring Security từ chối request, status phụ thuộc trạng thái authentication và chính sách ứng dụng:

- **401 Unauthorized:** caller chưa được xác thực hoặc thông tin xác thực không hợp lệ; client cần xác thực.
- **403 Forbidden:** caller đã được xác thực nhưng không có quyền thực hiện thao tác.
- **404 Not Found:** resource không tồn tại, hoặc ứng dụng chủ động dùng 404 để không tiết lộ sự tồn tại của resource mà caller không được phép biết.

Không nên đổi mọi lỗi authorization thành 404 nếu API contract yêu cầu 403. Ngược lại, một số hệ thống đa tenant chọn 404 cho resource thuộc tenant khác để tránh xác nhận ID đó tồn tại. Đây là quyết định bảo mật và hợp đồng API cần nhất quán.

Một lỗi 401/403 không chứng minh repository hoặc association đã bị ẩn; nó chứng minh request hiện tại bị từ chối theo security policy. Tương tự, 404 không đủ để kết luận resource không được export nếu có thể do ID hoặc path sai.

## 10. Kiểm thử ẩn resource, ẩn link và quyền truy cập

Nên kiểm thử từng cơ chế riêng để biết chính xác lớp nào đang hoạt động.

**Kiểm tra repository bị ẩn**

- GET collection path của repository.
- GET item path nếu biết URI.
- GET search path.
- Xác nhận Spring Data REST không công bố resource tương ứng theo cấu hình.
- Nếu có custom controller cùng dữ liệu, kiểm tra route đó riêng.

**Kiểm tra association link bị ẩn**

- GET parent resource với HAL Accept header.
- Xác nhận relation không xuất hiện trong _links.
- Thử gọi trực tiếp association URL bằng một request độc lập.
- Thử gọi repository endpoint đích nếu repository đó vẫn được export.

**Kiểm tra authorization**

- Gửi request không có credentials.
- Gửi request bằng user đã xác thực nhưng thiếu authority.
- Gửi request bằng user có authority phù hợp.
- Lặp lại với GET, POST, PUT/PATCH, DELETE, search và association endpoint.
- Thử gọi trực tiếp href đích dù parent response không công bố link.
- Thử truy cập resource thuộc tenant hoặc owner khác.

Không chỉ kiểm tra rằng link đã biến mất. Test cần xác nhận server từ chối request trực tiếp nếu caller không có quyền.

## 11. Ví dụ integration test với MockMvc

Một test có thể xác nhận caller thiếu quyền đọc Customer bị từ chối:

    @SpringBootTest
    @AutoConfigureMockMvc
    class CustomerAuthorizationTest {

        @Autowired
        private MockMvc mockMvc;

        @Test
        @WithMockUser(authorities = "customer:write")
        void userWithoutReadAuthorityCannotGetCustomer()
                throws Exception {

            mockMvc.perform(get("/customers/42")
                    .accept("application/hal+json"))
                .andExpect(status().isForbidden());
        }

        @Test
        @WithMockUser(authorities = "customer:read")
        void userWithReadAuthorityCanGetCustomer()
                throws Exception {

            mockMvc.perform(get("/customers/42")
                    .accept("application/hal+json"))
                .andExpect(status().isOk());
        }
    }

Ví dụ giả định security policy ở trên và Customer 42 tồn tại. Nếu ứng dụng dùng role thay vì authority, điều chỉnh @WithMockUser và matcher tương ứng.

Có thể kiểm tra association link bị ẩn:

    mockMvc.perform(get("/customers/42")
            .accept("application/hal+json"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$._links.internalProfile"
        ).doesNotExist());

Sau đó cần một test riêng gọi trực tiếp endpoint đích với user không có quyền. Assertion link không tồn tại chỉ kiểm tra representation; nó không kiểm tra authorization.

Khi test 401, 403 hoặc 404, dùng đúng authentication setup và policy của ứng dụng. Với một số cấu hình, request không credentials có thể được redirect tới login thay vì trả 401; API resource server thường cấu hình response khác form login.

## 12. Lỗi thường gặp

**Dùng exported=false thay cho security**

Annotation export điều khiển bề mặt Spring Data REST. Nó không bảo vệ controller tùy chỉnh, service khác hoặc database.

**Ẩn link nhưng để endpoint đích mở**

Client không nhìn thấy link vẫn có thể gọi URL trực tiếp. Bảo vệ endpoint đích bằng authorization và kiểm thử trực tiếp.

**Ẩn repository nhưng quên custom endpoint**

Repository không còn được REST exporter công bố, nhưng controller hoặc route khác có thể vẫn trả cùng dữ liệu. Kiểm kê và bảo vệ tất cả đường truy cập.

**Nhầm rel với repository path**

Association rel là tên quan hệ trong HAL; repository path là URL collection/item. Hai tên có thể được tùy chỉnh độc lập.

**Chỉ kiểm tra GET**

Quyền đọc không đồng nghĩa quyền ghi hoặc xóa. Kiểm tra từng HTTP method và các association mutation endpoint.

**Chỉ bảo vệ parent resource**

Caller có thể được phép đọc Customer nhưng không được phép đọc profile, payment hoặc dữ liệu nhạy cảm liên quan. Kiểm tra quyền cho resource đích.

**Dựa vào giao diện client**

Ẩn nút hoặc bỏ link trong UI không ngăn request HTTP. Server phải tự thực thi authorization.

**Không kiểm thử tenant/owner**

Quyền theo role có thể chưa đủ. Kiểm tra caller truy cập ID thuộc tenant khác hoặc owner khác.

## 13. Bài tập thực hành

Với Customer và InternalProfile:

1. Tạo InternalProfileRepository và đánh dấu repository exported=false.
2. GET collection path và search path để xác nhận repository không được Spring Data REST công bố.
3. Tạo association Customer.internalProfile và đánh dấu @RestResource(exported = false).
4. GET Customer HAL representation và xác nhận relation internalProfile không xuất hiện trong _links.
5. Nếu InternalProfile vẫn có một custom controller hoặc endpoint khác, thử truy cập endpoint đó trực tiếp.
6. Cấu hình SecurityFilterChain để yêu cầu customer:read cho GET và customer:write cho thao tác ghi.
7. Gửi request không xác thực, request thiếu authority và request có authority phù hợp.
8. Kiểm thử association endpoint và item URL trực tiếp, kể cả khi link đã bị ẩn.
9. Bật method security cho một service có kiểm tra owner/tenant và xác nhận request đi qua đúng service.
10. Viết MockMvc test cho 401/403 theo security configuration thực tế.
11. Xác nhận một user không thể đọc hoặc thay đổi resource thuộc tenant khác.

Câu hỏi tự kiểm tra:

- @RepositoryRestResource(exported = false) tác động tới phần nào của API?
- @RestResource(exported = false) trên association khác ẩn repository đích thế nào?
- Vì sao link không xuất hiện không có nghĩa endpoint đã được bảo vệ?
- Khi nào dùng request matcher và khi nào cần kiểm tra quyền theo object?
- 401, 403 và 404 khác nhau thế nào trong authorization flow?
- Vì sao phải kiểm thử URL trực tiếp và mọi HTTP method?

## 14. Ghi nhớ

- Repository export quyết định Spring Data REST có công bố repository resource hay không.
- Association export quyết định relation/association endpoint có được công bố hay không.
- Authorization quyết định caller hiện tại có được phép thực hiện request hay không.
- @RepositoryRestResource(exported = false) ẩn repository resource khỏi REST exporter.
- @RestResource(exported = false) có thể ẩn association hoặc query method tương ứng.
- Ẩn link không bảo vệ endpoint đích; client vẫn có thể gọi URL trực tiếp.
- Dùng Spring Security ở HTTP boundary và method/service security cho quy tắc nghiệp vụ theo owner hoặc tenant.
- Kiểm tra riêng quyền trên parent, association, item, collection và search endpoint.
- Kiểm thử cả request không credentials, thiếu quyền và có quyền.
- Không dựa vào UI, URL khó đoán hoặc link bị ẩn để bảo vệ dữ liệu.

## Tài liệu tham khảo

- Spring Data REST Reference — Configuring repository exposure: https://docs.spring.io/spring-data/rest/reference/
- Spring Data REST Reference — Hiding repository and association resources: https://docs.spring.io/spring-data/rest/reference/
- Spring Security Reference — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security Reference — Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
