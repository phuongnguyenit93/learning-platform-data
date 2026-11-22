# Giữ khả năng kiểm thử và phát hành độc lập khi kiến trúc cho phép

Trong một hệ thống gồm nhiều dự án hoặc service, một thay đổi ở repository này có thể ảnh hưởng đến repository khác. Một API thay đổi có thể làm consumer lỗi; một thư viện dùng chung được nâng phiên bản có thể ảnh hưởng nhiều ứng dụng; một schema database mới có thể yêu cầu nhiều service cùng cập nhật. Nếu mỗi thay đổi đều kích hoạt toàn bộ pipeline của mọi dự án, CI/CD sẽ chậm, tốn tài nguyên và tạo sự phụ thuộc phát hành không cần thiết.

Mục tiêu của pipeline nhiều dự án (multi-project pipelines) là tổ chức việc kiểm thử, phối hợp và phát hành giữa các repository/service theo đúng quan hệ phụ thuộc. **Dự án nên có thể kiểm thử và phát hành độc lập khi hợp đồng, dữ liệu và kiến trúc cho phép; khi có phụ thuộc thực sự, pipeline phải thể hiện và kiểm soát sự phối hợp đó.**

Đây là năng lực thuộc **DEVOPS_CI_CD_FUNDAMENTALS**: xây dựng tư duy CI/CD từ sự kiện Git, pipeline dưới dạng mã, build và kiểm thử tự động đến quản lý artifact, môi trường, cổng chất lượng, phát hành có truy vết, bảo vệ bí mật, xác minh sau triển khai và khả năng quay lui.

## 1. Multi-project pipeline giải quyết vấn đề gì?

Một tổ chức có thể chia mã nguồn thành nhiều repository:

- `web-frontend`: giao diện người dùng.
- `orders-api`: xử lý đơn hàng.
- `catalog-api`: cung cấp sản phẩm và giá.
- `shared-contracts`: schema hoặc API contract.
- `platform-infra`: hạ tầng và cấu hình triển khai.

Các dự án có pipeline riêng, nhưng chúng không hoàn toàn độc lập. Frontend gọi orders-api; orders-api đọc catalog-api; nhiều service dùng chung contract hoặc thư viện; platform-infra quản lý môi trường triển khai.

Nếu mọi commit trong một repository đều kích hoạt build và deploy của tất cả repository khác, một thay đổi tài liệu ở frontend cũng có thể khiến pipeline backend chạy lại. Cách làm này làm tăng thời gian chờ và che khuất quan hệ phụ thuộc thực tế.

Multi-project pipeline giúp:

- Chạy kiểm tra tại đúng repository có thay đổi.
- Kích hoạt dự án phụ thuộc khi hợp đồng hoặc artifact liên quan thay đổi.
- Chia sẻ kết quả và artifact qua ranh giới dự án có kiểm soát.
- Phối hợp các lần phát hành cần thứ tự hoặc approval chung.
- Theo dõi release từ source project đến consumer và môi trường.
- Giữ quyền sở hữu và trách nhiệm của từng nhóm rõ ràng.

Multi-project pipeline không có nghĩa mọi repository phải deploy cùng nhau. Mục tiêu là phối hợp theo dependency graph và hợp đồng thực tế, không tạo thêm coupling chỉ vì các dự án nằm trong cùng một hệ thống.

## 2. Phân biệt repository, project, service và deployment unit

Các khái niệm này có thể trùng nhau trong một tổ chức nhỏ, nhưng không nên mặc định chúng là một:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Repository | Nơi lưu source và lịch sử thay đổi | orders-api Git repository |
| Project | Đơn vị quản lý mã, pipeline, owner hoặc quyền | Commerce Orders project |
| Service | Thành phần chạy và cung cấp chức năng | Orders API |
| Package/library | Thành phần được build và tiêu thụ bởi dự án khác | order-client |
| Deployment unit | Đơn vị được triển khai hoặc rollback | Container image orders-api |
| Product/system | Nhiều service phối hợp để cung cấp giá trị | Nền tảng commerce |

Một monorepo có thể chứa nhiều service và nhiều deployment unit. Một service cũng có thể lấy mã từ nhiều repository. Vì vậy, thiết kế pipeline cần dựa trên ownership, dependency và deployment boundary, không chỉ dựa trên tên folder.

Đơn vị phát hành độc lập nên là thành phần có thể được build, kiểm thử, cấu hình, triển khai và rollback theo một hợp đồng rõ ràng. Nếu hai module luôn phải thay đổi cùng nhau vì chia sẻ state hoặc schema không tương thích, có thể chúng chưa có ranh giới phát hành độc lập.

## 3. Monorepo và multirepo

Hai cách tổ chức source phổ biến có ưu và nhược điểm khác nhau:

| Tiêu chí | Monorepo | Multirepo |
| --- | --- | --- |
| Source | Nhiều dự án trong một repository | Mỗi dự án hoặc nhóm thành phần có repository riêng |
| Thay đổi đồng bộ | Có thể thay nhiều thành phần trong một commit/PR | Cần nhiều PR hoặc quy trình phối hợp |
| Quyền và ownership | Cần quy ước theo folder/project | Có thể tách quyền ở cấp repository |
| Pipeline | Cần path filtering và dependency graph | Cần trigger và artifact handoff giữa repository |
| Dependency | Có thể dùng workspace/local package | Thường qua version package/API hoặc artifact |
| Release | Có thể độc lập nếu build/deploy unit được tách | Có thể độc lập theo repository, nhưng vẫn phụ thuộc contract |

Monorepo không bắt buộc phải có một pipeline duy nhất. Có thể dùng path filter, build graph và cache để chỉ chạy pipeline của những dự án bị ảnh hưởng cùng consumer liên quan.

Multirepo cũng không tự tạo ra độc lập. Nếu mỗi lần deploy orders-api đều phải chờ catalog-api release một phiên bản mới dù contract không đổi, các pipeline vẫn bị coupling.

Hãy chọn cách tổ chức phù hợp với quy mô, quyền sở hữu, tốc độ thay đổi và khả năng quản lý dependency. Cả hai mô hình đều cần versioning, contract testing, artifact identity và release traceability.

## 4. Vẽ dependency graph trước khi thiết kế trigger

Dependency graph mô tả dự án nào phụ thuộc vào dự án, package hoặc contract nào. Có thể phân biệt:

- **Build dependency:** cần một package/tool/artifact để build.
- **Test dependency:** cần service hoặc fixture để kiểm thử.
- **Runtime dependency:** service gọi service khác khi chạy.
- **Deployment dependency:** cần triển khai một thành phần trước thành phần khác.
- **Ownership dependency:** cần approval hoặc hành động từ nhóm khác.

Ví dụ:

~~~mermaid
flowchart TD
    C["shared-contracts"] --> O["orders-api"]
    C --> K["catalog-api"]
    K --> O
    O --> W["web-frontend"]
    I["platform-infra"] --> O
    I --> K
    I --> W
~~~

Sơ đồ cho thấy orders-api phụ thuộc contract và catalog-api; frontend phụ thuộc orders-api; các thành phần triển khai dùng hạ tầng do platform-infra quản lý.

Không phải mọi cạnh trong graph đều cần trigger pipeline ngay lập tức. Ví dụ:

- Thay đổi README trong catalog-api không nhất thiết phải build orders-api.
- Thay đổi API schema của catalog có thể cần contract test với orders-api.
- Thay đổi base image dùng chung có thể cần build lại các image phụ thuộc.
- Thay đổi hạ tầng production có thể cần integration test hoặc approval của nhiều service.

Mỗi cạnh nên có loại dependency, phiên bản/hợp đồng, owner và điều kiện kích hoạt. Điều đó giúp tránh chạy thừa pipeline hoặc bỏ sót consumer bị ảnh hưởng.

## 5. Giữ ranh giới dự án qua hợp đồng ổn định

Khả năng phát hành độc lập phụ thuộc vào mức độ ổn định của hợp đồng giữa các thành phần:

- API contract: endpoint, method, schema request/response, status code và semantics.
- Event contract: tên event, schema, version và quy tắc tương thích.
- Library contract: public API, package version và hành vi được hỗ trợ.
- Data contract: quyền sở hữu dữ liệu, schema và quy tắc đọc/ghi.
- Operational contract: timeout, retry, authentication, rate limit và SLO.

Consumer nên phụ thuộc vào hợp đồng được công bố, không phụ thuộc vào implementation nội bộ của provider. Provider cần biết consumer nào đang dùng contract của mình trước khi loại bỏ hành vi cũ.

### 5.1. Thay đổi tương thích ngược

Các thay đổi thường ít gây coupling hơn:

- Thêm endpoint mới mà không thay endpoint cũ.
- Thêm field response tùy chọn.
- Thêm enum value nếu consumer được thiết kế để xử lý giá trị chưa biết.
- Thêm event field tùy chọn với default hợp lý.
- Thêm method vào library mà không đổi hành vi API cũ.

Các thay đổi có nguy cơ phá vỡ consumer:

- Xóa hoặc đổi tên field đang được sử dụng.
- Đổi kiểu dữ liệu hoặc ý nghĩa của field.
- Đổi endpoint, authentication hoặc status code.
- Làm một field tùy chọn trở thành bắt buộc.
- Thay đổi semantics của event hoặc thứ tự xử lý.
- Xóa package method hoặc nâng major version không tương thích.

Tương thích không chỉ là schema hợp lệ. Một field vẫn tồn tại nhưng thay đổi ý nghĩa nghiệp vụ cũng có thể phá vỡ consumer.

### 5.2. Expand-contract

Khi thay đổi không thể thực hiện một bước, dùng chiến lược expand-contract:

1. Expand: thêm API/field/schema mới theo cách phiên bản cũ vẫn hoạt động.
2. Migrate: cập nhật consumer để đọc/ghi theo hợp đồng mới.
3. Verify: xác nhận không còn consumer quan trọng sử dụng hợp đồng cũ.
4. Contract: xóa field/API/schema cũ trong một release riêng.

Không xóa contract cũ chỉ vì provider pipeline đã pass. Cần bằng chứng từ consumer inventory, telemetry hoặc migration record rằng việc sử dụng cũ đã kết thúc.

## 6. Contract testing để kiểm thử độc lập

Contract test xác minh provider và consumer hiểu cùng một hợp đồng mà không cần chạy toàn bộ hệ thống cho mọi thay đổi.

Có hai hướng kiểm tra:

- **Consumer-driven contract:** consumer công bố những tương tác mà nó cần; provider xác minh implementation đáp ứng các kỳ vọng đó.
- **Provider contract/schema validation:** provider xác minh response/event của mình tuân thủ schema đã công bố và các quy tắc tương thích.

Ví dụ:

1. orders-api khai báo cần GET /catalog/items/{id} với id, price và currency.
2. Consumer contract được lưu như artifact có version.
3. Pipeline của catalog-api lấy contract đã công bố và chạy provider verification.
4. Nếu thay đổi response làm contract fail, pipeline chặn thay đổi trước khi release.
5. Khi contract pass, provider có thể phát hành mà không cần deploy consumer cùng lúc.

Contract test không thay thế integration test hoàn chỉnh. Nó kiểm tra giao diện và kỳ vọng giữa hai thành phần; các lỗi về network, auth, timeout, database, message broker hoặc cấu hình môi trường vẫn cần kiểm tra ở các lớp khác.

## 7. Chọn kiểm thử theo phạm vi thay đổi

Pipeline nhiều dự án nên dùng nhiều lớp kiểm thử, mỗi lớp có phạm vi và tốc độ khác nhau:

| Lớp test | Phạm vi | Khi nào chạy |
| --- | --- | --- |
| Unit test | Module/class/function trong project | Mỗi thay đổi liên quan |
| Component test | Một service với dependency giả lập hoặc cục bộ | Mỗi PR hoặc merge |
| Contract test | Provider/consumer interface | Khi contract hoặc implementation liên quan thay đổi |
| Integration test | Một nhóm service và dependency thật | Theo PR quan trọng, merge hoặc lịch |
| End-to-end test | Luồng người dùng xuyên hệ thống | Trên môi trường tích hợp hoặc trước release |
| Compatibility test | Consumer với nhiều version provider hoặc ngược lại | Khi thay đổi API/schema/package |
| Deployment smoke test | Luồng quan trọng trên artifact đã deploy | Sau triển khai |

Không nên chạy toàn bộ end-to-end suite của hệ thống mỗi khi sửa một câu thông báo trong một service. Ngược lại, không nên chỉ chạy unit test khi thay đổi contract dùng chung.

Một policy có thể là:

- Thay đổi nội bộ không đổi contract: unit + component tests.
- Thay đổi API/event schema: unit + provider/consumer contract tests.
- Thay đổi database migration: migration compatibility + integration tests.
- Thay đổi base image hoặc shared library: build/test các consumer bị ảnh hưởng theo dependency graph.
- Release production: quality gates + deployment smoke + post-deploy observation.

## 8. Chạy pipeline có chọn lọc

Selective pipeline chỉ chạy những dự án và kiểm tra liên quan đến thay đổi. Cần phân biệt:

- File thay đổi trực tiếp.
- Dependency của dự án bị thay đổi.
- Consumer chịu ảnh hưởng từ contract hoặc package.
- Test bắt buộc theo policy dù không có file thay đổi.

Trong monorepo, mỗi project có thể khai báo tập đường dẫn ảnh hưởng đến pipeline của mình. Ví dụ workflow của orders project chạy khi mã orders hoặc contract dùng chung thay đổi:

~~~yaml
name: Monorepo checks

on:
  pull_request:
    paths:
      - 'services/orders/**'
      - 'contracts/**'
      - 'libs/order-client/**'

jobs:
  orders:
    runs-on: ubuntu-latest
    steps:
      - run: ./scripts/test-orders.sh
~~~

Đây là ví dụ GitHub Actions cho một workflow riêng của orders project. Workflow catalog có thể khai báo paths riêng như services/catalog/** và contracts/**. Cú pháp path filter và cách xử lý rename có thể khác giữa các CI platform; hãy xác minh hành vi của nền tảng đang dùng. Nếu một workflow chung cần quyết định theo từng job, hãy tạo bước phát hiện changed files và xuất kết quả có cấu trúc thay vì dùng một trường số lượng file như thể đó là danh sách đường dẫn.

Selective pipeline cần có dependency graph. Nếu shared-contracts thay đổi, pipeline có thể chạy contract verification của orders-api và catalog-api dù source của hai consumer không đổi.

Khi không xác định được phạm vi ảnh hưởng, chạy tập test rộng hơn hoặc yêu cầu review thay vì mặc định bỏ qua kiểm tra.

## 9. Điều phối pipeline giữa nhiều repository

Có hai kiểu điều phối thường gặp:

**Orchestration:** một pipeline trung tâm kích hoạt pipeline của các dự án phụ thuộc, chờ kết quả và tổng hợp trạng thái. Phù hợp khi cần release train, phối hợp nhiều service hoặc một approval chung.

**Choreography/event-driven:** mỗi project phát event khi artifact hoặc contract mới được publish; consumer tự quyết định có cần chạy pipeline hay không. Phù hợp khi các nhóm có quyền sở hữu độc lập và không cần một coordinator kiểm soát mọi bước.

Có thể kết hợp cả hai: event thông báo artifact mới, còn release orchestrator được dùng cho các đợt phát hành cần phối hợp.

### 9.1. Ví dụ GitLab multi-project trigger

Một project có thể kích hoạt pipeline ở project khác:

~~~yaml
stages:
  - verify
  - downstream

verify-contract:
  stage: verify
  script:
    - ./scripts/validate-contract.sh

test-orders-consumer:
  stage: downstream
  trigger:
    project: commerce/orders-api
    branch: main
    strategy: depend
~~~

Ví dụ minh họa upstream pipeline chờ kết quả downstream theo cơ chế của GitLab. Cú pháp và lựa chọn strategy có thể phụ thuộc phiên bản GitLab đang sử dụng; cần đối chiếu tài liệu phiên bản triển khai.

Không nên mặc định dùng branch main cho release production nếu cần tái lập chính xác. Với release phối hợp, truyền hoặc tham chiếu một version/ref bất biến đã được phê duyệt để biết downstream đang kiểm thử contract hoặc artifact nào.

Trigger downstream không tự động truyền mọi artifact, secret hay context. Cần xác định dữ liệu nào được chuyển, cách downstream lấy artifact, token nào được dùng và quyền truy cập tối thiểu cho cross-project pipeline.

### 9.2. Ví dụ orchestration trung lập với nền tảng

~~~yaml
release:
  id: commerce-release-2026-08
  projects:
    - name: catalog-api
      ref: v3.6.1
      required: true
      action: verify-and-publish
    - name: orders-api
      ref: v2.8.0
      required: true
      action: verify-and-publish
    - name: web-frontend
      ref: v5.2.0
      required: false
      action: compatibility-test
  gates:
    - wait_for_required_projects
    - verify_contracts
    - verify_artifact_digests
    - require_release_approval
    - deploy_approved_artifacts
~~~

Đây là mô hình minh họa, không phải schema của một CI platform. Trong thực tế, cần định nghĩa ref bất biến, artifact digest, dependency order, timeout, retry, approval và cách xử lý khi một project thất bại.

## 10. Tránh trigger vòng lặp và pipeline bùng nổ

Khi A kích hoạt B, B publish artifact rồi lại kích hoạt A, hệ thống có thể tạo vòng lặp pipeline. Nếu mỗi downstream lại kích hoạt nhiều project khác, số pipeline có thể tăng theo cấp số nhân.

Các biện pháp:

- Ghi trigger source và upstream pipeline ID.
- Dùng event ID hoặc idempotency key để chống xử lý lặp.
- Chỉ trigger khi artifact/contract thực sự thay đổi.
- Phân biệt pipeline do source change với pipeline do downstream trigger.
- Có giới hạn fan-out, concurrency và timeout.
- Đặt quy tắc rõ cho retry và cancellation.
- Không để publish lại cùng digest tạo event mới vô hạn.

Một pipeline nên biết mình đang chạy vì thay đổi source, vì contract mới, vì release orchestrator hay vì lịch. Trigger reason giúp áp dụng policy và điều tra khi có pipeline bất thường.

## 11. Quản lý artifact và version giữa các dự án

Khi dự án cung cấp library hoặc service artifact cho consumer, cần một cách phát hành có thể xác định:

- Package name và version.
- Artifact URI và digest.
- Source commit và pipeline run.
- Provenance/SBOM/signature khi policy yêu cầu.
- Contract/schema version.
- Hỗ trợ tương thích và lịch deprecation.

Consumer nên pin phiên bản dependency rõ ràng thay vì lấy latest trong build production. Việc nâng version cần được thực hiện qua thay đổi có review và test tương thích.

Với service-to-service API, consumer thường không pin image của provider nhưng cần biết API contract/version được hỗ trợ. Có thể dùng API versioning, schema registry hoặc contract repository để theo dõi.

Build một lần và promote cùng artifact digest qua môi trường. Nếu artifact được build lại cho mỗi project/environment, cùng version string không bảo đảm cùng nội dung.

## 12. Giữ khả năng phát hành độc lập

Một project có thể release độc lập khi các điều kiện sau được đáp ứng:

- Có ownership rõ ràng và pipeline build/test riêng.
- Artifact có version và digest riêng.
- Contract với consumer tương thích hoặc có versioning.
- Database/data ownership không buộc deploy đồng thời.
- Config và feature flag cho phép bật/tắt hành vi theo release plan.
- Có thể triển khai và rollback mà không làm hỏng consumer đang chạy.
- Observability phân biệt service version và deployment.

Ví dụ, catalog-api thêm một endpoint mới mà orders-api chưa sử dụng. Provider có thể deploy endpoint mới trước; consumer nâng cấp sau. Khi consumer đã chuyển, provider mới có thể deprecate endpoint cũ theo chính sách.

Ngược lại, nếu thay đổi làm consumer hiện tại không thể chạy, hai dự án cần một kế hoạch phối hợp. Đừng gọi đó là release độc lập chỉ vì pipeline có hai job riêng.

### 12.1. Dùng feature flag để tách deploy khỏi release

Feature flag có thể giúp deploy code tương thích trước khi bật hành vi mới:

1. Deploy provider với API hoặc schema mới nhưng chưa mở luồng sử dụng.
2. Deploy consumer có khả năng dùng contract mới.
3. Chạy contract/integration tests và quan sát.
4. Bật tính năng theo nhóm hoặc theo service.
5. Sau khi consumer cũ không còn dùng contract cũ, lên kế hoạch loại bỏ.

Flag không thay thế versioning hoặc authorization. Backend vẫn phải kiểm tra quyền và tính hợp lệ của request.

## 13. Khi nào cần release phối hợp?

Một số thay đổi thực sự cần phối hợp nhiều dự án:

- Thay đổi contract phá vỡ tương thích mà không thể dùng giai đoạn chuyển tiếp.
- Migration database yêu cầu provider và consumer cùng thay đổi.
- Thay đổi giao thức authentication hoặc certificate ảnh hưởng nhiều service.
- Thay đổi event schema mà consumer cũ không thể xử lý.
- Release nghiệp vụ cần nhiều service cùng đạt một trạng thái trước khi mở traffic.

Khi đó, lập một release plan có:

- Danh sách project và owner.
- Phiên bản/ref hoặc commit được phê duyệt của từng project.
- Dependency order và điều kiện bắt đầu.
- Contract và compatibility matrix.
- Artifact digest của từng project.
- Môi trường kiểm thử tích hợp.
- Approval, thời điểm triển khai và người trực.
- Rollback/forward-fix plan cho từng service và dữ liệu dùng chung.

Nếu có thể, dùng expand-contract để chuyển thay đổi phá vỡ thành nhiều release tương thích. Nếu không thể, release orchestrator phải điều phối đúng thứ tự và có trạng thái tổng hợp.

## 14. Dữ liệu và database là ranh giới độc lập khó nhất

Hai service có pipeline riêng nhưng cùng ghi một database hoặc cùng sở hữu một bảng có thể vẫn bị coupling mạnh. Một migration của service A có thể làm service B lỗi dù B không thay đổi source.

Để giảm coupling:

- Mỗi service nên sở hữu dữ liệu và schema của mình khi kiến trúc cho phép.
- Tránh để nhiều service ghi trực tiếp vào cùng bảng do service khác quản lý.
- Dùng API hoặc event contract thay cho truy cập database nội bộ.
- Migration theo expand-contract.
- Giữ tương thích đọc/ghi trong cửa sổ chuyển đổi.
- Có migration test và backup/restore plan phù hợp.
- Ghi nhận migration version trong release manifest.

Nếu chưa thể tách database, hãy quản lý schema ownership, migration order và consumer compatibility rõ ràng. Pipeline cần kiểm tra các service phụ thuộc trước khi cho phép contract migration phá vỡ.

Không rollback migration phá hủy chỉ bằng cách deploy lại image cũ. Có thể cần restore dữ liệu, forward-fix hoặc migration bù; kế hoạch này phải được xác định trước release.

## 15. Bảo vệ quyền truy cập giữa các dự án

Cross-project pipeline thường cần đọc source, tải artifact hoặc trigger pipeline ở project khác. Đây là ranh giới quyền cần kiểm soát.

Thực hành:

- Dùng token/service identity riêng cho automation.
- Chỉ cấp quyền trigger hoặc đọc artifact ở project cần thiết.
- Ưu tiên credential ngắn hạn hoặc workload identity khi nền tảng hỗ trợ.
- Không chuyển secret qua pipeline variables nếu không cần.
- Không log token hoặc giá trị nhạy cảm.
- Xác minh downstream project, ref và artifact digest trước khi sử dụng.
- Giới hạn ai được sửa shared pipeline template và release orchestrator.
- Tách quyền build/test khỏi quyền publish/deploy production.

Không tin mọi pipeline được trigger từ project nội bộ. Một project có thể nhận thay đổi từ fork hoặc branch không bảo vệ. Downstream cần xác minh source identity, trigger context và artifact provenance theo policy.

## 16. Quản lý shared pipeline templates và reusable workflows

Các nhóm thường chia sẻ template để chuẩn hóa build, test, scan, publish và deploy. Template giúp giảm trùng lặp nhưng cũng tạo dependency giữa các dự án.

Nên:

- Có repository riêng cho template hoặc reusable workflow.
- Ghi owner, version, changelog và phạm vi hỗ trợ.
- Pin template theo version/ref được kiểm soát.
- Kiểm thử template với một số project đại diện.
- Phát hành thay đổi template theo quy trình có review.
- Có lịch nâng cấp và cách rollback về version trước.
- Tránh thay đổi hành vi production âm thầm qua branch main.

Một template thay đổi có thể tác động hàng trăm pipeline. Vì vậy, cần phân biệt patch sửa lỗi, thay đổi tương thích và thay đổi breaking; có thể dùng versioning hoặc migration guide để project chủ động nâng cấp.

Không nên tạo một template khổng lồ chứa mọi logic của mọi project. Hãy giữ phần chung ở mức build convention, security, artifact metadata và quality gate; logic nghiệp vụ riêng vẫn thuộc project owner.

## 17. Theo dõi trạng thái tổng hợp mà không mất chi tiết từng project

Release orchestrator có thể tổng hợp:

| Project | Pipeline | Contract | Artifact | Deployment |
| --- | --- | --- | --- | --- |
| catalog-api | Passed | Verified | Digest A | Staging verified |
| orders-api | Passed | Verified | Digest B | Staging verified |
| web-frontend | Running | Pending | Chưa có | Chưa deploy |

Trạng thái tổng hợp giúp biết release train đang ở đâu, nhưng không thay thế trạng thái gốc của từng project. Khi một project fail, cần liên kết tới pipeline run, log, test report và owner cụ thể.

Mỗi project nên phát ra kết quả có cấu trúc:

- Project name và source revision.
- Pipeline run ID.
- Contract/schema version đã kiểm tra.
- Artifact URI và digest.
- Kết quả quality gate.
- Deployment ID và environment nếu đã deploy.
- Trạng thái, timestamp và liên kết evidence.

Release orchestrator nên lưu cả kết quả thành công và thất bại, không chỉ danh sách job màu xanh.

## 18. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Mọi commit đều trigger mọi project | Pipeline chậm và tốn tài nguyên | Dependency graph và selective triggers |
| Dùng branch main làm đầu vào release phối hợp | Downstream có thể chạy revision khác giữa các lần retry | Pin ref/version bất biến |
| Chỉ chạy unit test trong project | Bỏ sót lỗi contract với consumer | Contract và integration tests theo dependency |
| Deploy tất cả service cùng nhau theo mặc định | Tạo coupling phát hành không cần thiết | Release độc lập khi contract cho phép |
| Giả định multirepo nghĩa là độc lập | Runtime/data coupling vẫn tồn tại | Đánh giá contract và ownership |
| Dùng chung database không có owner | Migration của một service làm service khác lỗi | Schema ownership và expand-contract |
| Trigger vòng lặp A→B→A | Pipeline bùng nổ hoặc chạy vô hạn | Trigger reason, event ID và idempotency |
| Truyền artifact qua tên tag | Consumer có thể lấy nhầm nội dung | Artifact digest và provenance |
| Dùng token có quyền rộng giữa project | Sự cố một pipeline ảnh hưởng nhiều repository | Least privilege và identity riêng |
| Template chung thay đổi không kiểm soát | Nhiều project bị ảnh hưởng bất ngờ | Version, pin và migration process |
| Release orchestrator che mất trạng thái project | Khó tìm owner và nguyên nhân lỗi | Giữ liên kết tới pipeline/evidence gốc |
| Rollback image nhưng quên migration | Ứng dụng cũ không đọc được dữ liệu mới | Kế hoạch dữ liệu và forward/rollback riêng |

## 19. Checklist thiết kế pipeline nhiều dự án

**Ranh giới và dependency**

- [ ] Repository, project, service và deployment unit được phân biệt rõ.
- [ ] Có dependency graph với loại dependency và owner.
- [ ] Contract/API/event/library/data được version hóa hoặc quản lý tương thích.
- [ ] Xác định dự án nào có thể build, test và release độc lập.
- [ ] Các thay đổi bắt buộc phối hợp có release plan riêng.

**Kiểm thử và trigger**

- [ ] Selective trigger chỉ chạy dự án/test liên quan.
- [ ] Thay đổi contract kích hoạt consumer/provider verification cần thiết.
- [ ] Có unit, component, contract, integration và post-deploy tests phù hợp.
- [ ] Có fallback khi không xác định được phạm vi ảnh hưởng.
- [ ] Downstream trigger có timeout, retry và chống vòng lặp.

**Artifact và phát hành**

- [ ] Mỗi project có artifact version và digest riêng.
- [ ] Build một lần và promote cùng digest qua môi trường.
- [ ] Có provenance/SBOM/scan evidence theo policy.
- [ ] Release orchestrator pin ref và artifact cụ thể.
- [ ] Deployment/rollback có thể thực hiện theo từng service khi kiến trúc cho phép.

**Bảo mật và vận hành**

- [ ] Cross-project identity có quyền tối thiểu.
- [ ] Secret không bị truyền hoặc log ngoài phạm vi cần thiết.
- [ ] Shared template có owner, version và quy trình cập nhật.
- [ ] Release status tổng hợp vẫn liên kết evidence từng project.
- [ ] Database migration và side effect có kế hoạch tương thích/phục hồi.
- [ ] Có release ID, pipeline run ID, deployment ID và incident linkage.

## Kết luận

Pipeline nhiều dự án cần phản ánh đúng dependency graph và hợp đồng giữa các thành phần. Khi một project có ownership, artifact, contract, dữ liệu và quy trình rollback đủ rõ, nó có thể build, kiểm thử và phát hành độc lập. Khi thay đổi phá vỡ tương thích hoặc dùng chung state, pipeline cần phối hợp có chủ đích với thứ tự, approval và kế hoạch dữ liệu cụ thể.

Selective triggers, contract testing, artifact digest bất biến, shared pipeline templates có version và release orchestration giúp cân bằng tốc độ với kiểm soát. Mục tiêu không phải gom mọi dự án vào một pipeline lớn, mà là để mỗi nhóm tự phát hành trong ranh giới an toàn và có bằng chứng rõ khi cần phối hợp với nhóm khác.
