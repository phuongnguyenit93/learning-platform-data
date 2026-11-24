# Chọn nơi lưu hợp đồng và quy trình đề xuất thay đổi

Khi số lượng microservices tăng lên, câu hỏi không còn chỉ là **viết contract Groovy/YAML như thế nào**. Nhóm cần quyết định contract được lưu ở repository nào, ai sở hữu nội dung, consumer đề xuất thay đổi bằng cách nào, producer phê duyệt ra sao, và artifact nào được dùng để kiểm thử trong CI. Nếu mỗi đội tự lưu một bản contract, producer test và consumer test có thể chạy trên những định nghĩa khác nhau. Nếu dồn mọi thứ vào một kho trung tâm mà không phân định ownership, một thay đổi nhỏ có thể phải chờ nhiều nhóm và không ai chịu trách nhiệm cuối cùng.

Với **Spring Cloud Contract**, cần tách ba câu hỏi:

1. **Contract source được quản lý ở đâu?** Đây là nguồn Groovy/YAML có thể review, version control và sinh tests.
2. **Stub/generated artifacts được phân phối ở đâu?** Consumer thường tải JAR classifier `stubs` từ Maven repository hoặc cơ chế phân phối đã cấu hình để dùng với Stub Runner.
3. **Quy trình thay đổi được điều phối thế nào?** Ai đề xuất, review, xác nhận compatibility, merge, publish và thông báo tới các consumer?

Ba câu hỏi liên quan nhưng không đồng nhất. Maven repository lưu JAR `stubs` không tự trở thành nơi quản lý toàn bộ source contract và quyết định nghiệp vụ. Git repository lưu DSL không tự chứng minh producer implementation đã đáp ứng contract. Một contract broker hoặc developer portal, nếu tổ chức dùng, là lớp governance/phân phối riêng; không nên nhầm nó với chức năng bắt buộc có sẵn của Spring Cloud Contract.

Bài thuộc chương **Lựa chọn chiến lược** của mô-đun **SPRING_CLOUD_CONTRACT**. Mô-đun học kiểm thử hợp đồng giữa producer và consumer qua HTTP hoặc message, định nghĩa hành vi bằng Groovy/YAML DSL, sinh producer verification tests, phát hành stubs, sử dụng Stub Runner và tích hợp CI để phát hiện thay đổi API không tương thích. Mục tiêu là chọn mô hình lưu trữ phù hợp với ownership và quy mô nhóm, sau đó thiết kế một quy trình đề xuất thay đổi có thể kiểm tra, truy vết và mở rộng.

## 1. Bắt đầu bằng cách phân biệt ba loại dữ liệu

Một hệ thống Spring Cloud Contract thường có ít nhất ba lớp dữ liệu:

| Loại | Ví dụ | Mục đích | Nơi lưu phù hợp |
| --- | --- | --- | --- |
| **Contract source** | `get_paid_order.groovy`, `order-created-v1.yml` | Mô tả request, response, message, matchers và scenario. | Git repository có review và lịch sử. |
| **Generated tests và mappings** | JUnit/Spock tests, WireMock mappings | Kiểm producer và tạo hành vi stub. | Thường là build output; có thể đóng gói vào artifact `stubs`. |
| **Published stub artifact** | `com.acme:order-service:1.4.2:stubs` | Consumer tải bộ stubs đúng version để chạy Stub Runner. | Maven-compatible artifact repository hoặc cơ chế phân phối đã cấu hình. |

Ngoài ra, tổ chức có thể lưu **metadata quản trị**: owner, consumer inventory, compatibility decision, deprecation date, approval và release provenance. Metadata này có thể ở PR, CODEOWNERS, catalog, contract registry hoặc hệ thống governance; nó không nên bị nhúng tùy tiện vào DSL nếu không thuộc hành vi API.

**Source of truth** phải chỉ rõ:

- File contract nào là bản được review và sửa đổi.
- Ai có quyền chấp nhận thay đổi behavior.
- Build nào đã sinh producer tests/stubs từ source đó.
- Artifact nào được consumer test sử dụng.
- Version nào đang được triển khai và còn được hỗ trợ.

Không để hai bản DSL cùng được xem là canonical mà không có quy tắc đồng bộ.

## 2. Những mô hình lưu trữ thường gặp

Có năm mô hình chính:

1. Contract nằm trong **producer repository**.
2. Contract do **consumer đề xuất/sở hữu** trong repository của consumer hoặc một vùng riêng.
3. Contract nằm trong **central contract repository**.
4. Contract nằm trong **monorepo** cùng các dịch vụ.
5. Mô hình **hybrid**: source theo ownership, còn artifacts và metadata được phân phối tập trung.

Không có một mô hình đúng cho mọi tổ chức. Lựa chọn phụ thuộc vào số lượng consumer, mức độ độc lập release, quy trình ownership, khả năng vận hành CI và yêu cầu audit.

## 3. Mô hình A: lưu contract trong producer repository

Đây là lựa chọn tự nhiên cho nhiều dự án Spring Cloud Contract. Producer quản lý DSL cùng code mà nó phải thực hiện:

~~~text
order-service/
├── pom.xml
└── src/
    └── test/
        ├── java/com/acme/orders/contract/
        │   └── BaseContractTest.java
        └── resources/contracts/
            ├── orders/
            │   ├── get-paid-order.groovy
            │   └── order-not-found.groovy
            └── messaging/
                └── order-created-v1.groovy
~~~

Producer team review contract change như một phần của code change. Spring Cloud Contract Maven/Gradle Plugin đọc thư mục contract, sinh producer tests và mappings; build có thể đóng gói mappings thành JAR classifier `stubs` để consumer sử dụng.

### Ưu điểm

- **Ownership rõ:** team sở hữu API và implementation cùng review.
- **Thay đổi nguyên tử:** code và contract có thể merge trong một commit/PR.
- **Producer verification gần code:** generated tests chạy ngay trên implementation.
- **Lịch sử đầy đủ:** Git blame/log cho biết contract thay đổi cùng lý do.
- **Release thuận tiện:** stubs gắn với version/build của producer.
- **Ít hạ tầng:** không cần một contract server riêng chỉ để lưu DSL.

### Hạn chế

- Consumer có thể **không biết contract thay đổi** nếu không có notification/compatibility workflow.
- Consumer-driven proposal cần đi qua repository của producer hoặc một cơ chế mở PR có quyền.
- Khi nhiều consumer có nhu cầu khác nhau, producer repo có thể chứa nhiều scenario và khó xác định consumer nào đang phụ thuộc.
- Producer có thể định nghĩa contract theo góc nhìn của mình và bỏ sót behavior consumer thật sự cần.

### Phù hợp khi

- Producer là owner chính của API.
- Consumer team có thể review PR hoặc tham gia quy trình thay đổi.
- Số lượng consumer vừa phải, release được điều phối tốt.
- Contract và implementation thường thay đổi cùng nhau.

**Khuyến nghị:** nếu chưa có yêu cầu đặc biệt, bắt đầu với producer-owned contract trong producer repo. Đây là mô hình dễ tích hợp generated verification và stub packaging nhất. Khi tổ chức lớn lên, bổ sung consumer inventory, compatibility tests và governance trước khi chuyển toàn bộ source sang một kho mới.

## 4. Mô hình B: consumer-driven contract

Trong mô hình consumer-driven, **consumer đưa ra nhu cầu tương tác cụ thể** mà nó phụ thuộc. Consumer mô tả request/response hoặc message behavior cần thiết; producer review và xác nhận có thể cung cấp behavior đó. Với Spring Cloud Contract, contract DSL vẫn có thể được dùng để sinh producer verification tests; điểm khác là **quyền khởi xướng và quy trình ownership**.

Ví dụ Billing cần Order API:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'billingReadsPaidOrder'

    request {
        method 'GET'
        url '/api/orders/42'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            id: 42,
            status: 'PAID',
            amountMinor: 125000,
            currency: 'VND'
        )
    }
}
~~~

Contract này diễn tả nhu cầu của Billing. Producer cần review và xác nhận:

- Endpoint/method/header có được hỗ trợ?
- `status`, amount và currency có đúng semantics?
- Response này có thực sự được bảo đảm hay chỉ là dữ liệu tình cờ?
- Billing có đang yêu cầu một behavior chỉ dùng riêng cho nó không?
- Những consumer khác có bị ảnh hưởng bởi việc thêm hoặc thay đổi behavior?

### Ưu điểm

- Consumer requirements được thể hiện rõ, giảm nguy cơ producer tự đoán nhu cầu.
- Consumer có thể chủ động đề xuất thay đổi và đưa test case tái hiện.
- Contract review trở thành cuộc trao đổi về behavior thực tế thay vì tài liệu chung chung.
- Hữu ích khi consumer có nhiều release độc lập hoặc producer phục vụ nhiều đội.

### Hạn chế

- Nhiều consumer có thể tạo các contract trùng lặp hoặc mâu thuẫn.
- Nếu mọi consumer đều đòi behavior riêng, producer có thể phải duy trì API quá đặc thù.
- Producer vẫn cần quyền quyết định behavior và khả năng triển khai.
- Phải có cơ chế hợp nhất các nhu cầu thành một contract source có thẩm quyền.

**Consumer-driven không có nghĩa consumer tự ý áp đặt API lên producer.** Consumer đề xuất bằng chứng và nhu cầu; producer owner xác nhận contract có thể được hỗ trợ; các consumer khác được đánh giá khi thay đổi có ảnh hưởng rộng.

### 4.1. Lưu contract consumer ở đâu?

Có thể lưu draft/consumer proposal trong:

- Repository của consumer, gắn với code client.
- Một thư mục proposal riêng trong central contract repository.
- Pull request vào producer repository.
- Một contract registry/portal có hỗ trợ versioning và approval.

Điểm bắt buộc là có **đường dẫn rõ từ proposal tới contract đã được producer chấp nhận**. Đừng để Stub Runner tiêu thụ nhiều bản proposal chưa được xác minh như thể tất cả đều là producer release chính thức.

## 5. Mô hình C: central contract repository

Một kho trung tâm lưu contract của nhiều service:

~~~text
service-contracts/
├── README.md
├── ownership/
│   ├── order-service.yml
│   └── billing-service.yml
├── order-service/
│   ├── v1/
│   │   ├── http/
│   │   └── messaging/
│   └── v2/
│       └── http/
├── payment-service/
│   └── v1/
└── inventory-service/
    └── v1/
~~~

Central repository có thể dùng Git như một nguồn contract source, còn producer pipeline checkout/fetch contract theo commit/tag được cấu hình. Cách tích hợp cụ thể phụ thuộc cách project cấu hình `contractsDirectory`, build plugin, submodule, artifact hoặc script checkout; **Spring Cloud Contract không bắt buộc mọi tổ chức phải có một central repository**.

### Ưu điểm

- Dễ nhìn toàn cảnh contract giữa nhiều service.
- Có thể đặt quy tắc review, ownership, naming và versioning thống nhất.
- Consumer-driven proposals có một nơi chung để trao đổi.
- Dễ lập báo cáo consumer inventory và compatibility matrix nếu metadata được chuẩn hóa.
- Hữu ích khi tổ chức cần audit hoặc governance tập trung.

### Hạn chế

- Central repository có thể trở thành bottleneck của mọi thay đổi.
- Build producer phụ thuộc thêm vào checkout/version của repository khác.
- Có thể khó giữ contract source và producer code đồng bộ nguyên tử.
- Team platform phải duy trì cấu trúc, quyền truy cập, CI và công cụ.
- Nếu quyền sửa quá rộng, một nhóm có thể thay contract service khác mà owner không biết.

### Phù hợp khi

- Nhiều team chia sẻ API/event và cần governance chung.
- Có platform/API enablement team duy trì tooling.
- Consumer-driven proposal cần workflow đa nhóm.
- Tổ chức đã có catalog/registry/approval process và có thể tích hợp.

**Central repository không tự giải quyết ownership.** Mỗi contract vẫn cần một producer owner, consumer stakeholders và rule review. Nếu thiếu ownership, kho trung tâm chỉ chuyển sự mơ hồ từ nhiều repo sang một repo lớn.

## 6. Mô hình D: monorepo

Nếu nhiều dịch vụ cùng nằm trong một repository:

~~~text
platform/
├── services/
│   ├── order-service/
│   │   ├── src/main/
│   │   └── src/test/resources/contracts/
│   ├── billing-service/
│   │   └── src/test/
│   └── inventory-service/
├── shared-contract-test/
└── pom.xml
~~~

Contract thường nằm cạnh producer module. Build có thể điều phối các module phụ thuộc theo reactor hoặc task graph.

### Ưu điểm

- Một PR có thể cập nhật producer contract, implementation và consumer cùng lúc.
- Dễ chạy compatibility tests giữa các module trong cùng commit.
- Không cần đồng bộ commit qua nhiều repository cho một thay đổi phối hợp.
- Dễ áp dụng code owners/path filters và chuẩn build chung.

### Hạn chế

- Repo lớn, build có thể chậm nếu không tối ưu affected modules.
- Quyền merge và release độc lập cần được thiết kế cẩn thận.
- Một PR có thể vô tình kéo thay đổi nhiều service.
- Artifact versions vẫn cần được quản lý riêng nếu deploy độc lập.

**Monorepo không loại bỏ nhu cầu versioning artifact**. Consumer ở release cũ vẫn cần stub của producer version tương ứng; CI trong monorepo không tự chứng minh mọi binary đang chạy production đã được cập nhật.

## 7. Mô hình E: hybrid — source theo ownership, artifacts phân phối tập trung

Mô hình thường thực tế ở tổ chức đã có nhiều service:

~~~mermaid
flowchart TD
    A["Producer repository: canonical DSL"] --> B["Producer CI + Contract Verifier"]
    C["Consumer proposal / PR"] --> A
    B --> D["Immutable stub JAR"]
    D --> E["Maven artifact repository"]
    D --> F["Provenance + compatibility metadata"]
    E --> G["Consumer CI + Stub Runner"]
    F --> H["Catalog / contract registry / portal"]
    G --> I["Consumer test report"]
    H --> I
~~~

Trong mô hình này:

- **Git của producer** giữ source contract được chấp nhận.
- **Consumer** gửi proposal qua PR hoặc workflow đã thống nhất.
- **Producer CI** sinh tests, chạy verification và đóng gói stubs.
- **Maven repository** phân phối JAR `stubs` bất biến.
- **Registry/catalog** có thể lưu owner, consumers, deprecation, compatibility decision và provenance.

Đây thường là điểm cân bằng tốt: producer ownership rõ, consumer tham gia được, Stub Runner dùng artifact chuẩn, và platform team có metadata tổng quan.

## 8. Contract repository khác artifact repository và contract broker

Ba khái niệm dễ bị nhầm:

| Thành phần | Lưu gì? | Làm gì? | Có tự xác minh producer không? |
| --- | --- | --- | --- |
| **Git contract repository** | Groovy/YAML DSL, review history, ownership files. | Source control và collaboration. | Không; cần producer verification pipeline. |
| **Maven artifact repository** | JAR/POM, classifier `stubs`, version/checksum. | Phân phối artifact cho Stub Runner/build tools. | Không; chỉ lưu artifact đã publish. |
| **Contract broker/registry** | Contract metadata, consumer/provider relationships, verification results tùy sản phẩm. | Governance, compatibility visibility, workflow và reporting. | Tùy nền tảng/integration; không mặc định. |

**Spring Cloud Contract hỗ trợ sinh và phân phối stubs**, nhưng không bắt buộc một broker trung tâm để hoạt động. Một tổ chức có thể dùng Git + Maven repository là đủ. Nếu bổ sung contract broker/registry bên ngoài, cần định nghĩa rõ dữ liệu nào được đồng bộ, ai là source of truth và cách xác minh trạng thái.

Đừng dùng từ `broker` cho mọi Maven repository. Repository tải JAR không nhất thiết biết consumer nào đã xác minh với JAR đó, cũng không tự đưa ra compatibility decision.

## 9. Ma trận lựa chọn mô hình lưu trữ

| Tiêu chí | Producer repo | Consumer-driven repo | Central repo | Monorepo | Hybrid |
| --- | --- | --- | --- | --- | --- |
| Ownership API | Rõ nếu producer owner | Cần producer acceptance | Cần owner metadata | Theo module/path | Rõ ở source, tập trung ở metadata |
| Consumer đề xuất | Qua PR vào producer | Tự nhiên | Tự nhiên | Cùng PR hoặc path proposal | Qua PR/workflow |
| Tính nguyên tử code + contract | Cao | Thấp nếu khác repo | Thấp hơn nếu producer code tách | Cao | Source vẫn gần producer |
| Governance tập trung | Trung bình | Tùy cách tổ chức | Cao | Qua repo policy | Cao ở metadata |
| Vận hành ban đầu | Thấp | Trung bình | Cao | Tùy monorepo | Trung bình |
| Phân phối stub | Maven repo | Maven repo sau producer verify | Maven repo | Maven repo hoặc CI artifact | Maven repo |
| Phù hợp team độc lập | Tốt nếu phối hợp PR | Tốt khi CDC mạnh | Tốt khi platform team đủ năng lực | Tùy cấu trúc | Rất tốt khi có quy trình |

### Gợi ý quyết định

- **Một vài service, một producer owner rõ:** bắt đầu ở producer repository.
- **Consumer có yêu cầu API chủ động, release độc lập:** thêm consumer-driven proposal workflow.
- **Nhiều team, nhiều domain, audit/ownership phức tạp:** cân nhắc central metadata/contract repository.
- **Nhiều service cùng release/train hoặc thay đổi thường xuyên phối hợp:** monorepo có thể đơn giản hóa review.
- **Tổ chức lớn, cần cả ownership phân tán và governance tập trung:** chọn hybrid.

Không chọn central repository chỉ vì muốn “có một nơi lưu tất cả”. Hãy chọn khi có người vận hành, quy tắc ownership và lợi ích phối hợp đủ lớn.

## 10. Ai sở hữu contract?

Một contract có thể được nhiều nhóm sử dụng, nhưng cần **một producer owner chịu trách nhiệm cuối cùng cho behavior được công bố**.

| Vai trò | Trách nhiệm |
| --- | --- |
| **Producer owner** | Xác nhận behavior, implementation, generated tests và version support. |
| **Consumer owner** | Nêu request/response/message needs, kiểm client/listener và xác nhận compatibility. |
| **API/domain owner** | Quyết định semantics, schema evolution, deprecation và breaking changes. |
| **Platform/build team** | Duy trì plugin versions, artifact repository, CI templates và provenance. |
| **Security owner** | Review auth, sensitive fields, data exposure và secret handling khi liên quan. |
| **Release owner** | Xác nhận gates, promotion, deployment evidence và rollback. |

Với nhóm nhỏ, một người có thể giữ nhiều vai trò. Điều quan trọng là **decision owner được nêu rõ** trong PR và quy trình.

### 10.1. Ownership metadata

Có thể lưu file ownership trong Git, ví dụ:

~~~yaml
service: order-service
contractOwner: team-orders
apiOwner: commerce-platform
consumers:
  - billing-service
  - analytics-batch
channels:
  - http
  - messaging
support:
  - api-v1
review:
  requiredProducerApproval: true
  requiredConsumerReviewForBreakingChanges: true
~~~

Đây là **metadata governance minh họa**, không phải schema Spring Cloud Contract. Không thêm file này vào bài contract YAML nếu task/project không yêu cầu; nó có thể sống ở catalog/ownership directory tùy mô hình.

## 11. Quy trình đề xuất thay đổi contract

Một thay đổi tốt đi qua các bước:

1. **Nêu nhu cầu:** consumer hoặc producer mô tả behavior cần thêm/sửa và lý do.
2. **Xác định affected consumers:** kiểm consumer inventory, version đang chạy và owner.
3. **Tạo proposal:** chỉnh contract DSL hoặc mở PR draft với ví dụ request/response/message.
4. **Review semantics:** required fields, types, enum, status, errors, headers, auth, ordering, retry và nullability.
5. **Phân loại compatibility:** additive, compatible theo policy, breaking hoặc chưa rõ.
6. **Producer acceptance:** owner xác nhận có thể cung cấp behavior và cách triển khai.
7. **Generated verification:** producer test được sinh và chạy trên implementation.
8. **Consumer verification:** Stub Runner tests chạy với artifact mới trên các consumer được hỗ trợ.
9. **Version/publish:** đóng gói stubs bất biến, ghi coordinates/checksum/provenance.
10. **Release/migration:** promote/deploy theo policy, giữ v1 hoặc deprecate có kế hoạch.
11. **Communicate:** ghi release note, consumer migration steps và thời hạn nếu có.

~~~mermaid
flowchart TD
    A["Consumer/producer nêu nhu cầu"] --> B["Xác định owner và consumers bị ảnh hưởng"]
    B --> C["Contract proposal PR"]
    C --> D["Review semantics + compatibility"]
    D --> E{"Breaking hoặc chưa rõ?"}
    E -->|Có| F["Thiết kế version/migration + consumer review"]
    E -->|Không| G["Producer acceptance"]
    F --> G
    G --> H["Generate + run producer verification"]
    H --> I{"Producer tests pass?"}
    I -->|Không| X["Sửa implementation/contract"]
    I -->|Có| J["Package immutable stubs"]
    J --> K["Consumer Stub Runner matrix"]
    K --> L{"Supported consumers pass?"}
    L -->|Không| Y["Block release / migration plan"]
    L -->|Có| M["Publish/promote + notify consumers"]
~~~

**Contract proposal chưa phải contract release**. PR có thể ở trạng thái draft cho tới khi producer owner chấp nhận và CI chứng minh implementation. Không cho consumer tải bản draft như một stub version chính thức.

## 12. Chọn contract-first hay implementation-first

Hai hướng đều có thể dùng:

### Contract-first

1. Consumer/producer cùng thống nhất contract trước.
2. Producer triển khai theo contract.
3. Generated tests kiểm implementation.
4. Consumer chạy Stub Runner với stub được sinh từ contract.

Phù hợp khi API mới, event schema mới hoặc nhiều team cần đồng thuận trước khi code.

### Implementation-first

1. Producer thay đổi code trong phạm vi có kiểm soát.
2. Cập nhật contract phản ánh behavior dự định được hỗ trợ.
3. Review contract diff như một API change.
4. Chạy producer verification và consumer compatibility tests.
5. Release theo gates.

Phù hợp với refactor nội bộ hoặc API hiện hữu đã có behavior rõ. Nhưng **không được viết contract sau khi code xong chỉ để test tự pass**; consumer owner vẫn phải xác nhận semantics.

### Hybrid theo mức rủi ro

Với thay đổi breaking, contract-first và consumer review thường có lợi. Với thay đổi nội bộ không đổi behavior, implementation-first có thể nhanh hơn. Với thêm field optional, vẫn cần kiểm policy unknown fields của các consumer.

## 13. Cấu trúc một contract proposal tốt

Một proposal nên trả lời:

| Mục | Nội dung |
| --- | --- |
| Problem | Consumer/business problem cần giải quyết. |
| Producer | Service và API/message owner. |
| Consumers | Các consumer hiện tại và consumer mới bị ảnh hưởng. |
| Scenario | Request, response hoặc message cụ thể. |
| Contract DSL | Groovy/YAML files và paths. |
| Semantics | Meaning của fields, units, timezone, enum, nullability. |
| Compatibility | Additive/compatible/breaking/unknown và lý do. |
| Test evidence | Producer generated tests, consumer Stub Runner results. |
| Versioning | Artifact version, API/event version, migration window. |
| Rollout | Thứ tự deploy producer/consumer, rollback. |
| Deprecation | Consumer nào phải migrate, deadline và owner. |

### 13.1. Mẫu mô tả PR

~~~markdown
## Mục đích
Mô tả nhu cầu consumer và behavior cần thay đổi.

## Producer / API
- Producer:
- Endpoint hoặc destination:
- Contract files:

## Consumers bị ảnh hưởng
- Consumer:
- Version đang hỗ trợ:
- Owner/reviewer:

## Thay đổi contract
- Request/message:
- Response/message:
- Fields/types/headers:
- Error scenarios:

## Compatibility
- [ ] Additive theo policy
- [ ] Backward compatible đã xác minh
- [ ] Breaking change
- [ ] Chưa rõ, cần review thêm

## Bằng chứng
- Producer generated tests:
- Consumer Stub Runner matrix:
- Stub coordinates/checksum:

## Release và migration
- Version:
- Rollout order:
- Deprecation date:
- Rollback:
~~~

Đây là mẫu nội dung PR để đội áp dụng. Không phải file bắt buộc do Spring Cloud Contract tạo.

## 14. Review contract diff theo semantics

Không chỉ review số dòng Groovy/YAML thay đổi. Hãy so:

- HTTP method/path/query/header.
- Status code và error response.
- Required/optional/null fields.
- JSON types và enum values.
- Units, precision, timezone và ordering.
- Request validation và authorization.
- Message destination, event type, schema version, key/partition nếu có.
- Retry, idempotency, delivery semantics nếu contract bao gồm.

Ví dụ:

**Trước**

~~~json
{
  "id": 42,
  "amountMinor": 125000,
  "currency": "VND"
}
~~~

**Sau**

~~~json
{
  "id": 42,
  "amountMinor": "125000",
  "currency": "VND"
}
~~~

Diff JSON chỉ thay một cặp quote, nhưng đổi **number thành string** và có thể phá consumer typed DTO. Review phải nhận diện đây là breaking với client strict.

Ngược lại, đổi thứ tự khóa JSON object hoặc pretty-print không nhất thiết là thay đổi contract. Thêm field optional có thể additive, nhưng phải xem strict deserializer và schema policy của consumer.

## 15. Phân loại compatibility

| Thay đổi | Phân loại thường gặp | Điều kiện cần xác minh |
| --- | --- | --- |
| Thêm optional response field | Có thể additive | Consumer cũ bỏ qua unknown field? |
| Thêm required request field | Thường breaking cho consumer cũ | Client cũ có gửi field không? |
| Xóa response field đang dùng | Breaking | Consumer inventory và DTO usage. |
| Number thành String | Breaking với typed consumer | JSON schema/DTO/converter. |
| Thêm enum value | Có thể phá consumer enum strict | Unknown enum policy. |
| Đổi status 200 thành 202 | Có thể breaking về workflow | Consumer có hiểu async/pending không? |
| Đổi error code/body | Có thể breaking | Error decoder/business mapping. |
| Thay endpoint path | Breaking nếu không giữ alias/version cũ | Routing và consumer migration. |
| Đổi timezone/units | Có thể rất nghiêm trọng dù type không đổi | Domain semantics. |
| Thêm event header/schema version | Phụ thuộc consumer policy | Listener và schema registry. |
| Đổi destination/topic | Thường breaking | Consumer subscription/routing. |
| Đổi thứ tự message | Breaking nếu ordering được cam kết | Partition/key/sequence semantics. |

**Không có quy tắc “mọi field thêm vào đều tương thích”.** Compatibility là quan hệ giữa thay đổi, consumer behavior và policy schema của tổ chức.

## 16. Versioning: contract, service và stub artifact

Nên phân biệt:

1. **Service version:** version của ứng dụng producer.
2. **Stub artifact version:** version Maven dùng để consumer tải mappings.
3. **API version:** version được công bố cho consumer, ví dụ `/api/v1` và `/api/v2`.
4. **Message schema/event version:** version trong payload/header, nếu protocol dùng.
5. **Git commit:** identity của source contract và implementation.

Ví dụ:

~~~text
Producer:
  com.acme:order-service:1.4.2

Stub artifact:
  com.acme:order-service:1.4.2:stubs

HTTP API:
  /api/v1/orders/{id}

Message:
  eventType = OrderCreated
  schemaVersion = 1

Source:
  Git SHA = <full-commit-sha>
~~~

Một artifact `stubs` có thể được gắn với version producer theo cách build đã cấu hình. Nếu nhiều API/event versions cùng được hỗ trợ, contract source cần tổ chức rõ và build artifact phải chứa đúng mappings được publish.

**Không dùng Git branch name như version artifact bất biến**. Branch có thể di chuyển; release version/checksum/source SHA mới giúp consumer test tái lập.

## 17. Deprecation và quy trình loại bỏ contract cũ

Khi producer muốn bỏ API/event v1:

1. Xác định consumer inventory và owner.
2. Công bố deprecation và thời điểm dự kiến loại bỏ.
3. Thêm v2 mà không làm v1 thay đổi ngoài cam kết.
4. Cung cấp contract/stub v2 và migration notes.
5. Consumer cập nhật và chạy Stub Runner tests với v2.
6. Theo dõi runtime usage/telemetry của v1.
7. Chỉ loại bỏ v1 khi các consumer được hỗ trợ đã migrate hoặc có exemption được phê duyệt.
8. Giữ lại artifact/reports cũ theo retention policy để điều tra lịch sử.

Không xóa contract source cũ chỉ vì không còn nằm trong PR mới. Lịch sử contract là bằng chứng cho release trước và có thể cần khi tái hiện incident.

## 18. Quy trình cross-repository khi consumer đề xuất thay đổi

Giả sử Billing cần thêm field `paymentReference` từ Order Service.

Một workflow rõ:

1. Billing tạo issue/proposal nêu business reason, expected type, required/optional và consumer fallback.
2. Billing mở PR draft trong consumer repo hoặc proposal area, kèm contract example.
3. Order owner review semantics, security/data exposure và tác động tới các consumer khác.
4. Nếu chấp nhận, contract source canonical được cập nhật trong producer repo hoặc central source theo policy.
5. Producer implementation được cập nhật.
6. Producer CI sinh tests, chạy verification, đóng gói stubs.
7. Consumer CI tải artifact version mới, chạy client thật.
8. Các consumer liên quan chạy compatibility matrix.
9. Merge/publish/promote theo release policy.
10. Billing deploy theo migration plan và thông báo hoàn tất.

**Không để hai PR cross-repo cùng merge mà không có điểm đồng bộ**. Có thể dùng draft PR, release candidate artifact hoặc coordinated merge window. Điều quan trọng là producer và consumer biết rõ commit/artifact nào là candidate đang được kiểm.

## 19. Workflow khi contract nằm trong central repository

Nếu central repo là source of truth:

1. Consumer/producer mở PR vào contract repo.
2. CODEOWNERS/approval rule yêu cầu producer owner review.
3. PR CI kiểm DSL parse, naming, schema/policy và diff.
4. Producer pipeline lấy đúng commit/tag contract đã được chấp nhận.
5. Producer generated tests chạy trên implementation commit tương ứng.
6. Producer publish stub artifact gắn với contract revision.
7. Consumer matrix dùng artifact đó.
8. Registry/manifest ghi central contract commit, producer SHA và stub checksum.

Điểm cần tránh: producer build lấy contract từ **branch head đang thay đổi** thay vì commit/tag đã pin. Build cần reproducible: source code và contract revision phải được xác định trước khi chạy.

## 20. Workflow khi contract nằm trong producer repository

Một PR điển hình:

~~~text
PR #482 — Add payment reference to paid order response

Changed:
  - OrderController / response mapper
  - contracts/orders/get-paid-order.groovy
  - BaseContractTest fixture

Required reviews:
  - Team Orders producer owner
  - Billing consumer owner

CI:
  - contract discovery / generation
  - generated producer verification
  - package stubs
  - Billing Stub Runner compatibility

Outputs:
  - producer commit SHA
  - stub artifact version + checksum
  - producer test report
  - consumer test report
~~~

Contract diff được review cùng implementation diff. Nếu thêm field nhạy cảm, security/data owner cũng review. Nếu thay đổi breaking, PR phải có versioning/migration plan.

## 21. Git policy: branch, CODEOWNERS và protection

Một policy thực tế:

- Contract source nằm trong branch protection tương tự code.
- Thư mục contracts có **CODEOWNERS** trỏ tới producer API owner.
- Breaking change yêu cầu consumer owner approval.
- PR template yêu cầu compatibility classification.
- CI chạy parser/generator và producer tests.
- Main/release branch không chứa contract chưa qua review.
- Tag release gắn với source commit; artifact coordinates không bị overwrite.
- Generated source/output không được chỉnh thủ công nếu generator có thể tái tạo.

Ví dụ CODEOWNERS minh họa:

~~~text
/src/test/resources/contracts/ @team-orders-api
/src/test/resources/contracts/messaging/ @team-events
~~~

Đường dẫn/username phải khớp repository và team thực tế. CODEOWNERS giúp yêu cầu review, nhưng **không tự thay thế compatibility analysis** hoặc kiểm consumer tests.

## 22. CI checks theo từng loại repository

| CI check | Producer repo | Consumer repo | Central contract repo |
| --- | --- | --- | --- |
| DSL parse/validate | Có | Nếu consumer lưu proposal | Có |
| Generated producer tests | Có | Không | Chỉ khi pipeline checkout producer implementation |
| Stub packaging | Có | Không | Không tự có |
| Stub Runner test | Có thể chạy consumer matrix | Có | Có thể trigger downstream |
| Consumer DTO/business assertions | Không nhất thiết | Có | Không tự có |
| Ownership/approval | Producer owner | Consumer owner | Producer + consumer owners |
| Compatibility report | Producer release gate | Consumer result | Có thể tổng hợp |
| Provenance | Producer SHA/test/stub | Consumer SHA/stub checksum | Contract commit/revision |

**Không gán mọi trách nhiệm cho central repository**. Contract repo có thể parse và lint DSL, nhưng muốn chạy producer verification cần producer application/base test và môi trường test phù hợp.

## 23. Artifact repository và chính sách bất biến

JAR `stubs` là đầu ra build được consumer dùng. Một policy phù hợp:

- Release coordinates bất biến; không overwrite cùng version.
- Snapshot chỉ dùng trong môi trường dev/test với hiểu biết về tính mutable.
- Consumer pin version cụ thể; không dùng `latest` cho release gate.
- Ghi checksum SHA-256 từ JAR thật.
- Giữ POM/metadata và provenance theo policy.
- Staging repository cho phép consumer test trước khi promote release.
- Retention đủ dài để tái hiện các consumer build cũ.

Ví dụ:

~~~text
com.acme:order-service:1.4.2:stubs
SHA-256: <actual-jar-checksum>
Producer Git SHA: <full-commit-sha>
Producer CI run: <run-id>
Contract revision: <git-commit-or-tag>
~~~

Các placeholder phải được pipeline thay bằng giá trị thật. **Maven repository phân phối bytes, không tự quyết định bytes đó có đúng source hay được consumer test hay chưa**; provenance phải nối các bước.

## 24. Contract broker/registry có cần thiết không?

Một contract registry hoặc broker có thể hữu ích nếu tổ chức cần:

- Tra cứu producer/consumer relationships.
- Xem verification status theo version.
- Theo dõi compatibility matrix.
- Quản lý deprecation/consumer migration.
- Cung cấp portal và API discovery.
- Tích hợp approval/notification workflow.

Nhưng nó cũng tạo thêm:

- Hạ tầng và chi phí vận hành.
- Identity/permissions/retention.
- Đồng bộ Git source, artifact và verification results.
- Quy trình xử lý dữ liệu stale/inconsistent.
- Trách nhiệm platform team.

**Spring Cloud Contract không yêu cầu phải triển khai một contract broker riêng** để dùng Groovy/YAML DSL, generated tests, JAR stubs và Stub Runner. Chỉ bổ sung registry khi vấn đề governance/visibility thực sự cần giải pháp đó. Nếu chỉ cần lưu source và phân phối stubs, Git + Maven repository có thể đủ.

## 25. Security và quyền truy cập theo mô hình lưu trữ

| Tài sản | Quyền gợi ý |
| --- | --- |
| Producer contract source | Producer owner write; consumer/platform read; PR approval theo policy. |
| Consumer proposal | Consumer owner write; producer owner review/accept. |
| Central contract repo | CODEOWNERS/path ownership; merge protection; audit. |
| Maven release stubs | CI publisher write; consumer CI read; immutable release. |
| Staging artifacts | CI publisher write; compatibility jobs read; cleanup có kiểm soát. |
| Registry metadata | Owner update; platform maintain; read theo quyền tổ chức. |
| Secrets/credentials | Secret manager/CI identity; không nằm trong Git/contract/stub. |

Contract là dữ liệu chia sẻ rộng, nên **không đặt token, password, customer PII hoặc sample production payload nhạy cảm** trong DSL. Dùng synthetic fixtures. Khi contract chứa header authorization, mô tả dạng matcher/placeholder phù hợp, không lưu bearer token thật.

## 26. Những anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách điều chỉnh |
| --- | --- | --- |
| Mỗi consumer giữ một bản contract riêng, không có canonical source | Các bên kiểm trên behavior khác nhau. | Hợp nhất proposal vào source có producer acceptance. |
| Central repo không có owner | Mọi PR bị chờ hoặc merge sai semantics. | CODEOWNERS và producer decision owner. |
| Dùng Maven repository làm nơi review DSL | Thiếu diff/review context và ownership. | Source ở Git; Maven repository phân phối artifact. |
| Consumer tải `latest` stubs | Test không tái lập. | Pin version/checksum. |
| Sửa mapping trong JAR sau publish | Artifact không còn tương ứng source/provenance. | Build version mới. |
| Producer test tự pass bằng fixture giả | Không kiểm implementation. | Base test kích hoạt controller/publisher thật. |
| Chỉ có producer contract tests | Không kiểm client/listener. | Consumer Stub Runner tests. |
| Chỉ có consumer tests với mock tự viết | Không kiểm stub artifact thực. | Dùng Stub Runner và artifact đúng version. |
| Contract source ở branch head không pin | Build có thể lấy nội dung khác giữa các lần chạy. | Pin commit/tag. |
| Không ghi consumer inventory | Không biết ai bị ảnh hưởng. | Metadata owner/consumer list và runtime discovery. |
| Xóa v1 ngay khi v2 sẵn sàng | Consumer cũ bị phá. | Deprecation và expand–migrate–contract. |
| Đổi DSL mà không phân loại compatibility | Review bỏ sót breaking change. | Contract diff review và consumer matrix. |
| Mọi thay đổi đều cần toàn bộ tổ chức phê duyệt | Quy trình chậm, approval fatigue. | Approval theo scope/risk/ownership. |

## 27. Chọn mô hình theo mức trưởng thành

Một lộ trình tiến hóa có thể là:

**Giai đoạn 1 — Team sở hữu một service**

- Lưu DSL trong producer repo.
- Sinh producer tests.
- Publish JAR `stubs` vào Maven repository.
- Consumer dùng Stub Runner với version pin.

**Giai đoạn 2 — Nhiều consumer**

- Thêm consumer owners vào review.
- Lập consumer inventory.
- Chạy compatibility matrix cho các consumer được hỗ trợ.
- Dùng staging artifact và release notes.

**Giai đoạn 3 — Nhiều team/domain**

- Chuẩn hóa ownership metadata, CODEOWNERS và proposal template.
- Có thể tạo central contract index/repository cho visibility.
- Tích hợp CI result/provenance.
- Đặt deprecation và versioning policy thống nhất.

**Giai đoạn 4 — Governance toàn tổ chức**

- Cân nhắc registry/broker hoặc developer portal.
- Tự động tổng hợp consumer relationships/verification status.
- Có policy approval theo risk và domain.
- Audit artifact, release và runtime deployment identity.

Không cần nhảy thẳng tới giai đoạn 4. Chọn mức tối thiểu giải quyết được rủi ro hiện tại, rồi mở rộng khi chi phí phối hợp tăng.

## 28. Bài thực hành: thiết kế workflow cho Order và Billing

Giả sử tổ chức có Order Service và ba consumer: Billing, Analytics Batch, Notification. Billing cần thêm `paymentReference` vào response đơn đã thanh toán.

### Phần A — Chọn nơi lưu source

1. Vẽ topology repository hiện tại: producer repo, các consumer repo, artifact repository và CI.
2. Xác định producer API owner và owner của từng consumer.
3. Chọn một mô hình: producer repo, consumer-driven proposal, central repo, monorepo hoặc hybrid.
4. Viết lý do theo ownership, release independence, governance, vận hành và audit.
5. Xác định canonical source và nơi lưu stub artifact.

### Phần B — Đề xuất thay đổi

1. Billing mở proposal nêu lý do và cách sử dụng `paymentReference`.
2. Xác định field là required hay optional, type/format/nullability.
3. Xác định Analytics và Notification có bị ảnh hưởng không.
4. Producer owner review security/data exposure và semantics.
5. Phân loại thay đổi là additive hay breaking theo consumer policy.
6. Chọn contract source canonical và tạo PR.

### Phần C — Producer verification

1. Cập nhật Groovy contract trong đúng repository đã chọn.
2. Cập nhật base test fixture/implementation để field có mặt.
3. Chạy generated producer tests.
4. Thử mutation: bỏ field hoặc đổi type để xác nhận test FAIL.
5. Package JAR `stubs` version mới.
6. Ghi Git SHA, CI run, report và checksum.

### Phần D — Consumer compatibility

1. Billing CI tải stub version mới và chạy client thật qua Stub Runner.
2. Analytics CI chạy test nếu có phụ thuộc schema.
3. Notification CI xác nhận behavior không bị ảnh hưởng hoặc đánh dấu NOT TESTED nếu chưa có bằng chứng.
4. Ghi consumer commit, stub coordinates/checksum và test report.
5. Nếu một consumer cũ fail, sửa client hoặc lập migration plan; không nới contract một cách vô căn cứ.

### Phần E — Release và truy vết

1. Publish vào staging repository.
2. Chỉ promote sau khi các gates bắt buộc đạt.
3. Build/promote producer image từ source/build đã được verification.
4. Deploy theo image digest.
5. Ghi release manifest và deployment revision.
6. Thực hiện incident drill: từ trace ID truy về image, producer CI, contract commit, stub checksum và consumer test.

**Deliverable của workshop:** một ADR ngắn giải thích lựa chọn storage model; một PR proposal mẫu; một compatibility matrix; một release manifest; và bằng chứng CI cho producer/consumer.

## 29. Checklist quyết định

| Câu hỏi | Nếu câu trả lời là… | Hướng chọn |
| --- | --- | --- |
| Producer owner có rõ và API chủ yếu do một team quản lý? | Có | Producer repository là điểm bắt đầu tốt. |
| Consumer thường phải chủ động đề xuất behavior? | Có | Bổ sung consumer-driven proposal workflow. |
| Nhiều domain cần xem ownership/compatibility toàn cục? | Có | Central index/registry có thể hữu ích. |
| Nhiều service thay đổi phối hợp trong cùng commit? | Có | Cân nhắc monorepo. |
| Các team release độc lập nhưng cần governance tập trung? | Có | Hybrid: source phân tán, metadata/artifacts tập trung. |
| Chỉ cần phân phối stubs cho Stub Runner? | Có | Maven artifact repository có thể đủ. |
| Cần biết consumer nào đã verify với stub nào? | Có | Lưu consumer CI result/provenance; cân nhắc registry. |
| Không có người vận hành central platform? | Có | Tránh thêm central service chưa có ownership. |

## 30. Câu hỏi tự kiểm tra

1. Contract source, generated tests/mappings và published stub artifact khác nhau thế nào?
2. Vì sao producer repository là lựa chọn tự nhiên của Spring Cloud Contract?
3. Consumer-driven contract thay đổi ai khởi xướng và review như thế nào?
4. Vì sao consumer proposal chưa phải contract release chính thức?
5. Central contract repository đem lại lợi ích gì và tạo bottleneck nào?
6. Monorepo có loại bỏ nhu cầu version hóa stub artifact không?
7. Mô hình hybrid tách source ownership và artifact distribution ra sao?
8. Maven artifact repository khác contract broker/registry như thế nào?
9. Spring Cloud Contract có bắt buộc một contract broker không?
10. Ai chịu trách nhiệm cuối cùng về behavior của producer contract?
11. Consumer inventory giúp quyết định compatibility như thế nào?
12. Vì sao một thay đổi thêm field optional vẫn có thể phá strict consumer?
13. Contract-first và implementation-first phù hợp với loại thay đổi nào?
14. PR proposal cần ghi những thông tin gì để review semantics?
15. CODEOWNERS có thể bảo vệ điều gì và không thể thay thế điều gì?
16. Vì sao build cần pin central contract commit/tag?
17. Stub artifact version, API version, message schema version và Git SHA khác nhau thế nào?
18. Vì sao không dùng `latest` stubs cho release gates?
19. Quy trình deprecation v1 nên đi qua những bước nào?
20. Khi nào nên thêm central registry thay vì chỉ dùng Git + Maven repository?
21. Vì sao cần ghi consumer chưa kiểm là NOT TESTED?
22. Những dữ liệu nào cần lưu để truy từ deployment về contract source và test report?

**Ghi nhớ:** **Chọn nơi lưu contract là quyết định về ownership và workflow, không chỉ là quyết định về thư mục.** Với Spring Cloud Contract, hãy giữ Groovy/YAML source ở một Git location có producer owner rõ; cho consumer một đường đề xuất và review behavior; dùng Contract Verifier để kiểm implementation; đóng gói JAR `stubs` bất biến để Stub Runner phân phối; và lưu consumer results/provenance để biết ai đã kiểm version nào. Producer repo thường là điểm bắt đầu đơn giản; consumer-driven proposal, central governance, monorepo hoặc hybrid được bổ sung theo topology và mức trưởng thành. Một thay đổi chỉ nên trở thành contract release sau khi owner chấp nhận, producer verification đạt, consumer compatibility được đánh giá và version/artifact được truy vết.
