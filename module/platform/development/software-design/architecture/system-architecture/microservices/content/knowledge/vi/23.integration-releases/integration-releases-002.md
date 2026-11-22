# Lựa chọn monorepo hoặc polyrepo theo mô hình phối hợp trong microservices

## 1. Bối cảnh: nơi lưu mã nguồn là một quyết định về phối hợp

Trong hệ thống microservices, mỗi service có thể có vòng đời riêng: nhóm phát triển riêng, pipeline kiểm thử riêng, lịch triển khai riêng, yêu cầu bảo mật riêng và hợp đồng trao đổi dữ liệu riêng. Khi hệ thống tăng từ vài service lên hàng chục service, cách tổ chức repository ảnh hưởng trực tiếp đến việc các nhóm sửa API, cập nhật thư viện chung, review thay đổi, phối hợp migration và phát hành.

Có hai cách tổ chức phổ biến:

- **Monorepo:** nhiều service, thư viện và hợp đồng được lưu chung trong một repository Git, có thể dưới các thư mục độc lập.
- **Polyrepo (multi-repo):** các service và thư viện được chia ra nhiều repository Git; mỗi repository có quy trình quản trị và CI/CD phù hợp.

Ví dụ:

```text
MONOREPO                           POLYREPO
commerce-platform/                 orders-service.git
  services/orders/                   src/
  services/payments/                 build.gradle
  services/inventory/                .github/workflows/
  contracts/
  libraries/                       payments-service.git
  tooling/                           src/
  .github/workflows/                 build.gradle

                                   inventory-service.git
                                     src/

                                   commerce-contracts.git
                                   shared-observability.git
```

**Monorepo không đồng nghĩa monolith. Polyrepo không tự bảo đảm tính độc lập của microservices.** Một monorepo vẫn có thể build, test và deploy từng service độc lập; một polyrepo vẫn có thể bị khóa phiên bản và phải phát hành tất cả service cùng lúc nếu kiến trúc có liên kết chặt.

Quyết định đúng cần xuất phát từ **mô hình phối hợp thay đổi**: ai thường phải sửa cùng nhau, ai sở hữu phần nào, giới hạn quyền truy cập ra sao, quy trình đảm bảo compatibility thế nào và những thay đổi nào cần nguyên tử trong source control.

### Mục tiêu học tập

Sau bài này, bạn có thể:
1. Phân biệt ranh giới repository, ranh giới code module, ranh giới service và ranh giới triển khai.
2. Đánh giá monorepo/polyrepo dựa trên team ownership, tần suất thay đổi liên service, contract và độc lập phát hành.
3. Thiết kế CI/CD theo changed paths, dependency graph và contract verification.
4. Giải thích vì sao commit nguyên tử ở monorepo **không đồng nghĩa** triển khai nguyên tử.
5. Xử lý shared libraries, versioning, quyền truy cập, kiểm thử chéo và thay đổi database/event schema.
6. Xây tiêu chí lựa chọn, lộ trình chuyển đổi và guardrail để repository hỗ trợ mô hình tổ chức thực tế.

## 2. Bốn ranh giới dễ bị nhầm

| Ranh giới | Nó quyết định | Nó không tự quyết định |
| --- | --- | --- |
| **Git repository** | Commit, branch, quyền đọc/ghi, review và lịch sử mã nguồn | Service có độc lập runtime hay không |
| **Build module/package** | Dependency nội bộ, cache, build task, artifact | Service phải deploy chung hay không |
| **Service/process** | API, dữ liệu, tài nguyên runtime, failure boundary | Phải nằm trong repository riêng |
| **Deployment/release unit** | Đối tượng có thể deploy/rollback, version, canary | Cấu trúc Git tương ứng một-một |

Ví dụ một repository Git chứa `orders` và `payments` dưới hai thư mục. Nếu mỗi service có container image riêng, database riêng và pipeline deploy riêng, đó vẫn là hai microservices độc lập ở runtime. Ngược lại, hai repo Git khác nhau nhưng bắt buộc publish đồng thời, dùng chung schema database không kiểm soát và cùng phụ thuộc một snapshot library chưa version hóa thì vẫn liên kết chặt.

Quy tắc thực tế: **chọn repository để tối ưu cách cộng tác và kiểm soát mã nguồn; thiết kế boundaries và deployment để giữ độc lập vận hành.** Hai nhóm quyết định có liên hệ nhưng không thay thế nhau.

## 3. Monorepo: thuận lợi khi thay đổi cần được nhìn như một tổng thể

Monorepo gom những thành phần có liên quan vào một Git history và một bề mặt khám phá mã nguồn.

```text
commerce/
├── services/
│   ├── orders/
│   │   ├── src/
│   │   ├── Dockerfile
│   │   └── build.gradle
│   ├── payments/
│   │   ├── src/
│   │   ├── Dockerfile
│   │   └── build.gradle
│   └── inventory/
│       ├── src/
│       └── build.gradle
├── contracts/
│   ├── orders-openapi.yaml
│   ├── payment-events.avsc
│   └── inventory-openapi.yaml
├── libraries/
│   └── tracing/
├── tooling/
│   └── build-logic/
├── settings.gradle
└── .github/workflows/
```

### Lợi ích thường gặp

**Thay đổi có thể đi cùng một commit/PR.** Khi thêm trường `reservationId` vào event, các nhóm có thể thấy contract, publisher, consumer và bài kiểm tra tương ứng trong cùng diff. Điều này giảm khoảng mù giữa các repo khi cần một thay đổi đồng bộ ở mức mã nguồn.

**Khả năng khám phá cao.** Developer có thể tìm nơi gọi endpoint, serializer và shared library mà không phải dò nhiều repository và quyền truy cập. Các quy tắc lint, định dạng, bảo mật và build platform có thể chia sẻ.

**Refactor rộng dễ kiểm soát hơn về mặt source.** Nâng một library hoặc đổi API có thể cập nhật nhiều consumer và kiểm tra tác động trong một PR, nếu build graph được xác định rõ.

**Dễ thiết lập môi trường phát triển nhất quán.** Một tập tooling, wrapper, conventions và môi trường chạy local có thể giảm khác biệt giữa các nhóm.

### Chi phí và rủi ro

- Repository lớn làm clone, indexing và tìm kiếm chậm nếu không có công cụ phù hợp.
- Pipeline “mọi commit chạy mọi test và deploy mọi service” có thể tăng chi phí rất nhanh.
- Shared branch và global rules có thể tạo xung đột khi nhiều team muốn nhịp thay đổi khác nhau.
- Một PR sửa nhiều service có thể không rõ ai có quyền approve và ai chịu trách nhiệm rollback.
- Chính sách đọc code bí mật hoặc yêu cầu cô lập pháp lý khó triển khai nếu mọi thành viên được cấp quyền đọc toàn repo.
- Lịch sử commit chung không bảo đảm mọi service dùng cùng commit được deploy vào production.

**Monorepo chỉ thực sự hiệu quả ở quy mô lớn khi có build graph, ownership, quy trình review và CI chọn lọc**. Một Git repo chung nhưng thiếu những thành phần đó thường trở thành nơi các pipeline chờ nhau.

## 4. Polyrepo: thuận lợi khi service là đơn vị sở hữu và vận hành độc lập

Trong polyrepo, mỗi service hoặc mỗi nhóm artifact có repository riêng.

```text
orders-service.git
  src/
  Dockerfile
  build.gradle
  .github/workflows/

payments-service.git
  src/
  Dockerfile
  build.gradle
  .github/workflows/

inventory-service.git
  src/
  Dockerfile
  build.gradle
  .github/workflows/

commerce-api-contracts.git
  orders-openapi.yaml
  payment-events.avsc
```

### Lợi ích thường gặp

**Ownership rõ.** Team Orders quyết định nhịp phát hành, branch protection và quy tắc review của Orders. Những service quan trọng có thể có policy và quyền truy cập riêng.

**Pipeline và lịch sử thay đổi cô lập.** Một commit vào Orders không tự kích hoạt build của Payments nếu không có dependency hay sự kiện contract tương ứng. Team có thể kiểm soát công nghệ và vòng đời một cách độc lập trong giới hạn kiến trúc.

**Phạm vi quyền đọc/ghi nhỏ hơn.** Khi có vendor, bên đối tác hoặc mã nguồn nhạy cảm, repo riêng giúp áp dụng access boundary cụ thể hơn.

**Tăng tính chịu trách nhiệm về API công khai.** Vì không thể tùy tiện sửa mã của consumer cùng lúc, provider có xu hướng coi API/schema version như hợp đồng được publish.

### Chi phí và rủi ro

- Thay đổi liên service cần nhiều PR, thứ tự merge và release được điều phối.
- Nâng shared library cho 40 repo có thể đòi automation và phụ thuộc version hóa chặt.
- Khó phát hiện consumer bị ảnh hưởng nếu không có catalog dependency và contract registry.
- Tooling, bảo mật, pipeline template dễ bị lệch nếu các team sao chép cấu hình rồi quên cập nhật.
- Một thay đổi cần phối hợp có thể tạm thời ở trạng thái “repo A đã merge, repo B chưa”, cần quy trình compatibility.
- Tracing và chẩn đoán một lỗi không nên phụ thuộc vào việc ghép thủ công các revision từ từng repo.

**Polyrepo chỉ giúp giảm phối hợp khi ranh giới service và contract đủ ổn định.** Nếu mỗi thay đổi nhỏ phải sửa bốn repo cùng lúc, việc tách repo đang che giấu coupling kiến trúc.

## 5. Trục lựa chọn: mô hình phối hợp của nhóm

Thay vì bắt đầu bằng “repo nào tốt hơn”, hãy nhìn **kiểu thay đổi và quyền ra quyết định** của tổ chức.

| Mô hình phối hợp | Dấu hiệu | Hướng ưu tiên để cân nhắc |
| --- | --- | --- |
| Một nhóm nhỏ sở hữu nhiều service | Cùng người sửa API và consumer; thay đổi xuyên service thường xuyên | Monorepo có thể giảm chi phí điều phối |
| Nhiều nhóm nhưng dùng chung platform chuẩn | Cần refactor/lint/security rollout đồng bộ, có công cụ changed-target build | Monorepo với ownership rõ là phương án hợp lý |
| Nhiều nhóm có quyền phát hành độc lập | Hợp đồng tương đối ổn định; số thay đổi liên service thấp | Polyrepo thường phù hợp |
| Dịch vụ có dữ liệu hoặc mã nguồn nhạy cảm riêng | Yêu cầu phân quyền đọc/ghi, audit hoặc tách nhà thầu | Polyrepo hoặc repository riêng cho vùng nhạy cảm |
| Có platform team quản trị toolchain | Team muốn độc lập service nhưng cần chuẩn chung | Cả hai mô hình đều được; tập trung vào template, catalog và policy |
| Hệ thống chứa nhiều ngôn ngữ/stack | Build cần isolation mạnh, toolchains khác nhau | Polyrepo dễ cô lập; monorepo vẫn khả thi nếu build graph tốt |
| Các nhóm liên tục phải chỉnh cùng contract | Đang thiếu compatibility policy hoặc domain boundary sai | Cải thiện contract trước; repo không tự chữa coupling |

Đừng dùng **số service** làm tiêu chí duy nhất. Năm service của năm công ty khác nhau có nhu cầu phân quyền khác hẳn năm mươi service do một platform team quản lý với build system mạnh.

### Câu hỏi khảo sát thực tế

1. Trong 20–50 PR gần nhất, bao nhiêu PR phải sửa nhiều service?
2. Những thay đổi chéo đó là refactor source thật sự cần đi cùng nhau, hay do coupling hợp đồng cần được cải thiện?
3. Mỗi service có owner và lịch deploy/rollback riêng không?
4. Quyền đọc mã nguồn có thống nhất hay có nhóm/đối tác phải bị giới hạn?
5. Nếu service A thay đổi contract, team B phát hiện và xác nhận tương thích bằng cách nào?
6. Nếu shared library cần vá bảo mật gấp, cần bao lâu để tất cả consumer sử dụng bản đã vá?
7. Chi phí CI, thời gian clone/build và tần suất flaky test hiện tại ra sao?
8. Một ngày làm việc có bao nhiêu lần phải chuyển repository, đồng bộ local scripts hoặc tạo nhiều PR cho một thay đổi?

Hãy xem dữ liệu về **thời gian phối hợp, lead time và tần suất thay đổi chéo**, thay vì quyết định chỉ từ sở thích Git của từng người.

## 6. Atomic commit không phải atomic deployment

Một ưu điểm của monorepo là có thể commit sửa cả producer và consumer cùng lúc:

```text
Commit 7f1a:
  contracts/payment-event.avsc
  services/payments/Publisher.java
  services/orders/PaymentConsumer.java
```

Tuy nhiên production có thể đang chạy:

```text
Payment Service: revision 7f1a (new)
Orders Service:  revision 4c2b (old)
Inventory:       revision a8d0 (unchanged)
```

Nếu event mới không tương thích với consumer cũ, monorepo vẫn bị lỗi. Commit nguyên tử chỉ cho thấy **mã nguồn thay đổi trong cùng snapshot**, không bắt các service rollout cùng thời điểm. Rollout phân tán có network delay, canary, retry, rollback độc lập và một khoảng thời gian chạy lẫn phiên bản.

Do đó mọi hệ microservices phải thiết kế:
- **Backward compatibility:** producer mới không phá consumer cũ đang dùng.
- **Forward compatibility:** consumer mới có thể xử lý dữ liệu từ producer cũ khi cần.
- **Expand/contract migrations:** thêm khả năng mới trước, chuyển consumer sau, loại bỏ schema/field cũ cuối cùng.
- **Version-aware deployment:** xác định service nào đang chạy với contract/artifact version nào.

Monorepo hỗ trợ review thay đổi đa thành phần; polyrepo buộc biểu diễn nhiều phần qua PR/release riêng. Cả hai vẫn cần kiểm soát compatibility trong runtime.

## 7. Thay đổi API và event: phối hợp bằng contract, không bằng vị trí repo

Ví dụ Orders tiêu thụ event `PaymentSucceeded` có schema:

```json
{
  "paymentId": "pay-42",
  "orderId": "order-83",
  "status": "SUCCEEDED",
  "amount": "250000.00"
}
```

Payment team muốn đổi `orderId` thành `checkoutId`. Xóa field cũ ngay có thể khiến consumer cũ thất bại.

Lộ trình **expand → migrate → contract**:

1. **Expand:** producer bổ sung `checkoutId` mà vẫn giữ `orderId` trong giai đoạn chuyển; xác định quy tắc giá trị/semantics.
2. **Verify:** contract tests xác nhận consumer cũ vẫn đọc được event mới và consumer mới có thể đọc event cũ nếu điều này cần trong rollout.
3. **Migrate:** Orders cập nhật đọc trường mới, deploy và quan sát các instance/consumer group chuyển xong.
4. **Contract:** chỉ bỏ `orderId` khi các consumer hỗ trợ đã chuyển, dữ liệu/event lịch sử được xử lý theo chính sách và registry cho phép.
5. **Retire:** cập nhật tài liệu, schema compatibility checks và thời hạn ngừng hỗ trợ.

Trong monorepo, các sửa đổi source của producer/consumer có thể nằm cùng một PR nhưng vẫn triển khai theo các bước trên. Trong polyrepo, contract version và PR của từng consumer phải được liên kết qua issue/release plan, đồng thời CI provider xác minh những contract được hỗ trợ.

Với database, nguyên tắc tương tự: đừng xóa cột đang được version cũ đọc trong lúc service đang rolling deploy. Với gRPC/Protobuf, chú ý field numbers và reserved fields; với event schema registry, áp dụng compatibility mode phù hợp. Đừng chỉ xem đổi tên field là refactor nội bộ nếu dữ liệu đã qua ranh giới service.

## 8. Ownership và review: ai có quyền thay đổi phần nào?

### Trong monorepo

Cần mô tả owner theo đường dẫn, ví dụ GitHub CODEOWNERS:

```text
/services/orders/       @orders-team
/services/payments/     @payments-team
/services/inventory/    @inventory-team
/contracts/             @architecture-team
/tooling/               @platform-team
```

Đây là ví dụ pattern; review bắt buộc còn phụ thuộc branch protection và cấu hình hosting Git. CODEOWNERS không tự thay thế phân quyền đọc Git.

Quy tắc có thể gồm:
- PR sửa một service cần review của nhóm sở hữu.
- PR đổi contract công khai cần review của provider và đại diện consumer có liên quan.
- PR sửa build logic hoặc shared libraries cần platform owner.
- PR sửa nhiều service phải nêu phạm vi rollout và khả năng tương thích.
- CI chỉ chạy target bị ảnh hưởng, nhưng có trường hợp phải chạy kiểm tra toàn repository.

Rủi ro cần quản lý: người có quyền merge chung có thể tạo thay đổi sâu ở service họ không sở hữu nếu protections không được cấu hình; mono ownership phải thực thi trong quy trình.

### Trong polyrepo

Mỗi repo áp dụng owner/reviewer và branch protection riêng. Vấn đề chuyển sang **trách nhiệm kết nối**:
- Provider contract nằm ở đâu và ai quản lý version?
- Consumer có nhận thông báo khi provider thay breaking change không?
- Shared library có owner, release notes và lịch deprecation không?
- Team nào điều phối một change cần merge ba PR?
- Khi production lỗi, team nào truy vết tổ hợp release thực tế?

Nếu không trả lời được, polyrepo có thể có ownership cục bộ tốt nhưng thiếu owner của **hành trình nghiệp vụ xuyên service**.

## 9. Shared libraries: đừng để “dùng chung” biến thành coupling

Các service có thể cần dùng chung tracing, authentication helpers, logging conventions hoặc client SDK. Nhưng thư viện chung cần có boundary và versioning.

**Trong monorepo**, library có thể được tham chiếu trực tiếp bằng build graph:

```text
commerce/
  libraries/observability/
  services/orders/
  services/payments/
```

Một thay đổi ở `libraries/observability` có thể cần build/test tất cả consumer bị ảnh hưởng. Điều này giúp kiểm chứng ở cùng revision nhưng cũng có thể làm đổi hàng chục service nếu dependency không được quản lý.

**Trong polyrepo**, thư viện thường được publish thành artifact có version:

```text
com.example.platform:observability-starter:2.4.1
```

Mỗi service chủ động nâng version, cần audit consumer còn dùng version cũ và automation tạo PR cập nhật. Tránh phát hành cùng một artifact mutable dưới một version cố định vì làm mất tính tái lập.

Nên ưu tiên chia sẻ:
- Cross-cutting concerns ổn định: telemetry conventions, security primitives đã kiểm chứng, build conventions.
- Client SDK hoặc DTO được sinh từ **contract được version hóa**.
- Utilities tổng quát có API rõ ràng.

Nên thận trọng khi chia sẻ:
- Entity JPA, model database và domain aggregates giữa nhiều bounded context.
- “Common” module chứa business logic thay đổi liên tục và ép tất cả service nâng version cùng lúc.
- Cơ chế truy cập trực tiếp database của service khác.
- Shared library phụ thuộc trực tiếp vào cấu trúc internal implementation của nhiều service.

Nếu service Orders phải chờ Payments phát hành shared domain model mới để đổi một trạng thái riêng, vấn đề trước tiên là coupling, không đơn thuần là chọn repo chưa tối ưu.

## 10. Monorepo CI/CD: chạy đúng những target bị ảnh hưởng

Sai lầm phổ biến:

```text
Mỗi commit:
  build tất cả service
  chạy tất cả unit + integration + E2E
  build tất cả Docker images
  deploy tất cả service
```

Với 50 service, cách này dễ khiến thay đổi một file README kích hoạt hàng giờ CI. Monorepo cần **affected-target analysis** và cache đủ tin cậy.

### Mô hình phụ thuộc

```text
changed files
      |
      v
map path → build target
      |
      v
reverse dependency graph
      |
      +→ orders
      +→ payments
      +→ contracts-compatibility
      |
      v
compile/test/package affected targets
      |
      v
publish immutable artifacts
      |
      v
deploy selected services only
```

Ví dụ:

| File thay đổi | Những việc nên cân nhắc chạy |
| --- | --- |
| `services/orders/src/**` | Orders compile, unit, component, integration liên quan |
| `contracts/payment-event.avsc` | Validate schema, provider/consumer contract tests, affected services |
| `libraries/observability/**` | Tests của library và mọi service thực sự phụ thuộc vào nó |
| `tooling/build-logic/**` | Kiểm tra build rộng hơn vì rule có thể tác động toàn repo |
| `infra/gateway/**` | Gateway tests và smoke/route checks liên quan |
| `docs/**` | Lint docs/link nếu cần; không tự deploy tất cả service |

Chỉ dùng file path filter là chưa đủ khi có transitive dependencies. Nếu library A thay đổi và Orders phụ thuộc A, Orders phải được đưa vào affected set dù `services/orders` không có file được sửa.

Nếu phân tích thay đổi không thể xác định ảnh hưởng an toàn, fallback hợp lý là chạy phạm vi rộng hơn; **không bỏ qua test vì graph thất bại**.

### Cache và tính tái lập

- Cache theo toolchain, dependency lock và input thực sự; tránh cache sai giữa các branch.
- Phân biệt artifact build của từng service và tag version theo immutable Git SHA hoặc digest.
- Không dùng mutable `latest` để chứng minh test ở PR khớp image triển khai.
- Không để một workflow deploy mọi service chỉ vì repository có một revision mới.
- Khi thư viện build dùng chung thay đổi, tuyên bố rõ downstream target nào bị rebuild.

Một số tổ chức dùng Bazel, Nx, Pants, Turborepo hoặc build orchestration riêng. Với Gradle multi-project, Gradle có project dependency graph, configuration cache/build cache khi cấu hình phù hợp và khả năng gọi task theo project. Công cụ nào cũng cần policy affected-target phù hợp; không nên coi tên tool là bảo đảm CI tối ưu.

## 11. Ví dụ monorepo dùng Gradle multi-project

Một cấu trúc Java/Spring Boot minh họa:

```text
commerce/
  settings.gradle
  build.gradle
  gradle/wrapper/
  services/
    orders/build.gradle
    payments/build.gradle
  libraries/
    tracing/build.gradle
```

`settings.gradle` có thể khai báo project paths (cần khớp layout thực tế):

```groovy
rootProject.name = 'commerce'

include ':services:orders'
include ':services:payments'
include ':libraries:tracing'
```

Mỗi service có build task riêng:

```text
./gradlew :services:orders:test
./gradlew :services:orders:bootJar
./gradlew :services:payments:test
./gradlew :services:payments:bootJar
```

Các lệnh minh họa cách gọi project task, không phải hướng dẫn chạy trực tiếp trên một repository cụ thể. Trên Windows có thể dùng `gradlew.bat` nếu phù hợp.

Ví dụ Orders phụ thuộc thư viện tracing nhưng không phụ thuộc source code Payments:

```groovy
dependencies {
    implementation project(':libraries:tracing')
    // Orders tương tác với Payments qua client/protocol contract.
}
```

Nếu Payments triển khai riêng, **không tạo dependency Gradle trực tiếp vào module runtime của Payments** chỉ để dùng vài DTO. Hãy sinh client từ OpenAPI/Protobuf hoặc dùng artifact contract/SDK có version và ownership rõ.

Trong mono, Gradle composite hoặc multi-project giúp tái sử dụng build conventions nhưng chỉ tốt khi không tạo vòng dependency và không ép tất cả module chạy chung một tiến trình Spring Boot.

## 12. Polyrepo CI/CD: phiên bản artifact và tương thích là trung tâm

Với polyrepo, mỗi repo có pipeline độc lập:

```text
orders-service.git
  PR → test → build orders image → publish digest → deploy orders

payments-service.git
  PR → test → build payments image → publish digest → deploy payments

commerce-contracts.git
  PR → schema validation → compatibility verification
                             |
                             +→ báo consumer/provider cần kiểm tra
```

Các thực hành quan trọng:
1. **Mỗi artifact có identity bất biến:** version, commit SHA, image digest, SBOM khi yêu cầu.
2. **Mỗi contract có version/scheme rõ:** consumer biết cần artifact nào; provider biết các contract còn được hỗ trợ.
3. **Release notes có tác động:** ghi breaking changes, migration và deprecation window.
4. **Dependency automation:** bot tạo PR cập nhật SDK, client, shared library và kiểm tra CI ở consumer.
5. **Cross-repo orchestration:** thay đổi cần nhiều repo có issue/plan liên kết và các mốc “provider compatible”, “consumer migrated”, “old path retired”.
6. **Service catalog:** ánh xạ owner, repo, runtime service, API schema, topic, database và deployment environment.
7. **Compatibility gate:** không publish breaking API chỉ vì producer build thành công.

Ví dụ luồng publish một library:

```text
shared-security.git
   |
   +--> test security contracts
   +--> publish 2.6.0
   |
   +--> dependency bot opens PR in orders.git
   +--> dependency bot opens PR in payments.git
   |
   +--> mỗi consumer tự test, review, release
```

Cơ chế này tốn chi phí điều phối, nhưng đổi lại mỗi consumer chọn thời điểm nâng version trong giới hạn deadline bảo mật và compatibility.

## 13. Contract tests và consumer-driven compatibility

**Contract testing** là cơ chế quan trọng trong cả hai chiến lược repo. Một provider “pass unit tests” không chứng minh consumer còn đọc được response hoặc event sau thay đổi.

### HTTP contract

Consumer Orders thực sự cần từ Payments:

```http
GET /internal/payments/pay-42
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json

{
  "paymentId": "pay-42",
  "status": "SUCCEEDED"
}
```

Consumer contract nêu behavior mà Orders dựa vào; provider verification chạy với implementation Payments và các state tương ứng. Nếu provider đổi `status` thành object không tương thích, gate phải bắt được trước release.

### Event contract

Với Kafka, RabbitMQ hoặc event bus, contract gồm schema, topic, key, partitioning assumptions, semantic của event, versioning, ordering và xử lý event trùng. Schema registry/compatibility checks giúp nhưng không thể bảo đảm mọi thay đổi semantic hợp lệ. Đổi `amount` từ “đơn vị tiền nhỏ nhất” sang “đơn vị tiền nguyên” có thể không đổi kiểu dữ liệu mà vẫn phá nghiệp vụ.

### Liên kết contract với model repo

- **Monorepo:** PR có thể sửa provider, consumer và contract cùng lúc; CI kiểm tra tất cả affected consumers trước merge.
- **Polyrepo:** consumer publish expectation vào broker/registry hoặc artifact; provider CI kiểm tra những consumer versions đang active. Contract có thể ở repo riêng hoặc do từng consumer sở hữu, tùy quy trình.
- **Cả hai:** runtime có thể chứa nhiều version; cần verification dựa trên môi trường đang triển khai và dự kiến deploy, không chỉ branch mới nhất.

Contract test bổ sung cho integration/E2E; không thay thế kiểm tra auth, TLS, network và hành trình nghiệp vụ.

## 14. Tần suất thay đổi chéo: dấu hiệu nên đo

Giả sử nhóm khảo sát 40 thay đổi gần đây:

| Chỉ số ví dụ | Giá trị giả định |
| --- | ---: |
| PR chỉ ảnh hưởng một service | 26 |
| PR cần sửa ít nhất hai service | 10 |
| PR chỉ sửa tooling/contract/shared library | 4 |
| Số thay đổi liên service do breaking contract | 7 |
| Lead time trung vị để phối hợp ba PR ở các repo | 3 ngày |
| Lead time trung vị cho thay đổi một service | 4 giờ |

Đây là **số liệu minh họa, không phải số đo thực tế**. Nếu hầu hết thay đổi chéo do provider phá contract, chuyển về monorepo sẽ giúp review nhưng không giải quyết nguyên nhân thiếu versioning. Nếu thay đổi chéo là nâng một library nền tảng và CI đã có dependency graph tốt, monorepo có thể giảm lặp công việc.

Nên đo:
- **Cross-service change rate:** tỷ lệ thay đổi cần sửa từ hai service trở lên.
- **Coordination lead time:** thời gian đợi approve và merge cross-repo.
- **Independent deploy rate:** phần trăm release chỉ cập nhật một service.
- **Change failure rate:** lỗi deployment do tương thích hoặc môi trường.
- **Mean time to restore:** thời gian rollback/recover sau sự cố.
- **CI feedback latency:** thời gian từ commit đến kết quả có thể hành động.
- **Shared dependency lag:** consumer chậm nâng version theo các bản vá quan trọng.
- **Ownership clarity:** thay đổi hợp đồng có owner/provider/consumer rõ không.

Đừng lấy “số repo ít hơn” hoặc “số PR ít hơn” làm mục tiêu cuối. Mục tiêu là giảm thời gian phối hợp **mà vẫn giữ tính đúng đắn và độc lập release**.

## 15. Ma trận lựa chọn dựa trên tiêu chí có trọng số

Một cách ra quyết định có thể cho điểm 1–5 theo thực tế tổ chức:

| Tiêu chí | Monorepo thường có lợi khi | Polyrepo thường có lợi khi |
| --- | --- | --- |
| Atomic source changes | Nhiều thay đổi cần sửa nhiều service cùng lúc | Hầu hết thay đổi gói trong từng service |
| Quyền truy cập mã nguồn | Các nhóm có quyền xem source tương tự | Cần phân quyền tách biệt theo team/vendor |
| Release autonomy | Team chấp nhận repo chung, pipeline tách service | Team muốn pipeline/release governance riêng |
| Build infrastructure | Có affected-target graph/cache mạnh | Build toolchain khác nhau, không có platform chung |
| Shared dependency updates | Cần refactor đồng loạt thường xuyên | Library ổn định, publish và version tốt |
| Compliance/security | Policy repo đồng nhất | Có repository cần audit/retention/secret policy riêng |
| Developer experience | Cần điều hướng đa service nhanh | Developer thường chỉ làm một hoặc vài service |
| Cross-team coordination | Một team hoặc nhóm hợp tác rất chặt | Nhiều nhóm có contract rõ và sở hữu độc lập |

Cách dùng:
1. Chọn tiêu chí quan trọng và đặt trọng số, ví dụ security boundary có trọng số lớn hơn tốc độ local build trong tổ chức được quản lý chặt.
2. Cho điểm dựa trên số liệu công việc thật, không chỉ dựa vào niềm tin công nghệ.
3. Chạy thử một kịch bản như nâng shared library, sửa API và hotfix production trong cả phương án khả thi.
4. Xem lại những giả định khó thay đổi: quyền truy cập, ranh giới team và topology pipeline.
5. Chọn phương án có chi phí phối hợp thấp **trong các ràng buộc không thương lượng**.

Không có ngưỡng “trên 20 service phải polyrepo” hay “dưới 10 service phải monorepo”. Điểm số là công cụ làm rõ tradeoff, không phải quyết định thay con người.

## 16. Một ví dụ lựa chọn cho tổ chức phát triển thương mại điện tử

Giả sử tổ chức có ba nhóm:
- **Commerce Team:** quản lý Orders, Cart và Inventory; thay đổi chéo thường xuyên vì hành trình checkout.
- **Payments Team:** xử lý thanh toán, quyền truy cập giới hạn, audit và release riêng.
- **Platform Team:** xây tracing, build conventions, API guidelines và hạ tầng CI.

Một phương án **hybrid** hợp lý có thể là:

```text
commerce-core.git
  services/orders/
  services/cart/
  services/inventory/
  contracts/checkout/

payments-service.git
  src/
  contracts/payment/

platform-libraries.git
  tracing/
  security-starter/
  build-conventions/
```

Commerce có thể phối hợp refactor nhanh trong một repo, Payments có quyền và pipeline riêng, Platform publish libraries. Với phương án này, vẫn cần quy trình:
- Orders ↔ Payments giao tiếp qua versioned APIs/events.
- Payments không trực tiếp truy cập schema DB của Orders.
- Mọi shared library publish immutable versions hoặc có cách quản lý compatibility tương đương.
- Trace/metrics theo dõi hành trình checkout xuyên repository.
- Có owner chịu trách nhiệm kiểm tra critical E2E checkout và sự cố cross-team.

Hybrid không phải lựa chọn mặc định. Nó có thêm complexity ở ranh giới repo, nhưng có thể phù hợp nếu **các nhóm có điều kiện phối hợp và quyền truy cập khác nhau**. Thay vì ép toàn bộ hệ thống theo một mô hình, có thể nhóm những bounded contexts phối hợp chặt và tách các vùng có governance riêng.

## 17. Ảnh hưởng đến môi trường phát triển nội bộ

### Monorepo

Lợi ích: developer clone một lần, tìm contract và sửa nhiều service ngay trên cùng branch. Nhưng môi trường local có thể nặng nếu cố chạy toàn bộ hệ thống.

Nên cung cấp:
- Lệnh chạy một service và dependency tối thiểu.
- Docker Compose hoặc testcontainer profiles cho một nhóm service liên quan.
- Build cache và task target rõ để tránh khởi động mọi service.
- Script tạo dữ liệu giả, seed DB theo namespace/tenant test.
- Documentation về impacted services khi sửa shared contract.

### Polyrepo

Developer thường cần checkout một service và 1–2 repo phụ thuộc. Nếu mỗi repo dùng phiên bản tool khác nhau, onboarding có thể phức tạp.

Nên cung cấp:
- Một developer portal/service catalog để tìm repo, owner, API và môi trường.
- Bootstrap script có version, không dùng những command copy-paste đã lỗi thời.
- Contract artifact/sandbox hoặc mock server có hành vi đáng tin.
- Môi trường ephemeral cho kiểm thử nhiều service.
- Cơ chế liên kết trace/release version qua nhiều repo.

**Không nên đòi developer có thể chạy toàn bộ production topology trên laptop** để sửa một endpoint. Mô hình local tối thiểu có thể khác mô hình repo và runtime production.

## 18. Quyền, bảo mật và supply chain

Repository là ranh giới quyền quản lý Git, nhưng không phải tường bảo mật cho runtime.

**Monorepo cần cân nhắc:**
- Quyền đọc: nhiều hosting platform cấp quyền đọc toàn repo; CODEOWNERS không chặn đọc source.
- CI workflow: thay đổi từ một thư mục không nên mặc định được dùng secret deploy của mọi service.
- Trusted runners và permissions: nguyên tắc least privilege cho từng job/environment.
- Artifact provenance: biết image nào được build từ path, commit và dependency nào.
- Thư viện chung: lỗ hổng trong build logic có thể ảnh hưởng nhiều service.

**Polyrepo cần cân nhắc:**
- Đồng nhất dependency scanning, SAST, secret scanning và branch protection.
- Template CI được version hóa; tránh các repo bị bỏ lại trên phiên bản lỗi thời.
- Danh sách người có quyền publish image/artifact ở từng repo.
- Chính sách ký artifact, SBOM và phản ứng lỗ hổng trên nhiều repo.
- Secret/token dùng cho cross-repo automation không được cấp quyền rộng không cần thiết.

**Không lưu secret trong mã nguồn**, dù là monorepo hay polyrepo. Secret Manager, workload identity, môi trường CI và quy trình rotation vẫn thuộc kiến trúc bảo mật riêng. Tách repository không bảo đảm rằng container image hoặc service account sẽ được cô lập đúng.

## 19. Mẫu điều phối một thay đổi liên service

Ví dụ: Payments thêm trạng thái `PENDING_REVIEW`; Orders và Notifications cần hiểu trạng thái mới.

### Trong monorepo

```text
Ticket: PAYMENT-341
  1. Cập nhật contract + test compatibility
  2. Cập nhật Orders consumer xử lý PENDING_REVIEW
  3. Cập nhật Notifications template/logic
  4. Cập nhật Payments producer
  5. CI kiểm tra affected components và provider/consumer contracts
  6. Merge một PR khi source hợp lệ
  7. Deploy consumers tương thích trước
  8. Deploy producer có trạng thái mới
  9. Quan sát rồi kết thúc migration
```

Bước 7–9 vẫn cần thực hiện tuần tự và có thể chạy qua nhiều deployment, mặc dù source nằm trong cùng commit.

### Trong polyrepo

```text
Ticket: PAYMENT-341
  - contracts.git PR → release contract 1.7
  - orders.git PR → hỗ trợ PENDING_REVIEW
  - notifications.git PR → hỗ trợ trạng thái mới
  - payments.git PR → bắt đầu phát trạng thái mới

  Dependency gate:
    consumers deployed compatible
         ↓
    producer may emit new state
```

Nếu provider merge trước nhưng chưa được phép emit new state, dùng feature flag hoặc compatibility mode có owner và deadline rõ ràng. Đừng dùng việc “merge xong” làm tín hiệu tự động phát dữ liệu không tương thích.

Trong cả hai mô hình cần một **release coordination record** chứa owner, contracts, thứ tự deploy, nơi đo usage, rollback và điều kiện bỏ hỗ trợ cũ.

## 20. Rollback và phát hành độc lập

Rollback phải xem xét cả sự tương thích data và message, không chỉ image:

- Producer mới đã ghi event schema mới; rollback consumer về bản cũ có còn đọc được không?
- DB migration đã chạy; schema cũ có bị xóa không? Không nên rollback bằng cách drop dữ liệu mới.
- Một service đã chuyển contract sang version mới; các service còn lại có giữ được compatibility không?
- Canary lỗi ở một service có làm hỏng toàn hành trình không?
- Retry, queue và event lịch sử có thể quay lại sau rollout không?

Mô hình tốt:
1. Mỗi service có image digest, revision và deployment record.
2. Mỗi thay đổi contract có cửa sổ hỗ trợ rõ.
3. Rollback một service chỉ thực hiện khi version quay về còn tương thích với trạng thái data/producer đang tồn tại.
4. Test hỗn hợp phiên bản (old/new) được chạy ở mức cần thiết.
5. Nếu rollback không an toàn do migration dữ liệu, chọn forward fix hoặc cơ chế khôi phục đã định nghĩa.

**Independent deploy** nghĩa là một service có thể phát hành mà không yêu cầu deploy đồng thời tất cả service khác; không phải không cần thông báo hay kiểm tra hợp đồng. Đây là thuộc tính kiến trúc và quy trình release, không tự sinh từ việc có repo riêng.

## 21. Chuyển từ monorepo sang polyrepo

Khi tổ chức lớn lên và cần quyền/pipeline độc lập, có thể tách một service khỏi monorepo theo thứ tự:

1. **Làm rõ ranh giới:** service sở hữu dữ liệu, API, deployment và dependencies riêng. Không chuyển nếu vẫn phụ thuộc source nội bộ của service khác.
2. **Publish contract và shared libraries:** thay dependency source không đúng boundary bằng artifact/version hoặc generated clients.
3. **Tạo repository đích:** có CI, branch protection, secret scanning, CODEOWNERS và build từ toolchain có thể tái lập.
4. **Chuyển source/history theo kế hoạch:** có thể giữ lịch sử liên quan bằng Git tooling khi cần audit; không tự ý rewrite nhánh production mà thiếu kế hoạch.
5. **Thiết lập pipeline độc lập:** build/test/image publish/deploy cho riêng service, có provenance.
6. **Chạy song song có kiểm soát:** xác minh binary/artifact và contract trong giai đoạn chuyển; tránh hai pipeline cùng deploy một service.
7. **Chuyển quyền sở hữu:** cập nhật service catalog, runbook, dashboards, incident contacts và quyền CI.
8. **Ngừng đường build cũ:** sau khi đã xác minh, loại bỏ target và workflow obsolete có kiểm soát.

Rủi ro hay gặp: tách thư mục Git thành repo mới nhưng quên service vẫn dùng build logic, version catalog hoặc generated code nội bộ. Đó là coupling phải được xử lý trước.

## 22. Chuyển từ polyrepo sang monorepo

Khi nhiều repo phối hợp quá chặt và tooling phân tán, có thể hợp nhất theo các bước:

1. Chọn grouping hợp lý theo bounded context/team, không nhất thiết gom tất cả công ty.
2. Tạo layout đường dẫn rõ để tránh trùng tên package, module và file config.
3. Chọn cách nhập lịch sử: giữ lịch sử từng repo nếu cần audit, hoặc snapshot có ghi nguồn gốc và mapping rõ ràng.
4. Chuẩn hóa toolchain/build conventions mà không ép mọi service chạy cùng runtime process.
5. Tạo CODEOWNERS, path-level CI, dependency graph, policies cho thay đổi shared library.
6. Giữ image/version/deploy unit riêng cho từng service.
7. Xác minh artifact trước/sau chuyển và kiểm tra compatibility.
8. Chuyển pipeline từng service; chỉ tắt workflow repo cũ sau khi deploy từ repo mới hoạt động.
9. Ghi lại revision mapping để truy vết incident xảy ra trước/sau migration.

Monorepo không nên trở thành lý do xóa toàn bộ versioning và contract tests. Services vẫn có quyền lifecycle độc lập.

## 23. Khi nào nên hoãn quyết định đổi repository?

Một số triệu chứng thường bị quy cho mô hình Git nhưng nguyên nhân nằm ở nơi khác:

| Triệu chứng | Nguyên nhân có thể thực sự | Việc nên kiểm tra trước |
| --- | --- | --- |
| Mỗi release phải deploy 10 service | Breaking API, shared DB hoặc distributed transaction không được kiểm soát | Contract compatibility và domain boundaries |
| PR monorepo rất chậm | CI chạy tất cả test, thiếu cache/affected graph | Targeted CI, build cache, parallelism |
| Polyrepo cập nhật security chậm | Thiếu dependency bot và service catalog | Artifact versioning, ownership, upgrade automation |
| Team thường bị conflict trong một file | Shared configuration hoặc module sở hữu không rõ | Tách config và định nghĩa ownership |
| Staging E2E flaky | Dữ liệu chung, async timing, environment drift | Test isolation, trace, deterministic waits |
| Hotfix của service không thể rollback độc lập | DB migration và event không tương thích | Expand/contract, deployment policy |
| Secret bị lộ chéo giữa các workflow | CI permissions quá rộng | Least privilege và environment secrets |
| Khó truy vết lỗi cross-service | Thiếu release inventory/observability | Trace, image digest và service catalog |

Chuyển monorepo ↔ polyrepo là thay đổi lớn tới quy trình và toolchain. Nếu coupling vẫn nguyên, có thể chỉ chuyển chi phí từ CI sang con người, hoặc từ nhiều PR sang nhiều test toàn repository.

## 24. Checklist ra quyết định cho nhóm thiết kế

Trước khi chọn mô hình, thảo luận và ghi rõ:

- **Team ownership:** mỗi service có owner, reviewer, on-call và quyền deploy không?
- **Change locality:** phần lớn thay đổi nằm trong một bounded context hay trải qua nhiều?
- **Deployment autonomy:** có thể phát hành và rollback từng service mà vẫn compatible không?
- **Contract maturity:** OpenAPI/event schema/consumer-driven tests được version và verify chưa?
- **Shared libraries:** các dependency chung có version, owner, release process và impact graph không?
- **CI performance:** chỉ build/test targets bị ảnh hưởng hay luôn chạy tất cả?
- **Security and access:** có yêu cầu tách quyền đọc code, CI secrets, compliance không?
- **Developer workflow:** onboarding, local setup, code search và cross-service debugging mất bao lâu?
- **Operational evidence:** dashboards có biết revision/image digest nào đang chạy?
- **Migration cost:** nếu đổi repo, ai duy trì history, pipelines, ownership, catalog và rollback?

Câu trả lời cần gắn với **tình huống thực tế**. Ví dụ “chúng tôi triển khai Payments độc lập 20 lần/tháng, chỉ thay contract một lần/quý và cần quyền đọc riêng” là một luận cứ cụ thể để cân nhắc polyrepo. “Commerce Team sửa Orders và Inventory trong cùng hai phần ba tính năng, với CI affected-target tốt” là luận cứ để cân nhắc đặt chúng cùng monorepo.

## 25. Bài tập và tình huống thực hành

### Bài tập 1 — Nhận diện boundary

Một repository chứa 12 service, mỗi service có Docker image, database và pipeline riêng. Giải thích vì sao đó có thể vẫn là microservices và chỉ ra yếu tố nào sẽ làm độc lập phát hành bị phá dù tất cả service nằm ở repo khác nhau.

### Bài tập 2 — Đề xuất chiến lược cho 3 nhóm

Commerce gồm Orders/Inventory thường xuyên thay đổi cùng nhau; Payments có yêu cầu bảo mật cao và release riêng; Platform xây tracing library. Hãy đề xuất monorepo, polyrepo hoặc hybrid, vẽ layout source, xác định ownership, contract và CI boundary.

### Bài tập 3 — Thiết kế affected CI

Trong monorepo, một PR chỉ sửa `libraries/security-starter`. Orders, Payments và Inventory dùng library này; Search không dùng. Hãy mô tả cách dependency graph chọn target cần kiểm thử và điều kiện buộc full regression thay vì chỉ path filter.

### Bài tập 4 — Thay đổi contract không gián đoạn

Payments muốn đổi tên trạng thái `AUTHORIZED` thành `RESERVED`. Hãy lập thứ tự sửa contract, consumer, producer, versioning và rollout sao cho hai phiên bản consumer vẫn có thể chạy trong migration. Thảo luận khả năng rollback sau khi event mới đã được phát.

### Bài tập 5 — Vượt qua nhiều repository

Một thay đổi cần ba PR ở three service repos. Hãy thiết kế release coordination record chứa issue liên kết, owner, dependency gate, kiểm thử, thứ tự deploy và cách xác minh môi trường đã chuyển sang version tương thích.

### Bài tập 6 — Migration không đổi behavior

Lập kế hoạch chuyển Orders từ monorepo sang repo riêng. Liệt kê những thứ phải giữ nguyên: API contract, database ownership, image provenance, CI gate, deployment, observability, access và source history mapping.

## 26. Tổng kết và nguyên tắc áp dụng

- **Repository là boundary của source control và phối hợp; service và deployment là boundaries kiến trúc khác.**
- **Monorepo hữu ích khi thay đổi liên quan có thể được review cùng nhau** và tổ chức có affected-target CI, build graph, owner theo path.
- **Polyrepo hữu ích khi ownership, access và nhịp phát hành thật sự độc lập**, đồng thời contract, versioning và service catalog đủ trưởng thành.
- **Commit chung không tạo deployment nguyên tử.** Mọi microservices vẫn cần backward/forward compatibility và expand/contract migration.
- **Shared code và database coupling phải được quản lý theo boundary**, tránh biến reuse thành vòng dependency.
- **CI/CD phải phản ánh dependency và rủi ro**, không chạy mọi thứ mù quáng hoặc bỏ sót consumer vì thay đổi chỉ nằm ở contract.
- **Hybrid có thể là lựa chọn có chủ đích** khi một số bounded contexts phối hợp chặt còn những service khác cần governance riêng.
- **Chọn dựa trên dữ liệu:** change locality, coordination lead time, independent deploy rate, access constraints và chi phí CI.

Câu hỏi quyết định là: **Cách tổ chức nào giúp những nhóm thật sự phải phối hợp làm việc nhanh và an toàn hơn, trong khi vẫn cho phép từng service phát hành và hồi phục theo hợp đồng của mình?**

### Tài liệu để tiếp tục nghiên cứu

- GitHub — About code owners: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners
- GitHub Actions — Workflow syntax: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- Gradle — Multi-project builds: https://docs.gradle.org/current/userguide/multi_project_builds.html
- Gradle — Build cache: https://docs.gradle.org/current/userguide/build_cache.html
- Martin Fowler — Monorepo: https://martinfowler.com/articles/monorepo.html
- Google SRE Workbook — CI/CD and release engineering: https://sre.google/workbook/release-engineering/
- Pact — Consumer-driven contract testing: https://docs.pact.io/

Các layout, giá trị đo và workflow trong bài mang tính minh họa. Khi áp dụng, cần dựa trên quyền repository, CI platform, Gradle hoặc build system thực tế, contract hiện hành và chính sách phát hành của từng tổ chức.
