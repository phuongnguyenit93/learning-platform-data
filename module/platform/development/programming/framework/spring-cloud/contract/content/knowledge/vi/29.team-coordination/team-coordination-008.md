# Giữ thay đổi hợp đồng và triển khai producer có thể truy vết

Trong một hệ thống microservices, **consumer** có thể gặp lỗi ngay sau khi **producer** được triển khai: một trường JSON đổi tên, lỗi 404 có schema khác, header bị bỏ, destination của message đổi hoặc bản producer đang chạy không còn phù hợp với JAR `stubs` mà consumer đã kiểm. Vấn đề không chỉ là “test có pass hay không” mà là **trả lời được ai đã yêu cầu thay đổi, hợp đồng nào đổi, commit nào được xác minh, artifact nào được phát hành, producer release nào thực sự được triển khai, và consumer nào bị ảnh hưởng**.

Đó là **traceability (khả năng truy vết)**. Trong **Spring Cloud Contract**, traceability cần nối được nguồn hợp đồng **Groovy/YAML DSL**, **generated producer tests**, **stub artifact**, **Stub Runner consumer tests**, bản triển khai và dữ liệu quan sát vận hành. Một đường liên kết bị đứt — ví dụ artifact `stubs` xuất từ build khác với Docker image đã triển khai — có thể khiến hai nhóm tin rằng đã kiểm cùng một phiên bản trong khi thực tế không phải.

Bài thuộc chương **Phối hợp nhiều nhóm** của mô-đun **SPRING_CLOUD_CONTRACT**. Mô-đun hướng dẫn kiểm thử hợp đồng giữa producer và consumer qua HTTP hoặc thông điệp, sinh test producer, phát hành stub, dùng Stub Runner và tích hợp CI để phát hiện API không tương thích. Trọng tâm ở đây là **quy trình nhiều nhóm có bằng chứng**, từ đề xuất thay đổi hợp đồng tới rollout producer, rollback và điều tra sự cố; không chỉ là thêm một nhãn version vào file.

## 1. Traceability cần trả lời những câu hỏi nào?

Hãy tưởng tượng **Order Service** là producer và **Billing Service** là consumer. Billing đột nhiên không giải mã được `GET /api/orders/42` trên production.

Một hệ thống có thể truy vết sẽ trả lời được:

| Câu hỏi | Loại bằng chứng cần có |
| --- | --- |
| **Điều gì đổi?** | Contract diff ở Groovy/YAML, PR, review và mô tả thay đổi semantics. |
| **Ai phê duyệt?** | API owner, các consumer owners liên quan và quyết định tương thích. |
| **Lúc nào đổi?** | Thời điểm commit/merge, artifact publish, deploy start/end và rollout. |
| **Đổi trong bản nào?** | Producer Git SHA, release version, image digest, stub artifact coordinates. |
| **Đã kiểm gì trước khi phát hành?** | Generated producer test reports, consumer stub tests và CI run ID. |
| **Production đang chạy bản nào?** | Deployment record/manifest và runtime build identity. |
| **Consumer đang dùng giao tiếp nào?** | Bản consumer triển khai, version contract, access logs/traces khi có. |
| **Rollback về đâu?** | Bản image/artifact trước đó đã biết và kế hoạch rollback có kiểm chứng. |

**Traceability không đồng nghĩa logging thật nhiều.** Cần một tập dấu vết **đúng nguồn, gắn kết được, ổn định và không lộ secrets/PII**. Một log ghi “release 2.0” nhưng không chỉ được Git commit hoặc image digest là chưa đủ cho điều tra đáng tin.

## 2. Chuỗi truy vết lý tưởng

Một thay đổi hợp đồng nên có đường đi:

~~~mermaid
flowchart TD
    A["Yêu cầu thay đổi / issue có owner"] --> B["PR sửa Groovy/YAML contract"]
    B --> C["Code review + đánh giá consumer impact"]
    C --> D["Merge commit Git SHA xác định"]
    D --> E["Producer CI: generate + run contract tests"]
    E --> F{"Verification đạt?"}
    F -->|Không| X["Chặn publish/deploy"]
    F -->|Có| G["Build artifact stubs + container image"]
    G --> H["Lưu coordinates, checksums và CI run ID"]
    H --> I["Publish bất biến vào artifact registry"]
    I --> J["Deploy producer từ image digest đã xác minh"]
    J --> K["Deployment record + runtime build identity"]
    K --> L["Metrics/traces và consumer checks"]
    L --> M["Tái dựng được đường thay đổi khi cần điều tra"]
~~~

Điểm quan trọng nhất: **một mã nguồn/commit đã qua producer verification phải dẫn tới chính những artifacts và deployment được ghi nhận**. Nếu build lại từ branch `main` ở một thời điểm khác trong job deploy, có thể thu được bytes khác. Khi đó, cần chứng minh bản build lại tương ứng đúng commit và đủ điều kiện kiểm hoặc, tốt hơn, **promote chính artifact đã được xác minh**.

### 2.1. Bốn nhóm danh tính không thể thay thế nhau

| Danh tính | Ví dụ | Định danh cái gì? |
| --- | --- | --- |
| **Contract identity** | `GET /api/v1/orders/{id}`, `OrderCreated:v2` | Giao tiếp và version/semantics được cam kết. |
| **Source identity** | Git SHA `a1b2c3d...`, PR `#184` | Phiên bản source/contract được review. |
| **Build artifact identity** | `com.acme:order-service:2.1.0:stubs` và checksum | Bộ stub được publish từ một lần build. |
| **Deployment identity** | Image digest `sha256:...`, env `prod-eu`, rollout ID | Bản producer thực tế chạy ở một môi trường/vùng. |

Một artifact có version `2.1.0` **không tự chứng minh** môi trường production đang chạy source/contract nào. Một Git SHA **không tự nói** container image đã được deploy ở những region nào. Cần **liên kết có thể kiểm chứng** giữa các loại danh tính.

## 3. Ví dụ xuyên suốt: bổ sung trường currency

Ban đầu Order Service công bố:

~~~http
GET /api/orders/42
Accept: application/json
~~~

~~~json
{
  "id": 42,
  "status": "PAID",
  "amountMinor": 125000
}
~~~

Billing muốn bổ sung `currency` để xử lý đơn hàng đa tiền tệ:

~~~json
{
  "id": 42,
  "status": "PAID",
  "amountMinor": 125000,
  "currency": "VND"
}
~~~

Đây là **thay đổi có thể tương thích** nếu consumer cũ cho phép trường JSON bổ sung, trường cũ giữ nguyên tên/kiểu/ý nghĩa và contract không cấm extra fields. Nhưng **không thể kết luận “thêm field luôn an toàn”**: client dùng strict deserializer, JSON schema đóng, chữ ký payload hoặc logic kiểm số trường có thể bị ảnh hưởng.

Vì vậy, quyết định thay đổi cần có:

1. Yêu cầu nghiệp vụ và **định nghĩa currency** (ISO code, giá trị hợp lệ, tương tác với `amountMinor`).
2. Thông báo cho **các nhóm consumer** đang dùng API.
3. Hợp đồng producer được cập nhật và **producer tests** xác minh.
4. **Consumer Stub Runner tests** với artifact mới, gồm consumer cũ và consumer mới nếu còn hỗ trợ.
5. Một release producer có **source SHA, stub artifact và image digest** liên kết với nhau.
6. Bằng chứng bản producer đã triển khai, quan sát lỗi parse và kết quả canary.

Ngược lại, đổi `amountMinor` thành `amount.minor` và xóa field cũ là **breaking change** với nhiều consumers. Phải version hóa hoặc thực hiện expand–migrate–contract có kiểm soát, không coi một test xanh ở consumer mới là đủ.

## 4. Ownership: ai sở hữu hợp đồng và ai xác nhận thay đổi?

Trong consumer-driven contracts, consumer thường mô tả **nhu cầu giao tiếp** còn producer chịu trách nhiệm **chứng minh implementation đáp ứng**. Nhưng mô hình sở hữu file có thể khác nhau: hợp đồng lưu trong producer repo, consumer repo hay một repository chung. Điều bất biến là **quyền quyết định và trách nhiệm phải rõ**.

| Công việc | Producer team | Consumer team | Platform/SRE |
| --- | --- | --- | --- |
| Định nghĩa public API và tương thích | **Accountable** | Consulted | Consulted |
| Đề xuất trường/hành vi mới | Reviewed | Có thể **Responsible** cho nhu cầu | Informed |
| Chấp nhận thay đổi contract DSL | Approver theo ownership | Review những phần tác động | Hỗ trợ policy |
| Tạo generated producer tests | **Responsible** | Informed | Hỗ trợ CI tooling |
| Phát hành `stubs` đúng version | **Responsible** | Dùng artifact | Repository/tooling |
| Chạy consumer tests với Stub Runner | Hỗ trợ khi không tương thích | **Responsible** | Hỗ trợ runner/network |
| Quyết định rollout production | Product/API owner + release authority | Xác nhận readiness | **Responsible** vận hành |
| Theo dõi và rollback | Cùng SRE | Theo dõi tác động consumer | Điều phối sự cố |

Bảng là **mô hình trách nhiệm minh họa**, không phải cơ cấu nhân sự bắt buộc. Một tổ chức có thể dùng RACI khác, nhưng mỗi quyết định cần **owner, người review và nơi ghi bằng chứng**.

**Chỉ gắn CODEOWNERS trên Git không thay cho trao đổi tác động consumer**. Một PR được một producer reviewer duyệt vẫn có thể phá consumer ngoài nhóm nếu không có cơ chế phát hiện dependency và notification.

## 5. Hợp đồng phải là nguồn có thể review trong version control

Ví dụ trong Order Service:

~~~text
order-service/
├── src/
│   └── test/
│       ├── java/com/acme/orders/ContractTestBase.java
│       └── resources/contracts/
│           └── orders/
│               ├── get_paid_order.groovy
│               └── order_not_found.groovy
├── pom.xml
└── ... producer source
~~~

Tệp `get_paid_order.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name 'shouldReturnPaidOrder'
    description 'Order Service trả dữ liệu thanh toán đã công bố'

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

**Ý nghĩa của truy vết nguồn:** commit sửa `currency` còn chứa hoặc trỏ được tới thay đổi producer implementation, thông báo API và test cần thiết. Nhờ vậy, khi cần điều tra, nhóm có thể xem **diff chính xác** thay vì chỉ biết artifact release có tên “new order API”.

### 5.1. YAML DSL cho cùng yêu cầu

~~~yaml
description: Order Service trả dữ liệu thanh toán đã công bố
request:
  method: GET
  url: /api/orders/42
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    status: PAID
    amountMinor: 125000
    currency: VND
~~~

Groovy và YAML là **hai cách diễn đạt cùng một hợp đồng**. Trong một build, chỉ giữ **một dạng có hiệu lực** cho cùng tình huống, tránh sinh test/mappings trùng. Nếu nhóm chuyển DSL, ghi rõ commit migration và kiểm đầu ra tương đương trước/sau, không âm thầm thay nguồn contract mà không kiểm.

### 5.2. Đặt tên contract đủ ổn định để so diff

Tệp `orders/get_paid_order.groovy`, tên `shouldReturnPaidOrder` và HTTP path là **ba loại định danh khác nhau**:

- Tên file giúp tổ chức và review; nên thay đổi có lý do.
- Contract name giúp đọc generated test/report; nên duy nhất và dễ nhận biết.
- Method/path/body/headers là **giao diện consumer thực sự phụ thuộc**; cần bảo vệ tương thích.

Không xem đổi tên file từ `get_paid_order.groovy` sang `get_order.groovy` là breaking API khi method/path không đổi. Nhưng việc rename có thể đổi generated class/đường dẫn report hoặc ảnh hưởng tooling nội bộ, nên vẫn cần xem tác động build.

## 6. Phân loại contract diff trước khi merge

PR nên có phần đánh giá thay đổi:

| Thay đổi | Phân loại dự kiến | Điều phải xác minh |
| --- | --- | --- |
| Thêm `currency` không bắt buộc, giữ field cũ | **Có thể tương thích** | Consumer cũ có chấp nhận extra field? |
| Xóa `amountMinor` | **Thường phá tương thích** | Consumer cũ có còn dùng? Có API v2/migration? |
| Đổi JSON number thành string | **Phá với nhiều consumers** | DTO/schema/matcher/decoder của consumer. |
| Thay HTTP `200` bằng `202` | **Có thể breaking** | Consumer branch xử lý status. |
| Đổi URL, HTTP method, required header | **Thường breaking** | Mã client và request matching. |
| Thêm một optional response header | Thường ít rủi ro | Header có ảnh hưởng signature/caching không? |
| Đổi enum `PAID` thành `SETTLED` | **Có thể breaking** | Consumer switch/map trên trạng thái. |
| Đổi array ordering đã cam kết | **Breaking nếu thứ tự có ý nghĩa** | Test sort/ranking/timeline. |
| Đổi semantic `amountMinor` nhưng giữ schema | **Breaking nghiệp vụ** | Đơn vị và logic tài chính của consumer. |
| Thay retry/timeout/rate limit contract | **Có thể breaking về hành vi vận hành** | Consumer resilience và SLA. |
| Đổi messaging destination/header/schemaVersion | **Có thể breaking** | Subscriptions, serializers, replay. |

**Diff text không tự quyết định tương thích.** Một thay đổi “chỉ thêm field” có thể ảnh hưởng strict parser; một thay đổi implementation lớn có thể giữ nguyên contract. Cần **đánh giá từ góc nhìn consumer**, dữ liệu thực tế và phiên bản được hỗ trợ.

### 6.1. Mẫu mô tả PR thay đổi contract

~~~text
Issue: ORDER-184 – bổ sung currency cho response Order
Producer owner: Order Team
Affected contract: GET /api/orders/{id}
Source PR: #184
Compatibility: additive, consumer review required
Known consumers: Billing, Checkout, Analytics batch
New behavior: currency = ISO 4217 code, e.g. VND
Legacy behavior: id/status/amountMinor giữ nguyên
Producer generated tests: required
Consumer tests: Billing/Checkout stubs new release
Deployment plan: canary -> production, rollback by image digest
Open risks: strict JSON parsers và batch chạy hàng tháng
~~~

Các ID trong ví dụ là **giả định**, không phải issue/PR tồn tại. Mục tiêu là có một **bản tóm tắt có thể review** và nối được tới CI/release, không chỉ một tiêu đề commit chung chung như “update contracts”.

## 7. Git history và version: nguồn dữ liệu cần giữ

Một commit Git nên phản ánh thay đổi có chủ đích:

~~~text
commit a1b2c3d4...
message: feat(order-contract): add currency to paid order response
source: src/test/resources/contracts/orders/get_paid_order.groovy
issue: ORDER-184
review: API owner + consumer representatives
~~~

**Không dùng `main` hay `latest` làm danh tính của một release đã xuất bản.** Branch có thể dịch chuyển; Git SHA xác định một snapshot source. Để truy vết chính xác, lưu **full SHA** trong metadata/provenance, còn SHA rút gọn chỉ để hiển thị.

Tuy nhiên, **Git SHA chưa đủ để định danh bytes artifact** nếu build phụ thuộc:

- Dependency versions mutable hoặc snapshot.
- Toolchain/JDK khác nhau giữa các runner.
- Plugin/dependency resolution từ repository không bất biến.
- Build timestamp hoặc nguồn sinh file không quyết định.
- Secret hoặc dữ liệu môi trường vô tình ảnh hưởng nội dung build.

Do đó nên ghi **cả source commit, build run ID và artifact digest/checksum**. Nếu có reproducible builds và provenance được kiểm chứng, việc đối chiếu càng mạnh; không giả định một SHA trong tên file tự bảo đảm nguồn gốc nếu chưa có quy trình kiểm.

## 8. Producer verification: bằng chứng gì là có giá trị?

Spring Cloud Contract plugin sinh **producer verification tests** từ Groovy/YAML DSL và chạy chúng trên producer thật trong môi trường test đã cấu hình.

Một quy trình Maven thường là:

~~~shell
./mvnw clean verify
~~~

Với Gradle:

~~~shell
./gradlew clean test
~~~

Đây là các lệnh **người học tự thực hiện trên dự án đã cấu hình**, không phải bằng chứng chúng đã được chạy trong bài này. Maven `verify` đi qua các phase test/package phù hợp với plugin; Gradle `test` chạy generated tests nếu plugin wiring đúng nhưng không nhất thiết publish stubs. Phải kiểm task/plugin version và reports thực tế.

**Bằng chứng verification tối thiểu:**

1. Plugin đã tìm thấy **đúng các contracts** thuộc release.
2. Generated tests đã được tạo vào test sources.
3. Test runner **thực sự thực thi** chúng; không có `skipTests` hoặc số test = 0 ngoài ý muốn.
4. Các test đạt ở đúng producer implementation/commit.
5. Reports chỉ ra test nào PASS/FAIL và CI run nào chạy.
6. Có kiểm các trường hợp quan trọng ngoài happy path, nếu API cam kết negative cases.

**`BUILD SUCCESS` riêng lẻ không đủ** khi có nguy cơ generator không tìm thấy contract hoặc test bị skip. Để gắn kết release, lưu report references trong **build record**, không chỉ chụp một dòng log.

### 8.1. Cố tình gây lỗi để chứng minh cổng kiểm

Trong một nhánh thử nghiệm, đổi implementation producer từ:

~~~json
{"id":42,"status":"PAID","amountMinor":125000,"currency":"VND"}
~~~

thành:

~~~json
{"id":42,"status":"PAID","amountMinor":"125000","currency":"VND"}
~~~

Nếu hợp đồng bảo vệ **kiểu JSON number**, generated producer tests phải **FAIL**. Nếu test vẫn xanh, hãy kiểm matcher/DSL và generated assertions; có thể chúng đang kiểm chuỗi hoặc quá lỏng. **Không sửa contract cho giống lỗi implementation chỉ để có test xanh** khi consumer vẫn cần số nguyên.

Một pipeline có thể truy vết tốt phải ghi rõ: commit nào gây regression, test nào phát hiện, tại sao build bị chặn và bản nào cuối cùng được publish sau khi sửa.

## 9. Từ producer tests tới stub artifact có danh tính

Khi producer verification đã đạt, producer đóng gói JAR có classifier `stubs`:

~~~text
com.acme:order-service:2.1.0:stubs
~~~

Một layout minh họa:

~~~text
order-service-2.1.0-stubs.jar
└── META-INF/
    └── com.acme/
        └── order-service/
            └── 2.1.0/
                ├── contracts/
                │   └── orders/get_paid_order.groovy
                └── mappings/
                    └── ... WireMock JSON mappings
~~~

Cấu trúc **thực tế** phụ thuộc plugin version và packaging configuration; mở artifact để xác minh. Với messaging-only stubs, có thể có hợp đồng message không đi kèm WireMock HTTP mappings cho những kịch bản đó.

**Mỗi release cần có các liên kết**:

| Thuộc tính | Ví dụ | Dùng khi |
| --- | --- | --- |
| `sourceCommit` | Full Git SHA | Tìm chính xác contract và implementation source. |
| `buildRunId` | `ci-2027-01-15-483` | Truy test logs, plugin outputs, approvals. |
| `artifactCoordinates` | `com.acme:order-service:2.1.0:stubs` | Consumer chọn đúng stub. |
| `artifactChecksum` | SHA-256 của JAR | Xác minh artifact bytes và phát hiện ghi đè. |
| `producerImageDigest` | `sha256:...` | Xác định container image được deploy. |
| `contractPaths` | `orders/get_paid_order.groovy` | Tìm nguồn thay đổi. |
| `verificationReport` | Link/ID báo cáo CI | Xác nhận tests đã chạy/đạt. |
| `publicationTime` | Timestamp có timezone | Phân biệt publish và deploy. |

**Không đủ chỉ ghi “order-service version 2.1.0”** trong wiki nếu cùng version có thể bị ghi đè hoặc image không khớp JAR stub. Phát hành release nên **bất biến** và có kiểm checksum/digest phù hợp.

## 10. Phân biệt version ứng dụng, stub, Docker image và API

| Danh tính | Ví dụ | Sự thật nó thể hiện |
| --- | --- | --- |
| API version | `/api/v1/orders/{id}` | Hợp đồng giao tiếp đang được consumer dùng. |
| Maven producer version | `order-service:2.1.0` | Một build/release ứng dụng. |
| Stub Maven version | `order-service:2.1.0:stubs` | Bộ hợp đồng/mappings đi cùng producer build đó. |
| Docker image tag | `order-service:2.1.0` | Một **tên tham chiếu** có thể mutable tùy registry policy. |
| Docker image digest | `sha256:abc...` | Nội dung image xác định theo digest. |
| Deployment revision | `orders-prod-r134` | Lần rollout trên môi trường cụ thể. |
| Consumer version | `billing:3.8.0` | Bản client đã triển khai/được test. |

**Tag không luôn bất biến**, nên với sản xuất hãy lưu image digest và nguồn registry đã được kiểm. Stub artifact coordinates cũng cần chính sách **không overwrite release** hoặc ghi checksum/provenance để phát hiện nội dung thay đổi.

Một producer release mới có thể vẫn phục vụ nhiều **API versions** cùng lúc. Ngược lại, artifact `2.1.0-stubs.jar` tồn tại không chứng minh `/api/v1` vẫn đang chạy trong production nếu route đã bị tắt ở gateway. Cần cả **test contract** lẫn **deployment/runtime evidence**.

## 11. Mẫu release manifest liên kết toàn bộ bằng chứng

Một **record JSON minh họa** có thể được CI/release registry lưu:

~~~json
{
  "service": "order-service",
  "source": {
    "repository": "order-service",
    "commit": "a1b2c3d4e5f678901234567890abcdef12345678",
    "pullRequest": "184",
    "contractPaths": [
      "src/test/resources/contracts/orders/get_paid_order.groovy"
    ]
  },
  "build": {
    "runId": "ci-483",
    "verificationStatus": "PASSED",
    "verificationReportRef": "ci-483/test-report",
    "artifactRef": "com.acme:order-service:2.1.0:stubs",
    "artifactSha256": "<sha256-of-stubs-jar>"
  },
  "container": {
    "image": "registry.example.org/orders/order-service",
    "digest": "sha256:<image-digest>"
  },
  "deployment": {
    "environment": "production",
    "region": "region-a",
    "rolloutId": "orders-prod-r134",
    "status": "COMPLETED"
  },
  "consumerChecks": [
    {
      "consumer": "billing-service",
      "stubVersion": "2.1.0",
      "result": "PASSED",
      "ciRunId": "billing-ci-991"
    }
  ]
}
~~~

Đây là **schema nội bộ gợi ý**, không phải định dạng bắt buộc của Spring Cloud Contract, Maven, Gradle hay Kubernetes. Giá trị trong dấu `<...>` là **placeholder**, không phải digest thật. Trong dự án, record phải được tạo từ **thông tin do CI/registry/deployment system xác nhận**, không điền tay dựa trên giả định.

Một số lưu ý:

- **Verification status** là kết quả thực của test runner, không phải metadata do developer tự đặt `PASSED`.
- **Artifact checksum** phải được tính từ bytes của file được publish, không từ nội dung README.
- **Image digest** lấy từ registry/build output và kiểm khi deploy, không lấy từ tên tag.
- **Deployment status** nên có thời điểm, environment/region, rollout revision và nguồn audit có thẩm quyền.
- **Consumer checks** cần nêu artifact version thực sự được test; một CI xanh từ stub cũ không bảo vệ producer release mới.
- **Không lưu secrets** (token, password, private key) hoặc payload người dùng thật trong manifest.

## 12. Maven: giữ traceability khi đóng gói và publish

Một producer Maven thường có plugin:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>${spring-cloud-contract.version}</version>
    <extensions>true</extensions>
    <configuration>
        <testFramework>JUNIT5</testFramework>
        <testMode>MOCKMVC</testMode>
        <baseClassForTests>com.acme.orders.ContractTestBase</baseClassForTests>
    </configuration>
</plugin>
~~~

Plugin tạo generated tests và stub resources theo lifecycle đã được tích hợp; **cấu hình thực tế phải được đối chiếu với phiên bản plugin/Spring Boot/Spring Cloud đang dùng**. Một quy trình tham khảo:

~~~shell
./mvnw clean verify
./mvnw deploy
~~~

`deploy` thường chạy qua các phase trước và có thể **chạy lại tests**. Nếu CI tách verify và publish thành job riêng, cần **chuyển đúng artifact đã được xác minh** sang job publish hoặc bảo đảm build lại đúng commit/dependencies/toolchain và có verification gate tương ứng; không đơn giản checkout `main` một lần nữa rồi phát hành bytes khác.

### 12.1. Tọa độ và checksum có thể ghi thế nào?

Thông tin để ghi trong release record:

~~~text
groupId: com.acme
artifactId: order-service
version: 2.1.0
classifier: stubs
extension: jar
sourceCommit: <full-git-sha>
verificationRun: <ci-run-id>
artifactChecksum: SHA-256 của JAR được publish
~~~

Với Maven, một JAR classifier `stubs` có thể được **attach** vào project và publish cùng POM theo cơ chế của Contract Plugin. Nhưng không mặc định mọi cấu hình custom hoặc profile đều xuất đủ stubs; hãy mở artifact và đối chiếu tọa độ/publish logs.

Một lệnh người học có thể dùng trong môi trường thử nghiệm:

~~~shell
jar tf target/order-service-2.1.0-stubs.jar
~~~

Đường dẫn `target/...` chỉ là ví dụ theo cấu hình mặc định thường gặp. Tránh chỉ kiểm file tồn tại từ lần build trước; `clean` hoặc artifact checksum giúp phát hiện stale output.

## 13. Gradle: giữ cùng nguyên tắc dù task khác Maven

Producer Gradle áp dụng:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
    id 'org.springframework.cloud.contract' version '4.1.5'
    id 'maven-publish'
}

group = 'com.acme'
version = '2.1.0'

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-starter-contract-verifier'
}

contracts {
    baseClassForTests = 'com.acme.orders.ContractTestBase'
    testFramework = 'JUNIT5'
    testMode = 'MOCKMVC'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đoạn trên là **mảnh cấu hình minh họa**, chưa phải build đầy đủ: phải quản lý BOM, repositories, Java toolchain và publication theo bộ phiên bản tương thích. `3.3.6`/`4.1.5` chỉ là **version ví dụ**, không khẳng định là bản mới nhất.

Gradle Plugin có các task liên quan như `generateContractTests`, `generateClientStubs` và task đóng gói stub (tên có thể khác theo version). Cần kiểm `./gradlew tasks --all` và task graph thực tế; đừng tự đổi `mvn verify` thành `./gradlew verify` khi dự án Gradle không khai báo task đó.

**Traceability không phụ thuộc build tool**: dù dùng Maven hay Gradle, phải lưu **source SHA, CI run ID, producer test report, artifact coordinates/checksum và deployment record**.

## 14. Stub Runner consumer tests phải chỉ rõ producer release

Billing dùng `spring-cloud-starter-contract-stub-runner` ở test scope, ví dụ:

~~~java
import java.net.URL;
import java.util.Objects;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.StubFinder;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:2.1.0:stubs",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class BillingOrderContractTest {

    @Autowired StubFinder stubFinder;

    @Test
    void readsOrderWithCurrency() {
        URL stubUrl = Objects.requireNonNull(
            stubFinder.findStubUrl("com.acme", "order-service"),
            "Order Service stub not started"
        );

        OrderClient client = new OrderClient(stubUrl.toExternalForm());
        OrderClient.OrderDto dto = client.getOrder(42L);

        assertThat(dto.status()).isEqualTo("PAID");
        assertThat(dto.amountMinor()).isEqualTo(125000L);
        assertThat(dto.currency()).isEqualTo("VND");
    }
}
~~~

`OrderClient` và DTO là **mã ứng dụng Billing giả định**; ví dụ tập trung vào chọn đúng stub và kiểm response. Với `LOCAL`, artifact phải được cài vào Maven local tương ứng; trong CI độc lập thường dùng `REMOTE` với repository và read credentials đã cấu hình.

**Đừng sử dụng `latest` hoặc một artifact mutable thiếu kiểm soát** nếu muốn test tái lập. Đầu ra CI consumer nên chỉ rõ `com.acme:order-service:2.1.0:stubs`, hash khi có và CI run. Nếu consumer test thất bại hôm nay nhưng hôm qua pass, việc biết **stub nào đã nạp** là dữ liệu chẩn đoán quan trọng.

### 14.1. Producer verification và consumer test là hai bằng chứng bổ trợ

| Test | Chứng minh điều gì? | Không chứng minh điều gì? |
| --- | --- | --- |
| **Generated producer test** | Implementation producer tại build được kiểm **phù hợp hợp đồng**. | Consumer production đã deploy client mới. |
| **Stub Runner consumer test** | Mã client consumer có thể sử dụng **dữ liệu stub được chọn**. | Producer instance đang chạy đúng commit nếu không có deployment evidence. |
| **Deploy smoke test** | Producer deployment đang phục vụ một số request/sample kiểm. | Toàn bộ hợp đồng/consumer/các lỗi hiếm đều đúng. |
| **Runtime tracing/metrics** | Bản deployment nào nhận traffic và có lỗi gì. | Causal proof cho mọi thay đổi API nếu không liên kết commit/artifact. |

**Không một loại test nào thay thế các loại còn lại.** Muốn xác định một lỗi là do source contract, implementation, artifact, deployment hoặc client phải có **chuỗi bằng chứng liên tục**.

## 15. Consumer compatibility matrix nên có nguồn dữ liệu rõ

Khi nhiều nhóm phát hành độc lập, cần ghi tổ hợp producer–consumer được hỗ trợ:

| Consumer version | Producer stub release | Kết quả CI | Producer production release | Ghi chú |
| --- | --- | --- | --- | --- |
| `billing 3.7.0` | `order 2.0.0:stubs` | PASS | Order `2.0.0` | Baseline lịch sử. |
| `billing 3.7.0` | `order 2.1.0:stubs` | PASS/FAIL thực tế | Order `2.1.0` chưa triển khai | Kiểm tương thích trước rollout. |
| `billing 3.8.0` | `order 2.1.0:stubs` | PASS/FAIL thực tế | Order `2.1.0` đang canary | Billing đã hỗ trợ `currency`. |
| `analytics monthly job` | `order 2.1.0:stubs` | Chưa kiểm | Order `2.1.0` | Owner cần xác nhận. |

Bảng là **minh họa, không có kết quả CI thật**. Tránh ghi `PASS` khi chưa có report. “Source branch compatible” khác “binary consumer đang chạy compatible”; cả hai cần được ghi đúng trạng thái.

### 15.1. Ma trận không phải mọi tổ hợp phiên bản có thể tưởng tượng

Không nhất thiết chạy tích Descartes của mọi release trong lịch sử. Hãy ưu tiên:

- Consumer versions còn được hỗ trợ/đang chạy trên production.
- Producer releases sắp triển khai hoặc đang canary.
- Những thay đổi có nguy cơ breaking (schema/headers/status/error/destination).
- Consumer batch/offline hoặc partner có chu kỳ deploy dài.
- Phiên bản đang trong giai đoạn deprecation/migration.

Với tổ hợp không được hỗ trợ, phải **công bố chính sách**. Không để một dấu “not tested” bị diễn giải thành “compatible”.

## 16. Deployment traceability: chứng minh producer nào đang phục vụ production

Một release record build `PASSED` **chưa phải bằng chứng đã deploy**. Khi rollout, cần thông tin:

~~~text
service: order-service
environment: prod
region: region-a
releaseVersion: 2.1.0
gitCommit: a1b2c3d4... (full SHA trong nguồn record)
containerImage: registry.example.org/orders/order-service@sha256:...
deploymentRevision: orders-prod-r134
deployedAt: timestamp có timezone
rolloutStrategy: canary -> full
rolloutStatus: COMPLETED / PARTIAL / ROLLED_BACK
approvedBy: change/release authority
~~~

**Chỉ ghi “đã triển khai v2.1.0” là chưa đủ** nếu cluster có nhiều pods/regions đang chạy những digests khác nhau. Giai đoạn canary có thể phục vụ **cùng một API request qua hai phiên bản producer**. Phải biết tỷ lệ, vùng, thời gian và cách route của traffic.

### 16.1. Helm/Kubernetes manifest là bằng chứng ý định, không phải runtime đầy đủ

Ví dụ manifest dùng image digest:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
  annotations:
    example.org/source-commit: "a1b2c3d4e5f678901234567890abcdef12345678"
    example.org/release-version: "2.1.0"
    example.org/build-run-id: "ci-483"
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: order-service
          image: registry.example.org/orders/order-service@sha256:<digest>
          ports:
            - containerPort: 8080
~~~

Các keys `example.org/*` và digest placeholder là **quy ước minh họa**, không phải Spring Cloud Contract tự tạo. Trong triển khai thật, YAML này còn cần security context, probes, resources, secrets, policy và template substitutions phù hợp.

**Manifest được commit hoặc apply chỉ chứng minh deployment được yêu cầu**, không tự chứng minh tất cả pods đã chạy đúng image. Cần **deployment rollout status, pod/container image IDs/digests và monitoring** từ nền tảng triển khai để xác nhận trạng thái thực tế.

## 17. Runtime build identity và correlation ID: hai mục đích khác nhau

Một request có thể được gắn **correlation ID** để lần qua gateway, Order Service và Billing Service. Một bản deploy có **build identity** để xác định nó chạy từ source/artifact nào. Đây là **hai loại dữ liệu khác nhau**:

| Thuộc tính | Ví dụ | Phạm vi |
| --- | --- | --- |
| Correlation/trace ID | `traceId=9d7...` | Một trace hoặc workflow/request. |
| Request ID | `X-Request-Id: req-001` | Một HTTP request, tùy quy ước. |
| Contract/API version | `/api/v1/orders/42` | Giao diện được sử dụng. |
| Release version | `order-service 2.1.0` | Bản phần mềm. |
| Git SHA | `a1b2c3...` | Source snapshot. |
| Image digest | `sha256:...` | Bytes container image. |
| CI build/run ID | `ci-483` | Lượt build/verification. |
| Deployment revision | `orders-prod-r134` | Lượt triển khai. |

**Không dùng một request ID làm bằng chứng source code đã deploy**. Cũng đừng tự chèn version software vào `traceId` để “tiện truy”: hệ thống tracing có cấu trúc/span attributes dành cho thông tin này.

### 17.1. Quan sát ở mức HTTP

Một log có cấu trúc, **không chứa PII hoặc token**, có thể ghi:

~~~json
{
  "timestamp": "2027-01-15T10:00:00Z",
  "service": "order-service",
  "environment": "production",
  "releaseVersion": "2.1.0",
  "gitCommit": "a1b2c3d4...",
  "buildRunId": "ci-483",
  "deploymentRevision": "orders-prod-r134",
  "traceId": "9d75c42f...",
  "httpMethod": "GET",
  "httpRoute": "/api/orders/{id}",
  "httpStatus": 200,
  "contractVariant": "orders-v1"
}
~~~

Đây là **ví dụ schema log**, không phải output tự động mặc định của Spring Boot. `httpRoute` nên dùng **route template** để tránh log raw IDs/PII hoặc làm metrics quá nhiều nhãn; `contractVariant` phải xuất phát từ cơ chế nhận dạng hợp đồng thực, không được suy đoán từ status code.

Các lưu ý an toàn:

- Không log `Authorization`, cookies, token, toàn bộ body đơn hàng hoặc dữ liệu nhạy cảm.
- Không đưa Git SHA thành label metrics có cardinality quá lớn nếu hệ thống quan sát không cho phép.
- Timestamp cần có timezone và đồng bộ thời gian giữa CI, registry, deploy system.
- Khi log sampling, **không thấy request** có thể do bị sample, không phải chắc chắn không có traffic.
- Thuộc tính release identity nên gắn từ **pipeline/metadata đã được xác minh**, không tự gõ một chuỗi “2.1.0” trong source.

## 18. Traceability cho messaging: event version, destination và replay

Với messaging, thay đổi hợp đồng không chỉ là URL/JSON. Producer có thể phát `OrderCreated`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'orderCreatedV2'
    description 'OrderCreated schema v2 cho Billing'

    input {
        triggeredBy('publishOrderCreatedV2()')
    }

    outputMessage {
        sentTo('orders.created.v2')
        headers {
            header('contentType', 'application/json')
            header('eventType', 'OrderCreated')
            header('schemaVersion', 2)
        }
        body(
            eventId: 'evt-001',
            orderId: 'ORD-42',
            amount: [minor: 125000, currency: 'VND']
        )
    }
}
~~~

Để truy vết một sự cố message, cần biết:

| Dữ liệu | Vai trò |
| --- | --- |
| Contract source path/commit | Schema và label nào được producer cam kết. |
| `schemaVersion` hoặc schema registry ID | Consumer giải mã theo schema nào. |
| Destination/topic và partition/key | Message được publish vào luồng nào, partition/order ra sao. |
| `eventId` | Idempotency/deduplication và truy vết sự kiện nghiệp vụ. |
| Trace/correlation ID | Liên kết producer publish với consumer processing nếu hạ tầng hỗ trợ. |
| Producer release/image digest | Version nào phát ra message. |
| Consumer release | Version nào đã đọc và xử lý hoặc đưa vào DLQ. |
| Offset/delivery metadata phù hợp | Truy message lưu trữ/retry/replay trong broker. |

**Lưu ý:** không phải mọi transport giữ nguyên header, và `eventId` không thay thế message broker offset. Nếu hệ thống có Kafka/RabbitMQ/schema registry, phải kiểm **actual serialization/binder mapping** và retention/replay policies bằng integration tests. Generated messaging contract test có thể chỉ quan sát `Spring Message` trong test adapter, chưa chắc chứng minh bytes production đúng.

### 18.1. Không chỉ truy bản publisher hiện tại

Consumer có thể nhận lại một message **được publish bởi producer release cũ** do backlog, DLQ hoặc replay. Vì thế:

- Đừng suy rằng mọi event nhận hôm nay đều do **producer image đang chạy hôm nay** tạo.
- Nếu lưu producer release ID trong message metadata, quy ước field phải được hai bên thống nhất; không đưa thông tin môi trường nhạy cảm vào payload công khai.
- Giữ khả năng giải mã các schema cũ còn xuất hiện theo retention/support policy.
- Đối chiếu `schemaVersion` với event time, publish time, broker metadata và consumer processing time.
- Khi retirement một event version, có thể dừng phát version cũ **trước** khi dừng khả năng đọc version cũ.

Đó là lý do traceability messaging cần cả **build identity** lẫn **event identity** và thông tin lưu trữ trên broker.

## 19. Quy trình PR giữa nhiều nhóm

Một thay đổi contract nên đi qua các bước phối hợp rõ ràng:

~~~mermaid
flowchart TD
    A["Consumer mở nhu cầu mới"] --> B["Producer đánh giá API + khả năng tương thích"]
    B --> C{"Breaking change?"}
    C -->|Có| D["Thiết kế version/migration/dual support"]
    C -->|Không rõ| E["Chạy test consumer cũ + review schema"]
    C -->|Không| F["Cập nhật contract/test có chủ đích"]
    D --> F
    E --> F
    F --> G["PR: links issue, owners, diff, test impact"]
    G --> H["Producer + affected consumers review"]
    H --> I["CI generated producer tests"]
    I --> J["CI Stub Runner consumer compatibility"]
    J --> K{"Gates và approvals đạt?"}
    K -->|Không| L["Sửa/hoãn, không release"]
    K -->|Có| M["Merge commit xác định, build verified artifacts"]
~~~

**Không dùng “consumer review” như một thủ tục hình thức**. Reviewer cần xem những hành vi client thật phụ thuộc: error body/status, required headers, enums, array order, timeout/retry, auth scopes và message semantics.

Một thay đổi có thể ảnh hưởng **nhiều nhóm**; thông báo chỉ qua một cuộc chat không có link PR/artifact dễ bị mất. Nên lưu quyết định ở PR/ADR/issue và gắn link vào release record.

### 19.1. Contract-first và producer-first

Hai quy trình đều có thể được dùng nếu có kỷ luật:

- **Contract-first:** các bên review DSL/semantics trước, producer triển khai theo hợp đồng, generated tests kiểm implementation.
- **Producer-first với kiểm soát:** producer đề xuất thay đổi implementation/contract trong cùng PR hoặc chuỗi PR có liên kết, chạy tương thích với consumer trước rollout.

Rủi ro không nằm ở tên phương pháp mà ở **thời điểm xác nhận và bằng chứng**. Nếu producer deploy breaking API trước khi consumer kiểm/di chuyển, các commit sau đó không khắc phục được thời gian downtime đã xảy ra.

## 20. Tạo CI gate ngăn “đúng stub nhưng sai producer”

Một pipeline mạnh nên ngăn các tình huống:

1. Contract source thuộc commit A nhưng generated test chạy trên commit B.
2. Stub artifact build từ commit A nhưng producer image build lại từ commit C.
3. Consumer Stub Runner CI test `order-service:2.0.0:stubs` trong khi production deploy producer `2.1.0` có breaking change.
4. Producer tests bị skip nhưng build vẫn publish `stubs`.
5. Một release version bị ghi đè làm checksum JAR thay đổi.
6. Canary đang chạy hai image digests nhưng báo cáo rollout chỉ ghi một version.

**Đề xuất CI gate:**

| Gate | Điều kiện bắt buộc | Bằng chứng |
| --- | --- | --- |
| **G1. Contract source** | Contract diff + owner/review hợp lệ. | PR/commit links. |
| **G2. Producer verification** | Generated tests thực sự chạy và pass. | CI run/test reports, test count. |
| **G3. Stub packaging** | JAR `stubs` chứa contract/mappings dự kiến. | Artifact inspection + checksum. |
| **G4. Consumer compatibility** | Consumer versions được hỗ trợ pass hoặc có migration decision. | Stub Runner CI report/version matrix. |
| **G5. Artifact provenance** | Source SHA, run ID, stub checksum và image digest liên kết. | Build/release manifest, registry records. |
| **G6. Publish policy** | Release artifacts bất biến, rights và approval đúng. | Artifact registry audit. |
| **G7. Deployment controls** | Canary/approval/rollback/health checks rõ. | Deployment records và observability. |
| **G8. Post-deploy** | Runtime lỗi/traffic phù hợp, version thực được xác nhận. | Metrics/traces/rollout status. |

Không phải mọi gate phải chạy trên một CI job duy nhất. Nhưng **gates sau không được coi là đạt nếu bằng chứng ở gates trước chưa tồn tại hoặc chưa đúng phiên bản**.

### 20.1. Pseudocode pipeline để mô tả liên kết

~~~yaml
# Pseudocode: không phải cấu hình chạy được trên một CI cụ thể.
producer_pipeline:
  source:
    commit: <immutable-full-git-sha>
    contracts: <changed-contract-paths>

  verify:
    run_generated_contract_tests: true
    fail_if_zero_required_contract_tests: true
    publish_only_if_pass: true

  package:
    from_verified_workspace: true
    create_stubs_classifier_jar: true
    build_image_from_same_source: true
    collect_checksums_and_digest: true

  consumer_checks:
    select_supported_consumers: true
    pin_new_stub_artifact: true
    keep_run_references: true

  publish:
    require_all_gates: true
    immutable_artifact_coordinates: true
    persist_release_manifest: true

  deploy:
    use_verified_image_digest: true
    require_approval: true
    record_environment_and_rollout: true
    monitor_and_allow_rollback: true
~~~

Các khóa trên chỉ **minh họa chính sách**. Chúng không phải option của Spring Cloud Contract hay một CI provider. Khi triển khai, dùng cơ chế của GitHub Actions/GitLab/Jenkins/Argo CD hoặc hệ thống hiện có để tạo **quan hệ phụ thuộc và quyền** thật, thay vì tin một trường YAML `publish_only_if_pass: true` tự thực hiện việc chặn.

## 21. Rollout, canary, rollback và dấu vết hậu triển khai

Một PR được merge và producer verification PASS không đảm bảo không có lỗi vận hành. Sau release, cần phân biệt:

| Sự kiện | Dấu vết |
| --- | --- |
| Build image | Git SHA, build run, image digest và checksum stub. |
| Publish | Artifact coordinates, registry, timestamp, permissions. |
| Staging deploy | Environment, deploy revision, smoke tests. |
| Canary prod | Image digest, traffic percentage, region, time window. |
| Full rollout | Quyết định GO, manifest, trạng thái replicas/health. |
| Consumer regression | Consumer/service version, trace ID, API contract version, log sample đã redaction. |
| Rollback | Old image digest, rollback revision, lý do và thời điểm hoàn tất. |
| Fix forward | New commit, artifact, generated test report, deployment ID. |

**Rollback không phải sửa một version trong POM rồi chạy lại ngẫu nhiên**. Cần biết **image digest và cấu hình runtime** của bản tốt trước đó, dữ liệu/schema migrations có đảo ngược được không, và contract cũ còn phù hợp các consumer đang chạy không.

Trong canary, nếu một phần traffic đến bản cũ và phần còn lại đến bản mới, hãy phân loại error metrics **theo deployment revision** trước khi kết luận consumer hỏng do contract.

### 21.1. Trường hợp rollback không an toàn

Một schema event mới có thể đã được publish hoặc dữ liệu DB đã migration. Quay lại producer binary cũ có thể khiến:

- Producer cũ không đọc được dữ liệu mới.
- Consumer đã cập nhật không còn hỗ trợ phản hồi cũ.
- Message v2 còn trong queue nhưng consumer/producer cũ chỉ xử lý v1.
- API gateway hoặc auth policy đã đổi.

Vì vậy, **rollback plan phải được thiết kế khi review thay đổi**, không phải sau khi lỗi xuất hiện. Với thay đổi phá tương thích, expand–migrate–contract và dual-read/dual-write có thể giúp tạo khoảng an toàn để quay lui, nhưng phải kiểm duplication/idempotency khi phát nhiều event.

## 22. Khi sự cố xảy ra: lần theo chuỗi không suy đoán

Giả sử Billing báo lỗi deserialize `currency` trên production sau một deploy của Order Service.

Quy trình điều tra:

1. Lấy **trace ID/request timestamp** từ Billing, cùng môi trường và vùng bị ảnh hưởng. Không bắt đầu bằng suy đoán “do commit mới”.
2. Xác định **Billing binary/release** thật sự đã nhận response, và nó kỳ vọng schema nào.
3. Tìm request đến **Order Service deployment revision/image digest** nào dựa trên logs/traces/gateway routing.
4. Từ digest, tra **release manifest** tới source commit, CI run và stub checksum/coordinates.
5. Xem **contract diff** giữa release hiện tại và bản tốt trước đó; kiểm field/type/headers/error semantics.
6. Xem **generated producer test report**: test tương ứng có chạy không, đã kiểm đúng kiểu/dữ liệu không?
7. Xem **consumer Stub Runner report**: Billing đã test với stub release nào; có phải release được triển khai không?
8. Đối chiếu **raw HTTP response đã được lọc an toàn** hoặc structured schema evidence để xác định server thực đã gửi gì. Không in payload nhạy cảm.
9. Phân loại: **lỗi contract**, **lỗi implementation**, **lỗi converter**, **sai artifact**, **sai deployment**, **thiếu CI coverage** hay **lỗi runtime**.
10. Chọn **rollback/fix forward** theo tác động và compatibility, rồi cập nhật contract/tests/release process để ngăn lặp.

~~~mermaid
flowchart TD
    A["Billing incident + trace ID"] --> B["Consumer release / expected schema"]
    A --> C["Producer deployment revision/image digest"]
    C --> D["Release record: Git SHA + CI run"]
    D --> E["Contract diff + producer tests"]
    D --> F["Stub coordinates + checksum"]
    F --> G["Consumer test dùng đúng artifact?"]
    E --> H["Root cause + repair + rollback/fix-forward"]
    G --> H
~~~

**Nếu không có bản ghi nối artifact stub với producer image**, điều tra có thể mất nhiều thời gian và chỉ kết thúc bằng phỏng đoán. Đó là một lỗi quy trình có thể khắc phục bằng release manifest và CI gates, không phải bằng việc tăng log tùy tiện.

## 23. Những sai lầm làm mất traceability

| Sai lầm | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Commit contract và implementation không liên quan nhưng publish chung release. | Không biết version API có thực sự được producer kiểm không. | Link PR/commit, giữ contract source và verified build record. |
| Producer tests bị skip hoặc số tests = 0. | Stub được publish dù implementation chưa được xác minh. | Gate trên generated test execution/reports. |
| Dùng `latest` hoặc mutable `-SNAPSHOT` không kiểm soát. | Cùng CI commit có thể tải stub khác theo thời điểm. | Pin version/checksum, quản lý snapshot/cache rõ. |
| Publish cùng version nhưng ghi đè bytes stub. | Consumer results không tái lập. | Immutable releases và artifact digests. |
| Image build lại từ branch đang di chuyển. | Producer production không khớp source đã test. | Promote image digest của verified build. |
| Chỉ lưu Docker tag, không có digest. | Tag có thể trỏ image khác sau này. | Ghi image digest + registry reference. |
| PR review chỉ có producer, không biết consumer owners. | Breaking change lọt trước migration. | Consumer inventory/ownership + compatibility review. |
| Test consumer cũ chỉ với stub của producer cũ. | Producer release hiện tại làm hỏng legacy nhưng không bị phát hiện. | Verify supported legacy contracts trên producer hiện tại. |
| Có release manifest nhưng do người tự điền status PASS. | Bằng chứng không đáng tin. | CI tạo record từ tool outputs được xác nhận. |
| Canaries chạy nhiều digests nhưng chỉ ghi một version. | Không xác định pod/region gây lỗi. | Track rollout revision và image digest theo instance. |
| Gộp trace ID với release version. | Khó phân biệt sự cố request và bản build. | Dùng các trường tách biệt trong logs/traces. |
| Log request body/token toàn bộ để “truy vết”. | Lộ bí mật/PII, tăng rủi ro tuân thủ. | Structured logging có redaction và retention policy. |
| Xóa artifacts lịch sử ngay khi EOL. | Không tái dựng sự cố cũ được. | Retention/audit policy độc lập API support policy. |
| Mỗi đội tự đặt tên version/metadata khác nhau. | Không join được reports/registry/deploy records. | Dùng convention chung cho service, SHA, artifact, revision. |
| Rollback không có bản tốt xác định. | Quay về nhầm image hoặc phá consumer mới. | Lưu digest/config trước đó và diễn tập. |

Một quy trình truy vết tốt phải **đủ dễ làm trong công việc hằng ngày**. Nếu cần nhiều thao tác thủ công, teams có xu hướng bỏ qua; hãy tự động thu Git SHA, artifact coordinates, checksums và deploy revisions qua CI/CD thay vì yêu cầu người viết tay.

## 24. Bài thực hành: liên kết một thay đổi contract tới production release

Thực hành giả lập với **Order Service** và **Billing Service** đã có Spring Cloud Contract:

1. **Tạo issue giả định** `ORDER-184` với yêu cầu bổ sung `currency` vào response đơn hàng, chỉ định producer owner, consumer reviewers và tiêu chí không phá schema cũ.
2. **Viết hợp đồng Groovy hoặc YAML** cho `GET /api/orders/42` như mục 5, giữ `id`, `status`, `amountMinor` và thêm `currency`.
3. **Thêm/đổi implementation producer** để trả JSON khớp hợp đồng; xây dựng base test và generated producer verification.
4. **Chạy producer tests**, xác minh test được sinh và thực thi; cố ý đổi `amountMinor` từ number sang string để kiểm cổng test FAIL, rồi hoàn nguyên.
5. **Ghi Git commit đầy đủ** cùng PR/issue link; tạo record mô tả contract paths và quyết định compatibility.
6. **Đóng gói JAR classifier `stubs`**, ví dụ `com.acme:order-service:2.1.0:stubs`; mở JAR để kiểm mappings/contracts và tính checksum của bytes.
7. **Chạy Billing Stub Runner test với artifact version xác định**, dùng `StubFinder` lấy URL động và `OrderClient` thật để kiểm `amountMinor`/`currency`.
8. **Chạy thêm consumer cũ** nếu vẫn được hỗ trợ, để phát hiện strict parser không chấp nhận field mới.
9. **Ghi CI run ID, test reports và artifact checksum** vào release manifest mẫu; chưa ghi `PASSED` nếu chưa có báo cáo thực tế.
10. **Build container image từ cùng source/verified build**, lấy digest thật từ container registry hoặc build output.
11. **Mô phỏng staging/canary deploy**, lưu environment, region, rollout ID và digest; phân biệt **intended manifest** với evidence của pods đang chạy.
12. **Tạo structured log giả định** có release identity và trace ID riêng, không chứa token hoặc payload nhạy cảm.
13. **Mô phỏng lỗi Billing** khi consumer gọi sai API version; từ trace ID truy ngược release manifest → source contract diff → generated tests → artifact stub → deployment.
14. **Mô phỏng rollback**: xác định image digest của bản tốt trước đó, kiểm khả năng tương thích dữ liệu/consumer và ghi sự kiện rollback.
15. **Đưa vào CI gates**: producer test pass → artifact immutable → consumer compatibility tests → approved deploy → post-deploy verification.

**Tiêu chí hoàn thành:** chỉ từ một incident record hoặc một deployment revision, người học có thể tìm được **hợp đồng đã đổi, Git commit/PR, producer verification report, JAR `stubs` với checksum, consumer test version, container image digest và bằng chứng deploy** mà không phải đoán hay dựa vào tên branch đang thay đổi.

## 25. Câu hỏi tự kiểm tra

1. Traceability trong kiểm thử hợp đồng trả lời những câu hỏi gì ngoài “test pass hay fail”?
2. `API contract version`, Maven artifact version, Git SHA, image digest và deployment revision khác nhau ở điểm nào?
3. Vì sao một artifact `stubs` có tên đúng version vẫn có thể không đáng tin nếu generated producer tests bị skip?
4. Vì sao không nên dùng branch `main` làm danh tính của một release đã triển khai?
5. Vì sao Git SHA không đủ để định danh hoàn toàn một artifact khi build không quyết định?
6. Tại sao nên ghi SHA-256 checksum của JAR `stubs` và image digest thay vì chỉ ghi filenames/tags?
7. Khi thêm một trường optional vào JSON, có thể mặc định tương thích với mọi consumer không?
8. Vì sao việc consumer test xanh với `order-service:2.0.0:stubs` không chứng minh producer `2.1.0` đang triển khai tương thích?
9. Mỗi nhóm producer/consumer/platform chịu trách nhiệm phần nào trong quy trình đề xuất, verification, publish và rollout?
10. Những thông tin nào nên có trong phần đánh giá tác động của một PR sửa contract?
11. Tại sao một producer release có thể phải giữ contract v1 dù đã phát hành API v2?
12. Một release manifest nên được sinh từ đâu để thông tin `verificationStatus=PASSED` đáng tin?
13. Vì sao một Kubernetes manifest chứa image digest chưa đủ chứng minh tất cả pods production đã chạy đúng bản đó?
14. Correlation ID và release ID khác nhau về phạm vi như thế nào?
15. Trong message-driven architecture, tại sao message nhận hôm nay có thể do producer release đã ngừng chạy phát trước đó?
16. Khi dùng Stub Runner `REMOTE`, URL Maven repository khác URL HTTP stub server ra sao?
17. Những gate nào cần có trước khi cho phép publish/deploy một thay đổi có nguy cơ breaking?
18. Vì sao canary rollout phải ghi nhận cả traffic percentage và image digest theo môi trường/vùng?
19. Khi rollback producer, tại sao cần xem consumer version, DB migration và message schemas?
20. Khi điều tra incident, đường truy vết nào nối consumer error tới source contract và verified artifact?
21. Vì sao giữ artifacts lịch sử có thể hữu ích dù hợp đồng API v1 đã retired?
22. Cách nào giúp truy vết nhưng vẫn bảo vệ secrets và dữ liệu nhạy cảm?

## 26. Mẫu checklist release có thể áp dụng

| Nhóm kiểm | Điều cần xác nhận | Bằng chứng/Link |
| --- | --- | --- |
| **Contract ownership** | Có owner, affected consumers, PR/ADR/issue và compatibility review. | Link PR, issue và review record. |
| **Source** | Full Git SHA đã merge, contract paths và producer implementation liên quan. | Repository commit link. |
| **Producer verification** | Generated tests chạy thật, không bị skip, đủ contract cases và pass. | CI run + test report. |
| **Stub packaging** | Classifier `stubs`, đúng coordinates, mappings/contracts và checksum. | Artifact registry + digest. |
| **Consumer tests** | Các client được hỗ trợ đã test đúng stub version. | Stub Runner run IDs + compatibility matrix. |
| **Artifact linkage** | Image digest và JAR stub có nguồn source/build rõ ràng. | Build manifest/provenance. |
| **Publish** | Artifact bất biến, chính sách repository và quyền ghi đúng. | Registry publish/audit record. |
| **Deploy** | Đúng environment/region, image digest, rollout/approval. | Deployment revision + rollout status. |
| **Runtime** | Logs/metrics theo bản deploy, API version, lỗi và trace IDs có redaction. | Dashboards/traces/smoke report. |
| **Rollback** | Có bản tốt trước đó, điều kiện quay lui và owner on-call. | Runbook + previous image digest. |
| **Retirement** | Hợp đồng cũ chỉ bị xóa sau khi đã đạt tiêu chí EOL. | Decision record và consumer inventory. |

**Kết luận:** **Một thay đổi hợp đồng chỉ có thể truy vết tốt khi các nhóm liên kết được nguồn DSL → Git commit/PR → generated producer tests → artifact `stubs` → consumer Stub Runner tests → producer image digest → bản triển khai và quan sát runtime**. Đừng dùng mỗi tên version hoặc trạng thái CI xanh để suy ra producer production đang chạy đúng hợp đồng. Hãy giữ artifact bất biến, dùng checksum/digest, có owner/approval và compatibility gates, lưu release/deploy records, kết hợp correlation IDs khi điều tra nhưng không log secrets. Khi các dấu vết này được tự động hóa trong CI/CD, producer và consumer có thể phát hành độc lập mà vẫn tìm đúng nguyên nhân và rollback an toàn trước những thay đổi API hoặc message không tương thích.
