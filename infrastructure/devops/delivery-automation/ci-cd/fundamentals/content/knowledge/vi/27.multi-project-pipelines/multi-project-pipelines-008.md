# Đánh giá độ phức tạp trước khi thêm điều phối nhiều pipeline

Điều phối nhiều pipeline giúp chia quy trình giao phần mềm thành các phần độc lập: build service, kiểm thử hợp đồng, publish artifact, triển khai hạ tầng và phát hành ứng dụng. Nhưng mỗi ranh giới pipeline cũng tạo thêm hợp đồng dữ liệu, trigger, quyền truy cập, trạng thái chờ, retry và cách xử lý lỗi. Nếu chỉ tách một pipeline lớn thành nhiều workflow mà không có nhu cầu độc lập thực sự, hệ thống có thể khó vận hành hơn trước.

Trước khi thêm orchestration, cần xác định vấn đề hiện tại, mức độ phụ thuộc giữa các dự án và chi phí điều phối sẽ phát sinh. Chỉ nên thêm lớp điều phối khi lợi ích về quyền sở hữu, tốc độ, khả năng tái sử dụng, cô lập lỗi hoặc phát hành độc lập lớn hơn chi phí phối hợp. Mục tiêu là chọn kiến trúc vừa đủ để các nhóm giao phần mềm có thể hiểu, kiểm soát và truy vết được toàn bộ luồng.

## 1. Điều phối nhiều pipeline là gì?

Một pipeline đơn thường xử lý các bước trong một repository hoặc một sản phẩm: kiểm tra mã nguồn, build, test, đóng gói và deploy. Điều phối nhiều pipeline xuất hiện khi một luồng phát hành cần kích hoạt hoặc phối hợp nhiều pipeline có vòng đời riêng.

Ví dụ một sản phẩm gồm:

- Web frontend trong repository riêng.
- API backend trong repository riêng.
- Database migration do một nhóm sở hữu.
- Hạ tầng Kubernetes được quản lý bằng repository IaC.
- Bộ kiểm thử contract và end-to-end dùng chung.
- Pipeline release tổng hợp các artifact tương thích rồi triển khai.

Mỗi pipeline có thể chạy độc lập, nhưng một bản phát hành hoàn chỉnh cần biết phiên bản nào của từng thành phần được kết hợp và điều kiện nào cho phép chuyển sang bước tiếp theo.

Một luồng khái niệm:

~~~mermaid
flowchart TD
    A[Release request] --> B[Build frontend]
    A --> C[Build backend]
    A --> D[Validate infrastructure]
    B --> E[Publish frontend artifact]
    C --> F[Publish backend artifact]
    D --> G[Publish infrastructure plan]
    E --> H[Integration and contract tests]
    F --> H
    G --> I[Environment preparation]
    H --> J[Release coordination]
    I --> J
    J --> K[Deploy and verify]
~~~

Điều phối không nhất thiết là một workflow trung tâm gọi tuần tự mọi job. Nó có thể dùng reusable workflow, parent-child pipeline, downstream trigger, event bus hoặc release service. Lựa chọn phụ thuộc vào mức độ kết hợp và quyền tự chủ của các dự án.

## 2. Bắt đầu từ vấn đề cần giải quyết

Không nên bắt đầu bằng câu hỏi “nên dùng công cụ orchestration nào?”. Hãy xác định vấn đề cụ thể của luồng hiện tại.

Những dấu hiệu có thể cho thấy cần điều phối nhiều pipeline:

- Một release cần artifact từ nhiều repository.
- Các nhóm muốn build và test độc lập nhưng cần một điểm phối hợp phát hành.
- Pipeline đang lặp lại cùng một logic ở nhiều dự án.
- Một thay đổi contract cần kích hoạt kiểm thử ở các consumer liên quan.
- Hạ tầng và ứng dụng có lịch phát hành khác nhau nhưng phải phối hợp theo một thứ tự.
- Cần một bản ghi release tổng hợp chứa chính xác digest/version của nhiều artifact.
- Có yêu cầu approval, promotion hoặc rollback ở cấp sản phẩm gồm nhiều service.

Ngược lại, nếu một repository chỉ có vài bước build-test-deploy tuần tự, việc tạo thêm một pipeline điều phối có thể không đem lại lợi ích. Một job graph rõ ràng hoặc reusable workflow đơn giản có thể đã đủ.

Hãy viết vấn đề dưới dạng kết quả có thể quan sát:

- Giảm thời gian chờ giữa build và integration test.
- Tránh deploy backend khi frontend contract chưa tương thích.
- Cho phép nhóm service phát hành độc lập nhưng vẫn tạo release record thống nhất.
- Loại bỏ logic build bị sao chép ở nhiều repository.
- Bảo đảm chỉ một release được thay đổi cùng môi trường production tại một thời điểm.

Nếu không thể nêu được vấn đề hoặc kết quả mong muốn, chưa có cơ sở tốt để thêm orchestration.

## 3. Phân biệt chia pipeline với điều phối pipeline

Chia pipeline là tổ chức lại các bước bên trong một workflow. Điều phối nhiều pipeline là phối hợp các workflow có thể được khởi chạy, theo dõi và thất bại độc lập.

| Mô hình | Đặc điểm | Phù hợp khi |
|---|---|---|
| Một pipeline nhiều job | Một DAG chứa build, test, publish và deploy | Các bước cùng repository, cùng quyền sở hữu và cùng vòng đời |
| Reusable workflow/template | Nhiều pipeline gọi lại một quy trình chuẩn | Muốn tái sử dụng logic mà không cần release coordinator riêng |
| Parent-child pipeline | Pipeline cha tạo pipeline con và tổng hợp kết quả | Một repository có nhiều module hoặc nhiều nhánh công việc |
| Multi-project/downstream pipeline | Một dự án kích hoạt pipeline của dự án khác | Có quan hệ phụ thuộc giữa repository hoặc team |
| Event-driven choreography | Pipeline phát event, hệ thống khác tự quyết định phản ứng | Các service độc lập, không cần một controller giữ toàn bộ luồng |
| Central release orchestration | Một release controller chọn phiên bản, điều phối và ghi trạng thái tổng thể | Cần phối hợp nhiều artifact, approval và promotion thành một release |

Đừng dùng nhiều pipeline chỉ để thay thế một YAML dài. Nếu các phần vẫn phải deploy cùng lúc, dùng cùng secret, cùng owner và không thể chạy độc lập, việc tách có thể chỉ chuyển độ phức tạp từ file cấu hình sang giao tiếp giữa workflow.

## 4. Đánh giá theo các chiều phức tạp

Một quyết định orchestration nên xem xét nhiều chiều cùng lúc. Không có một chỉ số duy nhất đủ để kết luận hệ thống đã cần nhiều pipeline.

| Chiều đánh giá | Câu hỏi cần trả lời | Dấu hiệu phức tạp tăng |
|---|---|---|
| Dependency graph | Pipeline nào cần kết quả của pipeline nào? | Nhiều nhánh phụ thuộc, fan-in/fan-out và chuỗi dài |
| Ownership | Ai sở hữu pipeline, artifact và môi trường? | Nhiều team, quyền và lịch phát hành khác nhau |
| Contract | Các pipeline trao đổi input/output nào? | Payload không ổn định, phụ thuộc ngầm vào branch hoặc tag |
| Trigger | Điều gì kích hoạt pipeline tiếp theo? | Nhiều event, webhook lặp, trigger vòng hoặc trigger không rõ nguồn |
| Versioning | Làm sao xác định bộ artifact tương thích? | Tag di động, version độc lập và thiếu release manifest |
| Failure handling | Khi một pipeline fail thì các pipeline khác làm gì? | Partial success, retry, compensation và trạng thái không rõ |
| Concurrency | Hai release có thể chạy cùng lúc không? | Tranh chấp môi trường, registry, migration hoặc release pointer |
| Security | Pipeline nào được phép đọc secret và deploy? | Trust boundary giữa repository, runner, project và environment |
| Observability | Có truy vết được toàn bộ release không? | Run ID rời rạc, log phân tán và thiếu correlation |
| Cost/latency | Điều phối làm tăng bao nhiêu thời gian và tài nguyên? | Queue dài, runner chờ, artifact truyền nhiều lần |

Hãy đánh giá theo quy trình thật và ghi lại các giả định. Một hệ thống có nhiều repository chưa chắc cần central orchestration; một monorepo cũng có thể cần nhiều pipeline nếu module có quyền sở hữu và vòng đời độc lập.

## 5. Vẽ dependency graph trước khi thiết kế trigger

Trước khi viết workflow, hãy vẽ DAG mô tả quan hệ cần thiết. Mỗi node đại diện cho một công việc hoặc pipeline; mỗi cạnh biểu diễn một điều kiện đầu vào hoặc kết quả bắt buộc.

Ví dụ:

~~~mermaid
flowchart LR
    A[API source] --> B[Build API]
    B --> C[API artifact]
    D[Web source] --> E[Build Web]
    E --> F[Web artifact]
    C --> G[Contract tests]
    F --> G
    H[Infrastructure source] --> I[Validate IaC]
    I --> J[Infrastructure plan]
    G --> K[Release candidate]
    J --> K
    K --> L[Deploy]
~~~

Khi đọc graph, cần kiểm tra:

- Có chu trình phụ thuộc hay không.
- Node nào thật sự cần chờ node khác.
- Công việc nào có thể chạy song song.
- Có node nào chỉ là bước chuyển tiếp không cần thiết.
- Kết quả nào phải được lưu bền vững để pipeline sau sử dụng.
- Khi một node fail, những node nào cần dừng và những node nào vẫn có giá trị chẩn đoán.

Nếu một pipeline A kích hoạt B, B lại kích hoạt A khi nhận kết quả, có nguy cơ tạo trigger loop. Nếu nhiều nhánh cùng chờ một pipeline tổng hợp, cần xác định rõ cách correlation và timeout khi một nhánh không gửi kết quả.

Không xây DAG dựa trên giả định “pipeline chạy trước chắc chắn đã xong”. Phải có dependency hoặc event/result contract thể hiện điều kiện đó.

## 6. Phân biệt dependency bắt buộc và dependency tùy chọn

Không phải mọi thành phần trong sản phẩm đều phải hoàn tất để release tiếp tục.

Ví dụ:

| Dependency | Loại | Hành vi khi không thành công |
|---|---|---|
| Backend artifact | Bắt buộc | Không tạo release candidate |
| Frontend contract test | Bắt buộc nếu thay đổi contract liên quan | Chặn promotion |
| Documentation site | Tùy chọn theo sản phẩm | Có thể cảnh báo hoặc phát hành riêng |
| Security policy scan | Bắt buộc theo release policy | Chặn phát hành nếu gate không đạt |
| Analytics dashboard | Có thể độc lập | Không nhất thiết chặn deploy ứng dụng |
| Database migration | Bắt buộc nếu artifact cần schema mới | Không deploy code phụ thuộc khi migration chưa đạt |

Phân loại rõ giúp tránh một pipeline phụ không quan trọng làm chặn toàn bộ release. Ngược lại, không được đánh dấu một dependency bắt buộc thành optional chỉ để pipeline tiếp tục chạy.

Mỗi dependency cần mô tả điều kiện pass, fail, timeout và không có kết quả. Trạng thái “chưa nhận được kết quả” không tương đương với “đã thành công”.

## 7. Chọn mô hình điều phối phù hợp với mức độ kết hợp

Có thể dùng các mô hình từ đơn giản đến phức tạp:

### 7.1. Một pipeline với nhiều job

Đây là lựa chọn đơn giản khi các bước cùng repository và cùng quyền sở hữu. DAG trong một workflow thường đủ để thể hiện dependency, concurrency và kết quả.

Ưu điểm:

- Một run ID tổng thể.
- Dễ theo dõi log và trạng thái.
- Không cần truyền kết quả qua event ngoài.
- Ít hợp đồng giữa các pipeline.

Hạn chế là workflow có thể lớn, quyền truy cập và lịch chạy có thể bị gắn với một repository, khó để team khác quản lý độc lập.

### 7.2. Reusable workflow hoặc pipeline template

Dùng khi nhiều dự án cần chung quy trình build, scan, sign hoặc deploy. Workflow gọi lại nhận input rõ ràng và trả output theo contract.

Ví dụ GitHub Actions reusable workflow:

~~~yaml
name: Build service

on:
  workflow_call:
    inputs:
      java-version:
        required: true
        type: string
    outputs:
      artifact-digest:
        description: Digest of the published artifact
        value: ${{ jobs.build.outputs.digest }}

permissions:
  contents: read
  packages: write

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      digest: ${{ steps.publish.outputs.digest }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: ${{ inputs.java-version }}
      - name: Build
        run: ./mvnw --batch-mode verify
      - id: publish
        name: Publish artifact
        run: |
          digest="$(./scripts/publish-artifact.sh)"
          echo "digest=$digest" >> "$GITHUB_OUTPUT"
~~~

Workflow gọi:

~~~yaml
jobs:
  build-api:
    uses: ./.github/workflows/build-service.yml
    permissions:
      contents: read
      packages: write
    with:
      java-version: '21'
~~~

Ví dụ minh họa contract input/output. Script publish cần chỉ ghi digest đã được registry xác nhận ra stdout; log chẩn đoán nên ghi ra stderr. Quyền ở workflow được gọi không thể vượt quá quyền caller cấp. Workflow thực tế cần cấu hình quyền tối thiểu, secret inheritance rõ ràng và pin action theo chính sách tổ chức. Nếu gọi reusable workflow từ repository khác, hãy tham chiếu một ref tin cậy và bất biến theo chính sách, thay vì một branch có thể di chuyển. Reusable workflow giúp chia sẻ logic, nhưng bản thân nó chưa phải release orchestrator.

### 7.3. Parent-child hoặc downstream pipeline

Dùng khi một pipeline cần kích hoạt các pipeline khác và chờ kết quả. Mô hình này hữu ích cho monorepo nhiều module hoặc các repository có quan hệ phụ thuộc trực tiếp.

Cần xác định:

- Parent có chờ child hoàn tất không.
- Child trả kết quả bằng cách nào.
- Parent xử lý child failed, cancelled và timeout ra sao.
- Ai có quyền kích hoạt child.
- Event có thể được gửi lại không.
- Child có được chạy độc lập không.

Một parent không nên chỉ gửi trigger rồi giả định child đã thành công. Cần có run identity và cách đọc trạng thái cuối.

### 7.4. Event-driven choreography

Một pipeline phát event như ArtifactPublished; consumer khác nhận event và thực hiện công việc của mình. Mô hình này giảm phụ thuộc trực tiếp giữa các repository.

Ưu điểm:

- Producer không cần biết mọi consumer.
- Các nhóm có thể phát triển pipeline riêng.
- Dễ mở rộng thêm consumer khi event contract ổn định.

Hạn chế:

- Khó biết toàn bộ release đang ở trạng thái nào.
- Event có thể bị trễ, lặp hoặc đến sai thứ tự.
- Cần deduplication, correlation ID, retry và dead-letter handling.
- Việc điều tra phải nối nhiều hệ thống.

Choreography phù hợp khi các service thực sự độc lập. Nếu một release phải chờ tất cả thành phần đạt rồi mới promotion theo một gate tập trung, một coordinator có thể dễ kiểm soát trạng thái hơn.

### 7.5. Central release orchestration

Một release controller nhận yêu cầu phát hành, chốt bộ artifact, kiểm tra policy, chờ approval, điều phối deploy và lưu release record.

Nó phù hợp khi có nhiều thành phần phải được phát hành như một sản phẩm thống nhất. Nhưng nó cũng tạo thêm một hệ thống quan trọng cần vận hành, bảo mật, nâng cấp và khôi phục.

Chỉ nên xây khi các workflow đơn giản hơn không đáp ứng được nhu cầu về trạng thái tổng thể, approval, promotion hoặc audit.

## 8. Định nghĩa contract giữa các pipeline

Pipeline không nên phụ thuộc vào chi tiết nội bộ của pipeline khác. Chúng cần một contract mô tả rõ input, output, trạng thái và phiên bản.

Một contract có thể gồm:

| Trường | Ý nghĩa |
|---|---|
| Event type | Loại sự kiện, ví dụ ArtifactPublished |
| Schema version | Phiên bản cấu trúc payload |
| Producer | Repository/project và pipeline phát event |
| Run identity | Workflow run ID và attempt |
| Source revision | Commit SHA hoặc tag bất biến |
| Artifact coordinate | Registry, package, version, digest |
| Provenance | Bằng chứng nguồn gốc build |
| Target | Environment hoặc release channel nếu có |
| Correlation ID | Liên kết các bước trong cùng release |
| Idempotency key | Nhận diện request lặp |
| Result/status | Thành công, thất bại, bị hủy hoặc chưa xác định |

Ví dụ event:

~~~json
{
  "eventType": "ArtifactPublished",
  "schemaVersion": 1,
  "producer": {
    "repository": "org/payments-api",
    "runId": "8421",
    "attempt": 1
  },
  "source": {
    "commit": "a1b2c3d4"
  },
  "artifact": {
    "name": "payments-api",
    "version": "2.8.1",
    "digest": "sha256:0123456789abcdef..."
  },
  "release": {
    "correlationId": "release-2026-11-18-001",
    "idempotencyKey": "payments-api:2.8.1"
  }
}
~~~

Payload là ví dụ minh họa. Không đưa secret vào event. Event nên chứa reference và digest; consumer lấy artifact từ registry bằng identity được cấp quyền.

Contract cần có quy tắc tương thích khi thêm, đổi hoặc xóa field. Consumer không nên bị hỏng chỉ vì producer thêm một trường tùy chọn mới. Thay đổi phá vỡ tương thích cần schema version mới hoặc giai đoạn chuyển tiếp.

## 9. Dùng artifact bất biến để nối các pipeline

Một lỗi thường gặp là pipeline sau checkout branch mới nhất và build lại, thay vì dùng artifact được pipeline trước tạo ra. Khi đó release không còn bảo đảm đã kiểm thử đúng sản phẩm nào.

Nên dùng nguyên tắc:

1. Source pipeline build artifact một lần.
2. Artifact được publish theo version và digest.
3. Test pipeline tải đúng digest đó.
4. Release pipeline ghi nhận digest đã được kiểm thử.
5. Deploy pipeline triển khai cùng digest qua các môi trường.
6. Mỗi bước lưu provenance và run ID liên quan.

Không dùng branch name hoặc tag di động làm contract duy nhất. Nếu một event nói version 2.8.1 nhưng tag có thể bị ghi đè, consumer có thể nhận nội dung khác với lần test trước.

Một release manifest có thể liên kết nhiều artifact:

~~~yaml
releaseId: payments-suite-2026.11.18.1
components:
  api:
    version: "2.8.1"
    digest: sha256:api...
  web:
    version: "5.4.0"
    digest: sha256:web...
  infrastructure:
    revision: "a1b2c3d4"
    planDigest: sha256:infra...
compatibility:
  apiContract: "v3"
  webRequiresApi: ">=2.8.0"
~~~

Manifest giúp xác định bộ thành phần đã được kết hợp và triển khai. Nó cần được lưu bất biến cùng release record.

## 10. Quản lý fan-out và fan-in

Fan-out xảy ra khi một pipeline kích hoạt nhiều pipeline con hoặc consumer. Fan-in xảy ra khi một bước cần tổng hợp kết quả từ nhiều nhánh.

Ví dụ fan-out:

- Build API, web, worker và migration song song.
- Chạy test trên nhiều runtime.
- Kiểm tra nhiều region hoặc môi trường.

Ví dụ fan-in:

- Tổng hợp kết quả test contract.
- Xác nhận tất cả artifact đã được publish.
- Kiểm tra policy của toàn bộ release manifest.
- Chờ approval trước khi promotion.

Fan-out làm tăng concurrency và có thể gây quá tải runner hoặc registry. Fan-in tạo điểm chờ; một pipeline chậm có thể kéo dài toàn bộ release.

Cần thiết kế:

- Giới hạn số job chạy đồng thời.
- Timeout cho mỗi nhánh.
- Trạng thái rõ cho success, failure, cancelled và missing.
- Quy tắc xử lý nhánh optional.
- Tổng hợp report ngay cả khi một số nhánh fail.
- Không promotion khi dependency bắt buộc chưa đạt.

Không nên dùng một khoảng sleep cố định để đợi pipeline con. Hãy chờ trạng thái có định danh hoặc nhận callback/event có correlation ID.

## 11. Tránh chu trình trigger và dependency ngầm

Trigger loop có thể xảy ra khi:

- Pipeline A publish artifact, event kích hoạt B.
- Pipeline B cập nhật file hoặc tag, tạo sự kiện kích hoạt A.
- A lại publish hoặc phát event mới.

Các cách giảm nguy cơ:

- Phân biệt event source và event type.
- Không kích hoạt publish khi commit chỉ thay đổi file generated.
- Dùng idempotency key để loại request lặp.
- Đặt giới hạn số lần kích hoạt theo release correlation.
- Tách branch/tag dùng cho automation khỏi branch nguồn.
- Kiểm tra actor và loại token tạo commit.
- Ghi nhận nguyên nhân trigger trong run metadata.

Dependency ngầm cũng nguy hiểm. Ví dụ pipeline deploy tự tải image tag latest vì “build pipeline thường chạy trước”. Không có contract hoặc dependency chính thức thì thứ tự thực tế có thể thay đổi khi queue, retry hoặc chạy thủ công.

Mọi phụ thuộc bắt buộc cần có input/output rõ và cách xác minh kết quả.

## 12. Xử lý failure, retry và partial success

Trong nhiều pipeline, một phần công việc có thể hoàn tất trong khi phần khác thất bại. Ví dụ API và web đã publish, nhưng migration validation fail. Release controller cần biết các artifact đã tạo ra vẫn tồn tại, nhưng chưa được promotion.

Cần xác định:

- Failure có dừng toàn bộ release không.
- Pipeline nào có thể chạy lại độc lập.
- Retry có tạo artifact/version mới hay dùng lại digest cũ.
- Event trùng có được deduplicate không.
- Một pipeline bị timeout nhưng side effect có thể đã hoàn tất thì kiểm tra trạng thái ở đâu.
- Có bước compensation hoặc rollback nào cần chạy không.
- Partial artifact có được giữ lại để debug hay cần dọn theo policy.

Retry chỉ phù hợp với lỗi tạm thời và phải có giới hạn. Với lỗi validation hoặc version conflict, retry cùng input thường không giải quyết vấn đề.

Không giả định rollback một pipeline sẽ tự động rollback tất cả pipeline khác. Nếu nhiều service đã deploy, việc phục hồi có thể cần thứ tự riêng và có thể dùng roll-forward thay vì rollback đồng loạt.

## 13. Điều phối concurrency và môi trường dùng chung

Nhiều pipeline độc lập vẫn có thể tranh chấp cùng tài nguyên:

- Hai release cùng deploy một service lên production.
- Hai migration cùng thay đổi một schema.
- Hai pipeline cùng cập nhật một channel pointer hoặc tag.
- Nhiều test cùng ghi vào một database dùng chung.
- Hai workflow cùng apply một hạ tầng Terraform state.

Cần xác định lock key theo tài nguyên:

~~~text
deploy:production:payments-api
migration:production:payments-db
publish:registry.example.com/payments-api:2.8.1
terraform:production:network-state
~~~

Không dùng một lock toàn cục nếu các tài nguyên độc lập có thể chạy song song. Không dùng lock theo run ID vì mỗi lần chạy sẽ có khóa khác nhau và không ngăn được tranh chấp.

Với lock phân tán, cần owner, lease/TTL và cơ chế ngăn worker cũ tiếp tục ghi sau khi mất quyền. Các thao tác có side effect nên idempotent hoặc có điều kiện để retry an toàn.

## 14. Ranh giới bảo mật giữa các repository và pipeline

Mỗi pipeline có thể chạy với token, runner và quyền khác nhau. Khi pipeline A kích hoạt pipeline B, cần xác minh ai được phép gửi trigger và B sẽ tin cậy dữ liệu nào.

Các nguyên tắc:

- Dùng token có quyền tối thiểu và thời hạn phù hợp.
- Ưu tiên OIDC/workload identity cho truy cập cloud nếu nền tảng hỗ trợ.
- Không truyền secret trong event payload hoặc artifact metadata.
- Consumer tự xác thực event và kiểm tra producer được phép.
- Không tin branch, repository hoặc actor chỉ vì tên xuất hiện trong payload.
- Giới hạn quyền deploy theo environment và resource.
- Tách quyền build, publish, approve và deploy khi cần.
- Không để pull request từ fork nhận secret production.
- Ghi audit cho trigger và hành động có đặc quyền.

Nếu pipeline trung tâm có quyền deploy mọi service, nó trở thành một trust boundary lớn. Một lỗi hoặc compromise ở coordinator có thể ảnh hưởng nhiều dự án. Cần giảm quyền và chia phạm vi theo môi trường hoặc domain sản phẩm.

## 15. Truy vết một release qua nhiều pipeline

Khi release đi qua nhiều repository, run ID của từng pipeline không đủ để nối chúng. Cần một correlation ID hoặc release ID chung, đồng thời giữ run ID riêng của từng producer/consumer.

Một release record nên ghi:

- Release ID và correlation ID.
- Source commit của từng component.
- Artifact version và digest.
- Pipeline run ID, attempt và producer.
- Contract test và security gate result.
- Approval identity và thời điểm.
- Target environment và deployment revision.
- Kết quả post-deployment validation.
- Rollback/roll-forward event nếu có.

Có thể biểu diễn mối quan hệ:

~~~mermaid
flowchart LR
    A[Release ID] --> B[API run ID]
    A --> C[Web run ID]
    A --> D[Infra run ID]
    B --> E[API digest]
    C --> F[Web digest]
    D --> G[Infra revision]
    E --> H[Deployment record]
    F --> H
    G --> H
    H --> I[Post-deploy evidence]
~~~

Nếu không có correlation ID, việc điều tra có thể phải tìm từng workflow theo timestamp và tên tag, rất dễ nối nhầm các lần chạy trùng nhau.

## 16. Đánh giá chi phí và lợi ích

Điều phối nhiều pipeline có chi phí trực tiếp và gián tiếp.

Chi phí trực tiếp:

- Runner minutes và thời gian queue.
- Artifact storage và network transfer.
- Event delivery, queue hoặc release controller.
- Monitoring, log và audit storage.
- Vận hành các integration và credential.

Chi phí phối hợp:

- Thiết kế và duy trì contract.
- Xử lý schema evolution.
- Điều tra lỗi xuyên repository.
- Quản lý quyền giữa các team.
- Xử lý retry, duplicate và partial success.
- On-call cho coordinator hoặc event infrastructure.

Lợi ích có thể gồm:

- Các nhóm phát hành độc lập.
- Build/test song song và giảm thời gian chờ.
- Tái sử dụng workflow chuẩn.
- Cô lập lỗi và quyền tốt hơn.
- Có release record thống nhất.
- Promotion và approval rõ ràng.
- Dễ mở rộng số lượng service khi contract ổn định.

Nên đo trước và sau thay đổi: lead time, queue time, pipeline duration, tỷ lệ retry, số lần trigger trùng, thời gian điều tra và số lần deploy lỗi. Không kết luận thành công chỉ vì số workflow giảm hoặc tăng.

## 17. Ma trận quyết định: có nên thêm orchestration không?

Có thể dùng ma trận định tính sau để thảo luận với các nhóm:

| Điều kiện | Chưa cần orchestration riêng | Có thể cần orchestration |
|---|---|---|
| Repository | Một repo hoặc các phần thay đổi cùng nhau | Nhiều repo có release lifecycle riêng |
| Ownership | Một team sở hữu toàn bộ | Nhiều team có quyền và lịch phát hành riêng |
| Dependency | Chuỗi job đơn giản | Nhiều nhánh, fan-in/fan-out hoặc cross-project dependency |
| Artifact | Một artifact chính | Nhiều artifact cần được chốt thành release |
| Approval | Một gate đơn giản | Approval/promotion theo thành phần hoặc môi trường |
| Failure | Một kết quả tổng thể | Partial success, retry và compensation cần quản lý |
| Traceability | Một run ID đủ | Cần release ID nối nhiều run |
| Security | Cùng trust boundary | Cần tách quyền producer/consumer |
| Scale | Ít pipeline, ít thay đổi | Nhiều service và tần suất phát hành cao |

Nếu hầu hết tiêu chí nằm ở cột trái, hãy giữ một pipeline hoặc dùng reusable workflow. Nếu nhiều tiêu chí nằm ở cột phải và đang gây vấn đề đo được, hãy thử orchestration có phạm vi nhỏ.

Không cộng điểm cơ học rồi lấy một ngưỡng tùy ý làm quyết định. Ma trận là công cụ đặt câu hỏi và làm rõ trade-off; một rủi ro nghiêm trọng về bảo mật hoặc tính nhất quán có thể quan trọng hơn nhiều tiêu chí khác.

## 18. Các dấu hiệu đang over-engineer

Có thể đang xây quá nhiều orchestration nếu:

- Một release controller chỉ chuyển tiếp lệnh giữa hai workflow không có logic.
- Nhiều tầng workflow gọi nhau nhưng không tạo ra ranh giới ownership rõ ràng.
- Mọi job đều phải chờ một coordinator trung tâm dù có thể chạy độc lập.
- Event payload chứa nhiều dữ liệu nội bộ thay vì reference ổn định.
- Một lỗi nhỏ buộc phải sửa nhiều repository chỉ để thay contract.
- Retry và trạng thái được triển khai riêng ở từng tầng mà không có quy tắc chung.
- Không ai hiểu đầy đủ trạng thái release đang ở đâu.
- Coordinator có quyền quá rộng chỉ để giảm số bước cấu hình.
- Thời gian điều tra dài hơn thời gian tiết kiệm từ parallelism.
- Nhóm phải duy trì nhiều queue, database và service cho một luồng ít thay đổi.

Nếu orchestration không tạo ra quyền tự chủ, khả năng tái sử dụng hoặc kiểm soát release rõ hơn, hãy xem xét đơn giản hóa.

## 19. Lộ trình áp dụng từng bước

Không cần chuyển toàn bộ hệ thống sang multi-project orchestration cùng lúc. Có thể triển khai theo từng bước:

1. **Ghi nhận hiện trạng:** vẽ pipeline và dependency graph hiện tại, đo thời gian, queue và lỗi.
2. **Chọn một pain point:** ví dụ cần phối hợp API và web trước release.
3. **Xác định contract:** input, output, artifact digest, event schema và correlation ID.
4. **Chọn mô hình đơn giản nhất:** reusable workflow, parent-child hoặc event-driven tùy nhu cầu.
5. **Thử trên staging hoặc một service:** giữ quy trình cũ làm phương án đối chiếu trong giai đoạn chuyển tiếp.
6. **Kiểm thử lỗi:** duplicate event, timeout, partial success, cancellation, retry và concurrency.
7. **Bổ sung security và audit:** identity, least privilege, secret scope và approval.
8. **Đo kết quả:** so sánh lead time, chi phí, độ tin cậy và khả năng điều tra.
9. **Mở rộng có chọn lọc:** chỉ nhân rộng khi contract và ownership đã rõ.
10. **Loại bỏ đường cũ:** khi luồng mới ổn định và release record đầy đủ.

Mỗi bước nên có tiêu chí hoàn tất. Không để hai cơ chế trigger cùng hoạt động lâu dài mà không có quy tắc xác định nguồn nào là chuẩn.

## 20. Checklist trước khi thêm điều phối nhiều pipeline

Trước khi thiết kế hoặc triển khai orchestration, hãy kiểm tra:

- [ ] Đã mô tả vấn đề hiện tại bằng kết quả có thể đo.
- [ ] Đã xác định một pipeline đơn hoặc reusable workflow có đủ hay không.
- [ ] Đã vẽ DAG và xác định dependency bắt buộc/tùy chọn.
- [ ] Không có trigger loop hoặc dependency ngầm.
- [ ] Mỗi pipeline có owner và ranh giới trách nhiệm rõ.
- [ ] Input/output contract có schema version và quy tắc tương thích.
- [ ] Artifact được định danh bằng version bất biến và digest.
- [ ] Release manifest liên kết đúng các artifact cần phối hợp.
- [ ] Fan-out/fan-in có timeout, concurrency limit và trạng thái missing rõ.
- [ ] Duplicate event và retry được xử lý idempotently.
- [ ] Failure, cancellation và partial success có quy tắc rõ.
- [ ] Publish, deploy và migration có concurrency control theo resource.
- [ ] Identity và secret scope được giới hạn theo producer/consumer.
- [ ] Approval và promotion gắn với đúng release manifest.
- [ ] Correlation ID nối được các run, artifact và deployment.
- [ ] Có audit, dashboard và runbook cho lỗi xuyên pipeline.
- [ ] Đã đo chi phí runner, queue, artifact transfer và vận hành.
- [ ] Có kế hoạch chuyển đổi, rollback và loại bỏ trigger cũ.

Điều phối nhiều pipeline là một quyết định kiến trúc, không chỉ là cách chia file YAML. Khi dependency, ownership, contract, failure semantics và trust boundary đã đủ phức tạp để gây chậm trễ hoặc rủi ro, orchestration có thể tạo ra giá trị rõ ràng. Nếu chưa có những nhu cầu đó, giữ quy trình đơn giản sẽ giúp nhóm phát hành nhanh và dễ kiểm soát hơn.

