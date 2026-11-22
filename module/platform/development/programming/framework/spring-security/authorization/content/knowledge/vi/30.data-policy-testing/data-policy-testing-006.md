# Kiểm thử phân trang, số lượng tổng và dữ liệu bị che

## Mục tiêu

Bài này hướng dẫn kiểm thử một API danh sách có phân trang trong Spring Security để bảo đảm ba điều đồng thời: (1) mỗi trang chỉ chứa bản ghi mà danh tính hiện tại được phép xem, (2) `totalElements` và `totalPages` không tiết lộ số lượng bản ghi ngoài phạm vi quyền, (3) dữ liệu nhạy cảm được che hoặc loại bỏ khỏi **JSON phản hồi thực tế**. Một request trả HTTP 200 và đủ `size` phần tử chưa chứng minh được những điều đó.

Học xong, bạn cần tự thiết kế fixture trộn nhiều chủ sở hữu/tenant, viết phép kiểm tra page đầu/page tiếp/page rỗng, đối chiếu phép COUNT với chính sách authorization, và dùng canary để phát hiện trường bí mật xuất hiện ngoài dự kiến.

## 1. Xác định chính sách và hợp đồng đầu ra

Giả sử endpoint `GET /api/invoices?page=0&size=2` dùng page index từ 0 và thứ tự `id ASC`. Chính sách **minh họa**:

- `ROLE_USER` chỉ được thấy bản ghi có `tenantId` trùng tenant từ danh tính đã xác thực **và** `ownerUsername` trùng username đã xác thực.
- `ROLE_ADMIN` được thấy mọi hóa đơn trong **tenant của chính mình**; ADMIN không mặc nhiên vượt qua ranh giới tenant.
- `customerEmail` hiển thị nguyên văn cho ADMIN và được che cho USER: `alice@example.test` thành `a***@example.test`.
- `internalMemo` tuyệt đối không có trong response DTO, kể cả khi caller là ADMIN.

Spring Security không tự áp các quy tắc theo từng hàng/trường lên JPA repository; ứng dụng phải triển khai chúng. Đặt các giá trị test sau (mọi `internalMemo` chứa canary `SAMPLE_PRIVATE_X9`):

| ID | Tenant | Owner | Email |
| ---: | --- | --- | --- |
| 101 | t-a | alice | alice@example.test |
| 102 | t-a | bob | bob@example.test |
| 103 | t-a | alice | alice@example.test |
| 104 | t-a | alice | alice@example.test |
| 105 | t-a | alice | alice@example.test |
| 201 | t-b | alice | alice@example.test |

Với `alice` thuộc `t-a` và `ROLE_USER`, tập bản ghi được thấy theo thứ tự là **[101, 103, 104, 105]**. ID 102 khác owner; ID 201 khác tenant dù owner vẫn tên alice.

| Caller và yêu cầu | ID trong `content` | `totalElements` | `totalPages` | `hasNext` |
| --- | --- | ---: | ---: | --- |
| alice/t-a USER, page=0 size=2 | [101,103] | 4 | 2 | true |
| alice/t-a USER, page=1 size=2 | [104,105] | 4 | 2 | false |
| alice/t-a USER, page=2 size=2 | [] | 4 | 2 | false |
| admin/t-a ADMIN, page=0 size=2 | [101,102] | 5 | 3 | true |
| mallory/t-a USER, page=0 size=2 | [] | 0 | 0 | false |

Gọi `V(u)` là tập bản ghi người dùng `u` được phép nhìn thấy. Nội dung phải là một lát cắt sau khi **lọc V(u) rồi mới sort/limit/offset**; `totalElements = |V(u)|` và, với `size > 0`, `totalPages = ceil(totalElements/size)` (tổng bằng 0 thì số trang bằng 0 theo hợp đồng mẫu). Không được dùng tổng của toàn bảng hoặc toàn tenant khi người gọi chỉ có quyền xem một phần.

### Tại sao phân trang trước rồi lọc quyền là lỗi?

Nếu query không giới hạn owner lấy hai ID đầu tenant t-a là [101,102], sau đó controller bỏ 102, page=0 chỉ còn [101], trong khi 103 phải nằm ở trang đầu. Query COUNT toàn tenant trả 5 làm lộ số bản ghi không được phép thấy. Sửa tổng bằng `content.size()` cũng sai: tổng hợp lệ phải là 4, không phải 1. Lọc sau khi gọi `findAll(pageable)`, lọc tại frontend hoặc dùng post-filter trên dữ liệu đã chia trang đều không thể phục hồi đúng trang/tổng.

Luồng đúng: **authentication → quyền gọi API → điều kiện quyền trong truy vấn → sắp xếp ổn định → page và COUNT cùng phạm vi → DTO → che trường → JSON**.

Ví dụ ý tưởng SQL; các biến phải bind bằng tham số và tenant lấy từ principal/claims đã được server kiểm chứng:

```sql
SELECT id, title, customer_email, internal_memo
FROM invoice
WHERE tenant_id = :tenant
  AND (:is_admin = TRUE OR owner_username = :username)
ORDER BY id ASC
LIMIT :size OFFSET :offset;

SELECT COUNT(*)
FROM invoice
WHERE tenant_id = :tenant
  AND (:is_admin = TRUE OR owner_username = :username);
```

Điều kiện trong COUNT phải tương đương điều kiện lọc dữ liệu. Nếu thêm trạng thái, soft-delete, quan hệ sở hữu, ACL, search keyword hay chính sách tenant, **cả data query và count query** phải tính cùng phạm vi. Không nhận `tenantId`/`ownerUsername` do client tự khai báo làm nguồn thẩm quyền.

## 2. Triển khai tham khảo với Spring Data JPA

Ví dụ dưới đây là **đoạn tích hợp** vào ứng dụng Spring Boot/Spring Security hiện có, không phải file Java biên dịch độc lập. Giả định entity `Invoice` có `id`, `title`, `tenantId`, `ownerUsername`, `customerEmail`, `internalMemo`; `TenantIdentity` là thành phần của ứng dụng đọc tenant đã xác thực; đã bật `@EnableMethodSecurity`. Cần import các type Spring/Java tương ứng.

```java
interface InvoiceRepository extends JpaRepository<Invoice, Long>,
        JpaSpecificationExecutor<Invoice> {}

record InvoiceDto(Long id, String title, String customerEmail) {}

@Service
class InvoiceQueryService {
    private final InvoiceRepository repository;
    private final TenantIdentity tenantIdentity;

    InvoiceQueryService(InvoiceRepository repository, TenantIdentity tenantIdentity) {
        this.repository = repository;
        this.tenantIdentity = tenantIdentity;
    }

    @PreAuthorize("hasAnyRole('USER', 'ADMIN')")
    @Transactional(readOnly = true)
    public Page<InvoiceDto> list(Authentication actor, int page, int size) {
        if (page < 0 || size < 1 || size > 100) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Invalid page or size");
        }

        String tenant = tenantIdentity.tenantOf(actor); // từ danh tính tin cậy
        boolean admin = actor.getAuthorities().stream()
                .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));

        Specification<Invoice> visible = (root, query, cb) -> {
            Predicate sameTenant = cb.equal(root.get("tenantId"), tenant);
            return admin ? sameTenant
                    : cb.and(sameTenant,
                            cb.equal(root.get("ownerUsername"), actor.getName()));
        };

        Pageable pageable = PageRequest.of(
                page, size, Sort.by("id").ascending());

        return repository.findAll(visible, pageable).map(row ->
                new InvoiceDto(
                        row.getId(),
                        row.getTitle(),
                        admin
                                ? row.getCustomerEmail()
                                : maskEmail(row.getCustomerEmail())));
    }

    private static String maskEmail(String email) {
        if (email == null) return null;
        int at = email.indexOf('@');
        if (at <= 0) return "***";
        return email.substring(0, 1) + "***" + email.substring(at);
    }
}
```

`JpaSpecificationExecutor.findAll(spec,pageable)` dùng `Specification` cho truy vấn lấy trang và truy vấn tính tổng của Page. `Page.map` chỉ **biến đổi các phần tử đã được truy vấn đúng quyền**, vẫn giữ metadata của Page; nó không phải công cụ lọc phân quyền. Entity chứa `internalMemo` nhưng `InvoiceDto` không chứa field đó. Không trả thẳng entity JPA: getter, quan hệ lồng nhau hoặc thay đổi serializer có thể mở rộng dữ liệu trả về ngoài ý muốn.

Để có JSON contract ổn định, định nghĩa response DTO rõ ràng thay vì phụ thuộc vào cách từng phiên bản Spring Data serialize trực tiếp `PageImpl`:

```java
record PageResponse<T>(
        List<T> content, int number, int size,
        long totalElements, int totalPages, boolean hasNext) {
    static <T> PageResponse<T> from(Page<T> p) {
        return new PageResponse<>(
                p.getContent(), p.getNumber(), p.getSize(),
                p.getTotalElements(), p.getTotalPages(), p.hasNext());
    }
}

@RestController
@RequestMapping("/api/invoices")
class InvoiceController {
    private final InvoiceQueryService service;

    InvoiceController(InvoiceQueryService service) {
        this.service = service;
    }

    @GetMapping
    PageResponse<InvoiceDto> list(
            Authentication actor,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "2") int size) {
        return PageResponse.from(service.list(actor, page, size));
    }
}
```

Trong thực tế, policy có thể phức tạp hơn vai trò USER/ADMIN và cần `@PreAuthorize`/permission evaluator/check service thích hợp. Quy tắc che email là ví dụ; nếu policy yêu cầu ẩn email cả với admin, sửa DTO mapping và kỳ vọng test tương ứng. Với sort theo `createdAt`, thêm `id` làm tie-breaker để pagination ổn định, ví dụ `Sort.by("createdAt").ascending().and(Sort.by("id"))`.

## 3. Kiểm thử qua HTTP và database

Kết hợp kiểm thử repository/query với integration test `MockMvc`. Unit test mock repository trả Page đã chuẩn bị sẵn chỉ kiểm tra mapping, **không chứng minh SQL WHERE/COUNT được phân quyền đúng**. Với đặc tính database riêng, kiểm thử tích hợp trên DB tương thích production (chẳng hạn Testcontainers); dùng fixture DB cố định có đủ owner/tenant chéo.

Ví dụ dưới đây dùng bảng fixture nêu trên, cần ứng dụng Spring, entity/repository, SQL fixture `/data/invoices-visibility.sql` (được reset giữa test), imports của JUnit/Mockito/Hamcrest/Spring. `@WithMockUser` chỉ đặt username/role, **không tạo tenant claim thật**. Mock `TenantIdentity` ở đây chỉ cô lập bài toán phân trang; một test riêng phải kiểm tra principal/JWT thực và việc không tin tenant từ request.

```java
@SpringBootTest
@AutoConfigureMockMvc
@Sql("/data/invoices-visibility.sql")
class InvoiceQueryHttpTest {
    @Autowired MockMvc mvc;
    @MockBean TenantIdentity tenantIdentity;

    @BeforeEach
    void setupTenant() {
        when(tenantIdentity.tenantOf(any(Authentication.class)))
                .thenReturn("t-a");
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void firstPageAndTotalContainOnlyAuthorizedRows() throws Exception {
        mvc.perform(get("/api/invoices").param("page", "0").param("size", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.number").value(0))
                .andExpect(jsonPath("$.size").value(2))
                .andExpect(jsonPath("$.totalElements").value(4))
                .andExpect(jsonPath("$.totalPages").value(2))
                .andExpect(jsonPath("$.hasNext").value(true))
                .andExpect(jsonPath("$.content.length()").value(2))
                .andExpect(jsonPath("$.content[0].id").value(101))
                .andExpect(jsonPath("$.content[1].id").value(103))
                .andExpect(jsonPath("$.content[0].customerEmail")
                        .value("a***@example.test"))
                .andExpect(jsonPath("$.content[*].internalMemo").doesNotExist())
                .andExpect(content().string(
                        not(containsString("SAMPLE_PRIVATE_X9"))));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void subsequentAndOutOfRangePagesPreserveCorrectCount() throws Exception {
        mvc.perform(get("/api/invoices").param("page", "1").param("size", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[0].id").value(104))
                .andExpect(jsonPath("$.content[1].id").value(105))
                .andExpect(jsonPath("$.totalElements").value(4))
                .andExpect(jsonPath("$.hasNext").value(false));

        mvc.perform(get("/api/invoices").param("page", "2").param("size", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content.length()").value(0))
                .andExpect(jsonPath("$.totalElements").value(4))
                .andExpect(jsonPath("$.totalPages").value(2));
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminIsStillScopedToOwnTenant() throws Exception {
        mvc.perform(get("/api/invoices").param("page", "0").param("size", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content[0].id").value(101))
                .andExpect(jsonPath("$.content[1].id").value(102))
                .andExpect(jsonPath("$.totalElements").value(5))
                .andExpect(jsonPath("$.totalPages").value(3))
                .andExpect(content().string(
                        not(containsString("SAMPLE_PRIVATE_X9"))));
    }

    @Test
    @WithMockUser(username = "mallory", roles = "USER")
    void zeroVisibleRowsMustMeanZeroTotal() throws Exception {
        mvc.perform(get("/api/invoices").param("page", "0").param("size", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content.length()").value(0))
                .andExpect(jsonPath("$.totalElements").value(0))
                .andExpect(jsonPath("$.totalPages").value(0));
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void invalidPaginationIsRejected() throws Exception {
        mvc.perform(get("/api/invoices").param("size", "0"))
                .andExpect(status().isBadRequest());
        mvc.perform(get("/api/invoices").param("page", "-1"))
                .andExpect(status().isBadRequest());
        mvc.perform(get("/api/invoices").param("size", "101"))
                .andExpect(status().isBadRequest());
    }
}
```

Các matcher `jsonPath` và canary kiểm tra **response serialized**. Có thể test từng DTO mà vẫn bỏ sót field do Jackson thêm vào; có thể test chỉ tổng đúng nhưng nội dung trang vẫn sai. Cần đồng thời so ID, thứ tự, trang rỗng, metadata và chuỗi bí mật không xuất hiện. File SQL minh họa phải được triển khai theo schema dự án và tự reset để test độc lập.

## 4. Ma trận ca kiểm thử cần có

| Tình huống | Kỳ vọng phải kiểm tra |
| --- | --- |
| Bản ghi bị cấm nằm xen giữa hai bản ghi được xem | Page 0 đủ [101,103], page 1 đủ [104,105]; không xảy ra lọc sau offset |
| Hai user cùng tenant khác owner | Mỗi user chỉ thấy phần của mình; tổng độc lập |
| Cùng username ở tenant khác | alice/t-b chỉ thấy [201], total=1; không lộ t-a |
| Admin cùng tenant | Xem thêm bản ghi 102, total=5; không thấy 201 |
| Không có bản ghi được phép | `content=[]`, total=0, totalPages=0, hasNext=false |
| Trang nằm ngoài cuối | `content=[]` nhưng `totalElements` giữ nguyên tổng được phép |
| Input sai | page âm; size 0/âm/quá max; giá trị không phải số trả 400 |
| Sort được phép | Thứ tự xác định, có tie-breaker ID; cấm sort trên field nhạy cảm nếu policy không cho |
| Chặn tại endpoint | anonymous/role thiếu quyền nhận 401 hoặc 403 theo security config, không trả dữ liệu |
| Chi tiết ID không thuộc quyền | 403 hoặc 404 tùy chính sách chống dò tồn tại; không xác nhận ID nhạy cảm qua lỗi |
| Thêm/xóa bản ghi có quyền ở fixture | Count, số trang, hasNext thay đổi đúng với tập được phép |
| Thay đổi quyền field | Email đúng chuỗi che cho USER, nguyên văn cho ADMIN nếu policy cho phép; `internalMemo` luôn vắng mặt |

Để kiểm tra toàn bộ pagination khi fixture tĩnh, gọi từng trang và ghép danh sách ID theo thứ tự: kết quả phải bằng tập ID được phép thấy, **không trùng, không thiếu, không có ID ngoài quyền**. Chỉ kiểm tra `content.length()==size` là chưa đủ.

## 5. Che dữ liệu: kiểm tra đúng JSON, đúng chính sách

Ba kiểu hợp đồng khác nhau: **bỏ field** (property không tồn tại), **mask field** (ví dụ email che một phần), **trả nguyên văn** (chỉ khi có quyền tương ứng). Nếu hợp đồng yêu cầu bỏ field, JSON có `"internalMemo": null` vẫn khác với field hoàn toàn vắng mặt; nên dùng DTO allowlist và khẳng định `doesNotExist()`. Nếu hợp đồng yêu cầu mask, test chuỗi chính xác, đừng chỉ test nó khác email gốc; giá trị rỗng hoặc che sai cũng là lỗi.

Đặt canary duy nhất vào trường nhạy cảm và khẳng định **toàn bộ HTTP body** không chứa nó. Nếu API có nested DTO, export, liên kết, metadata, GraphQL resolver hoặc error response, mỗi bề mặt có thể cần test riêng. JSON body an toàn không tự chứng minh application logs, audit, cache hay metrics cũng an toàn; rà soát các kênh đó theo mức độ nhạy cảm của hệ thống.

Trường hợp admin được thấy email không có nghĩa admin được thấy `internalMemo`: authorization của hàng và authorization của từng trường là hai tầng độc lập. Test từng role theo cùng fixture để phát hiện thay đổi mapping vô tình mở quyền xem.

## 6. Page, Slice và tính nhất quán

`Page<T>` chứa `totalElements`/`totalPages` và thường cần count query trên tập đã phân quyền. `Slice<T>` chủ yếu cho biết có trang tiếp hay không (thường lấy dư một phần tử); **không hứa tổng chính xác**. Đừng gán `totalElements` bằng `content.size()` nếu dùng Slice. Nếu sản phẩm cần số lượng kết quả trong UI, phải có count hợp lệ.

Với dữ liệu thay đổi liên tục, OFFSET pagination có thể trùng/mất bản ghi giữa hai request dù query authorization đúng. Test logic phân trang bằng fixture bất biến; nếu yêu cầu nghiệp vụ là duyệt danh sách ổn định khi có ghi đồng thời, cân nhắc cursor/keyset hoặc snapshot nhất quán. Tương tự, data query và count query trong `READ_COMMITTED` có thể quan sát dữ liệu khác nhau khi có concurrent writes; `@Transactional(readOnly = true)` không tự đảm bảo snapshot cho mọi database. Phân biệt sai lệch do đồng thời với lỗi thiếu predicate bảo mật.

## 7. Lỗi phổ biến và checklist nghiệm thu

| Sai lầm | Hậu quả | Cách phát hiện và sửa |
| --- | --- | --- |
| `findAll(pageable)` rồi lọc owner/tenant | Trang thiếu phần tử, tổng rò rỉ | Đưa predicate quyền vào query trước paging; COUNT cùng scope |
| Dùng `@PostFilter` trên collection sau paging | Không phục hồi offset/count; chi phí lớn | Dùng query authorization |
| Count query chỉ lọc tenant nhưng data query lọc owner | Tổng cao hơn quyền thực | Test `totalElements` cho USER/ADMIN/mallory |
| Frontend ẩn cột nhưng server trả raw entity | Email/ghi chú lộ trong network payload | DTO allowlist; test body thực tế |
| Fixture chỉ chứa dữ liệu hợp lệ | Test không kích hoạt đường lỗi | Có row khác owner, khác tenant xen giữa |
| Không có trang 2, trang rỗng, boundary | Không thấy totalPages/hasNext sai | Test trang đầu, trang sau, vượt cuối và input sai |
| Lấy tenant từ query parameter | Truy cập chéo tenant | Lấy từ authentication server kiểm chứng, test giả mạo tenant |
| Test mock Page đã lọc | Không kiểm tra WHERE/COUNT thực | Repository + HTTP integration test, DB tương thích production |

Checklist cuối cùng: danh tính và tenant tin cậy; quyền gọi endpoint được kiểm tra; content đúng ID/thứ tự; count/totalPages/hasNext đúng **cùng tập được phép**; không có bản ghi xuyên owner/tenant; input paging được giới hạn; field ẩn biến mất khỏi JSON; field mask có giá trị đúng; canary không lộ; kiểm thử thật đi qua query, security chain và serializer. Khi các bất biến đó đều đúng, pagination vừa đúng nghiệp vụ vừa không tiết lộ dữ liệu ngoài phạm vi quyền.
