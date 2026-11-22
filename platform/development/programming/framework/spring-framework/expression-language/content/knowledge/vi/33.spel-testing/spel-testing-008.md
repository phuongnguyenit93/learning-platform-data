# Kiểm thử expression dùng trong annotation của Spring

Spring sử dụng Spring Expression Language (SpEL) trong nhiều annotation để đánh giá giá trị hoặc quyết định hành vi tại runtime. Ví dụ, `@Value` có thể inject giá trị từ expression; Spring Security dùng `@PreAuthorize` và `@PostAuthorize` để kiểm tra quyền; các annotation khác của Spring cũng có thể có expression context riêng.

Khi kiểm thử, cần chạy expression qua đúng hạ tầng đã xử lý annotation trong ứng dụng. Một bài test chỉ gọi `parseExpression()` chứng minh parser chấp nhận cú pháp, nhưng không chứng minh annotation được cấu hình đúng, tham số được bind đúng hoặc quyền được áp dụng đúng khi method được gọi.

## 1. Xác định annotation và thời điểm expression được đánh giá

Trước khi viết test, hãy xác định framework nào xử lý annotation và expression được đánh giá ở thời điểm nào.

| Vị trí dùng expression | Thời điểm kiểm thử phù hợp |
|---|---|
| `@Value("#{...}")` | Khi Spring tạo bean và inject giá trị |
| `@PreAuthorize` | Khi lời gọi method đi qua method-security interceptor |
| `@PostAuthorize` | Sau khi method trả về kết quả |
| `@PreFilter` | Trước khi method nhận collection đầu vào |
| `@PostFilter` | Sau khi method tạo collection kết quả |
| SpEL gọi trực tiếp trong Java | Khi test gọi `getValue()` với EvaluationContext |

Các annotation có thể dùng expression handler, root object, biến và quy tắc phân giải khác nhau. Không giả định một expression chạy trong method security sẽ có cùng context với expression trong `@Value` hoặc cache annotation.

Hãy kiểm thử qua cơ chế thật của framework đang dùng. Với annotation được xử lý lúc khởi tạo bean, hãy tạo ApplicationContext. Với annotation được xử lý khi gọi method, hãy gọi Spring-managed bean qua proxy.

## 2. Kiểm thử SpEL trực tiếp khi cần cô lập biểu thức

Nếu mục tiêu là kiểm tra riêng cú pháp, root object, variables hoặc toán tử, có thể viết unit test tạo parser và EvaluationContext:

    @Test
    void evaluatesOrderExpression() {
        OrderView order = new OrderView(
                new BigDecimal("150.00")
        );

        StandardEvaluationContext context =
                new StandardEvaluationContext(order);

        context.setVariable(
                "minimum",
                new BigDecimal("100.00")
        );

        ExpressionParser parser =
                new SpelExpressionParser();

        Boolean result = parser.parseExpression(
                "total >= #minimum"
        ).getValue(context, Boolean.class);

        assertTrue(result);
    }

Test này kiểm tra expression trên context được tạo trong test. Nó phù hợp để kiểm tra logic SpEL độc lập, nhưng không thay thế test tích hợp annotation: Spring có thể cung cấp một root object, resolver, converter hoặc biến khác khi xử lý annotation thực tế.

Nên tách test parser/evaluation khỏi test tích hợp để khi có lỗi, dễ xác định lỗi nằm ở expression hay cấu hình Spring.

## 3. Kiểm thử giá trị được inject bằng @Value

Với `@Value`, Spring đánh giá expression trong quá trình tạo bean và inject giá trị vào constructor, field hoặc setter. Hãy khởi động một ApplicationContext thật trong test để xác nhận cả expression lẫn quá trình injection.

Ví dụ component:

    @Component
    public class ReportSettings {

        private final String region;

        public ReportSettings(
                @Value("#{systemProperties['user.timezone']}")
                String region) {
            this.region = region;
        }

        public String getRegion() {
            return region;
        }
    }

Có thể kiểm thử bean sau khi context được tạo:

    @SpringJUnitConfig(TestConfiguration.class)
    class ReportSettingsTest {

        @Autowired
        private ReportSettings settings;

        @Test
        void injectsExpressionValue() {
            assertNotNull(settings.getRegion());
        }
    }

Nếu expression phụ thuộc property cấu hình, hãy cung cấp giá trị test xác định bằng `@TestPropertySource`, `@DynamicPropertySource` hoặc cấu hình test phù hợp. Ví dụ:

    @TestPropertySource(properties = {
        "reports.region=ap-southeast-1"
    })

    @Value("${reports.region}")
    private String region;

Placeholder `${...}` lấy property từ Environment; expression `#{...}` được xử lý bởi SpEL. Khi cần kiểm thử một giá trị SpEL kết hợp property, hãy đặt input test rõ ràng để kết quả không phụ thuộc máy chạy test.

Nếu expression tham chiếu bean bằng `@beanName`, hãy khai báo bean đó trong test context hoặc import cấu hình thật tương ứng. Không chỉ mock parser; cần xác nhận bean resolver thực tế tìm đúng bean và giá trị được inject như mong đợi.

## 4. Kiểm thử @PreAuthorize qua method-security proxy

Để kiểm thử `@PreAuthorize`, bật method security trong test context và gọi method trên bean do Spring inject. Ví dụ:

    @Configuration
    @EnableMethodSecurity
    static class TestSecurityConfiguration {
        @Bean
        DocumentService documentService() {
            return new DocumentService();
        }
    }

    @Service
    public class DocumentService {

        @PreAuthorize("hasAuthority('document:read')")
        public String readDocument() {
            return "document";
        }
    }

Test với authority được cấp:

    @Test
    @WithMockUser(authorities = "document:read")
    void allowsUserWithRequiredAuthority() {
        assertEquals(
                "document",
                documentService.readDocument()
        );
    }

Test trường hợp thiếu quyền:

    @Test
    @WithMockUser(authorities = "document:write")
    void deniesUserWithoutReadAuthority() {
        assertThrows(
                AccessDeniedException.class,
                () -> documentService.readDocument()
        );
    }

Các annotation `@WithMockUser` thuộc Spring Security Test. Test cần dependency test tương ứng và phải gọi method trên bean được Spring quản lý để method-security interceptor thực sự chạy.

Nếu tự tạo object bằng `new DocumentService()`, annotation không tự được áp dụng vì lời gọi không đi qua proxy Spring.

## 5. Kiểm tra cả hành vi method khi bị từ chối

Với `@PreAuthorize`, điều kiện được đánh giá trước method body. Ngoài việc xác nhận exception, nên kiểm tra method không thực hiện side effect khi quyền bị từ chối.

Ví dụ service phụ thuộc repository:

    @Service
    public class DocumentService {

        private final DocumentRepository repository;

        public DocumentService(DocumentRepository repository) {
            this.repository = repository;
        }

        @PreAuthorize("hasAuthority('document:delete')")
        public void delete(Long id) {
            repository.deleteById(id);
        }
    }

Trong test, mock repository và xác nhận không có lệnh xóa khi caller thiếu authority:

    @Test
    @WithMockUser(authorities = "document:read")
    void doesNotDeleteWhenAccessIsDenied() {
        assertThrows(
                AccessDeniedException.class,
                () -> documentService.delete(10L)
        );

        verify(repository, never()).deleteById(anyLong());
    }

Kiểm tra này chứng minh ranh giới bảo mật ngăn method thực hiện thao tác. Với method có nhiều side effect, hãy kiểm tra những dependency quan trọng để bảo đảm chúng không được gọi khi pre-authorization thất bại.

## 6. Kiểm thử expression tham chiếu tham số method

Method-security expression thường dùng `#parameterName` để truy cập đối số. Ví dụ:

    @PreAuthorize(
        "#ownerId == authentication.name"
    )
    public Document findDocument(
            @P("ownerId") String ownerId) {
        return repository.findByOwner(ownerId);
    }

Test nên bao phủ cả trường hợp owner trùng principal và trường hợp khác principal:

    @Test
    @WithMockUser(username = "lan")
    void allowsMatchingOwner() {
        assertNotNull(documentService.findDocument("lan"));
    }

    @Test
    @WithMockUser(username = "minh")
    void deniesDifferentOwner() {
        assertThrows(
                AccessDeniedException.class,
                () -> documentService.findDocument("lan")
        );
    }

Tên tham số trong expression phụ thuộc metadata biên dịch hoặc annotation cung cấp tên tường minh. Có thể biên dịch Java với tùy chọn `-parameters`, hoặc dùng `@P("ownerId")` của Spring Security để chỉ rõ tên cần tham chiếu.

Nếu expression dùng `#p0` hoặc `#a0`, hãy kiểm tra đúng chỉ số và thứ tự tham số. Một test chỉ kiểm tra parse sẽ không phát hiện trường hợp tham chiếu sai tên hoặc sai vị trí.

## 7. Kiểm thử bean được gọi trong expression

Method-security expression có thể gọi bean qua `@beanName`:

    @PreAuthorize(
        "@documentAuthorization.canRead(authentication, #documentId)"
    )
    public Document getDocument(
            @P("documentId") Long documentId) {
        return repository.findById(documentId).orElseThrow();
    }

Đăng ký authorization bean trong test context. Có thể dùng bean thật để kiểm tra quy tắc domain, hoặc mock bean nếu mục tiêu là kiểm tra việc expression gọi đúng method và truyền đúng đối số.

Các trường hợp nên kiểm tra:

- Bean name trong expression khớp tên bean được đăng ký.
- Bean resolver của method-security expression tìm được bean.
- Authentication hiện tại được truyền đúng.
- Method argument được bind đúng tên hoặc index.
- Kết quả true cho phép method chạy.
- Kết quả false từ chối method trước khi thực thi.

Không nên mock toàn bộ method-security infrastructure nếu mục tiêu là kiểm tra cấu hình annotation. Hãy để Spring xử lý expression thật, chỉ thay thế dependency domain mà test cần kiểm soát.

## 8. Kiểm thử @PostAuthorize và returnObject

`@PostAuthorize` được đánh giá sau khi method đã chạy. Biến `returnObject` tham chiếu giá trị method trả về.

Ví dụ:

    @PostAuthorize(
        "returnObject.owner == authentication.name"
    )
    public Document load(Long id) {
        return repository.findById(id).orElseThrow();
    }

Test cần bao phủ cả kết quả thuộc caller và kết quả thuộc người khác:

    @Test
    @WithMockUser(username = "lan")
    void returnsDocumentOwnedByCurrentUser() {
        Document document = service.load(1L);
        assertEquals("lan", document.getOwner());
    }

    @Test
    @WithMockUser(username = "minh")
    void deniesDocumentOwnedByAnotherUser() {
        assertThrows(
                AccessDeniedException.class,
                () -> service.load(1L)
        );
    }

Lưu ý method body đã chạy trước khi hậu điều kiện được kiểm tra. Nếu method có side effect, test cần xác nhận hậu quả đó và cân nhắc chuyển kiểm tra quyền sang `@PreAuthorize` hoặc service trước khi thực hiện hành động. Không dùng `@PostAuthorize` như lớp bảo vệ duy nhất cho thao tác không thể hoàn tác.

## 9. Kiểm thử @PreFilter và @PostFilter

Hai annotation filter dùng `filterObject` để tham chiếu phần tử đang được kiểm tra.

Với `@PreFilter`, test cần xác nhận method chỉ nhận những phần tử phù hợp với predicate:

    @PreFilter(
        value = "filterObject.owner == authentication.name",
        filterTarget = "documents"
    )
    public int countOwned(
            List<Document> documents) {
        return documents.size();
    }

Với `@PostFilter`, test xác nhận collection trả về chỉ chứa phần tử được phép:

    @PostFilter(
        "filterObject.owner == authentication.name"
    )
    public List<Document> findAllVisible() {
        return repository.findAll();
    }

Nên kiểm tra collection có nhiều phần tử, không có phần tử phù hợp, một phần tử phù hợp và dữ liệu biên như owner null nếu domain cho phép.

Nếu method có nhiều tham số collection, kiểm tra `filterTarget` trỏ đúng tham số. Với collection lớn, lọc sau khi tải toàn bộ dữ liệu có thể tốn tài nguyên; nên kiểm thử cả truy vấn repository và cân nhắc đưa điều kiện phân quyền xuống database.

## 10. Kiểm thử root object và biến đặc biệt theo annotation

Mỗi expression handler có thể cung cấp root object và biến riêng. Ví dụ method security có Authentication và các hàm như `hasAuthority`; filter annotation có `filterObject`; post-authorization có `returnObject`.

Không lấy một expression từ annotation rồi đánh giá bằng StandardEvaluationContext tự tạo và cho rằng kết quả tương đương với framework. Context tự tạo có thể thiếu root object, method arguments, security helper hoặc resolver mà framework cung cấp.

Nếu cần unit test một đoạn logic thuần SpEL, hãy dựng context tương ứng và kiểm tra rõ những thành phần đã đăng ký. Nếu cần xác nhận annotation hoạt động, hãy kiểm thử qua bean và infrastructure thực tế.

## 11. Kiểm thử method security không bị bỏ qua do self-invocation

Method security thường được áp dụng qua Spring AOP proxy. Nếu một method trong cùng class gọi trực tiếp method khác trên `this`, lời gọi nội bộ có thể không đi qua proxy:

    public void process(Long id) {
        update(id);
    }

    @PreAuthorize("hasAuthority('document:write')")
    public void update(Long id) {
        // ...
    }

Một test gọi `process()` có thể không kích hoạt interceptor trên `update()` như mong đợi. Hãy kiểm tra đường gọi thực tế và đặt ranh giới bảo mật ở method được gọi qua proxy. Có thể tách method được bảo vệ sang một bean khác nếu cần một ranh giới rõ ràng.

Trong test, inject service từ ApplicationContext. Không tự khởi tạo service bằng `new`, và không gọi method trên target object đã bị unwrap khỏi proxy khi muốn kiểm tra method security.

## 12. Phân biệt lỗi parse, lỗi evaluate và lỗi authorization

Khi test thất bại, hãy xác định lỗi thuộc giai đoạn nào:

| Loại lỗi | Ví dụ | Cách kiểm tra |
|---|---|---|
| Parse | Cú pháp expression sai | Kiểm tra parser và chuỗi expression |
| Evaluation | Thiếu variable, bean, property hoặc converter | Kiểm tra EvaluationContext và resolver thực tế |
| Authorization | Expression trả false hoặc quyền không đủ | Kiểm tra principal, authority, tham số và dữ liệu domain |
| Proxy/infrastructure | Annotation không được áp dụng | Kiểm tra method security, bean registration và đường gọi |

Không bắt mọi exception rồi coi là access denied. Ví dụ, lỗi bean name hoặc property có thể là lỗi cấu hình chứ không phải quyết định từ chối quyền. Test nên phân biệt lỗi hệ thống với kết quả authorization false.

## 13. Bộ test tối thiểu cho annotation expression

Với mỗi annotation có SpEL, nên có các trường hợp phù hợp:

1. Cấu hình Spring khởi động và bean được tạo thành công.
2. Expression nhận đúng property, variable và tham số cần dùng.
3. Người dùng hoặc dữ liệu hợp lệ được phép.
4. Người dùng thiếu quyền hoặc dữ liệu không phù hợp bị từ chối.
5. Method không thực hiện side effect khi pre-authorization thất bại.
6. Bean được tham chiếu trong expression được resolve đúng.
7. Null, collection rỗng và dữ liệu biên được xử lý theo hợp đồng.
8. Đường gọi thực tế đi qua proxy nếu annotation dựa trên AOP.
9. Lỗi parse/evaluation được phân biệt với lỗi phân quyền.
10. Test không phụ thuộc vào dữ liệu hoặc property của máy phát triển.

Không phải annotation nào cũng cần toàn bộ các trường hợp trên. Chọn các trường hợp tương ứng với context và hành vi mà annotation cung cấp.

## 14. Ghi nhớ

Kiểm thử expression trong annotation cần đi qua đúng cơ chế Spring xử lý annotation. Với `@Value`, tạo ApplicationContext và xác nhận giá trị được inject; với method security, bật `@EnableMethodSecurity`, gọi Spring-managed bean qua proxy và kiểm tra cả trường hợp được phép lẫn bị từ chối. Kiểm tra tên tham số, bean reference, `returnObject` và `filterObject` trong context thực tế của annotation. Unit test dùng parser và EvaluationContext hữu ích để cô lập logic SpEL, nhưng không thay thế integration test. Luôn phân biệt lỗi parse, lỗi evaluate, lỗi cấu hình proxy và quyết định authorization.
