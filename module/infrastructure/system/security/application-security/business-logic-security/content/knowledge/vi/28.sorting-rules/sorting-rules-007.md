# Sort authorization tests — Kiểm thử quyền sắp xếp dữ liệu

## 1. Cần chứng minh nhiều hơn việc API chấp nhận một tên field

Trong chương **Sorting Rules** của Business Logic Security, sort authorization tests là các kiểm thử chứng minh người gọi chỉ được sử dụng những lựa chọn sắp xếp được cấp quyền trong đúng ngữ cảnh, và việc sắp xếp không làm rộng phạm vi dữ liệu hay thay đổi quy tắc nghiệp vụ.

Một request trả `200` với các dòng được sắp đúng chưa chứng minh quyền sort đúng. Một request trả `403` cũng chưa chứng minh field bị cấm đã được phát hiện: request có thể thiếu session hoặc CSRF và bị chặn trước khi đi tới policy.

Bộ kiểm thử cần bảo vệ các invariant cụ thể:

- Tên sort công khai chỉ ánh xạ tới property/biểu thức được cho phép.
- Actor không được sử dụng field bị hạn chế, kể cả khi field tồn tại trong entity.
- Tenant, quyền đối tượng và bộ lọc nghiệp vụ không đổi khi thay lựa chọn sort.
- Sort không lộ thông tin qua thứ tự ngoài hợp đồng đã cấp quyền.
- Thứ tự ưu tiên bắt buộc và khóa phân xử vẫn được giữ.
- Một thao tác đọc có sort không được tạo quyết định duyệt, đổi giá hoặc tác động nghiệp vụ khác.

Đây là kiểm thử ranh giới quyền và hành vi. Nó không chỉ là kiểm thử một comparator hoặc xác nhận thư viện ORM có thể hiểu tên property.

## 2. Bắt đầu từ hợp đồng và ma trận quyền độc lập

### 2.1. Hợp đồng API minh họa

Xét `POST /orders/search` dùng JSON để biểu diễn điều kiện tìm kiếm. Trong ví dụ, endpoint chỉ đọc đơn của người gọi trong tenant đang hoạt động, có filter trạng thái và trả response gồm `items` cùng `totalElements`.

```json
{
  "state": "PENDING_APPROVAL",
  "page": 0,
  "size": 20,
  "sort": [
    { "field": "createdAt", "direction": "DESC" }
  ]
}
```

Quy tắc sort được sản phẩm lựa chọn cho bài:

| Quy tắc | Hợp đồng mong đợi |
| --- | --- |
| Field cơ bản | `createdAt`, `number` |
| Field số tiền | `amount`, cần cả quyền đọc và quyền sort số tiền |
| Alias | `number` ánh xạ tới property nội bộ `reference` |
| Không công bố | `totalAmount`, `internalRiskScore`, đường dẫn quan hệ và biểu thức tùy ý |
| Direction | Chính xác `ASC` hoặc `DESC` |
| Số term | Từ một đến hai term nếu có mảng sort |
| Không truyền sort/null | Dùng `createdAt DESC, id ASC` |
| Mảng rỗng, term trùng, term sai | Từ chối toàn bộ sort |
| Khóa phân xử | Server thêm `id ASC` sau các term hợp lệ |
| Lỗi sort | `400` và mã công khai `INVALID_SORT` trong ví dụ |

Các mã lỗi và giới hạn trên là hợp đồng minh họa, không phải chuẩn bắt buộc cho mọi API. Bộ test của dự án phải bám lựa chọn thực tế đã được xác định trước, không sửa expectation theo phản hồi hiện tại chỉ để test xanh.

### 2.2. Ma trận không chỉ có vai trò quản trị và người dùng

| Profile test | Tìm đơn của mình | Đọc số tiền | Sort số tiền | Kết quả với `amount ASC` |
| --- | --- | --- | --- | --- |
| BASIC | Có | Không | Không | Từ chối |
| AMOUNT_READ_ONLY | Có | Có | Không | Từ chối |
| AMOUNT_SORT_ONLY | Có | Không | Có | Từ chối theo hợp đồng này |
| FINANCE | Có | Có | Có | Cho phép |
| NO_SEARCH | Không | Có thể có | Có thể có | Bị chặn ở quyền chức năng |

Mỗi profile còn cần tenant, quan hệ ownership và trạng thái tài khoản phù hợp. Một field được cấp quyền ở báo cáo tài chính không tự được cấp quyền ở API cá nhân hoặc hàng đợi phê duyệt.

OWASP đề xuất tự động hóa kiểm thử từ ma trận authorization có các chiều chức năng, vai trò logic và dữ liệu. Tham khảo [OWASP — Authorization Testing Automation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Testing_Automation_Cheat_Sheet.html). Trong bài này, field, direction và operation là các chiều cần bổ sung cho hành vi sort.

## 3. Tạo fixture có thể làm lỗi lộ rõ

### 3.1. Các giá trị không được vô tình cùng thứ tự

Một fixture minh họa cho actor Lan trong tenant A:

| Bí danh | Tenant | Owner | Ngày tạo | Mã đơn | Amount | Trạng thái |
| --- | --- | --- | --- | --- | --- | --- |
| A | A | Lan | 2026-01-03 | PO-020 | 300 | PENDING_APPROVAL |
| B | A | Lan | 2026-01-01 | PO-010 | 900 | PENDING_APPROVAL |
| C | A | Lan | 2026-01-03 | PO-030 | 100 | PENDING_APPROVAL |
| D | A | Minh | 2026-01-02 | PO-005 | 50 | PENDING_APPROVAL |
| E | B | Đức | 2026-01-04 | PO-001 | 1 | PENDING_APPROVAL |
| F | A | Lan | 2026-01-05 | PO-000 | 0 | APPROVED |

Giả sử ID của A đứng trước ID của C theo cách so sánh của database. Với filter PENDING_APPROVAL, Lan chỉ được nhận A, B, C và tổng bằng 3.

Các oracle độc lập:

```text
createdAt DESC, id ASC → A, C, B
number ASC, id ASC    → B, A, C
amount ASC, id ASC    → C, A, B
```

Như vậy, lỗi ánh xạ `number` sang ngày tạo hoặc `amount` sang mã đơn có cơ hội bị phát hiện. Nếu fixture có ngày, mã, số tiền và ID đều tăng cùng nhau, nhiều implementation sai vẫn trả đúng chuỗi ID mà test mong đợi.

### 3.2. Dòng ngoài phạm vi phải có khả năng lọt lên đầu

D và E có số tiền nhỏ hơn các đơn của Lan; E còn mới hơn. Nếu truy vấn làm mất ownership hoặc tenant khi đổi sort, chúng dễ xuất hiện ở vị trí quan sát được. F giúp phát hiện lỗi bỏ filter trạng thái.

Có thể thêm field nội bộ như `internalRiskScore` với giá trị khác nhau để kiểm thử quyền sử dụng field ẩn. Oracle là API từ chối lựa chọn không được công bố, không phải chỉ giấu giá trị field khỏi JSON.

Mỗi test nên có fixture riêng hoặc dữ liệu được phân vùng rõ bằng tenant/actor/ID. Các tên A, B, C chỉ là bí danh trong bài; test harness có thể sinh UUID riêng và cung cấp `aId()`, `bId()`, `cId()` cho assertion.

## 4. Chọn tầng test và tránh ca âm giả

### 4.1. Ba tầng kiểm chứng có mục đích khác nhau

| Tầng | Điều có thể chứng minh | Điều chưa tự chứng minh |
| --- | --- | --- |
| Test policy/resolver thuần | Ma trận quyền field, alias, direction, mặc định, giới hạn term | HTTP binding, cấu hình bảo mật và SQL thực tế |
| Test tích hợp ứng dụng | Auth → service → resolver → persistence → response | Proxy ngoài, cache triển khai hoặc parser khác ở biên mạng |
| Test đường triển khai cần thiết | Cache, gateway, API tương thích, job/export liên quan | Toàn bộ policy chỉ từ một đường đi happy path |

Không cần đưa mọi chuỗi input vào tầng chậm nhất. Bao phủ quy tắc bằng test nhỏ, rồi chọn các ranh giới quan trọng để kiểm tra qua pipeline thật.

### 4.2. Giữ những yếu tố không phải mục tiêu ở trạng thái hợp lệ

Khi kiểm tra BASIC không được sort `amount`, dùng tài khoản đã đăng nhập, có quyền tìm đơn, body đúng JSON và dữ liệu thực sự tồn tại. Nếu API dùng session cookie và bật CSRF cho POST, cung cấp token hợp lệ.

Spring Security hướng dẫn thêm CSRF token hợp lệ khi kiểm thử các method cần bảo vệ tại [Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html). Thiếu token có thể làm request bị chặn trước policy sort.

Cần một **positive control**: cùng actor, session, endpoint và cấu trúc body, nhưng dùng `createdAt DESC` thì thành công. Với quyền tài chính, cũng cần ca FINANCE dùng `amount ASC` thành công, để bắt implementation từ chối mọi field mà vẫn làm các ca âm xanh.

### 4.3. Cấu hình bảo mật phải thực sự tham gia

MockMvc cần đi qua filter chain phù hợp. Spring mô tả cách tích hợp bằng `springSecurity()` khi tự dựng MockMvc trong [Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html).

Nếu dùng cấu hình test tự động của ứng dụng, xác minh bảo mật không bị tắt hoặc thay bằng cấu hình cho phép mọi request. Nếu policy nằm ở method security, bean và interceptor tương ứng cũng phải hoạt động; gọi một service tự `new` không chứng minh luồng bảo vệ đó.

Một principal mock với vai trò không tự tạo membership, ownership hoặc grant trong database. Session/test principal phải phù hợp với cách ứng dụng suy ra actor và tenant. Nếu cần kiểm tra chữ ký hoặc claim token thật, đó là phần cần được bao phủ bởi test xác thực tương ứng, không suy ra từ một MockMvc request đã gắn sẵn Authentication.

## 5. Test policy thuần theo ma trận field và quyền

Giả sử ứng dụng có `OrderSortResolver.resolve(terms, actor)` trả `Sort`, cùng record `SortTerm(field, direction)`. Test dưới chỉ minh họa cấu trúc; resolver, actor factory và exception là thành phần ứng dụng.

### 5.1. Không rút gọn hai quyền thành một

```java
static Stream<Arguments> amountPermissionCases() {
    return Stream.of(
        Arguments.of(false, false, false),
        Arguments.of(true,  false, false),
        Arguments.of(false, true,  false),
        Arguments.of(true,  true,  true)
    );
}

@ParameterizedTest
@MethodSource("amountPermissionCases")
void amountRequiresBothCapabilities(
        boolean canReadAmount,
        boolean canSortAmount,
        boolean allowed) {
    Actor actor = testActors.searcherWithAmountPermissions(
        canReadAmount, canSortAmount);
    List<SortTerm> input = List.of(new SortTerm("amount", "ASC"));

    if (allowed) {
        Sort result = resolver.resolve(input, actor);
        assertThat(result.toList())
            .extracting(Sort.Order::getProperty)
            .containsExactly("totalAmount", "id");
    } else {
        assertThatThrownBy(() -> resolver.resolve(input, actor))
            .isInstanceOf(InvalidSortException.class);
    }
}
```

Expected được xác định từ ma trận sản phẩm. Không lấy `allowed` bằng cách gọi chính hàm policy cần kiểm tra.

### 5.2. Field tồn tại nhưng không công bố phải bị từ chối

```java
@ParameterizedTest
@ValueSource(strings = {
    "totalAmount",
    "internalRiskScore",
    "customer.email",
    "LENGTH(reference)",
    "1",
    "createdAt DESC"
})
void rejectsUnpublishedSortChoices(String field) {
    Actor actor = testActors.financeSearcher();

    assertThatThrownBy(() -> resolver.resolve(
        List.of(new SortTerm(field, "ASC")), actor))
        .isInstanceOf(InvalidSortException.class);
}
```

Dùng actor có nhiều quyền trong ca này giúp tách lỗi “không phải lựa chọn công khai” khỏi việc actor thiếu quyền cơ bản. `totalAmount` là property nội bộ hợp lệ trong mô hình minh họa, nên test bắt được cách triển khai chỉ kiểm tra property có tồn tại.

### 5.3. Kiểm tra ngữ pháp và chuẩn hóa theo hợp đồng

Bổ sung các ca độc lập cho direction, mảng rỗng, term null, field null, term trùng, quá số lượng và sort mặc định. Với nhiều term, assert cả property lẫn direction theo đúng thứ tự ưu tiên.

Không chỉ assert `Sort` chứa field cần thiết. Kết quả có thêm một property nhạy cảm ở cuối vẫn có thể qua một assertion `contains`. Với những tập cấu trúc nhỏ đã xác định, `containsExactly` hữu ích hơn để phát hiện term thừa hoặc sai thứ tự.

## 6. Test tích hợp Java với MockMvc và persistence thật

Khung dưới giả định API trả `items`, `totalElements` và lỗi có `code`. Các kiểu `CommittedFixtures`, `TestSessions`, `BusinessProbe`, `Fixture`, `SearchRequest`, `SortTerm`, `TestPage` và `TestOrder` là test harness/DTO cần tự hiện thực. Ví dụ không phải lớp độc lập có thể chạy trong mọi dự án.

```java
@SpringBootTest
@AutoConfigureMockMvc
class SortAuthorizationIT {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper objectMapper;
    @Autowired CommittedFixtures fixtures;
    @Autowired TestSessions sessions;
    @Autowired BusinessProbe probe;

    @Test
    void basicActorGetsDefaultOrderWithinOwnScope() throws Exception {
        Fixture f = fixtures.ordersForProfile(Profile.BASIC);
        TestPage page = readPage(search(f, null)
            .andExpect(status().isOk())
            .andReturn());

        assertThat(page.items()).extracting(TestOrder::id)
            .containsExactly(f.aId(), f.cId(), f.bId());
        assertThat(page.totalElements()).isEqualTo(3);
    }

    @ParameterizedTest
    @ValueSource(strings = {"amount", "internalRiskScore", "totalAmount"})
    void basicActorCannotUseProhibitedField(String field) throws Exception {
        Fixture f = fixtures.ordersForProfile(Profile.BASIC);
        search(f, List.of(new SortTerm("createdAt", "DESC")))
            .andExpect(status().isOk());
        BusinessView before = probe.readInNewTransaction(f.scopeId());

        search(f, List.of(new SortTerm(field, "ASC")))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_SORT"));

        BusinessView after = probe.readInNewTransaction(f.scopeId());
        assertThat(after).isEqualTo(before);
    }

    @Test
    void financeActorCanSortAmountButCannotWidenObjectScope() throws Exception {
        Fixture f = fixtures.ordersForProfile(Profile.FINANCE);
        TestPage page = readPage(search(
                f, List.of(new SortTerm("amount", "ASC")))
            .andExpect(status().isOk())
            .andReturn());

        assertThat(page.items()).extracting(TestOrder::id)
            .containsExactly(f.cId(), f.aId(), f.bId());
        assertThat(page.totalElements()).isEqualTo(3);
    }

    private ResultActions search(Fixture f, List<SortTerm> sort) throws Exception {
        SearchRequest request = new SearchRequest(
            "PENDING_APPROVAL", 0, 20, sort);
        return mvc.perform(post("/orders/search")
            .session(sessions.forActor(f.actorId()))
            .with(csrf().asHeader())
            .contentType(MediaType.APPLICATION_JSON)
            .content(objectMapper.writeValueAsString(request)));
    }

    private TestPage readPage(MvcResult result) throws Exception {
        return objectMapper.readValue(
            result.getResponse().getContentAsString(StandardCharsets.UTF_8),
            TestPage.class);
    }
}
```

Các import tĩnh chính là `MockMvcRequestBuilders.post`, `MockMvcResultMatchers.status/jsonPath`, `SecurityMockMvcRequestPostProcessors.csrf` và `Assertions.assertThat` của AssertJ. Các kiểu còn lại thuộc Java, JUnit Jupiter, Spring Test, Jackson hoặc test harness đã mô tả.

Điều kiện để khung test có ý nghĩa:

1. Fixture đã commit trước request, actor có đúng grant và tenant do server quản lý.
2. Mỗi fixture chứa các đơn tương đương A–F với ID riêng. A/C có khóa sort chính bằng nhau và thứ tự ID đã biết.
3. Service nghiệp vụ và persistence thật được gọi; không mock search service trả sẵn danh sách đúng.
4. `BusinessProbe` trả snapshot bất biến từ transaction mới, không trả entity JPA dùng chung với luồng đang kiểm tra.
5. Session phù hợp cơ chế xác thực thực tế của ứng dụng. Nếu ứng dụng dùng bearer token, thay adapter request bằng cơ chế test tương ứng.
6. API thực tế có hợp đồng null sort như ví dụ; việc serialize null hoặc bỏ field cần được test rõ, không dựa vào cấu hình Jackson tình cờ.

Khung này chưa bao phủ toàn bộ ma trận. Nó minh họa ba bằng chứng bổ sung nhau: mặc định hợp lệ, field bị cấm bị từ chối với request hợp lệ và field tài chính được phép vẫn giữ đúng phạm vi đối tượng.

## 7. Kiểm tra ranh giới query và lỗi field ẩn

### 7.1. Đừng coi exception của ORM là cơ chế phân quyền

Nếu request `internalRiskScore` đi xuống ORM rồi gây lỗi `500`, test không nên được đánh dấu thành công chỉ vì response không phải `200`. Hợp đồng của ví dụ yêu cầu từ chối sort có kiểm soát trước khi thực thi truy vấn đơn hàng bằng field đó.

Spring Data JPA mô tả sort theo property/alias và khả năng thêm biểu thức qua `JpaSort.unsafe`. Xem [Spring Data JPA — Using Sort](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html#jpa.query-methods.sorting). Test cần bảo vệ policy của ứng dụng, không phụ thuộc việc một phiên bản framework tình cờ từ chối một biểu thức.

Có thể quan sát lệnh truy vấn đã chuẩn hóa tại ranh giới query adapter bằng một wrapper test vẫn delegate tới triển khai thật. Với request bị cấm, không được có lệnh tìm đơn dùng property bị cấm hoặc một lệnh fallback không sort.

Không yêu cầu “không có bất kỳ SQL nào” vì xác thực, membership hoặc audit có thể cần truy vấn. Hãy xác định đúng loại truy vấn và điều kiện cần quan sát.

### 7.2. Payload cần là dữ liệu hợp lệ của transport

Dùng serializer để tạo JSON chứa field như `LENGTH(reference)` hoặc `createdAt DESC`. Nếu JSON bị hỏng trước khi resolver chạy, test chỉ chứng minh parser từ chối JSON hỏng.

Với API query string, gửi đúng cách mã hóa tham số và quan sát cách binding giữ nhiều term. Nếu API có cả body và query parameter cho sort, xác định ưu tiên hoặc từ chối mâu thuẫn; test cả đường đã được công bố.

Tên cột/chiều sort là lựa chọn cấu trúc cần ánh xạ cố định, còn các giá trị dữ liệu tiếp tục được bind. Nguyên tắc này được giải thích tại [OWASP — SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html). Test chỉ với tên hợp lệ về cú pháp chưa bao phủ được ranh giới đó.

### 7.3. Giấu giá trị chưa chứng minh đã chặn dùng property

Một API trả các ID theo `internalRiskScore` nhưng không chứa field đó trong JSON vẫn có thể vi phạm hợp đồng. Test phải kiểm tra yêu cầu sử dụng field bị từ chối, không chỉ assert response không có key nhạy cảm.

Nếu API cố ý cho sort một chỉ số ẩn, quyền quan sát thứ tự đó phải được nêu rõ và có oracle riêng. Không suy ra quyền đó từ việc developer quên thêm field vào serializer.

Response lỗi cũng không nên liệt kê schema nội bộ hoặc stack trace. Nếu response có danh sách sort khả dụng, kiểm tra nó chỉ phản ánh lựa chọn công khai phù hợp với actor và operation.

## 8. Kiểm tra quyền đối tượng với mọi lựa chọn được phép

### 8.1. Quyền dùng field không làm rộng tập dữ liệu

Lặp test `createdAt`, `number` và `amount` với các actor phù hợp. Trên fixture A–F, mọi lựa chọn được phép đều chỉ chứa A, B, C khi filter PENDING_APPROVAL còn hiệu lực.

Điểm này bắt những lỗi như:

```text
Nhánh sort ngày dùng query có tenant/owner.
Nhánh sort số tiền chuyển sang query báo cáo toàn tenant.
Nhánh sort mã đơn bỏ filter trạng thái.
```

Chỉ kiểm tra sort ngày không phát hiện được những đường query thay thế này.

### 8.2. Metadata cần cùng phạm vi

`totalElements`, số trang, facet hoặc tổng tiền không được đếm từ tập rộng hơn chỉ vì nội dung đã được lọc. Với fixture tĩnh, tổng bằng 3 là một oracle có ý nghĩa để phát hiện D, E hoặc F bị tính nhầm.

Không trộn test tổng chính xác trên dữ liệu tĩnh với test dữ liệu đang thay đổi đồng thời mà không xác định mốc quan sát. Lệch count do hai snapshot đọc khác nhau là vấn đề khác với count thiếu predicate quyền.

### 8.3. Kiểm tra các thuộc tính do client tự khai

Nếu request có các field ngoài hợp đồng như `actorId`, `tenantId`, `financeUser` hoặc `allowedSortFields`, chúng không được nâng quyền. Tùy hợp đồng, API có thể từ chối field lạ hoặc bỏ qua, nhưng không được dùng chúng thay context tin cậy.

Test danh tính cần đi qua đúng luồng actor/tenant của ứng dụng. Một mock principal có role FINANCE nhưng không có quan hệ tenant không nên vô tình được dùng làm positive control cho quyền tài chính trong tenant bất kỳ.

## 9. Thứ tự nhiều khóa, null và ưu tiên nghiệp vụ

### 9.1. Test cả tính đúng thứ tự lẫn tính đầy đủ

Với dữ liệu tĩnh, duyệt các trang nhỏ rồi ghép ID. Kiểm tra:

```text
chuỗi ID đúng thứ tự đầy đủ đã xác định từ fixture
không có ID ngoài tập được phép
không trùng hoặc thiếu ID
khóa phân xử được giữ khi các giá trị sort chính bằng nhau
metadata và dấu hiệu còn trang sau đúng hợp đồng
```

Assertion chỉ nói “mọi phần tử trả về đều được phép” vẫn xanh với response rỗng. Assertion chỉ so tập ID không phát hiện được chiều sort bị đảo hoặc thứ tự nhiều term bị tráo.

### 9.2. Null placement và kiểu dữ liệu cần database thật

Nếu hỗ trợ field nullable, tạo các dòng null và non-null rồi kiểm tra vị trí null cho từng profile/chiều được phép. PostgreSQL mô tả null ordering và ý nghĩa từng khóa độc lập tại [Sorting Rows](https://www.postgresql.org/docs/18/queries-order.html).

Một database thay thế trong test có thể có quy tắc khác database triển khai. Với collation, kiểu tiền, enum hoặc biểu thức tính toán, hãy kiểm tra trên backend/provider phù hợp mục tiêu thay vì suy ra từ một comparator Java.

Mã đơn dạng chuỗi có thể cần thứ tự từ điển hoặc thứ tự phần số; test phải dùng kỳ vọng mà sản phẩm đã chọn. Đừng tự suy ra `PO-10` và `PO-2` phải theo một thứ tự chỉ vì chúng nhìn giống số.

### 9.3. Khóa ưu tiên bắt buộc không được client ghi đè

Nếu endpoint hàng đợi yêu cầu `priorityClass DESC` trước các term phụ, dựng fixture có dòng lớp cao nhưng giá trị phụ sẽ đứng cuối nếu client kiểm soát toàn bộ sort. Gửi mọi profile phụ được phép và xác nhận không dòng lớp thấp nào vượt lên trên lớp cao trái policy.

Test này kiểm tra quy tắc workflow, không chỉ field allowlist. Cũng cần bảo vệ đường ghi `priorityClass`; cho phép chọn khóa đúng không ngăn một actor sửa giá trị của khóa để nhảy hàng đợi.

## 10. Cache, cursor, thu hồi quyền và các đường truy cập khác

### 10.1. Cache hit phải được thử với actor khác quyền

Một kịch bản quan trọng:

1. Actor FINANCE thực hiện `amount ASC` để làm nóng cache.
2. Actor BASIC tìm cùng điều kiện và yêu cầu cùng sort.
3. Request BASIC vẫn bị từ chối theo policy, không nhận lại trang đã cache.
4. BASIC dùng `createdAt DESC` vẫn thành công và chỉ nhận phạm vi của mình.

Kịch bản này phân biệt lỗi quyền field với lỗi toàn bộ session không hoạt động. Kiểm tra cả cache nội bộ lẫn tầng cache triển khai nếu chúng có thể phục vụ response của endpoint.

### 10.2. Quyền đã đổi cần giữ đúng cam kết hệ thống

Trong hợp đồng kiểm tra quyền hiện hành, cho actor dùng `amount`, thu hồi quyền sort hoặc quyền đọc số tiền, rồi gửi request tiếp theo bằng cùng session/token còn hợp lệ theo cơ chế xác thực. API không được dùng grant cũ trong cache để tiếp tục cấp quyền trái cam kết.

Nếu sản phẩm sử dụng mô hình quyền có thời hạn khác, xác định rõ điểm quyết định và oracle tương ứng. Đừng vô tình yêu cầu thu hồi tức thời ở một test trong khi kiến trúc chỉ cam kết hết hiệu lực theo chu kỳ đã công bố.

### 10.3. Cursor không phải bằng chứng quyền sort

Tạo cursor với `amount ASC`, sau đó thử:

- Dùng cursor bằng actor hoặc tenant khác.
- Đổi sort thành `createdAt DESC` nhưng giữ cursor cũ.
- Dùng cursor sau khi quyền field bị thu hồi theo mô hình đang kiểm tra.
- Sửa phần sort/field trong token hoặc dùng token đã hết hạn.

Kết quả cần đúng hợp đồng tiếp tục hoặc lỗi đã định nghĩa. Không bỏ token rồi trả một trang theo sort mặc định, và không lấy property từ token chưa xác minh để bỏ qua policy hiện tại.

### 10.4. Export, job nền và API tương thích

Một hệ thống có thể bảo vệ API chính nhưng endpoint export vẫn nhận tên field tùy ý. Nếu có các đường đó, kiểm thử theo cùng operation/quyền đã định nghĩa: quyền submit, sort được phép, quyền khi worker thực thi và quyền tải kết quả.

Không suy từ một resolver unit test rằng mọi entry point đều gọi resolver. Test tích hợp cần chứng minh các đường thực tế giữ được ranh giới tương ứng.

## 11. Kiểm tra tác động nghiệp vụ và cách quan sát

### 11.1. Snapshot trước/sau phải thực sự độc lập

Bản chụp phục vụ test có thể gồm giá có thẩm quyền, trạng thái, người duyệt, quyết định, reservation và outbox/job nghiệp vụ liên quan. Đọc bằng transaction mới sau request và trả dữ liệu bất biến.

Không dùng cùng entity JPA đang được quản lý cho cả `before` và `after`. Hai biến có thể cùng nhìn dữ liệu đã bị sửa. Cũng không dựa vào transaction test tự rollback để kết luận request không để lại thay đổi đã commit.

Audit truy cập, audit từ chối hoặc metrics kỹ thuật có thể đổi theo thiết kế. Oracle cần phân biệt chúng với một quyết định duyệt hay công việc thanh toán không được phép phát sinh từ thao tác đọc.

### 11.2. Nếu có bất đồng bộ, kiểm tra cả lệnh chờ thực thi

Một request sort bị từ chối có thể chưa đổi trạng thái ngay nhưng đã tạo một job nghiệp vụ do interceptor lỗi. Quan sát cả outbox/queue và kết quả khi consumer kiểm soát được xử lý công việc liên quan.

Không dùng `verifyNoInteractions()` trên một mock ở controller làm bằng chứng cho toàn hệ thống. Một worker hoặc đường gọi khác có thể vẫn phát tác động. Với kiểm thử tương tác đồng thời, dùng barrier/latch tại điểm cần điều phối thay vì chỉ sleep.

### 11.3. Quan sát đúng ranh giới và tránh assertion quá giòn

Không nhất thiết so nguyên chuỗi SQL vì alias, quoting hoặc kế hoạch của provider có thể thay đổi mà policy vẫn đúng. Có thể assert cấu trúc normalized sort tại adapter, kết quả trên fixture độc lập và việc không có truy vấn dùng field bị cấm.

Tuy nhiên, chỉ kiểm tra normalized plan cũng không đủ nếu adapter cuối cùng ghép thêm input thô. Kết hợp quan sát cấu trúc với test tích hợp trên query thật cho những nhánh rủi ro cao.

## 12. Hồi quy trong CI và cách báo cáo lỗi

### 12.1. Một bộ kiểm thử nhỏ cần bắt được các thay đổi sai quan trọng

Các biến thể lỗi sau nên làm một hoặc nhiều test thất bại:

| Thay đổi sai | Test cần bắt |
| --- | --- |
| Đổi điều kiện hai quyền thành chỉ cần một quyền | Ma trận AMOUNT_READ_ONLY/AMOUNT_SORT_ONLY |
| Dùng reflection mở mọi property entity | Field nội bộ tồn tại nhưng không công bố |
| Truyền thẳng field vào `Sort.by` hoặc biểu thức query | Test ranh giới adapter và field/biểu thức ngoài hợp đồng |
| Bỏ tenant/owner ở nhánh amount | Fixture D/E và tổng số phần tử |
| Nhầm alias number sang createdAt | Oracle B, A, C thay vì A, C, B |
| Bỏ khóa phân xử | Fixture bằng khóa chính và test nhiều trang |
| Bắt lỗi rồi query lại không sort | Ca lỗi toàn request và quan sát không có fallback |
| Cache không xét quyền hiện hành | Test làm nóng cache và thu hồi quyền |

Danh sách này giúp đánh giá mục tiêu của bộ test. Nó không có nghĩa cần tự động tạo mọi biến thể lỗi hoặc chạy một vòng thay đổi code rộng chỉ để hoàn thành một bài viết.

Khi thêm property mới vào entity, mặc định nó không được trở thành sort công khai. Với một lựa chọn sort mới có chủ đích, cập nhật hợp đồng, ma trận, fixture và oracle của backend tương ứng.

### 12.2. Báo cáo phân biệt đúng tầng thất bại

```text
Case: BASIC-CANNOT-SORT-AMOUNT
Endpoint: POST /orders/search
Actor: chủ đơn tenant A, có quyền tìm đơn, thiếu quyền sort số tiền
Positive control: createdAt DESC trả 200 và đúng tập A/B/C
Attack input: amount ASC, JSON hợp lệ, session và CSRF hợp lệ
Expected: 400 INVALID_SORT, không thực hiện query đơn bằng amount
Observed: 200, thứ tự C/A/B, tổng 3
Conclusion: FAIL — phạm vi đối tượng đúng nhưng quyền dùng field bị bỏ qua
```

Một lỗi khác có thể chỉ xuất hiện ở backend:

```text
Case: NUMBER-ALIAS-MAPPING
Resolver output: reference ASC, id ASC
Expected IDs: B, A, C
Observed IDs from database path: A, C, B
Conclusion: FAIL — adapter/query không thực hiện sort đã được cấp quyền
```

Báo cáo nên ghi phiên bản policy, actor/tenant test, sort chuẩn hóa và lớp đã được kiểm tra. Không khẳng định đã kiểm tra proxy hoặc cache triển khai nếu ca chỉ chạy MockMvc.

## 13. Bài tập thực hành

Một dự án có các test hiện tại:

```text
- Mọi test dùng @WithMockUser với vai trò ADMIN.
- Ca sort bị cấm chỉ assert status không phải 200.
- Body trong ca âm có JSON sai.
- Repository được mock để luôn trả cùng danh sách ba đơn.
- Fixture có ngày, mã và amount đều tăng cùng ID.
- Không kiểm tra count, cursor, cache hoặc dữ liệu sau commit.
```

Hãy thiết kế lại bộ kiểm thử:

1. Xây ma trận BASIC, AMOUNT_READ_ONLY, AMOUNT_SORT_ONLY, FINANCE và NO_SEARCH.
2. Tạo các đơn A–F hoặc một fixture tương đương với thứ tự các field khác nhau và có dòng ngoài phạm vi.
3. Viết positive control và ca field bị cấm với transport, auth và CSRF hợp lệ theo cấu hình.
4. Chứng minh alias, direction, term phụ và khóa phân xử được backend thực thi đúng.
5. Kiểm tra field nội bộ có thật vẫn bị từ chối dù không xuất hiện trong JSON.
6. Thêm kịch bản cache hit và thu hồi quyền theo cam kết của hệ thống.
7. Xác định dữ liệu trước/sau và bằng chứng cần thiết để loại trừ tác động nghiệp vụ ngoài ý muốn.

Một bộ sort authorization tests có giá trị khi nó chứng minh cả quyền sử dụng lựa chọn sort, thứ tự dữ liệu thực tế và các invariant còn nguyên vẹn trên đường đọc, thay vì chỉ chứng minh một request đã bị từ chối ở đâu đó.
