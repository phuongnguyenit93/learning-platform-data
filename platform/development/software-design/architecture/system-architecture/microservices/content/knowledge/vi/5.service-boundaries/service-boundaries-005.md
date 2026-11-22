# Nhận diện phụ thuộc triển khai và phát hành đồng bộ

Trong kiến trúc microservices, việc chia hệ thống thành nhiều ứng dụng, repository hoặc container chưa bảo đảm các service có thể **triển khai và phát hành độc lập**. Nếu thay đổi nhỏ trong một service buộc nhiều service khác phải sửa code, chạy migration hoặc lên production cùng thời điểm, hệ thống vẫn có **phụ thuộc phát hành đồng bộ (lockstep release)**. Đây là tín hiệu quan trọng để xem lại ranh giới dịch vụ và cách thiết kế hợp đồng tích hợp.

Bài này hướng dẫn nhận diện phụ thuộc triển khai, phân biệt phụ thuộc runtime với phụ thuộc khi phát hành, truy ra nguyên nhân kỹ thuật/nghiệp vụ và thiết kế tiến trình nâng cấp an toàn. Ví dụ xuyên suốt là hệ thống thương mại điện tử gồm Catalog, Pricing, Ordering, Inventory và Payments.

## 1. Hiểu đúng các khái niệm

**Deployment (triển khai)**: đưa một phiên bản phần mềm, cấu hình, database schema hoặc hạ tầng lên một môi trường. Triển khai có thể diễn ra mà người dùng chưa nhìn thấy tính năng mới, ví dụ tính năng vẫn bị tắt bằng feature flag.

**Release (phát hành)**: cho phép người dùng hay hệ thống khác thực sự sử dụng hành vi mới. Một release có thể diễn ra sau deployment bằng cấu hình, feature flag hoặc thay đổi định tuyến.

**Independent deployability (khả năng triển khai độc lập)**: một service có thể nhận bản build mới, vận hành an toàn bên cạnh các phiên bản đang chạy của consumer/provider, rồi rollback hoặc roll forward mà **không buộc** những service không liên quan phải triển khai đồng thời.

**Deployment dependency (phụ thuộc triển khai)**: điều kiện khiến việc đưa phiên bản A vào môi trường chỉ an toàn sau khi có phiên bản, migration, cấu hình hoặc hành động tương ứng từ B. Một phụ thuộc kỹ thuật được kiểm soát có thể chấp nhận được; điều đáng chú ý là các thay đổi thường xuyên cần nhiều bên phối hợp như một đơn vị triển khai.

**Lockstep release (phát hành đồng bộ)**: các thành phần phải được phát hành theo cùng thời điểm hoặc một thứ tự cứng, trong một cửa sổ hẹp, nếu không hệ thống hỏng hay sinh dữ liệu không hợp lệ. Ví dụ Ordering mới chỉ hiểu response API của Pricing mới, còn Ordering cũ không hiểu response đó. Nếu hai bản không tương thích chéo, nhóm vận hành buộc phải chuyển cả hai cùng nhau.

**Runtime dependency (phụ thuộc lúc chạy)**: service A cần service B để hoàn tất một hành động, chẳng hạn Ordering gọi Payments. Runtime dependency không tất yếu dẫn đến lockstep release: hợp đồng ổn định, resilience và compatibility có thể cho phép từng service triển khai riêng.

**Build dependency (phụ thuộc build)**: service A sử dụng một thư viện, generated client hoặc schema package khi biên dịch. Đây không nhất thiết là deployment dependency nếu artifact đã được version hóa và tương thích. Ngược lại, shared library có quy trình cập nhật bắt buộc đồng loạt có thể biến build coupling thành release coupling.

Điểm cần kiểm chứng là **khả năng chạy song song phiên bản cũ và mới**, gồm request, response, message, schema lưu trữ và trạng thái nghiệp vụ, trong khoảng thời gian rollout/rollback thực tế.

## 2. Vì sao phụ thuộc phát hành đồng bộ có hại?

Một release có thể có nhiều service vì nhu cầu sản phẩm. Vấn đề xuất hiện khi **bất kỳ thay đổi nhỏ nào** cũng yêu cầu một chuỗi triển khai và kiểm thử chung.

Hệ quả thường gặp:

- Thời gian đưa tính năng lên production phụ thuộc lịch trống của nhiều team.
- Pull request tại service A phải chờ API, database migration hoặc pipeline của B.
- Một lỗi tại thành phần nhỏ bắt cả nhóm rollback; đôi khi rollback không thể thực hiện nếu dữ liệu/schema đã chuyển đổi không tương thích.
- Quy mô blast radius tăng: triển khai một service kéo theo thay đổi trên nhiều luồng nghiệp vụ.
- Các service cần chung cửa sổ bảo trì và kiểm thử end-to-end tốn kém.
- Team không tự quyết định nhịp phát hành, làm giảm lợi ích tổ chức của microservices.
- Khi sự cố, khó biết rollback service nào, phiên bản nào còn tương thích, bước nào không thể đảo ngược.

Tuy vậy, **không phải mọi phối hợp phát hành là lỗi kiến trúc**. Một đợt thay đổi lớn có rủi ro cao, cutover hạ tầng, migration có giới hạn tương thích hoặc thay đổi chính sách nghiệp vụ trên nhiều miền có thể cần điều phối. Cần nhận diện xem đó là một lần chuyển đổi có kế hoạch hay phụ thuộc lặp lại ở gần như mọi lần đổi mã.

## 3. Dấu hiệu nhận diện nhanh

Hãy theo dõi chu kỳ từ chỉnh code đến production. Các dấu hiệu mạnh gồm:

1. Một PR sửa contract khiến nhiều repo phải merge và deploy trong cùng sprint.
2. Bảng hướng dẫn release ghi “Deploy Pricing trước, lập tức deploy Ordering và Checkout; không được rollback một bên”.
3. Các service khác nhau được quản lý bởi cùng một release version và chỉ có một pipeline deploy tất cả.
4. Chỉ thay đổi một DTO/entity nhưng phải regenerate và tái phát hành client của mọi consumer.
5. Nhiều service đọc/ghi trực tiếp cùng bảng, khiến thay đổi cột/constraint cần xử lý đồng bộ.
6. Producer đổi payload event thì consumer cũ lỗi parse hoặc bỏ qua message không có đường khôi phục.
7. Thêm một enum/status mới làm consumer cũ crash, dead-letter hàng loạt hoặc chuyển sai state.
8. Triển khai thành công ở staging nhưng không lên được production vì chưa có configuration, secret hoặc hạ tầng mới được provision ở nhiều nơi.
9. Business team chỉ dám bật feature khi đã xác nhận mọi service lên cùng commit hoặc cùng image tag.
10. Rollback service A bị chặn vì dữ liệu do phiên bản mới tạo không còn đọc được bởi phiên bản cũ.

Một hiện tượng riêng lẻ chưa đủ để kết luận. Cần xem **thay đổi nào gây phụ thuộc, cơ chế tương thích có tồn tại không và có thể triển khai lệch thời điểm bao lâu**.

## 4. Các loại phụ thuộc và cách phát hiện

| Loại phụ thuộc | Biểu hiện thực tế | Điều cần kiểm tra |
| --- | --- | --- |
| API contract | Producer đổi field, route, kiểu dữ liệu hoặc mã lỗi; consumer phải cập nhật cùng ngày | Các phiên bản consumer có hiểu response của producer cũ/mới không? |
| Message/event schema | Consumer cũ không đọc được event mới; consumer mới chỉ hiểu event phiên bản mới | Quy tắc thêm/bỏ field, schema registry, version và deserialization |
| Semantic contract | Payload vẫn parse được nhưng ý nghĩa của status, tiền tệ, thời điểm thanh toán thay đổi | Test hành vi, state machine và bất biến nghiệp vụ |
| Database schema | Nhiều service dùng chung bảng/cột; migration phá query cũ | Data ownership, truy vấn thật, thời gian tồn tại của schema cũ |
| Shared library/client | Thay thư viện chung buộc tất cả service build/deploy | Version pinning, compatibility, cách publish và lịch sử release |
| Workflow/state transition | Service A bắt đầu phát trạng thái mà B chưa xử lý | Version của workflow, event ordering, feature activation |
| Infra/configuration | Đổi topic, queue, permission, TLS, secret, routing cần sửa nhiều dịch vụ | Infrastructure as Code, backward-compatible provisioning |
| UI/backend | Frontend mới chỉ làm việc với backend mới | API compatibility, capability negotiation, feature flag |
| Data migration | Chuyển định dạng dữ liệu mà code cũ không đọc được | Dual-read/write, backfill, rollback data strategy |
| Operational process | Một runbook, release train hoặc approval bắt buộc gộp nhiều service | Thực tế có cần tương thích runtime hay chỉ là chính sách triển khai? |

**Phân biệt coupling kỹ thuật và phối hợp do quy trình:** Một pipeline duy nhất có thể khiến các service deploy đồng thời dù từng service hoàn toàn tương thích. Ngược lại, nhiều pipeline riêng chưa chứng minh độc lập nếu schema/API buộc cập nhật đồng bộ. Phân tích cả cấu trúc kỹ thuật lẫn quy trình.

## 5. Phân biệt phụ thuộc runtime với phụ thuộc release

Xét Ordering gọi Pricing để lấy giá sản phẩm:

~~~text
Ordering --HTTP--> Pricing
~~~

Trường hợp 1: Pricing cung cấp hợp đồng v1 ổn định; thêm field discountBreakdown tùy chọn nhưng vẫn trả price và currency. Ordering cũ bỏ qua field mới. Ordering mới có thể dùng field đó khi sẵn có, fallback khi không có. **Hai service có runtime dependency nhưng có thể deploy độc lập.**

Trường hợp 2: Pricing đổi price từ số nguyên đơn vị nhỏ nhất sang object amount/currency và ngừng trả field cũ ngay lập tức. Ordering cũ không parse được response. Ordering mới cũng không hiểu bản Pricing cũ. **Hai phiên bản mới phải triển khai đồng bộ hoặc có giai đoạn thích ứng.**

Vì vậy, kết luận thiết kế nên dựa trên một ma trận phiên bản:

| | Pricing cũ | Pricing mới |
| --- | --- | --- |
| Ordering cũ | Hoạt động | Phải hoạt động trong thời gian rollout |
| Ordering mới | Phải hoạt động trong thời gian rollout | Hoạt động |

Nếu chỉ hai ô đường chéo hoạt động, release bị ghép cặp. Mục tiêu của migration là tạo giai đoạn mà ít nhất các tổ hợp phiên bản có thể xuất hiện trong rollout đều an toàn. Không bắt buộc mọi phiên bản ở mọi thời điểm phải tương thích mãi mãi; phải xác định **cửa sổ hỗ trợ** và khi nào được phép ngừng v1.

Lưu ý: “API không trả lỗi 500” chưa chứng minh tương thích. Consumer có thể tính sai tiền, bỏ sót giảm giá hoặc xử lý status mới thành một hành vi sai. Cần kiểm tra cả semantics và trạng thái dữ liệu.

## 6. Quy trình điều tra phụ thuộc triển khai

### Bước 1 — Chọn một thay đổi thực tế

Dùng một change vừa hoặc sẽ làm: “Thêm phân loại giá theo khu vực”, “Đổi cấu trúc địa chỉ giao hàng”, “Tách bảng thanh toán”, “Thêm trạng thái PARTIALLY_SHIPPED”. Ghi service sở hữu thay đổi, provider và consumer chịu ảnh hưởng.

Không bắt đầu bằng kết luận “service X và Y phụ thuộc”; hãy ghi **lệnh, trường dữ liệu hoặc schema cụ thể** dẫn tới yêu cầu phối hợp.

### Bước 2 — Lần theo phụ thuộc trên code và dữ liệu

Đối chiếu:

- OpenAPI/gRPC/protobuf/GraphQL schema, generated clients và các validation.
- Event payload/schema, serializer/deserializer, handler và dead-letter policy.
- Mã truy cập database (ORM models, SQL, migration), nhất là truy cập qua service boundary.
- Version dependency của thư viện, SDK nội bộ, artifact chung.
- Manifest triển khai, Helm chart, Kubernetes ConfigMap, secret, topic/queue, feature flag và chính sách routing.
- CI/CD pipeline, stage dependencies, approval gates, thứ tự deploy, script release và rollback.
- Test tích hợp, contract test, lỗi production, runbook và lịch sử release.

Một tham chiếu code chưa chứng minh phụ thuộc deploy. Cần xác định service cũ có thể làm việc với kết quả mới hay không.

### Bước 3 — Vẽ hướng phụ thuộc và điều kiện

Với mỗi cạnh A → B, ghi:

- **Provider / consumer:** ai cung cấp contract và ai cần nó?
- **Lý do:** field, enum, endpoint, table, event, config hay invariant nào?
- **Tương thích:** A cũ ↔ B mới, A mới ↔ B cũ trong các tổ hợp thực tế.
- **Điều kiện rollout:** B phải được triển khai trước? Có thể cùng chạy v1/v2?
- **Thời điểm kích hoạt:** triển khai binary đã có ảnh hưởng chưa, hay chỉ khi bật flag?
- **Rollback:** service cũ có đọc được dữ liệu/sự kiện do service mới tạo không?
- **Bằng chứng:** test, log, link PR, migration hoặc lần xảy ra lỗi.

Không cần gom mọi dependency runtime vào đồ thị release. Chỉ đánh dấu cạnh cần phối hợp khi **một hành động triển khai/phát hành bị chặn bởi thay đổi ở thành phần khác**.

### Bước 4 — Nhận diện các chu trình và cụm bị khóa

Ví dụ:

~~~text
Catalog --(shared Product DTO)--> Pricing
Pricing --(breaking API change)--> Ordering
Ordering --(new order status)--> Payments
Payments --(shared DB update)--> Ordering
~~~

Nếu Ordering chỉ được triển khai sau Payments mới, đồng thời Payments mới yêu cầu Ordering mới, đồ thị chứa một chu trình. Không có thứ tự triển khai từng bên đơn giản nào thỏa cả hai. Cần **pha tương thích trung gian**, tách sở hữu dữ liệu hoặc một cutover phối hợp có kiểm soát.

Dùng đồ thị phụ thuộc của các change cụ thể, không suy ra rằng hai service phải gộp chỉ vì chúng gọi nhau lúc chạy.

### Bước 5 — Đo độ thường xuyên và hậu quả

Hỏi trong 10–20 lần deploy gần đây: bao nhiêu lần cần deploy thêm service khác vì lý do kỹ thuật, bao nhiêu lần trì hoãn, rollback bị chặn, incident sau thay đổi hợp đồng, thời gian chờ lâu nhất và số team phải phối hợp.

Chỉ số hữu ích là **tỷ lệ thay đổi bắt buộc phối hợp**, không phải số lượng service trong hệ thống. Đánh giá cùng với mức độ quan trọng nghiệp vụ; một cạnh ít khi thay đổi nhưng có thể làm mất tiền vẫn cần xử lý nghiêm túc.

### Bước 6 — Chọn giải pháp và xác thực qua migration thử

Chọn contract evolution, tách dữ liệu, giảm phụ thuộc build, quản lý trạng thái hoặc điều chỉnh ranh giới service. Tạo thử kế hoạch rollout để chứng minh từng phiên bản có thể sống chung và rollback an toàn.

## 7. Mẫu bảng kiểm kê phụ thuộc

Ghi lại theo từng thay đổi, không chỉ theo cặp service:

| Change | Provider / owner | Consumer | Bản cũ với bản mới | Có bắt buộc deploy đồng thời? | Cách xử lý |
| --- | --- | --- | --- | --- | --- |
| Thêm field discountBreakdown tùy chọn | Pricing | Ordering | Consumer cũ bỏ qua field | Không | Additive contract + test |
| Đổi price từ number sang object | Pricing | Ordering | Hai chiều không hiểu nhau | Có, nếu thay trực tiếp | Expand/migrate/contract |
| Rename event StockReserved | Inventory | Ordering | Handler cũ không nhận | Có, nếu đổi ngay | Dual-publish hoặc adapter có giới hạn |
| Thêm cột nullable trên bảng riêng của Orders | Ordering | Ordering | Code cũ còn chạy | Không, nếu migration an toàn | Expand schema trước |
| Shared order table bị hai service ghi | Ordering + Payments | Cả hai | Không có ownership rõ | Thường có | Tách ownership và đồng bộ qua hợp đồng |
| Nâng thư viện logging không đổi interface | Platform | Nhiều service | Binary đã deploy không phụ thuộc | Không | Mỗi service nâng phiên bản khi phù hợp |

Có thể thêm cột mức độ ảnh hưởng, thời hạn ngừng v1, người sở hữu migration, link test và kế hoạch rollback. Không dùng kết luận “Không” chỉ vì chưa từng thấy lỗi; test với phiên bản cũ/mới và cả dữ liệu được tạo bởi các phiên bản đó.

## 8. Kỹ thuật cốt lõi: thiết kế thay đổi tương thích ngược

### 8.1. Thêm trước, chuyển dần, xóa sau

Một thay đổi phá vỡ hợp đồng thường được chia thành ba pha: **expand → migrate → contract**.

Ví dụ muốn đổi response Pricing từ:

~~~json
{
  "sku": "A100",
  "priceMinor": 159900,
  "currency": "VND"
}
~~~

sang:

~~~json
{
  "sku": "A100",
  "price": {
    "amountMinor": 159900,
    "currency": "VND"
  }
}
~~~

Kế hoạch:

1. **Expand:** Pricing trả cả priceMinor/currency cũ và price mới. Các consumer hiện tại tiếp tục hoạt động. Deploy Pricing mới trước và xác nhận consumer cũ vẫn đọc đúng.
2. **Migrate:** từng consumer cập nhật để ưu tiên price, đồng thời hỗ trợ fallback sang priceMinor/currency khi gọi Pricing chưa lên bản mới, nếu kịch bản rollback hoặc multi-region yêu cầu. Deploy các consumer theo nhịp riêng.
3. **Observe:** theo dõi consumer nào còn dùng field cũ; chạy consumer-driven contract test, telemetry và xác nhận mọi client trong phạm vi hỗ trợ đã chuyển.
4. **Contract:** ngừng xuất field cũ sau cửa sổ hỗ trợ đã công bố, có kế hoạch ứng phó nếu phát hiện consumer cũ. Nếu không thể kiểm soát mọi consumer, xem xét endpoint/version riêng thay vì xóa field.

Các giai đoạn này thường diễn ra trong **nhiều deployment**, và chỉ cần yêu cầu tất cả bên thay đổi đồng thời nếu đã chứng minh không thể có trạng thái trung gian an toàn.

### 8.2. Không tự ý thay đổi ý nghĩa dữ liệu

“Giữ nguyên tên field” không đủ. Ví dụ status PAID từng nghĩa là đã capture tiền, nay chỉ nghĩa authorize. Consumer cũ có thể bắt đầu tạo Shipment sớm dù JSON không đổi. Đây là breaking change về semantics.

Hãy dùng status/event có tên phản ánh đúng điều kiện, bổ sung phase/version hoặc hợp đồng mới, chuyển từng consumer và chỉ cho phép tạo hành vi mới khi downstream hiểu rõ.

### 8.3. Tương thích hai chiều trong cửa sổ triển khai

Với rollout rolling update, nhiều replica của cùng service có thể chạy phiên bản N và N+1 đồng thời. Nếu producer mới gửi enum mà consumer cũ không hiểu, một phần request/message sẽ lỗi ngẫu nhiên.

Trước khi rollout, xác định:

- Consumer cũ có bỏ qua field không biết không? Có fail-fast khi gặp enum mới không?
- Consumer mới có bắt buộc field mới không, dù producer cũ chưa trả?
- Có cache hoặc retry khiến payload cũ tồn tại lâu hơn thời gian deploy không?
- Có hàng đợi giữ message của version cũ hàng giờ/ngày không?
- Rollback consumer có đọc được trạng thái do bản mới đã ghi không?
- Có thể tắt feature mới mà không rollback schema hay dữ liệu không?

Tính tương thích phải bao phủ ít nhất các tổ hợp mà hệ thống thực sự có thể gặp trong thời gian chuyển đổi.

## 9. API và consumer-driven contract test

**Producer contract** mô tả điều producer hứa cung cấp; **consumer contract** mô tả điều một consumer thực sự cần để hoạt động. Consumer-driven contract test giúp phát hiện thay đổi phá vỡ bên sử dụng trước khi production.

Ví dụ:

~~~text
Ordering cần từ Pricing:
- sku đúng theo request
- amountMinor là integer >= 0
- currency là đơn vị tiền hợp lệ
- khi không tìm thấy giá, trả lỗi nghiệp vụ xác định
- timeout/5xx không được coi là giá 0
~~~

Quy trình:

1. Consumer công bố contract cho tình huống thực sự sử dụng.
2. Producer xác nhận bản build mới vẫn đáp ứng những contract đang được hỗ trợ.
3. CI kiểm tra ma trận phiên bản đang chạy hoặc sẽ hỗ trợ.
4. Khi producer muốn bỏ contract cũ, cần biết các consumer liên quan đã nâng cấp và cửa sổ hỗ trợ đã hết.
5. E2E test vẫn dùng cho các luồng thiết yếu như chốt tổng tiền và thanh toán; contract test không thay thế kiểm thử nghiệp vụ xuyên service.

Không để contract test trở thành một cổng bắt buộc tất cả service deploy đồng thời. Mục đích là **phát hiện tính tương thích**, sau đó cho phép consumer và producer triển khai ở thời điểm khác nhau.

Với client bên thứ ba/ứng dụng di động chưa nâng cấp ngay được, phải duy trì hợp đồng lâu hơn và có versioning rõ ràng. Một app mobile cũ không thể bị buộc rollout như một service nội bộ.

## 10. Event-driven integration cũng có thể gây lockstep release

Hệ thống dùng message broker vẫn có release coupling nếu schema hoặc semantics của event không ổn định.

Ví dụ Inventory đang phát:

~~~json
{
  "eventId": "evt-17",
  "eventType": "StockReserved",
  "orderId": "ord-12",
  "sku": "A100",
  "quantity": 2
}
~~~

Phiên bản mới cần phân biệt nguồn tồn kho và thêm warehouseId. Nếu chỉ thêm warehouseId tùy chọn mà consumer cũ bỏ qua được, có thể deploy Inventory mới trước; Ordering mới chuyển dần sang đọc field. Nhưng nếu tính nghiệp vụ yêu cầu mọi consumer dùng warehouseId để tránh xuất nhầm kho, **tính tương thích về cú pháp vẫn chưa đủ**.

Hướng xử lý:

- Dùng event cho sự kiện miền đã xảy ra, ghi rõ semantics và ownership.
- Ưu tiên thay đổi additive; optional field cần có ý nghĩa mặc định rõ ràng.
- Không đổi nghĩa eventType cũ dưới cùng tên. Với thay đổi lớn, tạo eventType/schema version mới và chiến lược chuyển tiếp.
- Nếu dual-publish v1/v2, định nghĩa ID tương quan để consumer không xử lý hai lần cùng một nghiệp vụ.
- Consumer phải idempotent, có chính sách retry, DLQ và xử lý event đến muộn/sai thứ tự khi thiết kế đòi hỏi.
- Kiểm tra retention của topic, outbox backlog, replay và bản consumer đã ngừng dùng trước khi xóa contract cũ.
- Có thể dùng schema registry với quy tắc backward/forward/full compatibility phù hợp, nhưng registry chỉ giúp kiểm tra cấu trúc; semantics vẫn cần test.

Ví dụ một consumer mới chỉ hiểu StockReservedV2 **không nên** được triển khai trước producer nếu không có hỗ trợ song song StockReserved. Có thể triển khai consumer nhận cả v1/v2 trước, sau đó producer phát v2, rồi bỏ v1 khi hết consumer cũ.

## 11. Shared database: nguồn phụ thuộc sâu và khó rollback

Một mô hình hay gặp:

~~~text
Ordering ----\
              > shared database: orders, order_items, payments
Payments ----/
Reporting ---/
~~~

Khi Ordering đổi cột order_status, Payments có thể lỗi SQL; khi Payments thêm trạng thái mới, Reporting có thể tính sai. Lúc này database schema trở thành **hợp đồng ngầm** giữa các service.

Dấu hiệu cụ thể:

- Một table có nhiều service quyền INSERT/UPDATE/DELETE.
- Migration nằm trong repo A nhưng deploy pipeline B cần chạy migration đó.
- Code service B import JPA entity hoặc DAO của A.
- Cần database lock hoặc stored procedure cập nhật dữ liệu thuộc nhiều miền.
- Rollback code bị chặn vì old schema đã bị drop hoặc dữ liệu chuyển định dạng không thể đọc lại.

Hướng cải thiện: thiết lập một **owner có thẩm quyền cho dữ liệu**, nơi khác truy cập thông qua API, event hoặc read model được cấp dữ liệu. Tách schema/database có thể là bước triển khai về sau; điều quan trọng trước mắt là loại bỏ quyền ghi trực tiếp chồng chéo và xác định hợp đồng sở hữu.

Khi cần thay đổi bảng có consumer cũ, áp dụng migration an toàn:

~~~sql
-- Pha expand: bổ sung cột mới, không xóa cột hiện có.
ALTER TABLE orders ADD COLUMN shipping_country_code VARCHAR(2) NULL;

-- Pha migrate: ứng dụng/worker bổ sung dữ liệu từng đợt,
-- có checkpoint, retry và quan sát tiến độ.

-- Pha contract: chỉ xóa cột cũ sau khi tất cả đường đọc/ghi cũ
-- đã hết và hết cửa sổ rollback.
~~~

Nguyên tắc triển khai:

1. Migrations trước phải giữ code cũ chạy được; thêm cột nullable, index an toàn, constraint ở giai đoạn thích hợp.
2. Nếu cần dual-write cột cũ và mới, xác định nguồn sự thật và xử lý khác biệt khi một phần ghi thất bại.
3. Backfill cần idempotent, theo lô, có checkpoint, giới hạn tải và xử lý bản ghi phát sinh trong lúc chạy.
4. Chỉ bật đọc bằng schema mới sau khi dữ liệu cần thiết đã sẵn sàng; theo dõi null/invalid/mismatch.
5. Không drop/rename cột trong cùng bước deploy ứng dụng mới. Chờ toàn bộ consumer cũ biến mất và đáp ứng rollback window.
6. Rollback code không phải lúc nào hoàn tác được migration dữ liệu; ưu tiên rollback hành vi bằng flag hoặc roll forward schema tương thích.

Một số database migration đặc biệt (thay partitioning, primary key, encryption hoặc dữ liệu khối lượng rất lớn) có thể cần công cụ và chiến lược online migration riêng; đừng mặc định mọi ALTER TABLE đều không chặn.

## 12. Shared libraries và monorepo: khi nào thành release coupling?

Dùng chung thư viện cho logging, tracing, security hoặc client code không sai. Cần xem thư viện có kéo theo đồng bộ runtime hay không.

**Trường hợp ít coupling:** Thư viện HTTP client phiên bản 2 được publish bất biến; service A tiếp tục pin phiên bản 1; server hỗ trợ cả hai giao thức trong cửa sổ chuyển đổi. Các service cập nhật độc lập.

**Trường hợp coupling cao:** Một package shared-domain chứa entity, enum và cả DB migration; thay status trong package buộc mọi service lấy version mới và deploy cùng nhau. Cộng thêm cơ chế dependency luôn dùng bản latest, các service mất quyền chọn nhịp cập nhật.

Khuyến nghị thiết kế:

- Chia sẻ code ổn định, ít semantics miền biến động; tránh dùng một domain model sống cho mọi bounded context.
- Publish artifact theo phiên bản rõ ràng, khóa dependency bằng lockfile/version pinning.
- Generated client dựa trên hợp đồng công khai, hỗ trợ tương thích giữa version cũ/mới.
- Không bắt ép thay đổi thư viện chung dẫn đến triển khai đồng loạt trừ khi có lý do bảo mật/vận hành cụ thể.
- Monorepo có thể chứa nhiều deployment unit độc lập. Ngược lại, nhiều repo không bảo đảm microservices độc lập nếu tích hợp phá tương thích.

Việc đổi một CI workflow chung hay base image có thể tạo nhu cầu rebuild nhiều service, nhưng **rebuild** khác với **bắt buộc phát hành đồng thời**. Đánh giá đúng cơ chế trước khi thay đổi ranh giới.

## 13. Phân tách deployment và feature activation

Một cách giảm áp lực lockstep là cho các service triển khai code mới trước, nhưng tắt hành vi mới cho đến khi hệ thống sẵn sàng.

Ví dụ luồng đổi cách tính giá:

~~~text
T1: Pricing deploy support pricing_v2, vẫn trả v1
T2: Ordering deploy support đọc v1 và v2
T3: Checkout deploy support hiển thị cách tính mới
T4: Bật feature flag cho một nhóm người dùng
T5: Quan sát kết quả, tăng traffic theo từng đợt
T6: Ngừng v1 sau khi mọi consumer trong phạm vi hỗ trợ đã chuyển
~~~

Cần phân biệt ba trạng thái: **code đã có**, **contract đã được dùng**, **tính năng đã bật**. Tách được chúng giúp từng nhóm triển khai độc lập dù thời điểm phát hành tính năng liên quan phải phối hợp.

Feature flag không giải quyết mọi vấn đề. Một flag chỉ có ích nếu đường code cũ và mới cùng tồn tại an toàn, dữ liệu có thể dùng chung hoặc được tách theo phiên bản. Phải đặt owner, thời gian dọn flag và quan sát version nào đang hoạt động để tránh flag tồn tại mãi.

## 14. Thiết kế một rollout có thể rollback

Giả sử yêu cầu thay địa chỉ giao hàng từ chuỗi free-text sang cấu trúc country, province, district, addressLine.

**Trước thay đổi:**

~~~json
{ "shippingAddress": "12 Le Loi, District 1" }
~~~

**Sau thay đổi mong muốn:**

~~~json
{
  "shippingAddress": {
    "countryCode": "VN",
    "provinceCode": "79",
    "districtCode": "760",
    "addressLine": "12 Le Loi"
  }
}
~~~

Nếu thay ngay kiểu field shippingAddress từ string sang object, consumer cũ có thể lỗi deserialization; các đơn đặt trước vẫn chứa string.

Kế hoạch chuyển đổi:

| Pha | Thao tác | Điều kiện an toàn |
| --- | --- | --- |
| 0. Inventory | Liệt kê producer, consumer, database, mobile client và các bản đang chạy | Có owner và tập version thực tế |
| 1. Expand | Thêm shippingAddressV2 tùy chọn; giữ shippingAddress cũ | Consumer cũ còn hoạt động |
| 2. Reader migration | Consumer mới đọc V2 nếu có, fallback sang string nếu chưa có | Có test mixed version và dữ liệu lịch sử |
| 3. Writer migration | Producer mới ghi cả V2 và legacy representation trong thời gian chuyển tiếp | Dual-write nhất quán, kiểm soát dữ liệu thiếu |
| 4. Backfill | Chuyển dữ liệu cũ khi có thể; trường không phân tích được được đánh dấu xử lý | Worker idempotent, có thống kê và retry |
| 5. Activation | Bật tính năng theo cohort/traffic và giám sát | Có công tắc tắt/giảm tải |
| 6. Contract | Dừng field cũ sau khi hết consumer và rollback window | Bằng chứng consumer cũ đã ngừng |
| 7. Cleanup | Xóa code/flag/migration tạm thời | Tài liệu và hợp đồng cập nhật |

**Rollback theo pha:** Trong pha 1–5, hạ version/flag phải còn đọc và xử lý được dữ liệu mới tạo. Nếu V2 mang thông tin mà string cũ không biểu diễn hết, cần xác định rõ backward representation bị mất gì, có chặn feature khi rollback hay cần một adapter. Sau pha contract, rollback về rất cũ có thể không còn được hỗ trợ; đây phải là quyết định vận hành được công bố.

Không coi “deploy xong trong năm phút” là lý do để bỏ qua cửa sổ mixed version. Retry, queue backlog, mobile client, multi-region và long-lived request có thể khiến nhiều phiên bản cùng tồn tại lâu hơn.

## 15. Phụ thuộc về nghiệp vụ: lúc nào cần giữ phối hợp?

Một số thay đổi yêu cầu điều phối ngay cả khi deploy độc lập về kỹ thuật. Ví dụ quy định thuế mới có hiệu lực tại một thời điểm, hoặc luật phê duyệt giao dịch phải nhất quán trên Pricing, Checkout và Invoicing.

Có thể xử lý bằng cách:

- Đưa chính sách được version hóa về một owner có thẩm quyền.
- Phát hành code hỗ trợ chính sách mới sớm, kích hoạt theo effectiveAt hoặc feature flag khi đến giờ.
- Ghi policyVersion/ruleVersion vào giao dịch để truy vết và tránh xử lý lại bằng luật khác.
- Xác định rõ consumer nào cần được nâng cấp trước khi kích hoạt, rồi kiểm tra trạng thái readiness.
- Thiết kế idempotency, retry và bù trừ cho quy trình phân tán.

**Đừng đánh đổi bất biến nghiệp vụ quan trọng lấy khẩu hiệu “mỗi service deploy lúc nào cũng được”.** Mục tiêu là dịch chuyển sự phối hợp từ bước thay binary sang bước kích hoạt nghiệp vụ có chủ đích, đồng thời giữ rollout và rollback an toàn.

Nếu hai miền có thay đổi code đồng thời liên tục, sharing transaction/owned data rất chặt và luôn thay đổi vì cùng một lý do nghiệp vụ, cần xem lại bounded context hoặc lựa chọn modular monolith. Đôi khi một module thống nhất có chi phí điều hành thấp hơn hai service bị lockstep mãi mãi.

## 16. Chỉ báo nên theo dõi sau khi cải thiện

Không chỉ đo số lần deploy. Nên đo cùng nhau:

| Chỉ báo | Công thức/ý nghĩa | Cần hiểu đúng |
| --- | --- | --- |
| Tỷ lệ deploy độc lập | Số deploy không cần phối hợp version service khác / tổng deploy | Loại trừ việc chủ động gộp vì sản phẩm nhưng không bắt buộc kỹ thuật |
| Phụ thuộc bắt buộc trên mỗi change | Số service khác phải nâng cấp trước khi change hoạt động an toàn | Phân biệt dependency lúc chạy với deploy dependency |
| Lead time do chờ phối hợp | Thời gian chờ thay đổi ở team khác, migration hoặc release window | Đánh giá trên change có liên kết |
| Rollback autonomy | Có thể hoàn nguyên service mà không rollback thành phần khác | Bao gồm schema và dữ liệu mới tạo |
| Compatibility coverage | Các cặp version được test / cặp version có thể cùng chạy | Bổ sung semantic behavior, không chỉ parse schema |
| Contract break incidents | Sự cố do schema, semantics, version mismatch | Theo dõi API, event, database, client |
| Release blast radius | Số service/luồng nghiệp vụ bắt buộc thay đổi trong release | Đừng nhầm với số replica triển khai |
| Migration debt | Số legacy contract/flag đang chờ loại bỏ, thời gian tồn tại | Nợ kỹ thuật tăng nếu expand mà không contract |

Ví dụ không nên báo “100% deployment độc lập” nếu pipeline chỉ deploy một image/service, nhưng mỗi release phải tạm dừng chờ ba service khác. Cũng không nên ép độc lập bằng cách để consumer âm thầm bỏ qua dữ liệu sai.

## 17. Các lỗi thường gặp khi sửa coupling

### 17.1. “Chỉ cần tách repo và pipeline”

Tách repository có thể giúp ownership và build, nhưng không sửa API breaking, shared DB hoặc state transition. Hãy chứng minh cặp version cũ/mới tương thích trước khi coi vấn đề được giải quyết.

### 17.2. “Dùng message broker là hết coupling”

Broker giảm đồng bộ theo thời gian request, nhưng event có thể phá schema/semantics. Producer có thể nâng cấp trong khi message cũ vẫn nằm trong queue. Hãy thiết kế version, retention, retry, consumer idempotency và lifecycle của event.

### 17.3. “Cứ tăng API version là triển khai được”

V1 và V2 cùng tồn tại là một cách giảm coupling, nhưng cần cơ chế chọn version, deprecation, telemetry người dùng, bảo trì bảo mật và chính sách xóa version cũ. Versioning không thay thế thiết kế semantics và compatibility test.

### 17.4. “Database migration có thể chạy ngay lúc deploy”

Drop/rename cột trước khi code cũ biến mất sẽ làm rollback khó hoặc bất khả thi. Migration phải được chia pha, tính đến lock, dữ liệu lịch sử, concurrent writer và giới hạn rollback.

### 17.5. “Chỉ test bản mới với bản mới”

Môi trường staging toàn bản mới bỏ sót mismatch khi production chạy rolling update. Kiểm tra cả **old consumer/new producer**, **new consumer/old producer**, dữ liệu cũ/mới, event pending và rollback.

### 17.6. “Consumer bỏ qua lỗi là đã tương thích”

Deserialization thành công nhưng logic dùng default sai có thể gây mất tiền hoặc vi phạm nghiệp vụ. Thiết kế default rõ ràng, kiểm tra status chưa biết, và từ chối thao tác an toàn hơn khi không đủ dữ liệu quan trọng.

### 17.7. “Cho mọi service dùng một model thống nhất”

Shared domain library tạo coupling khi semantics thay đổi. Mỗi bounded context có mô hình riêng; tích hợp bằng hợp đồng và mapping rõ ràng, kể cả khi thêm chút code chuyển đổi.

## 18. Checklist kiểm tra trước một release có thay đổi hợp đồng

1. **Owner:** Ai sở hữu API/event/data/policy? Có danh sách consumer đang dùng không?
2. **Scope:** Thay đổi field, enum, state machine, dữ liệu, schema hay cấu hình nào?
3. **Compatibility:** Producer và consumer cũ/mới tương tác thế nào? Test có bao gồm ngữ nghĩa nghiệp vụ không?
4. **Mixed versions:** Rolling update, multi-region, mobile client, retry và queue có thể duy trì phiên bản cũ bao lâu?
5. **Database:** Có expand schema trước không? Old code còn chạy được? Backfill có an toàn không?
6. **Migration:** Ai chịu trách nhiệm từng pha expand, migrate, contract? Tiêu chí nào xác nhận có thể dừng v1?
7. **Feature activation:** Có thể deploy code trước rồi bật hành vi sau không? Có điều kiện readiness không?
8. **Rollback:** Hạ service hoặc tắt feature có giữ dữ liệu đúng? Có thay đổi không thể đảo ngược không?
9. **Observation:** Có metrics, tracing, contract errors, DLQ, backlog và cảnh báo phù hợp không?
10. **Cleanup:** Khi nào xóa field, handler, flag, adapter, bảng và code chuyển tiếp?
11. **Ownership:** Runbook xử lý sự cố, người quyết định rollback và điểm dừng rollout đã rõ chưa?
12. **Evidence:** Kết luận tương thích dựa trên test nào, version nào và môi trường nào?

Một release có thể đi qua nhiều bước có thứ tự **mà vẫn có tính triển khai độc lập**, miễn từng bước tạo trạng thái an toàn và có thể dừng. Thứ tự có kế hoạch không đồng nghĩa với yêu cầu thay đổi đồng thời trong một cửa sổ hẹp.

## 19. Bài thực hành: kiểm tra ranh giới Pricing–Ordering–Payments

Giả sử doanh nghiệp bổ sung mã khuyến mại có thể áp dụng riêng cho từng item. Hiện tại:

- Pricing trả totalAmount là số nguyên.
- Ordering lưu totalAmount và các dòng hàng.
- Payments nhận totalAmount từ Ordering và chỉ cho phép tạo payment một lần theo orderId.
- Reporting đọc trực tiếp bảng orders để tính doanh thu.

Phiên bản mới cần hỗ trợ itemDiscounts, totalBeforeDiscount, totalAfterDiscount và trạng thái PAYMENT_PENDING_REVIEW cho một số đơn hàng. Team đề xuất deploy đồng thời cả bốn ứng dụng.

Hãy thực hiện:

1. Xác định các phụ thuộc runtime, build, database và release cụ thể.
2. Lập ma trận old/new cho API Pricing → Ordering và Ordering → Payments.
3. Phân biệt field additive với thay đổi semantics của totalAmount và payment status.
4. Đề xuất expand/migrate/contract cho API, event và bảng orders.
5. Thiết kế cơ chế tránh thanh toán trùng khi message gửi lại hoặc consumer nhận hai version.
6. Cho biết khi nào Reporting có thể tách khỏi bảng orders và nhận read model/event.
7. Xác định những giai đoạn có thể rollback, giai đoạn nào cần roll forward.
8. Đề xuất ba contract tests và ba integration/rollback tests chứng minh không cần deploy cùng một cửa sổ.

Một hướng phân tích khả thi:

~~~text
Pricing:
  - Bổ sung fields mới, giữ totalAmount cũ có định nghĩa rõ
  - Công bố contract và hỗ trợ consumer cũ

Ordering:
  - Đọc cả định dạng cũ/mới trong thời gian chuyển tiếp
  - Chốt snapshot giá/discount theo ruleVersion
  - Chỉ phát status mới khi Payments đã có handler tương thích

Payments:
  - Thêm handler đọc status mới trước khi Ordering phát ra
  - Thực thi idempotency theo payment operation key
  - Không ngầm coi trạng thái lạ là "đã thanh toán"

Reporting:
  - Chuyển dần từ query trực tiếp bảng orders sang event/read model
  - Kiểm tra sai lệch dữ liệu rồi gỡ quyền đọc bảng
~~~

Với thay đổi như trên, việc **kích hoạt chính sách giảm giá** có thể được điều phối ở một thời điểm do nghiệp vụ quyết định, trong khi deployment code cho từng service diễn ra trước đó và ở những ngày khác nhau.

## 20. Tóm lược quyết định kiến trúc

Để nhận diện phụ thuộc triển khai và phát hành đồng bộ, luôn xuất phát từ **một thay đổi cụ thể** và hỏi: “Nếu chỉ triển khai service này, những phiên bản còn lại có tiếp tục xử lý đúng request, event, dữ liệu và trạng thái không?” Nếu câu trả lời là “không”, truy đến contract hoặc quyền sở hữu gây xung đột.

Để giảm coupling, ưu tiên hợp đồng tương thích, owner dữ liệu rõ ràng, quản lý phiên bản, contract testing, migration theo pha và tách deployment khỏi feature activation. Chỉ xem xét gộp service hoặc thay đổi ranh giới nghiệp vụ sau khi đã xác định nguồn phụ thuộc thực sự. Thước đo thành công là **mỗi thay đổi có thể được triển khai, quan sát, tạm dừng và phục hồi trong một phạm vi kiểm soát được**, trong khi các bất biến nghiệp vụ vẫn được bảo vệ.