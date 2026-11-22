# Giảm phụ thuộc bàn giao và lịch phát hành đồng bộ

**Nhóm kiến thức:** Tổ chức nhóm trong Software Design, System Architecture và Microservices.

Một hệ thống được chia thành nhiều microservice nhưng mỗi lần phát hành vẫn phải họp năm nhóm, chờ một nhóm DBA sửa schema, chờ nhóm nền tảng tạo namespace, chờ nhóm kiểm thử chạy regression cho mọi ứng dụng, rồi cùng deploy vào một đêm cuối tuần thì **khả năng phát hành độc lập chỉ tồn tại trên sơ đồ kiến trúc**. Mỗi dịch vụ có thể là một repository hoặc một container riêng, nhưng quy trình thay đổi vẫn tạo ra một **distributed monolith về mặt tổ chức và vận hành**.

Nguyên nhân có thể nằm ở ranh giới trách nhiệm không rõ, hợp đồng giữa dịch vụ thiếu ổn định, quyền truy cập hạ tầng bị tập trung, database dùng chung, pipeline chưa tự phục vụ, môi trường thử nghiệm chung dễ va chạm hoặc thói quen coi mỗi thay đổi đều phải lên cùng một release train. Khi nhiều bước bàn giao nối tiếp, **thời gian chờ** thường lớn hơn thời gian thực sự viết và kiểm thử code.

Mục tiêu của bài học là thiết kế **quyền sở hữu đầu-cuối, giao tiếp qua hợp đồng, nền tảng tự phục vụ và cơ chế phát hành an toàn** để phần lớn thay đổi thường ngày có thể đi từ ý tưởng đến production mà không cần đồng bộ lịch nhiều nhóm. Bài học cũng phân biệt trường hợp nào vẫn cần phối hợp chủ đích, cách đo điểm nghẽn và phương án chuyển đổi từng bước mà không làm tăng rủi ro bảo mật hay chất lượng.

## 1. Nhận diện đúng vấn đề: handoff không phải mọi sự hợp tác

**Bàn giao (handoff)** là chuyển công việc hoặc trách nhiệm từ một chủ thể sang chủ thể khác để có thể tiếp tục tiến trình. Một số bàn giao bắt buộc vì chuyên môn, rủi ro hoặc phân quyền; nhưng nhiều bàn giao chỉ tồn tại vì tổ chức phân chia trách nhiệm theo công đoạn quá cứng.

Ví dụ luồng phát hành một thay đổi nhỏ:

~~~text
Business yêu cầu
    |
    v
Nhóm phân tích viết ticket
    |
    v
Backend thiết kế API
    |
    v
Nhóm database sửa schema
    |
    v
Nhóm frontend tích hợp
    |
    v
Nhóm QA kiểm thử thủ công
    |
    v
Nhóm DevOps chạy deploy
    |
    v
Nhóm SRE xác nhận release
~~~

Mỗi mũi tên có thể thêm queue, chờ giải thích lại yêu cầu, chuyển trạng thái ticket và rủi ro hiểu sai ngữ cảnh. Nếu mỗi bước mất 30 phút làm việc nhưng chờ 1–2 ngày mới được xử lý, lead time không phản ánh độ phức tạp của thay đổi.

**Hợp tác tốt** là các nhóm cùng giải quyết vấn đề khó, trao đổi kỹ thuật và ra quyết định có chủ đích. **Handoff gây nghẽn** là khi một nhóm đã hoàn thành phần mình nhưng không thể tạo giá trị tiếp vì thiếu quyền, thông tin, công cụ hoặc xác nhận mang tính hình thức từ nhóm khác.

Không đặt mục tiêu “không bao giờ cần liên hệ nhóm khác”. Mục tiêu hợp lý là **phần lớn thay đổi có ranh giới rõ có thể được thực hiện và phát hành tự chủ**, trong khi thay đổi xuyên ranh giới, có tác động hệ thống hoặc rủi ro cao vẫn được phối hợp qua một quy trình minh bạch.

## 2. Ví dụ: một thay đổi nhỏ nhưng cần đồng bộ sáu nhóm

Giả sử ứng dụng thương mại điện tử muốn thêm trường **deliveryInstruction** cho địa chỉ giao hàng.

Cách vận hành có nhiều phụ thuộc:
1. Web team chờ Backend thêm trường DTO.
2. Backend chờ Database team thêm cột.
3. Orders team chờ Shipping team cập nhật sự kiện.
4. Shipping team chờ công bố schema chung.
5. QA team chờ cả web/backend/shipping sẵn sàng trên một staging dùng chung.
6. Release manager đặt lịch tối thứ Sáu để mọi dịch vụ lên phiên bản mới cùng lúc.

Một trường tùy chọn đáng lẽ là thay đổi có thể triển khai tiến dần, nhưng vì các thành phần yêu cầu phiên bản mới phải xuất hiện đồng thời, tổ chức phải tạo **điểm hội tụ lịch phát hành**. Chỉ một nhóm chưa xong cũng giữ các nhóm khác.

Một hướng thiết kế khác:
- Owner của Delivery/Checkout xác định hợp đồng mới và mức tương thích.
- Database được mở rộng trước bằng migration **additive** an toàn.
- Backend chấp nhận cả payload cũ và mới, trường mới optional hoặc có default đúng nghĩa.
- Event/schema cho Shipping tiến hóa tương thích, có contract test giữa các phiên bản.
- Frontend bật cách gửi trường mới bằng feature flag sau khi khả năng đọc đã có.
- Mỗi nhóm chạy pipeline và canary của mình; không yêu cầu mọi service cùng deploy một lúc.
- Đường rollback vẫn đọc được dữ liệu đã ghi và sự kiện đã phát.

Đây là mục tiêu **loại bỏ phụ thuộc về thứ tự phát hành không cần thiết**. Tổ chức vẫn cần thống nhất hợp đồng, owner, SLO và thời điểm loại bỏ phiên bản cũ; chỉ không cần chờ một “ngày phát hành chung” cho mọi thay đổi thông thường.

## 3. Quyền sở hữu đầu-cuối của một nhóm

Một team sở hữu dịch vụ không chỉ là nhóm “viết code” cho dịch vụ đó. **End-to-end ownership** nên bao gồm vòng đời đủ để tự đưa một thay đổi phù hợp phạm vi đến production:

~~~text
Yêu cầu nghiệp vụ
    |
Thiết kế và phân tích rủi ro
    |
Code + schema/API contract
    |
Unit/contract/integration tests
    |
Build immutable artifact
    |
Deploy theo pipeline được cấp quyền
    |
Quan sát SLO + hỗ trợ vận hành
    |
Cải tiến từ incident và phản hồi người dùng
~~~

Một team nên biết rõ:
- **Capability** nghiệp vụ nào họ sở hữu.
- API, sự kiện, job, database và dữ liệu nào thuộc họ.
- Ai có quyền sửa và phát hành, ai chịu trách nhiệm trực khi có sự cố.
- Các SLO/SLI quan trọng và ngân sách rủi ro.
- Các phụ thuộc ngoài team và hợp đồng sử dụng.
- Cách phát hành, rollback và kiểm chứng không phải xin thao tác thủ công từ một team khác.
- Khi nào cần tham vấn Security, Data, Platform hoặc một chủ thể được phân quyền.

Ownership đầu-cuối **không có nghĩa một nhóm tự làm mọi việc chuyên môn**. Nền tảng có thể cung cấp CI/CD, secret manager, quan sát và chuẩn bảo mật; nhóm ứng dụng sử dụng các dịch vụ đó qua interface tự phục vụ. Security vẫn đặt guardrail và review những thay đổi rủi ro cao. Điều cần giảm là **các bước xin phép thủ công lặp lại** cho một hành động đã được cho phép theo chính sách.

## 4. Xác định ranh giới team từ nghiệp vụ thay vì lớp kỹ thuật

Một mô hình tổ chức phổ biến là tách đội Frontend, Backend, Database, QA, DevOps. Mỗi thay đổi tính năng xuyên nhiều lớp nên tạo nhiều ticket/handoff.

Một hướng khác là tổ chức các **stream-aligned teams** quanh dòng giá trị hoặc năng lực nghiệp vụ như Checkout, Catalog, Payments, Fulfillment. Mỗi nhóm có năng lực đa chức năng đủ để xử lý phần lớn công việc thường xuyên trong ranh giới của mình.

| Ranh giới | Ví dụ team sở hữu | Trách nhiệm chính |
|---|---|---|
| Catalog | Catalog Team | Sản phẩm, tìm kiếm thông tin hàng hóa, catalog API |
| Checkout | Checkout Team | Tạo đơn, hành trình checkout, hợp đồng OrderCreated |
| Payments | Payments Team | Thanh toán, đối soát, trạng thái payment |
| Fulfillment | Fulfillment Team | Giao hàng, vận đơn, giao tiếp đơn vị vận chuyển |
| Internal Platform | Platform Team | Golden path, pipeline, secrets, observability, cluster nền |
| Security enablement | Security Team | Guardrails, threat modeling, kiểm soát rủi ro và hỗ trợ tự động hóa |

Đây là một mô hình minh họa, không phải cơ cấu bắt buộc. Có tổ chức nhỏ chỉ cần một product team và một platform function bán thời gian; có tổ chức lớn cần nhiều team trên cùng một domain.

**Ranh giới tốt** giảm số thay đổi cần chạm đồng thời vào nhiều team. Nó thường liên quan đến **bounded context** trong Domain-Driven Design: khái niệm nghiệp vụ, quy tắc và nguồn dữ liệu có ý nghĩa nhất quán bên trong một ranh giới.

Không nên tách team chỉ vì mỗi service có một repository. Nếu ba service thường xuyên thay đổi cùng nhau vì cùng một use case và chia sẻ dữ liệu, có thể ranh giới service/team đang bị chia quá vụn.

## 5. Đặt giới hạn cognitive load cho team

Đưa toàn bộ trách nhiệm vào một team nhỏ có thể giảm handoff trên giấy nhưng làm team quá tải. Một nhóm phải hiểu hàng chục công nghệ, nhiều môi trường, IAM, observability, database, broker, UI và mọi hệ thống đối tác sẽ mất khả năng tập trung vào nghiệp vụ.

Vì vậy, tối ưu là **giảm handoff đồng thời giữ tải nhận thức ở mức có thể quản lý**, không phải ép mỗi đội tự xây toàn bộ nền tảng.

Ba câu hỏi:
1. Team cần biết những gì để thay đổi thành công dịch vụ của mình?
2. Công việc nào lặp lại giữa nhiều team và nên được **chuẩn hóa thành platform capability**?
3. Công việc nào hiếm, phức tạp và cần hỗ trợ chuyên gia theo thời hạn, thay vì vĩnh viễn trở thành ticket queue?

Ví dụ: Team Checkout cần biết dùng pipeline chuẩn để tạo canary, nhưng không nhất thiết phải thiết kế hệ thống quản lý chứng chỉ cho cả công ty. Team Platform cung cấp cơ chế cấp chứng chỉ, tài liệu, template và guardrail; Checkout tự sử dụng nó mà không phải đợi một người tạo file thủ công.

Mỗi khi thêm một yêu cầu mới như tracing hay secret rotation, cân nhắc đưa nó vào **golden path** để các team sử dụng nhất quán.

## 6. Phụ thuộc nào có thể loại bỏ, phụ thuộc nào phải quản trị?

Không phải mọi phụ thuộc giữa team đều xấu. Phân loại trước khi xử lý:

| Loại phụ thuộc | Ví dụ | Hướng xử lý |
|---|---|---|
| **Phụ thuộc dữ liệu/API** | Checkout cần PaymentStatus | Contract rõ, versioning, backward/forward compatibility |
| **Phụ thuộc thứ tự deploy** | Consumer cũ không đọc được event mới | Expand/contract, dual-read/dual-write có kiểm soát |
| **Phụ thuộc môi trường** | Cả team chờ một staging | Test isolation, ephemeral environment, contract test |
| **Phụ thuộc quyền/hạ tầng** | Mỗi deploy phải nhờ DevOps | Self-service pipeline với IAM tối thiểu |
| **Phụ thuộc kiến thức** | Chỉ một chuyên gia biết rollback | Runbook, pairing, tài liệu, diễn tập |
| **Phụ thuộc phê duyệt** | Mọi config đều qua họp hàng tuần | Policy-as-code, phân loại rủi ro và auto-approval trong guardrail |
| **Phụ thuộc lịch vận hành** | Mọi service phát hành cùng đêm | Independent rollout và version skew |
| **Phụ thuộc chung bất khả tránh** | Thay đổi pháp lý hoặc giao thức thanh toán xuyên domain | Lập kế hoạch phối hợp có owner, deadline và phương án chuyển đổi |

Một cách làm hữu ích là hỏi: **Phụ thuộc này tồn tại vì yêu cầu nghiệp vụ thật, vì hợp đồng kỹ thuật, hay vì quy trình tổ chức?** Ba nguồn gốc dẫn đến ba loại giải pháp khác nhau.

Nếu phụ thuộc chỉ tồn tại vì “nhóm A phải bấm nút deploy cho nhóm B”, giải pháp có thể là cấp pipeline tự phục vụ. Nếu do hai service cùng sửa một bảng DB, cần tái thiết kế ownership/schema, không thể chỉ thay Jira workflow.

## 7. Bản đồ phụ thuộc giữa các team

Vẽ đồ thị giữa **team, service và thay đổi** chứ không chỉ sơ đồ hạ tầng.

~~~mermaid
flowchart LR
    C["Checkout Team"] -->|"Payment API"| P["Payments Team"]
    C -->|"Order event"| F["Fulfillment Team"]
    C -->|"Pipeline, secrets, telemetry"| PL["Platform Team"]
    P -->|"Policy yêu cầu"| SEC["Security Team"]
    F -->|"Carrier contract"| X["External partner"]
~~~

Các cạnh chưa nói mức độ phụ thuộc. Với mỗi cạnh, ghi:
- **Contract owner** và người liên hệ.
- Loại giao tiếp: HTTP, event, data projection, CI/CD, review.
- Tần suất cần phối hợp trong một tháng.
- Một thay đổi đơn phương có phá bên kia không?
- Có test hợp đồng tự động không?
- Có quyền tự deploy trong guardrail không?
- Có phải chờ lịch phát hành chung không?
- Có SLO hoặc điều kiện escalation không?

Mục tiêu không phải xóa mọi cạnh. Mục tiêu là chuyển càng nhiều cạnh càng tốt từ **phụ thuộc đồng bộ trong mỗi lần thay đổi** thành **phụ thuộc qua hợp đồng ổn định, tự kiểm chứng và có thể triển khai lệch phiên bản**.

### 7.1. Đồ thị thay đổi (change coupling)

Nếu service A và B luôn phải sửa cùng một PR hoặc release để thêm một feature, đó có thể là dấu hiệu coupling dù chúng gọi nhau ít khi chạy.

Đo **tỷ lệ thay đổi liên quan nhiều repository/team**, số lần cùng rollout, số lần phải chờ release đối tác và số incident do version mismatch. Số liệu kết hợp với bối cảnh nghiệp vụ mới cho biết cần thay kiến trúc hay quy trình.

Một service được deploy độc lập về kỹ thuật nhưng mỗi deploy vẫn phải chờ xác nhận từ 4 team là độc lập chưa hoàn chỉnh.

## 8. Independent deployability: năng lực, không chỉ tính năng pipeline

Một dịch vụ được coi là **có thể deploy độc lập** khi team có khả năng phát hành một thay đổi hợp lệ của dịch vụ đó mà không phải đồng thời phát hành các service không thuộc mình, đồng thời vẫn giữ các hợp đồng người dùng và downstream đã công bố.

Điều kiện thường cần:

1. Artifact được build và version hóa riêng.
2. Pipeline có thể kiểm thử và deploy riêng trong quyền được cấp.
3. API/event/schema hỗ trợ khoảng lệch phiên bản cần thiết.
4. Database change có chiến lược migration không yêu cầu deploy cùng thời điểm.
5. Quan sát riêng theo service, version, region và SLO.
6. Traffic có thể canary/rollout/rollback trong giới hạn an toàn.
7. Cấu hình và secret của service có phạm vi riêng.
8. Các test không phụ thuộc một môi trường dùng chung bất ổn.
9. Owner và escalation rõ.
10. Thay đổi không làm mất dữ liệu hoặc gây side effect không thể phục hồi khi rollback.

**Không đánh đồng “deployment độc lập” với “mọi thay đổi đều độc lập”.** Một thay đổi làm biến đổi hợp đồng tài chính hoặc buộc chuyển quy trình nghiệp vụ ở nhiều domain vẫn cần phối hợp. Mục tiêu là phần lớn thay đổi additive, nội bộ và có hợp đồng ổn định không bắt buộc phụ thuộc lịch của người khác.

## 9. Contract-first: API giữa nhóm là sản phẩm có người sử dụng

Một nhóm sở hữu Payment API nên coi các consumer như khách hàng nội bộ của contract, không yêu cầu họ đọc source code để đoán behavior.

Contract nên mô tả:
- Endpoint/event type và mục đích.
- Request/response schema, kiểu, required/optional và giá trị null.
- Quy tắc semantic: trạng thái, đơn vị tiền, thời điểm phát event.
- Authentication, authorization và giới hạn dữ liệu.
- Idempotency, retry, rate limit và timeout.
- Lỗi và khả năng khôi phục.
- Quy tắc tương thích, deprecation và thời hạn hỗ trợ.
- Thông tin owner, SLO, changelog và cách xác minh.

Ví dụ một phần hợp đồng API thanh toán:

~~~yaml
api: payment-status
owner: payments-team
version: v1
operation: getPaymentStatus
input:
  orderId: required-string
output:
  paymentState:
    enum: [PENDING, AUTHORIZED, CAPTURED, FAILED, UNKNOWN]
  lastUpdatedAt: iso8601-utc
semantics:
  UNKNOWN: "Không đủ thông tin để xác nhận trạng thái"
  CAPTURED: "Đã được cổng thanh toán xác nhận theo hợp đồng"
reliability:
  readTimeoutBudgetMs: 800
  idempotentRead: true
compatibility:
  unknownEnumHandling: required
  additiveFieldsAllowed: true
ownerContact: payments-oncall
~~~

Đây là **mẫu tài liệu nghiệp vụ**, không phải schema máy có thể chạy trực tiếp. Các giá trị timeout hay enum cần được quyết định từ nhu cầu và dịch vụ thật.

Nếu consumer mới buộc producer thay đổi để nó chạy, cần xem consumer có thể sử dụng contract hiện có, event read model hoặc adapter không, thay vì tự động mở yêu cầu đồng bộ hai team.

## 10. Tương thích hai chiều để không phải deploy cùng lúc

Giả sử Producer P1 phát sự kiện OrderCreated v1, Consumer C1 đọc. Đội Checkout muốn phát v2 có thêm trường tùy chọn **deliveryInstruction**.

Các tổ hợp có thể xuất hiện trong rolling deployment:

| Writer | Reader | Điều cần kiểm tra |
|---|---|---|
| P1 | C1 | Trạng thái cơ sở |
| P1 | C2 | Reader mới đọc event cũ khi nâng consumer trước |
| P2 | C1 | Reader cũ chịu được event mới khi nâng producer trước |
| P2 | C2 | Trạng thái mục tiêu |
| P0 trong lịch sử | C2 | Replay nếu broker/backup còn dữ liệu từ version rất cũ |

**Backward compatibility** thường nghĩa reader mới đọc writer cũ. **Forward compatibility** thường nghĩa reader cũ đọc writer mới. **Full compatibility** bao gồm cả hai hướng; mức **transitive** xét thêm các phiên bản lịch sử theo cấu hình kiểm tra.

Đây là ngữ nghĩa tổng quát; mức hỗ trợ cụ thể phụ thuộc Avro, JSON Schema, Protobuf và serializer đang dùng. Không coi schema registry cho phép đăng ký là bằng chứng thay đổi business semantics an toàn.

Với HTTP/JSON, consumer cũ có thể từ chối trường lạ nếu deserializer cấu hình strict. Với Protobuf, field number có vai trò quyết định binary wire compatibility. Với Avro, schema resolution và default ở reader có quy tắc riêng. Mỗi tổ hợp phải được kiểm thử bằng client/serializer thật của các version còn hỗ trợ.

### 10.1. Tại sao rollback cũng cần tính tương thích?

Một producer mới có thể đã gửi event v2 vào broker. Dù rollback producer về v1, **message v2 vẫn còn trong queue/topic**. Nếu rollback mọi consumer về C1 không đọc được v2, hệ thống có thể bị kẹt. Vì vậy, một đường rollback an toàn đôi khi phải **giữ reader mới** hoặc adapter cho dữ liệu đã phát.

Independent deployment phụ thuộc vào khả năng xử lý **phiên bản khác nhau cùng tồn tại**, không chỉ khả năng bắt đầu một container mới.

## 11. Expand → migrate → contract để giải quyết thứ tự phát hành

Một trong những kỹ thuật quan trọng nhất là thay đổi qua nhiều giai đoạn có thời gian chồng lấp phiên bản.

~~~mermaid
flowchart LR
    A["Current contract"] --> B["Expand: hỗ trợ cũ và mới"]
    B --> C["Migrate: chuyển client/consumer"]
    C --> D["Verify: không còn phụ thuộc cũ"]
    D --> E["Contract: bỏ hỗ trợ cũ"]
~~~

**Expand:** thêm khả năng mới mà chưa phá client cũ. Ví dụ thêm trường nullable, endpoint mới, dual-reader hoặc cột DB mới.

**Migrate:** nâng từng client/consumer, chuyển dần traffic hoặc ghi dữ liệu theo format mới; không cần họ lên cùng phút.

**Verify:** quan sát lưu lượng phiên bản cũ, schema usage, backlog, retention, client còn đang dùng, kết quả nghiệp vụ và chất lượng dữ liệu.

**Contract:** loại trường/endpoint cũ sau khi điều kiện hỗ trợ đã đạt, có thông báo và phương án xử lý replay/rollback.

Điểm mấu chốt là trong giai đoạn chuyển đổi, **producer và consumer phải có cửa sổ phiên bản chồng lấp được**, giúp các đội phát hành theo nhịp riêng.

### 11.1. Ví dụ đổi trường tiền

Ban đầu event có amount kiểu decimal. Bản mới muốn dùng **amountMinor** dạng integer và currency.

Không đổi thẳng ý nghĩa **amount** từ đơn vị lớn sang đơn vị nhỏ mà giữ tên/kiểu rồi mặc định tương thích. Nên:
1. Consumer mới hiểu cả amount và amountMinor.
2. Producer xuất cả hai trường trong giai đoạn chuyển đổi khi hợp đồng cho phép.
3. Contract test xác minh quy tắc chuyển đổi, đơn vị và làm tròn.
4. Migrate mọi consumer đã được kiểm kê, gồm batch job và data warehouse.
5. Đảm bảo replay dữ liệu lịch sử.
6. Loại field cũ chỉ khi điều kiện hỗ trợ và rollback đã được đánh giá.

Một thay đổi có **schema hợp lệ nhưng semantic sai** vẫn có thể gây thiệt hại lớn. Giảm handoff không được đánh đổi bằng việc bỏ review thay đổi tài chính quan trọng.

## 12. Database migration không buộc hai service phát hành đồng bộ

Một nguyên nhân release train là schema DB thay đổi theo ứng dụng mới mà phiên bản cũ không chạy được. Đặc biệt nguy hiểm khi nhiều service dùng chung một database schema.

Ví dụ: Checkout muốn đổi cột **shipping_note** sang **delivery_instruction**.

Không nên lập kế hoạch:

~~~text
22:00 ngừng mọi service
22:05 RENAME COLUMN shipping_note
22:06 deploy mọi consumer và producer
22:10 chạy toàn bộ regression
22:20 mở traffic
~~~

Một lộ trình **expand/contract** có thể là:

1. Thêm cột delivery_instruction, giữ cột cũ.
2. Đưa code mới đọc linh hoạt theo kế hoạch và hỗ trợ dữ liệu cũ.
3. Chuyển ghi từ cũ sang mới, có thể dùng dual-write tạm thời nếu cần và có kiểm tra nhất quán.
4. Backfill dữ liệu theo batch có kiểm soát, đo tiến độ.
5. Chuyển mọi reader sang cột mới.
6. Đo xem cột cũ còn được đọc/ghi không.
7. Bỏ cột cũ trong một phiên bản sau, khi rollback không còn phụ thuộc nó.

**Dual-write có rủi ro sai lệch**, nhất là khi viết vào hai nguồn dữ liệu khác nhau. Nếu thực hiện trong cùng database, cần transaction/invariant rõ; nếu xuyên service, cân nhắc outbox/event và reconciliation. Không xem dual-write là giải pháp mặc định cho mọi tình huống.

**Sở hữu dữ liệu:** Team của một bounded context nên sở hữu mô hình lưu trữ và migration. Các team khác không nên đọc trực tiếp bảng của team đó, vì mỗi thay đổi schema sẽ trở thành sự kiện đồng bộ nhiều nhóm.

## 13. Consumer-driven contract testing giúp loại bỏ “chờ team kia test”

Nếu mỗi thay đổi Producer đều phải chờ Consumer Team chạy thủ công toàn bộ ứng dụng, hai đội vẫn bị ràng buộc bởi lịch nhau.

**Consumer-driven contract** cho phép consumer định nghĩa những kỳ vọng nó cần, ví dụ:
- Field nào bắt buộc.
- Trạng thái enum và cách xử lý unknown.
- Giá trị tiền và đơn vị.
- Mã lỗi, semantic và độ mới dữ liệu.
- Hành vi retry/idempotency.
- Các sự kiện được phát sau điều kiện nghiệp vụ nào.

Kỳ vọng được công bố tại kho contract/test artifact được kiểm soát. Khi producer thay code, pipeline của producer chạy xác minh các hợp đồng consumer được hỗ trợ.

~~~mermaid
flowchart LR
    C["Consumer Team"] -->|"Published expectations"| K["Contract repository / registry"]
    K --> P["Producer CI"]
    P --> T{"Compatible and semantic tests pass?"}
    T -->|Yes| D["Independent rollout"]
    T -->|No| F["Fix or coordinate breaking change"]
~~~

Điều này **không thay thế hoàn toàn integration tests**. Contract test không thể bảo đảm mọi cấu hình broker, chứng chỉ, network, sự cố dependency đều đúng. Nhưng nó giảm việc phải dựng toàn bộ hệ thống và chờ người khác chạy manual QA cho mọi thay đổi additive.

Công cụ như Pact, schema registry và test fixture tự xây có thể phục vụ những phần khác nhau; không phụ thuộc vào một thương hiệu để áp dụng nguyên tắc.

### 13.1. Tránh hợp đồng quá chặt

Nếu consumer contract khẳng định response phải chứa đúng 12 field và không được có field thứ 13 dù không dùng, producer sẽ khó tiến hóa. Cần phân biệt:
- **Kỳ vọng quan trọng với consumer:** field, semantics, bảo mật và behavior.
- **Chi tiết triển khai không quan trọng:** thứ tự field JSON, header không liên quan hoặc trường mới optional được phép.

Contract phải chặt ở những gì ảnh hưởng đúng/sai nghiệp vụ, linh hoạt ở phần mở rộng được công bố.

## 14. Tạo một “testing pyramid” giảm phối hợp đồng bộ

Một hệ thống muốn phát hành riêng nên có test chạy được mà không phải khởi động mọi microservice ở staging.

| Tầng | Thực hiện | Giá trị |
|---|---|---|
| **Unit tests** | Kiểm tra logic, validation và mapping trong service | Phản hồi nhanh cho developer |
| **Component tests** | Chạy service với DB/broker hoặc test double phù hợp | Kiểm tra cấu hình và behavior cục bộ |
| **Contract tests** | Producer ↔ consumer schema/semantic expectations | Phát hiện breaking change giữa team |
| **Integration tests** | Serializer, DB, broker, auth và dependency thiết yếu | Bắt lỗi giao thức/hạ tầng |
| **End-to-end tests** | Một số critical journeys xuyên hệ thống | Bảo đảm luồng nghiệp vụ tổng thể |
| **Production verification** | Canary, synthetic, SLI và metric theo revision | Xác minh môi trường thật |

E2E vẫn hữu ích cho hành trình cốt lõi, nhưng nếu **mọi PR đều phải chờ một E2E toàn hệ thống không ổn định**, pipeline trở thành chốt nghẽn. Nên giữ số luồng E2E có giá trị và chuyển nhiều điều kiện sang contract/component tests nhanh, độc lập.

**Không biến test double thành sự thật giả.** Mock luôn trả thành công có thể khiến producer và consumer đồng ý trong test nhưng không tương thích ở runtime. Đối với behavior quan trọng, fixture phải xuất phát từ contract/serializer thực tế, và integration test cần kiểm tra adapter thật.

## 15. Môi trường thử nghiệm độc lập và có thể tái tạo

Một staging chung có thể gây handoff vì:
- Team A đang test schema mới khiến Team B bị lỗi.
- Mọi người phải đăng ký slot.
- Dữ liệu test bị sửa lẫn nhau.
- Test chạy không thể biết đang dùng phiên bản service nào.
- Một pipeline E2E chặn mọi nhóm phát hành.

Các phương án:
- **Ephemeral environment** cho PR hoặc một nhóm thay đổi khi chi phí phù hợp.
- **Namespace/tenant test isolation** cùng seed data riêng.
- **Consumer contract test** chạy độc lập với dịch vụ khác.
- **Service virtualization** hoặc test doubles có hợp đồng.
- **Testcontainers** hoặc môi trường cục bộ cho DB/broker thiết yếu.
- **Version pinning** khi chạy tập hợp service test.
- **Synthetic journey** ở staging/prod canary cho đường nghiệp vụ thật.

Tuy nhiên, không cần clone toàn bộ 200 dịch vụ cho mỗi PR: chi phí, startup và flakiness có thể vượt lợi ích. Chọn mức cô lập theo rủi ro và loại test; phần lớn validation đơn lẻ nên nhanh và có thể tái tạo.

Một CI pipeline độc lập vẫn phải giữ các cổng bảo mật/chất lượng đã thỏa thuận. Tự phục vụ không đồng nghĩa được vượt quy trình khi test đỏ.

## 16. Platform as a product: cắt hàng đợi DevOps thủ công

Nhiều handoff đến từ việc team ứng dụng phải nhờ Platform/SRE để:
- Tạo repository và pipeline.
- Cấp namespace, service account, secret.
- Provision database hoặc queue.
- Thiết lập dashboard/logging.
- Cấu hình canary, autoscaling và ingress.
- Phát hành một image sang production.
- Quản lý TLS certificate hoặc workload identity.

Nếu mỗi yêu cầu đều là ticket được xử lý thủ công, Platform trở thành **bottleneck trung tâm** khi số team tăng.

Hướng tốt hơn là cung cấp **Internal Developer Platform** như một sản phẩm nội bộ:

~~~text
Developer chọn service template
    |
    v
Platform portal / CLI / GitOps API
    |
    +-- Repo + CI template
    +-- Service account + least-privilege IAM
    +-- Container deployment + autoscaling defaults
    +-- Secret reference + config management
    +-- Logs, metrics, traces, alert labels
    +-- Service catalog + owner metadata
    +-- Canary, rollback, environment promotion
    |
    v
Team tự phát hành trong guardrail
~~~

Các yêu cầu còn cần chuyên gia nên có lối escalation, ví dụ workload GPU, dữ liệu cực nhạy cảm hoặc network policy đặc biệt.

Platform team cần **đo adoption, độ tin cậy, thời gian self-service và developer experience**. Một portal đẹp nhưng thường xuyên lỗi, template không được nâng cấp hoặc không có tài liệu sẽ tạo handoff khác dưới tên mới.

### 16.1. Golden path không phải khóa cứng sáng tạo

**Golden path** là lộ trình chuẩn, được hỗ trợ tốt để tạo/triển khai dịch vụ thông thường. Nó giảm số quyết định lặp, chuẩn hóa an toàn và rút thời gian từ commit đến môi trường chạy.

Đội vẫn có thể đi đường ngoại lệ khi workload khác biệt thật, nhưng ngoại lệ phải có owner, threat model và khả năng vận hành. Nếu mọi dịch vụ bị ép dùng cùng một runtime/DB dù không phù hợp, đội có thể tìm cách vượt platform, tạo “shadow DevOps” và tăng rủi ro.

## 17. Self-service đi cùng guardrail, không phải bỏ kiểm soát

Cấp quyền cluster-admin cho mọi developer có thể giảm chờ DevOps nhưng làm tăng nguy cơ xóa nhầm dữ liệu và mở cửa leo thang.

Thiết kế tốt hơn:
- Pipeline triển khai bằng danh tính theo service/environment.
- Quyền IAM/RBAC giới hạn tài nguyên và hành động.
- Infrastructure-as-code có template, policy-as-code và review thích hợp.
- Image signing/SBOM/vulnerability scan theo chính sách.
- Deployment policies cho min replicas, resource requests, network và secret.
- Canary tự động dừng nếu SLO guardrail không đạt.
- Logging/audit mỗi lần thay đổi và rollback.
- Break-glass có thời hạn, lý do và dấu vết.
- Phê duyệt thủ công chỉ cho thay đổi vượt mức rủi ro đã xác định.

**Tự động hóa kiểm soát** giúp việc lặp lại được thực hiện an toàn mà không cần người khác bấm nút. Một yêu cầu thay đổi đã qua test, nằm trong quyền và không phá contract có thể đi tiếp không cần cuộc họp phát hành hàng tuần.

## 18. Pipeline phát hành độc lập của một service

~~~mermaid
flowchart TD
    C["Commit thay đổi của Checkout"] --> U["Unit + static analysis + security scan"]
    U --> K["Contract + component tests"]
    K --> B["Build immutable artifact"]
    B --> S["Deploy staging/ephemeral"]
    S --> T["Targeted integration + smoke"]
    T --> R{"Guardrails pass?"}
    R -->|No| F["Block release"]
    R -->|Yes| CA["Canary to production"]
    CA --> M["Monitor SLI, logs, traces"]
    M --> G{"Healthy?"}
    G -->|Yes| E["Progressive rollout"]
    G -->|No| RB["Stop / rollback safely"]
~~~

**Điều kiện pipeline độc lập:**
1. Không phụ thuộc trạng thái chưa ổn định của một staging dùng chung.
2. Không yêu cầu build lại toàn bộ service khác.
3. Có contract test đủ để kiểm tra phiên bản lệch.
4. Có version/artifact digest bất biến.
5. Có smoke/canary và health signals đáng tin.
6. Có rollback/roll-forward được diễn tập.
7. Có người chịu trách nhiệm SLO và hậu quả thay đổi.
8. Có log audit, quyền và secret được quản lý.

“Pipeline xanh” không bảo đảm mọi khía cạnh sản xuất đều đúng; vì vậy canary và SLO guardrail là lớp bảo vệ cần thiết. Ngược lại, một pipeline độc lập có test hợp lý có thể an toàn hơn một release train lớn vì thay đổi nhỏ, blast radius thấp và dễ xác định regression.

## 19. Feature flag tách triển khai khỏi kích hoạt

**Deploy** đưa code đến runtime. **Release feature** mở hành vi mới cho người dùng. Tách hai hành động giúp các team không cần chờ nhau tại một thời điểm.

Ví dụ:
1. Backend triển khai endpoint mới nhưng giữ flag tắt.
2. Frontend triển khai code biết hiển thị trường mới nhưng flag tắt.
3. Contract giữa các phiên bản đã được kiểm tra.
4. Đội sản phẩm bật flag cho 1% traffic phù hợp.
5. Quan sát conversion, error, latency và feedback.
6. Mở rộng hoặc tắt flag nếu chỉ số xấu.

Feature flag không thay thế backward compatibility. Nếu một phiên bản mới ghi dữ liệu không đọc được bởi bản cũ, tắt flag có thể không đảo ngược dữ liệu đã ghi. Với event được phát hoặc giao dịch tài chính, cần đánh giá **side effect** trước khi xem flag như kill switch.

Quản lý vòng đời flag:
- Owner và mục đích.
- Quy tắc phân phối theo tenant/cohort có phân quyền.
- Mặc định khi dịch vụ flag lỗi.
- Thời hạn dự kiến loại bỏ flag.
- Metric cho từng cohort.
- Test cả trạng thái on/off tại các phiên bản cần hỗ trợ.

Flag quá nhiều, tồn tại mãi làm tăng số tổ hợp hành vi và nợ kỹ thuật. Nó là công cụ chuyển đổi, không phải phương án giữ mọi release logic vĩnh viễn.

## 20. Release train: khi nào cần, khi nào gây chi phí vô ích?

**Release train** là lịch phát hành theo đợt cố định, thường có người điều phối và tập thay đổi được gom lại. Nó có thể phù hợp trong trường hợp:
- Sản phẩm có ràng buộc pháp lý/quy trình kiểm định chặt.
- Firmware, desktop/mobile client cần phát hành qua kênh tập trung.
- Thay đổi lớn có tương tác nhiều vùng dữ liệu không thể chuyển độc lập trong giai đoạn hiện tại.
- Hệ thống legacy chưa có contract hay rollback cho phiên bản lệch.
- Có cửa sổ bảo trì bắt buộc vì phụ thuộc kỹ thuật thật.

Nhưng dùng release train như **mặc định cho mọi API bugfix nhỏ** có thể tạo:
- Batch thay đổi lớn, khó tìm nguyên nhân lỗi.
- Nhiều team chờ đến ngày chung dù đã xong.
- Áp lực test hồi quy toàn hệ thống.
- Rủi ro rollback dây chuyền khi nhiều artifact đổi cùng lúc.
- Khó cung cấp giá trị/khắc phục lỗi nhỏ kịp thời.

Không nhất thiết loại bỏ toàn bộ lịch phối hợp. Một chiến lược phù hợp là **phần lớn service deploy liên tục trong guardrail; chỉ các thay đổi cross-cutting thật sự được tổ chức như migration có timeline chung và người điều phối**.

### 20.1. Release window và thời điểm bật tính năng

Có thể tách:
- Deploy code sau khi test/canary đạt.
- Bật tính năng vào thời điểm sản phẩm cần.
- Thực hiện database cutover sau khi các consumer hoàn tất migration.
- Loại phiên bản cũ vào ngày được công bố.

Điều này tránh biến một ngày marketing launch thành một lần triển khai gấp hàng chục service cùng phút. Thay vào đó, các khả năng kỹ thuật đã được đưa lên, thử nghiệm và giữ ở trạng thái an toàn từ trước.

## 21. Coordination tax: tính chi phí chờ để ưu tiên cải tiến

Một thay đổi có thể cần 4 giờ kỹ thuật và 8 ngày lịch vì bốn lần chờ. Để nhìn rõ, phân tách:

~~~text
Lead time = Active work time + Waiting/queue time
            + Rework + Deployment/verification time
~~~

Ví dụ giả định:

| Giai đoạn | Làm việc | Chờ |
|---|---:|---:|
| Backend change | 2 giờ | 0 |
| Chờ DBA mở cột | 0,5 giờ | 2 ngày |
| Chờ partner API review | 1 giờ | 1 ngày |
| Chờ staging slot | 1 giờ | 2 ngày |
| Chờ release train | 0,5 giờ | 3 ngày |

Trong bảng, thời gian làm việc chỉ khoảng 5 giờ nhưng thời gian chờ tới 8 ngày. Đây là dữ liệu minh họa, không phải benchmark ngành. Mục tiêu cải tiến lớn nhất có thể là **loại bỏ các hàng đợi**, không phải ép engineer code nhanh hơn 10%.

### 21.1. Định nghĩa blocked time

Một team nên thống nhất:
- **Start:** khi công việc sẵn sàng thực hiện nhưng đang chờ thứ ngoài quyền kiểm soát.
- **End:** khi phụ thuộc được giải quyết và công việc có thể tiếp tục.
- **Blocker category:** API, data, infrastructure, permission, approval, test environment, release window.
- **Owner và SLA nội bộ:** ai xử lý yêu cầu, kênh escalation.
- **Có thể tránh trong lần sau không?** Nếu có, đề xuất capability hoặc thay đổi hợp đồng.

Không gán mọi phút đợi giữa hai trạng thái ticket là blocker; một số việc còn phụ thuộc ưu tiên sản phẩm hoặc công việc khác của chính team. Dữ liệu cần đủ sạch để tránh biến metric thành tranh cãi trách nhiệm.

## 22. DORA/flow metrics và điều cần diễn giải cẩn thận

Các chỉ số về năng lực delivery có thể giúp xem quy trình có giảm phụ thuộc hay không:

- **Lead time for changes:** từ mốc code/change được quy định đến production; định nghĩa cụ thể phải ổn định.
- **Deployment frequency:** số lần deploy thành công theo service/thời gian.
- **Change failure rate:** tỷ lệ thay đổi production gây suy giảm cần phục hồi, theo định nghĩa đã chọn.
- **Failed deployment recovery time:** thời gian phục hồi sau những deployment gây lỗi, theo quy tắc đo của tổ chức.
- **Flow efficiency:** tỷ lệ thời gian làm việc hữu ích trên tổng thời gian trôi qua của một item.
- **Blocked time:** thời gian bị chờ phụ thuộc, theo loại blocker.
- **Cross-team change ratio:** tỷ lệ thay đổi cần phối hợp nhiều team.
- **Coordinated release ratio:** tỷ lệ phát hành cần cùng phiên bản nhiều service.
- **Deployment independence:** tỷ lệ service release không cần release đồng thời service khác.

**Không xem deployment frequency cao là đích duy nhất.** Một nhóm tự động phát hành 20 lần/ngày nhưng gây 15 incident có thể chưa tốt hơn nhóm phát hành chậm nhưng an toàn. Kết hợp throughput và stability, gắn với SLO/error budget.

Không dùng các metric này để xếp hạng cá nhân và ép chia commit nhỏ giả tạo. Chúng hữu ích ở mức dòng công việc và năng lực hệ thống.

### 22.1. Flow efficiency minh họa

~~~text
Active work: 8 giờ
Waiting: 72 giờ
Total elapsed: 80 giờ

Flow efficiency = 8 / 80 = 10%
~~~

Con số 10% gợi ý cơ hội giảm thời gian chờ. Nó không tự chỉ ra ai phải chịu trách nhiệm hoặc phải xóa bước kiểm soát nào. Cần phân tích nguyên nhân chờ, rủi ro và mức độ lặp.

## 23. Ma trận ownership tránh tình huống "ai cũng tưởng người khác chịu"

Một service catalog nên có thông tin:

| Đối tượng | Owner | Người sử dụng | Kênh tương tác | Trách nhiệm vận hành |
|---|---|---|---|---|
| Checkout API | Checkout Team | Web, Mobile | OpenAPI/SDK, changelog | Checkout SLO, incidents |
| OrderCreated event | Checkout Team | Fulfillment, Analytics | Registry, contract fixtures | Schema version, publish reliability |
| Payment API | Payments Team | Checkout, Refund | API contract, support policy | Payment SLO và đối soát |
| DB Checkout | Checkout Team | Không cho query trực tiếp team khác | Data contract/read model | Migration, backup coordination |
| CI/CD platform | Platform Team | Các product team | Self-service, docs, support | Pipeline availability, guardrails |
| Security policy | Security Team | Các team | Policy-as-code và exception process | Chuẩn, audit và rủi ro |

Một sơ đồ **RACI** có thể hữu ích cho tác vụ cross-cutting, nhưng nếu mọi sửa nhỏ đều phải đi qua bốn tầng ký tên, bảng đó làm tăng handoff. Tách **quyết định trong phạm vi team** với **quyết định ảnh hưởng ranh giới/nguồn lực chung**.

Đặc biệt cần biết owner của **schema, deprecation, shared library, platform template, alert và dữ liệu**. Những tài sản này thường trở thành vùng “không ai sở hữu” hoặc bị một nhóm nắm quyền chờ.

## 24. Service catalog và documentation như interface tự phục vụ

Một team muốn dùng API của team khác không nên phải gửi tin nhắn chỉ để biết tên endpoint, môi trường và ví dụ request.

Service catalog có thể cung cấp:
- Tên service và capability nghiệp vụ.
- Owner, kênh hỗ trợ, on-call và escalation.
- OpenAPI/AsyncAPI/schema registry.
- SLO và hướng xử lý lỗi client.
- Authentication/authorization scopes.
- SDK/CLI/fixture ví dụ.
- Changelog, versioning/deprecation policy.
- Endpoint staging/test data và hướng dẫn chạy local.
- Dashboard, runbook và incident history có quyền phù hợp.

Tài liệu nên được cập nhật trong cùng quy trình code hoặc contract thay đổi, tránh một wiki đẹp nhưng lỗi thời. Việc cập nhật schema có thể tự động sinh tài liệu, nhưng phần semantic/compatibility vẫn cần người sở hữu.

**API có tài liệu tốt là một cách giảm handoff.** Consumer có thể tự tích hợp và test, chỉ cần trao đổi trực tiếp khi hợp đồng chưa đủ rõ hoặc yêu cầu vượt phạm vi được công bố.

## 25. Async communication giảm phụ thuộc thời điểm phản hồi

Có những nhu cầu không cần trả kết quả tức thời. Ví dụ OrderCreated phát sau khi đơn được ghi bền vững; Fulfillment và Analytics nhận event theo nhịp riêng, không cần Checkout gọi từng dịch vụ và chờ xác nhận trong request tạo đơn.

~~~mermaid
flowchart LR
    O["Checkout Service"] --> DB[("Orders DB")]
    O --> OB["Outbox / Event publication"]
    OB --> BK[("Broker")]
    BK --> F["Fulfillment consumer"]
    BK --> A["Analytics consumer"]
    BK --> N["Notification consumer"]
~~~

Lợi ích khi phù hợp:
- Producer không phải chờ mọi consumer chạy để hoàn tất giao dịch.
- Consumer có thể nâng cấp độc lập nếu message contract tương thích.
- Broker có thể giữ backlog khi một consumer tạm dừng.
- Thêm consumer mới không nhất thiết sửa producer.

Đánh đổi:
- Eventual consistency và chậm trễ xử lý.
- Retry, redelivery, ordering, idempotency và DLQ.
- Schema evolution/replay dữ liệu cũ.
- Phân quyền publish/consume và quản lý broker.
- Khả năng quan sát xuyên luồng và reconciliation.

**Không dùng event để che mọi dependency đồng bộ.** Nếu checkout cần xác nhận thanh toán trước khi cho phép giao hàng, hợp đồng nghiệp vụ vẫn yêu cầu điểm quyết định đáng tin, dù cách thực hiện có thể là workflow bất đồng bộ bền vững. Giảm call trực tiếp không được làm mất kiểm soát transaction và dữ liệu.

### 25.1. Outbox làm giảm phụ thuộc giữa DB commit và broker

Khi producer vừa ghi DB vừa gửi event mà không có cơ chế tin cậy, có thể xảy ra DB commit thành công nhưng event không phát. Transactional outbox lưu bản ghi event trong cùng transaction DB, sau đó publisher độc lập gửi ra broker với retry và idempotency.

Đây là cách để producer không phải yêu cầu tất cả downstream có mặt ngay thời điểm commit, nhưng consumer vẫn cần chịu duplicate và out-of-order theo hợp đồng. Một hệ thống có outbox vẫn cần quan sát backlog và xử lý event stuck.

## 26. API gateway/BFF không nên trở thành team phụ thuộc mới

Một BFF/API gateway có thể tổng hợp dữ liệu cho client và giảm N+1 call. Tuy nhiên, nếu **mọi thay đổi của product team đều phải gửi ticket cho Gateway Team sửa route hoặc DTO**, điểm nghẽn chỉ chuyển vị trí.

Hướng giải quyết:
- Team sở hữu API công bố contract trong registry.
- Routing/config dùng template có version và cơ chế review tự động.
- Có ranh giới rõ giữa policy toàn cục do Platform/Security sở hữu và các route trong phạm vi product team.
- BFF theo use case được một team sở hữu đầu-cuối, không phải một shared monolith không rõ owner.
- Chính sách API version, auth, rate limit và observability được chuẩn hóa.
- Thay đổi route rủi ro cao có review theo ngưỡng, không phải mọi route có cùng mức phê duyệt.

Tương tự, shared library phục vụ mọi team có thể tạo dependency cập nhật đồng loạt. Nếu một thay đổi library buộc 50 repo nâng version cùng ngày, hãy xem lại compatibility policy và mức cần thiết của chia sẻ code.

## 27. Shared library, shared database và thư viện "nội bộ dùng chung"

Chia sẻ thư viện có lợi khi nó chuẩn hóa chức năng thực sự ổn định như tracing, HTTP client policy, validation nền hoặc SDK contract. Nhưng thư viện chứa quy tắc nghiệp vụ thay đổi thường xuyên có thể gây lockstep.

Ví dụ:
- Các team đều phụ thuộc **common-domain-model**.
- Payment thêm một enum.
- Thư viện cập nhật, mọi service được yêu cầu nâng ngay.
- Một thay đổi nhỏ tạo hàng chục PR và cuộc họp phát hành.

Các phương án:
1. Chỉ chia sẻ **schema/contract công bố** hoặc generated SDK với versioning phù hợp.
2. Giữ logic domain trong bounded context sở hữu.
3. Cho phép các version library cùng tồn tại trong cửa sổ hỗ trợ.
4. Không buộc mọi consumer nâng nếu họ không cần tính năng mới.
5. Có compatibility tests cho API công khai của library.
6. Chuyển thay đổi semantic lớn sang migration có hợp đồng rõ.

**Database dùng chung** còn tạo coupling mạnh hơn: một nhóm đổi bảng có thể phá nhiều dịch vụ. Nếu không thể tách DB ngay, bắt đầu bằng ownership schema, view hoặc API façade có hợp đồng, phân quyền truy cập, inventory consumer và lộ trình phân tách theo rủi ro.

## 28. Tổ chức phiên bản client và môi trường ngoài tầm kiểm soát

Không phải mọi consumer đều là service nội bộ có thể deploy trong ngày. Mobile app, thiết bị tại cửa hàng, tích hợp đối tác và dữ liệu backup có thể giữ phiên bản cũ lâu.

Với API bên ngoài, cần chính sách:
- Những version nào đang hỗ trợ.
- Hạn deprecation và cách thông báo.
- Phương pháp đo usage theo version/client khi hợp pháp.
- Tương thích payload cũ và lỗi rõ ràng.
- Cách nâng SDK và tài liệu migration.
- Khi nào được chặn phiên bản không an toàn.
- Đối tác nào cần phối hợp theo lịch riêng.

Một team không thể tuyên bố "deploy độc lập" bằng cách tùy ý phá client bên ngoài. **Độc lập đến từ giữ hợp đồng**, không phải quyền thay đổi vô hạn.

Nếu một migration yêu cầu nhiều đối tác nâng version, nên mở cửa sổ hỗ trợ đủ dài, thử nghiệm trước, có adapter hoặc API version mới. Đồng bộ theo ngày chỉ nên là lựa chọn khi thực sự không thể hỗ trợ coexistence và mọi bên đã chấp nhận rủi ro.

## 29. Thay đổi phá vỡ hợp đồng: phối hợp có chủ đích thay vì hy vọng

Có những trường hợp compatibility không thể giữ:
- Đổi mô hình định danh khách hàng.
- Loại bỏ một trạng thái thanh toán cũ không còn được phép.
- Thay đổi định dạng dữ liệu do yêu cầu pháp lý.
- Cắt chuyển luồng giao dịch giữa hai hệ thống.
- Xóa một field có ý nghĩa bảo mật không thể tiếp tục hỗ trợ.

Với loại này, cần một kế hoạch phối hợp:

~~~text
Contract-breaking proposal
    |
    v
Impact inventory (consumers, clients, data, backups)
    |
    v
Owner + migration plan + support window
    |
    v
Dual support / adapter nếu khả thi
    |
    v
Consumer migration + metrics
    |
    v
Cutover có guardrails, rollback/roll-forward
    |
    v
Deprecation và dọn bản cũ
~~~

Công cụ có thể gồm change RFC/ADR, contract migration plan, stakeholder list và cổng phê duyệt rủi ro. Cần ghi **điều kiện cutover**, không chỉ lịch "ngày 15". Ví dụ: mọi consumer nội bộ đã nâng, partner xác nhận, traffic v1 dưới ngưỡng được duyệt và replay lịch sử đã thử.

Đừng dùng mục tiêu giảm handoff để bỏ qua thay đổi cần Security hoặc Data review. Tự động hóa những điều lặp lại, phối hợp những điều có rủi ro thực.

## 30. Mẫu RFC ngắn cho thay đổi cross-team

~~~markdown
# RFC: Bổ sung deliveryInstruction vào OrderCreated

## Owner
Checkout Team

## Consumer bị ảnh hưởng
Fulfillment, Notification, Analytics

## Hợp đồng hiện tại
OrderCreated v1, không có deliveryInstruction

## Hợp đồng đề xuất
Thêm field optional có ý nghĩa và default rõ

## Compatibility
- Reader mới đọc dữ liệu cũ trong retention
- Reader cũ xử lý message mới theo định dạng đã chọn
- Contract fixtures cho v1/v2

## Deployment plan
1. Cập nhật consumer/adapter có khả năng đọc mới
2. Deploy producer phát field mới khi phù hợp
3. Bật UI theo feature flag
4. Quan sát error, backlog, event schema usage

## Rollback
- Producer có thể lùi về version cũ
- Reader vẫn xử lý event mới còn tồn trên broker
- Không có side effect không thể đảo ngược

## Điều kiện kết thúc
- Không còn consumer nội bộ yêu cầu version cũ
- Replay và data consistency đạt yêu cầu
- Owner các contract xác nhận
~~~

Đây là mẫu nội dung, không phải yêu cầu mọi thay đổi phải viết RFC. Với thay đổi không phá hợp đồng, một PR và test tự động thường đủ. RFC hữu ích khi có **quyết định liên team, thay đổi semantic, điều kiện cutover hoặc rủi ro khó đảo ngược**.

## 31. Mẫu quyết định kỹ thuật: có cần release đồng bộ?

Một cách đặt câu hỏi:

~~~text
Thay đổi chỉ nằm trong implementation nội bộ?
   |
   +-- Có --> Deploy riêng với tests và SLO guardrail.
   |
   +-- Không
        |
        +-- API/schema/event có giữ compatibility window?
        |       |
        |       +-- Có --> Expand rồi migrate theo nhịp từng team.
        |       |
        |       +-- Không --> Có thể thêm adapter/version mới?
        |                     |
        |                     +-- Có --> Dual support + gradual cutover.
        |                     |
        |                     +-- Không --> Phối hợp migration theo RFC,
        |                                    cutover và kế hoạch phục hồi.
        |
        +-- Thay đổi DB có giữ bản ứng dụng cũ chạy được?
                |
                +-- Có --> Migration online, deploy riêng.
                |
                +-- Không --> Tách giai đoạn hoặc lập maintenance plan.
~~~

Đây không phải thuật toán tuyệt đối. Một thay đổi nội bộ vẫn có thể rủi ro cao nếu liên quan bảo mật, dữ liệu hoặc traffic lớn. Một thay đổi hợp đồng additive vẫn có thể gây lỗi consumer nghiêm ngặt. Quyết định cuối cùng dựa trên **bằng chứng test và threat/risk analysis**, không chỉ nhãn “compatible”.

## 32. Kịch bản điển hình: tách một release train trong thương mại điện tử

**Bối cảnh:** Tổ chức có Catalog, Checkout, Payments, Fulfillment. Mỗi thứ Sáu, tất cả nhóm đóng code, triển khai đồng loạt và đội QA chạy E2E trên staging chung. Bugfix vào thứ Hai phải chờ thứ Sáu sau.

**Dấu hiệu đo được:**
- Ticket chờ deploy chiếm nhiều ngày.
- Hầu hết thay đổi nhỏ không cần sửa service khác nhưng vẫn chung lịch.
- E2E thường fail do dữ liệu staging bị ghi đè.
- Khó xác định commit gây regression do nhiều version đổi cùng lúc.
- Mọi team đều cần DevOps mở change ticket.

**Lộ trình chuyển đổi:**

**Giai đoạn 1 — Lập bản đồ**
- Inventory service owner, API, event, DB và tập client.
- Đo change-coupling, blocked time, lead time và incident theo deploy.
- Phân loại service có thể deploy riêng ngay và service còn dependency dữ liệu/contract.

**Giai đoạn 2 — Tạo golden path**
- Mỗi service có pipeline build/test/deploy, artifact immutable.
- Platform tạo template canary, rollback, secret và observability.
- Cấp quyền theo service và policy-as-code thay manual deploy.

**Giai đoạn 3 — Tách hợp đồng**
- API/event contract có version và automated verification.
- Áp expand/contract cho schema DB.
- Xử lý shared library buộc nâng đồng loạt.
- Giảm dependency vào staging bằng component/contract tests.

**Giai đoạn 4 — Canary từng service**
- Bắt đầu một dịch vụ ít rủi ro, ví dụ Catalog read API.
- Đo p95, error, deployment success, recovery và customer impact.
- Cho phép phát hành ngoài release train khi guardrail đạt.
- Tăng dần nhóm service, giữ lịch đặc biệt cho migration lớn.

**Giai đoạn 5 — Rà soát**
- So lead time và blocked time trước/sau.
- Kiểm tra change failure rate và SLO không xấu.
- Đo số phát hành còn cần đồng bộ, nguyên nhân và cách giảm tiếp.
- Đánh giá tải on-call, developer experience và platform reliability.

**Điểm cần tránh:** tổ chức không nên lập một đêm “big bang” để chuyển toàn bộ service sang continuous delivery. Hãy thay đổi theo nhóm rủi ro và bảo đảm mỗi bước có khả năng phục hồi.

## 33. Tình huống: đổi schema thanh toán cần nhiều đội

Một hệ thống Payment đang dùng **paymentState=PENDING/PAID/FAILED**, muốn chuyển sang trạng thái chi tiết hơn như AUTHORIZED và CAPTURED. Đây là thay đổi semantic quan trọng.

Nếu Checkout chỉ hiểu PAID, việc producer phát CAPTURED ngay có thể phá logic hoàn tất đơn.

Kế hoạch:
1. Payments công bố trạng thái mới, ý nghĩa và mapping sang trạng thái cũ.
2. Consumer contract ghi rõ những trạng thái consumer hiện hỗ trợ.
3. Checkout thêm nhánh xử lý trạng thái mới, có default an toàn cho unknown.
4. Payments có thể giữ contract v1 hoặc xuất event v2 trong giai đoạn chuyển đổi.
5. Từng consumer nâng và xác minh theo chính sách.
6. Canary các version và theo dõi giao dịch đã xác nhận nhưng đơn chưa hoàn thành.
7. Chuyển dần producer sang event mới khi consumer sẵn sàng.
8. Bỏ v1 sau khi đáp ứng retention, replay và mọi client trong phạm vi.

Không nhất thiết nâng tất cả vào cùng một phút nếu có cửa sổ hợp đồng; nhưng vẫn cần **quyết định nghiệp vụ chung** về ý nghĩa trạng thái và tính đúng giao dịch.

## 34. Tình huống: Platform team là cổ chai của mọi deployment

**Hiện trạng:** 20 product team gửi ticket để cập nhật biến môi trường, tăng replica và deploy image. Hai platform engineer trực tiếp làm từng yêu cầu, đôi khi phải thức đêm.

**Vấn đề:** Platform team nắm thao tác chứ chưa cung cấp capability. Người dùng phải xếp hàng; lỗi dễ xảy ra vì thao tác thủ công lặp lại.

**Cải tiến:**
- Tạo service template và GitOps repo cho mỗi team theo quyền.
- Tích hợp secret reference và environment promotion.
- Cấp quyền CI/CD theo namespace/service, không dùng admin chung.
- ResourceQuota, network policy, image scan, approval theo rủi ro áp tự động.
- Canary và rollback theo phiên bản, có runbook và audit.
- Self-service dashboard cho triển khai, incident và chi phí.
- Platform nhận yêu cầu như product backlog: quan sát adoption, latency và support ticket loại nào còn lặp.

**Thước đo:** median thời gian từ yêu cầu deploy tới deployed, số ticket thủ công/100 deploy, tỷ lệ triển khai tự phục vụ, tỉ lệ rollback thành công và số incident do policy/config. Nếu chỉ giảm ticket nhưng mọi nhóm phải copy-paste YAML khó hiểu, developer experience có thể vẫn tệ.

## 35. Tình huống: "Microservices" nhưng mọi nhóm cùng sửa một database

**Hiện trạng:** Checkout, Payment và Fulfillment cùng đọc/ghi bảng orders. DB team thường phải duyệt mọi migration; schema đổi làm cả ba đội phải test và deploy cùng lúc.

**Rủi ro:**
- Một thay đổi DB có blast radius rộng.
- Service không có ownership dữ liệu.
- Các nhóm không biết ai được phép sửa cột.
- Migration phá client cũ, rollback phức tạp.
- Quyền DB rộng làm tăng rủi ro bảo mật.

**Hướng chuyển đổi:**
1. Gán owner cho bảng/cột và xác định đường đọc/ghi đang tồn tại.
2. Giới hạn thay đổi mới không mở rộng truy cập trực tiếp.
3. Cung cấp API/read model cho dữ liệu cần dùng xuyên nhóm.
4. Tách quyền theo schema và di chuyển từng luồng truy vấn.
5. Áp expand/contract migration với backward-compatible readers.
6. Chạy reconciliation, đo truy vấn legacy còn tồn tại.
7. Cắt quyền đọc bảng trực tiếp sau khi consumer đã chuyển và có bằng chứng.
8. Chỉ tách hạ tầng DB vật lý nếu cần theo rủi ro/tải/chi phí; ranh giới ownership có thể cải thiện trước.

Đừng đòi tách toàn bộ database trong một sprint. Đây là migration dữ liệu có rủi ro, cần đo và tiến hành từng bước.

## 36. Tình huống: Mobile app và backend không thể deploy đồng bộ

**Bối cảnh:** Backend có thể phát hành vài lần mỗi ngày, mobile app mất thời gian qua store và người dùng không cập nhật ngay. Nếu API backend chỉ hỗ trợ version mới sau deploy, app cũ có thể ngừng hoạt động.

**Thiết kế cần có:**
- API version hoặc hợp đồng tương thích với các client còn được hỗ trợ.
- Trường mới optional/default phù hợp.
- Feature negotiation hoặc capability flags khi cần.
- Deprecated endpoints có thời gian hỗ trợ công bố.
- Telemetry theo client version để hiểu thực tế.
- Không yêu cầu app gửi field mới cho đến khi tỷ lệ nâng phiên bản đạt điều kiện.
- Đường lỗi rõ ràng và thông báo nâng cấp khi version không còn an toàn.

Đây là ví dụ trực quan rằng **independent release không có nghĩa biến tất cả thành service deploy cùng lúc**. Nó có nghĩa mỗi phía có thể tiến hóa khi hợp đồng và cửa sổ hỗ trợ được quản trị tốt.

## 37. Sự cố phát hành: rollback phải xét dữ liệu và message đã lưu

Một tổ chức có thể tối ưu deployment pipeline còn 2 phút nhưng mất 3 giờ phục hồi vì thay đổi DB hoặc event schema không tương thích.

Trước mỗi rollout có ảnh hưởng hợp đồng, cần kiểm tra:
- Bản cũ đọc được dữ liệu mới không?
- Bản mới đọc được dữ liệu lịch sử không?
- Đã có event mới trong broker chưa?
- Khi rollback producer, consumer sẽ xử lý event tồn đọng thế nào?
- Có side effect không thể hoàn tác không?
- Có script migration/reconciliation được thử không?
- Feature flag tắt có đủ ngăn tác động mới không?
- Owner nào quyết định roll-forward thay vì rollback?

Nếu đường quay lại không an toàn, **roll-forward có kiểm soát** hoặc adapter có thể là phương án đúng. Tuyên bố "mỗi team tự rollback" là thiếu trách nhiệm nếu nó làm hỏng dữ liệu của các nhóm khác.

## 38. Thiết kế kênh giao tiếp giữa team theo mức rủi ro

Một ma trận:

| Loại thay đổi | Giao tiếp tối thiểu | Bằng chứng cần |
|---|---|---|
| Implementation nội bộ, giữ contract | PR/team review, pipeline | Tests, SLO guardrails |
| Thêm field optional tương thích | Changelog tự động, contract registry | Compatibility + fixtures |
| Thêm endpoint mới | API docs và owner notification | Auth, rate limit, integration |
| Thay đổi tải lớn lên dependency | Capacity review hoặc giao tiếp chủ đích | Load test, quota, SLO |
| Thay đổi semantic tài chính | RFC/ADR + consumer owners | Business rules, migration, rollback |
| Đổi database schema không tương thích | Migration plan và owner dữ liệu | Expand/contract, replay |
| Thay đổi quyền mạng/secret quan trọng | Security/platform review theo chính sách | Threat model, access validation |
| Thay đổi dữ liệu pháp lý | Legal/compliance và owner | Policy, audit, retention |
| Cắt chuyển hệ thống lớn | Điều phối chính thức với điều kiện cutover | End-to-end drill, recovery plan |

Một quá trình **có thể dự đoán** giảm phụ thuộc hơn một hệ thống "luôn hỏi trưởng nhóm xem có được không". Với những thay đổi phổ biến, rule cần được tự động hóa; với thay đổi rủi ro cao, cần người ra quyết định được xác định rõ.

## 39. Chống sự phụ thuộc vào một chuyên gia

Handoff có thể nằm trong đầu một người: chỉ một senior biết cách release Payment hoặc sửa Kafka consumer lag. Khi người đó nghỉ phép, cả team ngừng.

Biện pháp:
- Pairing và rotating ownership cho tác vụ quan trọng.
- Runbook đầy đủ, được thử trong game day.
- Service catalog có on-call và escalation.
- Traces/metrics/version markers đủ để người trực mới điều tra.
- Infrastructure và policy được quản lý như code.
- Thao tác rollback được diễn tập bởi người không phải tác giả ban đầu.
- Review ADR để lưu lý do kiến trúc, không chỉ lệnh thao tác.
- Hướng dẫn onboarding theo tác vụ thực, không chỉ tài liệu tổng quan.

**Không phải mọi kiến thức đều phải phân phối đều tới mọi người.** Team vẫn có chuyên gia, nhưng một thao tác sống còn không nên chỉ khả thi khi người đó trực tuyến.

## 40. Kiểm tra thay đổi bằng ma trận phiên bản

Với hai service Producer và Consumer, đừng chỉ test P2 + C2. Nếu muốn deploy khác lịch, cần tối thiểu:

~~~text
P1 -> C1    existing
P1 -> C2    consumer-upgrade-first
P2 -> C1    producer-upgrade-first
P2 -> C2    target-state
P0 -> C2    replay if historical data still exists
~~~

Một suite contract test tốt:
- Chạy schema resolution/serializer thực.
- Test required/optional/default và unknown enum.
- Kiểm tra semantic, đơn vị tiền, idempotency và thời điểm phát event.
- Kiểm tra producer ghi event sau transaction đáng tin.
- Test consumer lỗi/retry/DLQ và replay.
- Có fixture version cũ được tạo bằng writer version cũ.
- Kiểm tra both success and expected rejection.

**Đừng suy ra full compatibility** chỉ từ P1 → C2 pass. Nếu rollout hoặc rollback có khả năng gặp P2 → C1, phải test hướng đó hoặc thiết kế trình tự triển khai để tổ hợp ấy không xuất hiện.

## 41. Bài kiểm tra phát hành độc lập trong thực tế

Một PoC nên chọn một feature vừa đủ đại diện, chẳng hạn thêm trường tùy chọn trong OrderSummary, và kiểm chứng:

1. Checkout tạo PR và chạy tests không cần đặt lịch staging với team khác.
2. Contract fixtures xác minh client/consumer đã được hỗ trợ.
3. Pipeline build artifact và scan an toàn.
4. Deployment chạy bằng danh tính Checkout, không nhờ platform gõ lệnh.
5. Canary chuyển một phần traffic, metric theo version.
6. Team có thể dừng rollout và rollback trong giới hạn an toàn.
7. Consumer vẫn chạy bản cũ mà không hỏng.
8. Không có kết nối DB hoặc quyền secret ngoài phạm vi.
9. Dữ liệu lịch sử và event replay vẫn xử lý.
10. Incident log/metrics đủ xác minh hiệu quả.

Nếu một bước bắt buộc gửi ticket hoặc chờ cuộc họp, ghi **blocker reason và waiting time**. Mục tiêu PoC không chỉ chứng minh pipeline chạy mà chứng minh **quy trình end-to-end không cần lịch phát hành đồng bộ cho loại thay đổi ấy**.

## 42. Đo trước và sau chuyển đổi

Một bộ chỉ số:

| Metric | Trước | Sau (ví dụ giả định) | Điều cần xác minh |
|---|---:|---:|---|
| Median lead time | 8 ngày | 2 ngày | Cùng loại thay đổi, không thay định nghĩa |
| Median blocked time | 5 ngày | 0,5 ngày | Handoff nào đã biến mất? |
| Deploys cần lịch chung | 70% | 20% | Có thống kê theo service và rủi ro? |
| Manual platform tickets/100 deploy | 80 | 12 | Self-service có hoạt động thật? |
| Change failure rate | 8% | 7% | Không đánh đổi reliability để tăng tốc |
| Restore time sau deploy lỗi | 90 phút | 25 phút | Rollback và schema có an toàn? |
| Contract break incidents/quý | 6 | 1 | Có bỏ sót incident không? |
| Critical journey SLO | Đạt | Đạt | Error budget không xấu đi |

**Các số là minh họa, không phải benchmark hay cam kết.** Khi đọc chúng:
- So sánh cùng nhóm service, loại thay đổi và khoảng thời gian.
- Kiểm tra sample size và severity.
- Tách sự cố do code, platform, dependency hay dữ liệu.
- Xem kinh nghiệm người dùng cuối, không chỉ năng suất.
- Đừng kết luận nguyên nhân chỉ từ tương quan sau một thay đổi lớn.

Có thể một thời kỳ tăng deployment frequency nhưng incident count cũng tăng vì phát hiện tốt hơn các lỗi nhỏ trước đây không được ghi. Khi đó cần đọc **user impact và SLO** để đánh giá đầy đủ.

## 43. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Hướng giải quyết |
|---|---|---|
| Chia team theo Frontend/Backend/DB/QA cho mọi tính năng | Nhiều bàn giao tuần tự | Team theo dòng giá trị và chuyên môn đa chức năng phù hợp |
| Chia mỗi repository thành một team | Tăng giao tiếp không cần | Đặt ranh giới theo bounded context và cognitive load |
| Mỗi service deploy riêng nhưng dùng DB chung | Schema đổi phá nhiều service | Data ownership, API/read model, expand/contract |
| Tất cả cần release train dù thay đổi additive | Lead time dài, batch release lớn | Độc lập deploy trong guardrail |
| Bỏ review mọi thứ để giảm thời gian | Tăng rủi ro bảo mật và dữ liệu | Phân loại rủi ro, tự động hóa kiểm tra thường ngày |
| Platform team bấm mọi nút deploy | Queue trung tâm | Golden path và self-service IAM |
| Chỉ test trạng thái P2 + C2 | Version skew gây lỗi | Test ma trận writer/reader |
| Schema registry pass nhưng semantic đổi | Tính sai tiền/trạng thái | Contract test nghiệp vụ |
| Tạo BFF chung do một team sửa hộ mọi nhóm | Chuyển bottleneck | Ownership theo use case, self-service route |
| Chia sẻ common-domain-model thay đổi liên tục | Tất cả nâng library cùng lúc | Chia sẻ contract ổn định, versioning |
| Thêm event rồi coi mọi dependency biến mất | Mất event hoặc dữ liệu stale | Outbox, idempotency, replay, monitoring |
| Mọi PR chạy E2E toàn hệ thống ở staging chung | Flaky test, chờ slot | Contract/component tests, môi trường cách ly |
| Có feature flag thì khỏi cần compatibility | Dữ liệu/message mới vẫn tồn tại | Expand/contract, rollback plan |
| Đo deployment frequency duy nhất | Khuyến khích release thiếu kiểm soát | Lead time + stability + SLO |
| Ép mỗi team tự quản toàn bộ Kubernetes | Cognitive load quá cao | Platform capabilities và paved road |
| Làm RFC cho mọi sửa typo | Approval trở thành queue | Quy trình tương xứng rủi ro |
| Không có owner rõ cho event/schema | Breaking change bất ngờ | Service catalog và changelog |
| Bỏ client/partner cũ khỏi inventory | Phá ứng dụng ngoài tầm deploy | Support policy, usage telemetry |
| Tuyên bố rollout độc lập nhưng rollback không an toàn | Sự cố kéo dài | Migration/roll-forward/adapter plan |
| Dùng một senior làm cổng tri thức | Blocker khi người đó vắng | Runbook, pairing, game day |

## 44. Bài tập thực hành

**Bài A — bản đồ phụ thuộc:** Một thay đổi Checkout phải qua DBA, Payment, QA chung và DevOps. Vẽ dependency graph, phân loại từng cạnh là data/API, test environment, quyền hoặc lịch phát hành. Đề xuất một cải tiến kỹ thuật và một cải tiến tổ chức cho mỗi cạnh.

**Bài B — thay đổi schema:** Producer v2 thêm deliveryInstruction vào OrderCreated. Consumer v1/v2 tồn tại cùng lúc, broker giữ sự kiện 30 ngày. Hãy thiết kế schema, ma trận compatibility, fixture và thứ tự rollout để hai team không cần deploy cùng phút.

**Bài C — database migration:** Một cột amount được đổi đơn vị tiền. Hãy lập kế hoạch expand → migrate → contract, xác định thời điểm có thể xóa field cũ, kiểm tra reader cũ và đường rollback khi đã có dữ liệu mới.

**Bài D — platform self-service:** 15 product team phải nhờ 2 DevOps để deploy mỗi ngày. Viết danh sách capability nên tự phục vụ, policy/guardrail phải giữ, quyền CI/CD tối thiểu và metric đo queue giảm.

**Bài E — shared library:** 20 repo phụ thuộc chung một JAR domain. Một enum mới làm tất cả phải nâng. Đề xuất cách tách hợp đồng, versioning và các test giảm lockstep.

**Bài F — thay đổi rủi ro cao:** Payments muốn bỏ trạng thái PENDING vì yêu cầu pháp lý. Xác định những phần cần RFC và phối hợp, phần nào vẫn có thể deploy độc lập, kế hoạch cutover và rollback/roll-forward.

**Bài G — release train:** Team có 10 thay đổi nhỏ mỗi tuần, chỉ 1 thay đổi thật sự cần cắt chuyển dữ liệu chung. Thiết kế quy tắc cho 9 thay đổi còn lại tự deploy, nhưng vẫn bảo vệ SLO và quyền.

**Bài H — mobile client:** Backend triển khai nhanh, mobile app cũ không thể update tức thì. Thiết kế support window, API version, telemetry và kế hoạch deprecation không phá người dùng.

**Bài I — metric:** Lead time trung bình 8 ngày, active time 12 giờ, còn lại chủ yếu chờ staging, DBA, release manager. Hãy tính flow efficiency theo một quy ước giờ rõ, rồi đề xuất dashboard blocked time, deployment independence và change failure rate.

**Bài J — ownership:** Một domain có 12 microservice thuộc 4 team, mọi feature chạm 6 service. Hãy xem bounded contexts, cognitive load và change coupling; có cần gộp service/team hay thiết kế contract ổn định hơn?

**Bài K — rollback:** Producer v2 phát message mới, consumer mới bị lỗi nên team định rollback cả hai. Giải thích vì sao có thể phá hàng đợi, và thiết kế đường giữ reader/adapter tương thích.

**Bài L — test isolation:** Mỗi PR chờ staging 2 ngày, E2E hay fail do team khác thay dữ liệu. Đề xuất test pyramid mới, ephemeral environment theo phạm vi và những E2E vẫn nên giữ.

## 45. Checklist áp dụng cho một service mới

1. **Nêu capability nghiệp vụ** và owner đầu-cuối.
2. **Chọn ranh giới team/service** dựa trên bounded context, không theo repository.
3. **Ghi API/event/data contract** với owner, semantic và support policy.
4. **Kiểm tra version skew** giữa các client/consumer còn hỗ trợ.
5. **Tách database ownership** và thiết kế migration expand/contract.
6. **Có pipeline tự phục vụ** từ build đến canary trong quyền tối thiểu.
7. **Test unit/component/contract** chạy không cần lịch toàn hệ thống.
8. **Có health, metrics, traces và SLO** theo service và version.
9. **Có rollback/roll-forward plan** cho code, data, message và config.
10. **Có feature flag** nếu cần tách deploy khỏi bật tính năng.
11. **Có service catalog** và tài liệu tự phục vụ, changelog.
12. **Có quy trình RFC ngắn** cho breaking changes và thay đổi rủi ro cao.
13. **Đo waiting time, blocked time và handoff** theo loại phụ thuộc.
14. **Đo reliability** cùng tốc độ phát hành: change failure, restore time, SLO.
15. **Diễn tập sự cố** khi một team/nhà cung cấp không sẵn sàng.
16. **Rà soát shared libraries và staging** để tránh điểm nghẽn ẩn.
17. **Bảo vệ quyền và dữ liệu** khi cho team tự triển khai.
18. **Kiểm tra khách hàng bên ngoài và mobile clients** trước deprecation.
19. **Dọn compatibility layer** khi cửa sổ hỗ trợ đã hết và có bằng chứng.
20. **Xem lại ranh giới** khi số thay đổi xuyên team tăng trở lại.

## 46. Ghi nhớ

- **Ít handoff hơn không đồng nghĩa ít cộng tác hơn.** Hãy giảm hàng đợi và phụ thuộc đồng bộ lặp lại; vẫn hợp tác khi có rủi ro hoặc quyết định xuyên domain.
- **End-to-end ownership** gắn một team với capability, contract, chất lượng, deploy và vận hành.
- **Independent deployability** đòi hỏi pipeline riêng **và** tương thích API/event/database khi nhiều phiên bản cùng tồn tại.
- **Expand → migrate → contract** là kỹ thuật nền tảng giúp thay đổi mà không cần mọi team lên cùng phút.
- **Contract tests, schema registry, service catalog và tài liệu tốt** biến nhiều cuộc hỏi đáp thủ công thành giao diện có thể tự phục vụ.
- **Platform as a product** giảm ticket DevOps bằng golden path, quyền tối thiểu và guardrail tự động.
- **Feature flags** giúp tách code deployment khỏi thời điểm kích hoạt tính năng, nhưng không đảo ngược dữ liệu hay event đã phát.
- **Release train** nên dành cho những thay đổi thực sự cần phối hợp, không mặc định cho mọi bugfix nhỏ.
- **Shared database, shared domain library và staging chung** thường là nguồn lockstep ẩn sau các repository độc lập.
- **Đo cả lead time, blocked time, deployment independence, change failure và SLO**, không đánh giá năng lực chỉ bằng số lần deploy.
- **Team boundaries phải cân bằng flow và cognitive load**; ép mọi team tự quản mọi hạ tầng là một hình thức phụ thuộc vào kiến thức hiếm khác.
- **Rollback và dữ liệu lịch sử** là một phần của hợp đồng phát hành; tự do deploy không có nghĩa tự do phá consumer.

Một tổ chức xây microservices hiệu quả không cần mọi nhóm chạy nhanh theo cùng một nhịp. Nó cần **mỗi nhóm có khả năng tiến hóa và phát hành trách nhiệm của mình trong ranh giới hợp đồng đã được bảo vệ**, biết khi nào cần phối hợp và có bằng chứng để khôi phục nếu thay đổi gây hại. Khi giảm được phụ thuộc bàn giao và lịch phát hành đồng bộ mà vẫn giữ độ tin cậy, kiến trúc dịch vụ và tổ chức nhóm mới thực sự hỗ trợ lẫn nhau.
