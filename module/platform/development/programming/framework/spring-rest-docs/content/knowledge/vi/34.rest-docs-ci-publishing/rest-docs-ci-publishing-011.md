# Phân biệt tài liệu preview và tài liệu production

## 1. Mục tiêu và bối cảnh

Trong quy trình Spring REST Docs, HTTP tests tạo snippets cho request, response, payload, parameters và headers. Build tiếp tục ghép snippets thành Asciidoctor/Markdown, render HTML rồi có thể đưa tài liệu lên một địa chỉ preview để review hoặc lên website production cho người dùng API.

Hai môi trường này phục vụ mục đích khác nhau:

- **Preview documentation** là bản xem trước gắn với một thay đổi cụ thể, thường là pull request, commit hoặc build. Nó giúp reviewer kiểm tra nội dung và giao diện trước khi phát hành.
- **Production documentation** là bản chính thức gắn với API version/release đã được phê duyệt. Đây là nguồn mà developer, partner hoặc người dùng API được hướng dẫn truy cập.

Không nên coi preview là production chỉ vì cả hai cùng render thành công. Preview có thể chứa endpoint chưa phát hành, mô tả đang review, fixture thử nghiệm hoặc thông tin nội bộ. Production phải có classification, version, approval, access policy và lifecycle rõ ràng.

Bài học thuộc chương **CI và phát hành** của module **SPRING_REST_DOCS**. Module tạo tài liệu REST API có thể kiểm chứng từ HTTP tests dùng MockMvc, WebTestClient hoặc REST Assured; sinh snippets rồi biên soạn Asciidoctor/Markdown và tích hợp build/CI.

Sau bài học, bạn có thể:

- Phân biệt mục đích và vòng đời preview/production docs.
- Thiết kế URL, access control và retention cho từng môi trường.
- Tạo preview theo PR/commit mà không làm thay đổi tài liệu chính thức.
- Phát hành production docs theo API version và release.
- Promotion artifact đã kiểm tra qua các bước review.
- Kiểm soát dữ liệu, secrets, cache, indexing và links.
- Thiết lập CI/CD, approval gate, rollback và cleanup.

## 2. So sánh preview và production

| Tiêu chí | Preview docs | Production docs |
| --- | --- | --- |
| Mục đích | Review thay đổi trước release | Hướng dẫn chính thức cho audience đã xác định |
| Nguồn | PR branch/commit hoặc build cụ thể | Release/tag đã được phê duyệt |
| Nội dung | Có thể chưa hoàn chỉnh, có draft labels | Đã qua technical/security/editorial review |
| URL | Tạm thời, thường gắn PR/build | URL ổn định theo sản phẩm/version |
| Audience | Reviewer, team hoặc partner được mời | Public, partner hoặc internal theo classification |
| Access | Thường hạn chế | Theo chính sách phát hành |
| Retention | Ngắn, xóa sau review/merge | Theo vòng đời release và policy |
| Indexing | Không nên được index công khai | Có thể index nếu là public docs |
| Cache | Ngắn hạn, dễ invalidation | Có cache policy và versioning rõ |
| Approval | Review/CI checks | Release owner và approvals cần thiết |
| Rollback | Xóa preview hoặc rebuild PR | Trỏ lại bản release trước hoặc phục hồi version |
| Contract status | Đang đề xuất/thay đổi | Contract chính thức của release |

Một preview có thể được chia sẻ ra ngoài team nếu policy cho phép, nhưng cần xác định rõ audience và quyền truy cập. URL khó đoán không phải access control.

## 3. Vòng đời của preview documentation

Preview thường được tạo tự động khi có pull request hoặc commit cần review:

~~~mermaid
flowchart TD
    A["Developer opens PR"] --> B["Run REST Docs HTTP tests"]
    B --> C["Generate snippets"]
    C --> D["Assemble and render preview"]
    D --> E["Run link, secret and content checks"]
    E --> F{"Checks pass?"}
    F -->|No| G["Mark preview failed"]
    F -->|Yes| H["Upload isolated preview"]
    H --> I["Reviewer inspects URL"]
    I --> J{"PR merged or closed?"}
    J -->|No| I
    J -->|Yes| K["Promote approved release or delete preview"]
~~~

Preview nên có:

- Build/commit identifier để biết nội dung đến từ đâu.
- Banner dễ nhận ra là bản preview/draft.
- URL riêng, không ghi đè URL production.
- Access control phù hợp với classification.
- Thời hạn lưu hoặc cleanup khi PR đóng.
- Secret scanning và validation trước khi upload.
- Link tới PR/commit tương ứng để reviewer phản hồi.

### 3.1. Preview theo PR hay theo commit?

Có thể chọn một trong hai cách:

| Cách | Ưu điểm | Điểm cần kiểm soát |
| --- | --- | --- |
| Một URL cho mỗi PR | Dễ tìm và comment trong review | Build mới phải thay preview cũ có kiểm soát |
| Một URL cho mỗi commit | Artifact bất biến, truy vết chính xác | Có thể tạo nhiều preview và cần cleanup |
| Một URL cho mỗi branch | Dễ theo dõi nhánh dài hạn | Nội dung thay đổi liên tục, khó xác định snapshot reviewer đã xem |

Một mô hình thực tế là có alias theo PR trỏ tới artifact của commit mới nhất, đồng thời lưu artifact theo commit SHA để truy vết. Cần hiển thị rõ commit/build trên trang preview.

## 4. Production documentation có vòng đời release

Production docs nên được phát hành cùng API release hoặc một mốc version được quản lý:

~~~mermaid
flowchart TD
    A["Release candidate"] --> B["Run tests and generate docs"]
    B --> C["Render versioned documentation"]
    C --> D["Security and contract review"]
    D --> E{"Approvals complete?"}
    E -->|No| X["Block release"]
    E -->|Yes| F["Publish production version"]
    F --> G["Update version navigation"]
    G --> H["Monitor links and feedback"]
~~~

Production docs cần:

- API version/release rõ ràng.
- URL ổn định và navigation giữa các versions.
- Nội dung đã qua review.
- Access control theo public/partner/internal audience.
- Metadata về commit, build và release.
- Chính sách hỗ trợ/deprecation.
- Quy trình sửa lỗi và rollback.

Không nên để production docs tự động theo dõi nhánh main nếu API contract chưa được phát hành. Build từ main có thể là candidate; production release cần trigger và approval riêng theo release policy.

## 5. Tách URL và deployment target

Dùng URL hoặc deployment target riêng cho preview và production. Ví dụ minh họa:

| Môi trường | URL |
| --- | --- |
| PR preview | docs-preview.example.test/pr/482/ |
| Commit snapshot | docs-preview.example.test/commit/ab12cd3/ |
| Production latest | docs.example.test/api/ |
| Version cụ thể | docs.example.test/api/v2/ |
| Internal docs | docs-internal.example.test/services/orders/ |

Domain và path ở đây chỉ là ví dụ. Chọn URL theo hạ tầng, DNS, access policy và version strategy thực tế.

### 5.1. Không dùng cùng một thư mục publish

Không cho job preview ghi vào directory/bucket của production. Nếu dùng cùng object storage hoặc hosting platform, tách prefix, bucket, project hoặc deployment environment và credential.

Ví dụ cấu trúc artifact:

~~~text
artifacts/
├── preview/
│   ├── pr-482/
│   └── pr-483/
└── production/
    ├── v1/
    ├── v2/
    └── latest/
~~~

Tách target giúp tránh một PR vô tình ghi đè tài liệu chính thức. Quyền ghi production chỉ cấp cho publish job đã qua approval.

## 6. Access control và audience

Preview không mặc định là private. Một số static hosting tạo URL public dù URL chứa PR number hoặc token ngẫu nhiên. Phải kiểm tra access control thật sự ở hosting/storage layer.

| Audience | Preview | Production |
| --- | --- | --- |
| Public API | Có thể dùng URL tạm, không index trước release | Public site |
| Partner-only | Hạn chế người review được phép | Partner authentication/authorization |
| Internal | SSO/VPN hoặc access gateway | Internal portal |
| Restricted | Chỉ nhóm được cấp quyền | Hệ thống được phê duyệt riêng |

Các nguyên tắc:

- Dùng least privilege cho deployment credentials.
- Preview job không có quyền ghi production.
- Fork PR không được truy cập secrets của repository một cách mặc định.
- Không đưa credentials vào URL query, page source hoặc JavaScript bundle.
- Kiểm tra quyền download artifact, không chỉ quyền đọc repository.
- Dùng cơ chế xác thực của hosting thay vì dựa vào URL khó đoán.

### 6.1. Noindex không phải bảo mật

Có thể đặt header hoặc metadata để yêu cầu search engine không index preview, nhưng noindex không ngăn người có URL truy cập. Với tài liệu nội bộ, cần authentication/authorization ở server, gateway hoặc artifact store.

Đối với public preview chưa phát hành, có thể kết hợp noindex, access restriction và retention ngắn. Không coi robots directives là ranh giới bảo mật.

## 7. Dữ liệu và nội dung được phép xuất hiện

Preview có thể chứa thay đổi chưa phát hành, nhưng không vì vậy mà được phép chứa secret hoặc PII. Cả preview lẫn production phải tuân thủ cùng baseline bảo mật:

- Dùng synthetic fixtures trong HTTP tests.
- Preprocess Authorization, Cookie, Set-Cookie và body tokens.
- Scan generated snippets, assembled docs và rendered HTML.
- Không upload raw test logs/traces nếu không cần.
- Loại internal hostnames, private IPs và test-only routes khỏi public bundle.
- Xác định audience/classification trước khi publish.

Preview có thể có draft content, nhưng phải gắn nhãn rõ để người đọc không coi đó là contract đã phát hành.

### 7.1. Draft banner và trạng thái API

Một banner preview nên nêu:

- Đây là bản xem trước, chưa phải tài liệu chính thức.
- PR/commit/build đang được xem.
- Thời điểm tạo.
- Link tới pull request hoặc source change.
- Cách gửi feedback.

Không dùng banner thay cho classification/access control. Một preview internal vẫn phải được bảo vệ như tài liệu internal.

## 8. Artifact promotion: build một lần, phát hành có kiểm soát

Khi có thể, nên promotion chính artifact đã qua review thay vì build lại một lần khác cho production. Cách này giảm nguy cơ preview và production khác nhau do thời gian, dependency hoặc generated inputs.

Quy trình:

1. Build candidate từ commit đã xác định.
2. Chạy tests, tạo snippets và render docs.
3. Scan và review artifact.
4. Gắn metadata commit/build/version.
5. Sau approval, promote đúng artifact sang production target.
6. Ghi nhận destination và release identifier.

Artifact nên bất biến sau khi review. Nếu thay source, dependencies, template hoặc build configuration, cần tạo artifact mới và chạy lại các checks.

### 8.1. Khi nào phải rebuild?

Có thể phải rebuild nếu production yêu cầu environment-specific configuration, public base URL hoặc version metadata. Khi đó cần xác định phần nào được phép khác:

- Nội dung contract và snippets phải giữ nguyên.
- Base URL/permalink có thể được thay theo môi trường.
- Secret/configuration không được nhúng vào HTML.
- Build production phải chạy lại validation và scan.
- Artifact được publish phải có commit/build provenance riêng.

Không tuyên bố hai artifact giống nhau nếu thực tế đã rebuild và thay đổi nội dung.

## 9. Versioning và navigation production

Production docs nên giữ các phiên bản API được hỗ trợ:

~~~text
/api/
├── latest/
├── v1/
└── v2/
~~~

Các nguyên tắc:

- Version trong URL phải khớp API contract.
- latest trỏ tới version được xác định theo policy, không tự động trỏ tới release candidate.
- Version cũ có trạng thái support/deprecated rõ ràng.
- Link từ version cũ tới migration guide/version mới phải hoạt động.
- Preview version chưa phát hành không xuất hiện trong production navigation.
- Không ghi đè docs version cũ nếu cần giữ lịch sử contract.

Một API có thể có versioning theo URL, header hoặc media type. Cách tổ chức docs cần giải thích đúng versioning strategy; không mặc định mọi dự án đều có /v1/ trong endpoint.

## 10. Cache, indexing và retention

Preview và production cần cache policy khác nhau:

| Thành phần | Preview | Production |
| --- | --- | --- |
| Browser/CDN cache | Ngắn hoặc no-store tùy dữ liệu | Cache theo version/release |
| Search indexing | Thường noindex | Index nếu public |
| Artifact retention | Ngắn, gắn PR lifecycle | Theo release/audit policy |
| Cleanup | Khi PR đóng hoặc hết hạn | Theo deprecation/retention policy |
| URL stability | Tạm thời | Ổn định |
| Purge | Khi preview bị thay/xóa | Khi có incident hoặc release correction |

Với versioned production docs, URL có thể immutable và cache lâu. Alias latest cần cache/invalidation phù hợp để người đọc nhận release mới. Preview nên tránh cache lâu khiến reviewer nhìn thấy nội dung của commit cũ.

## 11. CI/CD tách preview và production

Pipeline có thể chia thành các workflow hoặc job có quyền khác nhau:

~~~mermaid
flowchart TD
    A["Pull request"] --> B["Docs build and tests"]
    B --> C["Secret scan and link validation"]
    C --> D["Upload isolated preview"]
    D --> E["Review and PR approval"]

    F["Release tag"] --> G["Build release candidate"]
    G --> H["Tests, scan and render"]
    H --> I["Release approval"]
    I --> J["Promote artifact to production"]
    J --> K["Post-deploy smoke checks"]
~~~

### 11.1. PR workflow

PR workflow thường:

- Chạy HTTP tests và tạo snippets.
- Assemble/render docs.
- Chạy secret scan, link check và Markdown/Asciidoctor validation.
- Upload preview artifact hoặc deploy preview URL.
- Đăng link preview vào PR qua cơ chế CI được phép.
- Cleanup preview khi PR đóng/merge hoặc hết retention.

Không cho PR từ fork sử dụng deployment secrets hoặc production credentials. Nếu cần preview cho fork, dùng sandbox không có secrets và dữ liệu tổng hợp.

### 11.2. Release workflow

Release workflow nên:

- Chỉ chạy từ tag/release event hoặc trigger được bảo vệ.
- Xác minh commit và version.
- Chạy tests từ clean build.
- Tạo candidate artifact và scan.
- Yêu cầu approvals theo policy.
- Promote artifact đã duyệt.
- Chạy smoke checks trên production URL.
- Ghi nhận release metadata và rollback target.

Preview success không tự động tương đương production approval.

## 12. Kiểm tra sau deploy và rollback

Sau khi publish production docs:

- Mở URL public/internal bằng đúng audience.
- Xác minh version, navigation và canonical links.
- Kiểm tra assets, anchors và search.
- Xác minh access control của internal/partner docs.
- Chạy smoke checks cho trang chính và một số operation quan trọng.
- Kiểm tra cache/CDN phục vụ đúng release.
- Theo dõi broken links và feedback.

Nếu release docs sai:

1. Dừng rollout tiếp theo.
2. Xác định artifact/version bị ảnh hưởng.
3. Trỏ alias về release trước hoặc deploy lại artifact đã biết tốt.
4. Purge cache/CDN nếu cần.
5. Gỡ preview/artifact có nội dung không được phép.
6. Nếu secret đã lộ, revoke/rotate theo incident process.
7. Tạo bản sửa, chạy lại scan/review và publish.
8. Ghi lại incident, phạm vi ảnh hưởng và hành động khắc phục.

Rollback docs không nhất thiết rollback API service. Nhưng nếu docs sai có thể khiến consumer gọi API sai, cần phối hợp API owner và release manager.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Preview ghi đè production | Dùng chung target hoặc credential | Tách target và quyền ghi. |
| Preview URL bị người ngoài truy cập | Nghĩ URL khó đoán là private | Bật access control thật ở hosting. |
| Reviewer thấy nội dung commit cũ | Cache preview quá lâu hoặc alias cập nhật sai | Gắn commit ID và purge/invalidate. |
| Draft bị hiểu là contract chính thức | Không có banner/status rõ | Gắn preview label và PR/build provenance. |
| Production chứa endpoint chưa release | Copy toàn bộ preview bundle | Tạo production allowlist từ release scope. |
| Preview có secret | Chỉ scan production | Scan mọi preview và artifact. |
| PR fork dùng được deployment secret | Workflow cấp quyền quá rộng | Không expose secrets cho untrusted PR. |
| Production latest trỏ release candidate | Không gắn version/release gate | Chỉ cập nhật alias sau approval. |
| Version cũ biến mất | Ghi đè cùng output path | Giữ versioned immutable outputs. |
| Rollback không phục hồi được docs | Không lưu artifact trước đó | Lưu release artifact/provenance. |
| Nội dung preview khác production | Build lại với inputs khác | Promote cùng artifact hoặc ghi rõ rebuild và kiểm tra lại. |

## 14. Bài thực hành

Thiết lập pipeline cho một module API có pull request preview và production docs theo version:

1. Chạy REST Docs tests để sinh snippets từ MockMvc hoặc WebTestClient.
2. Render docs vào artifact riêng cho PR.
3. Gắn banner preview, PR number, commit SHA và build timestamp.
4. Giới hạn quyền truy cập preview theo audience; xác minh noindex không bị coi là access control.
5. Đặt retention/cleanup khi PR đóng.
6. Tạo release candidate từ tag và chạy tests, secret scan, link validation.
7. Tạo versioned production bundle và kiểm tra allowlist.
8. Yêu cầu release approval trước khi publish.
9. Promote artifact đã duyệt hoặc ghi nhận rõ nếu phải rebuild.
10. Cập nhật alias latest sau release thành công.
11. Chạy post-deploy smoke checks và xác minh CDN/cache.
12. Mô phỏng rollback về artifact trước đó và cleanup preview.

**Tiêu chí hoàn thành:** preview có URL/access/retention riêng; production chỉ chứa nội dung đã duyệt và đúng version; CI/CD tách quyền PR/release; artifact có provenance; promotion và rollback tái lập được.

## Tài liệu tham khảo

- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
- [GitHub Actions — Deploying with GitHub Actions](https://docs.github.com/en/actions/deployment/about-deployments)
- [GitHub Actions — Workflow Artifacts](https://docs.github.com/en/actions/using-workflows/storing-workflow-data-as-artifacts)
- [GitHub — Managing Environments for Deployment](https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/managing-environments-for-deployment)
- [OWASP — CI/CD Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/CI_CD_Security_Cheat_Sheet.html)
- [Google Search Central — Block Search Indexing](https://developers.google.com/search/docs/crawling-indexing/block-indexing)
