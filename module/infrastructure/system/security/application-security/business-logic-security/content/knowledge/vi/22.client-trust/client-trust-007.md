# Client trust boundary tests — Kiểm thử ranh giới tin cậy với client

## 1. Kiểm thử phải chứng minh server tự giữ quy tắc

**Client trust boundary tests** là các bài kiểm thử xác minh dữ liệu do client kiểm soát không tự trở thành căn cứ cho quyền, giá, trạng thái workflow hoặc kết quả nghiệp vụ ở server.

Một UI ẩn nút phê duyệt chưa chứng minh API không cho người thiếu quyền phê duyệt. Một lỗi HTTP cũng chưa chứng minh request không làm đổi dữ liệu, giữ tồn hoặc đưa tác vụ vào hàng đợi.

Bài thuộc chương **Client Trust** của module `SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`. Trọng tâm là thiết kế kiểm thử cho các tình huống sửa giá, giả quyền, bỏ qua bước duyệt, thao tác ngoài object/tenant scope và replay request.

Câu hỏi cần trả lời là:

```text
Nếu client sửa hoặc bỏ qua mọi state trên giao diện,
server có còn quyết định theo bằng chứng và dữ liệu có thẩm quyền không?

Nếu server từ chối,
có chắc không có tác dụng nghiệp vụ trái phép đã commit không?
```

OWASP WSTG mô tả kiểm thử forged request như cách gửi trực tiếp dữ liệu hoặc thao tác mà frontend không cung cấp, nhằm xác minh logic backend không phụ thuộc vào luồng GUI dự kiến. [OWASP WSTG: Ability to Forge Requests](https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/10-Business_Logic/02-Ability_to_Forge_Requests/).

## 2. Xác định ranh giới và nguồn sự thật trước khi viết test

### 2.1. Lập bản đồ dữ liệu client có thể kiểm soát

| Dữ liệu hoặc trạng thái | Biến đổi cần thử | Nguồn server phải dùng |
| --- | --- | --- |
| Role/cờ `isAdmin`, `canApprove` | Tự tăng quyền trong body, header hoặc storage | Credential và dữ kiện authorization đã kiểm chứng |
| Tenant/resource selector | Đổi tenant, order ID, line ID | Tenant context và quyền trên đúng object/parent |
| Quantity/giá/tổng tiền | Đổi dấu, giá trị hoặc trường tính toán | Command hợp lệ, giá/policy server và phép tính có thẩm quyền |
| Workflow flags | Giả `approvalCompleted`, `currentStep`, `confirmed` | State machine và quyết định đã lưu |
| Version/quote ID | Dùng bản cũ hoặc quote của object khác | Version/binding hiện tại và điều kiện hiệu lực |
| Thời gian/countdown | Đổi giờ máy, expiry client | Nguồn thời gian và deadline server |
| Session/token | Sửa nội dung, dùng bằng chứng sai mục đích | Cơ chế xác thực/verify đúng profile và scope |
| Local draft/offline state | Gửi lại graph cũ, field server-only | Allowlist, quyền, version và domain rules |
| Idempotency key/cờ `used` | Xóa cờ client, đổi key, gửi lại | Kho kết quả, state và constraint server |

Không cần mọi ứng dụng dùng tất cả các cơ chế trong bảng. Test phải bám vào kiến trúc thật, kể cả các đường mobile, import hoặc service nhận cùng ý định nghiệp vụ.

### 2.2. Phân biệt ba loại input

- **Ý định:** quantity hoặc ghi chú mà user được phép đề nghị; server kiểm tra trước khi dùng.
- **Precondition:** version/hash mà client đang xem; server đối chiếu, không gán nó làm sự thật mới.
- **Bằng chứng:** session/token/quote được phát hành và bảo vệ theo một hợp đồng; phải verify đúng nguồn, mục đích và ngữ cảnh.

Test sửa một token làm chữ ký sai chủ yếu kiểm tra integrity. Test dùng một credential hợp lệ của người không có quyền kiểm tra authorization. Cần cả hai nếu hệ thống dùng những ranh giới đó.

### 2.3. Oracle phải độc lập với implementation đang kiểm tra

Oracle là căn cứ xác định kết quả đúng. Nó nên đến từ invariant, hợp đồng API và ma trận quyền được xem xét, không phải gọi lại chính hàm authorization để tính expected result.

Ví dụ “requester không được tự duyệt yêu cầu của mình” là expected behavior. Nếu test lấy role hiện tại rồi dùng cùng logic `canApprove()` của production để quyết định có mong đợi thành công không, test có thể lặp lại chính lỗi của implementation.

## 3. Chuẩn bị fixture có thể chứng minh lỗi

### 3.1. Bộ chủ thể và tài nguyên minh họa

| Fixture | Đặc điểm cần được lưu ở nguồn tin cậy |
| --- | --- |
| U-requester | Đọc được đơn của mình, không có quyền reviewer trên đơn đó |
| U-reviewer | Reviewer độc lập, được phân công, có quyền trong tenant A |
| U-unassigned | Có role reviewer ở A nhưng không có assignment/grant trên đơn đích |
| U-other-tenant | Có role tương tự trong tenant B |
| U-multi-tenant | Có quyền ở A và B nhưng mỗi request chọn một context |
| U-revoked | Phiên còn xác thực được, nguồn quyền nghiệp vụ đã bị thu hồi theo policy |
| Order-ready | Đủ điều kiện server để action cuối thành công |
| Order-needs-approval | Đúng kiểu dữ liệu nhưng thiếu phê duyệt bắt buộc |
| Quote-current | Đúng tenant, object, nội dung, người/phạm vi dùng và thời gian |
| Quote-foreign/stale | Có integrity hợp lệ nhưng sai binding hoặc đã hết hiệu lực |

Nguồn xác thực và quyền của fixture phải được thiết lập có kiểm soát. Đừng lấy role mà request tự gửi làm cơ sở dựng principal trong test.

### 3.2. Có cả tài nguyên của tenant khác và tài nguyên trùng local ID

Một ID chỉ tồn tại trong B giúp kiểm tra request context A không tìm hộ toàn cục. Một cặp local ID giống nhau trong A/B giúp phát hiện repository/cache chỉ dùng ID mà quên tenant.

Với ID trùng, request A phải thao tác đúng bản A và giữ B nguyên vẹn. Không coi việc cùng chuỗi ID tự nó là một request vào B; identity đầy đủ phụ thuộc mô hình tenant của hệ thống.

### 3.3. Fixture cần nhất quán, không vô tình làm mọi request thất bại

Quote, version, state, membership và tài nguyên phải hợp lệ đối với điều kiện **không phải mục tiêu** của test.

Ví dụ đang kiểm tra quyền reviewer thì dùng payload đúng schema, version hiện tại và object tồn tại. Nếu quote sai hoặc body thiếu field, request có thể bị chặn trước khi authorization được chạy.

Có thể seed dữ liệu server nhất quán cho test một boundary cụ thể; cần ghi rõ phạm vi đó. Kiểm thử workflow từ đầu đến cuối còn phải đi qua các bước tạo/gửi duyệt thật để tìm lỗi hình thành bằng chứng.

## 4. Mỗi negative test cần một đối chứng đi qua cùng đường xử lý

### 4.1. Phương pháp arrange–control–mutate–observe

```text
Arrange: chuẩn bị trạng thái server và principal đã biết.
Control: request hợp lệ tương đương có thể thành công.
Mutate: thay một giả định client hoặc điều kiện cần kiểm tra.
Observe: xem response, dữ liệu commit và tác dụng tiếp theo.
```

Đối chứng giúp bắt lỗi test gửi nhầm URL, sai content type, thiếu CSRF hoặc chưa đăng nhập. Nên dùng object/command độc lập cho control và negative case để kết quả control không làm fixture negative tự trở thành stale.

### 4.2. Không để lớp bảo vệ khác che mất lỗi mục tiêu

Một test “forged role phải bị chặn” có thể luôn nhận 403 vì thiếu CSRF token, dù application service đang tin `X-Client-Role`. Kết luận quyền được bảo vệ khi đó là sai.

Với ứng dụng cookie dùng CSRF protection, test authorization cần credential và CSRF hợp lệ. Test CSRF là nhóm riêng, chủ động dùng token thiếu/sai. Spring Security hỗ trợ `csrf()` cho các request kiểm thử và nêu yêu cầu token hợp lệ khi kiểm tra method không an toàn với CSRF đang bật. [Spring Security: Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/7.0/servlet/test/mockmvc/csrf.html).

Tương tự:

- Test workflow không nên thất bại chỉ vì actor không có capability gọi action.
- Test tenant không nên dùng resource ID gõ sai hoàn toàn mà fixture không biết có tồn tại.
- Test giá không nên chỉ gặp lỗi parse trước khi tới quyết định nghiệp vụ rồi kết luận server đã tính giá đúng.
- Test replay không nên dùng credential hết hạn ngoài chủ đích rồi coi tác dụng lặp đã được ngăn.

### 4.3. Kiểm tra lý do bị chặn theo hợp đồng an toàn

Nếu API có reason code ổn định và được phép lộ trong ngữ cảnh đó, assert reason phù hợp ngoài status. Nếu response chủ động che lý do, có thể dùng audit/trace nội bộ có kiểm soát để xác nhận boundary nào đã từ chối.

Không vì test muốn phân biệt mà yêu cầu production lộ tenant, owner, tồn kho hoặc chi tiết nhạy cảm cho caller không có quyền.

## 5. Chọn lớp test theo ranh giới cần chứng minh

| Lớp | Chứng minh tốt điều gì? | Không tự chứng minh |
| --- | --- | --- |
| Domain/policy unit test | Invariant, phép tính, transition với dữ kiện xác định | Parser/binder hoặc security filter thực tế |
| MVC integration | Mapping, deserialize, validation, filter và application flow được nạp | Hành vi của reverse proxy, browser hoặc container thật |
| Database integration | Constraint, transaction, khóa và dữ liệu commit | Mọi đường UI hoặc kênh message ngoài cấu hình test |
| HTTP test qua server thật | Wire format và routing/converter/container thực tế | State/cookie behavior của browser nếu không dùng browser |
| Browser test | UI, storage, cookie policy, tab và request thực sự phát đi | Toàn bộ khả năng gọi trực tiếp API không qua UI |
| Async integration | Message/event, retry, deduplication và side effect | Toàn quy trình nếu chỉ consumer được cô lập |

Spring MockMvc thực hiện xử lý Spring MVC qua mock request/response thay vì một server đang chạy. Gọi trực tiếp method controller còn bỏ qua nhiều thành phần như mapping, converter và validation của pipeline. [Spring Framework: MockMvc Overview](https://docs.spring.io/spring-framework/reference/7.1/testing/mockmvc/overview.html).

Không thay mọi dependency bằng mock rồi gọi đó là kiểm thử toàn ranh giới. Có thể stub hệ thống ngoài tại adapter để quan sát tác dụng, nhưng giữ implementation authorization, workflow và persistence thật khi chính chúng là mục tiêu.

Các test dùng helper giả principal/role vẫn hữu ích cho phạm vi riêng của chúng. Tuy nhiên, không dùng việc test tự gán authority tin cậy để chứng minh rằng một role tự khai trong browser không được tin.

## 6. Ví dụ Java: cờ role từ client không tạo quyền approve

### 6.1. Hợp đồng và giả định của ví dụ

Ví dụ có API approve chỉ nhận version kỳ vọng; principal thật lấy từ session. Header `X-Client-Role` không có thẩm quyền. Contract minh họa trả 403 với code `RESOURCE_ACTION_DENIED` khi actor đọc được đơn nhưng không có quyền action đó.

Test dùng application context/security filter chain thật và database kiểm thử thích hợp. `fixtures` tạo dữ liệu nhất quán; các session được lấy qua cơ chế đăng nhập của ứng dụng. `probe` đọc snapshot bất biến bằng transaction mới, không trả managed entity từ persistence context cũ.

```java
@Test
void clientRoleHeaderMustNotGrantApproval() throws Exception {
    ApprovalScenario control = fixtures.pendingOrderWithIndependentReviewer();

    mvc.perform(validApproveRequest(
            control, control.reviewerSession(), "control-approve-01"))
        .andExpect(status().isOk());

    probe.requireExactlyOneCommittedApproval(
        control.tenantId(), control.orderId());

    ApprovalScenario scenario = fixtures.pendingOrderReadableByRequester();
    BusinessSnapshot before = probe.readCommittedSnapshot(
        scenario.tenantId(), scenario.orderId());

    mvc.perform(validApproveRequest(
            scenario, scenario.requesterSession(), "forged-role-01")
            .header("X-Client-Role", "ADMIN"))
        .andExpect(status().isForbidden())
        .andExpect(jsonPath("$.code").value("RESOURCE_ACTION_DENIED"));

    BusinessSnapshot after = probe.readCommittedSnapshot(
        scenario.tenantId(), scenario.orderId());

    assertEquals(before.protectedBusinessData(), after.protectedBusinessData());
    assertEquals(before.committedDomainEvents(), after.committedDomainEvents());
}
```

Helper tạo request hợp lệ về các mặt còn lại:

```java
private MockHttpServletRequestBuilder validApproveRequest(
        ApprovalScenario scenario,
        MockHttpSession session,
        String idempotencyKey) throws Exception {

    String body = json.writeValueAsString(Map.of(
        "expectedVersion", scenario.orderVersion()));

    return post("/tenants/{tenantId}/orders/{orderId}/approve",
            scenario.tenantId(), scenario.orderId())
        .session(session)
        .with(csrf().asHeader())
        .header("Idempotency-Key", idempotencyKey)
        .contentType(MediaType.APPLICATION_JSON)
        .content(body);
}
```

Các API request/assertion thuộc Spring MVC/Spring Security Test và JUnit; fixture, probe và snapshot là hợp đồng minh họa chưa được triển khai trong bài.

### 6.2. Điều test này có và chưa chứng minh

Test có thể phát hiện việc biến header role không tin cậy thành quyền approve trong flow được nạp. Nó còn kiểm tra không có business state/domain event mới sau request bị chặn.

Nó chưa chứng minh mọi parser ở reverse proxy/container sẽ diễn giải giống MockMvc, cũng chưa kiểm tra localStorage, JWT hoặc mọi object/tenant combination. Cần các case bổ sung đúng ranh giới đó.

Security attempt, session last-seen hoặc metric có thể thay đổi hợp lệ. `protectedBusinessData` chỉ bao gồm dữ liệu cần bất biến khi deny, không được so sánh toàn bộ database một cách máy móc.

## 7. Nhóm kiểm thử field, giá và dữ liệu browser tự kết luận

### 7.1. Tách test input contract khỏi test nguồn thẩm quyền

Nếu command strict không nhận `total`, gửi thêm `total = 1` có thể phải trả lỗi schema và không mutation. Đó là kiểm thử command allowlist.

Để chứng minh tổng có thẩm quyền đúng, còn cần request hợp lệ mà server tính/tra giá thật, rồi assert receipt, order và các tác dụng dùng đúng tổng đó. Nếu API cho client gửi estimate hợp lệ, thay estimate không được làm nó trở thành số tiền có thẩm quyền.

Không kết luận toàn bộ logic tính giá đã an toàn chỉ vì một payload có field thừa bị trả 400.

### 7.2. Kiểm tra sâu vào object graph và các đường binding

Thử các field như owner, tenant, creator, role, trạng thái duyệt hoặc đơn giá ở root, array item và nested object mà adapter có thể nhận.

Các trường hợp cần có gồm:

- Field không có trong UI nhưng có trên entity/read model.
- Giá trị đúng enum/UUID nhưng không được client gán ở command hiện tại.
- Một child ID thuộc parent hoặc tenant khác.
- Map metadata chứa key có tên giống field quyền/trạng thái.
- Form binding và JSON body nếu ứng dụng hỗ trợ cả hai.
- Request qua adapter import/message sử dụng cùng ý định nghiệp vụ.

### 7.3. Duplicate parameter phải được gửi đúng dạng cần kiểm tra

Một `Map` Java không biểu diễn được hai key JSON giống nhau cùng tồn tại như raw payload. Nếu test duplicate key bằng cách put hai lần vào map, lần trước có thể đã mất trước khi request được gửi.

Để kiểm tra parser differential, cần gửi raw JSON có key lặp, form/query có nhiều occurrence hoặc body/query mâu thuẫn theo case. Test qua server/proxy thật khi mục tiêu là cách các thành phần diễn giải byte request, không chỉ trạng thái request object đã parse.

Lưu representation đã gửi và lý do từ chối. Không chỉ chụp một ảnh UI để chứng minh payload đã thật sự vượt qua frontend và tới boundary cần kiểm tra.

## 8. Nhóm kiểm thử bỏ bước, binding và bằng chứng được bảo vệ

### 8.1. Giả cờ hoàn thành và gọi trực tiếp action là hai case

Giả sử order cần phê duyệt nhưng client có thể gọi confirm:

```text
Case A: thêm approvalCompleted=true vào body.
Mục tiêu: không cho field này ghi đè state/bằng chứng server.

Case B: bỏ toàn bộ field giả, gọi confirm bằng command tối thiểu hợp lệ.
Mục tiêu: server vẫn phát hiện thiếu phê duyệt, dù caller mở thẳng bước cuối.
```

Nếu chỉ Case A bị từ chối bởi strict DTO, một endpoint thiếu workflow guard vẫn có thể qua Case B. Actor, quote và các dữ kiện khác của Case B cần hợp lệ để test thật sự nhắm vào precondition phê duyệt.

### 8.2. Integrity và binding phải được kiểm tra riêng

| Biến thể bằng chứng | Điều cần xác minh |
| --- | --- |
| Sửa payload nhưng giữ signature cũ | Không chấp nhận integrity sai |
| Bằng chứng hợp lệ cho object khác | Không dùng nhầm resource |
| Bằng chứng hợp lệ cho tenant/principal khác | Không vượt phạm vi được phép |
| Token/quote hợp lệ nhưng sai action/type | Không thay thế được bằng chứng của action hiện tại |
| Quote đã hết hạn | Thời gian server chi phối, không phải countdown browser |
| Quote đúng nhưng content version đã đổi | Không dùng cho quantity/giá/người nhận khác |
| Bằng chứng đã tiêu thụ | Không tạo thêm tác dụng bằng một lần dùng mới |

Một token sai chữ ký bị 401 không chứng minh object authorization đúng. Một token hợp lệ được cấp cho người không có quyền object là fixture cần thiết cho bài toán thứ hai.

### 8.3. Kiểm tra phản hồi và tác dụng cuối

Khi giả state hoặc dùng bằng chứng không hợp lệ, không được có decision thành công, reservation, xác nhận đơn hoặc message fulfillment mới. Nếu có event từ chối, phải được phân loại đúng và không làm consumer hiểu thành sự kiện nghiệp vụ đã commit.

Nếu ứng dụng dùng cờ return URL/callback client để hiển thị thành công, thử sửa cờ đó và xác minh trạng thái backend vẫn phụ thuộc bằng chứng từ nguồn có thẩm quyền theo tích hợp thực tế.

## 9. Stale state, deadline và thay đổi quyền

### 9.1. Không cần attacker để tạo state lỗi thời

Tạo hai tab hoặc hai client cùng đọc version V. Một client thay nội dung thành V+1; client còn lại gửi command cũ. Assert đúng conflict hoặc quy trình xác nhận lại theo hợp đồng, và không có dữ liệu cũ ghi đè ngoài policy.

Làm tương tự với đổi owner, hủy order hoặc cập nhật policy/giá. Chỉ thay state UI mà không thay server giúp kiểm tra client không tạo thẩm quyền; thay server trong khi giữ UI cũ giúp kiểm tra server không tin snapshot client lỗi thời.

### 9.2. Dùng nguồn thời gian mà code ra quyết định thật sự đọc

Test các mốc trước, đúng và sau deadline theo quy ước đã định nghĩa, ví dụ `< expiresAt` là còn hiệu lực còn `>= expiresAt` là hết hạn.

Không dùng thay đổi giờ browser để giả lập server hết hạn. Nếu domain dùng clock được inject, điều khiển đúng clock đó. Nếu quyết định dùng thời gian database, việc đổi một Java `Clock` không tự làm database clock đổi; fixture/harness cần kiểm soát đúng boundary thời gian của implementation.

Tránh dùng sleep dài hoặc mốc sát đến mức test phụ thuộc lịch chạy CI. Cần dữ liệu thời gian và điểm điều phối đủ xác định cho invariant được kiểm tra.

### 9.3. Thu hồi quyền cần assert đúng hợp đồng độ mới

Giữ session/browser state cũ rồi thu hồi role hoặc membership tại nguồn. Gọi action tiếp theo và kiểm tra theo policy:

- Nếu cam kết kiểm tra quyền hiện tại ở mỗi lần quyết định, request mới không được dùng role cũ.
- Nếu có cửa sổ cache được phép, kiểm tra cả trong và sau giới hạn đó cùng cơ chế không tiếp tục dùng dữ liệu quá cũ khi nguồn lỗi.
- Nếu có hàng rào tuần tự hóa, kiểm tra cả hai thứ tự action và thu hồi tranh chấp khóa.

Không đòi “thu hồi tức thì” trong test khi kiến trúc chỉ cam kết độ trễ mà không sửa hợp đồng. Cũng không hạ expected result để hợp thức hóa một cửa sổ không có giới hạn đã được công bố.

## 10. Replay, concurrency và tác vụ nền

### 10.1. Client xóa cờ đã dùng không được mở lại operation

Sau một confirm/approve/consume thành công, xóa cờ local `used` hoặc gửi từ browser khác rồi replay. Kết quả có thể là receipt cũ hoặc từ chối thao tác mới theo contract, nhưng không có tác dụng nghiệp vụ bổ sung.

Phân biệt các case:

- Cùng key, cùng semantic input: một hiệu ứng, receipt phù hợp.
- Cùng key, đổi object/quantity/action: xung đột theo fingerprint/scope.
- Key mới, cùng object/bằng chứng đã dùng: state/constraint vẫn chặn thực hiện lặp.
- Cùng key ở tenant/principal khác: không trả nhầm receipt hoặc chia sẻ kết quả ngoài quyền.

### 10.2. Tạo tranh chấp thật thay vì gọi tuần tự

Hai request cùng quota/tồn hoặc cùng version cần được chạy với hai transaction thực sự độc lập. Dùng barrier/latch hoặc khóa hàng được điều phối trong harness để tạo thứ tự cần kiểm chứng.

Không chỉ chạy một vòng lặp nhiều lần rồi kỳ vọng scheduler ngẫu nhiên sẽ tạo race. Đặt timeout rõ để test không treo, và đọc kết quả từ nguồn đã commit.

Ví dụ invariant cho hai confirm tranh cùng order:

```text
Số chuyển trạng thái confirm có hiệu lực = 1
Số intent fulfillment chuẩn = 1
Tồn/quota chỉ bị sử dụng cho một lần confirm
Request còn lại có kết quả theo contract, không có hiệu ứng mới.
```

### 10.3. Outbox và side effect cần được quan sát có kiểm soát

Đếm lời gọi mock notifier ngay sau response có thể bỏ sót job chạy trễ. Kiểm tra outbox/intent đã commit và chạy dispatcher/consumer trong harness theo cách kiểm soát được khi side effect là mục tiêu.

Nếu message được giao lại, xác minh deduplication hoặc transition tại nơi nhận chỉ tạo một hiệu ứng. Stub hệ thống ngoài có thể ghi nhận lần nhận theo event/correlation ID, nhưng không thay toàn bộ logic publisher/consumer bằng mock rồi suy ra chúng đúng.

Job được enqueue trước khi quyền thay đổi cần được assert theo policy tiếp tục hoặc kiểm tra lại đã chọn. Một ý định đã được chấp nhận hợp lệ không mặc nhiên phải hủy, và một message có `requestedBy` cũng không tự là bằng chứng quyền còn hiệu lực.

## 11. Snapshot và assertion không bị transaction test che lỗi

### 11.1. Những dữ liệu cần quan sát

| Nhóm | Ví dụ assertion |
| --- | --- |
| Resource | Tenant, owner, state, version và binding nội dung không đổi trái phép |
| Quyết định | Không có approve/confirm hợp lệ sinh từ client flag giả |
| Giá và lượng | Tổng có thẩm quyền không lấy từ payload ngoài hợp đồng |
| Tài nguyên | Reservation, used quota, inventory giữ đúng invariant |
| Event | Không có committed domain event/intent ngoài quyền |
| Dữ liệu trả về | Không lộ receipt, field hoặc tài nguyên khác tenant/principal |
| Bằng chứng nguồn | Actor, thời gian và policy/evidence reference đến từ nguồn đúng |

Không assert mọi bảng đều bất biến: security log, rate-limit counter hoặc session activity có thể thay đổi hợp lệ. Phải xác định phần business state được bảo vệ theo từng action.

### 11.2. Đọc committed state bằng transaction độc lập

Nếu test bọc toàn bộ kịch bản trong transaction ngoài rồi rollback ở cuối, request chạy cùng thread có thể vô tình tham gia transaction test. Khi đó test không phản ánh ranh giới commit của production và có thể che một mutation xảy ra trước khi trả lỗi.

Fixture cần được commit trước request. Probe sau request phải dùng transaction/connection phù hợp và tránh persistence cache cũ. Snapshot “before” phải là value copy bất biến; đừng giữ cùng managed entity rồi so sánh với chính object đã bị mutate.

Nếu production phụ thuộc tính năng database cụ thể như row lock, RLS hoặc constraint, dùng database kiểm thử có semantics tương ứng cho các test đó. Một repository mock không chứng minh được tính nguyên tử.

### 11.3. Lỗi HTTP sau side effect vẫn là test thất bại

Một implementation có thể ghi trạng thái rồi ném lỗi trong lúc serialize response. API trả 500 nhưng action ngoài quyền đã xảy ra. Vì vậy “không phải 2xx” không phải oracle đủ cho negative security test.

Ngược lại, một replay có thể trả 200 hợp lệ với receipt cũ mà không tạo tác dụng mới. Test cần hiểu contract để phân biệt response thành công với operation được thực hiện thêm lần nữa.

## 12. Ma trận regression và chất lượng của bộ kiểm thử

### 12.1. Một ma trận tối thiểu theo ranh giới

| Mã minh họa | Client mutation hoặc tình huống | Kết quả cần giữ |
| --- | --- | --- |
| CTB-AUTH-01 | Tự khai role/admin trong header/body/storage | Không tăng quyền server |
| CTB-OBJ-01 | Actor hợp lệ đổi object/parent ID | Chỉ thao tác resource được phép |
| CTB-TENANT-01 | Đổi tenant hoặc dùng ID B-only trong context A | Không fallback hoặc lộ/tác động B |
| CTB-FIELD-01 | Thêm field owner/state/approvedBy/price | Đúng allowlist và không mutation nhạy cảm |
| CTB-PARSE-01 | Duplicate field, body/query mâu thuẫn | Không có cách diễn giải khác nhau để bypass |
| CTB-FLOW-01 | Gọi trực tiếp bước cuối bằng command tối thiểu | Server kiểm tra đủ precondition |
| CTB-EVID-01 | Bằng chứng hợp lệ nhưng sai type/object/subject | Binding chặn dùng sai ngữ cảnh |
| CTB-TIME-01 | Sửa countdown và test biên deadline server | Backend time quyết định |
| CTB-STALE-01 | UI cũ sau đổi quantity/owner/policy | Không ghi nội dung lỗi thời ngoài contract |
| CTB-REVOKE-01 | Session còn sống nhưng nguồn quyền bị gỡ | Đúng cam kết hiệu lực/độ mới |
| CTB-REPLAY-01 | Xóa cờ local và gửi lại cùng/key mới | Một hiệu ứng theo state/idempotency |
| CTB-RACE-01 | Hai request cùng tranh state/quota/tồn | Invariant đúng trên tổng commit |
| CTB-ASYNC-01 | Job/event mang state client hoặc được giao lại | Đúng nguồn dữ liệu, scope và số hiệu ứng |
| CTB-OFFLINE-01 | Đồng bộ graph cũ có field server-only | Không mass assignment hoặc đổi scope |

OWASP mô tả việc tự động hóa ma trận authorization theo feature, role và dữ liệu để duy trì kiểm tra khi hệ thống thay đổi. Với client trust boundary, nên bổ sung state, nguồn bằng chứng và tác dụng nghiệp vụ vào các chiều cần thiết. [OWASP Authorization Testing Automation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Testing_Automation_Cheat_Sheet.html).

### 12.2. Không cần nhân mọi chiều một cách máy móc

Ưu tiên các tổ hợp có khả năng phá ranh giới: role hợp lệ nhưng object sai, token hợp lệ nhưng binding sai, command hợp lệ nhưng workflow thiếu bước, request được xác thực nhưng state client lỗi thời.

Các tổ hợp parse sai, thiếu đăng nhập và sai CSRF có nhóm test riêng. Chúng không thay thế các case đi sâu đến đúng quyết định nghiệp vụ.

Có thể dùng parameterized/property-based tests cho biến thể payload, nhưng expected behavior phải được gắn với contract. Ví dụ field metadata bị bỏ qua theo một API không có cùng expected status với API strict từ chối unknown field.

### 12.3. Đánh giá test có thực sự bắt lỗi không

Trong một build/harness kiểm thử được kiểm soát, có thể đánh giá sức mạnh test bằng thay đổi lỗi có chủ đích: bỏ workflow guard, dùng total client hoặc tin header role. Test mục tiêu phải thất bại vì invariant bị phá.

Nếu test vẫn xanh, xem nó có đang bị CSRF/authentication/schema chặn sớm, mock đã trả sẵn deny hoặc chỉ quan sát UI không. Không đưa các biến thể làm yếu kiểm soát đó vào đường production.

Khi thêm field, adapter, token profile, role hoặc transition mới, cập nhật ma trận và assertion tương ứng. Một danh sách test dài nhưng không chạm trust boundary mới không tạo coverage thực chất.

Các đoạn Java và kịch bản trong bài là minh họa thiết kế bộ kiểm thử; chúng chưa được chạy trên một ứng dụng hoàn chỉnh.

## 13. Bài tập áp dụng

Một SPA giữ tenant, role, total, `approvalCompleted` và quote trong localStorage. API dùng session cookie có CSRF protection. Worker xử lý fulfillment bất đồng bộ. Một test hiện tại chỉ gửi request thiếu CSRF, thấy 403 và kết luận user không thể tự phê duyệt.

Hãy thiết kế lại bộ kiểm thử:

1. Tạo fixture và positive control nào để chứng minh request đã tới đúng boundary?
2. Tách test giả role, command allowlist và gọi thẳng bước cuối như thế nào để chúng không che lỗi cho nhau?
3. Bằng chứng integrity sai và bằng chứng đúng nhưng sai object/tenant cần các case khác nhau nào?
4. State, inventory/quota, decision và outbox nào phải bất biến khi deny?
5. Làm sao quan sát committed state và side effect mà transaction test hoặc mock không che lỗi?
6. Tab cũ, role bị thu hồi, quote hết hạn và hai request đồng thời được điều phối ra sao theo contract đã chọn?
7. Những mutant có kiểm soát nào giúp chứng minh test thật sự phát hiện việc backend tin client?

Một bộ client trust boundary tests có giá trị phải đi qua đúng ranh giới thực thi và dùng oracle độc lập với implementation. Kết quả cần chứng minh là dữ liệu client tự kết luận không tạo ra thẩm quyền hoặc tác dụng nghiệp vụ ngoài policy, kể cả khi request bỏ qua UI, dùng state cũ, bị replay hoặc chạy đồng thời.
