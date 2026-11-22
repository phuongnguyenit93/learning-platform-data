# Liên hệ giữa cấu trúc giao tiếp của tổ chức và kiến trúc Microservices

Kiến trúc phần mềm không chỉ hình thành từ framework, cơ sở dữ liệu, giao thức hoặc kỹ thuật triển khai. Nó còn chịu ảnh hưởng sâu sắc bởi **cách con người phối hợp để thiết kế, xây dựng, kiểm thử, phát hành và vận hành hệ thống**. Nếu một thay đổi nhỏ luôn phải đi qua năm nhóm với năm hàng đợi phê duyệt, code và quy trình release thường xuất hiện các ranh giới và phụ thuộc phản ánh mạng lưới phối hợp đó. Ngược lại, nếu một nhóm sở hữu trọn một luồng giá trị, họ có khả năng tạo ra ranh giới dịch vụ phù hợp hơn và tự triển khai trong phạm vi hợp đồng đã cam kết.

Mối liên hệ này thường được nói đến qua **Conway's Law**: tổ chức thiết kế một hệ thống có xu hướng tạo ra thiết kế phản ánh cấu trúc giao tiếp của chính tổ chức đó. Đây là một quan sát quan trọng về hệ thống **xã hội–kỹ thuật (sociotechnical systems)**, không phải một quy luật cứng khẳng định cứ đổi sơ đồ tổ chức là kiến trúc tự động đổi.

Trong Microservices, hiểu Conway's Law giúp trả lời: nên chia nhóm theo lớp kỹ thuật hay năng lực nghiệp vụ? Ai sở hữu contract và dữ liệu? Vì sao đã tách thành nhiều service mà vẫn không deploy độc lập được? Cần thay đổi API, team ownership, platform hay cả ba? Làm sao giảm phối hợp bắt buộc nhưng vẫn giữ bảo mật và chất lượng vận hành?

Bài học thuộc nhóm **Tổ chức nhóm** trong chủ đề **Software Design, Architecture, System Architecture và Microservices**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích Conway's Law, bối cảnh và giới hạn của cách diễn giải.
- Vẽ đồ thị giao tiếp tổ chức và đồ thị phụ thuộc kỹ thuật của một hệ thống.
- Nhận ra ranh giới tổ chức nào gây waiting time, coupled releases hoặc shared ownership.
- Phân biệt domain boundary, module boundary, deployment boundary và team boundary.
- So sánh team chia theo chức năng kỹ thuật với team theo luồng giá trị nghiệp vụ.
- Hiểu cách **Inverse Conway Maneuver** tác động có chủ đích đến kiến trúc.
- Phân biệt bốn loại team và ba chế độ tương tác trong Team Topologies.
- Sử dụng bounded context, contract tests, API ownership và platform self-service để giảm coordination cost.
- Tránh distributed monolith, shared database không có owner và microservice sprawl.
- Lập kế hoạch chuyển giao ownership, đo lead time, reliability và cognitive load sau khi thay đổi tổ chức.

## 2. Conway's Law là gì?

Melvin Conway nêu quan sát nổi tiếng năm 1968 rằng hệ thống được thiết kế bởi một tổ chức có xu hướng phản ánh cấu trúc giao tiếp của tổ chức ấy. Có thể diễn giải thực tế:

> Những phần code có người thường xuyên làm việc cùng nhau có xu hướng có quan hệ chặt; những phần code ở ranh giới nhiều nhóm thường cần những interface và quy trình phối hợp tương ứng.

Một tổ chức có ba nhóm gần như độc lập có thể tạo ra ba module và các interface giữa chúng:

~~~text
Tổ chức:

Team A <----> Team B <----> Team C
   |             |             |
   v             v             v
Module A <--> Module B <--> Module C
~~~

Đây chỉ là hình ảnh giải thích **xu hướng**. Kiến trúc thật còn phụ thuộc domain, hệ thống legacy, công nghệ, chi phí, quy định và năng lực của từng nhóm.

### 2.1. Tại sao giao tiếp tác động đến kiến trúc?

Khi một nhóm làm việc trong một phạm vi trách nhiệm:

1. Các quyết định nội bộ được thống nhất nhanh hơn vì ít ranh giới phối hợp.
2. Những abstraction và convention nội bộ hình thành qua việc làm việc thường xuyên.
3. Thay đổi xuyên nhóm phải được trao đổi qua ticket, API contract, PR review hoặc phê duyệt.
4. Các giao diện ở ranh giới nhóm trở thành điểm tích hợp hệ thống.
5. Những phần ít cần trao đổi có thể được triển khai và tiến hóa độc lập hơn.

Nếu ranh giới nhóm phù hợp domain, kết quả có thể là những module/service có ownership rõ. Nếu một nghiệp vụ thường xuyên thay đổi bị chia ngang qua nhiều nhóm, code thường có coupled changes, shared schemas và đường release phức tạp.

### 2.2. Những cách hiểu sai

Conway's Law **không** có nghĩa:

- Mỗi team bắt buộc tương ứng một Microservice.
- Một service chỉ được một team chạm vào code.
- Đổi tên phòng ban sẽ tự sửa được technical debt.
- Nhiều nhóm nhỏ luôn tốt hơn một nhóm lớn.
- Một nhóm phải sở hữu duy nhất một bounded context.
- Không được có communication xuyên nhóm.
- Microservices luôn tốt hơn modular monolith.

Nó là lăng kính để tìm **chi phí giao tiếp không cần thiết** và thiết kế lại ranh giới phù hợp, không phải lý do để phân tách vô hạn.

## 3. Hai đồ thị phải được nhìn cùng nhau

### 3.1. Đồ thị giao tiếp tổ chức

Mỗi nút đại diện một team; mỗi cạnh là quan hệ phối hợp:

~~~text
                  Product
                     |
                     v
Frontend Team <--> Backend Team <--> Database Team
                         |
                         +----> QA Team
                         |
                         +----> SRE / Platform
                         |
                         +----> Security
~~~

Cạnh có thể là quyết định API, bàn giao kiểm thử, chờ migration, cấp quyền, phê duyệt release, xử lý incident hoặc tư vấn domain.

Không phải mọi giao tiếp đều xấu. **Collaboration để khám phá vấn đề mới** tạo giá trị; **phối hợp bắt buộc lặp đi lặp lại để làm việc thường ngày** có thể là bottleneck.

### 3.2. Đồ thị phụ thuộc kỹ thuật

Đây là đồ thị giữa service, module, database, event và deployment:

~~~text
Web/Mobile
    |
    v
Order Service ---------> Payment Service
    |                         |
    v                         v
Inventory Service        Payment DB
    |
    v
Inventory DB

Order Service ----> Broker ----> Notification Service
~~~

Các cạnh là HTTP/gRPC calls, event, cùng schema hoặc release dependency. Đồ thị cho thấy lỗi có thể lan qua đâu và một thay đổi contract có thể ảnh hưởng tới những thành phần nào.

### 3.3. Cách đối chiếu

Đặt các câu hỏi:

- Thay một quy tắc checkout cần bao nhiêu nhóm quyết định?
- Service A và B có phải phát hành cùng ngày không?
- Team có thể tự chạy test, deploy và rollback phần mình sở hữu không?
- Một database đang do bao nhiêu team cùng sửa?
- Có những lần gọi RPC chỉ để lấy một field vì dữ liệu bị chia theo nhóm chứ không theo domain?
- Một incident phải được chuyển tay bao nhiêu lần trước khi tìm được owner?
- Một nhóm có phải phê duyệt tất cả thay đổi mặc dù không liên quan domain?
- API/event boundary có trùng với nơi cần hợp tác giữa các domain thực sự không?

Không cần ép hai đồ thị trùng hoàn toàn. Mục tiêu là đảm bảo **những thứ cần thay cùng nhau có ownership/contract hợp lý**, còn những thứ cần tiến hóa riêng có đường giao tiếp ổn định.

## 4. Ví dụ tổ chức theo chức năng kỹ thuật

Một công ty thương mại điện tử tổ chức:

- Frontend Team phát triển UI.
- Backend Team xây dựng API và logic.
- DBA Team kiểm soát schema và migration.
- QA Team thực hiện kiểm thử tích hợp.
- Operations Team chuẩn bị pipeline và deploy.

Yêu cầu thêm mã giảm giá cho Checkout có thể đi qua:

~~~text
Yêu cầu nghiệp vụ
    |
    v
Frontend ticket
    |
    v
Backend ticket
    |
    v
Database migration request
    |
    v
QA handoff
    |
    v
Operations release approval
~~~

Nếu mỗi bước phải chờ ưu tiên của nhóm khác, tổng thời gian hoàn thành chủ yếu có thể là **waiting time**, không phải coding time.

### 4.1. Dấu vết trong kiến trúc

Tổ chức dạng này đôi khi tạo:

- Backend monolith vì tất cả nghiệp vụ ở một nhóm.
- Một database lớn do nhóm DBA duy nhất quản lý.
- Thay schema phải thông qua cùng hàng đợi dù thuộc domain khác nhau.
- API trở thành điểm bàn giao giữa frontend/backend thay vì contract của một luồng giá trị.
- QA đến cuối quy trình làm lỗi tích hợp bị phát hiện muộn.
- Operations trở thành cổng release thủ công.
- Incident bị chuyển tay giữa nhóm UI, backend, DB và hạ tầng.

Đây không phải kết luận mọi functional organization đều yếu. Với dự án nhỏ, công nghệ chuyên sâu hoặc hệ thống ổn định, phân công theo chức năng có thể hiệu quả. Cần đo thực tế: liệu ranh giới đó có làm tăng phụ thuộc bắt buộc cho các thay đổi thường ngày hay không?

## 5. Nhóm theo luồng giá trị nghiệp vụ

Một cách tổ chức khác:

~~~text
+-------------------+  +--------------------+
| Checkout Team     |  | Catalog Team       |
| UI slice + API    |  | UI slice + API     |
| Tests + on-call   |  | Tests + on-call    |
+-------------------+  +--------------------+

+-------------------+  +--------------------+
| Payment Team      |  | Fulfillment Team   |
| Contract + data   |  | Inventory/Shipping |
| Incident/release  |  | Data + operations  |
+-------------------+  +--------------------+

                Platform Team
         CI/CD + runtime + observability
         + self-service infrastructure
~~~

Mỗi stream-aligned team có thể chịu trách nhiệm phần lớn đường đi từ nhu cầu người dùng đến sản phẩm hoạt động, trong phạm vi được xác định rõ.

**Lợi ích tiềm năng:** ít handoff, ownership rõ, quyết định gần domain, thời gian phản hồi nhanh, phát hành và xử lý sự cố dễ hơn. **Điều kiện:** team có đủ năng lực, quyền thao tác trong guardrail, contract rõ với các team khác và platform đủ tự phục vụ.

Chỉ đổi tên nhóm mà vẫn buộc mọi triển khai, migration và quan sát lỗi phải gửi ticket cho nhóm trung tâm thì tính tự chủ chưa được cải thiện.

## 6. Phân biệt bốn kiểu boundary

| Boundary | Câu hỏi chính | Ví dụ |
|---|---|---|
| Domain boundary | Ở đâu có mô hình nghiệp vụ và ngôn ngữ nhất quán? | Checkout, Payment, Fulfillment |
| Code/module boundary | Code chia thành các phần và dependency thế nào? | package/module, library |
| Deployment boundary | Đơn vị nào build/ship độc lập? | container/service, một modular monolith |
| Team boundary | Ai quyết định, triển khai và chịu trách nhiệm? | Checkout Team, Platform Team |

Chúng **có thể nhưng không bắt buộc** trùng nhau. Một bounded context có thể chứa nhiều module và service. Một team có thể sở hữu nhiều service nhỏ. Một modular monolith có nhiều context vẫn là một deployment. Ngược lại, một service có thể có nhiều người đóng góp nhưng cần một cơ chế owner rõ cho quyết định và vận hành.

### 6.1. Vì sao 1 team = 1 service là quy tắc sai?

Nếu một nhóm tám người sở hữu bốn worker nhỏ cùng domain, việc bắt họ thành bốn nhóm không giúp gì khi khối lượng công việc chưa đủ. Nếu một service đang thực hiện ba năng lực độc lập và được nhiều nhóm sửa thường xuyên, có thể cần thay module boundary, data ownership hoặc deployment strategy. Quyết định phải dựa vào **nhu cầu thay đổi và năng lực vận hành**, không chỉ đếm số service.

## 7. DDD và bounded context

Trong Domain-Driven Design, bounded context là phạm vi có domain model và thuật ngữ nhất quán.

Ví dụ “Customer” ở các context:

- Checkout: người đặt hàng, địa chỉ giao.
- Billing: đối tượng xuất hóa đơn và thông tin pháp lý.
- Support: người liên hệ, yêu cầu hỗ trợ.
- Marketing: hồ sơ phân khúc và sự đồng ý nhận thông tin.

Ép tất cả dùng một Customer entity chung tạo coupling. Một field thêm cho Marketing có thể khiến Checkout/Billing phải cập nhật shared library hoặc database schema dù không cần.

~~~text
Checkout Context ---- contract ----> Billing Context
      |                                 |
      v                                 v
Checkout Model                     Billing Model
~~~

Mỗi bên có mô hình riêng, trao đổi qua interface và mapping cần thiết. Boundary domain thường hữu ích cho thiết kế ownership, nhưng không có nghĩa phải tách một Microservice ngay lập tức.

### 7.1. Bounded context và luồng thay đổi

Khi nhiều quy tắc thường xuyên thay cùng nhau, ví dụ discount calculation và checkout total calculation, cần hỏi chúng có thuộc cùng một capability không. Ngược lại Payment có audit, idempotency, fraud và yêu cầu SLO riêng; đó có thể là context phù hợp để tách ownership và deployment.

Context map cần ghi bên upstream/downstream, owner contract, chiều phụ thuộc và chính sách thay đổi. Không để mọi team sửa trực tiếp persistence của nhau.

## 8. Distributed monolith phản ánh coordination bottleneck

**Distributed monolith** có nhiều service nhưng rất khó phát hành, sửa hoặc khôi phục từng phần độc lập.

Dấu hiệu:

1. Một thay đổi nhỏ buộc sửa bốn service.
2. Service A thay contract thì B/C phải nâng cùng thời điểm.
3. Nhiều service đọc/ghi trực tiếp cùng bảng database.
4. Dùng shared domain library versioned buộc mọi team nâng đồng thời.
5. Một transaction nghiệp vụ bị chia thành nhiều RPC nhỏ và đồng bộ.
6. Không có contract tests hoặc chiến lược schema evolution.
7. Mọi release phải đi trong cùng một release train.
8. Incident bị chuyển qua nhiều owner vì không rõ ai chịu trách nhiệm flow cuối cùng.

Ví dụ:

~~~text
Promotion Service --RPC--> Pricing Service
        |                       |
        v                       v
   Shared discount DB <----- Checkout Service
                                  |
                                  v
                              Order Service
~~~

Nếu bất kỳ thay đổi discount nào cũng phải thay và deploy bốn thành phần, service boundary không đem lại độc lập thực tế.

Hướng xử lý có thể là gom logic thay cùng nhau vào domain module phù hợp, làm rõ quyền sở hữu dữ liệu, thiết kế API có độ hạt đúng, tiến hóa schema theo Expand–Migrate–Contract và dùng compatibility tests. Không nhất thiết phải gộp hoặc tách service ngay; cần hiểu coupling nằm ở đâu.

## 9. Inverse Conway Maneuver

**Inverse Conway Maneuver** là cách cố ý tổ chức các nhóm và đường phối hợp nhằm hỗ trợ kiến trúc mục tiêu, thay vì để kiến trúc chỉ phản ánh tổ chức sẵn có.

Ví dụ mong muốn ba context Catalog, Checkout, Billing có ownership rõ, nhưng mọi thay đổi hiện phải qua nhóm Backend, Database và Operations trung tâm:

~~~text
BEFORE:
Frontend ---- Backend ---- Database ---- Operations

AFTER:
Catalog Team ---- API contracts ---- Checkout Team
       |                                |
       +------------ Platform ----------+
                         |
                    Billing Team
~~~

Cách làm thực tế:

1. Giao ownership của code, data contract, release và SLO.
2. Cung cấp pipeline, test environment và observability tự phục vụ.
3. Thiết kế domain boundaries và API/event interfaces rõ.
4. Giảm shared schema và tập trung logic nghiệp vụ trong đúng context.
5. Chọn chế độ tương tác giữa các nhóm phù hợp.
6. Tạo policy bảo mật/compatibility và automatic guardrails.
7. Đo waiting time, lead time, deployment independence và incident.
8. Điều chỉnh sau khi có dữ liệu, không kỳ vọng đổi org chart là xong.

### 9.1. Điều kiện giới hạn

Nếu tổ chức chỉ có vài kỹ sư nhưng chia thành hàng chục team và triển khai hàng chục service, chi phí vận hành, on-call và communication có thể tăng. Một modular monolith với một nhóm đa kỹ năng có thể hợp lý hơn ở giai đoạn đầu.

Inverse Conway là **thiết kế có chủ đích**, không phải công thức phải chia nhỏ tối đa.

## 10. Team Topologies: bốn loại team

Team Topologies cung cấp một khung tư duy về tổ chức nhóm và tương tác nhằm giảm cognitive load, tăng flow và làm rõ trách nhiệm.

| Loại team | Trọng tâm | Ví dụ |
|---|---|---|
| Stream-aligned | Một luồng tạo giá trị | Checkout, Onboarding, Fulfillment |
| Platform | Khả năng nội bộ được dùng như sản phẩm | CI/CD, runtime, tracing, service templates |
| Enabling | Giúp nhóm khác học kỹ năng và vượt trở ngại | Security coaching, performance engineering |
| Complicated-subsystem | Năng lực chuyên sâu có chi phí nhận thức lớn | Fraud detection, optimizer, media processing |

Không nhất thiết mỗi công ty phải tạo đúng bốn phòng ban. Có thể một người/nhóm kiêm vài vai trò khi quy mô nhỏ; cần đảm bảo ownership và kỳ vọng rõ.

### 10.1. Stream-aligned team

Nhóm tập trung vào một luồng giá trị có thể xác định từ góc nhìn người dùng. Họ cần đủ khả năng thay đổi code, chạy kiểm thử, triển khai và phản hồi về hành vi production. Mức tự chủ phải đi cùng guardrail và quyền truy cập phù hợp.

### 10.2. Platform team

Platform cung cấp những capability dùng chung bằng giao diện tự phục vụ. Ví dụ:

- Template tạo service với liveness/readiness, logging và health checks.
- Pipeline build, ký artifact, scan và deploy.
- Tracing, metrics, log search.
- Secret management, access control và policy.
- Database provisioning theo mẫu.
- Cơ chế chuẩn hóa runbook, alert, rollback.

Platform tốt không trở thành đội thực hiện thủ công mọi deployment. Nếu vẫn phải gửi ticket để bật một metric tiêu chuẩn, bottleneck tổ chức còn đó.

### 10.3. Enabling team

Giúp team nghiệp vụ phát triển kỹ năng như threat modeling, distributed tracing, contract testing hoặc load testing. Mục tiêu là **chuyển giao năng lực**, không giữ tri thức trong một nhóm trung tâm mãi mãi.

### 10.4. Complicated-subsystem team

Phụ trách phần có chuyên môn rất sâu, ví dụ thuật toán phát hiện gian lận hoặc tối ưu tuyến đường. Cung cấp contract rõ để các nhóm khác dùng mà không cần hiểu toàn bộ phần kỹ thuật bên trong.

## 11. Ba chế độ tương tác giữa các team

### 11.1. Collaboration

Hai team làm việc chặt chẽ trong một giai đoạn để khám phá contract/thiết kế chưa rõ. Ví dụ Checkout và Payment cùng định nghĩa quy tắc idempotency, refund và error handling.

Collaboration hữu ích ở giai đoạn khám phá; nếu mọi thay đổi checkout bình thường đều phải có cuộc họp dài giữa hai team, cần xem boundary và contract.

### 11.2. X-as-a-Service

Một team cung cấp capability ổn định thông qua API, tài liệu, SLO, versioning và support model. Consumer có thể tự sử dụng mà không cần liên tục trao đổi implementation.

Ví dụ Payment cung cấp Payments API; Platform cung cấp deployment pipeline self-service. Điều kiện là contract rõ và vận hành đáng tin cậy.

### 11.3. Facilitating

Enabling team hỗ trợ, coaching và giúp team khác tự chủ dần. Ví dụ chuyên gia reliability làm việc ngắn hạn với Checkout để xây tracing và SLO, sau đó rút khỏi các thao tác thường ngày.

### 11.4. Chọn theo giai đoạn

~~~text
Khám phá vấn đề mới:
Checkout <--- collaboration ---> Payment

Hợp đồng ổn định:
Checkout ------ consume API ----> Payment

Thiếu năng lực quan sát:
Enabling ---- facilitating -----> Checkout

Deploy thường ngày:
Checkout ---- self-service -----> Platform
~~~

Không có một kiểu tương tác phù hợp mãi mãi. Collaboration kéo dài gây phụ thuộc; X-as-a-Service quá sớm có thể khóa một API chưa đủ hiểu nhu cầu; facilitating vô thời hạn khiến team chưa tự làm được.

## 12. Cognitive load quyết định phạm vi ownership

**Cognitive load** là lượng thông tin mà team cần nắm để phát triển và vận hành hệ thống an toàn.

Nguồn tải nhận thức:

- Quá nhiều service/framework khác nhau.
- Nhiều API, event, schema version và dependency.
- Mỗi service có pipeline, logging và security policy riêng.
- On-call một hệ thống thiếu traces/runbook.
- Dữ liệu và domain ownership mơ hồ.
- Nhiều approval, ticket và quan hệ phối hợp bất định.
- Phải hiểu các hệ thống internals mà team không thực sự sở hữu.

Không có số service tối ưu chung cho mỗi nhóm. Một team có thể vận hành nhiều service đơn giản hoặc bị quá tải bởi một subsystem cực kỳ phức tạp.

**Platform** giúp giảm tải nhận thức bằng cách chuẩn hóa và tự động hóa. **Bounded context** giúp giảm phạm vi domain cần hiểu. **Contract** giúp consumer không cần biết implementation của provider. Tuy nhiên, abstraction không được che giấu toàn bộ khả năng debug production.

## 13. Ownership và trách nhiệm end-to-end

Một bảng ownership nên làm rõ:

- Ai chịu trách nhiệm quyết định nghiệp vụ?
- Ai có quyền thay đổi contract và schema?
- Ai chạy deploy/rollback?
- Ai sở hữu SLO và nhận cảnh báo?
- Ai điều phối incident khi ảnh hưởng nhiều service?
- Ai hỗ trợ consumer khi API thay đổi?
- Ai phê duyệt migration hoặc thay đổi có rủi ro cao?

| Thành phần | Primary owner | Consumer/chủ thể liên quan | Phạm vi trách nhiệm |
|---|---|---|---|
| Checkout API | Checkout Team | Web, Mobile | Checkout flow, release, SLO |
| Payment API | Payment Team | Checkout, Refund | Payment contract, idempotency, audit |
| Inventory API | Fulfillment Team | Checkout | Reservation và consistency |
| Deployment platform | Platform Team | Các stream team | Runtime, self-service, observability |
| Security standards | Security/Enabling | Các team | Policy, training, verification |

Có thể dùng CODEOWNERS để xác định review có trách nhiệm. Nhưng mọi file không nên cần năm phê duyệt thủ công nếu kiểm tra lặp lại có thể tự động hóa.

### 13.1. “You build it, you run it” cần thực tế

Team phát triển service nên chịu trách nhiệm chất lượng và hành vi production. Điều này không có nghĩa họ phải tự vận hành mọi loại hạ tầng hoặc trực 24/7 không có hỗ trợ. Platform/SRE cung cấp runtime và năng lực vận hành chung; service owner cần runbook, observability, on-call/escalation phù hợp.

## 14. API/event contract như ranh giới phối hợp

Một team sở hữu Payment API, team Checkout là consumer:

~~~http
POST /payments HTTP/1.1
Content-Type: application/json
Idempotency-Key: order-100

{
  "orderId": "order-100",
  "amountMinorUnits": 150000,
  "currency": "VND"
}
~~~

Payment công bố response, status/error semantics, idempotency và SLO. Checkout không cần biết Payment lưu database gì; Payment không cần import entity nội bộ của Checkout.

Ranh giới được hỗ trợ bằng:

1. OpenAPI, Protobuf, AsyncAPI hoặc tài liệu contract tương ứng.
2. Consumer contract tests và provider verification.
3. Versioning, backward compatibility và deprecation policy.
4. Timeout/retry/idempotency/error codes.
5. Correlation ID, logs, metrics và distributed tracing.
6. Owner của từng API/event, support channel rõ.
7. Release notes và chiến lược migration.

### 14.1. Shared domain library gây coupling

Nếu mọi service dùng chung một library chứa các domain entity và phải nâng version đồng thời, tổ chức có thể bị buộc phát hành cùng nhau dù network API tương thích. Cần phân biệt utility dùng chung ổn định và model nghiệp vụ của từng bounded context.

### 14.2. Shared database là communication ngầm

Khi nhiều team đọc/ghi chung bảng, schema trở thành một contract không chính thức:

~~~text
Checkout Team ------+
                    +--> shared order_payment table
Payment Team -------+
Reporting Team -----+
~~~

Thay một column có thể cần phối hợp với ba team. Nên xác định owner của dữ liệu và chuyển consumer sang API/event/materialized view hoặc pipeline thích hợp; việc chuyển từ shared DB cần lộ trình tương thích.

## 15. Coordination cost ảnh hưởng lead time

Lead time một thay đổi có thể được nhìn như:

~~~text
Lead time
= thời gian chờ được ưu tiên
+ phân tích/trao đổi
+ triển khai
+ chờ review và dependency
+ kiểm thử
+ chờ phát hành
~~~

Đây là cách phân rã khái niệm, không phải công thức kế toán bắt buộc. Có thể đo timestamps của issue, PR và pipeline để thấy phần nào chiếm nhiều nhất.

Ví dụ giả định:

| Hoạt động | Functional silos | Stream-aligned ownership |
|---|---:|---:|
| Implement | 2 ngày | 2 ngày |
| Chờ API decision | 2 ngày | 0,5 ngày |
| Chờ DB/infra | 3 ngày | 0,5 ngày |
| Chờ QA/release | 3 ngày | 1 ngày |
| Tổng | 10 ngày | 4 ngày |

Số liệu chỉ minh họa. Nếu self-service làm giảm waiting time, nhóm có thể đưa tính năng đến người dùng sớm hơn **mà không cần viết code nhanh hơn**.

### 15.1. Thêm người không luôn giảm thời gian

Nếu mỗi thay đổi buộc trao đổi giữa nhiều nhóm, thêm nhân sự có thể tăng số kênh cần đồng bộ. Nên phân tích trước:

- Những boundary nào bị đi qua thường xuyên?
- Có approval lặp lại có thể tự động hóa?
- Có thể chuyển một capability ổn định sang X-as-a-Service?
- Có thể gom ownership theo domain?
- Có cần enabling team chuyển giao kỹ năng?
- Có module/service nào nên gom lại để giảm coupled releases?

## 16. Collaboration vẫn cần thiết

Không phải mọi giao tiếp xuyên team là xấu. Những trường hợp nên hợp tác sâu:

- Thiết kế payment với rủi ro tài chính và yêu cầu audit.
- Thay schema event dùng bởi nhiều consumer.
- Migration data qua nhiều bounded context.
- Quy tắc consistency/saga cho workflow nhiều service.
- Authentication, authorization, data privacy.
- Breaking API change, chiến lược backward compatibility.
- Incident xuyên nhiều service hoặc shared dependency.

Mục tiêu là **collaborate khi khám phá**, rồi chuyển sang contract và quy trình tự phục vụ cho việc lặp lại. Nếu mỗi request bình thường đều cần các nhóm họp cùng nhau, đã đến lúc đánh giá lại boundary và interaction mode.

## 17. Microservice sprawl và modular monolith

Microservice sprawl xuất hiện khi có quá nhiều deployment nhỏ hơn mức tổ chức có thể vận hành hiệu quả:

- Mỗi service có repo, pipeline, dashboard và on-call riêng.
- Các request đi qua hàng chục synchronous hops.
- Phải nâng shared schema hoặc library cùng lúc.
- Không ai hiểu end-to-end business flow.
- Chi phí hạ tầng, tracing và release tăng mà giá trị không tương xứng.
- Các service không thể deploy độc lập dù khác repository.

Một **modular monolith** có thể là lựa chọn phù hợp hơn:

~~~text
Application (one deployment)
  |
  +-- Catalog Module
  +-- Checkout Module
  +-- Billing Module
  +-- Fulfillment Module
       |
       +-- Explicit module interfaces
~~~

Nó vẫn có domain boundaries và ownership rõ, chỉ khác deployment boundary. Khi một module có nhu cầu scale/SLO/release riêng và có team vận hành đủ năng lực, có thể cân nhắc tách service. Conway's Law là lý do cần nhìn tổ chức và domain cùng nhau, không phải lý do Microservices luôn bắt buộc.

## 18. Tiến hóa tổ chức và kiến trúc theo giai đoạn

### Giai đoạn 1 — Sản phẩm nhỏ

Một team đa kỹ năng, một deployment, module nghiệp vụ rõ, CI/CD đơn giản. Ưu tiên tốc độ học và tránh distributed overhead quá sớm.

### Giai đoạn 2 — Nhiều luồng giá trị

Khi Catalog và Checkout thay đổi theo nhịp khác nhau, làm rõ ownership theo bounded context. Có thể giữ một deployment nếu module boundaries vẫn hiệu quả.

### Giai đoạn 3 — Tách deployment có bằng chứng

Khi một context có nhu cầu scale, bảo mật hoặc SLO riêng, tách service cùng data ownership và contract. Team phải có khả năng deploy và điều tra incident.

### Giai đoạn 4 — Nền tảng tự phục vụ

Nhiều team lặp lại các thao tác về CI/CD, secrets, tracing, database provisioning. Đầu tư platform và enabling để giảm cognitive load và tránh phát minh lại các công cụ.

### Giai đoạn 5 — Quản trị quy mô lớn

Nhiều stream team cùng tồn tại, cần dependency graph, API governance, contract compatibility, release waves và platform standards có automation; tránh một hội đồng phê duyệt mọi thay đổi nhỏ.

Lộ trình này không bắt buộc. Tổ chức có nhiều ràng buộc legacy hoặc lĩnh vực yêu cầu compliance nghiêm ngặt sẽ cần bước chuyển tiếp khác nhau.

## 19. Quy trình tái thiết kế boundary

### Bước 1. Chọn một luồng giá trị

Ví dụ “khách hàng đặt và thanh toán đơn hàng”. Liệt kê UI, xác nhận giá, giữ kho, thanh toán, tạo order và thông báo.

### Bước 2. Vẽ đường giao tiếp hiện tại

Một thay đổi checkout gần đây đã cần ai tham gia? Chú ý cả việc ẩn như chờ migration, cấp quyền, tạo môi trường và phê duyệt release.

### Bước 3. Vẽ dependency graph

Liệt kê module/service, schema, event, owner và pipeline. Đánh dấu những service thường phải phát hành cùng lúc.

### Bước 4. Đánh giá domain boundary

Dùng DDD và các quy tắc nghiệp vụ để xác định code/data cần thay cùng nhau, chỗ nào hợp lý giữ API.

### Bước 5. Thiết kế ownership mục tiêu

Xem team có đủ kỹ năng, cognitive capacity và on-call coverage không. Không phân ownership theo số lượng file bằng nhau.

### Bước 6. Tạo quyền tự chủ an toàn

Cung cấp self-service deployment, test data, observability, contract tests và automated policy. Chuyển shared database qua lộ trình an toàn.

### Bước 7. Di chuyển dần

Có thể bắt đầu thay module boundary trước khi tách service. Hạn chế big-bang rewrite và phân định owner trong thời kỳ chuyển giao.

### Bước 8. Đo và điều chỉnh

Theo dõi lead time, blocked time, coupled changes, change failure rate, SLO và phản hồi nhóm. Chỉnh lại boundary nếu kết quả không đạt.

## 20. Change coupling: những phần thường sửa cùng nhau

Một dữ liệu hữu ích là **co-change**: hai module/service có hay xuất hiện trong cùng PR, issue hoặc deployment không?

Ví dụ giả định:

| Module A | Module B | Tỷ lệ xuất hiện cùng trong mẫu | Gợi ý |
|---|---|---:|---|
| Checkout pricing | Checkout discounts | 70% | Có thể cùng capability |
| Checkout | Payment API | 12% | Contract có thể tương đối ổn |
| Catalog | Notification | 3% | Có thể độc lập |
| Inventory | Fulfillment schedule | 55% | Xem ownership và data boundary |

Các tỷ lệ chỉ minh họa. Co-change cao không tự chứng minh cần gộp code: có thể do một migration tạm thời hoặc coupling đang được sửa. Phải kết hợp lịch sử thay đổi, domain semantics, incident và giao tiếp thực tế.

### 20.1. Nguồn thông tin có thể dùng

- Git/PRs: module nào thường thay cùng nhau?
- Issue tracker: ticket nào blocked by nhóm khác?
- CI/CD: service nào thường được triển khai cùng wave?
- Tracing: synchronous calls có quá nhiều hop không?
- Postmortem: incident phải nhờ bao nhiêu nhóm?
- Domain workshops: thuật ngữ và quy tắc thuộc context nào?
- Phỏng vấn nhóm: những điểm nghẽn không hiện trên dashboard là gì?

Các metric phải được đặt trong ngữ cảnh; không dùng để quy trách nhiệm cá nhân.

## 21. Chỉ số để đánh giá hiệu quả

| Nhóm | Chỉ số | Câu hỏi |
|---|---|---|
| Delivery | Lead time for change | Mất bao lâu từ code đến production? |
| Delivery | Deployment frequency | Có thể ship mỗi capability độc lập không? |
| Reliability | Change failure rate | Thay đổi có gây sự cố không? |
| Reliability | Time to restore | Mất bao lâu để khôi phục sau lỗi? |
| Coordination | Blocked/waiting time | Chờ ai và vì sao? |
| Coordination | Cross-team dependency tickets | Bao nhiêu lần phải chuyển việc? |
| Architecture | Co-change/release coupling | Các deployment có thật sự độc lập? |
| Operations | Incident handoffs | Ai nhận trách nhiệm cuối? |
| Team experience | Cognitive load, onboarding time | Team có hiểu và vận hành scope không? |
| Product | User outcome, SLO | Người dùng có nhận giá trị ổn định không? |

Bốn chỉ số delivery/reliability đầu thường liên quan các phép đo DORA. Không nên dùng riêng deployment frequency, số PR hay số Microservice làm mục tiêu hình thức. Một service ổn định ít thay đổi có thể rất khỏe mạnh.

### 21.1. Đọc kết quả có trách nhiệm

Sau tái tổ chức, lead time giảm nhưng change failure rate tăng mạnh có thể cho thấy tự chủ thiếu guardrail. Ngược lại, incident ít hơn nhưng tất cả thay đổi phải chờ hội đồng có thể là tối ưu quá mức một phía. Cần đánh giá khả năng tạo giá trị **và** độ tin cậy.

## 22. Release coordination và API evolution

Microservices có giá trị khi các phần có thể triển khai độc lập **trong phạm vi hợp đồng tương thích**.

Một release train bắt tất cả service A/B/C deploy cùng giờ có thể do contract không ổn, shared DB hoặc process tổ chức:

~~~text
Trước:
A v2 + B v2 + C v2 phải cùng phát hành

Sau:
A v2 tương thích B v1/v2
B v2 tương thích C v1/v2

=> Có thể rollout từng service theo ma trận
~~~

Để giảm phối hợp bắt buộc:

1. Công bố provider/consumer owner cho API và event.
2. Giữ backward compatibility trong thời kỳ chuyển tiếp.
3. Dùng consumer-driven contract test khi phù hợp.
4. Migration database theo Expand–Migrate–Contract.
5. Dùng feature flags và canary nếu giúp giới hạn blast radius.
6. Có rollback/runbook rõ và đo version thật đang chạy.
7. Cung cấp self-service CI/CD để release bình thường không cần ticket.

Thay đổi breaking, giao dịch quan trọng và incident vẫn cần collaboration có chủ đích.

## 23. Event-driven communication và coupling tổ chức

Async messaging có thể giảm phụ thuộc thời gian:

~~~text
Order Team:
OrderCreated ------> Event Broker
                        |
                        +----> Inventory consumer
                        +----> Notification consumer
                        +----> Analytics consumer
~~~

Producer không cần gọi đồng bộ từng consumer để hoàn thành request. Consumer có thể xử lý và deploy theo nhịp riêng **nếu event contract ổn định**.

Tuy nhiên, async không tự xóa coupling:

- Schema vẫn cần owner và compatibility policy.
- Consumer phải xử lý duplicate, retry, out-of-order và eventual consistency.
- Business event phải có ý nghĩa rõ, không phải object DB bị serialize tùy tiện.
- Sự cố của broker có thể ảnh hưởng nhiều nhóm.
- Workflow cần tính nhất quán nghiệp vụ có thể cần saga/compensation.
- Thiếu tracing khiến dependency khó nhìn thấy.

Không nên biến một event thành kho field khổng lồ để thỏa mãn mọi team. Hợp đồng cần phản ánh một business fact, không chỉ cấu trúc bảng.

## 24. SLO và trách nhiệm vận hành

Nếu một team sở hữu service nhưng không biết SLO, không có dashboard hoặc không biết cách rollback, ownership có thể chỉ là hình thức.

Ví dụ:

| Team | Capability | SLI/SLO quan trọng | Runbook |
|---|---|---|---|
| Checkout | Đặt hàng | Success rate, p95 checkout | Checkout Team |
| Payment | Giao dịch | Correctness, availability, latency | Payment + escalation |
| Fulfillment | Reservation | Reservation success, queue age | Fulfillment Team |
| Platform | Runtime | Deployment latency, pipeline reliability | Platform/SRE |

Khi lỗi xuyên service, cần một người điều phối incident; các owner vẫn có trách nhiệm xác định nguyên nhân và sửa phần của mình.

### 24.1. On-call và cognitive capacity

“You build it, you run it” không có nghĩa mọi team tự quản trị toàn bộ hạ tầng hoặc trực vô hạn. Nên phân trách nhiệm domain behavior và platform operations rõ, có escalation và tài liệu. Tránh giao quá nhiều service cho team không đủ năng lực trực và phục hồi.

## 25. Governance nhẹ nhưng hiệu quả

Team tự chủ vẫn cần tiêu chuẩn chung cho:

- Authentication, authorization và dữ liệu nhạy cảm.
- Schema/API versioning, deprecation, contract tests.
- Logging, metrics, tracing và correlation IDs.
- Artifact provenance, dependency scanning và supply chain.
- Timeout, retry, idempotency, circuit breaker.
- Data ownership, retention, backup và disaster recovery.
- Security review theo độ rủi ro.
- Paved-road service templates và runtime policy.

Nên triển khai các quy tắc lặp lại bằng **tài liệu, template và automated guardrails**. Các quyết định kiến trúc lớn có thể dùng ADR và review liên nhóm, nhưng đừng yêu cầu hội đồng duyệt mọi thay đổi nhỏ đã tuân thủ tiêu chuẩn.

### 25.1. Ví dụ Architecture Decision Record

~~~markdown
# ADR-012: Checkout sở hữu chính sách tính giá giỏ hàng

## Context
Discount và checkout totals thường đổi cùng nhau.
Bảng dữ liệu chung gây phát hành đồng bộ.

## Decision
Checkout sở hữu mô hình tính giá của giỏ.
Payment nhận số tiền phải trả và currency qua API.
Không nhúng Promotion domain vào Payment.

## Consequences
Checkout chịu trách nhiệm chính sách giá.
Payment giữ payment contract và idempotency.
Cần migration để loại bỏ shared table.
~~~

Đây là quyết định minh họa. Mục tiêu của ADR là lưu bối cảnh, lý do, phương án và hệ quả cho các team, không chỉ mô tả code.

## 26. Anti-pattern khi tái tổ chức

| Anti-pattern | Hậu quả | Điều chỉnh |
|---|---|---|
| Đổi org chart nhưng giữ ticket deploy tập trung | Thời gian chờ không giảm | Platform self-service + policy |
| Chia service theo manager hiện tại | Domain boundary bị méo | Thiết kế từ nghiệp vụ và thay đổi |
| Một team sở hữu hàng chục service khác công nghệ | Cognitive overload | Gom module, giảm tool diversity, hỗ trợ platform |
| Team xây lại CI/CD của riêng mình | Lãng phí và drift security | Platform product với paved road |
| Shared database không có owner | Coupled migrations | Data ownership và lộ trình tách |
| Mỗi thay đổi nhỏ cần ba team review | Lead time cao | Contract + automated guardrail |
| Mọi nhóm tự chủ nhưng không có chuẩn | Thiếu compatibility và bảo mật | Chính sách chung có automation |
| Chuyển ownership không có giai đoạn bàn giao | Incident không ai nhận | Runbook, shadowing và ngày cutover |
| Tách quá nhiều Microservice khi team nhỏ | Sprawl, khó on-call | Modular monolith khi phù hợp |
| Collaboration không có điểm kết thúc | Thường trực chờ họp | Ổn định contract, chuyển sang X-as-a-Service |

### 26.1. Tranh chấp ownership

Khi hai team đều nhận trách nhiệm hoặc không team nào nhận, đặt câu hỏi:

- Ai hiểu và thay đổi quy tắc nghiệp vụ thường xuyên nhất?
- Ai sở hữu dữ liệu và transaction boundary?
- Ai có thể đảm bảo SLO và xử lý incident?
- Consumer cần một contract ổn định từ ai?
- Có thể chọn một primary owner và mô hình đóng góp của nhóm khác không?
- Team đó có đủ cognitive capacity để nhận responsibility?

Ownership không nhất thiết thuộc team viết code đầu tiên; nên theo năng lực quyết định và vòng đời lâu dài.

## 27. Bài tập thực hành A: khảo sát luồng checkout

**Bối cảnh:** Web, Backend, DBA, QA và SRE là năm nhóm độc lập. Tính năng thêm phương thức thanh toán thường mất hai tuần, trong đó coding chỉ ba ngày. Release tuần một lần.

**Nhiệm vụ:**

1. Vẽ communication graph cho quy trình tính năng.
2. Vẽ dependency graph Web → Checkout → Payment → Database.
3. Ghi thời gian chờ mỗi handoff và những điều kiện phê duyệt thực sự cần thiết.
4. Đề xuất ownership theo Checkout và Payment capability.
5. Định nghĩa API contract, error semantics, idempotency và consumer tests.
6. Xác định các thao tác có thể đưa vào platform self-service.
7. Ghi những thay đổi vẫn cần Security/DBA collaboration.
8. Chọn baseline lead time, blocked time, change failure và SLO.
9. Đề xuất một thử nghiệm nhỏ trước khi thay toàn bộ tổ chức.

**Điểm rút ra:** Nếu vẫn dùng shared schema và release thủ công, đổi tên nhóm chưa chắc thay đổi khả năng phát hành.

## 28. Bài tập thực hành B: chọn Team Topologies

**Bối cảnh:** Hệ thống SaaS có 30 service. Các nhóm sản phẩm chờ Infrastructure để deploy và xem logs. Một nhóm chuyên gia xây mô hình phát hiện gian lận; các nhóm checkout cần dùng điểm rủi ro nhưng không cần biết thuật toán.

**Phương án xem xét:**

- Các luồng Onboarding, Checkout, Fulfillment có thể là stream-aligned teams.
- Platform cung cấp deploy, runtime, logs và secrets theo self-service.
- Fraud Detection là complicated-subsystem team nếu độ sâu thuật toán biện minh.
- Enabling giúp nhóm khác áp dụng tracing, security practices, contract testing.
- Checkout và Fraud collaboration để khám phá API, sau đó X-as-a-Service khi contract ổn định.

**Câu hỏi:**

1. Capability nào nên là sản phẩm platform?
2. Frauds API đồng bộ hay event bất đồng bộ phù hợp với latency và risk?
3. Ai chịu trách nhiệm khi fraud scoring timeout và checkout cần phản hồi?
4. Team Checkout có bắt buộc sở hữu một service duy nhất?
5. Làm sao giảm cognitive load mà vẫn giữ khả năng debug?
6. Khi nào một collaboration đã có thể kết thúc?

## 29. Bài tập thực hành C: điều tra change coupling

Giả sử từ 100 pull request:

- 55 PR thay Checkout và Discount module cùng nhau.
- 10 PR thay Checkout và Payment contract.
- 3 PR thay Catalog và Notification.
- 25 PR cần release team tham gia dù chỉ thay một service.

Hãy:

1. Phân tích Checkout–Discount có cùng bounded context hoặc owner không.
2. Kiểm tra Checkout–Payment có backward compatible contract không.
3. Tìm lý do 25 PR phải chờ release team.
4. Đề xuất can thiệp nhỏ như self-service, contract tests hoặc gộp module.
5. Chọn chỉ số trước/sau và thử trong vài chu kỳ release.
6. Giải thích vì sao co-change cao không tự quyết định kiến trúc cần gộp.

Số liệu là giả định phục vụ bài tập, không phải kết quả thực tế.

## 30. Checklist đánh giá kiến trúc và tổ chức

### Ranh giới nghiệp vụ

- [ ] Có luồng giá trị chính và bounded contexts được mô tả.
- [ ] Mỗi context có mô hình dữ liệu, ngôn ngữ và owner rõ.
- [ ] Không tách Microservice chỉ vì sơ đồ tổ chức.
- [ ] Các module hay thay cùng nhau được phân tích.
- [ ] Shared database/schema có owner và migration policy.
- [ ] Contract giữa context có versioning và compatibility test.

### Tổ chức và tương tác

- [ ] Có sơ đồ các team và handoff bắt buộc của thay đổi điển hình.
- [ ] Team biết khi nào collaboration, X-as-a-Service và facilitating phù hợp.
- [ ] Những thao tác thường ngày có self-service trong guardrail.
- [ ] Platform không trở thành nút phê duyệt thủ công.
- [ ] Enabling giúp chuyển giao kỹ năng thay vì giữ phụ thuộc mãi.
- [ ] Cognitive load và on-call burden được cân nhắc trước khi giao thêm service.
- [ ] Ownership code, contract, data, SLO và incident đều rõ.
- [ ] Có kế hoạch chuyển giao khi đổi team boundary.

### Kiến trúc và vận hành

- [ ] Service có khả năng deploy riêng trong phạm vi contract đã công bố.
- [ ] Breaking change có kế hoạch chuyển tiếp và rollout phù hợp.
- [ ] Có distributed tracing và runbook để xử lý sự cố xuyên service.
- [ ] Shared domain library không buộc synchronized deploy không cần thiết.
- [ ] Có tiêu chuẩn chung về security, observability và resilience.
- [ ] Kiến trúc lớn được giải thích bằng ADR hoặc cơ chế phù hợp.

### Đo hiệu quả

- [ ] Có baseline lead time và blocked time.
- [ ] Có dữ liệu co-change, co-deploy và dependency tickets.
- [ ] Theo dõi change failure rate, restore time và SLO.
- [ ] Có phản hồi định tính từ người làm việc thực tế.
- [ ] Không dùng số service, số PR hoặc deployment frequency đơn lẻ làm thước đo chất lượng.
- [ ] Sau thay đổi tổ chức, đã có mốc xem xét và điều chỉnh ranh giới.

## 31. Kết luận

**Cấu trúc giao tiếp của tổ chức và kiến trúc phần mềm ảnh hưởng lẫn nhau.** Conway's Law nhắc rằng đường trao đổi và quyết định giữa con người thường để lại dấu vết ở module, API và dependency. Trong Microservices, vấn đề không chỉ mang tính lý thuyết: khi một thay đổi nhỏ phải qua nhiều nhóm, shared schema và release window chung, kiến trúc khó mang lại khả năng triển khai độc lập dù đã có nhiều service.

Hướng tiếp cận phù hợp là **thiết kế domain boundary, team ownership, contract và platform capabilities cùng nhau**. Inverse Conway Maneuver giúp định hướng lại tổ chức để hỗ trợ kiến trúc mong muốn. Team Topologies cung cấp các kiểu team và chế độ tương tác nhằm cân bằng flow, chuyên môn và tải nhận thức. Không nên thực hiện máy móc hay chia nhóm nhỏ hơn khả năng vận hành thực tế.

Bắt đầu từ dữ liệu: **luồng giá trị → đồ thị giao tiếp → đồ thị phụ thuộc → bounded context → ownership và platform tự phục vụ → đo tốc độ thay đổi, reliability và trải nghiệm nhóm**. Khi ranh giới con người và kỹ thuật phù hợp, các nhóm có thể đổi mới nhanh hơn mà vẫn giữ trách nhiệm, hợp đồng và chất lượng của toàn bộ hệ thống.