# Xác minh hành vi và xóa cấu trúc cũ đã được thay thế

## Mục tiêu

Khi cải tiến một ứng dụng MVC, nhóm phát triển thường thay một Controller, service, route, View template hoặc cơ chế lưu trữ bằng cấu trúc mới. Việc tạo đường đi mới chưa có nghĩa là thay thế đã hoàn tất. Ứng dụng có thể vẫn gọi code cũ qua một endpoint khác, một job nền, một test fixture hoặc một template chưa được cập nhật. Nếu xóa cấu trúc cũ quá sớm, hành vi đang được người dùng hoặc hệ thống khác phụ thuộc có thể bị mất.

Refactor hoàn chỉnh cần hai việc đi cùng nhau: chứng minh hành vi cần giữ vẫn đúng sau thay đổi, và loại bỏ đường triển khai cũ khi không còn consumer hợp lệ. Kiểm thử giúp phát hiện thay đổi ngoài ý muốn; tìm kiếm tham chiếu, quan sát runtime và kiểm tra hợp đồng giúp xác nhận cấu trúc cũ thực sự không còn được dùng.

Bài học này trình bày cách ghi nhận hành vi hiện tại, xây dựng kiểm thử hồi quy, thay thế theo từng lát cắt và dọn code cũ an toàn trong ứng dụng MVC. Ví dụ sử dụng Java, Spring MVC và Spring Security.

Sau khi học, người học có thể:

- Xác định hành vi cần được giữ khi thay thế một cấu trúc MVC.
- Viết characterization test trước khi refactor.
- Phân biệt kiểm thử hành vi với kiểm thử chi tiết triển khai.
- Thay thế Controller, service, route, View và persistence theo từng bước.
- Phát hiện caller, route, template, cấu hình và dependency cũ còn sót.
- Xử lý tương thích API, form cũ, session và dữ liệu trong giai đoạn chuyển đổi.
- Xóa code cũ mà không làm mất hợp đồng cần duy trì.
- Xác nhận thay đổi bằng test, tìm kiếm tham chiếu, quan sát runtime và review.

## 1. Refactor chưa hoàn tất khi cấu trúc cũ vẫn còn đường chạy

Giả sử ứng dụng có một Controller cũ xử lý việc hủy đơn hàng. Nhóm phát triển tạo use case mới và Controller mới để phân chia trách nhiệm tốt hơn.

Sau khi thêm code mới, hệ thống có thể tồn tại đồng thời:

- Route cũ vẫn ánh xạ đến LegacyOrderController.
- Route mới gọi CancelOrder use case.
- Một trang cũ vẫn submit form đến URL cũ.
- Một job nền gọi LegacyOrderService.
- Một test vẫn khởi tạo trực tiếp class cũ.
- Cấu hình Spring vẫn đăng ký bean cũ.
- Một feature flag vẫn chọn giữa hai implementation.

Nếu chỉ kiểm thử route mới, nhóm chưa biết liệu route cũ còn được sử dụng hay không. Nếu xóa class cũ ngay, một caller chưa được phát hiện có thể gây lỗi runtime.

### Ba trạng thái của một lần thay thế

| Trạng thái | Mô tả | Việc cần làm |
|---|---|---|
| Chưa thay thế | Đường cũ là implementation đang hoạt động | Ghi nhận hành vi và thiết kế đường mới |
| Chuyển tiếp | Đường mới đã có, một số caller còn dùng đường cũ | Chuyển consumer, theo dõi và kiểm tra tương thích |
| Hoàn tất | Consumer cần thiết đã chuyển, đường cũ không còn được gọi | Xóa code, route, cấu hình và test lỗi thời |

Một cấu trúc cũ chỉ nên bị xóa sau khi xác định rõ phạm vi phụ thuộc và có bằng chứng rằng đường mới đáp ứng các hành vi cần giữ.

## 2. Xác định chính xác điều gì cần được giữ

Trước khi thay thế, hãy mô tả hành vi từ góc nhìn của client và nghiệp vụ. Đừng bắt đầu bằng việc liệt kê class cần đổi; hãy bắt đầu bằng những gì hệ thống phải tiếp tục làm.

Với một endpoint MVC, hành vi có thể gồm:

- HTTP method và URL.
- Authentication và authorization.
- Request parameter, header, form field và body.
- Validation và thông báo lỗi.
- HTTP status, redirect và response header.
- JSON schema hoặc tên View.
- Model attributes được template sử dụng.
- Thay đổi dữ liệu và transaction boundary.
- Event, email, audit record hoặc side effect.
- Idempotency, concurrency và thứ tự xử lý.
- Logging, metric và trace cần thiết.

### Ví dụ hợp đồng của thao tác hủy đơn hàng

| Tình huống | Hành vi cần giữ |
|---|---|
| Chủ đơn hàng hủy đơn đang chờ | Thành công, trạng thái chuyển sang CANCELLED |
| Người khác hủy đơn | Bị từ chối, dữ liệu không đổi |
| Đơn đã giao | Trả lỗi conflict theo hợp đồng |
| Đơn không tồn tại | Trả 404 hoặc thông báo không tiết lộ theo chính sách |
| Request thiếu CSRF token với session cookie | Bị security filter từ chối |
| Gửi lại cùng yêu cầu | Không tạo tác dụng phụ trùng ngoài chính sách |
| Hủy thành công | Audit/event được ghi đúng một lần theo semantics của use case |

Hợp đồng có thể thay đổi nếu sản phẩm yêu cầu, nhưng thay đổi đó phải được chủ ý ghi nhận. Refactor thuần túy không nên vô tình đổi status code, quyền truy cập, format lỗi hoặc tác dụng phụ.

### Phân biệt hành vi công khai và chi tiết nội bộ

Hành vi công khai là điều client hoặc consumer có quyền dựa vào: URL, method, status, response schema, semantics nghiệp vụ và các side effect đã cam kết.

Chi tiết nội bộ là cách triển khai: tên method private, thứ tự gọi helper không quan sát được, tên biến hoặc class tạm thời. Không cần giữ những chi tiết này chỉ vì chúng từng tồn tại.

## 3. Characterization test: ghi lại hành vi trước khi sửa

Characterization test là kiểm thử ghi nhận hành vi hiện tại của một hệ thống, đặc biệt hữu ích khi code cũ thiếu tài liệu hoặc khó xác định đầy đủ quy tắc.

Mục tiêu không phải khẳng định implementation cũ hoàn hảo. Test giúp tạo một đường cơ sở có thể so sánh trước và sau refactor.

### Một ví dụ với MockMvc

    @WebMvcTest(LegacyOrderController.class)
    class LegacyOrderControllerCharacterizationTest {

        @Autowired
        MockMvc mockMvc;

        @Test
        @WithMockUser(username = "alice", roles = "USER")
        void cancelPendingOrderRedirectsToOrderDetails() throws Exception {
            mockMvc.perform(post("/orders/42/cancel")
                            .with(csrf()))
                    .andExpect(status().is3xxRedirection())
                    .andExpect(redirectedUrl("/orders/42"));
        }
    }

Ví dụ này chỉ minh họa cấu trúc. Test thực tế cần cấu hình service và dữ liệu để phản ánh hành vi của ứng dụng. Không nên ghi một expected value theo suy đoán rồi xem đó là hợp đồng.

### Ghi nhận response đầy đủ

Với endpoint quan trọng, kiểm tra:

- Status code.
- Location header nếu redirect.
- Content-Type và response body.
- Error code và cấu trúc lỗi.
- Model attributes hoặc tên View với server-rendered MVC.
- Cookie hoặc header bảo mật liên quan.
- Số lần use case hoặc dependency được gọi nếu đó là bảo đảm quan trọng.

Không cần assert mọi header mặc định của framework. Chỉ ghi nhận những gì thuộc hợp đồng hoặc có ý nghĩa vận hành.

### Ghi nhận side effect

Một request có thể trả response đúng nhưng vẫn ghi dữ liệu sai. Characterization test nên kiểm tra database hoặc dependency quan trọng:

- Trạng thái đơn hàng sau khi hủy.
- Số lượng bản ghi audit.
- Event được phát ra.
- Email hoặc message được lên lịch.
- Không có cập nhật khi request bị từ chối.

Nếu test dùng mock, có thể xác nhận phương thức save hoặc publish không được gọi. Với transaction và persistence thực, integration test sẽ cung cấp bằng chứng mạnh hơn.

## 4. Kiểm thử theo nhiều tầng trước khi refactor

Không nên chỉ có một end-to-end test cho toàn bộ luồng. Chia test theo trách nhiệm giúp xác định hành vi nào được giữ và lỗi xuất hiện ở đâu.

| Tầng test | Điều cần xác nhận |
|---|---|
| Unit test domain | Quy tắc trạng thái và bất biến nghiệp vụ |
| Application service test | Trình tự use case, quyền và side effect |
| MVC slice test | Mapping, binding, validation, status và View/body |
| Persistence integration test | Truy vấn, transaction và dữ liệu được lưu |
| Security integration test | Authentication, authorization và CSRF |
| End-to-end test | Người dùng hoàn thành luồng thực tế |

Ví dụ, quy tắc đơn đã giao không thể hủy nên được kiểm thử ở domain/application layer. Việc POST /orders/42/cancel trả 409 là trách nhiệm của HTTP adapter. Hai test này bổ sung cho nhau.

### Tránh test phụ thuộc implementation cũ

Nếu test chỉ khẳng định Controller gọi đúng một helper cụ thể, test sẽ cản trở refactor dù hành vi không đổi. Hãy ưu tiên assert kết quả quan sát được và ranh giới có ý nghĩa.

Có thể giữ một số interaction test để bảo đảm security hoặc transaction dependency không bị gọi khi điều kiện không hợp lệ. Tuy nhiên, đừng biến mọi lời gọi nội bộ thành hợp đồng.

## 5. Tách test hồi quy khỏi test của implementation cũ

Khi thay cấu trúc, một số test cũ có thể kiểm tra trực tiếp class đã bị thay thế. Không nên xóa tất cả test cũ một cách máy móc.

Hãy phân loại:

- **Behavior test:** mô tả hành vi cần giữ; chuyển sang test của implementation mới hoặc test ở tầng phù hợp.
- **Characterization test:** ghi nhận hành vi cũ; giữ làm tài liệu tạm thời hoặc chuyển assertion sang đường mới.
- **Implementation test:** kiểm tra chi tiết class cũ; xóa khi class không còn.
- **Compatibility test:** xác nhận contract cũ vẫn hoạt động trong giai đoạn deprecation.
- **Obsolete test:** chỉ kiểm tra hành vi đã được sản phẩm chủ ý loại bỏ; cập nhật hoặc xóa cùng quyết định thay đổi.

Không để test cũ tiếp tục chạy bằng cách khởi tạo một implementation đã bị loại bỏ chỉ vì test đó từng có sẵn. Điều đó có thể khiến test suite xanh trong khi production đã chuyển sang một đường khác.

## 6. Thay thế theo lát cắt nhỏ

Một thay đổi lớn có thể chạm nhiều Controller, service, template và repository cùng lúc. Nếu thay tất cả trong một lần, khi test thất bại sẽ khó xác định nguyên nhân.

Thay theo lát cắt dọc (vertical slice) giúp mỗi bước có thể kiểm thử và review.

Ví dụ quy trình:

1. Tạo use case mới với hợp đồng input/output rõ ràng.
2. Chuyển một Controller gọi use case mới.
3. Chạy unit và MVC tests của endpoint đó.
4. Chuyển template hoặc client liên quan.
5. Chuyển consumer tiếp theo.
6. Theo dõi lỗi và xác nhận đường mới hoạt động.
7. Chỉ khi mọi consumer đã chuyển mới xóa implementation cũ.

Một lát cắt nên hoàn chỉnh từ request đến persistence/response trong phạm vi chức năng cụ thể. Tránh tạo một service mới nhưng vẫn để Controller cũ thực hiện toàn bộ nghiệp vụ.

### Không tạo hai nguồn dữ liệu có thẩm quyền

Trong giai đoạn chuyển tiếp, tránh để implementation cũ và mới cùng ghi một dữ liệu theo các quy tắc khác nhau. Nếu cần chạy song song để so sánh, chỉ dùng shadow/read-only execution hoặc một chiến lược dual-write có thiết kế idempotency, reconciliation và xử lý lỗi rõ ràng.

Không gọi hai implementation có side effect trên cùng request chỉ để “so sánh kết quả”. Điều đó có thể tạo hai lần thanh toán, gửi email hoặc phát event.

## 7. Chuyển đổi route và endpoint cũ

Route là hợp đồng với browser, mobile client, bookmark, email link hoặc hệ thống tích hợp. Xóa route cũ có thể làm hỏng consumer chưa được kiểm soát.

### Các lựa chọn

**Giữ route và đổi implementation:** Nếu URL vẫn là hợp đồng cần hỗ trợ, giữ mapping cũ nhưng để nó gọi use case mới. Đây thường là cách đơn giản nhất khi chỉ thay cấu trúc nội bộ.

**Redirect route:** Với trang HTML, có thể chuyển hướng từ URL cũ sang URL mới nếu semantics và method cho phép. Redirect cần xem xét method, body và khả năng gửi lại request. Không dùng redirect GET một cách tùy tiện để thay thế một POST có tác dụng phụ.

**Deprecate API:** Với API công khai, có thể thông báo phiên bản cũ sắp ngừng hỗ trợ, ghi nhận consumer và thời điểm kết thúc. Duy trì compatibility trong thời hạn đã công bố.

**Xóa route:** Chỉ thực hiện khi đã xác nhận không còn consumer cần route đó hoặc quyết định sản phẩm cho phép breaking change.

### Không để hai mapping trùng nhau

Khi route cũ và mới cùng tồn tại, phải xác định rõ path, method và điều kiện mapping. Hai handler cùng khớp một request có thể gây ambiguous mapping hoặc khiến hành vi phụ thuộc cấu hình.

Nếu route cũ chỉ là alias, nên để alias gọi cùng use case thay vì sao chép lại nghiệp vụ.

## 8. Chuyển template, form và static assets

View template cũng là consumer của Model và endpoint. Một template cũ có thể tiếp tục gửi field hoặc gọi URL đã bị thay thế.

Trước khi xóa template cũ, kiểm tra:

- Có Controller nào còn trả tên View đó không?
- Có fragment hoặc layout nào include template đó không?
- Có redirect hoặc error handler nào dẫn đến template không?
- Có email hoặc PDF renderer dùng chung template không?
- Có static JavaScript nào còn gọi endpoint cũ không?
- Có form đang mở trong browser gửi field theo contract cũ không?

### Form đã mở trước khi deploy

Người dùng có thể mở form rồi để đó trước khi ứng dụng được triển khai. Sau deploy, form cũ mới được submit. Nếu server mới không còn chấp nhận field hoặc CSRF/session token cũ theo chính sách, request có thể thất bại.

Hãy xem xét thời gian sống của form, session và browser tab. Có thể giữ tên field cũ trong một giai đoạn hoặc trả lỗi stale-form thân thiện. Không nên giữ vĩnh viễn một contract cũ nếu đã có kế hoạch kết thúc rõ ràng.

### Static assets

JavaScript cũ có thể còn nằm trong browser cache hoặc CDN. Nếu HTML mới được deploy nhưng asset cũ gọi API cũ, người dùng có thể gặp lỗi không đồng nhất.

Dùng fingerprinted asset, version manifest và thời gian lưu asset cũ phù hợp. Chỉ xóa file cũ khi không còn HTML hoặc client hợp lệ tham chiếu.

## 9. Chuyển đổi bean, dependency và cấu hình Spring

Một class cũ có thể không còn được gọi trực tiếp nhưng vẫn được tạo bởi component scanning hoặc configuration.

Hãy kiểm tra:

- Annotation Component, Service, Repository hoặc Controller còn tồn tại không.
- Bean có được khai báo trong @Configuration không.
- Có @Import hoặc @ComponentScan đặc biệt không.
- Có qualifier hoặc injection point còn tham chiếu bean cũ không.
- Có profile hoặc conditional bean tạo implementation cũ không.
- Có scheduled job, event listener hoặc message consumer gọi service cũ không.
- Có reflection, serialization hoặc tên class trong cấu hình không.

### Hai bean cùng interface

Nếu implementation mới và cũ cùng implement một interface, Spring có thể gặp lỗi nhiều bean hoặc chọn nhầm bean theo qualifier/primary. Không nên để hai implementation cùng hoạt động vô thời hạn mà không có cơ chế lựa chọn rõ.

Trong giai đoạn chuyển đổi, có thể dùng một adapter tạm thời hoặc feature flag có giới hạn. Sau khi chuyển xong, xóa bean cũ và các qualifier/flag chỉ phục vụ migration.

### Cấu hình lỗi thời

Xóa cấu hình liên quan khi không còn consumer:

- Property chỉ dùng cho implementation cũ.
- Feature flag đã kết thúc.
- Bean override hoặc profile migration.
- Route mapping cũ.
- Cache namespace cũ.
- Scheduled task cũ.
- Permission hoặc role chỉ phục vụ endpoint đã bỏ.

Đừng xóa một property chỉ vì tên có chữ legacy. Hãy xác nhận không còn code hoặc môi trường triển khai nào đọc nó.

## 10. Xóa code cũ theo thứ tự phụ thuộc

Khi cấu trúc mới đã hoạt động, hãy loại bỏ các phần cũ theo dependency graph. Xóa từ consumer đến implementation thường dễ kiểm soát hơn.

Một thứ tự tham khảo:

1. Chuyển các Controller hoặc adapter còn gọi service cũ.
2. Chuyển job, listener, scheduler và integration consumer.
3. Chuyển template, fragment và client gọi endpoint cũ.
4. Xóa route alias hoặc compatibility adapter nếu hết thời hạn.
5. Xóa service, mapper, validator và repository adapter cũ.
6. Xóa bean/configuration/feature flag chỉ phục vụ đường cũ.
7. Xóa test chỉ kiểm tra implementation cũ; chuyển behavior test sang cấu trúc mới.
8. Xóa migration helper hoặc dữ liệu tạm khi đã xác nhận không cần nữa.
9. Cập nhật tài liệu vận hành và runbook có tham chiếu cũ.

Thứ tự thực tế phụ thuộc dependency. Có thể cần giữ một adapter tương thích để route cũ gọi use case mới; adapter đó không phải implementation cũ nếu nó không còn chứa nghiệp vụ cũ.

### Không xóa file chỉ dựa trên tên

Tên Legacy hoặc Old là tín hiệu để điều tra, không phải bằng chứng đủ để xóa. Ngược lại, một class có tên bình thường vẫn có thể là implementation cũ. Cần xem caller, bean registration, runtime path và vai trò thực tế.

## 11. Tìm tham chiếu tĩnh và xác nhận runtime

Sau khi chuyển consumer, tìm các tham chiếu còn lại trong source và cấu hình. Có thể dùng công cụ tìm kiếm mã nguồn như ripgrep hoặc IDE Find Usages.

Ví dụ lệnh tìm:

    rg -n "LegacyOrderService|LegacyOrderController" src

Tìm URL cũ:

    rg -n "/orders/.*/cancel|legacy-order" src

Tìm tên template:

    rg -n "orders/legacy-detail|legacy-order" src

Kết quả tìm kiếm cần được phân loại:

- Production source reference.
- Test reference.
- Documentation hoặc migration note.
- Generated code hoặc build output.
- String literal được dùng trong cấu hình/runtime.
- Reflection hoặc dynamic lookup khó tìm bằng symbol reference.

Không xóa mọi kết quả một cách máy móc. Một tài liệu ghi lại migration có thể cần được giữ; một test characterization có thể cần chuyển; một production caller cần được sửa.

### Tìm kiếm tĩnh không đủ

Một endpoint có thể được gọi từ:

- Mobile application hoặc frontend repository khác.
- Webhook hoặc partner integration.
- Scheduled job ở hệ thống khác.
- Bookmark, email hoặc liên kết cũ.
- Script vận hành.
- Consumer không nằm trong cùng repository.

Hãy kết hợp source search với access log, API gateway metrics, distributed trace, consumer registry hoặc thông tin từ owner của tích hợp. Dữ liệu runtime cần quan sát đủ lâu để bao phủ chu kỳ sử dụng thực tế; một endpoint không được gọi trong vài phút không chứng minh nó không còn consumer.

### Quan sát theo route và version

Ghi nhận route template, release version và client metadata an toàn. Có thể theo dõi:

- Request count của route cũ.
- Tỷ lệ 4xx/5xx.
- Consumer/client version.
- Thời điểm gọi cuối.
- Số lượng session hoặc form còn hoạt động nếu có cơ chế đo.
- Số lần adapter tương thích được sử dụng.

Không log token, password hoặc dữ liệu cá nhân chỉ để xác định consumer.

## 12. Database migration và dữ liệu còn phụ thuộc cấu trúc cũ

Thay một service hoặc repository có thể đi cùng thay đổi schema. Việc xóa code cũ không đồng nghĩa có thể xóa cột hoặc bảng ngay.

Dùng chiến lược expand-and-contract:

### Expand

- Thêm cột/bảng mới theo cách code cũ vẫn chạy được.
- Deploy code có thể đọc dữ liệu cũ và mới.
- Bắt đầu ghi cấu trúc mới hoặc dual-write có kiểm soát.
- Backfill dữ liệu theo batch và có thể tiếp tục sau khi deploy.

### Migrate

- Chuyển các consumer sang cấu trúc mới.
- So sánh số lượng, checksum hoặc các invariant nghiệp vụ.
- Theo dõi query cũ và mới.
- Xác nhận dữ liệu đã được chuyển đầy đủ.

### Contract

- Xác nhận không còn code hoặc job đọc/ghi cấu trúc cũ.
- Dừng ghi vào cột/bảng cũ.
- Chờ qua khoảng thời gian tương thích cần thiết.
- Xóa cấu trúc cũ bằng migration riêng.

Không gộp việc thêm schema mới, chuyển code và xóa schema cũ trong cùng một bước nếu các phiên bản ứng dụng có thể chạy đồng thời.

### Kiểm tra dữ liệu sau chuyển

Tùy loại dữ liệu, có thể kiểm tra:

- Row count theo nhóm.
- Tổng tiền hoặc số lượng.
- Foreign key và orphan records.
- Trạng thái nghiệp vụ hợp lệ.
- Unique constraints.
- Phân bố null/default.
- Một mẫu dữ liệu được đối chiếu giữa đường cũ và mới.

Nếu dữ liệu có giá trị pháp lý hoặc tài chính, cần có kế hoạch reconciliation và lưu dấu vết thay đổi phù hợp.

## 13. Feature flag và thời điểm xóa đường cũ

Feature flag có thể giúp chuyển đổi dần:

    if (featureFlags.isEnabled("new-order-cancellation", actor)) {
        return newCancellation.execute(command);
    }

    return legacyCancellation.execute(command);

Trong giai đoạn chuyển tiếp, flag cần có:

- Owner chịu trách nhiệm.
- Giá trị mặc định theo môi trường.
- Nhóm user/tenant được bật.
- Metric xác nhận đường nào được sử dụng.
- Cách tắt nhanh khi có sự cố.
- Điều kiện và thời điểm xóa flag.

### Khi flag đã bật cho toàn bộ consumer

Không nên giữ hai implementation mãi mãi chỉ vì flag vẫn tồn tại. Khi đã xác nhận:

- Tất cả nhóm consumer đã dùng đường mới.
- Không còn request hợp lệ đi vào đường cũ.
- Kết quả và side effect đạt yêu cầu.
- Rollback window đã kết thúc hoặc có phương án tương thích.

Có thể xóa nhánh cũ và flag trong một thay đổi riêng. Sau đó tìm lại mọi tham chiếu đến tên flag để bảo đảm không còn code hoặc config thừa.

### Tránh chạy song song hai đường có side effect

Nếu cần so sánh kết quả, chỉ chạy đường cũ ở chế độ read-only/shadow và bảo đảm nó không gửi email, ghi database hoặc phát event. Nếu không thể bảo đảm điều đó, dùng test fixture hoặc bản sao dữ liệu thay vì chạy cả hai trong production.

## 14. Compatibility và deprecation cho API công khai

Với API được consumer bên ngoài sử dụng, việc thay thế cấu trúc nội bộ không nhất thiết yêu cầu đổi endpoint. Nếu cần thay đổi contract, cần một quy trình deprecation.

Một kế hoạch có thể gồm:

1. Công bố contract mới và lý do thay đổi.
2. Đưa API mới vào hoạt động.
3. Giữ API cũ như adapter gọi use case mới nếu có thể.
4. Thêm deprecation notice hoặc metadata theo quy ước của tổ chức.
5. Theo dõi traffic theo consumer.
6. Thông báo thời hạn ngừng hỗ trợ.
7. Xác nhận consumer đã chuyển.
8. Trả response phù hợp hoặc xóa endpoint sau thời hạn đã công bố.

Không dựa vào việc đổi tên Controller để kết luận API đã thay đổi. Contract là URL, method, schema, semantics, status và behavior mà client quan sát được.

Với API nội bộ, vẫn cần biết consumer nào bị ảnh hưởng. “Internal” không có nghĩa là có thể xóa mà không thông báo.

## 15. Session, cache và request đang xử lý

Một cấu trúc cũ có thể được giữ trong trạng thái runtime:

- Session chứa class hoặc attribute cũ.
- Cache chứa DTO/serialized object theo schema cũ.
- Job đang chạy được tạo từ implementation cũ.
- Request đã vào instance cũ trước khi rollout.
- Message đã được đưa vào queue với payload version cũ.

Trước khi xóa:

- Xác định session có serialize class cũ hay không.
- Xác định cache key hoặc value có cấu trúc cũ không.
- Xác định job có thể chạy qua thời điểm deploy không.
- Xác định message consumer có hỗ trợ payload cũ không.
- Drain instance cũ và chờ request đang xử lý hoàn tất theo chính sách.
- Giữ compatibility cho message hoặc session trong khoảng thời gian cần thiết.

Không chỉ kiểm tra source code. Một class có thể không còn được gọi trong code mới nhưng vẫn cần để deserialize dữ liệu đang tồn tại. Khi đã hết vòng đời dữ liệu cũ, có thể xóa class và serializer mapping tương ứng.

## 16. Đánh giá rủi ro và kế hoạch rollback

Trước khi xóa đường cũ, hãy xác định cách khôi phục nếu phát hiện consumer chưa được chuyển.

Cần biết:

- Artifact trước đó còn khả dụng không?
- Database schema hiện tại có tương thích với code cũ không?
- Feature flag có thể tắt ngay không?
- Route cũ có thể khôi phục mà không tạo mapping xung đột không?
- Asset và template cũ còn được lưu không?
- Message hoặc event đã phát ra có thể được xử lý bởi consumer cũ không?
- Thay đổi dữ liệu có thể đảo ngược hay cần forward-fix?

### Rollback và khôi phục code cũ không giống nhau

Nếu code cũ đã bị xóa khỏi artifact mới nhưng vẫn có trong release trước, rollback artifact có thể khôi phục đường cũ. Tuy nhiên, nếu schema hoặc dữ liệu đã thay đổi không tương thích, code cũ có thể không chạy được.

Nếu thay đổi dữ liệu không thể đảo ngược, có thể cần forward-fix hoặc compatibility adapter thay vì rollback toàn bộ.

Không giữ code cũ trong cùng codebase chỉ để có cảm giác an toàn. Hãy quản lý artifact release trước và kế hoạch rollback rõ ràng.

## 17. Kiểm thử sau khi xóa cấu trúc cũ

Sau khi xóa, chạy lại các kiểm tra ở mức phù hợp:

### Build và compile

Xác nhận không còn tham chiếu class, method, bean hoặc resource đã xóa. Compile là bước cơ bản để phát hiện symbol reference bị thiếu.

### Unit và integration tests

Chạy test của use case, Controller, persistence, security và các consumer đã chuyển. Xác nhận cả đường thành công lẫn đường bị từ chối.

### Route và template tests

Xác nhận route mới hoạt động, route cũ có hành vi đúng theo quyết định (alias, redirect, deprecated response hoặc không còn tồn tại). Render các template liên quan và kiểm tra asset được tham chiếu.

### Dependency injection context

Khởi tạo Spring application context để phát hiện bean thiếu, bean trùng hoặc qualifier còn tham chiếu implementation cũ.

### Architecture và static checks

Có thể dùng ArchUnit hoặc quy tắc build để ngăn package cũ được tham chiếu lại. Chỉ thêm rule khi ranh giới ổn định và có ý nghĩa. Không tạo test chỉ kiểm tra rằng một tên class không xuất hiện trong một file nếu điều đó không bảo vệ một kiến trúc thực sự.

### Smoke và production verification

Sau deploy, xác nhận route, business flow, status/error rate, metric và log. Theo dõi đủ thời gian để phát hiện consumer ít hoạt động.

## 18. Ví dụ tổng hợp: thay LegacyOrderService bằng use case mới

Giả sử ứng dụng có:

- LegacyOrderController.
- LegacyOrderService.
- OrderRepository cũ.
- Template orders/detail-legacy.
- Route POST /orders/{id}/cancel.

Nhóm muốn thay bằng CancelOrder use case, OrderAccessPolicy và OrderPageController.

### Bước 1: Ghi nhận hợp đồng

Viết test cho:

- Chủ đơn hàng hủy đơn đang chờ.
- Người khác bị từ chối.
- Đơn đã giao bị conflict.
- Đơn không tồn tại trả đúng lỗi.
- CSRF được kiểm tra.
- Thành công tạo audit record và cập nhật trạng thái.

### Bước 2: Tạo use case mới

    @Service
    public class CancelOrder {
        private final OrderRepository orders;
        private final OrderAccessPolicy accessPolicy;

        public CancelOrder(
                OrderRepository orders,
                OrderAccessPolicy accessPolicy) {
            this.orders = orders;
            this.accessPolicy = accessPolicy;
        }

        @Transactional
        public OrderResult execute(CancelOrderCommand command) {
            Order order = orders.findById(command.orderId())
                    .orElseThrow(OrderNotFoundException::new);

            accessPolicy.checkCanCancel(command.actorId(), order);
            order.cancel();

            return OrderResult.from(orders.save(order));
        }
    }

### Bước 3: Chuyển Controller mới

    @Controller
    @RequestMapping("/orders")
    public class OrderPageController {
        private final CancelOrder cancelOrder;

        @PostMapping("/{id}/cancel")
        public String cancel(
                @PathVariable UUID id,
                @AuthenticationPrincipal AppPrincipal principal) {

            cancelOrder.execute(
                    new CancelOrderCommand(principal.userId(), id));

            return "redirect:/orders/" + id;
        }
    }

Trong giai đoạn chuyển tiếp, route có thể được giữ nguyên để client không phải đổi URL. Chỉ implementation phía sau thay đổi.

### Bước 4: Chuyển consumer còn lại

Tìm và chuyển:

- Controller API.
- Job tự động hủy đơn hết hạn.
- Message listener xử lý yêu cầu hủy.
- Template và JavaScript gửi request.
- Test và fixture khởi tạo service cũ.

Các adapter có thể dùng cùng use case nhưng vẫn truyền actor và ngữ cảnh phù hợp. Job hệ thống cần một danh tính/service principal hoặc policy riêng, không giả lập người dùng tùy tiện.

### Bước 5: Xác nhận không còn đường cũ

- Tìm reference đến LegacyOrderService và LegacyOrderController.
- Kiểm tra Spring bean registration.
- Kiểm tra scheduled job và listener.
- Quan sát traffic route và adapter cũ.
- Xác nhận template cũ không còn được render.
- Xác nhận session/cache/message không cần class cũ.

### Bước 6: Xóa code và test lỗi thời

Khi không còn caller, xóa legacy service, bean/configuration, template và test chỉ kiểm tra implementation cũ. Giữ behavior tests trên use case mới và MVC adapter mới.

### Bước 7: Xác minh sau xóa

Chạy build, test phù hợp, khởi tạo Spring context, smoke test và theo dõi metric theo release. Chỉ đánh dấu migration hoàn tất khi bằng chứng cho thấy đường mới đang phục vụ toàn bộ consumer cần thiết.

## 19. Các sai lầm thường gặp

### Xóa class ngay sau khi tạo implementation mới

Consumer có thể vẫn gọi class cũ qua job, listener hoặc template. Hãy lập danh sách caller và chuyển từng nhóm.

### Chỉ kiểm thử đường mới

Test mới có thể bỏ sót status, error mapping, authorization hoặc side effect của đường cũ. Dùng characterization test và behavior contract làm cơ sở so sánh.

### Giữ hai implementation cùng ghi dữ liệu

Điều này có thể tạo double-write, event trùng hoặc trạng thái không nhất quán. Dùng một nguồn ghi có thẩm quyền; nếu shadow, giữ read-only.

### Dùng test implementation làm hợp đồng lâu dài

Test gọi private helper hoặc khẳng định thứ tự gọi nội bộ có thể cản trở refactor. Ưu tiên kết quả và ranh giới có ý nghĩa.

### Tìm kiếm source rồi kết luận không còn consumer

Client ngoài repository, bookmark và job bên ngoài không xuất hiện trong source. Kết hợp access log, metric, trace và thông tin từ consumer owner.

### Xóa route cũ mà không có deprecation

Client có thể vẫn dùng URL cũ. Giữ alias hoặc công bố thời hạn ngừng hỗ trợ theo contract.

### Xóa template nhưng quên fragment hoặc asset

Template có thể được include từ layout khác; JavaScript cũ có thể còn được cache. Tìm tham chiếu trên toàn bộ phạm vi được quản lý và giữ asset theo retention phù hợp.

### Xóa schema cũ cùng release thay code

Instance cũ hoặc job chưa chuyển có thể vẫn đọc cột/bảng cũ. Dùng expand-and-contract qua các release.

### Giữ feature flag và nhánh legacy vô thời hạn

Code chết làm tăng nhánh test và chi phí hiểu hệ thống. Đặt owner và điều kiện xóa flag ngay từ đầu.

### Rollback code nhưng không xét dữ liệu

Artifact cũ có thể không đọc được schema mới hoặc dữ liệu đã chuyển. Đánh giá compatibility trước khi quyết định rollback.

## 20. Quy trình xác minh và dọn cấu trúc cũ

Có thể dùng trình tự sau cho mỗi lần thay thế:

1. Liệt kê hành vi công khai và side effect phải giữ.
2. Ghi characterization tests cho đường hiện tại.
3. Phân loại test theo behavior, compatibility và implementation detail.
4. Tạo implementation mới với hợp đồng rõ.
5. Chuyển một adapter/consumer tại một thời điểm.
6. Chạy test và so sánh response, dữ liệu, quyền và side effect.
7. Giữ route/template compatibility khi còn consumer.
8. Theo dõi runtime usage của đường cũ đủ lâu.
9. Kiểm tra source reference, bean, config, job, listener, template và asset.
10. Xử lý session, cache, message và schema còn phụ thuộc.
11. Xóa implementation và test lỗi thời theo dependency order.
12. Chạy build, test, context startup và smoke test.
13. Theo dõi release mới và xác nhận không còn traffic hoặc lỗi liên quan.
14. Cập nhật tài liệu, runbook và kế hoạch rollback.

## 21. Checklist trước khi đánh dấu refactor hoàn tất

- Hành vi cần giữ đã được mô tả.
- Characterization/behavior tests bao phủ các tình huống quan trọng.
- Response status, schema, redirect và error contract không đổi ngoài chủ ý.
- Quy tắc authentication, authorization và CSRF vẫn được thực thi.
- Side effect và transaction không bị mất hoặc chạy hai lần.
- Tất cả Controller, job, listener và integration consumer đã chuyển.
- Route cũ có quyết định rõ: giữ, alias, deprecate hay xóa.
- Template, fragment, JavaScript và static asset cũ đã được kiểm tra.
- Bean, configuration, profile, property và feature flag cũ đã được xử lý.
- Session, cache, message và serialized data không còn phụ thuộc class cũ.
- Database migration tương thích với các phiên bản còn chạy.
- Source search không còn production reference ngoài dự kiến.
- Runtime metric/log xác nhận không còn consumer cần đường cũ.
- Test chỉ kiểm tra implementation cũ đã được chuyển hoặc xóa.
- Build, test, Spring context startup và smoke test đều đạt.
- Có phương án rollback hoặc forward-fix phù hợp với dữ liệu.

## Kết luận

Xác minh hành vi và xóa cấu trúc cũ là hai phần của cùng một lần cải tiến thiết kế. Characterization test ghi lại những gì client và nghiệp vụ cần tiếp tục nhận được; behavior test xác nhận implementation mới giữ các hợp đồng đó. Việc thay thế nên diễn ra theo từng lát cắt, chuyển hết consumer và quan sát đường cũ trước khi xóa.

Một refactor chỉ thực sự hoàn tất khi không còn caller hợp lệ phụ thuộc implementation cũ, route/template/configuration lỗi thời đã được xử lý, dữ liệu và session vẫn tương thích, và test chứng minh hành vi mới đúng. Giữ ranh giới giữa contract công khai và chi tiết nội bộ giúp nhóm loại bỏ code cũ mà không biến refactor thành một thay đổi hành vi ngoài ý muốn.
